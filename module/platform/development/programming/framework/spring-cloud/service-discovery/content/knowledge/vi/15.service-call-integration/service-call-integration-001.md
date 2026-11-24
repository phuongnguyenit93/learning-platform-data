# Từ serviceId đến danh sách instance rồi đến một yêu cầu HTTP

Trong hệ thống microservice, một dịch vụ thường chạy nhiều bản sao (replica). Các bản sao có thể được tạo thêm, khởi động lại hoặc chuyển máy trong lúc hệ thống hoạt động. Vì vậy, consumer không nên giữ cố định địa chỉ IP và cổng của provider. Consumer cần biết **tên logic của dịch vụ**, tìm các instance hiện có rồi gửi yêu cầu đến một instance phù hợp.

Spring Cloud cung cấp các abstraction để thực hiện luồng này. **DiscoveryClient** đọc danh sách instance theo serviceId; **ServiceRegistry** đại diện cho các thao tác đăng ký và quản lý trạng thái; Eureka và Consul là những hệ thống có thể lưu thông tin đăng ký; **Spring Cloud LoadBalancer** chọn một instance để gửi request. Các thành phần này phối hợp để biến một địa chỉ logic như `http://inventory-service` thành địa chỉ mạng thực tế.

## 1. Phân biệt serviceId, instance và registry

Giả sử hệ thống bán hàng có dịch vụ quản lý tồn kho. Dịch vụ này được triển khai thành ba bản sao:

| Khái niệm | Ví dụ | Ý nghĩa |
|---|---|---|
| serviceId | `inventory-service` | Tên logic mà consumer dùng để tìm dịch vụ |
| Instance | `10.20.1.11:8081` | Một tiến trình provider đang chạy và có thể nhận request |
| Instance ID | `inventory-service:node-a:8081` | Định danh một bản sao cụ thể trong registry |
| Registry | Eureka hoặc Consul | Nơi lưu thông tin các instance đã đăng ký |
| Discovery client | `DiscoveryClient` | API để ứng dụng hỏi danh sách instance theo serviceId |

Một serviceId có thể ánh xạ đến không instance nào, một instance hoặc nhiều instance. Danh sách này thay đổi theo trạng thái triển khai. Instance record thường chứa serviceId, instance ID, host, port, scheme bảo mật và metadata như zone hoặc phiên bản.

Tên dịch vụ thường bắt nguồn từ cấu hình `spring.application.name` của provider:

~~~yaml
spring:
  application:
    name: inventory-service

server:
  port: 8081
~~~

Khi có nhiều bản sao, mỗi bản sao đăng ký cùng serviceId nhưng có địa chỉ và instance ID riêng. Consumer chỉ cần biết serviceId; nó không cần biết trước các địa chỉ vật lý.

## 2. Vòng đời từ lúc provider khởi động đến khi rời registry

Một luồng đăng ký phổ biến diễn ra như sau:

1. **Khởi động ứng dụng:** provider nạp cấu hình, xác định serviceId, instance ID, địa chỉ và cổng có thể truy cập.
2. **Đăng ký:** discovery client gửi thông tin instance đến registry. Registry lưu bản ghi để consumer có thể tra cứu.
3. **Theo dõi trạng thái:** client gửi heartbeat hoặc registry thực hiện health check theo cơ chế của từng nền tảng. Kết quả kiểm tra giúp registry xác định instance còn phục vụ được hay không.
4. **Tra cứu và sử dụng:** consumer lấy danh sách instance và chọn một instance để gửi request.
5. **Rời hệ thống:** khi ứng dụng tắt có kiểm soát, client cố gắng deregister. Nếu tiến trình chết đột ngột, registry thường chỉ loại bỏ bản ghi sau khi lease, TTL hoặc health check cho thấy instance không còn hợp lệ.

Eureka và Consul đều hỗ trợ đăng ký dịch vụ nhưng chi tiết vận hành khác nhau. Eureka client thường duy trì lease bằng heartbeat; Eureka Server có cơ chế loại bỏ instance không gia hạn lease, đồng thời có thể điều chỉnh việc eviction trong một số trạng thái bảo vệ registry. Consul dùng service registration kết hợp health check như HTTP, TCP hoặc TTL. Vì vậy, không nên giả định mọi registry đều phát hiện instance chết ngay lập tức hoặc dùng cùng một khoảng thời gian kiểm tra.

Đăng ký thành công cũng không đồng nghĩa ứng dụng đã sẵn sàng xử lý mọi request. Health endpoint cần phản ánh đúng khả năng phục vụ; nếu ứng dụng đánh dấu healthy quá sớm, consumer có thể gọi vào instance chưa khởi tạo xong. Ngược lại, health check quá nhạy có thể loại instance tạm thời chậm khỏi danh sách.

## 3. Dùng DiscoveryClient để lấy danh sách instance

Trong Spring Cloud Commons, `DiscoveryClient` cung cấp API tra cứu discovery ở mức trừu tượng. Ứng dụng không cần phụ thuộc trực tiếp vào API riêng của Eureka hoặc Consul:

- `getServices()` trả về các serviceId mà discovery implementation đang biết.
- `getInstances(serviceId)` trả về các instance đã biết của serviceId đó.

Ví dụ sau minh họa cách tra cứu địa chỉ của một instance:

~~~java
import java.net.URI;
import java.util.List;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Service;

@Service
public class InventoryInstanceLookup {

    private final DiscoveryClient discoveryClient;

    public InventoryInstanceLookup(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public List<URI> findInstanceUris() {
        List<ServiceInstance> instances =
                discoveryClient.getInstances("inventory-service");

        if (instances.isEmpty()) {
            throw new IllegalStateException(
                    "No instance registered for inventory-service");
        }

        return instances.stream()
                .map(ServiceInstance::getUri)
                .toList();
    }
}
~~~

Kết quả có thể chứa nhiều URI, ví dụ:

~~~text
http://10.20.1.11:8081
http://10.20.1.12:8081
http://10.20.1.13:8081
~~~

Đoạn code chỉ minh họa bước **serviceId → danh sách instance**. Nó chưa thực hiện cân bằng tải. Nếu luôn lấy phần tử đầu tiên, mọi request có thể dồn vào cùng một bản sao; thứ tự danh sách cũng không phải cam kết về độ ưu tiên. Trong ứng dụng thực tế, hãy để Spring Cloud LoadBalancer chọn instance hoặc triển khai một chính sách chọn có chủ đích.

Cần xử lý trường hợp danh sách rỗng như một lỗi phụ thuộc dịch vụ: trả lỗi phù hợp cho caller, áp dụng timeout và chính sách retry có giới hạn nếu phù hợp, đồng thời ghi log để điều tra. Không nên lặp tra cứu vô hạn hoặc chuyển một serviceId do người dùng bên ngoài cung cấp thẳng vào discovery API.

### DiscoveryClient và ServiceRegistry có vai trò khác nhau

Hai abstraction này thường xuất hiện cùng nhau nhưng phục vụ hai chiều khác nhau:

| API | Vai trò | Thao tác tiêu biểu |
|---|---|---|
| `DiscoveryClient` | Consumer tra cứu dịch vụ | Đọc serviceId và danh sách instance |
| `ServiceRegistry` | Provider hoặc thành phần quản lý đăng ký | Đăng ký, deregister, đọc hoặc cập nhật trạng thái registration |

`ServiceRegistry` là abstraction cho thao tác đăng ký; nó không phải tên gọi khác của Eureka Server hay Consul Server. Trong ứng dụng Spring Cloud, auto-registration thường được cấu hình thông qua discovery starter và vòng đời ứng dụng. Chỉ gọi API đăng ký thủ công khi có nhu cầu quản lý đặc biệt và đã hiểu rõ vòng đời của registration. Đăng ký trùng, quên deregister hoặc tự cập nhật trạng thái không đồng bộ với health check có thể làm registry phản ánh sai thực tế.

Ngoài `DiscoveryClient` đồng bộ, Spring Cloud còn có abstraction reactive tương ứng trong các tích hợp hỗ trợ reactive discovery. Chọn API phù hợp với stack của ứng dụng và tránh chặn event loop khi xử lý request reactive.

## 4. Từ danh sách instance đến một yêu cầu HTTP

Tra cứu danh sách instance mới giải quyết câu hỏi “có những bản sao nào?”. Để gửi HTTP request, ứng dụng còn phải chọn một bản sao, tạo địa chỉ đích và xử lý kết quả gọi.

Có hai cách tiếp cận:

- **Tự tra cứu và tự chọn:** gọi `DiscoveryClient`, chọn một `ServiceInstance`, sau đó gọi URI của instance. Cách này hữu ích cho công cụ quản trị, chẩn đoán hoặc trường hợp có chính sách chọn riêng.
- **Dùng Spring Cloud LoadBalancer:** consumer gửi request đến serviceId; LoadBalancer lấy danh sách ứng viên qua discovery integration, chọn instance và chuyển request đến địa chỉ vật lý. Đây thường là lựa chọn phù hợp cho lời gọi service-to-service thông thường.

Với Spring WebFlux, có thể khai báo một `WebClient.Builder` được đánh dấu `@LoadBalanced`:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class HttpClientConfiguration {

    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder() {
        return WebClient.builder();
    }
}
~~~

Consumer dùng builder đó để gọi bằng tên dịch vụ:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

@Component
public class InventoryClient {

    private final WebClient webClient;

    public InventoryClient(@LoadBalanced WebClient.Builder builder) {
        this.webClient = builder.build();
    }

    public Mono<InventoryResponse> findInventory(String sku) {
        return webClient.get()
                .uri("http://inventory-service/api/inventory/{sku}", sku)
                .retrieve()
                .bodyToMono(InventoryResponse.class);
    }
}
~~~

Trong ví dụ, `inventory-service` là serviceId. Với builder đã được đánh dấu `@LoadBalanced`, Spring Cloud bổ sung cơ chế phân giải serviceId và chọn instance. LoadBalancer chuyển đích logic thành host và port của instance đã chọn trước khi request được gửi đi. Nếu dùng `WebClient.Builder` thông thường không có cấu hình load balancing, tên `inventory-service` có thể bị xử lý như hostname DNS và không được phân giải theo registry.

Cần có discovery starter tương ứng với registry và Spring Cloud LoadBalancer trên classpath. Ví dụ, ứng dụng dùng Eureka thường thêm `spring-cloud-starter-netflix-eureka-client`; ứng dụng dùng Consul thường thêm `spring-cloud-starter-consul-discovery`. Thêm `spring-cloud-starter-loadbalancer` khi cấu hình ứng dụng cần starter này trực tiếp. Quản lý phiên bản bằng Spring Cloud BOM tương thích với phiên bản Spring Boot đang dùng; không ghép tùy ý các phiên bản release train.

Luồng xử lý tổng quát:

~~~mermaid
sequenceDiagram
    participant C as Consumer
    participant LB as Spring Cloud LoadBalancer
    participant D as DiscoveryClient
    participant R as Eureka hoặc Consul
    participant I as Instance được chọn

    C->>LB: GET http://inventory-service/api/inventory/sku-1
    LB->>D: Lấy instance theo serviceId
    D->>R: Đọc registry hoặc cache discovery
    R-->>D: Danh sách instance đã đăng ký
    D-->>LB: Các instance ứng viên
    LB->>LB: Chọn một instance
    LB->>I: HTTP GET đến host:port thực tế
    I-->>LB: HTTP response
    LB-->>C: HTTP response
~~~

Trên thực tế, discovery client hoặc service instance supplier có thể dùng cache; không nhất thiết mỗi request đều tạo một truy vấn mạng đến registry. Chính sách chọn mặc định thường là round-robin, nhưng ứng dụng có thể cấu hình supplier hoặc thuật toán khác. Kết quả còn phụ thuộc dữ liệu registry, cache và cấu hình health check tại thời điểm chọn.

## 5. Cấu hình registry ở provider và consumer

Ví dụ provider đăng ký với Eureka:

~~~yaml
spring:
  application:
    name: inventory-service

server:
  port: 8081

eureka:
  client:
    serviceUrl:
      defaultZone: http://localhost:8761/eureka/
~~~

Consumer có serviceId riêng nhưng gọi đến tên của provider:

~~~yaml
spring:
  application:
    name: order-service

eureka:
  client:
    serviceUrl:
      defaultZone: http://localhost:8761/eureka/
~~~

Trong code của order-service, lời gọi đến `http://inventory-service/...` được phân giải thành một instance inventory-service. Với Consul, provider và consumer cấu hình kết nối đến Consul agent/server bằng các thuộc tính `spring.cloud.consul`; tên dịch vụ đăng ký thường lấy từ `spring.application.name`. Cấu hình cụ thể phụ thuộc môi trường và phiên bản starter.

Trong môi trường container hoặc Kubernetes, cần bảo đảm địa chỉ mà provider đăng ký có thể truy cập được từ consumer. Một instance đăng ký địa chỉ loopback, hostname chỉ tồn tại trong container khác hoặc cổng nội bộ không được publish sẽ khiến tra cứu thành công nhưng kết nối HTTP thất bại.

## 6. Những lỗi thường gặp và cách điều tra

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Không tìm thấy instance | Provider chưa đăng ký, sai serviceId hoặc registry chưa sẵn sàng | So sánh `spring.application.name`, tên consumer gọi và danh sách service trong registry |
| Có instance nhưng gọi timeout | Host/port không thể truy cập từ consumer, firewall hoặc network sai | Thử kết nối từ chính môi trường chạy consumer đến địa chỉ instance |
| Gọi nhầm instance đã chết | Heartbeat, lease, health check hoặc cache chưa cập nhật | Kiểm tra trạng thái health, chu kỳ kiểm tra và thời gian cache |
| Request dồn vào một bản sao | Code luôn chọn phần tử đầu tiên hoặc LoadBalancer bị cấu hình sai | Kiểm tra cách chọn instance và log instance ID được chọn |
| Provider khởi động nhưng chưa sẵn sàng | Health endpoint báo healthy quá sớm | Điều chỉnh readiness/health check để chỉ nhận traffic khi dependency đã sẵn sàng |
| Registry có bản ghi trùng hoặc cũ | Instance ID không ổn định, shutdown không deregister hoặc TTL quá dài | Kiểm tra instance ID, vòng đời ứng dụng và chính sách hết hạn |

Khi chẩn đoán, ghi log serviceId, instance ID, host, port và kết quả gọi để có thể nối request với instance thực tế. Không ghi token, mật khẩu hoặc metadata nhạy cảm vào log. Cần phân biệt rõ ba tình huống: registry không có instance, LoadBalancer không chọn được instance, và đã chọn được instance nhưng kết nối HTTP thất bại. Mỗi tình huống nằm ở một lớp khác nhau.

Retry không thay thế health check hoặc discovery. Nếu request đã gửi đến instance lỗi, retry có thể giúp thử instance khác khi cấu hình LoadBalancer và retry cho phép; tuy nhiên retry phải có giới hạn, timeout rõ ràng và cân nhắc tính idempotent của thao tác. Với lệnh ghi dữ liệu, retry mù có thể tạo tác dụng phụ lặp lại.

## 7. Bảo mật và độ tin cậy

Registry là nguồn dữ liệu quan trọng để định tuyến nội bộ, vì vậy cần bảo vệ cả kênh đăng ký lẫn kênh tra cứu:

- Giới hạn mạng truy cập registry; bật xác thực và ACL theo khả năng của nền tảng.
- Dùng TLS cho kết nối đến registry và cân nhắc mTLS giữa các service khi mô hình bảo mật yêu cầu.
- Không lưu secret, access token hoặc dữ liệu cá nhân trong metadata của instance.
- Không xem việc tìm được địa chỉ instance là bằng chứng caller có quyền gọi API. Provider vẫn phải xác thực và phân quyền request.
- Chỉ cho phép serviceId từ cấu hình hoặc danh sách được kiểm soát; không biến discovery thành proxy tùy ý đến dịch vụ do người dùng chỉ định.
- Theo dõi số lượng instance, trạng thái health, thời gian đăng ký và lỗi gọi giữa các service.

Độ tin cậy của request phụ thuộc vào nhiều lớp: provider phải đăng ký đúng, registry phải cập nhật trạng thái, consumer phải nhận được danh sách đủ mới, LoadBalancer phải chọn ứng viên hợp lệ và mạng phải kết nối được đến instance. Không một abstraction đơn lẻ nào bảo đảm toàn bộ chuỗi luôn thành công.

## 8. Quy trình áp dụng

Khi tích hợp một lời gọi service-to-service, có thể đi theo trình tự sau:

1. Đặt serviceId ổn định cho provider bằng `spring.application.name`.
2. Chọn registry và cấu hình discovery starter tương ứng ở provider, consumer.
3. Xác minh provider đăng ký đúng host, port, instance ID và health check.
4. Kiểm tra consumer đọc được danh sách bằng `DiscoveryClient.getInstances(serviceId)`.
5. Dùng Spring Cloud LoadBalancer cho request HTTP thông thường; chỉ tự chọn instance khi có lý do cụ thể.
6. Đặt timeout, retry có giới hạn, xử lý danh sách rỗng và log instance được chọn.
7. Thử các tình huống provider khởi động, mở rộng replica, dừng có kiểm soát, chết đột ngột và registry tạm thời mất kết nối.
8. Bảo vệ registry và API provider theo chính sách bảo mật của hệ thống.

Điểm cần nắm vững là: **serviceId xác định dịch vụ logic; DiscoveryClient cung cấp danh sách instance; LoadBalancer chọn một instance; HTTP client gửi request đến địa chỉ thực tế của instance đó.** Registry và health check duy trì dữ liệu phục vụ quá trình này, còn ứng dụng vẫn phải xử lý timeout, lỗi mạng và trạng thái instance thay đổi trong lúc request đang chạy.

