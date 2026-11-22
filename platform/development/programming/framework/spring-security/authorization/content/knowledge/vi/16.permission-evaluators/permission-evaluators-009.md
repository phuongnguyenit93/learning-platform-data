# Tránh truy vấn lặp cho mỗi phần tử khi kiểm tra tập dữ liệu với `PermissionEvaluator`

## 1. Vì sao một trang 100 tài liệu có thể tạo 101 truy vấn?

Một API trả về danh sách tài liệu mà người dùng hiện tại được đọc. Lập trình viên viết:

```java
@PostFilter("hasPermission(filterObject, 'read')")
public List<Document> listDocuments() {
    return documentRepository.findAll();
}
```

Ở đây `@PostFilter` duyệt kết quả và đánh giá biểu thức cho **từng phần tử**; `filterObject` là đối tượng đang xét. Nếu `PermissionEvaluator.hasPermission(...)` gọi database một lần để xác định quyền trên mỗi tài liệu, một request có thể tạo:

- 1 truy vấn lấy danh sách 100 tài liệu;
- 100 truy vấn khác để xác định quyền đọc của từng tài liệu;
- tổng khoảng **101 truy vấn** để trả một danh sách.

Đó là dạng **N+1 query** trong kiểm tra quyền: không nhất thiết do Hibernate lazy loading; chính bước authorization theo từng phần tử cũng có thể sinh N truy vấn độc lập. Với trang có 2.000 bản ghi, một request có thể cần khoảng 2.001 lần gọi SQL, chưa kể nạp owner, tenant, ACL, role hierarchy hoặc các dữ liệu bổ sung.

Vấn đề còn nghiêm trọng hơn về **bảo mật và phân trang**: nạp toàn bộ tài liệu rồi lọc trong bộ nhớ làm backend chạm vào dữ liệu không thuộc quyền xem; nếu phân trang trước khi lọc, trang trả về có thể thiếu phần tử, tổng số bản ghi và số trang bị sai.

Bài Knowledge này thuộc **Spring Security – authorization**, trọng tâm **PermissionEvaluator**. Sau bài học, bạn sẽ:

1. Nhận ra N+1 khi `@PostFilter`, `@PreFilter` hoặc vòng lặp gọi `hasPermission(...)`.
2. Hiểu khi nào quyền được kiểm tra **mỗi phần tử**, kể cả với các collection nhỏ và lớn.
3. Biết cách đẩy điều kiện quyền xuống SQL bằng `WHERE`/`EXISTS`/`JOIN`, hoặc tra quyền **một lần theo tập ID**.
4. Thiết kế ranh giới bảo mật không để client giả mạo user/tenant.
5. Dùng Java 17+ / Spring Boot, JDBC và H2 chạy một ví dụ so sánh **7 lần gọi DB với 1 lần** cho cùng kết quả.
6. Kiểm thử số lượt truy cập DB, đúng quyền, trường hợp thiếu authority/anonymous và dữ liệu khác tenant.
7. Nắm các giới hạn của cache, phân trang, transaction, index và kiểm tra quyền sau khi dữ liệu thay đổi.

**Nguyên tắc:** tối ưu hiệu năng không được nới lỏng quyền. Nếu người dùng không có quyền đọc bản ghi, mọi chiến lược — kiểm tra từng phần tử, batch hoặc SQL — phải cùng trả kết quả từ chối.

## 2. Cơ chế: `@PostFilter` + `hasPermission` tạo ra bao nhiêu lần gọi?

Khi bật `@EnableMethodSecurity`, Spring Security đăng ký interceptor cho `@PreAuthorize`, `@PostAuthorize`, `@PreFilter` và `@PostFilter`. Trong ví dụ đầu bài:

```text
Caller
  |
  v
Spring-managed service proxy
  |
  v
listDocuments() -> repository.findAll()
  |                      |
  |                     1 SQL
  v
List<Document> gồm N phần tử
  |
  v
@PostFilter: cho từng filterObject
  |---- hasPermission(document 1, "read") -> ACL/DB lookup
  |---- hasPermission(document 2, "read") -> ACL/DB lookup
  |---- ...
  |---- hasPermission(document N, "read") -> ACL/DB lookup
  |
  v
Danh sách đã lọc trả về caller
```

`hasPermission(filterObject, 'read')` dẫn đến chữ ký:

```java
boolean hasPermission(
    Authentication authentication,
    Object targetDomainObject,
    Object permission
);
```

Nếu expression dùng ID:

```java
@PreAuthorize("hasPermission(#id, 'Document', 'read')")
```

thì Spring gọi chữ ký còn lại:

```java
boolean hasPermission(
    Authentication authentication,
    java.io.Serializable targetId,
    String targetType,
    Object permission
);
```

Hai đoạn chữ ký trên chỉ để nhắc hợp đồng API. Điều khiến phát sinh N+1 **không phải bản thân interface** mà là implementation của nó, chẳng hạn mỗi lời gọi dùng `repository.existsBy...` hoặc `aclService.readAclById(...)` riêng cho một tài nguyên.

### Ví dụ chi phí đơn giản

Giả sử mỗi round-trip đến database mất trung bình 3 ms ở một môi trường cụ thể, và bỏ qua chi phí khác chỉ để hiểu quy mô:

| Số phần tử được xét (`N`) | Lần gọi SQL ở chiến lược N+1 | Thời gian round-trip giả định |
| ---: | ---: | ---: |
| 10 | 11 | 33 ms |
| 100 | 101 | 303 ms |
| 1.000 | 1.001 | 3.003 ms |
| 5.000 | 5.001 | 15.003 ms |

Đây **không phải benchmark**. Database có connection pool, bộ đệm, lập kế hoạch truy vấn và độ trễ biến thiên; các query có thể nhanh/chậm khác nhau. Bảng chỉ cho thấy số lần qua mạng hoặc JDBC tăng tuyến tính theo `N`. Trong thực tế, query theo tập có thể vẫn tốn tài nguyên, nhưng thường tiết kiệm nhiều lần round-trip và có cơ hội dùng index tốt hơn.

### Vì sao không chỉ “tăng connection pool”?

Tăng pool có thể làm database chịu tải nặng hơn mà không giảm số truy vấn trên mỗi request. Giải pháp cốt lõi là **giảm số lần phải hỏi cùng một loại quyết định theo từng item**, đưa tập điều kiện xuống tầng dữ liệu hoặc có batch API. Trước khi tối ưu, cần đo **lượt query thực tế** thay vì chỉ đo độ dài danh sách.

## 3. Các hướng xử lý và ưu tiên chọn

| Phương án | Số lượt tra quyền điển hình | Ưu điểm | Điều kiện an toàn |
| --- | --- | --- | --- |
| `@PostFilter` + evaluator truy vấn từng object | `N` lookup sau query danh sách | Dễ viết, dễ biểu đạt | Phù hợp tập nhỏ; tránh nạp dữ liệu nhạy cảm không cần thiết |
| SQL `WHERE`/`EXISTS` có điều kiện owner/tenant/ACL | Thường 1 truy vấn dữ liệu đã được lọc | Ít round-trip, phân trang đúng hơn | Tenant/user từ nguồn xác thực; query khớp policy |
| Đọc ACL/allowed IDs theo batch rồi lọc in-memory | 1 hoặc vài truy vấn quyền cho toàn bộ tập | Dùng lại với nhiều nguồn dữ liệu; hỗ trợ rule phức tạp | Toàn bộ ID được đối chiếu; fail closed; tránh lộ dữ liệu trước lọc |
| Cache quyền theo request | Có thể giảm lookup lặp **cùng ID** | Hữu ích khi cùng đối tượng xuất hiện nhiều lần | Key theo user/tenant/action; không biến N ID khác nhau thành 1 query |
| Cache quyền chia sẻ (Redis/Caffeine) | Giảm lookup khi cache hit | Tăng hit rate giữa requests | Invalidation khi revoke/ACL đổi; không cache `allowed=true` chung giữa user |
| Batch API từ policy decision point (PDP) | Một lời gọi xét nhiều resource | Giảm network hops với hệ thống quyền bên ngoài | Kết quả phải map đúng theo ID, user, tenant và action |

Với endpoint trả danh sách lớn, lựa chọn ưu tiên thường là **đẩy chính sách quyền xuống truy vấn danh sách**, sau đó dùng method security để bảo vệ ranh giới service. Nếu policy không thể biểu diễn trọn vẹn trong SQL, cân nhắc **batch authorization** trên tập ID; không mặc định gọi evaluator lần lượt.

## 4. Quy tắc quyền của ví dụ: quyền tổng quát, tenant và ACL

Demo dùng ba lớp kiểm tra:

1. Caller phải được xác thực, không phải anonymous và có authority `document:read`.
2. Tenant của caller được xác định qua **directory phía server**. Tenant này phải trùng `documents.tenant_id`.
3. Caller được đọc tài liệu nếu là `owner_name` hoặc có bản ghi cấp quyền `'read'` tương ứng trong `document_grants`.

Viết thành biểu thức:

```text
canRead(user, document) =
    authenticated(user)
    AND hasAuthority(user, "document:read")
    AND sameTenant(user, document)
    AND (
          document.ownerName == user.username
          OR grantExists(document.id, user.username, "read")
        )
```

Bộ dữ liệu mẫu:

| ID | Tenant | Chủ sở hữu | Tên tài liệu | Quyền chia sẻ |
| ---: | --- | --- | --- | --- |
| 1 | T1 | alice | Alpha | Không |
| 2 | T1 | bob | Beta | Cho `alice` quyền `read` |
| 3 | T1 | owner3 | Gamma | Không |
| 4 | T2 | owner4 | Delta | Không |
| 5 | T1 | alice | Epsilon | Không |
| 6 | T2 | owner6 | Zeta | Không |

Directory server ghi `alice` và `bob` ở tenant `T1`; `carol` ở `T2`. Với `document:read`, `alice` được thấy ID **[1, 2, 5]**, `bob` được thấy **[2]**. Quyền đọc không được suy từ trường owner/tenant do client tự khai. Nếu caller không có profile hoặc authority, cả hai cách lấy danh sách phải từ chối.

### Quyền phải xuất phát từ dữ liệu server

Không dùng cách kiểm tra sau để cấp quyền:

```java
// Không an toàn nếu document là DTO từ client:
return authentication.getName().equals(document.owner());
```

Client có thể gửi `{"id":4,"owner":"alice","tenant":"T1"}` dù database thực sự lưu ID 4 thuộc tenant T2. Khi kiểm tra bằng SQL, hãy chỉ dùng ID từ đầu vào để tra bản ghi thật, còn `owner`, `tenant`, `grant` lấy từ database; user/tenant lấy từ identity đã được xác thực.

## 5. Ví dụ chạy được: N+1 so với SQL lọc theo tập

Dự án dùng **Java 17, Spring Boot 3.5.8, Spring Security 6.x, Spring JDBC và H2**. Đây là bản demo phục vụ học tập, không phải khuyến nghị giữ nguyên phiên bản patch trong ứng dụng production. Chúng ta cố định phiên bản để ví dụ dễ tái lập.

Mục tiêu là có hai API trên cùng dữ liệu:

- **Legacy:** `@PostFilter("hasPermission(filterObject, 'read')")`, truy vấn danh sách một lần rồi evaluator gửi một query xác định quyền cho **mỗi** tài liệu.
- **Optimized:** cùng policy được triển khai trong một câu SQL `WHERE tenant_id = ? AND (owner = ? OR EXISTS (...))`.

Để có kết quả đếm xác định, ứng dụng tự tăng `DbCalls` **trước mỗi lời gọi JDBC do repository thực hiện**. Đây là bộ đếm số *lời gọi truy vấn của code demo*, không phải bộ đo thống kê toàn bộ câu lệnh trong H2 hoặc Spring Boot startup. Với dataset 6 tài liệu, đường legacy thực hiện 1 + 6 = **7** lần gọi JDBC, đường optimized thực hiện **1**.

### 5.1. Cấu trúc dự án

```text
permission-batch-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── PermissionBatchApplication.java
    │   │   ├── Document.java
    │   │   ├── UserDirectory.java
    │   │   ├── DbCalls.java
    │   │   ├── DocumentRepository.java
    │   │   ├── DocumentPermissionEvaluator.java
    │   │   └── DocumentService.java
    │   └── resources/
    │       ├── schema.sql
    │       └── data.sql
    └── test/java/demo/
        └── DocumentServiceTest.java
```

### 5.2. Gradle

**`settings.gradle`:**

```groovy
rootProject.name = 'permission-batch-demo'
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.8'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-jdbc` cung cấp `JdbcTemplate` và connection pool; `h2` là database in-memory. Spring Boot có thể tự tạo datasource H2 và thực thi `schema.sql` rồi `data.sql` với embedded database khi khởi tạo context. Không cần JPA/entity mapping cho bài demo này, để đếm trực tiếp các truy vấn mà code thực hiện.

### 5.3. Schema và dữ liệu

**`src/main/resources/schema.sql`:**

```sql
CREATE TABLE documents (
    id BIGINT PRIMARY KEY,
    tenant_id VARCHAR(30) NOT NULL,
    owner_name VARCHAR(100) NOT NULL,
    title VARCHAR(150) NOT NULL
);

CREATE TABLE document_grants (
    document_id BIGINT NOT NULL,
    grantee VARCHAR(100) NOT NULL,
    permission VARCHAR(30) NOT NULL,
    PRIMARY KEY (document_id, grantee, permission),
    FOREIGN KEY (document_id) REFERENCES documents(id)
);

CREATE INDEX idx_documents_tenant_owner
    ON documents(tenant_id, owner_name, id);

CREATE INDEX idx_grants_grantee_permission_document
    ON document_grants(grantee, permission, document_id);
```

**`src/main/resources/data.sql`:**

```sql
INSERT INTO documents (id, tenant_id, owner_name, title) VALUES
    (1, 'T1', 'alice', 'Alpha'),
    (2, 'T1', 'bob', 'Beta'),
    (3, 'T1', 'owner3', 'Gamma'),
    (4, 'T2', 'owner4', 'Delta'),
    (5, 'T1', 'alice', 'Epsilon'),
    (6, 'T2', 'owner6', 'Zeta');

INSERT INTO document_grants (document_id, grantee, permission) VALUES
    (2, 'alice', 'read');
```

Các index trên chỉ là điểm xuất phát: với cơ sở dữ liệu thật, phải xem query plan và kích thước bảng. `document_grants` có khóa ngoại để grant không trỏ đến tài liệu không tồn tại. Quy ước production còn có thể cần tenant trong bảng grant và ràng buộc tenant chặt chẽ hơn.

### 5.4. Domain object

**`src/main/java/demo/Document.java`:**

```java
package demo;

public record Document(
        long id,
        String tenant,
        String owner,
        String title) {
}
```

Bản ghi chứa owner/tenant để hiển thị, **không phải bằng chứng quyền** nếu do caller cung cấp. Evaluator trong demo chỉ lấy ID và thực hiện kiểm tra quyền với dữ liệu lưu trong DB.

### 5.5. Directory của người dùng và policy quyền tổng quát

**`src/main/java/demo/UserDirectory.java`:**

```java
package demo;

import java.util.Map;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

record ViewerScope(String username, String tenant) {
}

@Component("userDirectory")
public class UserDirectory {

    private final Map<String, String> tenants = Map.of(
        "alice", "T1",
        "bob", "T1",
        "carol", "T2"
    );

    private final AuthenticationTrustResolver trustResolver =
        new AuthenticationTrustResolverImpl();

    public ViewerScope scope(Authentication auth) {
        if (auth == null
                || !auth.isAuthenticated()
                || trustResolver.isAnonymous(auth)) {
            return null;
        }

        boolean canRead = auth.getAuthorities() != null
            && auth.getAuthorities().stream()
                .anyMatch(a -> "document:read".equals(a.getAuthority()));

        if (!canRead) {
            return null;
        }

        String tenant = tenants.get(auth.getName());
        if (tenant == null) {
            return null;
        }

        return new ViewerScope(auth.getName(), tenant);
    }

    public boolean canBrowse(Authentication auth) {
        return scope(auth) != null;
    }

    public ViewerScope requireScope(Authentication auth) {
        ViewerScope result = scope(auth);
        if (result == null) {
            throw new AccessDeniedException("No trusted document read scope");
        }
        return result;
    }
}
```

Hợp đồng nhỏ `ViewerScope` giữ user và tenant đã được directory server xác định. Ở hệ thống thật, `auth.getName()` có thể là username, `sub` của JWT hoặc một định danh khác; nên ánh xạ sang ID nội bộ ổn định. Trong ứng dụng nhiều tenant, tenant nên lấy từ danh tính/permission mapping đáng tin, **không lấy từ query parameter không kiểm chứng**.

`canBrowse` là bước **authorization cấp chức năng** cho service; evaluator sẽ thêm điều kiện **cấp đối tượng**. Nếu user không tồn tại trong directory, thiếu authority hoặc anonymous, policy trả false. Đặc biệt, `AnonymousAuthenticationToken` có thể có `isAuthenticated() == true`, nên cần `AuthenticationTrustResolver`.

### 5.6. Bộ đếm số lần code gọi JDBC

**`src/main/java/demo/DbCalls.java`:**

```java
package demo;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.stereotype.Component;

@Component
public class DbCalls {

    private final AtomicInteger calls = new AtomicInteger();

    public void record() {
        calls.incrementAndGet();
    }

    public int value() {
        return calls.get();
    }

    public void reset() {
        calls.set(0);
    }
}
```

`DbCalls` là một bộ đếm toàn ứng dụng, chỉ dùng trong chương trình demo tuần tự. Khi có nhiều request đồng thời, bộ đếm này **không đại diện cho một request cụ thể**. Trong production nên dùng query metrics/tracing có request correlation, JDBC proxy hoặc các công cụ quan sát thực tế; không dùng biến toàn cục này để quy trách nhiệm cho từng user.

### 5.7. Repository: ba phương thức và hai chiến lược SQL

**`src/main/java/demo/DocumentRepository.java`:**

```java
package demo;

import java.util.List;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Repository;

@Repository
public class DocumentRepository {

    private static final RowMapper<Document> MAPPER = (rs, row) ->
        new Document(
            rs.getLong("id"),
            rs.getString("tenant_id"),
            rs.getString("owner_name"),
            rs.getString("title")
        );

    private final JdbcTemplate jdbc;
    private final DbCalls dbCalls;

    public DocumentRepository(JdbcTemplate jdbc, DbCalls dbCalls) {
        this.jdbc = jdbc;
        this.dbCalls = dbCalls;
    }

    // Một truy vấn để nạp TOÀN BỘ bản ghi; đây là đường chưa tối ưu.
    public List<Document> loadAll() {
        dbCalls.record();
        return jdbc.query(
            "SELECT id, tenant_id, owner_name, title " +
            "FROM documents ORDER BY id",
            MAPPER
        );
    }

    // Một lookup quyền theo ID; gọi N lần sẽ tạo N lượt DB.
    public boolean canRead(ViewerScope scope, long id) {
        dbCalls.record();

        Integer matches = jdbc.queryForObject(
            """
            SELECT COUNT(*)
            FROM documents d
            WHERE d.id = ?
              AND d.tenant_id = ?
              AND (
                    d.owner_name = ?
                    OR EXISTS (
                        SELECT 1
                        FROM document_grants g
                        WHERE g.document_id = d.id
                          AND g.grantee = ?
                          AND g.permission = 'read'
                    )
              )
            """,
            Integer.class,
            id,
            scope.tenant(),
            scope.username(),
            scope.username()
        );

        return matches != null && matches > 0;
    }

    // Một truy vấn trả thẳng các tài liệu caller được thấy.
    public List<Document> loadVisible(ViewerScope scope) {
        dbCalls.record();

        return jdbc.query(
            """
            SELECT d.id, d.tenant_id, d.owner_name, d.title
            FROM documents d
            WHERE d.tenant_id = ?
              AND (
                    d.owner_name = ?
                    OR EXISTS (
                        SELECT 1
                        FROM document_grants g
                        WHERE g.document_id = d.id
                          AND g.grantee = ?
                          AND g.permission = 'read'
                    )
              )
            ORDER BY d.id
            """,
            MAPPER,
            scope.tenant(),
            scope.username(),
            scope.username()
        );
    }
}
```

Điểm cần đọc kỹ:

- `loadAll()` chạy một SQL nhưng lấy **cả các bản ghi thuộc tenant khác**. Đó là lý do không nên lấy `findAll()` rồi lọc trong bộ nhớ cho API thực tế.
- `canRead(scope, id)` mỗi lần chạy một `COUNT(*)` với cùng tenant, user và permission; nếu evaluator gọi cho từng object, SQL sẽ được thực hiện N lần.
- `loadVisible(scope)` đưa **cùng rule** vào một câu SQL: `tenant` khớp và (`owner` khớp hoặc có grant `'read'`). Database được quyền tối ưu tập kết quả qua index/query planner.
- Tất cả biến đều là tham số `?` của `JdbcTemplate`, **không nối chuỗi SQL từ username hoặc ID client**, giúp tránh SQL injection.
- Vì query có điều kiện `d.tenant_id = ?`, một bản ghi ở T2 không được trả cho principal của T1 kể cả khi ID được đưa vào hoặc có grant không hợp lệ.
- `ORDER BY d.id` bảo đảm thứ tự xác định trong demo. Với phân trang production nên có `ORDER BY` ổn định, bổ sung tie-breaker khi cần.

**Phân biệt số lời gọi và thời gian:** optimized không “tính quyền miễn phí”; database vẫn phải xét điều kiện owner/ACL cho những bản ghi phù hợp. Lợi ích là lọc theo tập trong một SQL, có cơ hội tận dụng index và tránh hàng loạt round-trip.

### 5.8. `PermissionEvaluator` cố ý sử dụng đường N+1 để minh họa

**`src/main/java/demo/DocumentPermissionEvaluator.java`:**

```java
package demo;

import java.io.Serializable;

import org.springframework.security.access.PermissionEvaluator;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component
public class DocumentPermissionEvaluator implements PermissionEvaluator {

    private final UserDirectory directory;
    private final DocumentRepository repository;

    public DocumentPermissionEvaluator(
            UserDirectory directory,
            DocumentRepository repository) {
        this.directory = directory;
        this.repository = repository;
    }

    @Override
    public boolean hasPermission(
            Authentication authentication,
            Object targetDomainObject,
            Object permission) {

        if (!(targetDomainObject instanceof Document document)) {
            return false;
        }

        // Chỉ tin ID; không tin owner/tenant từ object đầu vào.
        return allowed(authentication, document.id(), permission);
    }

    @Override
    public boolean hasPermission(
            Authentication authentication,
            Serializable targetId,
            String targetType,
            Object permission) {

        if (!"Document".equals(targetType)
                || !(targetId instanceof Long id)) {
            return false;
        }

        return allowed(authentication, id, permission);
    }

    private boolean allowed(
            Authentication authentication,
            Long id,
            Object permission) {

        if (id == null || !"read".equals(permission)) {
            return false;
        }

        ViewerScope scope = directory.scope(authentication);
        if (scope == null) {
            return false;
        }

        // Một JDBC query CHO MỖI lời gọi hasPermission.
        return repository.canRead(scope, id);
    }
}
```

Đây là evaluator đúng về **kết quả quyền** nhưng không tối ưu khi lặp qua danh sách lớn. Việc triển khai cả hai overload đảm bảo `hasPermission(object, 'read')` và `hasPermission(id, 'Document', 'read')` có cùng policy. Tuy nhiên, overload chỉ được gọi **một lần cho mỗi object**, vì vậy có `N` lần truy vấn khi gắn vào `@PostFilter`.

Không thêm cache singleton kiểu `Map<Long, Boolean>` để “sửa” N+1. Key thiếu user/tenant/action có thể làm người khác được hưởng quyết định `true` đã cache. Hơn nữa, cache per-item không giảm N lookup với N ID hoàn toàn khác nhau ở cache cold; SQL/batch thường thích hợp hơn.

### 5.9. Service: phương thức chậm và phương thức tối ưu

**`src/main/java/demo/DocumentService.java`:**

```java
package demo;

import java.util.List;

import org.springframework.security.access.prepost.PostFilter;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {

    private final DocumentRepository repository;
    private final UserDirectory directory;

    public DocumentService(
            DocumentRepository repository,
            UserDirectory directory) {
        this.repository = repository;
        this.directory = directory;
    }

    @PreAuthorize("@userDirectory.canBrowse(authentication)")
    @PostFilter("hasPermission(filterObject, 'read')")
    public List<Document> listLegacy() {
        return repository.loadAll();
    }

    @PreAuthorize("@userDirectory.canBrowse(authentication)")
    public List<Document> listOptimized() {
        var authentication = SecurityContextHolder.getContext()
            .getAuthentication();
        ViewerScope scope = directory.requireScope(authentication);

        // DB chỉ trả tài liệu đã thỏa rule quyền.
        return repository.loadVisible(scope);
    }
}
```

`listLegacy` phải đi qua Spring proxy để `@PostFilter` được thực thi; nếu gọi `new DocumentService(...)`, `this.listLegacy()` nội bộ hoặc tự bỏ `@EnableMethodSecurity`, interceptor có thể không chạy. Vì vậy ví dụ **không được dùng trực tiếp để xuất bản endpoint** khi chưa bảo đảm đúng đường gọi và đúng quyền.

`@PreAuthorize("@userDirectory.canBrowse(authentication)")` bảo vệ **cả hai** phương thức ở cấp chức năng: caller phải là user thật, có authority và có tenant từ directory. Sau đó:

- `listLegacy`: query all, rồi `hasPermission` cho từng tài liệu.
- `listOptimized`: `UserDirectory` lấy scope đáng tin và repository chỉ load visible rows.

Vì cùng một rule owner/grant/tenant được mã hóa ở `canRead` và `loadVisible`, hai đường phải trả đúng cùng tập ID. Trong codebase thật, tránh để hai implementation chính sách bị **trôi logic** khi có thêm trạng thái, loại quyền hay tenant: viết integration/contract test so sánh, gom shared query fragment/specification có kiểm soát hoặc thiết kế authorization service chung.

### 5.10. Bật Method Security và chạy kịch bản

**`src/main/java/demo/PermissionBatchApplication.java`:**

```java
package demo;

import java.util.List;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Profile;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.PermissionEvaluator;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;

@SpringBootApplication
@EnableMethodSecurity
public class PermissionBatchApplication {

    public static void main(String[] args) {
        SpringApplication.run(PermissionBatchApplication.class, args);
    }

    @Bean
    static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
            PermissionEvaluator evaluator) {
        var handler = new DefaultMethodSecurityExpressionHandler();
        handler.setPermissionEvaluator(evaluator);
        return handler;
    }

    @Bean
    @Profile("!test")
    CommandLineRunner runDemo(DocumentService service, DbCalls calls) {
        return args -> {
            try {
                authenticateAs("alice", "document:read");

                calls.reset();
                System.out.println("ALICE_LEGACY_IDS: "
                    + ids(service.listLegacy()));
                System.out.println("ALICE_LEGACY_DB_CALLS: "
                    + calls.value());

                calls.reset();
                System.out.println("ALICE_OPTIMIZED_IDS: "
                    + ids(service.listOptimized()));
                System.out.println("ALICE_OPTIMIZED_DB_CALLS: "
                    + calls.value());

                authenticateAs("bob", "document:read");
                System.out.println("BOB_OPTIMIZED_IDS: "
                    + ids(service.listOptimized()));

                authenticateAs("bob", "unrelated:read");
                expectDenied("NO_AUTHORITY",
                    () -> service.listOptimized());
            } finally {
                SecurityContextHolder.clearContext();
            }
        };
    }

    private static List<Long> ids(List<Document> docs) {
        return docs.stream().map(Document::id).toList();
    }

    private static void authenticateAs(String username, String authority) {
        var token = new UsernamePasswordAuthenticationToken(
            username,
            "demo-only",
            List.of(new SimpleGrantedAuthority(authority))
        );
        var context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(token);
        SecurityContextHolder.setContext(context);
    }

    private static void expectDenied(String label, Runnable action) {
        try {
            action.run();
            System.out.println(label + ": UNEXPECTED_ALLOW");
        } catch (AccessDeniedException denied) {
            System.out.println(label + ": DENIED");
        }
    }
}
```

`@EnableMethodSecurity` bật `@PreAuthorize` và `@PostFilter`. Bean `MethodSecurityExpressionHandler` được khai báo `static` và gọi `setPermissionEvaluator(...)` để `hasPermission` dùng evaluator của ứng dụng. Phương thức này **không tự nạp ACL**: evaluator của chúng ta sử dụng JDBC, nên không cần module Spring Security ACL.

Mẫu tạo `UsernamePasswordAuthenticationToken` đã được xác thực chỉ dành cho **chương trình mô phỏng**. Trong ứng dụng thật, token/context phải đến từ authentication provider, session hoặc bearer JWT đã được xác minh; tuyệt đối không tạo token tin cậy từ `username` client gửi tùy ý. Mọi lần đổi danh tính trong demo đều tạo context mới và giải phóng trong `finally`.

### 5.11. Chạy và đối chiếu stdout

Tại thư mục có `build.gradle`, nếu đã có Gradle Wrapper:

```bash
./gradlew bootRun
```

Trên Windows PowerShell:

```bash
.\gradlew.bat bootRun
```

Nếu chưa có Wrapper nhưng đã cài Gradle tương thích, chạy `gradle bootRun` hoặc tạo Gradle Wrapper trước. Ngoài log khởi động của Spring Boot, các dòng do code demo **trực tiếp in ra** là:

```text
ALICE_LEGACY_IDS: [1, 2, 5]
ALICE_LEGACY_DB_CALLS: 7
ALICE_OPTIMIZED_IDS: [1, 2, 5]
ALICE_OPTIMIZED_DB_CALLS: 1
BOB_OPTIMIZED_IDS: [2]
NO_AUTHORITY: DENIED
```

**Giải thích chính xác số đếm:**

1. Legacy chạy `loadAll()` một lần, nhận 6 tài liệu. `@PostFilter` chạy evaluator trên cả 6; mỗi evaluator gọi `canRead()` một query. Tổng số lần `DbCalls.record()` = **1 + 6 = 7**.
2. Optimized chạy `loadVisible(scope)` một lần. Không có `@PostFilter` trên phương thức này, nên không có 6 lookup riêng. Tổng = **1**.
3. Cả hai trả `[1, 2, 5]` cho `alice` (tài liệu sở hữu 1/5 và grant 2). Tài liệu `3` không có quyền và tài liệu `4`, `6` ở tenant T2 không xuất hiện.
4. `bob` thấy `[2]`. Khi authority đổi thành `unrelated:read`, `@PreAuthorize` từ chối lời gọi, không chạy repository.

Đây là **đếm lời gọi JDBC do code được viết thực hiện**, không phải đo chính xác số packet, số bản ghi quét, thời gian hoặc CPU của database. Với SQL optimizer khác nhau, một statement vẫn có thể dùng nhiều operation nội bộ. Muốn chứng minh hiệu năng ở production, cần số liệu latency p50/p95/p99, query plan, I/O, CPU, số hàng scan, kết nối và phân trang.

## 6. Kiểm thử: quyền không đổi khi giảm từ 7 query xuống 1

**`src/test/java/demo/DocumentServiceTest.java`:**

```java
package demo;

import java.io.Serializable;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.PermissionEvaluator;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.test.context.support.WithAnonymousUser;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("test")
class DocumentServiceTest {

    @Autowired DocumentService service;
    @Autowired PermissionEvaluator evaluator;
    @Autowired DbCalls calls;

    @BeforeEach
    void resetCounter() {
        calls.reset();
    }

    private List<Long> ids(List<Document> documents) {
        return documents.stream().map(Document::id).toList();
    }

    @Test
    @WithMockUser(username = "alice", authorities = "document:read")
    void bothPathsReturnSameRowsButOneUsesFewerQueries() {
        List<Long> legacy = ids(service.listLegacy());
        assertEquals(List.of(1L, 2L, 5L), legacy);
        assertEquals(7, calls.value());

        calls.reset();
        List<Long> optimized = ids(service.listOptimized());
        assertEquals(legacy, optimized);
        assertEquals(1, calls.value());
    }

    @Test
    @WithMockUser(username = "bob", authorities = "document:read")
    void onlyBobsDocumentIsVisible() {
        assertEquals(List.of(2L), ids(service.listOptimized()));
        assertEquals(1, calls.value());
    }

    @Test
    @WithMockUser(username = "alice", authorities = "document:read")
    void forgedDtoCannotOverrideServerTenantOrOwner() {
        var auth =
            SecurityContextHolder.getContext().getAuthentication();

        // ID 4 thực tế thuộc tenant T2: forged DTO khai T1/alice
        // không làm evaluator cấp quyền.
        Document forged = new Document(4L, "T1", "alice", "Forged");
        assertFalse(evaluator.hasPermission(auth, forged, "read"));

        assertFalse(evaluator.hasPermission(
            auth, (Serializable) 4L, "Document", "read"
        ));

        // Tài liệu 2 được share read cho alice.
        assertTrue(evaluator.hasPermission(
            auth, (Serializable) 2L, "Document", "read"
        ));
    }

    @Test
    @WithMockUser(username = "bob", authorities = "unrelated:read")
    void missingAuthorityDeniesBeforeDataQuery() {
        assertThrows(AccessDeniedException.class,
            () -> service.listLegacy());
        assertThrows(AccessDeniedException.class,
            () -> service.listOptimized());

        assertEquals(0, calls.value());
    }

    @Test
    @WithMockUser(username = "ghost", authorities = "document:read")
    void missingTrustedProfileFailsClosed() {
        assertThrows(AccessDeniedException.class,
            () -> service.listOptimized());
    }

    @Test
    @WithAnonymousUser
    void anonymousPrincipalIsDenied() {
        assertThrows(AccessDeniedException.class,
            () -> service.listOptimized());
    }
}
```

Chạy:

```bash
./gradlew test
```

`@SpringBootTest` nạp context thật, `@WithMockUser`/`@WithAnonymousUser` từ `spring-security-test` thiết lập `Authentication` để Method Security đánh giá. `@ActiveProfiles("test")` vô hiệu hóa CLI runner, không làm demo in stdout trong test.

Test dùng `@Autowired DocumentService`: cần gọi **Spring-managed proxy** thì `@PostFilter` mới thực sự chạy. Một unit test tạo `new DocumentService(...)` rồi so kết quả **không kiểm chứng** Spring Method Security.

Lưu ý `DbCalls` trong demo là singleton và các test ở đây được giả định chạy tuần tự. Nếu hệ thống chạy test song song hoặc có tác vụ khác cùng dùng repository, thay bằng metric/tracer tách theo test/request. Đối với JPA, có thể dùng SQL statistics/`StatementInspector`; với JDBC, dùng datasource proxy hoặc tracing. Không dựa vào một con số global để đo production.

## 7. Lọc tập dữ liệu ở tầng SQL: không chỉ là vấn đề hiệu năng

### 7.1. Tại sao `WHERE` + `EXISTS` thường tốt hơn lọc sau khi đọc?

Một câu SQL có quyền theo người gọi có dạng:

```sql
SELECT d.id, d.title
FROM documents d
WHERE d.tenant_id = :trustedTenant
  AND (
      d.owner_name = :trustedUsername
      OR EXISTS (
          SELECT 1
          FROM document_grants g
          WHERE g.document_id = d.id
            AND g.grantee = :trustedUsername
            AND g.permission = 'read'
      )
  )
ORDER BY d.id;
```

Cú pháp `:trustedTenant`, `:trustedUsername` ở đây minh họa **named parameters**; dùng `NamedParameterJdbcTemplate`, JPA query parameters hoặc adapter thích hợp. `JdbcTemplate` thuần ở mục 5 dùng `?`.

Database có thể sử dụng index, join hoặc semi-join để xử lý hàng loạt. Quan trọng hơn, API chỉ materialize những hàng hợp lệ. Một lần lấy list và một lần lấy policy theo từng item không còn cần thiết.

**Caveat:** câu SQL phải phản ánh đúng mọi ràng buộc, chẳng hạn trạng thái `PUBLISHED`, tenant, share expiration, role, denied ACE và field-level redaction nếu nghiệp vụ có. Một query nhanh nhưng quên ràng buộc tenant hoặc revoke là lỗi bảo mật nặng hơn N+1.

### 7.2. Hạn chế duplicate khi dùng JOIN

Một query dễ mắc lỗi:

```sql
SELECT d.*
FROM documents d
JOIN document_grants g ON g.document_id = d.id
WHERE g.grantee = :username;
```

Nó có thể loại bỏ tài liệu do chủ sở hữu tự được xem (nếu không có grant), trả bản ghi trùng khi có nhiều grant và quên tenant. `EXISTS` có ích vì chỉ cần xác định **có một grant phù hợp**, tránh nhân bản số dòng do join nhiều-một. Nếu dùng join, phải xử lý đúng cả owner, tenant, permission, duplicate và phân trang.

### 7.3. Phân trang phải xảy ra **sau điều kiện quyền**

Ví dụ request `pageSize = 10`:

1. Query đầu tiên lấy 10 tài liệu bất kỳ.
2. `@PostFilter` loại 9 tài liệu không được xem.
3. Client chỉ nhận 1 tài liệu, dù phía sau còn hàng trăm tài liệu được phép xem.
4. Giá trị `totalElements` (nếu đã tính trước khi lọc) có thể tính cả tài liệu mà user không được quyền, gây sai UI và đôi khi lộ metadata.

Cách đúng là đặt điều kiện quyền trong SQL **trước** khi `LIMIT`/`OFFSET` hoặc cursor/keyset pagination được áp dụng:

```sql
SELECT d.id, d.title
FROM documents d
WHERE d.tenant_id = :tenant
  AND (
      d.owner_name = :username
      OR EXISTS (
          SELECT 1
          FROM document_grants g
          WHERE g.document_id = d.id
            AND g.grantee = :username
            AND g.permission = 'read'
      )
  )
ORDER BY d.id
LIMIT :pageSize OFFSET :offset;
```

Đây là SQL minh họa trên database hỗ trợ `LIMIT/OFFSET`; framework và DB dialect có cách phân trang khác nhau. Query `COUNT(*)` cho tổng số bản ghi cũng phải dùng **cùng điều kiện quyền**, không đếm toàn tenant hoặc toàn bảng rồi lọc sau. Với dataset rất lớn, cân nhắc keyset pagination dựa trên `(created_at, id)` hoặc khóa sắp xếp ổn định.

## 8. Khi policy không thể đưa hết vào SQL: batch tra quyền

Có trường hợp quyết định cần hỏi một policy service ngoài database, nhiều loại resource, ACL phức tạp hoặc dữ liệu phân tán. Không nhất thiết phải đưa mọi logic vào một câu SQL khổng lồ; thay vào đó, thiết kế **bulk authorization**.

### 8.1. Quy trình theo batch

```text
1. Xác thực caller -> trustedPrincipal, trustedTenant, action
2. Lấy một tập ID ứng viên từ repository có giới hạn
3. Gọi authorizationService.allowedIds(user, tenant, action, ids)
4. Nhận Set<ID> được phép và xác minh đủ/đúng phạm vi yêu cầu
5. Lọc dữ liệu ứng viên hoặc truy vấn lại chỉ những ID được phép
6. Áp dụng giới hạn dữ liệu, thứ tự, phân trang và policy bổ sung
```

Thay vì:

```java
for (Document document : documents) {
    if (permissionEvaluator.hasPermission(
            authentication, document, "read")) {
        result.add(document);
    }
}
```

hãy tạo một API chuyên biệt:

```java
// Chữ ký thiết kế; không phải đoạn mã chạy độc lập.
Set<Long> allowedDocumentIds(
    ViewerScope viewer,
    String permission,
    Set<Long> candidateIds
);
```

API này có thể dùng một SQL:

```sql
SELECT d.id
FROM documents d
WHERE d.id IN (:ids)
  AND d.tenant_id = :tenant
  AND (
      d.owner_name = :username
      OR EXISTS (
          SELECT 1
          FROM document_grants g
          WHERE g.document_id = d.id
            AND g.grantee = :username
            AND g.permission = 'read'
      )
  );
```

`IN (:ids)` là minh họa cho `NamedParameterJdbcTemplate`/ORM biết bind collection, **không** nối thủ công chuỗi ID từ client vào SQL. Khi tập ID lớn, phải chia batch phù hợp giới hạn tham số của DB, tránh một câu lệnh hàng trăm nghìn biến hoặc dùng temporary table/table-valued parameter nếu DB hỗ trợ.

### 8.2. Lưu ý quan trọng cho thao tác ghi nhiều item

Nếu API là `updateDocuments(List<Long> ids)`, việc âm thầm loại item không được phép rồi cập nhật số còn lại có thể vi phạm hợp đồng nghiệp vụ. Cần quyết định rõ:

- **All-or-nothing:** yêu cầu `allowedIds` chứa **toàn bộ tập ID** được yêu cầu, còn ID lạ/không tồn tại/từ tenant khác hoặc bị từ chối thì **không cập nhật gì**; dùng transaction và ràng buộc tại thời điểm ghi.
- **Partial success có chủ đích:** trả kết quả từng item với trạng thái `ALLOWED`/`DENIED` theo một hợp đồng rõ ràng, không tiết lộ thông tin tài nguyên không được phép cho người không đủ quyền.

`@PreFilter("hasPermission(filterObject, 'write')")` mặc định có nghĩa là lọc phần tử đầu vào. Nó **không tự bảo đảm atomicity** hay trả lỗi cho từng item; collection có thể bị sửa/loại phần tử trước khi thân phương thức chạy. Vì vậy, với thao tác tiền bạc, duyệt đơn hàng, xóa hàng loạt, hãy xác định rõ kỳ vọng nghiệp vụ trước khi dùng filter.

### 8.3. Tránh sai lệch do ID trùng và trạng thái thay đổi

- Chuẩn hóa danh sách ID, xử lý `null`, ID trùng, ID không tồn tại và giới hạn độ dài đầu vào.
- Một tập `allowedIds` trả về thiếu bản ghi có thể là vì **không tồn tại** hoặc **không được phép**; endpoint không nhất thiết phải tiết lộ sự khác biệt này.
- Tránh lấy `viewerId`/`tenantId` trực tiếp từ JSON như một bằng chứng quyền; derive từ principal đã được xác minh.
- Nếu quyền có thể bị thu hồi giữa bước prefetch và thao tác ghi, cần ràng buộc thêm ở transaction/update hoặc cơ chế consistency thích hợp.
- Không cache `allowedIds` vô thời hạn. Tập quyền phụ thuộc principal, tenant, action, tài nguyên và policy version.

## 9. Vì sao cache không tự giải quyết N+1?

Giả sử `PermissionEvaluator` có cache:

```text
key = (userId, tenantId, documentId, permission, policyVersion)
```

Đây là key phù hợp hơn key chỉ có `documentId`, nhưng khi request đầu tiên cần duyệt **1.000 ID khác nhau**, cache cold vẫn có thể gây **1.000 lookup**, sau đó mới có khả năng hit. Cache hữu ích nếu:

- cùng một đối tượng bị kiểm tra lặp trong request;
- nhiều request liên tiếp kiểm tra các object đã có entry;
- thay đổi ACL ít và có chiến lược invalidation đáng tin.

Cache cũng có chi phí:

- **Revoke/ownership/tenant** đổi khiến kết quả `allowed=true` cũ không còn hợp lệ.
- Cross-user/tenant leakage nếu key thiếu scope danh tính.
- Bộ nhớ tăng theo số `(user × resource × action × policy)`.
- Cache distributed phải thống nhất invalidation giữa node.
- Chính sách phải được cập nhật khi permission mask, group membership hoặc role hierarchy thay đổi.

**Ưu tiên:** giảm số lần truy vấn không cần thiết bằng SQL/batch, sau đó dùng cache có kiểm soát ở những điểm thật sự có lợi. Với policy nhạy cảm, thậm chí không cache quyết định cấp quyền nếu không thể bảo đảm thông tin mới nhất.

### Cache trong một request khác gì cache toàn ứng dụng?

Một `RequestScope` memoization có thể giữ kết quả đã tra cho `(user, tenant, ID, action)` trong một request; nó giúp khi **cùng ID** được kiểm tra vài lần. Còn `PermissionEvaluator` thường là singleton Spring bean: không được giữ `Authentication currentUser` trong field mutable cho nhiều request đồng thời. Khi dùng async hoặc job không có request HTTP, khái niệm request scope cũng có thể không tồn tại.

## 10. Đo lường và tối ưu truy vấn có hệ thống

Đừng tối ưu dựa trên suy đoán. Một quy trình thực tế:

1. **Đo baseline:** bao nhiêu SQL trong một request list? Bao nhiêu do truy xuất dữ liệu, bao nhiêu do evaluator/ACL? Số bản ghi ứng viên là bao nhiêu?
2. **Phân tích trace:** tìm pattern `SELECT ... FROM acl WHERE object_id = ?` lặp N lần hoặc nhiều lần `existsBy...` với ID khác nhau.
3. **Kiểm tra query plan:** dùng `EXPLAIN`/`EXPLAIN ANALYZE` tùy DB. Xem index tenant/owner, lookup grants, số hàng scan, nested loop, sort và join cardinality.
4. **Tối ưu theo tập:** thay vòng lặp truy vấn từng object bằng query lọc kết quả hoặc batch allowed IDs.
5. **Bảo đảm semantic parity:** cùng user, role, tenant và ACL phải có cùng kết quả ở phiên bản cũ/mới; test cả deny và missing ID.
6. **Đo lại:** số lần gọi SQL, p50/p95/p99 latency, memory, CPU DB, rows read, connection-pool saturation, throughput và payload.
7. **Kiểm tra bảo mật:** không lộ cross-tenant, owner giả, quyền hết hạn, cache stale hoặc tổng số bản ghi trái phép.
8. **Triển khai có kiểm soát:** nếu thay query lớn trong production, cần giám sát regressions, plan stability và rollback strategy.

### Về index

Với SQL demo, index `documents(tenant_id, owner_name, id)` và `document_grants(grantee, permission, document_id)` có thể hữu ích. Nhưng index tốt phụ thuộc dữ liệu thật, thứ tự chọn lọc, kích thước tenant và optimizer. `EXISTS` chỉ nói về semantics; không tự bảo đảm DB chọn plan tối ưu.

Với quyền dựa trên `group membership`, có thể join/batch vào bảng nhóm. Nếu ACL có quy tắc deny overriding allow, query SQL phải tái tạo đúng thứ tự ưu tiên, không đơn giản dùng `EXISTS grant` như trường hợp owner/read giản lược.

## 11. Rủi ro bảo mật và tính nhất quán

### 11.1. Lọc tại database không thay thế bảo vệ method

Một controller có thể được gọi qua job, service khác hoặc message consumer. Dù repository đã đưa owner/tenant vào query, vẫn cần kiểm tra authority cấp chức năng ở ranh giới service (`@PreAuthorize` hoặc `AuthorizationManager` phù hợp). Tương tự, **không** cấp quyền chỉ vì client truyền ID/tenant có vẻ đúng.

### 11.2. Đọc và ghi là hai bài toán khác nhau

Với read-only list, trả tập tài liệu visible theo SQL thường phù hợp. Với thao tác ghi, policy có thể thay đổi giữa lúc gọi `allowedIds()` và lúc update. Đó là **TOCTOU (time of check, time of use)**.

Một lệnh ghi có thể cần điều kiện quyền ngay trong câu `UPDATE`/`DELETE`, kiểm tra số hàng bị tác động, transaction, locking hoặc version column. Không sử dụng danh sách ID được phép đã cache từ vài phút trước làm bằng chứng đủ để cập nhật khi chính sách vừa đổi.

### 11.3. `@PostFilter` và dữ liệu nhạy cảm

Khi method trả toàn bộ danh sách rồi `@PostFilter` mới lọc, dữ liệu không được phép đã được materialize **bên trong server**. Dù caller cuối cùng chỉ nhận bản ghi hợp lệ, dữ liệu tạm thời vẫn có thể xuất hiện trong log/debug, serialization nhầm hoặc luồng xử lý phụ nếu code cấu trúc sai. Truy vấn visible rows giúp thu hẹp phạm vi dữ liệu xử lý.

Nếu endpoint hiển thị dữ liệu theo cấp quyền ở từng **trường** (field-level security), chỉ lọc hàng chưa đủ. Cần tạo DTO/redaction đúng policy; dữ liệu của quyền cao hơn không được cache chung với quyền thấp hơn.

### 11.4. Lỗi trong evaluator và fail closed

Nếu database/ACL tạm thời không phản hồi, đừng bắt exception và trả `true` để request vẫn hoạt động. Chính sách có thể trả `false` cho target/permission không được hỗ trợ, còn lỗi hạ tầng nên được báo/log an toàn và chuyển thành phản hồi phù hợp; **không bao giờ cấp quyền do lỗi tra cứu**.

## 12. Bảng lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Danh sách 100 item tạo 101 SQL | `@PostFilter` gọi evaluator query từng item | Đẩy điều kiện vào SQL hoặc batch allowed IDs |
| Tăng pool nhưng latency vẫn cao | Round-trip trên mỗi item không đổi | Giảm số query, đo plan/rows |
| Trang 20 phần tử chỉ còn 3 sau filter | Pagination trước authorization filtering | Filter quyền trong SQL rồi mới phân trang |
| `totalElements` lộ số bản ghi toàn tenant | COUNT không có cùng điều kiện quyền | Count theo visible predicate |
| User tenant T1 thấy tài liệu T2 | Query chỉ xét owner/grant hoặc tin tenant từ client | Kiểm tra tenant server-side trong chính SQL |
| Bỏ `@PostFilter` để tăng tốc và lộ dữ liệu | Query mới không có đủ predicate quyền | Contract test parity và fail closed |
| Query tối ưu trả record trùng | Join nhiều grant nhưng thiếu `DISTINCT` hoặc thiết kế sai | Dùng `EXISTS`/semi-join khi phù hợp |
| Cache quyền chia sẻ qua người dùng | Key chỉ có ID | Thêm principal/tenant/action/version, invalidation |
| Cache cold vẫn có N lookup | N ID khác nhau không trùng entry | Batch/SQL set-based thay vì trông chờ cache |
| Test số SQL sai khi chạy song song | Counter toàn cục hoặc startup query xen vào | Tracing per request/test, tách workload |
| `@PostFilter` không chạy | Self-invocation, bean `new`, chưa `@EnableMethodSecurity` | Gọi Spring proxy, integration test |
| Quyền bị thu hồi nhưng phép ghi vẫn chạy | Check ở thời điểm cũ, cache ACL stale | Recheck/conditional UPDATE trong transaction |
| `IN` query quá dài hoặc chậm | Batch ID vượt giới hạn DB | Chia batch, temp table hoặc table-valued parameters |
| Permission theo ACL phức tạp bị sai | Query `EXISTS` không phản ánh deny/inheritance/expiry | Đặc tả policy, test đầy đủ, policy service hoặc batch PDP |

## 13. Bài tập tự kiểm tra

1. **Có 500 tài liệu, `listAll()` gọi một SQL và evaluator gọi một SQL mỗi item. Tổng số lượt SQL là bao nhiêu?**  
   Khoảng `1 + 500 = 501` đối với pattern đơn giản ấy, chưa tính truy vấn khác.

2. **Vì sao `@PostFilter` có thể làm sai phân trang?**  
   Vì dữ liệu đã bị `LIMIT` rồi mới lọc theo quyền, làm thiếu item và có thể khiến số lượng thống kê không đúng.

3. **Nếu dùng `EXISTS` trong SQL, có mặc nhiên không còn chi phí authorization không?**  
   Không. DB vẫn phải đánh giá predicate; lợi ích là set-based processing và ít round-trip, cần xem query plan.

4. **Vì sao không dùng `Map<DocumentId, Boolean>` làm cache quyền chung?**  
   Vì quyết định còn phụ thuộc user, tenant, permission và thời điểm/quyền hiện tại; cache thiếu scope gây rò rỉ quyền.

5. **Một danh sách 1.000 ID hoàn toàn khác nhau có được cải thiện bằng request memoization không?**  
   Không nhiều khi mỗi ID chỉ xuất hiện một lần; batch query thường tốt hơn.

6. **Nếu không thể biểu diễn hết policy trong SQL, phương án nào thích hợp?**  
   Batch authorization API nhận danh sách ID, principal/tenant/action đáng tin, trả allowed IDs rồi lọc đúng semantics.

7. **Chỉ dùng `@PreAuthorize("hasAuthority('document:read')")` có bảo đảm mỗi bản ghi thuộc quyền người xem?**  
   Không. Nó kiểm tra năng lực tổng quát; còn cần tenant/owner/grant/ACL trên từng tài nguyên.

8. **Vì sao `@PreFilter` không tự phù hợp với mọi batch update?**  
   Vì phần tử không hợp lệ có thể bị loại âm thầm, khiến cập nhật một phần thay vì all-or-nothing.

9. **Vì sao test chỉ đo thời gian chạy một lần chưa đủ?**  
   Do cache, JIT, connection pool, warm-up, dữ liệu và query planner ảnh hưởng latency; cần cả số query, plan, load test và kết quả quyền đúng.

10. **Tối ưu hóa từ 7 query xuống 1 có chứng minh hệ thống an toàn chưa?**  
    Chưa. Cần kiểm tra cross-user/tenant, missing permission, principal giả, revoke, cache, phân trang và TOCTOU.

## 14. Tổng kết và tài liệu tham khảo

**Quy tắc vận dụng:**

- `PermissionEvaluator` kiểm tra từng item có thể tạo N lookup, nhất là với `@PostFilter`/`@PreFilter` và vòng lặp service.
- Với danh sách lớn, ưu tiên **SQL lọc quyền theo tập** hoặc **batch authorization**; không nhất thiết bỏ toàn bộ Method Security.
- Quyền tổng quát và quyền trên từng bản ghi là hai tầng khác nhau. User/tenant phải lấy từ identity đáng tin; owner/grant phải được xác minh trong nguồn dữ liệu server.
- Đúng về hiệu năng nhưng sai quyền là thất bại. Luôn đối chiếu kết quả giữa cách cũ và mới, cả allow lẫn deny.
- Pagination và COUNT phải đặt cùng predicate quyền; thao tác ghi phải xử lý concurrency và quyền thay đổi tại thời điểm update.
- Theo dõi N+1 bằng query count/tracing, không dựa duy nhất vào latency hoặc số phần tử trong response.

Tài liệu chính thức:

1. [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@PostFilter`, `filterObject`, `@PreAuthorize` và mô hình interceptor/proxy.
2. [Spring Security — PermissionEvaluator API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/access/PermissionEvaluator.html): hai overload, tham số `Authentication`, object/ID và permission.
3. [Spring Security — Testing Method Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html): `@WithMockUser`, `@WithAnonymousUser`.
4. [Spring Framework — Data Access with JDBC](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): `JdbcTemplate`, SQL parameters và row mapping.
5. [Spring Boot — SQL Databases](https://docs.spring.io/spring-boot/reference/data/sql.html): datasource, H2 và khởi tạo schema/data SQL.
6. [Spring Framework — AOP Proxying](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): ranh giới proxy và self-invocation.

**Điểm cần nhớ:** việc gọi `hasPermission` trên từng phần tử không sai, nhưng khi mỗi lần kiểm tra lại truy vấn DB thì một danh sách có N phần tử dễ tạo ra N+1 query. Cách sửa bền vững là **đưa quyền vào truy vấn dữ liệu hoặc kiểm tra quyền theo batch**, giữ nguyên ràng buộc người dùng/tenant/ACL và kiểm thử chính xác cả **kết quả được phép xem** lẫn **số truy vấn**.