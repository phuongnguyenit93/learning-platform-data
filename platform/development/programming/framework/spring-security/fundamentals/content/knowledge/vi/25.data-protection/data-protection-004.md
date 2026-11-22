# Kiểm tra quyền cho đọc, sửa, xóa và xuất dữ liệu như các thao tác riêng

> **Phạm vi:** Spring Security trên **Spring Boot MVC / Servlet**, Java 17+, trọng tâm **Bảo vệ dữ liệu**. Bài học xem READ, UPDATE, DELETE và EXPORT là **bốn hành động cần quyết định quyền độc lập**, đồng thời kiểm tra **đúng bản ghi, chủ sở hữu, tenant, trạng thái nghiệp vụ và dữ liệu thực tế được trả về**. Không chỉ kiểm tra người dùng “đã đăng nhập” hoặc có một vai trò chung.

## 1. Bài toán: một người có thể xem nhưng không được sửa, xóa hoặc xuất

Hãy tưởng tượng ứng dụng lưu các tài liệu kinh doanh. Người dùng có thể được phép mở tài liệu trong giao diện nhưng không được:

- **Sửa:** thay tiêu đề/nội dung hoặc thay thông tin nhạy cảm.
- **Xóa:** loại bỏ dữ liệu, có thể ảnh hưởng đối soát và khả năng truy vết.
- **Xuất:** tạo file CSV/XLSX/PDF chứa hàng loạt bản ghi, mang dữ liệu ra khỏi phạm vi kiểm soát thông thường.
- **Đọc bản ghi khác:** dù biết ID hoặc URL hợp lệ, vẫn không có quyền xem tài liệu ngoài tổ chức/tenant của họ.

Đây là hai chiều quyền cần kết hợp:

1. **Quyền chức năng (function-level):** người dùng có được thực hiện hành động READ, EDIT, DELETE, EXPORT nói chung hay không?
2. **Quyền đối tượng (object-level):** người dùng được thao tác trên **bản ghi cụ thể nào**, ở tenant nào, với vai trò/chủ sở hữu/trạng thái nào?

Công thức khái niệm:

```text
ALLOW(subject, action, resource, context)
    = authenticated(subject)
    AND hasCapability(subject, action)
    AND belongsToAllowedScope(subject, resource)
    AND businessRulesAllow(subject, action, resource, context)
```

Các điều kiện trên phải được kiểm tra **ở server**, trước khi dữ liệu bị tiết lộ hoặc thay đổi. Một button bị ẩn, route frontend bị disable hay việc dùng UUID khó đoán không thể thay cho kiểm tra này.

### Ma trận quyền mẫu

| Người dùng mẫu | Đọc bản ghi cùng tenant | Sửa bản ghi của mình | Xóa bản ghi của mình | Xuất danh sách cùng tenant |
| --- | --- | --- | --- | --- |
| Alice, quyền `DOC_READ` + `DOC_EDIT` + `DOC_DELETE` | Có | Có | Có | **Không**, thiếu `DOC_EXPORT` |
| Bob, quyền `DOC_READ` + `DOC_EXPORT` | Có | Không | Không | Có, trong tenant được phép |
| Carol, quyền đọc/sửa/xóa/xuất, tenant khác | Chỉ tenant của Carol | Theo quyền và sở hữu | Theo quyền và sở hữu | Chỉ tenant của Carol |
| Người chưa đăng nhập | Không | Không | Không | Không |

Đây là **chính sách ví dụ** để hiểu nguyên tắc. Ứng dụng thực có thể quy định “chỉ trưởng phòng được DELETE”, “EXPORT cần phê duyệt”, hoặc “bản ghi đã khóa không được UPDATE”. Điểm cốt lõi là **không tự suy ra EXPORT từ READ, DELETE từ EDIT, hoặc quyền đối tượng từ quyền truy cập menu**.

## 2. Phân biệt authentication, authorization và kiểm soát dữ liệu

- **Authentication:** xác định người gọi là ai (session, Basic, Bearer token, OAuth2...). `Authentication` của Spring Security thể hiện principal và authorities trong ngữ cảnh xác thực.
- **Request authorization:** chặn hoặc cho qua URL/method ở `SecurityFilterChain`, ví dụ chỉ người đã đăng nhập mới gọi `/api/documents/**`.
- **Method authorization:** áp điều kiện lên lời gọi service thông qua `@EnableMethodSecurity` và `@PreAuthorize`; rất hữu ích khi quyết định cần ID bản ghi.
- **Data authorization:** giới hạn **bản ghi được truy vấn/cập nhật/xóa/xuất**, lọc theo tenant/owner và quy tắc nghiệp vụ tại nơi làm việc với dữ liệu.
- **Data minimization:** ngay cả khi được READ, người dùng có thể chỉ được thấy một số field; dùng DTO/query projection thay vì lộ toàn bộ entity.
- **Audit và giám sát:** ghi ai đã thực hiện thao tác gì, khi nào, trên tài nguyên nào; không ghi nguyên nội dung nhạy cảm vào log.

Spring Security cho phép cấu hình quyền ở request và method; `@EnableMethodSecurity` **không được bật chỉ bằng việc thêm starter security**. Khi bật, `@PreAuthorize` được xử lý qua Spring AOP proxy đối với các Spring-managed beans.

### Đường đi kiểm tra cần có

```text
HTTP request
    |
    v
SecurityFilterChain: người gọi được xác thực?
    |
    v
Controller: parse và validate dữ liệu đầu vào
    |
    v
DocumentService: @PreAuthorize(action, documentId)
    |
    v
DocumentPolicy: capability + tenant + owner + business state
    |
    v
DocumentRepository: truy vấn/thao tác trong phạm vi hợp lệ
    |
    v
DTO hoặc CSV đã giảm thiểu dữ liệu
    |
    v
HTTP response
```

**Không chỉ kiểm tra ở controller.** Service có thể còn được gọi từ job, event listener, batch hoặc endpoint khác; nếu rule chỉ có ở một route, đường gọi khác có thể bỏ qua. Dù có `@PreAuthorize`, cần chú ý hiệu năng và race condition của kiểm tra trước thao tác DB (phần 10).

## 3. Xác định từng hành động và tài nguyên đích

### 3.1. READ: quyền nhìn thấy bản ghi

READ gồm xem chi tiết, tìm kiếm/list, xem preview, lấy attachment, xem lịch sử và các endpoint trả field dữ liệu. Phân quyền GET chi tiết nhưng quên search/list là lỗi phổ biến.

Ví dụ `GET /api/documents/a-1`:

1. Xác thực người gọi.
2. Kiểm tra `DOC_READ`.
3. Xác định tenant từ identity đáng tin; **không lấy tenant do client tự gửi mà tin ngay**.
4. Xác định bản ghi `a-1` thực sự thuộc tenant được phép.
5. Chỉ trả field mà người gọi cần.

READ không đồng nghĩa “được xem toàn bộ cột của bảng”. Có thể có `READ_METADATA`, `READ_CONTENT`, `READ_PII` hoặc field masking riêng khi dữ liệu nhạy cảm.

### 3.2. UPDATE: quyền thay đổi bản ghi và field

UPDATE thường cần quyền mạnh hơn READ. Kiểm tra:

- `DOC_EDIT` (quyền chức năng);
- người sở hữu bản ghi hoặc vai trò được phép sửa hộ;
- cùng tenant/phạm vi dự án;
- trạng thái bản ghi cho phép sửa (không khóa, không đã phê duyệt nếu nghiệp vụ cấm);
- **field nào được sửa** (không nhận ownerId, tenantId, role, approvedBy nếu không có rule phù hợp);
- concurrency/version để tránh cập nhật đè thay đổi của người khác.

Không dùng `BeanUtils.copyProperties(request, entity)` hoặc binding DTO trực tiếp vào entity có các field nhạy cảm mà không có allowlist. DTO nên chỉ khai báo field client có quyền thay.

### 3.3. DELETE: quyền hủy và hậu quả

DELETE thường cần authority **riêng** (`DOC_DELETE`), ngay cả người có EDIT cũng chưa chắc được xóa. Cần xem xét:

- soft delete so với hard delete, retention/legal hold;
- xóa document kéo theo attachment/cache/index/search hay không;
- có phải phê duyệt hoặc xác nhận lại với dữ liệu quan trọng không;
- idempotency, xử lý ID không tồn tại;
- audit event để biết ai thực hiện.

Dù API dùng `DELETE /api/documents/{id}`, **HTTP method không tự cấp quyền**. Rule phải kiểm tra method **và bản ghi cụ thể**.

### 3.4. EXPORT: quyền “mang dữ liệu ra” độc lập với READ

EXPORT có rủi ro khác GET một bản ghi: một request có thể tải hàng nghìn dòng, có PII, dữ liệu đã lọc nhầm, công thức spreadsheet độc hại, tên file không an toàn hoặc link chia sẻ tồn tại sau khi quyền bị thu hồi.

Kiểm tra tối thiểu:

1. Authority **`DOC_EXPORT` riêng**; không mặc định thừa kế từ `DOC_READ`.
2. Phạm vi tenant/dự án và các quyền đọc áp dụng cho **từng dòng/nhóm dòng**.
3. Giới hạn filter, số bản ghi, dung lượng, thời gian xử lý, tốc độ và số export đồng thời.
4. Chỉ xuất cột đã được phép; không xuất password hash, access token, secret, dữ liệu nội bộ không thuộc hợp đồng.
5. Audit người yêu cầu, loại dữ liệu, phạm vi, thời điểm và trạng thái job (tránh đưa nội dung file vào log).
6. Nếu export tạo file lưu lâu hoặc chạy async: kiểm tra quyền **khi yêu cầu, trong lúc tạo và khi tải**, với thời hạn lưu/link truy cập thích hợp.
7. Encode CSV và xử lý **formula injection** (chi tiết phần 9).

**Một list endpoint đã phân trang không thể được “nới” thành export toàn bộ chỉ bằng query `?pageSize=100000000`.** Định nghĩa một use case EXPORT riêng có hợp đồng, giới hạn và authorization riêng.

## 4. Thiết kế endpoint và status

| HTTP endpoint minh họa | Hành động | Kiểm tra cần thiết |
| --- | --- | --- |
| `GET /api/documents/{id}` | READ | `DOC_READ` + phạm vi bản ghi |
| `PUT /api/documents/{id}` | UPDATE | `DOC_EDIT` + owner/tenant + field allowlist |
| `DELETE /api/documents/{id}` | DELETE | `DOC_DELETE` + owner/tenant + chính sách xóa |
| `GET /api/documents/export` | EXPORT | `DOC_EXPORT` + `DOC_READ` + tenant + phép lọc dòng/cột |

**Status để client hiểu đúng:**

- **401 Unauthorized:** request chưa có authentication hợp lệ theo cơ chế API.
- **403 Forbidden:** đã xác thực nhưng không đủ quyền với hành động hoặc dữ liệu; CSRF cũng có thể dẫn tới 403.
- **404 Not Found:** tài nguyên không tồn tại, hoặc ứng dụng **cố ý che việc tài nguyên có tồn tại** khi chính sách yêu cầu.
- **400 Bad Request:** payload không hợp lệ; không dùng 400 thay mọi lỗi phân quyền.
- **409 Conflict:** có xung đột trạng thái/version trong trường hợp nghiệp vụ phù hợp.
- **204 No Content:** DELETE đã xử lý thành công và không trả body.

Không cố định mọi request sai quyền thành 404 hoặc 403 một cách máy móc. Chọn chính sách tránh tiết lộ sự tồn tại của bản ghi, ghi rõ contract và test nhất quán. Với demo dưới đây, policy từ chối thao tác trên ID không tồn tại bằng 403 vì kiểm tra `@PreAuthorize` diễn ra trước khi service lấy entity; đó là **quyết định minh họa**, không phải quy tắc HTTP chung.

## 5. Demo chạy được: một authority cho mỗi hành động, thêm tenant và owner

Ví dụ Spring Boot 3.x, Java 17+, Spring Security 6.x, Spring MVC, Spring Data JPA và H2. Người dùng và tenant được **khởi tạo trong server** để dễ học; không lấy `X-Tenant-ID` client gửi làm nguồn sự thật. Ví dụ chỉ dùng local để thử quyền, không có cơ chế provisioning, quản lý mật khẩu hoặc audit production.

Cấu trúc:

```text
document-security-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── resources/application.yml
    │   └── java/com/example/docsecurity/
    │       ├── DocumentSecurityApplication.java
    │       ├── SecurityConfig.java
    │       ├── TenantDirectory.java
    │       ├── DocumentEntity.java
    │       ├── DocumentRepository.java
    │       ├── DocumentPolicy.java
    │       ├── UpdateDocumentRequest.java
    │       ├── DocumentView.java
    │       ├── DocumentService.java
    │       └── DocumentController.java
    └── test/java/com/example/docsecurity/
        └── DocumentAuthorizationTest.java
```

### 5.1. Gradle build và cấu hình H2

Tệp `settings.gradle`:

```groovy
rootProject.name = 'document-security-demo'
```

Tệp `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
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
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Tệp `src/main/resources/application.yml`:

```yaml
spring:
  datasource:
    url: jdbc:h2:mem:docsecurity;DB_CLOSE_DELAY=-1
    username: sa
    password: ""
  jpa:
    hibernate:
      ddl-auto: create-drop
    open-in-view: false

server:
  error:
    include-message: never
```

Phiên bản plugin được **ghim để ví dụ có thể tái hiện trên môi trường hỗ trợ Gradle/Java 17**, không phải đề xuất triển khai một bản Spring Boot cũ lên production. Khi làm việc trên repo hiện có, dùng phiên bản và cách quản lý dependency đã được dự án chấp nhận, đồng thời cập nhật bản vá bảo mật.

### 5.2. Main class — `DocumentSecurityApplication.java`

```java
package com.example.docsecurity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DocumentSecurityApplication {
    public static void main(String[] args) {
        SpringApplication.run(DocumentSecurityApplication.class, args);
    }
}
```

### 5.3. Entity — `DocumentEntity.java`

```java
package com.example.docsecurity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "business_documents")
public class DocumentEntity {

    @Id
    private String id;

    @Column(name = "tenant_id", nullable = false)
    private String tenantId;

    @Column(name = "owner_username", nullable = false)
    private String ownerUsername;

    @Column(nullable = false, length = 120)
    private String title;

    @Version
    private Long version;

    protected DocumentEntity() {
    }

    public DocumentEntity(
            String id, String tenantId, String ownerUsername, String title) {
        this.id = id;
        this.tenantId = tenantId;
        this.ownerUsername = ownerUsername;
        this.title = title;
    }

    public String getId() {
        return id;
    }

    public String getTenantId() {
        return tenantId;
    }

    public String getOwnerUsername() {
        return ownerUsername;
    }

    public String getTitle() {
        return title;
    }

    public Long getVersion() {
        return version;
    }

    public void changeTitle(String newTitle) {
        this.title = newTitle;
    }
}
```

Chỉ `title` được cập nhật bằng method nghiệp vụ; client không có API setter cho `tenantId` hoặc `ownerUsername`. `@Version` hỗ trợ **optimistic locking** khi entity được cập nhật qua JPA, nhưng chỉ thêm annotation chưa đồng nghĩa có API hỗ trợ conditional update/ETag hoàn chỉnh; phía client cần hợp đồng version nếu muốn phát hiện xung đột từ UI.

### 5.4. Repository — `DocumentRepository.java`

```java
package com.example.docsecurity;

import java.util.List;

import org.springframework.data.jpa.repository.JpaRepository;

public interface DocumentRepository extends JpaRepository<DocumentEntity, String> {
    List<DocumentEntity> findByTenantIdOrderByIdAsc(String tenantId);
}
```

`findByTenantIdOrderByIdAsc(...)` quan trọng cho ví dụ export: truy vấn đã có **điều kiện tenant trong SQL**, thay vì đọc toàn bảng rồi tự lọc trong Java. Trên tập dữ liệu lớn, phải phân trang hoặc stream theo giới hạn tài nguyên; method trả `List` chỉ thích hợp với dữ liệu demo nhỏ.

### 5.5. Danh bạ tenant phía server — `TenantDirectory.java`

```java
package com.example.docsecurity;

import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component
public class TenantDirectory {

    private final Map<String, String> tenants = Map.of(
        "alice", "tenant-alpha",
        "bob", "tenant-alpha",
        "carol", "tenant-beta"
    );

    public String tenantFor(Authentication authentication) {
        if (authentication == null || !authentication.isAuthenticated()) {
            return null;
        }
        return tenants.get(authentication.getName());
    }
}
```

Trong production, danh bạ này phải thay bằng claims/định danh tenant đã được xác thực qua identity provider và kiểm chứng, hoặc lookup phía server có quản trị. **Không được** lấy tenant từ query/header hoặc form body rồi coi đó là quyền sở hữu. Người dùng có thể thuộc nhiều tenant; khi đó mô hình phải kiểm chứng tenant đang chọn có thuộc tập tenant được phép, và lại kiểm tra mỗi tài nguyên theo tenant đó.

### 5.6. Khai báo người dùng, quyền, SecurityFilterChain — `SecurityConfig.java`

```java
package com.example.docsecurity;

import java.util.List;

import org.springframework.boot.CommandLineRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/csrf").permitAll()
                .requestMatchers("/api/documents/**").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());

        // Giữ CSRF mặc định cho HTTP requests có khả năng dùng browser credentials.
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        var alice = User.withUsername("alice")
            .password(encoder.encode("demo-password"))
            .authorities("DOC_READ", "DOC_EDIT", "DOC_DELETE")
            .build();

        var bob = User.withUsername("bob")
            .password(encoder.encode("demo-password"))
            .authorities("DOC_READ", "DOC_EXPORT")
            .build();

        var carol = User.withUsername("carol")
            .password(encoder.encode("demo-password"))
            .authorities("DOC_READ", "DOC_EDIT",
                         "DOC_DELETE", "DOC_EXPORT")
            .build();

        return new InMemoryUserDetailsManager(alice, bob, carol);
    }

    @Bean
    CommandLineRunner seedDocuments(DocumentRepository repository) {
        return args -> {
            if (repository.count() == 0) {
                repository.saveAll(List.of(
                    new DocumentEntity(
                        "a-1", "tenant-alpha", "alice", "Budget Alpha"),
                    new DocumentEntity(
                        "a-2", "tenant-alpha", "bob", "Delivery Notes"),
                    new DocumentEntity(
                        "b-1", "tenant-beta", "carol", "Budget Beta")
                ));
            }
        };
    }
}
```

Đây là **demo với HTTP Basic** để dễ gọi/test; mật khẩu demo và H2 in-memory **không phù hợp production**. Khi dùng `curl -u`, chú ý shell history và process list; trên hệ thống thật không đặt mật khẩu nhạy cảm trực tiếp trong command line. Ứng dụng thực nên dùng TLS, hệ thống identity phù hợp, credential management và policy vận hành.

Ở đây URL guard chỉ yêu cầu xác thực; **quyền READ/EDIT/DELETE/EXPORT nằm ở method service**. Nhờ `@EnableMethodSecurity`, annotation `@PreAuthorize` mới có tác dụng. Nếu bỏ annotation này, các kiểm tra method sẽ không tự được bật chỉ vì có `spring-boot-starter-security`.

### 5.7. Policy: kiểm tra khả năng, tenant và owner — `DocumentPolicy.java`

```java
package com.example.docsecurity;

import java.util.Objects;

import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("documentPolicy")
public class DocumentPolicy {

    private final DocumentRepository repository;
    private final TenantDirectory tenants;

    public DocumentPolicy(
            DocumentRepository repository, TenantDirectory tenants) {
        this.repository = repository;
        this.tenants = tenants;
    }

    public boolean canRead(Authentication auth, String documentId) {
        return repository.findById(documentId)
            .map(doc -> canReadDocument(auth, doc))
            .orElse(false);
    }

    public boolean canEdit(Authentication auth, String documentId) {
        if (!has(auth, "DOC_EDIT")) {
            return false;
        }
        return repository.findById(documentId)
            .map(doc -> sameTenant(auth, doc) && (
                Objects.equals(doc.getOwnerUsername(), auth.getName())
                || has(auth, "DOC_ADMIN")
            ))
            .orElse(false);
    }

    public boolean canDelete(Authentication auth, String documentId) {
        if (!has(auth, "DOC_DELETE")) {
            return false;
        }
        return repository.findById(documentId)
            .map(doc -> sameTenant(auth, doc) && (
                Objects.equals(doc.getOwnerUsername(), auth.getName())
                || has(auth, "DOC_ADMIN")
            ))
            .orElse(false);
    }

    public boolean canExport(Authentication auth) {
        return has(auth, "DOC_EXPORT")
            && has(auth, "DOC_READ")
            && tenants.tenantFor(auth) != null;
    }

    public boolean canReadDocument(
            Authentication auth, DocumentEntity document) {
        return has(auth, "DOC_READ") && sameTenant(auth, document);
    }

    private boolean sameTenant(Authentication auth, DocumentEntity doc) {
        String userTenant = tenants.tenantFor(auth);
        return userTenant != null
            && Objects.equals(userTenant, doc.getTenantId());
    }

    private boolean has(Authentication auth, String authority) {
        return auth != null
            && auth.isAuthenticated()
            && auth.getAuthorities().stream()
                .anyMatch(a -> authority.equals(a.getAuthority()));
    }
}
```

Giải thích chi tiết:

- `canRead`: cần `DOC_READ` **và** đúng tenant. Vì thế Carol dù có quyền READ không thể đọc `a-1` của tenant-alpha.
- `canEdit`: cần `DOC_EDIT`, cùng tenant, **và** người sở hữu hoặc có `DOC_ADMIN`. Alice không thể sửa `a-2` của Bob dù cùng tenant.
- `canDelete`: kiểm tra `DOC_DELETE` **riêng**, không tái dùng `canEdit`. Trong sản phẩm thật, DELETE có thể còn bị chặn nếu bản ghi đã khóa.
- `canExport`: cần **đồng thời** `DOC_EXPORT` và `DOC_READ`, đồng thời có tenant phía server. Alice dù đọc/sửa/xóa được vẫn không thể export.
- `canReadDocument` được dùng lại khi tạo file để tránh export bản ghi ngoài phạm vi đọc. Truy vấn xuất cũng có điều kiện tenant để giảm khối lượng dữ liệu.
- `DOC_ADMIN` trong ví dụ chỉ là **ngoại lệ owner trong cùng tenant**; không vượt tenant và cũng không thay thế authority `DOC_EDIT`/`DOC_DELETE`. Muốn có superadmin vượt tenant phải định nghĩa và audit **một quy tắc mới**, không “ngầm hiểu admin là toàn năng”.

Dấu hiệu quyền đã tách đúng: thay đổi `DOC_EXPORT` không làm thay đổi khả năng READ/EDIT/DELETE. Thay đổi `DOC_DELETE` không làm tăng quyền sửa hoặc xem.

### 5.8. DTO nhập/xuất — `UpdateDocumentRequest.java`, `DocumentView.java`

Tệp `UpdateDocumentRequest.java`:

```java
package com.example.docsecurity;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record UpdateDocumentRequest(
    @NotBlank @Size(max = 120) String title
) {}
```

Tệp `DocumentView.java`:

```java
package com.example.docsecurity;

public record DocumentView(String id, String title) {}
```

Chỉ cho client sửa `title`: không có `tenantId`, `ownerUsername`, `version` hoặc `authorities` trong request body. Output chỉ trả `id` và `title`. Nếu cần thêm trường, mỗi field phải có lý do nghiệp vụ và chính sách đọc/ghi phù hợp.

### 5.9. Service thực thi quyền theo từng hành động — `DocumentService.java`

```java
package com.example.docsecurity;

import java.util.Objects;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DocumentService {

    private final DocumentRepository repository;
    private final DocumentPolicy policy;
    private final TenantDirectory tenants;

    public DocumentService(
            DocumentRepository repository,
            DocumentPolicy policy,
            TenantDirectory tenants) {
        this.repository = repository;
        this.policy = policy;
        this.tenants = tenants;
    }

    @PreAuthorize("@documentPolicy.canRead(authentication, #p0)")
    @Transactional(readOnly = true)
    public DocumentView read(String id) {
        return toView(requireDocument(id));
    }

    @PreAuthorize("@documentPolicy.canEdit(authentication, #p0)")
    @Transactional
    public DocumentView edit(String id, UpdateDocumentRequest request) {
        DocumentEntity doc = requireDocument(id);
        doc.changeTitle(request.title());
        return toView(doc);
    }

    @PreAuthorize("@documentPolicy.canDelete(authentication, #p0)")
    @Transactional
    public void delete(String id) {
        DocumentEntity doc = requireDocument(id);
        repository.delete(doc);
    }

    @PreAuthorize("@documentPolicy.canExport(authentication)")
    @Transactional(readOnly = true)
    public String exportCsv() {
        Authentication auth =
            SecurityContextHolder.getContext().getAuthentication();
        String tenant = Objects.requireNonNull(tenants.tenantFor(auth));

        StringBuilder csv = new StringBuilder("id,title\r\n");
        repository.findByTenantIdOrderByIdAsc(tenant).stream()
            .filter(doc -> policy.canReadDocument(auth, doc))
            .forEach(doc -> csv
                .append(csvCell(doc.getId()))
                .append(',')
                .append(csvCell(doc.getTitle()))
                .append("\r\n"));

        return csv.toString();
    }

    private DocumentEntity requireDocument(String id) {
        return repository.findById(id)
            .orElseThrow(() ->
                new IllegalStateException("Document not found after check"));
    }

    private DocumentView toView(DocumentEntity doc) {
        return new DocumentView(doc.getId(), doc.getTitle());
    }

    private String csvCell(String raw) {
        String normalized = raw == null ? "" :
            raw.replace("\r", " ").replace("\n", " ");
        String leading = normalized.stripLeading();

        // Giảm một số kiểu formula injection phổ biến trong CSV.
        if (!leading.isEmpty() && "=+-@".indexOf(leading.charAt(0)) >= 0) {
            normalized = "'" + normalized;
        }
        return "\"" + normalized.replace("\"", "\"\"") + "\"";
    }
}
```

**Vì sao dùng `#p0`?** Trong biểu thức `@PreAuthorize`, `#p0` chỉ tham số thứ nhất của method, ở đây là `id`. Cách này không phụ thuộc vào việc tên tham số Java được giữ trong bytecode bằng cờ compiler `-parameters`. Annotation gọi bean `documentPolicy`, truyền `authentication` từ security expression root và ID đang xử lý.

**Phân quyền khi nào?** Spring AOP proxy chặn method call trước khi thân service chạy. Nếu policy từ chối, service chưa đọc kết quả để trả client và chưa thay dữ liệu. Với app thực, chú ý việc `@PreAuthorize` gọi repository để kiểm tra đối tượng trước khi mở transaction nghiệp vụ; giao dịch, isolation và race cần thiết kế nhất quán (phần 10).

**Vì sao không return entity?** Entity còn tenant, owner, version và có thể thêm PII về sau. DTO `DocumentView` tạo hợp đồng hẹp hơn, giảm nguy cơ lộ dữ liệu khi schema DB phát triển.

**Vì sao có hai điều kiện tenant khi export?** `findByTenantIdOrderByIdAsc(tenant)` lọc ngay ở DB; `canReadDocument` nhắc lại quyền đọc từng bản ghi. Với policy phức tạp, truy vấn phải diễn đạt đúng phạm vi để không load dữ liệu không được phép vào memory; ví dụ này dùng hai lớp nhằm minh họa, không khuyến khích lọc hàng triệu hàng trong Java.

**Giới hạn code demo:** `exportCsv` dựng toàn bộ file trong RAM; chỉ dùng tập dữ liệu nhỏ. Với production, phân trang/stream đúng cách, đặt giới hạn rows/bytes, quota và xử lý tải xuống an toàn. Phương pháp thêm dấu nháy đơn cho ô bắt đầu như công thức là **giảm thiểu một số trường hợp CSV injection**, không bảo đảm an toàn tuyệt đối với mọi chương trình spreadsheet; xem phần 9.

`requireDocument` ném lỗi nếu bản ghi biến mất giữa lúc kiểm tra quyền và thao tác DB. Đó là ví dụ cố ý làm lộ khoảng cách **check–use**; production phải xử lý missing/race thành response phù hợp, không phơi stack trace. `@Version` giúp phát hiện xung đột update theo optimistic locking nhưng không tự giải quyết mọi race phân quyền.

### 5.10. HTTP Controller — `DocumentController.java`

```java
package com.example.docsecurity;

import java.nio.charset.StandardCharsets;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class DocumentController {

    private final DocumentService documents;

    public DocumentController(DocumentService documents) {
        this.documents = documents;
    }

    @GetMapping("/csrf")
    public CsrfToken csrf(HttpServletRequest request) {
        return (CsrfToken) request.getAttribute(CsrfToken.class.getName());
    }

    @GetMapping("/documents/{id}")
    public DocumentView read(@PathVariable String id) {
        return documents.read(id);
    }

    @PutMapping("/documents/{id}")
    public DocumentView update(
            @PathVariable String id,
            @Valid @RequestBody UpdateDocumentRequest request) {
        return documents.edit(id, request);
    }

    @DeleteMapping("/documents/{id}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void delete(@PathVariable String id) {
        documents.delete(id);
    }

    @GetMapping(value = "/documents/export", produces = "text/csv")
    public ResponseEntity<byte[]> export() {
        byte[] data = documents.exportCsv().getBytes(StandardCharsets.UTF_8);
        return ResponseEntity.ok()
            .header(HttpHeaders.CONTENT_DISPOSITION,
                    "attachment; filename=\"documents.csv\"")
            .header(HttpHeaders.CACHE_CONTROL, "no-store")
            .contentType(MediaType.parseMediaType("text/csv;charset=UTF-8"))
            .body(data);
    }
}
```

**Điểm kiểm tra:** controller gọi **bean service** qua proxy Spring để `@PreAuthorize` có hiệu lực. Controller chỉ nhận DTO và trả HTTP response. Đừng đặt logic quyền chính vào một `if (id.equals(...))` tại controller trong khi service có thể bị gọi từ nhiều nơi.

Tại `GET /api/csrf`, Spring Security cung cấp `CsrfToken` ở request attribute khi CSRF filter tham gia và token được tạo. Đây là cách minh họa để client giữ token trước khi gọi PUT/DELETE qua browser/cookie. API dùng HTTP Basic làm demo, nhưng vẫn **giữ CSRF được bật** để tránh vô tình đưa ra mẫu tắt bảo vệ cho browser credentials. Trong production cần quyết định CSRF theo cách xác thực thực tế.

### 5.11. Chạy chương trình

Trong thư mục chứa project, dùng Gradle tương thích (hoặc wrapper nếu đã tạo):

```bash
./gradlew test
./gradlew bootRun
```

Nếu tạo project mới chưa có `gradlew`, có thể chạy `gradle test` và `gradle bootRun` trên máy cài Gradle tương thích. Các class ví dụ **không phải các file độc lập để chạy `javac`/`java` mà không có dependency**; Gradle chuẩn bị classpath, Spring Boot tạo application context và H2 database. Không có stdout ứng dụng cố định; log khởi động phụ thuộc môi trường, dữ liệu demo nằm trong H2 in-memory.

Trên môi trường phát triển, request đọc bằng Basic Authentication:

```bash
# Alice đọc tài liệu a-1 (tenant-alpha): mong đợi 200.
curl -i -u alice:demo-password \
  http://localhost:8080/api/documents/a-1

# Carol thuộc tenant-beta thử đọc a-1: mong đợi 403.
curl -i -u carol:demo-password \
  http://localhost:8080/api/documents/a-1

# Alice có READ nhưng không có EXPORT: mong đợi 403.
curl -i -u alice:demo-password \
  http://localhost:8080/api/documents/export

# Bob có DOC_EXPORT và DOC_READ tại tenant-alpha: mong đợi 200 CSV.
curl -i -u bob:demo-password \
  http://localhost:8080/api/documents/export
```

Khi Bob export, nội dung chỉ có những tài liệu tenant-alpha thuộc quyền đọc, ví dụ `a-1` và `a-2`. Không có `b-1` của tenant-beta. Tên file trả về `documents.csv` và header `Cache-Control: no-store`. Header này chỉ hỗ trợ kiểm soát cache; không thay thế quy trình bảo vệ file sau khi người dùng đã tải xuống thiết bị.

Để thử PUT/DELETE với CSRF, dùng cookie jar và token trả từ endpoint `/api/csrf`. Bash có `curl` và `jq`:

```bash
# Bước 1: lấy token, giữ cùng cookie jar.
CSRF=$(curl -sS -u alice:demo-password \
  -b cookies.txt -c cookies.txt \
  http://localhost:8080/api/csrf | jq -r '.token')

# Bước 2: Alice sửa a-1 của chính mình: mong đợi 200.
curl -i -u alice:demo-password \
  -b cookies.txt -c cookies.txt \
  -X PUT http://localhost:8080/api/documents/a-1 \
  -H "X-CSRF-TOKEN: $CSRF" \
  -H "Content-Type: application/json" \
  -d '{"title":"Budget Alpha (Updated)"}'

# Bước 3: Alice thử sửa a-2 của Bob: mong đợi 403.
curl -i -u alice:demo-password \
  -b cookies.txt -c cookies.txt \
  -X PUT http://localhost:8080/api/documents/a-2 \
  -H "X-CSRF-TOKEN: $CSRF" \
  -H "Content-Type: application/json" \
  -d '{"title":"Unauthorized change"}'

# Bước 4: Alice xóa a-1 do mình sở hữu: mong đợi 204.
curl -i -u alice:demo-password \
  -b cookies.txt -c cookies.txt \
  -X DELETE http://localhost:8080/api/documents/a-1 \
  -H "X-CSRF-TOKEN: $CSRF"
```

Những lệnh có thể **thay đổi dữ liệu demo**, vì vậy chạy trên ứng dụng local đã seed dữ liệu test, không áp dụng bừa vào dịch vụ thật. Khi chạy bước 4, bản ghi `a-1` không còn trong database H2 của phiên chạy; muốn lặp lại từ đầu thì khởi động lại app trong cấu hình H2 in-memory ví dụ.

**Không hiểu nhầm 403 thiếu quyền với 403 thiếu CSRF:** nếu quên token, `CsrfFilter` có thể chặn trước khi service có cơ hội kiểm tra `DOC_EDIT` hoặc `DOC_DELETE`. Muốn kiểm thử authorization, hãy cấp CSRF hợp lệ.

## 6. Test chứng minh 4 hành động độc lập

Tệp `src/test/java/com/example/docsecurity/DocumentAuthorizationTest.java`. Dùng Spring Boot integration context, `MockMvc` và `spring-security-test`. `@Transactional` cho test hỗ trợ rollback các thay đổi trên luồng request đồng bộ MockMvc, giúp một test không ảnh hưởng dữ liệu nền của test khác.

```java
package com.example.docsecurity;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.annotation.Rollback;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.annotation.Transactional;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@Transactional
@Rollback
class DocumentAuthorizationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void anonymousCannotRead() throws Exception {
        mvc.perform(get("/api/documents/a-1"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void aliceCanReadButCannotExport() throws Exception {
        mvc.perform(get("/api/documents/a-1")
                .with(httpBasic("alice", "demo-password")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value("a-1"));

        mvc.perform(get("/api/documents/export")
                .with(httpBasic("alice", "demo-password")))
            .andExpect(status().isForbidden());
    }

    @Test
    void bobCanReadAndExportButCannotEditOrDelete() throws Exception {
        mvc.perform(get("/api/documents/a-1")
                .with(httpBasic("bob", "demo-password")))
            .andExpect(status().isOk());

        mvc.perform(get("/api/documents/export")
                .with(httpBasic("bob", "demo-password")))
            .andExpect(status().isOk())
            .andExpect(header().string("Cache-Control", "no-store"))
            .andExpect(content().contentTypeCompatibleWith("text/csv"))
            .andExpect(content().string(
                org.hamcrest.Matchers.containsString("a-1")));

        mvc.perform(put("/api/documents/a-2")
                .with(httpBasic("bob", "demo-password"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"Changed\"}"))
            .andExpect(status().isForbidden());

        mvc.perform(delete("/api/documents/a-2")
                .with(httpBasic("bob", "demo-password"))
                .with(csrf()))
            .andExpect(status().isForbidden());
    }

    @Test
    void aliceCanEditOwnDocumentButNotAnotherOwners() throws Exception {
        mvc.perform(put("/api/documents/a-1")
                .with(httpBasic("alice", "demo-password"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"Updated by Alice\"}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.title").value("Updated by Alice"));

        mvc.perform(put("/api/documents/a-2")
                .with(httpBasic("alice", "demo-password"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"Illegal update\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void carolCannotReadAcrossTenantEvenWithReadAuthority() throws Exception {
        mvc.perform(get("/api/documents/a-1")
                .with(httpBasic("carol", "demo-password")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/documents/b-1")
                .with(httpBasic("carol", "demo-password")))
            .andExpect(status().isOk());
    }

    @Test
    void aliceCanDeleteOwnDocument() throws Exception {
        mvc.perform(delete("/api/documents/a-1")
                .with(httpBasic("alice", "demo-password"))
                .with(csrf()))
            .andExpect(status().isNoContent());
    }

    @Test
    void missingCsrfRejectsMutationBeforeBusinessAuthorization() throws Exception {
        mvc.perform(put("/api/documents/a-1")
                .with(httpBasic("alice", "demo-password"))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"No csrf\"}"))
            .andExpect(status().isForbidden());
    }
}
```

**Vì sao test từng thao tác?** Nếu chỉ có test “Alice gọi GET được” thì vẫn chưa chứng minh UPDATE/DELETE/EXPORT an toàn. Bộ test kiểm tra **đủ cả chiều ngang (action) và chiều dọc (owner/tenant)**.

**Một lưu ý về status của tests:** ví dụ này sử dụng Spring Security method authorization được bật, nên lỗi thiếu `DOC_*` trả 403 trong trường hợp đã xác thực. Nếu đội ngũ chọn 404 để che sự tồn tại của tài nguyên, phải thay đổi cơ chế phản hồi một cách nhất quán và cập nhật assertions.

**Kiểm thử bổ sung cho sản phẩm thật:** cả GET list/search, phân trang, filter id do client chọn, batch edit/delete, attachment/preview, quyền qua GraphQL/websocket/job, kết quả export có đúng cột/dòng, và việc tải lại file đã export sau khi thu hồi quyền.

## 7. Vì sao kiểm tra URL đơn thuần chưa đủ?

Ví dụ cấu hình kiểu:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/documents/**")
        .hasAuthority("DOC_READ")
    .requestMatchers(HttpMethod.PUT, "/api/documents/**")
        .hasAuthority("DOC_EDIT")
    .requestMatchers(HttpMethod.DELETE, "/api/documents/**")
        .hasAuthority("DOC_DELETE")
    .anyRequest().denyAll()
);
```

Đoạn code trên là **mẫu minh họa request-level**, cần imports `HttpMethod` và `HttpSecurity` nếu đặt vào lớp cấu hình đầy đủ. Nó có hai vấn đề:

1. Một rule `GET /api/documents/**` quá rộng sẽ bao gồm cả `GET /api/documents/export`. Nếu không đặt rule **EXPORT riêng trước rule GET tổng quát**, người chỉ có READ có thể vượt qua kiểm tra tại URL. Service-level rule `DOC_EXPORT` vẫn có thể bảo vệ nếu được giữ.
2. Rule path/method **không biết** tài liệu `a-2` thuộc Bob hay `b-1` thuộc tenant khác, nên không thể tự kết luận người gọi được đọc/sửa/xóa tài liệu đó.

Khi muốn chặn sớm ở URL, cấu hình rõ path đặc biệt:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/documents/export")
        .hasAuthority("DOC_EXPORT")
    .requestMatchers(HttpMethod.GET, "/api/documents/**")
        .hasAuthority("DOC_READ")
    .requestMatchers(HttpMethod.PUT, "/api/documents/**")
        .hasAuthority("DOC_EDIT")
    .requestMatchers(HttpMethod.DELETE, "/api/documents/**")
        .hasAuthority("DOC_DELETE")
    .anyRequest().denyAll()
)
```

Đây là **lựa chọn thay thế request guard trong ví dụ**, không kết hợp hai đoạn `authorizeHttpRequests` không rõ thứ tự. Để bảo đảm `DOC_EXPORT` cũng phải có `DOC_READ`, có thể dùng biểu thức/manager phù hợp ở request layer hoặc để `@PreAuthorize` ở service kiểm tra **cả hai** như demo. **Không bỏ service-level check** sau khi thêm rule URL.

Thứ tự matcher quan trọng vì Spring Security chọn rule phù hợp theo thứ tự khai báo. Quy tắc cụ thể hơn như `/export` phải đứng trước `/**` rộng hơn. Quyền kiểm tra URL khác với quyền đối tượng sau khi đã giải ID trong DB.

## 8. Các lỗi bảo mật thực tế liên quan đến bốn thao tác

### 8.1. IDOR / BOLA: đổi ID trong URL

Người dùng Alice mở `/api/documents/a-1`, sau đó sửa URL thành `/api/documents/b-1`. Nếu server chỉ kiểm tra có login hoặc authority `DOC_READ` mà không kiểm tra tenant/owner phù hợp thì có thể tiết lộ dữ liệu. Đây là **Broken Object Level Authorization (BOLA)**, nổi bật trong OWASP API Security Top 10.

Đường đọc, sửa, xóa hay export nhận object ID từ client đều cần cùng nguyên tắc: **định danh object không phải bằng chứng về quyền**. Đừng tin ID tự tăng, UUID, slug hay ID đã ký nếu chính sách không xác thực quyền hiện tại.

### 8.2. BFLA: một quyền truy cập bị dùng cho nhiều chức năng

Ví dụ frontend ẩn nút “Export” nhưng endpoint `GET /export` chỉ kiểm tra `authenticated()`; người dùng có thể gọi API trực tiếp. Đó là lỗi **Broken Function Level Authorization**. Tránh biểu thức kiểu “ai có tài khoản là được tải tất cả”.

### 8.3. Mass assignment và field-level security

Ví dụ client gửi:

```json
{
  "title": "Updated",
  "tenantId": "tenant-beta",
  "ownerUsername": "attacker",
  "approved": true
}
```

Nếu backend bind thẳng payload lên JPA entity và lưu lại, người có EDIT title có thể chỉnh tenant/owner hoặc trạng thái phê duyệt. DTO có đúng **field allowlist** giúp tránh loại lỗi này. Ngoài ra, READ cần giới hạn output field để tránh excessive data exposure.

### 8.4. Export bỏ qua pagination/filter hoặc bypass chính sách đọc

Một sai lầm là UI chỉ cho xem 20 tài liệu nhưng export gọi `repository.findAll()` rồi tải hàng chục nghìn hàng. Phải áp cùng phạm vi nghiệp vụ vào query xuất, giới hạn bản ghi và kiểm tra `DOC_EXPORT`. Nếu export cho phép lọc theo id/status, bộ lọc đó **chỉ được thu hẹp** phạm vi được phép, không được làm rộng phạm vi ngoài tenant.

### 8.5. Soft delete và dữ liệu lưu trữ ngoài DB

Nếu DELETE được thực hiện bằng `deleted = true`, các truy vấn READ và EXPORT phải loại bản ghi đã xóa nếu chính sách yêu cầu. Nếu attachment đã được lưu ở object storage, người dùng không được tải qua URL công khai còn tồn tại sau khi quyền bị thu hồi. Kiểm tra quyền trên metadata chưa đủ khi link tải không đi qua authorization.

### 8.6. Export tiếp tục sau khi quyền bị thu hồi

Nếu người dùng được phép export lúc 10:00 và bị thu hồi quyền lúc 10:01, một export chạy 30 phút có thể vẫn tạo file. Cần thiết kế job snapshot, lịch kiểm quyền lại, thời hạn file và quyền ở endpoint tải; quyết định cụ thể phụ thuộc nghiệp vụ. Một **signed URL** có TTL không phải bản thay thế hoàn toàn cho quyền người dùng nếu nó có thể được chuyển tiếp cho người khác.

## 9. Xử lý CSV, XLSX, PDF và bảo vệ dữ liệu xuất

### 9.1. Đúng scope và cột trước khi tạo file

Quyết định về export nên có hai lớp riêng:

- **Eligibility:** ai được **yêu cầu export**, loại export nào, tenant nào, giới hạn bao nhiêu dòng.
- **Content authorization:** từng dòng/cột nào được đưa vào file. Một người có `DOC_EXPORT` không tự nhận quyền xem dữ liệu của tenant khác hoặc field riêng tư mà họ không được READ.

Khi export nhiều loại entity liên quan, ví dụ đơn hàng + người mua + thanh toán, không tự join rồi kéo theo PII người mua nếu hợp đồng chỉ cho xuất số đơn hàng.

### 9.2. CSV escaping khác với formula injection

CSV đúng cú pháp cần quote, escape dấu `"` thành `""` và xử lý ký tự xuống dòng. Nhưng **quote CSV không tự ngăn spreadsheet hiểu một ô là công thức**. Nếu một ô bắt đầu bằng `=`, `+`, `-`, `@` hoặc cách biểu diễn đặc biệt tùy app, chương trình spreadsheet có thể thực thi công thức khi mở file.

Đoạn `csvCell(...)` trong demo thay CR/LF thành khoảng trắng, thêm dấu `'` trước một số ô có dấu công thức ở đầu nội dung sau khoảng trắng, rồi CSV-quote mọi giá trị. Nó chỉ là **biện pháp minh họa giảm rủi ro**, không phải giải pháp chung cho mọi spreadsheet app hoặc mọi cách re-save/re-open CSV. Cần kiểm thử chính xác với ứng dụng người dùng mở file, xem hướng dẫn OWASP và ưu tiên **XLSX với cell được gán kiểu Text** khi muốn kiểm soát kiểu dữ liệu tốt hơn.

Tuyệt đối không coi việc loại bỏ một ký tự công thức duy nhất là giải pháp hoàn toàn; người tấn công có thể dùng tab/khoảng trắng, Unicode, dấu phân cách hoặc các khả năng của spreadsheet tùy môi trường.

### 9.3. Vòng đời file export

- Trả `Content-Disposition: attachment` với tên file an toàn, không đưa input client vào header thiếu kiểm tra.
- Đặt `Cache-Control` phù hợp dữ liệu nhạy cảm, dùng HTTPS.
- Giới hạn row count, bytes, số export đồng thời; dùng streaming/async job cho dữ liệu lớn.
- Lưu export vào vùng private, gắn người tạo/tenant/phạm vi, TTL, audit; xóa khi hết hạn.
- Kiểm tra quyền lại lúc tải; nếu dùng pre-signed URL phải có TTL ngắn và kiểm soát phát hành.
- Tránh PII/raw CSV trong access log, error log và email/thông báo nội bộ.
- Với PDF/XLSX, lưu ý metadata, hidden sheet/column, external links và thông tin ẩn cũng là dữ liệu cần phân quyền.

## 10. Phân quyền cùng lúc với giao dịch dữ liệu

### 10.1. Race condition giữa policy check và thao tác

`@PreAuthorize` kiểm tra trước body service. Nếu hệ thống khác có thể đổi tenant/owner/trạng thái bản ghi ngay sau lần kiểm tra nhưng trước update/delete, kiểm tra dựa trên snapshot cũ có thể không còn đúng. Ví dụ:

```text
T1: Alice có quyền sửa tài liệu a-1.
T1: canEdit(a-1) = true.
T2: Hệ thống chuyển a-1 cho Bob hoặc khóa tài liệu.
T1: UPDATE a-1 dựa trên quyết định cũ -> vi phạm policy mới.
```

Kỹ thuật thường dùng trong production:

1. Ràng buộc tenant/owner/trạng thái **trong cùng truy vấn UPDATE/DELETE có điều kiện**, kiểm tra số dòng ảnh hưởng.
2. Dùng transaction/isolation hoặc row-level locking phù hợp khi quy tắc đòi hỏi.
3. Dùng `@Version`/optimistic locking để phát hiện cập nhật đồng thời; trả lỗi conflict hoặc retry có kiểm soát, **không tự retry khi quyền đã thay đổi**.
4. Đảm bảo các field dùng trong authorization không được thay ngoài các use case được kiểm soát.
5. Với hệ thống đa tenant nghiêm ngặt, cân nhắc **database row-level security** như lớp bổ sung nếu DB hỗ trợ; context tenant đưa xuống DB phải đến từ nguồn đáng tin và được reset an toàn giữa các request.

Ví dụ ý tưởng SQL trong trường hợp chỉ owner được sửa:

```sql
UPDATE business_documents
SET title = :title
WHERE id = :id
  AND tenant_id = :authorized_tenant
  AND owner_username = :authenticated_user
  AND state = 'DRAFT';
```

Đoạn này **minh họa truy vấn ràng buộc scope**, không chạy trực tiếp với entity demo vì demo không có cột `state`. Trong code thực cần kiểm tra affected row count, xử lý optimistic version và trạng thái đúng, thay vì coi “không ném lỗi” là thao tác thành công.

### 10.2. Self-invocation có thể bỏ qua method security

`@PreAuthorize` hoạt động nhờ Spring AOP proxy. Nếu `DocumentService` có method nội bộ:

```java
public void unsafeInternalCall(String id) {
    this.delete(id);  // Cần xem lại: gọi trong cùng object có thể bỏ qua proxy
}
```

Đây chỉ là **mẫu cảnh báo**, không thêm vào demo. Lời gọi `this.delete(...)` từ cùng object không đi qua proxy như lời gọi từ controller sang service bean, nên annotation trên method đích **có thể không được thực thi ở nhánh self-invocation**. Tách ranh giới service/use case hoặc gọi qua một bean được proxy phù hợp, và vẫn đặt điều kiện an toàn ở data-access layer.

### 10.3. Không dựa vào thao tác “đã đọc” trước đó

Quyền đọc hôm qua không chứng minh quyền xóa hôm nay. Nếu UI gửi token “user đã xem tài liệu” hoặc client gọi GET thành công, backend vẫn phải kiểm tra quyền UPDATE/DELETE/EXPORT **tại thời điểm hành động**. Với quyền có thời hạn, trạng thái phê duyệt hoặc tenant membership thay đổi, kiểm tra mới là bắt buộc.

## 11. Export bất đồng bộ và batch operation

Ứng dụng lớn có thể tạo báo cáo async:

```text
POST /api/exports
   -> xác thực + DOC_EXPORT + valid filter + quota
   -> tạo ExportJob {requester, tenant, filter, permissions-context}

Background worker
   -> lấy job, xác minh scope còn hợp lệ theo chính sách
   -> đọc bằng truy vấn tenant-scoped, lọc dòng/cột
   -> tạo file private, scan nội dung/format nếu cần
   -> ghi audit, trạng thái COMPLETED/FAILED

GET /api/exports/{jobId}
   -> requester hoặc vai trò đặc quyền phù hợp mới xem trạng thái

GET /api/exports/{jobId}/download
   -> lại kiểm tra DOC_EXPORT, requester, tenant, TTL và quyền truy cập file
   -> stream file/URL thời hạn ngắn với kiểm soát phát hành
```

Đây là **kiến trúc tham khảo**, không phải phần mã đã triển khai ở demo. Background worker không mang theo `SecurityContextHolder` từ request thread một cách mặc định và an toàn. Lưu **định danh/requester, scope và policy context** dưới dạng được kiểm chứng; worker phải xác định quyền theo chính sách được chọn tại thời điểm chạy/tải. Đừng truyền raw bearer token dài hạn hoặc serialized `Authentication` vào queue rồi dùng tùy tiện.

Với bulk UPDATE/DELETE, không chỉ kiểm tra quyền cho ID đầu tiên. Phải xác minh **mọi** ID, áp quy tắc all-or-nothing hay partial success một cách rõ ràng, đặt giới hạn batch size và thực hiện transaction tương thích. Chỉ cần một bản ghi ngoài tenant lọt vào thao tác hàng loạt là vi phạm.

## 12. Trình tự test bảo mật nên bao phủ

Một ma trận đầy đủ cần thử không chỉ 4 method HTTP mà cả các đối tượng khác nhau:

| Người gọi / tài nguyên | READ | UPDATE | DELETE | EXPORT |
| --- | --- | --- | --- | --- |
| Chưa đăng nhập | Bị chặn | Bị chặn | Bị chặn | Bị chặn |
| Người có READ trong tenant | Cho phép bản ghi phù hợp | Bị chặn nếu thiếu EDIT | Bị chặn nếu thiếu DELETE | Bị chặn nếu thiếu EXPORT |
| Người có READ+EDIT, không sở hữu | Có thể đọc theo policy | Bị chặn sửa bản ghi không thuộc owner | Tách riêng | Tách riêng |
| Người có DELETE nhưng không EDIT | Quyết định độc lập theo READ | Bị chặn nếu thiếu EDIT | Chỉ cho phép DELETE đối tượng đúng scope | Tách riêng |
| Người có EXPORT nhưng thiếu READ | Không | Không | Không | Bị chặn nếu policy yêu cầu cả hai |
| Người thuộc tenant khác | Không thấy nội dung | Không đổi dữ liệu | Không xóa | Không có dòng tenant khác |
| Người có đủ authority, record locked | Theo policy READ | Thường bị chặn | Theo chính sách retention | Theo policy export riêng |
| Người gọi với CSRF không hợp lệ | GET đọc có thể hợp lệ theo auth | 403 trước khi tới service | 403 trước khi tới service | GET không dùng CSRF nhưng vẫn phải kiểm tra export |

Các test quan trọng khác:

- ID không tồn tại và ID tồn tại nhưng không được phép: quyết định 403/404 nhất quán, không lộ nội dung.
- UPDATE chứa field cấm `ownerUsername`, `tenantId`, `approved`: hệ thống bỏ qua hoặc từ chối theo contract, **không đổi** giá trị DB.
- EXPORT có filter để thử cross-tenant ID, pageSize cực lớn hoặc ký tự CSV gây formula injection.
- Request có nhiều ID: không dùng quyền của một ID để cho phép tất cả.
- Sau khi thu hồi quyền, không tải được file export có TTL dài hơn chính sách.
- Hai request đồng thời cập nhật/xóa: kiểm tra race, version conflict và transaction semantics.
- Gọi service trực tiếp qua Spring bean trong integration test: bảo đảm `@PreAuthorize` còn áp dụng ngoài controller.
- Thử các route khác cùng trả tài liệu: search, preview, attachment, history, “download original”, “print”, GraphQL, audit và admin API.
- Nếu dùng multi-tenant, thử cross-tenant cả READ, EDIT, DELETE và EXPORT với ID/UUID hợp lệ.

**Đừng dừng ở việc so status.** Với UPDATE/DELETE bị từ chối phải kiểm tra DB thực sự **không thay đổi**; với EXPORT phải kiểm tra file **không có dòng/cột bị cấm**, bởi một API trả 200 đúng đôi khi vẫn có data leak trong body.

## 13. Lỗi triển khai thường gặp

1. **Gom mọi thứ vào `hasRole("USER")`:** role chung chỉ nói người dùng có mặt trong hệ thống, không phân biệt thao tác.
2. **Cho quyền EXPORT bằng quyền READ:** hành động bulk download có rủi ro và chính sách riêng.
3. **Chỉ ẩn nút ở frontend:** client có thể gọi API bằng curl/Postman/script trực tiếp.
4. **Để `GET /export` khớp rule `GET /**` rộng:** cần rule cụ thể hoặc policy service độc lập, và đúng thứ tự request matcher.
5. **Chỉ check ID đã tồn tại:** ID không tạo ra quyền; phải check tenant/owner/business rule.
6. **Trả JPA entity trực tiếp:** entity có thể lộ tenant, internal flags hoặc secret fields khi thêm cột.
7. **Dùng request body để đổi tenant/owner tùy ý:** mass assignment/privilege escalation.
8. **Chạy `repository.findAll()` rồi lọc một ít trước export:** dễ lộ data và tốn tài nguyên; scope query tại DB.
9. **Dùng một method `canEdit` chung cho DELETE:** sẽ vô tình cho EDIT kéo theo quyền xóa.
10. **Quên check khi tải lại file export:** quyền có thể đã bị thu hồi sau khi job bắt đầu.
11. **Không để ý CSV formula injection:** file “chỉ chứa dữ liệu” có thể được spreadsheet diễn giải như công thức.
12. **Dựa hoàn toàn vào `@PreAuthorize` trên method bị gọi bằng `this.***:** self-invocation có thể bỏ qua proxy.
13. **Quên race giữa check và write:** quyền/trạng thái có thể thay đổi; cần transaction và điều kiện DB.
14. **Giả định chỉ `@EnableMethodSecurity` là đủ:** còn cần rule nghiệp vụ đúng; annotation không tự biết tenant/owner.
15. **Trả 401 khi người dùng đã xác thực nhưng thiếu quyền:** nhầm authentication với authorization; client có thể yêu cầu đăng nhập lại vô ích.
16. **Bỏ CSRF để test DELETE cho dễ:** khi browser gửi cookie tự động, có thể làm tăng rủi ro CSRF; viết test có token hợp lệ.
17. **Dùng một user “admin” vượt mọi tenant mà không audit:** ngoại lệ đặc quyền cần phạm vi, lý do và kiểm toán tường minh.
18. **Log nguyên title/body/CSV export:** audit nên ghi metadata thao tác và định danh phù hợp, tránh phát tán dữ liệu vào log.

## 14. Checklist trước khi triển khai tính năng dữ liệu mới

- [ ] Liệt kê READ, UPDATE, DELETE, EXPORT riêng, xác định authority và chính sách vai trò cho từng cái.
- [ ] Xác định resource ID, tenant, owner, trạng thái và quy tắc nghiệp vụ làm điều kiện quyết định.
- [ ] Kiểm tra quyền ở service/use case và phạm vi query DB, thay vì chỉ ở giao diện/URL.
- [ ] Mở `@EnableMethodSecurity` nếu dùng `@PreAuthorize`; kiểm thử gọi qua Spring proxy.
- [ ] Thiết kế DTO output và field allowlist input; không bind các trường hệ thống nhạy cảm.
- [ ] READ danh sách/search, preview và attachment đều lọc theo scope; không chỉ GET chi tiết.
- [ ] UPDATE có transaction, version/concurrency và bảo vệ field/state.
- [ ] DELETE có retention/soft-delete/attachment lifecycle, kiểm tra quyền riêng và audit.
- [ ] EXPORT cần authority riêng, query scoped, cột được phép, giới hạn và audit.
- [ ] CSV/XLSX/PDF được kiểm tra injection, metadata và bảo vệ file sau tải.
- [ ] Endpoint download của export job xác minh lại người gọi, tenant, TTL và quyền hiện hành theo policy.
- [ ] Test đủ ma trận action × user × tenant × owner × trạng thái, cả kết quả dữ liệu thực.
- [ ] Kiểm tra hành vi 401/403/404/409, CSRF, log và dữ liệu trả về.

### Câu hỏi tự kiểm tra

1. Vì sao người có `DOC_READ` không mặc định được `DOC_EXPORT`?
2. Alice có `DOC_EDIT` và biết ID của tài liệu tenant-beta. Còn thiếu điều kiện gì trước khi cho phép UPDATE?
3. Vì sao rule `GET /api/documents/**` có thể gây lỗi với `GET /api/documents/export`?
4. Khác biệt giữa request authorization tại `SecurityFilterChain` và kiểm tra đối tượng ở `@PreAuthorize`?
5. Vì sao test UPDATE bị chặn cần kiểm tra DB **không đổi**, không chỉ HTTP 403?
6. Một API trả `DocumentEntity` có rủi ro gì khi thêm field private vào DB?
7. Một export job được tạo trước khi quyền người dùng bị thu hồi; cần thiết kế gì để link tải không tiếp tục lộ dữ liệu?
8. `@PreAuthorize` trên method bị gọi qua `this.method()` có nguy cơ gì?
9. Vì sao `csvCell` thêm dấu `'` chỉ là biện pháp giảm thiểu, không bảo đảm an toàn tuyệt đối?
10. Điều gì sai nếu authorization dùng `tenantId` do client tự gửi mà không kiểm tra identity?
11. Vì sao `@Version` không tự thay thế việc kiểm tra quyền theo trạng thái bản ghi?
12. Khi nào một truy vấn `UPDATE ... WHERE tenant_id = ... AND owner = ...` có lợi hơn cách check trước rồi update?

**Gợi ý trả lời:** (1) xuất là bulk exfiltration, cần quyền chức năng riêng và scope đọc; (2) tenant, owner và state; (3) matcher rộng có thể nhận route export; (4) một bên kiểm tra request, bên kia có ID và policy dữ liệu; (5) ngăn việc handler trả đúng status nhưng mutation vẫn xảy ra; (6) overexposure; (7) recheck lúc tải, TTL/file ACL; (8) bypass AOP proxy; (9) spreadsheet apps xử lý CSV khác nhau; (10) attacker tự chọn tenant; (11) optimistic locking không xác nhận ai có quyền; (12) giảm cửa sổ check–use và ràng buộc scope ở DB.

## Tài liệu chính thức

- Spring Security — Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security — Authorize HTTP Requests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — Testing with MockMvc: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html
- Spring Security — CSRF: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- OWASP API Security Top 10 — API1 Broken Object Level Authorization: https://api-security.owasp.org/editions/2023/en/0xa1-broken-object-level-authorization/
- OWASP API Security Top 10 — API3 Broken Object Property Level Authorization: https://owasp.org/API-Security/editions/2023/en/0xa3-broken-object-property-level-authorization/
- OWASP — CSV Injection: https://owasp.org/www-community/attacks/CSV_Injection
- Spring Data JPA — Repositories: https://docs.spring.io/spring-data/jpa/reference/repositories.html
