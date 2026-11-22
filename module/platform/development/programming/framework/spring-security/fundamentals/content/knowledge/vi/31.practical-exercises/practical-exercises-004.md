# Bảo vệ API bằng HTTP Basic và giải thích chính sách CSRF đã chọn

> **Bài thực hành tổng hợp — Spring Security fundamentals.** Xây dựng REST API Spring Boot yêu cầu HTTP Basic, phân biệt người chưa xác thực với người đã xác thực nhưng thiếu quyền, rồi giải thích **vì sao lựa chọn CSRF trong bài phù hợp với một loại client cụ thể**. Bài sử dụng Spring Boot Servlet, Spring Security 6.x, Java 17+, các HTTP client như `curl` và JUnit/MockMvc.

## 1. Bài toán, yêu cầu và phạm vi bảo mật

Ta xây dựng một dịch vụ **Notes API** dành riêng cho **script và dịch vụ backend**, không có trang đăng nhập bằng trình duyệt, không dùng session-cookie làm cơ chế xác thực và không cung cấp API ghi dữ liệu cho người dùng đăng nhập trực tiếp trong trình duyệt.

API có hai thao tác:

| Phương thức và URL | Hành vi | Chính sách truy cập |
| --- | --- | --- |
| `GET /api/notes` | Xem danh sách ghi chú | `ROLE_READER` hoặc `ROLE_EDITOR` |
| `POST /api/notes` | Tạo một ghi chú JSON | Chỉ `ROLE_EDITOR` |
| Mọi đường dẫn/phương thức khác | Không thuộc API công bố | Từ chối theo nguyên tắc deny-by-default |

Hai tài khoản thử nghiệm: `reader` có quyền đọc và `editor` có quyền đọc/ghi. Mật khẩu được **băm bằng BCrypt** trong `UserDetailsService` in-memory khi ứng dụng khởi động. Giá trị password trình bày trong bài chỉ dành cho môi trường cục bộ để chạy thử; hệ thống thật phải dùng kho người dùng/secret riêng, không hard-code.

**Kết quả mong đợi:**

- Không gửi thông tin đăng nhập hoặc gửi sai → `401 Unauthorized` (HTTP Basic thường kèm `WWW-Authenticate`).
- Đăng nhập đúng nhưng thiếu quyền thao tác → `403 Forbidden`.
- `reader` xem danh sách thành công, không thể tạo ghi chú.
- `editor` đọc và tạo ghi chú thành công.
- Request POST từ script đã xác thực **không cần CSRF token** vì bài thiết kế dịch vụ **chỉ phục vụ non-browser client**. Đây là quyết định theo threat model, không phải quy tắc “HTTP Basic thì luôn tắt CSRF”.

## 2. HTTP Basic hoạt động ra sao?

HTTP Basic là một cơ chế gửi thông tin xác thực trong HTTP. Client đính kèm header:

```http
Authorization: Basic <base64(username:password)>
```

Chuỗi `Base64` chỉ mã hóa để truyền, **không mã hóa bảo mật**. Ai đọc được header không được bảo vệ bằng TLS có thể khôi phục username/password. Vì vậy **phải dùng HTTPS trong môi trường thật**. HTTP trên `localhost` ở ví dụ dưới đây chỉ để chạy thử.

Luồng tổng quát:

```text
Client (curl/service)
  |
  | Authorization: Basic ...
  v
Spring SecurityFilterChain
  |
  +-- BasicAuthenticationFilter
  |       -> AuthenticationManager / AuthenticationProvider
  |       -> UserDetailsService
  |       -> PasswordEncoder.matches(...)
  |       -> tạo Authentication hợp lệ khi xác thực thành công
  |
  +-- AuthorizationFilter
  |       -> đối chiếu ROLE_READER / ROLE_EDITOR theo request
  v
NotesController hoặc 401 / 403
```

Trên request cần bảo vệ mà chưa xác thực, `BasicAuthenticationEntryPoint` có thể yêu cầu client cung cấp credentials bằng response `401` cùng header `WWW-Authenticate: Basic ...`. Với request hợp lệ, Spring Security đặt `Authentication` trong `SecurityContext` **cho quá trình xử lý request** để lớp authorization quyết định truy cập.

HTTP Basic không tự cung cấp một cơ chế phân quyền: **xác thực** bằng username/password và **phân quyền** bằng roles/authorities là hai bước. Trong Spring Security, `roles("READER")` tạo authority `ROLE_READER`; `hasRole("READER")` kiểm tra authority tương ứng. Nếu dùng `hasAuthority("ROLE_READER")` thì cần viết đầy đủ tên.

**Giới hạn của HTTP Basic:** credentials thường được gửi trong mỗi request; không có hành vi “logout server-side” tương đương một phiên có thể hủy. Basic có thể thích hợp cho bài thực hành hoặc kết nối nội bộ có kiểm soát, nhưng với hệ thống rộng, hãy cân nhắc token ngắn hạn, OAuth2/mTLS hoặc cơ chế phù hợp hơn.

## 3. Chọn chính sách CSRF từ threat model

**CSRF (Cross-Site Request Forgery)** xảy ra khi kẻ tấn công làm cho một trình duyệt đã có trạng thái xác thực gửi request không mong muốn đến một website/API khác. Nguy cơ đặc biệt liên quan đến **credentials mà trình duyệt tự động gắn vào request**, ví dụ session cookie hoặc **HTTP Basic credentials đã được browser nhớ/cache**.

CSRF khác với authentication: request có thể được server nhận diện là “đúng tài khoản” nhưng **không phải hành động người dùng thực sự muốn thực hiện**. CSRF token là một giá trị cần đưa vào request thay đổi trạng thái, ở vị trí trình duyệt không tự động gửi theo cách kẻ tấn công có thể lợi dụng.

### Quyết định trong bài

Ta chọn:

- **Client chỉ là script/CLI/service**, tự thiết lập header `Authorization`; không có phiên đăng nhập bằng trình duyệt, không yêu cầu browser gửi request và không dựa vào cookie tự động.
- Dùng `SessionCreationPolicy.STATELESS`: Spring Security không tạo/dùng `HttpSession` để lưu `SecurityContext` giữa các request.
- **Tắt kiểm tra CSRF cho dịch vụ API riêng này** bằng `csrf(csrf -> csrf.disable())` để `curl`/backend có thể POST khi đã xác thực và có quyền, không cần cơ chế cấp CSRF token.
- Vẫn giữ **authentication, authorization, HTTPS, mật khẩu an toàn, kiểm tra input và logging phù hợp**. Tắt CSRF không tương đương tắt các bảo vệ khác.

**Điều kiện bắt buộc:** Bài thực hành này chỉ phù hợp khi dịch vụ thực sự **không được dùng như browser-facing API với ambient credentials**. HTTP Basic có thể bị trình duyệt tự động gửi lại sau khi người dùng đã đăng nhập. Bởi vậy, **stateless không làm Basic trong browser miễn nhiễm với CSRF**.

| Client/cơ chế credentials | Có thể bị browser tự gắn credentials? | Hướng xử lý CSRF |
| --- | --- | --- |
| CLI/service gọi API bằng Basic do chính chương trình chủ động gửi | Không có browser trong luồng | Có thể tắt CSRF nếu API được giới hạn đúng như thiết kế |
| Web browser đã nhớ HTTP Basic credentials | **Có thể có** | **Giữ CSRF protection** cho request thay đổi trạng thái; xem xét đổi cách xác thực |
| Browser đăng nhập bằng session cookie | **Có** | Giữ CSRF protection (mặc định của Spring Security) |
| SPA dùng bearer token do JS chủ động đặt và không dùng cookie/ambient auth | Thông thường không tự gắn token như cookie | Đánh giá theo kiến trúc thực tế; vẫn bảo vệ XSS, token và CORS |

**Không dùng những lập luận sai:** “API trả JSON nên không cần CSRF”, “đã bật CORS nên không có CSRF”, “không có session nên không có CSRF”, hoặc “HTTP Basic luôn không có CSRF”. CORS chủ yếu kiểm soát truy cập cross-origin của mã trình duyệt và không phải cơ chế xác nhận ý định của user cho request thay đổi trạng thái.

### Khi bài toán thay đổi

Nếu người dùng bắt đầu gọi API qua trình duyệt, hoặc backend thêm session/cookie làm credentials, phải **đánh giá lại cấu hình**. Có thể bật lại `csrf(Customizer.withDefaults())` và thiết kế cách cấp/gửi CSRF token ở request POST/PUT/PATCH/DELETE, hoặc chuyển sang mô hình đăng nhập phù hợp. Nếu một ứng dụng vừa có UI trình duyệt vừa có service API, thường cần **SecurityFilterChain được phân vùng rõ ràng**, thay vì đặt một lệnh tắt CSRF áp dụng toàn ứng dụng.

## 4. Tổ chức ví dụ và dependency

Ví dụ là **một Spring Boot Servlet application** hoàn chỉnh về các lớp Java cốt lõi. Có thể đặt ba lớp trong một dự án Spring Boot Java 17+ đang dùng Spring Security 6.x:

```text
src/main/java/com/example/basicapi/
  BasicApiApplication.java
  ApiSecurityConfig.java
  NotesController.java

src/test/java/com/example/basicapi/
  BasicApiSecurityTest.java
```

Trong dự án Gradle Groovy đã có Spring Boot plugin và dependency management, bổ sung các dependency:

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

Dùng phiên bản Spring Boot/Java toolchain mà dự án chọn; khi tạo dự án mới có thể khởi tạo qua Spring Initializr rồi thêm các lớp dưới đây. Nếu dự án đã có các dependency hoặc cấu hình task test thì không khai báo trùng.

### `BasicApiApplication.java`

```java
package com.example.basicapi;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BasicApiApplication {

    public static void main(String[] args) {
        SpringApplication.run(BasicApiApplication.class, args);
    }
}
```

Đây là entry point. Các lớp khác cùng package `com.example.basicapi` nên được component scan của Spring Boot tìm thấy.

## 5. Cấu hình SecurityFilterChain, HTTP Basic và CSRF

### `ApiSecurityConfig.java`

```java
package com.example.basicapi;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            // Chỉ chấp nhận non-browser clients; xem threat model mục 3.
            .csrf(csrf -> csrf.disable())
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .requestCache(cache -> cache.disable())
            .formLogin(form -> form.disable())
            .logout(logout -> logout.disable())
            .httpBasic(Customizer.withDefaults())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/error").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/notes")
                    .hasAnyRole("READER", "EDITOR")
                .requestMatchers(HttpMethod.POST, "/api/notes")
                    .hasRole("EDITOR")
                .anyRequest().denyAll()
            )
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        // Mật khẩu demo chỉ dùng để học tại localhost.
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader-demo-pass"))
            .roles("READER")
            .build();

        UserDetails editor = User.withUsername("editor")
            .password(encoder.encode("editor-demo-pass"))
            .roles("READER", "EDITOR")
            .build();

        return new InMemoryUserDetailsManager(reader, editor);
    }
}
```

**Giải thích từng quyết định:**

1. **`httpBasic(Customizer.withDefaults())`:** bật `BasicAuthenticationFilter` để đọc `Authorization: Basic ...`. Spring Security thực hiện so khớp credentials với user được cấu hình.
2. **`PasswordEncoder` bằng BCrypt:** không so sánh mật khẩu plaintext đã lưu. Mật khẩu thử nghiệm viết trong source chỉ để việc thực hành có thể lặp lại. Trong production, lấy dữ liệu user từ kho xác thực thực sự và giữ secret ngoài Git.
3. **`GET` và `POST` có rules riêng:** người có `ROLE_READER` hoặc `ROLE_EDITOR` đọc được; chỉ `ROLE_EDITOR` được tạo mới. `anyRequest().denyAll()` chặn phương thức/URL ngoài phạm vi thay vì vô tình cho phép.
4. **`STATELESS`:** không giữ `SecurityContext` trong `HttpSession`; mỗi request có trách nhiệm mang credentials. Cấu hình này **không đồng nghĩa tự động bảo vệ CSRF**.
5. **`csrf(...disable())`:** chỉ phù hợp vì **toàn bộ ứng dụng ví dụ** là API cho non-browser clients. Không chép nguyên lệnh này vào ứng dụng dùng browser/session mà chưa phân tích lại.
6. **Tắt form login, logout, request cache:** tránh redirect/form flow không cần thiết cho CLI API. Logout phía server không giải quyết browser cache HTTP Basic.
7. **`/error` được cho phép:** để Spring Boot có thể trả lỗi API; điều này không công khai dữ liệu ứng dụng. Với dự án production cần đảm bảo thông tin lỗi không lộ stack trace/secret.

> **Lưu ý phạm vi:** `SecurityFilterChain` này khớp toàn ứng dụng ví dụ. Nếu ứng dụng lớn có cả UI/session và API, phải giới hạn matcher của chain API và tạo một chain riêng bảo vệ UI. Không tắt CSRF toàn hệ thống chỉ vì có một API non-browser.

## 6. Tạo REST controller có dữ liệu thay đổi trạng thái

### `NotesController.java`

```java
package com.example.basicapi;

import java.util.Comparator;
import java.util.List;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/notes")
public class NotesController {

    private final AtomicLong nextId = new AtomicLong();
    private final ConcurrentMap<Long, Note> notes = new ConcurrentHashMap<>();

    @GetMapping
    public List<Note> list() {
        return notes.values().stream()
            .sorted(Comparator.comparingLong(Note::id))
            .toList();
    }

    @PostMapping
    public ResponseEntity<Note> create(@RequestBody CreateNoteRequest body) {
        if (body.text() == null || body.text().isBlank()) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "text must not be blank"
            );
        }

        Note created = new Note(nextId.incrementAndGet(), body.text().trim());
        notes.put(created.id(), created);
        return ResponseEntity.status(HttpStatus.CREATED).body(created);
    }

    public record CreateNoteRequest(String text) {}
    public record Note(long id, String text) {}
}
```

Controller có **`GET` chỉ đọc** và **`POST` tạo dữ liệu**. Hai endpoint khác nhau về tác động nên cần chứng minh chính sách CSRF được chọn có ý thức. Dữ liệu chỉ nằm trong RAM và mất sau khi ứng dụng khởi động lại; đây là chủ đích của ví dụ học tập, không phải hệ lưu trữ production.

`@RequestBody` buộc client gửi JSON đúng định dạng; JSON không tự chống CSRF. Controller kiểm tra `text` để tránh chấp nhận giá trị trống; ứng dụng thật cần validation toàn diện, giới hạn độ dài, kiểm soát chủ sở hữu ghi chú và xử lý lỗi ổn định.

## 7. Chạy và kiểm thử bằng HTTP client

Khởi động ứng dụng từ thư mục dự án có Gradle wrapper:

```bash
./gradlew bootRun
```

Trên Windows PowerShell, dùng `.\gradlew.bat bootRun`. Khi ứng dụng đã chạy tại `http://localhost:8080`, mở terminal khác và thử các lệnh sau. Trên Windows PowerShell dùng `curl.exe` thay `curl` nếu `curl` là alias của PowerShell.

### 7.1. Chưa đăng nhập: 401

```bash
curl -i http://localhost:8080/api/notes
```

Kỳ vọng status **`HTTP/1.1 401`** và một header thử thách HTTP Basic, ví dụ `WWW-Authenticate: Basic realm="Realm"`. Chính xác giá trị realm/header phụ thuộc cấu hình, nhưng status phải là 401 vì request không có credentials.

### 7.2. Reader truy cập GET: 200

```bash
curl -i -u reader:reader-demo-pass http://localhost:8080/api/notes
```

Kỳ vọng **`200 OK`**. Với ứng dụng mới khởi động và chưa thêm dữ liệu, JSON body là:

```json
[]
```

`curl -u` tạo header Basic từ username/password. Trong ví dụ localhost, credentials có sẵn để dễ học; ở môi trường thật không ghi password trên command line nếu lịch sử shell hoặc danh sách process có thể bị quan sát. Có thể dùng `curl -u reader` để được hỏi password, hoặc lấy secret từ kho an toàn.

### 7.3. Reader gọi POST: 403

```bash
curl -i -u reader:reader-demo-pass \
  -H 'Content-Type: application/json' \
  -d '{"text":"First note"}' \
  http://localhost:8080/api/notes
```

Kỳ vọng **`403 Forbidden`**. Credentials đúng nhưng `reader` không có `ROLE_EDITOR`. Controller không được tạo thêm ghi chú. Đây là bằng chứng phân biệt **authentication thành công** với **authorization bị từ chối**.

### 7.4. Editor gọi POST: 201 mà không gửi CSRF token

```bash
curl -i -u editor:editor-demo-pass \
  -H 'Content-Type: application/json' \
  -d '{"text":"First note"}' \
  http://localhost:8080/api/notes
```

Kỳ vọng **`201 Created`**. Nếu đây là ghi chú đầu tiên sau khi ứng dụng khởi động:

```json
{"id":1,"text":"First note"}
```

Không có header `X-CSRF-TOKEN` hoặc tham số `_csrf` trong lệnh. Request **được cho phép vì người gọi đã xác thực, có role EDITOR và cấu hình CSRF đã được tắt có chủ đích cho non-browser API**. Việc POST thành công không chứng minh tắt CSRF là an toàn với browser.

Gọi lại GET bằng `reader`:

```bash
curl -i -u reader:reader-demo-pass http://localhost:8080/api/notes
```

Kỳ vọng **`200 OK`**, body có ghi chú vừa tạo. Nếu có nhiều request tạo trước đó, ID và số lượng ghi chú sẽ khác.

### 7.5. Sai mật khẩu: 401

```bash
curl -i -u reader:wrong-password http://localhost:8080/api/notes
```

Kỳ vọng **`401 Unauthorized`**, không phải 403. Client chưa được xác thực thành công nên chưa đến bước kiểm tra role như một người dùng hợp lệ.

**Lưu ý khi chạy trên PowerShell:** các lệnh Bash nhiều dòng dùng dấu `\` để nối dòng. Với PowerShell, chạy cùng lệnh trên **một dòng** hoặc dùng cú pháp nối dòng của PowerShell; đừng giữ dấu `\` cuối dòng như trong Bash.

## 8. Kiểm thử tự động bằng JUnit và MockMvc

Ngoài việc dùng `curl`, kiểm thử security ở lớp HTTP giúp phát hiện thay đổi policy ngoài ý muốn. Dependency `spring-security-test` bổ sung helper `httpBasic(...)`; các test sau đi qua Spring Security filter chain thực sự.

### `BasicApiSecurityTest.java`

```java
package com.example.basicapi;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers
    .jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers
    .status;

@SpringBootTest
@AutoConfigureMockMvc
class BasicApiSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void missingCredentialsReturns401() throws Exception {
        mvc.perform(get("/api/notes"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void readerCanRead() throws Exception {
        mvc.perform(get("/api/notes")
                .with(httpBasic("reader", "reader-demo-pass")))
            .andExpect(status().isOk());
    }

    @Test
    void incorrectPasswordReturns401() throws Exception {
        mvc.perform(get("/api/notes")
                .with(httpBasic("reader", "wrong-password")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void readerCannotCreate() throws Exception {
        mvc.perform(post("/api/notes")
                .with(httpBasic("reader", "reader-demo-pass"))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"text\":\"Denied\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void editorCanCreateWithoutCsrfToken() throws Exception {
        mvc.perform(post("/api/notes")
                .with(httpBasic("editor", "editor-demo-pass"))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"text\":\"Allowed\"}"))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.text").value("Allowed"));
    }
}
```

Chạy từ thư mục chứa Gradle wrapper:

```bash
./gradlew test
```

Các test không phụ thuộc thứ tự chạy: không test nào giả định `id` cụ thể hoặc danh sách rỗng sau khi test khác đã tạo ghi chú. Khi chạy thành công, Gradle kết thúc với trạng thái **BUILD SUCCESSFUL** (thời gian và số task có thể khác). Không có một chuỗi stdout cố định cần học thuộc.

**Ý nghĩa bài test cuối:** editor POST thành công **mà không gắn CSRF token**, chứng minh policy đang có hiệu lực. Đó cũng là lời nhắc quan trọng: nếu sau này API cho phép browser sử dụng HTTP Basic, test này cần được xem xét lại theo threat model mới, không thể suy ra cấu hình cũ luôn an toàn.

## 9. Nếu client là trình duyệt: quyết định CSRF phải thay đổi

Giả sử người dùng mở trang của ứng dụng qua browser và browser đã lưu HTTP Basic credentials. Một trang web độc hại có thể tìm cách làm browser gửi request đến endpoint của ứng dụng. Vì browser **có thể tự gửi Basic credentials đã nhớ**, request có thể được server xác thực như chính người dùng thật.

Do đó, với browser-facing application:

1. **Không sao chép** `csrf(csrf -> csrf.disable())` của bài này.
2. Giữ Spring Security CSRF protection (mặc định), ví dụ `csrf(Customizer.withDefaults())`, và thiết kế cách frontend lấy/gửi token khi thực hiện thao tác thay đổi trạng thái.
3. Khi CSRF bật, một `POST` phù hợp về credentials/role nhưng **không có token hợp lệ** thông thường bị từ chối với **403** bởi CSRF filter; kết quả có thể phụ thuộc thứ tự filter và cách xử lý request.
4. Với web app thông thường, cân nhắc `formLogin`/OIDC cùng session-cookie được bảo vệ, CSRF token và cài đặt cookie phù hợp. Nếu cần API từ script lẫn browser, tạo các security chain rõ phạm vi và kiểm thử từng chain.
5. CORS, `SameSite`, JSON content type và việc đánh dấu ứng dụng “stateless” chỉ là các yếu tố bổ sung, không thay thế CSRF protection khi có browser tự gửi credentials.

Ví dụ thay đổi cấu hình **mang tính định hướng cho ứng dụng browser**, không cắm song song vào cấu hình API đã nêu:

```java
// Chỉ là phần minh họa cho cấu hình của ứng dụng có browser:
// Thay quyết định tắt CSRF bằng:
.csrf(Customizer.withDefaults())
// Và thiết kế frontend nhận/gửi token hợp lệ cho POST, PUT, PATCH, DELETE.
```

Token phải được đưa vào request theo cách mà browser không tự động bổ sung khi trang khác cố tạo request, ví dụ header `X-CSRF-TOKEN` từ UI hợp lệ. Việc bảo vệ phiên, login/logout, XSS và cookie vẫn cần được thiết kế toàn diện.

## 10. Checklist triển khai ngoài môi trường học

| Vấn đề | Phần ví dụ đã làm | Khi dùng thật cần thêm |
| --- | --- | --- |
| Password | BCrypt với user in-memory demo | Database/IdP/secret manager, chính sách mật khẩu và vòng đời tài khoản |
| Transport | `http://localhost` khi học | HTTPS toàn đường đi; cấu hình proxy/TLS đúng |
| Authorization | Roles tại endpoint | Quyền dữ liệu theo owner/tenant, kiểm tra ở service/domain |
| CSRF | Tắt với điều kiện chỉ non-browser | Xác minh client thực tế; bật CSRF khi browser dùng ambient credentials |
| Session | Stateless SecurityContext | Không phát sinh cookie/session ngầm từ thành phần khác |
| Abuse protection | Chưa có rate limit | Rate limiting, giám sát brute force, audit và khóa tài khoản phù hợp |
| Credentials | Demo xuất hiện trong source/lệnh | Không hard-code, không ghi header Authorization ra log |
| API contract | GET/POST và JSON đơn giản | Validation, body size, error contract, idempotency khi cần |
| Operability | RAM store, không persistent | Persistence, logging an toàn, metrics và kiểm thử tích hợp |

Đừng dùng HTTP Basic trên kết nối HTTP thông thường ngoài localhost; Base64 không mang lại tính bí mật. Tránh lưu user/password của hệ thống thật trong repository hoặc output của CI. Nếu có reverse proxy/API gateway, kiểm tra nó không ghi lại `Authorization` header vào log.

## 11. Tự đánh giá kết quả và xử lý lỗi

**Câu hỏi kiểm tra:**

1. Vì sao request không credentials trả 401, còn `reader` tạo ghi chú trả 403?
2. Vì sao `roles("EDITOR")` khớp với `hasRole("EDITOR")` dù authority thực tế là `ROLE_EDITOR`?
3. Cơ chế nào xử lý header Basic và cơ chế nào quyết định quyền GET/POST?
4. Vì sao `SessionCreationPolicy.STATELESS` không đủ để kết luận “không có CSRF” khi client là browser?
5. Chính xác giả định nào khiến ta tắt CSRF trong bài này? Điều gì phải đổi nếu API được gọi từ web app?
6. Vì sao CORS hoặc Content-Type JSON không thay thế CSRF token?
7. Nếu cần tự động thu hồi credential hoặc chia quyền theo từng client, HTTP Basic có còn là lựa chọn phù hợp không?

**Gợi ý khi test lỗi:**

- **Luôn 401:** kiểm tra username/password, user store, header Basic có được gửi hay bị gateway loại bỏ, API có dùng HTTPS đúng cấu hình hay không.
- **403 dù đúng mật khẩu:** kiểm tra `ROLE_...`/`hasRole`, phương thức/URL đúng matcher và quyền của tài khoản.
- **POST 403 dù đã cấp EDITOR:** có thể chain khác bật CSRF, matcher/role không khớp, hoặc cấu hình thực tế khác bài. Kiểm tra filters và response trước khi tự động tắt CSRF.
- **Redirect đến trang login:** có thể chưa tắt form login hoặc request đang đi qua chain khác; API trong bài phải trả trạng thái HTTP cho client.
- **POST báo 400/415:** kiểm tra JSON body và `Content-Type: application/json`; lỗi này khác với 401/403.
- **GET không thấy ghi chú:** xác nhận đã POST 201, ứng dụng chưa restart và đang gọi cùng instance; ví dụ chỉ lưu dữ liệu trong RAM.

**Tiêu chí hoàn thành:** Có mã chạy được trong Spring Boot Servlet; năm test security quan trọng đạt; có bằng chứng request 401, 403, 200, 201; giải thích được luồng Basic; và viết được quyết định **“tắt CSRF cho non-browser-only API” kèm ranh giới “Basic dùng trong browser vẫn có nguy cơ CSRF”**.

## 12. Tài liệu chính thức để đào sâu

- [Spring Security — HTTP Basic Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/basic.html): challenge/response, `BasicAuthenticationFilter` và cấu hình `httpBasic`.
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): quy tắc bảo vệ, CSRF token và trường hợp client trình duyệt.
- [Spring Security — CSRF Overview](https://docs.spring.io/spring-security/reference/features/exploits/csrf.html): vì sao ứng dụng stateless và Basic trong browser vẫn có thể bị CSRF.
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): request matching, `hasRole`, `denyAll`.
- [Spring Security — Testing](https://docs.spring.io/spring-security/reference/servlet/test/index.html): MockMvc, authentication và authorization tests.

**Kết luận học tập:** HTTP Basic giải quyết việc xác minh credentials trên mỗi request, còn Spring Security authorization quyết định endpoint có được gọi hay không. **Chính sách CSRF phải dựa trên loại client và cách credentials được gửi**, không dựa vào tên giao thức, trạng thái stateless hay định dạng JSON.
