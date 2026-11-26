# Nạp SecurityFilterChain cùng FilterChainProxy vào context kiểm thử

## Mục tiêu bài học

Trong mô-đun **SPRING_SECURITY_TESTING**, chúng ta kiểm chứng xác thực, phân quyền và cơ chế bảo vệ HTTP trên ứng dụng Servlet và Reactive bằng `spring-security-test`. Chương **Thiết lập MockMvc** tập trung vào ứng dụng **Servlet/Spring MVC**: một phép thử bảo mật chỉ đáng tin khi request thực sự chạy qua các filter mà ứng dụng cần sử dụng.

Bài này hướng dẫn nạp `SecurityFilterChain` vào Spring test context, hiểu vai trò của `FilterChainProxy` và nối filter bảo mật vào `MockMvc`. Sau khi học, bạn có thể:

1. Phân biệt **`SecurityFilterChain`**, **`FilterChainProxy`**, bean **`springSecurityFilterChain`** và **`DelegatingFilterProxy`**.
2. Tạo `SecurityFilterChain` trong context kiểm thử bằng cấu hình Spring Security kiểu bean.
3. Kết nối các filter của context với `MockMvc` qua `@AutoConfigureMockMvc` hoặc `springSecurity()`.
4. Viết kiểm thử chứng minh filter đã tham gia: ẩn danh bị từ chối, sai quyền bị chặn, đủ quyền được phép và CSRF được kiểm tra.
5. Tìm nguyên nhân khi test trả về 200 dù route phải được bảo vệ, hoặc trả về 403 ngoài mong đợi.
6. Hiểu thứ tự chọn chuỗi bảo mật khi ứng dụng có nhiều `SecurityFilterChain`.

## 1. Các đối tượng trong chuỗi lọc bảo mật

Các tên rất giống nhau nhưng giữ vai trò khác nhau:

| Đối tượng | Vai trò | Ai thường tạo? |
| --- | --- | --- |
| `SecurityFilterChain` | Mô tả **request nào khớp** với chuỗi và **danh sách filter** phải thực thi | Bean từ cấu hình `HttpSecurity`; thường có implementation `DefaultSecurityFilterChain` |
| `FilterChainProxy` | Chọn **SecurityFilterChain khớp đầu tiên** rồi thực thi các filter trong chuỗi đó | Hạ tầng Spring Security khi web security được kích hoạt |
| Bean tên `springSecurityFilterChain` | Điểm vào dạng `jakarta.servlet.Filter` để container hoặc MockMvc gọi hệ thống filter bảo mật | Cấu hình hạ tầng Spring Security; tùy phiên bản có thể là `FilterChainProxy` hoặc filter bọc nó |
| `DelegatingFilterProxy` | Cầu nối từ servlet filter của container đến filter bean nằm trong Spring context | Tích hợp servlet container / cấu hình đăng ký filter |
| `SecurityContext` | Chứa `Authentication` của lần xử lý hiện tại | Các authentication filter, Spring Security Test hoặc code ứng dụng phù hợp |

Một mô hình luồng xử lý:

~~~mermaid
flowchart TB
    A["Request của MockMvc<br/>hoặc servlet container"] --> B["Bộ lọc bảo mật được đăng ký<br/>(bean springSecurityFilterChain)"]
    B --> C["FilterChainProxy<br/>hoặc đường ủy quyền đến nó"]
    C --> D{"SecurityFilterChain nào<br/>khớp đầu tiên?"}
    D --> E["Chuỗi cho /api/admin/**"]
    D --> F["Chuỗi cho /api/**"]
    D --> G["Chuỗi mặc định / fallback"]
    E --> H["Các security filters được chọn"]
    F --> H
    G --> H
    H --> I["DispatcherServlet / Controller<br/>nếu request được cho đi tiếp"]
~~~

**`SecurityFilterChain` không phải đối tượng được truyền thẳng tới servlet container.** Nó mô tả một chuỗi. `FilterChainProxy` (hoặc filter wrapper bao quanh nó) là phần thực thi và điều phối các chuỗi. Trong cấu hình thông thường, các bean `SecurityFilterChain` được Spring Security thu thập khi dựng bộ lọc đầu vào mang tên `springSecurityFilterChain`.

Trên server thật, `DelegatingFilterProxy` thường là cầu nối từ servlet container sang bean Spring có tên đó. Trong test `MockMvc`, tích hợp `springSecurity()` hoặc cấu hình tự động của Spring Boot sẽ đưa Spring Security vào pipeline mock; **không cần mở socket hay khởi động một server HTTP thật**.

**Lưu ý về kiểu bean:** Đừng giả định ở mọi phiên bản rằng `context.getBean("springSecurityFilterChain")` có thể ép kiểu trực tiếp thành `FilterChainProxy`. API ổn định cho mục tiêu gắn filter là `jakarta.servlet.Filter`; Spring Security có thể đặt thêm filter wrapper ở bên ngoài. Chỉ dùng API riêng của `FilterChainProxy` nếu object thực sự có kiểu đó.

## 2. Quy trình nạp filter vào kiểm thử

Để một request do `MockMvc` tạo ra đi qua kiểm tra quyền HTTP, cần bảo đảm **ba mắt xích**:

1. **Tạo chính sách bảo mật:** một hoặc nhiều bean `SecurityFilterChain` được định nghĩa và nhận đúng cấu hình `HttpSecurity`.
2. **Tải cấu hình vào test context:** Spring web security tạo filter đầu vào `springSecurityFilterChain` từ những chuỗi nói trên; test sử dụng đúng context đó.
3. **Gắn filter với MockMvc:** instance `MockMvc` thực sự đăng ký filter đầu vào và tích hợp `SecurityContext` phục vụ phép thử.

~~~text
@Bean SecurityFilterChain
    ↓ Spring Security web configuration
springSecurityFilterChain (Filter; thường chứa FilterChainProxy)
    ↓ @AutoConfigureMockMvc hoặc .apply(springSecurity())
MockMvc.perform(request)
    ↓ FilterChainProxy chọn chuỗi theo RequestMatcher
authentication / authorization / CSRF / headers / ...
    ↓ nếu được chấp nhận
DispatcherServlet → controller
~~~

Thiếu mắt xích 1 hoặc 2 có thể khiến test dùng **chuỗi khác** với mong đợi. Thiếu mắt xích 3 có thể khiến controller chạy trực tiếp và trả 200 kể cả khi người dùng ẩn danh.

## 3. Ví dụ hoàn chỉnh: tải SecurityFilterChain bằng Spring Boot

Ta có API gồm endpoint công khai, endpoint dành riêng cho `ADMIN` và thao tác `POST` phải có CSRF token. Trong ví dụ này, Spring Security dùng **HTTP Basic** để kết quả của request ẩn danh được thể hiện rõ bằng 401.

### 3.1. Cấu hình ứng dụng Servlet

Tệp `src/main/java/example/DemoApplication.java`:

~~~java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}

@RestController
class ApiController {
    @GetMapping("/api/public")
    String publicInfo() {
        return "public";
    }

    @GetMapping("/api/admin")
    String adminInfo() {
        return "admin";
    }

    @PostMapping("/api/admin/orders")
    ResponseEntity<Void> createOrder() {
        return ResponseEntity.status(HttpStatus.CREATED).build();
    }
}
~~~

Tệp `src/main/java/example/SecurityConfiguration.java`:

~~~java
package example;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
public class SecurityConfiguration {
    @Bean
    SecurityFilterChain apiSecurityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public").permitAll()
                .requestMatchers("/api/admin", "/api/admin/**")
                    .hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

Ở đây, `http.build()` trả về một `SecurityFilterChain`. Spring Security web configuration đưa chuỗi này vào hạ tầng filter dùng cho ứng dụng. Bean được đặt tên `apiSecurityFilterChain` vì tên phương thức `@Bean` là như vậy; **đây không phải** bean tên `springSecurityFilterChain`. Bean `springSecurityFilterChain` là điểm vào chung do Spring Security tạo để điều phối các chuỗi bảo mật.

Ví dụ giữ cấu hình CSRF mặc định để kiểm tra hiệu lực bảo vệ của các HTTP method có thể thay đổi dữ liệu. `@EnableWebSecurity` thể hiện rõ việc kích hoạt hạ tầng web security; trong ứng dụng Spring Boot có starter bảo mật, auto-configuration cũng hỗ trợ kích hoạt cơ chế này.

Các dependency Gradle điển hình:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-security")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.security:spring-security-test")
}
~~~

Với Maven, dùng các artifact tương ứng và đặt hai thư viện kiểm thử ở scope `test`. Ví dụ Java phía dưới giả định dự án Spring Boot Servlet đã có các dependency này và dùng JUnit Jupiter/AssertJ từ starter test.

### 3.2. Tạo MockMvc từ context có các filter

Tệp `src/test/java/example/ApiSecurityTest.java`:

~~~java
package example;

import jakarta.servlet.Filter;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
class ApiSecurityTest {
    @Autowired
    MockMvc mockMvc;

    @Autowired
    ApplicationContext context;

    @Test
    void securityBeansAreInTheContext() {
        assertThat(context.getBeansOfType(SecurityFilterChain.class))
            .containsKey("apiSecurityFilterChain");

        // Filter đầu vào; không phụ thuộc việc nó có bị bọc hay không.
        assertThat(context.getBean("springSecurityFilterChain"))
            .isInstanceOf(Filter.class);
    }

    @Test
    void anonymousCanReadPublicEndpoint() throws Exception {
        mockMvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void anonymousCannotReadAdminEndpoint() throws Exception {
        mockMvc.perform(get("/api/admin"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(roles = "READER")
    void readerCannotReadAdminEndpoint() throws Exception {
        mockMvc.perform(get("/api/admin"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminCanReadAdminEndpoint() throws Exception {
        mockMvc.perform(get("/api/admin"))
            .andExpect(status().isOk())
            .andExpect(content().string("admin"));
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminPostWithoutCsrfIsRejected() throws Exception {
        mockMvc.perform(post("/api/admin/orders"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminPostWithCsrfIsAccepted() throws Exception {
        mockMvc.perform(post("/api/admin/orders").with(csrf()))
            .andExpect(status().isCreated());
    }
}
~~~

`@SpringBootTest(webEnvironment = MOCK)` tải application context trong môi trường web giả lập và **không chạy embedded HTTP server trên cổng TCP**. `@AutoConfigureMockMvc` tạo `MockMvc` và theo mặc định đăng ký các filter có trong context (`addFilters = true`). Spring Security Test hỗ trợ đưa `@WithMockUser` vào `SecurityContext` tương ứng.

Phép thử `securityBeansAreInTheContext()` xác nhận hai tầng cấu hình: bean chính sách `SecurityFilterChain` do ứng dụng khai báo và bean filter đầu vào `springSecurityFilterChain`. Tuy nhiên **sự tồn tại của bean trong context chưa đủ chứng minh MockMvc đã chạy qua filter đó**. Các test ẩn danh/thiếu quyền/CSRF bên cạnh xác nhận kết quả bảo mật thực sự tại endpoint.

### 3.3. Ý nghĩa kết quả

| Test case | Kỳ vọng | Cơ chế cần chạy |
| --- | --- | --- |
| `GET /api/public` không đăng nhập | 200 | `permitAll()` |
| `GET /api/admin` không đăng nhập | 401 | Entry point HTTP Basic |
| `GET /api/admin` với `READER` | 403 | `AuthorizationFilter` kiểm tra `ROLE_ADMIN` |
| `GET /api/admin` với `ADMIN` | 200 | Người dùng đã xác thực, đủ quyền |
| `POST /api/admin/orders` với `ADMIN`, thiếu token | 403 | `CsrfFilter` |
| `POST /api/admin/orders` với `ADMIN`, token hợp lệ | 201 | CSRF hợp lệ và đủ quyền |

Nếu chỉ dùng test `@WithMockUser(roles = "ADMIN")` và kiểm tra 200, một pipeline thiếu filter có thể vẫn vượt qua vì controller trả 200. **Ca bị từ chối** là bằng chứng quan trọng để phát hiện cấu hình MockMvc thiếu bảo mật.

> Các status 401/403 trong ví dụ gắn với cấu hình **HTTP Basic** và CSRF mặc định. Nếu ứng dụng dùng form login hoặc tùy chỉnh `AuthenticationEntryPoint`, request ẩn danh có thể nhận 302 redirect hoặc phản hồi khác. Hãy xác định contract bảo mật của ứng dụng trước khi viết assert.

## 4. Tự nối Spring Security vào MockMvc khi dùng builder

Khi không dùng `@AutoConfigureMockMvc` mà tự xây MockMvc từ `WebApplicationContext`, áp dụng cấu hình `springSecurity()`:

~~~java
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.context.WebApplicationContext;

import static org.springframework.security.test.web.servlet.setup.SecurityMockMvcConfigurers.springSecurity;
import static org.springframework.test.web.servlet.setup.MockMvcBuilders.webAppContextSetup;

@Autowired
WebApplicationContext webContext;

MockMvc securedMockMvc = webAppContextSetup(webContext)
    .apply(springSecurity())
    .build();
~~~

`SecurityMockMvcConfigurers.springSecurity()` tìm bean `springSecurityFilterChain` trong `WebApplicationContext`, đăng ký filter và tích hợp xử lý security context cho phép thử. Điều kiện là **context đã có hạ tầng Spring Security phù hợp**; cấu hình này không tự sinh ra các bean bảo mật bị thiếu.

Đối chiếu:

~~~java
// Có WebApplicationContext nhưng thiếu tích hợp filter bảo mật:
MockMvc incompleteMvc = webAppContextSetup(webContext)
    .build();

// Có WebApplicationContext và tích hợp Spring Security:
MockMvc securedMvc = webAppContextSetup(webContext)
    .apply(springSecurity())
    .build();
~~~

Hai đối tượng có thể gọi cùng controller nhưng khác kết quả phân quyền. Nếu bạn đã dùng `@AutoConfigureMockMvc` và inject `MockMvc` do Boot tạo, không cần tự tạo thêm một instance chỉ để gọi `springSecurity()`. Tránh đăng ký lặp cùng filter qua nhiều cách tích hợp trong một builder vì có thể gây lỗi thứ tự/filter bị gọi nhiều lần.

### Khi dùng @WebMvcTest

`@WebMvcTest` tạo **MVC slice context**: phù hợp kiểm tra một controller và phần MVC/Security nằm trong slice đó. Tuy nhiên, không được mặc nhiên coi mọi `SecurityFilterChain` hoặc dependency của ứng dụng đầy đủ đều được nạp.

Ví dụ sử dụng controller và cấu hình của mục 3:

~~~java
@WebMvcTest(ApiController.class)
@Import(SecurityConfiguration.class)
class ApiMvcSliceSecurityTest {
    @Autowired
    MockMvc mockMvc;

    @Test
    void anonymousCannotReadAdminEndpoint() throws Exception {
        mockMvc.perform(get("/api/admin"))
            .andExpect(status().isUnauthorized());
    }
}
~~~

Các import trong ví dụ rút gọn gồm `org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest`, `org.springframework.context.annotation.Import`, `org.springframework.beans.factory.annotation.Autowired`, JUnit `@Test`, cùng static imports của MockMvc. `@Import(SecurityConfiguration.class)` làm rõ cấu hình bảo mật nào được đưa vào slice. Nếu controller có service, repository hoặc bean riêng, hãy cấp đúng dependency kiểm thử; slice không tự tải toàn bộ ứng dụng.

Khi có nhu cầu xác minh chính xác sự tích hợp của nhiều bean và filter trong ứng dụng, `@SpringBootTest` + `@AutoConfigureMockMvc` thường phản ánh phạm vi rộng hơn. Nhưng ngay cả cách này cũng chỉ phản ánh **test context** với profile, properties và những bean đã thực sự được tải.

## 5. Khi có nhiều SecurityFilterChain: chọn chuỗi đầu tiên khớp

Một hệ thống có thể cần chính sách riêng cho trang quản trị, API và các route khác. Spring Security cho phép tạo nhiều bean `SecurityFilterChain` với `@Order` khác nhau.

Ví dụ minh họa **thay thế** bean `apiSecurityFilterChain` ở mục 3 bằng ba bean dưới đây (không khai báo đồng thời cả hai bộ cấu hình):

~~~java
@Bean
@Order(1)
SecurityFilterChain adminChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/admin", "/api/admin/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().hasRole("ADMIN")
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}

@Bean
@Order(2)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/public").permitAll()
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}

@Bean
@Order(3)
SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

Các phương thức này nằm trong một class `@Configuration` có bật web security; cần import `org.springframework.core.annotation.Order` cùng những kiểu Spring Security đã dùng ở mục 3. Với các chain trên, CSRF vẫn mặc định có hiệu lực ở các method cần bảo vệ.

Trong quá trình xử lý, `FilterChainProxy` kiểm tra các chuỗi theo thứ tự ưu tiên rồi sử dụng **chuỗi khớp đầu tiên**. Nó không tiếp tục thử chuỗi thứ hai chỉ vì người dùng bị từ chối bởi chuỗi đầu tiên.

| Request | SecurityFilterChain được chọn | Lý do |
| --- | --- | --- |
| `GET /api/admin` | `adminChain` | Khớp route quản trị ở ưu tiên 1 |
| `GET /api/admin/audit` | `adminChain` | Khớp `/api/admin/**` |
| `GET /api/public` | `apiChain` | Không khớp admin, khớp `/api/**` |
| `GET /settings` | `fallbackChain` | Không khớp hai chuỗi có `securityMatcher` |

**Phân biệt hai loại matcher:**

- `http.securityMatcher(...)` xác định **toàn bộ chain này có áp dụng cho request không**.
- `authorizeHttpRequests(...).requestMatchers(...)` chọn **quy tắc authorization bên trong chain đã được chọn**.

Đặt một chain quá rộng (`/**`) ở ưu tiên cao có thể khiến chain phía sau **không bao giờ được chọn**. Ngược lại, nếu chỉ định `securityMatcher("/api/**")` mà không có fallback, các URL ngoài `/api/**` có thể **không khớp chuỗi Spring Security nào**. Đó là lý do nên kiểm tra cả request ngoài vùng matcher và xác định rõ chính sách fallback.

Sơ đồ chọn chuỗi:

~~~mermaid
flowchart TD
    A["GET /api/admin/audit"] --> B{"adminChain khớp?"}
    B -->|Có| C["Dùng adminChain"]
    B -->|Không| D{"apiChain khớp?"}
    D -->|Có| E["Dùng apiChain"]
    D -->|Không| F["Dùng fallbackChain"]
    C --> G["Chạy filters của chuỗi đã chọn"]
    E --> G
    F --> G
    G --> H{"Được phép?"}
    H -->|Có| I["Controller"]
    H -->|Không| J["401 / 403 hoặc phản hồi theo entry point"]
~~~

## 6. Xác minh FilterChainProxy đã được nạp và được sử dụng

Một quy trình chẩn đoán hữu ích đi từ **bean → gắn filter → phản hồi HTTP**:

**Bước 1 — Xác nhận bean chính sách tồn tại.** Có thể dùng `context.getBeansOfType(SecurityFilterChain.class)` để xác định chain nào có trong test context. Với cấu hình ví dụ, phải tìm thấy bean tên `apiSecurityFilterChain`.

**Bước 2 — Xác nhận filter đầu vào tồn tại.** `context.getBean("springSecurityFilterChain")` phải trả về `jakarta.servlet.Filter`. Điều này chứng minh Spring Security đã tạo entry filter cho context. Nó **chưa chứng minh** MockMvc được gắn filter đó.

**Bước 3 — Xác nhận MockMvc đăng ký filter.** Kiểm tra bạn đang sử dụng `@AutoConfigureMockMvc` với mặc định `addFilters = true` hoặc tự dựng bằng `webAppContextSetup(context).apply(springSecurity())`. Nếu dựng qua `standaloneSetup(...)`, bạn phải tích hợp filter một cách có chủ ý; standalone không tự thừa hưởng toàn bộ filter từ ứng dụng.

**Bước 4 — Thử một yêu cầu chắc chắn bị từ chối.** Một `GET /api/admin` ẩn danh phải nhận 401 với ví dụ HTTP Basic. Sau đó thử `READER` nhận 403 và `ADMIN` nhận 200 để loại trừ trường hợp endpoint bị sai mapping hoặc controller hỏng. Thêm request `POST` thiếu CSRF để quan sát `CsrfFilter`.

**Bước 5 — Quan sát log filter khi cần.** Có thể bật log của `org.springframework.security.web.FilterChainProxy` ở mức `DEBUG` hoặc `TRACE` trong cấu hình **test** để theo dõi request nào được áp dụng filter. Ví dụ property:

~~~properties
logging.level.org.springframework.security.web.FilterChainProxy=TRACE
~~~

Log giúp điều tra thứ tự và matcher nhưng không thay thế các assertion về phản hồi. Tránh phụ thuộc vào nguyên văn log vì thông điệp có thể thay đổi theo phiên bản Spring Security.

Nếu muốn xem danh sách chain tại runtime, `FilterChainProxy#getFilterChains()` là API thích hợp **khi bạn thực sự có một object kiểu `FilterChainProxy`**. Không ép kiểu mù quáng từ bean `springSecurityFilterChain` vì lớp bao ngoài của bean này có thể thay đổi.

## 7. Các tình huống lỗi và cách xử lý

| Hiện tượng | Khả năng thường gặp | Cách xác minh/sửa |
| --- | --- | --- |
| `GET /api/admin` ẩn danh trả 200 | MockMvc không có Spring Security filter hoặc request không khớp chain nào | Xem `addFilters`, `springSecurity()`, `securityMatcher` và test ẩn danh |
| Không tìm thấy bean `springSecurityFilterChain` | Web security config chưa được nạp, thiếu starter/cấu hình cần thiết hoặc slice test bị giới hạn | Kiểm tra dependency, `@EnableWebSecurity`/Boot auto-configuration, `@Import` trong slice |
| Bean `SecurityFilterChain` đã có nhưng request vẫn đi qua | Filter đầu vào chưa được gắn với instance MockMvc, hoặc matcher loại request ra | Kiểm tra cách dựng MockMvc và phạm vi `securityMatcher` |
| `POST` của `ADMIN` trả 403 | Thiếu hoặc sai CSRF token, hoặc không đủ quyền ở một lớp khác | Thử `with(csrf())` và tách riêng test thiếu/CSRF sai |
| Request ẩn danh trả 302 thay vì 401 | Ứng dụng dùng form login / redirect entry point | Assert redirect phù hợp cấu hình thực tế |
| Test slice 401/403 khác test full context | Slice thiếu/có thêm SecurityFilterChain, filter hoặc cấu hình khác | Kiểm tra bean trong từng context, import cấu hình mục tiêu |
| Không đúng chain khi có nhiều chain | Thứ tự `@Order` sai hoặc `securityMatcher` quá rộng | Kiểm tra chain nào khớp đầu tiên và bổ sung test từng vùng đường dẫn |
| Một filter bị gọi nhiều lần | Đăng ký filter trùng khi dùng Boot tự cấu hình và builder thủ công | Chỉ tích hợp filter theo một cơ chế phù hợp cho mỗi MockMvc |
| `@WithMockUser` cho 200, token thật vẫn bị 401 | `@WithMockUser` bỏ qua xác thực thực tế | Thêm test gửi credential/bearer token qua authentication filter/decoder thật |

Ví dụ lỗi đặc biệt dễ mắc:

~~~java
@AutoConfigureMockMvc(addFilters = false) // Không phù hợp để chứng minh phân quyền HTTP.
~~~

Cấu hình này có thể phù hợp cho một số kiểm thử MVC không quan tâm filter, nhưng nếu dùng làm bằng chứng API đã được bảo vệ, kết luận sẽ thiếu cơ sở.

Tương tự, `standaloneSetup(controller)` không tự nạp `SecurityFilterChain`; một `@WithMockUser` trên test không tự bổ sung filter còn thiếu. Nếu bạn chủ động dùng một filter thực với standalone, phải cung cấp đúng bean filter và hỗ trợ Spring Security Test tương ứng. Khi mục tiêu là kiểm tra policy của ứng dụng, thiết lập từ web context thường đơn giản và đáng tin hơn.

## 8. SecurityContext, JWT/OAuth2/OIDC và giới hạn của phép thử

`@WithMockUser` và `with(user(...))` tạo người dùng đã xác thực để thử **authorization**. Với resource server, `with(jwt())` có thể tạo `JwtAuthenticationToken` giả lập; `oauth2Login()` và `oidcLogin()` mô phỏng principal sau login. Những công cụ này hữu ích để thử chính sách sau xác thực, nhưng **không kiểm chứng** mật khẩu, chữ ký JWT, hạn dùng token, issuer/audience, authorization code flow hoặc callback thực với nhà cung cấp danh tính.

Để kiểm tra **authentication**, vẫn có thể dùng MockMvc với filter chain thật, gửi header `Authorization` chứa thông tin hợp lệ hoặc không hợp lệ, để hệ thống xử lý qua `AuthenticationProvider`/`JwtDecoder` và các filter đã nạp. MockMvc không có socket HTTP thật nhưng vẫn có thể chạy logic xác thực trong JVM. Chỉ khi cần xác minh TLS, proxy, servlet container hoặc giao tiếp mạng, hãy thêm kiểm thử với `@SpringBootTest(webEnvironment = RANDOM_PORT)` và HTTP client thật.

### Phân biệt với Reactive/WebFlux

Ứng dụng **Reactive** không sử dụng servlet `SecurityFilterChain` và `FilterChainProxy` của `MockMvc` làm cơ chế bảo mật chính. Trong WebFlux, các thành phần tương ứng là **`SecurityWebFilterChain`** và **`WebFilterChainProxy`**, được dùng cùng `WebTestClient` và các tiện ích reactive của `spring-security-test` (ví dụ `mockUser()` hoặc `mockJwt()`).

Khi kiểm thử WebFlux, hãy tạo client gắn với reactive application context và áp dụng Spring Security test configurer tương ứng. Nếu cần HTTP thực, dùng `WebTestClient.bindToServer()`. Không áp dụng mẫu `MockMvcBuilders.webAppContextSetup(...).apply(springSecurity())` của Servlet cho pipeline Reactive.

## 9. Bài tập thực hành

1. **Nạp đúng filter:** Dựng một test `@SpringBootTest` nhưng tạo `MockMvc` bằng `webAppContextSetup(context).build()`. Quan sát test truy cập admin ẩn danh, sau đó thêm `.apply(springSecurity())` và giải thích thay đổi.
2. **Thử đầy đủ ba trạng thái:** Với `GET /api/admin`, viết các ca ẩn danh, `@WithMockUser(roles = "READER")` và `@WithMockUser(roles = "ADMIN")`. Chứng minh kết quả 401/403/200 trong cấu hình HTTP Basic.
3. **Kiểm tra CSRF:** Với `POST /api/admin/orders`, so sánh `with(csrf())`, không có token và `with(csrf().useInvalidToken())`. Phân biệt lỗi token với lỗi thiếu quyền.
4. **Thử thứ tự chuỗi:** Tạo hai chain `/api/admin/**` và `/api/**`, đổi `@Order` rồi ghi nhận sự thay đổi về chain được chọn. Thêm một fallback bảo vệ các URL không khớp hai chain này.
5. **So sánh test context:** Chạy cùng một phép thử bằng `@WebMvcTest` có `@Import(SecurityConfiguration.class)` và `@SpringBootTest`. Liệt kê các bean bảo mật thực sự được nạp ở từng context và giải thích khác biệt nếu có.

## 10. Ghi nhớ

**Bean `SecurityFilterChain` định nghĩa chính sách cho một nhóm request; `FilterChainProxy` là hạ tầng chọn chuỗi và thực thi các filter; bean `springSecurityFilterChain` là điểm vào dạng Servlet `Filter` cho ứng dụng và MockMvc.** Để kiểm thử bảo mật HTTP có ý nghĩa, phải đưa đúng các bean vào **test application context** và gắn filter đầu vào đó với **chính instance MockMvc đang thực hiện request**.

Hãy kiểm chứng bằng các ca **được phép lẫn bị từ chối**, gồm phân quyền, xác thực và CSRF. Một context có bean bảo mật nhưng MockMvc không sử dụng filter, hoặc một request không khớp chuỗi nào, đều có thể khiến test cho kết quả 200 sai với mục tiêu kiểm chứng của bạn.
