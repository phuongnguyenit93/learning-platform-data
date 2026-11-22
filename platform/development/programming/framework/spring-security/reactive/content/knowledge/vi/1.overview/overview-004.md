# Nhận diện người dùng, thông tin xác thực, vai trò và quyền truy cập

> **Ngữ cảnh:** Tổng quan về Spring Security trong ứng dụng Spring WebFlux (reactive). Bài này phân biệt rõ *ai đang gọi*, *bằng chứng họ cung cấp* và *họ được phép làm gì*, sau đó áp dụng bằng `SecurityWebFilterChain`, `Authentication` và `GrantedAuthority`.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích **identity/principal**, **credentials**, **authentication** và **authorization** mà không đánh đồng chúng.
- Phân biệt **role** (vai trò) với **authority/permission** (quyền thao tác), hiểu quy tắc tiền tố `ROLE_` trong Spring Security.
- Mô tả cách Spring Security WebFlux xử lý một yêu cầu, lưu ngữ cảnh bảo mật trong Reactor `Context` và quyết định cho phép/từ chối.
- Viết và kiểm tra chính sách truy cập bằng `ServerHttpSecurity`, `hasRole`, `hasAuthority` và `authenticated`.
- Nhận ra những chỗ phải kiểm tra quyền ở mức đối tượng/dữ liệu, kể cả khi endpoint đã được bảo vệ.

## 2. Bốn khái niệm không thể thay thế cho nhau

Giả sử một hệ thống báo cáo có tài khoản `lan`. Lan gửi tên đăng nhập và mật khẩu để xem báo cáo. Hệ thống cần trả lời hai câu hỏi độc lập: **Lan có thực sự là người đang đăng nhập không?** và **Lan có quyền xem báo cáo cụ thể này không?**

| Khái niệm | Câu hỏi | Ví dụ | Ý nghĩa |
| --- | --- | --- | --- |
| Identity / principal (danh tính/chủ thể) | Ai là chủ thể của yêu cầu? | Người dùng `lan`, service account `billing-service` | Đối tượng được xác định sau khi hệ thống xử lý bằng chứng nhận diện |
| Credentials (thông tin xác thực) | Chủ thể đưa bằng chứng gì? | Mật khẩu, HTTP Basic credentials, bearer token, mã OTP, khóa/chứng chỉ | Dữ liệu hoặc yếu tố dùng để chứng minh danh tính; không đồng nghĩa với quyền |
| Authentication (xác thực) | Bằng chứng có hợp lệ và gắn với chủ thể không? | Kiểm tra mật khẩu đã băm; xác minh chữ ký, hạn sử dụng và bên phát hành JWT | Quá trình và kết quả xác minh chủ thể |
| Authorization (phân quyền/ủy quyền truy cập) | Chủ thể đã xác thực được thực hiện hành động nào trên tài nguyên nào? | `report:read`, `ROLE_ADMIN`, chỉ được đọc báo cáo của phòng ban mình | Quyết định cho phép hoặc từ chối theo chính sách và ngữ cảnh |

**Ví dụ:** Mật khẩu đúng → `authentication` thành công; nhưng Lan không có `report:delete` → thao tác xóa vẫn bị từ chối. Ngược lại, tự khai `role=ADMIN` trong JSON request không khiến người gọi trở thành quản trị viên: quyền phải đến từ nguồn tin cậy được phía máy chủ kiểm tra.

Trong ứng dụng thực tế, identity còn có thể gắn với tenant, tổ chức, trạng thái tài khoản, thiết bị hoặc phiên đăng nhập. Hai người có cùng tên hiển thị không nhất thiết là cùng danh tính; với JWT, `sub` nên được hiểu trong ngữ cảnh issuer (`iss`) phù hợp.

## 3. Các đối tượng Spring Security cần nhận diện

| Thành phần | Vai trò thực tế trong WebFlux |
| --- | --- |
| `Authentication` | Biểu diễn chủ thể, credentials (nếu còn), tập `GrantedAuthority`, trạng thái xác thực; `getName()` thường trả tên chủ thể |
| `Principal` | Hợp đồng Java biểu diễn danh tính cơ bản; `Authentication` cũng là một `Principal` |
| `Authentication#getPrincipal()` | Đối tượng chủ thể, có thể là `UserDetails`, `Jwt`, một chuỗi hoặc kiểu riêng theo cơ chế xác thực |
| `UserDetails` | Mô hình tài khoản dùng phổ biến trong xác thực username/password: username, mật khẩu đã mã hóa, authorities và các trạng thái tài khoản |
| `ReactiveUserDetailsService` | Nạp người dùng theo kiểu không chặn (`Mono<UserDetails>`); ví dụ demo dùng `MapReactiveUserDetailsService` lưu trong bộ nhớ |
| `ReactiveAuthenticationManager` | Xác minh một `Authentication` theo cách reactive và trả kết quả xác thực |
| `GrantedAuthority` | Một quyền được biểu diễn bằng chuỗi, ví dụ `ROLE_ADMIN` hoặc `report:read` |
| `SecurityContext` | Chứa `Authentication` hiện tại |
| `ReactiveSecurityContextHolder` | Truy cập `SecurityContext` qua Reactor `Context` trong luồng reactive |
| `SecurityWebFilterChain` | Khai báo cơ chế xác thực và chính sách cho HTTP request trong WebFlux |

`Authentication#getCredentials()` **không phải chỗ để đọc lại mật khẩu của người dùng**. Sau xác thực, thông tin nhạy cảm có thể bị xóa khỏi đối tượng; ứng dụng không nên ghi credentials, token hay header `Authorization` vào log.

### 3.1. Role và permission được biểu diễn ra sao?

Spring Security dùng `GrantedAuthority` để biểu diễn các quyền mà bộ máy kiểm tra truy cập nhìn thấy. **Role là một quy ước trên authority**, không phải một loại quyền phép thuật tách biệt.

| Đã cấp trong `Authentication` | Điều kiện | Kết quả |
| --- | --- | --- |
| `ROLE_ADMIN` | `hasRole("ADMIN")` | Cho phép |
| `ROLE_ADMIN` | `hasAuthority("ROLE_ADMIN")` | Cho phép |
| `ADMIN` | `hasRole("ADMIN")` | Không khớp theo tiền tố mặc định `ROLE_` |
| `report:read` | `hasAuthority("report:read")` | Cho phép |
| `ROLE_ADMIN` | `hasAuthority("report:read")` | Không tự động cho phép |

- `hasRole("ADMIN")` thường kiểm tra authority `ROLE_ADMIN`; truyền `ADMIN` là cách viết đúng với quy ước mặc định.
- `hasAuthority("report:read")` kiểm tra đúng chuỗi được cấp, không tự thêm tiền tố.
- `User.withUsername(...).roles("ADMIN")` tạo authority `ROLE_ADMIN`; `authorities("report:read")` tạo chính xác `report:read`.
- Một người có thể có nhiều authority. Việc vai trò `ADMIN` có bao hàm `report:read` hay không là **quy tắc cấp quyền do hệ thống thiết kế**; Spring Security không tự suy ra bao hàm đó.
- Tên role/permission là quy ước của ứng dụng; nên quản lý tập quyền tập trung và chọn tên nhất quán, ví dụ `invoice:read`, `invoice:approve`.

**Ba tầng chính sách thường gặp:** kiểm tra đã xác thực (`authenticated`) → kiểm tra vai trò/quyền thao tác (`hasRole`, `hasAuthority`) → kiểm tra điều kiện dữ liệu như người sở hữu, tenant, trạng thái bản ghi. Hai tầng đầu không tự động thay thế tầng cuối.

## 4. Luồng xử lý một HTTP request trong Spring WebFlux

```text
HTTP request + credentials
    |
    v
Spring Security WebFilter chain
    |
    +--> Tìm và đọc bằng chứng (Basic, bearer token, session...)
    |        |
    |        v
    |    Xác thực qua cơ chế phù hợp
    |        |
    |        +-- thất bại / chưa có chứng thực hợp lệ --> xử lý chưa xác thực (thường HTTP 401 với API Basic/Bearer)
    |        |
    |        v
    |    Authentication + GrantedAuthority
    |        |
    v        v
SecurityContext trong Reactor Context
    |
    v
Kiểm tra rule truy cập (path/method/permission/điều kiện)
    |
    +-- từ chối chủ thể đã xác thực --> thường HTTP 403
    |
    v
Controller -> Service -> dữ liệu được phép -> response
```

Cách diễn đạt trên là sơ đồ khái niệm; các filter và entry point cụ thể phụ thuộc cấu hình. `SecurityWebFilterChain` áp dụng cho request WebFlux, còn `SecurityFilterChain`/`HttpSecurity` là cấu hình Servlet: **không dùng lẫn hai API**.

Trong WebFlux, việc thực thi có thể chuyển thread. Spring Security kết nối ngữ cảnh bảo mật với Reactor `Context`, vì vậy không dựa vào một `ThreadLocal` thông thường để nhận diện người dùng ở mọi điểm trong pipeline. Có thể lấy danh tính từ `ServerWebExchange.getPrincipal()` hoặc từ `ReactiveSecurityContextHolder`.

### 4.1. Authentication khác authorization trong từng bước

1. **Trích xuất bằng chứng:** chẳng hạn Basic gửi username/password hoặc bearer gửi access token.
2. **Xác thực:** so sánh mật khẩu đã mã hóa qua `PasswordEncoder`, hoặc kiểm tra chữ ký và các ràng buộc của token; nếu hợp lệ, tạo `Authentication` đã được xác thực.
3. **Gắn quyền:** các role/permission được lấy từ nguồn có thẩm quyền (database, identity provider, mapping claim đã kiểm soát...).
4. **Kiểm tra chính sách:** yêu cầu gọi `/api/reports` đòi `report:read`; yêu cầu `/api/admin` đòi `ROLE_ADMIN`.
5. **Bảo vệ dữ liệu:** sau khi vượt qua quy tắc endpoint, service vẫn kiểm tra người gọi có quyền với **báo cáo cụ thể** hay không.

Không dùng `authentication.isAuthenticated()` như kiểm tra duy nhất để suy ra người dùng thực: Spring Security có thể tạo anonymous authentication token. Hãy dùng `authenticated()` trong rule (hoặc cơ chế đánh giá trạng thái tin cậy phù hợp).

## 5. Ví dụ Java 17+ chạy được: WebFlux + HTTP Basic + phân quyền

Ví dụ dùng Spring Boot **3.3.7** (Spring Security 6.x), Maven và Java 17+. Mục đích là nhìn rõ sự khác nhau giữa danh tính, vai trò và quyền. Người dùng và mật khẩu đặt trong bộ nhớ **chỉ để học**. Tất cả endpoint demo dùng HTTP GET, nên không phải tắt CSRF để chạy thử.

Cấu trúc dự án:

```text
reactive-identity-demo/
├── pom.xml
└── src/main/java/demo/security/
    ├── ReactiveIdentityApplication.java
    ├── SecurityConfiguration.java
    └── DemoController.java
```

### 5.1. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.7</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>reactive-identity-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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

### 5.2. `src/main/java/demo/security/ReactiveIdentityApplication.java`

```java
package demo.security;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveIdentityApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveIdentityApplication.class, args);
    }
}
```

### 5.3. `src/main/java/demo/security/SecurityConfiguration.java`

```java
package demo.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.web.server.SecurityWebFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfiguration {

    @Bean
    SecurityWebFilterChain securityFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/public").permitAll()
                .pathMatchers("/api/reports").hasAuthority("report:read")
                .pathMatchers("/api/admin").hasRole("ADMIN")
                .anyExchange().authenticated()
            )
            .httpBasic(withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails reporter = User.withUsername("reporter")
            .password("{noop}reporter123")
            .authorities("report:read")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password("{noop}admin123")
            .roles("ADMIN")
            .build();

        return new MapReactiveUserDetailsService(reporter, admin);
    }
}
```

Giải thích từng lựa chọn:

- `@EnableWebFluxSecurity` bật cấu hình Spring Security WebFlux. `SecurityWebFilterChain` là chính sách HTTP cho ví dụ này.
- `permitAll()`: endpoint công khai, không đòi đăng nhập. Security filter vẫn hoạt động trên request.
- `hasAuthority("report:read")`: chỉ người có đúng quyền đọc báo cáo được vào `/api/reports`.
- `hasRole("ADMIN")`: yêu cầu `ROLE_ADMIN`; `roles("ADMIN")` cấp quyền này cho `admin`.
- `anyExchange().authenticated()`: các đường dẫn còn lại phải xác thực; đặt cuối để không che các rule cụ thể phía trên.
- `httpBasic(...)` kích hoạt HTTP Basic; tắt form login để API không chuyển hướng sang trang đăng nhập HTML.
- `{noop}` là bộ mã hóa không băm mật khẩu: **chỉ chấp nhận trong demo**. Ứng dụng thật phải dùng password encoder mạnh (ví dụ BCrypt/Argon2 theo chính sách) và lưu hash, không lưu mật khẩu rõ.
- `reporter` có `report:read` nhưng không có `ROLE_ADMIN`; `admin` có `ROLE_ADMIN` nhưng **chưa được cấp** `report:read`. Đây là lựa chọn có chủ đích nhằm thấy rõ role không tự bao hàm permission.

### 5.4. `src/main/java/demo/security/DemoController.java`

```java
package demo.security;

import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class DemoController {

    @GetMapping("/public")
    public Mono<String> publicInfo() {
        return Mono.just("public: OK");
    }

    @GetMapping("/reports")
    public Mono<String> reports() {
        return Mono.just("reports: OK");
    }

    @GetMapping("/admin")
    public Mono<String> admin() {
        return Mono.just("admin: OK");
    }

    @GetMapping("/me")
    public Mono<String> me() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(auth -> "hello, " + auth.getName());
    }
}
```

`/api/me` lấy tên chủ thể từ `Authentication` bên trong reactive security context, thay vì đoán người dùng từ request parameter hay dùng `ThreadLocal` tự tạo. `Mono` giúp kết quả tham gia pipeline WebFlux; nếu pipeline không có authenticated principal, rule `authenticated()` đã chặn trước khi đến endpoint này.

### 5.5. Chạy và xác minh

Trong thư mục chứa `pom.xml`, chạy:

```bash
mvn spring-boot:run
```

Ở terminal khác, chạy lần lượt:

```bash
curl -i http://localhost:8080/api/public
curl -i http://localhost:8080/api/me
curl -i -u reporter:reporter123 http://localhost:8080/api/me
curl -i -u reporter:reporter123 http://localhost:8080/api/reports
curl -i -u reporter:reporter123 http://localhost:8080/api/admin
curl -i -u admin:admin123 http://localhost:8080/api/admin
curl -i -u admin:admin123 http://localhost:8080/api/reports
curl -i -u reporter:wrong http://localhost:8080/api/reports
```

Kết quả mong đợi (chỉ liệt kê **HTTP status và body**, không cố định header hoặc định dạng thông báo lỗi vốn tùy cấu hình):

| Yêu cầu | HTTP status mong đợi | Body với yêu cầu thành công | Vì sao |
| --- | --- | --- | --- |
| GET `/api/public` không credentials | 200 | `public: OK` | `permitAll` |
| GET `/api/me` không credentials | 401 | — | Chưa xác thực, API dùng HTTP Basic |
| GET `/api/me` với `reporter` | 200 | `hello, reporter` | Đã xác thực |
| GET `/api/reports` với `reporter` | 200 | `reports: OK` | Có `report:read` |
| GET `/api/admin` với `reporter` | 403 | — | Thiếu `ROLE_ADMIN` |
| GET `/api/admin` với `admin` | 200 | `admin: OK` | Có `ROLE_ADMIN` |
| GET `/api/reports` với `admin` | 403 | — | `ROLE_ADMIN` không tự tạo `report:read` |
| GET `/api/reports` với mật khẩu sai | 401 | — | Authentication thất bại |

**401 và 403:** 401 cho biết thiếu thông tin xác thực hợp lệ (hoặc chưa xác thực) đối với chính sách ví dụ; 403 cho biết chủ thể đã được nhận diện nhưng không đủ quyền. Một ứng dụng có thể tùy biến cách phản hồi hay che giấu sự tồn tại của tài nguyên; không nên suy status chỉ từ việc giao diện có nút hay không.

## 6. Phân quyền theo URL, method và dữ liệu

### 6.1. HTTP authorization

`authorizeExchange` bảo vệ request theo method/path và authority. Với hệ thống thực, có thể thêm `pathMatchers(HttpMethod.POST, "/api/reports").hasAuthority("report:create")`, rồi rule cho GET. Hãy đặt rule cụ thể trước rule bao quát: nếu `anyExchange().authenticated()` đứng trước thì chính sách đến sau không còn hiệu lực như mong muốn.

Đừng suy rằng `permitAll()` tương đương tắt toàn bộ bảo vệ. Request vẫn đi qua security chain phù hợp, còn các kiểm soát khác (chẳng hạn headers hoặc CSRF theo cơ chế ứng dụng) vẫn có thể áp dụng.

### 6.2. Method authorization trong reactive service

HTTP rule là cửa vào; service vẫn có thể bị gọi từ các luồng khác. Spring Security WebFlux hỗ trợ `@EnableReactiveMethodSecurity` và `@PreAuthorize` để bảo vệ method trên Spring-managed bean. Đoạn dưới **minh họa phần tích hợp bổ sung**, không phải chương trình độc lập; nó giả định ứng dụng đã khai báo Spring Security và đã cấp quyền `report:read` cho người dùng cần thiết:

```java
// Trong một @Configuration của ứng dụng:
@EnableReactiveMethodSecurity(useAuthorizationManager = true)

// Trên một method của @Service do Spring quản lý:
@PreAuthorize("hasAuthority('report:read')")
public Mono<String> readReportSummary() {
    return Mono.just("summary");
}
```

Với mô hình reactive, method được bảo vệ nên trả kiểu publisher như `Mono`/`Flux` để Spring Security truy cập Reactor `Context`. Method security dựa vào Spring AOP proxy: gọi nội bộ từ một method khác **trong chính cùng object** có thể bỏ qua interceptor; hãy thiết kế lời gọi qua bean được Spring quản lý. Không dùng `@EnableMethodSecurity` của Servlet thay cho `@EnableReactiveMethodSecurity` trong bài WebFlux.

### 6.3. Quyền với từng đối tượng: chống truy cập vượt quyền

Giả sử `reporter` có `report:read` và gửi `GET /api/reports/42`. Rule endpoint xác nhận được **loại hành động**; nó chưa chứng minh report 42 thuộc tenant hoặc phòng ban của `reporter`.

Ở service, quy trình hợp lý là:

1. Lấy user ID/tenant ID đã xác thực từ ngữ cảnh đáng tin (không tin header `X-User-Id` do client tự khai).
2. Truy vấn tài nguyên theo cả ID **và** phạm vi được cấp, ví dụ `findByIdAndTenantId(reportId, currentTenantId)`; hoặc tra cứu rồi kiểm tra quyền sở hữu trước khi phát dữ liệu.
3. Nếu không thuộc phạm vi, trả lỗi phù hợp (403 hoặc 404 theo chính sách bảo mật) và không để lộ nội dung.
4. Kiểm tra lại đối với các hành động mutate (sửa, xóa, approve), kể cả khi người dùng được phép đọc.

Đây là bảo vệ chống **IDOR/BOLA** (truy cập đối tượng trái phép). Chỉ kiểm tra `ROLE_ADMIN` hay `report:read` ở URL sẽ không tự giải quyết phân quyền theo bản ghi hoặc tenant.

## 7. Username/password, session và JWT: nguồn xác thực khác nhau

### Username/password và session

Máy chủ kiểm tra username/password bằng `ReactiveAuthenticationManager` hoặc tích hợp thích hợp với `ReactiveUserDetailsService` và `PasswordEncoder`. Với đăng nhập qua session, trạng thái bảo mật thường được liên kết với session; chính sách cookie, thời hạn phiên, đăng xuất và CSRF rất quan trọng. Với HTTP Basic, client gửi credentials mỗi request, nên chỉ dùng trên HTTPS và không coi đó là giải pháp đăng nhập trình duyệt hiện đại mặc định.

### Bearer access token/JWT

Với resource server, client gửi `Authorization: Bearer <token>`. Ứng dụng phải cấu hình xác minh token phù hợp: chữ ký/khóa tin cậy, issuer, audience theo yêu cầu, expiration và các kiểm tra khác tùy chính sách. Sau khi token hợp lệ, Spring Security dựng `Authentication` và authorities từ các claim đã được ánh xạ.

- Trong cấu hình JWT mặc định phổ biến của Spring Security, scope `report.read` có thể trở thành authority `SCOPE_report.read`. Điều này **khác** `report:read` trong demo; muốn dùng chung thì phải thiết kế quy tắc mapping nhất quán.
- Claim `roles` tự do trong token **không mặc nhiên** biến thành `ROLE_ADMIN`; cần converter/mapping tương ứng và chỉ tin claim từ issuer đã xác minh.
- JWT có chữ ký hợp lệ không có nghĩa mọi hành động đều được phép: vẫn phải kiểm tra quyền và phạm vi dữ liệu.
- Access token và refresh token có mục đích khác nhau; không đưa refresh token vào các lời gọi API tài nguyên thông thường.

Demo ở mục 5 dùng HTTP Basic và tài khoản trong bộ nhớ để làm rõ khái niệm; khi chuyển sang JWT/OAuth2, **đừng đồng thời trộn** config của Basic như một mô hình mặc định nếu không có yêu cầu nghiệp vụ rõ ràng.

## 8. Quy trình thiết kế policy và các lỗi dễ mắc

Một cách xây dựng policy có thể kiểm tra được:

1. **Liệt kê tài nguyên/hành động**: ví dụ `report:read`, `report:export`, `report:approve`.
2. **Xác định nguồn danh tính đáng tin**: identity provider, user store, service identity; xác nhận trạng thái tài khoản và tenant nếu có.
3. **Định nghĩa role như tập quyền do ứng dụng cấp**: `ANALYST` có thể chứa `report:read`; `ADMIN` có những quyền nào phải được quyết định rõ.
4. **Đặt rule HTTP theo phạm vi nhỏ nhất cần thiết**; kiểm tra lại ở service đối với nghiệp vụ quan trọng.
5. **Thử cả trường hợp được phép và bị từ chối**, cùng trường hợp khác tenant/sai chủ sở hữu.
6. **Theo dõi kết quả an toàn**: log chủ thể hoặc correlation ID và quyết định tổng quát; không log mật khẩu, raw token, session secret hay PII không cần thiết.

| Lỗi | Tác hại | Cách sửa |
| --- | --- | --- |
| Nhầm `hasRole("ADMIN")` với authority `ADMIN` | Người đúng quyền bị 403, hoặc policy được cấp sai | Kiểm tra `ROLE_` prefix và mapping thực tế |
| Cho `ROLE_ADMIN` nhưng kỳ vọng tự có `report:read` | Logic cấp quyền không đúng thiết kế | Ánh xạ role → tập authority minh bạch |
| Chỉ ẩn nút trên frontend | Client vẫn có thể gọi API trực tiếp | Kiểm tra authorization tại backend |
| Tin user ID/role/tenant từ query, JSON hoặc header tự khai | Leo thang đặc quyền | Lấy danh tính/quyền từ authentication đã xác minh |
| Chỉ kiểm tra quyền endpoint, không kiểm tra bản ghi | IDOR/BOLA; lộ dữ liệu người khác | Kiểm tra object ownership, tenant và trạng thái nghiệp vụ ở service/repository |
| Dùng Servlet `SecurityFilterChain` hoặc `ThreadLocal` tự viết cho WebFlux | Cấu hình sai stack, mất ngữ cảnh trong reactive pipeline | Dùng `SecurityWebFilterChain`, Reactor `Context` |
| Dùng `block()` để tìm user trong WebFlux handler/service | Nguy cơ chặn event-loop, giảm khả năng xử lý | Nối `Mono`/`Flux` bằng `map`, `flatMap`... |
| Lưu mật khẩu rõ hoặc `{noop}` trong production | Rủi ro lộ credentials | Dùng `PasswordEncoder` mạnh và HTTPS |
| Vô hiệu CSRF vô điều kiện | Tăng nguy cơ thao tác trái ý người dùng với xác thực dựa trên cookie/session | Đánh giá riêng cơ chế xác thực, trình duyệt và tính chất API trước khi thay đổi |
| Đặt `anyExchange().permitAll()` hoặc rule quá rộng | Mở endpoint không chủ ý | Mặc định đóng, mở từng đường dẫn công khai có lý do |
| Xem 401 và 403 là cùng một lỗi | Khó debug và sai thông điệp cho client | Phân biệt chưa xác thực với đã xác thực nhưng thiếu quyền |

## 9. Bài tự kiểm tra

**Tình huống A.** `Authentication` có `ROLE_ADMIN` và `report:read`. `hasRole("ADMIN")` và `hasAuthority("report:read")` cùng đúng không?

**Đáp án:** Có, vì cả hai chuỗi authority cần thiết đều tồn tại.

**Tình huống B.** Người dùng đã xác thực và có `report:read`, nhưng yêu cầu xem report thuộc tenant khác. Có nên trả dữ liệu vì đã qua `hasAuthority`?

**Đáp án:** Không. Phải kiểm tra tenant hoặc ownership của report ở mức nghiệp vụ/dữ liệu.

**Tình huống C.** Client gửi `{"role":"ADMIN"}` trong body; server chưa xác thực user. Body này có thể cấp `ROLE_ADMIN` không?

**Đáp án:** Không. Authority chỉ được cấp từ thông tin/nguồn đã được xác minh và quy tắc phía máy chủ.

**Tình huống D.** Tại sao việc đọc `SecurityContext` bằng một `ThreadLocal` tự tạo dễ sai trong ứng dụng WebFlux?

**Đáp án:** Reactive pipeline có thể chuyển thread và không gắn một request với một thread cố định; Spring Security reactive dùng Reactor `Context`.

## 10. Ghi nhớ

- **Identity** trả lời *ai*, **credentials** cung cấp bằng chứng, **authentication** xác minh bằng chứng, **authorization** quyết định *được làm gì với tài nguyên nào*.
- Role trong Spring Security thường là authority có tiền tố `ROLE_`; permission cụ thể có thể là authority `report:read`. Không có quan hệ bao hàm tự động nếu chưa được cấp.
- WebFlux dùng `SecurityWebFilterChain`, `ReactiveSecurityContextHolder` và Reactor `Context`. Tránh bê nguyên cơ chế Servlet sang reactive.
- Bảo vệ endpoint là bước đầu; hệ thống đa tenant hoặc có ownership phải kiểm tra quyền theo dữ liệu trong service/repository.
- Luôn thử trường hợp không có credentials, sai credentials, đủ quyền, thiếu quyền và truy cập nhầm chủ sở hữu.

**Tham khảo chính thức:**

- Spring Security — WebFlux Security: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Security — Reactive Method Security: https://docs.spring.io/spring-security/reference/reactive/authorization/method.html
