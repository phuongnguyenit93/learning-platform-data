# Tạo ACL khi tạo mới đối tượng nghiệp vụ

> **Phạm vi:** Spring Security – authorization, nhóm **Triển khai ACL**. Bài học giải thích cách **khởi tạo Access Control List (ACL) ngay khi tạo một đối tượng nghiệp vụ mới** như Document, Project hoặc Invoice; từ khi DB cấp ID, tạo `ObjectIdentity`, `MutableAclService.createAcl(...)`, thêm ACE, `updateAcl(...)` đến đảm bảo giao dịch, quyền tối thiểu và xử lý lỗi. Ví dụ Spring hướng tới Spring Boot 3.x + Spring Security 6.x; nguyên lý áp dụng cho các phiên bản khác khi kiểm tra Javadoc/runtime tương ứng. Ví dụ Java 17 độc lập được phân biệt rõ với framework thực.

## 1. Mục tiêu và yêu cầu nghiệp vụ

Một API nhận yêu cầu tạo tài liệu:

~~~http
POST /api/documents
Authorization: Bearer <token>
Content-Type: application/json

{"title":"Kế hoạch tháng 11"}
~~~

Giả sử Alice đã đăng nhập, thuộc tenant alpha và có authority `document:create`. Ứng dụng cần làm **hai việc gắn liền**:

1. Lưu một hàng Document có ID thực, creator/owner đáng tin và tenant phù hợp.
2. Tạo ACL cho chính Document đó; cấp cho Alice quyền `READ` và `WRITE`, không tự cấp `DELETE`, `ADMINISTRATION` hoặc quyền cho tất cả người dùng.

Không nên coi thao tác hoàn thành chỉ vì repository đã trả một ID. Nếu đã có Document nhưng ACL chưa được tạo, hai kết quả xấu có thể xảy ra: tài liệu bị khóa ngoài ý muốn, hoặc endpoint khác dùng logic fallback thiếu an toàn và để lộ dữ liệu.

Sau bài này, bạn có thể:

- Giải thích **tại sao ACL không tự xuất hiện** sau `repository.save(...)`.
- Chọn đúng thời điểm có ID để tạo `ObjectIdentity` và ACL.
- Dùng `MutableAclService.createAcl`, `MutableAcl.insertAce` và `MutableAclService.updateAcl` đúng chức năng, phân biệt ACL owner với ACE quyền đọc/ghi.
- Đặt domain save và ACL provisioning vào **một transaction thực sự** khi có cùng DB/transaction manager; nhận diện khi `@Transactional` chưa đủ.
- Thiết kế fail closed, least privilege, idempotency/retry, tenant isolation và parent inheritance có chủ đích.
- Viết test cho luồng thành công, lỗi tạo ACL, duplicate ACL, rollback, sai owner/tenant và đọc lại quyền sau commit.

## 2. Spring Security ACL bảo vệ cái gì?

Spring Security ACL là cơ chế **ủy quyền theo từng object**, bổ sung cho URL/method authority. Người dùng có thể có authority `document:read` nhưng chỉ được READ một vài Document cụ thể. Các thành phần:

| Thành phần | Ý nghĩa khi tạo Document mới |
| --- | --- |
| `ObjectIdentity` | Cặp type + ID, ví dụ `Document.class` và `101L` |
| `Acl` / `MutableAcl` | Chính sách cho đúng object; mutable ACL dùng để thêm/sửa ACE và parent |
| `Sid` | Danh tính chịu tác động của ACE: `PrincipalSid` hoặc `GrantedAuthoritySid` |
| `Permission` | Mask quyền như `BasePermission.READ`, `WRITE`, `DELETE` |
| `AccessControlEntry` (ACE) | Một quy tắc cho SID + permission + cấp/từ chối |
| `MutableAclService` | Dịch vụ tạo/cập nhật/xóa ACL persistent |
| `AclService` | Dịch vụ đọc ACL phục vụ quyết định quyền |
| `AclPermissionEvaluator` | Cầu nối expression `hasPermission(...)` với dữ liệu ACL |
| `AclAuthorizationStrategy` | Quy định ai được **thay đổi ACL**, không phải ai được đọc document |
| `parentAcl` / `entriesInheriting` | Quan hệ ACL cha và có tham khảo quyền kế thừa hay không |

### 2.1. Bốn bảng phổ biến của Spring JDBC ACL

~~~text
acl_class            loại đối tượng: com.example.domain.Document
acl_sid              SID: principal alice / authority ROLE_REVIEWER
acl_object_identity  ID của ACL cho Document 101, owner, parent, inheritance
acl_entry            ACE: READ/WRITE/DELETE... cho SID trên ACL đó
~~~

Trong schema JDBC chuẩn, `acl_object_identity` lưu object identity, `owner_sid`, `parent_object`, `entries_inheriting`. `acl_entry` lưu `acl_object_identity`, `ace_order`, `sid`, `mask` và `granting`.

**Không có một trigger mặc định nào của Spring Security tự tạo ACL khi JPA repository lưu entity.** Chính service/application workflow phải thực hiện provisioning hoặc gọi một component chuyên trách. Spring Security documentation nêu rõ rằng ACL không được tự tích hợp vào mọi DAO/repository operation.

### 2.2. Owner của ACL không phải quyền READ mặc định

`Acl.getOwner()` biểu thị SID sở hữu ACL cho mục đích quản trị/thay đổi ACL theo strategy được cấu hình. Việc Alice là owner ACL **không đồng nghĩa** tự có ACE `READ` hay `WRITE` để biểu thức `hasPermission` cho phép.

Do đó luồng tạo mới cần xác định riêng:
- **Ai được tạo?** Method/web authorization `document:create`.
- **Ai là owner của Document?** Principal/tenant đã xác minh trong domain data.
- **Ai là owner ACL?** SID dùng cho quản trị ACL, trong JDBC mặc định liên quan security context khi tạo ACL.
- **ACE ban đầu gồm gì?** Ví dụ Alice `READ` và `WRITE`, không cấp thêm quyền chỉ vì Alice là creator.

Quản lý owner ACL và owner nghiệp vụ là hai quyết định liên quan nhưng không tự đồng bộ. Nếu actor tạo hộ người khác, cần policy cấp quyền thay owner, tránh biến creator thành người có thể sửa mọi ACL.

## 3. Thứ tự tạo mới đúng: ID → ACL → ACE → commit

Một luồng rõ ràng:

~~~text
Client Alice: CreateDocument(title)
             |
             v
Spring Security kiểm tra document:create
             |
             v
@Service @Transactional
  1. Validate title và xác định creator + tenant từ identity tin cậy
  2. Tạo Document và lưu để có ID 101
  3. ObjectIdentity(Document.class, 101L)
  4. aclService.createAcl(objectIdentity)  -> ACL mới, chưa có ACE
  5. Cấu hình inheritance/parent (nếu có chủ đích)
  6. insertAce(READ, PrincipalSid("alice"), grant=true)
  7. insertAce(WRITE, PrincipalSid("alice"), grant=true)
  8. aclService.updateAcl(acl)           -> lưu ACE và metadata
             |
             +-- nếu bất kỳ bước nào thất bại: rollback CẢ domain + ACL
             |
             v
Transaction COMMIT
             |
             v
Trả 201 Created + id=101
~~~

**Thứ tự phụ thuộc ID đã tồn tại:** với ID do DB sinh, không tạo `ObjectIdentityImpl(Document.class, null)` trước khi save. Nếu ID đến từ JPA `IDENTITY`, ORM thường cần insert để cấp ID; với `SEQUENCE`, ID có thể có trước khi row được flush. Cách an toàn trong ví dụ là `saveAndFlush` rồi kiểm tra ID khác null; lưu ý **flush không đồng nghĩa commit**.

### 3.1. Hai phase của ACL provisioning

API `MutableAclService` được dùng theo đúng trách nhiệm:

~~~java
ObjectIdentity oi =
        new ObjectIdentityImpl(Document.class, savedDocument.getId());

// Phase 1: tạo hàng ACL rỗng cho ObjectIdentity.
MutableAcl acl = aclService.createAcl(oi);

// Phase 2: thêm entries và cập nhật vào persistent ACL.
Sid creatorSid = new PrincipalSid(creatorId);
acl.insertAce(acl.getEntries().size(),
              BasePermission.READ, creatorSid, true);
acl.insertAce(acl.getEntries().size(),
              BasePermission.WRITE, creatorSid, true);
aclService.updateAcl(acl);
~~~

Đây là **trích đoạn** cần biến `savedDocument`, `creatorId` và `aclService` trong service; không phải file Java độc lập.

Các điểm cần nhớ:

1. `createAcl(oi)` tạo một **ACL chưa có ACE**, lưu object identity và trả `MutableAcl` đã có ID của ACL.
2. `insertAce(index, permission, sid, granting)` chỉ sửa danh sách ACE của mutable object; phải gọi `updateAcl(acl)` để persist các thay đổi.
3. `acl.getEntries().size()` là chỉ số chèn **cuối danh sách ACE trực tiếp**. Thứ tự ACE có ý nghĩa đối với chiến lược xét quyền; không tự thêm trùng khi chạy lại workflow.
4. `true` nghĩa là GRANT. `false` nghĩa là DENY, không đồng nghĩa “không tạo ACE”.
5. `createAcl` có thể ném `AlreadyExistsException` khi ObjectIdentity đã có ACL. Không tự bắt rồi thêm quyền rộng hơn vào ACL đã tồn tại, vì đó có thể là lỗi race hoặc policy khác.
6. `updateAcl` không phải thao tác tạo mới: nó cập nhật ACL đã tồn tại, có thể ném `NotFoundException` nếu record chưa được tạo.

### 3.2. Không dùng new AclImpl thay createAcl

~~~java
// KHÔNG dùng để tạo hàng ACL mới:
AclImpl localObject = new AclImpl(/* ... */);
aclService.updateAcl(localObject); // Không tự insert acl_object_identity.
~~~

Mã trên là phản ví dụ khái niệm, thiếu constructor arguments. Với JDBC ACL, phải dùng `MutableAclService.createAcl(oi)` để cấp ID ACL và lưu object identity; chỉ sau đó mới `updateAcl`. Tự tạo object `AclImpl` thích hợp cho một số unit test nhưng **không thay** persistence contract.

## 4. Thiết kế quyền ban đầu theo nguyên tắc tối thiểu

Giả sử tài liệu cá nhân vừa tạo:

| SID | Quyền | Grant | Có nên cấp khi tạo? |
| --- | --- | --- | --- |
| `PrincipalSid("alice")` | READ | true | Có, theo yêu cầu mẫu |
| `PrincipalSid("alice")` | WRITE | true | Có, nếu creator được sửa |
| `PrincipalSid("alice")` | DELETE | Không có ACE | Không tự động |
| `PrincipalSid("alice")` | ADMINISTRATION | Không có ACE | Không tự động |
| `GrantedAuthoritySid("ROLE_USER")` | READ | Không có ACE | Không cấp mọi user |
| `GrantedAuthoritySid("ROLE_REVIEWER")` | READ | Tuỳ business | Chỉ cấp khi chính sách được xác nhận |
| `PrincipalSid("bob")` | READ | Không có ACE | Không được đọc trừ khi chia sẻ |

**Không có ACE phù hợp không phải một ACE GRANT.** `Acl.isGranted(...)` của strategy chuẩn có thể ném `NotFoundException` khi không tìm thấy quyết định; `AclPermissionEvaluator`/security layer phải xử lý theo contract không cấp quyền khi chưa có bằng chứng.

### 4.1. Chọn SID đúng

- `PrincipalSid(String username)` dùng một định danh principal. Trong ứng dụng thật, nên chọn stable ID thay vì username có thể đổi; nhất quán giữa login, ACL provisioning và SID retrieval.
- `GrantedAuthoritySid("ROLE_REVIEWER")` dùng authority chung. Nhớ rằng cấp READ cho `ROLE_USER` có thể làm **mọi user mang role đó** đọc được tài liệu mới.
- Nếu tenant cần là một thành phần của SID, xác định mô hình rõ (principal ID toàn hệ thống, hoặc composite namespaced ID đáng tin); tránh collision giữa “alice” tenant A và “alice” tenant B.

Chọn một convention duy nhất cho `ObjectIdentity` type và SID. Ví dụ `new ObjectIdentityImpl(Document.class, id)` dùng tên class mà ACL persistence nhận biết; nếu expression check dùng một tên type khác, lookup có thể thất bại hoặc truy xuất sai ACL.

### 4.2. BasePermission không suy diễn theo vai trò

`BasePermission.READ`, `WRITE`, `CREATE`, `DELETE` và `ADMINISTRATION` là các mask riêng. Không tự suy luận rằng cấp WRITE bao gồm READ hoặc cấp READ là đủ để update. Nếu API yêu cầu cả READ và WRITE, thêm ACE tương ứng theo policy.

Nếu document có trạng thái `DRAFT` và creator chỉ được sửa trước khi publish, **đừng mong ACL WRITE tự động hiểu nghiệp vụ “chỉ DRAFT”**. Phải dùng thêm business-state policy ở service/domain.

## 5. Service Spring Boot: tạo Document và ACL trong cùng transaction

Ví dụ sau cho thấy phần **service lõi**. Nó cần một Spring Boot 3.x/Spring Security 6.x project đã cấu hình JPA, Spring ACL JDBC, transaction manager, schema, authentication và các dependency bên dưới. Các lớp `Document`, `DocumentRepository` và `TenantDirectory` là thành phần domain mà ứng dụng phải cung cấp; vì vậy đây là **trích đoạn tích hợp có thể đưa vào dự án**, không tự nhận là một ứng dụng hoàn chỉnh chỉ với một file.

Tạo `src/main/java/example/documents/CreateDocumentService.java`:

~~~java
package example.documents;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.acls.domain.BasePermission;
import org.springframework.security.acls.domain.ObjectIdentityImpl;
import org.springframework.security.acls.domain.PrincipalSid;
import org.springframework.security.acls.model.MutableAcl;
import org.springframework.security.acls.model.MutableAclService;
import org.springframework.security.acls.model.ObjectIdentity;
import org.springframework.security.acls.model.Sid;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CreateDocumentService {
    private final DocumentRepository repository;
    private final MutableAclService aclService;
    private final TenantDirectory tenantDirectory;

    public CreateDocumentService(DocumentRepository repository,
                                 MutableAclService aclService,
                                 TenantDirectory tenantDirectory) {
        this.repository = repository;
        this.aclService = aclService;
        this.tenantDirectory = tenantDirectory;
    }

    @Transactional
    @PreAuthorize("hasAuthority('document:create')")
    public Long create(NewDocument command) {
        Authentication actor =
                SecurityContextHolder.getContext().getAuthentication();
        if (actor == null || !actor.isAuthenticated()
                || actor instanceof AnonymousAuthenticationToken) {
            throw new AccessDeniedException("Authentication required");
        }

        // Đây là ID đã xác thực, KHÔNG phải creatorId do client khai.
        String creatorId = actor.getName();

        // Tenant lấy từ nguồn tin cậy phía server, KHÔNG từ request header.
        String tenantId = tenantDirectory.requireTenantFor(actor);

        Document entity = new Document(
                command.title(), tenantId, creatorId);
        Document saved = repository.saveAndFlush(entity);
        Long id = saved.getId();
        if (id == null) {
            throw new IllegalStateException("Document ID was not generated");
        }

        ObjectIdentity oid = new ObjectIdentityImpl(Document.class, id);
        MutableAcl acl = aclService.createAcl(oid);

        // Không tự thừa hưởng ACE từ folder/tenant khác.
        acl.setEntriesInheriting(false);

        // JDBC createAcl tạo owner từ security context.
        // ACL owner không tự làm phát sinh ACE READ/WRITE.
        Sid creator = new PrincipalSid(creatorId);
        acl.insertAce(acl.getEntries().size(),
                BasePermission.READ, creator, true);
        acl.insertAce(acl.getEntries().size(),
                BasePermission.WRITE, creator, true);

        aclService.updateAcl(acl);
        return id;
    }
}
~~~

Ví dụ `NewDocument` là một command/value object nhận dữ liệu đã kiểm tra:

~~~java
package example.documents;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record NewDocument(
        @NotBlank @Size(max = 180) String title) {
}
~~~

**Các dependency domain cần tự khai báo:** `Document` là JPA `@Entity` có constructor nhận `title, tenantId, creatorId` và getter `Long getId()`; `DocumentRepository` là `JpaRepository<Document, Long>`; `TenantDirectory.requireTenantFor(Authentication)` tra tenant từ nguồn định danh tin cậy của server và ném exception nếu không xác minh được. Không lấy tenant/creator từ request rồi gán mặc nhiên là đáng tin.

### 5.1. Vì sao saveAndFlush trước createAcl?

- Với ID do DB sinh, phải có ObjectIdentity dựa trên ID **đã được cấp**.
- `saveAndFlush` bảo đảm JPA gửi các thay đổi đang chờ tới DB, nhưng **transaction vẫn mở** và chưa commit.
- ACL JDBC có thể cần đọc/ghi trong cùng DB. Khi dùng đúng một DataSource và transaction configuration, cả phần domain và ACL tham gia cùng transaction để rollback chung.

Đừng viết:

~~~java
// Sai thứ tự khi ID chưa tồn tại:
Document draft = new Document(title, tenant, creator);
ObjectIdentity oi = new ObjectIdentityImpl(Document.class, draft.getId());
// draft.getId() lúc này có thể null.
MutableAcl acl = aclService.createAcl(oi);
~~~

Cũng đừng gọi `entityManager.persist(...)` trong một method không có transaction rồi dựa vào JDBC ACL ở method khác như thể cả hai chắc chắn atomic.

### 5.2. Cẩn trọng với ACL owner và identity

`JdbcMutableAclService.createAcl(...)` thiết lập owner SID theo security context của caller trong implementation chuẩn. Trong ví dụ, principal đang gọi chính là creator. Nếu job hệ thống tạo thay người khác:
- Không giả rằng ACL owner tự là owner nghiệp vụ.
- Có thể cần một `Sid` đại diện service identity và ACE riêng cho người hưởng quyền.
- Nếu muốn đổi owner ACL bằng `MutableAcl.setOwner(...)`, actor thay đổi phải được `AclAuthorizationStrategy` cho phép; cần quyền quản trị phù hợp.
- Không tạo `Authentication` giả với tên Alice chỉ để lách security checks rồi ghi dữ liệu.
- Tài khoản/tenant có thể thay đổi trước khi job async chạy; xác minh lại identity và policy nếu nhiệm vụ kéo dài.

### 5.3. Vì sao @PreAuthorize không thay quyền READ trên object?

`@PreAuthorize("hasAuthority('document:create')")` bảo vệ **hành động tạo**. Nó không tạo ACE và không bảo vệ mọi method READ/WRITE khác. Các method khác có thể dùng:

~~~java
@PreAuthorize("hasPermission(#p0, 'example.documents.Document', 'READ')")
public DocumentView readById(Long documentId) {
    return repository.loadView(documentId);
}
~~~

Đây là **trích đoạn** phụ thuộc repository/domain. Literal type phải khớp ObjectIdentity được lưu, permission string `'READ'` phải được evaluator/factory hiểu đúng. Cần bật `@EnableMethodSecurity` và nối `AclPermissionEvaluator` vào `MethodSecurityExpressionHandler`, nếu không expression có thể dùng evaluator mặc định deny-all.

### 5.4. Proxy và @Transactional phải thực sự chạy

Cả `@PreAuthorize` lẫn `@Transactional` trong cấu hình Spring AOP mặc định cần lời gọi **đi qua Spring-managed proxy**. Nếu cùng bean gọi `this.create(command)`, các advice có thể bị bỏ qua. Tách entrypoint gọi sang bean khác và kiểm thử service được lấy qua `@Autowired`, transaction active và rollback thực tế.

**Không dùng `@PostAuthorize` để bảo vệ thao tác create**: khi hậu kiểm chạy, domain row hoặc side effect bên ngoài có thể đã được tạo. Quyền cấp tính năng nên chặn trước.

## 6. Cấu hình ACL persistence cần có trước khi dùng service

Thư viện ACL là module riêng. Ví dụ dependency `build.gradle` trong một dự án đã cấu hình Spring Boot plugin, Java 17+ và dependency management:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    implementation 'org.springframework.security:spring-security-acl'

    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Nếu production dùng PostgreSQL/MySQL, thay H2 driver và điều chỉnh schema/SQL/dialect cho phù hợp. Khối dependencies **không phải** file build độc lập, còn thiếu plugin/version và cấu hình database. ACL schema phải được tạo bằng migration (Flyway/Liquibase hoặc cơ chế có kiểm soát), không trông chờ Hibernate `ddl-auto` tự sinh đầy đủ bốn bảng ACL.

### 6.1. Các bean ACL cốt lõi

Ví dụ cấu hình Spring Security ACL phổ biến:

~~~java
@Configuration
@EnableMethodSecurity
class AclConfiguration {

    @Bean
    static MethodSecurityExpressionHandler expressionHandler(
            AclPermissionEvaluator evaluator) {
        DefaultMethodSecurityExpressionHandler handler =
                new DefaultMethodSecurityExpressionHandler();
        handler.setPermissionEvaluator(evaluator);
        return handler;
    }

    @Bean
    static AclPermissionEvaluator aclPermissionEvaluator(
            AclService service) {
        return new AclPermissionEvaluator(service);
    }

    @Bean
    JdbcMutableAclService mutableAclService(
            DataSource dataSource,
            LookupStrategy lookup,
            AclCache cache) {
        return new JdbcMutableAclService(dataSource, lookup, cache);
    }

    @Bean
    LookupStrategy lookupStrategy(
            DataSource dataSource,
            AclCache cache,
            AclAuthorizationStrategy authStrategy,
            PermissionGrantingStrategy grantStrategy) {
        return new BasicLookupStrategy(
                dataSource, cache, authStrategy, grantStrategy);
    }

    @Bean
    AclCache aclCache(PermissionGrantingStrategy grantStrategy,
                      AclAuthorizationStrategy authStrategy) {
        return new SpringCacheBasedAclCache(
                new ConcurrentMapCache("aclCache"),
                grantStrategy, authStrategy);
    }

    @Bean
    AclAuthorizationStrategy aclAuthorizationStrategy() {
        return new AclAuthorizationStrategyImpl(
                new SimpleGrantedAuthority("ROLE_ACL_ADMIN"));
    }

    @Bean
    PermissionGrantingStrategy grantStrategy() {
        return new DefaultPermissionGrantingStrategy(
                new ConsoleAuditLogger());
    }
}
~~~

Đây là **trích đoạn bean configuration**: thiếu imports để ngắn gọn; các class tương ứng ở packages `org.springframework.security.acls.*`, `org.springframework.security.access.expression.method.*`, `org.springframework.cache.concurrent.*`, `org.springframework.security.config.annotation.method.configuration.*` và `javax.sql.DataSource`. Mẫu bean/wiring dựa trên reference ACL chính thức. Nó chưa khai báo `SecurityFilterChain`, JPA entity, JDBC driver-specific SQL, migrations hay repository, vì thế **không phải dự án Spring Boot tự chạy chỉ bằng khối này**.

### 6.2. Schema và DB dialect

Bốn bảng cần có:
- `acl_sid`
- `acl_class`
- `acl_object_identity`
- `acl_entry`

Một cấu hình ACL JDBC mới có thể thất bại ở `createAcl` vì bảng chưa có, ID generation query không đúng dialect hoặc key constraint. `JdbcMutableAclService` có default SQL phù hợp mẫu HSQLDB; với một số DB khác cần chỉnh `sidIdentityQuery`, `classIdentityQuery`, `objectIdentityPrimaryKeyQuery` hoặc câu SQL tương ứng. Không copy nguyên DDL HSQLDB sang PostgreSQL/MySQL rồi mặc định hoạt động.

Bảo đảm unique constraint hợp lý trên cặp class + object identity, foreign keys và indexes phục vụ ACL lookup. Nên có migration được versioning, kiểm thử tạo nhiều object liên tiếp và đọc quyền sau commit.

### 6.3. Có thể dùng JPA và ACL JDBC trong cùng transaction không?

Có thể **nếu chúng thực sự chia sẻ cùng transaction resource**: ví dụ cấu hình `JpaTransactionManager` thích hợp cho JPA `EntityManager` và JDBC access trên **cùng DataSource**. Đừng chỉ dựa vào annotation `@Transactional` để suy ra mọi connection ở mọi bean đều chung transaction. Những trường hợp làm mất tính nguyên tử:

- Entity lưu tại DB-A, ACL lưu tại DB-B.
- ACL dùng DataSource độc lập hoặc connection không tham gia transaction.
- `@Transactional(propagation = REQUIRES_NEW)` ở helper ACL khiến ACL commit trước transaction domain.
- Dùng `@Async` để ghi ACL trên worker thread khác; transaction context không được tự truyền sang.
- Sau khi đã tạo domain, bắn event `AFTER_COMMIT` mới tạo ACL mà không có trạng thái pending/compensation.
- Gọi method transactional bằng self-invocation, advice không hoạt động.

**Phải chứng minh bằng integration test:** giả lập ACL write failure rồi kiểm tra trong DB sau transaction rằng **không còn Document cũng không còn ACL/ACE**. Nếu không có rollback đồng bộ, cần một kiến trúc eventual provisioning có trạng thái khóa truy cập an toàn.

## 7. API create và cách phản hồi

Controller nhận input từ client, nhưng quyền và tenant do security/service quyết định:

~~~java
@RestController
@RequestMapping("/api/documents")
class DocumentController {
    private final CreateDocumentService service;

    DocumentController(CreateDocumentService service) {
        this.service = service;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    Map<String, Long> create(
            @Valid @RequestBody NewDocument request) {
        Long id = service.create(request);
        return Map.of("id", id);
    }
}
~~~

Đây là trích đoạn phụ thuộc service/record của phần trước; import từ Spring Web, Jakarta Validation và `java.util.Map`. Có thể thêm header `Location: /api/documents/{id}` theo REST contract.

Kết quả mong muốn:
- Caller đã xác thực và có `document:create`, input đúng, domain+ACL commit: **201** cùng ID.
- Thiếu authority: thường **403**, trước khi lưu.
- Chưa xác thực: thường **401** với HTTP Basic/Bearer theo entry point.
- `title` trống hoặc vượt giới hạn: **400** với `@Valid` trong Spring MVC.
- Cơ sở dữ liệu ACL lỗi: **không trả thành công giả**; rollback và trả lỗi server có kiểm soát, không lộ SQL/tenant/ACL internals.
- Request bị gửi lặp: xử lý theo idempotency policy; không tự tạo hai Document và hai ACL ngoài dự kiến.

**CSRF:** Nếu dùng session/cookie, POST cần token hợp lệ khi CSRF protection bật; test MockMvc có thể cần `with(csrf())`. Đây là bảo vệ HTTP request, độc lập với tạo ACL.

## 8. Khi nào dùng parent ACL và entriesInheriting?

Một Document nằm trong Folder có thể cần nhận READ từ folder, nhưng **không tự đồng nghĩa được phép thừa hưởng tất cả quyền**. Với object mới tạo, phải quyết định inheritance theo policy.

### 8.1. Mặc định không kế thừa

Trong service ở trên:

~~~java
acl.setEntriesInheriting(false);
~~~

Điều này làm rõ rằng Document chỉ dựa trên local ACE của nó cho đến khi được cấu hình quan hệ cha hợp lệ. Không có parent link hoặc inheritance đúng thì Spring ACL không tự dò folder trong bảng domain.

### 8.2. Kế thừa có chủ đích từ Folder

~~~java
// Trích đoạn trong transaction và sau khi đã xác minh quyền.
ObjectIdentity parentId =
        new ObjectIdentityImpl(Folder.class, trustedFolderId);
Acl parentAcl = aclService.readAclById(parentId);

MutableAcl childAcl = aclService.createAcl(documentId);
childAcl.setParent(parentAcl);
childAcl.setEntriesInheriting(true);
childAcl.insertAce(childAcl.getEntries().size(),
        BasePermission.READ, creatorSid, true);
aclService.updateAcl(childAcl);
~~~

Ở đây `documentId` là một `ObjectIdentity`, không phải Long thô; `trustedFolderId` đến từ domain/service đã xác minh. Không lấy arbitrary parent ID từ request rồi cho child ACL trỏ sang ACL tenant khác.

**Hai điểm cần ghi nhớ:**
1. `setParent(parentAcl)` chỉ tạo liên kết; `entriesInheriting` điều khiển có tham khảo quyền từ cha khi không có ACE phù hợp.
2. Kế thừa theo Spring ACL không có cờ sẵn “chỉ READ, không WRITE”. Nếu parent có WRITE và child inherit, WRITE có thể lan khi không có local ACE tương ứng. Với tài liệu nhạy cảm, nên tắt inheritance hoặc thêm required policy/boundary kiểm soát WRITE.

### 8.3. ACL cha chưa có

Nếu Folder chưa có ACL, không tự tạo một parent ACL trống từ client input rồi cấp quyền bất ngờ. Chọn chính sách:
- Reject việc tạo Document cho đến khi Folder được provisioning hợp lệ.
- Hoặc tạo ACL Folder bằng workflow quản trị riêng có cùng transaction.
- Hoặc tạo Document private, inheritance false, chỉ gán parent sau khi valid.

**Không bắt `NotFoundException` rồi tự grant toàn bộ quyền để “giữ hoạt động”.** Một ACL thiếu dữ liệu là dấu hiệu cần provisioning/repair, không phải lý do bỏ kiểm tra.

## 9. Idempotency, retry và tạo trùng ACL

### 9.1. Đừng nhầm retry với createAcl trên cùng ID

`MutableAclService.createAcl(oi)` sẽ báo `AlreadyExistsException` khi ACL đã tồn tại. Với request create thường có ID DB mới, retry không kiểm soát có thể tạo **Document mới** rồi ACL mới; không phải duplicate ACL cùng ID, nhưng lại duplicate business object.

Chiến lược thường dùng:
- Client gửi `Idempotency-Key` khi tạo Document.
- Server ràng buộc key với principal/tenant và fingerprint nội dung.
- Lưu kết quả tạo (documentId, status) với unique constraint trên key/phạm vi.
- Retry cùng key trả lại cùng documentId **khi transaction hoàn tất**; không tạo lần nữa.
- Một request trùng key nhưng payload khác bị từ chối có kiểm soát (ví dụ 409 theo API contract).
- Kết quả idempotency phải được lưu atomic với domain/ACL khi có thể; nếu không, có quy trình reconcile.

### 9.2. Có nên bắt AlreadyExists rồi tiếp tục?

Chỉ nếu nghiệp vụ thiết kế rõ **ensure ACL exists**, không phải thao tác “create fresh ACL”. Một service repair/migration có thể đọc ACL hiện hữu và sửa theo policy **sau khi** xác thực ObjectIdentity thuộc đúng domain/tenant. Trong request tạo mới, một ACL đã tồn tại cho ID đang cấp thường là **bất thường cần điều tra**; đừng tự thêm ACE vào ACL mà chưa biết nguồn gốc hoặc owner.

### 9.3. Concurrent create

Unique key trên `acl_class + object_id_identity` ngăn ACL trùng cho cùng một object. Nếu nhiều request cố tạo ACL cùng ID, một request có thể thắng, request khác gặp constraint/`AlreadyExistsException`. Không dùng pattern “check exists → create” mà không có DB constraint: hai thread có thể cùng thấy không tồn tại.

Idempotency của endpoint và unique constraint ACL giải quyết **hai vấn đề khác nhau**: một ngăn tạo trùng nghiệp vụ khi client retry, một ngăn trùng chính sách cho cùng ObjectIdentity.

## 10. Tính nguyên tử và trạng thái lỗi giữa các bước

| Bước thất bại | Nếu cùng transaction thực sự | Nếu các nguồn commit riêng |
| --- | --- | --- |
| `saveAndFlush` thất bại | Không có Domain/ACL hoàn chỉnh | Không ghi tiếp; xử lý lỗi DB |
| `createAcl` thất bại | Rollback Document | Có thể còn Document “mồ côi ACL” |
| `insertAce` hoặc `updateAcl` thất bại | Rollback Document và ACL đã tạo | Có thể còn ACL trống/thiếu ACE |
| Commit transaction thất bại | Rollback tất cả resource tham gia | Không thể suy ra trạng thái cả hai nguồn |
| Response mất sau commit | Client tưởng lỗi nhưng Document+ACL đã commit | Cần idempotency key để trả đúng kết quả |
| Job tạo ACL bị trì hoãn | Không nên trả object công khai trước khi cấp quyền | Phải có state PENDING và fail-closed read/write |

**Quy tắc an toàn:** nếu yêu cầu nghiệp vụ là “Document không tồn tại nếu ACL không được tạo”, transaction phải bao được cả hai phần. Nếu không làm được, model hóa “provisioning chưa hoàn tất” như một trạng thái **không thể đọc/chia sẻ/ghi** cho tới khi ACL có hiệu lực.

### 10.1. @TransactionalEventListener AFTER_COMMIT có phù hợp không?

Nếu bạn tạo Document rồi phát event `@TransactionalEventListener(phase = AFTER_COMMIT)` để tạo ACL, event chỉ chạy **sau khi Document đã commit**. Điều này có thể phù hợp với hệ thống eventual consistency có trạng thái `PENDING_ACL`; nhưng **không cung cấp atomicity** giữa Domain row và ACL row.

Nếu listener thất bại hoặc process chết, có thể còn Document chưa có ACL. Muốn kiến trúc bền vững:
- Commit Domain ở trạng thái PENDING cùng bản ghi outbox.
- Worker đọc outbox, provision ACL idempotently, kiểm tra owner/tenant/ACE, chuyển trạng thái ACTIVE.
- Query/read/write đều chặn Document chưa ACTIVE, kể cả khi thiếu ACL.
- Retry backoff, dead-letter/alert và reconciliation job; audit khi cần manual repair.
- Chỉ thông báo “tạo xong và có thể sử dụng” sau provisioning hoàn tất theo API contract.

### 10.2. Khi hai database không thể cùng transaction

Dùng orchestration/saga hoặc outbox với compensating actions. Tuyệt đối không gọi một transaction local rồi tự nhận có đảm bảo all-or-nothing cross-database. Trong các trường hợp nhạy cảm, cân nhắc thiết kế ACL cùng database/domain schema để giảm complexity và dễ chứng minh nhất quán.

## 11. Đọc lại ACL sau commit và kiểm chứng quyền thực sự

Một lần gọi `createAcl` thành công không chứng minh ACE đã tồn tại, vì ACE chỉ persist ở `updateAcl`. Integration test nên đọc lại qua `AclService` sau khi transaction hoàn tất:

~~~java
// Trong integration test có DB thật và principal phù hợp.
ObjectIdentity oi = new ObjectIdentityImpl(Document.class, documentId);
Sid alice = new PrincipalSid("alice");

Acl acl = aclService.readAclById(oi, List.of(alice));

assertEquals(oi, acl.getObjectIdentity());
assertTrue(acl.isGranted(
        List.of(BasePermission.READ), List.of(alice), false));
assertTrue(acl.isGranted(
        List.of(BasePermission.WRITE), List.of(alice), false));
~~~

Đây là trích đoạn JUnit với các import `Acl`, `Sid`, `ObjectIdentity`, `BasePermission` và static assertions. Kết quả test cần chứng minh:
- ACL của đúng Document type + ID đã tồn tại.
- `getEntries()` có đúng ACE dự định (không grant tràn cho ROLE_USER hoặc principal khác).
- Owner đọc được READ/WRITE theo policy; người khác không được cấp quyền.
- READ/WRITE được kiểm tra qua Spring method security/`AclPermissionEvaluator` khi gọi service thực.
- Sau rollback mô phỏng, cả Document và ACL không còn trong DB.

`Acl.isGranted(...)` có thể ném `NotFoundException` khi không có ACE phù hợp cho người khác; test negative nên xử lý theo contract thay vì mặc định assert false trực tiếp. Một số kiểm tra còn cần gọi `AclService.readAclById(oi)` không SID filter hoặc cung cấp danh sách SID phù hợp để tránh incomplete ACL khi inspection.

### 11.1. Chọn test transaction đúng mục tiêu

Một method `@SpringBootTest @Transactional` thường rollback toàn bộ dữ liệu fixture khi test kết thúc. Điều đó hữu ích, nhưng chưa chứng minh **commit production path**. Với test cần xác minh sau commit:
- Gọi service qua Spring bean/proxy ngoài transaction của test, hoặc dùng `TestTransaction` để chủ động kết thúc và bắt đầu transaction.
- Sau khi service return, đọc lại ACL từ DB bằng một connection/transaction mới.
- Kịch bản failure injection khiến `updateAcl` ném runtime exception, rồi xác nhận không còn cả domain record lẫn ACL.
- Test thật với dialect production hoặc Testcontainers để phát hiện khác biệt identity query, FK, schema và transaction enlistment.

Không thay integration test bằng mock `MutableAclService` rồi kết luận DB rollback đã đúng.

## 12. Unit test workflow và integration test: kiểm gì ở mỗi tầng?

### 12.1. Unit test kiểm trình tự gọi đúng

Một unit test dùng Mockito có thể fake repository và ACL service để chứng minh:
1. Lưu domain trước khi gọi createAcl.
2. `ObjectIdentity` dùng đúng ID vừa được cấp.
3. Creator SID được lấy từ actor tin cậy.
4. Insert READ/WRITE, không thêm quyền DELETE hoặc ACE public.
5. `updateAcl` chỉ gọi sau khi đã chèn ACE.
6. Lỗi `createAcl` được lan ra, không return ID thành công.

Ví dụ đoạn khung kiểm thử (không phải file đầy đủ vì thiếu fixtures của domain):

~~~java
// Trong @ExtendWith(MockitoExtension.class) test.
InOrder order = inOrder(repository, aclService, mutableAcl);

order.verify(repository).saveAndFlush(any(Document.class));
order.verify(aclService).createAcl(any(ObjectIdentity.class));
order.verify(mutableAcl).setEntriesInheriting(false);
order.verify(mutableAcl).insertAce(
        eq(0), eq(BasePermission.READ),
        eq(new PrincipalSid("alice")), eq(true));
order.verify(mutableAcl).insertAce(
        eq(1), eq(BasePermission.WRITE),
        eq(new PrincipalSid("alice")), eq(true));
order.verify(aclService).updateAcl(mutableAcl);
~~~

**Lưu ý:** `InOrder` với nhiều mocks phải match các lời gọi thực đúng thứ tự; nếu mock repository có thêm nội bộ hoặc mock ACL bị gọi `getEntries().size()`, có thể cần stub `getEntries()` và/hoặc chỉ verify các lời gọi chính. Ví dụ có chủ đích minh họa, không thể dán riêng rồi chạy mà không có các mock và import Mockito.

Unit test **không kiểm chứng** `@Transactional`, `@PreAuthorize`, schema ACL, generated ID hay cache. Những vấn đề đó thuộc integration test.

### 12.2. Integration test nghiệp vụ + ACL JDBC

Các case thiết yếu:

| Case | Kỳ vọng |
| --- | --- |
| Alice có `document:create`, title hợp lệ | Document và ACL/READ/WRITE cùng xuất hiện |
| Alice thiếu `document:create` | `AccessDeniedException`, không tạo Document hoặc ACL |
| Title rỗng/quá dài | HTTP 400/validation theo contract, không tạo |
| Repository không cấp ID | Lỗi, không tạo ACL với ID null |
| ACL create lỗi | Rollback Document; không trả 201 |
| ACL update lỗi sau create | Rollback cả ACL rỗng và Document |
| Trùng ObjectIdentity | `AlreadyExistsException` hoặc xử lý idempotency đúng, không mở rộng quyền ngoài ý muốn |
| ACL owner khác actor nghiệp vụ | Phải có policy rõ, không vô ý cấp admin |
| Tenant không xác minh được | DENY trước khi lưu |
| Creator là Alice | Chỉ Alice được READ/WRITE theo ACE, Bob bị deny |
| Re-submit cùng Idempotency-Key | Một Document và một ACL, trả cùng ID |
| Parent Folder khác tenant | Reject hoặc private, không inherit nhầm |
| DB/caches nhiều instance | Quyền mới và revoke tuân thủ consistency contract |
| Nhiều request tạo song song | Unique constraints/idempotency hoạt động, không duplicate ACL |
| App restart, reload ACL | Quyền vẫn đúng, không chỉ là in-memory state |

### 12.3. Test @PreAuthorize và @Transactional qua proxy

`@Autowired CreateDocumentService service` lấy bean Spring để Spring AOP intercept. Thêm ít nhất một test grant và một test deny; nếu chỉ test deny, một cấu hình deny-all sai vẫn có thể cho test xanh. Dùng `@WithMockUser` hoặc test request `httpBasic(...)`/`jwt()` tùy mức kiểm thử.

Không dùng `new CreateDocumentService(...)` và kết luận annotation có chạy. Self-invocation `this.create(...)` cũng có thể bỏ qua proxy. Nếu controller mock cả service, test controller không chứng minh ACL workflow được thi hành.

## 13. Java 17 độc lập: mô phỏng tạo business object và ACL một bước

Chương trình sau dùng JDK thuần, không phụ thuộc Spring. Nó minh họa nguyên tắc: **tạo data và ACL ở vùng staging, chỉ publish kết quả khi đã có đầy đủ cả hai**. Trong ví dụ, một `Bundle` chứa Document và ACL được put vào **một map** trong một bước. Đây là mô hình học tập, **không phải transaction manager hoặc JDBC ACL thật**.

Lưu thành `ProvisioningDemo.java`:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;

public class ProvisioningDemo {
    record Document(long id, String owner, String title) {}
    record Acl(long documentId, String sid, Set<String> permissions) {}
    record Bundle(Document document, Acl acl) {}

    static final class Store {
        private final Map<Long, Bundle> committed = new LinkedHashMap<>();
        private long nextId = 1L;

        synchronized long create(String actor, String title,
                                 boolean failProvisioning) {
            if (actor == null || actor.isBlank()
                    || title == null || title.isBlank()) {
                throw new IllegalArgumentException("Invalid input");
            }

            long id = nextId++; // ID có trước ACL; sequence có thể có khoảng trống.
            Document document = new Document(id, actor, title);
            Acl acl = new Acl(id, actor, Set.of("READ", "WRITE"));

            // Mô phỏng lỗi trước khi publish bundle.
            if (failProvisioning) {
                throw new IllegalStateException("ACL provisioning failed");
            }

            committed.put(id, new Bundle(document, acl));
            return id;
        }

        boolean allowed(long id, String actor, String permission) {
            Bundle bundle = committed.get(id);
            return bundle != null
                    && bundle.acl().sid().equals(actor)
                    && bundle.acl().permissions().contains(permission);
        }

        int total() {
            return committed.size();
        }

        int incomplete() {
            int count = 0;
            for (Bundle bundle : committed.values()) {
                if (bundle.document() == null || bundle.acl() == null) {
                    count++;
                }
            }
            return count;
        }
    }

    public static void main(String[] args) {
        Store store = new Store();

        long id = store.create("alice", "Plan A", false);
        System.out.println("created-id=" + id);
        System.out.println("alice-read=" +
                store.allowed(id, "alice", "READ"));
        System.out.println("alice-write=" +
                store.allowed(id, "alice", "WRITE"));
        System.out.println("alice-delete=" +
                store.allowed(id, "alice", "DELETE"));
        System.out.println("bob-read=" +
                store.allowed(id, "bob", "READ"));

        try {
            store.create("bob", "Broken", true);
        } catch (IllegalStateException failed) {
            System.out.println("failed=" + failed.getMessage());
        }

        System.out.println("committed=" + store.total());
        System.out.println("incomplete=" + store.incomplete());
    }
}
~~~

Biên dịch và chạy với JDK 17+:

~~~bash
javac --release 17 ProvisioningDemo.java
java ProvisioningDemo
~~~

**stdout chính xác:**

~~~text
created-id=1
alice-read=true
alice-write=true
alice-delete=false
bob-read=false
failed=ACL provisioning failed
committed=1
incomplete=0
~~~

Phân tích:
- ID 1 được cấp trước khi gắn ACL; Alice có READ/WRITE nhưng không DELETE.
- Bob không được đọc Document 1 vì SID khác.
- Lần tạo của Bob cố ý thất bại **trước khi publish**; `committed` còn một bundle đầy đủ, không có bản ghi thiếu ACL.
- `nextId` có thể tăng ngay cả khi task fail; việc sequence có khoảng trống không phải lỗi transaction.
- Trong DB thật, hai bảng không trở thành atomic chỉ nhờ hai lệnh `put` hoặc code `synchronized`. Phải dùng transaction/constraint/outbox theo kiến trúc.

## 14. Lỗi triển khai thường gặp

### Lỗi 1 — Chỉ lưu JPA entity, quên ACL
`repository.save(...)` không tự insert `acl_object_identity`/`acl_entry`. Người dùng được tạo có thể không đọc lại được, hoặc service khác bypass ACL để đọc. Đặt provisioning trong workflow tạo đối tượng và test ACL sau commit.

### Lỗi 2 — Tạo ACL trước khi có generated ID
`ObjectIdentityImpl(Document.class, entity.getId())` nhận ID chưa sinh. Với JPA generated ID, lưu/flush trước; kiểm tra ID không null. Chọn type + ID ổn định, không tự chuyển từ Long sang String không nhất quán.

### Lỗi 3 — Gọi createAcl rồi quên insertAce/updateAcl
`createAcl` tạo ACL rỗng. ACL owner không tự được READ/WRITE. Thêm ACE theo policy, gọi `updateAcl` rồi đọc lại trong integration test.

### Lỗi 4 — Trao quyền cho ROLE_USER để “creator ai cũng đọc được”
Một `GrantedAuthoritySid("ROLE_USER")` READ trên Document có thể cấp quyền cho **mọi** người có ROLE_USER, không riêng creator. Dùng `PrincipalSid(creator)` hoặc group SID đúng phạm vi.

### Lỗi 5 — Tin creatorId hoặc tenantId do client khai
Client có thể giả `creatorId=bob` hoặc `tenant=other`. Chỉ nhận metadata không nhạy cảm từ payload; creator và tenant phải đến từ authentication/identity service được xác minh.

### Lỗi 6 — Nghĩ @Transactional phủ qua nhiều DB hoặc async
Nếu domain transaction và ACL JDBC dùng hai DataSource/transaction managers khác nhau, rollback có thể chỉ hoàn tác một phần. Kiểm thử fail injection và xác định transaction boundaries thực.

### Lỗi 7 — Tạo ACL sau commit nhưng trả 201 như đã sẵn sàng
Worker có thể chết trước khi tạo ACL. Nếu dùng eventual provisioning, giữ object ở PENDING và chặn truy cập cho tới khi ACL hoàn tất; dùng outbox/retry/reconciliation.

### Lỗi 8 — Bắt AlreadyExists rồi âm thầm mở ACE
Một lỗi race/config có thể dẫn tới ACL của object khác hoặc policy khác. Trong create workflow mới, phân biệt duplicate request/ID và xử lý idempotency; chỉ sửa ACL cũ trong flow được quản trị và xác minh quyền.

### Lỗi 9 — Không kiểm tra phạm vi parent ACL
Child inheriting từ Folder khác tenant có thể nhận grant của tenant lạ. Kiểm tra parent là đối tượng đáng tin, owner/tenant của hai bên, và quyền actor thay đổi parent.

### Lỗi 10 — Lạm dụng ACL admin identity trong request thường
`AclAuthorizationStrategy` có quyền sửa ACL owner/ACE. Đừng cấp `ROLE_ACL_ADMIN` cho mọi người chỉ để `insertAce` không lỗi. Khi ACL mới được tạo, owner hợp lệ thường có khả năng thêm ACE theo strategy; job tạo hộ cần service identity chính danh và audit riêng.

### Lỗi 11 — Không quản lý ACL khi xóa domain object
Xóa Document nhưng giữ ACL gây orphan và rủi ro nếu tái sử dụng ID; xóa ACL quá sớm cũng có thể làm mất quyền của child ACL. Dùng `MutableAclService.deleteAcl(oi, deleteChildren)` theo policy và transaction, phân biệt hard delete/soft delete. `deleteChildren` không nên mặc định true khi có descendants cần giữ.

### Lỗi 12 — Không kiểm soát cache khi ACL mới được cập nhật
ACL cache và application decision cache có thể stale. `updateAcl` phải đi cùng invalidation đúng version; nếu nhiều instance, thiết kế cache consistency. Không tự lưu “allowed=true” trong cache không gắn principal, tenant, object, permission và policy version.

### Lỗi 13 — Test chỉ assert HTTP 201
201 không chứng minh ACL, owner hay ACE đúng. Phải reload qua `AclService`, kiểm tra bảng/permission, thử cả Alice và Bob, lỗi rollback, duplicate request và restart.

### Lỗi 14 — Nhầm quyền create với quyền read sau create
`document:create` chỉ cho phép tạo. Mọi READ/WRITE sau đó vẫn phải áp ACL trên đúng ObjectIdentity, cùng tenant scope và business-state policy.

### Lỗi 15 — Trộn transaction của controller với proxy của service
`@Transactional` trên method bị self-invoke có thể không chạy; controller gửi event async có thể đi khỏi transaction. Đặt boundary ở Spring-managed application service và kiểm thử bằng bean thật.

## 15. Checklist vận hành và bảo mật

| Giai đoạn | Kiểm tra |
| --- | --- |
| Trước create | Authenticated principal hợp lệ, authority `document:create`, tenant từ nguồn server |
| Domain input | `title`/fields hợp lệ, không tin owner/tenant từ client |
| Identity | ID đã sinh, không null, type canonical, không collision ObjectIdentity |
| ACL init | `createAcl` một lần cho object mới, owner SID đúng, không tự grant công khai |
| ACE init | Chính xác READ/WRITE theo policy, không ADMIN/DELETE ngoài chủ đích |
| Inheritance | Mặc định false hoặc parent đã kiểm tra tenant/cấp quyền |
| Persist | `updateAcl` sau insertAce, DB schema/FK/identity query hợp lệ |
| Transaction | JPA và JDBC ACL chia sẻ transaction thực; lỗi giữa chừng rollback chung |
| API response | 201 chỉ sau khi provisioning hợp lệ; lỗi không trả thành công giả |
| Retry | Idempotency-Key và unique constraints, không tạo trùng Document/ACL |
| Test | Unit order, integration after commit, permission grant/deny, rollback, proxy |
| Cache | ACL cache invalidation và multi-instance consistency |
| Lifecycle | Update owner/tenant, move parent, revoke, soft/hard delete, reconciliation |
| Monitoring | Metrics ACL creation failure/orphan, audit an toàn không lộ token/ACL secret |

### Bài tập 1 — Tạo entity và ACL theo thứ tự nào?

Một Document dùng IDENTITY và khi gọi `new Document(...)` thì `getId()==null`. Có nên gọi `createAcl` ngay không?

**Đáp án:** Không. Phải lưu entity để có ID hợp lệ, thường dùng `repository.saveAndFlush(...)` trong transaction trước khi tạo `ObjectIdentity`. Sau đó `createAcl`, thêm ACE, `updateAcl` rồi commit.

### Bài tập 2 — ACL owner có thể đọc không?

Alice là owner ACL mới, nhưng chưa có ACE READ. Lời gọi `hasPermission(documentId, 'Document', 'READ')` chắc chắn true không?

**Đáp án:** Không. ACL ownership chủ yếu phục vụ quyền quản trị ACL, không tự tạo ACE READ. Cần cấp READ tường minh hoặc policy có chủ đích khác.

### Bài tập 3 — Thiếu updateAcl

Service gọi `createAcl(oi)` rồi `insertAce(READ...)` nhưng không gọi `updateAcl(acl)`. Có thể khẳng định ACE đã persisted không?

**Đáp án:** Không. `insertAce` thay đổi mutable ACL object; `updateAcl` là thao tác lưu thay đổi vào database theo contract của `MutableAclService`.

### Bài tập 4 — ACL lỗi nhưng Document còn

Application có hai database: DB-A lưu Document, DB-B lưu ACL. Sau khi A commit, B báo lỗi. `@Transactional` ở service có bảo đảm xóa Document đã commit không?

**Đáp án:** Không nếu không có distributed transaction/coordination. Thiết kế compensation hoặc saga/outbox cùng trạng thái PENDING không cho truy cập, và báo lỗi đúng contract.

### Bài tập 5 — READ theo Folder nhưng WRITE không lan

Document tạo dưới Folder có ACL READ/WRITE cho `ROLE_EDITOR`. Document chỉ nên thừa hưởng READ. Có bật `entriesInheriting=true` rồi mặc định WRITE không lan không?

**Đáp án:** Không. Inheritance không có allow-list per-permission bằng một cờ. Cần cắt kế thừa, tạo local READ hoặc thêm policy bắt buộc hạn chế WRITE, và kiểm thử nhiều SID/ACE.

## 16. Tóm tắt

Một luồng tạo đối tượng có ACL đúng **không dừng ở việc save entity**. Khi DB đã cấp ID:
1. Tạo `ObjectIdentity(type, id)` với convention ổn định.
2. `MutableAclService.createAcl(oi)` để có ACL rỗng hợp lệ.
3. Cấu hình owner/inheritance **có chủ đích**, không cấp quyền dư.
4. `MutableAcl.insertAce(...)` cấp đúng permission cho SID cần thiết.
5. `MutableAclService.updateAcl(acl)` persist ACE.
6. Chỉ trả kết quả hoàn tất sau khi domain và ACL đã commit **nhất quán**; nếu bất đồng bộ, phải có trạng thái PENDING và cơ chế hồi phục an toàn.

**Nguyên tắc cốt lõi:** *Tạo quyền cho object mới là một phần của nghiệp vụ tạo object, có identity/transaction/idempotency riêng; không phải hiệu ứng tự nhiên của một lệnh repository.save().*

## Tài liệu tham khảo chính thức

- [Spring Security – Domain Object Security (ACLs)](https://docs.spring.io/spring-security/reference/servlet/authorization/acls.html): ACL model, bốn bảng, `ObjectIdentity`, ví dụ `createAcl → insertAce → updateAcl` và nhận định Spring không tự tạo ACL từ DAO.
- [MutableAclService Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/model/MutableAclService.html): `createAcl`, `updateAcl`, `deleteAcl`, `AlreadyExistsException`, `NotFoundException`.
- [MutableAcl Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/model/MutableAcl.html): `insertAce`, `setParent`, `setEntriesInheriting`, `setOwner`.
- [JdbcMutableAclService Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/jdbc/JdbcMutableAclService.html): JDBC persistence, DB-specific identity query và cấu hình.
- [Spring Security – Security Database Schema](https://docs.spring.io/spring-security/reference/servlet/appendix/database-schema.html): cấu trúc `acl_sid`, `acl_class`, `acl_object_identity`, `acl_entry`.
- [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, interception và biểu thức tùy chỉnh.
- [Spring Framework – Declarative Transactions](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): proxy/`@Transactional` và transaction boundaries.
