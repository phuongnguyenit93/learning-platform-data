# Phạm vi thuộc tính spring.cloud.loadbalancer

Trong module **Spring Cloud Service Communication Load Balancing**, ứng dụng gọi có thể liên hệ nhiều dịch vụ đích bằng service ID như `inventory-service`, `payment-service` hoặc `catalog-service`. Spring Cloud LoadBalancer dùng danh sách `ServiceInstance` từ discovery, lọc ứng viên theo chính sách được kích hoạt và chọn instance cho RestClient, WebClient hoặc OpenFeign gửi request. Mỗi dịch vụ đích có thể cần thời gian cache, retry, health check và chính sách định tuyến khác nhau.

Để cấu hình chính xác, cần hiểu phạm vi thuộc tính dưới tiền tố `spring.cloud.loadbalancer`: giá trị mặc định áp dụng chung, giá trị ghi đè theo từng LoadBalancer client, và một số công tắc đặc biệt chỉ có tác dụng ở cấp toàn ứng dụng. Một thuộc tính nằm dưới đúng tiền tố chưa chắc tự bật tính năng tương ứng; ví dụ cấu hình đường dẫn health check không tự sinh ra `HealthCheckServiceInstanceListSupplier`.

## 1. Ba phạm vi cần phân biệt

Trong Spring Cloud, ba tên sau có thể giống nhau về mặt chữ nhưng đại diện cho ba đối tượng khác nhau:

| Đối tượng | Ví dụ | Vai trò |
|---|---|---|
| Tên ứng dụng caller | `spring.application.name: order-service` | Định danh tiến trình Spring Boot đang gửi request |
| LoadBalancer client ID / service ID đích | `inventory-service` | Khóa dùng để chọn cấu hình và tìm các instance đích |
| Một ServiceInstance cụ thể | `inventory-1:8081` | Host, port, instance ID và metadata của một bản sao đang được discovery cung cấp |

Ví dụ trong một ứng dụng `order-service`:

~~~text
order-service (caller)
  |
  +-- RestClient -> http://inventory-service/api/items/42
  |                 LoadBalancer client ID: inventory-service
  |                 -> inventory-1 hoặc inventory-2
  |
  +-- WebClient  -> http://catalog-service/api/products/42
  |                 LoadBalancer client ID: catalog-service
  |                 -> catalog-a hoặc catalog-b
  |
  +-- OpenFeign  -> @FeignClient(name = "payment-service")
                    LoadBalancer client ID: payment-service
                    -> payment-1 hoặc payment-2
~~~

`spring.application.name` của caller không phải là client ID dùng để tra cứu các cấu hình theo dịch vụ đích. Với RestClient/WebClient được tích hợp `@LoadBalanced`, service ID thường đến từ host logic trong URI; với OpenFeign dùng load balancing, service ID tương ứng với tên dịch vụ được khai báo tại `@FeignClient(name = "...")`. `contextId` của Feign chủ yếu phục vụ định danh context/bean Feign, không nên nhầm với service ID thực sự gọi đến.

Spring Cloud LoadBalancer tạo context con cho mỗi service ID, thường khởi tạo khi service đó được gọi lần đầu. Các context này có thể có cấu hình `ReactorLoadBalancer` hoặc `ServiceInstanceListSupplier` riêng.

## 2. Cấu trúc tên thuộc tính

Có hai cách đặt cấu hình chính:

~~~text
spring.cloud.loadbalancer.<property>
spring.cloud.loadbalancer.clients.<clientId>.<property>
~~~

Dòng thứ nhất là giá trị mặc định dùng chung; dòng thứ hai là cấu hình theo LoadBalancer client ID. Với phần lớn thuộc tính được hỗ trợ ở cả hai nơi, Spring Cloud tạo cấu hình hiệu lực bằng cách kết hợp hai cấp, ưu tiên giá trị được đặt riêng cho client.

Ví dụ:

~~~yaml
spring:
  cloud:
    loadbalancer:
      health-check:
        initial-delay: 1s
        interval: 25s

      clients:
        inventory-service:
          health-check:
            interval: 8s

        catalog-service:
          health-check:
            initial-delay: 3s
~~~

Giả sử từng service đã được cấu hình sử dụng health-check supplier, các giá trị hiệu lực là:

| Client | Initial delay | Interval | Nguồn giá trị |
|---|---:|---:|---|
| `inventory-service` | 1 giây | 8 giây | Lấy delay chung, ghi đè interval riêng |
| `catalog-service` | 3 giây | 25 giây | Ghi đè delay riêng, lấy interval chung |
| `payment-service` | 1 giây | 25 giây | Không có cấu hình riêng, dùng cả hai giá trị chung |

Cấu hình per-client không yêu cầu nhân bản toàn bộ cây thuộc tính. Chỉ khai báo những trường cần thay đổi. Tuy nhiên, hành vi kết hợp chi tiết có thể khác với giá trị map/list phức tạp; khi gặp các khóa như `health-check.path`, cần kiểm tra cách map được hỗ trợ trong phiên bản đang sử dụng và thử nghiệm cấu hình hiệu lực.

`<clientId>` là tên logic của LoadBalancer client; trong bài này là service ID. Nếu viết nhầm `inventory` khi request dùng `inventory-service`, nhánh riêng đó sẽ không chi phối dịch vụ mong muốn.

## 3. Nhóm thuộc tính nào thường nằm trong namespace này?

Một số nhóm thường dùng:

| Nhóm | Thuộc tính đại diện | Mục đích |
|---|---|---|
| Bật/tắt lõi | `enabled` | Bật/tắt Spring Cloud LoadBalancer trên toàn ứng dụng |
| Cache instance | `cache.enabled`, `cache.ttl`, `cache.capacity` | Giảm số lần lấy danh sách instance từ discovery |
| Retry | `retry.enabled`, `retry.max-retries-on-same-service-instance`, `retry.max-retries-on-next-service-instance` | Kiểm soát cơ chế thử lại các lời gọi load-balanced |
| Health check | `health-check.initial-delay`, `health-check.interval`, `health-check.path` | Thời gian và URL kiểm tra các instance |
| Định tuyến có điều kiện | `zone`, `hint`, `hint-header-name` | Cung cấp zone/hint cho bộ lọc instance được cấu hình |
| Cấu hình sẵn | `configurations` | Chọn tập supplier/cấu hình LoadBalancer được cung cấp sẵn |
| Khởi tạo context | `eager-load.clients` | Khởi tạo trước context của những service ID được liệt kê |
| Quan sát | `stats.micrometer.enabled`, `stats.include-path` | Metrics của các lời gọi load-balanced |
| Tra cứu discovery | `service-discovery.timeout` | Timeout dành cho việc truy vấn service discovery |
| Sticky/subset | `sticky-session.*`, `subset.*` | Tinh chỉnh chính sách tương ứng khi đã kích hoạt |

Các thuộc tính được Spring Boot bind vào cấu hình và những thành phần load balancing liên quan. Không phải tất cả nhóm thuộc tính đều tương ứng với một tính năng mặc định đã được bật. Chẳng hạn, `zone` không tự tạo `ZonePreferenceServiceInstanceListSupplier` và `hint` không tự tạo `HintBasedServiceInstanceListSupplier`; phải có supplier tương ứng trong pipeline.

Tên, giá trị mặc định và sự hỗ trợ của thuộc tính phụ thuộc phiên bản Spring Cloud Commons/LoadBalancer. Khi chép cấu hình vào một dự án thực tế, kiểm tra tài liệu `Configuration Properties` của đúng release train thay vì suy đoán tên khóa.

## 4. Bốn công tắc có ý nghĩa toàn cục

Tài liệu Spring Cloud Commons nêu bốn thuộc tính có phạm vi đặc biệt. Không nên đối xử với chúng như mọi tùy chọn per-client khác.

| Thuộc tính | Phạm vi thực tế | Lưu ý |
|---|---|---|
| `spring.cloud.loadbalancer.enabled` | Toàn ứng dụng | Tắt ở global sẽ vô hiệu hóa Spring Cloud LoadBalancer; nhánh `clients.<id>.enabled` không bật lại độc lập |
| `spring.cloud.loadbalancer.retry.enabled` | Quyền bật retry chung | Khi global đã bật và cơ chế retry tương ứng có mặt, có thể tắt retry cho một client; global tắt thì client không bật ngược lại |
| `spring.cloud.loadbalancer.cache.enabled` | Quyền bật cache chung | Global tắt thì client không tự bật lại; nếu global bật, muốn bỏ cache riêng cho một client cần cấu hình supplier không gồm `CachingServiceInstanceListSupplier` |
| `spring.cloud.loadbalancer.stats.micrometer.enabled` | Toàn ứng dụng | Bật/tắt việc tạo lifecycle metrics; không phải công tắc metrics độc lập cho mỗi service |

Ví dụ:

~~~yaml
spring:
  cloud:
    loadbalancer:
      enabled: true

      retry:
        enabled: true

      cache:
        enabled: true

      stats:
        micrometer:
          enabled: true

      clients:
        payment-service:
          retry:
            enabled: false
~~~

Ở đây LoadBalancer vẫn hoạt động cho các service ID. Retry ở cấp global được cho phép, nhưng `payment-service` được cấu hình tắt retry của LoadBalancer. Các client khác có thể dùng retry nếu có integration/thư viện phù hợp và request đủ điều kiện.

Nếu đổi `spring.cloud.loadbalancer.retry.enabled` thành `false`, việc gán `clients.inventory-service.retry.enabled: true` không làm cơ chế retry của riêng inventory được bật lại. Tương tự, `clients.inventory-service.cache.enabled: false` không phải cách được bảo đảm để bỏ caching supplier cho riêng inventory. Hãy dùng cấu hình supplier riêng cho service nếu cần bỏ một thành phần trong chuỗi.

Đừng nhầm `stats.micrometer.enabled: true` với việc metrics lập tức xuất hiện. Ứng dụng còn cần `MeterRegistry` tương ứng, chẳng hạn từ Spring Boot Actuator và registry dùng để xuất metrics.

## 5. Ví dụ kết hợp cấu hình chung và riêng theo service

Giả sử `order-service` gọi hai dịch vụ: inventory thường có nhiều bản sao và đôi khi gặp lỗi mạng tạm thời; payment là tác vụ nhạy cảm với xử lý lặp và caller không muốn LoadBalancer tự retry.

~~~yaml
spring:
  application:
    name: order-service

  cloud:
    loadbalancer:
      enabled: true

      cache:
        enabled: true
        ttl: 35s
        capacity: 256

      retry:
        enabled: true
        max-retries-on-same-service-instance: 0
        max-retries-on-next-service-instance: 1
        retry-on-all-operations: false

      health-check:
        initial-delay: 1s
        interval: 25s
        path:
          default: /actuator/health
          inventory-service: /internal/ready

      clients:
        inventory-service:
          cache:
            ttl: 10s
          retry:
            max-retries-on-next-service-instance: 2
          health-check:
            interval: 10s

        payment-service:
          retry:
            enabled: false

      stats:
        micrometer:
          enabled: true
        include-path: false
~~~

Đọc cấu hình theo từng nhóm:

- **Cache:** `inventory-service` yêu cầu TTL 10 giây nếu sử dụng caching supplier; các client không có override kế thừa 35 giây. Caffeine spec riêng, nếu có, có thể ghi đè chính sách TTL/capacity của cache; không nên khai báo hai kiểu rồi kỳ vọng cả hai cùng điều khiển.
- **Retry:** `inventory-service` đặt tối đa hai lần thử ở instance mới theo cấu hình của Spring Cloud LoadBalancer; các client khác kế thừa một lần, còn `payment-service` tắt retry tại tầng này. Đây là số lần retry, không phải tổng số HTTP request; phải cộng lần gọi đầu.
- **Health check:** `inventory-service` lấy initial delay 1 giây và interval 10 giây nếu health-check supplier được kích hoạt. Đường dẫn `/internal/ready` áp dụng cho inventory; mặc định dành cho client khác là `/actuator/health`.
- **Metrics:** lifecycle Micrometer được cho phép ở global; `include-path: false` giảm nguy cơ bùng nổ số nhãn `uri` khi request path chứa ID động.

Đây là một mô hình cấu hình để giải thích phạm vi. Nó chưa tự xây dựng `HealthCheckServiceInstanceListSupplier` hoặc bổ sung các thư viện cần thiết cho retry/metrics; những thành phần đó phải được cấu hình trong ứng dụng.

## 6. Phân biệt cấu hình property và cấu hình strategy

Một lỗi phổ biến là cho rằng có thể viết:

~~~yaml
spring:
  cloud:
    loadbalancer:
      clients:
        inventory-service:
          strategy: random
~~~

`strategy: random` không phải thuộc tính chuẩn được tài liệu Spring Cloud LoadBalancer công bố để đổi thuật toán. Mặc định thường dùng `RoundRobinLoadBalancer`. Nếu muốn `inventory-service` dùng Random trong khi `payment-service` vẫn dùng Round Robin, hãy cấu hình riêng LoadBalancer client.

Ví dụ cách đăng ký theo service:

~~~java
@SpringBootApplication
@LoadBalancerClient(
        name = "inventory-service",
        configuration = InventoryLoadBalancerConfiguration.class
)
public class OrderApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

Định nghĩa `InventoryLoadBalancerConfiguration` trong package không bị component scan của ứng dụng chính quét như một cấu hình global, hoặc dùng lớp cấu hình riêng không gắn `@Configuration` rồi chỉ import qua `@LoadBalancerClient`:

~~~java
public class InventoryLoadBalancerConfiguration {

    @Bean
    ReactorLoadBalancer<ServiceInstance> randomLoadBalancer(
            Environment environment,
            LoadBalancerClientFactory factory) {

        String serviceId = environment.getProperty(
                LoadBalancerClientFactory.PROPERTY_NAME
        );

        return new RandomLoadBalancer(
                factory.getLazyProvider(
                        serviceId, ServiceInstanceListSupplier.class
                ),
                serviceId
        );
    }
}
~~~

Ví dụ này minh họa lựa chọn thuật toán theo service ID. Cần có các import Spring Cloud LoadBalancer tương ứng và cấu hình discovery cung cấp danh sách instance cho inventory. `@LoadBalancerClient` thiết lập bean trong context con cho `inventory-service`; nó khác với việc khai báo giá trị số/thời gian dưới `clients.inventory-service`.

Với nhiều dịch vụ cần cấu hình riêng, có thể dùng `@LoadBalancerClients` chứa nhiều khai báo `@LoadBalancerClient`. Không để các configuration class được component scan như cấu hình global, vì như vậy bean tùy chỉnh có thể áp dụng rộng hơn phạm vi mong muốn.

Thuộc tính `spring.cloud.loadbalancer.configurations` cung cấp một số cấu hình sẵn, ví dụ `weighted` hoặc `zone-preference`, nhưng không có nghĩa mọi loại chiến lược tùy biến đều bật được bằng một chuỗi tùy ý. Kiểm tra các giá trị được hỗ trợ ở phiên bản đang dùng.

## 7. Health check: scope và điều kiện kích hoạt

Đường dẫn health check là một trường hợp đặc biệt đã hỗ trợ map theo service ID ngay tại nhánh global:

~~~yaml
spring:
  cloud:
    loadbalancer:
      health-check:
        initial-delay: 1s
        interval: 20s
        path:
          default: /actuator/health
          inventory-service: /internal/ready
          catalog-service: /internal/health
~~~

`health-check.path.default` là đường dẫn dùng chung. Các khóa dưới `path` có thể ghi đè đường dẫn theo service ID. Đây là cú pháp map được duy trì để tương thích ngược; không phải dấu hiệu cho thấy mọi thuộc tính đều có thể viết ở dạng `spring.cloud.loadbalancer.<serviceId>.<property>`.

Nếu dùng `/actuator/health`, dịch vụ đích cần có Spring Boot Actuator hoặc endpoint tương ứng. Nếu service mở riêng management port, có thể cần cấu hình `health-check.port` cho request health check, chú ý sự khác nhau giữa cổng kiểm tra và cổng nghiệp vụ.

Để tạo health-check supplier, có thể đăng ký riêng cho một LoadBalancer client:

~~~java
public class InventoryHealthLoadBalancerConfiguration {

    @Bean
    ServiceInstanceListSupplier inventoryInstances(
            ConfigurableApplicationContext context) {
        return ServiceInstanceListSupplier.builder()
                .withDiscoveryClient()
                .withHealthChecks()
                .build(context);
    }
}
~~~

Và gắn cấu hình đó cho `inventory-service` bằng `@LoadBalancerClient(name = "inventory-service", configuration = InventoryHealthLoadBalancerConfiguration.class)`.

Nếu hệ thống dùng service registry đã lọc các instance không khỏe, việc kiểm tra lại từng instance từ caller có thể tạo thêm network traffic không cần thiết. Nếu health-check supplier được dùng, hãy đặt nó gần nguồn discovery trong chuỗi supplier theo hướng dẫn của Spring Cloud; supplier này có cơ chế giữ kết quả riêng và không nên tùy tiện bọc cache trùng.

Cấu hình `health-check.interval` chỉ điều khiển chu kỳ của supplier khi supplier này thật sự tồn tại. Nếu không thêm supplier, việc thay giá trị interval không làm caller tự kiểm tra sức khỏe từng instance.

## 8. Cache instance: scope khác TTL của HTTP client

LoadBalancer cache lưu kết quả danh sách `ServiceInstance` phục vụ việc chọn đích. Nó không phải cache HTTP response hay cache đối tượng nghiệp vụ.

~~~text
Request
  -> Service ID
     -> ServiceInstanceListSupplier
        -> cache danh sách instance
           -> chọn instance
              -> RestClient/WebClient/OpenFeign
                 -> HTTP request đến instance
~~~

Một cấu hình tiêu biểu:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        enabled: true
        ttl: 35s
      clients:
        inventory-service:
          cache:
            ttl: 5s
~~~

Khi cấu hình supplier có cache và được hỗ trợ ở phiên bản đang sử dụng, TTL riêng inventory có thể làm danh sách instance được cập nhật thường xuyên hơn. Tuy nhiên, việc đặt `ttl: 5s` không tự bảo đảm mọi request cập nhật tức thì: bản thân DiscoveryClient, registry hoặc các tầng cache khác cũng có chu kỳ làm mới.

Nếu thêm thư viện Caffeine, thuộc tính `spring.cloud.loadbalancer.cache.caffeine.spec` cho phép cấu hình cache theo cú pháp Caffeine. Khi đặt spec này, các thiết lập cache chung như `ttl` và `capacity` có thể bị spec ghi đè. Do đó, hãy chọn một cơ chế cấu hình nhất quán và xác minh kết quả.

Nếu discovery đã có cache dữ liệu instance riêng, ví dụ một số tích hợp registry, cân nhắc vô hiệu hóa cache của LoadBalancer để tránh cache nhiều tầng làm trạng thái instance chậm cập nhật. Đây là quyết định cấp ứng dụng và pipeline supplier; không nên suy ra chỉ từ một giá trị TTL.

## 9. Retry: global gate và chính sách theo service

Các thuộc tính thường dùng:

| Thuộc tính sau tiền tố `spring.cloud.loadbalancer.` | Ý nghĩa |
|---|---|
| `retry.enabled` | Công tắc bật cơ chế retry ở phạm vi toàn ứng dụng |
| `retry.max-retries-on-same-service-instance` | Số retry trên cùng instance |
| `retry.max-retries-on-next-service-instance` | Số retry với instance được chọn lại |
| `retry.retry-on-all-operations` | Có thử lại cả thao tác ngoài GET hay không |
| `retry.retryable-status-codes` | Tập HTTP status được xem là đủ điều kiện retry |
| `retry.retryable-exceptions` | Các loại exception được cấu hình để retry |
| `retry.avoid-previous-instance` | Hỗ trợ tránh lại instance vừa thất bại khi chọn instance mới |
| `retry.backoff.*` | Các thiết lập backoff cho reactive retry |

Đặt các trường về số lần thử hoặc loại lỗi ở nhánh `clients.inventory-service.retry.*` để tùy chỉnh inventory. Có thể tắt riêng retry cho `payment-service` bằng `clients.payment-service.retry.enabled: false` khi global đã bật.

Cần phân biệt công tắc cấu hình và cơ chế retry thật sự có sẵn. Với client blocking, hành vi retry phụ thuộc tích hợp và thư viện Spring Retry; với WebClient reactive, phụ thuộc reactive integration. Vì vậy, `retry.enabled: true` không có nghĩa mọi HTTP client tự động retry mọi request.

Retry một thao tác ghi không idempotent có thể gây tạo đơn hoặc trừ tiền hai lần. Tắt retry ở tầng LoadBalancer cho dịch vụ nhạy cảm là một lựa chọn, nhưng vẫn cần kiểm tra retry ở RestClient, Feign, gateway và tầng ứng dụng. Số retry ở nhiều tầng có thể nhân số lần thực thi vượt mong đợi.

`spring.cloud.loadbalancer.retry.backoff.min-backoff` và các trường tương tự không phải timeout của TCP connection; chúng điều khiển khoảng cách giữa các lần retry reactive khi bật backoff. HTTP connect/read/response timeout thuộc phần cấu hình transport hoặc từng HTTP client.

## 10. Zone, hint và chính sách chọn instance

Có thể cấu hình `spring.cloud.loadbalancer.zone` để cho biết zone ưu tiên ở phía caller. Instance muốn được lọc theo zone cần có metadata phù hợp và pipeline cần chứa `ZonePreferenceServiceInstanceListSupplier`. Nếu không có instance trong zone mong muốn, supplier có thể trả lại danh sách đầy đủ theo chiến lược fallback của nó.

Hint thường dùng cho routing dựa trên metadata:

~~~yaml
spring:
  cloud:
    loadbalancer:
      hint:
        default: stable
        inventory-service: canary
      hint-header-name: X-SC-LB-Hint
~~~

`hint` hỗ trợ map `default` và khóa service ID; các phiên bản Spring Cloud đã duy trì cách khai báo theo service này để tương thích. Để có tác dụng lọc instance, cần cấu hình `HintBasedServiceInstanceListSupplier` hoặc component tương ứng. Header `X-SC-LB-Hint` có thể cung cấp hint trên request; danh sách instance cần metadata `hint` tương ứng. Nếu không có instance khớp, supplier mặc định có thể fallback về danh sách ban đầu.

Đừng đưa các giá trị như `zone`, `hint` hoặc `weight` vào một YAML bất kỳ rồi mặc định LoadBalancer sẽ đổi thuật toán. Chính sách cần supplier hoặc configuration preset thật sự đọc dữ liệu đó.

## 11. Những thuộc tính nằm ngoài spring.cloud.loadbalancer

Namespace này chỉ quản lý cơ chế LoadBalancer và các cấu hình liên quan. Nó không thay thế cấu hình của tất cả các phần trên đường đi HTTP.

| Nhu cầu | Cấu hình thực tế cần tìm |
|---|---|
| Định danh ứng dụng caller | `spring.application.name` |
| Danh sách instance tĩnh | `spring.cloud.discovery.client.simple.instances.<serviceId>` |
| Khai báo Eureka/Consul | Thuộc tính của Eureka/Consul DiscoveryClient tương ứng |
| URL, timeout và connection pool của RestClient | `RestClient.Builder` và HTTP request factory/transport |
| Timeout và pool của WebClient | `WebClient.Builder`, Reactor Netty hoặc connector đang dùng |
| Timeout của OpenFeign | `spring.cloud.openfeign.client.config.<name>.connectTimeout`, `readTimeout` và cấu hình client tương ứng theo phiên bản |
| Circuit breaker, rate limit, bulkhead | Resilience4j/Spring Cloud CircuitBreaker hoặc thành phần tương ứng |
| Health endpoint của service đích | Spring Boot Actuator và `management.*` |
| Tracing và metrics export | Spring Boot Actuator, Micrometer, tracing backend |

Đặc biệt, `spring.cloud.loadbalancer.service-discovery.timeout` liên quan thời gian truy xuất discovery. Không nên xem nó là timeout cho toàn bộ HTTP request tới instance đã chọn.

Ngoài ra, `clients.<clientId>` là nhánh cấu hình theo client; nó không phải nơi liệt kê `host`, `port` hoặc `instances` của service. Danh sách instance phải đến từ `ServiceInstanceListSupplier`, `DiscoveryClient`, registry hoặc nguồn dữ liệu được cung cấp phù hợp.

## 12. Cách xác minh cấu hình theo service

Giả sử caller gọi cùng lúc inventory và payment.

**Bước 1: xác minh service ID thật sự.** Dùng log hoặc breakpoint kiểm tra URI service ID được truyền cho client được cấu hình load-balanced. Với RestClient/WebClient ví dụ:

~~~java
// Bean Builder phải được cấu hình @LoadBalanced.
RestClient inventoryClient = loadBalancedBuilder
        .baseUrl("http://inventory-service")
        .build();

RestClient paymentClient = loadBalancedBuilder
        .baseUrl("http://payment-service")
        .build();
~~~

Nếu client gọi trực tiếp `http://localhost:8081`, chính sách của `clients.inventory-service` sẽ không tự tham gia vào request đó.

**Bước 2: xác minh danh sách instance.** Kiểm tra discovery trả đúng các `ServiceInstance` cho mỗi service ID, bao gồm metadata zone/hint nếu dùng routing theo metadata.

**Bước 3: kiểm tra giá trị hiệu lực.** Đối chiếu thuộc tính chung và riêng. Với ví dụ inventory interval 10 giây, payment interval kế thừa 25 giây; kiểm tra xem supplier health check đã được đăng ký cho các client cần kiểm tra chưa.

**Bước 4: kiểm tra tính năng đã thực sự bật.** Nếu muốn quan sát retry, tạo lỗi có kiểm soát tại instance đích với một HTTP GET idempotent và xác định request được thử lại ở đâu. Nếu muốn quan sát cache, thay đổi danh sách instance trong discovery và đo thời gian caller nhận cập nhật.

**Bước 5: kiểm tra metrics.** Bật registry phù hợp, gọi các endpoint qua client load-balanced, rồi đối chiếu metric của Spring Cloud LoadBalancer. Metric có thể chỉ xuất hiện sau khi có request. Khi path chứa giá trị động, cân nhắc `stats.include-path: false` để hạn chế cardinality.

**Bước 6: so sánh hai client.** Xác nhận thay đổi override của inventory không vô tình làm payment đổi behavior. Nếu đổi thuật toán hay supplier ở code, bảo đảm cấu hình dành riêng cho inventory không bị component scan ở mức toàn ứng dụng.

## 13. Các lỗi cấu hình thường gặp

**Nhầm client ID với tên ứng dụng caller.** Đặt thuộc tính dưới `clients.order-service` trong khi caller gọi `inventory-service` khiến override không áp dụng cho request inventory. Hãy đặt theo service ID đích.

**Đặt thuộc tính global vào client và kỳ vọng bật lại.** `clients.inventory-service.enabled: true` không đảo ngược `spring.cloud.loadbalancer.enabled: false`. Bốn công tắc đặc biệt cần được hiểu theo phạm vi thực tế.

**Chỉ khai báo health-check interval mà không tạo health-check supplier.** Interval không tự thêm bộ kiểm tra sức khỏe. Hãy dùng preset được hỗ trợ hoặc cấu hình `ServiceInstanceListSupplier` thích hợp.

**Dùng thuộc tính không tồn tại như strategy.** `clients.inventory-service.strategy: random` không phải cú pháp chuẩn để đổi thuật toán. Dùng `@LoadBalancerClient` và bean `ReactorLoadBalancer` chuyên trách.

**Gắn nhầm cache với HTTP response.** `cache.ttl` quản lý danh sách instance, không quản lý thời gian cache một response `GET /products`.

**Nhầm timeout discovery với timeout HTTP.** Cấu hình discovery timeout không bảo đảm giới hạn thời gian kết nối/đọc response của RestClient, WebClient hoặc Feign.

**Cho rằng retry.enabled luôn có retry.** Cần bảo đảm dependency/integration phù hợp; ngoài ra, các request không đủ điều kiện retry vẫn sẽ không được lặp lại.

**Dùng health-check.path như tên một thuộc tính đơn cho mọi service.** Đây là map với đường dẫn mặc định và các entry theo service ID. Cần kiểm tra đúng cấu trúc YAML và endpoint tồn tại.

## 14. Checklist trước khi triển khai

- [ ] Xác nhận client ID trùng service ID của request, không nhầm với `spring.application.name`.
- [ ] Dùng `spring.cloud.loadbalancer.*` cho mặc định, `spring.cloud.loadbalancer.clients.<clientId>.*` cho giá trị riêng được hỗ trợ.
- [ ] Nắm bốn công tắc global: `enabled`, `retry.enabled`, `cache.enabled` và `stats.micrometer.enabled`.
- [ ] Không kỳ vọng per-client override bật lại tính năng đã tắt toàn cục.
- [ ] Hiểu cache TTL là TTL của danh sách `ServiceInstance`.
- [ ] Bật supplier phù hợp khi cần health check, zone preference hoặc hint filtering.
- [ ] Dùng `@LoadBalancerClient` khi cần bean chọn instance hay chuỗi supplier chuyên biệt.
- [ ] Đặt timeout HTTP ở HTTP client; không nhầm với service-discovery timeout.
- [ ] Chỉ retry thao tác an toàn, và kiểm tra dependency/transport thật sự hỗ trợ retry.
- [ ] Quan sát cùng lúc hai service ID để kiểm tra override có tác dụng đúng phạm vi.
- [ ] Đối chiếu danh sách thuộc tính với phiên bản Spring Cloud Commons cụ thể đang dùng.

## Tài liệu tham khảo

- [Spring Cloud Commons — Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): cấu hình theo client, custom LoadBalancer, caching, health check, hint, zone và Micrometer.
- [Spring Cloud Commons — Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html): tên thuộc tính và giá trị mặc định.
- [Spring Cloud Commons — Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): retry các lời gọi load-balanced.

Phạm vi `spring.cloud.loadbalancer` cho phép định nghĩa mặc định nhất quán rồi điều chỉnh từng service ID khi cần. Nhưng mọi thuộc tính không có cùng mức độ ghi đè: một số là công tắc toàn cục, một số có thể được merge với cấu hình riêng, còn một số chỉ có tác dụng nếu supplier/strategy hoặc integration tương ứng đã được kích hoạt. Phân biệt ba trường hợp này giúp thiết kế chính sách load balancing ổn định mà không làm thay đổi ngoài ý muốn các dịch vụ khác.
