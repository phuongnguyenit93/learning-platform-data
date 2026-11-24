# Khám phá phía máy khách và phía máy chủ

Trong microservice, một dịch vụ thường có nhiều instance chạy trên các máy hoặc container khác nhau. Địa chỉ của từng instance có thể thay đổi khi triển khai, mở rộng hoặc khởi động lại. Vì vậy, consumer cần một cách gọi dịch vụ bằng tên logic, chẳng hạn **inventory-service**, thay vì phải biết trước địa chỉ IP và cổng của từng instance.

Service discovery giải quyết việc tìm các instance đang được đăng ký cho một dịch vụ. Sau khi có danh sách instance, hệ thống còn phải quyết định instance nào sẽ nhận request. Hai quyết định này có thể được đặt ở phía ứng dụng gọi dịch vụ hoặc ở một thành phần trung gian. Đó là điểm khác nhau cốt lõi giữa **client-side discovery** và **server-side discovery**.

Trong Spring Cloud, các khái niệm **DiscoveryClient**, **ServiceRegistry**, Eureka, Consul và Spring Cloud LoadBalancer thường xuất hiện cùng nhau. Hiểu đúng vai trò của từng thành phần giúp chọn kiến trúc phù hợp và tránh nhầm registry với bộ cân bằng tải.

## 1. Các thành phần tham gia service discovery

Một kiến trúc discovery thường có ba vai trò:

| Thành phần | Trách nhiệm |
|---|---|
| Service provider | Khởi tạo instance và đăng ký thông tin dịch vụ như service ID, host, port và metadata. |
| Service registry | Lưu thông tin các instance đã đăng ký và trạng thái mà registry biết được. Eureka Server và Consul là những lựa chọn phổ biến. |
| Service consumer | Tìm các instance theo service ID, chọn đích đến và gửi request. |

Spring Cloud cung cấp các abstraction để ứng dụng không phải phụ thuộc trực tiếp vào một registry cụ thể:

- **ServiceRegistry** đại diện cho thao tác đăng ký và hủy đăng ký một instance.
- **DiscoveryClient** cung cấp API để truy vấn các instance theo service ID.
- **ServiceInstance** mô tả một instance đã được phát hiện, thường bao gồm host, port, URI, service ID và metadata.
- **Spring Cloud LoadBalancer** chọn một instance từ danh sách phù hợp khi ứng dụng cần gọi dịch vụ theo tên logic.

Eureka hoặc Consul đóng vai trò registry. Chúng lưu và cung cấp thông tin instance theo cơ chế riêng của từng nền tảng. Spring Cloud LoadBalancer là thành phần lựa chọn instance ở phía client. Registry không tự động trở thành load balancer chỉ vì nó lưu danh sách instance.

## 2. Khám phá phía máy khách (client-side discovery)

Với client-side discovery, chính ứng dụng consumer truy vấn registry hoặc sử dụng danh sách instance được discovery client cập nhật. Sau đó, consumer chọn một instance và kết nối trực tiếp đến instance đó.

~~~mermaid
flowchart LR
    C["Order Service<br/>Consumer"] -->|"1. Tìm inventory-service"| R[("Service Registry")]
    R -->|"2. Danh sách instance"| C
    C -->|"3. Chọn instance và gọi trực tiếp"| I1["Inventory instance A"]
    C -.->|"Có thể chọn ở request tiếp theo"| I2["Inventory instance B"]
~~~

Luồng xử lý điển hình:

1. Khi khởi động, mỗi instance của **inventory-service** đăng ký service ID cùng địa chỉ truy cập của nó vào registry.
2. **order-service** cần gọi **inventory-service**, nên yêu cầu discovery client tìm các instance có service ID tương ứng.
3. Discovery client trả về danh sách **ServiceInstance** mà nó biết. Danh sách có thể đến từ registry hoặc từ cache được cập nhật định kỳ.
4. Bộ cân bằng tải phía client chọn một instance theo chiến lược đã cấu hình.
5. Consumer gửi request trực tiếp đến địa chỉ của instance được chọn.

### Ví dụ với Spring Cloud LoadBalancer và RestTemplate

Có thể khai báo một RestTemplate được tích hợp với Spring Cloud LoadBalancer:

~~~java
@Configuration
public class HttpClientConfiguration {

    @Bean
    @LoadBalanced
    public RestTemplate restTemplate(RestTemplateBuilder builder) {
        return builder.build();
    }
}
~~~

Consumer gọi dịch vụ bằng service ID:

~~~java
@Service
public class InventoryClient {

    private final RestTemplate restTemplate;

    public InventoryClient(RestTemplate restTemplate) {
        this.restTemplate = restTemplate;
    }

    public ItemDto getItem(String itemId) {
        return restTemplate.getForObject(
            "http://inventory-service/api/items/{id}",
            ItemDto.class,
            itemId
        );
    }
}
~~~

Trong URL trên, **inventory-service** là tên dịch vụ logic. Khi request đi qua RestTemplate có **@LoadBalanced**, Spring Cloud LoadBalancer dùng service ID để tìm và chọn một instance phù hợp, sau đó thay phần địa chỉ logic bằng địa chỉ thực của instance được chọn. Ứng dụng không cần tự ghi danh sách IP và port của từng instance.

Ví dụ này cần các dependency Spring Cloud phù hợp, bao gồm tích hợp registry mà hệ thống sử dụng và Spring Cloud LoadBalancer. **@LoadBalanced** chỉ đánh dấu client HTTP để áp dụng cơ chế cân bằng tải; nó không tự tạo registry và cũng không tự đăng ký provider.

### Truy vấn instance trực tiếp bằng DiscoveryClient

Khi cần xem thông tin instance hoặc xây dựng một luồng tích hợp đặc thù, ứng dụng có thể truy vấn DiscoveryClient:

~~~java
@Service
public class ServiceLookup {

    private final DiscoveryClient discoveryClient;

    public ServiceLookup(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public List<ServiceInstance> findInventoryInstances() {
        return discoveryClient.getInstances("inventory-service");
    }
}
~~~

**getInstances** trả về các instance mà discovery client hiện biết. Danh sách rỗng có thể có nghĩa là chưa có instance được đăng ký, registry chưa cập nhật, hoặc consumer không truy vấn được dữ liệu cần thiết. Việc có danh sách instance cũng chưa đảm bảo mọi instance đều đang xử lý request tốt.

Trong ứng dụng thông thường, nên để Spring Cloud LoadBalancer đảm nhiệm việc chọn instance thay vì tự viết thuật toán chọn trong từng service. Cách này giúp chính sách lựa chọn, cấu hình và tích hợp với các client HTTP được quản lý nhất quán hơn.

### Ưu điểm và giới hạn

Client-side discovery có các ưu điểm:

- Consumer gọi trực tiếp provider, không cần thêm một proxy trung gian cho mỗi request.
- Có thể áp dụng chiến lược chọn instance theo nhu cầu của từng consumer.
- Phù hợp với hệ thống có nhiều service Spring Cloud và các ứng dụng đều có thể truy cập registry.
- Có thể kết hợp với retry, circuit breaker và các chính sách resilience ở phía consumer.

Mô hình này cũng có một số giới hạn:

- Mỗi loại client cần thư viện hoặc cơ chế discovery tương thích. Client viết bằng ngôn ngữ khác phải tự tích hợp registry hoặc có lớp hỗ trợ tương ứng.
- Consumer cần kết nối được đến registry và thường cũng cần kết nối mạng trực tiếp đến các instance provider.
- Cache ở client có thể giữ địa chỉ cũ trong một khoảng thời gian, nhất là khi instance vừa bị dừng hoặc thay đổi địa chỉ.
- Khi có nhiều loại consumer, việc quản lý phiên bản thư viện, cấu hình và chính sách chọn instance ở nhiều nơi có thể phức tạp.

## 3. Khám phá phía máy chủ (server-side discovery)

Với server-side discovery, consumer gửi request đến một địa chỉ ổn định, chẳng hạn virtual IP, load balancer hoặc API Gateway. Thành phần trung gian nhận request sẽ tìm instance phù hợp và chuyển tiếp request đến provider.

Consumer ban đầu không cần truy vấn registry và không cần biết địa chỉ của từng instance provider.

~~~mermaid
flowchart LR
    C["Web App hoặc Order Service"] -->|"1. Gọi địa chỉ ổn định"| L["Load Balancer hoặc API Gateway"]
    L -->|"2. Tra cứu hoặc dùng danh sách đã đồng bộ"| R[("Service Registry")]
    R -->|"3. Các instance phù hợp"| L
    L -->|"4. Chuyển tiếp request"| I1["Inventory instance A"]
    L -.->|"Có thể chọn instance khác"| I2["Inventory instance B"]
~~~

Luồng xử lý điển hình:

1. Provider đăng ký các instance vào registry như trong mô hình client-side.
2. Consumer gửi request đến địa chỉ của load balancer hoặc gateway.
3. Thành phần trung gian lấy danh sách instance từ registry, hoặc sử dụng danh sách đích đã được đồng bộ trước đó.
4. Thành phần trung gian chọn một instance theo trạng thái sức khỏe và chính sách định tuyến.
5. Request được chuyển tiếp đến provider đã chọn; response quay lại consumer qua thành phần trung gian.

Thành phần trung gian có thể là load balancer ở tầng mạng, reverse proxy, API Gateway hoặc một lớp routing trong service mesh. Không phải mọi load balancer đều tự truy vấn Eureka hay Consul; cần có cơ chế tích hợp hoặc đồng bộ danh sách đích phù hợp với nền tảng triển khai.

### Ví dụ với Spring Cloud Gateway

Trong hệ thống Spring Cloud, API Gateway có thể nhận request bên ngoài và định tuyến đến service ID bằng URI **lb://**:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: inventory-route
          uri: lb://inventory-service
          predicates:
            - Path=/inventory/**
~~~

Gateway nhận request có đường dẫn **/inventory/**. Với URI **lb://inventory-service**, Gateway sử dụng tích hợp discovery và Spring Cloud LoadBalancer để tìm, chọn instance của **inventory-service**, rồi chuyển tiếp request đến instance đó. Consumer bên ngoài chỉ cần biết địa chỉ Gateway.

Có một điểm cần phân biệt: xét từ consumer bên ngoài, việc khám phá và chọn provider diễn ra ở phía server trung gian nên đây là cách triển khai theo mô hình server-side discovery. Tuy nhiên, bên trong Gateway, thành phần định tuyến vẫn có thể dùng Spring Cloud LoadBalancer để lựa chọn instance. Tên mô hình mô tả vị trí mà consumer ban đầu nhìn thấy và giao trách nhiệm discovery, không nhất thiết mô tả thuật toán nội bộ của từng thành phần.

### Ưu điểm và giới hạn

Server-side discovery có các ưu điểm:

- Client đơn giản hơn vì chỉ cần gọi một địa chỉ ổn định.
- Client không cần biết registry hoặc có quyền truy cập trực tiếp vào mạng nội bộ của provider.
- Có thể tập trung định tuyến, xác thực, giới hạn lưu lượng, TLS termination và quan sát request ở gateway hoặc proxy.
- Phù hợp khi hệ thống có nhiều loại client, bao gồm trình duyệt, ứng dụng di động hoặc service viết bằng nhiều ngôn ngữ.

Các giới hạn cần cân nhắc:

- Request đi qua thêm một thành phần trung gian, làm tăng một chặng mạng và có thể tăng độ trễ.
- Gateway hoặc load balancer cần đủ năng lực xử lý lưu lượng và phải được triển khai dự phòng để tránh trở thành điểm lỗi tập trung.
- Cần duy trì kết nối hoặc cơ chế đồng bộ giữa thành phần định tuyến và registry.
- Khi gateway, proxy hoặc registry gặp sự cố, phạm vi ảnh hưởng có thể rộng nếu kiến trúc không có phương án dự phòng.

## 4. So sánh hai mô hình

| Tiêu chí | Client-side discovery | Server-side discovery |
|---|---|---|
| Nơi tìm và chọn instance | Ứng dụng consumer | Load balancer, gateway hoặc proxy trung gian |
| Địa chỉ consumer sử dụng | Service ID, sau đó client chọn địa chỉ instance | Địa chỉ ổn định của thành phần trung gian |
| Consumer có cần truy cập registry? | Thường có, trực tiếp hoặc qua discovery client | Không cần |
| Kết nối đến provider | Consumer kết nối trực tiếp | Thành phần trung gian kết nối đến provider |
| Thành phần cần tích hợp | Discovery client và load balancer trong từng loại client | Load balancer hoặc gateway có tích hợp discovery |
| Chặng mạng | Thường ít hơn vì gọi trực tiếp | Có thêm chặng qua thành phần trung gian |
| Nơi quản lý chính sách chọn instance | Phân tán ở các consumer | Tập trung tại thành phần trung gian |
| Phù hợp với | Service-to-service trong hệ sinh thái có client hỗ trợ discovery | Nhiều loại client hoặc môi trường cần che giấu mạng nội bộ |

Không có mô hình nào luôn tốt hơn. Quyết định phụ thuộc vào khả năng tích hợp của client, ranh giới mạng, yêu cầu bảo mật, độ trễ và cách vận hành hệ thống.

## 5. Vòng đời đăng ký và cập nhật instance

Hai mô hình khác nhau ở nơi thực hiện discovery và chọn instance, nhưng vẫn cần một vòng đời đăng ký dịch vụ đáng tin cậy:

1. **Khởi động:** provider tạo instance và đăng ký service ID, địa chỉ, port cùng metadata cần thiết.
2. **Duy trì trạng thái:** instance gửi heartbeat hoặc được kiểm tra sức khỏe theo cơ chế của registry và nền tảng triển khai.
3. **Cập nhật danh sách:** consumer hoặc thành phần trung gian lấy thông tin instance mới. Một số hệ thống dùng cache để giảm số lần truy vấn registry.
4. **Định tuyến request:** bộ cân bằng tải chọn một instance đang được xem là phù hợp và gửi request đến đó.
5. **Dừng instance:** provider hủy đăng ký khi shutdown có kiểm soát; nếu instance mất kết nối đột ngột, registry cần cơ chế timeout hoặc health check để loại bỏ instance không còn hợp lệ.

Trạng thái trong registry có thể chậm hơn trạng thái thực tế của ứng dụng. Ví dụ, một instance vừa bị lỗi nhưng bản ghi vẫn còn trong cache của consumer hoặc gateway. Vì vậy, health check, thời gian cache, heartbeat và quá trình graceful shutdown cần được cấu hình phù hợp với thời gian phục hồi mà hệ thống mong muốn.

## 6. Lưu ý khi triển khai trong Spring Cloud

**Phân biệt đăng ký và khám phá.** Provider đăng ký bằng cơ chế ServiceRegistry hoặc tích hợp tự động của starter. Consumer khám phá qua DiscoveryClient. Có bản ghi đăng ký không đồng nghĩa consumer đã cấu hình đúng để gọi dịch vụ.

**Phân biệt discovery và load balancing.** Discovery trả lời câu hỏi có những instance nào cho một service ID. Load balancing quyết định request hiện tại đi đến instance nào. Trong Spring Cloud, hai trách nhiệm này có thể được phối hợp nhưng vẫn là hai khái niệm riêng.

**Chú ý dữ liệu cũ.** Khi instance bị thay thế, địa chỉ cũ có thể còn trong cache hoặc danh sách đích đã đồng bộ. Cần chọn thời gian refresh, heartbeat và health check phù hợp; đồng thời xử lý lỗi kết nối khi một địa chỉ vừa hết hiệu lực.

**Không coi health check là bảo đảm tuyệt đối.** Một instance vượt qua health check vẫn có thể lỗi ở một endpoint cụ thể, quá tải hoặc mất kết nối sau thời điểm kiểm tra. Consumer nên có timeout hợp lý, retry có giới hạn và circuit breaker khi phù hợp. Retry cần cân nhắc tính idempotent của thao tác để tránh gửi lặp một yêu cầu ghi dữ liệu.

**Giới hạn quyền truy cập registry.** Chỉ các thành phần cần thiết mới nên truy cập registry. Bảo vệ thông tin xác thực, dùng TLS khi phù hợp và không đưa bí mật vào metadata của service instance. Với server-side discovery, cần bảo vệ kênh kết nối giữa gateway hoặc load balancer và registry.

**Kiểm tra khả năng kết nối thực tế.** Địa chỉ instance được đăng ký phải có thể truy cập từ nơi thực hiện request. Một địa chỉ nội bộ chỉ hợp lệ trong mạng provider có thể không dùng được với consumer ở mạng khác. Cần xem xét subnet, DNS, port, firewall và địa chỉ quảng bá khi triển khai container hoặc nhiều vùng mạng.

## 7. Chọn mô hình nào?

Client-side discovery thường phù hợp khi các service nội bộ chủ yếu dùng Spring Cloud, đều có thể tích hợp discovery client, và đội ngũ muốn consumer kết nối trực tiếp đến provider. Mô hình này giúp giảm chặng trung gian và cho phép từng consumer áp dụng chính sách lựa chọn phù hợp.

Server-side discovery thường phù hợp khi client đa dạng, không thể hoặc không nên truy cập registry, hoặc hệ thống cần một điểm tập trung để kiểm soát định tuyến và bảo mật. API Gateway là lựa chọn phổ biến ở ranh giới hệ thống; load balancer hoặc proxy nội bộ có thể đảm nhiệm vai trò tương tự giữa các mạng dịch vụ.

Một hệ thống có thể kết hợp cả hai. Ví dụ, trình duyệt và ứng dụng di động gọi qua API Gateway theo mô hình server-side; các service Spring Cloud ở mạng nội bộ gọi nhau bằng client-side discovery. Cách kết hợp này giữ giao diện truy cập bên ngoài ổn định trong khi các service nội bộ vẫn có thể giao tiếp trực tiếp.

Khi thiết kế, hãy xác định rõ consumer nào chịu trách nhiệm tìm instance, thành phần nào chọn đích đến, thành phần đó lấy dữ liệu từ registry bằng cách nào, và điều gì xảy ra khi dữ liệu discovery bị cũ. Trả lời được bốn câu hỏi này sẽ giúp kiến trúc service discovery rõ ràng và dễ vận hành hơn.
