# Quản trị từng tenant so với quản trị toàn hệ thống

> **Chủ đề:** Spring Security – authorization → **Cách ly tenant**. Bài học phân biệt **tenant administrator** (quản trị viên trong phạm vi một tổ chức/khách hàng) với **system administrator** (quản trị viên vận hành nền tảng), cách diễn đạt scope của quyền và ngăn truy cập chéo tenant. Ví dụ sử dụng Java 17+, Spring Boot 3.x, Spring Security 6.x, Spring Data JPA và H2. Phần bảo vệ sâu bằng database Row-Level Security (RLS) được trình bày riêng với cảnh báo về tài khoản đặc quyền và ngữ cảnh tenant.

## 1. Vấn đề: cùng tên “admin”, nhưng quản trị cái gì?

Giả sử một nền tảng SaaS dùng chung nhiều khách hàng:

~~~text
                      SaaS PLATFORM
        +----------------+----------------+
        |                |                |
     Tenant ACME      Tenant BETA     System Ops
        |                |                |
     Alice: admin      Bob: admin     Root: system admin
     Carol: member     David: member  Operations / billing
        |                |
     ACME documents    BETA documents
~~~

Yêu cầu nghiệp vụ:

- Alice có thể quản trị người dùng và tài liệu thuộc **ACME**, nhưng không được sửa dữ liệu của BETA.
- Bob có thể quản trị BETA, không được xem tài liệu ACME chỉ vì cùng mang role `TENANT_ADMIN`.
- Một người có thể là admin của **nhiều tenant** nếu có membership độc lập ở từng tenant.
- Root có quyền vận hành nền tảng (ví dụ theo dõi trạng thái, tạo tenant, cấu hình tính phí) nhưng **không tự động có quyền xem/sửa nội dung bí mật của mọi tenant**.
- Nếu thực sự cần can thiệp dữ liệu tenant để hỗ trợ sự cố, phải có **đường thao tác đặc quyền riêng** với phạm vi, lý do, phê duyệt hoặc step-up authentication, audit và cơ chế thu hồi.

Nguy cơ phổ biến là viết:

~~~java
// SAI trong nhiều hệ thống multi-tenant:
@PreAuthorize("hasRole('ADMIN')")
public void updateDocument(long id, String newTitle) {
    repository.findById(id).orElseThrow().rename(newTitle);
}
~~~

`hasRole('ADMIN')` chỉ trả lời user có authority `ROLE_ADMIN` theo prefix mặc định, **không nói user đang quản trị tenant nào**, và `findById(id)` không ràng buộc tenant. Nếu mọi tenant admin đều có `ROLE_ADMIN`, Alice có thể chỉnh tài liệu BETA khi đoán được ID.

**Nguyên tắc trung tâm:** quyền quản trị là tổ hợp **actor + action + resource + scope + điều kiện**, không chỉ là một chuỗi role.

## 2. Bốn lớp khái niệm không nên đánh đồng

| Khái niệm | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Identity** | Ai đang gọi? | Subject `user-17` đã được xác thực |
| **Role/authority** | Được phép thực hiện nhóm hành động nào? | `ROLE_TENANT_ADMIN`, `ROLE_SYSTEM_ADMIN` |
| **Scope/membership** | Quyền có hiệu lực tại tenant nào? | `user-17` là tenant admin của `acme`, không phải `beta` |
| **Resource ownership** | Tài nguyên thực sự thuộc tenant nào? | Document#202 có `tenant_id = beta` |
| **Conditions** | Có giới hạn bổ sung không? | MFA gần đây, ticket hỗ trợ, legal hold, trạng thái locked |

Nếu một actor có `ROLE_TENANT_ADMIN` nhưng không có membership quản trị trong tenant đích, thì **không đủ quyền**. Nếu actor là thành viên tenant nhưng chỉ có role VIEWER, cũng **không đủ quyền quản trị**. Chỉ khi các yếu tố đúng với nhau mới cho phép.

Ký hiệu:

~~~text
ALLOW tenant action khi:
  authenticated(actor)
  AND hasAuthority(actor, "ROLE_TENANT_ADMIN")
  AND activeMembership(actor, targetTenant, "ADMIN")
  AND resource.tenantId == targetTenant
  AND satisfiesBusinessConditions(resource, action)
~~~

Với system action:

~~~text
ALLOW system operation khi:
  authenticated(actor)
  AND hasAuthority(actor, "ROLE_SYSTEM_ADMIN")
  AND operation thuộc tập system-operation được định nghĩa
  AND stepUp / approval / audit nếu operation yêu cầu
~~~

Hai biểu thức **khác nhau**. Không thêm `OR hasRole('SYSTEM_ADMIN')` vào mọi endpoint của tenant theo thói quen. Quyền vận hành hệ thống có thể tách khỏi quyền xem dữ liệu khách hàng để áp dụng **least privilege**.

## 3. Ma trận quyền: tenant admin so với system admin

| Hành động | Tenant admin ACME | Tenant admin BETA | System admin mặc định |
| --- | --- | --- | --- |
| Xem tài liệu thuộc ACME | Theo chính sách ACME | Không | **Không mặc nhiên** |
| Đổi tên tài liệu thuộc ACME | Có nếu policy cho phép | Không | **Không mặc nhiên** |
| Quản trị membership ACME | Có, với giới hạn cấp quyền | Không | Theo workflow riêng |
| Quản trị membership BETA | Không | Có | Theo workflow riêng |
| Cấp role `ROLE_SYSTEM_ADMIN` | **Không** | **Không** | Chỉ qua control plane đặc quyền |
| Tạo tenant mới | Không (mặc định) | Không (mặc định) | Có nếu được phân công |
| Đọc metric hạ tầng toàn hệ thống | Không | Không | Có theo quyền vận hành |
| Xem nội dung tài liệu BETA để hỗ trợ sự cố | Không | Theo policy BETA | Chỉ khi có **break-glass** được kiểm soát |
| Đổi tenantId của tài nguyên | Không tự ý | Không tự ý | Chỉ workflow migration có kiểm soát |
| Xem báo cáo tổng hợp không nhận dạng dữ liệu | Có thể theo tenant | Có thể theo tenant | Có theo nhiệm vụ |
| Xóa toàn bộ tenant | Không mặc định | Không mặc định | Chỉ workflow đặc biệt, có xác minh |

Đây là **một policy đề xuất cho hệ thống SaaS**, không phải hành vi tự động của Spring Security. Framework cung cấp cơ chế thực thi quyết định; ứng dụng phải định nghĩa chính xác ai được làm gì trên phạm vi nào.

### 3.1. Cùng role không có nghĩa cùng quyền

~~~text
Alice: ROLE_TENANT_ADMIN + adminMembership(ACME)
Bob:   ROLE_TENANT_ADMIN + adminMembership(BETA)

hasRole("TENANT_ADMIN") đều true.
canAdministerTenant("acme") chỉ Alice true.
canAdministerTenant("beta") chỉ Bob true.
~~~

`ROLE_TENANT_ADMIN` là **loại khả năng**; membership cụ thể mới xác định **phạm vi**.

### 3.2. Một user có thể quản trị nhiều tenant

Ví dụ Sam:

~~~text
Sam: ROLE_TENANT_ADMIN
Membership:
  (sam, acme, ADMIN, active=true)
  (sam, beta, ADMIN, active=true)
~~~

Sam có thể chuyển ngữ cảnh điều hành giữa ACME/BETA, nhưng mỗi request vẫn phải chỉ rõ tenant đang thao tác và hệ thống kiểm tra membership tương ứng. Việc Sam quản trị hai tenant **không** cho phép sao chép dữ liệu giữa hai tenant mà thiếu policy nghiệp vụ.

### 3.3. System admin không phải “tenant admin của tất cả tenant”

Một system admin có thể được giao nhiệm vụ bảo trì hạ tầng, billing, provisioning hay incident response mà không cần biết nội dung từng tài liệu. Việc thêm wildcard permission `tenant=*` cho mọi system admin tăng phạm vi thiệt hại khi tài khoản bị chiếm đoạt. Mẫu an toàn là:

- **Control plane**: API quản trị hạ tầng, tenants, pricing, trạng thái dịch vụ.
- **Data plane**: API đọc/sửa/xóa dữ liệu của một tenant.
- **Break-glass plane**: đường hỗ trợ dữ liệu đặc biệt, bật theo thời hạn, có duyệt và audit.

Đây là tách lớp logic; có thể triển khai ở các microservice hoặc trong một ứng dụng modular monolith. Quan trọng là kiểm tra đúng policy ở từng boundary.

## 4. TenantId trong URL là selector, không phải bằng chứng quyền

Một endpoint dễ gặp:

~~~text
PATCH /api/tenants/acme/documents/101
Authorization: Bearer <token>
Body: {"title":"Reviewed"}
~~~

Người dùng có thể sửa đường dẫn thành:

~~~text
PATCH /api/tenants/beta/documents/202
~~~

`tenantId=beta` chỉ là **đối tượng mà caller yêu cầu thao tác**. Nó không chứng minh caller thuộc BETA.

Đúng:

~~~text
1. Xác thực token/session → principal ID tin cậy.
2. Đọc tenantId từ path để biết target.
3. Kiểm tra actor đang có membership ADMIN tại target tenant.
4. Tải document bằng (id, tenantId), không chỉ bằng id.
5. Kiểm tra trạng thái/nghiệp vụ rồi thao tác trong transaction.
6. Audit actor, target tenant, object và action.
~~~

Sai:

~~~java
// PHẢN VÍ DỤ: tin request tự khai.
String tenantId = request.getHeader("X-Tenant");
if (request.getRole().equals("TENANT_ADMIN")) {
    repository.findById(documentId).orElseThrow().rename(title);
}
~~~

Header, query, body và path do client cung cấp là **untrusted selectors** trừ khi được đối chiếu với nguồn xác thực. Ngay cả nếu tenant được nhúng trong JWT đã ký, cần kiểm tra người gọi có active membership cho tenant đích; token có thể stale sau khi bị thu hồi membership.

## 5. Kiến trúc nhiều tầng: chặn quyền rồi vẫn ràng buộc dữ liệu

~~~text
HTTP Request
    |
    v
Authentication (JWT/session đã verify)
    |
    v
Controller / request routing
    |
    v
Method Security (@PreAuthorize)
    |
    v
TenantPolicy
  |-- ROLE_TENANT_ADMIN?
  |-- active ADMIN membership tại target tenant?
    |
    v
Application Service (@Transactional)
    |
    v
Repository query ràng buộc tenant_id
    |
    v
Database (tenant_id + optional RLS)
~~~

Một hệ thống an toàn phải tránh tình trạng:

~~~text
Method Security đã kiểm tra membership ACME
nhưng Repository lại findById(202) không lọc tenant
→ vẫn có nguy cơ đọc/sửa row BETA.
~~~

**Defense in depth:** authorization ở service và ràng buộc tenant ở truy vấn là hai chốt độc lập. Với PostgreSQL, Row-Level Security còn có thể là lớp chặn ở DB nếu được cấu hình đúng; nhưng không thay thế việc kiểm soát identity và request scope.

### 5.1. Đặt chốt ở service chứ không chỉ ở controller

Nếu ứng dụng có REST controller, GraphQL resolver, message consumer, scheduled job hoặc CLI admin task cùng gọi repository, chốt riêng ở HTTP controller không bảo vệ các đường gọi khác. Đặt logic tenant authorization tại **application service boundary** để mọi điểm vào cùng đi qua.

### 5.2. Không dựa vào `ThreadLocal tenantId` từ request chưa verify

Một số ORM filter hoặc `CurrentTenantIdentifierResolver` dùng tenant context. Nếu tenant context được đặt từ header chưa xác minh, nó có thể làm hệ thống lọc sang dữ liệu của tenant khác. Mỗi request/job phải thiết lập tenant context từ lựa chọn đã được **authorize** và dọn dẹp trong `finally`/context boundary để tránh lây sang request tiếp theo.

### 5.3. Không dùng ID của tenant khác để suy ra sự tồn tại

Nếu ACME admin hỏi Document#202 của BETA, service nên trả generic “not available / denied” theo contract để không lộ tên tenant hoặc owner. Việc map thành HTTP 403 hay 404 cần nhất quán với chính sách chống enumeration. Không tự trả mọi thông tin metadata của tài nguyên trái quyền trong error message.

## 6. Ví dụ Spring Boot 3.x, Java 17+: kiểm tra role và membership riêng

Chúng ta dựng một ứng dụng nhỏ có:
- Tenant membership của Alice, Bob và Sam trong một directory server-side **demo**.
- Tài liệu lưu trong H2 có `tenantId`.
- Một method chỉnh sửa tài liệu của tenant, chỉ cho phép tenant admin của tenant đó.
- Một method report toàn hệ thống riêng, chỉ cho system admin.
- Integration tests qua Spring proxy chứng minh tenant admin không truy cập chéo tenant, system admin không tự có quyền sửa tenant document.

Ứng dụng này không cần tạo HTTP endpoint. Test gọi trực tiếp Spring-managed service để kiểm tra Method Security, repository và transaction. Mã Java dùng package `demo.tenancy`.

### 6.1. Dependencies

Trong dự án Spring Boot Gradle đã có plugin Java, Spring Boot và dependency management cùng phiên bản tương thích, bổ sung:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Không thêm trực tiếp phiên bản Security không tương thích với Boot 3.x. `@EnableMethodSecurity` sẽ được khai báo trong application class; starter Security một mình **không tự** bật method authorization.

### 6.2. H2 dành cho integration test

**`src/test/resources/application.properties`**

~~~properties
spring.datasource.url=jdbc:h2:mem:tenant_scope;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
spring.jpa.show-sql=false
~~~

`create-drop` và H2 in-memory chỉ thích hợp demo/test. Production cần schema migration, row isolation/transaction/locking của database đích và index theo tenant, ví dụ `(tenant_id, id)` cho truy vấn đúng phạm vi.

### 6.3. Main application

**`src/main/java/demo/tenancy/TenantAdminApplication.java`**

~~~java
package demo.tenancy;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@SpringBootApplication
@EnableMethodSecurity
public class TenantAdminApplication {
    public static void main(String[] args) {
        SpringApplication.run(TenantAdminApplication.class, args);
    }
}
~~~

### 6.4. Entity lưu tenant rõ ràng

**`src/main/java/demo/tenancy/TenantDocument.java`**

~~~java
package demo.tenancy;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "tenant_documents")
public class TenantDocument {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 32, updatable = false)
    private String tenantId;

    @Column(nullable = false, length = 160)
    private String title;

    @Version
    private Long version;

    protected TenantDocument() {
        // JPA constructor
    }

    public TenantDocument(String tenantId, String title) {
        this.tenantId = tenantId;
        this.title = title;
    }

    public Long getId() {
        return id;
    }

    public String getTenantId() {
        return tenantId;
    }

    public String getTitle() {
        return title;
    }

    public Long getVersion() {
        return version;
    }

    public void rename(String newTitle) {
        this.title = newTitle;
    }
}
~~~

`tenantId` được gán khi tạo tài liệu qua use case đã authorize. `updatable=false` ở demo thể hiện không cho đổi tenant qua update entity thông thường; đây **không** thay thế một policy tenant migration. `@Version` hỗ trợ optimistic locking cho entity lifecycle, không bảo đảm tất cả bulk JPQL updates cùng tuân theo version.

### 6.5. Repository luôn có điều kiện tenant khi truy cập data plane

**`src/main/java/demo/tenancy/TenantDocumentRepository.java`**

~~~java
package demo.tenancy;

import java.util.List;
import java.util.Optional;
import jakarta.persistence.LockModeType;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface TenantDocumentRepository
        extends JpaRepository<TenantDocument, Long> {

    List<TenantDocument> findAllByTenantIdOrderByIdAsc(String tenantId);

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("""
            select d from TenantDocument d
             where d.id = :id and d.tenantId = :tenantId
            """)
    Optional<TenantDocument> lockByIdAndTenant(
            @Param("id") Long id,
            @Param("tenantId") String tenantId);
}
~~~

`lockByIdAndTenant` kết hợp object ID với tenant ID trong **cùng truy vấn**; nếu Alice đang thao tác ACME nhưng gửi ID của tài liệu BETA, không có row được trả về. `PESSIMISTIC_WRITE` giảm nguy cơ thay đổi dữ liệu giữa đọc và ghi trong một transaction, tùy cơ sở dữ liệu.

`JpaRepository.findById(id)` vẫn là API có thể được gọi tại chỗ khác; **không** cho rằng repository toàn hệ thống tự an toàn. Quy tắc review là code ở data plane cần chỉ rõ tenant predicate hoặc dùng một cơ chế RLS/tenant-filter được kiểm soát, có test chống quên điều kiện.

### 6.6. Membership directory tin cậy ở phía server

**`src/main/java/demo/tenancy/TenantMemberships.java`**

~~~java
package demo.tenancy;

import java.util.Map;
import java.util.Set;
import org.springframework.stereotype.Component;

@Component
public class TenantMemberships {

    // Demo: membership ADMIN được cấp bởi phía server.
    // Production: truy vấn membership table/IAM, kèm active/revoked status.
    private final Map<String, Set<String>> adminTenants = Map.of(
            "alice", Set.of("acme"),
            "bob", Set.of("beta"),
            "sam", Set.of("acme", "beta"));

    public boolean isAdminOf(String subjectId, String tenantId) {
        return adminTenants
                .getOrDefault(subjectId, Set.of())
                .contains(tenantId);
    }
}
~~~

Tập dữ liệu cố định này **không** phải cơ chế quản trị membership production. Nó giúp JUnit chứng minh trường hợp user có role nhưng không có membership và user có membership nhưng không có role. Trong hệ thống thật, `subjectId` nên là ID bất biến toàn cục từ token/identity provider đã xác thực; membership nên có status, valid-from/to, scope, audit và chiến lược thu hồi.

### 6.7. Policy bean kiểm tra cả loại role lẫn phạm vi

**`src/main/java/demo/tenancy/TenantPolicy.java`**

~~~java
package demo.tenancy;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("tenantPolicy")
public class TenantPolicy {

    private final TenantMemberships memberships;

    public TenantPolicy(TenantMemberships memberships) {
        this.memberships = memberships;
    }

    public boolean canManageTenant(
            Authentication authentication,
            String tenantId) {

        return validActor(authentication)
                && validTenantId(tenantId)
                && hasAuthority(authentication, "ROLE_TENANT_ADMIN")
                && memberships.isAdminOf(
                        authentication.getName(), tenantId);
    }

    public boolean canOperateSystem(Authentication authentication) {
        return validActor(authentication)
                && hasAuthority(authentication, "ROLE_SYSTEM_ADMIN");
    }

    private boolean validActor(Authentication authentication) {
        return authentication != null
                && authentication.isAuthenticated()
                && !(authentication instanceof AnonymousAuthenticationToken);
    }

    private boolean validTenantId(String tenantId) {
        return tenantId != null
                && tenantId.matches("[a-z][a-z0-9-]{1,31}");
    }

    private boolean hasAuthority(Authentication authentication, String name) {
        return authentication.getAuthorities().stream()
                .anyMatch(a -> name.equals(a.getAuthority()));
    }
}
~~~

**Hai quyết định hoàn toàn tách biệt:**

- `canManageTenant(auth, tenantId)` yêu cầu `ROLE_TENANT_ADMIN` **và** membership tại đúng tenant đích. Không có shortcut “system admin thì true”.
- `canOperateSystem(auth)` yêu cầu `ROLE_SYSTEM_ADMIN` cho action thuộc control plane. Method này không nhận tenantId, không tự cấp quyền cho mọi bản ghi.

`validTenantId` chỉ xác minh **định dạng canonical** của tenant ID mẫu; nó **không** xác thực một tenant đang tồn tại và không chứng minh caller có quyền. Membership mới là một thành phần trong quyết định quyền.

Vai trò/authority ở production phải phát từ một Authentication đã verify, không lấy từ JSON body/header do client tự khai. Có thể dùng `RoleHierarchy` nhưng phải test kỹ: tự động khiến `ROLE_SYSTEM_ADMIN` được suy ra `ROLE_TENANT_ADMIN` **không** được biến system admin thành admin mọi tenant, và membership check vẫn là bắt buộc.

### 6.8. Service chỉ sửa trong tenant đã được xác minh

**`src/main/java/demo/tenancy/TenantDocumentService.java`**

~~~java
package demo.tenancy;

import java.util.List;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TenantDocumentService {

    public record DocumentView(Long id, String tenantId, String title) {
    }

    private final TenantDocumentRepository repository;

    public TenantDocumentService(TenantDocumentRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize(
            "@tenantPolicy.canManageTenant(authentication, #tenantId)")
    @Transactional(readOnly = true)
    public List<DocumentView> listWithinTenant(
            @P("tenantId") String tenantId) {

        return repository.findAllByTenantIdOrderByIdAsc(tenantId)
                .stream()
                .map(d -> new DocumentView(
                        d.getId(), d.getTenantId(), d.getTitle()))
                .toList();
    }

    @PreAuthorize(
            "@tenantPolicy.canManageTenant(authentication, #tenantId)")
    @Transactional
    public void renameWithinTenant(
            @P("tenantId") String tenantId,
            Long documentId,
            String title) {

        if (title == null || title.isBlank() || title.length() > 160) {
            throw new IllegalArgumentException("Invalid title");
        }

        TenantDocument document = repository.lockByIdAndTenant(
                documentId, tenantId)
                .orElseThrow(() ->
                        new AccessDeniedException("Document not available"));

        document.rename(title);
        repository.flush();
    }
}
~~~

**Phân tích đường đi:**

1. `@PreAuthorize` gọi `TenantPolicy` qua tên bean `tenantPolicy`, lấy Authentication do Spring Security cung cấp và giá trị `#tenantId`.
2. `@P("tenantId")` giúp SpEL tìm tham số mà không phụ thuộc compiler flag `-parameters`.
3. Nếu caller không là admin của tenant đích, Method Security ném `AccessDeniedException` trước khi vào body.
4. Method service tiếp tục truy vấn bằng **cả** `documentId` và `tenantId`. Nếu ID thuộc tenant khác, nó không được trả về.
5. `@Transactional` bao thao tác ghi. `@Version` hỗ trợ phát hiện cạnh tranh ở entity lifecycle; `PESSIMISTIC_WRITE` yêu cầu DB lock row được chọn.
6. Dữ liệu trả về qua `DocumentView` chỉ gồm những rows đã scope theo tenant. Không trả JPA entity lazy graph có thể chứa quan hệ sang tenant khác.

Trong demo, `title` là field không quá nhạy cảm và không có external side effects. Nếu service thêm chia sẻ, gửi thông báo, xóa file, cần bảo vệ quyền cho từng action và điều phối side effect sau commit/outbox. Một check READ không tự cấp quyền DELETE.

### 6.9. System operation nằm ở service riêng

**`src/main/java/demo/tenancy/SystemOperationsService.java`**

~~~java
package demo.tenancy;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class SystemOperationsService {

    private final TenantDocumentRepository repository;

    public SystemOperationsService(TenantDocumentRepository repository) {
        this.repository = repository;
    }

    // Ví dụ một metric vận hành được cho phép ở control plane.
    @PreAuthorize("@tenantPolicy.canOperateSystem(authentication)")
    @Transactional(readOnly = true)
    public long globalDocumentCount() {
        return repository.count();
    }
}
~~~

`globalDocumentCount()` là một action được cấp riêng cho system admin, trả về **số lượng tổng hợp**, không tự cấp quyền xem từng tài liệu hoặc sửa mọi document. Trong production, cả số liệu tổng hợp cũng có thể nhạy cảm; nên áp dụng policy và audit phù hợp.

**Không làm**:

~~~java
// PHẢN VÍ DỤ: mọi system admin vô tình vượt tenant checks.
@PreAuthorize("""
    hasAuthority('ROLE_SYSTEM_ADMIN') or
    @tenantPolicy.canManageTenant(authentication, #tenantId)
    """)
public void changeTenantDocument(String tenantId, Long id) {
    repository.findById(id).orElseThrow().rename("changed");
}
~~~

Nếu một system administrator **thực sự** cần sửa tài liệu để khắc phục sự cố, tạo một method/endpoint khác như `emergencyChangeForTenant(...)`, với bước duyệt/thời hạn/ticket/MFA và audit; không giấu quyền vượt scope trong một OR expression ở API bình thường.

## 7. Integration tests: cùng role khác tenant và system admin không tự bypass

Test dùng `@SpringBootTest` với H2, Spring Security Method Security và JPA thật. `@WithMockUser` gán principal/authorities cho từng test; nó không thực hiện xác thực password hay ký JWT. Các service lấy qua Spring Context để annotation/proxy được áp dụng.

**`src/test/java/demo/tenancy/TenantAuthorizationTest.java`**

~~~java
package demo.tenancy;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithAnonymousUser;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest(classes = TenantAdminApplication.class)
class TenantAuthorizationTest {

    @Autowired TenantDocumentRepository repository;
    @Autowired TenantDocumentService tenantService;
    @Autowired SystemOperationsService systemService;

    private Long acmeId;
    private Long betaId;

    @BeforeEach
    void seed() {
        repository.deleteAll();
        repository.flush();

        acmeId = repository.saveAndFlush(
                new TenantDocument("acme", "ACME-original")).getId();
        betaId = repository.saveAndFlush(
                new TenantDocument("beta", "BETA-original")).getId();
    }

    private String title(Long id) {
        return repository.findById(id).orElseThrow().getTitle();
    }

    @Test
    @WithMockUser(username = "alice", authorities = "ROLE_TENANT_ADMIN")
    void tenantAdminCanManageOwnTenant() {
        tenantService.renameWithinTenant("acme", acmeId, "ACME-reviewed");

        assertEquals("ACME-reviewed", title(acmeId));
        assertEquals(1, tenantService.listWithinTenant("acme").size());
        assertEquals("BETA-original", title(betaId));
    }

    @Test
    @WithMockUser(username = "alice", authorities = "ROLE_TENANT_ADMIN")
    void tenantAdminCannotSelectAnotherTenant() {
        assertThrows(AccessDeniedException.class, () ->
                tenantService.renameWithinTenant(
                        "beta", betaId, "Hacked"));

        assertEquals("BETA-original", title(betaId));
    }

    @Test
    @WithMockUser(username = "alice", authorities = "ROLE_TENANT_ADMIN")
    void tenantAdminCannotUseForeignIdInOwnTenant() {
        assertThrows(AccessDeniedException.class, () ->
                tenantService.renameWithinTenant(
                        "acme", betaId, "Hacked"));

        assertEquals("BETA-original", title(betaId));
    }

    @Test
    @WithMockUser(username = "mallory", authorities = "ROLE_TENANT_ADMIN")
    void authorityWithoutMembershipCannotManageTenant() {
        assertThrows(AccessDeniedException.class, () ->
                tenantService.listWithinTenant("acme"));
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_READ")
    void membershipWithoutAdminAuthorityCannotManageTenant() {
        assertThrows(AccessDeniedException.class, () ->
                tenantService.listWithinTenant("acme"));
    }

    @Test
    @WithMockUser(username = "root", authorities = "ROLE_SYSTEM_ADMIN")
    void systemAdminDoesNotImplicitlyBecomeTenantAdmin() {
        assertThrows(AccessDeniedException.class, () ->
                tenantService.renameWithinTenant(
                        "acme", acmeId, "Hacked"));

        assertEquals("ACME-original", title(acmeId));
    }

    @Test
    @WithMockUser(username = "root", authorities = "ROLE_SYSTEM_ADMIN")
    void systemAdminCanCallExplicitSystemMetric() {
        assertEquals(2L, systemService.globalDocumentCount());
    }

    @Test
    @WithMockUser(username = "alice", authorities = "ROLE_TENANT_ADMIN")
    void tenantAdminCannotCallSystemMetric() {
        assertThrows(AccessDeniedException.class,
                () -> systemService.globalDocumentCount());
    }

    @Test
    @WithMockUser(username = "sam", authorities = "ROLE_TENANT_ADMIN")
    void membershipInTwoTenantsPermitsTwoExplicitContexts() {
        tenantService.renameWithinTenant("acme", acmeId, "A");
        tenantService.renameWithinTenant("beta", betaId, "B");

        assertEquals("A", title(acmeId));
        assertEquals("B", title(betaId));
    }

    @Test
    @WithAnonymousUser
    void anonymousCannotManageAnyTenant() {
        assertThrows(AccessDeniedException.class,
                () -> tenantService.listWithinTenant("acme"));
    }
}
~~~

### 7.1. Những điều phải được chứng minh

| Test | Ý nghĩa bảo mật |
| --- | --- |
| Alice chỉnh ACME | Đúng role + membership + row tenant |
| Alice chọn BETA | Role chung không mở quyền tenant khác |
| Alice dùng BETA document ID dưới route ACME | Repository `id + tenantId` chặn IDOR |
| Mallory có role nhưng thiếu membership | Chặn privilege escalation do authority chung |
| Alice có membership nhưng thiếu role | Membership không tự cấp quyền admin |
| Root có SYSTEM_ADMIN nhưng không thuộc ACME | Không bypass data plane mặc định |
| Root đọc system metric | Control-plane action được định nghĩa riêng |
| Alice không gọi system metric | Tenant admin không thành system admin |
| Sam quản trị hai tenant | Membership có thể gồm nhiều tenant nhưng chọn scope rõ |
| Anonymous bị chặn | Phải xác thực trước khi thao tác |

### 7.2. Chạy test

Trên macOS/Linux:

~~~text
./gradlew test --tests demo.tenancy.TenantAuthorizationTest
~~~

Trên Windows:

~~~text
gradlew.bat test --tests demo.tenancy.TenantAuthorizationTest
~~~

Không có `System.out.println` nên không có stdout nghiệp vụ cố định. Khi môi trường phù hợp, kết quả cần kiểm tra là mọi assertion thành công và Gradle hoàn thành task `test`. Mã được kiểm tra tĩnh trong bài; cần chạy thực tế trong dự án và test trên database production-compatible trước khi dùng chính sách thật.

Không đặt `@Transactional` lên toàn bộ lớp test một cách máy móc: test có thể tự rollback cuối method và che giấu các lỗi commit/transaction boundary của service. Trong ví dụ, test chỉ seed và đọc lại qua repository, còn service được gọi qua proxy.

## 8. Vì sao phải phân biệt “được quản trị tenant” và “được cấp quyền cho người khác”?

Tenant admin thường có thể quản lý user membership và role trong tenant của họ. Nhưng nếu cho admin tự cấp tùy ý authority `ROLE_SYSTEM_ADMIN`, một tenant bị chiếm quyền có thể lan thành **xâm nhập toàn hệ thống**.

### 8.1. Quy tắc cấp role theo scope

| Caller | Grant/revoke target | Có thể cho phép? |
| --- | --- | --- |
| Tenant admin ACME | Cấp role VIEWER trong ACME | Có theo policy |
| Tenant admin ACME | Cấp TENANT_EDITOR trong ACME | Có theo policy và hạn mức quyền |
| Tenant admin ACME | Cấp tenant admin trong ACME | Có thể cần owner approval / 2-person rule |
| Tenant admin ACME | Cấp admin trong BETA | Không |
| Tenant admin ACME | Cấp SYSTEM_ADMIN | **Không** |
| System admin | Cấp SYSTEM_ADMIN cho user | Chỉ control-plane workflow đặc quyền |
| System admin | Cấp quyền đọc tài liệu khách hàng | Không mặc định; cần break-glass |

Một ví dụ nguy hiểm:

~~~java
// PHẢN VÍ DỤ: role request là chuỗi tùy ý.
@PreAuthorize("@tenantPolicy.canManageTenant(authentication,#tenantId)")
public void grantRole(
        String tenantId, String targetUser, String role) {
    membershipRepository.grant(targetUser, tenantId, role);
}
~~~

Nếu `role` có thể là `SYSTEM_ADMIN`, tenant admin đã được cấp **quyền vượt scope**. Policy phải kiểm tra **cả role sẽ cấp**:

~~~text
allowGrant(actor, targetTenant, requestedRole)
  = canManageTenant(actor, targetTenant)
    AND requestedRole thuộc TENANT_GRANTABLE_ROLES
    AND targetTenant == membership.tenantId
    AND caller không tự nâng quyền trái policy
    AND đủ phê duyệt khi cấp quyền nhạy cảm
~~~

Ví dụ whitelist:

~~~java
// MINH HỌA policy helper, không phải method service độc lập.
private static final Set<String> TENANT_GRANTABLE_ROLES = Set.of(
        "TENANT_VIEWER", "TENANT_EDITOR");

// SYSTEM_ADMIN cố ý không nằm trong whitelist.
boolean canGrantByTenantAdmin(String role) {
    return TENANT_GRANTABLE_ROLES.contains(role);
}
~~~

Ở production cần lưu role bằng enum/permission catalog được quản lý server-side thay vì tin chuỗi bất kỳ; tenant admin cũng không được tự thay owner của tenant, đổi billing plan, xóa audit hoặc cấp quyền vượt cấp chỉ qua cách đoán tên role.

### 8.2. Self-service membership không được thành self-promotion

Chú ý đường nâng quyền:

~~~text
Member Alice gọi POST /tenants/acme/memberships
Body: {"userId":"alice","role":"TENANT_ADMIN"}
~~~

Nếu API chỉ kiểm tra Alice đang là member ACME rồi cho thay role, Alice có thể tự nâng thành admin. Hành động cấp membership phải thuộc nhóm quyền riêng, có check actor và requestedRole; trên một số hệ thống còn yêu cầu tenant owner hoặc security approver.

### 8.3. Tenant admin không tự chuyển dữ liệu xuyên tenant

Một API `moveDocument(sourceTenant, destinationTenant, id)` là hành động **giữa hai phạm vi**. Phải xác minh quyền xuất dữ liệu tại source, quyền nhập tại destination, các chính sách data residency và legal hold, và atomicity/migration flow. “Admin ở source” **không** tự là “admin ở destination”.

## 9. System admin: control-plane action, support access và break-glass

### 9.1. Phân loại các system-level actions

Có thể tách authorities:

~~~text
ROLE_SYSTEM_OPERATOR      - restart/health/config an toàn
ROLE_SYSTEM_TENANT_ADMIN  - provisioning/disable tenant
ROLE_SYSTEM_BILLING_ADMIN - billing config
ROLE_SECURITY_AUDITOR     - xem audit theo phạm vi phê duyệt
ROLE_SUPPORT_BREAK_GLASS  - truy cập dữ liệu khẩn cấp, theo thời hạn
~~~

Đây là **một cách thiết kế**, không phải role được Spring Security tạo sẵn. Tách roles giảm việc một tài khoản duy nhất có tất cả đặc quyền. Trong nhiều tổ chức, người vận hành infrastructure không có nhu cầu truy cập dữ liệu khách hàng hằng ngày.

### 9.2. Break-glass không phải một nút “bỏ qua mọi check”

Nếu support cần xem dữ liệu một tenant để xử lý P1 incident, một workflow an toàn có thể là:

~~~text
System operator được xác thực
    |
    +-- yêu cầu hỗ trợ Tenant ACME
    +-- incident ticket, mục tiêu cụ thể
    +-- step-up MFA / approval
    +-- giới hạn 15 phút và chỉ READ (ví dụ)
    +-- phát hành capability/entitlement ngắn hạn
    +-- kiểm tra capability trên mỗi request
    +-- audit ở nơi khó sửa + alert tới tenant/security
    +-- tự hết hạn/thu hồi và kiểm tra lại
~~~

Một user có `ROLE_SYSTEM_ADMIN` nhưng thiếu ticket hoặc entitlement break-glass **không** vượt data-plane policy. Thời hạn 15 phút chỉ là ví dụ; giá trị thực tế do mức độ rủi ro và quy định nội bộ quyết định.

### 9.3. Luồng xử lý đặc biệt phải tách endpoint và audit

Ví dụ ý tưởng:

~~~java
// CHỈ MINH HỌA: SupportEntitlementService và AuditService phải
// được triển khai đầy đủ, không tự chạy độc lập.
@PreAuthorize("@supportPolicy.canUseBreakGlass(authentication,#tenantId,#ticket)")
@Transactional(readOnly = true)
public DocumentView supportRead(
        @P("tenantId") String tenantId,
        String ticket,
        Long documentId) {

    // Dù break-glass, vẫn query theo (tenantId, documentId).
    TenantDocument document = repository
            .findByIdAndTenantId(documentId, tenantId)
            .orElseThrow(() -> new AccessDeniedException("Not available"));

    auditService.recordSupportRead(
            authentication.getName(), tenantId, ticket, documentId);

    return toView(document);
}
~~~

Method trên chỉ là **hình dạng** thiết kế, không có lớp `supportPolicy`, `auditService` và `toView` nên không được trình bày như file buildable. Trong thực tế, audit phải có chiến lược bền vững, tránh việc transaction rollback xóa cả audit; muốn ghi sự kiện đáng tin cậy có thể cần outbox.

Không dùng `@PostAuthorize` làm chốt duy nhất cho hành động đã side effect. Nếu hỗ trợ cần ghi dữ liệu, authorization phải được xét trước mutation cùng transaction và điều kiện SQL theo tenant.

## 10. Tenant isolation tại database: shared schema, schema-per-tenant, DB-per-tenant

| Kiểu lưu dữ liệu | Điểm mạnh | Rủi ro/chi phí |
| --- | --- | --- |
| Shared schema, cột `tenant_id` | Dễ vận hành, ít DB | Dễ quên tenant predicate ở một truy vấn |
| Schema-per-tenant | Phân chia logic/schema rõ hơn | Routing schema, migration hàng loạt, connection context |
| Database-per-tenant | Ranh giới hạ tầng mạnh hơn, backup riêng | Chi phí/điều phối/phân vùng tăng |
| PostgreSQL RLS trong shared schema | Database có thể chặn hàng theo policy | Phải kiểm soát DB role/session context và các trường hợp bypass |
| Hybrid | Tùy quy mô và độ nhạy dữ liệu | Nhiều đường code/migration cần test |

Không có kiến trúc nào tự bảo đảm authorization nếu request tenant selector hoặc database credentials không đáng tin. DB-per-tenant vẫn có thể lộ dữ liệu nếu router lấy tenantId từ header không được xác minh và kết nối nhầm database.

### 10.1. Query phải có tenant predicate

Đúng ở service bình thường:

~~~sql
SELECT id, title
FROM tenant_documents
WHERE tenant_id = :authorized_tenant
  AND id = :document_id;
~~~

Khi update:

~~~sql
UPDATE tenant_documents
SET title = :new_title
WHERE tenant_id = :authorized_tenant
  AND id = :document_id;
~~~

Nếu dùng SQL UPDATE/DELETE trực tiếp, kiểm tra affected row count và transaction; zero rows có thể là row không tồn tại hoặc không đúng scope, không tự suy ra caller bị “mất quyền tenant” trừ khi thêm bằng chứng. Với batch updates, nếu thiếu một row quyền, phải xác định hợp đồng all-or-nothing/best-effort riêng.

### 10.2. PostgreSQL Row-Level Security là lớp bổ sung, không phải phép màu

Ví dụ policy mang tính minh họa:

~~~sql
ALTER TABLE tenant_documents ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_document_isolation
ON tenant_documents
USING (tenant_id = current_setting('app.tenant_id', true))
WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
~~~

Trong ứng dụng dùng connection pool, phải bảo đảm giá trị `app.tenant_id` được gán **theo đúng transaction** từ tenant đã được server authorize, và dọn/không rò context sang request khác. Nếu biến setting có thể bị một đường code tùy ý thay thành tenant khác, RLS policy dựa vào biến đó không còn là một ranh giới xác thực độc lập.

**Điểm cực kỳ quan trọng từ PostgreSQL:** superuser và role mang `BYPASSRLS` luôn vượt Row-Level Security; chủ bảng thường cũng vượt RLS, trừ khi dùng `FORCE ROW LEVEL SECURITY` phù hợp. Vì vậy ứng dụng bình thường không nên chạy bằng DB superuser/table owner có quyền bypass khi kỳ vọng RLS bảo vệ dữ liệu tenant. Policy `USING`/`WITH CHECK` phải được kiểm tra với đúng database role và session context thực tế.

Chúng ta **không** chạy SQL PostgreSQL đó trên H2 của ví dụ chính; RLS snippet chỉ phục vụ kiến trúc PostgreSQL.

### 10.3. Background jobs và system reports cũng phải có policy

Một job tổng hợp nhiều tenant có thể cần đọc nhiều rows, nhưng không nên tái sử dụng đường dữ liệu tenant-scoped rồi tắt bộ lọc tenant một cách tùy ý. Tạo repository/service dành riêng cho cross-tenant analytics, chỉ trả aggregate tối thiểu và dùng principal/service-account đặc quyền với audit và allowlist hành động.

Trong async processing, `SecurityContextHolder` và request-scoped context không mặc nhiên được truyền qua thread/message. Consumer phải xác minh danh tính hệ thống, tenant scope của command và quyền cần thiết, không tin tenantId do producer chưa xác thực gửi.

## 11. Membership có thời gian sống, trạng thái và rủi ro token cũ

Một bản ghi membership thực tế có thể gồm:

~~~text
subject_id | tenant_id | role         | status | valid_until
-----------+-----------+--------------+--------+------------
user-17    | acme      | TENANT_ADMIN | ACTIVE | ...
user-17    | beta      | VIEWER       | ACTIVE | ...
user-42    | beta      | TENANT_ADMIN | REVOKED| ...
~~~

Cần test:

- Khi membership bị thu hồi, service không cho phép ở lần kiểm tra kế tiếp theo tính nhất quán đã công bố.
- Khi một user rời tenant ACME, họ không thể truy cập bằng tenantId cũ đã nằm trong local context.
- Session/JWT có authority `ROLE_TENANT_ADMIN` được cấp trước đó vẫn có thể tồn tại; **quyền tenant thực tế** cần được đồng bộ bằng membership mới/entitlement mới.
- Nếu membership được cache, phải có invalidation/revision/TTL phù hợp; không dựa duy nhất vào role trong JWT stale.
- Những membership tạm thời phải tự hết hạn, bị revoke khi user offboard.
- Người quản trị tenant có thể bị đình chỉ hoặc tenant bị disabled; cả hai trạng thái nên được xét khi authorization.

Ví dụ Spring `TenantPolicy` đã kiểm tra directory server-side (mock) **ở mỗi lần gọi**; production có thể dùng cache, nhưng phải chấp nhận và đo độ trễ thu hồi quyền. Nếu quyền dữ liệu nhạy cảm, ưu tiên source of truth hoặc revision check.

### 11.1. Thay tenant ngữ cảnh trong UI

Một tài khoản có membership ở ACME và BETA có thể chọn “đang làm việc tại ACME”. Lựa chọn này chỉ xác định **target scope** cho request. Server phải kiểm tra lại membership mỗi lần có thao tác nhạy cảm. Không chỉ xác minh “Sam thuộc cả hai tenant” rồi để UI ẩn tenantId dẫn tới thực thi nhầm phạm vi.

### 11.2. User ID phải bất biến và phân biệt tenant

Đừng dùng email hoặc username dễ đổi làm khóa membership duy nhất nếu hệ thống có trùng tên ở các tenant. Dùng subject ID ổn định, kèm tenant ID explicit trong membership, và không cho một tài khoản mới kế thừa quyền cũ chỉ vì username được tái sử dụng.

## 12. Các lỗi phân quyền nghiêm trọng thường gặp

| Dấu hiệu | Nguyên nhân | Biện pháp |
| --- | --- | --- |
| Alice admin ACME sửa được tài liệu BETA | Chỉ check `ROLE_TENANT_ADMIN` | Thêm membership scope + repository tenant predicate |
| Root system admin xem được mọi tài liệu | Thêm `or hasRole('SYSTEM_ADMIN')` vào data endpoints | Tách system ops và break-glass |
| Đổi `tenantId` trong URL là đổi được dữ liệu | Tin tenant selector do client gửi | Bind tenant target với verified membership |
| Có membership nhưng chưa có role mà vẫn admin | Chỉ kiểm tra membership tồn tại | Kiểm tra role/action + trạng thái membership |
| Có role admin nhưng không là member vẫn được cấp quyền | Chỉ check authority | Kiểm tra active ADMIN membership |
| Tenant admin tự cấp SYSTEM_ADMIN | GrantRole cho phép chuỗi role bất kỳ | Allowlist roles và policy grant scope |
| Admin ACME cấp role tại BETA | Grant API thiếu tenant predicate | Kiểm tra actor/target tenant trong cùng transaction |
| User đã bị thu hồi nhưng còn truy cập | JWT hoặc cache membership stale | Revocation/version/TTL phù hợp |
| Spring annotation có nhưng không chặn | Thiếu `@EnableMethodSecurity` hoặc self-invocation | Bật Method Security, test qua bean proxy |
| SpEL `#tenantId` null | Sai tên tham số, thiếu `-parameters` | Dùng `@P("tenantId")` |
| Query `findById` trả row tenant khác | Không scope theo tenant | Repository method `id + tenantId`/RLS |
| IDOR qua export, search, attachment | Chỉ bảo vệ update endpoint | Kiểm tra tất cả read/export/delete/list paths |
| RLS không có tác dụng | App role là superuser/table owner/BYPASSRLS | Dùng DB role hạn chế, FORCE RLS khi cần |
| Tenant context lây sang request kế | ThreadLocal/session state không dọn | Context lifecycle nghiêm ngặt, test concurrency |
| Background job bỏ qua quyền | Job dùng service/repository đặc quyền tùy tiện | System principal/tenant scope + explicit policy |
| Đổi tenant khi đang dùng connection pool gây lộ | Session variable/schema không reset | SET LOCAL trong transaction, kiểm soát connection reuse |
| Cross-tenant reporting trả PII | Dùng system role để đọc tất cả rows | Aggregate tối thiểu, purpose limitation và audit |
| Root incident access không có log | Break-glass không có ticket/MFA/audit | Đường riêng, entitlement ngắn hạn, alert |
| Role hierarchy mở quyền ngoài dự kiến | SYSTEM_ADMIN tự suy ra TENANT_ADMIN | Vẫn kiểm tra membership và explicit action |

## 13. Ma trận kiểm thử mở rộng cho hệ thống thật

| Actor | Role | Active membership | Target | Operation | Kỳ vọng |
| --- | --- | --- | --- | --- | --- |
| Alice | TENANT_ADMIN | ACME | ACME | Rename document | Allow |
| Alice | TENANT_ADMIN | ACME | BETA | Rename document | Deny |
| Alice | TENANT_ADMIN | ACME | ACME route + BETA ID | Rename document | Deny |
| Bob | TENANT_ADMIN | BETA | ACME | List documents | Deny |
| Mallory | TENANT_ADMIN | Không có | ACME | List documents | Deny |
| Alice | DOC_READ | ACME admin membership | ACME | Rename document | Deny |
| Sam | TENANT_ADMIN | ACME, BETA | Mỗi tenant riêng | Rename | Allow trong scope |
| Root | SYSTEM_ADMIN | Không có | ACME | Normal tenant rename | Deny |
| Root | SYSTEM_ADMIN | Không có | System | Aggregate report | Allow |
| Alice | TENANT_ADMIN | ACME | System | Aggregate report | Deny |
| Alice | TENANT_ADMIN | ACME | ACME | Grant SYSTEM_ADMIN | Deny |
| Root | SYSTEM_ADMIN | Không có | BETA sensitive data | Emergency read không có ticket | Deny |
| Root | SUPPORT_BREAK_GLASS | Entitlement hết hạn | BETA | Emergency read | Deny |
| Alice (revoked) | TENANT_ADMIN trong JWT cũ | ACME REVOKED | ACME | Rename document | Deny theo revocation policy |
| System job | Service principal | Scope báo cáo cụ thể | All tenants | Aggregate | Chỉ allowlist operations |

Ngoài kiểm thử API, cần kiểm tra mọi đường:
- HTTP REST, GraphQL, WebSocket, export/report, file download, search/autocomplete.
- Background worker, message consumer, scheduled task, CLI migration.
- Bulk update/delete, ACL and membership management, support tools.
- Database RLS với connection pool và đúng role ứng dụng.
- Audit, event và độ trễ thu hồi quyền sau membership change.

**Negative tests có giá trị cao nhất:** cùng role nhưng khác tenant; ID của tenant khác trong route hợp lệ; system admin đi vào tenant endpoint; tenant admin gọi grant role cao; tenant selector bị thay trong header/body; session cũ sau revoke.

## 14. Checklist thiết kế và vận hành

Một hệ thống Spring Security multi-tenant có thể dùng checklist:

1. Có định nghĩa rõ các action của **control plane**, **data plane**, **break-glass** không?
2. Actor được nhận diện bằng subject ID đã verify chưa?
3. TenantId trong request được đối chiếu với active membership chưa?
4. Policy có kiểm tra cả authority + tenant admin membership + resource tenant không?
5. System admin có bị từ chối mặc định ở tenant data endpoints không?
6. Repository có ràng buộc `tenant_id` ở read/update/delete/search/export không?
7. Có test IDOR khi dùng document ID của tenant khác nhưng đường dẫn tenant hợp lệ không?
8. Có cấm tenant admin grant system roles hoặc thay role ngoài tenant không?
9. Có chống self-promotion và chuyển ownership/migration không kiểm soát không?
10. Các membership có trạng thái active/revoked/expired và cơ chế invalidation không?
11. RLS (nếu dùng) có được test dưới DB role thực và tránh bypass superuser/owner không?
12. Context tenant có được dọn khi connection/thread được tái sử dụng không?
13. Các lệnh cross-tenant có lý do/mục tiêu/timeout/audit/alert không?
14. System analytics có trả dữ liệu tổng hợp tối thiểu và không lộ PII ngoài policy không?
15. Security tests có chạy qua Spring proxy chứ không chỉ gọi policy trực tiếp không?
16. Khi incident support access hết hạn, có kiểm thử không còn quyền trong mọi cache/node không?

## 15. Bài tập thực hành

**Bài 1 – Tenant admin không chéo tenant.** Chạy test Alice/Bob. Thử bỏ `tenantId` khỏi `lockByIdAndTenant` trong bản thử nghiệm và viết test phát hiện IDOR. Khôi phục điều kiện type+ID+tenant.

**Bài 2 – Admin hai tenant.** Cho Sam là admin ACME và BETA. Thêm một tenant GAMMA không nằm trong membership. Test Sam quản trị được hai tenant, nhưng không quản trị GAMMA dù có `ROLE_TENANT_ADMIN`.

**Bài 3 – Membership bị revoke.** Thay Map demo bằng bảng membership có `ACTIVE/REVOKED`. Thu hồi Alice ở ACME; giữ Authentication có `ROLE_TENANT_ADMIN` nhưng test rename bị từ chối.

**Bài 4 – Hạn chế cấp role.** Tạo `grantTenantRole` với whitelist `TENANT_VIEWER` và `TENANT_EDITOR`, chỉ cho admin của tenant đích. Test Alice không cấp BETA role và không cấp `ROLE_SYSTEM_ADMIN` ở bất kỳ tenant nào.

**Bài 5 – Break-glass.** Tạo use case `supportRead` yêu cầu system role chuyên biệt, ticket, reason, MFA gần đây, approval và entitlement có thời hạn. Test thiếu từng điều kiện đều deny, kể cả system admin không có ticket; kiểm tra audit/expiration.

**Bài 6 – PostgreSQL RLS.** Dùng database test PostgreSQL, bật RLS trên tenant documents. Test application DB role dưới tenant context ACME không đọc BETA; sau đó kiểm tra riêng owner role, `BYPASSRLS` và `FORCE ROW LEVEL SECURITY`. Không đặt tenant từ header chưa verify.

**Bài 7 – Data export và background job.** Thiết kế endpoint export tài liệu theo tenant và job báo cáo system-level; chứng minh query/repository không thể trả raw data tenant khác chỉ vì job chạy bằng system service account.

**Bài 8 – Role hierarchy.** Cấu hình system role cao hơn tenant role ở một bản thử nghiệm. Kiểm tra `TenantPolicy.canManageTenant` vẫn từ chối Root khi không có membership của tenant đích.

**Tiêu chí hoàn thành:** phân biệt được tenant admin và system admin; hiểu role không đủ để xác định scope; dùng `@PreAuthorize` với `@P("tenantId")` và trusted membership; ràng buộc tenant trong repository, chứng minh negative tests cross-tenant; biết đặt system operation ở control plane và thiết kế break-glass; nhận ra giới hạn của JWT/session cache, PostgreSQL RLS và connection context.

## Tài liệu tham khảo chính thức

- Spring Security – **Method Security**, `@EnableMethodSecurity`, `@PreAuthorize`, custom bean và `@P` parameter annotation: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- Spring Security – **Authorization Architecture** và `AuthorizationManager`: https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html
- Spring Security – **Authorize HTTP Requests** (request-level authorization và ordering): https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html
- Spring Security – **Testing Method Security**, `@WithMockUser` và `@WithAnonymousUser`: https://docs.spring.io/spring-security/reference/servlet/test/method.html
- Spring Data JPA – **Locking**, `@Lock` trên repository query: https://docs.spring.io/spring-data/jpa/reference/jpa/locking.html
- Spring Framework – **Declarative Transaction Management**, `@Transactional`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- PostgreSQL – **Row Security Policies**, `ENABLE/FORCE ROW LEVEL SECURITY`, chủ bảng và `BYPASSRLS`: https://www.postgresql.org/docs/current/ddl-rowsecurity.html
