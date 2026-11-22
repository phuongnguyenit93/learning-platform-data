# Phân biệt JMX exposure với HTTP exposure trong Spring Boot

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích **exposure** của Spring Boot Actuator là việc cho phép endpoint quản trị được truy cập qua một **công nghệ truyền tải (technology)** nhất định.
- Phân biệt **HTTP exposure** (qua web endpoint/HTTP request) với **JMX exposure** (qua MBeanServer, ObjectName và JMX client).
- Hiểu các nhóm cấu hình `management.endpoints.web.exposure.*` và `management.endpoints.jmx.exposure.*` hoạt động **độc lập**.
- Phân biệt Actuator endpoints được expose qua JMX với các **custom MBeans** có `@ManagedResource` hoặc Standard/MXBean interface.
- Đọc và cấu hình `spring.jmx.enabled`, `management.endpoints.jmx.domain`, `management.endpoints.web.base-path` và các phần bảo mật liên quan trong bối cảnh phiên bản Spring Boot cụ thể.
- Nhận diện lỗi thường gặp: có HTTP endpoint nhưng không thấy JMX MBean, JMX đã bật nhưng `/actuator/...` trả 404, endpoint bị disable, ObjectName sai, hoặc nhầm phạm vi authorization.
- Đưa ra lựa chọn exposure cho local, CI, staging và production mà không công bố nhầm các operations nhạy cảm.

## 2. Exposure là gì và vì sao một endpoint có nhiều kênh?

Trong Spring Boot Actuator, một **endpoint** mô tả chức năng vận hành, chẳng hạn:

- `health`: kiểm tra tình trạng hoạt động.
- `info`: thông tin ứng dụng.
- `metrics`: truy vấn dữ liệu metric.
- `loggers`: xem hoặc thay đổi mức logging theo khả năng endpoint.
- `threaddump`: chụp thông tin thread.
- `env`: thông tin môi trường/cấu hình được lọc theo security và sanitization.

Một endpoint **có thể** được expose qua web hoặc JMX nếu có extension/technology adapter tương ứng và đã được bật theo điều kiện của phiên bản Spring Boot.

```text
                       Actuator endpoint "health"
                                  |
                      +-----------+-----------+
                      |                       |
                      v                       v
               HTTP exposure             JMX exposure
                      |                       |
                      v                       v
          GET /actuator/health       JMX MBean/ObjectName
                      |                       |
                      v                       v
               HTTP client              JMX client
               curl/browser             JConsole/JMC
```

Đây là hai **đường truy cập khác nhau** tới cùng một loại chức năng quản trị. Bật một đường **không tự động bật đường còn lại**.

Một điểm cần nhớ: JMX exposure không có nghĩa ứng dụng mở một HTTP URL mới; HTTP exposure không có nghĩa một MBean xuất hiện trong MBeanServer.

## 3. Ba quyết định riêng: available, enabled và exposed

Khi một Actuator endpoint không truy cập được, cần tách ba điều kiện:

1. **Endpoint có khả dụng không?** Dependency Actuator và các điều kiện bean/configuration có tạo endpoint tương ứng không?
2. **Endpoint được bật (enabled) không?** Cấu hình access/enabled theo phiên bản có cho phép endpoint hoạt động không?
3. **Endpoint được expose qua technology cần dùng không?** Web và JMX có include/exclude và điều kiện riêng.

Có thể biểu diễn:

```text
Endpoint tồn tại
      |
      v
Enabled / access được phép?
      |
      +-- No  --> không khả dụng
      |
      v
Technology exposure include?
      |
      +-- HTTP: web.exposure.include/exclude
      |
      +-- JMX: jmx.exposure.include/exclude
      |
      v
Cấu hình security + network có cho client truy cập?
```

Trong Spring Boot versions mới, còn có các thiết lập **endpoint access** (ví dụ các mức truy cập hạn chế), nên không thể coi danh sách `exposure.include` là cơ chế quyết định duy nhất. Dùng reference đúng **version** đang chạy.

Một endpoint được expose không đồng nghĩa mọi client có quyền dùng nó. Authorization, authentication, network exposure và access policy vẫn phải cấu hình.

## 4. HTTP exposure: công bố qua web

HTTP exposure thường xuất hiện dưới base path Actuator, ví dụ:

```text
GET http://localhost:8080/actuator/health
GET http://localhost:8080/actuator/info
GET http://localhost:8080/actuator/metrics
```

Base path và cổng ở đây chỉ để minh họa. Tên endpoint, endpoint có tồn tại và được expose hay không phụ thuộc dependencies/configuration. Nếu cấu hình management server port riêng, URL sẽ dùng cổng management tương ứng.

Một cấu hình minh họa:

```yaml
management:
  endpoints:
    web:
      base-path: /actuator
      exposure:
        include: health,info,metrics
```

Ý nghĩa:

- Chọn các endpoint IDs đưa ra bằng HTTP technology.
- Dùng `/actuator` làm base path cho web management endpoints.
- Không đòi hỏi JMX exporter phải chạy.
- Không tự thay đổi danh sách endpoint được expose bằng JMX.

Nếu application có context path, management base path hoặc separate management port, URL thực tế sẽ khác. Đừng hardcode đường dẫn `/actuator` khi vận hành nếu config đã điều chỉnh.

### Kiểm tra HTTP exposure

Có thể thử từ host được cấp quyền:

```bash
curl -i http://localhost:8080/actuator/health
```

Kết quả có thể là 200, 503, 401, 403, 404 hoặc phản hồi khác tùy health status, security và routing. Không dùng mỗi mã 404 để khẳng định `health` endpoint không tồn tại: có thể sai port/path, chưa expose hoặc không bật; cũng có môi trường cố ý che thông tin.

## 5. JMX exposure: công bố qua MBeanServer

JMX (Java Management Extensions) cung cấp `MBeanServer`, nơi các MBeans được đăng ký bằng `ObjectName`.

Actuator có thể expose endpoints như JMX MBeans để JConsole hoặc JMX client truy cập.

Một cấu hình minh họa:

```yaml
management:
  endpoints:
    jmx:
      exposure:
        include: health,info,metrics
```

Cấu hình này chỉ áp dụng cho **JMX technology của Actuator endpoints**, không đặt một HTTP route.

Luồng:

```text
Spring Boot Actuator endpoint
             |
             v
Actuator JMX endpoint infrastructure
             |
             v
MBeanServer
             |
             v
JMX ObjectName
             |
             v
JConsole / JMX client
```

ObjectName của Actuator JMX endpoints chịu ảnh hưởng cấu hình domain/naming, khác với URL HTTP. Không suy ra ObjectName từ URL bằng cách thay dấu `/` thành `:` hoặc từ một HTTP endpoint ID bất kỳ.

### Kiểm tra JMX exposure

Sử dụng JConsole kết nối đến JVM, rồi xem cây MBeans trong domain Actuator, hoặc gọi JMX API:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import java.util.Set;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();

Set<ObjectName> names = server.queryNames(null, null);
for (ObjectName name : names) {
    if (name.getDomain().contains("endpoint")) {
        System.out.println(name.getCanonicalName());
    }
}
```

Đây chỉ là cách tìm sơ bộ: domain mặc định hoặc tùy chỉnh có thể không chứa chữ `endpoint`. Khi debug thực tế, xem cấu hình `management.endpoints.jmx.domain` và query domain đã được chọn. Nếu exporter dùng MBeanServer khác platform server, phải truy cập đúng server.

## 6. Hai namespace cấu hình exposure độc lập

Một cấu hình Spring Boot có thể quy định:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,prometheus
    jmx:
      exposure:
        include: health,info,metrics
```

Từ cấu hình này:

- `health` và `info` được chọn cho cả hai technology nếu endpoint hợp lệ và các điều kiện khác thỏa.
- `prometheus` được chọn cho HTTP, không tự được chọn cho JMX.
- `metrics` được chọn cho JMX, không tự được chọn cho HTTP.
- Các điều kiện dependency, enablement và access vẫn quyết định endpoint thực sự có mặt.
- `prometheus` không nhất thiết hiện diện nếu không có registry/dependency tương ứng.

Có thể diễn đạt ngắn:

```text
management.endpoints.web.exposure  !=
management.endpoints.jmx.exposure
```

Việc một endpoint được chọn qua HTTP không tự đồng nghĩa có một JMX endpoint tương đương.

## 7. Bảng so sánh HTTP exposure và JMX exposure

| Tiêu chí | HTTP exposure | JMX exposure |
|---|---|---|
| Kênh truy cập | HTTP(S) | JMX/MBeanServer |
| Định danh endpoint | URL path | ObjectName + attributes/operations |
| Client thường gặp | curl, browser, reverse proxy, HTTP monitoring | JConsole, JMC, JMX connector client |
| Cấu hình include/exclude | `management.endpoints.web.exposure.*` | `management.endpoints.jmx.exposure.*` |
| Base namespace | `management.endpoints.web.base-path` | `management.endpoints.jmx.domain` |
| Network | Web server/management HTTP server | Local MBeanServer hoặc JMX remote connector |
| Authorization | Spring Security / web infrastructure | JMX authentication/authorization và connector controls |
| Format phổ biến | HTTP response, thường JSON/text | JMX attributes/operations theo metadata |
| Browser truy cập trực tiếp | Có thể | Không qua URL HTTP thông thường |
| Thay đổi port | `management.server.port` khi cấu hình management web port riêng | JMX remote config riêng, không đồng nghĩa với management HTTP port |
| Thích hợp | Web health checks, metrics scraping, automation qua HTTP | JVM management, JConsole, JMX-centric operations |
| Scope | HTTP clients được network cho phép | JVM/JMX clients được connector cho phép |

Không có công nghệ nào mặc nhiên “an toàn hơn”. Cả hai cần thiết kế exposure và security riêng. HTTP/HTTPS có hệ sinh thái proxy, auth và observability rộng; JMX local có thể thuận tiện khi debug JVM. Nhưng JMX remote connector nếu cấu hình sai cũng có rủi ro nghiêm trọng.

## 8. “Exposed” không có nghĩa “public Internet”

Trong Spring Boot, **exposed** có nghĩa endpoint được đưa vào bề mặt công nghệ tương ứng; đó chưa chắc là public.

Ví dụ HTTP endpoint có thể:

- Chỉ lắng nghe localhost.
- Lắng nghe một management address nội bộ.
- Bị reverse proxy hoặc network policy chặn.
- Yêu cầu authentication/authorization.
- Chỉ mở trong môi trường kiểm thử.

JMX endpoint có thể:

- Chỉ được đọc trong cùng JVM qua platform MBeanServer.
- Có remote connector nhưng chỉ trên private network.
- Yêu cầu JMX authentication/TLS.
- Bị giới hạn bởi firewall hoặc container policy.

Vì thế cần tách:

```text
Technology exposure
          !=
Network reachability
          !=
Authenticated identity
          !=
Authorized action
```

Một cấu hình include endpoint không nên được xem là đầy đủ nếu chưa có chính sách bảo mật và networking.

## 9. HTTP exposure không phải Spring MVC controller thông thường

Actuator web endpoints dùng một infrastructure riêng để map endpoint IDs và operations sang HTTP routes. Nó liên quan tới web stack đang sử dụng (Spring MVC/WebFlux nếu có), nhưng không nên coi mọi endpoint như một `@RestController` thủ công.

Ví dụ `health` thường được truy cập bằng GET, nhưng tùy actuator endpoint operation, có thể có operations dạng read/write/delete và semantics khác.

Spring Security configuration cần bao phủ management endpoints cụ thể. Một số ứng dụng có management context hoặc port riêng, nên security chain và network policy cần được kiểm tra tại deployment thực tế.

Đồng thời, **custom MVC controller** ở `/admin/status` không phải là Actuator endpoint chỉ vì tên mang ý nghĩa quản trị. Nó không tự xuất hiện trong `management.endpoints.jmx.exposure`.

## 10. JMX exposure không phải mọi custom MBean

Đây là điểm dễ nhầm khi ứng dụng dùng Spring Framework JMX bên cạnh Spring Boot Actuator.

Custom MBean:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.shop.orders:type=Queue,name=outbox")
public class OrderQueueManagement {

    @ManagedAttribute
    public int getPendingCount() {
        return 12;
    }
}
```

Nếu bean được Spring JMX exporter đăng ký, nó xuất hiện dưới ObjectName đã cấu hình.

**Nhưng** `management.endpoints.jmx.exposure.include=health,info` là cấu hình **Actuator JMX endpoint exposure**. Nó không phải allowlist trực tiếp áp dụng cho mọi custom `@ManagedResource` hay JVM platform MBeans.

Phân biệt ba tập:

1. **Actuator endpoints qua HTTP.**
2. **Actuator endpoints qua JMX.**
3. **Custom/platform MBeans đăng ký trực tiếp hoặc qua Spring `MBeanExporter`.**

Một custom MBean có thể tồn tại dù HTTP Actuator exposure không bật. Ngược lại, HTTP Actuator `/health` có thể hoạt động mà custom MBean chưa được export.

## 11. JVM platform MBeans và Actuator JMX endpoints khác nhau

JVM thường có platform MBeans như:

```text
java.lang:type=Memory
java.lang:type=Threading
java.lang:type=Runtime
java.lang:type=ClassLoading
```

Đây là Java platform management MBeans. Chúng không phải do `management.endpoints.jmx.exposure.include` của Actuator tạo ra.

Cấu hình Actuator JMX exposure không đồng nghĩa với việc tắt platform MBeans. Khi JConsole kết nối JVM, có thể thấy cả MBeans của JVM, thư viện, custom application và Actuator.

Để không nhầm:

| Nguồn MBean | Ai tạo/đăng ký? | Cách kiểm soát |
|---|---|---|
| JVM platform | Java runtime/platform | JVM management facilities và JMX access |
| Spring custom `@ManagedResource` | Spring JMX exporter | Annotation/assembler/export configuration |
| Standard/MXBean custom | App/library register | Registration owner, ObjectName, MBeanServer |
| Actuator JMX endpoint | Spring Boot Actuator JMX infrastructure | Actuator endpoint enablement + JMX exposure |

Nếu tắt một Actuator endpoint qua JMX, không suy ra JVM `java.lang:type=Memory` biến mất.

## 12. Hiểu đúng spring.jmx.enabled

Trong Spring Boot, `spring.jmx.enabled` thường liên quan tới việc bật tích hợp/export Spring JMX. Ví dụ:

```yaml
spring:
  jmx:
    enabled: true
```

Tuy nhiên, không nên hiểu nó là công tắc “bật toàn bộ JMX remote cho Internet”. Nó không tự cấu hình đầy đủ JMX remote ports, network policy, authentication hoặc TLS.

Với Actuator, khả năng expose qua JMX còn cần:

- Actuator endpoint bean tồn tại và được phép hoạt động.
- JMX endpoint exposure đã cấu hình phù hợp.
- MBeanServer/export infrastructure được khởi tạo.
- Client có đường truy cập JMX hợp lệ.

Tính năng và giá trị mặc định thay đổi theo phiên bản Spring Boot, nên tham khảo tài liệu của version sử dụng, thay vì sao chép cấu hình giữa các major versions một cách máy móc.

## 13. Domain của Actuator JMX và base-path HTTP

Hai cấu hình thường gây nhầm:

```yaml
management:
  endpoints:
    web:
      base-path: /manage
    jmx:
      domain: com.example.shop.actuator
```

**HTTP:** endpoint `health` có thể nằm dưới `/manage/health` với điều kiện routing và exposure phù hợp.

**JMX:** Actuator MBeans có domain `com.example.shop.actuator`, với ObjectName được tạo bởi infrastructure/naming convention tương ứng.

Đổi `web.base-path` không đổi JMX ObjectNames. Đổi `jmx.domain` không đổi HTTP URL.

Đặt domain tùy chỉnh có thể tránh collision với MBeans khác trong cùng server, nhưng phải lưu ý JMX exporter/dashboard client đang query domain cũ.

## 14. Include và exclude

Các nhóm cấu hình ví dụ:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
        exclude: env
    jmx:
      exposure:
        include: health,info
        exclude: shutdown
```

Khi một endpoint đồng thời nằm trong include và exclude, exclude thường được dùng để loại endpoint khỏi bề mặt exposure theo logic của Spring Boot; luôn đối chiếu version cụ thể.

Có thể dùng `include: "*"` để chọn nhiều endpoints, nhưng điều đó có rủi ro nếu được áp dụng trong production không kiểm soát. Với YAML, ký tự `*` phải được đặt trong chuỗi trích dẫn để tránh cú pháp YAML alias:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "*"
```

Dù exposure all được cấu hình, nó không tự bật mọi endpoint đã disabled hoặc đáp ứng mọi security/access condition. Không nên dùng include all nếu mục tiêu chỉ là health/metrics.

## 15. Endpoint enablement và access theo version

Một số Spring Boot versions sử dụng properties như `management.endpoint.<id>.enabled` và global enablement defaults, trong khi những phiên bản mới có cơ chế **access** nhằm chỉ định quyền ở cấp endpoint.

Khái niệm:

```text
Endpoint bean
   |
   +-- có dependency/condition cần thiết?
   |
   +-- enabled / access được cho phép?
   |
   +-- technology exposure include?
   |
   +-- security/network cho client thực sự truy cập?
```

Nếu endpoint chưa được bật, thêm vào `web.exposure.include` chưa chắc làm nó xuất hiện.

Nếu một endpoint chỉ cho phép read-only access, các write operations có thể bị hạn chế dù endpoint được expose theo một technology nào đó. Từng behavior phụ thuộc phiên bản và endpoint support.

Vì vậy khi xử lý lỗi, luôn xác định Spring Boot **version**, property thực tế, danh sách endpoints hiện có và lỗi client.

## 16. Một ví dụ cấu hình production mang tính tham khảo

Một ứng dụng chủ yếu cần Kubernetes HTTP readiness/health và Prometheus scrape, còn JMX được dùng để debug JVM nội bộ:

```yaml
spring:
  jmx:
    enabled: true

management:
  endpoints:
    web:
      base-path: /actuator
      exposure:
        include: health,info,prometheus
    jmx:
      exposure:
        include: health,info,metrics
  endpoint:
    health:
      show-details: when_authorized
```

**Đây không phải template bảo mật hoàn chỉnh.** Cần thêm:

- Dependency Actuator và metrics registry phù hợp.
- Kiểm tra endpoint defaults của Boot version.
- Spring Security rules cho HTTP Actuator.
- Network policy/firewall/management port.
- JMX remote connector security nếu có remote JMX.
- Access policy cho endpoint có write operations.
- Kiểm tra `info` có dữ liệu nhạy cảm hay không.
- Kiểm tra health details được phép công bố đến đối tượng nào.

Cấu hình “an toàn” phụ thuộc mô hình threat và deployment, không chỉ hai danh sách include.

## 17. Phân biệt management.server.port và JMX remote port

Nếu đặt:

```yaml
management:
  server:
    port: 9090
```

thì cấu hình này thường điều khiển **management HTTP server port** (khi web management server riêng có hiệu lực). Nó không tự làm JMX remote connector lắng nghe cổng 9090.

JMX remote có cơ chế cấu hình riêng ở cấp JVM/connector. Ví dụ các JVM flags như `com.sun.management.jmxremote.port` chỉ mang tính tham khảo và cần xem kỹ cách bảo vệ remote JMX.

Tránh suy luận:

```text
management.server.port = 9090
=> JMX remote port = 9090  (SAI)
```

Trong container, việc expose management HTTP port trong Kubernetes Service cũng không đồng nghĩa JConsole có thể kết nối tới MBeanServer qua cùng port.

## 18. Những use cases phù hợp cho mỗi technology

### HTTP exposure hợp khi

- Load balancer hoặc orchestrator cần health endpoint.
- Prometheus-compatible scraper lấy metrics qua HTTP.
- DevOps tooling, API gateway hoặc automation dùng HTTP clients.
- Muốn security routing thông qua web stack.
- Đang dùng monitoring/alerting dựa trên HTTP endpoints.

### JMX exposure hợp khi

- Kỹ sư cần JConsole hoặc JMC inspect JVM/MBeans.
- Có công cụ quản trị Java dựa trên ObjectName.
- Muốn đọc các attributes/operations của MBeans trong cùng JVM.
- Dùng JMX collector để lấy thông tin từ JVM và ứng dụng.
- Cần vận hành các chức năng quản trị được thiết kế riêng cho JMX.

### Có thể sử dụng cả hai

Một ứng dụng có thể dùng HTTP cho health checks và monitoring, JMX cho diagnostics JVM. Tuy nhiên phải quản lý riêng scope, access và alerting; việc có cả hai không tự tăng an toàn.

## 19. Trường hợp HTTP hoạt động nhưng JMX không thấy endpoint

Ví dụ:

```text
GET /actuator/health -> 200
JConsole -> không thấy Actuator health MBean
```

Các giả thuyết:

1. JMX exposure không include `health`.
2. JMX export bị tắt hoặc chưa cấu hình theo phiên bản Boot.
3. JConsole kết nối sai JVM hoặc sai MBeanServer/connector.
4. Actuator JMX domain được đổi nên tìm sai nhánh.
5. Endpoint MBean registration lỗi do ObjectName conflict.
6. Có sự khác biệt profile/property giữa môi trường.
7. Actuator endpoint chưa được expose qua JMX do điều kiện technology hỗ trợ.

Cách kiểm tra:

- Xác nhận active Spring profiles.
- Kiểm tra `management.endpoints.jmx.exposure.*`.
- Kiểm tra `spring.jmx.enabled` và config tương ứng.
- Đọc startup logs về JMX registration.
- Query ObjectNames trên đúng server/domain.
- Đọc `MBeanInfo` nếu ObjectName tồn tại.

Không đổi HTTP security rules để sửa một lỗi thuộc JMX registration nếu chưa có bằng chứng liên quan.

## 20. Trường hợp JMX thấy MBean nhưng HTTP 404

Ví dụ:

```text
JConsole -> Actuator metrics MBean tồn tại
GET /actuator/metrics -> 404
```

Các giả thuyết:

1. `metrics` không nằm trong web exposure include.
2. HTTP base path đã đổi.
3. Management port/address khác.
4. Không có web endpoint infrastructure trong deployment.
5. Endpoint bị disabled hoặc bị hạn chế theo access policy.
6. Request đang đi qua reverse proxy/router không forward đúng.
7. URL sai do context path hoặc management context.

Cách xử lý không phải “tắt JMX” hay “đăng ký lại MBean”. Kiểm tra riêng các điều kiện web endpoint.

## 21. Phân biệt lỗi authorization và lỗi exposure

Có thể gặp:

| Kết quả | Ý nghĩa thường gặp | Kiểm tra |
|---|---|---|
| HTTP 200 | Web endpoint đã trả lời thành công | Không tự nói gì về JMX |
| HTTP 401 | Cần authentication hoặc credentials không hợp lệ | HTTP security |
| HTTP 403 | Đã xác thực nhưng không được phép hoặc policy từ chối | HTTP authorization |
| HTTP 404 | Không có route phù hợp hoặc bị che | Web exposure, path, endpoint availability |
| JMX `InstanceNotFoundException` | ObjectName không có MBean | JMX registration/domain |
| JMX access denied | Client thiếu quyền theo JMX connector/security policy | JMX authentication/authorization |
| JMX operation không tìm thấy | MBeanInfo/signature không phù hợp | JMX metadata/operation mapping |

Một số hệ thống security có thể cố ý trả 404 cho tài nguyên không được phép, nên trạng thái HTTP không phải bằng chứng duy nhất về nguyên nhân. Quan trọng là **đặt lỗi vào đúng technology** trước khi thay cấu hình.

## 22. Kiểm thử HTTP exposure

Với Spring Boot test, có thể dùng HTTP client/test framework để xác minh route và status trong context phù hợp.

Ví dụ curl:

```bash
curl -i http://localhost:8080/actuator/health
curl -i http://localhost:8080/actuator/metrics
```

Một test nên xác minh:

- Endpoint được phép có thể truy cập bởi principal phù hợp.
- Endpoint không được phép không lộ data.
- Cấu hình web path và management port chính xác.
- Health details không rò rỉ secret.

Đừng chỉ assert status 200 khi ứng dụng có authentication; cần dùng credentials/test principal tương ứng.

## 23. Kiểm thử JMX exposure

Một JMX integration test có thể:

1. Khởi động Spring context với Actuator/JMX config cần kiểm tra.
2. Lấy MBeanServer được Actuator JMX infrastructure sử dụng.
3. Query ObjectNames theo domain mong đợi.
4. Assert Actuator MBeans được include xuất hiện.
5. Assert endpoints bị exclude không xuất hiện.
6. Đọc MBeanInfo để xác minh attributes/operations.
7. Đóng context và xác minh cleanup registration thuộc context.

Ví dụ kiểm tra MBeanServer:

```java
import javax.management.MBeanServer;
import javax.management.ObjectName;
import java.util.Set;

public final class JmxEndpointInspection {
    public static void list(MBeanServer server, String domain)
            throws Exception {
        Set<ObjectName> names = server.queryNames(
                new ObjectName(domain + ":*"),
                null);

        names.stream()
                .map(ObjectName::getCanonicalName)
                .sorted()
                .forEach(System.out::println);
    }
}
```

Đối số `domain` trong ví dụ cần là domain hợp lệ được cấu hình cho Actuator, không lấy trực tiếp từ input không tin cậy. Thực thi trong test có server riêng giúp tránh registration state của các ứng dụng/tests khác.

## 24. Kết hợp test hai technology một cách độc lập

Trong một integration test suite:

- **Test web exposure** bằng HTTP test client và security configuration.
- **Test JMX exposure** bằng MBeanServer/ObjectName.
- **Test custom MBeans** bằng exporter và MBeanInfo riêng.
- **Test endpoint availability** qua Spring context/configuration.

Đừng dùng `GET /actuator/health = 200` để khẳng định `health` đã được expose qua JMX. Cũng đừng dùng `isRegistered(ObjectName)` để khẳng định HTTP URL tồn tại.

Đây là các hợp đồng truy cập riêng, cần các assertions riêng.

## 25. Chính sách exposure theo môi trường

| Môi trường | HTTP exposure | JMX exposure | Lưu ý an toàn |
|---|---|---|---|
| **Local** | Health/info/metrics phục vụ debug | Có thể bật đủ cho thử nghiệm | Không mở remote JMX không bảo vệ |
| **CI** | Test endpoints được phép/không được phép | Test ObjectNames và metadata | Cô lập server, tránh xung đột tests |
| **Staging** | Phản ánh production | Phản ánh production nếu cần | Kiểm tra security, routing, monitoring |
| **Production** | Allowlist tối thiểu theo vận hành | Chỉ endpoint cần thiết; giới hạn JMX access | Defense in depth, audit và không expose secrets |

Bảng là hướng dẫn thiết kế, không phải Spring Boot defaults. Một dự án production chỉ cần HTTP metrics có thể tắt Actuator JMX exposure nếu không dùng; một dự án dựa trên JMX có thể giữ HTTP exposure tối thiểu.

Không nên bật mọi endpoint để “đỡ lỗi dashboard”, vì thay đổi exposure có thể tạo bề mặt tấn công mới.

## 26. Một ví dụ vận hành: health qua HTTP, diagnostics qua JMX

Một shop service có:

```text
Business service: orders-service
HTTP health:      /actuator/health
HTTP metrics:     /actuator/prometheus
JMX diagnostics:  java.lang:type=Threading
                  java.lang:type=Memory
Custom JMX:       com.example.shop.orders:type=Queue,name=outbox
```

Thiết kế:

- Orchestrator gọi HTTP health để biết instance còn phục vụ.
- Metrics scraper lấy time series qua HTTP endpoint.
- JConsole/approved JMX client đọc JVM thread/memory khi điều tra.
- Custom queue MBean công bố `PendingCount` và có thể có operation chỉ cho operator được ủy quyền.

Các đường access phục vụ mục tiêu khác nhau. HTTP health không cần đi qua JMX để lấy thread count, và JMX không nhất thiết phải được expose remote chỉ vì ứng dụng có Actuator.

## 27. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| HTTP `/actuator/health` có nhưng JMX health không thấy | JMX exposure/config khác web | Kiểm tra `jmx.exposure`, JMX enablement và domain |
| JMX metrics có nhưng HTTP metrics 404 | `metrics` không thuộc web include/path sai | Kiểm tra web exposure/base-path/port |
| `/actuator/prometheus` 404 | Thiếu registry/dependency hoặc chưa expose | Kiểm tra Prometheus registry và config |
| Spring `@ManagedResource` không có HTTP URL | Custom MBean không phải Actuator web endpoint | Dùng JMX client hoặc tạo web endpoint có chủ đích |
| Actuator JMX bị tắt nhưng `java.lang` MBeans còn | JVM platform MBeans độc lập | Phân biệt nguồn MBean |
| JMX remote không kết nối dù `spring.jmx.enabled=true` | Chưa cấu hình remote connector/network | Phân biệt export với JMX remote |
| Thay `management.server.port` mà JConsole vẫn không thấy | Cổng này cho management HTTP | Kiểm tra JMX connector separately |
| HTTP 403 | Security policy | Đọc HTTP security configuration |
| ObjectName conflict | Actuator/custom exporter trùng tên | Tách domain/owner; không replace mù |
| Mở `include:"*"` production | Tăng exposure ngoài chủ đích | Dùng allowlist tối thiểu |

## 28. Bài tập thực hành

### Bài tập 1 — Phân biệt cấu hình

Đọc YAML:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
    jmx:
      exposure:
        include: health,metrics
```

Trả lời:

1. Endpoint IDs nào được chọn cho HTTP?
2. Endpoint IDs nào được chọn cho JMX?
3. `metrics` có chắc có URL HTTP không?
4. `info` có chắc có JMX MBean không?

**Đáp án định hướng:** (1) health/info; (2) health/metrics; (3) không, chưa được include web; (4) không, chưa được include JMX. Sự tồn tại thực tế còn phụ thuộc enablement/access/dependencies.

### Bài tập 2 — Thay base path

Thêm:

```yaml
management:
  endpoints:
    web:
      base-path: /ops
```

Hãy xác định đường dẫn HTTP health mới trong điều kiện cổng/context path không đổi, và giải thích tại sao JMX ObjectName không thay đổi do cấu hình web base path.

### Bài tập 3 — Kiểm tra security

Một team muốn public `/actuator/health` nhưng giữ `/actuator/metrics` chỉ cho internal monitoring. Hãy đề xuất HTTP authorization và network policy theo deployment. Đồng thời giải thích vì sao chính sách này **không tự bảo vệ** JMX remote connector.

### Bài tập 4 — Custom MBean không có HTTP route

Bạn export một `@ManagedResource` với ObjectName `com.example.shop:type=Queue,name=outbox`. JConsole đọc được `PendingCount`, nhưng GET `/actuator/queue` trả 404.

Hãy giải thích đây không nhất thiết là lỗi. Custom MBean không tự trở thành Actuator endpoint. Nếu muốn HTTP API, cần xây endpoint/controller phù hợp và đặt security riêng.

### Bài tập 5 — Test độc lập

Viết hai bài test:

- HTTP: endpoint `health` có thể truy cập trong role được phép.
- JMX: domain Actuator có MBean `health` với metadata mong đợi.

Giải thích vì sao không thể thay test JMX bằng test HTTP, hoặc ngược lại.

### Bài tập 6 — Deployment nhiều cổng

Một service có `server.port=8080`, `management.server.port=9090`, và JMX remote connector được cấu hình riêng. Vẽ sơ đồ ba tuyến truy cập, chỉ rõ HTTP business, HTTP management và JMX remote là các kênh độc lập.

## 29. Câu hỏi tự kiểm tra

**1. Bật HTTP exposure cho `metrics` có tự làm JMX MBean `metrics` xuất hiện không?**

Không. Cần cấu hình JMX exposure và những điều kiện endpoint/JMX khác tương ứng.

**2. `management.endpoints.jmx.exposure.include` có điều khiển custom `@ManagedResource` beans không?**

Không trực tiếp. Nó điều khiển exposure của Actuator endpoints qua JMX, không phải allowlist cho mọi custom MBeans.

**3. Đổi `management.endpoints.web.base-path` có đổi JMX domain không?**

Không. Hai namespace/configuration riêng.

**4. Có thể có JMX MBeans chuẩn JVM khi Actuator HTTP exposure tắt không?**

Có. JVM platform MBeans độc lập với Actuator HTTP technology.

**5. `spring.jmx.enabled=true` có tự mở remote JMX qua Internet không?**

Không. JMX remote connector/network/security cần cấu hình riêng.

**6. HTTP 401 và JMX `InstanceNotFoundException` có cùng nguyên nhân không?**

Không. HTTP 401 thường là authentication; JMX instance not found là ObjectName không được đăng ký ở server đang truy vấn.

**7. Vì sao nên kiểm thử web và JMX exposure riêng?**

Vì mỗi technology có routing, identity, configuration, security và client path độc lập.

## 30. Ghi nhớ

- Spring Boot Actuator có thể expose endpoints qua **HTTP** và **JMX** như hai technology riêng.
- `management.endpoints.web.exposure.*` và `management.endpoints.jmx.exposure.*` chọn endpoint IDs độc lập.
- HTTP dùng URL/base path/management web server; JMX dùng MBeanServer/ObjectName/JMX client.
- `spring.jmx.enabled` không tự mở JMX remote connector, và `management.server.port` không phải JMX remote port.
- Actuator JMX MBeans khác custom `@ManagedResource` và JVM platform MBeans.
- Endpoint phải tồn tại và được cho phép/enable trước khi exposure có hiệu quả; authorization/network access vẫn là tầng riêng.
- Đặt HTTP/JMX exposure theo nhu cầu vận hành và mức an toàn, tránh `include: "*"` không kiểm soát trong production.
- Test HTTP routes và JMX ObjectNames bằng công cụ phù hợp cho từng technology.
- Khi gặp lỗi, xác định trước vấn đề thuộc **endpoint availability**, **technology exposure**, **routing/registration** hay **security**.

## 31. Tài liệu tham khảo

- Spring Boot Reference — Actuator Endpoints: https://docs.spring.io/spring-boot/reference/actuator/endpoints.html
- Spring Boot Reference — JMX: https://docs.spring.io/spring-boot/reference/actuator/jmx.html
- Spring Boot Reference — Monitoring and Management over HTTP: https://docs.spring.io/spring-boot/reference/actuator/monitoring.html
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Java SE 21 — `MBeanServer`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
