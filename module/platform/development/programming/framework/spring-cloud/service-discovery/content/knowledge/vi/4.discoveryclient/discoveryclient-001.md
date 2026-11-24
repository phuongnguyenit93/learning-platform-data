# Hợp đồng DiscoveryClient và cách lấy danh sách dịch vụ

Trong Spring Cloud Service Discovery, một ứng dụng có thể chạy thành nhiều instance ở các máy hoặc container khác nhau. Địa chỉ của từng instance có thể thay đổi khi triển khai, mở rộng hoặc khởi động lại. Vì vậy, consumer cần tìm instance theo tên dịch vụ thay vì gắn cứng IP và port.

**DiscoveryClient** là hợp đồng truy vấn của Spring Cloud Commons: nó cho phép ứng dụng hỏi registry đang biết những service ID nào và tìm các instance thuộc một service ID. Eureka, Consul và các cơ chế discovery khác có thể cung cấp implementation riêng, trong khi mã nghiệp vụ của consumer vẫn làm việc qua cùng một API.

Bài này tập trung vào hợp đồng đó, cách đọc danh sách dịch vụ và cách diễn giải kết quả trong một hệ thống microservice. Đây là một phần của Spring Cloud Service Discovery, nơi việc đăng ký, health check, load balancing, bảo mật và xử lý registry không đồng bộ cùng quyết định khả năng tìm thấy và gọi đúng instance.

## 1. Phân biệt service và instance

Một **service** là một năng lực logic, ví dụ `inventory-service`. Một **instance** là một tiến trình cụ thể đang cung cấp service đó, ví dụ tiến trình ở `10.0.2.15:8080`.

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Service ID | Tên logic dùng để tìm dịch vụ | `inventory-service` |
| Service instance | Một bản chạy cụ thể của dịch vụ | Instance A, instance B |
| Endpoint | Địa chỉ có thể kết nối đến instance | `http://10.0.2.15:8080` |
| Registry | Nơi lưu thông tin đăng ký và trạng thái instance | Eureka Server, Consul |
| Discovery client | Thành phần đọc thông tin dịch vụ từ registry | EurekaDiscoveryClient, ConsulDiscoveryClient |

Một service có thể có không, một hoặc nhiều instance. Service ID thường được cấu hình nhất quán giữa các bản chạy; với nhiều ứng dụng Spring Boot, `spring.application.name` là giá trị thường được dùng làm tên dịch vụ. Tên cuối cùng mà consumer nhìn thấy phụ thuộc vào cấu hình và implementation của registry.

Luồng tổng quát:

~~~mermaid
flowchart LR
    P["Provider instance"] -->|"đăng ký / gia hạn"| R[("Service registry")]
    C["Consumer"] --> D["DiscoveryClient"]
    D -->|"đọc service ID và instances"| R
    C --> L["Spring Cloud LoadBalancer"]
    L -->|"chọn một instance"| P
~~~

Provider đăng ký thông tin instance với registry. Consumer dùng DiscoveryClient để đọc thông tin đó. Khi cần gửi request đến một service, consumer thường kết hợp discovery với Spring Cloud LoadBalancer để chọn instance phù hợp.

## 2. Hợp đồng DiscoveryClient

DiscoveryClient thuộc package `org.springframework.cloud.client.discovery` trong Spring Cloud Commons. Hai phương thức cốt lõi là:

~~~java
List<String> getServices();

List<ServiceInstance> getInstances(String serviceId);
~~~

DiscoveryClient còn cung cấp thông tin mô tả implementation qua `description()`. Trong các phiên bản Spring Cloud Commons hiện hành, hợp đồng cũng tham gia cơ chế sắp thứ tự `Ordered`, hữu ích khi ứng dụng có nhiều discovery client hoặc dùng composite client. Chi tiết phụ trợ có thể khác theo phiên bản; khi viết mã ứng dụng, hãy dựa trên API của Spring Cloud release train mà dự án đang sử dụng.

| Phương thức | Đầu vào | Kết quả | Dùng khi |
|---|---|---|---|
| `getServices()` | Không có | Danh sách service ID mà client nhìn thấy | Muốn liệt kê các dịch vụ đã được công bố |
| `getInstances(serviceId)` | Service ID | Danh sách instance của dịch vụ đó | Muốn tìm host, port, URI và metadata của một dịch vụ |
| `description()` | Không có | Mô tả implementation | Ghi log hoặc chẩn đoán loại discovery client đang hoạt động |

Điểm cần nhớ:

- `getServices()` trả về tên dịch vụ, không trả về địa chỉ máy chủ. Muốn biết địa chỉ, cần gọi tiếp `getInstances(serviceId)`.
- `getInstances(serviceId)` trả về danh sách vì một service có thể có nhiều bản chạy. Không nên giả định chỉ có một instance.
- Kết quả phụ thuộc dữ liệu mà registry và discovery implementation đang cung cấp. Danh sách có thể thay đổi khi instance đăng ký, ngừng hoạt động hoặc bị loại khỏi registry.
- Không dựa vào thứ tự phần tử để chọn instance. Thứ tự trả về không phải hợp đồng cân bằng tải.

### ServiceInstance chứa những gì?

Mỗi phần tử trong kết quả `getInstances()` là một `ServiceInstance`, thuộc package `org.springframework.cloud.client`. Các thông tin thường dùng gồm:

| Thuộc tính / phương thức | Ý nghĩa |
|---|---|
| `getServiceId()` | Service ID mà instance đăng ký |
| `getHost()` | Host của instance |
| `getPort()` | Port của instance |
| `isSecure()` | Instance có sử dụng kết nối bảo mật hay không |
| `getUri()` | URI kết nối đến instance |
| `getMetadata()` | Metadata dạng key-value do provider hoặc registry cung cấp |
| `getInstanceId()` | ID phân biệt instance nếu implementation cung cấp |

Ưu tiên dùng `getUri()` khi cần URI kết nối. Tự ghép host và port có thể bỏ sót scheme hoặc thông tin bảo mật. Metadata có thể hữu ích cho việc phân loại instance hoặc truyền thuộc tính vận hành, nhưng không nên chứa mật khẩu, token hay bí mật.

## 3. Inject và sử dụng DiscoveryClient

Spring quản lý DiscoveryClient dưới dạng bean khi dependency và cấu hình discovery phù hợp được đưa vào ứng dụng. Consumer có thể inject interface này; nhờ vậy, lớp nghiệp vụ không phải phụ thuộc trực tiếp vào Eureka hay Consul.

~~~java
import java.util.List;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Service;

@Service
public class ServiceCatalog {

    private final DiscoveryClient discoveryClient;

    public ServiceCatalog(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public List<String> listServiceIds() {
        return discoveryClient.getServices();
    }

    public List<ServiceInstance> findInstances(String serviceId) {
        return discoveryClient.getInstances(serviceId);
    }
}
~~~

Lớp trên có hai thao tác tách biệt:

1. `listServiceIds()` lấy các service ID mà discovery client đang nhìn thấy.
2. `findInstances(serviceId)` lấy các bản chạy cụ thể của một service.

Ví dụ gọi từ một thành phần khác:

~~~java
List<String> services = serviceCatalog.listServiceIds();

List<ServiceInstance> instances =
        serviceCatalog.findInstances("inventory-service");

if (instances.isEmpty()) {
    // Chưa tìm thấy instance phù hợp tại thời điểm truy vấn.
} else {
    for (ServiceInstance instance : instances) {
        System.out.println(instance.getServiceId());
        System.out.println(instance.getUri());
        System.out.println(instance.getMetadata());
    }
}
~~~

Khi kết quả rỗng, consumer nên xử lý theo nghiệp vụ: báo service chưa sẵn sàng, trả lỗi có kiểm soát hoặc thử lại theo chính sách phù hợp. Không nên truy cập phần tử đầu tiên mà chưa kiểm tra danh sách.

Nếu expose thông tin discovery qua một API quản trị, hãy chuyển ServiceInstance sang DTO chỉ chứa trường cần thiết. Tránh trả toàn bộ metadata hoặc địa chỉ nội bộ cho người dùng không có quyền xem topology hệ thống.

## 4. DiscoveryClient và ServiceRegistry đảm nhiệm hai chiều khác nhau

Trong Spring Cloud, hai abstraction thường xuất hiện cùng nhau nhưng giải quyết hai việc khác nhau:

| Abstraction | Vai trò | Ví dụ thao tác |
|---|---|---|
| `ServiceRegistry` | Đăng ký, cập nhật trạng thái hoặc hủy đăng ký instance | Provider đăng ký khi khởi động và rời registry khi dừng |
| `DiscoveryClient` | Truy vấn service ID và danh sách instance | Consumer tìm instance của `inventory-service` |

Có thể hình dung:

- **ServiceRegistry là đường ghi**: provider công bố rằng mình cung cấp service nào, ở địa chỉ nào và với metadata nào.
- **DiscoveryClient là đường đọc**: consumer hỏi registry hiện có những service nào và instance nào thuộc service cần tìm.

Trong vòng đời phổ biến, provider khởi động và đăng ký instance; registry nhận heartbeat hoặc chạy health check theo cơ chế của backend; consumer truy vấn discovery client; khi provider dừng, instance được deregister hoặc bị registry loại bỏ sau khi hết thời gian hiệu lực. Cách thực hiện cụ thể phụ thuộc Eureka, Consul và cấu hình triển khai.

Việc có một bản ghi trong registry không đảm bảo request tiếp theo chắc chắn thành công. Instance có thể vừa lỗi, mạng có thể gián đoạn hoặc dữ liệu registry chưa kịp cập nhật. Discovery trả lời câu hỏi “địa chỉ nào đang được công bố”; health check và request thực tế mới cung cấp thêm bằng chứng về khả năng phục vụ.

## 5. Kết hợp với load balancing

DiscoveryClient giúp tìm các instance. Nó không tự biến một lời gọi HTTP thông thường thành lời gọi được cân bằng tải.

Ví dụ, nếu gọi trực tiếp instance đầu tiên:

~~~java
List<ServiceInstance> instances =
        discoveryClient.getInstances("inventory-service");

ServiceInstance selected = instances.get(0);
URI target = selected.getUri();
~~~

Cách làm này chỉ minh họa cách lấy URI. Trong ứng dụng thật, nó có một số vấn đề:

- Danh sách có thể rỗng, khiến truy cập phần tử đầu tiên gây lỗi.
- Instance đầu tiên không nhất thiết là instance khỏe hoặc phù hợp nhất.
- Nhiều consumer có thể cùng chọn một instance, làm tải phân bố không đều.
- Mã gọi phải tự xử lý lựa chọn, cập nhật danh sách và các trường hợp lỗi.

Với lời gọi service-to-service, thường nên dùng Spring Cloud LoadBalancer. Load balancer nhận service ID, lấy danh sách instance từ discovery client và chọn một instance theo chiến lược đang cấu hình.

Ví dụ quen thuộc với RestTemplate:

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

Consumer có thể gọi bằng service ID:

~~~java
restTemplate.getForObject(
        "http://inventory-service/api/items",
        ItemResponse[].class
);
~~~

Để dùng mẫu này, ứng dụng cần dependency Spring Cloud LoadBalancer tương thích với Spring Cloud release train. Tùy phiên bản Spring Boot và loại HTTP client, dự án cũng có thể dùng WebClient hoặc RestClient với tích hợp load balancing tương ứng.

Khi đã dùng load balancer, tránh tự gọi `getInstances()` rồi chọn instance trong từng lớp nghiệp vụ. Hãy để một cơ chế chịu trách nhiệm chọn instance, cache danh sách và áp dụng chính sách retry phù hợp. Retry cần giới hạn và chỉ áp dụng an toàn với loại request tương ứng; retry một thao tác ghi không idempotent có thể tạo tác dụng phụ lặp.

## 6. Khác biệt giữa các backend discovery

DiscoveryClient tạo một điểm truy cập chung, nhưng không làm cho mọi registry có hành vi vận hành giống hệt nhau.

| Backend | Cách cung cấp discovery | Điều cần chú ý |
|---|---|---|
| Eureka | Client đăng ký với Eureka Server và thường gia hạn lease bằng heartbeat | Cache phía client và chu kỳ cập nhật có thể khiến thay đổi chưa xuất hiện ngay |
| Consul | Service được đăng ký vào catalog; health check có thể ảnh hưởng trạng thái được công bố | Kiểm tra chính sách health check và cách truy vấn service khỏe |
| SimpleDiscoveryClient | Dùng danh sách instance cấu hình tĩnh | Phù hợp môi trường đơn giản hoặc kiểm thử; không tự phản ánh vòng đời instance động |

Vì vậy, mã gọi DiscoveryClient nên dựa vào hợp đồng chung, còn cấu hình heartbeat, health check, quyền truy cập registry, thời gian cache và cơ chế deregister cần được kiểm tra theo backend thực tế.

Trong ứng dụng reactive, Spring Cloud Commons còn có abstraction ReactiveDiscoveryClient. Nên chọn API đồng bộ hoặc reactive phù hợp với mô hình xử lý của ứng dụng, tránh chặn event loop bằng lời gọi đồng bộ trong luồng reactive.

## 7. Xử lý kết quả rỗng, registry lỗi và dữ liệu cũ

Khi truy vấn discovery, cần phân biệt các tình huống sau:

| Tình huống | Cách hiểu có thể có | Hướng xử lý |
|---|---|---|
| `getServices()` trả danh sách rỗng | Client chưa thấy service nào | Kiểm tra provider đã đăng ký chưa, service ID và cấu hình discovery |
| `getInstances(id)` trả danh sách rỗng | Không có instance được công bố cho ID đó tại thời điểm truy vấn | Kiểm tra tên service, health check, trạng thái đăng ký và môi trường |
| Truy vấn phát sinh exception hoặc timeout | Registry, mạng, xác thực hoặc provider discovery có vấn đề | Ghi log có ngữ cảnh, đặt timeout và xử lý lỗi theo chính sách |
| Có instance nhưng gọi không được | Bản ghi có thể cũ hoặc endpoint không thể truy cập từ consumer | Kiểm tra health check, mạng, security group, DNS và log của provider |

Danh sách rỗng không đồng nghĩa registry chắc chắn đang hỏng. Ngược lại, một danh sách có instance cũng không chứng minh mọi instance đang khỏe. Cách biểu hiện lỗi cụ thể phụ thuộc implementation; không nên giả định mọi backend đều chuyển lỗi thành danh sách rỗng.

Một số nguyên tắc vận hành:

- Dùng health check và heartbeat/lease phù hợp để registry loại instance không còn phục vụ.
- Cấu hình graceful shutdown để provider deregister khi có thể.
- Đặt timeout cho lời gọi mạng và dùng circuit breaker hoặc fallback khi nghiệp vụ cho phép.
- Theo dõi số lượng instance, thời điểm cập nhật registry, lỗi truy vấn và tỷ lệ request thất bại.
- Không truy vấn registry liên tục ở mọi request nếu load balancer đã quản lý cache và cập nhật danh sách.
- Bảo vệ registry và các API quản trị discovery bằng xác thực, phân quyền và giới hạn mạng truy cập.
- Không đưa thông tin nhạy cảm vào metadata hoặc log đầy đủ cấu hình kết nối.

## 8. Kiểm tra nhanh khi consumer không tìm thấy dịch vụ

Khi `getInstances("inventory-service")` không trả về instance như mong đợi, hãy kiểm tra theo thứ tự:

1. **Đúng service ID chưa?** So sánh tên provider đăng ký với tên consumer truy vấn, bao gồm khác biệt chữ hoa/chữ thường nếu backend có phân biệt.
2. **Provider đã đăng ký chưa?** Kiểm tra log khởi động, cấu hình discovery và trạng thái ứng dụng trên registry.
3. **Instance có qua health check không?** Một instance bị đánh dấu unhealthy có thể không xuất hiện trong kết quả mà consumer sử dụng.
4. **Consumer có kết nối được registry không?** Kiểm tra DNS, network policy, credential, TLS và timeout.
5. **Dữ liệu có đang trễ không?** Kiểm tra chu kỳ heartbeat, refresh và cache ở registry hoặc client.
6. **Endpoint có thể truy cập từ consumer không?** Host và port được công bố phải định tuyến được từ mạng của consumer; địa chỉ nội bộ của provider có thể không dùng được qua ranh giới mạng.

Nên kiểm tra cả log ở provider, registry và consumer. Chỉ nhìn vào danh sách service ở một phía thường chưa đủ để xác định lỗi nằm ở đăng ký, đồng bộ registry hay kết nối mạng.

## 9. Ghi nhớ

- `getServices()` trả danh sách service ID; `getInstances(serviceId)` trả các instance của một service.
- `ServiceInstance` cung cấp URI, host, port, trạng thái secure và metadata để mô tả một bản chạy.
- `ServiceRegistry` phục vụ đăng ký và cập nhật trạng thái; `DiscoveryClient` phục vụ truy vấn.
- Discovery và load balancing là hai trách nhiệm liên quan nhưng khác nhau. Dùng Spring Cloud LoadBalancer cho việc chọn instance khi gọi service.
- Registry có thể trễ hoặc chứa bản ghi cũ. Cần health check, timeout, xử lý lỗi, bảo mật và quan sát vận hành để service discovery hoạt động tin cậy.

Khi hiểu rõ hợp đồng DiscoveryClient, consumer có thể tìm dịch vụ qua Eureka, Consul hoặc implementation khác mà không gắn logic nghiệp vụ với một registry cụ thể.
