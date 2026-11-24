# Bảo vệ endpoint quản trị, log chẩn đoán và dữ liệu dump

## 1. Vì sao endpoint quản trị cần được bảo vệ?

Spring Boot Actuator cung cấp endpoint để kiểm tra sức khỏe, xem metrics, thay đổi log level và thu thập thông tin chẩn đoán. Những endpoint này giúp vận hành ứng dụng, nhưng cũng có thể tiết lộ cấu hình nội bộ hoặc làm thay đổi hành vi của process.

Các endpoint như `health`, `metrics`, `loggers`, `env`, `configprops`, `threaddump` và `heapdump` có mức độ nhạy cảm khác nhau. Một số chỉ trả trạng thái tổng quát; một số có thể hiển thị tên bean, cấu hình, stack trace, dữ liệu trong bộ nhớ hoặc cho phép thay đổi log level. Nếu công khai tất cả endpoint trên cùng mạng với API nghiệp vụ, người ngoài có thể thu thập thông tin phục vụ tấn công hoặc gây tải lên process.

Với ứng dụng Spring Boot được biên dịch thành **GraalVM Native Image**, cần thêm một bước xác minh: khả năng hỗ trợ endpoint và công cụ chẩn đoán có thể khác JVM HotSpot. Một endpoint có mặt trong Actuator không có nghĩa mọi chức năng chẩn đoán của JVM đều hoạt động giống hệt trong native executable.

Bài này thuộc chương **Quan sát** của module **SPRING_BOOT_NATIVE_IMAGE**. Nội dung tập trung vào:

- Chỉ công khai những Actuator endpoint thật sự cần thiết.
- Bảo vệ endpoint quản trị bằng xác thực, phân quyền và giới hạn mạng.
- Quản lý log level động, log dữ liệu nhạy cảm và audit thao tác quản trị.
- Thu thập thread dump, heap dump và core dump an toàn.
- Phân biệt chẩn đoán trên JVM với khả năng monitoring của Native Image.
- Kiểm thử cấu hình bảo mật và quy trình xử lý sự cố.

## 2. Phân loại endpoint theo mục đích và mức độ nhạy cảm

Không nên xem mọi Actuator endpoint là một nhóm có cùng rủi ro. Hãy phân loại trước khi cấu hình exposure:

| Endpoint | Mục đích | Rủi ro cần cân nhắc |
| --- | --- | --- |
| `health` | Kiểm tra trạng thái ứng dụng và health indicator | Chi tiết health có thể tiết lộ dependency, host hoặc trạng thái hạ tầng |
| `info` | Hiển thị thông tin ứng dụng/build | Có thể lộ version, commit, tên dịch vụ hoặc thông tin triển khai |
| `metrics` | Đọc số liệu Micrometer | Tên metric/tag có thể tiết lộ cấu trúc nội bộ; truy vấn quá rộng gây tải |
| `prometheus` | Xuất metrics cho Prometheus | Có thể lộ tag và cardinality lớn; chỉ cần mở cho scraper |
| `loggers` | Đọc hoặc thay đổi logger level | Người có quyền có thể bật DEBUG/TRACE, làm lộ dữ liệu và tăng dung lượng log |
| `threaddump` | Xem stack trace, thread state và lock | Có thể lộ package, endpoint nội bộ, SQL hoặc thông tin trong stack |
| `heapdump` | Tạo bản dump heap | Có thể chứa token, password, session, dữ liệu cá nhân và payload |
| `env` / `configprops` | Kiểm tra environment và configuration properties | Có nguy cơ tiết lộ secret, URL, key và cấu hình bảo mật |
| `mappings` / `conditions` / `beans` | Chẩn đoán route, auto-configuration và bean | Tiết lộ cấu trúc ứng dụng và thành phần đang chạy |
| `shutdown` | Yêu cầu tắt ứng dụng | Thao tác ảnh hưởng availability; thường không cần bật |

Một cấu hình khởi đầu thận trọng chỉ expose các endpoint phục vụ probe và metrics:

```properties
management.endpoints.web.exposure.include=health,info,metrics,prometheus
management.endpoint.health.show-details=when-authorized
management.endpoint.health.roles=OPS
management.endpoints.web.base-path=/actuator
```

Endpoint `prometheus` chỉ hoạt động khi ứng dụng có registry tương ứng, ví dụ dependency Micrometer Prometheus. Nếu môi trường không dùng Prometheus, bỏ endpoint này khỏi danh sách.

Không dùng `management.endpoints.web.exposure.include=*` cho production. Nếu cần endpoint chẩn đoán trong một đợt điều tra, hãy bật có kiểm soát, giới hạn người truy cập và tắt lại sau khi hoàn tất.

### 2.1. Phân biệt endpoint được bật và endpoint được expose

Actuator có hai lớp kiểm soát:

- **Endpoint availability/enabled:** endpoint có được đăng ký và hoạt động trong application context hay không.
- **Web exposure:** endpoint có được công bố qua HTTP hay không.

Một endpoint có thể được bật nhưng không được expose qua web. Ngược lại, thêm endpoint vào danh sách exposure không thể làm một endpoint bị disable hoặc thiếu dependency tự xuất hiện.

Giữ hai lớp cấu hình riêng giúp giảm bề mặt tấn công. Với endpoint chỉ cần dùng qua JMX hoặc một kênh quản trị khác, không nhất thiết expose nó qua HTTP.

## 3. Tách cổng quản trị khỏi cổng API nghiệp vụ

Một cách giảm rủi ro là dùng management port riêng:

```properties
server.port=8080

management.server.port=8081
management.endpoints.web.base-path=/actuator
management.endpoints.web.exposure.include=health,info,metrics,prometheus
```

Khi đó, API nghiệp vụ lắng nghe ở port 8080, còn Actuator HTTP endpoints lắng nghe ở port 8081. Tuy nhiên, **cổng riêng không tự tạo ra bảo mật**. Nếu port 8081 vẫn được mở ra Internet hoặc mạng người dùng, endpoint vẫn có thể bị truy cập.

Nếu management endpoint chỉ phục vụ process agent trên cùng máy, có thể bind loopback:

```properties
management.server.address=127.0.0.1
```

Lựa chọn này phù hợp khi scraper hoặc công cụ quản trị chạy cùng host/network namespace. Trong Kubernetes, container và sidecar có thể chia sẻ network namespace trong cùng Pod; scraper chạy ngoài Pod không thể truy cập địa chỉ loopback của container. Khi cần probe hoặc scrape từ ngoài Pod, hãy bind vào interface nội bộ phù hợp và giới hạn bằng NetworkPolicy, firewall hoặc service riêng.

Các lớp bảo vệ nên kết hợp: management port riêng nếu cần, bind vào interface nội bộ, NetworkPolicy/firewall, authentication, authorization, TLS hoặc mTLS và audit thao tác quản trị. Không dùng port khác như lý do để bỏ xác thực; mạng nội bộ vẫn có thể bị truy cập bởi workload hoặc tài khoản đã bị xâm nhập.

## 4. Bảo vệ Actuator bằng Spring Security

Khi có Spring Security trên classpath, hãy cấu hình rõ ai được truy cập endpoint quản trị. Ví dụ dưới đây dùng Servlet stack và một role vận hành riêng:

```java
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ActuatorSecurityConfiguration {

@Bean
@Order(1)
SecurityFilterChain actuatorSecurity(HttpSecurity http) throws Exception {
    http
        .securityMatcher(EndpointRequest.toAnyEndpoint())
        .authorizeHttpRequests(authorize -> authorize
            .anyRequest().hasRole("OPS")
        )
        .httpBasic(Customizer.withDefaults());

    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain applicationSecurity(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/public/**").permitAll()
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults());

    return http.build();
}
}
```

`EndpointRequest.toAnyEndpoint()` tạo matcher theo Actuator endpoint mapping thay vì hardcode từng URL. Chain có `@Order(1)` xử lý endpoint quản trị trước; chain ứng dụng là fallback cho request còn lại. Ví dụ giả định ứng dụng đã cấu hình authentication provider hoặc user store và cấp role `OPS` cho tài khoản vận hành.

HTTP Basic chỉ an toàn khi truyền qua TLS và mật khẩu được quản lý bằng secret store. Production có thể dùng OAuth2 Resource Server, mTLS tại ingress hoặc identity provider nội bộ. Tránh đặt mật khẩu trực tiếp trong source code hoặc file cấu hình được commit.

### 4.1. Phân quyền theo endpoint

Không phải mọi endpoint quản trị đều cần cùng một role. Có thể tách quyền đọc health/metrics với quyền thay đổi log level hoặc tải dump:

- `MONITOR`: đọc health và metrics.
- `OPS`: đọc thông tin vận hành và thay đổi logger level.
- `DIAGNOSTICS`: tạo thread dump hoặc heap dump.
- `SECURITY_ADMIN`: truy cập endpoint có cấu hình nhạy cảm, nếu thật sự cần.

Khi cần policy chi tiết, dùng request matcher cụ thể hoặc authorization manager phù hợp với endpoint. Kiểm tra cả quyền đọc lẫn quyền ghi; endpoint `loggers` có thể nhận POST để thay đổi cấu hình.

### 4.2. CSRF và endpoint thay đổi trạng thái

Spring Security bật CSRF protection theo cấu hình mặc định cho nhiều ứng dụng Servlet. Các thao tác POST như thay đổi log level có thể cần CSRF token. Không tắt CSRF toàn cục chỉ để một lệnh vận hành chạy được.

Nếu endpoint quản trị chỉ dành cho machine-to-machine, dùng authentication không dựa trên cookie và thiết kế CSRF policy có chủ đích, giới hạn đúng management matcher. Nếu dùng session/cookie trong trình duyệt, giữ CSRF protection và cấp token cho thao tác thay đổi trạng thái.

### 4.3. WebFlux dùng reactive security

Ứng dụng WebFlux dùng `SecurityWebFilterChain` và `ServerHttpSecurity`, không dùng Servlet `SecurityFilterChain`. Cần cấu hình matcher Actuator reactive tương ứng, authorization rule và authentication mechanism trên reactive stack. Không copy trực tiếp bean security Servlet vào ứng dụng reactive.

## 5. Giới hạn thông tin health endpoint

Health endpoint thường cần cho load balancer, orchestrator và monitoring. Nhưng trả toàn bộ chi tiết cho mọi caller có thể làm lộ topology, dependency và trạng thái hạ tầng.

Cấu hình:

```properties
management.endpoint.health.show-details=when-authorized
management.endpoint.health.roles=OPS
management.endpoint.health.show-components=when-authorized
```

Với caller không có role phù hợp, endpoint có thể chỉ trả trạng thái tổng quát. Người vận hành được cấp quyền mới xem component details.

Spring Boot còn hỗ trợ health groups như liveness và readiness. Trong môi trường orchestration, có thể bật probe endpoint:

```properties
management.endpoint.health.probes.enabled=true
```

Liveness nên phản ánh process có cần restart hay không. Không đưa mọi dependency ngoài như database, message broker hoặc API bên thứ ba vào liveness nếu một sự cố dependency tạm thời sẽ khiến orchestrator restart hàng loạt instance. Readiness có thể phản ánh ứng dụng đã sẵn sàng nhận traffic và các dependency thiết yếu cho request hiện tại.

## 6. Bảo vệ endpoint loggers và thay đổi log level

Actuator `loggers` cho phép xem logger đang dùng level nào và có thể thay đổi level lúc runtime. Điều này hữu ích khi cần bật DEBUG trong một khoảng thời gian ngắn để điều tra.

Endpoint phải được expose qua HTTP mới có route. Nếu cần bật các endpoint chẩn đoán trong một profile vận hành riêng, cấu hình danh sách tường minh và chỉ kích hoạt cùng với security/network policy đã chuẩn bị:

```properties
management.endpoints.web.exposure.include=health,info,metrics,prometheus,loggers,threaddump,heapdump
```

Danh sách này là ví dụ cho một profile chẩn đoán được bảo vệ. Không thêm `env`, `configprops` hoặc wildcard chỉ để tiện điều tra; cân nhắc khả năng hỗ trợ từng endpoint trên native runtime trước khi bật.

Ví dụ endpoint mặc định:

```text
GET  /actuator/loggers/com.example.orders
POST /actuator/loggers/com.example.orders
```

Body thay đổi level:

```json
{
  "configuredLevel": "DEBUG"
}
```

Có thể đặt level về INFO sau khi điều tra:

```json
{
  "configuredLevel": "INFO"
}
```

Level được thay đổi qua endpoint thường chỉ tồn tại trong runtime process; nó không tự cập nhật file cấu hình hoặc source configuration và có thể mất khi restart. Nếu muốn level mặc định khác sau deploy, cập nhật cấu hình quản lý tập trung hoặc environment config theo quy trình phát hành.

Quy trình vận hành nên giới hạn:

- Chỉ cho role vận hành đã xác thực truy cập.
- Chỉ cho phép thay đổi package/logger cần điều tra, tránh bật DEBUG cho root logger.
- Ghi audit log cho người thực hiện, logger name, level cũ/mới và thời điểm.
- Đặt thời gian điều tra và khôi phục level sau khi xong.
- Theo dõi dung lượng log, CPU và latency khi bật DEBUG/TRACE.

Không ghi token, password, session cookie, authorization header hoặc payload chứa dữ liệu cá nhân vào log chỉ vì đang bật mức DEBUG.

## 7. Thiết kế log chẩn đoán an toàn

Log cần giúp trả lời ba câu hỏi: request nào gặp lỗi, lỗi xảy ra ở thành phần nào và thời điểm nào. Log không nên trở thành bản sao của toàn bộ request/response hoặc cấu hình runtime.

Một log event có cấu trúc:

```json
{
  "timestamp": "2026-11-23T10:15:30Z",
  "level": "WARN",
  "service": "order-api",
  "traceId": "9c12f7a4...",
  "event": "payment-provider-timeout",
  "provider": "primary",
  "durationMs": 1500
}
```

Các nguyên tắc:

- Dùng correlation ID hoặc trace ID để nối log giữa các service.
- Ghi event name, service, severity và duration cần thiết.
- Redact hoặc loại bỏ secret, token, cookie, password và dữ liệu cá nhân.
- Tránh log toàn bộ request body, multipart content hoặc object dump.
- Giới hạn log volume và retention; có chính sách rotation.
- Phân quyền truy cập log tập trung và mã hóa khi lưu/truyền.
- Ghi audit riêng cho thao tác thay đổi cấu hình, tải dump và truy cập dữ liệu chẩn đoán.

Nếu dùng MDC trong ứng dụng reactive, không giả định ThreadLocal luôn đi theo request khi pipeline đổi thread. Cấu hình context propagation tương thích với Reactor/Micrometer và kiểm thử trace ID trên nhiều nhánh async.

## 8. Thread dump: điều tra thread, lock và deadlock

Thread dump thể hiện trạng thái thread tại một thời điểm, stack trace, trạng thái chờ và một số thông tin lock. Nó hữu ích khi ứng dụng treo, latency tăng, thread pool cạn hoặc có dấu hiệu deadlock.

Actuator cung cấp endpoint `threaddump` trên các runtime được hỗ trợ:

```text
GET /actuator/threaddump
```

Khi phân tích:

1. Tìm thread ở trạng thái BLOCKED hoặc WAITING kéo dài.
2. Kiểm tra nhiều thread có cùng chờ một lock hoặc resource không.
3. Tìm pool worker bị chiếm hết bởi cùng một loại tác vụ.
4. So sánh nhiều thread dump cách nhau một khoảng thời gian để phân biệt chờ bình thường với treo.
5. Đối chiếu timestamp với request latency, metrics và log cùng trace/correlation ID.

Một thread dump đơn lẻ chỉ là ảnh chụp tức thời; không thể kết luận deadlock hoặc starvation chỉ từ một stack trace. Cần kết hợp nhiều snapshot và metrics của thread pool.

Thread dump cũng có thể tiết lộ tên class nội bộ, URL, SQL, tên file hoặc dữ liệu nằm trong stack. Hạn chế quyền truy cập và xử lý file như dữ liệu chẩn đoán nhạy cảm.

## 9. Heap dump và rủi ro rò rỉ dữ liệu

Heap dump lưu biểu diễn các object trong bộ nhớ tại thời điểm thu thập. Trên JVM, Actuator có endpoint `heapdump` trên runtime hỗ trợ:

```text
GET /actuator/heapdump
```

Heap dump có thể rất lớn và chứa password, access token, refresh token, API key, session, cookie, request/response payload, thông tin cá nhân, dữ liệu nghiệp vụ, object cache và cấu hình đã nạp vào process.

Không expose endpoint này cho public network. Chỉ role chẩn đoán có thẩm quyền mới được phép tạo dump, và cần kiểm soát nơi lưu file, encryption, retention và người được tải xuống.

Việc tạo heap dump có thể tiêu thụ CPU, I/O và dung lượng đĩa; trong một số trường hợp còn ảnh hưởng latency hoặc memory pressure. Không tạo dump liên tục trong production như một loại health check.

### 9.1. Quy trình xử lý heap dump

1. Xác định sự cố cần heap dump, ví dụ nghi ngờ memory leak hoặc retained object tăng.
2. Kiểm tra dung lượng trống và ảnh hưởng tải của instance.
3. Cấp quyền chẩn đoán tạm thời cho người xử lý.
4. Tạo dump trên một instance được chọn, tránh thu thập đồng loạt.
5. Lưu file vào vùng lưu trữ riêng, mã hóa và giới hạn người đọc.
6. Phân tích bằng công cụ phù hợp với định dạng dump.
7. Ghi nhận kết quả mà không đưa object chứa secret vào ticket/log.
8. Xóa file theo retention policy và xác nhận bản sao tạm cũng được xử lý.

Heap dump không phải artifact để đính kèm tự do vào issue tracker hoặc gửi qua chat. Nếu cần chia sẻ, tạo bản đã được xử lý theo quy trình bảo mật dữ liệu của tổ chức.

## 10. Core dump và sự cố native process

Native executable là process hệ điều hành. Khi process crash do lỗi native, segmentation fault hoặc tín hiệu fatal, hệ điều hành/container runtime có thể tạo **core dump**. Core dump khác với heap dump của JVM: nó có thể chứa toàn bộ hoặc một phần memory image của process cùng register và thông tin phục vụ debugger.

Core dump có ích khi process native thoát bất thường mà không có Java exception, có lỗi trong native library/JNI, cần phân tích crash bằng debugger và symbol tương ứng, hoặc stack trace runtime không đủ để xác định vị trí lỗi.

Core dump cũng có thể chứa secret và dữ liệu ứng dụng. Giới hạn quyền ghi, vị trí lưu, retention, encryption và quyền truy cập. Không bật core dump không giới hạn trên node/container có dung lượng nhỏ.

Trong Linux, việc tạo core dump còn phụ thuộc ulimit, kernel core pattern, quyền filesystem và cấu hình container/orchestrator. Hãy phối hợp với nền tảng vận hành để bật cơ chế thu thập có kiểm soát và giữ symbol/build metadata phù hợp cho việc phân tích.

## 11. Khác biệt chẩn đoán giữa JVM và GraalVM Native Image

Không nên giả định công cụ chẩn đoán JVM HotSpot có đầy đủ trong native executable. Native Image có runtime, memory model và khả năng monitoring riêng; tính năng cần được hỗ trợ bởi phiên bản GraalVM đang dùng và đôi khi phải bật ngay lúc build.

| Khả năng | JVM HotSpot | GraalVM Native Image |
| --- | --- | --- |
| Actuator health/metrics | Thường được hỗ trợ qua Spring và Micrometer | Thường dùng được nếu dependency và native metadata tương thích |
| Dynamic log level | Spring Boot logging system quản lý | Phụ thuộc logging implementation và endpoint được đóng gói |
| Thread dump | Có thể dùng Actuator/JVM diagnostic tools | Cần kiểm tra ThreadMXBean/monitoring support của runtime cụ thể |
| Heap dump | Có các công cụ JVM và Actuator integration trên runtime hỗ trợ | Phụ thuộc monitoring feature và cách endpoint tạo dump; không giả định HotSpot MXBean có sẵn |
| JFR/JMX | Tùy JDK/runtime và cấu hình | Native Image có các monitoring feature riêng, phải bật và xác minh theo phiên bản |
| Core dump | Có thể có core dump của JVM process | Có thể thu thập core dump của native process theo OS/container |
| `jcmd`, `jmap`, `jstack` | Hỗ trợ tùy JDK và quyền attach | Không mặc định hoạt động như với HotSpot process |

Một số phiên bản GraalVM Native Image hỗ trợ monitoring feature như thread dump, heap dump hoặc JFR khi được bật trong quá trình tạo image. Ví dụ cấu hình có thể dùng option:

```text
--enable-monitoring=threaddump,heapdump
```

Đây là ví dụ phụ thuộc phiên bản GraalVM và distribution. Trước khi thêm option, kiểm tra danh sách feature mà native-image toolchain đang cài hỗ trợ. Việc bật monitoring feature cũng không tự bảo đảm Actuator endpoint tương ứng hoạt động: endpoint implementation có thể phụ thuộc JMX/MXBean hoặc API không được native runtime cung cấp giống HotSpot.

Với mỗi tính năng dump/monitoring, cần build thử và gọi endpoint trên chính native executable. Nếu runtime không hỗ trợ, dùng cơ chế chẩn đoán phù hợp như process metrics, OS core dump, structured logs hoặc tracing thay vì dựa vào một endpoint chưa được xác minh.

## 12. Thu thập metrics và log khi dump không khả dụng

Trong production, nhiều sự cố có thể được khoanh vùng mà không cần lấy heap dump. Hãy thu thập các tín hiệu ít xâm lấn trước:

- CPU usage, process RSS và container memory usage.
- GC hoặc memory metrics mà runtime cung cấp.
- Request rate, error rate, latency percentile.
- Thread count, executor queue và connection pool usage.
- HTTP client timeout/retry và database pool metrics.
- Log có correlation ID và trace ID.
- Restart count, exit code và container termination reason.

Native Image có runtime và memory manager riêng; loại GC cùng metric khả dụng và ngữ nghĩa của chúng phụ thuộc GraalVM version, cấu hình image và nền tảng. Không mặc định metric heap trên native có cùng ý nghĩa hoặc cùng tập số liệu như HotSpot JVM. Phân biệt heap usage với RSS/container memory: RSS còn bao gồm code, native allocation, stack và các vùng memory khác.

Nếu nghi ngờ leak, so sánh xu hướng qua thời gian và tải tương đương. Một snapshot RSS tăng chưa đủ chứng minh object leak. Kết hợp memory metrics, allocation behavior, request pattern và giới hạn cgroup để tìm nguyên nhân.

## 13. Kiểm thử bảo mật endpoint quản trị

Không dừng ở việc kiểm tra cấu hình file. Cần test HTTP behavior trong môi trường gần production.

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| Caller không xác thực gọi health | Chỉ được phép phần public đã định nghĩa hoặc nhận 401 |
| Caller thường gọi metrics/loggers | Nhận 401/403 theo policy |
| Role MONITOR đọc metrics | Thành công nếu endpoint được expose |
| Role MONITOR thay đổi logger level | Bị từ chối nếu chỉ OPS được quyền |
| Role OPS thay đổi logger level | Thành công, có audit và có thể khôi phục |
| Caller không có quyền gọi heapdump/threaddump | Nhận 401/403 |
| Port quản trị bị truy cập từ public network | Bị firewall/NetworkPolicy chặn |
| Health detail được gọi bởi user không có role | Không trả component details |
| Endpoint không nằm trong exposure allowlist | Không được công bố qua web |

Ví dụ kiểm thử MVC với MockMvc:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ActuatorSecurityTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void metricsRequiresAuthentication() throws Exception {
        mockMvc.perform(get("/actuator/metrics"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(roles = "OPS")
    void opsCanReadMetrics() throws Exception {
        mockMvc.perform(get("/actuator/metrics"))
            .andExpect(status().isOk());
    }
}
```

Ví dụ giả định endpoint metrics đã được expose và ứng dụng dùng authentication entry point trả response 401 cho anonymous. Nếu policy thực tế trả 403 hoặc dùng OAuth2/mTLS, điều chỉnh assertion theo authentication mechanism của ứng dụng.

Ngoài MockMvc, hãy chạy test qua management port riêng và từ đúng network zone. MockMvc không kiểm tra firewall, ingress, TLS termination hoặc NetworkPolicy.

## 14. Kiểm thử trên native executable

Một bộ kiểm thử native nên xác minh:

1. Chỉ endpoint nằm trong allowlist được expose.
2. Anonymous caller không truy cập được endpoint cần authentication.
3. Role đúng đọc được endpoint tương ứng.
4. Role không đủ quyền không thể thay đổi log level hoặc tải dump.
5. Health detail chỉ hiển thị với caller có quyền.
6. Loggers endpoint thay đổi level đúng và có thể khôi phục.
7. Threaddump hoạt động nếu runtime hỗ trợ.
8. Heapdump hoạt động nếu runtime và endpoint implementation hỗ trợ; file dump có định dạng có thể phân tích.
9. Core dump được thu thập theo chính sách của OS/container khi thử nghiệm crash có kiểm soát.
10. Native executable không ghi secret hoặc payload nhạy cảm vào log chẩn đoán.

Khi build native, kiểm tra các option monitoring đã được chấp nhận và có hiệu lực. Không suy ra hỗ trợ từ việc endpoint được liệt kê trong Actuator discovery document. Hãy gọi endpoint thật, kiểm tra content type, file output, kích thước, quyền truy cập và log lỗi.

Với production, nên thử quy trình dump trên staging hoặc một instance canary trước. Đo thời gian tạo dump, dung lượng file, CPU, RSS và ảnh hưởng tới request latency. Chuẩn bị đủ disk space và cách thu hồi file sau khi phân tích.

## 15. Quy trình xử lý sự cố và quản trị dữ liệu dump

Một runbook có thể tổ chức theo trình tự:

1. **Phát hiện:** alert từ latency, error rate, memory, CPU hoặc restart count.
2. **Khoanh vùng:** xác định service, instance, phiên bản native image, thời điểm và trace ID.
3. **Thu thập ít xâm lấn:** log, metrics, health và process/container status.
4. **Chẩn đoán sâu:** thread dump hoặc heap dump nếu runtime hỗ trợ và cần thiết.
5. **Crash analysis:** thu core dump khi process native gặp lỗi fatal.
6. **Bảo vệ dữ liệu:** mã hóa, giới hạn quyền, ghi audit và đặt retention.
7. **Phân tích:** dùng công cụ tương thích định dạng dump và build symbols.
8. **Khắc phục:** sửa lỗi, build lại native image và kiểm thử trên staging.
9. **Đóng sự cố:** khôi phục log level, tắt exposure tạm thời và xóa dump hết hạn.

Mỗi dump nên có metadata tối thiểu: service, instance ID không nhạy cảm, image/build version, timestamp, loại dump, người yêu cầu, ticket/incident reference và thời điểm hết hạn. Không ghi secret hoặc nội dung object vào metadata.

## 16. Bài thực hành: bảo vệ Actuator và diễn tập chẩn đoán

**Bối cảnh:** Một Spring Boot service chạy native image trong container. Đội vận hành cần health và metrics cho monitoring; chỉ nhóm OPS được phép xem loggers và nhóm DIAGNOSTICS mới được thu thập dump.

**Các bước:**

1. Thêm Spring Boot Actuator và chỉ expose health, info, metrics cùng prometheus nếu có registry.
2. Cấu hình health details chỉ hiển thị cho role được phép.
3. Tách management port khỏi port API nếu kiến trúc yêu cầu.
4. Cấu hình Spring Security matcher cho Actuator và phân quyền role.
5. Đặt management port sau firewall/NetworkPolicy; chỉ cho scraper và admin network truy cập.
6. Thử GET loggers và POST thay đổi level bằng role OPS; ghi audit thao tác và khôi phục level.
7. Tạo thread dump trên JVM test để luyện phân tích thread state và lock.
8. Kiểm tra khả năng heapdump/threaddump trên native executable của GraalVM version đang dùng; nếu không hỗ trợ, ghi rõ cơ chế thay thế.
9. Thực hiện crash test có kiểm soát trong staging để xác minh core dump và quyền lưu file.
10. Kiểm tra dump không được ghi vào public artifact store; xác nhận encryption, retention và deletion.
11. Chạy test anonymous, role thiếu quyền và role hợp lệ trên native management port.
12. Tắt endpoint chẩn đoán tạm thời và xác nhận exposure trở về allowlist ban đầu.

**Tiêu chí đạt:**

- Không expose toàn bộ Actuator endpoint trong production.
- Management endpoint có xác thực, phân quyền và giới hạn mạng.
- Health details không hiển thị cho caller không được phép.
- Thao tác thay đổi log level có audit và có quy trình khôi phục.
- Thread/heap/core dump được xem là dữ liệu nhạy cảm và có kiểm soát lưu trữ.
- Đã xác minh tính năng dump/monitoring trên đúng GraalVM Native Image runtime.
- Native integration test xác nhận endpoint và policy hoạt động như mong đợi.

## 17. Tổng kết

Actuator cung cấp dữ liệu quan sát và endpoint quản trị, nhưng exposure phải được giới hạn theo nhu cầu. Kết hợp allowlist endpoint, management port riêng, network policy, TLS, authentication, authorization và audit. Endpoint loggers cần được kiểm soát vì có thể thay đổi log level; log phải có correlation ID nhưng không được chứa secret hoặc payload nhạy cảm.

Thread dump, heap dump và core dump là dữ liệu chẩn đoán có thể tiết lộ thông tin trong process. Chỉ thu thập khi cần, giới hạn người truy cập, mã hóa và đặt retention. Với GraalVM Native Image, xác minh từng monitoring feature trên phiên bản runtime thực tế; không mặc định công cụ HotSpot hoặc Actuator dump endpoint hoạt động giống JVM. Kiểm thử cả quyền truy cập lẫn hành vi dump trên native executable để runbook vận hành phản ánh đúng khả năng của artifact được triển khai.

