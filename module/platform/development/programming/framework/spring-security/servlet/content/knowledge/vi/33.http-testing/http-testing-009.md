# Ma trận endpoint theo HTTP method, vai trò và trạng thái đăng nhập trong Spring Security Servlet

## 1. Vấn đề: một endpoint có nhiều kết quả tùy người gọi và HTTP method

Trong Spring MVC, một đường dẫn như `/api/orders/42` có thể hỗ trợ `GET`, `PUT` và `DELETE`. Không phải cả ba thao tác đều cần cùng một quyền. Một người chưa đăng nhập có thể bị từ chối, một tài khoản `ROLE_MEMBER` chỉ được xem/sửa, còn người quản trị `ROLE_ADMIN` có thể xóa. Khi dùng cookie/session, những request thay đổi trạng thái còn phải vượt qua kiểm tra **CSRF**.

Vì thế câu hỏi kiểm thử không chỉ là “URL này có trả 200 không?”, mà là:

> **Với HTTP method M, đường dẫn P, trạng thái xác thực S, tập quyền R và điều kiện bảo mật bổ sung C, ứng dụng phải trả gì và có thực hiện tác động được phép không?**

Một ma trận endpoint giúp biến các quyết định này thành hợp đồng kiểm thử tự động, tránh tình trạng mở một URL đúng nhưng vô tình cho phép phương thức khác, hoặc chỉ kiểm happy path của admin mà quên người dùng thông thường.

Trong bài này chúng ta sẽ:

- Xây dựng ma trận **HTTP method × endpoint × anonymous/authenticated × role × CSRF**.
- Phân biệt chính xác **401 Unauthorized**, **403 Forbidden** và trạng thái thành công **200/201/204** trong cấu hình cụ thể.
- Viết `SecurityFilterChain` với **request matcher theo HTTP method**, thứ tự rõ ràng, mặc định từ chối đường dẫn chưa khai báo.
- Xây một ứng dụng **Java 17 + Spring Boot 3.3.5 + Spring Security 6 Servlet** và kiểm thử bằng `@SpringBootTest`, `@AutoConfigureMockMvc`, `MockMvc`, JUnit 5 parameterized tests.
- Test riêng CSRF để không nhầm lỗi thiếu token với lỗi thiếu role.
- Hiểu giới hạn của ma trận URL: quyền theo đối tượng/tenant, session, CORS, HEAD/OPTIONS và method-level security cần kiểm thêm.

**Phạm vi:** Spring Security trên **Servlet stack** với `authorizeHttpRequests`. Ví dụ dùng **HTTP Basic** để có response status 401/403 rõ ràng trong test. Ứng dụng sử dụng form login hoặc OAuth2 Login có thể redirect 302 cho người chưa đăng nhập; không sao chép nguyên kỳ vọng HTTP Basic sang mọi dự án.

## 2. Hai trục quan trọng: method và trạng thái danh tính

### 2.1. HTTP method thay đổi ý nghĩa của URL

| Method | Mục đích thường gặp | Có thể cần CSRF trong ứng dụng browser? | Ví dụ |
| --- | --- | --- | --- |
| `GET` | Đọc tài nguyên | Không, nếu tuân thủ ngữ nghĩa không thay đổi trạng thái | `GET /api/orders/42` |
| `HEAD` | Lấy metadata response không có body | Không theo CSRF matcher mặc định | `HEAD /api/orders/42` |
| `POST` | Tạo tài nguyên/thực hiện lệnh | Có, nếu sử dụng bối cảnh dễ bị browser gửi tự động như cookie session | `POST /api/orders` |
| `PUT` | Thay thế/cập nhật tài nguyên | Có | `PUT /api/orders/42` |
| `PATCH` | Cập nhật một phần tài nguyên | Có | `PATCH /api/me` |
| `DELETE` | Xóa tài nguyên | Có | `DELETE /api/orders/42` |
| `OPTIONS` | Hỏi phương thức/khả năng được hỗ trợ; browser có thể gửi CORS preflight | Thường không bị CSRF mặc định, nhưng có thể cần cấu hình CORS đặc biệt | `OPTIONS /api/orders` |

Spring Security `CsrfFilter` thường bỏ qua **GET, HEAD, TRACE và OPTIONS** theo matcher mặc định, bảo vệ những method còn lại. Điều này không có nghĩa một GET gây thay đổi dữ liệu là an toàn: phải thiết kế GET chỉ đọc. Không dùng `GET /admin/delete?id=42` rồi dựa vào việc CSRF mặc định không yêu cầu token.

**URL giống nhau, method khác nhau có thể cần vai trò khác nhau.** `requestMatchers(HttpMethod.GET, "/api/orders/*")` không giống `requestMatchers(HttpMethod.DELETE, "/api/orders/*")`. Cũng không nên mặc định rằng quyền `ROLE_ADMIN` bao hàm quyền `ROLE_MEMBER`; nếu muốn quan hệ thứ bậc role phải định nghĩa rõ.

### 2.2. Trạng thái đăng nhập không đồng nghĩa với quyền

Các trường hợp cần phân biệt:

| Trạng thái | Authentication/authorities | Ý nghĩa kiểm thử |
| --- | --- | --- |
| **Anonymous** | Không có người dùng xác thực; Spring có thể đặt `AnonymousAuthenticationToken` | Với endpoint cần xác thực, HTTP Basic thường trả 401 |
| **Sai credentials** | Thử Basic password sai, chưa thành authenticated | Thường 401 với HTTP Basic |
| **Authenticated MEMBER** | `ROLE_MEMBER` | Có thể truy cập route yêu cầu MEMBER nhưng không mặc nhiên có ADMIN |
| **Authenticated ADMIN** | `ROLE_ADMIN` | Có thể truy cập route ADMIN, không tự động có `ROLE_MEMBER` |
| **Authenticated nhưng thiếu role** | Đã đăng nhập nhưng quyền không đủ | Thường 403 từ authorization |
| **Session hết hạn/không gửi cookie** | Request hiện tại không có authentication phù hợp | Như anonymous, tùy entry point |
| **Tài khoản bị khóa/vô hiệu hóa** | Provider có thể từ chối xác thực hoặc phiên cũ có thể còn state | Cần test policy account status/revocation riêng |

**Một status 403 không đủ chứng minh rule role đã chạy đúng.** Với POST không kèm CSRF token, request có thể bị `CsrfFilter` chặn trước khi `AuthorizationFilter` kiểm tra quyền. Để test quyền của POST/PUT/PATCH/DELETE một cách rõ ràng, **cấp CSRF token hợp lệ trong test** trước, sau đó viết bộ test thiếu/sai CSRF riêng.

## 3. Diễn giải HTTP status đúng theo cấu hình

| Status | Ý nghĩa khi kiểm thử | Cần tránh suy diễn |
| --- | --- | --- |
| **200 OK** | Request được cho phép và handler trả dữ liệu | Không chứng minh quyền sở hữu tài nguyên đã được kiểm nếu controller không có ACL |
| **201 Created** | Handler tạo tài nguyên và thông báo thành công | Test thực tế còn cần kiểm state/Location/header khi có |
| **204 No Content** | Handler xử lý thành công, không có body | Không phải mọi PUT/PATCH/DELETE đều bắt buộc trả 204 |
| **302 Found** | Redirect, chẳng hạn sang trang login của form login | Không nhầm với HTTP Basic 401; kiểm `Location` |
| **401 Unauthorized** | Client chưa được xác thực hợp lệ và cần authentication | “Unauthorized” ở đây chủ yếu là **chưa authenticated**, không phải “đã login nhưng role sai” |
| **403 Forbidden** | Server hiểu request nhưng từ chối, có thể vì thiếu quyền hoặc CSRF | Phải xác định filter/condition nào từ chối |
| **404 Not Found** | Handler không có tài nguyên, hoặc ứng dụng chủ động che thông tin về đối tượng không được phép | Không luôn là lỗi route; có thể là lựa chọn bảo vệ thông tin |
| **405 Method Not Allowed** | MVC đã thấy route nhưng method không được handler hỗ trợ | Nếu Security deny trước MVC, có thể nhận 401/403 thay vì 405 |

Với ví dụ HTTP Basic bên dưới, các request **đã cấp CSRF khi cần** sẽ có quy tắc: anonymous vào protected endpoint nhận 401; người đã xác thực nhưng không đủ role nhận 403; người đủ quyền nhận 200, 201 hoặc 204 tùy handler. Kết quả này **gắn với cấu hình của demo**, không phải cam kết chung của mọi Spring Security application.

Nếu dùng `formLogin()`, unauthenticated browser GET thường redirect tới `/login`; nếu dùng API bearer token, response 401 và `WWW-Authenticate` có thể mang thông tin lỗi khác. Nếu app tùy biến `AuthenticationEntryPoint` hoặc `AccessDeniedHandler`, phải cập nhật ma trận theo contract thực tế.

## 4. Thiết kế ma trận cho một API mẫu

Ứng dụng giả lập có hai tài khoản:

- `member`: có đúng `ROLE_MEMBER`.
- `admin`: có đúng `ROLE_ADMIN`; **không** có `ROLE_MEMBER`.

Chính sách của từng endpoint:

| Method | URL | Chính sách ở SecurityFilterChain | Kết quả thành công |
| --- | --- | --- | --- |
| GET | `/public/ping` | `permitAll()` | 200 |
| GET | `/api/me` | `authenticated()` | 200 |
| PATCH | `/api/me` | `authenticated()` | 204 |
| POST | `/api/orders` | `hasRole("MEMBER")` | 201 |
| GET | `/api/orders/{id}` | `hasAnyRole("MEMBER","ADMIN")` | 200 |
| PUT | `/api/orders/{id}` | `hasRole("MEMBER")` | 204 |
| DELETE | `/api/orders/{id}` | `hasRole("ADMIN")` | 204 |
| GET | `/admin/metrics` | `hasRole("ADMIN")` | 200 |
| Mọi route/method khác | Bất kỳ URL còn lại | `denyAll()` | Từ chối |

Giả định có CSRF token hợp lệ cho PATCH/POST/PUT/DELETE, ma trận **kỳ vọng trạng thái** là:

| Method | URL | Anonymous | MEMBER | ADMIN |
| --- | --- | ---: | ---: | ---: |
| GET | `/public/ping` | 200 | 200 | 200 |
| GET | `/api/me` | 401 | 200 | 200 |
| PATCH | `/api/me` | 401 | 204 | 204 |
| POST | `/api/orders` | 401 | 201 | 403 |
| GET | `/api/orders/42` | 401 | 200 | 200 |
| PUT | `/api/orders/42` | 401 | 204 | 403 |
| DELETE | `/api/orders/42` | 401 | 403 | 204 |
| GET | `/admin/metrics` | 401 | 403 | 200 |
| POST | `/admin/metrics` (không khai báo) | 401 | 403 | 403 |

Ở dòng cuối, **POST** không được phép bởi bất kỳ rule nào dù **GET** cùng URL được ADMIN đọc. Request rơi vào `anyRequest().denyAll()`. Nếu muốn trả 405 cho method không hỗ trợ thay vì bảo vệ trước MVC, cần thiết kế chính sách routing/authorization khác và test đúng kết quả đã quyết định; không dùng status 405 làm giả định mặc định.

Ma trận nên còn chứa **test group về CSRF**, **test role sai**, **test quyền trên đối tượng** và **test các trường hợp không hỗ trợ**. Một bảng Excel/Markdown chỉ có dữ liệu mà không được chạy trong CI dễ trở nên lỗi thời; phần 8 sẽ biến mỗi ô thành một test JUnit có thể chạy.

## 5. Spring Security rule order: method + path + role

Trong `authorizeHttpRequests`, các request matcher thường được xét **theo thứ tự khai báo** và áp dụng quyết định của matcher đầu tiên phù hợp. Bởi vậy rule cụ thể phải đứng trước rule rộng.

~~~java
// Mảnh cấu hình, không phải file Java độc lập.
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/public/ping")
        .permitAll()
    .requestMatchers(HttpMethod.GET, "/api/me")
        .authenticated()
    .requestMatchers(HttpMethod.PATCH, "/api/me")
        .authenticated()
    .requestMatchers(HttpMethod.POST, "/api/orders")
        .hasRole("MEMBER")
    .requestMatchers(HttpMethod.GET, "/api/orders/*")
        .hasAnyRole("MEMBER", "ADMIN")
    .requestMatchers(HttpMethod.PUT, "/api/orders/*")
        .hasRole("MEMBER")
    .requestMatchers(HttpMethod.DELETE, "/api/orders/*")
        .hasRole("ADMIN")
    .requestMatchers(HttpMethod.GET, "/admin/metrics")
        .hasRole("ADMIN")
    .anyRequest().denyAll()
);
~~~

**Đặt `requestMatchers("/api/**").authenticated()` lên đầu sẽ sai** nếu bạn muốn rule cụ thể `POST /api/orders` yêu cầu MEMBER: một người chỉ có ADMIN hoặc một người bất kỳ đã login có thể trúng rule rộng trước, dẫn đến bypass điều kiện role. Khi dùng nhiều `SecurityFilterChain`, còn phải xét chain nào được chọn trước (qua `securityMatcher` và `@Order`), không chỉ thứ tự matcher bên trong chain.

`HttpMethod.GET`, `HttpMethod.POST`, `HttpMethod.PATCH`, ... đến từ `org.springframework.http.HttpMethod`. Trong Spring Framework 6, `HttpMethod` là **class với các constant**, không nên viết `switch` Java trên nó như enum cũ; trong test có thể dùng `HttpMethod.valueOf("GET")`.

**`hasRole("MEMBER")`** so khớp authority `ROLE_MEMBER`. **`hasAuthority("MEMBER")`** so khớp literal `MEMBER`. Không trộn hai kiểu nếu không định nghĩa rõ. `hasAnyRole("MEMBER","ADMIN")` cho phép một trong hai; trong ví dụ `ROLE_ADMIN` không hàm ý `ROLE_MEMBER`.

Mẫu path `/api/orders/*` trong cấu hình minh họa dùng cho **một segment ID**. Nếu sản phẩm có URL chứa slash/matrix variables/servlet path đặc biệt, cần test request matcher tương ứng với MVC, container, URL decoding và proxy; tránh tự tin một dấu `*` bao phủ mọi dạng URL.

## 6. Demo hoàn chỉnh: Java 17 + Spring Boot 3.3.5 + Spring Security 6

Cấu trúc dự án:

~~~text
http-matrix-demo/
├── pom.xml
├── src/main/java/example/httpmatrix/HttpMatrixApplication.java
└── src/test/java/example/httpmatrix/HttpMatrixTests.java
~~~

Ví dụ **không cần cơ sở dữ liệu**, không cần auth provider ngoài. Nó cố ý chỉ mô phỏng endpoint và HTTP status để tập trung test ma trận. Phần kiểm quyền sở hữu từng đơn hàng, business transaction, lưu trữ dữ liệu hoặc session management trong production cần có thêm.

### 6.1. pom.xml

~~~xml
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
    <groupId>example</groupId>
    <artifactId>http-matrix-demo</artifactId>
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

`spring-security-test` cung cấp `csrf()`, `httpBasic()`, `user()` và các công cụ hỗ trợ MockMvc. JUnit Jupiter/parameterized testing được cung cấp qua `spring-boot-starter-test` trong cấu hình này. Đây là dự án Servlet do `spring-boot-starter-web` sử dụng Spring MVC, không phải WebFlux.

### 6.2. Spring Security và các endpoint cần test

**src/main/java/example/httpmatrix/HttpMatrixApplication.java**:

~~~java
package example.httpmatrix;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class HttpMatrixApplication {

    public static void main(String[] args) {
        SpringApplication.run(HttpMatrixApplication.class, args);
    }

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
                User.withUsername("member")
                        .password("{noop}member-pass")
                        .roles("MEMBER")
                        .build(),
                User.withUsername("admin")
                        .password("{noop}admin-pass")
                        .roles("ADMIN")
                        .build()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(
                                HttpMethod.GET, "/public/ping")
                            .permitAll()
                        .requestMatchers(
                                HttpMethod.GET, "/api/me")
                            .authenticated()
                        .requestMatchers(
                                HttpMethod.PATCH, "/api/me")
                            .authenticated()
                        .requestMatchers(
                                HttpMethod.POST, "/api/orders")
                            .hasRole("MEMBER")
                        .requestMatchers(
                                HttpMethod.GET, "/api/orders/*")
                            .hasAnyRole("MEMBER", "ADMIN")
                        .requestMatchers(
                                HttpMethod.PUT, "/api/orders/*")
                            .hasRole("MEMBER")
                        .requestMatchers(
                                HttpMethod.DELETE, "/api/orders/*")
                            .hasRole("ADMIN")
                        .requestMatchers(
                                HttpMethod.GET, "/admin/metrics")
                            .hasRole("ADMIN")
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .csrf(Customizer.withDefaults())
                .build();
    }

    @RestController
    static class ApiController {

        @GetMapping("/public/ping")
        Map<String, String> ping() {
            return Map.of("status", "ok");
        }

        @GetMapping("/api/me")
        Map<String, String> me(Authentication authentication) {
            return Map.of("username", authentication.getName());
        }

        @PatchMapping("/api/me")
        ResponseEntity<Void> updateProfile() {
            return ResponseEntity.noContent().build();
        }

        @PostMapping("/api/orders")
        ResponseEntity<Map<String, String>> createOrder() {
            return ResponseEntity.status(HttpStatus.CREATED)
                    .body(Map.of("id", "42"));
        }

        @GetMapping("/api/orders/{id}")
        Map<String, String> getOrder(@PathVariable String id) {
            return Map.of("id", id, "status", "created");
        }

        @PutMapping("/api/orders/{id}")
        ResponseEntity<Void> updateOrder(@PathVariable String id) {
            return ResponseEntity.noContent().build();
        }

        @DeleteMapping("/api/orders/{id}")
        ResponseEntity<Void> deleteOrder(@PathVariable String id) {
            return ResponseEntity.noContent().build();
        }

        @GetMapping("/admin/metrics")
        Map<String, Integer> metrics() {
            return Map.of("totalOrders", 1);
        }
    }
}
~~~

**Tại sao cấu hình này hợp với ma trận?**

- Đầu tiên match method + path nên cùng `/api/orders/42` có quyền khác cho GET, PUT và DELETE.
- `permitAll` chỉ dùng cho **GET /public/ping**, không tự mở mọi method của `/public/ping`.
- `authenticated` cho GET/PATCH `/api/me`: admin và member đều hợp lệ, nhưng người chưa xác thực không được.
- `POST /api/orders` và `PUT /api/orders/*` chỉ cho `ROLE_MEMBER`, không mặc định dành cho admin. Chính sách này được chọn để minh họa **role không tự kế thừa**, không phải thiết kế role bắt buộc của mọi sản phẩm.
- `DELETE /api/orders/*` và `GET /admin/metrics` yêu cầu `ROLE_ADMIN`.
- `anyRequest().denyAll()` chặn method/URL chưa khai báo, kể cả khi handler MVC có thể tồn tại ở nơi khác.
- `httpBasic` dùng để tạo 401 (unauthenticated) và 403 (authenticated but denied) dễ kiểm qua HTTP. Với login session, response anonymous có thể là 302.
- `csrf(Customizer.withDefaults())` giữ bảo vệ các unsafe methods. `permitAll` hay `authenticated` không tự vô hiệu hóa CSRF.

**Lưu ý security:** `{noop}` lưu password dạng rõ trong demo **chỉ để kiểm thử**; production dùng PasswordEncoder, nơi lưu credential và quy tắc xác thực phù hợp. Controller PUT/DELETE demo không thực hiện thay đổi DB, không có owner/tenant check; chúng minh họa contract route/status, **không** phải một API order an toàn đầy đủ. Với nghiệp vụ thật phải kiểm ownership/ACL ở service layer và kiểm kết quả dữ liệu thực.

### 6.3. Cách chạy và kiểm thủ công bằng curl

Yêu cầu máy có JDK 17+ và Maven. Từ thư mục `http-matrix-demo`:

~~~bash
mvn spring-boot:run
~~~

Ở terminal khác:

~~~bash
# Public endpoint: 200.
curl -i http://localhost:8080/public/ping

# Protected endpoint không có credentials: 401 (HTTP Basic).
curl -i http://localhost:8080/api/me

# Member có thể đọc profile: 200.
curl -i -u member:member-pass \
  http://localhost:8080/api/me

# Member không có quyền admin: 403.
curl -i -u member:member-pass \
  http://localhost:8080/admin/metrics

# Admin được xem metrics: 200.
curl -i -u admin:admin-pass \
  http://localhost:8080/admin/metrics

# Thiếu CSRF khi dùng unsafe method: 403, kể cả member hợp role.
curl -i -u member:member-pass -X POST \
  http://localhost:8080/api/orders
~~~

Response `GET /api/me` với member trả JSON `{"username":"member"}`; `GET /admin/metrics` với admin trả `{"totalOrders":1}`. JSON field order không được coi là bảo đảm byte-for-byte. Để thử POST **có CSRF token**, dùng UI/client duy trì session và token phù hợp hoặc chạy `MockMvc` tests mục 7. Không bỏ `CsrfFilter` chỉ để câu lệnh curl POST trả 201.

## 7. Tạo một ma trận JUnit 5 có thể chạy tự động

Thay vì viết 27 phương thức giống nhau, ta mô hình hóa mỗi **hàng chính sách** và tạo ba **tình huống người gọi**: `ANON`, `MEMBER`, `ADMIN`. Kết quả là **9 hàng × 3 danh tính = 27 ca kiểm thử**.

**src/test/java/example/httpmatrix/HttpMatrixTests.java**:

~~~java
package example.httpmatrix;

import java.util.List;
import java.util.stream.Stream;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpMethod;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.request;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class HttpMatrixTests {

    @Autowired
    MockMvc mvc;

    record Rule(
            String method,
            String path,
            boolean includeCsrf,
            int anonymousStatus,
            int memberStatus,
            int adminStatus) {}

    record Scenario(
            String method,
            String path,
            boolean includeCsrf,
            String actor,
            int expectedStatus) {}

    // Một dòng là contract cho method + URL, không phải 3 test copy tay.
    static Stream<Scenario> matrix() {
        List<Rule> rules = List.of(
                new Rule(
                        "GET", "/public/ping", false,
                        200, 200, 200),
                new Rule(
                        "GET", "/api/me", false,
                        401, 200, 200),
                new Rule(
                        "PATCH", "/api/me", true,
                        401, 204, 204),
                new Rule(
                        "POST", "/api/orders", true,
                        401, 201, 403),
                new Rule(
                        "GET", "/api/orders/42", false,
                        401, 200, 200),
                new Rule(
                        "PUT", "/api/orders/42", true,
                        401, 204, 403),
                new Rule(
                        "DELETE", "/api/orders/42", true,
                        401, 403, 204),
                new Rule(
                        "GET", "/admin/metrics", false,
                        401, 403, 200),
                new Rule(
                        "POST", "/admin/metrics", true,
                        401, 403, 403)
        );

        return rules.stream().flatMap(r -> Stream.of(
                new Scenario(
                        r.method(), r.path(), r.includeCsrf(),
                        "ANON", r.anonymousStatus()),
                new Scenario(
                        r.method(), r.path(), r.includeCsrf(),
                        "MEMBER", r.memberStatus()),
                new Scenario(
                        r.method(), r.path(), r.includeCsrf(),
                        "ADMIN", r.adminStatus())
        ));
    }

    @ParameterizedTest(name = "{index}: {0}")
    @MethodSource("matrix")
    void authorizationMatrix(Scenario scenario) throws Exception {
        MockHttpServletRequestBuilder request =
                request(
                        HttpMethod.valueOf(scenario.method()),
                        scenario.path());

        // Test authorization của unsafe method cần CSRF hợp lệ.
        // Không đưa thiếu CSRF vào cùng ca kiểm role.
        if (scenario.includeCsrf()) {
            request.with(csrf());
        }

        if ("MEMBER".equals(scenario.actor())) {
            request.with(httpBasic("member", "member-pass"));
        } else if ("ADMIN".equals(scenario.actor())) {
            request.with(httpBasic("admin", "admin-pass"));
        }

        // ANON: không gửi credential.
        mvc.perform(request)
                .andExpect(status().is(scenario.expectedStatus()));
    }

    static Stream<Arguments> unsafeWithCredentials() {
        return Stream.of(
                Arguments.of(
                        "PATCH", "/api/me",
                        "member", "member-pass"),
                Arguments.of(
                        "POST", "/api/orders",
                        "member", "member-pass"),
                Arguments.of(
                        "PUT", "/api/orders/42",
                        "member", "member-pass"),
                Arguments.of(
                        "DELETE", "/api/orders/42",
                        "admin", "admin-pass")
        );
    }

    @ParameterizedTest
    @MethodSource("unsafeWithCredentials")
    void unsafeMethodWithoutCsrfIsForbidden(
            String method, String path, String username, String password)
            throws Exception {

        mvc.perform(request(HttpMethod.valueOf(method), path)
                        .with(httpBasic(username, password)))
                .andExpect(status().isForbidden());
    }

    @Test
    void invalidCsrfTokenIsForbidden() throws Exception {
        mvc.perform(request(HttpMethod.POST, "/api/orders")
                        .with(httpBasic("member", "member-pass"))
                        .with(csrf().useInvalidToken()))
                .andExpect(status().isForbidden());
    }

    @Test
    void invalidBasicPasswordIsUnauthenticated() throws Exception {
        mvc.perform(request(HttpMethod.GET, "/api/me")
                        .with(httpBasic("member", "wrong-pass")))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void successfulGetReturnsExpectedIdentityAndData()
            throws Exception {
        mvc.perform(request(HttpMethod.GET, "/api/me")
                        .with(httpBasic("member", "member-pass")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value("member"));

        mvc.perform(request(HttpMethod.GET, "/api/orders/42")
                        .with(httpBasic("admin", "admin-pass")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value("42"));
    }
}
~~~

**Chạy:**

~~~bash
mvn test
~~~

Với code và dependency vừa trình bày, bộ test được thiết kế gồm **27 ca ma trận** + **4 ca thiếu CSRF** + **3 test đơn**. Chúng xác nhận response status theo bối cảnh đã chọn; các assertion JSON ở cuối giúp bảo đảm request được phép thực sự tới handler trả dữ liệu mong đợi, không chỉ nhận 200 từ một interceptor khác.

Để chạy **một test class** bằng Maven Surefire:

~~~bash
mvn -Dtest=HttpMatrixTests test
~~~

Không dùng `Thread.sleep()` hoặc tự tạo `SecurityContextHolder` cho từng test. `@AutoConfigureMockMvc` trong Spring Boot kết hợp `spring-security-test` để request đi qua Security filter chain của application context. `httpBasic(...)` gắn Basic Authorization header; nó kiểm authentication **thông qua provider của Spring Security**, khác với `with(user(...))` hoặc `@WithMockUser` vốn nạp principal giả lập trực tiếp.

**Bộ test trên là ví dụ để biên dịch/chạy trong dự án được tạo theo các file đã mô tả; chưa phải bản ghi chạy thật trên máy của người đọc.** Nếu thay SecurityFilterChain, role hierarchy, authentication entry point hoặc MVC route, phải cập nhật kỳ vọng theo chính sách có chủ đích.

## 8. Tại sao phải tách test authorization khỏi test CSRF?

Xét `POST /api/orders` dành cho MEMBER. Có bốn tổ hợp quan trọng:

| Người gọi | CSRF token | Kỳ vọng | Lý do |
| --- | --- | --- | --- |
| MEMBER | Hợp lệ | **201** | Vượt cả CSRF lẫn rule MEMBER |
| MEMBER | Thiếu | **403** | `CsrfFilter` chặn, dù role đúng |
| MEMBER | Sai | **403** | CSRF validation thất bại |
| ADMIN | Hợp lệ | **403** | Không có ROLE_MEMBER trong demo |
| ANON | Hợp lệ | **401** | Không authenticated theo HTTP Basic |
| ANON | Thiếu | Thường **403** trước auth | Thiếu CSRF, không dùng để suy ra quyết định role |

Nếu chỉ viết:

~~~java
mvc.perform(post("/api/orders")
        .with(httpBasic("admin", "admin-pass")))
    .andExpect(status().isForbidden());
~~~

thì **test không chứng minh ADMIN bị từ chối vì thiếu ROLE_MEMBER**. Với CSRF bật, request không có CSRF cũng có thể bị 403. Test đúng cho câu hỏi role phải thêm `.with(csrf())`:

~~~java
mvc.perform(post("/api/orders")
        .with(httpBasic("admin", "admin-pass"))
        .with(csrf()))
    .andExpect(status().isForbidden());
~~~

Và thêm một test riêng:

~~~java
mvc.perform(post("/api/orders")
        .with(httpBasic("member", "member-pass")))
    .andExpect(status().isForbidden());
~~~

Các đoạn trên là **mảnh MockMvc test**; imports và thiết lập được cung cấp đầy đủ ở mục 7. Sự tách biệt giữa biến “đã authenticated”, “đủ role” và “CSRF hợp lệ” là nguyên tắc quan trọng để ma trận có ý nghĩa.

**CSRF tùy bối cảnh threat model:** ứng dụng dùng cookie/session dễ có credential được browser tự gửi; Spring Security mặc định bật CSRF trong Servlet. Với một API chỉ dùng bearer token đặt trong `Authorization` header, có thể có thiết kế khác, nhưng không tự tắt CSRF chỉ vì endpoint trả JSON hay dùng `permitAll()`. Quyết định phải dựa vào cách client xác thực, browser behavior và các điểm có thể bị gửi cross-site.

## 9. Anonymous, wrong role, disabled account và phiên hết hạn

### 9.1. Anonymous không giống principal có role rỗng

Spring Security có thể đặt anonymous authentication trong `SecurityContext` để phần code truy cập principal thống nhất; tuy nhiên `authenticated()` không coi anonymous là người dùng đã xác thực theo quy tắc authorization của Spring Security. Vì thế một request không có Basic credentials vào protected endpoint thường nhận **401**.

Một **authenticated user với roles rỗng** khác anonymous: `authenticated()` có thể cho phép vào `/api/me`, trong khi `hasRole("ADMIN")` sẽ từ chối 403. Nếu chỉ dùng `@WithMockUser(roles = {})`, hãy hiểu bạn đang tạo principal **đã xác thực không có role**, không phải anonymous.

### 9.2. Credentials sai

`httpBasic("member","wrong-pass")` kiểm password thông qua filter/provider và nhận **401** nếu không có cách xác thực khác. Nếu một test dùng `@WithMockUser` cùng lúc, principal mock có thể che việc Basic credentials sai hoặc tạo bối cảnh không mong muốn; tránh trộn hai cơ chế trong cùng test khi muốn khẳng định lỗi authentication.

### 9.3. Disabled hoặc locked user

Khi ứng dụng có `UserDetails.isEnabled()`, `isAccountNonLocked()`, external IdP hoặc local status, cần bổ sung hàng:

~~~text
GET /api/me | disabled account | 401 hoặc failure theo entry point đã thiết kế
~~~

Không suy diễn mọi account disabled đều được trả 403. Nhiều provider từ chối ngay tại **authentication** và gọi `AuthenticationEntryPoint` để trả 401/redirect. Với phiên đã tồn tại, thay đổi trạng thái account ở database không nhất thiết tự xóa SecurityContext; sản phẩm có rủi ro cao cần session revocation hoặc kiểm account status định kỳ.

### 9.4. Session hết hạn và role thay đổi

Với HTTP Basic của demo, credential được gửi trên mỗi request; không có “login session” theo nghĩa browser form login cần kiểm trong ma trận này. Khi chuyển sang session-based authentication, phải bổ sung các trạng thái: không cookie, cookie hợp lệ, cookie hết hạn, logout, session fixation protection và cookie cũ sau thu hồi quyền.

Role/permission trong SecurityContext có thể là ảnh chụp tại thời điểm login; thay đổi vai trò ở DB không tự cập nhật ngay phiên hiện có. Kiểm theo yêu cầu nghiệp vụ và chính sách thu hồi quyền.

## 10. Ma trận URL không thay object-level authorization

Cùng một endpoint GET được phép với MEMBER và ADMIN **không đảm bảo** user được đọc mọi order:

~~~text
GET /api/orders/42
  -> SecurityFilterChain:
       hasAnyRole("MEMBER", "ADMIN")
  -> OrderService:
       findById(42)
       check owner/tenant/status/ACL
       deny if not authorized for this exact order
~~~

Code demo không có database nên bỏ bước owner check; **không nên áp dụng nguyên trạng cho dữ liệu thật**. Khi bổ sung persistence, cần test ít nhất:

| Danh tính | Object | Kỳ vọng |
| --- | --- | --- |
| MEMBER Alice | Order của Alice | 200 |
| MEMBER Alice | Order của Bob cùng tenant | 403 hoặc 404 theo chính sách |
| MEMBER Alice | Order của tenant khác | 403 hoặc 404, không lộ metadata |
| ADMIN | Order hợp lệ trong tenant được cấp | Tùy quy tắc quản trị |
| ADMIN | Order ngoài tenant/phạm vi quản trị | Từ chối nếu không có quyền toàn cục |
| Anonymous | Bất kỳ order riêng | 401/redirect theo entry point |

**URL role** và **object-level authorization** phải đi cùng nhau. Nếu dùng `@PreAuthorize`, `PermissionEvaluator` hoặc một policy service như `orderAccess.canRead(authentication, orderId)`, hãy kiểm cả call qua Spring-managed proxy và request HTTP qua controller. `@PreAuthorize` không tự thực thi nếu thiếu `@EnableMethodSecurity` hoặc gọi `new Service()` ngoài proxy.

Khi dùng dữ liệu từ request body, **không cho client gửi owner/tenant rồi coi đó là dữ liệu đã xác minh**. Lấy identity từ Authentication đáng tin và đối chiếu với metadata server-side. Các test role mà không kiểm quyền trên từng đối tượng có thể bỏ sót IDOR/BOLA.

## 11. HEAD, OPTIONS, CORS preflight và các method ít gặp

### 11.1. HEAD

Một handler `@GetMapping` trong Spring MVC có thể hỗ trợ `HEAD` theo cơ chế của framework. Tuy vậy, **rule `HttpMethod.GET` của Spring Security không mặc nhiên là rule `HEAD`**. Nếu `HEAD /api/orders/42` cần cùng quyền đọc với GET, hãy định nghĩa chính sách rõ ràng và thêm hàng HEAD vào ma trận, kiểm status và không có body. Đừng chỉ thấy GET được bảo vệ rồi tin HEAD chắc chắn được bảo vệ đúng.

### 11.2. OPTIONS và CORS preflight

Browser có thể gửi preflight `OPTIONS` với `Origin`, `Access-Control-Request-Method` và `Access-Control-Request-Headers` trước một request cross-origin. Preflight thường **không mang credential đăng nhập**; khi bật CORS, Spring cần xử lý CORS **trước authentication decision**, nếu không có thể từ chối preflight dù actual request hợp lệ.

Ví dụ test preflight (chỉ là **mảnh MockMvc cần cấu hình CORS tương ứng**, không có trong ứng dụng minimal mục 6):

~~~java
mvc.perform(options("/api/orders")
        .header("Origin", "https://frontend.example.org")
        .header("Access-Control-Request-Method", "POST")
        .header("Access-Control-Request-Headers",
                "authorization,content-type"))
    .andExpect(status().isOk());
~~~

Không thêm kỳ vọng 200 này vào app demo hiện tại vì **demo chưa định nghĩa CORS**. Khi có `http.cors(Customizer.withDefaults())` và một `CorsConfigurationSource` bean với origin/method/header cho phép, mới kiểm preflight được xử lý như thiết kế. Một preflight hợp lệ **không** chứng minh actual `POST /api/orders` sẽ vượt qua role, CSRF hay validation nghiệp vụ. Ngược lại, chỉ `permitAll(HttpMethod.OPTIONS, "/**")` không tự sinh đủ `Access-Control-Allow-*` và không thay cấu hình CORS.

### 11.3. TRACE và phương thức khác

`TRACE` có thể bị container/gateway tắt trước Spring MVC; không tùy tiện giả định status từ app. Nếu một phương thức không được hỗ trợ, xác định tầng nào từ chối (proxy, servlet container, Spring Security, Spring MVC) và kiểm thông điệp/headers phù hợp. Một policy default deny giúp hạn chế mở method mới ngoài ý muốn.

### 11.4. Mở rộng matcher theo servlet path và proxy

Nếu app có `server.servlet.context-path`, nhiều `DispatcherServlet`, nhiều filter chains hoặc reverse proxy rewrite, hãy test URL mà Security thực nhận. `requestMatchers` trên Spring Security + MVC có ngữ nghĩa path matching phụ thuộc cách cấu hình servlet và matcher; không ghép bừa context path vào pattern hoặc suy đoán URL browser trùng request path bên trong. Với nhiều servlet, có thể cần `MvcRequestMatcher.Builder` và servlet path rõ ràng.

## 12. Tổ chức ma trận ở quy mô hệ thống

Với hàng trăm endpoint, làm thủ công một danh sách test khổng lồ có thể khó duy trì. Một chiến lược hiệu quả:

1. **Một nguồn chân lý cho hợp đồng:** ghi path template, method, authentication requirement, roles/permissions, owner/tenant rule, CSRF/CORS requirement và expected status.
2. **Nhóm endpoint theo chính sách:** public GET, user profile, member write, admin-only, cross-tenant, file download, webhooks, callbacks.
3. **Sinh test có kiểu dữ liệu rõ ràng:** như `Rule`/`Scenario` ở mục 7, để mỗi dòng chính sách được chạy với các identity tiêu chuẩn. Tránh một helper che mọi chi tiết của request.
4. **Kiểm cả negative cases:** anonymous, sai role, không có role, wrong tenant, revoked user, invalid/expired credentials, thiếu/sai CSRF, method không được khai báo.
5. **Kiểm actual handler result:** response body/header và thay đổi state/DB; chỉ so status 200 có thể bỏ sót việc trả dữ liệu không đúng người.
6. **Dùng integration tests khi cần:** WebTestClient cho WebFlux (khác stack), `MockMvc` cho MVC Servlet; với cookie/redirect/filter dispatch/proxy/TLS thật, dùng embedded server và HTTP client.
7. **Đặt test trong CI và review policy diff:** thay đổi security matcher, role hierarchy, handler mapping hoặc HTTP method phải gây test tương ứng thay đổi/cần đánh giá.

Ma trận có thể đặt trong file Markdown, YAML, CSV hoặc code Java. Nếu dùng nguồn dữ liệu bên ngoài test, bảo đảm parser kiểm giá trị hợp lệ (method, role, status), và đừng để nội dung untrusted có thể tiêm câu lệnh hoặc mở quyền. **Không cần test mọi tổ hợp hình thức vô nghĩa**, nhưng cần mỗi **rủi ro bảo mật riêng biệt** có đại diện rõ ràng, đặc biệt negative test.

### 12.1. Định nghĩa coverage có ý nghĩa

Một số thước đo hữu ích:

| Phạm vi | Câu hỏi kiểm chứng |
| --- | --- |
| Mỗi public endpoint | Anonymous có được phép đúng method đã chủ định? |
| Mỗi protected endpoint | Anonymous có bị từ chối đúng entry point? |
| Mỗi role rule | Người đúng role được phép và người sai role bị từ chối? |
| Mỗi unsafe method | Không/sai CSRF bị chặn khi CSRF áp dụng? |
| Mỗi path template | Có test với ID thật, ID sai định dạng, URL encoding và template khác? |
| Mỗi object ACL | Same-tenant vs cross-tenant, owner vs non-owner đã test? |
| Mỗi authentication type | Basic vs session vs bearer vs OIDC đã test đúng luồng riêng? |
| Mỗi internal dispatch | FORWARD/ERROR/ASYNC có policy tương ứng nếu ứng dụng dùng? |
| Mỗi API change | Thêm method mới có làm default-deny test cảnh báo không? |

Chỉ đếm số test không đủ: 100 test happy path vẫn có thể không phát hiện một method DELETE nhầm `permitAll()` hoặc một path download thiếu ownership check.

## 13. Những lỗi thường gặp khi kiểm thử endpoint theo ma trận

**Lỗi 1 — Test chỉ URL mà không chỉ method.** `GET /api/orders/42` đúng role nhưng `DELETE /api/orders/42` có rule khác. Ma trận phải có cột method.

**Lỗi 2 — Test wrong role ở POST nhưng không thêm CSRF.** 403 có thể do CsrfFilter, test vẫn “pass” dù authorization sai. Để kiểm role, cung cấp `with(csrf())`; thiếu/sai CSRF kiểm riêng.

**Lỗi 3 — Chỉ có một người dùng admin.** Nếu mọi test đều dùng quyền cao, không biết MEMBER có bị từ chối/cho phép đúng hay không. Test tối thiểu anonymous + role thấp + role cao, và role rỗng khi cần.

**Lỗi 4 — Coi ADMIN luôn bao hàm MEMBER.** Trong Spring Security, `ROLE_ADMIN` không tự thêm `ROLE_MEMBER`. Dùng `hasAnyRole` hoặc cấu hình role hierarchy có kiểm chứng nếu chính sách cần.

**Lỗi 5 — Dùng `@WithMockUser` để chứng minh password đúng.** Annotation dựng authentication sẵn. Khi test authentication thật, dùng credentials qua filter/provider (`httpBasic`, form login, token) và kiểm failure path.

**Lỗi 6 — Dùng HTTP 200 làm bằng chứng không lộ dữ liệu.** Role URL đúng chưa đủ; controller/service có thể trả đơn hàng của người khác. Thêm object-level ACL tests và kiểm body/state.

**Lỗi 7 — Đặt matcher rộng lên đầu.** `/api/**.authenticated()` trước rule member/admin làm rule cụ thể không tới lượt. Test role âm tính sẽ giúp bắt lỗi này.

**Lỗi 8 — Cho phép mọi HTTP method vì matcher không giới hạn method.** `requestMatchers("/api/orders/**").permitAll()` có thể ảnh hưởng GET/PUT/DELETE. Dùng `HttpMethod` khi quyền khác nhau theo thao tác.

**Lỗi 9 — Test route không tồn tại và kỳ vọng 404 mọi trường hợp.** `denyAll()` có thể từ chối ở Security trước khi MVC trả 404/405. Phải hiểu tầng nào quyết định response.

**Lỗi 10 — Trộn session và Basic trong cùng test mà không biết authentication nguồn nào được dùng.** Một SecurityContext dựng sẵn có thể che credentials sai. Cô lập từng loại identity và kiểm với request mới khi cần.

**Lỗi 11 — Bỏ qua HEAD/OPTIONS.** MVC có thể hỗ trợ HEAD dựa vào GET, browser dùng OPTIONS cho preflight; security matcher và CORS cần test riêng khi API dùng các cơ chế này.

**Lỗi 12 — Mở toàn bộ CSRF để làm test xanh.** CSRF là control độc lập, đặc biệt với cookie-backed browser sessions. Test phải phản ánh threat model, không xóa bảo vệ chỉ vì POST chưa mang token trong fixture.

**Lỗi 13 — Static assets hoặc `/error` bị `denyAll` ngoài ý muốn.** Nếu ứng dụng có trang login/static/error thực, lập danh sách public rõ ràng và test đúng route/dispatch; ví dụ tối giản chỉ có `/public/ping`.

**Lỗi 14 — Nhầm `hasRole` và `hasAuthority`.** `hasRole("MEMBER")` thường so `ROLE_MEMBER`, trong khi `hasAuthority("MEMBER")` đòi `MEMBER` đúng chuỗi. Nhất quán ở principal test và SecurityFilterChain.

**Lỗi 15 — Không kiểm method security.** Controller được bảo vệ URL nhưng service được gọi từ job/message listener có thể bỏ qua điều kiện quyền. Với nghiệp vụ nhạy cảm, test boundary service riêng và `@PreAuthorize` thích hợp.

**Lỗi 16 — Dùng test mock thay thế hoàn toàn kiểm triển khai thực.** MockMvc không tự chứng minh proxy routing, HTTPS, session cookie, OAuth2 callback hoặc CORS browser behavior. Bổ sung integration tests đúng tầng.

## 14. Bài tập thực hành

**Bài 1.** Với rule `GET /api/orders/* -> hasAnyRole(MEMBER, ADMIN)` và `DELETE /api/orders/* -> hasRole(ADMIN)`, anonymous, MEMBER, ADMIN nhận trạng thái gì khi đã thỏa các điều kiện khác?  
**Đáp án:** GET: 401/200/200. DELETE (có CSRF hợp lệ): 401/403/204 trong demo.

**Bài 2.** Member gọi `POST /api/orders` nhưng không có CSRF token, server trả 403. Có kết luận member thiếu quyền POST được không?  
**Không.** Cần kiểm với CSRF hợp lệ để tách authorization khỏi CSRF.

**Bài 3.** Một user có đúng `ROLE_ADMIN` có vào route `hasRole("MEMBER")` không?  
**Không mặc định.** Chỉ được nếu user có `ROLE_MEMBER` hoặc hệ thống định nghĩa role hierarchy/authorization khác.

**Bài 4.** Vì sao `POST /admin/metrics` bị từ chối dù `GET /admin/metrics` cho ADMIN?  
**Vì** rule chỉ match `HttpMethod.GET`; POST không được khai báo và rơi vào deny-all.

**Bài 5.** `with(user("alice").roles("MEMBER"))` có kiểm password của Alice không?  
**Không.** Đây là request post-processor tạo user đã xác thực. `httpBasic("alice", "password")` mới đưa credentials vào filter Basic tương ứng để kiểm.

**Bài 6.** HTTP Basic anonymous gặp protected route trả 401, nhưng ứng dụng form login cùng rule trả 302 đến login. Test nào sai?  
**Không nhất thiết có test sai.** Entry point khác nhau nên response khác; cập nhật ma trận theo phương thức xác thực của ứng dụng.

**Bài 7.** Cùng role `MEMBER`, Alice truy cập order của Bob. Ma trận URL với role đã pass; cần gì thêm?  
**Object-level authorization:** kiểm owner/tenant/ACL từ dữ liệu server-side và test case bị từ chối.

**Bài 8.** Browser gửi CORS preflight OPTIONS không có cookie; test POST endpoint đã có `hasRole("MEMBER")`. Có nên buộc preflight có MEMBER không?  
**Không.** CORS preflight cần xử lý trước authentication khi bật CORS; actual POST vẫn phải kiểm authentication, authorization và CSRF nếu áp dụng.

**Bài 9.** Một test `@WithMockUser(roles = {})` nhận 200 ở `/api/me`. Có phải anonymous vừa được phép?  
**Không.** Principal mock vẫn authenticated dù không có role; `authenticated()` khác `hasRole`.

**Bài 10.** Vì sao một test status 204 của DELETE chưa chứng minh dữ liệu thực đã xóa?  
**Vì** handler demo chỉ trả status, không có persistence. Kiểm business state/transaction và authorization side effect trong integration test.

## 15. Checklist triển khai một ma trận endpoint đáng tin

- **Kiểm kê** method và path thực tế của mọi API; chú ý cùng URL nhưng GET/POST/PATCH/PUT/DELETE khác quyền.
- **Định nghĩa principal states**: anonymous, authenticated role thấp/role cao, sai credential, không role, disabled/revoked/expired session khi phù hợp.
- **Mô hình hóa policy**: permitAll, authenticated, role/authority, ownership/tenant và default deny. Đặt matcher cụ thể trước matcher rộng.
- **Xác định response contract**: 200/201/204 thành công; 401/302 chưa login tùy entry point; 403 thiếu quyền/CSRF; 404/405 tùy nơi từ chối.
- **Tách biến kiểm thử**: cấp CSRF hợp lệ khi đo role cho unsafe method; kiểm missing/invalid CSRF riêng; không dùng 403 làm bằng chứng thiếu role nếu request cũng thiếu CSRF.
- **Chạy data-driven tests**: tối thiểu anonymous + các role liên quan cho từng endpoint, có assertion response/body/state thay vì chỉ status.
- **Test negative methods**: method chưa khai báo, URL mới, path encoding, HEAD/OPTIONS, preflight khi bật CORS; không tự mở rộng public endpoint.
- **Kiểm quyền trên đối tượng**: chủ sở hữu, tenant, resource status, data filtering và method security tại service.
- **Cô lập test auth**: `httpBasic`/form login/bearer test xác thực thật; `@WithMockUser` hoặc `with(user())` dùng cho policy-only tests.
- **Chạy trong CI** và duy trì ma trận khi thêm endpoint, đổi role hoặc tách security filter chains; integration test container/proxy/session khi có nhu cầu.

**Kết luận:** Kiểm thử HTTP an toàn không phải chỉ kiểm một URL với một tài khoản đủ quyền. Ma trận **endpoint × HTTP method × trạng thái đăng nhập × role × CSRF** cho thấy rõ **ai được làm gì, trong điều kiện nào**, và giúp phát hiện thiếu rule, matcher sai thứ tự hoặc lỗ hổng authorization. Với dữ liệu thật, phải mở rộng ma trận đến **quyền sở hữu từng đối tượng**, không chỉ dựa trên tên đường dẫn.
