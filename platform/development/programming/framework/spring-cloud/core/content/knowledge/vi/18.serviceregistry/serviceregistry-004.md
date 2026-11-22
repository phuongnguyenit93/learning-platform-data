# Auto-registration và vòng đời ứng dụng

Trong một ứng dụng Spring Cloud, service registry cần biết địa chỉ của từng instance để các client có thể tìm và gọi dịch vụ. Spring Cloud Commons chuẩn hóa thao tác này qua `ServiceRegistry` và `Registration`, đồng thời cung cấp cơ chế **auto-registration** để provider đăng ký instance của ứng dụng trong quá trình khởi động và hủy đăng ký khi ứng dụng dừng.

Auto-registration nối vòng đời của `ApplicationContext` với vòng đời của một service instance trong registry. Khi web server đã khởi tạo và có port thực tế, implementation discovery thường tạo thông tin đăng ký rồi gửi tới registry. Khi context đóng, implementation thường deregister instance. Chi tiết thời điểm và cách thực hiện phụ thuộc provider, nhưng các abstraction chung giúp ứng dụng hiểu được các bước chính và mở rộng hành vi khi cần.

Bài học thuộc chương **ServiceRegistry** của module **SPRING_CLOUD_CORE**, tập trung vào Spring Cloud Commons, service discovery, đăng ký dịch vụ, vòng đời Spring Boot, quản trị trạng thái instance và cách kiểm thử khi ứng dụng khởi động hoặc dừng.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích vai trò của `ServiceRegistry`, `Registration` và `AutoServiceRegistration`.
2. Phân biệt đăng ký tự động với đăng ký thủ công.
3. Mô tả thời điểm đăng ký trong vòng đời ứng dụng Spring Boot.
4. Hiểu hai event `InstancePreRegisteredEvent` và `InstanceRegisteredEvent`.
5. Cấu hình bật/tắt auto-registration và hiểu các thuộc tính liên quan.
6. Giải thích việc đăng ký management service khi management port tách biệt.
7. Mô tả quá trình deregister khi context đóng.
8. Phân biệt trạng thái instance với việc đăng ký và hủy đăng ký.
9. Sử dụng endpoint `/serviceregistry` để đọc hoặc cập nhật trạng thái theo khả năng provider.
10. Kiểm thử startup, registration, shutdown, lỗi registry và hành vi của nhiều replica.

## 2. Các thành phần của service registration

### 2.1. `ServiceRegistry`

`ServiceRegistry` là abstraction để thao tác với registry. Các phương thức tiêu biểu gồm:

- `register(registration)`: đăng ký một instance.
- `deregister(registration)`: hủy đăng ký instance.
- `setStatus(registration, status)`: cập nhật trạng thái nếu provider hỗ trợ.
- `getStatus(registration)`: đọc trạng thái do provider trả về.
- `close()`: đóng tài nguyên của registry client khi implementation cần.

Interface nằm trong package:

~~~java
org.springframework.cloud.client.serviceregistry.ServiceRegistry
~~~

`ServiceRegistry` là hợp đồng chung; mỗi provider có implementation riêng. Ví dụ:

| Provider | Registration type | Registry implementation |
| --- | --- | --- |
| Eureka | `EurekaRegistration` | `EurekaServiceRegistry` |
| Consul | `ConsulRegistration` | `ConsulServiceRegistry` |
| ZooKeeper | `ZookeeperRegistration` | `ZookeeperServiceRegistry` |

Khi gọi API generic, cần truyền đúng registration type mà implementation provider yêu cầu. Không thể lấy một `Registration` bất kỳ rồi giả định mọi registry đều hiểu cùng metadata hoặc cùng cách cập nhật trạng thái.

### 2.2. `Registration`

`Registration` là marker interface mở rộng `ServiceInstance`. Nó mô tả instance cần được đưa vào registry, thường bao gồm:

- Service ID hoặc tên logic.
- Instance ID nếu provider sử dụng.
- Host và port.
- URI hoặc scheme bảo mật.
- Metadata như zone, version, region hoặc thông tin routing.

Ví dụ khái niệm:

~~~text
serviceId: orders-service
instanceId: orders-service-7f9c
host: orders-7f9c.internal
port: 8080
scheme: http
metadata:
  zone: ap-southeast-1a
  version: v2
~~~

Đây là dữ liệu minh họa. Cách provider tạo `Registration`, chọn địa chỉ mạng và biểu diễn metadata có thể khác nhau.

### 2.3. `AutoServiceRegistration`

`AutoServiceRegistration` mô tả khả năng tự đăng ký instance theo lifecycle của ứng dụng. Provider thường cung cấp một implementation kết hợp với `ServiceRegistry` để tự động đăng ký và deregister instance.

Ứng dụng dùng abstraction này để nhận hành vi tự động; không cần tự gọi `register()` trong mỗi lần khởi động nếu provider đã cấu hình auto-registration.

### 2.4. Vai trò của DiscoveryClient

Cần phân biệt hai hướng:

| Abstraction | Trách nhiệm |
| --- | --- |
| `DiscoveryClient` / `ReactiveDiscoveryClient` | Đọc danh sách service và instance từ discovery |
| `ServiceRegistry` | Ghi, xóa và cập nhật trạng thái registration |
| `Registration` | Mô tả instance được đăng ký |
| `AutoServiceRegistration` | Gắn thao tác đăng ký với vòng đời ứng dụng |

Một ứng dụng có thể dùng `DiscoveryClient` để tìm dịch vụ khác mà không tự đăng ký mình. Ngược lại, một thành phần có thể đăng ký instance nhưng không nhất thiết dùng discovery để gọi downstream.

## 3. Auto-registration hoạt động khi nào?

### 3.1. Provider có trên classpath

Khi dependency discovery provider phù hợp có trên runtime classpath, Spring Boot auto-configuration có thể tạo các bean discovery và service registry tương ứng.

Ví dụ, một ứng dụng dùng Eureka có thể thêm Eureka Client starter; ứng dụng dùng Consul có thể thêm Consul Discovery starter. Spring Cloud Commons định nghĩa hợp đồng chung, còn starter/provider chịu trách nhiệm cấu hình kết nối và đăng ký.

`@EnableDiscoveryClient` không còn bắt buộc trong các phiên bản Spring Cloud hiện hành nếu implementation phù hợp đã có trên classpath. Annotation vẫn tồn tại và có thể dùng để điều chỉnh hành vi, chẳng hạn `autoRegister=false`. Hãy đối chiếu release train của dự án khi làm việc với phiên bản cũ.

### 3.2. Địa chỉ instance phải được xác định

Registration cần địa chỉ mà client khác có thể truy cập. Thông tin này có thể được tạo từ:

- `spring.application.name`.
- Port của web server.
- Hostname hoặc địa chỉ mạng được provider chọn.
- Cấu hình secure port hoặc scheme.
- Metadata và thuộc tính riêng của provider.

Không nên giả định địa chỉ được đăng ký luôn là `localhost`. Trong container, VM hoặc Kubernetes, địa chỉ mà registry công bố phải truy cập được từ network của consumer.

### 3.3. Luồng phổ biến với web application

Một implementation phổ biến dựa trên `AbstractAutoServiceRegistration` lắng nghe `WebServerInitializedEvent`. Khi embedded web server khởi tạo xong, event cung cấp port thực tế; implementation sau đó bắt đầu đăng ký.

~~~mermaid
sequenceDiagram
    participant Boot as Spring Boot
    participant Web as Embedded Web Server
    participant Auto as AutoServiceRegistration
    participant Registry as ServiceRegistry
    participant Store as Remote Registry

    Boot->>Web: Khởi tạo web server
    Web-->>Auto: WebServerInitializedEvent
    Auto->>Auto: Kiểm tra auto-registration
    Auto->>Auto: Tạo Registration với port thực tế
    Auto->>Registry: register(Registration)
    Registry->>Store: Ghi instance
    Store-->>Registry: Kết quả đăng ký
    Registry-->>Auto: Hoàn tất
~~~

Không phải mọi provider đều phải dùng chính xác lớp base này hoặc cùng một event. Đây là luồng phổ biến trong implementation dùng `AbstractAutoServiceRegistration`; provider có thể có cách khởi tạo riêng, đặc biệt với non-web application hoặc registry không phụ thuộc web server.

### 3.4. Vì sao cần đợi web server khởi tạo?

Nếu đăng ký trước khi web server có port thực tế, ứng dụng có thể công bố port sai, đặc biệt khi dùng `server.port=0` để yêu cầu hệ điều hành cấp port động.

Đợi `WebServerInitializedEvent` giúp implementation lấy port đã được server bind. Với ứng dụng không có web server, provider phải có chiến lược riêng để xác định địa chỉ và thời điểm đăng ký; không nên mặc định luồng web event áp dụng cho mọi loại ứng dụng.

## 4. Trình tự auto-registration và các lifecycle hook

Trong implementation dựa trên `AbstractAutoServiceRegistration`, quá trình startup thường có các bước sau:

1. Nhận `WebServerInitializedEvent` từ web server của ứng dụng.
2. Lưu port thực tế và gọi `start()`.
3. Kiểm tra provider có bật registration hay không.
4. Kiểm tra trạng thái đang chạy để tránh đăng ký lặp.
5. Phát `InstancePreRegisteredEvent`.
6. Chạy các `RegistrationLifecycle` hook trước khi đăng ký.
7. Gọi `ServiceRegistry.register()` cho instance chính.
8. Chạy hook sau khi đăng ký instance chính.
9. Nếu management server dùng port riêng và được phép đăng ký, đăng ký thêm management instance.
10. Phát `InstanceRegisteredEvent`.
11. Đánh dấu auto-registration đang chạy.

~~~mermaid
flowchart TD
    A[WebServerInitializedEvent] --> B{Auto-registration enabled?}
    B -->|No| X[Không đăng ký]
    B -->|Yes| C{Đã chạy?}
    C -->|Yes| Y[Bỏ qua đăng ký lặp]
    C -->|No| D[InstancePreRegisteredEvent]
    D --> E[RegistrationLifecycle before]
    E --> F[ServiceRegistry.register]
    F --> G[RegistrationLifecycle after]
    G --> H{Management port riêng?}
    H -->|Có và được bật| I[Đăng ký management instance]
    H -->|Không| J[Hoàn tất]
    I --> J
    J --> K[InstanceRegisteredEvent]
    K --> L[Đánh dấu running]
~~~

Thứ tự này mô tả implementation base hiện hành. Provider cụ thể có thể bổ sung bước, thay đổi điều kiện hoặc thực hiện đăng ký management theo cách riêng. Khi cần phụ thuộc vào chi tiết lifecycle, hãy kiểm tra implementation và tài liệu đúng phiên bản đang dùng.

### 4.1. `InstancePreRegisteredEvent`

Event này được phát trước khi gọi đăng ký chính. Listener có thể dùng nó để:

- Ghi log bắt đầu registration.
- Gắn metadata bổ sung nếu đối tượng registration cho phép.
- Kiểm tra điều kiện triển khai.
- Tạo correlation ID cho log vận hành.

Không dùng listener để thực hiện một lần đăng ký thứ hai cho cùng instance; việc đó có thể tạo registration trùng hoặc làm trạng thái registry không nhất quán.

### 4.2. `InstanceRegisteredEvent`

Event này được phát sau khi auto-registration hoàn tất trong luồng implementation tương ứng. Listener có thể:

- Ghi nhận instance đã được đăng ký.
- Phát metric hoặc audit event.
- Kích hoạt bước kiểm tra phụ thuộc sau đăng ký.
- Gửi thông báo cho một thành phần nội bộ.

Event cho biết bước đăng ký đã được thực hiện theo lifecycle. Nó không chứng minh mọi consumer đã nhìn thấy instance ngay lập tức, vì registry có thể có độ trễ đồng bộ hoặc cache.

### 4.3. Đăng ký listener

Ví dụ dùng `@EventListener`:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.cloud.client.discovery.event.InstancePreRegisteredEvent;
import org.springframework.cloud.client.discovery.event.InstanceRegisteredEvent;

@Component
public class RegistrationEventLogger {

    @EventListener
    public void beforeRegistration(InstancePreRegisteredEvent event) {
        // Ghi nhận thời điểm bắt đầu registration.
    }

    @EventListener
    public void afterRegistration(InstanceRegisteredEvent<?> event) {
        // Ghi nhận registration đã hoàn tất theo provider.
    }
}
~~~

Ví dụ tập trung vào vị trí listener. Tránh gọi registry đồng bộ thêm lần nữa từ listener nếu không có mục tiêu cụ thể. Với thao tác có thể thất bại hoặc cần retry, thiết kế một service riêng có timeout, idempotency và quan sát lỗi.

### 4.4. Các hook `RegistrationLifecycle`

Spring Cloud Commons cung cấp extension point `RegistrationLifecycle` để xử lý trước/sau các thao tác đăng ký và hủy đăng ký local service. Các hook thường gặp:

| Hook | Thời điểm |
| --- | --- |
| `postProcessBeforeStartRegister(registration)` | Trước khi đăng ký instance |
| `postProcessAfterStartRegister(registration)` | Sau khi đăng ký instance |
| `postProcessBeforeStopRegister(registration)` | Trước khi hủy đăng ký |
| `postProcessAfterStopRegister(registration)` | Sau khi hủy đăng ký |

Có nhóm hook tương tự trong `RegistrationManagementLifecycle` dành cho management registration.

Các hook này hữu ích khi provider hoặc ứng dụng cần bổ sung metadata, ghi nhận audit hoặc phối hợp tác vụ trước/sau registry operation. Chúng không thay thế `ServiceRegistry`; thao tác ghi/xóa vẫn do registry implementation thực hiện.

## 5. Cấu hình bật và tắt auto-registration

### 5.1. Mặc định

Theo configuration properties hiện hành của Spring Cloud Commons:

| Thuộc tính | Mặc định | Ý nghĩa |
| --- | --- | --- |
| `spring.cloud.service-registry.auto-registration.enabled` | `true` | Bật/tắt auto-registration |
| `spring.cloud.service-registry.auto-registration.fail-fast` | `false` | Có fail startup nếu không có `AutoServiceRegistration` hay không |
| `spring.cloud.service-registry.auto-registration.register-management` | `true` | Cho phép đăng ký management service khi phù hợp |

Giá trị mặc định này nói về cấu hình Commons. Provider vẫn có thể có thuộc tính riêng ảnh hưởng registration, chẳng hạn bật/tắt client, chọn port hoặc điều khiển đăng ký theo môi trường.

### 5.2. Tắt bằng application.yml

~~~yaml
spring:
  cloud:
    service-registry:
      auto-registration:
        enabled: false
~~~

Cấu hình này ngăn cơ chế auto-registration chung chạy. Ứng dụng vẫn có thể sử dụng `DiscoveryClient` để đọc instance của dịch vụ khác nếu discovery client được bật và provider hỗ trợ.

Tắt auto-registration không có nghĩa là tắt toàn bộ discovery. Nếu muốn vô hiệu hóa discovery hoàn toàn, đó là cấu hình khác, chẳng hạn `spring.cloud.discovery.enabled=false`.

### 5.3. Tắt bằng `@EnableDiscoveryClient`

Có thể dùng:

~~~java
@EnableDiscoveryClient(autoRegister = false)
@SpringBootApplication
public class OrdersApplication {
}
~~~

Trong các phiên bản hiện hành, annotation không bắt buộc chỉ để kích hoạt discovery khi provider đã có trên classpath. Tuy nhiên, tham số `autoRegister=false` vẫn là cách biểu đạt rõ ràng trong các tình huống muốn tắt hành vi này ở cấu hình annotation.

Ưu tiên một nguồn cấu hình rõ ràng và nhất quán. Tránh đặt annotation và property ở các giá trị trái ngược khiến người vận hành khó xác định ý định.

### 5.4. Khi nào nên tắt auto-registration?

Một số trường hợp hợp lý:

- Ứng dụng chỉ đọc discovery nhưng không muốn đăng ký chính nó.
- Registration được điều khiển bởi một quy trình deploy bên ngoài.
- Một tiến trình quản trị dùng chung dependency discovery nhưng không phải service endpoint.
- Integration test cần kiểm soát registration thủ công.
- Một service chỉ được đưa vào registry sau khi hoàn tất bước warm-up hoặc readiness riêng.

Khi tắt auto-registration, phải có cách khác để instance xuất hiện trong registry nếu consumer vẫn cần tìm nó. Không nên tắt registration rồi kỳ vọng registry tự biết địa chỉ của ứng dụng.

## 6. `fail-fast` và xử lý lỗi lúc startup

Thuộc tính:

~~~yaml
spring:
  cloud:
    service-registry:
      auto-registration:
        fail-fast: true
~~~

điều khiển hành vi khi không có `AutoServiceRegistration` theo mô tả configuration properties của Commons. Giá trị mặc định là `false`.

Cần phân biệt:

- **Không có AutoServiceRegistration bean:** ứng dụng có thể không có cơ chế auto-registration được cấu hình.
- **Có bean nhưng registry không truy cập được:** provider thực hiện lời gọi mạng và xử lý lỗi theo implementation, timeout và chính sách riêng.
- **Registry nhận request nhưng từ chối registration:** có thể do credential, service ID, metadata hoặc policy.
- **Registration thành công nhưng client chưa thấy instance:** có thể do độ trễ đồng bộ, cache hoặc truy vấn nhầm namespace.

Không diễn giải `fail-fast` như một bảo đảm chung rằng mọi lỗi mạng registry đều sẽ được xử lý giống nhau. Muốn fail startup khi provider không thể đăng ký, hãy kiểm tra chính sách lỗi của provider cụ thể và viết integration test với registry không khả dụng.

### 6.1. Quyết định fail startup hay tiếp tục chạy

| Bối cảnh | Chính sách có thể phù hợp |
| --- | --- |
| Service bắt buộc phải được discovery tìm thấy ngay khi chạy | Cân nhắc fail startup khi registration thất bại |
| Công việc nền không nhận traffic qua discovery | Có thể cho phép startup và cảnh báo |
| Registry tạm thời mất kết nối | Retry có giới hạn, backoff và readiness phù hợp |
| Credential sai hoặc service ID sai | Thường cần báo lỗi rõ ràng, không retry vô hạn |
| Test local không có registry | Dùng SimpleDiscoveryClient hoặc tắt auto-registration theo mục tiêu test |

Không để một service báo readiness `UP` nếu kiến trúc yêu cầu nó phải được đăng ký trước khi nhận traffic nhưng registration chưa thành công.

## 7. Đăng ký management service

### 7.1. Management port riêng

Spring Boot có thể chạy management endpoint trên port riêng thông qua `management.server.port`. Khi port quản trị khác port ứng dụng, một số provider có thể đăng ký thêm một management instance để các công cụ vận hành tìm được endpoint quản trị.

Ví dụ:

~~~yaml
server:
  port: 8080

management:
  server:
    port: 9090
~~~

Trong implementation base của Spring Cloud, `spring.cloud.service-registry.auto-registration.register-management` mặc định là `true`. Việc đăng ký management chỉ được thực hiện khi có management port riêng và provider hỗ trợ tạo management registration.

### 7.2. Tắt đăng ký management

~~~yaml
spring:
  cloud:
    service-registry:
      auto-registration:
        register-management: false
~~~

Điều này hữu ích nếu endpoint quản trị chỉ được phép truy cập qua mạng riêng và không nên xuất hiện trong registry dịch vụ chung.

Tắt management registration không tự tắt Actuator. Nó chỉ ảnh hưởng đến việc công bố management endpoint như một registration riêng theo khả năng provider.

### 7.3. Vì sao cần tách địa chỉ quản trị?

Nếu management port được đăng ký như một instance riêng, consumer có thể phân biệt service endpoint với management endpoint. Nhưng việc công bố port quản trị cũng mở rộng bề mặt khám phá. Chỉ đăng ký management service khi có use case và policy truy cập phù hợp; bảo vệ Actuator bằng authentication, authorization và network restriction.

## 8. Deregistration khi ứng dụng dừng

### 8.1. Vòng đời shutdown

Trong implementation dùng `AbstractAutoServiceRegistration`, phương thức hủy được gắn với `@PreDestroy`. Khi Spring đóng context, implementation gọi `stop()` để hủy đăng ký.

Luồng phổ biến:

1. ApplicationContext bắt đầu đóng.
2. `AbstractAutoServiceRegistration.destroy()` gọi `stop()`.
3. Kiểm tra instance đã được đánh dấu running và registration còn được bật.
4. Chạy hook `postProcessBeforeStopRegister`.
5. Gọi `ServiceRegistry.deregister()` cho instance chính.
6. Chạy hook `postProcessAfterStopRegister`.
7. Nếu management service đã được đăng ký, hủy registration đó.
8. Đóng registry client nếu implementation yêu cầu.

~~~mermaid
sequenceDiagram
    participant Context as ApplicationContext
    participant Auto as AutoServiceRegistration
    participant Registry as ServiceRegistry
    participant Store as Remote Registry

    Context->>Auto: @PreDestroy / destroy()
    Auto->>Auto: stop()
    Auto->>Auto: RegistrationLifecycle before stop
    Auto->>Registry: deregister(Registration)
    Registry->>Store: Xóa hoặc đánh dấu instance
    Store-->>Registry: Kết quả
    Auto->>Auto: RegistrationLifecycle after stop
    Auto->>Registry: deregister management (nếu có)
    Auto->>Registry: close()
~~~

Đây là luồng của implementation base, không phải cam kết mọi provider dùng cùng một thứ tự nội bộ. Provider có thể dùng lease, heartbeat hoặc cơ chế cleanup khác.

### 8.2. Graceful shutdown và deregistration

Deregister giúp registry ngừng công bố instance theo semantics của provider. Nó không tự bảo đảm mọi request đang chạy đã hoàn tất.

Trong production, nên phối hợp:

1. Đưa instance vào trạng thái không nhận traffic mới hoặc readiness `DOWN`.
2. Cho load balancer/router thời gian ngừng chọn instance.
3. Drain request đang xử lý.
4. Đóng ApplicationContext.
5. Để provider deregister instance.
6. Xác minh registry đã cập nhật.

Nếu process bị kill cưỡng bức, mất điện hoặc container bị terminate trước khi callback chạy, deregistration có thể không được thực hiện. Registry cần TTL, lease, heartbeat hoặc cơ chế expiry để dọn instance stale. Thời gian phát hiện phụ thuộc provider và cấu hình.

### 8.3. Deregister không đồng nghĩa xóa lịch sử

Một số registry lưu lịch sử, trạng thái hoặc event của instance sau khi nó không còn active. `deregister()` thường làm instance không còn được công bố như một registration hoạt động, nhưng retention và audit history phụ thuộc provider.

Không giả định dữ liệu đã biến mất hoàn toàn khỏi registry storage chỉ vì `deregister()` trả về.

## 9. Trạng thái instance và ServiceRegistry Actuator endpoint

### 9.1. Trạng thái khác với đăng ký

Một instance có thể đã đăng ký nhưng được đánh dấu `OUT_OF_SERVICE` hoặc `DOWN`. Trạng thái này có thể giúp ngừng chọn instance trong khi vẫn giữ registration để phục vụ maintenance hoặc điều tra.

| Thao tác | Ý nghĩa |
| --- | --- |
| `register()` | Tạo hoặc công bố registration |
| `setStatus()` | Thay đổi trạng thái của registration nếu provider hỗ trợ |
| `deregister()` | Hủy registration |
| Heartbeat/lease | Duy trì sự hiện diện theo cơ chế provider |

Không dùng status update như thay thế universal cho deregister. Cách LoadBalancer hoặc registry xử lý status phụ thuộc provider.

### 9.2. Endpoint `/serviceregistry`

Spring Cloud Commons cung cấp Actuator endpoint `/serviceregistry` nếu có `Registration` bean và endpoint được cấu hình/expose.

- `GET /actuator/serviceregistry`: đọc trạng thái registration hiện tại.
- `POST /actuator/serviceregistry`: cập nhật trạng thái bằng JSON có field `status`.

Ví dụ:

~~~http
POST /actuator/serviceregistry
Content-Type: application/json

{
  "status": "OUT_OF_SERVICE"
}
~~~

Các giá trị hợp lệ phụ thuộc provider. Tài liệu nêu Eureka có thể dùng `UP`, `DOWN`, `OUT_OF_SERVICE` và `UNKNOWN`. Không giả định Consul, ZooKeeper hoặc provider khác có cùng semantics.

### 9.3. Exposure và bảo mật

Để truy cập endpoint qua HTTP, cần có Actuator, endpoint implementation, exposure phù hợp và quyền gọi. Ví dụ cấu hình exposure:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,serviceregistry
~~~

Endpoint thay đổi trạng thái registration là API quản trị. Cần giới hạn mạng, xác thực và phân quyền; không expose công khai. Nếu Spring Security được cấu hình riêng, hãy kiểm tra `SecurityFilterChain` có cho phép write operation chỉ với role vận hành.

## 10. Đăng ký thủ công bằng ServiceRegistry

Auto-registration phù hợp với service thông thường. Một số use case cần đăng ký dịch vụ theo điều kiện hoặc theo một quy trình riêng. Spring Cloud Commons cho phép gọi `ServiceRegistry` trực tiếp.

### 10.1. Registration phụ thuộc provider

Mỗi provider có kiểu registration cụ thể. Ví dụ với ZooKeeper, tài liệu provider minh họa tạo registration qua builder rồi gọi registry:

~~~java
ZookeeperRegistration registration =
        ServiceInstanceRegistration.builder()
                .defaultUriSpec()
                .address("inventory.internal")
                .port(8080)
                .name("/services/inventory-service")
                .build();

serviceRegistry.register(registration);
~~~

Đoạn mã là ví dụ dành cho Spring Cloud Zookeeper; các lớp và cách tạo registration không dùng chung cho Eureka hoặc Consul. Hãy dùng builder/registration type của provider đang chạy.

### 10.2. Tắt auto-registration nếu tự quản lý

Nếu ứng dụng tự gọi `register()` theo workflow riêng, thường cần tắt auto-registration để tránh đăng ký trùng:

~~~yaml
spring:
  cloud:
    service-registry:
      auto-registration:
        enabled: false
~~~

Sau đó, ứng dụng cần xác định rõ:

- Khi nào tạo registration.
- Điều kiện nào cho phép đăng ký.
- Khi nào retry nếu registry tạm thời lỗi.
- Làm sao bảo đảm register idempotent.
- Ai chịu trách nhiệm deregister.
- Điều gì xảy ra khi process bị dừng bất thường.

Không tắt auto-registration rồi quên tạo workflow thay thế; service sẽ không xuất hiện trong registry.

### 10.3. Idempotency và registration trùng

Registry có thể xử lý registration lặp theo cách riêng, ví dụ cập nhật entry cùng instance ID hoặc tạo một entry khác. Không dựa vào giả định chung này.

Thiết kế nên có instance ID ổn định trong vòng đời process, xử lý retry có giới hạn và tránh tạo nhiều registration cho cùng một process. Khi scale nhiều replica, mỗi replica phải có định danh riêng.

## 11. `SimpleDiscoveryClient` không phải service registry động

`SimpleDiscoveryClient` có thể đọc danh sách instance tĩnh từ cấu hình:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://inventory-1.internal:8080
              - uri: http://inventory-2.internal:8080
~~~

Cách này phù hợp với local development, test hoặc môi trường có endpoint tĩnh. Nó cung cấp dữ liệu để `DiscoveryClient` tra cứu, nhưng không phải một registry server và không tự đăng ký local application vào một hệ thống registry từ xa.

Vì vậy, có `DiscoveryClient` bean không đồng nghĩa có `ServiceRegistry` hoặc `AutoServiceRegistration` bean. Cần kiểm tra dependency và implementation cụ thể.

## 12. Kiểm thử auto-registration và vòng đời

### 12.1. Unit test cho listener

Có thể kiểm tra listener nhận event bằng cách publish event trong test context hoặc mock event publisher. Mục tiêu là xác nhận logic quan sát/audit không thực hiện registration lặp.

Các listener nên nhẹ, không thực hiện network call dài và không làm hỏng startup nếu tác vụ phụ không thiết yếu thất bại.

### 12.2. Integration test với registry thật

Một integration test có thể dùng Testcontainers hoặc môi trường test của provider:

1. Khởi động registry.
2. Khởi chạy ứng dụng với provider starter và auto-registration bật.
3. Chờ instance xuất hiện theo service ID.
4. Xác minh host, port, scheme và metadata.
5. Gọi `GET /actuator/serviceregistry` nếu endpoint được expose.
6. Đóng context.
7. Chờ instance bị deregister hoặc chuyển sang trạng thái provider quy định.
8. Xác minh registry không còn trả instance hoạt động.

Không dùng `Thread.sleep()` cố định làm bằng chứng duy nhất. Dùng polling có timeout để chờ registry đạt trạng thái mong muốn, vì registry có thể đồng bộ bất đồng bộ.

### 12.3. Kiểm thử tắt auto-registration

Đặt:

~~~properties
spring.cloud.service-registry.auto-registration.enabled=false
~~~

Xác nhận:

- Instance không được tự đăng ký.
- `InstancePreRegisteredEvent` và `InstanceRegisteredEvent` không được phát từ auto-registration.
- Discovery client đọc dịch vụ khác vẫn hoạt động nếu không bị tắt riêng.
- Workflow manual registration nếu có vẫn chạy đúng.

### 12.4. Kiểm thử lỗi registry

Nên có các kịch bản:

- Registry không khả dụng lúc startup.
- Credential không hợp lệ.
- Registry ngắt kết nối khi ứng dụng đang chạy.
- Registration bị từ chối do service ID hoặc metadata.
- Registry chậm hoặc trả lỗi timeout.
- Process bị kill trước khi deregister.
- Instance restart nhanh và đăng ký lại cùng service ID.
- Hai replica vô tình dùng cùng instance ID.

Ghi nhận hành vi theo provider và chính sách fail-fast/retry thực tế. Không giả định tất cả provider có cùng thời gian timeout, retry hoặc stale instance cleanup.

## 13. Vận hành nhiều instance

### 13.1. Mỗi replica là một registration riêng

Nếu service có ba replica, registry thường có ba registration riêng:

~~~text
orders-service
  ├── orders-7f9c -> 10.0.1.12:8080
  ├── orders-1ab3 -> 10.0.1.13:8080
  └── orders-4de8 -> 10.0.1.14:8080
~~~

Mỗi instance cần địa chỉ và instance ID phù hợp. Không dùng một instance ID tĩnh giống nhau cho mọi replica nếu provider yêu cầu ID duy nhất.

### 13.2. Rolling deployment

Trong rolling deployment, instance cũ và mới có thể cùng tồn tại một thời gian:

1. Instance mới khởi động và đăng ký.
2. Health/readiness đạt yêu cầu.
3. Traffic được chuyển sang instance mới.
4. Instance cũ ngừng nhận traffic.
5. Instance cũ deregister khi shutdown.
6. Registry hội tụ về danh sách instance mới.

Nếu đăng ký quá sớm trước khi service thực sự sẵn sàng, client có thể chọn instance chưa phục vụ được request. Cần phối hợp registration với readiness, health check và load balancer.

### 13.3. Stale registration

Khi process bị kill -9 hoặc node mất kết nối, callback deregister có thể không chạy. Registry có thể tiếp tục hiển thị instance cho đến khi TTL/lease/heartbeat hết hạn hoặc health check đánh dấu instance không khỏe.

Vì vậy, cần cấu hình thời gian phát hiện instance chết phù hợp với mục tiêu availability và tránh TTL quá dài khiến client tiếp tục gọi địa chỉ không còn hoạt động.

## 14. Bảo mật và độ tin cậy

Registration metadata thường được nhiều service có quyền đọc discovery nhìn thấy. Không đưa secret, token, password hoặc thông tin cá nhân vào metadata.

Các điểm cần kiểm soát:

- TLS giữa ứng dụng và registry.
- Credential riêng theo workload.
- Quyền register/deregister/read tối thiểu.
- Service ID và instance ID không bị giả mạo.
- Management endpoint không công khai.
- Metadata không chứa bí mật.
- Retry có backoff và giới hạn.
- Timeout cho thao tác registry.
- Log có correlation ID nhưng không chứa credential.
- Audit thay đổi trạng thái instance.
- Kiểm tra network address được quảng bá có thể truy cập từ consumer.

Khi registry không sẵn sàng, không retry vô hạn với tần suất cao. Retry storm có thể làm registry quá tải đúng lúc hệ thống cần phục hồi.

## 15. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng điều tra |
| --- | --- | --- |
| Service không xuất hiện trong registry | Thiếu provider, auto-registration bị tắt hoặc registration lỗi | Kiểm tra starter, auto-registration property và log |
| Instance đăng ký sai port | Registration được tạo trước khi có port thực tế hoặc provider config sai | Kiểm tra `WebServerInitializedEvent`, server port và provider settings |
| Registry hiển thị localhost | Host/address quảng bá không phù hợp môi trường container | Kiểm tra hostname, network interface và advertised address |
| Hai replica ghi đè nhau | Instance ID không duy nhất | Kiểm tra cách provider tạo instance ID |
| `InstanceRegisteredEvent` không xuất hiện | Auto-registration bị tắt hoặc registration chưa hoàn tất | Kiểm tra property và lifecycle log |
| Event pre-register có nhưng event after không có | Lời gọi register thất bại hoặc lifecycle dừng giữa chừng | Kiểm tra exception từ registry và hook |
| Instance cũ vẫn tồn tại sau shutdown | Callback không chạy hoặc registry cập nhật trễ | Kiểm tra deregister, lease, heartbeat và TTL |
| Management endpoint không được đăng ký | Không có management port riêng hoặc `register-management=false` | Kiểm tra management port và property |
| `/actuator/serviceregistry` trả 404 | Thiếu Actuator/Registration bean hoặc chưa expose | Kiểm tra dependency, auto-configuration và exposure |
| POST status không nhận giá trị | Status không hợp lệ với provider hoặc thiếu quyền write | Kiểm tra provider docs và security |
| Service có trong discovery nhưng gọi không được | Registration chỉ phản ánh địa chỉ, instance có thể chưa ready hoặc network lỗi | Kiểm tra readiness, port, health và network |
| Startup không fail dù registry lỗi | `fail-fast` không điều khiển lỗi provider theo kỳ vọng hoặc provider cho phép tiếp tục | Kiểm tra implementation và integration test |

## 16. Quy trình chẩn đoán theo vòng đời

Khi instance không xuất hiện trong registry, kiểm tra theo trình tự:

1. Xác nhận provider starter có trong runtime classpath.
2. Xác nhận discovery và auto-registration không bị tắt.
3. Kiểm tra `AutoServiceRegistration` bean có tồn tại.
4. Kiểm tra `spring.application.name`, host, port và instance ID.
5. Xác nhận web server đã phát event khởi tạo nếu provider dùng luồng đó.
6. Kiểm tra `InstancePreRegisteredEvent` và log trước khi register.
7. Kiểm tra request đăng ký và response/lỗi từ registry.
8. Kiểm tra `InstanceRegisteredEvent`.
9. Truy vấn registry trực tiếp theo service ID.
10. Khi shutdown, kiểm tra deregister và TTL/lease nếu instance còn sót.

Nếu dùng endpoint `/serviceregistry`, kiểm tra status của registration trong context. Nếu cần xác minh dữ liệu thực tế, truy vấn registry provider hoặc dùng API quản trị tương ứng.

## 17. Bài tập vận dụng

**Bài tập 1 — Auto-registration cơ bản.** Tạo ứng dụng Spring Boot với một discovery provider. Khởi động ứng dụng và xác nhận service ID, instance ID, host và port xuất hiện trong registry.

**Bài tập 2 — Theo dõi lifecycle events.** Tạo listener cho `InstancePreRegisteredEvent` và `InstanceRegisteredEvent`. Ghi log thời điểm, service name và kết quả registration; không thực hiện đăng ký lần hai trong listener.

**Bài tập 3 — Tắt auto-registration.** Đặt `spring.cloud.service-registry.auto-registration.enabled=false`. Xác nhận ứng dụng vẫn có thể đọc service khác qua `DiscoveryClient` nhưng không tự đăng ký.

**Bài tập 4 — Management port.** Đặt `management.server.port` khác `server.port`. Kiểm tra provider có đăng ký management instance hay không. Sau đó đặt `register-management=false` và so sánh.

**Bài tập 5 — Deregistration.** Đóng ApplicationContext bình thường. Quan sát hook stop, thao tác deregister và trạng thái registry. Sau đó kill process cưỡng bức và kiểm tra TTL/lease.

**Bài tập 6 — Fail-fast.** Chạy ứng dụng khi provider hoặc registry không sẵn sàng. So sánh `fail-fast=false` và `true`; xác định chính xác lỗi nào thuộc property Commons và lỗi nào thuộc provider.

**Bài tập 7 — Service status.** Gọi GET `/actuator/serviceregistry`, sau đó POST `OUT_OF_SERVICE` nếu provider hỗ trợ. Kiểm tra LoadBalancer hoặc registry có ngừng chọn instance hay không.

**Bài tập 8 — Manual registration.** Tắt auto-registration và tạo registration thủ công bằng provider API. Thiết kế retry, instance ID, deregister và test cho trường hợp đăng ký lặp.

**Bài tập 9 — Rolling deployment.** Chạy hai replica. Đưa replica mới lên trước, kiểm tra readiness, chuyển traffic, rồi dừng replica cũ. Xác nhận registry luôn có ít nhất một instance phục vụ được.

## 18. Ghi nhớ và nguồn tra cứu

- `ServiceRegistry` cung cấp hợp đồng register, deregister và cập nhật trạng thái; `Registration` mô tả instance cần đăng ký.
- Auto-registration thường được bật mặc định khi provider phù hợp có mặt và cấu hình không tắt.
- `@EnableDiscoveryClient` không còn bắt buộc trong phiên bản hiện hành nếu implementation provider đã có trên classpath.
- `InstancePreRegisteredEvent` được phát trước thao tác register; `InstanceRegisteredEvent` được phát sau auto-registration. Hai event không được phát khi auto-registration bị tắt bằng property chung.
- Implementation dùng `AbstractAutoServiceRegistration` thường chờ `WebServerInitializedEvent` để lấy port thực tế.
- `register-management` mặc định cho phép đăng ký management instance khi management port riêng và provider hỗ trợ.
- Khi context đóng, implementation phổ biến gọi `stop()` và deregister instance; process bị kill cưỡng bức cần TTL/lease/heartbeat để dọn stale registration.
- `/actuator/serviceregistry` đọc hoặc cập nhật trạng thái theo khả năng provider; giá trị status không đồng nhất giữa các registry.
- Tắt auto-registration không đồng nghĩa tắt discovery read API.
- Kiểm thử cả startup, shutdown, registry outage, nhiều replica và trường hợp registration stale.

Nguồn chính thức để đối chiếu theo phiên bản Spring Cloud/Spring Boot của dự án:

1. [Spring Cloud Commons – Common Abstractions: ServiceRegistry và Auto-Registration](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html)
2. [Spring Cloud Commons – Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html)
3. [Spring Cloud Commons Javadoc – `ServiceRegistry`](https://javadoc.io/static/org.springframework.cloud/spring-cloud-commons/5.0.2/org/springframework/cloud/client/serviceregistry/ServiceRegistry.html)
4. [Spring Cloud Commons Javadoc – `Registration`](https://javadoc.io/static/org.springframework.cloud/spring-cloud-commons/5.0.2/org/springframework/cloud/client/serviceregistry/Registration.html)
5. [Spring Cloud Commons Javadoc – `AbstractAutoServiceRegistration`](https://javadoc.io/static/org.springframework.cloud/spring-cloud-commons/5.0.2/org/springframework/cloud/client/serviceregistry/AbstractAutoServiceRegistration.html)
6. [Spring Cloud Commons Javadoc – `RegistrationLifecycle`](https://javadoc.io/static/org.springframework.cloud/spring-cloud-commons/5.0.2/org/springframework/cloud/client/serviceregistry/RegistrationLifecycle.html)
7. [Spring Cloud Zookeeper – Service Registry](https://docs.spring.io/spring-cloud-zookeeper/reference/service-registry.html)
8. [Spring Cloud – Release train và tương thích Spring Boot](https://spring.io/projects/spring-cloud/)
