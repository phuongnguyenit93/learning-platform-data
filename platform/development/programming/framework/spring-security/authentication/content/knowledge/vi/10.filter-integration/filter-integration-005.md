# AuthenticationWebDetailsSource và dữ liệu bổ sung của yêu cầu trong Spring Security

> **Phạm vi:** Spring Security Authentication trên **Servlet stack** (Spring MVC), trọng tâm **tích hợp bộ lọc xác thực** và cách đưa metadata của HTTP request vào `Authentication.getDetails()`. Đề bài dùng tên `AuthenticationWebDetailsSource`; trong **API chính thức của Spring Security 6.5**, lớp cần tìm là **`WebAuthenticationDetailsSource`**, triển khai interface `AuthenticationDetailsSource<HttpServletRequest, WebAuthenticationDetails>`. Bài giải thích cơ chế mặc định, cách viết source/details tùy chỉnh, cấu hình vào form login/filter, các ranh giới tin cậy và kiểm thử với **Java 17+, Spring Boot 3.5.7, Spring Security 6.5 và MockMvc**.

## 1. Kết quả cần đạt

Sau khi học, bạn có thể:

1. Tìm đúng các class: `AuthenticationDetailsSource`, `WebAuthenticationDetailsSource`, `WebAuthenticationDetails` và `Authentication.getDetails()`; phân biệt với cụm tên không có trong API chính thức `AuthenticationWebDetailsSource`.
2. Giải thích Spring Security lấy `HttpServletRequest` ở đâu, vào lúc nào, để tạo thông tin bổ sung cho **một lần thử authentication**.
3. Biết những trường mà `WebAuthenticationDetails` ghi nhận mặc định: **remote address** và **session ID nếu đã có session** — việc dựng details **không tạo session mới**.
4. Tạo một `AuthenticationDetailsSource` tùy chỉnh với dữ liệu bổ sung có kiểm soát, ví dụ channel **do client tự khai**; nhận biết đó không phải dữ liệu được xác thực.
5. Cấu hình source bằng `formLogin(form -> form.authenticationDetailsSource(...))` hoặc `AbstractAuthenticationProcessingFilter.setAuthenticationDetailsSource(...)` khi thật sự dùng filter tùy chỉnh.
6. Phân biệt **metadata/details**, **principal**, **credentials**, **authorities**, **UserDetails** và **SecurityContext**.
7. Hiểu vì sao `UserDetailsService.loadUserByUsername(username)` không tự nhận `HttpServletRequest` và không nên dùng details như nguồn tự cấp quyền.
8. Kiểm thử cả login thành công, request metadata, session đã có/chưa có, request thiếu CSRF và request giả mạo header.
9. Xác định dữ liệu có thể log, dữ liệu phải redaction; xử lý IP sau reverse proxy, session fixation và metadata lỗi thời.
10. Áp dụng dữ liệu bổ sung vào giám sát hoặc risk assessment **chỉ qua ranh giới tin cậy phù hợp**, không coi một HTTP header do client gửi là proof of identity.

## 2. Đặt tên đúng: WebAuthenticationDetailsSource, không phải AuthenticationWebDetailsSource

Trong Spring Security 6.5 có các lớp/interface chính:

| Thành phần | Tên API chính xác | Chức năng |
| --- | --- | --- |
| Interface tạo details | `org.springframework.security.authentication.AuthenticationDetailsSource<C,T>` | Từ một context `C` tạo một đối tượng details `T` |
| Source mặc định cho web | `org.springframework.security.web.authentication.WebAuthenticationDetailsSource` | Từ `HttpServletRequest` tạo `WebAuthenticationDetails` |
| Dữ liệu details mặc định | `org.springframework.security.web.authentication.WebAuthenticationDetails` | Chứa remote address, session ID nếu đã có |
| Authentication | `org.springframework.security.core.Authentication` | `getDetails()` trả metadata tùy implementation; không nhất thiết luôn là `WebAuthenticationDetails` |
| Login filter chuẩn | `org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter` | Đọc username/password, tạo token và gọi details source |
| Lớp cha của login filter | `AbstractAuthenticationProcessingFilter` | Có `setAuthenticationDetailsSource(...)` và luồng success/failure |

**Ghi chú tên gọi:** “`AuthenticationWebDetailsSource`” trong tên bài nên được hiểu là chủ đề về nguồn metadata xác thực cho web; nếu tìm nguyên văn đó trong Javadoc Spring Security 6.5 sẽ không tìm thấy lớp chuẩn. Tên class dùng trong code phải là **`WebAuthenticationDetailsSource`**. Không tự đổi import thành tên không tồn tại rồi kết luận Gradle/Spring Boot thiếu dependency.

Interface khái quát có hình dạng:

```java
public interface AuthenticationDetailsSource<C, T> {
    T buildDetails(C context);
}
```

Đây là **trích mô tả chữ ký**, không phải file cần khai báo lại. Với web authentication, `C` là `HttpServletRequest` và `T` thường là `WebAuthenticationDetails` hoặc subclass tương thích.

Ví dụ sử dụng source chuẩn:

```java
AuthenticationDetailsSource<HttpServletRequest, WebAuthenticationDetails>
        source = new WebAuthenticationDetailsSource();

WebAuthenticationDetails details = source.buildDetails(request);
```

Đoạn này là snippet, giả định có `HttpServletRequest request` và imports đúng. Nếu chỉ cần IP/ID session mặc định, **không cần viết custom details source**.

## 3. Chi tiết được tạo ở đâu trong luồng xác thực?

Với form login bằng username/password:

```text
Browser
    |
    | POST /login: username, password, CSRF token
    v
Spring Security filter chain
    |
    v
UsernamePasswordAuthenticationFilter
    | 1. lấy username và password
    | 2. tạo UsernamePasswordAuthenticationToken chưa xác thực
    | 3. gọi authenticationDetailsSource.buildDetails(request)
    | 4. authRequest.setDetails(details)
    v
AuthenticationManager / ProviderManager
    |
    v
AuthenticationProvider (thường DaoAuthenticationProvider)
    | - UserDetailsService tải user và password hash
    | - PasswordEncoder kiểm tra password
    | - account-state checks và quy tắc provider khác
    v
Authentication thành công (hoặc AuthenticationException)
    |
    +--> Authentication.getDetails() có thể giữ details nguồn
    |
    v
SecurityContext + success/failure handling theo cơ chế đã cấu hình
```

Cụ thể, `UsernamePasswordAuthenticationFilter` có phương thức `setDetails(HttpServletRequest, UsernamePasswordAuthenticationToken)` và sử dụng `authenticationDetailsSource.buildDetails(request)`. Với `DaoAuthenticationProvider`/`AbstractUserDetailsAuthenticationProvider`, kết quả authentication thành công theo flow chuẩn thường **sao chép details của authentication request** sang authentication result.

**Không nhầm nhiệm vụ:** details source chỉ *tạo dữ liệu mô tả request*. Nó không xác thực password, không quyết định account được enabled/locked, không tự ghi session, không tự cấp `GrantedAuthority` và không thay thế `AuthenticationProvider`. Các provider/filter khác có thể dùng kiểu token/details khác; không khẳng định `getDetails()` của mọi authentication luôn là cùng một class.

### Phân biệt properties của Authentication

| Property / API | Nội dung | Cần chú ý |
| --- | --- | --- |
| `getPrincipal()` | Danh tính: `UserDetails`, username, `Jwt`… | Có thể chứa thông tin nội bộ; không serialize bừa |
| `getCredentials()` | Bằng chứng: password/token hoặc đã bị erase | **Không lưu vào details** hoặc ghi log |
| `getAuthorities()` | Quyền đã được cấp qua nguồn đáng tin | Dùng cho authorization, không lấy từ header tùy ý |
| **`getDetails()`** | Metadata tùy cơ chế, ví dụ remote address/session ID | Chủ yếu phục vụ ngữ cảnh sự kiện; giá trị có thể không đáng tin |
| `isAuthenticated()` | Trạng thái token theo contract | Không tự set true bằng dữ liệu client |
| `SecurityContextHolder.getContext()` | Container của authentication hiện tại | Scope của thread/request, không phải kho dữ liệu login vĩnh viễn |

Một request chứa `X-Role: ADMIN` không có nghĩa code được phép làm:

```java
// TUYỆT ĐỐI KHÔNG LÀM: header từ client không phải proof cấp quyền.
requestAuthentication.setDetails("ROLE_ADMIN");
```

Ngay cả khi bạn đã đặt string này trong details, Spring Security **không tự** biến nó thành `GrantedAuthority`. Nhưng nếu ứng dụng custom đọc details rồi tự cấp quyền, nó có thể tạo lỗ hổng privilege escalation.

## 4. WebAuthenticationDetails lấy gì mặc định?

Javadoc Spring Security 6.5 cho biết constructor `new WebAuthenticationDetails(request)` ghi nhận:

1. `getRemoteAddress()`: địa chỉ remote của HTTP request theo thông tin Servlet container nhận được, thường tương ứng `request.getRemoteAddr()`.
2. `getSessionId()`: session ID **nếu request đã có `HttpSession`**; nếu chưa có, giá trị có thể là `null`.

Nó **không gọi tạo session mới** chỉ để lấy ID. Hai giá trị này là **request metadata**, không phải danh tính đã được xác minh.

```java
WebAuthenticationDetailsSource source =
        new WebAuthenticationDetailsSource();

WebAuthenticationDetails d = source.buildDetails(request);

String address = d.getRemoteAddress();
String existingSessionId = d.getSessionId(); // có thể null
```

Đây là snippet trong Servlet context; không nên in `existingSessionId` vào log. Session ID có thể là **session bearer secret**, phải tránh lộ ra response, analytics, dashboard hoặc exception trace.

### 4.1. “Không tạo session” có nghĩa cụ thể gì?

Giả sử request không có session:

```text
Trước buildDetails:
    request.getSession(false) -> null

new WebAuthenticationDetailsSource().buildDetails(request):
    remote address = request.getRemoteAddr()
    session ID    = null
    không tạo HttpSession

Sau buildDetails:
    request.getSession(false) vẫn là null
```

Nhưng **các thành phần khác** vẫn có thể tạo session trong cùng HTTP request: CSRF token repository, request cache, login/session strategy, controller hoặc Servlet infrastructure. Do đó “WebAuthenticationDetails không tạo session” **không đồng nghĩa** “POST /login không bao giờ tạo session”.

### 4.2. Session ID trong details có thể là ID trước khi login hoàn tất

Các chiến lược chống **session fixation** có thể xoay/chuyển session ID sau khi credential được xác minh. `WebAuthenticationDetails` ghi ID tại lúc **filter xây details**, trước những bước success/session processing về sau.

Vì vậy:

- `details.getSessionId()` không nhất thiết bằng session ID cuối cùng của trình duyệt sau login.
- Không dùng `details.getSessionId()` như khóa dài hạn cho authorization, chống session fixation hay audit “phiên đang sống”.
- Muốn kiểm soát session hiện tại, dùng session management API đúng điểm lifecycle; không dựa trên ID capture ở bước attempt.
- Không lấy ID session từ details rồi đưa vào URL/JSON/metric labels.

### 4.3. Remote address sau reverse proxy

Nếu ứng dụng chạy sau load balancer/reverse proxy, `request.getRemoteAddr()` có thể là **IP của proxy**, không phải IP người dùng cuối. Các header `Forwarded`, `X-Forwarded-For`, `X-Real-IP` chỉ đáng tin **nếu lớp edge/proxy đáng tin đã xóa giá trị do client gửi và chèn giá trị chuẩn hóa**.

**Không đọc thủ công `request.getHeader("X-Forwarded-For")` và lấy phần tử đầu tiên làm identity/trusted IP** khi client có thể tự gửi header đó. Một attacker có thể tự khai `127.0.0.1` hoặc IP “trong danh sách cho phép”.

Nếu cần IP người dùng cuối cho fraud/rate limiting:

1. Xác định ranh giới trusted proxy/load balancer.
2. Chỉ chấp nhận forwarded metadata từ đường mạng đã xác thực/được bảo vệ.
3. Cấu hình xử lý Forwarded headers qua container/framework (ví dụ `ForwardedHeaderFilter` hoặc native support) **chỉ khi proxy trust được thiết lập đúng**.
4. Phân biệt TCP peer address với client address sau proxy. Trong log cần đặt tên rõ.
5. Không dùng IP đơn lẻ làm proof danh tính: NAT, VPN, di động và proxy làm IP thay đổi hoặc dùng chung.

## 5. Khi nào thật sự cần custom AuthenticationDetailsSource?

Một số tình huống nghiệp vụ cần metadata bổ sung tại thời điểm login:

- Channel người dùng **tự khai** (web/mobile), chỉ để phân tích UI/observability.
- Request correlation ID **do server/gateway tin cậy tạo** để liên kết audit logs.
- Tín hiệu rủi ro sơ bộ từ hệ thống edge đã được xác thực, ví dụ risk tier ở một request attribute do filter tin cậy gắn.
- Device characteristics có phạm vi hẹp, không chứa fingerprint quá chi tiết hay dữ liệu riêng tư không cần thiết.
- Tenant hint/organization slug để định tuyến login, **nhưng** vẫn phải kiểm tra membership và tính hợp lệ của tenant trong provider/authorization layer.
- WebAuthn/OIDC/challenge flow có thể cần dữ liệu request, nhưng không nên dùng details mặc định như nơi chứa raw token/OTP.

**Cần phân loại source trước khi dùng:**

| Dữ liệu | Ai kiểm soát? | Có thể dùng làm gì? | Không được mặc định dùng làm gì? |
| --- | --- | --- | --- |
| `X-Demo-Client: mobile` | HTTP client | Demo UI label/analytics đã normalize | Chứng minh dùng mobile app thật, cấp role |
| `X-Request-Id` tự gửi | Có thể là client | Correlation hiển thị với độ tin cậy thấp | Unique trusted audit ID |
| Internal trace ID do gateway cấp | Trusted edge nếu ranh giới được bảo vệ | Audit/trace correlation | Proof username/permission |
| `getRemoteAddr()` | Servlet container/trust chain | Một tín hiệu mạng có ngữ cảnh | User ID, role, MFA proof |
| Session ID hiện có | Servlet/session infrastructure | Thông tin request/session ngắn hạn | Giá trị công khai hoặc khóa authorization |
| OTP/password/token | Secret người dùng | Phải chuyển vào verifier/challenge flow có kiểm soát | Lưu bền trong details hoặc log |
| Header `X-Role` / `X-Tenant-Admin` | HTTP client | Bỏ qua hoặc ghi nhận cảnh báo có kiểm soát | Tạo `GrantedAuthority` |
| Request attribute đã được trusted filter xác minh | Server | Risk/policy input nếu có hợp đồng rõ | Tin mọi attribute có tên giống nhau không phân biệt nguồn |

### Nguyên tắc tối thiểu

Custom details nên **immutable sau khi tạo**, kích thước nhỏ, dữ liệu có ý nghĩa rõ ràng và an toàn khi session serialization. Không giữ `HttpServletRequest`, `HttpServletResponse`, `HttpSession`, InputStream, password hoặc raw header map trong details. Không đưa PII không cần thiết vào principal/session.

## 6. Ba cách viết custom source/details

### 6.1. Cách 1: giữ WebAuthenticationDetails và thêm thuộc tính

```java
final class RequestMetadataDetails extends WebAuthenticationDetails {
    private static final long serialVersionUID = 1L;

    private final String clientHint;

    RequestMetadataDetails(HttpServletRequest request) {
        super(request);

        String value = request.getHeader("X-Demo-Client");
        this.clientHint = "mobile".equalsIgnoreCase(value)
                ? "mobile-claimed"
                : "not-declared";
    }

    String getClientHint() {
        return clientHint;
    }
}
```

Đây là snippet thuộc một file Java có imports/Servlet dependency. Chỉ nhận giá trị trong một **allowlist** và giới hạn nội dung ngay tại lúc tạo details. `mobile-claimed` có nghĩa **client tự tuyên bố**, không phải server đã xác nhận mobile device.

Kế thừa `WebAuthenticationDetails` giúp giữ `getRemoteAddress()`, `getSessionId()` cùng các metadata bạn thêm. Việc `super(request)` không tạo session mới. Trong code thực, tránh để custom `toString()` tự in thêm chi tiết nhạy cảm.

### 6.2. Cách 2: implement AuthenticationDetailsSource

```java
final class RequestMetadataDetailsSource
        implements AuthenticationDetailsSource<
                HttpServletRequest, RequestMetadataDetails> {

    @Override
    public RequestMetadataDetails buildDetails(
            HttpServletRequest request) {
        return new RequestMetadataDetails(request);
    }
}
```

Đây là snippet, lớp được dùng trong project đầy đủ ở mục 7. Source mặc định là stateless, nên có thể dùng lại giữa nhiều request nếu bản thân class không giữ dữ liệu mutable theo user. **Đừng** lưu `currentUsername`, `lastIp` hoặc `lastSessionId` vào field của singleton details source — các request có thể chạy đồng thời và gây lẫn dữ liệu.

### 6.3. Cách 3: chỉ dùng source chuẩn

Nếu không có nhu cầu metadata riêng:

```java
http.formLogin(form -> form
        .authenticationDetailsSource(new WebAuthenticationDetailsSource()));
```

Đây là snippet trong cấu hình `SecurityFilterChain`, và trong nhiều trường hợp còn **không cần khai báo**, bởi source chuẩn đã được Spring Security cấu hình mặc định cho flow form login.

**Không viết custom class chỉ để sao chép y nguyên getRemoteAddr/sessionId** nếu không có hành vi mới. Càng ít logic dùng request không đáng tin, càng dễ kiểm soát rủi ro.

## 7. Ví dụ chạy được: Spring Boot form login với custom details

Project này chứng minh **đường filter thực**:

1. Form login chuẩn nhận `POST /login`.
2. `UsernamePasswordAuthenticationFilter` gọi custom `RequestMetadataDetailsSource`.
3. Details subclass lưu remote address, session ID nếu đã tồn tại và `clientHint` từ header.
4. `DaoAuthenticationProvider` xác minh password như thông thường.
5. `Authentication.getDetails()` trong request sau giữ details từ login session.
6. MockMvc test kiểm tra login success, CSRF, custom details và việc source chuẩn không tạo session.

**Giới hạn bảo mật của demo:** chỉ có tài khoản nội bộ `mai / demo-pass-123` và test channel **không đáng tin**; đừng dùng mật khẩu demo trong production. Dữ liệu custom được đưa ra endpoint `/whoami` chỉ để người học nhìn thấy; ứng dụng thật nên giảm thiểu metadata trả về và không công khai session ID hay thông tin mạng không cần thiết.

### 7.1. Cấu trúc

```text
web-auth-details-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/dev/demo/details/WebAuthDetailsDemoApplication.java
    └── test/java/dev/demo/details/WebAuthDetailsDemoApplicationTests.java
```

`settings.gradle`:

```groovy
rootProject.name = 'web-auth-details-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.7'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'dev.demo'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Spring Boot quản lý phiên bản Spring Security thích hợp theo BOM; không khai chồng một phiên bản khác tùy tiện. Dự án dùng Java 17+, Servlet namespace là `jakarta.servlet.*`, không phải `javax.servlet.*` của các thế hệ cũ.

### 7.2. Ứng dụng Java hoàn chỉnh

Tạo `src/main/java/dev/demo/details/WebAuthDetailsDemoApplication.java`:

```java
package dev.demo.details;

import java.util.LinkedHashMap;
import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationDetailsSource;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.WebAuthenticationDetails;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class WebAuthDetailsDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebAuthDetailsDemoApplication.class, args);
    }
}

@Configuration
class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder passwordEncoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("mai")
                        .password(passwordEncoder.encode("demo-pass-123"))
                        .roles("READER")
                        .build());
    }

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/login").permitAll()
                .requestMatchers("/whoami").authenticated()
                .anyRequest().denyAll());

        http.formLogin(form -> form
                .authenticationDetailsSource(
                        new RequestMetadataDetailsSource())
                .permitAll());

        // Không tắt CSRF, không tạo Authentication thủ công.
        // Form login và session management sử dụng cơ chế chuẩn.
        return http.build();
    }
}

// Nguồn metadata được gọi khi form-login filter tạo request token.
final class RequestMetadataDetailsSource
        implements AuthenticationDetailsSource<
                HttpServletRequest, RequestMetadataDetails> {

    @Override
    public RequestMetadataDetails buildDetails(HttpServletRequest request) {
        return new RequestMetadataDetails(request);
    }
}

// Serializable do WebAuthenticationDetails hỗ trợ lưu theo session.
final class RequestMetadataDetails extends WebAuthenticationDetails {
    private static final long serialVersionUID = 1L;
    private final String clientHint;

    RequestMetadataDetails(HttpServletRequest request) {
        super(request);

        // Header do client khai báo; chỉ dùng để hiển thị trong DEMO.
        String raw = request.getHeader("X-Demo-Client");
        this.clientHint = "mobile".equalsIgnoreCase(raw)
                ? "mobile-claimed"
                : "not-declared";
    }

    String clientHint() {
        return clientHint;
    }
}

@RestController
class CurrentAuthenticationController {

    @GetMapping("/whoami")
    Map<String, Object> whoami(Authentication authentication) {
        Map<String, Object> response = new LinkedHashMap<>();
        response.put("username", authentication.getName());

        Object details = authentication.getDetails();
        response.put("detailsType", details == null
                ? "none"
                : details.getClass().getSimpleName());

        if (details instanceof RequestMetadataDetails metadata) {
            response.put("clientHint", metadata.clientHint());

            // Chỉ minh họa; production không cần trả remote address.
            response.put("remoteAddress", metadata.getRemoteAddress());

            // KHÔNG trả session ID thực ra JSON.
            response.put("hadSessionAtLogin",
                    metadata.getSessionId() != null);
        }

        return response;
    }
}
```

**Giải thích chính xác đường xử lý:**

- `SecurityFilterChain` cho `/login`, `/whoami` và deny các endpoint khác. `formLogin(...)` đăng ký filter xử lý `POST /login` cùng trang login mặc định.
- `.authenticationDetailsSource(new RequestMetadataDetailsSource())` là cấu hình tại **authentication filter**, không phải trong `UserDetailsService`.
- `RequestMetadataDetailsSource.buildDetails(request)` được gọi trên request login và trả một object **mới** cho request đó.
- `RequestMetadataDetails` kế thừa `WebAuthenticationDetails`: IP và session ID lấy theo Servlet request. Giá trị `clientHint` là một **claim do client đưa**, bị normalize thành hai giá trị cố định và không được dùng để cấp quyền.
- `InMemoryUserDetailsManager` cung cấp user/BCrypt hash; việc xác minh password thuộc provider của Spring Security, không phải details source.
- Khi đăng nhập thành công, details thường được giữ trên authentication result và có thể xuất hiện ở `/whoami` qua session.
- Controller chỉ trả **boolean** về việc lúc attempt đã có session, không xuất actual session ID.
- CSRF mặc định còn bật: POST form login từ browser phải cung cấp CSRF token phù hợp. MockMvc dùng `.with(csrf())` để giả lập proof của test.
- Login filter chuẩn còn xử lý success/failure, session strategy và lưu `SecurityContext` theo cấu hình; nếu tự viết filter/controller, trách nhiệm session có thể khác.

### 7.3. Test thực sự qua filter chain bằng MockMvc

Tạo `src/test/java/dev/demo/details/WebAuthDetailsDemoApplicationTests.java`:

```java
package dev.demo.details;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.security.web.authentication.WebAuthenticationDetails;
import org.springframework.security.web.authentication.WebAuthenticationDetailsSource;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class WebAuthDetailsDemoApplicationTests {

    @Autowired
    private MockMvc mvc;

    @Test
    void defaultSourceDoesNotCreateSession() {
        MockHttpServletRequest request =
                new MockHttpServletRequest("POST", "/login");
        request.setRemoteAddr("203.0.113.8");

        assertNull(request.getSession(false));

        WebAuthenticationDetails details =
                new WebAuthenticationDetailsSource()
                        .buildDetails(request);

        assertEquals("203.0.113.8", details.getRemoteAddress());
        assertNull(details.getSessionId());
        assertNull(request.getSession(false));
    }

    @Test
    void formLoginAttachesDetailsAndKeepsAuthentication() throws Exception {
        MockHttpSession session = new MockHttpSession();

        mvc.perform(post("/login")
                        .session(session)
                        .with(csrf())
                        .with(request -> {
                            request.setRemoteAddr("198.51.100.23");
                            return request;
                        })
                        .header("X-Demo-Client", "mobile")
                        .param("username", "mai")
                        .param("password", "demo-pass-123"))
                .andExpect(status().is3xxRedirection());

        // Request khác nhưng cùng session đã được xác thực.
        mvc.perform(get("/whoami").session(session))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value("mai"))
                .andExpect(jsonPath("$.detailsType")
                        .value("RequestMetadataDetails"))
                .andExpect(jsonPath("$.clientHint")
                        .value("mobile-claimed"))
                .andExpect(jsonPath("$.remoteAddress")
                        .value("198.51.100.23"))
                .andExpect(jsonPath("$.hadSessionAtLogin")
                        .value(true));
    }

    @Test
    void clientHeaderDoesNotGrantAnyAdditionalRole() throws Exception {
        MockHttpSession session = new MockHttpSession();

        mvc.perform(post("/login")
                        .session(session)
                        .with(csrf())
                        .header("X-Demo-Client", "admin")
                        .param("username", "mai")
                        .param("password", "demo-pass-123"))
                .andExpect(status().is3xxRedirection());

        mvc.perform(get("/whoami").session(session))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.clientHint")
                        .value("not-declared"))
                .andExpect(jsonPath("$.username")
                        .value("mai"));
    }

    @Test
    void csrfIsStillRequiredForFormLogin() throws Exception {
        mvc.perform(post("/login")
                        .param("username", "mai")
                        .param("password", "demo-pass-123"))
                .andExpect(status().isForbidden());
    }
}
```

Chạy test từ thư mục `web-auth-details-demo`:

```bash
gradle test
```

Nếu đã có Gradle Wrapper, chạy `./gradlew test` trên macOS/Linux hoặc `gradlew.bat test` trên Windows.

Chạy ứng dụng để mở trang login mặc định:

```bash
gradle bootRun
```

Truy cập `http://localhost:8080/login`, đăng nhập bằng tài khoản demo; sau đó mở `http://localhost:8080/whoami` để quan sát JSON. Thao tác qua browser **không tự đặt header `X-Demo-Client`**, vì vậy `clientHint` mặc định sẽ là `not-declared`, trừ khi client/test đã gửi header. Không tự viết lệnh POST `/login` không có CSRF token rồi tưởng framework bị lỗi — browser form login chuẩn có token trong form.

### 7.4. Kết quả kỳ vọng

| Test | Điều kiện | Kết quả |
| --- | --- | --- |
| `defaultSourceDoesNotCreateSession` | Mock request không có session | `getSessionId() == null`; sau build vẫn không có session |
| `formLoginAttachesDetailsAndKeepsAuthentication` | Login hợp lệ + session có sẵn + header mobile | Login redirect; `/whoami` 200, user mai, detailsType custom |
| `clientHeaderDoesNotGrantAnyAdditionalRole` | Header tự khai admin | Không tạo role ADMIN; chỉ nhận `not-declared` |
| `csrfIsStillRequiredForFormLogin` | POST login không CSRF token | **403** |

Ví dụ JSON từ `/whoami` khi test login hợp lệ:

```json
{
  "username": "mai",
  "detailsType": "RequestMetadataDetails",
  "clientHint": "mobile-claimed",
  "remoteAddress": "198.51.100.23",
  "hadSessionAtLogin": true
}
```

JSON này mô tả **request test có session được tạo trước login** và remote address được MockMvc đặt cho HTTP request; không nên coi IP thật luôn có giá trị đó. Kết quả được suy ra từ code, **không phải log của test đã được chạy trong tài liệu này**.

**Phân biệt hai điều đáng tin:** testcase chứng minh source được gọi và details xuất hiện sau login; nó **không tự chứng minh** rằng header mobile phát ra từ một ứng dụng mobile được ký hoặc rằng IP dùng cho allowlist là đáng tin.

## 8. Tích hợp với formLogin và filter tùy chỉnh: chọn đúng điểm mở rộng

### 8.1. Cách tốt nhất cho form login: dùng DSL trực tiếp

Khi ứng dụng dùng `formLogin`:

```java
http.formLogin(form -> form
        .authenticationDetailsSource(
                new RequestMetadataDetailsSource()));
```

Đây là snippet trong `SecurityFilterChain`. Spring Security tạo và cấu hình login filter; bạn không phải tự xây `UsernamePasswordAuthenticationFilter` chỉ để thay details source.

`FormLoginConfigurer` kế thừa configurer có phương thức `authenticationDetailsSource(AuthenticationDetailsSource<HttpServletRequest, ?>)`. API này đã có trong Spring Security 6.5.

### 8.2. Khi dùng UsernamePasswordAuthenticationFilter custom

Một filter tùy chỉnh có thể cấu hình:

```java
UsernamePasswordAuthenticationFilter filter =
        new UsernamePasswordAuthenticationFilter();

filter.setAuthenticationManager(authenticationManager);
filter.setAuthenticationDetailsSource(
        new RequestMetadataDetailsSource());

// Còn phải cấu hình matching, success/failure,
// SecurityContextRepository, session strategy và vị trí filter.
```

Đây là **snippet cấu hình chưa hoàn chỉnh**, không nên copy thêm ngay filter này vào chain vốn đã có form login chuẩn. Nếu vô tình để **hai filter** đều xử lý `POST /login`, có thể có hai lần authentication, handler khác nhau và việc lưu session/CSRF khó kiểm tra.

`AbstractAuthenticationProcessingFilter` có setter tương đương `setAuthenticationDetailsSource(...)`, và các subclass phù hợp có thể kế thừa. Hãy xác minh flow của đúng filter đang xử lý request.

Nếu ứng dụng viết custom `OncePerRequestFilter` thay vì subclass `AbstractAuthenticationProcessingFilter`, source **không tự được gọi**. Bạn phải tự xây `Authentication` và đặt `details`:

```java
UsernamePasswordAuthenticationToken token =
        UsernamePasswordAuthenticationToken.unauthenticated(
                username, password);

token.setDetails(detailsSource.buildDetails(request));

Authentication result = authenticationManager.authenticate(token);
```

Đây chỉ là **snippet tạo authentication attempt**. Cần kiểm tra credential thật, error handling, security context, session fixation/CSRF, lưu context (Spring Security 6 explicit save cho manual authentication) và vị trí filter. Chỉ gắn details không biến token thành đã xác thực.

### 8.3. Khác biệt ở API/token filters

HTTP Basic, bearer JWT, API key, OAuth2 login, SAML, pre-auth và custom credential converter có những nơi tạo `Authentication` khác nhau:

- Có filter dùng details source mặc định, có filter tự tạo details, có filter không gắn `WebAuthenticationDetails`.
- `Authentication.getDetails()` không có kiểu trả về cố định ngoài `Object`.
- `formLogin.authenticationDetailsSource(...)` **chỉ cấu hình form-login filter tương ứng**, không tự ảnh hưởng tới BearerTokenAuthenticationFilter hoặc filter của chain khác.
- Nếu ứng dụng có nhiều `SecurityFilterChain`, phải xác định **chain nào được chọn** và filter nào xử lý path.
- Trong WebFlux, ngữ cảnh thường ở Reactor Context, không thể bê nguyên ``jakarta.servlet.http.HttpServletRequest` và form-login servlet source sang reactive authentication.

Không viết code cast mù quáng:

```java
// DỄ LỖI khi Authentication đến từ token/flow khác.
WebAuthenticationDetails details =
        (WebAuthenticationDetails) authentication.getDetails();
```

Dùng `instanceof` hoặc contract cụ thể nếu application thật sự chỉ chấp nhận một kiểu token.

## 9. Dữ liệu details có thể đi vào đâu sau login?

Trong một flow dùng session, `SecurityContext` chứa `Authentication`, và `Authentication` có thể giữ `details`. Do đó details **có thể được giữ qua nhiều request trong session**.

Hệ quả:

1. IP trong details có thể là **IP ở lần login**, không phải IP ở request hiện tại.
2. `getSessionId()` có thể là ID **trước khi xoay session**; không dùng để đại diện cho session ID hiện hành.
3. Nếu custom details chứa object không serializable, **Spring Session/distributed session storage** có thể gặp lỗi serialize/replicate.
4. Nếu details chứa raw token/password, bí mật có thể bị giữ trong session, heap dump hoặc logs lâu hơn cần thiết.
5. Khi user logout/reset password hoặc policy thay đổi, details snapshot không tự được refresh theo mỗi request.
6. Với JWT resource server stateless, `Authentication` thường được tạo lại từ token; không có đảm bảo custom form-login details xuất hiện.

**Bài học thiết kế:** chỉ giữ vài giá trị cần cho mục đích hợp lệ, hạn chế thời gian lưu và khả năng serialize. Với dữ liệu risk lớn cần cập nhật liên tục, có thể chỉ lưu một opaque reference ID an toàn thay vì object graph.

### Tránh lẫn hai loại request metadata

- **Login-time metadata:** thông tin tại thời điểm authentication attempt.
- **Current-request metadata:** thông tin của HTTP request đang được xử lý sau login.

Nếu bạn muốn rate limit request hiện tại hoặc thực hiện policy mạng tại mỗi API call, phải lấy input từ **request hiện tại và trusted edge**, không dùng `Authentication.getDetails().getRemoteAddress()` của login cách đây nhiều giờ.

## 10. AuthenticationDetailsSource có phải chỗ thích hợp để quyết định MFA, risk và tenant?

**Không phải tự thân.** Details source có thể tạo các **tín hiệu đầu vào** cho hệ thống quyết định rủi ro. Nhưng quyết định challenge/allow/deny phải thuộc một lớp đã có hợp đồng trust, kiểm tra input, xác minh credential và quản lý state.

### 10.1. Ví dụ risk signal đáng tin

Giả sử một filter/trusted gateway xác minh device attestation hoặc tính toán risk score. Thay vì cho client gửi header tùy ý rồi coi là verified, kiến trúc có thể:

```text
Client HTTP request
      ↓
Trusted edge / attestation verification
      ↓
Edge loại bỏ header giả mạo, gắn trusted metadata
      ↓
Application filter đã xác minh nguồn
      ↓ request attribute: verifiedRiskTier = LOW / HIGH
AuthenticationDetailsSource.buildDetails(request)
      ↓
Custom auth/risk policy sử dụng typed risk signal
      ↓
AuthenticationProvider / MFA challenge / deny theo policy
```

Tại lớp application, hãy kiểm tra rằng `verifiedRiskTier` **thực sự do filter đáng tin đặt**, chứ không phải một param mà client tự điền. Đừng mở API đọc chung `request.getAttribute("verifiedRiskTier")` rồi coi bất kỳ filter nào hoặc controller nào cũng được đặt/ghi đè.

### 10.2. Nếu cần thêm OTP thì sao?

OTP là **credential/challenge proof**, không phải metadata để lưu lâu dài vào `WebAuthenticationDetails` rồi xuất hiện trong `SecurityContext` sau login. Các hướng thích hợp hơn:

- Một `AuthenticationConverter` hoặc custom filter tạo token có các trường credential cần cho provider và bảo đảm cleanup.
- Một `AuthenticationProvider` hoặc multi-step authentication flow xác minh OTP/WebAuthn challenge đúng ranh giới.
- Một challenge state ngắn hạn có TTL, bảo vệ CSRF/replay, xử lý thất bại/rate limit và không cấp full authentication trước khi hoàn tất MFA.
- Dọn xóa chứng cứ tạm thời khi xác minh xong; không serialize raw OTP vào session object details.

**Đừng lấy một flag `mfaPassed=true` từ header rồi gắn vào details và coi là MFA đã hoàn tất.**

### 10.3. Nếu cần tenant ID thì sao?

Tenant slug có thể đến từ path/subdomain/login form; nó là **routing hint**, không phải bằng chứng user thuộc tenant. Phải ràng buộc tenant ID với account lookup, credential validation và authorization policy. Sau login, không cho client tự đổi tenant bằng header nếu chưa có transition/authorization hợp lệ.

Nếu dùng multi-tenant, hãy thiết kế rõ cache keys, session isolation, audit namespace và mọi query có tenant scope. Đừng gắn `tenantId` vào details rồi quên dùng nó trong provider hoặc service khi kiểm tra dữ liệu.

## 11. UserDetailsService có lấy được HttpServletRequest không?

Contract `UserDetailsService.loadUserByUsername(String username)` nhận **một tham số username**, không nhận `HttpServletRequest`, `WebAuthenticationDetails` hay `Authentication`. Vì vậy không thể giả định trong implementation có request details sẵn để đọc.

Một số giải pháp dựa vào `RequestContextHolder`/thread locals hoặc bean request-scoped có thể truy cập request trong web thread, nhưng dễ tạo coupling tới Servlet, khó test, có thể không hoạt động trong background task và **không phải đường mặc định để đưa dữ liệu request vào provider**.

Nếu chính sách xác thực **thật sự cần request metadata** (IP đã trusted, device proof, tenant, risk), những lựa chọn rõ ràng hơn:

1. Custom `AuthenticationProvider` nhận một `Authentication` có details và kiểm tra thêm policy.
2. Custom `AuthenticationConverter`/filter tạo một token được định nghĩa rõ, xử lý credential/challenge đúng nguồn.
3. Risk service được gọi từ đúng điểm của authentication pipeline, với context typed và trust contract.
4. Cơ chế authentication chuẩn (MFA/OIDC/WebAuthn) nếu nghiệp vụ phù hợp, không tự phát minh provider yếu.

**Không để `UserDetailsService` cấp role từ request header**. Vai trò của nó là tải user từ nguồn danh tính đã được tin cậy, không phải thẩm định quyền do client khai báo.

## 12. Bảo mật, quyền riêng tư và audit của WebAuthenticationDetails

### 12.1. Không log secrets hoặc toàn bộ Authentication

`WebAuthenticationDetails` mặc định có session ID và remote address. Gọi `toString()` có thể sinh thông tin nhạy cảm tùy implementation; không log nguyên object `Authentication`/`details` một cách vô điều kiện.

Tránh ghi:

- Raw password, OTP, recovery token, API key, OAuth2 bearer token.
- Cookie, session ID, `Authorization` header và CSRF token.
- Dữ liệu định danh/fingerprint thiết bị chi tiết không cần thiết.
- Chuỗi header tự do không bị giới hạn độ dài hoặc chưa được sanitize (nguy cơ log injection).
- IP/client hints dưới dạng metric labels cardinality cao.

Nếu cần audit, ưu tiên **account internal ID, event type, timestamp, correlation ID được phát hành đáng tin, result class** và một dấu hiệu mạng đã được chuẩn hóa theo policy. Áp dụng access control/retention/privacy policy.

### 12.2. Không có xác thực chính xác chỉ từ IP

`getRemoteAddress()` là một dữ kiện mạng trong môi trường đang chạy. Nó không chứng minh:

- Người dùng nào đang ngồi trước thiết bị.
- Session có cùng chủ thể với IP hiện tại.
- Request đi qua đúng ứng dụng mobile.
- Thiết bị đã vượt qua MFA.
- User có `ROLE_ADMIN` hoặc thuộc tenant nhất định.

Dựa vào IP để quyết định “bỏ qua password” hoặc cấp role là thiết kế dễ lỗi, nhất là khi có shared NAT, reverse proxy, VPN hoặc attacker kiểm soát đường header.

### 12.3. Không tạo session chỉ để đưa ID vào details

Session ID có thể null, và điều này **hợp lệ**. Không viết:

```java
// Không nên tạo session vô điều kiện chỉ vì muốn có sessionId trong details.
String id = request.getSession(true).getId();
```

Đây là anti-pattern. Tạo session có thể tăng memory/session storage và tạo cookie không cần thiết cho các request stateless. Nếu ứng dụng yêu cầu session-based login, để Spring Security session strategy/repository xử lý khi cần.

### 12.4. Dữ liệu từ header phải có giới hạn độ dài và nguồn tin cậy

Demo chỉ dùng allowlist `mobile`; các giá trị khác rơi vào `not-declared`. Ứng dụng thật nên:

- Chặn request/header quá lớn ở gateway và server.
- Normalize và validate đúng schema, reject hoặc ignore dữ liệu không hợp lệ.
- Không dùng header tùy ý trong SQL, paths, log format hay serialization không sanitize.
- Ghi rõ metadata là `claimed`, `verified` hay `derived`.
- Với forwarded headers, xác định proxy trust chain và ngăn client tự đưa giá trị được coi là “verified”.

## 13. Những sai lầm hay gặp

1. **Nhập `AuthenticationWebDetailsSource` trong code** rồi tìm dependency không tồn tại. Tên API là `WebAuthenticationDetailsSource`.
2. **Nhầm `WebAuthenticationDetailsSource` với `WebAuthenticationDetails`:** một bên là factory, một bên là value object.
3. **Cho rằng details source xác minh credential:** authentication provider/manager mới xử lý password/credential theo contract.
4. **Cho rằng remote address luôn là IP gốc client:** có thể chỉ là IP reverse proxy.
5. **Tin trực tiếp `X-Forwarded-For` do client gửi:** cho phép spoof IP nếu không có proxy trust.
6. **Cho rằng buildDetails tạo HttpSession:** source chuẩn không tạo session chỉ để lấy ID.
7. **Cho rằng session ID trong details luôn là session ID sau login:** session fixation protection có thể xoay ID.
8. **Log `WebAuthenticationDetails.toString()` hoặc actual session ID:** có thể làm lộ bearer secret.
9. **Cho rằng details chứa email, roles, device ID mặc định:** mặc định chỉ là remote address và ID của session có sẵn.
10. **Gán `X-Role: ADMIN` hoặc `X-MFA: passed` thành `GrantedAuthority`:** client không được tự quyết định quyền.
11. **Đưa raw password/OTP vào details:** dữ liệu có thể được giữ trong authenticated session.
12. **Lưu `HttpServletRequest` trong details:** request object không an toàn để giữ lâu/serialize.
13. **Giữ field mutable `lastClientIp` trong source singleton:** gây lẫn thông tin giữa requests đồng thời.
14. **Tự cast `authentication.getDetails()` sang một subtype mà không kiểm tra:** fail với Basic/JWT/custom providers.
15. **Cấu hình form-login details source rồi nghĩ nó tự áp dụng cho JWT filter:** mỗi authentication mechanism có pipeline khác.
16. **Tự thêm UsernamePasswordAuthenticationFilter vào chain đã dùng formLogin:** nguy cơ double authentication.
17. **Chỉ set details ở success handler sau login:** quá muộn nếu provider/risk cần dữ liệu trong authentication attempt.
18. **Tự viết custom filter thiếu `setDetails`:** provider không nhận request metadata mong muốn.
19. **Manual authentication chỉ `SecurityContextHolder.setContext` trong Spring Security 6:** context có thể không persist nếu không explicit save đúng repository.
20. **Dùng `UserDetailsService` để truy cập Servlet request qua ThreadLocal mà không có lý do:** coupling mạnh, test khó.
21. **Chỉ kiểm tra có details trong cùng request:** không chứng minh session lưu hoặc metadata được chuyển sang request sau.
22. **Dùng details login-time cho IP/rate-limit ở request nhiều giờ sau:** dữ liệu đã cũ.
23. **Không kiểm tra CSRF trong form login với cookie:** tạo rủi ro login CSRF và những vấn đề khác.
24. **Không bảo vệ identity khi tenant hint đổi:** header không xác minh membership/tenant isolation.
25. **Ghi metrics với username/IP/sessionId làm label:** rò rỉ và cardinality cao.
26. **Không đối chiếu phiên bản namespace jakarta/javax:** Spring Security 6/Spring Boot 3 dùng `jakarta.servlet`.
27. **Không kiểm thử reverse proxy/header spoofing:** dễ tạo ranh giới trusted IP sai.
28. **Không xác định dữ liệu nào cần tồn tại trong session:** có thể lưu PII hoặc secret không cần thiết.

## 14. Bài tập thực hành

**Bài A — Đúng tên API.** Giải thích `AuthenticationDetailsSource<C,T>`, `WebAuthenticationDetailsSource`, `WebAuthenticationDetails` và `Authentication.getDetails()`. Nêu lý do `AuthenticationWebDetailsSource` không phải import chuẩn trong Spring Security 6.5.

**Bài B — Source mặc định.** Tạo `MockHttpServletRequest` không có session, gọi `new WebAuthenticationDetailsSource().buildDetails(request)`, assert IP và `sessionId == null`, confirm `getSession(false)` vẫn null.

**Bài C — Source custom.** Thêm một field `clientHint` được normalize theo allowlist, chạy test `X-Demo-Client=mobile` và một giá trị bất kỳ. Giải thích sự khác biệt giữa `mobile-claimed` và mobile đã được xác thực.

**Bài D — Filter pipeline.** Chạy `gradle test` ở mục 7, đặt breakpoint trong `buildDetails`, `UsernamePasswordAuthenticationFilter.setDetails`, `DaoAuthenticationProvider` và controller. Ghi rõ thứ tự gọi, kết quả `Authentication.getDetails()` và hành vi khi password sai.

**Bài E — Authentication failure.** Đăng nhập mật khẩu sai, kiểm tra không có authenticated session và không công bố session ID/password trong response/log. Chứng minh details được tạo **không có nghĩa credential được chấp nhận**.

**Bài F — CSRF.** Xác minh POST `/login` thiếu CSRF token bị từ chối trong demo và form login với token hợp lệ hoạt động. Không tắt CSRF chỉ để test đơn giản hơn.

**Bài G — Proxy.** Vẽ trust chain client → LB → gateway → app, thử client tự đặt `X-Forwarded-For`, rồi nêu chính sách loại bỏ/chuẩn hóa headers ở trusted edge. Không kết luận IP từ header tự khai là proof.

**Bài H — Session fixation.** Ghi nhận `details.getSessionId()` trước khi login thành công và session ID sau strategy. Giải thích vì sao không nên dùng field đó làm khóa hiện hành; **không log actual ID trong hệ thống chung**.

**Bài I — Tenant/role spoofing.** Thêm header `X-Role=ADMIN` hoặc `X-Tenant=other` và chứng minh user `mai` chỉ có `ROLE_READER`. Nếu có tenant thật, kiểm tra membership và object permissions ở tầng trusted provider/service.

**Bài J — Multi-chain.** Định nghĩa form-login chain và JWT API chain, tìm chain nào được chọn cho từng path. Xác minh `formLogin.authenticationDetailsSource` không tự ảnh hưởng JWT principal.

**Bài K — Audit.** Thiết kế một event `LoginAttempt` với internal account ID (nếu đã biết), outcome, timestamp và trusted correlation ID; quyết định lưu IP ở mức nào và chính sách retention. Loại password, session ID, OTP và token khỏi event.

### Tiêu chí hoàn thành

Bạn có thể tự trình bày:

- Class nào thực sự tên là `WebAuthenticationDetailsSource`, và tên trong đề bài có gì cần lưu ý?
- Source mặc định tạo những field nào, session có bị tạo chỉ để lấy ID không?
- Filter xây details trước hay sau khi `AuthenticationManager.authenticate(...)`?
- Cách cấu hình custom source trong `formLogin` hoặc filter tùy chỉnh?
- Vì sao `UserDetailsService` không tự nhận `HttpServletRequest`?
- Khi nào metadata đáng tin đủ để làm risk signal, khi nào chỉ là client claim?
- Tại sao không dùng header tự khai để cấp authority/MFA/tenant permission?
- Làm sao kiểm thử đường login thực, CSRF, session, privacy và chống metadata lỗi thời?

## 15. Tài liệu chính thức

- [Spring Security 6.5.11 — WebAuthenticationDetailsSource](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/WebAuthenticationDetailsSource.html): class chuẩn, `buildDetails(HttpServletRequest)`.
- [Spring Security 6.5.11 — WebAuthenticationDetails](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/WebAuthenticationDetails.html): remote address, session ID và quy tắc không tạo session.
- [Spring Security 6.5.11 — AuthenticationDetailsSource](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/AuthenticationDetailsSource.html): generic contract `buildDetails`.
- [Spring Security 6.5.11 — AbstractAuthenticationProcessingFilter](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/AbstractAuthenticationProcessingFilter.html): `setAuthenticationDetailsSource` và authentication lifecycle.
- [Spring Security 6.5.11 — AbstractAuthenticationFilterConfigurer](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/config/annotation/web/configurers/AbstractAuthenticationFilterConfigurer.html): DSL `authenticationDetailsSource` và source mặc định.
- [Spring Security 6.5 — Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html): `UsernamePasswordAuthenticationFilter` và flow login.
- [Spring Security 6.5 — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): `Authentication`, provider, context và authorities.
- [Spring Security 6.5 — Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html): session fixation, context persistence và login.
- [Spring Security 6.5 — CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html): CSRF với browser session/form login.
- [Spring Framework — ForwardedHeaderFilter](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/filter/ForwardedHeaderFilter.html): xử lý forwarded headers và ranh giới trusted proxy.

**Ghi chú phiên bản:** nội dung bám theo Spring Security Servlet 6.5 / Spring Boot 3.5.7 và Java 17+. Khi dùng Spring Security 7, WebFlux, custom OAuth2/JWT provider hoặc container/proxy khác, cần đối chiếu chính xác class/API hiện hành. Đặc biệt, `Authentication.getDetails()` không phải một security principal mới và không làm dữ liệu HTTP request tự nhiên trở thành đáng tin.