# HTTP Basic: HTTPS, cách trình duyệt lưu thông tin đăng nhập và giới hạn đăng xuất

**Module:** Spring Security – Servlet  
**Nhóm:** HTTP Basic  
**Ví dụ:** Java 17, Spring Boot 3.3.5, Spring Security 6.x, Spring MVC và Tomcat.

## Mục tiêu

Sau bài học, bạn có thể giải thích vì sao HTTP Basic **bắt buộc phải đi qua HTTPS**, cách browser có thể ghi nhớ và gửi lại username/password, tại sao không có logout Basic đáng tin cậy giữa các trình duyệt, và cách kiểm thử một API Spring Security Servlet có HTTP Basic. Bài phân biệt rõ **HTTP authentication cache**, **password manager**, **session cookie** và **SecurityContext**. Ví dụ dùng credentials giả, không phục vụ production.

## 1. Cơ chế của HTTP Basic

HTTP Basic dùng `Authorization` request header. Với username `student`, password `learn-pass`, phần dữ liệu là Base64 của chuỗi `student:learn-pass`:

```http
GET /api/me HTTP/1.1
Host: localhost:8080
Authorization: Basic c3R1ZGVudDpsZWFybi1wYXNz
```

Có thể giải mã Base64 để lấy nguyên username/password; **Base64 là encoding, không phải encryption hay hashing**. Nếu header lộ, attacker có thể khôi phục thông tin xác thực và gửi lại yêu cầu. Không giải thích nhầm rằng dấu `Basic` hoặc Base64 cung cấp confidentiality.

Luồng challenge-response phổ biến:

```mermaid
sequenceDiagram
    participant C as Browser hoặc HTTP client
    participant S as Spring Security Servlet
    participant P as AuthenticationProvider
    C->>S: GET /api/me (chưa có Authorization)
    S-->>C: 401 + WWW-Authenticate: Basic realm="Learning API"
    Note over C: Browser có thể hiện hộp thoại username/password
    C->>S: GET /api/me + Authorization: Basic ...
    S->>P: Kiểm tra username/password
    P-->>S: Authentication thành công hoặc lỗi
    S-->>C: 200 JSON hoặc 401 challenge
```

**Không phải client nào cũng đợi challenge.** `curl -u` và một số HTTP libraries có thể gửi Basic header ngay ở request đầu. Browser sau khi đã xác thực cũng có thể chủ động gửi lại header cho các URL thuộc phạm vi bảo vệ.

| Thành phần | Ý nghĩa | Cần nhớ |
| --- | --- | --- |
| `Authorization: Basic <base64>` | Client gửi username/password theo HTTP Basic | Có thể giải mã; mỗi lần gửi đều chứa credential có thể tái sử dụng |
| `401 Unauthorized` | Yêu cầu xác thực chưa được đáp ứng | Status tên *Unauthorized*, nhưng thường là authentication challenge |
| `WWW-Authenticate: Basic realm="Learning API"` | Server quảng bá Basic scheme và realm | Realm là nhãn protection space, **không phải** session, role, token |
| `403 Forbidden` | Người gọi không được phép thực hiện thao tác | Có thể do authorization hoặc CSRF; không nhất thiết mật khẩu sai |
| `200 OK` | Request được xử lý thành công | Không chứng minh browser đang có session cookie |

`BasicAuthenticationFilter` trong Spring Security đọc header Basic, tạo authentication request, gọi `AuthenticationManager` và sử dụng kết quả. `AuthenticationEntryPoint` có thể tạo challenge `401` khi cần. Đây là luồng **Servlet filter**, không phải `@PostMapping` đăng nhập trong MVC.

## 2. HTTPS quan trọng hơn Base64

### 2.1. Điều xảy ra với HTTP thuần

Với `http://`, header `Authorization` có thể bị đọc hoặc chỉnh sửa bởi người ở vị trí giám sát/kiểm soát đường truyền. Vì Base64 giải mã được, attacker thấy `username:password`; người dùng có thể bị chiếm tài khoản khi password được dùng lại. Server có dùng `BCryptPasswordEncoder` để lưu hash cũng không giải quyết được raw password **đang truyền qua mạng**.

**Kết luận:** HTTP Basic chỉ nên dùng trên **HTTPS có xác thực chứng chỉ server đúng** khi có credentials thật.

HTTPS/TLS giúp bảo vệ bí mật và toàn vẹn từ client tới **điểm TLS kết thúc**. Nó không tự bảo vệ các hệ thống phía sau, dữ liệu trong log, heap dump, secrets ở trình duyệt hay credential stuffing.

```text
Browser -- HTTPS/TLS --> Reverse proxy -- đường backend --> Spring Boot
```

Nếu TLS terminate ở proxy, phải xác định đường proxy→backend có được bảo vệ đủ theo threat model không. Với dữ liệu nhạy cảm, cân nhắc TLS/mTLS nội bộ, mạng hạn chế truy cập, secret redaction ở proxy/APM, cấu hình certificate chain và kiểm tra server name.

### 2.2. Đừng gửi Basic qua HTTP rồi mới chuyển hướng

Một cách làm sai là mong ứng dụng nhận request `http://` mang `Authorization` rồi trả `301/302` sang `https://`. Khi browser nhận redirect, header đã đi qua đoạn **không có TLS**; bí mật có thể đã lộ.

Client phải bắt đầu kết nối **trực tiếp qua `https://`** và xác minh certificate. Server/edge có thể redirect các request HTTP thông thường sang HTTPS, nhưng redirect đó không khôi phục confidentiality cho credentials đã gửi trước. HSTS có thể khiến browser ưu tiên HTTPS **sau khi chính sách hợp lệ được ghi nhận hoặc preload**, không xóa hậu quả của một lần gửi credential qua HTTP trước đó.

### 2.3. Những chỗ HTTPS không bảo vệ

- Application hoặc reverse proxy ghi `Authorization`, raw HTTP headers hoặc password vào access log.
- Hệ thống tracing/APM ghi credential trong span attributes, exception messages hoặc body capture.
- TLS termination ở edge nhưng backend hop không được bảo vệ.
- Client tắt certificate verification bằng `curl -k`/`--insecure` hoặc browser bỏ qua lỗi certificate.
- Credential có mặt trong shell history, command-line process listing, script deploy, URL query string hoặc repository.
- Mật khẩu dùng lại ở nhiều dịch vụ hoặc bị đoán qua brute force.

Thiết kế phải gồm **HTTPS + password hashing phía server + kiểm soát logs/traces + rate limiting**; một lớp không thay thế các lớp khác.

## 3. Browser lưu thông tin HTTP Basic như thế nào?

### 3.1. Hộp thoại Basic do browser quản lý

Khi một trang trả `401` và `WWW-Authenticate: Basic ...`, browser có thể hiện **hộp thoại đăng nhập native**. Người dùng nhập username/password; browser gửi lại request có Basic header. Khi truy cập các URL liên quan, browser có thể **tự động gửi lại credentials đã có** mà không hỏi người dùng thêm lần nữa.

Hành vi giữ credentials phụ thuộc browser, phiên, realm, origin, cách truy cập và cài đặt. **Đóng tab không bảo đảm quên thông tin xác thực**. Một số browser giữ tới khi đóng phiên/chương trình, một số có cơ chế khác; không nên hứa thời gian hoặc điều kiện cụ thể cho mọi browser.

Tương tự, việc browser hiện popup lần nữa khi nhận `401` không phải bằng chứng cache cũ đã được xóa hoàn toàn. Browser có thể dùng credential đã nhớ, hỏi lại, hoặc chọn credential khác; ứng dụng không nên dựa vào popup làm ranh giới phiên bảo mật.

### 3.2. Protection space và `realm`

Header ví dụ:

```http
WWW-Authenticate: Basic realm="Learning API"
```

`realm` giúp client nhận biết vùng yêu cầu xác thực. Phạm vi áp dụng credential HTTP Basic còn liên quan **scheme/host/port và phạm vi đường dẫn** theo quy tắc giao thức và triển khai client. Browser có thể gửi lại credentials cho các URL cùng vùng được bảo vệ.

Đừng coi việc tạo hai path `/api/a` và `/api/b` là cách buộc browser hỏi password hai lần; cũng không coi realm là quyền truy cập. **Authorization vẫn do server kiểm tra từng endpoint**. Đổi realm có thể gây prompt khác, nhưng không phải cách thu hồi password hay logout được chuẩn bảo đảm.

### 3.3. Bốn kiểu lưu trạng thái khác nhau

| Nơi/cơ chế | Thứ được giữ | Ai điều khiển | Liên quan logout thế nào? |
| --- | --- | --- | --- |
| HTTP auth cache của browser | Thông tin HTTP Basic đã dùng | Browser/HTTP stack | Không có web API logout Basic chuẩn để server buộc quên |
| Password manager | Mật khẩu được người dùng lưu, có thể đồng bộ | Người dùng/password manager | Xóa mục đã lưu không nhất thiết xóa auth cache hiện tại |
| Cookie như `JSESSIONID` | Session identifier | Browser giữ, server quản lý session | Server có thể invalidate session và gửi cookie expiry |
| Spring Security `SecurityContext` | `Authentication` cho request, có thể qua repository/session | Spring Security theo cấu hình | Xóa context/session không buộc browser xóa Basic credentials |

**Rất dễ nhầm:** Browser có thể tiếp tục tự gửi `Authorization` **dù không có `JSESSIONID`**, vì HTTP Basic không đòi hỏi session cookie. Ngược lại, việc password manager đề nghị lưu mật khẩu là một tính năng riêng, không đồng nghĩa mọi browser dùng HTTP Basic đều lưu vĩnh viễn.

Không cố đọc hay xóa auth cache của browser bằng JavaScript trên trang web: trình duyệt không cung cấp một API web phổ quát bảo đảm tác vụ đó. Không thiết kế logout dựa vào “đóng tab”, `window.location`, xóa localStorage hoặc xóa cookie khi cơ chế xác thực là Basic.

## 4. Giới hạn logout: vì sao xóa session vẫn có thể vào lại?

### 4.1. HTTP Basic xác thực lại theo request

Một client đã có username/password Basic có thể gửi lại **mỗi request**:

```text
Request 1: Authorization: Basic ... -> server xác thực -> 200
Request 2: Authorization: Basic ... -> server xác thực -> 200
Request 3: Authorization: Basic ... -> server xác thực -> 200
```

Spring Security có thể giữ `Authentication` trong `SecurityContext` của request. Nếu có session, logout handler có thể xóa session và context. Nhưng khi request sau vẫn có `Authorization: Basic ...` hợp lệ, **`BasicAuthenticationFilter` có thể xác thực lại ngay**, nên người dùng trông như chưa đăng xuất.

Đây không phải bug của `HttpSession.invalidate()`; HTTP Basic **không định nghĩa một thao tác logout chuẩn** buộc browser quên username/password. Trong thiết kế browser app, đây là giới hạn UX và bảo mật quan trọng.

### 4.2. Những “mẹo” không tạo logout chắc chắn

| Thử nghiệm | Vì sao không đáng tin làm logout |
| --- | --- |
| Trả `401` khi bấm Logout | Có thể xuất hiện challenge/prompt, nhưng không đảm bảo browser quên credentials |
| Gửi header Basic sai để “thay” password | Tùy browser; có thể chỉ làm request thất bại hoặc xuất hiện prompt |
| Đổi `realm` | Có thể tạo một protection space khác, credentials cũ không nhất thiết bị xóa |
| Xóa cookie `JSESSIONID` | HTTP Basic không cần session cookie để gửi credentials |
| Xóa localStorage/sessionStorage | Không quản lý browser HTTP authentication cache |
| `Clear-Site-Data: "cache", "cookies", "storage"` | Tác động một số site data được hỗ trợ; **không bảo đảm** quét hết HTTP Basic auth cache |
| Đóng tab/refresh trang/JavaScript redirect | Không có đảm bảo về thời điểm browser quên Basic credentials |

Đừng xây một nút Logout tuyên bố “đã đăng xuất hoàn toàn” khi vẫn chấp nhận password cũ trên cùng browser và browser còn tự gửi lại Basic header.

### 4.3. Làm gì để thu hồi quyền truy cập thật sự?

Có hai mục tiêu khác nhau:

- **Chặn mọi client sử dụng password cũ:** vô hiệu hóa tài khoản, đổi/thu hồi password ở backend hoặc cập nhật chính sách quyền. Nếu mọi request kiểm tra lại nguồn credential hiện hành thì client gửi lại password cũ sẽ nhận `401`/lỗi phù hợp.
- **Chỉ kết thúc một phiên/thiết bị:** HTTP Basic không có session identifier độc lập với password. Hãy dùng form login + session có khả năng invalidate, hoặc token/OIDC có vòng đời và revocation/rotation được thiết kế đúng.

Thay password **không tự xóa mật khẩu từng lưu trong browser**; browser có thể tiếp tục gửi password đã hết hiệu lực và bị từ chối. Nếu hệ thống có authentication cache, token, session hoặc cơ chế SSO khác, cần đánh giá thu hồi cho **tất cả** con đường đó thay vì giả định chỉ thay password là đủ ngay.

### 4.4. Khi nào nên dùng HTTP Basic?

HTTP Basic đơn giản, phổ biến với script nội bộ và CLI **qua TLS**, khi mỗi request tự đưa credentials và không đòi UX logout theo thiết bị. Với browser app cần nút Logout, timeouts, remember-me, SSO hoặc nhiều phiên độc lập, **form login/session hoặc OAuth2/OIDC/token** thường phù hợp hơn.

Dù dùng session hay token, logout phải có định nghĩa cụ thể: một session, mọi thiết bị, refresh token, access token hay phiên tại identity provider. Không có cơ chế nào làm mọi loại token biến mất chỉ bằng một redirect.

## 5. Cấu hình HTTP Basic trong Spring Security Servlet

Các thành phần:

```mermaid
flowchart TD
    A["GET /api/me"] --> B["FilterChainProxy chọn SecurityFilterChain"]
    B --> C["BasicAuthenticationFilter kiểm tra Authorization"]
    C --> D{"Credentials có và hợp lệ?"}
    D -- "Có" --> E["AuthenticationManager → Provider"]
    E --> F["SecurityContext cho request"]
    F --> G["Authorization rồi controller"]
    D -- "Không" --> H["AuthenticationEntryPoint"]
    H --> I["401 + WWW-Authenticate: Basic ..."]
```

`FilterChainProxy` chọn security chain đầu tiên khớp request. `BasicAuthenticationFilter` làm việc **trong chain đã chọn**, vì vậy nếu nhiều chain có `securityMatcher` khác nhau, phải bảo đảm `/api/**` vào chain có `httpBasic`.

HTTP Basic là cơ chế xác thực **có thể dùng không cần server session**, nhưng `httpBasic()` một mình **không chứng minh** cả ứng dụng không có `HttpSession`: controller, MVC, CSRF hoặc các thư viện khác vẫn có thể tạo session vì mục đích riêng.

Khi muốn mỗi API request cung cấp header riêng, một cấu hình thường dùng:

```java
http.sessionManagement(session -> session
        .sessionCreationPolicy(SessionCreationPolicy.STATELESS));
```

`STATELESS` hướng Spring Security không dùng `HttpSession` để lưu/khôi phục `SecurityContext` qua những request sau; **không** làm browser quên header, **không** tắt password manager và **không** thay thế TLS.

### 5.1. Cảnh báo CSRF khi browser tự gửi credentials

**Không kết luận CSRF vô hại chỉ vì API dùng Basic hoặc được gọi là stateless.** Browser có thể tự gửi credentials Basic đã lưu kèm một số request. Với endpoint thay đổi trạng thái, cần đánh giá CSRF dựa trên khả năng credentials được gửi tự động, hành vi browser và client thực tế.

`CsrfFilter` của Spring Security bảo vệ các request không an toàn khi CSRF được bật. `GET` nên không gây thay đổi trạng thái. Không đánh đồng CORS với CSRF: CORS chủ yếu giới hạn cách cross-origin JavaScript đọc/sử dụng response, không là bằng chứng mọi cross-site state-changing request đều vô hại.

Bài demo dưới đây **chỉ có GET** và giữ cấu hình CSRF mặc định; nếu thêm `POST/PUT/DELETE`, phải đánh giá và test chính sách CSRF phù hợp. Không đưa một câu lệnh `.csrf(csrf -> csrf.disable())` thành lời khuyên mặc định cho mọi API dùng Basic.

## 6. Project Spring Boot chạy được

Ví dụ có `/public/ping` công khai, `/api/me` cần Basic và `/api/admin` cần role `ADMIN`. Tài khoản demo `student`/`learn-pass` có `ROLE_USER`, password được mã hóa một chiều bằng BCrypt trong memory user store; kết quả chỉ trả username, không trả password/hash.

### 6.1. Cây thư mục

```text
http-basic-demo/
├── pom.xml
└── src/
    ├── main/java/demo/basic/
    │   ├── BasicApplication.java
    │   ├── SecurityConfig.java
    │   └── ApiController.java
    └── test/java/demo/basic/
        └── BasicApplicationTests.java
```

Dùng JDK 17+, Maven 3.6.3+ và kết nối dependency repository khi build lần đầu.

### 6.2. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>http-basic-demo</artifactId>
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

`spring-boot-starter-web` dùng Spring MVC/Servlet (embedded Tomcat mặc định), khác WebFlux. Spring Boot BOM quản lý phiên bản Spring Security và dependencies liên quan.

### 6.3. `src/main/java/demo/basic/BasicApplication.java`

```java
package demo.basic;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BasicApplication {
    public static void main(String[] args) {
        SpringApplication.run(BasicApplication.class, args);
    }
}
```

### 6.4. `src/main/java/demo/basic/SecurityConfig.java`

```java
package demo.basic;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
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
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public/ping").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/admin")
                    .hasRole("ADMIN")
                .anyRequest().authenticated());

        http.httpBasic(basic -> basic.realmName("Learning API"));

        http.sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS));

        // Chỉ demo GET; không tắt CSRF bằng mặc định.
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails student = User.withUsername("student")
                .password(encoder.encode("learn-pass"))
                .roles("USER")
                .build();
        return new InMemoryUserDetailsManager(student);
    }
}
```

`httpBasic(...)` cài Basic authentication cho security chain và đặt realm. `hasRole("ADMIN")` đòi authority `ROLE_ADMIN`; tài khoản `student` chỉ có `ROLE_USER`, nên không được truy cập `/api/admin`. Vì có `UserDetailsService` bean, ứng dụng không cần generated user mặc định của Boot.

Đây là cấu hình demo **không có form login và không có logout endpoint**: không tạo cảm giác rằng `/logout` sẽ xóa HTTP Basic credentials trong browser. Trong hệ thống thật, lưu người dùng trong database/identity provider, dùng password hashing và hạn chế brute-force.

### 6.5. `src/main/java/demo/basic/ApiController.java`

```java
package demo.basic;

import org.springframework.http.MediaType;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {
    @GetMapping(value = "/public/ping",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public String ping() {
        return "pong";
    }

    @GetMapping("/api/me")
    public MeResponse me(Authentication authentication) {
        return new MeResponse(authentication.getName());
    }

    @GetMapping("/api/admin")
    public String admin() {
        return "admin-only";
    }

    public record MeResponse(String username) {}
}
```

Chỉ trả `MeResponse` gồm username, **không trả** raw `Authentication`, `Authorization` header hay encoded password hash.

## 7. Chạy project và xem status đúng

Trên localhost có thể chạy HTTP để quan sát cơ chế trong môi trường học tập **không có credentials thật**:

```bash
mvn clean test
mvn spring-boot:run
```

Ở terminal khác (Windows PowerShell có thể cần `curl.exe`):

```bash
# GET public
curl -s http://localhost:8080/public/ping

# Không cung cấp Basic credentials
curl -s -o /dev/null -w '%{http_code}\n' \
  http://localhost:8080/api/me

# Credentials giả hợp lệ
curl -s -u student:learn-pass \
  http://localhost:8080/api/me

# Password sai
curl -s -o /dev/null -w '%{http_code}\n' \
  -u student:wrong http://localhost:8080/api/me

# Đúng password nhưng thiếu ROLE_ADMIN
curl -s -o /dev/null -w '%{http_code}\n' \
  -u student:learn-pass http://localhost:8080/api/admin
```

Output từ **năm lệnh riêng**:

```text
pong
401
{"username":"student"}
401
403
```

Các body `pong` và JSON thường không có newline ở cuối; lệnh `-w` thêm newline khi in HTTP status. Nếu cần kiểm tra challenge, dùng:

```bash
curl -i http://localhost:8080/api/me
```

Các phần quan trọng trong response:

```http
HTTP/1.1 401
WWW-Authenticate: Basic realm="Learning API"
```

Headers khác có thể thay đổi. `Authorization` là **request** header của client; `WWW-Authenticate` là **response** header của server. Không gửi password thật trong `curl -u user:password` command có thể lưu trong history/process logs; chỉ dùng credential giả của demo.

### 7.1. Chứng minh Base64 có thể giải ngược bằng Java 17

File độc lập `BasicHeaderDemo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.util.Base64;

public class BasicHeaderDemo {
    public static void main(String[] args) {
        String credentials = "student:learn-pass";
        String value = Base64.getEncoder().encodeToString(
                credentials.getBytes(StandardCharsets.UTF_8));

        String decoded = new String(Base64.getDecoder().decode(value),
                StandardCharsets.UTF_8);
        System.out.println(value);
        System.out.println(decoded);
    }
}
```

Chạy:

```bash
javac BasicHeaderDemo.java
java BasicHeaderDemo
```

Stdout chính xác:

```text
c3R1ZGVudDpsZWFybi1wYXNz
student:learn-pass
```

Đây là phép thử encoding với **dữ liệu giả**; không in `Authorization` header hoặc Base64 credentials trong production logs.

## 8. Thiết lập HTTPS self-signed cho localhost

Trong môi trường phát triển, có thể dùng TLS self-signed để học trao đổi Basic qua HTTPS. **Đây không phải cấu hình chứng chỉ production**. Ứng dụng thật cần certificate chain được tin cậy, quản lý private key và cấu hình reverse proxy/edge chính xác.

### 8.1. Tạo keystore PKCS#12

Đảm bảo thư mục `src/main/resources` tồn tại, rồi chạy JDK `keytool`:

```bash
keytool -genkeypair \
  -alias localhost \
  -keyalg RSA -keysize 3072 \
  -validity 365 -storetype PKCS12 \
  -keystore src/main/resources/dev-keystore.p12 \
  -storepass changeit -keypass changeit \
  -dname "CN=localhost, OU=Dev, O=Demo, L=HCM, ST=HCM, C=VN" \
  -ext "SAN=dns:localhost,ip:127.0.0.1"
```

Các dấu `\` biểu thị xuống dòng trong shell POSIX; với Windows PowerShell dùng một dòng lệnh hoặc cú pháp riêng. Mật khẩu `changeit` **chỉ cho demo**. Không commit keystore/private key/password vào repository thật.

Thêm file `src/main/resources/application.properties`:

```properties
server.port=8443
server.ssl.enabled=true
server.ssl.key-store=classpath:dev-keystore.p12
server.ssl.key-store-type=PKCS12
server.ssl.key-store-password=${TLS_KEYSTORE_PASSWORD}
server.ssl.key-alias=localhost
```

Cấp mật khẩu qua biến môi trường lúc chạy:

```bash
export TLS_KEYSTORE_PASSWORD=changeit
mvn spring-boot:run
```

Trong PowerShell, đặt `$env:TLS_KEYSTORE_PASSWORD = "changeit"` trước khi chạy Maven.

### 8.2. Dùng `curl --cacert` thay vì bỏ qua TLS validation

Xuất public certificate sang PEM:

```bash
keytool -exportcert \
  -alias localhost -storetype PKCS12 \
  -keystore src/main/resources/dev-keystore.p12 \
  -storepass changeit -rfc -file local-cert.pem
```

Thử HTTPS tới hostname `localhost` trùng SAN:

```bash
curl --cacert local-cert.pem \
  -u student:learn-pass https://localhost:8443/api/me
```

Body được dự kiến:

```json
{"username":"student"}
```

`--cacert` dùng chứng chỉ test làm trust anchor cho yêu cầu này, **không tắt xác thực server**. Tránh `curl -k`/`--insecure` vì chúng vô hiệu hóa kiểm tra chứng chỉ và không chứng minh password được gửi đúng máy chủ. Browser có thể cảnh báo với self-signed certificate; không hướng người dùng bỏ qua cảnh báo trong môi trường thật.

## 9. Kiểm thử Servlet filter chain bằng MockMvc

File `src/test/java/demo/basic/BasicApplicationTests.java`:

```java
package demo.basic;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BasicApplicationTests {
    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointDoesNotNeedCredentials() throws Exception {
        mvc.perform(get("/public/ping"))
                .andExpect(status().isOk())
                .andExpect(content().string("pong"));
    }

    @Test
    void privateEndpointIssuesBasicChallenge() throws Exception {
        mvc.perform(get("/api/me")
                .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isUnauthorized())
                .andExpect(header().string("WWW-Authenticate",
                        containsString("Basic realm=\"Learning API\"")));
    }

    @Test
    void validCredentialsAreAccepted() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("student", "learn-pass")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value("student"))
                .andExpect(jsonPath("$.password").doesNotExist());
    }

    @Test
    void incorrectPasswordIsRejected() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("student", "wrong")))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void nextIndependentRequestWithoutHeaderIsUnauthenticated()
            throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("student", "learn-pass")))
                .andExpect(status().isOk());

        mvc.perform(get("/api/me"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticatedUserWithoutAdminRoleIsForbidden()
            throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("student", "learn-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void adminEndpointWithoutCredentialsChallenges() throws Exception {
        mvc.perform(get("/api/admin")
                .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isUnauthorized())
                .andExpect(header().string("WWW-Authenticate",
                        containsString("Basic")));
    }
}
```

`mvn test` dự kiến chạy **bảy bài kiểm thử** và pass với source/config ở trên. `httpBasic(...)` trong test là helper của `spring-security-test`, không phải thao tác trên browser thật.

**Giới hạn chứng cứ:** MockMvc không kiểm tra TLS handshake, certificate validation, HSTS hoặc cache HTTP Basic của browser. Test có hai request độc lập chỉ chứng minh **không có header thì request MockMvc sau không tự thành công** trong cấu hình này; không thể suy ra browser thật sẽ quên password sau khi đóng tab. Phải dùng test với browser/client thực tế và môi trường triển khai cho các yêu cầu đó.

## 10. Tình huống lỗi phổ biến

### Lỗi A: Nghĩ Base64 là mã hóa an toàn

Một `Authorization` header có thể được giải mã dễ dàng. **Sửa:** HTTPS với xác thực chứng chỉ, không log secrets, lưu password hash tại server.

### Lỗi B: Ứng dụng có `STATELESS` nhưng browser vẫn “tự đăng nhập”

Browser có thể tự gửi lại Basic credentials. `STATELESS` chỉ định cơ chế lưu `SecurityContext` của Spring Security, không xóa cache credentials trên client. Kiểm tra network request bằng dữ liệu demo và phân biệt `Authorization` với cookie.

### Lỗi C: Logout xóa session mà refresh vẫn vào được

Browser vẫn gửi password hợp lệ qua Basic header. Xóa session chỉ xóa state tương ứng; không buộc client quên Basic credentials. Nếu cần thu hồi theo thiết bị, chuyển sang session/token riêng có vòng đời rõ.

### Lỗi D: Đổi realm rồi nghĩ người dùng đã bị đăng xuất

Realm mới có thể thay đổi prompt/cache mapping nhưng không làm password cũ hết hiệu lực trên server. Đừng dùng làm ranh giới bảo mật.

### Lỗi E: HTTPS ở proxy nhưng logs vẫn chứa password

TLS giải mã ở edge. Nếu access logs hay APM ghi Authorization header thì secret bị lưu ở hạ tầng. Cần masking/redaction, giới hạn quyền và thời gian lưu.

### Lỗi F: `401` và `403` bị hiểu lẫn nhau

Không có Basic credential -> có thể nhận `401` kèm challenge. Đã xác thực nhưng không có `ROLE_ADMIN` -> `403`. Trong các request unsafe, `403` cũng có thể do CSRF. Test cả status, header và policy.

### Lỗi G: Chỉ có HTTP Basic nên tắt CSRF

Đây là kết luận sai đối với nhiều ứng dụng browser. Nếu browser tự gửi HTTP Basic credentials, request độc hại có thể tận dụng ambient authentication. Đánh giá CSRF theo phương thức HTTP, loại client và chính sách xác thực thực tế.

### Lỗi H: Bỏ qua lỗi chứng chỉ TLS

`curl -k` có thể khiến request chạy nhưng bỏ qua xác thực máy chủ. Dùng trust store/chứng chỉ hợp lệ; dev self-signed có thể dùng `--cacert`.

## 11. Checklist lựa chọn triển khai

1. Client gửi credentials chỉ đến **HTTPS URL** có TLS validation và hostname đúng.
2. Không phụ thuộc redirect HTTP→HTTPS để bảo vệ password đã gửi trước đó.
3. Reverse proxy/backend hop, certificate chain và forwarded headers được cấu hình từ nguồn tin cậy.
4. `Authorization`, cookie và secrets không bị ghi vào logs/APM/traces.
5. Mật khẩu lưu ở server bằng password hashing an toàn; có rate limiting và cảnh báo đăng nhập bất thường.
6. `httpBasic` được bật ở **đúng SecurityFilterChain**; `securityMatcher` và `@Order` không chặn route cần xác thực.
7. Nếu cần request độc lập, dùng `STATELESS` và kiểm tra behavior thực tế, nhưng không coi nó như logout.
8. Phân biệt authentication `401` với authorization `403`.
9. Dùng CSRF policy phù hợp, nhất là browser có thể tự gửi Basic credentials cho request thay đổi trạng thái.
10. Không trả password/hash/header Basic qua REST DTO hoặc logs.
11. Nếu UX cần Logout, session expiry hay thu hồi theo thiết bị, xem xét **form login/session** hoặc token có revocation.
12. Test MockMvc cho security chain, test HTTPS bằng client có certificate validation và test browser thật cho credential cache.
13. Không hứa rằng đóng tab, xóa cookie, `401` hay đổi realm sẽ làm browser quên Basic password.
14. Xác định rõ logout nghĩa là thu hồi một thiết bị, mọi thiết bị, session, refresh token hay toàn bộ quyền của account.

## 12. Câu hỏi tự luyện

**1.** Vì sao Base64 không đủ bảo mật?  
**Đáp án:** Đó là encoding đảo ngược được; password trong Basic header có thể khôi phục. HTTPS là yêu cầu bảo vệ dữ liệu khi truyền.

**2.** `WWW-Authenticate: Basic realm="Docs"` có tạo session không?  
**Đáp án:** Không. Realm quảng bá vùng bảo vệ và giúp client phân loại credentials; không tự phát hành session ID.

**3.** Không có cookie nhưng browser tải lại `/api/me` vẫn thành công. Tại sao?  
**Đáp án:** Browser có thể tự gửi `Authorization: Basic ...` đã ghi nhớ, server xác thực lại request.

**4.** Xóa `JSESSIONID` có xóa Basic credentials không?  
**Đáp án:** Không. HTTP Basic credentials nằm trong header do client quản lý; session cookie và HTTP auth cache là hai cơ chế khác nhau.

**5.** Trả `401` trong endpoint Logout có buộc mọi browser quên password không?  
**Đáp án:** Không. Có thể tạo prompt, nhưng không có đảm bảo logout chuẩn cho HTTP Basic.

**6.** GET `/api/me` với password đúng trả `200` nhưng GET `/api/admin` trả `403`. Lỗi ở đâu?  
**Đáp án:** Không nhất thiết lỗi. User đã xác thực nhưng thiếu authority `ROLE_ADMIN`.

**7.** Vì sao `STATELESS` chưa đủ chứng minh CSRF vô hại?  
**Đáp án:** Browser có thể tự gửi ambient Basic credentials; phải đánh giá khả năng cross-site request gây thay đổi trạng thái và policy CSRF.

**8.** Cách logout theo thiết bị tốt hơn?  
**Đáp án:** Sử dụng cơ chế session/token tách khỏi password và có expiry/invalidation/revocation cụ thể, không dựa vào cache HTTP Basic của browser.

## Kết luận

**HTTP Basic chỉ biểu diễn `username:password` bằng Base64, nên luôn cần HTTPS đúng nghĩa.** Browser có thể ghi nhớ và tự gửi lại credentials độc lập với cookie/session; Spring Security `httpBasic` và `SessionCreationPolicy.STATELESS` không cung cấp cách xóa bộ nhớ đó. **Không có logout HTTP Basic phổ quát đáng tin cậy.** Hãy chọn Basic cho client đơn giản qua TLS khi chấp nhận hạn chế này; dùng session/token với cơ chế thu hồi được thiết kế khi ứng dụng cần logout thực sự.