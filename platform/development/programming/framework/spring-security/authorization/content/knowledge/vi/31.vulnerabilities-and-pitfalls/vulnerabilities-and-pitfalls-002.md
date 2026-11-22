# Quy tắc `permitAll` quá rộng hoặc bị che bởi thứ tự matcher trong Spring Security

Một lỗi cấu hình authorization rất dễ tạo lỗ hổng là đặt `permitAll()` trên pattern bao phủ cả các API nhạy cảm, hoặc viết quy tắc đúng nhưng **không bao giờ được áp dụng** vì một matcher rộng hơn đã khớp trước. Lỗi ngược lại cũng xuất hiện: một matcher yêu cầu đăng nhập hoặc từ chối đặt trước matcher public khiến endpoint công khai bất ngờ trả 401/403. Bài này giải thích cách Spring Security chọn quy tắc, cách xác định phạm vi public an toàn và cách viết kiểm thử phát hiện regression.

Phạm vi: **Spring Security servlet stack**, cấu hình `HttpSecurity` với `authorizeHttpRequests` (Spring Security 6.x, Java 17+). Nội dung phân biệt rõ thứ tự quy tắc **trong cùng một `SecurityFilterChain`** với thứ tự chọn **giữa nhiều filter chain**.

## 1. Lỗ hổng phát sinh như thế nào?

Giả sử ứng dụng định nghĩa ba loại endpoint:

| Endpoint | Chính sách mong muốn |
| --- | --- |
| `GET /api/public/ping` | Bất kỳ ai, kể cả chưa đăng nhập |
| `GET /api/admin/report` | Chỉ người có vai trò `ADMIN` |
| `GET /api/orders` | Người dùng đã xác thực |
| Các URL không nằm trong danh sách | Từ chối theo mặc định |

Cấu hình **sai** sau đây nhìn qua có vẻ đã bảo vệ `/api/admin/**`:

~~~java
// SAI — fragment minh họa, đặt bên trong cấu hình HttpSecurity.
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").permitAll()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .requestMatchers("/api/orders").authenticated()
    .anyRequest().denyAll()
);
~~~

Kết quả thực tế:

- `GET /api/public/ping` khớp `/api/**` → được phép, đúng dự định.
- `GET /api/admin/report` **cũng khớp `/api/**` trước** → được phép dù chưa đăng nhập.
- `GET /api/orders` cũng được phép mà không cần xác thực.
- Quy tắc `hasRole("ADMIN")` và `authenticated()` ở phía sau không được dùng cho các URL này.

Trong `authorizeHttpRequests`, Spring Security đánh giá các cặp matcher/rule theo thứ tự khai báo và áp dụng **quy tắc khớp đầu tiên**. Nó không tự chọn pattern có vẻ “cụ thể nhất”, không tự ưu tiên `hasRole` hơn `permitAll` và không cộng dồn tất cả quy tắc khớp.

> **Điểm cần nhớ:** Một quy tắc trông có vẻ chặt chẽ vẫn có thể không có tác dụng nếu đã bị matcher trước đó che khuất.

### Sửa đúng theo chính sách đã chọn

~~~java
// ĐÚNG — chỉ public đúng endpoint, kiểm soát phần còn lại theo thứ tự.
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/public/ping").permitAll()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .requestMatchers("/api/orders").authenticated()
    .anyRequest().denyAll()
);
~~~

Cần import `org.springframework.http.HttpMethod`. Nếu ứng dụng cần nhiều URL công khai, hãy liệt kê rõ hoặc nhóm theo một namespace mà **không thể** chứa endpoint nhạy cảm, ví dụ `/api/public/**` sau khi đã rà soát toàn bộ URL và các HTTP method của namespace đó.

Ở ví dụ thứ hai, `GET /api/orders` vẫn được bảo vệ vì matcher `/api/orders` đứng trước `anyRequest()`. Những endpoint chưa khai báo sẽ bị `denyAll()`; cách này giúp phát hiện URL mới bị quên khi bổ sung controller.

## 2. Hai loại thứ tự cần hiểu riêng

### 2.1. Thứ tự các quy tắc trong một chain

Khi một request đã được đưa vào một `SecurityFilterChain`, `AuthorizationFilter` áp dụng danh sách được cấu hình qua `authorizeHttpRequests`. Chính sách trong đó là **first match wins**.

| Thứ tự | Matcher | Quyết định |
| --- | --- | --- |
| 1 | `GET /api/public/ping` | `permitAll` |
| 2 | `/api/admin/**` | `hasRole("ADMIN")` |
| 3 | `/api/**` | `authenticated` |
| 4 | `anyRequest()` | `denyAll` |

Với `GET /api/admin/report`, matcher đầu không khớp, matcher thứ hai khớp và yêu cầu `ROLE_ADMIN`. Với `GET /api/private/data`, matcher thứ ba áp dụng. Với `GET /ops/health`, cả ba không khớp nên áp dụng `denyAll`.

**Thứ tự cho đúng phạm vi là điều kiện cần:** đặt `/api/**` sau matcher `/api/admin/**` nếu hai loại có mức bảo vệ khác nhau. Tránh duy trì các matcher sau một matcher rộng đến mức không thể tới được.

### 2.2. Thứ tự lựa chọn giữa nhiều `SecurityFilterChain`

`FilterChainProxy` duyệt các `SecurityFilterChain` theo thứ tự ưu tiên và chọn **chain khớp đầu tiên** với request. Quy tắc `authorizeHttpRequests` của những chain không được chọn sẽ **không tham gia** quyết định.

Sai lầm ví dụ:

~~~java
// SAI — hai Bean minh họa thứ tự chain, không chép ghép với ví dụ khác.
@Bean
@Order(1)
SecurityFilterChain openEverywhere(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/**")
        .authorizeHttpRequests(auth -> auth.anyRequest().permitAll())
        .build();
}

@Bean
@Order(2)
SecurityFilterChain protectAdmin(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/admin/**")
        .authorizeHttpRequests(auth -> auth.anyRequest().hasRole("ADMIN"))
        .build();
}
~~~

`openEverywhere` ở thứ tự 1 khớp cả `/api/admin/report`. Chain bảo vệ admin ở thứ tự 2 không được chọn. Sửa bằng cách đặt chain phạm vi hẹp, cần bảo vệ đặc biệt lên trước; đồng thời xây dựng chain cuối kiểm soát toàn bộ phần còn lại:

~~~java
// ĐÚNG — các Bean minh họa khi cần nhiều SecurityFilterChain.
@Bean
@Order(1)
SecurityFilterChain adminChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/admin/**")
        .authorizeHttpRequests(auth -> auth.anyRequest().hasRole("ADMIN"))
        .httpBasic(Customizer.withDefaults())
        .build();
}

@Bean
@Order(2)
SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/public/ping").permitAll()
            .requestMatchers("/api/**").authenticated()
            .anyRequest().denyAll()
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

Đây là **mẫu minh họa riêng**, không phải file hoàn chỉnh. Nó cần các import `@Bean`, `@Order`, `HttpSecurity`, `SecurityFilterChain`, `Customizer`, `HttpMethod` và cấu hình ứng dụng phù hợp. Trong hai mẫu này, `fallbackChain` không giới hạn bằng `securityMatcher` nên hoạt động như chain cuối bao trùm tất cả request còn lại.

**`securityMatcher(...)` khác `requestMatchers(...)`:**

- `http.securityMatcher("/api/**")` xác định **request nào được gửi vào cả filter chain** này.
- `authorizeHttpRequests(auth -> auth.requestMatchers(...))` xác định **quy tắc quyền nào được áp dụng trong chain đã chọn**.
- `anyRequest()` chỉ có nghĩa “mọi request thuộc chain hiện tại còn chưa khớp quy tắc”. Nó **không** tự bảo vệ đường dẫn không được bất kỳ chain nào chọn.

Nếu không có `SecurityFilterChain` nào khớp một URL, request đó không được các filter Spring Security trong chuỗi xử lý. Vì vậy, khi dùng nhiều chain, phải rà soát độ bao phủ của tất cả `securityMatcher`, đặc biệt các URL không bắt đầu bằng `/api/`.

## 3. Nhận diện những cấu hình sai thường gặp

### 3.1. `/api/**` hoặc `/**` được phép quá rộng

~~~java
// SAI: mọi API dưới /api/ đều public.
.requestMatchers("/api/**").permitAll()

// SAI: một matcher bao trùm toàn ứng dụng.
.requestMatchers("/**").permitAll()

// SAI: mọi đường dẫn chưa khớp được public, kể cả endpoint mới.
.anyRequest().permitAll()
~~~

Các dạng này thường đến từ cấu hình tạm để kiểm thử, “mở” API cho frontend, hoặc thêm endpoint public mà thiếu phân biệt đường dẫn. Khi dùng `permitAll()`, hãy đòi hỏi một lý do nghiệp vụ cụ thể cho **từng URL và HTTP method**; hạn chế diện tích public ở mức cần thiết.

### 3.2. Quy tắc public bị che bởi `authenticated` hoặc `denyAll`

~~~java
// SAI: matcher đầu đã bắt cả /api/public/ping.
.requestMatchers("/api/**").authenticated()
.requestMatchers("/api/public/**").permitAll()

// SAI: matcher đầu chặn cả /api/public/ping.
.requestMatchers("/api/**").denyAll()
.requestMatchers("/api/public/**").permitAll()
~~~

Đây thường là lỗi chức năng (người dùng ẩn danh gặp 401/403 ở endpoint cần public), nhưng nếu sửa bằng cách chuyển nguyên `/api/**` sang `permitAll` thì lại tạo lỗ hổng ở phần còn lại. Cách sửa đúng là **thu hẹp matcher public** hoặc **đưa matcher cụ thể lên trước**, sau đó giữ rule bảo vệ phần còn lại.

### 3.3. Quên ràng buộc HTTP method

~~~java
// Cần kiểm tra: GET, POST, PUT, DELETE đều có thể được cấp quyền.
.requestMatchers("/api/public/ping").permitAll()

// Hẹp hơn: chỉ công khai GET.
.requestMatchers(HttpMethod.GET, "/api/public/ping").permitAll()
~~~

Nếu cùng URL hỗ trợ `GET` để xem và `POST` để cập nhật, dùng matcher không phân biệt method có thể làm công khai cả thao tác ghi. Đặt chính sách theo method, ví dụ `GET` công khai, `POST` phải xác thực hoặc yêu cầu authority cụ thể. Không dùng `permitAll` cho mọi `OPTIONS` chỉ để “sửa CORS” một cách vội vàng; hãy cấu hình CORS và preflight theo nhu cầu ứng dụng.

### 3.4. Các prefix có tên gần giống hoặc lồng nhau

Ví dụ `/api/public/**` không đồng nghĩa với `/api/publicity`; còn `/api/public/admin/**` có thể nằm trong namespace tưởng là công khai. Đừng cho rằng tên đường dẫn tự đảm bảo không có chức năng nhạy cảm. Khi thiết kế route, tách rõ khu vực public/private và thêm test phản ví dụ cho URL gần giống.

Các matcher phụ thuộc vào cách ứng dụng xử lý servlet path, path pattern, context path và quy tắc khớp của phiên bản Spring Security/Spring MVC. Không tự áp dụng kết luận từ một regex/Ant-style pattern cho mọi matcher; kiểm thử **đường dẫn HTTP thực tế** qua `MockMvc` hoặc integration test. Tránh tự “giải mã” hoặc sửa URL trước khi match mà không có bằng chứng cấu hình.

### 3.5. Đặt rule đúng nhưng ở chain sai

~~~java
http.securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/admin/**").hasRole("ADMIN")
        .anyRequest().authenticated()
    );
~~~

Matcher `/admin/**` bên trong chain `/api/**` không bảo vệ `/admin/dashboard` vì request đó không vào chain. Nếu endpoint admin thực nằm ở `/api/admin/**`, matcher trong chain cũng phải là `/api/admin/**`. Luôn kiểm tra **hai tầng phạm vi** trước khi kết luận rule đã có hiệu lực.

### 3.6. Nhầm `permitAll` với tắt mọi lớp bảo vệ

`permitAll()` chỉ nói rằng quyết định **authorization ở matcher này** cho phép truy cập. Request vẫn đi qua filter chain đã được chọn, và các cơ chế khác như CSRF, filter tùy chỉnh, HTTP security headers hoặc method security vẫn có thể ảnh hưởng kết quả.

Ví dụ `POST` vào endpoint `permitAll` vẫn có thể nhận 403 do CSRF nếu ứng dụng bật CSRF và request thiếu token. Đây **không** chứng minh matcher đã hoạt động như mong muốn. Tương tự, `web.ignoring()` loại request khỏi Spring Security filter chain nên không tương đương `permitAll()`; với tài nguyên tĩnh, tài liệu Spring Security khuyên dùng `permitAll` để vẫn nhận các tính năng như security headers.

## 4. Cách thiết kế chính sách an toàn từ đầu

Làm rõ danh sách route, method và quyền trước khi viết matcher. Một thứ tự dễ đọc:

1. Endpoint public **cụ thể** trước: login, health công khai thật sự, file tĩnh, các GET đã được phê duyệt.
2. Endpoint nhạy cảm theo chức năng, vai trò, authority hoặc policy: `/api/admin/**`, `/api/billing/**`.
3. Matcher rộng nhưng **vẫn yêu cầu bảo vệ**: `/api/**` → `authenticated()`.
4. Quy tắc cuối `anyRequest().denyAll()` để tránh vô tình mở endpoint mới.

Ví dụ:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/public/ping").permitAll()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .requestMatchers("/api/billing/**").hasAuthority("BILLING_READ")
    .requestMatchers("/api/**").authenticated()
    .anyRequest().denyAll()
);
~~~

Bốn điểm cần kiểm tra khi thay đổi route:

- `/api/admin/**` và `/api/billing/**` có nằm dưới matcher rộng nào đứng trước hay không?
- API có **thêm HTTP method** mới ở URL public cũ không?
- Thay đổi `securityMatcher`, servlet path hoặc `@Order` có khiến request đi sang chain khác không?
- Endpoint mới không có khai báo riêng sẽ bị chặn hay vô tình được phép bởi wildcard?

`hasRole("ADMIN")` kiểm tra authority `ROLE_ADMIN` theo tiền tố role mặc định. `hasAuthority("BILLING_READ")` yêu cầu authority đúng tên `BILLING_READ`. Không đổi giữa hai dạng nếu chưa xác minh mapping từ user/JWT sang authorities.

**Lưu ý về quyền sở hữu:** `authenticated()` chỉ yêu cầu đã đăng nhập, **không** chứng minh user được phép xem mọi bản ghi. Với `/api/orders/{id}`, phải có kiểm tra quyền theo chủ sở hữu/tenant hoặc policy ở tầng service để tránh truy cập chéo người dùng. Bài này tập trung vào matcher và phạm vi authorization; việc kiểm tra ownership là lớp chính sách bổ sung cần có khi dữ liệu nhạy cảm.

## 5. Ví dụ đầy đủ: kiểm thử cấu hình và thứ tự bằng MockMvc

Ví dụ dùng **Spring Boot 3.5.7, Spring Security 6.x, Java 17, JUnit 5**. Không cần khởi động server thật hoặc kết nối database. Tạo dự án:

~~~text
permit-all-order-demo/
├── pom.xml
└── src/test/java/com/example/security/MatcherOrderTest.java
~~~

### 5.1. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>permit-all-order-demo</artifactId>
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
</project>
~~~

### 5.2. `MatcherOrderTest.java`

~~~java
package com.example.security;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(classes = MatcherOrderTest.TestApp.class)
@AutoConfigureMockMvc
class MatcherOrderTest {

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @Import({RulesConfig.class, DemoController.class})
    static class TestApp {}

    @Configuration(proxyBeanMethods = false)
    @EnableWebSecurity
    static class RulesConfig {

        @Bean
        SecurityFilterChain appChain(HttpSecurity http) throws Exception {
            http.authorizeHttpRequests(auth -> auth
                    // Chỉ phương thức GET ở một endpoint được public.
                    .requestMatchers(HttpMethod.GET, "/api/public/ping").permitAll()
                    // Kiểm soát vùng admin trước matcher API rộng hơn.
                    .requestMatchers("/api/admin/**").hasRole("ADMIN")
                    // Các API còn lại bắt buộc phải đăng nhập.
                    .requestMatchers("/api/**").authenticated()
                    // Chặn URL không được khai báo trong chính sách.
                    .anyRequest().denyAll()
                )
                // Dùng HTTP Basic để test 401 nhất quán.
                .httpBasic(Customizer.withDefaults())
                .formLogin(AbstractHttpConfigurer::disable);
            return http.build();
        }
    }

    @RestController
    static class DemoController {
        @GetMapping("/api/public/ping")
        String ping() { return "pong"; }

        @PostMapping("/api/public/ping")
        String createPing() { return "created"; }

        @GetMapping("/api/admin/report")
        String adminReport() { return "restricted"; }

        @GetMapping("/api/private/data")
        String privateData() { return "private"; }

        @GetMapping("/api/publicity")
        String nearbyNameButPrivate() { return "sensitive"; }

        @GetMapping("/ops/health")
        String operationsHealth() { return "internal"; }
    }

    @Autowired
    MockMvc mvc; // AutoConfigureMockMvc sử dụng Spring Security filters.

    @Test
    void anonymousCanReadDeclaredPublicGet() throws Exception {
        mvc.perform(get("/api/public/ping"))
           .andExpect(status().isOk())
           .andExpect(content().string("pong"));
    }

    @Test
    void anonymousCannotReadPrivateApi() throws Exception {
        mvc.perform(get("/api/private/data"))
           .andExpect(status().isUnauthorized());
    }

    @Test
    void anonymousCannotReadAdminApi() throws Exception {
        mvc.perform(get("/api/admin/report"))
           .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser
    void authenticatedUserCanReadPrivateApi() throws Exception {
        mvc.perform(get("/api/private/data"))
           .andExpect(status().isOk());
    }

    @Test
    @WithMockUser
    void authenticatedUserCannotReadAdminApi() throws Exception {
        mvc.perform(get("/api/admin/report"))
           .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminCanReadAdminApi() throws Exception {
        mvc.perform(get("/api/admin/report"))
           .andExpect(status().isOk())
           .andExpect(content().string("restricted"));
    }

    @Test
    void similarLookingPathIsNotAccidentallyPublic() throws Exception {
        mvc.perform(get("/api/publicity"))
           .andExpect(status().isUnauthorized());
    }

    @Test
    void postOnGetOnlyPublicPathRequiresLogin() throws Exception {
        mvc.perform(post("/api/public/ping").with(csrf()))
           .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser
    void authenticatedPostWithCsrfIsAllowed() throws Exception {
        mvc.perform(post("/api/public/ping").with(csrf()))
           .andExpect(status().isOk())
           .andExpect(content().string("created"));
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void unrelatedAreaIsDeniedEvenForAdmin() throws Exception {
        mvc.perform(get("/ops/health"))
           .andExpect(status().isForbidden());
    }
}
~~~

Chạy từ thư mục gốc dự án bằng JDK 17+ và Maven:

~~~bash
mvn test
~~~

**Kỳ vọng:** Maven chạy 10 test JUnit 5 và báo thành công. Nội dung log và thời lượng phụ thuộc môi trường; điều cần kiểm là mỗi `status()` và `content()` assertion đều đạt.

**Lưu ý kiểm thử:** Ví dụ có `.httpBasic(...)` và tắt form login để trường hợp chưa đăng nhập nhận HTTP 401 thay vì một redirect đến trang đăng nhập. Chính sách 401/403 cụ thể có thể khác trong ứng dụng dùng OAuth2 login, Bearer token hoặc custom exception handling; kiểm tra tương ứng với API của ứng dụng.

Test `postOnGetOnlyPublicPathRequiresLogin` cố ý thêm `.with(csrf())`. Nếu bỏ token, `CsrfFilter` có thể từ chối POST trước bước authorization; test trả 403 khi đó **không chứng minh** `permitAll` có hoặc không áp dụng cho POST. Khi yêu cầu kiểm chính sách URL, phải kiểm soát các điều kiện filter khác để kết luận đúng nguyên nhân.

`@WithMockUser` giả lập danh tính và authorities cho test authorization; không có nghĩa là cơ chế đăng nhập thật hoặc JWT validation đã được kiểm tra. Test cuối gọi URL **có controller thật** nhưng bị `anyRequest().denyAll()` chặn, tránh nhầm kết quả 404 do không có handler với chính sách từ chối truy cập.

### 5.3. Kiểm chứng test phát hiện lỗi thật

Thử thay duy nhất các rule trong `RulesConfig` của ví dụ trên bằng cấu hình sai:

~~~java
// SAI: dùng tạm để chứng minh test hồi quy phát hiện lỗi.
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").permitAll()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .anyRequest().denyAll()
);
~~~

Không cần giữ thay đổi này khi dùng code thực tế. Các kiểm thử chờ 401/403 cho `/api/admin/report`, `/api/private/data`, `/api/publicity` hoặc POST sẽ thất bại: rule `/api/**` đã biến những đường dẫn đó thành public. Đây là tín hiệu quan trọng để phát hiện lỗ hổng **trước khi đưa cấu hình lên môi trường thật**.

Thử lỗi ngược lại:

~~~java
// SAI: quy tắc rộng hơn che quy tắc public ở phía sau.
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").authenticated()
    .requestMatchers(HttpMethod.GET, "/api/public/ping").permitAll()
    .anyRequest().denyAll()
);
~~~

Test `anonymousCanReadDeclaredPublicGet` sẽ không còn nhận 200: matcher `/api/**` yêu cầu xác thực trước khi `permitAll` được xét. Cả hai phép thử cho thấy **vị trí trong danh sách** là thành phần của chính sách, không phải chỉ tên matcher.

## 6. Ma trận kiểm thử regression cần có

Bảng sau giả định đang dùng **cấu hình an toàn** ở mục 5 với HTTP Basic và các route đã khai báo:

| Actor | Request | Quy tắc được chọn | HTTP mong đợi |
| --- | --- | --- | --- |
| Anonymous | `GET /api/public/ping` | Public GET cụ thể | 200 |
| Anonymous | `GET /api/private/data` | `/api/** → authenticated` | 401 |
| User có `ROLE_USER` | `GET /api/private/data` | `/api/** → authenticated` | 200 |
| Anonymous | `GET /api/admin/report` | `/api/admin/** → hasRole` | 401 |
| User có `ROLE_USER` | `GET /api/admin/report` | `/api/admin/** → hasRole` | 403 |
| User có `ROLE_ADMIN` | `GET /api/admin/report` | `/api/admin/** → hasRole` | 200 |
| Anonymous | `GET /api/publicity` | `/api/** → authenticated` | 401 |
| Anonymous, có CSRF | `POST /api/public/ping` | `/api/** → authenticated` | 401 |
| User có `ROLE_USER`, có CSRF | `POST /api/public/ping` | `/api/** → authenticated` | 200 |
| User có `ROLE_ADMIN` | `GET /ops/health` | `anyRequest → denyAll` | 403 |

Đừng chỉ kiểm thử những URL **được phép**. Một `GET /api/admin/report` với vai trò `ADMIN` trả 200 chưa chứng minh người thường **không** thể gọi nó. Bắt buộc có ca không đăng nhập và ca đăng nhập thiếu quyền.

Với nhiều `SecurityFilterChain`, bổ sung ca test cho đường ranh giữa chain: đường dẫn thuộc chain admin, đường dẫn sát prefix admin nhưng thuộc chain fallback, các URL bên ngoài `/api`, và URL mới thêm. Nếu một chain bị matcher khác che phủ, ít nhất một test dùng người không có quyền phải phát hiện được.

## 7. Quy trình rà soát và sửa lỗi trong dự án thật

### Bước 1. Liệt kê phạm vi các chain

Tìm các bean trả về `SecurityFilterChain`, chú ý `@Order`, `securityMatcher(...)` và chain mặc định. Vẽ một bảng: “request mẫu → chain đầu tiên khớp”. Nếu không có chain nào khớp, đây là khoảng trống phải xử lý.

### Bước 2. Đọc matcher trong chain từ trên xuống

Với từng chain, lập danh sách chính sách `requestMatchers` và `anyRequest`. Kiểm tra cụ thể liệu một matcher như `/**`, `/api/**`, `/public/**` hoặc `anyRequest` có che khuất quy tắc phía sau. Không dựa vào vị trí class, tên bean, format code hay việc IDE vẫn hiển thị rule để kết luận nó được chạy.

### Bước 3. Đối chiếu endpoint thật

Lập inventory từ controller mappings, API gateway/reverse proxy, HTTP method, servlet path và context path. Lưu ý endpoint mới hoặc phương thức mới dùng chung URL với GET public. Nếu có proxy rewrite path, cần kiểm request URI mà ứng dụng thực nhận.

### Bước 4. Sửa nhỏ, duy trì deny-by-default

Thu hẹp những `permitAll` quá rộng, đưa matcher nhạy cảm lên trước matcher chung, hoặc chuyển `securityMatcher`/`@Order` để đúng chain nhận request. Đặt `anyRequest().denyAll()` ở chain bao phủ còn lại nếu phù hợp chính sách sản phẩm. Khi thay đổi, tránh mở tạm toàn bộ `/api/**` để chẩn đoán lỗi frontend.

### Bước 5. Kiểm thử tích cực và tiêu cực

Chạy `MockMvc`/integration tests cho **anonymous, user thường, user có quyền** trên cùng endpoint; phân biệt GET/POST; với request ghi, cung cấp CSRF hợp lệ nếu CSRF được bật. Test path gần giống, chain chồng lấn, endpoint không khai báo và truy cập tài nguyên thuộc người khác. Đặc biệt xác nhận URL nhạy cảm không bị rule public phía trên bắt mất.

### Bước 6. Đọc log để xác định đường đi

Khi cần điều tra, có thể bật log có giới hạn trong môi trường kiểm thử:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

Các log giúp xác định filter chain đang được áp dụng và quá trình xử lý security. Nội dung log thay đổi theo phiên bản và mức log; không thay thế test hành vi HTTP. Tránh bật log nhạy cảm quá rộng trên production.

## 8. Những bẫy khi diễn giải kết quả

**Một endpoint trả 403 chưa chắc do `authorizeHttpRequests`.** Với POST/PUT/DELETE, trước hết kiểm tra CSRF và CORS/filter tùy chỉnh. Dùng request hợp lệ để test chính sách quyền; sau đó test CSRF riêng.

**Một endpoint trả 404 chưa chứng minh đã được bảo vệ.** Nếu route không tồn tại, request có thể kết thúc 404 dù authorization mặc định public; khi kiểm thử quyền, dùng route có controller thực hoặc một spy kiểm tra controller không bị chạy khi bị từ chối.

**Đăng nhập là điều kiện cần, nhưng có thể chưa đủ.** `authenticated()` cho mọi user đã xác thực; tài nguyên theo ID, phạm vi tenant và chức năng có quyền đặc biệt cần authorization theo đối tượng/role. Matcher bảo vệ namespace không tự giải quyết IDOR/BOLA.

**`permitAll` không đồng nghĩa bỏ hết xác thực và bảo vệ.** Bộ lọc được chọn vẫn có thể hoạt động. Nên giữ security filter chain cho tài nguyên tĩnh thay vì loại bằng `web.ignoring()` nếu chỉ muốn mọi người truy cập chúng.

**Thứ tự matcher không giống thứ tự endpoint trong controller.** Chuyển vị trí `@GetMapping` trong source Java không sửa được một danh sách `requestMatchers` sai. Thứ tự được xác định ở cấu hình security, và với nhiều chain còn phụ thuộc `@Order` + `securityMatcher`.

**Không bỏ sót các HTTP method khác.** Nếu chỉ GET công khai, đừng dùng matcher không ghi method cho cùng URL rồi mặc định rằng POST sẽ an toàn nhờ CSRF. CSRF có cấu hình và trường hợp ngoại lệ riêng; authorization phải đúng cả khi request có CSRF hợp lệ.

**Đổi từ `authorizeRequests` sang `authorizeHttpRequests` có thể đòi hỏi rà soát cấu hình matcher cũ.** Không copy nguyên pattern từ API cũ mà bỏ qua thay đổi trong cách chọn/request matcher giữa các phiên bản. Cần test đường dẫn thực tế, method và filter-chain coverage sau nâng cấp.

## 9. Checklist rà soát trước khi triển khai

- [ ] Từng endpoint `permitAll` có lý do nghiệp vụ rõ ràng và phạm vi URL/method tối thiểu.
- [ ] Không có `/api/**`, `/**` hoặc `anyRequest().permitAll()` vô tình bao phủ endpoint nhạy cảm.
- [ ] Matcher cụ thể có độ bảo vệ cao đứng **trước** matcher rộng hơn trong cùng chain.
- [ ] Không có quy tắc cần dùng nhưng bị một matcher phía trước che khuất.
- [ ] Với nhiều chain, thứ tự `@Order` và `securityMatcher` đưa request đến chain dự kiến.
- [ ] Có chain cuối phù hợp để bảo vệ hoặc từ chối đường dẫn còn lại; không để khoảng trống ngoài mọi chain.
- [ ] Đã kiểm tra cả GET/POST/PUT/DELETE khi cùng URL có nhiều thao tác.
- [ ] Có test anonymous và authenticated-without-authority cho từng endpoint nhạy cảm.
- [ ] Test xác nhận public route thật sự public, private route thật sự private và URL gần giống không bị public nhầm.
- [ ] Test POST dùng CSRF hợp lệ khi mục tiêu là kiểm tra authorization, không lẫn nguyên nhân 403.
- [ ] Với dữ liệu theo chủ sở hữu/tenant, có policy ở tầng phù hợp ngoài kiểm tra namespace HTTP.
- [ ] Sau thay đổi matcher hoặc framework version, chạy lại toàn bộ authorization regression tests.

## 10. Tài liệu tham khảo chính thức

- Spring Security — Authorize HttpServletRequests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — Java Configuration, multiple `SecurityFilterChain`: https://docs.spring.io/spring-security/reference/servlet/configuration/java.html
- Spring Security — Architecture, `FilterChainProxy`: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Security — Spring MVC Test Integration: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/
- Spring Security — Setting Up MockMvc and Spring Security: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/setup.html

**Đánh giá đạt yêu cầu:** Với `GET /api/admin/report`, user thường phải bị chặn dù rule public đứng gần; với `GET /api/public/ping`, anonymous phải truy cập được; với `POST` trên cùng URL, anonymous vẫn phải bị yêu cầu đăng nhập nếu chỉ GET được public. Các kiểm thử này phải được giữ khi thêm endpoint, đổi đường dẫn, thay `@Order` hoặc nâng cấp Spring Security.
