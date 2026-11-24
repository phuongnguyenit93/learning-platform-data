# Metric endpoint và security

Trong chương **Actuator metrics endpoint** của mô-đun **SPRING_BOOT_OBSERVABILITY**, việc mở endpoint xem metrics không chỉ là vấn đề cấu hình một URL. Người vận hành cần biết **endpoint nào phục vụ chẩn đoán**, **endpoint nào phục vụ hệ thống scrape**, **ai được quyền truy cập** và **những thông tin nào có thể bị lộ** nếu cấu hình sai.

Mô-đun này xây dựng observability cho Spring Boot bằng **Micrometer Observation, metrics, logs và distributed tracing**; đồng thời học propagation ngữ cảnh, tag/cardinality, exporter và sampling để điều tra lỗi, độ trễ và hành vi ứng dụng trong môi trường thực. Endpoint metrics là cửa sổ đọc dữ liệu từ nhánh metrics của hệ thống đó. Nó không tự động xuất logs hoặc tracing spans, cũng không thay thế các yêu cầu bảo mật của ứng dụng.

**Nguyên tắc cốt lõi:** bật endpoint chỉ khi có nhu cầu, giới hạn người dùng và mạng được truy cập, bảo vệ đường truyền, đồng thời kiểm tra rằng việc bảo vệ endpoint **không làm hỏng pipeline thu thập metrics**.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt `/actuator/metrics`, `/actuator/metrics/{name}` và `/actuator/prometheus`.
2. Giải thích khác nhau giữa **endpoint tồn tại**, **endpoint được expose qua HTTP** và **endpoint cho phép một người dùng truy cập**.
3. Cấu hình Spring Boot Actuator và Micrometer Prometheus registry cho môi trường thử nghiệm.
4. Dùng Spring Security để chỉ cho phép người có quyền đọc metrics; nhận biết hành vi khi có hoặc chưa có `SecurityFilterChain` tùy biến.
5. Xây dựng nguyên tắc truy cập riêng cho **nhân sự vận hành** và **dịch vụ Prometheus scraper**.
6. Kiểm tra các phản hồi HTTP 200, 401, 403 và 404 để chẩn đoán lỗi cấu hình.
7. Đánh giá nguy cơ lộ metadata, cardinality, chi phí scrape và các rủi ro khi đưa endpoint metrics ra môi trường production.
8. Kết hợp thông tin metrics với logs, tracing và sampling trong quá trình điều tra sự cố.

## 2. Hai endpoint thường bị nhầm

Spring Boot Actuator có nhiều endpoint. Khi làm việc với metrics, hai loại quan trọng nhất là:

| Endpoint | Mục đích | Định dạng phổ biến | Người sử dụng |
| --- | --- | --- | --- |
| `GET /actuator/metrics` | Liệt kê tên meter mà ứng dụng đang công bố qua Actuator. | JSON | Người phát triển/vận hành, công cụ kiểm tra. |
| `GET /actuator/metrics/{metric.name}` | Xem measurements và các tag values có sẵn của một meter; có thể lọc theo `tag`. | JSON | Người điều tra một metric cụ thể. |
| `GET /actuator/prometheus` | Xuất dữ liệu theo định dạng để Prometheus scrape. | Prometheus/OpenMetrics text, tùy nội dung/đàm phán định dạng. | Prometheus hoặc scraper được ủy quyền. |

Ví dụ:

~~~bash
curl -s http://localhost:8080/actuator/metrics
curl -s http://localhost:8080/actuator/metrics/http.server.requests
curl -s http://localhost:8080/actuator/prometheus
~~~

`/actuator/metrics` là API **chẩn đoán** của Actuator, không phải endpoint mà Prometheus thông thường dùng để scrape. Prometheus dùng định dạng tại `/actuator/prometheus` khi Prometheus registry được bật.

Với một HTTP server timer, tên trong Actuator có thể là `http.server.requests` nhưng exporter cho Prometheus có thể đặt các series như `http_server_requests_seconds_count` và `http_server_requests_seconds_sum`. Điều này không có nghĩa có hai metrics độc lập: registry áp dụng quy ước đặt tên, hậu tố và đơn vị phù hợp với backend.

### Dữ liệu trả về của endpoint metrics

Ví dụ một phản hồi **minh họa** khi gọi `GET /actuator/metrics/http.server.requests`:

~~~json
{
  "name": "http.server.requests",
  "description": null,
  "baseUnit": "seconds",
  "measurements": [
    {"statistic": "COUNT", "value": 120.0},
    {"statistic": "TOTAL_TIME", "value": 14.2},
    {"statistic": "MAX", "value": 0.83}
  ],
  "availableTags": [
    {"tag": "method", "values": ["GET", "POST"]},
    {"tag": "status", "values": ["200", "500"]},
    {"tag": "uri", "values": ["/orders/{id}", "/checkout"]}
  ]
}
~~~

Đây **không phải output thật** từ dự án. Các fields và values phụ thuộc loại meter, registry, traffic và phiên bản Spring Boot. Một số meter có base unit khác hoặc không có đủ những measurements ví dụ trên.

Ý nghĩa chính:

- `name` là tên meter trong mô hình Micrometer.
- `measurements` chứa các số đo tổng hợp; ví dụ `COUNT`, `TOTAL_TIME` của timer.
- `availableTags` cho biết những chiều dùng để lọc; đây cũng là nơi có thể nhận ra tag cardinality không mong muốn.
- `MAX` của timer có thể là số đo theo cửa sổ thời gian; không nên coi nó luôn là mức lớn nhất từ khi process khởi động.

**Không lấy phép cộng hoặc chia tùy tiện các measurements của Actuator rồi coi đó là P95 toàn hệ thống.** Các phân vị và histogram cần dữ liệu phân bố phù hợp từ exporter/backend.

## 3. Ba tầng điều kiện: enablement, exposure và authorization

Một endpoint có thể **được triển khai trong ứng dụng** nhưng không truy cập được qua HTTP. Phải kiểm tra riêng ba câu hỏi:

1. **Có endpoint/registry tương ứng không?** Ví dụ `/actuator/prometheus` cần Prometheus registry và auto-configuration hỗ trợ.
2. **Endpoint có được expose qua HTTP không?** `management.endpoints.web.exposure.include` xác định tập endpoint được công bố qua HTTP.
3. **Caller có được phép đọc không?** Spring Security, reverse proxy, service mesh, ingress hoặc network policy có thể chặn request.

~~~mermaid
flowchart TD
    A["Client: GET /actuator/metrics"] --> B{"Endpoint được cấu hình và khả dụng?"}
    B -->|"Không"| N["Không có endpoint phù hợp"]
    B -->|"Có"| C{"Được expose qua HTTP?"}
    C -->|"Không"| N
    C -->|"Có"| D{"Đi qua network/ingress?"}
    D -->|"Không"| T["Timeout / connection refused / proxy error"]
    D -->|"Có"| E{"Được xác thực và có quyền?"}
    E -->|"Không"| U["401 hoặc 403 tùy trường hợp"]
    E -->|"Có"| F["200 + dữ liệu nếu endpoint hoạt động"]
~~~

**404** thường gợi ý endpoint không tồn tại hoặc không được expose ở URL đó; **401** cho biết chưa được xác thực theo chính sách bảo mật; **403** thường cho biết danh tính đã được xác thực nhưng không được phép. Đây là quy tắc chẩn đoán khởi đầu, không phải hợp đồng tuyệt đối: proxy và security filters có thể trả mã khác hoặc cố tình che giấu sự tồn tại của endpoint.

Một endpoint mở thành công trong local không bảo đảm nó sẽ truy cập được sau khi triển khai qua ingress, management port hay service mesh.

## 4. Cấu hình tối thiểu cho Spring Boot và Micrometer

Ví dụ ứng dụng **Spring Boot 3.x** dùng Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'io.micrometer:micrometer-registry-prometheus'
}
~~~

`spring-boot-starter-actuator` cung cấp hạ tầng Actuator và metrics tương ứng. `micrometer-registry-prometheus` cho phép Spring Boot cấu hình Prometheus registry khi các điều kiện được đáp ứng. Quản lý phiên bản Micrometer theo Spring Boot BOM thay vì tùy tiện phối những phiên bản không tương thích.

Ví dụ cấu hình **chỉ dùng ở môi trường thử nghiệm có kiểm soát**:

~~~yaml
spring:
  application:
    name: order-api

management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
  metrics:
    tags:
      application: order-api
      environment: local
~~~

Kết quả mong đợi khi ứng dụng có metrics và đang chạy trên cổng 8080:

~~~bash
curl -i http://localhost:8080/actuator/health
curl -i http://localhost:8080/actuator/metrics
curl -i http://localhost:8080/actuator/prometheus
~~~

Một số điểm cần tránh nhầm:

- Với cấu hình mặc định thông dụng của Spring Boot, **health** là endpoint chủ yếu được expose qua web; `metrics` hoặc `prometheus` thường cần khai báo exposure.
- Thêm exposure **không tự quyết định** ai được phép truy cập: đó là việc của security và hạ tầng mạng.
- Nếu không có Prometheus registry hoặc nó bị vô hiệu hóa, `/actuator/prometheus` có thể không khả dụng dù có tên trong `include`.
- Nếu đổi `management.endpoints.web.base-path`, management port hoặc context path, URL sẽ không còn đúng với ví dụ.
- Bật endpoint metrics không tự động tạo dữ liệu của một custom meter chưa bao giờ được ghi.

Không dùng `include: "*"` như một cách sửa lỗi 404 ở production. Nó có thể vô tình expose nhiều endpoint quản trị không phù hợp với người dùng ngoài.

## 5. Spring Security bảo vệ Actuator như thế nào?

Khi **Spring Security** có trên classpath và bạn chưa định nghĩa `SecurityFilterChain` riêng, Spring Boot thường cung cấp quy tắc bảo mật mặc định cho Actuator: endpoint health được đối xử khác các endpoint quản trị còn lại. Hành vi cụ thể còn phụ thuộc phiên bản, dependency và cấu hình.

**Điểm đặc biệt quan trọng:** khi ứng dụng đã định nghĩa một `SecurityFilterChain` tùy biến, Spring Boot thường **lùi lại khỏi auto-configuration bảo mật Actuator**. Khi đó, chính bạn phải viết quy tắc truy cập cho Actuator. Không thể giả định “Actuator sẽ luôn tự bảo mật” nếu đã có security configuration của ứng dụng.

Thêm Spring Security:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
~~~

### Một security chain có quy tắc minh họa

Ví dụ Spring Security 6 / Spring Boot 3.x, trong đó:

- `health` cho phép truy cập mà không cần xác thực, **nếu chính sách tổ chức cho phép**.
- `metrics` chỉ dành cho người có role `OPS`.
- `prometheus` chỉ dành cho danh tính scraper có role `SCRAPER`.
- Các Actuator endpoint còn lại yêu cầu `OPS`.
- API bình thường vẫn cần người dùng đã xác thực.

~~~java
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain applicationSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(EndpointRequest.to("health")).permitAll()
                .requestMatchers(EndpointRequest.to("metrics")).hasRole("OPS")
                .requestMatchers(EndpointRequest.to("prometheus")).hasRole("SCRAPER")
                .requestMatchers(EndpointRequest.toAnyEndpoint()).hasRole("OPS")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
~~~

**Ví dụ chỉ tập trung vào authorization**, không định nghĩa người dùng, mật khẩu hay cách cấp role. Để chạy được, ứng dụng phải có identity provider hoặc cơ chế xác thực cấp quyền `ROLE_OPS` và `ROLE_SCRAPER` theo Spring Security. `httpBasic` được chọn để minh họa dễ thử trong mạng nội bộ; trong sản xuất, bạn có thể dùng OAuth2/OIDC, mTLS hoặc cơ chế xác thực service account thích hợp. **Không gửi Basic credentials qua HTTP không mã hóa**.

Nếu ứng dụng đang dùng OAuth2 resource server, nhiều `SecurityFilterChain`, CSRF/HTTP session hoặc API authorization phức tạp, cần tích hợp quy tắc Actuator vào kiến trúc hiện có thay vì sao chép một chain toàn cục và vô tình thay đổi hành vi API. `EndpointRequest` giúp match endpoint theo cơ chế Actuator thay vì dựa hoàn toàn vào chuỗi URL cố định.

### Tách role đọc metrics và role scraper

Việc có hai role khác nhau là quyết định nguyên tắc **least privilege**:

| Nhóm truy cập | Nhu cầu | Quyền khuyến nghị |
| --- | --- | --- |
| Developer/Ops đang điều tra sự cố | Liệt kê, lọc và kiểm tra từng meter JSON. | Chỉ các endpoint cần thiết như `metrics`. |
| Prometheus service account | Đọc dữ liệu theo lịch định kỳ. | Chỉ `prometheus` qua network được phép. |
| Health checker | Kiểm tra trạng thái đơn giản. | Chỉ thông tin health phù hợp mức công khai. |
| Người dùng API bình thường | Sử dụng nghiệp vụ. | Không cần truy cập metrics endpoints. |

Không nhất thiết phải sử dụng đúng tên role trong ví dụ; điều quan trọng là ánh xạ chúng tới quyền thực sự từ hệ thống identity của bạn, và kiểm thử các trường hợp truy cập chéo.

## 6. Bảo vệ bằng network boundary và management port

**Authorization ở lớp ứng dụng là cần thiết nhưng không đủ.** Endpoint metrics có thể bị truy cập qua nhiều đường: trực tiếp tới pod, qua service nội bộ, qua ingress công khai hoặc qua một sidecar/proxy. Cần xây dựng ranh giới mạng rõ ràng.

Một kiến trúc thường dùng:

~~~mermaid
flowchart LR
    Client["Người dùng Internet"] --> Public["Public ingress"]
    Public --> API["Spring Boot API port"]
    Collector["Prometheus trong mạng nội bộ"] --> Private["Private service / management ingress"]
    Private --> Mgmt["Actuator management port"]
    OPS["Ops qua VPN / bastion"] --> Private
    Mgmt --> Registry["MeterRegistry / Actuator"]
    API --> Registry
~~~

Có thể chạy Actuator trên một cổng quản trị riêng:

~~~yaml
management:
  server:
    port: 9091
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
~~~

Khi cấu hình như vậy và dùng các mặc định phù hợp, URL kiểm tra có thể là `http://localhost:9091/actuator/metrics` thay vì cổng ứng dụng 8080.

**Cổng riêng không đồng nghĩa cổng an toàn.** Nếu port 9091 vẫn bị expose qua một public load balancer hoặc pod network không có policy, rủi ro vẫn tồn tại. Cần giới hạn ingress/sources, quyền truy cập và TLS. Việc bind `127.0.0.1` có thể phù hợp với scraper cục bộ/sidecar, nhưng cũng có thể khiến Prometheus chạy từ xa không truy cập được. Hãy thiết kế cùng topology triển khai thực tế.

Các biện pháp thường phối hợp:

- Đưa endpoint metrics lên **mạng quản trị nội bộ**, tránh route qua public ingress không cần thiết.
- Dùng **TLS** cho kết nối đọc metrics khi đi qua mạng; cân nhắc mTLS cho service-to-service.
- Áp dụng network policy, firewall, security group, service mesh authorization hoặc proxy ACL.
- Cấp identity/role tối thiểu cho scraper, xoay vòng credentials, lưu bí mật trong secret manager.
- Giới hạn những endpoint được expose; không biến vấn đề scrape thành lý do mở mọi endpoint quản trị.
- Giám sát HTTP status, scrape duration, số lần authentication failures và request volume tới management endpoint.

## 7. Prometheus scrape endpoint có cần xác thực không?

**Có, theo chính sách truy cập của hệ thống.** Một thiết kế phổ biến là endpoint `/actuator/prometheus` chỉ mở cho Prometheus scraper qua mạng riêng; nếu có xác thực, scraper phải có thông tin đăng nhập phù hợp. Việc cho scraper truy cập không có nghĩa người dùng Internet được phép đọc endpoint.

Một ví dụ cấu hình Prometheus cho management endpoint phía sau proxy TLS đã được bảo vệ:

~~~yaml
scrape_configs:
  - job_name: "order-api"
    scheme: https
    metrics_path: /actuator/prometheus
    scrape_interval: 15s
    static_configs:
      - targets:
          - order-api-management.internal:9443
    basic_auth:
      username: scraper
      password_file: /etc/prometheus/secrets/order-api-password
~~~

Đây là **topology minh họa**: hostname, port, TLS termination và file secret phải được chuẩn bị trước. Prometheus sẽ không tự tạo chúng. Mật khẩu không được hard-code trong mã nguồn hoặc công khai trong cấu hình; file secret cần được cấp quyền phù hợp. Với môi trường hỗ trợ OAuth2, bearer token, mTLS hoặc proxy-based authentication, chọn cơ chế đáp ứng yêu cầu tổ chức.

Một lỗi hay gặp là bảo vệ endpoint bằng Spring Security nhưng quên cập nhật cấu hình scrape. Kết quả: kiểm tra thủ công với credentials hợp lệ thì 200, nhưng Prometheus target lại trả **401** hoặc **403**. Cần kiểm tra trực tiếp **target status** và HTTP response từ đúng địa chỉ mà Prometheus đang truy cập.

### Scraper không dùng `/actuator/metrics` làm endpoint mặc định

`/actuator/metrics` trả JSON phục vụ chẩn đoán. Prometheus cần định dạng metrics mà Prometheus registry xuất tại `/actuator/prometheus`. Nếu trỏ `metrics_path` sai, kết quả có thể là parse error, response không đúng content type hoặc không có series mong muốn dù HTTP status vẫn là 200.

## 8. Truy vấn một metric và lọc bằng tag

Sau khi có quyền phù hợp, liệt kê names:

~~~bash
curl -s -u ops http://localhost:9091/actuator/metrics
~~~

`curl -u ops` thường yêu cầu nhập mật khẩu tương tác nếu chưa được cung cấp; ví dụ không đặt mật khẩu trong shell history. Chỉ thử qua localhost hoặc HTTPS trong môi trường được bảo vệ.

Ví dụ truy vấn một meter cụ thể:

~~~bash
curl -s -u ops http://localhost:9091/actuator/metrics/http.server.requests
~~~

Bạn có thể lọc theo một hoặc nhiều cặp tag:

~~~bash
curl -s -u ops --get \
  --data-urlencode "tag=method:GET" \
  --data-urlencode "tag=status:200" \
  http://localhost:9091/actuator/metrics/http.server.requests
~~~

Tham số `tag=key:value` giúp giới hạn phép tổng hợp trong Actuator response theo tag được cung cấp. Nó **không phải PromQL**, không phải ngôn ngữ truy vấn tùy ý, cũng không tìm tất cả các traces của request.

Nếu service có route như `/orders/{id}`, nên chuẩn hóa route thành template trong HTTP metrics thay vì sử dụng URL chứa order ID thực tế. Có thể dùng bộ lọc `uri` theo giá trị từ `availableTags`. Điều này giúp kiểm soát cardinality và tránh làm lộ thông tin trong metadata.

**Không để request ID, user ID, email, access token hoặc đường dẫn thô chứa dữ liệu cá nhân trở thành metric tag**. Bảo vệ endpoint bằng xác thực không sửa được việc một backend đang lưu lượng series khổng lồ do high-cardinality tags.

## 9. Vì sao endpoint metrics cũng là tài sản cần bảo vệ?

Metrics thường không có request body, nhưng có thể tiết lộ:

- Tên service, route nội bộ, dependency, pool và cấu trúc runtime.
- Tần suất giao dịch, tỉ lệ lỗi, tình trạng bão hòa hoặc thời điểm hệ thống hoạt động mạnh.
- Nhãn phân vùng, môi trường, instance hoặc các tên thành phần có ý nghĩa nội bộ.
- Nếu instrumentation bị thiết kế sai: request IDs, tên khách hàng, URL chi tiết và các giá trị nhạy cảm trong tags.

Vì vậy, bảo mật endpoint không chỉ để ngăn người ngoài thấy dashboard mà còn để hạn chế **rò rỉ metadata**, **điều tra kiến trúc trái phép** và **truy vấn quá mức**. Scrape payload có thể lớn khi ứng dụng có nhiều meter/series; một endpoint bị truy cập liên tục bởi nguồn không tin cậy có thể gây tải lên process và đường mạng.

Các kiểm soát chính gồm xác thực và phân quyền, TLS, giới hạn network, theo dõi tốc độ request, giới hạn cardinality từ nguồn phát và chính sách retention ở backend. Một số kiểm soát như rate limit nên triển khai ở proxy/ingress hoặc hạ tầng phù hợp để không làm ảnh hưởng việc scrape hợp lệ.

Không sử dụng thông tin từ endpoint metrics như chứng cứ phân quyền hay xác thực người dùng. Đây là telemetry, không phải nguồn danh tính tin cậy.

## 10. Endpoint exposure không thay thế filter ở tầng metric

Một hiểu nhầm phổ biến: “Ẩn `/actuator/metrics` thì ứng dụng ngừng ghi metrics”. Thực tế hai vấn đề khác nhau:

- **Exposure** quyết định endpoint có thể được truy cập qua HTTP hay không.
- **MeterRegistry** vẫn có thể ghi metrics vào registry implementation ngay cả khi endpoint không expose.
- **MeterFilter** có thể tác động tới việc đăng ký meters, chỉnh tên/tags hoặc từ chối một nhóm meter.
- **ObservationPredicate** có thể loại một observation ở tầng Micrometer Observation; đó không phải chính sách HTTP authorization.
- **Tracing sampling** quyết định một phần traces được ghi/giữ, không phải công cụ kiểm soát quyền truy cập endpoint metrics.

Ví dụ, nếu application ghi `checkout.completed` vào `MeterRegistry` nhưng `/actuator/metrics` không được expose, scraper dùng một exporter khác vẫn có thể nhận metrics tùy hệ thống. Ngược lại, nếu endpoint metrics expose công khai nhưng có `MeterFilter` loại một meter, việc công khai endpoint không khiến meter bị loại xuất hiện lại.

**Bảo mật endpoint là bài toán access control; cardinality và sampling là bài toán chất lượng/chi phí telemetry.** Cần xử lý cả hai nhưng không đánh đồng.

## 11. Liên hệ metrics với logs và distributed tracing khi điều tra

Giả sử ứng dụng `order-api` gặp sự cố: từ 10:20 đến 10:30, P95 của `GET /orders/{id}` tăng từ 180 ms lên 1,2 giây.

Một quy trình hợp lý:

1. **Metrics:** xem count, error rate và duration theo route, method, status và instance từ Prometheus. Nếu nghi một process bị ảnh hưởng, kiểm tra JVM, CPU, connection pool cùng instance.
2. **Actuator diagnostic endpoint:** nếu cần xác minh nguồn phát metrics, đọc `/actuator/metrics/http.server.requests` bằng quyền OPS; đối chiếu `availableTags` và measurements.
3. **Logs:** tìm timeout, retry và exception trong cùng khoảng thời gian; tra `traceId` nếu logging/MDC integration đã được cấu hình.
4. **Distributed tracing:** mở một vài trace chậm và bình thường để xem dependency nào gây trễ, span nào nằm trên critical path.
5. **Propagated context:** nếu trace đứt ở HTTP client hoặc messaging, kiểm tra `traceparent`, instrumentation và async context thay vì cho rằng endpoint metrics sai.
6. **Sampling/exporter:** nếu metrics cho thấy nhiều request lỗi nhưng không tìm được trace cụ thể, cân nhắc trace bị sample out hoặc lỗi collector/exporter; metrics và tracing có pipeline khác nhau.
7. **Xác minh kết quả:** sau khắc phục, kiểm tra lại tỉ lệ lỗi và độ trễ trên tập request đủ lớn, rồi đối chiếu logs/traces mới khi cần.

Một Actuator metrics endpoint trả 200 chỉ chứng minh **đường đọc metrics của endpoint hoạt động tại thời điểm đó**. Nó không chứng minh Prometheus đã scrape thành công, không chứng minh trace exporter hoạt động và cũng không chứng minh dữ liệu trên dashboard đã cập nhật.

## 12. Bảng chẩn đoán nhanh theo HTTP status

| Triệu chứng | Giả thuyết thường gặp | Hành động kiểm tra |
| --- | --- | --- |
| **404** ở `/actuator/metrics` | Endpoint chưa expose, đã disable hoặc management base path/port khác. | Kiểm tra exposure và URL management thật. |
| **404** ở `/actuator/prometheus` | Thiếu Prometheus registry hoặc endpoint chưa expose/bật. | Kiểm tra dependency `micrometer-registry-prometheus` và cấu hình endpoint. |
| **401 Unauthorized** | Chưa xác thực hoặc credentials của scraper sai. | Kiểm tra security chain, authentication provider và danh tính scraper. |
| **403 Forbidden** | Caller thiếu quyền; một số trường hợp còn liên quan chính sách khác của security/proxy. | Kiểm tra roles/authorities và quy tắc access control. |
| **200** nhưng JSON chỉ có vài names | Chưa có traffic, meter chưa được ghi, binder thiếu hoặc meter filter loại dữ liệu. | Chạy nhánh nghiệp vụ và kiểm tra registry/metric names. |
| **200** ở `/metrics`, target Prometheus vẫn down | Scraper đi đường mạng, URL, credentials hoặc TLS khác. | Kiểm tra từ network của scraper và trạng thái target. |
| **200** ở `/prometheus` nhưng không thấy metric mong muốn | Meter chưa được tạo, tên chuyển đổi, tags sai hoặc dữ liệu bị filter. | Tìm tên meter trong Actuator và so sánh raw exporter response. |
| Timeout/connection refused | Network policy, firewall, management port, ingress hoặc process chưa sẵn sàng. | Kiểm tra reachability theo đường scraper thực tế. |
| Sau triển khai endpoint bỗng mở công khai | Security chain mới bỏ quên Actuator hoặc public ingress route nhầm management port. | Rà soát authorization, ingress/network policy và test từ mạng không tin cậy. |

Khi xử lý 404, tránh thay đổi ngay thành `include: "*"`. Đó là cách sửa tiện lợi nhưng có thể mở rộng bề mặt tấn công. Hãy expose **chính xác** endpoint đang cần và giữ chính sách truy cập tối thiểu.

## 13. Kiểm thử bảo mật trước khi triển khai

Một số kiểm tra cần có trong pipeline hoặc kiểm tra triển khai:

### 13.1 Kiểm tra đường public không được phép đọc metrics

Từ nơi có đường đi giống người dùng Internet, gửi một request không có credentials tới URL management nếu route đó có thể truy cập:

~~~bash
curl -i https://public.example.invalid/actuator/metrics
curl -i https://public.example.invalid/actuator/prometheus
~~~

Tên miền `example.invalid` chỉ là placeholder, không phải host cần tồn tại. Kết quả mong muốn tùy kiến trúc: có thể là không có route, timeout từ network boundary, 401 hoặc 403. **Không coi 200 là thành công của test âm tính này.**

### 13.2 Kiểm tra Ops và scraper có quyền phù hợp

Trong môi trường được bảo vệ:

~~~bash
curl -i -u ops https://management.example.invalid/actuator/metrics
curl -i -u scraper https://management.example.invalid/actuator/prometheus
~~~

Ví dụ không chèn mật khẩu vào dòng lệnh; `curl` sẽ hỏi password khi dùng `-u <username>` theo cách tương tác thông thường. Nếu hệ thống sử dụng mTLS, bearer token hoặc identity proxy, cách kiểm tra phải tương ứng với cơ chế xác thực thực tế.

Đồng thời kiểm tra **truy cập chéo bị từ chối**: scraper không nên tự đọc mọi Actuator endpoint, còn tài khoản API thông thường không nên đọc metrics.

### 13.3 Kiểm tra nội dung bị rò rỉ

Kiểm tra danh sách tags và sample metrics:

- Có request ID, user ID, email, token hoặc URL thô làm tags không?
- Các route đã chuẩn hóa theo template chưa?
- Có tên dependency, server, pool hoặc business data không cần công bố không?
- Thông tin nào chỉ nên nằm trong logs/traces có kiểm soát?

Nếu có high-cardinality/sensitive tags, sửa instrumentation hoặc dùng quy tắc lọc phù hợp. **Authorization không thay thế việc thiết kế metadata an toàn.**

### 13.4 Kiểm tra sự sống của scrape

Sau khi đặt access control, xác nhận target Prometheus vẫn **UP** và scrape duration không bất thường. Kiểm tra HTTP 200, content type và dữ liệu metric mong muốn từ đúng network của scraper. Việc một operator có thể mở endpoint thủ công trên laptop không đủ để xác nhận scraper có kết nối và quyền đọc.

## 14. Checklist vận hành

- [ ] Chỉ expose `health`, `metrics`, `prometheus` hoặc các endpoint thật sự cần.
- [ ] Đã phân biệt rõ API JSON của `/actuator/metrics` với exporter `/actuator/prometheus`.
- [ ] Có Prometheus registry khi thực sự muốn scrape định dạng Prometheus.
- [ ] Có kiểm soát authentication/authorization khi bật Spring Security và khi cấu hình `SecurityFilterChain` tùy biến.
- [ ] Ops và service account scraper chỉ có những quyền cần thiết.
- [ ] Management endpoint nằm trong network boundary phù hợp; có TLS/mTLS nếu chính sách yêu cầu.
- [ ] Management port, base path và ingress không vô tình expose ra Internet.
- [ ] Đã kiểm thử từ vị trí không được cấp quyền và xác nhận metrics không trả về 200 ngoài ý muốn.
- [ ] Scraper vẫn kết nối được qua đúng đường mạng, auth và TLS sau khi áp dụng security.
- [ ] Metrics tags không chứa request ID, user ID, email, token hoặc giá trị làm bùng nổ cardinality.
- [ ] Phân biệt vấn đề endpoint exposure với MeterRegistry, MeterFilter, tracing sampling và exporter.
- [ ] Có runbook đối chiếu metrics với logs/traces khi điều tra lỗi và latency.

## 15. Bài tập tự kiểm tra

### Bài 1: Endpoint nào dành cho Prometheus?

Ứng dụng có hai URL:

~~~text
/actuator/metrics
/actuator/prometheus
~~~

**Câu hỏi:** Prometheus nên scrape URL nào và vì sao?

**Đáp án:** Thông thường là `/actuator/prometheus` khi Prometheus registry được cấu hình, vì đây là endpoint xuất metrics theo định dạng Prometheus. `/actuator/metrics` là API JSON để liệt kê và chẩn đoán meter, không phải endpoint scrape tương đương.

### Bài 2: Có SecurityFilterChain mà vẫn rò rỉ metrics

Ứng dụng có Spring Security và một `SecurityFilterChain` riêng cho API. Sau deploy, `/actuator/metrics` trả 200 cho client không xác thực.

**Câu hỏi:** Điều gì đáng kiểm tra trước?

**Đáp án:** Kiểm tra các matcher và phạm vi của security filter chains: custom chain có thể khiến Spring Boot không dùng bảo mật Actuator mặc định, hoặc route quản trị không đi qua chain phù hợp. Kiểm tra ingress và management context nữa, không chỉ thêm `spring-boot-starter-security` rồi cho rằng đã an toàn.

### Bài 3: 404 có chứng minh không có metrics?

`/actuator/metrics` trả 404 nhưng ứng dụng vẫn ghi `Counter` vào `MeterRegistry`.

**Đáp án:** Không. HTTP exposure/enablement và khả năng ghi metrics vào registry là hai tầng khác nhau. Hãy kiểm tra URL, port, endpoint exposure và registry; dữ liệu có thể vẫn đang được xuất qua một backend khác.

### Bài 4: Role của scraper

Một Prometheus service account chỉ cần đọc `/actuator/prometheus` nhưng được cấp role cho toàn bộ endpoints `env`, `configprops` và `heapdump`.

**Câu hỏi:** Đây là thiết kế phù hợp không?

**Đáp án:** Không. Đây là quyền quá rộng so với nhiệm vụ scrape. Nên cấp quyền tối thiểu cho exporter endpoint và hạn chế mạng/TLS; tránh expose những endpoint quản trị nhạy cảm.

### Bài 5: Sau khi bật xác thực, target DOWN

Ops gọi `/actuator/prometheus` bằng tài khoản cá nhân được 200; Prometheus target chuyển từ UP sang DOWN và báo 401.

**Đáp án:** Kiểm tra credentials/identity của scraper, cấu hình `basic_auth` hoặc phương thức auth khác, role `SCRAPER`, secret rotation và URL đích. Không xóa security chỉ để target UP; sửa đúng quyền truy cập và kiểm chứng lại.

**Ghi nhớ:** `/actuator/metrics` là **API chẩn đoán metrics**, `/actuator/prometheus` là **đường xuất cho scraper**. Cả hai cần được kiểm soát theo nguyên tắc **expose tối thiểu, phân quyền tối thiểu, mạng quản trị an toàn và bảo vệ metadata**. Chỉ khi đường đọc metrics đáng tin cậy và không mở quá mức, chúng mới hỗ trợ tốt quá trình kết nối metrics, logs và distributed tracing để tìm nguyên nhân lỗi và độ trễ thực tế.
