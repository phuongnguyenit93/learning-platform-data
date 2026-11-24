# Đường điều khiển đăng ký và đường truyền yêu cầu nghiệp vụ

Trong kiến trúc microservice, việc một ứng dụng biết địa chỉ của dịch vụ khác gồm hai hoạt động có mục đích khác nhau. Hệ thống cần **công bố và cập nhật thông tin instance** để các thành phần biết service nào đang tồn tại; sau đó consumer cần **gửi request nghiệp vụ đến một instance cụ thể**. Có thể nhìn hai hoạt động này như đường điều khiển (control path) và đường truyền yêu cầu (data path).

Trong Spring Cloud Service Discovery, đường điều khiển thường đi qua cơ chế đăng ký của provider, ServiceRegistry, service registry và health check. Đường truyền yêu cầu đi qua consumer, DiscoveryClient hoặc nguồn instance list, Spring Cloud LoadBalancer và HTTP client để gọi provider. Hai đường có liên hệ chặt chẽ vì đường truyền sử dụng thông tin do đường điều khiển công bố.

Phân biệt hai đường giúp thiết kế và chẩn đoán hệ thống rõ hơn: registry có thể hoạt động tốt nhưng request vẫn thất bại do mạng hoặc provider; ngược lại, registry tạm thời không truy cập được nhưng consumer có thể vẫn gọi được một số instance từ dữ liệu cache hiện có.

## 1. Hai đường giải quyết hai câu hỏi khác nhau

Hãy xét order-service cần gọi inventory-service. Có thể có ba instance inventory đang chạy trên ba container khác nhau. Consumer không nên lưu cố định địa chỉ của từng container, vì địa chỉ thay đổi khi scale, restart hoặc triển khai phiên bản mới.

Hệ thống cần trả lời hai câu hỏi:

- **Đường điều khiển:** Service nào đang được công bố? Instance nào tồn tại? Instance có đủ điều kiện nhận traffic không? Thông tin đăng ký đã thay đổi chưa?
- **Đường truyền yêu cầu:** Với request này, consumer sẽ chọn instance nào? Kết nối đến endpoint nào? Provider có xử lý và trả response thành công không?

| Khía cạnh | Đường điều khiển đăng ký | Đường truyền yêu cầu nghiệp vụ |
|---|---|---|
| Mục tiêu | Công bố và duy trì trạng thái dịch vụ | Gửi request đến dịch vụ đích |
| Thành phần chính | Provider discovery integration, ServiceRegistry, registry, health check | Consumer, DiscoveryClient/instance supplier, LoadBalancer, HTTP client, provider |
| Dữ liệu chính | Service ID, instance ID, host, port, metadata, health status | HTTP request, URI đích, header, body, response |
| Nhịp hoạt động | Khi khởi động, heartbeat, health check, thay đổi trạng thái, shutdown và refresh | Mỗi lần có request nghiệp vụ |
| Lỗi thường gặp | Đăng ký thất bại, sai service ID, health check sai, registry chậm cập nhật | Timeout, connection refused, lỗi HTTP, endpoint không truy cập được |
| Câu hỏi chẩn đoán | Registry đang công bố những instance nào? | Request thực tế đã đi đến instance nào và kết quả ra sao? |

Hai đường là một cách phân tích kiến trúc. Không nhất thiết chúng phải chạy trên hai mạng vật lý riêng biệt hoặc hai cụm máy chủ riêng. Trong triển khai Spring Cloud, một số hoạt động có thể dùng chung tiến trình, kết nối hoặc thư viện.

## 2. Sơ đồ kiến trúc tổng quan

~~~mermaid
flowchart TB
    subgraph CP["Đường điều khiển đăng ký"]
        P["Provider instance"] -->|"register / update / deregister"| SR["ServiceRegistry integration"]
        SR --> R[("Eureka Server / Consul")]
        HC["Health checker / agent"] -->|"probe"| P
        HC -->|"report status"| R
        R -->|"registry data / refresh"| DC["Discovery data phía consumer"]
    end

    subgraph DP["Đường truyền yêu cầu nghiệp vụ"]
        C["Consumer"] -->|"service ID + request"| LB["Spring Cloud LoadBalancer"]
        DC -->|"instance list"| LB
        LB -->|"chọn endpoint"| HTTP["HTTP client"]
        HTTP -->|"HTTP request"| P
        P -->|"HTTP response"| C
    end
~~~

Đường điều khiển tạo và cập nhật thông tin định tuyến. Đường truyền yêu cầu sử dụng thông tin đó để chọn đích và chuyển dữ liệu nghiệp vụ.

Một số hệ thống có thể đặt registry và consumer trong cùng mạng nội bộ; một số hệ thống có thể dùng Consul Agent cục bộ trên node. Dù topology khác nhau, trách nhiệm logic vẫn có thể phân biệt theo hai đường.

## 3. Đường điều khiển: provider công bố instance

Đường điều khiển bắt đầu khi provider khởi động. Provider cần công bố tên dịch vụ và endpoint mà consumer có thể truy cập.

Ví dụ, một instance của inventory-service có thể công bố:

| Thuộc tính | Giá trị minh họa |
|---|---|
| Service ID | inventory-service |
| Instance ID | inventory-service-8081-node-a |
| Host | 10.0.1.12 |
| Port | 8081 |
| Scheme | http |
| Metadata | zone=zone-a, version=v2 |
| Health | UP |

Các trường cụ thể phụ thuộc implementation. Điều quan trọng là địa chỉ được công bố phải có thể định tuyến từ phía consumer. Đăng ký một địa chỉ chỉ truy cập được từ container của provider sẽ khiến discovery trả về dữ liệu có vẻ hợp lệ nhưng request vẫn thất bại.

### 3.1. Vai trò của ServiceRegistry

Spring Cloud Commons định nghĩa ServiceRegistry như abstraction để đăng ký và cập nhật trạng thái instance. Các thao tác phổ biến trong hợp đồng gồm đăng ký, hủy đăng ký, cập nhật status và đọc status. Registration object mang thông tin phù hợp với backend cụ thể.

Luồng logic khi provider khởi động:

1. Spring Boot tạo application context.
2. Discovery integration đọc cấu hình ứng dụng như service name, port, host và metadata.
3. Integration tạo registration object.
4. Implementation của ServiceRegistry gửi registration đến registry hoặc agent.
5. Registry lưu thông tin instance để consumer có thể khám phá.

Trong ứng dụng Spring Cloud, starter thường cung cấp auto-configuration cho quá trình này. Provider không cần tự triển khai HTTP client để gọi API đăng ký của Eureka hoặc Consul nếu đã dùng integration tương ứng.

### 3.2. Ví dụ cấu hình provider với Eureka

Một ứng dụng Eureka Client có thể dùng cấu hình:

~~~yaml
spring:
  application:
    name: inventory-service

server:
  port: 8081

eureka:
  client:
    serviceUrl:
      defaultZone: http://eureka.internal:8761/eureka/
  instance:
    preferIpAddress: true
~~~

Khi ứng dụng khởi động, Eureka Client đăng ký instance với Eureka Server và gia hạn lease theo chu kỳ heartbeat. Eureka Server duy trì thông tin đăng ký dựa trên các lease và quy tắc vận hành của Eureka.

Thuộc tính preferIpAddress ảnh hưởng đến cách instance công bố địa chỉ trong cấu hình phù hợp. Cần kiểm tra địa chỉ được quảng bá có thể truy cập từ consumer, đặc biệt khi ứng dụng chạy trong container hoặc qua nhiều subnet.

### 3.3. Ví dụ cấu hình provider với Consul

Với Consul, ứng dụng Spring Cloud thường đăng ký service thông qua Consul Agent:

~~~yaml
spring:
  application:
    name: inventory-service
  cloud:
    consul:
      host: consul-agent.internal
      port: 8500
      discovery:
        service-name: inventory-service
~~~

Agent tiếp nhận thông tin đăng ký và đồng bộ vào catalog. Health check, tags, instance ID và các tùy chọn deregistration có thể được cấu hình bổ sung tùy yêu cầu triển khai và phiên bản Spring Cloud Consul.

Consul có mô hình agent và catalog riêng. Vì vậy, khi điều tra registration, cần xem trạng thái ở agent cũng như trạng thái được công bố trong catalog.

## 4. Đường điều khiển: duy trì health và cập nhật registry

Đăng ký thành công không có nghĩa instance sẽ luôn khỏe. Registry cần biết instance còn tồn tại và có thể nhận traffic hay không.

Hai cơ chế thường gặp:

- **Heartbeat/lease:** client gửi tín hiệu định kỳ để duy trì registration. Nếu lease hết hạn, registry có thể loại hoặc đánh dấu instance theo chính sách.
- **Health check:** agent hoặc registry thực hiện probe, chẳng hạn HTTP hoặc TCP, rồi cập nhật trạng thái health.

Eureka chủ yếu duy trì registration bằng heartbeat/lease của client và có thể tích hợp trạng thái health ứng dụng theo cấu hình. Consul hỗ trợ các health check được gắn với service registration, thường thông qua agent. Không nên coi heartbeat và health check là cùng một khái niệm: heartbeat cho biết client còn duy trì đăng ký, trong khi health check kiểm tra điều kiện phục vụ theo một phép thử cụ thể.

### 4.1. Liveness và readiness

Với Spring Boot Actuator, ứng dụng có thể cung cấp endpoint health. Khi cần tách khả năng sống và khả năng nhận traffic, hãy thiết kế probe theo mục đích:

- **Liveness:** tiến trình có còn hoạt động và có thể tiếp tục chạy không?
- **Readiness:** instance đã sẵn sàng nhận request nghiệp vụ chưa?
- **Dependency health:** các dependency như database hoặc message broker có đáp ứng không?

Ví dụ cấu hình exposure endpoint health:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      show-details: never
~~~

Cấu hình exposure không tự đảm bảo registry đang gọi đúng readiness endpoint. Phải cấu hình đường dẫn, port, giao thức và quyền truy cập tương ứng trong backend hoặc discovery integration. Tránh công khai chi tiết nội bộ của health indicator cho các đối tượng không được phép.

### 4.2. Trạng thái thay đổi và thời gian hội tụ

Giả sử instance inventory-service-8081-node-a bắt đầu trả health check thất bại:

1. Probe phát hiện lỗi hoặc heartbeat không còn được gia hạn.
2. Backend áp dụng threshold, timeout và chính sách health/lease.
3. Registry cập nhật trạng thái hoặc loại instance khỏi kết quả phù hợp.
4. Discovery client hoặc instance supplier phía consumer làm mới dữ liệu.
5. Load balancer dùng danh sách mới cho các lần chọn instance tiếp theo.

Các bước này không nhất thiết xảy ra tức thời. Health interval, số lần thất bại, thời gian lease, cache và chu kỳ refresh đều ảnh hưởng thời gian từ khi instance lỗi đến khi mọi consumer ngừng chọn nó.

Khái niệm **eventual consistency** hữu ích để hiểu khoảng trễ đó: các thành phần có thể nhìn thấy trạng thái khác nhau trong một khoảng thời gian trước khi dữ liệu hội tụ. Ứng dụng vẫn phải chịu được request thất bại trong khoảng chuyển tiếp.

## 5. Đường truyền yêu cầu: consumer khám phá service

Consumer biết service ID, ví dụ inventory-service, nhưng không cần biết instance đang chạy ở host nào. Trong Spring Cloud Commons, DiscoveryClient cung cấp API truy vấn:

~~~java
List<String> getServices();

List<ServiceInstance> getInstances(String serviceId);
~~~

getServices() liệt kê các service ID mà discovery client nhìn thấy. getInstances(serviceId) trả về danh sách ServiceInstance tương ứng. Mỗi instance thường cung cấp host, port, URI, trạng thái secure và metadata.

Ví dụ inject DiscoveryClient:

~~~java
import java.util.List;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Service;

@Service
public class InventoryLookup {

    private final DiscoveryClient discoveryClient;

    public InventoryLookup(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public List<ServiceInstance> findInstances() {
        return discoveryClient.getInstances("inventory-service");
    }
}
~~~

Kết quả này là dữ liệu discovery mà consumer đang nhìn thấy. Nó có thể đến từ registry hoặc cache phía client tùy implementation và cấu hình. Một danh sách có instance không đảm bảo endpoint vẫn khỏe khi request được gửi đi vài mili giây sau đó.

### 5.1. Truy vấn discovery không phải request nghiệp vụ

Khi consumer gọi getInstances(), nó đang hỏi thông tin định tuyến. Request này không phải là request nghiệp vụ như “lấy danh sách sản phẩm” hay “tạo đơn hàng”.

Sự phân biệt này quan trọng khi đo tải và chẩn đoán:

- Truy vấn discovery tạo tải lên registry hoặc cache/discovery client.
- Request nghiệp vụ tạo tải lên provider instance.
- Một request nghiệp vụ có thể không cần gọi registry trực tiếp nếu instance list đã được cache và còn hiệu lực.
- Discovery client có thể refresh dữ liệu ở background hoặc theo cơ chế riêng của backend.

Do đó, không nên mặc định rằng mỗi HTTP request nghiệp vụ đều tạo một lần gọi mạng đến registry. Cách refresh phụ thuộc discovery implementation, cache và service instance supplier.

## 6. Load balancer nối thông tin điều khiển với request nghiệp vụ

Khi có nhiều instance, consumer cần chọn một instance cho mỗi lần gọi. Spring Cloud LoadBalancer dùng service ID và nguồn instance list để thực hiện lựa chọn.

Luồng logic:

1. Consumer gọi logical URL, ví dụ http://inventory-service/api/items.
2. HTTP client được tích hợp load balancing nhận ra inventory-service là service ID.
3. LoadBalancer lấy danh sách instance có thể sử dụng.
4. Một instance được chọn theo thuật toán và cấu hình.
5. HTTP client gửi request đến endpoint của instance đó.

Ví dụ cấu hình RestTemplate:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestTemplate;

@Configuration
public class HttpClientConfiguration {

    @Bean
    @LoadBalanced
    RestTemplate restTemplate() {
        return new RestTemplate();
    }
}
~~~

Ví dụ gọi API theo tên service:

~~~java
ItemResponse[] items = restTemplate.getForObject(
        "http://inventory-service/api/items",
        ItemResponse[].class
);
~~~

Ứng dụng cần dependency Spring Cloud LoadBalancer tương thích và một discovery integration đã được cấu hình. Với WebClient hoặc RestClient, cách tích hợp phụ thuộc phiên bản Spring Boot và Spring Cloud đang sử dụng.

### 6.1. Vai trò của instance supplier và cache

LoadBalancer thường nhận instance thông qua một service instance list supplier. Supplier có thể lấy dữ liệu từ DiscoveryClient, áp dụng lọc hoặc cache tùy cấu hình.

Một số điểm cần phân biệt:

- DiscoveryClient là abstraction truy vấn service discovery.
- Service instance supplier cung cấp danh sách instance cho LoadBalancer.
- Cache giữ danh sách trong một khoảng thời gian để giảm truy vấn lặp.
- LoadBalancer chọn instance từ danh sách được cung cấp.

Cache giúp giảm tải registry và độ trễ tra cứu, nhưng cache quá lâu có thể giữ endpoint đã lỗi. Cache quá ngắn có thể làm tăng tải và chi phí cập nhật. Cần chọn cấu hình dựa trên tốc độ thay đổi instance, quy mô hệ thống và khả năng chịu sai lệch của request.

## 7. Request nghiệp vụ đi đến provider

Sau khi chọn endpoint, HTTP client mở kết nối và gửi request. Từ đây, luồng xử lý là luồng HTTP thông thường:

~~~mermaid
sequenceDiagram
    participant O as order-service
    participant LB as LoadBalancer
    participant DS as Discovery data
    participant I as inventory instance
    O->>LB: GET http://inventory-service/api/items
    LB->>DS: Obtain candidate instances
    DS-->>LB: Instance A, B, C
    LB->>LB: Select one instance
    LB->>I: HTTP GET /api/items
    I-->>O: HTTP response
~~~

Provider nhận request, xác thực caller, kiểm tra quyền, xử lý nghiệp vụ và trả response. Service discovery không thực hiện các trách nhiệm đó thay provider.

Ví dụ, order-service có thể chọn instance A ở thời điểm đầu và instance B ở request tiếp theo. Mã nghiệp vụ vẫn gọi cùng logical URL. Nếu request đầu tiên thất bại vì instance A vừa ngừng hoạt động nhưng registry chưa cập nhật, consumer cần timeout và chính sách lỗi phù hợp.

Không nên retry mọi request một cách mù quáng. Retry thao tác ghi không idempotent có thể tạo đơn hàng hoặc thanh toán trùng. Hãy dùng idempotency key hoặc cơ chế nghiệp vụ phù hợp trước khi bật retry cho thao tác có tác dụng phụ.

## 8. Quan hệ giữa hai đường khi scale và deploy

Đường điều khiển phản ánh thay đổi vòng đời instance; đường truyền yêu cầu sử dụng thông tin đã cập nhật để gửi request.

### 8.1. Scale out: thêm instance

Khi inventory-service tăng từ hai lên ba instance:

1. Instance mới khởi động và công bố cùng service ID.
2. Đường điều khiển đăng ký endpoint mới vào registry.
3. Health check hoặc readiness xác nhận instance đủ điều kiện nhận traffic theo chính sách.
4. Registry công bố trạng thái mới.
5. Consumer cập nhật instance list theo chu kỳ refresh.
6. LoadBalancer có thể chọn instance mới cho request tiếp theo.

Trong thời gian hội tụ, một số consumer có thể chưa nhìn thấy instance mới. Điều này không nhất thiết là lỗi; cần xem refresh/cache và trạng thái đăng ký.

### 8.2. Scale in: loại instance

Khi cần dừng một instance:

1. Provider chuyển sang trạng thái không nhận traffic mới hoặc bắt đầu graceful shutdown.
2. Provider deregister khỏi registry nếu lifecycle và backend hỗ trợ.
3. Registry cập nhật danh sách.
4. Consumer refresh discovery data.
5. LoadBalancer ngừng chọn instance sau khi danh sách mới có hiệu lực.
6. Request đang xử lý được hoàn tất theo graceful shutdown và connection draining.

Nếu instance bị kill đột ngột, deregistration có thể không diễn ra. Heartbeat/lease hoặc health check sẽ giúp phát hiện sự cố sau một khoảng thời gian. Vì vậy, request đang bay hoặc consumer còn cache có thể vẫn gặp lỗi trong giai đoạn chuyển tiếp.

### 8.3. Deploy phiên bản mới

Trong rolling deployment, phiên bản cũ và mới có thể cùng tồn tại dưới một service ID. Metadata như version, zone hoặc region có thể hỗ trợ quan sát hoặc lọc instance, nhưng chỉ khi backend, supplier và chính sách LoadBalancer được cấu hình để sử dụng các thuộc tính đó.

Không nên giả định chỉ vì metadata đã được đăng ký thì LoadBalancer tự động ưu tiên hoặc loại một phiên bản. Quy tắc chọn cần được triển khai và kiểm thử rõ ràng.

## 9. Khi một đường lỗi nhưng đường còn lại vẫn hoạt động

Hai đường liên hệ với nhau nhưng có thể gặp lỗi độc lập. Phân biệt chúng giúp chọn biện pháp khắc phục đúng chỗ.

| Tình huống | Đường điều khiển | Đường truyền yêu cầu | Ảnh hưởng có thể thấy |
|---|---|---|---|
| Registry tạm thời không truy cập được | Đăng ký/refresh bị gián đoạn | Có thể vẫn gọi bằng cache hiện có | Không thấy instance mới; dữ liệu cũ có thể tiếp tục được dùng |
| Provider chết nhưng registry chưa phát hiện | Dữ liệu health/lease chưa cập nhật | Request đến instance đó có thể timeout | Lỗi kết nối dù discovery vẫn trả instance |
| Consumer không kết nối registry | Truy vấn/refresh thất bại | Có thể dùng cache hoặc không chọn được instance | Phụ thuộc dữ liệu còn cache và chính sách lỗi |
| Provider đăng ký sai địa chỉ | Registration thành công nhưng endpoint sai | Request không kết nối được | Có instance trong registry nhưng gọi thất bại |
| Network policy chặn consumer đến provider | Registry có thể hoàn toàn khỏe | Request thất bại | Discovery thành công nhưng data path bị chặn |
| LoadBalancer cấu hình sai | Registry vẫn công bố đúng | Chọn instance hoặc chuyển URL sai | Lỗi định tuyến phía consumer |

### 9.1. Registry gián đoạn không đồng nghĩa mọi request dừng ngay

Nếu consumer còn danh sách instance cache hợp lệ, một số request có thể tiếp tục đi đến provider trong khi registry tạm thời mất kết nối. Tuy nhiên:

- Instance mới có thể không được phát hiện.
- Instance đã lỗi có thể vẫn nằm trong cache.
- Cache hết hạn có thể khiến consumer không lấy được danh sách mới.
- Hành vi khi refresh thất bại phụ thuộc implementation và cấu hình.

Vì vậy, không nên thiết kế ứng dụng với giả định registry luôn sẵn sàng hoặc cache luôn còn dữ liệu đúng.

### 9.2. Registry khỏe không bảo đảm request thành công

Registry có thể công bố một instance healthy, nhưng request vẫn có thể thất bại do:

- Host hoặc port được quảng bá không định tuyến từ consumer.
- Firewall, security group hoặc network policy chặn kết nối.
- Provider bị quá tải sau lần health check gần nhất.
- TLS certificate hoặc authentication không hợp lệ.
- API trả lỗi nghiệp vụ hoặc lỗi dependency.

Health check là tín hiệu theo thời điểm và theo phép thử cụ thể. Nó không phải cam kết rằng mọi request tiếp theo đều thành công.

## 10. Bảo mật cho đường điều khiển và đường truyền

Đường điều khiển mang dữ liệu topology và quyền thay đổi registration. Đường truyền mang dữ liệu nghiệp vụ. Cả hai đều cần được bảo vệ.

| Phạm vi | Rủi ro | Biện pháp |
|---|---|---|
| Registry API | Người lạ đọc topology hoặc sửa registration | Authentication, authorization, ACL và giới hạn network |
| Provider registration | Instance giả mạo service hoặc endpoint | Chỉ workload được cấp quyền mới được đăng ký |
| Metadata | Rò rỉ token, password hoặc thông tin nội bộ | Không lưu secret trong metadata; giới hạn dữ liệu công bố |
| Health endpoint | Lộ chi tiết hệ thống hoặc bị lạm dụng | Chỉ cho agent/monitoring cần thiết truy cập; giới hạn response |
| Consumer đến provider | Nghe lén hoặc giả mạo endpoint | TLS, xác thực service-to-service và quản lý certificate |
| API nghiệp vụ | Người gọi vượt quyền | Authentication và authorization tại provider |

Với Consul, có thể dùng ACL để giới hạn quyền đọc/ghi catalog và đăng ký service. Với Eureka, cần bảo vệ server, network, thông tin xác thực và các endpoint quản trị theo mô hình triển khai. Việc consumer tìm thấy địa chỉ không đồng nghĩa consumer có quyền gọi API.

## 11. Quan sát riêng từng đường

Để vận hành tốt, cần có chỉ số và log tách biệt cho registration/discovery và request nghiệp vụ.

### Quan sát đường điều khiển

Theo dõi:

- Số instance đã đăng ký theo service ID.
- Thời điểm đăng ký và deregistration.
- Tỷ lệ heartbeat hoặc health check thành công.
- Thời gian từ lúc instance khởi động đến khi xuất hiện trong registry.
- Thời gian từ lúc instance lỗi đến khi bị loại khỏi kết quả discovery.
- Lỗi kết nối, xác thực hoặc timeout giữa provider, agent và registry.

### Quan sát đường truyền yêu cầu

Theo dõi:

- Service ID được gọi và instance thực tế được chọn.
- Request rate, latency và status code theo instance.
- Tỷ lệ timeout, connection refused và lỗi TLS.
- Số lần retry và kết quả retry.
- Tỷ lệ phân phối traffic giữa các instance.
- Trace ID để nối log consumer với log provider.

Khi ghi log, không đưa token, credential hoặc payload nhạy cảm vào log. Đồng bộ thời gian giữa consumer, provider và registry để so sánh timestamp và xác định khoảng trễ.

## 12. Quy trình chẩn đoán từ trên xuống

Khi order-service không gọi được inventory-service, hãy xác định lỗi thuộc đường nào:

1. **Kiểm tra provider:** instance có đang chạy và API có phản hồi trực tiếp từ mạng consumer không?
2. **Kiểm tra registration:** registry có đúng service ID, host, port và instance ID không?
3. **Kiểm tra health:** instance có healthy/readiness theo cấu hình không? Heartbeat hoặc check gần nhất có thành công không?
4. **Kiểm tra discovery:** DiscoveryClient ở consumer có trả danh sách instance không? Dữ liệu có cũ không?
5. **Kiểm tra load balancing:** LoadBalancer có chọn đúng instance và tạo đúng URI không?
6. **Kiểm tra network và security:** Consumer có kết nối được endpoint đã chọn không? TLS, credential và policy có cho phép không?
7. **Kiểm tra nghiệp vụ:** Provider nhận request chưa, trả status nào và lỗi ở tầng nào?

Một phép thử hữu ích là so sánh hai cách gọi trong môi trường kiểm thử: gọi trực tiếp một endpoint đã biết và gọi bằng logical service name. Nếu gọi trực tiếp thành công nhưng gọi theo tên thất bại, hãy tập trung vào discovery data, load balancer hoặc cách tích hợp HTTP client. Nếu cả hai đều thất bại, kiểm tra provider, network và API.

## 13. Ví dụ tổng hợp: order-service và inventory-service

Giả sử inventory-service có ba instance. order-service cần đọc số lượng tồn kho trước khi xác nhận đơn hàng.

**Đường điều khiển:**

1. Ba instance khởi động với service ID inventory-service.
2. Mỗi instance đăng ký endpoint riêng vào Eureka hoặc Consul.
3. Registry duy trì trạng thái bằng lease/heartbeat hoặc health check.
4. Một instance lỗi; backend cập nhật trạng thái và consumer dần nhận được danh sách mới.
5. Một instance mới được triển khai; sau khi đăng ký và healthy, nó xuất hiện trong discovery data.

**Đường truyền yêu cầu:**

1. order-service nhận yêu cầu xác nhận đơn hàng.
2. HTTP client gọi http://inventory-service/api/items.
3. Spring Cloud LoadBalancer nhận danh sách instance khả dụng.
4. LoadBalancer chọn một instance.
5. HTTP client gửi request đến endpoint đó.
6. inventory-service trả số lượng tồn kho.
7. order-service tiếp tục hoặc từ chối xác nhận đơn theo kết quả nghiệp vụ.

Nếu registry tạm thời gián đoạn nhưng consumer còn cache, một số request có thể tiếp tục. Nếu cache chứa instance đã lỗi, request vẫn có thể thất bại. Nếu registry hoạt động bình thường nhưng network policy chặn kết nối đến instance, discovery thành công vẫn không giúp request hoàn tất.

## 14. Ghi nhớ

- Đường điều khiển đăng ký công bố service ID, instance endpoint, metadata và trạng thái health.
- ServiceRegistry là abstraction phía đăng ký; Eureka và Consul có cơ chế lưu trữ, heartbeat và health khác nhau.
- Đường truyền yêu cầu sử dụng thông tin discovery để chọn instance và gửi request nghiệp vụ.
- DiscoveryClient tìm danh sách instance; Spring Cloud LoadBalancer chọn instance; HTTP client thực hiện kết nối.
- Registry và consumer có thể nhìn thấy trạng thái khác nhau trong một khoảng thời gian do heartbeat, health check, cache và refresh.
- Registry khỏe không đảm bảo endpoint truy cập được; request thất bại không nhất thiết có nghĩa registration thất bại.
- Bảo vệ registry và registration ở đường điều khiển; bảo vệ kết nối và API ở đường truyền.
- Quan sát riêng registration/health và latency/error của request giúp xác định đúng vị trí lỗi.

Khi phân tích service discovery qua hai đường này, có thể biết hệ thống đang gặp vấn đề ở việc công bố và cập nhật thông tin hay ở việc sử dụng thông tin đó để chuyển request. Đây là cơ sở để thiết kế, triển khai và vận hành Spring Cloud Service Discovery ổn định khi microservice thay đổi liên tục.
