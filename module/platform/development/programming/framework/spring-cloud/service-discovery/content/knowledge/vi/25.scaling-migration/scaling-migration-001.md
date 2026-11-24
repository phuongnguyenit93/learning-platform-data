# Khi nào cần một DiscoveryClient tùy chỉnh

Spring Cloud cung cấp DiscoveryClient như một giao diện chung để ứng dụng tra cứu instance theo service ID. Eureka, Consul và một số hệ thống khác đã có implementation tương ứng. Vì vậy, trước khi viết một DiscoveryClient mới, cần xác định chính xác phần nào của service discovery chưa đáp ứng yêu cầu: nguồn dữ liệu instance, cách đăng ký service, hay cách LoadBalancer chọn instance.

DiscoveryClient tùy chỉnh phù hợp khi ứng dụng cần đọc từ một catalog riêng, một nền tảng nội bộ chưa có adapter Spring Cloud, hoặc một quy tắc ánh xạ service ID và metadata mà các implementation có sẵn không hỗ trợ. Nếu chỉ cần thay đổi chiến lược chọn instance, ServiceInstanceListSupplier của Spring Cloud LoadBalancer thường là điểm mở rộng phù hợp hơn. Nếu cần đăng ký hoặc hủy đăng ký service, cần xem xét ServiceRegistry riêng.

## 1. DiscoveryClient làm nhiệm vụ gì?

DiscoveryClient thuộc Spring Cloud Commons. Nó tách code của consumer khỏi API riêng của Eureka, Consul hoặc provider khác.

Một consumer chỉ cần biết service ID:

    List<ServiceInstance> instances =
            discoveryClient.getInstances("inventory-service");

Ứng dụng không phải biết registry đang lưu dữ liệu ở Eureka, Consul hay catalog riêng. Implementation DiscoveryClient chịu trách nhiệm gọi nguồn dữ liệu, chuyển đổi kết quả thành ServiceInstance và trả về cho consumer.

Luồng cơ bản:

    Consumer
       |
       | getInstances("inventory-service")
       v
    DiscoveryClient
       |
       | tra cứu theo service ID
       v
    Registry / Catalog / Directory
       |
       | danh sách host, port, scheme, metadata
       v
    List<ServiceInstance>
       |
       v
    Spring Cloud LoadBalancer
       |
       v
    Chọn một instance để gọi

DiscoveryClient chỉ là lớp tra cứu. Nó không tự gửi HTTP request tới service đích và không quyết định thuật toán cân bằng tải.

## 2. Hợp đồng của DiscoveryClient

Giao diện blocking DiscoveryClient hiện có các phương thức chính:

    public interface DiscoveryClient extends Ordered {

        String description();

        List<ServiceInstance> getInstances(String serviceId);

        List<String> getServices();

        default void probe() {
            getServices();
        }

        default int getOrder() {
            return 0;
        }
    }

Ý nghĩa:

| Phương thức | Trách nhiệm |
|---|---|
| description() | Trả mô tả dễ đọc về implementation, được dùng trong health indicator |
| getInstances(serviceId) | Trả các instance đã biết của một service ID |
| getServices() | Trả các service ID mà nguồn discovery biết |
| probe() | Kiểm tra implementation còn có thể liên lạc với nguồn dữ liệu |
| getOrder() | Xác định thứ tự của implementation khi có nhiều DiscoveryClient |

DiscoveryClient mở rộng Ordered. Giá trị mặc định của getOrder() là 0. Custom implementation có thể ghi đè để đặt thứ tự phù hợp.

Một số quy tắc cần giữ:

- Không trả null từ getInstances() hoặc getServices(); khi không có dữ liệu, trả danh sách rỗng.
- Giữ service ID nhất quán với cách consumer gọi; chỉ chuẩn hóa chữ hoa/thường nếu quy ước của hệ thống quy định rõ.
- Trả đúng host, port, scheme và metadata để LoadBalancer có thể tạo URI hợp lệ.
- Phân biệt service không có instance với lỗi kết nối tới catalog.
- Không biến lỗi backend thành danh sách rỗng một cách âm thầm; việc đó làm consumer khó phân biệt không có instance với registry đang lỗi.
- Đặt timeout hữu hạn cho truy vấn tới nguồn dữ liệu.

## 3. ServiceInstance là dữ liệu đầu ra chuẩn

Mỗi instance được biểu diễn bằng ServiceInstance. Các thông tin thường cần có:

- instanceId: định danh duy nhất của instance nếu provider có cung cấp.
- serviceId: tên logic của service.
- host: hostname hoặc IP có thể truy cập.
- port: cổng mà consumer sẽ gọi.
- isSecure: kết nối dùng HTTPS hay HTTP.
- uri: URI của instance.
- metadata: các cặp key-value bổ sung.
- scheme: scheme riêng nếu implementation cần cung cấp.

Spring Cloud có DefaultServiceInstance để chuyển dữ liệu từ catalog riêng thành đối tượng chuẩn:

    new DefaultServiceInstance(
        instanceId,
        serviceId,
        host,
        port,
        secure,
        metadata
    );

Không nên đặt thông tin không thể định tuyến vào ServiceInstance. Ví dụ, localhost bên trong container có thể khiến consumer gọi nhầm chính nó. Host và port trả về phải phù hợp với network của consumer.

Metadata nên chứa các thuộc tính nhỏ và ổn định như zone, version, role hoặc protocol. Không đưa secret, token hay dữ liệu nghiệp vụ vào metadata.

## 4. Khi nào nên viết DiscoveryClient tùy chỉnh?

Các tình huống sau thường có lý do kỹ thuật rõ ràng.

### 4.1. Có nguồn catalog riêng chưa có integration

Doanh nghiệp có thể dùng một nền tảng nội bộ để lưu service, instance, địa chỉ, vùng triển khai và trạng thái. Nếu không có Spring Cloud DiscoveryClient adapter cho nền tảng đó, custom implementation có thể gọi REST API, SDK hoặc database view của catalog và chuyển kết quả sang ServiceInstance.

Ví dụ nguồn dữ liệu:

- Internal service directory.
- Control plane của nền tảng triển khai.
- Catalog đa vùng hoặc đa tài khoản.
- Hệ thống service mapping được quản lý tập trung.
- Một API discovery do tổ chức tự phát triển.

Trường hợp này phù hợp nhất khi catalog là nguồn dữ liệu chính thức và có hợp đồng API ổn định.

### 4.2. Cần ánh xạ service ID hoặc metadata theo quy ước riêng

Một nền tảng có thể đặt tên service theo namespace, tenant, region hoặc phiên bản. Custom DiscoveryClient có thể chuyển tên logic của ứng dụng thành khóa tra cứu của catalog, sau đó ánh xạ kết quả về service ID chuẩn.

Ví dụ consumer gọi:

    inventory-service

Catalog nội bộ lưu:

    prod/asia-southeast1/commerce/inventory

Adapter có thể thực hiện ánh xạ giữa hai tên này. Cần bảo đảm quy tắc ánh xạ rõ ràng, có kiểm thử và không tạo ra hai instance trùng nhau khi dữ liệu đến từ nhiều nguồn.

Nếu việc lọc chỉ dựa trên metadata đã có sẵn trong ServiceInstance, có thể xử lý ở LoadBalancer thay vì thay đổi DiscoveryClient.

### 4.3. Cần tích hợp một giao thức hoặc API đặc thù

Nếu catalog sử dụng giao thức riêng, chữ ký request, xác thực workload hoặc định dạng phản hồi không tương thích trực tiếp với Eureka/Consul, custom client có thể đóng vai trò adapter.

Adapter nên cô lập chi tiết giao thức trong một gateway/service riêng. DiscoveryClient chỉ chịu trách nhiệm chuyển đổi kết quả catalog sang mô hình Spring Cloud.

Không để logic ký request, retry, phân tích JSON hoặc quản lý token rải rác trong các consumer.

### 4.4. Cần hợp nhất dữ liệu từ nhiều nguồn theo quy tắc riêng

Một hệ thống có thể đang chuyển từ Eureka sang Consul, hoặc có registry khác nhau theo vùng. Nếu yêu cầu hợp nhất, loại trùng, ưu tiên nguồn hoặc chuẩn hóa metadata phức tạp hơn khả năng cấu hình hiện có, một lớp adapter riêng có thể hữu ích.

Tuy nhiên, trước tiên hãy kiểm tra CompositeDiscoveryClient và khả năng ordering của Spring Cloud. Nếu chỉ cần nhiều implementation cùng tồn tại, không cần viết thêm một client tổng hợp.

Khi hợp nhất nhiều nguồn, phải xác định rõ:

- Quy tắc ưu tiên nếu cùng một instance xuất hiện ở hai nguồn.
- Cách nhận diện bản ghi trùng.
- Nguồn nào là source of truth khi metadata khác nhau.
- Cách xử lý khi một nguồn lỗi nhưng nguồn còn lại vẫn hoạt động.
- Cách tránh trả đồng thời endpoint cũ và endpoint mới trong giai đoạn migration.

## 5. Khi nào không cần DiscoveryClient tùy chỉnh?

| Nhu cầu | Hướng xử lý phù hợp |
|---|---|
| Dùng Eureka | Thêm Spring Cloud Netflix Eureka Client và cấu hình server |
| Dùng Consul | Thêm Spring Cloud Consul Discovery và cấu hình agent/catalog |
| Danh sách endpoint cố định, ít thay đổi | Dùng SimpleDiscoveryClient |
| Chỉ muốn round-robin, weighted hoặc zone preference | Cấu hình Spring Cloud LoadBalancer |
| Chỉ muốn lọc instance theo metadata | Dùng ServiceInstanceListSupplier hoặc LoadBalancer configuration |
| Chỉ cần đăng ký/hủy đăng ký service | Xem ServiceRegistry và Registration |
| Muốn nhiều DiscoveryClient cùng tồn tại | Xem CompositeDiscoveryClient và ordering |
| Chỉ muốn thay endpoint theo profile | Dùng Spring Boot Profiles và cấu hình tương ứng |

SimpleDiscoveryClient được dùng khi không có Service-Registry-backed DiscoveryClient phù hợp trên classpath. Danh sách instance được khai báo bằng properties:

    spring:
      cloud:
        discovery:
          client:
            simple:
              instances:
                inventory-service:
                  - uri: http://inventory-a:8080
                  - uri: http://inventory-b:8080

Nếu danh sách endpoint đã biết trước và ít thay đổi, cách này thường đơn giản hơn việc xây dựng adapter riêng.

## 6. Phân biệt DiscoveryClient, ServiceRegistry và LoadBalancer

Ba abstraction giải quyết ba vấn đề khác nhau:

| Abstraction | Câu hỏi | API hoặc điểm mở rộng |
|---|---|---|
| DiscoveryClient | Có những instance nào của service? | getInstances(), getServices() |
| ServiceRegistry | Đăng ký, cập nhật hoặc hủy đăng ký instance bằng cách nào? | register(), deregister(), status |
| ServiceInstanceListSupplier / LoadBalancer | Chọn instance nào cho request hiện tại? | Supplier và ReactorLoadBalancer |

DiscoveryClient là giao diện đọc. Việc triển khai DiscoveryClient không tự động cung cấp khả năng đăng ký instance của ứng dụng vào catalog.

Spring Cloud Commons cung cấp ServiceRegistry và Registration cho phía đăng ký. Nếu custom platform cần cả đọc lẫn ghi, hãy thiết kế hai trách nhiệm riêng và bảo đảm vòng đời register/deregister được quản lý đúng.

Nếu chỉ cần thay đổi cách LoadBalancer chọn instance, hãy bắt đầu với ServiceInstanceListSupplier. Không nên đưa chính sách round-robin, sticky session hoặc retry vào DiscoveryClient vì chúng thuộc lớp chọn instance và gọi service.

## 7. Thiết kế kiến trúc của custom DiscoveryClient

Nên tách implementation thành ba phần:

    Consumer / LoadBalancer
             |
             v
    Custom DiscoveryClient
             |
             v
    Directory Gateway
             |
             | HTTP / SDK / database
             v
    Internal Service Catalog

**Custom DiscoveryClient** thực hiện hợp đồng Spring Cloud, kiểm tra đầu vào và chuyển đổi dữ liệu.

**Directory Gateway** gọi API hoặc SDK của catalog. Thành phần này chịu trách nhiệm timeout, xác thực, retry và chuyển lỗi kỹ thuật thành exception có ý nghĩa.

**Internal Service Catalog** là nguồn dữ liệu chính thức, quản lý instance và metadata.

Cách chia này giúp unit test DiscoveryClient mà không cần khởi động catalog thật. Gateway cũng có thể được thay thế bằng implementation giả trong integration test.

## 8. Ví dụ triển khai DiscoveryClient blocking

Giả sử tổ chức có DirectoryGateway để truy vấn catalog nội bộ:

    public interface DirectoryGateway {

        List<DirectoryInstance> findInstances(String serviceId);

        List<String> listServiceIds();

        void ping();
    }

    public record DirectoryInstance(
            String instanceId,
            String host,
            int port,
            boolean secure,
            Map<String, String> metadata
    ) {
    }

Implementation:

    import java.util.List;
    import java.util.Map;

    import org.springframework.cloud.client.DefaultServiceInstance;
    import org.springframework.cloud.client.ServiceInstance;
    import org.springframework.cloud.client.discovery.DiscoveryClient;
    import org.springframework.stereotype.Component;
    import org.springframework.util.StringUtils;

    @Component
    public class DirectoryDiscoveryClient implements DiscoveryClient {

        private final DirectoryGateway gateway;

        public DirectoryDiscoveryClient(DirectoryGateway gateway) {
            this.gateway = gateway;
        }

        @Override
        public String description() {
            return "Internal Directory Discovery Client";
        }

        @Override
        public List<ServiceInstance> getInstances(String serviceId) {
            if (!StringUtils.hasText(serviceId)) {
                return List.of();
            }

            return gateway.findInstances(serviceId)
                    .stream()
                    .<ServiceInstance>map(instance -> new DefaultServiceInstance(
                            instance.instanceId(),
                            serviceId,
                            instance.host(),
                            instance.port(),
                            instance.secure(),
                            instance.metadata() == null
                                    ? Map.of()
                                    : Map.copyOf(instance.metadata())
                    ))
                    .toList();
        }

        @Override
        public List<String> getServices() {
            return gateway.listServiceIds()
                    .stream()
                    .distinct()
                    .sorted()
                    .toList();
        }

        @Override
        public void probe() {
            gateway.ping();
        }

        @Override
        public int getOrder() {
            return 20;
        }
    }

Ví dụ dùng Java 17 trở lên. DirectoryGateway là abstraction của ứng dụng; cần có implementation gọi catalog thật và cấu hình timeout phù hợp.

Một số quyết định trong ví dụ:

- Service ID rỗng trả danh sách rỗng vì không có khóa tra cứu hợp lệ.
- Instance được chuyển thành DefaultServiceInstance.
- Metadata null được chuyển thành map rỗng.
- getServices() loại service ID trùng và sắp xếp để kết quả ổn định.
- probe() gọi một thao tác nhẹ thay vì tải toàn bộ danh sách service.
- getOrder() trả 20 để khai báo thứ tự của implementation khi cùng tồn tại với client khác.

Trong ứng dụng thực tế, cần kiểm tra host và port có hợp lệ, instance có được đánh dấu healthy hay không, metadata có đúng schema và URI có thể truy cập từ consumer hay không. Nếu catalog trả lỗi, gateway nên ném exception phù hợp để hệ thống quan sát được lỗi kết nối.

## 9. Cách đưa implementation vào Spring context

Với ứng dụng đơn lẻ, có thể khai báo implementation bằng @Component như ví dụ trên hoặc tạo bean trong một @Configuration class. Component scan phải bao phủ package chứa implementation.

Với một thư viện hoặc starter dùng lại cho nhiều ứng dụng, nên đóng gói auto-configuration:

    @AutoConfiguration
    @ConditionalOnClass(DiscoveryClient.class)
    @ConditionalOnProperty(
        prefix = "acme.discovery",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
    )
    public class AcmeDiscoveryAutoConfiguration {

        @Bean
        @ConditionalOnMissingBean(DirectoryDiscoveryClient.class)
        DirectoryDiscoveryClient acmeDiscoveryClient(DirectoryGateway gateway) {
            return new DirectoryDiscoveryClient(gateway);
        }
    }

Đăng ký auto-configuration class trong file:

    META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports

Nội dung file:

    com.example.discovery.AcmeDiscoveryAutoConfiguration

Tên package và class trong ví dụ cần thay bằng tên thực tế của thư viện.

Hai cách đăng ký bean là hai lựa chọn thay thế nhau. Nếu dùng @Component ở ví dụ blocking, hãy để component scan tạo bean và không khai báo lại bean đó trong auto-configuration. Nếu đóng gói starter, có thể bỏ @Component và để auto-configuration tạo bean. Điều kiện @ConditionalOnMissingBean(DirectoryDiscoveryClient.class) chỉ ngăn tạo trùng custom implementation này; nó vẫn cho phép EurekaDiscoveryClient hoặc ConsulDiscoveryClient cùng tồn tại.

Điều kiện bean được dùng theo kiểu custom implementation để tránh tạo hai bean cùng loại. Không dùng @ConditionalOnMissingBean(DiscoveryClient.class) một cách máy móc nếu mục tiêu là cho phép custom client cùng tồn tại với Eureka hoặc Consul. Spring Cloud có thể kết hợp nhiều DiscoveryClient; việc tạo bean duy nhất có thể làm mất khả năng phối hợp.

Trong hệ sinh thái Spring Cloud, cơ chế tích hợp mở rộng qua @EnableDiscoveryClient cũng có metadata trong META-INF/spring.factories với key org.springframework.cloud.client.discovery.EnableDiscoveryClient. Đây là cơ chế đăng ký cấu hình discovery của Spring Cloud; còn AutoConfiguration.imports là cơ chế Spring Boot 3 tìm auto-configuration. Khi phát hành starter, cần theo đúng integration path và phiên bản Spring Boot/Spring Cloud mà thư viện hỗ trợ.

@EnableDiscoveryClient không còn bắt buộc trong ứng dụng Spring Boot thông thường nếu implementation discovery đã có trên classpath và được cấu hình phù hợp.

## 10. Xử lý nhiều DiscoveryClient và thứ tự ưu tiên

Một ứng dụng có thể có nhiều implementation, chẳng hạn Eureka và một catalog nội bộ. DiscoveryClient mở rộng Ordered để khai báo thứ tự.

Ví dụ:

    @Override
    public int getOrder() {
        return 20;
    }

Có thể cấu hình order của các implementation Spring Cloud có sẵn bằng thuộc tính riêng của provider, chẳng hạn eureka.client.order hoặc spring.cloud.consul.discovery.order.

Theo quy ước của Spring Ordered, giá trị order nhỏ hơn có độ ưu tiên cao hơn. Hãy chọn giá trị có chủ đích và kiểm tra thứ tự client thực tế trong application context, đặc biệt khi nhiều provider cùng được bật.

Khi có nhiều nguồn, cần xác định rõ ý nghĩa của thứ tự:

- Nguồn nào được ưu tiên trong quá trình tra cứu.
- Có fallback sang nguồn tiếp theo khi nguồn đầu không có instance hay không.
- Có gộp instance từ nhiều nguồn hay không.
- Lỗi truy vấn một nguồn có làm hỏng toàn bộ kết quả không.
- Instance trùng ID được xử lý thế nào.

Không nên chỉ thay đổi số order rồi giả định dữ liệu sẽ được hợp nhất đúng. Hãy viết integration test với hai nguồn có dữ liệu trùng, dữ liệu riêng và tình huống một nguồn lỗi.

Với reactive composite discovery client, hành vi được Spring Cloud mô tả rõ hơn:

- Mặc định, instance được lấy từ client nhanh nhất trả về danh sách không rỗng.
- spring.cloud.discovery.reactive.order-enforced=true yêu cầu thử theo thứ tự; client ưu tiên thấp chỉ được truy vấn khi client trước không có instance.
- Trong chế độ order-enforced, client ưu tiên cao phản hồi chậm có thể làm chậm kết quả và lỗi có thể được truyền ra thay vì fallback.
- spring.cloud.discovery.reactive.combine-instances=true cho phép gộp instance từ các reactive client; lỗi của một client được ghi log mà không ngăn kết quả từ client khác.
- Nếu bật cả combine-instances và order-enforced, các client được truy vấn theo thứ tự cấu hình.

Các thuộc tính này áp dụng cho reactive composite; không suy diễn cùng một hành vi cho blocking composite nếu chưa kiểm tra phiên bản đang dùng.

## 11. Có cần triển khai ReactiveDiscoveryClient không?

Spring Cloud có hai hợp đồng discovery:

- DiscoveryClient: API blocking, trả List.
- ReactiveDiscoveryClient: API reactive, trả Flux và dùng reactive probe.

Nếu ứng dụng dùng WebFlux hoặc cần tra cứu hoàn toàn non-blocking, hãy xem xét ReactiveDiscoveryClient. Giao diện reactive có các thao tác tương đương như getInstances(serviceId), getServices() và reactiveProbe().

Một adapter reactive nên sử dụng HTTP client hoặc SDK có API reactive. Không gọi một SDK blocking trực tiếp trên Reactor event loop.

Nếu chỉ có SDK blocking, có thể cô lập thao tác blocking trên scheduler phù hợp như boundedElastic, nhưng cần timeout và giới hạn concurrency. Đây là giải pháp chuyển tiếp; với tải cao, adapter reactive thực sự thường dễ kiểm soát hơn.

Không bắt buộc phải triển khai cả blocking và reactive client nếu ứng dụng chỉ dùng một mô hình. Nếu cung cấp cả hai, bảo đảm chúng trả cùng service ID, địa chỉ, metadata và quy tắc health.

## 12. Tích hợp với Spring Cloud LoadBalancer

Sau khi DiscoveryClient trả về ServiceInstance, Spring Cloud LoadBalancer có thể dùng danh sách đó để chọn instance cho request.

Ví dụ với RestTemplate:

    @Configuration
    public class ClientConfiguration {

        @Bean
        @LoadBalanced
        RestTemplate restTemplate() {
            return new RestTemplate();
        }
    }

Gọi service bằng service ID:

    restTemplate.getForObject(
            "http://inventory-service/api/items/42",
            Item.class
    );

LoadBalancer sử dụng DiscoveryClient để lấy danh sách instance và áp dụng thuật toán chọn instance. Nếu custom client trả sai host, port hoặc scheme, request sẽ thất bại dù truy vấn catalog thành công.

Nếu yêu cầu chỉ là lọc theo zone, version, metadata, weight, sticky session hoặc health check bổ sung, hãy kiểm tra ServiceInstanceListSupplier. Đây là lớp chuyên xử lý danh sách instance trước khi LoadBalancer chọn một instance.

Ví dụ, lọc instance theo metadata version có thể được thực hiện ở supplier. DiscoveryClient vẫn trả về danh sách đầy đủ và đúng với catalog; policy chọn instance được giữ ở tầng LoadBalancer.

## 13. Hiệu năng, timeout và cache

DiscoveryClient có thể được gọi thường xuyên trong quá trình LoadBalancer làm mới danh sách instance. Vì vậy, không nên để mỗi lần getInstances() tạo một truy vấn không giới hạn tới catalog.

Một số nguyên tắc:

- Đặt connect timeout và response timeout hữu hạn cho DirectoryGateway.
- Giới hạn số request đồng thời tới catalog.
- Dùng cache có TTL nếu nguồn dữ liệu chậm và topology không đổi theo từng request.
- Có chính sách refresh/invalidation khi registration thay đổi.
- Không cache lỗi vô thời hạn hoặc biến lỗi backend thành kết quả rỗng.
- Dùng retry có backoff và jitter; tránh retry dồn dập khi catalog đang lỗi.
- Theo dõi cache age và propagation delay để biết consumer đang dùng dữ liệu cũ bao lâu.
- Phân trang hoặc lọc ở phía catalog nếu getServices() có thể trả về danh sách rất lớn.
- Không tải toàn bộ registry chỉ để kiểm tra một service nếu provider có API probe nhẹ.

DiscoveryClient mặc định có phương thức probe() gọi getServices(). Ở hệ thống có rất nhiều service, việc tải toàn bộ danh sách chỉ để health check có thể tốn tài nguyên. Custom client nên ghi đè probe() để kiểm tra kết nối nhẹ nếu backend hỗ trợ.

Có thể cấu hình health indicator không gọi getServices() mà sử dụng probe():

    spring:
      cloud:
        discovery:
          client:
            health-indicator:
              use-services-query: false

Khi đó DiscoveryClientHealthIndicator dùng probe() để kiểm tra khả năng liên lạc. Health indicator không nên biến thành một truy vấn toàn registry chạy quá thường xuyên.

## 14. Bảo mật nguồn catalog

Custom client thường gọi một API hoặc SDK nội bộ, vì vậy cần xử lý bảo mật ở lớp gateway:

- Dùng TLS và xác minh certificate.
- Cấp credentials theo workload identity hoặc secret manager.
- Giới hạn quyền đọc catalog theo namespace hoặc service group.
- Không log access token, password hoặc URL có credentials.
- Giới hạn metadata được trả về consumer.
- Kiểm tra quyền truy cập khi có nhiều tenant hoặc nhiều vùng.
- Dùng timeout và giới hạn response size để tránh response bất thường tiêu tốn bộ nhớ.
- Không tin tưởng host, port hoặc URI do nguồn dữ liệu không xác thực trả về.

DiscoveryClient.getInstances(serviceId) không nhận một đối tượng request context tùy ý. Nếu catalog cần tenant context hoặc quyền theo người dùng, hãy thiết kế rõ cách truyền context trong ứng dụng. Không dựa vào ThreadLocal khi gọi reactive hoặc xử lý bất đồng bộ vì context có thể không đi theo thread như dự kiến.

Nếu quyền truy cập khác nhau theo người gọi, cần cân nhắc liệu DiscoveryClient chung có phải abstraction phù hợp hay consumer cần một API rõ ràng hơn có request context.

## 15. Kiểm thử custom DiscoveryClient

Nên chia kiểm thử thành nhiều lớp.

**Unit test cho ánh xạ dữ liệu**

- Service ID hợp lệ trả đúng instance.
- Service không tồn tại trả danh sách rỗng.
- Metadata được giữ nguyên.
- HTTPS được ánh xạ thành secure=true.
- Host và port được ánh xạ đúng.
- Instance ID không bị trùng hoặc bị mất.
- getServices() không trả phần tử trùng.
- probe() gọi thao tác nhẹ của gateway.

Ví dụ:

    @Test
    void mapsDirectoryInstanceToServiceInstance() {
        DirectoryInstance record = new DirectoryInstance(
                "inventory-1",
                "inventory.internal",
                8443,
                true,
                Map.of("zone", "zone-a")
        );

        when(gateway.findInstances("inventory-service"))
                .thenReturn(List.of(record));

        List<ServiceInstance> instances =
                discoveryClient.getInstances("inventory-service");

        assertThat(instances).hasSize(1);
        assertThat(instances.get(0).getServiceId())
                .isEqualTo("inventory-service");
        assertThat(instances.get(0).getUri().toString())
                .isEqualTo("https://inventory.internal:8443");
        assertThat(instances.get(0).getMetadata())
                .containsEntry("zone", "zone-a");
    }

Ví dụ dùng JUnit, Mockito và AssertJ; cần tạo mock gateway và khởi tạo discoveryClient trong test setup.

**Integration test**

- Kiểm tra bean được tạo đúng trong Spring ApplicationContext.
- Kiểm tra custom client có trong CompositeDiscoveryClient.
- Kiểm tra thứ tự khi cùng có Eureka hoặc Consul.
- Kiểm tra LoadBalancer chọn được instance.
- Kiểm tra backend timeout, authentication failure và response lỗi.
- Kiểm tra cache refresh khi instance đăng ký hoặc hủy đăng ký.

**Contract test**

Nếu catalog có API riêng, viết test để xác nhận schema, metadata, service ID, trạng thái health và địa chỉ công bố. Khi provider thay đổi API, contract test giúp phát hiện lỗi trước khi đưa vào production.

## 16. Di chuyển từ Eureka/Consul sang catalog riêng

Custom DiscoveryClient có thể hỗ trợ migration từng bước mà không phải sửa mọi consumer cùng lúc.

Một quy trình tham khảo:

1. Xác định contract hiện tại: service ID, instance ID, host, port, scheme, metadata và trạng thái.
2. Viết adapter đọc catalog mới và chuyển kết quả sang ServiceInstance.
3. Chạy adapter trong môi trường test cùng với implementation cũ.
4. So sánh kết quả discovery của hai nguồn theo từng service.
5. Kiểm tra bản ghi trùng, endpoint không thể định tuyến và metadata thiếu.
6. Kiểm tra LoadBalancer, health check, cache và hành vi khi catalog mới lỗi.
7. Chuyển một nhóm consumer hoặc một profile sang nguồn mới.
8. Theo dõi lookup latency, lỗi gọi service và propagation delay.
9. Mở rộng cutover theo từng nhóm.
10. Giữ đường rollback rõ ràng cho tới khi dữ liệu và registration ổn định.

Nếu cần đọc song song từ nhiều registry, dùng CompositeDiscoveryClient khi hành vi của nó đáp ứng yêu cầu. Nếu cần dual-write registration, hãy xử lý riêng ở ServiceRegistry/lifecycle. Không giả định rằng thêm một DiscoveryClient sẽ tự động đăng ký instance vào cả hai registry.

Trong giai đoạn migration, cần xác định nguồn nào là source of truth cho từng service. Nếu cả hai registry cùng trả một instance nhưng địa chỉ khác nhau, consumer có thể gọi endpoint cũ hoặc nhận bản ghi trùng.

## 17. Lỗi thường gặp khi tự triển khai

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Consumer không thấy custom client | Bean chưa được component scan hoặc auto-configuration chưa được nạp | Kiểm tra package, bean condition và AutoConfiguration.imports |
| Có hai DiscoveryClient cùng trả instance trùng | Eureka/Consul và custom client cùng được composite sử dụng | Đặt quy tắc nguồn, deduplicate hoặc chỉ bật provider theo profile |
| getInstances() trả danh sách rỗng dù catalog có dữ liệu | Sai service ID, namespace hoặc filter | Kiểm tra ánh xạ ID và truy vấn trực tiếp catalog |
| Consumer gọi sai host hoặc port | Ánh xạ ServiceInstance không đúng | Kiểm tra host, port, scheme và network từ consumer |
| Health indicator chậm | probe mặc định tải toàn bộ getServices() | Override probe() nhẹ và dùng use-services-query=false |
| WebFlux bị block | Gọi SDK blocking trên event loop | Dùng reactive client hoặc cô lập blocking bằng scheduler |
| Lỗi catalog bị hiểu thành không có instance | Exception bị bắt rồi trả List.of() | Phân biệt empty result với backend failure |
| LoadBalancer vẫn chọn instance cũ | Cache hoặc refresh chưa cập nhật | Kiểm tra ServiceInstanceListSupplier và cache TTL |
| Auto-configuration tạo client hai lần | Cấu hình đăng ký bean trùng | Kiểm tra điều kiện bean và tên bean |
| Chỉ đọc được instance nhưng không đăng ký được local service | Chỉ triển khai DiscoveryClient | Bổ sung ServiceRegistry/Registration nếu cần write-side lifecycle |

## 18. Quy trình quyết định trước khi viết

Trước khi tạo class mới, hãy trả lời các câu hỏi sau:

1. Nguồn dữ liệu instance có phải Eureka, Consul hoặc provider đã có Spring Cloud starter không?
2. SimpleDiscoveryClient có đáp ứng được nếu danh sách endpoint ổn định không?
3. Vấn đề nằm ở nguồn dữ liệu hay chỉ ở cách LoadBalancer chọn instance?
4. Có cần ánh xạ service ID, metadata hoặc namespace riêng không?
5. Có cần đọc từ nhiều registry hay chỉ cần đổi provider?
6. Có cần đăng ký/hủy đăng ký local service hay chỉ tra cứu?
7. Ứng dụng dùng blocking hay reactive API?
8. Catalog có timeout, authentication, pagination và cache policy rõ ràng không?
9. Có test contract và quy trình rollback không?
10. Có thể giải quyết bằng cấu hình hiện có thay vì thêm một abstraction mới không?

Nếu câu trả lời cho thấy nguồn dữ liệu đã được hỗ trợ và yêu cầu chỉ là chọn instance, hãy tùy chỉnh LoadBalancer. Nếu cần ghi registration, xem ServiceRegistry. Chỉ xây dựng DiscoveryClient khi thật sự cần một adapter đọc dữ liệu discovery mới.

## 19. Kết luận

DiscoveryClient tùy chỉnh phù hợp khi Spring Cloud chưa có adapter cho nguồn catalog của tổ chức, cần ánh xạ service ID hoặc metadata theo quy ước riêng, hoặc cần tích hợp một API discovery đặc thù. Implementation cần tuân thủ hợp đồng getInstances(), getServices(), description(), probe() và trả ServiceInstance có địa chỉ định tuyến chính xác.

Trước khi viết, hãy phân biệt rõ DiscoveryClient với ServiceRegistry và ServiceInstanceListSupplier. Dùng implementation có sẵn khi có thể, SimpleDiscoveryClient cho danh sách tĩnh, LoadBalancer supplier cho chính sách chọn instance và ServiceRegistry cho vòng đời đăng ký. Nếu xây dựng custom client, cần có timeout, cache, bảo mật, health probe, kiểm thử contract và kế hoạch migration rõ ràng.

## Tài liệu tham khảo

- [Spring Cloud Commons — Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html)
- [Spring Cloud Commons — DiscoveryClient API](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/client/discovery/DiscoveryClient.java)
- [Spring Cloud Commons — ServiceInstance API](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/client/ServiceInstance.java)
- [Spring Cloud Commons — DefaultServiceInstance](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/client/DefaultServiceInstance.java)
- [Spring Cloud LoadBalancer — Client-Side Load Balancing](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html)
- [Spring Cloud LoadBalancer — Getting Started Guide](https://spring.io/guides/gs/spring-cloud-loadbalancer/)
- [Spring Boot — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html)

