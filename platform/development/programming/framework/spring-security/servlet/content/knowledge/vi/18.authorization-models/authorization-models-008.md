# Sự kiện phân quyền và theo dõi các quyết định bị từ chối

> **Phạm vi:** Spring Security **Servlet stack**, Java 17+, Spring Boot 3.x / Spring Security 6.x. Bài tập trung vào **authorization events**: khi `AuthorizationManager` quyết định không cho phép một request, làm sao công bố/nhận `AuthorizationDeniedEvent`, liên hệ quyết định với HTTP 403/401 mà **không đánh đồng** mọi lỗi 403 với authorization denial, đo đạc để phát hiện bất thường và ghi audit an toàn. Ví dụ minh họa có `AuthorizationEventPublisher`, `SpringAuthorizationEventPublisher`, `@EventListener`, một `SecurityFilterChain`, kiểm thử `MockMvc` và ví dụ Java 17 chạy trực tiếp. Không coi sự kiện này là cơ chế tự cấp/từ chối quyền thay cho authorization policy.

## 1. Vấn đề thực tế: “403” chưa giải thích được điều gì

Một ứng dụng có thể trả HTTP 403 vì nhiều nguyên nhân:

- User **đã xác thực**, nhưng thiếu `ROLE_ADMIN` khi gọi `GET /admin`.
- User có role phù hợp nhưng **POST thiếu hoặc sai CSRF token**, nên `CsrfFilter` chặn trước khi authorization của endpoint được đánh giá.
- Một controller, gateway hoặc `AccessDeniedHandler` tùy chỉnh tự trả 403.
- Một `@PreAuthorize` ở service từ chối dù HTTP-level authorization cho request đi tiếp.
- Chính sách về object/tenant/ownership trong business service bác bỏ quyền truy cập vào bản ghi cụ thể.

Mặt khác, người dùng **chưa xác thực** có thể nhận 401 hoặc 302 redirect tới trang đăng nhập, chứ không nhất thiết 403. Vì vậy “đếm tất cả status 403” là một **metric HTTP**, không phải một tập hợp trung thực của những **quyết định từ chối phân quyền**.

**Câu hỏi bài học:** làm sao quan sát lúc Spring Security đã thực sự ra **authorization decision** bị từ chối, phân biệt với authentication failure và CSRF failure, rồi dùng tín hiệu ấy để debug, audit, cảnh báo mà không lộ dữ liệu nhạy cảm?

### Mô hình logic

~~~text
HTTP request
  |
  v
FilterChainProxy -> SecurityFilterChain phù hợp
  |
  | Authentication filter / SecurityContext
  |   -> xác định principal + GrantedAuthority
  |
  | CsrfFilter (khi cần)
  |   -> CSRF invalid? request có thể bị 403 NGAY Ở ĐÂY
  |
  v
AuthorizationFilter
  |
  | chọn AuthorizationManager theo request matcher
  | -> tạo / thu được kết quả authorization
  |
  +-- GRANTED
  |      -> cho tiếp đến Servlet/MVC/controller
  |
  +-- DENIED
         |
         +-- AuthorizationEventPublisher
         |      -> AuthorizationDeniedEvent
         |      -> listener an toàn (audit/metrics/alerts)
         |
         +-- AccessDeniedException
                -> ExceptionTranslationFilter
                -> AccessDeniedHandler / AuthenticationEntryPoint
                -> thường 403 hoặc 401/302 tùy ngữ cảnh
~~~

**Sự kiện, quyết định và HTTP response là ba khái niệm khác nhau:**

1. **Decision** là kết quả đánh giá quyền tại một điểm authorization.
2. **Event** là thông tin hệ thống có thể công bố để quan sát decision.
3. **HTTP response** là kết quả của nhiều filter/handler và có thể có status không phản ánh duy nhất decision đó.

Một denial event không tự động đồng nghĩa “ứng dụng đã gửi một 403”; request có thể qua error dispatch, handler khác hoặc entry point khác. Ngược lại 403 không bảo đảm có denial event.

## 2. Những class/interface liên quan

| Thành phần | Vai trò |
| --- | --- |
| `AuthorizationManager<T>` | Đánh giá xem `Authentication` hiện tại có thỏa policy trên đối tượng `T` hay không. |
| `AuthorizationResult` / `AuthorizationDecision` | Mang kết quả granted/denied; API kết quả có thay đổi giữa các bản Spring Security 6.x. |
| `AuthorizationFilter` | Kết nối authorization manager với Servlet request, có thể công bố authorization event theo publisher đã cấu hình. |
| `AuthorizationEventPublisher` | Hợp đồng để công bố thông tin về quyết định phân quyền. |
| `SpringAuthorizationEventPublisher` | Cài đặt publisher sử dụng cơ chế `ApplicationEventPublisher` của Spring để gửi event. |
| `AuthorizationDeniedEvent<T>` | Event cho một authorization decision bị từ chối. |
| `AuthorizationGrantedEvent<T>` | Event cho decision được cấp phép, khi publisher được cấu hình phát loại này. |
| `@EventListener` | Cách một Spring bean đăng ký hàm nhận event. |
| `AccessDeniedHandler` | Chuyển access denied thành HTTP response thích hợp, **không** thay thế event publisher. |
| `AuthenticationEntryPoint` | Khởi động yêu cầu xác thực khi request chưa có authentication phù hợp (401/redirect). |
| `AuthenticationFailure...` events | Tín hiệu thuộc **authentication**, khác với authorization denied. |

Trong các bản Spring Security 6.x mới, API authorization đang dần sử dụng `AuthorizationResult` bao quát hơn. Một số đoạn code hoặc Javadoc cũ nói đến `AuthorizationDecision`, hoặc expose getter mang tên khác. **Không copy một accessor từ tài liệu phiên bản khác mà giả định biên dịch ở mọi 6.x.** Đoạn listener thực hành bên dưới chỉ nhận loại event và tăng counter, tránh lệ thuộc vào các accessor dễ thay đổi.

### Trách nhiệm của AuthorizationManager

Ví dụ policy:

~~~java
.requestMatchers("/admin").hasRole("ADMIN")
.requestMatchers("/reports").hasAuthority("REPORT_READ")
~~~

Với user mang `ROLE_USER` nhưng không có `ROLE_ADMIN`, yêu cầu `GET /admin` sẽ bị authorization từ chối. `hasRole("ADMIN")` theo quy ước mặc định kiểm tra authority `ROLE_ADMIN`; `hasAuthority("REPORT_READ")` kiểm tra chính xác chuỗi `REPORT_READ`.

Nhưng manager không tự xác thực password. Identity/authorities phải đến từ cơ chế xác thực đáng tin cậy: form login, HTTP Basic, JWT verifier hoặc custom provider chính xác. Nếu một custom provider cấp sai authority, event publisher vẫn chỉ quan sát **quyết định trên bộ quyền sai đó**, không sửa được lỗ hổng cấp quyền.

## 3. AuthorizationDeniedEvent chứa loại thông tin nào?

Một denied event thường gắn với:

- Tham chiếu/lazy supplier đến `Authentication` đang được xét.
- Đối tượng được authorization manager đánh giá: có thể là request (hoặc context liên quan) trong HTTP authorization, hoặc method invocation khi method security được bật.
- Kết quả authorization bị từ chối.

Vì loại đối tượng đích `T` thay đổi theo nơi dùng, **không nên cast mọi event thành `HttpServletRequest`**. Cũng không nên gọi `event.toString()` hoặc log nguyên đối tượng authentication/event/request: nó có thể chứa attributes nhạy cảm, query strings, thông tin user, session-related references hoặc cấu trúc nội bộ.

Khi cần audit, trích xuất có chủ đích những trường **đã cho phép** (ví dụ action/route đã chuẩn hóa, tên policy, category principal, trace ID do server sinh), và **không** đưa raw credential, cookies, CSRF token, Authorization header hoặc toàn bộ request body vào log.

### Denial event không phải AccessDeniedException

`AccessDeniedException` đại diện cho việc kiểm tra quyền thất bại trong dòng xử lý exception. Một event có thể được phát **trước khi** exception được chuyển thành HTTP 403; một `AccessDeniedHandler` tùy chỉnh cũng có thể tự xử lý exception mà không phát event tương ứng.

Cả hai cùng hữu ích nhưng mục đích khác:

~~~text
AuthorizationDeniedEvent: "Có quyết định authorization bị bác"
AccessDeniedException:     "Luồng thực thi gặp từ chối truy cập"
HTTP 403:                  "Response báo không được phép tiếp tục"
~~~

**Không đồng nhất bằng cách đếm:** một HTTP request có thể trải qua nhiều authorization checks (web + method, forwards/error dispatch, custom manager) nên có nhiều decision events. Khi muốn metric *requests denied*, nên có cơ chế correlation/dedup và policy rõ ràng; không lấy tổng `AuthorizationDeniedEvent` làm “số người dùng bị 403” mà không xem cấu trúc.

## 4. Làm sao bật việc công bố authorization events?

Spring Security có `AuthorizationEventPublisher`. Một cách tiêu biểu cho ứng dụng Spring Boot Servlet là khai báo bean publisher để Spring Security có thể phát quyết định qua hệ thống application events.

Tạo `src/main/java/com/example/authzaudit/AuthorizationEventsConfig.java`:

~~~java
package com.example.authzaudit;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authorization.AuthorizationEventPublisher;
import org.springframework.security.authorization.SpringAuthorizationEventPublisher;

@Configuration
public class AuthorizationEventsConfig {

    @Bean
    AuthorizationEventPublisher authorizationEventPublisher(
            ApplicationEventPublisher applicationEvents) {

        return new SpringAuthorizationEventPublisher(applicationEvents);
    }
}
~~~

**Các điểm phải hiểu:**

1. `SpringAuthorizationEventPublisher` sử dụng `ApplicationEventPublisher` của Spring để thông báo những sự kiện mà nó được thiết kế phát.
2. Mẫu mặc định của publisher này **ưu tiên phát sự kiện denial**, không biến mỗi granted request thành một event. Điều đó tránh lượng event cao khi web traffic bình thường đa số thành công.
3. Việc khai báo bean không thay đổi `hasRole`, `hasAuthority` hay chính sách của endpoint; nó thay đổi khả năng **quan sát** kết quả.
4. Tùy phiên bản/cách bạn tự cấu hình filter hoặc interceptor, cần bảo đảm component authorization thực tế **được gắn với publisher**. Một custom filter/controller gọi manager bằng code tùy biến không nhất thiết tự tìm bean này. Đừng coi `@Bean` là bảo đảm theo dõi mọi điểm quyết định trong toàn hệ thống.
5. Để test, hãy gửi một request thiếu quyền rồi xác nhận listener đã nhận event; điều đó chứng minh pipeline **thực sự nối được**, tốt hơn chỉ nhìn tên bean trong context.
6. Nếu dự án nằm trên nhánh Spring Security cũ hơn hoặc đã nâng major, kiểm tra package/constructor/API thực tế của `spring-security-core`, `spring-security-web` và `spring-security-config` theo version/BOM đang dùng. Ví dụ được viết cho mô hình Spring Security 6.x tương thích; không khẳng định tên method của mọi bản giống hệt.

### Nếu muốn ghi cả “granted”?

`AuthorizationGrantedEvent` tồn tại để biểu diễn các lần cấp phép, nhưng **không phải cứ khai báo `SpringAuthorizationEventPublisher` là mặc định có đầy đủ granted events**. Để publish granted, cần tùy biến publisher theo đúng API phiên bản đang dùng và cân nhắc traffic:

- Route `GET /assets/...` có thể có hàng triệu success decisions; phát một event cho mỗi request thường gây overhead và cardinality cao.
- Audit compliance đôi khi cần quyết định **thành công** cho hành động nhạy cảm. Khi đó chọn **điểm audit nghiệp vụ** cụ thể, không tràn event cho mọi URL.
- Có thể lấy mẫu (sampling) cho metrics/diagnostics không bắt buộc, nhưng **không** dùng sampling ngẫu nhiên để làm mất các bản ghi audit mà quy định bắt buộc phải lưu.
- Luôn nói rõ data source: `AuthorizationGrantedEvent` có thể chỉ phản ánh manager check, không chứng minh nghiệp vụ/DB transaction cuối cùng thành công.

Một publisher custom phải giữ semantics chính xác cho deny/grant và được test dưới load; không biến logic audit thành authorization shortcut.

## 5. Bắt denied event bằng @EventListener

Tạo `src/main/java/com/example/authzaudit/DeniedEventRecorder.java`:

~~~java
package com.example.authzaudit;

import java.util.concurrent.atomic.LongAdder;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.security.authorization.event.AuthorizationDeniedEvent;

@Component
public final class DeniedEventRecorder {

    private final LongAdder deniedDecisions = new LongAdder();

    @EventListener
    public void onDenied(AuthorizationDeniedEvent<?> ignoredEvent) {
        // Demo: ghi nhận số decision bị từ chối.
        // Không log Authentication, request, secret hoặc event object.
        deniedDecisions.increment();
    }

    public long count() {
        return deniedDecisions.sum();
    }
}
~~~

**Giới hạn cố ý của ví dụ:**

- `LongAdder` phù hợp một counter chịu cập nhật nhiều luồng trong **một JVM**; nó không phải hệ thống metric bền vững và không đồng bộ số liệu giữa node/pod.
- Method nhận `AuthorizationDeniedEvent<?>` mà không đọc payload, nên tránh log nhầm session/token và ít phụ thuộc vào các getter thay đổi giữa phiên bản.
- Nếu publisher hoạt động mặc định bằng Spring event multicast đồng bộ, listener được gọi trong luồng publish. Không đưa truy vấn DB hoặc HTTP call chậm vào method ấy.
- Nếu hệ thống chuyển application events sang async executor, không được mặc định test có thể assert counter ngay lập tức; cần cách chờ/eventual-consistency phù hợp, đồng thời phân tích thứ tự, retry và mất event khi process crash.
- Counter này đếm **authorization decisions denied**, không đếm người dùng duy nhất hay phiên đăng nhập thất bại; không dùng nó để tự khóa tài khoản.

Trong production có thể dùng Micrometer/OTel metrics và audit sink, nhưng phải định nghĩa **ngữ nghĩa metric** và các trường được phép ghi rõ ràng trước.

## 6. Một demo Spring Boot 3 + Spring Security 6.x có thể chạy

Mục tiêu tạo một luồng dễ tái hiện:

- `GET /public`: mọi người truy cập, bình thường trả 200.
- `GET /admin`: cần `ROLE_ADMIN`.
- `GET /reports`: cần `REPORT_READ`.
- `POST /reports/submit`: cần `REPORT_WRITE` và (với cấu hình web session/CSRF mặc định) **CSRF token hợp lệ**.
- Một account `reader` chỉ có `ROLE_USER` và `REPORT_READ`; một account `admin` có `ROLE_ADMIN`, `REPORT_READ` và `REPORT_WRITE`.
- `DeniedEventRecorder` chỉ tăng khi publisher báo một authorization denial; kiểm thử sẽ xác nhận điều đó qua request thiếu quyền.

### Cấu trúc

~~~text
src/main/java/com/example/authzaudit/
  AuthzAuditApplication.java
  SecurityConfig.java
  AuthorizationEventsConfig.java
  DeniedEventRecorder.java
  DemoController.java

src/test/java/com/example/authzaudit/
  AuthorizationEventsIntegrationTest.java
~~~

Các dependencies:

~~~text
spring-boot-starter-web
spring-boot-starter-security
spring-boot-starter-test        (scope test)
spring-security-test           (scope test)
~~~

Các class ở cùng package `com.example.authzaudit`. Không cần database. Password và username học tập dưới đây **không được dùng cho môi trường thật**.

### 6.1. SecurityConfig.java

~~~java
package com.example.authzaudit;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService demoUsers(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
                .password(encoder.encode("reader-demo-only"))
                .authorities("ROLE_USER", "REPORT_READ")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin-demo-only"))
                .authorities(
                    "ROLE_ADMIN", "REPORT_READ", "REPORT_WRITE")
                .build();

        return new InMemoryUserDetailsManager(reader, admin);
    }

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/admin")
                    .hasRole("ADMIN")
                .requestMatchers(HttpMethod.GET, "/reports")
                    .hasAuthority("REPORT_READ")
                .requestMatchers(HttpMethod.POST, "/reports/submit")
                    .hasAuthority("REPORT_WRITE")
                .requestMatchers("/reports/**").denyAll()
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults());

        // CSRF mặc định đang bật cho unsafe methods như POST.
        // Không tắt CSRF để một test POST chạy qua.
        return http.build();
    }
}
~~~

**Mổ xẻ:**

1. `reader` có `REPORT_READ` nhưng không có `REPORT_WRITE` hoặc `ROLE_ADMIN`.
2. `admin` có cả ba quyền; `hasRole("ADMIN")` cần đúng authority `ROLE_ADMIN`.
3. `/reports/submit` được ràng buộc **POST**, không mở GET/DELETE vì điều kiện cùng path.
4. `anyRequest().denyAll()` giảm nguy cơ thêm endpoint mà quên viết rule.
5. `httpBasic` dùng cho demo, không yêu cầu render form login. Đối với API browser với cookie, cấu hình session/CSRF có thể khác; phải xem threat model thực tế.
6. Đây là một `SecurityFilterChain` cụ thể; nếu dự án có nhiều chains, một chain `@Order` cao hơn có thể chọn request trước và thay đổi cách event được phát.
7. `AuthorizationEventsConfig` cung cấp bean publisher, còn `DeniedEventRecorder` tiếp nhận event; **không phải** security config tự gọi recorder.

Đừng gộp `AuthorizationEventPublisher` vào một custom access-control rule kiểu “nếu audit sink lỗi thì cho quyền”. Thành công/thất bại của authorization phải được quyết định bởi chính sách bảo mật, không bởi hệ thống telemetry.

### 6.2. DemoController.java

~~~java
package com.example.authzaudit;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    public String publicPage() {
        return "public";
    }

    @GetMapping("/admin")
    public String adminPage() {
        return "admin";
    }

    @GetMapping("/reports")
    public String readReport() {
        return "report-read";
    }

    @PostMapping("/reports/submit")
    public String submitReport() {
        // Demo không sửa DB: chỉ trả response.
        return "report-submitted";
    }
}
~~~

**Không dùng controller `@GetMapping("/admin")` để tự kiểm tra `if (username.equals("admin"))`**. Quyền được thực thi tại Spring Security HTTP authorization layer; business service có thể có additional permission/tenant check nhưng không được dựa vào tên người dùng thuần túy.

### 6.3. AuthzAuditApplication.java

~~~java
package com.example.authzaudit;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthzAuditApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthzAuditApplication.class, args);
    }
}
~~~

Cần JDK 17+ và dependencies Spring Boot đã resolve tương thích. Để chạy với Maven Wrapper của project:

~~~bash
./mvnw spring-boot:run
~~~

Ví dụ request ở localhost với credential **học tập**:

~~~bash
curl -i http://localhost:8080/public

curl -i -u reader:reader-demo-only \
  http://localhost:8080/reports

curl -i -u reader:reader-demo-only \
  http://localhost:8080/admin

curl -i -u admin:admin-demo-only \
  http://localhost:8080/admin
~~~

Kết quả logic theo demo:

| Request | Kỳ vọng | Lý do |
| --- | --- | --- |
| Anonymous GET `/public` | 200, body `public` | `permitAll()`. |
| Reader GET `/reports` | 200, body `report-read` | Có `REPORT_READ`. |
| Reader GET `/admin` | 403 | Thiếu `ROLE_ADMIN`; một denied decision có thể được công bố. |
| Admin GET `/admin` | 200, body `admin` | Có `ROLE_ADMIN`. |
| Anonymous GET `/admin` | Thường 401 với HTTP Basic | Cần xác thực; không kết luận tương đương một 403. |

Không cung cấp stdout cố định của `curl -i`: các header, cookies hoặc challenge header có thể khác theo phiên bản/server. `curl -u` đặt credential lên command-line/process history; chỉ dùng tài khoản giả ở localhost, không dùng với secret thật. Production phải dùng TLS và quản lý credential phù hợp.

### 6.4. Những gì một listener không nên làm

~~~java
// PHẢN VÍ DỤ: không chép vào hệ thống thật.
@EventListener
public void unsafeLogging(
        AuthorizationDeniedEvent<?> event) {
    System.out.println(event); // có thể làm lộ dữ liệu.
}
~~~

Đây là snippet minh họa lỗi, không phải file Java độc lập. Việc log nguyên event/request/authentication có thể làm lộ nội dung ngoài ý muốn hoặc tăng rủi ro PII. Trong chương trình demo thật, listener chỉ tăng counter an toàn.

## 7. MockMvc: chứng minh event đến từ authorization denial

Tạo `src/test/java/com/example/authzaudit/AuthorizationEventsIntegrationTest.java`:

~~~java
package com.example.authzaudit;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class AuthorizationEventsIntegrationTest {

    @Autowired MockMvc mvc;
    @Autowired DeniedEventRecorder denied;

    @Test
    void publicRequestSucceedsWithoutAuthentication()
            throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void deniedHttpAuthorizationPublishesDeniedEvent()
            throws Exception {
        long before = denied.count();

        mvc.perform(get("/admin")
                    .with(httpBasic("reader", "reader-demo-only")))
            .andExpect(status().isForbidden());

        assertTrue(denied.count() > before);
    }

    @Test
    void authorizedAdminRequestIsAllowed() throws Exception {
        mvc.perform(get("/admin")
                    .with(httpBasic("admin", "admin-demo-only")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin"));
    }

    @Test
    void missingWriteAuthorityDeniesEvenWithValidCsrf()
            throws Exception {
        long before = denied.count();

        mvc.perform(post("/reports/submit")
                    .with(csrf())
                    .with(httpBasic("reader", "reader-demo-only")))
            .andExpect(status().isForbidden());

        assertTrue(denied.count() > before);
    }

    @Test
    void validWriteAuthorityWithCsrfSucceeds()
            throws Exception {
        mvc.perform(post("/reports/submit")
                    .with(csrf())
                    .with(httpBasic("admin", "admin-demo-only")))
            .andExpect(status().isOk())
            .andExpect(content().string("report-submitted"));
    }

    @Test
    void missingCsrfReturns403ButProvesNothingAboutTheRule()
            throws Exception {
        // Admin có REPORT_WRITE nhưng CsrfFilter có thể chặn
        // trước khi tới AuthorizationFilter.
        mvc.perform(post("/reports/submit")
                    .with(httpBasic("admin", "admin-demo-only")))
            .andExpect(status().isForbidden());
    }
}
~~~

**Giải thích chi tiết:**

- Test `deniedHttpAuthorizationPublishesDeniedEvent` là phép kiểm tra **publisher → event listener** cho một denied decision ở HTTP layer. Nó không chỉ kiểm tra HTTP status.
- `denied.count() > before` thay vì bằng chính xác `before + 1` vì số authorization checks có thể thay đổi bởi error dispatch, method security hoặc cấu hình bổ sung. Đừng biến số event tuyệt đối thành giả định “một request luôn một sự kiện”.
- `missingWriteAuthority...` gửi `.with(csrf())` để đi qua tầng CSRF, nhờ vậy denial phản ánh **thiếu REPORT_WRITE**.
- `missingCsrf...` cố ý **không** assert số denied events: 403 có thể phát sinh **trước authorization**. Đây là bài học phân biệt CSRF rejection và authorization denial.
- `validWriteAuthority...` kiểm tra path+method+authority và token hợp lệ đồng thời.
- Nếu dự án sử dụng async application event multicaster, counter có thể tăng muộn; khi đó cần Awaitility hoặc một cơ chế đợi hợp lý trong test. Ví dụ giả định phát sự kiện đồng bộ mặc định của Spring.
- Các test dùng chung bean counter trong application context. Vì mỗi test chỉ so `before` với `after` trong test hiện tại, chúng không dựa vào số đếm từ 0. Nếu test chạy song song hoặc có traffic khác, nên tách fixture/counter để tránh nhiễu.

Chạy:

~~~bash
./mvnw test
~~~

**Không khẳng định đã chạy thành công trong mọi bản Boot/Security.** API, dependency và cách Spring Security tích hợp publisher cần được xác minh trên version dự án thực tế. Khi triển khai với nhiều filter chains hoặc custom `AuthorizationManager`, nên thêm test cho **đúng điểm quyết định** đang quan tâm.

### Kết quả denial trong application events khác với nhật ký HTTP 403

Test `GET /admin` của reader có thể tạo:

~~~text
Authentication: reader, authorities=[ROLE_USER, REPORT_READ]
Authorization rule: hasRole("ADMIN")
Authorization result: DENIED
AuthorizationDeniedEvent: published
HTTP response: 403
~~~

Nhưng cùng status 403 từ POST thiếu CSRF có thể theo chuỗi khác:

~~~text
Authentication: có thể chưa được xử lý ở đoạn filter đó
CsrfFilter: missing/invalid token
AuthorizationFilter: chưa nhất thiết chạy
AuthorizationDeniedEvent: không thể suy ra từ status 403
HTTP response: 403
~~~

**Đừng gom hai đường lại thành một chỉ số mà gọi “người dùng không có role”**. Điều đó dễ tạo alert giả và dẫn người vận hành đến quyết định sai.

## 8. Ghi audit: thế nào là “đủ thông tin nhưng không làm lộ dữ liệu”?

Một bản ghi audit có ích cần mô tả **điều gì bị từ chối**, **trong ngữ cảnh nào**, **đã xử lý thế nào**, và có thể truy vết mà không xuất bí mật. Các trường gợi ý:

| Trường | Ví dụ | Quy tắc an toàn |
| --- | --- | --- |
| `event_type` | `authorization.denied` | Tên event ổn định. |
| `timestamp` | ISO 8601 UTC | Dùng clock đồng bộ; không giả định clock của nhiều node hoàn hảo. |
| `service` / `environment` | `orders-api / prod` | Label ít giá trị biến thiên. |
| `rule_id` | `admin.read` | Identifier do server định nghĩa, không phải toàn biểu thức chứa input. |
| `action` | `read_admin_dashboard` | Semantic ổn định theo nghiệp vụ. |
| `route_template` | `/admin` hoặc `/orders/{id}` | **Không** log raw path ID/token nếu không cần. |
| `http_method` | `GET` | Normalized verb. |
| `principal_ref` | Internal pseudonymous ID | Chỉ khi cần audit, kiểm soát truy cập/retention; không dùng làm metric label. |
| `tenant_ref` | Pseudonymous tenant ID | Chỉ khi cần và lấy từ nguồn server đáng tin. |
| `correlation_id` | ID ngẫu nhiên do gateway/server cấp | Không tin hoàn toàn input arbitrary từ client; giới hạn format/length. |
| `decision` | `denied` | Cần ghi nguồn/cơ chế của decision. |
| `response_status` | `403` | Trường **tùy chọn từ HTTP response layer**; không tự suy từ event. |
| `policy_version` | `acp-v3` | Hữu ích khi rule thay đổi qua release. |

Một denial event thuộc method security có thể không có HTTP route; đừng chế một path giả. Nếu cần kiểm tra “ai, thao tác nào, đối tượng nào”, audit tại **nghiệp vụ có ngữ nghĩa** sau khi đã xác định resource/tenant, và phát audit đã được redaction. Một danh sách URL không thay thế được dữ liệu này.

### Dữ liệu không được đưa vào audit/metrics

- Raw `Authorization` header, Basic credential, Bearer JWT, refresh token, API key.
- `JSESSIONID`, CSRF token, remember-me cookie hoặc toàn bộ `Cookie` header.
- Password/passcode, thông tin từ form đăng nhập.
- Body request đầy đủ, JSON hồ sơ khách hàng, file upload, query string có thông tin nhạy cảm.
- `Authentication.toString()` hay `event.toString()` không kiểm soát.
- Full IP + user-agent + account ID trong metric labels có cardinality rất cao và có thể xâm phạm quyền riêng tư.

Đối với security audit yêu cầu nhận diện actor, bảo vệ trường `principal_ref` bằng quyền truy cập, mã hóa khi lưu/truyền, thời hạn lưu và chính sách tuân thủ; không đồng nghĩa “phải xóa toàn bộ dấu vết danh tính”. Cần cân bằng giá trị điều tra với minimization và quy định của tổ chức.

## 9. Metrics, alerting và tracing: đếm đúng đại lượng

Một pipeline có thể triển khai theo hướng:

~~~text
AuthorizationDeniedEvent
   |
   v
Event listener nhẹ, redaction và gắn context an toàn
   |
   +--> Micrometer counter / OTel metric
   |      security_authorization_denied_total
   |      tags: service, policy_category, http_method, outcome
   |
   +--> Audit queue / append-only storage
   |      có retention, quyền truy cập và cơ chế retry
   |
   +--> Trace/span event
          liên kết bằng correlation ID an toàn
          (nếu đã có trace trong request)
   |
   v
Alert engine:
   - Tỷ lệ denied tăng theo endpoint category
   - Số denied bất thường sau một deployment
   - Một policy quan trọng bị từ chối hàng loạt
~~~

Lưu ý:

- **Counter** của decision không phải số HTTP requests duy nhất. Nếu dashboard muốn tỷ lệ request 403, cần một metric từ HTTP server/response layer hoặc cách tổng hợp theo correlation ID.
- Dùng **tags cardinality thấp**: tên service, nhóm policy, method, outcome. Đừng dùng user ID, raw URL, order ID, token hoặc error message làm tag.
- Đặt ngưỡng trên **tỷ lệ** denied theo tổng request hợp lệ, theo endpoint category và baseline; một endpoint vốn yêu cầu admin thường có tỷ lệ bị từ chối cao hơn endpoint public.
- Tách tăng denial do **tấn công dò quyền** khỏi tăng do **deploy sai policy** bằng các chiều phân tích: thời gian release, routes cụ thể, nhóm user/scope (đã ẩn danh), vùng hệ thống.
- Audit log có thể yêu cầu lưu đầy đủ event quan trọng; metrics và trace thường chỉ là dữ liệu quan sát có retention/sampling khác.
- Nếu dùng queue, định nghĩa tình huống queue unavailable: policy authorization **không được tự cho phép** chỉ vì audit không ghi được. Lựa chọn fail-closed với *hành động tuân thủ đặc biệt* cần được thiết kế riêng, không mặc định làm chết mọi request khi telemetry chậm.

### Ví dụ tích hợp Micrometer (tùy chọn)

Nếu project có Micrometer `MeterRegistry` được cấu hình qua Spring Boot Actuator, có thể sử dụng listener đơn giản thay cho counter memory:

~~~java
package com.example.authzaudit;

import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.context.event.EventListener;
import org.springframework.security.authorization.event.AuthorizationDeniedEvent;

public final class DeniedMetricsListener {

    private final MeterRegistry registry;

    public DeniedMetricsListener(MeterRegistry registry) {
        this.registry = registry;
    }

    @EventListener
    public void onDenied(AuthorizationDeniedEvent<?> ignored) {
        registry.counter("security.authorization.denied",
                "decision", "denied")
                .increment();
    }
}
~~~

Đây là **class tùy chọn**, chưa tự được Spring quản lý nếu bạn chưa đăng ký nó thành bean (ví dụ qua `@Bean` trong `@Configuration`); không cần nó để chạy demo mục 6. Project phải có dependency Micrometer phù hợp, chẳng hạn `spring-boot-starter-actuator` và registry exporter. Không thêm label chứa account/path raw. Việc cài metric publisher và HTTP server metrics là hai kênh khác nhau; đừng giả định tên metric trong snippet là chuẩn bắt buộc của mọi backend.

## 10. Khi cần response 403 có cấu trúc: AccessDeniedHandler

Một frontend API thường muốn JSON thay vì trang lỗi HTML. `AccessDeniedHandler` có thể biến access denial thành response `application/problem+json` hoặc một JSON envelope thống nhất. **Nhưng AccessDeniedHandler không phải event publisher**: nó xử lý HTTP response khi exception đi tới nó, và không bảo đảm mọi 403 đều là `AuthorizationDeniedEvent`.

Ví dụ mảnh cấu hình để trả mã 403, **không** ghi thông tin nhạy cảm vào body:

~~~java
import jakarta.servlet.http.HttpServletResponse;

// Bên trong cấu hình HttpSecurity:
http.exceptionHandling(ex -> ex
    .accessDeniedHandler((request, response, denied) -> {
        response.sendError(HttpServletResponse.SC_FORBIDDEN);
    }));
~~~

Đoạn này là **mảnh code**, cần đặt vào `SecurityFilterChain` trong ứng dụng Boot. Nó không kiểm soát các lỗi xảy ra trước security chain, và không thay thế kiểm tra phân quyền. Với API JSON thật, phải cân nhắc response đã commit và không phản chiếu exception message/role/tenant ID trực tiếp ra client.

Khi nào dùng?

- Event để audit/metric ở **điểm quyết định**.
- AccessDeniedHandler để tạo **hợp đồng HTTP lỗi**.
- AuthenticationEntryPoint để xử lý **chưa xác thực**.
- Service-level audit để ghi ngữ cảnh business đã được kiểm soát.

Đừng ghi một sự kiện audit trùng từ cả publisher và handler rồi đếm hai lần như hai lần deny khác nhau mà không có deduplication key/semantics.

## 11. Method security và authorization events

Ngoài HTTP request matching, Spring Security còn có method security, thường qua `@EnableMethodSecurity` và annotations như `@PreAuthorize`. Một authorization denial tại method interceptor có thể tạo loại event liên quan nếu các thành phần được cấu hình publisher phù hợp.

Ví dụ mô tả logic:

~~~java
@PreAuthorize("hasAuthority('REPORT_EXPORT')")
public byte[] exportReport(String reportId) {
    return reportStore.export(reportId);
}
~~~

Đây là **mảnh minh họa**, không biên dịch độc lập vì thiếu class/service `reportStore` và method body. Trong ứng dụng thật cần bean method security, service/transaction và kiểm tra quyền theo resource. Điểm chính:

- HTTP-level `GET /reports/export/{id}` có thể thỏa `REPORT_READ` nhưng method yêu cầu `REPORT_EXPORT`, nên denial diễn ra ở method layer.
- Ngược lại, nếu HTTP rule đã bác request trước controller, method sẽ không được gọi.
- Nếu bạn bật cả hai, số authorization decisions và event counts **không còn có quan hệ một-một** với request.
- Những event liên quan `MethodInvocation` không nhất thiết có `HttpServletRequest`; listener phải nhận diện loại object trước khi trích xuất context.
- Đừng ghi toàn bộ method arguments vào audit. Chúng có thể là PII, raw payload hoặc object chứa secrets.

**Không cần bật method security chỉ để đếm denial của HTTP rule** trong ví dụ mục 6; `authorizeHttpRequests` là đủ. Khi thêm method security ở production, hãy phân tách `source=web` và `source=method` theo cách đáng tin cậy, không suy từ tên class một cách võ đoán.

## 12. Phân biệt các loại thất bại để không báo động sai

| Tình huống | Bộ phận chính | HTTP status hay gặp | Có tự suy ra AuthorizationDeniedEvent không? |
| --- | --- | --- | --- |
| User đã login, thiếu authority GET `/admin` | `AuthorizationFilter` / `AuthorizationManager` | 403 | **Có thể**, khi event publisher được nối đúng. |
| Anonymous gọi protected URL | Authorization + entry point | 401 hoặc redirect 302 | Không kết luận số sự kiện bằng số lần chưa login. |
| Sai username/password | Authentication provider/filter | 401 hoặc login failure redirect | **Không**. Dùng authentication failure events. |
| POST thiếu CSRF | `CsrfFilter` | 403 | **Không** chỉ từ status 403. |
| Controller tự trả `ResponseEntity.status(403)` | Controller | 403 | **Không**, nếu không có authorization manager decision. |
| `@PreAuthorize` thiếu quyền | Method security interceptor | Thường 403 khi qua HTTP | Tùy cấu hình event publisher của method authorization. |
| Route không tồn tại | MVC/router | 404, đôi khi bị policy deny trước | Không suy từ status. |
| Proxy/gateway ngoài Spring từ chối | Gateway/firewall/WAF | 403 hoặc khác | Không thể trông chờ Spring application event bên trong service. |
| Business service từ chối ownership bằng exception tùy chỉnh | Service | 403 hoặc khác | Không tự phát event trừ khi kết hợp authorization mechanism tương ứng. |

Quan trọng với hệ thống nhiều lớp: một request có thể bị **gateway chặn trước khi vào service**. Nếu bạn chỉ đo event Spring Security, không thể thấy những từ chối ấy. Để điều tra 403 end-to-end, cần đối chiếu access log gateway, HTTP metrics của service, Spring authorization events và business audit có cùng correlation ID phù hợp.

### Cách chẩn đoán GET /admin trả 403

1. Xác định request đã đến đúng service, đúng `SecurityFilterChain` và đúng matcher chưa.
2. Kiểm tra authentication đã tồn tại không, user/authorities thực tế có được tạo từ nguồn tin cậy không.
3. Xác minh `hasRole("ADMIN")` đang tìm `ROLE_ADMIN` theo prefix mặc định, chứ không phải authority `ADMIN`.
4. Kiểm tra bean `AuthorizationEventPublisher` được cấu hình và request denial có thực sự kích hoạt listener không.
5. Nếu event không xuất hiện nhưng status 403 tồn tại, xem `CsrfFilter`, custom filter, proxy và controller/service layer.
6. Nếu event xuất hiện nhiều lần cho cùng request, xem error/forward dispatch, web+method security, async và listener/decorators bị đăng ký trùng.
7. Không sửa thành `permitAll` chỉ vì thiếu log; đó là thay đổi policy, không sửa instrumentation.

## 13. Quan hệ với AuthenticationFailure events

Spring Security cũng có luồng phát sự kiện khi xác thực không thành công, ví dụ các event thuộc nhóm `AbstractAuthenticationFailureEvent` và cơ chế `AuthenticationEventPublisher` khi được cấu hình phù hợp.

Cần tách hai loại:

~~~text
Client gửi sai password:
   -> AuthenticationProvider bác credential
   -> authentication failure event (nếu publisher được cấu hình)
   -> thường không có authenticated principal được cấp

Client đăng nhập đúng nhưng vào /admin:
   -> Authentication thành công
   -> AuthorizationManager thấy thiếu ROLE_ADMIN
   -> authorization denial event (nếu publisher được cấu hình)
   -> HTTP 403 thường gặp
~~~

Không nên gom tất cả vào `security_failures_total` mà không có `stage=authentication|authorization|csrf`. Việc điều tra credential stuffing khác hoàn toàn điều tra privilege probing hoặc migration role mapping sai.

**Bảo vệ quyền riêng tư:** lỗi đăng nhập cần tránh user enumeration; lỗi phân quyền cần tránh tiết lộ “bạn còn thiếu chính xác ROLE_ADMIN”. Thông điệp trả client nên vừa đủ, audit nội bộ có thể chứa mã policy nhưng phải kiểm soát quyền truy cập.

## 14. Độ tin cậy và hiệu năng của event pipeline

### ApplicationEventPublisher không phải hệ thống message queue bền vững

Một `ApplicationEventPublisher` trong process giúp các bean nhận event, nhưng không tự cung cấp:

- Lưu trữ bền vững qua crash.
- Cam kết exactly-once delivery.
- Backpressure, retry, dead-letter queue.
- Đồng bộ giữa nhiều pod/instance.
- Quy tắc retention và chống sửa log.

Đối với audit bắt buộc có bằng chứng lâu dài, cần kiến trúc audit sink đáp ứng yêu cầu như append-only store, signed events hoặc transactional outbox khi cần liên kết với nghiệp vụ. Cũng cần kiểm tra hành vi khi sink lỗi.

### Listener không được làm chậm request

Một listener bị gọi đồng bộ có thể tăng độ trễ hoặc ném exception làm nhiễu luồng authorization. Thực hành tốt:

- Listener tối giản, không gửi email/HTTP request trực tiếp cho mỗi event.
- Đẩy dữ liệu đã redaction sang queue nội bộ với giới hạn tài nguyên.
- Nếu queue đầy, chọn policy rõ ràng cho **telemetry**: có thể count dropped/lagged events và alert mà không biến denial thành grant.
- Không gọi database chậm chỉ để “tra thêm tên người dùng” trong đường authorization.
- Bảo đảm độ an toàn luồng, tránh biến mutable map dùng chung thành race condition.
- Giới hạn mức thông tin log khi có tấn công tạo hàng loạt denied requests, tránh log-flood làm cạn disk/CPU.

### Deduplication và tracing

Khi cần tỷ lệ “số request bị deny”, dùng ID của request/span từ tracing infrastructure và định nghĩa quy tắc tổng hợp: một request có thể có **nhiều** deny events hay một deny event từ method security rồi được error handler xử lý lại. Không dựa vào `event.hashCode()` hoặc principal name để khử trùng, vì chúng không phải event/request identity bảo đảm.

Nếu sử dụng async dispatch hoặc application event async, trace context có thể không được propagate tự động; cần giải pháp context propagation phù hợp. Không truyền raw `SecurityContext` hoặc credentials qua queue/audit payload.

### Khi nào cần sampling?

- Metrics volume lớn hoặc granted events: sampling/bucketing có thể hợp lý.
- Các event denial đòi điều tra bảo mật: cần retention và loss budget rõ ràng.
- Các audit events theo luật/chính sách: nếu bắt buộc lưu đầy đủ, **không được sampling tùy tiện**.

Giải pháp thường là **metrics cardinality thấp + audit events được redaction + application logs có correlation ID**, không phải log hết mọi đối tượng request.

## 15. Java 17 độc lập: mô phỏng công bố denial event

Để nắm ý nghĩa “decision” tách khỏi “event” mà không cần thư viện Spring, tạo file `AuthorizationDecisionDemo.java`. Đây là **mô hình Java SE**, không phải class `AuthorizationManager` hay `SpringAuthorizationEventPublisher` thật.

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Set;

public final class AuthorizationDecisionDemo {

    record Attempt(
        String method, String route, String requiredAuthority) {}

    private static final List<String> deniedEvents = new ArrayList<>();

    static boolean authorize(Attempt attempt, Set<String> authorities) {
        boolean granted = authorities.contains(
                attempt.requiredAuthority());

        if (!granted) {
            deniedEvents.add(attempt.method() + " " + attempt.route());
        }

        return granted;
    }

    static void check(Attempt attempt, Set<String> authorities) {
        System.out.println(
            attempt.method() + " " + attempt.route()
            + " -> " + (authorize(attempt, authorities)
                        ? "ALLOW" : "DENY"));
    }

    public static void main(String[] args) {
        Set<String> reader = Set.of("ROLE_USER", "REPORT_READ");

        check(new Attempt("GET", "/reports", "REPORT_READ"), reader);
        check(new Attempt("GET", "/admin", "ROLE_ADMIN"), reader);
        check(new Attempt(
            "POST", "/reports/submit", "REPORT_WRITE"), reader);

        System.out.println("denialEvents=" + deniedEvents.size());
    }
}
~~~

Chạy với JDK 17 trở lên:

~~~bash
javac AuthorizationDecisionDemo.java
java AuthorizationDecisionDemo
~~~

Stdout **chính xác**:

~~~text
GET /reports -> ALLOW
GET /admin -> DENY
POST /reports/submit -> DENY
denialEvents=2
~~~

Bài học rút ra:

- **Decision** của mỗi attempt phụ thuộc quyền thực tế.
- **Event** chỉ được ghi vào danh sách khi decision bị từ chối.
- Một attempt được phép không làm tăng denied counter.
- Chương trình không xử lý HTTP 401/403, không xác thực password và không có CSRF. Việc có `POST` trong output chỉ là nhãn của attempt, không chứng minh request HTTP đã qua CsrfFilter.

Nếu muốn mở rộng, hãy thêm một kết quả `UNKNOWN` / `ABSTAIN` vào mô hình và tự định nghĩa khi nào được phát event. Trong Spring Security thật, null/abstain decision và semantics của `AuthorizationResult` phụ thuộc phiên bản/manager; **không tự coi mọi decision null đều là denied** mà phải hiểu chính sách tổng hợp.

## 16. Sai lầm phổ biến

### 16.1. Coi 403 là một authorization-denied event

HTTP 403 có thể đến từ CSRF, gateway hoặc controller. Một metric đọc `http.server.requests{status=403}` không tự tương đương `AuthorizationDeniedEvent`. Phải đối chiếu data source và phạm vi.

### 16.2. Log nguyên event hoặc Authentication

~~~java
// PHẢN VÍ DỤ: có rủi ro lộ PII/credential.
logger.warn("Denied: {}", event);
~~~

Đây là snippet minh họa lỗi, cần `logger` và `event` từ một class thực tế nếu cố biên dịch. Không log `event.getAuthentication()` hoặc raw `HttpServletRequest`; xây schema audit an toàn.

### 16.3. Bật granted events cho mọi request rồi query DB

Nếu listener làm một truy vấn DB cho mỗi allowed request, hệ thống có thể bị nghẽn khi lưu lượng lớn. Ưu tiên instrumentation mức độ thấp và audit trọng điểm, không đặt tác vụ IO nặng vào synchronous event path.

### 16.4. Listener tự cấp lại quyền vì user thiếu role

~~~java
// PHẢN VÍ DỤ: tuyệt đối không "chữa" denied event bằng nâng quyền.
// event đã nói rằng authorization bị từ chối, không trao quyền mới.
grantRoleToCurrentUser("ADMIN");
~~~

Đây chỉ là pseudocode biểu diễn lỗi. Nếu role mapping sai, sửa tại nguồn cấp authorities và kiểm thử chính sách, không dùng audit callback để tự sửa security context.

### 16.5. Không phân biệt web và method events

Một controller đã qua URL policy nhưng service `@PreAuthorize` bị từ chối là tình huống khác. Nếu listener chỉ cast event source sang `HttpServletRequest`, nó có thể throw exception khi event đến từ method security. Chỉ đọc các trường có hợp đồng/type rõ ràng.

### 16.6. Gắn userId/raw URL vào metrics labels

Một metric có một chuỗi giá trị khác nhau cho mỗi account/order/token sẽ làm cardinality bùng nổ, tăng chi phí và lộ thông tin. Các nhãn `policy_category`, `service`, `method`, `decision` thường có chất lượng tốt hơn.

### 16.7. Coi event đồng bộ như message queue có delivery guarantee

Spring application event không tự bảo đảm replay sau crash. Cần audit sink bền vững khi có yêu cầu điều tra hoặc tuân thủ, cùng quy trình vận hành khi queue/DB ngừng hoạt động.

### 16.8. Alert theo mọi denial mà không có baseline

Bot gọi `/admin` từ Internet làm denial tăng; deploy một rule sai cũng làm denial tăng. Nếu alert không có tổng traffic, endpoint category, thời gian release và baseline, báo động sẽ không đáng tin hoặc gây fatigue.

### 16.9. Chuyển denial thành HTTP 200 để giảm chỉ số lỗi

Thay đổi response status không sửa được authorization logic và có thể gây lộ dữ liệu. Điều đúng là trả response phù hợp và giải thích nguyên nhân cho frontend bằng mã lỗi không nhạy cảm, đồng thời theo dõi trên kênh nội bộ.

### 16.10. Chỉ test @EventListener mà không chạy FilterChainProxy

Unit test gọi trực tiếp `onDenied` chỉ chứng minh counter tăng, **không** chứng minh `AuthorizationFilter` có publisher. Phải có integration test với request thiếu quyền thật qua `MockMvc`.

## 17. Ma trận QA và test edge cases

| Ca | HTTP / kết quả | Ý nghĩa về event |
| --- | --- | --- |
| Reader GET `/reports` | 200 | Decision cấp phép; publisher mặc định không cần phát granted event. |
| Reader GET `/admin` | 403 | Một denial của HTTP policy; khi publisher nối đúng, listener nhận event. |
| Admin GET `/admin` | 200 | Không phải denied decision. |
| Reader POST `/reports/submit` + CSRF đúng | 403 | Thiếu REPORT_WRITE, có thể theo dõi authorization denial. |
| Admin POST `/reports/submit` + CSRF đúng | 200 | Có REPORT_WRITE; controller chạy. |
| Admin POST `/reports/submit` thiếu CSRF | 403 | Thất bại CSRF, **không** suy ra denied event. |
| Anonymous GET `/admin` | Thường 401 với HTTP Basic | Entry point, không đếm là “đã login nhưng thiếu role”. |
| Sai mật khẩu HTTP Basic | Thường 401 | Authentication failure, không giống authorization denial. |
| Controller tự trả ResponseEntity 403 | 403 | Không tự phát authorization event. |
| Custom AuthorizationManager | Tùy policy | Phải xác nhận publisher có được gắn/được gọi. |
| Method-level @PreAuthorize denial | Thường 403 ở HTTP endpoint | Có thể phát event riêng khi method interceptor được cấu hình. |
| Gateway WAF chặn trước ứng dụng | Tùy gateway | Spring app không thấy request/event. |
| Nhiều chains / forward / error dispatch | Tùy chain/dispatch | Có thể phát thêm event; test chính sách xử lý trùng. |
| Listener exception / queue unavailable | Không được đổi denied thành grant | Quan sát và xử lý lỗi audit theo chính sách đã thiết kế. |

### Checklist trước khi triển khai production

- [ ] Đã xác định sự kiện cần đo là authorization denial, không phải mọi status 403.
- [ ] Nắm rõ điểm áp dụng policy: HTTP authorization, method security hoặc business/resource policy.
- [ ] Có bean `AuthorizationEventPublisher` phù hợp version và cơ chế kết nối với những manager/filter thực sự dùng.
- [ ] Test `MockMvc` chứng minh một request authenticated thiếu authority phát denied event.
- [ ] CSRF test riêng; không gán denial event dựa trên 403 do thiếu token.
- [ ] Tách authentication failures/401/302, authorization denied/403 và gateway-level rejections.
- [ ] Listener không gây side effect lên authorization, không tự cấp quyền hoặc bỏ qua exception.
- [ ] Không log raw event/authentication/request hoặc secrets trong cookie/header/query/body.
- [ ] Schema audit được định nghĩa với action, route template, policy ID, correlation ID và retention phù hợp.
- [ ] Metrics chỉ dùng labels cardinality thấp, có tỷ lệ/baseline và grouping phù hợp.
- [ ] Có chính sách xử lý asynchronous event processing, mất event, retry, backpressure và queue failure.
- [ ] Dedupe/trace correlation khi một request trải qua nhiều decisions.
- [ ] Kiểm tra publisher behavior và method signatures khi nâng Spring Security 6.x/major mới.
- [ ] Nếu audit bắt buộc bền vững, không coi ApplicationEventPublisher là store exactly-once.
- [ ] Có test trên môi trường nhiều security chains, proxies, session/CSRF và method-level policies nếu ứng dụng dùng chúng.

## 18. Tự kiểm tra

**Q1. Một request trả 403 thì chắc có `AuthorizationDeniedEvent` không?** Không. Nó có thể bị CSRF, gateway hoặc controller chặn mà không qua authorization manager/event publisher.

**Q2. `AuthorizationDeniedEvent` có tự làm request bị từ chối không?** Không. Authorization manager/policy quyết định; event phục vụ quan sát. HTTP handling do filter/exception translation/handler xử lý.

**Q3. Cấu hình bean `SpringAuthorizationEventPublisher` giải quyết gì?** Tạo cầu nối để các thành phần authorization tương thích có thể gửi event qua Spring `ApplicationEventPublisher`, giúp listener theo dõi denial.

**Q4. Vì sao dùng `AuthorizationDeniedEvent<?>` thay vì giả định source là `HttpServletRequest`?** Event có thể đến từ HTTP hoặc method security với object type khác nhau; generic source không bảo đảm là request.

**Q5. Mặc định có cần theo dõi mọi granted request không?** Không. Thường denial quan trọng hơn cho an ninh, còn granted events cần thiết kế riêng để tránh tải lớn và chi phí audit.

**Q6. Một user thiếu role và một POST thiếu CSRF đều trả 403. Cách test sự khác biệt?** Cho POST đi qua `csrf()` hợp lệ rồi kiểm tra thiếu role, so với POST cố tình thiếu token. Đừng chỉ assert status.

**Q7. Có nên ghi toàn bộ Authentication object vào audit không?** Không. Trích xuất trường cho phép theo schema đã redaction, không log raw password/token/session/cookie.

**Q8. Một denial event tương ứng đúng một HTTP request không?** Không bảo đảm. Có nhiều authorization checks, forwarding/error dispatch hoặc method security.

**Q9. Dùng `LongAdder` trong listener có đủ làm audit production không?** Không. Nó đếm trong một JVM, không có retention, replay, phân tán hay thông tin điều tra.

**Q10. Nếu queue audit tạm hỏng, có được cho phép request vốn bị deny không?** Không. Telemetry không phải cơ chế được quyền bỏ qua authorization. Hãy xử lý reliability theo chính sách bảo mật riêng.

**Q11. Vì sao metric label không nên chứa user ID?** Tạo cardinality cực cao, tăng chi phí và có thể lộ thông tin; dùng tags ổn định/cấp thấp, đưa actor ID có kiểm soát vào audit nếu cần.

**Q12. Test unit gọi trực tiếp listener đã chứng minh event được publish chưa?** Chưa. Chỉ test HTTP thật qua `FilterChainProxy` với bean publisher mới kiểm tra tích hợp end-to-end.

**Tóm lại:** **AuthorizationManager quyết định → AuthorizationEventPublisher ghi nhận → `AuthorizationDeniedEvent` được listener xử lý → ExceptionTranslationFilter/handler tạo response**. Ghi nhận được *denied decision* không đồng nghĩa đếm được *mọi response 403*. Một hệ thống quan sát tốt phải biết **nguồn từ chối**, có **kiểm thử thực**, **không rò rỉ secrets**, **không làm chậm authorization** và có **audit/metrics/alerting** được thiết kế đúng ngữ nghĩa.
