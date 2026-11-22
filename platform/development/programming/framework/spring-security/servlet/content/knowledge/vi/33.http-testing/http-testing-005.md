# Kiểm thử HTTP: CSRF, token sai và các thao tác thay đổi dữ liệu trong Spring Security Servlet

## 1. Vấn đề cần kiểm thử

Một API Spring MVC có thể xác thực người dùng đúng và kiểm tra role đầy đủ nhưng vẫn gặp rủi ro **Cross-Site Request Forgery (CSRF)** nếu trình duyệt tự đính kèm cookie phiên hoặc một loại credential khác vào request do trang web độc hại kích hoạt. Với những thao tác tạo, sửa, xóa dữ liệu, một request hợp lệ về mặt HTTP không có nghĩa người dùng **chủ động** gửi thao tác đó.

Khi bật CSRF protection trong Spring Security Servlet, request dùng những HTTP method được xem là **không an toàn** thường phải cung cấp một CSRF token hợp lệ. Trong kiểm thử HTTP, cần phân biệt tối thiểu:

1. Request đọc dữ liệu bằng GET có cần CSRF token không?
2. POST, PUT, PATCH, DELETE không có CSRF token bị chặn thế nào?
3. CSRF token có mặt nhưng **sai** có bị từ chối như trường hợp thiếu token không?
4. Có CSRF token đúng nhưng **chưa đăng nhập** thì có được sửa dữ liệu không?
5. Có CSRF token đúng, đã đăng nhập nhưng **thiếu quyền** thì sao?
6. Nếu bị từ chối, controller/service có thực sự **không tạo side effect**?
7. Nếu API dùng Authorization: Bearer do JavaScript chủ động thêm, chính sách CSRF có khác API dựa trên session/cookie không?

Bài này tập trung **kiểm thử HTTP Servlet bằng MockMvc và spring-security-test** (Spring Boot 3.x, Spring Security 6.x, Java 17+). Ví dụ dựng một REST API nhỏ, có @SpringBootTest, @AutoConfigureMockMvc, SecurityFilterChain thật, HTTP Basic demo và kho dữ liệu trong bộ nhớ để kiểm tra rằng request bị chặn không thay đổi trạng thái.

**Phân biệt ngay từ đầu:** CSRF token không phải session ID, access token OAuth 2.0, JWT, ID token hoặc password. Nó là giá trị riêng dùng để xác nhận request thay đổi trạng thái được tạo trong ngữ cảnh trình duyệt/phiên được bảo vệ đúng theo thiết kế. Token đúng không thay thế authentication hoặc authorization.

## 2. Vì sao CSRF tồn tại dù hệ thống đã có đăng nhập?

Một tình huống điển hình:

~~~text
1. Người dùng đăng nhập tại https://bank.example.org.
2. Trình duyệt giữ session cookie thuộc miền bank.example.org.
3. Người dùng mở một trang từ miền khác do attacker kiểm soát.
4. Trang độc hại khiến trình duyệt gửi POST tới bank.example.org/transfer.
5. Tùy chính sách cookie, trình duyệt có thể tự gửi cookie phiên đi kèm.
6. Nếu server chỉ kiểm tra cookie -> authenticated, request có thể chạy.
7. Nếu server còn yêu cầu CSRF token hợp lệ, attacker thường
   không thể tự tạo được token tương ứng với phiên bảo mật.
~~~

Trong môi trường thực, thuộc tính SameSite của cookie, CORS, cách thiết kế form và các hạn chế trình duyệt làm thay đổi khả năng khai thác. Tuy nhiên **SameSite/CORS không phải lời giải thay thế mặc định cho CSRF protection**. SameSite có thể giúp giảm rủi ro nhưng không phải mọi mô hình đều được bảo vệ chỉ bởi một thuộc tính cookie; CORS chủ yếu điều khiển quyền truy cập cross-origin từ JavaScript, không ngăn mọi hình thức trình duyệt gửi request.

Đối với session-based login, cookie là **credential tự động được trình duyệt gửi**. Đây là nguồn rủi ro CSRF. HTTP Basic cũng cần đánh giá tương tự vì trình duyệt có thể nhớ credentials và tự gắn chúng khi gọi lại origin.

Ngược lại, một API Resource Server hoàn toàn stateless, chỉ chấp nhận access token từ Authorization header do ứng dụng client **chủ động** đưa vào và không dựa cookie tự động gửi, có mô hình CSRF khác. Nhưng không thể kết luận “REST API luôn miễn CSRF” hay “cứ dùng JWT là an toàn CSRF”. JWT nằm trong cookie tự động gửi vẫn có thể tạo rủi ro CSRF.

## 3. HTTP method an toàn và thao tác thay đổi dữ liệu

Spring Security có mặc định CSRF matcher dựa trên HTTP method. Theo các quy tắc thường gặp, **GET, HEAD, TRACE, OPTIONS** được xem là những method không cần CSRF token, còn những method khác cần được bảo vệ. Cụ thể trong API REST:

| Method | Mục đích chuẩn | CSRF theo mặc định | Ví dụ |
| --- | --- | --- | --- |
| GET | Đọc dữ liệu | Thông thường không yêu cầu | GET /api/items/5 |
| HEAD | Đọc headers | Thông thường không yêu cầu | HEAD /api/items/5 |
| OPTIONS | Khảo sát tùy chọn/preflight | Thông thường không yêu cầu | OPTIONS /api/items |
| POST | Tạo hoặc kích hoạt thao tác | Cần token hợp lệ | POST /api/items |
| PUT | Thay thế tài nguyên | Cần token hợp lệ | PUT /api/items/5 |
| PATCH | Chỉnh sửa một phần | Cần token hợp lệ | PATCH /api/items/5 |
| DELETE | Xóa tài nguyên | Cần token hợp lệ | DELETE /api/items/5 |

**Không lấy tên method làm bằng chứng duy nhất rằng endpoint an toàn.** Theo thiết kế HTTP, GET và HEAD không được thực hiện hành vi thay đổi trạng thái mang tính nghiệp vụ. Nếu GET /delete-account thực sự xóa tài khoản, CSRF matcher mặc định có thể không chặn request ấy; lỗi cần sửa là **thiết kế endpoint có side effect trên GET**.

TRACE có thể được phân loại safe trong logic CSRF mặc định nhưng bị HttpFirewall hoặc servlet container chặn vì lý do khác. Không mở TRACE chỉ để thử CSRF và cũng không tuyên bố mọi TRACE đều được Spring Security chấp nhận.

Việc một POST có CSRF token hợp lệ không tự biến nó thành request được phép. Method đó còn phải vượt qua authentication, authorization, input validation và business invariants.

## 4. Vị trí của CsrfFilter trong Spring Security

Đường đi khái quát:

~~~text
Client HTTP request
     |
     v
Servlet container
     |
     v
DelegatingFilterProxy("springSecurityFilterChain")
     |
     v
FilterChainProxy -> SecurityFilterChain
     |
     +--> Filter thiết lập SecurityContext
     |
     +--> CsrfFilter
     |        |
     |        +--> Kiểm tra method có cần CSRF không
     |        |
     |        +--> Lấy expected token từ CsrfTokenRepository
     |        |
     |        +--> Đọc submitted token từ header/parameter
     |        |
     |        +--> So khớp hợp lệ
     |                 |
     |                 +--> thiếu/sai: AccessDenied, thường HTTP 403
     |                 +--> đúng: cho filter chain đi tiếp
     |
     +--> Authentication / Authorization filters khác
     |
     v
DispatcherServlet -> Controller -> Service
~~~

Sơ đồ giải thích chức năng, không liệt kê tất cả filter. Vị trí tương quan của các thành phần authentication và exception handling phụ thuộc phiên bản/cấu hình. **CsrfFilter có thể từ chối request trước khi authorization chạy**, nên với một POST vừa thiếu đăng nhập vừa thiếu CSRF token, response có thể là **403** vì CSRF thay vì 401 như ta đoán từ authentication.

Khái niệm quan trọng:

- **CsrfTokenRepository:** cơ chế quản lý expected token gắn với request/session/nguồn lưu trữ được cấu hình. Với Servlet stack, một triển khai thường dùng là HttpSessionCsrfTokenRepository; CookieCsrfTokenRepository phục vụ mô hình cookie khi được cấu hình đúng.
- **CsrfTokenRequestHandler:** cách ứng dụng đưa CSRF token vào request attribute và resolve submitted token từ HTTP request. Spring Security 6 có xử lý deferred token và cơ chế token masking phù hợp để giảm các rủi ro như BREACH trong một số mô hình.
- **CsrfFilter:** quyết định request cần token hay không và so sánh expected token với giá trị được gửi.
- **AccessDeniedHandler:** thường trả HTTP 403 khi missing/invalid CSRF token; cấu hình tùy chỉnh có thể cho phản hồi khác.
- **SecurityContext / AuthorizationFilter:** quyết định danh tính và quyền sau khi request vượt qua các điều kiện bảo mật liên quan.

Khi request bị từ chối ở CsrfFilter, controller không nên chạy và dữ liệu không bị thay đổi. Đây là lý do test không chỉ assert HTTP 403 mà còn kiểm tra **side effect bằng 0**.

## 5. Phân biệt thiếu token, token sai, token hợp lệ và quyền truy cập

Một ma trận quan trọng cho POST /api/items. Giả sử endpoint yêu cầu ROLE_EDITOR, CSRF protection đang bật và hệ thống dùng HTTP Basic làm authentication demo:

| Authentication | CSRF | Kết quả thường gặp | Có được tạo item? |
| --- | --- | --- | --- |
| Không có | Không có | 403 ở CSRF filter | Không |
| Không có | Hợp lệ | 401 tại authentication/authorization | Không |
| ROLE_EDITOR | Không có | 403 | Không |
| ROLE_EDITOR | Token không hợp lệ | 403 | Không |
| ROLE_VIEWER | Hợp lệ | 403 do thiếu ROLE_EDITOR | Không |
| ROLE_EDITOR | Hợp lệ | 201 Created nếu request/body hợp lệ | Có |
| ROLE_EDITOR | Hợp lệ nhưng body vi phạm validation | 4xx theo validation | Không, nếu xử lý đúng |

Các status trên là kỳ vọng **đối với cấu hình demo** bên dưới. Không xem chúng như quy tắc bất biến của mọi API: entry point, AccessDeniedHandler, servlet container, proxy, custom filter và rule ứng dụng có thể làm status khác. Muốn xác định 403 do CSRF hay authorization, cần xem request có token đúng không, log/exception an toàn và vị trí filter xử lý.

**Token CSRF sai** khác **access token OAuth sai**. Token CSRF sai thường bị CsrfFilter chặn 403 khi request cần bảo vệ. JWT Bearer sai chữ ký/hết hạn thuộc authentication, điển hình 401. Nếu cả hai đều sai, tầng được chạy trước có thể quyết định phản hồi đầu tiên; đừng suy luận nguyên nhân duy nhất từ status.

## 6. spring-security-test và MockMvc: bộ công cụ kiểm thử

Với Spring Security Test, một request postprocessor tên **csrf()** được import từ SecurityMockMvcRequestPostProcessors giúp thêm CSRF token hợp lệ cho request MockMvc. Những biến thể thường dùng:

~~~java
// Đính kèm CSRF token hợp lệ vào request:
.with(csrf())

// Gửi submitted token như HTTP header:
.with(csrf().asHeader())

// Chủ động gửi CSRF token không hợp lệ:
.with(csrf().useInvalidToken())

// Gửi một giá trị không hợp lệ qua header:
.with(csrf().asHeader().useInvalidToken())
~~~

Các dòng trên là fragment dành cho MockHttpServletRequestBuilder; không phải chương trình Java chạy độc lập.

**with(csrf()) không phải hành động đăng nhập**. Nó chỉ thiết lập điều kiện CSRF cho mock request. Nếu endpoint yêu cầu đăng nhập, cần thêm @WithMockUser, httpBasic(...) hoặc một cách authentication khác vào test. Ngược lại, **@WithMockUser không tự thêm CSRF token**; một POST đã được mock authentication vẫn có thể trả 403 vì thiếu token.

Test helper tạo/đính kèm token trong môi trường MockMvc để thử security filter, **không phải bằng chứng rằng frontend production đã thực hiện đúng luồng nhận token**, cookie, session, SameSite, XSRF header hay token rotation. Muốn kiểm tra browser/client thực cần test HTTP integration riêng.

Đối với các API dạng application/json, có thể dùng POST/PUT/PATCH cùng contentType(MediaType.APPLICATION_JSON) và with(csrf()). Bài demo dùng **text/plain** để giữ controller code và nội dung test ngắn, tập trung vào CSRF. CSRF không phụ thuộc việc request body là JSON, form, multipart hay text/plain.

## 7. Tạo project mẫu: phụ thuộc và cấu trúc file

Dự án Java 17+ dùng Spring Boot 3.x, Spring MVC và Spring Security 6.x.

Trong build.gradle (Groovy), dưới cấu hình Boot plugin và dependency management đã có sẵn:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Các file:

~~~text
src/main/java/demo/csrfhttp/
    CsrfHttpApplication.java
    SecurityConfig.java
    ItemStore.java
    ItemController.java

src/test/java/demo/csrfhttp/
    CsrfHttpIntegrationTest.java
~~~

Đây là ví dụ chạy được trong dự án Spring Boot đã có build plugin, repository dependencies và Gradle wrapper tương ứng. Spring Boot quản lý phiên bản Security; không trộn tùy tiện version ngoài BOM.

Ứng dụng mẫu sử dụng **in-memory store**, không có database, để test xác nhận việc tạo/sửa/xóa có xảy ra hay không. Dữ liệu sẽ mất khi restart; nó không phải thiết kế persistence cho production.

## 8. Lớp khởi động Spring Boot

File src/main/java/demo/csrfhttp/CsrfHttpApplication.java:

~~~java
package demo.csrfhttp;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CsrfHttpApplication {

    public static void main(String[] args) {
        SpringApplication.run(CsrfHttpApplication.class, args);
    }
}
~~~

@SpringBootApplication thực hiện component scan trong package demo.csrfhttp, bao gồm SecurityConfig, ItemStore và ItemController. Không cần viết một servlet filter riêng để tự xử lý CSRF.

## 9. SecurityConfig: giữ CSRF protection và phân quyền độc lập

File src/main/java/demo/csrfhttp/SecurityConfig.java:

~~~java
package demo.csrfhttp;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/items/public")
                    .permitAll()
                .requestMatchers(HttpMethod.POST, "/api/items")
                    .hasRole("EDITOR")
                .requestMatchers(HttpMethod.PUT, "/api/items/**")
                    .hasRole("EDITOR")
                .requestMatchers(HttpMethod.PATCH, "/api/items/**")
                    .hasRole("EDITOR")
                .requestMatchers(HttpMethod.DELETE, "/api/items/**")
                    .hasRole("EDITOR")
                .requestMatchers(HttpMethod.GET, "/api/items/**")
                    .authenticated()
                .anyRequest().denyAll()
            )
            .csrf(Customizer.withDefaults())
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories
            .createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("demo-password"))
                .roles("EDITOR")
                .build(),
            User.withUsername("bob")
                .password(encoder.encode("demo-password"))
                .roles("VIEWER")
                .build()
        );
    }
}
~~~

Các quyết định quan trọng:

1. **.csrf(Customizer.withDefaults())** giữ CSRF protection mặc định. Bản thân Spring Security Servlet thường đã bật CSRF mặc định trong một chain sử dụng HttpSecurity; viết rõ trong bài để tránh hiểu sai.
2. GET /api/items/public công khai, nhưng không có nghĩa các thao tác tạo/sửa/xóa cũng được phép.
3. POST/PUT/PATCH/DELETE yêu cầu ROLE_EDITOR. Bob có ROLE_VIEWER nên ngay cả khi có CSRF token hợp lệ vẫn bị chặn bởi authorization.
4. GET /api/items/{id} yêu cầu authentication nhưng mặc định không cần CSRF token vì là thao tác đọc.
5. **HTTP Basic** cung cấp demo credential để test đường authentication ngoài @WithMockUser. Không dùng HTTP Basic không mã hóa trong production; luôn yêu cầu HTTPS.
6. PasswordEncoder dùng delegating encoder, còn user demo nằm trong bộ nhớ. Đây không phải phương pháp quản lý tài khoản production.
7. Không gọi csrf.disable() hay đặt ignoringRequestMatchers rộng chỉ để test POST đi qua; làm như vậy sẽ khiến các negative tests không còn kiểm tra policy mong muốn.

Cấu hình mẫu không cố định SessionCreationPolicy.STATELESS. Mô hình CSRF thường dùng HttpSessionCsrfTokenRepository; nếu tự áp policy stateless trong một ứng dụng session/cookie, cần thiết kế lại CSRF token repository và luồng client thay vì chỉ bật một flag.

## 10. Kho dữ liệu trong bộ nhớ để đo side effect

File src/main/java/demo/csrfhttp/ItemStore.java:

~~~java
package demo.csrfhttp;

import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.stereotype.Component;

@Component
public class ItemStore {

    private final AtomicLong sequence = new AtomicLong();
    private final ConcurrentMap<Long, String> items =
        new ConcurrentHashMap<>();

    public long create(String name) {
        long id = sequence.incrementAndGet();
        items.put(id, name);
        return id;
    }

    public String find(long id) {
        return items.get(id);
    }

    public boolean update(long id, String name) {
        return items.replace(id, name) != null;
    }

    public boolean delete(long id) {
        return items.remove(id) != null;
    }

    public int count() {
        return items.size();
    }

    public void clearForTests() {
        items.clear();
        sequence.set(0);
    }
}
~~~

ItemStore cố tình đơn giản, không transaction, không database. Mỗi request POST/PUT/PATCH/DELETE nếu thực sự chạy tới controller sẽ tác động tới items. Test có thể quan sát dữ liệu trước/sau để phát hiện một request đáng lẽ bị chặn nhưng vẫn thực thi.

clearForTests() là tiện ích dành cho ví dụ kiểm thử, không nên expose thành HTTP endpoint cho client gọi. Nếu dùng database trong dự án thực, hãy kiểm tra repository state và transaction boundaries tương ứng; không được coi HTTP 403 tự động chứng minh một method chưa gây side effect nếu có custom filter làm việc trước đó.

## 11. Controller cho GET, POST, PUT, PATCH, DELETE

File src/main/java/demo/csrfhttp/ItemController.java:

~~~java
package demo.csrfhttp;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/items")
public class ItemController {

    private final ItemStore store;

    public ItemController(ItemStore store) {
        this.store = store;
    }

    @GetMapping("/public")
    public Map<String, String> publicInfo() {
        return Map.of("status", "ok");
    }

    @GetMapping("/{id}")
    public ResponseEntity<Item> get(@PathVariable long id) {
        String name = store.find(id);
        if (name == null) {
            return ResponseEntity.notFound().build();
        }
        return ResponseEntity.ok(new Item(id, name));
    }

    @PostMapping(consumes = MediaType.TEXT_PLAIN_VALUE)
    public ResponseEntity<Item> create(@RequestBody String name) {
        long id = store.create(name);
        return ResponseEntity.status(HttpStatus.CREATED)
            .body(new Item(id, name));
    }

    @PutMapping(
        value = "/{id}",
        consumes = MediaType.TEXT_PLAIN_VALUE
    )
    public ResponseEntity<Item> replace(
            @PathVariable long id, @RequestBody String name) {
        if (!store.update(id, name)) {
            return ResponseEntity.notFound().build();
        }
        return ResponseEntity.ok(new Item(id, name));
    }

    @PatchMapping(
        value = "/{id}",
        consumes = MediaType.TEXT_PLAIN_VALUE
    )
    public ResponseEntity<Item> patch(
            @PathVariable long id, @RequestBody String name) {
        if (!store.update(id, name)) {
            return ResponseEntity.notFound().build();
        }
        return ResponseEntity.ok(new Item(id, name));
    }

    @DeleteMapping("/{id}")
    public ResponseEntity<Void> delete(@PathVariable long id) {
        if (!store.delete(id)) {
            return ResponseEntity.notFound().build();
        }
        return ResponseEntity.noContent().build();
    }

    public record Item(long id, String name) {}
}
~~~

Trong ví dụ này PUT và PATCH đều thay toàn bộ trường name chỉ để minh họa rằng cả hai là **state-changing methods** cần CSRF protection. Trong API thật, PUT và PATCH có contract thay thế toàn bộ/một phần resource khác nhau và cần validation, concurrency control, ownership, idempotency phù hợp.

Không dùng GET để tạo, sửa hoặc xóa item. GET /api/items/public chỉ trả status. POST thành công trả 201 Created; PUT/PATCH thành công trả 200 OK; DELETE thành công trả 204 No Content. Khi item không tồn tại, controller trả 404. Các status nghiệp vụ này chỉ xuất hiện **sau khi security filters cho phép request tới controller**.

## 12. Test đầy đủ: MockMvc + CSRF + authorization + side effects

File src/test/java/demo/csrfhttp/CsrfHttpIntegrationTest.java:

~~~java
package demo.csrfhttp;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
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
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CsrfHttpIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    ItemStore store;

    @BeforeEach
    void resetItems() {
        store.clearForTests();
    }

    @Test
    void getPublicWithoutCsrfIsAllowed() throws Exception {
        mvc.perform(get("/api/items/public"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("ok"));
    }

    @Test
    @WithMockUser(username = "alice", roles = "EDITOR")
    void postMissingCsrfIsForbiddenWithoutSideEffect()
            throws Exception {
        mvc.perform(post("/api/items")
                .contentType(MediaType.TEXT_PLAIN)
                .content("Notebook"))
            .andExpect(status().isForbidden());

        assertEquals(0, store.count());
    }

    @Test
    @WithMockUser(username = "alice", roles = "EDITOR")
    void postInvalidCsrfIsForbiddenWithoutSideEffect()
            throws Exception {
        mvc.perform(post("/api/items")
                .with(csrf().useInvalidToken())
                .contentType(MediaType.TEXT_PLAIN)
                .content("Notebook"))
            .andExpect(status().isForbidden());

        assertEquals(0, store.count());
    }

    @Test
    @WithMockUser(username = "alice", roles = "EDITOR")
    void postValidCsrfCreatesOneItem() throws Exception {
        mvc.perform(post("/api/items")
                .with(csrf())
                .contentType(MediaType.TEXT_PLAIN)
                .content("Notebook"))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.name").value("Notebook"));

        assertEquals(1, store.count());
    }

    @Test
    @WithMockUser(username = "alice", roles = "EDITOR")
    void csrfSentAsHeaderAlsoWorks() throws Exception {
        mvc.perform(post("/api/items")
                .with(csrf().asHeader())
                .contentType(MediaType.TEXT_PLAIN)
                .content("From header"))
            .andExpect(status().isCreated());

        assertEquals(1, store.count());
    }

    @Test
    void validCsrfDoesNotReplaceAuthentication()
            throws Exception {
        mvc.perform(post("/api/items")
                .with(csrf())
                .contentType(MediaType.TEXT_PLAIN)
                .content("Not logged in"))
            .andExpect(status().isUnauthorized());

        assertEquals(0, store.count());
    }

    @Test
    @WithMockUser(username = "bob", roles = "VIEWER")
    void validCsrfDoesNotReplaceAuthorization()
            throws Exception {
        mvc.perform(post("/api/items")
                .with(csrf())
                .contentType(MediaType.TEXT_PLAIN)
                .content("Not editor"))
            .andExpect(status().isForbidden());

        assertEquals(0, store.count());
    }

    @Test
    @WithMockUser(username = "alice", roles = "EDITOR")
    void missingCsrfRejectsPutPatchAndDelete()
            throws Exception {
        long id = store.create("Before");

        mvc.perform(put("/api/items/{id}", id)
                .contentType(MediaType.TEXT_PLAIN)
                .content("After PUT"))
            .andExpect(status().isForbidden());

        mvc.perform(patch("/api/items/{id}", id)
                .contentType(MediaType.TEXT_PLAIN)
                .content("After PATCH"))
            .andExpect(status().isForbidden());

        mvc.perform(delete("/api/items/{id}", id))
            .andExpect(status().isForbidden());

        assertEquals("Before", store.find(id));
        assertEquals(1, store.count());
    }

    @Test
    @WithMockUser(username = "alice", roles = "EDITOR")
    void validCsrfAllowsPutPatchAndDelete()
            throws Exception {
        long id = store.create("Before");

        mvc.perform(put("/api/items/{id}", id)
                .with(csrf())
                .contentType(MediaType.TEXT_PLAIN)
                .content("After PUT"))
            .andExpect(status().isOk());

        assertEquals("After PUT", store.find(id));

        mvc.perform(patch("/api/items/{id}", id)
                .with(csrf())
                .contentType(MediaType.TEXT_PLAIN)
                .content("After PATCH"))
            .andExpect(status().isOk());

        assertEquals("After PATCH", store.find(id));

        mvc.perform(delete("/api/items/{id}", id)
                .with(csrf()))
            .andExpect(status().isNoContent());

        assertNull(store.find(id));
        assertEquals(0, store.count());
    }

    @Test
    void actualHttpBasicAndValidCsrfAllowPost()
            throws Exception {
        mvc.perform(post("/api/items")
                .with(httpBasic("alice", "demo-password"))
                .with(csrf())
                .contentType(MediaType.TEXT_PLAIN)
                .content("Authenticated"))
            .andExpect(status().isCreated());

        assertEquals(1, store.count());
    }
}
~~~

Đây là test class dùng **SpringBootTest, AutoConfigureMockMvc, JUnit 5 và spring-security-test**. Khi có các class và dependency nêu ở trên, nó khởi tạo Web ApplicationContext, dùng SecurityFilterChain thật, cấu hình CSRF thật và controller thật. Không cần mock CsrfFilter hoặc tắt bảo mật.

**Phân tích mười test:**

1. getPublicWithoutCsrfIsAllowed: chứng minh GET public không cần token và status đúng.
2. postMissingCsrfIsForbiddenWithoutSideEffect: người dùng có ROLE_EDITOR nhưng thiếu CSRF token vẫn bị 403; kho vẫn rỗng.
3. postInvalidCsrfIsForbiddenWithoutSideEffect: cùng quyền nhưng token sai; vẫn 403 và không tạo item.
4. postValidCsrfCreatesOneItem: đủ CSRF và role; POST tới controller, trả 201 và item count tăng.
5. csrfSentAsHeaderAlsoWorks: đưa token qua header của Spring Security Test; vẫn được phép.
6. validCsrfDoesNotReplaceAuthentication: CSRF hợp lệ nhưng thiếu user; HTTP Basic entry point từ chối 401.
7. validCsrfDoesNotReplaceAuthorization: Bob có ROLE_VIEWER, không phải ROLE_EDITOR; 403 do authorization.
8. missingCsrfRejectsPutPatchAndDelete: cả ba thao tác sửa/xóa bị chặn, dữ liệu giữ nguyên.
9. validCsrfAllowsPutPatchAndDelete: token và role hợp lệ cho phép thao tác PUT, PATCH, DELETE; có kiểm tra state sau mỗi bước.
10. actualHttpBasicAndValidCsrfAllowPost: dùng httpBasic(...) để thực hiện authentication qua SecurityFilterChain thay vì @WithMockUser; cần đồng thời có CSRF token.

Mỗi test dùng @BeforeEach để xóa bộ nhớ, tránh phụ thuộc thứ tự chạy. Các ví dụ dự kiến chạy tuần tự theo cấu hình JUnit thông thường; nếu dự án bật parallel execution, cần cách cô lập ItemStore per-test hoặc khóa thích hợp để tránh test chia sẻ state.

Không dùng @Transactional hoặc rollback database trong demo vì ItemStore không có persistence; production test repository cần kiểm tra đúng transaction và commit/rollback semantics.

## 13. Tại sao assert 403 là chưa đủ?

Một test chỉ viết:

~~~java
mvc.perform(post("/api/items"))
    .andExpect(status().isForbidden());
~~~

chưa chứng minh đầy đủ chính sách mong muốn vì:

- Request có thể bị chặn do **không đăng nhập**, do **CSRF**, do **không có role** hoặc do một filter khác.
- Nếu controller có side effect trước khi một exception được chuyển thành 403 trong custom flow, dữ liệu vẫn có thể bị thay đổi.
- Nếu endpoint không tồn tại hoặc routing sai, kết quả test có thể không kiểm tra đúng tài nguyên.
- Một status 403 cũng có thể được custom application code tự trả, không liên quan tới CsrfFilter.

Để **cô lập CSRF**, test đặt user đã xác thực **có đủ role** rồi thay đổi duy nhất submitted CSRF token: missing, invalid và valid. Sau đó assert response và state. Nếu muốn cô lập role, hãy giữ CSRF token hợp lệ rồi thay đổi authority từ ROLE_EDITOR sang ROLE_VIEWER. Nếu muốn cô lập authentication, giữ CSRF token hợp lệ nhưng không đưa credential.

Đây là mô hình thử nghiệm theo từng trục:

~~~text
Trục A - Authentication
  anonymous <-> authenticated

Trục B - Authorization
  ROLE_VIEWER <-> ROLE_EDITOR

Trục C - CSRF
  missing <-> invalid <-> valid

Trục D - HTTP method
  GET <-> POST <-> PUT <-> PATCH <-> DELETE

Trục E - Side effects
  unchanged <-> created/updated/deleted
~~~

Một test tốt nêu rõ trục nào đang được thay đổi. Đừng khiến tất cả yếu tố cùng sai rồi suy luận 403 chứng minh từng yếu tố hoạt động.

## 14. Token hợp lệ trong MockMvc không mô phỏng trọn vẹn phiên trình duyệt

with(csrf()) được tạo để test logic Spring Security. Nó **không** bảo đảm frontend thực sự biết cách lấy token, truyền đúng cookie, dùng đúng session hoặc nhận token mới sau sự kiện login/logout.

Trong browser app dùng session:

1. Server cấp hoặc làm CSRF token sẵn có theo cơ chế đã cấu hình.
2. Client nhận token qua HTML form, meta tag, response attribute hoặc API cung cấp token được thiết kế an toàn.
3. Client gửi token trong form parameter hoặc request header được server cho phép.
4. Browser gửi session cookie của đúng người dùng/phiên.
5. Server đối chiếu token từ client với expected token của phiên hoặc repository.
6. Khi login/logout hoặc lifecycle thay đổi, token có thể bị xóa/refresh và client phải cập nhật.

Với CSRF configuration mặc định của Spring Security 6, còn có chi tiết về **deferred CSRF token** và **token masking thông qua CsrfTokenRequestHandler**. Nếu một SPA gửi raw token lấy từ cookie, cấu hình header request handler phải phù hợp. Không tự kết luận rằng chỉ thêm CookieCsrfTokenRepository.withHttpOnlyFalse() luôn đủ cho mọi Spring Security 6 SPA: có thể cần cách giải mã/resolve token header khác so với masked token trong request attribute, và cần làm mới token sau authentication.

Kiểm thử đầy đủ một ứng dụng dùng cookie/session cần thêm các bước HTTP thực: lấy token/cookie từ response trước, giữ cookie jar, gửi CSRF token trong form/header, thử token từ **phiên khác**, thử token hết hiệu lực sau logout và xác nhận server từ chối.

MockMvc helper có thể thuận tiện mà chưa kiểm tra rủi ro **CSRF token bị nhầm giữa hai phiên**. Hãy có integration tests mô phỏng ít nhất hai session khác nhau nếu chính sách ứng dụng phụ thuộc chặt vào session.

## 15. Request multipart, JSON và form không làm CSRF biến mất

CSRF áp dụng theo **HTTP request** và cơ chế token, không đơn giản theo content type.

- HTML form POST thường gửi tham số _csrf dưới dạng field ẩn, cùng session cookie.
- AJAX/JSON có thể gửi CSRF qua header như X-CSRF-TOKEN theo repository/handler đang cấu hình.
- Multipart upload cần xét cách parse body và thứ tự multipart filter/CSRF để tìm token, giới hạn upload trước khi authentication và tình huống request tốn tài nguyên.
- PUT/PATCH/DELETE sử dụng JSON body vẫn cần CSRF nếu ứng dụng dùng credential tự động gửi.

Ví dụ MockMvc cho JSON POST:

~~~java
mvc.perform(post("/api/items")
        .with(csrf())
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"name\":\"Notebook\"}"))
    .andExpect(status().isCreated());
~~~

**Đoạn trên là minh họa cho một controller nhận JSON đúng schema**, không dùng trực tiếp với ItemController ở phần 11 vì controller demo chỉ nhận text/plain. Để chạy JSON example, controller phải khai @RequestBody DTO phù hợp với JSON và không dùng consumes=text/plain.

Khi test negative cases, vẫn giữ request body **hợp lệ** theo controller để không vô tình test một lỗi 400/415 do body thay vì lỗi CSRF. Tương tự, nếu cố tình test invalid validation thì hãy dùng token và authentication hợp lệ để chứng minh lỗi đến từ validation.

## 16. Khi nào không bật CSRF cho mọi request?

Một API chỉ dùng Authorization: Bearer từ header do JavaScript/mobile app **chủ động** gửi và không dựa vào cookie/session credential tự động có thể không chịu cùng CSRF threat model. Với Resource Server stateless, có trường hợp hợp lý để tắt CSRF trong chain API:

~~~java
@Bean
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated()
        )
        .csrf(csrf -> csrf.disable())
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(org.springframework.security.config.Customizer.withDefaults())
        )
        .build();
}
~~~

Đoạn này là **cấu hình minh họa riêng** cho Bearer JWT Resource Server, không phải thay thế class SecurityConfig ở demo. Để chạy cần JWT decoder/issuer cấu hình đúng, resource-server dependencies và việc xác nhận API không chấp nhận một đường cookie/session authentication tự động. Không copy đoạn này vào ứng dụng sử dụng form login rồi kết luận được bảo vệ.

Nếu cùng hệ thống có **web UI session/cookie** và **API Bearer** thì có thể tách SecurityFilterChain với matcher phù hợp: giữ CSRF cho browser chain, đánh giá tắt CSRF chỉ với API chain đã xác minh threat model. Nhưng thứ tự chain, fallback rule, cookie sharing và authentication mechanisms cần được test để không làm hở endpoint.

**Không tắt CSRF vì test bị 403.** 403 có thể đang báo đúng một lỗ hổng trong cách frontend gửi request. Mục tiêu của test là giữ chính sách bảo vệ đúng và phát hiện thay đổi nguy hiểm, không phải làm mọi POST trả 2xx.

## 17. Một ma trận mở rộng cho kiểm thử hồi quy

Sau khi có test cơ bản, nên bổ sung theo nhu cầu nghiệp vụ:

| Ca thử | Setup | Kỳ vọng |
| --- | --- | --- |
| POST thiếu token | ROLE_EDITOR, body hợp lệ | 403; không tạo item |
| POST token giả | ROLE_EDITOR, csrf().useInvalidToken() | 403; không tạo item |
| POST token qua header | ROLE_EDITOR, csrf().asHeader() | 201; tạo một item |
| PUT thiếu token | ROLE_EDITOR, item tồn tại | 403; name cũ giữ nguyên |
| PATCH thiếu token | ROLE_EDITOR, item tồn tại | 403; name cũ giữ nguyên |
| DELETE thiếu token | ROLE_EDITOR, item tồn tại | 403; item còn tồn tại |
| POST token đúng, thiếu login | Anonymous | 401 với HTTP Basic; không tạo item |
| POST token đúng, thiếu role | ROLE_VIEWER | 403; không tạo item |
| POST token đúng, role đúng | ROLE_EDITOR | 201; item được tạo |
| PUT/PATCH/DELETE token đúng | ROLE_EDITOR, item tồn tại | 200/200/204; state tương ứng |
| GET public không token | Anonymous | 200; không thay state |
| GET item private không đăng nhập | Anonymous | 401 |
| GET item private đã xác thực | ROLE_VIEWER hoặc ROLE_EDITOR | 200 nếu item có thật |
| POST credential sai + token đúng | HTTP Basic sai | 401, không thay state |
| POST token từ session khác | Cookie/session test thực | Từ chối nếu policy session-bound |
| Request body vi phạm validation | Đủ authentication, CSRF và role | Lỗi validation; không ghi dữ liệu |
| CORS preflight OPTIONS | Origin, method, header hợp lệ | Kết quả theo CORS policy, không bị coi là POST |
| Request POST không hợp lệ qua proxy | Môi trường deployment | Từ chối tại tầng phù hợp; không side effect |

Không cần áp đặt một status cố định cho mọi trường hợp trong bảng nếu app có AccessDeniedHandler/custom entry point. Trong thực tế, nên lưu cả kết quả response và bằng chứng controller/service có chạy hay không; dùng request ID/correlation ID khi có tracing.

Với kiểm thử HTTP quy mô lớn, phân tầng:

1. **MockMvc:** nhanh, kiểm tra security filter logic, controller và side effects trong Spring TestContext.
2. **Integration với embedded servlet container:** kiểm tra cookie, session, token issuance, form encoding và HTTP client thật.
3. **Browser end-to-end:** kiểm tra token được frontend nạp lại sau login/logout, requests AJAX, SameSite/CORS và CSRF state.
4. **Deployment smoke tests:** kiểm tra reverse proxy, ingress, HTTPS và policy production.

## 18. Những lỗi thường gặp

**Lỗi 1 — @WithMockUser được hiểu là đã đủ cho POST.** Không đúng. Annotation tạo Authentication giả lập nhưng không thêm CSRF token. Thêm with(csrf()) khi muốn test đường thành công; bỏ hoặc làm sai token khi muốn test đường chặn.

**Lỗi 2 — csrf() bị hiểu là đăng nhập.** Không đúng. CSRF token chứng minh request đáp ứng cơ chế chống giả mạo, không cho biết principal là ai hoặc có role nào.

**Lỗi 3 — 403 được xem là luôn thiếu role.** Sai: CsrfFilter có thể trả 403 vì token thiếu/sai. Giữ authentication/role hợp lệ khi test CSRF để cô lập nguyên nhân.

**Lỗi 4 — Request thiếu authentication và thiếu CSRF token nhưng đòi 401.** CsrfFilter có thể từ chối trước authorization, nên 403 là hợp lý. Để test authentication, gửi CSRF token hợp lệ trước.

**Lỗi 5 — Chỉ test POST mà quên PUT, PATCH, DELETE.** Các method này đều thay đổi dữ liệu và cần cùng chính sách CSRF trong mô hình phù hợp.

**Lỗi 6 — GET được dùng để thay đổi dữ liệu.** Default CSRF matcher thường bỏ qua GET. Sửa API semantics và dùng POST/PUT/PATCH/DELETE đúng mục đích.

**Lỗi 7 — Test status mà không test side effects.** Phải xác nhận store/repository không ghi khi request bị từ chối; chỉ một status 403 không đủ để chứng minh nghiệp vụ an toàn.

**Lỗi 8 — Bật csrf.disable() để làm test pass.** Điều đó loại bỏ chính cơ chế mà bài đang kiểm thử. Chỉ tắt khi threat model thực sự phù hợp, ví dụ Bearer-only API không dùng auto-attached credentials.

**Lỗi 9 — Dùng csrf().useInvalidToken() nhưng gán thêm lỗi khác.** Nếu role cũng sai hoặc endpoint không tồn tại, kết quả 403/404 có thể không chứng minh riêng CSRF. Cần kiểm soát từng biến.

**Lỗi 10 — Nghĩ CORS đủ để chống CSRF.** CORS không ngăn mọi cross-origin request; SameSite giúp giảm rủi ro nhưng không thay thế policy CSRF trong mọi kịch bản.

**Lỗi 11 — Nghĩ token trong MockMvc mô phỏng hoàn toàn cookie/SPA.** with(csrf()) là helper test. Hãy test token issuance, cookie jar, request handler và token rotation thực tế riêng.

**Lỗi 12 — Nhầm CSRF token sai với access token Bearer sai.** Một lỗi thuộc CsrfFilter, một lỗi thuộc authentication. Trạng thái HTTP tương ứng phụ thuộc vào chính sách và vị trí lỗi.

**Lỗi 13 — Token từ form hoặc AJAX bị lấy sai tên header.** Kiểm tra CsrfTokenRepository, CsrfTokenRequestHandler, request attribute/parameter/header, đặc biệt với SPA trên Spring Security 6.

**Lỗi 14 — Lưu state kiểm thử giữa các test.** Dùng fixture riêng, dọn state hoặc rollback/transaction strategy rõ ràng để mỗi test độc lập. Khi chạy song song phải cô lập bộ nhớ/database phù hợp.

**Lỗi 15 — Kết luận MockMvc chứng minh production safe.** MockMvc không bao gồm tất cả biến đổi ở browser/proxy/container. Chạy thêm kiểm thử HTTP thật cho cookie, SameSite, session và deployment.

## 19. Checklist trước khi chấp nhận một API có thao tác thay đổi dữ liệu

- [ ] Đã xác định rõ request nào dùng cookie/session/Basic credentials tự động gửi; request nào là Bearer-only.
- [ ] Các GET/HEAD chỉ đọc dữ liệu, không có side effects thay đổi trạng thái.
- [ ] POST/PUT/PATCH/DELETE được bảo vệ theo CSRF policy phù hợp.
- [ ] Có negative tests cho thiếu CSRF token và token không hợp lệ.
- [ ] Có positive tests cho token hợp lệ khi đã xác thực và đủ quyền.
- [ ] Có test token hợp lệ nhưng thiếu authentication và test token hợp lệ nhưng thiếu authority.
- [ ] Không đồng nhất 401 và 403 với một nguyên nhân duy nhất.
- [ ] Assertions kiểm tra dữ liệu **không thay đổi** ở request bị chặn.
- [ ] MockMvc tests có spring-security-test, @AutoConfigureMockMvc và đúng filter chain.
- [ ] Không dùng @WithMockUser để khẳng định password/JWT thật đã được xác minh.
- [ ] SPA có quy trình nhận/gửi CSRF token phù hợp token repository và request handler của Spring Security 6.
- [ ] Cookie, SameSite, CORS, session và HTTPS được kiểm thử trong môi trường gần production.
- [ ] Không tắt CSRF chung cho browser endpoints chỉ để vượt qua lỗi 403.
- [ ] Các rule authentication, role/authority và object-level permission được kiểm thử độc lập với CSRF.
- [ ] Không đưa credential, session ID, Bearer token hoặc raw CSRF token nhạy cảm vào logs công khai.

## 20. Tự kiểm tra và kết luận

**Câu hỏi 1.** Alice có ROLE_EDITOR và POST /api/items không có CSRF token. Kỳ vọng?

Trong cấu hình demo, CsrfFilter chặn với HTTP 403, ItemStore không có item mới. Xác thực đúng không thay cho token chống giả mạo.

**Câu hỏi 2.** POST mang CSRF token hợp lệ nhưng chưa có Basic authentication. Kết quả?

Với Basic entry point của ví dụ, HTTP 401 và không tạo item. CSRF hợp lệ không phải credential đăng nhập.

**Câu hỏi 3.** Bob đã đăng nhập, có ROLE_VIEWER, gửi token hợp lệ. Có được POST tạo item?

Không. Rule hasRole("EDITOR") yêu cầu ROLE_EDITOR, nên authorization từ chối 403. Token đúng không cấp role.

**Câu hỏi 4.** Vì sao phải test PUT, PATCH và DELETE mà không chỉ POST?

Chúng cũng thay đổi trạng thái nên phải chịu CSRF protection trong mô hình session/cookie. Một rule hoặc cấu hình custom thiếu một method có thể tạo khoảng trống bảo mật.

**Câu hỏi 5.** with(csrf()) có chứng minh giao diện web lấy đúng token sau khi đăng nhập và gửi đúng session cookie không?

Không. Nó chuẩn bị mock token cho request MockMvc. Cần test HTTP thật/browser để kiểm tra token issuance, session binding và lifecycle.

**Câu hỏi 6.** Khi một POST bị 403, cần làm gì để xác định nguyên nhân?

Kiểm tra authentication, role, submitted CSRF token, expected token repository/handler, filter chain được chọn và log/exception an toàn. Thay đổi từng trục trong test và kiểm tra side effect.

**Kết luận:** Kiểm thử HTTP về CSRF phải đi xa hơn việc “POST trả 403”. Hãy tách **thiếu token**, **token sai**, **token đúng**, **authentication**, **authorization** và **state mutation** thành các trường hợp độc lập. Dùng MockMvc với csrf(), csrf().useInvalidToken() và @WithMockUser hoặc httpBasic(...), rồi xác nhận controller/service **không làm thay đổi dữ liệu khi bị chặn**. Với browser/cookie, bổ sung test session và token lifecycle ngoài MockMvc. Đó là cách kiểm tra cả tính đúng đắn của filter lẫn tác động bảo vệ của CSRF trên thao tác tạo, sửa và xóa.
