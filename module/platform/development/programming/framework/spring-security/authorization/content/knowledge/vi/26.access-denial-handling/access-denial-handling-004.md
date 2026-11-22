# AccessDeniedHandler với người không có quyền

> Phạm vi: **Spring Security trên Servlet/Spring MVC**, trong nhóm **Xử lý từ chối**. Trọng tâm là tình huống người dùng đã xác thực nhưng **không đủ quyền** truy cập tài nguyên. Ví dụ thực hành dùng Java 17, Spring Boot 3.5.x và cấu hình `SecurityFilterChain` hiện đại.

## 1. Vấn đề cần giải quyết

Giả sử hệ thống có endpoint `GET /api/admin/report` chỉ dành cho quản trị viên. Alice đã đăng nhập thành công với vai trò `READER`, nhưng cố gọi endpoint này. Spring Security phải ngăn truy cập và gửi một phản hồi dễ hiểu, nhất quán cho client, chẳng hạn HTTP **403 Forbidden** cùng mã lỗi JSON `ACCESS_DENIED`. Đó là công việc của **`AccessDeniedHandler`**.

Cần phân biệt hai câu hỏi bảo mật:

- **Authentication (xác thực):** Bạn là ai? Danh tính/phiên/token có hợp lệ không?
- **Authorization (phân quyền):** Danh tính đó có quyền thực hiện hành động trên tài nguyên này không?

`AccessDeniedHandler` **không quyết định ai được phép truy cập**. Quy tắc như `hasRole("ADMIN")`, `hasAuthority("report:read")` hoặc `@PreAuthorize` quyết định việc đó; handler chỉ **chuyển một lần từ chối quyền thành phản hồi HTTP** phù hợp.

### Phân biệt 401 và 403

| Tình huống | Thành phần thường xử lý | Kết quả điển hình |
|---|---|---|
| Chưa xác thực, truy cập tài nguyên cần đăng nhập | `AuthenticationEntryPoint` | HTTP 401 với HTTP Basic/Bearer; hoặc 302 tới trang đăng nhập với form login |
| Đã xác thực với `ROLE_READER`, cần `ROLE_ADMIN` | `AccessDeniedHandler` | HTTP 403 |
| Có đủ quyền | Luồng xử lý request bình thường | HTTP 2xx (tùy controller) |
| Sai mật khẩu/token không hợp lệ | Cơ chế xác thực và entry point | Thường HTTP 401; phụ thuộc loại xác thực |
| Request bị chặn bởi CSRF/CORS hoặc filter khác | Bộ phận tạo ra lỗi tương ứng | Có thể HTTP 403, nhưng **không nhất thiết** do handler cấu hình ở đây |

Vì vậy, **không đổi thiếu quyền thành 401** chỉ để đồng bộ JSON; 401 biểu thị cần xác thực hoặc xác thực lại. Trường hợp remember-me hoặc mức xác thực chưa đủ có thể được Spring Security yêu cầu xác thực thêm thay vì đi thẳng tới handler.

## 2. `AccessDeniedHandler` nằm ở đâu trong luồng Servlet?

Luồng khái quát của một request bảo vệ bằng `authorizeHttpRequests`:

```text
Client
  |
  v
SecurityFilterChain
  |-- các filter xác thực (tùy HTTP Basic, form, Bearer, ...)
  |-- ExceptionTranslationFilter
  |       |
  |       +-- gọi các filter phía sau
  |                   |
  |                   +-- AuthorizationFilter
  |                          |
  |                          +-- đủ quyền --> Controller --> response
  |                          |
  |                          +-- thiếu quyền --> AccessDeniedException
  |
  +-- ExceptionTranslationFilter bắt lỗi phù hợp:
         |-- chưa/không đủ xác thực --> AuthenticationEntryPoint
         +-- đã xác thực, thiếu quyền --> AccessDeniedHandler --> 403
```

Trình tự cần hiểu:

1. Filter xác thực thiết lập `Authentication` trong `SecurityContext` khi có thông tin đăng nhập hợp lệ.
2. `AuthorizationFilter` áp dụng rule khớp request. Nếu bị từ chối, nó phát sinh lỗi thuộc họ `AccessDeniedException`.
3. `ExceptionTranslationFilter` bắt `AccessDeniedException` hoặc `AuthenticationException` được ném từ phần chuỗi filter phía sau nó. Bộ lọc này **không tự kiểm tra quyền**; nó lựa chọn cách phản hồi.
4. Khi người gọi đã được xác thực thích hợp nhưng thiếu quyền, `ExceptionTranslationFilter` gọi `AccessDeniedHandler.handle(...)`. Với anonymous/chưa xác thực hoặc trường hợp cần nâng mức xác thực, nó có thể dùng `AuthenticationEntryPoint`.
5. Handler đặt status, header, body hoặc chuyển tiếp tới trang lỗi. Request bị từ chối **không được tiếp tục vào nghiệp vụ cần quyền**.

Giao diện chính nằm trong package `org.springframework.security.web.access`:

```java
public interface AccessDeniedHandler {
    void handle(
        jakarta.servlet.http.HttpServletRequest request,
        jakarta.servlet.http.HttpServletResponse response,
        org.springframework.security.access.AccessDeniedException exception
    ) throws java.io.IOException, jakarta.servlet.ServletException;
}
```

- `request`: dữ liệu HTTP request để xác định tài nguyên đang truy cập.
- `response`: nơi thiết lập HTTP status, `Content-Type` và nội dung trả về.
- `exception`: lỗi từ chối quyền. Có thể ghi log an toàn ở phía server nhưng **không trả nguyên stack trace hay thông tin rule nội bộ** ra ngoài.

Nếu không tùy biến, `AccessDeniedHandlerImpl` thường gửi lỗi 403 bằng `sendError`; cũng hỗ trợ forward đến trang lỗi được cấu hình. Khi API cần một cấu trúc JSON ổn định, ta có thể triển khai handler riêng.

## 3. Ví dụ chạy được: trả JSON 403 cho người không có quyền

Dự án mẫu dùng HTTP Basic cho dễ quan sát ba trường hợp: chưa đăng nhập, đăng nhập thiếu quyền và đăng nhập đủ quyền. HTTP Basic và mật khẩu trong bộ nhớ **chỉ dùng để minh họa**, không dùng làm phương án lưu mật khẩu trong sản phẩm thực tế.

### 3.1. Cấu trúc và dependencies

```text
security-denied-demo/
|-- pom.xml
|-- src/main/java/com/example/securitydemo/
|   |-- SecurityDemoApplication.java
|   |-- SecurityConfig.java
|   |-- JsonAccessDeniedHandler.java
|   +-- DemoController.java
+-- src/test/java/com/example/securitydemo/
    +-- AuthorizationResponseTest.java
```

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>security-denied-demo</artifactId>
    <version>1.0.0</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.6</version>
        <relativePath/>
    </parent>
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

Lưu ý Spring Security 6+ dùng Servlet API thuộc **`jakarta.servlet`**, không còn `javax.servlet`. Với dự án đã có Spring Boot và dependencies tương đương, chỉ cần áp dụng các lớp Java bên dưới.

### 3.2. Khởi động ứng dụng

`src/main/java/com/example/securitydemo/SecurityDemoApplication.java`:

```java
package com.example.securitydemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityDemoApplication.class, args);
    }
}
```

### 3.3. Handler tùy biến phản hồi 403

`src/main/java/com/example/securitydemo/JsonAccessDeniedHandler.java`:

```java
package com.example.securitydemo;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import org.springframework.http.MediaType;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.web.access.AccessDeniedHandler;
import org.springframework.stereotype.Component;

@Component
public class JsonAccessDeniedHandler implements AccessDeniedHandler {
    private final ObjectMapper objectMapper;

    public JsonAccessDeniedHandler(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @Override
    public void handle(
            HttpServletRequest request,
            HttpServletResponse response,
            AccessDeniedException exception) throws IOException {
        response.setStatus(HttpServletResponse.SC_FORBIDDEN);
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        response.setHeader("Cache-Control", "no-store");

        Map<String, String> body = Map.of(
                "code", "ACCESS_DENIED",
                "message", "Bạn không có quyền truy cập tài nguyên này",
                "path", request.getRequestURI()
        );
        objectMapper.writeValue(response.getOutputStream(), body);
    }
}
```

Giải thích các lựa chọn:

- `SC_FORBIDDEN` chính là HTTP **403**; không trả 200 kèm lỗi trong body.
- `Content-Type: application/json` và UTF-8 giúp client xử lý tiếng Việt.
- `ObjectMapper` do Spring Boot cấp bảo đảm JSON được escape đúng cách; `Map.of` không cam kết thứ tự các trường JSON, nên client cần kiểm tra **tên trường**, không phụ thuộc thứ tự.
- `Cache-Control: no-store` giúp tránh lưu bộ nhớ đệm đối với response từ chối có thông tin request.
- Handler **không gọi `filterChain.doFilter`**, không chuyển sang controller và không viết nội dung hai lần.
- `exception` được nhận theo interface, nhưng ví dụ cố ý không đưa chi tiết exception ra client. Trong hệ thống thật có thể ghi log mã sự kiện/correlation ID ở server.

### 3.4. Cấu hình rule và gắn handler vào SecurityFilterChain

`src/main/java/com/example/securitydemo/SecurityConfig.java`:

```java
package com.example.securitydemo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            JsonAccessDeniedHandler accessDeniedHandler) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .exceptionHandling(ex -> ex
                .accessDeniedHandler(accessDeniedHandler)
            );

        return http.build();
    }

    @Bean
    UserDetailsService users() {
        UserDetails reader = User.withUsername("reader")
                .password("{noop}reader123")
                .roles("READER")
                .build();
        UserDetails admin = User.withUsername("admin")
                .password("{noop}admin123")
                .roles("ADMIN")
                .build();
        return new InMemoryUserDetailsManager(reader, admin);
    }
}
```

`hasRole("ADMIN")` yêu cầu authority tên **`ROLE_ADMIN`** theo quy ước prefix. Vì thế `roles("ADMIN")` của admin phù hợp, còn `roles("READER")` không đủ quyền. Nếu hệ thống gán authority theo chuỗi chi tiết như `report:read` thì dùng `hasAuthority("report:read")`. **Đừng viết `hasRole("ROLE_ADMIN")`** với cấu hình prefix mặc định, vì sẽ gắn tiền tố `ROLE_` lần nữa.

Cấu hình `.exceptionHandling(ex -> ex.accessDeniedHandler(...))` đặt handler cho chuỗi bảo mật này. Nó không thay thế phần `authorizeHttpRequests`, không tự động tạo quyền và không biến lỗi xác thực thành lỗi phân quyền.

### 3.5. Controller để quan sát kết quả

`src/main/java/com/example/securitydemo/DemoController.java`:

```java
package com.example.securitydemo;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {
    @GetMapping("/api/admin/report")
    public Map<String, String> report() {
        return Map.of("report", "ready");
    }

    @GetMapping("/api/profile")
    public Map<String, String> profile() {
        return Map.of("profile", "visible");
    }
}
```

Chỉ có admin được vào `/api/admin/report`. Cả reader và admin, sau khi xác thực, đều được vào `/api/profile`.

### 3.6. Chạy và thử qua HTTP

Yêu cầu JDK 17+ và Maven 3.9+. Chạy từ thư mục chứa `pom.xml`:

```bash
mvn spring-boot:run
```

Mở terminal khác (trên PowerShell Windows dùng `curl.exe` nếu `curl` được ánh xạ sang lệnh khác):

```bash
# 1. Chưa đăng nhập
curl -i http://localhost:8080/api/admin/report

# 2. Đã đăng nhập với ROLE_READER, nhưng endpoint cần ROLE_ADMIN
curl -i -u reader:reader123 http://localhost:8080/api/admin/report

# 3. Đăng nhập với ROLE_ADMIN
curl -i -u admin:admin123 http://localhost:8080/api/admin/report

# 4. Reader được phép xem profile
curl -i -u reader:reader123 http://localhost:8080/api/profile
```

Kết quả cần quan sát:

| Request | Status dự kiến | Nội dung nổi bật |
|---|---|---|
| Không có credentials tới report | `401 Unauthorized` | HTTP Basic entry point có thể gửi header `WWW-Authenticate` |
| Reader tới report | `403 Forbidden` | JSON có `code = ACCESS_DENIED`, `path = /api/admin/report` |
| Admin tới report | `200 OK` | JSON chứa `"report":"ready"` |
| Reader tới profile | `200 OK` | JSON chứa `"profile":"visible"` |

Ví dụ **body** của lần gọi thứ hai (thứ tự khóa có thể khác):

```json
{
  "code": "ACCESS_DENIED",
  "message": "Bạn không có quyền truy cập tài nguyên này",
  "path": "/api/admin/report"
}
```

Nếu dùng form login thay vì HTTP Basic, truy cập ẩn danh thường được chuyển sang trang đăng nhập bằng 302; đừng kiểm thử cứng rằng mọi ứng dụng Spring Security đều trả 401 cho anonymous.

## 4. Kiểm thử tự động: xác nhận đúng nhánh 401, 403 và 200

Tạo `src/test/java/com/example/securitydemo/AuthorizationResponseTest.java`:

```java
package com.example.securitydemo;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class AuthorizationResponseTest {
    @Autowired
    MockMvc mvc;

    @Test
    void anonymousIsChallenged() throws Exception {
        mvc.perform(get("/api/admin/report"))
           .andExpect(status().isUnauthorized());
    }

    @Test
    void readerGetsCustomForbiddenBody() throws Exception {
        mvc.perform(get("/api/admin/report")
                .with(user("reader").roles("READER")))
           .andExpect(status().isForbidden())
           .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
           .andExpect(jsonPath("$.code").value("ACCESS_DENIED"))
           .andExpect(jsonPath("$.path").value("/api/admin/report"));
    }

    @Test
    void adminCanReadReport() throws Exception {
        mvc.perform(get("/api/admin/report")
                .with(user("admin").roles("ADMIN")))
           .andExpect(status().isOk())
           .andExpect(jsonPath("$.report").value("ready"));
    }

    @Test
    void readerCanReadProfile() throws Exception {
        mvc.perform(get("/api/profile")
                .with(user("reader").roles("READER")))
           .andExpect(status().isOk());
    }
}
```

Chạy:

```bash
mvn test
```

Kiểm thử `with(user(...))` tạo principal giả lập cho request MockMvc và **không kiểm tra mật khẩu trong `UserDetailsService`**; do đó kiểm thử này xác nhận **phân quyền + định dạng response**, còn hai lệnh `curl -u` ở trên kiểm tra cả luồng HTTP Basic thực tế. Nếu chạy MockMvc theo kiểu `standaloneSetup`, phải tích hợp filter chain Spring Security; `@SpringBootTest` + `@AutoConfigureMockMvc` trong ví dụ đã bao gồm tích hợp đó.

## 5. Khi nào áp dụng và cách mở rộng

**API JSON:** Tùy biến `AccessDeniedHandler` khi frontend/mobile cần cùng một schema lỗi để hiển thị thông báo, điều hướng hoặc ghi nhận mã sự kiện. Duy trì status 403 và mã lỗi ổn định; tách thông báo hiển thị khỏi thông tin kỹ thuật nội bộ.

**Ứng dụng HTML:** `AccessDeniedHandlerImpl` có thể được cấu hình chuyển tiếp đến trang lỗi (giữ trạng thái 403). Chọn forward/HTML khi trình duyệt cần một trang thông báo, thay vì bắt mọi request nhận JSON.

**Phân quyền theo phương thức:** Thêm `@EnableMethodSecurity` rồi dùng `@PreAuthorize("hasAuthority('report:read')")` trên Spring-managed method nếu quyền phụ thuộc nghiệp vụ hoặc dữ liệu. Khi lời gọi đi qua luồng web bảo mật phù hợp, lỗi thiếu quyền có thể được chuyển thành HTTP 403; lời gọi method ngoài HTTP không có `HttpServletResponse` để `AccessDeniedHandler` xử lý. Cần kiểm thử cả lớp service và endpoint.

**Nhiều `SecurityFilterChain`:** Mỗi chain có phạm vi `securityMatcher(...)` và cấu hình riêng. Handler đăng ký ở chain A không tự động áp dụng cho request đi vào chain B; cần tìm chain thực sự khớp endpoint đang kiểm thử.

**OAuth2 Resource Server/Bearer token:** Trường hợp token hợp lệ nhưng scope không đủ thường cần phản hồi 403 phù hợp giao thức và header `WWW-Authenticate`, có thể chứa `insufficient_scope`. Spring Security có `BearerTokenAccessDeniedHandler` phục vụ yêu cầu đó. Trước khi thay bằng handler JSON tùy biến, kiểm tra và giữ nguyên các header/chỉ dẫn chuẩn mà client OAuth2 cần; handler JSON của ví dụ HTTP Basic không bao quát toàn bộ hành vi Bearer token.

## 6. Lỗi phổ biến và cách xác định nguyên nhân

| Triệu chứng | Nguyên nhân cần kiểm tra | Hướng xử lý |
|---|---|---|
| Anonymous trả 401, handler 403 không chạy | `AuthenticationEntryPoint` xử lý đúng nhánh | Kiểm thử bằng tài khoản **đã xác thực** nhưng thiếu quyền |
| Đã đăng nhập vẫn vào được tài nguyên | Rule match sai, rule rộng đặt trước hoặc authority khác dự kiến | Rà soát `requestMatchers`, thứ tự rule, `hasRole`/`hasAuthority` và authority thực |
| Có 403 nhưng body không phải JSON tự viết | Request vào chain khác; lỗi đến từ CSRF/CORS/filter khác; response đã bị commit | Xác định filter/chain phát sinh lỗi, kiểm tra log và test đúng đường dẫn |
| `@RestControllerAdvice` không bắt được lỗi từ filter | Lỗi bảo mật có thể xuất hiện ngoài vòng xử lý exception MVC | Cấu hình `exceptionHandling` ở `HttpSecurity` thay vì chỉ dựa vào controller advice |
| Phản hồi 500 khi tùy biến handler | JSON serializer ném lỗi hoặc response đã bắt đầu ghi | Viết status/header trước body; không ghi lặp hoặc gọi `sendError` sau khi đã xuất JSON |
| Role "ADMIN" vẫn nhận 403 | Nhầm `ROLE_ADMIN` với `ADMIN` hoặc quyền thực tế không được map | Kiểm tra danh sách `GrantedAuthority`, tránh lặp prefix |
| API POST nhận 403 dù quyền đúng | Có thể thiếu CSRF token trong ứng dụng dùng session/cookie | Phân biệt CSRF với phân quyền; cấu hình CSRF theo cơ chế xác thực và mô hình đe dọa |
| Handler không được gọi từ custom filter | Exception phát sinh trước `ExceptionTranslationFilter` hoặc bị bắt ở nơi khác | Kiểm tra vị trí filter và phạm vi xử lý exception; không giả định mọi 403 đi qua một handler |

Một số nguyên tắc vận hành:

1. **Chặn ở rule, trình bày ở handler:** không dùng handler để nới quyền, thay đổi `Authentication` hay tiếp tục request đã bị từ chối.
2. **Không rò rỉ dữ liệu:** trả mã lỗi chung; không gửi exception message, stack trace, tên policy nhạy cảm, token hay danh sách vai trò đang thiếu. Tránh đưa URI/query có thông tin nhạy cảm vào response; trường `path` trong ví dụ chỉ là path thuần.
3. **Giữ đúng HTTP semantics:** 403 khi đã xác thực nhưng thiếu quyền; entry point quyết định cách yêu cầu đăng nhập/xác thực. Với Bearer cần bảo toàn giao thức OAuth2.
4. **Đo cả nhánh thành công:** một test chỉ kiểm tra 403 không chứng minh user đúng quyền vẫn vào được. Luôn có test ít nhất 401/403/200 trong bối cảnh ứng dụng áp dụng.
5. **Không tắt CSRF để “sửa” lỗi 403 một cách máy móc:** các request thay đổi trạng thái dùng session/cookie thường vẫn cần CSRF protection.
6. **Tách thông điệp kỹ thuật và thông điệp người dùng:** logging/monitoring có correlation ID, client nhận nội dung không tiết lộ nội bộ.

## 7. Checklist tự đánh giá

- [ ] Xác định được **ai** thiếu quyền (đã xác thực) và rule **nào** từ chối request.
- [ ] Phân biệt được `AuthenticationEntryPoint` và `AccessDeniedHandler`.
- [ ] Hiểu `ExceptionTranslationFilter` chỉ chuyển lỗi thành HTTP response; `AuthorizationFilter` mới thực thi rule request.
- [ ] Đăng ký handler trong đúng `SecurityFilterChain` bằng `exceptionHandling(...)`.
- [ ] JSON 403 có status, charset và nội dung phù hợp; không lộ thông tin nhạy cảm.
- [ ] Test 401 (anonymous), 403 (reader thiếu quyền), 200 (admin đủ quyền).
- [ ] Kiểm tra thêm CSRF, Bearer token hoặc method security nếu ứng dụng dùng các cơ chế này.

## Tài liệu chính thức

- Spring Security — [Servlet architecture và ExceptionTranslationFilter](https://docs.spring.io/spring-security/reference/servlet/architecture.html).
- Spring Security — [`AccessDeniedHandler` API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/access/AccessDeniedHandler.html).
- Spring Security — [Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html).
- Spring Security — [Spring MVC Test và giả lập user](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html).
- Spring Security — [Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html).
