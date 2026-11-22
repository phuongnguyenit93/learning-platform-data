# Phân biệt xóa mềm với tùy chỉnh lệnh xóa bằng `@SQLDelete` trong Hibernate

## 1. Vấn đề: “xóa” không luôn đồng nghĩa với xóa hàng khỏi database

Trong một hệ thống thương mại điện tử, người dùng nhấn **Xóa tài khoản**, nhưng đội vận hành vẫn cần dữ liệu để giải quyết giao dịch đang xử lý, điều tra sự cố hoặc phục hồi nhầm lẫn. Một ứng dụng quản lý tài liệu có thể yêu cầu tài liệu không xuất hiện ở màn hình mặc định nhưng chưa được phép biến mất vật lý. Hai yêu cầu này thường dẫn đến mô hình **xóa mềm** (*soft delete*).

Tuy nhiên, trong Hibernate có annotation `@SQLDelete`. Vì tên chứa chữ “Delete”, nhiều người nhầm rằng chỉ cần thêm `@SQLDelete` là ứng dụng tự có đầy đủ chức năng soft delete, bao gồm ẩn bản ghi, phục hồi, lọc quan hệ, phân quyền và xử lý bulk delete.

**Đây là hai khái niệm khác nhau:**

- **Xóa mềm (soft delete)** là một **chính sách dữ liệu/nghiệp vụ**: không xóa vật lý bản ghi; thay vào đó đánh dấu bản ghi không còn hoạt động, định nghĩa bản ghi nào hiển thị, có thể khôi phục không và dữ liệu liên quan được xử lý thế nào.
- **`@SQLDelete`** là một **cơ chế tùy chỉnh SQL của Hibernate**: thay câu SQL được Hibernate phát ra khi xóa một entity/collection row theo vòng đời ORM bằng câu SQL do lập trình viên cung cấp. SQL đó *có thể* là `UPDATE deleted = true`, nhưng cũng có thể là câu lệnh khác hoặc stored procedure. Annotation này tự nó không tạo một soft-delete policy hoàn chỉnh.

Ví dụ ý tưởng:

```text
Người dùng nhấn “Xóa”

              |
              v
      EntityManager.remove()
              |
              +---- Không tùy chỉnh
              |       DELETE FROM accounts WHERE id = ?
              |       -> hàng biến mất vật lý
              |
              +---- Có @SQLDelete custom SQL
                      UPDATE accounts SET deleted = true WHERE id = ?
                      -> hàng vẫn còn trong DB
                      -> nhưng query có tự ẩn hàng đó không? CHƯA CHẮC
```

Trong Hibernate 6.4 trở lên, có thêm `@SoftDelete` cung cấp hỗ trợ xóa mềm trực tiếp và thường nên được ưu tiên cho use case thông thường. Bài này tập trung **phân biệt ý nghĩa, phạm vi và giới hạn** của các cách tiếp cận ấy, đặc biệt khi tích hợp với bộ lọc.

### 1.1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích sự khác biệt giữa **physical delete**, **soft delete**, **`@SQLDelete`** và **`@SoftDelete`**.
2. Mô tả chính xác `EntityManager.remove()`/`Session.remove()` dẫn đến SQL gì theo mapping.
3. Dùng `@SQLDelete` kết hợp `@SQLRestriction` (hoặc bộ lọc phù hợp) để triển khai soft delete kiểu legacy.
4. Hiểu vì sao **chỉ có `@SQLDelete` là chưa đủ để ẩn row** khỏi truy vấn.
5. Biết giới hạn của `@Where` cũ, `@SQLRestriction` tĩnh, `@Filter` động và native SQL.
6. Dùng `@SoftDelete` trong Hibernate 6.4+ khi phù hợp, hiểu chiến lược `DELETED` và `ACTIVE`.
7. Xử lý `@Version`, kiểm tra affected row count, transaction, khôi phục và xóa vĩnh viễn.
8. Nhận diện bẫy với Spring Data JPA bulk deletes, cascade, association, unique index, cache và audit.
9. Xây integration test quan sát SQL và hành vi đọc/xóa/khôi phục.

## 2. Từ vựng nền tảng: physical delete, soft delete, tombstone, custom SQL

### 2.1. Physical delete

```sql
DELETE FROM customer_accounts WHERE id = 101;
```

Bản ghi không còn trong bảng `customer_accounts` sau commit. Các foreign keys, ON DELETE rules, triggers và transaction constraints quyết định các side effects.

Trong JPA, thao tác thông thường:

```java
CustomerAccount account = em.find(CustomerAccount.class, 101L);
em.remove(account);
```

khi không có soft-delete mapping hoặc custom SQL khác, thường dẫn đến physical DELETE.

### 2.2. Soft delete

```sql
UPDATE customer_accounts
SET deleted = true
WHERE id = 101;
```

Bản ghi vẫn có mặt trong database nhưng có trạng thái ngừng hoạt động. Application cần quyết định:

- Các truy vấn mặc định có loại `deleted = true` không?
- Admin hoặc audit viewer có được xem bản ghi đã xóa không?
- Khi người dùng muốn khôi phục thì làm gì?
- Unique constraints xử lý bản ghi đã xóa ra sao?
- Quan hệ FK/collection có ẩn child và parent đúng không?
- Xóa sau bao lâu thì purge thực sự?
- Có cần `deleted_at` và `deleted_by` không?

Không có một annotation nào thay thế được toàn bộ chính sách nghiệp vụ ấy.

### 2.3. Tombstone

Một **tombstone** là dấu hiệu bản ghi đã bị xóa logic, ví dụ `deleted = true` hoặc `deleted_at IS NOT NULL`. Có thể dùng để đồng bộ với hệ thống khác, giữ thông tin truy vết và ngăn xuất hiện trong read model mặc định.

Tombstone chỉ là một representation. Nó không nhất thiết giải quyết thời gian xóa, lý do xóa, phân quyền hoặc storage retention.

### 2.4. Custom delete SQL

`@SQLDelete` cho phép thay một lệnh DELETE do Hibernate chuẩn bị bằng SQL khác:

```java
@SQLDelete(
    sql = "UPDATE customer_accounts SET deleted = true WHERE id = ?"
)
```

Đây là **cơ chế SQL**, không phải tuyên bố business semantics. Nếu SQL là:

```sql
DELETE FROM customer_accounts WHERE id = ?;
```

thì nó vẫn là physical delete dù được khai báo qua `@SQLDelete`.

## 3. So sánh nhanh: mục tiêu và cơ chế

| Tiêu chí | Physical delete mặc định | Soft delete tự quản lý | `@SQLDelete` | Hibernate `@SoftDelete` |
|---|---|---|---|---|
| Bản chất | Hành vi xóa vật lý | Chính sách dữ liệu/nghiệp vụ | Tùy chỉnh SQL khi ORM xóa | Mapping soft delete tích hợp |
| Lệnh DB thường gặp | `DELETE` | `UPDATE` cờ hoặc timestamp | Do lập trình viên tự viết | Hibernate tạo theo mapping indicator |
| Bản ghi còn trong bảng chính | Không | Có | Tùy SQL đã khai báo | Có |
| Tự động ẩn trong truy vấn | Không liên quan | Phải thiết kế riêng | **Không** | Có hỗ trợ trực tiếp trong ORM |
| Hỗ trợ `EntityManager.remove` | Có | Tùy triển khai | Có, dùng custom statement | Có, theo soft-delete semantics |
| Khôi phục | Không có row để khôi phục | Phải thiết kế | Phải thiết kế | Không mặc định là API restore toàn diện |
| SQL handwritten | Không | Có thể có | **Có** | Thường không cần |
| Phụ thuộc Hibernate | JPA portable | Tùy thiết kế | Có | Có, Hibernate 6.4+ |
| Kiểm soát delete timestamp/actor tùy biến | Cần cơ chế riêng | Linh hoạt | Có thể dùng custom SQL, nhưng bind parameters bị giới hạn | Cần thiết kế bổ sung |
| Bulk HQL/native SQL | Thao tác khác per-entity remove | Tùy đường ghi | Không nên giả định callback custom SQL được dùng | Kiểm tra semantics/version cho bulk operations |

**Kết luận sơ bộ:** nếu cần xóa mềm thuần túy ở Hibernate 6.4+, cân nhắc `@SoftDelete`. Nếu phải tùy chỉnh câu delete statement trong một ứng dụng đang dùng mapping legacy hoặc database-specific, `@SQLDelete` có ích nhưng phải phối hợp với read filtering và các quy tắc khác.

## 4. Mô hình ví dụ: tài khoản khách hàng

Giả sử có bảng:

```sql
CREATE TABLE customer_accounts (
    id BIGINT PRIMARY KEY,
    email VARCHAR(255) NOT NULL,
    display_name VARCHAR(160) NOT NULL,
    deleted BOOLEAN NOT NULL DEFAULT FALSE
);
```

Hai trạng thái:

| ID | email | display_name | deleted |
|---:|---|---|---|
| 101 | an@example.test | Nguyễn An | false |
| 102 | binh@example.test | Trần Bình | false |
| 103 | cu@example.test | Lê Cũ | true |

Ứng dụng mặc định chỉ hiển thị 101 và 102. Admin có thể cần xem 103. Một service khác có thể cần xóa vĩnh viễn các bản ghi đã quá thời hạn retention. Tất cả đều sử dụng cùng một database, nhưng **không có nghĩa cùng một đường truy vấn**.

### 4.1. Entity cơ bản trước khi soft delete

```java
package com.example.account;

import jakarta.persistence.*;

@Entity
@Table(name = "customer_accounts")
public class CustomerAccount {

    @Id
    private Long id;

    @Column(nullable = false, length = 255)
    private String email;

    @Column(name = "display_name", nullable = false, length = 160)
    private String displayName;

    protected CustomerAccount() {}

    public Long getId() { return id; }
    public String getEmail() { return email; }
    public String getDisplayName() { return displayName; }
}
```

Nếu gọi `em.remove(account)` với mapping này, Hibernate thường phát:

```sql
DELETE FROM customer_accounts WHERE id = ?;
```

Bây giờ ta sẽ thay hành vi delete SQL, rồi xem phần nào của soft-delete policy vẫn chưa được xử lý.

## 5. Cách legacy: `@SQLDelete` chỉ thay câu SQL khi remove entity

### 5.1. Ánh xạ custom delete

```java
import jakarta.persistence.*;
import org.hibernate.annotations.SQLDelete;

@Entity
@Table(name = "customer_accounts")
@SQLDelete(
    sql = "UPDATE customer_accounts SET deleted = true WHERE id = ?"
)
public class CustomerAccount {

    @Id
    private Long id;

    @Column(nullable = false)
    private String email;

    @Column(name = "display_name", nullable = false)
    private String displayName;

    @Column(nullable = false)
    private boolean deleted = false;

    protected CustomerAccount() {}

    // getters và domain operations...
}
```

Khi entity được quản lý bởi Hibernate và bị xóa qua ORM lifecycle:

```java
CustomerAccount account = em.find(CustomerAccount.class, 101L);
em.remove(account);
```

Hibernate sử dụng câu SQL custom:

```sql
UPDATE customer_accounts SET deleted = true WHERE id = ?;
```

Thay vì physical DELETE, hàng 101 còn trong bảng với `deleted = true`.

### 5.2. `@SQLDelete` dùng cho DELETE event, không phải mọi UPDATE

Annotation này không thay đổi logic INSERT hoặc UPDATE thông thường:

```java
account.changeDisplayName("Tên mới");
```

vẫn là thay đổi entity do dirty checking và Hibernate phát UPDATE theo mapping. `@SQLDelete` chỉ định lệnh custom **thay cho lệnh xóa** trong các thao tác mà Hibernate giải quyết qua cơ chế đó.

Cũng đừng nhầm với:

- `@SQLInsert`: thay SQL INSERT do Hibernate tạo.
- `@SQLUpdate`: thay SQL UPDATE do Hibernate tạo.
- `@SQLSelect`: tùy chỉnh select-by-id trong các trường hợp mapping hỗ trợ.
- `@SQLRestriction`: thêm predicate tĩnh cho SQL SELECT/association loading.
- `@SoftDelete`: soft-delete indicator mapping tích hợp trong Hibernate 6.4+.

### 5.3. Nhược điểm rõ nhất: query vẫn có thể thấy bản ghi đã xóa

Chỉ với `@SQLDelete`:

```java
List<CustomerAccount> accounts = em.createQuery(
        "select a from CustomerAccount a",
        CustomerAccount.class
    )
    .getResultList();
```

HQL này **không tự hiểu** rằng `deleted = true` phải bị ẩn. Kết quả có thể chứa cả bản ghi 103, 101 sau khi xóa mềm.

`@SQLDelete` không phải bộ lọc truy vấn. Đây là khác biệt quan trọng nhất của bài.

### 5.4. Hibernate vẫn coi entity là “removed”

Sau `em.remove(account)`, entity được xử lý theo lifecycle **removed** dù câu SQL custom thực chất là UPDATE. Sau flush/commit, application không nên tiếp tục dùng cùng object như một entity managed bình thường hoặc trông đợi field `deleted` trong object tự được cập nhật chỉ vì SQL custom đã sửa database.

Nếu cần trả response về trạng thái đã xóa, nên tạo DTO từ identity/kết quả nghiệp vụ đã biết. Không nên dựa vào `account.isDeleted()` của instance vừa bị remove để chứng minh flag DB đã đổi.

### 5.5. Cần default hợp lệ khi INSERT

Nếu đã thêm cột `deleted BOOLEAN NOT NULL`, các row mới phải có giá trị mặc định hợp lệ. Có thể khai báo:

```java
@Column(name = "deleted", nullable = false)
private boolean deleted = false;
```

và/hoặc schema có default:

```sql
deleted BOOLEAN NOT NULL DEFAULT FALSE
```

Cần đảm bảo cột tồn tại và dữ liệu lịch sử đã được backfill trước khi code mới tham chiếu nó. Nếu database đang có NULL, predicate `deleted = false` sẽ **không** trả về những rows NULL vì logic SQL ba giá trị.

## 6. Hoàn thiện cách legacy bằng `@SQLRestriction`

Trong Hibernate 6.3+, `@SQLRestriction` áp một mệnh đề SQL **tĩnh**, tự động bổ sung vào các SQL mà Hibernate sinh để load entity hoặc collection trong phạm vi mapping.

Ví dụ:

```java
import jakarta.persistence.*;
import org.hibernate.annotations.SQLDelete;
import org.hibernate.annotations.SQLRestriction;

@Entity
@Table(name = "customer_accounts")
@SQLDelete(
    sql = "UPDATE customer_accounts SET deleted = true WHERE id = ?"
)
@SQLRestriction("deleted = false")
public class CustomerAccount {

    @Id
    private Long id;

    private String email;

    @Column(name = "display_name")
    private String displayName;

    @Column(name = "deleted", nullable = false)
    private boolean deleted = false;

    protected CustomerAccount() {}

    // getters...
}
```

Bây giờ Hibernate có hai chỉ dẫn riêng:

1. `@SQLDelete`: khi thực hiện entity removal, dùng `UPDATE deleted = true ...`.
2. `@SQLRestriction`: khi load entity qua SQL được Hibernate sinh trong phạm vi mapping, thêm predicate `deleted = false`.

### 6.1. SQL minh họa

```java
CustomerAccount a = em.find(CustomerAccount.class, 101L);
```

Hibernate có thể tạo SQL tương đương:

```sql
SELECT a.id, a.email, a.display_name, a.deleted
FROM customer_accounts a
WHERE a.id = ?
  AND a.deleted = false;
```

Với HQL:

```hql
select a
from CustomerAccount a
order by a.id
```

Hibernate cũng có thể áp restriction vào SQL:

```sql
SELECT a.id, a.email, a.display_name, a.deleted
FROM customer_accounts a
WHERE a.deleted = false
ORDER BY a.id;
```

**Lưu ý:** SQL chính xác, alias injection và vị trí predicate phụ thuộc query/mapping/dialect. `@SQLRestriction` nhận **một SQL fragment theo tên cột**, không phải HQL property expression. Với joined tables, phải xác nhận fragment áp vào đúng table.

### 6.2. Vì sao vẫn không phải một giải pháp đầy đủ?

Bộ đôi `@SQLDelete + @SQLRestriction` giải quyết **một số** yêu cầu phổ biến:

- JPA remove -> cập nhật cờ xóa.
- Các truy vấn ORM load CustomerAccount mặc định ẩn row đã xóa.

Nhưng chưa tự giải quyết:

- Xem bản ghi đã xóa ở màn hình quản trị.
- Khôi phục flag từ true về false.
- Xóa vĩnh viễn sau thời hạn retention.
- Dữ liệu liên kết, cascade và FK tới row đã xóa.
- Unique constraint khi tạo lại email.
- Bulk HQL/SQL mutations.
- Actor/timestamp/reason cho thao tác xóa.
- Các đường đọc ngoài Hibernate.
- Authorization, cache và audit history.

Đây là lý do nên phân biệt **kỹ thuật thay SQL** với **soft-delete policy của toàn hệ thống**.

### 6.3. Restriction tĩnh không thể tắt trong một Session

`@SQLRestriction("deleted = false")` là restriction gắn ở mapping. Nó **không** có tham số và **không thể disable động** theo từng request. Đó có thể là ưu điểm cho read path thông thường nhưng là giới hạn rõ ràng khi admin muốn “include deleted”.

Nếu cần cả default active-only và admin including-deleted, phải thiết kế đường đọc riêng. Không giả định rằng `session.disableFilter(...)` có thể vô hiệu hóa `@SQLRestriction` vì chúng là hai cơ chế khác nhau.

## 7. `@Where` cũ và thay thế trong Hibernate mới

Nhiều bài hướng dẫn trên Internet dùng:

```java
@Entity
@SQLDelete(sql = "UPDATE customer_accounts SET deleted = true WHERE id = ?")
@Where(clause = "deleted = false")
public class CustomerAccount {
    // ...
}
```

Cách này rất phổ biến trong các ứng dụng Hibernate đời trước. Tuy nhiên:

- `org.hibernate.annotations.Where` **đã deprecated từ Hibernate 6.3**.
- Trong Hibernate 6.3/6.6, annotation được khuyến nghị thay thế là `@SQLRestriction`.
- `@Where`/`@SQLRestriction` đều là SQL predicate tĩnh, không có dynamic parameters và không thể disable tại runtime.
- `@Where` không nên là lựa chọn mặc định cho code Hibernate mới khi có giải pháp được hỗ trợ tốt hơn.

Đối với dự án đang chạy Hibernate 5.x/6.2, cần theo API thực tế của phiên bản đó. Đừng copy `@SQLRestriction` vào một phiên bản chưa hỗ trợ.

### 7.1. Đừng dùng @Where trong ví dụ của Hibernate 6.6 như thể đây là API mới

Các bài cũ có thể vẫn chạy với `@Where`, nhưng lifecycle và giới hạn của nó không thay đổi: annotation chỉ giải quyết **read restriction**, không tự làm delete SQL thành UPDATE. Muốn soft delete legacy vẫn cần custom delete logic hoặc service logic ở phía write.

### 7.2. Không có predicate nào thay quyền truy cập

`@SQLRestriction("deleted = false")` chỉ ẩn tombstone; nó không chứng minh người dùng có quyền xem mọi hàng còn active. Điều kiện tenant/ownership/permission phải được thực thi theo security architecture. Không dùng nó để thay thế row-level authorization.

## 8. Hibernate 6.4+: `@SoftDelete` là tính năng soft delete chính thức

Hibernate ORM 6.4 bổ sung `@SoftDelete`, hỗ trợ soft-delete indicator cho entity và một số collection-table mappings. Khác với `@SQLDelete`, annotation này biểu đạt **ngữ nghĩa soft delete trực tiếp** để Hibernate điều phối SQL mutation và restriction trong ORM.

Ví dụ đơn giản:

```java
import jakarta.persistence.*;
import org.hibernate.annotations.SoftDelete;
import org.hibernate.annotations.SoftDeleteType;

@Entity
@Table(name = "customer_accounts")
@SoftDelete(
    columnName = "deleted",
    strategy = SoftDeleteType.DELETED
)
public class CustomerAccount {

    @Id
    private Long id;

    @Column(nullable = false)
    private String email;

    @Column(name = "display_name", nullable = false)
    private String displayName;

    protected CustomerAccount() {}
}
```

Hibernate hiểu rằng row được “xóa” bằng cách thay trạng thái indicator, và các load/query mapping cần coi row đã xóa là không hoạt động.

**Không cần khai báo đồng thời `@SQLDelete` và `@SQLRestriction` chỉ để tạo soft-delete đơn giản khi đã dùng `@SoftDelete`.** Hãy để mapping soft-delete chính thức điều phối hành vi, thay vì chồng nhiều cơ chế cạnh tranh trên cùng entity.

### 8.1. `SoftDeleteType.DELETED`

Ý nghĩa của indicator:

| DB value | Semantics |
|---|---|
| `deleted = false` | Row đang tồn tại logic |
| `deleted = true` | Row đã xóa mềm |

Default column name cho chiến lược này là `deleted` khi không ghi đè `columnName`.

### 8.2. `SoftDeleteType.ACTIVE`

Một số schema có cột `active` thay vì `deleted`:

```java
@Entity
@SoftDelete(
    strategy = SoftDeleteType.ACTIVE,
    columnName = "active"
)
public class CustomerAccount {
    @Id
    private Long id;
    // ...
}
```

Ở chiến lược ACTIVE:

| DB value | Semantics |
|---|---|
| `active = true` | Row đang hoạt động |
| `active = false` | Row bị ẩn/xóa mềm |

Hai chiến lược dùng **ngược nghĩa** cho cùng giá trị Boolean. Không đổi từ DELETED sang ACTIVE mà không migration dữ liệu.

### 8.3. Converter cho representation không phải BOOLEAN

Một database có thể lưu `'Y'/'N'` hoặc `0/1`. `@SoftDelete` có thể dùng AttributeConverter để map giữa boolean indicator và kiểu lưu trong DB.

Ví dụ:

```java
import org.hibernate.type.YesNoConverter;

@Entity
@SoftDelete(
    strategy = SoftDeleteType.DELETED,
    columnName = "removed",
    converter = YesNoConverter.class
)
public class CustomerAccount {
    @Id
    private Long id;
}
```

Với converter YesNo: ý nghĩa boolean `true` và `false` được đổi thành `'Y'` và `'N'`; chiến lược DELETED quyết định boolean nào có nghĩa đã xóa. Không viết converter đảo ngược hai lần vì Hibernate đã áp dụng `SoftDeleteType` cho semantics.

Converter phải không trả null cho indicator. Cần thống nhất converter, column type, constraints và dữ liệu cũ.

### 8.4. Indicator có thể được Hibernate quản lý nội bộ

Khi dùng `@SoftDelete` ở cấp entity, không nhất thiết khai báo thêm field Java:

```java
@Column(name = "deleted")
private boolean deleted;
```

Nếu mapping trùng cột với soft-delete indicator nội bộ, có thể gặp conflict hoặc semantics khó hiểu. Khi cần hiển thị trạng thái xóa cho admin, chọn query/read model phù hợp thay vì tự ý tạo một cột mutable trùng mapping mà không kiểm tra provider.

### 8.5. Giới hạn của @SoftDelete

`@SoftDelete` giúp xử lý mutation/filtering cho soft-delete mapping thường gặp, nhưng **không tự là một quy trình nghiệp vụ hoàn chỉnh**:

- Không tự cung cấp API “restore”/“undelete” nghiệp vụ với authorization.
- Không quyết định khi nào purge vật lý.
- Không biết ai xóa, lý do xóa hoặc retention policy nếu bạn chưa thiết kế.
- Không thay index/unique constraints.
- Không bảo đảm các SQL ngoài Hibernate tuân thủ chính sách.
- Không giải quyết mọi association cascade/archival rule cho domain.
- Không tự cung cấp history theo thời gian như Envers.

Với Hibernate 6.4+, đây thường là lựa chọn nên ưu tiên cho **xóa mềm đơn giản theo Boolean indicator**.

## 9. Vậy khi nào vẫn cần `@SQLDelete`?

`@SQLDelete` hữu ích khi:

1. Dự án dùng phiên bản Hibernate chưa hỗ trợ `@SoftDelete`.
2. Delete operation cần SQL đặc thù với predicate bổ sung, stored procedure hoặc cấu trúc database legacy.
3. Có các yêu cầu SQL ngoài phạm vi soft-delete indicator đơn giản mà annotation tích hợp không biểu diễn trực tiếp.
4. Cần giữ mapping legacy ổn định trong thời gian migrate sang Hibernate mới.

Ví dụ một câu SQL có conditional guard:

```java
@SQLDelete(
    sql = """
          UPDATE customer_accounts
          SET deleted = true
          WHERE id = ? AND deleted = false
          """
)
```

Hoặc custom SQL physical delete theo cấu hình database:

```java
@SQLDelete(
    sql = "DELETE FROM customer_accounts WHERE id = ?"
)
```

Ví dụ thứ hai minh chứng rằng **`@SQLDelete` không mang ngữ nghĩa soft delete bắt buộc**.

### 9.1. Mức tùy biến vẫn có ràng buộc

`@SQLDelete` **không** nhận arbitrary named parameters như một query HQL. Câu SQL phải có đúng số vị trí JDBC `?` mà Hibernate dự kiến cho delete mapping, theo thứ tự do Hibernate xác định.

Không viết:

```java
@SQLDelete(
    sql = "UPDATE customer_accounts SET deleted_by = :currentUser WHERE id = :id"
)
```

rồi giả định Hibernate tự bind `:currentUser` như HQL. Muốn ghi `deleted_by` từ security principal cần thiết kế riêng: service-level update, session-scoped DB variables đã kiểm soát, audit listener, trigger, custom event integration hoặc cơ chế khác phù hợp.

### 9.2. SQL có thể dùng biểu thức DB

Có thể muốn lưu thời điểm xóa:

```java
@SQLDelete(
    sql = """
          UPDATE customer_accounts
          SET deleted = true,
              deleted_at = CURRENT_TIMESTAMP
          WHERE id = ?
          """
)
```

Về SQL, điều này khả thi nếu cột tồn tại và dialect hỗ trợ syntax. Nhưng mapping `deletedAt` trong Java object vừa bị remove **không tự đồng bộ lại** với thời điểm DB đã ghi. Cần xác định mục tiêu audit và query admin riêng.

### 9.3. Không bỏ qua ảnh hưởng khác của customized SQL

Custom SQL có thể phá optimistic locking hoặc khiến affected row count sai nếu thiếu WHERE đúng; có thể mâu thuẫn với trigger, multi-tenancy, partition key hoặc secondary tables. Mỗi `@SQLDelete` nên có integration test dùng database/dialect thực tế.

## 10. `@SQLDelete` với `@Version` và optimistic locking

Đây là một điểm dễ sai kỹ thuật.

Giả sử entity có:

```java
@Entity
@Table(name = "documents")
@SQLDelete(
    sql = """
          UPDATE documents
          SET deleted = true,
              version = version + 1
          WHERE id = ? AND version = ?
          """
)
@SQLRestriction("deleted = false")
public class Document {

    @Id
    private Long id;

    @Version
    private long version;

    @Column(nullable = false)
    private boolean deleted = false;

    private String title;
}
```

Khi entity có `@Version`, Hibernate thường kỳ vọng các JDBC placeholders của custom delete theo thứ tự:

1. Primary key column(s).
2. Version column.

Ở ví dụ: `id = ?` rồi `version = ?`. Nếu dùng composite ID, phải biết chính xác thứ tự các cột identifier theo mapping. **Không tự đoán số lượng hoặc vị trí placeholder** trên entity có partition key, secondary tables hay mapping đặc thù.

### 10.1. Vì sao WHERE version quan trọng?

Nếu transaction A và B cùng đọc Document#101 ở version 4, rồi A sửa thành version 5, B không nên “xóa mềm” dựa trên stale version 4 mà không phát hiện conflict.

SQL có guard:

```sql
UPDATE documents
SET deleted = true, version = version + 1
WHERE id = ? AND version = ?;
```

sẽ ảnh hưởng 0 row khi version không còn khớp. Nhưng Hibernate chỉ biết đây là conflict nếu **cơ chế xác minh kết quả update** được cấu hình phù hợp và dialect/driver báo affected row count đáng tin.

### 10.2. Kiểm tra số row được tác động

Trong Hibernate 6.5/6.6, `@SQLDelete` có thuộc tính `verify` với `Expectation.RowCount`:

```java
import org.hibernate.jdbc.Expectation;

@Entity
@Table(name = "documents")
@SQLDelete(
    sql = """
          UPDATE documents
          SET deleted = true,
              version = version + 1
          WHERE id = ? AND version = ? AND deleted = false
          """,
    verify = Expectation.RowCount.class
)
@SQLRestriction("deleted = false")
public class Document {
    @Id
    private Long id;
    @Version
    private long version;
    private boolean deleted;
}
```

`Expectation.RowCount` yêu cầu số affected rows phù hợp. Khi SQL không tác động bản ghi vì version cũ hoặc đã bị xóa trước đó, ứng dụng có thể nhận failure/stale state thay vì tưởng thành công.

**Lưu ý version:** `verify` là API Hibernate-specific; `check`/`ResultCheckStyle` trong các ví dụ cũ đã deprecated ở Hibernate 6.5. Chọn API theo phiên bản đang chạy.

### 10.3. Có nên tự tăng version trong custom UPDATE?

Đoạn `version = version + 1` biểu diễn một cách duy trì monotonic version trên row thực tế, nhưng cần xác nhận với kiểu version và cơ chế mapping. Không viết phép cộng cho một version type không hỗ trợ số học. Nếu version dùng timestamp hoặc logic tùy biến, cần SQL/strategy khác.

### 10.4. `@Version` không thay uniqueness và authorization

Optimistic locking chỉ kiểm soát concurrent updates trên một row. Nó không tự kiểm soát quyền xóa document hoặc ngăn hai active rows có cùng email. Những điều đó cần business validation và DB constraints riêng.

## 11. Hai con đường khác: soft delete qua service thay vì `@SQLDelete`

Không phải hệ thống nào cũng muốn `em.remove(entity)` có nghĩa là UPDATE.

Một cách biểu diễn rõ business rule:

```java
@Entity
@Table(name = "customer_accounts")
public class CustomerAccount {
    @Id
    private Long id;

    @Version
    private long version;

    @Column(nullable = false)
    private boolean deleted = false;

    private Instant deletedAt;

    public void softDelete(Instant now) {
        if (deleted) {
            return;
        }
        deleted = true;
        deletedAt = now;
    }

    public void restore() {
        if (!deleted) {
            return;
        }
        deleted = false;
        deletedAt = null;
    }
}
```

Service:

```java
@Transactional
public void deactivate(Long id, Instant now) {
    CustomerAccount account = em.find(CustomerAccount.class, id);
    if (account == null) {
        throw new EntityNotFoundException();
    }

    checkPermissionToDelete(account);
    account.softDelete(now);
}
```

Đây là **entity UPDATE thông thường** do dirty checking, không phải `remove` và không cần `@SQLDelete`. Nếu muốn các truy vấn mặc định loại deleted rows, cần tự thêm WHERE/filter/repository policy phù hợp.

### 11.1. Ưu điểm

- Có thể mô hình hóa `deletedAt`, `deletedBy`, `reason`, status transitions.
- Dễ định nghĩa `restore()` như một transition hợp lệ.
- `@Version` hoạt động như managed entity update thông thường.
- Entity vẫn managed sau `softDelete()` trong transaction.
- Envers (nếu bật) có thể nhận đây là entity MOD thay vì REMOVE event.

### 11.2. Nhược điểm

- Những caller vẫn có thể gọi `repository.delete(...)`/`em.remove(...)` và tạo physical delete nếu không có mapping/cơ chế bảo vệ.
- Mọi read paths phải lọc đúng status.
- Cần thống nhất API repository, security và các write paths.
- Nếu dùng `@SQLRestriction` tĩnh che bản ghi, chính cùng entity mapping có thể khó load bản ghi đã xóa để restore.

Vì vậy service-level soft delete phù hợp khi domain cần **trạng thái xóa như một nghiệp vụ rõ ràng**, nhưng phải chặn các đường xóa vật lý ngoài ý muốn.

### 11.3. Không trộn remove và softDelete bừa bãi

Đừng vừa gọi:

```java
account.softDelete(Instant.now());
em.remove(account);
```

mà không chủ động định nghĩa muốn Hibernate chạy UPDATE do dirty checking hay custom `@SQLDelete`. State transitions và SQL có thể chồng chéo; audit/history cũng khó suy luận. Chọn một chiến lược write rõ cho từng use case.

## 12. Bộ lọc tĩnh `@SQLRestriction` và bộ lọc động `@Filter`

Nếu mục tiêu read model là “mặc định chỉ thấy active, nhưng admin có thể xem deleted”, restriction tĩnh là một công cụ có giới hạn.

### 12.1. `@SQLRestriction` luôn áp dụng

```java
@SQLRestriction("deleted = false")
```

Ưu điểm: an toàn cho những use case không bao giờ muốn thấy deleted row qua entity mapping.

Hạn chế: không thể enable/disable hoặc bind parameter theo request.

### 12.2. `@Filter` là dynamic Hibernate filter

Ví dụ với Hibernate `@FilterDef` và `@Filter`:

```java
import org.hibernate.annotations.Filter;
import org.hibernate.annotations.FilterDef;

@Entity
@Table(name = "customer_accounts")
@FilterDef(name = "notDeletedOnly")
@Filter(
    name = "notDeletedOnly",
    condition = "deleted = false"
)
public class CustomerAccount {
    @Id
    private Long id;
    private boolean deleted;
}
```

Trong service:

```java
Session session = em.unwrap(Session.class);

session.enableFilter("notDeletedOnly");
try {
    List<CustomerAccount> visible = session.createQuery(
            "from CustomerAccount",
            CustomerAccount.class
        )
        .getResultList();
} finally {
    session.disableFilter("notDeletedOnly");
}
```

Filter là **Session-scoped**. Khi không bật, truy vấn có thể bao gồm deleted rows. Vì vậy nếu hệ thống đòi mặc định không thấy deleted, chỉ dùng `@Filter` bật bằng tay ở một vài service có thể để lọt dữ liệu.

### 12.3. Cẩn thận với `findById` và direct loads

Không giả định mọi filter runtime tự áp vào tất cả các đường load-by-key và association trong mọi Hibernate version. Cần integration tests cụ thể cho:

- `EntityManager.find`/`Session.get`.
- HQL/Criteria list queries.
- To-one lazy associations.
- To-many collections.
- L2-cache hits hoặc entity đã managed trong L1.
- Tình huống filter được bật sau khi entity đã tải.

Một filter bật sau không tự xóa object đã managed. Nếu bảo mật/tenant isolation phụ thuộc filter, cần thiết kế cơ chế mạnh hơn, không chỉ hy vọng Session filter luôn được bật đúng.

### 12.4. Không dùng cả restriction tĩnh và filter để “cho admin xem deleted”

Nếu entity đã có `@SQLRestriction("deleted = false")`, bật hay tắt `@Filter` không xóa restriction tĩnh. Admin vẫn khó load deleted rows qua cùng entity mapping.

Các lựa chọn include-deleted cần được thiết kế riêng: admin/native read query, entity mapping khác được phân quyền, hoặc mô hình status service có khả năng query đủ trạng thái.

### 12.5. Khi nào chọn loại nào?

| Yêu cầu | Gợi ý |
|---|---|
| Mọi load qua ORM phải ẩn deleted | `@SoftDelete` mới hoặc restriction tĩnh phù hợp |
| Có phiên bản ORM cũ; muốn legacy soft delete | `@SQLDelete` + restriction/filter được kiểm thử |
| Admin cần xem cả active/deleted | Read model riêng, API/SQL có authorization; hoặc dynamic filter được thiết kế mặc định an toàn |
| Filter thay đổi theo request/tenant | `@Filter` là công cụ kỹ thuật, nhưng phải kiểm soát scope và load paths |
| Hệ thống ghi và restore rõ trạng thái | Service-managed status + repository policies |
| Cần database-level bảo đảm mọi client | DB security/views/triggers/constraints theo yêu cầu, không chỉ Hibernate annotations |



## 13. Liên hệ với `@SQLJoinTableRestriction` và các collection

Một entity có thể được ẩn đúng ở truy vấn root nhưng vẫn có vấn đề với các association.

Ví dụ:

```java
@Entity
public class Project {
    @Id
    private Long id;

    @OneToMany(mappedBy = "project")
    private List<Task> tasks;
}
```

`Task` có cột `deleted`. Màn hình Project chỉ nên hiển thị tasks chưa bị xóa mềm.

### 13.1. Predicate trên target entity

Với `Task` được map cùng `@SQLRestriction("deleted = false")`, Hibernate có thể thêm restriction vào SQL load Task/association trong phạm vi hỗ trợ. Cần xác nhận generated SQL khi load collection, nhất là với mappings đặc thù và cache.

### 13.2. Predicate trên collection

Một restriction đặt ở collection role:

```java
@OneToMany(mappedBy = "project")
@SQLRestriction("deleted = false")
private List<Task> tasks;
```

có thể dùng khi chỉ muốn giới hạn association ở riêng collection đó. Annotation nhận **SQL fragment**, nên tên cột phải đúng với target table SQL được Hibernate tạo.

**Không nhầm:** đặt restriction trên collection không tự làm delete child thành UPDATE. Cần write policy cho Task riêng.

### 13.3. ManyToMany join table cũng có trạng thái

Nếu join table chứa cột `active` để thể hiện liên kết bị thu hồi, có thể dùng `@SQLJoinTableRestriction` cho **bản thân join table**, khác với restriction cho target entity.

Ví dụ ý tưởng:

```java
@ManyToMany
@JoinTable(name = "team_memberships")
@SQLJoinTableRestriction("active = true")
private Set<User> members;
```

Câu SQL sẽ phụ thuộc mapping, dialect và naming strategy. Nếu join table không có cột `active`, annotation này không làm nó tự xuất hiện.

### 13.4. Xóa mềm association không đồng nghĩa xóa mềm entity

Khi xóa một membership ở join table, business có thể muốn đánh dấu liên kết không active nhưng giữ cả User và Team. Đó là soft delete của **association row**, không phải User entity.

Với nhiều metadata như join time, role, deletedAt, deletedBy, thường nên mô hình hóa join table thành **entity riêng** (`Membership`) thay vì `@ManyToMany` thuần. Khi đó lifecycle, unique index, audit và restore rõ ràng hơn.

## 14. Cascade REMOVE và orphanRemoval: bẫy quan trọng

Một parent có children:

```java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.REMOVE,
    orphanRemoval = true
)
private List<OrderLine> lines;
```

Nếu parent được xóa mềm, câu hỏi: children có bị xóa logic theo không? Không thể trả lời chỉ bằng việc nhìn `@SQLDelete` của parent.

### 14.1. CascadeType.REMOVE

Khi `em.remove(parent)`, Hibernate có thể cascade REMOVE tới child entities, tùy mapping. Nếu child không có soft-delete mechanism, child có thể bị physical DELETE ngay cả khi parent chỉ bị soft-deleted.

Nếu business muốn giữ tất cả child records, phải kiểm tra cascade rules và soft-delete mapping cho child. Không tự bật CascadeType.REMOVE trên mọi quan hệ vì cho rằng “cascade sẽ chỉ đổi deleted flag”.

### 14.2. orphanRemoval

`orphanRemoval = true` có thể khiến Hibernate xóa child entity khi bị loại khỏi collection. Nếu child có custom `@SQLDelete`, đường entity delete có thể đi qua custom SQL; nhưng vẫn cần kiểm tra SQL thực tế, join-table actions và collection semantics.

Thao tác:

```java
order.getLines().remove(line);
```

khác về domain với “xóa mềm cả Order”. Bạn có thể muốn child thành orphan rồi physical delete, hoặc muốn giữ child để audit. Cần xác định quy tắc, không dùng một annotation cho tất cả.

### 14.3. DB ON DELETE CASCADE không chạy với UPDATE flag

`ON DELETE CASCADE` là rule khi parent row **bị DELETE vật lý**. Soft delete bằng:

```sql
UPDATE orders SET deleted = true WHERE id = ?;
```

không kích hoạt hành vi ON DELETE CASCADE do **không có physical DELETE**.

Nếu business đòi “xóa mềm parent thì child cũng bị ẩn”, cần application policy, child flag, query filter theo parent status hoặc DB trigger chuyên biệt. Không dựa vào database cascade DELETE.

### 14.4. To-one tham chiếu tới row bị ẩn

Giả sử OrderLine giữ FK tới Product#101 và Product#101 đã deleted. Nếu entity Product có restriction tự ẩn, việc load `line.getProduct()` có thể gặp tình huống target không tìm thấy theo mapping.

Tùy Hibernate version, mapping và fetch style, biểu hiện có thể là null, proxy không khởi tạo được hoặc exception. Với quan hệ bắt buộc, đây là một bài toán domain: lịch sử đơn hàng vẫn cần tên sản phẩm đã bán dù catalog item đã bị ẩn.

Cách giải thường là lưu snapshot (SKU, name, price tại thời điểm đặt hàng) trong OrderLine hoặc sử dụng read model lịch sử riêng, không phụ thuộc việc load Product đã bị soft-delete.

## 15. Bulk HQL/JPQL DELETE có nhất thiết đi qua `@SQLDelete` không?

Không. Đây là một bẫy phổ biến.

### 15.1. Entity remove và bulk delete khác nhau

Đường entity lifecycle:

```java
CustomerAccount account = em.find(CustomerAccount.class, id);
em.remove(account);
```

Hibernate có entity instance và xử lý removal theo persistence context. `@SQLDelete` được thiết kế cho đường này.

Bulk HQL mutation:

```java
int count = em.createQuery(
        "delete from CustomerAccount a where a.id in :ids"
    )
    .setParameter("ids", ids)
    .executeUpdate();
```

là thao tác **bulk mutation trực tiếp** ở database. Nó không load từng CustomerAccount rồi gọi `em.remove`. Vì vậy **đừng giả định custom `@SQLDelete` được áp cho từng row**. SQL có thể là physical DELETE hoặc được dịch bởi những cơ chế mapping khác theo phiên bản. Điều bắt buộc là phải xác minh generated SQL và semantics của bulk delete trong stack thực tế.

### 15.2. Spring Data JPA batch delete variants

Các method có tên tương tự:

```java
repository.delete(entity);
repository.deleteById(id);
repository.deleteAllInBatch();
repository.deleteAllByIdInBatch(ids);
```

không nhất thiết có cùng con đường thực thi:

- Các delete method dùng `EntityManager.remove` trên managed entities thường đi qua lifecycle như trên.
- Batch/bulk delete methods của Spring Data JPA có thể tạo JPQL bulk DML và bỏ qua per-entity lifecycle/cascade.
- `@Modifying @Query("delete from ...")` rõ ràng là bulk delete.
- Delete semantics có thể khác giữa Spring Data versions và các repository overrides/customizations.

Với hệ thống cần bảo toàn soft-delete policy, hãy **cấm/kiểm tra các đường bulk delete không chủ ý**, không dựa vào tên method chứa chữ `delete`.

### 15.3. Hibernate @SoftDelete và HQL mutation

Hibernate 6.4+ tích hợp soft-delete semantics sâu hơn mapping legacy, nhưng hành vi của từng dạng bulk HQL mutation vẫn cần kiểm tra ở phiên bản cụ thể; đừng biến một ví dụ `delete from Entity` thành bằng chứng mọi ORM/native write path đều an toàn.

Một integration test cần assert:

1. Bảng chính còn row hay không.
2. Cờ deleted đã đổi đúng hay chưa.
3. L2/query cache còn nhất quán không.
4. Bản ghi child và FK có bị ảnh hưởng ngoài ý muốn không.
5. Audit/history có ghi đúng nghiệp vụ không.

### 15.4. HQL UPDATE flag thủ công cũng cần lưu ý

Một bulk HQL UPDATE:

```hql
update CustomerAccount a
set a.deleted = true
where a.id in :ids
```

có thể có nghĩa khác `remove` tùy cách mapping, và bypass dirty checking/per-entity callbacks. Nếu entity dùng `@SQLRestriction` hoặc `@SoftDelete` nội bộ, update restrictions/indicator mapping có thể khác dự kiến.

Đừng sửa bulk query dựa trên ví dụ chung mà không kiểm tra SQL và cache semantics; đặc biệt không sửa indicator nội bộ `@SoftDelete` bằng HQL khi field Java không được mapped như property.

## 16. Native SQL, JDBC và external writers

`@SQLDelete` là annotation của Hibernate. Các thao tác:

```java
jdbcTemplate.update(
    "delete from customer_accounts where id = ?",
    accountId
);
```

hoặc:

```sql
DELETE FROM customer_accounts WHERE id = 101;
```

do DBA, ETL, stored procedure hay ứng dụng khác chạy **không đi qua `@SQLDelete`**.

Tương tự, Hibernate native SQL:

```java
em.createNativeQuery(
        "DELETE FROM customer_accounts WHERE id = :id"
    )
    .setParameter("id", id)
    .executeUpdate();
```

thực thi SQL do bạn chỉ định; nó không được tự viết lại thành custom `@SQLDelete` trên entity.

### 16.1. Chính sách xóa mềm toàn hệ thống cần thống nhất write paths

Nếu có nhiều service cùng ghi bảng, cần cân nhắc:

- Database privileges: không cấp DELETE tùy ý cho application user không được phép hard-delete.
- Chỉ cho phép write qua API/service đã kiểm tra quyền.
- Database trigger hoặc stored procedure khi cần bắt buộc giữ tombstone.
- Định nghĩa retention/purge job được cấp quyền riêng.
- Monitoring để phát hiện physical deletes ngoài dự kiến.
- CDC/replication nếu các hệ thống cần biết trạng thái xóa.

Chỉ có annotation trong một microservice không thể bắt mọi ứng dụng khác tuân theo.

### 16.2. Native SELECT cũng bỏ qua read restriction

```java
em.createNativeQuery(
    "select id, email, deleted from customer_accounts"
);
```

không tự được Hibernate thêm `WHERE deleted = false` chỉ vì entity có `@SQLRestriction`, đặc biệt khi kết quả không được ánh xạ qua query generation cho entity. Phải tự thêm điều kiện phù hợp hoặc dùng DB view/policy riêng.

Với các SQL báo cáo/ETL, nên nêu rõ “active-only” hay “include deleted” trong query contract.

## 17. Khôi phục bản ghi đã xóa mềm

Khả năng **undelete/restore** thường là một yêu cầu nghiệp vụ riêng với xóa mềm. Điều kiện khôi phục có thể gồm:

- Có quyền admin.
- Bản ghi chưa vượt thời gian purge.
- Không có active row khác chiếm email/SKU duy nhất.
- Owner/tenant vẫn tồn tại.
- Trạng thái các child records còn hợp lệ.
- Không vi phạm business workflow.

### 17.1. Vì sao không thể đơn giản gọi `em.find` rồi set false khi có restriction?

Với:

```java
@SQLRestriction("deleted = false")
```

bản ghi deleted bị loại khỏi ORM loads thông thường. `em.find(CustomerAccount.class, id)` có thể trả null dù row vẫn tồn tại trong DB. Vì thế method:

```java
CustomerAccount a = em.find(CustomerAccount.class, id);
a.setDeleted(false);
```

không phải một đường restore đáng tin trên mapping đã ẩn tombstone.

### 17.2. Restore trong service quản trị riêng

Có thể dùng native SQL trong transaction:

```java
@Transactional
public boolean restore(Long id) {
    int affected = em.createNativeQuery(
            """
            UPDATE customer_accounts
            SET deleted = false
            WHERE id = :id AND deleted = true
            """
        )
        .setParameter("id", id)
        .executeUpdate();

    em.clear(); // Bỏ managed state cũ trong context hiện tại.
    return affected == 1;
}
```

Đây chỉ là ví dụ **cơ chế SQL**, chưa đủ authorization/constraints/cache consistency. Khi dùng JDBC hoặc native SQL, cần xem Hibernate synchronization/eviction cho L2/query cache và transaction timing; `em.clear()` **chỉ xử lý L1**, không làm L2 tự hết stale.

### 17.3. Restore trên versioned entity

Nếu row có `version`, một restore cần guard chống race và có thể tăng version:

```sql
UPDATE customer_accounts
SET deleted = false, version = version + 1
WHERE id = :id
  AND deleted = true
  AND version = :expected_version;
```

`:expected_version` phải lấy từ một nguồn được xác thực theo workflow admin; không tin client có quyền khôi phục chỉ vì đoán được version. Kiểm tra affected rows và phản hồi conflict phù hợp.

### 17.4. @SoftDelete không tự đồng nghĩa có restore API

Mapping `@SoftDelete` thường làm Hibernate ẩn entity đã xóa; vì thế việc restore có thể cần read/write path tách biệt với entity mapping bình thường. Với các miền nghiệp vụ restore thường xuyên, đôi khi **trạng thái nghiệp vụ được quản lý bằng managed entity UPDATE** dễ kiểm soát hơn soft-delete hidden mapping.

### 17.5. Khôi phục child/parent không đơn giản là đổi một flag

Nếu Order đã soft-delete mà các OrderLine cũng bị đánh dấu deleted, khôi phục Order có nên khôi phục mọi line? Nếu line đã bị xóa độc lập trước khi parent bị xóa, không nên khôi phục nhầm line đó.

Cần phân biệt:

- Line bị xóa do parent cascade soft delete.
- Line bị người dùng xóa trước đó.
- Line bị purge hẳn.
- Dữ liệu referenced đã biến mất.
- Business status đã thay đổi sau khi xóa.

Một schema chỉ có `deleted BOOLEAN` không lưu đủ nguyên nhân để quyết định tự động. Có thể cần deletion group ID, snapshot hoặc events để phục hồi đúng.

## 18. Hard delete/purge sau retention

Soft delete thường là trạng thái tạm thời hoặc dành cho lưu trữ dài hạn; database vẫn giữ row và indexes. Nếu retention cho phép, có thể cần purge vĩnh viễn.

### 18.1. Purge là operation khác remove trên soft-deleted entity

Nếu Hibernate mapping đã có `@SQLDelete`, gọi:

```java
em.remove(account);
```

không phải cách chắc chắn để hard-delete, bởi ORM sẽ dùng custom UPDATE thay vì DELETE. Với `@SQLRestriction`, row đã deleted cũng không tải được qua normal entity load để gọi remove lần thứ hai.

Purge nên là một **service/job riêng** được phân quyền, dùng SQL/DB API rõ ràng và biết các foreign keys, retention constraints, legal holds.

### 18.2. Ví dụ SQL purge có guard

```sql
DELETE FROM customer_accounts
WHERE deleted = true
  AND deleted_at < :cutoff
  AND legal_hold = false;
```

Đây là SQL minh họa; schema phải có các cột `deleted_at` và `legal_hold` mới dùng được. Trên bảng lớn, nên purge theo batch/partition, có monitoring, tránh một DELETE khổng lồ giữ lock và tạo WAL/redo đột biến.

### 18.3. Không dùng soft delete làm giải pháp compliance mặc định

Có dữ liệu nhạy cảm bị xóa “trên UI” nhưng vẫn nằm ở DB, backups, audit tables hoặc replicas. Cần retention, right-to-erasure, anonymization và quyền truy cập theo quy định áp dụng. `@SQLDelete` không tự xóa PII khỏi hệ thống.

## 19. Unique constraints: xóa mềm nhưng không tạo lại được email?

Giả sử schema có:

```sql
ALTER TABLE customer_accounts
ADD CONSTRAINT uq_customer_email UNIQUE (email);
```

Tài khoản `an@example.test` bị soft-delete; row vẫn còn trong table, nên người khác có thể không tạo được tài khoản mới với cùng email.

### 19.1. Định nghĩa lại business uniqueness

Có hai chính sách khác nhau:

1. **Email duy nhất vĩnh viễn**, kể cả tài khoản đã xóa. Giữ UNIQUE(email) có thể đúng.
2. **Email chỉ duy nhất giữa active accounts**. Cần index/constraint áp dụng riêng active rows.

Chọn theo nghiệp vụ, không tự thay constraint chỉ vì có soft delete.

### 19.2. Partial unique index trên PostgreSQL

Nếu uniqueness chỉ cần trên active rows:

```sql
CREATE UNIQUE INDEX uq_customer_email_active
ON customer_accounts (lower(email))
WHERE deleted = false;
```

Đây là **PostgreSQL-specific**. Cần đồng bộ cách chuẩn hóa email (lowercase, trimming, collation) với business rule và queries. Với database khác, dùng cơ chế filtered index, generated column hoặc cấu trúc tương đương được hỗ trợ.

Không mặc định một `UNIQUE(email, deleted)` là thay thế hoàn hảo: nó có thể chỉ cho phép **một** deleted row của cùng email trong khi lịch sử có thể có nhiều tài khoản đã xóa.

### 19.3. Restore có thể vi phạm unique index

Khi tài khoản A bị xóa, tài khoản B mới có cùng email được tạo, rồi admin khôi phục A: việc đặt `deleted = false` trên A sẽ vi phạm unique index active-only.

Restore phải có workflow giải quyết conflict, có thể đổi email, hợp nhất account hoặc từ chối restore. Đây là vấn đề business, không phải bug Hibernate.

### 19.4. Foreign keys vẫn nhìn thấy soft-deleted rows

FK trên database vẫn hợp lệ vì row chưa bị DELETE. Điều này giúp giữ order history, nhưng có thể tạo khác biệt giữa **tính tồn tại vật lý** và **khả năng load qua ORM** khi restriction ẩn target. Cần thiết kế read model lịch sử phù hợp.

## 20. Cache L1, L2 và query cache khi xóa mềm

### 20.1. L1 cache

Khi entity đã được load trong một `EntityManager`, persistence context giữ managed instance. Sau khi Session khác soft-delete và commit, entity trong L1 cũ **không tự biến mất** chỉ vì database flag đã đổi hoặc L2 đã invalidated.

`em.clear()`/`em.refresh()`/mở context mới có semantics khác nhau. `refresh` có thể không phù hợp nếu entity đã bị soft-deleted và bị restriction loại khỏi load.

### 20.2. L2 cache và query cache

Một JPA `remove` được Hibernate quản lý thường kích hoạt cơ chế cache eviction/update phù hợp với entity lifecycle. Nhưng nếu custom `@SQLDelete` là một UPDATE thực tế, cache provider vẫn cần không phục vụ lại state như thể entity còn active.

Trên những đường ghi thủ công:

```java
jdbcTemplate.update(
    "UPDATE customer_accounts SET deleted = true WHERE id = ?",
    id
);
```

Hibernate không tự biết mutation. L2 entity region hoặc query result cache có thể stale. Cần transaction-aware invalidation và kiểm chứng bằng Session mới.

### 20.3. Hibernate query cache không phải business search index

Một query cache result “active accounts” có thể cần invalidation khi row chuyển từ active sang deleted. Nhưng Elasticsearch, Redis app cache, CDN, API response cache hoặc các read models ngoài Hibernate **không tự được Hibernate cập nhật**.

Nếu xóa mềm phải biến account khỏi search trong vài giây, cần event/CDC/invalidation tích hợp riêng và xác định SLA freshness.

### 20.4. Đừng dùng caching để che thiếu restriction

Nếu query active-only chỉ nhờ một entity đã được L2 cache theo cách nào đó, sau cache miss có thể xuất hiện row deleted. Filtering phải được mô hình hóa rõ, không phụ thuộc một trạng thái cache may mắn.

## 21. Auditing và `@SQLDelete`: soft delete chưa phải lịch sử

Nếu cần biết **ai xóa, khi nào, vì sao** thì chỉ có `deleted = true` là chưa đủ. Có thể thêm:

```sql
deleted_at TIMESTAMP NULL,
deleted_by VARCHAR(100) NULL,
delete_reason VARCHAR(500) NULL
```

Nhưng cách lấy và ghi metadata phải được thiết kế riêng.

### 21.1. Envers nhìn thấy entity remove hay managed update?

Hibernate Envers (`@Audited`) nhận entity events. Nếu bạn dùng `em.remove(entity)` và `@SQLDelete` biến SQL thành UPDATE, Envers có thể coi thao tác là **entity removal** theo event lifecycle, chứ không mặc định là một business MOD do flag chuyển false→true.

Nếu bạn dùng service-managed flag update trên managed entity, Envers thường nhận một entity modification. Vì vậy history representation có thể khác nhau dù DB row cuối cùng giống nhau.

**Không suy luận từ tên REVTYPE/đường SQL một cách tuyệt đối**; viết integration test trên mapping/version thực tế.

### 21.2. Bulk/native SQL bypass per-entity audit

Một `DELETE FROM Entity` HQL bulk hoặc raw SQL UPDATE không tự tạo đầy đủ Envers audit rows như cập nhật từng managed entity. Nếu audit là yêu cầu bắt buộc, phải thiết kế toàn bộ write paths.

### 21.3. `@PreRemove` không tự cập nhật đầy đủ cột

Có thể muốn:

```java
@PreRemove
void markDeleted() {
    deletedAt = Instant.now();
}
```

Nhưng callback PRE_REMOVE nằm trong lifecycle removal; nếu custom SQL chỉ có `SET deleted = true` thì Hibernate **không tự thêm** `deleted_at` vào câu SQL. Thay đổi field Java trong callback không đảm bảo giá trị đó được persist theo cách bạn kỳ vọng.

Muốn cột deleted_at chính xác, hãy dùng SQL cụ thể, DB function, hoặc domain service UPDATE tùy thiết kế. Test giá trị DB sau commit, không chỉ assert object Java.

## 22. Multi-tenancy, quyền truy cập và tính đúng đắn của custom SQL

Nếu bảng có tenant ID:

```sql
CREATE TABLE customer_accounts (
    tenant_id BIGINT NOT NULL,
    id BIGINT NOT NULL,
    email VARCHAR(255) NOT NULL,
    deleted BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (tenant_id, id)
);
```

thì mọi query và mutation phải tôn trọng tenant isolation.

### 22.1. Custom SQL phải khớp identifier mapping

Nếu PK là composite `(tenant_id, id)`, custom `@SQLDelete` thường cần đủ placeholders cho identifier columns và đúng thứ tự Hibernate kỳ vọng. Không dùng:

```java
@SQLDelete(
    sql = "UPDATE customer_accounts SET deleted = true WHERE id = ?"
)
```

một cách máy móc khi entity ID bao gồm tenant_id hoặc có partition key constraints. Có thể update nhầm hoặc làm affected rows khác dự kiến.

### 22.2. Security không chỉ là predicate trong @SQLRestriction

`@SQLRestriction("deleted = false")` không chặn tenant A nhìn tenant B. Cần row-level security, Hibernate multitenancy/filter phù hợp, repository predicates và authorization.

Tương tự, không cho client gửi arbitrary SQL sort/filter để “include deleted”; API admin phải được phân quyền rõ.

### 22.3. Tenant-aware native admin operations

Restore/purge SQL nên có tenant constraint ngay trong WHERE:

```sql
UPDATE customer_accounts
SET deleted = false
WHERE tenant_id = :tenantId
  AND id = :id
  AND deleted = true;
```

Đây là cách biểu diễn business guard trong SQL, nhưng application vẫn phải xác thực `tenantId` từ security context đáng tin và kiểm tra affected row count. Nếu database có RLS, phải cấu hình DB role/session correctly.

### 22.4. SQLDelete với RowCount verification

Một custom SQL có guard `AND deleted=false` có thể tác động 0 row khi xóa lại tombstone hoặc khi row đã được transaction khác sửa/xóa. Nếu không kiểm tra affected row count, caller có thể tưởng thao tác xóa thành công. Cân nhắc `verify = Expectation.RowCount.class` trong Hibernate 6.5+ khi phù hợp.

## 23. Thời điểm transaction và concurrency

### 23.1. Remove chưa chắc đã chạy SQL ngay

```java
@Transactional
public void delete(Long id) {
    CustomerAccount a = em.find(CustomerAccount.class, id);
    em.remove(a);

    // Hibernate có thể thực thi UPDATE custom ở flush/commit.
}
```

`remove` thay trạng thái entity trong persistence context. SQL custom có thể được gửi khi flush theo action queue, tùy generator/mapping/flush mode.

### 23.2. Flush không phải commit

```java
em.remove(a);
em.flush();
```

SQL có thể đã được thực thi trong transaction, nhưng nếu transaction rollback, trạng thái row DB phải trở về theo semantics database transactional. Không được coi “đã gọi flush” là deletion event đã commit.

### 23.3. Two concurrent deletes

Hai requests cùng soft-delete một row:

- Nếu custom SQL `SET deleted=true WHERE id=?`, cả hai có thể ghi lại cùng trạng thái và không phát hiện conflict.
- Nếu SQL có `AND deleted=false` và RowCount verification, request thứ hai có thể bị coi là stale/missing.
- Nếu có `@Version` trong WHERE, một transaction có thể nhận optimistic locking failure.
- Nếu business yêu cầu idempotent DELETE, “xóa lần hai” có thể là thành công về mặt API dù DB row đã deleted; cơ chế báo status code là quyết định service layer.

Không mặc định `Expectation.RowCount` là lựa chọn duy nhất; nó phù hợp khi muốn nhận biết stale/duplicate operations, nhưng business có thể chọn semantics idempotent và xử lý 0 affected rows theo cách khác.

### 23.4. Concurrent restore và create cùng email

Với partial unique index, database uniqueness là lớp cuối cùng để ngăn hai active accounts cùng email. Dù application đã check “email còn trống”, một transaction khác có thể tạo record mới trước khi restore commit. Phải xử lý unique constraint violation, transaction rollback và retry/conflict response.

### 23.5. Delete với ongoing background job

Worker có thể đã load account trước khi nó bị soft-delete. Nếu nó vẫn dùng managed instance lâu hoặc dữ liệu đã cache, job có thể tiếp tục xử lý account không còn active. Cần boundary, version/token/active check và side-effect policy phù hợp với nghiệp vụ, không chỉ ẩn row ở API.

## 24. Chuyển từ xóa vật lý sang xóa mềm trên production

Đây là schema và behavior migration, không phải thay một annotation rồi deploy.

### 24.1. Pha 1: kiểm kê

Xác định:

- Các entity cần soft-delete.
- Những `remove`/delete Spring Data repository calls.
- Bulk DML, native SQL, JDBC jobs, ETL và external writers.
- Cascade và `orphanRemoval`.
- FK/unique constraints, index, queries, admin/search/cache.
- Retention/compliance và rollback requirements.

### 24.2. Pha 2: mở rộng schema

Ví dụ PostgreSQL:

```sql
ALTER TABLE customer_accounts
ADD COLUMN deleted BOOLEAN NOT NULL DEFAULT FALSE;
```

Trên bảng rất lớn và nhiều database versions, DDL có thể có lock/rewrite implications. Có thể cần staged nullable column + backfill + NOT NULL constraint validation thay vì một thao tác trực tiếp; chọn theo DB/dialect thực tế.

Nếu dùng `@SQLDelete` với `deleted_at`, thêm cột và indexes cần thiết. Nếu dùng `@SoftDelete`, bảo đảm indicator column có type/default/values tương thích với strategy.

### 24.3. Pha 3: triển khai write/read policy

Chọn một trong các hướng:

**A — Hibernate 6.4+:** `@SoftDelete` tích hợp.

**B — Hibernate legacy:** `@SQLDelete` + `@SQLRestriction`/`@Where` hoặc filter phù hợp với version, kèm read/admin paths.

**C — Business status:** service-managed update `deleted/deletedAt` + repository query policy rõ.

Không “mix and match” tất cả annotations khi không hiểu precedence và mapping ownership.

### 24.4. Pha 4: dữ liệu cũ và read paths

Nếu các row cũ mặc định active, backfill `deleted=false`. Thêm index hỗ trợ active-only queries. Kiểm tra null semantics và unique constraints. Đảm bảo các HQL/named/native queries, reports và search indexes đều hiểu chính sách mới.

### 24.5. Pha 5: mixed-version deployment

Nếu node cũ vẫn physical DELETE trong rolling deployment, một số requests có thể tiếp tục xóa thật khi node mới đã soft-delete. Nếu yêu cầu không được mất dữ liệu, cần chặn old delete paths trước hoặc dùng database-level protection/cutover.

Rollback code cũng có thể khiến app cũ không hiểu indicator mới. Không coi schema additive là bằng chứng mọi writer cũ đã an toàn.

### 24.6. Pha 6: kiểm thử và theo dõi

Cần đo:

- Số row bị physical DELETE sau cutover.
- Số row có deleted=true.
- API active-only query counts.
- Delete success/failure/stale row counts.
- Soft-deleted child/parent consistency.
- Restore conflicts và purge job behavior.
- Cache/search freshness.
- Query latency và index selectivity.

## 25. Thử nghiệm trực tiếp với hai mapping

### 25.1. Schema khởi đầu

```sql
CREATE TABLE notes (
    id BIGINT PRIMARY KEY,
    title VARCHAR(100) NOT NULL,
    deleted BOOLEAN NOT NULL DEFAULT FALSE
);

INSERT INTO notes (id, title, deleted)
VALUES
  (1, 'Ghi chú A', FALSE),
  (2, 'Ghi chú B', FALSE);
```

### 25.2. Mapping kiểu legacy

```java
@Entity
@Table(name = "notes")
@SQLDelete(
    sql = "UPDATE notes SET deleted = true WHERE id = ?",
    verify = Expectation.RowCount.class
)
@SQLRestriction("deleted = false")
public class Note {

    @Id
    private Long id;

    @Column(nullable = false)
    private String title;

    @Column(nullable = false)
    private boolean deleted = false;

    protected Note() {}

    public Long getId() { return id; }
    public String getTitle() { return title; }
}
```

Import:

```java
import jakarta.persistence.*;
import org.hibernate.annotations.SQLDelete;
import org.hibernate.annotations.SQLRestriction;
import org.hibernate.jdbc.Expectation;
```

Trên Hibernate 6.5+, ví dụ `verify` tương thích với annotation API. Với phiên bản cũ hơn, hãy tham khảo API tương ứng.

### 25.3. Các bước quan sát

Bên trong transaction:

```java
Note note = em.find(Note.class, 1L);
em.remove(note);
em.flush();
```

SQL kỳ vọng về semantics:

```sql
UPDATE notes SET deleted = true WHERE id = ?;
```

Sau commit, query database trực tiếp:

```sql
SELECT id, title, deleted FROM notes ORDER BY id;
```

Kết quả:

| id | title | deleted |
|---:|---|---|
| 1 | Ghi chú A | true |
| 2 | Ghi chú B | false |

Nhưng:

```java
List<Note> notes = em.createQuery(
        "from Note n order by n.id",
        Note.class
    )
    .getResultList();
```

trong EntityManager mới có thể chỉ trả Note#2 vì SQL restriction loại Note#1.

### 25.4. Thử bỏ @SQLRestriction

Nếu xóa `@SQLRestriction` khỏi mapping, giữ nguyên custom SQL và chạy lại:

- `remove` vẫn cập nhật `deleted=true`.
- `from Note` có thể trả cả row 1 và 2.
- Điều này chứng minh **`@SQLDelete` chỉ điều chỉnh delete statement, không tự ẩn bản ghi**.

### 25.5. Thử chỉ giữ @SQLRestriction

Nếu có restriction nhưng **không có `@SQLDelete`**, `em.remove(note)` thường phát physical DELETE. Query chỉ thấy active rows nhưng database đã mất row 1.

Điều này chứng minh **read restriction cũng không tự tạo soft-delete write behavior**.

### 25.6. Thử @SoftDelete thay hai annotations

Trên Hibernate 6.4+, có thể dùng mapping mới:

```java
@Entity
@Table(name = "notes")
@SoftDelete(
    strategy = SoftDeleteType.DELETED,
    columnName = "deleted"
)
public class Note {
    @Id
    private Long id;
    private String title;
}
```

Không khai báo cùng `@SQLDelete`/`@SQLRestriction` trên entity này chỉ để lặp lại hành vi. Test `remove` và HQL/`find` active-only; quan sát SQL và semantics thực tế của version được dùng.

## 26. Integration test trong Spring Boot

Một integration test nên chạy trên database phù hợp với production dialect và transaction thực sự được commit. Mục tiêu không chỉ assert “repository không tìm thấy entity” mà còn xác minh row **vẫn còn vật lý**.

### 26.1. Dùng TransactionTemplate để tách transaction

```java
@SpringBootTest
class NoteSoftDeleteIT {

    @Autowired
    private TransactionTemplate tx;

    @PersistenceContext
    private EntityManager em;

    @Test
    void removeMarksRowDeletedButKeepsItInDatabase() {

        tx.executeWithoutResult(status -> {
            Note note = em.find(Note.class, 1L);
            assertThat(note).isNotNull();

            em.remove(note);
        });

        tx.executeWithoutResult(status -> {
            Note visible = em.find(Note.class, 1L);
            assertThat(visible).isNull();
        });

        Object raw = tx.execute(status ->
            em.createNativeQuery(
                "SELECT deleted FROM notes WHERE id = 1"
            ).getSingleResult()
        );

        // Kiểu JDBC có thể là Boolean, số hoặc representation
        // khác tùy database; chuyển theo dialect phù hợp.
        assertThat(raw).isNotNull();
    }
}
```

Ví dụ này giả định fixture Note#1 tồn tại từ trước, mapping đã cấu hình, và test sử dụng AssertJ/JUnit imports. **Không** đặt một outer `@Transactional` trên test method nếu mục tiêu là kiểm tra state **sau commit** mà test framework sẽ rollback cuối test.

Để chứng minh physical row còn, nên thêm một native count query:

```java
Number count = (Number) em.createNativeQuery(
        "SELECT COUNT(*) FROM notes WHERE id = 1"
    ).getSingleResult();

assertThat(count.longValue()).isEqualTo(1L);
```

Đọc `deleted` cần assert giá trị đúng theo representation của dialect (BOOLEAN vs 0/1/CHAR). Không hard-code cast `(Boolean) raw` nếu database test chưa xác nhận.

### 26.2. Những ca test không thể thiếu

| Kịch bản | Cần xác minh |
|---|---|
| `persist` entity mới | Indicator mặc định active |
| `remove` entity | Row còn vật lý, indicator đổi |
| HQL list query | Row deleted không xuất hiện khi filter policy yêu cầu |
| `em.find` với deleted ID | Không trả entity như active theo mapping phù hợp |
| Native SELECT | Không tự áp restriction nếu query không do ORM tạo |
| HQL bulk delete | Không phá soft-delete policy ngoài ý muốn |
| Spring Data deleteAllInBatch | Có bypass lifecycle không |
| To-one association tới deleted target | Semantics rõ ràng, không làm detail page lỗi bất ngờ |
| To-many collection | Chỉ member hợp lệ xuất hiện |
| Unique key reuse | Constraint phản ánh active-only uniqueness nếu business yêu cầu |
| Restore | Có quyền, guard version, xử lý unique conflict |
| Concurrent delete | Row count/version/idempotency policy |
| Transaction rollback | DB và audit không commit state xóa thất bại |
| L2/query cache | Session mới không đọc stale state |
| External JDBC delete/update | Có monitoring/invalidation/protection |
| Multi-tenant | Tenant A không tác động row Tenant B |

### 26.3. Kiểm tra SQL thật, không chỉ return value

`repository.findById(id).isEmpty()` không đủ để chứng minh soft delete: physical DELETE cũng trả kết quả đó. Hãy đọc raw SQL table sau commit, đo câu DML được phát và assert đúng policy.

Có thể bật:

```properties
spring.jpa.show-sql=true
spring.jpa.properties.hibernate.format_sql=true
logging.level.org.hibernate.SQL=DEBUG
```

Không bật bind-parameter logging nhạy cảm trong production một cách vô điều kiện.

## 27. Hiệu năng của soft delete

### 27.1. Tích lũy tombstones

Physical DELETE làm giảm số rows trong bảng; soft delete giữ các rows đã xóa. Sau nhiều năm, số tombstones có thể lớn hơn active rows, ảnh hưởng:

- Kích thước bảng và indexes.
- Query execution plans và statistics.
- Backup/restore/replication costs.
- Scan/sort trên nhiều deleted rows.
- Vacuum/maintenance và partition strategy.
- Unique index và storage retention.

`@SQLDelete` không xóa tác động này. Nó chỉ thay dạng mutation.

### 27.2. Index cho active-only queries

Nếu ứng dụng thường truy vấn:

```sql
SELECT *
FROM customer_accounts
WHERE deleted = false
  AND email = ?;
```

có thể cân nhắc index theo pattern, ví dụ PostgreSQL partial index active-only, hoặc composite index tương thích với dialect. Index lựa chọn phụ thuộc tỷ lệ active/deleted, selectivity và số lượng writes.

### 27.3. UPDATE thường không miễn phí

Soft delete là UPDATE; nó vẫn ghi WAL/redo, update indexes (nếu cột indexed), có row locking và có thể tạo bloat theo MVCC. Không cho rằng soft delete rẻ hơn physical DELETE trong mọi trường hợp.

### 27.4. Query filter cũng có chi phí

Thêm `deleted = false` có thể giúp optimizer loại rows sớm nếu có index thích hợp, nhưng có thể làm những composite predicates, joins và query plan phức tạp hơn. Hãy đo p95 latency, plan, row counts thay vì chỉ nhìn số dòng SQL.

### 27.5. Retention có thể cần partition/archival

Nếu hệ thống buộc giữ dữ liệu xóa mềm trong 90 ngày rồi purge, một job theo batches có thể thích hợp. Nếu audit/retention vài năm, cân nhắc archive table/storage và tách active data khỏi historical data, nhưng điều đó là kiến trúc dữ liệu riêng, không còn chỉ là `@SQLDelete`.

## 28. Bảng lỗi thường gặp và hướng giải quyết

| Hiện tượng | Nguyên nhân điển hình | Cách xử lý |
|---|---|---|
| Đã thêm `@SQLDelete` nhưng list API vẫn thấy deleted | Chưa có read restriction/query policy | Thêm `@SQLRestriction`/`@SoftDelete` hoặc WHERE có chủ đích |
| `remove` vẫn xóa vật lý | Annotation đặt sai, query dùng bulk/native path hoặc mapping khác | Kiểm tra ORM lifecycle và SQL thật |
| `@SQLRestriction` nhưng row đã biến mất khỏi DB | Chỉ lọc đọc, vẫn dùng physical DELETE | Tạo đúng write semantics |
| Admin không xem được row đã xóa | Restriction tĩnh không disable được | Read path riêng có authorization |
| Restore `em.find` trả null | ORM filter ẩn tombstone | Admin-native/status path được thiết kế |
| Xóa lần hai tạo stale exception | Guard `deleted=false` + RowCount | Xác định idempotent vs conflict semantics |
| `@Version` không còn bảo vệ custom delete | SQL thiếu version predicate/verification | Thêm đúng placeholders/row-count handling |
| INSERT fail vì deleted NULL | Column NOT NULL không default/mapping | Backfill/default nhất quán |
| Không tạo lại được email | Unique index vẫn áp trên deleted rows | Định nghĩa active-only uniqueness nếu nghiệp vụ muốn |
| Khôi phục fail unique | Có active row cùng email | Business conflict workflow |
| Child bị xóa vật lý khi parent soft-delete | Cascade child khác parent mapping | Review REMOVE/orphanRemoval/child policy |
| Order detail lỗi khi Product đã xóa | Filter ẩn target FK vẫn còn | Snapshot hoặc historical read model |
| `@Filter` lúc có lúc không | Session filter chưa enable đúng scope | Centralize policy, test direct loads |
| Native report có tombstones | Restriction ORM không áp cho native SQL | Viết WHERE rõ hoặc DB view/policy |
| Spring Data `deleteAllInBatch` hard-delete | Bulk DML bypass custom remove path | Cấm/đổi API, integration test |
| Search index vẫn thấy account deleted | Cache/search bên ngoài Hibernate stale | CDC/event-driven invalidation |
| Restore không thấy state mới | L1/L2/query cache còn stale | Clear/evict/transaction synchronization |
| Envers ghi DEL trong khi DB UPDATE flag | ORM lifecycle vẫn là removal | Kiểm tra audit semantics; dùng domain UPDATE nếu muốn MOD |
| Old node tiếp tục physical DELETE | Rolling deploy chưa rút hết writer cũ | Cutover/migration plan có bảo vệ |
| Hibernate boot lỗi annotation không tồn tại | Version ORM không hỗ trợ `@SQLRestriction`/`@SoftDelete` | Kiểm tra version và import |
| Custom SQL lỗi bind parameters | Số/thứ tự `?` không khớp mapping | Đọc JavaDoc và test SQL đối với ID/version/secondary table |

## 29. Cách chọn giải pháp theo nhu cầu

### Trường hợp A — Hibernate mới, xóa mềm Boolean đơn giản

**Ưu tiên `@SoftDelete`** trên entity khi đang chạy Hibernate 6.4+ và mapping phù hợp. Đây là soft-delete abstraction tích hợp, tránh phải ghép tự tay SQL + filter.

### Trường hợp B — Hệ thống legacy Hibernate 5/6.2, muốn giữ API `delete()`

Dùng `@SQLDelete` và read restriction tương thích với phiên bản, cộng tests cho cascade, restore, bulk deletes và caches. Khi nâng Hibernate, đánh giá migration sang `@SoftDelete`.

### Trường hợp C — Cần trạng thái lifecycle phong phú, deletedBy, deletedAt, restore thường xuyên

Cân nhắc status field được thay đổi bằng **domain service UPDATE** thay vì mượn `remove` làm thao tác nghiệp vụ. Tách physical purge thành operation riêng. Dùng repository predicates/view/filter rõ để không leak deleted rows.

### Trường hợp D — Nhiều writers ngoài Hibernate

Chỉ annotation ORM có thể không đủ. Cân nhắc DB-level policies/triggers/CDC, một write API thống nhất hoặc refactor để mọi writer tuân thủ lifecycle.

### Trường hợp E — Cần lịch sử đầy đủ, bất biến, compliance

Soft delete không thay audit trail. Phối hợp Envers hoặc giải pháp lịch sử riêng và retention/permission/immutability controls. Không lưu secrets trong tombstone/audit ngoài yêu cầu.

### Trường hợp F — Có các parent-child associations phức tạp

Thiết kế từng aggregate: xóa parent làm child ẩn theo hay child phải tồn tại độc lập? Historical references dùng snapshot hay entity? Không dựa duy nhất vào một annotation cho toàn bộ graph.

## 30. Bài tập thực hành

**Bài 1 — Phân biệt khái niệm.** Giải thích vì sao `@SQLDelete(sql="DELETE ...")` không phải soft delete và `@SQLRestriction` không tự làm DELETE thành UPDATE.

**Bài 2 — Legacy mapping.** Tạo entity Note với `@SQLDelete UPDATE deleted=true`, chạy `remove`, rồi SELECT raw table để chứng minh row còn.

**Bài 3 — Thiếu restriction.** Bỏ `@SQLRestriction` và chạy HQL list. Quan sát deleted row xuất hiện lại.

**Bài 4 — Thiếu SQLDelete.** Giữ restriction nhưng bỏ custom SQL. Chạy `remove` và quan sát physical deletion.

**Bài 5 — SoftDelete tích hợp.** Dùng Hibernate 6.4+ và `@SoftDelete(strategy=DELETED)`; so SQL/mapping với legacy approach.

**Bài 6 — ACTIVE strategy.** Dùng cột `active`, đặt `SoftDeleteType.ACTIVE`, kiểm tra ý nghĩa true/false.

**Bài 7 — @Version.** Thêm optimistic version, custom SQL có `WHERE id=? AND version=?` và xác minh RowCount trên concurrent delete.

**Bài 8 — @Filter.** Bật/tắt Session filter, test list query và load-by-id. Giải thích vì sao Session scope cần được quản lý chặt.

**Bài 9 — Restore.** Dùng admin service SQL restore với authorization và concurrency guard; thử restore twice.

**Bài 10 — Unique email.** Tạo partial unique index active-only (trên PostgreSQL), kiểm tra tạo account mới sau soft delete và conflict khi restore account cũ.

**Bài 11 — Cascade.** Parent Order có child OrderLine. So hành vi khi child cũng có soft-delete mapping và khi child không có.

**Bài 12 — Historical FK.** OrderLine tham chiếu Product đã soft-deleted, thiết kế DTO hiển thị tên sản phẩm lịch sử mà không cần load Product ẩn.

**Bài 13 — Bulk JPQL.** So `em.remove(entity)` với `delete from Entity` và Spring Data `deleteAllInBatch`. Đọc raw SQL và row counts.

**Bài 14 — Native SQL.** Dùng JdbcTemplate physical DELETE trong môi trường test để chứng minh Hibernate annotations không áp dụng.

**Bài 15 — Cache.** Warm L2/query cache rồi soft-delete qua ORM và qua raw JDBC. Kiểm tra Session mới, query results và invalidation.

**Bài 16 — Auditing.** Kết hợp Envers; xem cách REMOVE event + custom UPDATE được phản ánh trong history so với service-managed UPDATE.

**Bài 17 — Migration.** Thêm deleted column vào bảng lớn, backfill, chuẩn bị index/constraints, rollout nodes cũ mới, lập plan rollback.

**Bài 18 — Retention.** Thiết kế một purge job chỉ xóa row deleted đủ tuổi, không vi phạm legal hold và không bỏ qua FK.

## 31. Câu hỏi tự kiểm tra

**1. Soft delete là gì?**

Chính sách giữ row trong database nhưng đánh dấu không còn hoạt động để hệ thống xử lý như đã xóa theo nghiệp vụ.

**2. `@SQLDelete` làm gì?**

Thay câu SQL khi Hibernate xóa entity/collection row qua đường ORM lifecycle bằng câu SQL tự khai báo.

**3. Chỉ thêm `@SQLDelete` là đủ soft delete không?**

Không. Nó không tự lọc kết quả đọc, không tạo restore workflow, không giải quyết unique constraints, cascade hoặc bulk/native writes.

**4. `@SQLRestriction` làm gì?**

Áp SQL predicate tĩnh cho các SQL được Hibernate sinh ở entity/collection mapping phù hợp. Nó không thể disable hoặc parameterize tại runtime.

**5. `@Where` có còn là lựa chọn chính trong Hibernate 6.6 không?**

Không. `@Where` deprecated từ Hibernate 6.3; dùng `@SQLRestriction` hoặc `@SoftDelete` khi phù hợp.

**6. Hibernate 6.4 giới thiệu annotation nào cho soft delete?**

`@SoftDelete`.

**7. DELETED và ACTIVE khác nhau ở đâu?**

DELETED: true nghĩa đã xóa. ACTIVE: true nghĩa đang hoạt động.

**8. `EntityManager.remove` với `@SQLDelete` custom UPDATE có vẫn làm entity removed trong L1 không?**

Có theo lifecycle ORM; custom SQL không biến entity thành managed active object sau remove.

**9. `@SQLDelete` có tự áp cho `delete from Entity` HQL bulk không?**

Không nên giả định; bulk mutation không gọi `remove` trên từng entity. Phải kiểm tra generated SQL và thiết kế write policy.

**10. Admin muốn restore row bị `@SQLRestriction` ẩn phải làm gì?**

Dùng admin write/read path được phân quyền và không phụ thuộc normal entity load đã bị restriction loại, ví dụ native SQL có guard.

**11. Vì sao email unique có thể bị chặn sau soft delete?**

Row cũ vẫn tồn tại nên UNIQUE(email) tiếp tục áp dụng. Cần chọn uniqueness policy và index tương ứng.

**12. Xóa mềm parent có tự kích hoạt DB ON DELETE CASCADE không?**

Không, vì DB không nhận physical DELETE trên parent.

**13. `@Version` có cần quan tâm trong custom SQL delete không?**

Có. SQL placeholders và version predicate phải khớp mapping; cần kiểm tra affected row count/optimistic conflict.

**14. `em.clear()` có sửa mọi cache stale không?**

Không. Nó bỏ L1; L2/query cache và các cache ngoài Hibernate vẫn cần xử lý riêng.

**15. Soft delete có tự ghi lịch sử, actor, lý do xóa không?**

Không. Những yêu cầu này cần metadata, Envers hoặc business audit riêng.

## 32. Ghi nhớ

- **Soft delete** là chính sách giữ row và đánh dấu đã xóa; **`@SQLDelete` chỉ tùy chỉnh DELETE SQL** của Hibernate.
- `@SQLDelete` có thể chạy `UPDATE ... SET deleted=true` nhưng **không tự làm kết quả SELECT ẩn tombstones**.
- Với legacy mapping, `@SQLDelete` thường đi kèm `@SQLRestriction` hoặc giải pháp filter thích hợp. `@Where` là annotation cũ đã deprecated.
- Hibernate 6.4+ có `@SoftDelete` hỗ trợ soft delete ở cấp ORM, thường phù hợp hơn cách ghép thủ công cho use case Boolean indicator.
- `@SQLRestriction` là SQL predicate tĩnh, không thể tắt; `@Filter` động theo Session nhưng dễ có lỗ hổng nếu quên enable hoặc không test mọi load path.
- `@SQLDelete` phải có đúng `?` placeholders theo Hibernate mapping; với `@Version`, ID thường đứng trước version. Dùng `verify = Expectation.RowCount.class` khi cần phát hiện stale/zero-row operations.
- `EntityManager.remove` khác HQL bulk DELETE, native SQL và JDBC; các đường ngoài ORM entity lifecycle không tự dùng custom delete statement.
- Restore và hard purge là hai use cases riêng, cần transaction, authorization, constraint và cache handling.
- Soft-deleted rows vẫn chịu UNIQUE/FK constraints và chiếm storage/index; thiết kế uniqueness active-only và retention ngay từ đầu.
- Xóa mềm parent không kích hoạt DB `ON DELETE CASCADE`; cascade/orphanRemoval của Hibernate và các relation filters cần được kiểm chứng.
- Envers/audit history, actor/reason, multi-tenant isolation và distributed cache freshness không tự được giải quyết chỉ bằng một annotation.
- **Đọc generated SQL và kiểm tra database row sau commit**; một query không tìm thấy entity chưa chứng minh row được xóa mềm thay vì xóa vật lý.

### Tài liệu tham khảo

- [Hibernate ORM 6.6 User Guide — Soft Delete](https://docs.hibernate.org/orm/6.6/userguide/html_single/#soft-delete)
- [Hibernate ORM 6.6 JavaDoc — `@SQLDelete`](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/annotations/SQLDelete.html)
- [Hibernate ORM 6.6 JavaDoc — `@SQLRestriction`](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/annotations/SQLRestriction.html)
- [Hibernate ORM 6.6 JavaDoc — `@SoftDelete`](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/annotations/SoftDelete.html)
- [Hibernate ORM 6.6 JavaDoc — `@Filter`](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/annotations/Filter.html)
- [Hibernate ORM 6.6 JavaDoc — `@Where` (deprecated)](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/annotations/Where.html)
- [Hibernate ORM 6.4 Migration Guide — Soft Delete](https://docs.hibernate.org/orm/6.4/migration-guide/#soft-delete)
- [Hibernate ORM 6.6 Introduction — Soft-delete and custom SQL](https://docs.hibernate.org/orm/6.6/introduction/html_single/)
- [Spring Data JPA Reference — JPA Query Methods](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html)
- [Jakarta Persistence Specification 3.1](https://jakarta.ee/specifications/persistence/3.1/jakarta-persistence-spec-3.1)
- [PostgreSQL Documentation — CREATE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html)

