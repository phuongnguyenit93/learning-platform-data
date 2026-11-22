# Kiểm tra quyền ở máy chủ trên từng yêu cầu và thao tác nhạy cảm

> **Nguyên tắc:** Mỗi lần người dùng hoặc hệ thống yêu cầu **đọc, thay đổi, xuất hoặc quản lý tài nguyên**, máy chủ phải xác định chủ thể thực sự là ai và chủ thể đó **có được thực hiện hành động cụ thể trên đối tượng cụ thể, trong trạng thái hiện tại hay không**. Nút bấm bị ẩn trên giao diện, route của SPA được bảo vệ, hoặc client nói “tôi là admin” đều không thay thế được quyết định phân quyền ở server.

Bài học thuộc nhóm **Tư duy bảo mật** của Spring Security. Ví dụ minh họa dành cho ứng dụng Spring MVC/Servlet, sử dụng Java 17+ và Spring Security; các nguyên tắc thiết kế quyền vẫn áp dụng cho API, batch, message consumer và các giao thức khác.

## 1. Kết quả cần đạt

Sau khi học, bạn có thể:

1. Giải thích vì sao **authentication** (xác thực) khác **authorization** (phân quyền), và vì sao chỉ kiểm tra vai trò ở URL chưa đủ.
2. Lập chính sách kiểm tra quyền cho **mọi request** và từng thao tác như xem, sửa, duyệt, xuất dữ liệu, chuyển trạng thái và thay đổi quyền người khác.
3. Đặt kiểm tra hợp lý ở request filter, service và nơi truy cập dữ liệu; xử lý đối tượng thuộc chủ sở hữu/tenant khác.
4. Dùng `SecurityFilterChain` và method security của Spring Security để thực thi một phần chính sách.
5. Kiểm thử cả tình huống được phép và **phải từ chối**, kể cả đổi ID, đổi HTTP method, gửi thiếu CSRF token, gọi lặp hoặc gọi đồng thời.

## 2. Vì sao kiểm tra ở frontend không có giá trị như một ranh giới bảo mật?

Giả sử giao diện chỉ hiển thị nút “Duyệt chứng từ” nếu `isManager === true`. Một người có thể không cần nhấn nút này: họ gọi trực tiếp `POST /api/invoices/42/approve` bằng curl, Postman, script hoặc sửa request trong DevTools. Tương tự, người dùng đã đăng nhập có thể đổi `/documents/10` thành `/documents/20`.

**Bất kỳ dữ liệu nào do client kiểm soát đều không được xem là bằng chứng cấp quyền**, bao gồm:

- ID tài nguyên, `ownerId`, `tenantId`, `userId`, tham số `role`, trường `isAdmin`, quyền được mã hóa trong JSON, ID nằm trong route.
- Header tự khai như `X-User-Id`, `X-Tenant` hay `X-Role` nếu đường vào Internet có thể đặt hoặc sửa header đó.
- Việc frontend ẩn menu, khoá nút, chặn navigation hay kiểm tra “đang đăng nhập” trong local storage.
- Token có vẻ là JWT nhưng máy chủ chưa xác thực đúng chữ ký, issuer, audience, thời hạn và loại token theo hợp đồng tin cậy.

Frontend vẫn cần kiểm tra để có trải nghiệm tốt và ngăn thao tác nhầm. Nhưng **máy chủ quyết định**, dựa trên identity/claim đã được kiểm chứng, chính sách nghiệp vụ và trạng thái dữ liệu đáng tin cậy.

```text
Client                  Spring Security                 Domain/service
  | POST /documents/10/publish      |                            |
  |-------------------------------->|                            |
  |                                  | authenticate credential    |
  |                                  | authorize HTTP action      |
  |                                  |--------------------------->|
  |                                  |     check document owner   |
  |                                  |     check current state    |
  |                                  |     perform atomic update  |
  |                                  |<---------------------------|
  |<---------------------------------| result / reject            |
```

Quyết định cần được lặp ở **mỗi request**; request đã qua trước đó không tạo một “giấy phép vĩnh viễn” cho request tiếp theo. Với phiên/credential còn hiệu lực, thông tin quyền có thể bị cache và thay đổi theo chính sách, nhưng hệ thống phải định nghĩa rõ cách xử lý khi quyền bị thu hồi và cửa sổ hiệu lực của token.

## 3. Chính sách đầy đủ: ai, làm gì, trên cái gì, trong điều kiện nào?

Mô hình dễ dùng nhất cho review nghiệp vụ là:

```text
Decision = allow(
  actor       = danh tính đã xác thực,
  action      = READ | EDIT | PUBLISH | EXPORT | DELETE | GRANT_PERMISSION,
  resource    = đối tượng và owner/tenant thật trong hệ thống,
  context     = trạng thái, mối quan hệ, thời hạn, yêu cầu xác thực bổ sung
)
```

| Thành phần | Ví dụ | Nguồn đáng tin cậy |
| --- | --- | --- |
| Actor | Alice, Bob, nhân viên phòng kế toán | `Authentication` từ security context, token đã kiểm chứng |
| Action | `DOCUMENT_READ`, `DOCUMENT_PUBLISH` | Tên thao tác thực sự mà endpoint/service thực hiện |
| Resource | Document 10 có `owner=alice` | Database/repository, không lấy nguyên owner từ request |
| Context | `status=DRAFT`, tenant, ngày hiệu lực | Trạng thái dữ liệu và chính sách server |

Ví dụ ma trận quyền:

| Chủ thể | Tài liệu | Hành động | Điều kiện | Kết quả |
| --- | --- | --- | --- | --- |
| Alice có `DOC_READ` | Của Alice | READ | Tài liệu còn tồn tại | Cho phép |
| Alice có `DOC_READ` | Của Bob | READ | Không cùng owner | Từ chối |
| Alice có `DOC_PUBLISH` | Của Alice | PUBLISH | Đang `DRAFT` | Cho phép |
| Alice có `DOC_PUBLISH` | Của Alice | PUBLISH | Đã `PUBLISHED` | Từ chối vì trạng thái |
| Bob chỉ có `DOC_READ` | Của Bob | PUBLISH | Thiếu quyền publish | Từ chối |
| Anonymous | Bất kỳ | READ/PUBLISH | Chưa xác thực | Từ chối |

**Phân biệt ba mức quyền:**

- **Chức năng (function-level):** người này có quyền gọi thao tác publish hay không?
- **Đối tượng (object-level):** người này có được publish **tài liệu số 10** hay không?
- **Trường dữ liệu (property/field-level):** người này có được sửa trường `ownerId`, `status`, `limit` hoặc xem cột chứa bí mật hay không?

Chỉ kiểm tra chức năng dễ dẫn tới **BFLA** (Broken Function Level Authorization) nếu endpoint quản trị bị mở; chỉ kiểm tra quyền đăng nhập và bỏ qua owner/tenant dẫn đến **BOLA/IDOR** (Broken Object Level Authorization). Dùng entity nhận thẳng request body làm dữ liệu cập nhật có thể dẫn đến **mass assignment/overposting**; ngay cả khi người dùng sửa được tài liệu của chính mình, họ cũng không đương nhiên có quyền sửa `status` hoặc `ownerId`.

## 4. Đặt kiểm tra quyền ở nhiều ranh giới

### 4.1. HTTP request: lọc thao tác được phép gọi

Định nghĩa đường dẫn và HTTP method theo nguyên tắc **deny by default**: những endpoint không khai báo rõ phải bị từ chối, đồng thời kiểm tra các method mới phát sinh. Ví dụ:

```java
// Minh họa một phần cấu hình; lớp ứng dụng đầy đủ có ở mục 6.
@Bean
SecurityFilterChain security(HttpSecurity http) throws Exception {
    return http.authorizeHttpRequests(auth -> auth
        .requestMatchers(HttpMethod.POST, "/api/documents/*/publish")
            .hasAuthority("DOC_PUBLISH")
        .requestMatchers(HttpMethod.GET, "/api/documents/*")
            .hasAuthority("DOC_READ")
        .anyRequest().denyAll()
    ).httpBasic(Customizer.withDefaults()).build();
}
```

Các rule của `authorizeHttpRequests` được xét **theo thứ tự**, rule khớp đầu tiên thắng. Vì vậy, đặt rule hẹp trước rule rộng. Với một ứng dụng có nhiều `SecurityFilterChain`, phải kiểm tra cả **chain nào được chọn** bởi `securityMatcher` và quy tắc bên trong mỗi chain; tránh để request đi ngoài mọi chain. Cấu hình quyền riêng cho URL phải tính cả dispatcher type, servlet path và endpoint không đi qua Spring MVC (nếu có).

Spring Security cung cấp `permitAll`, `authenticated`, `hasAuthority`, `hasRole`, `denyAll` cùng các `AuthorizationManager` tùy chỉnh. Role mặc định như `hasRole("ADMIN")` đối chiếu authority `ROLE_ADMIN`; nếu sử dụng permission dạng `DOC_PUBLISH`, dùng `hasAuthority("DOC_PUBLISH")` rõ ràng hơn.

**Giới hạn:** URL filter biết đường dẫn, method, authentication và dữ liệu request; nó không tự biết document 10 thuộc về Alice và đang `DRAFT`. Kiểm tra ở service/domain vẫn là bắt buộc.

### 4.2. Service/domain: quyền trên tài nguyên và chuyển trạng thái

Đặt rule ngay cạnh hành vi nghiệp vụ quan trọng để tất cả caller cùng chịu policy, không chỉ một controller:

- Trước khi **xem**: tài nguyên tồn tại? actor có thể xem trong tenant/owner này? response có chứa trường bí mật?
- Trước khi **cập nhật**: actor được sửa tài nguyên nào? field nào cho phép sửa? thay đổi có vi phạm bất biến nghiệp vụ?
- Trước khi **duyệt/publish/hoàn tiền/xóa/cấp quyền**: actor có quyền riêng cho action này? đã thỏa trạng thái tiền điều kiện? có cần người thứ hai phê duyệt hoặc xác thực lại?
- Với **list/search/export**: filter ngay tại query theo người dùng/tenant; không chỉ bảo vệ endpoint detail. Với batch operation, kiểm tra **từng item**, tránh trường hợp một ID sai kéo theo xuất dữ liệu khác.
- Với **thao tác nhạy cảm** như đổi MFA, tạo API key, tăng hạn mức, cấp role: xem xét step-up authentication, phân tách người tạo/người duyệt, giới hạn số lần thử, audit đầy đủ và quy trình khôi phục.

Trong Spring Security, `@EnableMethodSecurity` cho phép `@PreAuthorize` trên method. Đây là rào chắn hữu ích nhưng phải hiểu **proxy interception**: lời gọi từ bean khác vào public method thường được kiểm tra; gọi `this.publish(...)` từ cùng bean có thể bỏ qua interceptor. Phương thức không có annotation hoặc không đi qua proxy vẫn cần policy rõ ràng trong kiến trúc. Tránh đặt kiểm tra duy nhất ở controller khi nghiệp vụ còn được gọi từ message handler, scheduled job hay luồng nội bộ.

### 4.3. Data layer: lọc đúng owner/tenant, tránh kiểm tra rời rạc

Một query theo ID đơn thuần như `findById(id)` chưa đủ cho dữ liệu riêng tư. Với tài liệu của người dùng, cách an toàn hơn là truy vấn có scope:

```java
// Mã minh họa Spring Data; cần entity/repository thật mới biên dịch.
Optional<DocumentEntity> findByIdAndOwnerIdAndTenantId(
    Long id, Long ownerId, Long tenantId);
```

Đối với update trạng thái, cân nhắc **conditional update trong transaction** thay cho “SELECT để kiểm tra, chờ một lúc rồi UPDATE”:

```sql
-- Minh họa logic nghiệp vụ; tên bảng/cột cần khớp schema thật.
UPDATE document
SET status = 'PUBLISHED'
WHERE id = :id
  AND owner_id = :trustedActorId
  AND tenant_id = :trustedTenantId
  AND status = 'DRAFT';
```

Chỉ xem thao tác thành công nếu số dòng được cập nhật bằng **1**; bằng 0 nghĩa là không tồn tại, không đúng owner/tenant hoặc trạng thái không hợp lệ. Nếu nghiệp vụ cần phân biệt lỗi, làm điều đó mà không làm lộ sự tồn tại dữ liệu ngoài phạm vi. Với chuyển tiền, tồn kho, phê duyệt song song hoặc xử lý nhiều bảng, cần transaction, optimistic/pessimistic lock, idempotency và kiểm soát số lần xử lý phù hợp; annotation phân quyền đơn lẻ không giải quyết race condition.

## 5. Vì sao “mỗi request” còn bao gồm nhiều lối vào?

Một hệ thống có thể cung cấp cùng một nghiệp vụ qua:

- Web UI, REST endpoint và mobile API.
- Endpoint export, file download, preview, report, webhook.
- Scheduler, queue consumer, asynchronous job, workflow, listener hoặc lệnh quản trị.
- GraphQL mutation/resolver, WebSocket message, gRPC, service-to-service API.

HTTP `SecurityFilterChain` chỉ kiểm soát những request đi qua filter chain tương ứng. **Không** mặc nhiên áp dụng cùng URL rule cho message queue hay một service method được gọi nội bộ. Mỗi entrypoint phải xác thực nguồn gọi và chuyển actor/service identity đáng tin cậy đến **cùng policy nghiệp vụ**, đồng thời chỉ cấp privilege tối thiểu cho service account.

Đặc biệt, endpoint `GET /api/orders` có thể được kiểm tra đúng, nhưng một endpoint `GET /api/orders/export` mới thêm lại trả toàn bộ bảng nếu chỉ lọc theo HTTP role. Các đường phát sinh dữ liệu (download, export, search, log, cache) cũng là tài nguyên cần phân quyền.

## 6. Ví dụ Spring Boot có thể chạy: quyền đọc và quyền publish

Ta xây dựng một API nhỏ có hai tài liệu: ID 10 thuộc Alice, ID 20 thuộc Bob. Alice được đọc/publish tài liệu của mình; Bob chỉ có quyền đọc tài liệu của mình. Publisher không được chuyển tài liệu của người khác sang `PUBLISHED`. Request không có CSRF token cũng bị từ chối theo thiết lập mặc định khi dùng POST.

Ví dụ dùng **Java 17, Spring Boot 3.5.16 (Spring Security 6.x)** để minh họa API và cách test. Đây là bản 3.x đóng băng cho bài học; khi bắt đầu dự án production năm 2026, dùng dòng Spring Boot đang được hỗ trợ và áp dụng bản vá hiện hành.

### 6.1. Cấu trúc

```text
authorize-every-action/
├── pom.xml
└── src/
    ├── main/java/demo/authorization/AuthorizationApplication.java
    └── test/java/demo/authorization/AuthorizationApplicationTests.java
```

```xml
<!-- pom.xml -->
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>authorize-every-action</artifactId>
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
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### 6.2. Ứng dụng và chính sách

Tạo file `src/main/java/demo/authorization/AuthorizationApplication.java`:

```java
package demo.authorization;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

import jakarta.servlet.DispatcherType;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
@EnableMethodSecurity
public class AuthorizationApplication {

    public static void main(String[] args) {
        SpringApplication.run(AuthorizationApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                // Cho phép container render lỗi 404/409 bằng ERROR dispatch.
                // Không mở quyền cho request trực tiếp từ client.
                .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
                .requestMatchers(HttpMethod.POST, "/api/documents/*/publish")
                    .hasAuthority("DOC_PUBLISH")
                .requestMatchers(HttpMethod.GET, "/api/documents/*")
                    .hasAuthority("DOC_READ")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            // CSRF vẫn bật theo mặc định, kể cả với POST ở ví dụ này.
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("demo-pass"))
                .authorities("DOC_READ", "DOC_PUBLISH")
                .build(),
            User.withUsername("bob")
                .password(encoder.encode("demo-pass"))
                .authorities("DOC_READ")
                .build()
        );
    }
}

@RestController
@RequestMapping("/api/documents")
class DocumentController {
    private final DocumentService service;

    DocumentController(DocumentService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    DocumentView read(@PathVariable long id) {
        return service.read(id);
    }

    @PostMapping("/{id}/publish")
    DocumentView publish(@PathVariable long id) {
        return service.publish(id);
    }
}

@Service
class DocumentService {
    private final ConcurrentMap<Long, Document> documents =
        new ConcurrentHashMap<>(Map.of(
            10L, new Document(10L, "alice", "Alice draft", State.DRAFT),
            20L, new Document(20L, "bob", "Bob draft", State.DRAFT)
        ));

    @PreAuthorize("hasAuthority('DOC_READ')")
    public DocumentView read(long id) {
        return toView(ownedDocument(id));
    }

    @PreAuthorize("hasAuthority('DOC_PUBLISH')")
    public synchronized DocumentView publish(long id) {
        // Demo in-memory: cùng một lock bảo vệ kiểm tra + cập nhật.
        Document doc = ownedDocument(id);
        if (doc.state() != State.DRAFT) {
            throw new ResponseStatusException(HttpStatus.CONFLICT);
        }

        Document published = new Document(
            doc.id(), doc.owner(), doc.title(), State.PUBLISHED);
        documents.put(id, published);
        return toView(published);
    }

    private Document ownedDocument(long id) {
        Authentication auth =
            SecurityContextHolder.getContext().getAuthentication();
        if (auth == null || !auth.isAuthenticated()) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED);
        }

        Document doc = documents.get(id);
        // Cùng một phản hồi cho "không có" và "không sở hữu".
        if (doc == null || !doc.owner().equals(auth.getName())) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        }
        return doc;
    }

    private static DocumentView toView(Document doc) {
        // Không expose owner hay entity nội bộ một cách mặc định.
        return new DocumentView(
            doc.id(), doc.title(), doc.state().name());
    }
}

enum State {
    DRAFT, PUBLISHED
}

record Document(long id, String owner, String title, State state) {}

record DocumentView(long id, String title, String status) {}
```

**Giải thích từng ranh giới:**

1. **Request authorization:** URL và HTTP method phải có permission tương ứng; mọi đường khác bị `denyAll`. Không có tình huống `GET` được phép thì mặc nhiên `POST` cũng được phép.
2. **Method authorization:** `@PreAuthorize` giữ lại một kiểm tra nếu logic service được gọi từ bean khác. `@EnableMethodSecurity` bắt buộc để annotation hoạt động trong cấu hình này.
3. **Object authorization:** `ownedDocument(id)` so sánh owner từ kho dữ liệu với username ở `SecurityContextHolder`; server **không lấy owner từ request body/query**. Alice có `DOC_PUBLISH` vẫn không publish tài liệu của Bob.
4. **State authorization:** được phép publish không có nghĩa được publish lặp; chỉ `DRAFT` mới chuyển sang `PUBLISHED`.
5. **Data minimization:** response chỉ gồm `id/title/status`; không serialize trực tiếp toàn bộ entity có thể chứa dữ liệu nội bộ.
6. **Concurrency:** `synchronized` giữ kiểm tra trạng thái và cập nhật cùng một critical section **trong một JVM demo**. Ứng dụng thật có nhiều instance và database phải dùng transaction + ràng buộc cập nhật có điều kiện/locking; `synchronized` không bảo vệ giữa các node.
7. **CSRF:** vì POST dùng cơ chế HTTP Basic có thể được trình duyệt tự gửi lại credential, ví dụ giữ CSRF bảo vệ theo cấu hình Servlet mặc định. Nếu triển khai API Bearer token thực sự không dựa vào cookie/credential tự gửi, đánh giá threat model và cấu hình phù hợp; không dùng `csrf.disable()` như thói quen.
8. **Tài khoản mẫu:** `InMemoryUserDetailsManager` và mật khẩu `demo-pass` chỉ phục vụ test local. Production cần hệ thống identity thật, HTTPS, chính sách mật khẩu/MFA và quyền gán từ nguồn tin cậy.

Một ghi chú về `404`: ở ví dụ này, response cho “ID không tồn tại” và “không phải chủ sở hữu” là giống nhau để tránh tiết lộ existence. Trong sản phẩm, cần cân nhắc quy ước `403`/`404`, logging nội bộ và trải nghiệm người dùng; quan trọng là không lộ dữ liệu.

### 6.3. Kiểm thử mọi nhánh được phép và bị từ chối

Tạo file `src/test/java/demo/authorization/AuthorizationApplicationTests.java`:

```java
package demo.authorization;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.RequestPostProcessor;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AuthorizationApplicationTests {

    @Autowired
    MockMvc mvc;

    private static RequestPostProcessor alice() {
        return user("alice").authorities(
            new SimpleGrantedAuthority("DOC_READ"),
            new SimpleGrantedAuthority("DOC_PUBLISH")
        );
    }

    private static RequestPostProcessor bob() {
        return user("bob").authorities(
            new SimpleGrantedAuthority("DOC_READ")
        );
    }

    @Test
    void everyRequestAndSensitiveActionIsChecked() throws Exception {
        // 1. Không đăng nhập -> HTTP Basic trả 401.
        mvc.perform(get("/api/documents/10"))
            .andExpect(status().isUnauthorized());

        // 2. Alice đọc đúng tài liệu mình sở hữu.
        mvc.perform(get("/api/documents/10").with(alice()))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.title").value("Alice draft"));

        // 3. Alice đổi ID sang tài liệu Bob -> không được.
        mvc.perform(get("/api/documents/20").with(alice()))
            .andExpect(status().isNotFound());

        // 4. Gửi POST mà không có CSRF token -> 403.
        mvc.perform(post("/api/documents/10/publish").with(alice()))
            .andExpect(status().isForbidden());

        // 5. Bob là owner của 20 nhưng thiếu DOC_PUBLISH -> 403.
        mvc.perform(post("/api/documents/20/publish")
                .with(bob()).with(csrf()))
            .andExpect(status().isForbidden());

        // 6. Alice có quyền publish nhưng tài liệu 20 của Bob -> 404.
        mvc.perform(post("/api/documents/20/publish")
                .with(alice()).with(csrf()))
            .andExpect(status().isNotFound());

        // 7. Alice publish tài liệu 10 ở trạng thái DRAFT -> 200.
        mvc.perform(post("/api/documents/10/publish")
                .with(alice()).with(csrf()))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("PUBLISHED"));

        // 8. Gọi lại cùng hành động ở trạng thái PUBLISHED -> 409.
        mvc.perform(post("/api/documents/10/publish")
                .with(alice()).with(csrf()))
            .andExpect(status().isConflict());

        // 9. Đường dẫn không khai báo, dù đã đăng nhập -> 403.
        mvc.perform(get("/api/unknown").with(alice()))
            .andExpect(status().isForbidden());
    }
}
```

Trong thư mục dự án, chạy với **JDK 17+ và Maven 3.6.3+**:

```bash
mvn test
mvn spring-boot:run
```

`mvn test` chạy một integration test gồm chín tình huống; khi tất cả đáp ứng hợp đồng phía trên, Maven báo build thành công. Bài học không dựa vào việc đoán số lượng log hoặc in ra stdout từ server.

Khi chạy server local, `GET` bằng Basic Auth có thể kiểm tra bằng:

```bash
curl -i http://localhost:8080/api/documents/10
curl -i -u alice:demo-pass http://localhost:8080/api/documents/10
curl -i -u alice:demo-pass http://localhost:8080/api/documents/20
```

Với `POST`, đừng bỏ qua CSRF để làm cho curl “dễ thành công”; dùng test `MockMvc` có `csrf()` ở trên. Nếu muốn gửi POST bằng trình duyệt/curl, cần cấp token phù hợp với session/cấu hình CSRF và gửi cả token lẫn credential tương ứng. Tất cả Basic credential trong production phải đi trên HTTPS.

**Lưu ý kiểm thử:** `user(...)` trong `spring-security-test` tạo principal giả lập cho request; nó kiểm tra authorization, **không kiểm thử đường xác thực password/token thật**. Hãy có test riêng cho login, chữ ký và claim của token khi sản phẩm dùng các cơ chế đó. Với dữ liệu `ConcurrentHashMap`, một test duy nhất chạy các bước trạng thái theo thứ tự; production test phải có database fixture độc lập giữa các test.

## 7. Chặn lỗi ở những thao tác nhạy cảm hơn publish

### 7.1. Phê duyệt, hoàn tiền, chuyển tiền, thanh toán

Các thao tác này không chỉ kiểm tra role mà còn **giới hạn số tiền, trạng thái, owner/tenant, người phê duyệt, số lần lặp**. Ví dụ chính sách duyệt hoàn tiền:

- `REFUND_REQUEST` cho phép tạo yêu cầu hoàn tiền, giới hạn theo chủ sở hữu order.
- `REFUND_APPROVE` cho phép phê duyệt trong ngưỡng số tiền và bộ phận được giao.
- Người tạo yêu cầu không được tự duyệt nếu bắt buộc phân tách nhiệm vụ.
- Trong transaction, kiểm tra order/payment còn đủ điều kiện và chuyển trạng thái một lần.
- Dùng idempotency key để request bị retry không hoàn tiền hai lần.
- Ghi audit ai, lúc nào, thao tác gì, đối tượng nào, kết quả; tránh ghi số thẻ đầy đủ, mật khẩu hoặc bearer token.

Thao tác “có quyền duyệt” chỉ là **một điều kiện**. Những quy tắc “đang chờ duyệt”, “chưa hoàn tiền”, “không tự duyệt” và “trong hạn mức” cũng phải được máy chủ thực thi.

### 7.2. Gán role, chuyển owner và thay đổi chính sách

Không cho phép cập nhật trực tiếp các trường nhạy cảm từ DTO chung như:

```json
{
  "displayName": "Alice",
  "role": "ADMIN",
  "ownerId": "bob",
  "tenantId": "finance"
}
```

Nếu endpoint `PUT /users/me` nhận `UserEntity` trực tiếp rồi lưu tất cả field, client có thể thử leo thang quyền. Hướng thiết kế:

- Định nghĩa DTO tách biệt cho từng tác vụ; `UpdateProfileRequest` chỉ có trường người dùng được sửa.
- Viết endpoint riêng cho thay đổi role, owner, giới hạn hoặc chính sách; yêu cầu permission chuyên biệt, điều kiện nghiệp vụ, audit và khi cần thì xác thực lại.
- Tại service, đối chiếu actor với mục tiêu và phân cấp role; không cho người có quyền yếu cấp quyền mạnh hơn.
- Quyền và danh tính phải lấy từ dữ liệu/server đã xác minh; không tin giá trị `role`, `isAdmin` hoặc `actorId` gửi lên.

### 7.3. Export, list và các tác vụ chạy nền

Một endpoint export có thể hợp lệ về chức năng nhưng vẫn rò rỉ cả bảng. Lọc dữ liệu ngay tại query theo owner/tenant/allowed scope, giới hạn số dòng và cột được phép xuất, kiểm soát thời hạn link tải xuống. Với job bất đồng bộ, cần lưu scope đã kiểm chứng, xác định khi nào kiểm tra lại quyền (lúc enqueue, lúc execute, lúc download) theo yêu cầu nghiệp vụ. Không sao chép nguyên authentication của browser vào background job mà không xét thời hạn và ranh giới tin cậy.

## 8. Các lỗi thường gặp khi thiết kế quyền

### Lỗi 1 — Chỉ bảo vệ giao diện

**Dấu hiệu:** menu admin bị ẩn nhưng `POST /api/admin/users/1/role` vẫn truy cập được khi biết URL.

**Cách sửa:** kiểm tra quyền ở server cho endpoint và service; test request trực tiếp không qua frontend.

### Lỗi 2 — Chỉ gọi `authenticated()`

**Dấu hiệu:** Alice đăng nhập rồi tải được tài liệu của Bob bằng cách thay số ID.

**Cách sửa:** kiểm tra actor + action + resource; lọc owner/tenant từ cơ sở dữ liệu và không đưa thông tin ngoài phạm vi vào response.

### Lỗi 3 — Chỉ kiểm tra quyền lúc đầu luồng

**Dấu hiệu:** quyền đã bị rút nhưng link tải đã cấp hoặc job chạy sau đó vẫn dùng quyền cũ mãi.

**Cách sửa:** xác định policy về session/token TTL, revocation, quyền ngắn hạn và điểm kiểm tra lại trước tác vụ nhạy cảm. Không mặc nhiên coi một bước UI xác minh trước đó là quyền cho mọi bước sau.

### Lỗi 4 — Cho mọi method quyền như nhau

**Dấu hiệu:** `GET /api/documents/10` được phép nên `POST /api/documents/10/publish` hoặc `DELETE /api/documents/10` cũng lọt qua wildcard quá rộng.

**Cách sửa:** phân quyền theo HTTP method và path/action cụ thể; sắp xếp matcher hẹp trước, `denyAll` cho đường không rõ. Không dùng GET để thực hiện thay đổi trạng thái.

### Lỗi 5 — Dựa vào check ở service nhưng gọi vòng qua proxy

**Dấu hiệu:** `@PreAuthorize` có trên method nhưng code trong cùng bean gọi `this.method()`, hoặc chỉ có annotation mà quên `@EnableMethodSecurity`.

**Cách sửa:** đặt policy ở boundary service được gọi từ bean khác và test method interception thật; với bất biến nghiệp vụ, kiểm tra trực tiếp tại nơi cập nhật dữ liệu. Không coi annotation là lưới an toàn tự động cho mọi invocation.

### Lỗi 6 — Đọc quyền từ input chưa được chứng thực

**Dấu hiệu:** backend tin `X-User-Id` hoặc `role=ADMIN` trên request Internet, hoặc tin JWT mà không verify đầy đủ claim/chữ ký.

**Cách sửa:** chỉ lấy actor từ authentication đáng tin cậy; claim mapping và proxy/header trust boundary phải được cấu hình rõ ràng. Tuyệt đối không để frontend tự quyết định actor.

### Lỗi 7 — Check-then-act bị race condition

**Dấu hiệu:** hai request đều thấy `status=PENDING`, cùng duyệt hoặc cùng hoàn tiền.

**Cách sửa:** ràng buộc transaction và thao tác atomic/conditional update; dùng optimistic lock/row lock khi cần, bảo đảm idempotency ở nguồn ghi. Authorization có thể đúng nhưng xử lý trạng thái vẫn sai nếu tách check ra khỏi write.

### Lỗi 8 — Từ chối bằng HTTP code nhưng vẫn gây side effect

**Dấu hiệu:** service thực hiện cập nhật/đẩy message rồi mới gọi `@PostAuthorize` để quyết định có cho phép hay không.

**Cách sửa:** quyết định quyền và điều kiện **trước khi thực hiện side effect**. `@PostAuthorize` có thể hợp lý với một số trường hợp đọc dữ liệu nhưng không nên dùng làm cửa kiểm soát duy nhất cho mutation đã thực thi.

### Lỗi 9 — Không thống nhất ở hệ thống nhiều tenant

**Dấu hiệu:** màn detail lọc theo tenant nhưng list, export, cache, search index hoặc background consumer thì không.

**Cách sửa:** policy và tenant scope phải nhất quán trên tất cả đường truy cập và key cache; test chéo tenant với cùng ID hoặc ID đoán được.

## 9. Bộ test khuyến nghị trước khi phát hành

| Kịch bản | Điều cần chứng minh |
| --- | --- |
| Anonymous gọi endpoint private | Bị từ chối/challenge xác thực phù hợp |
| User đúng quyền, đúng owner | Cho phép và chỉ trả dữ liệu được phép |
| User đúng role nhưng khác owner/tenant | Không truy cập, không xác nhận tồn tại trái phép |
| User đúng owner nhưng thiếu quyền action | Không được publish/delete/export/cấp quyền |
| Đổi `GET` thành `POST`/`DELETE` | Không thừa kế quyền đọc |
| Gửi `role`/`ownerId` giả, mass assignment | Không leo thang quyền hay chuyển sở hữu |
| Gọi lại request sau khi state chuyển | Không thực hiện thao tác lần hai trái policy |
| Hai request đồng thời | Không xử lý trùng hoặc phá bất biến |
| Thiếu/sai CSRF token khi CSRF áp dụng | Bị từ chối trước mutation |
| Token hết hạn, sai issuer/audience | Không xác thực, không được cấp quyền |
| Quyền bị thu hồi | Thực hiện đúng SLA/policy thu hồi và cache |
| Không đi qua HTTP: job/queue/service call | Vẫn chịu policy tại boundary thích hợp |
| Export/list/download đa tenant | Không rò rỉ record hay field ngoài scope |
| Route mới không khai báo | Bị chặn bởi deny-by-default |
| Phát sinh lỗi | Không log secret/PII và không gây side effect trước deny |

Với request authorization dùng Spring Security Test + MockMvc; với method authorization kiểm thử qua bean/proxy thật; với owner/tenant dùng dataset có ít nhất hai chủ thể và hai tenant; với concurrency/transaction dùng database thật hoặc môi trường đủ gần production. Đối với quyết định nhạy cảm, test các nhánh **DENY** thường tìm ra lỗi quan trọng hơn chỉ test đường thành công.

## 10. Checklist áp dụng cho một endpoint mới

Trước khi merge code cho một endpoint hoặc mutation, tự kiểm tra:

1. **Ai gọi?** Authentication được thiết lập từ credential đã xác minh hay từ header/body client tự khai?
2. **Hành động gì?** GET/list/detail khác EDIT/PUBLISH/DELETE/EXPORT/GRANT_PERMISSION như thế nào?
3. **Trên dữ liệu nào?** Owner, tenant, ACL, project scope và trạng thái hiện tại lấy từ đâu?
4. **Ở đâu kiểm tra?** URL, service, query/update transaction, background worker và file download có cùng policy?
5. **Nếu có concurrency/retry?** Kiểm tra và cập nhật có atomic, có giới hạn idempotency và audit phù hợp không?
6. **Mặc định khi thiếu policy?** Request mới bị từ chối hay được thông qua?
7. **Có kiểm thử âm tính?** Có ít nhất ca anonymous, sai role, sai object, sai tenant, sai state, sai HTTP method và token/CSRF không?

Đối với tác vụ có rủi ro cao (hoàn tiền, thay đổi MFA, cấp quyền, khóa tài khoản, xóa dữ liệu), bổ sung đánh giá hạn mức, xác thực lại, hai người phê duyệt, quyền quản trị tối thiểu và khả năng phát hiện/khôi phục.

## 11. Ghi nhớ

- **Mọi request cần được xác thực và phân quyền theo chính sách của chính request đó.** Những request công khai phải được đánh dấu công khai có chủ đích.
- **Mọi thao tác nhạy cảm cần được kiểm tra tại nơi thực thi:** đủ permission, đúng owner/tenant, đúng trạng thái và điều kiện nghiệp vụ.
- **Đừng tin client khi client tự khai quyền.** Chỉ dùng danh tính/claim được server xác minh và dữ liệu resource đáng tin cậy.
- **Quyền gọi endpoint không đồng nghĩa quyền sở hữu đối tượng.** Cần lớp HTTP, lớp service/domain và ràng buộc dữ liệu hỗ trợ nhau.
- **Deny by default + least privilege + kiểm thử trường hợp bị từ chối** là bộ ba thực dụng để ngăn lộ dữ liệu và thực hiện trái phép.

## Tài liệu tham khảo

- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Security — Testing Method Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html)
- [OWASP API Security Top 10 — 2023](https://owasp.org/API-Security/editions/2023/en/0x11-t10/)
- [Spring Boot 3.5 System Requirements](https://docs.spring.io/spring-boot/3.5/system-requirements.html)
