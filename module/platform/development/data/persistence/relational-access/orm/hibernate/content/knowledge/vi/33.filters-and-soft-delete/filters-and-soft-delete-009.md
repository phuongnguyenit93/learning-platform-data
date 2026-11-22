# Khôi phục, xóa vĩnh viễn và yêu cầu giữ lịch sử

**Xóa mềm (soft delete)** không xóa ngay một bản ghi khỏi database. Thay vào đó, ứng dụng đánh dấu bản ghi đã ngừng hoạt động, rồi những truy vấn nghiệp vụ thông thường không còn hiển thị nó. Cách làm này tạo cơ hội **khôi phục (restore/undelete)**, điều tra sự cố và tạm giữ dữ liệu trong một khoảng thời gian.

Tuy nhiên, “còn hàng trong database” không đồng nghĩa:

- Có thể khôi phục bằng `EntityManager.persist()` như một entity mới.
- Những khóa UNIQUE, foreign key và collection associations vẫn còn tương thích.
- Các truy vấn quản trị có thể nhìn thấy bản ghi bị ẩn bằng cùng repository thông thường.
- Hibernate cache và các nodes khác sẽ tự biết một hàng vừa được khôi phục bằng SQL ngoài ORM.
- Dữ liệu có thể được giữ mãi mà không cần quan tâm quyền riêng tư, thời hạn lưu trữ, legal hold hoặc yêu cầu xóa vĩnh viễn.
- Envers đã lưu đầy đủ lịch sử mọi thay đổi, kể cả bulk/native SQL.
- Xóa cứng khỏi bảng chính đồng nghĩa mọi thông tin nhận dạng cá nhân đã biến mất khỏi audit tables, backups, search indexes và external systems.

Vì vậy cần thiết kế rõ **vòng đời dữ liệu**:

```text
               CREATE
                 |
                 v
        +----------------+
        | ACTIVE         |
        | Đang sử dụng   |
        +----------------+
          |            ^
   soft delete          | restore
          |            |
          v            |
        +----------------+
        | SOFT_DELETED   |
        | Bị ẩn          |
        +----------------+
          |
          | hết retention + được phép purge
          v
        +----------------+
        | PURGED         |
        | Xóa vĩnh viễn  |
        +----------------+
```

Một số hệ thống có thêm `PENDING_DELETION`, `ARCHIVED`, `LEGAL_HOLD`, `ANONYMIZED`, `RESTORE_REQUESTED` hoặc `PURGE_FAILED`. Những trạng thái này không nhất thiết đều là cột của cùng một bảng, nhưng cần được diễn đạt trong domain, API và vận hành.

Bài học sẽ đi từ Hibernate `@SoftDelete`, bộ lọc `@SQLRestriction`/`@Filter`, cách khôi phục qua thao tác có kiểm soát, cách hard delete theo chính sách retention, giữ lịch sử Envers và dữ liệu audit, đến khóa ngoại, unique constraints, concurrency, multi-tenant security, cache, transactional outbox, migrations và integration tests.

## 1. Phân biệt các hành động nghiệp vụ

| Hành động | Ý định | Hàng trong bảng chính | Truy vấn thông thường | Có thể phục hồi? |
| --- | --- | --- | --- | --- |
| Deactivate | Tạm ngừng cho phép sử dụng | Còn | Có thể vẫn hiển thị tùy policy | Thường có |
| Soft delete | Ẩn khỏi nghiệp vụ đang hoạt động | Còn, được đánh dấu | Thường bị loại | Có thể, nếu đủ điều kiện |
| Archive | Chuyển sang lưu trữ ít truy cập | Còn hoặc được chuyển kho | Thường không hiện trong màn hình chính | Tùy chính sách |
| Anonymize | Loại/biến đổi dữ liệu nhận dạng | Có thể còn record không còn PII | Tùy | Không nhất thiết đảo ngược được |
| Hard delete / purge | Xóa vật lý dữ liệu thuộc phạm vi purge | Hàng đã bị DELETE | Không còn | Không bảo đảm, trừ backup theo policy |
| Legal hold | Tạm giữ không cho purge do yêu cầu hợp lệ | Thường còn hoặc lưu ở kho kiểm soát | Có thể bị ẩn | Theo quy trình |

**Soft delete là một trạng thái nhìn thấy của bản ghi, không phải một quyền được giữ dữ liệu vô thời hạn.** Một record bị ẩn vẫn cần được quản lý về security, retention, backup và trách nhiệm với dữ liệu.

### 1.1. “Restore” là thao tác miền nghiệp vụ, không phải SQL toggle tùy ý

Khi khôi phục đơn hàng, tài khoản hoặc tài liệu, ứng dụng có thể phải kiểm tra:

- Người yêu cầu có quyền restore không?
- Bản ghi có thực sự ở trạng thái soft-deleted không?
- Thời hạn cho phép khôi phục còn hiệu lực không?
- Customer/organization cha có còn hoạt động không?
- Unique key (email, slug, external ID) có bị người khác chiếm không?
- Các bản ghi con, liên kết và file có được khôi phục cùng không?
- Dữ liệu đã bị anonymize/purged một phần chưa?
- Có legal hold, fraud restriction hoặc compliance rule ngăn restore không?
- Các search indexes/caches/materialized views được đồng bộ khi nào?

Việc update một flag chỉ là một bước trong quy trình đó.

## 2. Ví dụ domain: Customer và Document

Ta giả định ứng dụng lưu khách hàng và tài liệu.

```sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    email VARCHAR(320) NOT NULL,
    display_name VARCHAR(120) NOT NULL,
    deleted BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at TIMESTAMP WITH TIME ZONE,
    version BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE TABLE documents (
    id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    title VARCHAR(255) NOT NULL,
    deleted BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at TIMESTAMP WITH TIME ZONE,
    version BIGINT NOT NULL DEFAULT 0,
    CONSTRAINT fk_documents_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers(id)
);
```

Đây là PostgreSQL-style DDL minh họa. Cột `deleted_at` có thể do ứng dụng quản lý riêng hoặc do một Hibernate soft-delete timestamp strategy phù hợp quản lý. **Không cấu hình hai cơ chế cùng ghi một indicator mà chưa có contract rõ ràng.**

Với PostgreSQL, nếu email chỉ cần duy nhất trong **các customer đang hoạt động**:

```sql
CREATE UNIQUE INDEX uk_customers_active_email
ON customers (tenant_id, lower(email))
WHERE deleted = FALSE;
```

Index này cho phép hai rows cùng email nếu ít nhất một row đã soft-deleted, nhưng chính điều đó tạo ra **xung đột khi restore**. Phần sau sẽ phân tích.

Trong mô hình multi-tenant này, mọi native SQL/admin job phải lọc `tenant_id` đúng. Không dựa riêng vào ID nếu policy/DB model cho phép ID trùng giữa tenants.

## 3. Hibernate `@SoftDelete`: cơ chế first-class

Hibernate ORM từ dòng 6.4 cung cấp annotation `org.hibernate.annotations.SoftDelete` cho soft deletion. Ví dụ sử dụng chiến lược cờ `deleted`:

```java
import jakarta.persistence.*;
import org.hibernate.annotations.SoftDelete;
import org.hibernate.annotations.SoftDeleteType;

@Entity
@Table(name = "customers")
@SoftDelete(
    strategy = SoftDeleteType.DELETED,
    columnName = "deleted"
)
public class Customer {

    @Id
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private Long tenantId;

    @Column(nullable = false, length = 320)
    private String email;

    @Column(name = "display_name", nullable = false)
    private String displayName;

    @Version
    private long version;

    protected Customer() {}

    public Long getId() { return id; }
}
```

Khi ứng dụng gọi `em.remove(customer)` trên entity được quản lý, Hibernate với mapping `@SoftDelete` xử lý soft-delete semantics thay vì xóa vật lý row entity theo luồng bình thường.

Về ý tưởng, SQL sẽ giống:

```sql
UPDATE customers
SET deleted = TRUE
WHERE id = ? AND deleted = FALSE;
```

**Đây là SQL mô phỏng**, không phải một lời hứa về câu SQL chính xác. Hibernate có thể bổ sung predicates/version/tenant handling hoặc dùng cú pháp khác theo mapping, dialect và version.

Các truy vấn Hibernate thông thường tới entity này được cấu hình để không trả những rows đã đánh dấu deleted.

### 3.1. `SoftDeleteType.DELETED` và `SoftDeleteType.ACTIVE`

| Strategy | Ý nghĩa `true` | Ý nghĩa `false` | Tên cột mặc định thường dùng |
| --- | --- | --- | --- |
| `DELETED` | Đã xóa | Còn hoạt động | `deleted` |
| `ACTIVE` | Còn hoạt động | Đã xóa | `active` |

Ví dụ:

```java
@SoftDelete(
    strategy = SoftDeleteType.ACTIVE,
    columnName = "active"
)
@Entity
public class Account {
    // ...
}
```

Không đảo ngược boolean tùy hứng. Nếu schema legacy có `is_active = 1`, dùng ACTIVE strategy/converter thích hợp thay vì coi đó là DELETED flag.

### 3.2. Converter và SQL type

Có thể khai báo converter:

```java
@SoftDelete(
    columnName = "deleted",
    converter = org.hibernate.type.YesNoConverter.class
)
```

Converter ở đây biểu diễn boolean soft-delete indicator thành `'Y'`/`'N'` theo Hibernate/JPA converter, không phải chỗ để nhét logic kiểm tra quyền hoặc thời hạn lưu trữ.

Nếu DB column là `CHAR(1)`, DDL/constraints cần khớp converter; nếu DB dùng native boolean thì không cần converter.

## 4. Timestamp strategy ở các Hibernate versions mới

Hibernate ORM 7.1+ có `SoftDeleteType.TIMESTAMP` cho soft-delete marker dạng thời điểm:

```java
@SoftDelete(
    strategy = SoftDeleteType.TIMESTAMP,
    columnName = "deleted_at"
)
@Entity
@Table(name = "customers")
public class Customer {
    // ...
}
```

Theo chiến lược này, khái niệm thường là:

- `deleted_at IS NULL`: đang hoạt động.
- `deleted_at IS NOT NULL`: đã xóa mềm, với thời điểm xóa.

Điểm lợi: cùng một indicator cho biết **cả trạng thái và thời điểm**, hữu ích khi xác định các candidates đến hạn purge.

### 4.1. Không dùng boolean converter với TIMESTAMP

Javadoc Hibernate nói `converter` chỉ hợp lệ với `DELETED` hoặc `ACTIVE`; kết hợp converter với `TIMESTAMP` không được hỗ trợ.

Do đó, ví dụ sau **không hợp lệ** theo contract:

```java
@SoftDelete(
    strategy = SoftDeleteType.TIMESTAMP,
    converter = YesNoConverter.class
)
```

### 4.2. Phạm vi phiên bản

`@SoftDelete` đã có trong Hibernate 6.4, nhưng **không giả định mọi 6.x có TIMESTAMP strategy**. Cần kiểm tra `SoftDeleteType` Javadoc của đúng version.

Nếu đang ở Hibernate 6.4/6.5 và muốn `deleted_at`, có thể chọn cơ chế manual soft-delete hoặc bảng tombstone riêng thay vì copy annotation TIMESTAMP từ Hibernate mới rồi gặp compile error.

### 4.3. Nguồn timestamp phải thống nhất

Nếu thời điểm xóa dùng để bắt đầu retention, cần xác định:

- Timestamp lấy từ DB clock hay application clock?
- Timezone/precision của cột.
- Time of user request, time of transaction commit hay time of SQL execution?
- Nếu transaction rollback, timestamp có tồn tại không?
- Có đồng nhất với các timestamps trong audit/outbox không?

Không suy `deleted_at` nhất thiết đúng chính xác thời gian commit đến từng microsecond nếu implementation không cam kết điều đó.

## 5. Cách làm legacy: cờ deleted và SQL restriction

Một số dự án đã triển khai trước khi `@SoftDelete` xuất hiện:

```java
import org.hibernate.annotations.SQLDelete;
import org.hibernate.annotations.SQLRestriction;

@Entity
@Table(name = "customers")
@SQLDelete(sql = """
    UPDATE customers
    SET deleted = TRUE
    WHERE id = ?
    """)
@SQLRestriction("deleted = FALSE")
public class Customer {
    @Id
    private Long id;

    // ...
}
```

Ở đây:

- `@SQLDelete` thay SQL DELETE Hibernate sinh trong một số đường ORM remove bằng SQL UPDATE.
- `@SQLRestriction` chèn predicate cố định để ẩn rows đã xóa khi load phù hợp.
- `@SQLRestriction` là một biểu thức SQL cố định, **không bật/tắt theo admin request**.
- Custom SQL `@SQLDelete` đòi hỏi bind parameter/identifier/version ordering phù hợp mapping/provider; đoạn trên chỉ là mẫu cho entity đơn giản và không thể sao chép nguyên xi cho composite ID/@Version.

**Không gắn đồng thời `@SoftDelete` first-class và custom `@SQLDelete` cho cùng entity khi chưa hiểu interaction**; chọn một cơ chế sở hữu delete semantics.

### 5.1. Legacy SQL delete dễ sai với optimistic locking

Nếu entity có `@Version`, custom `@SQLDelete(sql=...)` phải xử lý version column và parameter positions đúng theo Hibernate version. Một SQL thiếu version check có thể xóa mềm row đã được transaction khác sửa mà không phát hiện conflict.

Dùng built-in `@SoftDelete` khi phù hợp, hoặc viết integration test xác minh stale version không thể xóa nhầm.

## 6. `@Filter` và `@SQLRestriction` có cùng công dụng không?

Không.

`@SQLRestriction` áp SQL predicate tĩnh và không thể disable theo request:

```java
@SQLRestriction("deleted = false")
```

Hibernate `@Filter` có thể bật/tắt trong Session và nhận parameters theo mapping:

```java
@FilterDef(name = "tenantVisibility")
@Filter(
    name = "tenantVisibility",
    condition = "tenant_id = :tenantId"
)
```

Phần khai báo tham số trong `@FilterDef` cần viết đúng theo Hibernate version, ví dụ `@ParamDef(name="tenantId", type=Long.class)` ở các phiên bản hiện đại.

Một ví dụ kết hợp tenant filter và deleted filter cần test kỹ với:
- Load by identifier (`find/getReference`).
- Eager/lazy to-one associations.
- Collection initialization.
- Native queries.
- Current Persistence Context.
- Query cache.

Không giả định mọi version Hibernate luôn áp filters giống nhau cho mọi load path. Không dùng toggle filter như một cơ chế authorization duy nhất.

### 6.1. Khi nào cần admin thấy cả deleted rows?

Nếu dùng `@SoftDelete` hoặc `@SQLRestriction` tĩnh, một repository/entity query thông thường không được thiết kế như một “includeDeleted=true” toggle dễ dàng.

Các hướng phù hợp hơn:

- Một native SQL/admin JDBC repository có truy vấn và authorization tường minh.
- Một read-only projection/DTO từ bảng thực cho chức năng quản trị.
- Một persistence model riêng có visibility rules được thiết kế rõ.
- Một database view dùng cho màn hình quản trị và được bảo vệ.
- Một dynamic filter design từ đầu, nếu support/admin toggle là use case chủ đạo, sau khi kiểm thử mọi load path.

Đừng cố disable một predicate tĩnh bằng cách `session.disableFilter("deleted")` nếu predicate đó đến từ `@SQLRestriction` hoặc built-in `@SoftDelete`, vì chúng không phải một dynamic filter cùng tên.

## 7. `EntityManager.remove()` không phải API khôi phục

Luồng Hibernate:

```java
Customer customer = em.find(Customer.class, 42L);

em.remove(customer);
em.flush();
```

Với `@SoftDelete`, row có thể còn trong DB với marker deleted, nhưng ở ORM level entity đã đi qua lifecycle remove.

Sau commit, các thao tác:

```java
em.find(Customer.class, 42L);
```

trong một EntityManager mới thông thường **không nhìn thấy** row bị soft-deleted.

Không có một JPA API chuẩn kiểu:

```java
em.restore(customer); // Không tồn tại trong EntityManager chuẩn.
```

Và thao tác:

```java
em.persist(customer);
```

trên một object đã có ID không phải một công cụ undelete. Nó có thể bị coi là detached, bị từ chối, hoặc cố INSERT trùng primary key tùy lifecycle/config.

### 7.1. Vì sao restore khó hơn soft delete?

ORM `remove()` đã chuyển object lifecycle sang removed; entity không còn được các normal entity queries nhìn thấy. Để phục hồi bạn cần một đường truy cập **dữ liệu bị ẩn**, xác minh điều kiện nghiệp vụ rồi thực hiện UPDATE.

Không nên đơn giản dựng một entity mới có cùng primary key và `merge()`, vì:
- Row vật lý có thể vẫn tồn tại.
- Mapping soft-delete lọc row đó khỏi load.
- `merge()` có thể cố insert hoặc ném exception theo provider behavior.
- Cascades có thể làm thay đổi graph không dự kiến.
- Query/collection cache và version chưa được xử lý.

Hãy thiết kế thao tác restore tường minh thay vì dựa vào state transitions ngầm của ORM.

## 8. Khôi phục bằng UPDATE có điều kiện

Với schema boolean `deleted` và `@Version`, một restore command có thể là native SQL:

```sql
UPDATE customers
SET deleted = FALSE,
    deleted_at = NULL,
    version = version + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE id = :id
  AND tenant_id = :tenantId
  AND deleted = TRUE
  AND version = :expectedVersion;
```

Nếu affected row count = 1, restore đã cập nhật DB row trong transaction hiện tại.

Nếu count = 0, có thể do:
- Không tồn tại row.
- Sai tenant.
- Row chưa bị xóa mềm.
- Version stale.
- Row đã purge.
- Ràng buộc/row-level security ngăn update.

**Không suy ra một nguyên nhân duy nhất chỉ từ `0`**. API có thể trả kết quả bảo mật trung tính `NOT_FOUND_OR_CONFLICT`, rồi chỉ internal audit log mới ghi chi tiết phù hợp.

### 8.1. Code mẫu với JDBC

Đường quản trị có thể dùng JDBC tường minh:

```java
import javax.sql.DataSource;
import java.sql.*;
import java.util.Objects;

public final class CustomerRestoreDao {

    private final DataSource dataSource;

    public CustomerRestoreDao(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource);
    }

    public boolean restore(
            long tenantId,
            long customerId,
            long expectedVersion
    ) throws SQLException {
        String sql = """
            UPDATE customers
            SET deleted = FALSE,
                deleted_at = NULL,
                version = version + 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
              AND tenant_id = ?
              AND deleted = TRUE
              AND version = ?
            """;

        try (Connection connection = dataSource.getConnection();
             PreparedStatement ps =
                 connection.prepareStatement(sql)) {

            ps.setLong(1, customerId);
            ps.setLong(2, tenantId);
            ps.setLong(3, expectedVersion);

            return ps.executeUpdate() == 1;
        }
    }
}
```

Đây là **DAO minh họa phần SQL**, không phải toàn bộ restore service production: transaction manager, permissions, cache invalidation và domain checks phải được thiết kế bên ngoài.

Trong Spring-managed transaction, thường nên dùng `JdbcTemplate`/`NamedParameterJdbcTemplate` gắn cùng `DataSource` và transaction manager để đảm bảo UPDATE cùng transaction với audit/outbox. Đoạn sử dụng `dataSource.getConnection()` trực tiếp không tự đảm bảo cùng transaction Spring/JPA nếu hệ thống chưa tích hợp quản lý connection thích hợp.

### 8.2. Timestamp strategy

Nếu dùng `@SoftDelete(strategy=TIMESTAMP, columnName="deleted_at")`, update sẽ tập trung vào:

```sql
UPDATE customers
SET deleted_at = NULL,
    version = version + 1
WHERE id = :id
  AND tenant_id = :tenantId
  AND deleted_at IS NOT NULL
  AND version = :expectedVersion;
```

Ví dụ boolean và timestamp ở hai phần **không nên được áp máy móc cùng lúc**. Chọn một indicator semantics cho entity thực tế.

## 9. Kiểm tra điều kiện trước khi restore

Một workflow đáng tin cậy:

```text
RESTORE request
      |
      v
Authorize actor + tenant
      |
      v
Load deleted row qua admin access path
      |
      v
Check deleted state, age, legal holds, purge status
      |
      v
Check parent/children + unique conflicts
      |
      v
Conditional UPDATE in transaction
      |
      v
Write audit/outbox event in same transaction
      |
      v
COMMIT
      |
      v
Invalidate/reindex/publish
```

Không chỉ chạy:

```sql
UPDATE customers SET deleted = false WHERE id = ?;
```

vì bỏ qua tenant, version, authorization và concurrency.

### 9.1. Validate trong transaction không thay unique constraints

Một service có thể check:

```sql
SELECT COUNT(*)
FROM customers
WHERE tenant_id = ?
  AND lower(email) = lower(?)
  AND deleted = false;
```

rồi cho restore. Nhưng concurrent transaction khác có thể INSERT cùng email ngay sau check.

Database UNIQUE index vẫn phải đóng vai trò bảo vệ cuối cùng. Service bắt unique violation và trả conflict phù hợp, không gán responsibility chỉ cho pre-check.

## 10. Unique constraint khi một bản ghi được khôi phục

Giả sử:

```text
Customer#42: email=an@example.org, deleted=true
Customer#99: email=an@example.org, deleted=false
```

Với partial unique index:

```sql
CREATE UNIQUE INDEX uk_active_email
ON customers (tenant_id, lower(email))
WHERE deleted = FALSE;
```

Cả hai row đang cùng tồn tại hợp lệ. Nhưng:

```sql
UPDATE customers SET deleted = FALSE WHERE id = 42;
```

sẽ vi phạm uniqueness.

Một restore API phải có policy rõ:
- Từ chối restore và yêu cầu đổi email trước.
- Restore ở trạng thái `PENDING_REVIEW`, chưa kích hoạt identity/email cũ.
- Chuyển conflict sang manual resolution.
- Cấp email mới sau xác minh ownership.
- Không merge hai customer identities tự động.

### 10.1. Global unique có đánh đổi khác

Nếu database dùng:

```sql
UNIQUE (tenant_id, email)
```

bao gồm cả deleted rows, email của bản ghi đã xóa không thể được tái sử dụng. Điều này hỗ trợ restore đơn giản hơn nhưng có thể không phù hợp sản phẩm cho phép đăng ký lại email.

Không có lựa chọn luôn đúng; hãy xác định nghĩa business của “xóa” và “tái sử dụng identity”.

### 10.2. Unique composite với deleted flag chưa chắc đúng

Thiết kế:

```sql
UNIQUE (tenant_id, email, deleted)
```

chỉ cho phép tối đa **một** bản ghi deleted có cùng email. Nếu lịch sử có nhiều lần tạo/xóa cùng email, constraint này có thể không đáp ứng.

Partial unique index cho active rows thường diễn đạt intent rõ hơn trên PostgreSQL. Với DBMS khác, có thể cần generated column, functional index hoặc pattern tương ứng.

## 11. Cạnh tranh giữa restore, delete và update

Hai requests:

```text
T1: restore Customer#42
T2: purge Customer#42
```

Hoặc:

```text
T1: restore Customer#42
T2: rename Customer#42 / change email
```

Nếu các SQL thiếu điều kiện trạng thái/version, transaction kết thúc sau có thể ghi đè ý nghĩa thao tác trước.

Một conditional restore:

```sql
UPDATE customers
SET deleted = FALSE, version = version + 1
WHERE id = :id
  AND deleted = TRUE
  AND version = :expectedVersion;
```

mang tính **compare-and-set**. Kết quả affected count giúp phát hiện xung đột.

Purge cũng nên dùng state/retention/hold conditions trong cùng transaction, thay vì chỉ check trước rồi DELETE vô điều kiện.

### 11.1. Pessimistic locking có phù hợp?

Có thể dùng `SELECT ... FOR UPDATE` trên row bị ẩn qua native SQL/admin repository khi cần serialize restore/purge quyết định phức tạp. Nhưng:
- Query phải lock đúng DB row và transaction.
- Không giữ lock trong thời gian gọi network service.
- Deadlock/timeout vẫn có thể xảy ra.
- Lock không thay DB unique constraints.

Nếu workflow đơn giản, conditional UPDATE + unique index + optimistic version thường đủ và dễ mở rộng hơn.

## 12. Persistence Context và cache sau restore

Một request có thể đã load Customer trước khi người khác soft delete/restore. `EntityManager` giữ identity map (L1) cho entity đang managed.

Nếu restore bằng native/JDBC SQL:

```java
jdbcTemplate.update("UPDATE customers SET deleted = FALSE ...");
```

Hibernate **không tự gọi entity lifecycle setters/dirty checking** cho object đã load, và một EntityManager cũ có thể giữ state không đúng với database mới.

Sau khi thao tác hoàn tất:
- Với context còn pending changes, quyết định flush trước clear.
- `em.clear()` detach managed entities trong **context đó**.
- `em.refresh()` chỉ dùng khi entity có thể load hợp lệ và semantics phù hợp.
- Đóng/mở EntityManager mới giúp tách identity map.
- Cache cấp hai và query cache cần được xem xét riêng.

### 12.1. `Cache.evict` theo ID

Với Hibernate L2 caching:

```java
EntityManagerFactory emf = ...;

emf.getCache().evict(Customer.class, customerId);
```

Evict theo ID hẹp hơn `emf.getCache().evictAll()`.

Nếu documents/collections có cache association membership hoặc query cache kết quả đếm customers active, cần invalidation đúng dependencies.

Một native SQL đi qua Hibernate có thể kích hoạt broad invalidation/synchronized query-space logic tùy API/version. JDBC từ process khác **không tự báo Hibernate**. Không giả định một API xóa một entity key đã giải quyết toàn bộ search cache/HTTP cache/distributed nodes.

### 12.2. Tác động multi-node

Node A restore row và evict L2 local. Node B vẫn có local cached result cũ nếu không có invalidation propagation. Dùng shared coherent cache, event fanout hoặc TTL hợp lý, và kiểm thử read-after-write theo consistency policy.

### 12.3. Đừng gọi `clear()` để che transaction lỗi

Nếu SQL restore thất bại vì unique constraint, transaction có thể không còn tiếp tục an toàn. Rollback/discard context, sau đó xử lý conflict trong transaction mới. `clear()` không “sửa” transaction lỗi.

## 13. Dynamic filter và khôi phục ở tầng truy vấn

Một số ứng dụng dùng manual `deleted` flag với Hibernate `@Filter`, cho phép admin Session bật điều kiện khi cần:

```java
Session session = em.unwrap(Session.class);
session.enableFilter("activeOnly");
```

và:

```java
session.disableFilter("activeOnly");
```

Nhưng cần tách:
- User query: chỉ active.
- Admin query: có thể include deleted theo quyền.
- Write path: phải tôn trọng lifecycle/constraints.
- Security: tenant/role filter không được người dùng tùy ý tắt.

### 13.1. Không bật/tắt filter trên Session dùng chung bất cẩn

Nếu một request admin disable filter rồi reuse một Session lâu dài cho request user, dữ liệu deleted có thể rò ra.

Trong ứng dụng web, mỗi unit of work nên có session/context lifecycle riêng với policy thiết lập rõ. Không giữ state filter trong shared Session giữa threads: Hibernate Session không thread-safe.

### 13.2. Truy vấn native SQL thường không tự thừa hưởng filter

Ví dụ:

```sql
SELECT * FROM customers WHERE tenant_id = :tenantId;
```

không có `deleted = FALSE`, nên native SQL có thể trả deleted rows dù JPQL entity queries đang ẩn chúng.

Nếu native SQL được dùng trong public read path, phải viết predicate/permission rõ ràng. Không coi `@SoftDelete` là database row-level security policy cho tất cả clients.

## 14. Hard delete/purge là nghiệp vụ khác với remove

Với entity có `@SoftDelete`:

```java
em.remove(customer);
```

được thiết kế để **soft delete**, không phải phương tiện xóa vật lý.

Để purge cần đường quản trị riêng, thường là SQL/JDBC:

```sql
DELETE FROM customers
WHERE id = :id
  AND tenant_id = :tenantId
  AND deleted = TRUE;
```

Nhưng ví dụ trên **chưa đủ cho production**. Nó chưa xét:
- Thời gian retention.
- Legal hold.
- FK constraints.
- Audit/outbox.
- File/blob attachments và external search indexes.
- Transaction/version.
- Batch limits và khóa.
- Khả năng retry/idempotency.
- Audit history retention.
- Backups và replicas.

### 14.1. “Xóa vĩnh viễn” là phạm vi, không phải một câu SQL

Cần định nghĩa rõ một purge gồm:
1. Live entity row.
2. Children và join tables.
3. Audit/history rows nếu policy yêu cầu.
4. File/object storage.
5. Search indexes/cache/materialized views.
6. Export snapshots và analytics datasets.
7. Message/event payloads chứa PII.
8. Backups theo retention/expiry policy.
9. Tài khoản khác của cùng người dùng nếu có.
10. Evidence log không chứa dữ liệu bị cấm giữ.

Không thể khẳng định đã xóa dữ liệu khỏi **mọi nơi** chỉ vì `DELETE FROM customers` trả affected count 1.

## 15. Retention policy: giữ bao lâu và vì sao?

Một policy có thể khác theo loại dữ liệu:

| Loại dữ liệu | Sau soft delete | Sau hết retention | Ghi chú |
| --- | --- | --- | --- |
| User profile | Ẩn khỏi public reads | Có thể purge/anonymize | Tùy pháp luật, hợp đồng, mục đích |
| Invoice/financial ledger | Không cho chỉnh tùy ý | Có thể phải giữ theo nghĩa vụ | Không đồng nhất với profile |
| Temporary export | Xóa khỏi UI | Xóa blob sớm | Có thể có TTL riêng |
| Security logs | Retain tối thiểu cần thiết | Xóa/anonymize theo policy | Tránh lưu secrets |
| Reference data | Inactive/soft-deleted | Thường khó purge vì FK/history | Cần domain review |
| Audit revisions | Giữ theo requirement | Purge/partition/archive có kiểm soát | Không mặc định tồn tại vĩnh viễn |

Đừng tự đặt con số retention vì “Hibernate hỗ trợ xóa mềm”. Các mốc thời gian phải đến từ chính sách được phê duyệt, yêu cầu pháp lý/contract và risk assessment của tổ chức.

### 15.1. Phân biệt thời điểm bắt đầu tính retention

Có thể tính từ:
- `deleted_at`.
- Ngày account được đóng chính thức.
- Ngày hợp đồng kết thúc.
- Ngày hoạt động tài chính cuối.
- Ngày legal hold hết hiệu lực.
- Một sự kiện nghiệp vụ khác được policy chỉ định.

Không dùng `updated_at` làm mốc purge chung: các cập nhật kỹ thuật không liên quan deletion có thể làm thay đổi thời hạn theo cách sai.

### 15.2. Retention không phải đồng nghĩa “cho phép restore”

Có thể một bản ghi đang trong thời gian phải lưu vì pháp lý nhưng **không được khôi phục** thành tài khoản hoạt động. `retained=true` và `restorable=true` là hai quyết định riêng.

## 16. Legal hold: không purge khi có yêu cầu giữ hợp lệ

Một mô hình đơn giản:

```sql
CREATE TABLE data_holds (
    id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    subject_type VARCHAR(60) NOT NULL,
    subject_id BIGINT NOT NULL,
    hold_reason VARCHAR(200) NOT NULL,
    released_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL
);
```

Tình trạng hold đang hiệu lực nếu `released_at IS NULL`.

Một purge service phải kiểm tra hold trong cùng consistency boundary với DELETE. Nhưng chỉ check:

```sql
SELECT ...
-- không có hold
DELETE ...
```

vẫn có race nếu một transaction khác thêm hold giữa hai bước.

### 16.1. Giải quyết race với legal hold

Các lựa chọn:
- Serialize hold-setting và purge qua lock trên **một parent/control row** ổn định.
- Dùng DB constraints/triggers phù hợp để chặn purge khi hold active.
- Dùng một control table và transaction protocol chung.
- Sử dụng conditional DELETE trong transaction kết hợp locking/isolation thích hợp.
- Có một delete queue và một quyền final approval.

Cần kiểm thử race thật giữa đặt hold và purge, không chỉ test một request đơn lẻ.

**Không tuyên bố an toàn chỉ vì có câu `NOT EXISTS`** nếu workflow khác có thể đồng thời thêm hold mà không dùng giao thức khóa/transaction tương thích.

## 17. Purge chỉ những bản ghi đủ điều kiện

Một query để **liệt kê** candidates:

```sql
SELECT c.id, c.tenant_id
FROM customers c
WHERE c.deleted = TRUE
  AND c.deleted_at < :cutoff
  AND NOT EXISTS (
      SELECT 1
      FROM data_holds h
      WHERE h.subject_type = 'CUSTOMER'
        AND h.subject_id = c.id
        AND h.tenant_id = c.tenant_id
        AND h.released_at IS NULL
  )
ORDER BY c.deleted_at, c.id
LIMIT :batchSize;
```

Đây là PostgreSQL-style SQL với parameters của ứng dụng.

Lưu ý:
- `deleted_at` không được null với các rows sẽ purge.
- `:cutoff` được tính từ policy, không phải một giá trị hard-coded tùy hứng.
- Cần xác định subject type/tenant/hold scope đúng.
- Candidates có thể thay đổi giữa `SELECT` và `DELETE`.
- Không dùng `LIMIT` trong một DELETE lớn khi DBMS/dialect không hỗ trợ cú pháp trực tiếp.

### 17.1. Điều kiện phải được kiểm tra lại lúc DELETE

Sau khi chọn candidates, lệnh DELETE cho từng ID/chunk nên nhắc lại các điều kiện quan trọng:

```sql
DELETE FROM customers c
WHERE c.id = :id
  AND c.tenant_id = :tenantId
  AND c.deleted = TRUE
  AND c.deleted_at < :cutoff
  AND NOT EXISTS (
      SELECT 1
      FROM data_holds h
      WHERE h.subject_type = 'CUSTOMER'
        AND h.subject_id = c.id
        AND h.tenant_id = c.tenant_id
        AND h.released_at IS NULL
  );
```

Tuy nhiên, như đã nêu, để chống race với writer tạo hold vẫn cần transaction/locking protocol phù hợp.

### 17.2. Keyset pagination cho purge jobs

Nếu bảng có nhiều deleted rows và job vừa đọc vừa xóa, tránh dùng OFFSET tăng dần trên tập đang co lại. Có thể quét theo `(deleted_at, id)` hoặc ID ổn định tùy index:

```sql
WHERE deleted = true
  AND deleted_at < :cutoff
  AND id > :lastProcessedId
ORDER BY id
LIMIT :batchSize
```

Cần xử lý concurrent changes và checkpoint/idempotency. Nếu ID không phản ánh thứ tự đủ ổn định hoặc nhiều tenants, dùng keyset tuple `(tenant_id, id)`/composite key phù hợp.

## 18. Xóa theo chunk thay vì một transaction khổng lồ

Một câu:

```sql
DELETE FROM customers WHERE deleted = TRUE;
```

có thể:
- Chạy lâu và giữ transaction resources.
- Gây lock waits.
- Tạo WAL/redo/undo lớn.
- Kích hoạt FK cascade ngoài dự kiến.
- Làm tăng replication lag.
- Khó xác định chính xác row nào cần giữ.
- Xóa cả những rows chưa hết retention.

Purge worker nên:
1. Chọn lô nhỏ có điều kiện eligibility.
2. Lock/reserve công việc nếu nhiều workers.
3. Xóa children/attachments theo dependency policy.
4. Delete parent có conditions.
5. Ghi event/receipt trong transaction thích hợp.
6. Commit.
7. Checkpoint và retry idempotently.
8. Quan sát lock/DB load/error rate.

### 18.1. Commit từng chunk có đánh đổi

Nếu chunk 1 đã commit và chunk 2 thất bại, chunk 1 vẫn bị xóa vật lý. Đây là **partial success** được thiết kế, không phải atomic all-or-nothing.

Phải có job state/idempotency và khả năng tiếp tục thay vì chạy lại mọi công việc mà không phân biệt.

## 19. Foreign keys: parent bị xóa mềm còn child thế nào?

Giả sử:

```text
Customer#42
  ├── Document#101 (active)
  ├── Document#102 (soft-deleted)
  └── Document#103 (active)
```

Soft delete Customer#42 không xóa row, nên FK từ Document vẫn có target vật lý. Nhưng **nghiệp vụ có thể muốn các documents bị ẩn theo customer**.

Có hai mô hình:

**Mô hình A — Cascade soft-delete riêng**
- Khi customer bị xóa mềm, service cũng đánh dấu từng document.
- Restore có thể quyết định những documents nào cần phục hồi.
- Cần ghi rõ *lý do* document bị xóa để tránh hồi sinh document bị xóa độc lập trước đó.

**Mô hình B — Visibility phụ thuộc parent**
- Document vẫn active ở DB nhưng public query chỉ trả nếu customer cũng active.
- Restore customer có thể làm document hiện lại mà không update child.
- Tránh ghi nhiều rows, nhưng mọi read path phải áp điều kiện parent visibility và tenant đúng.

Không thể chọn một mô hình chỉ bằng việc đặt `cascade = CascadeType.REMOVE`. Cascade ORM thuộc lifecycle remove, còn visibility ở tầng business phải được thiết kế rõ.

### 19.1. Restore parent không nên tự restore mọi child

Giả sử Document#102 đã bị user xóa độc lập trước khi customer bị soft-delete. Nếu khôi phục customer rồi update tất cả `documents SET deleted=false WHERE customer_id=42`, Document#102 bất ngờ xuất hiện trở lại.

Cần biết `deletion_reason`, `deleted_by_operation_id` hoặc một event history đủ để phân biệt:
- Soft delete child do parent.
- Soft delete child do yêu cầu riêng.
- Child bị purge/anonymize.
- Child không còn hợp lệ theo policy.

Một restoration plan phải dựa trên nguồn thông tin này thay vì blind cascade.

## 20. Xóa vĩnh viễn parent và FK dependencies

Hard delete Customer có thể bị FK chặn vì Documents vẫn tham chiếu.

Các lựa chọn:

| Cách | Khi phù hợp | Đánh đổi |
| --- | --- | --- |
| RESTRICT / NO ACTION | Cần bảo vệ child data | Parent không purge nếu còn child |
| ON DELETE CASCADE | Child hoàn toàn sở hữu bởi parent, có policy delete tương ứng | Xóa dây chuyền, cần audit/retention |
| ON DELETE SET NULL | Child được giữ độc lập và FK nullable | Mất liên kết trực tiếp |
| Xóa child trước rồi parent | Có pipeline kiểm soát dependencies | Nhiều SQL/transactions, phải đúng thứ tự |
| Anonymize parent giữ ID | Cần giữ ledger/historical reference | Không phải hard delete hoàn toàn |
| Archive immutable snapshot | Phải giữ chứng từ, tách PII không cần | Thêm lưu trữ/retention policy |

**Một FK `ON DELETE CASCADE` không tự tạo Envers revision cho từng child** khi database xóa trực tiếp ngoài Hibernate lifecycle.

Không bật cascade vật lý để né một `ConstraintViolationException` mà chưa đánh giá dữ liệu lịch sử/retention cần giữ.

## 21. Soft delete trên join table và collection

Hibernate `@SoftDelete` hỗ trợ entities và một số mapping collection, chẳng hạn các rows của `@ElementCollection` hoặc `@ManyToMany` table theo annotation target/version.

Ví dụ ý tưởng:

```java
@ElementCollection
@CollectionTable(
    name = "customer_tags",
    joinColumns = @JoinColumn(name = "customer_id")
)
@SoftDelete(columnName = "deleted")
private Set<String> tags;
```

Với collection table, soft delete có thể áp cho **rows liên kết/collection elements**, không phải toàn bộ entity Customer.

### 21.1. `@OneToMany` không đồng nghĩa join table

Trong `@OneToMany(mappedBy="customer")`, child là entity riêng. Nếu muốn child có lifecycle soft delete riêng, cần thiết kế mapping/policy ở child; không mặc định đặt `@SoftDelete` lên `@OneToMany` có cùng semantics với `@ManyToMany` join rows.

### 21.2. Khôi phục collection membership phức tạp hơn entity row

Nếu một relation `customer_tags` đã bị soft-deleted, thêm lại cùng tag có thể:
- Cố tạo row mới.
- Vi phạm unique key của link.
- Không hồi sinh row cũ.
- Tạo nhiều rows mang cùng logical association ở các trạng thái khác nhau.

Cần test mapping cụ thể khi muốn restore collection membership. Với lịch sử liên kết quan trọng, một join entity tường minh (`CustomerTagAssignment`) với ID/status/reason/timestamps có thể dễ quản lý hơn implicit many-to-many.

## 22. Lọc child theo parent: vì sao load by ID cần test?

Một `@SQLRestriction("deleted = FALSE")` ở Document che các document tự deleted. Nhưng parent Customer đã bị soft-delete có thể làm Document vẫn active theo cột của chính nó.

Ví dụ query:

```hql
select d
from Document d
where d.id = :documentId
```

nếu chỉ áp restriction cho Document, điều kiện parent status **không tự trở thành policy thống nhất** trong mọi load path.

Cần test:
- `find(Document.class, id)`.
- JPQL/HQL query.
- Fetch join tới Customer.
- Lazy `document.getCustomer()`.
- Native SQL.
- Collection load.
- Multi-tenant filter.
- Second-level cache.
- Hibernate version-specific to-one behavior.

Đừng tin rằng mọi cách lấy child đều áp một predicate `parent.deleted=false` chỉ vì một repository method đã làm như vậy.

## 23. Xóa mềm và optimistic locking

Một entity:

```java
@Version
private long version;
```

giúp Hibernate phát hiện nhiều lost-update scenarios trong các managed updates.

Nhưng restore/hard purge qua JDBC phải **tự** thực hiện version semantics nếu cần:

```sql
UPDATE customers
SET deleted = false, version = version + 1
WHERE id = :id
  AND tenant_id = :tenantId
  AND deleted = true
  AND version = :expectedVersion;
```

Nếu không tăng version, một detached entity đã load trước đó có thể được merge/update theo logic stale mà không phát hiện thay đổi lifecycle đã diễn ra.

### 23.1. Native bulk SQL bypass ORM lifecycle

Hibernate/JPA không tự gọi per-entity callbacks, Envers listeners, `@Version` checks cho mỗi row khi bạn chạy một custom native/bulk statement.

Cần:
- Version predicate/increment.
- Explicit audit event.
- Cache invalidation.
- Transaction state checks.
- Ownership/tenant predicates.

Không hứa rằng một `@PreUpdate` sẽ tự chạy khi `JdbcTemplate` restore hàng.

## 24. Envers: giữ lịch sử khác việc giữ row bị xóa mềm

Hibernate Envers tạo audit revisions cho các entity được `@Audited` khi thay đổi được xử lý bởi lifecycle mà Envers hỗ trợ.

```java
import org.hibernate.envers.Audited;

@Entity
@Audited
@SoftDelete(columnName = "deleted")
public class Customer {
    // ...
}
```

Khi entity được remove qua Hibernate, ở ORM level đây là **delete lifecycle event** dù DB physical row có thể chỉ bị update soft-delete indicator.

Một mô hình audit có thể ghi `RevisionType.DEL` tại thao tác soft delete, nhưng chi tiết audit flags/snapshots/SQL phải được kiểm thử trên **Hibernate + Envers version thực tế**.

Không giả định `@SoftDelete` tự biến mọi tombstone/restore/hard delete thành một chuỗi audit revisions đầy đủ và có nội dung nghiệp vụ như mong muốn.

### 24.1. Dữ liệu cần biết tại thời điểm restore

Envers có thể giúp:
- Đọc thuộc tính entity tại revisions trước.
- Biết một entity đã có trạng thái nào qua lifecycle.
- Truy vấn lịch sử relationships được audit.
- Điều tra thay đổi qua Hibernate.

Nhưng Envers không thay thế:
- Domain event `CustomerRestored`.
- Actor/reason/approval workflow.
- Thời hạn retention/legal hold.
- Hard purge audit receipt.
- Sự kiện do external JDBC/bulk SQL.

### 24.2. Restore native SQL có tạo Envers revision không?

Thông thường **không**. Native SQL từ JDBC không đi qua managed entity listeners của Envers. Nếu service restore bằng direct SQL, phải ghi audit/outbox record riêng hoặc một cơ chế database-level audit để có dấu vết khôi phục.

Không tự insert vào Envers `_AUD` tables nếu chưa hiểu revision numbering, audit strategy, delete semantics và composite keys. Có thể tốt hơn là lưu **business audit log** riêng cho restore/purge.

## 25. Soft delete, Envers và trạng thái đã purge

Ví dụ audit database:

```text
customers:
  Customer#42 deleted=true

customers_AUD:
  REV1 ADD
  REV5 MOD
  REV9 DEL
```

Sau hard DELETE Customer#42:

```text
customers:
  không còn Customer#42

customers_AUD:
  vẫn có thể có REV1/REV5/REV9
```

**Purge bảng chính không mặc nhiên purge audit tables.**

Nếu mục tiêu là loại bỏ hoàn toàn dữ liệu cá nhân khỏi phạm vi được kiểm soát, phải xét cả Envers history. Ngược lại, có nghiệp vụ/chính sách buộc giữ một phần lịch sử mà không giữ hồ sơ hoạt động.

### 25.1. Hard purge audit tables có thể phá historical graph

Nếu xóa mọi `Customer_AUD` rows của Customer#42, một `Order_AUD` trước đây tham chiếu Customer#42 có thể không resolve được historical target nữa.

Có các phương án:
- Giữ customer audit nhưng anonymize những thuộc tính bị yêu cầu xóa, nếu policy cho phép.
- Giữ một minimal tombstone/key record.
- Tách financial/legal snapshots khỏi PII.
- Thay quan hệ lịch sử bằng immutable business identifiers không mang PII.
- Thiết kế retention riêng cho customer và financial records.

Không tự bật `ON DELETE CASCADE` từ audit tables sang live entity để “dọn sạch” khi purge. Audit references và historical consistency cần thiết kế riêng.

## 26. History có thể nằm ở nhiều nơi

Một hệ thống thực tế thường có:

```text
Primary DB
   ├─ customers (live + soft-deleted)
   ├─ documents
   ├─ _AUD / REVINFO (Envers)
   └─ outbox / audit events

Object storage
   └─ document files, thumbnails

Search
   └─ customer/document indexes

Analytics
   └─ warehouse, exports, materialized views

Infrastructure
   └─ backups, replicas, snapshots, logs
```

Một “purge request” cần inventory các nơi giữ bản sao theo chính sách.

### 26.1. Tránh giữ PII trong purge evidence

Log chứng minh đã purge có thể chỉ cần:

```text
deletion_request_id
subject_type
hashed_or_internal_subject_reference
tenant_id
policy_version
started_at / completed_at
status
approved_by_role
error_code
```

Không lưu lại toàn bộ email/address/JSON payload của người dùng trong “evidence log” chỉ để chứng minh đã xóa — việc đó có thể làm mất tác dụng của purge.

## 27. Anonymization khác xóa vật lý

Ví dụ một hóa đơn phải giữ các số liệu tài chính nhưng không cần giữ tên/email người mua ở bảng chính.

Có thể biến:

```text
customer_name = "An Nguyen"
customer_email = "an@example.org"
```

thành:

```text
customer_name = "REDACTED"
customer_email = NULL
```

với các constraints/schema phù hợp.

Tuy nhiên:
- Nếu email là UNIQUE/NOT NULL, migration cần xử lý.
- Tên có thể còn trong audit table/JSON payload/outbox.
- Một pseudonym hoặc hash của email **có thể vẫn là dữ liệu có khả năng liên kết cá nhân** tùy bối cảnh.
- Reversible encryption không tự tương đương anonymization.
- Nếu đã anonymize không đảo ngược, “restore” đầy đủ có thể không còn khả thi.

### 27.1. Chọn một dữ liệu snapshot tối thiểu

Với tài liệu/đơn hàng lịch sử, đôi khi chỉ cần:
- Mã chứng từ.
- Ngày/giờ.
- Số tiền.
- Trạng thái thanh toán.
- Mã người mua đã pseudonymize đúng policy.

Không nhất thiết phải giữ mọi field của Customer object graph.

## 28. Backups: không hứa xóa tức thời mọi bản sao

Sau khi hard delete trên primary DB:
- Replicas sẽ áp thay đổi theo cơ chế replication.
- Point-in-time recovery/WAL có thể chứa dữ liệu cũ trong khoảng retention.
- Backups cũ có thể còn dữ liệu.
- Logs/exports/analytics có thể còn copy.

Chính sách xóa cần mô tả:
- Backup retention và thời hạn expiry.
- Quy trình restore backup không làm “hồi sinh” dữ liệu đã có lệnh purge.
- Re-apply deletion tombstones sau disaster recovery khi cần.
- Encryption/key lifecycle và giới hạn crypto-erasure.
- Audit evidence có thể kiểm tra.
- Nguyên tắc không dùng backup như kho dữ liệu truy cập thông thường.

Không được tuyên bố dữ liệu đã biến mất trên mọi hệ thống nếu chưa kiểm chứng pipeline retention/replication/backups.

## 29. Tombstone và bảng yêu cầu xóa

Khi live row bị purge, hệ thống vẫn có thể cần biết rằng ID đã được xóa để chống replay/reimport.

Một bảng minimal tombstone:

```sql
CREATE TABLE purge_tombstones (
    subject_type VARCHAR(60) NOT NULL,
    tenant_id BIGINT NOT NULL,
    subject_id BIGINT NOT NULL,
    purge_request_id VARCHAR(100) NOT NULL,
    purged_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (subject_type, tenant_id, subject_id)
);
```

Tombstone không nên chứa những PII mà purge nhằm xóa.

Lợi ích:
- Ngăn import/replay vô tình tạo lại subject.
- Làm checkpoint/idempotency cho job.
- Giúp hệ thống search/external sync xử lý deletion event.
- Cung cấp dấu vết tối thiểu.

Nhưng retention của tombstone cũng cần policy; không phải dữ liệu ít hơn thì được giữ mãi mà không đánh giá.

## 30. Transactional outbox cho restore/purge events

Một restore service phải update DB và thông báo các downstream systems:

```text
Restore Customer#42
    |
    +-- UPDATE customers SET deleted=false ...
    |
    +-- INSERT outbox(
          event_type='CustomerRestored',
          subject_id=42,
          event_id=...
        )
    |
    v
DB COMMIT
    |
    v
Outbox relay -> search/cache/other services
```

Outbox record cùng DB transaction với state change giúp tránh trường hợp DB commit mà service crash trước khi ghi event.

Với purge, có thể:
- Ghi yêu cầu/điều kiện và tiến trình.
- Hard delete live rows theo job.
- Ghi completion/tombstone/outbox metadata tối thiểu trong transaction phù hợp.
- Relay các notifications đến object storage/search/analytics workers.
- Mark toàn request completed **chỉ sau khi các bước bắt buộc đạt điều kiện**.

### 30.1. Outbox không tự bảo đảm exactly-once

Relay có thể publish lại một event nếu crash giữa publish và ack. Consumers phải idempotent theo `event_id` hoặc deletion request ID.

Sự kiện purge cần tránh mang PII đã định xóa. Consumer chỉ cần định danh/tombstone đủ để xóa bản sao của nó theo chính sách.

### 30.2. Không gọi network trong JPA callback để xóa file ngay

`@PostRemove`/Hibernate `POST_DELETE` có thể chạy trước DB commit. Nếu lập tức xóa file ở object storage rồi transaction rollback, database còn record nhưng file đã mất.

Dùng outbox/workflow sau commit và có cơ chế bù trừ/retry.

## 31. Bulk soft delete và bulk purge có được audit không?

Một lệnh:

```java
em.createQuery("""
    update Customer c
    set c.status = :status
    where c.tenantId = :tenant
    """)
    .setParameter("status", "INACTIVE")
    .setParameter("tenant", tenantId)
    .executeUpdate();
```

là bulk DML. Nó không gọi per-entity `@PreUpdate`/Envers event handlers cho từng row như cách mutate managed entities.

Một native:

```sql
UPDATE customers SET deleted=true WHERE tenant_id=:tenantId;
```

cũng không tự có toàn bộ lifecycle/version/cache/audit semantics của `em.remove(entity)`.

**Không nhầm**:
- ORM remove với built-in @SoftDelete.
- HQL/JPQL bulk DELETE.
- HQL/JPQL bulk UPDATE.
- Native SQL DELETE/UPDATE.
- JDBC từ process khác.
- Database `ON DELETE CASCADE`.

Tùy Hibernate version, một số bulk operations có thể được biến đổi để xử lý soft-deletable entities, nhưng không coi điều đó là cam kết Envers audit đủ từng row hay áp mọi policy custom. Kiểm thử SQL thực tế và `@SoftDelete` interaction trước khi chạy trên production.

## 32. Soft delete và Row-Level Security (RLS)

Hibernate filters và annotations thuộc ứng dụng/ORM. Nếu có các writers/readers ngoài Hibernate, chúng có thể bỏ qua soft-delete predicate.

PostgreSQL Row-Level Security có thể góp phần đảm bảo database user chỉ thấy đúng tenant/rows phù hợp, nhưng:
- RLS policies phụ thuộc DB roles và session context.
- Admin/maintenance roles có thể cần quyền bypass có kiểm soát.
- Soft delete ở DB có thể tương tác với RLS UPDATE/DELETE policies.
- Một policy SELECT chỉ cho active rows có thể khiến admin không nhìn thấy deleted rows để restore trừ khi có một admin role/policy riêng.
- RLS không thay domain rules/retention.

Không bật một RLS policy mẫu rồi tin mọi `UPDATE`/`DELETE` đã an toàn. Test ở đúng DB roles với các tình huống restore/purge.

## 33. Authorization: ai có quyền khôi phục và purge?

Phân biệt quyền:

| Quyền | Ví dụ actor | Rủi ro |
| --- | --- | --- |
| Soft delete own document | Người sở hữu | Có thể xóa dữ liệu chia sẻ |
| Restore own document | Người sở hữu trong cửa sổ cho phép | Lộ dữ liệu từng được ẩn |
| Restore customer account | Support/admin sau xác minh | Chiếm danh tính hoặc bypass fraud flag |
| Purge record | Retention worker có approval | Không thể khôi phục |
| Override legal hold | Vai trò đặc biệt có kiểm soát | Rủi ro compliance cao |
| Read deleted data | Admin/auditor được ủy quyền | Lộ PII |

Không nhận role/tenant từ request body như nguồn tin cậy. User-facing API không nên tiết lộ sự tồn tại của một deleted row ở tenant khác qua thông điệp `CONFLICT` quá chi tiết.

### 33.1. Hai-person approval khi cần

Với dữ liệu quan trọng, có thể yêu cầu:
- Người đề xuất purge.
- Người phê duyệt.
- Job executor có quyền giới hạn.
- Audit evidence không chứa PII.
- Dry-run report trước khi thực thi.

Đây là quy trình governance, không phải một annotation Hibernate.

## 34. API contract cho restore và purge

Ví dụ endpoints:

```text
POST /api/customers/{id}/restore
POST /api/customers/{id}/deletion-requests
GET  /api/deletion-requests/{requestId}
```

Không nhất thiết expose hard delete như:

```text
DELETE /api/customers/{id}?force=true
```

cho public clients; hard purge nên là workflow được ủy quyền, ghi nhận trạng thái và có idempotency.

### 34.1. Kết quả restore

| Tình huống | Kết quả đề xuất |
| --- | --- |
| Deleted row được restore | 200/204 theo API contract |
| Đã active và request lặp | 200/204 idempotent hoặc 409 theo policy |
| Unique key conflict | 409 với thông điệp không rò rỉ dữ liệu tenant khác |
| Chưa hết waiting period | 409/422 tùy API policy |
| Quá hạn restore / đã purge | 404/410 hoặc lỗi domain trung tính |
| Không đủ quyền | 403/404 theo security policy |
| Concurrent version mismatch | 409/412 nếu có precondition/version |
| Database tạm không khả dụng | 5xx/retry với idempotency |

Mã HTTP cần được chuẩn hóa theo sản phẩm; bảng chỉ minh họa.

### 34.2. API purge thường bất đồng bộ

Nếu purge gồm DB, object storage, search và analytics:

```text
202 Accepted
{
  "requestId": "delreq-..."
}
```

Các trạng thái có thể là:
- `REQUESTED`
- `ELIGIBILITY_CHECK`
- `WAITING_RETENTION`
- `BLOCKED_BY_HOLD`
- `PURGING`
- `PARTIAL_FAILURE`
- `COMPLETED`
- `REJECTED`

Không trả “đã xóa vĩnh viễn” ngay sau khi ghi một bản ghi vào queue nếu các bước thực thi chưa hoàn thành.

## 35. Migrations khi thêm soft delete vào hệ thống cũ

Migration ví dụ PostgreSQL:

```sql
ALTER TABLE customers
ADD COLUMN deleted BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE customers
ADD COLUMN deleted_at TIMESTAMP WITH TIME ZONE;
```

Cần:
1. Chọn indicator semantics, nullable, defaults.
2. Backfill existing rows thành active.
3. Thay queries/repositories để ẩn deleted theo policy.
4. Xem unique indexes khi có deleted rows.
5. Cập nhật indexes cho active queries.
6. Kiểm tra FK/cascade.
7. Thêm retention metadata và legal hold model.
8. Đảm bảo ứng dụng cũ/mới tương thích khi rolling deploy.
9. Test Hibernate mapping và raw SQL/admin paths.
10. Thiết kế rollback/migration forward khi lỗi.

### 35.1. Đừng thêm `@SoftDelete` trước khi cột được migrate

Nếu Hibernate mapping kỳ vọng `deleted` nhưng database chưa có cột, startup hoặc query có thể lỗi. Với migration-owned schema, chạy Flyway/Liquibase trước Hibernate validate.

### 35.2. Đừng chỉ thêm default ở Java

`boolean deleted=false` trong Java không đảm bảo SQL từ writers khác gán default đúng. DB `NOT NULL DEFAULT FALSE` và constraints vẫn quan trọng.

### 35.3. Chuyển từ legacy `@SQLDelete` sang `@SoftDelete`

Cần kiểm tra:
- Cột indicator và type có tương thích.
- Legacy queries có dùng `@Where`/`@SQLRestriction` không.
- Fetch joins/to-one/filter behavior.
- Collection delete semantics.
- Cache invalidation.
- Envers event/revision behavior.
- Custom SQL `@SQLDelete` và cascade không còn mâu thuẫn.
- Version/optimistic locking.
- Dữ liệu tombstone cũ.
- Bản upgrade Hibernate 6.4 → 7.x có thay đổi semantics không.

Không chỉ đổi annotation và mong mọi use case restore/purge vẫn hoạt động.

## 36. Index cho soft-delete queries và purge jobs

Truy vấn phổ biến:

```sql
SELECT id, display_name
FROM customers
WHERE tenant_id = :tenant
  AND deleted = false
ORDER BY id;
```

Có thể tận dụng index:

```sql
CREATE INDEX idx_customers_active_by_tenant
ON customers (tenant_id, id)
WHERE deleted = FALSE;
```

Cho purge:

```sql
CREATE INDEX idx_customers_purge_candidates
ON customers (deleted_at, id)
WHERE deleted = TRUE;
```

Đây là PostgreSQL partial indexes, không phải DDL portable mọi DBMS.

### 36.1. Không tạo index chỉ vì nhìn câu SQL

Cần xem:
- Tỷ lệ active/deleted.
- Cardinality tenant.
- Index selectivity.
- Query plans và sort.
- Số writes, index maintenance cost.
- Vacuum/partitioning.
- Các FKs và join paths.
- Các truy vấn admin khác cần deleted rows.

Một boolean `deleted` đơn độc có cardinality thấp; index trên đúng composite/filter condition thường hữu ích hơn, nhưng phải đo trên dữ liệu thật.

## 37. Bảng audit/log riêng cho restore và purge

Envers history phục vụ historical entity state, nhưng thao tác restore/purge còn cần metadata như actor, reason, request ID và approval.

Có thể tạo:

```sql
CREATE TABLE data_lifecycle_events (
    event_id UUID PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    subject_type VARCHAR(60) NOT NULL,
    subject_id BIGINT NOT NULL,
    action VARCHAR(40) NOT NULL,
    actor_ref VARCHAR(100),
    reason_code VARCHAR(100),
    request_id VARCHAR(100),
    occurred_at TIMESTAMP WITH TIME ZONE NOT NULL
);
```

Action values như:
- `SOFT_DELETE_REQUESTED`
- `SOFT_DELETED`
- `RESTORE_REQUESTED`
- `RESTORED`
- `PURGE_BLOCKED`
- `PURGED`
- `ANONYMIZED`

Bảng này cũng có retention/PII policy riêng. Nếu actor ID hoặc reason text là dữ liệu nhạy cảm, phải bảo vệ tương ứng.

### 37.1. Event log khác audit snapshot

- `Customer_AUD` có thể cho biết fields tại revision.
- `data_lifecycle_events` cho biết một hành động đã được yêu cầu/thực hiện, ai, lý do.
- `purge_tombstones` cho biết chủ thể đã bị xóa vật lý.
- Outbox bảo đảm downstream synchronization.

Không cố ép một bảng làm tất cả mà bỏ qua đặc tính transaction/retention của từng loại.

## 38. Integration test: soft delete ẩn row nhưng DB vẫn còn

Với mapping `@SoftDelete` và test database có schema phù hợp:

```java
@Test
void softDeleteHidesCustomerButKeepsPhysicalRow() {
    EntityManager em = emf.createEntityManager();
    EntityTransaction tx = em.getTransaction();

    try {
        tx.begin();

        Customer customer = em.find(Customer.class, customerId);
        assertNotNull(customer);

        em.remove(customer);
        em.flush();

        tx.commit();
    } catch (RuntimeException ex) {
        if (tx.isActive()) tx.rollback();
        throw ex;
    } finally {
        em.close();
    }

    EntityManager verify = emf.createEntityManager();

    try {
        assertNull(verify.find(Customer.class, customerId));
    } finally {
        verify.close();
    }

    // Với JDBC/admin SQL riêng:
    // assertEquals(true, SELECT deleted FROM customers WHERE id=?);
}
```

Cần fixture `emf`, `customerId`, migrations, imports JUnit và test isolation. Không dùng `try-with-resources` với EntityManager khi Jakarta Persistence version chưa cho phép AutoCloseable.

**Hai assertions khác nhau:**
- Hibernate normal read không thấy row.
- JDBC raw query vẫn thấy row với marker deleted.

Nếu chỉ assert Hibernate `find()==null`, test chưa chứng minh soft delete thay vì hard delete.

## 39. Integration test: restore và unique conflict

Flow:

1. Tạo Customer#42 email `an@example.org`, commit.
2. Soft delete Customer#42, commit.
3. Tạo Customer#99 cùng email (với partial unique active index), commit.
4. Thử restore Customer#42 bằng conditional UPDATE.
5. Database từ chối do unique constraint.
6. Rollback transaction, verify Customer#42 vẫn deleted.
7. Giải quyết conflict theo policy rồi thử restore lại.
8. Kiểm tra Hibernate `find(Customer#42)` qua context mới cho trạng thái phù hợp.

### 39.1. Test restore version

- Đọc `version` của deleted row qua admin SQL.
- Transaction T1 restore với `expectedVersion=3`.
- Transaction T2 thử restore với `expectedVersion=3`.
- T2 affected rows = 0 vì deleted flag/version đã đổi.

Không giả định `@Version` tự được Hibernate quản lý cho update JDBC trực tiếp.

### 39.2. Test record đã purge

Sau hard purge:
- `em.find()` trả null.
- Raw SQL cũng không còn row.
- Tombstone/event evidence theo policy có trạng thái hoàn thành.
- Restore không thể tự INSERT row mới có cùng identity nếu không có một quy trình tái tạo dữ liệu đặc biệt.

## 40. Integration test: quan hệ và idempotency

Scenario:

```text
Customer#42
  Document#101 soft-deleted independently
  Document#102 active
```

Sau soft delete Customer:
- Theo **cascade model**, Document#102 bị deleted với reason `PARENT_DELETED`.
- Document#101 giữ reason `USER_DELETED`.
- Theo **parent visibility model**, Document#102 vẫn active ở row nhưng public read phải ẩn vì parent deleted.

Restore Customer:
- Document#101 **không tự trở lại**.
- Document#102 có thể hiện lại theo đúng model.
- Search/authorization/tenant scope không làm lộ deleted records.

Test này cần SQL assertions và API read-path assertions, không chỉ kiểm tra JPA cascade annotations.

### 40.1. Retry purge không xóa thêm dữ liệu ngoài scope

- Chạy purge worker cho Customer#42, commit.
- Chạy lại cùng request ID.
- Worker xem tombstone/checkpoint và trả idempotent completion.
- Không xóa Customer#99 hoặc child của tenant khác.
- Không tạo thêm lifecycle event “xóa thành công” giả nếu target đã không còn.

## 41. Testcontainers và kiểm thử giống production

Nếu production là PostgreSQL, nên dùng Testcontainers PostgreSQL để kiểm tra:
- Partial unique indexes.
- Boolean/timestamp soft-delete SQL.
- `SELECT ... FOR UPDATE`/locking.
- Transaction isolation.
- FK ON DELETE actions.
- Audit tables Envers và rollback.
- Native UPDATE version behavior.
- Retention candidate indexes.
- Concurrent restore và purge.
- Query filter behavior trên đúng Hibernate version.
- Cache invalidation nếu L2/query cache bật.

Một setup đơn giản:

```java
@Testcontainers
@SpringBootTest
class LifecycleIntegrationTest {

    @Container
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void databaseProps(DynamicPropertyRegistry registry) {
        registry.add(
            "spring.datasource.url",
            postgres::getJdbcUrl
        );
        registry.add(
            "spring.datasource.username",
            postgres::getUsername
        );
        registry.add(
            "spring.datasource.password",
            postgres::getPassword
        );
        registry.add(
            "spring.jpa.hibernate.ddl-auto",
            () -> "validate"
        );
        registry.add(
            "spring.flyway.enabled",
            () -> "true"
        );
    }
}
```

Đoạn trên cần các imports/dependencies của Spring Boot, JUnit 5, Testcontainers; migration files và `Customer` mapping phải có trong test runtime classpath. Không dùng schema H2 tự tạo để kết luận partial index/locking PostgreSQL đúng.

## 42. Theo dõi vận hành

Các metrics có ích:

- Số soft-delete requests/commit successes/failures.
- Số restore attempts, successes, unique conflicts, stale version conflicts.
- Số records đã đủ điều kiện purge nhưng vẫn còn.
- Độ tuổi record soft-deleted lâu nhất theo policy.
- Số active legal holds, số purge bị block do hold.
- Purge throughput và p95/p99 chunk duration.
- Database lock waits/replication lag/transaction log growth.
- Outbox backlog và số retries của downstream deletion.
- Số objects/files/search docs còn sót sau purge.
- Envers audit table size/retention pressure.
- Cache miss spikes sau restore/delete.
- Số subject đã bị hồi sinh từ backup/import trái ý muốn.

Không ghi email, access token hay payload PII vào log nhằm đo metrics. Dùng IDs nội bộ và aggregate counts theo quyền.

## 43. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `persist()` không “restore” được row đã xóa mềm | Row vật lý vẫn tồn tại, lifecycle removed/detached | Admin restore command có điều kiện |
| Admin repository không tìm thấy deleted row | `@SoftDelete`/`@SQLRestriction` tự ẩn | Native/JDBC read path có quyền tường minh |
| Restore vi phạm UNIQUE | Key đã được row active khác sử dụng | Conflict policy + DB unique index |
| Restore xong API vẫn trả 404 | L1/L2/query cache stale hoặc downstream chưa reindex | New context, targeted eviction/event |
| `clear()` mất thay đổi khác | Pending changes chưa flush | Không clear bừa; thiết kế transaction boundary |
| Bulk SQL thay deleted flag nhưng Envers không có revision | Bypass per-entity lifecycle | Business audit event/DB audit |
| Hard DELETE không xóa audit rows | Audit tables độc lập | Retention policy cho historical data |
| Hard DELETE bị FK chặn | Child còn tham chiếu parent | Dependency plan, restrict/anonymize |
| Restore parent hồi sinh child user đã xóa | Blind cascade restore | Deletion reason/operation ID |
| Purge khi legal hold vừa được tạo | Race trong eligibility check | Transaction/locking protocol |
| DeletedAt null cho row deleted | Migration/backfill hoặc indicator semantics sai | Data validation, chọn một chiến lược |
| TTI/cache TTL làm dữ liệu không mới | External SQL không invalidated | Invalidation + test multi-node |
| Soft delete không lọc native query | ORM predicate không áp raw SQL | Viết tenant/deleted filter rõ |
| `@SQLDelete` với @Version lỗi bind | Custom SQL parameter positions sai | Test/update SQL hoặc @SoftDelete |
| `@SoftDelete TIMESTAMP` không compile | Hibernate version cũ | Kiểm tra SoftDeleteType version |
| Partial index hoạt động trên Postgres nhưng H2 fail | DB-specific DDL | Test đúng DBMS |
| Phần mềm hứa “purged” nhưng file còn | Async delete pipeline chưa xong | Job state/checkpoint/inventory |
| Backup restore đưa dữ liệu đã purge quay lại | Thiếu tombstone reapply | Recovery runbook + deletion ledger |
| Public API lộ deleted record cross-tenant | Admin path/tenant check sai | RLS/authorization + tests |
| Một giant DELETE làm lock DB | Không chia chunk, thiếu index | Keyset batch purge + metrics |
| Pseudonym vẫn có thể xác định người | Hash/linkable identity còn | Privacy assessment, minimization |
| Dữ liệu bắt buộc lưu bị xóa sớm | Không phân biệt legal retention | Hold/policy enforcement/approval |
| Không thể khôi phục sau anonymize | Mất irreversible fields | API/lifecycle nêu rõ non-restorable |

## 44. Quy trình quyết định cho từng use case

**Bước 1 — Xác định ngữ nghĩa xóa.** Người dùng muốn ẩn khỏi UI, vô hiệu tài khoản, tạm giữ để khôi phục, hay xóa dữ liệu vật lý?

**Bước 2 — Chọn indicator.** Boolean `deleted`, boolean `active`, timestamp `deleted_at` hoặc state machine riêng. Không để nhiều cột mâu thuẫn mà không có invariants.

**Bước 3 — Chọn Hibernate mapping.** Nếu phù hợp, dùng first-class `@SoftDelete`; với legacy/manual visibility cần `@SQLRestriction`/`@Filter` có test. Không nhầm native SQL với ORM rules.

**Bước 4 — Thiết kế read paths.** Public reads ẩn deleted; admin reads có authorization và audit. Đảm bảo load by ID, joins, collections và caches nhất quán.

**Bước 5 — Thiết kế restore.** Đường SQL tường minh với tenant, version, deleted state, conflict handling và business validations.

**Bước 6 — Định nghĩa relationship behavior.** Parent soft delete có cascade hay chỉ visibility; restore children nào, giữ child nào đã deleted độc lập.

**Bước 7 — Đặt database constraints/indexes.** UNIQUE semantics cho active rows, FK actions, versioning, indexes cho query/purge.

**Bước 8 — Phân biệt retention và restorable window.** Hết thời hạn restore chưa chắc được purge; còn retention chưa chắc được restore.

**Bước 9 — Phối hợp legal holds.** Check/lock protocol đủ để không purge nhầm khi hold được tạo đồng thời.

**Bước 10 — Định nghĩa scope purge.** Live rows, children, audit, blobs, search, analytics, backups; không hứa “xóa hết” nếu còn hệ thống chưa xử lý.

**Bước 11 — Ghi evidence tối thiểu.** Audit/outbox/tombstone không giữ PII trái mục tiêu xóa.

**Bước 12 — Chọn transaction/chunks.** Xóa theo lô, retry/idempotency, observability, tránh một transaction quá lớn.

**Bước 13 — Kiểm thử đúng stack.** ORM remove vs native SQL, restore, unique conflict, FK, Envers, multi-tenant, caching, concurrency.

**Bước 14 — Chuẩn bị runbook.** Cảnh báo backlog, legal hold conflicts, backup restore reapply, manual intervention.

## 45. Bài tập tình huống

### Bài 1 — `persist()` có phải khôi phục?

Customer#42 đã soft-deleted nhưng row còn trong DB. Có thể tạo `new Customer(id=42)` rồi `em.persist()` để restore?

**Đáp án:** Không. Row vật lý vẫn có; có thể trùng PK/lifecycle conflict. Cần command restore theo DB state.

### Bài 2 — Restore và uniqueness

Một deleted account và active account có cùng email nhờ partial unique index. Restore deleted account sẽ ra sao?

**Đáp án:** Vi phạm uniqueness nếu không giải quyết conflict. Restore policy phải xử lý email/identity trước khi kích hoạt.

### Bài 3 — `@SQLRestriction`

Entity có `@SQLRestriction("deleted=false")`. Admin gọi `disableFilter("deleted")` có chắc thấy deleted rows?

**Đáp án:** Không. SQLRestriction là static predicate, không phải dynamic filter đó. Dùng admin read path riêng.

### Bài 4 — Xóa mềm nhưng foreign key còn

Customer đã soft-deleted, Document vẫn FK tới Customer. Database có tự xóa child không?

**Đáp án:** Không chỉ vì parent flag đổi. FK `ON DELETE CASCADE` thường áp cho DELETE vật lý, không phải UPDATE deleted flag.

### Bài 5 — Parent restore

Document#101 bị xóa bởi user trước khi parent Customer bị xóa. Restore parent có nên tự restore Document#101?

**Đáp án:** Không mặc định. Cần phân biệt lý do và phạm vi xóa.

### Bài 6 — Retention

Policy yêu cầu giữ invoice nhưng xóa profile người dùng. Có nên xóa toàn bộ invoice để purge profile?

**Đáp án:** Không tự động. Thiết kế lưu trữ tài chính tối thiểu, anonymization/snapshot và retention riêng theo chính sách hợp lệ.

### Bài 7 — Legal hold

Purge job vừa kiểm tra không có hold, worker khác thêm hold trước DELETE. Check trước đó đã đủ an toàn chưa?

**Đáp án:** Chưa. Cần transaction/locking protocol hoặc DB enforcement để tránh race.

### Bài 8 — Envers restore

Restore bằng `JdbcTemplate.update(...)`. Envers có tự tạo một `MOD` revision không?

**Đáp án:** Không, vì direct JDBC không qua Hibernate Envers per-entity listener. Cần business audit/event riêng.

### Bài 9 — Purge và audit

`DELETE FROM customers WHERE id=42` thành công. Có chắc `customers_AUD` không còn PII không?

**Đáp án:** Không. Audit tables phải có retention/remediation policy riêng.

### Bài 10 — Cache sau restore

Row restored nhưng Node B vẫn trả 404. Tại sao?

**Đáp án:** Cache/L1, query cache hoặc downstream search state stale; cần targeted invalidation, context lifecycle và multi-node propagation.

### Bài 11 — Timestamp strategy

Cấu hình `@SoftDelete(strategy=TIMESTAMP, converter=YesNoConverter.class)` có hợp lệ không?

**Đáp án:** Không. Converter boolean không hợp lệ với TIMESTAMP theo API Hibernate.

### Bài 12 — Bulk SQL

`UPDATE customers SET deleted=true` cho 10.000 rows có tương đương gọi `em.remove()` từng Customer không?

**Đáp án:** Không. Bulk/native SQL không tự đi qua per-entity callbacks/Envers/version/cascade giống nhau.

### Bài 13 — Backup

Primary DB đã purge nhưng backup tháng trước vẫn chứa user data. Có thể hứa đã xóa khỏi mọi nơi không?

**Đáp án:** Không. Cần backup retention/recovery policy và xử lý tái xuất hiện sau restore backup.

### Bài 14 — Restore version conflict

T1 restore thành công, T2 cố restore với `expectedVersion` cũ. T2 nên xử lý thế nào?

**Đáp án:** Conditional update trả 0 row; phản hồi idempotent/conflict theo API policy và đọc lại state trong transaction mới khi cần.

### Bài 15 — Admin security

API cho phép `includeDeleted=true` nhưng không kiểm tra role. Rủi ro?

**Đáp án:** Lộ bản ghi đã ẩn/PII và cross-tenant data; phải có authorization, tenant checks và audit.

### Bài 16 — Unique key với cờ deleted

`UNIQUE(tenant_id,email,deleted)` cho phép bao nhiêu deleted rows có cùng email?

**Đáp án:** Thường tối đa một nếu cả ba giá trị giống nhau; không phù hợp nếu muốn lưu nhiều deleted duplicates. Partial unique index diễn đạt “duy nhất khi active” rõ hơn trên PostgreSQL.

### Bài 17 — Định nghĩa completed

Purge job đã xóa DB row nhưng object storage file chưa xóa. Có nên đánh dấu `COMPLETED`?

**Đáp án:** Không nếu storage file thuộc scope bắt buộc. Cần partial/in-progress state, retries và verification.

### Bài 18 — Audit evidence

Sau purge, nên lưu nguyên email của user trong `purge_tombstones` để đối soát không?

**Đáp án:** Không mặc định. Lưu minimal identifiers/evidence theo policy, tránh tái tạo nguồn PII mới.

### Bài 19 — `ON DELETE CASCADE`

Database tự xóa children khi hard DELETE parent. Envers có chắc thêm DEL revision cho mỗi child?

**Đáp án:** Không. DB cascade không đi qua ORM entity delete events của từng child.

### Bài 20 — Một entity active hay inactive?

Entity dùng `SoftDeleteType.ACTIVE`; DB field `active=false`. Nó có bị coi soft-deleted không?

**Đáp án:** Có. Với ACTIVE strategy, true là còn hoạt động, false là bị xóa mềm.

## 46. Tài liệu tham khảo chính thức

- [Hibernate ORM User Guide — Soft Delete](https://docs.hibernate.org/orm/7.1/userguide/html_single/#soft-delete): `@SoftDelete`, boolean/timestamp strategies, entities và collection tables.
- [Hibernate ORM Javadocs — `SoftDelete`](https://docs.hibernate.org/orm/7.1/javadocs/org/hibernate/annotations/SoftDelete.html): annotation target, indicator column, converters và strategy.
- [Hibernate ORM Javadocs — `SoftDeleteType`](https://docs.hibernate.org/orm/7.1/javadocs/org/hibernate/annotations/SoftDeleteType.html): `DELETED`, `ACTIVE`, `TIMESTAMP`.
- [Hibernate ORM User Guide — Filtering entities and associations](https://docs.hibernate.org/orm/7.1/userguide/html_single/#pc-filter): `@SQLRestriction`, `@Filter`, associations và Session visibility.
- [Hibernate ORM Javadocs — `SQLRestriction`](https://docs.hibernate.org/orm/7.1/javadocs/org/hibernate/annotations/SQLRestriction.html): static SQL predicates.
- [Hibernate ORM Javadocs — `SQLDelete`](https://docs.hibernate.org/orm/7.1/javadocs/org/hibernate/annotations/SQLDelete.html): custom delete SQL và mapping constraints.
- [Hibernate ORM User Guide — Envers](https://docs.hibernate.org/orm/7.1/userguide/html_single/#envers): revision auditing và giới hạn lifecycle/bulk DML.
- [Hibernate Envers](https://hibernate.org/orm/envers/): module versioning/audit và mục tiêu sử dụng.
- [Hibernate ORM User Guide — Caching](https://docs.hibernate.org/orm/7.1/userguide/html_single/#caching): L2 cache/query cache behavior.
- [Jakarta Persistence 3.2 Specification](https://jakarta.ee/specifications/persistence/3.2/jakarta-persistence-spec-3.2.html): lifecycle remove/merge, transactions, persistence context, bulk operations.
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html): transaction boundaries, rollback và propagation.
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): after-commit application events và giới hạn.
- [PostgreSQL Documentation — Indexes on Expressions](https://www.postgresql.org/docs/current/indexes-expressional.html): `lower(email)` index.
- [PostgreSQL Documentation — Partial Indexes](https://www.postgresql.org/docs/current/indexes-partial.html): unique constraints trên subset active rows.
- [PostgreSQL Documentation — Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html): FK, UNIQUE, CHECK và referential integrity.
- [Testcontainers Java — PostgreSQL](https://java.testcontainers.org/modules/databases/postgres/): integration tests với DBMS tương đương production.

**Giới hạn phiên bản và vận hành:** `@SoftDelete` là Hibernate-specific và có các khả năng bổ sung theo major/minor version; `TIMESTAMP` không nhất thiết có trên Hibernate 6.4. `@SQLRestriction`, filters, bulk DML và to-one association visibility có hành vi thay đổi theo phiên bản. Partial unique indexes trong ví dụ là PostgreSQL-specific. Retention, privacy, backup và legal hold phải theo chính sách/yêu cầu pháp lý áp dụng cho hệ thống, không có một giá trị thời gian mặc định do Hibernate quyết định.

## Kết luận

**Xóa mềm là một trạng thái trong vòng đời dữ liệu, không phải giải pháp hoàn chỉnh cho xóa và lưu lịch sử.** Hibernate `@SoftDelete` giúp ẩn rows thay cho DELETE vật lý trong ORM lifecycle; còn **restore** cần một đường quản trị có điều kiện vì entity đã bị ẩn khỏi normal loads và không có JPA `restore()` chuẩn. Native/JDBC restore phải tự xử lý tenant, optimistic version, unique conflicts, cache invalidation và audit.

**Hard purge** là quy trình có quyền hạn và thời hạn rõ ràng: chỉ xóa khi đủ điều kiện, không vi phạm legal hold, giải quyết FK/children, xử lý audit records/PII, files/search/analytics/backups theo scope và có idempotency/monitoring. Envers giữ lịch sử theo ORM revisions nhưng không tự ghi đầy đủ mọi native restore, bulk purge, DB cascade hoặc external writer; retention của audit tables cần được quyết định độc lập.

Thiết kế tốt nhất bắt đầu từ **ý nghĩa nghiệp vụ của xóa, khôi phục và retention**, sau đó mới chọn annotation, SQL schema, transaction protocol và purge worker. Hãy kiểm thử cả active/soft-deleted/restored/purged states trên DBMS thật, gồm concurrency, multi-tenant authorization, lịch sử và tình huống lỗi, trước khi tin một cờ `deleted` đã giải quyết trọn vẹn vòng đời dữ liệu.
