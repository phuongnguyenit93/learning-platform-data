# Lọc bản sao theo vùng bằng zone preference

Khi một dịch vụ có nhiều bản sao chạy ở các availability zone khác nhau, client-side load balancing không nhất thiết nên phân phối request đều cho tất cả bản sao trên toàn khu vực. Những request vượt zone có thể tăng độ trễ, chi phí truyền dữ liệu hoặc phụ thuộc vào hạ tầng mạng liên vùng. **Zone preference** là chính sách ưu tiên chọn bản sao nằm trong cùng vùng với ứng dụng gọi, nhưng vẫn có khả năng sử dụng vùng khác khi không tìm thấy bản sao cùng vùng.

Trong Spring Cloud LoadBalancer, cơ chế này được cung cấp bởi **ZonePreferenceServiceInstanceListSupplier**. Nó không phải thuật toán thay thế Round Robin hoặc Random: nó **lọc danh sách ứng viên trước**, sau đó LoadBalancer chọn một instance từ danh sách đã lọc.

Bài học tập trung vào cách gắn zone cho ServiceInstance, cách xác định zone của client, cơ chế lọc và fallback, cấu hình ServiceInstanceListSupplier, tác động với cache/health check và những giới hạn cần biết khi định tuyến nhiều vùng.

## 1. Vì sao cần ưu tiên instance cùng zone?

Giả sử hệ thống bán hàng có **Order Service** gọi **Inventory Service**. Mỗi dịch vụ được triển khai trên nhiều instance ở hai vùng hạ tầng:

| Service | Instance | Zone | Địa chỉ minh họa |
| --- | --- | --- | --- |
| Order Service | order-1 | zone-a | 10.10.1.11:8080 |
| Inventory Service | inventory-a1 | zone-a | 10.10.1.21:8080 |
| Inventory Service | inventory-a2 | zone-a | 10.10.1.22:8080 |
| Inventory Service | inventory-b1 | zone-b | 10.10.2.31:8080 |

Nếu không có lọc theo zone, một LoadBalancer Round Robin có thể đưa request từ order-1 lần lượt đến a1, a2 rồi b1. Nếu bật zone preference và ứng dụng gọi được cấu hình ở **zone-a**, LoadBalancer ưu tiên tập **[a1, a2]**. Instance b1 chỉ trở lại danh sách ứng viên khi không có instance zone-a phù hợp trong dữ liệu đầu vào của bộ lọc.

Lợi ích có thể đạt được:

- **Giảm độ trễ:** đường mạng trong cùng zone thường có ít hop hoặc được tối ưu tốt hơn.
- **Giảm lưu lượng liên zone:** có thể giảm chi phí truyền dữ liệu hoặc tải lên liên kết giữa các zone.
- **Tối ưu locality:** giữ phần lớn request gần ứng dụng gọi khi hệ thống có đủ năng lực ở zone đó.
- **Tăng tính linh hoạt khi thiếu năng lực cục bộ:** fallback cho phép thử các instance ở zone khác thay vì bắt buộc từ chối request.

Đây là các lợi ích *có điều kiện*, không phải cam kết. Một instance cùng zone nhưng đang quá tải có thể chậm hơn instance khác zone. Zone preference không tự đo RTT, bandwidth, CPU, số kết nối hay chi phí thực tế; nó sử dụng **nhãn metadata** đã được cấu hình.

### Zone không đồng nghĩa với region hay cluster

Các thuật ngữ hạ tầng cần phân biệt:

| Thuật ngữ | Ví dụ | Vai trò |
| --- | --- | --- |
| Region | ap-southeast-1 | Khu vực địa lý/hạ tầng lớn |
| Availability zone | zone-a, zone-b | Phân vùng độc lập trong region hoặc cụm |
| Kubernetes node | worker-01 | Máy chạy pod; một node có thể thuộc một zone |
| ServiceInstance | inventory-a1 | Bản sao ứng dụng có host/port/metadata |
| Client zone | zone-a | Zone mà ứng dụng gọi muốn ưu tiên |

Spring Cloud LoadBalancer không suy diễn region từ service ID hoặc địa chỉ IP. Trong cơ chế zone preference cơ bản, việc so khớp phụ thuộc vào **giá trị zone của client** và **metadata zone của instance**.

## 2. Hai nguồn thông tin bắt buộc: client zone và instance zone

Để lọc có tác dụng, cần trả lời hai câu hỏi:

1. **Client đang muốn ưu tiên zone nào?**
2. **Mỗi ServiceInstance được ghi nhận thuộc zone nào?**

Spring Cloud hỗ trợ cấu hình zone của client bằng:

~~~yaml
spring:
  cloud:
    loadbalancer:
      zone: zone-a
~~~

Giá trị này là zone mà **ứng dụng thực hiện lời gọi** dùng làm tiêu chí lọc. Trong môi trường nhiều bản sao của chính caller, mỗi bản sao nên nhận zone tương ứng với nơi nó được triển khai, ví dụ qua profile hoặc biến môi trường.

Với instance được khám phá, ZonePreferenceServiceInstanceListSupplier lấy zone từ:

~~~java
String instanceZone = serviceInstance.getMetadata().get("zone");
~~~

Metadata của ba instance có thể như sau:

~~~text
inventory-a1  metadata = {"zone": "zone-a", "version": "v2"}
inventory-a2  metadata = {"zone": "zone-a", "version": "v2"}
inventory-b1  metadata = {"zone": "zone-b", "version": "v2"}
~~~

**Chú ý:** tên khóa phải là **zone** trong map metadata của ServiceInstance. Một giá trị nằm ở nhãn Kubernetes, metadata key khác hoặc cấu hình riêng của registry không tự động được ZonePreference sử dụng nếu integration không ánh xạ nó vào đúng khóa này.

### 2.1. Hai cấu hình không thay thế lẫn nhau

| Nơi cấu hình | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Caller | spring.cloud.loadbalancer.zone=zone-a | Ưu tiên bản sao ở zone-a |
| Provider (Eureka) | eureka.instance.metadata-map.zone=zone-a | Đăng ký instance có metadata zone-a |
| Discovery data | ServiceInstance.getMetadata().get("zone") | Dữ liệu thực sự được bộ lọc so khớp |

Nếu chỉ cấu hình zone ở caller nhưng các instance không có metadata zone, bộ lọc sẽ **không tìm thấy bất cứ bản sao cùng zone nào** và fallback về toàn bộ danh sách. Nếu chỉ gắn zone ở provider nhưng caller không xác định zone ưu tiên, kết quả cũng không được lọc theo một vùng cụ thể.

## 3. ZonePreferenceServiceInstanceListSupplier lọc như thế nào?

Lớp **ZonePreferenceServiceInstanceListSupplier** thuộc gói **org.springframework.cloud.loadbalancer.core**. Nó là một decorator của ServiceInstanceListSupplier, tức nhận danh sách từ supplier bên trong rồi áp dụng chính sách zone trước khi chuyển danh sách tới LoadBalancer.

Logic trọng tâm của implementation hiện hành có thể diễn giải thành mã giả:

~~~java
List<ServiceInstance> filterByZone(
        List<ServiceInstance> input,
        String preferredZone) {

    if (preferredZone == null) {
        return input;
    }

    List<ServiceInstance> matches = input.stream()
            .filter(instance ->
                    preferredZone.equalsIgnoreCase(
                            instance.getMetadata().get("zone")))
            .toList();

    return matches.isEmpty() ? input : matches;
}
~~~

Đây là **mã minh họa rút gọn hành vi**, không phải API công khai được gọi từ ứng dụng. Implementation thật cũng xử lý việc đọc cấu hình zone và chuyển tiếp Request trong supplier chain.

Ba quy tắc quan trọng:

1. Có zone ưu tiên và **ít nhất một instance khớp**: trả về **chỉ những instance khớp zone**.
2. **Không cấu hình zone của client**: trả về nguyên danh sách delegate.
3. **Có zone ưu tiên nhưng không có instance nào khớp**: trả về nguyên danh sách delegate, **không trả danh sách rỗng**.

So khớp giá trị zone dùng **equalsIgnoreCase** trong implementation được tham chiếu. Tuy vậy, cần giữ quy ước tên nhất quán: không nên phụ thuộc vào việc tự loại khoảng trắng, alias hoặc chuẩn hóa tên zone, vì các thao tác này không thuộc logic lọc cơ bản.

### 3.1. Bảng kết quả mẫu

Giả sử đầu vào từ discovery là **[A(zone-a), B(zone-a), C(zone-b), D(không có zone)]**:

| Zone của caller | Kết quả sau ZonePreference | Giải thích |
| --- | --- | --- |
| zone-a | [A, B] | Có hai instance cùng zone |
| zone-b | [C] | Có một instance cùng zone |
| zone-c | [A, B, C, D] | Không match, fallback về toàn bộ đầu vào |
| Không cấu hình | [A, B, C, D] | Không có tiêu chí zone để lọc |
| ZONE-A | [A, B] | Giá trị khớp không phân biệt hoa/thường |

Nếu đầu vào từ discovery là danh sách rỗng **[]**, ZonePreference cũng trả **[]**. Nó không tự tạo instance, không làm mới service registry và không quyết định lỗi HTTP sẽ trả về.

### 3.2. Zone preference khác strict zone affinity

Tên **preference** có ý nghĩa chính xác: đây là **ưu tiên mềm (soft preference)**, không phải giới hạn cứng:

~~~text
Client zone-a
    |
    +-- Có [A(zone-a), B(zone-a)]? --> chỉ trả [A, B]
    |
    +-- Không có instance zone-a? --> trả tất cả instance delegate
                                      (bao gồm zone-b, zone-c, ...)
~~~

Không dùng bộ lọc này như một kiểm soát bắt buộc về chủ quyền dữ liệu, pháp lý, phân vùng tenant hoặc cô lập bảo mật. Nếu **tuyệt đối không được gọi ngoài zone**, cần chính sách lọc cứng hoặc một lớp route/security riêng có khả năng từ chối khi không có instance đúng zone.

## 4. Đặt zone preference trong chuỗi chọn instance

~~~mermaid
flowchart TD
    A["RestClient / WebClient / OpenFeign"] --> B["LoadBalancer theo service ID"]
    B --> C["ServiceInstanceListSupplier"]
    C --> D["DiscoveryClient / ReactiveDiscoveryClient"]
    D --> E["Danh sách instance"]
    E --> F["Cache hoặc HealthCheck"]
    F --> G["ZonePreference: lọc metadata zone"]
    G --> H{"Có ứng viên cùng zone?"}
    H -->|Có| I["Chỉ danh sách same-zone"]
    H -->|Không| J["Fallback: giữ danh sách delegate"]
    I --> K["RoundRobin / Random chọn instance"]
    J --> K
    K --> L["Tái dựng URI host/port"]
    L --> M["Gửi HTTP request"]
~~~

Ví dụ theo từng bước:

~~~text
Request: GET http://inventory-service/api/stock/BOOK-01
Client zone: zone-a

Discovery:            [inventory-a1, inventory-a2, inventory-b1]
Cache:                [inventory-a1, inventory-a2, inventory-b1]
ZonePreference:       [inventory-a1, inventory-a2]
RoundRobin:           inventory-a1  (tùy vị trí bộ đếm hiện tại)
URI vật lý:           http://10.10.1.21:8080/api/stock/BOOK-01
~~~

Lần request kế tiếp có thể chọn inventory-a2. **ZonePreference không bảo đảm luân phiên a1 rồi a2**; RoundRobin mới là thành phần xác định vị trí chọn, và thứ tự/chính sách có thể bị ảnh hưởng bởi các supplier khác.

## 5. Cấu hình builder để bật zone preference

Spring Cloud LoadBalancer **không tự áp dụng zone preference chỉ vì application.yml có spring.cloud.loadbalancer.zone**. Cần dùng ZonePreferenceServiceInstanceListSupplier, thường được tạo qua **ServiceInstanceListSupplier.builder()**.

### 5.1. Ví dụ với discovery blocking

Phù hợp khi nguồn instance dùng DiscoveryClient đồng bộ, chẳng hạn SimpleDiscoveryClient trong môi trường local:

~~~java
import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

class InventoryZoneLoadBalancerConfiguration {

    @Bean
    ServiceInstanceListSupplier inventoryServiceInstanceListSupplier(
            ConfigurableApplicationContext context) {

        return ServiceInstanceListSupplier.builder()
                .withBlockingDiscoveryClient()
                .withCaching()
                .withZonePreference()
                .build(context);
    }
}
~~~

Với thứ tự này, dữ liệu đi theo tuyến:

~~~text
Discovery -> Cache -> ZonePreference -> LoadBalancer
~~~

Mặc dù khi đọc theo quan hệ delegate, ZonePreference là wrapper ngoài cùng, nó **áp dụng phép lọc sau khi** Cache đã cung cấp danh sách instance. Đây là thứ tự được tài liệu Spring Cloud khuyến nghị: đặt cache ngay sau nguồn discovery, rồi đến các supplier lọc theo chính sách.

### 5.2. Ví dụ với reactive discovery

Khi provider hỗ trợ ReactiveDiscoveryClient:

~~~java
class InventoryReactiveZoneLoadBalancerConfiguration {

    @Bean
    ServiceInstanceListSupplier inventoryServiceInstanceListSupplier(
            ConfigurableApplicationContext context) {

        return ServiceInstanceListSupplier.builder()
                .withDiscoveryClient()
                .withCaching()
                .withZonePreference()
                .build(context);
    }
}
~~~

Trong builder này, **withDiscoveryClient()** chọn nguồn ReactiveDiscoveryClient, còn **withBlockingDiscoveryClient()** chọn nguồn DiscoveryClient. Không nhầm hai API chỉ vì cả hai cuối cùng đều cung cấp một danh sách ServiceInstance.

### 5.3. Gắn cấu hình cho một service ID

Để chỉ áp dụng supplier cho inventory-service:

~~~java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.loadbalancer.annotation.LoadBalancerClient;

@SpringBootApplication
@LoadBalancerClient(
        name = "inventory-service",
        configuration = InventoryZoneLoadBalancerConfiguration.class)
class OrderApplication {
}
~~~

Lớp **InventoryZoneLoadBalancerConfiguration** trong ví dụ được định nghĩa **không có @Configuration** và được tham chiếu bởi @LoadBalancerClient. Theo hướng dẫn Spring Cloud, lớp cấu hình riêng cho LoadBalancer không nên bị component scan của ứng dụng chính thu nhận như một cấu hình toàn cục. Cách khác là đặt lớp đó ngoài phạm vi component scan.

Nếu ứng dụng cũng gọi payment-service, không nhất thiết áp dụng cùng supplier cho payment-service. Cấu hình riêng theo service ID giúp điều chỉnh chính sách phù hợp với từng downstream.

### 5.4. Bật zone ở caller

~~~yaml
spring:
  application:
    name: order-service
  cloud:
    loadbalancer:
      zone: zone-a
~~~

Thuộc tính **spring.cloud.loadbalancer.zone** xác định vùng ưu tiên ở phía caller. Nó không tự đăng ký metadata của các Inventory instance; phần đó do provider/discovery đảm nhận.

## 6. Cấu hình metadata zone từ nguồn discovery

### 6.1. Eureka: gắn zone cho instance

Ứng dụng Inventory đăng ký metadata zone:

~~~yaml
spring:
  application:
    name: inventory-service

eureka:
  instance:
    metadata-map:
      zone: zone-a
~~~

Một bản sao Inventory khác, ở zone-b, dùng:

~~~yaml
eureka:
  instance:
    metadata-map:
      zone: zone-b
~~~

Với Eureka, Spring Cloud có tích hợp để suy ra **zone của caller** từ cấu hình Eureka và truyền vào LoadBalancer; tài liệu cũng nêu các nhánh suy đoán liên quan đến metadata hoặc availability zone của Eureka. Tuy nhiên, **spring.cloud.loadbalancer.zone** cho phép ghi đè zone mà LoadBalancer dùng. Để tránh phụ thuộc vào giá trị mặc định hoặc heuristic, trong bài thực hành nên đặt rõ ràng zone ở caller.

Một ứng dụng có thể vừa là provider cho dịch vụ của mình, vừa là caller của dịch vụ khác. Khi đó cần phân biệt:

- **eureka.instance.metadata-map.zone**: metadata instance **nó đăng ký** cho ứng dụng khác đọc.
- **spring.cloud.loadbalancer.zone**: zone **nó dùng để ưu tiên** khi gọi ứng dụng khác.

Trong nhiều deployment, hai giá trị giống nhau nhưng chúng phục vụ hai chiều dữ liệu khác nhau.

### 6.2. Consul, Kubernetes và các provider khác

Đừng giả định tất cả discovery provider tự sinh metadata **zone** theo cùng một cách. Spring Cloud LoadBalancer chỉ đọc:

~~~java
serviceInstance.getMetadata().get("zone")
~~~

Nếu Kubernetes lưu zone ở nhãn node **topology.kubernetes.io/zone**, điều đó không tự đảm bảo nhãn này xuất hiện ở đúng vị trí metadata của ServiceInstance. Tùy integration, cần một cơ chế ánh xạ nhãn hoặc bổ sung metadata từ nguồn discovery.

Tương tự, nếu Consul hoặc một provider khác dùng tag hay key khác, hãy chuẩn hóa khi tạo ServiceInstance hoặc viết supplier chuyển đổi metadata. Nên dùng **spring.cloud.loadbalancer.zone** ở caller nếu integration chưa tự xác định được local zone.

**Nguyên tắc:** kiểm chứng dữ liệu trả ra từ DiscoveryClient/ReactiveDiscoveryClient trước, không chỉ nhìn dashboard registry hoặc YAML của workload.

### 6.3. SimpleDiscoveryClient để thử nghiệm local

Khi chưa dựng registry, có thể khai báo danh sách tĩnh trong caller:

~~~yaml
spring:
  cloud:
    loadbalancer:
      zone: zone-a
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://localhost:8081
                metadata:
                  zone: zone-a
              - uri: http://localhost:8082
                metadata:
                  zone: zone-b
~~~

Ví dụ này dựa vào SimpleDiscoveryClient và metadata có trong cấu hình danh sách instance. Trước khi diễn giải kết quả, kiểm tra từng **ServiceInstance.getMetadata()** xem khóa zone đã được bind đúng trong phiên bản Spring Cloud đang dùng. SimpleDiscoveryClient là nguồn **tĩnh**; nó không tự phát hiện bản sao vừa dừng hoặc vừa được mở.

Với SimpleDiscoveryClient, có thể dùng **withBlockingDiscoveryClient()** trong builder của mục 5.1. Với provider có reactive discovery thật sự, thay bằng **withDiscoveryClient()** theo nhu cầu.

## 7. Cách zone preference thay đổi lựa chọn của Round Robin

Giả sử các instance đều khỏe, không có filter khác và chuỗi danh sách ổn định:

~~~text
inventory-service
  A - zone-a
  B - zone-a
  C - zone-b
  D - zone-b
~~~

Trong cấu hình không có ZonePreference, Round Robin có bốn ứng viên **[A, B, C, D]**. Khi client ở zone-a với ZonePreference, Round Robin chỉ nhìn thấy **[A, B]**.

| Chính sách | Danh sách RoundRobin nhận | Kết quả có thể chọn |
| --- | --- | --- |
| Không lọc zone | [A, B, C, D] | A, B, C hoặc D |
| Caller zone-a | [A, B] | A hoặc B |
| Caller zone-b | [C, D] | C hoặc D |
| Caller zone-c, không có match | [A, B, C, D] | A, B, C hoặc D |

**Zone preference không chọn instance trực tiếp.** Nó không tạo một lượt Round Robin riêng cho mỗi zone theo một API tách biệt; nó chỉ thu hẹp danh sách ứng viên. Thuật toán lựa chọn cuối cùng vẫn hoạt động theo danh sách được supplier trả về.

Trong hệ thống nhiều instance, việc cân bằng tải **trong một zone** có thể tiếp tục theo Round Robin, Random hoặc thuật toán tùy biến.

### 7.1. Vì sao nhiều request không chắc có phân bố 50/50?

Ngay cả khi zone-a có hai instance, không nên lấy đúng hai request để kết luận thuật toán đã lỗi nếu kết quả chưa luân phiên như dự đoán. Cần tính đến:

- Trạng thái bộ đếm của RoundRobin.
- Các request đồng thời và thứ tự thực thi.
- Khả năng supplier trả snapshot khác nhau.
- Cache hoặc health check cập nhật danh sách.
- Retry làm phát sinh thêm lần chọn đích.
- Bộ lọc khác như hint, sticky session hoặc weighted supplier.

Để kiểm tra phân bố, cần một số lượng request đủ lớn và ghi nhận danh sách ứng viên thực tế khi chọn.

## 8. Fallback khi không có instance cùng zone

Đây là đặc tính quan trọng nhất cần hiểu trước khi sử dụng ZonePreference:

~~~mermaid
flowchart TD
    A["Danh sách từ delegate"] --> B{"Zone caller được cấu hình?"}
    B -->|Không| C["Trả nguyên danh sách"]
    B -->|Có| D["Lọc metadata zone"]
    D --> E{"Tìm được >= 1 instance?"}
    E -->|Có| F["Trả danh sách cùng zone"]
    E -->|Không| C
    F --> G["LoadBalancer chọn instance"]
    C --> G
~~~

Ví dụ hệ thống đang chạy:

~~~text
T0:
  Caller: zone-a
  Discovery: [A(zone-a), B(zone-b)]
  ZonePreference: [A]

T1: A bị hủy đăng ký, discovery đã cập nhật
  Discovery: [B(zone-b)]
  ZonePreference: [B]    // fallback ra ngoài zone-a

T2: A được triển khai trở lại và xuất hiện trong discovery
  Discovery: [A(zone-a), B(zone-b)]
  ZonePreference: [A]    // ưu tiên local trở lại
~~~

Điều này hỗ trợ **khả năng tiếp tục phục vụ khi thiếu bản sao cục bộ**, nhưng không đồng nghĩa tự động failover toàn bộ tầng hạ tầng. Độ trễ cập nhật có thể phụ thuộc cache, health check, registry và cơ chế retry.

### 8.1. Fallback không đánh giá tình trạng instance

Nếu A còn nằm trong danh sách discovery nhưng thực tế đã chết, ZonePreference vẫn có thể trả **[A]**, vì nó chỉ nhìn metadata zone. Nó không tự ping A để phát hiện lỗi.

Với trường hợp này, cần:

1. Cập nhật trạng thái instance qua registry/health check.
2. Sử dụng HealthCheckServiceInstanceListSupplier nếu nguồn instance không có health đáng tin cậy.
3. Cấu hình timeout và retry phù hợp ở HTTP client.
4. Theo dõi lỗi kết nối và thời điểm danh sách instance thay đổi.

Không thể mong đợi một bộ lọc zone tự thay thế circuit breaker hay health monitoring.

### 8.2. Fallback và yêu cầu tuân thủ

Nếu dữ liệu chỉ được phép xử lý trong zone-a, việc fallback sang zone-b có thể vi phạm yêu cầu kiến trúc. Khi đó:

- **Không dùng ZonePreference như cơ chế cô lập duy nhất.**
- Cần một supplier lọc nghiêm ngặt: không có instance cùng zone thì trả danh sách rỗng, để caller nhận lỗi thay vì vượt vùng.
- Hoặc áp dụng định tuyến/network policy tách biệt, kết hợp xác thực/ủy quyền ở backend.
- Kiểm tra toàn bộ retry, Gateway và proxy để không vô tình gửi lưu lượng ra ngoài vùng.

Đây là lựa chọn giữa **availability** và **strict locality**. Phải quyết định rõ bằng yêu cầu hệ thống.

## 9. Thứ tự decorator: cache, health check và zone

ZonePreference là một decorator; đầu ra của nó phụ thuộc vào danh sách được các lớp trước đó cung cấp.

### 9.1. Cache đặt trước ZonePreference

Chuỗi được khuyến nghị:

~~~java
return ServiceInstanceListSupplier.builder()
        .withBlockingDiscoveryClient()
        .withCaching()
        .withZonePreference()
        .build(context);
~~~

Luồng biến đổi:

~~~text
Discovery -> Caching -> ZonePreference -> LoadBalancer
~~~

CachingServiceInstanceListSupplier giữ danh sách instance theo service ID, sau đó ZonePreference mới áp dụng chính sách zone. Cấu hình này giảm số lần đọc registry nhưng vẫn có thể sử dụng một snapshot discovery làm nguồn cho chính sách zone.

Nếu cache bị đặt **ngoài** ZonePreference, kết quả đã lọc có thể bị cache theo service ID. Với một zone cố định của client, điều đó có thể trông vẫn đúng; tuy nhiên, dữ liệu đã lọc không còn là danh sách discovery gốc và dễ gây nhầm khi ghép thêm filter theo request, thay đổi chính sách zone hoặc tái sử dụng supplier ở những ngữ cảnh khác.

Spring Cloud khuyến nghị đặt caching supplier **ngay sau supplier lấy instance từ mạng**, trước các supplier lọc.

### 9.2. Health check trước ZonePreference

Nếu nguồn discovery không phản ánh health đầy đủ:

~~~java
return ServiceInstanceListSupplier.builder()
        .withBlockingDiscoveryClient()
        .withBlockingHealthChecks()
        .withZonePreference()
        .build(context);
~~~

Luồng:

~~~text
Discovery -> HealthCheck -> ZonePreference -> LoadBalancer
~~~

HealthCheck nên thấy **đầy đủ danh sách gốc** trước khi ưu tiên zone. Nếu A cùng zone đã DOWN và B khác zone còn UP, HealthCheck có cơ hội loại A trước khi ZonePreference xét fallback.

Tuy nhiên, HealthCheckServiceInstanceListSupplier có vòng poll và cơ chế phát kết quả bất đồng bộ; đồng thời tùy phiên bản/cấu hình, khi không tìm thấy instance healthy, nó có thể fallback theo danh sách delegate. Không xem một snapshot health là bảo đảm request chắc chắn thành công.

**Không mặc định bật cả cache và health-check supplier**: Spring Cloud HealthCheckServiceInstanceListSupplier có cơ chế replay kết quả riêng; ghép thêm cache thường có thể khiến dữ liệu stale hoặc khó hiểu hơn. Hãy kiểm tra hành vi cụ thể của release train.

### 9.3. Zone và Hint: thứ tự cũng là chính sách

Giả sử:

~~~text
A: zone-a, hint=stable
B: zone-b, hint=canary
Client zone: zone-a
Request hint: canary
~~~

Hai thứ tự cho kết quả khác nhau do ZonePreference và HintBased đều fallback khi không match:

| Chuỗi biến đổi | Diễn biến | Kết quả |
| --- | --- | --- |
| Zone rồi Hint | [A,B] → Zone [A] → Hint không match, fallback [A] | A |
| Hint rồi Zone | [A,B] → Hint [B] → Zone không match, fallback [B] | B |

Vì thế, cần định nghĩa ưu tiên:

- **Zone trước, Hint sau**: ưu tiên locality; canary chỉ có cơ hội nếu tồn tại trong zone đã được lọc.
- **Hint trước, Zone sau**: ưu tiên nhóm triển khai; zone chỉ tối ưu trong các instance thuộc nhóm hint.

Đây không phải lỗi thuật toán. Nó là hệ quả của **thứ tự decorator và điều kiện fallback**. Nếu cần cả hai điều kiện bắt buộc đồng thời, không nên dùng hai soft-preference filter rồi giả định chúng thực hiện phép giao nghiêm ngặt.

## 10. Tích hợp với RestClient, WebClient và OpenFeign

### 10.1. RestClient

Caller đăng ký builder có @LoadBalanced:

~~~java
@Configuration(proxyBeanMethods = false)
class InventoryClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }
}
~~~

Client gọi bằng service ID:

~~~java
@Service
class InventoryClient {

    private final RestClient restClient;

    InventoryClient(@LoadBalanced RestClient.Builder builder) {
        this.restClient = builder.build();
    }

    StockResponse getStock(String sku) {
        return restClient.get()
                .uri("http://inventory-service/api/stock/{sku}", sku)
                .retrieve()
                .body(StockResponse.class);
    }
}
~~~

Nếu cấu hình supplier zone preference cho inventory-service, BlockingLoadBalancerClient nhận danh sách đã lọc rồi chọn instance. Code nghiệp vụ vẫn dùng URI logic **http://inventory-service/...**, không cần hardcode IP của zone-a.

### 10.2. WebClient

Với reactive HTTP client:

~~~java
@Configuration(proxyBeanMethods = false)
class ReactiveClientConfiguration {

    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder() {
        return WebClient.builder();
    }
}
~~~

~~~java
@Service
class ReactiveInventoryClient {

    private final WebClient webClient;

    ReactiveInventoryClient(@LoadBalanced WebClient.Builder builder) {
        this.webClient = builder.build();
    }

    Mono<StockResponse> getStock(String sku) {
        return webClient.get()
                .uri("http://inventory-service/api/stock/{sku}", sku)
                .retrieve()
                .bodyToMono(StockResponse.class);
    }
}
~~~

Khi provider có ReactiveDiscoveryClient, có thể dùng **withDiscoveryClient().withCaching().withZonePreference()** trong cấu hình supplier. ZonePreference không yêu cầu một thuật toán riêng cho WebClient; nó vẫn lọc danh sách trước bước chọn ServiceInstance.

### 10.3. OpenFeign

~~~java
@FeignClient(name = "inventory-service")
interface InventoryFeignClient {

    @GetMapping("/api/stock/{sku}")
    StockResponse getStock(@PathVariable("sku") String sku);
}
~~~

Với Spring Cloud OpenFeign có tích hợp LoadBalancer, tên inventory-service được dùng để tìm instance; supplier zone preference có thể thu hẹp danh sách trước khi Feign gọi instance thật. **Không khai báo URL cố định** nếu muốn kích hoạt phân giải theo service ID và cân bằng tải qua discovery.

Trong cả ba cách, lọc theo zone nằm tại **ServiceInstanceListSupplier**, độc lập với method GET/POST hoặc nội dung response. Timeout, retry, idempotency và xác thực vẫn cần cấu hình riêng.

## 11. Zone preference không thay thế các cơ chế khác

| Cơ chế | Trả lời câu hỏi gì? | Phạm vi |
| --- | --- | --- |
| Discovery | Có những bản sao nào? | Service registry / ServiceInstance |
| Health check | Bản sao còn sẵn sàng không? | Trạng thái instance |
| Zone preference | Nên ưu tiên bản sao ở zone nào? | Metadata zone |
| Round Robin | Trong danh sách ứng viên, chọn ai tiếp theo? | Thuật toán lựa chọn |
| Weighted | Instance nào có trọng số chọn lớn hơn? | Phân bố lưu lượng |
| Hint-based | Request thuộc nhóm nào, ví dụ canary/stable? | Metadata hint và request |
| Circuit breaker | Khi downstream lỗi liên tục thì bảo vệ caller ra sao? | Chuỗi lời gọi |
| Retry | Có thử lại hay chọn lại instance không? | Điều khiển request/response |

Zone preference chỉ sử dụng **metadata**, nên nó không thể:

- Nhận biết CPU hoặc bộ nhớ tức thời của instance.
- Bảo đảm kết nối cùng zone luôn nhanh hơn.
- Phát hiện instance chết nếu registry/health chưa cập nhật.
- Tự điều chuyển traffic khi một zone đang quá tải nhưng vẫn còn instance.
- Bảo đảm mọi request chỉ đi trong một zone trong mọi hoàn cảnh.
- Thay thế chính sách định tuyến theo dữ liệu nhạy cảm, tenant hoặc yêu cầu pháp lý.

Nếu muốn điều khiển traffic theo độ trễ, tải hoặc circuit breaker, phải kết hợp chính sách và observability tương ứng.

## 12. Vấn đề vận hành: khi zone-a quá tải

Giả sử zone-a có hai instance, zone-b có bốn instance. Caller nằm ở zone-a và hai instance zone-a vẫn đăng ký khỏe mạnh nhưng đang quá tải.

~~~text
ZonePreference:
    zone-a: [A1, A2]   // có match
    zone-b: [B1, B2, B3, B4]
    kết quả: [A1, A2]
~~~

ZonePreference **không tự fallback sang zone-b** chỉ vì A1/A2 phản hồi chậm hoặc có CPU cao. Nó chỉ fallback khi **không tìm thấy instance cùng zone trong danh sách được delegate cung cấp**.

Nếu cần giảm tải chủ động:

1. Bổ sung capacity/autoscaling trong zone-a.
2. Dùng health check phù hợp khi instance thực sự không còn phục vụ được.
3. Thiết kế load-balancing policy dựa trên số liệu tải hoặc trọng số, nếu có dữ liệu tin cậy.
4. Theo dõi latency, saturation, 5xx và retry của từng zone.
5. Cân nhắc chính sách cross-zone spillover có điều kiện, thay vì cho rằng ZonePreference đã có sẵn tính năng đó.

Một hệ thống vẫn có thể cần điều phối ở tầng Kubernetes, Gateway, service mesh hoặc proxy ngoài ứng dụng. Các tầng này phải thống nhất để tránh hai chính sách định tuyến mâu thuẫn.

## 13. Unit test nguyên lý zone preference

Có thể kiểm chứng quy tắc bằng mô hình thuần Java trước khi chạy Spring:

~~~java
import java.util.List;

public class ZonePreferenceDemo {

    record Instance(String id, String zone) {}

    static List<Instance> prefer(
            List<Instance> instances,
            String clientZone) {

        if (clientZone == null) {
            return instances;
        }

        List<Instance> local = instances.stream()
                .filter(i -> clientZone.equalsIgnoreCase(i.zone()))
                .toList();

        return local.isEmpty() ? instances : local;
    }

    public static void main(String[] args) {
        List<Instance> discovered = List.of(
                new Instance("A", "zone-a"),
                new Instance("B", "zone-a"),
                new Instance("C", "zone-b"));

        System.out.println(prefer(discovered, "zone-a"));
        System.out.println(prefer(discovered, "zone-b"));
        System.out.println(prefer(discovered, "zone-c"));
        System.out.println(prefer(discovered, null));
    }
}
~~~

Kỳ vọng:

~~~text
zone-a -> [A, B]
zone-b -> [C]
zone-c -> [A, B, C]   // fallback
null   -> [A, B, C]   // không lọc
~~~

Đây là **mô hình khái niệm**, không trực tiếp gọi lớp ZonePreferenceServiceInstanceListSupplier. Nó cho phép tách quy tắc lọc khỏi service registry, Spring ApplicationContext, cache và HTTP. Khi đã hiểu quy tắc, nên dùng integration test với supplier thật.

### 13.1. Các trường hợp biên cần kiểm tra

| Đầu vào | Zone caller | Kỳ vọng |
| --- | --- | --- |
| [] | zone-a | [] |
| [A(zone-a)] | zone-a | [A] |
| [A(zone-b)] | zone-a | [A] do fallback |
| [A(zone-a), B(zone-b)] | zone-a | [A] |
| [A(không metadata), B(zone-b)] | zone-a | [A, B] do fallback |
| [A(zone-a), B(zone-a)] | ZONE-A | [A, B] |
| [A(zone-a)] | null | [A] |

Trong unit test thực tế, nên tạo DefaultServiceInstance và gắn metadata zone, sau đó đưa chúng qua supplier giả kiểm soát danh sách. Điều quan trọng là biết bản thân thuật toán lọc trả về gì, không để tình trạng registry hoặc cache làm kết quả thay đổi không dự đoán được.

## 14. Integration test với SimpleDiscoveryClient

### 14.1. Chuẩn bị

Khởi chạy hai backend cùng endpoint GET /whoami:

~~~text
inventory-a: http://localhost:8081/whoami -> {"instanceId":"inventory-a"}
inventory-b: http://localhost:8082/whoami -> {"instanceId":"inventory-b"}
~~~

Caller có spring-cloud-starter-loadbalancer, sử dụng Spring Cloud SimpleDiscoveryClient và @LoadBalanced RestClient.Builder.

~~~yaml
spring:
  cloud:
    loadbalancer:
      zone: zone-a
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://localhost:8081
                metadata:
                  zone: zone-a
              - uri: http://localhost:8082
                metadata:
                  zone: zone-b
~~~

Gắn InventoryZoneLoadBalancerConfiguration của mục 5.1 bằng @LoadBalancerClient.

### 14.2. Các bước quan sát

1. Gọi **http://inventory-service/whoami** nhiều lần qua RestClient đã tích hợp LoadBalancer.
2. Với client zone-a, xác nhận response chỉ đến từ inventory-a trong điều kiện hai backend hoạt động và metadata được bind đúng.
3. Thay **spring.cloud.loadbalancer.zone=zone-b**, khởi động lại caller, xác nhận chỉ inventory-b được chọn.
4. Thay zone thành zone-c (không có instance cùng zone), xác nhận request có thể đến cả inventory-a và inventory-b theo chính sách chọn cuối cùng.
5. Xóa metadata zone khỏi cả hai instance, xác nhận zone preference không còn thu hẹp danh sách.
6. Dừng inventory-a nhưng **giữ nó trong cấu hình tĩnh**: request vẫn có thể cố gọi inventory-a. Đây là giới hạn của SimpleDiscoveryClient, không phải bằng chứng fallback tự động theo health.
7. Thử dùng HealthCheck supplier ngay sau discovery, chờ trạng thái health cập nhật rồi kiểm tra khả năng chọn instance còn khỏe ở vùng khác.

**Cảnh báo cho bước 6:** cấu hình tĩnh không phản ánh instance vừa chết. Trong production, cập nhật registry/health và thời gian TTL quyết định khi nào zone preference quan sát được danh sách mới.

### 14.3. Bảng quan sát mong đợi

| Thay đổi | Danh sách từ discovery/health | ZonePreference trả |
| --- | --- | --- |
| zone-a, cả hai UP | [A(zone-a), B(zone-b)] | [A] |
| zone-b, cả hai UP | [A(zone-a), B(zone-b)] | [B] |
| zone-c, cả hai UP | [A(zone-a), B(zone-b)] | [A, B] |
| zone-a, A đã bị loại bởi health | [B(zone-b)] | [B] do fallback |
| zone-a, danh sách rỗng | [] | [] |

Một cách kiểm chứng đáng tin cậy là log **ServiceInstance ID và zone được chọn** ở caller, đồng thời backend trả instanceId của nó. Không chỉ kiểm tra status 200, bởi nhiều bản sao có thể trả cùng kết quả nghiệp vụ.

## 15. Quan sát và chẩn đoán lỗi

Để hiểu vì sao một request rời zone mong muốn, hãy quan sát:

~~~text
serviceId: inventory-service
clientZone: zone-a
discovered: [A(zone-a), B(zone-b)]
healthy:    [B(zone-b)]
zoneOutput: [B(zone-b)]   // fallback, không có local match
selected:   B
~~~

Nếu hệ thống đã có tracing/metrics, nên bổ sung service ID, instance ID và zone ở mức log cấu trúc phù hợp. **Không ghi token, thông tin định danh nhạy cảm hoặc toàn bộ headers/cookies** khi phân tích định tuyến.

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Luôn chọn cross-zone dù có instance local | Không có spring.cloud.loadbalancer.zone hoặc metadata zone sai | In cấu hình caller và metadata từ ServiceInstance |
| Cấu hình zone nhưng danh sách không thay đổi | Chưa thêm withZonePreference vào supplier | Kiểm tra bean ServiceInstanceListSupplier đang hoạt động |
| Tất cả instance có metadata nhưng không match | Key không phải zone, tên zone có khoảng trắng hoặc khác quy ước | Kiểm tra metadata map thực tế |
| Không failover khi local instance chết | Registry/cache chưa cập nhật hoặc health filter chưa loại instance | Kiểm tra danh sách delegate và TTL |
| Bất ngờ gọi cross-zone | ZonePreference fallback khi không có local match | Đo số instance cùng zone trước và sau filter |
| Canary không nhận traffic như mong đợi | Hint và Zone filter có thứ tự ưu tiên không phù hợp | Kiểm tra thứ tự decorator và fallback của từng lớp |
| WebClient không chọn được instance | Reactive discovery/supplier cấu hình sai | Kiểm tra provider reactive và chuỗi supplier |
| Feign gọi một URL cố định | @FeignClient có url hoặc thuộc tính URL cố định | Bỏ URL cố định nếu cần discovery |
| Request local zone quá chậm | Instance cùng zone vẫn healthy nhưng quá tải | Kiểm tra CPU, thread pool, latency và timeout |
| Không bao giờ chọn instance ở zone khác khi local zone UP | Đúng hành vi của zone preference | Đánh giá có cần cơ chế spillover theo tải hay không |

### Quy trình kiểm tra nhanh

1. Kiểm tra **clientZone** thực sự mà LoadBalancer nhận.
2. Xác nhận **ServiceInstance.getMetadata().get("zone")** cho từng instance.
3. Xác định danh sách **trước ZonePreference**, sau discovery/cache/health.
4. Áp dụng quy tắc **same-zone hoặc fallback toàn bộ** trên snapshot đó.
5. Kiểm tra instance mà Round Robin/Random đã chọn.
6. Quan sát URI vật lý và lỗi HTTP/TLS/timeout sau khi chọn.

Nếu danh sách trước ZonePreference đã rỗng, vấn đề nằm ở discovery/supplier trước đó. Nếu zoneOutput có local instance nhưng request lại đi cross-zone, hãy xem có wrapper khác ở ngoài hoặc một tầng Gateway/proxy đang định tuyến lại hay không.

## 16. Thiết kế chiến lược zone cho production

### 16.1. Đảm bảo cùng một cách đặt tên

Sử dụng taxonomy zone nhất quán giữa các nhóm:

~~~text
Đúng:
  caller:   zone-a
  provider: zone-a

Dễ lỗi:
  caller:   asia-1a
  provider: zone-a
~~~

Nếu ứng dụng triển khai trên các nền tảng khác nhau, cần một bảng ánh xạ chính thức giữa nhãn cloud/Kubernetes, metadata của registry và zone mà client-side LoadBalancer dùng.

### 16.2. Tạo cấu hình theo môi trường triển khai

Mỗi bản sao Order Service có thể được gán biến môi trường:

~~~text
SPRING_CLOUD_LOADBALANCER_ZONE=zone-a
~~~

Giá trị nên do hệ thống triển khai đưa vào theo placement thực tế, không gắn cứng chung cho mọi pod trong nhiều zone. Sau khi thay đổi vị trí triển khai hoặc cấu hình, kiểm tra lại bean supplier và zone đang có hiệu lực.

### 16.3. Quyết định rõ fallback được phép đến đâu

Với request thông thường, fallback ra ngoài zone có thể tăng khả dụng. Với dữ liệu chỉ được phép xử lý ở một vùng, phải dùng strict filter hoặc cơ chế bảo vệ khác. Cả hai lựa chọn đều cần được thử nghiệm khi local zone biến mất.

### 16.4. Đặt health/caching đúng chỗ

Đường đi khuyến nghị:

~~~text
Discovery -> Caching hoặc HealthCheck -> ZonePreference
          -> các chính sách request còn lại -> LoadBalancer
~~~

Không giả định thứ tự các decorator có thể hoán đổi tự do. Một decorator có fallback có thể trả lại danh sách đầu vào khi không match, làm thay đổi ý nghĩa của chính sách đứng trước hoặc sau nó.

### 16.5. Đặt timeout và retry có giới hạn

Cross-zone có thể có latency khác local zone. Cần đo và cấu hình timeout dựa trên SLO, không dùng một ngưỡng quá thấp chỉ hợp với local path. Khi retry chọn lại instance, cần cân nhắc deadline tổng, retry budget, backoff và an toàn của thao tác không lũy đẳng.

### 16.6. Theo dõi tỷ lệ spillover

Có thể theo dõi chỉ số tự xây dựng:

~~~text
cross_zone_selection_ratio =
  số lần chọn instance có zone khác clientZone
  ------------------------------------------------
  tổng số lần chọn instance có zone xác định
~~~

Đây là **metric thiết kế gợi ý**, không phải tên metric mặc định được Spring Cloud LoadBalancer cung cấp. Việc đo phải nêu rõ cách xử lý instance không có metadata zone và những request retry. Tỷ lệ tăng đột biến có thể gợi ý local zone đang thiếu instance hoặc metadata không đồng nhất.

## 17. Checklist triển khai

- [ ] Phân biệt zone của caller với metadata zone của provider.
- [ ] Cấu hình spring.cloud.loadbalancer.zone tại caller hoặc xác minh tích hợp discovery đã cung cấp zone chính xác.
- [ ] Mỗi ServiceInstance có metadata key **zone** đúng quy ước.
- [ ] Supplier thực sự có ZonePreferenceServiceInstanceListSupplier.
- [ ] Cache/HealthCheck được đặt sau nguồn discovery và trước zone preference.
- [ ] Biết rõ hành vi fallback khi không còn bản sao cùng zone.
- [ ] Không dùng zone preference như ràng buộc bảo mật hoặc lưu trữ dữ liệu bắt buộc.
- [ ] Kiểm chứng sự kết hợp với hint, sticky session, retry và weighted routing nếu có.
- [ ] Kiểm tra cả kịch bản local UP, local DOWN, metadata thiếu và zone không tồn tại.
- [ ] Theo dõi instance đã chọn, latency, cross-zone traffic và lỗi kết nối.
- [ ] Đánh giá giới hạn năng lực local zone; zone preference không tự phát hiện overload.
- [ ] Cân nhắc nhất quán cấu hình giữa RestClient, WebClient và OpenFeign.

## 18. Kết luận

**ZonePreferenceServiceInstanceListSupplier** là lớp lọc theo vùng của Spring Cloud LoadBalancer. Nó sử dụng **spring.cloud.loadbalancer.zone** hoặc thông tin zone của caller do discovery integration cung cấp, so với **ServiceInstance.metadata["zone"]**, rồi ưu tiên trả những instance cùng vùng. Nếu không có zone của caller hoặc không có bản sao cùng vùng, nó **trả lại danh sách delegate** để LoadBalancer vẫn có ứng viên.

Thiết kế đúng cần cả ba điều kiện: **zone metadata chính xác**, **supplier chain đặt đúng vị trí**, và **chính sách fallback phù hợp với yêu cầu kinh doanh/vận hành**. Khi đó RestClient, WebClient và OpenFeign có thể tiếp tục dùng service ID logic, còn LoadBalancer ưu tiên chọn địa chỉ thật gần caller hơn mà không phải hardcode IP của từng zone.

## 19. Tài liệu tham khảo

- [Spring Cloud LoadBalancer – Zone-Based Load-Balancing](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): cơ chế zone preference, thuộc tính spring.cloud.loadbalancer.zone, metadata zone và cách cấu hình builder.
- [Spring Cloud Commons – Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): DiscoveryClient, ServiceInstance và HTTP client integrations.
- [ZonePreferenceServiceInstanceListSupplier.java](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-loadbalancer/src/main/java/org/springframework/cloud/loadbalancer/core/ZonePreferenceServiceInstanceListSupplier.java): nguồn chuẩn cho so khớp zone (equalsIgnoreCase) và fallback.
- [ServiceInstanceListSupplierBuilder.java](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-loadbalancer/src/main/java/org/springframework/cloud/loadbalancer/core/ServiceInstanceListSupplierBuilder.java): cách tạo chuỗi supplier/decorator.
- [Spring Cloud Netflix Eureka – Reference](https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html): metadata instance và tích hợp Eureka với zone của LoadBalancer.
