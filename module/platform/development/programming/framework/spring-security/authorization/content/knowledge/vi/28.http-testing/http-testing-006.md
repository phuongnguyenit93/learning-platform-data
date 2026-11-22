# Kiểm thử thứ tự matcher, wildcard, servlet path và đường dẫn sát biên

> **Phạm vi:** Spring Security **Servlet**, lớp phân quyền HTTP qua `SecurityFilterChain` và `authorizeHttpRequests`. Mục tiêu của bài là chứng minh bằng test rằng **đúng request được cho phép, request sát biên bị chặn**, và việc đổi thứ tự matcher không tạo lỗ hổng. Ví dụ chính dùng Java 17+, Spring Boot 3.5.x và Spring Security 6.5.x; các API `PathPatternRequestMatcher` được sử dụng cũng có trong Spring Security 7.x.

## 1. Sau bài này cần kiểm chứng được điều gì?

Một cấu hình phân quyền nhìn có vẻ hợp lý vẫn có thể sai vì một matcher quá rộng được khai báo trước matcher hẹp, nhầm đường dẫn của `DispatcherServlet`, nhầm ý nghĩa `*`/`**`, hoặc chỉ thử đúng một URL “đẹp”. Một bộ kiểm thử tốt phải trả lời được:

1. **Chuỗi filter nào thực sự nhận request?** `securityMatcher` chọn `SecurityFilterChain`; nếu có nhiều chuỗi, thứ tự chuỗi cũng quan trọng.
2. **Quy tắc nào thắng bên trong chuỗi?** `AuthorizationFilter` xét các cặp `requestMatchers(...).rule(...)` theo thứ tự khai báo và dùng **quy tắc khớp đầu tiên**.
3. **Matcher dựa trên những phần nào của request?** HTTP method, đường dẫn sau context path, servlet path, path segments; query string không tự trở thành một phần của path pattern.
4. **Giới hạn đường dẫn có được bảo vệ?** Cần thử đường dẫn gốc, con, anh em có tiền tố gần giống, dấu `/` cuối, khác hoa/thường, method khác, segment thừa, URL mã hóa, và servlet path khác cấu hình.
5. **Status code phản ánh đúng nguyên nhân?** `200` do request được phép và controller xử lý; `401` thường là chưa xác thực với HTTP Basic; `403` thường là bị từ chối hoặc thiếu CSRF; `404` có thể chỉ là không có handler. Không suy ra “an toàn” chỉ từ một status code.

## 2. Hai tầng matching, hai loại thứ tự

Luồng Servlet cần kiểm thử:

```text
HTTP request
    |
    v
FilterChainProxy
    |-- SecurityFilterChain @Order(1), securityMatcher(...) ? --+
    |-- SecurityFilterChain @Order(2), securityMatcher(...) ? --+--> chọn chuỗi khớp đầu tiên
    |-- Chuỗi mặc định khớp mọi request ? ----------------------+
    |
    v
AuthorizationFilter trong chuỗi được chọn
    |-- requestMatchers(matcher cụ thể).hasAuthority(...)
    |-- requestMatchers(matcher rộng hơn).authenticated()
    |-- anyRequest().denyAll()
    +--> chỉ áp dụng rule khớp đầu tiên
    |
    v
Cho phép -> DispatcherServlet -> controller, hoặc từ chối -> security response
```

- `http.securityMatcher(...)` xác định **phạm vi chuỗi filter**. `http.authorizeHttpRequests(...).requestMatchers(...)` xác định **quyền truy cập trong chuỗi đã được chọn**. Một request không khớp bất kỳ `SecurityFilterChain` nào có thể đi qua mà không chịu các filter của Spring Security; `anyRequest().denyAll()` trong chuỗi khác không cứu được trường hợp đó.
- Với **nhiều chuỗi**, dùng `@Order` rõ ràng cho chuỗi chuyên biệt trước, và một chuỗi cuối bao phủ phần còn lại nếu muốn chặn mặc định. Trong **mỗi chuỗi**, viết rule hẹp trước rule rộng; đặt `anyRequest()` sau cùng.
- `hasRole("ADMIN")` kiểm tra authority `ROLE_ADMIN` theo quy ước mặc định; `hasAuthority("admin")` kiểm tra đúng chuỗi `admin`. Test phải tạo đúng authority đang dùng, không trộn lẫn hai kiểu.
- Xác thực, CSRF, firewall, CORS, controller và method security có thể tác động kết quả. Test authorization cần tách các yếu tố này để tránh kết luận nhầm.

### Thí dụ sai thứ tự

```java
// SAI: mọi GET /admin/** đi qua permitAll, kể cả /admin/audit.
.authorizeHttpRequests(a -> a
    .requestMatchers(HttpMethod.GET, "/admin/**").permitAll()
    .requestMatchers(HttpMethod.GET, "/admin/audit").hasRole("ADMIN")
    .anyRequest().denyAll()
)
```

```java
// ĐÚNG: ngoại lệ cụ thể đứng trước wildcard rộng.
.authorizeHttpRequests(a -> a
    .requestMatchers(HttpMethod.GET, "/admin/audit").hasRole("ADMIN")
    .requestMatchers(HttpMethod.GET, "/admin/**").authenticated()
    .anyRequest().denyAll()
)
```

Hai đoạn trên là **trích đoạn cấu hình**, thay cho phần `authorizeHttpRequests` của một `HttpSecurity`, không phải chương trình Java độc lập. Đừng đặt một rule `permitAll` rộng ở đầu rồi trông chờ matcher cụ thể phía sau sẽ “ghi đè”.

## 3. Wildcard và đường dẫn sát biên

Ví dụ dưới đây dùng `PathPatternRequestMatcher` và parser mặc định (`PathPatternParser.defaultInstance`). Đừng mặc định mọi ứng dụng đều dùng cùng một engine: ứng dụng cũ có thể dùng `AntPathRequestMatcher`, `MvcRequestMatcher`, hoặc regex. Khi nâng cấp, hãy cố định matcher được dùng và chạy lại toàn bộ bảng biên.

| Pattern | Có thể khớp | Không nên giả định là khớp |
| --- | --- | --- |
| `/admin` | Chính xác `/admin` | `/admin/users`, `/administrator` |
| `/admin/*` | Một segment ngay dưới `/admin`, ví dụ `/admin/users` | `/admin/users/7` |
| `/admin/**` | `/admin` và các đường dẫn con như `/admin/users/7` | `/administrator` |
| `/reports/{id}` | Một segment tại `{id}`, ví dụ `/reports/42` | `/reports/42/items` |
| `/assets/*.css` | Một segment tên file phù hợp trong `/assets` | `/assets/css/site.css` |
| `/api/?` | Đúng một ký tự trong segment cuối, ví dụ `/api/a` | `/api/ab` |

`*` khớp trong **một segment**, `?` khớp một ký tự, `**` khớp nhiều segment (với `PathPattern`, `**` phải ở cuối pattern). `{id}` đặt tên segment và có thể trích giá trị; nó không tự chứng minh người dùng có quyền xem `id` đó. Nếu `/admin/**` có thể bao phủ cả `/admin`, không cần suy luận rằng `/admin/*` cũng tương đương.

Các cặp dễ nhầm cần test riêng:

- `/admin` ↔ `/admin/`: dấu gạch chéo cuối có thể thay đổi match; parser mặc định hiện đại không tự coi hai URL là một.
- `/admin/item` ↔ `/admin/item/extra`: một segment so với hai segment.
- `/admin/item` ↔ `/administrator/item`: tiền tố giống nhau không có nghĩa nằm trong cùng nhánh.
- `/reports/42` ↔ `/Reports/42`: parser mặc định phân biệt hoa/thường; đừng dựa vào hành vi này nếu ứng dụng tùy chỉnh parser.
- `GET /reports/42` ↔ `POST /reports/42`: cùng path nhưng khác method; matcher có ràng buộc `HttpMethod` sẽ phân biệt.
- `/reports/42?view=full` ↔ `/reports/42`: query string không đổi path pattern; nếu quyền phụ thuộc query, phải thiết kế logic hoặc matcher riêng.
- `/reports/42` ↔ `/reports/%34%32` và `/reports/%2F`: URL encoding/decoding, proxy, servlet container và `HttpFirewall` quyết định request được chuẩn hóa hay từ chối như thế nào. Không hard-code một kỳ vọng 200/403 cho mọi môi trường; kiểm chứng an toàn ở ranh giới triển khai thực.

## 4. Ví dụ hoàn chỉnh: phân quyền báo cáo theo path và HTTP method

Dùng project Spring Boot **Servlet MVC**, Java 17+, với các dependency `spring-boot-starter-web`, `spring-boot-starter-security`, `spring-boot-starter-test` và `spring-security-test`. Nếu dùng Gradle Groovy, phần `dependencies` tương ứng là:

```groovy
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

Đây là **phần dependencies cho dự án đã có plugin Spring Boot và khai báo repository/dependency management**; nó không thay thế toàn bộ `build.gradle`.

**`src/main/java/example/authorization/AuthorizationDemoApplication.java`**

```java
package example.authorization;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthorizationDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthorizationDemoApplication.class, args);
    }
}
```

**`src/main/java/example/authorization/SecurityConfig.java`**

```java
package example.authorization;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.servlet.util.matcher.PathPatternRequestMatcher;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        var path = PathPatternRequestMatcher.withDefaults();

        http.authorizeHttpRequests(auth -> auth
            // Phải đứng trước /reports/{id}.
            .requestMatchers(path.matcher(HttpMethod.GET, "/reports/public"))
                .permitAll()
            .requestMatchers(path.matcher(HttpMethod.GET, "/reports/{id}"))
                .hasAuthority("report:read")
            .requestMatchers(path.matcher(HttpMethod.POST, "/reports/{id}"))
                .hasAuthority("report:write")
            // Chặn path con không nằm trong hai dạng URL được cho phép.
            .requestMatchers(path.matcher("/reports/**"))
                .denyAll()
            .anyRequest().denyAll()
        );
        // Với cấu hình này, request chưa xác thực đến endpoint được bảo vệ
        // sẽ nhận HTTP Basic challenge (thông thường 401).
        http.httpBasic(Customizer.withDefaults());
        // Giữ nguyên CSRF mặc định: test POST phải đưa token hợp lệ.
        return http.build();
    }
}
```

**`src/main/java/example/authorization/ReportController.java`**

```java
package example.authorization;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/reports")
public class ReportController {
    @GetMapping("/public")
    String publicReport() {
        return "PUBLIC";
    }

    @GetMapping("/{id}")
    String getReport(@PathVariable String id) {
        return "REPORT:" + id;
    }

    @PostMapping("/{id}")
    String updateReport(@PathVariable String id) {
        return "UPDATED:" + id;
    }
}
```

Ý nghĩa của cấu hình:

- `GET /reports/public` là công khai dù `/reports/{id}` cũng có thể khớp chuỗi `public`; **độ ưu tiên đến từ thứ tự rule**.
- `GET /reports/42` cần `report:read`; `POST /reports/42` cần `report:write` và token CSRF hợp lệ theo cấu hình demo.
- `/reports/42/extra` và các method khác không được cấp quyền; `anyRequest().denyAll()` là chốt cuối cho những đường dẫn còn lại.
- Các authority ở đây cố tình đặt tên `report:read`/`report:write`; code kiểm tra **quyền theo endpoint**, chưa kiểm tra ownership của từng báo cáo. Quyền xem báo cáo 42 của cá nhân nào phải có thêm kiểm tra ở lớp nghiệp vụ.

## 5. Kiểm thử tích hợp với MockMvc

**`src/test/java/example/authorization/AuthorizationBoundaryTest.java`**

```java
package example.authorization;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AuthorizationBoundaryTest {
    @Autowired
    MockMvc mvc;

    @Test
    void publicExactPathIsAnonymous() throws Exception {
        mvc.perform(get("/reports/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("PUBLIC"));
    }

    @Test
    void protectedPathIsUnauthorizedWithoutIdentity() throws Exception {
        mvc.perform(get("/reports/42"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(authorities = "report:read")
    void readerCanGetOneReport() throws Exception {
        mvc.perform(get("/reports/42"))
            .andExpect(status().isOk())
            .andExpect(content().string("REPORT:42"));
    }

    @Test
    @WithMockUser(authorities = "other")
    void unrelatedAuthorityCannotRead() throws Exception {
        mvc.perform(get("/reports/42"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(authorities = "report:write")
    void writerCanPostWithCsrf() throws Exception {
        mvc.perform(post("/reports/42").with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("UPDATED:42"));
    }

    @Test
    @WithMockUser(authorities = "report:read")
    void readDoesNotGrantWrite() throws Exception {
        mvc.perform(post("/reports/42").with(csrf()))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(authorities = "report:write")
    void missingCsrfIsForbiddenEvenForWriter() throws Exception {
        mvc.perform(post("/reports/42"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(authorities = "report:read")
    void extraSegmentCannotBypassExactResourceRule() throws Exception {
        mvc.perform(get("/reports/42/extra"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(authorities = "report:read")
    void trailingSlashIsNotAutomaticallyEquivalent() throws Exception {
        mvc.perform(get("/reports/42/"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(authorities = "report:read")
    void queryStringDoesNotChangePathMatch() throws Exception {
        mvc.perform(get("/reports/42").param("view", "full"))
            .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(authorities = "report:write")
    void unlistedMethodIsDeniedEvenWithCsrf() throws Exception {
        mvc.perform(put("/reports/42").with(csrf()))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(authorities = "report:read")
    void caseChangedPrefixIsNotSamePath() throws Exception {
        mvc.perform(get("/Reports/42"))
            .andExpect(status().isForbidden());
    }

    @Test
    void similarPublicPrefixIsStillProtected() throws Exception {
        // "publication" khớp /reports/{id}, không khớp /reports/public.
        mvc.perform(get("/reports/publication"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(authorities = "report:read")
    void otherPathIsDeniedByFallback() throws Exception {
        mvc.perform(get("/unlisted"))
            .andExpect(status().isForbidden());
    }
}
```

Chạy trong dự án dùng Gradle wrapper:

```bash
./gradlew test --tests 'example.authorization.AuthorizationBoundaryTest'
```

Trên Windows PowerShell có thể dùng `.\gradlew.bat test --tests "example.authorization.AuthorizationBoundaryTest"`. **Kết quả mong đợi:** toàn bộ test trên pass khi ứng dụng dùng đúng cấu hình và dependency đã nêu; kết quả do JUnit/Gradle công bố sau khi chạy, không phải output chương trình Java viết ra `stdout`.

Trong ví dụ này, `@SpringBootTest` + `@AutoConfigureMockMvc` khởi tạo cấu hình Security và đăng ký filter cho `MockMvc`. Nếu tự xây dựng `MockMvcBuilders`, cần thêm `springSecurity()`/`FilterChainProxy`; thiếu filter sẽ khiến test phân quyền cho kết quả sai. `@WithMockUser` giả lập principal và authority trong test, không tự chứng minh quy trình đăng nhập thực hay JWT hợp lệ. Vì vậy, bổ sung test xác thực thật nếu bài toán cần bảo đảm cả hai.

### Ma trận kiểm thử nên duy trì

| Method, URL | Principal / điều kiện | Kỳ vọng trong demo | Điều được chứng minh |
| --- | --- | --- | --- |
| GET `/reports/public` | Chưa đăng nhập | 200 | Exact public rule thắng |
| GET `/reports/42` | Chưa đăng nhập | 401 | URL riêng tư phải xác thực (HTTP Basic) |
| GET `/reports/42` | `report:read` | 200 | Được phép đọc |
| GET `/reports/42` | `other` | 403 | Authenticated nhưng thiếu quyền |
| POST `/reports/42` | `report:write` + CSRF | 200 | Đúng method + authority |
| POST `/reports/42` | `report:read` + CSRF | 403 | Read không suy ra write |
| POST `/reports/42` | `report:write`, thiếu CSRF | 403 | CSRF là lớp kiểm tra riêng |
| GET `/reports/42/extra` | `report:read` | 403 | Segment thừa không đi qua `/{id}` |
| GET `/reports/42/` | `report:read` | 403 | Trailing slash bị kiểm soát |
| GET `/Reports/42` | `report:read` | 403 | Case mặc định được phân biệt |
| GET `/reports/42?view=full` | `report:read` | 200 | Query không đổi path matcher |
| GET `/reports/publication` | Chưa đăng nhập | 401 | Prefix gần giống không phải URL public |
| PUT `/reports/42` | `report:write` + CSRF | 403 | Không tự cho phép method chưa liệt kê |
| GET `/unlisted` | `report:read` | 403 | Fallback deny-all hoạt động |

Điểm then chốt: **assert cả success lẫn denial**. Nếu chỉ test 403 cho endpoint không có controller, ta có thể che giấu vấn đề router; vì vậy các ca được phép ở trên còn kiểm tra **body thật** để chứng minh controller đã chạy.

## 6. Riêng servlet path: phân biệt context path và mapping của DispatcherServlet

Giả sử request bên ngoài là `GET /shop/mvc/admin/7`:

| Thành phần | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| `requestURI` | `/shop/mvc/admin/7` | Toàn đường dẫn của request (không gồm query) |
| `contextPath` | `/shop` | Prefix triển khai ứng dụng, ví dụ `server.servlet.context-path` |
| `servletPath` | `/mvc` | Prefix mapping của `DispatcherServlet`, ví dụ `spring.mvc.servlet.path` |
| Path trong MVC | `/admin/7` | Đường dẫn controller xử lý phía sau servlet mapping |

Với `PathPatternRequestMatcher`, pattern được hiểu **tương đối với context path**. Nếu muốn tái sử dụng một servlet prefix, cấu hình `basePath("/mvc")` và viết các pattern còn lại tương đối với prefix đó:

```java
import static org.springframework.security.web.servlet.util.matcher.PathPatternRequestMatcher.withDefaults;

// Trích đoạn bên trong cấu hình SecurityFilterChain:
var mvc = withDefaults().basePath("/mvc");
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(mvc.matcher("/admin/**")).hasAuthority("admin")
    .anyRequest().denyAll()
);
```

Trong ví dụ này, matcher kiểm tra request đến `/shop/mvc/admin/7` bằng pattern tương ứng với `/mvc/admin/**` **sau khi bỏ context path `/shop`**. Không thêm `/shop` vào pattern; cũng không vô tình bỏ `/mvc`. Cần bảo đảm servlet mapping thật của ứng dụng trùng với giả định.

Một phép kiểm thử matcher độc lập để kiểm tra việc bóc prefix (dùng JUnit 5 và `spring-test`):

```java
package example.authorization;

import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.security.web.servlet.util.matcher.PathPatternRequestMatcher;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ServletPathMatcherTest {
    @Test
    void matchesServletPrefixButNotUnrelatedPath() {
        var builder = PathPatternRequestMatcher.withDefaults().basePath("/mvc");
        var admin = builder.matcher("/admin/**");

        var request = new MockHttpServletRequest("GET", "/shop/mvc/admin/7");
        request.setContextPath("/shop");
        request.setServletPath("/mvc");
        request.setPathInfo("/admin/7");
        assertTrue(admin.matches(request));

        var unrelated = new MockHttpServletRequest("GET", "/shop/other/admin/7");
        unrelated.setContextPath("/shop");
        unrelated.setServletPath("/other");
        unrelated.setPathInfo("/admin/7");
        assertFalse(admin.matches(unrelated));
    }
}
```

Test matcher độc lập chỉ chứng minh `RequestMatcher.matches` trên request giả lập; **chưa chứng minh DispatcherServlet và controller được ánh xạ đúng**. Để kiểm chứng end-to-end, chạy thêm `MockMvc` trong một fixture riêng có `spring.mvc.servlet.path=/mvc`, controller ở `@GetMapping("/admin/7")`, và thực hiện `get("/mvc/admin/7").servletPath("/mvc")` với các authority được phép/bị chặn. Khi chạy ứng dụng thật, thử cả context path và reverse-proxy prefix.

**Lưu ý phiên bản liên quan trực tiếp đến servlet path:** Spring Security **7.0.0–7.0.4** có CVE-2026-22753 khi kết hợp `securityMatchers(String)` với `PathPatternRequestMatcher.Builder` bean dùng để gắn servlet path; đường dẫn dự định bảo vệ có thể không chọn đúng filter chain. Bản sửa là **7.0.5**. Nếu dự án thuộc cấu hình bị ảnh hưởng, nâng cấp bản đã vá và thêm regression test chọn chuỗi theo servlet path; không suy rằng test của `requestMatchers` đủ kiểm chứng `securityMatchers`.

## 7. Nhiều SecurityFilterChain: test việc chọn chuỗi trước khi test quyền

Ví dụ sau là **trích đoạn minh họa hai bean**, không thay thế cấu hình hoàn chỉnh ở mục 4:

```java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/**")
        .authorizeHttpRequests(a -> a.anyRequest().hasAuthority("api:read"))
        .httpBasic(Customizer.withDefaults());
    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain fallback(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(a -> a.anyRequest().denyAll());
    return http.build();
}
```

Thêm imports khi đưa vào một class chạy thật: `org.springframework.context.annotation.Bean`, `org.springframework.core.annotation.Order`, `org.springframework.security.web.SecurityFilterChain`, `org.springframework.security.config.annotation.web.builders.HttpSecurity` và `org.springframework.security.config.Customizer`.

Với nhiều chuỗi, **không được giả định** `anyRequest().denyAll()` bên trong `apiChain` sẽ xử lý `/outside`: request `/outside` không khớp `securityMatcher("/api/**")`. Test nên chứng minh `/api/resource` đi vào chuỗi API với quyền đúng và sai, còn `/outside` vẫn bị fallback chặn. Thử cả `/api`, `/api/`, `/apis` và một path ngoài API; nếu có `basePath` của servlet, test chính đường dẫn đó. Việc khai báo matcher theo chuỗi cần tương thích phiên bản/engine của dự án.

## 8. Đường dẫn bất thường, firewall và status code

Các case sau là **danh sách kiểm thử an toàn theo chính sách**, không được mặc định tất cả sẽ trả 403:

| Nhóm | Dữ liệu nên thử | Kiểm chứng |
| --- | --- | --- |
| Path traversal/chuẩn hóa | `/admin/../public`, `/admin//audit` | Proxy, servlet container, `StrictHttpFirewall` không tạo lối đi ngoài rule |
| Encoded separator | `%2F`, `%5C`, double-encoding | URL bị từ chối hoặc cùng chính sách sau giải mã; xác nhận trên container thật |
| Path parameters | `/admin;v=1/audit` | Không làm sai kết quả matcher; chú ý chính sách dấu `;` |
| Case/trailing slash | `/Admin`, `/admin/` | Không vô tình đổi quyền do parser hoặc redirect |
| Method | GET, HEAD, POST, PUT, DELETE, OPTIONS | Method cụ thể và CORS preflight được xử lý có chủ đích |
| Dispatcher | REQUEST, FORWARD, ERROR | Quy tắc theo dispatcher type nếu ứng dụng có forward/error route |

`StrictHttpFirewall` có thể **từ chối request trước `AuthorizationFilter`**, dẫn đến status hoặc exception khác nhau theo môi trường và handler. Nếu một test bị 400, 403 hoặc `RequestRejectedException`, kiểm tra log/filter trước khi khẳng định matcher đã thực thi. Test qua `MockMvc` có thể không mô phỏng chính xác reverse proxy/servlet container; với biến thể URL nguy hiểm, chạy thêm HTTP integration test qua cổng thật của ứng dụng.

`401 Unauthorized` và `403 Forbidden` trong bài là **kỳ vọng của cấu hình HTTP Basic + CSRF đã nêu**. Nếu đổi sang `formLogin`, OAuth2 resource server, custom `AuthenticationEntryPoint` hoặc `AccessDeniedHandler`, mã phản hồi có thể khác; hãy kiểm thử theo hợp đồng bảo mật thực tế. `404 Not Found` và `405 Method Not Allowed` có thể đến từ MVC **sau khi** security đã cho qua: chúng không tự chứng minh quyền được kiểm tra đúng.

## 9. Quy trình viết test cho một rule mới

1. **Ghi rõ hợp đồng**: method, URI và servlet/context path, principal/authority, controller có tồn tại, status/body mong đợi.
2. **Liệt kê các matcher cạnh tranh**: rule cụ thể, rule rộng, matcher theo method, `anyRequest`; với nhiều filter chain, liệt kê thêm `securityMatcher` và `@Order`.
3. **Tạo cặp đối chứng**: một request phải được phép và một request gần giống phải bị từ chối; có ít nhất một ca anonymous và một ca authenticated sai authority.
4. **Thử ranh giới**: base path, segment con, segment thừa, tiền tố giống nhau, dấu `/` cuối, hoa/thường, method khác, query, CSRF, servlet path; chỉ thêm ca encoding/firewall nào ứng dụng thực sự chấp nhận hoặc có nguy cơ.
5. **Assert nguyên nhân đúng**: với ca success, kiểm tra body/handler; với ca denial, bảo đảm request có handler tương ứng khi muốn chứng minh rule phân quyền, kiểm soát riêng CSRF và firewall.
6. **Chạy lại sau mỗi thay đổi route/matcher/Spring Security**. Không đổi cấu hình để làm test pass bằng cách nới `permitAll` hoặc tắt các filter bảo vệ; trước hết tìm matcher nào thực sự khớp.

### Các lỗi phổ biến và cách tìm nguyên nhân

- **Quy tắc rộng đứng trước quy tắc hẹp:** thêm test `GET /admin/audit` với user thường; đưa rule đặc thù lên trước.
- **Nhầm `securityMatcher` và `requestMatchers`:** kiểm tra chuỗi filter thực sự được chọn và có fallback; không chỉ nhìn vào `anyRequest()`.
- **Nhầm servlet path/context path:** ghi lại `requestURI`, `contextPath`, `servletPath` và `pathInfo` trong test/log; dùng `basePath` đúng với servlet mapping.
- **Test chỉ có status deny:** thêm ca 200 với response body để chứng minh controller đã chạy.
- **Sai authority vì prefix `ROLE_`:** thống nhất `hasRole`/`roles` hoặc `hasAuthority`/`authorities`.
- **POST bị 403 dù quyền đúng:** thêm `with(csrf())` nếu chính sách yêu cầu CSRF, rồi test riêng ca thiếu token.
- **MockMvc bỏ filter:** dùng `@AutoConfigureMockMvc` với filter được bật, hoặc `apply(springSecurity())` khi xây `MockMvc` thủ công.
- **Giả định wildcard giống nhau qua các phiên bản:** xác định engine/parser thực tế, test case dấu slash, `**`, dấu `;`, encoded path và nâng cấp bằng regression tests.
- **Chặn nhầm tài nguyên theo owner:** request-level `hasAuthority` chỉ xác minh quyền tổng quát; thêm `@PreAuthorize`/`AuthorizationManager` hoặc kiểm tra nghiệp vụ cho từng object.

## 10. Bài tập tự kiểm chứng

1. Đảo hai rule GET `/reports/public` và GET `/reports/{id}` trong ví dụ. Chạy `publicExactPathIsAnonymous`: sự thay đổi kết quả chứng minh **first match wins**. Sau đó khôi phục thứ tự đúng.
2. Bổ sung endpoint `GET /reports/42/items` và rule chỉ cho phép `report:read:items`. Viết test chứng minh tài khoản chỉ có `report:read` không tự truy cập được đường dẫn mới; đặt rule mới trước fallback `/reports/**`.
3. Chuyển ứng dụng sang servlet path `/mvc` trong một fixture riêng. Test `/mvc/reports/42`, `/reports/42` và context path `/shop` để kiểm tra đúng/thiếu prefix.
4. Tạo hai `SecurityFilterChain` theo `@Order` và cố tình bỏ fallback trong fixture thử nghiệm. Quan sát khác biệt với cấu hình có fallback, rồi khôi phục chính sách chặn mặc định.
5. Tạo ma trận test quyền cho ba vai trò: anonymous, reader, writer; mỗi method/path có cả ca cho phép và từ chối.

**Tiêu chí hoàn thành:** test phải phát hiện được thay đổi thứ tự rule, chênh lệch một segment hoặc servlet prefix, khác method, và các trường hợp thiếu quyền/CSRF. Một đường dẫn bị 404 hoặc bị firewall từ chối phải được phân loại chính xác thay vì coi là bằng chứng duy nhất của authorization.

## Tài liệu tham khảo chính thức

- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html) — thứ tự rule, matcher và servlet path.
- [Spring Security — Java Configuration](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html) — nhiều `SecurityFilterChain` và `securityMatcher`.
- [Spring Security — MockMvc Authentication](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html) — principal giả lập và tích hợp security vào `MockMvc`.
- [Spring Security — Testing CSRF](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html) — token hợp lệ/không hợp lệ trong test.
- [PathPatternRequestMatcher.Builder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/servlet/util/matcher/PathPatternRequestMatcher.Builder.html) — `matcher`, `basePath` và method.
- [Spring Security advisory CVE-2026-22753](https://spring.io/security/cve-2026-22753/) — lỗi chọn chuỗi khi kết hợp `securityMatchers(String)` và servlet path trong Spring Security 7.0.0–7.0.4.