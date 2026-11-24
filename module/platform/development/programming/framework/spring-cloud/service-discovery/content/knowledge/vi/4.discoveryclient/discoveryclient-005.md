# Bật hoặc tắt khám phá kiểu blocking và reactive

Spring Cloud cung cấp hai cách truy vấn service discovery ở phía ứng dụng: API **blocking** thông qua `DiscoveryClient` và API **reactive** thông qua `ReactiveDiscoveryClient`. Hai API này cùng phục vụ một mục tiêu là tìm danh sách service instance, nhưng có mô hình lập trình và cách sử dụng tài nguyên khác nhau. Ứng dụng Spring MVC thường phù hợp với luồng blocking; ứng dụng Spring WebFlux có thể sử dụng luồng reactive để tránh chặn event loop khi xử lý request.

Spring Cloud Commons cung cấp các thuộc tính cấu hình để bật hoặc tắt từng kiểu discovery. Việc lựa chọn cần dựa trên stack đang chạy, discovery provider có hỗ trợ API tương ứng hay không và những bean mà ứng dụng thực sự sử dụng. Bật một thuộc tính không tự tạo ra implementation nếu dependency hoặc provider không cung cấp khả năng đó.

## 1. Hai API discovery trong Spring Cloud

### 1.1. Blocking DiscoveryClient

`org.springframework.cloud.client.discovery.DiscoveryClient` là API đồng bộ. Các phương thức thường dùng gồm:

- `getServices()`: trả về danh sách service ID đã biết.
- `getInstances(serviceId)`: trả về danh sách `ServiceInstance` thuộc service ID được yêu cầu.

Khi gọi phương thức, luồng hiện tại chờ kết quả trả về. Đây là cách sử dụng đơn giản trong ứng dụng Spring MVC, command-line job hoặc các luồng xử lý đồng bộ.

Ví dụ:

```java
import java.util.List;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Service;

@Service
public class BlockingPaymentLookup {

    private final DiscoveryClient discoveryClient;

    public BlockingPaymentLookup(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public List<ServiceInstance> findInstances() {
        return discoveryClient.getInstances("payment-service");
    }
}
```

Phương thức `getInstances` trả về danh sách ngay trong luồng gọi. Nếu implementation phải truy cập registry từ xa hoặc chờ một thao tác đồng bộ, luồng hiện tại có thể bị giữ trong thời gian đó. Vì vậy, không nên gọi API blocking trực tiếp trên event loop của WebFlux.

### 1.2. ReactiveDiscoveryClient

`org.springframework.cloud.client.discovery.ReactiveDiscoveryClient` cung cấp API reactive, thường trả về `Flux<ServiceInstance>` cho danh sách instance và `Flux<String>` cho danh sách service. Kết quả được biểu diễn bằng Reactor Publisher để có thể kết hợp với các toán tử reactive và chuỗi xử lý bất đồng bộ.

Ví dụ:

```java
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.ReactiveDiscoveryClient;
import org.springframework.stereotype.Service;

import reactor.core.publisher.Flux;

@Service
public class ReactivePaymentLookup {

    private final ReactiveDiscoveryClient discoveryClient;

    public ReactivePaymentLookup(ReactiveDiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public Flux<ServiceInstance> findInstances() {
        return discoveryClient.getInstances("payment-service");
    }
}
```

`Flux` là một publisher có thể phát ra không, một hoặc nhiều instance. Nếu không có instance phù hợp, publisher có thể hoàn tất mà không phát phần tử nào. Consumer cần xử lý trường hợp danh sách rỗng bằng `switchIfEmpty`, `hasElements` hoặc logic tương đương tùy mục tiêu.

API reactive giúp ứng dụng kết hợp discovery với WebFlux, `WebClient` và các thao tác reactive khác mà không phải chờ kết quả đồng bộ ở điểm gọi. Tuy nhiên, tên API reactive không tự bảo đảm mọi thao tác I/O bên trong provider đều non-blocking. Khả năng thực tế phụ thuộc implementation discovery và phiên bản thư viện.

## 2. Các thuộc tính bật/tắt

Spring Cloud Commons có các thuộc tính cấu hình chính sau:

| Thuộc tính | Ý nghĩa | Giá trị thường dùng khi không khai báo |
|---|---|---|
| `spring.cloud.discovery.enabled` | Bật/tắt discovery ở mức tổng thể. | `true` |
| `spring.cloud.discovery.blocking.enabled` | Bật/tắt cấu hình discovery client kiểu blocking. | `true` |
| `spring.cloud.discovery.reactive.enabled` | Bật/tắt cấu hình discovery client kiểu reactive. | `true` |

Các giá trị mặc định trên là mặc định thường gặp của Spring Cloud Commons. Bean cụ thể vẫn phụ thuộc phiên bản Spring Cloud, starter/provider có trong classpath và các điều kiện auto-configuration khác.

Có thể bật cả hai API:

```yaml
spring:
  cloud:
    discovery:
      enabled: true
      blocking:
        enabled: true
      reactive:
        enabled: true
```

Khi đó, ứng dụng có thể sử dụng cả `DiscoveryClient` và `ReactiveDiscoveryClient` nếu provider đang dùng cung cấp implementation tương ứng và các điều kiện cấu hình được đáp ứng.

### 2.1. Chỉ bật blocking

Với ứng dụng Spring MVC chỉ cần API đồng bộ, có thể tắt phần reactive:

```yaml
spring:
  cloud:
    discovery:
      enabled: true
      blocking:
        enabled: true
      reactive:
        enabled: false
```

Ứng dụng tiếp tục sử dụng `DiscoveryClient`. Các thành phần yêu cầu `ReactiveDiscoveryClient` sẽ không có cấu hình reactive tương ứng từ auto-configuration bị tắt; nếu code vẫn inject bean đó, ứng dụng có thể không khởi động được.

### 2.2. Chỉ bật reactive

Với ứng dụng WebFlux và provider có hỗ trợ reactive discovery, có thể tắt phần blocking:

```yaml
spring:
  cloud:
    discovery:
      enabled: true
      blocking:
        enabled: false
      reactive:
        enabled: true
```

Ứng dụng nên inject `ReactiveDiscoveryClient` và giữ luồng xử lý ở dạng reactive. Những thành phần đang phụ thuộc trực tiếp vào `DiscoveryClient` blocking cần được kiểm tra trước khi tắt API này.

### 2.3. Tắt discovery ở mức tổng thể

Nếu ứng dụng không cần tra cứu dịch vụ thông qua Spring Cloud Discovery, có thể tắt discovery tổng thể:

```yaml
spring:
  cloud:
    discovery:
      enabled: false
```

Khi cờ tổng thể bị tắt, việc bật riêng `blocking.enabled` hoặc `reactive.enabled` không làm discovery tự hoạt động trở lại. Cần xem điều kiện auto-configuration của phiên bản đang dùng để biết chính xác những bean nào không được tạo.

Không nên dùng cờ tổng thể chỉ để tắt một kiểu API. Nếu ứng dụng vẫn cần blocking hoặc reactive discovery còn lại, hãy giữ `spring.cloud.discovery.enabled: true` và điều chỉnh cờ tương ứng.

## 3. Phân biệt discovery lookup và tự động đăng ký service

Tra cứu service và đăng ký service là hai hoạt động khác nhau:

- **Discovery lookup:** consumer hỏi registry để lấy service ID hoặc danh sách instance. `DiscoveryClient` và `ReactiveDiscoveryClient` phục vụ nhóm chức năng này.
- **Service registration:** provider gửi thông tin instance để registry biết dịch vụ đang chạy ở đâu. `ServiceRegistry` và cơ chế auto-registration tham gia nhóm chức năng này.

Vì vậy, tắt một API discovery không đồng nghĩa chắc chắn provider đã ngừng đăng ký. Nếu mục tiêu là tắt tự động đăng ký của Spring Cloud, có thể cấu hình riêng:

```yaml
spring:
  cloud:
    service-registry:
      auto-registration:
        enabled: false
```

Thuộc tính này kiểm soát cơ chế auto-registration của Spring Cloud. Cách provider cụ thể khởi tạo client hoặc đăng ký instance còn phụ thuộc implementation và cấu hình riêng của nó. Cần xác minh trạng thái đăng ký trên registry sau khi thay đổi cấu hình.

## 4. Chọn kiểu discovery theo ứng dụng

### 4.1. Ứng dụng Spring MVC

Spring MVC xử lý request theo mô hình servlet và thường sử dụng các API đồng bộ. `DiscoveryClient` là lựa chọn tự nhiên khi controller hoặc service cần lấy danh sách instance rồi thực hiện xử lý đồng bộ.

Ví dụ, một service nội bộ cần lấy địa chỉ các instance để ghi nhận thông tin vận hành có thể dùng `DiscoveryClient`. Nếu ứng dụng đã dùng `RestTemplate` hoặc `RestClient` với Spring Cloud LoadBalancer, cần kiểm tra đúng bộ tích hợp blocking tương ứng.

### 4.2. Ứng dụng Spring WebFlux

WebFlux sử dụng Reactor và event loop. Khi xử lý request reactive, nên dùng `ReactiveDiscoveryClient` hoặc cơ chế gọi dịch vụ reactive được Spring Cloud hỗ trợ. Tránh gọi phương thức blocking trực tiếp trong chuỗi `Mono`/`Flux`, vì một thao tác chờ đồng bộ có thể giữ event loop và làm giảm khả năng xử lý đồng thời.

Ví dụ kết hợp lookup với WebFlux:

```java
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.ReactiveDiscoveryClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;

@RestController
public class DiscoveryController {

    private final ReactiveDiscoveryClient discoveryClient;

    public DiscoveryController(ReactiveDiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    @GetMapping("/discovery/payment-instances")
    public Flux<String> paymentInstances() {
        return discoveryClient.getInstances("payment-service")
                .map(ServiceInstance::getUri)
                .map(Object::toString);
    }
}
```

Endpoint này minh họa cách trả dữ liệu discovery dưới dạng reactive. Trong ứng dụng thực tế, cần cân nhắc việc công khai hostname và port nội bộ ra API; thông tin registry thường chỉ nên được cung cấp cho công cụ quản trị có xác thực.

### 4.3. Ứng dụng có cả blocking và reactive

Một ứng dụng có thể chứa cả luồng MVC và reactive, hoặc có module tích hợp thư viện đồng bộ trong một hệ thống WebFlux. Trong trường hợp này, có thể cần cả hai API. Việc bật cả hai không có nghĩa ứng dụng nên trộn lẫn chúng tùy tiện; mỗi luồng nên dùng API phù hợp và tránh gọi blocking trên event loop.

Nếu provider chỉ cung cấp một kiểu discovery, bật cờ cho kiểu còn lại không tự tạo ra implementation. Khi đó, cần chọn provider hỗ trợ, dùng abstraction có sẵn của phiên bản Spring Cloud hoặc xây dựng adapter phù hợp với yêu cầu và hiểu rõ giới hạn của adapter.

## 5. Tích hợp với Spring Cloud LoadBalancer

Discovery client trả về danh sách instance; load balancer chịu trách nhiệm chọn một instance để gửi request. Spring Cloud LoadBalancer có các đường tích hợp blocking và reactive tương ứng với cách gọi của ứng dụng.

Ví dụ điển hình:

| Cách gọi | Kiểu xử lý | API/load balancer thường dùng |
|---|---|---|
| `RestTemplate` có `@LoadBalanced` | Blocking | Blocking load-balancing client và blocking discovery path. |
| `RestClient` có `@LoadBalanced` trong phiên bản hỗ trợ | Blocking | Blocking load-balancing client. |
| `WebClient` có `@LoadBalanced` | Reactive | Reactive load-balancing client và reactive discovery path. |

Ví dụ cấu hình `WebClient` load-balanced:

```java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class WebClientConfiguration {

    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder() {
        return WebClient.builder();
    }
}
```

Khi gọi URI dạng `http://payment-service/...`, Spring Cloud LoadBalancer có thể phân giải service ID thành instance phù hợp. Cần có dependency Spring Cloud LoadBalancer và discovery provider tương ứng. Cấu hình reactive discovery bị tắt có thể làm hỏng đường tích hợp reactive nếu phiên bản/provider đang dùng yêu cầu `ReactiveDiscoveryClient`.

Load balancing không phải là chức năng tự động của riêng `DiscoveryClient`. Một danh sách instance có thể được tra cứu thành công nhưng request vẫn cần timeout, retry và xử lý lỗi kết nối.

## 6. Cấu hình theo profile

Có thể dùng Spring profile để bật kiểu discovery phù hợp với môi trường hoặc ứng dụng:

```yaml
spring:
  config:
    activate:
      on-profile: mvc
  cloud:
    discovery:
      enabled: true
      blocking:
        enabled: true
      reactive:
        enabled: false
```

Trong profile `webflux`, có thể dùng cấu hình tương ứng:

```yaml
spring:
  config:
    activate:
      on-profile: webflux
  cloud:
    discovery:
      enabled: true
      blocking:
        enabled: false
      reactive:
        enabled: true
```

Đặt các document trong cùng `application.yml` (chèn dấu phân cách YAML `---` giữa hai document) hoặc tách thành `application-mvc.yml` và `application-webflux.yml`. Chỉ kích hoạt profile phù hợp với loại ứng dụng đang chạy. Nếu một service cần cả hai API, giữ cả hai cờ ở `true` và xác minh provider hỗ trợ.

Không nên sao chép cấu hình profile mà không kiểm tra các thư viện phụ thuộc. Ví dụ, một thư viện nội bộ có thể inject `DiscoveryClient` dù ứng dụng chính dùng WebFlux; tắt blocking discovery sẽ làm context khởi động thất bại nếu bean đó không còn được cung cấp.

## 7. Khi nào nên bật hoặc tắt?

| Tình huống | Cấu hình gợi ý | Lý do |
|---|---|---|
| Ứng dụng MVC chỉ dùng API đồng bộ | Blocking `true`, reactive `false` nếu chắc chắn không có dependency cần reactive discovery. | Giảm các cấu hình/bean không sử dụng. |
| Ứng dụng WebFlux dùng discovery reactive | Blocking `false` nếu không có thành phần blocking phụ thuộc; reactive `true`. | Giữ luồng xử lý reactive và tránh gọi đồng bộ trên event loop. |
| Ứng dụng có cả MVC và WebFlux hoặc hai loại client | Cả hai `true`. | Cho phép mỗi thành phần dùng API phù hợp. |
| Ứng dụng không sử dụng service discovery | Global `enabled: false`. | Tắt auto-configuration discovery ở mức tổng thể. |
| Provider chỉ hỗ trợ blocking | Blocking `true`; không dựa vào reactive flag để tạo API reactive. | Cần implementation thực sự hỗ trợ reactive nếu muốn dùng reactive discovery. |
| Chỉ muốn dừng provider tự đăng ký | Kiểm soát `service-registry.auto-registration.enabled` và cấu hình provider. | Đây là luồng registration, khác với lookup của consumer. |

Không nên tắt một kiểu API chỉ vì ứng dụng có tên là MVC hoặc WebFlux. Hãy kiểm tra các bean được inject trong toàn bộ context, các thư viện tích hợp và đường gọi LoadBalancer trước khi thay đổi.

## 8. Kiểm tra bean và chẩn đoán cấu hình

Sau khi thay đổi thuộc tính, cần xác minh ứng dụng có đúng API mong muốn hay không. Có thể kiểm tra bằng cách inject API cần dùng vào một bean nhỏ hoặc xem điều kiện auto-configuration trong log khởi động.

Nếu bật Actuator và cho phép endpoint conditions trong môi trường quản trị phù hợp, endpoint `/actuator/conditions` có thể giúp kiểm tra auto-configuration nào được áp dụng hoặc bị loại. Không công khai endpoint này không có bảo vệ ra môi trường bên ngoài.

Các tình huống thường gặp:

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không inject được `DiscoveryClient` | Blocking discovery bị tắt, global discovery bị tắt hoặc provider không có trên classpath. | Kiểm tra ba cờ discovery, dependency provider và điều kiện auto-configuration. |
| Không inject được `ReactiveDiscoveryClient` | Reactive discovery bị tắt hoặc provider không cung cấp implementation reactive. | Bật cờ reactive và xác minh provider/version thực sự hỗ trợ. |
| WebFlux bị chậm hoặc nghẽn event loop | Gọi API blocking trong luồng reactive hoặc provider reactive thực hiện I/O đồng bộ bên trong. | Dùng reactive implementation; nếu buộc phải bọc API blocking, chuyển tác vụ sang scheduler dành cho blocking và đánh giá giới hạn. |
| Tắt blocking làm `@LoadBalanced RestTemplate` lỗi | Đường gọi RestTemplate cần blocking discovery/load-balancing path. | Bật lại blocking hoặc chuyển client sang đường reactive phù hợp. |
| `WebClient` không phân giải được service ID | Reactive load-balancer/discovery path không có hoặc cấu hình dependency chưa đúng. | Kiểm tra Spring Cloud LoadBalancer, reactive discovery và provider. |
| Provider vẫn xuất hiện trên registry sau khi tắt lookup | Registration là luồng riêng và vẫn được provider thực hiện. | Kiểm tra `ServiceRegistry` và cờ auto-registration, sau đó xác minh trên registry. |
| API discovery trả danh sách rỗng | Service chưa đăng ký, status không phù hợp hoặc registry/cache chưa cập nhật. | Kiểm tra provider, registry, health và thời điểm refresh. |

### 8.1. Bọc blocking API trong ứng dụng reactive khi bắt buộc

Nếu một provider chỉ có `DiscoveryClient` blocking nhưng ứng dụng cần tích hợp tạm thời với chuỗi reactive, có thể chuyển lời gọi blocking sang `boundedElastic`:

```java
import java.util.List;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Service;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@Service
public class BlockingDiscoveryAdapter {

    private final DiscoveryClient discoveryClient;

    public BlockingDiscoveryAdapter(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public Mono<List<ServiceInstance>> findInstances(String serviceId) {
        return Mono.fromCallable(() -> discoveryClient.getInstances(serviceId))
                .subscribeOn(Schedulers.boundedElastic());
    }
}
```

Đây là cách cô lập thao tác blocking khỏi event loop, không biến I/O blocking thành I/O non-blocking. Cần giới hạn concurrency, timeout và theo dõi thread pool; không nên dùng adapter như lý do để bỏ qua một reactive provider phù hợp khi tải cao.

## 9. Lưu ý về phiên bản và bảo mật

- Các thuộc tính `spring.cloud.discovery.*` thuộc Spring Cloud Commons; kiểm tra tài liệu đúng release train đang dùng vì điều kiện auto-configuration và tên thuộc tính có thể thay đổi theo phiên bản.
- Cần đồng bộ phiên bản Spring Boot, Spring Cloud release train và discovery starter theo ma trận tương thích của dự án.
- Không giả định mọi registry đều cung cấp cả blocking và reactive implementation.
- Không gọi API blocking trên event loop của WebFlux; thao tác blocking cần được cô lập trên scheduler phù hợp nếu không thể thay bằng API reactive.
- Registry có thể chứa hostname, IP, port và metadata nội bộ. Bảo vệ API registry, Actuator và endpoint conditions bằng network policy, authentication và authorization phù hợp.
- Tắt discovery lookup không thay thế cấu hình bảo mật, deregistration hoặc quy trình dừng instance.
- Khi thay đổi cờ trong production, kiểm tra health indicator, gateway, load balancer và thư viện nội bộ có phụ thuộc vào các bean bị tắt hay không.

## Kết luận

`DiscoveryClient` là API blocking trả kết quả đồng bộ; `ReactiveDiscoveryClient` là API reactive trả dữ liệu qua Reactor Publisher. Spring Cloud Commons cho phép bật/tắt discovery tổng thể và từng kiểu API bằng các thuộc tính `spring.cloud.discovery.enabled`, `spring.cloud.discovery.blocking.enabled` và `spring.cloud.discovery.reactive.enabled`.

Hãy chọn API phù hợp với mô hình xử lý của ứng dụng, xác minh provider thực sự hỗ trợ và kiểm tra các thành phần phụ thuộc trước khi tắt bean. Đặc biệt, phân biệt discovery lookup với service auto-registration để tránh vô tình thay đổi hành vi đăng ký của provider khi mục tiêu chỉ là điều chỉnh cách consumer tra cứu instance.
