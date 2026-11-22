# Phân biệt điểm truy cập công khai, yêu cầu xác thực và yêu cầu quyền

## 1. Ba câu hỏi bảo mật khác nhau trên cùng một HTTP request

Khi tích hợp **Spring Security** vào Spring Boot, việc một URL trả được dữ liệu hay không không chỉ phụ thuộc Controller có tồn tại. Mỗi request có thể đi qua các lớp kiểm tra: nhận diện đường dẫn, xác thực danh tính, phân quyền và xác minh quyền sở hữu dữ liệu cụ thể.

Phân biệt ba mức độ thường gặp:

1. **Điểm truy cập công khai (public endpoint):** người chưa đăng nhập cũng được phép gọi. Ví dụ GET /api/public/info hiển thị thông tin sản phẩm công khai.
2. **Điểm truy cập yêu cầu xác thực (authenticated endpoint):** người gọi phải được hệ thống xác thực, nhưng chưa đòi hỏi một vai trò/đặc quyền cụ thể. Ví dụ GET /api/me trả thông tin chính người đang đăng nhập.
3. **Điểm truy cập yêu cầu quyền (authorized/permission-protected endpoint):** ngoài việc có danh tính đã xác thực, người gọi phải có role/authority/permission phù hợp; với dữ liệu theo từng người còn phải kiểm tra **quyền trên đối tượng cụ thể**. Ví dụ xem báo cáo quản trị, đọc hóa đơn hoặc truy cập đơn hàng thuộc về một user.

**Xác thực (authentication)** trả lời “người gọi là ai và đã chứng minh danh tính chưa?”. **Phân quyền (authorization)** trả lời “danh tính này có được thực hiện thao tác này trên tài nguyên này không?”. Một user có thể đăng nhập thành công nhưng **không có quyền** xem trang quản trị.

Bài thuộc nhóm **Tích hợp bảo mật** của Spring Boot web-runtime, tập trung vào **Spring Boot 3.3.x, Spring Security 6.x, Spring MVC/Servlet và Java 17+**. Với Spring WebFlux, ý tưởng tương tự nhưng API thường là **SecurityWebFilterChain** và ServerHttpSecurity, không bê nguyên HttpSecurity của Servlet.

## 2. Request đi qua Spring Security trước Controller như thế nào?

Khi dùng **spring-boot-starter-security**, Spring Security tích hợp vào web application bằng các Servlet Filter. **FilterChainProxy** điều phối các **SecurityFilterChain**; các filter cụ thể xử lý SecurityContext, cơ chế authentication, exception và authorization.

Sơ đồ khái niệm:

~~~text
HTTP request
     |
     v
Servlet container / DelegatingFilterProxy
     |
     v
FilterChainProxy -> tìm SecurityFilterChain khớp request
     |
     +--> SecurityContext + Authentication mechanisms
     |        Basic / session / form login / bearer token ... tùy cấu hình
     |
     +--> AuthorizationFilter:
     |        requestMatchers ... FIRST MATCH
     |        permitAll? authenticated? hasRole? hasAuthority?
     |
     +--> ExceptionTranslationFilter / authentication entry point / 403 handler
     |
     v
DispatcherServlet -> Controller -> Service
                           |
                           +--> Có thể kiểm tra thêm method security
                           +--> Có thể kiểm tra owner/tenant của dữ liệu
     |
     v
HTTP response
~~~

Sơ đồ **không cam kết thứ tự chính xác của mọi filter** trên mọi cấu hình, chỉ mô tả trách nhiệm. Các request bị từ chối có thể **không tới Controller**. Ngược lại, việc Controller được gọi không chứng minh ứng dụng đã kiểm tra đầy đủ quyền trên **dữ liệu cụ thể** bên trong.

Một **Authentication** thường chứa:
- **Principal:** danh tính được framework xác nhận, ví dụ username.
- **Credentials:** thông tin dùng xác thực, cần được xử lý/bảo vệ; thường không giữ ở dạng raw khi không cần.
- **GrantedAuthority:** tập quyền/role đã được hệ thống gán.
- **authenticated flag:** trạng thái của Authentication, nhưng không nên tự suy luận “có object Authentication bất kỳ” là người dùng đăng nhập hợp lệ; anonymous authentication có thể cũng được biểu diễn bằng object.

**Quy tắc thực hành:** dùng cơ chế **SecurityContext**/Authentication do Spring Security quản lý, không tự tin vào request header như **X-User: admin** hoặc cookie **role=admin** nếu nguồn đó chưa được xác thực.

## 3. Quy tắc URL: permitAll, authenticated, hasRole và hasAuthority

Spring Security khai báo quy tắc qua **HttpSecurity.authorizeHttpRequests(...)**. Những expression phổ biến:

| Quy tắc | Ý nghĩa | Trường hợp dùng |
| --- | --- | --- |
| permitAll() | Không yêu cầu authentication/authority để qua bước authorization này | Thông tin public, login page, endpoint được công bố có chủ đích |
| authenticated() | Cần người gọi được xác thực | Thông tin tài khoản của chính mình, endpoint bất kỳ user đã login |
| hasRole("ADMIN") | Cần authority theo quy ước **ROLE_ADMIN** | Quản trị theo nhóm vai trò |
| hasAuthority("invoice:read") | Cần đúng authority **invoice:read** | Quyền chức năng hẹp, granular permission |
| hasAnyRole("USER", "ADMIN") | Có ít nhất một trong các role tương ứng | Nhiều nhóm được phép |
| hasAnyAuthority("a", "b") | Có ít nhất một authority chỉ định | Nhiều permission thay thế |
| denyAll() | Không cho request qua rule này | Chặn endpoint nội bộ, fallback **fail closed** |
| anonymous() | Chỉ cho principal được coi anonymous | Ví dụ trang/luồng chỉ dành cho khách; không đồng nghĩa permitAll() |

**permitAll() không có nghĩa bỏ qua toàn bộ Spring Security.** Filter chain vẫn hoạt động, có thể thêm security headers, xử lý authentication nếu client gửi credential, áp CSRF cho phương thức thay đổi trạng thái, CORS, session-related logic và các kiểm soát khác. Một request tới public endpoint nhưng gửi **Basic credentials sai** vẫn có thể bị authentication filter từ chối.

**authenticated() không đồng nghĩa user có quyền xem mọi bản ghi.** Nó chỉ bảo đảm trạng thái xác thực theo cấu hình; kiểm tra quyền của user A trên đơn hàng của user B còn là nhiệm vụ khác.

**hasRole() và hasAuthority() không đồng nghĩa.** Mặc định **hasRole("ADMIN")** yêu cầu một **GrantedAuthority tên ROLE_ADMIN** (có thể tùy biến prefix); **hasAuthority("ADMIN")** yêu cầu đúng chuỗi **ADMIN**. Khi tạo user bằng **.roles("ADMIN")**, Spring Security thường cấp authority **ROLE_ADMIN**.

### 3.1. Phân biệt các trường hợp bằng bảng

Giả sử hệ thống dùng rule:
- **GET /api/public/info**: permitAll.
- **GET /api/me**: authenticated.
- **GET /api/admin/report**: hasRole("ADMIN").
- **GET /api/invoices/report**: hasAuthority("invoice:read").

| Người gọi | Public | /api/me | /api/admin/report | /api/invoices/report |
| --- | --- | --- | --- | --- |
| Chưa có credentials | Được phép | Cần xác thực | Cần xác thực | Cần xác thực |
| reader: ROLE_USER | Được phép | Được phép | Từ chối quyền | Từ chối quyền |
| admin: ROLE_USER, ROLE_ADMIN | Được phép | Được phép | Được phép | Từ chối nếu thiếu invoice:read |
| auditor: ROLE_USER, invoice:read | Được phép | Được phép | Từ chối nếu thiếu ROLE_ADMIN | Được phép |

Quan sát quan trọng: **ADMIN không mặc định có mọi authority**. Việc có ROLE_ADMIN tự động bao gồm invoice:read chỉ đúng khi ứng dụng đã cấu hình **role hierarchy/quy tắc ánh xạ** cụ thể. Đừng ngầm coi role admin là “siêu quyền” khi thiết kế rule granular.

## 4. HTTP 401, 403, 302 và 404: cùng là không vào được nhưng khác nguyên nhân

Trong ứng dụng API dùng HTTP Basic, kết quả thông dụng:

| Tình huống | Mã HTTP thường gặp | Diễn giải |
| --- | --- | --- |
| GET public không credential | **200** khi Controller xử lý thành công | Không yêu cầu đăng nhập |
| GET protected không credential | **401 Unauthorized** và WWW-Authenticate: Basic ... | Chưa xác thực; client cần credentials |
| Có Basic credentials sai | **401 Unauthorized** | Xác thực thất bại |
| Đã xác thực, thiếu role/authority | **403 Forbidden** | Danh tính đã biết nhưng không đủ quyền |
| Đã xác thực, đủ quyền | **200** nếu xử lý nghiệp vụ thành công | Qua các cửa authorization |
| Endpoint bị rule denyAll | **403** với user đã xác thực | Rule cố ý cấm |
| Form-login application, chưa login | Có thể **302 redirect** tới login page | Entry point khác HTTP Basic |
| Tài nguyên không tồn tại hoặc cố tình che existence | **404** theo contract thiết kế | Không nhất thiết là lỗi xác thực |

**Không học thuộc rằng mọi thiếu login luôn là 401**. Với formLogin, framework có thể redirect; ứng dụng tùy biến entry point/AccessDeniedHandler có thể trả cấu trúc khác. Với **CSRF token thiếu** ở POST, người dùng đã xác thực vẫn có thể nhận **403** trước khi logic phân quyền thông thường chạy.

Một **401** không chỉ là “không có quyền”: nó nhấn mạnh **authentication cần được thực hiện hoặc đã thất bại**. Một **403** thường là **authorization/access denied**, nhưng cũng có thể đến từ CSRF, firewall hoặc policy khác. Đọc log/filter và test đúng tình huống, không suy luận chỉ từ status.

### 4.1. Authentication entry point và access denied handler

- **AuthenticationEntryPoint:** thường xử lý tình huống yêu cầu xác thực hoặc authentication không đạt, ví dụ phát 401 + Basic challenge hoặc redirect login.
- **AccessDeniedHandler:** xử lý AccessDeniedException cho người dùng đã xác thực nhưng không đủ quyền, thường trả 403.
- **ExceptionTranslationFilter:** kết nối ngoại lệ liên quan authentication/authorization với các handler phù hợp.

Nếu tự biến mọi 401/403 thành 200 với JSON **success=false**, monitoring, browser và HTTP client có thể hiểu sai. Giữ HTTP status đúng ý nghĩa và cung cấp error body không tiết lộ chi tiết nội bộ.

## 5. Matcher order: “match đầu tiên” quyết định quy tắc

Trong một **SecurityFilterChain**, Spring Security đánh giá các **requestMatchers** theo thứ tự đã khai báo; **quy tắc khớp đầu tiên** được sử dụng. Vì vậy order là một phần của bảo mật.

Cấu hình sai:

~~~java
// SAI: rule rộng đặt trước rule riêng.
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/**").permitAll()
        .requestMatchers("/api/admin/**").hasRole("ADMIN")
        .anyRequest().authenticated()
);
~~~

Vì /api/admin/report cũng khớp **/api/**, rule permitAll đã được áp dụng trước, nên rule admin có thể **không bao giờ được sử dụng**. Đặt rule hẹp trước:

~~~java
// ĐÚNG về thứ tự: admin trước, public cụ thể sau, fallback rõ.
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/admin/**").hasRole("ADMIN")
        .requestMatchers("/api/public/**").permitAll()
        .anyRequest().authenticated()
);
~~~

Hai đoạn trên là **fragment trong cấu hình HttpSecurity**, không phải chương trình Java độc lập. Chúng giải thích nguy cơ từ pattern, không thay thế một security policy hoàn chỉnh.

### 5.1. Method-specific matcher giảm quyền ngoài ý muốn

Rule:

~~~java
.requestMatchers(HttpMethod.GET, "/api/public/info").permitAll()
~~~

chỉ công bố **GET** ở path này. Nếu đặt:

~~~java
.requestMatchers("/api/public/**").permitAll()
~~~

thì có thể công bố thêm các method và endpoint bên dưới prefix (POST, DELETE...), kể cả khi API mới được thêm sau này. Đừng công bố một vùng path rộng khi mục tiêu chỉ là đọc một tài nguyên công khai.

**HEAD và OPTIONS** có hành vi framework/HTTP riêng; một GET matcher không tự bảo đảm mọi phương thức phụ trợ sẽ được cho phép. Nếu client browser cần **CORS preflight OPTIONS**, phải cấu hình CORS và rule phù hợp, không mở toàn bộ API một cách tùy tiện.

### 5.2. Chọn fail closed thay vì quên rule

Hai kiểu fallback thường gặp:

~~~java
// Mọi endpoint còn lại yêu cầu đăng nhập.
.anyRequest().authenticated()
~~~

~~~java
// Mọi endpoint chưa được liệt kê đều bị chặn.
.anyRequest().denyAll()
~~~

Dùng **authenticated()** khi policy cho phép mọi user đã login truy cập phần còn lại; dùng **denyAll()** khi muốn endpoint mới **không được mở** cho đến lúc chủ động cấp quyền. Không có lựa chọn đúng cho mọi ứng dụng, nhưng **phải có chính sách cho endpoint mới và test rule này**.

Tránh đặt **anyRequest()** trước các requestMatcher cụ thể vì nó là catch-all cuối cùng, có thể khiến cấu hình không hợp lệ hoặc các rule sau vô nghĩa.

## 6. Ứng dụng runnable: ba mức truy cập trên Spring Boot 3.3.13

Demo thực hành dùng **Spring Boot 3.3.13, Spring Security 6.x và Java 17+**, với một SecurityFilterChain dùng **HTTP Basic**. HTTP Basic chỉ dùng trong demo local và khi production phải chạy **HTTPS**; credentials được gửi theo Basic encoding, không được coi là đã mã hóa bí mật nếu đi qua HTTP không TLS.

Ba tài khoản **demo cố định** (không phải credential production):
- **reader / reader-pass** có **ROLE_USER**.
- **admin / admin-pass** có **ROLE_USER** và **ROLE_ADMIN**.
- **auditor / auditor-pass** có **ROLE_USER** và authority **invoice:read**.

Demo **không tắt CSRF** nhưng chỉ xây dựng GET endpoints, để tập trung vào public/authentication/authorization. Khi bổ sung POST/PUT/DELETE, phải xử lý CSRF và authentication model đúng như phần 10.

### 6.1. Cấu trúc dự án

~~~text
endpoint-access-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/access/
    │   │   └── EndpointAccessDemoApplication.java
    │   └── resources/application.yml
    └── test/
        └── java/com/example/access/
            └── EndpointAccessSecurityTest.java
~~~

**pom.xml**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>endpoint-access-demo</artifactId>
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
~~~

**src/main/resources/application.yml**:

~~~yaml
server:
  port: 8080
~~~

### 6.2. Mã Java đầy đủ: một file chứa application, security config và controller

**src/main/java/com/example/access/EndpointAccessDemoApplication.java**:

~~~java
package com.example.access;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class EndpointAccessDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(EndpointAccessDemoApplication.class, args);
    }
}

@Configuration
class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public/info")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/admin/report")
                    .hasRole("ADMIN")
                .requestMatchers(HttpMethod.GET, "/api/invoices/report")
                    .hasAuthority("invoice:read")
                .requestMatchers(HttpMethod.GET, "/api/me")
                    .authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());

        // Không gọi csrf.disable(): Spring Security giữ CSRF mặc định.
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
                .password(encoder.encode("reader-pass"))
                .roles("USER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("USER", "ADMIN")
                .build();

        UserDetails auditor = User.withUsername("auditor")
                .password(encoder.encode("auditor-pass"))
                .authorities("ROLE_USER", "invoice:read")
                .build();

        return new InMemoryUserDetailsManager(reader, admin, auditor);
    }
}

@RestController
class AccessController {

    @GetMapping(
        path = "/api/public/info",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    String publicInfo() {
        return "public-ok\n";
    }

    @GetMapping(
        path = "/api/me",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    String me(Authentication authentication) {
        return "user=" + authentication.getName() + "\n";
    }

    @GetMapping(
        path = "/api/admin/report",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    String adminReport() {
        return "admin-report\n";
    }

    @GetMapping(
        path = "/api/invoices/report",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    String invoicesReport() {
        return "invoice-report\n";
    }
}
~~~

### 6.3. Giải thích chính xác behavior

1. **SecurityFilterChain** là Bean của Spring Security. Spring Boot dùng cấu hình này thay vì policy bảo vệ mọi request mặc định của starter.
2. **requestMatchers(GET, "/api/public/info").permitAll()**: GET không cần credentials; các HTTP method khác tại cùng path không được tự động công khai bởi matcher này.
3. **GET /api/admin/report** chỉ cho người có **ROLE_ADMIN**. User có ROLE_USER thôi sẽ bị từ chối.
4. **GET /api/invoices/report** cần **invoice:read** đúng chuỗi, không tự coi ADMIN đủ quyền.
5. **GET /api/me** chỉ cần authenticated; Controller nhận **Authentication** do Spring Security cung cấp để lấy username. Không đọc identity từ query parameter.
6. **anyRequest().denyAll()**: các path/method chưa cấp quyền bị từ chối kể cả khi user đã login. Đây là policy **fail closed**.
7. **HTTP Basic** tạo challenge 401 cho client chưa xác thực; không bật form login trong demo để curl dễ quan sát và không bị redirect 302.
8. **PasswordEncoder BCrypt** băm mật khẩu ngay khi khởi động cho ba tài khoản demo. Code vẫn chứa password text trong source; điều này **chỉ phù hợp lab**, production phải dùng identity service/user repository và secret management. Không dùng **{noop}** hoặc mật khẩu cứng trong ứng dụng thật.
9. **CSRF vẫn bật**. Vì các endpoint demo chỉ GET và không thay đổi state, chúng không cần CSRF token cho phép thử này. **Đừng thêm POST cập nhật dữ liệu rồi tắt CSRF tùy tiện**.
10. Cấu hình trên áp cho **Spring MVC/Servlet**. Với ứng dụng WebFlux, dùng **SecurityWebFilterChain/ServerHttpSecurity**, không dùng HttpSecurity.

### 6.4. Chạy và dùng curl kiểm chứng

Trong thư mục **endpoint-access-demo**, cần JDK 17+, Maven và cổng 8080 rảnh:

~~~bash
mvn spring-boot:run
~~~

Có thể dùng **mvn package** rồi **java -jar target/endpoint-access-demo-1.0.0.jar**. Chạy trong terminal 1; terminal 2 gửi request. Với Windows PowerShell, dùng **curl.exe** nếu alias curl không hỗ trợ cờ.

**Thử 1 — public, không credentials:**

~~~bash
curl -i http://localhost:8080/api/public/info
~~~

Kết quả: **HTTP 200**, body:

~~~text
public-ok
~~~

**Thử 2 — cần xác thực, không gửi credentials:**

~~~bash
curl -i http://localhost:8080/api/me
~~~

Kết quả thông dụng của demo dùng HTTP Basic: **HTTP 401 Unauthorized**, response có **WWW-Authenticate: Basic ...**. Error body có thể do container/framework tạo và không nên cố định toàn bộ stdout.

**Thử 3 — xác thực reader:**

~~~bash
curl -i -u reader:reader-pass http://localhost:8080/api/me
~~~

Kết quả: **HTTP 200**, body:

~~~text
user=reader
~~~

**Thử 4 — reader không có quyền admin:**

~~~bash
curl -i -u reader:reader-pass \
  http://localhost:8080/api/admin/report
~~~

Kết quả: **HTTP 403 Forbidden**; Controller adminReport không được phép thực thi.

**Thử 5 — admin có ROLE_ADMIN:**

~~~bash
curl -i -u admin:admin-pass \
  http://localhost:8080/api/admin/report
~~~

Kết quả: **HTTP 200**, body:

~~~text
admin-report
~~~

**Thử 6 — auditor có granular authority:**

~~~bash
curl -i -u auditor:auditor-pass \
  http://localhost:8080/api/invoices/report
~~~

Kết quả: **HTTP 200**, body:

~~~text
invoice-report
~~~

**Thử 7 — admin không được tự cấp invoice:read:**

~~~bash
curl -i -u admin:admin-pass \
  http://localhost:8080/api/invoices/report
~~~

Kết quả: **HTTP 403 Forbidden**, vì danh sách authorities của admin **không có** invoice:read.

**Thử 8 — unknown path bị fallback denyAll:**

~~~bash
curl -i -u reader:reader-pass \
  http://localhost:8080/api/unlisted
~~~

Kết quả: **HTTP 403 Forbidden** trước khi xử lý routing thông thường, vì request không khớp các GET rule cho phép. Không nhầm nó với 404 của một ứng dụng không có security rule denyAll.

**Thử 9 — mật khẩu sai:**

~~~bash
curl -i -u reader:wrong-password \
  http://localhost:8080/api/me
~~~

Kết quả thông dụng: **HTTP 401 Unauthorized**. User tồn tại không đủ; credential phải được kiểm tra thành công.

**Cảnh báo:** cờ **curl -u** có thể làm lộ password demo trong shell history, command listing hoặc script; dùng giá trị lab, không ghi credential production trực tiếp vào lệnh/log. Trên production, HTTP Basic phải đi qua **HTTPS**.

### 6.5. Bảng kết quả dự kiến của lab

| Request | HTTP status mong đợi | Vì sao |
| --- | --- | --- |
| Anonymous GET /api/public/info | 200 | permitAll |
| Anonymous GET /api/me | 401 | authenticated cần login |
| reader GET /api/me | 200 | credentials đúng |
| reader GET /api/admin/report | 403 | thiếu ROLE_ADMIN |
| admin GET /api/admin/report | 200 | có ROLE_ADMIN |
| auditor GET /api/invoices/report | 200 | có invoice:read |
| admin GET /api/invoices/report | 403 | thiếu invoice:read |
| reader GET /api/unlisted | 403 | anyRequest denyAll |
| reader:wrong-password GET /api/me | 401 | xác thực thất bại |

Đây là **kết quả kỳ vọng của cấu hình demo**. Khi thêm proxy, formLogin, error handler, OAuth2 hoặc tùy biến, mã HTTP có thể khác. Không lấy bảng này làm hợp đồng cho tất cả ứng dụng Spring Security.

## 7. Kiểm thử tự động bằng MockMvc + Spring Security Test

Để không vô tình công khai một route khi refactor, biến bảng quyền thành test. Dependency **spring-security-test** đã có trong pom.xml với scope test.

Tệp **src/test/java/com/example/access/EndpointAccessSecurityTest.java**:

~~~java
package com.example.access;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class EndpointAccessSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void anonymousCanReadPublicInfo() throws Exception {
        mvc.perform(get("/api/public/info"))
                .andExpect(status().isOk())
                .andExpect(content().string("public-ok\n"));
    }

    @Test
    void anonymousCannotReadOwnProfile() throws Exception {
        mvc.perform(get("/api/me"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(username = "reader", roles = "USER")
    void authenticatedUserCanReadOwnProfile() throws Exception {
        mvc.perform(get("/api/me"))
                .andExpect(status().isOk())
                .andExpect(content().string("user=reader\n"));
    }

    @Test
    @WithMockUser(username = "reader", roles = "USER")
    void readerCannotReadAdminReport() throws Exception {
        mvc.perform(get("/api/admin/report"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(roles = {"USER", "ADMIN"})
    void adminCanReadAdminReport() throws Exception {
        mvc.perform(get("/api/admin/report"))
                .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(authorities = {"ROLE_USER", "invoice:read"})
    void auditorCanReadInvoiceReport() throws Exception {
        mvc.perform(get("/api/invoices/report"))
                .andExpect(status().isOk())
                .andExpect(content().string("invoice-report\n"));
    }

    @Test
    @WithMockUser(roles = {"USER", "ADMIN"})
    void adminCannotReadInvoiceReportWithoutPermission() throws Exception {
        mvc.perform(get("/api/invoices/report"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(roles = "USER")
    void unknownRouteIsDenied() throws Exception {
        mvc.perform(get("/api/unlisted"))
                .andExpect(status().isForbidden());
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

Kết quả mong đợi: **8 test đi qua**, không có AssertionError. Maven log thay đổi theo hệ điều hành/phiên bản; không gán một stdout cố định cho mvn test.

**@WithMockUser** tạo principal thử nghiệm trong Spring SecurityContext; nó **không chứng minh bcrypt password hoặc HTTP Basic parsing hoạt động**. Vì vậy hãy giữ cả test MockMvc policy và **test end-to-end** dùng curl/spring security test **httpBasic(...)** hoặc server thật khi kiểm tra authentication mechanism. Trong test production, thêm negative cases: anonymous, sai role, sai authority, sai owner, expired token, CSRF và HTTP method khác.

### 7.1. Test thay đổi thứ tự matcher

Một test bảo vệ khỏi cấu hình sai ở phần 5 là:

~~~java
@Test
@WithMockUser(roles = "USER")
void adminRouteMustNeverBecomePublic() throws Exception {
    mvc.perform(get("/api/admin/report"))
            .andExpect(status().isForbidden());
}
~~~

Đây là **fragment bổ sung** nếu đưa vào class test đã có mvc/imports. Nó hữu ích khi người khác thêm rule /api/** rộng và không nhận ra rule admin bị shadowed. Trong ứng dụng nhiều module, mỗi nhóm endpoint nhạy cảm cần có ít nhất một test **đúng quyền** và một test **thiếu quyền**.

## 8. Authentication có thể đến từ nhiều cơ chế, authorization vẫn phải rõ

Demo dùng **HTTP Basic** để nhìn rõ 401/403. Ứng dụng thật có thể dùng:

| Cơ chế xác thực | Client cung cấp gì | Điểm cần nhớ |
| --- | --- | --- |
| HTTP Basic | Authorization: Basic ... | Credentials cần HTTPS; browser có hành vi lưu credentials; vẫn cần xét CSRF |
| Form Login + Session | Login form, sau đó JSESSIONID/session cookie | Login redirect, CSRF, session fixation và logout cần framework quản lý |
| OAuth2 Resource Server JWT | Authorization: Bearer <token> | Xác minh chữ ký, issuer/audience/expiry; ánh xạ claims thành authorities |
| Opaque Bearer Token | Authorization: Bearer <token> | Server/introspection xác thực token và xác định permissions |
| mTLS | Client certificate qua TLS | Xác minh certificate và ánh xạ danh tính; không tự thay nghiệp vụ phân quyền |

Sau khi xác thực thành công, SecurityContext có thể chứa principal/authorities để các rule **authenticated/hasRole/hasAuthority** đánh giá. Nhưng **không có nghĩa mọi authentication mechanism gán authority giống nhau**.

Ví dụ OAuth2 resource server thường map scope thành authority có tiền tố **SCOPE_**. Nếu token có scope **orders.read**, một rule **hasAuthority("SCOPE_orders.read")** có thể phù hợp theo converter mặc định của cấu hình đó; **hasRole("ADMIN")** sẽ không tự trùng với scope. Kiểm tra **JwtAuthenticationConverter/GrantedAuthoritiesMapper** nếu có customization. Đừng tự quyết định từ claim JSON chưa verify chữ ký/token validity.

### 8.1. Principal có identity nhưng thiếu roles

Một ứng dụng có thể xác thực token đúng chữ ký nhưng không map roles/authorities; khi đó:
- authenticated() có thể cho qua.
- hasRole("ADMIN") hoặc hasAuthority("invoice:read") có thể từ chối.
- Lỗi nằm ở mapping/policy (hoặc token thực thiếu permission), không nhất thiết ở login/password.

Khi debug, có thể log **loại authentication** và **tên các authority không nhạy cảm** trong môi trường được bảo vệ; không log token gốc, password, session ID hoặc toàn bộ SecurityContext.

## 9. Role, authority và quyền trên từng đối tượng

Một rule **hasRole("USER")** hoặc **authenticated()** áp dụng cho **nhóm người gọi**, chưa chứng minh người đó có quyền đọc **đơn hàng 123**.

Ví dụ nguy hiểm:

~~~java
// SAI về bảo mật nghiệp vụ nếu service chỉ lookup theo ID.
@GetMapping("/api/orders/{id}")
OrderDto read(@PathVariable long id) {
    return orderRepository.findById(id)
            .map(OrderDto::from)
            .orElseThrow();
}
~~~

Nếu chỉ có rule **/api/orders/** authenticated(), mọi người đăng nhập có thể đổi ID để thử xem tài nguyên của nhau. Đây là dạng **broken object-level authorization (BOLA)/IDOR**.

Cách tốt hơn: kết hợp xác thực người gọi và truy vấn có ràng buộc **owner/tenant** hoặc một authorization policy ở service:

~~~java
// Fragment minh họa; OrderDto, repository và exception do ứng dụng định nghĩa.
@GetMapping("/api/orders/{id}")
OrderDto read(@PathVariable long id, Authentication auth) {
    return orderRepository.findByIdAndOwnerUsername(id, auth.getName())
            .map(OrderDto::from)
            .orElseThrow(() -> new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Order not found"));
}
~~~

Ở đây repository chỉ trả dữ liệu thuộc người dùng hiện tại. 404 có thể được dùng để không tiết lộ sự tồn tại của tài nguyên; trong hệ thống khác, contract có thể yêu cầu 403. Quan trọng nhất là **không trả dữ liệu của user khác**. Đối với admin/đại diện hỗ trợ, policy có thể cho ngoại lệ có audit và yêu cầu riêng, không mở toàn bộ truy vấn theo ID mặc định.

**Các fragment chưa biên dịch độc lập**: cần @GetMapping, Authentication, ResponseStatusException, HttpStatus, repository/DTO và lớp Controller. Không thêm chúng vào runnable demo phần 6 nếu chưa triển khai data model.

### 9.1. Phân biệt nhóm quyền và kiểm tra chi tiết

- **Role/authority theo chức năng:** có thể đọc báo cáo, tạo đơn, đổi cấu hình.
- **Resource ownership:** đơn này thuộc người dùng nào? tenant nào? project nào?
- **Attribute-based policy:** account đang bị khóa? thời điểm này có được phép? đơn hàng trạng thái nào?
- **Scope/context:** đang xem dữ liệu của chính mình hay hành động thay người khác? Có phê duyệt cụ thể không?

Một endpoint **authenticated()** không phải “an toàn với mọi bản ghi” nếu service không thực thi các điều kiện này.

## 10. Method security: kiểm tra quyền ở tầng Service

Spring Security hỗ trợ **@PreAuthorize, @PostAuthorize** và các annotation khác cho method-level authorization, nhưng **starter security không tự bật method security**. Cần khai báo **@EnableMethodSecurity**.

Ví dụ **fragment** nằm ở lớp @Configuration, không phải chương trình đầy đủ riêng:

~~~java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfig {
}
~~~

Tầng Service có thể kiểm tra:

~~~java
// Fragment trong một @Service được Spring quản lý.
@PreAuthorize("hasAuthority('invoice:read')")
public InvoiceDto readInvoice(long id) {
    return invoiceRepository.findById(id)
            .map(InvoiceDto::from)
            .orElseThrow();
}
~~~

**@PreAuthorize** kiểm tra trước khi gọi method; nếu không đạt, method không thực thi. Nhưng fragment trên chỉ kiểm tra quyền **invoice:read tổng quát**; nếu dữ liệu theo owner/tenant, vẫn cần điều kiện người sở hữu. Một chính sách phức tạp có thể ủy quyền cho bean như **@PreAuthorize("@invoicePolicy.canRead(authentication, #id)")** với một **invoicePolicy bean** có logic thật.

Lưu ý kỹ thuật:
- Method security dựa vào Spring AOP/proxy theo cấu hình phổ biến. Nếu object gọi **một method khác của chính nó** bằng **this.someMethod()**, lời gọi đó có thể **bỏ qua proxy** và annotation trên method đích không được áp dụng. Hãy đặt policy ở bean boundary phù hợp và kiểm thử đường gọi thật.
- Method security **bổ sung**, không nên tự động thay thế toàn bộ URL rules.
- Các rule ở request và method có thể cùng kiểm tra; vượt qua lớp URL chưa đồng nghĩa vượt qua method policy.
- Không dựa vào annotation trang trí nếu **@EnableMethodSecurity** chưa bật hoặc class không do Spring quản lý.

**Khi nào dùng tầng nào?** URL rules tốt cho cổng coarse-grained như “/admin/** chỉ ADMIN”, method rules tốt khi một service được gọi từ HTTP, batch, messaging và cần giữ policy gần nghiệp vụ; object-level checks phải sử dụng dữ liệu owner/tenant đáng tin và có test.

## 11. CSRF: public, authenticated và permission không thay thế kiểm tra request giả mạo

Một người dùng đã đăng nhập qua **session cookie** hoặc browser tự gửi HTTP Basic credentials có thể bị lừa truy cập một trang khác gửi request thay họ. Đó là bối cảnh của **Cross-Site Request Forgery (CSRF)**.

Spring Security với Servlet **bật CSRF protection mặc định** cho các **unsafe HTTP methods**, ví dụ POST/PUT/PATCH/DELETE. Vì thế:

~~~text
POST /api/orders
Authorization: Basic ...
(no valid CSRF token)
~~~

có thể nhận **403** dù Basic authentication hợp lệ và user có authority **order:write**. Đừng kết luận ngay rằng user thiếu role hoặc authorization matcher sai.

**Không dùng GET để tạo/sửa/xóa dữ liệu** chỉ để tránh CSRF token. GET được thiết kế là safe method; thay đổi state qua GET làm tăng rủi ro và phá cache/crawler expectations.

### 11.1. Khi nào cân nhắc disable/ignore CSRF?

Chỉ khi mô hình threat cụ thể chứng minh endpoint **không dựa vào credentials mà browser tự đính kèm** và đã có biện pháp phù hợp. Ví dụ một API chỉ dùng Bearer token trong Authorization header do client có kiểm soát cung cấp và không có cookie-based auth **có thể** xem xét tắt CSRF trên chain riêng. Nhưng:
- HTTP Basic với browser vẫn có nguy cơ CSRF.
- Một hệ thống có session cookie cần CSRF protection hoặc biện pháp tương đương.
- **.csrf(csrf -> csrf.disable())** tắt rộng có thể là quyết định sai nếu cùng app có login form/cookie.
- **permitAll() không tự vô hiệu CSRF**; một public POST vẫn có thể bị 403 vì không có CSRF token.

Trong ứng dụng kết hợp SPA và browser session, xử lý token qua framework và header/cookie phù hợp; cấu hình CORS cũng không tự thay CSRF.

### 11.2. Ví dụ rule permission cho hành động thay đổi trạng thái

~~~java
// Fragment cho một API đã thiết kế authentication + CSRF tương ứng:
.requestMatchers(HttpMethod.POST, "/api/orders/**")
    .hasAuthority("order:write")
~~~

Đây là **điều kiện authorization**, **không phải** xử lý CSRF. Có quyền **order:write** không cho phép bỏ token khi CSRF đang bật. Cũng cần kiểm tra dữ liệu đơn hàng mà user có được phép thay đổi hay không.

## 12. Public endpoint vẫn cần bảo mật các yếu tố khác

Cấu hình permitAll chỉ loại bỏ yêu cầu authz của **rule đó**, không bảo đảm endpoint public là vô hại. Ví dụ:
- **GET /api/catalog:** công khai nhưng vẫn cần input validation, rate limit, caching và chống data scraping theo chính sách.
- **POST /register:** công khai với người chưa login nhưng phải chống spam, bot, account enumeration, brute force và xử lý CSRF phù hợp với browser form.
- **GET /actuator/health:** có thể công khai liveness/readiness ở mạng nội bộ theo vận hành, nhưng không mặc định công khai /actuator/env, /heapdump hoặc toàn bộ management endpoints. Một actuator endpoint có hiện diện hay không còn phụ thuộc dependency/exposure config.
- **Static CSS/JS:** có thể public; Spring Security khuyên dùng **permitAll() thay vì web.ignoring()** để giữ các security headers/filter protections. Nếu filter bypass hoàn toàn, các bảo vệ này có thể không được áp dụng.
- **Error responses:** không tiết lộ stack trace, file path hoặc nguyên văn database errors cho người dùng public.

### 12.1. Bài toán CORS preflight

Browser cross-origin có thể gửi **OPTIONS preflight** trước request thật. Với cấu hình **anyRequest().denyAll()**, một OPTIONS chưa được xử lý phù hợp có thể bị từ chối.

CORS là cơ chế browser kiểm soát **origin được phép đọc/gửi request theo CORS policy**; nó không phải authentication và không làm người dùng có authority. Cần:
1. Xác định allowed origins cụ thể, methods, headers và credentials.
2. Cấu hình **CorsConfigurationSource** hoặc Spring MVC CORS và tích hợp **http.cors(...)** khi cần.
3. Không kết hợp **Access-Control-Allow-Origin: *** với credentialed requests một cách tùy tiện.
4. Giữ authorization rule riêng cho request thật và test cả preflight lẫn request có credentials.

Không “sửa” CORS bằng cách permitAll toàn bộ **/api/** rồi bỏ kiểm tra quyền.

## 13. Khi có nhiều SecurityFilterChain: securityMatcher khác requestMatchers

Trong một ứng dụng nhiều khu vực (web session, public API, internal API), có thể khai báo nhiều bean **SecurityFilterChain** với **@Order** khác nhau.

- **securityMatcher(...)**: quyết định **SecurityFilterChain nào áp dụng** cho request.
- **authorizeHttpRequests().requestMatchers(...)**: quyết định **rule phân quyền bên trong chain đã được chọn**.
- **FilterChainProxy** thường chọn **chain đầu tiên khớp** theo thứ tự cấu hình; nó không tự hợp nhất mọi chain thành một tập rule.

Ví dụ fragment minh họa, không phải cấu hình chạy độc lập:

~~~java
@Bean
@Order(1)
SecurityFilterChain api(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/public/**").permitAll()
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults());
    return http.build();
}
~~~

Nếu chỉ khai báo chain này mà không có fallback chain, request ngoài **/api/** có thể **không đi qua Spring Security chain đó**. Việc đó không đồng nghĩa Spring Boot tự từ chối mọi URL ngoài /api. Hãy thiết kế một **fallback SecurityFilterChain** cho các request còn lại khi cần và kiểm tra thứ tự các bean.

Tránh dùng nhiều chain chỉ để chia nhỏ vài rule đơn giản. Một chain với requestMatchers rõ ràng thường dễ kiểm tra hơn; nhiều chain nên có lý do kiến trúc (ví dụ session browser vs Bearer API) và integration test đủ rộng.

## 14. Chẩn đoán sự cố khi “đã login mà vẫn 403”

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| Public GET trả 401 | Client gửi Basic credentials sai, chain khác áp dụng, custom filter | Xem credentials, SecurityFilterChain được chọn và AuthenticationEntryPoint |
| Anonymous GET protected trả 302 thay 401 | Form login entry point đang bật | Kiểm tra httpBasic/formLogin/exceptionHandling |
| Đã login nhưng /admin trả 403 | Thiếu ROLE_ADMIN hoặc matcher/rule không đúng | Xem GrantedAuthority đã được xác minh, matcher order |
| Có authority ADMIN nhưng hasRole("ADMIN") thất bại | hasRole thường cần ROLE_ADMIN | Kiểm tra prefix/GrantedAuthoritiesMapper |
| Có ROLE_ADMIN nhưng invoice:read bị từ chối | Role không tự bao gồm permission | Cấp/map authority đúng policy hoặc cấu hình hierarchy có chủ đích |
| POST authenticated trả 403 | Thiếu CSRF token hoặc policy cấm | Kiểm tra CsrfFilter/log và method-specific rules |
| /api/admin/** bất ngờ public | Rule permitAll rộng đứng trước | Review thứ tự requestMatchers, thêm regression test |
| Method có @PreAuthorize nhưng vẫn truy cập được | Chưa @EnableMethodSecurity hoặc self-invocation/proxy | Test gọi từ bean khác qua Spring, kiểm tra config |
| User A đọc được record của user B | Chỉ check authenticated, thiếu object ownership | Query theo owner/tenant, test IDOR/BOLA |
| Một số path không có bảo vệ | securityMatcher chỉ chọn một phần URL, thiếu fallback chain | Kiểm tra toàn bộ filter chains và @Order |
| Browser CORS error dù user có quyền | Origin/preflight/credentials policy | Kiểm tra OPTIONS, CORS config và headers |
| Error endpoint trả 403 thay response mong muốn | ERROR/FORWARD dispatch hoặc fallback denyAll | Kiểm tra dispatcher types và handler, không mở rộng cả API |
| JWT hợp lệ nhưng thiếu permissions | Mapping claims/scope -> GrantedAuthority sai | Kiểm tra converter và authorities thực tế |
| Static files 403 | Rule fallback áp lên static resource | permitAll theo path cụ thể; không bypass filter vô cớ |

### 14.1. Bật log chẩn đoán có kiểm soát

Trong môi trường phát triển, có thể tăng log cho Spring Security:

~~~yaml
logging:
  level:
    org.springframework.security: DEBUG
~~~

Log có thể cho thấy filter/authorization decision theo cấu hình, nhưng **không** coi mọi thông điệp debug là ổn định qua phiên bản. Không bật debug quá rộng lâu dài trên production: có thể tăng chi phí và để lộ metadata request hoặc cơ chế xác thực. **Không log password, token, JSESSIONID hoặc raw Authorization header**.

Một quy trình debug hợp lý:
1. Xác định chính xác **URL, HTTP method, principal** và request type.
2. Xác định **SecurityFilterChain** nào được chọn.
3. Xác định **requestMatcher khớp đầu tiên**.
4. Kiểm tra Authentication đã xác thực và tập authorities.
5. Kiểm tra CSRF/CORS/request firewall nếu request không tới Controller.
6. Nếu vào service, kiểm tra method security và quyền owner/tenant.
7. Chỉ tùy biến entry point/handler khi biết response contract cần thay đổi.
8. Đưa phát hiện thành negative/positive test để tránh tái diễn.

## 15. Bài tập tự đánh giá

**Bài 1.** GET /api/news có permitAll(), người chưa login có gọi được không?

**Đáp án:** Có thể qua bước request authorization mà không cần login. Nhưng vẫn phải vượt qua các filter khác, không được giả định HTTP 200 nếu Controller lỗi hoặc client gửi credentials sai.

**Bài 2.** User đã login và có ROLE_USER, còn rule /api/me là authenticated(). Đủ điều kiện không?

**Đáp án:** Có theo request rule đó, vì authenticated không yêu cầu ROLE_USER cụ thể. Dữ liệu trả ra vẫn phải được giới hạn theo user hiện tại.

**Bài 3.** User có ROLE_USER, rule /api/admin/** có hasRole("ADMIN"). Kết quả thông thường?

**Đáp án:** Với HTTP Basic đã xác thực, thường trả HTTP 403 vì thiếu ROLE_ADMIN; không phải 401 vì danh tính đã xác thực.

**Bài 4.** User có authority **ADMIN** (không có ROLE_ADMIN), hasRole("ADMIN") cho qua không?

**Đáp án:** Không theo prefix mặc định. hasRole("ADMIN") thường kiểm tra ROLE_ADMIN. Nếu muốn đối chiếu chuỗi ADMIN, dùng hasAuthority("ADMIN") theo policy đã chọn.

**Bài 5.** ROLE_ADMIN có tự động cấp **invoice:read** không?

**Đáp án:** Không. Chỉ khi hệ thống gán thêm permission hoặc cấu hình role hierarchy/mapping cụ thể.

**Bài 6.** Đặt permitAll("/api/**") trước hasRole("/api/admin/**") có an toàn không?

**Đáp án:** Không. Rule rộng có thể match trước; admin rule bị vô hiệu do first-match semantics.

**Bài 7.** POST /api/orders với user có **order:write** vẫn trả 403. Có chắc thiếu authority không?

**Đáp án:** Không. Nếu CSRF mặc định bật, request thiếu/không hợp lệ token cũng có thể bị 403. Phải kiểm tra bộ lọc và lỗi gốc.

**Bài 8.** GET /api/orders/123 yêu cầu authenticated(), user A đổi 123 thành 124 và xem được đơn của B. Đây là lỗi gì?

**Đáp án:** **Broken object-level authorization (BOLA/IDOR)**. URL authenticated không kiểm tra quyền theo owner/tenant của record.

**Bài 9.** Có @PreAuthorize ở service method nhưng không có @EnableMethodSecurity. Có được thực thi tự động không?

**Đáp án:** Không. Spring Boot Starter Security không bật method security chỉ do annotation xuất hiện. Cần enable và kiểm thử proxy invocation.

**Bài 10.** Một chain được giới hạn bằng securityMatcher("/api/**") nhưng không có fallback. Request /admin liệu chắc chắn bị deny không?

**Đáp án:** Không. Nó có thể không được chain đó bảo vệ; cần kiểm tra các chain khác và cấu hình fallback thích hợp.

**Bài 11.** Public /register POST có permitAll. Có thể bị CSRF chặn không?

**Đáp án:** Có nếu CSRF protection áp dụng. Public authorization không có nghĩa tắt các bộ lọc khác.

**Bài 12.** Browser báo CORS error. Có nên đổi mọi rule thành permitAll để sửa?

**Đáp án:** Không. Phải cấu hình origin/preflight/credentials đúng, đồng thời giữ authentication/authorization cho request thật.

## 16. Checklist review Spring Security trước triển khai

- **Định nghĩa rõ phạm vi:** endpoint nào public, endpoint nào chỉ cần authenticated, endpoint nào yêu cầu role/authority.
- **Least privilege:** public chỉ cho những URL và HTTP methods thật sự cần; không tạo matcher /** quá rộng.
- **Matcher order:** rule cụ thể trước rule rộng; anyRequest là fallback được lựa chọn có chủ đích.
- **Role/authority:** phân biệt ROLE_ prefix với exact authority và converter cho JWT/OAuth2.
- **Object-level:** đọc/ghi dữ liệu theo owner, tenant, trạng thái và policy; không chỉ authenticated() trên path.
- **Authentication:** danh tính đến từ Spring SecurityContext sau khi credentials/token đã được verify, không từ header/cookie tự khai.
- **Errors:** mong đợi 401 cho unauthenticated ở Basic API, 403 cho authenticated nhưng thiếu quyền; hiểu 302/CSRF/404 tùy kiến trúc.
- **CSRF/CORS:** không tắt CSRF chung khi còn browser cookies/Basic; test unsafe methods và preflight.
- **Chain selection:** nếu dùng nhiều SecurityFilterChain, kiểm tra @Order, securityMatcher và fallback đầy đủ.
- **Method security:** bật @EnableMethodSecurity khi cần; kiểm tra AOP self-invocation và quyền trên tài nguyên.
- **Password/token:** không hard-code credential production, không dùng HTTP Basic trên cleartext HTTP, bảo vệ secret/log.
- **Observability:** logs/metrics không chứa raw Basic, Bearer token, session ID hoặc dữ liệu riêng tư.
- **Regression tests:** mỗi endpoint nhạy cảm có test anonymous, đúng quyền, sai quyền và owner/tenant khác; thêm case HTTP method khác.
- **Default deny:** endpoint mới phải được review rõ trước khi công khai hoặc cấp quyền.

## 17. Kết luận

Ba mức **public – authenticated – authorized** là ba quyết định khác nhau, không phải ba tên gọi thay thế:

- **permitAll()**: không yêu cầu người dùng đăng nhập để qua **rule authorization** đã khai báo.
- **authenticated()**: yêu cầu danh tính được xác thực, **chưa chứng minh quyền trên mọi tài nguyên**.
- **hasRole()/hasAuthority()**: yêu cầu các quyền đã được hệ thống cấp; object-level policy còn kiểm tra **ai sở hữu dữ liệu cụ thể**.

Để có web-runtime an toàn, hãy kết hợp **request matcher đúng thứ tự**, **CSRF/CORS đúng mô hình**, **SecurityFilterChain được áp toàn bộ vùng cần bảo vệ**, **method/data authorization**, và **integration tests với cả tình huống cho phép lẫn từ chối**. Quy tắc fail closed và kiểm tra quyền tại nơi dữ liệu được truy cập giúp tránh biến một endpoint “chỉ cần login” thành lỗ hổng đọc dữ liệu của người khác.

## Tài liệu tham khảo chính thức

- Spring Security — Authorize HttpServletRequests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — Authentication Architecture: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security — In-Memory Authentication: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/in-memory.html
- Spring Security — HTTP Basic Authentication: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/basic.html
- Spring Security — Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security — CSRF Protection: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Spring Security — Testing: https://docs.spring.io/spring-security/reference/servlet/test/index.html
- Spring Boot 3.3 — Spring Security: https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html
