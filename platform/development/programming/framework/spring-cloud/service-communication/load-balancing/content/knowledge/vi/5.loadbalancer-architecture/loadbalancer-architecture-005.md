# ServiceInstanceListSupplier trong chuỗi cung cấp bản sao

Spring Cloud LoadBalancer cần biết những instance nào có thể nhận một request trước khi chọn một instance cụ thể. Thành phần cung cấp danh sách đó là `ServiceInstanceListSupplier`. Nó đứng giữa nguồn service discovery và bộ chọn instance: lấy danh sách `ServiceInstance`, có thể cache hoặc lọc danh sách theo health, zone hay thông tin request, rồi cung cấp các ứng viên cho LoadBalancer.

Bài học này thuộc chương **Kiến trúc LoadBalancer** của module `SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING`. Module tập trung vào cân bằng tải phía client: chọn `ServiceInstance` theo service ID, discovery, health check và chính sách định tuyến; tích hợp `RestClient`, `WebClient`, OpenFeign; cấu hình retry/timeout và quan sát lỗi. Hiểu rõ `ServiceInstanceListSupplier` giúp bạn biết danh sách ứng viên đến từ đâu, vì sao một số instance bị loại và vì sao kết quả chọn có thể khác nhau giữa các request.

Sau bài học, bạn có thể:

- Đặt `ServiceInstanceListSupplier` đúng vị trí trong luồng xử lý của Spring Cloud LoadBalancer.
- Phân biệt việc cung cấp danh sách instance với việc chọn một instance.
- Giải thích cách discovery client, cache, health check và các bộ lọc phối hợp thành một supplier chain.
- Cấu hình supplier theo từng service bằng `@LoadBalancerClient`.
- Hiểu khi nào nên dùng thông tin zone, hint hoặc request context để lọc ứng viên.
- Kiểm thử danh sách supplier và điều tra trường hợp danh sách rỗng, dữ liệu cũ hoặc instance không khả dụng.

## 1. Vị trí của ServiceInstanceListSupplier trong kiến trúc

Một service gọi service khác bằng tên logic, ví dụ `inventory-service`. Tên này là service ID. Discovery client tra cứu các bản sao đã đăng ký cho service ID đó và thu được các `ServiceInstance`. Mỗi instance chứa thông tin kết nối như host, port, secure flag, metadata và service ID.

Spring Cloud LoadBalancer cần một danh sách ứng viên để bộ chọn instance có thể quyết định nơi gửi request. `ServiceInstanceListSupplier` chịu trách nhiệm cung cấp danh sách này.

~~~mermaid
flowchart LR
    A["HTTP client gọi inventory-service"] --> B["Spring Cloud LoadBalancer"]
    B --> C["ServiceInstanceListSupplier"]
    C --> D["Nguồn discovery"]
    D --> E["Danh sách ServiceInstance"]
    E --> F["Cache / health / zone / request filters"]
    F --> G["Danh sách ứng viên cuối"]
    G --> H["LoadBalancer chọn một instance"]
    H --> I["HTTP request tới host:port"]
~~~

Có thể tách luồng thành hai câu hỏi:

1. **Những instance nào được phép trở thành ứng viên?** Supplier chain trả lời câu hỏi này bằng cách lấy và biến đổi danh sách.
2. **Trong số các ứng viên, instance nào được chọn cho request hiện tại?** LoadBalancer algorithm, chẳng hạn round robin hoặc random, trả lời câu hỏi này.

Supplier không tự thực hiện HTTP request và cũng không phải thuật toán round robin. Nó chuẩn bị danh sách đầu vào cho thành phần chọn instance. Sau khi một instance được chọn, LoadBalancer thay thế service ID trong URI bằng địa chỉ của instance đó để HTTP client gửi request.

## 2. ServiceInstanceListSupplier cung cấp dữ liệu gì?

`ServiceInstanceListSupplier` là một abstraction trong Spring Cloud LoadBalancer. Về mặt sử dụng, nó cung cấp service ID và một luồng các danh sách `ServiceInstance`. API có phương thức lấy danh sách thông thường và phương thức có thể nhận request context:

~~~java
String getServiceId();

Flux<List<ServiceInstance>> get();

Flux<List<ServiceInstance>> get(Request request);
~~~

Đây là hình dạng API khái quát để hiểu vai trò; kiểu trả về reactive `Flux` cho phép supplier phát danh sách theo cách phù hợp với pipeline của LoadBalancer. Phương thức `get(Request request)` cho phép một supplier sử dụng ngữ cảnh của request khi cần lọc ứng viên. Cách triển khai mặc định có thể bỏ qua request context nếu không cần xử lý theo request.

Một `ServiceInstance` thường cung cấp các thông tin như:

| Thông tin | Ý nghĩa |
|---|---|
| `serviceId` | Dịch vụ logic mà instance thuộc về. |
| `host` | Host hoặc địa chỉ IP của bản sao. |
| `port` | Cổng HTTP/HTTPS của bản sao. |
| `isSecure()` | Cho biết instance dùng kết nối bảo mật hay không. |
| `metadata` | Thuộc tính bổ sung như zone, version, rack hoặc weight. |
| `instanceId` | Định danh instance nếu discovery implementation cung cấp. |

Ví dụ, discovery có thể trả về ba instance của `inventory-service`:

~~~text
inventory-service -> 10.0.1.21:8080, zone=zone-a
inventory-service -> 10.0.1.22:8080, zone=zone-a
inventory-service -> 10.0.2.31:8080, zone=zone-b
~~~

Supplier có thể cung cấp cả ba instance, hoặc một decorator tiếp theo có thể lọc danh sách theo điều kiện. Kết quả cuối cùng là đầu vào cho LoadBalancer algorithm.

## 3. Nguồn danh sách: Service Discovery

Trong ứng dụng dùng Eureka, Consul hoặc một hệ thống discovery khác, discovery client truy vấn registry để tìm các bản sao của service ID. Supplier nền tảng chuyển kết quả từ discovery client thành danh sách `ServiceInstance` mà LoadBalancer hiểu được.

Một số nguồn thường gặp:

- **Discovery client**: lấy instance động từ registry. Danh sách thay đổi khi service đăng ký, hủy đăng ký hoặc trạng thái instance thay đổi.
- **Reactive discovery client**: cung cấp dữ liệu thông qua API discovery reactive nếu ứng dụng dùng loại client này.
- **SimpleDiscoveryClient**: nguồn cấu hình đơn giản, thường hữu ích cho phát triển hoặc kiểm thử khi khai báo instance tĩnh trong cấu hình.
- **Nguồn tùy chỉnh**: ứng dụng có thể tự triển khai supplier để lấy danh sách từ một hệ thống nội bộ hoặc nguồn dữ liệu khác.

Ví dụ minh họa dùng SimpleDiscoveryClient trong cấu hình:

~~~yaml
spring:
  cloud:
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

Khi dùng nguồn tĩnh, danh sách instance không tự phản ánh tình trạng tiến trình đang chạy. Nếu một port ngừng phục vụ, cấu hình vẫn có thể chứa địa chỉ đó cho đến khi được cập nhật. Với môi trường nhiều replica thay đổi thường xuyên, discovery registry và cơ chế cập nhật trạng thái phù hợp sẽ quan trọng hơn.

Điểm cần nhớ là `ServiceInstanceListSupplier` không bắt buộc phải truy vấn registry trực tiếp ở mỗi request. Nó có thể đọc từ cache, từ nguồn tĩnh hoặc từ một supplier khác. Supplier nền tảng và các decorator phía trên quyết định cách danh sách được tạo ra.

## 4. Supplier chain và mô hình decorator

Một supplier chain thường gồm một supplier nền tảng và một hoặc nhiều supplier bọc bên ngoài. Supplier nền tảng lấy danh sách ban đầu; các supplier tiếp theo ủy quyền cho supplier trước rồi bổ sung hành vi như cache hoặc lọc.

Ví dụ danh sách đi qua các bước:

~~~text
Discovery client
    |
    v
[instance A, instance B, instance C]
    |
    v
Caching supplier
    |
    v
[instance A, instance B, instance C]  (dữ liệu được cache)
    |
    v
Health-check supplier
    |
    v
[instance A, instance C]              (instance B không khỏe)
    |
    v
Zone-preference supplier
    |
    v
[instance A]                          (ưu tiên zone của caller)
    |
    v
LoadBalancer algorithm
    |
    v
Chọn instance A
~~~

Đây là ví dụ minh họa một lần xử lý. Danh sách thực tế phụ thuộc supplier đã cấu hình, metadata và trạng thái instance.

Các supplier bọc nhau thường triển khai kiểu ủy quyền: giữ tham chiếu tới supplier delegate, gọi `get()` hoặc `get(request)` của delegate rồi biến đổi danh sách. Mô hình này giúp kết hợp nhiều chính sách mà không phải viết lại phần truy vấn discovery.

**Thứ tự trong chain có ý nghĩa.** Ví dụ, cache nên bọc trực tiếp nguồn discovery để các bộ lọc phía trên làm việc trên danh sách đã cache. Nếu đặt cache bên ngoài một bộ lọc phụ thuộc request, kết quả đã lọc cho request trước có thể bị dùng lại sai ngữ cảnh cho request sau. Với supplier có request context, cần đặc biệt chú ý dữ liệu nào được cache và cache ở tầng nào.

Không phải mọi ứng dụng đều cần tất cả decorator. Hãy bắt đầu với nguồn discovery phù hợp, sau đó chỉ thêm cache, health check hoặc bộ lọc khi yêu cầu vận hành thực sự cần chúng.

## 5. Các supplier thường gặp

Spring Cloud LoadBalancer cung cấp các supplier và decorator phục vụ các nhu cầu phổ biến. Tên lớp và tùy chọn cấu hình cụ thể có thể thay đổi theo phiên bản Spring Cloud; hãy đối chiếu phiên bản dependency đang dùng khi triển khai.

| Supplier / nhóm chức năng | Vai trò |
|---|---|
| Discovery client supplier | Lấy danh sách instance từ discovery client. |
| Caching supplier | Cache danh sách instance để giảm số lần truy vấn discovery. |
| Health-check supplier | Kiểm tra khả năng phục vụ của instance và loại instance không khỏe khỏi danh sách phù hợp. |
| Zone-preference supplier | Ưu tiên instance cùng zone với caller khi có metadata zone. |
| Hint-based supplier | Lọc hoặc ưu tiên ứng viên theo hint gắn với request và metadata. |
| Same-instance preference | Có thể ưu tiên lại instance đã được dùng trong một ngữ cảnh phù hợp. |
| Request-based sticky-session supplier | Hỗ trợ lựa chọn có tính bám phiên dựa trên thông tin request/cookie theo cấu hình. |
| Weighted supplier | Sử dụng metadata trọng số để ảnh hưởng đến tập ứng viên hoặc cách lựa chọn theo hỗ trợ của phiên bản. |
| Retry-aware supplier | Có thể loại instance đã thử trong ngữ cảnh retry để lần thử tiếp theo chọn ứng viên khác. |

Không nên coi tất cả các chức năng trên là một chuỗi mặc định luôn bật. Một số supplier chỉ có ý nghĩa khi có metadata, request context hoặc cấu hình tương ứng. Ví dụ zone preference cần biết zone của caller và zone của instance; weighted selection cần trọng số được khai báo và thuật toán hỗ trợ; sticky session cần cơ chế truyền và đọc thông tin phiên.

### Caching supplier

Discovery có thể được truy vấn thường xuyên, trong khi danh sách instance thường không thay đổi theo từng request. Caching supplier lưu kết quả trong một khoảng thời gian để giảm tải cho registry và giảm độ trễ tra cứu.

Cache giúp hiệu năng tốt hơn nhưng tạo ra độ trễ cập nhật. Khi một instance vừa bị hủy đăng ký hoặc vừa được thêm mới, cache có thể chưa phản ánh thay đổi cho đến lần refresh tiếp theo.

Khi cấu hình cache, cần cân nhắc:

- TTL phù hợp với tốc độ thay đổi instance.
- Dung lượng và eviction policy của cache.
- Cache đã được cung cấp bởi Spring Cloud LoadBalancer hay bởi discovery client.
- Nguy cơ dùng đồng thời nhiều tầng cache khiến dữ liệu cũ tồn tại lâu hơn dự kiến.
- Cách ứng dụng phản ứng khi registry tạm thời không truy cập được.

Spring Cloud LoadBalancer hỗ trợ tích hợp cache theo cấu hình và dependency tương ứng. Nếu dùng Caffeine hoặc cache khác, hãy bảo đảm dependency và cache manager đã được cấu hình đúng. Không bật thêm cache chỉ vì thấy một ví dụ; trước hết xác định cache nào đang hoạt động.

### Health-check supplier

Một instance có thể vẫn xuất hiện trong registry dù ứng dụng đã ngừng phục vụ hoặc một phần chức năng bị lỗi. Health-check supplier có thể chủ động kiểm tra endpoint sức khỏe của instance và chỉ cung cấp những instance được xem là khỏe theo chính sách.

Health check cần được cấu hình nhất quán với endpoint thực tế. Nếu ứng dụng dùng Spring Boot Actuator, có thể chọn health path phù hợp và bảo đảm endpoint đó có thể truy cập từ phía thực hiện kiểm tra.

Cần phân biệt health check của supplier với trạng thái health do registry quản lý. Hai cơ chế có thể cùng tồn tại nhưng nếu cấu hình không nhất quán, một instance có thể bị kiểm tra trùng hoặc bị loại dù vẫn đáp ứng yêu cầu. Health endpoint cũng cần phản ánh đúng mức độ sẵn sàng của service; endpoint trả HTTP 200 đơn giản chưa chắc chứng minh các dependency quan trọng đều hoạt động.

### Zone preference

Trong hệ thống triển khai nhiều vùng, metadata của instance có thể chứa zone, chẳng hạn `zone-a` hoặc `zone-b`. Zone-preference supplier ưu tiên danh sách instance cùng zone với caller nếu tìm được ứng viên phù hợp.

Mục tiêu là giảm độ trễ mạng và chi phí truyền dữ liệu liên vùng. Nếu không có instance cùng zone, hành vi fallback phụ thuộc cách supplier được cấu hình; cần xác minh chính sách thay vì giả định mọi phiên bản đều fallback giống nhau.

Zone preference chỉ hoạt động khi metadata zone của instance và cấu hình zone của client được đồng bộ. Nếu tên zone sai chính tả hoặc thiếu metadata, supplier có thể không tìm được instance cùng zone.

### Hint và request context

Một request có thể mang hint để chọn nhóm instance phù hợp, ví dụ request dành cho phiên bản thử nghiệm hoặc một nhóm vùng nhất định. Supplier có khả năng đọc request context có thể dùng hint đó để lọc danh sách.

Cần xác định rõ hint được lấy từ đâu, ai có quyền gửi và server metadata được đặt theo quy ước nào. Không dùng giá trị do caller không tin cậy gửi tới để mở đường truy cập vào một nhóm instance nhạy cảm. Nếu filter tạo ra danh sách rỗng, request có thể thất bại vì không còn ứng viên; cần có chính sách fallback phù hợp với nghiệp vụ.

## 6. Cấu hình supplier theo từng service

Spring Cloud LoadBalancer hỗ trợ cấu hình riêng cho từng service thông qua `@LoadBalancerClient` hoặc `@LoadBalancerClients`. Điều này hữu ích khi `inventory-service` cần zone preference, còn `pricing-service` chỉ cần discovery và cache.

Ví dụ cấu hình supplier cho `inventory-service`:

~~~java
import org.springframework.cloud.loadbalancer.annotation.LoadBalancerClient;
import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@LoadBalancerClient(
    name = "inventory-service",
    configuration = InventoryLoadBalancerConfiguration.class
)
class InventoryLoadBalancerClientRegistration {
}

@Configuration(proxyBeanMethods = false)
class InventoryLoadBalancerConfiguration {

    @Bean
    ServiceInstanceListSupplier inventoryServiceInstanceListSupplier(
            ConfigurableApplicationContext context) {
        return ServiceInstanceListSupplier.builder()
            .withDiscoveryClient()
            .withCaching()
            .withHealthChecks()
            .withZonePreference()
            .build(context);
    }
}
~~~

Ví dụ trên minh họa một chain có discovery làm nguồn, cache ngay sau nguồn discovery, sau đó health check và zone preference. Các builder method và discovery implementation phải phù hợp với phiên bản Spring Cloud cùng loại discovery client trong dự án. Nếu ứng dụng sử dụng reactive discovery client hoặc blocking discovery client cụ thể, chọn supplier nền tảng tương ứng theo API phiên bản đó.

Một lưu ý quan trọng: lớp cấu hình được tham chiếu bởi `@LoadBalancerClient` nên được đặt ngoài phạm vi component scan thông thường của ứng dụng, hoặc được loại khỏi component scan. Cấu hình LoadBalancer được nạp trong context riêng theo service. Nếu vô tình để cấu hình này trở thành cấu hình chung, bean tùy chỉnh có thể ảnh hưởng đến nhiều service ngoài dự kiến.

Không khai báo nhiều bean `ServiceInstanceListSupplier` cạnh tranh cho cùng một LoadBalancer context nếu chưa có chủ đích rõ ràng. Hãy bảo đảm mỗi service có một chain cuối cùng mà LoadBalancer sử dụng.

## 7. Request-aware supplier và lọc ứng viên

Phương thức `get(Request request)` cho phép supplier nhận thông tin request thay vì chỉ trả một danh sách tĩnh. Request context có thể chứa hint hoặc dữ liệu mà một supplier chuyên biệt hiểu được.

Luồng xử lý khái quát:

~~~mermaid
sequenceDiagram
    participant C as HTTP Client
    participant L as LoadBalancer
    participant S as ServiceInstanceListSupplier
    participant D as Discovery
    C->>L: Request tới service ID + context
    L->>S: get(request)
    S->>D: Lấy danh sách instance nếu cần
    D-->>S: Danh sách instance
    S->>S: Áp dụng cache / health / metadata filter
    S-->>L: Danh sách ứng viên
    L->>L: Chọn một instance
    L-->>C: Instance được chọn
~~~

Ví dụ, một hệ thống có metadata `zone` và `version` trên từng instance. Một request có thể yêu cầu phiên bản `v2`. Supplier dựa trên request context và metadata để ưu tiên hoặc giới hạn ứng viên phù hợp. Nếu không có instance nào thỏa mãn, ứng dụng cần quyết định có fallback sang phiên bản khác hay trả lỗi. Quyết định này là chính sách nghiệp vụ và triển khai, không nên để xảy ra ngẫu nhiên.

Với một filter tự viết, nên dùng mô hình delegate:

1. Nhận supplier nền tảng trong constructor.
2. Gọi `get(request)` của delegate để giữ nguyên request context.
3. Lọc hoặc sắp xếp danh sách theo metadata đã thống nhất.
4. Trả lại danh sách kết quả; không thực hiện HTTP call bên trong supplier.
5. Xác định rõ hành vi khi kết quả rỗng và kiểm thử trường hợp đó.

Không nên sửa trực tiếp danh sách dùng chung từ cache. Hãy tạo danh sách kết quả mới khi lọc để tránh làm thay đổi dữ liệu mà các request khác có thể đang sử dụng.

## 8. Supplier và thuật toán chọn instance là hai bước khác nhau

Giả sử supplier chain trả về ba ứng viên:

~~~text
[A, B, C]
~~~

Round-robin có thể chọn A, rồi B, rồi C theo các lần gọi tiếp theo. Random có thể chọn bất kỳ ứng viên nào trong danh sách. Thuật toán lựa chọn không tự biết instance nào ở zone gần hơn hoặc khỏe hơn nếu các điều kiện đó chưa được phản ánh trong danh sách hay chiến lược lựa chọn.

Có thể hình dung:

~~~mermaid
flowchart TD
    A["Discovery trả A, B, C, D"] --> B["Supplier chain"]
    B --> C["Lọc B vì health check thất bại"]
    C --> D["Ưu tiên A, C cùng zone"]
    D --> E["Danh sách cuối: A, C"]
    E --> F["RoundRobinLoadBalancer"]
    F --> G["Chọn A hoặc C"]
~~~

Nếu danh sách cuối chỉ còn một instance, bất kể thuật toán là round robin hay random, instance đó sẽ là ứng viên duy nhất. Nếu danh sách rỗng, LoadBalancer không có instance để gửi request. Ứng dụng cần xử lý lỗi không có instance khả dụng, đồng thời quan sát nguyên nhân khiến supplier loại hết ứng viên.

Supplier cũng không thay thế retry. Retry-aware supplier có thể hỗ trợ loại instance đã thử khỏi tập ứng viên trong một ngữ cảnh retry, nhưng chính sách retry, số lần thử, timeout và tính idempotent của request vẫn cần được cấu hình ở cơ chế retry tương ứng.

## 9. Kiểm thử ServiceInstanceListSupplier

Kiểm thử supplier nên tập trung vào dữ liệu đầu vào và đầu ra của từng bước. Có thể tạo các instance giả với host, port và metadata khác nhau để xác minh filter hoạt động như dự kiến.

Các trường hợp cần kiểm tra:

| Trường hợp | Kết quả mong đợi |
|---|---|
| Discovery trả về nhiều instance | Supplier nền tảng cung cấp đúng service ID và danh sách. |
| Cache còn hiệu lực | Nhiều lần đọc dùng kết quả cache theo cấu hình. |
| Instance bị đánh dấu không khỏe | Health-check supplier loại instance theo chính sách. |
| Có instance cùng zone | Zone preference ưu tiên nhóm cùng zone. |
| Không có instance cùng zone | Hành vi fallback đúng với cấu hình và phiên bản. |
| Request có hint | Supplier request-aware lọc hoặc ưu tiên theo hint. |
| Không có instance phù hợp | Trả danh sách rỗng hoặc fallback đúng chính sách đã thiết kế. |
| Discovery thay đổi danh sách | Cache cập nhật sau TTL/refresh phù hợp. |

Một kiểm thử tích hợp hữu ích là đăng ký hai hoặc ba instance của cùng service ID, gọi qua một HTTP client có `@LoadBalanced`, rồi ghi lại instance ID trong response. Kiểm thử này xác nhận cả discovery, supplier chain, thuật toán chọn instance và việc thay thế URI cùng hoạt động.

Khi kiểm thử cache, đừng chỉ kiểm tra lần gọi đầu tiên. Hãy kiểm tra thêm hành vi sau khi registry thêm hoặc xóa instance, sau khi TTL hết hạn và khi cache không thể lấy dữ liệu mới. Khi kiểm thử health check, tạo tình huống endpoint health không phản hồi để xác nhận instance được xử lý theo đúng chính sách.

## 10. Quan sát và xử lý lỗi thường gặp

Khi request không tới được service hoặc chỉ một số replica nhận request, hãy quan sát danh sách trước và sau từng bước của supplier chain.

Một số dấu hiệu thường gặp:

- **Không có instance:** service ID sai, discovery chưa đăng ký instance, registry không truy cập được hoặc supplier lọc hết ứng viên.
- **Instance cũ vẫn được chọn:** cache TTL quá dài, cache nhiều tầng hoặc registry chưa cập nhật trạng thái.
- **Instance không khỏe vẫn được chọn:** health-check supplier chưa được bật, health path sai hoặc health check không phản ánh trạng thái cần thiết.
- **Chỉ instance cùng zone được chọn:** có thể là hành vi đúng của zone preference; kiểm tra fallback khi zone đó không còn instance.
- **Request hint không có tác dụng:** client chưa truyền request context, supplier không đọc đúng loại context hoặc metadata không khớp.
- **Một service bị ảnh hưởng bởi cấu hình của service khác:** cấu hình LoadBalancer có thể đã bị component scan và áp dụng ngoài phạm vi dự kiến.

Nên ghi log hoặc metric đủ để trả lời:

- Service ID nào đang được yêu cầu?
- Supplier chain nào đang được cấu hình cho service đó?
- Danh sách instance ban đầu và số lượng ứng viên sau filter là bao nhiêu?
- Cache có trả dữ liệu cũ hay không?
- Instance bị loại vì health, zone, hint hay lý do nào?
- LoadBalancer cuối cùng chọn instance nào?

Không nhất thiết ghi toàn bộ metadata hoặc payload của request. Chỉ log các trường cần thiết, tránh thông tin bí mật và dữ liệu cá nhân. Với môi trường production, ưu tiên metric có cardinality được kiểm soát; không đưa instance ID động hoặc request ID không giới hạn vào label metric.

## 11. Những điểm cần nhớ

- `ServiceInstanceListSupplier` cung cấp danh sách ứng viên; LoadBalancer algorithm chọn một instance từ danh sách đó.
- Supplier nền tảng thường lấy dữ liệu từ discovery client, SimpleDiscoveryClient hoặc nguồn tùy chỉnh.
- Supplier chain kết hợp các decorator như cache, health check, zone preference và request-aware filtering.
- Thứ tự chain ảnh hưởng đến dữ liệu mà mỗi decorator nhận được; cache nên đặt ở vị trí phù hợp với nguồn dữ liệu và không cache nhầm kết quả phụ thuộc request.
- Cấu hình `@LoadBalancerClient` cho phép tùy chỉnh supplier theo service ID; cần giữ đúng phạm vi context.
- Danh sách rỗng có nghĩa là LoadBalancer không có ứng viên; cần kiểm tra discovery và từng điều kiện lọc.
- Kiểm thử cả danh sách đầu vào, đầu ra từng filter và luồng gọi end-to-end qua HTTP client.

Khi hiểu `ServiceInstanceListSupplier`, bạn có thể giải thích được LoadBalancer lấy ứng viên từ đâu, những điều kiện nào làm thay đổi danh sách và vì sao thuật toán lựa chọn chỉ có thể chọn trong tập instance mà supplier cung cấp.

