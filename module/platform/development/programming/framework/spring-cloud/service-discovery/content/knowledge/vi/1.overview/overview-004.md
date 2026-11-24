# Luồng tổng thể từ đăng ký đến khám phá và gọi dịch vụ

Trong một hệ thống microservice, một dịch vụ có thể chạy thành nhiều instance trên các máy hoặc container khác nhau. Địa chỉ của mỗi instance có thể thay đổi khi triển khai, mở rộng hoặc khởi động lại. Consumer vì vậy cần tìm dịch vụ bằng tên logic thay vì phụ thuộc vào IP và port được ghi cố định trong mã nguồn.

**Service discovery trong Spring Cloud** kết nối các bước đăng ký instance, lưu thông tin tại registry, kiểm tra tình trạng phục vụ, truy vấn danh sách instance và chọn đích đến cho request. Các abstraction như ServiceRegistry và DiscoveryClient giúp ứng dụng làm việc với cơ chế discovery; Eureka và Consul cung cấp các backend registry; Spring Cloud LoadBalancer hỗ trợ chọn instance khi gọi dịch vụ.

Bài này trình bày toàn bộ vòng đời từ lúc provider khởi động đến khi consumer gửi request, sau đó theo dõi những thay đổi khi instance khỏe, lỗi, mở rộng hoặc dừng. Đây là luồng nền tảng của Spring Cloud Service Discovery, bao gồm đăng ký, health check, load balancing, bảo mật và xử lý sai lệch dữ liệu registry trong môi trường microservice.

## 1. Các thành phần tham gia

Trước khi theo dõi luồng, cần phân biệt vai trò của từng thành phần:

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| Provider | Ứng dụng cung cấp API hoặc năng lực nghiệp vụ | `inventory-service` |
| Provider instance | Một tiến trình cụ thể của provider | `10.0.1.12:8081` |
| Service registry | Lưu thông tin service và các instance đã đăng ký | Eureka Server, Consul catalog |
| ServiceRegistry | Abstraction phía Spring Cloud để đăng ký, cập nhật hoặc hủy đăng ký instance | Implementation của Eureka hoặc Consul |
| DiscoveryClient | Abstraction để truy vấn service ID và các instance tương ứng | `getServices()`, `getInstances()` |
| Consumer | Ứng dụng cần gọi provider | `order-service` |
| Health check | Cơ chế đánh giá instance có đáp ứng điều kiện phục vụ hay không | HTTP health endpoint, heartbeat/lease |
| Load balancer | Chọn một instance từ danh sách có thể phục vụ | Spring Cloud LoadBalancer |
| HTTP client | Gửi request đến endpoint đã chọn | RestTemplate, WebClient, RestClient |

Một **service ID** đại diện cho dịch vụ logic, chẳng hạn `inventory-service`. Một service ID có thể tương ứng với nhiều instance. Registry lưu thông tin từng instance như host, port, scheme, ID và metadata tùy backend.

Điểm quan trọng là các abstraction có trách nhiệm khác nhau:

- `ServiceRegistry` thuộc phía công bố dịch vụ: provider đăng ký thông tin instance và cập nhật trạng thái.
- `DiscoveryClient` thuộc phía tìm kiếm: consumer truy vấn registry để biết dịch vụ nào và instance nào đang được công bố.
- `LoadBalancer` chọn một instance để phục vụ một lần gọi. Nó thường sử dụng danh sách instance lấy qua discovery client.

## 2. Sơ đồ luồng từ provider đến consumer

Luồng tổng thể có thể hình dung như sau:

~~~mermaid
flowchart TD
    P["Provider khởi động"] --> C["Đọc service ID, host, port và metadata"]
    C --> SR["ServiceRegistry / Discovery adapter"]
    SR --> R[("Service Registry")]
    R --> H["Heartbeat hoặc health check"]
    H --> S["Cập nhật trạng thái instance"]
    U["Consumer nhận request nghiệp vụ"] --> D["DiscoveryClient"]
    D --> R
    D --> I["Danh sách ServiceInstance"]
    I --> L["Spring Cloud LoadBalancer"]
    L --> E["Chọn một endpoint"]
    E --> HC["HTTP client gửi request"]
    HC --> P2["Provider instance xử lý"]
    P2 --> RES["Response về consumer"]
    P2 -. "Dừng / deregister" .-> SR
~~~

Có thể chia luồng thành ba giai đoạn:

1. **Công bố dịch vụ:** provider tạo thông tin instance và đăng ký vào registry.
2. **Duy trì trạng thái:** registry nhận heartbeat hoặc thực hiện health check; trạng thái instance thay đổi theo vòng đời ứng dụng.
3. **Tìm và gọi dịch vụ:** consumer truy vấn instance, load balancer chọn endpoint, HTTP client gửi request.

Các bước cụ thể khác nhau giữa Eureka và Consul. Sơ đồ mô tả hợp đồng và ý tưởng chung; backend quyết định cách đăng ký, kiểm tra sức khỏe, lưu trữ và cập nhật dữ liệu.

## 3. Giai đoạn 1: Provider khởi động và đăng ký instance

Giả sử hệ thống có dịch vụ quản lý kho tên `inventory-service`. Khi chạy một instance, ứng dụng cần công bố tối thiểu thông tin để consumer có thể định vị nó:

- Service ID: `inventory-service`.
- Host hoặc địa chỉ mạng mà consumer có thể truy cập.
- Port ứng dụng đang lắng nghe.
- Scheme hoặc thông tin kết nối bảo mật nếu có.
- Instance ID để phân biệt những bản chạy cùng service.
- Metadata cần thiết cho việc định tuyến hoặc vận hành.

Trong Spring Boot, `spring.application.name` thường được dùng làm service ID mặc định. Ví dụ cấu hình nền tảng:

~~~yaml
spring:
  application:
    name: inventory-service

server:
  port: 8081
~~~

Nếu có hai instance cùng chạy với cấu hình service name này, cả hai cùng công bố service ID `inventory-service`, nhưng phải có endpoint và định danh instance phù hợp với từng bản chạy.

### 3.1. Đăng ký qua ServiceRegistry

Spring Cloud Commons định nghĩa abstraction `ServiceRegistry` cho thao tác đăng ký. Provider hoặc discovery integration sử dụng registration object chứa thông tin instance để gửi đến registry.

Ở mức khái niệm, trình tự là:

1. Spring Boot tạo application context và khởi tạo discovery integration.
2. Integration xác định service ID, host, port, instance ID và metadata.
3. Implementation tạo thông tin đăng ký phù hợp với backend.
4. Instance được gửi đến registry hoặc agent quản lý registry.
5. Provider bắt đầu duy trì trạng thái đăng ký theo cơ chế backend.

Provider thường không phải tự viết lời gọi HTTP đến Eureka hoặc Consul. Starter và auto-configuration của Spring Cloud cung cấp các bean và lifecycle cần thiết khi cấu hình discovery được bật.

`ServiceRegistry` là abstraction đăng ký chung. Các backend có thể có cách biểu diễn registration và quy tắc trạng thái khác nhau. Vì vậy, không nên giả định mọi backend đều có cùng payload, heartbeat hoặc cách hủy đăng ký.

### 3.2. Ví dụ provider dùng Eureka

Một ứng dụng dùng Eureka Client có thể khai báo tên và địa chỉ Eureka Server trong cấu hình:

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
  instance:
    preferIpAddress: true
~~~

Để cấu hình này hoạt động, ứng dụng cần dependency Eureka Client tương thích với Spring Boot và Spring Cloud release train đang dùng. `preferIpAddress` ảnh hưởng đến địa chỉ mà client công bố trong trường hợp phù hợp; hãy đảm bảo địa chỉ đó có thể được consumer truy cập qua mạng triển khai.

Khi khởi động, Eureka Client đăng ký instance với Eureka Server và định kỳ gia hạn lease bằng heartbeat. Eureka Server dựa vào trạng thái lease và các quy tắc của nó để quản lý thông tin instance. Đây là cơ chế duy trì đăng ký của Eureka, không phải hành vi mặc định của mọi registry.

### 3.3. Ví dụ provider dùng Consul

Với Consul, ứng dụng thường kết nối Consul Agent. Agent tiếp nhận đăng ký service và đưa thông tin vào catalog của Consul. Một cấu hình minh họa:

~~~yaml
spring:
  application:
    name: inventory-service
  cloud:
    consul:
      host: localhost
      port: 8500
      discovery:
        service-name: inventory-service
~~~

Ví dụ này minh họa các thuộc tính kết nối và service name. Các tùy chọn health check, instance ID, tags và đăng ký tự động cần được cấu hình theo topology và phiên bản Spring Cloud Consul đang dùng.

Consul hỗ trợ đăng ký thông qua agent và kiểm tra sức khỏe bằng nhiều loại check. Agent và catalog phối hợp để consumer có thể truy vấn service cùng trạng thái health tương ứng.

## 4. Giai đoạn 2: Registry duy trì trạng thái và health check

Đăng ký thành công chỉ cho biết registry đã nhận thông tin instance. Một instance có thể gặp sự cố sau đó, vì vậy hệ thống cần cơ chế phát hiện và loại bỏ hoặc đánh dấu instance không còn phục vụ.

Có hai khái niệm liên quan nhưng không hoàn toàn giống nhau:

- **Heartbeat hoặc lease:** client định kỳ xác nhận rằng instance vẫn duy trì đăng ký. Nếu quá thời hạn, registry có thể xem registration là hết hiệu lực theo chính sách.
- **Health check:** một thành phần thực hiện kiểm tra trạng thái, ví dụ gọi HTTP health endpoint hoặc kiểm tra TCP. Kết quả có thể quyết định instance có được coi là healthy hay không.

Eureka thường dựa trên heartbeat và lease của client; có thể tích hợp trạng thái health ứng dụng theo cấu hình. Consul có thể chạy các health check do service đăng ký, chẳng hạn HTTP, TCP hoặc script tùy môi trường. Cách backend đánh giá và công bố trạng thái khác nhau.

### 4.1. Health endpoint của ứng dụng

Spring Boot Actuator cung cấp endpoint health khi ứng dụng thêm dependency Actuator và cấu hình exposure phù hợp. Ví dụ:

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

Một health endpoint chỉ nên công bố thông tin phù hợp với đối tượng được phép truy cập. Nếu registry hoặc agent cần gọi endpoint này, cần đảm bảo đường dẫn, cổng, giao thức và quyền truy cập khớp với cấu hình health check.

Health check có thể gồm:

- Liveness: tiến trình có còn hoạt động để tiếp tục chạy hay không.
- Readiness: instance đã sẵn sàng nhận traffic nghiệp vụ hay chưa.
- Dependency health: các phụ thuộc quan trọng như database hoặc message broker có đáp ứng hay không.

Không nên gộp mọi kiểm tra vào một endpoint mà không cân nhắc ý nghĩa. Nếu một dependency phụ trợ tạm thời lỗi nhưng service vẫn có thể xử lý một phần request, readiness policy cần phản ánh yêu cầu thực tế của ứng dụng.

### 4.2. Điều gì xảy ra khi instance unhealthy?

Một luồng xử lý phổ biến:

1. Health check thất bại hoặc heartbeat/lease không còn được gia hạn.
2. Backend cập nhật trạng thái registration theo chính sách.
3. Instance có thể bị đánh dấu unhealthy, bị loại khỏi danh sách truy vấn hoặc bị xóa sau thời gian chờ.
4. Discovery client hoặc load balancer cập nhật danh sách instance theo chu kỳ refresh/cache.
5. Request mới không nên tiếp tục được phân phối đến instance đã bị loại khỏi tập instance có thể phục vụ.

Không phải mọi backend đều loại instance ngay sau một lần health check thất bại. Threshold, timeout, interval, deregistration delay và cache có thể làm thay đổi thời điểm trạng thái mới có hiệu lực.

## 5. Giai đoạn 3: Consumer tìm service theo tên

Consumer không cần biết IP và port của từng provider instance. Nó chỉ cần biết service ID logic, ví dụ `inventory-service`.

Trong Spring Cloud Commons, `DiscoveryClient` cung cấp hai thao tác truy vấn cơ bản:

~~~java
List<String> getServices();

List<ServiceInstance> getInstances(String serviceId);
~~~

- `getServices()` trả về các service ID mà discovery client nhìn thấy.
- `getInstances(serviceId)` trả về danh sách `ServiceInstance` của service ID được yêu cầu.

`ServiceInstance` thường cung cấp service ID, host, port, URI, trạng thái secure, metadata và instance ID tùy implementation. Consumer có thể inject DiscoveryClient để truy vấn:

~~~java
import java.util.List;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Service;

@Service
public class InventoryDiscovery {

    private final DiscoveryClient discoveryClient;

    public InventoryDiscovery(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public List<ServiceInstance> findInventoryInstances() {
        return discoveryClient.getInstances("inventory-service");
    }
}
~~~

Nếu danh sách trả về rỗng, consumer chưa tìm thấy instance được công bố cho service ID đó tại thời điểm truy vấn. Ứng dụng phải xử lý tình huống này theo nghiệp vụ, chẳng hạn trả lỗi service unavailable hoặc áp dụng retry có giới hạn nếu phù hợp.

DiscoveryClient là API truy vấn. Nó không tự đăng ký provider, không đảm bảo endpoint còn sống ở thời điểm request và cũng không tự cân bằng tải cho mọi HTTP client.

### 5.1. Đường đi của một truy vấn

~~~mermaid
sequenceDiagram
    participant C as Consumer
    participant D as DiscoveryClient
    participant R as Registry
    participant I as ServiceInstance list
    C->>D: getInstances("inventory-service")
    D->>R: Query instances
    R-->>D: Registrations visible to client
    D-->>C: List<ServiceInstance>
~~~

Tùy backend, discovery client có thể đọc dữ liệu từ registry trực tiếp, qua agent, hoặc sử dụng dữ liệu đã cache. Vì vậy, kết quả truy vấn là góc nhìn hiện tại của client theo cơ chế đồng bộ dữ liệu, không phải ảnh chụp tức thời tuyệt đối của mọi tiến trình trong mạng.

## 6. Giai đoạn 4: Load balancer chọn instance

Nếu service có nhiều instance, consumer cần quyết định gửi request đến bản chạy nào. Spring Cloud LoadBalancer cung cấp cơ chế chọn instance dựa trên service ID và danh sách discovery.

Luồng thường gặp:

1. Consumer gửi request đến logical service name, chẳng hạn `http://inventory-service/api/items`.
2. HTTP client được tích hợp load balancing nhận biết đây là service ID, không phải hostname DNS thông thường.
3. Load balancer yêu cầu danh sách instance qua discovery integration.
4. Load balancer chọn một instance theo thuật toán và cấu hình hiện tại.
5. HTTP client gửi request đến URI của instance được chọn.

Ví dụ cấu hình `RestTemplate` có tích hợp load balancing:

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

Consumer gọi theo service ID:

~~~java
ItemResponse[] items = restTemplate.getForObject(
        "http://inventory-service/api/items",
        ItemResponse[].class
);
~~~

Để đoạn mã hoạt động, ứng dụng cần dependency Spring Cloud LoadBalancer tương thích và một DiscoveryClient implementation đã được cấu hình. Tùy phiên bản Spring Boot và loại HTTP client, có thể sử dụng tích hợp tương ứng cho WebClient hoặc RestClient.

Không nên lấy `getInstances()` rồi luôn chọn phần tử đầu tiên trong mã nghiệp vụ. Thứ tự danh sách không phải cam kết cân bằng tải; danh sách có thể rỗng, có thể thay đổi, và instance đầu tiên chưa chắc phù hợp nhất. Hãy để load balancer quản lý việc chọn instance và dùng chính sách timeout, retry hoặc circuit breaker phù hợp.

### 6.1. Discovery và load balancing là hai bước khác nhau

| Discovery | Load balancing |
|---|---|
| Tìm các instance thuộc service ID | Chọn một instance cho request cụ thể |
| Trả về thông tin instance | Dùng thông tin instance để định tuyến request |
| Làm việc với registry hoặc dữ liệu discovery đã cache | Làm việc với danh sách instance và chính sách chọn |
| Ví dụ: `getInstances("inventory-service")` | Ví dụ: chọn một `ServiceInstance` cho request |

Có danh sách instance không có nghĩa request đã được cân bằng tải. Ngược lại, load balancer cần nguồn cung cấp instance, thường là DiscoveryClient hoặc service instance list supplier phù hợp.

## 7. Giai đoạn 5: Provider nhận request và trả response

Sau khi load balancer chọn endpoint, HTTP client kết nối đến host và port đã công bố. Provider xử lý request như một request HTTP thông thường:

1. Network định tuyến đến endpoint của instance.
2. Web server của provider nhận request.
3. Spring MVC hoặc WebFlux định tuyến đến controller/handler.
4. Service layer xử lý nghiệp vụ và truy cập dependency cần thiết.
5. Provider trả response cho consumer.

Service discovery chỉ giúp tìm đích đến. Nó không thay thế xác thực người gọi, phân quyền nghiệp vụ, mã hóa kết nối, kiểm soát timeout hoặc xử lý lỗi. Một request đi đúng endpoint vẫn có thể bị từ chối bởi security filter, lỗi nghiệp vụ hoặc dependency phía provider.

Khi dùng HTTPS, cần đảm bảo instance công bố đúng scheme và consumer tin cậy chứng chỉ tương ứng. Nếu có gateway, proxy hoặc service mesh ở giữa, địa chỉ và luồng kết nối cần được thiết kế nhất quán với kiến trúc mạng đó.

## 8. Giai đoạn 6: Scale, thay đổi trạng thái và deregister

Service discovery là một luồng sống theo thời gian, không chỉ là thao tác tra cứu một lần.

### Khi scale out

Giả sử `inventory-service` tăng từ hai lên ba instance:

1. Instance mới khởi động với cùng service ID.
2. Instance mới đăng ký thông tin endpoint vào registry.
3. Health check hoặc trạng thái đăng ký cho biết instance đã sẵn sàng theo chính sách backend.
4. Registry công bố instance mới.
5. Discovery client và load balancer cập nhật danh sách.
6. Các request sau đó có thể được phân phối đến instance mới.

Không nên đưa instance vào nhận traffic trước khi ứng dụng sẵn sàng. Cần phối hợp trạng thái readiness, đăng ký và chính sách health check để tránh request đến instance đang khởi tạo.

### Khi scale in hoặc triển khai phiên bản mới

Khi một instance cần dừng:

1. Orchestrator hoặc ứng dụng phát tín hiệu shutdown.
2. Provider ngừng nhận request mới hoặc chuyển sang trạng thái không sẵn sàng.
3. Provider deregister khỏi registry nếu cơ chế backend hỗ trợ và shutdown được thực hiện có kiểm soát.
4. Registry cập nhật danh sách instance.
5. Consumer/load balancer làm mới dữ liệu discovery.
6. Request đang xử lý được hoàn tất theo thời gian graceful shutdown và connection draining đã cấu hình.

Nếu tiến trình bị kill đột ngột, bước deregister có thể không chạy. Khi đó heartbeat, lease hoặc health check giúp phát hiện instance đã biến mất, nhưng có thể tồn tại một khoảng trễ trước khi dữ liệu registry được cập nhật.

### Khi instance đổi địa chỉ

Nếu container hoặc máy ảo được tạo lại, host và port có thể đổi. Instance mới cần công bố endpoint mới. Consumer dựa trên service ID và discovery data được refresh sẽ tìm được địa chỉ mới mà không cần sửa URL trong mã nghiệp vụ.

## 9. Eureka và Consul thể hiện luồng như thế nào?

Cả Eureka và Consul đều có thể cung cấp service discovery cho Spring Cloud, nhưng cơ chế quản lý registration và health khác nhau.

| Khía cạnh | Eureka | Consul |
|---|---|---|
| Thành phần registry | Eureka Server | Consul Agent và catalog của Consul |
| Đăng ký | Eureka Client đăng ký với server | Service đăng ký qua Consul Agent hoặc cơ chế tích hợp |
| Duy trì trạng thái | Client gia hạn lease bằng heartbeat | Agent thực hiện health check và cập nhật trạng thái theo cấu hình |
| Health | Dựa vào lease và cấu hình health integration | Có thể dùng HTTP, TCP hoặc check khác |
| Truy vấn | Eureka client lấy danh sách registry theo cơ chế client | Consul discovery truy vấn catalog và trạng thái service |
| Tích hợp Spring Cloud | Spring Cloud Netflix Eureka | Spring Cloud Consul |

Các điểm khác biệt vận hành cần lưu ý:

- Eureka thường có góc nhìn registry được client cache; thay đổi có thể chưa xuất hiện ở tất cả consumer ngay lập tức.
- Consul có health check gắn với service registration; truy vấn service khỏe phụ thuộc check và tùy chọn discovery.
- Cấu hình timeout, interval, heartbeat, cache, deregistration và retry phải dựa trên backend cùng phiên bản đang triển khai.
- Không suy luận rằng một instance xuất hiện trong một giao diện quản trị chắc chắn sẽ được mọi consumer nhận ngay tại cùng thời điểm.

Dù backend nào được sử dụng, consumer vẫn có thể làm việc qua DiscoveryClient và load balancing abstraction khi integration tương ứng được cấu hình đúng.

## 10. Dữ liệu registry có thể sai lệch như thế nào?

Trong hệ phân tán, provider, registry và consumer không cập nhật trạng thái trong cùng một thời điểm. Vì vậy có thể có một khoảng thời gian mà mỗi thành phần nhìn thấy trạng thái khác nhau.

Ví dụ:

- Provider đã dừng nhưng registry chưa hết lease hoặc chưa chạy xong health check.
- Registry đã loại instance nhưng consumer vẫn còn bản cache cũ.
- Instance đã healthy nhưng consumer chưa refresh danh sách.
- Provider đăng ký sai host hoặc port khiến consumer tìm thấy instance nhưng không kết nối được.
- Nhiều instance trùng định danh làm registration cập nhật hoặc xóa nhầm bản ghi tùy backend.

### 10.1. Bảng tình huống và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Không thấy service ID | Provider chưa đăng ký, sai tên service hoặc consumer chưa kết nối registry | Kiểm tra cấu hình tên, log khởi động và kết nối registry |
| Service có tên nhưng không có instance | Instance chưa healthy, đăng ký thất bại hoặc bị loại khỏi catalog | Kiểm tra health check, lease và trạng thái registration |
| Có instance nhưng gọi timeout | Host/port sai, firewall, DNS hoặc route không truy cập được | Kiểm tra endpoint từ chính mạng consumer |
| Instance đã dừng nhưng vẫn xuất hiện | Cache hoặc lease/health check chưa hết hạn | Kiểm tra refresh interval, TTL và deregistration |
| Instance mới chạy nhưng chưa nhận traffic | Chưa đăng ký, chưa healthy hoặc consumer chưa cập nhật danh sách | Kiểm tra readiness và discovery refresh |
| Request phân phối không đều | Chính sách chọn, cache, số lượng request hoặc cấu hình client | Kiểm tra load balancer và metric theo instance |

### 10.2. Chiến lược giảm sai lệch

- Đặt health check interval, timeout và threshold phù hợp với thời gian khởi động và đặc tính ứng dụng.
- Dùng readiness để chỉ cho instance nhận traffic khi đã sẵn sàng.
- Cấu hình graceful shutdown và deregistration khi triển khai có kiểm soát.
- Đảm bảo host/port công bố có thể truy cập từ consumer, kể cả khi chạy qua nhiều network segment.
- Hiểu cache và refresh behavior của discovery client và load balancer.
- Đặt timeout cho request; chỉ retry với giới hạn và loại thao tác phù hợp.
- Theo dõi registration, health transition, số lượng instance và lỗi kết nối theo từng service ID.
- Không coi danh sách registry là bằng chứng tuyệt đối rằng endpoint chắc chắn phục vụ thành công.

## 11. Bảo mật trong toàn bộ luồng discovery

Registry lưu topology của hệ thống: tên service, địa chỉ instance, port, metadata và trạng thái. Nếu thông tin này bị truy cập trái phép, kẻ tấn công có thể thu thập bản đồ nội bộ hoặc đăng ký instance giả tùy quyền hạn backend.

Cần bảo vệ cả luồng đăng ký, truy vấn và gọi dịch vụ:

1. **Bảo vệ registry:** giới hạn network access, bật xác thực và phân quyền cho API quản trị.
2. **Bảo vệ registration:** chỉ workload được phép mới có thể đăng ký hoặc thay đổi trạng thái service.
3. **Bảo vệ metadata:** không lưu password, token hoặc secret trong metadata hiển thị cho consumer.
4. **Bảo vệ kết nối:** sử dụng TLS khi phù hợp; quản lý và xoay vòng certificate/credential.
5. **Bảo vệ health endpoint:** chỉ mở đường truy cập cần thiết cho registry hoặc monitoring được phép.
6. **Bảo vệ service API:** vẫn cần authentication và authorization ở provider; biết địa chỉ instance không đồng nghĩa được quyền gọi API.

Nếu sử dụng Consul ACL hoặc cơ chế bảo vệ của Eureka và hạ tầng xung quanh, hãy cấp quyền theo nguyên tắc tối thiểu. Credential của provider, consumer và operator nên có phạm vi riêng khi backend hỗ trợ.

## 12. Quan sát và chẩn đoán theo từng chặng

Khi request không đến được provider, hãy xác định chặng nào trong luồng bị lỗi thay vì chỉ nhìn log của consumer.

| Chặng | Dấu hiệu cần quan sát | Nguồn kiểm tra |
|---|---|---|
| Provider khởi động | Service ID, instance ID, endpoint được công bố | Log ứng dụng và cấu hình runtime |
| Registration | Thành công/thất bại, thời điểm đăng ký | Log provider, registry hoặc agent |
| Health | Healthy/unhealthy, thời gian chuyển trạng thái | Health check, Actuator, registry |
| Discovery | Danh sách service ID và instance nhìn thấy | DiscoveryClient hoặc API registry |
| Load balancing | Instance được chọn, lỗi chọn instance | Log/metric của HTTP client và load balancer |
| Request | Kết nối, latency, status code, timeout | Log và metric của consumer/provider |
| Deregistration | Thời điểm xóa hoặc hết hạn registration | Log shutdown và registry |

Một quy trình điều tra thực tế:

1. Xác nhận provider đang chạy và endpoint hoạt động trực tiếp từ mạng consumer.
2. Kiểm tra provider đã đăng ký đúng service ID, host và port chưa.
3. Kiểm tra health status và thời điểm heartbeat/lease gần nhất.
4. Truy vấn danh sách instance từ góc nhìn consumer.
5. Kiểm tra load balancer có chọn instance nào và URI nào.
6. Gửi request kiểm thử đến endpoint được chọn, rồi so sánh kết quả với request qua service ID.
7. Đối chiếu timestamp giữa provider, registry và consumer để tìm độ trễ đồng bộ.

Đồng bộ thời gian giữa các máy/container giúp ghép log chính xác hơn. Khi ghi log, nên có service ID, instance ID, trace ID và kết quả chọn endpoint nếu chính sách bảo mật cho phép; tránh ghi token, credential hoặc dữ liệu nhạy cảm.

## 13. Ví dụ tổng hợp: order-service gọi inventory-service

Giả sử hệ thống có hai ứng dụng:

- `inventory-service` cung cấp API đọc tồn kho.
- `order-service` cần gọi API tồn kho trước khi xác nhận đơn hàng.

Luồng chạy:

1. `inventory-service` khởi động với `spring.application.name=inventory-service`.
2. Discovery integration đăng ký instance vào Eureka hoặc Consul.
3. Registry duy trì registration và cập nhật trạng thái theo heartbeat/health check.
4. `order-service` khởi động với service ID riêng và kết nối cùng registry.
5. Khi cần kiểm tra tồn kho, `order-service` gọi URL logic `http://inventory-service/api/items`.
6. Load balancer lấy danh sách instance khỏe có thể sử dụng và chọn một instance.
7. HTTP client gửi request đến endpoint được chọn.
8. `inventory-service` xử lý và trả response.
9. Nếu có instance mới, instance cũ lỗi hoặc bị dừng, registry và discovery client cập nhật danh sách theo cơ chế của backend.

Consumer không cần sửa URL khi `inventory-service` tăng từ một lên nhiều instance. Nó tiếp tục gọi theo service ID; discovery và load balancing xử lý việc tìm và chọn endpoint.

Tuy nhiên, service ID không thay thế DNS, routing hoặc network policy. Địa chỉ mà provider đăng ký phải có thể truy cập từ consumer. Nếu các service nằm ở những mạng hoặc cluster khác nhau, cần thiết kế địa chỉ quảng bá, gateway, kết nối liên mạng hoặc cơ chế discovery phù hợp.

## 14. Ghi nhớ

- Provider đăng ký service instance vào registry thông qua discovery integration và abstraction đăng ký như ServiceRegistry.
- Registry duy trì trạng thái bằng heartbeat/lease, health check hoặc cơ chế riêng của backend.
- Consumer dùng DiscoveryClient để tìm service ID và danh sách ServiceInstance.
- Spring Cloud LoadBalancer chọn instance cho request; HTTP client gửi request đến endpoint đã chọn.
- Scale out, scale in, restart và đổi địa chỉ đều làm thay đổi dữ liệu discovery theo thời gian.
- Eureka và Consul có khác biệt về registration, health check, cache và cách truy vấn; cần cấu hình theo backend thực tế.
- Dữ liệu registry có thể trễ hoặc cũ. Cần readiness, graceful shutdown, timeout, quan sát và xử lý lỗi.
- Bảo mật registry, registration, metadata, health endpoint và API provider là một phần của thiết kế service discovery.

Khi nắm được luồng từ đăng ký đến gọi dịch vụ, có thể lần theo từng chặng để xác định lỗi nằm ở provider, registry, health check, discovery client, load balancer hay mạng. Đây là nền tảng để triển khai Spring Cloud Service Discovery ổn định khi số lượng instance và dịch vụ thay đổi liên tục.
