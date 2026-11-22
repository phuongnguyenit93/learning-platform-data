# HTTP 401, 403, 404 và chính sách không tiết lộ sự tồn tại của dữ liệu

> Phạm vi: xử lý yêu cầu bị từ chối trong API dùng Spring Security **Servlet**. Bài này phân biệt lỗi xác thực, lỗi phân quyền và tài nguyên không tìm thấy; sau đó áp dụng chính sách trả 404 để người gọi không suy ra dữ liệu của người khác có tồn tại. Ví dụ dùng Java 17+, Spring Boot 3.x và Spring Security 6.x.

## 1. Mục tiêu và nguyên tắc

Sau bài này, bạn cần trả lời được: (1) khi nào gửi 401, 403, 404; (2) Spring Security chuyển lỗi xác thực/phân quyền thành phản hồi HTTP như thế nào; (3) khi nào có thể thay 403 bằng 404; (4) cách thiết kế truy vấn và kiểm thử để không lộ ID, tenant, owner hoặc trạng thái của dữ liệu.

**Xác thực (authentication)** trả lời “người gọi là ai?”. **Phân quyền (authorization)** trả lời “người gọi đó được làm gì với đối tượng nào, trong ngữ cảnh nào?”. Một HTTP status chỉ là thông điệp gửi cho client; nó **không thay thế** kiểm tra quyền ở server. Trong API có dữ liệu riêng tư, đôi khi ngay cả câu trả lời “tài nguyên này có tồn tại” cũng là thông tin nhạy cảm.

Ví dụ một API có `GET /api/documents/10`. Nếu tài liệu 10 thuộc Alice, Bob không được đọc nó. Khi Bob đoán số 10, hệ thống có thể chủ động trả cùng một phản hồi như với một ID không tồn tại để Bob không xác định được Alice có tài liệu đó hay không.

## 2. Ý nghĩa HTTP chính xác

| HTTP | Ý nghĩa chuẩn | Tình huống thường gặp | Điều client nên hiểu |
|---|---|---|---|
| `401 Unauthorized` | Thiếu thông tin xác thực hợp lệ cho tài nguyên đích | Chưa đăng nhập, thiếu token, token hết hạn/không hợp lệ | Cần cung cấp hoặc làm mới thông tin xác thực phù hợp |
| `403 Forbidden` | Server hiểu yêu cầu nhưng từ chối thực hiện | Đã xác thực, thiếu role/scope/quyền thao tác; một chính sách khác cấm | Không nên tự động gửi lại cùng quyền và mong thành công |
| `404 Not Found` | Không tìm thấy biểu diễn hiện tại **hoặc** server không muốn tiết lộ rằng tài nguyên tồn tại | ID sai, đã xóa, hoặc tài nguyên bị che giấu theo chính sách | Không thể kết luận chỉ từ status rằng đối tượng thực sự không tồn tại |

Lưu ý quan trọng:

- Tên `401 Unauthorized` dễ gây hiểu nhầm: trong thực tế nó liên quan đến **authentication**. Theo RFC 9110, phản hồi 401 **phải** có ít nhất một `WWW-Authenticate` challenge thích hợp, ví dụ `WWW-Authenticate: Basic realm="api"` hoặc `WWW-Authenticate: Bearer realm="api"`. Chỉ ghi status 401 mà không xử lý challenge là thiếu ngữ nghĩa HTTP.
- `403` không đồng nghĩa “chưa đăng nhập”. Người gọi đã xác thực nhưng thiếu quyền là trường hợp phổ biến. Chính sách như chặn theo trạng thái tài khoản cũng có thể dẫn đến 403.
- Theo RFC 9110, server **được phép** gửi `404` thay cho `403` khi muốn giấu sự tồn tại của tài nguyên bị cấm truy cập. Đây là quyết định thiết kế có chủ đích, không phải quy tắc “mọi trường hợp 403 đều đổi thành 404”.
- `404` có thể được cache theo heuristic trong HTTP. Với kết quả liên quan đến dữ liệu riêng tư, cần kiểm soát `Cache-Control` và cấu hình reverse proxy/CDN để tránh chia sẻ hoặc giữ lại phản hồi theo quyền của người dùng.

### Ba trục cần tách bạch

1. **Ai gọi?** Không có thông tin xác thực hợp lệ → đường đi 401 tại endpoint được bảo vệ.
2. **Người đó có thấy sự tồn tại của đối tượng không?** Không có quyền biết ID/đối tượng → thường trả 404 thống nhất với ID không tồn tại.
3. **Nếu được biết đối tượng, có quyền thực hiện thao tác không?** Biết đối tượng nhưng không được sửa/xóa/xem báo cáo → có thể trả 403.

Đừng gọi 404 là “bảo mật hơn” một cách tuyệt đối. 404 chỉ che giấu sự tồn tại qua **một kênh phản hồi**; nếu response body, độ trễ, kích thước, cache, danh sách, log công khai hoặc thông báo phụ khác vẫn tiết lộ thông tin thì chính sách chưa đạt mục tiêu.

## 3. Bảng quyết định cho endpoint được bảo vệ

| Trạng thái người gọi và đối tượng | Status đề xuất | Lý do |
|---|---:|---|
| Chưa xác thực, gọi `GET /api/documents/10` | 401 | Yêu cầu đăng nhập trước khi xét ID |
| Có credential nhưng xác thực thất bại | 401 | Credential không hợp lệ |
| Alice có quyền đọc tài liệu 10 của Alice | 200 | Cho phép, trả dữ liệu |
| Alice truy cập ID 999 không tồn tại | 404 | Không có tài nguyên hiển thị |
| Bob truy cập ID 10 của Alice, sự tồn tại cần giữ kín | 404 | Tài nguyên không hiển thị với Bob |
| Alice biết tài liệu 10 của mình nhưng role không được xóa | 403 | Tài liệu thấy được, thao tác bị cấm |
| Alice gọi endpoint quản trị đã biết `/api/admin/report` nhưng thiếu role | 403 | Cấm thao tác toàn cục, không có ID riêng tư cần che |
| Gọi sai một route chưa tồn tại | 404 (thường) | Không có endpoint tương ứng; thứ tự filter và chính sách bảo vệ có thể ảnh hưởng kết quả thực tế |

Đây là **một chính sách mẫu** cho API tài liệu cá nhân, không phải luật áp dụng giống nhau cho mọi hệ thống. Nếu một resource công khai danh tính nhưng nội dung riêng tư, 403 có thể phù hợp hơn 404. Nếu chính sự tồn tại của resource là bí mật, hãy cố định một lựa chọn 404 cho cả ID không tồn tại và ID không thể nhìn thấy.

### Quy trình quyết định

```text
Yêu cầu vào endpoint cần bảo vệ
  ├─ Chưa có/xác thực credential không thành công?
  │    └─ 401 + WWW-Authenticate thích hợp
  └─ Đã xác thực
       ├─ Đối tượng không tồn tại trong phạm vi người gọi ĐƯỢC NHÌN THẤY?
       │    └─ 404 chung cho "không có" và "không được thấy"
       └─ Đối tượng hiển thị với người gọi
            ├─ Không được làm thao tác đang yêu cầu? → 403
            └─ Được làm? → tiếp tục nghiệp vụ (200/201/204/... tùy thao tác)
```

Không nhất thiết truy vấn toàn bộ đối tượng trước rồi mới kiểm tra owner. Một truy vấn ràng buộc ngay theo người gọi giúp tránh vô tình đưa bản ghi ngoài phạm vi vào controller, DTO, audit công khai hoặc cache.

## 4. Spring Security Servlet thực sự xử lý từ chối ra sao?

Luồng khái quát với cấu hình `authorizeHttpRequests` và cơ chế xác thực HTTP Basic/Bearer:

```text
HTTP request
  → SecurityFilterChain
  → filter xác thực (ví dụ BasicAuthenticationFilter, BearerTokenAuthenticationFilter)
  → ExceptionTranslationFilter bao quanh phần filter phía sau
  → AuthorizationFilter / các bước xử lý tiếp theo
  → DispatcherServlet → controller → service/repository
```

- `AuthorizationFilter` lấy thông tin `Authentication` và dùng `AuthorizationManager` đánh giá quy tắc. Khi không được phép, nó ném `AccessDeniedException` (hoặc lớp dẫn xuất).
- `ExceptionTranslationFilter` không tự ra quyết định quyền. Nó bắt `AuthenticationException` và `AccessDeniedException` từ chuỗi xử lý phía sau để chuyển sang cơ chế phản hồi.
- Nếu phát hiện cần xác thực hoặc người dùng anonymous bị từ chối, `ExceptionTranslationFilter` gọi `AuthenticationEntryPoint`. HTTP Basic thường trả 401 kèm challenge; ứng dụng dùng form login có thể trả **302 chuyển tới trang đăng nhập**, nên đừng mặc định mọi hệ thống Spring Security luôn trả 401.
- Nếu người dùng đã xác thực nhưng bị từ chối, nó gọi `AccessDeniedHandler`; hành vi thường thấy là 403.
- Lỗi xác thực xảy ra ngay trong filter xác thực có thể được filter đó chuyển trực tiếp tới failure handler/entry point. Không phải mọi 401 đều đi qua cùng một nhánh `ExceptionTranslationFilter`.
- Kiểm tra ở method layer (`@PreAuthorize`, `@PostAuthorize`) cũng có thể tạo từ chối. Với yêu cầu servlet đi qua Security filter chain, nó có thể được dịch thành phản hồi bởi cơ chế trên; nhưng thứ tự filter, exception handler MVC và cách bạn bắt ngoại lệ có thể thay đổi điều quan sát được.

**Điểm mấu chốt:** `AuthenticationEntryPoint` phụ trách nhánh cần xác thực; `AccessDeniedHandler` phụ trách nhánh từ chối quyền. Chính sách “resource của người khác → 404” thường phải diễn ra tại **nghiệp vụ/truy vấn đối tượng**, không nên ép mọi `AccessDeniedException` trong toàn ứng dụng thành 404.

## 5. Ví dụ chạy được: 401 / 403 / 404 khác nhau thế nào?

Dựng ứng dụng nhỏ sử dụng **Spring Boot 3.3.x, Java 17, Spring Security 6.x**, HTTP Basic để thấy rõ các status. Dữ liệu nằm trong bộ nhớ, chỉ để học; ứng dụng thực tế thay bằng repository giới hạn theo tenant/owner và hệ thống xác thực an toàn.

Cấu trúc:

```text
build.gradle
src/main/java/demo/DenialDemoApplication.java
src/main/java/demo/SecurityConfig.java
src/main/java/demo/DocumentController.java
src/test/java/demo/DenialDemoApplicationTests.java
```

`build.gradle` (ví dụ phiên bản cụ thể, cập nhật bản vá phù hợp khi dùng thực tế):

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

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

`src/main/java/demo/DenialDemoApplication.java`:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DenialDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DenialDemoApplication.class, args);
    }
}
```

`src/main/java/demo/SecurityConfig.java`:

```java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/documents/**").authenticated()
                .requestMatchers(HttpMethod.GET, "/api/admin/report").hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .build();
    }

    @Bean
    UserDetailsService userDetailsService() {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password("{noop}alicepass")
                .roles("USER")
                .build(),
            User.withUsername("bob")
                .password("{noop}bobpass")
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password("{noop}adminpass")
                .roles("ADMIN")
                .build()
        );
    }
}
```

Ở đây `authenticated()` chỉ đòi người gọi có danh tính hợp lệ; **chưa quyết định** Alice có được đọc tài liệu cụ thể của Bob hay không. `hasRole("ADMIN")` tương đương kiểm tra authority `ROLE_ADMIN`. `{noop}` lưu mật khẩu dạng rõ **chỉ phục vụ demo**, tuyệt đối không dùng với người dùng thật.

`src/main/java/demo/DocumentController.java`:

```java
package demo;

import java.util.Map;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DocumentController {

    private final Map<Long, Document> documents = Map.of(
        10L, new Document(10L, "alice", "Tai lieu rieng cua Alice"),
        20L, new Document(20L, "bob", "Tai lieu rieng cua Bob")
    );

    @GetMapping("/api/documents/{id}")
    public ResponseEntity<DocumentResponse> read(
            @PathVariable long id, Authentication authentication) {

        // Bản demo dùng bộ nhớ. Với DB, truy vấn ngay theo id + owner/tenant.
        return documents.values().stream()
            .filter(doc -> doc.id() == id
                && doc.owner().equals(authentication.getName()))
            .findFirst()
            .map(doc -> ResponseEntity.ok(
                new DocumentResponse(doc.id(), doc.title())))
            .orElseGet(() -> ResponseEntity.notFound().build());
    }

    @GetMapping("/api/admin/report")
    public String adminReport() {
        return "Admin report";
    }

    private record Document(long id, String owner, String title) {}

    public record DocumentResponse(long id, String title) {}
}
```

Hai trường hợp **không có ID 10** và **có ID 10 nhưng Bob không được thấy** đều kết thúc bằng `ResponseEntity.notFound().build()`. Controller không tiết lộ khác biệt qua response body; cũng không trả owner/title của tài liệu ngoài quyền. Endpoint admin minh họa 403 ở tầng `AuthorizationFilter`.

### Chạy và kiểm tra thủ công

Trong project Gradle có wrapper và JDK 17+, chạy `./gradlew bootRun` (trên Windows dùng `gradlew.bat bootRun`). Với `curl`, chỉ in HTTP status:

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/api/documents/10
# 401: chưa có credential

curl -s -o /dev/null -w '%{http_code}\n' -u alice:alicepass http://localhost:8080/api/documents/10
# 200: Alice thấy tài liệu của mình

curl -s -o /dev/null -w '%{http_code}\n' -u bob:bobpass http://localhost:8080/api/documents/10
# 404: Bob không được thấy tài liệu của Alice

curl -s -o /dev/null -w '%{http_code}\n' -u alice:alicepass http://localhost:8080/api/documents/999
# 404: ID không tồn tại đối với Alice

curl -s -o /dev/null -w '%{http_code}\n' -u alice:alicepass http://localhost:8080/api/admin/report
# 403: Alice không có role ADMIN

curl -s -o /dev/null -w '%{http_code}\n' -u admin:adminpass http://localhost:8080/api/admin/report
# 200: admin có quyền
```

Các dòng bắt đầu bằng `#` ở trên là **kết quả mong đợi**, không phải output đã thu thập từ server đang chạy. Để kiểm tra challenge, chạy `curl -i http://localhost:8080/api/documents/10` và tìm `WWW-Authenticate` trong response 401. Cấu hình Basic mặc định thường gửi challenge dạng `Basic`. Không lưu trữ hoặc in credential thật vào log/lịch sử shell.

### Kiểm thử hồi quy bằng MockMvc

`src/test/java/demo/DenialDemoApplicationTests.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class DenialDemoApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void anonymousNeedsAuthentication() throws Exception {
        mvc.perform(get("/api/documents/10"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void ownerCanRead() throws Exception {
        mvc.perform(get("/api/documents/10"))
            .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(username = "bob", roles = "USER")
    void hiddenDocumentLooksMissing() throws Exception {
        mvc.perform(get("/api/documents/10"))
            .andExpect(status().isNotFound());
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void missingDocumentLooksMissing() throws Exception {
        mvc.perform(get("/api/documents/999"))
            .andExpect(status().isNotFound());
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void knownAdminOperationIsForbidden() throws Exception {
        mvc.perform(get("/api/admin/report"))
            .andExpect(status().isForbidden());
    }
}
```

Chạy `./gradlew test`. Đây là bộ test về **quyết định status**. Trong hệ thống thực, bổ sung so sánh JSON error, header và chính sách cache cho cặp “ID không tồn tại / ID bị ẩn”; test tách tenant, quyền read/write, user bị vô hiệu hóa và mỗi authentication scheme thực tế.

## 6. Thiết kế che giấu sự tồn tại trong nghiệp vụ

### 6.1. Query trong phạm vi được phép xem

**Mẫu kém an toàn:**

```java
// Đoạn minh họa, không phải chương trình Java độc lập.
Document doc = repository.findById(id)
    .orElseThrow(() -> new NotFoundException("not found"));
if (!doc.getOwnerId().equals(currentUserId)) {
    throw new AccessDeniedException("document " + id + " belongs to another user");
}
return toDto(doc);
```

Đoạn trên phân biệt ID không tồn tại và ID của người khác bằng các loại ngoại lệ 404/403. Nếu policy yêu cầu bảo mật sự tồn tại, sự khác biệt đó là một tín hiệu giúp liệt kê ID.

**Mẫu nên dùng khi owner/tenant quyết định quyền nhìn thấy:**

```java
// Đoạn minh họa trong Spring Data JPA, dùng entity/repository phù hợp dự án.
interface DocumentRepository extends JpaRepository<DocumentEntity, Long> {
    Optional<DocumentEntity> findByIdAndTenantIdAndOwnerId(
        Long id, String tenantId, String ownerId);
}

// tenantId và ownerId phải lấy từ principal/claims đã xác thực,
// không tin giá trị client tự gửi nếu client được phép giả mạo.
return repository.findByIdAndTenantIdAndOwnerId(id, tenantId, ownerId)
    .map(this::toDto)
    .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND));
```

Với cả ID chưa từng tồn tại và ID ngoài phạm vi của người gọi, repository trả `Optional.empty()`, nên API có thể tạo **một** phản hồi 404 thống nhất. Không truy vấn bản ghi của tenant khác chỉ để xác định “nó có tồn tại không?”. Với danh sách, áp bộ lọc owner/tenant vào truy vấn phân trang và đếm tổng; đừng lấy tất cả rồi lọc tại UI.

**Trường hợp quyền phức tạp:** owner không phải điều kiện duy nhất (chia sẻ, nhóm, ACL, dự án, delegated access). Khi đó hãy định nghĩa một predicate “visible to principal” đủ bao quát, đưa nó xuống query/policy layer, rồi kiểm tra riêng quyền thao tác trên đối tượng đã nhìn thấy. Tránh dựa vào tên role đơn lẻ để thay thế kiểm tra object-level.

### 6.2. Định nghĩa chính sách nhất quán

Ví dụ sản phẩm quản lý hồ sơ:

- **Khả năng nhìn thấy:** Alice nhìn thấy hồ sơ của mình; người cùng dự án được gán quyền `read` có thể nhìn thấy hồ sơ được chia sẻ.
- **Khả năng thực hiện:** Người chỉ có `read` được GET, nhưng PUT/DELETE trả 403 nếu sự tồn tại đã được phép biết.
- **Không nhìn thấy:** Người ngoài dự án nhận 404 ở URL hồ sơ cụ thể, giống ID không tồn tại.
- **Endpoint chung:** API quản trị bị deny 403 nếu thiếu role; không ẩn tất cả thành 404.
- **Không đăng nhập:** API bảo vệ trả 401/challenge trước khi tra ID, để không tiết lộ dữ liệu cho anonymous.

Nếu tài nguyên có trạng thái `deleted`, `archived` hoặc `suspended`, quyết định có được thấy trạng thái ấy hay không cũng là một phần của visibility policy. Đừng trả 410 cho người không được biết đối tượng từng tồn tại; 410 khẳng định việc “đã biến mất”.

### 6.3. Cách tránh lộ qua kênh khác

1. **Cùng status, body và metadata công khai:** Cặp “không tồn tại” / “không hiển thị” nên có body chung như `{"title":"Not Found","status":404}` hoặc body rỗng, thông điệp không nhắc owner, tenant, “permission denied”, ID nội bộ. Cẩn thận cả `Content-Length`, header riêng và redirect.
2. **Đồng nhất đường xử lý hợp lý:** Khác biệt độ trễ lặp lại nhiều lần có thể trở thành oracle. Scoped query và index phù hợp thường giúp giảm khác biệt. Không tuyên bố “constant time” nếu chưa có bằng chứng đo đạc; so sánh phân phối latency dưới tải đại diện khi rủi ro cao.
3. **Chặn dò quét:** Áp rate limit hợp lý, theo dõi tỷ lệ 404 bất thường, ID đoán tuần tự, lỗi lặp lại. UUID ngẫu nhiên giúp giảm khả năng đoán ID nhưng **không thay kiểm tra quyền**.
4. **Cẩn thận cache:** Nếu phản hồi phụ thuộc người dùng, tenant hoặc token, không để CDN dùng chung response đó. Với API dữ liệu riêng tư, cân nhắc `Cache-Control: private, no-store` theo policy và kiểm tra header thực tế ở mọi gateway. Không chỉ dựa vào mặc định framework.
5. **Không rò rỉ từ endpoint phụ:** GET, HEAD, download URL, preview, export, tìm kiếm, autocomplete, total count, batch lookup, GraphQL, WebSocket và liên kết đính kèm phải áp cùng chính sách visibility. Đừng để GET trả 404 nhưng HEAD trả 403 hoặc export lộ tên file.
6. **Log nội bộ tách phản hồi công khai:** Server có thể audit lý do thật (`missing`/`out_of_scope`/`forbidden`), principal/tenant được xác thực, correlation ID và rule đã áp dụng. Không ghi bearer token, mật khẩu, nội dung nhạy cảm hay log công khai tiết lộ owner của đối tượng.
7. **Không biến mọi exception thành 404:** Lỗi DB, timeout, bug mapping, `NullPointerException` hay lỗi cấu hình không phải “tài nguyên không tồn tại”. Nuốt lỗi hệ thống thành 404 làm sai quan sát, che bug và có thể tạo các kênh rò rỉ khác.

## 7. Những trường hợp dễ chọn nhầm

### 401 so với 403 trong Bearer Token

Với OAuth 2.0 Resource Server, Spring Security hỗ trợ `BearerTokenAuthenticationEntryPoint` và `BearerTokenAccessDeniedHandler`:

- Thiếu token để truy cập endpoint được bảo vệ: 401 kèm `WWW-Authenticate: Bearer` (không nhất thiết công bố chi tiết).
- Token hết hạn/không hợp lệ: thường 401; Bearer challenge có thể có `error="invalid_token"` theo RFC 6750.
- Token hợp lệ nhưng thiếu scope để thực hiện thao tác: thường 403; Bearer challenge có thể có `error="insufficient_scope"`. Chỉ công bố tên scope khi phù hợp chính sách tiết lộ thông tin.

Không dùng `AccessDeniedHandler` tự viết để ép toàn bộ response thành JSON 403 nếu nó vô tình xóa `WWW-Authenticate` hoặc chặn cách Spring Security xử lý lỗi Bearer. Khi thay entry point/handler, kiểm tra lại cả status, challenge, body và error codes.

### 302 không phải lỗi 401 trong form login

Ứng dụng web dùng `formLogin` có thể redirect anonymous tới trang đăng nhập (302). Đó là hành vi có chủ đích cho trình duyệt, khác với API JSON/Basic/Bearer. Đặt kỳ vọng test theo authentication scheme thực sự của từng `SecurityFilterChain`.

### 403 không luôn cần đổi thành 404

Nếu một user nhìn thấy ticket trong cùng đội nhưng không được đóng ticket, 403 phản ánh rõ “biết ticket, không được thao tác”. Nếu user không được biết ticket tồn tại, 404 phù hợp hơn. Sự lựa chọn nằm ở **chính sách visibility** của sản phẩm.

### Cẩn thận khi custom ExceptionHandler

Một `@ControllerAdvice` bắt mọi `Exception` hoặc mọi `AccessDeniedException` có thể tạo phản hồi khác với `AuthenticationEntryPoint` / `AccessDeniedHandler` hoặc làm lộ `exception.getMessage()`. Chỉ map ngoại lệ nghiệp vụ đã được xác định rõ, để Spring Security xử lý lỗi security đúng tầng và test request thực đi qua filters.

### 404 của route và 404 của đối tượng là hai nhánh khác nhau

Route không tồn tại có thể bị từ chối sớm bởi filter (đặc biệt khi `anyRequest().authenticated()` hoặc `denyAll()`). Đừng suy ra từ status của một URL lạ rằng controller đã chạy. Với API thật, cấu hình routing, security matching và handler fallback nhất quán theo yêu cầu ứng dụng.

## 8. Checklist thiết kế và kiểm thử

| Câu hỏi kiểm tra | Điều cần đạt |
|---|---|
| Anonymous gọi endpoint bảo vệ? | 401 + challenge hợp lệ với Basic/Bearer; hoặc redirect đúng hợp đồng form login |
| Credential sai/hết hạn? | Bị từ chối trước nghiệp vụ, không truy cập dữ liệu |
| Authenticated nhưng không được biết resource? | Trả giống resource không tồn tại trong phần thông tin công khai |
| Được biết resource nhưng thiếu quyền thao tác? | Trả 403 nhất quán với policy |
| Có kiểm tra quyền trực tiếp trên object? | Query/policy ràng buộc owner, tenant, ACL; không chỉ dựa trên role của đường dẫn |
| List, HEAD, search, export, download, count có cùng policy? | Không có đường phụ tiết lộ tên/ID/trạng thái/số lượng |
| 404 có thể cache sai giữa người dùng? | Cache policy và CDN được kiểm chứng |
| Có test thật qua SecurityFilterChain? | Phủ 401, 403, 404 hidden, 404 missing, 200 allowed và header/body liên quan |
| Log/audit có hữu ích mà không lộ bí mật? | Có phân biệt nguyên nhân nội bộ, không công bố cho client ngoài quyền |

**Quy tắc ghi nhớ:** `401` yêu cầu xác thực hợp lệ; `403` nói yêu cầu bị cấm; `404` có thể nghĩa là không có **hoặc không được biết là có**. Chính sách tránh tiết lộ chỉ hiệu quả khi áp trên truy vấn, endpoint liên quan, body, header, cache và kiểm thử, chứ không chỉ đổi một mã HTTP.

## 9. Tài liệu chuẩn

- [RFC 9110 – HTTP Semantics, mục 15.5.2–15.5.5](https://www.rfc-editor.org/rfc/rfc9110.html#section-15.5.2): định nghĩa 401, 403, 404; cho phép 404 nhằm che giấu sự tồn tại.
- [RFC 6750 – OAuth 2.0 Bearer Token Usage, mục 3](https://www.rfc-editor.org/rfc/rfc6750.html#section-3): `WWW-Authenticate` và lỗi `invalid_token`, `insufficient_scope`.
- [Spring Security – Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html): `ExceptionTranslationFilter` và các filter bảo mật.
- [Spring Security – Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): `AuthorizationFilter` và `AuthorizationManager`.
- [Spring Security – Basic Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/basic.html): xử lý 401 và challenge trong HTTP Basic.
- [Spring Security – Bearer Token Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/bearer-tokens.html): xử lý token thất bại.