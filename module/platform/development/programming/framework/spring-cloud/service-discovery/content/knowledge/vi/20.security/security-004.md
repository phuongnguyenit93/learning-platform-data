# Phạm vi CSRF cho Eureka API và bảo vệ các đường dẫn còn lại

Eureka Client gửi request đăng ký, heartbeat và hủy đăng ký tới REST API của Eureka Server. Các thao tác thay đổi trạng thái thường dùng POST, PUT hoặc DELETE dưới đường dẫn mặc định `/eureka/**`. Spring Security bật CSRF protection cho các request thay đổi trạng thái, nên client backend không có CSRF token có thể nhận `403 Forbidden`.

Cách xử lý là miễn CSRF trong đúng phạm vi API Eureka, nhưng vẫn yêu cầu xác thực và phân quyền. Dashboard, Actuator và endpoint quản trị tiếp tục được bảo vệ bằng CSRF mặc định.

## Vì sao Eureka API gặp CSRF?

CSRF (Cross-Site Request Forgery) bảo vệ các endpoint có thể thay đổi trạng thái khi trình duyệt tự gửi thông tin xác thực của người dùng, chẳng hạn session cookie. Spring Security bật CSRF protection cho các method không an toàn như `POST`, `PUT`, `PATCH` và `DELETE` theo mặc định.

Eureka Client là ứng dụng backend gọi Eureka Server theo giao thức REST. Client không hoạt động như trình duyệt có session và không tự lấy/gửi CSRF token của người dùng. Khi client gửi request đăng ký hoặc heartbeat, CSRF filter có thể chặn request trước khi Eureka Controller xử lý.

| Thao tác Eureka | HTTP method thường dùng | Mục đích |
|---|---|---|
| Đăng ký instance | `POST` | Tạo bản ghi application/instance trong registry |
| Gia hạn lease/heartbeat | `PUT` | Báo instance vẫn hoạt động |
| Hủy đăng ký | `DELETE` | Gỡ instance khỏi registry khi shutdown có kiểm soát |
| Đọc registry | `GET` | Lấy danh sách application/instance |

Các endpoint REST mặc định của Eureka Server nằm dưới `/eureka/**`, ví dụ `/eureka/apps` và `/eureka/apps/{APP_NAME}`. Đường dẫn thực tế có thể thay đổi nếu ứng dụng đặt context path hoặc cấu hình endpoint khác; phải căn cứ URL mà Eureka Client đang gọi.

```mermaid
sequenceDiagram
    participant C as Eureka Client
    participant S as Spring Security
    participant E as Eureka Server
    C->>S: POST /eureka/apps/INVENTORY (Basic Auth)
    S->>S: Kiểm tra CSRF theo request matcher
    Note over S: /eureka/** được miễn CSRF
    S->>S: Xác thực và kiểm tra role
    S->>E: Cho phép request tới Eureka API
    E-->>C: Registration response
```

Miễn CSRF chỉ bỏ yêu cầu CSRF token. Nó không có nghĩa request được phép ẩn danh hoặc được bỏ qua các bước xác thực, phân quyền, network policy và TLS.

## Phạm vi cần miễn: API Eureka

Với cấu hình mặc định, matcher thường dùng là `/eureka/**`. Đây là phạm vi dành cho REST API mà Eureka Client và peer Eureka Server gọi. Không mở rộng matcher thành `/**`, `/api/**` hoặc toàn bộ ứng dụng nếu chỉ mục tiêu là xử lý đăng ký Eureka.

Ví dụ cấu hình Spring Security 6, thường dùng cùng Spring Boot 3:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/actuator/health").permitAll()
                .requestMatchers("/eureka/**").hasRole("REGISTRY_CLIENT")
                .requestMatchers("/actuator/**").hasRole("OPS")
                .anyRequest().hasRole("OPS")
            )
            .httpBasic(Customizer.withDefaults())
            .csrf(csrf -> csrf
                .ignoringRequestMatchers("/eureka/**")
            );
        return http.build();
    }
}
```

Trong ví dụ này, `/eureka/**` không cần CSRF token nhưng vẫn yêu cầu role `REGISTRY_CLIENT`. `/actuator/health` được phép truy cập để phục vụ health probe; chỉ nên làm vậy nếu response không tiết lộ chi tiết nhạy cảm. Các endpoint Actuator còn lại và dashboard Eureka yêu cầu role `OPS`.

`hasRole("REGISTRY_CLIENT")` kiểm tra authority `ROLE_REGISTRY_CLIENT`. Người vận hành cần truy cập dashboard và xem registry cũng có thể được cấp thêm role này. Trong hệ thống thực tế, hãy quản lý user và role bằng nguồn danh tính phù hợp thay vì dùng chung một tài khoản cho tất cả ứng dụng.

### Vì sao không dùng csrf.disable()?

Không dùng cấu hình sau chỉ để sửa lỗi đăng ký Eureka:

```java
http.csrf(csrf -> csrf.disable());
```

Lệnh này tắt CSRF cho toàn bộ SecurityFilterChain. Các form hoặc endpoint thay đổi trạng thái khác trong ứng dụng sẽ không còn được bảo vệ bởi CSRF token. Thay vào đó, dùng `ignoringRequestMatchers("/eureka/**")` để loại trừ đúng REST API của Eureka. Mọi request không khớp matcher vẫn đi qua CSRF filter như bình thường.

## Bảo vệ các đường dẫn còn lại

Khi thiết kế SecurityFilterChain, hãy liệt kê rõ từng nhóm endpoint và quyền cần thiết:

| Đường dẫn | Mục đích | Chính sách gợi ý |
|---|---|---|
| `/eureka/**` | Eureka REST API cho client và peer | Miễn CSRF; vẫn yêu cầu xác thực và role dành cho registry client |
| `/` và dashboard Eureka | Giao diện quan sát registry | Yêu cầu tài khoản vận hành; giữ CSRF mặc định |
| `/actuator/health` | Health probe | Có thể mở trong mạng nội bộ; không hiển thị chi tiết nhạy cảm |
| `/actuator/**` | Metrics, env, beans, config và endpoint quản trị | Chỉ role vận hành; chỉ expose endpoint cần thiết |
| Endpoint quản trị riêng | Refresh, maintenance hoặc thao tác thay đổi cấu hình | Yêu cầu role đặc quyền và giữ CSRF |
| Mọi đường dẫn còn lại | Static resource hoặc endpoint không được liệt kê | Chính sách mặc định nghiêm ngặt; không tự động permit all |

Trong ví dụ SecurityFilterChain, `anyRequest().hasRole("OPS")` khiến dashboard và các đường dẫn còn lại cần quyền vận hành. Có thể điều chỉnh static resources nếu dashboard phiên bản đang dùng yêu cầu truy cập riêng, nhưng phải thêm matcher chính xác và kiểm tra không vô tình mở API quản trị.

Không nên thêm matcher rộng `/**` với `permitAll()` sau khi cấu hình Eureka. Một quy tắc quá rộng có thể làm mất ý nghĩa của các quy tắc bảo vệ trước đó hoặc tạo ra bề mặt truy cập ngoài dự kiến.

## Tài khoản và role minh họa

Để SecurityFilterChain có thể áp dụng, ứng dụng cần một `UserDetailsService` hoặc cơ chế xác thực tương đương có các role tương ứng. Đoạn dưới dùng in-memory user để minh họa trong lab; không dùng kho tài khoản in-memory làm phương án quản lý danh tính production.

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;

@Configuration
public class UserConfiguration {
    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(
            PasswordEncoder encoder,
            @Value("${security.registry-client.username}") String clientUsername,
            @Value("${security.registry-client.password}") String clientPassword,
            @Value("${security.operator.username}") String operatorUsername,
            @Value("${security.operator.password}") String operatorPassword) {
        var registryClient = User.withUsername(clientUsername)
            .password(encoder.encode(clientPassword))
            .roles("REGISTRY_CLIENT")
            .build();
        var operator = User.withUsername(operatorUsername)
            .password(encoder.encode(operatorPassword))
            .roles("REGISTRY_CLIENT", "OPS")
            .build();
        return new InMemoryUserDetailsManager(registryClient, operator);
    }
}
```

Đưa username/password từ secret manager hoặc biến môi trường vào cấu hình:

```yaml
security:
  registry-client:
    username: ${EUREKA_CLIENT_USERNAME}
    password: ${EUREKA_CLIENT_PASSWORD}
  operator:
    username: ${EUREKA_OPS_USERNAME}
    password: ${EUREKA_OPS_PASSWORD}

management:
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    health:
      show-details: never
```

Trong production, thay `InMemoryUserDetailsManager` bằng user store hoặc identity provider phù hợp, phân quyền riêng cho client, peer và operator, xoay vòng credential và kiểm soát audit log. Không commit mật khẩu vào Git hoặc ghi chúng vào log.

## Eureka Client xác thực với Eureka Server

Eureka Client có thể dùng HTTP Basic bằng cách đặt username/password trong URL của `service-url.defaultZone`. Ví dụ cấu hình client trong môi trường container:

```yaml
eureka:
  client:
    service-url:
      defaultZone: "http://${EUREKA_CLIENT_USERNAME}:${EUREKA_CLIENT_PASSWORD}@eureka-server:8761/eureka/"
    register-with-eureka: true
    fetch-registry: true
```

Khi URL chứa thông tin xác thực, Eureka Client có thể gửi Basic Auth tới Eureka Server. `eureka-server` là hostname nội bộ có thể phân giải từ network của client; thay bằng hostname và port thực tế của registry trong môi trường triển khai.

Không đặt credential trực tiếp trong YAML được commit. Nếu mật khẩu có ký tự đặc biệt trong URI user-info như `@`, `:`, `/` hoặc `%`, cần URL-encode đúng thành phần user/password hoặc dùng cơ chế transport credential phù hợp với phiên bản đang dùng. Hãy kiểm tra log để bảo đảm URL có credential không bị in ra.

### Eureka Server peer cũng là client

Trong cụm Eureka peer-aware, mỗi Eureka Server có thể đăng ký và fetch registry từ peer. Các request peer tới `/eureka/**` cũng cần được xác thực và được cấp role phù hợp. Cấu hình URL peer có credential tương tự client thông thường:

```yaml
eureka:
  client:
    register-with-eureka: true
    fetch-registry: true
    service-url:
      defaultZone: "http://${EUREKA_PEER_USERNAME}:${EUREKA_PEER_PASSWORD}@eureka-b:8762/eureka/"
```

Với server standalone không có peer, cấu hình `register-with-eureka: false` và `fetch-registry: false` để không phát sinh request client tới peer không tồn tại. Dù vậy, Eureka API và dashboard vẫn cần chính sách xác thực riêng.

## CSRF không thay thế authentication và authorization

Ba cơ chế này giải quyết ba vấn đề khác nhau:

| Cơ chế | Câu hỏi cần trả lời | Ví dụ trong Eureka Server |
|---|---|---|
| CSRF protection | Request thay đổi trạng thái có được khởi tạo từ ngữ cảnh trình duyệt hợp lệ không? | CSRF token cho form/dashboard hoặc endpoint quản trị |
| Authentication | Ai đang gửi request? | HTTP Basic, client certificate hoặc cơ chế danh tính khác |
| Authorization | Danh tính đó được phép làm gì? | Role registry client được gọi API đăng ký; role OPS được truy cập dashboard/Actuator |

Khi miễn CSRF cho `/eureka/**`, request không có token vẫn phải qua authentication và authorization. Nếu bỏ luôn hai bước này hoặc dùng `permitAll`, bất kỳ workload nào truy cập được endpoint có thể thử đăng ký, thay đổi trạng thái hoặc đọc registry tùy API.

Không dùng CORS như cách thay thế CSRF. CORS chủ yếu điều khiển việc trình duyệt có được đọc response cross-origin; nó không phải cơ chế xác thực và không bảo đảm ngăn mọi request làm thay đổi trạng thái.

## Rủi ro khi dùng HTTP Basic và browser

CSRF thường bảo vệ ứng dụng dùng session cookie, nhưng HTTP Basic cũng cần được cân nhắc nếu trình duyệt người dùng có thể truy cập Eureka API. Trình duyệt có thể lưu hoặc tự gửi thông tin xác thực Basic trong một số tình huống; vì vậy, việc miễn CSRF cho `/eureka/**` không nên được xem là an toàn nếu API đó mở rộng ra mạng người dùng hoặc Internet.

Để giảm rủi ro:

- Chỉ cho workload và peer được phép truy cập `/eureka/**` bằng firewall, security group hoặc network policy.
- Dùng tài khoản machine-to-machine riêng; không dùng credential operator cho ứng dụng.
- Bật TLS để bảo vệ Basic Auth và nội dung registry trên đường truyền.
- Cân nhắc mTLS hoặc identity giữa workload nếu hạ tầng hỗ trợ.
- Không expose Eureka API trực tiếp ra Internet; đặt registry trong mạng quản trị/backend.
- Bảo vệ dashboard bằng danh tính người vận hành và giữ CSRF cho các đường dẫn giao diện/quản trị.
- Giới hạn quyền đọc/ghi theo khả năng phân quyền của lớp bảo vệ đang triển khai.

Basic Auth chỉ mã hóa username/password bằng Base64 trong header, không mã hóa đường truyền. Không dùng HTTP thuần qua mạng không tin cậy.

## Nếu Eureka API chạy dưới context path khác

Matcher `/eureka/**` giả định REST API dùng path mặc định. Nếu ứng dụng có `server.servlet.context-path`, reverse proxy thêm hoặc bỏ prefix, hoặc cấu hình server thay đổi base path, cần xác định path mà Spring Security nhìn thấy và điều chỉnh matcher tương ứng.

Không nên đoán matcher chỉ từ URL bên ngoài. Hãy kiểm tra:

1. Giá trị `eureka.client.service-url.defaultZone` của client.
2. Context path của Spring Boot và cấu hình reverse proxy.
3. Request path thực tế trong access log hoặc test.
4. SecurityFilterChain nào được chọn nếu ứng dụng có nhiều chain.
5. Kết quả CSRF matcher đối với request Eureka và request ngoài phạm vi.

Nếu có nhiều `SecurityFilterChain`, chain có `securityMatcher` cụ thể và `@Order` cao hơn có thể xử lý request trước. Bảo đảm `/eureka/**` đi qua đúng chain đã miễn CSRF; các request còn lại phải khớp chain bảo vệ chung. Một chain không được match không có nghĩa request tự động an toàn.

## Kiểm thử phạm vi CSRF

Không chỉ kiểm tra Eureka Client đăng ký thành công. Cần xác minh cả request trong phạm vi miễn CSRF lẫn request bên ngoài vẫn được bảo vệ.

Ví dụ kiểm thử với MockMvc và Spring Security Test:

```java
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class EurekaSecurityTest {
    @Autowired
    MockMvc mockMvc;

    @Test
    void eurekaApiDoesNotRequireCsrfButStillRequiresRole() throws Exception {
        mockMvc.perform(post("/eureka/apps/INVENTORY")
                .with(user("registry-client").roles("REGISTRY_CLIENT")))
            .andExpect(result -> assertNotEquals(
                403, result.getResponse().getStatus()));
    }

    @Test
    void eurekaApiStillRequiresAuthentication() throws Exception {
        mockMvc.perform(get("/eureka/apps"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void otherMutatingPathsStillRequireCsrf() throws Exception {
        mockMvc.perform(post("/ops/maintenance")
                .with(user("operator").roles("OPS", "REGISTRY_CLIENT")))
            .andExpect(status().isForbidden());
    }

    @Test
    void otherMutatingPathsAcceptValidCsrfToken() throws Exception {
        mockMvc.perform(post("/ops/maintenance")
                .with(user("operator").roles("OPS", "REGISTRY_CLIENT"))
                .with(csrf()))
            .andExpect(result -> assertNotEquals(
                403, result.getResponse().getStatus()));
    }
}
```

Các test trên minh họa ranh giới filter: request tới Eureka API không bị từ chối chỉ vì thiếu CSRF token; request ngoài phạm vi vẫn bị chặn khi thiếu token; xác thực và role của Eureka API vẫn được kiểm tra. Test endpoint thật có thể trả `404`, `405` hoặc lỗi nghiệp vụ tùy controller và payload, nên không nên ép tất cả test phải trả một status thành công cụ nếu mục tiêu chỉ là xác minh CSRF.

Bổ sung test cho trường hợp user chỉ có role `OPS` gọi API registry, hoặc user `REGISTRY_CLIENT` gọi dashboard/Actuator. Các request đó phải bị từ chối theo authorization policy đã định nghĩa.

## Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Eureka Client nhận `403` khi đăng ký | CSRF vẫn áp dụng cho `/eureka/**` hoặc matcher sai path | Kiểm tra request URL thực tế và `ignoringRequestMatchers` |
| Eureka Client nhận `401` | Thiếu/sai Basic Auth hoặc credential chưa được bind | Kiểm tra user, password, URL và secret injection |
| Eureka Client nhận `403` dù đã xác thực | User thiếu role `REGISTRY_CLIENT` hoặc request khớp rule khác | Kiểm tra authority và thứ tự authorization matcher |
| Dashboard không mở được | Tài khoản không có role OPS hoặc static resource bị rule chặn | Kiểm tra request path và quyền dashboard |
| Actuator health trả `401` | Matcher health chưa được permit hoặc endpoint path khác | Kiểm tra endpoint exposure và security matcher |
| Endpoint quản trị chấp nhận POST không token | CSRF đã bị tắt toàn cục hoặc matcher quá rộng | Bật lại CSRF và chỉ ignore `/eureka/**` |
| Peer replication lỗi xác thực | Peer URL thiếu credential hoặc peer user không có role | Đồng bộ credential/role hai chiều và kiểm tra TLS |
| API bị truy cập từ mạng ngoài | Chỉ dựa vào CSRF hoặc Basic Auth, thiếu network boundary | Giới hạn network, bật TLS/mTLS và rà soát firewall |

Khi điều tra một request bị chặn, xác định response là `401` hay `403`: `401` thường chỉ ra xác thực chưa thành công; `403` có thể do CSRF hoặc authorization. Bật log Spring Security có kiểm soát trong môi trường test để xem filter và authorization decision, nhưng không ghi header Authorization hoặc token.

## Checklist triển khai

1. Xác nhận base path REST API Eureka; mặc định thường là `/eureka/**`.
2. Chỉ miễn CSRF cho matcher của Eureka API cần phục vụ client/peer.
3. Giữ `httpBasic`, mTLS hoặc cơ chế authentication tương đương.
4. Yêu cầu role riêng cho registry client; tách quyền operator khi có thể.
5. Giữ CSRF cho dashboard, Actuator và endpoint quản trị ngoài Eureka API.
6. Không dùng `csrf.disable()` hoặc `permitAll()` cho toàn ứng dụng.
7. Cấu hình credential bằng secret manager/environment, không commit vào Git.
8. Dùng TLS và giới hạn network truy cập registry; không expose Eureka API trực tiếp ra Internet.
9. Kiểm tra context path, reverse proxy và thứ tự nhiều SecurityFilterChain.
10. Viết test xác nhận Eureka API không cần CSRF nhưng vẫn cần authentication/role, còn POST ngoài phạm vi vẫn cần token.

## Kết luận

Với Eureka Server, các request đăng ký, heartbeat và hủy đăng ký dưới `/eureka/**` là luồng machine-to-machine nên thường cần được miễn CSRF token để Eureka Client hoạt động. Phạm vi miễn phải hẹp và không làm mất authentication hoặc authorization: client/peer vẫn cần credential và role phù hợp. Dashboard, Actuator và endpoint quản trị còn lại tiếp tục được bảo vệ bằng CSRF cùng chính sách quyền riêng. Kết hợp matcher chính xác, TLS, network isolation, credential riêng và test 401/403 giúp Eureka API hoạt động mà không mở rộng vùng không được bảo vệ sang phần còn lại của server.
