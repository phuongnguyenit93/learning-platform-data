# Thuộc tính bị loại trừ và đánh dấu trường đã thay đổi trong Hibernate Envers

Hibernate Envers là mô-đun ghi nhận lịch sử thay đổi của các thực thể JPA/Hibernate. Khi một entity được đánh dấu `@Audited` và thay đổi qua **entity lifecycle** phù hợp, Envers có thể lưu một bản ghi lịch sử trong bảng audit như `customer_accounts_AUD`, gắn với một revision. Khi truy vấn quá khứ, ứng dụng có thể đọc trạng thái entity tại một thời điểm/revision trước đó mà không phải tự viết toàn bộ logic lưu snapshot.

Tuy nhiên, không phải mọi thuộc tính trong entity đều cần lịch sử; cũng không phải mọi câu hỏi kiểm toán chỉ đơn giản là “entity lúc đó có giá trị gì?”. Hai yêu cầu rất thường gặp là:

1. **Loại một số thuộc tính khỏi lịch sử:** chẳng hạn access token, dữ liệu tính toán, ghi chú kỹ thuật hoặc thông tin chỉ có giá trị hiện tại. Envers hỗ trợ `@NotAudited` và các cấu hình override audit tương ứng.
2. **Biết thuộc tính nào đã thay đổi ở từng revision:** chẳng hạn lọc những revision mà `status` hoặc `creditLimit` được sửa, không phải chỉ những revision mà một thuộc tính khác của entity thay đổi. Envers hỗ trợ **modified flags**, thường bật bằng `@Audited(withModifiedFlag = true)`.

Đây là hai quyết định độc lập:

- `@NotAudited` nghĩa là **không ghi lịch sử** cho thuộc tính được loại trừ.
- `withModifiedFlag = true` nghĩa là **ghi lịch sử của thuộc tính đã được audit và thêm metadata đánh dấu nó có thay đổi trong một revision hay không**.

Nếu hiểu nhầm, ứng dụng có thể mất bằng chứng lịch sử cần thiết, tạo schema audit quá lớn, tưởng cờ changed chứa giá trị cũ, hoặc dùng truy vấn `hasChanged()` khi cột modified flag chưa được cấu hình.

Bài học trình bày mô hình revision của Envers, cách áp dụng `@Audited` và `@NotAudited`, modified flags ở cấp entity/field/cấu hình toàn cục, câu truy vấn `hasChanged()`/`hasNotChanged()`, quan hệ và đối tượng kế thừa, migration, bảo mật, giới hạn do bulk DML, kiểm thử cùng các tình huống nghiệp vụ thực tế.

---

## 1. Envers lưu lịch sử như thế nào?

Giả sử bảng hiện hành:

```sql
CREATE TABLE customer_accounts (
    id BIGINT PRIMARY KEY,
    organization_id UUID NOT NULL,
    email VARCHAR(320) NOT NULL,
    display_name VARCHAR(200) NOT NULL,
    status VARCHAR(32) NOT NULL,
    credit_limit NUMERIC(18, 2),
    last_viewed_at TIMESTAMP WITH TIME ZONE
);
```

Một ứng dụng cần biết tài khoản đã từng được đặt trạng thái `ACTIVE`, `SUSPENDED` hoặc `CLOSED` vào revision nào.

Với Envers, những thay đổi entity được audit có thể tạo ra:

```text
customer_accounts
    id | organization_id | email | display_name | status | credit_limit
    10 | org-A           | ...   | An           | ACTIVE | 5000

REVINFO
    REV | REVTSTMP
      1 | ...
      2 | ...
      3 | ...

customer_accounts_AUD
    id | REV | REVTYPE | email | display_name | status | credit_limit | ...
    10 |  1  |    0    | ...   | An           | NEW    | 5000         | ...
    10 |  2  |    1    | ...   | An           | ACTIVE | 5000         | ...
    10 |  3  |    1    | ...   | An           | ACTIVE | 7000         | ...
```

Đây là sơ đồ khái niệm. Tên bảng/cột, kiểu dữ liệu và cách ghi revision phụ thuộc mapping, naming strategy và revision strategy.

Thông thường:

- `REV` nhận diện một revision.
- `REVTYPE` cho biết kiểu thay đổi (thêm, sửa, xóa).
- Các cột audited chứa dữ liệu được Envers dùng để tái dựng trạng thái lịch sử.
- Một revision có thể bao gồm nhiều entities thay đổi trong cùng transaction.
- Số revision không nhất thiết là số lần `setStatus()` được gọi hay số lần người dùng nhấn nút lưu.

### 1.1. Revision là gì?

Một revision là đơn vị đánh số lịch sử do Envers quản lý khi có công việc audit được ghi nhận. Thông thường, những thay đổi được audit trong cùng transaction dùng chung revision number.

Ví dụ:

```text
Transaction T1
    Customer#10.status = ACTIVE
    Customer#11.status = ACTIVE
    Commit
      |
      +-- Revision 101
            +-- Customer#10_AUD
            +-- Customer#11_AUD

Transaction T2
    Customer#10.creditLimit = 7000
    Commit
      |
      +-- Revision 102
            +-- Customer#10_AUD
```

Envers không phải event sourcing tự động: audit rows biểu diễn state/revision theo cơ chế ORM, không thay thế domain events và toàn bộ nguyên nhân nghiệp vụ của thay đổi.

### 1.2. REVTYPE và các trường changed là hai thông tin khác nhau

`REVTYPE` mô tả entity được thêm, sửa hay xóa.

Modified flags mô tả **thuộc tính nào được xem là đã thay đổi tại revision tương ứng**.

Ví dụ một row `REVTYPE = MOD` có thể có:

```text
status_MOD       = false
credit_limit_MOD = true
display_name_MOD = false
```

Nghĩa là entity có revision sửa đổi, nhưng chính `creditLimit` là thuộc tính được đánh dấu thay đổi.

## 2. Entity mẫu cho bài học

Ví dụ Spring Boot/Jakarta Persistence với Envers:

```java
import jakarta.persistence.*;
import org.hibernate.envers.Audited;
import org.hibernate.envers.NotAudited;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "customer_accounts")
@Audited
public class CustomerAccount {

    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE)
    private Long id;

    @Column(name = "organization_id", nullable = false)
    private UUID organizationId;

    @Column(nullable = false)
    private String email;

    @Column(name = "display_name", nullable = false)
    private String displayName;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private AccountStatus status;

    @Column(name = "credit_limit", precision = 18, scale = 2)
    private BigDecimal creditLimit;

    @NotAudited
    @Column(name = "last_viewed_at")
    private Instant lastViewedAt;

    protected CustomerAccount() {}

    public void rename(String newName) {
        this.displayName = newName;
    }

    public void changeStatus(AccountStatus newStatus) {
        this.status = newStatus;
    }

    public void changeCreditLimit(BigDecimal newLimit) {
        this.creditLimit = newLimit;
    }

    public void recordView(Instant at) {
        this.lastViewedAt = at;
    }
}
```

Enum:

```java
public enum AccountStatus {
    NEW, ACTIVE, SUSPENDED, CLOSED
}
```

Ở cấu hình này:

- `@Audited` trên entity yêu cầu audit những thuộc tính persistent được hỗ trợ theo mapping.
- `lastViewedAt` mang `@NotAudited` nên không được ghi như một thuộc tính lịch sử của `CustomerAccount`.
- Các thuộc tính còn lại, như `status` và `creditLimit`, được audit.
- **Chưa bật modified flags** chỉ vì entity có `@Audited`.

Muốn biết giá trị `status` tại revision 25, audit history thông thường đã đủ. Muốn dễ dàng **lọc revision mà `status` thật sự thay đổi**, nên cân nhắc modified flags.

## 3. @Audited và @NotAudited: phạm vi áp dụng

Thông thường một entity được đánh dấu:

```java
@Entity
@Audited
public class CustomerAccount {
    // ...
}
```

`@Audited` nói Envers theo dõi lịch sử của entity và những thuộc tính thuộc phạm vi audit. Nhưng có những trường không nên lưu:

```java
@NotAudited
private Instant lastViewedAt;
```

**`@NotAudited` có nghĩa “loại thuộc tính khỏi audit”, không phải “không lưu thuộc tính vào bảng hiện hành”.**

### 3.1. So sánh @NotAudited và @Transient

| Annotation | Bảng hiện hành | Bảng audit Envers | Mục đích |
|---|---|---|---|
| `@Column` thông thường trong entity `@Audited` | Lưu thuộc tính | Thường audit theo mapping | Dữ liệu persistent cần lịch sử |
| `@NotAudited` + `@Column` | Vẫn lưu | Không audit thuộc tính đó | Persistent nhưng không cần/không nên giữ lịch sử |
| `@Transient` của JPA | Không mapping persistent | Không audit như field persistent | Thuộc tính tính toán/runtime |
| `transient` Java | Không persistent theo quy tắc access phù hợp | Không audit | Trạng thái runtime không lưu |
| `@Version` | Dùng optimistic locking | Thường được loại trừ khỏi audit theo config Envers mặc định | Quản lý concurrency |

Những behavior chi tiết phụ thuộc access strategy, mapping, phiên bản và các override. Đặc biệt trường `@Version` thường bị bỏ qua bởi setting `org.hibernate.envers.do_not_audit_optimistic_locking_field` mặc định, nhưng cần đối chiếu cấu hình dự án.

### 3.2. Ví dụ trường persistent nhưng không audit

```java
@Audited
@Entity
public class ApiClient {

    @Id
    private UUID id;

    @Column(nullable = false)
    private String displayName;

    @NotAudited
    @Column(name = "last_used_at")
    private Instant lastUsedAt;
}
```

Nếu `lastUsedAt` thay đổi liên tục nhưng người dùng chỉ cần lịch sử tên hiển thị, không ghi timestamp này vào audit giúp:

- Giảm dữ liệu lịch sử không cần thiết.
- Tránh mang một field có nhịp thay đổi cao vào các snapshot audit.
- Đơn giản hóa các câu hỏi “thay đổi nghiệp vụ” nếu field này không mang ý nghĩa kiểm toán.

Tuy nhiên, nếu yêu cầu an ninh cần lịch sử hoạt động của API client, loại `lastUsedAt` khỏi Envers không tự tạo audit thay thế; cần một cơ chế access log/security event riêng.

## 4. Thuộc tính bị loại trừ ảnh hưởng những gì?

Giả sử:

```java
CustomerAccount c = em.find(CustomerAccount.class, id);
c.recordView(Instant.now());
```

Khi Hibernate flush thay đổi persistent `lastViewedAt`:

- Bảng `customer_accounts` có thể được UPDATE.
- `lastViewedAt` không được lưu thành cột lịch sử trong `customer_accounts_AUD`.
- Một thay đổi **chỉ gồm thuộc tính không audit** thường không có ý nghĩa tạo revision audit mới cho entity nếu Envers không có dữ liệu audited khác thay đổi; hành vi cụ thể cần kiểm chứng theo mapping, dirty tracking và phiên bản.
- Nếu cùng transaction cũng đổi `status`, Envers ghi revision cho `status`; bản thân `lastViewedAt` vẫn không trở thành một phần snapshot lịch sử.

### 4.1. @NotAudited không bảo đảm loại mọi dấu vết trong hệ thống

Nếu một thuộc tính nhạy cảm bị loại khỏi Envers, dữ liệu có thể vẫn nằm ở:

- Bảng hiện hành.
- Backup/snapshot database.
- SQL/parameter logs nếu bật logging thiếu kiểm soát.
- Change data capture.
- Application log.
- Outbox/event payload.
- Revision history cũ từ trước khi thay đổi annotation.

Vì vậy `@NotAudited` chỉ điều chỉnh cơ chế audit Envers cho mapping đó, không phải chính sách xóa sạch dữ liệu nhạy cảm.

### 4.2. Đọc entity lịch sử không có giá trị field bị loại

Ví dụ:

```java
CustomerAccount historical =
    auditReader.find(CustomerAccount.class, id, revision);
```

Nếu `lastViewedAt` không được audit, **đừng dựa vào historical.getLastViewedAt() như giá trị tại revision**. Field này không có dữ liệu lịch sử để Envers tái dựng; với kiểu và mapping cụ thể, giá trị quan sát có thể là null/default hoặc không được tái tạo theo ý định nghiệp vụ.

Nếu UI lịch sử cần trường đó, quyết định loại trừ có thể không phù hợp.

### 4.3. Không suy luận lý do thay đổi từ một snapshot đơn lẻ

Một row audit có thể cho thấy status đã chuyển thành ACTIVE, nhưng không tự cho biết “admin nào” hoặc “vì sao”. Muốn thông tin người thực hiện, có thể mở rộng revision entity với actor/tenant/correlation metadata theo chính sách; muốn lý do nghiệp vụ có thể ghi audit event/outbox rõ.

## 5. Chọn thuộc tính nào nên loại khỏi audit

Không có một danh sách tuyệt đối; quyết định xuất phát từ mục tiêu lịch sử và chính sách lưu trữ.

Những ứng viên thường cần xem xét:

| Nhóm thuộc tính | Ví dụ | Lý do cân nhắc không audit |
|---|---|---|
| Runtime/diagnostic | `lastViewedAt`, `lastPolledAt` | Thay đổi thường xuyên, ít giá trị lịch sử domain |
| Dữ liệu cache | `cachedSummary` | Có thể tính lại, không phải nguồn dữ liệu thật |
| Dữ liệu nhạy cảm | `apiKeyHash`, `resetToken` | Không muốn giữ bản cũ lâu dài |
| Dữ liệu kỹ thuật | `lastSyncAttemptAt` | Có thể phù hợp hơn với operational logs |
| Quan hệ tạm thời | Temporary assignment | Lịch sử có thể không cần thiết |
| Payload lớn | Large text/blob | Audit size có thể tăng nhanh, cần retention riêng |

**Cảnh báo:** các ví dụ như `apiKeyHash` có thể thuộc yêu cầu bảo mật/audit đặc thù. Không nên mặc định loại mọi trường nhạy cảm hay giữ mọi trường nhạy cảm. Cần threat model, yêu cầu pháp lý, khả năng điều tra và chính sách retention.

### 5.1. Dữ liệu computed có thể không cần mapping

Nếu một giá trị có thể tính từ những thuộc tính khác và không được lưu, dùng Java getter hoặc `@Transient` thay vì thêm cột persistent rồi `@NotAudited`.

### 5.2. Dữ liệu lớn có thể yêu cầu cơ chế riêng

Một tài liệu có `byte[] attachmentContent` lớn không nên mặc định audit toàn bộ blob ở mỗi revision. Có thể lưu versioned object reference (hash/object storage key) thay vì copy payload vào Envers; cần thiết kế tính bất biến và khả năng truy xuất lịch sử của object storage.

### 5.3. Thuộc tính mang invariant quan trọng nên cân nhắc audit

`status`, `ownerId`, `creditLimit`, `approvalState` hoặc các thuộc tính liên quan tài chính/quyền thường cần lịch sử để kiểm tra hành trình nghiệp vụ. Loại chúng chỉ để giảm số cột audit có thể làm mất thông tin cần thiết cho hỗ trợ vận hành và tuân thủ.

## 6. Ví dụ SQL schema khi loại một field

Mapping:

```java
@Entity
@Audited
@Table(name = "customer_accounts")
public class CustomerAccount {

    @Id
    private Long id;

    @Column(nullable = false)
    private String displayName;

    @NotAudited
    private Instant lastViewedAt;

    private String status;
}
```

Bảng hiện hành có thể gồm:

```text
customer_accounts
-----------------
id
display_name
last_viewed_at
status
```

Bảng audit:

```text
customer_accounts_AUD
---------------------
id
REV
REVTYPE
display_name
status

-- Không có last_viewed_at dưới cơ chế @NotAudited
```

Tùy naming strategy, cột audit không nhất thiết viết đúng như field Java. Trong production nên quản lý schema bằng migration (Flyway/Liquibase hoặc tương đương) và kiểm chứng DDL thực tế thay vì suy luận toàn bộ tên cột từ ví dụ.

## 7. Modified flags giải quyết bài toán gì?

Giả sử revision history cho Customer#10:

| Revision | displayName | status | creditLimit |
|---:|---|---|---:|
| 21 | An | NEW | 5.000 |
| 22 | An | ACTIVE | 5.000 |
| 23 | An Nguyễn | ACTIVE | 5.000 |
| 24 | An Nguyễn | ACTIVE | 7.000 |

Nếu chỉ cần trạng thái tại revision 23, Envers đọc snapshot được.

Nếu muốn trả lời **“Những revision nào đổi status?”**, có thể so sánh snapshot giữa các revision. Nhưng:

- Cần lấy nhiều revision để đối chiếu.
- Có thể nhiều thuộc tính và rất nhiều entities.
- Phải tính đến thêm/xóa entity, quan hệ, null và custom types.
- Truy vấn lịch sử trở nên khó tối ưu.

**Modified flags** là cột metadata được Envers ghi cùng audit row cho từng thuộc tính được bật, thường là kiểu boolean.

Ví dụ:

```text
customer_accounts_AUD
----------------------------------------------------------------
id | REV | REVTYPE | display_name | status | credit_limit
   | DISPLAY_NAME_MOD | STATUS_MOD | CREDIT_LIMIT_MOD
----------------------------------------------------------------
10 | 22  | MOD     | An           | ACTIVE | 5000
   | false            | true       | false

10 | 23  | MOD     | An Nguyễn    | ACTIVE | 5000
   | true             | false      | false

10 | 24  | MOD     | An Nguyễn    | ACTIVE | 7000
   | false            | false      | true
```

Nhờ vậy, một query history có thể lọc `status` changed mà không cần tự đối chiếu từng row trong Java.

### 7.1. Cờ changed là metadata của revision

`STATUS_MOD = true` được hiểu trong ngữ cảnh audit row/revision: Envers ghi nhận `status` thay đổi ở revision đó theo change-tracking/mapping của Envers.

Nó **không** có nghĩa:

- Status hiện tại khác giá trị mặc định.
- Status đổi ngay trước khi người dùng mở trang.
- Có một câu SQL UPDATE riêng chỉ dành cho status.
- Setter `setStatus()` đã được gọi ít nhất một lần.
- User đã nhìn thấy bản ghi đó.
- Database row cuối cùng đã commit nếu transaction thực tế rollback.

### 7.2. Envers không phải source-level assignment tracker

Một method Java có thể gọi setter nhiều lần trong một transaction:

```java
account.changeStatus(AccountStatus.SUSPENDED);
account.changeStatus(AccountStatus.ACTIVE);
```

Nếu giá trị cuối cùng bằng giá trị cũ tại thời điểm flush, ORM có thể không sinh một audited modification cho status. Modified flags phản ánh semantics của Envers và dirty checking, **không đếm mọi lần setter được gọi**.

## 8. Bật modified flags ở cấp entity

Cách phổ biến:

```java
import org.hibernate.envers.Audited;

@Entity
@Audited(withModifiedFlag = true)
public class CustomerAccount {

    @Id
    private Long id;

    private String displayName;

    private String status;

    private BigDecimal creditLimit;

    @NotAudited
    private Instant lastViewedAt;
}
```

Với cấu hình này, Envers thường tạo các cột modified flag cho các thuộc tính audited được hỗ trợ, chẳng hạn:

```text
displayName_MOD
status_MOD
creditLimit_MOD
```

Tên cột thực tế có thể qua naming strategy và mặc định `_MOD` hoặc cấu hình suffix; **không suy luận modified flag cho `lastViewedAt`** vì field đã bị loại khỏi audit.

### 8.1. Lợi thế

- Không cần đặt annotation trên từng audited property.
- Có thể dùng `hasChanged()` cho nhiều thuộc tính thường được truy vấn.
- Chuẩn hóa convention cho toàn entity.

### 8.2. Chi phí

- Tăng số cột trong mỗi audit table.
- Tăng dữ liệu ghi và storage.
- Khi có nhiều thuộc tính, audit schema và migration lớn hơn.
- Có thể cần chỉ số (index) và tối ưu queries theo workload.
- Những thay đổi naming/suffix về sau đòi migration.

Không nên bật flags toàn bộ hệ thống chỉ vì “thêm vài cột boolean không đáng kể” khi có hàng trăm entities và rất nhiều audited fields.

## 9. Bật modified flag chỉ cho một số thuộc tính

Nếu chỉ `status` và `creditLimit` cần truy vấn change history, có thể để entity được audit bình thường rồi dùng `@Audited(withModifiedFlag = true)` ở những thuộc tính cần cờ.

Ví dụ:

```java
@Entity
@Audited
public class CustomerAccount {

    @Id
    private Long id;

    private String displayName;

    @Audited(withModifiedFlag = true)
    private AccountStatus status;

    @Audited(withModifiedFlag = true)
    private BigDecimal creditLimit;

    @NotAudited
    private Instant lastViewedAt;
}
```

Ý định:

- `displayName` được audit nhưng không bắt buộc có cột modified flag.
- `status` và `creditLimit` được audit và có cờ changed.
- `lastViewedAt` không audit, không có modified flag.

Đối chiếu phiên bản/mapping cụ thể nếu có cả annotation cấp class và cấp field với giá trị `withModifiedFlag` khác nhau, bởi effective mapping/override cần được kiểm tra trên DDL thực tế.

### 9.1. Vì sao nên chọn theo câu hỏi nghiệp vụ?

Ví dụ:

- CSKH thường hỏi “khi nào status đổi?” → flag cho status.
- Quản lý tín dụng hỏi “khi nào credit limit đổi?” → flag cho creditLimit.
- Ít ai cần query “tất cả revision mà displayName đổi” → có thể chưa cần flag.

Đây là cách giảm chi phí mà vẫn đáp ứng truy vấn lịch sử quan trọng.

### 9.2. Không thể bật flag cho field bị @NotAudited để lấy lịch sử

Ví dụ ý tưởng sai:

```java
@NotAudited
@Audited(withModifiedFlag = true)
private String secret;
```

Hai annotation có ý định xung đột: một annotation loại field khỏi audit, annotation kia yêu cầu audit/change flag. Không dùng đồng thời làm thủ thuật “chỉ lưu boolean changed nhưng không lưu giá trị” rồi mặc định Envers hỗ trợ như mong muốn.

Nếu cần biết **secret đã được rotate** nhưng không lưu secret cũ, thiết kế một thuộc tính audit-safe khác như `secretRotationAt`, `secretVersion` hoặc domain event `SecretRotated` và đánh dấu/audit thuộc tính/event đó. Không buộc Envers lưu lịch sử giá trị secret để có bằng chứng thay đổi.

## 10. Bật modified flags ở phạm vi cấu hình

Envers có property để bật modified flags rộng hơn:

```properties
org.hibernate.envers.global_with_modified_flag=true
```

Trong Spring Boot, Hibernate property có thể được chuyển qua:

```properties
spring.jpa.properties.org.hibernate.envers.global_with_modified_flag=true
```

Khi bật globally, Envers có thể tạo flags cho các audited properties trên nhiều audited entities theo effective mapping của version đó.

### 10.1. Cấu hình toàn cục không loại bỏ nhu cầu xem schema

Nếu hệ thống có:

- 120 audited entities.
- Mỗi entity trung bình 25 audited properties.

thì có thể phải quản lý hàng nghìn modified-flag columns trên các audit tables. Đây chỉ là ước lượng minh họa, nhưng đủ cho thấy cần đánh giá chi phí trước khi bật global setting.

### 10.2. Không áp toàn cục khi chỉ vài report cần

Nếu một report chỉ lọc changes của `Invoice.status`, có thể bật flag ở đúng field đó thay vì tất cả fields của mọi entity.

### 10.3. Thay đổi property trong ứng dụng hiện hữu

Nếu bảng audit đã tồn tại, đổi cấu hình Java/property **không đảm bảo database tự có cột flags**. Với `ddl-auto=validate` hoặc schema migration do Flyway/Liquibase quản lý, ứng dụng có thể lỗi startup hoặc SQL INSERT khi thiếu cột.

Cần migration tương ứng trước khi deploy code cần ghi flags.

## 11. Đặt tên modified-flag column

Envers hỗ trợ suffix cấu hình cho các cột modified flags. Property thông dụng:

```properties
org.hibernate.envers.modified_flag_suffix=_MOD
```

Đây là cách biểu đạt convention thường gặp: cột dữ liệu `status` có thêm `status_MOD`. Naming strategy có thể thay đổi chữ hoa/chữ thường và tên vật lý.

### 11.1. Đặt tên riêng cho field

`@Audited` có khả năng cấu hình `modifiedColumnName` theo phiên bản Envers hỗ trợ:

```java
@Audited(
    withModifiedFlag = true,
    modifiedColumnName = "status_changed"
)
@Enumerated(EnumType.STRING)
private AccountStatus status;
```

Đây là ví dụ khi ứng dụng muốn audit column name rõ hơn convention `status_MOD`.

### 11.2. Khi nào cần custom name?

- Schema audit đã có convention riêng.
- DB giới hạn chiều dài identifier.
- Thuộc tính lồng/embedded gây tên dài.
- Muốn báo cáo SQL đọc dễ hơn.
- Cần tránh collision với một cột đã tồn tại.

### 11.3. Không đổi suffix tùy tiện sau khi có dữ liệu

Đổi `_MOD` thành `_CHANGED` có thể khiến Envers mapping tìm những cột khác với schema đã có. Cần:

1. Xác định tất cả audit tables bị ảnh hưởng.
2. Tạo migration rename/add columns.
3. Quyết định giá trị flags lịch sử.
4. Deploy theo compatibility plan.
5. Kiểm chứng queries `hasChanged()` vẫn hợp lệ.

Một thay đổi tên cột metadata không phải cosmetic trong hệ thống đã có lịch sử.

## 12. Query các revision bằng AuditReader

Envers cung cấp `AuditReader`, thường lấy từ `AuditReaderFactory`:

```java
import jakarta.persistence.EntityManager;
import org.hibernate.envers.AuditReader;
import org.hibernate.envers.AuditReaderFactory;

AuditReader reader = AuditReaderFactory.get(entityManager);
```

Đọc entity tại revision:

```java
CustomerAccount historic = reader.find(
    CustomerAccount.class,
    customerId,
    revisionNumber
);
```

Tìm danh sách revisions có entity change:

```java
List<Number> revisions = reader.getRevisions(
    CustomerAccount.class,
    customerId
);
```

### 12.1. getRevisions không tự cho biết field nào đổi

`reader.getRevisions(...)` trả revision numbers cho audited entity, không phải map trường changed.

Có thể đọc từng revision và so sánh snapshot thủ công, nhưng nếu câu hỏi thường xuyên là “revision nào đổi status”, modified flags và Envers AuditQuery phù hợp hơn.

### 12.2. Revision number khác timestamp

`REV` là số revision theo generator; timestamp lấy qua revision metadata và không nhất thiết cho phép suy luận “mọi thay đổi theo từng giây” bằng cách cộng/trừ revision.

Dùng Envers API để truy vấn revision/timestamp thay vì đoán khoảng thời gian từ giá trị số.

## 13. AuditEntity.property(...).hasChanged()

Khi `status` có modified flag hợp lệ, có thể query những revision mà trường này được đánh dấu thay đổi:

```java
import org.hibernate.envers.AuditReader;
import org.hibernate.envers.AuditReaderFactory;
import org.hibernate.envers.query.AuditEntity;

AuditReader reader = AuditReaderFactory.get(em);

@SuppressWarnings("unchecked")
List<Object[]> history = reader.createQuery()
    .forRevisionsOfEntity(
        CustomerAccount.class,
        false,
        true
    )
    .add(AuditEntity.id().eq(customerId))
    .add(AuditEntity.property("status").hasChanged())
    .addOrder(AuditEntity.revisionNumber().asc())
    .getResultList();
```

Giải thích:

- `forRevisionsOfEntity(CustomerAccount.class, false, true)` yêu cầu kết quả dạng revision history có metadata thay vì chỉ entity; tham số thứ ba cho phép xét cả deleted revisions theo API tương ứng.
- `AuditEntity.id().eq(customerId)` lọc một entity.
- `AuditEntity.property("status").hasChanged()` sử dụng modified flag của `status`.
- `addOrder(...asc())` sắp revision number.
- Kết quả dạng `Object[]` thường chứa historical entity, revision entity và `RevisionType` trong cấu hình API ba-phần-tử; cần kiểm tra shape theo method/phiên bản thực tế.

### 13.1. Vì sao không dùng WHERE status = 'ACTIVE' để thay hasChanged?

Query:

```java
.add(AuditEntity.property("status").eq(AccountStatus.ACTIVE))
```

lọc những audit snapshots có **giá trị status ACTIVE**. Nhưng nhiều revisions có thể mang status ACTIVE, dù revision đó chỉ sửa `displayName` hoặc `creditLimit`.

Ngược lại:

```java
.add(AuditEntity.property("status").hasChanged())
```

lọc những revisions mà **flag changed của status** được ghi là true.

Hai câu hỏi khác nhau:

- “Entity đang có trạng thái nào ở revision R?” → lọc snapshot value.
- “Status có bị đổi tại revision R không?” → modified flag.

### 13.2. Thêm điều kiện giá trị mới

Nếu muốn những revisions mà status đổi **sang ACTIVE**:

```java
.add(AuditEntity.property("status").hasChanged())
.add(AuditEntity.property("status").eq(AccountStatus.ACTIVE))
```

Đây là intersection của hai điều kiện: field changed và giá trị snapshot bằng ACTIVE.

Tùy dữ liệu/hành vi trên `ADD` và `DEL`, có thể cần thêm `AuditEntity.revisionType()` để chỉ tính sửa đổi.

## 14. hasNotChanged(): trường không thay đổi trong một revision

Nếu modified flag có mặt, Envers cũng hỗ trợ predicate `hasNotChanged()`:

```java
List<?> rows = reader.createQuery()
    .forRevisionsOfEntity(
        CustomerAccount.class,
        false,
        false
    )
    .add(AuditEntity.id().eq(customerId))
    .add(AuditEntity.property("status").hasNotChanged())
    .getResultList();
```

Nghĩa là trong những audited revisions được xét, `status` **không được đánh dấu thay đổi**.

### 14.1. hasNotChanged không trả mọi transaction không sửa status

Giả sử có 10.000 transactions trong hệ thống, nhưng Customer#10 chỉ có 3 audit revisions. `hasNotChanged()` xét **các audit rows của Customer#10**, không tự tạo row cho mọi transaction mà Customer#10 không được đụng đến.

Nếu không có audit row ở revision 500, query không thể “trả revision 500 với status not changed” như một sự kiện của entity đó.

### 14.2. Phân biệt “không đổi” và “chưa từng được đánh giá”

Cờ false nói về audited row cụ thể; nó không phải kết luận rằng nghiệp vụ không gọi setter, không đọc entity hay không thực hiện một command sau cùng rollback.

### 14.3. Khi nào hasNotChanged hữu ích?

- Tìm revision đổi `creditLimit` nhưng giữ nguyên `status`.
- So sánh các nhóm thay đổi để phân loại update.
- Kiểm tra một quy tắc “chỉ các field tài chính được thay đổi trong revision này”.

Ví dụ:

```java
.add(AuditEntity.property("creditLimit").hasChanged())
.add(AuditEntity.property("status").hasNotChanged())
```

Query này dùng hai flag; nếu một field chưa bật modified flag, query tương ứng có thể không được hỗ trợ hoặc lỗi, tùy mapping/version.

## 15. Phân biệt ADD, MOD và DEL khi đọc flags

Envers có `RevisionType` phổ biến:

```java
import org.hibernate.envers.RevisionType;

RevisionType.ADD;
RevisionType.MOD;
RevisionType.DEL;
```

Thông thường database lưu một cột tương ứng như `REVTYPE`, với giá trị có thể biểu diễn thành số 0/1/2 theo mapping phổ biến.

### 15.1. Revision ADD

Khi entity được tạo, các audited properties xuất hiện lần đầu. Modified flags trên ADD có thể được đánh dấu theo semantics Envers về entity mới (thường được hiểu như các thuộc tính được đưa vào lịch sử), **không nên diễn giải là property vừa thay đổi so với một snapshot entity đã tồn tại**.

Nếu report chỉ muốn “thay đổi status trên entity đã tồn tại”, lọc `RevisionType.MOD`:

```java
.add(AuditEntity.revisionType().eq(RevisionType.MOD))
.add(AuditEntity.property("status").hasChanged())
```

### 15.2. Revision MOD

Đây là trường hợp điển hình để hiểu cờ `status_MOD` true/false với audited changes của entity đã tồn tại.

### 15.3. Revision DEL

Theo cấu hình Envers phổ biến, row DEL có thể chỉ giữ ID/revision metadata trong khi các dữ liệu khác để null, trừ khi dùng setting lưu dữ liệu khi xóa (ví dụ `store_data_at_delete` ở version hỗ trợ).

Vì vậy:

- Không suy luận values hoặc flags của row DEL giống MOD.
- Kiểm tra dữ liệu/DDL/hành vi theo revision strategy và setting cụ thể.
- Trong report “field nào đổi”, có thể lọc MOD riêng để tránh nhập nhằng deletion.

### 15.4. Một transaction sửa nhiều field

Nếu transaction đổi cả `status` và `creditLimit`, một audit row MOD có thể có:

```text
STATUS_MOD       = true
CREDIT_LIMIT_MOD = true
DISPLAY_NAME_MOD = false
```

Cùng một revision có thể chứa nhiều flags true; không có bảo đảm “một revision chỉ một field changed”.

## 16. Modified flag không lưu giá trị cũ

Giả sử:

```text
Revision 18: status = NEW
Revision 19: status = ACTIVE, STATUS_MOD = true
```

Cờ `STATUS_MOD = true` nói status changed tại revision 19, **không chứa trực tiếp giá trị NEW**.

Muốn hiển thị:

```text
18 -> 19: NEW -> ACTIVE
```

cần lấy dữ liệu từ hai snapshots thích hợp:

1. Historical entity at revision 19 (giá trị mới).
2. Historical state từ revision trước đó của entity (giá trị cũ).
3. So sánh field với chính sách null và mapping.

### 16.1. Revision trước đó là revision của entity, không nhất thiết REV - 1

Ví dụ Customer#10 có revisions `[3, 9, 27]`.

Muốn old state tại revision 27, previous audited revision của Customer#10 là 9, không phải 26.

Không gọi `reader.find(Customer.class, id, revision - 1)` rồi giả định nó là row audit ngay trước đó; Envers có thể trả state tại thời điểm tương ứng, nhưng nếu cần liệt kê change events thì phải xác định previous revision của entity đúng.

### 16.2. Không thể truy ra giá trị cũ của @NotAudited field từ Envers

Nếu `secret` không được audit, modified flag của field audit-safe khác có thể cho biết có sự kiện rotate, nhưng không tự khôi phục secret trước đó. Đây thường chính là điều mong muốn về bảo mật.

## 17. Ví dụ báo cáo lịch sử thay đổi status

Một service xây DTO:

```java
public record StatusChangeRow(
    Number revision,
    AccountStatus status,
    RevisionType revisionType
) {}
```

Code minh họa:

```java
@Transactional(readOnly = true)
public List<StatusChangeRow> listStatusChanges(
        Long accountId) {

    AuditReader reader = AuditReaderFactory.get(em);

    @SuppressWarnings("unchecked")
    List<Object[]> rows = reader.createQuery()
        .forRevisionsOfEntity(
            CustomerAccount.class,
            false,
            false
        )
        .add(AuditEntity.id().eq(accountId))
        .add(AuditEntity.revisionType().eq(RevisionType.MOD))
        .add(AuditEntity.property("status").hasChanged())
        .addOrder(AuditEntity.revisionNumber().asc())
        .getResultList();

    return rows.stream()
        .map(tuple -> {
            CustomerAccount state =
                (CustomerAccount) tuple[0];

            Object revisionEntity = tuple[1];
            RevisionType type =
                (RevisionType) tuple[2];

            Number rev = extractRevisionNumber(revisionEntity);

            return new StatusChangeRow(
                rev,
                state.getStatus(),
                type
            );
        })
        .toList();
}
```

`extractRevisionNumber(...)` là helper ứng dụng; cách lấy revision ID phụ thuộc revision entity class của dự án (default/custom). Code chỉ minh họa shape của query API thông thường và yêu cầu bổ sung getters/imports phù hợp.

### 17.1. Không hardcode cast revision entity thành Long

Khi `forRevisionsOfEntity(..., false, ...)` trả metadata, thành phần thứ hai thường là **revision entity object**, không nhất thiết chính là Number. Nếu dùng custom revision entity chứa actor và timestamp, cần cast theo class tương ứng rồi đọc ID.

### 17.2. Authorization của audit history

Một report lịch sử có thể chứa PII hoặc giá trị trước khi bị hạn chế quyền. Dù entity hiện tại chỉ hiển thị một số trường, audit rows có thể tiết lộ giá trị cũ.

Kiểm tra:

- Tenant/resource authorization trước khi query.
- Quyền `VIEW_HISTORY` có khác quyền `VIEW_CURRENT` không.
- Redaction và retention của audit data.
- Không expose toàn bộ object lịch sử qua JSON tùy tiện.

Envers không tự định nghĩa ACL cho audit history.

## 18. Vì sao hasChanged có thể không chạy khi chưa bật flags?

Giả sử entity:

```java
@Entity
@Audited
public class Invoice {

    @Id
    private Long id;

    private String status;
}
```

Bạn viết:

```java
reader.createQuery()
    .forRevisionsOfEntity(Invoice.class, false, true)
    .add(AuditEntity.property("status").hasChanged())
    .getResultList();
```

Nếu modified flag cho `status` không được cấu hình/mapped, Envers không có cột metadata cần thiết để lọc như yêu cầu. Tùy version có thể ném exception khi xây/thực thi audit query.

**Không thể bổ sung `hasChanged()` ở Java query rồi mặc định Envers sẽ tự so sánh mọi bản ghi lịch sử để tìm field changed.**

### 18.1. Bật flags là thay đổi cả mapping và schema

Thêm:

```java
@Audited(withModifiedFlag = true)
private String status;
```

có thể đòi migration để thêm `status_MOD` vào `invoice_AUD`.

### 18.2. Không quên dữ liệu lịch sử trước migration

Giả sử có các audit rows từ trước khi modified flag tồn tại. Thêm column:

```sql
ALTER TABLE invoice_AUD
ADD COLUMN status_MOD BOOLEAN;
```

có thể để các rows cũ có `NULL`. Query `hasChanged()` trên dữ liệu cũ sẽ không tự có câu trả lời đúng vì metadata chưa từng được ghi.

Các lựa chọn:

- Chấp nhận chỉ hỗ trợ modified flags cho revisions mới và ghi rõ mốc hiệu lực.
- Backfill flags bằng quy trình so sánh lịch sử theo từng entity, revision và dữ liệu cũ nếu khả thi.
- Mở report riêng với semantics “unknown before revision X”.
- Giới hạn truy vấn ở giai đoạn sau migration.

Không tự set tất cả flags của rows cũ thành `false` nếu chưa chứng minh chúng không thay đổi; làm vậy có thể tạo lịch sử sai.

## 19. Migration khi bắt đầu dùng modified flags

Một quy trình thiết kế phù hợp:

### 19.1. Khảo sát schema và query thực tế

- Entity nào có `@Audited`?
- Audit table nào đã tồn tại?
- Những fields nào sẽ bật `withModifiedFlag`?
- Audit rows bao nhiêu? Retention thế nào?
- Có tool/report cũ phụ thuộc audit table columns không?
- Có naming strategy custom hoặc quoted names không?

### 19.2. Xác định schema đích

Ví dụ:

```sql
ALTER TABLE customer_accounts_AUD
ADD COLUMN status_MOD BOOLEAN;

ALTER TABLE customer_accounts_AUD
ADD COLUMN credit_limit_MOD BOOLEAN;
```

Đây là SQL minh họa, cần chỉnh kiểu dữ liệu/tên cột theo database/dialect/schema thật.

### 19.3. Quyết định dữ liệu cũ

Nếu chưa backfill, giá trị NULL nên được xem là “chưa có thông tin changed flag”, không phải “false”.

Nếu backfill, cần quy trình đối chiếu các audited snapshots theo đúng revision thứ tự, xét ADD/MOD/DEL, null, custom types và quan hệ. Với lượng dữ liệu lớn, nên chạy migration chunked và kiểm thử hiệu năng.

### 19.4. Lập kế hoạch deploy

Nếu application code bắt đầu INSERT vào cột `status_MOD` trước khi migration được áp, có thể lỗi SQL.

Một kế hoạch rollout thường gồm:

1. Thêm audit flag columns tương thích trước.
2. Deploy code bật flags.
3. Xác nhận new audit rows ghi flags đúng.
4. Cập nhật report/query hasChanged.
5. Backfill hoặc công bố giới hạn lịch sử nếu cần.
6. Chạy monitoring/schema validation.

### 19.5. Không mặc định Hibernate ddl-auto=update là migration strategy

Trong production, đổi Envers metadata nên có schema migration được quản lý, có rollback plan, backup và kiểm tra dữ liệu. Hibernate schema update tự động có thể không xử lý backfill, index, column rename hoặc compatibility giữa deployments.

## 20. Đổi từ audited sang @NotAudited sau khi hệ thống đã chạy

Giả sử trước đây `apiKeyHash` được audit, giờ quyết định không lưu nữa:

```java
@NotAudited
@Column(name = "api_key_hash")
private String apiKeyHash;
```

Hệ quả:

- Các revision mới không ghi thuộc tính này theo mapping mới.
- Cột cũ trong audit table có thể vẫn tồn tại.
- **Giá trị lịch sử cũ không tự bị xóa**.
- Báo cáo đọc lịch sử qua mapping mới có thể không trả trường cũ, nhưng database vẫn giữ dữ liệu.
- Backup và replicas cũng có thể còn thông tin cũ.

### 20.1. Vấn đề bảo mật dữ liệu cũ

Nếu mục tiêu loại field vì retention/privacy, việc thêm `@NotAudited` chỉ ngăn lưu mới. Muốn xóa quá khứ cần một chương trình remediation gồm:

- Dữ liệu nào là nhạy cảm?
- Cần xóa/anonymize ở bảng audit, backup, replicas, logs hay export?
- Có ràng buộc pháp lý phải giữ hay phải xóa?
- Có trigger/index/constraints ảnh hưởng không?
- Revision consistency được bảo vệ thế nào?

Không chạy SQL `DELETE FROM ..._AUD` tùy tiện để “dọn sạch một trường” mà làm hỏng audit history, referential integrity hoặc requirements tuân thủ.

### 20.2. Đừng đổi field sang @Transient chỉ để ngăn audit

Nếu field vẫn cần lưu ở bảng hiện hành, `@Transient` làm nó không còn persistent theo JPA. Đó là thay đổi business data mapping lớn hơn nhiều so với `@NotAudited`.

## 21. Kế thừa thuộc tính: @AuditOverride

Trong hệ thống có `@MappedSuperclass`, một số thuộc tính được kế thừa bởi nhiều entities. Ví dụ:

```java
@MappedSuperclass
public abstract class OperationalMetadata {

    @Column(name = "created_by")
    private String createdBy;

    @Column(name = "last_sync_attempt_at")
    private Instant lastSyncAttemptAt;
}
```

Một entity có thể muốn audit `createdBy` nhưng không audit `lastSyncAttemptAt`.

Envers hỗ trợ `@AuditOverride` / `@AuditOverrides` cho một số trường hợp override thuộc tính kế thừa hoặc component theo mapping/version.

Ví dụ ý định:

```java
import org.hibernate.envers.AuditOverride;
import org.hibernate.envers.Audited;

@Entity
@Audited
@AuditOverride(
    forClass = OperationalMetadata.class,
    name = "lastSyncAttemptAt",
    isAudited = false
)
public class Invoice extends OperationalMetadata {

    @Id
    private Long id;

    private String status;
}
```

### 21.1. Khi nào dùng @AuditOverride?

- Một base class được chia sẻ nhưng mỗi entity có chính sách audit khác nhau.
- Một embeddable chứa nhiều fields, entity cụ thể chỉ cần audit một phần.
- Không thể đặt `@NotAudited` trực tiếp trên base field vì sẽ ảnh hưởng các entities khác.

### 21.2. Đừng dùng override để thay kiến trúc bảo mật

Một override chỉ điều chỉnh mapping audit. Nếu một field mang dữ liệu nhạy cảm cần policy retention toàn hệ thống, nên định nghĩa quy ước chung thay vì mỗi entity tùy ý bật/tắt mà không kiểm soát.

### 21.3. Kiểm tra vị trí annotation

JPA có field access/property access. Hibernate Envers metadata theo mapping. Một override sai tên Java property hoặc đặt annotation lệch access strategy có thể không mang ý nghĩa mong đợi. Kiểm chứng DDL/behavior trên phiên bản thực tế.

## 22. Quan hệ entity: không audit association khác với không audit target

Giả sử `Invoice` tham chiếu `Currency`:

```java
@Entity
@Audited
public class Invoice {

    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    private Currency currency;
}
```

Có hai câu hỏi khác nhau:

1. Có cần lưu lịch sử **invoice trỏ đến currency nào**?
2. Có cần lưu lịch sử **các thuộc tính bên trong Currency**?

### 22.1. @NotAudited trên association

```java
@NotAudited
@ManyToOne(fetch = FetchType.LAZY)
private Currency currency;
```

Ý định: association này không nằm trong lịch sử audit của Invoice. Truy vấn Invoice ở revision cũ không thể mặc định cho biết Currency đã được gắn vào lúc đó.

### 22.2. Audit association nhưng target entity không audited

Với reference data ít thay đổi hoặc không audit, Envers có cơ chế như:

```java
import org.hibernate.envers.RelationTargetAuditMode;

@Audited(
    targetAuditMode = RelationTargetAuditMode.NOT_AUDITED
)
@ManyToOne(fetch = FetchType.LAZY)
private Currency currency;
```

Ý định: Envers theo dõi association ở Invoice nhưng target Currency không có audit history riêng, nên historical association có thể dẫn tới **trạng thái hiện tại** của Currency thay vì một historical Currency snapshot.

Điều này khác `@NotAudited` trên chính association.

### 22.3. Cẩn thận khi reference data đổi nghĩa

Nếu Currency có field display name hay conversion rules thay đổi, historical Invoice có thể trỏ tới Currency hiện tại; việc hiển thị “tên Currency trong quá khứ” có thể không chính xác nếu UI lấy trạng thái target hiện tại.

Nếu audit report cần đúng snapshot của reference data, cần audit target hoặc lưu immutable code/snapshot phù hợp với domain.

### 22.4. Quan hệ targetAuditedMode phụ thuộc mapping

Không phải mọi association type, composite key hay collection đều có cùng semantics của `NOT_AUDITED` target. Các cơ chế đặc biệt như `@AuditJoinTable`, `@NotFound`, join tables và target entity auditing cần xem theo Hibernate Envers version.

## 23. Collection và modified flags

Một entity có:

```java
@Entity
@Audited(withModifiedFlag = true)
public class PurchaseOrder {

    @Id
    private Long id;

    @OneToMany(mappedBy = "order")
    private List<OrderLine> lines = new ArrayList<>();
}
```

Một câu hỏi là: “Khi một OrderLine được thêm hoặc xóa, cờ `lines_MOD` có tự đúng không?”

Câu trả lời không thể rút gọn thành “mọi thay đổi trong object graph đều làm mọi flag thay đổi”.

### 23.1. Cần phân biệt owner và association mapping

- Quan hệ owning side và inverse side khác nhau.
- `@OneToMany(mappedBy=...)` có thể không sở hữu FK.
- Collection audit có thể cần audit join table hoặc theo dõi child entity.
- Collection dirty checking có hành vi riêng.
- Thay đổi thuộc tính scalar của một child không nhất thiết được coi là **thay đổi collection membership** của parent.

### 23.2. Cờ collection không phải tổng hợp mọi thay đổi trong child

Ví dụ:

```java
OrderLine line = em.find(OrderLine.class, id);
line.changeQuantity(4);
```

Dù OrderLine được audit, không nên kết luận `PurchaseOrder.lines_MOD` chắc chắn true. Membership của collection có thể không đổi; chỉ scalar `quantity` của child thay đổi.

Nếu cần report “mọi thay đổi liên quan aggregate Order”, phải thiết kế truy vấn/metadata tổng hợp child revisions, hoặc phát domain event ở application layer.

### 23.3. Tránh suy luận qua inverse collection sau clear

Trong batch import, thêm child bằng `line.setOrder(parentRef)` không có nghĩa một managed inverse collection của parent đã được dirty checked. Envers theo dõi events/mapping thực tế; kiểm thử association revision flags trên đúng đường persist/update/remove.

### 23.4. Khi nào loại association khỏi audit?

Nếu association chỉ là cache/tạm thời và không có ý nghĩa lịch sử, `@NotAudited` có thể phù hợp. Nhưng nếu đây là quyền sở hữu, người phê duyệt, thành viên nhóm hoặc trạng thái quan hệ nghiệp vụ, bỏ audit có thể làm mất dữ liệu điều tra.

## 24. Embeddable và nested properties

Một entity có value object:

```java
@Embeddable
public class MailingAddress {

    private String city;
    private String postalCode;
    private String street;
}
```

Entity:

```java
@Entity
@Audited
public class CustomerAccount {

    @Id
    private Long id;

    @Embedded
    private MailingAddress address;
}
```

Khi cần audit/modified flag của từng thành phần trong embeddable:

- Xem cách Hibernate Envers flatten/map component fields thành audit columns.
- Xác định flag ở property container hay từng nested field theo version/mapping.
- Dùng override/annotations được Envers hỗ trợ khi cần loại một nested property.
- Kiểm tra query `AuditEntity.property(...).hasChanged()` có chấp nhận nested path tương ứng trong phiên bản cụ thể.
- Không tự đặt tên SQL flag bằng `address_city_MOD` rồi mặc định metadata Envers sẽ khớp.

### 24.1. Phân biệt thay object với đổi giá trị

Code:

```java
customer.setAddress(
    new MailingAddress("Hanoi", "100000", "Street A")
);
```

Nếu địa chỉ mới có cùng dữ liệu persistent như cũ, dirty checking và Envers không nhất thiết coi các thành phần là changed chỉ vì Java object reference khác.

### 24.2. Các kiểu custom cần equals/dirty checking chính xác

Với `AttributeConverter`, custom basic type hoặc mutable value object, cách Hibernate phát hiện change có thể phụ thuộc equality/mutability plan. Nếu logic flag changed rất quan trọng, nên có integration tests cho null→value, value→null và field cập nhật cùng giá trị.

## 25. Entity version và modified flag

Nhiều audited entities có:

```java
@Version
private long version;
```

Hibernate dùng `@Version` cho optimistic locking. Envers thường mặc định không audit version field theo setting:

```properties
org.hibernate.envers.do_not_audit_optimistic_locking_field=true
```

### 25.1. Version tăng không có nghĩa mọi field changed

Một revision có thể tăng version vì entity update, nhưng điều đó không cho biết `status` hay `displayName` được thay đổi. Modified flag mới chứa thông tin field-specific nếu được cấu hình.

### 25.2. Không dùng @Version làm lịch sử thay đổi

Version column có thể tăng theo updates nhưng không lưu snapshot cũ hoặc actor/timestamp. Envers revision number và version của entity là **hai khái niệm khác nhau**.

### 25.3. Khi dùng bulk SQL

Bulk HQL/Criteria UPDATE thường không tự tăng `@Version` theo entity lifecycle trừ khi được xử lý rõ, và Envers cũng không tự nhận audit event của từng row theo đường entity lifecycle. Modified flags không sửa được giới hạn ấy.

## 26. Những thao tác nào Envers thường theo dõi?

Đường entity lifecycle:

```java
@Transactional
public void changeAccountStatus(Long id, AccountStatus status) {
    CustomerAccount account =
        em.find(CustomerAccount.class, id);

    if (account == null) {
        throw new IllegalArgumentException("Not found");
    }

    account.changeStatus(status);
}
```

Managed entity được Hibernate dirty checked, tạo UPDATE nếu có thay đổi persistent phù hợp. Với Envers listener hoạt động, entity audit revision và modified flags có thể được ghi khi transaction flush/commit theo cấu hình.

### 26.1. Nhiều sửa đổi trước flush

```java
account.changeStatus(AccountStatus.SUSPENDED);
account.changeStatus(AccountStatus.ACTIVE);
```

Nếu state cuối bằng state ban đầu, dirty checking có thể không tạo change như mong đợi. Không coi từng setter invocation là Envers event bất biến.

### 26.2. persist và remove

```java
em.persist(account);
em.remove(account);
```

Envers có semantics ADD/DEL theo entity lifecycle, nhưng kết quả cuối của nhiều thao tác trong cùng transaction có thể được coalesced hoặc không tạo lịch sử như một chuỗi lệnh bên ngoài. Cần kiểm tra đúng workflow thực tế thay vì kỳ vọng một audit row mỗi lời gọi.

### 26.3. Rollback

Nếu transaction rollback, các audit rows thuộc cùng database transaction thông thường cũng rollback. Không gửi audit event ra hệ thống ngoài DB chỉ vì thấy Envers chuẩn bị SQL nếu nghiệp vụ yêu cầu only committed changes.

## 27. Bulk HQL/Criteria và native SQL bỏ qua đường audit entity

Ví dụ bulk update:

```java
int changed = em.createQuery("""
    update CustomerAccount a
    set a.status = :status
    where a.organizationId = :orgId
    """)
    .setParameter("status", AccountStatus.SUSPENDED)
    .setParameter("orgId", orgId)
    .executeUpdate();
```

Đây là **bulk DML** chạy trực tiếp trên database theo query, không duyệt managed entities rồi gọi entity lifecycle update từng row.

Hệ quả quan trọng:

- Envers thường **không tự sinh audit revision per-entity** cho những rows bị bulk update.
- Modified flags không tự được ghi cho từng row.
- `@PreUpdate` callback per-entity không chạy.
- Persistence context đã load entity có thể stale.
- Versioning và cache invalidation cần chính sách riêng.

### 27.1. Native SQL và JDBC

`EntityManager.createNativeQuery(...)` hoặc `JdbcTemplate.update(...)` cũng không tự biến mỗi changed row thành một Envers entity event. Database triggers vẫn có thể chạy, nhưng đó là cơ chế khác với Envers.

### 27.2. Đừng dùng Envers như bằng chứng mọi DB write đã được audit

Nếu hệ thống có nhiều writers—batch jobs, SQL maintenance scripts, import tools, ETL—cần thống kê đường ghi nào đi qua Hibernate entity lifecycle, đường nào không. Nếu phải audit tất cả, có thể cần database audit/CDC/triggers hoặc một workflow riêng.

### 27.3. Khi bulk update là bắt buộc

Có thể cân nhắc:

1. Đổi sang managed entity updates theo chunks nếu số rows/hiệu năng cho phép.
2. Viết audit rows/metadata bằng một cơ chế đã thiết kế riêng với DB transaction và revision semantics rõ (không giả vờ giống Envers nếu không bảo đảm).
3. Dùng database change capture/event sourcing phù hợp.
4. Ghi một domain-level bulk operation event nếu business chỉ yêu cầu tổng hợp.

Không tự insert vài cột `_AUD` thủ công mà bỏ qua revision consistency, revision strategies, composite keys, foreign keys, ordering và metadata.

## 28. Modified flags và độ chính xác của dirty checking

Envers dựa vào Hibernate entity state/mapping/event infrastructure để xác định thay đổi. Do đó cần hiểu một số trường hợp.

### 28.1. Gán lại cùng giá trị

```java
account.changeStatus(AccountStatus.ACTIVE);
// Status đã ACTIVE trước khi gọi.
```

Nếu không có thay đổi giá trị thực, Hibernate có thể không tạo UPDATE/audit revision cho status. Modified flag không phải “setter invoked flag”.

### 28.2. Null sang non-null

```text
creditLimit: null -> 1000
```

Đây là một change có nghĩa, modified flag thích hợp phải phản ánh changed property nếu entity update được audit qua đường hỗ trợ.

### 28.3. non-null sang null

```text
displayName: "An" -> null
```

Đây cũng là change, nhưng có thể bị database `NOT NULL` constraint từ chối. Nếu transaction rollback, audit row không được commit.

### 28.4. Mutable type và deep changes

Một field JSON/custom mutable type có thể được thay đổi *bên trong object* mà không thay reference. Nếu Hibernate mapping/mutability plan không phát hiện đúng, Envers cũng không thể đáng tin phát cờ changed.

Dùng immutable value objects, custom type equality và proper dirty tracking; kiểm thử mapping nếu field quan trọng.

### 28.5. Precision và converter

Với timestamps/numbers, Java value có thể khác nhưng database column precision làm tròn về cùng giá trị. Với `AttributeConverter` hoặc custom type, cần hiểu equality của snapshot Hibernate. Không lấy mọi khác biệt Java trước flush làm bằng chứng chính xác 100% của historical SQL value.

## 29. Modified flags không giải quyết đồng thời và overwrite

Hai users cùng sửa Customer#10. Envers có thể ghi revisions tuần tự sau commits, nhưng không ngăn lost update nếu transaction concurrency policy thiếu.

### 29.1. Optimistic locking

`@Version` có thể phát hiện một số xung đột khi Hibernate UPDATE managed entity.

```java
@Version
private long version;
```

Một transaction thua version check có thể rollback, do đó audit revision không được commit. Modified flags chỉ mô tả những changes được audit thành công.

### 29.2. Kịch bản ví dụ

```text
T1: Alice tải status=NEW, version=1
T2: Bob tải status=NEW, version=1

T1: status=ACTIVE -> commit (version=2)
T2: status=SUSPENDED -> version conflict -> rollback
```

Envers không nên bị hiểu là sẽ ghi cả “revision Bob đổi status” nếu transaction của Bob rollback. Nếu muốn audit **attempt** kể cả thất bại, cần event/audit operation riêng, khác với lịch sử state committed.

### 29.3. Concurrent field updates

Hai users đổi hai fields khác nhau nhưng dùng cùng `@Version` vẫn có thể conflict. Đây là quyết định concurrency của aggregate, không liên quan việc có hay không modified flags.

## 30. Cờ changed có phải dùng làm change event cho integration không?

Ví dụ một service bên ngoài cần nhận thông báo khi `creditLimit` đổi. Có thể dùng history query lọc `creditLimit_MOD = true` rồi polling revisions.

Nhưng cần nhận ra giới hạn:

- Envers không phải message queue có delivery guarantee tự động.
- Revision entity có thể ghi nhiều entities per transaction.
- Poller cần checkpoint/idempotency.
- Bulk SQL có thể bỏ qua Envers.
- Permission/tenant scope phải được áp.
- Audit rows có thể bị purge theo retention.
- Deleted entity và data-at-delete cần xử lý riêng.

Nếu downstream cần near-real-time business event, **transactional outbox** thường là lựa chọn rõ ràng hơn.

### 30.1. Một cờ changed không mang ý nghĩa nghiệp vụ đầy đủ

`creditLimit_MOD = true` chỉ nói field thay đổi, không nói:

- Ai phê duyệt?
- Vì sao tăng/hạ hạn mức?
- Yêu cầu business nào gây ra?
- Có phải thao tác điều chỉnh hệ thống?
- Có cần thông báo khách hàng không?

Domain event `CreditLimitApproved` có thể cần fields riêng và đảm bảo delivery.

### 30.2. Khi nào Envers thích hợp cho report?

- Tra cứu lịch sử trạng thái.
- Tìm revisions có field thay đổi.
- So sánh giá trị trước/sau.
- Điều tra sai lệch nghiệp vụ khi có dữ liệu audit đầy đủ.
- Hiển thị timeline cho nhân viên có quyền.

Dùng Envers cho **historical query**, không nên tùy tiện biến nó thành bus thực thi nghiệp vụ.

## 31. Truy vấn hiệu năng với hasChanged

Một audit table có thể rất lớn. Query lọc:

```java
.add(AuditEntity.property("status").hasChanged())
.add(AuditEntity.id().eq(accountId))
```

thường nên có điều kiện hẹp như:

- Entity ID.
- Revision range/timestamp window.
- Organization/tenant scope đã được kiểm soát.
- Revision type.
- Pagination/batch processing theo API hỗ trợ.

### 31.1. Index trên audit table

Một index có thể phục vụ truy vấn theo entity ID và revision:

```sql
CREATE INDEX idx_customer_aud_id_rev
ON customer_accounts_AUD (id, REV);
```

Nếu hệ thống hay lọc `status_MOD` với tập dữ liệu lớn, cân nhắc index/partial index theo dialect sau khi đo query plan. Không mặc định index một cột boolean luôn hữu ích vì selectivity có thể rất thấp.

### 31.2. Query plan phụ thuộc revision strategy

Envers có revision strategies như DefaultAuditStrategy và ValidityAuditStrategy (tùy phiên bản/cấu hình) với cách xác định revision validity khác nhau. Query reconstruction và performance có thể khác.

Modified flags là metadata nằm trong audit row nhưng không thay thế các semantics về khoảng thời gian có hiệu lực của từng entity snapshot.

### 31.3. Không tải mọi revisions rồi lọc trong Java

Ví dụ kém hiệu quả:

```java
List<Number> revs = reader.getRevisions(
    CustomerAccount.class,
    accountId
);

for (Number rev : revs) {
    CustomerAccount oldState =
        reader.find(CustomerAccount.class, accountId, rev);
    // So sánh toàn bộ trường...
}
```

Với vài chục revisions thì chấp nhận được cho một use case đơn giản. Với hàng triệu rows/queries lặp lại, sẽ tốn IO. Nếu modified flags được bật và đúng semantics, dùng audit query có predicate `hasChanged()` để filter tại database.

## 32. Audit history trong hệ thống đa tổ chức

Ví dụ `CustomerAccount` có `organizationId`.

Current repository có thể áp tenant filter hoặc `@TenantId`, nhưng không nên mặc định mọi AuditReader query đều có chính sách authorization giống current repository.

### 32.1. Quy tắc an toàn

- Xác minh principal thuộc organization đang truy cập.
- Xác minh quyền xem lịch sử của resource.
- Scope audit query bằng ID/resource đã xác thực.
- Không trả cả audit table nếu không có ranh giới tenant.
- Kiểm thử việc một user org A yêu cầu history entity org B.
- Đừng dùng ID global không đoán được thay cho authorization.

### 32.2. Dữ liệu quyền truy cập trong quá khứ

Một tài liệu đã chuyển owner hoặc organization có thể có lịch sử đặc biệt nhạy cảm. Câu hỏi “ai hiện tại được xem lịch sử trước chuyển quyền?” cần policy rõ; không suy luận quyền hiện tại tự động bao phủ mọi historical state.

### 32.3. Đừng log toàn bộ audit rows

Snapshot cũ có thể chứa email, địa chỉ, số tiền, trạng thái nhạy cảm. Log chỉ metadata/IDs phù hợp với chính sách privacy, không serialize toàn bộ historical entity mặc định.

## 33. Retention và quyền được quên

Dữ liệu audit được lưu lâu để phục vụ compliance, nhưng cũng có những yêu cầu giữ tối thiểu.

### 33.1. @NotAudited là prevention, không phải deletion

Thêm `@NotAudited` không xóa audit rows đã tồn tại hay backup cũ.

### 33.2. Cần retention policy riêng

Một chính sách có thể xác định:

- Giữ revision history của hóa đơn 7 năm theo quy định áp dụng.
- Giữ operational login timestamps chỉ 90 ngày trong hệ thống telemetry.
- Không lưu raw token/private keys vào Envers.
- Anonymize PII lịch sử khi được yêu cầu hợp lệ.
- Có quyền xem lịch sử và audit hành vi truy cập audit.

Các con số trên chỉ minh họa; retention phải do luật áp dụng và policy tổ chức quyết định.

### 33.3. Xóa audit rows có thể ảnh hưởng truy vấn Envers

Nếu xóa một số revision rows nhưng để lại các revisions khác không nhất quán, reconstruct historical state và modified flag semantics có thể không còn như mong đợi.

Thiết kế purge/anonymization theo entity/revision strategy, backup, FK và reporting requirements. Không chạy ad hoc DELETE chỉ dựa trên một cột ngày.

## 34. Tác động khi đổi tên field hoặc kiểu dữ liệu

Giả sử đổi:

```java
private String status;
```

thành:

```java
private AccountStatus lifecycleState;
```

Những thay đổi cần xét:

1. Current column mapping.
2. Audit data column mapping.
3. Modified flag column name, nếu dùng suffix từ property.
4. Mapping enum/string converter.
5. Query `AuditEntity.property("...")`.
6. Index/report SQL.
7. Schema migration và backward compatibility.
8. Historical values không còn thuộc enum mới.

### 34.1. Rename field không phải tự động rename cột audit

Nếu audit schema có `status_MOD`, code mới kỳ vọng `lifecycle_state_MOD`, có thể lỗi runtime nếu không migration đúng.

### 34.2. Backward-compatible enum evolution

Đổi hoặc xóa enum constants có thể làm Envers không đọc được historical rows có giá trị cũ. Cân nhắc converter/legacy mapping hoặc giữ compatibility khi đổi domain representation.

### 34.3. Thay @NotAudited thành audited

Nếu một field trước đây không audit, nay trở thành audited, audit table cần cột dữ liệu cho field. Các historical revisions trước migration **không tự có giá trị quá khứ** cho field đó.

Không điền toàn bộ rows cũ bằng giá trị hiện tại rồi mô tả như snapshot thật trong quá khứ.

## 35. Kiểm thử @NotAudited với một transaction chỉ sửa field bị loại

Một integration test nên:

1. Persist CustomerAccount, commit.
2. Ghi nhận revisions ban đầu bằng AuditReader trong context mới.
3. Thực hiện transaction chỉ đổi `lastViewedAt`.
4. Commit.
5. Đọc lại current row và xác nhận timestamp mới.
6. Kiểm tra lịch sử Envers không giữ giá trị timestamp đó.
7. Xác định semantics revision creation trên phiên bản đang dùng.
8. Đảm bảo không có thay đổi audited field tình cờ trong cùng transaction.

Ví dụ về intent:

```java
@Transactional
public void recordView(Long id, Instant time) {
    CustomerAccount account =
        em.find(CustomerAccount.class, id);

    account.recordView(time);
}
```

**Mục tiêu test:** chứng minh field không nằm trong audit history dù bảng hiện hành vẫn được cập nhật.

### 35.1. Test cả trường hợp đổi hai field

```java
account.recordView(time);
account.changeStatus(AccountStatus.ACTIVE);
```

Khi commit, revision audit cho status được tạo, nhưng `lastViewedAt` không phải một phần historical snapshot.

## 36. Kiểm thử modified flag đúng trường

Tạo entity `@Audited(withModifiedFlag = true)`, sau đó thực hiện các transactions riêng:

```text
T1: Persist entity NEW
T2: Change status NEW -> ACTIVE
T3: Change displayName "An" -> "An Nguyen"
T4: Change creditLimit 5000 -> 7000
```

Sau khi commit, kiểm tra audit table/revision query:

| Revision | STATUS_MOD | DISPLAY_NAME_MOD | CREDIT_LIMIT_MOD |
|---|---|---|---|
| T2 | true | false | false |
| T3 | false | true | false |
| T4 | false | false | true |

Các dòng minh họa **revision MOD**; không áp kỳ vọng y hệt cho ADD/DEL mà chưa xác nhận provider behavior.

### 36.1. Kiểm thử hasChanged query

- `status.hasChanged()` trả đúng revision T2.
- `displayName.hasChanged()` trả T3.
- `creditLimit.hasChanged()` trả T4.
- Kết hợp `status.hasNotChanged()` với `creditLimit.hasChanged()` trả T4.
- Nếu flags chỉ bật cho status, query hasChanged trên displayName không được giả định chạy.

### 36.2. Kiểm thử null và cùng giá trị

- null → 1000.
- 1000 → null (nếu schema cho phép).
- 1000 → 1000.
- Đổi status rồi đổi trở lại trước flush.
- Đổi một nonaudited field cùng transaction.
- Test annotation field/property access đúng.

Mục đích là xác minh trường changed phản ánh persisted state được Envers xem là thay đổi, không phải đếm setter calls.

## 37. Kiểm thử migration và lịch sử cũ

Trong môi trường có sẵn audit data:

1. Tạo rows audit theo schema **chưa có flags**.
2. Áp migration thêm cột flags.
3. Deploy mapping mới.
4. Tạo revisions mới.
5. Kiểm tra rows mới ghi flags đúng.
6. Kiểm tra rows cũ được hiển thị với semantics “unknown” nếu chưa backfill.
7. Nếu backfill, đối chiếu với snapshots/expected changes.
8. Xác nhận report không coi null là false.
9. Thử rollback deployment trong kế hoạch compatibility thích hợp.

### 37.1. Đừng chỉ test schema mới trống

Một database mới tạo từ mappings có thể hoạt động trong khi production cũ thiếu columns hoặc chứa null historical flags. Migration test cần dữ liệu từ trước rollout.

### 37.2. Kiểm tra indexes và query plans

Với audit table lớn, thêm cột boolean không phải vấn đề duy nhất. Query history có thể JOIN/aggregate theo revision metadata, nên đo performance với volume thực tế.

## 38. Kiểm thử các đường ghi không qua entity lifecycle

Một bộ test nên so sánh:

**Đường A — managed update:**

```java
@Transactional
public void changeStatusManaged(Long id) {
    CustomerAccount c = em.find(
        CustomerAccount.class,
        id
    );
    c.changeStatus(AccountStatus.ACTIVE);
}
```

**Đường B — bulk HQL:**

```java
@Transactional
public void changeStatusBulk(Long id) {
    em.createQuery("""
        update CustomerAccount c
        set c.status = :status
        where c.id = :id
        """)
        .setParameter("status", AccountStatus.ACTIVE)
        .setParameter("id", id)
        .executeUpdate();
}
```

Kiểm tra:

- Database current row đã đổi ở cả hai đường.
- Envers audit/modified flags xuất hiện theo entity lifecycle path.
- Bulk path không mặc định tạo per-row audit revision.
- Persistence context stale sau bulk nếu entity đã được load.
- Version/audit/permission rules được thiết kế riêng nếu bulk cần thiết.

Không dùng sự thành công của database UPDATE làm bằng chứng Envers đã ghi lại đầy đủ lịch sử.

## 39. Những nhầm lẫn thường gặp

| Nhầm lẫn | Hệ quả | Cách hiểu đúng |
|---|---|---|
| `@NotAudited` làm field không lưu ở current table | Mất/nhầm dữ liệu hiện hành | Chỉ loại field khỏi Envers audit mapping |
| `@Transient` và `@NotAudited` giống nhau | Mapping sai | Transient không persistent, NotAudited vẫn persistent |
| `@Audited` tự thêm flags | `hasChanged()` không chạy | Bật modified flags rõ ràng |
| `status_MOD=true` chứa old status | Report sai | Flag chỉ báo field changed, old value từ previous snapshot |
| Một revision tương ứng một setter | Lịch sử bị hiểu nhầm | Revision theo audited entity changes trong transaction |
| Mọi revision MOD nghĩa mọi field changed | Lọc sai | Có thể chỉ một số flags true |
| `hasNotChanged` trả mọi revision toàn hệ thống | Kết quả sai | Chỉ xét audited rows của entity/query |
| `@NotAudited` xóa lịch sử đã lưu | Privacy leak cũ | Annotation không purge dữ liệu cũ |
| Thêm flag annotation không migration schema | SQL error | Cập nhật _AUD columns đúng |
| NULL flag cũ bằng false | Sai lịch sử | NULL có thể là unknown/pre-migration |
| Global flags không có chi phí | Schema phình to | Bật chọn lọc hoặc đánh giá storage |
| Cho rằng relationship child đổi sẽ bật parent collection flag | Sai semantics | Kiểm tra ownership/mapping/association change |
| `targetAuditMode=NOT_AUDITED` giống @NotAudited | Đọc lịch sử sai | Audit association nhưng target không historic |
| Bulk HQL UPDATE vẫn tạo Envers revisions | Thiếu audit | Bulk bypass per-entity listeners |
| Field version tăng là evidence changed field | Sai | `@Version` khác modified flag |
| Envers là event bus | Missed events/side effects | Dùng outbox/saga nếu cần delivery |
| Audit query tự bảo vệ quyền tenant | Lộ lịch sử | Scope resource + authorization |
| Soft delete bỏ hoàn toàn dữ liệu audit | Retention sai | Audit persistence/retention riêng |
| Query hasChanged không cần flag index | Có thể chậm ở volume lớn | Đo query plan và thiết kế indexes |
| Hardcode audit column names | Mapping/dialect mismatch | Kiểm chứng DDL/version/naming strategy |
| Enum đổi tên không ảnh hưởng lịch sử | Lỗi hydrate entity cũ | Bảo vệ backward compatibility |

## 40. Bài tập 1 — Loại field khỏi audit

Một entity ghi thông tin đăng nhập:

```java
@Entity
@Audited
public class UserLogin {

    @Id
    private Long id;

    private String displayName;

    private Instant lastLoginAt;
}
```

Yêu cầu: vẫn lưu `lastLoginAt` ở bảng hiện hành nhưng không ghi lịch sử Envers.

**Gợi ý:**

```java
@NotAudited
private Instant lastLoginAt;
```

Không đổi thành `@Transient` nếu vẫn cần lưu cột.

**Câu hỏi:** Những audit rows đã lưu `lastLoginAt` trước khi thêm annotation có tự bị xóa không?

**Đáp án:** Không. Cần migration/retention/remediation riêng nếu phải xóa dữ liệu lịch sử cũ.

## 41. Bài tập 2 — Theo dõi duy nhất status

Yêu cầu: audit mọi field quan trọng của Invoice nhưng report chỉ lọc các revisions mà `status` đổi.

**Gợi ý:**

```java
@Entity
@Audited
public class Invoice {

    @Id
    private Long id;

    private BigDecimal amount;

    @Audited(withModifiedFlag = true)
    private String status;
}
```

Sau đó:

```java
.add(AuditEntity.property("status").hasChanged())
```

**Câu hỏi:** Có thể query `amount.hasChanged()` ngay không?

**Đáp án:** Không mặc định; chỉ khi mapping có modified flag tương ứng. Cần bật flag cho amount hoặc dùng cách so sánh historical snapshots khác.

## 42. Bài tập 3 — Bật toàn cục

Một hệ thống có 300 audited entities, mỗi entity 40 properties. Team muốn bật:

```properties
org.hibernate.envers.global_with_modified_flag=true
```

**Câu hỏi:** Điều gì cần kiểm tra trước?

**Gợi ý:** Số audit columns mới, migrations cho database hiện hữu, storage/write amplification, query cần dùng flags, naming collisions, retention và dữ liệu pre-migration.

Không kết luận “vì boolean rất nhỏ nên bật toàn cục luôn tốt”.

## 43. Bài tập 4 — Phân biệt snapshot và changed

Audit rows:

```text
REV 101: status=ACTIVE, STATUS_MOD=true
REV 102: status=ACTIVE, STATUS_MOD=false, CREDIT_LIMIT_MOD=true
REV 103: status=SUSPENDED, STATUS_MOD=true
```

**Câu hỏi 1:** Query `status = ACTIVE` lấy revision nào?

**Đáp án:** 101 và 102 theo snapshot value.

**Câu hỏi 2:** Query `status.hasChanged()` lấy revision nào?

**Đáp án:** 101 và 103 theo flags minh họa. Nếu cần chỉ MOD, thêm revision-type filter.

## 44. Bài tập 5 — Cờ không cho biết giá trị cũ

`STATUS_MOD=true` ở revision 50, status hiện tại tại revision đó là `CLOSED`.

**Câu hỏi:** Có biết ngay giá trị trước đó là `ACTIVE` không?

**Đáp án:** Không. Cần historical state ở revision audited trước đó của entity, không suy luận từ boolean flag.

## 45. Bài tập 6 — Bulk update

Một background job chạy:

```java
em.createQuery("""
    update Invoice i
    set i.status = 'OVERDUE'
    where i.dueDate < :cutoff
    """)
    .setParameter("cutoff", cutoff)
    .executeUpdate();
```

**Câu hỏi:** Tất cả Invoice có `status_MOD=true` trong Envers không?

**Đáp án:** Không mặc định. Bulk HQL DML không đi qua per-entity lifecycle auditing; cần workflow audit khác hoặc managed updates theo chunks.

## 46. Bài tập 7 — Audit relation hay target?

Invoice tham chiếu Currency; Currency không có history vì là reference data.

**Câu hỏi:** Nên dùng `@NotAudited` hay `@Audited(targetAuditMode = NOT_AUDITED)`?

**Gợi ý:** Nếu không cần biết Invoice dùng currency nào ở revision cũ, loại association khỏi audit. Nếu muốn lưu association ID nhưng không có historical Currency data, cân nhắc target audit mode phù hợp, và hiểu target object có thể được resolve theo trạng thái hiện tại.

## 47. Checklist thiết kế lịch sử thuộc tính và modified flags

1. **Mục đích audit:** cần reconstruct entity ở quá khứ, truy vấn field changes hay cả hai?
2. **Field classification:** business-critical, operational, sensitive, derived, temporary?
3. **Data minimization:** field nào không nên đưa vào audit table?
4. **Retention:** giá trị nào bị yêu cầu giữ/xóa sau thời gian cụ thể?
5. **@Audited scope:** entity và các thuộc tính inherited/embedded được audit đúng?
6. **@NotAudited:** loại field nào, ảnh hưởng report gì?
7. **@Transient:** field có cần persistent ở current table không?
8. **Modified flags:** bật toàn entity, từng property hay toàn cục?
9. **Column naming:** suffix/custom name có đụng schema và naming strategy không?
10. **Schema migration:** cột `_AUD` đã có trước deploy code chưa?
11. **Historical backfill:** flags cũ là unknown hay được backfill đúng?
12. **Revision type:** report có phân biệt ADD/MOD/DEL không?
13. **Query semantics:** `hasChanged` và `hasNotChanged` dùng đúng nghĩa?
14. **History values:** cần old/new values, không chỉ changed boolean?
15. **Access strategy:** field/property annotations đặt đúng vị trí mapping?
16. **Inheritance:** cần `@AuditOverride` cho mapped superclass?
17. **Embeddable:** nested fields và names có đúng Envers metadata không?
18. **Relations:** association audit và target audit mode có đúng domain?
19. **Collection:** membership changes có đúng semantics cần report?
20. **Dirty checking:** mutable/custom converted types có phát hiện changes chính xác?
21. **@Version:** không dùng optimistic version làm field-change history?
22. **Bulk DML:** có writers bypass entity lifecycle không?
23. **Security:** actor có quyền xem current và historical data không?
24. **Tenant:** audit query có scope organization đúng?
25. **Performance:** queries, indexes, audit table growth và retention được đo?
26. **Migration backward compatibility:** enum/field renames có phá lịch sử cũ?
27. **Testing:** có case null, same value, rollback, concurrent changes, ADD/MOD/DEL?
28. **Event delivery:** có đang lạm dụng Envers làm outbox/CDC thay vì audit?
29. **Privacy:** dữ liệu nhạy cảm cũ trong backups/logs có policy remediation?
30. **Monitoring:** đã quan sát lỗi schema, audit insert, query history, purge job?

## 48. Ghi nhớ

- **`@Audited`** bật audit history cho entity/thuộc tính được hỗ trợ; chỉ bật `@Audited` **không đồng nghĩa có modified flags**.
- **`@NotAudited`** loại một persistent attribute khỏi lịch sử Envers nhưng **không loại nó khỏi bảng hiện hành** như `@Transient`.
- **Modified flags** cho biết thuộc tính nào được Envers ghi nhận là changed tại audited revision; cột thường có hậu tố `_MOD`.
- Bật flags bằng **`@Audited(withModifiedFlag = true)`** ở cấp entity/property hoặc setting **`org.hibernate.envers.global_with_modified_flag`** khi cần.
- Có thể cấu hình tên bằng `modifiedColumnName` và hậu tố qua `org.hibernate.envers.modified_flag_suffix` theo Envers version/mapping.
- **`AuditEntity.property("status").hasChanged()`** lọc revisions mà status được đánh dấu đổi; **`hasNotChanged()`** lọc audit rows mà status không được đánh dấu đổi.
- **So sánh giá trị snapshot khác truy vấn changed flag:** `status = ACTIVE` có thể xuất hiện ở nhiều revisions không sửa status.
- Modified flag không lưu **old value**, không đếm setter calls và không bảo đảm revision tương ứng một field/SQL UPDATE.
- **Revision ADD/MOD/DEL** có semantics khác nhau; khi report về “đổi field của entity đã tồn tại”, nên xác định có lọc MOD không.
- **Migration là bắt buộc phải tính đến** khi bật flags trên hệ thống đã có audit tables; thêm annotation không tự backfill lịch sử.
- **NULL flags pre-migration không mặc nhiên bằng false**; nếu chưa backfill, phải coi đó là thiếu metadata.
- Đổi một field từ audited sang `@NotAudited` **không tự xóa dữ liệu lịch sử cũ**.
- **`@AuditOverride`** hữu ích khi cần thay chính sách audit cho inherited/embedded properties trong mapping hỗ trợ.
- **`@NotAudited` trên association khác `targetAuditMode = NOT_AUDITED`**: một bên không audit association, bên kia có thể audit quan hệ tới target không có history.
- Collection/embedded modified flags cần hiểu **mapping và dirty-checking semantics**; không suy luận mọi thay đổi child đều bật flag của parent.
- **Bulk HQL/Criteria DML, native SQL và JDBC ngoài entity lifecycle** không tự tạo Envers per-entity audit rows/modified flags.
- Envers là lịch sử state/revision, **không tự thay thế domain audit, outbox, authorization hoặc change delivery**.
- Audit history có thể chứa dữ liệu nhạy cảm; **phải kiểm tra tenant, quyền xem lịch sử, retention và redaction**.
- Test phải bao gồm transactions thật, dữ liệu audit trước/sau migration, null/same value, relation changes, version/conflicts và rollback.

**Kết luận:** Việc dùng Envers hiệu quả đòi xác định rõ **thuộc tính nào cần lưu lịch sử** và **thuộc tính nào cần truy vấn thời điểm thay đổi**. `@NotAudited` giúp giảm dữ liệu không cần thiết hoặc không nên giữ trong audit, còn `withModifiedFlag` giúp tìm các revision liên quan đúng field thay vì tự so sánh mọi snapshot. Hai tính năng chỉ đáng tin khi được cấu hình theo mapping thực tế, có migration cho các cột audit, kiểm thử semantics của revision và dirty checking, đồng thời nhận thức rằng bulk DML hay external writers không tự đi qua Envers. Khi kết hợp ranh giới trách nhiệm ấy với chính sách bảo mật, phân quyền và retention, lịch sử dữ liệu sẽ hữu ích cho điều tra và nghiệp vụ mà không trở thành gánh nặng lưu trữ hoặc nguồn sai lệch.
