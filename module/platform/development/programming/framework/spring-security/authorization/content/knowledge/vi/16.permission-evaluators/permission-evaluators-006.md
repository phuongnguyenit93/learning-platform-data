# Tách kiểm tra quyền khỏi việc tải và cập nhật tài nguyên với PermissionEvaluator

## 1. Bài toán: một phương thức đang gánh ba trách nhiệm

Giả sử hệ thống quản lý tài liệu có nghiệp vụ xem và chỉnh sửa một tài liệu thuộc một tenant. Cách viết dễ gặp:

```java
public void updateDocument(long id, String newContent) {
    Document document = repository.findById(id).orElseThrow();
    if (!currentUserCanEdit(document)) {
        throw new AccessDeniedException("Denied");
    }
    document.setContent(newContent);
    repository.save(document);
}
```

Đây chỉ là đoạn minh họa; các kiểu và dependency do ứng dụng định nghĩa. Mã này có thể chạy đúng trong một ứng dụng cụ thể, nhưng đang đan xen **tải dữ liệu**, **quyết định quyền** và **thay đổi dữ liệu**. Nếu nhiều service dùng cùng quyền, logic dễ bị sao chép; nếu chỉ kiểm tra sau khi tải cả nội dung nhạy cảm, ứng dụng có thể đã làm một lượng công việc không cần thiết hoặc vô tình xử lý/log dữ liệu trước khi kiểm tra quyền.

Spring Security cho phép tách ba trách nhiệm:

1. **Authorization:** trả lời “caller có quyền *read/write* trên resource ID này không?”. `PermissionEvaluator` giúp biểu thức `hasPermission(...)` đưa ra quyết định boolean.
2. **Resource loading:** repository/service lấy tài liệu và dữ liệu nghiệp vụ cần thiết.
3. **Mutation:** service áp dụng luật nghiệp vụ, transaction, kiểm tra phiên bản và lưu thay đổi.

Cần phân biệt tinh tế: để quyết định permission theo object, evaluator **có thể phải đọc một lượng dữ liệu tối thiểu từ nguồn đáng tin cậy**, ví dụ owner/tenant/state/ACL. “Tách khỏi việc tải tài nguyên” **không đồng nghĩa “permission check không được đọc database”**. Nghĩa đúng là **không tải toàn bộ nội dung không cần thiết, không tạo side effect và không coi evaluator là nơi thực hiện nghiệp vụ đọc/ghi**.

Ví dụ mục tiêu:

```text
Caller
  |
  v
Spring AOP proxy / @PreAuthorize
  |
  v
PermissionEvaluator.hasPermission(auth, documentId, "Document", "read")
  |       \
  |        -> truy vấn metadata quyền: tenant, owner, status
  v
GRANT hoặc DENY
  |
  +-- DENY  -> service method không được gọi
  |
  +-- GRANT -> DocumentService.read(id)
                  |
                  v
             Repository tải nội dung
                  |
                  v
             Kiểm tra lại dữ liệu nhạy cảm nếu cần
                  |
                  v
             Trả dữ liệu đã được phép
```

Với thao tác **ghi**, một kiểm tra trước method thường là **điều kiện cần, chưa đủ**. Nếu owner/tenant/trạng thái đổi giữa kiểm tra và cập nhật, cần thêm cơ chế nhất quán bên trong transaction.

## 2. Vai trò của PermissionEvaluator trong Spring Security

`PermissionEvaluator` là chiến lược đánh giá quyền trên domain object; Spring Security sử dụng nó khi biểu thức method security gọi `hasPermission`. Hai overload:

```java
boolean hasPermission(
        Authentication authentication,
        Object targetDomainObject,
        Object permission);

boolean hasPermission(
        Authentication authentication,
        Serializable targetId,
        String targetType,
        Object permission);
```

Các tham số:

| Tham số | Ý nghĩa |
| --- | --- |
| `authentication` | Danh tính và authorities của caller đã được framework xác thực |
| `targetDomainObject` | Đối tượng domain **đã có sẵn** cho evaluation |
| `targetId` | ID có thể serialize, thường là `Long` hoặc `UUID` |
| `targetType` | Tên loại tài nguyên theo contract của ứng dụng, ví dụ `"Document"` |
| `permission` | Hành động cần kiểm tra, ví dụ `"read"`, `"write"` |
| Kết quả | `true` cho phép, `false` từ chối |

Hợp đồng chính thức cho phép `targetDomainObject == null` ở overload thứ nhất; implementation nên trả `false` cho trường hợp null.

Hai biểu thức khác nhau:

```java
// Đối số #p0 là long/Long: sử dụng overload ID + loại tài nguyên.
@PreAuthorize("hasPermission(#p0, 'Document', 'read')")
public String read(long documentId) { /* ... */ }

// Đối số #p0 là object Document đã được caller cung cấp.
@PreAuthorize("hasPermission(#p0, 'read')")
public void share(Document document) { /* ... */ }
```

**Điểm dễ nhầm:** `hasPermission(#p0, 'read')` với `#p0` là `Long` sẽ gọi overload nhận **Object**, không tự biết đó là ID của tài liệu. Nếu evaluator chỉ xử lý `Document` ở overload object, biểu thức đó bị từ chối. Chọn rõ dạng ID ba đối số cho service nhận ID.

`PermissionEvaluator` chỉ là một hook. Không có chuyện Spring tự biết bảng `documents`, bảng ACL hoặc chủ sở hữu. Người phát triển phải đăng ký evaluator và cài đặt chính sách. Nếu không, cách cấu hình mặc định thường không cung cấp quyết định quyền theo dữ liệu nghiệp vụ mong muốn.

### Phân biệt ba lớp

| Thành phần | Nên làm | Không nên làm |
| --- | --- | --- |
| `PermissionEvaluator` | Chuẩn hóa action/type/ID, gọi policy và trả boolean | Gọi `save`, xóa bản ghi, phát sự kiện nghiệp vụ |
| `DocumentAccessPolicy` | Mô tả quy tắc thuần: action, tenant, owner, state, authorities | Thực hiện controller response, mở HTTP session, mutate resource |
| `DocumentService` + repository | Tải dữ liệu, xác thực ràng buộc hiện hành, ghi trong transaction, xử lý lỗi | Tin tuyệt đối vào kết quả pre-check đã cũ, bỏ qua transaction |

Policy có thể tái sử dụng cả từ evaluator lẫn service. Như vậy ta tách được **vị trí quyết định quyền** khỏi **vị trí truy xuất và sửa dữ liệu**, mà không viết lại quy tắc owner/tenant nhiều lần.

## 3. Vì sao không tải và cập nhật tài nguyên ngay bên trong evaluator?

Một implementation không tốt:

```java
@Override
public boolean hasPermission(
        Authentication auth,
        Serializable targetId,
        String targetType,
        Object action) {

    Document doc = repository.findById((Long) targetId).orElseThrow();

    if ("write".equals(action) && isOwner(auth, doc)) {
        doc.setContent("updated"); // Sai: authorization đã làm mutation.
        repository.save(doc);
        return true;
    }
    return false;
}
```

Đây là **phản ví dụ không dùng production**. Các vấn đề:

- Một biểu thức chỉ hỏi “có quyền không” lại **thay đổi dữ liệu**, vi phạm trách nhiệm của authorization.
- Evaluator có thể được gọi nhiều lần trên mỗi request hoặc bởi advice khác; mutation có thể chạy lặp, sai tính idempotent.
- Transaction tại thời điểm evaluator chạy có thể **không phải** transaction nghiệp vụ mong muốn. Mặc định `@PreAuthorize` đánh giá trước khi vào thân method; không được mặc nhiên tin đang có transaction của `@Transactional` trên method đích.
- Nếu method đích bị từ chối bởi kiểm tra khác, hay sau đó lỗi, dữ liệu từ evaluator có thể đã thay đổi ngoài ý muốn.
- Quyền của caller có thể bị lẫn với dữ liệu do client cung cấp; khi dùng object overload, đối tượng truyền vào có thể chưa phải bản authoritative từ database.
- Test chính sách trở nên khó khăn vì gọi `hasPermission` đã tạo side effect.

**Nguyên tắc:** permission check nên **không có side effect nghiệp vụ** và nên tách truy vấn quyền tối thiểu khỏi thao tác đọc nội dung/cập nhật. Việc đọc metadata hợp lệ, nhưng phải đo số query và giữ nhất quán.

## 4. Mẫu phân tách được khuyến nghị

### Bước A: Định nghĩa policy trên thông tin tối thiểu

Ví dụ muốn cho phép `read` hoặc `write` khi:

```text
authenticated
AND not anonymous
AND action được hỗ trợ
AND có authority DOC_READ hoặc DOC_WRITE tương ứng
AND thuộc đúng tenant của document
AND owner = Authentication.name
AND status = ACTIVE
```

Ứng dụng thực có thể thêm quyền chia sẻ, nhóm, ACL hoặc ngoại lệ admin có audit. Các trường `tenant`, `owner` và `status` phải lấy từ dữ liệu server đáng tin cậy, không lấy từ header/body do caller tự khai.

### Bước B: Evaluator chỉ lấy AccessFacts

```text
PermissionEvaluator
   |
   +--> DocumentRepository.findAccessFacts(id)
              |
              +--> SELECT tenant, owner_name, state
                   FROM documents WHERE id = ?
   |
   +--> DocumentAccessPolicy.can(auth, facts, "write")
   |
   +--> boolean
```

Không cần SELECT `body`, attachment, blob, lịch sử tài liệu hoặc nạp cả object graph chỉ để quyết định quyền.

### Bước C: Service tải/cập nhật trong ranh giới thích hợp

- Với `read`: sau pre-check, service lấy nội dung. Nếu quyền/dữ liệu có thể thay đổi, kiểm tra lại facts trên dữ liệu vừa lấy trước khi trả; hoặc dùng truy vấn có điều kiện tenant/owner.
- Với `write`: sau pre-check, service bắt đầu transaction, lấy bản ghi có khóa hoặc kiểm tra version/conditional update, **kiểm tra lại** policy trên facts hiện hành, sau đó mới mutate.
- Lỗi quyền phải chặn nghiệp vụ; lỗi hợp lệ dữ liệu và xung đột phiên bản cần hợp đồng lỗi rõ (ví dụ 400/409/422 tùy API), không tùy tiện coi mọi lỗi là 403.

## 5. Hai dạng kiểm tra: ID và object

### Kiểm tra bằng ID trước khi tải nội dung

```java
@PreAuthorize("hasPermission(#p0, 'Document', 'read')")
public DocumentView read(long id) {
    Document document = repository.findById(id).orElseThrow();
    return toView(document);
}
```

Đây là **đoạn tích hợp**; `DocumentView`, `toView`, repository thuộc dự án. Lợi ích: chặn caller thiếu quyền **trước khi** method tải nội dung. Chi phí: evaluator có thể phải đọc metadata một lần rồi service đọc resource lần thứ hai. Có thể tối ưu bằng truy vấn projection, join/conditional access hoặc cache có phạm vi an toàn, nhưng không “tối ưu” bằng cách biến evaluator thành nơi ghi dữ liệu.

### Kiểm tra trên object đã tải

```java
@PostAuthorize("returnObject == null or hasPermission(returnObject, 'read')")
public Document get(long id) {
    return repository.findById(id).orElse(null);
}
```

Đoạn này minh họa object overload: method tải tài liệu trước, authorization đánh giá sau khi có `returnObject`. Có thể phù hợp một số API chỉ đọc, nhưng **không bảo vệ chi phí tải hoặc side effect trước thời điểm kiểm tra**. Với tài liệu rất nhạy cảm, nên dùng kiểm tra **trước** method và một ràng buộc dữ liệu ở tầng truy vấn/service; không dùng `@PostAuthorize` làm phương tiện duy nhất bảo vệ update/delete.

### Object do client truyền không phải nguồn quyền đáng tin

```java
@PreAuthorize("hasPermission(#request.document, 'write')")
public void update(UpdateRequest request) {
    // ...
}
```

Nếu `request.document.owner` đến từ JSON client, việc so sánh owner trong evaluator **không chứng minh** caller thực sự sở hữu tài liệu trong database. Chỉ dùng field trusted hoặc tải canonical metadata phía server. Tên `targetType` cũng phải được whitelist: không dùng một string client điều khiển để chọn tùy ý repository/loại tài nguyên.

## 6. Thiết kế Java 17 rõ trách nhiệm

Trong phần này, định nghĩa một mô hình tối thiểu, dùng được cho implementation Spring Boot hoàn chỉnh ở mục 8.

```java
record AccessFacts(String tenant, String owner, String state) {}

record Document(
        long id, String tenant, String owner,
        String state, String body) {

    AccessFacts facts() {
        return new AccessFacts(tenant, owner, state);
    }
}
```

`AccessFacts` không mang nội dung nhạy cảm (`body`). `Document` mang cả nội dung vì service cần dùng nó. `DocumentAccessPolicy` đánh giá một `AccessFacts`. Với Java 17, `record` immutable theo nghĩa các field final; nó phù hợp cho snapshot quyền và giảm nguy cơ mutate tình cờ.

**Quan trọng:** một bản snapshot immutable không khiến quyền trở thành bất biến ở database. Nếu owner/state có thể thay đổi giữa check và write, vẫn cần khóa, version hoặc conditional update.

## 7. Kết nối PermissionEvaluator với MethodSecurityExpressionHandler

Đối với Spring Security 6.x, một cách cấu hình là khai báo bean `MethodSecurityExpressionHandler` và cài evaluator:

```java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfig {

    @Bean
    static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
            DocumentRepository repository,
            DocumentAccessPolicy policy) {

        DefaultMethodSecurityExpressionHandler handler =
                new DefaultMethodSecurityExpressionHandler();

        handler.setPermissionEvaluator(
                new DocumentPermissionEvaluator(repository, policy));

        return handler;
    }
}
```

Đây là **đoạn tích hợp**; `DocumentRepository`, `DocumentAccessPolicy` và `DocumentPermissionEvaluator` thuộc ứng dụng. `@Bean static` được tài liệu Spring Security khuyến nghị để publish handler trước khi framework khởi tạo cấu hình method security. Không cần tạo thêm một bean handler cạnh tranh nếu ứng dụng đã có handler tùy chỉnh để thiết lập `RoleHierarchy` hoặc các option khác: **cấu hình evaluator lên cùng một handler**.

Imports chính:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
```

Đừng nhầm với `SecurityFilterChain` của HTTP. `@EnableMethodSecurity` áp dụng cho lời gọi method qua Spring AOP proxy. Nếu caller tự `new Service()` hoặc gọi nội bộ `this.securedMethod()` trong proxy mode, advice có thể bị bỏ qua. Kiểm thử qua bean Spring thật.

## 8. Ví dụ hoàn chỉnh: Spring Boot + H2 + PermissionEvaluator

Ví dụ dưới đây dùng **Java 17** và **Spring Boot 3.5.16 (Spring Security 6.x)** để có API ổn định, dễ tái hiện. Đây là phiên bản có trên Maven Central, nhưng dòng Spring Boot 3.5.x đã kết thúc hỗ trợ OSS; dự án production nên chọn một dòng còn được hỗ trợ và kiểm tra API khi nâng cấp.

Demo dùng database H2 trong bộ nhớ. Chúng ta **không đọc cả `body` trong evaluator**; evaluator chỉ truy vấn `tenant`, `owner_name`, `state`. Service đọc nội dung sau khi được phép. Với lệnh ghi, service dùng `SELECT ... FOR UPDATE` rồi kiểm tra lại policy trong transaction trước khi update.

Chính sách đơn giản cho demo:

- `DOC_READ` cần cho `read`; `DOC_WRITE` cần cho `write`.
- Caller phải có authority dạng `TENANT_A` hoặc `TENANT_B` tương ứng tenant của tài liệu.
- `Authentication.name` bằng owner, state bằng `ACTIVE`.
- Không hỗ trợ hành động hoặc kiểu tài nguyên khác: **deny**.
- Dữ liệu H2, username và authority là giả lập; không phải hệ thống authentication production.

### 8.1. Cấu trúc

```text
permission-separation-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   └── PermissionSeparationApplication.java
    │   └── resources/
    │       ├── schema.sql
    │       └── data.sql
    └── test/
        └── java/demo/
            └── PermissionSeparationTest.java
```

Để ví dụ ngắn gọn và tránh sai imports giữa các file, các class package-private được đặt cạnh public application class trong **một file Java**. Ở dự án thật, nên tách thành từng file theo trách nhiệm.

### 8.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
  </parent>

  <groupId>demo</groupId>
  <artifactId>permission-separation-demo</artifactId>
  <version>1.0.0</version>

  <properties>
    <java.version>17</java.version>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>
    <dependency>
      <groupId>com.h2database</groupId>
      <artifactId>h2</artifactId>
      <scope>runtime</scope>
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

### 8.3. `src/main/resources/schema.sql`

```sql
CREATE TABLE documents (
    id BIGINT PRIMARY KEY,
    tenant VARCHAR(32) NOT NULL,
    owner_name VARCHAR(64) NOT NULL,
    state VARCHAR(16) NOT NULL,
    body VARCHAR(500) NOT NULL
);
```

### 8.4. `src/main/resources/data.sql`

```sql
INSERT INTO documents (id, tenant, owner_name, state, body)
VALUES (1, 'A', 'alice', 'ACTIVE', 'alpha');

INSERT INTO documents (id, tenant, owner_name, state, body)
VALUES (2, 'B', 'bob', 'ACTIVE', 'beta');

INSERT INTO documents (id, tenant, owner_name, state, body)
VALUES (3, 'A', 'alice', 'LOCKED', 'gamma');
```

Tài liệu 1 thuộc alice, tài liệu 2 thuộc bob/tenant B, tài liệu 3 thuộc alice nhưng bị khóa. Đây là dữ liệu server, không phải các field caller được tự đặt.

### 8.5. `src/main/java/demo/PermissionSeparationApplication.java`

```java
package demo;

import java.io.Serializable;
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.Optional;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.CommandLineRunner;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.PermissionEvaluator;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Repository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@SpringBootApplication
@EnableMethodSecurity
public class PermissionSeparationApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(PermissionSeparationApplication.class);

        app.setDefaultProperties(Map.of(
                "spring.main.web-application-type", "none",
                "spring.main.banner-mode", "off",
                "logging.level.root", "OFF"));

        try (ConfigurableApplicationContext ignored = app.run(args)) {
            // CommandLineRunner đã chạy trong SpringApplication.run.
        }
    }

    @Bean
    static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
            DocumentRepository repository, DocumentAccessPolicy policy) {
        DefaultMethodSecurityExpressionHandler handler =
                new DefaultMethodSecurityExpressionHandler();
        handler.setPermissionEvaluator(
                new DocumentPermissionEvaluator(repository, policy));
        return handler;
    }

    @Bean
    CommandLineRunner showSeparation(DocumentService service) {
        return args -> {
            try {
                authenticate("alice", "TENANT_A", "DOC_READ", "DOC_WRITE");

                printRead("alice read 1", service, 1L);
                printRead("alice read 2", service, 2L);

                printUpdate("alice update 1", service, 1L, "alpha-v2");
                printRead("alice read 1 after", service, 1L);
                printUpdate("alice update 3", service, 3L, "bad");

                authenticate("bob", "TENANT_B", "DOC_READ", "DOC_WRITE");
                printRead("bob read 2", service, 2L);
            } finally {
                SecurityContextHolder.clearContext();
            }
        };
    }

    private static void printRead(String label, DocumentService service, long id) {
        try {
            System.out.println(label + ": " + service.read(id));
        } catch (AccessDeniedException denied) {
            System.out.println(label + ": DENIED");
        }
    }

    private static void printUpdate(
            String label, DocumentService service, long id, String content) {
        try {
            service.update(id, content);
            System.out.println(label + ": OK");
        } catch (AccessDeniedException denied) {
            System.out.println(label + ": DENIED");
        }
    }

    private static void authenticate(String username, String... authorities) {
        List<SimpleGrantedAuthority> granted = Arrays.stream(authorities)
                .map(SimpleGrantedAuthority::new)
                .toList();

        SecurityContext context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(
                UsernamePasswordAuthenticationToken.authenticated(
                        username, "demo-only", granted));
        SecurityContextHolder.setContext(context);
    }
}

// Snapshot chỉ chứa những field cần để quyết định quyền.
record AccessFacts(String tenant, String owner, String state) {}

record Document(
        long id, String tenant, String owner, String state, String body) {
    AccessFacts facts() {
        return new AccessFacts(tenant, owner, state);
    }
}

@Repository
class DocumentRepository {

    private final JdbcTemplate jdbc;

    DocumentRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    // Evaluator sử dụng query metadata, KHÔNG SELECT body.
    Optional<AccessFacts> findAccessFacts(long id) {
        List<AccessFacts> rows = jdbc.query(
                "SELECT tenant, owner_name, state "
                        + "FROM documents WHERE id = ?",
                (rs, rowNumber) -> new AccessFacts(
                        rs.getString("tenant"),
                        rs.getString("owner_name"),
                        rs.getString("state")),
                id);
        return rows.stream().findFirst();
    }

    // Service đọc body sau khi pre-authorization cho phép.
    Optional<Document> findById(long id) {
        return findOne(
                "SELECT id, tenant, owner_name, state, body "
                        + "FROM documents WHERE id = ?",
                id);
    }

    // Bảo vệ dữ liệu đang định sửa cho đến cuối transaction.
    Optional<Document> findByIdForUpdate(long id) {
        return findOne(
                "SELECT id, tenant, owner_name, state, body "
                        + "FROM documents WHERE id = ? FOR UPDATE",
                id);
    }

    private Optional<Document> findOne(String sql, long id) {
        List<Document> rows = jdbc.query(
                sql,
                (rs, rowNumber) -> new Document(
                        rs.getLong("id"),
                        rs.getString("tenant"),
                        rs.getString("owner_name"),
                        rs.getString("state"),
                        rs.getString("body")),
                id);
        return rows.stream().findFirst();
    }

    void updateBody(long id, String body) {
        int count = jdbc.update(
                "UPDATE documents SET body = ? WHERE id = ?", body, id);
        if (count != 1) {
            throw new IllegalStateException("Unexpected document update count");
        }
    }
}

@Component
class DocumentAccessPolicy {

    boolean can(Authentication auth, AccessFacts facts, String action) {
        if (auth == null || !auth.isAuthenticated()
                || auth instanceof AnonymousAuthenticationToken
                || facts == null) {
            return false;
        }

        String requiredAuthority = switch (action) {
            case "read" -> "DOC_READ";
            case "write" -> "DOC_WRITE";
            default -> null;
        };

        if (requiredAuthority == null || !"ACTIVE".equals(facts.state())) {
            return false;
        }

        return facts.owner().equals(auth.getName())
                && hasAuthority(auth, "TENANT_" + facts.tenant())
                && hasAuthority(auth, requiredAuthority);
    }

    private boolean hasAuthority(Authentication auth, String name) {
        return auth.getAuthorities().stream()
                .anyMatch(a -> name.equals(a.getAuthority()));
    }
}

final class DocumentPermissionEvaluator implements PermissionEvaluator {

    private final DocumentRepository repository;
    private final DocumentAccessPolicy policy;

    DocumentPermissionEvaluator(
            DocumentRepository repository, DocumentAccessPolicy policy) {
        this.repository = repository;
        this.policy = policy;
    }

    @Override
    public boolean hasPermission(
            Authentication auth, Object target, Object permission) {
        if (!(target instanceof Document document)
                || !(permission instanceof String action)) {
            return false;
        }
        return policy.can(auth, document.facts(), action);
    }

    @Override
    public boolean hasPermission(
            Authentication auth, Serializable targetId,
            String targetType, Object permission) {
        if (!"Document".equals(targetType)
                || !(targetId instanceof Long id)
                || id <= 0
                || !(permission instanceof String action)) {
            return false;
        }

        return repository.findAccessFacts(id)
                .map(facts -> policy.can(auth, facts, action))
                .orElse(false);
    }
}

@Service
class DocumentService {

    private final DocumentRepository repository;
    private final DocumentAccessPolicy policy;

    DocumentService(DocumentRepository repository, DocumentAccessPolicy policy) {
        this.repository = repository;
        this.policy = policy;
    }

    @Transactional(readOnly = true)
    @PreAuthorize("hasPermission(#p0, 'Document', 'read')")
    public String read(long id) {
        // Method chỉ được gọi khi evaluator đã cho phép ID này.
        Document document = repository.findById(id)
                .orElseThrow(() -> new AccessDeniedException("Denied"));

        // Kiểm tra trên bản ghi thực tế vừa tải, phòng metadata đổi.
        Authentication auth =
                SecurityContextHolder.getContext().getAuthentication();
        if (!policy.can(auth, document.facts(), "read")) {
            throw new AccessDeniedException("Denied");
        }

        return document.body();
    }

    @Transactional
    @PreAuthorize("hasPermission(#p0, 'Document', 'write')")
    public void update(long id, String newBody) {
        if (newBody == null || newBody.isBlank()) {
            throw new IllegalArgumentException("Body must not be blank");
        }

        // Khóa bản ghi trong transaction trước khi cập nhật.
        Document current = repository.findByIdForUpdate(id)
                .orElseThrow(() -> new AccessDeniedException("Denied"));

        Authentication auth =
                SecurityContextHolder.getContext().getAuthentication();
        if (!policy.can(auth, current.facts(), "write")) {
            throw new AccessDeniedException("Denied");
        }

        // Chỉ sau khi kiểm tra lại mới thực hiện thao tác ghi.
        repository.updateBody(id, newBody);
    }
}
```

Mỗi thành phần có một nhiệm vụ:

1. `DocumentRepository.findAccessFacts` chỉ SELECT ba field phục vụ authorization.
2. `DocumentAccessPolicy.can` tính allow/deny từ facts và `Authentication`, không thay đổi database.
3. `DocumentPermissionEvaluator` chỉ kiểm tra loại/ID/action, gọi metadata query và policy, trả boolean.
4. `DocumentService.read` chạy sau `@PreAuthorize`, tải body và kiểm tra lại facts của bản ghi vừa tải trước khi trả ra.
5. `DocumentService.update` mở transaction, khóa bản ghi bằng `FOR UPDATE`, kiểm tra lại quyền trên bản ghi mới nhất rồi mới UPDATE.
6. `@Bean static MethodSecurityExpressionHandler` nối evaluator với biểu thức `hasPermission`.

**Giới hạn demo:** đang giả định một database quan hệ hỗ trợ row locking và một transaction manager hoạt động đúng. H2 phù hợp để minh họa; production cần xác minh transaction isolation/locking và behavior với database thực. `Authentication` trong demo được tạo thủ công qua `SecurityContextHolder`; production phải lấy từ cơ chế authentication được cấu hình, không tin username/tenant do client tự gán.

### 8.6. Chạy ứng dụng

Từ thư mục chứa `pom.xml`, cài Java 17+ và Maven:

```bash
mvn -q clean package
java -jar target/permission-separation-demo-1.0.0.jar
```

Các dòng do ứng dụng in ra:

```text
alice read 1: alpha
alice read 2: DENIED
alice update 1: OK
alice read 1 after: alpha-v2
alice update 3: DENIED
bob read 2: beta
```

Vì sao?

- **Alice đọc 1:** evaluator truy vấn access facts và grant; service tải body `alpha` và re-check rồi trả.
- **Alice đọc 2:** owner và tenant không khớp; evaluator trả false, method không tải `beta`.
- **Alice cập nhật 1:** evaluator cho qua; transaction lấy lock, re-check trên facts hiện hành, ghi `alpha-v2`.
- **Alice đọc lại 1:** body mới được trả.
- **Alice cập nhật 3:** state `LOCKED` khiến evaluator deny, không có lệnh update.
- **Bob đọc 2:** Bob có authority tenant B và quyền read, là owner của document 2.

Đây là **stdout do mã demo được thiết kế tạo ra**, không phải kết quả của một lần build/test đã thực hiện trong môi trường này. Một ứng dụng chạy bằng Maven có thể còn in log framework tùy cấu hình/JVM.

## 9. Kiểm thử: evaluator không làm business operation

Ngoài kiểm thử allow/deny, phải kiểm tra **ranh giới trách nhiệm**.

### 9.1. Integration test với Spring proxy và H2

Tệp `src/test/java/demo/PermissionSeparationTest.java`:

```java
package demo;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
class PermissionSeparationTest {

    @Autowired
    DocumentService service;

    @Autowired
    JdbcTemplate jdbc;

    @BeforeEach
    void restoreFixture() {
        jdbc.update("UPDATE documents SET body = 'alpha' WHERE id = 1");
    }

    @Test
    @WithMockUser(username = "alice",
            authorities = {"TENANT_A", "DOC_READ"})
    void readAllowedDocument() {
        assertEquals("alpha", service.read(1L));
    }

    @Test
    @WithMockUser(username = "alice",
            authorities = {"TENANT_A", "DOC_READ"})
    void cannotReadDocumentInAnotherTenant() {
        assertThrows(AccessDeniedException.class,
                () -> service.read(2L));
    }

    @Test
    @WithMockUser(username = "alice",
            authorities = {"TENANT_A", "DOC_WRITE"})
    void writerUpdatesAfterRecheckingInTransaction() {
        service.update(1L, "alpha-updated");
        assertEquals("alpha-updated", jdbc.queryForObject(
                "SELECT body FROM documents WHERE id = 1",
                String.class));
    }

    @Test
    @WithMockUser(username = "alice",
            authorities = {"TENANT_A", "DOC_READ"})
    void deniedWriteDoesNotMutateResource() {
        assertThrows(AccessDeniedException.class,
                () -> service.update(1L, "unauthorized"));

        assertEquals("alpha", jdbc.queryForObject(
                "SELECT body FROM documents WHERE id = 1",
                String.class));
    }

    @Test
    @WithMockUser(username = "alice",
            authorities = {"TENANT_A", "DOC_WRITE"})
    void lockedResourceCannotBeUpdated() {
        assertThrows(AccessDeniedException.class,
                () -> service.update(3L, "bad"));

        assertEquals("gamma", jdbc.queryForObject(
                "SELECT body FROM documents WHERE id = 3",
                String.class));
    }
}
```

Chạy:

```bash
mvn -q test
```

Test này chứng minh lời gọi đi qua Spring-managed `DocumentService` nên `@PreAuthorize` được thực thi; người thiếu quyền bị deny và body không bị thay đổi. Vì test đọc DB trực tiếp để xác minh hậu điều kiện, nó không bị nhầm với test chỉ kiểm tra HTTP status.

Lưu ý runner của demo cũng chạy khi tạo `@SpringBootTest` context và có thể cập nhật tài liệu 1; `@BeforeEach` đặt lại body cho từng test. Điều này chỉ phục vụ ví dụ, không phải cách tổ chức test fixture cho hệ thống lớn.

### 9.2. Unit test evaluator và policy

Với repository mock, nên xác minh:

- `hasPermission(auth, null, "read")` → false.
- `hasPermission(auth, Long.valueOf(1), "Document", "read")` → true khi facts hợp lệ.
- `targetType` sai hoặc action `"delete"` không hỗ trợ → false, không gọi update.
- ID âm, overflow do input parser khác hoặc không tồn tại → false.
- Principal anonymous/không xác thực/không có authority cần thiết → false.
- Facts khác tenant, khác owner, state `LOCKED` → false.
- Repository chỉ gọi `findAccessFacts`, **không** gọi `updateBody` hoặc business mutation.
- Exception do DB/PDP hỏng không biến thành `true`; chính sách fail-closed hoặc lỗi vận hành được định nghĩa rõ.

Mockito giúp đo boundary, ví dụ:

```java
verify(repository).findAccessFacts(1L);
verify(repository, never()).updateBody(anyLong(), anyString());
```

Đây là **đoạn assertion tích hợp**, cần các imports `org.mockito.Mockito.verify`, `never`, `anyLong`, `anyString` và setup mock đúng cách. Nó không phải file độc lập.

### 9.3. Kiểm thử race condition

Bài toán quan trọng hơn allow/deny tĩnh là:

```text
T1: @PreAuthorize -> evaluator thấy owner = alice -> GRANT
T2: người quản trị chuyển owner sang bob
T3: service của alice bắt đầu update
```

Nếu service **không re-check dưới transaction và không dùng conditional update**, câu lệnh T3 có thể sửa tài liệu mà Alice không còn quyền. Cần integration test concurrency thật trên database production hoặc DB tương thích hành vi khóa: dùng latches để điều phối hai transaction và xác minh writer không thành công khi quyền đã bị thu hồi trước khi lock/recheck.

Demo dùng `SELECT ... FOR UPDATE` để giữ snapshot sau khi khóa; test concurrency cụ thể cần thread và transaction độc lập. Không tuyên bố demo đã tự chứng minh tính đúng đắn dưới mọi mức isolation/database.

## 10. Vì sao pre-check và transaction có thể xảy ra ở hai thời điểm?

Với `@PreAuthorize`, framework phải quyết định có cho lời gọi được thực hiện hay không. Mặc định trong nhiều cấu hình Spring Security/Spring Transaction, advice pre-authorization chạy **bên ngoài hoặc trước** transaction của method đích; nhưng thứ tự thực tế phụ thuộc advisor order.

```text
@PreAuthorize trên proxy
       |
       v
PermissionEvaluator truy vấn facts (T1)
       |
       v
Transaction advice / @Transactional
       |
       v
SELECT ... FOR UPDATE (T2)
       |
       v
Re-check trên bản ghi đã khóa
       |
       v
UPDATE -> COMMIT hoặc ROLLBACK
```

Do đó:

- `@PreAuthorize` là “cửa chặn sớm” tốt, giảm số lần tải nội dung/tiến vào business method cho caller không có quyền.
- `@Transactional` là cơ chế quản lý giao dịch, **không tự giải quyết toàn bộ lỗi TOCTOU**.
- Với mutation nhạy cảm, kiểm tra lại quyền trên state hiện hành, kết hợp khóa hoặc optimistic version/conditional write.
- Nếu transaction không mở vì self-invocation, `new Service()` hoặc cấu hình thiếu transaction manager, logic bảo vệ consistency có thể không đúng kỳ vọng; integration test phải đi qua Spring proxy.

### Lựa chọn ít query hơn: conditional update

Một phương án khác cho ứng dụng không cần tải full document trước ghi là dùng **một UPDATE có điều kiện**:

```sql
UPDATE documents
SET body = ?
WHERE id = ?
  AND tenant = ?
  AND owner_name = ?
  AND state = 'ACTIVE';
```

Service chỉ được tính “thành công” khi số bản ghi cập nhật bằng 1. Với `tenant` và `owner` lấy từ nguồn tin cậy của `Authentication`, database kiểm tra điều kiện cùng câu lệnh UPDATE; tránh khoảng trống giữa SELECT và UPDATE đối với những điều kiện ấy.

Nhưng **không được lấy tenant/owner từ client header**, và SQL vẫn chưa thay thế kiểm tra authority `DOC_WRITE` hay các quy tắc nghiệp vụ khác. Nếu nghiệp vụ cần nhiều bảng hoặc side effects, dùng transaction/locking/version phù hợp.

## 11. Hiệu năng: tách trách nhiệm nhưng tránh N+1 query

Một request đọc 100 tài liệu mà gọi `hasPermission(id,...)` 100 lần có thể tạo 100 query metadata, sau đó service lại tải 100 documents: đây là **N+1** hoặc nhiều truy vấn hơn cần thiết.

Cách xử lý:

1. Với danh sách, đẩy lọc tenant/owner/ACL vào truy vấn có tham số ở repository và chỉ trả những bản ghi được phép.
2. Nếu cần quyền trên từng tài liệu, cân nhắc batch `findAccessFactsByIds` hoặc batch permission API; đừng giả định interface `PermissionEvaluator` tự có overload batch.
3. Kiểm soát kích thước collection khi dùng `@PostFilter`/`@PreFilter`; lọc trong memory sau khi lấy toàn bộ DB không luôn phù hợp.
4. Cache quyết định theo `subject + tenant + resource + action + policyVersion` chỉ khi hợp đồng cập nhật quyền cho phép. Cần TTL/invalidation rõ; cache allow quá lâu dễ làm thu hồi quyền chậm hiệu lực.
5. Nếu đã có một canonical domain object đáng tin và cùng transaction, có thể dùng object overload thay vì query facts thứ hai, nhưng đừng dựa vào object giả mạo từ client.
6. Tránh đọc blob/attachment/trường không liên quan trong evaluator chỉ để kiểm tra owner hoặc tenant.

**Không được tối ưu bằng cách bỏ hoàn toàn kiểm tra lại quyền ở ranh giới ghi có race**, trừ khi persistence operation đã ràng buộc chính sách theo cách khác (atomic conditional update, row-level security, version check...).

## 12. Đường ranh giới tenant và quyền đối tượng

Trong ứng dụng multi-tenant, resource ID chỉ là một phần định danh. Một người có `DOC_READ` không nên mặc nhiên đọc được mọi tài liệu nếu tenant khác.

Một chính sách an toàn có thể là:

```text
allow(user, document, "read") =
    document.exists
    AND user.authenticated
    AND user.has(DOC_READ)
    AND user.tenant ∈ document.allowedTenants
    AND (user.isOwner OR user.hasShareGrant)
    AND document.state ∈ readableStates
```

`PermissionEvaluator` chỉ dùng authorities/claims đã được xác minh bởi authentication infrastructure và dữ liệu authoritative từ server. Với JWT, claim `tenant` phải được xác thực chữ ký/audience/issuer và mapping đúng; không tin raw base64-decoded payload hay header `X-Tenant` nếu không có cơ chế xác minh.

Cần kiểm soát quyền **dọc** (admin/editor/viewer) và quyền **ngang** (người dùng A không đọc tài liệu của B). Đây là phần dễ bị bỏ qua nếu chỉ test một happy path có đúng role.

Không phân biệt quá rõ trên API rằng “ID tồn tại nhưng bạn không có quyền” với “ID không tồn tại” khi điều đó giúp kẻ tấn công liệt kê tài nguyên. Một số hệ thống chọn trả `404` cho cả hai, nhưng implementation HTTP exception handling phải nhất quán và tuân thủ contract, không mặc định mọi request phải là 403.

## 13. Sai lầm thường gặp và cách sửa

**Sai lầm 1 — Evaluator gọi `repository.save(...)`.** Đưa mutation sang service có transaction; evaluator chỉ trả allow/deny.

**Sai lầm 2 — Evaluator tải toàn bộ body, attachments và quan hệ lazy.** Dùng access projection `tenant/owner/state` nếu có thể; giảm I/O và hạn chế việc chạm dữ liệu không cần trước authorization.

**Sai lầm 3 — Chỉ có `@PostAuthorize` trên method cập nhật.** Side effect đã chạy trước kiểm tra. Đặt pre-authorization ở điểm vào và bảo vệ state trước khi ghi.

**Sai lầm 4 — Nghĩ “đã có `@PreAuthorize` thì không cần kiểm tra lại”.** Owner/tenant/state có thể đổi giữa check và write; dùng lock, version, conditional update và consistency contract.

**Sai lầm 5 — Kiểm tra owner từ DTO client.** Client có thể giả mạo; đọc owner từ repository phía server.

**Sai lầm 6 — Truyền ID như object overload.** `hasPermission(#p0,'write')` với `#p0` là Long sẽ gọi overload object; nếu evaluator chỉ xử lý Document object sẽ deny sai. Dùng `hasPermission(#p0,'Document','write')`.

**Sai lầm 7 — Chỉ implement một overload rồi overload còn lại trả true.** Overload chưa hỗ trợ phải trả `false`, không grant. Hãy test target null, type/action lạ.

**Sai lầm 8 — Quên đăng ký evaluator vào MethodSecurityExpressionHandler.** Gọi `hasPermission` không tự nhận custom class nếu handler đang dùng evaluator khác. Cấu hình bean sớm và test method proxy thực sự.

**Sai lầm 9 — Chỉ unit test bằng `new DocumentService(...)`.** Khi gọi trực tiếp object Java, `@PreAuthorize`/`@Transactional` không tự chạy trong proxy mode. Dùng `@SpringBootTest` và bean được inject.

**Sai lầm 10 — Trộn lỗi authorization với lỗi nghiệp vụ.** Chỉnh sửa tài liệu đã lưu trữ có thể là business conflict `409` hoặc quyền `403` tùy contract; không nhất thiết mọi trường hợp state khác đều là lỗi quyền.

**Sai lầm 11 — Lấy `SecurityContextHolder` từ async thread mà chưa truyền context đúng.** Bảo mật thường lưu theo thread; bất đồng bộ cần propagation phù hợp. Không coi việc có Authentication ở thread chính là bảo đảm mọi worker thread đều có.

**Sai lầm 12 — Tạo cache quyền không phân biệt tenant/action.** Cache key chỉ là `userId+documentId` có thể làm quyền `read` bị dùng cho `write` hoặc quyền tenant cũ dùng ở tenant mới. Bao gồm các thành phần policy cần thiết, version và invalidation.

**Sai lầm 13 — Bắt `AccessDeniedException` rồi tiếp tục ghi.** Trong service ghi, lỗi deny phải ngăn mutation; nếu đã có thay đổi trước khi exception, phải đảm bảo transaction rollback đúng. Không nuốt exception để trả thành công.

**Sai lầm 14 — Không xử lý database lỗi khi evaluator đọc facts.** Không biến timeout/exception thành grant; định nghĩa fail-closed và cách map lỗi hệ thống cho API, quan sát p95/p99 latency, retry/circuit-breaker nếu có PDP từ xa.

## 14. So sánh các mẫu triển khai

| Mẫu | Ưu điểm | Hạn chế/điều kiện |
| --- | --- | --- |
| `@PreAuthorize("hasAuthority('DOC_READ')")` | Rất đơn giản, nhanh | Không biết owner/tenant theo resource |
| `@PreAuthorize("hasPermission(#p0,'Document','read')")` | Chặn sớm theo ID, evaluator tái sử dụng | Có thể cần query metadata; phải đăng ký evaluator |
| `@PreAuthorize("@access.canRead(authentication,#p0)")` | Java policy đơn giản, không cần PermissionEvaluator | Không dùng ngôn ngữ `hasPermission` chung |
| `@PostAuthorize("hasPermission(returnObject,'read')")` | Dùng object đã được tải, dễ viết | Đã load/method chạy rồi; không phù hợp bảo vệ side effect |
| `Repository.findByIdAndTenantAndOwner(...)` | Phân quyền data query, giảm race và số query | Phải bảo vệ mọi đường query; policy phức tạp có thể khó diễn đạt |
| `UPDATE ... WHERE owner=? AND tenant=?` | Kiểm tra và ghi nguyên tử với các điều kiện SQL đó | Cần kiểm tra authority, row count và transaction cho tác vụ liên quan |
| `@Transactional` + lock + re-check | Chính sách hiện hành trước ghi và giảm TOCTOU | Tốn query/lock; cần hiểu DB isolation/deadlock |
| Database RLS | Bảo vệ sâu ở tầng lưu trữ | Phụ thuộc DB và đúng mapping danh tính, không thay hết application authorization |

Chọn mẫu theo yêu cầu dữ liệu và threat model, không phải vì một annotation “mạnh” hơn annotation khác. Trong nhiều ứng dụng, có thể kết hợp **pre-check bằng evaluator** và **conditional update** hoặc **lock + re-check**.

## 15. Các trường hợp cần suy nghĩ thêm

### 15.1. Bulk update

Ví dụ client gửi IDs `[1, 2, 3]` để cập nhật đồng loạt. Nếu chỉ lọc các ID được phép rồi ghi phần còn lại, API có thể **thành công một phần** dù người dùng tưởng nguyên batch được áp dụng. Trước khi làm bulk mutation, chọn rõ contract:

- **All-or-nothing:** xác minh tất cả IDs và quyền, sau đó ghi trong transaction; có một ID bị deny thì rollback cả batch.
- **Partial success:** trả rõ từng ID thành công/thất bại, không ghi nhận thành công toàn bộ.
- Giữ idempotency/retry/audit phù hợp cho batch.
- Với lượng lớn, dùng query batch/conditional update, tránh một permission query cho mỗi ID nếu gây N+1.

`PermissionEvaluator` không tự quyết định transaction semantics của batch. Đó là trách nhiệm của application service.

### 15.2. Quyền thay đổi trong lúc đọc

Nếu service kiểm tra permission bằng metadata tại T1 rồi tải body ở T2, quyền có thể bị thu hồi. Kiểm tra trên bản ghi vừa tải hoặc query có điều kiện giúp giảm rủi ro. Với hệ thống đòi hỏi consistency cao, cần giao dịch và khóa/version; **không có một chiến lược áp dụng mọi DB/isolation level**.

### 15.3. Audit

Nên ghi tên action, loại/ID tài nguyên, subject ID đã kiểm soát, tenant và kết quả allow/deny, policy version khi cần. Không ghi toàn bộ body, token, password hoặc dữ liệu nhạy cảm chỉ để debug evaluator.

Nếu policy cần audit “ai đã sửa gì”, ghi sự kiện thành công **sau khi** mutation thành công (thường sau commit hoặc qua transactional outbox). Evaluator chỉ nên ghi quan sát quyết định an toàn, không phát domain event “đã cập nhật”.

### 15.4. Quyền admin

Cho admin bỏ qua owner có thể hợp lệ trong một số tổ chức nhưng phải rõ mức tenant/global, action và audit. Đừng thêm `hasRole('ADMIN') || hasPermission(...)` khắp nơi nếu admin không được vượt biên tenant. Đưa ngoại lệ vào policy duy nhất, test cả trường hợp admin cross-tenant.

## 16. Checklist triển khai và kiểm thử

- [ ] Đã phân tách **authorization policy**, **resource loading** và **business mutation** bằng class/trách nhiệm rõ.
- [ ] `PermissionEvaluator` hỗ trợ đầy đủ hai overload hoặc deny an toàn cho overload không dùng.
- [ ] `targetType`, action, ID được whitelist/validate; target null hoặc loại sai → false.
- [ ] Dùng metadata/projection tối thiểu cho pre-check, không tải body/attachments không cần thiết.
- [ ] Không có `save`/`delete`/domain event trong evaluator.
- [ ] Nhận identity/tenant từ nguồn xác thực đáng tin; owner/state từ repository, không từ DTO/header client.
- [ ] Đã đăng ký evaluator vào handler dùng chung, có `@EnableMethodSecurity`, và lời gọi đi qua Spring proxy.
- [ ] Method đọc chỉ trả nội dung sau khi được phép, cân nhắc kiểm tra lại nếu dữ liệu có thể thay đổi.
- [ ] Method ghi có transaction và cơ chế consistency: lock + re-check, optimistic locking hoặc conditional update.
- [ ] Exception deny không bị nuốt; rollback rules và kết quả update count được kiểm tra.
- [ ] Có test allow/deny, cross-tenant, owner mismatch, state bị khóa, ID không tồn tại và action lạ.
- [ ] Test xác nhận **unauthorized write không thay đổi DB** và evaluator không gọi mutation.
- [ ] Có test concurrency cho trường hợp thu hồi quyền giữa pre-check và write nếu nghiệp vụ nhạy cảm.
- [ ] Đã đo số query/latency và xử lý batch/N+1/cache/invalidation hợp lý.
- [ ] Domain event/audit thành công được ghi sau khi nghiệp vụ commit, không phát từ evaluator.
- [ ] Các đường gọi qua HTTP, job, message consumer vẫn phải đi qua service boundary bảo vệ.

**Nguyên tắc cốt lõi:** `PermissionEvaluator` trả lời **“có quyền không?”**, repository trả lời **“tài nguyên hiện là gì?”**, còn application service thực hiện **“có nên và có thể thay đổi tài nguyên này một cách nhất quán không?”**. Phân tách được ba câu hỏi giúp mã dễ kiểm thử, dễ tối ưu và tránh vô tình cập nhật dữ liệu trong giai đoạn kiểm tra quyền.

## Tài liệu chính thức

- [Spring Security — PermissionEvaluator JavaDoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/access/PermissionEvaluator.html)
- [Spring Security — Method Security và hasPermission](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Framework — Declarative @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring Framework — Rollback trong transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html)
- [Spring Boot 3.5.16 — Thông báo phát hành và hỗ trợ](https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now)
