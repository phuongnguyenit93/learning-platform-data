# @PostAuthorize kiểm tra quyền dựa trên giá trị trả về

> **Spring Security fundamentals → Bảo vệ phương thức.** `@PostAuthorize` là một cơ chế **method security** dùng để đánh giá quyền **sau khi phương thức đã chạy và đã tạo giá trị trả về, nhưng trước khi giá trị đó được trao cho bên gọi**. Bài học làm rõ thời điểm kiểm tra, cách sử dụng biến `returnObject` trong SpEL, cách phối hợp với `@PreAuthorize` và phân quyền theo đối tượng, cùng giới hạn đặc biệt quan trọng: **từ chối ở bước hậu kiểm không có nghĩa những thao tác trong phương thức chưa từng xảy ra**.

## 1. Vấn đề: cùng quyền đọc, nhưng không phải cùng dữ liệu

Giả sử Alice và Bob đều có authority `DOC_READ` trong hệ thống tài liệu. Cả hai có thể gọi endpoint đọc tài liệu:

- Tài liệu `id = 1` có `owner = alice`.
- Tài liệu `id = 2` có `owner = bob`.
- Alice gọi `GET /api/documents/1` → hợp lệ.
- Alice gọi `GET /api/documents/2` → **không được nhận nội dung tài liệu của Bob**, dù Alice cũng có `DOC_READ`.

Chỉ dùng `@PreAuthorize("hasAuthority('DOC_READ')")` chưa đủ vì cả Alice và Bob cùng thỏa mãn điều kiện chung. Một cách học dễ hiểu là kiểm tra owner của **đối tượng đã đọc được**:

```java
@PreAuthorize("hasAuthority('DOC_READ')")
@PostAuthorize("returnObject.owner == authentication.name")
public DocumentView findById(long id) {
    return repository.findById(id);
}
```

Đây là **đoạn minh họa đặt trong một Spring-managed service**; `DocumentView` và `repository` do ứng dụng định nghĩa. `@PreAuthorize` kiểm tra authority **trước** khi gọi `findById`. Nếu qua bước đó, method chạy và tạo `DocumentView`; `@PostAuthorize` tiếp tục kiểm tra `owner` của đối tượng trả về có trùng username đã xác thực hay không.

**Đọc đúng bản chất:** `@PostAuthorize` không phải bộ lọc SQL, không tự thay `id` và không ngăn repository thực hiện truy vấn. Nó là **cửa kiểm soát sau khi method có kết quả**, nhằm quyết định có trả kết quả ấy cho caller hay phát sinh lỗi từ chối quyền.

## 2. Cơ chế thực thi: before → method → after

Khi bật method security, Spring Security triển khai các method interceptor thông qua Spring AOP, thường là proxy cho Spring-managed bean. Với một method có cả hai annotation, luồng điển hình:

```text
Caller (Controller hoặc service khác)
             |
             v
Spring proxy / method security
             |
   @PreAuthorize expression
       |              |
       | deny         | grant
       v              v
  Không gọi      Method được gọi
  method          |
                  v
             Kết quả được tạo
                  |
                  v
          @PostAuthorize expression
              |              |
              | deny         | grant
              v              v
       AccessDeniedException   Trả kết quả
              |              |
         HTTP mapping       Caller xử lý
         tùy context       giá trị
```

Cụ thể:

1. Một lời gọi **đi qua Spring proxy** để vào method được bảo vệ.
2. `@PreAuthorize` (nếu có) đánh giá các điều kiện trên Authentication, tham số và chính sách trước khi thực thi. Nếu từ chối, method không chạy.
3. Method có thể đọc database, gọi API, ghi log, thay đổi cache hoặc làm những việc khác.
4. Nếu method **trả về bình thường**, Spring Security đánh giá `@PostAuthorize` trên kết quả đó.
5. Nếu biểu thức hậu kiểm trả **true**, caller nhận kết quả. Nếu **false**, method authorization từ chối và thông thường ném `AccessDeniedException`; nếu đang xử lý HTTP qua Spring Security, cấu hình exception handling sẽ quyết định response, thường là **403 với principal đã xác thực**.
6. Nếu method ném exception trước khi trả về, không có giá trị kết quả bình thường để đánh giá theo đường hậu kiểm này; xử lý exception vẫn cần chính sách thích hợp.

**Không nhầm thứ tự:** “`@PostAuthorize` chạy sau” không có nghĩa “mã trong method đã được tự động rollback nếu fail”. Việc undo transaction, database writes, gửi email, gửi message, side effect bên ngoài hoàn toàn không được bảo đảm chỉ nhờ annotation này.

## 3. Điều kiện SpEL và ý nghĩa của `returnObject`

`@PostAuthorize` nhận một **Spring Expression Language (SpEL)** expression đánh giá thành giá trị Boolean để quyết định. Biến nổi bật nhất là `returnObject`, tức **đối tượng mà method vừa trả về** theo ngữ nghĩa interceptor đang sử dụng.

Ví dụ:

```java
@PostAuthorize("returnObject.owner == authentication.name")
public DocumentView read(long id) { /* đọc tài liệu */ }
```

- `returnObject`: đối tượng `DocumentView` được trả về.
- `returnObject.owner`: property `owner` mà SpEL đọc qua JavaBean getter hoặc property accessor phù hợp.
- `authentication`: đối tượng `Authentication` của phiên gọi được bảo vệ.
- `authentication.name`: tên principal hiện tại do Spring Security xác định, **không phải username do client tự gửi trong request body**.
- `==`: so sánh bằng theo semantics SpEL; kết quả Boolean quyết định cho qua hay từ chối.

### 3.1. Những biểu thức hữu ích

| Biểu thức | Ý nghĩa | Điều kiện áp dụng |
|---|---|---|
| `returnObject.owner == authentication.name` | Cho chủ sở hữu nhận đối tượng | Đối tượng không null, owner phản ánh principal đúng cách |
| `returnObject == null || returnObject.owner == authentication.name` | Cho kết quả không tồn tại đi tiếp, kiểm tra owner nếu có | Method trả null khi không tìm thấy; handler sau đó có thể trả 404 |
| `hasAuthority('DOC_READ') && returnObject.owner == authentication.name` | Cần quyền hành động **và** đúng chủ sở hữu ở hậu kiểm | Nhưng nên chuyển kiểm tra quyền chung sang `@PreAuthorize` để không đọc DB thừa |
| `hasRole('ADMIN') || returnObject.owner == authentication.name` | Admin hoặc owner được đọc | Chính sách admin xuyên owner phải thực sự được nghiệp vụ chấp thuận |
| `@documentPolicy.canRead(authentication, returnObject)` | Gọi bean authorization để xử lý policy phức tạp | Bean `documentPolicy` tồn tại, API và null handling được xác minh |

Spring Security có hỗ trợ SpEL như `hasAuthority(...)`, `hasRole(...)` và hook `hasPermission(...)`. **`hasPermission` không tự hiểu ACL của mọi domain**: nếu muốn dùng một permission evaluator tuỳ biến, phải đăng ký/cấu hình cơ chế kiểm tra tương ứng và kiểm thử.

Khi viết `returnObject.owner`, bảo đảm object có getter/property mà SpEL thực sự truy cập được. Với Java class có `getOwner()`, biểu thức `owner` là JavaBean property chuẩn. Nếu dùng Java record, projection, proxy, map, nullable/Optional hoặc wrapper DTO, hãy xác nhận kiểu trả về và cách SpEL truy cập thành phần đó. Đừng chép một expression cho các kiểu dữ liệu khác nhau mà không test.

### 3.2. Null và trường hợp tài nguyên không tồn tại

Khi method có thể trả `null`, biểu thức sau dễ phát sinh lỗi truy cập property:

```java
@PostAuthorize("returnObject.owner == authentication.name")
```

Hãy quyết định semantics cụ thể:

```java
@PostAuthorize("returnObject == null || returnObject.owner == authentication.name")
```

Trong ví dụ này, `null` nghĩa là “không tìm thấy bản ghi” và được cho đi tiếp để controller trả 404. Tuy nhiên, nếu **một bản ghi tồn tại ngoài quyền**, hậu kiểm owner có thể trả 403; như vậy caller có thể phân biệt “không tồn tại” và “tồn tại nhưng bị cấm”. Ở nhiều API nhạy cảm, truy vấn **theo scope từ đầu** và trả 404 cho cả hai trường hợp có thể là chính sách ít lộ thông tin hơn.

Nếu method trả `Optional<DocumentView>`, `returnObject` là một wrapper theo contract method; đừng giả định `returnObject.owner` trỏ trực tiếp đến đối tượng bên trong. Chọn API rõ ràng, xử lý empty có chủ đích và test biểu thức trên chính return type.

### 3.3. Trả về danh sách không giống trả một object

`@PostAuthorize` không mặc định lặp qua mọi element của `List<DocumentView>` để kiểm tra owner. Một biểu thức trên `returnObject` phải phù hợp với **đối tượng List** hoặc gọi policy xét toàn bộ danh sách. `@PostFilter` có thể lọc các phần tử sau khi method trả collection, nhưng với danh sách lớn cần ưu tiên **lọc bằng predicate trong truy vấn database**: hậu lọc sau khi load có thể tốn tài nguyên, sai phân trang/count, rủi ro từ cache/log, và không làm query gốc an toàn hơn.

### 3.4. ResponseEntity, DTO, entity và giá trị bất đồng bộ

Đặt `@PostAuthorize` trên service trả **domain object/DTO** thường dễ đánh giá hơn trên controller trả `ResponseEntity<...>`: nếu annotation đặt trên method trả `ResponseEntity` thì `returnObject` là wrapper response, không tự động là `body`. Tránh dựa vào cấu trúc nội bộ của wrapper mà người review không thấy.

Với JPA entity có quan hệ lazy, việc đọc property trong hậu kiểm có thể kích hoạt truy cập database thêm hoặc gặp lỗi do persistence context; nên xác định dữ liệu cần authorize trước, giữ transaction rõ ràng và không vô tình lộ entity qua serialization.

## 4. `@PreAuthorize` và `@PostAuthorize` bổ sung nhau như thế nào?

| Tiêu chí | `@PreAuthorize` | `@PostAuthorize` |
|---|---|---|
| Thời điểm | Trước khi method chạy | Sau khi method tạo kết quả trả về |
| Kiểm tra thuận tiện | Authentication, role/authority, tham số, policy đã có trước khi đọc dữ liệu | Thuộc tính của object kết quả, owner/visibility được biết sau khi load |
| Nếu bị từ chối | Method thông thường chưa thực thi | Method **đã thực thi**; caller không nhận kết quả |
| Chi phí thường gặp | Có thể tránh đọc DB, remote call không cần thiết | Có thể đã thực hiện DB query/CPU/I/O |
| Rủi ro với write | Giảm nguy cơ side effect nếu đặt rule đúng | **Không phù hợp làm kiểm soát duy nhất** cho mutation |
| Ví dụ | `hasAuthority('DOC_READ')` | `returnObject.owner == authentication.name` |

Một method đọc có thể dùng **cả hai**, với tất cả điều kiện đều phải được thỏa mãn:

```java
@PreAuthorize("hasAuthority('DOC_READ')")
@PostAuthorize("returnObject == null || returnObject.owner == authentication.name")
public DocumentView read(long id) {
    return repository.findById(id);
}
```

Trình tự hợp lý: caller không có `DOC_READ` bị từ chối ngay, không gọi repository. Caller có `DOC_READ` nhưng owner sai bị từ chối sau khi repository trả object. Caller có quyền và owner đúng nhận kết quả. Dùng `@PreAuthorize` để không lãng phí I/O khi từ chối được sớm.

**Phân biệt action-level và object-level:** `DOC_READ` là quyền *đọc loại tài nguyên*; `owner == authentication.name` chỉ là một policy về *bản ghi cụ thể*. Sản phẩm thật có thể còn tenant membership, trạng thái, ACL, cấp quyền chia sẻ, vai trò quản trị và field-level permission. Không mặc định owner là chính sách đầy đủ cho mọi hệ thống.

## 5. Ví dụ Spring Boot chạy được: phân quyền kết quả đọc

Ví dụ này dùng **Spring Boot 3.x, Java 17+, Spring Security 6.x, Servlet MVC**. Nó không yêu cầu database thật: dữ liệu giả được giữ trong `Map` để tập trung vào hành vi `@PostAuthorize`. Có ba user: Alice, Bob và Viewer.

| User | Mật khẩu demo | Authorities | Kết quả đọc tài liệu |
|---|---|---|---|
| `alice` | `demo123` | `DOC_READ` | Đọc doc 1; bị từ chối doc 2 |
| `bob` | `demo123` | `DOC_READ` | Đọc doc 2; bị từ chối doc 1 |
| `viewer` | `demo123` | `PROFILE_READ` | Không qua `@PreAuthorize` đọc tài liệu |

### 5.1. Tạo project và dependencies

Tạo project **Spring Boot 3.x, Java 17+** bằng Spring Initializr, chọn Gradle, Spring Web, Spring Security. Đảm bảo khối `dependencies` trong `build.gradle` gồm:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Đây là **khối dependencies**, không phải toàn bộ file build: giữ Spring Boot plugin, Java configuration, repositories và BOM từ project được tạo. Chạy bằng Gradle Wrapper của project sau khi tạo đầy đủ cấu trúc.

### 5.2. Một tệp Java hoàn chỉnh

Đặt `src/main/java/example/postauth/PostAuthorizeApplication.java`:

```java
package example.postauth;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@EnableMethodSecurity
public class PostAuthorizeApplication {
    public static void main(String[] args) {
        SpringApplication.run(PostAuthorizeApplication.class, args);
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/ping").permitAll()
                .requestMatchers(
                    HttpMethod.GET, "/api/documents/*"
                ).authenticated()
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    UserDetailsService demoUsers() {
        UserDetails alice = User.withUsername("alice")
            .password("{noop}demo123")
            .authorities("DOC_READ").build();
        UserDetails bob = User.withUsername("bob")
            .password("{noop}demo123")
            .authorities("DOC_READ").build();
        UserDetails viewer = User.withUsername("viewer")
            .password("{noop}demo123")
            .authorities("PROFILE_READ").build();
        return new InMemoryUserDetailsManager(alice, bob, viewer);
    }
}

// Public record package-private cùng file, Spring/Jackson vẫn
// có thể serialize các component trong ví dụ.
record DocumentView(long id, String owner, String title) {
    // Getter JavaBean rõ ràng cho SpEL property "owner".
    public String getOwner() {
        return owner;
    }
}

@Service
class DocumentService {
    private final Map<Long, DocumentView> documents = Map.of(
        1L, new DocumentView(1L, "alice", "Alice plan"),
        2L, new DocumentView(2L, "bob", "Bob notes")
    );

    @PreAuthorize("hasAuthority('DOC_READ')")
    @PostAuthorize(
        "returnObject == null || returnObject.owner == authentication.name"
    )
    public DocumentView findById(long id) {
        // Đây là read-only operation.
        return documents.get(id);
    }
}

@RestController
class DocumentController {
    private final DocumentService service;

    DocumentController(DocumentService service) {
        this.service = service;
    }

    @GetMapping("/public/ping")
    public String ping() {
        return "ok";
    }

    @GetMapping("/api/documents/{id}")
    public ResponseEntity<DocumentView> get(
            @PathVariable long id) {
        DocumentView document = service.findById(id);
        if (document == null) {
            return ResponseEntity.notFound().build();
        }
        return ResponseEntity.ok(document);
    }
}
```

Tệp có một `public class` đúng tên file và các top-level class/record package-private trong cùng package. `@EnableMethodSecurity` bật interceptor cho `@PreAuthorize` và `@PostAuthorize`; riêng việc thêm starter Security **không tự bật method security**.

**Tại sao annotation đặt ở `DocumentService`?** `DocumentController` nhận `DocumentService` từ Spring qua constructor, do đó lời gọi `service.findById(...)` đi qua Spring-managed bean/proxy. Khi `findById(2)` trả `DocumentView(owner="bob")` nhưng principal là Alice, interceptor hậu kiểm từ chối **trước khi controller nhận được object để trả JSON**. Nếu gọi trực tiếp một instance tự tạo bằng `new DocumentService()` hoặc tự gọi cùng class qua `this` trong cấu hình proxy thông thường, method advice có thể bị bỏ qua.

**Bảo mật của dữ liệu demo:** `{noop}` là password encoder không mã hóa, **chỉ dùng cho local demo**. Dùng password encoder thích hợp, identity provider, TLS, bảo vệ secret và audit trong ứng dụng thật. Dữ liệu Map chỉ mô phỏng read; không tự bảo vệ truy vấn SQL, tenant hay cache. DTO trả cả trường `owner` cho mục đích quan sát; sản phẩm thật phải chọn projection theo quyền xem field.

### 5.3. Chạy app và gửi request

Trong project Boot có Gradle Wrapper:

```bash
./gradlew bootRun
```

Windows:

```powershell
.\gradlew.bat bootRun
```

Mặc định HTTP port là 8080 khi chưa bị cấu hình khác chiếm hoặc thay đổi. Gọi các request:

```bash
curl -i http://localhost:8080/public/ping
curl -i http://localhost:8080/api/documents/1
curl -i -u viewer:demo123 http://localhost:8080/api/documents/1
curl -i -u alice:demo123 http://localhost:8080/api/documents/1
curl -i -u alice:demo123 http://localhost:8080/api/documents/2
curl -i -u bob:demo123 http://localhost:8080/api/documents/2
curl -i -u alice:demo123 http://localhost:8080/api/documents/99
```

| Request | Trạng thái dự kiến | Vì sao |
|---|---:|---|
| Anonymous `GET /public/ping` | 200, `ok` | HTTP `permitAll` |
| Anonymous `GET /api/documents/1` | 401 | HTTP yêu cầu login, HTTP Basic entry point |
| Viewer `GET /api/documents/1` | 403 | HTTP qua được; `@PreAuthorize` chặn vì thiếu `DOC_READ` |
| Alice `GET /api/documents/1` | 200, JSON chứa `"owner":"alice"` | Qua tiền kiểm và hậu kiểm |
| Alice `GET /api/documents/2` | 403 | Đã đọc object Bob nhưng hậu kiểm không cho trả |
| Bob `GET /api/documents/2` | 200, JSON chứa `"owner":"bob"` | Chủ sở hữu khớp |
| Alice `GET /api/documents/99` | 404 | Method trả null, biểu thức cho null đi qua, controller trả not found |

Không cố định thứ tự thuộc tính JSON, response headers hoặc error body: những phần này có thể khác theo Jackson/Spring Boot/Spring Security và cấu hình. Ở demo, `403` cho document Bob có thể tiết lộ rằng tài liệu tồn tại; phần 7 trình bày cách thiết kế truy vấn an toàn hơn.

### 5.4. Integration test xác nhận hai lớp method security

Tạo `src/test/java/example/postauth/PostAuthorizeApplicationTest.java`:

```java
package example.postauth;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class PostAuthorizeApplicationTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    DocumentService service;

    @Test
    void httpAndMethodAuthorization() throws Exception {
        mvc.perform(get("/public/ping"))
            .andExpect(status().isOk())
            .andExpect(content().string("ok"));

        mvc.perform(get("/api/documents/1"))
            .andExpect(status().isUnauthorized());

        // Có login nhưng không có quyền gọi method: tiền kiểm chặn.
        mvc.perform(get("/api/documents/1")
                .with(httpBasic("viewer", "demo123")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/documents/1")
                .with(httpBasic("alice", "demo123")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.owner").value("alice"));

        // Cùng DOC_READ nhưng khác owner: hậu kiểm chặn.
        mvc.perform(get("/api/documents/2")
                .with(httpBasic("alice", "demo123")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/documents/2")
                .with(httpBasic("bob", "demo123")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.owner").value("bob"));

        mvc.perform(get("/api/documents/99")
                .with(httpBasic("alice", "demo123")))
            .andExpect(status().isNotFound());
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_READ")
    void directServiceCallStillUsesMethodProxy() {
        assertThat(service.findById(1).getOwner()).isEqualTo("alice");
        assertThatThrownBy(() -> service.findById(2))
            .isInstanceOf(AccessDeniedException.class);
    }
}
```

Chạy:

```bash
./gradlew test
```

Trên Windows dùng `.\gradlew.bat test`. Test đầu gọi qua **HTTP/filter chain thật** với MockMvc, quan sát status; test sau gọi **Spring-injected service**, kiểm tra trực tiếp `AccessDeniedException` thay vì chỉ mock logic. Nếu chỉ `new DocumentService()` rồi gọi phương thức, không có Spring AOP interceptor nên kết quả đó không chứng minh annotation có tác dụng.

Bài học từ test: với Alice đọc doc Bob, repository giả đã trả đối tượng **trước** khi `@PostAuthorize` từ chối. Controller không nhận giá trị; nhưng bản thân một thao tác đọc đã diễn ra. Đây chính là lý do cần cân nhắc bảo vệ dữ liệu sớm hơn trong ứng dụng thật.

## 6. Vì sao không nên dùng `@PostAuthorize` để “bảo vệ” thao tác ghi?

Xem phản ví dụ sau, **chỉ để phân tích rủi ro, không phải class runnable**:

```java
// Thiết kế không nên dùng:
@PostAuthorize("returnObject.owner == authentication.name")
public Invoice approveAndReturnInvoice(long invoiceId) {
    Invoice invoice = repository.load(invoiceId);
    invoice.setStatus(APPROVED);
    repository.save(invoice);       // Có thể đã ghi DB.
    eventPublisher.publish(invoice); // Có thể đã phát event.
    return invoice;
}
```

Giả sử caller không phải owner. Hậu kiểm có thể từ chối **sau** khi đã gọi `save` và `publish`. Một `AccessDeniedException` không rút email đã gửi, event đã phát, request ngoài đã thực thi hoặc log đã ghi lại. Với transaction, thứ tự advice/commit/rollback phụ thuộc cấu hình AOP và transaction manager; **không nên dựa vào việc có `@Transactional` để coi đây là cơ chế ngăn side effect an toàn**.

Thiết kế phù hợp hơn: **đọc dữ liệu cần thiết → xác minh quyền trước khi thay đổi → thực hiện mutation có điều kiện và transaction**.

Ví dụ **skeleton nghiệp vụ, không độc lập chạy được**, sử dụng authorizer rõ ràng:

```java
@PreAuthorize("hasAuthority('INVOICE_APPROVE')")
@Transactional
public void approve(long id, Authentication authentication) {
    Invoice invoice = repository.findForUpdate(id)
        .orElseThrow(InvoiceNotFoundException::new);

    approvalPolicy.requireCanApprove(authentication, invoice);
    invoice.approve();

    // Nếu dùng SQL trực tiếp, WHERE nên có tenant/status/version.
    repository.save(invoice);
}
```

Cần kiểm tra race condition/TOCTOU: quyền, membership hoặc trạng thái có thể đổi giữa hai bước; dùng transaction/locking, optimistic version hoặc cập nhật có điều kiện để giữ bất biến. `@PreAuthorize` kiểm tra authority trước khi method vào, rồi policy dựa trên object được áp dụng **trước khi ghi**. Việc bảo đảm tính đúng đắn thuộc thiết kế transaction và database, không chỉ annotation.

**Quy tắc:** `@PostAuthorize` hợp lý nhất cho **read-only method** trả một object mà cần quyết định dựa trên thuộc tính mới biết sau khi truy vấn. Với write, command có side effect hoặc streaming, thiết kế authorization trước khi thực thi và/hoặc enforce bằng dữ liệu/transaction.

## 7. Phân quyền ở nguồn dữ liệu thường tốt hơn hậu kiểm

`@PostAuthorize` hữu ích để học khái niệm ownership hoặc bổ sung một tầng bảo vệ, nhưng nó có ba giới hạn đối với hệ thống có dữ liệu nhạy cảm:

1. **Đã đọc object không thuộc quyền:** dữ liệu có thể xuất hiện trong cache, trace, debugger, log hoặc được truyền qua thành phần khác trước khi hậu kiểm ngăn caller nhận kết quả.
2. **Rò rỉ sự tồn tại bản ghi:** query ID có object rồi hậu kiểm trả 403, trong khi ID không có trả 404. Sự khác biệt có thể hỗ trợ ID enumeration.
3. **Tốn I/O và khó mở rộng:** method đọc object đầy đủ trước khi đánh giá policy; các truy vấn phức tạp/list/pagination càng đắt.

Với ứng dụng nhiều tenant, thường ưu tiên truy vấn đã scope theo **tenant + owner/ACL** mà server xác thực, ví dụ:

```sql
SELECT id, tenant_id, owner_username, title
FROM documents
WHERE id = :id
  AND tenant_id = :authorizedTenant
  AND owner_username = :authenticatedUsername;
```

Các tham số phải được bind an toàn. `authorizedTenant` xuất phát từ tenant membership đã xác minh, không lấy thẳng từ header client. Nếu caller không có quyền xem bản ghi, truy vấn trả rỗng; API có thể trả 404 theo chính sách sản phẩm, đồng thời ghi audit thích hợp.

Cũng có thể cần chính sách “member trong một nhóm được đọc”, “document được share cho viewer”, “manager chỉ duyệt cùng tenant”. Khi đó owner check đơn giản không đủ: dùng policy service, ACL/ABAC/ReBAC phù hợp, và **đưa phần predicate có thể diễn đạt xuống query** để bảo vệ read/list/count/export.

Bảo vệ ở các tầng bổ sung cho nhau:

```text
HTTP authentication / coarse-grained route
    → @PreAuthorize: caller có quyền thực hiện read?
    → Query theo tenant/owner/ACL: caller có nhìn thấy record?
    → @PostAuthorize: hậu kiểm bất biến của object nếu còn cần
    → DTO/serialization: caller được xem trường nào?
```

`@PostAuthorize` vì vậy là **một lớp bảo vệ có điều kiện**, không phải thay thế cho truy vấn theo scope hoặc kiểm soát dữ liệu khi sửa/xóa.

## 8. Khi có `hasPermission` hoặc policy bean riêng

Ứng dụng phức tạp không nên nhồi toàn bộ logic vào một biểu thức SpEL khó kiểm thử:

```java
@PostAuthorize(
    "returnObject == null || " +
    "@documentPolicy.canRead(authentication, returnObject)"
)
public DocumentView findOne(long id) {
    return repository.findOne(id);
}
```

Đây là **mẫu gợi ý cấu trúc**, cần bean `documentPolicy` và method `canRead(Authentication, DocumentView)` do dự án viết. Tách policy thành Java method đem lại lợi ích: unit test độc lập, log/audit có thể giải thích lý do từ chối, dùng lại cho query predicate và action khác.

Có thể dùng cú pháp:

```java
@PostAuthorize("hasPermission(returnObject, 'read')")
```

Nhưng `hasPermission` phụ thuộc cơ chế `PermissionEvaluator` (hoặc tích hợp authorization) được cấu hình đúng cho domain của bạn. Nó **không tự đọc cột owner hay danh sách ACL**. Với kết quả nullable, loại đối tượng đặc biệt hoặc service chạy không có HTTP context, cần thiết kế cách diễn giải riêng và kiểm thử.

**Không gộp nhiều rule mơ hồ:** Nếu vừa có `@PreAuthorize` vừa có `@PostAuthorize`, mỗi annotation là một interceptor riêng và cả hai phải cho phép. Nếu có nhiều quyền liên quan, ưu tiên một policy dễ đọc thay cho chuỗi điều kiện phức tạp và sao chép trên nhiều class.

## 9. Cạm bẫy AOP/proxy: annotation có nhưng không chạy

Một lỗi thường gặp:

```java
@Service
class DocumentService {
    public DocumentView entry(long id) {
        return findById(id); // this.findById(): self-invocation
    }

    @PostAuthorize("returnObject.owner == authentication.name")
    public DocumentView findById(long id) {
        return repository.findById(id);
    }
}
```

Đây là **đoạn minh họa**, `repository` là field giả định. Khi `entry` gọi `findById` **trong cùng instance**, lời gọi có thể đi thẳng tới method mà không vòng qua Spring proxy; interceptor `@PostAuthorize` vì thế không chạy theo cơ chế Spring AOP proxy thông thường. Tương tự với đối tượng tạo bằng `new` ngoài container hoặc các method không proxy được theo kiểu proxy đang sử dụng.

Cách thiết kế sạch hơn là để caller gọi **một Spring-injected service bean**, tách các use case có bảo vệ thành bean độc lập nếu cần; test thật qua bean trong ApplicationContext. Đừng giải quyết bằng cách tự tạo proxy tùy tiện hoặc đẩy mọi policy ra controller.

Checklist chẩn đoán:

- `@EnableMethodSecurity` đã bật trên cấu hình phù hợp?
- Method nằm trên bean do Spring quản lý, không phải object tạo thủ công?
- Caller gọi qua proxy, không qua `this`?
- Method có modifier/kiểu bean tương thích với cơ chế proxy?
- Annotation gắn trên đúng method/class/interface theo cách Spring Security hỗ trợ?
- Authentication tồn tại trong luồng thực thi (HTTP, scheduled job, async, message consumer)?
- Test có kiểm chứng **một người bị từ chối** qua bean thật, thay vì chỉ test người được phép?
- Có dùng `@PreAuthorize`/`@PostAuthorize` trên method trả kết quả đúng kiểu mà expression mong đợi?

Method security không tự bảo vệ các method **không được annotate**. Vẫn cần chính sách HTTP catch-all và bảo vệ domain entrypoints quan trọng.

## 10. Lỗi đầu ra và mã HTTP: 403, 404 hay 401?

Trong ví dụ dùng HTTP Basic:

- Chưa xác thực gọi route yêu cầu `authenticated()`: thông thường **401** và challenge phù hợp.
- Đã xác thực, thiếu `DOC_READ`: bị `@PreAuthorize` từ chối, thông thường **403**.
- Đã xác thực, có `DOC_READ` nhưng kết quả thuộc user khác: bị `@PostAuthorize` từ chối, thông thường **403**.
- Có quyền, không có kết quả và expression cho null đi qua: controller có thể trả **404**.

Với form login/session, bearer JWT, custom authentication entry point hoặc exception handler, status/redirect/body có thể khác. Trong luồng **không phải HTTP** (job, consumer, direct service), `AccessDeniedException` không tự biến thành HTTP response: caller phải xử lý phù hợp, không nuốt lỗi rồi tiếp tục nghiệp vụ.

Nếu yêu cầu không tiết lộ tài nguyên tồn tại, có thể chọn trả **404 cho object nằm ngoài scope** ngay ở truy vấn. Đừng phân biệt 403/404 tùy tiện trên cùng policy khi điều đó cho phép suy đoán ID. Audit nội bộ cần lưu lý do chính xác, nhưng không nên gửi chi tiết quyền/secret qua lỗi public.

## 11. Reactive/WebFlux: nguyên tắc giống nhau, context khác nhau

Spring Security cũng hỗ trợ reactive method security, nhưng phải dùng cấu hình và semantics của WebFlux/Reactor:

- Servlet/MVC: `@EnableMethodSecurity`, Spring AOP method interceptor, thường sử dụng `SecurityContextHolder` trong imperative flow.
- WebFlux: `@EnableReactiveMethodSecurity` (với Spring Security 6 có thể dùng `useAuthorizationManager = true`), context gắn với Reactor subscription và `ReactiveSecurityContextHolder`.
- Method được bảo vệ trong reactive pipeline nên trả kiểu reactive phù hợp như `Mono<T>` hoặc `Flux<T>`; không lấy principal bằng `ThreadLocal` bất kỳ rồi kỳ vọng đúng qua async boundary.
- `@PostAuthorize` reactive có thể kiểm tra kết quả phát ra theo tích hợp framework, nhưng chi tiết xử lý empty publisher, nhiều phần tử, cancellation và lỗi phải đối chiếu đúng phiên bản Spring Security và được kiểm thử bằng `WebTestClient`/reactive tests.
- Non-blocking **không thay đổi** vấn đề hậu kiểm: việc đọc/streaming/chạy tác vụ và side effect có thể đã bắt đầu trước khi policy đánh giá; ưu tiên lọc scope tại reactive repository hoặc trước khi phát stream.

Ví dụ cấu hình ý tưởng (không phải một chương trình chạy độc lập):

```java
@Configuration
@EnableReactiveMethodSecurity(useAuthorizationManager = true)
class ReactiveMethodSecurityConfig {
}
```

Không trộn `SecurityFilterChain` Servlet với `SecurityWebFilterChain` reactive hoặc `@EnableMethodSecurity` imperative với phiên bản reactive mà chưa xác minh web stack đang chạy. Cùng một biểu thức ownership cần test riêng trên `Mono.empty()`, `Mono.just(value)` và dữ liệu của user khác nếu áp dụng trong reactive service.

## 12. Tình huống thực tế: nên dùng hay tránh `@PostAuthorize`?

| Tình huống | Có hợp lý dùng `@PostAuthorize`? | Giải thích |
|---|---|---|
| Read một đối tượng đã load, chỉ owner được xem | Có thể hữu ích | Kiểm tra kết quả sau read; cân nhắc query scope để tránh đọc ngoài quyền |
| Read dữ liệu có owner/tenant và nhiều luật chia sẻ | Có thể là lớp bổ sung | Nên có policy bean và predicate ở DB |
| Tìm kiếm 100.000 tài liệu trả List | Không nên coi là cơ chế lọc chính | Hậu lọc có chi phí lớn và không an toàn cho pagination/count |
| `approvePayment` thay đổi số dư | Không làm kiểm soát duy nhất | Mutation có thể đã hoàn tất khi hậu kiểm từ chối |
| Gửi email hoặc publish event | Tránh kiểm tra quyền ở cuối | Side effect ngoài transaction không thể thu hồi bằng exception |
| Trả `ResponseEntity<DocumentView>` từ controller | Cần thận trọng | `returnObject` là wrapper, không mặc nhiên là DTO bên trong |
| Service có nhiều caller (HTTP, job, listener) | Method security hữu ích | Nhưng mỗi caller cần danh tính và context rõ ràng |
| Đọc JPA entity với lazy property | Cần test transaction/persistence context | SpEL có thể kích hoạt truy vấn hoặc gặp lỗi lazy loading |
| Dữ liệu đa tenant | Không đủ nếu chỉ check owner | Tenant membership, ACL, field-level và query scope là thiết yếu |
| Reactive `Mono<DocumentView>` | Có thể dùng với reactive method security | Kiểm thử semantics và context đúng version |

**Khi nên dùng:** một read-only use case có kết quả nhỏ, owner/permission chỉ xác định sau khi load, và cần một hậu kiểm rõ ràng được tích hợp với method security. **Khi nên tránh:** command ghi dữ liệu, thao tác có side effect, danh sách lớn hoặc dữ liệu cần hạn chế từ chính truy vấn.

## 13. Các lỗi thường gặp khi viết biểu thức

| Lỗi | Hệ quả | Cách sửa |
|---|---|---|
| Không bật `@EnableMethodSecurity` | Annotation có thể không thực thi | Bật cấu hình, test âm tính qua Spring bean |
| Đặt chỉ `@PostAuthorize` cho write method | Side effect có thể xảy ra trước khi denial | Authorize trước mutation, bảo vệ transaction |
| `returnObject.owner` khi return null | Có thể lỗi evaluation | Kiểm tra null rõ ràng, định nghĩa 404/403 |
| So `returnObject.owner` với giá trị user nhập trong body | Tin dữ liệu chưa xác thực | So với `authentication.name` hoặc identity đã kiểm chứng |
| Trả `Optional/ResponseEntity` nhưng kiểm tra như domain object | Sai kiểu property, deny ngoài ý muốn | Dùng DTO trực tiếp hoặc xử lý wrapper rõ ràng |
| Dùng `hasRole('DOC_READ')` trong khi authority là `DOC_READ` | `hasRole` mặc định chờ `ROLE_DOC_READ` | Dùng `hasAuthority('DOC_READ')` khi định danh là authority |
| Đánh đồng hậu kiểm với SQL filter | DB đã đọc đối tượng ngoài scope | Predicate scope trong DB, hậu kiểm bổ sung |
| Đánh đồng 403 với mọi trường hợp access denied | Authentication/entry point tùy cấu hình | Test 401/403/404 theo flow thực tế |
| Self-invocation trong service | Có thể bỏ qua proxy/interceptor | Gọi qua Spring bean/proxy, tách service |
| Lọc list bằng hậu kiểm object đơn | Không kiểm tra phần tử hoặc tốn bộ nhớ | Query scoped và pagination đúng |
| Áp dụng SpEL phức tạp nhiều nơi | Drift policy, khó audit/test | Dùng bean authorizer có API rõ ràng |
| Không test sau đổi DTO | Property trong SpEL có thể đổi/mất | Regression test cả allow và deny |

## 14. Checklist code review và bài tập tự kiểm tra

### Checklist

- [ ] Phân biệt quyền hành động trước khi method chạy và quyền trên object sau khi method trả kết quả.
- [ ] `@EnableMethodSecurity` đã bật; method được gọi qua Spring-managed proxy.
- [ ] `returnObject` đúng kiểu trả về thực tế; xử lý null/Optional/wrapper có chủ đích.
- [ ] SpEL property có thể truy cập và không gây query lazy ngoài ý muốn.
- [ ] Biểu thức dùng principal/tenant đáng tin; không lấy thông tin quyền từ input tự khai.
- [ ] Không dựa vào `@PostAuthorize` làm cổng duy nhất trước mutation, publish event hay I/O có side effect.
- [ ] Nếu cần ngăn đọc dữ liệu ngoài phạm vi, query có tenant/owner/ACL predicate.
- [ ] Test riêng: anonymous 401, thiếu quyền 403, sai owner 403/404 theo policy, đúng owner 200, không tồn tại 404.
- [ ] Test trực tiếp qua Spring-injected service, không chỉ mock controller.
- [ ] Đã xét 403 vs 404, danh sách lớn, field-level và cache/logging.
- [ ] Với reactive, đã xác nhận Reactor Context, kiểu Publisher và test đúng version.

### Bài tập

1. Trong ví dụ, Alice có `DOC_READ` và đọc `id=2`. **Method có chạy không?** Có: `@PreAuthorize` cho phép, `findById` tạo `DocumentView(owner="bob")`, rồi `@PostAuthorize` từ chối.
2. Viewer đọc `id=1`. **Method có chạy không?** Không: thiếu `DOC_READ` nên bị `@PreAuthorize` chặn trước.
3. Alice đọc `id=99`. **Vì sao được 404?** `findById` trả null, expression cho null đi tiếp, controller chuyển thành `notFound()`. Nếu bỏ nhánh null, hành vi có thể khác và cần test.
4. Đổi `@PostAuthorize` sang `@PreAuthorize("returnObject.owner == authentication.name")` có đúng không? Không: ở thời điểm **trước** method chưa có object kết quả này để đánh giá.
5. Nếu muốn trả 404 cho cả tài liệu không tồn tại và tài liệu không thuộc Alice, nên thiết kế ở đâu? Ưu tiên truy vấn **đã giới hạn scope**, để cả hai trả rỗng; không chỉ đổi text lỗi sau hậu kiểm.
6. Nếu gọi `this.findById(2)` từ method khác trong cùng bean, annotation còn bảo vệ chắc chắn không? Không thể dựa vào điều đó với Spring proxy mặc định; cần refactor lời gọi qua bean và test.
7. Nếu người dùng có quyền đọc nhưng tài liệu chứa trường bí mật, `@PostAuthorize` có tự cắt trường bí mật không? Không. Cần projection/DTO hoặc field-level authorization riêng.

## 15. Tài liệu chính thức

- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, `@PostAuthorize`, `returnObject`, proxy và cách các interceptor chạy trước/sau method.
- [Spring Security — Authorizing HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): bảo vệ route ở tầng HTTP để bổ sung cho method security.
- [Spring Security — Method Security Test](https://docs.spring.io/spring-security/reference/servlet/test/method.html): `@WithMockUser` và kiểm thử method authorization.
- [Spring Security — MockMvc Support](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html): kiểm tra response 401/403/200 khi gọi endpoint thực.
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html): bảo mật method dựa trên Reactor Context.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): giới hạn self-invocation và các cách AOP proxy hoạt động.

Bài mẫu dùng Spring Boot 3.x / Spring Security 6.x, Java 17+. Kiểm tra dependency/API theo phiên bản ứng dụng thật và thay mật khẩu demo bằng cơ chế quản trị credential đúng chuẩn.
