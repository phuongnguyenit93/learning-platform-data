# Giới hạn của hợp đồng chung và đặc điểm riêng của từng nhà cung cấp

Spring Cloud cung cấp các abstraction như `DiscoveryClient`, `ServiceInstance`, `Registration` và `ServiceRegistry` để ứng dụng làm việc với service registry thông qua một bộ API tương đối thống nhất. Nhờ đó, phần lớn code consumer có thể tra cứu instance theo service ID mà không cần biết registry đang dùng là Eureka hay Consul.

Tuy nhiên, hợp đồng chung chỉ chuẩn hóa những thao tác và thông tin cơ bản. Nó không biến mọi registry thành một hệ thống có cùng mô hình dữ liệu, cơ chế health check, độ mới của dữ liệu, metadata, chính sách bảo mật hay khả năng vận hành. Khi ứng dụng phụ thuộc vào một đặc điểm riêng của Eureka hoặc Consul, cần nhận diện rõ phần phụ thuộc đó và đặt nó sau một ranh giới phù hợp.

## 1. Hợp đồng chung của Spring Cloud Discovery

Các abstraction discovery thuộc Spring Cloud Commons. Chúng tạo một lớp giao tiếp giữa ứng dụng Spring và implementation cụ thể.

### DiscoveryClient: tra cứu service và instance

`DiscoveryClient` là API phía đọc. Những phương thức thường dùng gồm:

- `getServices()`: lấy các service ID mà implementation hiện tại biết đến.
- `getInstances(serviceId)`: lấy các instance được đăng ký dưới một service ID.
- `description()`: mô tả implementation discovery đang được sử dụng.

Ví dụ consumer chỉ cần biết tên logic `inventory-service`:

```java
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
```

Đoạn code không chứa URL Eureka hay Consul. Implementation được Spring Boot cấu hình thông qua dependency và application properties. Khi đổi implementation, code gọi `DiscoveryClient` thường không phải thay đổi nếu chỉ dùng các khả năng thuộc hợp đồng chung.

`getServices()` hữu ích cho chẩn đoán hoặc màn hình quản trị nội bộ, nhưng không nên xem danh sách này là một danh mục toàn cục có ý nghĩa giống nhau ở mọi provider. Phạm vi dữ liệu có thể phụ thuộc datacenter, namespace, quyền truy cập, cache và cách implementation lọc service.

### ServiceInstance: mô tả một instance

`getInstances(serviceId)` trả về các đối tượng `ServiceInstance`. Các thuộc tính chung thường được sử dụng gồm:

| Thuộc tính/API | Ý nghĩa |
| --- | --- |
| `getServiceId()` | Tên logic của service |
| `getHost()` | Hostname hoặc IP của instance |
| `getPort()` | Cổng instance đang cung cấp |
| `isSecure()` | Cho biết instance dùng kết nối bảo mật theo thông tin mà implementation cung cấp |
| `getUri()` | URI được tạo từ thông tin kết nối của instance |
| `getMetadata()` | Map metadata dạng key/value mà implementation cung cấp |
| `getInstanceId()` | ID instance nếu implementation và phiên bản API cung cấp giá trị này |

Khi tạo request, ưu tiên dùng `getUri()` thay vì tự nối chuỗi host và port. URI có thể phản ánh scheme HTTP/HTTPS và cách implementation mô tả địa chỉ. Nếu tự ghép URL, code dễ bỏ qua `isSecure()`, IPv6, port mặc định hoặc quy tắc URI.

Ví dụ chuyển kết quả discovery thành dữ liệu hiển thị:

```java
import java.net.URI;
import java.util.List;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Service;

@Service
public class InstanceInspector {

    private final DiscoveryClient discoveryClient;

    public InstanceInspector(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public List<String> describe(String serviceId) {
        return discoveryClient.getInstances(serviceId)
                .stream()
                .map(this::format)
                .toList();
    }

    private String format(ServiceInstance instance) {
        URI uri = instance.getUri();
        return instance.getServiceId() + " -> " + uri
                + ", metadata=" + instance.getMetadata();
    }
}
```

Metadata là một map key/value chung, nhưng tên key, ý nghĩa, kiểu dữ liệu được mã hóa và cách cập nhật vẫn do provider quyết định. Không nên giả định mọi provider đều có cùng tập key như `zone`, `version`, `weight` hoặc `health`.

### ServiceRegistry và Registration: đăng ký instance

`ServiceRegistry` là abstraction phía ghi. Nó định nghĩa các thao tác vòng đời như đăng ký, hủy đăng ký, xem hoặc cập nhật trạng thái registration. `Registration` mô tả thông tin cần thiết để một implementation đăng ký instance. Kiểu registration cụ thể phụ thuộc provider.

Phân biệt hai nhóm API:

| Abstraction | Vai trò chính | Phía sử dụng thường gặp |
| --- | --- | --- |
| `DiscoveryClient` | Đọc service ID và danh sách instance | Consumer, công cụ quan sát |
| `ServiceInstance` | Mô tả địa chỉ và metadata của instance | Consumer, LoadBalancer |
| `Registration` | Mang thông tin đăng ký của một instance | Provider/registration lifecycle |
| `ServiceRegistry` | Đăng ký, hủy đăng ký và quản lý trạng thái | Provider, lifecycle integration |

Spring Cloud có thể tự đăng ký ứng dụng khi khởi động và hủy đăng ký khi dừng thông qua auto-configuration. Vì vậy, ứng dụng không nhất thiết phải gọi `ServiceRegistry.register()` bằng tay. Chỉ gọi thủ công khi có yêu cầu quản lý vòng đời đặc biệt và đã hiểu cách implementation tích hợp với auto-registration; đăng ký hai lần có thể tạo dữ liệu trùng hoặc xung đột instance ID.

## 2. Những điều hợp đồng chung không cam kết

Các abstraction làm code bớt phụ thuộc vendor, nhưng không bảo đảm mọi khác biệt về hành vi đều biến mất.

| Khía cạnh | Hợp đồng chung cung cấp | Điều không nên giả định |
| --- | --- | --- |
| Tra cứu | Service ID và danh sách `ServiceInstance` | Mọi provider trả cùng danh sách tại cùng một thời điểm |
| Thứ tự | Một collection các instance | Thứ tự trả về ổn định hoặc đã được cân bằng tải |
| Độ mới | Dữ liệu mà implementation hiện có | Kết quả luôn là trạng thái tức thời từ server authoritative |
| Health | Thông tin instance do implementation công bố | `passing` của Consul tương đương chính xác với trạng thái Eureka |
| Metadata | Map key/value | Cùng key, cùng schema, cùng quy tắc mã hóa ở mọi provider |
| Định danh | Service ID và thông tin instance cơ bản | Quy tắc chuẩn hóa tên và instance ID giống nhau |
| Phạm vi | Service ID được implementation trả về | Mọi datacenter, namespace hoặc partition đều nằm trong cùng một kết quả |
| Load balancing | Có thể kết hợp với Spring Cloud LoadBalancer | `DiscoveryClient` tự chọn instance hoặc bảo đảm request thành công |
| Bảo mật | Tích hợp thông qua cấu hình và implementation | ACL, authentication, TLS và quyền truy vấn giống nhau |
| Vòng đời | API registration chung | Mọi registry có cùng lease, heartbeat, deregistration hoặc eviction |

Điểm quan trọng là `DiscoveryClient` chỉ trả dữ liệu discovery. Nó không cam kết instance sẽ còn sống khi request thực sự đến nơi, không tự thực hiện retry nghiệp vụ và không bảo đảm registry đã hội tụ sau một sự cố mạng. Consumer vẫn cần timeout, xử lý lỗi kết nối và chính sách retry phù hợp.

## 3. DiscoveryClient không phải LoadBalancer

Một hiểu nhầm thường gặp là gọi `DiscoveryClient.getInstances()` đồng nghĩa với việc đã cân bằng tải. Thực tế hai nhiệm vụ này khác nhau:

1. Discovery tìm các instance thuộc service ID.
2. LoadBalancer chọn một instance từ danh sách phù hợp với request.
3. HTTP client gửi request đến URI của instance đã chọn.

Ứng dụng có thể lấy danh sách instance trực tiếp để hiển thị hoặc chẩn đoán:

```java
List<ServiceInstance> instances = discoveryClient.getInstances("inventory-service");
```

Nhưng trong đường gọi dịch vụ thông thường, nên để Spring Cloud LoadBalancer tích hợp với HTTP client xử lý việc chọn instance. Không nên tự lấy phần tử đầu tiên của danh sách vì thứ tự không phải hợp đồng cân bằng tải.

Ví dụ với `RestTemplate`:

```java
@Configuration
class HttpClientConfiguration {

    @Bean
    @LoadBalanced
    RestTemplate restTemplate() {
        return new RestTemplate();
    }
}
```

Khi dùng bean này, URL có host là service ID, chẳng hạn `http://inventory-service/api/items/42`, được xử lý qua LoadBalancer. Cần có implementation discovery và dependency LoadBalancer tương thích. Nếu tạo `RestTemplate` thông thường không có `@LoadBalanced`, tên service có thể bị xử lý như hostname DNS và request thất bại.

LoadBalancer có thể dùng các thành phần như `ServiceInstanceListSupplier` để lấy danh sách instance, áp dụng cache hoặc lọc theo thuộc tính. Cấu hình chi tiết của supplier, zone preference, retry và thuật toán chọn instance có thể khác nhau theo phiên bản Spring Cloud và ứng dụng.

## 4. Đặc điểm riêng của Eureka

Eureka là registry theo mô hình application và instance. Một application có thể có nhiều instance; client đăng ký instance, gửi heartbeat để gia hạn lease và tải registry để tra cứu service.

### Định danh và metadata

Trong Eureka, các thuộc tính thường quan tâm gồm:

- Application name: tên ứng dụng/service mà client đăng ký.
- Instance ID: định danh riêng của một instance trong application.
- Hostname/IP và port: địa chỉ được Eureka quảng bá.
- Metadata map: các cặp key/value do ứng dụng cấu hình.
- Status và các URL liên quan đến instance: trạng thái, health/status page nếu được cấu hình.

Ví dụ cấu hình metadata cho một Eureka client:

```yaml
spring:
  application:
    name: inventory-service

server:
  port: 8084

eureka:
  instance:
    prefer-ip-address: true
    instance-id: ${spring.application.name}:${spring.cloud.client.ip-address}:${server.port}
    metadata-map:
      version: "2.1"
      zone: "zone-a"
      team: "warehouse"
```

Consumer có thể đọc metadata qua `ServiceInstance.getMetadata()`, nếu implementation Eureka ánh xạ các trường đó vào map chung. Tuy vậy, tên thuộc tính cấu hình `metadata-map` là đặc điểm của Eureka client. Không nên yêu cầu một cấu hình Consul có cùng tên.

### Heartbeat, lease và self-preservation

Eureka client gửi heartbeat định kỳ để gia hạn lease. Nếu heartbeat ngừng, server có thể đánh dấu hoặc loại instance sau thời hạn lease và quy trình eviction. Cơ chế self-preservation giúp hạn chế xóa hàng loạt instance khi server nhận ít heartbeat bất thường, ví dụ trong một sự cố mạng diện rộng.

Do đó, trạng thái instance trên Eureka chịu ảnh hưởng của heartbeat, lease, eviction và self-preservation. Đây là mô hình khác với việc Consul agent thực hiện các health check HTTP/TCP/script và công bố trạng thái check.

### Vùng và cấu hình peer

Eureka có khái niệm region và availability zone cùng cấu hình danh sách server theo vùng. Client có thể ưu tiên registry trong vùng gần nó tùy cấu hình. Cụm Eureka peer trao đổi registry với nhau và có thể tạm thời không đồng nhất trong thời gian mạng gián đoạn. Việc đọc từ một peer không nên được xem là bằng chứng rằng mọi peer đã có cùng trạng thái tại đúng thời điểm đó.

Khi cần các chức năng riêng của Eureka như đọc application/instance theo API Netflix, lấy thông tin server cụ thể, điều chỉnh zone preference hoặc quan sát trạng thái peer, abstraction `DiscoveryClient` có thể không đủ. Khi đó cần dùng API hoặc properties riêng của Eureka, được cô lập trong một adapter.

## 5. Đặc điểm riêng của Consul

Consul tổ chức discovery quanh service catalog, node, service instance và health check. Ứng dụng Spring Cloud Consul thường giao tiếp với Consul agent; agent quản lý đăng ký và check tại node rồi đồng bộ dữ liệu với server cluster.

### Service name, instance ID, tags và metadata

Consul cung cấp tags và metadata cho service. Spring Cloud Consul ánh xạ cấu hình discovery của nó vào đăng ký Consul. Ví dụ:

```yaml
spring:
  application:
    name: inventory-service
  cloud:
    consul:
      host: localhost
      port: 8500
      discovery:
        register: true
        service-name: inventory-service
        instance-id: ${spring.application.name}:${spring.cloud.client.hostname}:${server.port}
        tags:
          - "version=2.1"
          - "team=warehouse"
        metadata:
          release: "2026.11"
          protocol: "http"
        health-check-path: /actuator/health
        health-check-interval: 15s

server:
  port: 8084
```

Trong ví dụ này, `service-name`, `instance-id`, `tags`, `metadata` và health-check properties là cấu hình Spring Cloud Consul. Consul catalog có khái niệm tag và metadata riêng; khi chuyển sang Eureka, cần ánh xạ có chủ đích thay vì mong đợi mọi field được giữ nguyên tự động.

### Health check là một phần quan trọng của Consul

Consul agent có thể chạy HTTP, TCP, gRPC hoặc script check tùy cấu hình và phiên bản. Trạng thái check phổ biến gồm `passing`, `warning` và `critical`. Truy vấn health service có thể lọc chỉ những instance đang `passing`.

Ví dụ Spring Cloud Consul khai báo HTTP check đến `/actuator/health`. Agent phải truy cập được địa chỉ và port của ứng dụng. Nếu app bind vào loopback trong một container riêng, agent bên ngoài container có thể không gọi được endpoint đó dù gọi từ trong app vẫn thành công.

Consul còn có các phạm vi và tính năng như datacenter, ACL, namespace hoặc partition tùy edition/cấu hình. Một `DiscoveryClient` đơn giản không thể diễn đạt đầy đủ mọi lựa chọn định tuyến và phạm vi đó.

### Catalog và API riêng của Consul

Khi cần truy vấn theo tag, lọc theo trạng thái health, chọn datacenter, thao tác KV hoặc kiểm soát ACL, cần dùng các thuộc tính hoặc API riêng của Consul. `DiscoveryClient.getInstances(serviceId)` chỉ biểu diễn yêu cầu tra cứu cơ bản theo service ID; nó không có tham số chung để truyền mọi bộ lọc Consul.

## 6. So sánh Eureka và Consul dưới góc nhìn hợp đồng chung

| Chủ đề | Eureka | Consul | Hệ quả khi dùng abstraction chung |
| --- | --- | --- | --- |
| Mô hình dữ liệu | Application và instance | Node, service, service instance và catalog | Cùng trả `ServiceInstance`, nhưng nguồn gốc và trường dữ liệu khác nhau |
| Đăng ký | Client registration và heartbeat | Agent nhận registration và quản lý service/check | Vòng đời phía sau API khác nhau |
| Health | Heartbeat/lease, eviction, self-preservation | Agent thực hiện health check và cập nhật trạng thái | Không quy đổi trạng thái một-một |
| Metadata | Metadata map của instance | Tags và metadata của service | Cần thống nhất schema ở tầng ứng dụng |
| Định danh | Application name và instance ID | Service name, node và service ID/instance ID | Quy tắc duy nhất và chuẩn hóa có thể khác |
| Phân vùng | Region và availability zone | Datacenter; namespace/partition tùy cấu hình | Service ID không mô tả toàn bộ phạm vi tìm kiếm |
| Peer/cluster | Peer replication, eventual consistency | Agent/server cluster, catalog và các chế độ truy vấn | Độ mới dữ liệu và topology không giống nhau |
| Bảo mật | Cấu hình xác thực/TLS tùy triển khai | ACL, token, TLS và policy | Cấu hình và quyền không thể chuyển nguyên xi |
| API mở rộng | Eureka client/server API | Consul HTTP API, catalog, health, KV | Tính năng riêng cần adapter riêng |

Bảng này không nói provider nào tốt hơn. Nó cho thấy cùng một thao tác discovery cơ bản có thể được thực hiện bằng các cơ chế và ngữ nghĩa khác nhau. Việc lựa chọn cần dựa trên yêu cầu về topology, health, consistency, bảo mật, vận hành và hệ sinh thái hiện có.

## 7. Thiết kế ứng dụng khi cần tính năng riêng của provider

Không nên để code nghiệp vụ gọi API native của Eureka hoặc Consul ở khắp nơi. Nếu ứng dụng thực sự cần một khả năng không có trong hợp đồng chung, hãy tạo một interface ở tầng ứng dụng mô tả đúng nhu cầu nghiệp vụ, rồi triển khai adapter theo provider.

Ví dụ, giả sử hệ thống cần tìm các instance khỏe mạnh theo một phiên bản dịch vụ:

```java
public interface VersionedServiceLocator {

    List<ServiceInstance> findHealthyInstances(
            String serviceId,
            String version
    );
}
```

Một adapter có thể dùng Eureka metadata để lọc `version`; adapter khác có thể dùng Consul health query và tags/metadata. Controller và service nghiệp vụ chỉ gọi `VersionedServiceLocator`, không biết chi tiết API vendor.

Không nên viết một adapter giả định mọi provider có cùng khái niệm “healthy”. Adapter cần xác định rõ cách provider đánh giá health, nguồn dữ liệu, thời gian cập nhật và hành vi khi registry không truy cập được. Nếu hai provider không có khả năng tương đương, interface nên thể hiện sự khác biệt hoặc ứng dụng cần chọn một provider có chủ đích.

### Ví dụ lọc metadata từ hợp đồng chung

Nếu version đã được ánh xạ vào `ServiceInstance.getMetadata()`, có thể lọc trong code chung:

```java
public List<ServiceInstance> findByVersion(
        DiscoveryClient discoveryClient,
        String serviceId,
        String expectedVersion) {

    return discoveryClient.getInstances(serviceId).stream()
            .filter(instance -> expectedVersion.equals(
                    instance.getMetadata().get("version")))
            .toList();
}
```

Đoạn code chỉ portable khi mọi implementation đều đăng ký cùng key `version` với cùng ý nghĩa và định dạng. Việc đặt tên key đó là một quy ước của ứng dụng, không phải quy tắc tự động của Spring Cloud. Cần bảo đảm provider nào cũng ghi metadata trước khi consumer lọc theo key này.

Nếu cần lọc health theo cơ chế riêng, truy vấn theo datacenter, region, zone hoặc tag phức tạp, hãy dùng adapter thay vì nhồi logic provider-specific vào một hàm chung.

## 8. Cache, độ mới dữ liệu và xử lý lỗi

Hợp đồng `DiscoveryClient` không quy định một độ trễ cập nhật duy nhất cho mọi implementation. Registry có thể cache danh sách ở client, đồng bộ giữa peer hoặc trả kết quả theo chế độ consistency riêng. Vì vậy:

- Kết quả `getInstances()` có thể cũ hơn trạng thái thực tế của ứng dụng.
- Instance vừa khởi động có thể chưa xuất hiện ngay trong mọi consumer.
- Instance đã dừng có thể còn trong cache một khoảng thời gian.
- Health check thành công không bảo đảm ứng dụng xử lý được mọi request nghiệp vụ.
- Một danh sách rỗng có thể do service chưa đăng ký, sai service ID, phạm vi truy vấn, quyền truy cập hoặc lỗi kết nối registry.

Consumer nên xử lý các tình huống này bằng timeout, retry có giới hạn, circuit breaker và logging có service ID/instance URI. Retry cần tránh tạo tải lớn hơn khi registry hoặc provider đang gặp sự cố. Với thao tác không idempotent, phải có cơ chế chống thực hiện lặp trước khi tự động retry.

Không nên giữ một `ServiceInstance` vô thời hạn rồi dùng lại như địa chỉ bất biến. Nếu ứng dụng cần cache riêng, phải có thời hạn và chính sách refresh phù hợp, hoặc sử dụng cơ chế cache/refresh do Spring Cloud LoadBalancer hỗ trợ ở phiên bản dự án.

## 9. Lựa chọn API chung hay API riêng

| Nhu cầu | Hướng xử lý phù hợp |
| --- | --- |
| Lấy instance theo service ID | Dùng `DiscoveryClient` |
| Đọc host, port, URI và metadata cơ bản | Dùng `ServiceInstance` |
| Gọi service và chọn instance | Dùng Spring Cloud LoadBalancer cùng HTTP client |
| Đăng ký/hủy đăng ký theo lifecycle chuẩn | Để auto-configuration quản lý hoặc dùng `ServiceRegistry` khi cần |
| Lọc metadata theo schema do ứng dụng quy ước | Dùng `getMetadata()` sau khi chuẩn hóa key/value |
| Chọn theo tag hoặc trạng thái Consul cụ thể | Dùng adapter/API Consul |
| Đọc application, zone hoặc trạng thái peer đặc thù Eureka | Dùng adapter/API Eureka |
| Cần hành vi tương đương khi chuyển provider | Xác định tập tính năng giao nhau và kiểm thử contract trên từng implementation |

Một nguyên tắc hữu ích là giữ phần lớn luồng gọi dịch vụ ở abstraction chung, chỉ mở rộng sang API riêng tại nơi có yêu cầu cụ thể. Điều này giữ code consumer dễ thay đổi mà không che giấu những khác biệt ảnh hưởng trực tiếp đến tính đúng đắn.

## 10. Kiểm thử khả năng tương thích giữa các provider

Nếu một ứng dụng dự định hỗ trợ nhiều registry, nên có contract test chạy với từng implementation. Test không chỉ xác nhận bean `DiscoveryClient` tồn tại mà cần kiểm tra hành vi mà ứng dụng thực sự phụ thuộc.

Ví dụ các tình huống kiểm thử:

1. Đăng ký provider với service ID đã thống nhất.
2. Tra cứu service ID và xác nhận có ít nhất một instance.
3. Kiểm tra URI trả về có scheme, host và port đúng với môi trường test.
4. Kiểm tra metadata ứng dụng yêu cầu có cùng key và định dạng.
5. Đánh dấu instance không khỏe theo cách provider hỗ trợ và xác nhận consumer không chọn nó theo chính sách đã định.
6. Dừng provider hoặc ngắt kết nối registry, sau đó quan sát thời gian phát hiện và hành vi consumer.
7. Khởi động lại provider và xác nhận registry/consumer hội tụ trong giới hạn thời gian chấp nhận được.

Không nên viết một test kỳ vọng cùng một thời gian phát hiện lỗi hoặc cùng trạng thái trung gian cho Eureka và Consul nếu hai provider có cấu hình health/lease khác nhau. Hãy kiểm tra yêu cầu quan sát được của ứng dụng, đồng thời đặt ngưỡng phù hợp cho từng implementation.

## 11. Các lỗi thiết kế thường gặp

| Cách làm | Rủi ro | Cách cải thiện |
| --- | --- | --- |
| Dùng `getInstances().get(0)` để cân bằng tải | Phụ thuộc thứ tự không được bảo đảm | Dùng Spring Cloud LoadBalancer |
| Coi metadata là schema chung của mọi registry | Thiếu key hoặc khác ý nghĩa khi đổi provider | Định nghĩa schema ứng dụng và kiểm thử adapter |
| Coi health status các provider là tương đương | Có thể gọi nhầm instance không đạt yêu cầu | Chuẩn hóa chính sách health ở tầng ứng dụng |
| Ghi cứng URL native của Eureka/Consul trong code nghiệp vụ | Khó chuyển implementation và khó test | Dùng abstraction hoặc adapter có phạm vi rõ |
| Dùng `localhost` làm địa chỉ quảng bá trong container | Consumer khác không kết nối được | Quảng bá hostname/IP có thể định tuyến |
| Giữ instance URI trong cache vô thời hạn | Dùng địa chỉ đã bị thay thế hoặc deregister | Dùng refresh/TTL và xử lý lỗi kết nối |
| Cho rằng danh sách rỗng chắc chắn là service chưa chạy | Bỏ sót lỗi quyền, phạm vi hoặc kết nối registry | Kiểm tra log, registry URL, scope và credentials |
| Dùng cùng một instance ID cho nhiều replica | Registration có thể ghi đè hoặc xung đột | Kết hợp hostname/IP, port hoặc ID duy nhất |

## 12. Checklist khi sử dụng DiscoveryClient

- [ ] Code chỉ dùng `DiscoveryClient` cho thao tác tra cứu cơ bản.
- [ ] Code dùng `ServiceInstance.getUri()` khi cần địa chỉ gọi dịch vụ.
- [ ] Không dựa vào thứ tự danh sách instance để chọn server.
- [ ] Load balancing được giao cho Spring Cloud LoadBalancer hoặc thành phần tương đương.
- [ ] Metadata có schema do ứng dụng quy định và được mọi provider ghi đúng.
- [ ] Đã xác định cách từng provider đánh giá health và loại instance lỗi.
- [ ] Đã xác định phạm vi discovery như region, zone hoặc datacenter.
- [ ] API native của Eureka/Consul được cô lập trong adapter.
- [ ] Consumer xử lý dữ liệu cũ, danh sách rỗng, timeout và lỗi registry.
- [ ] Contract test chạy với từng provider mà ứng dụng tuyên bố hỗ trợ.

`DiscoveryClient` giúp ứng dụng Spring Cloud có một điểm chung để tìm service instance. Giá trị của abstraction này nằm ở việc giảm phụ thuộc vào API cụ thể trong luồng nghiệp vụ thông thường. Khi cần health semantics, metadata, topology hoặc khả năng quản trị riêng của nhà cung cấp, ứng dụng phải làm rõ khác biệt đó và tích hợp có chủ đích. Một thiết kế tốt giữ phần giao tiếp cơ bản ở hợp đồng chung, đồng thời bảo toàn các đặc điểm quan trọng của provider qua adapter và contract test.
