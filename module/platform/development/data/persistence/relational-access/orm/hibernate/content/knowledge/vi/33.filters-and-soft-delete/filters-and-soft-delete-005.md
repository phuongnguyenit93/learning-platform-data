# Xóa mềm bằng @SoftDelete trong các phiên bản hỗ trợ

## 1. Vì sao cần xóa mềm trong ứng dụng Hibernate?

Thông thường, khi gọi `EntityManager.remove(entity)`, ứng dụng muốn xóa một hàng khỏi bảng cơ sở dữ liệu. Hibernate có thể sinh:

```sql
DELETE FROM customer_accounts
WHERE id = ?;
```

Sau khi transaction commit, hàng đó không còn trong bảng. Đây là **xóa vật lý** (*hard delete*). Tuy nhiên, nhiều hệ thống cần giữ bản ghi vì nghiệp vụ, khả năng khôi phục, đối soát hoặc yêu cầu bảo toàn quan hệ.

Ví dụ một tài khoản khách hàng ngừng hoạt động. Sản phẩm không muốn tài khoản xuất hiện trong danh sách người dùng đang hoạt động, nhưng vẫn cần giữ tham chiếu từ các hóa đơn đã phát sinh. Một cách là thêm cột chỉ báo:

```sql
CREATE TABLE customer_accounts (
    id BIGINT PRIMARY KEY,
    email VARCHAR(255) NOT NULL,
    display_name VARCHAR(255) NOT NULL,
    deleted BOOLEAN NOT NULL DEFAULT FALSE
);
```

Khi “xóa”:

```sql
UPDATE customer_accounts
SET deleted = TRUE
WHERE id = ?;
```

Khi “đọc danh sách còn hiệu lực”:

```sql
SELECT id, email, display_name
FROM customer_accounts
WHERE deleted = FALSE;
```

Đó là **xóa mềm** (*soft delete*): hàng vẫn nằm trong database nhưng được đánh dấu không còn tham gia luồng truy cập thông thường.

Vấn đề lớn nhất khi tự làm là dễ bỏ quên điều kiện `deleted = FALSE` ở một query nào đó. Hibernate cung cấp `@SoftDelete` trong các phiên bản có hỗ trợ để gắn chính sách xóa mềm trực tiếp vào mapping ORM.

## 2. Phạm vi bài học

Bài này tập trung vào annotation:

```java
org.hibernate.annotations.SoftDelete
```

và những hành vi liên quan trong Hibernate ORM:

- Cấu hình `@SoftDelete` cho entity.
- Ý nghĩa của `SoftDeleteType.DELETED` và `SoftDeleteType.ACTIVE`.
- Cột chỉ báo, kiểu dữ liệu SQL và `AttributeConverter`.
- Tác động tới `persist`, `find`, HQL/Criteria, `remove` và Spring Data repositories.
- Quan hệ, cascade, collections và optimistic locking.
- Dữ liệu đã xóa, khôi phục, uniqueness, foreign keys và audit.
- Sự khác biệt với `@SQLDelete`, `@Where`, `@SQLRestriction` và `@Filter`.
- Kiểm thử trên hệ quản trị cơ sở dữ liệu đích.

Không nên coi mọi ví dụ trong tài liệu là áp dụng cho mọi thế hệ Hibernate. Đây là API **đặc thù Hibernate**, không nằm trong Jakarta Persistence chuẩn. Annotation `@SoftDelete` được giới thiệu từ dòng **Hibernate ORM 6.4**; những cách dùng, lựa chọn strategy và giới hạn mapping có thể phát triển trong các bản 6.x/7.x. Trước khi áp dụng, phải kiểm tra version Hibernate thực tế và tài liệu của version đó.

## 3. Ba thuật ngữ cần phân biệt

| Thuật ngữ | Ý nghĩa | Dữ liệu sau thao tác |
|---|---|---|
| Hard delete | `DELETE` vật lý hàng dữ liệu | Hàng thường biến mất |
| Soft delete | Thay đổi cờ hoặc metadata đánh dấu đã xóa | Hàng vẫn tồn tại |
| Archival | Chuyển/lưu dữ liệu cũ sang kho khác theo chính sách | Có thể giữ hoặc xóa khỏi bảng chính |

Soft delete không phải:

- Một bản sao lưu có thể phục hồi mọi lỗi.
- Một hệ thống lịch sử thay đổi đầy đủ như Envers.
- Một giải pháp quyền truy cập và bảo vệ dữ liệu tự động.
- Bằng chứng rằng một bản ghi không thể bị xóa vật lý bởi DBA, JDBC hoặc job ngoài Hibernate.
- Thay thế mặc định cho luật bảo vệ dữ liệu cá nhân và retention policy.

Soft delete giúp các thao tác ORM thông thường coi một hàng như không còn hoạt động, trong khi database vẫn lưu nó.

## 4. @SoftDelete thuộc lớp nào?

Hình dung quá trình:

```text
Java service
   |
   v
EntityManager.remove(customer)
   |
   v
Hibernate ORM mapping
   |
   +-- Entity có @SoftDelete?
   |        |
   |        +-- Có -> DML đánh dấu inactive/deleted
   |        |
   |        +-- Không -> DELETE vật lý thông thường
   |
   v
JDBC + Database

Khi SELECT:
   Hibernate sinh predicate để không tải các hàng đã xóa
   trong những đường truy cập ORM được hỗ trợ.
```

Spring Boot chỉ giúp cấu hình provider và bean; Jakarta Persistence cung cấp `EntityManager.remove()`; **Hibernate mapping engine** quyết định entity này bị xóa mềm theo `@SoftDelete`.

Annotation đó không tự sửa câu native SQL do lập trình viên viết và không yêu cầu database ngăn lệnh `DELETE` vật lý từ mọi client.

## 5. Ví dụ tối thiểu: @SoftDelete trên entity

Một entity:

```java
package com.example.accounts.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import org.hibernate.annotations.SoftDelete;

@Entity
@Table(name = "customer_accounts")
@SoftDelete
public class CustomerAccount {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String email;

    @Column(nullable = false)
    private String displayName;

    protected CustomerAccount() {}

    public CustomerAccount(String email, String displayName) {
        this.email = email;
        this.displayName = displayName;
    }

    public Long getId() { return id; }
    public String getEmail() { return email; }
    public String getDisplayName() { return displayName; }
}
```

Với strategy mặc định `DELETED`, Hibernate thường sử dụng cột chỉ báo tên `deleted`, trong đó giá trị biểu diễn **chưa xóa** khác giá trị **đã xóa**. Kiểu SQL vật lý phụ thuộc dialect, converter và mapping.

Ví dụ DDL minh họa cho DBMS hỗ trợ Boolean:

```sql
CREATE TABLE customer_accounts (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    email VARCHAR(255) NOT NULL,
    display_name VARCHAR(255) NOT NULL,
    deleted BOOLEAN NOT NULL DEFAULT FALSE
);
```

DDL không phải một migration portable cho tất cả DBMS; cú pháp identity và Boolean cần điều chỉnh theo database đang triển khai.

### 5.1. Thao tác xóa thông thường

```java
@Transactional
public void closeAccount(long id) {
    CustomerAccount account =
        entityManager.find(CustomerAccount.class, id);

    if (account == null) {
        return;
    }

    entityManager.remove(account);
}
```

Thay vì xóa vật lý entity row, Hibernate có thể sinh SQL tương đương:

```sql
UPDATE customer_accounts
SET deleted = TRUE
WHERE id = ?
  AND deleted = FALSE;
```

Đây là SQL **minh họa**, không phải cam kết cú pháp chính xác: câu lệnh thực tế còn tùy Hibernate version, mapping, version column và dialect. Điểm bản chất là state đánh dấu đã xóa được thay đổi, hàng vẫn còn trong database.

## 6. Truy vấn sau khi xóa mềm

Ví dụ service:

```java
CustomerAccount account =
    entityManager.find(CustomerAccount.class, 100L);
```

Nếu row #100 đã được đánh dấu xóa, truy vấn ORM thông thường phải coi nó không còn là entity đang tồn tại để tải. Ở mức SQL khái niệm:

```sql
SELECT id, email, display_name
FROM customer_accounts
WHERE id = ?
  AND deleted = FALSE;
```

Tương tự HQL:

```hql
select a
from CustomerAccount a
where a.email = :email
```

Hibernate có thể thêm điều kiện của soft delete vào SQL được sinh. Ứng dụng không cần chép `a.deleted = false` vào mỗi HQL, và trong nhiều mapping cột soft-delete indicator không phải là một property nghiệp vụ được ánh xạ trực tiếp.

### 6.1. Không nhầm điều kiện SQL với filter bật/tắt tùy ý

`@SoftDelete` là chính sách mapping để dữ liệu đã xóa bị ẩn khỏi các đường truy cập Hibernate thông thường. Nó không giống `@Filter`, nơi application có thể bật/tắt filter và set parameters theo session. Không nên giả định có một API chuẩn `session.disableSoftDelete()` để lấy lại deleted rows.

## 7. Hai chiến lược DELETED và ACTIVE

Hibernate cung cấp các strategy biểu diễn ý nghĩa của cột chỉ báo.

| Strategy | Cách hiểu giá trị logic true | Ý nghĩa false | Tên cột mặc định thường gặp |
|---|---|---|---|
| `SoftDeleteType.DELETED` | Hàng đã bị xóa | Hàng còn hoạt động | `deleted` |
| `SoftDeleteType.ACTIVE` | Hàng còn hoạt động | Hàng đã bị xóa | `active` |

Với `DELETED`:

```java
@Entity
@SoftDelete(strategy = SoftDeleteType.DELETED)
public class CustomerAccount {
    @Id
    private Long id;
}
```

Trạng thái khái niệm:

```text
deleted = false -> đang có hiệu lực
deleted = true  -> đã xóa
```

Với `ACTIVE`:

```java
@Entity
@SoftDelete(strategy = SoftDeleteType.ACTIVE)
public class CustomerAccount {
    @Id
    private Long id;
}
```

Trạng thái:

```text
active = true  -> đang có hiệu lực
active = false -> đã xóa
```

**Đừng trộn nghĩa của cột** khi chuyển từ strategy này sang strategy kia. Đổi annotation mà không migrate dữ liệu hiện có có thể làm Hibernate hiểu ngược toàn bộ hàng đang còn sống và hàng đã xóa.

### 7.1. Chọn strategy nào?

- Chọn `DELETED` khi database/model quen dùng `is_deleted` hoặc `deleted`.
- Chọn `ACTIVE` khi schema đã có `active` và ý nghĩa `true = active`.
- Quyết định phải nhất quán giữa mapping, DDL, default values, migration và các ứng dụng khác cùng đọc bảng.

Không nên đổi strategy chỉ để tên field trong Java nhìn đẹp hơn.

## 8. Đổi tên cột soft-delete

Hibernate cho phép cấu hình tên cột:

```java
import org.hibernate.annotations.SoftDelete;
import org.hibernate.annotations.SoftDeleteType;

@Entity
@SoftDelete(
    strategy = SoftDeleteType.DELETED,
    columnName = "is_deleted")
@Table(name = "customer_accounts")
public class CustomerAccount {
    @Id
    private Long id;
}
```

Schema minh họa:

```sql
ALTER TABLE customer_accounts
ADD COLUMN is_deleted BOOLEAN NOT NULL DEFAULT FALSE;
```

Từ đây, cột `is_deleted` phải là cột được Hibernate điều khiển cho soft delete. Nếu bảng cũ đã có cột `deleted` khác, migration phải quyết định rõ giữ, chuyển đổi hay xóa cột cũ.

### 8.1. Không vô tình map indicator hai lần để ghi

Không nên vừa để Hibernate quản lý indicator qua `@SoftDelete` vừa tự ánh xạ một property writable với `@Column(name="is_deleted")` trên cùng entity mà chưa xét giới hạn mapping. Hai đường cập nhật cùng cột có thể tạo conflict, schema validation lỗi hoặc semantics khó kiểm soát.

Nếu nghiệp vụ cần hiển thị trạng thái deleted, cân nhắc DTO riêng đọc qua truy vấn quản trị hoặc một read model rõ ràng, thay vì biến indicator nội bộ thành setter có thể sửa tùy ý.

## 9. Kiểu Boolean không phải kiểu vật lý duy nhất

Một số hệ quản trị có cột Boolean thật; các hệ khác lưu cờ bằng số hoặc ký tự. Hibernate cho phép dùng `AttributeConverter<Boolean, T>` cho indicator.

Ví dụ lưu `Y`/`N`:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import org.hibernate.annotations.SoftDelete;
import org.hibernate.annotations.SoftDeleteType;
import org.hibernate.type.YesNoConverter;

@Entity
@SoftDelete(
    strategy = SoftDeleteType.ACTIVE,
    columnName = "active_flag",
    converter = YesNoConverter.class)
public class FeatureFlag {
    @Id
    private Long id;
}
```

Với `SoftDeleteType.ACTIVE`:

```text
logical true  = active
YesNoConverter maps true  -> "Y"
YesNoConverter maps false -> "N"

active_flag = 'Y' -> active
active_flag = 'N' -> soft-deleted
```

Một schema minh họa:

```sql
CREATE TABLE feature_flag (
    id BIGINT PRIMARY KEY,
    active_flag CHAR(1) NOT NULL DEFAULT 'Y',
    CONSTRAINT ck_feature_active_flag
        CHECK (active_flag IN ('Y', 'N'))
);
```

Nếu dùng `DELETED` với cùng converter:

```text
deleted_flag = 'N' -> chưa xóa
deleted_flag = 'Y' -> đã xóa
```

**Converter chỉ thay đổi biểu diễn vật lý** của trạng thái logic; nó không đảo nghĩa strategy. Nhầm converter với strategy có thể khiến mọi hàng bị coi là deleted.

### 9.1. Một AttributeConverter tự viết

Ví dụ một schema dùng `0`/`1`:

```java
import jakarta.persistence.AttributeConverter;

public class BooleanToZeroOneConverter
        implements AttributeConverter<Boolean, Integer> {

    @Override
    public Integer convertToDatabaseColumn(Boolean value) {
        return Boolean.TRUE.equals(value) ? 1 : 0;
    }

    @Override
    public Boolean convertToEntityAttribute(Integer dbValue) {
        if (dbValue == null) {
            return null;
        }
        return dbValue == 1;
    }
}
```

Sử dụng:

```java
@SoftDelete(
    strategy = SoftDeleteType.DELETED,
    columnName = "deleted_flag",
    converter = BooleanToZeroOneConverter.class)
```

Đây là converter minh họa. Khi database có ràng buộc `NOT NULL` và chỉ cho phép 0/1, ứng dụng cũng nên xử lý giá trị bất hợp lệ thay vì âm thầm xem mọi giá trị khác 1 là false. Kiểu parameter JDBC, cast và DDL phải được kiểm tra trên DBMS đích.

### 9.2. Không nhầm converter của soft-delete indicator với @Convert của field nghiệp vụ

Hibernate `@SoftDelete(converter=...)` mong converter có domain side `Boolean` cho trạng thái logic của indicator. Đây không phải một converter tự do dành cho bất cứ enum domain nào.

Nếu mapping dùng những type/strategy khác xuất hiện trong các phiên bản Hibernate mới, cần đọc contract API của phiên bản đó trước khi tái sử dụng converter Boolean.

## 10. Về phiên bản hỗ trợ

Đây là điểm quan trọng vì nhiều tutorial Hibernate dùng các kỹ thuật xóa mềm cũ.

| Thế hệ Hibernate | Lựa chọn cần lưu ý |
|---|---|
| Trước 6.4 | Không thể mặc định dùng built-in `@SoftDelete`; thường phải dùng `@SQLDelete` + predicate/filter tự cấu hình |
| 6.4 và các bản có API tương ứng | Hỗ trợ `@SoftDelete` theo tính năng và giới hạn của version |
| Các bản 6.x/7.x mới hơn | Có thể bổ sung options, strategy hoặc mở rộng mapping; phải kiểm tra Javadoc/docs đúng version |

Không thể kết luận Spring Boot hỗ trợ `@SoftDelete` chỉ dựa vào tên `spring-boot-starter-data-jpa`. Cần biết **Hibernate ORM version thực sự nằm trên runtime classpath**.

Ví dụ kiểm tra phiên bản qua Hibernate:

```java
String version =
    org.hibernate.Version.getVersionString();
System.out.println("Hibernate ORM version: " + version);
```

Mã này dùng trong chẩn đoán local/test. Trong production, quản lý version qua dependency lock/BOM và build metadata; không nên log tràn lan thông tin môi trường không cần thiết.

### 10.1. Không copy API mới vào dự án cũ

Nếu code biên dịch báo:

```text
Cannot resolve symbol 'SoftDelete'
```

nguyên nhân thường là Hibernate version quá cũ hoặc thiếu thư viện/nhầm imports. Không sửa bằng cách tự tạo annotation trùng tên. Hãy xem dependency graph và phiên bản provider mà Spring đang dùng.

## 11. So sánh với @SQLDelete và @Where trong các dự án cũ

Trước khi có `@SoftDelete`, một cách thông dụng:

```java
@Entity
@SQLDelete(
    sql = "UPDATE customer_accounts SET deleted = true WHERE id = ?")
@Where(clause = "deleted = false")
public class CustomerAccount {
    @Id
    private Long id;
}
```

Ý tưởng:

- `@SQLDelete` thay SQL DELETE ORM bằng câu UPDATE do lập trình viên định nghĩa.
- `@Where` thêm predicate vào một số câu đọc ORM.

Nhưng cách cũ có các giới hạn:

1. SQL thủ công có thể không phù hợp khi thêm `@Version` hoặc thay identifier mapping.
2. Predicate cố định có thể áp dụng khác nhau giữa các đường truy cập/association.
3. Tính di động giữa DBMS bị ảnh hưởng bởi SQL literal/column name.
4. Bulk HQL/native SQL và các thao tác ngoài Hibernate cần xử lý riêng.
5. Một số annotation legacy bị deprecated hoặc được thay bằng API như `@SQLRestriction` tùy Hibernate version.

Ví dụ cũ chỉ để giải thích cơ chế; **không copy nguyên vào production** mà không kiểm tra placeholder order, optimistic-locking, affected row count, filter behavior và phiên bản ORM.

### 11.1. Lợi ích của built-in @SoftDelete

Khi thuộc tính mapping được hỗ trợ, built-in `@SoftDelete` diễn đạt xóa mềm trực tiếp ở metadata level, giúp Hibernate phối hợp SQL generation và visibility policy thay vì lập trình viên tự ghép hai cơ chế thủ công.

Điều này làm giảm rủi ro quên predicate trên đường truy cập ORM được Hibernate hỗ trợ, nhưng không biến mọi thao tác SQL của cả hệ sinh thái thành an toàn mặc định.

## 12. @SoftDelete khác @Filter như thế nào?

Hibernate `@Filter` biểu diễn điều kiện động được bật/tắt theo Session:

```java
@FilterDef(
    name = "tenantFilter",
    parameters = @ParamDef(
        name = "tenantId",
        type = Long.class))
@Filter(
    name = "tenantFilter",
    condition = "tenant_id = :tenantId")
@Entity
public class Invoice {
    @Id
    private Long id;
}
```

Ví dụ này minh họa filter tenant; tên cột/kiểu cần khớp mapping và Hibernate version.

```java
Session session = em.unwrap(Session.class);
session.enableFilter("tenantFilter")
       .setParameter("tenantId", tenantId);
```

So sánh:

| Tính chất | `@SoftDelete` | `@Filter` |
|---|---|---|
| Mục tiêu chính | Chính sách xóa logic ở mapping | Điều kiện động theo Session |
| Tự phối hợp xóa logic | Có cho mappings được hỗ trợ | Không tự biến `remove()` thành soft delete |
| Mặc định ẩn dữ liệu xóa | Có theo mapping | Phụ thuộc filter được bật/định nghĩa |
| Có tham số runtime | Không theo kiểu Filter | Có |
| Dễ vô tình quên bật? | Ít hơn trên ORM path hỗ trợ | Có nếu app quên bật filter |
| Có thể phục vụ use case admin gồm deleted? | Không mặc định có công tắc bỏ qua | Có thể thiết kế dynamic filter phù hợp |

Không nhầm `@Filter` với Spring Security authorization. Filter điều khiển SQL predicate, còn quyền truy cập phải được enforce bằng context đáng tin và thiết kế bảo mật thích hợp.

## 13. @SoftDelete và Spring Data JPA

Repository:

```java
public interface CustomerAccountRepository
        extends JpaRepository<CustomerAccount, Long> {

    Optional<CustomerAccount> findByEmail(String email);
}
```

Service:

```java
@Service
public class AccountService {
    private final CustomerAccountRepository accounts;

    public AccountService(CustomerAccountRepository accounts) {
        this.accounts = accounts;
    }

    @Transactional
    public void deactivate(long id) {
        CustomerAccount account = accounts.findById(id)
            .orElseThrow();
        accounts.delete(account);
    }
}
```

Vì repository gọi JPA/Hibernate entity removal path, entity được map bằng `@SoftDelete` thường được đánh dấu deleted theo ORM semantics thay vì hard delete.

Sau commit:

```java
accounts.findById(id) // thường Optional.empty()
```

nếu request truy cập bằng persistence context mới và không có override hay khác biệt phiên bản.

### 13.1. deleteById, delete(entity), deleteAll

Các Spring Data CRUD methods có đường thực thi riêng tùy version. Đặc biệt các thao tác bulk/batch như `deleteAllInBatch()` có thể dùng HQL mutation thay vì lần lượt gọi `EntityManager.remove()` cho từng entity.

Không khẳng định mọi method `delete*` tự có đúng cùng cascade, callbacks hoặc SQL khi thiếu kiểm chứng. Cần kiểm tra Spring Data/Hibernate versions và SQL sinh ra trong integration test.

## 14. Vòng đời một entity soft-deleted

Một tình huống:

```java
CustomerAccount account = em.find(
    CustomerAccount.class, id);

em.remove(account);
```

Về JPA lifecycle, `remove()` đưa một managed entity sang trạng thái removed trong persistence context. Cơ chế xóa mềm quyết định thao tác database được thực thi khi flush.

```text
Before remove():
  Entity managed
  DB row deleted = false

remove(entity):
  Entity participates in remove lifecycle
  Hibernate schedules logical deletion

flush/commit:
  DB row deleted = true

New EntityManager:
  find(id) -> không thấy entity đang hoạt động
```

Không tiếp tục thao tác object removed như thể nó là managed entity bình thường. Một Java reference còn tồn tại trong memory sau `remove()` không làm row trở thành active trở lại.

### 14.1. Xóa mềm vẫn có thể gọi lifecycle callbacks

Vì ứng dụng gọi `EntityManager.remove()`, lifecycle events liên quan remove có thể được kích hoạt theo JPA/Hibernate mapping. Tuy nhiên không nên lấy việc callback chạy làm bằng chứng cột `deleted_at` hoặc `deleted_by` được tự động điền.

Callback nghiệp vụ cần được kiểm thử theo phiên bản và thứ tự flush; thêm các cập nhật property khác trong callback có thể không được ghi theo cách bạn đoán, bởi entity đã được lên lịch remove.

## 15. Transaction, flush và rollback

```java
@Transactional
public void closeAccount(long id) {
    CustomerAccount a = em.find(
        CustomerAccount.class, id);
    em.remove(a);
    em.flush();

    // Nếu sau đó ném RuntimeException làm rollback,
    // soft-delete UPDATE cũng bị rollback.
}
```

`flush()` đồng bộ SQL xuống DB trong transaction; **không đồng nghĩa đã commit**.

```text
BEGIN
  SELECT customer_accounts WHERE deleted=false
  UPDATE customer_accounts SET deleted=true
FLUSH
  (row có thể đã thay đổi trong transaction)
ROLLBACK
  (logical deletion chưa commit bị hoàn tác)
```

Khi transaction bị rollback, state Java mà ứng dụng giữ có thể không phản ánh đúng database đã rollback; nên kết thúc/discard persistence context phù hợp và không dựa vào entity đã đi qua failed transaction.

## 16. Optimistic locking với @Version

Một entity có:

```java
@Entity
@SoftDelete
public class CustomerAccount {
    @Id
    private Long id;

    @Version
    private long version;
}
```

Optimistic locking dùng `@Version` để phát hiện ghi/xóa trên state đã thay đổi đồng thời. Hibernate có thể đưa version predicate vào SQL deletion theo mapping/version:

```sql
UPDATE customer_accounts
SET deleted = TRUE
WHERE id = ?
  AND version = ?
  AND deleted = FALSE;
```

Đây chỉ là dạng SQL minh họa; **không giả định** soft delete luôn tăng version giống một entity update thông thường trong mọi phiên bản/strategy. Việc check version, update count và callback behavior phải được xác nhận bằng test concurrency.

### 16.1. Một race thực tế

```text
Transaction A                     Transaction B
-------------                     -------------
Load Account #42 version 3        Load Account #42 version 3
Change display name               Remove Account #42
Commit                            Commit

One transaction may conflict,
depending on version checks,
order of execution and locking.
```

Nếu yêu cầu một update không được âm thầm hồi sinh bản ghi đã deleted, test race giữa update và remove là bắt buộc. Database constraint, optimistic locking và predicate deleted còn hoạt động phải được xem như một hệ thống.

## 17. Có thể dùng indicator như một business field không?

Soft-delete indicator là một phần ORM metadata, không nhất thiết là field Java:

```java
@SoftDelete(columnName = "deleted")
public class CustomerAccount {
    // Không cần boolean deleted để Hibernate soft-delete.
}
```

Đừng viết:

```java
account.setDeleted(false);
repository.save(account);
```

như một cách giả định để restore nếu mapping cột deleted do `@SoftDelete` sở hữu. Nhiều mapping không có setter ấy, hoặc việc ánh xạ song song dễ tạo conflict.

Nếu nghiệp vụ cần trạng thái người dùng “tạm khóa”, “đang xác minh”, “ngừng kinh doanh” nhưng vẫn muốn account được tìm thấy bởi quản trị viên, tốt hơn là thêm một enum/status domain riêng và dùng `@SoftDelete` chỉ khi thực sự muốn coi row đã bị xóa khỏi ORM path thông thường.

## 18. Soft delete không thay thế trạng thái nghiệp vụ

Ví dụ các trạng thái:

```java
enum AccountStatus {
    PENDING_VERIFICATION,
    ACTIVE,
    SUSPENDED,
    CLOSED
}
```

Khác nhau:

- `SUSPENDED`: user có thể bị chặn đăng nhập, nhưng tài khoản vẫn là một entity còn tồn tại và quản trị viên cần xem.
- `CLOSED`: có thể vẫn cần giữ entity để đối soát.
- `@SoftDelete`: ORM mặc định coi entity không còn được hiển thị/tải qua truy cập thông thường.

Không dùng soft delete cho mọi thay đổi business status. Một entity bị ẩn khỏi mọi repository thông thường có thể khiến workflow support/appeal/chargeback khó thực hiện.

Quyết định soft delete phải xuất phát từ lifecycle của aggregate và khả năng truy cập lịch sử/khôi phục, không chỉ từ nhu cầu đổi một cờ Boolean.

## 19. Xử lý @ManyToOne tham chiếu tới bản ghi đã xóa

Giả sử Order tham chiếu Customer:

```java
@Entity
public class PurchaseOrder {
    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    private CustomerAccount customer;
}
```

Sau khi CustomerAccount được soft-delete, foreign key ở DB vẫn có thể hợp lệ vì row Customer vẫn tồn tại vật lý. Nhưng ORM truy cập tới Customer đã bị ẩn có thể có behavior khác nhau theo fetch plan/mapping/version.

Các câu hỏi cần kiểm thử:

- Một `find(PurchaseOrder.class,id)` có trả Order không?
- Khi truy cập `order.getCustomer()`, Hibernate có thể trả proxy/load target hay không?
- Join fetch inner join có làm biến mất Order khỏi kết quả vì Customer đã soft-delete?
- Left join có trả `null` cho target không còn active?
- Có exception khi proxy không tìm thấy target?

**Không dựa vào một giả định chung về association**. Với dữ liệu lịch sử như invoice/order, có thể cần lưu snapshot customer name/address trong Order hoặc thiết kế read model để vẫn hiển thị thông tin phù hợp sau khi Customer bị xóa mềm.

## 20. CascadeType.REMOVE và tác động tới con

Một aggregate:

```java
@Entity
@SoftDelete
public class Basket {

    @Id
    private Long id;

    @OneToMany(
        mappedBy = "basket",
        cascade = CascadeType.ALL,
        orphanRemoval = true)
    private List<BasketLine> lines = new ArrayList<>();
}
```

Khi xóa Basket qua `EntityManager.remove()`, Hibernate có thể cascade remove tới các BasketLine theo mapping.

Quan trọng:

- Basket có `@SoftDelete` không tự có nghĩa BasketLine cũng được soft delete.
- Nếu BasketLine **không** được cấu hình soft delete, remove cascade có thể xóa vật lý BasketLine.
- Nếu BasketLine cũng có soft-delete mapping phù hợp, đường remove của từng entity có thể dùng logical deletion.
- `orphanRemoval=true` trên collection là lifecycle operation cần kiểm thử; nó không đồng nghĩa tự động “đánh dấu mọi child bị xóa” theo chính sách của parent.

Một DB foreign key `ON DELETE CASCADE` thường chỉ phản ứng với SQL `DELETE` vật lý ở parent, **không** tự kích hoạt chỉ vì parent nhận SQL `UPDATE deleted=true`.

### 20.1. Đừng chọn cascade như một công tắc mù

Với đơn hàng và hóa đơn, xóa mềm Order không đồng nghĩa cần xóa mềm Invoice. Trong domain tài chính, dữ liệu invoice có thể cần giữ độc lập và có chính sách retention khác.

Hãy xác định aggregate boundary và quy tắc tham chiếu trước khi bật cascading remove.

## 21. @SoftDelete trên collection table

Trong các phiên bản Hibernate có hỗ trợ, `@SoftDelete` còn có thể áp dụng ở các collection mappings có bảng collection/join table phù hợp, chẳng hạn `@ElementCollection` hoặc những quan hệ dùng join table được hỗ trợ.

Ví dụ:

```java
@Entity
public class Article {

    @Id
    private Long id;

    @ElementCollection
    @CollectionTable(
        name = "article_tags",
        joinColumns = @JoinColumn(name = "article_id"))
    @Column(name = "tag_value")
    @SoftDelete(
        strategy = SoftDeleteType.DELETED,
        columnName = "removed")
    private Set<String> tags = new HashSet<>();
}
```

Ở ví dụ này, soft-delete indicator nằm trên **row của bảng `article_tags`**, không phải trên row Article hay một entity Tag độc lập. Khi một phần tử bị loại khỏi collection, Hibernate có thể đánh dấu row collection đó thay vì xóa vật lý.

### 21.1. Entity-level và collection-level là hai phạm vi

```text
article
  id=10, title="Hibernate"

article_tags
  article_id=10, tag_value="orm", removed=false
  article_id=10, tag_value="java", removed=true
```

Truy cập `article.getTags()` theo ORM path phù hợp thường chỉ xem những phần tử còn active.

Nếu muốn soft delete **Tag entity** dùng chung toàn hệ thống, cần đánh dấu chính Tag entity và phân biệt với việc soft delete row liên kết.

### 21.2. Mapping restrictions

Không phải mọi collection association dùng cùng chiến lược xóa:

- `@ElementCollection` lưu value rows trong collection table.
- `@ManyToMany` thường dùng join table.
- `@OneToMany` có thể dùng foreign key trực tiếp ở child entity table.

Các vị trí có thể đặt `@SoftDelete` và xử lý xóa ở collection khác nhau theo mapping và Hibernate version. Không đặt annotation bừa lên một `@OneToMany` rồi kỳ vọng Hibernate tự thêm indicator vào child entity table. Với child entity, nếu muốn delete logic ở mức entity, hãy xem xét `@SoftDelete` trên child entity.

## 22. @ManyToMany: xóa mềm quan hệ khác xóa mềm đối tượng

Giả sử một User thuộc một số Groups:

```java
@Entity
public class AppUser {

    @Id
    private Long id;

    @ManyToMany
    @JoinTable(
        name = "user_group_memberships",
        joinColumns = @JoinColumn(name = "user_id"),
        inverseJoinColumns = @JoinColumn(name = "group_id"))
    @SoftDelete(columnName = "removed")
    private Set<AppGroup> groups = new HashSet<>();
}
```

Trong những Hibernate mappings hỗ trợ soft delete cho collection join table, indicator `removed` mô tả membership row. Khi user rời group, membership có thể bị đánh dấu deleted mà Group entity không bị xóa.

```text
user #10 -- membership(active) --> group #5
user #10 -- membership(removed) --> group #8

group #8 vẫn là entity đang tồn tại
chỉ quan hệ giữa user #10 và group #8 bị loại.
```

Nếu cần lưu lịch sử nhiều lần join/leave cùng một cặp user/group, bảng join có unique constraints và identity model phải được thiết kế cẩn thận. Một collection join table có soft-delete indicator không tự biến nó thành một event log với nhiều bản ghi lịch sử được phép trùng.

## 23. Khóa duy nhất trở thành vấn đề quan trọng

Giả sử `email` có unique constraint:

```sql
CREATE TABLE customer_accounts (
    id BIGINT PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    deleted BOOLEAN NOT NULL DEFAULT FALSE
);
```

Sau khi account có email `a@example.test` bị soft-delete, row vẫn còn. Nếu tạo account mới cùng email:

```sql
INSERT INTO customer_accounts
    (id, email, deleted)
VALUES (102, 'a@example.test', FALSE);
```

database có thể từ chối do unique constraint cũ.

Điều này không phải Hibernate bug; đó là một **quyết định nghiệp vụ và schema** chưa được hoàn tất:

- Email phải độc nhất **vĩnh viễn**, kể cả khi user bị xóa?
- Hay chỉ độc nhất giữa những account còn active?
- Có được tái sử dụng email sau xóa hay không?
- Có yêu cầu giữ lịch sử tài khoản và liên kết hóa đơn trước đây?

Không thay đổi unique constraint nếu chính sách nghiệp vụ vẫn yêu cầu identity uniqueness tuyệt đối.

## 24. Partial/filtered unique index khi chỉ active rows cần unique

Trên PostgreSQL, có thể đặt unique index chỉ cho rows chưa xóa:

```sql
CREATE TABLE customer_accounts (
    id BIGINT PRIMARY KEY,
    email VARCHAR(255) NOT NULL,
    deleted BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE UNIQUE INDEX uq_customer_email_active
ON customer_accounts (lower(email))
WHERE deleted = FALSE;
```

Ở đây chỉ account đang active mới bị ràng buộc unique theo normalized lower-case email. Các account deleted cũ có thể giữ lại để đối soát, trong khi một account active mới có thể dùng lại email theo policy.

Lưu ý:

- Đây là cú pháp **PostgreSQL-specific**; SQL Server có filtered indexes, các DBMS khác có thể cần generated columns hoặc mô hình khác.
- `lower(email)` có semantics collation/Unicode riêng; cần xác định email uniqueness đúng.
- Nếu database đã có `UNIQUE(email)` toàn bảng, phải migrate/drop constraint cũ có kiểm soát.
- Khôi phục account cũ có thể thất bại vì một account active khác hiện đang dùng cùng email.

### 24.1. Vì sao UNIQUE(email, deleted) không luôn đúng?

```sql
UNIQUE (email, deleted)
```

chỉ cho phép tối đa một row active và một row deleted cho cùng email trong DBMS với Boolean non-null. Nhưng sau khi hai account cùng email lần lượt bị soft-delete, row thứ hai không thể đổi `deleted=true` vì đã có deleted row thứ nhất.

Nếu nghiệp vụ cho phép nhiều historical accounts cùng email, composite unique đơn giản đó là **không đủ**. Cần constraint dựa trên “active only” hoặc một thiết kế identity riêng.

## 25. Unique constraints trên collection table

Với `@ElementCollection Set<String>`, bảng collection có thể có khóa/candidate key như:

```text
(article_id, tag_value)
```

Nếu row `article_id=10, tag_value="orm"` bị soft-delete, rồi ứng dụng thêm lại tag `orm`:

```text
Old row:
  (10, "orm", removed=true)

New active membership:
  (10, "orm", removed=false)
```

Một unique constraint đơn giản trên `(article_id, tag_value)` có thể ngăn thêm row mới dù row cũ đã deleted.

Giải pháp phụ thuộc collection mapping và Hibernate's supported reinsertion strategy:

- Dùng key/constraint chỉ áp dụng với active rows nếu database hỗ trợ.
- Dùng entity link riêng với ID và lifecycle rõ nếu cần lịch sử membership.
- Thiết kế lại yêu cầu "thêm lại" và idempotency.
- Test remove → flush/commit → add lại, không chỉ test một lần remove.

Đừng mặc định mọi Set/Map/List sẽ khôi phục phần tử đã xóa theo cùng semantics.

## 26. Soft delete không xóa foreign keys vật lý

Ví dụ:

```sql
CREATE TABLE invoices (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customer_accounts(id)
);
```

Khi CustomerAccount bị soft-delete, row vẫn có ID trong database, do đó foreign key từ Invoice có thể vẫn hợp lệ. Đây là một lợi ích lớn khi giữ lịch sử giao dịch.

Nhưng nó tạo hai vấn đề:

1. ORM thông thường có thể không tải được Customer đã deleted vì visibility rule.
2. Các luồng cần hiển thị hóa đơn lịch sử vẫn phải quyết định lấy thông tin customer từ đâu.

Một mô hình phổ biến là Invoice giữ các snapshot fields cần cho chứng từ:

```java
@Entity
public class Invoice {
    @Id
    private Long id;

    private Long customerId;
    private String billedName;
    private String billedAddress;
}
```

Mã chỉ minh họa quyết định domain, không phải khuyến nghị thay mọi association bằng ID thô. Điểm chính: dữ liệu phải có ý nghĩa độc lập với việc current customer entity còn được Hibernate hiển thị hay không.

## 27. Soft delete và orphanRemoval

Với:

```java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.ALL,
    orphanRemoval = true)
private List<OrderLine> lines = new ArrayList<>();
```

Khi xóa một OrderLine khỏi collection, Hibernate có thể lên lịch remove cho child theo mapping. Nếu child entity có soft delete, quá trình physical-vs-logical deletion chịu ảnh hưởng annotation ở child. Nếu không, nó có thể bị hard delete.

Một số trường hợp có yêu cầu “loại line khỏi đơn” nhưng vẫn cần audit tất cả phiên bản dòng hàng; soft delete mọi OrderLine có thể thích hợp hoặc có thể tạo dữ liệu cũ khó truy vấn. Đừng coi `orphanRemoval` và `@SoftDelete` là hai từ đồng nghĩa.

Nếu OrderLine có unique/order index và bị thêm lại, cần test constraint, collection key và Hibernate DML sequence.

## 28. Native SQL không tự biết @SoftDelete

Ví dụ JDBC:

```java
String sql = """
    SELECT id, email
    FROM customer_accounts
    WHERE email = ?
    """;
```

Database thực thi đúng SQL này, không tự đọc annotation Java. Nếu thiếu:

```sql
AND deleted = FALSE
```

native query có thể trả cả row đã deleted.

Đây là một lỗi dễ gây rò rỉ dữ liệu nếu developer nghĩ Hibernate `@SoftDelete` tự bảo vệ mọi truy vấn.

### 28.1. Native SELECT được gọi qua EntityManager thì sao?

```java
entityManager.createNativeQuery("""
    SELECT id, email
    FROM customer_accounts
    """);
```

Đó vẫn là SQL gốc do ứng dụng cung cấp; đừng giả định Hibernate tự chèn soft-delete predicate vào mọi đoạn SQL text native. Nếu kết quả được map về entity, hành vi hydrate/cache có thể có chi tiết riêng theo version, nhưng **SQL raw vẫn phải được kiểm tra rõ ràng**.

### 28.2. Stored procedure, trigger và external jobs

Các writer bên ngoài Hibernate, ví dụ ETL, stored procedure hoặc DBA script, có thể cập nhật/xóa hàng mà không tuân theo quy tắc `@SoftDelete`. Nếu toàn tổ chức cần một chính sách bắt buộc, cân nhắc DB permissions, views, RLS và migration constraints thay vì chỉ dựa vào annotation ORM.

## 29. Bulk HQL mutation cần kiểm chứng riêng

Ví dụ:

```hql
delete from CustomerAccount a
where a.lastLoginAt < :cutoff
```

Đây là bulk mutation, không giống:

```java
for (CustomerAccount a : accounts) {
    entityManager.remove(a);
}
```

Các câu bulk HQL tác động ở query level, bỏ qua full per-entity lifecycle, callbacks và cascades. Với `@SoftDelete`, cách Hibernate chuyển đổi bulk deletion và áp dụng visibility rule phụ thuộc phiên bản/strategy/mapping.

Không tuyên bố tất cả các phiên bản luôn sinh hard DELETE hoặc luôn sinh soft UPDATE cho mọi bulk HQL. Cách làm đúng là:

1. Tạo fixture với active và deleted rows.
2. Chạy đúng bulk HQL bằng Hibernate version đang dùng.
3. Xem SQL được phát.
4. Assert current table rows và soft-delete indicator.
5. Kiểm tra entity callbacks, children, cache và transaction behavior.

### 29.1. Bulk UPDATE vẫn cần đặc biệt cẩn thận

```hql
update CustomerAccount a
set a.displayName = :name
where a.id = :id
```

Một bulk update không tự thực thi entity setters/dirty checking per row. Cần kiểm chứng liệu các predicate soft-delete được áp dụng theo HQL mutation semantics của version hay không. Một query update nhầm deleted row có thể vi phạm policy “đã xóa thì không thay đổi”.

Đối với native bulk UPDATE, hãy thêm `deleted=false` tường minh khi phù hợp.

## 30. Cẩn thận với dữ liệu đang managed trong Session

Ví dụ:

```java
CustomerAccount a = em.find(
    CustomerAccount.class, id);

// Một thao tác native/bulk khác đánh dấu row deleted.

CustomerAccount again = em.find(
    CustomerAccount.class, id);
```

Nếu `a` vẫn là managed instance trong first-level cache, Hibernate có thể trả lại Java object đó mà không đọc lại database ngay. Đó là quy tắc persistence context identity, không phải bằng chứng soft-delete mapping đã thất bại.

Khi trộn ORM với native DML:

- `flush()` các pending changes cần giữ trước bulk/native mutation.
- `clear()` nếu nhiều managed entities có thể stale.
- `refresh()` có thể dùng cho entity còn tồn tại và cần cập nhật state, nhưng có thể không phù hợp nếu row đã bị soft-deleted và không còn loadable qua ORM.
- Đừng để code tiếp tục ghi trạng thái cũ rồi vô tình làm sai lifecycle.

Hibernate L2/query cache cũng có thể stale nếu SQL ngoài ORM thay đổi indicator mà không thông báo provider.

## 31. Soft delete và second-level cache

Nếu entity cacheable:

```java
@Entity
@SoftDelete
@Cacheable
@org.hibernate.annotations.Cache(
    usage = CacheConcurrencyStrategy.READ_WRITE)
public class CustomerAccount {
    @Id
    private Long id;
}
```

Hibernate phải phối hợp giữa entity state và cache khi gọi remove qua ORM path. Nhưng nếu dùng native UPDATE trực tiếp:

```sql
UPDATE customer_accounts
SET deleted = TRUE
WHERE id = 10;
```

Hibernate có thể không biết cache entry cho #10 cần invalidated. Một Session khác có thể thấy state cũ tùy cache strategy và thời điểm.

Thiết kế an toàn:

- Ưu tiên một đường mutation được hỗ trợ thống nhất.
- Khi có out-of-band writes, có cơ chế cache eviction/invalidation rõ ràng.
- Test đọc qua Session mới sau soft delete và sau native update.
- Đo cache churn, hit/miss và stale-read behavior theo provider.

Đừng bật L2 cache cho entity quan trọng về quyền truy cập khi chưa kiểm chứng freshness/consistency.

## 32. @SoftDelete không phải hệ thống lịch sử Envers

Soft delete giữ lại row hiện tại với cờ deleted. Nó không tự lưu:

- Những giá trị cũ của mọi field.
- Ai đã thay đổi entity qua từng lần cập nhật.
- Thời điểm chính xác mỗi lần đổi status.
- Một chuỗi revisions có thể truy vấn as-of time.

Ví dụ:

```text
Trước xóa:
  email="new@example.test"
  deleted=false

Sau xóa mềm:
  email="new@example.test"
  deleted=true

Giá trị email cũ hơn:
  không tự được khôi phục chỉ từ soft-delete flag.
```

Nếu cần audit history, có thể cân nhắc Hibernate Envers hoặc một event/audit mechanism khác. Khi kết hợp `@Audited` và `@SoftDelete`, cần kiểm chứng theo Hibernate/Envers version rằng quá trình soft delete tạo revision như yêu cầu, không tự kết luận.

### 32.1. Hai chính sách retention khác nhau

Soft delete có thể giữ dữ liệu trên bảng chính; Envers có thể giữ nhiều snapshot lịch sử. Nếu policy yêu cầu xóa dữ liệu cá nhân sau một khoảng thời gian, phải xem xét cả current soft-deleted rows lẫn các audit tables, backups, logs và cache.

## 33. DeletedAt và DeletedBy

Nhiều hệ thống muốn thêm:

```text
deleted_at
deleted_by
delete_reason
```

Nhưng `@SoftDelete(strategy=DELETED)` với Boolean indicator không tự điền những cột đó. Cần thiết kế cách ghi metadata.

Một phương án là dùng domain service:

```java
@Transactional
public void closeAccount(long id, String reason) {
    CustomerAccount account =
        accounts.findById(id).orElseThrow();

    account.recordClosureReason(reason);
    accounts.flush();  // nếu muốn chắc chắn field nghiệp vụ được ghi
    accounts.delete(account);
}
```

Đây là cách minh họa, cần cân nhắc tác động audit/version/transaction và thứ tự flush. Một số ứng dụng thích dùng bảng `account_deletion_events` ghi lý do/người thực hiện trong cùng transaction thay vì đặt metadata vào row soft delete.

Nếu dùng converter/strategy có hỗ trợ timestamp ở những phiên bản mới, phải xem chính xác API version, semantics và DDL thay vì tự giả định Boolean converter vẫn phù hợp. Mục tiêu là có **một hợp đồng lưu trữ rõ ràng** cho deleted indicator và metadata.

## 34. Khôi phục bản ghi đã xóa mềm

Vấn đề lớn: mặc dù row vẫn nằm trong DB, ORM thông thường không tải được nó:

```java
CustomerAccount deleted = em.find(
    CustomerAccount.class, deletedId);
// thường nhận null ở persistence context mới
```

Do đó không có một quy trình restore chuẩn kiểu “load deleted entity như bình thường, set deleted=false, save” áp dụng cho mọi `@SoftDelete` mapping.

### 34.1. Những việc cần làm khi restore

1. Kiểm tra người dùng có quyền restore.
2. Xác nhận row đã bị soft-delete và vẫn tồn tại.
3. Xác nhận tenant/ownership/security.
4. Kiểm tra unique constraints, đặc biệt email/username/slug.
5. Kiểm tra foreign keys và parent/child lifecycle.
6. Xác định entity có cần khôi phục association/collection rows hay không.
7. Ghi audit/recovery event.
8. Thực hiện transaction và invalidate cache theo policy.

### 34.2. Một hướng kỹ thuật: repository quản trị với SQL có kiểm soát

Nếu Hibernate API cho entity không cung cấp chế độ includeDeleted, ứng dụng có thể xây **admin-only** native SQL query và mutation qua một repository riêng, có authorization và tenant predicate.

```sql
SELECT id, email, deleted
FROM customer_accounts
WHERE id = :id
  AND tenant_id = :tenantId;
```

Và khi đã kiểm tra điều kiện nghiệp vụ:

```sql
UPDATE customer_accounts
SET deleted = FALSE
WHERE id = :id
  AND tenant_id = :tenantId
  AND deleted = TRUE;
```

Ví dụ giả định bảng có cột `tenant_id`; nếu schema không có thì điều kiện phải được điều chỉnh theo mô hình bảo mật thực tế. Đây là SQL khái niệm cho strategy `DELETED` với Boolean, không dùng nguyên cho `ACTIVE` hoặc `YesNoConverter`.

Native restore có thể bypass lifecycle, optimistic locking và cache synchronization. Phải kiểm tra affected row count, concurrency và invalidate cache. Không tự coi UPDATE raw này là một public endpoint hoàn chỉnh.

## 35. Restore không đơn giản là đảo Boolean

Giả sử:

```text
T1: Account A dùng email "user@example.test"
T2: Soft delete Account A
T3: Account B được tạo với email giống A
T4: Admin muốn restore Account A
```

Nếu unique index chỉ bảo vệ active rows, restore A có thể vi phạm constraint vì B đang active.

Chính sách nghiệp vụ có thể là:

- Từ chối restore và yêu cầu xử lý conflict.
- Gán email mới sau xác minh.
- Merge accounts bằng quy trình riêng.
- Không cho phép tái sử dụng email từ đầu.

Không tạm tắt unique constraint để “restore cho được”. Database constraint chính là lớp chặn tình huống tạo hai active identities trùng.

## 36. Xóa mềm nhiều lần và idempotency

Một API DELETE có thể được gọi lại do client retry:

```text
Request 1: DELETE /accounts/42
   -> soft delete thành công
   -> response bị mất trên mạng

Request 2: DELETE /accounts/42
   -> ORM find thường trả không có bản ghi
```

API nên quyết định semantics:

- Trả 204/200 cho thao tác “đảm bảo tài nguyên không còn active” (idempotent).
- Hoặc trả 404 khi resource đã không còn có thể truy cập, nếu contract yêu cầu.

Đừng biến retry thành lỗi transaction nặng hoặc vô tình tạo audit/delete events trùng. Nếu cần sự kiện “AccountDeleted” chỉ phát một lần, cần idempotency và durable event/outbox phù hợp.

### 36.1. Race giữa hai DELETE

Hai transactions cùng xóa một active row có thể gặp row-count mismatch/stale state tùy optimistic locking và Hibernate version. Điều đó không có nghĩa hard deletion đã xảy ra; cần test driver/DBMS và mapping để chọn response/retry đúng.

## 37. Hard purge sau retention period

Soft delete đôi khi chỉ là bước đầu:

```text
ACTIVE
   |
   v
SOFT_DELETED (ẩn trong ORM)
   |
   | Sau thời hạn retention và approval
   v
PHYSICAL_PURGE (xóa hoặc anonymize dữ liệu)
```

Một job purge có thể xóa vật lý rows đã deleted:

```sql
DELETE FROM customer_accounts
WHERE deleted = TRUE
  AND deleted_at < :retentionCutoff;
```

SQL giả định đã có cột `deleted_at` và được kiểm chứng. Nếu chỉ có Boolean mà không có timestamp, database không tự biết đã xóa bao lâu; cần metadata khác.

Purge phải tính:

- Foreign keys và dependent rows.
- Envers/audit history hoặc snapshot backups.
- Phân vùng/archiving nếu bảng quá lớn.
- Privacy/legal retention.
- Batch size và transaction log.
- Quá trình xóa dữ liệu trên cache, search index, object storage.

Không tự áp dụng purge trên production nếu chưa xác định yêu cầu lưu giữ và legal hold.

## 38. Truy vấn báo cáo có cần xem deleted rows?

Một câu hỏi:

> “Có bao nhiêu khách hàng đang hoạt động?”

thường chỉ cần active rows. Nhưng:

> “Có bao nhiêu tài khoản từng tồn tại và đã đóng trong quý?”

cần cả deleted rows và metadata về thời điểm đóng.

Nếu repository JPA dùng entity có `@SoftDelete`, query thông thường được thiết kế để ẩn deleted rows. Do đó báo cáo tổng lịch sử không nên dựa vào `repository.count()` rồi nghĩ đó là toàn bộ row count của database.

Một reporting model nên phân biệt:

```sql
SELECT COUNT(*)
FROM customer_accounts
WHERE deleted = FALSE;
```

và:

```sql
SELECT COUNT(*)
FROM customer_accounts;
```

Khi sử dụng native SQL/reporting query, phải định nghĩa quyền truy cập và consistency rõ; không để endpoint bình thường vô tình được xem toàn bộ deleted data.

## 39. Security: một flag không phải ACL

Ẩn một entity qua `@SoftDelete` không thay thế authentication/authorization.

Một native query:

```sql
SELECT *
FROM customer_accounts
WHERE id = :id;
```

có thể trả deleted row nếu không có policy SQL. Một attacker có quyền gọi endpoint quản trị sai scope có thể thấy dữ liệu đã được “xóa” trong UI.

Nên có:

- Authorization tại service/API boundary.
- Tenant context lấy từ hệ thống xác thực đáng tin.
- Predicate tenant ở mọi read/write path cần thiết.
- Database least privilege hoặc RLS nếu phù hợp.
- Logging an toàn, không lộ deleted PII.
- Kiểm thử trực tiếp raw SQL/admin endpoints.

### 39.1. Multi-tenancy và soft delete là hai trục khác nhau

```sql
WHERE tenant_id = :tenantId
  AND deleted = FALSE
```

đây là hai điều kiện riêng. Soft-delete mapping không biết bản ghi thuộc tenant nào nếu multi-tenancy policy chưa được cấu hình. Không giả định `@SoftDelete` tự bổ sung tenant isolation.

## 40. Migration từ @SQLDelete/@Where cũ

Một dự án trước đây có:

```java
@SQLDelete(sql =
    "UPDATE customer_accounts SET deleted = true WHERE id = ?")
@Where(clause = "deleted = false")
```

Khi nâng lên `@SoftDelete`, không chỉ thay hai annotations bằng một.

Quy trình:

1. Xác định Hibernate version đã hỗ trợ built-in feature.
2. Xác định cột hiện tại: tên, type, default, nullability và giá trị logic.
3. Chọn `DELETED` hay `ACTIVE` để giữ nguyên semantics.
4. Nếu dùng `Y/N` hoặc `0/1`, cấu hình converter tương thích.
5. Kiểm tra indexes/unique constraints/soft-delete collections.
6. Gỡ cấu hình xóa/predicate cũ có nguy cơ trùng hoặc xung đột.
7. Test CRUD, derived queries, Criteria, joins, cascading, bulk operations.
8. Test schema validation, SQL logging và concurrency.
9. Triển khai có rollback strategy phù hợp với thay đổi mapping và DDL.

### 40.1. Không giữ hai chiến lược xóa trên cùng entity một cách vô thức

Nếu vừa giữ `@SQLDelete` tùy biến vừa thêm `@SoftDelete`, Hibernate có thể tạo/diễn giải SQL theo đường khác với ý định hoặc báo mapping conflict. Không nên tin rằng hai annotation chỉ “tăng độ an toàn”.

Hãy chọn **một hợp đồng deletion chính** và có integration test rõ ràng.

## 41. Chiến lược migration khi đổi DELETED sang ACTIVE

Ví dụ cũ:

```text
deleted = FALSE -> active
deleted = TRUE  -> deleted
```

Schema mới:

```text
active = TRUE -> active
active = FALSE -> deleted
```

Data migration phải đảo logic:

```sql
ALTER TABLE customer_accounts
ADD COLUMN active BOOLEAN;

UPDATE customer_accounts
SET active = NOT deleted;
```

Sau khi dữ liệu đã được backfill, cần ràng buộc `NOT NULL`/default phù hợp và chuyển ứng dụng sang mapping mới theo migration sequence được kiểm soát. Không xóa cột `deleted` cũ trong lúc phiên bản ứng dụng cũ vẫn đang chạy nếu không có kế hoạch compatibility.

SQL `NOT deleted` chỉ đúng khi cột không null và DB hỗ trợ cú pháp Boolean tương ứng. Với cột legacy có NULL, phải xác định ý nghĩa NULL trước khi migrate.

## 42. Schema defaults và nullability

Một cột Boolean:

```sql
deleted BOOLEAN NULL
```

cho phép NULL. Trong SQL three-valued logic, predicate:

```sql
WHERE deleted = FALSE
```

không match rows có deleted NULL. Nếu legacy data có NULL biểu thị chưa xóa, built-in soft-delete mapping có thể ẩn ngoài ý muốn.

Do đó:

- Backfill NULL theo business policy.
- Đặt cột `NOT NULL` khi phù hợp.
- Đặt default tương ứng với active row cho các INSERT ngoài Hibernate.
- Kiểm tra mọi writer, ETL và migration.

Ví dụ:

```sql
UPDATE customer_accounts
SET deleted = FALSE
WHERE deleted IS NULL;

ALTER TABLE customer_accounts
ALTER COLUMN deleted SET NOT NULL;
```

Đoạn ALTER là cú pháp PostgreSQL minh họa. MySQL/SQL Server/Oracle dùng cú pháp DDL khác; hãy chạy migration trên DBMS đích.

## 43. Query plan và index với soft-delete predicate

Một query thông thường:

```sql
SELECT id, email
FROM customer_accounts
WHERE deleted = FALSE
  AND email = :email;
```

Khi soft delete được thêm vào mọi truy vấn, indexes hiện tại có thể chưa phù hợp.

Trên PostgreSQL, có thể cân nhắc partial index cho active rows:

```sql
CREATE INDEX idx_customer_active_email
ON customer_accounts (email)
WHERE deleted = FALSE;
```

Nếu query cần uniqueness active-only, một **unique partial index** có thể đảm nhận cả constraint và access path, tránh tạo nhiều indexes trùng công dụng.

### 43.1. Vì sao không luôn thêm index trên cột deleted?

Nếu 99% hàng có `deleted=false`, index chỉ trên Boolean deleted có độ chọn lọc thấp, đôi khi không giúp nhiều. Một index kết hợp `tenant_id, email` hoặc một partial index có thể phù hợp hơn với query thực tế.

Cần đo:

- Số hàng active vs deleted.
- Predicate thường dùng.
- SQL Hibernate sinh.
- `EXPLAIN`/execution plan.
- Chi phí UPDATE khi đánh dấu deleted.
- Table bloat/vacuum hoặc storage behavior theo DBMS.

Một index giúp SELECT có thể làm mỗi INSERT/UPDATE tốn thêm chi phí duy trì; chọn theo workload.

## 44. Hiệu năng: xóa mềm đổi chi phí như thế nào?

Hard delete và soft delete có trade-offs:

| Chi phí | Hard delete | Soft delete |
|---|---|---|
| Thao tác xóa | DELETE row/index references | UPDATE indicator/index membership |
| Giữ lịch sử hàng | Không còn ở bảng chính | Có, ở dạng row hiện tại |
| Khả năng khôi phục | Phải dựa backup/audit khác | Có thể restore theo policy |
| Đọc active rows | Không cần deleted predicate | Thường có predicate |
| Dung lượng bảng theo thời gian | Có thể giảm | Deleted rows tích lũy |
| FK từ bảng khác | Có thể cản xóa | Thường vẫn trỏ được row |
| Uniqueness tái sử dụng key | Key freed sau DELETE nếu không ràng buộc khác | Cần xem partial/filtered indexes |
| Referential semantics trong ORM | Entity biến mất vật lý | Entity bị ẩn dù row còn |

Soft delete không mặc nhiên rẻ hơn hard delete. Một bảng lớn có nhiều deleted rows nhưng ít purge có thể làm scans, indexes và vacuum costs tăng.

Nếu sản phẩm chọn xóa mềm lâu dài, phải có kế hoạch retention, partitioning/archival và monitoring dữ liệu đã xóa.

## 45. Các test tối thiểu với @SoftDelete

Một integration test nên xác nhận:

1. Persist entity → cột indicator ở trạng thái active.
2. Find/query entity → thấy row active.
3. Remove trong transaction và commit → row vẫn tồn tại vật lý nhưng được đánh dấu deleted.
4. Mở EntityManager/Session mới → find/query không trả entity deleted.
5. Native SQL đọc bảng → row còn tồn tại cùng giá trị indicator tương ứng.
6. Rollback transaction remove → row vẫn active.
7. Lặp delete request → đúng API idempotency contract.
8. Query với nhiều rows active/deleted → count/list phản ánh visibility.

Thêm tests cho association, cascade, cache, uniqueness, restored rows và bulk HQL nếu hệ thống dùng.

### 45.1. Không test tất cả trong cùng một persistence context

Ví dụ:

```java
CustomerAccount before = em.find(
    CustomerAccount.class, id);
em.remove(before);

// Không lấy một lần find() khác trong cùng EM
// làm bằng chứng dữ liệu đã bị ẩn đối với mọi request.
```

Persistence context giữ state của entity và có removed status riêng. Để kiểm chứng visibility sau commit, dùng **một transaction và EntityManager mới** hoặc `clear()` khi phù hợp.

## 46. Ví dụ integration test với Spring Boot và Testcontainers

Một khung test:

```java
@Testcontainers
@SpringBootTest
class CustomerSoftDeleteIT {

    @Container
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine")
            .withDatabaseName("soft_delete_test");

    @DynamicPropertySource
    static void databaseProperties(
            DynamicPropertyRegistry registry) {
        registry.add(
            "spring.datasource.url",
            postgres::getJdbcUrl);
        registry.add(
            "spring.datasource.username",
            postgres::getUsername);
        registry.add(
            "spring.datasource.password",
            postgres::getPassword);
    }

    @Autowired
    CustomerAccountRepository repository;

    @Autowired
    TransactionTemplate tx;

    @Autowired
    JdbcTemplate jdbc;

    @Test
    void removeMarksRowButNormalFindCannotSeeIt() {
        Long id = tx.execute(status -> {
            CustomerAccount account =
                new CustomerAccount(
                    "sample@example.test", "Sample");
            return repository.saveAndFlush(account).getId();
        });

        tx.executeWithoutResult(status ->
            repository.deleteById(id));

        Boolean markedDeleted = jdbc.queryForObject(
            "SELECT deleted FROM customer_accounts WHERE id = ?",
            Boolean.class,
            id);

        assertEquals(Boolean.TRUE, markedDeleted);

        Boolean visibleToOrm = tx.execute(status ->
            repository.findById(id).isPresent());

        assertEquals(Boolean.FALSE, visibleToOrm);
    }
}
```

Ví dụ giả định đầy đủ JUnit 5, Spring Boot Test, Spring JDBC, Testcontainers PostgreSQL dependencies và migrations đúng schema. Test cần import các classes tương ứng. `@SpringBootTest` không mặc định bọc test method trong một transaction rollback; các `TransactionTemplate` calls thể hiện transaction boundaries rõ.

Nếu datasource/routing/cache làm các lần đọc không độc lập, cần cấu hình cô lập fixture và session thích hợp. Không dùng DDL mẫu nếu production có schema khác.

### 46.1. Kiểm tra đúng indicator vật lý

Nếu cấu hình:

```java
@SoftDelete(
    strategy = SoftDeleteType.ACTIVE,
    columnName = "active_flag",
    converter = YesNoConverter.class)
```

thì test không được query `deleted BOOLEAN` nữa. Phải assert `active_flag = 'N'` sau remove và `'Y'` khi active.

## 47. Test các repository methods và bulk operations

Không chỉ test `delete(entity)`:

| Operation | Câu hỏi test |
|---|---|
| `save()` | Insert mới tạo indicator active? |
| `findById()` | Ẩn entity deleted? |
| `findAll()` | Không trả deleted rows? |
| Derived query `findByEmail` | Có visibility predicate? |
| `count()` | Đếm active rows hay toàn bảng? |
| `deleteById()` | Có đánh dấu mềm đúng? |
| `deleteAll()` | Lifecycle/cascade và SQL thế nào? |
| `deleteAllInBatch()` | Bulk semantics trên version đang dùng? |
| JPQL bulk `delete` | DML vật lý là UPDATE hay DELETE? |
| JPQL bulk `update` | Predicate deleted và cache state ra sao? |
| Native query | Có thể thấy deleted rows nếu không lọc? |
| JDBC/ETL writer | Có tuân thủ policy deleted không? |

Các phép thử này cần chạy trên **Hibernate/Spring Data versions thật**, vì code path của methods có thể khác với giả định từ một tutorial khác.

## 48. Test association và cascade behavior

Kịch bản đáng có:

```text
1. Tạo active Customer.
2. Tạo Invoice tham chiếu Customer.
3. Soft-delete Customer và commit.
4. Đọc Invoice trong Session mới.
5. Kiểm tra fetch Customer theo:
     - EntityManager.find
     - lazy association
     - join fetch
     - projection DTO
6. Assert hành vi phù hợp business contract.
```

Một test khác:

```text
1. Tạo Parent và Child có CascadeType.REMOVE.
2. Remove Parent.
3. Kiểm tra indicator Parent.
4. Kiểm tra Child row còn hay mất vật lý.
5. Kiểm tra FK và queries.
```

Không thể quyết định đúng cascade bằng cách chỉ nhìn annotation `@SoftDelete` trên Parent.

## 49. Test uniqueness, restore và migration

Những kịch bản:

| Tình huống | Điều phải xác nhận |
|---|---|
| Create account email X | Thành công khi chưa có active X |
| Delete account X | Row được giữ và ẩn |
| Create account email X lần nữa | Theo uniqueness policy |
| Restore account cũ khi X đã được tái sử dụng | Phát hiện conflict và xử lý đúng |
| Remove → add collection value giống trước | Không vi phạm unexpected unique key |
| Legacy row có NULL indicator | Migration backfill và visibility đúng |
| Đổi strategy DELETED → ACTIVE | Dữ liệu được đảo nghĩa chính xác |
| Dùng custom converter | SQL type/values mapping đúng |
| Rollback remove | Không tồn tại committed soft deletion |
| Concurrent remove/update | Không bị mất cập nhật/hồi sinh |

Đây đều là những lỗi chỉ xuất hiện khi có dữ liệu cũ, foreign keys hoặc traffic đồng thời; một test CRUD đơn giản thường không đủ.

## 50. Test trên DBMS đích thay vì chỉ H2

Một số lý do:

- Kiểu Boolean có thể được biểu diễn khác.
- Partial/filtered unique indexes là DBMS-specific.
- DDL default/nullability khác nhau.
- Foreign keys và cascade behavior có thể khác.
- SQL sinh từ dialect khác nhau.
- Locking, isolation và optimistic concurrency khác.
- Query planner lựa chọn index khác.

Nếu production dùng PostgreSQL, nên test tích hợp với PostgreSQL có migration thật. Nếu dùng MySQL, SQL Server hoặc Oracle, dùng đúng engine/major version được hỗ trợ. H2 có thể hữu ích cho một số unit tests nhưng không chứng minh migration/index/locking của production.

### 50.1. Dùng migration thật

```text
Start DBMS container
        |
        v
Apply Flyway/Liquibase migrations
        |
        v
Hibernate validates mapping
        |
        v
Seed active/deleted fixtures
        |
        v
Run JPA and raw SQL tests
        |
        v
Assert indicator, row counts,
uniqueness, FK and concurrency
```

Không chỉ để Hibernate tự `ddl-auto=create` trong integration tests nếu production schema do migration quản lý: như vậy có thể bỏ sót index/constraint quan trọng cho soft delete.

## 51. Tác động tới batch deletion và jobs

Một job xóa mềm hàng triệu rows có các lựa chọn:

- Duyệt entity và gọi `remove()`: giữ lifecycle/cascade ORM nhưng có thể tốn SELECT, memory và round trips.
- HQL bulk mutation: database xử lý theo predicate, nhưng cần kiểm chứng soft-delete semantics/version/callbacks.
- Native UPDATE `SET deleted=true`: hiệu năng dễ kiểm soát, nhưng bypass ORM lifecycle và cache synchronization.
- Partition/archive/purge strategy: có thể phù hợp dữ liệu rất lớn với retention dài.

Đừng chọn HQL/JDBC chỉ vì nhanh hơn nếu nó bỏ qua event, cascade hoặc audit bắt buộc.

Khi chạy job:

- Chia chunk theo key/cursor khi transaction lớn gây lock.
- Ghi checkpoint và idempotency key.
- Theo dõi affected rows và retries.
- Không gửi notification nhiều lần cho cùng logical delete.
- Giữ index phù hợp cho cả predicate xóa và truy vấn active sau đó.

## 52. Soft delete trong multi-service architecture

Giả sử Customer service soft-deletes một account nhưng Billing service có read model riêng. `@SoftDelete` trên Customer entity **không** tự:

- Gửi event tới Billing.
- Xóa cache của Billing.
- Đánh dấu xóa read model ở search index.
- Bảo đảm các API ngoài hệ thống không trả thông tin account.

Nếu cần đồng bộ downstream:

```text
Customer transaction
   |
   +-- soft-delete Customer
   +-- append AccountClosed outbox event
   |
   v
COMMIT
   |
   v
Outbox relay
   |
   +-- Billing consumer: adjust visibility
   +-- Search index consumer: remove index entry
   +-- Analytics consumer: update projection
```

Với outbox, event và domain update nên commit trong cùng local transaction. Consumers cần idempotent và có replay/reconciliation. Soft-delete ở ORM không có nghĩa toàn bộ distributed system đã nhất quán ngay lập tức.

## 53. Soft delete có phải phù hợp dữ liệu cá nhân?

Nếu một người dùng yêu cầu xóa dữ liệu theo chính sách privacy, đánh dấu `deleted=true` có thể **chưa đáp ứng** yêu cầu xóa thực sự. Dữ liệu vẫn tồn tại và có thể được đọc bằng SQL trực tiếp, backups hoặc audit tables.

Trước khi áp dụng soft delete cho PII:

- Xác định legal basis và retention.
- Phân biệt đóng tài khoản với yêu cầu xóa/anonymize.
- Xem dữ liệu nào phải giữ vì nghĩa vụ kế toán/pháp lý.
- Xác định thời hạn purge hoặc anonymization.
- Kiểm tra audit tables, replicas, backups và cache.
- Giới hạn quyền truy cập dữ liệu deleted.

Không biến soft delete thành một lời hứa pháp lý rằng dữ liệu đã bị xóa khỏi mọi hệ thống.

## 54. Một ví dụ thiết kế đầy đủ cho Account

Giả sử business contract:

1. User có thể đóng account.
2. Account bị ẩn khỏi API người dùng bình thường.
3. Billing records vẫn được giữ theo chính sách.
4. Email có thể tái sử dụng sau một khoảng thời gian nếu đủ điều kiện.
5. Admin được phép xem lịch sử đóng nhưng không dùng ORM thông thường để lách visibility.
6. Dữ liệu nhạy cảm được purge/anonymize sau retention period.

Mô hình:

```text
CustomerAccount (@SoftDelete)
   |
   +-- current account identity
   +-- soft-delete indicator
   |
   +-- AccountClosureEvent
   |     closedBy / closedAt / reason / requestKey
   |
   +-- BillingRecord (separate lifecycle)
   |     immutable billed snapshot
   |
   +-- OutboxEvent
         AccountClosed notification
```

Transaction đóng tài khoản:

```java
@Transactional
public void closeAccount(
        long accountId,
        String requestKey,
        String reason) {

    CustomerAccount account =
        accounts.findById(accountId).orElse(null);

    if (account == null) {
        return; // Ví dụ idempotent policy.
    }

    closureEvents.save(
        AccountClosureEvent.create(
            accountId, requestKey, reason));

    accounts.delete(account);

    outbox.save(
        OutboxEvent.accountClosed(
            accountId, requestKey));
}
```

Đây là thiết kế minh họa, giả định cả ba repositories dùng **cùng transaction resource** và những class/factory methods được ứng dụng hiện thực. Cần thêm authorization, request-key uniqueness và validation thực tế; một đoạn code chưa thể thay thế business workflow.

### 54.1. Hành vi đọc

```text
CustomerAccountRepository.findById(id)
   -> Không thấy sau khi soft deleted

InvoiceRepository.findByCustomerId(id)
   -> Vẫn có thể thấy chứng từ theo quyền

AdminClosureHistoryService
   -> Đọc closure event/DTO có authorization

RetentionPurgeJob
   -> Xóa/anonymize khi đủ điều kiện
```

Việc phân loại rõ dữ liệu active, dữ liệu lịch sử và dữ liệu báo cáo làm kiến trúc dễ hiểu hơn dùng một cờ `deleted` cho mọi nghiệp vụ.

## 55. Những sai lầm thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Không tìm thấy `@SoftDelete` | Hibernate version chưa hỗ trợ hoặc dependency sai | Kiểm tra Hibernate version/BOM |
| Soft delete rồi row biến mất vật lý | Entity/mapping/đường delete không dùng feature | Kiểm tra SQL, version, query path |
| Row deleted vẫn xuất hiện trong báo cáo native | Native SQL thiếu predicate | Viết visibility rule tường minh và kiểm tra quyền |
| `find()` trả null sau delete nhưng DB row còn | Đúng soft-delete semantics | Phân biệt ORM visibility và DB existence |
| Soft-deleted Customer khiến Order lỗi fetch | Association đến target bị ẩn | Kiểm thử fetch plan, snapshot read model |
| Child rows bị hard-delete | Cascade remove trên child không có @SoftDelete | Quyết định lifecycle từng entity |
| Insert trùng email thất bại sau soft delete | UNIQUE toàn bảng vẫn giữ row deleted | Chọn uniqueness policy/index phù hợp |
| Restore conflict | Email/slug đã tái sử dụng | Validate uniqueness và policy |
| Không thể thêm lại collection value | Unique constraint trên row đã soft-deleted | Thiết kế collection index/row identity |
| Chuyển ACTIVE/DELETED làm ẩn hết data | Không migrate semantics indicator | Backfill đúng và kiểm thử |
| Cột Boolean có NULL làm biến mất rows | Predicate 3-valued logic | Backfill, NOT NULL và default |
| Tăng version/callback không như kỳ vọng | Assumed soft-delete UPDATE giống ordinary update | Test generated SQL/lifecycle |
| Cache vẫn thấy object cũ | Native writer bypass invalidation | Evict/clear/synchronize cache |
| HQL bulk không giống `remove()` | Bulk mutation không theo per-entity lifecycle | Test/thiết kế semantics riêng |
| Admin không thể load deleted via repository | Built-in visibility rule | Admin-only SQL/read model có auth |
| DeletedAt không được ghi | @SoftDelete chỉ quản lý indicator | Thiết kế closure metadata riêng |
| API DELETE retry bị báo lỗi khó hiểu | Không có idempotency contract | Chọn 204/404 policy và event dedup |
| Bảng phình to | Không có retention/purge | Theo dõi bloat/storage, archive |
| Xóa tài khoản nhưng PII vẫn còn | Soft delete không phải erase | Thiết kế legal retention/anonymization |

## 56. Quy trình áp dụng @SoftDelete an toàn

**Bước 1 — Xác định phiên bản.** Kiểm tra Hibernate ORM runtime có hỗ trợ `@SoftDelete` và các strategy/mapping mà dự án cần.

**Bước 2 — Xác định lifecycle.** “Xóa” có nghĩa bị ẩn khỏi ORM, ngừng hoạt động, hay cần xóa dữ liệu thật? Không dùng soft delete cho mọi trạng thái nghiệp vụ.

**Bước 3 — Chọn strategy.** `DELETED` hay `ACTIVE`, tên cột và converter phù hợp với schema.

**Bước 4 — Quản lý schema.** Tạo indicator không null, default đúng, migration/backfill rows cũ và constraints.

**Bước 5 — Review unique constraints.** Email, slug, external ID và collection keys có thể không được tái sử dụng sau soft delete nếu index chưa đúng.

**Bước 6 — Review associations.** Parent/child cascade, `@ManyToOne` target deleted, `@OneToMany` orphan removal, collection table semantics.

**Bước 7 — Review các đường ghi/đọc.** Spring Data CRUD, HQL, Criteria, bulk mutations, native SQL, JDBC, external integrations.

**Bước 8 — Thiết kế admin/restore.** Đọc deleted rows bằng cơ chế có quyền, xử lý conflicts, version/cache và audit.

**Bước 9 — Thiết kế retention.** Soft delete, audit history, anonymization, purge và backup policies phải nhất quán.

**Bước 10 — Test trên DBMS đích.** Quan sát SQL thực, transaction, constraints, concurrency, association và repository methods.

## 57. Sơ đồ quyết định

```text
                     Cần "xóa" một bản ghi
                                 |
                                 v
                  Dữ liệu phải biến mất vật lý?
                       /                 \
                     CÓ                  KHÔNG
                     |                     |
                     v                     v
              Hard delete/purge      Còn cần truy cập
              theo retention         qua ORM bình thường?
                                       /         \
                                     CÓ          KHÔNG
                                     |             |
                                     v             v
                              Business status   Xóa mềm
                              (SUSPENDED...)    có phù hợp?
                                                /       \
                                               CÓ       KHÔNG
                                               |          |
                                               v          v
                                      Hibernate version  Mô hình
                                      có @SoftDelete?     lifecycle khác
                                           /     \
                                         CÓ      KHÔNG
                                         |         |
                                         v         v
                                  Dùng built-in  SQLDelete /
                                  @SoftDelete    filter cũ hoặc
                                  theo mapping   nâng version
                                         |
                                         v
                                 DDL + uniqueness + FK
                                         |
                                         v
                                 Test CRUD/cascade/bulk
                                         |
                                         v
                                Restore / retention / audit
```

## 58. Tổng kết

Trong các phiên bản Hibernate ORM có hỗ trợ (bắt đầu từ dòng **6.4**), `@SoftDelete` giúp mô tả chính sách xóa logic ngay trong mapping. Khi entity được xóa qua đường ORM phù hợp, Hibernate có thể thay một DELETE vật lý bằng thao tác đánh dấu indicator và tự đưa điều kiện loại bỏ deleted rows vào những truy vấn ORM được hỗ trợ. `SoftDeleteType.DELETED` coi giá trị logic true là đã xóa; `SoftDeleteType.ACTIVE` coi true là còn hoạt động. Tên cột và `AttributeConverter<Boolean,T>` có thể được cấu hình để khớp với schema.

Lợi ích lớn là giảm nhu cầu tự phối hợp `@SQLDelete` với các predicate như `@Where`/`@SQLRestriction`. Nhưng `@SoftDelete` không tự bảo vệ native SQL/JDBC, không thay thế authorization, audit history, dữ liệu lưu lâu dài hay xóa thật theo retention policy. Quan hệ, cascade, collection tables, optimistic locking, cache và bulk HQL cần được kiểm chứng theo **mapping và Hibernate version cụ thể**.

Hai quyết định schema đặc biệt quan trọng là **unique constraints** (vì row deleted vẫn tồn tại, key có thể bị chiếm) và **foreign-key/association semantics** (vì database còn tham chiếu tới row nhưng ORM có thể không cho tải). Khôi phục deleted data cần một workflow có quyền, kiểm tra conflict và đồng bộ cache, không chỉ đảo Boolean một cách tùy tiện.

**Nguyên tắc cần nhớ:** Xóa mềm là một chính sách vòng đời dữ liệu ở ORM; muốn nó an toàn và có thể vận hành lâu dài, phải kết hợp mapping đúng phiên bản với migration, truy vấn, bảo mật, retention và integration tests trên database đích.
