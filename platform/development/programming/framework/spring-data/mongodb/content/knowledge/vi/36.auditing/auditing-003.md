# Cung cấp người thao tác bằng AuditorAware

## 1. Tại sao hệ thống cần biết ai đã thao tác?

Trong chương **Auditing** của **Spring Data MongoDB**, hai trường thông dụng là **ai tạo** một document và **ai sửa lần cuối**. Khi nhân viên sửa trạng thái hóa đơn, một scheduled job đồng bộ dữ liệu hoặc một API client tạo đơn hàng, ứng dụng thường muốn lưu:

~~~json
{
  "_id": "invoice-101",
  "tenantId": "tenant-a",
  "status": "APPROVED",
  "created_by": "user-101",
  "modified_by": "user-205",
  "created_at": { "$date": "2026-11-20T08:00:00Z" },
  "updated_at": { "$date": "2026-11-20T08:15:00Z" }
}
~~~

Các field `created_by`, `modified_by` phải lấy từ **nguồn định danh được hệ thống tin cậy**, không phải một chuỗi tùy ý do client gửi. Spring Data cung cấp cơ chế auditing metadata, trong đó:

- `@CreatedBy` đánh dấu property nhận người tạo.
- `@LastModifiedBy` đánh dấu property nhận người sửa gần nhất.
- `@CreatedDate` và `@LastModifiedDate` đánh dấu thời gian tạo/sửa.
- **`AuditorAware<T>`** cung cấp người thao tác hiện tại cho luồng truy cập dữ liệu **imperative**.
- `@EnableMongoAuditing` bật hạ tầng MongoDB auditing và có thể chỉ định bean `AuditorAware`.

Nếu không có một nguồn người thao tác đúng và nhất quán, hai annotation `@CreatedBy` và `@LastModifiedBy` không tự biết request đang thuộc user nào.

### Mục tiêu bài

1. Hiểu `AuditorAware<T>`, `Optional<T> getCurrentAuditor()` và cách Spring Data gắn người thao tác vào entity.
2. Thiết kế entity có `@CreatedBy`/`@LastModifiedBy`, mapping BSON và tùy chọn timestamps.
3. Đăng ký `@EnableMongoAuditing(auditorAwareRef = "...")` để dùng đúng auditor provider.
4. Lấy actor từ Spring Security `SecurityContextHolder`, tránh anonymous principal và user ID do client tự khai báo.
5. Xử lý tác vụ không có HTTP principal: job, batch, scheduler, migration, service account.
6. Phân biệt repository save với `updateFirst`, bulk writes, raw driver và delete operations.
7. Hiểu transaction, retry, optimistic locking, sự khác nhau giữa **audit metadata** và **audit trail**.
8. Kiểm thử sự chuyển đổi `createdBy`/`lastModifiedBy` khi đổi actor trên MongoDB thật, cả raw BSON.
9. Phân biệt `AuditorAware` và `ReactiveAuditorAware` trong ứng dụng reactive.

> Ví dụ sử dụng Java 17+, Spring Boot 3.x và Spring Data MongoDB 4.x. Các chi tiết như callback ordering, xác định entity mới và tác động của những đường update riêng có thể thay đổi theo API/phiên bản; cần integration test trên tổ hợp dependency đang dùng. Đây là bài về **metadata auditing**, chưa phải cơ chế audit log bất biến đáp ứng mọi yêu cầu pháp lý.

## 2. Auditing metadata khác nhật ký nghiệp vụ

Một document hóa đơn thường cần bốn câu hỏi:

| Câu hỏi | Field phù hợp | Cơ chế |
|---|---|---|
Ai tạo bản ghi? | `createdBy` | `@CreatedBy` + `AuditorAware` |
Ai sửa bản ghi gần nhất? | `lastModifiedBy` | `@LastModifiedBy` + `AuditorAware` |
Tạo lúc nào? | `createdAt` | `@CreatedDate` |
Sửa lần cuối lúc nào? | `lastModifiedAt` | `@LastModifiedDate` |

Nhưng các field này **không trả lời**:

- Ai đã sửa hóa đơn **mọi lần** trong quá khứ?
- Giá trị nào đã thay đổi, trước/sau là bao nhiêu?
- Thao tác có được duyệt bởi hai người không?
- Document có bị ghi đè trực tiếp qua driver/script không?
- Người dùng có giả mạo định danh hoặc tài khoản bị chiếm quyền không?
- Transaction chứa thao tác đó đã commit chưa?

`lastModifiedBy` chỉ là một **snapshot metadata**, không phải toàn bộ audit history. Nếu nghiệp vụ yêu cầu truy vết đầy đủ, cần audit event/ledger/outbox/change streams hoặc một giải pháp ghi lịch sử được kiểm soát, có retention và quyền truy cập rõ.

### 2.1. Không nhầm actor với subject

Ví dụ admin sửa thông tin cho khách hàng:

~~~text
actor = nhân viên admin user-205
subject = khách hàng customer-901
tenant = tenant-a
operation = APPROVE_INVOICE
~~~

`@LastModifiedBy` thường lưu **actor**, không phải customer ID là đối tượng bị thao tác. Nếu muốn lưu cả actor và subject, đó là hai field/khái niệm khác nhau. Không dùng `tenantId`, `createdBy` và `customerId` hoán đổi.

### 2.2. Nguồn dữ liệu phải đáng tin cậy

Một HTTP header như:

~~~http
X-Actor-Id: admin
~~~

không tự phải là bằng chứng actor là admin. Chỉ dùng một giá trị identity đã **được xác thực và ủy quyền** bởi security layer, chẳng hạn principal trong Spring Security sau khi JWT/session được kiểm tra.

## 3. Bản đồ lifecycle của Spring Data auditing

Khi repository lưu một entity thông qua Spring Data mapping, auditing infrastructure có thể tham gia pipeline **trước khi converter gửi BSON tới MongoDB**.

~~~mermaid
flowchart TD
    A["HTTP/worker đã xác thực"] --> B["Spring Security context / actor provider"]
    B --> C["AuditorAware.getCurrentAuditor()"]
    D["repository.save(entity)"] --> E["Spring Data auditing callback"]
    C --> E
    E --> F["Gán @CreatedBy/@LastModifiedBy phù hợp"]
    F --> G["MappingMongoConverter: Java -> BSON"]
    G --> H["MongoDB write"]
    H --> I["Trả entity / write result"]
~~~

Khi lưu entity mới, auditing thường điền người tạo và người sửa theo cấu hình. Khi lưu entity đã tồn tại, auditing thường giữ nguyên người tạo và cập nhật người sửa. Tuy nhiên:

1. Framework phải nhận diện entity **new** hay **existing** theo cơ chế mapping/version/`Persistable`.
2. Cơ chế auditing phải được **bật** và `AuditorAware` phải có bean phù hợp.
3. Write path phải sử dụng entity lifecycle được Spring Data hỗ trợ.
4. `getCurrentAuditor()` phải trả actor phù hợp; `Optional.empty()` có nghĩa không cung cấp actor, **không phải người thao tác rỗng hợp lệ**.
5. Mọi update thực hiện bằng raw driver hoặc update operators không chắc đi qua cùng entity callback.

**Auditing metadata được chuẩn bị trước một lần ghi không đồng nghĩa transaction đã commit.** Nếu transaction rollback, metadata vừa chuẩn bị không được xem là chứng cứ giao dịch đã được chấp nhận bền vững.

### 3.1. Thứ tự hoạt động ở mức khái niệm

~~~text
Application service
    └─ repository.save(entity)
         ├─ phát hiện new/existing
         ├─ auditing callback yêu cầu AuditorAware
         ├─ cập nhật createdBy/modifiedBy/date
         ├─ mapping entity thành BSON
         ├─ MongoDB insert / save
         └─ trả kết quả
~~~

Không đọc sơ đồ này như cam kết thứ tự tuyệt đối giữa mọi callback tùy biến, events, version increment hay các trường hợp store-specific auditing. Nếu viết callback tự phụ thuộc `lastModifiedBy` đã có, kiểm thử thực tế hoặc thiết kế thay đổi tại service/domain thay vì dựa vào thứ tự chưa được định nghĩa.

## 4. Hợp đồng AuditorAware<T>

Giao diện Spring Data:

~~~java
package org.springframework.data.domain;

import java.util.Optional;

public interface AuditorAware<T> {
    Optional<T> getCurrentAuditor();
}
~~~

Đoạn này chỉ minh họa hợp đồng công khai của API; **không tạo lại interface `org.springframework.data.domain.AuditorAware` trong dự án**.

Một implementation đơn giản:

~~~java
import java.util.Optional;
import org.springframework.data.domain.AuditorAware;

public class FixedActorAuditorAware
        implements AuditorAware<String> {

    @Override
    public Optional<String> getCurrentAuditor() {
        return Optional.of("system:demo");
    }
}
~~~

Nó luôn trả cùng một actor, dễ dùng làm minh họa hoặc một test fixture, nhưng **không phù hợp với hệ thống có nhiều user đăng nhập** vì mọi document đều mang cùng danh tính.

### 4.1. Generic type phải phù hợp field audit

| Khai báo field | Provider phù hợp |
|---|---|
`@CreatedBy private String createdBy` | `AuditorAware<String>` |
`@CreatedBy private UUID createdBy` | `AuditorAware<UUID>` hoặc conversion được thiết kế rõ |
`@CreatedBy private ActorRef createdBy` | `AuditorAware<ActorRef>` với mapping/converter phù hợp |

Nếu field dùng `String` nhưng provider trả một entity `User` có nhiều quan hệ, đừng mặc định converter có thể lưu đúng rồi truy vấn tốt. Nên lưu **stable user ID** đơn giản nếu yêu cầu chỉ là “ai đã thao tác”.

### 4.2. Optional.empty() không tương đương anonymous

~~~java
@Override
public Optional<String> getCurrentAuditor() {
    return Optional.empty();
}
~~~

`Optional.empty()` là **không cung cấp auditor** cho lần gọi này. Spring Data không tự biến kết quả rỗng thành `"anonymous"`, `"system"` hoặc một tài khoản mặc định duy nhất. Với entity mới, metadata actor có thể không được điền; với một entity cũ, thay đổi auditor fields phụ thuộc state/callback của phiên bản đang dùng.

Nếu chính sách yêu cầu **mọi write phải có actor**, cần thiết kế từ chối thao tác thiếu identity ở service/security boundary hoặc dùng một system actor đã được xác định rõ. Đừng im lặng gán mọi request không có principal thành admin.

### 4.3. AuditorAware là nguồn identity, không phải permission checker

`AuditorAware` có chức năng cung cấp danh tính, **không quyết định user được phép sửa hóa đơn nào**. Authorization phải kiểm tra ở service/policy và lọc `tenantId` trong query. Một request đã được xác thực vẫn có thể không có quyền sửa hóa đơn tenant khác.

## 5. Entity hóa đơn với @CreatedBy và @LastModifiedBy

Ví dụ sử dụng collection `audit_invoices` và hai field BSON `created_by`, `modified_by`.

**AuditInvoice.java**

~~~java
package com.example.audit;

import java.time.Instant;
import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "audit_invoices")
public class AuditInvoice {

    @MongoId(FieldType.STRING)
    private String id;

    private String tenantId;
    private String status;

    @CreatedBy
    @Field("created_by")
    private String createdBy;

    @LastModifiedBy
    @Field("modified_by")
    private String lastModifiedBy;

    @CreatedDate
    @Field("created_at")
    private Instant createdAt;

    @LastModifiedDate
    @Field("updated_at")
    private Instant updatedAt;

    @Version
    private Long version;

    protected AuditInvoice() {
        // Dành cho MongoDB converter.
    }

    public AuditInvoice(String id, String tenantId, String status) {
        this.id = id;
        this.tenantId = tenantId;
        this.status = status;
    }

    public String getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getStatus() { return status; }
    public String getCreatedBy() { return createdBy; }
    public String getLastModifiedBy() { return lastModifiedBy; }
    public Instant getCreatedAt() { return createdAt; }
    public Instant getUpdatedAt() { return updatedAt; }
    public Long getVersion() { return version; }

    public void setStatus(String status) {
        this.status = status;
    }
}
~~~

Ở model này:

- Caller không cần setter công khai cho `createdBy`/`lastModifiedBy`; auditing metadata được quản lý theo lifecycle.
- Java field `createdBy` được lưu dưới BSON `created_by`.
- Java field `lastModifiedBy` được lưu dưới BSON `modified_by`.
- `@CreatedDate`/`@LastModifiedDate` được điền qua auditing date provider.
- `@Version Long` minh họa optimistic locking khi repository save entity đã đọc; không phải điều kiện bắt buộc để bật auditing.
- `tenantId` không được tự đặt lại theo auditor trong callback. Actor và tenant là hai khái niệm khác nhau.

### 5.1. Repository

**AuditInvoiceRepository.java**

~~~java
package com.example.audit;

import java.util.Optional;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface AuditInvoiceRepository
        extends MongoRepository<AuditInvoice, String> {

    Optional<AuditInvoice> findByIdAndTenantId(
            String id, String tenantId);
}
~~~

Đây là repository **imperative**. Cách đặt tên method dùng property Java như `tenantId`; Spring Data sẽ ánh xạ field vật lý phù hợp. `findByIdAndTenantId` là phương thức thuận tiện cho việc đọc theo tenant, nhưng update phải tiếp tục bảo vệ tenant và trạng thái trong **điều kiện ghi** nếu invariant yêu cầu.

### 5.2. Vì sao dùng Long version?

Với entity có ID được cấp sẵn, một field `@Version Long` bắt đầu bằng `null` giúp Spring Data phân biệt entity mới theo version strategy được hỗ trợ. Khi insert, framework có thể khởi tạo version; các lần save sau dùng điều kiện version để phát hiện stale write.

Không suy từ `id != null` rằng entity đã tồn tại, cũng không tự sửa version trong auditing provider. Entity state detection và optimistic locking phải được kiểm thử trên phiên bản đang dùng.

## 6. Đăng ký Mongo auditing và lựa chọn auditorAwareRef

**InvoiceAuditingConfig.java**

~~~java
package com.example.audit;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.config.EnableMongoAuditing;

@Configuration
@EnableMongoAuditing(
        auditorAwareRef = "currentActorAuditorAware",
        modifyOnCreate = true)
public class InvoiceAuditingConfig {
}
~~~

`@EnableMongoAuditing` bật cơ chế Mongo auditing, trong đó `auditorAwareRef` chọn **bean có tên** `currentActorAuditorAware`. Điều này đặc biệt hữu ích khi application context chứa nhiều `AuditorAware<?>` implementations.

`modifyOnCreate = true` là lựa chọn tường minh trong bài: khi entity mới được tạo, hệ thống có thể điền cả created metadata và last-modified metadata. Nếu nghiệp vụ muốn `lastModifiedBy`/`updatedAt` chỉ có giá trị **sau lần cập nhật đầu tiên**, có thể xem xét `modifyOnCreate = false`, rồi viết test xác minh contract theo phiên bản.

### 6.1. Cơ chế bật auditing không có nghĩa đã có actor

Nếu cấu hình auditing có nhưng không có bean `currentActorAuditorAware` phù hợp, application context có thể thất bại khi tạo auditing infrastructure hoặc không cung cấp auditor theo ý định. Luôn kiểm tra bean registration.

Nếu bean tồn tại nhưng trả `Optional.empty()` vì request không có authenticated principal, annotation không tự sáng tạo một user ID thay thế. Kết quả audit phải được kiểm thử cho cả authenticated và anonymous/system contexts.

### 6.2. @EnableMongoAuditing không cần đặt trên từng entity

`@EnableMongoAuditing` bật infrastructure ở Spring configuration; `@CreatedBy`/`@LastModifiedBy` đặt trên entity fields/properties theo mapping. Không đặt `@EnableMongoAuditing` vào mỗi repository hoặc service.

Nếu Spring Boot app có nhiều configuration classes, cần đảm bảo config được component scan/import, và **không đăng ký nhiều auditing infrastructures xung đột**. Boot starter MongoDB giúp tạo client/template/repository, nhưng đừng coi starter tự chọn đúng một actor provider từ security context mà không cần cấu hình.

### 6.3. AuditorAware không quyết định đồng hồ

`@CreatedBy` và `@LastModifiedBy` lấy actor; timestamps lấy từ auditing time provider. Nếu cần clock có kiểm soát, Spring Data có cơ chế `DateTimeProvider` và thuộc tính cấu hình `dateTimeProviderRef` ở phiên bản hỗ trợ.

Không gọi `Instant.now()` trong `AuditorAware` chỉ để tự điền field thời gian: trộn hai trách nhiệm khiến khó kiểm thử và khó thống nhất timezone/clock.

## 7. Lấy actor từ Spring Security

Trong ứng dụng dùng Spring Security, một cách phổ biến là đọc `SecurityContextHolder` tại thời điểm save.

Dependency thông dụng khi hệ thống sử dụng Spring Security:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-mongodb'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
~~~

Security starter không tự quyết định actor mapping của dự án. Bạn cần phân biệt authenticated principal, anonymous authentication, service account và những request không đi qua HTTP.

**CurrentActorAuditorAware.java**

~~~java
package com.example.audit;

import java.util.Optional;
import org.springframework.data.domain.AuditorAware;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;

@Component("currentActorAuditorAware")
public class CurrentActorAuditorAware
        implements AuditorAware<String> {

    @Override
    public Optional<String> getCurrentAuditor() {
        Authentication auth = SecurityContextHolder
                .getContext()
                .getAuthentication();

        if (auth == null
                || !auth.isAuthenticated()
                || auth instanceof AnonymousAuthenticationToken) {
            return Optional.empty();
        }

        String principalName = auth.getName();
        if (principalName == null || principalName.isBlank()) {
            return Optional.empty();
        }
        return Optional.of(principalName);
    }
}
~~~

Ví dụ tránh:

~~~java
// Không dùng actor do client tự gửi mà chưa được xác thực:
String actor = request.getHeader("X-Actor-Id");
~~~

Với cấu hình Spring Security thông thường, `Authentication.getName()` trả một tên đại diện principal, nhưng **ngữ nghĩa của tên đó phụ thuộc authentication provider**:

- Username/password login có thể trả username.
- JWT resource server có thể ánh xạ từ claim như `sub` tùy converter.
- OAuth2 login có thể dùng một attribute khác.
- Service-to-service token có thể đại diện một service account.

Để làm audit metadata bền vững, hãy xác định contract **stable actor ID** của dự án. Không tự tin rằng display name, email hoặc giá trị từ `getName()` luôn ổn định, duy nhất toàn công ty và được phép lưu lâu dài.

### 7.1. Vì sao loại AnonymousAuthenticationToken?

Trong một số cấu hình Spring Security, anonymous request vẫn có một `Authentication` object và cờ `isAuthenticated()` có thể là `true` theo semantics token. Kiểm tra riêng `instanceof AnonymousAuthenticationToken` giúp tránh ghi `"anonymousUser"` vào field vốn được định nghĩa là user đã xác thực.

Nếu yêu cầu nghiệp vụ muốn lưu actor cho public/anonymous operations, hãy quy định **loại actor riêng**, ví dụ `"public:anonymous"` hoặc request ID, thay vì mặc định coi đó là admin/user thật.

### 7.2. Principal ID không nhất thiết là email

Nếu sử dụng email làm actor:

- Email có thể đổi;
- Cùng cá nhân có nhiều email;
- Email có thể là PII nhạy cảm theo policy;
- Service account đôi khi không có email.

Lưu `userId`/`serviceAccountId` không đổi theo thời gian thường hữu ích hơn. Để hiển thị tên, có thể resolve actor ID qua hệ thống identity với quyền thích hợp. Đừng nhúng token, secret hoặc toàn bộ principal object vào audit fields.

### 7.3. Đọc actor càng gần write càng tốt, nhưng authorization trước write

`AuditorAware` được gọi trong lifecycle của write, vì vậy có thể phản ánh security context đang active lúc đó. Tuy nhiên, authorization **không nên chờ đến callback**. Service phải kiểm tra tenant/role/ownership và áp dụng điều kiện ghi ngay tại database. Auditing chỉ ghi ai đã thao tác trên đường được hỗ trợ, không chặn mọi write trái quyền.

## 8. Một service CRUD dùng auditing đúng trách nhiệm

Sau khi cấu hình `InvoiceAuditingConfig` và `CurrentActorAuditorAware`, service không cần gọi setter `setCreatedBy` hoặc `setLastModifiedBy`.

**InvoiceService.java**

~~~java
package com.example.audit;

import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.stereotype.Service;

@Service
public class InvoiceService {

    private final AuditInvoiceRepository repository;

    public InvoiceService(AuditInvoiceRepository repository) {
        this.repository = repository;
    }

    public AuditInvoice create(
            String authenticatedTenantId,
            String id) {
        requireInput(authenticatedTenantId, id);

        // Domain/policy layer phải kiểm tra quyền CREATE cho tenant.
        AuditInvoice invoice =
                new AuditInvoice(id, authenticatedTenantId, "DRAFT");

        return repository.insert(invoice);
    }

    public AuditInvoice approve(
            String authenticatedTenantId,
            String id) {
        requireInput(authenticatedTenantId, id);

        // Domain/policy layer phải kiểm tra quyền APPROVE.
        AuditInvoice invoice = repository
                .findByIdAndTenantId(id, authenticatedTenantId)
                .orElseThrow(() -> new IllegalArgumentException(
                        "Không tìm thấy hóa đơn được phép truy cập"));

        if (!"DRAFT".equals(invoice.getStatus())) {
            throw new IllegalStateException(
                    "Chỉ hóa đơn DRAFT mới được duyệt");
        }

        invoice.setStatus("APPROVED");

        // @Version giúp phát hiện stale save ở đường repository,
        // không thay thế mọi business CAS.
        return repository.save(invoice);
    }

    private static void requireInput(String tenantId, String id) {
        if (tenantId == null || tenantId.isBlank()
                || id == null || id.isBlank()) {
            throw new IllegalArgumentException(
                    "Tenant/ID không hợp lệ");
        }
    }
}
~~~

**Lưu ý về API repository:** nếu repository mở rộng `MongoRepository<AuditInvoice, String>`, `insert(entity)` là phương thức do Spring Data MongoDB repository cung cấp. `insert` diễn đạt tạo mới rõ ràng hơn `save` khi muốn duplicate key phải bị từ chối, miễn collection/unique constraint đã đúng.

### 8.1. Ai điền createdBy và lastModifiedBy?

Giả sử authenticated user `"user-101"` gọi `create`:

~~~text
Before insert:
  id = invoice-101
  status = DRAFT
  createdBy = null
  lastModifiedBy = null

AuditorAware returns "user-101"
MongoDB insert -> metadata được ghi theo auditing config
~~~

Sau đó authenticated user `"user-205"` gọi `approve`:

~~~text
Before save existing:
  status = APPROVED
  auditing được cung cấp actor "user-205"

Sau save:
  createdBy = "user-101"      (giữ nguyên)
  lastModifiedBy = "user-205" (lần sửa gần nhất)
~~~

Với `modifyOnCreate = true`, `lastModifiedBy` có thể được điền ngay ở lần insert đầu tiên. Không suy rằng field này phải null trên entity mới trong mọi cấu hình.

### 8.2. Cập nhật bằng save vẫn có race nếu thiếu kiểm soát version

Service trên dùng `@Version Long`. Nếu hai request cùng đọc entity DRAFT, một request duyệt và save trước, request kia vẫn cầm version cũ. Save sau có thể bị từ chối bằng `OptimisticLockingFailureException` khi write concern có xác nhận.

Nhưng nếu nghiệp vụ cần một state transition nguyên tử không dựa vào việc load entity trước, một `MongoTemplate.updateFirst` với filter `status = DRAFT` và `tenantId` có thể phù hợp hơn. Khi đó **auditing callback của repository save không mặc định chạy**: phải chủ động xử lý actor và timestamps trong cùng update hoặc thiết kế domain repository riêng.

### 8.3. Không đưa security rule vào query sau khi đã đọc

Sai:

~~~java
AuditInvoice invoice = repository.findById(id).orElseThrow();
if (invoice.getTenantId().equals(authenticatedTenantId)) {
    return repository.save(invoice);
}
~~~

Một lệnh save chỉ theo ID/version không nhất thiết đặt tenant condition vào **chính write predicate**. Đối với multi-tenant domain, cần xác định rõ security policy và bảo vệ invariant trước các cách ghi khác. Với những tình huống nhạy cảm, dùng conditional update theo `_id + tenantId + status/version` thay vì giả định logic Java check trước là atomic.

### 8.4. CreatedBy có nên bất biến?

Ở domain hóa đơn, **người tạo** thường không đổi sau khi document được tạo. Không để API request body gửi `createdBy` rồi chấp nhận mapping trực tiếp vào entity. Chỉ nhận những trường client được phép sửa (ví dụ status/note đã xác thực) và kiểm tra rằng đường ghi không có cơ chế sao chép raw JSON đè các field auditing.

Một mutation trên document bằng raw driver có thể thay field `created_by` nếu database role cho phép; annotation auditing trong Java **không biến field thành immutable ở MongoDB server**. Cần quyền write, schema/policy và kiến trúc audit phù hợp.

## 9. Những actor không đến từ HTTP request

Không phải mọi write đều gắn với một user trong web session. Ví dụ:

| Nguồn thay đổi | Actor mong muốn |
|---|---|
Nhân viên duyệt hóa đơn | `user:<stable-id>` |
Scheduled job đồng bộ trạng thái | `job:invoice-sync` |
Kafka consumer xử lý message từ đối tác | `service:partner-ingest` hoặc actor đã được xác minh từ event |
Migration dữ liệu lịch sử | `migration:2026-11-schema` |
Hệ thống tạo báo cáo | `service:reporting` |
API client theo machine credentials | `service:<client-id>` |

Nếu `CurrentActorAuditorAware` chỉ đọc `SecurityContextHolder`, một job chạy bằng scheduler thông thường có thể nhận `Optional.empty()`. Điều đó **không đồng nghĩa actor là anonymous user**, mà là luồng hiện tại không có security identity được provider nhận diện.

### 9.1. Có ba chiến lược hợp lệ

1. **Service account authentication**: công việc nền chạy với một principal riêng được xác thực và có quyền hạn phù hợp, actor ID là service/job ID ổn định.
2. **Actor execution context đáng tin**: job orchestrator cung cấp actor metadata từ cấu hình server, không từ payload chưa xác thực; provider có thể đọc context đúng lifecycle.
3. **Auditing provider riêng theo module**: module chỉ chạy migration/job được gắn actor cố định, chọn đúng bean qua `auditorAwareRef`.

Không nên tự động trả `"SYSTEM"` cho **mọi** trường hợp thiếu security context trong cả HTTP APIs lẫn background jobs. Cách đó có thể che một lỗi cấu hình authentication khiến thao tác trái quyền mang chữ ký hệ thống.

### 9.2. Actor có định dạng rõ ràng

Một quy ước hữu ích:

~~~text
user:3b2d2f
service:catalog-sync
job:nightly-reconcile
migration:2026-11-audit-backfill
~~~

Tiền tố không phải tính năng bắt buộc của MongoDB hay Spring. Nó chỉ là **domain convention**, giúp người đọc phân biệt actor type và tránh xung đột ID từ nhiều nguồn.

Nếu sau này cần truy vấn theo actor type nhiều, cân nhắc một value object như `ActorRef(type, id)` hoặc metadata riêng; đừng ép toàn bộ thông tin quyền/PII vào một chuỗi dài không có giới hạn.

### 9.3. System fallback phải là policy có chủ đích

Một hệ thống nhỏ chỉ có migration writer có thể dùng:

~~~java
@Component("migrationAuditorAware")
public class MigrationAuditorAware
        implements AuditorAware<String> {

    @Override
    public Optional<String> getCurrentAuditor() {
        return Optional.of("migration:2026-11-backfill");
    }
}
~~~

Fragment này cần imports `java.util.Optional`, `AuditorAware` và `@Component` như ví dụ ở mục 7. Đây là ví dụ dành cho **job/migration context được giới hạn**, không phải bean mặc định thay thế user identity trong mọi endpoint.

Không để hai bean `@Component("currentActorAuditorAware")` và `@Component("migrationAuditorAware")` vô tình cùng được chọn theo type; `auditorAwareRef` chỉ định bean cần dùng cho một auditing configuration cụ thể.

## 10. Thay đổi thread và giới hạn SecurityContextHolder

`SecurityContextHolder` trong cấu hình thông dụng lưu ngữ cảnh bảo mật theo **thread-bound context**. Khi một service dùng:

~~~java
@Async
public void processInvoiceInBackground(...) {
    // Thread khác có thể không có cùng SecurityContext.
}
~~~

actor có thể không còn là user của request khởi tạo. Nguy hiểm hơn, dùng ThreadLocal tùy biến không cleanup có thể **rò identity giữa các công việc** trên pool thread.

### 10.1. Đừng tự sao chép security context một cách vô thức

Spring Security có các công cụ như `DelegatingSecurityContextAsyncTaskExecutor` và context propagation phù hợp; nhưng việc chuyển quyền của user sang job nền kéo dài phải có policy rõ:

- Quyền user có còn hiệu lực khi job chạy sau nhiều giờ?
- Job có được xử lý tenant của user đó?
- Actor của kết quả là user yêu cầu hay service thực thi?
- Một principal bị khóa/thu hồi quyền sau khi enqueue có còn được dùng?

Không tự động truyền toàn bộ token/secret vào job payload để “giữ auditor”. Có thể lưu `requestedByActorId` đã xác minh như **business metadata** và để worker chạy dưới service account, theo contract rõ.

### 10.2. @Async và transaction

Thread mới không tự kế thừa imperative Spring `@Transactional`/`MongoTransactionManager` context, cũng không tự kế thừa auditor. Nếu job cần transaction, mở một transaction boundary phù hợp **ngay trong worker** và gắn actor đáng tin cho worker đó.

Đừng tin rằng method có `@Transactional` ngoài controller sẽ bao mọi write trong `CompletableFuture` do controller tạo ra.

### 10.3. Tránh leak bằng cách thiết kế actor context cục bộ

Nếu hệ thống thực sự cần một ActorContext tùy biến, có thể dùng một scope `try/finally` để khôi phục context sau khi chạy, hoặc một cơ chế task delegation được framework hỗ trợ. Trong reactive pipelines, phải dùng **Reactor Context** thay vì thread-local access đơn giản.

Với dữ liệu audit nhạy cảm, thiếu actor tốt hơn việc âm thầm gán nhầm user — nhưng nếu actor bắt buộc, request/job phải bị từ chối và hệ thống ghi lỗi rõ.

## 11. Một hay nhiều AuditorAware beans?

Trong monolith nhiều module, có thể có:

~~~text
currentActorAuditorAware : AuditorAware<String>
migrationAuditorAware    : AuditorAware<String>
testActorAuditorAware    : AuditorAware<String> (test scope)
~~~

Khi framework cần một `AuditorAware<?>` và có nhiều candidates, injection theo type có thể mơ hồ. Bài dùng:

~~~java
@EnableMongoAuditing(
    auditorAwareRef = "currentActorAuditorAware")
~~~

để chọn rõ bean theo tên.

### 11.1. Không dùng @Primary để che nhầm môi trường

`@Primary` có thể giải quyết một số injection ambiguity nhưng không nên dùng để “thắng” tất cả các auditors mà không kiểm tra. Với auditing, một bean chọn sai có thể khiến metadata của mọi document mang actor không mong muốn trong thời gian dài.

### 11.2. Một audit config cho một application context

Nếu cùng application context có nhiều `@EnableMongoAuditing` configurations với những provider khác nhau, dễ phát sinh registrar/bean conflicts hoặc hành vi khó đoán. Đừng coi việc đặt annotation auditing trên từng module/package là cơ chế tự động “mỗi repository dùng một AuditorAware riêng”.

Khi cần phân loại actor theo nghiệp vụ, thường tốt hơn là một **chính sách identity chung** phản ánh context đã xác thực hoặc tách application contexts rõ ràng. Nếu cần auditing khác nhau theo collection, phải thiết kế custom callbacks/writers có test cụ thể, không kỳ vọng annotation có selector theo repository.

### 11.3. Kiểm tra bean thật

Trong integration test hoặc diagnostic:

~~~java
Map<String, AuditorAware> providers =
        applicationContext.getBeansOfType(AuditorAware.class);
~~~

Fragment trên giả định có `ApplicationContext applicationContext` và import `Map`/`AuditorAware`, không phải file Java độc lập. Kiểm tra **tên bean và lớp implementation**, không chỉ số lượng bean.

## 12. Luồng tạo mới và cập nhật với modifyOnCreate

Với cấu hình mục 6, giả sử hai authenticated actors:

~~~text
T0 — user-101 tạo invoice-101:
  created_by  = user-101
  modified_by = user-101
  created_at  = t0
  updated_at  = t0

T1 — user-205 sửa invoice-101:
  created_by  = user-101
  modified_by = user-205
  created_at  = t0
  updated_at  = t1
~~~

Đây là hành vi mục tiêu trong **đường lưu entity thông thường** với auditing enabled và `modifyOnCreate = true`.

### 12.1. So sánh modifyOnCreate

| Cấu hình | Insert | Update |
|---|---|---|
`modifyOnCreate = true` | Thường đặt cả created và modified metadata | Cập nhật modified metadata |
`modifyOnCreate = false` | Ưu tiên chỉ created metadata | Cập nhật modified metadata |

Không dùng `modifiedBy == null` để suy document chưa từng tồn tại: trong dữ liệu legacy, provider có thể trả empty, hoặc một đường update bypass auditing. Trạng thái mới/cũ nên được xác định theo schema/version và domain invariant chứ không bằng audit metadata duy nhất.

### 12.2. Ai được phép sửa createdBy?

Thông thường, `createdBy` là metadata do persistence layer quản lý. Các thao tác cập nhật status không nên sửa `createdBy`. Nhưng nếu một controller chấp nhận raw document payload rồi gọi raw update, nó có thể sửa field này khi có database write permission.

Giải pháp là **DTO whitelist, service ownership, quyền database và kiểm thử những đường ghi bypass**, không chỉ đặt annotation auditing trên entity.

### 12.3. Tại sao thời gian có thể bằng nhau?

Với insert, created và modified timestamps có thể bằng nhau (cùng một timestamp auditing) tùy provider/cấu hình. Trong integration test, đừng bắt buộc `updatedAt > createdAt` ngay sau insert. Sau update, tùy precision/clock, có thể kiểm tra `updatedAt >= createdAt` và/hoặc chủ động inject test clock nếu cần kiểm tra thời gian chặt.

### 12.4. Auditing và optimistic locking là hai cơ chế khác nhau

`@Version` cung cấp cơ chế phát hiện stale writes trên những đường persistence hỗ trợ. `@LastModifiedBy` ghi actor của lần sửa gần nhất. Cả hai có thể dùng cùng entity, nhưng **auditor không phải version guard**, và version không quyết định ai được phép sửa.

Nếu hai request cùng sửa entity, một save có thể thất bại optimistic lock; đừng báo audit metadata đã được commit chỉ vì callback đã điền field trước khi lệnh save bị từ chối.

## 13. Kiểm thử đơn vị Spring Security AuditorAware

Trước khi kết nối MongoDB, ta có thể kiểm tra riêng việc `CurrentActorAuditorAware` hiểu authenticated, anonymous và context không có principal.

**CurrentActorAuditorAwareTest.java**

~~~java
package com.example.audit;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

class CurrentActorAuditorAwareTest {

    private final CurrentActorAuditorAware provider =
            new CurrentActorAuditorAware();

    @AfterEach
    void cleanup() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void authenticatedPrincipalIsReturned() {
        SecurityContext context =
                SecurityContextHolder.createEmptyContext();

        context.setAuthentication(
                new UsernamePasswordAuthenticationToken(
                        "user-101",
                        "no-credential",
                        List.of(new SimpleGrantedAuthority(
                                "ROLE_OPERATOR"))));
        SecurityContextHolder.setContext(context);

        assertThat(provider.getCurrentAuditor())
                .contains("user-101");
    }

    @Test
    void emptySecurityContextDoesNotBecomeSystem() {
        SecurityContextHolder.clearContext();

        assertThat(provider.getCurrentAuditor()).isEmpty();
    }

    @Test
    void anonymousTokenIsNotAttributedToAuthenticatedUser() {
        SecurityContext context =
                SecurityContextHolder.createEmptyContext();
        context.setAuthentication(
                new AnonymousAuthenticationToken(
                        "test-key",
                        "anonymousUser",
                        List.of(new SimpleGrantedAuthority(
                                "ROLE_ANONYMOUS"))));
        SecurityContextHolder.setContext(context);

        assertThat(provider.getCurrentAuditor()).isEmpty();
    }
}
~~~

Test này không cần MongoDB. Nó chứng minh chính sách **lấy actor từ security context**, nhưng chưa chứng minh auditing Spring Data đã sử dụng provider trong đường `repository.insert/save`.

### 13.1. Các trường hợp cần mở rộng

- JWT principal dùng claim `sub` nhưng business muốn ID nội bộ khác.
- User đăng nhập nhưng `getName()` không được ánh xạ đúng.
- Service account có scope hạn chế; không nhầm với end-user.
- Context đã được xác thực nhưng user bị vô hiệu hóa/khóa giữa một background job dài.
- Lời gọi chạy qua executor mà security context không được truyền.
- Hai requests liên tiếp trên thread pool không được phép thấy cùng actor do context leak.

Việc một unit test `getCurrentAuditor()` pass không chứng minh access-control policy đã thực thi; nó chỉ chứng minh provider nhận dạng input context theo cách lập trình.

## 14. Integration test với AuditorAware thay đổi actor

Đây là bài test quan trọng nhất: **actor A tạo document, actor B sửa document, raw MongoDB BSON phản ánh đúng hai actor**.

Để test độc lập với HTTP authentication, ta dùng một `AuditorAware<String>` có actor điều khiển được trong **test context duy nhất**. Trong production, `CurrentActorAuditorAware` ở mục 7 vẫn lấy actor từ Spring Security.

### 14.1. Provider dùng riêng cho test

**SwitchingAuditorAware.java — đặt trong test sources**

~~~java
package com.example.audit;

import java.util.Optional;
import java.util.concurrent.atomic.AtomicReference;
import org.springframework.data.domain.AuditorAware;

public class SwitchingAuditorAware
        implements AuditorAware<String> {

    private final AtomicReference<String> actor =
            new AtomicReference<>();

    public void useActor(String actorId) {
        actor.set(actorId);
    }

    public void clear() {
        actor.set(null);
    }

    @Override
    public Optional<String> getCurrentAuditor() {
        return Optional.ofNullable(actor.get());
    }
}
~~~

`AtomicReference` chỉ giúp điều khiển fixture trong một test context; **không phải actor provider phù hợp production**. Nếu tests chạy song song cùng bean, hai tests có thể ghi đè actor của nhau. Chạy serial hoặc cô lập context/provider cho từng test.

### 14.2. Test configuration độc lập với production security

**InvoiceAuditingIntegrationTest.java**

~~~java
package com.example.audit;

import static org.assertj.core.api.Assertions.assertThat;

import com.mongodb.client.result.UpdateResult;
import java.time.Instant;
import org.bson.Document;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.data.mongodb.config.EnableMongoAuditing;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

@DataMongoTest
@Import(InvoiceAuditingIntegrationTest.TestAuditingConfig.class)
class InvoiceAuditingIntegrationTest {

    @TestConfiguration(proxyBeanMethods = false)
    @EnableMongoAuditing(
            auditorAwareRef = "testActorAuditorAware",
            modifyOnCreate = true)
    static class TestAuditingConfig {
        @Bean("testActorAuditorAware")
        SwitchingAuditorAware testActorAuditorAware() {
            return new SwitchingAuditorAware();
        }
    }

    @Autowired AuditInvoiceRepository repository;
    @Autowired MongoTemplate mongo;
    @Autowired SwitchingAuditorAware actor;

    @BeforeEach
    void reset() {
        // Chỉ thực hiện trong database test riêng.
        actor.useActor("test:initial");
        repository.deleteAll();
    }

    @Test
    void createdByAndLastModifiedByUseDifferentActors() {
        actor.useActor("user-101");

        AuditInvoice created = repository.insert(
                new AuditInvoice(
                        "invoice-101", "tenant-a", "DRAFT"));

        assertThat(created.getCreatedBy())
                .isEqualTo("user-101");
        assertThat(created.getLastModifiedBy())
                .isEqualTo("user-101");
        assertThat(created.getCreatedAt()).isNotNull();
        assertThat(created.getUpdatedAt()).isNotNull();

        Instant firstCreatedAt = created.getCreatedAt();

        actor.useActor("user-205");
        created.setStatus("APPROVED");
        AuditInvoice updated = repository.save(created);

        assertThat(updated.getCreatedBy())
                .isEqualTo("user-101");
        assertThat(updated.getLastModifiedBy())
                .isEqualTo("user-205");
        assertThat(updated.getCreatedAt())
                .isEqualTo(firstCreatedAt);
        assertThat(updated.getUpdatedAt()).isNotNull();

        AuditInvoice reloaded =
                repository.findById("invoice-101").orElseThrow();
        assertThat(reloaded.getCreatedBy())
                .isEqualTo("user-101");
        assertThat(reloaded.getLastModifiedBy())
                .isEqualTo("user-205");
        assertThat(reloaded.getStatus()).isEqualTo("APPROVED");
    }

    @Test
    void bsonUsesMappedFieldNames() {
        actor.useActor("user-101");
        repository.insert(
                new AuditInvoice("invoice-102", "tenant-a", "DRAFT"));

        Document raw = mongo.getCollection("audit_invoices")
                .find(new Document("_id", "invoice-102"))
                .first();

        assertThat(raw).isNotNull();
        assertThat(raw.getString("created_by"))
                .isEqualTo("user-101");
        assertThat(raw.getString("modified_by"))
                .isEqualTo("user-101");
        assertThat(raw.containsKey("createdBy")).isFalse();
        assertThat(raw.containsKey("lastModifiedBy")).isFalse();
        assertThat(raw.get("created_at")).isNotNull();
        assertThat(raw.get("updated_at")).isNotNull();
    }

    @Test
    void partialUpdateDoesNotApplyEntityAuditorCallback() {
        actor.useActor("user-101");
        repository.insert(
                new AuditInvoice("invoice-103", "tenant-a", "DRAFT"));

        actor.useActor("user-999");

        UpdateResult result = mongo.updateFirst(
                Query.query(Criteria.where("id").is("invoice-103")
                        .and("tenantId").is("tenant-a")),
                new Update().set("status", "APPROVED"),
                AuditInvoice.class);

        assertThat(result.getMatchedCount()).isEqualTo(1L);

        Document raw = mongo.getCollection("audit_invoices")
                .find(new Document("_id", "invoice-103"))
                .first();

        assertThat(raw).isNotNull();
        assertThat(raw.getString("modified_by"))
                .isEqualTo("user-101");
        assertThat(raw.getString("status"))
                .isEqualTo("APPROVED");
    }

    @Test
    void multipleTenantIdsRemainSeparateFromActor() {
        actor.useActor("user-101");
        repository.insert(
                new AuditInvoice("invoice-a", "tenant-a", "DRAFT"));
        repository.insert(
                new AuditInvoice("invoice-b", "tenant-b", "DRAFT"));

        assertThat(repository
                .findByIdAndTenantId("invoice-a", "tenant-b"))
                .isEmpty();
        assertThat(repository
                .findByIdAndTenantId("invoice-a", "tenant-a"))
                .isPresent();
    }
}
~~~

### 14.3. Tại sao test phải dùng MongoDB thật?

`@DataMongoTest` tạo context/test slice cho Spring Data MongoDB, nhưng **không tự chạy MongoDB server**. Cần MongoDB test đã chạy sẵn hoặc Testcontainers, và connection phải trỏ vào database test cô lập.

Test thật kiểm tra được:

1. Auditing infrastructure được tạo bởi `@EnableMongoAuditing`.
2. `auditorAwareRef` chọn đúng bean test.
3. `repository.insert/save` kích hoạt auditing theo mapping lifecycle.
4. `@CreatedBy` không bị ghi đè trên update bình thường.
5. `@LastModifiedBy` đổi khi actor đổi.
6. `@Field` ánh xạ đúng BSON `created_by`/`modified_by`.
7. `updateFirst` không tự biến thành entity `save` để chạy audit callbacks.

Mock repository có thể xác minh method `save` được gọi, nhưng không chứng minh Spring Data auditing hoạt động hoặc BSON được lưu đúng.

### 14.4. Tại sao test không assert timestamp tăng nghiêm ngặt?

Do độ phân giải thời gian, cách gán timestamp hoặc tốc độ thực thi, hai lần ghi có thể có timestamp trùng nhau ở mức millisecond. Test kiểm tra đã có thời gian và thời điểm tạo không đổi; nếu cần kiểm tra chính xác `updatedAt > createdAt`, inject `DateTimeProvider`/clock điều khiển được và định nghĩa policy.

Đừng dùng `Thread.sleep` trong integration test chỉ để “đợi đồng hồ nhảy”, vì làm test chậm/flaky và không chứng minh logic auditing.

### 14.5. Tách test config khỏi production config

Trong ví dụ `@DataMongoTest`, `TestAuditingConfig` cung cấp bean `testActorAuditorAware` thay thế cho kiểm thử. Nếu context đã import `InvoiceAuditingConfig` production với bean `currentActorAuditorAware` và cùng `@EnableMongoAuditing`, có thể phát sinh duplicate registrar/bean hoặc chọn sai provider.

Mỗi test phải biết **auditing config nào đang hoạt động**; không trộn hai `@EnableMongoAuditing` rồi cố đoán bean được dùng. Test cho production security actor thực nên thuộc suite khác với integration test dùng switching fixture.

## 15. Những đường ghi không tự áp dụng AuditorAware

Auditing hoạt động thông qua Spring Data lifecycle trên những operation hỗ trợ. Một thao tác khác có thể **không** materialize và save một entity, nên không có cơ hội gọi auditing callback theo cách tương tự.

| Đường ghi | Điều thường xảy ra | Có tự bảo đảm actor metadata? |
|---|---|---|
`MongoRepository.insert(entity)` | Insert entity qua mapper | Có thể được auditing hỗ trợ |
`MongoRepository.save(entity)` | Save entity qua mapper | Có thể được auditing hỗ trợ |
`MongoTemplate.insert/save(entity)` | Đường mapping entity | Có thể được auditing hỗ trợ |
`MongoTemplate.updateFirst(query, Update, Entity.class)` | Partial server-side update | **Không** coi là chạy đầy đủ auditing entity callbacks |
`MongoTemplate.updateMulti(...)` | Update nhiều document | Không coi là save từng entity |
`MongoTemplate.findAndModify(...)` | Find + update trong một server operation | Không mặc định tương đương entity save auditing |
`BulkOperations.execute()` | Bulk write models | Không mặc định gọi save callbacks cho từng item |
`MongoCollection.updateOne(...)` | Raw Java Driver | Bypass Spring Data entity auditing |
`MongoCollection.insertOne(Document)` | Raw Java Driver | Bypass converter/auditing |
`mongo.remove(query, Entity.class)` | Delete theo selector | Không tự tạo `@DeletedBy` field |

**Ý nghĩa:** nếu một module yêu cầu `lastModifiedBy` chính xác bất kể đường ghi, phải có **chính sách chung**: hạn chế raw writes, triển khai partial-update builders tự thêm audit fields, database validation/authorization phù hợp và integration tests cho từng đường.

### 15.1. Phản ví dụ: updateFirst không đổi modifiedBy

~~~java
Query query = Query.query(
        Criteria.where("id").is("invoice-101")
                .and("tenantId").is("tenant-a"));

Update update = new Update()
        .set("status", "PAID");

mongo.updateFirst(query, update, AuditInvoice.class);
~~~

Đây là một partial update. Nếu `modified_by` chưa được đưa vào `Update`, không được mặc nhiên kỳ vọng Spring Data chạy `@LastModifiedBy` trên **toàn bộ entity**. Tên class trong lời gọi chỉ giúp mapping query/update; nó không tạo một vòng `repository.save(entity)`.

### 15.2. Cập nhật actor tường minh khi partial update

Một cách kiểm soát:

~~~java
Query query = Query.query(
        Criteria.where("id").is(invoiceId)
                .and("tenantId").is(authenticatedTenantId)
                .and("status").is("DRAFT"));

Update update = new Update()
        .set("status", "APPROVED")
        .set("lastModifiedBy", authenticatedActorId)
        .currentDate("updatedAt");

UpdateResult result = mongo.updateFirst(
        query, update, AuditInvoice.class);
~~~

Fragment này nằm trong service với `mongo`, `invoiceId`, `authenticatedTenantId` và `authenticatedActorId` đã được xác thực/validate. Vì query/update dùng `AuditInvoice.class`, Spring Data ánh xạ `lastModifiedBy` sang `modified_by` và `updatedAt` sang `updated_at` theo metadata.

`currentDate("updatedAt")` dùng thời gian từ **MongoDB server** cho update, không nhất thiết cùng clock với `@CreatedDate` đã cấp từ application. Nếu domain yêu cầu clock thống nhất, chọn một chiến lược và kiểm thử precision/timezone. Không nhận `authenticatedActorId` từ request body do client tự gán.

### 15.3. Một lệnh có điều kiện bảo vệ state transition

Đưa `status == DRAFT` vào cùng update với actor giúp ngăn chuyển trạng thái trái luật nếu một request khác đã đổi status. Nếu chỉ đọc trước rồi update theo ID sau đó, có thể xảy ra time-of-check/time-of-use race.

Tuy nhiên `matchedCount == 0` có thể do sai tenant, ID không tồn tại hoặc status không còn DRAFT — không nên báo chắc chắn “không tìm thấy” mà chưa có policy phân loại.

### 15.4. Version cũng cần được cân nhắc

`@Version` không tự có cùng semantics trên mọi driver/custom update path. Một số phiên bản Spring Data có thể tự tăng version khi update chưa chỉ định version, nhưng **không nên coi đó là optimistic locking đầy đủ** nếu query không có expectedVersion. Khi yêu cầu CAS theo version:

~~~javascript
db.audit_invoices.updateOne(
  {
    _id: "invoice-101",
    tenantId: "tenant-a",
    version: 7,
    status: "DRAFT"
  },
  {
    $set: {
      status: "APPROVED",
      modified_by: "user-205"
    },
    $inc: { version: 1 },
    $currentDate: { updated_at: true }
  }
);
~~~

Đây là BSON query ví dụ. Nếu dùng Spring Data template trên entity có `@Version`, cần kiểm tra xem framework tự tăng version trong update hay không và tránh **tăng hai lần**; mỗi đường ghi phải có contract rõ.

## 16. Auditing khi delete và soft delete

`@CreatedBy`/`@LastModifiedBy` không tạo ra field **`@DeletedBy` mặc định** cho mọi delete operation của Spring Data MongoDB.

Ví dụ:

~~~java
mongo.remove(
        Query.query(Criteria.where("id").is(invoiceId)
                .and("tenantId").is(authenticatedTenantId)),
        AuditInvoice.class);
~~~

Đây là delete theo query selector. MongoDB có thể xóa document mà không tải entity để auditing lại. Sau physical delete, các audit metadata nằm trong document đó cũng **không còn trong collection**.

### 16.1. Khi cần biết ai xóa?

Có một số chiến lược:

- **Soft delete:** giữ document, thêm `deletedAt`, `deletedBy` và `deletedReason` bằng một conditional update.
- **Audit event/outbox:** lưu sự kiện xóa có actor/subject/tenant trong transaction cùng delete nếu cần all-or-nothing.
- **Change streams:** nhận thay đổi từ MongoDB với cơ chế resume và pre/post-images nếu được cấu hình/hỗ trợ, nhưng không tự có đủ actor nghiệp vụ nếu ứng dụng không ghi actor.
- **Service audit journal:** ghi một event có request ID/actor/tenant trước hoặc cùng transaction, quản lý reliability và retry.

Ví dụ soft delete:

~~~javascript
db.audit_invoices.updateOne(
  {
    _id: "invoice-101",
    tenantId: "tenant-a",
    status: { $ne: "DELETED" }
  },
  {
    $set: {
      status: "DELETED",
      deleted_by: "user-205"
    },
    $currentDate: { deleted_at: true }
  }
);
~~~

`deleted_by` và `deleted_at` ở ví dụ này là **schema mở rộng**, không có trong `AuditInvoice` ban đầu. Nếu triển khai, cần khai báo entity fields và quy tắc tìm kiếm (loại soft-deleted records), retention/TTL, index và quyền truy cập.

### 16.2. Delete event không phải per-document audit log

Một `deleteMany(query)` có thể xóa nhiều document mà không phát event chứa từng entity đã xóa. Không dùng `BeforeDeleteEvent`/`AfterDeleteEvent` để suy ra chính xác actor, subject và old state cho **từng document** trong một lần xóa hàng loạt.

### 16.3. Xóa theo tenant là điều kiện bảo mật

Auditor ID có thể đúng nhưng delete query thiếu tenant vẫn nguy hiểm. `tenantId` phải được xác nhận từ auth/policy và đưa vào **chính điều kiện ghi/xóa**, không chỉ gắn vào một audit event sau đó.

## 17. Auditing trong transaction và kết quả commit chưa rõ

Một method transaction có thể gọi repository save nhiều document:

~~~java
@Transactional(transactionManager = "mongoTransactionManager")
public void approveAndCreateNotification(...) {
    invoiceRepository.save(invoice);
    notificationRepository.save(notification);
}
~~~

Đây là fragment kiến trúc minh họa: chỉ có ý nghĩa khi có hai repositories và manager được đăng ký chính xác. Khi transaction thật sự hoạt động trên MongoDB topology hỗ trợ, cả hai write có thể commit hoặc rollback cùng nhau.

**AuditorAware có thể chạy trong giai đoạn chuẩn bị entity trước write, không phải sau commit.** Nó có thể trả actor đúng ngay cả khi transaction sẽ bị abort vì một lỗi khác. Do đó:

- `getCurrentAuditor()` được gọi không chứng minh có document mới đã commit.
- `AfterSaveCallback` hay listener nếu chạy trước commit cũng không đủ làm chứng từ final success.
- Transaction abort phải được kiểm tra trên **database state**, không chỉ bằng số lần callback.
- Nếu client timeout khi commit, kết quả có thể chưa xác định; không tự retry workflow ghi tài chính như một request mới mà không có idempotency key.

### 17.1. Lỗi sau write không xóa actor trong object Java

Giả sử auditing callback điền `lastModifiedBy = "user-205"` cho entity Java, sau đó MongoDB abort transaction. Object đang giữ trong bộ nhớ vẫn có thể mang metadata đã được tính, nhưng database **không có commit tương ứng**.

Không lấy trạng thái object trong bộ nhớ sau rollback làm bằng chứng dữ liệu đã lưu; đọc lại trong transaction/session phù hợp hoặc thực hiện đối soát ngoài transaction theo contract.

### 17.2. Transaction không tự bao HTTP, email hay Kafka

Nếu auditing actor ở một callback được dùng để gửi email “user-205 đã duyệt”, email có thể phát đi rồi transaction MongoDB rollback. Dùng **transactional outbox**:

~~~mermaid
flowchart LR
    A["Transactional service"] --> B["Save Invoice với actor"]
    A --> C["Insert OutboxEvent với actor/ID"]
    B --> D["Commit MongoDB transaction"]
    C --> D
    D --> E["Outbox worker"]
    E --> F["Publish event; consumer idempotent"]
~~~

Outbox lưu actor/subject đã xác định cùng business change. Worker xuất event sau commit và phải quản lý retry/duplicate delivery. Nếu message bus không hỗ trợ exact-once end-to-end, consumer vẫn cần idempotency.

### 17.3. Không dùng audit actor làm idempotency key

Một user có thể hợp pháp thao tác nhiều lần. `lastModifiedBy = "user-205"` không phân biệt hai request khác nhau. Nên có **commandId/requestId** riêng, business key/version và unique constraint phù hợp với transaction.

## 18. ReactiveAuditorAware khác AuditorAware

Ứng dụng **ReactiveMongoRepository** hoặc **ReactiveMongoTemplate** dùng Reactor publishers và context khác đường imperative. Khi cần actor trong reactive pipeline, Spring Data có giao diện **`ReactiveAuditorAware<T>`**:

~~~java
package org.springframework.data.domain;

import reactor.core.publisher.Mono;

public interface ReactiveAuditorAware<T> {
    Mono<T> getCurrentAuditor();
}
~~~

Đoạn trên mô tả hợp đồng, **không tạo lại interface này trong source code**. Với reactive auditing, không lấy `SecurityContextHolder` thread-local làm nguồn identity mặc định khi request có thể chuyển thread; Spring Security cung cấp `ReactiveSecurityContextHolder`.

### 18.1. Triển khai từ ReactiveSecurityContextHolder

**ReactiveCurrentActorAuditorAware.java**

~~~java
package com.example.audit.reactive;

import org.springframework.data.domain.ReactiveAuditorAware;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component("reactiveCurrentActorAuditorAware")
public class ReactiveCurrentActorAuditorAware
        implements ReactiveAuditorAware<String> {

    @Override
    public Mono<String> getCurrentAuditor() {
        return ReactiveSecurityContextHolder.getContext()
                .map(context -> context.getAuthentication())
                .filter(auth -> auth != null
                        && auth.isAuthenticated()
                        && !(auth instanceof AnonymousAuthenticationToken))
                .map(Authentication::getName)
                .filter(name -> name != null && !name.isBlank());
    }
}
~~~

Nếu reactive security context không tồn tại hoặc anonymous, pipeline có thể hoàn tất **rỗng**; không được suy rằng đó là user `"SYSTEM"`. `ReactiveAuditorAware` trả `Mono<String>`, không trả `Optional<String>` như imperative provider.

### 18.2. Bật reactive Mongo auditing

~~~java
package com.example.audit.reactive;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.config.EnableReactiveMongoAuditing;

@Configuration
@EnableReactiveMongoAuditing(
        auditorAwareRef = "reactiveCurrentActorAuditorAware")
public class ReactiveAuditingConfig {
}
~~~

Kết hợp với reactive MongoDB client/template/repositories phù hợp. `@EnableReactiveMongoAuditing` không tự tạo client, server hay Security WebFilterChain.

### 18.3. Context phải đi theo Publisher

~~~java
Mono<AuditInvoice> operation = reactiveRepository
        .save(new AuditInvoice(
                "invoice-301", "tenant-a", "DRAFT"));
~~~

Trong WebFlux, cần **return/compose Publisher** để framework subscribe và propagate Reactor Context. Không gọi `operation.block()` bên trong event-loop rồi cho rằng reactive security context sẽ tự xuất hiện như một thread-local.

Nếu tự gọi `subscribe()` ở một nơi tách khỏi request, có thể mất context, error handling và transaction boundary; dùng orchestrator/job identity phù hợp.

### 18.4. Reactive transaction manager là một chủ đề khác

`ReactiveMongoTransactionManager` quản lý multi-document transactions trong Reactor Context; `ReactiveAuditorAware` chỉ cung cấp actor. Hai cơ chế độc lập nhưng có thể cùng tham gia một reactive write flow. Không nhầm `AuditorAware<String>` imperative và `ReactiveAuditorAware<String>` rồi kỳ vọng framework tự chuyển đổi context.

## 19. DateTimeProvider, timezone và thời gian auditing

Người thao tác và thời gian cần được quản lý **tách biệt**. Một policy có thể định nghĩa:

- Actor ID theo hệ thống identity.
- Timestamps lưu dưới `Instant`/UTC.
- Display timezone chỉ dùng ở UI/report.
- Test dùng clock giả lập hoặc `DateTimeProvider` cho deterministic assertions.
- Không để client tự truyền `createdAt`/`updatedAt` rồi bỏ qua kiểm soát.

### 19.1. Vì sao Instant phù hợp?

`Instant` đại diện một thời điểm độc lập với timezone hiển thị. BSON Date lưu dạng timestamp tương ứng với đơn vị millisecond. Nếu user ở Việt Nam nhìn `2026-11-20 15:00 +07:00`, dữ liệu lưu có thể là `2026-11-20T08:00:00Z`.

Việc hiển thị theo múi giờ hay format ngôn ngữ không nên làm thay đổi actor field hoặc tạo ra một tác động ghi mới.

### 19.2. Dữ liệu từ các clock khác nhau

Ví dụ:

~~~java
new Update()
        .set("lastModifiedBy", actorId)
        .currentDate("updatedAt");
~~~

Ở partial update này, timestamp đến từ MongoDB server. Trong đường repository save, `@LastModifiedDate` thường dựa vào auditing provider ở ứng dụng. Nếu nhiều services dùng server clocks khác nhau, có thể có chênh lệch. Đặt rõ yêu cầu consistency và đo clock skew; không dùng timestamp làm surrogate version khi cần CAS mạnh.

### 19.3. Ngày giờ audit không phải business effective time

`createdAt` cho biết **document được tạo lúc nào trong hệ thống**, không nhất thiết là ngày hóa đơn phát hành hoặc thời điểm sự kiện kinh doanh xảy ra. Nếu một file lịch sử được import hôm nay, `createdAt` sẽ phản ánh thao tác import theo auditing policy, còn `invoiceIssuedAt` là thời gian nghiệp vụ từ dữ liệu nguồn.

Không dùng auditing date thay mọi mốc thời gian domain. Tương tự, `createdBy` có thể là người import, không phải người phát hành hóa đơn trong hệ thống nguồn.

## 20. Dữ liệu legacy và backfill audit metadata

Nhiều collection có document cũ chưa có `created_by`/`modified_by`:

~~~json
{
  "_id": "invoice-old",
  "tenantId": "tenant-a",
  "status": "PAID"
}
~~~

Bật auditing **không tự quét collection để điền actor cho tất cả dữ liệu cũ**. Nó chỉ ảnh hưởng những đường lifecycle được gọi trong tương lai.

### 20.1. Không bịa actor người dùng quá khứ

Nếu không thể xác định ai đã tạo document lịch sử, đừng tự điền một user cụ thể chỉ để field trông đầy đủ. Có thể dùng:

- `unknown:legacy` khi business policy chấp nhận và mọi báo cáo hiểu ý nghĩa;
- `migration:<id>` nếu field biểu diễn actor thực hiện **backfill hiện tại**, không phải người tạo gốc;
- Một metadata riêng `auditBackfilledBy`/`auditBackfilledAt` để ghi dấu tác vụ bổ sung;
- Giữ null và báo rõ rằng lịch sử trước thời điểm bật auditing không có nguồn identity đáng tin.

### 20.2. Tránh sửa createdBy bằng một đợt save thiếu kiểm soát

Chạy `repository.save(...)` cho mọi document legacy có thể:

- Làm tăng version;
- Thay modified metadata thành actor migration;
- Ghi đè field khi entity mapper không hiểu một phần schema cũ;
- Tạo write load lớn;
- Kích hoạt callbacks hoặc domain logic không mong muốn.

Thay vì vậy, xây **migration riêng** với query filter/batch/checkpoint và chỉ set những field có thể điền đúng, tránh thay đổi metadata tạo gốc nếu không có bằng chứng. Đo index/build và dùng rollback/backup policy phù hợp.

### 20.3. Ví dụ backfill có dấu vết rõ

~~~javascript
db.audit_invoices.updateMany(
  {
    created_by: { $exists: false },
    tenantId: "tenant-a"
  },
  {
    $set: {
      created_by: "unknown:legacy",
      audit_backfill_id: "migration:2026-11"
    }
  }
);
~~~

Đây là ví dụ **chỉ chạy khi đã có policy rằng người tạo lịch sử không xác định**. Nó không chứng minh actor gốc là `unknown:legacy` theo nghĩa một user đã tồn tại; đây là sentinel rõ ràng cho dữ liệu thiếu. Trước migration production phải có đánh giá business/legal/retention, backup và dry-run.

## 21. Bảo mật, riêng tư và toàn vẹn audit metadata

Audit fields có thể là dữ liệu nhạy cảm vì chúng liên kết hoạt động với cá nhân. Một chính sách hoàn chỉnh cần:

1. **Nguồn danh tính xác thực**: không tin client-supplied actor.
2. **Stable identity**: dùng ID không dễ thay đổi; không lạm dụng email/displayName.
3. **Phân quyền đọc**: không phải mọi client được xem `createdBy`/`lastModifiedBy`.
4. **Phân quyền ghi**: DTO không cho sửa audit fields tùy ý.
5. **Tenant isolation**: mọi query/write/delete dùng tenant từ server auth context.
6. **Retention**: bảo lưu hoặc xóa audit metadata theo yêu cầu pháp lý và chính sách dữ liệu.
7. **Secrets**: không lưu password, access token, session ID, JWT raw hoặc payload xác thực vào auditing fields.
8. **Logging**: không log cả `Authentication` object, raw BSON hoặc principal claims không cần thiết.
9. **Migration policy**: không bịa người thao tác lịch sử.
10. **Integrity evidence**: nếu cần bất biến/chống sửa, thêm audit ledger/outbox/append-only storage và quyền quản trị phù hợp.

### 21.1. @CreatedBy không phải database access control

Một người có quyền database trực tiếp vẫn có thể chạy:

~~~javascript
db.audit_invoices.updateOne(
  { _id: "invoice-101" },
  { $set: { created_by: "fake-user" } }
);
~~~

Annotation auditing của Spring Data không chặn raw MongoDB command này. Nếu audit metadata là bằng chứng pháp lý quan trọng, phải có kiểm soát database write permissions, journaling, monitoring, change streams/ledger và quy trình vận hành tương ứng.

### 21.2. Không “ủy quyền” bằng cách đọc createdBy

Ví dụ “chỉ người tạo được sửa” không tự an toàn nếu service chỉ kiểm tra `createdBy` sau khi đọc rồi ghi theo ID. Với concurrent changes hoặc role policies, cần một điều kiện/authorization contract đầy đủ. `createdBy` là một thành phần dữ liệu để đánh giá permission khi phù hợp, không phải toàn bộ security model.

### 21.3. Client có thể thấy actor nào?

Đối với API công khai, DTO có thể chỉ trả trạng thái, ngày giờ và ID đã được pseudonymize, thay vì email/user ID nội bộ. Với admin API, có thể cần quyền riêng để xem audit metadata. Hãy áp dụng whitelist serialization theo endpoint/role; không trả nguyên entity MongoDB cho tất cả user.

## 22. Lỗi thường gặp và cách chẩn đoán

| Biểu hiện | Nguyên nhân khả dĩ | Hướng xử lý |
|---|---|---|
`@CreatedBy` luôn null sau insert | Chưa bật auditing, provider thiếu hoặc `Optional.empty()` | Kiểm tra `@EnableMongoAuditing`, bean name, actor context |
`@LastModifiedBy` không đổi sau updateFirst | Partial update bypass entity auditing | Thêm actor/timestamp tường minh vào `Update` |
`createdBy` bị thay khi save | Đường ghi mapper/custom logic sửa metadata | Kiểm tra DTO, lifecycle và update policy |
`modifiedBy` được điền ngay khi insert | `modifyOnCreate = true` | Chấp nhận theo contract hoặc đổi config |
`modifiedBy` null khi insert | `modifyOnCreate = false` hoặc actor không có | Kiểm tra ý định cấu hình và provider |
Mọi document do `system` tạo | Fallback global che identity thật | Phân biệt request/user và job actor |
Anonymous request lưu `anonymousUser` | Chỉ kiểm tra `isAuthenticated()` | Loại `AnonymousAuthenticationToken` hoặc định nghĩa public actor riêng |
Đổi principal nhưng audit vẫn là actor cũ | Security context leak hoặc bean cố định | Test context lifecycle, provider bean, cleanup |
JWT user ID không khớp business ID | `getName()` lấy claim khác | Cấu hình converter và stable actor ID |
`@Async` không có auditor | Thread-bound context không được truyền | Dùng actor propagation/job identity có chủ đích |
Reactive auditing trả empty | Dùng `SecurityContextHolder` thay Reactor Context | `ReactiveAuditorAware`/`ReactiveSecurityContextHolder` |
Nhiều `AuditorAware` gây ambiguous bean | Không chọn auditor cụ thể | `auditorAwareRef` trỏ bean đúng |
`@EnableMongoAuditing` không có tác dụng | Config ngoài component scan hoặc trùng registrar | Import/scan đúng cấu hình, kiểm tra context |
Unit test mock save nhưng audit null ở runtime | Mock không chạy mapping callbacks | Integration test MongoDB thật |
`@Field("modified_by")` nhưng raw BSON khác | Mapping/schema/đường ghi không nhất quán | Đọc raw BSON và kiểm tra field names |
`@Version` báo stale save | Entity đã thay đổi từ lần đọc | Xử lý optimistic conflict, không ép version |
Actor đúng nhưng tenant sai | Auditor không làm authorization | Tenant filter/policy trên query ghi |
Raw driver update sửa createdBy | Auditing chỉ là Spring infrastructure | Hạn chế quyền DB, whitelist writes |
Migration làm mọi document thành actor migration | Dùng `save`/audit callback trong backfill | Có policy phân biệt actor gốc với actor sửa/migration |
AfterSave đã chạy nhưng DB rollback | Hook xảy ra trước commit | Outbox/transaction commit verification |
Timestamp không tăng rõ giữa hai saves | Precision/clock hoặc date provider | Kiểm thử với clock kiểm soát, không `sleep` bừa |
`lastModifiedBy` bị ghi dù document không đổi nội dung | Save làm audit metadata thay đổi | Chỉ save khi cần, xác định semantic “modification” |
Delete không ghi deletedBy | Physical delete không giữ metadata | Soft delete, outbox hoặc audit ledger |
Replica secondary đọc actor cũ sau write | Replication lag/read preference | Xác định read consistency contract |

### 22.1. Checklist khi createdBy không được điền

Trước khi thêm mã ở controller, hãy lần lượt xác minh:

1. Entity dùng `@CreatedBy` đúng field và kiểu dữ liệu.
2. Hạ tầng `@EnableMongoAuditing` có nằm trong application context.
3. `auditorAwareRef` có đúng tên bean, không nhầm type.
4. Provider `getCurrentAuditor()` có trả `Optional.of(actorId)` tại lúc ghi.
5. Principal có bị anonymous hoặc không mang user ID mong muốn.
6. Operation thực tế là `repository.insert/save` hay raw/partial update.
7. MongoDB converter có ánh xạ field sang BSON đúng bằng `@Field`.
8. Entity được nhận diện new/existing theo ID/version strategy phù hợp.
9. Một custom callback/auditing config khác có ghi đè field không.
10. Test trên MongoDB thật cho biết raw document cuối cùng chứa gì.

Đừng khắc phục bằng cách luôn set `createdBy = "admin"` trước save. Cách đó có thể che một lỗ hổng authentication hoặc attribution nghiêm trọng.

### 22.2. Phân biệt lỗi context và lỗi dữ liệu

Nếu provider trả actor đúng nhưng BSON chưa có actor, lỗi có thể nằm ở auditing registration/mapping/write path. Nếu provider trả empty, lỗi có thể nằm ở security context, job identity hoặc bean được chọn. Nếu BSON đúng nhưng API không trả, lỗi ở projection/DTO/serialization hoặc read consistency.

Tách ba tầng khi debug giúp tránh sửa nhầm: **identity provider → persistence auditing → API representation**.

## 23. Chiến lược thiết kế auditing cho production

Một kiến trúc an toàn không đặt mọi trách nhiệm vào `AuditorAware`. Có thể chia rõ thành:

~~~mermaid
flowchart TD
    A["Authenticated request / verified job"] --> B["Identity + authorization policy"]
    B --> C["Actor ID và tenant đáng tin"]
    C --> D["AuditorAware / application context"]
    C --> E["Domain service"]
    D --> F["Spring Data entity auditing"]
    E --> F
    E --> G["Conditional update / transaction / outbox"]
    F --> H["MongoDB document metadata"]
    G --> I["Audit event / business history"]
    H --> J["Monitoring + access policy"]
    I --> J
~~~

### 23.1. Những quyết định cần đưa vào thiết kế

| Quyết định | Ví dụ contract |
|---|---|
Actor ID là gì? | Stable user ID hoặc service account ID |
Ai được ghi actor? | Chỉ Spring Security/context server đã xác minh |
Anonymous writes được phép không? | Public creation có actor `public:anonymous` riêng hoặc bị từ chối |
Job actor là ai? | `job:invoice-sync` |
createdBy có bao giờ được sửa không? | Không, ngoại trừ migration có phê duyệt và audit riêng |
modifiedBy trên insert ra sao? | Có nếu `modifyOnCreate=true` |
LastModifiedAt dùng clock nào? | `DateTimeProvider`/UTC cho entity saves, policy riêng cho raw updates |
Có nhiều MongoDB writers không? | Có: mọi writer phải tuân audit contract, không dựa chỉ vào Spring callback |
Xóa vật lý có cần history không? | Có: outbox/ledger/soft delete |
Audit metadata lưu bao lâu? | Theo policy pháp lý và retention đã duyệt |
Actor có PII không? | Prefer stable opaque ID, hạn chế hiển thị |
Mức độ bằng chứng cần có? | Metadata vs append-only event journal |

### 23.2. Một actor provider không thay domain policy

Trong service duyệt hóa đơn, cần:

1. Xác nhận principal.
2. Xác định tenant và quyền duyệt.
3. Áp dụng CAS/state transition hợp lệ.
4. Ghi audit actor vào cùng lệnh/đường lifecycle.
5. Bảo đảm transaction nếu còn nhiều document liên quan.
6. Ghi business event có request/command ID nếu cần truy vết.
7. Xử lý retry, lỗi mạng, commit unknown và đối soát.

`AuditorAware` chỉ đảm nhiệm **bước cung cấp actor**. Nhờ tách trách nhiệm, ứng dụng có thể chuyển từ security session sang JWT hoặc service identity mà không phải viết lại mọi repository.

### 23.3. Khi nào nên không dùng auditing tự động?

Nếu một service ghi hàng loạt bằng aggregation pipeline hoặc bulk ops và mọi write cần kèm actor, cách rõ ràng hơn có thể là **update builder/domain repository tự thêm audit fields**. Nếu data model cố ý không có identity (ví dụ public aggregate counters), không cần gắn actor sai sự thật chỉ để mọi document có `createdBy`.

Auditing tự động hợp với **entity lifecycle**, không bắt buộc là nguồn metadata tối ưu cho mọi hoạt động MongoDB.

## 24. Bài tập thực hành

**Bài 1 — Hợp đồng AuditorAware.** Viết `AuditorAware<String>` trả `Optional.of("test-actor")`, sau đó thay thành `Optional.empty()`. Giải thích vì sao null/empty không được xem là user `SYSTEM` mặc định.

**Bài 2 — Entity metadata.** Tạo `AuditInvoice` có `@CreatedBy`, `@LastModifiedBy`, `@CreatedDate`, `@LastModifiedDate`, `@Version`; dùng `@Field` ánh xạ thành snake_case BSON. Kiểm tra raw document.

**Bài 3 — Bật auditing.** Tạo `@EnableMongoAuditing(auditorAwareRef = "currentActorAuditorAware")`. Cố tình đặt sai bean name ở test context để quan sát lỗi configuration và sửa.

**Bài 4 — Spring Security identity.** Tạo security context có authenticated `UsernamePasswordAuthenticationToken`; assert auditor trả đúng ID. Sau đó thử null context và anonymous token.

**Bài 5 — Stable identity.** So sánh lưu username/email với user ID ổn định. Thiết kế actor ID cho hệ thống có cả người dùng, service account và migration jobs.

**Bài 6 — Hai actors trên một document.** Actor A insert, actor B update qua repository `save`. Kiểm tra `createdBy=A`, `lastModifiedBy=B`, `createdAt` không đổi.

**Bài 7 — modifyOnCreate.** Chạy test riêng với `modifyOnCreate=true` và `false` (hai test contexts độc lập), đối chiếu `lastModifiedBy` và `updatedAt` sau insert.

**Bài 8 — Partial update bypass.** Actor B dùng `MongoTemplate.updateFirst` chỉ sửa status. Xác minh `modified_by` không tự đổi, sau đó thêm `set("lastModifiedBy", actorId)` và `currentDate("updatedAt")` vào cùng write.

**Bài 9 — Version/optimistic lock.** Hai actors cùng đọc bản invoice DRAFT, save lần lượt. Phân biệt xung đột version với auditing; không cho callback ghi đè version để ép save.

**Bài 10 — Tenant security.** User có quyền tenant-a thử đọc/sửa invoice tenant-b. Test cả query và write filters, không chỉ test auditor ID.

**Bài 11 — Job không có principal.** Chạy một scheduled job trong test không có `SecurityContext`. Chọn service/job actor riêng hoặc chủ động từ chối nếu actor bắt buộc; không gán fallback admin.

**Bài 12 — @Async actor propagation.** Gọi một operation từ executor khác. Đo actor trả về và triển khai một cơ chế job identity/propagation đúng lifecycle, kiểm tra cleanup giữa hai tasks.

**Bài 13 — ReactiveAuditorAware.** Viết provider dùng `ReactiveSecurityContextHolder`, bật `@EnableReactiveMongoAuditing` và kiểm tra bằng `StepVerifier`. Không dùng `ThreadLocal` để giả định actor tồn tại trên mọi scheduler.

**Bài 14 — Transaction rollback.** Trên MongoDB replica set test, save entity có actor rồi gây exception trước commit. Xác minh dữ liệu không xuất hiện sau rollback và callback trước commit không phải audit event bền vững.

**Bài 15 — Outbox.** Thêm `AuditActionEvent` có command ID, actor, subject ID, tenant và thời điểm. Ghi event cùng invoice change trong transaction; thiết kế publisher/consumer idempotent.

**Bài 16 — Soft delete.** Thiết kế `deletedBy`/`deletedAt` cho một document cần lịch sử xóa. So sánh với physical delete không còn metadata và cách lưu outbox.

**Bài 17 — Legacy migration.** Collection có 10.000 document thiếu `created_by`. Thiết kế migration có checkpoint/backup/actor sentinel, không bịa người tạo gốc và không vô tình sửa modified metadata của mọi record.

**Bài 18 — Multi-writer policy.** Cùng collection được cập nhật bởi Spring repository, bulk import và raw driver. Xác định đường nào tự chạy entity auditing và chuẩn hóa một quy trình đảm bảo metadata nhất quán.

**Bài 19 — Quality metrics.** Đo tỷ lệ document thiếu `created_by` theo thời gian, phân loại nguyên nhân (legacy, empty context, raw writes) và định nghĩa alert không làm lộ user IDs vào logs.

**Bài 20 — Audit privacy.** Thiết kế API DTO chỉ xuất actor metadata cho vai trò có quyền. Chứng minh user thường không thể ghi đè `created_by` qua request JSON.

## 25. Ghi nhớ

**`AuditorAware<T>` là nguồn cung cấp danh tính người thao tác cho auditing của Spring Data MongoDB ở luồng imperative.** Kết hợp `@CreatedBy`/`@LastModifiedBy` trên entity với `@EnableMongoAuditing(auditorAwareRef = "...")` để framework điền người tạo/người sửa trong các đường lưu entity được hỗ trợ. `getCurrentAuditor()` trả `Optional<T>`; nó không tự xác thực, phân quyền hay bịa một system user khi không có principal.

Trong ứng dụng dùng **Spring Security**, có thể đọc `Authentication` từ `SecurityContextHolder`, nhưng cần loại anonymous, ánh xạ sang **stable actor ID** và phân biệt user, service account, job và migration. Không tin actor ID từ request body/header chưa xác minh. Với WebFlux/reactive MongoDB, dùng **`ReactiveAuditorAware<T>` và `ReactiveSecurityContextHolder`** theo Reactor Context, không ép provider imperative vào reactive pipeline.

**Auditing trên entity không thay thế database constraint hay audit history.** `repository.save` và `MongoTemplate.updateFirst` không có cùng lifecycle; partial updates, bulk và raw driver có thể bỏ qua auditing callbacks. Nếu dùng conditional update, thêm actor/timestamp vào **cùng write** từ identity đã xác thực. Actor metadata không thay `@Version`, tenant authorization, unique indexes, transaction hay idempotency.

Cuối cùng, **createdBy/lastModifiedBy chỉ là metadata của document hiện tại, không phải chứng cứ bất biến của toàn bộ lịch sử**. Với thao tác quan trọng, thiết kế audit event/outbox/ledger và kiểm soát commit, retention, privacy. Xác minh bằng test đổi hai actors, đọc raw BSON, kiểm tra partial-update bypass và thử rollback trên MongoDB test thật trước khi triển khai production.
