# Khớp đường dẫn kết hợp HTTP method trong Spring Security

Một URL có thể phục vụ nhiều thao tác: `GET /api/orders` đọc danh sách, `POST /api/orders` tạo đơn, `PUT /api/orders/42` cập nhật và `DELETE /api/orders/42` xóa. Nếu chỉ bảo vệ bằng mẫu `/api/orders/**` rồi cấp quyền chung, ứng dụng có thể cho một người chỉ cần **quyền đọc** thực hiện cả thao tác ghi. Spring Security cho phép kết hợp **đường dẫn (path)** với **phương thức HTTP (HTTP method)** để mỗi hành động được kiểm soát riêng.

Bài này thuộc nhóm **Bảo vệ endpoint** của **Spring Security - fundamentals**. Trọng tâm là cách `RequestMatcher` xét **đồng thời path và method**, cách áp dụng **quy tắc khớp đầu tiên**, cấu hình thực tế bằng Java 17+ trên Spring MVC/Servlet, kiểm thử quyền và các điểm dễ nhầm với CSRF, CORS hoặc định tuyến của Controller.

## 1. Khác biệt giữa đường dẫn và hành động HTTP

HTTP method mô tả ý định thao tác trên tài nguyên:

| Method | Cách dùng thường gặp | Ví dụ | Quyền ứng dụng có thể yêu cầu |
| --- | --- | --- | --- |
| `GET` | Đọc tài nguyên | `GET /api/orders` | `ORDER_READ` |
| `POST` | Tạo/thực hiện hành động | `POST /api/orders` | `ORDER_CREATE` |
| `PUT` | Ghi đè/cập nhật theo quy ước API | `PUT /api/orders/42` | `ORDER_UPDATE` |
| `PATCH` | Cập nhật một phần | `PATCH /api/orders/42` | Quyền cập nhật, nếu API hỗ trợ |
| `DELETE` | Xóa tài nguyên | `DELETE /api/orders/42` | `ORDER_DELETE` |
| `HEAD` | Lấy metadata phản hồi không có body | `HEAD /api/orders` | Cần chính sách rõ nếu được hỗ trợ |
| `OPTIONS` | Hỏi phương thức/khả năng giao tiếp; có thể là CORS preflight | `OPTIONS /api/orders` | Cần xét mục đích preflight hoặc endpoint |

Đây là những **quy ước HTTP**, không phải Spring Security tự quyết định nghiệp vụ. Một ứng dụng có thể có `POST /api/orders/42/cancel` để hủy đơn dù nó không dùng DELETE. Vì thế hãy phân quyền theo **hợp đồng endpoint thực tế**, không tự coi mọi GET là không có dữ liệu nhạy cảm hoặc mọi POST đều có cùng mức quyền.

Phân biệt ba lớp trách nhiệm:

1. **Định tuyến** trong Spring MVC/WebFlux: request sẽ vào Controller/handler nào? Ví dụ `@GetMapping("/api/orders")`.
2. **Xác thực (authentication)**: request đại diện cho ai, đã có `Authentication` hợp lệ chưa?
3. **Phân quyền (authorization)**: cặp `(HTTP method, path)` này có được phép đi tiếp với danh tính/quyền hiện tại không?

Spring Security thường xét quyền trước khi request chạy vào Controller. Vì thế một request **không có handler tương ứng** vẫn có thể bị Spring Security từ chối trước khi Spring MVC trả 404/405.

## 2. Matcher kết hợp method + path là phép kiểm tra hai điều kiện

Trong Spring Security Servlet, `authorizeHttpRequests` khai báo nhiều cặp **điều kiện khớp → yêu cầu phân quyền**. Ví dụ:

~~~java
.requestMatchers(HttpMethod.GET, "/api/orders/**").hasAuthority("ORDER_READ")
.requestMatchers(HttpMethod.POST, "/api/orders").hasAuthority("ORDER_CREATE")
~~~

Ở mỗi dòng:

- `HttpMethod.GET` hoặc `HttpMethod.POST` giới hạn đúng phương thức được gửi trong request.
- Chuỗi mẫu `"/api/orders/**"` hoặc `"/api/orders"` giới hạn đường dẫn.
- Chỉ khi **cả method và path khớp**, quy tắc ở dòng đó mới được chọn để đánh giá quyền.
- `hasAuthority("ORDER_READ")` kiểm tra đúng quyền `ORDER_READ` trong `Authentication.getAuthorities()`; nó không tự thêm tiền tố `ROLE_` như `hasRole(...)`.

Đối chiếu:

| Request | Khớp quy tắc GET /api/orders/**? | Khớp quy tắc POST /api/orders? |
| --- | :---: | :---: |
| `GET /api/orders/42` | Có | Không |
| `POST /api/orders` | Không | Có |
| `POST /api/orders/42` | Không | Không |
| `DELETE /api/orders/42` | Không | Không |
| `GET /api/users/42` | Không | Không |

Với trường hợp `GET /api/orders`, việc mẫu `/api/orders/**` có bao gồm chính đường dẫn gốc hay không cần xét kiểu matcher và phiên bản đang dùng; **đừng âm thầm phụ thuộc vào dấu `/**` ở cuối** khi đường dẫn gốc là quan trọng. Trong ví dụ hoàn chỉnh ở phần sau, bài viết khai báo rõ `/api/orders` và `/api/orders/{id}`.

Câu lệnh sau khác về phạm vi:

~~~java
.requestMatchers(HttpMethod.GET).hasAuthority("READ_ANY_GET")
~~~

Nó chọn **mọi request GET trong phạm vi SecurityFilterChain**, kể cả `GET /admin` nếu chuỗi này xử lý đường dẫn đó. Đây là quy tắc method **không giới hạn path**; không thay thế được matcher kết hợp hai điều kiện khi cần cấp quyền từng nhóm API.

Ngược lại:

~~~java
.requestMatchers("/api/orders/**").authenticated()
~~~

quy tắc này chỉ ràng buộc **path** và áp dụng cho mọi HTTP method phù hợp. Nó không phân biệt GET với DELETE.

## 3. Spring Security dùng quy tắc khớp đầu tiên, không cộng quyền giữa các dòng

Trong `authorizeHttpRequests(...)`, `AuthorizationFilter` đánh giá các cặp `RequestMatcher → AuthorizationManager` **theo thứ tự khai báo**. **Quy tắc khớp đầu tiên** quyết định việc cấp hay từ chối quyền.

Xét cấu hình dễ sai:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").authenticated()
    .requestMatchers(HttpMethod.DELETE, "/api/orders/{id}")
        .hasAuthority("ORDER_DELETE")
    .anyRequest().denyAll()
)
~~~

`DELETE /api/orders/42` khớp ngay `/api/**`. Nếu người dùng đã xác thực, quy tắc này cho qua và **không tiếp tục** xuống dòng `ORDER_DELETE`. Quy tắc có vẻ chặt phía dưới đã bị vô hiệu bởi quy tắc quá rộng phía trên.

Hãy đảo lại:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.DELETE, "/api/orders/{id}")
        .hasAuthority("ORDER_DELETE")
    .requestMatchers("/api/**").authenticated()
    .anyRequest().denyAll()
)
~~~

Cấu hình trên đã bảo vệ DELETE ở URL cụ thể. Tuy nhiên, các DELETE khác dưới `/api/**` vẫn chỉ yêu cầu đăng nhập; vì vậy với API cần kiểm soát chặt, nên **liệt kê các method/path được hỗ trợ và từ chối các trường hợp còn lại**. `anyRequest().denyAll()` là lựa chọn mặc định an toàn trong ví dụ giảng dạy.

Một cách đọc chính xác của quy tắc:

~~~text
Duyệt từ trên xuống:
  1. Matcher hiện tại có khớp cả method và path?
     - Không: xét matcher kế tiếp.
     - Có: đánh giá điều kiện quyền của dòng này.
  2. Điều kiện quyền đạt? → cho đi tiếp.
     Không đạt? → từ chối.
  3. Không thử tiếp dòng dưới chỉ vì người dùng thiếu quyền ở dòng đã khớp.
~~~

Vì vậy, **không khớp matcher** khác với **khớp matcher nhưng không đủ quyền**. Trường hợp thứ nhất có thể rơi xuống quy tắc sau; trường hợp thứ hai dừng tại quy tắc đã chọn.

## 4. Bảng quyết định mẫu cho API đơn hàng

Giả sử ứng dụng có bốn quyền chính: `ORDER_READ`, `ORDER_CREATE`, `ORDER_UPDATE` và `ORDER_DELETE`.

| Request | Matcher dự kiến | Quyền yêu cầu | Kết quả khi chỉ có `ORDER_READ` |
| --- | --- | --- | --- |
| `GET /api/orders` | GET + đường dẫn danh sách | `ORDER_READ` | Cho qua |
| `GET /api/orders/42` | GET + đường dẫn từng đơn | `ORDER_READ` | Cho qua |
| `POST /api/orders` | POST + đường dẫn danh sách | `ORDER_CREATE` | Từ chối |
| `PUT /api/orders/42` | PUT + đường dẫn từng đơn | `ORDER_UPDATE` | Từ chối |
| `DELETE /api/orders/42` | DELETE + đường dẫn từng đơn | `ORDER_DELETE` | Từ chối |
| `PATCH /api/orders/42` | Không khai báo PATCH | `denyAll` | Từ chối |
| `GET /api/admin` | Không khai báo đường dẫn này | `denyAll` | Từ chối |

“Cho qua” ở đây chỉ có nghĩa **đạt điều kiện phân quyền HTTP**. Điều đó không đảm bảo Controller tồn tại, tài nguyên có thật, dữ liệu thuộc người dùng hay quá trình xử lý thành công. Ví dụ người dùng có `ORDER_READ` vẫn có thể bị từ chối khi cố đọc đơn hàng của khách khác nếu ứng dụng bổ sung kiểm tra quyền theo từng tài nguyên.

## 5. Cấu hình Java 17+ có thể đưa vào ứng dụng Spring MVC

Ví dụ sau dành cho **Spring Boot 3.3.x / Spring Security 6.3.x**, Java 17 trở lên, ứng dụng Servlet dùng `spring-boot-starter-web` và `spring-boot-starter-security`. Mục đích là tạo một ví dụ nhỏ nhưng có thể kiểm thử toàn bộ method/path, thay vì chỉ trình bày một đoạn DSL không có Controller.

### 5.1. Phụ thuộc Gradle

Trong dự án Spring Boot đã có Spring Boot plugin và quản lý phiên bản dependency:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Đoạn Gradle này chỉ là phần phụ thuộc và cấu hình test cần ghép vào `build.gradle` của dự án Spring Boot hiện có. Đừng tạo thêm bộ quản lý dependency/phiên bản thủ công khi dự án đã sử dụng cơ chế quản lý của Spring Boot.

### 5.2. Tệp EndpointPolicyApplication.java

Trong `src/main/java/example/methodpath/EndpointPolicyApplication.java`:

~~~java
package example.methodpath;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class EndpointPolicyApplication {
    public static void main(String[] args) {
        SpringApplication.run(EndpointPolicyApplication.class, args);
    }
}
~~~

Đây là điểm khởi động ứng dụng, để Spring Boot tự phát hiện `SecurityConfig` và `OrdersController` trong cùng package.

### 5.3. Tệp SecurityConfig.java

Trong `src/main/java/example/methodpath/SecurityConfig.java`:

~~~java
package example.methodpath;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET,
                        "/api/orders", "/api/orders/{id}")
                    .hasAuthority("ORDER_READ")

                .requestMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("ORDER_CREATE")

                .requestMatchers(HttpMethod.PUT, "/api/orders/{id}")
                    .hasAuthority("ORDER_UPDATE")

                .requestMatchers(HttpMethod.DELETE, "/api/orders/{id}")
                    .hasAuthority("ORDER_DELETE")

                // Mọi method khác trên tài nguyên đơn hàng: từ chối.
                .requestMatchers("/api/orders", "/api/orders/**")
                    .denyAll()

                // Mọi path chưa được khai báo: từ chối.
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Cấu hình giữ **CSRF mặc định của Spring Security**; điều này có ý nghĩa khi kiểm thử POST/PUT/DELETE. Nó dùng HTTP Basic làm cơ chế tạo phản hồi 401 xác định cho request chưa đăng nhập; dự án thực tế có thể dùng form login, OAuth2 Resource Server hoặc cơ chế khác.

Chú ý:

- `HttpMethod.GET` áp dụng **cho cả hai đường dẫn** trong cùng lời gọi; vì vậy cả danh sách và chi tiết đều đòi `ORDER_READ`.
- Mỗi phương thức ghi sử dụng quyền tương ứng; cùng một path không dẫn đến cùng một quyền mặc định.
- `"/api/orders/{id}"` là mẫu một đoạn biến đường dẫn. Thực tế tên kiểu mẫu/engine và cách phân tích chi tiết phụ thuộc Spring MVC + phiên bản matcher. Bài này dùng mẫu đơn giản, không dựa vào khác biệt nâng cao của `**`.
- Sau các quy tắc cụ thể là quy tắc **path-only `denyAll`** cho các method chưa được chấp nhận trên API đơn hàng, rồi đến `anyRequest().denyAll()`.
- Trong ứng dụng thật, chính sách có thể cần quyền theo đơn cụ thể, sở hữu bản ghi và trạng thái đơn, bên cạnh quyền khái quát `ORDER_UPDATE`.

### 5.4. Tệp OrdersController.java

Trong `src/main/java/example/methodpath/OrdersController.java`:

~~~java
package example.methodpath;

import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrdersController {

    @GetMapping
    public List<String> list() {
        return List.of("ORD-101", "ORD-102");
    }

    @GetMapping("/{id}")
    public String find(@PathVariable String id) {
        return "order-" + id;
    }

    @PostMapping
    public ResponseEntity<String> create() {
        return ResponseEntity.status(HttpStatus.CREATED).body("created");
    }

    @PutMapping("/{id}")
    public ResponseEntity<Void> update(@PathVariable String id) {
        return ResponseEntity.noContent().build();
    }

    @DeleteMapping("/{id}")
    public ResponseEntity<Void> delete(@PathVariable String id) {
        return ResponseEntity.noContent().build();
    }
}
~~~

Controller trả dữ liệu cố định để phục vụ kiểm thử chính sách; nó không lưu, sửa hay xóa dữ liệu thật. Đặt cả ba tệp vào cùng package `example.methodpath`. Với dự án có package riêng, đổi package **nhất quán cho cả ba tệp**.

Chính sách ở `SecurityConfig` và các `@GetMapping/@PostMapping/...` giải quyết hai câu hỏi độc lập:

- Spring Security xác định người dùng **có được đi qua URL + method này** không.
- Spring MVC xác định **phương thức Java nào xử lý request** nếu nó đã qua các bộ lọc.

Nếu hai bên khai báo khác nhau, ví dụ Security cho GET nhưng Controller chỉ hỗ trợ POST, lỗi định tuyến vẫn có thể xảy ra sau khi đã qua phân quyền. Ngược lại, một Controller có `@DeleteMapping` không có nghĩa Spring Security tự động biết phải yêu cầu `ORDER_DELETE`.

## 6. Kiểm thử tích hợp method + path bằng MockMvc

Một kiểm thử hữu ích phải có cả **đường được phép** và **đường bị chặn**, đặc biệt là **cùng path nhưng khác method**. Dùng `spring-security-test` để tạo danh tính có quyền cụ thể và kiểm tra cả CSRF.

Tệp `src/test/java/example/methodpath/EndpointMethodAuthorizationTest.java`:

~~~java
package example.methodpath;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class EndpointMethodAuthorizationTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void anonymousCannotReadProtectedOrders() throws Exception {
        mvc.perform(get("/api/orders"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void readerCanGetListAndDetail() throws Exception {
        var reader = user("reader")
                .authorities(new SimpleGrantedAuthority("ORDER_READ"));

        mvc.perform(get("/api/orders").with(reader))
                .andExpect(status().isOk())
                .andExpect(content().json("[\"ORD-101\", \"ORD-102\"]"));

        mvc.perform(get("/api/orders/42")
                .with(user("reader")
                    .authorities(new SimpleGrantedAuthority("ORDER_READ"))))
                .andExpect(status().isOk())
                .andExpect(content().string("order-42"));
    }

    @Test
    void readerCannotPostToSamePathEvenWithCsrf() throws Exception {
        mvc.perform(post("/api/orders")
                .with(user("reader")
                    .authorities(new SimpleGrantedAuthority("ORDER_READ")))
                .with(csrf()))
                .andExpect(status().isForbidden());
    }

    @Test
    void creatorCanPostWithCsrf() throws Exception {
        mvc.perform(post("/api/orders")
                .with(user("creator")
                    .authorities(new SimpleGrantedAuthority("ORDER_CREATE")))
                .with(csrf()))
                .andExpect(status().isCreated())
                .andExpect(content().string("created"));
    }

    @Test
    void creatorCannotPostWithoutCsrf() throws Exception {
        mvc.perform(post("/api/orders")
                .with(user("creator")
                    .authorities(new SimpleGrantedAuthority("ORDER_CREATE"))))
                .andExpect(status().isForbidden());
    }

    @Test
    void writerCanPutButCannotDelete() throws Exception {
        mvc.perform(put("/api/orders/42")
                .with(user("writer")
                    .authorities(new SimpleGrantedAuthority("ORDER_UPDATE")))
                .with(csrf()))
                .andExpect(status().isNoContent());

        mvc.perform(delete("/api/orders/42")
                .with(user("writer")
                    .authorities(new SimpleGrantedAuthority("ORDER_UPDATE")))
                .with(csrf()))
                .andExpect(status().isForbidden());
    }

    @Test
    void deleterCanDeleteWithCsrf() throws Exception {
        mvc.perform(delete("/api/orders/42")
                .with(user("deleter")
                    .authorities(new SimpleGrantedAuthority("ORDER_DELETE")))
                .with(csrf()))
                .andExpect(status().isNoContent());
    }

    @Test
    void unlistedMethodFallsToDenyAll() throws Exception {
        mvc.perform(patch("/api/orders/42")
                .with(user("writer")
                    .authorities(new SimpleGrantedAuthority("ORDER_UPDATE")))
                .with(csrf()))
                .andExpect(status().isForbidden());
    }

    @Test
    void unrelatedPathDoesNotInheritOrderReadAuthority() throws Exception {
        mvc.perform(get("/api/admin")
                .with(user("reader")
                    .authorities(new SimpleGrantedAuthority("ORDER_READ"))))
                .andExpect(status().isForbidden());
    }
}
~~~

Chạy từ thư mục dự án Spring Boot có Gradle wrapper:

~~~bash
./gradlew test --tests '*EndpointMethodAuthorizationTest'
~~~

Trên Windows PowerShell/CMD:

~~~powershell
.\gradlew.bat test --tests "*EndpointMethodAuthorizationTest"
~~~

**Kết quả kỳ vọng:** 9 phép thử thành công trên phiên bản/phụ thuộc nêu trên. Đây là kỳ vọng từ mã và các hợp đồng Spring Security được minh họa, **không phải kết quả đã thực thi trong môi trường của người đọc**. Các phép thử dùng `MockMvc` tích hợp chuỗi bộ lọc Spring Security do `@AutoConfigureMockMvc` cấu hình. Chúng không cần tài khoản người dùng thật vì `user(...)` đưa danh tính kiểm thử vào yêu cầu.

Trường hợp `readerCannotPostToSamePathEvenWithCsrf` là kiểm chứng trực tiếp nhất của chủ đề: đường dẫn `/api/orders` không thay đổi, nhưng từ `GET` sang `POST` khiến matcher và quyền cần thiết thay đổi.

## 7. CSRF có thể chặn request dù matcher quyền đúng

Spring Security thường bật bảo vệ **CSRF** trong ứng dụng Servlet. Các phương thức có thể thay đổi trạng thái như `POST`, `PUT`, `PATCH`, `DELETE` cần token CSRF hợp lệ theo quy tắc mặc định nếu request thuộc diện phải kiểm tra.

Cùng người dùng có `ORDER_CREATE`:

~~~text
POST /api/orders  + ORDER_CREATE + CSRF hợp lệ  → có thể qua bộ lọc và vào Controller
POST /api/orders  + ORDER_CREATE + thiếu CSRF   → có thể bị 403 trước bước phân quyền URL
POST /api/orders  + ORDER_READ   + CSRF hợp lệ  → không đạt ORDER_CREATE → bị từ chối
~~~

Do đó, khi thấy `403` ở POST, **đừng vội kết luận matcher method/path sai**; hãy kiểm tra cả quyền và yêu cầu CSRF. Trong `MockMvc` dùng `.with(csrf())` cho các request ghi để phép thử quyền không bị chặn sớm vì thiếu CSRF.

CSRF và authorization phục vụ hai mục tiêu khác nhau:

- **Phân quyền method/path**: ai được thực hiện thao tác này?
- **CSRF**: request có bằng chứng phù hợp chống việc trình duyệt bị lợi dụng gửi yêu cầu có sẵn thông tin xác thực hay không?

Không vô hiệu hóa `csrf` trên toàn ứng dụng chỉ để làm phép thử POST thành công. Với API không dùng cookie/phiên trình duyệt và có mô hình xác thực khác, có thể có quyết định riêng về phạm vi CSRF, nhưng phải dựa trên kiến trúc thực tế chứ không phải vì thấy mã 403.

## 8. OPTIONS và CORS preflight không phải POST thật

Một trình duyệt gọi API từ origin khác có thể gửi **preflight** trước khi gửi yêu cầu thực:

~~~http
OPTIONS /api/orders HTTP/1.1
Origin: https://app.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization,content-type
~~~

Tại tầng HTTP, request này có method là **`OPTIONS`**. Dòng `Access-Control-Request-Method: POST` chỉ mô tả method mà trình duyệt dự kiến gửi sau đó; Spring Security **không coi preflight này là một request POST** chỉ vì có header trên. Vì thế:

~~~java
.requestMatchers(HttpMethod.POST, "/api/orders").hasAuthority("ORDER_CREATE")
~~~

không khớp với request `OPTIONS`.

Nếu API thực sự phục vụ frontend khác origin, cách đúng là **cấu hình CORS theo origin, method và header hợp lệ**, đồng thời cho cơ chế xử lý preflight chạy trước các bước yêu cầu danh tính. Spring Security có tích hợp CORS cho trường hợp đó.

Ví dụ phần bổ sung vào `SecurityConfig`, chỉ khi ứng dụng cần CORS:

~~~java
// Import bổ sung:
// import java.util.List;
// import org.springframework.web.cors.CorsConfiguration;
// import org.springframework.web.cors.CorsConfigurationSource;
// import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Bean
CorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration config = new CorsConfiguration();
    config.setAllowedOrigins(List.of("https://app.example.com"));
    config.setAllowedMethods(List.of("GET", "POST", "PUT", "DELETE"));
    config.setAllowedHeaders(List.of("Authorization", "Content-Type", "X-CSRF-TOKEN"));
    config.setAllowCredentials(true);

    UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/api/**", config);
    return source;
}
~~~

Đồng thời thêm vào chuỗi cấu hình `HttpSecurity`:

~~~java
.cors(Customizer.withDefaults())
~~~

Đây là **mảnh cấu hình tích hợp**, không phải chương trình Java độc lập; cần đặt bean và các import vào class cấu hình Spring ở phần 5. Chỉ cho phép origin thực sự tin cậy, điều chỉnh header và credential theo cơ chế xác thực, và kiểm thử CORS trên trình duyệt. Cookie cross-origin còn chịu các quy tắc `SameSite`/`Secure`, và CORS không thay CSRF.

**Không dùng `requestMatchers(HttpMethod.OPTIONS, "/**").permitAll()` như phương án chữa lỗi CORS chung.** Nó không kiểm tra origin/method/header được phép và không thay thế được xử lý preflight; hơn nữa nó khiến mọi OPTIONS thuộc phạm vi matcher được cho qua, có thể không đúng yêu cầu API. Với cùng-origin request hoặc endpoint OPTIONS thật, hãy xác định chính sách riêng.

## 9. HEAD, PATCH và các method chưa khai báo

Bộ lọc phân quyền xét **method mà HTTP request thực sự mang**. Nếu cấu hình chỉ có `GET`, Spring MVC có thể hỗ trợ xử lý `HEAD` từ `@GetMapping`, nhưng một matcher bảo mật **`HttpMethod.GET` không tự động trở thành matcher `HttpMethod.HEAD`**. Nếu muốn cho phép HEAD, khai báo riêng:

~~~java
.requestMatchers(HttpMethod.HEAD, "/api/orders", "/api/orders/{id}")
    .hasAuthority("ORDER_READ")
~~~

Đặt quy tắc này trước các `denyAll` áp dụng cho đơn hàng. Ngược lại, nếu không muốn hỗ trợ HEAD, giữ `denyAll` và kiểm thử rõ.

Với `PATCH` cũng tương tự: không có quy tắc PATCH trong cấu hình ở phần 5 thì request `PATCH /api/orders/42` bị từ chối. Khi thêm `@PatchMapping("/{id}")`, cần thêm quy tắc phân quyền tương ứng, ví dụ yêu cầu `ORDER_UPDATE`, và kiểm tra CSRF.

Với `TRACE` hoặc các method khác, việc có cho phép hay không còn phụ thuộc web server/container. Chính sách `denyAll` là biện pháp phòng thủ ở tầng Spring Security, không đảm bảo request đã đi tới được ứng dụng. **Không hiểu “method chưa khai báo bị từ chối” thành “luôn trả 403”** nếu container từ chối trước.

## 10. Path pattern, query string và servlet context

`requestMatchers(HttpMethod.GET, "/api/orders/{id}")` dùng mẫu path, không phải chuỗi URL đầy đủ. Các lưu ý thường gặp:

- **Query string:** `GET /api/orders?status=OPEN` vẫn có path `/api/orders`. Matcher path thông thường không tự kiểm tra giá trị `status` hoặc `userId`. Nếu quyền phụ thuộc query, cần logic phân quyền riêng.
- **Path variable:** `/api/orders/{id}` mô tả một đoạn đường dẫn thay đổi. Khớp URL **không đồng nghĩa** người dùng được phép đọc mọi `id`; quyền theo đối tượng cần kiểm tra thêm.
- **Context path:** nếu ứng dụng được triển khai dưới `/shop`, khi viết matcher Spring Security Servlet, thông thường mẫu được xét tương đối với context path; đừng tự thêm `/shop` vào mọi matcher mà không xem cấu hình thực tế.
- **Servlet path:** nếu có nhiều Servlet hoặc `DispatcherServlet` nằm dưới đường dẫn phụ, có thể cần `MvcRequestMatcher.Builder.servletPath(...)` (với dòng Spring Security 6.x phù hợp) hoặc matcher phù hợp để chỉ rõ phạm vi. Không suy ra trực tiếp từ đường dẫn nhìn thấy trên trình duyệt.
- **Dấu gạch chéo cuối và mã hóa:** `/api/orders/42` và `/api/orders/42/`, dấu `;`, đường dẫn đã mã hóa, chữ hoa/thường có thể được xử lý khác giữa kiểu matcher và cấu hình web server. Hãy kiểm thử các biến thể thực tế của endpoint nhạy cảm.
- **Bản chất matcher:** Spring Security có thể chọn matcher tương thích Spring MVC hoặc matcher khác tùy phiên bản và bean hiện diện. Không lấy quy tắc của `AntPathRequestMatcher` rồi mặc định mọi phiên bản/kiểu matcher đều có cùng cách xử lý các trường hợp biên.

Khi cần dùng điều kiện ngoài path/method, có thể cung cấp một `RequestMatcher` tùy chỉnh. Nhưng hãy làm rõ nó chỉ quyết định **request có nằm trong phạm vi quy tắc không**; phần điều kiện danh tính/quyền vẫn thuộc `AuthorizationManager`.

Ví dụ minh họa cách ghép thêm header khi có yêu cầu thực tế:

~~~java
RequestMatcher selectedRequests = request ->
        "GET".equals(request.getMethod())
        && "/api/reports/export".equals(request.getServletPath())
        && "true".equals(request.getHeader("X-Export-Requested"));

// Tích hợp vào DSL:
// .requestMatchers(selectedRequests).hasAuthority("REPORT_EXPORT")
~~~

Đây là **đoạn mã tùy biến**, không phải phương án mặc định cho bảo vệ đơn hàng. Việc dựa vào header do client kiểm soát không được coi là bằng chứng quyền truy cập; quyền `REPORT_EXPORT` vẫn phải được kiểm tra. Ví dụ chỉ cho thấy matcher có thể kết hợp nhiều điều kiện về request.

## 11. Phân biệt requestMatchers với securityMatcher

Hai tên dễ giống nhau nhưng ở hai tầng:

- `http.securityMatcher("/api/**")`: xác định **một `SecurityFilterChain` có áp dụng cho request này hay không**.
- `authorizeHttpRequests(auth -> auth.requestMatchers(...))`: chọn **quy tắc phân quyền bên trong chain đã áp dụng**.

Ví dụ:

~~~java
http
    .securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
        .requestMatchers(HttpMethod.GET, "/api/orders")
            .hasAuthority("ORDER_READ")
        .anyRequest().denyAll()
    );
~~~

Phần cấu hình này chỉ thuộc các request mà chain `/api/**` nhận xử lý. `anyRequest().denyAll()` trong chain **không tự bảo vệ các đường ngoài `/api/**`**. Nếu dùng nhiều `SecurityFilterChain`, Spring Security chọn chain phù hợp theo thứ tự; cần có phương án bảo vệ các request nằm ngoài chain chuyên biệt để tránh một phần ứng dụng đi qua mà không có chuỗi bảo mật mong muốn.

Với một ứng dụng nhỏ, ví dụ ở phần 5 dùng **một chain tổng quát** và `anyRequest().denyAll()` giúp dễ kiểm tra phạm vi. Khi ứng dụng tách nhiều chain (API, Actuator, web UI), phải kiểm tra cả thứ tự chain, matcher cấp chain và quy tắc bên trong.

## 12. Kết quả 401, 403, 404, 405 đến từ các tầng khác nhau

Khi gỡ lỗi, hãy phân tích trình tự:

~~~text
HTTP method + path
      ↓
Chọn SecurityFilterChain
      ↓
Bộ lọc xác thực và cơ chế bảo vệ (CSRF, CORS, ...)
      ↓
AuthorizationFilter → matcher đầu tiên thỏa method + path
      ↓
Đánh giá quyền → cho qua / từ chối
      ↓
Nếu cho qua: DispatcherServlet chọn Controller
      ↓
Controller thực thi hoặc sinh kết quả như 404/405/2xx/5xx
~~~

Trong ví dụ dùng HTTP Basic:

| Hiện tượng | Nguyên nhân có thể gặp | Điều cần kiểm tra |
| --- | --- | --- |
| `401 Unauthorized` | Chưa có danh tính hợp lệ, cần xác thực | Header Authorization, `AuthenticationEntryPoint` |
| `403 Forbidden` | Thiếu authority, bị `denyAll` hoặc CSRF thất bại | Matcher đã chọn, authority hiện có, CSRF token |
| `404 Not Found` | Đã qua bảo mật nhưng không có tài nguyên/handler hợp lệ | Path, Controller, mapping cụ thể |
| `405 Method Not Allowed` | Qua được bảo mật nhưng handler không hỗ trợ HTTP method | `@GetMapping` / `@PostMapping`, routing |
| Chuyển hướng tới login | Ứng dụng dùng form login thay vì HTTP Basic | Cơ chế `AuthenticationEntryPoint` |
| Phản hồi CORS bị chặn | Origin/method/header preflight không hợp lệ hoặc cấu hình CORS sai | Request OPTIONS, cấu hình CORS |

Bảng này trình bày **tình huống thường gặp**, không cam kết mapping cố định một tín hiệu bảo mật với một mã HTTP. Một `denyAll` ở tầng Security có thể từ chối request `PATCH` ngay cả khi Controller không hề có `@PatchMapping`, nên người dùng có thể nhận 403 thay vì 405.

Một dấu hiệu hữu ích khi debug là log **matcher nào khớp đầu tiên** và principal có những `GrantedAuthority` nào. Tăng logging có chọn lọc trong môi trường phát triển; tránh ghi token, cookie hoặc thông tin đăng nhập nhạy cảm vào log.

## 13. Cấu hình WebFlux tương ứng nhưng khác API

Nếu ứng dụng dùng Spring WebFlux, không sao chép `HttpSecurity` và `authorizeHttpRequests` từ Servlet. WebFlux dùng `ServerHttpSecurity.authorizeExchange(...)`, với matcher theo method/path trong `pathMatchers`. Ví dụ **đoạn cấu hình minh họa**:

~~~java
return http
    .authorizeExchange(exchanges -> exchanges
        .pathMatchers(HttpMethod.GET, "/api/orders", "/api/orders/{id}")
            .hasAuthority("ORDER_READ")
        .pathMatchers(HttpMethod.POST, "/api/orders")
            .hasAuthority("ORDER_CREATE")
        .pathMatchers(HttpMethod.DELETE, "/api/orders/{id}")
            .hasAuthority("ORDER_DELETE")
        .anyExchange().denyAll()
    )
    .httpBasic(Customizer.withDefaults())
    .build();
~~~

Đoạn trên phải nằm trong một `@Bean SecurityWebFilterChain`, với `ServerHttpSecurity http` và các import tương ứng của WebFlux; nó **không phải chương trình Java độc lập**. Với phiên bản/reactive cụ thể, phải kiểm tra cách dùng `pathMatchers(HttpMethod, ...)` và cách bảo vệ CSRF/CORS của WebFlux. Ý tưởng vẫn là **method + path cùng khớp, rồi mới xét quyền**.

WebFlux dùng ngữ cảnh bảo mật của Reactor, không giả định mọi request có dữ liệu người dùng trong `SecurityContextHolder` kiểu `ThreadLocal`. Khi cần quyền theo từng tài nguyên, hãy sử dụng cơ chế phân quyền tương thích reactive và Publisher thay vì chặn luồng.

## 14. Những lỗi thiết kế nên tránh

1. **Dùng path-only cho mọi hành động:** `requestMatchers("/api/orders/**").authenticated()` không phân biệt đọc/tạo/sửa/xóa.
2. **Cho matcher rộng lên trước:** một quy tắc `/api/**` khớp trước khiến các quy tắc method cụ thể phía sau không bao giờ được áp dụng.
3. **Không định nghĩa fallback:** method mới như PATCH hoặc HEAD có thể đi vào một quy tắc quá rộng nếu thiếu `denyAll` rõ ràng.
4. **Chỉ phân quyền theo HTTP method toàn hệ thống:** `requestMatchers(HttpMethod.GET)` có thể vô tình cấp quyền đọc mọi tài nguyên, kể cả URL nhạy cảm.
5. **Tưởng Controller mapping tự quyết định quyền:** `@DeleteMapping` không thay `hasAuthority("ORDER_DELETE")`; kiểm tra định tuyến và phân quyền độc lập.
6. **Gán mọi 403 cho authorization:** request ghi thiếu CSRF có thể bị chặn trước khi kiểm tra role/authority.
7. **Xử lý CORS preflight như POST thật:** `OPTIONS` không phải `POST` dù có header `Access-Control-Request-Method: POST`.
8. **Quên HEAD và các biến thể path:** hành vi Spring MVC với HEAD không tự động mở quy tắc GET của Spring Security cho HEAD.
9. **Nhầm `requestMatchers` với `securityMatcher`:** fallback trong chain chuyên biệt không bao trùm các request nằm ngoài chain.
10. **Bỏ qua quyền theo đối tượng:** `ORDER_READ` cho phép gọi API đọc, nhưng chưa đủ chứng minh người dùng được đọc mọi đơn hàng.
11. **Dựa vào tiền tố URL mà bỏ qua method:** `GET /api/orders` và `POST /api/orders` có thể cần quyền hoàn toàn khác nhau.
12. **Không kiểm thử âm tính:** mỗi quyền cần có ít nhất một request phải được phép và một request phải bị từ chối; đặc biệt kiểm tra cùng path, khác method.
13. **Đánh đồng “method không khớp” với “đã từ chối”:** matcher không khớp sẽ được xét tiếp; matcher đã khớp và thiếu quyền thì kết thúc ở quy tắc đó.

## 15. Bài thực hành có đáp án

Giả sử cấu hình theo thứ tự:

~~~java
.requestMatchers(HttpMethod.GET, "/api/documents/**")
    .hasAuthority("DOC_READ")
.requestMatchers(HttpMethod.POST, "/api/documents")
    .hasAuthority("DOC_CREATE")
.requestMatchers(HttpMethod.DELETE, "/api/documents/{id}")
    .hasAuthority("DOC_DELETE")
.requestMatchers("/api/documents", "/api/documents/**")
    .denyAll()
.anyRequest().denyAll()
~~~

**Câu hỏi 1.** Một người chỉ có `DOC_READ` gửi `GET /api/documents/8`. Chuyện gì xảy ra?

Đáp án: matcher GET + `/api/documents/**` phù hợp, người dùng có `DOC_READ` nên **qua bước phân quyền**. Việc Controller có trả tài liệu số 8 hay không là câu chuyện riêng.

**Câu hỏi 2.** Cùng người dùng gửi `DELETE /api/documents/8`. Quy tắc GET có áp dụng không?

Đáp án: không; method khác. Quy tắc DELETE khớp nhưng đòi `DOC_DELETE`, nên bị từ chối. Nếu đây là request trình duyệt, CSRF cũng có thể ngăn request từ trước.

**Câu hỏi 3.** Người có `DOC_CREATE` gửi `POST /api/documents/8`. Đã có quyền tạo thì có được không?

Đáp án: không. Quy tắc POST chỉ dành cho đường `/api/documents`, không khớp `/api/documents/8`; request rơi xuống `denyAll`.

**Câu hỏi 4.** Vì sao đặt `requestMatchers("/api/**").authenticated()` lên đầu có thể gây lỗi phân quyền?

Đáp án: quy tắc chung có thể là matcher khớp đầu tiên cho các request GET/POST/DELETE, khiến các yêu cầu về quyền `DOC_READ` / `DOC_CREATE` / `DOC_DELETE` ở phía sau không được xét.

**Câu hỏi 5.** Có cần thêm `requestMatchers(HttpMethod.OPTIONS, "/**").permitAll()` khi trình duyệt bị lỗi CORS không?

Đáp án: không nên coi đó là cách sửa mặc định. Phải cấu hình CORS hợp lệ để xử lý preflight trước các kiểm tra xác thực, với đúng origin, method và header cần cho phép.

**Câu hỏi 6.** Trong MockMvc, `POST /api/documents` với quyền `DOC_CREATE` vẫn nhận 403. Kiểm tra gì trước?

Đáp án: ngoài quyền và matcher, kiểm tra đã cung cấp CSRF token hợp lệ (`.with(csrf())`) chưa, vì ví dụ không tắt CSRF.

**Câu hỏi 7.** Muốn giới hạn `GET /api/documents/{id}` chỉ cho người sở hữu tài liệu, matcher method/path đã đủ chưa?

Đáp án: chưa. Matcher xác định endpoint; còn quyền trên bản ghi `id` phải kiểm tra bằng chính sách nghiệp vụ, có thể ở service/method security hoặc `AuthorizationManager` tùy kiến trúc.

## 16. Checklist trước khi đưa vào sản phẩm

- Đã liệt kê mọi **method + path** thật sự hỗ trợ, bao gồm các hành động POST đặc biệt, PATCH, HEAD và endpoint quản trị chưa?
- Đã đặt quy tắc cụ thể trước quy tắc rộng và có `anyRequest().denyAll()` cho phần còn lại chưa?
- Các quyền dùng `hasAuthority` có đúng chuỗi được cấp cho người dùng không? Có vô tình đổi `hasAuthority("ORDER_READ")` thành `hasRole("ORDER_READ")` không?
- Cấu hình security matcher có cùng phạm vi với servlet/context/đường dẫn thực tế không?
- Đã kiểm thử cùng path với nhiều method, cả người có quyền lẫn không có quyền chưa?
- Đã kiểm thử CSRF cho thao tác ghi và CORS preflight nếu có frontend cross-origin chưa?
- Đã xác minh quyền theo tài nguyên cụ thể, không chỉ quyền gọi endpoint chưa?
- Đã kiểm thử các đường dẫn tương tự, path không tồn tại, method chưa khai báo và nhiều `SecurityFilterChain` nếu có chưa?

**Nguyên tắc cần nhớ:** trong Spring Security, quy tắc bảo vệ endpoint là một cặp **`(RequestMatcher, AuthorizationManager)`**. Một matcher kết hợp method và path chỉ chọn **loại request**; điều kiện quyền chỉ được áp dụng khi matcher đó là **điều kiện đầu tiên khớp**. Chính sách đầy đủ cần nêu rõ phương thức được chấp nhận, quyền tương ứng và cách từ chối các request còn lại.

## Tài liệu đối chiếu

- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): thứ tự matcher, path, method, `securityMatcher` và `requestMatchers`.
- [Spring Security — CORS trong Servlet](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html): thứ tự xử lý preflight và cách tích hợp Spring Security.
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): bảo vệ request thay đổi trạng thái và phạm vi CSRF.
- [Spring Security — MockMvc testing](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html): tích hợp kiểm thử bảo mật.
- [Spring Security — CSRF testing](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html): cung cấp CSRF token trong MockMvc.
- [Spring Security — Reactive request authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html): cấu hình tương ứng trong WebFlux.
