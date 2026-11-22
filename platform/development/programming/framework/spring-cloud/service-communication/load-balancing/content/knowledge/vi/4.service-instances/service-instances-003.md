# DiscoveryClient và ReactiveDiscoveryClient trong luồng cân bằng tải

Spring Cloud LoadBalancer cần biết những bản sao nào đang cung cấp một service ID trước khi có thể chọn instance để gửi request. Thông tin này thường đến từ một hệ thống service registry như Eureka, Consul hoặc ZooKeeper. Spring Cloud Commons chuẩn hóa cách ứng dụng đọc thông tin đó qua hai abstraction: **DiscoveryClient** cho lời gọi đồng bộ và **ReactiveDiscoveryClient** cho lời gọi reactive.

Hai abstraction cùng trả về các **ServiceInstance**, nhưng cách lấy dữ liệu và cách tích hợp với HTTP client khác nhau. Hiểu rõ điểm này giúp ứng dụng chọn đúng đường discovery cho RestClient, OpenFeign và WebClient, đồng thời tránh chặn luồng xử lý reactive.

## 1. Service discovery đứng ở đâu trong luồng cân bằng tải?

Service discovery giải quyết câu hỏi: “Những instance nào đang đăng ký dưới tên dịch vụ này và địa chỉ của chúng là gì?”. LoadBalancer giải quyết câu hỏi tiếp theo: “Trong danh sách đó, request hiện tại sẽ được gửi đến instance nào?”.

Discovery client lấy dữ liệu từ registry và chuyển thành các đối tượng ServiceInstance. LoadBalancer sử dụng danh sách này thông qua ServiceInstanceListSupplier, có thể cache hoặc lọc danh sách, rồi áp dụng thuật toán chọn instance.

~~~mermaid
flowchart TD
    A["Order Service"] --> B["HTTP client"]
    B --> C["LoadBalancer"]
    C --> D["ServiceInstanceListSupplier"]
    D --> E{"Nguồn discovery"}
    E --> F["DiscoveryClient"]
    E --> G["ReactiveDiscoveryClient"]
    F --> H["Service Registry"]
    G --> H
    H --> I["Danh sách ServiceInstance"]
    I --> J["Cache và bộ lọc"]
    J --> K["LoadBalancer chọn instance"]
    K --> L["Gửi request đến host và port"]
    L --> M["Service instance"]
~~~

Luồng này có thể chia thành bốn trách nhiệm:

1. **Đăng ký service:** instance cung cấp thông tin của nó cho registry.
2. **Khám phá service:** discovery client đọc các instance theo service ID.
3. **Cung cấp danh sách:** ServiceInstanceListSupplier chuyển kết quả discovery thành danh sách cho LoadBalancer và có thể thêm cache hoặc bộ lọc.
4. **Chọn instance:** ReactiveLoadBalancer hoặc BlockingLoadBalancerClient chọn một instance rồi HTTP client gửi request đến địa chỉ vật lý.

Discovery client không tự thực hiện Round Robin hay Random. Nó cung cấp dữ liệu đầu vào để LoadBalancer lựa chọn.

## 2. ServiceInstance biểu diễn một bản sao như thế nào?

Spring Cloud Commons định nghĩa interface **ServiceInstance** để mô tả một instance độc lập với loại registry đang dùng. Các thông tin thường được sử dụng gồm:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| serviceId | Tên logic của dịch vụ mà instance đăng ký |
| instanceId | Định danh của bản triển khai, nếu provider cung cấp |
| host | Host hoặc địa chỉ IP của instance |
| port | Cổng nhận request |
| secure | Cho biết instance sử dụng kết nối bảo mật hay không |
| metadata | Các nhãn bổ sung như zone, phiên bản hoặc hint |
| uri | URI vật lý được tạo từ thông tin instance |

Ví dụ, registry có thể trả về ba instance của **inventory-service**:

| Service ID | Instance ID | Địa chỉ | Metadata |
| --- | --- | --- | --- |
| inventory-service | inventory-1 | 10.0.0.21:8080 | zone=zone-a |
| inventory-service | inventory-2 | 10.0.0.22:8080 | zone=zone-a |
| inventory-service | inventory-3 | 10.0.1.31:8080 | zone=zone-b |

Client không cần gắn cứng các địa chỉ này vào mã nghiệp vụ. Nó gửi request đến service ID; LoadBalancer dùng ServiceInstance đã chọn để tạo URL thực tế.

Metadata có thể hỗ trợ định tuyến theo zone, hint hoặc phiên bản API. Ý nghĩa của từng metadata key phụ thuộc vào provider và cấu hình LoadBalancer. Một metadata key tự xuất hiện trong registry không có nghĩa LoadBalancer sẽ tự động sử dụng nó.

## 3. DiscoveryClient: API đồng bộ

**DiscoveryClient** nằm trong package org.springframework.cloud.client.discovery. Đây là abstraction đọc thông tin service discovery theo mô hình blocking.

Các phương thức chính:

| Phương thức | Kết quả | Công dụng |
| --- | --- | --- |
| description() | String | Mô tả implementation, thường dùng cho health indicator |
| getInstances(serviceId) | List<ServiceInstance> | Lấy các instance của một service ID |
| getServices() | List<String> | Lấy danh sách service ID đã biết |
| probe() | void | Kiểm tra discovery client có thể thực hiện lời gọi hay không |
| getOrder() | int | Xác định thứ tự khi có nhiều discovery client |

Ví dụ đọc các instance của một dịch vụ:

~~~java
@Service
class InventoryDiscoveryInspector {

    private final DiscoveryClient discoveryClient;

    InventoryDiscoveryInspector(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    List<ServiceInstance> findInstances() {
        return discoveryClient.getInstances("inventory-service");
    }

    List<String> findRegisteredServices() {
        return discoveryClient.getServices();
    }
}
~~~

Đây là lời gọi đồng bộ. Thread gọi phương thức chờ implementation lấy kết quả từ nguồn dữ liệu của nó. Với registry ở xa, thời gian chờ phụ thuộc vào mạng, timeout và cách provider triển khai.

Nếu service ID chưa được biết hoặc không có instance nào đăng ký, implementation thường trả về danh sách rỗng. Caller cần phân biệt trường hợp danh sách rỗng với lỗi kết nối registry: danh sách rỗng có thể là kết quả hợp lệ, còn lỗi kết nối thường được biểu diễn bằng exception.

### 3.1. Nhiều DiscoveryClient và thứ tự ưu tiên

Một ứng dụng có thể có nhiều implementation discovery trên classpath, ví dụ một client đọc Eureka và một client đọc Consul. DiscoveryClient mở rộng interface Ordered. Giá trị getOrder() cho phép sắp xếp thứ tự các implementation khi Spring Cloud kết hợp chúng.

Giá trị mặc định của DiscoveryClient là 0. Provider hoặc implementation tùy chỉnh có thể cung cấp thứ tự khác. Với các client có thuộc tính cấu hình riêng, có thể đặt order theo cấu hình provider, chẳng hạn:

~~~yaml
eureka:
  client:
    order: 0
~~~

Tên thuộc tính order phụ thuộc vào provider. Khi có nhiều registry cùng cung cấp một service ID, hãy kiểm tra thứ tự và cách composite client hợp nhất hoặc ưu tiên kết quả của các implementation. Không nên giả định rằng mọi registry đều trả cùng một danh sách instance.

## 4. ReactiveDiscoveryClient: API reactive

**ReactiveDiscoveryClient** cũng thuộc package org.springframework.cloud.client.discovery, nhưng trả kết quả dưới dạng Reactor Publisher. Thay vì trả về một List đã được tạo xong, API phát các phần tử theo luồng reactive.

Các phương thức chính:

| Phương thức | Kết quả | Công dụng |
| --- | --- | --- |
| description() | String | Mô tả implementation |
| getInstances(serviceId) | Flux<ServiceInstance> | Phát các instance của service ID |
| getServices() | Flux<String> | Phát các service ID đã biết |
| reactiveProbe() | Mono<Void> | Kiểm tra khả năng truy cập discovery theo mô hình reactive |
| getOrder() | int | Xác định thứ tự của implementation |

Ví dụ:

~~~java
@Service
class ReactiveInventoryDiscoveryInspector {

    private final ReactiveDiscoveryClient discoveryClient;

    ReactiveInventoryDiscoveryInspector(
            ReactiveDiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    Flux<ServiceInstance> findInstances() {
        return discoveryClient.getInstances("inventory-service");
    }

    Flux<String> findRegisteredServices() {
        return discoveryClient.getServices();
    }
}
~~~

Flux chỉ phát dữ liệu khi có subscription. Caller có thể nối các operator như map, filter, collectList hoặc timeout vào luồng này mà không cần chặn thread để chờ kết quả.

Không gọi block() bên trong một luồng WebFlux hoặc trên event-loop để lấy kết quả từ ReactiveDiscoveryClient. Việc block có thể làm mất lợi ích non-blocking, giữ event-loop trong lúc chờ registry và gây giảm thông lượng của toàn ứng dụng.

### 4.1. Reactive không chỉ là đổi List thành Flux

ReactiveDiscoveryClient phù hợp khi implementation bên dưới có thể thực hiện I/O theo mô hình reactive. Nếu một provider chỉ có API đồng bộ, việc bọc lời gọi blocking trong Flux không tự biến I/O đó thành non-blocking.

Khi lựa chọn provider, cần kiểm tra provider có cung cấp ReactiveDiscoveryClient thật sự hay chỉ có DiscoveryClient. Nếu chỉ có DiscoveryClient, ứng dụng vẫn có thể dùng đường blocking được hỗ trợ bởi Spring Cloud LoadBalancer; không nên tự viết một adapter reactive giả định rằng lời gọi registry đã trở thành non-blocking.

## 5. DiscoveryClient và ReactiveDiscoveryClient khác nhau ở đâu?

| Tiêu chí | DiscoveryClient | ReactiveDiscoveryClient |
| --- | --- | --- |
| Kiểu API | Đồng bộ, blocking | Reactive, non-blocking nếu provider hỗ trợ |
| Danh sách instance | List<ServiceInstance> | Flux<ServiceInstance> |
| Danh sách service ID | List<String> | Flux<String> |
| Kiểm tra kết nối | probe() | reactiveProbe() |
| Cách tiêu thụ | Gọi phương thức và nhận kết quả | Subscribe hoặc nối vào Reactor pipeline |
| Phù hợp với | RestClient, OpenFeign và stack blocking | WebClient reactive, WebFlux |
| Lưu ý | Thread có thể phải chờ I/O | Không block event-loop; cần provider reactive thực sự |

Hai interface không phải hai thuật toán cân bằng tải. Chúng là hai cách truy xuất dữ liệu discovery. Dù chọn interface nào, danh sách ServiceInstance cuối cùng vẫn được cung cấp cho LoadBalancer để chọn đích.

## 6. LoadBalancer kết nối với hai loại discovery client như thế nào?

Spring Cloud LoadBalancer sử dụng **ServiceInstanceListSupplier** để lấy danh sách instance. Supplier là lớp trung gian giữa discovery client và thuật toán chọn instance. Nó cũng là nơi có thể ghép cache, health check, zone preference hoặc bộ lọc khác.

Builder của ServiceInstanceListSupplier có hai phương thức quan trọng:

| Phương thức builder | Discovery API được sử dụng | Ý nghĩa |
| --- | --- | --- |
| withBlockingDiscoveryClient() | DiscoveryClient | Lấy instance qua API đồng bộ |
| withDiscoveryClient() | ReactiveDiscoveryClient | Lấy instance qua API reactive |

Ví dụ cấu hình supplier reactive:

~~~java
class InventoryReactiveLoadBalancerConfiguration {

    @Bean
    ServiceInstanceListSupplier inventoryServiceInstanceListSupplier(
            ConfigurableApplicationContext context) {

        return ServiceInstanceListSupplier.builder()
                .withDiscoveryClient()
                .withCaching()
                .build(context);
    }
}
~~~

Ví dụ cấu hình supplier blocking:

~~~java
class InventoryBlockingLoadBalancerConfiguration {

    @Bean
    ServiceInstanceListSupplier inventoryServiceInstanceListSupplier(
            ConfigurableApplicationContext context) {

        return ServiceInstanceListSupplier.builder()
                .withBlockingDiscoveryClient()
                .withCaching()
                .build(context);
    }
}
~~~

Đây là hai lựa chọn thay thế cho cùng một client ID. Không đăng ký cả hai cấu hình cùng lúc cho một LoadBalancer client theo cách tạo ra nhiều bean ServiceInstanceListSupplier cạnh tranh. Hãy chọn nguồn phù hợp với stack gọi dịch vụ và phiên bản Spring Cloud.

Có thể gắn một cấu hình riêng với service ID bằng @LoadBalancerClient:

~~~java
@SpringBootApplication
@LoadBalancerClient(
        name = "inventory-service",
        configuration = InventoryReactiveLoadBalancerConfiguration.class)
class OrderApplication {
}
~~~

Ví dụ này chọn cấu hình reactive cho inventory-service. Nếu dùng cấu hình blocking, thay lớp cấu hình tương ứng. Lớp được truyền vào thuộc tính configuration nên không nằm trong component scan như một cấu hình toàn cục; theo hướng dẫn Spring Cloud, lớp đó có thể không gắn @Configuration hoặc được đặt ngoài phạm vi component scan. Nếu không cần tùy biến supplier, hãy dùng auto-configuration mặc định của LoadBalancer.

Spring Cloud LoadBalancer tự cấu hình supplier dựa trên discovery client có trong ApplicationContext và các thuộc tính bật/tắt blocking hoặc reactive discovery. Trong cấu hình mặc định hiện hành:

- Nhánh reactive được tạo khi ReactiveDiscoveryClient có mặt và reactive discovery được bật. Supplier dùng withDiscoveryClient().
- Nhánh blocking được tạo khi DiscoveryClient có mặt và blocking discovery được bật. Supplier dùng withBlockingDiscoveryClient().

Ứng dụng thường không cần tự tạo supplier nếu auto-configuration đã cung cấp đúng implementation. Chỉ tạo cấu hình riêng khi cần thay đổi cache, health check, zone, hint hoặc chính sách lọc instance.

## 7. Chọn đường discovery theo HTTP client

### 7.1. RestClient

RestClient là HTTP client đồng bộ. Khi dùng builder được đánh dấu @LoadBalanced, Spring Cloud tích hợp BlockingLoadBalancerClient để phân giải service ID và chọn instance.

~~~java
@Configuration(proxyBeanMethods = false)
class InventoryHttpClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }
}
~~~

Ứng dụng gọi service ID như một host logic:

~~~java
@Service
class InventoryClient {

    private final RestClient restClient;

    InventoryClient(@LoadBalanced RestClient.Builder builder) {
        this.restClient = builder.build();
    }

    InventoryResponse getInventory(String sku) {
        return restClient.get()
                .uri("http://inventory-service/api/inventory/{sku}", sku)
                .retrieve()
                .body(InventoryResponse.class);
    }
}
~~~

Với stack blocking, supplier có thể lấy dữ liệu bằng DiscoveryClient thông qua withBlockingDiscoveryClient(). Request sẽ chờ cho đến khi bước chọn instance và lời gọi HTTP hoàn tất hoặc timeout.

### 7.2. WebClient

WebClient có thể sử dụng ReactorLoadBalancerExchangeFilterFunction để phân giải service ID trong một pipeline reactive.

~~~java
@Configuration(proxyBeanMethods = false)
class InventoryReactiveHttpClientConfiguration {

    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder() {
        return WebClient.builder();
    }
}
~~~

Ví dụ gọi service:

~~~java
@Service
class ReactiveInventoryClient {

    private final WebClient webClient;

    ReactiveInventoryClient(@LoadBalanced WebClient.Builder builder) {
        this.webClient = builder.build();
    }

    Mono<InventoryResponse> getInventory(String sku) {
        return webClient.get()
                .uri("http://inventory-service/api/inventory/{sku}", sku)
                .retrieve()
                .bodyToMono(InventoryResponse.class);
    }
}
~~~

Trong đường reactive, ServiceInstanceListSupplier thường lấy dữ liệu từ ReactiveDiscoveryClient thông qua withDiscoveryClient(). Kết quả discovery được nối vào pipeline reactive của LoadBalancer và WebClient.

### 7.3. OpenFeign

OpenFeign tạo client đồng bộ từ interface. Khi tích hợp Spring Cloud LoadBalancer, Feign dùng service ID để tìm instance qua load-balanced client theo stack blocking.

~~~java
@FeignClient(name = "inventory-service")
interface InventoryFeignClient {

    @GetMapping("/api/inventory/{sku}")
    InventoryResponse getInventory(@PathVariable String sku);
}
~~~

Không khai báo URL cố định nếu muốn Feign phân giải tên qua LoadBalancer. URL cố định làm client gọi trực tiếp địa chỉ đã cấu hình và bỏ qua bước discovery/load balancing.

OpenFeign và RestClient có mô hình gọi blocking; WebClient có thể chạy reactive. Dù vậy, cần kiểm tra các dependency và cấu hình thực tế của release train vì việc một provider có DiscoveryClient hay ReactiveDiscoveryClient phụ thuộc vào module tích hợp được đưa vào classpath.

## 8. Cấu hình service discovery để thử nghiệm local

Khi chưa kết nối Eureka, Consul hoặc ZooKeeper, Spring Cloud có thể dùng **SimpleDiscoveryClient** nếu không có discovery client gắn với service registry trên classpath. SimpleDiscoveryClient lấy thông tin instance từ application properties.

Ví dụ khai báo hai instance của inventory-service:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://localhost:8081
              - uri: http://localhost:8082
~~~

Ứng dụng gọi request bằng URL logic:

~~~text
http://inventory-service/api/inventory/BOOK-01
~~~

LoadBalancer nhận service ID inventory-service, lấy hai địa chỉ đã khai báo rồi chọn một địa chỉ để gửi request.

SimpleDiscoveryClient hữu ích cho local development, ví dụ minh họa và test tích hợp đơn giản. Danh sách này là cấu hình tĩnh; nó không tự phát hiện một tiến trình vừa khởi động hoặc vừa dừng. Khi thay đổi instance, cần cập nhật cấu hình hoặc dùng service registry có khả năng đăng ký và cập nhật trạng thái động.

SimpleDiscoveryClient là implementation blocking. Cấu hình này phù hợp để thử DiscoveryClient cùng RestClient hoặc OpenFeign. Muốn kiểm thử đường WebClient reactive, cần provider có ReactiveDiscoveryClient hoặc tự cung cấp implementation reactive tương ứng; không nên mặc định rằng cấu hình SimpleDiscoveryClient sẽ tạo ra ReactiveDiscoveryClient.

Lưu ý: spring-cloud-starter-loadbalancer cung cấp cơ chế cân bằng tải. Để đọc registry bên ngoài, ứng dụng còn cần starter hoặc integration tương ứng với registry đang sử dụng. Chỉ thêm LoadBalancer starter không tự tạo ra kết nối đến Eureka, Consul hay ZooKeeper.

## 9. Đăng ký service và khám phá service là hai trách nhiệm khác nhau

**DiscoveryClient** và **ReactiveDiscoveryClient** tập trung vào việc đọc danh sách service và instance. Việc đăng ký hoặc hủy đăng ký instance thuộc abstraction **ServiceRegistry**.

| Abstraction | Trách nhiệm | Ví dụ thao tác |
| --- | --- | --- |
| DiscoveryClient | Đọc thông tin discovery đồng bộ | getInstances(), getServices() |
| ReactiveDiscoveryClient | Đọc thông tin discovery reactive | getInstances(), getServices() |
| ServiceRegistry | Đăng ký hoặc hủy đăng ký instance | register(), deregister() |

Nhiều integration tự đăng ký ứng dụng đang chạy với registry khi khởi động và hủy đăng ký khi dừng. Trong Spring Cloud hiện hành, chỉ cần đưa implementation discovery phù hợp vào classpath để kích hoạt auto-configuration; @EnableDiscoveryClient thường không còn bắt buộc. Nếu muốn tắt tự động đăng ký, có thể cấu hình:

~~~yaml
spring:
  cloud:
    service-registry:
      auto-registration:
        enabled: false
~~~

Việc tắt auto-registration không đồng nghĩa với tắt khả năng đọc discovery. Hai hành vi này thuộc hai trách nhiệm khác nhau và cần được cấu hình theo nhu cầu vận hành.

## 10. Cache danh sách instance

Discovery client có thể truy vấn registry mỗi khi LoadBalancer cần danh sách instance. Để giảm số lần gọi registry, Spring Cloud LoadBalancer cung cấp **CachingServiceInstanceListSupplier** và cache mặc định.

Một cấu hình supplier có cache:

~~~java
return ServiceInstanceListSupplier.builder()
        .withDiscoveryClient()
        .withCaching()
        .build(context);
~~~

Cache giảm chi phí truy vấn nhưng cũng tạo ra độ trễ khi registry vừa cập nhật instance. Nếu một pod vừa bị xóa, danh sách cache có thể vẫn giữ địa chỉ cũ cho đến khi hết TTL hoặc cache bị làm mới.

Các thuộc tính phổ biến:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        enabled: true
        ttl: 35s
        capacity: 256
~~~

Giá trị mặc định của cache LoadBalancer hiện hành là TTL 35 giây và capacity 256. Nếu thêm Caffeine vào classpath, Spring Cloud có thể sử dụng cache dựa trên Caffeine thay cho cache mặc định.

Một số discovery client như Eureka đã có cơ chế cache riêng. Nếu provider đã cache danh sách instance, hãy cân nhắc tắt cache ở LoadBalancer để tránh cache hai tầng làm tăng độ trễ cập nhật. Cấu hình cache cần dựa vào hành vi thực tế của provider, không nên áp dụng một giá trị TTL chung cho mọi môi trường.

## 11. Health indicator của discovery và health check instance

Hai cơ chế này có mục tiêu khác nhau:

- **DiscoveryClientHealthIndicator** kiểm tra khả năng hoạt động của discovery client hoặc registry. Theo mặc định, nó có thể gọi getServices() để lấy danh sách service ID.
- **HealthCheckServiceInstanceListSupplier** kiểm tra các instance cụ thể mà supplier cung cấp, rồi lọc danh sách cho LoadBalancer.

Health indicator của registry báo rằng ứng dụng có thể giao tiếp với hệ thống discovery. Nó không chứng minh mọi instance của inventory-service đều đang xử lý request tốt.

Nếu registry có rất nhiều service, việc gọi getServices() trong mỗi lần health check có thể tốn chi phí. Có thể yêu cầu health indicator dùng probe() thay cho truy vấn danh sách service:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        health-indicator:
          use-services-query: false
~~~

Khi dùng reactive discovery, health indicator reactive có thể sử dụng reactiveProbe().

Với registry thực tế đã cung cấp trạng thái instance khỏe mạnh, thường không cần lặp lại health check định kỳ ở LoadBalancer. HealthCheckServiceInstanceListSupplier hữu ích hơn với SimpleDiscoveryClient hoặc nguồn instance không tự cung cấp trạng thái health.

## 12. Bật hoặc tắt từng đường discovery

Spring Cloud Commons có các thuộc tính để điều khiển service discovery:

| Thuộc tính | Tác dụng |
| --- | --- |
| spring.cloud.discovery.enabled | Bật hoặc tắt service discovery nói chung |
| spring.cloud.discovery.blocking.enabled | Bật hoặc tắt đường DiscoveryClient đồng bộ |
| spring.cloud.discovery.reactive.enabled | Bật hoặc tắt đường ReactiveDiscoveryClient |

Ví dụ chỉ tắt đường reactive:

~~~yaml
spring:
  cloud:
    discovery:
      reactive:
        enabled: false
~~~

Chỉ tắt đường reactive khi ứng dụng không cần reactive discovery. Nếu WebClient đang dựa vào ReactiveDiscoveryClient mà đường này bị tắt hoặc không có implementation tương ứng, LoadBalancer có thể không lấy được danh sách instance theo đường reactive đã cấu hình.

Không nên tắt discovery nói chung nếu các HTTP client vẫn đang gọi URL bằng service ID. Khi tắt discovery, cần có một nguồn instance khác hoặc chuyển sang địa chỉ cố định phù hợp.

## 13. Chẩn đoán lỗi discovery trong luồng cân bằng tải

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| getInstances() trả danh sách rỗng | Service ID sai, instance chưa đăng ký hoặc registry chưa cập nhật | So sánh service ID, trạng thái đăng ký và danh sách service trong registry |
| Không có bean DiscoveryClient | Thiếu starter provider hoặc discovery bị tắt | Kiểm tra dependency và các thuộc tính spring.cloud.discovery |
| WebClient không tìm thấy instance | Không có ReactiveDiscoveryClient hoặc reactive discovery bị tắt | Kiểm tra integration reactive của provider và cấu hình reactive |
| RestClient hoặc Feign không tìm thấy instance | Không có DiscoveryClient blocking hoặc blocking discovery bị tắt | Kiểm tra provider blocking và cấu hình blocking |
| Instance cũ vẫn được chọn sau khi đã dừng | Cache hoặc registry chưa cập nhật | Kiểm tra TTL cache, thời gian heartbeat, deregistration và health state |
| Một số request đến instance khác zone | Metadata zone không đúng hoặc chưa bật zone preference | Kiểm tra metadata và cấu hình LoadBalancer zone |
| Luồng WebFlux bị chậm hoặc nghẽn | Có lời gọi blocking trong reactive pipeline | Tìm các chỗ gọi block() hoặc adapter blocking và thay bằng reactive API phù hợp |
| Health indicator DOWN dù service vẫn trả request | Registry không truy cập được hoặc probe thất bại | Kiểm tra kết nối registry, credential và log discovery client |

Khi chẩn đoán, nên kiểm tra lần lượt từ discovery client đến supplier rồi mới đến thuật toán chọn instance. Nếu getInstances(serviceId) đã trả về danh sách rỗng thì thay Round Robin bằng Random không thể giải quyết vấn đề.

## 14. Thực hành kiểm chứng hai đường discovery

Có thể kiểm tra luồng discovery local mà không cần dựng một service registry đầy đủ:

1. Khai báo hai URI của inventory-service bằng SimpleDiscoveryClient, ví dụ localhost:8081 và localhost:8082.
2. Khởi chạy hai instance, mỗi instance trả về instance ID riêng trong response.
3. Inject DiscoveryClient và gọi getInstances("inventory-service") để quan sát danh sách đồng bộ.
4. Nếu provider hỗ trợ ReactiveDiscoveryClient, inject interface đó và subscribe vào getInstances("inventory-service") để quan sát danh sách reactive. SimpleDiscoveryClient trong ví dụ local là blocking nên không dùng nó để chứng minh đường reactive.
5. Tạo một RestClient được đánh dấu @LoadBalanced và gọi URL dùng service ID.
6. Khi có provider ReactiveDiscoveryClient, tạo một WebClient được đánh dấu @LoadBalanced và gọi endpoint theo kiểu reactive.
7. Gửi nhiều request, ghi lại instance ID để xác nhận LoadBalancer đang chọn từ danh sách discovery.
8. Dừng một instance, quan sát sự khác nhau giữa danh sách registry, danh sách cache và kết quả request.
9. Điều chỉnh TTL cache hoặc tắt cache trong môi trường test để quan sát độ trễ cập nhật.

Kết quả cần xác nhận:

- DiscoveryClient trả về danh sách instance đồng bộ.
- ReactiveDiscoveryClient phát các instance qua Flux khi có subscription.
- ServiceInstanceListSupplier cung cấp danh sách cho LoadBalancer.
- LoadBalancer chọn một instance và HTTP client gọi địa chỉ vật lý của instance đó.
- Khi registry hoặc cache thay đổi, danh sách có thể cập nhật sau một khoảng thời gian phụ thuộc vào provider và cấu hình.

## 15. Những điểm cần nhớ khi vận hành

- DiscoveryClient chỉ đọc thông tin service; ServiceRegistry phụ trách đăng ký và hủy đăng ký.
- ReactiveDiscoveryClient trả dữ liệu theo Reactor; không gọi block() trên event-loop.
- LoadBalancer cần một ServiceInstanceListSupplier để lấy danh sách instance trước khi chọn đích.
- withDiscoveryClient() dùng ReactiveDiscoveryClient; withBlockingDiscoveryClient() dùng DiscoveryClient.
- RestClient và OpenFeign đi theo stack blocking; WebClient có thể dùng đường reactive.
- SimpleDiscoveryClient phù hợp với cấu hình local hoặc test, còn registry bên ngoài phù hợp với danh sách instance thay đổi động.
- Cache giúp giảm tải truy vấn registry nhưng có thể làm chậm thời điểm nhận biết instance mới hoặc instance đã dừng.
- Health indicator kiểm tra discovery client; health-check supplier kiểm tra từng instance.
- Nếu không có instance, cần sửa nguồn discovery hoặc cấu hình supplier trước khi thay đổi thuật toán chọn instance.

## 16. Tài liệu tham khảo

- [Spring Cloud Commons - Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): DiscoveryClient, ReactiveDiscoveryClient, SimpleDiscoveryClient, ServiceRegistry, health indicator và thứ tự discovery client.
- [Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): ServiceInstanceListSupplier, cache, health check, cấu hình supplier và tích hợp RestClient/WebClient.
- [DiscoveryClient source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/client/discovery/DiscoveryClient.java): hợp đồng API đồng bộ.
- [LoadBalancerClientConfiguration source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-loadbalancer/src/main/java/org/springframework/cloud/loadbalancer/annotation/LoadBalancerClientConfiguration.java): điều kiện auto-configuration cho reactive và blocking discovery supplier.
