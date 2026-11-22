# Chính sách khi không có bản sao trong vùng ưu tiên

Trong hệ thống microservices triển khai trên nhiều **zone** (vùng khả dụng hoặc nhóm hạ tầng), client thường muốn gọi bản sao ở gần nó trước. Gọi cùng zone có thể giảm độ trễ mạng, lưu lượng liên vùng và chi phí truyền dữ liệu. Tuy nhiên, khi vùng ưu tiên không còn bản sao đủ điều kiện, hệ thống phải quyết định có nên **chuyển sang vùng khác (fallback)** hay **ngừng định tuyến (fail closed)**.

Spring Cloud LoadBalancer hỗ trợ ưu tiên zone qua `ZonePreferenceServiceInstanceListSupplier`. Điểm cốt lõi là **đây là chính sách ưu tiên mềm (soft preference)**: nếu không tìm thấy `ServiceInstance` cùng zone, supplier mặc định **trả lại toàn bộ danh sách mà supplier phía dưới cung cấp**. Nó không mặc định từ chối request chỉ vì vùng ưu tiên không có instance, cũng không có thứ tự ưu tiên nhiều vùng dự phòng.

Bài học phân tích quy tắc này, các tình huống biên và cách lựa chọn chính sách phù hợp với yêu cầu độ sẵn sàng, độ trễ, chi phí và giới hạn dữ liệu của hệ thống.

## 1. Bối cảnh: client có vùng ưu tiên, server có metadata zone

Giả sử `order-service` chạy tại `zone-a` và gọi `catalog-service`. Danh sách instance được discovery cung cấp gồm:

| Instance ID | Địa chỉ | Metadata `zone` |
|---|---|---|
| `catalog-a1` | `10.1.1.11:8080` | `zone-a` |
| `catalog-a2` | `10.1.1.12:8080` | `zone-a` |
| `catalog-b1` | `10.2.1.21:8080` | `zone-b` |
| `catalog-c1` | `10.3.1.31:8080` | `zone-c` |

Client có thể khai báo vùng ưu tiên bằng:

~~~yaml
spring:
  cloud:
    loadbalancer:
      zone: zone-a
~~~

`ZonePreferenceServiceInstanceListSupplier` đọc giá trị zone của client và đối chiếu với metadata key **`zone`** của từng `ServiceInstance`. Khi còn hai instance cùng vùng, danh sách ứng viên thường chỉ gồm `catalog-a1` và `catalog-a2`; thuật toán như round-robin mới chọn một instance từ danh sách này.

~~~mermaid
flowchart TD
    A["order-service ở zone-a"]
    B["ServiceInstanceListSupplier<br/>catalog-service có 4 instance"]
    C{"Có instance<br/>zone-a?"}
    D["Ưu tiên danh sách<br/>catalog-a1, catalog-a2"]
    E["Fallback danh sách từ delegate<br/>tất cả instance còn được cung cấp"]
    F["LoadBalancer chọn một instance"]
    A --> B
    B --> C
    C -->|"Có"| D
    C -->|"Không"| E
    D --> F
    E --> F
~~~

Zone của client là tiêu chí cấu hình cho cơ chế ưu tiên; zone của server là thuộc tính metadata. Cả hai phải khớp về ý nghĩa thì việc lọc mới đạt mục tiêu.

## 2. Hành vi mặc định khi không có instance trong vùng ưu tiên

`ZonePreferenceServiceInstanceListSupplier` nhận danh sách từ supplier bên dưới (delegate), sau đó xử lý về mặt logic như sau:

1. Xác định zone được cấu hình cho LoadBalancer client.
2. Lọc các instance có metadata `zone` trùng với zone của client.
3. **Nếu danh sách khớp không rỗng**, trả về danh sách khớp.
4. **Nếu zone client chưa được xác định hoặc danh sách khớp rỗng**, trả lại toàn bộ danh sách mà delegate đã cung cấp.

Có thể diễn đạt bằng mã Java thuần để hiểu thuật toán:

~~~java
import java.util.List;
import java.util.Map;
import org.springframework.cloud.client.ServiceInstance;

// Minh họa logic lựa chọn ứng viên, không thay thế bean supplier của framework.
static List<ServiceInstance> preferZone(
        List<ServiceInstance> candidates, String preferredZone) {

    if (preferredZone == null) {
        return candidates;
    }

    List<ServiceInstance> sameZone = candidates.stream()
            .filter(instance -> {
                Map<String, String> metadata = instance.getMetadata();
                String zone = metadata == null ? null : metadata.get("zone");
                return zone != null && preferredZone.equalsIgnoreCase(zone);
            })
            .toList();

    return sameZone.isEmpty() ? candidates : sameZone;
}
~~~

Đây là logic **lọc danh sách ứng viên**, chưa phải thao tác gửi HTTP. Sau khi nhận kết quả, một `ReactorLoadBalancer` hoặc bộ chọn tương ứng mới chọn `ServiceInstance` để HTTP client kết nối.

### Các trường hợp điển hình

| Zone client | Danh sách từ delegate | Danh sách sau ZonePreference | Ý nghĩa |
|---|---|---|---|
| `zone-a` | A1, A2, B1 | A1, A2 | Có cùng zone: chỉ giữ A1, A2 |
| `zone-a` | B1, C1 | B1, C1 | Không có cùng zone: fallback sang toàn bộ danh sách |
| `zone-a` | B1 không có metadata `zone` | B1 | Không có match nhưng delegate có instance: vẫn fallback |
| Chưa cấu hình zone client | A1, B1, C1 | A1, B1, C1 | Không lọc theo zone |
| `zone-a` | Danh sách rỗng | Danh sách rỗng | Không có đích để chọn, fallback cũng không tạo ra instance |

**Fallback không đảm bảo request thành công.** Nó chỉ mở rộng tập ứng viên khi thiếu instance cùng vùng. Những instance vùng khác vẫn có thể không truy cập được hoặc không đáp ứng yêu cầu ứng dụng.

## 3. Khi vùng ưu tiên biến mất: điều gì thay đổi?

Giả sử ban đầu `catalog-service` có:

~~~text
zone-a: catalog-a1, catalog-a2
zone-b: catalog-b1
zone-c: catalog-c1
~~~

Trong lúc bình thường, client ở `zone-a` chỉ chọn giữa A1 và A2. Nếu A1 và A2 được hủy đăng ký và supplier bên dưới đã cập nhật danh sách còn B1, C1:

~~~text
Trước sự cố:
  delegate = [A1, A2, B1, C1]
  cùng zone = [A1, A2]
  LoadBalancer chọn A1 hoặc A2

Sau khi discovery cập nhật:
  delegate = [B1, C1]
  cùng zone = []
  fallback = [B1, C1]
  LoadBalancer chọn B1 hoặc C1
~~~

Đây là **fallback theo danh sách ứng viên**, không phải một chuỗi “thử A1, rồi tự chuyển B1 nếu HTTP timeout”. Chính sách chỉ nhìn thấy những instance còn được supplier cung cấp và các metadata của chúng.

Nếu registry/cache vẫn giữ A1 và A2 trong danh sách dù hai tiến trình đã chết, bộ lọc zone vẫn nhìn thấy các instance cùng vùng và **chưa chuyển sang B1/C1**. Để ứng xử tốt với sự cố, cơ chế đăng ký, TTL cache và health check cần phản ánh được tình trạng instance.

## 4. Những giới hạn của fallback mặc định

Một số hiểu nhầm có thể khiến chính sách định tuyến không đáp ứng yêu cầu vận hành.

### Không có thứ tự vùng dự phòng

Khi không còn instance ở `zone-a`, mặc định danh sách B1, C1 được trả lại cùng nhau. `ZonePreferenceServiceInstanceListSupplier` không tự hiểu rằng `zone-b` gần hơn `zone-c` hoặc phải ưu tiên `zone-b` trước `zone-c`.

Nếu muốn thứ tự `zone-a → zone-b → zone-c`, cần chính sách lọc/supplier tùy biến có hiểu biết về thứ tự vùng hoặc một giải pháp định tuyến khác được cấu hình rõ ràng.

### Không tự kiểm tra sức khỏe HTTP

Có mặt trong danh sách discovery không chứng minh instance thực sự xử lý được request. Lọc theo zone không đồng nghĩa đã chạy health check. Hệ thống có thể cần trạng thái sức khỏe từ service registry hoặc `HealthCheckServiceInstanceListSupplier` tùy cách khám phá dịch vụ.

### Không tự retry khi một request thất bại

Chuyển vùng trong danh sách ứng viên khác với **retry một request HTTP lỗi**. Khi đã chọn B1 mà kết nối thất bại, việc có thử tiếp C1 hay không phụ thuộc vào retry policy, tích hợp RestClient/WebClient/OpenFeign và cấu hình cụ thể. Bật zone preference không tự bảo đảm có retry.

### Không bảo đảm cách ly dữ liệu hoặc quyền truy cập

Fallback mềm có thể đưa request sang vùng khác. Nếu ứng dụng có yêu cầu pháp lý, lưu trú dữ liệu, phân tách tenant hoặc giới hạn quyền truy cập theo khu vực, không nên coi zone preference là hàng rào bảo vệ. Phải thực thi chính sách kiểm soát ở lớp hạ tầng, dịch vụ và dữ liệu tương ứng.

## 5. Cấu hình zone preference trong Spring Cloud

Có hai cách thiết lập thường gặp: dùng cấu hình có sẵn hoặc cấu hình supplier cho một service cụ thể. Cả hai đều dựa trên metadata `zone` của server và zone mong muốn ở client.

### Cách 1: Bật cấu hình có sẵn

Với Spring Cloud LoadBalancer có hỗ trợ cấu hình `zone-preference`, có thể bật qua thuộc tính:

~~~yaml
spring:
  cloud:
    loadbalancer:
      zone: zone-a
      configurations: zone-preference
~~~

Giá trị `zone-preference` chọn cấu hình supplier phù hợp có ưu tiên vùng. Khi có nhiều dịch vụ với nhu cầu khác nhau, nên cân nhắc cấu hình LoadBalancer riêng theo service ID thay vì áp dụng một chính sách chung không phù hợp.

Ứng dụng cần dependency Spring Cloud LoadBalancer tương thích với Spring Boot/Spring Cloud release train đang dùng và nguồn `ServiceInstance` (discovery client hoặc cấu hình tĩnh).

### Cách 2: Khai báo supplier cho service ID cụ thể

Ví dụ dưới đây tạo chuỗi **discovery → cache → zone preference** cho `catalog-service`:

~~~java
import org.springframework.cloud.loadbalancer.annotation.LoadBalancerClient;
import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@LoadBalancerClient(
        name = "catalog-service",
        configuration = CatalogZoneSupplierConfiguration.class
)
class CatalogRoutingConfiguration {}

// Không đánh dấu @Configuration nếu lớp này nằm trong component scan
// của application context chính; nó được nạp cho child context của service.
class CatalogZoneSupplierConfiguration {

    @Bean
    ServiceInstanceListSupplier catalogSupplier(
            ConfigurableApplicationContext context) {
        return ServiceInstanceListSupplier.builder()
                .withDiscoveryClient()
                .withCaching()
                .withZonePreference()
                .build(context);
    }
}
~~~

Khi dùng cách 2, không cần đồng thời đặt `spring.cloud.loadbalancer.configurations: zone-preference` nếu đã tạo chuỗi riêng cho `catalog-service`. Kiểm tra cách cấu hình tương ứng với phiên bản thư viện và đảm bảo class cấu hình riêng không bị component scan như bean dùng chung ngoài ý muốn.

Tài liệu Spring Cloud cũng đề nghị đặt cache trực tiếp sau supplier lấy instance qua mạng và trước các bước lọc, để tránh cache kết quả phụ thuộc chính sách ở vị trí không phù hợp. Nếu discovery client đã có cache riêng, có thể cân nhắc tắt lớp cache bổ sung.

### Chuẩn bị dữ liệu vùng bằng SimpleDiscoveryClient

Trong thử nghiệm nhỏ, có thể khai báo các instance bằng cấu hình tĩnh:

~~~yaml
spring:
  cloud:
    loadbalancer:
      zone: zone-a
      configurations: zone-preference
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://127.0.0.1:8081
                metadata:
                  zone: zone-a
              - uri: http://127.0.0.1:8082
                metadata:
                  zone: zone-a
              - uri: http://127.0.0.1:8083
                metadata:
                  zone: zone-b
~~~

Cấu hình trên là **một ví dụ độc lập**: client có vùng ưu tiên `zone-a`, hai endpoint thuộc vùng này, một endpoint ở `zone-b`. Trong triển khai thực tế, dùng địa chỉ host/port mà client có thể truy cập trong mạng của nó; `127.0.0.1` chỉ phù hợp khi các server thử nghiệm cùng chia sẻ localhost với client.

Với Eureka, một số cấu hình zone có thể được tích hợp từ thông tin discovery. Với nguồn discovery khác, thiết lập tường minh `spring.cloud.loadbalancer.zone` giúp tránh trường hợp zone client không được xác định và toàn bộ danh sách bị coi như không cần lọc.

## 6. Thiết kế chính sách khi không có bản sao cùng zone

Không phải hệ thống nào cũng nên dùng fallback mặc định. Chọn chính sách dựa trên mục tiêu của từng dịch vụ.

| Chính sách | Khi vùng ưu tiên không có instance | Phù hợp khi | Đánh đổi |
|---|---|---|---|
| **Ưu tiên mềm (mặc định)** | Trả toàn bộ instance do delegate cung cấp | Dịch vụ có thể chạy xuyên vùng, ưu tiên tính sẵn sàng | Độ trễ/chi phí liên vùng tăng, mất kiểm soát thứ tự vùng |
| **Cứng theo vùng (strict)** | Trả danh sách rỗng hoặc chủ động từ chối lời gọi | Cần chỉ định tuyến trong vùng được cho phép | Dễ mất khả dụng khi vùng đó không có instance |
| **Thứ tự dự phòng** | Thử các vùng theo thứ tự ưu tiên đã thiết kế | Có yêu cầu gần nhất, vùng DR hoặc chi phí cụ thể | Cần xây dựng/chứng minh đúng chính sách |
| **Cho phép một tập vùng** | Chỉ chọn trong vùng được duyệt; rỗng thì từ chối hoặc fallback trong tập | Có giới hạn vùng nhưng vẫn cần dự phòng | Cần đồng bộ metadata và danh sách vùng hợp lệ |

Quy tắc quan trọng là định nghĩa “không có bản sao” theo **danh sách sau bước lọc nào**. Nếu health check đã loại instance lỗi, danh sách cùng zone có thể rỗng dù registry vẫn có bản ghi trong vùng. Nếu chưa có health check, một instance đã chết nhưng vẫn ở cache có thể ngăn fallback xảy ra.

### Chính sách strict phải được triển khai rõ

Nếu hệ thống yêu cầu chỉ được gọi instance ở `zone-a`, không thể chỉ dùng `ZonePreferenceServiceInstanceListSupplier` mặc định và mong rằng nó trả danh sách rỗng khi không có match.

Hãy xem một hàm minh họa chính sách lọc chặt:

~~~java
import java.util.List;
import java.util.Map;
import org.springframework.cloud.client.ServiceInstance;

static List<ServiceInstance> strictZoneCandidates(
        List<ServiceInstance> candidates, String requiredZone) {

    if (requiredZone == null || requiredZone.isBlank()) {
        return List.of(); // Không biết vùng bắt buộc: từ chối chọn.
    }

    return candidates.stream()
            .filter(instance -> {
                Map<String, String> metadata = instance.getMetadata();
                String zone = metadata == null ? null : metadata.get("zone");
                return zone != null && requiredZone.equalsIgnoreCase(zone);
            })
            .toList();
}
~~~

Đây là logic cốt lõi có thể dùng trong một `ServiceInstanceListSupplier` tùy biến; **đoạn hàm đứng riêng chưa đăng ký chính sách vào Spring Cloud LoadBalancer**. Khi danh sách kết quả rỗng, tầng chọn đích không có instance để gửi request. Mã trạng thái hoặc exception hiển thị cho caller tùy adapter HTTP và cấu hình lỗi.

Đối với dữ liệu nhạy cảm theo khu vực, strict routing vẫn cần phối hợp kiểm soát quyền, network policy và phân vùng lưu trữ; nó không thay thế kiểm soát truy cập.

### Chính sách dự phòng theo thứ tự

Ví dụ một hệ thống đặt thứ tự vùng `zone-a → zone-b → zone-c`:

~~~text
Nếu zone-a có ứng viên:  chọn trong zone-a.
Nếu zone-a rỗng:        thử zone-b.
Nếu zone-b cũng rỗng:    thử zone-c.
Nếu tất cả đều rỗng:     trả về không có ứng viên.
~~~

Hành vi này cần supplier/chính sách tùy biến. Khi triển khai, phải xác định rõ cách xử lý metadata thiếu `zone`, cách loại instance không khỏe, và sự khác nhau giữa **fallback khi danh sách rỗng** với **retry sang vùng khác sau lỗi HTTP**.

## 7. Kết hợp zone preference với discovery, health check và cache

Chính sách fallback chịu ảnh hưởng trực tiếp từ danh sách do các supplier phía dưới cung cấp. Có thể hình dung chuỗi thành phần như sau:

~~~mermaid
flowchart TD
    A["Discovery<br/>danh sách instance hiện biết"]
    B["Cache nếu được cấu hình"]
    C["Health filtering nếu được cấu hình"]
    D["ZonePreferenceServiceInstanceListSupplier"]
    E["RoundRobin / thuật toán chọn"]
    F["RestClient / WebClient / OpenFeign"]
    A --> B
    B --> C
    C --> D
    D --> E
    E --> F
~~~

Đây là mô hình khái niệm về **dữ liệu đi vào zone preference**, không phải một công thức thứ tự bean áp dụng cho mọi phiên bản và mọi loại health check. `HealthCheckServiceInstanceListSupplier` có cơ chế giữ kết quả riêng; Spring Cloud khuyến nghị kiểm tra kỹ thứ tự và việc dùng thêm cache để tránh hai lớp cache không cần thiết.

### Tình huống A: Instance cùng zone biến mất khỏi registry

`zone-a` không còn trong danh sách trả về. Supplier zone preference nhận danh sách từ vùng khác, nên fallback xảy ra ngay khi dữ liệu mới đến được tầng này.

### Tình huống B: Instance cùng zone chết nhưng registry chưa loại bỏ

`catalog-a1` vẫn có metadata `zone=zone-a`. Bộ lọc vẫn ưu tiên A1, dù request có thể gặp `connection refused` hoặc timeout. Cần sửa độ mới của registry/cache hoặc cơ chế health filtering; chỉ thay đổi thuật toán round-robin không giải quyết được.

### Tình huống C: Không còn instance nào trong toàn bộ dịch vụ

Delegate trả danh sách rỗng. Zone preference cũng trả rỗng. HTTP client tích hợp LoadBalancer thường báo không có server khả dụng theo cơ chế riêng, chẳng hạn response lỗi hoặc exception; không có lựa chọn fallback hợp lệ.

## 8. Fallback theo zone khác retry, timeout và circuit breaker

Một request có thể thành công trong giai đoạn lựa chọn nhưng thất bại khi thực thi HTTP. Vì vậy cần phân biệt:

- **Zone fallback:** điều chỉnh danh sách ứng viên trước khi LoadBalancer chọn một instance.
- **Retry:** thử lại lời gọi sau một lỗi theo điều kiện đã cấu hình; có thể chọn lại instance tùy integration và retry policy.
- **Timeout:** giới hạn thời gian kết nối hoặc chờ phản hồi theo HTTP client.
- **Circuit breaker:** hạn chế tiếp tục gọi một đường đi/nhóm request đang có tỉ lệ lỗi cao theo cấu hình.

Ví dụ, khi `catalog-a1` còn trong registry nhưng đã chết, zone preference vẫn có thể chọn A1. Nếu bật retry có khả năng chọn instance khác, request sau có thể thử A2. Tuy nhiên, retry không tự bảo đảm chuyển sang `zone-b` khi supplier vẫn ưu tiên các instance `zone-a`.

Nếu cần tự động “vùng gần nhất thất bại → chuyển sang vùng dự phòng”, phải thiết kế cách nhận biết lỗi, làm mới/loại ứng viên hỏng và retry/failover như một quy trình có kiểm soát. Với các request có tác dụng phụ như thanh toán, cần xử lý idempotency để tránh thực hiện nghiệp vụ trùng lặp.

## 9. Rủi ro của fallback xuyên vùng

Cho phép chuyển vùng tăng khả năng tiếp tục phục vụ nhưng có thể tạo các tác động vận hành:

| Rủi ro | Biểu hiện | Biện pháp |
|---|---|---|
| Độ trễ liên vùng | p95/p99 latency tăng khi toàn bộ request sang vùng khác | Theo dõi latency theo zone nguồn/đích, đặt timeout hợp lý |
| Chi phí mạng | Lưu lượng egress/inter-zone tăng | Đo lượng request và dữ liệu truyền xuyên vùng |
| Quá tải vùng dự phòng | Vùng còn sống nhận lưu lượng đột biến | Capacity planning, autoscaling, giới hạn lưu lượng |
| Lỗi kết nối xuyên vùng | Firewall, DNS, TLS hoặc routing chưa hỗ trợ | Kiểm tra thực tế đường đi từ client tới vùng dự phòng |
| Mất ràng buộc dữ liệu | Request sang vùng không được phép xử lý | Thực thi allowlist vùng, kiểm soát dữ liệu và quyền ngoài LoadBalancer |
| Chuyển vùng liên tục | Danh sách discovery/health thay đổi nhiều | Health/caching phù hợp, giám sát ổn định và cân nhắc hysteresis |

Một fallback thành công về mặt kết nối chưa chắc đáp ứng mục tiêu SLO hoặc ràng buộc nghiệp vụ. Do đó, nên coi trạng thái “đang gọi khác zone” là tín hiệu cần quan sát.

## 10. Quan sát và chẩn đoán khi không thấy instance cùng zone

Để tìm đúng nguyên nhân, cần nhìn **danh sách trước lọc**, **danh sách sau lọc**, **zone client** và **instance đã chọn**:

| Hiện tượng | Điều cần kiểm tra |
|---|---|
| Client luôn gọi xuyên vùng dù zone-a có instance | `spring.cloud.loadbalancer.zone`, metadata `zone` của instance, supplier zone có thực sự được bật hay không |
| Vùng ưu tiên đã hết instance nhưng không fallback | Cache/discovery còn instance cùng zone; bộ lọc khác có thay đổi danh sách hay không |
| Fallback sang zone-c dù zone-b gần hơn | Mặc định không có thứ tự ưu tiên zone-b trước zone-c |
| Không tìm thấy server nào | Delegate có trả danh sách rỗng hay mọi instance bị loại bởi supplier khác |
| Có fallback nhưng request vẫn timeout | Đường mạng đến vùng khác, HTTP client timeout, tài nguyên backend |
| Lưu lượng liên vùng tăng đột ngột | Có thể do vùng ưu tiên mất instance, metadata bị sai hoặc client zone chưa cấu hình |

Ví dụ hai dòng log tự thiết kế:

~~~text
serviceId=catalog-service preferredZone=zone-a
delegateCandidates=2 sameZoneCandidates=0 crossZoneFallback=true
selectedInstance=catalog-b1 selectedZone=zone-b
httpStatus=200 durationMs=82
~~~

Đây là ví dụ định dạng log mong muốn; Spring Cloud không nhất thiết tự ghi các field này với tên như trên. Nên tích hợp Micrometer/Tracing, log có correlation ID hoặc quan sát phù hợp để kết nối quyết định chọn instance với kết quả HTTP.

Cần phân biệt `sameZoneCandidates=0` vì **thực sự không còn instance** với `sameZoneCandidates=0` do **metadata `zone` bị thiếu hoặc sai**. Hai nguyên nhân này dẫn đến cùng fallback mặc định nhưng cách khắc phục khác nhau.

## 11. Bài thực hành kiểm tra chính sách fallback

Có thể tạo một thử nghiệm cục bộ gồm ba instance của `catalog-service`:

1. Chạy server A1 ở cổng `8081`, A2 ở `8082`, B1 ở `8083`; mỗi server trả về instance ID của mình ở `GET /whoami`.
2. Cấu hình `SimpleDiscoveryClient` để A1/A2 có metadata `zone=zone-a`, B1 có `zone=zone-b`.
3. Thiết lập `spring.cloud.loadbalancer.zone=zone-a` và bật `zone-preference`.
4. Gửi nhiều request bằng `RestClient`, `WebClient` hoặc OpenFeign đã tích hợp LoadBalancer. Khi các endpoint còn chạy, quan sát traffic được chọn trong A1/A2.
5. Thay danh sách cấu hình cho lần chạy tiếp theo để chỉ còn B1, hoặc hủy đăng ký A1/A2 qua registry động. Sau khi dữ liệu cập nhật, kiểm tra fallback tới B1.
6. Thử bỏ thuộc tính zone của client: danh sách ứng viên sẽ không bị giới hạn theo cùng vùng.
7. Thử cấu hình danh sách instance rỗng: xác minh client báo không có đích.
8. Nếu muốn kiểm tra strict policy, dùng supplier tùy biến trả danh sách rỗng khi `zone-a` không có match, rồi so sánh kết quả.

Khi dùng `SimpleDiscoveryClient`, việc sửa file cấu hình thường cần khởi động lại ứng dụng hoặc cơ chế refresh phù hợp; không nên mặc định rằng chỉnh `application.yml` khi tiến trình đang chạy sẽ cập nhật ngay danh sách.

### Tiêu chí đánh giá kết quả

| Tình huống | Kết quả kỳ vọng với ZonePreference mặc định |
|---|---|
| Có A1, A2 ở zone-a và B1 ở zone-b | Chọn A1 hoặc A2 |
| Chỉ còn B1 ở zone-b | Có thể chọn B1 qua fallback |
| Có A1 trong discovery nhưng A1 đã chết | Có thể vẫn chọn A1 đến khi danh sách nguồn thay đổi hoặc bị lọc |
| Không thiết lập zone client | Chọn trong toàn bộ instance do delegate cung cấp |
| Danh sách nguồn rỗng | Không có instance để chọn |
| Chỉ có B1, C1 trong hai vùng dự phòng | Cả B1 và C1 là ứng viên; không mặc định ưu tiên B1 |

## 12. Những nguyên tắc nên ghi nhớ

- **Ưu tiên zone mặc định là soft preference:** không có instance cùng zone thì trả về toàn bộ danh sách do delegate cung cấp.
- **Fallback không tự tạo instance:** nếu danh sách nguồn rỗng, kết quả vẫn rỗng.
- **Fallback không tương đương retry HTTP:** request lỗi sau khi chọn instance cần cơ chế xử lý riêng.
- **Mức độ sẵn sàng phụ thuộc độ mới của discovery/health:** instance chết nhưng vẫn xuất hiện cùng zone có thể ngăn fallback xảy ra.
- **Không có thứ tự các vùng dự phòng mặc định:** muốn `zone-a → zone-b → zone-c` phải cấu hình/chế tác chính sách riêng.
- **Dữ liệu/tenant nhạy cảm cần giới hạn cứng:** không dùng zone preference mềm làm công cụ phân quyền hay bảo đảm lưu trú dữ liệu.
- **Cần quan sát việc fallback:** theo dõi zone nguồn/đích, số lần fallback, tỉ lệ lỗi, latency và chi phí mạng.

Trong Spring Cloud LoadBalancer, `ZonePreferenceServiceInstanceListSupplier` chỉ thay đổi **danh sách ứng viên** mà thuật toán chọn instance nhìn thấy. Khi vùng ưu tiên rỗng, hành vi mặc định giúp hệ thống vẫn có cơ hội gọi các bản sao ở vùng khác; chính sách strict, thứ tự dự phòng, retry và quan sát chất lượng HTTP phải được thiết kế rõ theo yêu cầu của từng dịch vụ.

**Tài liệu tham khảo:** [Spring Cloud Commons – Zone-Based Load-Balancing](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html#zone-based-load-balancing).

