# SessionCreationPolicy: ALWAYS, IF_REQUIRED, NEVER và STATELESS

> **Ngữ cảnh:** Spring Security 6 trên Servlet stack, Java 17+, ứng dụng Spring MVC. `SessionCreationPolicy` quy định cách Spring Security dùng `HttpSession` để quản lý `SecurityContext`, không phải công tắc vô hiệu hóa mọi session hay mọi loại state trong ứng dụng. Bài học so sánh bốn giá trị, chỉ ra sự khác nhau cốt lõi giữa `NEVER` và `STATELESS`, minh họa form login, REST API và một project Spring Boot 3.3.5 chạy được.

## 1. HTTP session và SecurityContext là hai khái niệm khác nhau

HTTP xử lý từng request độc lập. Ứng dụng web dùng form login thường muốn nhớ người dùng đã đăng nhập khi họ chuyển trang. Trong Servlet, `HttpSession` là một vùng dữ liệu phía server, được nhận diện bằng session ID, thường chuyển qua cookie `JSESSIONID`. Spring Security có thể lưu `SecurityContext` vào session để request sau tìm lại `Authentication`.

```text
Browser: POST /login + CSRF + credentials
       |
       v
Authentication filter
       |
       v
AuthenticationManager / AuthenticationProvider
       |
       v
Authentication đã kiểm chứng
       |
       v
SecurityContext / SecurityContextRepository
       |
       +-- Có thể lưu context vào HttpSession
       |
       v
Browser: GET /dashboard + JSESSIONID
       |
       v
SecurityContext được tải theo chính sách security
       |
       v
AuthorizationFilter kiểm tra quyền
```

Tuy nhiên, không phải ứng dụng nào cũng cần phiên đăng nhập browser. Một REST API có thể nhận Bearer token hoặc HTTP Basic credentials **ở mỗi request** và tự kiểm chứng. Trong mô hình này, sử dụng session của giao diện web để xác thực API đôi khi là điều không mong muốn.

`SessionCreationPolicy` trả lời: **Spring Security có được tạo HttpSession không, và có được sử dụng HttpSession đã tồn tại để lấy SecurityContext không?** Nó **không** tự định nghĩa timeout, session fixation protection, quyền URL, CSRF, login form hoặc việc kiểm chứng token.

## 2. Bảng so sánh bốn chính sách

Enum nằm ở `org.springframework.security.config.http.SessionCreationPolicy`:

```java
import org.springframework.security.config.http.SessionCreationPolicy;
```

| Policy | Có chủ động tạo HttpSession cho security? | Dùng session tồn tại để lấy SecurityContext? | Hình dung |
| --- | --- | --- | --- |
| **`ALWAYS`** | **Có**, tạo sớm ngay cả khi không bắt buộc | Có | Luôn có session |
| **`IF_REQUIRED`** | **Chỉ khi cần** cho cơ chế security | Có | Tạo theo nhu cầu |
| **`NEVER`** | Không tự tạo cho mục đích quản lý SecurityContext | **Có thể dùng session sẵn có** | Không tạo, có thì dùng |
| **`STATELESS`** | Không tạo để quản lý SecurityContext | **Không dùng HttpSession làm nguồn SecurityContext** | Xác thực độc lập từng request |

Chú ý phần chữ đậm: **NEVER và STATELESS không giống nhau**. Khi client mang cookie của một `HttpSession` hợp lệ chứa `SecurityContext`:

- Với `NEVER`, Spring Security **có thể** đọc security context trong session đó.
- Với `STATELESS`, Spring Security **không** lấy authentication từ session đó.

Đây là điểm quan trọng khi một ứng dụng có **web login bằng cookie** và **API yêu cầu Bearer token/Basic credentials**. Nếu API không được phép dùng web session để xác thực, `STATELESS` có ý nghĩa rõ hơn `NEVER`.

**Giới hạn của bảng:** nó mô tả cách Spring Security cấu hình sử dụng session. Code của ứng dụng, Servlet container, thư viện MVC hoặc một thành phần khác vẫn có thể tạo `HttpSession` trong một request. Ngoài ra, các tính năng như request cache, CSRF và login handlers có quản lý state riêng, vì vậy phải xem **toàn bộ chain thực tế** nếu muốn chắc chắn session được tạo ở đâu.

## 3. Cách cấu hình bằng Java DSL

Trong một bean `SecurityFilterChain`:

```java
@Bean
SecurityFilterChain webChain(HttpSecurity http) throws Exception {
    http.sessionManagement(session -> session
            .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED)
    );
    http.authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated()
    );
    http.formLogin(Customizer.withDefaults());
    return http.build();
}
```

Đoạn trên là **fragment Java**: nó phải nằm trong `@Configuration` và cần imports của Spring Security. Project chạy được nằm ở mục 9. Để thay chính sách, chọn **một** trong bốn hằng:

```java
SessionCreationPolicy.ALWAYS
SessionCreationPolicy.IF_REQUIRED
SessionCreationPolicy.NEVER
SessionCreationPolicy.STATELESS
```

Không viết bốn lần `sessionCreationPolicy(...)` trong cùng một chain rồi mong chúng cộng dồn. Mỗi chain có chính sách session mà code cấu hình cuối cùng của nó lựa chọn.

### Nhận biết ngay các nhầm lẫn

- Có `HttpSession` **không đồng nghĩa** user đã đăng nhập.
- Có `Authentication` trong `SecurityContextHolder` của request hiện tại **không chứng minh** nó được lưu sang request sau.
- Không thấy `Set-Cookie` ở một response **không chứng minh** request không có session, vì session có thể đã tồn tại và client đã gửi cookie.
- Nhìn thấy `JSESSIONID` khi `STATELESS` **không chứng minh Spring Security dùng session để xác thực**; một thành phần khác có thể tạo session.
- `STATELESS` **không** tự bật JWT decoder hoặc kiểm chứng token.
- `IF_REQUIRED` **không** có nghĩa mọi request anonymous đều không tạo session.

## 4. ALWAYS — Spring Security chủ động tạo session

```java
http.sessionManagement(s -> s
        .sessionCreationPolicy(SessionCreationPolicy.ALWAYS));
```

Với policy này, Spring Security tạo `HttpSession` sớm trong vòng đời request được security chain xử lý, ngay cả khi request công khai chưa cần lưu authentication. Trong cấu hình Servlet phổ biến, framework có thể dùng `ForceEagerSessionCreationFilter` để thực hiện hành vi đó.

Ví dụ:

```text
Browser chưa có JSESSIONID
    |
    v
GET /public
    |
    v
Security filter chain (ALWAYS)
    |
    +--> tạo HttpSession
    |
    v
Controller gọi request.getSession(false)
    |
    v
Trả về một HttpSession, dù người dùng anonymous
```

**Ưu điểm:** hữu ích nếu ứng dụng legacy hoặc một cơ chế stateful thực sự yêu cầu session có mặt cho mọi request.

**Đổi lại:** request công khai cũng tạo server-side state; tăng chi phí lưu trữ, memory và tải của session store, có thể khiến ứng dụng khó scale hơn. `ALWAYS` không làm việc kiểm tra password tốt hơn, không tự bật MFA, concurrent-session limit hoặc session timeout. Chọn nó khi có yêu cầu kiến trúc cụ thể, không phải để chữa mọi lỗi login.

## 5. IF_REQUIRED — tạo session theo nhu cầu

```java
http.sessionManagement(s -> s
        .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED));
```

Đây thường là lựa chọn phù hợp cho **web form login dùng HTTP session**. Spring Security có thể tạo session khi một cơ chế thực sự cần nó, chẳng hạn lưu `SecurityContext` của người đã đăng nhập hoặc lưu `SavedRequest` để quay lại tài nguyên trước login.

Ví dụ luồng được bảo vệ:

```text
GET /home                   -> public, có thể chưa cần session
GET /dashboard              -> anonymous, cần authentication
  ExceptionTranslationFilter
  RequestCache.saveRequest  -> có thể tạo session lưu URL gốc
  redirect /login
GET /login                  -> hiển thị login form + CSRF
POST /login                 -> kiểm tra username/password
  Authentication thành công
  SecurityContext được lưu theo repository
  redirect saved URL
GET /dashboard + cookie     -> có Authentication, kiểm tra quyền
```

**Điểm quan trọng:** `IF_REQUIRED` **không bảo đảm anonymous không có session**. `HttpSessionRequestCache` có thể cần lưu URL đã cố truy cập trước login. CSRF token/session-based CSRF repository có thể cần state. Khi muốn biết session xuất hiện vì lý do gì, hãy kiểm tra request cache, CSRF, login flow, context repository và các filter khác.

Với một GET công khai rất đơn giản, không sử dụng state nào, IF_REQUIRED thường **không cần tạo** session. Tuy nhiên kết luận này phụ thuộc cấu hình toàn ứng dụng chứ không chỉ enum.

## 6. NEVER — không tạo session để quản lý context, nhưng có thể dùng session sẵn có

```java
http.sessionManagement(s -> s
        .sessionCreationPolicy(SessionCreationPolicy.NEVER));
```

`NEVER` có ý nghĩa: Spring Security không tự tạo `HttpSession` cho mục đích quản lý `SecurityContext`, **nhưng nếu một session đã tồn tại, framework vẫn có thể sử dụng nó** theo cấu hình `SecurityContextRepository`.

Hai trường hợp:

```text
Request A: không có session, không có credentials
    -> NEVER không chủ động tạo session cho SecurityContext
    -> user vẫn anonymous

Request B: mang JSESSIONID hợp lệ
    -> HttpSession đã tồn tại
    -> nếu chứa SecurityContext hợp lệ, NEVER có thể đọc
    -> authorization có thể thấy Authentication từ session
```

Điều này phù hợp với một số hệ thống tích hợp session được tạo từ một phần khác của ứng dụng. Nhưng nó **không phải** lựa chọn chặt chẽ nếu API quy định chỉ được xác thực bằng token gửi trong từng request, kể cả khi browser đang đăng nhập vào website cùng origin.

### Vì sao có thể thấy session khi dùng NEVER?

Không nên suy luận `NEVER` vô hiệu hóa `HttpServletRequest.getSession(true)`. Một controller hoặc thư viện khác vẫn có thể tạo session. Ngoài ra, request cache, CSRF và authentication handlers có logic state riêng; khi cần kiểm soát nghiêm ngặt việc tạo session, hãy xét từng thành phần đó cùng với SecurityContextRepository.

**NEVER không có nghĩa “từ chối mọi session tồn tại”.** Đó mới là điểm phân biệt với STATELESS trong quản lý context.

## 7. STATELESS — không dùng HttpSession để lấy SecurityContext

```java
http.sessionManagement(s -> s
        .sessionCreationPolicy(SessionCreationPolicy.STATELESS));
```

Với `STATELESS`, Spring Security không tạo session để quản lý context và **không sử dụng HttpSession để lấy SecurityContext** của request. Thay vào đó, ứng dụng API có thể kiểm chứng `Authorization: Bearer ...` hoặc `Authorization: Basic ...` ở mỗi request.

```text
GET /api/orders + Authorization header
       |
       v
Authentication filter + provider/decoder
       |
       v
Authentication hợp lệ trong request hiện tại
       |
       v
SecurityContextHolder
       |
       v
AuthorizationFilter
       |
       v
Controller

GET /api/orders tiếp theo KHÔNG có Authorization
       |
       v
Không tự lấy Authentication từ web HttpSession
       |
       v
Thường 401 nếu endpoint cần authenticated()
```

Policy STATELESS không tự kiểm tra JWT. Ứng dụng Bearer token còn cần resource server, decoder/validator, trusted issuer/audience, thời hạn token và ánh xạ authorities phù hợp. HTTP Basic cần manager/provider để kiểm chứng username/password. **Chỉ đặt STATELESS không phải là authentication mechanism.**

### STATELESS không cấm Servlet tạo HttpSession

Mã ứng dụng vẫn có thể chủ động thực hiện:

```java
// Fragment minh họa, không phải khuyến nghị cho API production:
HttpSession session = request.getSession(true);
session.setAttribute("demo", "created-by-controller");
```

Ngay cả với `STATELESS`, lời gọi `getSession(true)` từ controller có thể tạo session, và một request sau mang cookie phù hợp có thể nhìn thấy session đó qua `request.getSession(false)`. **Tuy nhiên Spring Security vẫn không dùng nó để lấy SecurityContext** theo policy STATELESS.

Phải phân biệt:

1. **Có HttpSession trên Servlet container**: có thể do bất cứ thành phần ứng dụng nào tạo.
2. **Spring Security dùng HttpSession làm nguồn identity**: với STATELESS, câu trả lời là **không**.

Đây cũng là lý do không thể kết luận “ứng dụng hoàn toàn không có state” chỉ từ enum: database, rate limiting, cache, audit logs vẫn là state ở các tầng khác.

### Form login với STATELESS dễ tạo trải nghiệm đăng nhập lặp

Form login browser thường dựa vào session/context persistence. Khi cấu hình STATELESS mà không có cơ chế mang credentials/token sang request tiếp theo:

```text
POST /login -> password đúng, authentication thành công
     |
     v
redirect /dashboard
     |
     v
GET /dashboard (request mới)
     |
     v
Không lấy Authentication từ HttpSession
     |
     v
Bị yêu cầu login lại
```

Không sửa bằng `permitAll("/dashboard")` vì sẽ mở tài nguyên nhạy cảm. Hoặc chọn policy phù hợp với session web (thường IF_REQUIRED), hoặc thiết kế đăng nhập dựa trên token hoàn chỉnh cho từng request.

## 8. SecurityContextRepository ảnh hưởng hành vi thực tế

`SecurityContextHolder` giữ `SecurityContext` để code/filter trong request đọc `Authentication`. `SecurityContextRepository` có nhiệm vụ tải/lưu context qua vị trí lưu trữ mà implementation hỗ trợ.

| Repository | Mục đích tiêu biểu | Giới hạn |
| --- | --- | --- |
| `HttpSessionSecurityContextRepository` | Đọc/lưu SecurityContext trong HttpSession | Phải cân nhắc quyền tạo session và các điều kiện save |
| `RequestAttributeSecurityContextRepository` | Lưu context trong request attributes | Không phải một session login xuyên nhiều request |
| `NullSecurityContextRepository` | Không lưu/tải SecurityContext qua một kho state | Phù hợp khi mỗi request tự xác thực |
| `DelegatingSecurityContextRepository` | Phối hợp nhiều repositories | Hành vi phụ thuộc các delegate và cấu hình |

`SessionCreationPolicy` ảnh hưởng lựa chọn và cách sử dụng session trong security config, nhưng **không thể thay thế việc hiểu repository và authentication filter**. Trong Spring Security 6, `SecurityContextHolderFilter` đọc context qua repository; khi tự viết filter/login endpoint, chỉ gọi `SecurityContextHolder.getContext().setAuthentication(...)` thường **không đủ bảo đảm lưu context sang request sau**. Cần hiểu `saveContext(...)`, session authentication strategies, success/failure handlers và cơ chế repository đang dùng.

Nếu một API chạy STATELESS nhưng controller thấy `Authentication` trong request hiện tại, điều đó **không mâu thuẫn**: authentication được filter tạo cho chính request đó. Policy chỉ nói không lấy/lưu context bằng HttpSession để dùng như session login qua request sau.

Một số hướng dẫn cũ dựa vào `SessionManagementFilter` chạy trên mọi request. Trong cấu hình Spring Security 6 hiện đại, không nên giả định filter này luôn hiện diện như trước; các cơ chế authentication có thể chủ động gọi `SessionAuthenticationStrategy` khi thành công.

## 9. Ví dụ chạy được với Java 17 + Spring Boot 3 + HTTP Basic

Ta tạo một ứng dụng Spring MVC Servlet nhỏ để **đổi policy khi khởi động** và kiểm tra session, tránh thay code bốn lần. Ví dụ dùng `spring-boot-starter-web` và `spring-boot-starter-security`, Spring Boot **3.3.5** (phiên bản minh họa đã phát hành) cùng Java 17+.

Ba endpoints:

- `GET /session-state`: công khai, đọc `request.getSession(false)`, không tự tạo session.
- `GET /demo-create-session`: **chỉ dùng trong bài lab**, chủ động gọi `request.getSession(true)` để chứng minh code ứng dụng vẫn có thể tạo HttpSession; endpoint GET tạo state này không phù hợp đưa vào REST API production.
- `GET /private`: yêu cầu HTTP Basic; trả username và thông tin session đã tồn tại hay không.

Ứng dụng dùng `NullRequestCache` để không có saved request của form login làm nhiễu kết quả. **Đây là lựa chọn riêng của thí nghiệm**, không phải khuyến nghị tắt request cache ở website form login.

### 9.1. Cấu trúc thư mục

```text
session-policy-lab/
├── pom.xml
└── src/main/java/example/sessionlab/
    ├── SessionPolicyApplication.java
    ├── SecurityConfig.java
    └── SessionProbeController.java
```

### 9.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>session-policy-lab</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### 9.3. SessionPolicyApplication.java

```java
package example.sessionlab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SessionPolicyApplication {
    public static void main(String[] args) {
        SpringApplication.run(SessionPolicyApplication.class, args);
    }
}
```

### 9.4. SecurityConfig.java

```java
package example.sessionlab;

import java.util.Locale;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.savedrequest.NullRequestCache;

@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http,
                                            Environment env) throws Exception {

        String configured = env.getProperty(
                "demo.session-policy", "IF_REQUIRED");
        SessionCreationPolicy policy = SessionCreationPolicy.valueOf(
                configured.trim().toUpperCase(Locale.ROOT));

        http.sessionManagement(session -> session
                .sessionCreationPolicy(policy));

        // Demo HTTP Basic: tránh SavedRequest / form login request cache.
        http.requestCache(cache -> cache
                .requestCache(new NullRequestCache()));

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET,
                        "/session-state", "/demo-create-session").permitAll()
                .requestMatchers(HttpMethod.GET, "/private").authenticated()
                .anyRequest().denyAll()
        );
        http.httpBasic(basic -> basic.realmName("Session Policy Lab"));

        // Giữ CSRF mặc định. Demo dùng GET, không dùng POST state-changing.
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails student = User.withUsername("student")
                .password(encoder.encode("demo123"))
                .roles("USER")
                .build();
        return new InMemoryUserDetailsManager(student);
    }
}
```

`Environment.getProperty` giúp thử bốn policies bằng tham số `demo.session-policy`. Nếu truyền tên không thuộc enum (như `STATE_FULL`), ứng dụng sẽ không khởi động đúng và hiển thị lỗi cấu hình — không tự fallback im lặng.

`NullRequestCache` **không lưu URL gốc để redirect sau form login**, nhưng ví dụ này chỉ dùng Basic. `PasswordEncoder` và `UserDetailsService` cung cấp username/password đã hash cho Spring Security; `httpBasic` bật filter xác thực trên request. `anyRequest().denyAll()` chặn những route không được khai báo rõ.

### 9.5. SessionProbeController.java

```java
package example.sessionlab;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SessionProbeController {

    @GetMapping("/session-state")
    public String sessionState(HttpServletRequest request) {
        // Quan sát session nếu đã có; không tạo.
        HttpSession session = request.getSession(false);
        return "session=" + (session == null ? "absent" : "present");
    }

    @GetMapping("/demo-create-session")
    public String demoCreateSession(HttpServletRequest request) {
        // Chỉ để học: ứng dụng cố ý tạo session.
        // GET tạo state là antipattern với REST production.
        HttpSession session = request.getSession(true);
        session.setAttribute("demo.marker", "created-by-controller");
        return "application-session=created";
    }

    @GetMapping("/private")
    public String privatePage(Authentication auth, HttpServletRequest request) {
        HttpSession session = request.getSession(false);
        String present = session == null ? "absent" : "present";
        return "user=" + auth.getName() + ";session=" + present;
    }
}
```

`getSession(false)` khác `getSession(true)`: đối số `false` chỉ hỏi session đã tồn tại hay chưa; đối số `true` cho phép Servlet tạo session mới.

### 9.6. Chạy với bốn policy

Từ thư mục có `pom.xml`, cần Java 17+ và Maven:

```bash
mvn spring-boot:run
```

Mặc định là `IF_REQUIRED`. Để chọn policy khác, chạy **một** trong các lệnh:

```bash
mvn spring-boot:run -Dspring-boot.run.arguments="--demo.session-policy=ALWAYS"
mvn spring-boot:run -Dspring-boot.run.arguments="--demo.session-policy=IF_REQUIRED"
mvn spring-boot:run -Dspring-boot.run.arguments="--demo.session-policy=NEVER"
mvn spring-boot:run -Dspring-boot.run.arguments="--demo.session-policy=STATELESS"
```

**Dừng tiến trình trước rồi mới thử policy kế tiếp** để tránh trùng cổng `8080`. Các lệnh thể hiện cú pháp Maven/shell POSIX; PowerShell có thể cần điều chỉnh cách quote tham số.

### 9.7. Thử request công khai mới, không cookie

Với từng policy, dùng một request không mang cookie cũ:

```bash
curl -s http://localhost:8080/session-state
```

Kỳ vọng cho project demo này:

| Policy | Body kỳ vọng | Lý do |
| --- | --- | --- |
| ALWAYS | `session=present` | Security tạo session trước khi controller chạy |
| IF_REQUIRED | `session=absent` | Request GET công khai không cần session trong cấu hình demo |
| NEVER | `session=absent` | Không có existing session, security không tự tạo cho context |
| STATELESS | `session=absent` | Không có component nào trong request này tạo session |

Đây là **behavior dự kiến theo chính cấu hình demo**, không phải lời bảo đảm cho mọi ứng dụng dùng những policy tương ứng. Nếu thêm form login, request cache, CSRF token repository tùy chỉnh hoặc code tạo session, kết quả có thể khác.

Kiểm tra response headers:

```bash
curl -i http://localhost:8080/session-state
```

Với ALWAYS, một client chưa có cookie có thể nhận `Set-Cookie: JSESSIONID=...`. Không dựa vào một header `Set-Cookie` đơn lẻ để khẳng định hoặc phủ nhận sự tồn tại của session trong mọi cấu hình.

### 9.8. Cố ý tạo session bằng controller

Dùng `curl` lưu cookie jar:

```bash
curl -s -c policy-cookies.txt \
  http://localhost:8080/demo-create-session

curl -s -b policy-cookies.txt \
  http://localhost:8080/session-state
```

Kỳ vọng hai body theo thứ tự:

```text
application-session=created
session=present
```

Ngay cả với NEVER/STATELESS, nếu cookie trỏ đến `HttpSession` đang sống, controller vẫn thấy nó. **Điều này không có nghĩa STATELESS đã dùng session để xác thực**. Session được tạo có chủ đích bằng Servlet API.

Dùng cookie jar mới sau khi restart server vì session ID từ tiến trình cũ không còn hợp lệ. `/demo-create-session` là endpoint thí nghiệm; không giữ endpoint public tạo state qua GET trong sản phẩm thật.

### 9.9. Thử xác thực HTTP Basic

Không có credentials:

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  http://localhost:8080/private
```

Kỳ vọng `401` với Basic authentication challenge.

Gửi tài khoản demo đúng:

```bash
curl -s --user student:demo123 \
  http://localhost:8080/private
```

Body có dạng `user=student;session=absent` hoặc `user=student;session=present`, tùy policy và cơ chế filter/repository thực tế. `ALWAYS` dự kiến là present, còn `STATELESS` trên request mới không cookie và không có code khác tạo session thường là absent. **Đừng mặc định IF_REQUIRED luôn có một kết quả cho mọi authentication filter.**

Nếu đang chạy STATELESS, request `/private` kế tiếp **không gửi Authorization** thường vẫn trả `401`; nó không được coi là “đã đăng nhập” chỉ vì request trước vừa thành công. HTTP Basic client cần gửi credentials phù hợp theo từng request.

## 10. Trường hợp ứng dụng web form login

Thay HTTP Basic bằng form login trong **một SecurityFilterChain khác**, chính sách IF_REQUIRED thường hợp lý:

```java
// Fragment minh họa thay thế, không ghép vào demo Basic ở mục 9.
http.sessionManagement(s -> s
        .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED));
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/public", "/login").permitAll()
        .anyRequest().authenticated());
http.formLogin(Customizer.withDefaults());
```

Trong web form login, `HttpSessionRequestCache` có thể lưu URL của request bị chặn và tạo session **trước** khi user nhập password. Sau login thành công, `SecurityContext` có thể được lưu vào session để browser mang cookie tới request tiếp theo. Đây là ví dụ vì sao IF_REQUIRED không đồng nghĩa “anonymous không có session”.

### RequestCache và CSRF có ảnh hưởng độc lập

`RequestCache` có thể cần session để nhớ `SavedRequest` và quay lại URL cũ. `NullRequestCache` của demo sẽ không làm như thế. Nếu website yêu cầu trải nghiệm “đăng nhập xong quay về trang trước”, đừng copy cấu hình NullRequestCache từ API vào chain web.

CSRF có thể dùng `HttpSessionCsrfTokenRepository` hoặc `CookieCsrfTokenRepository`; cách lưu token và thời điểm cần token ảnh hưởng tới việc session/cookie xuất hiện. **Không tắt CSRF chỉ để không nhìn thấy session**: browser dùng cookie/credentials tự gửi cần chính sách CSRF đúng threat model.

### NEVER và form login

Với NEVER, nếu đã có session từ thành phần khác, security có thể dùng context đã có; nếu không, một login flow trông có vẻ thành công nhưng không lưu được context qua request mới theo repository đang dùng. Đừng xem NEVER là một cách tự động chuyển form login thành stateless login; cần test session/cookie/saveContext.

### STATELESS và form login

Nếu không có cơ chế mang token/credentials vào request sau, form login với STATELESS dễ dẫn đến login loop. Giải pháp là chọn IF_REQUIRED cho web UI hoặc thiết kế token authentication đầy đủ thay cho cơ chế phiên truyền thống.

## 11. API và browser cùng tồn tại: dùng nhiều SecurityFilterChain

Với website có browser login và API, nên tách ranh giới URL:

```java
// Fragment thiết kế: nằm trong class @Configuration với các imports
// @Bean, @Order, HttpSecurity, SecurityFilterChain, SessionCreationPolicy,
// NullRequestCache và Customizer. Không phải class runnable độc lập.

@Bean
@Order(1)
SecurityFilterChain api(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/**");
    http.sessionManagement(s -> s
            .sessionCreationPolicy(SessionCreationPolicy.STATELESS));
    http.requestCache(c -> c.requestCache(new NullRequestCache()));
    http.authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated());
    http.httpBasic(Customizer.withDefaults());
    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain web(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated());
    http.sessionManagement(s -> s
            .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED));
    http.formLogin(Customizer.withDefaults());
    return http.build();
}
```

Ở đây API chain cụ thể `/api/**` được xét trước; web chain fallback áp dụng cho những URL còn lại. **Một request chỉ được `FilterChainProxy` đưa vào chain match đầu tiên**, không chạy qua cả hai. `securityMatcher` chọn chain, trong khi `authorizeHttpRequests().requestMatchers` chọn rule bên trong chain.

**Lý do STATELESS ở API:** Browser có thể mang cookie của web login sang request `/api/**`. API phải không tự lấy SecurityContext từ session đó nếu hợp đồng API bắt buộc dùng Authorization header. Chính sách NEVER có thể dùng existing web session, nên **không tương đương** STATELESS cho ranh giới này.

Nếu dùng JWT thay HTTP Basic, cần resource server/decoder/validator phù hợp; chỉ đổi `httpBasic` thành `STATELESS` không đủ để bảo vệ Bearer token.

## 12. Những thứ SessionCreationPolicy không tự cấu hình

### Session timeout

Thời gian sống của HttpSession phụ thuộc Servlet container/app config (ví dụ Spring Boot Servlet property `server.servlet.session.timeout`), không do ALWAYS/IF_REQUIRED/NEVER/STATELESS đặt ra.

### Session fixation protection

Sau form login, ứng dụng stateful thường cần đổi session ID hoặc cơ chế bảo vệ session fixation. Spring Security có session authentication strategies cho nhu cầu này; SessionCreationPolicy **không thay thế** chúng. Kết quả đổi JSESSIONID sau login cũng không có nghĩa session authentication bị mất nếu cơ chế đúng.

### Concurrent-session control

Giới hạn số phiên mỗi tài khoản (ví dụ maximum sessions), session registry, expiring old sessions và chính sách concurrent login là tính năng khác. Đặt ALWAYS không tự kích hoạt giới hạn một phiên.

### Logout và token revocation

Logout của web session có thể invalidate session và xóa SecurityContext theo cấu hình. Với API Bearer/JWT stateless, việc thu hồi/expire token đòi thiết kế riêng; STATELESS **không** tự thu hồi access token. Với HTTP Basic, trình duyệt có thể cache credentials ở phía client, nên xóa session không luôn “logout” Basic.

### Cookie, CORS và CSRF

Các thuộc tính `Secure`, `HttpOnly`, `SameSite`, domain/path, HTTPS và CORS cần được thiết kế theo client. Stateless **không tự miễn CSRF**: browser có thể gửi cookie hoặc một số Basic credentials được cache tự động. Khi request thay đổi state, hãy kiểm tra threat model và CSRF token policy tương ứng, không tắt toàn cục theo tên enum.

### “Hoàn toàn không có state”

API dùng STATELESS vẫn có thể ghi database, audit, cache, rate-limit counters và idempotency records. Enum đặc biệt nói về **HttpSession phục vụ SecurityContext**, không áp đặt toàn bộ hệ thống phải không lưu state.

## 13. Khi nào chọn giá trị nào?

| Yêu cầu thực tế | Chính sách thường phù hợp | Vì sao |
| --- | --- | --- |
| Web form login, cookie session, redirect trở lại URL đã mở | **IF_REQUIRED** | Session được tạo khi authentication/request cache cần |
| Web legacy cần session cho mọi request | **ALWAYS** | Chủ động tạo session dù request công khai |
| Tận dụng session được thành phần khác tạo nhưng không tự tạo thêm cho context | **NEVER** | Dùng existing session khi có |
| API yêu cầu Basic/Bearer credentials mỗi request, không lấy identity từ web cookie session | **STATELESS** | Tách SecurityContext khỏi HttpSession |
| Cùng ứng dụng có web UI và REST API | **Hai chains, hai policy** | Mỗi nhóm có authentication/session/entry point riêng |
| Muốn web form login nhưng tuyệt đối không dùng session | **Xem lại authentication flow** | Phải thiết kế token/cơ chế mang danh tính qua request khác |

Policy phải được lựa chọn **cùng** với authentication mechanism, security context repository, request cache, CSRF, logout và yêu cầu vận hành. Không nên có một enum “mặc định cho mọi endpoint” nếu UI/API có hợp đồng xác thực khác nhau.

## 14. Lỗi thường gặp và cách debug

| Biểu hiện | Điều cần kiểm tra | Cách giải quyết |
| --- | --- | --- |
| STATELESS nhưng vẫn có JSESSIONID | Controller/thư viện khác có gọi getSession(true), cookie cũ | Xác định nơi tạo, không tự kết luận security dùng nó |
| NEVER nhưng vẫn lấy identity từ session | Đây có thể đúng thiết kế NEVER | Nếu không muốn session auth, chọn STATELESS cho API |
| IF_REQUIRED nhưng anonymous có session | SavedRequest, CSRF, app component cần state | Kiểm tra request cache và token retrieval |
| ALWAYS gây tải cao cho session store | Mọi public request tạo session | Chọn IF_REQUIRED nếu không yêu cầu eager session |
| Form login đúng mật khẩu rồi redirect lại login | STATELESS, context không save/load, cookie hỏng | Xem policy/repository/cookie/session strategy |
| API thiếu Authorization nhưng vẫn truy cập được | Session web bị dùng hoặc request vào sai chain | Tách securityMatcher và STATELESS API chain |
| JWT trả 401 dù STATELESS đã bật | Chưa có decoder/provider hoặc token không hợp lệ | Cấu hình Resource Server đúng |
| Gặp 403 sau login | Thiếu role/authority hoặc CSRF | Kiểm tra authorization, không sửa policy tùy tiện |
| Login thành công nhưng request sau anonymous | SecurityContextRepository chưa lưu, session invalid/không có cookie | Test load/save context, các filter và success handler |
| NullRequestCache làm mất redirect URL cũ | Không lưu SavedRequest | Giữ request cache trong web flow cần redirect |
| Different chains cho các URL có policy khác | Order/matcher làm request đi nhầm chain | Debug FilterChainProxy, @Order và securityMatcher |
| Cookie sai SameSite/domain/path | Browser không gửi cookie khi cần | Kiểm tra HTTPS, proxy và cookie attributes |

**Quy trình kiểm tra có hệ thống:**

1. Xác định URL/method/cookie/Authorization thực tế, tránh log secrets.
2. Xác định **SecurityFilterChain** được chọn và SessionCreationPolicy của nó.
3. Xác định session đã có khi bắt đầu request hay mới được tạo: xem các nơi gọi `getSession(true)`.
4. Xác định `SecurityContextRepository`, login filter, request cache, CSRF repository.
5. Kiểm tra authentication được lấy từ header/token hay session.
6. Kiểm tra **authorization** độc lập với authentication, phân biệt 401/403.
7. Test lại browser có cookie và REST client không cookie để chứng minh ranh giới bảo mật đúng.

Trong môi trường development có thể bật:

```properties
logging.level.org.springframework.security=DEBUG
```

Không in session ID, password, Bearer token, Authorization header hoặc dữ liệu nhạy cảm vào log.

## 15. Câu hỏi tự kiểm tra

1. **ALWAYS có làm người dùng tự authenticated không?** Không, session rỗng không phải identity đã kiểm chứng.
2. **IF_REQUIRED có bảo đảm request anonymous không bao giờ có session?** Không, request cache/CSRF hoặc code khác có thể cần session.
3. **NEVER và STATELESS khác nhau ở đâu?** NEVER có thể dùng existing session cho SecurityContext; STATELESS không.
4. **Controller có thể tạo HttpSession khi STATELESS không?** Có, `getSession(true)` vẫn là Servlet API hợp lệ.
5. **Vì sao STATELESS + formLogin mặc định có thể gây login loop?** Request sau không được xác thực từ session; không có credential thay thế.
6. **STATELESS có tự kiểm tra JWT không?** Không, cần bộ lọc/provider/decoder Resource Server phù hợp.
7. **SecurityContextHolder của request STATELESS có thể có Authentication?** Có, authentication được tạo trong request hiện tại, không nhờ session.
8. **JSESSIONID xuất hiện có chứng minh Spring Security đã tạo?** Không.
9. **Chính sách nào phù hợp API không được dùng cookie web như một dạng login?** STATELESS ở riêng API chain.
10. **SessionCreationPolicy nào tự điều chỉnh session timeout/MFA/concurrent login?** Không có giá trị nào.
11. **Vì sao GET public với ALWAYS có session?** Policy yêu cầu eager session creation.
12. **Để test sự khác nhau, gọi getSession(false) hay true?** `false` để quan sát; `true` chủ động tạo và làm sai phép đo ban đầu nếu không có chủ đích.

## 16. Checklist triển khai

- [ ] Chọn policy dựa vào cơ chế xác thực và nhu cầu duy trì SecurityContext qua các request.
- [ ] Nếu web dùng form login, xác minh session cookie, request cache, login success, CSRF và security context persistence.
- [ ] Nếu API yêu cầu xác thực qua Bearer/Basic từng request, cấu hình STATELESS riêng và test request chỉ có cookie web.
- [ ] Không nhầm NEVER với STATELESS; nhớ NEVER có thể sử dụng session đang có.
- [ ] Không dùng JSESSIONID/Set-Cookie làm bằng chứng duy nhất về nguồn session/authentication.
- [ ] Kiểm tra các thành phần có thể tạo HttpSession, nhất là controller, request cache và CSRF repository.
- [ ] Với Spring Security 6, hiểu explicit security context save và cơ chế session authentication strategies nếu tự viết login.
- [ ] Test behavior theo từng HTTP request thay vì chỉ xem enum trong source.
- [ ] Cấu hình riêng timeout, fixation protection, concurrent sessions, logout và cookie security.
- [ ] Kiểm tra CSRF và CORS dựa trên cách client gửi credentials, không tắt theo tên policy.
- [ ] Không đưa `/demo-create-session` vào hệ thống production, vì nó cố ý tạo state từ GET.
- [ ] Sau khi đổi policy, test cả anonymous, authenticated, request tiếp theo, role-denied và session hết hạn.

**Kết luận:** `ALWAYS` luôn tạo HttpSession; `IF_REQUIRED` tạo khi cần; `NEVER` không chủ động tạo để quản lý SecurityContext nhưng **có thể dùng session sẵn có**; `STATELESS` **không sử dụng session để tải SecurityContext**, phù hợp cho API xác thực độc lập từng request. Hiểu ranh giới này giúp tránh login loop, session tạo ngoài ý muốn và đặc biệt tránh việc REST API vô tình tin cookie đăng nhập của web UI.