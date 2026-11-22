# Ánh xạ service ID sang các bản sao đang được cung cấp

Trong kiến trúc microservices, client thường biết **tên logic của dịch vụ** mà nó muốn gọi, còn hệ thống cần xác định những bản triển khai nào hiện đang cung cấp dịch vụ đó. Spring Cloud LoadBalancer giải quyết phần chọn đích bằng cách làm việc với một danh sách `ServiceInstance` gắn với service ID.

Ví dụ, client gọi `catalog-service`. Tại thời điểm tra cứu, dịch vụ này có thể có ba bản sao đang được đăng ký:

| Service ID | Instance ID | Địa chỉ |
|---|---|---|
| `catalog-service` | `catalog-1` | `http://10.0.1.21:8081` |
| `catalog-service` | `catalog-2` | `http://10.0.1.22:8081` |
| `catalog-service` | `catalog-3` | `http://10.0.1.23:8081` |

Có thể hình dung ánh xạ này như một mục tra cứu:

~~~text
catalog-service
    ├── catalog-1 -> http://10.0.1.21:8081
    ├── catalog-2 -> http://10.0.1.22:8081
    └── catalog-3 -> http://10.0.1.23:8081
~~~

Service ID là khóa để tìm nhóm instance. Mỗi instance là một đích gọi cụ thể. Danh sách có thể thay đổi khi ứng dụng khởi động, dừng, đăng ký, hủy đăng ký hoặc khi nguồn discovery cập nhật trạng thái.

## 1. Các thành phần tham gia ánh xạ

Việc ánh xạ service ID sang danh sách instance có nhiều thành phần phối hợp. Mỗi thành phần có trách nhiệm riêng:

| Thành phần | Trách nhiệm |
|---|---|
| Service registry | Lưu thông tin các dịch vụ và instance đã đăng ký |
| `DiscoveryClient` | Cung cấp API để truy vấn instance theo service ID |
| `ServiceInstanceListSupplier` | Cung cấp danh sách instance cho Spring Cloud LoadBalancer |
| LoadBalancer | Chọn một instance từ danh sách được cung cấp |
| HTTP client tích hợp | Gửi request đến địa chỉ của instance được chọn |

Service registry có thể là Eureka, Consul, Zookeeper hoặc một hệ thống discovery được tích hợp với Spring Cloud. Trong môi trường đơn giản, ứng dụng cũng có thể dùng danh sách instance cấu hình tĩnh.

`DiscoveryClient` là abstraction để truy vấn dữ liệu discovery. `ServiceInstanceListSupplier` là abstraction mà Spring Cloud LoadBalancer sử dụng để nhận danh sách ứng viên. Supplier có thể gọi discovery client, dùng cấu hình tĩnh hoặc kết hợp dữ liệu với cache và các bộ lọc.

~~~mermaid
flowchart TD
    A["Client gọi catalog-service"] --> B["Spring Cloud LoadBalancer"]
    B --> C["ServiceInstanceListSupplier"]
    C --> D["DiscoveryClient hoặc nguồn cấu hình"]
    D --> E["Danh sách ServiceInstance"]
    E --> F["Bộ lọc / cache nếu được cấu hình"]
    F --> G["Danh sách ứng viên"]
    G --> H["LoadBalancer chọn một instance"]
    H --> I["HTTP client gửi request đến URI của instance"]
~~~

Luồng thực tế có thể có thêm cache, bộ lọc hoặc supplier tùy biến. Sơ đồ mô tả mối quan hệ chính giữa service ID, nguồn cung cấp instance và bước lựa chọn đích.

## 2. Truy vấn danh sách instance bằng DiscoveryClient

Spring Cloud Commons định nghĩa interface `org.springframework.cloud.client.discovery.DiscoveryClient`. Hai thao tác thường dùng là:

- `getServices()`: lấy danh sách service ID mà discovery client biết.
- `getInstances(serviceId)`: lấy danh sách `ServiceInstance` đang được đăng ký cho service ID đó.

Ví dụ kiểm tra các bản sao của `catalog-service`:

~~~java
import java.util.List;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Component;

@Component
class ServiceDiscoveryInspector {

    private final DiscoveryClient discoveryClient;

    ServiceDiscoveryInspector(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    void printCatalogInstances() {
        List<ServiceInstance> instances =
                discoveryClient.getInstances("catalog-service");

        if (instances.isEmpty()) {
            System.out.println("Không tìm thấy instance của catalog-service");
            return;
        }

        for (ServiceInstance instance : instances) {
            System.out.printf(
                    "serviceId=%s, instanceId=%s, uri=%s%n",
                    instance.getServiceId(),
                    instance.getInstanceId(),
                    instance.getUri()
            );
        }
    }
}
~~~

Đoạn mã trên phục vụ kiểm tra dữ liệu discovery. Nó cho biết discovery client đang trả về những instance nào tại thời điểm truy vấn. Đây chưa phải là thao tác chọn instance cho một HTTP request.

Trong ứng dụng dùng discovery theo kiểu reactive, Spring Cloud cũng có abstraction `ReactiveDiscoveryClient`. API reactive trả về dữ liệu theo kiểu Reactor, phù hợp với luồng xử lý reactive. Việc chọn loại discovery client phụ thuộc integration và stack mà ứng dụng sử dụng.

Cần lưu ý rằng danh sách do `DiscoveryClient` trả về có thể khác danh sách cuối cùng mà LoadBalancer dùng. `ServiceInstanceListSupplier` có thể áp dụng cache, lọc theo zone, health check hoặc tiêu chí của request trước khi cung cấp ứng viên cho bộ chọn.

## 3. ServiceInstanceListSupplier ánh xạ service ID sang danh sách ứng viên

`ServiceInstanceListSupplier` thuộc package `org.springframework.cloud.loadbalancer.core`. Đây là thành phần trực tiếp cung cấp danh sách `ServiceInstance` cho Spring Cloud LoadBalancer.

Về mặt khái niệm, mỗi supplier gắn với một service ID và cung cấp một luồng danh sách instance:

~~~java
Flux<List<ServiceInstance>> get(Request request);
~~~

Một số điểm cần hiểu:

- Supplier làm việc với danh sách instance, không tự quyết định HTTP request sẽ được gửi đến instance nào.
- Danh sách được cung cấp có thể được tạo từ discovery client hoặc một nguồn khác.
- Supplier có thể được bọc bởi các supplier khác để thêm cache, lọc hoặc ưu tiên instance.
- Request context có thể được dùng bởi supplier có chính sách phụ thuộc vào thông tin của request.

Trong cấu hình thông thường có tích hợp discovery, Spring Cloud LoadBalancer có thể sử dụng supplier dựa trên discovery client để lấy các instance theo service ID. Ứng dụng cũng có thể tùy biến cấu hình LoadBalancer cho từng service nếu cần nguồn dữ liệu hoặc chính sách cung cấp danh sách riêng. Cách khai báo bean và chuỗi supplier cụ thể phụ thuộc phiên bản Spring Cloud đang dùng.

### Phân biệt nguồn discovery và supplier

Hai thành phần này thường được nhắc cùng nhau nhưng không thay thế cho nhau:

| Câu hỏi | Thành phần trả lời |
|---|---|
| Registry biết những service nào? | Discovery client |
| Service ID này có những instance nào trong registry? | `DiscoveryClient.getInstances(serviceId)` |
| LoadBalancer nhận danh sách ứng viên nào? | `ServiceInstanceListSupplier` |
| Trong danh sách ứng viên, instance nào được chọn? | Bộ chọn của LoadBalancer |

Sự phân tách này cho phép ứng dụng thay đổi cách cung cấp danh sách mà không phải thay đổi HTTP client. Ví dụ, cùng một service ID có thể được tra cứu từ Eureka trong môi trường triển khai và từ danh sách tĩnh trong một môi trường kiểm thử.

## 4. Nguồn cung cấp danh sách: discovery động và cấu hình tĩnh

### Discovery động từ service registry

Trong môi trường nhiều instance, mỗi bản triển khai thường đăng ký thông tin của mình với registry. Client hoặc thành phần tích hợp discovery truy vấn registry để lấy danh sách các instance theo service ID.

Ví dụ về dữ liệu registry:

~~~text
catalog-service
    catalog-1: host=10.0.1.21, port=8081
    catalog-2: host=10.0.1.22, port=8081
    catalog-3: host=10.0.1.23, port=8081
~~~

Khi một instance mới đăng ký, danh sách có thể tăng lên. Khi instance dừng và được hủy đăng ký hoặc bị registry loại bỏ sau khi mất heartbeat, danh sách có thể giảm xuống. Thời điểm client nhìn thấy thay đổi phụ thuộc cơ chế đồng bộ, heartbeat, cache và thời gian cập nhật của registry.

### Cấu hình tĩnh với SimpleDiscoveryClient

Không phải môi trường nào cũng cần một service registry độc lập. Spring Cloud Commons cung cấp `SimpleDiscoveryClient` để khai báo các instance trong cấu hình ứng dụng.

Ví dụ YAML:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://catalog-1:8081
                metadata:
                  zone: zone-a
              - uri: http://catalog-2:8081
                metadata:
                  zone: zone-b
            payment-service:
              - uri: http://payment-1:8090
~~~

Trong ví dụ này:

- `catalog-service` ánh xạ tới hai URI.
- `payment-service` ánh xạ tới một URI.
- Metadata `zone` được đính kèm với từng instance để các chính sách phù hợp có thể sử dụng.

Cấu hình tĩnh hữu ích cho phát triển cục bộ, demo hoặc kiểm thử tích hợp. Khi số lượng instance thay đổi thường xuyên, registry động thường phù hợp hơn vì thông tin có thể được cập nhật theo vòng đời triển khai.

Không nên nhầm cấu hình danh sách instance với cấu hình URL cố định trong HTTP client. Khi dùng LoadBalancer, client vẫn gọi bằng service ID, ví dụ `http://catalog-service/products`; supplier chịu trách nhiệm cung cấp các instance tương ứng.

## 5. Danh sách instance thay đổi theo vòng đời dịch vụ

Ánh xạ service ID sang instance không phải dữ liệu bất biến. Một vòng đời điển hình có thể diễn ra như sau:

1. Ứng dụng `catalog-1` khởi động và đăng ký service ID `catalog-service` cùng địa chỉ của nó.
2. Registry lưu thông tin instance và đưa nó vào kết quả tra cứu.
3. Ứng dụng `catalog-2` khởi động; danh sách của `catalog-service` có thêm một phần tử.
4. Một instance dừng có kiểm soát và hủy đăng ký; registry loại instance khỏi danh sách.
5. Nếu instance mất kết nối đột ngột, heartbeat hoặc cơ chế phát hiện lỗi của registry có thể loại bỏ nó sau một khoảng thời gian.
6. Supplier lấy dữ liệu mới theo cơ chế cập nhật hoặc hết hạn cache; LoadBalancer sử dụng danh sách ứng viên mới.

~~~mermaid
sequenceDiagram
    participant App as Catalog instance
    participant Registry as Service Registry
    participant Supplier as ServiceInstanceListSupplier
    participant LB as LoadBalancer
    App->>Registry: Đăng ký catalog-service
    Supplier->>Registry: Truy vấn danh sách
    Registry-->>Supplier: catalog-1
    App->>Registry: catalog-2 đăng ký
    Supplier->>Registry: Làm mới danh sách
    Registry-->>Supplier: catalog-1, catalog-2
    LB->>Supplier: Yêu cầu danh sách ứng viên
    Supplier-->>LB: Danh sách instance hiện có
~~~

Đây là mô hình khái niệm. Một số registry dùng cơ chế push, một số dùng polling hoặc cache; vì vậy thời điểm cập nhật danh sách ở client có thể trễ hơn thời điểm instance đăng ký hoặc dừng.

### Đăng ký thành công không đồng nghĩa instance đã sẵn sàng

Một instance có thể xuất hiện trong registry trong khi ứng dụng vẫn đang khởi tạo hoặc chưa sẵn sàng nhận traffic. Tùy cách tích hợp, registry có thể dựa trên heartbeat, trạng thái đăng ký hoặc health indicator để quản lý instance.

Vì vậy, cần phân biệt ba trạng thái:

- **Đã đăng ký:** registry có thông tin instance.
- **Được supplier cung cấp:** instance xuất hiện trong danh sách ứng viên mà LoadBalancer nhận được.
- **Có thể xử lý request:** endpoint thực sự sẵn sàng và truy cập được từ client.

Ba trạng thái này có liên quan nhưng không đảm bảo luôn trùng nhau.

## 6. Cache và lọc danh sách trước khi LoadBalancer chọn

Khi số lượng request lớn, truy vấn registry cho mọi request có thể tạo thêm tải và độ trễ. Spring Cloud LoadBalancer hỗ trợ các supplier bổ sung để kiểm soát cách danh sách được cung cấp.

Một số ví dụ:

| Supplier / cơ chế | Mục đích |
|---|---|
| `CachingServiceInstanceListSupplier` | Cache danh sách instance lấy từ supplier nền |
| `HealthCheckServiceInstanceListSupplier` | Kiểm tra sức khỏe endpoint và cung cấp các instance đạt điều kiện |
| `ZonePreferenceServiceInstanceListSupplier` | Ưu tiên instance thuộc zone phù hợp |
| `HintBasedServiceInstanceListSupplier` | Lọc hoặc ưu tiên instance dựa trên hint của request |
| `SameInstancePreferenceServiceInstanceListSupplier` | Có thể ưu tiên instance đã được sử dụng trước đó theo cơ chế hỗ trợ |

Các supplier này không nhất thiết cùng được bật trong mọi ứng dụng. Cần chọn theo yêu cầu triển khai và cấu hình đúng thứ tự khi kết hợp nhiều supplier.

### Cache ảnh hưởng đến thời điểm nhìn thấy thay đổi

Giả sử registry đã loại `catalog-2`, nhưng cache ở client vẫn còn danh sách cũ:

~~~text
Registry hiện tại:
catalog-1, catalog-3

Cache ở client:
catalog-1, catalog-2, catalog-3
~~~

Trong khoảng thời gian cache chưa làm mới, supplier có thể vẫn cung cấp `catalog-2`. Nếu LoadBalancer chọn instance đó, request có thể thất bại. Cache giúp giảm số lần truy vấn registry nhưng cần TTL và chiến lược làm mới phù hợp với tốc độ thay đổi của hệ thống.

### Health check giúp lọc endpoint không khỏe

Health check có thể kiểm tra endpoint của từng instance rồi loại những instance không đạt điều kiện khỏi danh sách ứng viên. Cơ chế này bổ sung cho discovery: registry trả lời instance nào đã đăng ký, còn health check đánh giá endpoint có đáp ứng tiêu chí sức khỏe hay không.

Health check cần được cấu hình phù hợp với ứng dụng, chẳng hạn endpoint kiểm tra, chu kỳ kiểm tra và thời gian chờ. Không nên giả định rằng chỉ cần dùng service registry là LoadBalancer tự động kiểm tra mọi endpoint bằng HTTP health check.

## 7. LoadBalancer nhận danh sách và chọn một instance

Sau khi supplier cung cấp danh sách ứng viên cho service ID, bộ chọn của Spring Cloud LoadBalancer áp dụng chính sách đã cấu hình để chọn một instance.

Ví dụ, danh sách supplier cung cấp:

~~~text
catalog-service -> [catalog-1, catalog-2, catalog-3]
~~~

Với thuật toán round-robin, các request liên tiếp có thể được phân phối luân phiên qua các instance trong danh sách. Việc chọn cụ thể còn phụ thuộc trạng thái bộ chọn, thứ tự danh sách và các bộ lọc đã áp dụng.

Điều cần phân biệt:

- Supplier trả về **danh sách ứng viên**.
- Bộ chọn quyết định **một instance cho lần gọi hiện tại**.
- HTTP client thực hiện **kết nối tới URI của instance được chọn**.

Nếu danh sách rỗng, LoadBalancer không có instance để chọn. Nếu danh sách có phần tử nhưng mọi endpoint đều không truy cập được, request vẫn có thể thất bại. Việc có danh sách không phải cam kết rằng request sẽ thành công.

## 8. Chẩn đoán khi service ID không ánh xạ được sang instance

Khi client gọi `http://catalog-service/...` nhưng không có instance phù hợp, hãy kiểm tra theo thứ tự từ định danh đến dữ liệu nguồn:

| Triệu chứng | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| Danh sách service không có `catalog-service` | Ứng dụng chưa đăng ký hoặc registry chưa nhận dữ liệu | Kiểm tra trạng thái đăng ký và tên service trên registry |
| Service có trong registry nhưng danh sách instance rỗng | Không có instance đang đăng ký hoặc truy vấn sai service ID | Gọi `getInstances("catalog-service")` và đối chiếu tên chính xác |
| DiscoveryClient có instance nhưng supplier trả danh sách rỗng | Bộ lọc, health check hoặc supplier tùy biến đã loại instance | Kiểm tra chuỗi supplier và điều kiện lọc |
| Supplier có instance cũ | Cache chưa hết hạn hoặc dữ liệu discovery chưa đồng bộ | Kiểm tra TTL, lịch làm mới và heartbeat |
| Chọn được instance nhưng kết nối thất bại | Host/port không thể truy cập hoặc ứng dụng chưa sẵn sàng | Kiểm tra từ đúng môi trường mạng của client |
| Chỉ một số client không thấy instance | Khác cấu hình discovery, namespace, zone hoặc quyền truy cập registry | So sánh cấu hình và phạm vi discovery giữa các client |

Một số lỗi quan trọng cần phân biệt:

**Sai service ID.** Client gọi `catalog-service` nhưng ứng dụng đăng ký tên `catalog`. Cần thống nhất tên dịch vụ giữa URL logic, registry và cấu hình LoadBalancer.

**Registry không cập nhật kịp.** Instance vừa khởi động hoặc dừng nhưng client chưa nhìn thấy thay đổi. Kiểm tra heartbeat, cơ chế đồng bộ và cache trước khi kết luận thuật toán cân bằng tải có lỗi.

**Supplier lọc hết danh sách.** Bộ lọc zone hoặc health check có thể loại mọi instance nếu metadata, zone hoặc endpoint kiểm tra được cấu hình sai. Hãy kiểm tra danh sách trước và sau từng bước lọc.

**Instance có trong danh sách nhưng không thể truy cập.** Kiểm tra host và port từ container hoặc máy đang chạy client. Kết quả kiểm tra từ máy phát triển có thể khác với kết quả trong mạng triển khai.

## 9. Thực hành kiểm tra ánh xạ service ID

Có thể dùng một bài kiểm tra đơn giản để xác nhận registry đang trả về danh sách instance như mong đợi:

1. Khởi động ít nhất hai bản sao của `catalog-service`.
2. Xác nhận mỗi bản sao đăng ký đúng cùng service ID.
3. Gọi `DiscoveryClient.getInstances("catalog-service")` và ghi lại instance ID cùng URI.
4. Dừng có kiểm soát một bản sao, chờ registry cập nhật rồi truy vấn lại.
5. Kiểm tra danh sách mà supplier cung cấp để xác định cache hoặc bộ lọc có làm thay đổi kết quả hay không.
6. Gửi request qua HTTP client tích hợp LoadBalancer và quan sát instance thực sự xử lý request.

Khi ghi log để chẩn đoán, nên có service ID, instance ID, URI, thời điểm truy vấn và nguồn dữ liệu. Tránh chỉ ghi “không tìm thấy service”, vì thông tin đó chưa phân biệt được lỗi đăng ký, lỗi truy vấn hay lỗi lọc danh sách.

## 10. Nguyên tắc thiết kế ánh xạ service ID

Một ánh xạ service ID ổn định cần đáp ứng các nguyên tắc sau:

- Dùng một service ID nhất quán giữa client, registry và cấu hình LoadBalancer.
- Mỗi instance phải công bố host và port truy cập được từ mạng của client.
- Cập nhật đăng ký và hủy đăng ký theo vòng đời ứng dụng.
- Chọn TTL/cache phù hợp với tần suất thay đổi instance.
- Bật health check hoặc bộ lọc khi hệ thống cần loại endpoint không sẵn sàng.
- Quan sát cả danh sách từ discovery client, danh sách từ supplier và instance cuối cùng được chọn.

Service ID giúp client tìm đúng nhóm dịch vụ. Discovery cung cấp dữ liệu về các bản triển khai, còn `ServiceInstanceListSupplier` đưa danh sách ứng viên vào Spring Cloud LoadBalancer. Khi hiểu rõ từng bước, có thể xác định chính xác lỗi nằm ở đăng ký dịch vụ, cập nhật danh sách, lọc instance hay kết nối đến endpoint được chọn.

