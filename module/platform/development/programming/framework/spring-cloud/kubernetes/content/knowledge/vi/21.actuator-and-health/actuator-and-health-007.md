# Giới hạn chi tiết sức khỏe công khai

Endpoint sức khỏe giúp Kubernetes và hệ thống giám sát biết ứng dụng có thể tiếp tục phục vụ hay không. Tuy nhiên, một phản hồi health quá chi tiết cũng có thể tiết lộ tên Pod, namespace, địa chỉ nội bộ, loại cơ sở dữ liệu, đường dẫn đĩa hoặc thông báo lỗi kết nối. Người gọi công khai thường chỉ cần một tín hiệu trạng thái, trong khi đội vận hành cần một kênh chẩn đoán được kiểm soát.

Bài học thuộc chương **Actuator và sức khỏe** của module **SPRING_CLOUD_KUBERNETES**. Mục tiêu là giới hạn dữ liệu health đưa ra ngoài mà vẫn giữ đúng hành vi probe, mã HTTP và khả năng điều tra sự cố của ứng dụng Spring chạy trên Kubernetes.

## 1. Xác định thông tin nào được phép công khai

Trước khi viết cấu hình, cần định nghĩa người nhận và mục đích của từng đường health.

| Người gọi | Nhu cầu | Dữ liệu nên nhận |
| --- | --- | --- |
| Bộ kiểm tra trạng thái công khai | Biết đường phục vụ được chọn có sẵn sàng không | Trạng thái và mã HTTP theo hợp đồng đã định nghĩa |
| Kubelet | Thực hiện liveness/readiness/startup probe | Tín hiệu phù hợp với loại probe; không cần topology hoặc credential |
| Công cụ giám sát được cấp quyền | Nhận biết thành phần gây suy giảm | Các thành phần được chọn và chi tiết đã giới hạn |
| Người vận hành điều tra sự cố | Kết hợp health với log, metric và sự kiện | Thông tin chẩn đoán qua kênh có xác thực, phân quyền và phạm vi mạng phù hợp |

Không có yêu cầu mặc định rằng toàn bộ `/actuator/**` phải được mở ra Internet để kubelet đọc health. Kubelet có thể gọi Pod trực tiếp, còn đường public và đường vận hành có thể được định tuyến riêng.

Trong bài, “công khai” nghĩa là người gọi không có quyền chẩn đoán vẫn truy cập được. Một endpoint nằm trong cluster nhưng mọi Pod đều có thể gọi cũng cần được xét theo mức độ tin cậy thực tế, không chỉ theo tên Service.

### Ba lớp thông tin trong phản hồi

Xét cấu trúc minh họa sau; tên trường trong từng `details` phụ thuộc indicator thực tế:

```json
{
  "status": "DOWN",
  "components": {
    "kubernetes": {
      "status": "UP",
      "details": {
        "namespace": "apps",
        "podName": "orders-example",
        "serviceAccount": "orders-runtime"
      }
    },
    "partnerGateway": {
      "status": "DOWN",
      "details": {
        "endpoint": "https://partner.internal.example",
        "error": "Thông báo lỗi kết nối nội bộ"
      }
    }
  }
}
```

Có ba quyết định khác nhau:

1. Cho phép công khai `status` tổng hợp hay không.
2. Cho phép liệt kê `components` và trạng thái của từng thành phần hay không.
3. Cho phép xem `details` của mỗi thành phần hay không.

Chỉ xóa `error` vẫn có thể để lộ kiến trúc qua tên component. Chỉ ẩn body ở giao diện frontend không ngăn người dùng gọi trực tiếp endpoint. [Cấu trúc phản hồi health của Spring Boot](https://docs.spring.io/spring-boot/3.5/api/rest/actuator/health.html).

## 2. Hiểu đúng các lớp cấu hình bảo vệ

Các ví dụ được đối chiếu với Spring Boot dòng 3.5 và Spring Cloud Kubernetes dòng 3.3. Khi áp dụng, dùng BOM và dependency tương thích của dự án; không suy rằng package Java hoặc mọi mặc định giữ nguyên giữa các major version.

| Cấu hình/cơ chế | Điều nó kiểm soát | Điều không được suy ra |
| --- | --- | --- |
| `management.endpoints.web.exposure.include` | Endpoint nào được đưa ra HTTP | Không quyết định ai được đọc từng endpoint |
| `management.endpoint.health.show-details` | Khi nào hiển thị chi tiết health | Không thay thế quy tắc truy cập HTTP |
| `management.endpoint.health.show-components` | Khi nào hiển thị cây thành phần | Không thay đổi việc thành phần có được kiểm tra hay không |
| `management.endpoint.health.roles` | Role nào được xem dữ liệu với chế độ `when-authorized` | Không tự bắt mọi request health phải đăng nhập |
| Spring Security | Quyền truy cập theo request và danh tính | Không tự làm sạch dữ liệu mà custom indicator tạo ra |
| Ingress, firewall, NetworkPolicy | Đường truy cập và nguồn mạng | Không tự thiết lập role trong Spring Security |

Hai thuộc tính hiển thị có các lựa chọn `never`, `when-authorized`, `always`. Nếu không đặt `show-components`, Spring Boot dùng thiết lập `show-details` tương ứng. Đặt rõ cả hai giúp chính sách dễ kiểm tra khi có nhiều lớp cấu hình. [Thuộc tính health của Spring Boot](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html#appendix.application-properties.actuator).

Điểm dễ nhầm nhất của `when-authorized`: nếu không cấu hình `roles`, mọi người dùng đã xác thực đều được xem theo chính sách đó. Một tài khoản người dùng nghiệp vụ thông thường không nên mặc nhiên có quyền chẩn đoán hạ tầng. Cần chỉ định role phù hợp và cấu hình cơ chế xác thực tạo đúng authority. [Chính sách hiển thị thông tin health](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html#actuator.endpoints.health).

Ngược lại, đặt `roles` không biến `show-details: always` thành chế độ có phân quyền. Muốn role quyết định việc hiển thị, cần dùng `when-authorized` cùng quy tắc HTTP phù hợp.

## 3. Cấu hình tối thiểu khi chỉ cần trạng thái

Nếu không cần cung cấp chi tiết health qua HTTP cho bất kỳ người gọi nào, cấu hình khởi đầu có thể là:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      show-details: never
      show-components: never
```

Đây là cấu hình về exposure và nội dung. Dự án vẫn cần quyết định endpoint health được cho phép đọc trong chuỗi bảo mật nào. Không bổ sung `include: "*"` chỉ để sửa một lỗi probe không truy cập được.

Phản hồi ở một đường health không có metadata bổ sung có thể đơn giản như sau:

```json
{
  "status": "UP"
}
```

Khi health thay đổi, trạng thái vẫn phải phản ánh đúng kết quả:

```http
HTTP/1.1 503 Service Unavailable
Content-Type: application/json

{"status":"DOWN"}
```

Việc ẩn chi tiết không làm indicator ngừng chạy, không loại nó khỏi phép tổng hợp và không biến một kết quả `DOWN` thành `UP`. Theo ánh xạ mặc định, `DOWN` và `OUT_OF_SERVICE` trả HTTP 503. Không đổi tất cả kết quả thành 200 để làm endpoint trông ít thông tin hơn, vì probe và giám sát có thể hiểu sai. [Ánh xạ health status sang HTTP](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html#actuator.endpoints.health.writing-custom-health-indicators).

Cũng không cam kết root `/actuator/health` luôn chỉ có một trường `status`: khi có health group, response có thể có metadata như tên group. Nếu hợp đồng public yêu cầu một tập trường hẹp và ổn định, chọn đường group cụ thể, giới hạn route và kiểm tra body thực tế. `show-components` và `show-details` không phải bộ lọc tùy ý cho mọi trường metadata.

## 4. Tách health công khai và nhóm chẩn đoán

Khi đội vận hành cần chi tiết, có thể chia nhóm thay vì bật `always` trên toàn bộ health endpoint. Ví dụ dưới đây thay thế cấu hình tối thiểu ở mục 3 bằng một cấu hình hoàn chỉnh hơn.

Giả định ứng dụng Servlet có Actuator, Spring Security, cổng chính `8080`, base path mặc định `/actuator`, không có context path và không tách management port. Các contributor `ping`, `diskSpace` mặc định chưa bị tắt; `readinessState` được cung cấp khi bật probes.

```yaml
server:
  port: 8080

management:
  endpoints:
    web:
      discovery:
        enabled: false
      exposure:
        include: health
  endpoint:
    health:
      show-details: never
      show-components: never
      probes:
        enabled: true
      group:
        public:
          include: readinessState
          show-details: never
          show-components: never
        internal:
          include: ping,diskSpace
          show-details: when-authorized
          show-components: when-authorized
          roles: HEALTH_DETAILS
```

Ý nghĩa của từng đường:

| Đường | Nội dung dự kiến | Hợp đồng sử dụng |
| --- | --- | --- |
| `/actuator/health/public` | Trạng thái nhóm `public`, không có cây component/chi tiết | Kiểm tra public theo readiness state đã chọn |
| `/actuator/health/liveness` | Nhóm liveness, kế thừa chính sách ẩn chi tiết | Kubelet liveness probe |
| `/actuator/health/readiness` | Nhóm readiness, kế thừa chính sách ẩn chi tiết | Kubelet readiness probe |
| `/actuator/health/internal` | Thành phần được chọn và chi tiết khi đủ quyền | Chẩn đoán nội bộ |
| `/actuator/health` | Health tổng hợp của hệ thống | Không mở public trong ví dụ bảo mật ở mục 5 |

Nhóm `public` trong ví dụ chỉ phản ánh `readinessState`, không khẳng định mọi dependency đều khỏe. Nếu cần kiểm tra thêm một dependency trước khi nhận lưu lượng, cần quyết định rõ nó thuộc nhóm phục vụ nào. Không thêm cơ sở dữ liệu vào liveness chỉ để người ngoài biết rằng nó đang lỗi.

Group mặc định kế thừa cấu hình health và có thể ghi đè chính sách hiển thị/role. Spring Boot còn kiểm tra contributor được tham chiếu có tồn tại khi khởi động. Nếu `diskSpace` đã bị tắt, sửa danh sách theo contributor thực có; không tắt kiểm tra membership để che lỗi tên hoặc dependency. [Health groups](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html#actuator.endpoints.health.groups).

Tắt discovery page chỉ làm giảm khả năng liệt kê các liên kết Actuator, không chặn URL mà người gọi đã biết. Nhóm có tên `internal` cũng chưa được bảo vệ cho đến khi có quy tắc truy cập tương ứng.

### Đưa thông tin Kubernetes vào đúng nhóm

Pod Health Indicator của Spring Cloud Kubernetes có thể đưa ra tên/IP Pod, namespace, ServiceAccount, tên/IP node và thông tin ứng dụng đang ở trong hay ngoài Kubernetes. Đây là dữ liệu hữu ích khi điều tra, nhưng không cần cho response công khai. [Pod Health Indicator](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/pod-health-indicator.html).

Nếu contributor `kubernetes` thực sự có trong ứng dụng và cần cho chẩn đoán, có thể đổi danh sách của nhóm `internal` thành:

```yaml
include: ping,diskSpace,kubernetes
```

Dòng này là giá trị thay cho `management.endpoint.health.group.internal.include`, không phải một manifest độc lập. Giữ chính sách hiển thị và role của nhóm như cũ. Tránh dùng `include: "*"` theo thói quen nếu muốn mọi contributor mới phải được xét trước khi công bố cho nhóm vận hành.

Nếu không cần contributor đó, có thể tắt riêng:

```properties
management.health.kubernetes.enabled=false
```

Tắt contributor khác với việc ẩn dữ liệu: nó loại một nguồn thông tin khỏi health và có thể ảnh hưởng phép tổng hợp/nhóm đang tham chiếu. Nó không phải công tắc tắt toàn bộ Spring Cloud Kubernetes hay bằng chứng DiscoveryClient/Watcher đã ngừng hoạt động.

## 5. Áp dụng quyền HTTP một cách rõ ràng

Cấu hình sau là ví dụ hoàn chỉnh cho quy tắc request trong một ứng dụng Servlet nhỏ. Nó dùng đúng các URL của mục 4: GET của nhóm public và probe được phép đọc; nhóm internal yêu cầu role; các đường Actuator khác bị từ chối; request nghiệp vụ còn lại cần xác thực.

```java
package com.example.orders.security;

import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration(proxyBeanMethods = false)
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(authorize -> authorize
                .requestMatchers(HttpMethod.GET,
                        "/actuator/health/public",
                        "/actuator/health/liveness",
                        "/actuator/health/readiness")
                    .permitAll()
                .requestMatchers(HttpMethod.GET,
                        "/actuator/health/internal",
                        "/actuator/health/internal/**")
                    .hasRole("HEALTH_DETAILS")
                .requestMatchers(EndpointRequest.toAnyEndpoint())
                    .denyAll()
                .anyRequest()
                    .authenticated());
        http.httpBasic(withDefaults());
        return http.build();
    }
}
```

Ví dụ giả định dự án đã có nguồn tài khoản hoặc authentication provider phù hợp. Nó không tạo người dùng, không lưu mật khẩu và không tự cấp role. HTTP Basic giúp minh họa trên máy local; khi truyền credential qua mạng, cần TLS và cơ chế truy cập được phê duyệt cho môi trường triển khai. Nếu dự án dùng OAuth2/JWT hoặc nhiều filter chain, tích hợp chính sách này vào cấu hình hiện có thay vì thêm một chain cạnh tranh không rõ thứ tự.

Với quy ước role mặc định, `hasRole("HEALTH_DETAILS")` kiểm tra authority `ROLE_HEALTH_DETAILS`. Khai báo `roles: HEALTH_DETAILS` trong health group cũng phải được ánh xạ đúng theo security context của ứng dụng. Một scope tên gần giống hoặc một claim JWT chưa được chuyển thành authority không tự đáp ứng điều kiện đó. [Quy tắc phân quyền request của Spring Security 6.5](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html).

Thứ tự rule có ý nghĩa: các đường cụ thể cần được xét trước rule từ chối Actuator. Không đặt `/actuator/health/**` thành `permitAll` trước rule internal, vì request internal có thể khớp rule rộng trước. Với cấu hình minh họa, GET trực tiếp tới `/actuator/health/kubernetes` cũng không được mở chỉ vì biết tên component.

Khi tự khai báo `SecurityFilterChain`, Spring Boot nhường việc thiết lập quyền HTTP cho cấu hình của bạn. Vì vậy cần giữ quy tắc cho cả endpoint quản trị và phần ứng dụng còn lại. Code trên chỉ minh họa Servlet; WebFlux cần `SecurityWebFilterChain` và API cấu hình tương ứng, không dùng nguyên lớp này. [Bảo mật Actuator](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html#actuator.endpoints.security).

Nhóm public dùng `never`, nên ngay cả người vận hành đã đăng nhập cũng không nhận chi tiết tại URL public. Người đó phải dùng đường internal. Đây là khác biệt quan trọng với cách dùng `when-authorized` trên cùng một endpoint công khai: cách sau có thể trả body khác nhau theo danh tính và đòi hỏi kiểm soát cache/proxy tương ứng.

## 6. Giữ probe hoạt động mà không cung cấp chi tiết

Kubelet không cần biết tên node, dung lượng đĩa hoặc thông báo exception để thực hiện HTTP probe. Trong cấu hình ví dụ, nó gọi các nhóm probe đã được phép truy cập bằng GET:

```yaml
livenessProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
  periodSeconds: 10
  timeoutSeconds: 2
readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: 8080
  periodSeconds: 5
  timeoutSeconds: 2
```

Đây là phần đặt trong cấu hình container, không phải một Deployment độc lập. Các thời gian chỉ là giá trị minh họa; ứng dụng khởi động chậm cần ngân sách khởi động phù hợp, có thể qua startup probe.

Probe phải nhận kết quả sức khỏe thật, không bị chuyển tới trang đăng nhập hoặc trả 401/403 do thiếu credential. Kubernetes đánh giá HTTP probe dựa trên kết quả HTTP; cung cấp nhiều trường JSON không làm phép kiểm tra đáng tin cậy hơn. [Cấu hình HTTP probe](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/).

Nếu tách management port hoặc đổi base path, cập nhật URL, cổng và matcher tương ứng. Khi đưa thêm `/livez`, `/readyz` ra cổng ứng dụng, chúng cũng là đường health cần áp dụng chính sách nội dung và quyền. Không chỉ kiểm tra URL mà Ingress đang quảng bá. [Cổng và base path quản trị](https://docs.spring.io/spring-boot/3.5/reference/actuator/monitoring.html).

Về định tuyến, chỉ công bố route chính xác cần thiết, chẳng hạn `/actuator/health/public`. Các đường probe có thể chỉ cần kubelet truy cập; đường internal nên nằm sau kênh vận hành có giới hạn nguồn và xác thực. Tránh route public kiểu `/actuator` với prefix quá rộng nếu không có nhu cầu.

Kubernetes RBAC quyết định quyền truy cập Kubernetes API, chẳng hạn quyền đọc ConfigMap/Secret. Nó không tự phân quyền HTTP `/actuator/health/internal`. Việc kubelet đang kiểm tra Pod hoặc người gọi sở hữu ServiceAccount không tự tạo role `HEALTH_DETAILS` trong Spring Security. [Phạm vi Kubernetes RBAC](https://kubernetes.io/docs/reference/access-authn-authz/rbac/).

## 7. Giới hạn dữ liệu ngay tại nguồn tạo health

Chính sách hiển thị là một lớp bảo vệ, nhưng dữ liệu nhạy cảm vẫn không nên được đưa tùy tiện vào `Health.details`. Khi đổi profile, bổ sung nhóm hoặc cấp quyền mới, dữ liệu đó có thể được xuất ra ở nơi khác.

Ví dụ cần tránh khi `exception` hoặc URL có thể chứa dữ liệu nhạy cảm:

```java
return Health.down(exception)
        .withDetail("connectionUrl", connectionUrl)
        .withDetail("configuration", configurationProperties)
        .build();
```

Không xem chuỗi exception là dữ liệu đã được làm sạch. Nó có thể mang hostname nội bộ, đường dẫn, tham số kết nối hoặc nội dung trả về từ hệ thống khác. Các đối tượng cấu hình cũng có thể chứa Secret, token hoặc thông tin tài khoản.

Một kết quả giới hạn hơn có thể là:

```java
return Health.down()
        .withDetail("reason", "UPSTREAM_UNAVAILABLE")
        .build();
```

Mã lý do do ứng dụng kiểm soát giúp vận hành phân loại lỗi mà không công bố payload gốc. Chi tiết sâu hơn có thể được đối chiếu qua log đã có chính sách che dữ liệu và quyền truy cập phù hợp; không chuyển nguyên thông tin bí mật từ health sang log rồi coi là đã giải quyết.

Các nguyên tắc khi viết custom indicator:

- Chỉ đưa ra các trường cần thiết cho quyết định vận hành đã xác định.
- Không thêm mật khẩu, token, private key, nội dung Secret hoặc toàn bộ map ConfigMap.
- Không mặc định mọi URL là an toàn; user info và query string có thể chứa credential.
- Giữ danh sách reason hữu hạn, tránh đưa thông báo lỗi nguyên văn thành tên trạng thái hoặc nhãn metric.
- Không để một lần kiểm tra công khai kích hoạt thao tác chậm, ghi dữ liệu hoặc tải lớn không cần thiết.

Đặt `show-details: never` cũng không tự làm sạch controller tùy chỉnh, handler lỗi hoặc gateway response. Nếu tự viết `/health` rồi serialize một đối tượng lấy từ Actuator bằng code nội bộ, phải kiểm tra riêng chính sách của đường đó; không suy rằng cơ chế hiển thị HTTP chuẩn sẽ tự được áp dụng.

## 8. Kiểm tra mọi đường có thể làm lộ thông tin

Để giới hạn health công khai, cần kiểm tra cả các đường lân cận:

| Bề mặt | Ví dụ cần xem lại |
| --- | --- |
| Root và health group | `/actuator/health`, `/actuator/health/public`, `/actuator/health/internal` |
| Component và component lồng nhau | `/actuator/health/kubernetes`, các đường con của nhóm internal |
| Đường health bổ sung | `/livez`, `/readyz`, alias do proxy hoặc ứng dụng tự tạo |
| Các endpoint khác | `/actuator/info`, `env`, `configprops`, `metrics`, `prometheus` nếu được expose |
| Đường truy cập mạng khác | Ingress, DNS Service, Pod IP, management port, port-forward |
| Dữ liệu được sao chép | Log, trang trạng thái, dashboard, cache/proxy response |

Spring Cloud Kubernetes còn có `InfoContributor` có thể thêm thông tin Pod vào endpoint `info`. Ẩn chi tiết `health` không tự ẩn thông tin đã được công bố tại `info`. Có thể không expose endpoint này hoặc tắt contributor riêng khi không cần:

```properties
management.info.kubernetes.enabled=false
```

[Info Contributor của Spring Cloud Kubernetes](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/info-contributor.html).

Tương tự, cơ chế che giá trị của `env`/`configprops` không phải bảo đảm chung rằng mọi custom health detail đã được che. Mỗi endpoint cần có chính sách exposure, quyền và dữ liệu phù hợp.

Nếu một URL có thể trả chi tiết theo danh tính, reverse proxy/CDN không được chia sẻ response có quyền cho người gọi không có quyền. Tránh cache dùng chung response chẩn đoán và kiểm tra header/chính sách cache thực tế. Đặt TTL không thay thế việc phân biệt quyền truy cập.

Khi ConfigMap, profile hoặc biến môi trường ghi đè cấu hình, hãy kiểm tra giá trị hiệu lực và kết quả của từng replica. Sửa một file cấu hình hoặc nhìn một Pod trả đúng chưa chứng minh các Pod còn lại đã áp dụng. Cũng không mặc định mọi thuộc tính management sẽ tự đổi ngay khi Configuration Watcher phát refresh; cần dùng cơ chế cập nhật/restart phù hợp và xác minh kết quả.

## 9. Thực hành xác minh bằng ma trận quyền

Chuẩn bị một ứng dụng dùng cấu hình nhóm và bảo mật ở mục 4–5. Giả sử nguồn xác thực đã cung cấp hai người dùng thử nghiệm: `reader` không có role chẩn đoán và `ops` có `ROLE_HEALTH_DETAILS`. Không dùng mật khẩu mẫu cố định trong manifest hoặc câu lệnh.

Trên máy local, có thể dùng `curl.exe` của Windows; với hệ thống khác dùng `curl` tương ứng:

```shell
curl.exe -i http://localhost:8080/actuator/health/public
curl.exe -i http://localhost:8080/actuator/health/liveness
curl.exe -i http://localhost:8080/actuator/health/readiness
curl.exe -i http://localhost:8080/actuator/health/internal
curl.exe -i --user reader http://localhost:8080/actuator/health/internal
curl.exe -i --user ops http://localhost:8080/actuator/health/internal
curl.exe -i --user ops http://localhost:8080/actuator/health/public
curl.exe -i http://localhost:8080/actuator/health/kubernetes
```

Khi chỉ cung cấp tên người dùng, `curl` yêu cầu nhập mật khẩu; không đặt credential thật trong lịch sử lệnh hoặc URL. Các lệnh dùng HTTP ở đây dành cho localhost; khi kiểm tra qua mạng dùng kênh bảo mật đã thiết kế.

| Phép kiểm tra với cấu hình minh họa | Kết quả cần xác minh |
| --- | --- |
| Anonymous gọi group public | Được đọc trạng thái; không có `components` hoặc `details` |
| `ops` gọi group public | Vẫn không có component/chi tiết, vì group public dùng `never` |
| Anonymous gọi internal | Bị từ chối; với HTTP Basic minh họa thường là 401 |
| `reader` có credential hợp lệ gọi internal | Bị từ chối do thiếu role, thường là 403 |
| `ops` gọi internal | Được đọc các contributor đã chọn và chi tiết mà chúng thực sự cung cấp |
| Anonymous gọi component trực tiếp | Không đọc được trạng thái/chi tiết của component đó |
| Kubelet gọi liveness/readiness | Nhận kết quả health thật, không nhận trang đăng nhập |
| Ứng dụng hoặc group đang không sẵn sàng | Mã trạng thái phải đúng với health và mapping; không mặc định luôn 200 |

Không chỉ tìm chuỗi `details` ở cấp JSON ngoài cùng; cây component có thể lồng nhau. Với response public, kiểm tra toàn bộ body, mã HTTP, redirect và header. Đừng kết luận đã ẩn dữ liệu chỉ vì endpoint trả 401 trong lúc bạn dùng sai credential: cần kiểm tra cả request hợp lệ có và không có role.

Lặp lại phép kiểm tra qua đường public thực tế và đường quản trị được cấp quyền. Nếu dùng port-forward để kiểm tra một Pod, kết quả đó chứng minh hành vi tại Pod được chọn, không chứng minh route Ingress hoặc mọi replica đều giống nhau.

## 10. Giữ giới hạn cả trong trạng thái lỗi

Một response `UP` ngắn chưa đủ chứng minh chính sách an toàn. Cần thử tình huống có lỗi kiểm soát được trong môi trường thử nghiệm, vì indicator thường chỉ thêm `details.error` khi thất bại.

Ví dụ kế hoạch xác minh:

1. Ghi nhận response public khi ứng dụng đã sẵn sàng.
2. Tạo một tình huống lỗi an toàn ở contributor thuộc nhóm đang kiểm tra.
3. Xác nhận trạng thái và HTTP mapping thay đổi đúng, nhưng body công khai không bổ sung hostname, stack trace, URL hoặc credential.
4. Xác nhận người không có quyền vẫn không đọc được nhóm internal hay component path.
5. Xác nhận người vận hành nhận đủ tín hiệu cần thiết qua kênh được cấp quyền.
6. Phục hồi dependency và xác nhận endpoint trở lại đúng trạng thái.

Không làm hỏng dependency production chỉ để kiểm tra định dạng health. Có thể dùng indicator thử nghiệm hoặc môi trường biệt lập. Nếu contributor lỗi không thuộc nhóm `public`, việc public vẫn `UP` có thể đúng với hợp đồng nhóm; phải giải thích rõ điều đó, không sửa body để giả lập kết quả mong muốn.

Các lỗi cấu hình thường gặp:

| Dấu hiệu | Nguyên nhân cần xem xét | Điều chỉnh phù hợp |
| --- | --- | --- |
| Không thấy details nhưng vẫn thấy tên database/cache | `show-components` còn cho phép | Đặt chính sách component rõ ràng và kiểm tra group override |
| Tài khoản nghiệp vụ xem được chẩn đoán | `when-authorized` không có role cụ thể hoặc rule quá rộng | Xác định role và ánh xạ authority, hạn chế đường internal |
| Public group lộ chi tiết sau đổi profile | Giá trị group bị ghi đè | Kiểm tra cấu hình hiệu lực và mọi replica |
| Probe trả 401/403 | Rule HTTP chặn đường probe | Cho phép đúng GET của nhóm probe, giữ nội dung tối thiểu |
| Root health ít dữ liệu nhưng `info` vẫn lộ Pod | Endpoint khác có contributor riêng | Xem lại exposure và contributor của từng endpoint |
| Health public bị thay bằng trang HTML | Gateway rewrite, redirect hoặc handler lỗi | Kiểm tra đường thực tế tới ứng dụng và chuỗi bảo mật |
| Đã chặn Ingress nhưng Pod khác vẫn xem được chi tiết | Listener/Service còn truy cập được, thiếu quyền HTTP | Áp dụng phân quyền tại ứng dụng và giới hạn nguồn mạng cần thiết |
| Internal có role đúng nhưng vẫn chỉ thấy trạng thái | Chính sách group vẫn `never` hoặc authority không được nhận diện như dự kiến | Kiểm tra đồng thời quyền request và điều kiện hiển thị |

## 11. Bài tập áp dụng

Với một dịch vụ Spring Cloud Kubernetes chạy hai replica, hãy viết chính sách và xác minh các yêu cầu sau:

1. Người dùng public chỉ đọc group phản ánh hợp đồng sẵn sàng đã chọn, không thấy topology hoặc chi tiết lỗi.
2. Kubelet tiếp tục thực hiện probe mà không cần dùng tài khoản vận hành.
3. Chỉ danh tính có role được chỉ định mới truy cập nhóm chẩn đoán.
4. Thông tin Kubernetes chỉ được đưa vào nhóm nội bộ khi contributor có thật và có nhu cầu sử dụng.
5. Một lỗi dependency trong môi trường thử nghiệm không làm response public lộ thêm thông tin.
6. Cả hai replica đều áp dụng cùng chính sách sau khi triển khai cấu hình.

Phần giải thích cần nêu rõ sự khác nhau giữa “không cho truy cập endpoint”, “cho truy cập nhưng chỉ trả trạng thái”, “ẩn cây thành phần” và “không tạo contributor”. Đồng thời chỉ ra nguồn xác thực, role/authority, đường mạng và nơi người vận hành lấy thông tin khi sự cố xảy ra.

Một triển khai phù hợp bắt đầu bằng dữ liệu công khai tối thiểu, giữ nguyên ý nghĩa health và chỉ mở kênh chẩn đoán khi có nhu cầu cụ thể. Việc dùng DiscoveryClient, ConfigMap/Secret, Spring Cloud LoadBalancer hay Configuration Watcher không làm tăng nhu cầu công bố chi tiết hạ tầng cho mọi người gọi.
