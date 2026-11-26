# Chọn thành phần cho health group của ứng dụng

Trong chương **Actuator và sức khỏe** của module **SPRING_CLOUD_KUBERNETES**, việc chọn thành phần cho health group là một quyết định vận hành: kết quả kiểm tra sẽ khiến Kubernetes tiếp tục gửi traffic, ngừng gửi traffic hay khởi động lại container. Gom mọi indicator vào một nhóm có thể biến sự cố của một dịch vụ dùng chung thành sự cố của toàn bộ các Pod.

Bài học này xây dựng cách chọn nhóm cho ứng dụng Spring tích hợp Kubernetes qua DiscoveryClient, ConfigMap, Secret và Spring Cloud LoadBalancer. Configuration Watcher được xét ở vai trò cập nhật cấu hình; thông tin sức khỏe của chính ứng dụng vẫn cần phản ánh khả năng phục vụ thực tế của từng instance.

Sau bài học, bạn có thể:

- Phân biệt health tổng thể, health group và health của một thành phần.
- Chọn thành phần cho `liveness`, `readiness` và nhóm chẩn đoán dựa trên hành động cần thực hiện.
- Nhận diện khi nào database, cache, discovery hoặc Kubernetes API thực sự nên ảnh hưởng đến readiness.
- Viết một indicator kiểm tra cấu hình đang có hiệu lực và đưa nó vào nhóm phù hợp.
- Dự đoán kết quả khi lỗi RBAC, mất kết nối hoặc cập nhật cấu hình thất bại.

Các ví dụ cấu hình và Java trong bài dùng **Spring Boot 3.5.x**, **Spring Cloud Kubernetes 3.3.x** và Java 17 trở lên. Dự án cần chọn Spring Cloud release train tương thích, quản lý phiên bản bằng BOM của dự án và có `spring-boot-starter-actuator`. Ví dụ database giả định ứng dụng đã có JDBC `DataSource` nên Actuator đăng ký contributor `db`. Khi dùng phiên bản khác hoặc ứng dụng reactive, đối chiếu API và contributor thực tế trước khi áp dụng.

## 1. Bắt đầu từ hành động sau khi nhóm báo lỗi

Một health group tập hợp một số health contributor đã đăng ký, tổng hợp trạng thái của chúng và cung cấp một góc nhìn qua endpoint riêng. Nhóm không tự tạo database connection, không tự bật một tính năng Spring Cloud và không tự cấu hình probe trong Kubernetes.

Với base path mặc định:

| Địa chỉ | Câu hỏi cần trả lời | Người hoặc hệ thống sử dụng |
| --- | --- | --- |
| `/actuator/health` | Các contributor đang báo trạng thái gì ở mức tổng thể? | Hệ thống giám sát và người vận hành |
| `/actuator/health/liveness` | Instance có đang ở trạng thái sống phù hợp để tiếp tục chạy? | Kubelet, nếu được cấu hình làm liveness probe |
| `/actuator/health/readiness` | Instance có nên nhận yêu cầu mới? | Kubelet, nếu được cấu hình làm readiness probe |
| `/actuator/health/dependencies` | Những dependency được chọn đang gặp vấn đề gì? | Người vận hành hoặc giám sát nội bộ |

`dependencies` là tên nhóm tự đặt trong bài. Không có quy tắc buộc một nhóm tùy biến phải trở thành probe.

Ví dụ thiết kế: một ứng dụng bán hàng dùng PostgreSQL để ghi đơn hàng và Redis để tăng tốc đọc danh mục. Khi Redis lỗi nhưng đọc trực tiếp từ database vẫn được, đưa Redis vào readiness có thể làm mất cả khả năng đọc đang hoạt động. Khi PostgreSQL lỗi, cần xét ứng dụng còn phục vụ được những chức năng nào trước khi quyết định loại cả Pod khỏi traffic.

**Mỗi thành phần được thêm vào nhóm cần đi kèm một câu giải thích: lỗi này có đáng để kích hoạt hành động của bên đọc nhóm hay không?**

## 2. Tách liveness, readiness và chẩn đoán

### 2.1. Liveness: tránh dùng khởi động lại để chữa lỗi bên ngoài

Một database dùng chung mất kết nối thường không được sửa bằng cách khởi động lại hàng loạt ứng dụng. Vì vậy, lựa chọn nền tảng trong bài là chỉ đưa `livenessState` vào liveness. Những dependency như Kubernetes API, database, Redis, broker và dịch vụ HTTP bên ngoài được đánh giá ở nơi khác.

Lưu ý rằng `livenessState` phản ánh trạng thái availability do Spring Boot quản lý hoặc do ứng dụng chủ động cập nhật. Nó không phải bộ phát hiện tự động mọi deadlock, lỗi nghiệp vụ hoặc rò rỉ tài nguyên. Kiểm tra HTTP trên cổng phục vụ giúp phát hiện thêm tình huống không trả lời được, nhưng cũng không chứng minh mọi luồng xử lý đều hoạt động.

### 2.2. Readiness: đánh giá khả năng phục vụ của instance

Lựa chọn nền tảng là giữ `readinessState`, sau đó bổ sung các điều kiện thật sự cần cho hợp đồng phục vụ của ứng dụng. Một điều kiện bổ sung hợp lý có thể là bộ quy tắc bắt buộc chưa được nạp vào bộ nhớ hoặc dependency riêng của instance không thể sử dụng.

Nếu tất cả replica cùng phụ thuộc vào một database và đều loại mình khỏi traffic khi database lỗi, hệ thống có thể không còn backend sẵn sàng. Đây có thể là chủ đích của một dịch vụ chỉ nhận giao dịch ghi, nhưng không phù hợp với một dịch vụ vẫn có thể cung cấp dữ liệu đã lưu hoặc chức năng khác. Quyết định cần nêu rõ hành vi mong muốn khi tất cả instance đều không ready.

### 2.3. Chẩn đoán: giữ tín hiệu để giải thích sự cố

Nhóm chẩn đoán có thể chứa database, dung lượng đĩa, discovery và thông tin Kubernetes nếu các contributor tương ứng tồn tại. Kết quả nhóm có thể là `DOWN` trong khi readiness vẫn `UP`: một chức năng phụ đang lỗi nhưng instance vẫn đủ điều kiện phục vụ phần việc đã cam kết.

Việc tách nhóm giúp giám sát tiếp tục nhìn thấy lỗi. Không đưa Redis vào readiness không có nghĩa là bỏ cảnh báo Redis.

Cách phân chia này bám theo ý nghĩa của application availability; có thể đọc và cập nhật trạng thái availability qua API chính thức của [Spring Boot ApplicationAvailability](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/availability/ApplicationAvailability.html).

## 3. Ma trận lựa chọn thành phần

Bảng dưới là **đề xuất thiết kế cho các tình huống nêu trong bài**, không phải danh sách mặc định áp dụng cho mọi ứng dụng.

| Thành phần hoặc tín hiệu | Liveness | Readiness | Chẩn đoán | Lý do cần cân nhắc |
| --- | --- | --- | --- | --- |
| `livenessState` | Có | Không cần lặp lại | Có thể xem qua nhóm riêng | Là tín hiệu availability dành cho việc tiếp tục chạy |
| `readinessState` | Không | Có | Có thể xem qua nhóm riêng | Giữ ý nghĩa sẵn sàng theo vòng đời ứng dụng |
| Database bắt buộc cho mọi yêu cầu | Không | Có điều kiện | Có | Cân nhắc lỗi dùng chung và trường hợp toàn bộ replica bị loại |
| Redis có fallback hoạt động | Không | Thường không | Có | Không loại một instance còn khả năng phục vụ |
| Dữ liệu cấu hình bắt buộc đã nạp và hợp lệ | Không | Có thể có | Có | Kiểm tra dữ liệu đang sử dụng, tránh bắt buộc gọi API mỗi probe |
| Kubernetes API chỉ dùng để theo dõi thay đổi | Không | Thường không | Theo dõi riêng | Mất control plane không nhất thiết làm hỏng yêu cầu đang được phục vụ |
| DiscoveryClient có danh sách instance còn dùng được | Không | Theo chính sách độ mới dữ liệu | Có | Kiểm tra khả năng định tuyến thực tế và giới hạn sử dụng dữ liệu cũ |
| Pod metadata do Spring Cloud Kubernetes cung cấp | Không cần thêm | Không thêm chỉ vì có chữ Kubernetes | Có ích | Metadata không chứng minh database hoặc luồng nghiệp vụ hoạt động |
| `diskSpace` trên vùng ghi bắt buộc | Không đưa vào một cách máy móc | Có điều kiện | Có | Khởi động lại không giải phóng chắc chắn một volume đang đầy |
| Configuration Watcher chạy ở workload riêng | Không | Không trực tiếp | Giám sát workload đó | Watcher lỗi và ứng dụng đang dùng cấu hình hợp lệ là hai trạng thái khác nhau |

Trước khi thêm một thành phần, trả lời bốn câu hỏi:

1. Thành phần này phục vụ toàn bộ yêu cầu hay chỉ một tính năng?
2. Lỗi là cục bộ ở instance này hay dùng chung giữa các replica?
3. Ứng dụng có fallback, dữ liệu đã nạp hoặc cơ chế trì hoãn công việc không?
4. Kết quả lỗi nên làm dừng traffic, phát cảnh báo hay khởi động lại? Hành động đó có giúp khắc phục không?

Nếu chưa trả lời được, hãy giữ tín hiệu ở nhóm chẩn đoán trước và xác định chính sách phục vụ cụ thể.

## 4. Chọn đúng ID của contributor

Danh sách `include` hoặc `exclude` dùng **ID đã đăng ký trong health registry**. Không dùng tên Maven dependency, tên Kubernetes Service hoặc tên lớp Java một cách tùy ý.

Ví dụ thường gặp trong môi trường giả định của bài:

| Thành phần | ID dùng trong nhóm |
| --- | --- |
| JDBC DataSource health contributor | `db` |
| Kiểm tra dung lượng đĩa | `diskSpace` |
| Liveness availability | `livenessState` |
| Readiness availability | `readinessState` |
| Bean được đặt tên rõ ràng `criticalConfig` trong ví dụ bên dưới | `criticalConfig` |

`management.health.diskspace.enabled` là khóa bật/tắt indicator, còn ID để đưa vào nhóm thường là `diskSpace`. Không suy ra rằng cách viết của hai loại khóa luôn giống nhau.

Trong môi trường phát triển hoặc qua truy cập quản trị đã được bảo vệ, xem danh sách `components` của health response hoặc kiểm tra health registry. Với contributor tổng hợp, xem cả cấu trúc con. Ghi lại các ID thực tế cho đúng profile đang chạy; classpath hoặc profile thay đổi có thể làm một contributor xuất hiện hoặc biến mất.

Spring Boot hỗ trợ chọn thành viên bằng `include` và `exclude`, kể cả đường dẫn thành phần con của composite. Theo mặc định, cấu hình một thành viên không tồn tại làm kiểm tra membership thất bại khi khởi động. Xem cú pháp và cơ chế này tại [Spring Boot: Health Groups](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html#actuator.endpoints.health.groups).

Với probe, nên liệt kê tường minh thành viên được phép tham gia. Ví dụ `include: "*"` khiến việc thêm starter mới có thể đưa một health check ngoài dự kiến vào quyết định vận hành. Dùng `exclude` trên một tập mở cũng cần đánh giá rủi ro tương tự.

Không đặt `management.endpoint.health.validate-group-membership=false` chỉ để che lỗi sai ID. Nếu local không có database nhưng môi trường Kubernetes có, hãy khai báo nhóm theo profile phù hợp.

## 5. Cấu hình nền tảng cho một ứng dụng có JDBC

Giả sử ứng dụng có `db` và `diskSpace`. Cấu hình dưới giữ probe gọn, còn hai contributor trên thuộc nhóm chẩn đoán `dependencies`:

```yaml
server:
  port: 8080

management:
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
      show-details: never
      show-components: never
      group:
        liveness:
          include: livenessState
        readiness:
          include: readinessState
        dependencies:
          include: "db,diskSpace"
          show-details: when-authorized
          show-components: when-authorized
          roles: ops
```

Thiết kế này sử dụng:

- `/actuator/health/liveness` và `/actuator/health/readiness` cho hai nhóm availability.
- `/livez` và `/readyz` làm đường dẫn bổ sung trên cổng phục vụ chính.
- `/actuator/health/dependencies` cho nhóm chẩn đoán.

`probes.enabled=true` làm ví dụ không phụ thuộc việc môi trường local có được nhận diện là Kubernetes hay không. Đường dẫn bổ sung là tính năng của Actuator; không cần cài Spring Cloud Kubernetes chỉ để có liveness/readiness. Xem [Spring Boot: Kubernetes Probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes).

`show-details`, `show-components` và `roles` điều khiển khả năng nhìn thấy nội dung health. Chúng **không tự tạo tài khoản quản trị, không cấp role và không thay thế quy tắc truy cập của Spring Security**. Cần cấu hình HTTP security để kubelet đọc đúng hai probe mà không bị yêu cầu đăng nhập; nhóm chẩn đoán cần được giới hạn theo chính sách quản trị. Không mở toàn bộ Actuator để xử lý một lỗi `401` của probe.

Trong ví dụ này, endpoint tổng thể vẫn có thể báo `DOWN` do `db`. Điều đó không khiến `/readyz` báo lỗi nếu `db` không thuộc readiness. Vì thế không thay `/readyz` bằng `/actuator/health` trong manifest mà bỏ qua việc đánh giá lại thành viên.

## 6. Khi nào thêm database vào readiness?

Xét `order-writer`, một dịch vụ chỉ chấp nhận giao dịch ghi vào database, không có cơ chế lưu hàng đợi và không có chức năng hữu ích nào khi không truy cập được dữ liệu. Nhóm phát triển chủ đích muốn instance ngừng nhận yêu cầu mới khi database không sử dụng được.

Trong thiết kế đó, thay danh sách thành viên readiness bằng:

```properties
management.endpoint.health.group.readiness.include=readinessState,db
```

Dòng trên là giá trị thay thế cho cấu hình cùng khóa trong ví dụ trước. Không tạo hai giá trị khác nhau cho cùng khóa rồi dựa vào thứ tự nạp cấu hình một cách ngầm định.

Trước khi áp dụng, cần chốt các điều kiện sau:

- Nếu database dùng chung lỗi, chấp nhận khả năng tất cả replica đều không ready.
- Client hoặc gateway có hành vi phù hợp khi không còn backend sẵn sàng.
- Database health check có timeout hữu hạn; chi phí kiểm tra không chiếm hết connection pool.
- Probe hồi phục được sau khi database hoạt động trở lại, không cần restart ứng dụng.
- Việc lấy được kết nối database chưa được coi là bằng chứng rằng mọi giao dịch nghiệp vụ đều thành công.

Đối với một ứng dụng có cả đọc dữ liệu cache, trang trạng thái đơn hàng và ghi đơn mới, loại cả Pod vì chức năng ghi hỏng có thể làm mất các chức năng còn dùng được. Các lựa chọn khác gồm giữ readiness theo khả năng phục vụ tối thiểu, trả lỗi có kiểm soát cho thao tác ghi hoặc tách workload có hợp đồng phục vụ khác nhau.

Đây là quyết định về hợp đồng của dịch vụ. Không có quy tắc chung rằng mọi ứng dụng dùng JDBC đều phải thêm `db` vào readiness.

## 7. Đặt Spring Cloud Kubernetes đúng vai trò

### 7.1. Pod health không thay thế health của luồng nghiệp vụ

Spring Cloud Kubernetes có contributor cung cấp thông tin về Pod và môi trường chạy, chẳng hạn namespace, service account, node và địa chỉ của Pod. Khi không cần contributor này, có thể tắt bằng:

```properties
management.health.kubernetes.enabled=false
```

Phạm vi thông tin và khóa cấu hình được mô tả trong [Spring Cloud Kubernetes 3.3: Pod Health Indicator](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/pod-health-indicator.html).

Trong thiết kế của bài, contributor đó hữu ích cho việc xác định instance đang gặp lỗi. Không suy ra rằng nó kiểm tra được quyền đọc mọi ConfigMap/Secret, kết nối database hay khả năng gọi downstream qua LoadBalancer. Cũng không dùng trường metadata của Pod để chứng minh mọi container trong Pod đều healthy.

Chỉ thêm contributor này vào một nhóm sau khi xác nhận ID thật và ý nghĩa trạng thái trong phiên bản/client đang dùng. Nếu tắt contributor, cần bỏ nó khỏi những nhóm đã liệt kê tường minh ID đó.

### 7.2. Discovery và LoadBalancer: kiểm tra đúng điều cần biết

Một health check hỏi DiscoveryClient hoạt động không chưa chắc trả lời được việc gọi `inventory-service` có thành công hay không. Ngược lại, tạm thời mất kết nối Kubernetes API chưa chắc làm hỏng ngay một lời gọi đang sử dụng danh sách instance đã nạp.

Giả sử `order-api` gọi `inventory-service` qua Spring Cloud LoadBalancer. Khi chọn readiness, cần phân biệt:

- Không có instance hợp lệ cho downstream bắt buộc.
- Có instance nhưng mọi kết nối đến chúng đều thất bại.
- Không cập nhật được discovery nhưng dữ liệu hiện có còn đáp ứng chính sách độ mới.
- Discovery của một dịch vụ không dùng trong request hiện tại gặp lỗi.

Không tự đặt `include: loadBalancer` và giả định có sẵn contributor tên đó. Chỉ cấu hình ID thực tế hoặc một indicator nghiệp vụ do ứng dụng cung cấp. Cũng tránh health check gọi nối tiếp toàn bộ chuỗi microservice: một lần lỗi ở cuối chuỗi có thể làm nhiều tầng cùng ngừng nhận traffic.

Spring Cloud Commons có health indicator dựa trên DiscoveryClient. Theo tài liệu, nó có thể gọi `getServices()`; khóa `spring.cloud.discovery.client.health-indicator.use-services-query=false` chuyển sang `probe()`. Điều này giảm một loại truy vấn, nhưng mức kiểm tra thực tế còn phụ thuộc implementation của client. Xem [Spring Cloud Commons: Health Indicators](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html#_health_indicators).

### 7.3. RBAC: một lỗi quyền cần có phạm vi ảnh hưởng rõ ràng

Ví dụ một service account thiếu quyền cần thiết để đọc ConfigMap qua API. Hãy tách hai thời điểm:

1. **Khởi động:** nếu cấu hình bắt buộc chưa từng được nạp, instance chưa đủ điều kiện phục vụ. Nó có thể fail startup hoặc giữ readiness ở trạng thái không phục vụ, tùy chính sách nạp cấu hình.
2. **Đang chạy:** nếu ứng dụng vẫn có cấu hình hợp lệ và cho phép tiếp tục sử dụng cấu hình đó, lỗi refresh là tín hiệu cần cảnh báo; không mặc nhiên biến thành lỗi liveness.

Khi dữ liệu cũ hết thời hạn được phép dùng, readiness có thể chuyển sang không phục vụ theo chính sách rõ ràng. Trạng thái cần phản ánh dữ liệu đang dùng và giới hạn an toàn của dữ liệu đó.

Điều tra lỗi `403` theo namespace, service account, resource và thao tác thực tế mà client cần. Không cấp `cluster-admin` chỉ để một health response chuyển xanh. Việc kubelet gọi HTTP vào Pod cũng không phải quyền RBAC đọc tài nguyên Kubernetes của service account trong ứng dụng.

### 7.4. ConfigMap, Secret và Configuration Watcher

Với ConfigMap hoặc Secret, câu hỏi readiness hữu ích là: **ứng dụng hiện có bộ cấu hình hợp lệ để xử lý yêu cầu không?** Câu hỏi này khác với việc API server vừa trả lời được một yêu cầu đọc.

Configuration Watcher chạy ở workload riêng có thể gặp lỗi trong khi các ứng dụng vẫn phục vụ bằng cấu hình hợp lệ. Theo dõi tiến trình watcher, kết quả gửi thông báo và phiên bản cấu hình được áp dụng để phát hiện việc cập nhật bị ngừng. Không dùng sự tồn tại của watcher làm bằng chứng rằng từng instance đã áp dụng bản mới.

Không cần thêm discovery, watcher hoặc quyền đọc Secret qua API nếu ứng dụng chỉ cần DNS của Kubernetes Service và cấu hình được mount sẵn. Chọn tính năng Spring Cloud Kubernetes theo nhu cầu triển khai giúp giảm cả bề mặt lỗi lẫn số health check phải giải thích.

## 8. Ví dụ indicator kiểm tra cấu hình đang có hiệu lực

Giả sử ứng dụng bắt buộc có một bộ quy tắc nghiệp vụ hợp lệ mới nhận traffic. Dùng một indicator cục bộ để ghi nhận kết quả sau khi quá trình tải, kiểm tra và áp dụng cấu hình hoàn tất.

Ví dụ sau chủ động đặt tên bean là `criticalConfig`, nên nhóm dùng đúng ID đó:

```java
package example.health;

import java.util.concurrent.atomic.AtomicReference;

import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component("criticalConfig")
public final class CriticalConfigHealthIndicator implements HealthIndicator {

    private record Snapshot(boolean usable, String reasonCode) {
    }

    private final AtomicReference<Snapshot> snapshot =
            new AtomicReference<>(new Snapshot(false, "NOT_LOADED"));

    public void markApplied() {
        snapshot.set(new Snapshot(true, "APPLIED"));
    }

    public void markUnavailable() {
        snapshot.set(new Snapshot(false, "NO_USABLE_CONFIG"));
    }

    @Override
    public Health health() {
        Snapshot current = snapshot.get();
        if (current.usable()) {
            return Health.up().build();
        }
        return Health.outOfService()
                .withDetail("reasonCode", current.reasonCode())
                .build();
    }
}
```

Đây là một lớp indicator hoàn chỉnh, nhưng **chưa bao gồm pipeline tải và áp dụng cấu hình**. Mã nạp cấu hình của ứng dụng cần inject bean này và gọi phương thức phù hợp:

- Chỉ gọi `markApplied()` sau khi kiểm tra dữ liệu thành công và bộ cấu hình mới đã được đặt vào trạng thái sử dụng.
- Nếu bản cập nhật lỗi nhưng bản cũ vẫn hợp lệ theo chính sách, giữ bản cũ và giữ trạng thái usable; báo lỗi cập nhật qua log/metric riêng.
- Gọi `markUnavailable()` nếu không có cấu hình hợp lệ hoặc bản đang dùng đã hết thời hạn cho phép. Lỗi tạm thời của một lần refresh không tự động đồng nghĩa với tình trạng này.
- Nếu có yêu cầu về độ mới, bổ sung thời điểm áp dụng thành công và logic kiểm tra hết hạn. Ví dụ tối giản trên chưa kiểm tra tuổi cấu hình.

Cơ chế reload cần đảm bảo dữ liệu được áp dụng và tín hiệu usable nhất quán về thứ tự, đặc biệt khi nhiều lần reload có thể chạy đồng thời. Indicator chỉ đọc một snapshot nhỏ, không tải ConfigMap hay Secret trong mỗi lần kubelet hỏi health.

Thêm thành phần này bằng cách thay giá trị readiness thành:

```properties
management.endpoint.health.group.readiness.include=readinessState,criticalConfig
```

Như vậy, Spring Boot báo sẵn sàng theo vòng đời vẫn chưa đủ nếu cấu hình bắt buộc chưa dùng được. Nếu thiết kế ở phần trước còn yêu cầu database, danh sách là `readinessState,criticalConfig,db` sau khi đã chấp nhận hệ quả của việc kiểm tra database.

Contract `HealthIndicator.health()` trả về đối tượng `Health` được mô tả tại [Spring Boot: HealthIndicator API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/actuate/health/HealthIndicator.html). Việc dùng `OUT_OF_SERVICE` trong ví dụ giúp biểu đạt instance hiện không đủ điều kiện phục vụ mà không quy kết nó cần được khởi động lại.

Không ghi giá trị Secret, chuỗi kết nối chứa mật khẩu hoặc nội dung cấu hình vào health details. Một mã nguyên nhân cố định như `NOT_LOADED` thường đủ cho tín hiệu probe; chẩn đoán sâu nên đi qua kênh quản trị phù hợp.

## 9. Gắn đúng nhóm vào Kubernetes probe

Đoạn dưới là **phần cấu hình container** trong Deployment, không phải một manifest hoàn chỉnh. Nó dùng cổng phục vụ chính và hai đường dẫn bổ sung đã bật ở phần cấu hình Spring Boot:

```yaml
ports:
  - name: http
    containerPort: 8080

startupProbe:
  httpGet:
    path: /livez
    port: http
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 36

livenessProbe:
  httpGet:
    path: /livez
    port: http
  periodSeconds: 10
  timeoutSeconds: 2
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /readyz
    port: http
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 3
  successThreshold: 2
```

Trong thiết kế này, startup probe dành khoảng 180 giây để đạt ngưỡng thành công; đó là ngân sách khởi động xấp xỉ theo chu kỳ và số lần lỗi, không phải cam kết thời gian chính xác. Ngưỡng cần dựa trên thời gian khởi động thực tế của ứng dụng.

Theo cơ chế Kubernetes, startup probe trì hoãn liveness/readiness cho đến khi khởi động thành công; liveness thất bại đủ ngưỡng dẫn đến khởi động lại container; readiness thất bại làm container không ready và ảnh hưởng điều kiện Ready của Pod. Readiness không tự yêu cầu restart. Xem [Kubernetes: Configure Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/).

Startup probe dùng `/livez` nên không xác nhận cấu hình nghiệp vụ đã nạp xong. Sau khi startup thành công, readiness chứa `criticalConfig` vẫn chặn traffic nếu cấu hình chưa hợp lệ. Điều này phù hợp khi bạn muốn tiến trình tiếp tục chờ cấu hình thay vì bị restart liên tục.

Những ngưỡng trên là điểm bắt đầu minh họa. Nếu dependency check mất ba giây nhưng `timeoutSeconds` chỉ là hai giây, kubelet có thể kết luận probe lỗi trước khi ứng dụng kịp trả kết quả. Cần đặt timeout thực sự ở HTTP client, driver và connection pool; ngưỡng log health chậm không thay thế các timeout đó.

Nếu dùng `management.server.port` riêng, ưu tiên giữ đường dẫn probe trên cổng ứng dụng để quan sát khả năng nhận kết nối của đường phục vụ chính. Một cổng quản trị còn trả lời không chứng minh cổng nghiệp vụ vẫn nhận được yêu cầu.

## 10. Trạng thái nhóm và mã HTTP phải cùng phục vụ một chính sách

Kubelet HTTP probe quyết định dựa trên kết quả HTTP, không đọc chuỗi `status` trong JSON để hiểu nghiệp vụ. Đối với cấu hình Actuator thông thường:

| Trạng thái health | Mã HTTP mặc định |
| --- | --- |
| `UP` | `200` |
| `DOWN` | `503` |
| `OUT_OF_SERVICE` | `503` |
| `UNKNOWN` | `200` nếu chưa có ánh xạ tùy chỉnh |

Không trả `UNKNOWN` khi ý định là loại instance khỏi traffic. Cũng không thêm trạng thái riêng như `STALE` rồi giả định kubelet sẽ hiểu nó là lỗi.

Nếu có trạng thái tùy chỉnh, phải xác định cả thứ tự tổng hợp lẫn ánh xạ HTTP. Khi tự khai báo HTTP mapping, cần giữ các mapping mong muốn cho `DOWN` và `OUT_OF_SERVICE`; không chỉ thêm một trạng thái mới rồi bỏ sót trạng thái lỗi hiện có. Các thuộc tính liên quan được tra cứu tại [Spring Boot: Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html).

Với ví dụ `criticalConfig`, dùng `OUT_OF_SERVICE` giúp tránh nhu cầu thêm trạng thái mới. Khi readiness lỗi, có thể nhận phản hồi tối giản sau với HTTP `503`:

```json
{"status":"OUT_OF_SERVICE"}
```

Đây là kết quả mong đợi theo thiết kế, không phải bằng chứng rằng ứng dụng phải restart. Ý nghĩa vận hành phụ thuộc probe nào đang đọc endpoint đó.

## 11. Kiểm chứng lựa chọn bằng các tình huống lỗi có kiểm soát

Giả sử cấu hình cuối cùng của một môi trường thử nghiệm là:

```text
liveness     = livenessState
readiness    = readinessState,criticalConfig
dependencies = db,diskSpace
```

Ứng dụng dùng Redis có fallback, database vẫn được theo dõi qua nhóm chẩn đoán, và hợp đồng phục vụ cho phép tiếp tục nhận phần yêu cầu có thể xử lý khi database lỗi. Đây là giả định của tình huống này; không áp dụng nó cho `order-writer` chỉ có chức năng ghi.

Dùng các bước kiểm chứng sau trong môi trường thử nghiệm:

| Tình huống | Kết quả mong đợi với thiết kế trên | Điều cần xác nhận |
| --- | --- | --- |
| Chưa nạp cấu hình bắt buộc | `/readyz` trả `503`; `/livez` có thể đã `200` | Chưa có traffic nghiệp vụ mới, tiến trình còn cơ hội nạp cấu hình |
| Áp dụng cấu hình hợp lệ thành công | Readiness chuyển về `200` khi các thành viên khác đều sẵn sàng | Pod ready sau ngưỡng thành công của probe |
| Redis lỗi, fallback chạy được | Hai probe giữ kết quả theo thành viên đã chọn | Lỗi cache vẫn có metric/cảnh báo, request thực tế còn thành công |
| Database lỗi | Nhóm dependencies báo lỗi; readiness không đổi chỉ vì lỗi đó | Hành vi từng API phù hợp hợp đồng đã công bố |
| Kubernetes API tạm không truy cập được, cấu hình cũ còn hợp lệ | Không restart chỉ vì lỗi API | Có log/metric lỗi discovery hoặc refresh, biết giới hạn dùng dữ liệu cũ |
| Cập nhật cấu hình chứa dữ liệu không hợp lệ, bản cũ còn dùng được | Giữ bản cũ và tiếp tục ready | Không công bố bản mới là đã áp dụng thành công |
| Bản cấu hình đang dùng không còn được phép sử dụng | `criticalConfig` báo `OUT_OF_SERVICE`, readiness lỗi | Mã nạp/giám sát đã gọi `markUnavailable()` theo chính sách |
| Health group dùng một ID không tồn tại | Khởi động bị chặn bởi kiểm tra membership mặc định | Sửa ID hoặc profile thay vì vô hiệu hóa kiểm tra một cách tùy tiện |

Để quan sát HTTP của một instance trong môi trường thử nghiệm, có thể chuyển tiếp cổng tới đúng Pod:

```powershell
# Thay POD_NAME bằng Pod thực tế trong namespace demo.
kubectl -n demo port-forward pod/POD_NAME 18080:8080

# Chạy các lệnh sau trong terminal khác.
curl.exe -i http://localhost:18080/livez
curl.exe -i http://localhost:18080/readyz
curl.exe -i http://localhost:18080/actuator/health/dependencies

kubectl -n demo get pods -w
kubectl -n demo describe pod POD_NAME
```

Truy cập nhóm dependencies phải tuân theo security của ứng dụng; thêm thông tin xác thực quản trị qua cơ chế đã được cấp nếu cần. Port-forward không tự bỏ qua Spring Security. Việc chuyển tiếp cổng cũng không tái hiện đầy đủ đường mạng từ kubelet, vì vậy hãy đọc cả sự kiện probe và điều kiện Pod thay vì chỉ dựa vào `curl`.

Kết quả cần ghi nhận gồm mã HTTP, thành phần gây lỗi, sự thay đổi Ready và số lần restart. Không kết luận chỉ từ màu xanh của endpoint tổng thể hoặc trạng thái `Running` của Pod.

## 12. Những lỗi thiết kế thường gặp

| Cách làm | Hệ quả có thể xảy ra | Điều chỉnh |
| --- | --- | --- |
| Dùng `/actuator/health` cho cả liveness và readiness | Một dependency phụ lỗi kéo theo restart và ngừng traffic | Tách nhóm theo hành động vận hành |
| Thêm mọi indicator vào liveness | Restart hàng loạt khi dependency dùng chung lỗi | Giữ tín hiệu liveness cục bộ và có ý nghĩa với restart |
| Bỏ `readinessState` khi thêm check tùy chỉnh | Mất tín hiệu availability theo vòng đời Spring Boot trong nhóm | Giữ `readinessState` và bổ sung điều kiện riêng |
| Chỉ kiểm tra Pod metadata | Có thông tin Kubernetes nhưng luồng nghiệp vụ vẫn hỏng | Chọn tín hiệu dựa trên hợp đồng phục vụ |
| Đọc Secret qua API ở mỗi probe | Tăng truy vấn, tạo phụ thuộc vào API server và quyền truy cập | Kiểm tra cấu hình hợp lệ đang dùng, theo dõi refresh riêng |
| Cho indicator gọi toàn bộ downstream | Tăng độ trễ và khuếch đại sự cố qua nhiều tầng | Kiểm tra có giới hạn, tránh chuỗi kiểm tra đệ quy |
| Tắt contributor nhưng quên sửa `include` | Lỗi membership hoặc cấu hình nhóm không còn đúng | Cập nhật nhóm cùng thay đổi classpath/profile |
| Coi `roles: ops` là bảo vệ HTTP đầy đủ | Endpoint vẫn có thể bị truy cập ngoài ý muốn | Cấu hình quyền truy cập, mạng và mức hiển thị riêng |
| Giảm `failureThreshold` để mong phát hiện mọi lỗi nhanh hơn | Probe nhạy với nhiễu và làm Pod đổi trạng thái liên tục | Đo độ trễ, xác định timeout và ngưỡng theo mục tiêu phục vụ |

Một cấu hình health group tốt phải giải thích được ba điều: thành viên nào quyết định kết quả, lỗi nào kích hoạt hành động nào và ứng dụng hồi phục ra sao khi nguyên nhân biến mất. Với Spring Cloud Kubernetes, hãy giữ ranh giới rõ giữa sức khỏe của instance, khả năng cập nhật dữ liệu từ Kubernetes và sức khỏe của các dependency phục vụ nghiệp vụ.
