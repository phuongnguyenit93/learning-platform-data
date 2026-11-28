# Giới hạn quyền đọc Actuator

## Mục tiêu học tập

Trong học phần **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY**, Spring Modulith giúp mô tả ranh giới application module và quan sát tương tác giữa các phần trong ứng dụng Spring Boot. Actuator cung cấp endpoint quản trị để kiểm tra health, metrics, cấu hình và trạng thái runtime. Những endpoint này có thể tiết lộ thông tin nội bộ hoặc cho phép thay đổi hành vi ứng dụng, vì vậy cần giới hạn quyền đọc và quyền thao tác theo vai trò.

Sau bài học, bạn có thể:

1. Phân biệt endpoint access, exposure, authentication, authorization và network restriction.
2. Dùng access level `none`, `read-only` và `unrestricted` của Spring Boot 4.2.
3. Cấu hình `management.endpoints.access.default` và `management.endpoints.access.max-permitted`.
4. Chỉ expose các Actuator endpoints cần cho health check, metrics và monitoring.
5. Bảo vệ HTTP Actuator endpoints bằng Spring Security và role riêng cho đội vận hành.
6. Hiểu tác động của custom `SecurityFilterChain` lên auto-configuration của Spring Boot.
7. Bảo vệ thông tin nhạy cảm từ `env`, `configprops`, `health`, `heapdump` và endpoint chẩn đoán.
8. Tách management port, giới hạn network access và cấu hình JMX phù hợp.
9. Kiểm tra quyền bằng HTTP requests và kiểm thử tự động.
10. Kết hợp bảo mật Actuator với module graph, metrics và tracing của Spring Modulith.

**Bối cảnh:** Module graph cho biết cấu trúc application module; Actuator cung cấp thông tin runtime; metrics và tracing giúp quan sát hiệu năng, lỗi và tương tác giữa module. Bảo vệ Actuator giúp thông tin vận hành chỉ đến đúng người và hệ thống được phép truy cập.

> **Phạm vi phiên bản:** Các thuộc tính `management.endpoint.<id>.access`, `management.endpoints.access.default` và `management.endpoints.access.max-permitted` được minh họa theo Spring Boot 4.2. Các dòng Spring Boot cũ hơn có thể chưa hỗ trợ access-level model này; khi đó cần dựa vào exposure allowlist và Spring Security. Luôn kiểm tra reference guide theo BOM của dự án.

## 1. Vì sao phải giới hạn quyền đọc Actuator?

Actuator cung cấp endpoint có ích cho vận hành, nhưng dữ liệu trả về có thể tiết lộ:

- tên bean, package, class và cấu trúc ứng dụng;
- mapping HTTP và route nội bộ;
- tên meter, tag và lưu lượng metrics;
- trạng thái database, broker, cache và dependency;
- cấu hình ứng dụng hoặc thông tin môi trường;
- loggers và mức log hiện tại;
- thread dump, heap dump hoặc nội dung log file;
- thông tin session nếu ứng dụng dùng Spring Session.

Một số endpoint còn có thao tác ghi hoặc xóa, ví dụ thay đổi log level, shutdown ứng dụng hoặc xóa session. Nếu mở các endpoint này cho mọi client, người truy cập có thể thu thập thông tin kiến trúc, gây gián đoạn dịch vụ hoặc đọc dữ liệu không cần thiết.

### 1.1. Ví dụ trong ứng dụng Spring Modulith

Giả sử ứng dụng có các module:

~~~text
shop
├── orders
├── inventory
├── payments
└── shipping
~~~

Đội vận hành muốn Prometheus đọc metrics và health checker kiểm tra trạng thái ứng dụng. Họ không cần mọi người dùng API có quyền xem danh sách Spring beans, đọc cấu hình runtime, tải heap dump, thay đổi log level hoặc shutdown service.

Nên tách quyền theo mục đích:

| Chủ thể | Nhu cầu hợp lý |
| --- | --- |
| Load balancer / platform probe | Đọc health endpoint cần thiết. |
| Prometheus | Đọc endpoint metrics đã expose. |
| Developer / operator | Đọc endpoint chẩn đoán được cấp quyền. |
| Administrator | Thao tác quản trị đặc biệt nếu quy trình cho phép. |
| API client thông thường | Không có quyền truy cập Actuator nội bộ. |

## 2. Năm lớp cần phân biệt

Bảo vệ Actuator hiệu quả cần hiểu các lớp khác nhau:

| Lớp | Câu hỏi | Cơ chế |
| --- | --- | --- |
| **Endpoint access** | Endpoint có được phép hoạt động và cung cấp operation nào? | `management.endpoint.<id>.access`, `management.endpoints.access.*`. |
| **Exposure** | Endpoint có được xuất qua HTTP hoặc JMX không? | `management.endpoints.web.exposure.*`, `management.endpoints.jmx.exposure.*`. |
| **Authentication** | Ai đang gửi request? | HTTP Basic, OAuth2 Resource Server, LDAP, OIDC hoặc identity provider. |
| **Authorization** | Người đã đăng nhập có quyền gì? | Role/authority trong Spring Security. |
| **Network boundary** | Kết nối đến management server có được phép từ nguồn đó không? | Management port/address, firewall, security group, Kubernetes NetworkPolicy, mTLS. |

Một endpoint có thể được cho phép ở lớp access nhưng không expose qua HTTP. Ngược lại, endpoint đã expose vẫn có thể yêu cầu authentication/authorization. Management port riêng cũng không tự tạo ra role hoặc kiểm tra danh tính.

~~~mermaid
flowchart TD
    A["HTTP request tới /actuator/..."] --> B{"Network cho phép kết nối?"}
    B -->|"Không"| X["Chặn ở firewall / network policy"]
    B -->|"Có"| C{"Endpoint được expose?"}
    C -->|"Không"| Y["Không có route HTTP"]
    C -->|"Có"| D{"Endpoint access cho phép?"}
    D -->|"Không"| Z["Endpoint không khả dụng"]
    D -->|"Có"| E{"Authentication hợp lệ?"}
    E -->|"Không"| U["401 Unauthorized"]
    E -->|"Có"| F{"Có role/authority?"}
    F -->|"Không"| V["403 Forbidden"]
    F -->|"Có"| G["Thực thi read operation được phép"]
~~~

## 3. Access level trong Spring Boot 4.2

Spring Boot 4.2 cung cấp ba access levels:

| Access level | Ý nghĩa |
| --- | --- |
| `none` | Không cho phép endpoint access. Endpoint không khả dụng và bị loại khỏi application context. |
| `read-only` | Chỉ cho phép các thao tác đọc. |
| `unrestricted` | Cho phép các thao tác mà endpoint hỗ trợ, gồm read/write/delete nếu có. |

Mặc định, access của phần lớn endpoint là unrestricted; `shutdown` và `heapdump` có mặc định riêng hạn chế hơn. Nếu muốn chính sách opt-in, nên khai báo rõ endpoint nào được phép hoạt động.

### 3.1. Read-only có nghĩa gì?

Với endpoint dựa trên `@Endpoint`, `@JmxEndpoint` hoặc `@WebEndpoint`:

- thao tác đọc là method có `@ReadOperation`;
- thao tác ghi là method có `@WriteOperation`;
- thao tác xóa là method có `@DeleteOperation`.

Với `@ControllerEndpoint` và `@RestControllerEndpoint`, read-only tương ứng với request mapping xử lý `GET` và `HEAD`. Với `@ServletEndpoint`, read-only cũng tương ứng `GET` và `HEAD`.

Vì vậy, endpoint `loggers` có thể cho phép đọc logger levels nhưng không cho phép thay đổi level qua operation ghi khi access bị giới hạn ở read-only.

### 3.2. Read-only không có nghĩa dữ liệu luôn an toàn

Một endpoint GET có thể trả về thông tin nhạy cảm. Ví dụ:

- `env` và `configprops` có thể mô tả cấu hình;
- `beans` tiết lộ cấu trúc nội bộ;
- `mappings` tiết lộ route;
- `heapdump` có thể chứa dữ liệu trong bộ nhớ;
- `logfile` có thể chứa thông tin cá nhân hoặc token bị ghi nhầm;
- `prometheus` có thể tiết lộ tên module, dependency và hoạt động hệ thống.

Do đó, read-only giới hạn **khả năng thay đổi trạng thái**, không thay thế authentication, authorization, sanitization và network isolation.

## 4. Dùng max-permitted để giới hạn toàn ứng dụng

Thuộc tính:

~~~yaml
management:
  endpoints:
    access:
      max-permitted: read-only
~~~

đặt mức quyền tối đa cho tất cả Actuator endpoints. Nó có độ ưu tiên cao hơn access mặc định hoặc access riêng của từng endpoint.

Có thể hiểu:

- `max-permitted: none`: không endpoint nào khả dụng;
- `max-permitted: read-only`: tối đa chỉ đọc;
- `max-permitted: unrestricted`: không đặt trần thấp hơn ở cấp ứng dụng.

Nếu một endpoint riêng được cấu hình `unrestricted` nhưng `max-permitted` là `read-only`, quyền thực tế vẫn bị giới hạn ở read-only.

### 4.1. Access default theo hướng opt-in

Để mặc định từ chối tất cả endpoint rồi mở từng endpoint cần thiết:

~~~yaml
management:
  endpoints:
    access:
      default: none
      max-permitted: read-only
    web:
      exposure:
        include: "health,metrics,prometheus"
  endpoint:
    health:
      access: read-only
    metrics:
      access: read-only
    prometheus:
      access: read-only
~~~

Trong ví dụ:

- `default: none` khiến endpoint không được khai báo riêng không khả dụng;
- `health`, `metrics` và `prometheus` được bật ở mức read-only;
- `max-permitted: read-only` bảo đảm không endpoint nào vượt quá quyền đọc;
- `exposure.include` chỉ đưa ba endpoint đó ra HTTP.

Endpoint `prometheus` cần dependency `micrometer-registry-prometheus`. Nếu ứng dụng không dùng Prometheus, bỏ endpoint này khỏi allowlist.

## 5. Exposure là lớp riêng với access

Mặc định Spring Boot chỉ expose endpoint `health` qua HTTP và JMX. Muốn thêm endpoint phải cấu hình `include` hoặc `exclude`.

Ví dụ chỉ expose health và metrics qua HTTP:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,metrics"
~~~

Nếu muốn loại một endpoint khỏi danh sách dù nó có trong include:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "*"
        exclude: "env,beans,heapdump,logfile"
~~~

Thuộc tính `exclude` có ưu tiên cao hơn `include`. Ký tự `*` trong YAML phải đặt trong dấu nháy.

### 5.1. Không dùng include all như cấu hình mặc định

Mở tất cả endpoint có thể tạo ra bề mặt quản trị lớn. Nếu cần một endpoint mới, hãy thêm đúng ID vào allowlist và review dữ liệu nó trả về.

Ví dụ một monitoring agent chỉ cần:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,prometheus"
~~~

Không cần expose `env`, `beans`, `mappings`, `loggers`, `heapdump` hoặc `shutdown` cho Prometheus.

### 5.2. Access và exposure có quan hệ thế nào?

Một endpoint chỉ khả dụng khi access được cho phép **và** endpoint được expose qua công nghệ tương ứng. `access: read-only` không tự làm endpoint xuất hiện trên HTTP; `exposure.include` cũng không tự cấp quyền cho người dùng.

| Access | HTTP exposure | Kết quả |
| --- | --- | --- |
| `none` | Có trong include | Endpoint vẫn không khả dụng. |
| `read-only` | Không trong include | Không truy cập qua HTTP. |
| `read-only` | Có trong include | Có thể gọi thao tác đọc nếu security/network cho phép. |
| `unrestricted` | Có trong include | Endpoint có thể cung cấp mọi operation mà endpoint hỗ trợ, subject to security. |

## 6. Cấu hình tối thiểu cho monitoring chỉ đọc

Một ví dụ cho service cần health và Prometheus:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
~~~

Cấu hình:

~~~yaml
management:
  endpoints:
    access:
      default: none
      max-permitted: read-only
    web:
      exposure:
        include: "health,prometheus"
  endpoint:
    health:
      access: read-only
      show-details: never
    prometheus:
      access: read-only
~~~

Cấu hình này tập trung vào hai nhu cầu: health endpoint phục vụ probe và Prometheus endpoint phục vụ scrape. Prometheus scrape credentials/network access cần được cấu hình ở hạ tầng. Nếu dùng Spring Security, endpoint vẫn cần được bảo vệ theo policy phù hợp.

### 6.1. Khi cần thêm metrics diagnostics

Endpoint `metrics` hữu ích khi developer kiểm tra meter của một instance:

~~~yaml
management:
  endpoints:
    access:
      default: none
      max-permitted: read-only
    web:
      exposure:
        include: "health,metrics,prometheus"
  endpoint:
    health:
      access: read-only
    metrics:
      access: read-only
    prometheus:
      access: read-only
~~~

Chỉ mở `metrics` cho nhóm vận hành nếu có nhu cầu. Nó cung cấp tên meter và các tag/measurement, có thể tiết lộ một phần cấu trúc ứng dụng.

## 7. Bảo vệ Actuator bằng Spring Security

Access-level properties không xác định **ai** được đọc endpoint. Để giới hạn theo người dùng hoặc service account, dùng Spring Security.

Khi `spring-boot-starter-security` có trên classpath và chưa có custom `SecurityFilterChain`, Spring Boot tự bảo vệ các Actuator endpoints khác `health`. Nếu ứng dụng khai báo custom `SecurityFilterChain`, auto-configuration security mặc định của Boot sẽ nhường quyền kiểm soát cho cấu hình của ứng dụng.

### 7.1. Dependency

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

### 7.2. Phân quyền theo role trong Spring Boot 4.2

Ví dụ sau yêu cầu role `ACTUATOR_READER` cho mọi Actuator endpoint ngoại trừ health, endpoint health được cho phép truy cập không cần đăng nhập:

~~~java
package com.example.shop.security;

import org.springframework.boot.security.autoconfigure.actuate.web.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
class ActuatorSecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain actuatorSecurity(HttpSecurity http) throws Exception {
        http.securityMatcher(EndpointRequest.toAnyEndpoint())
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(EndpointRequest.to("health")).permitAll()
                .anyRequest().hasRole("ACTUATOR_READER"))
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationSecurity(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(authorize -> authorize
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Giải thích:

- `EndpointRequest.toAnyEndpoint()` tạo matcher theo Actuator endpoint mapping, kể cả khi base path thay đổi.
- `EndpointRequest.to("health")` khớp endpoint health và các subpaths của nó.
- `hasRole("ACTUATOR_READER")` yêu cầu authority `ROLE_ACTUATOR_READER`.
- `@Order(1)` đặt chain Actuator trước chain ứng dụng.
- Chain thứ hai áp dụng cho request còn lại của ứng dụng.

Đây là ví dụ Spring MVC/Servlet theo package Spring Boot 4.2. Nếu ứng dụng đã có cấu hình OAuth2 Resource Server, form login hoặc policy riêng, hãy tích hợp matcher Actuator vào cấu trúc hiện có và giữ nguyên các quy tắc bảo vệ application routes. Với WebFlux, dùng `SecurityWebFilterChain` và matcher reactive tương ứng.

### 7.3. Vì sao cần chain thứ hai?

Khi có custom `SecurityFilterChain` bean, Spring Boot security auto-configuration không còn tự tạo toàn bộ policy mặc định. Nếu chỉ khai báo chain có matcher `EndpointRequest.toAnyEndpoint()`, các request ngoài Actuator không được chain đó xử lý.

Vì vậy cần một chain khác cho phần ứng dụng, hoặc điều chỉnh cấu hình bảo mật hiện có để bao phủ toàn bộ routes. Không để một khoảng trống authorization khi thêm cấu hình riêng cho Actuator.

### 7.4. Tài khoản vận hành

Role `ACTUATOR_READER` phải được cấp từ authentication provider mà ứng dụng sử dụng, ví dụ identity provider/SSO, LDAP, OAuth2 Resource Server với scope/authority được ánh xạ, service account dành riêng cho monitoring hoặc user store nội bộ trong môi trường phát triển.

Không dùng tài khoản quản trị chung cho Prometheus, developer và health probe. Không commit mật khẩu thật vào repository hoặc `application.yml`.

## 8. Đọc health nhưng giới hạn chi tiết

Health endpoint thường cần cho load balancer hoặc platform probe. Tuy nhiên, health details có thể tiết lộ tên dependency, trạng thái database, broker hoặc thông tin nội bộ.

Cấu hình mặc định an toàn:

~~~yaml
management:
  endpoint:
    health:
      show-details: never
      show-components: never
~~~

Nếu đội vận hành cần xem chi tiết sau khi xác thực:

~~~yaml
management:
  endpoint:
    health:
      show-details: when-authorized
      show-components: when-authorized
      roles: "ACTUATOR_READER"
~~~

Với `when-authorized`, Spring Boot chỉ hiển thị details/components cho người dùng đã xác thực và có một trong các role được cấu hình. Nếu không khai báo roles, mọi authenticated user có thể được coi là authorized cho phần chi tiết theo cấu hình mặc định.

Không bật `always` trên endpoint health có thể truy cập công khai nếu details chứa tên host, dependency hoặc thông tin triển khai không cần thiết.

## 9. Sanitization cho env và configprops

Các endpoint `env`, `configprops` và `quartz` có thể trả về giá trị nhạy cảm. Spring Boot mặc định sanitize các giá trị này thành `******`.

Có ba lựa chọn `show-values`:

| Giá trị | Hành vi |
| --- | --- |
| `never` | Luôn che giá trị. |
| `always` | Hiển thị cho mọi người có quyền truy cập endpoint, nếu không có `SanitizingFunction` khác áp dụng. |
| `when-authorized` | Chỉ hiển thị cho người dùng đã xác thực và có role phù hợp. |

Ví dụ chỉ role `ACTUATOR_ADMIN` được xem giá trị gốc ở endpoint `env`:

~~~yaml
management:
  endpoint:
    env:
      show-values: when-authorized
      roles: "ACTUATOR_ADMIN"
~~~

Cấu hình trên không tự expose endpoint `env`; vẫn phải quyết định có thêm nó vào exposure allowlist hay không. Nếu không có nhu cầu điều tra giá trị cấu hình, giữ `show-values: never` và không expose endpoint này.

### 9.1. Sanitization không thay thế quyền truy cập

Ngay cả khi giá trị đã được che, endpoint vẫn có thể tiết lộ tên property, nguồn cấu hình, profile hoặc cấu trúc deployment. Chỉ expose `env`/`configprops` khi có nhu cầu rõ và role phù hợp.

Có thể đăng ký `SanitizingFunction` để bổ sung quy tắc che các key nhạy cảm riêng của ứng dụng. Cần kiểm thử cả tên property, biến môi trường và nguồn cấu hình tùy chỉnh.

## 10. Endpoint nào cần thận trọng?

| Endpoint | Thông tin/tác động | Cách tiếp cận |
| --- | --- | --- |
| `health` | Trạng thái ứng dụng và dependency details. | Có thể expose cho probe; mặc định ẩn details. |
| `info` | Build, git hoặc metadata tùy ứng dụng cung cấp. | Chỉ expose các field không nhạy cảm. |
| `metrics` | Tên meter, measurements và tags. | Chỉ cho monitoring/operator cần thiết. |
| `prometheus` | Toàn bộ metrics được export. | Cho phép scrape từ monitoring network/service account. |
| `beans` | Danh sách bean và cấu trúc Spring context. | Hạn chế cho diagnostics. |
| `conditions` | Điều kiện auto-configuration và lý do match. | Chỉ operator/developer. |
| `mappings` | HTTP routes và handler mappings. | Không expose công khai. |
| `env` | Property và nguồn cấu hình. | Giữ sanitization; hạn chế role. |
| `configprops` | Các `@ConfigurationProperties`. | Giữ sanitization; hạn chế role. |
| `loggers` | Đọc và thay đổi log levels. | Nếu chỉ cần xem, giới hạn read-only. |
| `threaddump` | Stack traces của thread. | Hạn chế truy cập và retention. |
| `heapdump` | Snapshot bộ nhớ có thể chứa dữ liệu runtime nhạy cảm. | Không expose HTTP rộng rãi. |
| `logfile` | Nội dung log file. | Bảo vệ như dữ liệu vận hành có thể chứa PII/secret. |
| `sessions` | Đọc/xóa session nếu Spring Session được dùng. | Quyền rất hạn chế; không mở cho monitoring. |
| `shutdown` | Yêu cầu tắt ứng dụng. | Disabled mặc định; không expose cho reader. |

### 10.1. Read-only vẫn có thể nhạy cảm

`heapdump` là thao tác đọc theo HTTP GET nhưng có thể chứa nội dung bộ nhớ như token, object nghiệp vụ hoặc dữ liệu cá nhân. `read-only` không biến endpoint này thành dữ liệu công khai an toàn.

Với endpoint có mức độ nhạy cảm cao, hãy dùng `access: none` hoặc không expose qua HTTP, đồng thời chỉ cho phép quy trình thu thập có kiểm soát khi thực sự cần.

## 11. Giới hạn thao tác ghi bằng max-permitted

Một ứng dụng có thể expose endpoint `loggers` để operator đọc logger levels. Nếu chỉ muốn đọc, dùng:

~~~yaml
management:
  endpoints:
    access:
      max-permitted: read-only
  endpoint:
    loggers:
      access: read-only
~~~

`max-permitted` đặt trần read-only cho mọi endpoint; cấu hình riêng `loggers.access` thể hiện rõ ý định ở endpoint này.

Các thao tác ghi như thay đổi log level hoặc thao tác xóa không được phép ở access level read-only. Nếu một endpoint không có read operation thì read-only có thể khiến endpoint đó không khả dụng.

### 11.1. Shutdown cần được giữ disabled

Endpoint `shutdown` bị disabled mặc định. Không bật chỉ để thử nghiệm trên một service đang phục vụ traffic. Nếu có quy trình graceful shutdown, ưu tiên cơ chế orchestrator/platform và lifecycle quản trị phù hợp.

### 11.2. CSRF và thao tác thay đổi trạng thái

Spring Security bật CSRF protection mặc định. Các Actuator operations dùng `POST`, `PUT` hoặc `DELETE` có thể trả 403 nếu request không có CSRF token hợp lệ. `read-only` cũng loại bỏ khả năng thực hiện write operations ở tầng endpoint access.

Không tắt CSRF toàn cục chỉ để làm một endpoint quản trị hoạt động. Nếu service chỉ nhận request từ non-browser clients và cần policy CSRF khác, cấu hình phạm vi cụ thể theo Spring Security reference guide.

## 12. Tách management port và network boundary

Có thể chạy management endpoints trên một port riêng:

~~~yaml
server:
  port: 8080

management:
  server:
    port: 8081
~~~

Nếu management listener chỉ nên nhận kết nối từ loopback:

~~~yaml
management:
  server:
    port: 8081
    address: 127.0.0.1
~~~

Khi bind `127.0.0.1`, chỉ tiến trình có thể truy cập loopback của cùng network namespace mới kết nối được. Prometheus chạy ở pod/container khác sẽ không truy cập được địa chỉ này nếu không có proxy/sidecar phù hợp.

Trong Kubernetes hoặc môi trường container, dùng service/network nội bộ cho monitoring, giới hạn nguồn truy cập bằng NetworkPolicy/firewall, không publish management port ra public ingress và xác thực service account hoặc mTLS nếu nền tảng yêu cầu.

Management port riêng giúp phân tách route/port, nhưng không thay thế authorization. Nếu port đó vẫn được route công khai, Actuator vẫn cần được bảo vệ.

### 12.1. Management SSL

Khi management port riêng, có thể cấu hình TLS riêng bằng `management.server.ssl.*`. Nếu ứng dụng chính dùng HTTPS, hãy quyết định rõ management endpoint có cần TLS độc lập hay được bảo vệ qua một lớp proxy nội bộ.

Không coi việc management server dùng HTTP là an toàn chỉ vì port không phổ biến; network path và trust boundary mới quyết định ai có thể truy cập.

## 13. HTTP exposure và JMX exposure là hai cấu hình

Ví dụ chỉ expose health qua HTTP nhưng mở thêm metrics qua JMX:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health"
    jmx:
      exposure:
        include: "health,metrics"
~~~

Quyền truy cập endpoint có thể áp dụng theo access model; exposure lại được cấu hình riêng cho từng công nghệ. Nếu JMX remote được bật, cần bảo vệ connector, authentication, authorization và network. Không giả định HTTP firewall tự bảo vệ JMX.

## 14. Kiểm tra bằng HTTP requests

Giả sử management server chạy ở `localhost:8081` và đã expose `health,metrics,prometheus`.

### 14.1. Health endpoint

~~~bash
curl -i http://localhost:8081/actuator/health
~~~

Nếu health được permitAll và exposure bật, request có thể trả 200 cùng trạng thái health. Nội dung chi tiết phụ thuộc `show-details` và `show-components`.

### 14.2. Endpoint metrics không có credentials

~~~bash
curl -i http://localhost:8081/actuator/metrics
~~~

Nếu endpoint yêu cầu role và request chưa xác thực, kết quả thường là 401 Unauthorized.

### 14.3. Đọc bằng tài khoản operator

~~~bash
curl -i -u "$ACTUATOR_USER:$ACTUATOR_PASSWORD" \
  http://localhost:8081/actuator/metrics
~~~

Trong môi trường thực, lấy credentials từ secret manager hoặc biến môi trường được bảo vệ. Không ghi password vào lịch sử shell, script commit hoặc log.

### 14.4. Thử thao tác ghi

Nếu endpoint `loggers` được expose và access chỉ read-only, thử request ghi phải không thực hiện thay đổi log level. Kiểm tra response theo mapping của endpoint/version và xác minh logger level vẫn giữ nguyên.

### 14.5. Phân biệt các HTTP status

| Kết quả | Ý nghĩa thường gặp |
| --- | --- |
| 200 | Request được phép và operation hoàn tất. |
| 401 | Chưa xác thực hoặc credentials không hợp lệ. |
| 403 | Đã xác thực nhưng không có authority cần thiết, hoặc CSRF chặn thao tác. |
| 404 | Endpoint không expose/khả dụng hoặc route không tồn tại. |
| 405 | HTTP method không được endpoint hỗ trợ, ví dụ write operation không có trong read-only mapping. |

Không dựa duy nhất vào status code để xác minh policy; hãy kiểm tra endpoint access, exposure, security chain và dữ liệu trả về.

## 15. Kiểm thử quyền Actuator tự động

Nên có test cho ít nhất các trường hợp:

| Người gọi | Request | Kết quả mong đợi |
| --- | --- | --- |
| Anonymous | `GET /actuator/health` | Được phép nếu health được public theo policy. |
| Anonymous | `GET /actuator/metrics` | Bị từ chối nếu endpoint yêu cầu authentication. |
| Authenticated user không có role | `GET /actuator/metrics` | 403. |
| `ACTUATOR_READER` | `GET /actuator/metrics` | 200 nếu endpoint được expose và access read-only. |
| `ACTUATOR_READER` | Write operation của `loggers` | Không thể thay đổi logger level. |
| `ACTUATOR_READER` | `GET /actuator/env` khi env không expose | Không truy cập được. |
| `ACTUATOR_ADMIN` | `GET /actuator/env` với `show-values: when-authorized` | Chỉ thấy giá trị gốc nếu endpoint được expose, role khớp và không có sanitization rule khác che giá trị. |

Có thể dùng Spring Security MockMvc test với `@WithMockUser(roles = "ACTUATOR_READER")` hoặc request post-processors phù hợp. Nếu kiểm tra endpoint thực qua mạng, thêm integration test cho management port và authentication provider.

### 15.1. Kiểm thử cả cấu hình sai

Thử xác nhận:

- `include: "*"` không vô tình xuất hiện trong production profile;
- endpoint nhạy cảm không được expose;
- role reader không thể gọi write operation;
- chain ứng dụng vẫn bảo vệ routes không thuộc Actuator;
- health details không bị lộ;
- `env`/`configprops` vẫn sanitize;
- Prometheus chỉ scrape từ nguồn được phép;
- management port không mở qua public ingress.

## 16. Spring Modulith và thông tin Actuator

Spring Modulith có thể cung cấp module graph hoặc thông tin module qua Actuator integration khi starter/endpoint tương ứng được cấu hình. Module graph có thể tiết lộ tên application modules, cấu trúc package/module, quan hệ dependency và một phần thiết kế nội bộ của hệ thống.

Đây là thông tin hữu ích cho developer và operator, nhưng không nhất thiết cần cho người dùng API hoặc monitoring agent chỉ scrape metrics.

Nếu expose endpoint liên quan đến Modulith, hãy xác định endpoint ID thực tế theo phiên bản starter, thêm ID đó vào allowlist thay vì mở tất cả endpoints, đặt access read-only, yêu cầu role operator/developer và kiểm tra payload không chứa thông tin không nên công khai.

Module entry spans, metrics và tracing backend cũng có thể tiết lộ tên module, method hoặc dependency. Bảo vệ Actuator không tự bảo vệ Zipkin, Prometheus, Grafana, log store hoặc OpenTelemetry Collector; mỗi hệ thống cần policy riêng.

## 17. Khác biệt khi dùng Spring Boot 3.x

Các property access-level trong bài thuộc mô hình Spring Boot 4.2. Với các dòng 3.x chưa có `management.endpoints.access.max-permitted` hoặc `management.endpoint.<id>.access`, không sao chép cấu hình này rồi kỳ vọng nó có tác dụng.

Ở các phiên bản cũ hơn, hãy kết hợp allowlist `management.endpoints.web.exposure.include`, `management.endpoints.web.exposure.exclude`, Spring Security `SecurityFilterChain` và `EndpointRequest`, network restriction/management port, cùng sanitization và health detail properties có sẵn ở release đó.

Package của `EndpointRequest` cũng thay đổi giữa các major version. Trong Spring Boot 4.2, ví dụ Servlet ở bài này dùng:

~~~java
import org.springframework.boot.security.autoconfigure.actuate.web.servlet.EndpointRequest;
~~~

Các dòng Boot 3.x phổ biến dùng package cũ:

~~~java
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
~~~

Hãy xem API Javadoc theo version đang dùng trước khi nâng cấp hoặc copy code.

## 18. Những sai lầm thường gặp

### 18.1. Chỉ đặt read-only rồi nghĩ endpoint đã an toàn

Read-only chỉ giới hạn operation ghi/xóa. Người có quyền GET vẫn có thể đọc thông tin cấu trúc, metrics hoặc heap dump nếu endpoint được expose.

### 18.2. Chỉ cấu hình Spring Security mà quên exposure

Một endpoint không expose qua HTTP không thể được truy cập bằng HTTP dù user có role. Ngược lại, expose không có nghĩa mọi user đều được phép đọc.

### 18.3. Thêm custom SecurityFilterChain nhưng quên application chain

Spring Boot backs off security auto-configuration khi custom chain được khai báo. Cần bảo vệ cả Actuator và application routes.

### 18.4. Dùng include all cho tiện

Mở tất cả endpoints có thể làm lộ `env`, `beans`, `mappings`, `heapdump`, `logfile` hoặc endpoint có thao tác thay đổi. Dùng allowlist tối thiểu.

### 18.5. Public health details

Health status thường đủ cho probe. Dependency details có thể tiết lộ database, broker, hostname hoặc topology. Chỉ hiển thị khi cần và có role.

### 18.6. Cho Prometheus quyền quản trị

Prometheus thường chỉ cần GET endpoint metrics. Không cấp role có thể thay đổi loggers, shutdown hoặc xóa sessions cho service account scrape.

### 18.7. Coi management port riêng là cơ chế authentication

Port riêng chỉ phân tách listener. Nếu port vẫn có thể truy cập từ mạng không tin cậy, endpoint vẫn cần security policy và network controls.

### 18.8. Tắt CSRF toàn cục để sửa 403

403 có thể do CSRF hoặc thiếu authority. Xác định nguyên nhân trước khi thay policy. Với mục tiêu chỉ đọc, giữ endpoint ở read-only sẽ loại bỏ nhu cầu thao tác ghi từ client.

## 19. Quy trình thiết kế policy cho Actuator

1. Liệt kê endpoint cần cho health probe, monitoring và diagnostics.
2. Xác định endpoint nào chỉ cần GET/HEAD.
3. Dùng `management.endpoints.access.default: none` để bắt đầu từ trạng thái opt-in nếu dùng Boot 4.2.
4. Đặt `management.endpoints.access.max-permitted: read-only` nếu ứng dụng không cần write operations từ Actuator.
5. Expose allowlist riêng cho HTTP và JMX.
6. Gán role riêng cho operator và service account.
7. Giữ `env`/`configprops` sanitized; health details ở chế độ phù hợp.
8. Tách management port/address và giới hạn network.
9. Kiểm thử anonymous, reader, admin và write operations.
10. Kiểm tra các hệ thống telemetry khác như Prometheus, tracing backend và log store.
11. Ghi lại owner, mục đích, thời hạn và runbook cho mỗi endpoint được mở.

~~~mermaid
flowchart TD
    A["Liệt kê nhu cầu vận hành"] --> B["Chọn endpoint tối thiểu"]
    B --> C["Access default = none"]
    C --> D["Max permitted = read-only"]
    D --> E["Expose allowlist HTTP/JMX"]
    E --> F["Role-based authorization"]
    F --> G["Network / TLS boundary"]
    G --> H["Test anonymous, reader, admin"]
    H --> I["Review payload và audit policy"]
~~~

## 20. Checklist bảo vệ Actuator

- [ ] Đã xác định phiên bản Spring Boot và property access tương ứng.
- [ ] Đã phân biệt endpoint access với HTTP/JMX exposure.
- [ ] Đã đặt access default theo nguyên tắc opt-in nếu phù hợp.
- [ ] Đã giới hạn `max-permitted` ở `read-only` khi không cần write operations.
- [ ] Đã expose allowlist tối thiểu thay vì `*`.
- [ ] `health` không hiển thị details/components công khai ngoài nhu cầu.
- [ ] `env`, `configprops` và endpoint nhạy cảm giữ sanitization.
- [ ] Đã bảo vệ metrics/Prometheus bằng role hoặc network policy.
- [ ] Đã cấu hình Spring Security role riêng cho Actuator reader.
- [ ] Custom SecurityFilterChain vẫn bảo vệ application routes.
- [ ] Đã kiểm tra CSRF và write/delete operations.
- [ ] Management port/address chỉ truy cập từ mạng được phép.
- [ ] JMX exposure và remote connector được bảo vệ riêng.
- [ ] Không expose `heapdump`, `logfile`, `sessions` hoặc `shutdown` nếu không có nhu cầu được duyệt.
- [ ] Đã kiểm thử 401, 403, 404/405 và nội dung response.
- [ ] Các hệ thống Prometheus, tracing backend và log store có policy riêng.
- [ ] Có owner và runbook cho từng endpoint được expose.

## 21. Bài tập tự luyện

1. **Khái niệm:** Phân biệt endpoint access, exposure, authentication và authorization.
2. **Access level:** `none`, `read-only` và `unrestricted` khác nhau thế nào?
3. **Cấu hình:** Viết YAML để chỉ cho phép đọc `health`, `metrics` và `prometheus`, đồng thời đặt `max-permitted: read-only`.
4. **Exposure:** Vì sao endpoint có access read-only nhưng không nằm trong HTTP exposure allowlist vẫn không truy cập được qua HTTP?
5. **Spring Security:** `EndpointRequest.toAnyEndpoint()` và `hasRole("ACTUATOR_READER")` làm nhiệm vụ gì?
6. **Filter chain:** Vì sao cần chain thứ hai cho application routes khi thêm custom `SecurityFilterChain` chỉ match Actuator?
7. **Health:** Khi nào dùng `show-details: when-authorized` thay cho `never`?
8. **Sanitization:** `env.show-values: when-authorized` kết hợp `roles` có tác dụng gì?
9. **Threat model:** Vì sao `heapdump` vẫn nhạy cảm dù chỉ có HTTP GET?
10. **Network:** Management port riêng có thay thế authentication không? Hãy mô tả một network policy phù hợp.
11. **JMX:** Vì sao cấu hình HTTP exposure không tự bảo vệ JMX?
12. **CSRF:** Một POST tới Actuator trả 403. Làm thế nào phân biệt lỗi CSRF với thiếu role?
13. **Spring Modulith:** Vì sao module graph nên được giới hạn cho developer/operator?
14. **Nâng cấp:** Một ứng dụng Boot 3.x không nhận `management.endpoints.access.max-permitted`. Cần xử lý thế nào?
15. **Kiểm thử:** Thiết kế test xác minh reader có thể GET metrics nhưng không thể thay đổi log level.

## 22. Tổng kết

Giới hạn quyền đọc Actuator cần kết hợp nhiều lớp:

- **Endpoint access** quyết định endpoint có khả dụng và operation nào được phép.
- **Exposure** quyết định endpoint xuất qua HTTP hoặc JMX.
- **Authentication/authorization** xác định ai được truy cập.
- **Network boundary** giới hạn nguồn có thể kết nối.
- **Sanitization** giảm nguy cơ lộ giá trị nhạy cảm trong response.

Với Spring Boot 4.2, `management.endpoints.access.default: none` tạo chính sách opt-in; `management.endpoints.access.max-permitted: read-only` đặt trần quyền đọc cho toàn ứng dụng. Sau đó, expose đúng allowlist và dùng Spring Security role riêng cho operator/monitoring.

Trong ứng dụng Spring Modulith, module graph, metrics và observability spans là tài sản vận hành có giá trị nhưng cũng có thể tiết lộ kiến trúc nội bộ. Chỉ cấp quyền cho người và hệ thống có nhu cầu, đồng thời bảo vệ riêng Prometheus, tracing backend và log store. Mục tiêu là để đội vận hành có đủ dữ liệu chẩn đoán trong khi quyền thao tác và phạm vi thông tin vẫn được kiểm soát.

### Tài liệu tham khảo chính thức

1. [Spring Boot 4.2 — Endpoints: Access levels, exposure và security](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html).
2. [Spring Boot 4.2 — Spring Security: custom SecurityFilterChain và EndpointRequest](https://docs.spring.io/spring-boot/reference/web/spring-security.html).
3. [Spring Boot 4.2 — Monitoring and Management over HTTP: management port, address và SSL](https://docs.spring.io/spring-boot/reference/actuator/monitoring.html).
4. [Spring Boot — Actuator Endpoint API](https://docs.spring.io/spring-boot/api/rest/actuator/index.html).
5. [Spring Security — Servlet Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html).
6. [Spring Security — CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html).
7. [Spring Modulith — Production-ready Features: Module Actuator và Observability](https://docs.spring.io/spring-modulith/reference/production-ready.html).
