# Bật log chẩn đoán Spring Security theo môi trường (WebFlux / Reactive)

## 1. Mục tiêu và phạm vi

Trong ứng dụng Spring Boot dùng **Spring WebFlux + Spring Security**, log chẩn đoán giúp trả lời các câu hỏi: request có đi qua chuỗi bảo mật không, xác thực thất bại ở đâu, vì sao bị từ chối quyền, và cấu hình nào đang hoạt động. Ta cần bật đủ chi tiết khi phát triển hoặc điều tra sự cố, nhưng giữ mức log vừa phải ở production để giảm chi phí, nhiễu và nguy cơ lộ dữ liệu.

Kết quả mong muốn sau bài này:

- Hiểu sự khác nhau giữa mức `INFO`, `DEBUG`, `TRACE` và phạm vi của từng logger.
- Cấu hình mức log bằng `application.yml`, `application-dev.yml`, `application-staging.yml`, `application-prod.yml`; kích hoạt đúng Spring profile.
- Tái hiện và đọc tình huống HTTP 200, 401, 403 trong **security chain reactive**.
- Thu hẹp logger khi cần phân tích sâu, đổi mức log tạm thời bằng Actuator khi được phép, rồi trả về mức an toàn.
- Nhận biết ảnh hưởng đến hiệu năng, dữ liệu nhạy cảm, và tính tương quan của log khi request chuyển luồng trong Reactor.

Đây là **diagnostic logging**, không thay thế audit trail, metrics, tracing hoặc cơ chế bảo mật. Bật DEBUG không làm request được cấp quyền và cũng không tự trả chi tiết lỗi xác thực về cho client.

## 2. Log phát sinh từ đâu trong ứng dụng reactive?

WebFlux xử lý request qua `WebFilter`; Spring Security áp dụng `SecurityWebFilterChain`, thường cấu hình với `ServerHttpSecurity`. Các thành phần liên quan gồm `AuthenticationWebFilter`, `AuthorizationWebFilter`, `ExceptionTranslationWebFilter` và các bộ quản lý xác thực/phân quyền tương ứng. Tùy phương thức đăng nhập (HTTP Basic, OAuth2/JWT, OAuth2 Login...), các logger và thông điệp có thể khác nhau.

**Phân biệt với Servlet:** `SecurityFilterChain`, `HttpSecurity`, `FilterChainProxy` và `@EnableWebSecurity(debug = true)` là các ví dụ/khái niệm thuộc Servlet. Với bài này, dùng `SecurityWebFilterChain`, `ServerHttpSecurity` và logger trong nhánh reactive, đặc biệt `org.springframework.security.web.server`. Đừng mong dòng log Servlet kiểu “Invoking ...Filter (n/m)” xuất hiện y hệt trong WebFlux.

Spring Boot điều khiển mức log qua thuộc tính `logging.level.<tên-logger>`. Logger có thứ bậc theo tên package: thiết lập `org.springframework.security=DEBUG` tác động đến các logger con nếu chúng không có cấu hình cụ thể hơn. `logging.level.root` là mức nền của toàn ứng dụng, không nên hạ toàn bộ root xuống TRACE chỉ để tìm một lỗi authorization.

| Mức | Ý nghĩa khi chẩn đoán | Cách dùng |
| --- | --- | --- |
| `ERROR` / `WARN` | Vấn đề nghiêm trọng, cảnh báo; không bảo đảm ghi mọi quyết định security | Giám sát thường xuyên |
| `INFO` | Sự kiện thông tin do thành phần thực sự phát ra | Mặc định thực dụng cho nhiều môi trường |
| `DEBUG` | Chi tiết phục vụ theo dõi luồng xử lý và quyết định | Dev, test hoặc bật có thời hạn khi điều tra |
| `TRACE` | Chi tiết hơn DEBUG, nhiều thông điệp hơn | Chỉ bật logger hẹp, trong khoảng ngắn |
| `OFF` | Tắt logger được chọn | Chỉ dùng khi hiểu rõ hệ quả đối với khả năng quan sát |

Không có cam kết rằng mỗi request đều tạo một thông điệp nhất định ở mỗi mức log; điều đó phụ thuộc phiên bản, nhánh thực thi và lớp ghi log.

## 3. Chọn logger đúng vấn đề

| Logger/package | Nên dùng khi | Lưu ý |
| --- | --- | --- |
| `org.springframework.security` | Cần nhìn toàn cảnh authentication/authorization | DEBUG/TRACE rộng, có thể tạo nhiều log |
| `org.springframework.security.web.server` | Theo dõi security WebFilter của WebFlux | Đúng nhánh reactive |
| `org.springframework.security.authentication` | Điều tra logic xác thực/đối chiếu credential | Không kỳ vọng có cùng log ở mọi authentication provider |
| `org.springframework.security.authorization` | Điều tra quyết định cấp/từ chối quyền | Kết hợp đối chiếu rule `authorizeExchange` |
| `org.springframework.security.oauth2.server.resource` | Ứng dụng làm Resource Server, xác thực Bearer/JWT | Chỉ hữu ích khi thực sự dùng OAuth2 Resource Server |
| `org.springframework.web.server` | Cần thêm ngữ cảnh xử lý request WebFlux | Là log của WebFlux, không riêng Spring Security |
| `reactor.netty.http.server` | Chẩn đoán tầng HTTP/Netty khi có vấn đề giao tiếp | Không suy diễn log mạng là quyết định phân quyền |

Nên bắt đầu từ `org.springframework.security=DEBUG` trên dev. Khi thấy quá nhiều log, giảm về INFO và bật DEBUG/TRACE cho **một package nhỏ hơn**. Khi lỗi liên quan JWT, đồng thời kiểm tra cấu hình decoder, issuer, audience, thời gian và các quyền/authority; logger không thay thế việc kiểm tra cấu hình.

## 4. Cấu hình theo môi trường bằng Spring profiles

Giả sử dự án đã có Spring Boot 3.x, `spring-boot-starter-webflux` và `spring-boot-starter-security`. Đặt các file sau trong `src/main/resources/`. Giá trị sau là **ví dụ có chủ đích**, cần điều chỉnh theo chính sách log của đội.

**`application.yml` — mức nền dùng chung:**

```yaml
spring:
  application:
    name: reactive-security-demo

logging:
  level:
    root: INFO
    org.springframework.security: INFO
    org.springframework.web: INFO
```

**`application-dev.yml` — chẩn đoán chi tiết khi phát triển:**

```yaml
logging:
  level:
    org.springframework.security: DEBUG
    org.springframework.security.web.server: TRACE
    org.springframework.web.server: DEBUG
```

**`application-staging.yml` — bình thường yên tĩnh hơn dev:**

```yaml
logging:
  level:
    org.springframework.security: INFO
    org.springframework.security.web.server: DEBUG
```

**`application-prod.yml` — mức thận trọng:**

```yaml
logging:
  level:
    org.springframework.security: WARN
    org.springframework.security.web.server: WARN
    org.springframework.web.server: INFO
```

Diễn giải: trên dev, package security tổng thể ở DEBUG còn `security.web.server` ở TRACE; trên staging chỉ nhánh WebFlux security ở DEBUG; trên prod ưu tiên WARN. `application-{profile}.yml` ghi đè giá trị nền tương ứng khi profile được kích hoạt. Một logger con đặt mức cụ thể sẽ không bị thay thế đơn giản chỉ vì logger cha thay đổi mức.

**Kích hoạt đúng profile:**

```bash
# Chạy JAR ở dev
java -jar app.jar --spring.profiles.active=dev

# Chạy JAR ở staging qua biến môi trường (Linux/macOS)
SPRING_PROFILES_ACTIVE=staging java -jar app.jar

# Chạy JAR ở prod
java -jar app.jar --spring.profiles.active=prod

# Ghi đè một logger ngay lúc khởi động để điều tra có kiểm soát
java -jar app.jar --spring.profiles.active=staging --logging.level.org.springframework.security.web.server=TRACE
```

Có thể đặt biến môi trường cấp package, chẳng hạn `LOGGING_LEVEL_ORG_SPRINGFRAMEWORK_SECURITY=DEBUG`, để điều khiển mức chung. Với tên logger **cụ thể đến lớp**, dùng cấu hình tệp, tham số `--logging.level...` hoặc `SPRING_APPLICATION_JSON` vì quy tắc ánh xạ biến môi trường không phù hợp với mọi tên lớp viết hoa. Giá trị từ command line thường có độ ưu tiên cao hơn file cấu hình; nhiều profile đang cùng active cũng có thể thay đổi giá trị cuối. Hãy kiểm tra nguồn cấu hình thực sự được nạp.

**Không nhầm `--debug` của Spring Boot với việc bật toàn bộ log Spring Security:** tùy chọn này giúp Spring Boot ghi thêm thông tin khởi động và báo cáo auto-configuration, không phải cách xác định để đặt mọi logger security ở DEBUG. Muốn chẩn đoán bảo mật, đặt `logging.level.org.springframework.security` một cách tường minh.

## 5. Ví dụ WebFlux tái hiện 200 / 401 / 403

Ví dụ dưới đây chỉ dùng **trong môi trường học tập**; mật khẩu `{noop}` là mật khẩu thuần để minh họa, tuyệt đối không dùng cho tài khoản thực. Trong dự án Spring Boot 3.x dùng Java 17+, cần có các dependency:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
```

Tạo tệp `src/main/java/demo/SecurityLogDemoApplication.java`:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
public class SecurityLogDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityLogDemoApplication.class, args);
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/public").permitAll()
                        .pathMatchers("/admin").hasRole("ADMIN")
                        .anyExchange().authenticated())
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails learner = User.withUsername("learner")
                .password("{noop}learn-only")
                .roles("USER")
                .build();
        return new MapReactiveUserDetailsService(learner);
    }

    @RestController
    static class DemoEndpoints {
        @GetMapping("/public")
        Mono<String> publicEndpoint() {
            return Mono.just("public ok");
        }

        @GetMapping("/me")
        Mono<String> me() {
            return Mono.just("authenticated ok");
        }

        @GetMapping("/admin")
        Mono<String> admin() {
            return Mono.just("admin ok");
        }
    }
}
```

`SecurityWebFilterChain` là chuỗi **reactive**. Quy tắc `/public` cho phép mọi người; `/me` đòi xác thực; `/admin` đòi role `ADMIN`. Tài khoản minh họa chỉ có role `USER`, nên truy cập `/admin` dù đăng nhập thành công vẫn bị từ chối. HTTP Basic được dùng để dễ thử; form login bị tắt để tránh luồng chuyển hướng sang trang đăng nhập khi quan sát kết quả.

Chạy ứng dụng với cấu hình dev, ví dụ khi dự án có Gradle wrapper và Spring Boot Gradle plugin:

```bash
./gradlew bootRun --args='--spring.profiles.active=dev'
```

Ở terminal khác, chạy các lệnh độc lập sau. Dùng `-s -o /dev/null -w` để chỉ in mã HTTP, tránh hiển thị body/header không cần thiết:

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/public
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/me
curl -s -o /dev/null -w '%{http_code}\n' -u learner:learn-only http://localhost:8080/me
curl -s -o /dev/null -w '%{http_code}\n' -u learner:learn-only http://localhost:8080/admin
```

Với **đúng cấu hình minh họa trên**, stdout từ bốn lệnh lần lượt là:

```text
200
401
200
403
```

Ý nghĩa: `200` đầu là endpoint công khai; `401` là thiếu thông tin xác thực cho `/me`; `200` thứ ba là Basic auth hợp lệ; `403` cuối là đã xác thực nhưng thiếu quyền `ADMIN`. Trong ứng dụng thực, cơ chế entry point, access-denied handler, proxy/gateway và rule khác có thể làm phản hồi khác ví dụ.

**Cách đọc log khi chạy thử:**

1. Bật DEBUG/TRACE ở profile dev rồi gửi **một request có kiểm soát**.
2. Lọc theo thời gian request, logger `org.springframework.security.*`, đường dẫn và mã phản hồi.
3. Với 401, lần theo bước lấy credential, authentication manager và authentication entry point; kiểm tra credential tồn tại/hợp lệ.
4. Với 403, kiểm tra principal đã xác thực, authority/role có trong Authentication, quy tắc `authorizeExchange`, CSRF (với request thay đổi trạng thái), và access-denied handler.
5. So sánh cấu hình và log sau khi đổi profile; nếu mức log quá rộng, chỉ giữ DEBUG/TRACE ở đúng package có giá trị.

Đừng sao chép một chuỗi log “chuẩn” từ ứng dụng Servlet để kiểm tra WebFlux. Tên logger, thứ tự thông điệp và nội dung chi tiết thay đổi theo phiên bản Spring Security và phương thức xác thực. Dùng response + chính sách cấu hình + log quan sát được để kết luận.

## 6. Đổi mức log khi ứng dụng đang chạy bằng Actuator (tùy chọn)

Khi đã có `spring-boot-starter-actuator` và chính sách vận hành cho phép, endpoint **loggers** giúp đọc mức hiện tại hoặc điều chỉnh mức log mà không khởi động lại tiến trình. Chỉ cấu hình endpoint ở môi trường quản trị có xác thực/phân quyền và mạng giới hạn.

Ví dụ cấu hình triển khai kiểm soát trong môi trường thử nghiệm:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,loggers
```

Sau khi endpoint được bảo vệ và người gọi có quyền phù hợp, các thao tác HTTP có dạng:

```http
GET /actuator/loggers/org.springframework.security.web.server

POST /actuator/loggers/org.springframework.security.web.server
Content-Type: application/json

{"configuredLevel":"TRACE"}
```

Để hủy mức đặt trực tiếp và quay về mức kế thừa/cấu hình mặc định, gửi:

```http
POST /actuator/loggers/org.springframework.security.web.server
Content-Type: application/json

{"configuredLevel":null}
```

Khi GET, `configuredLevel` là mức đặt trực tiếp ở logger đó (có thể `null`), còn `effectiveLevel` là mức có hiệu lực sau kế thừa. Trạng thái chỉnh runtime là **tạm thời**: có thể mất sau khởi động lại hoặc bị thay bởi quá trình quản trị cấu hình khác. Phải chủ động đưa logger về mức mong muốn sau khi kết thúc điều tra.

**Bảo vệ endpoint:** Actuator thường chỉ expose `health` qua HTTP theo mặc định. Nếu app có cấu hình security chain tùy chỉnh, hãy tự bảo vệ `/actuator/loggers/**` bằng quyền quản trị, mạng nội bộ và cơ chế xác thực phù hợp; đừng mặc định nó được tự bảo vệ đúng ý. POST có thể trả `403` vì CSRF; xử lý chính sách xác thực/CSRF của management endpoint đúng trường hợp sử dụng, không tắt CSRF toàn ứng dụng chỉ để gọi API. Không expose `loggers` ra Internet công khai.

## 7. Logging có ích cho quan sát, nhưng cũng có chi phí

**Hiệu năng:** DEBUG/TRACE tăng lượng tạo chuỗi thông điệp, ghi stdout/file, vận chuyển và lưu trữ log; áp lực CPU, I/O và dung lượng thay đổi theo tải và logging backend. Trên WebFlux, tác vụ ghi log đồng bộ nặng trong đường xử lý request có thể gây độ trễ không mong muốn; nên đo lưu lượng, kích thước log và latency thực tế, xem xét cấu hình appender phù hợp. Đừng tuyên bố một mức overhead cố định nếu chưa đo.

**Dữ liệu nhạy cảm:** log DEBUG/TRACE có thể chứa đường dẫn, định danh, thông tin xác thực hoặc dữ liệu ứng dụng tùy cách viết logger. WebFlux mặc định che một số header/parameter nhạy cảm, nhưng điều đó **không bảo đảm mọi thư viện hoặc logger tự viết đều an toàn**. Tránh bật `enableLoggingRequestDetails(true)` hay ghi toàn bộ `Authorization`, cookie, bearer token, mật khẩu, request/response body, dữ liệu cá nhân. Giới hạn người truy cập, áp dụng redaction, retention, lọc và phân quyền ở hệ thống tập trung log.

**Đặc tính reactive:** một request có thể tiếp tục trên các thread khác nhau, nên thread name/thread ID không phải khóa nối log đáng tin cậy. Spring WebFlux có log ID cho request (thông qua `ServerWebExchange#getLogPrefix()`); trong hệ thống nhiều dịch vụ nên bổ sung correlation ID/tracing được triển khai nhất quán. Reactor context không tương đương với việc kỳ vọng một `ThreadLocal` luôn theo request qua mọi scheduler.

**Chính sách gợi ý:** prod thường ở INFO/WARN theo nhu cầu vận hành; lúc có sự cố hãy giới hạn khoảng thời gian, logger, phạm vi tài khoản/request và quyền truy cập; sau đó khôi phục mức cũ và kiểm tra kích thước/độ nhạy log đã phát sinh. Diagnostic log không đủ làm nhật ký kiểm toán bất biến.

## 8. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra / xử lý |
| --- | --- | --- |
| Đặt DEBUG nhưng không thấy log security | Sai profile; logger không phát sự kiện ở lần thử; mức logger con bị override | Kiểm tra profile active, thứ tự config, `effectiveLevel`, rồi phát request đúng nhánh |
| Chỉ thấy ví dụ `FilterChainProxy` của Servlet | Đang đối chiếu tài liệu MVC với WebFlux | Dùng `SecurityWebFilterChain` và `org.springframework.security.web.server` |
| `401` nhưng không biết lỗi credential | Request thiếu header, sai authentication provider hoặc entry point | Kiểm tra cơ chế xác thực đang sử dụng; bật DEBUG cho package authentication liên quan |
| `403` sau đăng nhập | Thiếu authority/role, rule không khớp, CSRF hoặc access denied | Đối chiếu đường dẫn, HTTP method, authority và cấu hình security |
| Log quá nhiều, tốn chi phí | Bật `root=DEBUG/TRACE` hoặc logger security quá rộng | Giảm root, nhắm package nhỏ, đặt thời hạn rồi tắt |
| Mức log thay đổi nhưng khởi động lại mất | Thay đổi bằng Actuator chỉ ở runtime | Cập nhật file/profile nếu cần chính sách lâu dài; nếu điều tra tạm thời thì khôi phục |
| Bật log ở staging làm lộ nội dung request | Logger riêng, cấu hình codec hoặc gateway ghi dữ liệu nhạy cảm | Xem chính sách redaction và quyền truy cập, loại bỏ chi tiết không cần thiết |
| Không nối được log cùng một request | Reactive request đổi thread; thiếu correlation ID | Dùng WebFlux log ID/tracing; không nhóm chỉ theo thread name |

## 9. Checklist khi triển khai

- [ ] Xác định đúng stack là **WebFlux reactive** và đúng Spring profile trên từng môi trường.
- [ ] Đặt logger hẹp nhất đủ chẩn đoán; bắt đầu DEBUG, chỉ dùng TRACE khi thật cần.
- [ ] Thử request công khai, thiếu xác thực, đủ quyền và thiếu quyền; quan sát 200/401/403 theo chính sách thực tế.
- [ ] Kiểm tra `configuredLevel`/`effectiveLevel` nếu có Actuator; kiểm soát quyền truy cập endpoint.
- [ ] Không ghi secrets/PII; có quy định redaction, retention và thời gian bật log.
- [ ] Đo lượng log và latency khi mở mức chi tiết; khôi phục cấu hình sau điều tra.

## Tài liệu tham khảo chính thức

- Spring Boot 3.3 — Externalized Configuration, profile-specific files: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot — Logging: https://docs.spring.io/spring-boot/reference/features/logging.html
- Spring Security — WebFlux Security: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Boot Actuator — Loggers: https://docs.spring.io/spring-boot/reference/actuator/loggers.html
- Spring Boot Actuator — Exposing and securing endpoints: https://docs.spring.io/spring-boot/reference/actuator/endpoints.html
- Spring Framework WebFlux — Logging and sensitive data: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
