# Endpoint tồn tại, được bật, được expose và được phép truy cập

Trong Spring Boot Actuator, việc thấy một endpoint trong tài liệu không có nghĩa luôn gọi được URL tương ứng. Ví dụ, `/actuator/metrics` có thể trả về `404 Not Found` dù ứng dụng đang chạy bình thường; một endpoint khác trả về `401 Unauthorized`, `403 Forbidden` hoặc `503 Service Unavailable`. Những kết quả này phản ánh **các tầng điều kiện khác nhau**, không nên quy tất cả về một lỗi cấu hình.

Để chẩn đoán chính xác, hãy tách bốn câu hỏi:

1. **Endpoint có tồn tại trong ứng dụng không?** Có implementation, dependency, bean và các điều kiện cần thiết hay chưa?
2. **Endpoint có được bật và cho phép thực hiện operation không?** Spring Boot có chấp nhận endpoint đó theo cấu hình enable/access không?
3. **Endpoint có được expose qua kênh đang sử dụng không?** HTTP và JMX có danh sách exposure riêng.
4. **Caller có được phép truy cập không?** Spring Security, chính sách authorization, mạng và hạ tầng triển khai có cho request đi tới endpoint không?

Bốn câu hỏi này là một mô hình kiểm tra logic, không phải bốn cờ độc lập luôn có sẵn trong mọi phiên bản Spring Boot. Một số cấu hình enable/access còn ảnh hưởng trực tiếp tới việc endpoint bean có được tạo trong ApplicationContext hay không.

## 1. Actuator endpoint là gì?

Spring Boot Actuator cung cấp các điểm quan sát và quản trị để tìm hiểu trạng thái ứng dụng đang chạy. Những endpoint thường gặp:

| Endpoint ID | Mục đích |
|---|---|
| `health` | Trạng thái sức khỏe ứng dụng và các health contributor |
| `info` | Thông tin ứng dụng đã được cấu hình công bố |
| `metrics` | Tên và giá trị metric được Micrometer ghi nhận |
| `loggers` | Quan sát và, nếu được phép, thay đổi log level |
| `env` | Thông tin các property sources trong Environment |
| `configprops` | Các bean cấu hình được bind bằng `@ConfigurationProperties` |
| `beans` | Thông tin các bean trong ApplicationContext |
| `threaddump` | Thông tin thread tại thời điểm lấy mẫu |
| `prometheus` | Metric theo định dạng Prometheus khi có registry tương ứng |
| `shutdown` | Yêu cầu dừng ứng dụng khi được cho phép |

Mỗi endpoint có một **ID**. Ví dụ, `health` là ID còn `/actuator/health` là đường dẫn HTTP mặc định thông thường, không phải bản thân định danh endpoint.

Một endpoint có thể cung cấp các operation khác nhau:

- `@ReadOperation`: đọc dữ liệu quan sát.
- `@WriteOperation`: thực hiện thay đổi trạng thái.
- `@DeleteOperation`: xóa hoặc làm sạch dữ liệu theo chức năng endpoint.

HTTP mapping của operation, quyền hạn của endpoint và quyền hạn của người gọi là các khái niệm cần xét riêng.

## 2. Điều kiện thứ nhất: endpoint phải có mặt trong ứng dụng

Để dùng các endpoint Actuator thông dụng, dự án thường cần dependency:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

Với Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

Starter cung cấp các thành phần Actuator, Micrometer và auto-configuration liên quan. Nhưng điều đó không có nghĩa **mọi** endpoint liệt kê trong tài liệu sẽ xuất hiện.

Một số endpoint phụ thuộc thêm vào:

- Thư viện có trên classpath.
- Một bean hoặc tính năng chuyên biệt đã được cấu hình.
- Điều kiện auto-configuration của phiên bản Spring Boot.
- Phần mở rộng hoặc integration tương ứng.
- Cấu hình access/enable có cho phép endpoint được đăng ký hay không.

Ví dụ, muốn dùng endpoint `prometheus`, ứng dụng thường cần Prometheus registry:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
~~~

Nếu chỉ khai báo HTTP exposure cho `prometheus` mà thiếu registry phù hợp, endpoint có thể không được tạo. **Exposure không thể tự sinh ra endpoint chưa tồn tại.**

### Custom endpoint

Ứng dụng cũng có thể định nghĩa endpoint riêng:

~~~java
import java.util.Map;

import org.springframework.boot.actuate.endpoint.annotation.Endpoint;
import org.springframework.boot.actuate.endpoint.annotation.ReadOperation;
import org.springframework.stereotype.Component;

@Component
@Endpoint(id = "buildstatus")
public class BuildStatusEndpoint {

    @ReadOperation
    public Map<String, String> status() {
        return Map.of("state", "available");
    }
}
~~~

Ví dụ dùng ID `buildstatus` cho custom endpoint; đường dẫn web mặc định (nếu endpoint được bật và expose) là `/actuator/buildstatus`. Không nhầm `@Endpoint` với `@RestController`: cả hai đều có thể dẫn tới đường dẫn HTTP, nhưng dùng những cơ chế discovery, enable và exposure khác nhau.

Một lớp Java tồn tại trong source code không tự đồng nghĩa Spring đã tạo bean của nó. Nếu component không được scan, không được import hoặc bị loại bởi điều kiện bean, endpoint chưa hiện diện trong context.

## 3. Điều kiện thứ hai: endpoint phải được bật hoặc cấp quyền operation

Spring Boot có hai nhóm cơ chế cần phân biệt theo phiên bản:

- **Cơ chế enabled/disabled truyền thống:** dùng `management.endpoint.<id>.enabled` và `management.endpoints.enabled-by-default`.
- **Mô hình endpoint access của các phiên bản Spring Boot mới:** dùng `management.endpoint.<id>.access` và `management.endpoints.access.default`, với các giá trị như `none`, `read-only`, `unrestricted`.

Mô hình `access` được giới thiệu trong các dòng Spring Boot hiện đại (ví dụ Spring Boot 3.4 trở lên). Những dự án ở phiên bản cũ cần xem chính xác property được phiên bản đó hỗ trợ; không nên sao chép cấu hình access mới vào một project Boot cũ rồi kỳ vọng nó có tác dụng.

### 3.1. Cơ chế enabled trong các phiên bản dùng thuộc tính này

Ví dụ minh họa:

~~~yaml
management:
  endpoints:
    enabled-by-default: false
  endpoint:
    health:
      enabled: true
    info:
      enabled: true
~~~

Ý nghĩa của mô hình này:

1. Các endpoint không còn được bật theo mặc định.
2. `health` và `info` được bật lại có chủ đích.
3. Chưa có gì ở ví dụ này tự đảm bảo endpoint được expose qua HTTP.
4. Chưa có gì ở ví dụ này tự cấu hình authentication hoặc authorization.

Ở các phiên bản có cơ chế enablement đó, endpoint bị vô hiệu hóa thường không được tạo như một endpoint có thể sử dụng, vì vậy caller không thể gọi được nó chỉ bằng cách thêm vào danh sách exposure.

### 3.2. Mô hình access trong phiên bản hỗ trợ

Ví dụ:

~~~yaml
management:
  endpoints:
    access:
      default: none
  endpoint:
    health:
      access: read-only
    info:
      access: read-only
    metrics:
      access: read-only
~~~

Các giá trị access mang ý nghĩa:

| Giá trị | Ý nghĩa |
|---|---|
| `none` | Không cho phép truy cập endpoint; trong mô hình access hiện đại, endpoint có thể bị loại khỏi ApplicationContext |
| `read-only` | Chỉ cho phép các operation đọc |
| `unrestricted` | Không hạn chế operation theo tầng access này |

Điểm quan trọng: `unrestricted` **không có nghĩa mọi người dùng Internet được phép truy cập**. Đây là mức access của cơ chế Actuator, không phải quyết định authentication/authorization của Spring Security.

Ở chiều ngược lại, `read-only` không đồng nghĩa HTTP GET công khai; một caller vẫn có thể nhận `401` hoặc `403` nếu SecurityFilterChain yêu cầu xác thực hoặc vai trò phù hợp.

Một số phiên bản có cấu hình giới hạn mức access tối đa:

~~~yaml
management:
  endpoints:
    access:
      max-permitted: read-only
~~~

Tùy phiên bản, giới hạn này ngăn các endpoint mở operation ghi ngay cả khi cấu hình riêng của endpoint cho phép mức cao hơn. Nó hữu ích cho một số hệ thống chỉ cần quan sát, nhưng phải kiểm tra các thao tác quản trị mong muốn trước khi bật.

### Enabled và access không phải authorization theo từng người dùng

Hai nhóm property trên quyết định tính sẵn có và khả năng operation của endpoint ở cấp ứng dụng. Chúng không phân biệt người dùng `alice` và `bob` theo vai trò. Việc phân quyền theo identity, token, principal hoặc role cần một cơ chế bảo mật như Spring Security hay gateway.

Không nên đánh đồng:

~~~text
management.endpoint.loggers.access=read-only
~~~

với:

~~~text
Chỉ cho phép người dùng có role OPERATIONS xem endpoint loggers.
~~~

Câu đầu quy định loại operation được cho phép. Câu sau là quy tắc authorization.

## 4. Điều kiện thứ ba: endpoint phải được expose qua đúng kênh

Một endpoint có thể có mặt và được bật nhưng **không được công bố qua HTTP**. Actuator cho phép cấu hình exposure cho từng công nghệ, phổ biến là HTTP và JMX.

Ví dụ để công bố ba endpoint qua HTTP:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
~~~

Mặc định, Spring Boot thường chỉ expose một tập nhỏ endpoint, trong đó `health` là endpoint HTTP mặc định quan trọng nhất. Không nên suy diễn rằng `env`, `beans`, `loggers` hoặc `metrics` đều có URL truy cập sẵn chỉ vì dependency Actuator hiện diện.

Danh sách exposure xác định **endpoint nào có thể được truy cập qua transport**. Nó không tự cấp quyền cho caller cụ thể.

### Include và exclude

Ví dụ:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,loggers
        exclude: loggers
~~~

Với các quy tắc exposure tương ứng, `loggers` bị loại khỏi HTTP exposure dù nằm trong `include`. Thuộc tính `exclude` được ưu tiên khi hai danh sách cùng đề cập tới một endpoint.

Nếu muốn expose mọi endpoint HTTP, có thể dùng:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "*"
~~~

Trong YAML, nên đặt `"*"` trong dấu nháy vì dấu `*` có ý nghĩa đặc biệt trong cú pháp YAML. Tuy vậy, **không nên dùng include `"*"` vô điều kiện trên production**: một số endpoint tiết lộ cấu hình, topology, thread dump hoặc cho phép thao tác quản trị.

Danh sách exposure tối thiểu theo nhu cầu và lớp bảo mật rõ ràng thường là lựa chọn tốt hơn.

### HTTP và JMX là hai danh sách riêng

Ví dụ:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
    jmx:
      exposure:
        include: health,info,metrics
~~~

Trong cấu hình này, `metrics` có thể được expose qua JMX trong khi không có endpoint HTTP tương ứng. Không nên dựa vào việc JMX truy cập được để kết luận `GET /actuator/metrics` chắc chắn hoạt động.

JMX có cơ chế truy cập, kết nối và bảo mật riêng. Nếu dùng remote JMX, cần bảo vệ kênh kết nối và thiết lập authentication/authorization phù hợp; HTTP SecurityFilterChain không quản lý trực tiếp phiên JMX.

## 5. URL endpoint có thể khác /actuator/{id}

Đường dẫn HTTP thông thường của một endpoint web là:

~~~text
/actuator/{endpoint-id}
~~~

Ví dụ:

~~~text
GET /actuator/health
GET /actuator/info
GET /actuator/metrics
~~~

Tuy nhiên, có thể thay đổi web base path:

~~~yaml
management:
  endpoints:
    web:
      base-path: /manage
      exposure:
        include: health,info
~~~

Khi đó, đường dẫn tương ứng thường là:

~~~text
GET /manage/health
GET /manage/info
~~~

Có thể đổi mapping của từng endpoint:

~~~yaml
management:
  endpoints:
    web:
      base-path: /manage
      path-mapping:
        health: status
~~~

Khi đó, health endpoint được map theo đường dẫn:

~~~text
GET /manage/status
~~~

Caller dùng `/actuator/health` sẽ không tìm thấy đường dẫn tương ứng dù endpoint vẫn có mặt và được expose dưới URL mới.

### Cổng management và context path

Spring Boot có thể phục vụ Actuator trên cổng riêng:

~~~yaml
server:
  port: 8080

management:
  server:
    port: 9090
  endpoints:
    web:
      exposure:
        include: health,info
~~~

Trong ví dụ này, web API của ứng dụng chạy ở cổng `8080`, còn endpoint Actuator có thể được phục vụ tại:

~~~text
http://localhost:9090/actuator/health
~~~

Không nên gọi cổng `8080` rồi kết luận endpoint chưa được expose. Khi thay đổi `server.servlet.context-path`, `management.server.base-path` hoặc reverse-proxy routing, đường dẫn cuối còn phụ thuộc cách bố trí management context và proxy.

Quy tắc thực dụng: luôn ghi rõ **host + port + context path + Actuator base path + endpoint mapping** trước khi chẩn đoán một `404`.

## 6. Điều kiện thứ tư: caller phải được phép truy cập

Ngay cả khi endpoint có mặt, được bật và expose qua HTTP, một request vẫn có thể bị từ chối vì bảo mật.

Đây là nơi cần phân biệt:

- **Authentication:** caller là ai? Có credential, session hoặc token hợp lệ không?
- **Authorization:** caller đó có được xem hoặc thực hiện operation này không?
- **Network reachability:** caller có tới được cổng và route qua firewall, ingress, service mesh hoặc gateway không?
- **Endpoint-level access:** nếu phiên bản hỗ trợ, Actuator có thể giới hạn operation theo `none`, `read-only` hoặc `unrestricted`.

Khi có Spring Security trên classpath và chưa có cấu hình SecurityFilterChain riêng, Spring Boot có thể tự cấu hình bảo vệ Actuator theo default của auto-configuration. Một khi ứng dụng tự định nghĩa SecurityFilterChain, cần hiểu rõ phạm vi các chain: Boot thường nhường việc cấu hình web security cho ứng dụng.

**Exposure không thay thế security.** Nếu không có lớp bảo mật hoặc hạn chế mạng phù hợp, endpoint đã expose có thể trở thành endpoint công khai.

## 7. Ví dụ bảo vệ endpoint bằng Spring Security

Giả sử ứng dụng cần công khai health probe cho hệ thống điều phối, nhưng chỉ người vận hành có role `OPS` được đọc các endpoint Actuator còn lại.

Cấu hình exposure:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,loggers
  endpoint:
    health:
      show-details: when-authorized
~~~

Cấu hình Spring Security minh họa cho ứng dụng servlet với một SecurityFilterChain:

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
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers(EndpointRequest.to("health"))
                    .permitAll()
                .requestMatchers(EndpointRequest.toAnyEndpoint())
                    .hasRole("OPS")
                .anyRequest()
                    .authenticated()
        );

        http.httpBasic(Customizer.withDefaults());
        return http.build();
    }
}
~~~

Đây là ví dụ nguyên lý authorization. Ứng dụng thực tế vẫn cần cấu hình nguồn xác thực, cách cung cấp role `OPS`, cơ chế bảo vệ API nghiệp vụ và chính sách CSRF phù hợp.

Kết quả mong đợi theo logic:

| Request | Điều kiện | Kết quả điển hình |
|---|---|---|
| GET `/actuator/health` | Endpoint được expose và được permitAll | Cho phép không cần đăng nhập |
| GET `/actuator/metrics` | Chưa xác thực | `401` hoặc phản hồi yêu cầu xác thực |
| GET `/actuator/metrics` | Đã xác thực nhưng thiếu `ROLE_OPS` | `403` |
| GET `/actuator/metrics` | Có `ROLE_OPS` | Được chuyển tới endpoint |
| GET `/actuator/env` | Không nằm trong exposure | Thường không có mapping HTTP, bất kể role |

Spring Security thường có thể được tích hợp với `EndpointRequest` để chọn endpoint theo ID thay vì hard-code URL. Điều này giúp quy tắc theo endpoint không phụ thuộc hoàn toàn vào việc đổi base path.

### Khi có nhiều SecurityFilterChain

Nếu khai báo một chain chỉ áp dụng cho Actuator:

~~~java
http.securityMatcher(EndpointRequest.toAnyEndpoint());
~~~

chain đó **không** bao phủ tất cả URL nghiệp vụ. Cần có chain khác cho API ứng dụng nếu ứng dụng dựa vào Spring Security để bảo vệ chúng. Không nên tạo một chain chỉ cho Actuator rồi vô tình để các endpoint nghiệp vụ ngoài vùng kiểm soát.

Trong WebFlux, security dùng cơ chế `SecurityWebFilterChain` thay vì `SecurityFilterChain` của Servlet API. Ví dụ trên dành cho ứng dụng Spring MVC/Servlet.

### HTTP write operation và CSRF

Một số endpoint có operation ghi, ví dụ thay đổi mức log. Ngay cả người dùng đã xác thực và được phân quyền cũng có thể nhận `403` khi gửi POST nếu yêu cầu CSRF token mà request không cung cấp.

Không nên tắt CSRF toàn bộ ứng dụng chỉ để một endpoint quản trị hoạt động. Hãy thiết kế authentication, CSRF và quyền thực thi operation theo mô hình bảo mật thực tế.

## 8. Ví dụ kiểm tra bốn điều kiện với metrics

Giả sử cần truy cập:

~~~text
GET http://localhost:8080/actuator/metrics
~~~

Một chuỗi kiểm tra hữu ích là:

**Bước 1 — Endpoint tồn tại?** Ứng dụng có Actuator dependency và metric infrastructure liên quan không? Có điều kiện auto-configuration nào khiến endpoint không được đăng ký không?

**Bước 2 — Endpoint được bật/cấp access?** Với phiên bản đang dùng, cấu hình `management.endpoint.metrics.enabled` hoặc `management.endpoint.metrics.access` có cho phép endpoint không? Có default deny hoặc max-permitted không?

**Bước 3 — Expose qua HTTP?** `management.endpoints.web.exposure.include` có chứa `metrics` không? Có `exclude` ghi đè? Đường dẫn, port và base path có đúng không?

**Bước 4 — Caller được phép?** SecurityFilterChain có cho user/token hiện tại truy cập endpoint không? Ingress có cho kết nối tới management port không?

Ví dụ cấu hình đơn giản cho phiên bản Spring Boot hỗ trợ mô hình access:

~~~yaml
management:
  endpoints:
    access:
      default: none
    web:
      exposure:
        include: health,metrics
  endpoint:
    health:
      access: read-only
    metrics:
      access: read-only
~~~

Cấu hình này cho phép `health` và `metrics` được sử dụng để đọc và được expose qua HTTP; nó **chưa** tự cấu hình authentication hoặc role-based authorization.

Nếu dự án dùng phiên bản Spring Boot cũ với cơ chế `enabled`, cần thay phần access bằng cấu hình tương ứng được phiên bản đó hỗ trợ.

## 9. 404, 401, 403, 405 và 503 có nghĩa gì?

Một mã HTTP không luôn xác định duy nhất nguyên nhân, nhưng giúp thu hẹp phạm vi kiểm tra.

| HTTP status | Ý nghĩa thường gặp | Việc cần kiểm tra |
|---|---|---|
| `404 Not Found` | Không có mapping cho URL đang gọi hoặc có thành phần cố ý che giấu tài nguyên | Dependency, enable/access, exposure, port, base path, proxy route |
| `401 Unauthorized` | Chưa xác thực hoặc credential không hợp lệ | Authentication, token, Basic auth, session, security chain |
| `403 Forbidden` | Caller thiếu quyền hoặc request bị cơ chế bảo vệ như CSRF từ chối | Authorization rules, role, CSRF, endpoint operation |
| `405 Method Not Allowed` | URL có thể tồn tại nhưng HTTP method không được hỗ trợ | GET/POST/DELETE, loại operation của endpoint |
| `503 Service Unavailable` | Có thể do health endpoint báo `DOWN`/`OUT_OF_SERVICE`, hoặc do proxy/upstream lỗi | Nội dung response, health contributors, proxy logs |
| `200 OK` | Request đã được xử lý thành công | Không tự chứng minh mọi thông tin nhạy cảm nên được công bố |

Đặc biệt với `health`, một phản hồi HTTP `503` có thể là **endpoint đã tồn tại, đã expose và đã được phép gọi**, nhưng chính health report cho biết ứng dụng không khỏe hoặc không sẵn sàng.

Ví dụ:

~~~text
HTTP/1.1 503 Service Unavailable
Content-Type: application/vnd.spring-boot.actuator.v3+json

{"status":"DOWN"}
~~~

Đây là tình huống khác với `503` do reverse proxy không thể kết nối tới management server. Cần phân biệt dựa trên body, header, log và nơi phản hồi được tạo.

Nếu nhận `404`, không nên lập tức bật `include: "*"`. Hãy xác định xem endpoint có được đăng ký và có đang gọi đúng URL trước khi mở rộng exposure.

## 10. Dùng curl để xác nhận từ ngoài ứng dụng

Có thể gọi endpoint với `curl`:

~~~bash
curl -i http://localhost:8080/actuator/health
curl -i http://localhost:8080/actuator/info
curl -i http://localhost:8080/actuator/metrics
~~~

Tùy cấu hình, một endpoint có thể phản hồi `200`, `401`, `403`, `404` hoặc `503`. Cần nhìn cả HTTP status và response body thay vì chỉ nhìn lệnh có trả dữ liệu hay không.

Nếu dùng HTTP Basic cho operator, có thể để `curl` hỏi mật khẩu:

~~~bash
curl -i -u ops http://localhost:8080/actuator/metrics
~~~

Tránh ghi secret trực tiếp vào lệnh vì terminal history, process listing và log của công cụ vận hành có thể lưu lại.

Khi management server ở cổng riêng, thử đúng URL:

~~~bash
curl -i http://localhost:9090/actuator/health
~~~

Nếu request từ cùng máy thành công nhưng từ máy khác không thành công, vấn đề có thể nằm ở bind address, firewall, ingress hoặc policy mạng, chứ không phải availability của endpoint trong Spring.

## 11. Discovery page không phải danh sách đầy đủ mọi endpoint

Khi bật HTTP exposure và discovery page theo cấu hình tương ứng, đường dẫn base path (thường là `/actuator`) có thể cung cấp danh sách liên kết tới các endpoint web đang được công bố.

Ví dụ:

~~~text
GET /actuator
~~~

Nhưng có một số giới hạn:

- Danh sách chỉ thể hiện các endpoint được discovery cho transport đó, không phải mọi endpoint trong source code.
- Endpoint không expose qua HTTP sẽ không được liệt kê ở đó.
- Có thể tắt discovery page bằng `management.endpoints.web.discovery.enabled=false`.
- Endpoint có mapping ở cổng hoặc base path khác có thể không xuất hiện tại URL mà caller đang kiểm tra.
- Bảo mật có thể chặn việc xem trang discovery.

Vì vậy, không thấy `metrics` trên `/actuator` không tự chứng minh endpoint bean hoàn toàn không tồn tại. Ngược lại, thấy một liên kết cũng không bảo đảm caller có quyền xem nội dung sau khi mở liên kết đó.

## 12. Quyền xem chi tiết khác quyền gọi health

Một endpoint đã được phép truy cập không có nghĩa người dùng được xem toàn bộ dữ liệu mà endpoint biết.

Ví dụ với health:

~~~yaml
management:
  endpoint:
    health:
      show-details: when-authorized
      roles: OPS
~~~

Cấu hình trên điều khiển **mức độ thông tin health được hiển thị** cho caller được xem là authorized theo cơ chế health detail của Actuator. Nó không thay thế SecurityFilterChain và cũng không tự tạo principal có role `OPS`.

Một request có thể được phép gọi `/actuator/health`, nhưng chỉ nhận:

~~~json
{"status":"UP"}
~~~

trong khi operator có quyền thích hợp nhận thêm component details. Các trạng thái, nội dung và điều kiện hiển thị thực tế phụ thuộc phiên bản Spring Boot và health group configuration.

Tương tự, `env` và `configprops` có khả năng chứa cấu hình nhạy cảm. Các thuộc tính `show-values` và cơ chế sanitization của Actuator cần được cấu hình theo phiên bản đang dùng, song song với việc hạn chế exposure và authorization.

**Giảm dữ liệu trả về** và **hạn chế người được xem** là hai lớp bảo vệ bổ sung, không thay thế nhau.

## 13. Read-only không có nghĩa endpoint không có tác động

Ở mô hình endpoint access hiện đại, `read-only` giới hạn operation theo loại thao tác của Actuator. Nó không phải một bảo đảm rằng mọi yêu cầu GET luôn nhẹ, an toàn về tài nguyên hoặc không tiết lộ thông tin.

Ví dụ:

- `threaddump` là thao tác đọc nhưng có thể cung cấp thông tin runtime chi tiết.
- `env` cho biết các property source và metadata cấu hình.
- `metrics` có thể tiết lộ thông tin hệ thống nếu triển khai công khai không phù hợp.
- Một custom `@ReadOperation` do ứng dụng tự viết có thể thực hiện tác vụ tốn thời gian.

Bởi vậy, khi chọn endpoint expose, vẫn cần đánh giá **độ nhạy thông tin, chi phí xử lý và đối tượng được phép gọi**.

Ngược lại, với `loggers`, việc đọc danh sách logger khác với việc thay mức log runtime. Một cấu hình chỉ cho phép đọc không nên được hiểu là đồng thời cho phép thao tác ghi.

Nếu cần operation ghi, hãy kết hợp access cho phép đúng mức với Security authorization và chính sách bảo vệ yêu cầu ghi. Đừng bật `unrestricted` cho mọi endpoint chỉ để một thao tác quản trị riêng hoạt động.

## 14. Endpoint shutdown: ví dụ ranh giới bảo mật quan trọng

`shutdown` là ví dụ giúp thấy rõ sự khác nhau giữa tồn tại, enable/access, expose và authorization.

Ngay cả khi actuator starter có hạ tầng shutdown endpoint, Spring Boot không mặc định mở chức năng dừng ứng dụng cho mọi HTTP caller. Muốn cho phép một thao tác shutdown cần đáp ứng chính xác những điều kiện mà phiên bản Boot và cấu hình deploy yêu cầu.

Các câu hỏi cần xem xét:

1. Endpoint shutdown có được hỗ trợ và được đăng ký không?
2. Cấu hình enable/access có cho phép operation cần thiết không?
3. Endpoint có được expose qua HTTP không?
4. Security có cho phép caller được ủy quyền thực hiện thao tác ghi không?
5. Phương thức HTTP và CSRF policy có phù hợp không?
6. Việc dừng ứng dụng có phối hợp với orchestrator, health probes và graceful shutdown không?

Trong production, thông thường nên dùng cơ chế dừng tiến trình của hệ thống điều phối thay vì mở endpoint shutdown qua mạng. Điều này giảm bề mặt tấn công và giúp shutdown theo đúng vòng đời quản trị ứng dụng.

## 15. Tác động của reverse proxy và management port

Khi ứng dụng đứng sau gateway hoặc ingress, câu chuyện không kết thúc tại Spring Boot.

Ví dụ topology:

~~~text
Client / monitoring agent
           |
           v
     Ingress / gateway
           |
           +--> :8080 application API
           |
           +--> :9090 management server
                     |
                     v
                /actuator/*
~~~

Một request có thể bị từ chối hoặc không tới được management server vì:

- Ingress không khai báo route cho management port.
- Firewall hoặc network policy chỉ cho kết nối từ monitoring namespace.
- Management server chỉ bind vào loopback hoặc một interface riêng.
- Proxy rewrite path khác với `management.endpoints.web.base-path`.
- TLS termination hoặc authentication ở gateway không phù hợp.
- Gateway cố ý trả `404` để không tiết lộ endpoint.

Do đó, khi có sự khác biệt giữa `curl localhost` và request qua domain public, hãy kiểm tra lần lượt đường đi qua proxy, routing và chính sách mạng. Đừng đổi cấu hình Actuator một cách mù quáng nếu endpoint đã hoạt động đúng ở bên trong.

### Health probe nên đi qua đường dẫn nào?

Nếu management server chạy ở cổng tách biệt, health endpoint trên cổng management có thể vẫn thành công trong khi web server chính gặp vấn đề. Với một số hệ thống, nên công bố thêm probe trên cổng ứng dụng, tùy khả năng phiên bản Boot:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
~~~

Các đường dẫn bổ sung thường là `/livez` và `/readyz` trên cổng chính. Nhưng phải kiểm tra routing thực tế, đặc biệt khi ứng dụng có context path hoặc lớp proxy.

Đây là bài toán xác nhận **đúng đường đi của health request**, không chỉ xác nhận health endpoint tồn tại.

## 16. Các tình huống chẩn đoán thực tế

### Tình huống A: health gọi được, metrics trả 404

Khả năng thường gặp là `health` đã được expose mặc định còn `metrics` chưa nằm trong danh sách HTTP exposure.

Kiểm tra:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics
~~~

Nếu vẫn `404`, kiểm tra tiếp endpoint access/enable, dependency, base path và cổng management. Đừng kết luận ngay rằng Spring Security chặn request, vì security thường phản hồi `401` hoặc `403` khi ngăn theo authentication/authorization, dù cách cấu hình thực tế có thể khác.

### Tình huống B: metrics trả 401

Đây thường là dấu hiệu request đã tới một vùng được bảo vệ nhưng caller chưa xác thực. Cung cấp credential hợp lệ hoặc cấu hình authorization của monitoring client theo chính sách hệ thống.

Không nên vội mở public `metrics` để xóa lỗi `401`.

### Tình huống C: metrics trả 403 dù đã đăng nhập

Cần kiểm tra role, authority và SecurityFilterChain. Nếu request là POST/DELETE tới một operation quản trị, kiểm tra thêm CSRF và quyền operation.

Role `OPS` trong code với `hasRole("OPS")` thường kiểm tra authority `ROLE_OPS`. Cần đảm bảo hệ thống xác thực phát đúng authority đó.

### Tình huống D: prometheus không có dù đã include

Kiểm tra dependency Micrometer Prometheus registry. Một tên endpoint có trong danh sách include không tạo ra integration bị thiếu.

Sau khi registry có mặt, kiểm tra tiếp quyền access/enable, HTTP exposure, URL và security.

### Tình huống E: /actuator trả 404 nhưng /actuator/health vẫn trả 200

Discovery page có thể bị tắt hoặc route base path không công bố danh sách liên kết. Không nên suy luận rằng mọi endpoint đã biến mất. Thử trực tiếp đường dẫn endpoint cần thiết và xác nhận cấu hình `management.endpoints.web.discovery.enabled`.

### Tình huống F: health trả 503 khi database lỗi

Nếu response do Actuator health endpoint sinh ra với status `DOWN`, đây là kết quả **health check**, không nhất thiết là lỗi endpoint không tồn tại hoặc thiếu quyền.

Cần xem các health contributor, policy mapping health status sang HTTP và đánh giá sự khác nhau giữa liveness/readiness. Một dependency ngoài bị lỗi không nhất thiết phải làm liveness probe thất bại.

### Tình huống G: cùng cấu hình nhưng môi trường khác cho kết quả khác

Kiểm tra active profile, biến môi trường, tham số dòng lệnh, file cấu hình ngoài JAR và dependency thực tế ở từng môi trường. Một property có thể bị nguồn ưu tiên cao hơn ghi đè.

Khi ứng dụng dùng nhiều management context, việc cùng một URL đi tới cổng hoặc context khác cũng có thể gây hiểu nhầm.

## 17. Một cấu hình quan sát tối thiểu, có chủ đích

Với ứng dụng cần health cho hệ thống điều phối và metrics cho hệ thống monitoring, có thể bắt đầu bằng exposure tối thiểu:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
  endpoint:
    health:
      show-details: never
~~~

Cấu hình này chưa cung cấp chính sách authorization; cần bảo vệ `metrics` và `info` theo mức độ nhạy và nhu cầu hệ thống, thông qua Spring Security, giới hạn mạng hoặc cả hai.

Nếu dùng phiên bản hỗ trợ access model và muốn chỉ cho phép operation đọc:

~~~yaml
management:
  endpoints:
    access:
      default: none
    web:
      exposure:
        include: health,info,metrics
  endpoint:
    health:
      access: read-only
    info:
      access: read-only
    metrics:
      access: read-only
~~~

Trong môi trường cần operation `loggers` hoặc endpoint quản trị khác, hãy cấu hình riêng endpoint đó thay vì mở toàn bộ mọi operation.

Một nguyên tắc triển khai dễ duy trì là:

- **Expose ít endpoint nhất đáp ứng yêu cầu quan sát.**
- **Ưu tiên quyền đọc khi không cần thao tác ghi.**
- **Xác thực và phân quyền theo identity đối với dữ liệu nội bộ.**
- **Giới hạn cổng management bằng network policy, gateway hoặc private network.**
- **Không đưa secret hoặc thông tin nhạy cảm vào response.**
- **Kiểm tra endpoint từ đúng đường đi của monitoring client.**

## 18. Quy trình kiểm tra bốn điều kiện

Khi một Actuator endpoint không hoạt động, hãy đi theo thứ tự:

1. Xác nhận phiên bản Spring Boot và dependency của Actuator/endpoint cụ thể.
2. Xác nhận endpoint có khả năng được đăng ký trong ApplicationContext; kiểm tra các điều kiện auto-configuration cần thiết.
3. Kiểm tra cơ chế bật endpoint tương ứng phiên bản: `enabled` truyền thống hoặc `access` hiện đại.
4. Kiểm tra operation cần gọi có bị giới hạn bởi `read-only` hay `max-permitted` không.
5. Kiểm tra exposure của transport đang dùng, phân biệt HTTP với JMX.
6. Kiểm tra `include`, `exclude`, base path, path mapping, context path và management port.
7. Kiểm tra request có tới được ứng dụng qua firewall, service, ingress và gateway không.
8. Kiểm tra authentication, authorization và, với operation ghi, CSRF.
9. Dựa vào HTTP status và body để phân biệt không có mapping, bị chặn và endpoint trả trạng thái nghiệp vụ như health `DOWN`.
10. Nếu kết quả giữa môi trường khác nhau, xác định property sources và profile đã có hiệu lực thật sự.

Điểm then chốt là **tồn tại, bật, expose và được phép truy cập không phải một trạng thái duy nhất**. Một endpoint có thể được triển khai đầy đủ nhưng không có mapping HTTP, có mapping nhưng bị Security từ chối, hoặc được gọi thành công nhưng báo health `DOWN`. Tách đúng từng điều kiện giúp mở quyền quan sát có chủ đích, tránh expose quá mức và chẩn đoán sự cố Spring Boot Actuator nhanh, chính xác hơn.

