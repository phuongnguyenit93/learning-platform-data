# Bật tắt discovery, blocking client và reactive client

Bài học thuộc chương **DiscoveryClient** của module **SPRING_CLOUD_CORE**. Spring Cloud Commons cung cấp abstraction để ứng dụng tìm các instance của dịch vụ mà không phụ thuộc trực tiếp vào Eureka, Consul, Zookeeper hoặc một registry cụ thể. Ứng dụng có thể sử dụng API blocking `DiscoveryClient` hoặc API reactive `ReactiveDiscoveryClient`. Spring Cloud cho phép bật/tắt từng loại client hoặc tắt toàn bộ discovery bằng các thuộc tính riêng.

Khi cấu hình, cần phân biệt bốn năng lực thường bị nhầm lẫn:

- **Discovery:** truy vấn danh sách dịch vụ và các instance đang tồn tại.
- **Blocking/reactive client:** hai kiểu API để truy vấn discovery theo mô hình lập trình tương ứng.
- **Auto-registration:** đăng ký chính instance của ứng dụng vào service registry.
- **Load balancing và health indicator:** các thành phần tiêu thụ dữ liệu discovery hoặc quan sát trạng thái discovery, có công tắc cấu hình riêng.

Tắt một năng lực không mặc nhiên tắt các năng lực còn lại. Bài học tập trung vào cách chọn đúng công tắc, kiểm tra bean được tạo và đánh giá tác động đến ứng dụng.

## 1. Kết quả cần đạt

Sau bài học, bạn có thể:

1. Giải thích vai trò của DiscoveryClient trong Spring Cloud Commons.
2. Phân biệt `DiscoveryClient` và `ReactiveDiscoveryClient` qua chữ ký API và cách sử dụng.
3. Bật hoặc tắt blocking discovery client bằng `spring.cloud.discovery.blocking.enabled`.
4. Bật hoặc tắt reactive discovery client bằng `spring.cloud.discovery.reactive.enabled`.
5. Tắt toàn bộ service discovery bằng `spring.cloud.discovery.enabled`.
6. Phân biệt tắt discovery với tắt auto-registration của ứng dụng.
7. Phân biệt công tắc discovery với công tắc Spring Cloud LoadBalancer.
8. Hiểu ảnh hưởng của các công tắc đến bean auto-configuration và các thành phần phụ thuộc.
9. Kiểm tra discovery client, service instance, health indicator và hành vi load balancing.
10. Thiết kế test cho các tổ hợp blocking/reactive và các trường hợp không có registry.

## 2. DiscoveryClient làm nhiệm vụ gì?

Trong hệ thống phân tán, một dịch vụ có thể chạy nhiều instance. Địa chỉ vật lý của mỗi instance thay đổi theo quá trình deploy, scale, restart hoặc thay thế container. Nếu ứng dụng gọi một địa chỉ IP/port cố định, nó phải tự quản lý danh sách endpoint và cập nhật khi topology thay đổi.

Service discovery cung cấp một cách tìm instance theo service ID:

~~~text
service ID: inventory-service
    ├── instance A: http://10.10.1.21:8080
    ├── instance B: http://10.10.1.22:8080
    └── instance C: http://10.10.1.23:8080
~~~

Spring Cloud Commons định nghĩa abstraction để ứng dụng hỏi các thông tin này. Provider cụ thể như Eureka, Consul hoặc Zookeeper thực hiện giao tiếp với registry và chuyển kết quả thành kiểu chung `ServiceInstance`.

~~~mermaid
flowchart TD
    APP["Ứng dụng Spring Boot"] --> API["DiscoveryClient abstraction"]
    APP --> RAPI["ReactiveDiscoveryClient abstraction"]
    API --> PROVIDER["Discovery provider"]
    RAPI --> PROVIDER
    PROVIDER --> REG["Service registry"]
    REG --> INST["Service instances"]
    INST --> PROVIDER
    PROVIDER --> API
    PROVIDER --> RAPI
~~~

Ứng dụng dùng abstraction chung thay vì phụ thuộc trực tiếp API riêng của registry. Nhờ đó, phần lớn logic gọi dịch vụ có thể giữ nguyên khi thay provider, dù cấu hình và hành vi chi tiết vẫn phụ thuộc implementation.

### 2.1. Những thao tác cơ bản

Blocking `DiscoveryClient` cung cấp các thao tác đọc chính:

- `getServices()`: trả danh sách service ID đã biết.
- `getInstances(serviceId)`: trả danh sách instance thuộc service ID.
- `description()`: mô tả implementation.
- `probe()`: kiểm tra client có thể thực hiện truy vấn discovery hay không; mặc định gọi `getServices()`, nhưng implementation có thể cung cấp phép kiểm tra nhẹ hơn.

Ví dụ:

~~~java
import java.util.List;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Service;

@Service
public class InventoryDiscoveryService {

    private final DiscoveryClient discoveryClient;

    public InventoryDiscoveryService(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public List<ServiceInstance> findInventoryInstances() {
        return discoveryClient.getInstances("inventory-service");
    }
}
~~~

Kết quả là danh sách instance tại thời điểm truy vấn. Nếu không tìm thấy service, implementation thường trả danh sách rỗng. Ứng dụng vẫn cần xử lý trường hợp không có instance và lỗi khi truy vấn registry.

### 2.2. ServiceInstance chứa gì?

Một `ServiceInstance` thường cung cấp:

- Service ID.
- Instance ID.
- Host và port.
- URI để gọi instance.
- Trạng thái secure/HTTPS.
- Metadata do provider cung cấp.

Metadata có thể chứa zone, region, namespace, version hoặc thông tin riêng của provider. Không giả định mọi provider có cùng tập metadata hoặc cùng quy tắc chọn instance.

## 3. Blocking DiscoveryClient và ReactiveDiscoveryClient

Spring Cloud Commons có hai API discovery để phù hợp với mô hình lập trình khác nhau.

### 3.1. Blocking API

`DiscoveryClient` trả về collection Java thông thường:

~~~java
List<String> getServices();

List<ServiceInstance> getInstances(String serviceId);
~~~

Ví dụ:

~~~java
List<ServiceInstance> instances =
        discoveryClient.getInstances("inventory-service");

if (instances.isEmpty()) {
    throw new IllegalStateException(
        "No inventory-service instance is available"
    );
}

URI target = instances.get(0).getUri();
~~~

Lệnh gọi trả kết quả trực tiếp. Nếu implementation cần gọi HTTP tới registry hoặc chờ I/O đồng bộ, thread gọi sẽ chờ cho đến khi truy vấn hoàn tất hoặc timeout.

Blocking API phù hợp với ứng dụng MVC hoặc code đang sử dụng mô hình đồng bộ. Không gọi một thao tác blocking kéo dài trực tiếp trên event-loop thread của ứng dụng reactive.

### 3.2. Reactive API

`ReactiveDiscoveryClient` trả dữ liệu dưới dạng Reactor Publisher:

~~~java
Flux<String> getServices();

Flux<ServiceInstance> getInstances(String serviceId);
~~~

Ví dụ:

~~~java
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.ReactiveDiscoveryClient;
import org.springframework.stereotype.Service;

import reactor.core.publisher.Flux;

@Service
public class ReactiveInventoryDiscoveryService {

    private final ReactiveDiscoveryClient discoveryClient;

    public ReactiveInventoryDiscoveryService(
            ReactiveDiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public Flux<ServiceInstance> findInventoryInstances() {
        return discoveryClient.getInstances("inventory-service");
    }
}
~~~

Reactive API phát các kết quả theo kiểu stream. Ứng dụng có thể kết hợp với Reactor operators như `map`, `filter`, `next`, `collectList` hoặc xử lý lỗi bằng `onErrorResume`.

Reactive API phù hợp với WebFlux và các luồng xử lý reactive. Tuy nhiên, kiểu trả về `Flux` không tự chứng minh toàn bộ provider bên dưới không blocking. Cần kiểm tra implementation và cách nó thực hiện I/O; tránh gọi một thư viện đồng bộ trên event loop mà không có cơ chế chuyển scheduler phù hợp.

### 3.3. So sánh

| Tiêu chí | DiscoveryClient | ReactiveDiscoveryClient |
| --- | --- | --- |
| Kiểu trả về | `List` | `Flux` |
| Mô hình gọi | Đồng bộ, caller nhận collection khi hoàn tất. | Reactive, kết quả được phát qua Publisher. |
| Phù hợp | Spring MVC, code imperative. | Spring WebFlux, pipeline Reactor. |
| Xử lý kết quả | Vòng lặp, Stream API, collection operations. | Reactor operators và reactive composition. |
| Tác động khi I/O chậm | Thread gọi có thể phải chờ. | Có thể giữ pipeline non-blocking nếu provider cũng thực hiện I/O non-blocking. |
| Cần kiểm tra | Timeout, thread usage và lỗi truy vấn. | Provider có blocking nội bộ hay không, scheduler và backpressure phù hợp. |

Không nên chọn reactive chỉ vì API trả `Flux`. Hãy chọn theo stack ứng dụng và khả năng thực tế của discovery provider.

### 3.4. Một provider có thể hỗ trợ cả hai API không?

Spring Cloud Commons cho phép các implementation cung cấp blocking và/hoặc reactive client. Tài liệu mô tả cả hai loại được cung cấp theo cấu hình mặc định của Spring Cloud; tuy nhiên bean cụ thể có tồn tại hay không còn phụ thuộc provider, dependency và auto-configuration được kích hoạt.

Nếu ứng dụng chỉ có blocking provider mà không có reactive implementation tương ứng, việc bật reactive discovery không tự biến mọi API đồng bộ của provider thành một implementation reactive thực sự. Hãy kiểm tra bean thực tế và tài liệu của provider đang dùng.

## 4. Các thuộc tính bật/tắt discovery

Spring Cloud Commons cung cấp ba công tắc chính:

| Thuộc tính | Ý nghĩa | Phạm vi |
| --- | --- | --- |
| `spring.cloud.discovery.blocking.enabled` | Bật/tắt blocking discovery client. | API `DiscoveryClient` và các auto-configuration phụ thuộc blocking discovery. |
| `spring.cloud.discovery.reactive.enabled` | Bật/tắt reactive discovery client. | API `ReactiveDiscoveryClient` và các auto-configuration phụ thuộc reactive discovery. |
| `spring.cloud.discovery.enabled` | Bật/tắt toàn bộ service discovery. | Công tắc tổng thể cho discovery. |

Spring Cloud cung cấp cả blocking và reactive discovery client theo mặc định. Bạn có thể tắt riêng từng loại mà không phải tắt loại còn lại. Để tắt hoàn toàn service discovery, dùng công tắc tổng thể `spring.cloud.discovery.enabled=false`.

### 4.1. Giữ cả hai loại client

Nếu ứng dụng có cả code MVC và reactive hoặc các thư viện phụ thuộc cả hai API, giữ mặc định có thể là lựa chọn phù hợp:

~~~yaml
spring:
  cloud:
    discovery:
      enabled: true
      blocking:
        enabled: true
      reactive:
        enabled: true
~~~

Các giá trị `true` được viết tường minh để người đọc thấy chính sách. Trong ứng dụng thông thường, có thể bỏ các thuộc tính khi muốn dùng mặc định của release train.

### 4.2. Chỉ bật blocking client

Nếu ứng dụng chỉ dùng API đồng bộ:

~~~yaml
spring:
  cloud:
    discovery:
      enabled: true
      blocking:
        enabled: true
      reactive:
        enabled: false
~~~

Khi đó, các auto-configuration yêu cầu reactive discovery bị loại theo điều kiện tương ứng. Các bean blocking vẫn có thể được tạo nếu provider có implementation và các điều kiện khác được đáp ứng.

### 4.3. Chỉ bật reactive client

Nếu ứng dụng dùng WebFlux và provider hỗ trợ reactive discovery:

~~~yaml
spring:
  cloud:
    discovery:
      enabled: true
      blocking:
        enabled: false
      reactive:
        enabled: true
~~~

Điều này giới hạn các auto-configuration theo blocking discovery. Kiểm tra các thư viện khác trong ứng dụng có đang inject `DiscoveryClient` hay không; nếu có, chúng có thể không còn bean phù hợp.

### 4.4. Tắt toàn bộ discovery

Nếu một profile chạy local/test không cần service discovery:

~~~yaml
spring:
  cloud:
    discovery:
      enabled: false
~~~

Công tắc tổng thể phù hợp khi ứng dụng không cần truy vấn discovery. Những thành phần phụ thuộc discovery, chẳng hạn service instance supplier của Spring Cloud LoadBalancer, cũng có thể không được cấu hình theo đường discovery tương ứng.

Không dùng công tắc tổng thể nếu mục tiêu chỉ là tắt một health indicator hoặc ngăn ứng dụng tự đăng ký vào registry. Hãy chọn thuộc tính đúng với mục tiêu.

## 5. Discovery khác auto-registration

Một nhầm lẫn phổ biến là nghĩ tắt auto-registration đồng nghĩa tắt DiscoveryClient. Hai việc này độc lập.

- **Discovery:** ứng dụng truy vấn registry để tìm instance của dịch vụ khác.
- **Auto-registration:** ứng dụng đăng ký instance của chính nó vào registry khi khởi động.

Ví dụ, một ứng dụng có thể cần gọi `inventory-service` nhưng không muốn tự đăng ký vào registry. Khi đó, giữ discovery và tắt auto-registration.

### 5.1. Tắt auto-registration bằng property

~~~yaml
spring:
  cloud:
    service-registry:
      auto-registration:
        enabled: false
~~~

Thuộc tính này tắt hành vi tự động đăng ký service của Spring Cloud ServiceRegistry. DiscoveryClient vẫn có thể được dùng để truy vấn các service khác nếu discovery còn bật và provider hỗ trợ.

### 5.2. Tắt auto-registration bằng annotation

`@EnableDiscoveryClient` có thuộc tính `autoRegister`:

~~~java
@Configuration
@EnableDiscoveryClient(autoRegister = false)
public class DiscoveryConfiguration {
}
~~~

Tuy nhiên, với Spring Cloud hiện đại, `@EnableDiscoveryClient` không còn bắt buộc chỉ để kích hoạt discovery khi implementation đã có trên classpath. Property `spring.cloud.service-registry.auto-registration.enabled=false` thường thuận tiện hơn khi cần quản lý qua profile/deployment configuration.

### 5.3. Bảng phân biệt

| Mục tiêu | Thuộc tính/cách làm |
| --- | --- |
| Tắt blocking client | `spring.cloud.discovery.blocking.enabled=false` |
| Tắt reactive client | `spring.cloud.discovery.reactive.enabled=false` |
| Tắt toàn bộ discovery | `spring.cloud.discovery.enabled=false` |
| Chỉ ngăn instance ứng dụng tự đăng ký | `spring.cloud.service-registry.auto-registration.enabled=false` |
| Chỉ tắt health indicator của discovery | `spring.cloud.discovery.client.health-indicator.enabled=false` |
| Tắt composite discovery health indicator | `spring.cloud.discovery.client.composite-indicator.enabled=false` |

Hãy đọc mục tiêu vận hành trước khi chọn property. Một cấu hình sai có thể khiến ứng dụng không tìm được dependency service dù registry vẫn hoạt động bình thường.

## 6. Discovery khác LoadBalancer

Discovery trả danh sách service instance. LoadBalancer chọn một instance trong danh sách đó để gửi request.

~~~mermaid
flowchart LR
    CALLER["Service caller"] --> LB["Spring Cloud LoadBalancer"]
    LB --> SUP["ServiceInstanceListSupplier"]
    SUP --> DISC["DiscoveryClient hoặc ReactiveDiscoveryClient"]
    DISC --> REG["Service registry"]
    REG --> INST["Danh sách ServiceInstance"]
    INST --> SUP
    SUP --> LB
    LB --> TARGET["Một instance được chọn"]
~~~

Hai công tắc có ý nghĩa khác nhau:

- `spring.cloud.discovery.enabled=false` tắt service discovery.
- `spring.cloud.loadbalancer.enabled=false` tắt Spring Cloud LoadBalancer auto-configuration.

Nếu tắt LoadBalancer nhưng vẫn giữ discovery, code tự gọi DiscoveryClient vẫn có thể truy vấn instance. Nếu tắt discovery nhưng LoadBalancer còn bật, phần supplier dựa trên discovery sẽ không thể lấy instance từ DiscoveryClient; ứng dụng cần nguồn instance khác hoặc sẽ không phân giải được service ID.

Blocking/reactive discovery flags cũng ảnh hưởng đến các cấu hình LoadBalancer tương ứng. Ví dụ, blocking LoadBalancer supplier có thể phụ thuộc `DiscoveryClient`; reactive supplier có thể phụ thuộc `ReactiveDiscoveryClient`.

Không nhầm ba công tắc này thành một:

~~~yaml
spring:
  cloud:
    discovery:
      enabled: true
      blocking:
        enabled: true
      reactive:
        enabled: false
    loadbalancer:
      enabled: true
~~~

Cấu hình trên giữ discovery tổng thể, giữ blocking discovery, tắt reactive discovery và vẫn bật LoadBalancer. Đây là một lựa chọn thường gặp trong ứng dụng imperative, nhưng cần kiểm tra dependency graph để bảo đảm không có thành phần cần reactive client.

## 7. Health indicator là lớp quan sát riêng

Spring Cloud Commons có thể tạo health indicator dựa trên discovery client. Health indicator kiểm tra khả năng truy vấn discovery và có thể hiển thị danh sách service trong phần detail.

Các thuộc tính liên quan:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        health-indicator:
          enabled: true
          include-description: false
          use-services-query: true
        composite-indicator:
          enabled: true
~~~

Ý nghĩa:

- `health-indicator.enabled=false`: tắt DiscoveryClientHealthIndicator.
- `health-indicator.include-description=false`: không đưa mô tả implementation vào health result.
- `health-indicator.use-services-query=false`: dùng phép `probe()` thay cho việc lấy toàn bộ danh sách service; có thể giảm chi phí ở registry lớn.
- `composite-indicator.enabled=false`: tắt composite indicator tổng hợp các discovery health indicators.

Nếu chỉ muốn tránh health check gọi `getServices()` trên registry có hàng nghìn service, có thể cân nhắc `use-services-query=false`. Không cần tắt discovery chỉ để giảm tải cho health endpoint.

Health indicator bị tắt không có nghĩa discovery client bị tắt. Tương tự, discovery client có thể hoạt động dù health indicator không được đăng ký.

## 8. @EnableDiscoveryClient có còn cần thiết?

Trong các phiên bản Spring Cloud hiện đại, `@EnableDiscoveryClient` không còn bắt buộc khi implementation DiscoveryClient đã có trên classpath và auto-configuration của provider được kích hoạt.

Ví dụ ứng dụng có starter discovery phù hợp:

~~~java
@SpringBootApplication
public class OrdersApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

Không cần thêm `@EnableDiscoveryClient` chỉ để inject DiscoveryClient trong trường hợp auto-configuration đã cung cấp bean.

Tuy vậy, annotation vẫn có thể hữu ích trong một số cấu hình, đặc biệt khi muốn dùng thuộc tính `autoRegister=false` trực tiếp trên annotation hoặc đang làm việc với phiên bản/integration cũ. Hãy kiểm tra tài liệu đúng release train và provider.

## 9. SimpleDiscoveryClient khi không dùng registry-backed client

Spring Cloud Commons có `SimpleDiscoveryClient`. Nếu không có DiscoveryClient được kết nối với service registry trên classpath, implementation đơn giản này có thể lấy danh sách instance từ cấu hình property.

Ví dụ:

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
            pricing-service:
              - uri: http://localhost:8091
~~~

Một cấu hình dạng indexed properties tương đương:

~~~properties
spring.cloud.discovery.client.simple.instances.inventory-service[0].uri=http://localhost:8081
spring.cloud.discovery.client.simple.instances.inventory-service[1].uri=http://localhost:8082
spring.cloud.discovery.client.simple.instances.pricing-service[0].uri=http://localhost:8091
~~~

SimpleDiscoveryClient hữu ích trong local development, test hoặc ứng dụng nhỏ có danh sách endpoint tĩnh. Nó không tự đăng ký, theo dõi hoặc đồng bộ topology với một registry bên ngoài.

Không nhầm SimpleDiscoveryClient với việc tắt discovery. Nó vẫn là một implementation của abstraction discovery, chỉ khác nguồn dữ liệu.

## 10. Chọn tổ hợp cấu hình theo mục tiêu

| Tình huống | Discovery tổng thể | Blocking | Reactive | Auto-registration |
| --- | --- | --- | --- | --- |
| MVC service dùng registry và tự đăng ký | Bật | Bật | Có thể tắt | Bật |
| WebFlux service với reactive provider | Bật | Có thể tắt | Bật | Theo yêu cầu |
| Ứng dụng chỉ truy vấn service, không tự đăng ký | Bật | Theo API dùng | Theo API dùng | Tắt |
| Local test dùng SimpleDiscoveryClient | Bật | Bật nếu test code imperative | Bật nếu test code reactive | Không áp dụng registry ngoài |
| Ứng dụng không dùng service discovery | Tắt | Không còn ý nghĩa | Không còn ý nghĩa | Cấu hình riêng theo provider nếu cần |
| Chỉ muốn tắt health check discovery | Bật | Theo nhu cầu | Theo nhu cầu | Không đổi |

### 10.1. MVC service

~~~yaml
spring:
  cloud:
    discovery:
      enabled: true
      blocking:
        enabled: true
      reactive:
        enabled: false
    service-registry:
      auto-registration:
        enabled: true
~~~

Ứng dụng có thể inject `DiscoveryClient` và dùng collection API. Nếu có thành phần reactive khác không dùng discovery, tắt reactive discovery giúp giảm các auto-configuration không cần thiết.

### 10.2. WebFlux service

~~~yaml
spring:
  cloud:
    discovery:
      enabled: true
      blocking:
        enabled: false
      reactive:
        enabled: true
    service-registry:
      auto-registration:
        enabled: true
~~~

Chỉ dùng cấu hình này khi provider có reactive DiscoveryClient phù hợp và các dependency của ứng dụng không yêu cầu blocking client. Nếu provider chỉ cung cấp blocking API, hãy đánh giá adapter hoặc integration được hỗ trợ thay vì giả định reactive client tự xuất hiện.

### 10.3. Ứng dụng chạy local không cần registry

~~~yaml
spring:
  cloud:
    discovery:
      enabled: false
~~~

Nếu vẫn cần gọi service khác trong local profile, có thể giữ discovery và dùng SimpleDiscoveryClient với danh sách URI tĩnh. Nếu ứng dụng không gọi service theo ID và không cần registry, tắt toàn bộ discovery sẽ làm cấu hình rõ ràng hơn.

## 11. Kiểm tra bean và hành vi lúc khởi động

Khi đổi property, đừng chỉ nhìn file YAML. Cần kiểm tra ApplicationContext thực sự đã áp dụng property và bean nào được tạo.

### 11.1. Kiểm tra bean bằng ApplicationContext

Ví dụ kiểm tra trong một integration test:

~~~java
@Autowired
ApplicationContext applicationContext;

@Test
void blockingClientIsAvailableWhenEnabled() {
    assertThat(applicationContext.getBeansOfType(DiscoveryClient.class))
        .isNotEmpty();
}
~~~

Test này giả định provider test đã được đưa vào classpath và cấu hình registry phù hợp. Nếu test không có provider, không nên kỳ vọng bean registry-backed xuất hiện.

### 11.2. Kiểm tra reactive client

~~~java
@Autowired
ApplicationContext applicationContext;

@Test
void reactiveClientIsAvailableWhenEnabled() {
    assertThat(
        applicationContext.getBeansOfType(ReactiveDiscoveryClient.class)
    ).isNotEmpty();
}
~~~

Với test tắt reactive discovery, kỳ vọng các bean reactive do auto-configuration quản lý không được tạo. Nếu ứng dụng tự khai báo bean custom, cần phân biệt bean custom với bean do Spring Cloud auto-configuration cung cấp.

### 11.3. Kiểm tra danh sách service và instance

Blocking:

~~~java
List<String> services = discoveryClient.getServices();

List<ServiceInstance> instances =
        discoveryClient.getInstances("inventory-service");
~~~

Reactive:

~~~java
Mono<List<ServiceInstance>> instances =
        reactiveDiscoveryClient.getInstances("inventory-service")
            .collectList();
~~~

Kết quả phụ thuộc registry và thời điểm truy vấn. Test nên kiểm tra service ID/instance do test fixture đăng ký, không dựa vào dữ liệu môi trường dùng chung.

### 11.4. Quan sát endpoint features và health

Spring Cloud Commons có endpoint `/features` để quan sát feature được nhận diện trên classpath và endpoint health để quan sát discovery indicator nếu đã expose. Trong môi trường test/diagnostic, các endpoint này giúp xác minh provider được nhận diện và health indicator đang hoạt động.

Không expose actuator endpoints rộng rãi trong production chỉ để debug discovery. Bảo vệ chúng bằng authentication, authorization và network policy.

## 12. Kiểm thử các tổ hợp bật/tắt

Một test matrix hữu ích:

| ID | discovery.enabled | blocking.enabled | reactive.enabled | Kết quả cần kiểm tra |
| --- | --- | --- | --- | --- |
| D1 | true | true | true | Các API được provider hỗ trợ có thể được đăng ký. |
| D2 | true | true | false | Blocking client còn hoạt động; reactive auto-configuration bị tắt. |
| D3 | true | false | true | Reactive client còn hoạt động; blocking auto-configuration bị tắt. |
| D4 | false | true | true | Công tắc tổng thể tắt discovery; hai cờ con không bật lại discovery. |
| D5 | true | true | true | Health indicator tắt riêng nhưng discovery client vẫn có thể được dùng. |
| D6 | true | true | true | Auto-registration tắt nhưng query discovery vẫn hoạt động. |
| D7 | true | true | false | SimpleDiscoveryClient đọc được instance tĩnh từ properties. |
| D8 | true | true | true | LoadBalancer bật và có thể lấy instance qua API phù hợp. |
| D9 | true | true | true | LoadBalancer tắt nhưng code trực tiếp vẫn có thể gọi DiscoveryClient. |

Nên có cả test khởi động context và test hành vi query. Một bean tồn tại không chứng minh registry đã kết nối thành công; tương tự, health indicator bị tắt không chứng minh provider đã bị loại khỏi context.

## 13. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Không inject được DiscoveryClient | Blocking client bị tắt, provider không có trên classpath hoặc auto-configuration không chạy. | Kiểm tra property, dependency và condition report. |
| Không inject được ReactiveDiscoveryClient | Reactive discovery bị tắt hoặc provider không cung cấp reactive implementation. | Kiểm tra `spring.cloud.discovery.reactive.enabled` và provider support. |
| Tắt blocking nhưng LoadBalancer không tìm được instance | Blocking supplier phụ thuộc DiscoveryClient. | Bật blocking client hoặc chuyển sang reactive supplier tương thích. |
| WebFlux bị chặn khi truy vấn registry | Code dùng blocking DiscoveryClient trên event loop. | Dùng reactive API thực sự non-blocking hoặc chuyển tác vụ blocking sang scheduler phù hợp. |
| Không tìm thấy service dù client bean tồn tại | Registry chưa có service, service ID sai hoặc query thất bại. | Kiểm tra registry, service ID, namespace, network và quyền truy cập. |
| Ứng dụng không đăng ký nhưng vẫn query được service | Auto-registration bị tắt; đây là hai cơ chế độc lập. | Kiểm tra `spring.cloud.service-registry.auto-registration.enabled`. |
| Tắt health indicator nhưng discovery vẫn hoạt động | Chỉ health indicator bị tắt. | Đây là hành vi mong đợi; dùng công tắc discovery nếu muốn tắt query. |
| Tắt LoadBalancer nhưng DiscoveryClient vẫn có bean | LoadBalancer và discovery có công tắc riêng. | Chọn công tắc theo đúng thành phần cần tắt. |
| SimpleDiscoveryClient trả danh sách rỗng | Sai prefix, service ID hoặc index/URI trong properties. | Kiểm tra `spring.cloud.discovery.client.simple.instances`. |
| Cả blocking và reactive client đều tồn tại dù chỉ dùng một API | Một trong các cờ vẫn bật hoặc provider khai báo custom bean. | Kiểm tra property đã bind và nguồn tạo bean. |
| Tắt discovery toàn cục nhưng vẫn có bean custom | Ứng dụng tự khai báo bean ngoài auto-configuration. | Xem bean definition và điều kiện đăng ký custom. |
| Discovery health chuyển DOWN | Registry không truy cập được hoặc probe/query lỗi. | Kiểm tra endpoint registry, timeout, DNS, credentials và network. |

## 14. Nguyên tắc triển khai

1. **Chọn API theo mô hình ứng dụng.** MVC thường dùng blocking; WebFlux nên ưu tiên reactive provider thực sự hỗ trợ non-blocking.
2. **Tắt đúng phạm vi.** Dùng blocking/reactive flags khi muốn loại một API; dùng global flag khi ứng dụng không dùng discovery.
3. **Tách query khỏi registration.** Nếu chỉ không muốn đăng ký instance hiện tại, tắt auto-registration mà vẫn giữ discovery.
4. **Tách discovery khỏi LoadBalancer.** Kiểm tra các thành phần gọi trực tiếp và các thành phần chọn instance.
5. **Tách health khỏi discovery.** Tắt health indicator chỉ thay đổi quan sát, không tắt khả năng query.
6. **Kiểm tra provider.** Một starter registry có thể cung cấp blocking, reactive hoặc cả hai implementation; không suy ra từ tên dependency.
7. **Kiểm tra startup conditions.** Dùng condition report, bean inspection và endpoint diagnostics trong môi trường bảo vệ.
8. **Đặt timeout và xử lý lỗi.** Registry chậm hoặc không sẵn sàng phải được xử lý có kiểm soát.
9. **Không giả định danh sách instance ổn định.** Instance có thể thay đổi giữa hai lần truy vấn; xử lý danh sách rỗng và lỗi kết nối.
10. **Đối chiếu release train.** Các auto-configuration và property condition cần được xác minh theo Spring Cloud version đang dùng.

## 15. Checklist hoàn thành

- [ ] Giải thích được DiscoveryClient trong Spring Cloud Commons.
- [ ] Phân biệt được blocking DiscoveryClient và ReactiveDiscoveryClient.
- [ ] Nêu được kiểu trả về List và Flux của hai API.
- [ ] Biết blocking và reactive discovery có thể bật/tắt độc lập.
- [ ] Cấu hình được `spring.cloud.discovery.blocking.enabled`.
- [ ] Cấu hình được `spring.cloud.discovery.reactive.enabled`.
- [ ] Cấu hình được `spring.cloud.discovery.enabled` để tắt discovery tổng thể.
- [ ] Phân biệt discovery với auto-registration.
- [ ] Biết `spring.cloud.service-registry.auto-registration.enabled`.
- [ ] Biết `@EnableDiscoveryClient` không còn bắt buộc trong Spring Cloud hiện đại khi provider auto-configured.
- [ ] Phân biệt discovery với Spring Cloud LoadBalancer.
- [ ] Phân biệt discovery client với health indicator.
- [ ] Hiểu vai trò và giới hạn của SimpleDiscoveryClient.
- [ ] Kiểm tra bean và hành vi query sau khi đổi property.
- [ ] Có test cho tổ hợp blocking/reactive/global và trường hợp registry không có service.
- [ ] Đối chiếu property và provider theo Spring Cloud release train.

**Tài liệu chính thức cần đối chiếu theo phiên bản dự án:**

- [Spring Cloud Commons – Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): blocking/reactive DiscoveryClient, công tắc bật/tắt, auto-registration, health indicators và SimpleDiscoveryClient.
- [Spring Cloud Commons – Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html): danh sách thuộc tính discovery và các cấu hình liên quan.
- [Spring Cloud Commons – Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): cách LoadBalancer lấy service instances qua discovery.
- [Spring Cloud Commons – DiscoveryClient API](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/client/discovery/DiscoveryClient.java): chữ ký blocking API.
- [Spring Cloud Commons – EnableDiscoveryClient API](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/client/discovery/EnableDiscoveryClient.java): thuộc tính autoRegister.

Hãy kiểm tra Spring Cloud BOM và discovery provider cụ thể của dự án. Các property condition điều khiển auto-configuration, còn khả năng truy vấn thật phụ thuộc provider, registry, network và dữ liệu instance tại thời điểm gọi.
