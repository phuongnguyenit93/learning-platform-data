# Endpoint quản trị trả 404, 401 hoặc 403

Các endpoint quản trị của một ứng dụng Spring Cloud thường được cung cấp qua Spring Boot Actuator. Spring Cloud bổ sung một số endpoint riêng, chẳng hạn `refresh` của Spring Cloud Context, nhưng việc ánh xạ HTTP, mở endpoint và kiểm soát truy cập vẫn phụ thuộc vào cấu hình management của Spring Boot và Spring Security. Vì vậy, cùng một URL có thể trả `404 Not Found`, `401 Unauthorized` hoặc `403 Forbidden` tùy endpoint có tồn tại, có được expose và request đã vượt qua các lớp bảo mật hay chưa.

Khi xử lý sự cố, cần xác định request đang đến đúng tiến trình, cổng và đường dẫn hay không trước khi thay đổi quyền truy cập. Không nên mở toàn bộ Actuator hoặc chuyển endpoint sang `permitAll` chỉ để làm mất lỗi.

## 1. Hiểu các lớp tạo nên endpoint quản trị

Với ứng dụng web, Spring Boot Actuator thường ánh xạ endpoint ID thành đường dẫn HTTP có tiền tố `/actuator`. Ví dụ, endpoint ID `health` có đường dẫn mặc định là `/actuator/health`. Endpoint chỉ có thể được gọi qua HTTP khi endpoint đó khả dụng và được expose trên HTTP. Hai điều kiện này độc lập: một endpoint có thể tồn tại trong ApplicationContext nhưng không được expose, hoặc bị giới hạn quyền truy cập ở mức Actuator.

Spring Cloud Context bổ sung các thao tác quản trị như `refresh`. Endpoint này làm mới các bean thuộc `@RefreshScope`; nó không phải endpoint mặc định của mọi ứng dụng Spring Boot. Ứng dụng phải có Spring Cloud Context phù hợp và expose endpoint `refresh` qua Actuator. Nếu dùng Spring Cloud Bus, `busrefresh` là endpoint khác, có mục đích phát tán thao tác refresh đến các instance thông qua Bus.

Một request đến endpoint quản trị thường đi qua các lớp sau:

1. DNS, load balancer, ingress hoặc API gateway chuyển request đến đúng ứng dụng và đúng cổng.
2. Management server xác định context path, management base path và endpoint ID.
3. Actuator kiểm tra endpoint có được khởi tạo, được phép truy cập và được expose qua HTTP hay không.
4. Spring Security xác thực danh tính, kiểm tra role/authority và các cơ chế như CSRF.
5. Endpoint kiểm tra HTTP method và thực thi thao tác tương ứng.

Một lớp phía trước có thể trả lỗi trước khi request đến lớp phía sau. Chẳng hạn, gateway có thể trả `404` vì route không khớp; Spring Security có thể trả `401` vì thiếu thông tin xác thực; CSRF có thể từ chối một request `POST` bằng `403`.

## 2. Phân biệt 404, 401 và 403

| Mã HTTP | Ý nghĩa thường gặp | Nhóm nguyên nhân cần kiểm tra |
|---|---|---|
| `404 Not Found` | Không tìm thấy route hoặc endpoint tại URL được gọi | Sai host/port/path, endpoint chưa có trong classpath, endpoint chưa được expose, endpoint bị vô hiệu hóa hoặc bị gateway che giấu |
| `401 Unauthorized` | Request chưa được xác thực hoặc thông tin xác thực không hợp lệ | Thiếu Basic credentials, bearer token, cookie hoặc token hết hạn/sai issuer/audience |
| `403 Forbidden` | Request đã được nhận diện nhưng không được phép thực hiện thao tác | Thiếu role/authority, sai rule trong `SecurityFilterChain`, CSRF token thiếu/sai hoặc quyền truy cập Actuator bị giới hạn |
| `405 Method Not Allowed` | URL có thể tồn tại nhưng HTTP method không được endpoint hỗ trợ | Gọi `GET` thay vì `POST`, hoặc ngược lại; kiểm tra header `Allow` và tài liệu endpoint |

Đây là cách diễn giải ban đầu, không phải quy tắc tuyệt đối. Ứng dụng có thể tùy chỉnh `AuthenticationEntryPoint`, `AccessDeniedHandler`, gateway hoặc reverse proxy để thay đổi mã phản hồi, thậm chí trả `404` nhằm che giấu sự tồn tại của tài nguyên. Hãy đối chiếu response header, body và log của từng lớp để tìm nơi phát sinh lỗi.

## 3. Xử lý lỗi 404: endpoint hoặc đường dẫn không được công bố

### 3.1. Xác nhận dependency và endpoint ID

Kiểm tra dependency runtime trước khi kiểm tra URL. Ứng dụng cần Spring Boot Actuator để cung cấp bề mặt HTTP quản trị. Với endpoint thuộc Spring Cloud, cần có module Spring Cloud tương ứng trên runtime classpath. Ví dụ, endpoint `refresh` thuộc Spring Cloud Context; một ứng dụng chỉ có Spring Boot Actuator không tự động có endpoint này.

Nếu dependency đã có, xác nhận endpoint được tạo trong cấu hình hiện tại. Một số endpoint phụ thuộc vào loại ứng dụng, bean hoặc dependency khác. Ví dụ, endpoint `prometheus` cần registry Prometheus; các endpoint tích hợp khác cũng có điều kiện tương tự. Đừng suy ra endpoint tồn tại chỉ từ việc ứng dụng có `spring-boot-starter-actuator`.

### 3.2. Kiểm tra cấu hình exposure

Spring Boot chỉ expose endpoint `health` qua HTTP theo mặc định. Vì vậy, gọi `/actuator/info`, `/actuator/metrics` hoặc `/actuator/refresh` có thể trả `404` nếu chưa được thêm vào danh sách exposure.

Ví dụ, cấu hình dưới đây expose ba endpoint cần dùng trong môi trường nội bộ:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info,refresh"
```

`include` nhận endpoint ID, không nhận URL đầy đủ. Nếu muốn expose endpoint Spring Cloud Bus, cần thêm ID `busrefresh` và xác nhận dependency/cấu hình Bus đã có. Khi đồng thời cấu hình `exclude`, danh sách `exclude` có ưu tiên cao hơn `include`; một endpoint vẫn có thể không xuất hiện dù đã nằm trong `include`.

Không dùng `include: "*"` như cách sửa mặc định. Các endpoint như `env`, `configprops`, `beans`, `loggers`, `heapdump` hoặc `shutdown` có thể làm lộ thông tin hoặc cho phép thay đổi trạng thái ứng dụng. Chỉ expose endpoint thực sự cần thiết và bảo vệ nó bằng mạng quản trị cùng cơ chế xác thực phù hợp.

### 3.3. Kiểm tra quyền truy cập ở mức Actuator

Exposure và quyền truy cập endpoint là hai cấu hình khác nhau. Trên các phiên bản Spring Boot có hỗ trợ endpoint access properties, `management.endpoints.access.default`, `management.endpoint.<id>.access` và `management.endpoints.access.max-permitted` có thể giới hạn quyền truy cập. Ví dụ, đặt access mặc định thành `none` sẽ làm các endpoint không được cấp quyền riêng trở nên không khả dụng; endpoint bị giới hạn ở mức này có thể bị loại khỏi ApplicationContext.

```yaml
management:
  endpoints:
    access:
      default: none
  endpoint:
    health:
      access: read-only
    refresh:
      access: unrestricted
```

Đây là ví dụ về cấu hình opt-in: chỉ những endpoint được cấp quyền riêng mới khả dụng. `refresh` là thao tác ghi nên `read-only` không phù hợp nếu mục tiêu là gọi refresh. Hãy kiểm tra cả `max-permitted`, vì giới hạn toàn cục này có thể chặn quyền rộng hơn được cấu hình ở endpoint riêng. Với phiên bản Spring Boot cũ hơn, đối chiếu đúng tài liệu của phiên bản đang chạy trước khi dùng các property này.

### 3.4. Xác minh port và đường dẫn thực tế

Đường dẫn mặc định `/actuator/{id}` có thể thay đổi bởi nhiều cấu hình:

- `management.endpoints.web.base-path` đổi tiền tố, ví dụ `/manage`.
- `server.servlet.context-path` thêm tiền tố cho ứng dụng Spring MVC khi management server dùng chung cổng.
- `spring.webflux.base-path` ảnh hưởng ứng dụng WebFlux khi management server dùng chung cổng.
- `management.server.port` đặt management server trên cổng riêng.
- `management.server.address` giới hạn địa chỉ lắng nghe; khi chỉ bind vào loopback, máy bên ngoài không thể truy cập trực tiếp.
- `management.endpoints.web.path-mapping` đổi path của một endpoint cụ thể.

Ví dụ, nếu management server chạy cổng `8081` và base path là `/manage`, endpoint refresh được gọi tại `http://localhost:8081/manage/refresh`, không phải `http://localhost:8080/actuator/refresh`:

```yaml
management:
  server:
    port: 8081
  endpoints:
    web:
      base-path: /manage
      exposure:
        include: "health,info,refresh"
```

Khi có ingress hoặc API gateway, kiểm tra cả URL bên ngoài và URL nội bộ mà ứng dụng nhận được. Một prefix được thêm ở gateway nhưng không được rewrite, hoặc bị rewrite hai lần, có thể khiến request đi đến route không tồn tại. Cũng cần xác minh Service/Ingress đang forward đến cổng ứng dụng hay cổng management.

## 4. Xử lý lỗi 401: xác thực chưa thành công

Nếu Spring Security có trên classpath và ứng dụng không khai báo `SecurityFilterChain` riêng, Spring Boot tự cấu hình bảo vệ các Actuator endpoint ngoại trừ `health`. Trong trường hợp này, request không có thông tin xác thực hợp lệ thường nhận `401`.

Kiểm tra lần lượt:

1. Client có gửi đúng loại thông tin xác thực mà server yêu cầu không: HTTP Basic, bearer token, session cookie hoặc cơ chế khác.
2. Với Basic authentication, kiểm tra username/password và cấu hình `UserDetailsService` hoặc identity provider.
3. Với bearer token, kiểm tra chữ ký, issuer, audience, thời hạn, clock skew và scope/claim mà ứng dụng dùng để ánh xạ authority.
4. Nếu request đi qua gateway, xác minh gateway có chuyển tiếp `Authorization` header hay không. Không ghi token hoặc mật khẩu vào log khi kiểm tra.
5. Xem response header `WWW-Authenticate` và log của authentication provider để xác định cơ chế xác thực đang được áp dụng.

Một nguyên nhân phổ biến là ứng dụng đã khai báo `SecurityFilterChain` cho API nghiệp vụ. Khi có bean này, cấu hình bảo mật Actuator tự động của Spring Boot sẽ nhường quyền kiểm soát cho cấu hình tùy chỉnh. Nếu chain mới chỉ match `/api/**`, request Actuator có thể không khớp chain nào và không nhận được các rule bảo vệ mà nhóm dự định. Nếu một chain tổng quát hơn khớp trước, chain đó có thể áp dụng rule khác với rule dành riêng cho management endpoint.

Với ứng dụng Spring MVC/Servlet, có thể dùng `EndpointRequest` để match endpoint Actuator thay vì hard-code `/actuator/**`. Ví dụ sau bảo vệ mọi Actuator endpoint bằng role `ENDPOINT_ADMIN`, đồng thời cho phép truy cập health:

```java
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class ManagementSecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain actuatorSecurity(HttpSecurity http) throws Exception {
        http.securityMatcher(EndpointRequest.toAnyEndpoint())
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(EndpointRequest.to("health")).permitAll()
                .anyRequest().hasRole("ENDPOINT_ADMIN"))
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
```

Ví dụ dùng HTTP Basic để minh họa; trong hệ thống thực tế, thay cơ chế này bằng cơ chế xác thực đang được ứng dụng sử dụng, chẳng hạn OAuth2 Resource Server với JWT. Chain thứ hai là rule cho request nghiệp vụ; nếu ứng dụng đã có chain riêng, hãy tích hợp rule phù hợp vào cấu hình hiện có. Khi tự khai báo chain cho Actuator, đừng bỏ quên việc bảo vệ các route còn lại.

Tên role trong `hasRole("ENDPOINT_ADMIN")` được Spring Security hiểu là authority `ROLE_ENDPOINT_ADMIN`. Nếu identity provider cấp authority `ENDPOINT_ADMIN` mà không có tiền tố `ROLE_`, hãy dùng `hasAuthority("ENDPOINT_ADMIN")` hoặc điều chỉnh mapping role cho nhất quán.

## 5. Xử lý lỗi 403: đã xác thực nhưng bị từ chối

### 5.1. Kiểm tra role và authority

Khi request đã xác thực nhưng người dùng không có quyền phù hợp, Spring Security thường trả `403`. Kiểm tra principal thực tế, danh sách authorities và biểu thức trong `authorizeHttpRequests`. Đặc biệt, phân biệt `hasRole("OPS")` với `hasAuthority("ROLE_OPS")`: `hasRole` tự thêm tiền tố `ROLE_`, còn `hasAuthority` so sánh đúng chuỗi authority được khai báo.

Đối với cấu hình nhiều `SecurityFilterChain`, kiểm tra thứ tự `@Order` và matcher của từng chain. Chain có thứ tự ưu tiên cao hơn và matcher khớp request sẽ được áp dụng trước. Một chain tổng quát như `anyRequest()` đặt trước chain Actuator có thể khiến rule chuyên biệt không bao giờ được dùng.

### 5.2. Kiểm tra CSRF với thao tác ghi

Các endpoint đọc thường dùng `GET`; endpoint thay đổi trạng thái có thể yêu cầu `POST`, `PUT` hoặc `DELETE`. Spring Security bật CSRF protection theo mặc định. Vì vậy, request ghi thiếu hoặc gửi sai CSRF token có thể bị trả `403`, ngay cả khi username/password hoặc bearer token đã hợp lệ.

Spring Cloud Context sử dụng thao tác `POST` cho endpoint `refresh`. Nếu `GET /actuator/refresh` không hoạt động, hãy kiểm tra method mà endpoint hỗ trợ; nếu `POST` trả `403`, kiểm tra CSRF trước khi thay đổi role. Với client trình duyệt dùng session cookie, cần gửi CSRF token đúng cách. Chỉ cân nhắc bỏ qua CSRF cho đúng management endpoint khi API chỉ phục vụ client máy-máy, không dựa vào cookie tự động của trình duyệt, và đã có xác thực cùng giới hạn mạng thích hợp. Không tắt CSRF toàn ứng dụng chỉ để sửa một request quản trị.

### 5.3. Kiểm tra giới hạn access của Actuator

Rule Spring Security có thể cho phép request nhưng Actuator vẫn giới hạn thao tác. Trên phiên bản hỗ trợ access properties, kiểm tra:

- `management.endpoints.access.default`: quyền mặc định của các endpoint.
- `management.endpoint.<id>.access`: quyền cụ thể của endpoint.
- `management.endpoints.access.max-permitted`: giới hạn cao nhất áp dụng toàn cục.

`read-only` chỉ phù hợp với thao tác đọc. Nếu endpoint cần thực hiện write operation, giới hạn read-only có thể làm thao tác bị từ chối. Cần phân biệt lỗi từ Actuator với lỗi từ Spring Security bằng log và response của request, thay vì chỉ tăng quyền cho mọi endpoint.

## 6. Quy trình chẩn đoán theo thứ tự

Thực hiện quy trình dưới đây với cùng một request, cùng một môi trường và cùng một instance để tránh so sánh nhầm kết quả giữa các node:

1. **Ghi lại request chính xác:** HTTP method, scheme, hostname, port, path, query string, header xác thực và instance đích. Che token, cookie và mật khẩu khi lưu bằng chứng.
2. **Gọi trực tiếp management server:** nếu có `management.server.port`, thử đúng cổng đó từ máy hoặc container có thể truy cập. So sánh với request qua ingress/gateway để khoanh vùng lớp tạo lỗi.
3. **Kiểm tra endpoint nền:** gọi endpoint `health` trên cùng management port và base path. Nếu health cũng `404`, ưu tiên kiểm tra route, cổng, context path và Actuator web exposure. Nếu health hoạt động nhưng endpoint khác `404`, kiểm tra endpoint ID, dependency, exposure và access.
4. **Đối chiếu cấu hình hiệu lực:** xem cấu hình theo profile, biến môi trường, command-line argument và remote Config Server. Chú ý các property `management.endpoints.web.exposure.*`, `management.endpoints.web.base-path`, `management.server.*`, `management.endpoint.*.access` và các cấu hình override từ nguồn ngoài.
5. **Xác định lớp bảo mật:** kiểm tra `SecurityFilterChain`, matcher, thứ tự chain, authentication provider, authorities và CSRF. Tạm bật log `org.springframework.security` ở mức DEBUG trong môi trường kiểm thử hoặc trong thời gian ngắn; không để log nhạy cảm tồn tại lâu dài.
6. **Gửi lại đúng method:** dùng `GET` cho thao tác đọc và `POST` cho refresh. Nếu nhận `405`, kiểm tra header `Allow`; nếu nhận `401` hoặc `403`, tiếp tục xử lý xác thực, quyền và CSRF theo các mục trên.
7. **Kiểm tra sau khi sửa:** xác nhận endpoint chỉ được expose trên đúng management port, client hợp lệ truy cập được, client thiếu quyền vẫn bị từ chối và route nghiệp vụ không bị ảnh hưởng.

Ví dụ kiểm tra một management server chạy tại cổng `8081`, base path `/manage`:

```bash
# Kiểm tra đường dẫn và response header của endpoint health
curl -i http://localhost:8081/manage/health

# Gọi thao tác refresh bằng POST; nếu CSRF được bật, request cần token hợp lệ
curl -i -u "$OPS_USER:$OPS_PASSWORD" \
  -X POST http://localhost:8081/manage/refresh
```

Nếu gọi trực tiếp trả `200` nhưng qua gateway trả `404`, tập trung kiểm tra route và rewrite rule của gateway. Nếu cả hai trả `401`, kiểm tra credential/token và rule xác thực. Nếu chỉ thao tác `POST` trả `403`, kiểm tra CSRF và quyền write của endpoint trước khi thay đổi role.

## 7. Ví dụ tình huống: `/actuator/refresh` trả 404 rồi chuyển thành 403

Một service dùng Spring Cloud Config cần refresh các bean `@RefreshScope` sau khi cấu hình từ xa thay đổi. Nhóm vận hành gọi `POST /actuator/refresh` nhưng nhận `404`.

**Bước 1 — Kiểm tra endpoint có được expose.** Ứng dụng đã có Spring Cloud Context, nhưng cấu hình chỉ expose `health`. Bổ sung `refresh` vào danh sách exposure:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,refresh"
```

Sau khi khởi động lại hoặc áp dụng cấu hình theo cơ chế triển khai của ứng dụng, request đã đến đúng endpoint nhưng nhận `403`.

**Bước 2 — Kiểm tra Spring Security và CSRF.** Principal vận hành đã được xác thực và có role quản trị, nhưng request `POST` thiếu CSRF token. Vì ứng dụng vẫn dùng cơ chế session/cookie cho client trình duyệt, CSRF protection đang hoạt động. Nhóm vận hành cần dùng token hợp lệ theo cơ chế hiện tại hoặc thiết kế riêng một luồng machine-to-machine được bảo vệ bằng token, giới hạn mạng và rule CSRF chỉ áp dụng cho endpoint phù hợp.

**Bước 3 — Xác minh kết quả.** Gọi lại `POST /actuator/refresh` với phương thức xác thực và CSRF phù hợp. Xác nhận response thành công, log cho thấy thao tác refresh đã chạy và bean thuộc `@RefreshScope` được khởi tạo lại ở lần truy cập tiếp theo. Nếu ứng dụng có nhiều instance, lưu ý gọi `refresh` chỉ tác động instance nhận request; dùng Spring Cloud Bus và endpoint `busrefresh` khi kiến trúc cần phát tán sự kiện refresh đến nhiều instance.

## 8. Lưu ý về phiên bản và vận hành an toàn

- Cấu hình exposure và đường dẫn management cần được đối chiếu với tài liệu đúng phiên bản Spring Boot đang chạy. Không mặc định mọi thuộc tính mới của Boot 4 đều có mặt trong Boot 3.x.
- Với Spring Boot 3.x, `EndpointRequest` cho Servlet nằm trong package `org.springframework.boot.actuate.autoconfigure.security.servlet`. Từ Spring Boot 4.x, package trong ví dụ chính thức là `org.springframework.boot.security.autoconfigure.actuate.web.servlet`. Khi nâng cấp Boot, cập nhật import theo phiên bản thực tế.
- Chọn Spring Cloud release train tương thích với Spring Boot. Tại thời điểm viết, bảng phát hành chính thức liệt kê Spring Cloud 2025.1.4 hỗ trợ Boot 4.0.9, Spring Cloud 2025.0.3 hỗ trợ Boot 3.5.15 và Spring Cloud 2024.0.3 hỗ trợ Boot 3.4.12. Không suy luận tương thích chỉ từ số phiên bản major; hãy kiểm tra bảng tương thích mới nhất trước khi nâng cấp.
- Không dùng `permitAll`, `include: "*"` hoặc tắt CSRF toàn cục như một cách sửa lỗi nhanh trên production. Chỉ expose các endpoint cần thiết, đặt management server trong mạng quản trị, giới hạn role và theo dõi audit log.
- Endpoint `refresh` thay đổi trạng thái runtime của ứng dụng. Chỉ cấp quyền cho tài khoản vận hành được kiểm soát, giới hạn tần suất gọi và xác nhận tác động đến các bean cần refresh.

## Tài liệu tham khảo

1. [Spring Boot 3.5 — Actuator Endpoints](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html)
2. [Spring Boot 4.x — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
3. [Spring Boot — Monitoring and Management Over HTTP](https://docs.spring.io/spring-boot/reference/actuator/monitoring.html)
4. [Spring Cloud Commons — Spring Cloud Context: Application Context Services](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html)
5. [Spring Cloud Release — Release Train Reference Documentation](https://docs.spring.io/spring-cloud-release/reference/index.html)
