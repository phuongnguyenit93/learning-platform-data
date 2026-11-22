# Tạo hai nhóm quyền và kiểm chứng ma trận truy cập

## 1. Bài toán và kết quả cần đạt

Một ứng dụng quản lý tài liệu cần bảo vệ thao tác đọc và tạo tài liệu. Bài thực hành này tạo **hai nhóm quyền** trong Spring Security, gán hai người dùng vào nhóm tương ứng, thiết kế **ma trận truy cập** trước khi viết mã, sau đó dùng kiểm thử tự động để chứng minh mỗi yêu cầu được cho phép hoặc bị từ chối đúng chính sách.

Hai nhóm là:

- **READER (người đọc):** đọc được tài liệu nhưng không được tạo tài liệu.
- **EDITOR (người biên tập):** vừa đọc vừa tạo được tài liệu.

Kết quả của bài gồm một ứng dụng Spring Boot chạy được, một cấu hình `SecurityFilterChain`, bảng quyền cho các HTTP endpoint, các phép thử `MockMvc` và giải thích rõ `200`/`201`/`401`/`403`. Độ tin cậy của bài tập đến từ **cả kiểm thử tích cực và kiểm thử từ chối**: một phép thử thành công đơn lẻ không chứng minh phân quyền đúng.

Ví dụ sử dụng **Spring MVC / Servlet** để tập trung vào nền tảng phân quyền. Nếu dự án đang dùng Spring WebFlux, cần dùng `ServerHttpSecurity`, `SecurityWebFilterChain` và `WebTestClient` tương ứng; không sao chép cấu hình Servlet sang ứng dụng reactive.

## 2. Mô hình hai nhóm quyền

Nhóm quyền là khái niệm do ứng dụng định nghĩa để gom nhiều quyền cụ thể. Spring Security thực thi chính sách dựa trên các `GrantedAuthority` được gắn với `Authentication` đã xác thực.

| Nhóm | Các authority được cấp | Người dùng demo | Năng lực |
| --- | --- | --- | --- |
| `READER` | `document:read` | `alice` | Xem tài liệu |
| `EDITOR` | `document:read` và `document:write` | `bob` | Xem và tạo tài liệu |

Khách chưa đăng nhập không thuộc nhóm nào. Trong ví dụ, ứng dụng ánh xạ tên nhóm sang mảng authorities **khi dựng tài khoản**; không tự kiểm tra chuỗi `READER`/`EDITOR` ở từng endpoint.

**Ba điểm cần phân biệt:**

1. **Authentication** trả lời “ai đang gọi?”; **authorization** trả lời “người đó được thực hiện hành động nào?”. Đăng nhập đúng không tự mang lại quyền ghi.
2. `hasAuthority("document:write")` kiểm tra chính xác quyền `document:write`. `hasRole("EDITOR")` mặc định kiểm tra authority `ROLE_EDITOR`; hai cách này không tương đương nếu bạn chưa định nghĩa ánh xạ vai trò.
3. `EDITOR` đọc được vì **ta cấp rõ `document:read`** cho nhóm này. Spring Security không tự thừa kế quyền dựa trên thứ bậc tên nhóm.

Trong hệ thống thật, tên nhóm và thành viên có thể lưu trong cơ sở dữ liệu, LDAP hoặc nhà cung cấp danh tính. Phép ánh xạ nhóm sang authorities phải lấy từ nguồn được xác thực và tin cậy, không lấy giá trị `group` do client tự gửi để cấp quyền.

## 3. Thiết kế ma trận truy cập trước khi viết mã

Xét ba route của API:

- `GET /public/ping`: kiểm tra ứng dụng sẵn sàng, công khai.
- `GET /api/documents/{id}`: đọc tài liệu, cần `document:read`.
- `POST /api/documents?title=Note`: tạo tài liệu, cần `document:write`.

Ma trận dự kiến khi dùng HTTP Basic và để **CSRF protection mặc định** hoạt động:

| Request | Anonymous | `alice` (READER) | `bob` (EDITOR) |
| --- | --- | --- | --- |
| `GET /public/ping` | `200` | `200` | `200` |
| `GET /api/documents/42` | `401` | `200` | `200` |
| `POST /api/documents?title=Note` **có CSRF token hợp lệ** | `401` | `403` | `201` |
| `POST /api/documents?title=Note` **không có CSRF token** | `403` | `403` | `403` |
| `GET /api/unknown` | `403` theo `denyAll` | `403` | `403` |

Đây là mã HTTP **theo đúng cấu hình bài tập**, không phải quy luật cho mọi kiểu ứng dụng. Khi dùng form login, khách chưa xác thực có thể nhận chuyển hướng đăng nhập thay vì `401`. `403` có nhiều nguyên nhân: thiếu authority, thiếu CSRF token, hoặc quy tắc `denyAll`; vì vậy khi kiểm tra một quyền phải giữ các điều kiện còn lại cố định.

Quy tắc nền của bài: **chỉ công khai endpoint cần công khai, cấp đúng authority tối thiểu, từ chối mọi endpoint chưa định nghĩa**.

## 4. Khởi tạo dự án

Chuẩn bị Java 17+, Spring Boot 3.5.x (dòng Spring Security 6.x), Spring MVC và Gradle. Có thể tạo skeleton bằng Spring Initializr, chọn **Spring Web**, **Spring Security** và test dependencies. Trong `build.gradle` của dự án Spring Boot đã khởi tạo, bảo đảm có:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Đoạn trên chỉ là phần `dependencies`, không phải toàn bộ tệp build; plugin và phiên bản Spring Boot do skeleton dự án quản lý. Nếu dùng một dòng Boot khác, kiểm tra DSL và starter theo tài liệu đúng phiên bản.

Dùng package `com.example.accessmatrix`. Ứng dụng chính ở `src/main/java/com/example/accessmatrix/AccessMatrixApplication.java`; test ở `src/test/java/com/example/accessmatrix/AccessMatrixApplicationTests.java`.

## 5. Mã ứng dụng: gán nhóm và cấu hình quyền

Tệp `src/main/java/com/example/accessmatrix/AccessMatrixApplication.java`:

~~~java
package com.example.accessmatrix;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class AccessMatrixApplication {
    public static void main(String[] args) {
        SpringApplication.run(AccessMatrixApplication.class, args);
    }
}

@Configuration
class SecurityConfig {

    // Hai nhóm quyền của ứng dụng: READER và EDITOR.
    private static final Map<String, String[]> GROUP_PERMISSIONS = Map.of(
        "READER", new String[] { "document:read" },
        "EDITOR", new String[] { "document:read", "document:write" }
    );

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("alice-pass"))
                .authorities(GROUP_PERMISSIONS.get("READER"))
                .build(),
            User.withUsername("bob")
                .password(encoder.encode("bob-pass"))
                .authorities(GROUP_PERMISSIONS.get("EDITOR"))
                .build()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public/ping")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/documents/{id}")
                    .hasAuthority("document:read")
                .requestMatchers(HttpMethod.POST, "/api/documents")
                    .hasAuthority("document:write")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());

        // Giữ CSRF protection mặc định để thử riêng điều kiện này.
        return http.build();
    }
}

@RestController
class DocumentController {

    @GetMapping("/public/ping")
    String ping() {
        return "pong";
    }

    @GetMapping("/api/documents/{id}")
    String read(@PathVariable("id") long id) {
        return "document:" + id;
    }

    @PostMapping("/api/documents")
    @ResponseStatus(HttpStatus.CREATED)
    String create(@RequestParam("title") String title) {
        return "created:" + title;
    }
}
~~~

Toàn bộ đoạn trên có thể đặt trong **một tệp** vì `AccessMatrixApplication` là lớp `public` duy nhất; hai lớp còn lại có phạm vi package. Khi chạy, Spring Boot phát hiện `@Configuration` và `@RestController` trong cùng package để đăng ký các bean/route.

### Giải thích từng thành phần

**Ánh xạ hai nhóm.** `GROUP_PERMISSIONS` cho thấy từng nhóm thực sự sở hữu authority nào. `UserDetailsService` tạo hai tài khoản với authorities từ nhóm đã chọn; mỗi lần HTTP Basic xác thực thành công, Spring Security dùng các authorities đó khi kiểm tra quyền. Số người dùng có thể tăng mà vẫn dùng lại một bản định nghĩa nhóm.

**Mật khẩu của tài khoản demo.** `PasswordEncoderFactories.createDelegatingPasswordEncoder()` tạo bộ mã hóa hỗ trợ định danh thuật toán; `encoder.encode(...)` mã hóa mật khẩu trước khi lưu vào kho nhớ. Tuy nhiên chuỗi `alice-pass` và `bob-pass` vẫn nằm trong mã nguồn bài tập. Không dùng mật khẩu cố định, lưu tài khoản trong bộ nhớ hoặc cấu hình này để triển khai sản xuất.

**Thứ tự và phạm vi của rule.** `authorizeHttpRequests` xét các cặp matcher/quy tắc theo thứ tự, quy tắc đầu tiên khớp sẽ quyết định. Rule GET tài liệu chỉ cấp quyền đọc; rule POST tài liệu chỉ cấp quyền ghi; `anyRequest().denyAll()` từ chối cả các HTTP method khác và những URL chưa được công bố. Không thay `denyAll` bằng `authenticated` nếu yêu cầu là cho phép đúng các endpoint trong ma trận.

**CSRF độc lập với phân quyền.** `httpBasic` là cơ chế xác thực phục vụ thử nghiệm. Spring Security giữ CSRF protection mặc định cho các request gây thay đổi trạng thái như POST. Bộ test ở dưới dùng `csrf()` để tạo token hợp lệ, nhờ vậy có thể phân biệt `403` do thiếu quyền ghi với `403` do thiếu token. HTTP Basic có thể được trình duyệt tự gửi; không dùng luận điểm “API dùng Basic nên cứ tắt CSRF”.

**Phản hồi nghiệp vụ demo.** GET tài liệu 42 trả `document:42`, POST `title=Note` trả `created:Note` với `201`. Đây chỉ là chuỗi minh họa để kiểm thử được kết quả, chưa có database, quyền sở hữu từng bản ghi hay thao tác lưu dữ liệu.

## 6. Kiểm thử tích hợp toàn bộ ma trận

Tệp `src/test/java/com/example/accessmatrix/AccessMatrixApplicationTests.java`:

~~~java
package com.example.accessmatrix;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AccessMatrixApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointIsOpen() throws Exception {
        mvc.perform(get("/public/ping"))
            .andExpect(status().isOk())
            .andExpect(content().string("pong"));
    }

    @Test
    void anonymousCannotRead() throws Exception {
        mvc.perform(get("/api/documents/42"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void readerCanReadButCannotCreate() throws Exception {
        mvc.perform(get("/api/documents/42")
                .with(httpBasic("alice", "alice-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("document:42"));

        mvc.perform(post("/api/documents")
                .param("title", "Note")
                .with(httpBasic("alice", "alice-pass"))
                .with(csrf()))
            .andExpect(status().isForbidden());
    }

    @Test
    void editorCanReadAndCreate() throws Exception {
        mvc.perform(get("/api/documents/42")
                .with(httpBasic("bob", "bob-pass")))
            .andExpect(status().isOk());

        mvc.perform(post("/api/documents")
                .param("title", "Note")
                .with(httpBasic("bob", "bob-pass"))
                .with(csrf()))
            .andExpect(status().isCreated())
            .andExpect(content().string("created:Note"));
    }

    @Test
    void anonymousWithCsrfCannotCreate() throws Exception {
        mvc.perform(post("/api/documents")
                .param("title", "Note")
                .with(csrf()))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void validEditorWithoutCsrfIsRejected() throws Exception {
        mvc.perform(post("/api/documents")
                .param("title", "Note")
                .with(httpBasic("bob", "bob-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void unknownRouteIsDeniedEvenForEditor() throws Exception {
        mvc.perform(get("/api/unknown")
                .with(httpBasic("bob", "bob-pass")))
            .andExpect(status().isForbidden());
    }
}
~~~

Bộ test có **bảy phương thức**, bao gồm cả test chứa hai request để đối chiếu trong cùng người dùng. Những assertion quan trọng:

- **`alice` và `bob` đọc thành công:** chứng minh quyền `document:read` được gán cho cả hai nhóm.
- **`alice` POST kèm CSRF là `403`:** chứng minh thiếu `document:write` bị từ chối dù đã xác thực.
- **`bob` POST kèm CSRF là `201`:** chứng minh đủ cả điều kiện xác thực, quyền ghi và CSRF để tạo.
- **`bob` POST không CSRF là `403`:** chứng minh quyền ghi **không vô hiệu hóa** kiểm tra CSRF.
- **Anonymous GET là `401`:** với Basic, khách phải xác thực trước khi đọc tài liệu.
- **`bob` vào URL không khai báo là `403`:** quyền biên tập không mở toàn bộ ứng dụng.

`httpBasic("alice", ...)` và `httpBasic("bob", ...)` gửi thông tin xác thực thực sự qua chain, thay vì giả lập authority bằng `@WithMockUser`. Nhờ đó bài test kiểm tra được **cả việc ánh xạ từ nhóm sang authority**. `MockMvc` có hỗ trợ Security từ `@AutoConfigureMockMvc`; `csrf()` của `spring-security-test` thêm CSRF token trong request POST. Đừng bỏ token chỉ để so sánh authority, vì ca POST sẽ thất bại vì một nguyên nhân khác.

### Chạy và quan sát

Trong thư mục gốc của dự án Gradle đã tạo:

~~~bash
./gradlew test
./gradlew bootRun
~~~

Chạy `test` trước để kiểm chứng ma trận; chạy `bootRun` riêng khi muốn gọi HTTP thật. Trên Windows PowerShell sử dụng `.\gradlew.bat test` và `.\gradlew.bat bootRun`. Với đúng cấu hình và đường dẫn trong bài, cả bảy phương thức test phải thành công; log khởi tạo và thời gian chạy khác nhau theo môi trường.

Với server đang chạy ở cổng mặc định 8080, thử các yêu cầu GET:

~~~bash
curl -i http://localhost:8080/public/ping
curl -i http://localhost:8080/api/documents/42
curl -i -u alice:alice-pass http://localhost:8080/api/documents/42
curl -i -u bob:bob-pass http://localhost:8080/api/documents/42
~~~

Status theo thứ tự mong đợi: `200`, `401`, `200`, `200`. Trên Windows PowerShell, có thể dùng `curl.exe` để tránh alias `curl`. Với POST, chỉ dùng `curl -u ... -X POST` mà không kèm CSRF token sẽ nhận `403`; phép thử `MockMvc` đã cung cấp token để xác nhận đúng quyền ghi.

## 7. Cách đọc kết quả và tìm lỗi

Hãy đối chiếu từng ca với **ba cổng kiểm tra**: có danh tính không, có quyền theo rule không, và (nếu POST) có CSRF token hợp lệ không.

| Trường hợp | Authentication | Authority cần thiết | CSRF | Kết quả |
| --- | --- | --- | --- | --- |
| `alice` đọc | Có | Có `document:read` | Không cần cho GET | `200` |
| `bob` đọc | Có | Có `document:read` | Không cần cho GET | `200` |
| `alice` tạo | Có | Thiếu `document:write` | Có | `403` |
| `bob` tạo | Có | Có `document:write` | Có | `201` |
| `bob` tạo, thiếu CSRF | Có | Có `document:write` | Không | `403` |
| Anonymous đọc | Không | Không xác định | Không cần cho GET | `401` |

Cặp thử nghiệm có giá trị nhất là **cùng một POST với cùng CSRF token hợp lệ, chỉ thay `alice` bằng `bob`**: `403` chuyển thành `201` là bằng chứng chính sách `document:write` hoạt động. Cặp thứ hai giữ nguyên `bob` và mọi tham số, chỉ bỏ CSRF: `201` chuyển thành `403` xác nhận nguyên nhân từ CSRF.

Nếu kết quả sai:

1. Xác minh URI, HTTP method và controller thật sự tồn tại. `404` có thể là lỗi mapping controller, không chứng minh rule cho phép.
2. Xem authority thực tế của user. `hasAuthority` so đúng chuỗi và phân biệt chữ hoa/thường; đừng nhầm với `hasRole`.
3. Nếu POST trả `403` không mong muốn, kiểm tra CSRF trước khi sửa nhóm quyền.
4. Nếu tất cả request có credential vẫn `401`, kiểm tra username/password, cấu hình `UserDetailsService` và bộ mã hóa mật khẩu.
5. Nếu URL chưa khai báo vẫn truy cập được, kiểm tra thứ tự matcher, rule rộng và những `SecurityFilterChain` khác có thể tồn tại trong dự án.
6. Không sửa lỗi bài test bằng cách tắt toàn bộ Spring Security, bỏ `denyAll` hay thêm `permitAll` quá rộng.

## 8. Bài tập biến thể để hiểu sâu

**Thí nghiệm 1 — Bỏ quyền đọc khỏi EDITOR.** Tạm thay mảng quyền `EDITOR` thành chỉ `document:write`. Dự đoán `bob` vẫn tạo được tài liệu (POST kèm CSRF trả `201`) nhưng đọc bị `403`. Sau khi thử, khôi phục hai quyền. Thí nghiệm chứng minh không có kế thừa quyền ngầm giữa các nhóm.

**Thí nghiệm 2 — Thêm thao tác xóa.** Giả sử thêm controller `DELETE /api/documents/{id}`. Vì rule mặc định là `denyAll`, cả hai nhóm ban đầu bị chặn. Hãy định nghĩa quyền mới `document:delete`, quyết định nhóm nào được cấp, thêm rule DELETE tương ứng và test hai chiều. Không mặc định suy ra quyền xóa từ quyền tạo.

**Thí nghiệm 3 — Thêm người dùng cùng nhóm.** Tạo `charlie` bằng authorities của `READER`. Kiểm chứng `charlie` có kết quả giống `alice`; mục đích là thấy nhóm quyền giúp áp dụng một chính sách cho nhiều tài khoản mà không lặp quyền ở các endpoint.

**Thí nghiệm 4 — Quyền đối với bản ghi.** Thay nội dung giả lập bằng tài liệu thật: `alice` chỉ được đọc tài liệu thuộc tenant của mình. Kiểm tra `document:read` ở HTTP là chưa đủ; ở service phải tra dữ liệu tin cậy và xác minh chủ sở hữu/tenant, có thể dùng `@PreAuthorize` và `AuthorizationManager` theo kiến trúc. Thêm test cross-tenant và test tài liệu do người khác sở hữu. Không tin `ownerId` do client tự điền.

Mỗi thí nghiệm cần ghi **dự đoán mã HTTP trước khi thay mã**, sửa một thay đổi, chạy lại test rồi phục hồi chính sách gốc. Đó là cách luyện tư duy chính sách thay vì chỉnh cấu hình đến khi test xanh.

## 9. Những sai lầm thường gặp

- **Chỉ thử trường hợp được phép:** READER bị cấp nhầm quyền ghi vẫn có thể lọt. Test ca từ chối là bắt buộc.
- **Coi nhóm là role có sẵn của Spring Security:** trong bài này `READER`/`EDITOR` là nhãn nhóm ứng dụng. Spring Security chỉ nhìn thấy `document:read`/`document:write` được gán khi xác thực.
- **Lẫn `hasRole` và `hasAuthority`:** `hasRole("EDITOR")` mặc định cần `ROLE_EDITOR`; không tự động hiểu `document:write`.
- **Tắt CSRF khi POST bị chặn:** xử lý nguyên nhân CSRF và authority riêng, theo loại client thật; không bỏ cơ chế bảo vệ vì thuận tiện cho demo.
- **Đặt matcher quá rộng trước rule chi tiết:** thứ tự rule quyết định request nào được xét. Để `anyRequest().denyAll()` cuối và chỉ mở chính xác route cần thiết.
- **Chỉ kiểm tra đường dẫn mà bỏ nghiệp vụ:** với bản ghi thật, cần chính sách sở hữu/tenant trong service hoặc tầng dữ liệu, không dừng ở quyền đọc chung.
- **Tin username hoặc nhóm do client truyền trong request:** kiểm tra bằng principal/authorities đã xác thực từ nguồn tin cậy.
- **Hiểu nhầm `403` luôn là “thiếu quyền”:** CSRF và `denyAll` cũng có thể tạo `403`; dùng test có kiểm soát để xác định lý do.

## 10. Tiêu chí hoàn thành và tài liệu đối chiếu

Bạn hoàn thành bài khi có thể tự giải thích đường đi **HTTP Basic → Authentication → GrantedAuthority → requestMatcher → quyết định cho phép/từ chối**, chỉ ra chính xác **hai nhóm** và authorities của từng nhóm, chạy bộ kiểm thử ma trận, và dự đoán được kết quả nếu đổi một quyền hoặc một rule.

Bài tập chỉ minh họa quyền ở lớp HTTP với tài khoản trong bộ nhớ và dữ liệu cố định. Trước khi áp dụng vào hệ thống thật, cần thiết kế nguồn danh tính, mật khẩu và bí mật, quyền ở service, sở hữu tài nguyên, ghi nhận thao tác bảo mật, kiểm tra tenant, CSRF theo client và các phép thử chống truy cập ngang quyền.

Tài liệu chính thức:

- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — In-Memory Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/in-memory.html)
- [Spring Security — Testing with MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html)
- [Spring Security — Testing CSRF](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html)
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
