# Giao tiếp dịch vụ là gì và vì sao cần cân bằng tải

Trong kiến trúc microservices, một nghiệp vụ thường đi qua nhiều dịch vụ. Khi người dùng đặt hàng, dịch vụ Order có thể gọi Inventory để kiểm tra tồn kho, gọi Pricing để tính giá và gọi Payment để xử lý thanh toán. Mỗi dịch vụ có thể chạy nhiều bản sao để tăng năng lực xử lý và duy trì hoạt động khi một máy gặp sự cố.

**Giao tiếp dịch vụ** là cách một dịch vụ trao đổi dữ liệu hoặc yêu cầu xử lý với dịch vụ khác. Các cách phổ biến gồm gọi HTTP/REST, gRPC và gửi thông điệp qua message broker. Cân bằng tải phía client đặc biệt hữu ích với các lời gọi request-response: phía gọi cần tìm một instance đang có thể nhận yêu cầu, chọn instance phù hợp và gửi request đến đó. Bài này tập trung vào HTTP client; gRPC và message broker có cơ chế phân giải tên, định tuyến hoặc phân phối tải riêng.

**Spring Cloud LoadBalancer** cung cấp cơ chế cân bằng tải phía client cho ứng dụng Spring. Nó nhận một service ID, lấy danh sách các **ServiceInstance** tương ứng, áp dụng bộ lọc hoặc chính sách lựa chọn rồi chuyển request đến địa chỉ vật lý của instance được chọn. Nhờ vậy, mã nghiệp vụ có thể gọi **inventory-service** thay vì phải biết trước IP và port của từng bản sao.

## 1. Vấn đề khi giao tiếp trực tiếp với một địa chỉ cố định

Giả sử **order-service** gọi **inventory-service** tại **http://10.0.0.21:8080**. Cách gọi này đơn giản khi chỉ có một máy, nhưng nhanh chóng bộc lộ hạn chế khi hệ thống mở rộng:

- **Giới hạn năng lực:** một instance phải xử lý toàn bộ request, dù có thể chạy thêm nhiều instance khác.
- **Điểm lỗi đơn:** nếu máy hoặc tiến trình đó dừng, mọi request phụ thuộc vào địa chỉ này đều thất bại.
- **Địa chỉ thay đổi:** khi triển khai lại, container hoặc pod có thể nhận IP và port khác. Cấu hình của các dịch vụ gọi đến phải được cập nhật đồng bộ.
- **Triển khai khó linh hoạt:** scale up, scale down, rolling deployment hoặc thay thế máy lỗi đều làm tăng công việc quản lý endpoint.
- **Phân phối tải không đều:** một số instance có thể quá tải trong khi instance khác còn tài nguyên.

Có thể đặt một load balancer ở phía server hoặc gateway để phân phối request. Tuy nhiên, với giao tiếp service-to-service, mỗi ứng dụng gọi dịch vụ cũng có thể tự chọn instance. Đây là cách tiếp cận **client-side load balancing**.

| Cách tiếp cận | Nơi chọn instance | Đặc điểm |
| --- | --- | --- |
| Gọi địa chỉ cố định | Không có bước chọn | Dễ bắt đầu, khó mở rộng và xử lý lỗi |
| Server-side load balancing | Proxy hoặc load balancer ở phía server | Client gọi một endpoint ổn định; proxy chọn backend |
| Client-side load balancing | Ứng dụng gọi dịch vụ | Client lấy danh sách instance và tự chọn đích cho từng request |

Client-side load balancing không thay thế mọi vai trò của API Gateway. Gateway thường xử lý lưu lượng đi vào hệ thống, xác thực, định tuyến theo API và chính sách biên. Spring Cloud LoadBalancer tập trung vào việc chọn instance cho lời gọi từ một ứng dụng Spring đến một service ID.

## 2. Luồng xử lý của Spring Cloud LoadBalancer

Một service ID là tên logic của dịch vụ, ví dụ **inventory-service**. Tại thời điểm gửi request, Spring Cloud LoadBalancer kết hợp với service discovery và HTTP client để tìm một địa chỉ thực tế.

~~~mermaid
flowchart TD
    A["Order Service"] --> B["HTTP client: RestClient / WebClient / OpenFeign"]
    B --> C["Service ID: inventory-service"]
    C --> D["ServiceInstanceListSupplier"]
    D --> E["Lấy danh sách instance từ DiscoveryClient"]
    E --> F["Cache, health check và bộ lọc"]
    F --> G["LoadBalancer chọn một ServiceInstance"]
    G --> H["Gửi request đến host:port đã chọn"]
    H --> I["Inventory Service instance"]
    G --> J["Không có instance phù hợp"]
    J --> K["Lỗi chọn instance được trả về caller"]
~~~

Quy trình thường diễn ra như sau:

1. Mã ứng dụng tạo request đến một URL có host là service ID, chẳng hạn **http://inventory-service/api/stock/ABC**.
2. Interceptor hoặc exchange filter được tích hợp với HTTP client nhận ra request cần cân bằng tải.
3. LoadBalancer yêu cầu **ServiceInstanceListSupplier** cung cấp danh sách instance của **inventory-service**.
4. Supplier lấy dữ liệu từ service discovery, sau đó có thể áp dụng cache, health check, zone preference hoặc bộ lọc khác.
5. LoadBalancer chọn một instance theo chính sách được cấu hình.
6. HTTP client thay service ID bằng địa chỉ thực tế, ví dụ **http://10.0.0.22:8080/api/stock/ABC**, rồi gửi request.
7. Kết quả hoặc lỗi được trả về ứng dụng gọi. Retry và metrics có thể tham gia vào vòng đời request tùy cấu hình.

Hai khái niệm cần phân biệt:

- **Service discovery** trả lời câu hỏi: “Hiện có những instance nào của dịch vụ này và chúng ở đâu?”
- **Load balancing** trả lời câu hỏi: “Trong các instance có thể sử dụng, request này sẽ đi đến instance nào?”

Discovery cung cấp dữ liệu đầu vào; LoadBalancer sử dụng dữ liệu đó để chọn đích. Có discovery chưa chắc đã có cân bằng tải, và một LoadBalancer cũng cần một nguồn cung cấp instance.

## 3. Các thành phần cốt lõi

### 3.1. Service ID và ServiceInstance

Service ID là tên định danh logic mà client dùng trong URL hoặc khai báo client. Nó thường trùng với tên dịch vụ được đăng ký trong registry, nhưng cần được cấu hình nhất quán giữa bên gọi và bên cung cấp.

**ServiceInstance** mô tả một bản triển khai cụ thể của dịch vụ. Thông tin thường có:

- **serviceId:** tên logic của dịch vụ.
- **host** và **port:** địa chỉ vật lý để kết nối.
- **secure:** cho biết instance dùng HTTPS hay không.
- **instanceId:** mã định danh riêng của bản triển khai.
- **metadata:** thông tin bổ sung như zone, phiên bản hoặc nhãn phục vụ định tuyến.

Ví dụ, **inventory-service** có thể có ba instance:

| Service ID | Instance ID | Địa chỉ |
| --- | --- | --- |
| **inventory-service** | **inventory-1** | **10.0.0.21:8080** |
| **inventory-service** | **inventory-2** | **10.0.0.22:8080** |
| **inventory-service** | **inventory-3** | **10.0.0.23:8080** |

Client chỉ cần biết **inventory-service**. Khi một instance được thay thế, registry cập nhật danh sách và client sẽ sử dụng danh sách mới sau khi dữ liệu discovery được làm mới.

### 3.2. DiscoveryClient

Spring Cloud Commons định nghĩa abstraction **DiscoveryClient** và **ReactiveDiscoveryClient**. Các implementation có thể lấy dữ liệu từ Eureka, Consul, Zookeeper hoặc nền tảng discovery khác. Ứng dụng gọi abstraction chung thay vì phụ thuộc trực tiếp vào API riêng của registry.

Trong môi trường production, registry thường nhận thông tin đăng ký khi service khởi động và cập nhật trạng thái khi service dừng hoặc không còn khỏe mạnh. Cơ chế heartbeat, lease, deregistration và thời gian làm mới phụ thuộc vào registry cụ thể.

Nếu classpath không có implementation gắn với service registry, Spring Cloud có thể dùng **SimpleDiscoveryClient**. Đây là lựa chọn hữu ích cho ví dụ local hoặc môi trường test vì danh sách instance được khai báo trong cấu hình.

Ví dụ cấu hình hai instance local:

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

**SimpleDiscoveryClient** không tự quản lý vòng đời tiến trình như một registry production. Khi địa chỉ hoặc số lượng instance thay đổi, người vận hành phải cập nhật cấu hình tương ứng.

### 3.3. ServiceInstanceListSupplier

**ServiceInstanceListSupplier** cung cấp danh sách **ServiceInstance** cho LoadBalancer. Supplier có thể lấy dữ liệu từ discovery client hoặc từ nguồn tùy chỉnh, rồi ghép thêm các bước xử lý.

Một chuỗi supplier có thể gồm:

1. Supplier lấy danh sách từ DiscoveryClient.
2. Supplier cache danh sách để giảm số lần truy vấn discovery.
3. Supplier kiểm tra health hoặc lọc instance theo zone.
4. Supplier lọc theo hint, metadata hoặc yêu cầu của request.

Thứ tự các supplier có ý nghĩa. Chẳng hạn, cache và health-check supplier cần đặt ở vị trí phù hợp so với supplier lấy dữ liệu mạng và các bộ lọc request. Khi tự cấu hình, hãy theo đúng thứ tự trong tài liệu của phiên bản Spring Cloud đang dùng.

Cache giúp giảm chi phí truy vấn registry nhưng cũng tạo ra độ trễ khi instance vừa được thêm hoặc gỡ bỏ. Cần cân nhắc TTL, chu kỳ cập nhật của registry và thời gian phát hiện lỗi để tránh sử dụng danh sách quá cũ.

### 3.4. ReactiveLoadBalancer và thuật toán chọn instance

Spring Cloud LoadBalancer cung cấp abstraction **ReactiveLoadBalancer** cùng các implementation chọn instance. Thuật toán mặc định là **Round Robin**: các request liên tiếp được phân phối lần lượt qua danh sách instance có sẵn.

Ví dụ với ba instance:

| Request | Instance được chọn theo Round Robin |
| --- | --- |
| 1 | **inventory-1** |
| 2 | **inventory-2** |
| 3 | **inventory-3** |
| 4 | **inventory-1** |
| 5 | **inventory-2** |

Spring Cloud cũng cung cấp **RandomLoadBalancer**, chọn ngẫu nhiên một instance trong danh sách. Với cấu hình phù hợp, có thể dùng thêm zone preference, hint hoặc supplier tùy chỉnh để lọc danh sách trước khi chọn.

Round Robin không đo CPU, bộ nhớ, số request đang xử lý hoặc thời gian phản hồi của từng instance. Nếu một instance có năng lực thấp hơn nhiều instance khác, phân phối đều số lượng request chưa chắc tạo ra tải đều. Khi cần định tuyến theo trọng số hoặc dữ liệu vận hành, cần chọn supplier/algorithm phù hợp hoặc xây dựng chính sách riêng.

Có thể cấu hình chính sách riêng cho một service ID bằng **@LoadBalancerClient**. Ví dụ dưới đây thay Round Robin bằng Random cho **inventory-service**:

~~~java
@Configuration(proxyBeanMethods = false)
@LoadBalancerClient(
    name = "inventory-service",
    configuration = InventoryRandomLoadBalancerConfiguration.class
)
class InventoryRandomLoadBalancerRegistration {
}

class InventoryRandomLoadBalancerConfiguration {

    @Bean
    ReactorLoadBalancer<ServiceInstance> randomLoadBalancer(
            Environment environment,
            LoadBalancerClientFactory factory) {

        String serviceId = environment.getProperty(
                LoadBalancerClientFactory.PROPERTY_NAME);

        return new RandomLoadBalancer(
                factory.getLazyProvider(
                        serviceId, ServiceInstanceListSupplier.class),
                serviceId);
    }
}
~~~

Ví dụ minh họa các thành phần chính; cần thêm import tương ứng từ Spring Cloud và Spring Framework. Class cấu hình truyền vào **@LoadBalancerClient** nên nằm ngoài phạm vi component scan hoặc không được đăng ký như cấu hình toàn cục, nếu không bean có thể ảnh hưởng đến nhiều LoadBalancer client ngoài dự kiến.

Một số lựa chọn định tuyến khác:

- **Zone preference:** ưu tiên instance trong cùng zone để giảm độ trễ và lưu lượng liên vùng. Có thể bật cấu hình dựng sẵn bằng **spring.cloud.loadbalancer.configurations: zone-preference**.
- **Hint-based routing:** gửi một hint để lọc instance có metadata tương ứng, ví dụ định tuyến đến nhóm instance phục vụ một phiên bản API.
- **Same-instance preference:** ưu tiên instance đã được chọn trước đó nếu instance vẫn còn khả dụng.
- **Sticky session:** giữ request của một phiên người dùng trên một instance theo định danh phiên. Cách này có giới hạn về loại client và làm giảm tính linh hoạt khi instance gặp lỗi; chỉ dùng khi ứng dụng thực sự cần.

Không nên dùng sticky session để che giấu trạng thái phiên đang lưu cục bộ nếu có thể chuyển trạng thái sang kho dùng chung. Stateless service thường dễ scale và phục hồi hơn.

## 4. Discovery và health check

### 4.1. Discovery không đồng nghĩa với health check tức thời

Một instance xuất hiện trong registry không đảm bảo nó luôn xử lý được request tại thời điểm gọi. Tiến trình có thể bị treo, quá tải, mất kết nối mạng hoặc đang khởi động. Registry cũng có thể cần một khoảng thời gian mới nhận ra instance đã chết.

Có ba lớp tín hiệu thường gặp:

- **Registration:** instance đã đăng ký và có địa chỉ để gọi.
- **Readiness:** instance đã sẵn sàng nhận traffic nghiệp vụ.
- **Liveness:** tiến trình còn sống và không cần khởi động lại.

Không nên dùng liveness thay cho readiness một cách máy móc. Một tiến trình còn sống nhưng chưa kết nối được database hoặc chưa nạp xong dữ liệu có thể chưa nên nhận request nghiệp vụ.

### 4.2. HealthCheckServiceInstanceListSupplier

Spring Cloud LoadBalancer có **HealthCheckServiceInstanceListSupplier** để định kỳ kiểm tra các instance do supplier nền cung cấp. Supplier chỉ trả về instance khỏe mạnh khi có ít nhất một instance vượt qua kiểm tra. Theo hành vi mặc định được tài liệu mô tả, nếu không có instance nào vượt qua, supplier trả lại danh sách instance đã lấy được; vì vậy health check không phải cơ chế bảo đảm rằng mọi request sẽ luôn được gửi đến một instance khỏe.

Ví dụ cấu hình health check cho một client reactive:

~~~java
@Configuration(proxyBeanMethods = false)
@LoadBalancerClient(
    name = "inventory-service",
    configuration = InventoryHealthCheckConfiguration.class
)
class InventoryHealthCheckRegistration {
}

class InventoryHealthCheckConfiguration {

    @Bean
    ServiceInstanceListSupplier inventoryServiceInstanceListSupplier(
            ConfigurableApplicationContext context) {

        return ServiceInstanceListSupplier.builder()
                .withDiscoveryClient()
                .withHealthChecks()
                .build(context);
    }
}
~~~

Với stack blocking, builder có biến thể **withBlockingHealthChecks()**. Hãy chọn biến thể tương ứng với loại client và phiên bản Spring Cloud trong ứng dụng. Ví dụ Random và health check ở hai mục là các cấu hình độc lập; nếu cần dùng đồng thời cho cùng service ID, hãy hợp nhất các bean cần thiết trong một cấu hình client thay vì đăng ký hai cấu hình cạnh tranh.

Có thể cấu hình thời gian và đường dẫn health check:

~~~yaml
spring:
  cloud:
    loadbalancer:
      health-check:
        initial-delay: 5s
        interval: 15s
        path:
          default: /actuator/health/readiness
~~~

Đường dẫn mặc định của health check là **/actuator/health**. Nếu dùng endpoint Actuator mặc định, service đích cần có **spring-boot-starter-actuator** và phải cấu hình endpoint tương ứng. Đường dẫn **/actuator/health/readiness** chỉ dùng được khi ứng dụng đã bật health group readiness phù hợp. Không nên mở endpoint quản trị ra Internet nếu không có kiểm soát truy cập.

Health check theo lịch đặc biệt hữu ích khi dùng **SimpleDiscoveryClient** hoặc nguồn instance không tự cung cấp trạng thái health. Với service registry đã trả về trạng thái instance khỏe mạnh, thường không cần thêm một lớp health check định kỳ trùng lặp. Việc thêm probe có thể làm tăng lưu lượng kiểm tra và tạo thêm áp lực lên các instance.

Health check cũng có chu kỳ phát hiện. Một instance có thể lỗi ngay sau lần probe thành công gần nhất. Vì vậy vẫn cần timeout, retry có giới hạn và xử lý lỗi tại caller.

## 5. Tích hợp với HTTP client trong Spring

### 5.1. Thêm dependency

Thêm starter Spring Cloud LoadBalancer vào ứng dụng:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-loadbalancer</artifactId>
</dependency>
~~~

Nếu dùng OpenFeign, thêm starter OpenFeign:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-openfeign</artifactId>
</dependency>
~~~

Quản lý phiên bản bằng Spring Cloud BOM tương thích với phiên bản Spring Boot của dự án. Không nên tự chọn một phiên bản LoadBalancer độc lập nếu Spring Cloud release train đã quản lý dependency đó.

### 5.2. RestClient

**RestClient** là HTTP client đồng bộ của Spring Framework, được giới thiệu từ Spring Framework 6.1. Tạo một **RestClient.Builder** bean có qualifier **@LoadBalanced** để Spring Cloud thêm tích hợp chọn instance; cần dùng release train Spring Cloud có hỗ trợ RestClient:

~~~java
@Configuration(proxyBeanMethods = false)
class HttpClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }
}
~~~

Inject builder đó vào client nghiệp vụ và gọi bằng service ID:

~~~java
@Service
class InventoryClient {

    private final RestClient restClient;

    InventoryClient(@LoadBalanced RestClient.Builder builder) {
        this.restClient = builder.build();
    }

    InventoryResponse findBySku(String sku) {
        return restClient.get()
                .uri("http://inventory-service/api/inventory/{sku}", sku)
                .retrieve()
                .body(InventoryResponse.class);
    }
}
~~~

Trong URL, **inventory-service** là service ID. LoadBalancer sẽ phân giải nó thành host và port của instance được chọn. Nếu dùng URL cố định như **http://localhost:8081**, request không còn cần chọn instance theo service ID.

### 5.3. WebClient

**WebClient** hỗ trợ lập trình reactive. Tạo builder có **@LoadBalanced**:

~~~java
@Configuration(proxyBeanMethods = false)
class ReactiveHttpClientConfiguration {

    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder() {
        return WebClient.builder();
    }
}
~~~

Sử dụng builder trong service:

~~~java
@Service
class ReactiveInventoryClient {

    private final WebClient webClient;

    ReactiveInventoryClient(@LoadBalanced WebClient.Builder builder) {
        this.webClient = builder.build();
    }

    Mono<InventoryResponse> findBySku(String sku) {
        return webClient.get()
                .uri("http://inventory-service/api/inventory/{sku}", sku)
                .retrieve()
                .bodyToMono(InventoryResponse.class);
    }
}
~~~

Spring Cloud sử dụng load-balancer exchange filter cho **WebClient**. Giữ đúng kiểu reactive xuyên suốt luồng xử lý; tránh gọi **.block()** trong WebFlux request handler vì có thể chiếm event-loop và làm mất lợi ích của mô hình non-blocking.

### 5.4. OpenFeign

OpenFeign cho phép khai báo HTTP client bằng interface:

~~~java
@EnableFeignClients
@SpringBootApplication
class OrderApplication {
}

@FeignClient(name = "inventory-service")
interface InventoryFeignClient {

    @GetMapping("/api/inventory/{sku}")
    InventoryResponse findBySku(@PathVariable String sku);
}
~~~

Khi có Spring Cloud LoadBalancer trên classpath, Feign client có thể dùng service ID trong thuộc tính **name**. Để request được cân bằng tải, không khai báo URL cố định trong **@FeignClient** hoặc cấu hình URL riêng cho client đó. Nếu có URL cố định, Feign sẽ gọi trực tiếp URL và bỏ qua bước load balancing.

Starter OpenFeign xem Spring Cloud LoadBalancer là dependency tùy chọn. Vì vậy, cần thêm **spring-cloud-starter-loadbalancer** rõ ràng khi muốn dùng tích hợp này.

### 5.5. Chọn client nào?

| Client | Mô hình | Tình huống thường dùng |
| --- | --- | --- |
| **RestClient** | Đồng bộ, blocking | Ứng dụng Spring MVC hoặc luồng nghiệp vụ đơn giản |
| **WebClient** | Reactive, non-blocking | WebFlux hoặc xử lý nhiều I/O bất đồng bộ |
| **OpenFeign** | Đồng bộ, khai báo bằng interface | Client nội bộ có contract HTTP rõ ràng và muốn giảm mã gọi HTTP lặp lại |

Có thể dùng nhiều loại client trong cùng hệ thống, nhưng nên chuẩn hóa timeout, retry, tracing và cách xử lý lỗi để hành vi giữa các client nhất quán.

## 6. Timeout và retry

### 6.1. Vì sao phải đặt timeout?

Nếu không có timeout phù hợp, một request có thể chờ quá lâu khi instance đích bị treo hoặc mạng gặp sự cố. Các thread, connection và request đang chờ sẽ tích lũy, làm dịch vụ gọi cũng bị cạn tài nguyên.

Nên phân biệt:

- **Connection timeout:** thời gian tối đa để thiết lập kết nối đến instance.
- **Read/response timeout:** thời gian chờ dữ liệu phản hồi sau khi kết nối được thiết lập.
- **Overall deadline:** giới hạn tổng thời gian cho cả lời gọi, bao gồm các lần thử lại.

Timeout cần phù hợp với SLA của nghiệp vụ. Nếu **order-service** chỉ có 3 giây để hoàn thành một request, không thể đặt timeout 5 giây cho từng lần gọi xuống **inventory-service** rồi kỳ vọng toàn bộ request hoàn tất trong 3 giây.

Ví dụ đặt connect timeout và read timeout cho **RestClient** bằng **SimpleClientHttpRequestFactory**:

~~~java
@Bean
@LoadBalanced
RestClient.Builder loadBalancedRestClientBuilder() {
    SimpleClientHttpRequestFactory factory =
            new SimpleClientHttpRequestFactory();
    factory.setConnectTimeout(Duration.ofSeconds(1));
    factory.setReadTimeout(Duration.ofSeconds(2));

    return RestClient.builder().requestFactory(factory);
}
~~~

Ví dụ cấu hình Reactor Netty cho **WebClient**:

~~~java
@Bean
@LoadBalanced
WebClient.Builder loadBalancedWebClientBuilder() {
    HttpClient httpClient = HttpClient.create()
            .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 1_000)
            .responseTimeout(Duration.ofSeconds(2));

    return WebClient.builder()
            .clientConnector(new ReactorClientHttpConnector(httpClient));
}
~~~

Trong ví dụ này, **responseTimeout** giới hạn thời gian chờ phản hồi ở tầng HTTP client. Nếu cần giới hạn tổng thời gian của cả chuỗi xử lý reactive, có thể đặt thêm **timeout(Duration)** trên publisher của request.

Với OpenFeign, có thể cấu hình timeout theo tên client:

~~~yaml
spring:
  cloud:
    openfeign:
      client:
        config:
          inventory-service:
            connectTimeout: 1000
            readTimeout: 2000
~~~

Các ví dụ trên minh họa cách đặt timeout; HTTP request factory hoặc engine thực tế có thể cần cấu hình thêm connection pool, TLS và giới hạn số kết nối tùy tải.

### 6.2. Retry ở tầng LoadBalancer

Retry cho phép thử lại request khi lần gọi trước thất bại do lỗi tạm thời. Với load-balanced retry, lần thử tiếp theo có thể chọn instance khác để tránh gửi lại request đến cùng một instance đang lỗi.

Ví dụ cấu hình giới hạn số lần thử:

~~~yaml
spring:
  cloud:
    loadbalancer:
      retry:
        enabled: true
        max-retries-on-same-service-instance: 0
        max-retries-on-next-service-instance: 1
        retryable-status-codes:
          - 502
          - 503
          - 504
~~~

Các thuộc tính retry và cách chúng được áp dụng phụ thuộc vào loại HTTP client và phiên bản Spring Cloud:

- Với **WebClient**, Spring Cloud LoadBalancer hỗ trợ retry dựa trên Reactor Retry.
- Với stack blocking, cơ chế retry cần adapter và thư viện retry tương ứng; một số tích hợp dùng Spring Retry.
- Với **OpenFeign**, Spring Cloud OpenFeign mặc định cung cấp **Retryer.NEVER_RETRY**, tức Feign không tự retry. Muốn retry cần cấu hình **Retryer** phù hợp hoặc sử dụng cơ chế retry của tầng khác.

Không nên bật retry rộng cho mọi exception và mọi HTTP method. Một timeout có thể xảy ra sau khi server đã thực hiện xong thao tác nhưng response bị thất lạc. Nếu client gửi lại lệnh tạo đơn hoặc trừ tiền, nghiệp vụ có thể bị thực hiện hai lần. Chỉ retry request an toàn hoặc thiết kế thao tác có idempotency key để server nhận diện yêu cầu lặp.

Một chính sách retry có trách nhiệm cần:

1. Chỉ retry lỗi được xem là tạm thời, ví dụ một số lỗi kết nối hoặc HTTP 502, 503, 504.
2. Giới hạn số lần retry ở cả tầng client và tầng LoadBalancer để tránh nhân số request ngoài dự kiến.
3. Ưu tiên instance khác nếu instance trước vừa thất bại và còn instance khả dụng.
4. Dùng backoff và jitter khi phù hợp để nhiều client không đồng loạt retry cùng thời điểm.
5. Dừng retry khi hết deadline của request gốc.
6. Ghi nhận số lần retry để phát hiện retry storm.

Retry không thay thế circuit breaker. Retry xử lý một số lỗi tạm thời bằng cách thử lại; circuit breaker ngăn caller tiếp tục tạo tải lên dependency đang liên tục thất bại. Hai cơ chế giải quyết vấn đề khác nhau và cần được phối hợp theo ngân sách thời gian của request.

## 7. Quan sát lỗi và hiệu năng

Khi một request thất bại, cần xác định lỗi xảy ra ở bước nào của luồng:

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Không tìm thấy instance hoặc lỗi “No servers available” | Service ID sai, instance chưa đăng ký, registry không truy cập được, supplier lọc hết danh sách | Kiểm tra tên service, trạng thái đăng ký, discovery client, cache, health check và hint |
| Connection refused | Host/port đăng ký sai, tiến trình chưa lắng nghe hoặc network policy chặn kết nối | Kiểm tra địa chỉ instance, port, container network, firewall và trạng thái tiến trình |
| Connect timeout | Đường mạng chậm, route sai, instance không thể truy cập hoặc đang quá tải | Kiểm tra latency mạng, DNS/route, security group và tài nguyên instance |
| Read/response timeout | Instance nhận request nhưng xử lý quá lâu hoặc không trả response | Kiểm tra thời gian xử lý, dependency phía sau, thread pool, connection pool và timeout |
| HTTP 502/503/504 | Instance hoặc proxy trả lỗi gateway/service unavailable/timeout | Đối chiếu log ở caller, proxy và service đích; kiểm tra chính sách retry |
| Một instance nhận tải cao hơn rõ rệt | Round Robin không phản ánh năng lực thực, danh sách hoặc metadata không đồng nhất | Kiểm tra thuật toán, số instance, zone, cache và tải thực tế |

### 7.1. Metrics của Spring Cloud LoadBalancer

Spring Cloud LoadBalancer cung cấp **MicrometerStatsLoadBalancerLifecycle** để ghi nhận thống kê request nếu có **MeterRegistry**. Bật metrics bằng cấu hình:

~~~yaml
spring:
  cloud:
    loadbalancer:
      stats:
        micrometer:
          enabled: true
~~~

Các meter chính gồm:

| Meter | Ý nghĩa |
| --- | --- |
| **loadbalancer.requests.active** | Số request đang hoạt động theo instance |
| **loadbalancer.requests.success** | Thời gian thực thi request kết thúc bằng việc chuyển response cho HTTP client |
| **loadbalancer.requests.failed** | Thời gian thực thi request kết thúc bằng exception |
| **loadbalancer.requests.discard** | Số request không lấy được instance để thực thi |

Kết hợp các meter này với Spring Boot Actuator, Micrometer và hệ thống giám sát như Prometheus để theo dõi xu hướng. Nếu **discard** tăng, hãy kiểm tra discovery, service ID và bộ lọc instance. Nếu **failed** tăng ở một instance cụ thể, cần đối chiếu với log và trace của service đó.

Tag metric có thể chứa service instance và URI. Với endpoint có path chứa ID biến thiên, nên cân nhắc **spring.cloud.loadbalancer.stats.include-path: false** để tránh tạo quá nhiều time series có cardinality cao.

### 7.2. Log và tracing

Metrics cho biết xu hướng; log và distributed tracing giúp tìm nguyên nhân của một request cụ thể. Nên truyền correlation ID hoặc trace context xuyên suốt các lời gọi service-to-service. Khi cần biết request được gửi đến instance nào, có thể ghi lại service ID, instance ID và địa chỉ đích ở tầng client hoặc thông qua request transformer của LoadBalancer.

Không ghi token, mật khẩu, dữ liệu cá nhân hoặc toàn bộ payload nhạy cảm vào log. Chỉ ghi các trường đủ để truy vết như trace ID, service ID, instance ID, HTTP method, route template, status code, thời gian và số lần retry.

## 8. Thực hành kiểm chứng

Một bài thử nhỏ có thể xác nhận cấu hình cân bằng tải trước khi đưa vào môi trường dùng chung:

1. Khởi chạy hai instance của **inventory-service** ở hai port khác nhau, ví dụ 8081 và 8082.
2. Mỗi instance trả về một trường **instanceId** riêng trong response để có thể nhận biết đích xử lý.
3. Cấu hình **SimpleDiscoveryClient** với hai URI và gọi service bằng **http://inventory-service/...** qua RestClient hoặc WebClient.
4. Gửi nhiều request và quan sát instance được chọn. Với Round Robin, request sẽ luân phiên theo danh sách instance mà LoadBalancer nhận được.
5. Dừng một instance, chờ discovery hoặc health check cập nhật danh sách, sau đó gửi request tiếp và quan sát kết quả.
6. Tạo endpoint phản hồi chậm để xác minh connect timeout, read timeout và deadline.
7. Trả về HTTP 503 có kiểm soát để kiểm tra retry, số lần gọi và việc chuyển sang instance khác.
8. Kiểm tra metrics **success**, **failed**, **discard** và đối chiếu log bằng trace ID.

Khi kiểm tra retry, hãy dùng endpoint đọc hoặc endpoint thử nghiệm có idempotency key. Không tạo side effect thật chỉ để kiểm tra một lần retry.

## 9. Những giới hạn cần hiểu rõ

- Cân bằng tải chỉ chọn trong danh sách instance mà supplier cung cấp. Nếu registry hoặc cache giữ dữ liệu cũ, LoadBalancer có thể chọn một instance đã ngừng hoạt động.
- Round Robin phân phối theo lượt, không phải theo CPU, số request đang chạy hoặc độ trễ.
- Health check theo chu kỳ có độ trễ phát hiện và không đảm bảo instance sẽ còn khỏe khi request thực sự đến nơi.
- Retry có thể làm tăng tải đúng lúc hệ thống đang suy giảm. Cần giới hạn số lần thử và tổng thời gian.
- Client-side load balancing không thay thế timeout, circuit breaker, bulkhead, rate limit hoặc khả năng phục hồi của nghiệp vụ.
- Nếu có nhiều client dùng nhiều HTTP stack, hành vi retry và timeout có thể khác nhau. Cần kiểm tra từng adapter và kiểm thử bằng phiên bản Spring Cloud thực tế của dự án.

## 10. Tài liệu tham khảo

- [Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): thuật toán chọn instance, supplier, health check, retry, metrics và cấu hình client riêng.
- [Spring Cloud Commons - Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): DiscoveryClient, SimpleDiscoveryClient, RestClient và WebClient integration.
- [Spring Cloud OpenFeign](https://docs.spring.io/spring-cloud-openfeign/reference/spring-cloud-openfeign.html): tích hợp load balancing, URL của Feign client và retry mặc định.
- [Spring Cloud LoadBalancer configuration properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html): danh sách thuộc tính cấu hình và giá trị mặc định.
