# Tránh cập nhật ngoài ý muốn khi hợp nhất entity từ dữ liệu đầu vào

Khi xây dựng API cập nhật bằng Jakarta Persistence (JPA), một lỗi bảo mật thường gặp là **tin rằng đối tượng nhận từ HTTP request chính là một entity hợp lệ có thể lưu thẳng vào cơ sở dữ liệu**. Ví dụ:

```java
@PutMapping("/users/{id}")
public UserAccount update(
        @PathVariable Long id,
        @RequestBody UserAccount incoming) {

    incoming.setId(id);
    return entityManager.merge(incoming);
}
```

Đoạn code ngắn này che giấu nhiều nguy cơ. Client có thể gửi thêm các thuộc tính không được phép sửa:

```json
{
  "displayName": "Mai Anh",
  "email": "mai@example.com",
  "role": "ADMIN",
  "enabled": true,
  "tenantId": "OTHER_TENANT",
  "creditLimit": 999999999
}
```

Nếu JSON được deserialize thành entity rồi được `merge()`, JPA không hiểu field nào được client **được quyền** chỉnh sửa. Nó chỉ thực hiện hợp nhất **persistent state** theo mapping và lifecycle rules. Những thuộc tính không có trong request còn có thể trở thành `null`/default values ở object mới tạo, khiến dữ liệu cũ bị xóa hoặc ghi đè khi merge.

Vấn đề này thường được gọi là **mass assignment**, **overposting** hoặc cập nhật vượt quyền (*unauthorized property modification*). Trong JPA, nó liên quan trực tiếp đến:

- Cơ chế `EntityManager.merge()` với **detached entity**.
- `save()` của Spring Data JPA và cách quyết định `persist` hay `merge`.
- Việc ánh xạ JSON/DTO sang entity.
- Dirty checking trên managed entity.
- Bảo vệ tenant, owner, role và các field nội bộ.
- Quan hệ `@ManyToOne`, `@OneToMany`, cascade `MERGE` và `orphanRemoval`.
- Optimistic locking và lost update do client gửi dữ liệu cũ.
- Validation, database constraints, authorization và integration tests.

Bài **“Tránh cập nhật ngoài ý muốn khi hợp nhất entity từ dữ liệu đầu vào”** thuộc chương **“Bảo mật dữ liệu”** của module **Data Persistence Relational Access ORM JPA**. Mục tiêu là hiểu vì sao merge không phải cơ chế kiểm soát quyền cập nhật, rồi thiết kế **command/DTO allowlist + tải entity theo phạm vi được phép + thay đổi có chủ đích trong transaction**.

## 1. Vấn đề cốt lõi: client không được quyết định toàn bộ trạng thái entity

Một entity chứa nhiều loại thuộc tính:

| Nhóm dữ liệu | Ví dụ | Ai được phép thay đổi? |
|---|---|---|
| Input công khai | `displayName`, `phoneNumber` | Người dùng với quyền phù hợp |
| Chỉ sửa qua workflow riêng | `emailVerified`, `orderStatus` | Service nghiệp vụ có kiểm tra |
| Quyền và bảo mật | `role`, `isAdmin`, `accountLocked` | Workflow quản trị chuyên biệt |
| Ranh giới tenant | `tenantId`, `organizationId` | Server/security context |
| Ownership | `ownerId`, `createdBy` | Service có quyền chuyển sở hữu |
| Dữ liệu hệ thống | `createdAt`, `updatedAt`, `version` | Server/JPA/database |
| Số liệu tài chính | `balance`, `creditLimit`, `paidAmount` | Domain transaction chuyên biệt |
| Quan hệ | `manager`, `memberships`, `items` | Có thể yêu cầu kiểm tra đối tượng liên quan |

Không thể suy ra các quyền này chỉ từ annotation `@Column` hay việc có setter Java.

### 1.1. Đối tượng nhận từ request là dữ liệu không đáng tin

Ngay cả khi frontend không hiện ô chọn role, một client có thể tự dựng HTTP request. Các field có thể được sửa bằng DevTools, curl, Postman hoặc script.

```http
PATCH /api/users/123
Content-Type: application/json

{
  "displayName": "Mai Anh",
  "role": "ADMIN"
}
```

Việc frontend ẩn `role` **không** phải cơ chế bảo vệ. Server phải định nghĩa và enforce những thuộc tính nào được cập nhật.

### 1.2. Authentication khác authorization

Một người dùng đăng nhập hợp lệ có thể:

- Được sửa profile của **chính mình**.
- Không được sửa profile của người khác.
- Không được tự đổi role.
- Không được chuyển account sang tenant khác.
- Được đổi email qua quy trình xác minh nhưng không được set `emailVerified=true`.

Authentication chỉ biết **ai đang gọi**. Authorization quyết định **người đó được thực hiện hành động nào trên tài nguyên nào**, với field và quan hệ nào.

### 1.3. Validation không thay authorization

`@NotBlank` trên `displayName` và `@Positive` trên `creditLimit` có thể xác nhận dữ liệu hợp lệ về hình thức. Chúng **không** trả lời câu hỏi “người dùng có quyền tăng creditLimit không?”.

Một request có `role="ADMIN"` là giá trị enum hợp lệ về mặt dữ liệu nhưng có thể hoàn toàn không được phép.

### 1.4. Database constraints cũng không thay authorization

`NOT NULL`, `FOREIGN KEY` và `UNIQUE` bảo vệ một số invariants. Chúng không tự xác nhận caller được cập nhật row hoặc field. Cơ sở dữ liệu có thể chấp nhận một thay đổi sai quyền nếu SQL hợp lệ.

## 2. Ôn lại vòng đời entity: new, managed, detached, removed

Hiểu vòng đời JPA là điều kiện để hiểu `merge`.

| Trạng thái | Ý nghĩa | Cách xử lý thường gặp |
|---|---|---|
| **New/transient** | Java object mới, chưa được quản lý bởi persistence context | `persist` để đưa vào managed state |
| **Managed** | Entity gắn với một persistence context đang hoạt động | Setter/domain methods + dirty checking |
| **Detached** | Entity từng managed nhưng đã tách khỏi context hoặc được truyền qua boundaries | Có thể `merge`; không tự dirty-check như managed hiện tại |
| **Removed** | Entity được đánh dấu xóa trong context | Provider xử lý DELETE theo lifecycle/flush rules |

### 2.1. Ví dụ managed entity

```java
EntityTransaction tx = em.getTransaction();
tx.begin();

UserAccount account = em.find(UserAccount.class, 123L);
account.renameDisplayName("Mai Anh");

tx.commit(); // Provider flush thay đổi managed state.
```

Không cần gọi `merge(account)` vì `account` đã managed trong cùng EntityManager. Điều kiện quan trọng vẫn là có **transaction hợp lệ** cho write operation.

### 2.2. Ví dụ detached entity

```java
EntityManager em1 = emf.createEntityManager();
UserAccount account = em1.find(UserAccount.class, 123L);
em1.close();

// account nay detached.
account.renameDisplayName("Mai Anh");
```

Nếu sửa `account` sau khi EntityManager đóng, thay đổi không tự được flush xuống DB. `merge` có thể được dùng trong luồng detached-entity có chủ đích, nhưng **không có quyền hạn bảo mật nào được JPA tự suy ra**.

### 2.3. DTO không phải detached entity

Một request object:

```java
public record UpdateProfileRequest(String displayName) {}
```

không phải entity. Không có `@Entity`, không có identity/persistence lifecycle, và không nên được đưa trực tiếp vào `EntityManager.merge`.

### 2.4. Đừng trộn “đối tượng JSON” với “aggregate root”

JSON có thể biểu diễn một command chỉ sửa hai fields. Một entity có thể chứa hàng chục fields và quan hệ, được bảo vệ bởi invariants riêng. Chúng là hai mô hình với mục đích khác nhau.

## 3. `EntityManager.merge()` thực sự làm gì?

Một signature JPA:

```java
<T> T merge(T entity);
```

Trong một persistence context, `merge(detachedEntity)` **hợp nhất persistent state của đối tượng đầu vào vào một managed instance** có identity tương ứng hoặc một managed copy mới theo trạng thái entity, rồi trả về managed instance đó.

### 3.1. Sơ đồ cơ chế

```text
      Detached input object (không managed)
      id=123
      displayName="Mai Anh"
      role="ADMIN"
      phone=null
                |
                v
       EntityManager.merge(...)
                |
                v
        Managed instance trong
        persistence context hiện tại
      id=123
      displayName="Mai Anh"
      role="ADMIN"
      phone=null
                |
                v
         flush / transaction commit
                |
                v
        SQL UPDATE theo mapping,
        dirty state và DB constraints
```

Đây là mô hình khái niệm: provider có thể load row từ DB, dùng managed instance đã tồn tại hoặc xử lý entity new state tùy ID/version/mapping. SQL cụ thể phụ thuộc provider, cascade và mapping.

### 3.2. `merge` không “gắn lại” chính input object

```java
UserAccount managed = em.merge(detached);

boolean same = managed == detached; // Thường là false với detached object.
```

Đối tượng đầu vào vẫn là detached; **đối tượng trả về** mới là managed instance cần dùng tiếp trong context. Không viết code kỳ vọng input object tự trở thành managed.

### 3.3. Merge có thể ghi đè nhiều field

`merge` không mặc định có nghĩa:

> “Chỉ copy những fields mà HTTP request có gửi.”

Nó không biết JSON field presence hoặc danh sách field được phép cập nhật. Nó hợp nhất **persistent state** từ entity đầu vào, trong đó `null` và giá trị mặc định cũng là state.

### 3.4. Merge không tự đồng nghĩa UPDATE

Với entity mới, `merge` có thể tạo một managed copy để insert. Với detached có ID không tồn tại, hành vi có thể khác theo JPA version/provider, generated ID và version mapping; một số trường hợp báo optimistic locking hoặc lỗi khác. **Đừng dùng merge như một “upsert tùy ý theo client ID”**.

### 3.5. SQL phát sinh không nhất thiết update mọi cột

Provider có thể dùng dirty checking, static UPDATE hay dynamic UPDATE optimization. Bảo mật không được dựa vào phỏng đoán “column không thay nên sẽ không update”. Nếu trạng thái trước và sau khác hoặc provider/cascade xử lý, field ngoài ý muốn vẫn có thể bị cập nhật.

### 3.6. `merge` yêu cầu transaction cho write

Nếu merge trong persistence context nhưng không có transaction phù hợp, cách phát SQL/flush và exception behavior khác theo bootstrap/provider; không thiết kế command update thiếu transaction boundary. Trong Spring thường dùng `@Transactional` trên service command.

## 4. Phân biệt `persist`, `merge`, `find` và dirty checking

| API/cơ chế | Ý nghĩa | Rủi ro nếu xử lý dữ liệu client sai |
|---|---|---|
| `persist(newEntity)` | Quản lý entity mới để INSERT | Client cấp giá trị nội bộ, ownership/tenant sai |
| `find(Entity,id)` | Tìm managed entity bằng ID | IDOR/BOLA nếu thiếu authorization |
| `merge(detached)` | Copy persistent state vào managed copy | Mass assignment, xóa/ghi đè fields/associations |
| Managed setter/domain method | Thay đổi object đã managed | Vẫn nguy hiểm nếu setter nhận mọi field từ request |
| `flush()` | Đồng bộ thay đổi vào DB transaction | Lỗi constraints/locks có thể xuất hiện muộn |
| `commit()` | Hoàn tất transaction nếu thành công | Không đảm bảo thành công chỉ vì `merge` trả object |

### 4.1. “Không dùng merge” chưa đủ để an toàn

Code này cũng nguy hiểm:

```java
UserAccount account = em.find(UserAccount.class, id);
beanUtils.copyProperties(requestBody, account);
```

Nếu `requestBody` chứa field `role` hoặc `tenantId` và BeanUtils copy tất cả properties, managed entity bị thay đổi, JPA dirty checking sẽ flush. **Vấn đề gốc là mapping input không có allowlist**, không chỉ tên method `merge`.

### 4.2. Một transaction commit thành công không chứng minh authorization đúng

Nếu request thay `role` trái phép nhưng vẫn hợp lệ theo enum/DB constraints, transaction có thể commit thành công. Bảo mật nằm ở **service authorization + mapping rules**, không ở commit outcome.

## 5. Mass assignment/overposting diễn ra thế nào?

Giả sử entity:

```java
@Entity
@Table(name = "user_accounts")
public class UserAccount {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "tenant_id", nullable = false,
            updatable = false)
    private String tenantId;

    @Column(name = "display_name", nullable = false)
    private String displayName;

    @Column(name = "email", nullable = false)
    private String email;

    @Enumerated(EnumType.STRING)
    @Column(name = "role", nullable = false)
    private AccountRole role;

    @Column(name = "enabled", nullable = false)
    private boolean enabled;

    @Column(name = "credit_limit", nullable = false)
    private BigDecimal creditLimit;

    @Version
    private Long version;

    protected UserAccount() {}

    public Long getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getDisplayName() { return displayName; }
    public String getEmail() { return email; }
    public AccountRole getRole() { return role; }
    public boolean isEnabled() { return enabled; }
    public BigDecimal getCreditLimit() { return creditLimit; }
    public Long getVersion() { return version; }
}

enum AccountRole {
    USER, SUPPORT, ADMIN
}
```

Các method nghiệp vụ sẽ được bổ sung trong ví dụ an toàn phía sau. Field `tenantId` có `updatable=false` là bảo vệ một chiều đối với SQL UPDATE từ JPA, **không thay authorization**. `role`, `enabled` và `creditLimit` vẫn là persistent state có thể bị merge.

### 5.1. Endpoint nhận thẳng entity

```java
@PatchMapping("/api/accounts/{id}")
public UserAccount patch(
        @PathVariable Long id,
        @RequestBody UserAccount input) {
    // Bad: truyền dữ liệu không đáng tin vào entity.
    return repository.save(input);
}
```

Rủi ro:

- Client gửi role ADMIN.
- Client gửi enabled true để mở lại tài khoản.
- Client gửi creditLimit cực lớn.
- Client chọn ID của account khác.
- Client bỏ những fields cũ, khiến chúng thành null/default.
- Client gửi nested associations để sửa related objects.

### 5.2. Frontend không gửi field nội bộ vẫn có thể gặp lỗi

Giả sử client chỉ gửi:

```json
{
  "displayName": "Mai Anh"
}
```

Nếu deserialize thành new `UserAccount` object:

```text
displayName = "Mai Anh"
email = null
role = null
enabled = false
creditLimit = null
```

Đây không phải “partial entity” theo nghĩa JPA hiểu. Nếu merge trên existing row, trạng thái đã mặc định/NULL có thể được copy và gây lỗi NOT NULL hoặc mất dữ liệu.

### 5.3. JSON property có thể bind dù UI không hiện

Jackson, Spring MVC, reflection-based mappers, Lombok setters và public constructors có thể cho bind thêm properties. Annotation như `@JsonIgnore` có thể giúp hạn chế serialization/deserialization một điểm, nhưng không nên là lớp authorization duy nhất; một đường gọi khác (message consumer, batch, test, mapper) vẫn có thể sửa entity.

### 5.4. Overposting và IDOR kết hợp

Client không chỉ sửa thuộc tính bị cấm mà còn có thể đưa `id=456` để sửa account thuộc người khác. Vì vậy cần kiểm tra **resource ownership/tenant scoping** trước khi cập nhật fields.

## 6. Vì sao bỏ field khỏi JSON không có nghĩa “giữ nguyên”?

JSON có ba trạng thái hữu ích cần phân biệt:

1. Property **không có mặt** trong request.
2. Property có mặt với `null`.
3. Property có mặt với một giá trị cụ thể (kể cả `""`, `false` hoặc `0`).

Ví dụ:

```json
{"displayName": "Mai Anh"}
```

khác:

```json
{"displayName": "Mai Anh", "phoneNumber": null}
```

Ở tầng JSON Patch/partial update, tình huống thứ hai có thể có nghĩa **xóa số điện thoại** trong khi thứ nhất có nghĩa **không đổi số điện thoại**.

### 6.1. Entity merge không hiểu field presence

Nếu cả hai payload đều được deserialize thành một entity object với `phoneNumber == null`, `merge` không có metadata nói NULL đến từ “không gửi” hay “gửi null”. Kết quả có thể là xóa phoneNumber ngoài ý muốn.

### 6.2. Primitive defaults đặc biệt nguy hiểm

`boolean enabled` nếu không có JSON property thì object new có giá trị false mặc định. Merge có thể chuyển một tài khoản đang enabled sang disabled, dù client chỉ muốn đổi display name.

### 6.3. DTO và API contract phải quyết định PUT/PATCH semantics

- Với **PUT replacement** đúng nghĩa, request đại diện toàn bộ resource representation và omitted fields có thể mang nghĩa replacement theo contract; không đồng nghĩa cho phép client thay server-managed fields.
- Với **PATCH partial update**, omitted fields thường phải giữ nguyên; explicit null hoặc operation remove có ý nghĩa tùy patch format/contract.
- Với command endpoint chuyên biệt, có thể dùng `ChangeDisplayNameRequest` chỉ nhận một field, tránh ambiguity.

Không chọn semantics từ việc JPA có `merge`; **API contract quyết định**, JPA chỉ ghi dữ liệu được service cho phép.

## 7. Mẫu an toàn: DTO allowlist và cập nhật managed entity

Thay vì nhận entity đầy đủ, dùng một DTO chỉ chứa những fields client được sửa trong use case.

### 7.1. Request DTO

```java
package example.accounts.api;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record UpdateProfileRequest(
    @NotBlank
    @Size(max = 120)
    String displayName,

    @Size(max = 32)
    String phoneNumber
) {}
```

Không có `role`, `tenantId`, `enabled`, `creditLimit`, `createdAt` hoặc `version` ở DTO này.

### 7.2. Entity có domain method

```java
@Entity
public class UserAccount {

    @Id
    private Long id;

    @Column(nullable = false)
    private String tenantId;

    @Column(nullable = false)
    private String displayName;

    private String phoneNumber;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private AccountRole role;

    @Version
    private Long version;

    protected UserAccount() {}

    public void updateProfile(
            String newName,
            String newPhoneNumber) {
        if (newName == null || newName.isBlank()) {
            throw new IllegalArgumentException(
                "Display name is required");
        }
        this.displayName = newName.trim();
        this.phoneNumber = newPhoneNumber;
    }

    // No public setRole/setTenantId in profile workflow.
}
```

**Ý nghĩa:** service chọn một method thể hiện đúng business operation; entity không cần phơi setter cho tất cả fields.

### 7.3. Service tải theo tenant và ID

```java
@Service
public class ProfileService {

    private final UserAccountRepository repository;
    private final CurrentUser currentUser;

    public ProfileService(
            UserAccountRepository repository,
            CurrentUser currentUser) {
        this.repository = repository;
        this.currentUser = currentUser;
    }

    @Transactional
    public ProfileResponse updateProfile(
            Long accountId,
            UpdateProfileRequest request) {

        String tenantId = currentUser.tenantId();
        Long actorAccountId = currentUser.accountId();

        UserAccount account = repository
            .findByIdAndTenantId(accountId, tenantId)
            .orElseThrow(ResourceNotFoundException::new);

        if (!account.getId().equals(actorAccountId)) {
            throw new AccessDeniedException(
                "Not permitted to edit this profile");
        }

        account.updateProfile(
            request.displayName(),
            request.phoneNumber());

        // Managed entity: dirty checking at flush/commit.
        return ProfileResponse.from(account);
    }
}
```

Trong ví dụ này:

- `CurrentUser` là abstraction của authenticated context phía server; phải triển khai an toàn.
- `findByIdAndTenantId` giới hạn row trong tenant.
- Ownership check xác nhận actor chỉ sửa profile của chính mình.
- `ResourceNotFoundException`/`AccessDeniedException` là lỗi ứng dụng cần map thành HTTP semantics an toàn.
- `ProfileResponse` là response DTO không lộ role/credit limit nếu không được phép.
- Service method chạy trong transaction; **không gọi `merge`**, vì entity đã managed.

### 7.4. Repository

```java
public interface UserAccountRepository
        extends JpaRepository<UserAccount, Long> {

    Optional<UserAccount> findByIdAndTenantId(
        Long id, String tenantId);
}
```

Chỉ load theo ID **không đủ** nếu ID có thể thuộc tenant khác. Điều kiện tenant từ authenticated context phải nằm trong lookup và những repository methods khác của command.

### 7.5. Controller

```java
@PatchMapping("/api/accounts/{accountId}/profile")
public ProfileResponse patchProfile(
        @PathVariable Long accountId,
        @Valid @RequestBody UpdateProfileRequest request) {

    return profileService.updateProfile(accountId, request);
}
```

DTO trong ví dụ được thiết kế là một **update-profile command có hai fields**. Nếu muốn PATCH cho phép chỉ gửi một field, DTO cần phân biệt “absent” và “explicit null” như phần sau; `@NotBlank` trên displayName ở đây có nghĩa field này được yêu cầu cho command hiện tại.

### 7.6. Phương pháp an toàn không phụ thuộc việc không có setter

Không có public setter cho `role` giảm nguy cơ vô tình gọi sai, nhưng JPA field access vẫn có thể quản lý field và reflection frameworks có thể bypass access modifiers. **Boundary authorization + allowlist mới là bảo vệ chính.**

## 8. Vì sao phải load managed entity trước khi cập nhật?

Luồng cập nhật có chủ đích:

```text
Authenticated request
       |
       v
Validate DTO
       |
       v
Resolve tenant/actor from security context
       |
       v
Load existing entity by tenant + ID
       |
       v
Check ownership / action permission
       |
       v
Apply only allowed fields via domain method
       |
       v
JPA dirty checking / optimistic version
       |
       v
Flush + commit; return safe DTO
```

### 8.1. Lợi ích của load-before-update

- Có **current persisted state** để kiểm tra business transition.
- Không biến omitted JSON fields thành null/default ngoài ý muốn.
- Có thể kiểm tra tenant/owner/role trước write.
- Giữ các server-owned fields không bị copy từ request.
- Có `@Version` trên entity để phát hiện một số race trong transaction.
- Có thể áp domain methods thay vì bean copying hàng loạt.

### 8.2. Không có nghĩa phải thực hiện hai SQL queries trong mọi trường hợp

Với một số use cases cực đơn giản, an toàn và high-throughput, một **atomic UPDATE ... WHERE tenant_id = ? AND id = ? AND version = ?** có thể phù hợp hơn load-then-dirty-check; nhưng đó là một **explicit allowlisted update query**, không phải mass assignment/merge từ untrusted entity. Phần sau sẽ trình bày điều kiện cần.

### 8.3. Trả response sau commit

Một method `@Transactional` có thể return object trước khi transaction interceptor hoàn tất commit; lỗi DB có thể xảy ra ở flush/commit. Framework phải đảm bảo response success chỉ được phát ra sau transaction completion phù hợp. Không gửi email hay side effects bên ngoài chỉ vì setter/`save` đã chạy.

## 9. Chọn DTO theo từng lệnh thay vì một DTO cho mọi thao tác

Một user account có nhiều workflows:

```text
Update profile
Change email
Verify email
Change password
Suspend account
Assign role
Adjust credit limit
Transfer ownership
```

Nếu tạo một DTO:

```java
record UpdateAccountRequest(
    String displayName,
    String email,
    boolean verified,
    String role,
    boolean enabled,
    BigDecimal creditLimit,
    String tenantId
) {}
```

rồi cố kiểm tra quyền cho từng field tùy user, thiết kế trở nên khó audit và dễ bỏ sót.

### 9.1. Command-specific DTOs

```java
public record RenameProfileRequest(
    @NotBlank @Size(max = 120) String displayName
) {}

public record ChangeEmailRequest(
    @NotBlank @Email String newEmail
) {}

public record AssignRoleRequest(
    @NotNull AccountRole targetRole
) {}

public record AdjustCreditLimitRequest(
    @NotNull @DecimalMin("0.00")
    BigDecimal newLimit,
    @NotBlank String reason
) {}
```

Mỗi DTO có **mục đích và quyền gọi khác nhau**. Role assignment không được tự thực hiện qua update profile.

### 9.2. Endpoint chuyên biệt

```text
PATCH /me/profile
POST  /me/email-change-requests
POST  /me/email-verifications
POST  /admin/accounts/{id}/role-assignments
POST  /risk/accounts/{id}/credit-limit-adjustments
```

Thiết kế API là ví dụ; route names và HTTP methods cần theo contract của ứng dụng. Quan trọng nhất là hành động nhạy cảm có **authorization, validation, auditing và transaction semantics riêng**.

### 9.3. Ranh giới quyền tại service

`@PreAuthorize` ở controller có thể là một lớp bảo vệ, nhưng command service vẫn phải kiểm tra row-level authorization và tenant/owner nếu nó có thể được gọi từ batch, message consumer hoặc endpoint khác. Không dựa duy nhất vào việc frontend chỉ gọi đúng URL.

### 9.4. Tránh “một mapper cho tất cả”

Một `AccountMapper.updateEntityFromDto` quá tổng quát dễ bị dùng lại ở luồng ít quyền. Mapping nên gắn với use case hoặc phải kiểm soát rõ field list/ignore rules.

### 9.5. Không cho input định nghĩa owner/creator

Khi tạo bản ghi mới, `createdBy`/`tenantId` phải được server đặt từ authenticated context hoặc workflow được ủy quyền, không lấy trực tiếp từ `CreateRequest` trừ khi đã xác thực authority. Việc dùng DTO không tự an toàn nếu DTO vẫn phơi những trường này.

## 10. PUT, PATCH và cập nhật một phần: kiểm soát field presence

Các API cập nhật thường gặp ba semantics:

| Hình thức | Ý định | Lưu ý |
|---|---|---|
| PUT replacement | Cung cấp representation thay thế theo contract | Không cho thay server-owned fields |
| PATCH Merge Patch | Chỉ gửi trường đổi, `null` có thể nghĩa remove | Phải phân biệt absent và explicit null |
| PATCH JSON Patch | Danh sách operations theo path | Allowlist paths, kiểm tra preconditions |

### 10.1. PUT không đồng nghĩa JPA `merge`

Tên phương thức HTTP PUT và JPA `merge` **không có quan hệ một-một**. Một PUT có thể dùng managed entity load + explicit fields. Ngược lại `merge` có thể được gọi ngoài HTTP workflows.

### 10.2. Ví dụ PATCH đơn giản

```json
{
  "displayName": "Mai Anh"
}
```

Nếu API contract cho phép partial, sau PATCH:

```text
displayName = "Mai Anh"
phoneNumber = giá trị cũ
role = giá trị cũ
tenantId = giá trị cũ
```

### 10.3. Khi client gửi explicit null

```json
{
  "phoneNumber": null
}
```

Nếu contract định nghĩa `null` là clear field, service có thể xóa phoneNumber **chỉ khi caller được phép**. Nếu phoneNumber bắt buộc thì reject. Không coi NULL là “không đổi” chỉ do library bỏ qua nulls trừ khi API contract nói vậy.

### 10.4. Đừng dùng wrapper DTO nullable mà không có presence tracking

`String phoneNumber` được deserialize thành null cho cả “absent” lẫn “explicit null” ở nhiều binder setups. Nếu cần phân biệt, dùng:

- JSON Merge Patch framework có presence semantics rõ.
- JSON Patch operations.
- Một wrapper `PatchField<T>` với trạng thái absent/present/null.
- `JsonNode`/field-presence adapter có allowlist và type validation.
- Command-specific endpoints (ví dụ `DELETE /me/phone`) nếu đơn giản hơn.

### 10.5. Một wrapper conceptual

```java
public sealed interface FieldChange<T> {
    record Unspecified<T>() implements FieldChange<T> {}
    record SetTo<T>(T value) implements FieldChange<T> {}
    record Clear<T>() implements FieldChange<T> {}
}
```

Phần chuyển JSON → wrapper cần serializer/custom deserializer phù hợp; đây chỉ là **mô hình ý nghĩa**, không phải Jackson tự bind đúng nếu dùng nguyên code.

### 10.6. Apply từng field có chủ đích

```java
void applyPhoneChange(
        UserAccount account,
        FieldChange<String> change) {
    if (change instanceof FieldChange.SetTo<?> set) {
        Object candidate = set.value();
        if (!(candidate instanceof String phone)) {
            throw new IllegalArgumentException(
                "Invalid phone value");
        }
        account.changePhoneNumber(phone);
    } else if (change instanceof FieldChange.Clear<?>) {
        account.clearPhoneNumber();
    }
    // Unspecified -> do nothing.
}
```

Pattern matching dùng wildcard `<?>` để tránh kiểm tra kiểu generic không thể reify ở runtime. Đây là một adapter minh họa; cần bổ sung validation/serializer và Java version phù hợp trong ứng dụng thật.

### 10.7. JSON Merge Patch không tự an toàn

Ngay cả khi có presence tracking đúng, JSON Merge Patch có thể chứa:

```json
{"role": "ADMIN", "tenantId": "TENANT_B"}
```

Service vẫn phải **từ chối hoặc bỏ qua theo policy đã công bố** các properties không thuộc allowlist. Với update security-sensitive fields, thường nên **reject unknown/forbidden fields** thay vì silently ignore vì giúp phát hiện misuse rõ hơn.

### 10.8. JSON Patch paths cũng phải allowlist

```json
[
  {"op": "replace", "path": "/displayName", "value": "Mai Anh"}
]
```

Chỉ các paths như `/displayName`, `/phoneNumber` được chấp nhận. Reject:

```json
[
  {"op": "replace", "path": "/role", "value": "ADMIN"}
]
```

Không áp JSON Patch trực tiếp lên entity qua reflection mà không kiểm tra allowed paths, value types và business transitions.

## 11. Mass assignment qua BeanUtils, MapStruct và reflection mappers

Ngay cả khi không gọi `merge`, một object mapper tổng quát vẫn có thể cập nhật ngoài ý muốn.

### 11.1. Spring BeanUtils

Không nên:

```java
BeanUtils.copyProperties(input, managedEntity);
```

nếu source input có cả protected fields. Một developer thêm field `isAdmin` vào DTO trong tương lai có thể vô tình mở quyền cập nhật.

### 11.2. MapStruct: cấu hình explicit allowlist

Với MapStruct:

```java
@Mapper(componentModel = "spring")
public interface ProfileMapper {

    @BeanMapping(ignoreByDefault = true)
    @Mapping(target = "displayName", source = "displayName")
    @Mapping(target = "phoneNumber", source = "phoneNumber")
    void applyProfile(
        UpdateProfileRequest request,
        @MappingTarget UserAccount account);
}
```

`ignoreByDefault = true` làm rõ: chỉ các fields được liệt kê mới được map. Không có `@Mapping(target="role",...)` hay tenant field.

### 11.3. MapStruct không thực hiện authorization

Mapper biết mapping fields, **không biết actor có quyền sửa entity nào**. Service phải load/authorize trước khi gọi mapper.

### 11.4. `NullValuePropertyMappingStrategy.IGNORE` có thể hữu ích nhưng có giới hạn

```java
@BeanMapping(
    nullValuePropertyMappingStrategy =
        NullValuePropertyMappingStrategy.IGNORE
)
```

Trong update mapping, IGNORE có thể tránh copy null source fields, nhưng không phân biệt đầy đủ “absent” với “explicit clear” nếu DTO không có presence tracking. Nó cũng không ngăn client overposting nếu protected fields được mapped.

### 11.5. Mappers cần review khi entity/DTO phát triển

Nếu entity thêm `securityLevel` hoặc `apiTokenHash`, một mapper “map all matching properties” có thể tự động copy field mới. Allowlist với explicit mappings ít bị rủi ro hơn nhưng vẫn cần review/test cho mỗi use case.

### 11.6. Định nghĩa policy unknown fields

Jackson mặc định có thể bỏ qua unknown JSON properties tùy configuration. Nếu muốn phát hiện tấn công/contract misuse, cân nhắc reject unknown fields ở request DTO boundary. Không dùng một setting toàn ứng dụng thiếu suy xét vì backward compatibility của public API có thể yêu cầu chính sách khác; quyết định theo endpoint.

## 12. Spring Data JPA `save()` không phải “safe update”

Một pattern:

```java
repository.save(inputEntity);
```

không xác nhận authorization. Spring Data JPA repository implementation thường quyết định entity mới/cũ qua metadata như version/ID hoặc `Persistable.isNew`, rồi gọi `EntityManager.persist` cho new hoặc `merge` cho existing. Chi tiết phụ thuộc Spring Data version/`JpaEntityInformation`.

### 12.1. Vì sao `save` với incoming entity nguy hiểm?

Nếu inputEntity mới được tạo từ request, nó chứa:

- Client-controlled ID hoặc các server fields.
- Null/default values với field không gửi.
- Nested associations không được kiểm tra.
- Có thể không có version đúng.

`save` không có cơ chế nhận biết field allowlist.

### 12.2. Tải managed entity rồi gọi `save` nữa có bắt buộc không?

Trong cùng transaction:

```java
@Transactional
public void rename(Long id, String tenantId, String newName) {
    UserAccount account = repository
        .findByIdAndTenantId(id, tenantId)
        .orElseThrow();

    account.renameDisplayName(newName);
    // No repository.save(account) needed for dirty checking.
}
```

Nếu gọi `save(account)` trên managed entity, có thể thừa, phụ thuộc Spring Data internals; không dùng `save` như cách “ra lệnh commit ngay”. `flush` và transaction completion vẫn theo persistence context/transaction.

### 12.3. Spring Data `saveAndFlush`

`saveAndFlush` có thể đẩy SQL sớm để lộ constraint violations trong transaction, nhưng **flush không bằng commit**. Không gửi email/payment side effects sau flush và giả định data chắc chắn committed.

### 12.4. `saveAll` cũng không phải bulk security boundary

`saveAll(untrustedEntities)` có thể áp cùng các rủi ro lên nhiều rows. Với import, map DTOs → các commands được validate/authorized, không cho client tùy ý ghi `tenantId`/`role` hàng loạt.

### 12.5. Entity ID và Spring Data isNew

Các entity có assigned ID, composite key hoặc custom `Persistable` logic có thể được Spring Data đánh giá new/existing khác dự đoán. Không thiết kế security dựa vào việc “nếu ID null thì save luôn insert, nếu không null thì chỉ update”; authorization, existence và allowed-state rules phải rõ dù method nào được gọi.

## 13. IDOR/BOLA: client chọn ID của tài nguyên khác

Giả sử endpoint:

```http
PATCH /api/accounts/123/profile
```

Nếu service:

```java
UserAccount account = repository.findById(id)
    .orElseThrow();
account.renameDisplayName(request.displayName());
```

thì user đã đăng nhập có thể thử ID của người khác.

### 13.1. Phạm vi tenant

```java
repository.findByIdAndTenantId(
    requestedId, authenticatedTenantId);
```

chặn truy cập account thuộc tenant khác **nếu query/repository implementation thực sự áp cả hai predicates**.

### 13.2. Tenant không đồng nghĩa ownership

Hai users cùng tenant vẫn không nhất thiết có quyền sửa profile của nhau. Sau tenant-scoped lookup cần kiểm tra ownership/role/action permission.

### 13.3. Resource-level authorization ở service

```java
if (!policy.canEditProfile(actor, account)) {
    throw new AccessDeniedException(
        "Not authorized");
}
```

`policy` có thể xét actor, resource, relationship và action. Với nhiều actions, tách `canChangeRole`, `canSuspend`, `canTransferOwner` thay vì một quyền chung “canEdit”.

### 13.4. 403 hay 404

Một API có thể trả 404 khi tài nguyên không thuộc tenant để tránh tiết lộ sự tồn tại, và 403 cho những hành động bị cấm trên resource user có quyền biết. Chính sách cần nhất quán và không làm lộ thông tin qua error messages/timing.

### 13.5. Không tự đổi resource identity từ request body

Đường dẫn `/accounts/123` và body có `"id":456` là xung đột. An toàn nhất là request DTO **không có ID**. ID lấy từ path/route và authorization từ authenticated scope. Nếu contract có ID ở body, phải validate consistency chứ không âm thầm dùng một trong hai tùy logic.

### 13.6. Query scoping không thay quyền sửa field

`findByIdAndTenantId` ngăn cross-tenant update nhưng chưa ngăn đổi `role` của tài khoản cùng tenant. Cần cả **row-level** và **field/action-level authorization**.

## 14. Tenant ID là server-owned state

Trong shared-table multitenancy:

```java
@Column(
    name = "tenant_id",
    nullable = false,
    updatable = false
)
private String tenantId;
```

Thường nên set tenant từ context đáng tin cậy:

```java
String tenantId = currentUser.tenantId();
```

không dùng:

```java
String tenantId = request.tenantId();
```

trừ khi workflow admin chọn tenant đã được kiểm tra quyền rõ.

### 14.1. `updatable=false` không phải security boundary

Nó chỉ ảnh hưởng provider-generated UPDATE assignments cho cột ấy. Không ngăn:

- Client chọn resource ID của tenant khác.
- Native SQL update.
- JDBC writers.
- Bulk JPQL DML trong trường hợp mapping khác.
- Thay association/other fields để truy cập nhầm dữ liệu.
- Một insert sai tenant khi field được cho phép insert.

### 14.2. Tenant scoping trên associations

Nếu account có association `department`, client gửi:

```json
{"departmentId": 99}
```

service cần xác minh department đó **thuộc tenant hợp lệ** và actor được chuyển đến nó. FK chỉ bảo vệ department ID tồn tại, không đảm bảo department thuộc cùng tenant nếu schema không enforce composite relationship.

### 14.3. Những tenant mechanisms của provider không phải lý do bỏ test

Hibernate tenant filters, multitenancy resolvers, `@TenantId` hoặc row-level security của DB có thể cung cấp layers bảo vệ, nhưng phải hiểu phạm vi áp dụng cho native SQL, bulk DML, maintenance jobs và repository queries. Tạo tests cho cross-tenant reads/writes; đừng mặc định mọi code path đều được filter.

### 14.4. Audit tenant transfer

Nếu nghiệp vụ cho phép chuyển tài nguyên giữa tenants, đó phải là command riêng với validation references, authorization hai phía, audit/reconciliation và data migration. Không cho client sửa `tenantId` như field profile thường.

## 15. Các trường hệ thống: ID, timestamps, creator, version

Các fields thường không được phép lấy từ JSON update:

```text
id
tenantId
createdAt
createdBy
updatedAt
updatedBy
version
deletedAt
lockReason
emailVerifiedAt
```

### 15.1. `@CreationTimestamp` và `@UpdateTimestamp`

Một số Hibernate-specific annotations có thể tự cập nhật timestamps khi persist/update, nhưng không phải mọi field audit đều tự bảo vệ trước input bị merge. Sử dụng provider features cho đúng mục đích, đồng thời **không map client timestamps vào server-owned fields**.

### 15.2. Auditing listeners

Spring Data auditing (`@CreatedDate`, `@LastModifiedDate`, `@CreatedBy`, `@LastModifiedBy`) hoặc custom JPA lifecycle listeners giúp điền metadata, nhưng vẫn cần security context đáng tin cậy và xác nhận field không bị client điều khiển qua mapper.

### 15.3. Server timestamp khác client timestamp

Client có thể gửi `preferredEventTime` cho một workflow cho phép user chọn lịch. Điều này khác `createdAt` dùng audit thời điểm server ghi. Không tái sử dụng cùng một field cho cả hai semantic.

### 15.4. `@Version` dùng để kiểm soát concurrency, không phải field sửa trực tiếp

Version có thể xuất hiện trong response hoặc `ETag` để client gửi precondition, nhưng không cho client ghi trực tiếp vào managed entity bằng mapper. Service phải **so sánh expected version** với current version, còn JPA cập nhật `@Version` theo optimistic locking rules.

### 15.5. `@Column(updatable=false)` với business immutability

`updatable=false` ngăn JPA đưa cột vào UPDATE SQL tương ứng, nhưng không làm business method an toàn nếu field Java bị sửa gây inconsistent in-memory state và được dùng làm authorization checks trong transaction. Thường không cho field bị sửa trong domain API và dùng DB constraints/permissions khi cần.

## 16. Validating reference IDs: association không phải field thường

Một DTO:

```java
public record ChangeDepartmentRequest(
    @NotNull Long departmentId
) {}
```

không nên được map thành:

```java
account.setDepartment(
    new Department(request.departmentId()));
```

và merge hàng loạt, vì đó là một entity reference do client tạo không có security checks.

### 16.1. Pattern an toàn

```java
@Transactional
public void changeDepartment(
        Long accountId,
        ChangeDepartmentRequest request) {

    String tenantId = currentUser.tenantId();
    UserAccount account = accountRepository
        .findByIdAndTenantId(accountId, tenantId)
        .orElseThrow(ResourceNotFoundException::new);

    permissionService.requireCanMoveAccount(
        currentUser, account);

    Department target = departmentRepository
        .findByIdAndTenantId(
            request.departmentId(), tenantId)
        .orElseThrow(ResourceNotFoundException::new);

    permissionService.requireCanJoinDepartment(
        currentUser, target);

    account.moveToDepartment(target);
}
```

### 16.2. `getReference` không tự xác thực existence/authorization

`em.getReference(Department.class, id)` có thể trả proxy mà chưa truy vấn row ngay. Nó **không** kiểm tra department thuộc tenant được phép hay actor có quyền liên kết. Nếu dùng `getReference` cho performance, phải có cách xác minh cùng invariant trước khi gắn association.

### 16.3. Foreign key chỉ bảo vệ referential integrity

FK bảo đảm referenced ID hợp lệ (theo schema), không đảm bảo user có quyền dùng referenced row. Với multi-tenant data, composite FK có tenant discriminator giúp bảo vệ thêm integrity nhưng vẫn không thay service authorization.

### 16.4. Association changes cần domain invariants

Thay department có thể kéo theo:

- Quyền truy cập tài liệu.
- Quản lý ngân sách.
- Thay đổi manager.
- Audit entries.
- Các thành viên/subscriptions liên quan.

Không coi association ID như một primitive không có tác động nghiệp vụ.

## 17. Cascade `MERGE`: rủi ro lan sang entity liên quan

JPA hỗ trợ cascade operations trong các quan hệ:

```java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.MERGE
)
private List<OrderItem> items;
```

Khi merge một `SalesOrder` detached, provider có thể cascade merge tới `OrderItem` theo mapping. Điều này rất hữu ích khi một aggregate detached được chỉnh sửa hợp lệ trong một workflow đáng tin, nhưng **rất nguy hiểm** nếu graph đến từ input client và không có allowlist.

### 17.1. Nested payload giả mạo

```json
{
  "id": 1001,
  "orderCode": "SO-001",
  "items": [
    {
      "id": 501,
      "quantity": 1,
      "unitPrice": 0.01,
      "discountPercent": 100
    }
  ]
}
```

Nếu server deserialize thành `SalesOrder` + `OrderItem` rồi merge, thay đổi `unitPrice`/`discountPercent` có thể đi xuống children khi cascade `MERGE`. Không có gì trong JPA tự xác nhận user được sửa giá bán đã chốt.

### 17.2. Cascade là persistence operation, không phải authorization

`CascadeType.MERGE` chỉ định provider có thể truyền hoạt động merge đến related entities. Nó không biết:

- Child có thực sự thuộc order đó?
- Child thuộc tenant nào?
- Caller có quyền sửa child không?
- Giá gốc có immutable sau payment không?
- Có được phép thêm/xóa item sau trạng thái PAID không?

Những câu hỏi này thuộc service/domain authorization và database integrity.

### 17.3. Cascade ALL có phạm vi rộng

`CascadeType.ALL` bao gồm nhiều lifecycle actions, không chỉ merge. Gắn ALL bừa bãi lên associations tới **shared entities** như `User`, `Role`, `Product` có thể tạo side effects không mong muốn, đặc biệt khi remove operations đi qua graph.

### 17.4. Không loại cascade bằng cách “cứ để entity detached”

Một detached graph không được tự động an toàn; chính `merge` có thể duyệt graph theo cascades. Cần kiểm soát **tập root fields/child commands**, không nhận arbitrary graph.

### 17.5. Khi cascade merge hợp lý

Ví dụ trong một batch nội bộ đáng tin, aggregate detached có ownership rõ, đầy đủ snapshot fields, version checks và business validation có thể được merge. Nhưng vẫn phải xác định rõ graph boundaries, race conditions và conflict policy; “trusted internal” không thay transaction-level correctness.

## 18. `orphanRemoval` và nguy cơ xóa dữ liệu hàng loạt

Giả sử Order có:

```java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.ALL,
    orphanRemoval = true
)
private List<OrderItem> items = new ArrayList<>();
```

Nếu một workflow thay collection của managed aggregate hoặc merge một detached graph có collection state thiếu children, các phần tử không còn liên kết với parent **có thể được coi là orphan** và bị xóa theo semantics lifecycle/provider khi association bị thay đổi.

### 18.1. JSON chỉ muốn sửa note nhưng collection trống

Client:

```json
{
  "note": "Giao trước 18h"
}
```

Nếu binder tạo entity mới với:

```java
private List<OrderItem> items = new ArrayList<>();
```

thì merged state có thể thể hiện **collection rỗng**, không phải “không đụng đến items”. Khi associations được merge/cascade và orphan removal áp dụng, hậu quả có thể là xóa hoặc thay relationship ngoài ý muốn; chi tiết còn phụ thuộc mapping/provider/initialized state. Không thiết kế API dựa vào hy vọng provider sẽ bỏ qua collection trống.

### 18.2. Không thay entire collection nếu chỉ cần sửa một child

Thay vì:

```java
order.setItems(request.items().stream()
    .map(this::toEntity)
    .toList());
```

dùng command:

```text
PATCH /orders/{orderId}/items/{itemId}/quantity
DELETE /orders/{orderId}/items/{itemId}
POST /orders/{orderId}/items
```

Mỗi command kiểm tra order state, tenant, ownership và child membership.

### 18.3. Kiểm tra child thuộc parent

Một request:

```json
{"itemId": 9999, "quantity": 100}
```

không nên cho sửa item 9999 nếu item đó thuộc order khác. Load child theo `orderId + tenantId + itemId` hoặc kiểm tra membership từ loaded parent trước khi thay đổi.

### 18.4. Domain methods giữ quan hệ hai chiều nhất quán

```java
public void addItem(OrderItem item) {
    if (status != OrderStatus.DRAFT) {
        throw new IllegalStateException(
            "Cannot change paid order");
    }
    items.add(item);
    item.attachTo(this);
}

public void removeItem(OrderItem item) {
    if (status != OrderStatus.DRAFT) {
        throw new IllegalStateException(
            "Cannot change paid order");
    }
    if (!items.remove(item)) {
        throw new IllegalArgumentException(
            "Item does not belong to order");
    }
    item.detachFromOrder();
}
```

Các method `attachTo`/`detachFromOrder` là domain helpers cần triển khai trên `OrderItem` và phù hợp FK nullability/orphan-removal policy. Không gọi remove trên một unrelated item chỉ vì client gửi ID.

### 18.5. `@ElementCollection` cũng cần cẩn trọng

Với tags/addresses/value objects, một collection rỗng hoặc `null` khi merge có thể làm các rows trong collection table bị thay đổi, chứ không chỉ một Java field. Nếu PATCH không đề cập tags, **không cập nhật collection**.

### 18.6. Đừng giả định `orphanRemoval=false` là an toàn

Tắt orphanRemoval có thể để lại orphan references hoặc làm cập nhật join tables thay vì xóa entity; vẫn có thay đổi ngoài ý muốn. Bảo vệ đúng là **không map uncontrolled collection state**.

## 19. Many-to-many: role và permission assignment đặc biệt nhạy cảm

Giả sử:

```java
@ManyToMany
@JoinTable(
    name = "user_roles",
    joinColumns = @JoinColumn(name = "user_id"),
    inverseJoinColumns = @JoinColumn(name = "role_id")
)
private Set<Role> roles = new HashSet<>();
```

Một user được phép đổi displayName không nên thay được toàn bộ `roles` collection.

### 19.1. Overposting roles

```json
{
  "displayName": "Mai Anh",
  "roles": [
    {"id": 1, "name": "ADMIN"}
  ]
}
```

Nếu server nhận `UserAccount` graph đầy đủ, kết quả có thể là thay đổi join-table links hoặc tác động tới Role entities qua cascades, tùy mapping. Đây là **privilege escalation risk**, không đơn thuần lỗi data correctness.

### 19.2. Role assignment là command riêng

```java
@Transactional
public void assignRole(
        Long targetUserId,
        Long roleId,
        String reason) {

    policy.requireCanAssignRoles(currentUser);

    UserAccount target = accountRepository
        .findByIdAndTenantId(
            targetUserId, currentUser.tenantId())
        .orElseThrow(ResourceNotFoundException::new);

    Role role = roleRepository.findAssignableRole(
        roleId, currentUser.tenantId())
        .orElseThrow(ResourceNotFoundException::new);

    policy.requireCanGrantSpecificRole(
        currentUser, role, target);

    target.grantRole(role);
    audit.recordRoleAssignment(
        currentUser, target, role, reason);
}
```

Các services/repository methods là minh họa cho policy cần triển khai. **Không tin rằng mọi administrator có quyền gán mọi role**, đặc biệt các role vượt phạm vi tenant/organization của họ.

### 19.3. Không cascade REMOVE tới shared Role

Một Role có thể liên kết hàng nghìn users; xóa UserAccount không đồng nghĩa xóa Role entity. Tránh `CascadeType.REMOVE`/`ALL` trên many-to-many tới shared reference entities nếu không có lý do/lifecycle ownership thực sự.

### 19.4. Collection write authorization

Ngay cả khi server không cho sửa `Role` fields, chỉ cần sửa join table `user_roles` cũng có thể thay quyền đăng nhập. Phải bảo vệ relationship changes, không chỉ attributes của `Role`.

## 20. Các trường nhạy cảm và immutable sau một trạng thái nghiệp vụ

Đơn hàng sau PAID thường không được chỉnh sửa:

```text
unitPriceAtPurchase
quantity
taxAmount
paymentReference
paidAt
customerId
currencyCode
```

Một request update generic có thể cố thay chúng bằng dữ liệu hợp lệ về syntax.

### 20.1. Kiểm tra trạng thái hiện tại

```java
public void changeShippingAddress(
        ShippingAddress newAddress) {
    if (status == OrderStatus.SHIPPED
            || status == OrderStatus.CANCELLED) {
        throw new BusinessRuleException(
            "Shipping address is locked");
    }
    this.shippingAddress = newAddress;
}
```

Điều kiện cụ thể là business-specific; ví dụ minh họa domain transition rule, không phải quy tắc áp dụng cho mọi order.

### 20.2. Chuyển status có quyền riêng

Không dùng:

```java
order.setStatus(request.status());
```

với một generic update DTO. Tạo workflows:

```java
order.markPaid(paymentConfirmation);
order.markShipped(shippingEvidence);
order.cancel(cancellationReason);
```

Mỗi method kiểm tra trạng thái trước, dữ liệu chứng cứ, quyền thực hiện và transition hợp lệ.

### 20.3. Validation không suy ra state transition

`@NotNull OrderStatus status` chỉ chặn null; nó không chặn chuyển `CANCELLED → PAID` hay set `SHIPPED` khi chưa có tracking code.

### 20.4. Immutable history cần nguồn dữ liệu vững

Một số hệ thống nên lưu price/payment history trong ledger hoặc append-only records, dùng database permissions/triggers/constraints tùy threat model. Chỉ bỏ setter Java không làm SQL writer khác không thể sửa.

### 20.5. Domain method là một lớp bảo vệ bổ sung

Nếu có đường gọi khác bypass domain method bằng reflection, bulk JPQL UPDATE hoặc native SQL, cần kiểm soát các writers và DB-level invariants. Không có một lớp duy nhất thay mọi lớp.

## 21. `@Version`: chống ghi đè khi hai giao dịch cùng sửa

Ngay cả khi DTO allowlist và authorization đúng, người dùng A và B có thể cập nhật cùng record trong hai transactions.

### 21.1. Tình huống lost update

```text
T1 load account version=7, phone="111"
T2 load account version=7, phone="111"
T1 change phone="222", commit -> version=8
T2 change phone="333", commit?
```

Nếu entity có `@Version` và provider thực thi optimistic locking đúng, T2 thường gặp optimistic lock conflict thay vì silently overwrite T1.

### 21.2. Entity version

```java
@Version
@Column(name = "version", nullable = false)
private Long version;
```

JPA có thể phát SQL khái niệm:

```sql
UPDATE user_accounts
SET phone_number = ?,
    version = 8
WHERE id = ?
  AND version = 7;
```

Nếu không có row được cập nhật vì version đã đổi, optimistic conflict được báo. SQL thực tế/provider behavior khác tùy mappings và database.

### 21.3. Hai requests khác thời điểm: JPA version chưa đủ nếu service load mới

Một kịch bản khác:

```text
10:00 Client đọc account version=7
10:05 Người khác sửa -> version=8
10:10 Client gửi PATCH từ màn hình cũ
10:10 Service load account version=8 rồi sửa field
10:10 Commit version=9 thành công
```

JPA `@Version` bảo vệ race **giữa lần load ở service và commit**, nhưng không tự biết client đã xem dữ liệu version=7. Nếu nghiệp vụ yêu cầu phát hiện stale client edits, request phải mang **expected version**/HTTP precondition.

### 21.4. Không copy version từ client vào managed entity

Sai:

```java
managedAccount.setVersion(request.version());
```

Version là field provider quản lý. Đúng hơn là **so sánh**:

```java
if (!Objects.equals(
        account.getVersion(),
        request.expectedVersion())) {
    throw new StaleResourceException();
}
```

rồi cập nhật allowed fields và để JPA kiểm tra optimistic version trong commit.

### 21.5. Khi cần client precondition

DTO:

```java
public record RenameProfileRequest(
    @NotBlank String displayName,
    @NotNull Long expectedVersion
) {}
```

Service:

```java
@Transactional
public ProfileResponse rename(
        Long id, RenameProfileRequest request) {

    UserAccount account = repository
        .findByIdAndTenantId(id, currentUser.tenantId())
        .orElseThrow(ResourceNotFoundException::new);

    policy.requireCanRename(currentUser, account);

    if (!Objects.equals(
            account.getVersion(),
            request.expectedVersion())) {
        throw new StaleResourceException();
    }

    account.renameDisplayName(request.displayName());
    return ProfileResponse.from(account);
}
```

Ở đây expectedVersion chỉ là **precondition**; không được dùng để thay `@Version`.

### 21.6. Version conflict vẫn có thể xuất hiện sau check

Giữa dòng so sánh expectedVersion và commit, transaction khác có thể sửa entity. `@Version` sẽ bảo vệ race đó. Không bỏ `@Version` chỉ vì đã có manual expectedVersion check.

### 21.7. HTTP `ETag` và `If-Match`

Một API theo HTTP semantics có thể gửi strong ETag:

```http
ETag: "account-123-v7"
```

Client update:

```http
PATCH /api/accounts/123/profile
If-Match: "account-123-v7"
Content-Type: application/json

{"displayName": "Mai Anh"}
```

Server xác minh tag gắn với đúng resource representation/version và quyền, rồi chỉ apply nếu precondition còn hợp lệ. Khi không khớp, HTTP `412 Precondition Failed` thường phù hợp; nếu yêu cầu precondition mà thiếu, có thể dùng `428 Precondition Required`. Application-specific version mismatch không dùng HTTP precondition có thể trả `409 Conflict` tùy API contract.

### 21.8. Không công bố version là bí mật

Version/ETag là concurrency token, không phải authorization credential. Dù client đoán đúng version, vẫn phải có quyền sửa tài nguyên.

### 21.9. Không coi optimistic locking là thay thế business invariants

Version chống một dạng concurrent update conflict. Nó không cấm sửa role trái phép, chuyển tenant hay thay price sai domain policy.

## 22. Detached entity cũ và “last write wins” ngoài ý muốn

Một UI có thể lấy full entity response:

```json
{
  "id": 123,
  "displayName": "Mai Anh",
  "phoneNumber": "111",
  "role": "USER",
  "version": 5
}
```

Sau đó admin cập nhật role thành SUPPORT và phone thành 222. Client cũ gửi lại toàn bộ JSON với displayName mới nhưng role/phone/version cũ.

### 22.1. Full-entity merge gây overwrite

Nếu server merge input cũ một cách ngây thơ, role/phone có thể bị ghi đè về snapshot cũ, tùy `@Version`/mapping. Nếu entity có version, stale detached merge thường dẫn đến optimistic conflict; nhưng nếu version không tồn tại, bị bỏ qua, hoặc workflow nạp data mới rồi copy toàn bộ fields, bảo vệ có thể mất.

### 22.2. Những thứ cần bảo vệ cùng lúc

- **Field allowlist**: client không được sửa role.
- **Stale-client precondition**: client phải update trên version đã thấy nếu yêu cầu.
- **JPA optimistic locking**: chống concurrent writes giữa load/commit.
- **Domain invariant**: không cho trạng thái chuyển sai.
- **Transaction boundary**: toàn bộ command atomic.

Một giải pháp chỉ có `@Version` nhưng vẫn nhận role từ request có thể chặn stale writes mà **không chặn authorized-looking nhưng unauthorized field update**.

### 22.3. PATCH field-level không tự giải quyết conflicts

Nếu hai users cùng đổi phone, PATCH chỉ sửa phone vẫn có “last write wins” khi không có concurrency policy. Không gộp khái niệm **partial update** với **optimistic concurrency**.

## 23. Bulk JPQL/native UPDATE: an toàn khi allowlist và scoped rõ

Đôi khi service muốn cập nhật một cột mà không load managed entity.

### 23.1. Explicit update query

Ví dụ Spring Data JPA:

```java
@Modifying
@Query("""
    update UserAccount a
    set a.displayName = :name
    where a.id = :id
      and a.tenantId = :tenantId
      and a.version = :expectedVersion
    """)
int updateDisplayName(
    @Param("id") Long id,
    @Param("tenantId") String tenantId,
    @Param("name") String name,
    @Param("expectedVersion") Long expectedVersion);
```

Truy vấn này allowlist đúng một column và ràng buộc tenant/version. Tuy nhiên còn thiếu một điểm quan trọng.

### 23.2. Bulk JPQL không tự quản lý version và lifecycle như managed entity

Một bulk JPQL UPDATE nói trên **không tự increment `@Version`** trong cách thức managed entity update, trừ khi query/provider explicitly làm điều đó. Nó cũng có thể bỏ qua entity callbacks, Bean Validation lifecycle và persistence context state.

Nếu muốn optimistic version policy, thường cần:

```java
@Modifying
@Query("""
    update UserAccount a
    set a.displayName = :name,
        a.version = a.version + 1
    where a.id = :id
      and a.tenantId = :tenantId
      and a.version = :expectedVersion
    """)
int updateDisplayNameWithVersion(
    @Param("id") Long id,
    @Param("tenantId") String tenantId,
    @Param("name") String name,
    @Param("expectedVersion") Long expectedVersion);
```

Arithmetic increment minh họa với numeric version type. Query phải được kiểm tra trên provider/database version cụ thể; không áp công thức này cho timestamp/custom versions.

### 23.3. Kiểm tra update count

```java
int affected = repository.updateDisplayNameWithVersion(
    id, tenantId, name, expectedVersion);

if (affected != 1) {
    throw new ConflictOrNotFoundException();
}
```

`affected=0` có thể do row không tồn tại, tenant mismatch hoặc version stale. Không trả chi tiết nội bộ nếu làm lộ sự tồn tại của row ngoài tenant.

### 23.4. Row-level authorization vẫn cần thiết

Điều kiện `tenantId` không chứng minh actor có quyền sửa account khác trong cùng tenant. Nếu command không phải self-service, cần condition/permission check trước hoặc thêm authorization predicate có cơ sở vào update query. Cẩn trọng time-of-check-to-time-of-use races; DB isolation/version checks và domain policy phải nhất quán.

### 23.5. Persistence context có thể stale

Bulk update không đồng bộ mọi managed entity đang ở persistence context. Nếu transaction trước đó đã load `UserAccount`, sau bulk UPDATE object còn có giá trị cũ. Cân nhắc `clearAutomatically`/`flushAutomatically` trong Spring Data hoặc tổ chức transaction boundary riêng; không clear bừa làm mất pending changes.

### 23.6. Khi không nên dùng bulk UPDATE

Nếu operation yêu cầu:

- Domain state transition phức tạp.
- Entity callbacks, auditing/encryption logic.
- Cascade/child synchronization.
- Validation liên quan nhiều fields.
- Tính toán quyền theo nhiều related entities.

thì load managed entity và gọi domain method thường an toàn/đọc hiểu tốt hơn.

### 23.7. Native SQL phải có tenant và version semantics tương tự

`UPDATE user_accounts SET role='ADMIN' WHERE id=?` vừa bỏ business authorization vừa có thể bypass `@Version` và JPA callbacks. Đừng cho native/bulk writer trở thành đường tắt vượt policy.

## 24. Entity graph từ client có thể tạo thêm bản ghi ngoài ý muốn

Một input:

```json
{
  "id": 123,
  "addresses": [
    {"label": "home", "street": "A"},
    {"label": "office", "street": "B"}
  ]
}
```

nếu được map thành entity graph rồi merge với cascade có thể tạo related entity objects hoặc sửa collections, tùy mapping/new-state detection. Client không nên tùy ý quyết định:

- Số bản ghi con được thêm.
- ID của bản ghi con.
- Quan hệ parent/child.
- Field system của child.
- Lifecycle/deletion.

### 24.1. Separate create/update/delete child commands

```text
POST   /accounts/{id}/addresses
PATCH  /accounts/{id}/addresses/{addressId}
DELETE /accounts/{id}/addresses/{addressId}
```

Service validate owner/tenant, số lượng tối đa, loại địa chỉ, child membership và invariant trước khi thay collection.

### 24.2. Client-provided child ID không phải bằng chứng ownership

Nếu child `addressId=999` có thực nhưng thuộc account khác, JPA may resolve reference theo ID mà không biết caller có quyền. Luôn xác minh `address.account.id == requestedAccountId` và tenant scope.

### 24.3. Đừng thay references bằng entity constructors từ IDs

`new Address(id)` không biến ID thành an toàn. Phải load/verify membership hoặc dùng scoping UPDATE SQL bảo vệ đúng association.

### 24.4. Immutable child snapshots

Với invoice lines/payment records, thay vì cho generic update child rows, có thể tạo adjustment/reversal records theo nghiệp vụ. Điều này cần domain design chứ không giải quyết bằng `@Column(updatable=false)` đơn lẻ.

## 25. Validation: dữ liệu hợp lệ không đồng nghĩa dữ liệu được phép ghi

Có ba kiểu câu hỏi phải tách biệt:

1. **Syntax/shape:** request có đúng JSON, đúng kiểu, required fields và range không?
2. **Business invariant:** thay đổi có hợp lệ với trạng thái domain hiện tại không?
3. **Authorization:** actor có quyền thực hiện thay đổi trên resource/field/association này không?

### 25.1. DTO validation ở HTTP boundary

```java
public record UpdateProfileRequest(
    @NotBlank
    @Size(max = 120)
    String displayName,
    @Pattern(regexp = "[+0-9 ()-]{0,32}")
    String phoneNumber
) {}
```

Ví dụ regex rất đơn giản, không phải quy chuẩn điện thoại quốc tế. Validation giúp chặn dữ liệu không hợp lệ về hình thức, **không quyết định quyền sửa**.

### 25.2. Bean Validation trên entity

```java
@NotBlank
@Column(name = "display_name", nullable = false)
private String displayName;
```

Entity validation ở JPA lifecycle có thể phát hiện state vi phạm constraints khi persist/update (nếu provider/validation mode được cấu hình). Nó không biết có người cố tình thay role trái phép hay không.

### 25.3. Custom Bean Validation không thay mọi domain method

Một constraint `@ValidRoleChange` có thể cần nhiều context (actor, current state, target user) mà lifecycle validation callback không nên phụ thuộc vào HTTP current user. Với authorization/state transition, explicit policy/domain service thường rõ hơn và dễ test hơn.

### 25.4. Database NOT NULL, UNIQUE, FK và CHECK

Database constraints bảo vệ invariants xuyên JPA và SQL writers khác. Nếu một role value thuộc tập enum hợp lệ nhưng user không được tự gán, `CHECK(role IN (...))` vẫn không chặn self-promotion. DB row-level security/permissions có thể bổ sung bảo vệ tùy kiến trúc, nhưng service authorization vẫn phải được thiết kế.

### 25.5. Không copy server-managed field rồi hy vọng validation bắt được

`enabled=true` có thể là một giá trị hoàn toàn hợp lệ; validation không xem đó là sai. **Allowlist từ đầu** là giải pháp đúng cho mass assignment.

### 25.6. Validation xảy ra ở nhiều thời điểm

DTO validation thường chạy trước service. JPA lifecycle validation/DB constraint error có thể xuất hiện lúc `flush` hoặc `commit`, không nhất thiết khi gọi setter. Xử lý transaction error phải đầy đủ đến completion boundary.

### 25.7. Không lạm dụng `@Valid` trên entity graph từ request

Một nested `@Valid` có thể kiểm tra child fields nhưng không chứng minh child ID được caller sở hữu. Validation cascade và JPA persistence cascade là hai cơ chế khác nhau.

## 26. Authorization theo field: ai có quyền sửa gì?

Một policy đơn giản có thể được biểu diễn:

| Vai trò/actor | Profile name | Email verification | Account role | Credit limit | Tenant transfer |
|---|---|---|---|---|---|
| Self-service user | Chỉ mình | Không set trực tiếp | Không | Không | Không |
| Support agent | Theo scope hỗ trợ | Workflow chuyên biệt | Không hoặc hạn chế | Không | Không |
| Tenant admin | Theo tenant policy | Theo policy | Các roles được phép gán | Có thể không | Không mặc định |
| Risk/finance officer | Không mặc định | Không mặc định | Không mặc định | Theo phê duyệt | Không |
| Platform operator | Theo quyền đặc biệt | Theo workflow | Theo chính sách | Theo quy trình | Workflow riêng |

Đây là bảng ví dụ, không phải một RBAC model chuẩn. Điểm cần thấy là **một quyền chung UPDATE_ACCOUNT thường quá rộng**.

### 26.1. Action-based authorization

Tách:

```java
policy.requireCanUpdateProfile(actor, account);
policy.requireCanAssignRole(actor, targetRole, account);
policy.requireCanChangeCreditLimit(actor, account);
policy.requireCanTransferTenant(actor, account, targetTenant);
```

Không phải mọi role admin đều có quyền bỏ mọi business constraints.

### 26.2. Attribute-based authorization

Quyền có thể phụ thuộc vào:

- Actor identity/role.
- Tenant và department.
- Ownership relationship.
- Account trạng thái suspended/locked.
- Giá trị cũ và giá trị mới.
- Approval/reason/ticket.
- Thời điểm hoặc vùng dữ liệu.

Ví dụ nhân viên hỗ trợ được đổi display name nhưng chỉ khi account đang active và thuộc support region được phân công.

### 26.3. Policy phải sử dụng trusted data

Nếu `actor.role` được lấy từ JSON request hoặc editable entity field có thể bị mass assignment, policy dễ bị bypass. Sử dụng authenticated principal và server-side permission source đáng tin cậy.

### 26.4. Authorization cần nhất quán cho nhiều entrypoints

HTTP controller, scheduled job, event consumer, admin dashboard và batch import có thể gọi cùng service. Thiết kế authorization boundary rõ giữa human-triggered commands và trusted system actions với service identities/permissions riêng.

### 26.5. Không chỉ kiểm tra “có role ADMIN không?”

Một admin tenant A không được sửa tenant B. Một support agent có thể xem tài khoản nhưng không sửa tiền. Một system worker có thể cập nhật payment state mà không có quyền gán role. Policy cần đúng **action + resource + scope**.

## 27. Auditing: ghi lại thay đổi có chủ đích

Với các lệnh nhạy cảm, audit cần trả lời:

```text
Ai thay đổi?
Thay resource nào?
Thuộc tenant nào?
Thay field/quan hệ nào?
Giá trị trước/sau (nếu được phép lưu)?
Vì sao? Được phê duyệt bởi ai?
Khi nào? Request/correlation ID nào?
Transaction đã commit chưa?
```

### 27.1. Domain audit events

Ví dụ:

```java
public record RoleAssignedEvent(
    Long actorId,
    Long targetUserId,
    Long roleId,
    String tenantId,
    String reason,
    Instant happenedAt
) {}
```

Event nên được tạo từ **service sau authorization**, không lấy `actorId`/`tenantId` tùy ý từ payload.

### 27.2. JPA `@PreUpdate` audit có giới hạn

Lifecycle callback có thể ghi timestamp hoặc log một số changes, nhưng thường không có đầy đủ business reason/actor permissions và có thể chạy lúc flush trước commit. Không gửi audit record ra hệ ngoài trong callback rồi giả định transaction sẽ commit.

### 27.3. Envers/automatic entity audit không thay authorization

Hibernate Envers hoặc auditing frameworks có thể lưu revision history khi managed changes xảy ra. Chúng giúp điều tra ai/điều gì thay đổi (với cấu hình actor), nhưng **không ngăn thay đổi sai quyền**.

### 27.4. Cần bảo mật audit logs

Không log password, token, card data hoặc full PII. Có thể lưu field names, masked values, deltas cần thiết, actor ID và reason dưới retention/access policy phù hợp.

### 27.5. Audit trong cùng transaction hoặc outbox

Nếu audit row phải atomically gắn với thay đổi DB, ghi audit/outbox row trong cùng transaction. External event publisher gửi sau commit, có retry/idempotency. Tránh trạng thái “audit đã phát hành nhưng account update rollback”.

### 27.6. Audit sự kiện bị từ chối

Một request cố set `role=ADMIN` qua profile update có thể được log như security event với actor, endpoint, reason code và correlation ID. Không log raw sensitive payload; không phát tán stack trace/internal schema ra response.

## 28. Transaction boundaries: ngăn cập nhật nửa vời và false success

Mẫu service thường là:

```java
@Transactional
public ProfileResponse update(...) {
    // Load, authorize, validate, mutate managed entity.
    // Transaction manager commits after method returns.
}
```

### 28.1. Nếu authorization fail

Service phải ném exception trước mutation khi có thể. Nếu fail sau khi đã sửa managed entity, transaction phải rollback theo policy phù hợp để không flush thay đổi từng phần.

### 28.2. Checked exception trong Spring

Mặc định Spring `@Transactional` thường rollback với unchecked exceptions (RuntimeException/Error), không tự động rollback mọi checked exception. Nếu business policy dùng checked `AccessPolicyException` hoặc `BusinessRuleException`, cấu hình `rollbackFor` hoặc transaction semantics cho phù hợp. Không dựa vào ngoại lệ bị bắt rồi nuốt mà mong rollback tự xảy ra.

### 28.3. Persistence error và rollback-only

Một DB UNIQUE/FK/validation failure ở flush có thể làm transaction rollback-only. Không bắt exception rồi tiếp tục update account khác trong cùng persistence context và commit. Rollback/discard context lỗi, retry trong transaction mới chỉ nếu điều kiện phù hợp.

### 28.4. Commit có thể fail sau service method body

`repository.save` hoặc dirty checking đã chạy không chứng minh transaction committed. SQL/constraint lỗi có thể xảy ra ở flush/commit. Controller không được báo thành công khi transaction completion thất bại.

### 28.5. External side effects

Không gửi email “Bạn đã đổi role thành công” ngay sau khi gọi setter trước commit. Dùng transactional outbox hoặc after-commit mechanism phù hợp; với reliability cần retry/idempotency.

### 28.6. Multi-step commands

Nếu chuyển quyền sở hữu cần sửa account, permissions và audit rows, hãy thiết kế atomic unit-of-work hoặc saga/workflow có compensation rõ. Không gọi nhiều services có independent transactions mà không biết partial completion semantics.

## 29. Exception mapping an toàn cho update commands

| Lỗi | Nguyên nhân | Xử lý thường gặp |
|---|---|---|
| Invalid JSON/DTO | Sai format, missing/invalid fields | 400/422 theo API contract |
| Unauthorized actor | Không có authentication | 401 |
| Forbidden action | Không có quyền sửa resource/field | 403 hoặc 404-hiding theo policy |
| Resource out of tenant | ID không tồn tại trong authorized scope | 404 |
| Expected version stale | Client chỉnh trên phiên bản cũ | 412 với If-Match; 409 nếu API version field |
| JPA optimistic conflict | Concurrent change | 409/412 theo contract |
| Business transition invalid | Trạng thái/điều kiện không cho phép | 409/422 phù hợp |
| Unique DB violation | Email/code trùng | 409 nếu xác định đúng constraint |
| FK constraint violation | Reference không hợp lệ/không tồn tại | 409/422 hoặc server error tùy context |
| Database outage | Infrastructure issue | 5xx, retry policy có kiểm soát |

### 29.1. Không trả raw database exceptions

Hibernate `org.hibernate.exception.ConstraintViolationException`, Spring `DataIntegrityViolationException` và `jakarta.validation.ConstraintViolationException` có ngữ nghĩa khác nhau. API response nên dùng code/message an toàn như `PROFILE_UPDATE_CONFLICT`, không trả SQL, stack trace, table names hoặc credential details.

### 29.2. Không tiết lộ resource ngoài tenant

Nếu account không nằm trong authorized tenant, đừng trả “account 123 tồn tại ở tenant B”. Có thể trả 404 theo policy để giảm khả năng enumeration.

### 29.3. Field errors chỉ dành cho fields công khai

DTO validation có thể trả `displayName` không được để trống. Không đưa internal `role`/`tenantId` values vào response khi user không có quyền xem.

### 29.4. Unknown fields: reject hay ignore

Với profile endpoint, có thể reject `role` trong JSON bằng 400/422 vì field không được hỗ trợ. Nếu một public API chọn forward-compatible ignore unknown fields, server vẫn không được copy chúng vào entity. Policy phải được kiểm thử rõ.

### 29.5. Tên lỗi phải phản ánh kết quả cuối

Nếu transaction rollback, không trả “Profile updated” dù setter đã được gọi. Nếu account có xung đột version, không chấp nhận retry mù tạo lost update.

## 30. API responses: dùng DTO để tránh lộ dữ liệu

Không nên:

```java
return account; // Managed entity graph.
```

vì serialization có thể:

- Truy cập lazy associations gây N+1.
- Lộ `role`, `creditLimit`, `tenantId` hoặc audit fields.
- Gây recursive JSON cycles với quan hệ hai chiều.
- Gây lỗi khi persistence context đã đóng.
- Tạo API contract phụ thuộc entity schema.

### 30.1. Response DTO

```java
public record ProfileResponse(
    Long accountId,
    String displayName,
    String phoneNumber,
    Long version
) {
    public static ProfileResponse from(UserAccount a) {
        return new ProfileResponse(
            a.getId(),
            a.getDisplayName(),
            a.getPhoneNumber(),
            a.getVersion());
    }
}
```

Version có thể được trả làm optimistic precondition metadata nếu API contract cần; không phơi các fields nhạy cảm chỉ vì chúng tồn tại trên entity.

### 30.2. Response snapshot trước commit

Nếu provider tăng `@Version` ở flush/commit, DTO được tạo trước flush có thể chứa version **cũ**. Nếu API cần trả version mới ngay, cần lấy giá trị sau flush hoặc đọc sau commit theo cách phù hợp framework; lưu ý flush vẫn không phải commit. Một phương án là tạo response sau transaction completion từ committed state.

### 30.3. Lazy fields không dành cho response mặc định

Không serialise entity trực tiếp rồi bật Open Session in View để che `LazyInitializationException`. Điều đó có thể kéo thêm SQL sau service boundary và làm khó kiểm soát trường nào lộ. Dùng response DTO/explicit projection.

### 30.4. Không coi `@JsonIgnore` là solution duy nhất

`@JsonIgnore` có thể ngăn một field được deserialize/serialize qua Jackson ở endpoint cụ thể, nhưng JPA entity còn được dùng bởi các consumers/mappers khác. DTO + authorization ở service vẫn là bảo vệ chính.

## 31. Một thiết kế API hoàn chỉnh: hồ sơ người dùng

Giả sử API cho phép chủ tài khoản sửa displayName và phoneNumber, nhưng không được sửa role/tenant/creditLimit.

### 31.1. Request và response

```java
public record EditProfileCommand(
    @NotBlank @Size(max = 120)
    String displayName,
    @Size(max = 32)
    String phoneNumber,
    @NotNull
    Long expectedVersion
) {}

public record ProfileView(
    Long id,
    String displayName,
    String phoneNumber,
    Long version
) {}
```

### 31.2. Domain entity

```java
@Entity
@Table(name = "user_accounts")
public class UserAccount {

    @Id
    private Long id;

    @Column(name = "tenant_id", nullable = false,
            updatable = false)
    private String tenantId;

    @Column(name = "display_name", nullable = false)
    private String displayName;

    @Column(name = "phone_number")
    private String phoneNumber;

    @Enumerated(EnumType.STRING)
    @Column(name = "role", nullable = false)
    private AccountRole role;

    @Column(name = "credit_limit", nullable = false)
    private BigDecimal creditLimit;

    @Version
    private Long version;

    protected UserAccount() {}

    public Long getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getDisplayName() { return displayName; }
    public String getPhoneNumber() { return phoneNumber; }
    public Long getVersion() { return version; }

    public void editProfile(String name, String phone) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Invalid name");
        }
        displayName = name.trim();
        phoneNumber = phone;
    }
}
```

### 31.3. Service

```java
@Service
public class ProfileCommandService {

    private final UserAccountRepository users;
    private final SecurityContextAdapter security;
    private final ProfilePolicy policy;

    public ProfileCommandService(
            UserAccountRepository users,
            SecurityContextAdapter security,
            ProfilePolicy policy) {
        this.users = users;
        this.security = security;
        this.policy = policy;
    }

    @Transactional
    public ProfileView edit(
            Long accountId,
            EditProfileCommand command) {

        Actor actor = security.currentActor();

        UserAccount account = users
            .findByIdAndTenantId(
                accountId, actor.tenantId())
            .orElseThrow(ResourceNotFoundException::new);

        policy.requireCanEdit(actor, account);

        if (!Objects.equals(
                account.getVersion(),
                command.expectedVersion())) {
            throw new StaleResourceException();
        }

        account.editProfile(
            command.displayName(),
            command.phoneNumber());

        // Dirty checking; no merge of request.
        return new ProfileView(
            account.getId(),
            account.getDisplayName(),
            account.getPhoneNumber(),
            account.getVersion());
    }
}
```

`Actor`, `SecurityContextAdapter`, `ProfilePolicy` và custom exceptions là abstractions cần triển khai. Version trong response có thể là pre-flush version như đã lưu ý; use case cần new version phải giải quyết transaction timing.

### 31.4. Controller

```java
@RestController
@RequestMapping("/api/accounts")
public class ProfileController {

    private final ProfileCommandService service;

    public ProfileController(ProfileCommandService service) {
        this.service = service;
    }

    @PutMapping("/{id}/profile")
    public ProfileView edit(
            @PathVariable Long id,
            @Valid @RequestBody EditProfileCommand request) {
        return service.edit(id, request);
    }
}
```

Ở đây `PUT /profile` nhận một representation **đầy đủ cho profile fields được phép sửa**, không phải entire UserAccount representation. Nếu muốn optional individual fields, xây PATCH semantics có presence tracking.

### 31.5. Những gì cố ý không có

Không có:

```java
em.merge(request);
repository.save(requestEntity);
BeanUtils.copyProperties(request, account);
account.setRole(request.role());
account.setTenantId(request.tenantId());
```

Đây không phải ngẫu nhiên: command/API contract không cho client cung cấp các fields đó.

### 31.6. Transaction và REST return timing

Trong Spring proxy mode, transaction interceptor hoàn tất commit trước khi controller method nhận result từ service proxy; nếu commit fail, exception thường propagate và handler sẽ xử lý. Tuy nhiên response DTO được xây trong method trước commit nên version có thể chưa phản ánh provider-generated value mới nếu không flush. Đừng nhầm **response hoàn tất sau commit** với **mọi field của DTO được lấy sau commit**.

## 32. Mẫu an toàn cho role assignment

Đây là workflow khác hẳn profile edit.

### 32.1. DTO dành cho admin command

```java
public record GrantRoleCommand(
    @NotNull Long roleId,
    @NotBlank String reason,
    @NotNull Long expectedVersion
) {}
```

### 32.2. Service phải kiểm tra chính target role

```java
@Transactional
public void grantRole(
        Long accountId, GrantRoleCommand command) {

    Actor actor = security.currentActor();

    UserAccount target = users
        .findByIdAndTenantId(
            accountId, actor.tenantId())
        .orElseThrow(ResourceNotFoundException::new);

    Role role = roles
        .findGrantableByIdAndTenantId(
            command.roleId(), actor.tenantId())
        .orElseThrow(ResourceNotFoundException::new);

    policy.requireCanGrant(actor, target, role);

    if (!Objects.equals(
            target.getVersion(),
            command.expectedVersion())) {
        throw new StaleResourceException();
    }

    target.grantRole(role);
    audit.recordGrant(
        actor, target, role, command.reason());
}
```

### 32.3. Tránh privilege escalation qua hierarchy

Một admin chỉ được cấp role USER không nhất thiết được cấp SUPER_ADMIN. `policy.requireCanGrant` phải xét **vai trò đích**, không chỉ actor có quyền “ROLE_ASSIGN”.

### 32.4. Bảo vệ quyền không chỉ ở thời điểm ghi

Role changes có thể ảnh hưởng active sessions, tokens, caches hoặc các permission grants khác. Thiết kế invalidation/revocation theo business security policy, không kỳ vọng JPA merge tự cập nhật mọi hệ thống phụ thuộc.

## 33. Kiểm thử mass assignment bằng request có trường cấm

Một test chỉ gửi JSON đúng theo DTO không chứng minh server chống overposting. Phải cố tình gửi **những field user không được sửa**.

### 33.1. Fixture

```text
User #123:
  tenant_id = TENANT_A
  display_name = "Mai"
  role = USER
  enabled = true
  credit_limit = 1000000
  version = 7

Actor:
  account_id = 123
  tenant_id = TENANT_A
  authorities = SELF_PROFILE_EDIT
```

### 33.2. Request tấn công

```http
PUT /api/accounts/123/profile
Content-Type: application/json

{
  "displayName": "Mai Anh",
  "phoneNumber": "0900000000",
  "expectedVersion": 7,
  "role": "ADMIN",
  "enabled": false,
  "creditLimit": 999999999999,
  "tenantId": "TENANT_B"
}
```

### 33.3. Kết quả an toàn

Có hai policy được chấp nhận tùy API:

1. **Reject unknown/forbidden fields**, trả 400/422, không thay đổi bất kỳ dữ liệu nào.
2. **Ignore unsupported fields** theo backward-compatibility policy, nhưng nếu thao tác profile thành công thì **chỉ** update displayName/phoneNumber, không đổi role/enabled/creditLimit/tenantId.

Chọn policy nhất quán và test rõ; không được có kết quả thứ ba là một số protected fields bị ghi.

### 33.4. Spring MockMvc skeleton

```java
@Test
void profileUpdateDoesNotAllowRoleEscalation()
        throws Exception {

    mockMvc.perform(put("/api/accounts/{id}/profile", 123L)
            .with(testUser(
                123L, "TENANT_A", "SELF_PROFILE_EDIT"))
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "displayName": "Mai Anh",
                  "phoneNumber": "0900000000",
                  "expectedVersion": 7,
                  "role": "ADMIN",
                  "tenantId": "TENANT_B",
                  "creditLimit": 999999999
                }
                """))
        .andExpect(status().isBadRequest());

    UserAccount reloaded =
        loadFreshAccount(123L);

    assertEquals(AccountRole.USER, reloaded.getRole());
    assertEquals("TENANT_A", reloaded.getTenantId());
    assertEquals(
        new BigDecimal("1000000"),
        reloaded.getCreditLimit());
}
```

`testUser` và `loadFreshAccount` là test helpers cần triển khai; đoạn code giả định endpoint được cấu hình **reject unknown properties**. Nếu chính sách là ignore unknown, đổi assertion HTTP status/allowed-field changes, nhưng vẫn assert protected fields không đổi.

### 33.5. Tại sao phải reload từ database?

Một Java object trong test có thể giữ giá trị cũ do first-level cache, trong khi transaction khác đã commit thay đổi. Mở EntityManager mới hoặc thực hiện DB query độc lập sau transaction completion để xác nhận trạng thái thực.

### 33.6. Test negative không chỉ đọc response

Không đủ assert JSON response không có `role`. Server có thể đã **sửa role ở DB nhưng không trả field ra response**. Assert database values và audit trail.

## 34. Kiểm thử omitted, null và primitive defaults

Một PATCH chỉ gửi displayName phải bảo toàn phone, enabled, creditLimit và associations nếu chúng không được đề cập.

### 34.1. Fixture

```text
Before:
    displayName = Mai
    phoneNumber = 0900123456
    enabled = true
    role = USER
    creditLimit = 1000000
```

Request:

```json
{"displayName": "Mai Anh"}
```

Expected:

```text
After:
    displayName = Mai Anh
    phoneNumber = 0900123456
    enabled = true
    role = USER
    creditLimit = 1000000
```

### 34.2. Explicit null có contract riêng

Request:

```json
{"phoneNumber": null}
```

Nếu API cho phép clear phone, database value trở thành NULL; nếu không, nhận validation error. Test phải khác omitted-field test.

### 34.3. Empty string và zero

`{"displayName": ""}`, `{"creditLimit": 0}` và `{"enabled": false}` là các giá trị cụ thể. Không dùng một mapper bỏ qua “falsy values” vì nó có thể che mất các thay đổi hợp lệ hoặc bỏ qua lệnh clear do user muốn.

### 34.4. Test PUT replacement

Nếu PUT contract là thay thế **toàn bộ profile representation** (ví dụ displayName và phone), thiếu phone có thể mang nghĩa clear, nhưng vẫn không được đụng server-owned role/tenant. Phân biệt resource representation “profile” với nguyên entity “account”.

### 34.5. Thêm field mới vào entity

Khi entity thêm `passwordResetRequired`, `riskLevel` hoặc `emailVerified`, test overposting phải bổ sung fields này. Dùng DTO allowlist giúp field mới không tự được cập nhật khi endpoint không thay đổi, nhưng regression tests vẫn hữu ích.

## 35. Kiểm thử IDOR và tenant boundary

### 35.1. Cross-tenant ID

```text
Actor tenant A, accountId=123
Target account tenant B, accountId=456
Request PATCH /api/accounts/456/profile
```

Expected: 404 hoặc 403 theo policy; tenant B row không đổi.

### 35.2. Same-tenant different owner

```text
Actor user 123 in tenant A
Target user 124 in tenant A
Action self-service profile update
```

Nếu self-service chỉ cho sửa bản thân, request phải bị từ chối dù tenant match. Test này bắt lỗi code chỉ dùng `findByIdAndTenantId` mà quên ownership.

### 35.3. Relationship IDOR

```json
{"departmentId": 999}
```

Nếu department 999 thuộc tenant B, lệnh từ tenant A không được liên kết dù FK hợp lệ. Nếu department 999 thuộc tenant A nhưng actor không được tham gia, vẫn phải reject.

### 35.4. Child membership

User được sửa `OrderItem#50` của Order A nhưng gửi `itemId=60` thuộc Order B. Dù cả hai orders ở cùng tenant, phải xác minh child thuộc parent được phép sửa. Test rằng B không bị ảnh hưởng.

### 35.5. Không lộ through error details

Không nên thông báo:

```text
Department 999 exists but belongs to tenant B.
```

cho caller không được xem tenant B. Sử dụng safe “not found/not permitted” response theo policy.

## 36. Kiểm thử cascade và collections

### 36.1. Kịch bản cascade MERGE

Fixture:

```text
Order #1001 in DRAFT:
    Item #501 unitPrice=500000
    Item #502 unitPrice=100000
```

Payload đổi note nhưng kèm:

```json
{
  "note": "Giao trong giờ hành chính",
  "items": [
    {
      "id": 501,
      "unitPrice": 1,
      "quantity": 1000
    }
  ]
}
```

Nếu endpoint chỉ cho sửa note, integration test assert **cả hai items và giá** giữ nguyên.

### 36.2. Orphan removal regression

Gửi PATCH note **không có items field**; assert Item #501/#502 vẫn tồn tại sau transaction. Điều này giúp phát hiện mapper tạo empty child collection rồi thay thế managed collection.

### 36.3. Client yêu cầu xóa child

Nếu endpoint cho xóa một item, service phải:

1. Load parent theo tenant.
2. Check action/state permission.
3. Load child thuộc chính parent.
4. Gọi domain `removeItem`.
5. Flush/commit và xác minh đúng một child bị xóa.

Không nhận một danh sách IDs mới rồi coi mọi IDs bị thiếu phải delete, trừ khi API replacement semantics được xác định rõ và có quyền đầy đủ.

### 36.4. Many-to-many role links

Profile update gửi `roles:[{"id":1}]` phải không làm thêm link USER→ADMIN. Test trực tiếp `user_roles` join table, không chỉ `Role` entity fields.

### 36.5. Provider-dependent lifecycle

Các chi tiết merge/cascade/orphanRemoval phụ thuộc mapping, detached graph completeness, initialized collections và provider. Không viết test chỉ assert Java collection content; chạy với JPA provider/database tương đương production và kiểm tra rows thực.

## 37. Kiểm thử optimistic locking và stale request

Cần ít nhất hai lớp test.

### 37.1. Stale client version

1. Client GET profile với version 7.
2. Một lệnh khác commit, version tăng thành 8.
3. Client gửi edit với expectedVersion 7.
4. Service load version 8, thấy không khớp, trả 409/412.
5. Database giữ version 8 và không ghi stale changes.

Đây là application precondition test.

### 37.2. Race giữa load và commit

Tạo hai independent EntityManagers/transactions:

```text
T1 load account version=8
T2 load account version=8
T1 modify/commit -> version 9
T2 modify/commit -> optimistic conflict/rollback
```

`@Version` bảo vệ khi hai transactions cùng chỉnh phiên bản cũ. Test cần chắc chắn hai EMs độc lập và không bị một `@Transactional` test wrapper che transaction boundaries.

### 37.3. Không phụ thuộc exception wrapper duy nhất

Ở JPA có thể gặp `OptimisticLockException`; Spring có thể dịch sang optimistic locking data-access exception. Chọn assertions ở application boundary và kiểm tra DB outcome, vì wrapper/timing có thể khác provider.

### 37.4. Collection update và version

Thay collection có tăng parent version hay không có thể phụ thuộc ownership/mapping/provider. Nếu business yêu cầu optimistic lock ở cấp aggregate, test đồng thời thay children/parent và chọn version/check strategy phù hợp; đừng giả định `@Version` trên parent tự bảo vệ mọi native/join-table writes.

### 37.5. Bulk UPDATE regression

Nếu có JPQL bulk update, test affected-row count khi expectedVersion sai, increment version khi thành công và clear/reload persistence context để tránh stale managed state.

## 38. Kiểm thử transaction và side effects

### 38.1. Authorization failure rollback

Nếu policy từ chối, assert không thay database row, join table, audit success record hoặc outbox success event.

### 38.2. Constraint error rollback

Thử đổi email thành email trùng đã có. Database UNIQUE từ chối; transaction rollback. Không có phần profile được commit nửa chừng nếu operation có atomicity requirement.

### 38.3. Service call + commit

Integration test phải quan sát transaction hoàn tất, không chỉ mock `repository.save` được gọi. Dùng EntityManager mới hoặc DB query sau commit để xác minh.

### 38.4. Email/outbox

Thử lệnh đổi role nhưng DB commit fail; email thông báo đổi role không được gửi với “đổi thành công”. Nếu event lưu outbox trong cùng transaction, audit/outbox row rollback theo.

### 38.5. Retry không biến unauthorized thành authorized

Authorization failure hoặc invalid input không nên tự retry. Với transient DB error có thể retry trên transaction/context mới theo idempotency policy; mỗi retry vẫn phải enforce permissions và current state.

### 38.6. Transaction isolation và TOCTOU

Nếu permission phụ thuộc vào ownership/status có thể đổi đồng thời, cần xem isolation, version checks, pessimistic locking hoặc conditional UPDATE. Một authorization check trong transaction **không có nghĩa mọi dữ liệu liên quan không thể đổi trước commit**. Chọn concurrency model theo invariant quan trọng.

## 39. Những biện pháp tưởng an toàn nhưng chưa đủ

### 39.1. Chỉ dùng `@JsonIgnore`

`@JsonIgnore` hoặc `@JsonProperty(access = READ_ONLY)` có thể chặn serialization/deserialization của một field trong Jackson, nhưng không bảo vệ:

- BeanUtils/MapStruct reflection copy ở service.
- Message consumer tạo entity trực tiếp.
- Bulk JPQL/native SQL writer.
- Một endpoint khác dùng DTO có field nhạy cảm.

**Sử dụng DTO allowlist + authorization như cơ chế chính; Jackson annotations chỉ là một lớp phụ.**

### 39.2. Chỉ dùng `@Column(updatable=false)`

Nó ảnh hưởng SQL UPDATE do JPA tạo với cột đó. Không ngăn client chọn ID khác, thêm record mới với tenant sai, sửa associations hay field khác. Cũng không thay policy ở domain.

### 39.3. Chỉ dùng `@Version`

Version chống một số concurrent write conflicts, không xác định actor có quyền đổi role/creditLimit. Một request có expectedVersion đúng vẫn có thể tấn công mass assignment nếu mapping cho phép.

### 39.4. Chỉ dùng `@Valid`

Validation giúp kiểm tra shape/invariants, không quyết định quyền người dùng. `role=ADMIN` có thể là một enum hợp lệ nhưng không được phép.

### 39.5. Chỉ dùng Spring Security `@PreAuthorize("isAuthenticated()")`

Đăng nhập không có nghĩa sở hữu resource hoặc được sửa mọi fields. Cần row-level/action-level policy.

### 39.6. Chỉ dùng repository `findById`

ID do client chọn có thể thuộc tenant/owner khác; phải scope/authorize.

### 39.7. Chỉ bỏ setter nhạy cảm

JPA field access/reflection/mappers có thể ghi private fields; thiếu setter giúp domain API rõ hơn nhưng không phải bảo vệ duy nhất.

### 39.8. Chỉ dùng Hibernate `@DynamicUpdate`

`@DynamicUpdate` có thể khiến SQL chỉ update dirty columns theo provider-specific strategy, nhưng **giá trị role sai do merge vẫn có thể được xem là dirty**. Nó là tối ưu DML, không phải field allowlist/security control.

### 39.9. Chỉ dùng dirty checking

Dirty checking hoạt động trên managed state, không biết thay đổi đó có được phép. Copy properties từ request vào managed entity có cùng rủi ro như merge.

### 39.10. Chỉ dùng tenant ID từ HTTP request

`request.tenantId` do client kiểm soát, không đáng tin. Tenant scope phải lấy từ authenticated context/authorized delegation, không lấy từ field được client tùy ý chọn.

### 39.11. Chỉ kiểm tra tenant của parent

Child/related entity có thể thuộc tenant khác hoặc parent khác. Cần check association membership/cross-tenant integrity.

### 39.12. Chỉ map IDs rồi gọi `getReference`

`getReference` có thể cho proxy mà không xác minh ownership/existence ngay. Chưa đủ cho authorization.

### 39.13. Chỉ trả 200 khi `save()` không ném lỗi

SQL/constraints có thể fail ở commit. Phải xác nhận transaction completion, tránh side effects trước commit.

### 39.14. Chỉ test response không chứa role

API có thể đã sửa role ở DB nhưng không serialize nó. Kiểm tra persisted state và relationship join tables.

### 39.15. Chỉ test user hợp lệ

Happy-path tests không phát hiện IDOR, overposting, omitted fields, client NULL, cascade MERGE hay stale version.

### 39.16. Chỉ xử lý role ở frontend

Frontend ẩn ô role không ngăn curl gửi `{"role":"ADMIN"}`. Policy phải nằm server-side.

### 39.17. Chỉ dùng `CascadeType.MERGE` vì “tiện”

Merge graph có thể sửa related entities từ nested payload; cascade không tự hiểu quyền và business aggregate boundaries.

### 39.18. Chỉ xóa phần tử trong Java Set

Việc thay đổi many-to-many links có thể cấp/tước quyền trên DB. Kiểm tra authorization cho association update.

### 39.19. Chỉ dùng `NullValuePropertyMappingStrategy.IGNORE`

Nó có thể giúp giữ field khi source null nhưng không giải quyết explicit null/absent semantics hoàn chỉnh, không chặn protected non-null values và không thay authorization.

### 39.20. Chỉ dùng `saveAndFlush()`

Flush không phải commit. Không đảm bảo transaction thành công hoặc side effect ngoài DB được đồng bộ.

### 39.21. Chỉ bắt lỗi rồi tiếp tục cùng transaction

Sau persistence/constraint failure, transaction có thể rollback-only. Bắt exception không tự sửa context/transaction. Rollback rồi xác định hướng xử lý trong transaction mới.

### 39.22. Chỉ kiểm tra quyền tại controller

Batch import, message consumer hoặc service khác có thể gọi command service trực tiếp. Authorization phải có boundary tin cậy đủ gần thao tác domain.

### 39.23. Chỉ dùng DB foreign key

FK bảo vệ reference tồn tại, không nhất thiết bảo vệ cùng tenant hoặc actor có quyền liên kết. Có thể dùng composite FK/RLS bổ sung, vẫn cần app policy.

### 39.24. Chỉ sử dụng native UPDATE cho nhanh

Bulk/native writes có thể bypass lifecycle/`@Version`/auditing, thậm chí cập nhật nhiều rows nếu WHERE thiếu tenant. Cần allowlist, scoped predicates, rowcount và tests.

### 39.25. Chỉ nghĩ “internal API là trusted”

Một internal service có thể nhận dữ liệu client đã được forward, hoặc credentials của nó bị lạm dụng. Các command service vẫn nên duy trì invariant/authorization theo trust boundary rõ.

## 40. So sánh các chiến lược cập nhật

| Chiến lược | Ưu điểm | Nhược điểm/rủi ro | Khi phù hợp |
|---|---|---|---|
| Deserialize JSON trực tiếp thành entity rồi `merge` | Ít code | Mass assignment, NULL/default overwrite, cascade graph, stale state | **Không nên** cho untrusted public inputs |
| Tạo entity mới từ DTO rồi `save` | Dễ viết | Similar merge/isNew, mất existing state | Chỉ với create thật sự và server-owned fields đã kiểm soát |
| BeanUtils copy tất cả vào managed entity | Ít mapping code | Mở rộng field ngoài ý muốn khi DTO thay đổi | Không dùng với security-sensitive updates |
| MapStruct allowlist vào managed entity | Compile-time mapping rõ | Vẫn cần authorization, null/patch semantics | Dữ liệu đơn giản, nhiều fields công khai |
| Load managed + domain method | Rõ invariant/authorization, tránh merge untrusted | Cần SELECT, domain/service code | **Mặc định tốt** cho business commands |
| Explicit scoped JPQL UPDATE | Ít round trips, allowlisted columns | Bypass callbacks/dirty check/version nếu không tự xử lý | Trường đơn giản, invariants rõ và được test |
| JSON Patch qua allowlisted operations | Hỗ trợ partial updates phức tạp | Patch parser/path rules, security checks | API cần genuine partial semantics |
| Trusted detached aggregate merge | Có thể tái sử dụng graph snapshot | Version/cascade/graph completeness, khó audit | Internal workflow có ownership/trust rõ |

### 40.1. Câu hỏi quyết định

Trước khi chọn `merge()` cho dữ liệu input:

1. Đầu vào có phải entity đầy đủ đã được tạo từ một **nguồn đáng tin** không?
2. Mọi persistent fields/associations có thực sự được phép copy không?
3. Các trường absent/null có semantic rõ không?
4. Entity/children có cùng tenant/owner được xác minh không?
5. Có @Version hoặc concurrency precondition thích hợp không?
6. Cascade MERGE/orphanRemoval có ảnh hưởng related rows không?
7. Có business transitions/audit/side effects cần domain methods không?
8. Transaction completion/error handling có được test không?

Nếu một câu trả lời là “không chắc”, **không** merge nguyên incoming entity; chọn command/DTO allowlist và kiểm tra context trước.

### 40.2. Quy tắc ưu tiên

Với input từ web/mobile API, cách bắt đầu là:

```text
Request DTO
 -> validate
 -> authorized entity lookup
 -> action policy
 -> domain method / explicit field mapping
 -> transaction commit
 -> response DTO
```

Chỉ chuyển sang bulk query/advanced patching khi có lý do rõ và bảo vệ tương ứng.

## 41. Ma trận mối đe dọa và lớp phòng vệ

| Tấn công/tình huống | Dấu hiệu | Lớp bảo vệ chính | Test cần có |
|---|---|---|---|
| Self-assign ADMIN | `"role":"ADMIN"` trong profile JSON | DTO allowlist + role command policy | Role DB không đổi |
| Cross-tenant update | Path ID của tenant khác | Tenant-scoped repository + authorization | Target row không đổi, safe 404/403 |
| Same-tenant IDOR | ID user khác cùng tenant | Ownership/action policy | Denied + DB unchanged |
| Client chọn tenant | `"tenantId":"B"` | Server current tenant | Tenant ID không đổi |
| Reset enabled mặc định | Omitted primitive boolean | DTO, no entity merge | Enabled giữ nguyên |
| Xóa phone ngoài ý muốn | Omitted → NULL | PATCH presence semantics | Omitted preserves, explicit null as policy |
| Sửa giá order item | Nested payload có unitPrice | Child allowlist/domain invariants | Price DB không đổi |
| Xóa items do empty list | Omitted collection mapped as [] | Không replace collection từ request | Children giữ nguyên |
| Thay role memberships | Nested many-to-many links | Dedicated grant/revoke command | Join table không đổi |
| Associate resource B vào A | Client-controlled departmentId | Related entity tenant/permission checks | Cross-tenant link denied |
| Client stale edit | expectedVersion cũ | Precondition + @Version | Conflict, no lost update |
| Concurrent update | Hai transactions version N | @Version/conditional update | Một commit, một conflict |
| Bulk update bypass policy | UPDATE WHERE id=? | Scoped WHERE + rowcount + version | Unauthorized 0 affected |
| DB constraint violation | Duplicate email/invalid FK | DB constraints + rollback | No partial commit |
| Audit side effect sớm | Email sent before rollback | Outbox/after commit | No success event on rollback |
| Sensitive response leak | Entity directly serialized | Response DTO allowlist | No protected JSON fields |

### 41.1. Threat model không chỉ xét người dùng ác ý

Các lỗi tương tự có thể xuất hiện khi:

- Frontend cũ gửi stale full DTO.
- Batch import thiếu một field.
- Mapper tự động thêm field sau refactor.
- Business service được reuse ở endpoint mới.
- Message schema thay đổi.
- Migration thay tenant/owner relationships.

**Thiết kế tốt ngăn được cả lỗi lập trình không cố ý**, không chỉ tấn công.

### 41.2. Quyền mặc định nên hạn chế

Nếu API không có yêu cầu rõ cho client sửa field X, không nên đưa X vào request DTO chỉ “để sau này cần”. Khi cần mở quyền mới, tạo command và review policy/tests.

### 41.3. Kiểm tra audit và DB state

Một request bị từ chối không được tạo successful audit event; một update hợp lệ phải có audit theo domain policy. Security tests cần nhìn cả outcome và side effects, không chỉ HTTP status.

## 42. Bài tập thực hành

### Bài 1 — Nhận diện mass assignment

Đọc endpoint:

```java
@PutMapping("/accounts/{id}")
public UserAccount save(
        @PathVariable Long id,
        @RequestBody UserAccount input) {
    input.setId(id);
    return repository.save(input);
}
```

Entity có `role`, `tenantId`, `enabled`, `createdAt`, `creditLimit`. Hãy liệt kê ít nhất năm dữ liệu client có thể tác động trái phép và viết bản thiết kế thay thế bằng DTO allowlist.

### Bài 2 — `merge` có trả về chính object detached?

Tạo entity `UserAccount`, persist vào DB, đóng EntityManager, sửa detached object rồi `em2.merge(detached)`. Quan sát managed result và detached input; giải thích vì sao phải dùng instance do merge trả về nếu workflow thực sự cần merge.

### Bài 3 — Omitted field

DB hiện có:

```text
displayName = Mai
phoneNumber = 0900123456
role = USER
enabled = true
```

Client gửi `{"displayName":"Mai Anh"}`. Mô tả expected state theo PATCH semantics và vì sao deserialize thẳng thành entity mới rồi merge có thể sai.

### Bài 4 — Explicit null khác omitted

Viết test cho hai request:

```json
{"displayName":"Mai Anh"}
```

và:

```json
{"phoneNumber":null}
```

Thiết kế parser/DTO field-presence semantics để request đầu giữ phone, request sau clear phone nếu policy cho phép.

### Bài 5 — Primitive default

Entity có `boolean enabled=true`. Body không gửi enabled; mapper tạo new entity làm enabled=false. Viết regression test xác minh enabled không đổi khi client chỉ cập nhật displayName.

### Bài 6 — DTO riêng cho role assignment

Tách `EditProfileRequest` và `AssignRoleRequest`. Thiết kế hai service methods với action policies khác nhau, không dùng một DTO chứa role/creditLimit/tenant cho cả hai.

### Bài 7 — Tenant-scoped lookup

Viết repository:

```java
Optional<UserAccount> findByIdAndTenantId(
    Long id, String tenantId);
```

Tạo actor tenant A cố PATCH account tenant B. Kỳ vọng resource không bị thay đổi và response không lộ tenant B.

### Bài 8 — Same-tenant IDOR

Hai users A/B cùng tenant. Self-service profile endpoint chỉ được cập nhật chính mình. Chứng minh chỉ có tenant-scoped lookup vẫn chưa đủ; thêm ownership policy và test.

### Bài 9 — Path ID và body ID xung đột

Request `PUT /accounts/123` với body `{"id":456,...}`. Thiết kế API DTO không có id; giải thích vì sao việc server chọn tùy ý một ID từ hai nguồn có thể gây lỗi truy cập.

### Bài 10 — MapStruct allowlist

Viết `@BeanMapping(ignoreByDefault=true)` cho profile với chỉ `displayName` và `phoneNumber`. Thêm field mới `securityLevel` vào entity và xác nhận mapper không tự cập nhật field ấy.

### Bài 11 — BeanUtils anti-pattern

Giả sử `BeanUtils.copyProperties(request, managedAccount)`. Khi DTO được thêm field `role`, điều gì xảy ra? Thay bằng explicit domain method/mapper allowlist và so sánh maintainability.

### Bài 12 — `@Column(updatable=false)`

Entity có tenantId `updatable=false`. Hãy chỉ ra ít nhất năm đường tấn công/lỗi mà annotation này không ngăn được (IDOR, INSERT sai tenant, native SQL, association, unauthorized fields).

### Bài 13 — Cascade MERGE trên order items

`Order` có `cascade=MERGE` tới `items`. Client gửi nested `unitPrice=1` cho item thuộc đơn đã thanh toán. Thiết kế DTO chỉ đổi note và test unitPrice không đổi.

### Bài 14 — Orphan removal

Entity `Order` có `orphanRemoval=true`. Một PATCH note không chứa items nhưng binder tạo empty collection. Giải thích rủi ro và thiết kế apply logic không thay collection khi request không đề cập items.

### Bài 15 — Child IDOR

Client sửa `OrderItem#60` nhưng item thuộc Order B, không phải Order A trong route. Viết repository/service check cả `tenantId`, `orderId`, `itemId` và bảo đảm không ảnh hưởng B.

### Bài 16 — Many-to-many privilege escalation

`UserAccount.roles` là `@ManyToMany`. Client gửi `roles:[{id:1}]` khi sửa profile. Thiết kế security test kiểm tra `user_roles` join table không đổi.

### Bài 17 — Shared Role và cascade REMOVE

Một Role được nhiều users dùng. Vì sao `CascadeType.ALL` trên `UserAccount.roles` có thể nguy hiểm? Chọn cascade policy và command grant/revoke phù hợp.

### Bài 18 — Reference thuộc tenant khác

Client chuyển account sang `departmentId=99` của tenant B. Thiết kế `findByIdAndTenantId` cho Department và policy kiểm tra quyền trước khi gắn association.

### Bài 19 — `getReference`

Thử lấy Department bằng `em.getReference(Department.class, id)`. Giải thích vì sao chỉ tạo proxy không xác minh actor có quyền sử dụng department và khi nào nên query scope trước.

### Bài 20 — Business transition

Order đã `SHIPPED`, client gửi `status=DRAFT` và `totalAmount=0`. Thiết kế domain method `cancel(...)`/`refund(...)` theo workflow thay vì generic setters; nêu invariant cần kiểm tra.

### Bài 21 — Optimistic locking trong hai transactions

Tạo hai EntityManagers load cùng account `version=7`, cả hai sửa phone, commit T1 trước T2. Assert T2 optimistic conflict/rollback và database chỉ có giá trị T1.

### Bài 22 — Stale client

Client GET version 7; sau đó DB lên version 8; client PATCH với expectedVersion 7. Service load version 8 và so sánh precondition; phân biệt với optimistic locking chống race load-to-commit.

### Bài 23 — ETag/If-Match

Thiết kế endpoint GET trả strong ETag gắn với version của profile; PATCH bắt buộc `If-Match`. Viết response 412 khi không khớp, 428 khi thiếu nếu API policy yêu cầu precondition.

### Bài 24 — Không copy version từ input

Code sai: `account.setVersion(dto.expectedVersion())`. Thay bằng comparison rồi managed entity update; giải thích vì sao version field phải được JPA quản lý.

### Bài 25 — Bulk JPQL update

Viết `@Modifying @Query` chỉ update `displayName` theo `id + tenantId + expectedVersion` và increment numeric version. Check affected rows, xử lý 0 rows an toàn, không lộ resource ngoài tenant.

### Bài 26 — Persistence context sau bulk DML

Trong cùng EntityManager, load Account rồi chạy JPQL bulk UPDATE. Giải thích vì sao managed object có thể stale; chọn clear/refresh/transaction boundary phù hợp mà không làm mất pending changes.

### Bài 27 — Bean Validation vs authorization

`role=ADMIN` và `creditLimit=1000000` đều hợp lệ theo enum/range. Một user thường không được sửa chúng. Liệt kê layers DTO validation, domain rules, authorization và DB constraints và mục đích riêng.

### Bài 28 — Response DTO

Entity chứa password hash, role, tenant, credit limit, timestamps. Thiết kế `ProfileResponse` chỉ trả những fields cần UI. Viết test JSON response không có protected data; test riêng rằng DB cũng không bị mass assignment.

### Bài 29 — Transaction rollback và audit

Một lệnh role assignment tạo audit event, nhưng DB commit fail vì unique/FK constraint. Thiết kế transactional outbox/audit row để không gửi thông báo thành công sai.

### Bài 30 — Bộ regression tests tổng hợp

Viết integration test suite với các case:

```text
1. Happy path edit allowed fields
2. Overposting role/tenant/creditLimit
3. Omitted phone preserves old value
4. Explicit null according to PATCH contract
5. Cross-tenant ID
6. Same-tenant wrong owner
7. Cross-tenant department reference
8. Nested item price manipulation
9. Orphan removal by omitted collection
10. Role join-table modification
11. Stale client version
12. Concurrent @Version update
13. DB constraint rollback
14. No premature outbox/email
15. Response DTO contains no secrets
```

Dùng database/provider gần production, chạy transaction thật và reload data bằng context mới.

### Bài 31 — Trusted batch import

Một batch nội bộ nhập customer updates từ đối tác có `externalId`, `displayName` và `status`. Thiết kế mapping command allowlist, tenant scoping và policy cho status; nêu vì sao “đối tác tin cậy” không tự cấp quyền thay role.

### Bài 32 — RLS và JPA multitenancy

Database có row-level security theo tenant, ứng dụng có Hibernate tenant filter. Những code paths nào cần test thêm: native SQL, bulk DML, privileged maintenance connections, admin overrides? Phân biệt enforcement của DB với policy sửa field ở application.

### Bài 33 — Duplicate email

Hai transactions đổi email thành cùng giá trị. Pre-check cả hai pass, DB unique constraint từ chối một. Giải thích vì sao phải rollback transaction lỗi, trả conflict an toàn và giữ nguyên role/tenant.

### Bài 34 — Audit actor

Role assignment event chứa `actorId`, `tenantId` và `reason`. Những fields nào lấy từ authenticated context, những fields nào có thể là request input đã validate? Viết audit record không chứa password/token.

### Bài 35 — API thay đổi ownership

Thiết kế một workflow chuyển resource owner cần đồng ý/phê duyệt, validation cả old/new owner, quyền actor, tenant scope, audit và transaction. Giải thích vì sao generic `PATCH {"ownerId":...}` là quá rủi ro.

## 43. Câu hỏi tự kiểm tra

**1. `EntityManager.merge()` được thiết kế để làm gì?**

Hợp nhất persistent state của entity vào managed instance trong persistence context, trả về managed result. Nó không tự đánh giá authorization của client.

**2. `merge(detached)` có làm chính detached object trở thành managed không?**

Không. Managed instance là object được trả về; detached source thường vẫn detached.

**3. `merge` có tự hiểu HTTP PATCH chỉ cập nhật fields có mặt trong JSON không?**

Không. Nó xử lý persistent state, không theo dõi JSON property presence.

**4. Vì sao bỏ field khỏi JSON có thể nguy hiểm khi tạo entity mới rồi merge?**

Các fields bị bỏ có thể thành null/default ở object rồi được copy vào managed instance.

**5. Omitted JSON field và explicit null có cùng nghĩa không?**

Không bắt buộc; PATCH semantics thường phân biệt “không đổi” với “xóa giá trị”.

**6. Vì sao primitive boolean đặc biệt dễ gây lỗi?**

Không được gửi thì một new Java object có default false, dễ ghi đè giá trị true cũ.

**7. Mass assignment là gì?**

Để input bên ngoài tự điều khiển các attributes/relationships vượt danh sách field được phép, thường qua deserialization/bulk property copying.

**8. Overposting có cần attacker biết giao diện frontend không?**

Không. Client có thể tự gửi thêm JSON properties qua HTTP.

**9. Chỉ ẩn form field role ở frontend có đủ an toàn không?**

Không. Authorization và allowlist phải được enforce ở server.

**10. Một value enum ADMIN có thể hợp lệ về validation nhưng trái quyền không?**

Có. Validation kiểm tra giá trị, authorization kiểm tra quyền thực hiện.

**11. Vì sao DTO update thường an toàn hơn nhận `@Entity` trực tiếp?**

Nó giới hạn schema input ở những fields mà use case cho phép, tách client contract khỏi persistent state.

**12. DTO có tự bảo đảm authorization không?**

Không. Cần resource/action/tenant/field policy và trusted actor identity.

**13. Vì sao service nên load entity theo tenant và ID?**

Để giới hạn resource trong authorized tenant scope và có current state trước khi sửa.

**14. `findByIdAndTenantId` có đủ cho self-service profile edit không?**

Không nếu user có thể sửa tài khoản người khác trong cùng tenant; cần ownership check.

**15. IDOR/BOLA là gì trong ngữ cảnh update?**

Caller dùng ID của resource không được phép truy cập để xem/sửa đối tượng.

**16. Có nên lấy `tenantId` từ request body làm quyền truy cập không?**

Không, trừ trusted delegation được kiểm tra; thường lấy từ authenticated context.

**17. `@Column(updatable=false)` có thay authorization không?**

Không. Nó chỉ điều khiển JPA UPDATE assignments của cột ấy.

**18. `@JsonIgnore` có thay DTO allowlist không?**

Không. Nó chỉ ảnh hưởng một serialization/deserialization mechanism và không chặn những đường cập nhật khác.

**19. Không có setter `setRole` có đủ để chống mass assignment không?**

Không. Field access, reflection mapping, native SQL và các methods khác vẫn có thể sửa.

**20. `BeanUtils.copyProperties(request, entity)` nguy hiểm ở đâu?**

Có thể copy fields vượt quyền và fields mới thêm trong tương lai vào managed entity.

**21. MapStruct `ignoreByDefault=true` giúp gì?**

Chỉ map những fields được liệt kê tường minh, giảm nguy cơ thêm field không chủ đích.

**22. MapStruct mapper có biết user có quyền sửa resource nào không?**

Không. Authorization phải được service/domain kiểm tra riêng.

**23. `NullValuePropertyMappingStrategy.IGNORE` có giải quyết mọi PATCH semantics không?**

Không. Nó không tự phân biệt absent/explicit null và không chặn protected non-null fields.

**24. HTTP PUT có đồng nghĩa JPA `merge` không?**

Không. PUT là HTTP resource replacement semantics theo contract; merge là JPA persistence operation.

**25. JSON Patch có cần allowlist paths không?**

Có. Không nên cho replace `/role`, `/tenantId` hoặc fields nhạy cảm tùy ý.

**26. Vì sao command-specific DTOs có lợi?**

Tách permissions/validation/audit cho profile edit, role assignment, credit limit, email verification thay vì một generic update.

**27. Managed entity có cần `merge` sau khi gọi domain setter trong transaction không?**

Không, dirty checking có thể flush changes khi transaction hoàn tất.

**28. Dirty checking có tự biết field bị sửa trái phép không?**

Không. Mọi managed state changes có thể được ghi nếu mapping/transaction cho phép.

**29. Spring Data `save(existingEntity)` có phải authorization mechanism không?**

Không. Nó quản lý persistence theo entity new-state detection; không kiểm tra quyền.

**30. Spring Data `save` lúc nào cũng là SQL UPDATE không?**

Không. Có thể gọi persist/merge theo entity metadata, ID/version và isNew detection.

**31. `saveAndFlush` có bảo đảm commit thành công không?**

Không. Flush đồng bộ SQL trong transaction nhưng commit có thể thất bại.

**32. Cascade MERGE làm gì?**

Cho phép merge operation lan tới related entities theo mapping; không kiểm tra authorization hay child ownership.

**33. Vì sao nested JSON chứa `unitPrice` nguy hiểm?**

Nếu được copy/merge vào child entity, nó có thể thay giá bán đã chốt trái nghiệp vụ.

**34. `orphanRemoval=true` gây rủi ro gì với empty collection?**

Nếu association được cập nhật thành thiếu children, children có thể bị coi là orphan và bị xóa theo lifecycle.

**35. `orphanRemoval=false` có làm generic collection mapping an toàn không?**

Không; relationship changes ngoài ý muốn vẫn có thể xảy ra.

**36. Java `Set<Role>` có bảo vệ role assignment không?**

Không. Collection liên kết vẫn có thể bị cập nhật trái quyền trong join table.

**37. Vì sao tránh `CascadeType.ALL` với shared Role entity?**

Nó có thể đưa các lifecycle operations không phù hợp sang một entity dùng chung, đặc biệt REMOVE.

**38. `getReference(Department,id)` có kiểm tra tenant/ownership không?**

Không. Nó có thể trả proxy mà chưa load/authorize row.

**39. Foreign key có xác nhận actor được liên kết tới referenced entity không?**

Không. FK bảo vệ referential integrity, không phải per-user authorization.

**40. Domain method có thể bảo vệ những gì?**

Valid state transitions, invariants, allowed operations và consistency của entity/aggregate.

**41. `@Version` giải quyết vấn đề nào?**

Optimistic concurrency control giữa những phiên bản entity đang được cập nhật.

**42. `@Version` có chặn request sửa role trái phép không?**

Không. Request có version đúng vẫn cần authorization.

**43. Vì sao JPA `@Version` chưa đủ để phát hiện client chỉnh trên màn hình cũ?**

Service có thể load version mới khi request đến; cần expectedVersion/If-Match precondition từ client nếu muốn bảo vệ stale edits xuyên requests.

**44. Có nên copy `expectedVersion` vào entity.version không?**

Không. So sánh như precondition và để provider quản lý version field.

**45. Khi client gửi `If-Match` không khớp, HTTP status thường là gì?**

`412 Precondition Failed` theo HTTP precondition semantics.

**46. Khi API bắt buộc precondition nhưng client không gửi, có thể trả gì?**

`428 Precondition Required` nếu contract đó được áp dụng.

**47. Version/ETag có thay authentication không?**

Không. Nó không phải authorization token.

**48. Bulk JPQL UPDATE có tự chạy entity lifecycle callbacks như managed update không?**

Không theo per-entity lifecycle.

**49. Bulk JPQL UPDATE có tự increment `@Version` không?**

Không nên giả định. Query phải thể hiện version semantics có chủ đích.

**50. Vì sao kiểm tra rowcount của conditional UPDATE?**

Để biết có đúng một row thuộc scope và version mong đợi được thay đổi hay không; 0 rows có thể là stale/missing/forbidden.

**51. Bulk UPDATE có thể làm persistence context stale không?**

Có. Managed objects đã load có thể không phản ánh database changes.

**52. Validation có thể thay quyền sửa field không?**

Không. Valid syntax/data values không đảm bảo actor có quyền.

**53. Database UNIQUE có chặn user tự gán ADMIN không?**

Không, trừ khi có cơ chế authorization riêng ngoài constraint ấy.

**54. Vì sao update endpoint không nên trả entity trực tiếp?**

Nguy cơ lộ data, lazy loads, recursive serialization và API contract phụ thuộc internal model.

**55. Một lệnh bị reject có được ghi audit “update success” không?**

Không. Có thể ghi security attempted action nhưng không thành successful business event.

**56. Vì sao cần transactional outbox?**

Để đồng bộ business change và event record trong một DB transaction rồi gửi external side effect sau commit theo retry/idempotency policy.

**57. Sau persistence failure có nên tiếp tục cùng EntityManager không?**

Thông thường không; rollback affected transaction và dùng context mới theo provider/framework rules.

**58. Test chỉ kiểm tra HTTP response có đủ chứng minh protected fields không đổi không?**

Không. Cần reload database và kiểm tra associations/audit/outbox liên quan.

**59. Hai users cùng tenant có mặc định sửa profile nhau được không?**

Không. Cần ownership/action policy.

**60. Một nguyên tắc thực hành ngắn gọn nhất?**

**Không merge entity dựng từ input không đáng tin; validate DTO, load authorized managed entity, apply đúng fields/commands, kiểm tra version và commit trong transaction.**

## 44. Checklist review một endpoint cập nhật JPA

### 44.1. Input contract và mass assignment

1. Request có nhận trực tiếp `@Entity`/detached graph không? Nếu có, tại sao?
2. DTO chỉ chứa fields mà use case cho phép sửa chưa?
3. Có field nội bộ như role, tenant, owner, createdAt, creditLimit, version trong input không?
4. Unknown/forbidden JSON properties bị reject hay ignore theo contract đã định nghĩa?
5. Omitted vs explicit null có được phân biệt khi cần không?
6. Primitive defaults/empty collections có làm mất dữ liệu cũ không?
7. PUT replacement và PATCH partial semantics có rõ không?
8. Mapper có explicit allowlist (`ignoreByDefault`/domain methods) không?
9. Có dùng BeanUtils/reflection “copy all matching fields” trên managed entity không?
10. Khi entity thêm field mới, endpoint có tự mở quyền sửa field đó không?

### 44.2. Authentication, authorization và tenant

11. Actor identity/tenant được lấy từ nguồn đáng tin nào?
12. Query load có scope bằng tenant/owner theo yêu cầu không?
13. Có check same-tenant wrong-owner case không?
14. Permission gắn với **action cụ thể**, không chỉ “authenticated”?
15. Có field-specific restrictions với role/status/balance/creditLimit không?
16. Association references có được xác minh target tenant/ownership không?
17. Child IDs có được xác minh thuộc parent trong route không?
18. Cross-tenant resource errors có tránh tiết lộ sự tồn tại/metadata không?
19. Native/bulk SQL hoặc provider filters có bao phủ mọi entrypoint không?
20. Admin/system workflows có boundaries riêng và audit không?

### 44.3. JPA semantics và concurrency

21. Có tránh `merge` trên entity nhận trực tiếp từ JSON không?
22. Nếu dùng `merge` trong trusted workflow, detached graph có đủ/đúng state không?
23. Có biết managed instance do `merge` trả về khác source object không?
24. Cascade MERGE/ALL có thể ghi related entities ngoài ý muốn không?
25. `orphanRemoval`/`@ElementCollection` có thể xóa data khi collections bị thay thế không?
26. Shared many-to-many Role/Product có cascade policies phù hợp không?
27. Domain methods có kiểm tra state transitions/immutable fields không?
28. `@Version` được sử dụng cho concurrent updates cần bảo vệ không?
29. Client precondition expectedVersion/If-Match có cần để chống stale edits không?
30. Có tránh copy version trực tiếp vào managed entity không?
31. Bulk update có explicit tenant/version predicates và kiểm tra affected rows không?
32. Có tránh stale persistence context sau bulk DML không?

### 44.4. Transaction, validation và auditing

33. DTO validation và domain validation có làm đúng việc riêng?
34. DB constraints có bảo vệ integrity xuyên writers không?
35. Tất cả changes thuộc một business command có transaction atomicity phù hợp không?
36. Authorization/business exceptions có trigger rollback theo policy không?
37. Persistence failure có được rollback, không bị nuốt rồi commit tiếp không?
38. Success chỉ trả khi transaction completion thành công?
39. Email/webhook/audit external event có tránh gửi trước commit không?
40. Security/audit logs có actor/action/tenant/correlation ID mà không lộ secrets không?
41. Response DTO có giới hạn public fields không?

### 44.5. Integration tests và vận hành

42. Test overposting role/tenant/creditLimit bằng actual HTTP JSON?
43. Test omitted field giữ old state, explicit null theo contract?
44. Test cross-tenant ID, same-tenant wrong owner, child/association IDOR?
45. Test cascade MERGE/orphanRemoval không sửa/xóa related records ngoài ý muốn?
46. Test stale version và concurrent transactions với DB thật?
47. Test UPDATE rowcount, bulk DML version và persistence context stale?
48. Test database rollback và outbox/audit outcome?
49. Test response không lộ fields nhạy cảm?
50. Test cả controller và service entrypoints (batch/message/admin) nếu có?

## 45. Tổng kết

**Tránh cập nhật ngoài ý muốn khi hợp nhất entity từ dữ liệu đầu vào** là một yêu cầu bảo mật và toàn vẹn dữ liệu, không phải chỉ là mẹo dùng `EntityManager.merge()`.

Điều quan trọng nhất cần hiểu là **JPA merge quản lý trạng thái persistence, không quản lý quyền truy cập**. Nó không biết thuộc tính nào được client phép sửa, không phân biệt absent JSON field với null Java property và có thể ảnh hưởng đến entity graph theo cascade mappings. Ngay cả khi bỏ `merge()`, dùng BeanUtils copy mọi thuộc tính vào managed entity vẫn có cùng lỗ hổng.

Những nguyên tắc quan trọng:

1. **Không deserialize request trực tiếp thành entity để merge/save.** Nhận DTO/command riêng với allowlist fields tường minh.
2. **Server quyết định identity, tenant, owner và quyền.** Không tin client-provided ID/tenant/role chỉ vì payload hợp lệ.
3. **Load managed entity trong transaction theo authorized scope**, rồi áp domain methods hoặc explicit allowed fields.
4. **Phân biệt PUT, PATCH và JSON field presence.** Omitted/null/false/empty collection có ý nghĩa khác nhau; đừng để mapper quyết định ngầm.
5. **Tách commands nhạy cảm**, ví dụ assignRole, changeEmail, suspendAccount, adjustCreditLimit, chuyển quyền sở hữu, thay vì generic update.
6. **Cascade MERGE và orphanRemoval là vùng rủi ro cao** khi graph đến từ client; child/association ownership phải được xác minh.
7. **Role memberships và foreign-key relationships cũng là dữ liệu có quyền hạn.** Sửa join table có thể nguy hiểm không kém sửa role field.
8. **Optimistic locking có hai lớp khác nhau**: `@Version` bảo vệ race trong transaction, expectedVersion/If-Match bảo vệ client stale state giữa requests.
9. **Bulk UPDATE cần explicit guards**: tenant, action scope, version, affected rows; không tự có managed-entity callbacks hoặc dirty checking guarantees.
10. **Validation và DB constraints không thay authorization.** Một value hợp lệ vẫn có thể trái quyền.
11. **Commit và audit cần đồng bộ.** Không trả success hoặc phát external side effects dựa trên setter/flush nếu transaction còn có thể rollback.
12. **Test các payload đối kháng**, không chỉ happy path. Xác minh DB, join tables, collections, audit/outbox và response.

Luồng an toàn có thể ghi nhớ:

```text
                Untrusted JSON
                     |
                     v
           Request DTO / allowlist
                     |
                     v
              Validate format
                     |
                     v
       Authenticated actor + tenant
                     |
                     v
       Load managed entity in scope
                     |
                     v
       Check action/ownership policy
                     |
                     v
       Verify client version if needed
                     |
                     v
           Apply allowed fields
           through domain methods
                     |
                     v
         Dirty checking + @Version
                     |
                     v
         Flush + transaction commit
                     |
              +------+------+
              |             |
            Success       Failure
              |             |
              v             v
         Safe DTO       Rollback and
         / outbox       safe error
```

> **Quy tắc dễ nhớ:** *Client gửi ý định thay đổi, không gửi toàn bộ quyền quyết định trạng thái entity. Server phải chọn đúng tài nguyên, đúng hành động và đúng trường được phép cập nhật; JPA chỉ nên ghi những thay đổi đã vượt qua ranh giới đó.*
