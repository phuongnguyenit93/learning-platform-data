# Giới hạn quyền truy cập khi dùng thông tin chẩn đoán của Actuator

## 1. Mục tiêu và bối cảnh

Spring Boot Actuator cung cấp các endpoint để quan sát và quản trị ứng dụng đang chạy. Chúng rất hữu ích khi điều tra lỗi, theo dõi sức khỏe, xem cấu hình đã bind, kiểm tra điều kiện auto-configuration, metrics, thread dump hoặc log. Nhưng dữ liệu chẩn đoán cũng có thể tiết lộ **cấu trúc nội bộ, thông tin triển khai, cấu hình nhạy cảm, dấu vết request và trạng thái vận hành**.

Ví dụ:

- `/actuator/health` có thể chỉ trả `UP`, hoặc có thể tiết lộ database, Redis, broker, host và trạng thái từng thành phần nếu bật details.
- `/actuator/env` hiển thị property sources và giá trị môi trường; `/actuator/configprops` hiển thị dữ liệu đã bind vào `@ConfigurationProperties`.
- `/actuator/beans`, `conditions` và `mappings` có thể cho biết tên bean, cấu hình và đường dẫn ứng dụng.
- `/actuator/heapdump` có thể chứa dữ liệu trong bộ nhớ như token, session hoặc nội dung nghiệp vụ.
- `/actuator/logfile` có thể trả về log có thông tin cá nhân, header, lỗi nội bộ hoặc dữ liệu vô tình ghi nhầm.
- `/actuator/loggers` có thể thay đổi mức log; `/actuator/shutdown` có thể tắt ứng dụng khi endpoint được bật.

**Mục tiêu của bài học:** thiết kế quyền truy cập theo mức độ nhạy cảm của dữ liệu, giới hạn endpoint được công khai, xác thực và phân quyền người gọi, giữ sanitization, và bố trí management server trong mạng phù hợp. Bài dùng baseline **Spring Boot 3.3.x, Java 17+ và Spring Security 6.3**.

Một nguyên tắc cần nhớ: **endpoint được bật, endpoint được expose, người gọi được phép truy cập và dữ liệu trả về được làm sạch là bốn quyết định khác nhau**. Chỉ thực hiện một trong bốn chưa đủ để bảo vệ thông tin chẩn đoán.

## 2. Actuator có thể tiết lộ những gì?

| Endpoint | Giá trị vận hành | Rủi ro nếu người không phù hợp truy cập |
| --- | --- | --- |
| `health` | Trạng thái tổng thể và khả năng phục vụ | Details có thể lộ tên dependency, trạng thái database, cache, broker hoặc host |
| `info` | Build, git, metadata do ứng dụng cung cấp | Có thể lộ phiên bản, commit, branch, thông tin môi trường hoặc nội dung tùy chỉnh |
| `env` | Property sources và cấu hình môi trường | Có thể lộ tên property, nguồn cấu hình, URL, hostname và giá trị nhạy cảm nếu cho phép hiển thị |
| `configprops` | Giá trị của các bean `@ConfigurationProperties` | Có thể lộ cấu hình datasource, client, credential hoặc topology |
| `conditions` | Lý do auto-configuration được chọn/bỏ qua | Tiết lộ classpath, cấu hình và thành phần nội bộ |
| `beans` | Danh sách bean trong context | Tiết lộ kiến trúc, tên class, dependency và module |
| `mappings` | Các HTTP request mapping | Tiết lộ đường dẫn API, controller và cấu trúc endpoint |
| `metrics` / `prometheus` | Chỉ số vận hành | Tên metric, tag, định danh tenant hoặc nhãn có dữ liệu nhạy cảm nếu tự thiết kế sai |
| `httpexchanges` | Dấu vết request/response gần đây | Có thể lộ URI, trạng thái, principal hoặc header tùy repository và cấu hình |
| `threaddump` | Trạng thái thread, stack trace | Tiết lộ tên class, đường đi xử lý, tài nguyên và thông tin runtime |
| `logfile` | Nội dung file log | Có thể lộ token, dữ liệu cá nhân, SQL, exception hoặc thông tin nội bộ |
| `heapdump` | Snapshot bộ nhớ JVM | Có thể chứa dữ liệu ứng dụng và bí mật ở dạng có thể phân tích |
| `loggers` | Xem và thay đổi mức log | Có thể thay đổi hành vi ghi log, làm tăng dữ liệu nhạy cảm hoặc ảnh hưởng hiệu năng |
| `shutdown` | Dừng ứng dụng có kiểm soát | Là thao tác quản trị có tác động trực tiếp đến khả năng phục vụ |

Không phải mọi endpoint đều có cùng mức độ nhạy cảm. Cũng không nên coi `health` hoặc `info` mặc nhiên vô hại: dữ liệu cụ thể phụ thuộc health contributors và info contributors của ứng dụng. Hãy xem response thật trong môi trường thử nghiệm trước khi mở endpoint.

## 3. Bốn lớp kiểm soát độc lập

### 3.1. Enable: endpoint có được đăng ký hay không?

Trong Spring Boot 3.3, hầu hết endpoint được bật mặc định, ngoại trừ `shutdown` bị tắt mặc định. Có thể kiểm soát bằng:

```yaml
management:
  endpoints:
    enabled-by-default: false
  endpoint:
    health:
      enabled: true
    info:
      enabled: true
```

Khi dùng `management.endpoints.enabled-by-default=false`, hãy bật tường minh những endpoint cần dùng bằng `management.endpoint.<id>.enabled=true`. Endpoint bị disable được loại khỏi ApplicationContext. Đây là chính sách *opt-in* hữu ích khi hệ thống có yêu cầu giới hạn chức năng quản trị.

### 3.2. Expose: endpoint có được đưa ra HTTP hoặc JMX không?

Endpoint đã enabled vẫn có thể không được expose trên một transport cụ thể. Spring Boot 3.3 mặc định chỉ expose `health` qua HTTP và JMX. Dùng:

- `management.endpoints.web.exposure.include` để chọn endpoint HTTP.
- `management.endpoints.web.exposure.exclude` để loại endpoint HTTP.
- `management.endpoints.jmx.exposure.include` và `exclude` cho JMX.

Ví dụ chỉ mở health và info:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info"
```

Nếu một endpoint có mặt đồng thời trong include và exclude, **exclude được ưu tiên**. Khi cần expose thêm một endpoint, thêm đúng ID cần dùng; không mở tất cả chỉ để tiện debug.

Không dùng cấu hình rộng sau như mặc định cho production:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "*"
```

Dấu `*` trong YAML cần được đặt trong dấu ngoặc kép. Nếu thật sự cần expose rộng cho một môi trường chẩn đoán cô lập, vẫn phải thiết lập network boundary, authentication, authorization và kiểm tra nội dung của từng endpoint.

### 3.3. Authenticate và authorize: ai được phép gọi?

- **Authentication** xác định danh tính người gọi.
- **Authorization** xác định người đó có quyền truy cập endpoint/operation cụ thể hay không.

Chỉ expose endpoint không tự tạo ra authentication. Nếu không có Spring Security hoặc cơ chế bảo vệ khác, endpoint được expose có thể truy cập theo cấu hình mạng hiện có.

Khi Spring Security có trên classpath và không có bean `SecurityFilterChain` tùy chỉnh, Spring Boot auto-configuration bảo vệ các actuator khác `/health`. Nếu ứng dụng tự khai báo `SecurityFilterChain`, auto-configuration bảo mật mặc định sẽ nhường quyền điều khiển cho cấu hình của ứng dụng. Đây là điểm dễ gây lỗi: một filter chain tùy chỉnh không giới hạn đúng endpoint có thể vô tình làm các đường dẫn actuator hoặc đường dẫn nghiệp vụ không được bảo vệ như dự kiến.

### 3.4. Sanitize: người có quyền có được xem giá trị gốc không?

Một người được phép gọi `/actuator/env` không nhất thiết phải xem mọi giá trị cấu hình. Với `env`, `configprops` và `quartz`, Spring Boot 3.3 mặc định **sanitize toàn bộ giá trị** thành `******`. Nếu cần hiển thị giá trị gốc, endpoint hỗ trợ `show-values`:

| Giá trị | Hành vi |
| --- | --- |
| `never` | Luôn ẩn giá trị; đây là mặc định |
| `when-authorized` | Chỉ hiển thị cho người được xác thực và có role được endpoint yêu cầu |
| `always` | Hiển thị giá trị cho mọi người có thể gọi endpoint, trừ khi `SanitizingFunction` vẫn áp dụng |

Đối với HTTP, người dùng được xem là authorized khi đã xác thực và có một trong các role được khai báo tại endpoint. Nếu không cấu hình role, mặc định **mọi người dùng đã xác thực** đều được coi là authorized. Đối với JMX, Spring Boot coi mọi người dùng là authorized cho quyết định sanitization này. Vì vậy không được cho rằng `roles` của `show-values` cũng giới hạn JMX giống HTTP.

Một `SanitizingFunction` tùy chỉnh vẫn được áp dụng ngay cả khi `show-values=always` hoặc `when-authorized`. Hãy giữ `never` nếu không có nhu cầu chẩn đoán thực sự cần giá trị gốc.

## 4. Cấu hình mẫu cho môi trường có đội vận hành

Ví dụ sau chỉ expose health và info qua HTTP; health details chỉ hiển thị cho role vận hành:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info"
  endpoint:
    health:
      show-details: when-authorized
      show-components: when-authorized
      roles: ACTUATOR_ADMIN
```

Nếu có nhu cầu chẩn đoán cấu hình trong thời gian giới hạn, có thể thêm `env` và `configprops` cùng chính sách giá trị:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info,env,configprops"
  endpoint:
    health:
      show-details: when-authorized
      show-components: when-authorized
      roles: ACTUATOR_ADMIN
    env:
      show-values: when-authorized
      roles: ACTUATOR_ADMIN
    configprops:
      show-values: when-authorized
      roles: ACTUATOR_ADMIN
```

`show-values=when-authorized` không thay thế việc phân quyền endpoint. Nó chỉ điều khiển việc hiển thị giá trị nhạy cảm trong response. Người không có quyền endpoint vẫn phải bị chặn bởi Spring Security; người đã đăng nhập nhưng không có role vận hành chỉ được nhận phần đã sanitize nếu được phép gọi endpoint theo chính sách HTTP tương ứng.

Với tài khoản Basic Auth demo có thể dùng cấu hình sau:

```yaml
spring:
  security:
    user:
      name: actuator-admin
      password: ${ACTUATOR_ADMIN_PASSWORD}
      roles: ACTUATOR_ADMIN
```

`ACTUATOR_ADMIN_PASSWORD` phải được cung cấp từ secret manager hoặc biến môi trường của nền tảng triển khai; không commit mật khẩu thật vào Git, Docker image, file cấu hình mẫu hoặc log. Đây là ví dụ cho môi trường đơn giản. Ở production nhiều người dùng, nên dùng identity provider/OAuth2 Resource Server, LDAP hoặc hệ thống xác thực tập trung để cấp role theo danh tính và audit được hoạt động quản trị.

## 5. Bảo vệ HTTP Actuator bằng Spring Security

### 5.1. Dùng `EndpointRequest` thay cho hard-code URL

Spring Boot 3.3 cung cấp `org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest` để tạo `RequestMatcher` dựa trên endpoint thực tế. Ví dụ:

- `EndpointRequest.to("health")` khớp endpoint health và các subpath của nó.
- `EndpointRequest.toAnyEndpoint()` khớp các actuator web endpoints.

Điểm lợi là matcher vẫn làm việc khi đổi `management.endpoints.web.base-path` hoặc path mapping, miễn endpoint được cấu hình qua cơ chế Actuator. Không nên dựa vào việc URL mặc định luôn là `/actuator/**`.

### 5.2. Một SecurityFilterChain bao phủ cả ứng dụng

Ví dụ dưới đây cho phép health được gọi không cần đăng nhập; các actuator còn lại yêu cầu role `ACTUATOR_ADMIN`; những route nghiệp vụ khác yêu cầu authentication. Cấu hình này dùng **một filter chain bao phủ toàn bộ HTTP request**, nên không để lọt đường dẫn không khớp actuator matcher.

Lưu tệp `src/main/java/example/security/ActuatorSecurityConfiguration.java`:

```java
package example.security;

import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class ActuatorSecurityConfiguration {

    @Bean
    SecurityFilterChain applicationSecurity(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(authorize -> authorize
                .requestMatchers(EndpointRequest.to("health")).permitAll()
                .requestMatchers(EndpointRequest.toAnyEndpoint())
                    .hasRole("ACTUATOR_ADMIN")
                .anyRequest().authenticated()
        );

        http.httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
```

Các điểm cần hiểu:

1. `health` được phép truy cập công khai ở lớp HTTP authorization; mức chi tiết health vẫn do `management.endpoint.health.show-details` và `roles` quyết định.
2. `toAnyEndpoint()` đứng sau matcher health nên những actuator còn lại cần role `ACTUATOR_ADMIN`.
3. `anyRequest().authenticated()` bảo vệ phần ứng dụng còn lại.
4. `httpBasic` là ví dụ xác thực đơn giản; production nên dùng HTTPS và cơ chế danh tính phù hợp, không gửi Basic credentials qua HTTP không mã hóa.

### 5.3. Cảnh báo khi tách riêng filter chain cho Actuator

Có thể giới hạn một filter chain chỉ dành cho actuator bằng:

```java
http.securityMatcher(EndpointRequest.toAnyEndpoint());
```

Nhưng khi đã khai báo custom `SecurityFilterChain`, Spring Boot security auto-configuration nhường quyền điều khiển. Nếu chain chỉ match actuator, bạn **phải có thêm một SecurityFilterChain khác** xử lý các request của ứng dụng còn lại, với thứ tự `@Order` và matcher được thiết kế rõ. Nếu thiếu chain thứ hai, các route ngoài actuator có thể không đi qua bộ quy tắc bạn nghĩ rằng đang bảo vệ chúng.

Đây là lỗi cấu hình phổ biến khi copy ví dụ security actuator rồi quên bổ sung security cho phần ứng dụng.

## 6. Tách management server và giới hạn mạng

Mặc định Actuator HTTP thường dùng cùng cổng với ứng dụng. Khi cần, có thể dùng cổng quản trị riêng:

```yaml
management:
  server:
    port: 8081
    address: 127.0.0.1
```

Trong Spring Boot 3.3, có thể đổi cổng bằng `management.server.port` và địa chỉ lắng nghe bằng `management.server.address`. Địa chỉ khác chỉ được dùng khi management port khác cổng chính. `127.0.0.1` khiến management server chỉ nhận kết nối loopback trên host/container đó; đây phù hợp khi agent giám sát chạy cùng network namespace, nhưng sẽ không phù hợp nếu hệ thống monitoring ở máy khác cần gọi trực tiếp.

Với hạ tầng có monitoring agent bên ngoài, nên bind vào interface nội bộ phù hợp, sau đó dùng firewall, Kubernetes NetworkPolicy, security group hoặc service mesh để chỉ cho phép nguồn tin cậy truy cập. Cổng riêng **không tự tạo authentication** và không thay thế role authorization.

Nếu management server dùng cổng riêng, có thể cấu hình TLS riêng bằng `management.server.ssl.*`. Hãy bảo đảm dữ liệu xác thực và response chẩn đoán được mã hóa trên đường truyền. Việc đổi `management.endpoints.web.base-path` từ `/actuator` sang `/manage` hoặc tên khó đoán chỉ là đổi URL, **không phải biện pháp bảo mật**.

Nếu ứng dụng không cần HTTP Actuator, có thể tắt hoàn toàn HTTP endpoints:

```yaml
management:
  server:
    port: -1
```

JMX có chính sách exposure riêng; tắt HTTP không tự động đồng nghĩa mọi kênh quản trị khác cũng tắt. Hãy rà soát cả `management.endpoints.jmx.exposure.*` và cấu hình JMX connector/network tương ứng.

## 7. Những endpoint cần quản lý đặc biệt

### 7.1. `env` và `configprops`

Hai endpoint này có thể trả về tên property, nguồn property và giá trị đã bind. Giá trị nhạy cảm mặc định được mask, nhưng tên key, tên nguồn, prefix hoặc cấu trúc cấu hình vẫn có thể giúp người xem suy ra kiến trúc nội bộ.

- Không bật `show-values=always` trong môi trường public.
- Nếu thực sự cần giá trị gốc, dùng `when-authorized` và role riêng cho đội vận hành.
- Giữ custom `SanitizingFunction` nếu có quy tắc redaction theo tổ chức.
- Chỉ expose qua HTTP khi có nhu cầu; cân nhắc exclude khỏi JMX nếu không có chính sách JMX tương đương.
- Không gửi toàn bộ response vào ticket/log công khai vì có thể làm lộ metadata nhạy cảm.

### 7.2. `health`

`management.endpoint.health.show-details` và `show-components` mặc định là `never`. Có thể dùng `when-authorized` với `management.endpoint.health.roles` để chỉ role vận hành xem chi tiết. Hãy kiểm tra custom `HealthIndicator` của ứng dụng: dữ liệu detail do chính bạn trả về cũng cần được đánh giá. Không đưa password, token, connection string hoặc dữ liệu khách hàng vào `Health.details`.

Đối với Kubernetes, phân biệt liveness và readiness. Liveness nên cho biết ứng dụng có cần restart hay không; không nên phụ thuộc vào mọi dịch vụ ngoài vì sự cố database có thể khiến Kubernetes restart hàng loạt pod và tạo cascading failure. Readiness có thể kiểm tra dependency thiết yếu theo chính sách của ứng dụng. Không cần expose chi tiết health cho tất cả người gọi chỉ để probe nhận status.

### 7.3. `conditions`, `beans`, `mappings` và `threaddump`

Các endpoint này rất hữu ích khi developer điều tra lỗi startup hoặc wiring, nhưng có thể tiết lộ classpath, cấu trúc bean, URL nội bộ, controller mapping và stack trace. Hãy giới hạn cho đội kỹ thuật có trách nhiệm, và chỉ bật trong thời gian/chặng triển khai cần thiết nếu không có nhu cầu vận hành thường xuyên.

### 7.4. `logfile` và `heapdump`

Đây là các nguồn dữ liệu có rủi ro cao:

- Log có thể chứa dữ liệu request, email, định danh, SQL hoặc token nếu ứng dụng log không đúng cách.
- Heap dump có thể giữ nguyên object chứa thông tin xác thực, session, request body hoặc dữ liệu nghiệp vụ trong bộ nhớ.
- Việc tải file lớn có thể tốn băng thông, bộ nhớ, dung lượng lưu trữ và gây ảnh hưởng đến ứng dụng.

Không expose các endpoint này ra internet. Khi cần thu thập để điều tra, cấp quyền rất hạn chế, dùng kênh truyền mã hóa, lưu trữ có kiểm soát, thời hạn lưu ngắn và xóa artifact khi hoàn thành.

### 7.5. `loggers` và `shutdown`

`loggers` có thao tác thay đổi mức log; `shutdown` có thể dừng ứng dụng. `shutdown` bị disable mặc định trong Spring Boot 3.3 và phải bật riêng nếu thật sự cần. Đừng thêm `shutdown` vào exposure chỉ vì muốn có một API tiện để restart. Ưu tiên orchestration platform hoặc quy trình deployment có audit.

Các thao tác ghi của Actuator thường dùng HTTP POST, PUT hoặc DELETE. Spring Security bật CSRF protection mặc định; vì vậy `shutdown` hoặc `loggers` có thể trả `403` khi không có CSRF token phù hợp. Không nên tắt CSRF toàn cục chỉ để làm một thao tác quản trị chạy được. Chỉ cân nhắc chính sách CSRF riêng cho client-to-service không dùng browser session/cookie, sau khi đã giới hạn authentication, network và operation.

## 8. CORS không phải authentication

CORS kiểm soát việc trình duyệt cho phép JavaScript từ origin khác đọc response; nó **không xác thực người gọi** và không chặn các client như curl, script, service-to-service hoặc công cụ mạng khác. Một endpoint Actuator có thể vẫn truy cập được dù browser bị CORS chặn.

Spring Boot 3.3 mặc định tắt CORS cho Actuator; CORS chỉ hoạt động khi cấu hình `management.endpoints.web.cors.allowed-origins`. Chỉ cấu hình CORS cho frontend vận hành thật sự cần truy cập; không dùng `allowed-origins=*` hoặc coi CORS là lớp bảo vệ thay thế cho Spring Security và network ACL.

## 9. Kiểm thử quyền truy cập bằng MockMvc

Một security rule nên có test cho ít nhất ba trạng thái: anonymous, người dùng có role đúng và người dùng đã xác thực nhưng không có role. Test dưới đây dùng Spring Security Test để mô phỏng danh tính, không cần hard-code mật khẩu.

### 9.1. Dependency cần có

Trong Maven, project test cần các dependency được quản lý version qua Spring Boot BOM/parent:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

### 9.2. Tệp test hoàn chỉnh

Tạo `src/test/java/example/security/ActuatorSecurityTests.java`:

```java
package example.security;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(
    classes = ActuatorSecurityTests.TestApplication.class,
    properties = {
        "management.endpoints.web.exposure.include=health,info",
        "management.endpoint.health.show-details=never"
    }
)
@AutoConfigureMockMvc
class ActuatorSecurityTests {

    @Autowired
    MockMvc mockMvc;

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @Import(SecurityConfiguration.class)
    static class TestApplication {}

    @Configuration(proxyBeanMethods = false)
    static class SecurityConfiguration {

        @Bean
        SecurityFilterChain applicationSecurity(HttpSecurity http)
                throws Exception {
            http.authorizeHttpRequests(authorize -> authorize
                    .requestMatchers(EndpointRequest.to("health"))
                        .permitAll()
                    .requestMatchers(EndpointRequest.toAnyEndpoint())
                        .hasRole("ACTUATOR_ADMIN")
                    .anyRequest().authenticated()
            );
            http.httpBasic(Customizer.withDefaults());
            return http.build();
        }
    }

    @Test
    void healthIsPublic() throws Exception {
        mockMvc.perform(get("/actuator/health"))
                .andExpect(status().isOk());
    }

    @Test
    void infoRejectsAnonymousUser() throws Exception {
        mockMvc.perform(get("/actuator/info"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void infoAllowsActuatorAdmin() throws Exception {
        mockMvc.perform(get("/actuator/info")
                        .with(user("ops").roles("ACTUATOR_ADMIN")))
                .andExpect(status().isOk());
    }

    @Test
    void infoRejectsAuthenticatedUserWithoutRole() throws Exception {
        mockMvc.perform(get("/actuator/info")
                        .with(user("reader").roles("USER")))
                .andExpect(status().isForbidden());
    }
}
```

### 9.3. Chạy test và đọc kết quả

Với Gradle wrapper:

```bash
./gradlew test --tests example.security.ActuatorSecurityTests
```

Với Maven wrapper:

```bash
./mvnw -Dtest=ActuatorSecurityTests test
```

Kết quả mong đợi là **4 test PASS**:

| Request | Danh tính | Kết quả HTTP mong đợi | Ý nghĩa |
| --- | --- | --- | --- |
| `GET /actuator/health` | Anonymous | `200` | Health status được mở |
| `GET /actuator/info` | Anonymous | `401` | Chưa xác thực |
| `GET /actuator/info` | Role `ACTUATOR_ADMIN` | `200` | Đã xác thực và được phân quyền |
| `GET /actuator/info` | Role `USER` | `403` | Đã xác thực nhưng thiếu quyền |

`SecurityMockMvcRequestPostProcessors.user` đặt principal giả lập vào request để kiểm thử authorization. Nó **không phải** test giao thức Basic Auth thực tế, TLS, reverse proxy, network policy hoặc secret manager. Những phần đó cần integration test/deployment test riêng. Khi đổi `management.endpoints.web.base-path`, nên bổ sung test endpoint matcher vẫn áp dụng đúng.

## 10. Quy trình rà soát trước khi mở thông tin chẩn đoán

1. **Liệt kê nhu cầu vận hành:** monitoring chỉ cần health hay cần cả info, metrics, env, configprops, thread dump? Ghi rõ consumer của từng endpoint.
2. **Phân loại dữ liệu:** endpoint nào chỉ trả trạng thái, endpoint nào trả metadata, endpoint nào có thể trả dữ liệu trong bộ nhớ/log.
3. **Tắt mặc định và opt-in nếu phù hợp:** dùng `management.endpoints.enabled-by-default=false` rồi bật từng endpoint cần thiết; nếu giữ mặc định enable, vẫn cần allow-list exposure.
4. **Chỉ expose qua transport cần dùng:** HTTP/JMX có include/exclude riêng. Rà soát cả hai; không suy luận từ HTTP sang JMX.
5. **Cấu hình role theo chức năng:** người chỉ xem health không cần quyền xem env hoặc tải heap dump. Tách role read-only, operator và incident responder khi hệ thống có các nhóm nhiệm vụ khác nhau.
6. **Giữ sanitization:** `show-values=never` là lựa chọn an toàn; chỉ chuyển sang `when-authorized` khi có case vận hành cụ thể, kèm role endpoint riêng.
7. **Đặt management server vào network tin cậy:** cổng, address, firewall/security group/network policy và TLS phải phù hợp kiến trúc.
8. **Test 401, 403 và 200:** kiểm tra anonymous, role sai, role đúng; thử cả base path tùy chỉnh và các operation ghi nếu chúng được bật.
9. **Kiểm tra response thực tế:** xem health details, env/configprops, info contributors, logs, metrics tags và custom health indicators. Không đưa dữ liệu thật nhạy cảm vào ảnh chụp, issue hay tài liệu công khai.
10. **Theo dõi thay đổi:** khi thêm dependency/starter hoặc endpoint custom, rà soát lại exposure, security matcher, sanitizer và network path. Endpoint mới không nên tự động trở thành dữ liệu public.

## 11. Lỗi thường gặp và cách khắc phục

- **Chỉ cấu hình exposure rồi cho rằng endpoint đã an toàn.** Exposure chỉ quyết định endpoint có được đưa ra transport; phải có authentication/authorization và network boundary.
- **Dùng `include: "*"` để debug rồi quên thu hẹp.** Đổi về allow-list theo nhu cầu; `exclude` có ưu tiên nhưng không nên dựa vào blacklist dài khi có thể chọn whitelist ngắn.
- **Bật `show-values=always` trong production.** Dùng `never` hoặc `when-authorized` với role cụ thể; rà soát cả JMX và `SanitizingFunction`.
- **Không khai báo `roles` cho `show-values=when-authorized`.** Mặc định bất kỳ user đã xác thực nào cũng được coi là authorized; phải đặt role nếu chỉ nhóm vận hành được xem.
- **Chỉ tạo custom SecurityFilterChain cho actuator rồi quên chain cho application.** Spring Boot security auto-configuration backs off; nếu chain chỉ match actuator, cần chain thứ hai cho phần còn lại.
- **Hard-code `/actuator/**` trong SecurityMatcher.** Dùng `EndpointRequest` để tương thích base path và path mapping.
- **Mở health details cho mọi người.** Giữ `show-details=never` hoặc dùng `when-authorized` với role; xem lại dữ liệu do HealthIndicator tự thêm.
- **Đổi tên path để “ẩn” endpoint.** Path khó đoán không thay authentication hoặc authorization.
- **Coi CORS là cơ chế chặn truy cập.** CORS chủ yếu áp dụng cho browser; API client khác vẫn có thể gọi nếu network/security cho phép.
- **Tắt CSRF toàn ứng dụng để gọi POST Actuator.** Xem xét CSRF token hoặc chính sách riêng cho non-browser client; không vô hiệu hóa toàn cục chỉ để bỏ qua lỗi 403.
- **Expose heapdump hoặc logfile như endpoint giám sát thông thường.** Đây là artifact có khả năng chứa dữ liệu rất nhạy cảm; chỉ cấp quyền điều tra rất hẹp và theo quy trình.
- **Đặt management port riêng nhưng mở cùng ingress public.** Port riêng không phải network isolation; cấu hình firewall/network policy và kiểm thử đường truy cập từ ngoài.
- **Bảo vệ HTTP nhưng quên JMX.** Exclude endpoint nhạy cảm khỏi JMX nếu không cần; remember `WHEN_AUTHORIZED` coi JMX users là authorized trong cơ chế sanitization của Boot.
- **Không kiểm tra dữ liệu do custom endpoint trả về.** Custom `@Endpoint` và `@ReadOperation` có thể tự expose object; review output như một API công khai và tránh trả thẳng secret hoặc object cấu hình toàn phần.

## 12. Câu hỏi tự kiểm tra

1. Trong Spring Boot 3.3, endpoint nào được expose qua HTTP mặc định? **`health`.** Các endpoint khác không tự xuất hiện qua HTTP chỉ vì chúng enabled.
2. `management.endpoints.web.exposure.include=health,env` có tự xác thực người gọi không? **Không.** Nó chỉ expose endpoint; cần Spring Security hoặc lớp kiểm soát khác.
3. `show-values=when-authorized` mà không đặt `roles` cho endpoint thì ai có thể xem giá trị? **Mọi người dùng HTTP đã xác thực**, theo mặc định của cơ chế này.
4. `show-values=when-authorized` áp dụng cho JMX như thế nào? **JMX users được coi là authorized** trong quyết định sanitization; cần quản lý JMX riêng.
5. Đã có custom `SecurityFilterChain` chỉ match `EndpointRequest.toAnyEndpoint()`. Cần nhớ điều gì? **Spring Boot security auto-configuration backs off; phải có chain khác bảo vệ request của ứng dụng.**
6. Đổi `management.endpoints.web.base-path` có thay thế authentication không? **Không.** Chỉ đổi đường dẫn.
7. `/actuator/heapdump` có nên public vì chỉ dùng để debug? **Không.** Heap dump có thể chứa dữ liệu nhạy cảm trong bộ nhớ.
8. `403` khi POST `/actuator/loggers` có thể do đâu? **CSRF protection mặc định** nếu request không gửi token phù hợp; không nên tắt CSRF toàn cục mà không xem xét mô hình client.
9. Đã mở cổng management riêng 8081, có thể bỏ Spring Security không? **Không thể suy luận như vậy.** Cần network ACL, authentication và authorization phù hợp; port riêng chỉ là một phần của phân tách mạng.
10. Muốn monitoring nhận trạng thái UP nhưng không thấy database hostname/chi tiết dependency, cấu hình nào phù hợp? **Để health details/components ở `never` hoặc `when-authorized` với role riêng**, đồng thời xem lại custom HealthIndicator.

## 13. Tài liệu tham khảo chính thức

- [Spring Boot 3.3 — Endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html): enable/disable, exposure HTTP/JMX, Spring Security, CSRF, sanitization và health details.
- [Spring Boot 3.3 — Monitoring and Management Over HTTP](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html): base path, management port, management address, SSL riêng và tắt HTTP endpoints.
- [Spring Boot 3.3 — EndpointRequest API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/security/servlet/EndpointRequest.html): matcher cho actuator endpoints trong Spring Security.
- [Spring Boot 3.3 — Actuator REST API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/index.html): đường dẫn và contract HTTP của các endpoint.
- [Spring Boot 3.3 — Spring Security](https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html): security auto-configuration và hành vi khi khai báo custom filter chain.
