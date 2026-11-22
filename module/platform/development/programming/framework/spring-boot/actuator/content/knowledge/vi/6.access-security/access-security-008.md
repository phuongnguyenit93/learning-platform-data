# Kiểm soát CSRF cho thao tác ghi hoặc xóa theo cơ chế xác thực

## 1. Vì sao đọc Actuator được nhưng ghi lại bị 403?

Giả sử bạn dùng đúng tài khoản vận hành: đọc cấu hình logger thành công, nhưng đổi mức log lại bị từ chối. Điều này chưa chứng minh tài khoản thiếu quyền. Một thao tác thay đổi trạng thái cần thỏa mãn các điều kiện khác nhau:

- Endpoint đã được bật và được công bố qua HTTP.
- Yêu cầu có danh tính hợp lệ và được cấp quyền.
- Nếu tuyến yêu cầu chống giả mạo, token CSRF phải hợp lệ.
- Phương thức HTTP, dữ liệu và tài nguyên đích phải phù hợp.

CSRF là **giả mạo yêu cầu từ một website khác** (Cross-Site Request Forgery). Nguy cơ xuất hiện khi trình duyệt tự gửi thông tin xác thực đến website đích, dù chủ tài khoản không chủ ý thực hiện thao tác. Vì vậy, “đã đăng nhập” không đồng nghĩa với “đã chủ ý đổi cấu hình”.

Bài này dùng **Spring Boot 3.3.x, Spring Security 6.3.x, Servlet/Spring MVC, Java 21**; ứng dụng và Actuator dùng chung cổng, đường dẫn mặc định `/actuator`. WebFlux có API cấu hình khác; không chép `HttpSecurity` sang ứng dụng reactive.

[Tài liệu Actuator 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.security) xác nhận mặc định có CSRF và việc tự khai báo `SecurityFilterChain` khiến bạn chịu trách nhiệm cấu hình bảo mật cho phần ứng dụng còn lại.

## 2. Phân biệt danh tính, quyền và cơ chế chống giả mạo

Hãy hình dung một trang quản trị cho phép nhân viên vận hành thay đổi mức log. Trình duyệt đã giữ cookie phiên đăng nhập. Nếu một trang khác khiến trình duyệt gửi yêu cầu đến trang quản trị và cookie được gửi kèm theo chính sách trình duyệt, máy chủ vẫn có thể nhận diện đúng nhân viên đó.

Máy chủ cần thêm một giá trị mà trang bên ngoài không tự cung cấp được. Với token CSRF, trang hợp lệ lấy token rồi chủ động gửi lại qua header hoặc tham số trên yêu cầu thay đổi trạng thái.

| Lớp kiểm tra | Câu hỏi trong tình huống đổi mức log |
| --- | --- |
| Xác thực | Ai đang yêu cầu? |
| Phân quyền | Người này có quyền vận hành không? |
| CSRF | Yêu cầu đáp ứng cơ chế chống giả mạo của phiên không? |
| Nghiệp vụ endpoint | Tên logger và mức log có hợp lệ không? |

Token CSRF không thay thế mật khẩu hoặc access token. Mật khẩu đúng cũng không thay thế token CSRF trên tuyến yêu cầu token.

**Cách thông tin xác thực đi vào yêu cầu** quyết định chính sách, không phải riêng tên công nghệ. Các trường hợp cookie và Basic được giải thích trong [tài liệu tổng quan CSRF của Spring Security](https://docs.spring.io/spring-security/reference/features/exploits/csrf.html).

| Cơ chế trên tuyến ghi/xóa | Chính sách phù hợp |
| --- | --- |
| Đăng nhập bằng form, nhận cookie phiên | Giữ CSRF và gửi token khi thay đổi trạng thái |
| JWT nằm trong cookie xác thực, trình duyệt tự gửi | Vẫn cần xét CSRF; JWT không làm cookie mất tính tự động |
| HTTP Basic có thể được trình duyệt dùng và lưu thông tin đăng nhập | Giữ CSRF hoặc thiết kế tuyến dành riêng cho trình khách máy |
| Bearer chỉ được trình khách chủ động đặt vào `Authorization`, không nhận danh tính từ cookie/Basic | Có thể miễn CSRF trong phạm vi đã cô lập và kiểm chứng |
| Cùng URL vừa nhận cookie vừa nhận Bearer | Không miễn toàn bộ URL chỉ vì có hỗ trợ Bearer |

`SessionCreationPolicy.STATELESS` chỉ nói về chính sách sử dụng phiên của Spring Security. Nó không ngăn bộ lọc khác đọc JWT từ cookie và không thay đổi hành vi gửi thông tin xác thực của trình duyệt. Do đó, stateless không đủ làm căn cứ tắt CSRF.

Việc bạn đang thử bằng curl cũng không chứng minh URL chỉ dành cho curl. Hãy xét các cách cùng tuyến có thể xác thực trong triển khai thật, kể cả proxy hoặc bộ lọc tùy chỉnh.

## 3. Thao tác đọc và thao tác thay đổi trạng thái

Một endpoint có thể chứa cả đọc và ghi:

| Ví dụ HTTP | Tác động |
| --- | --- |
| `GET /actuator/loggers/com.example.actuatorcsrf.probe` | Đọc cấu hình logger |
| `POST /actuator/loggers/com.example.actuatorcsrf.probe` | Thay đổi hoặc xóa mức log được cấu hình riêng |
| `GET /actuator/caches` | Đọc thông tin cache |
| `DELETE /actuator/caches/books` | Xóa các phần tử trong cache tên `books` |

POST đặt `configuredLevel`, còn POST với `{}` bỏ mức log riêng để kế thừa từ cha; xem [API loggers 3.3](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/loggers.html). DELETE làm rỗng cache, không xóa bean `CacheManager` hay định nghĩa cache; xem [API caches 3.3](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/caches.html).

Trong cấu hình CSRF mặc định, `GET`, `HEAD`, `OPTIONS`, `TRACE` được loại khỏi kiểm tra token. Các phương thức còn lại, thường gặp là `POST`, `PUT`, `PATCH`, `DELETE`, cần token nếu không có ngoại lệ. Điều này không cấp quyền truy cập hay bảo đảm endpoint hỗ trợ mọi phương thức đó.

Không thiết kế `GET /clear-cache` để tránh gửi token. Thao tác ghi ẩn trong GET làm hỏng giả định rằng đọc dữ liệu không gây thay đổi trạng thái.

Cũng cần phân biệt:

- Xóa dữ liệu cache dùng HTTP `DELETE`.
- Xóa mức log riêng vẫn dùng HTTP `POST` với `{}`.

CSRF quyết định theo yêu cầu HTTP và chính sách thực tế, không theo động từ tiếng Việt trong tên thao tác.

## 4. Phương án A: giữ CSRF khi dùng cookie hoặc Basic

Ví dụ dùng Basic để dễ thử từ dòng lệnh, đồng thời **giữ CSRF**. Nó minh họa cả việc gửi danh tính và duy trì phiên chứa token CSRF.

Đây là các tệp cho **một dự án Spring Boot 3.3.x tối thiểu đã có Gradle Wrapper và plugin Spring Boot**. Mã Spring cần dependency; không chạy bằng `javac SecurityConfig.java` đơn lẻ. Chỉ dùng một bộ cấu hình A hoặc B trong cùng lần thử.

### 4.1. Dependency và cấu hình thử nghiệm

Trong `build.gradle`, dùng dependency management của Spring Boot:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`src/main/resources/application.yml`:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,loggers,caches

spring:
  security:
    user:
      name: ops
      password: ${OPS_PASSWORD}
      roles: OPS

logging:
  level:
    com.example.actuatorcsrf.probe: INFO
~~~

Biến môi trường `OPS_PASSWORD` cung cấp mật khẩu lúc chạy. Không đặt mật khẩu vận hành thật vào tệp được commit. Ví dụ chỉ công bố ba endpoint phục vụ thí nghiệm.

Tạo các tệp Java dưới `src/main/java/com/example/actuatorcsrf/`.

`DemoApplication.java`:

~~~java
package com.example.actuatorcsrf;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.CacheManager;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("books");
    }
}
~~~

Bean cache giúp DELETE có tài nguyên thật để thử. Không cần `@EnableCaching` chỉ để truy cập trực tiếp cache này; annotation đó phục vụ cơ chế chặn lời gọi các phương thức có annotation cache.

### 4.2. Hai filter chain có phạm vi rõ ràng

`SecurityConfig.java`:

~~~java
package com.example.actuatorcsrf;

import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration(proxyBeanMethods = false)
public class SecurityConfig {
    @Bean
    @Order(1)
    SecurityFilterChain actuatorChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher(EndpointRequest.toAnyEndpoint())
            .authorizeHttpRequests(auth -> auth
                .anyRequest().hasRole("OPS")
            )
            .httpBasic(withDefaults())
            .csrf(withDefaults());
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/ops/csrf").hasRole("OPS")
                .anyRequest().denyAll()
            )
            .httpBasic(withDefaults())
            .csrf(withDefaults());
        return http.build();
    }
}
~~~

Chuỗi thứ nhất áp dụng cho Actuator; chuỗi thứ hai tiếp nhận phần còn lại. Chỉ chuỗi đầu tiên khớp với yêu cầu được sử dụng; các chuỗi không cộng dồn chính sách. Trong A, cả health cũng yêu cầu vai trò OPS: đây là lựa chọn của bài thử.

`hasRole("OPS")` kiểm tra authority `ROLE_OPS`. Cấu hình `roles: OPS` tạo vai trò tương ứng cho người dùng thử nghiệm. Cho phép quyền không bỏ qua bộ lọc CSRF.

Ứng dụng thật cần quy tắc riêng cho tuyến nghiệp vụ thay cho `denyAll()`. Không bỏ chuỗi dự phòng và trông chờ cấu hình tự động tiếp tục bảo vệ mọi URL.

### 4.3. Cấp token qua tuyến quản trị thông thường

`CsrfController.java`:

~~~java
package com.example.actuatorcsrf;

import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CsrfController {
    public record TokenView(String headerName, String token) {
    }

    @GetMapping("/ops/csrf")
    ResponseEntity<TokenView> csrf(CsrfToken csrfToken) {
        TokenView body = new TokenView(
            csrfToken.getHeaderName(),
            csrfToken.getToken()
        );
        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(body);
    }
}
~~~

`/ops/csrf` là controller của ứng dụng, không phải endpoint Actuator có sẵn. Nó chỉ cho OPS truy cập và trả `Cache-Control: no-store`.

Với mặc định đang dùng, token kỳ vọng nằm trong phiên HTTP. Đọc `getToken()` làm token được hiện thực hóa nếu trước đó còn được tải trì hoãn. Trình khách phải giữ cookie phiên lúc lấy token và gửi lại token đúng header được trả về.

Spring Security 6 có xử lý che token bằng giá trị ngẫu nhiên để giảm rủi ro BREACH. Không lấy chuỗi cookie phiên, UUID tự sinh hay token ở phiên khác để thay thế. Dùng token qua cơ chế máy chủ đã cung cấp. Repository, request handler và token trì hoãn được giải thích trong [tài liệu CSRF Servlet nhánh 6.3](https://raw.githubusercontent.com/spring-projects/spring-security/6.3.x/docs/modules/ROOT/pages/servlet/exploits/csrf.adoc).

Nếu dùng `CookieCsrfTokenRepository` cho giao diện JavaScript, phải thống nhất repository, cách đọc header và xử lý token với frontend. Chỉ có cookie chứa token chưa đủ: trình khách còn phải chủ động đưa token vào header mà máy chủ kiểm tra. Ví dụ hiện tại dùng repository mặc định theo phiên, không dùng cookie repository của SPA.

### 4.4. Thử POST và DELETE từ PowerShell

Ở terminal chạy ứng dụng:

~~~powershell
$env:OPS_PASSWORD = 'local-demo-only'
.\gradlew.bat bootRun
~~~

Mật khẩu này chỉ dành cho ứng dụng thử cục bộ. Mở terminal PowerShell thứ hai:

~~~powershell
$pair = 'ops:local-demo-only'
$encoded = [Convert]::ToBase64String(
    [Text.Encoding]::UTF8.GetBytes($pair)
)
$basicHeaders = @{ Authorization = "Basic $encoded" }
$base = 'http://localhost:8080'
$loggerUrl = "$base/actuator/loggers/com.example.actuatorcsrf.probe"

$read = Invoke-WebRequest -UseBasicParsing `
    -Uri $loggerUrl -Headers $basicHeaders
$read.StatusCode
~~~

Biểu thức cuối trả `200`; `configuredLevel` ban đầu là `INFO`. Đọc không cần token CSRF nhưng vẫn cần xác thực.

Gửi POST đúng tài khoản, chưa có token:

~~~powershell
try {
    Invoke-WebRequest -UseBasicParsing `
        -Uri $loggerUrl -Method Post `
        -Headers $basicHeaders -ContentType 'application/json' `
        -Body '{"configuredLevel":"DEBUG"}' | Out-Null
} catch {
    [int]$_.Exception.Response.StatusCode
}
~~~

Trong ứng dụng thử này, kết quả là `403`. Không chữa bằng `permitAll()`: danh tính không phải phần còn thiếu của yêu cầu thử.

Lấy token, giữ cookie và gửi lại:

~~~powershell
$tokenResponse = Invoke-WebRequest -UseBasicParsing `
    -Uri "$base/ops/csrf" -Headers $basicHeaders `
    -SessionVariable opsSession
$token = $tokenResponse.Content | ConvertFrom-Json

$writeHeaders = @{ Authorization = "Basic $encoded" }
$writeHeaders[$token.headerName] = $token.token

$changed = Invoke-WebRequest -UseBasicParsing `
    -Uri $loggerUrl -Method Post `
    -Headers $writeHeaders -WebSession $opsSession `
    -ContentType 'application/json' `
    -Body '{"configuredLevel":"DEBUG"}'
$changed.StatusCode

$deleted = Invoke-WebRequest -UseBasicParsing `
    -Uri "$base/actuator/caches/books" -Method Delete `
    -Headers $writeHeaders -WebSession $opsSession
$deleted.StatusCode
~~~

Hai trạng thái lần lượt là `204` và `204`. Không có response body là bình thường. Đọc lại logger bằng GET sẽ thấy `configuredLevel` là `DEBUG`.

Trong ví dụ, phiên giữ token CSRF; Basic header tiếp tục cung cấp danh tính trên từng yêu cầu. Không suy luận rằng chỉ mang cookie vừa nhận sẽ tự thay thế Basic.

Để bỏ mức log riêng, gửi POST cùng header và phiên, với body `{}`:

~~~powershell
Invoke-WebRequest -UseBasicParsing `
    -Uri $loggerUrl -Method Post `
    -Headers $writeHeaders -WebSession $opsSession `
    -ContentType 'application/json' -Body '{}' | Out-Null
~~~

Nếu mục tiêu là khôi phục một mức log riêng trước đó, phải đặt lại đúng giá trị cũ thay vì dùng `{}`.

## 5. Kiểm chứng cả thất bại và thành công

Muốn kiểm tra CSRF, giữ nguyên tài khoản, URL và body rồi thay đổi token hoặc phiên. Một POST trả 204 chỉ chứng minh một nhánh thành công.

Tạo `src/test/java/com/example/actuatorcsrf/ActuatorCsrfTest.java` cho phương án A:

~~~java
package com.example.actuatorcsrf;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = "spring.security.user.password=test-only")
@AutoConfigureMockMvc
class ActuatorCsrfTest {
    private static final String LOGGER =
        "/actuator/loggers/com.example.actuatorcsrf.probe";
    private static final String BODY = "{\"configuredLevel\":\"DEBUG\"}";

    @Autowired MockMvc mvc;
    @Autowired ObjectMapper mapper;
    @Autowired CacheManager cacheManager;

    private Cache books;

    @BeforeEach
    void seedCache() {
        books = cacheManager.getCache("books");
        assertNotNull(books);
        books.put("isbn", "draft");
    }

    @Test
    void getDoesNotRequireCsrfToken() throws Exception {
        mvc.perform(get(LOGGER).with(httpBasic("ops", "test-only")))
            .andExpect(status().isOk());
    }

    @Test
    void postWithoutTokenIsForbidden() throws Exception {
        mvc.perform(post(LOGGER)
                .with(httpBasic("ops", "test-only"))
                .contentType(MediaType.APPLICATION_JSON).content(BODY))
            .andExpect(status().isForbidden());
    }

    @Test
    void postWithInvalidTokenIsForbidden() throws Exception {
        mvc.perform(post(LOGGER)
                .with(httpBasic("ops", "test-only"))
                .with(csrf().asHeader().useInvalidToken())
                .contentType(MediaType.APPLICATION_JSON).content(BODY))
            .andExpect(status().isForbidden());
    }

    @Test
    void tokenFromControllerWorksWithItsSession() throws Exception {
        MvcResult result = mvc.perform(get("/ops/csrf")
                .with(httpBasic("ops", "test-only")))
            .andExpect(status().isOk())
            .andReturn();

        JsonNode token = mapper.readTree(
            result.getResponse().getContentAsString()
        );
        MockHttpSession session =
            (MockHttpSession) result.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(post(LOGGER)
                .with(httpBasic("ops", "test-only"))
                .session(session)
                .header(token.get("headerName").asText(),
                        token.get("token").asText())
                .contentType(MediaType.APPLICATION_JSON).content(BODY))
            .andExpect(status().isNoContent());
    }

    @Test
    void validCsrfDoesNotGrantOpsRole() throws Exception {
        mvc.perform(post(LOGGER)
                .with(user("reader").roles("READER"))
                .with(csrf().asHeader())
                .contentType(MediaType.APPLICATION_JSON).content(BODY))
            .andExpect(status().isForbidden());
    }

    @Test
    void validCsrfDoesNotAuthenticateAnonymousRequest() throws Exception {
        mvc.perform(post(LOGGER)
                .with(csrf().asHeader())
                .contentType(MediaType.APPLICATION_JSON).content(BODY))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void deleteWithoutTokenDoesNotEvictCache() throws Exception {
        mvc.perform(delete("/actuator/caches/books")
                .with(httpBasic("ops", "test-only")))
            .andExpect(status().isForbidden());
        assertNotNull(books.get("isbn"));
    }

    @Test
    void deleteWithTokenEvictsCache() throws Exception {
        mvc.perform(delete("/actuator/caches/books")
                .with(httpBasic("ops", "test-only"))
                .with(csrf().asHeader()))
            .andExpect(status().isNoContent());
        assertNull(books.get("isbn"));
    }
}
~~~

Chạy trong dự án thử:

~~~powershell
.\gradlew.bat test --tests com.example.actuatorcsrf.ActuatorCsrfTest
~~~

Kỳ vọng tám kiểm thử đạt. Không cố định toàn bộ log Gradle vì đường dẫn, thời gian và cảnh báo phụ thuộc môi trường.

Các trợ giúp `csrf()`, `asHeader()` và `useInvalidToken()` có trong [tài liệu kiểm thử CSRF](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html). Kiểm thử lấy token từ controller còn kiểm tra token thật cùng đúng phiên, thay vì chỉ dựa vào trợ giúp tạo yêu cầu.

`user("reader")` giả lập danh tính để cô lập kiểm tra quyền; nó không kiểm chứng mật khẩu Basic. MockMvc không mô phỏng đầy đủ cookie, SameSite hay CORS của trình duyệt. Nếu có giao diện web, cần thử thêm luồng đăng nhập và gửi token trên trình duyệt.

## 6. Phương án B: tuyến quản trị chỉ nhận Bearer header

Giả sử công cụ máy thực hiện tác vụ vận hành bằng access token. Chỉ chọn phương án này khi kiểm soát được các điều kiện:

- Token chỉ lấy từ header `Authorization: Bearer ...`.
- Tuyến không nhận danh tính từ phiên, cookie JWT, Basic hoặc cơ chế proxy tự gắn danh tính.
- Token được xác minh và có quyền vận hành.
- Ngoại lệ CSRF nằm trong các endpoint đã chọn; tuyến web khác giữ chính sách riêng.

**B thay thế A**, không thêm một chuỗi cùng `@Order(1)` vào A. Giữ `DemoApplication` và cấu hình exposure/cache. Thêm dòng sau trong block `dependencies`:

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
~~~

Thay cấu hình `spring.security.user` bằng:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: ${OPS_ISSUER_URI}
~~~

`OPS_ISSUER_URI` phải là issuer thật của môi trường thử, có cấu hình khám phá/JWK phù hợp. B cần hạ tầng cấp token, không dùng chuỗi bất kỳ thay cho JWT hợp lệ. Tùy chính sách hệ thống, bổ sung kiểm tra audience để token chỉ dùng cho dịch vụ dự định.

Thay nội dung `SecurityConfig.java`:

~~~java
package com.example.actuatorcsrf;

import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.server.resource.web.DefaultBearerTokenResolver;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.context.NullSecurityContextRepository;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration(proxyBeanMethods = false)
public class SecurityConfig {
    @Bean
    @Order(1)
    SecurityFilterChain machineActuatorChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher(EndpointRequest.to("loggers", "caches"))
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .securityContext(context -> context
                .securityContextRepository(new NullSecurityContextRepository())
            )
            .requestCache(AbstractHttpConfigurer::disable)
            .httpBasic(AbstractHttpConfigurer::disable)
            .formLogin(AbstractHttpConfigurer::disable)
            .logout(AbstractHttpConfigurer::disable)
            .authorizeHttpRequests(auth -> auth
                .anyRequest().hasAuthority("SCOPE_actuator.write")
            )
            .oauth2ResourceServer(resource -> resource
                .bearerTokenResolver(new DefaultBearerTokenResolver())
                .jwt(withDefaults())
            )
            .csrf(AbstractHttpConfigurer::disable);
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(EndpointRequest.to("health")).permitAll()
                .anyRequest().denyAll()
            )
            .csrf(withDefaults());
        return http.build();
    }
}
~~~

Lời gọi `csrf(...disable)` thuộc chuỗi chỉ khớp `loggers` và `caches`, gồm đường dẫn con của chúng. Health được phép đọc ở chuỗi dự phòng; các tuyến khác bị từ chối. `/ops/csrf` của A không được mở trong B và có thể bỏ khỏi dự án thử B.

Cả thao tác đọc và ghi của hai endpoint được chọn đều cần `SCOPE_actuator.write`. Đây là quy tắc đơn giản cho công cụ vận hành trong bài; ứng dụng thật có thể tách quyền đọc/ghi. Theo ánh xạ scope mặc định, scope `actuator.write` thành authority `SCOPE_actuator.write`; không truyền chuỗi đó cho `hasRole`.

`DefaultBearerTokenResolver` mặc định lấy Bearer từ header Authorization, không bật lấy token từ body/query. Có thể đối chiếu trong [mã nguồn resolver nhánh 6.3](https://raw.githubusercontent.com/spring-projects/spring-security/6.3.x/oauth2/oauth2-resource-server/src/main/java/org/springframework/security/oauth2/server/resource/web/DefaultBearerTokenResolver.java).

Một chi tiết triển khai: DSL OAuth2 Resource Server nhánh 6.3 tự đăng ký ngoại lệ CSRF cho yêu cầu mà resolver nhận diện có Bearer token. Ngoại lệ đó **không thay việc xác minh token**, cũng không tự miễn mọi yêu cầu cookie. Trong B, CSRF được tắt tường minh ở chuỗi hẹp để chính sách tuyến máy rõ ràng; không cần ngoại lệ toàn ứng dụng. Xem [OAuth2ResourceServerConfigurer nhánh 6.3](https://raw.githubusercontent.com/spring-projects/spring-security/6.3.x/config/src/main/java/org/springframework/security/config/annotation/web/configurers/oauth2/server/resource/OAuth2ResourceServerConfigurer.java).

### Kiểm chứng B

Sau khi cấu hình issuer và lấy token đủ scope, đặt token vào biến môi trường `OPS_ACCESS_TOKEN` ở terminal thử:

~~~powershell
$bearerHeaders = @{
    Authorization = "Bearer $env:OPS_ACCESS_TOKEN"
}
$response = Invoke-WebRequest -UseBasicParsing `
    -Uri 'http://localhost:8080/actuator/loggers/com.example.actuatorcsrf.probe' `
    -Method Post -Headers $bearerHeaders `
    -ContentType 'application/json' `
    -Body '{"configuredLevel":"DEBUG"}'
$response.StatusCode
~~~

Với token hợp lệ, đủ quyền, kỳ vọng `204` mà không cần token CSRF. Không in access token ra log.

| Tình huống POST/DELETE trong phạm vi B | Kỳ vọng |
| --- | --- |
| Không có Bearer, dù có cookie phiên cũ | 401 |
| Chỉ gửi Basic | 401 |
| Bearer hết hạn hoặc sai chữ ký | 401 |
| Bearer hợp lệ nhưng thiếu scope | 403 |
| Bearer hợp lệ, đủ scope, dữ liệu đúng, tài nguyên tồn tại | Thao tác được thực hiện; ví dụ trên trả 204 |

Nếu cookie cũ giúp ghi thành công khi thiếu Bearer, các điều kiện của B chưa đạt: kiểm tra chuỗi đang khớp, bộ lọc tùy chỉnh và proxy.

Trợ giúp `jwt()` của Spring Security Test giả lập danh tính JWT; nó không chứng minh chữ ký, issuer hay thời hạn được kiểm tra. Cần thêm yêu cầu với token ký thật và token hết hạn/sai chữ ký để kiểm tra đường xác thực thực tế.

## 7. Ngoại lệ phải bám theo ranh giới xác thực

Có thể dùng `ignoringRequestMatchers(...)` nếu chỉ một số tuyến trong một chuỗi chắc chắn không dựa vào thông tin xác thực tự gửi. Phải kiểm chứng cách xác thực tại chính các URL được bỏ qua.

Không bỏ qua toàn bộ `/actuator/**` trong một chuỗi vẫn cho phép Basic hoặc phiên quản trị ghi dữ liệu: luồng trình duyệt cũng mất kiểm tra token.

Không tự viết quy tắc “có header Authorization là bỏ CSRF” rồi vẫn cho fallback sang cookie khi token không hợp lệ. Một header do trình khách cung cấp không chứng minh cơ chế xác thực mong muốn đã thành công.

Nếu cùng endpoint buộc phải nhận cookie và Bearer, có thể giữ CSRF cho luồng cookie hoặc tách điểm truy cập/chính sách xác thực. Khi trộn DSL Resource Server, phải xét cả ngoại lệ framework đăng ký; chỉ thêm `csrf(withDefaults())` không có nghĩa mọi yêu cầu Bearer bị buộc gửi token.

Đổi `management.endpoints.web.base-path` làm URL thay đổi. Matcher `EndpointRequest` giúp bám theo endpoint thay vì viết cứng tiền tố, nhưng vẫn phải thử đường dẫn thật. Nếu dùng cổng hoặc context quản trị riêng, kiểm chứng chính sách trong context đó; không mặc định hai chuỗi của bài bao phủ mọi cách triển khai.

## 8. Chẩn đoán lỗi mà không làm yếu chính sách

### 8.1. Hai yêu cầu cùng 403 có thể khác nguyên nhân

Trong A:

1. OPS gửi POST thiếu token: CSRF có thể chặn trước phân quyền.
2. READER gửi POST có token hợp lệ: qua CSRF nhưng thiếu vai trò.
3. OPS dùng token của phiên khác: token không khớp.
4. Phiên và token đúng nhưng body sai: có thể đến endpoint rồi bị từ chối vì dữ liệu.

Không dùng mỗi mã trạng thái để suy ngược toàn bộ nguyên nhân. So sánh các yêu cầu có kiểm soát và quan sát máy chủ.

Trong ứng dụng thử cục bộ, có thể tạm bật:

~~~yaml
logging:
  level:
    org.springframework.security.web.csrf: DEBUG
~~~

Ghép vào block `logging.level` hiện có, không tạo hai khóa `logging` trùng nhau. Đối chiếu thông báo token thiếu/sai với chuỗi bảo mật và quyền đang áp dụng. Giảm mức log sau điều tra; tránh ghi thông tin xác thực.

| Dấu hiệu | Hướng kiểm tra |
| --- | --- |
| GET được, POST của cùng OPS bị 403 | Token thiếu hoặc sai phiên? |
| Token đúng, READER vẫn 403 | Quyền/authority có đúng không? |
| POST chưa đăng nhập cũng 403 trong A | CSRF có thể chặn trước; dùng token hợp lệ để cô lập xác thực |
| Bearer hết hạn bị 401 trong B | Kiểm tra xác minh token, không chữa bằng token CSRF |
| 404/405 sau khi qua bảo mật | Exposure, tên endpoint, phương thức, tài nguyên |
| 400/415 sau khi qua bảo mật | Body, tham số, Content-Type |

Bộ lọc có thể chặn trước MVC nên URL sai cũng có thể nhận 401/403. Bảng là hướng điều tra, không phải quan hệ một-một giữa mã lỗi và nguyên nhân.

### 8.2. Những suy luận dễ dẫn đến cấu hình sai

- **“Có CORS nên không cần CSRF.”** Một số yêu cầu khác origin vẫn được gửi dù trang bên ngoài không được đọc phản hồi. Chặn đọc không đồng nghĩa chặn thay đổi trạng thái.
- **“Chỉ nhận JSON hoặc DELETE thì luôn an toàn.”** Preflight và kiểm tra Content-Type có giá trị, nhưng phải xét cơ chế xác thực, các tuyến ghi khác và method override nếu có.
- **“JWT nghĩa là miễn CSRF.”** Phải hỏi token ở header chủ động hay cookie tự gửi.
- **“Có SameSite/HttpOnly/Secure là xong.”** HttpOnly hạn chế JavaScript đọc cookie, Secure giới hạn kênh truyền, SameSite phụ thuộc quan hệ site. Chúng không tự cấp quyền hay cung cấp token CSRF hợp lệ.
- **“Mạng nội bộ không liên quan trình duyệt.”** Trình duyệt trên máy được vào mạng đó vẫn có thể là đường gửi yêu cầu; phải xét mô hình sử dụng thật.
- **“Tắt CSRF rồi 204 là đã sửa bảo mật.”** Nhánh thành công chưa chứng minh yêu cầu thiếu danh tính, thiếu quyền hoặc bị giả mạo bị từ chối.
- **“GET không cần CSRF nên mở mọi GET Actuator.”** Quyền đọc và dữ liệu nhạy cảm vẫn cần chính sách riêng.

CSRF trong bài là cơ chế trên HTTP. JMX có chính sách truy cập riêng; header CSRF của HTTP không bảo vệ kênh JMX.

## 9. Bài tập tự kiểm tra

1. Với A, đổi token thành chuỗi bất kỳ nhưng giữ Basic đúng. Giải thích vì sao kết quả khác yêu cầu có token thật.
2. Lấy token ở hai phiên rồi tráo token và cookie. Quan hệ token–phiên bị phá vỡ ở đâu?
3. Gửi DELETE cache `books` bằng OPS thiếu token, sau đó gửi với token đúng. Kiểm tra trạng thái HTTP lẫn phần tử cache.
4. Giữ token đúng, đổi danh tính thành READER. Vì sao token không nâng quyền?
5. Chọn B nhưng thêm bộ lọc đọc JWT từ cookie. Vì sao phải xem lại căn cứ miễn CSRF?
6. Chuyển sang STATELESS nhưng vẫn xác thực bằng cookie. Điều kiện nào của nguy cơ CSRF còn tồn tại?

Bạn nắm được bài khi chọn chính sách từ **cách thông tin xác thực được gửi**, kiểm chứng riêng xác thực/quyền/CSRF và giới hạn ngoại lệ đúng tuyến, thay vì chỉ tắt kiểm tra để một lệnh POST chạy thành công.
