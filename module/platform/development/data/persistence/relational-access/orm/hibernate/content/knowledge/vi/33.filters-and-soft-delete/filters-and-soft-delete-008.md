# Ràng buộc duy nhất khi bản ghi đã xóa mềm vẫn còn trong bảng

## 1. Bài toán: đã xóa người dùng nhưng không thể đăng ký lại email

Giả sử bảng tài khoản có ràng buộc `UNIQUE(email)`:

~~~sql
CREATE TABLE users (
    id BIGINT PRIMARY KEY,
    email VARCHAR(320) NOT NULL,
    deleted_at TIMESTAMP NULL,
    CONSTRAINT uq_users_email UNIQUE (email)
);
~~~

Một người dùng đăng ký `linh@example.com`:

| id | email | deleted_at |
|---:|---|---|
| 101 | linh@example.com | NULL |

Ứng dụng thực hiện **xóa mềm (soft delete)** bằng cách ghi thời điểm xóa thay vì xóa row:

~~~sql
UPDATE users
SET deleted_at = CURRENT_TIMESTAMP
WHERE id = 101;
~~~

Row 101 vẫn ở database:

| id | email | deleted_at |
|---:|---|---|
| 101 | linh@example.com | 2026-03-01 10:00:00 |

Sau đó người dùng đăng ký một tài khoản mới cùng email:

~~~sql
INSERT INTO users (id, email, deleted_at)
VALUES (202, 'linh@example.com', NULL);
~~~

Lệnh này **vẫn vi phạm `UNIQUE(email)`**: ràng buộc của database kiểm tra tất cả các row thuộc phạm vi index, bất kể Hibernate query thông thường có lọc `deleted_at IS NULL` hay không.

Đây là mâu thuẫn giữa hai yêu cầu:

- **Xóa mềm:** giữ row để phục vụ audit, phục hồi hoặc lịch sử.
- **Tính duy nhất theo nghiệp vụ:** chỉ cho phép một bản ghi **đang hoạt động** sử dụng email, mã sản phẩm, slug, số điện thoại hoặc số hiệu.

Nhiều người xử lý bằng cách thêm điều kiện vào query:

~~~java
boolean exists = userRepository
    .existsByEmailAndDeletedAtIsNull(email);
~~~

Cách này giúp kiểm tra logic ứng dụng, nhưng **không sửa ràng buộc UNIQUE đang tồn tại trong database**, và cũng không ngăn được hai requests đồng thời tạo trùng.

Bài học thuộc chương **Bộ lọc và xóa mềm**, module *Data Persistence Relational Access ORM Hibernate*. Trọng tâm không chỉ là cách viết SQL index, mà là **định nghĩa chính xác “duy nhất” khi bản ghi xóa mềm vẫn tồn tại, cấu hình database bảo đảm quy tắc dưới concurrency, và tích hợp an toàn với Hibernate/JPA**.

### 1.1. Kết quả cần đạt

Sau bài này, bạn có thể:

1. Xác định khi nào cần giữ business key vĩnh viễn và khi nào cho phép tái sử dụng.
2. Giải thích vì sao `UNIQUE(email)`, `UNIQUE(email, deleted)` và `UNIQUE(email, deleted_at)` có thể cho kết quả khác nhau ngoài dự tính.
3. Dùng **partial/filtered unique index** cho database hỗ trợ.
4. Dùng **generated column hoặc functional unique key với NULL semantics** khi DB không có partial index cùng cú pháp.
5. Thiết kế uniqueness theo `tenant_id` và trạng thái active/deleted.
6. Tách Hibernate `@SoftDelete`, `@SQLDelete`, query filters khỏi **ràng buộc database**.
7. Xử lý race condition khi tạo mới, xóa mềm, phục hồi và đổi business key.
8. Dùng migration, integration test và error handling để bảo đảm constraint có hiệu lực trong production.

## 2. Bước đầu tiên: quyết định chính sách tái sử dụng khóa

Không có một index đúng cho tất cả hệ thống. Trước khi sửa schema, phải quyết định **row đã xóa mềm còn sở hữu business key hay không**.

### 2.1. Chính sách A — Không cho tái sử dụng khóa

Ví dụ:
- Mã định danh giấy phép đã cấp không bao giờ được cấp lại.
- Số chứng từ hoặc số hóa đơn phải duy nhất xuyên suốt lịch sử.
- Username bị khóa vì lý do bảo mật, không được đăng ký lại.
- Một idempotency key phải được bảo lưu đủ lâu.

Khi đó `UNIQUE(business_key)` có thể chính là ràng buộc mong muốn. Xóa mềm không giải phóng khóa. Việc INSERT khóa cũ bị từ chối là **đúng nghiệp vụ**, không phải lỗi của Hibernate.

Phải làm rõ khi nào tái kích hoạt row cũ, lúc nào tạo định danh mới và có cần cơ chế “tên được bảo lưu” riêng hay không.

### 2.2. Chính sách B — Chỉ một row đang hoạt động sở hữu khóa

Ví dụ:
- Một tenant có tối đa một product slug đang hoạt động.
- Email có thể dùng lại sau khi chủ tài khoản cũ thực sự xóa tài khoản.
- Một coupon code chỉ có một cấu hình active, lịch sử cũ vẫn giữ.

Quy tắc:

> Với mỗi cặp `(tenant_id, normalized_email)`, tồn tại **tối đa một row có `deleted_at IS NULL`**. Có thể tồn tại nhiều row đã xóa mềm trùng email.

Đây là **uniqueness có điều kiện**. Cần thiết kế constraint/index chỉ kiểm tra các row active.

### 2.3. Chính sách C — Không tái sử dụng ngay; có thời gian giữ chỗ

Ví dụ email/slug đã xóa bị giữ trong 30 ngày để phòng chiếm đoạt tài khoản hoặc bảo vệ liên kết cũ.

~~~text
active -----------------------> deleted / reserved
                                  |
                                  | Hết thời gian + điều kiện nghiệp vụ
                                  v
                              released
                                  |
                                  v
                           key có thể tái sử dụng
~~~

Một unique index với predicate kiểu `WHERE deleted_at > now() - interval '30 days'` thường **không phải giải pháp trực tiếp**: nhiều DB yêu cầu predicate index ổn định/immutable; index cũng không tự thay đổi row membership khi thời gian trôi nếu row không đổi.

Thay vào đó, dùng **trạng thái reservation được materialize** (ví dụ một bảng `key_claims`), scheduler/workflow giải phóng khóa qua transaction và unique constraint trên claims còn hiệu lực. Các quy tắc thời gian, bảo mật và retry phải được định nghĩa rõ.

### 2.4. Chính sách D — Một row active theo nhiều chiều

Không phải mọi business key đều global:

~~~text
Global:
  UNIQUE(email) among active users

Per tenant:
  UNIQUE(tenant_id, email) among active users

Per product group:
  UNIQUE(category_id, slug) among active products

Per owner:
  UNIQUE(user_id, role_id) among active memberships
~~~

Chọn sai scope gây lỗi:

- `UNIQUE(email)` chặn hai tenants dùng cùng email dù nghiệp vụ cho phép.
- `UNIQUE(tenant_id, email)` cho phép cùng email ở nhiều tenants dù identity provider yêu cầu global.
- Chỉ lọc trạng thái deleted nhưng quên tenant key có thể cấp trùng domain key.

**Các ví dụ chính sau đây giả định chính sách B:** chỉ row active cần unique. Đây là giả định minh họa, không phải mọi hệ thống đều nên cho phép tái sử dụng email.

## 3. Mô hình dữ liệu xuyên suốt

Giả sử ứng dụng quản lý tài khoản theo tenant:

~~~sql
CREATE TABLE users (
    id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    email VARCHAR(320) NOT NULL,
    normalized_email VARCHAR(320) NOT NULL,
    display_name VARCHAR(200) NOT NULL,
    deleted_at TIMESTAMP NULL,
    version BIGINT NOT NULL DEFAULT 0
);
~~~

Ý nghĩa:
- `id` là **surrogate key** ổn định, không tái sử dụng.
- `tenant_id` xác định miền tính duy nhất.
- `normalized_email` là business key chuẩn hóa dùng cho uniqueness.
- `email` là giá trị hiển thị/nhập liệu, có thể giữ original case.
- `deleted_at IS NULL` nghĩa là đang hoạt động.
- `deleted_at IS NOT NULL` nghĩa là đã xóa mềm.
- `version` dùng cho optimistic locking khi update entity-level.

Giả định:

~~~text
ACTIVE  <=> deleted_at IS NULL
DELETED <=> deleted_at IS NOT NULL
~~~

Nếu hệ thống dùng `deleted BOOLEAN NOT NULL DEFAULT FALSE`, predicate/index tương ứng là `deleted = false`. **Đừng đồng thời duy trì `deleted` và `deleted_at` rồi bỏ qua nguy cơ lệch trạng thái**; nếu bắt buộc cả hai, schema/service phải bảo đảm chúng nhất quán.

### 3.1. Business key phải được chuẩn hóa có chủ đích

Hai input:

~~~text
Linh@Example.com
linh@example.com
~~~

Nếu nghiệp vụ coi chúng là cùng tài khoản nhưng index phân biệt hoa/thường, sẽ có hai active users.

Các lựa chọn:
- Lưu thêm `normalized_email` với chuẩn hóa từ application.
- Dùng index trên biểu thức `lower(email)` ở DB hỗ trợ.
- Dùng collation không phân biệt hoa/thường phù hợp.
- Dùng loại cột case-insensitive như `citext` trên PostgreSQL nếu chấp nhận extension.

Cần quyết định rõ Unicode normalization, trimming, locale, quy tắc email, dấu cách, collation và cách cập nhật normalized key. **Không tự áp dụng quy tắc email quá mạnh** (ví dụ bỏ dấu chấm cho mọi nhà cung cấp) nếu nghiệp vụ chưa yêu cầu.

### 3.2. Khi key có thể NULL

Với nhiều DB, UNIQUE có semantics riêng cho NULL. Nếu business key của active record có thể NULL, một unique index trên key có thể cho phép nhiều active rows với NULL.

Nếu email bắt buộc cho user active, thể hiện ở schema:

~~~sql
normalized_email VARCHAR(320) NOT NULL
~~~

Nếu deleted row cần ẩn danh hóa xóa email, hãy thiết kế nullable key cùng constraint active/non-active phù hợp hoặc tách PII/snapshot. **NULL semantics là một phần của ràng buộc**, không phải chi tiết nhỏ.

## 4. Bốn cách tưởng đúng nhưng thường sai

### 4.1. Sai lầm 1 — UNIQUE(email) khi muốn reuse sau xóa

~~~sql
ALTER TABLE users
ADD CONSTRAINT uq_users_tenant_email
UNIQUE (tenant_id, normalized_email);
~~~

Constraint này kiểm tra **mọi row**.

| tenant_id | normalized_email | deleted_at | Kết quả |
|---:|---|---|---|
| 7 | linh@example.com | 2026-03-01 | Row cũ đang chiếm key |
| 7 | linh@example.com | NULL | **Bị từ chối** |
| 8 | linh@example.com | NULL | Được phép, tenant khác |

Nếu chính sách “key không được reuse”, constraint đúng. Nếu chỉ unique cho active, đây là quá chặt.

### 4.2. Sai lầm 2 — UNIQUE(email, deleted BOOLEAN)

~~~sql
CREATE UNIQUE INDEX ux_users_email_deleted
ON users(tenant_id, normalized_email, deleted);
~~~

Với `deleted=false` khi active, nó chặn hai active rows cùng key. Nhưng cũng **chặn hai deleted rows cùng key** vì cả hai `deleted=true`.

~~~text
Row 1: (tenant=7, email=a@x.com, deleted=false) -> OK
Row 2: (tenant=7, email=a@x.com, deleted=true)  -> OK
Row 3: (tenant=7, email=a@x.com, deleted=false) -> DUPLICATE
Row 4: (tenant=7, email=a@x.com, deleted=true)  -> DUPLICATE
~~~

Tình huống:

1. User A đăng ký `a@x.com`.
2. User A xóa mềm → `deleted=true`.
3. User B đăng ký email đó → `deleted=false`.
4. User B xóa mềm → phải đổi thành `deleted=true`.
5. Bước 4 **vi phạm unique** do đã có A deleted cùng key.

Vì vậy `UNIQUE(email, deleted)` không biểu đạt đúng “tối đa một active, không giới hạn các historical deleted rows”.

### 4.3. Sai lầm 3 — UNIQUE(email, deleted_at TIMESTAMP NULL)

~~~sql
CREATE UNIQUE INDEX ux_users_email_deleted_at
ON users(tenant_id, normalized_email, deleted_at);
~~~

Nếu active rows dùng `deleted_at=NULL`, thì ở PostgreSQL/MySQL với **NULL DISTINCT mặc định**, hai tổ hợp:

~~~text
(7, a@x.com, NULL)
(7, a@x.com, NULL)
~~~

có thể **cùng tồn tại**. Unique comparison theo mặc định coi các NULL là không bằng nhau. Nghĩa là index có thể cho phép nhiều active rows trùng key.

PostgreSQL 15+ có `NULLS NOT DISTINCT` để điều chỉnh cách unique index xử lý NULL, nhưng cần cân nhắc historical rows có deleted timestamps trùng nhau; một **partial unique index** vẫn diễn đạt yêu cầu “chỉ unique khi active” rõ ràng hơn.

### 4.4. Sai lầm 4 — Chỉ kiểm tra exists() trong service

~~~java
if (!repository.existsByTenantIdAndNormalizedEmailAndDeletedAtIsNull(
        tenantId, normalizedEmail)) {
    repository.save(newUser);
}
~~~

Hai transactions có thể cùng thấy “chưa tồn tại”:

~~~text
Transaction T1                     Transaction T2
--------------                     --------------
SELECT exists active? -> false
                                   SELECT exists active? -> false
INSERT active user
                                   INSERT active user
COMMIT                             COMMIT
~~~

Nếu không có unique constraint/index đúng ở DB, **cả hai có thể thành công**. Transaction isolation đặc biệt đôi khi khiến một transaction bị hủy, nhưng không nên chỉ dựa vào precheck.

`exists` hữu ích cho thông báo lỗi dễ hiểu; **database unique index là điểm đảm bảo cuối cùng dưới concurrency**.
+
## 5. Giải pháp chuẩn khi DB hỗ trợ: partial/filtered unique index

Ý tưởng là duy nhất **chỉ trên tập rows active**:

~~~text
users table
  id  tenant email     deleted_at
  1   7      a@x.com   2026-01-01  ----\
  2   7      a@x.com   2026-02-01  -----+-- không nằm trong active unique index
  3   7      a@x.com   NULL        ----/
                           |
                           +------> active unique index chứa (7, a@x.com)
~~~

Các deleted rows được phép trùng business key; thêm một active row cùng key sẽ bị DB từ chối.

### 5.1. PostgreSQL partial unique index

~~~sql
CREATE UNIQUE INDEX ux_users_active_tenant_email
ON users (tenant_id, normalized_email)
WHERE deleted_at IS NULL;
~~~

Index biểu đạt: **chỉ users có `deleted_at IS NULL` tham gia uniqueness của `(tenant_id, normalized_email)`**.

| tenant | normalized_email | deleted_at | Kết quả |
|---:|---|---|---|
| 7 | a@x.com | NULL | Active đầu tiên hợp lệ |
| 7 | a@x.com | NULL | Active thứ hai bị từ chối |
| 7 | a@x.com | 2026-01-01 | Deleted hợp lệ |
| 7 | a@x.com | 2026-02-01 | Deleted thứ hai hợp lệ |
| 8 | a@x.com | NULL | Tenant khác hợp lệ |

Khi một row được xóa mềm bằng `UPDATE ... SET deleted_at = now()`, nó không còn thuộc predicate index. Một active row mới cùng key có thể INSERT khi transaction/locking cho phép.

### 5.2. PostgreSQL với cột boolean

Nếu schema dùng:

~~~sql
deleted BOOLEAN NOT NULL DEFAULT FALSE
~~~

thì:

~~~sql
CREATE UNIQUE INDEX ux_users_active_tenant_email
ON users (tenant_id, normalized_email)
WHERE deleted = false;
~~~

**Phải thống nhất định nghĩa active** giữa Hibernate soft-delete mapping/filter, repository query, unique-index predicate, restore logic và external SQL writers. Nếu ORM nhìn `deleted=false` nhưng index dựa `deleted_at IS NULL`, hai trường lệch có thể tạo lỗ hổng integrity.

### 5.3. Case-insensitive uniqueness qua expression index

PostgreSQL hỗ trợ:

~~~sql
CREATE UNIQUE INDEX ux_users_active_tenant_email_ci
ON users (tenant_id, lower(email))
WHERE deleted_at IS NULL;
~~~

Hai active rows trong cùng tenant với `Linh@Example.com` và `linh@example.com` xung đột theo `lower(email)` của DB.

Có thể thay bằng `normalized_email` được lưu sẵn. Cần quyết định collation, Unicode normalization, trailing spaces và các quy tắc email, tránh làm mất phân biệt địa chỉ hợp lệ do chuẩn hóa tùy tiện.

### 5.4. SQLite partial unique index

SQLite cũng hỗ trợ:

~~~sql
CREATE UNIQUE INDEX ux_users_active_tenant_email
ON users (tenant_id, normalized_email)
WHERE deleted_at IS NULL;
~~~

Nhưng data types, boolean representation, collation và JDBC driver behavior có khác biệt so với database production. SQLite in-memory test không chứng minh đầy đủ SQL Server/PostgreSQL/MySQL behavior.

### 5.5. SQL Server filtered unique index

SQL Server dùng **filtered unique index**:

~~~sql
CREATE UNIQUE INDEX UX_Users_ActiveTenantEmail
ON dbo.Users (tenant_id, normalized_email)
WHERE deleted_at IS NULL;
~~~

SQL Server có cú pháp, collation và index-management rules riêng. Nếu dùng `is_deleted BIT NOT NULL`, có thể thiết kế predicate tương ứng trên database/version mục tiêu.

### 5.6. @UniqueConstraint không mô tả được WHERE predicate

JPA annotation:

~~~java
@Table(
    name = "users",
    uniqueConstraints = @UniqueConstraint(
        name = "uq_users_tenant_email",
        columnNames = {"tenant_id", "normalized_email"}
    )
)
~~~

nếu tạo constraint thì sẽ kiểm tra **cả deleted rows**. JPA `@UniqueConstraint` không có tham số chuẩn cho `WHERE deleted_at IS NULL`. Hibernate `@SoftDelete`, `@Filter`, `@SQLRestriction` cũng **không** tự biến annotation này thành partial index.

Dùng Flyway/Liquibase hoặc SQL migration theo dialect làm nguồn sự thật cho conditional unique index.

### 5.7. PostgreSQL ON CONFLICT và partial index

PostgreSQL có thể infer một partial unique index nếu conflict target và predicate phù hợp:

~~~sql
INSERT INTO users (
    id, tenant_id, email, normalized_email,
    display_name, deleted_at, version
)
VALUES (
    :id, :tenant_id, :email, :normalized_email,
    :display_name, NULL, 0
)
ON CONFLICT (tenant_id, normalized_email)
    WHERE deleted_at IS NULL
DO NOTHING;
~~~

Đây là SQL đặc thù PostgreSQL, không portable JPQL. Một partial unique index không giống named UNIQUE constraint để dùng tùy ý với `ON CONFLICT ON CONSTRAINT`. Khi dùng `DO NOTHING`, phải kiểm tra lệnh INSERT có thêm row thật không, không âm thầm trả success.

## 6. MySQL/MariaDB: tận dụng NULL semantics có chủ đích

MySQL không hỗ trợ partial unique index theo cú pháp PostgreSQL `CREATE UNIQUE INDEX ... WHERE ...`. Một chiến lược là **biến key của deleted rows thành NULL trong generated expression/column** rồi tạo UNIQUE index.

### 6.1. Nguyên tắc

~~~text
active row:  (tenant_id=7, active_email='a@x.com')
deleted row: (tenant_id=7, active_email=NULL)
~~~

Với MySQL UNIQUE index, nhiều rows chứa NULL trong unique key được phép cùng tồn tại.

- Active rows cùng tenant/email có `active_email` không NULL, nên xung đột.
- Deleted rows có `active_email=NULL`, có thể trùng business key ở `normalized_email`.
- Một key được tái sử dụng nhiều lần qua nhiều vòng đời xóa mềm.

### 6.2. Generated column biểu diễn active business key

Ví dụ MySQL 8.x:

~~~sql
ALTER TABLE users
  ADD COLUMN active_email VARCHAR(320)
    GENERATED ALWAYS AS (
      CASE
        WHEN deleted_at IS NULL THEN normalized_email
        ELSE NULL
      END
    ) STORED,
  ADD UNIQUE INDEX ux_users_active_tenant_email (
      tenant_id, active_email
  );
~~~

Cột `active_email` được database tính từ `deleted_at`/`normalized_email`. Application không tự set cột này.

| tenant_id | normalized_email | deleted_at | active_email |
|---:|---|---|---|
| 7 | a@x.com | NULL | a@x.com |
| 7 | a@x.com | 2026-01-01 | NULL |
| 7 | a@x.com | 2026-02-01 | NULL |

Unique `(tenant_id, active_email)` chặn hai active rows cùng tenant/key nhưng cho nhiều deleted rows có NULL.

### 6.3. Generated active marker

Một biến thể:

~~~sql
ALTER TABLE users
  ADD COLUMN active_marker TINYINT
    GENERATED ALWAYS AS (
      CASE WHEN deleted_at IS NULL THEN 1 ELSE NULL END
    ) STORED,
  ADD UNIQUE INDEX ux_users_active_tenant_email_marker (
      tenant_id, normalized_email, active_marker
  );
~~~

Active marker = 1; deleted marker = NULL. Unique composite key đảm bảo tối đa một active row cho mỗi tenant/email.

Cần bảo đảm `tenant_id` và `normalized_email` NOT NULL theo nghiệp vụ. Nếu một thành phần khác cũng NULL ở active row, ràng buộc có thể bị bypass theo null semantics.

### 6.4. Functional index

Một số MySQL versions hỗ trợ functional key parts, nên có thể tạo unique index trên `CASE WHEN deleted_at IS NULL THEN normalized_email ELSE NULL END` mà không khai báo cột visible. Cú pháp, giới hạn key length, generated-column restrictions và compatibility khác nhau giữa MySQL/MariaDB versions.

Generated column + UNIQUE thường dễ nhìn trong migration/schema, nhưng cần tính chi phí lưu trữ, index maintenance và ORM mapping của cột generated.

### 6.5. Các tình huống cần kiểm tra

- Active key bị NULL: unique chưa chắc chặn duplicates → dùng NOT NULL/CHECK phù hợp.
- Case-sensitive collation: `A@x.com` khác `a@x.com` → chuẩn hóa/collation phải rõ.
- Soft delete: `deleted_at` NULL → timestamp, active key trở thành NULL và nhường uniqueness.
- Restore: timestamp → NULL, active key trở lại email; có thể bị unique violation nếu đã có người khác.
- Migration gặp active duplicates: tạo index không thành công.
- MySQL vs MariaDB DDL/online index support khác nhau theo version.

**Không nhầm `UNIQUE(tenant_id, email, deleted_at)` với generated active key**. Ở MySQL, nhiều NULL trong deleted_at làm hai active rows trùng key có thể cùng tồn tại; generated key đảo logic để active mới có giá trị non-NULL.

## 7. Oracle: function-based unique index

Một hướng cho Oracle là index các biểu thức chỉ có giá trị ở active rows:

~~~sql
CREATE UNIQUE INDEX ux_users_active_tenant_email
ON users (
    CASE WHEN deleted_at IS NULL THEN tenant_id END,
    CASE WHEN deleted_at IS NULL THEN normalized_email END
);
~~~

Active row cho key `(tenant_id, normalized_email)`. Deleted row trả NULL cho cả hai biểu thức; với cơ chế B-tree/unique của Oracle, thiết kế này cho phép nhiều deleted rows cùng key nhưng chặn active duplicates.

Cần lưu ý:
- Các biểu thức phải cùng thể hiện một predicate active.
- `tenant_id`/`normalized_email` của active rows nên NOT NULL.
- Oracle coi empty string như NULL trong nhiều trường hợp VARCHAR.
- Cần kiểm tra optimizer, collation và index creation trên version đích.
- Không copy PostgreSQL `WHERE deleted_at IS NULL` sang Oracle.
- Có thể dùng virtual column + unique index theo conventions của project.

## 8. Tổng hợp chiến lược theo database

| Database | Cơ chế active-only unique | Ý tưởng |
|---|---|---|
| PostgreSQL | Partial unique index | `UNIQUE (tenant_id, email) WHERE deleted_at IS NULL` |
| SQLite | Partial unique index | `WHERE deleted_at IS NULL` |
| SQL Server | Filtered unique index | `WHERE deleted_at IS NULL` |
| MySQL 8.x | Generated/functional key + UNIQUE với NULL | Active key = email nếu active, NULL nếu deleted |
| MariaDB | Generated column/compatible unique index tùy version | Active marker/key theo conditional expression |
| Oracle | Function-based unique index/virtual column | `CASE WHEN deleted_at IS NULL THEN key END` |
| DB khác | Xem DDL và NULL semantics của DB đích | Có thể dùng bảng key claim riêng |

Không có một annotation JPA portable diễn đạt toàn bộ các SQL constructs trên; schema migrations theo database production là nơi thực thi ràng buộc.

### 8.1. Scope, nullability và access pattern

Dù dùng partial index hay conditional generated index:
- `tenant_id` phải thuộc key nếu uniqueness theo tenant.
- `normalized_email` cần NOT NULL khi active.
- Query lookup nên có predicate active phù hợp index.
- Query lịch sử có thể cần index riêng vì active-only index cố ý bỏ deleted rows.
- Optimizer có dùng partial/functional index hay không còn phụ thuộc query predicate, statistics và DB implementation.

Ví dụ lookup:

~~~sql
SELECT id
FROM users
WHERE tenant_id = :tenant_id
  AND normalized_email = :email
  AND deleted_at IS NULL;
~~~

**Đừng lấy thành công của test trên DB in-memory khác engine để khẳng định tính đúng đắn của partial unique index production.**
+
## 9. Hibernate @SoftDelete không tự thay đổi unique constraint

Hibernate ORM 6.4+ có annotation `org.hibernate.annotations.SoftDelete` để provider quản lý soft-deletion indicator cho các mapping được hỗ trợ.

Ví dụ **boolean indicator**:

~~~java
package com.example.account;

import jakarta.persistence.*;
import org.hibernate.annotations.SoftDelete;
import org.hibernate.annotations.SoftDeleteType;

@Entity
@Table(name = "users")
@SoftDelete(
    strategy = SoftDeleteType.DELETED,
    columnName = "deleted"
)
public class UserAccount {

    @Id
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private Long tenantId;

    @Column(name = "normalized_email", nullable = false)
    private String normalizedEmail;

    @Column(name = "display_name", nullable = false)
    private String displayName;

    protected UserAccount() {}

    // Constructor, getters và business operations...
}
~~~

Với `SoftDeleteType.DELETED`, indicator thể hiện **row đã bị xóa**. Hibernate có thể thêm predicate loại deleted rows khỏi entity access paths và thay physical removal bằng update indicator theo contract mapping/provider.

Nếu database dùng `deleted BOOLEAN NOT NULL` thay vì `deleted_at`:

~~~sql
-- PostgreSQL
CREATE UNIQUE INDEX ux_users_active_tenant_email
ON users (tenant_id, normalized_email)
WHERE deleted = false;
~~~

**Hai nhiệm vụ khác nhau:**

| Tầng | Chức năng |
|---|---|
| Hibernate `@SoftDelete` | Điều khiển entity soft delete và cách ORM nhìn thấy deleted rows |
| Partial unique index ở database | Cấm hai active rows cùng tenant/email, kể cả dưới concurrency/external SQL |

Thêm `@SoftDelete` **không tự xóa** một `UNIQUE(tenant_id, normalized_email)` toàn cột đã tồn tại, và **không tự tạo partial unique index** portable.

### 9.1. Không ánh xạ indicator hai lần một cách tùy tiện

Khi Hibernate quản lý cột `deleted` bằng `@SoftDelete`, không nên vô điều kiện khai báo thêm một persistent field `deleted` writable vào cùng cột rồi sửa như field bình thường; mapping có thể bị xung đột/không nhất quán.

Nếu ứng dụng cần ngày xóa, có thể có `deleted_at` do service/trigger/audit cơ chế riêng cập nhật. Nhưng khi giữ cả hai cột:

~~~text
deleted=false  <=> deleted_at IS NULL
deleted=true   <=> deleted_at IS NOT NULL
~~~

phải bảo đảm hai trạng thái không lệch nhau. Nếu DB index dựa trên `deleted=false` còn API hiển thị dựa trên `deleted_at`, integrity và dữ liệu người dùng có thể bất nhất.

### 9.2. Filter không thay thế database integrity

Hibernate `find` có thể không nhìn thấy deleted row trong khi SQL trực tiếp vẫn đọc được:

~~~sql
SELECT *
FROM users
WHERE id = 101;
~~~

Soft delete không xóa vật lý row. Partial index là một cơ chế độc lập tại DB, áp dụng cả Hibernate, JDBC, stored procedure và admin SQL (trong phạm vi DB constraint).

### 9.3. Restore là một workflow riêng

`@SoftDelete` là Hibernate-specific. **Không mặc định `persist`/`merge` một entity cũ là cách chính thức restore**. Khi muốn restore, thiết kế admin/service operation có authorization, active-key uniqueness checks, version strategy, stale context/cache handling và audit.

## 10. @SQLDelete, @SQLRestriction, @Filter và soft delete tùy biến

### 10.1. Custom SQLDelete

Ví dụ minh họa **cho entity không có `@Version` trong mapping này**:

~~~java
import org.hibernate.annotations.SQLDelete;
import org.hibernate.annotations.SQLRestriction;

@Entity
@Table(name = "users")
@SQLDelete(
    sql = "UPDATE users SET deleted_at = CURRENT_TIMESTAMP WHERE id = ?"
)
@SQLRestriction("deleted_at IS NULL")
public class LegacyUser {

    @Id
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private Long tenantId;

    @Column(name = "normalized_email", nullable = false)
    private String normalizedEmail;

    // ...
}
~~~

`@SQLDelete` thay SQL DELETE trong entity removal path bằng custom statement; `@SQLRestriction` thêm predicate cố định vào các access paths mà Hibernate hỗ trợ.

**Không copy đoạn SQL một-parameter này vào entity có `@Version` hoặc secondary table rồi giả định đúng**. Custom SQLDelete có yêu cầu số lượng/thứ tự JDBC parameters (ID và có thể version) theo mapping/provider. Nếu sai có thể làm mất optimistic locking hoặc gây JDBC error. Cần đối chiếu Hibernate Javadoc/version chính xác.

### 10.2. @Where và @SQLRestriction

Các Hibernate apps cũ có thể dùng:

~~~java
@Where(clause = "deleted = false")
~~~

Các phiên bản Hibernate mới deprecate `@Where` trong những trường hợp và cung cấp `@SQLRestriction`/`@SoftDelete`. Không đổi annotation chỉ dựa tên; phải hiểu tác động tới:
- Direct load theo ID.
- Lazy collection fetch.
- Join/fetch queries.
- Native SQL.
- Bulk DML.
- Caching.
- Admin query cần xem deleted rows.

### 10.3. @Filter có thể bật/tắt nhưng không sửa UNIQUE

`@FilterDef`/`@Filter` cho phép predicate động theo Session. Tuy nhiên, behavior theo query/access path và không bảo vệ mọi direct ID load/native SQL như một security policy.

Quan trọng:

~~~text
Hibernate filter active rows:
  SELECT ... WHERE deleted = false

Database unique constraint:
  UNIQUE(tenant_id, normalized_email)
~~~

Filter chỉ ảnh hưởng những câu query tương ứng; **không thay đổi tập rows mà unique constraint toàn cột kiểm tra**.

### 10.4. Application-managed deleted_at

Một mô hình dễ hiểu để hỗ trợ restore là domain method:

~~~java
@Entity
@Table(name = "users")
public class UserAccount {

    @Id
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private Long tenantId;

    @Column(name = "normalized_email", nullable = false)
    private String normalizedEmail;

    @Column(name = "deleted_at")
    private Instant deletedAt;

    @Version
    private long version;

    protected UserAccount() {}

    public void delete(Instant now) {
        if (deletedAt == null) {
            deletedAt = now;
        }
    }

    public boolean isDeleted() {
        return deletedAt != null;
    }

    public void restore() {
        deletedAt = null;
    }
}
~~~

Cách này **không tự lọc** mọi query Hibernate: repository phải chủ động thêm predicate hoặc mapping restriction. `EntityManager.remove(entity)` vẫn là physical delete nếu không có soft-delete mapping riêng. Ưu điểm là đơn giản và có thể dùng entity-level optimistic locking; nhược điểm là dễ quên filter hoặc bị native writers bypass.

**Dù chọn @SoftDelete, @SQLDelete hay application-managed timestamp, unique index vẫn phải được định nghĩa ở database theo đúng active predicate.**
+
## 11. Tạo user an toàn dưới concurrency

### 11.1. exists() giúp UX nhưng không thay DB constraint

~~~java
boolean taken =
    userRepository.existsByTenantIdAndNormalizedEmailAndDeletedAtIsNull(
        tenantId, normalizedEmail
    );

if (taken) {
    throw new DuplicateEmailException(normalizedEmail);
}
~~~

Đây chỉ là **kiểm tra tại một thời điểm**. Sau SELECT, transaction khác có thể INSERT cùng key trước transaction hiện tại.

Vì vậy database phải có active-only unique index, chẳng hạn PostgreSQL:

~~~sql
CREATE UNIQUE INDEX ux_users_active_tenant_email
ON users (tenant_id, normalized_email)
WHERE deleted_at IS NULL;
~~~

### 11.2. Spring service tạo user

Giả định entity có constructor/factory và repository được cấu hình đúng:

~~~java
@Service
public class RegistrationService {

    private final UserRepository repository;

    public RegistrationService(UserRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Long register(Long tenantId, String email) {
        String normalized = EmailNormalizer.normalize(email);

        if (repository
                .existsByTenantIdAndNormalizedEmailAndDeletedAtIsNull(
                    tenantId, normalized)) {
            throw new DuplicateEmailException(normalized);
        }

        UserAccount user =
            UserAccount.create(tenantId, email, normalized);

        repository.saveAndFlush(user);
        return user.getId();
    }
}
~~~

`EmailNormalizer`, `DuplicateEmailException` và `UserAccount.create` là các thành phần ứng dụng tự định nghĩa. `saveAndFlush` giúp đẩy SQL sớm, nhưng không biến precheck thành atomic lock hoặc tương đương commit. Với deferred constraints, lỗi vẫn có thể xuất hiện tại commit.

### 11.3. Bắt unique violation ở ranh giới phù hợp

Trong Spring, database integrity errors có thể được dịch thành `DataIntegrityViolationException`. Tuy nhiên exception này **không chỉ là duplicate email**: CHECK, NOT NULL, FK cũng có thể gây lỗi cùng loại.

Cách xử lý:
- Đặt tên constraint/index rõ ràng: `ux_users_active_tenant_email`.
- Dùng SQLState/vendor error code/constraint metadata để xác định đúng loại lỗi.
- Chỉ map **constraint của use case** thành HTTP `409 Conflict` hay `DuplicateEmail`.
- Các constraint khác được xử lý đúng loại hoặc báo lỗi hệ thống; không che lỗi schema.
- Không rò rỉ raw SQL, email/PII hoặc internal constraint details trong API.
- Nếu lỗi phát ở transaction commit sau method return, exception handling phải ở tầng ngoài transaction proxy phù hợp.

**Không bắt integrity exception trong transaction đã rollback-only rồi tiếp tục repository writes như thể vẫn sạch.** Nếu có retry phải dùng transaction mới.

### 11.4. Hai transactions chạy song song

~~~text
T1: SELECT active email? -> chưa có
T2: SELECT active email? -> chưa có

T1: INSERT active (tenant=7, email=x)
T2: INSERT active (tenant=7, email=x)

Unique index của DB:
  chỉ một active row cùng key có thể được commit.
  transaction còn lại có thể chờ hoặc lỗi theo DB/isolation.
~~~

Ngay cả khi có `exists` check ở cả hai threads, constraint DB mới bảo đảm không có hai active rows hợp lệ cùng key. Ứng dụng phải coi unique conflict là một kết quả nghiệp vụ bình thường.

### 11.5. Security và response khi duplicate email

Có thể trả `201 Created` khi tạo, `409 Conflict` khi key đã được dùng, `400 Bad Request` khi input sai. Tuy nhiên trong luồng identity/registration, trả “email này tồn tại” cho caller chưa xác thực có thể tạo nguy cơ account enumeration.

**Uniqueness strategy** và **error disclosure policy** là hai quyết định khác nhau; không leak thông tin chủ sở hữu email chỉ vì database trả duplicate-key error.

## 12. Xóa mềm rồi tạo lại cùng key trong một transaction

### 12.1. Hibernate ActionQueue có thể đảo thứ tự SQL

Giả sử User#101 đang active với `x@example.com`. Use case cần:
1. Xóa mềm User#101.
2. Tạo User#202 cùng email.
3. Commit hai bước atomically.

Code ban đầu:

~~~java
@Transactional
public void replaceUser(Long oldId, UserAccount replacement) {
    UserAccount old = em.find(UserAccount.class, oldId);

    old.delete(Instant.now());
    em.persist(replacement);
}
~~~

Hibernate **không bảo đảm luôn phát SQL theo đúng thứ tự câu lệnh Java**, do action queue, identifier generation và flush ordering. Nếu INSERT replacement được gửi khi old row vẫn active ở database, unique index sẽ từ chối.

### 12.2. Flush tường minh trước khi INSERT mới

~~~java
@Transactional
public void replaceUser(Long oldId, UserAccount replacement) {
    UserAccount old = em.find(UserAccount.class, oldId);

    if (old == null || old.isDeleted()) {
        throw new IllegalStateException("Old user is not active");
    }

    old.delete(Instant.now());

    // UPDATE soft-delete phải được gửi DB trước INSERT.
    em.flush();

    em.persist(replacement);
    em.flush();
}
~~~

Đây là thứ tự rõ ràng:
1. UPDATE old row sang deleted.
2. Partial/filtered index không còn tính old row là active trong transaction hiện tại.
3. INSERT replacement active.
4. Transaction manager commit/rollback cả hai.

Lưu ý:
- `flush()` **không commit** và có thể flush các pending changes khác trong context.
- Nếu dùng Hibernate `@SoftDelete` + `em.remove(old)` thay vì `old.delete(...)`, mapping/lifecycle khác; kiểm tra generated SQL đúng phiên bản.
- Nếu transaction khác cũng đang tạo cùng key, index vẫn có thể gây conflict.
- Không bỏ optimistic version check hoặc xóa/clear managed graph bừa bãi.
- Nếu old row cần giữ lịch sử, đừng gọi physical DELETE thay cho soft-delete operation.

### 12.3. Native SQL có thể giải phóng key trực tiếp

~~~java
@Transactional
public void replaceUsingSql(Long oldId) {
    int deleted = em.createNativeQuery(
        """
        UPDATE users
           SET deleted_at = CURRENT_TIMESTAMP,
               version = version + 1
         WHERE id = :oldId
           AND deleted_at IS NULL
        """
    )
    .setParameter("oldId", oldId)
    .executeUpdate();

    if (deleted != 1) {
        throw new IllegalStateException(
            "Old user missing or already deleted"
        );
    }

    // INSERT replacement trong cùng transaction.
    // Native DML không refresh managed old user tự động.
}
~~~

Một native UPDATE trực tiếp có thể làm old row ngừng thuộc partial index; nhưng managed object đã nạp có thể stale. Sau đó cần xử lý refresh/clear/context mới nếu tiếp tục dùng nó.

### 12.4. Concurrency của delete+create

~~~text
T1: soft-delete User#101, chưa commit
T2: INSERT User#202 cùng email

T2 có thể phải đợi transaction T1, hoặc gặp
unique/serialization conflict theo DB và isolation.
~~~

Không suy luận rằng chỉ cần T1 `flush()` là T2 chắc chắn nhìn thấy key đã được giải phóng: T1 chưa commit, transaction visibility/locks vẫn có hiệu lực.

### 12.5. Chuyển email không chỉ là SQL

Nếu “thay thế user” là chuyển quyền sở hữu email, phải xét quyền truy cập, xác minh danh tính, liên kết external IDs, tokens/sessions, audit và privacy rules. Unique index chỉ đảm bảo **data invariant về key**, không xác nhận người đăng ký mới được phép sở hữu key cũ.
+
## 13. Phục hồi bản ghi xóa mềm: trường hợp khó hơn đăng ký

### 13.1. Xung đột restore sau khi key đã tái sử dụng

Giả sử:

| id | normalized_email | deleted_at |
|---:|---|---|
| 101 | x@example.com | 2026-01-01 |
| 202 | x@example.com | NULL |

User#101 muốn restore:

~~~sql
UPDATE users
SET deleted_at = NULL
WHERE id = 101;
~~~

Partial unique index sẽ từ chối vì User#202 đang active với cùng key. Đây là **hành vi đúng** khi quy tắc chỉ cho một active user.

Ứng dụng cần **restore conflict policy**; không có một lệnh `em.refresh()` nào giải quyết ràng buộc này.

### 13.2. Bốn hướng xử lý restore

1. **Từ chối restore:** yêu cầu chủ tài khoản chọn email/slug mới.
2. **Restore với business key mới:** xác minh quyền sở hữu rồi đổi email/slug của row cũ trong cùng transaction.
3. **Restore thành pending/review:** chưa phải active nên chưa chiếm active-key uniqueness; khi kích hoạt phải kiểm tra lại.
4. **Merge dữ liệu vào current active account:** chỉ khi có workflow identity verification, authorization, audit và chính sách dữ liệu minh bạch.

Đặc biệt với email/username, tự động restore/merge có thể gây account takeover hoặc leak lịch sử của người sở hữu trước.

### 13.3. Restore bằng conditional UPDATE và version

~~~sql
UPDATE users
   SET deleted_at = NULL,
       version = version + 1
 WHERE id = :id
   AND deleted_at IS NOT NULL
   AND version = :expected_version;
~~~

Kết quả:
- Affected rows = 0: row thiếu, đã active hoặc version không khớp.
- Unique violation: một active row khác đã chiếm key.
- Thành công: database chấp nhận UPDATE trong transaction; chưa đồng nghĩa đã commit.

Khi muốn đổi email trong cùng operation:

~~~sql
UPDATE users
   SET normalized_email = :new_normalized_email,
       email = :new_email,
       deleted_at = NULL,
       version = version + 1
 WHERE id = :id
   AND deleted_at IS NOT NULL
   AND version = :expected_version;
~~~

Unique index kiểm tra trạng thái active và key **sau** update. Hai requests restore/register cùng new email vẫn có thể race; phải xử lý database conflict.

### 13.4. Hibernate @SoftDelete và quyền nhìn thấy deleted rows

Với `@SoftDelete` hoặc static `@SQLRestriction`, `em.find(UserAccount.class, deletedId)` thông thường có thể không trả row đã xóa. Vì vậy admin restore cần:
- Truy vấn chuyên biệt với quyền hạn rõ, thường là native SQL hoặc mapping/admin path được kiểm soát.
- Predicate `WHERE deleted...` để tránh restore nhầm.
- Version/ownership checks.
- Stale persistence context và cache handling.
- Test để deleted rows không bị lộ trong API public.

Không “tắt filter toàn hệ thống” chỉ để restore một row nếu làm các deleted records khác lộ ra ngoài.

## 14. Khóa ngoại, lịch sử và định danh ổn định

### 14.1. Đừng dùng email/slug làm foreign key tới user active

Ví dụ:

~~~text
User#101: email=x@example.com, deleted
User#202: email=x@example.com, active

Order#9001 được tạo bởi User#101.
~~~

Nếu order chỉ lưu `user_email=x@example.com` rồi join tới active users, nó có thể **trỏ nhầm User#202** — lỗi dữ liệu và bảo mật.

Hãy dùng surrogate ID:

~~~sql
CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    CONSTRAINT fk_orders_user
        FOREIGN KEY (user_id) REFERENCES users(id)
);
~~~

Order#9001 tiếp tục tham chiếu đúng User#101 dù email được cấp lại cho User#202.

### 14.2. Partial unique index không phải target FK thông thường

Trên PostgreSQL, referenced columns của foreign key phải được bảo vệ bởi primary key, unique constraint hoặc unique index đủ điều kiện **không partial**. Một active-only partial index không phải target FK hợp lệ cho toàn bộ bảng users có nhiều historical rows trùng email.

Vì vậy:
- FK tham chiếu `users.id` (PK).
- `normalized_email` là lookup/business key, không phải identity.
- Nếu cần historical versioning, lưu row ID hoặc version-specific ID ổn định.

### 14.3. Quan hệ user-role cũng cần uniqueness theo trạng thái

Giả sử mỗi user chỉ có một membership active với cùng role:

~~~sql
CREATE TABLE user_roles (
    id BIGINT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    role_id BIGINT NOT NULL,
    deleted_at TIMESTAMP NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
~~~

Trên PostgreSQL:

~~~sql
CREATE UNIQUE INDEX ux_user_roles_active_pair
ON user_roles (user_id, role_id)
WHERE deleted_at IS NULL;
~~~

Nhờ vậy nhiều deleted memberships lịch sử được lưu, nhưng chỉ một active membership có cặp `(user_id, role_id)`.

Nếu `@ManyToMany` dùng join table thuần, soft-delete/audit từng membership row có thể khó quản lý; cân nhắc **association entity** `UserRoleMembership` có ID và trạng thái riêng.

### 14.4. One-to-one active uniqueness

Một quan hệ one-to-one theo active rows có thể cần:
- FK tới target ID.
- Partial unique index trên FK ở bảng soft-deletable.
- Quy tắc restore khi row cũ và row mới cùng tham chiếu một target.

`@OneToOne`/`@JoinColumn(unique = true)` có thể yêu cầu UNIQUE toàn cột, không tự hiểu “chỉ active”; cần schema migration phù hợp.

### 14.5. Đổi email của deleted row thành chuỗi giả có phải giải pháp?

Một workaround là đổi:

~~~text
deleted user email = "x@example.com#deleted#101"
~~~

Điều này có thể giải phóng `UNIQUE(email)` toàn bảng, nhưng **thay đổi dữ liệu lịch sử** và có nhiều rủi ro:
- Audit/legal/privacy requirements.
- References vô tình dựa trên email thay vì ID.
- Khả năng restore.
- Max length/collation và uniqueness của tombstone string.
- Không được gửi email tới địa chỉ giả.
- Vấn đề khi lịch sử được dùng cho đối soát.

Nếu chủ đích là anonymize/scrub PII sau delete theo policy, đó là một workflow riêng. Không xem nó là workaround mặc định thay cho conditional uniqueness.

## 15. Thêm active-only unique index vào database đã có dữ liệu

Với hệ thống chạy production, tạo index là một **migration dữ liệu và ràng buộc**, không chỉ thêm vài dòng SQL.

### 15.1. Kiểm tra active duplicates trước migration

Trên PostgreSQL/SQL tương tự:

~~~sql
SELECT tenant_id, normalized_email, COUNT(*) AS active_count
FROM users
WHERE deleted_at IS NULL
GROUP BY tenant_id, normalized_email
HAVING COUNT(*) > 1;
~~~

Nếu có rows, tạo unique index sẽ thất bại. Trước khi quyết định sửa dữ liệu:
- Xác định row nào thực sự là owner hợp lệ.
- Kiểm tra linked data, sessions, orders, tokens.
- Xác định có phải normalized emails chưa thống nhất không.
- Lập kế hoạch merge, rename, soft-delete hay manual remediation.
- Có audit/reconciliation và approval phù hợp.

Không tự động “giữ ID nhỏ nhất, xóa các row còn lại” trên dữ liệu người dùng thật khi chưa có business policy.

### 15.2. Nếu đang có UNIQUE toàn bảng

Ví dụ bảng đang có `UNIQUE(tenant_id, normalized_email)`, nên deleted rows vẫn giữ key.

Để chuyển sang chỉ unique active:
1. Xác định tên chính xác của existing constraint/index.
2. Kiểm tra dữ liệu active duplicates (thường không có nếu old constraint còn enforce).
3. Tạo index mới có active-only predicate.
4. Kiểm tra build thành công và SQL/write behavior.
5. Gỡ old full-table constraint trong một migration có kiểm soát.
6. Đảm bảo không còn một unique index toàn cột thứ hai đang chặn reuse.
7. Deploy application paths tương ứng, test đăng ký/xóa/restore.

Điều kiện migration có thể tạm **chặt hơn cần thiết** khi cả hai indexes cùng tồn tại; đây thường là sự đánh đổi an toàn để không có khoảng trống hoàn toàn thiếu uniqueness.

### 15.3. PostgreSQL CREATE INDEX CONCURRENTLY

Với bảng lớn, PostgreSQL có:

~~~sql
CREATE UNIQUE INDEX CONCURRENTLY ux_users_active_tenant_email
ON users (tenant_id, normalized_email)
WHERE deleted_at IS NULL;
~~~

`CONCURRENTLY` giảm một số dạng blocking writes trong quá trình build, nhưng:
- Không được thực thi trong một transaction block thông thường.
- Có thể mất thời gian đáng kể và bị ảnh hưởng bởi concurrent transactions.
- Nếu active duplicate được tạo trong lúc build hoặc dữ liệu đã duplicate, build có thể fail.
- Index không hợp lệ/incomplete có thể cần cleanup/retry theo PostgreSQL docs.
- Migration tool (Flyway/Liquibase) phải được cấu hình cho statement không chạy trong transaction theo cơ chế hỗ trợ của nó.

Đừng thêm `CONCURRENTLY` vào một migration framework mặc định wrap tất cả statements trong transaction rồi mong nó hoạt động.

### 15.4. Gỡ old constraint không giống gỡ index

Nếu ràng buộc được khai báo:

~~~sql
ALTER TABLE users
ADD CONSTRAINT uq_users_tenant_email
UNIQUE (tenant_id, normalized_email);
~~~

thì trên PostgreSQL có thể gỡ bằng:

~~~sql
ALTER TABLE users
DROP CONSTRAINT uq_users_tenant_email;
~~~

Nếu old uniqueness chỉ là index độc lập thì cần thao tác `DROP INDEX` phù hợp thay vì `DROP CONSTRAINT`. Đừng đoán đối tượng chỉ từ tên, và không gỡ PK/FK dependencies ngoài phạm vi migration được phê duyệt.

### 15.5. MySQL generated unique migration

Nếu dùng generated active key:
1. Kiểm tra MySQL/MariaDB version, DDL support và table size.
2. Tạo generated column với expression đúng active status.
3. Kiểm tra duplicates khi tạo UNIQUE.
4. Xác minh generated value chuyển đúng giữa active/deleted.
5. Chỉ sau đó gỡ unique constraint toàn bảng nếu có.
6. Theo dõi locks/replication lag/online DDL behavior.

`ALTER TABLE` thêm generated column và index có thể tái xây bảng/chiếm tài nguyên tùy engine/version; cần staging benchmark và maintenance/online migration strategy.

### 15.6. Migration trong hệ thống nhiều service ghi chung

Trong thời gian cutover:
- Một service cũ có thể vẫn dùng `UNIQUE(email)` logic trong precheck.
- Service mới có thể cho reuse nhưng DB chưa gỡ old constraint.
- Một ETL có thể ghi duplicated active values trong cửa sổ thay đổi.
- Read replicas/schema version có thể chưa đồng bộ.
- Các nodes có Hibernate schema validation/DDL mode khác nhau.

Dùng rollout plan theo version:
1. Chuẩn hóa inputs/validators ở mọi writers.
2. Triển khai DB guardrail mới.
3. Chuyển hành vi API sang reuse-active-only.
4. Gỡ guardrail cũ khi không còn cần.
5. Giám sát unique violation rates và data anomalies.

Trong production, không dựa vào `hibernate.hbm2ddl.auto=update` để tự tạo/gỡ đúng các partial indexes; để migration là nguồn sự thật. `ddl-auto=validate` cũng không thay thế việc kiểm tra partial-index definitions/semantics bằng DB catalog/test.

## 16. SQL xử lý dữ liệu đã xóa và truy vấn lịch sử

### 16.1. Query active phải nhất quán với index

~~~sql
SELECT id, tenant_id, email
FROM users
WHERE tenant_id = :tenant_id
  AND normalized_email = :normalized_email
  AND deleted_at IS NULL;
~~~

Phải sử dụng **cùng business key normalization** và cùng predicate active như unique index. Nếu application tìm bằng `lower(email)` nhưng index unique theo `normalized_email` được cập nhật không nhất quán, có thể tìm thấy kết quả khác quy tắc DB.

### 16.2. Query lịch sử không thể chỉ lấy entity filter mặc định

Để xem các user records cùng email trong lịch sử:

~~~sql
SELECT id, email, deleted_at, version
FROM users
WHERE tenant_id = :tenant_id
  AND normalized_email = :normalized_email
ORDER BY deleted_at DESC NULLS FIRST, id;
~~~

`NULLS FIRST` ví dụ trên phù hợp PostgreSQL; database khác có syntax/order khác. Query này cố ý **không lọc deleted_at IS NULL** và vì vậy phải có authorization/audit giới hạn ai được xem PII/historical identities.

Nếu entity mapping Hibernate `@SoftDelete` luôn lọc deleted, một admin report có thể cần native SQL/read model riêng, không “hạ” mọi default filters trong request public.

### 16.3. Active unique index thường không giúp mọi historical report

Partial index active không chứa deleted rows. Nếu admin report thường tìm historical records theo tenant/email, có thể cần index khác:

~~~sql
CREATE INDEX ix_users_tenant_email_history
ON users (tenant_id, normalized_email, deleted_at);
~~~

Index này **không UNIQUE** và bao gồm historical rows. Cần đo query plan/write overhead trước khi tạo; mỗi index bổ sung tăng chi phí INSERT/UPDATE và storage.

### 16.4. Soft delete row vẫn giữ khóa chính và audit identity

Nếu xóa mềm `id=101` rồi đăng ký user mới `id=202` cùng email, chúng là **hai thực thể lịch sử khác nhau**. Không gộp identity, không chuyển foreign keys cũ sang user 202 chỉ vì email giống.

Unique active key được giải phóng không có nghĩa primary key hoặc quan hệ lịch sử được tái sử dụng.
+
## 17. Concurrency ngoài bài toán uniqueness đơn giản

### 17.1. Hai requests cùng đăng ký

Unique index bảo đảm chỉ có tối đa một active row cùng key sau khi các writes được xác nhận. Nó không quyết định request nào “thắng” về mặt nghiệp vụ. API phải xử lý unique violation và trả response an toàn.

Nếu cần idempotent registration, hãy thiết kế idempotency key/request ownership riêng; không xem `ON CONFLICT DO NOTHING` là đủ để trả row thuộc về người khác.

### 17.2. Delete và restore đồng thời

Giả sử User#101 đã deleted, transaction T1 chuẩn bị restore. Trong khi đó T2 đăng ký một User#202 với cùng email và commit. T1 cập nhật `deleted_at=NULL` và phải bị unique index từ chối hoặc gặp transaction serialization conflict theo DB.

**Không chỉ kiểm tra exists() trước khi restore rồi bỏ unique DB guard.**

### 17.3. Đổi email trong hai transactions

T1 muốn đổi User A sang `new@example.com`, T2 muốn đổi User B cùng email. Cả hai có thể thấy key chưa bị dùng. Unique index phân xử.

`@Version` giúp ngăn **hai requests cùng sửa một row**. Active-only unique index giúp ngăn **hai rows khác nhau cùng chiếm business key**. Hai cơ chế bảo vệ các loại race khác nhau và nên phối hợp khi nghiệp vụ cần.

### 17.4. Native/secondary writers

ETL hoặc admin SQL có thể set `deleted_at=NULL` mà bỏ qua authorization workflow. Unique index vẫn chặn duplicate active key, nhưng DB không tự biết ai được quyền restore row cũ. Cần database privileges, audit trail và policy rõ ràng.

### 17.5. Precheck + constraint + retry

Một workflow thường hợp lý:

~~~text
Validate & normalize
          |
          v
Optional exists() check -> Thông báo sớm
          |
          v
INSERT / restore / rename trong transaction
          |
          v
Database active-key unique index
       /         \
  success       conflict
     |             |
   commit        rollback
     |             |
  response      409 / xử lý theo policy
~~~

Không retry vô hạn một duplicate deterministic vì key đã thuộc owner khác. Deadlock/serialization failure có thể là transient và retry trong **transaction mới** với backoff/giới hạn, nhưng mỗi lần phải kiểm tra lại điều kiện nghiệp vụ.

### 17.6. Multi-node và sharding

Hai application nodes có thể cache `existsBy...` nhưng cache không biến precheck thành distributed lock. Primary database unique constraint là authoritative.

Nếu dữ liệu được shard, một unique index chỉ đảm bảo uniqueness **bên trong shard**. Muốn global uniqueness phải route business key nhất quán tới shard hoặc dùng key registry/claim service có cơ chế consensus/transaction phù hợp.

## 18. Một chiến lược khác: bảng giữ quyền sở hữu business key

Nếu chính sách có thời gian giữ chỗ, revoke, chuyển quyền sở hữu hoặc nhiều trạng thái, partial index có thể chưa đủ. Khi đó tách **quyền sở hữu key hiện tại** khỏi rows lịch sử.

### 18.1. Bảng claims

~~~sql
CREATE TABLE user_email_claims (
    tenant_id BIGINT NOT NULL,
    normalized_email VARCHAR(320) NOT NULL,
    owner_user_id BIGINT NOT NULL,
    CONSTRAINT pk_user_email_claims
        PRIMARY KEY (tenant_id, normalized_email),
    CONSTRAINT fk_email_claim_owner
        FOREIGN KEY (owner_user_id) REFERENCES users(id)
);
~~~

Bảng này lưu keys còn được **claim/reserve**. Bảng users vẫn chứa nhiều historical rows cùng email.

~~~text
users:
  User#101  email=x@x.com  deleted
  User#202  email=x@x.com  active

user_email_claims:
  tenant=7, email=x@x.com, owner_user_id=202
~~~

Khi cấp key, insert claim và tạo/activate user trong cùng transaction. Khi soft-delete, quyết định xóa claim ngay hay giữ thêm 30 ngày theo nghiệp vụ.

### 18.2. Ưu/nhược điểm

Ưu điểm:
- PK unique của claims diễn đạt một owner hoặc reservation rõ.
- Có thể thêm `reserved_until`, reason, transfer status.
- Historical rows độc lập với quyền sở hữu hiện tại.

Nhược điểm:
- Hai bảng phải được cập nhật **atomically**.
- Cần xử lý stale/orphan claims và reconciliation.
- Chuyển owner phải có locking/version strategy.
- Cache của claims có thể stale; DB PK vẫn là guardrail cuối.
- Thiết kế phức tạp hơn partial index cho rule đơn giản.

**Nếu chỉ cần “một active row cho mỗi tenant/email”, partial/filtered index thường dễ triển khai và vận hành hơn bảng claims.**
+
## 19. Ghi hàng loạt, bulk DML và cache sau soft delete

### 19.1. Bulk soft delete

Ví dụ này dành cho mapping có field `deletedAt` và có `lastSeenAt`, không phải Hibernate `@SoftDelete` boolean:

~~~java
@Transactional
public int deleteInactive(Instant cutoff) {
    return em.createQuery(
        """
        update UserAccount u
           set u.deletedAt = :now
         where u.deletedAt is null
           and u.lastSeenAt < :cutoff
        """
    )
    .setParameter("now", Instant.now())
    .setParameter("cutoff", cutoff)
    .executeUpdate();
}
~~~

Bulk UPDATE có thể giải phóng nhiều active keys trong partial index nhưng:
- Không đồng bộ managed user instances đã load trong L1.
- Không gọi lifecycle callbacks cho từng user.
- Không mặc định tăng `@Version` giống entity-level dirty checking.
- Có thể ảnh hưởng L2/query cache khi dữ liệu thay đổi ngoài đường ORM quản lý.
- Có thể giữ locks lâu và gây index maintenance đáng kể.

Nếu nghiệp vụ cần version, audit, timestamps hoặc event, phải đưa chúng vào DML/DB/workflow riêng. Đừng hy vọng filter soft delete tự cung cấp những hiệu ứng đó.

### 19.2. JDBC batching vẫn chịu unique constraint

Nếu JDBC driver gửi 1.000 INSERT active users bằng `PreparedStatement.addBatch()/executeBatch()`, unique index vẫn được DB enforce. Batching **không miễn ràng buộc**.

Khi có duplicate:
- `BatchUpdateException` có thể xuất hiện.
- Driver trả update counts có thể có `SUCCESS_NO_INFO` hoặc partial-failure semantics.
- Transaction thường cần rollback cả chunk.
- Không giả định rows trước lỗi đã commit.
- Cần idempotency key và retry trên transaction mới khi thích hợp.

### 19.3. L1/L2/query cache khi SQL trực tiếp thay đổi deleted_at

Native/JDBC UPDATE có thể làm một `UserAccount` đang managed trong EntityManager giữ `deletedAt=null` dù database đã ghi timestamp. Dùng `refresh`/`clear` hoặc context mới khi cần đọc lại state.

`clear()` chỉ detach L1; nó không tự evict L2/query/application caches. Hibernate native query synchronization có thể hỗ trợ cache/query space coordination theo version/API nhưng **không tự làm per-entity refresh**. JDBC của process khác không gửi cache invalidation cho Hibernate SessionFactory.

Nếu dùng outbox/CDC để phát hiện soft-delete/restore, có thể làm mới:
- Entity cache theo ID.
- Query cache của tập active users.
- Collection cache của tenant/group.
- API/Redis caches liên quan.
- Search index hoặc materialized read models.

### 19.4. Retention/purge là nghiệp vụ riêng

Một hệ thống có thể giữ deleted rows 90 ngày rồi purge vật lý. Purge ảnh hưởng storage, FK/history references, privacy retention và cascades. Nếu partial index đã bỏ deleted rows thì purge **không cần thiết để giải phóng active business key**. Không dùng physical purge thay thế restore/reuse policy mà không xem xét audit.

## 20. Kiểm chứng trên database mục tiêu

### 20.1. Vì sao mock repository không đủ?

Mock `existsBy...` không chứng minh database sẽ chặn hai INSERT đồng thời. H2/SQLite in-memory cũng có thể khác production về:
- Partial/filtered unique index support.
- Generated/functional columns.
- NULL unique semantics.
- Collation/case-folding.
- DDL transaction và online/concurrent index build.
- Locking, isolation, constraint timing.
- JDBC exception translation.

Cần integration test trên đúng DB engine/version hoặc môi trường tương thích cao, ví dụ Testcontainers với PostgreSQL/MySQL.

### 20.2. Test matrix

| Test | Input/operation | Kết quả mong đợi |
|---|---|---|
| First active | Chưa có active key | Insert thành công |
| Duplicate active | Hai rows cùng tenant/email active | Row thứ hai bị unique violation |
| Cross-tenant | Cùng email, khác tenant | Thành công nếu policy per-tenant |
| Multiple tombstones | Hai deleted rows cùng key | Thành công |
| Delete then recreate | Soft-delete A, tạo B cùng key | Thành công khi SQL/transaction đúng thứ tự |
| Delete second generation | Soft-delete B khi A đã deleted | Thành công |
| Restore without conflict | Old deleted, chưa ai dùng key | Thành công |
| Restore with conflict | Old deleted, new active đang dùng key | Unique violation |
| Rename to taken | Hai active users đổi cùng email | Một bị conflict |
| Two concurrent registrations | Hai transactions tạo cùng active key | Tối đa một commit thành công |
| Case variants | `A@x.com` và `a@x.com` | Theo normalization policy |
| NULL active email | Active key thiếu | Bị NOT NULL/CHECK chặn nếu policy yêu cầu |
| JDBC restore duplicate | SQL không qua Hibernate | Database vẫn chặn |
| FK to historical row | Order gắn User#101 khi key tái dùng | Vẫn trỏ User#101 |
| SoftDelete mapping | ORM cập nhật đúng indicator | Index predicate khớp trạng thái |
| Bulk soft delete | Nhiều users chuyển deleted | Active keys giải phóng, cache policy phù hợp |

### 20.3. Dữ liệu kiểm tra PostgreSQL

Ví dụ tạo ba row cùng key trong một tenant, hai deleted và một active:

~~~sql
INSERT INTO users (
    id, tenant_id, email, normalized_email,
    display_name, deleted_at, version
)
VALUES
 (101, 7, 'x@example.com', 'x@example.com', 'Old',
  '2026-01-01', 0),
 (102, 7, 'x@example.com', 'x@example.com', 'Older',
  '2026-02-01', 0),
 (103, 7, 'x@example.com', 'x@example.com', 'Current',
  NULL, 0);
~~~

Với partial index đúng, ba rows này hợp lệ. Thử thêm active thứ hai:

~~~sql
INSERT INTO users (
    id, tenant_id, email, normalized_email,
    display_name, deleted_at, version
)
VALUES (
    104, 7, 'x@example.com', 'x@example.com',
    'Duplicate', NULL, 0
);
~~~

câu INSERT phải bị từ chối. Đừng cho deliberate failure làm abort toàn transaction test rồi tiếp tục assertions trong cùng transaction bị lỗi; tách transaction/test case hoặc dùng savepoint/rollback strategy đúng.

### 20.4. Test xóa mềm nhiều thế hệ

1. Tạo User A active.
2. Soft-delete A.
3. Tạo User B cùng email active.
4. Soft-delete B.
5. Tạo User C cùng email active.
6. Kiểm tra A và B vẫn deleted, C active duy nhất.

Test này phát hiện trực tiếp bẫy `UNIQUE(email, deleted BOOLEAN)`: thiết kế sai thường fail khi soft-delete B ở bước 4.

### 20.5. Test concurrency với hai transactions thật

Một integration test có thể dùng:
- Hai threads tách biệt, mỗi thread có EntityManager/transaction riêng.
- Barrier để cả hai precheck xong rồi INSERT.
- Commit/rollback với timeout.
- Đọc DB trong transaction mới để assert tối đa một active key.
- Capture lỗi tại `flush` **hoặc commit**, tùy provider.

Không dùng cùng một EntityManager/Session từ hai threads. Không chỉ dựa vào `@Transactional` trên test method nếu điều đó khiến cả hai operations vô tình dùng chung transaction.

### 20.6. Test migration và generated columns

- Xác nhận migration tạo đúng partial predicate/functional expression trên DB catalog.
- Tạo active duplicates phải bị từ chối.
- Tạo nhiều historical deleted rows phải hợp lệ.
- Restore collision phải bị chặn.
- MySQL generated active field có giá trị khi active và NULL khi deleted.
- SQL Server filtered index có cùng effective predicate với Hibernate boolean/timestamp mapping.
- Kiểm tra query plan trên dataset đại diện khi index còn phục vụ lookup lớn.

## 21. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Đăng ký lại email sau delete bị duplicate | `UNIQUE(email)` vẫn bao gồm deleted row | Quyết định policy; active-only index nếu cho reuse |
| Xóa mềm user B cùng email thất bại | `UNIQUE(email, deleted)` chỉ cho một deleted row | Partial/conditional unique |
| Hai active users cùng email được chấp nhận | `UNIQUE(email, deleted_at)` + NULL DISTINCT | Partial/filtered hoặc generated active key |
| @SoftDelete hoạt động nhưng INSERT vẫn lỗi | ORM filter không sửa DB UNIQUE | Migration index đúng predicate |
| @Where/@Filter che row nhưng DB báo duplicate | SELECT filter khác uniqueness domain | Chuyển rule vào DB |
| Exists check rồi vẫn duplicate | Concurrent requests race | DB unique + exception handling |
| Restore user cũ không được | Key đã thuộc active user mới | Restore conflict policy |
| Restore xong getter vẫn cũ | Persistence context/cache stale | Refresh/clear/invalidate |
| Delete rồi create cùng transaction lỗi | SQL INSERT chạy trước soft-delete UPDATE | Explicit flush, kiểm tra SQL order |
| T1 flush rồi T2 vẫn chưa insert được | Lock/isolation, T1 chưa commit | Xác định transaction visibility |
| MySQL generated unique cho active duplicates | Generated key hoặc component key vẫn NULL | NOT NULL/constraint/expression |
| MySQL migration unique fail | Existing duplicates, DDL/version limitation | Remediation và migration plan |
| PostgreSQL concurrent index fail | Transaction block/active duplicates | Nontransactional build và cleanup |
| JPA schema update không tạo partial index | Annotation không biểu đạt predicate | Flyway/Liquibase |
| Email hoa/thường vẫn trùng | Normalization/collation không thống nhất | DB index semantics + normalize |
| Query planner không dùng index | Predicate/expression không khớp | EXPLAIN, statistics |
| Order trỏ nhầm user mới | Tham chiếu email thay surrogate ID | Stable PK/FK |
| Admin không thấy deleted user | Hibernate filter/SQLRestriction | Admin query có quyền |
| Bulk soft-delete không tăng version | Bypass entity-level @Version | Version strategy explicit |
| SQL ngoài Hibernate vẫn bị duplicate | DB constraint hoạt động đúng | Fix input/workflow |
| API trả 500 thay vì 409 | Thiếu unique constraint-aware mapping | Kiểm tra SQLState/index name |
| Transaction rollback-only sau catch | Integrity violation trong transaction | Rollback và retry ở transaction mới |
| Report lịch sử chậm | Active-only index không chứa deleted rows | History index nếu workload cần |
| Old unique index vẫn tồn tại | Chưa gỡ constraint full-table | Kiểm tra DB catalog/migration |
| Hai tenants chặn trùng email | Key thiếu tenant_id | Xác định business scope |
| Account takeover sau reuse | Identity ownership chưa xác minh | Authorization/verification/audit |
+
## 22. Bài tập thực hành

### Bài 1 — Tại sao UNIQUE(email) gây lỗi?

Bảng users có `UNIQUE(email)` và `deleted_at`. User#101 với email `a@example.com` đã bị soft delete.

**Hỏi:** Tại sao INSERT User#202 cùng email vẫn lỗi?

**Đáp án:** Row 101 vẫn nằm trong bảng và vẫn tham gia unique constraint toàn cột. Hibernate filter ẩn row không làm database unique index bỏ row.

### Bài 2 — Khi nào UNIQUE(email) lại đúng?

Một hệ thống cấp mã định danh chứng từ không cho tái sử dụng mã dù bản ghi đã archived.

**Hỏi:** Có nên thay bằng active-only index không?

**Đáp án:** Không. Nếu domain rule bắt buộc không reuse lịch sử, `UNIQUE(document_number)` toàn bảng chính là bảo vệ đúng. Phải xác định business policy trước.

### Bài 3 — Bẫy deleted BOOLEAN

~~~sql
CREATE UNIQUE INDEX uq_bad
ON users(normalized_email, deleted);
~~~

**Hỏi:** User A bị soft-delete, User B dùng lại email rồi cũng soft-delete. Điều gì xảy ra?

**Đáp án:** Bước soft-delete B có thể vi phạm UNIQUE vì cả A/B có `deleted=true` cùng key.

### Bài 4 — Bẫy deleted_at NULL

~~~sql
CREATE UNIQUE INDEX uq_bad2
ON users(normalized_email, deleted_at);
~~~

**Hỏi:** Với PostgreSQL/MySQL NULL DISTINCT mặc định, có thể có hai active rows có `deleted_at=NULL` không?

**Đáp án:** Có thể. Hai composite keys chứa NULL không được so là trùng theo default unique semantics; index không bảo vệ active uniqueness.

### Bài 5 — PostgreSQL partial index

Viết index cấm hai users active cùng email trong một tenant nhưng cho nhiều deleted rows.

**Đáp án:**

~~~sql
CREATE UNIQUE INDEX ux_users_active_tenant_email
ON users (tenant_id, normalized_email)
WHERE deleted_at IS NULL;
~~~

### Bài 6 — MySQL generated active key

**Hỏi:** Với MySQL không dùng PostgreSQL partial-index syntax, làm sao cho nhiều deleted rows cùng email nhưng chỉ một active?

**Đáp án:** Tạo generated column trả normalized email khi `deleted_at IS NULL`, trả `NULL` khi deleted, rồi tạo UNIQUE `(tenant_id, active_email)`.

### Bài 7 — Vì sao active key phải NOT NULL?

**Hỏi:** Nếu `normalized_email=NULL` ngay cả với active row, có vấn đề gì?

**Đáp án:** Với unique semantics của nhiều DB, nhiều NULL có thể bypass duplicate check. Dùng NOT NULL hoặc CHECK/conditional validation để active row luôn có key hợp lệ.

### Bài 8 — Hibernate @SoftDelete

Entity có `@SoftDelete` và Hibernate find không thấy deleted row, nhưng INSERT email cũ vẫn vi phạm UNIQUE.

**Hỏi:** Tại sao?

**Đáp án:** `@SoftDelete` thay đổi ORM entity filtering/deletion behavior, không sửa unique constraint toàn bảng đã được tạo trong database.

### Bài 9 — @UniqueConstraint

~~~java
@Table(uniqueConstraints = @UniqueConstraint(
    columnNames = {"tenant_id", "normalized_email"}
))
~~~

**Hỏi:** Annotation này có tạo `WHERE deleted_at IS NULL` không?

**Đáp án:** Không theo JPA chuẩn. Nó mô tả uniqueness trên cột, không có partial-index predicate. Dùng migration theo dialect.

### Bài 10 — existsByEmailAndDeletedAtIsNull

Hai threads cùng gọi exists và đều nhận false, sau đó INSERT.

**Hỏi:** Chỉ có precheck đã bảo đảm uniqueness chưa?

**Đáp án:** Chưa. Chỉ DB unique index/transaction concurrency mechanism đúng mới bảo đảm không có hai active rows cùng key.

### Bài 11 — SQL order khi xóa rồi tạo

Một transaction thay `deleted_at` của User#101 và persist User#202 cùng key, nhưng flush tạo INSERT trước UPDATE.

**Hỏi:** Hướng khắc phục?

**Đáp án:** Đảm bảo UPDATE soft-delete được gửi DB trước INSERT, ví dụ explicit `entityManager.flush()` sau khi đổi trạng thái old row; vẫn xử lý conflict từ transactions khác.

### Bài 12 — Flush đã giải phóng key cho transaction khác chưa?

T1 soft-delete rồi `flush()` nhưng chưa commit; T2 thử tạo row active cùng email.

**Hỏi:** Có chắc T2 thành công ngay không?

**Đáp án:** Không. DB isolation/unique locks có thể khiến T2 chờ hoặc gặp conflict đến khi T1 commit/rollback.

### Bài 13 — Restore conflict

User A deleted, User B active cùng email.

**Hỏi:** Restore A bằng `deleted_at=NULL` sẽ ra sao?

**Đáp án:** Unique index từ chối. Phải có restore conflict policy: dùng key mới, không restore, pending state hoặc merge qua workflow được xác minh.

### Bài 14 — Phiên bản và key uniqueness

Hai requests cùng sửa **hai users khác nhau** thành email `x@example.com`.

**Hỏi:** `@Version` trên mỗi user đã đủ không?

**Đáp án:** Không. Version giúp bảo vệ update cạnh tranh trên cùng row; unique index cần để bảo vệ việc hai rows khác nhau chiếm một active key.

### Bài 15 — Case-insensitive email

**Hỏi:** Nếu nghiệp vụ coi `User@Example.com` và `user@example.com` là một, index trên email phân biệt case có phù hợp không?

**Đáp án:** Không. Dùng normalized key hoặc expression/collation index đúng semantics. Kiểm tra Unicode/locale và sự thống nhất giữa application với DB.

### Bài 16 — Multi-tenant

Một email được phép xuất hiện một lần mỗi tenant.

**Hỏi:** Nên index key nào?

**Đáp án:** `(tenant_id, normalized_email)` có active predicate. Nếu thiếu tenant_id sẽ hạn chế toàn cục ngoài yêu cầu.

### Bài 17 — FK lịch sử

User A deleted, User B active cùng email. Order cũ của A lưu `user_email` thay vì `user_id`.

**Hỏi:** Rủi ro?

**Đáp án:** Order có thể join nhầm sang B. Phải tham chiếu stable surrogate primary key, ví dụ `orders.user_id → users.id`.

### Bài 18 — Xóa mềm bảng liên kết

Bảng `user_roles` có `user_id`, `role_id` và `deleted_at`.

**Hỏi:** Ràng buộc nào bảo đảm chỉ một active membership cho mỗi user/role?

**Đáp án (PostgreSQL):**

~~~sql
CREATE UNIQUE INDEX ux_user_roles_active_pair
ON user_roles(user_id, role_id)
WHERE deleted_at IS NULL;
~~~

### Bài 19 — Migration dữ liệu cũ

Một hệ thống có nhiều active rows cùng normalized email. Developer chạy CREATE UNIQUE INDEX.

**Hỏi:** Điều gì cần làm trước?

**Đáp án:** Query xác định duplicates, đối soát owner, giải quyết các active conflicts có approval và migration plan. Không tự xóa/merge dữ liệu nhạy cảm.

### Bài 20 — Concurrent index build

PostgreSQL migration có `CREATE UNIQUE INDEX CONCURRENTLY` nhưng migration runner bao cả file trong transaction.

**Hỏi:** Có thể chạy bình thường không?

**Đáp án:** Không. PostgreSQL không cho CREATE INDEX CONCURRENTLY trong transaction block; phải cấu hình migration chạy ngoài transaction thích hợp, có cleanup/retry nếu build thất bại.

### Bài 21 — MySQL collation

MySQL generated `active_email` có collation phân biệt case, nhưng service normalize sai.

**Hỏi:** Active-only uniqueness đã chắc đáp ứng business policy chưa?

**Đáp án:** Chưa. Index key value/collation phải tương đương với cách ứng dụng xác định “cùng email”.

### Bài 22 — Migrations và JPA schema validation

Hibernate `ddl-auto=validate` khởi động thành công.

**Hỏi:** Có chắc partial unique index đúng predicate đã được tạo không?

**Đáp án:** Không. Schema validation không thay thế kiểm tra migration và catalog index definitions/behavior trên DB thật.

### Bài 23 — Admin restore bằng native SQL

Entity có `@SoftDelete`; admin dùng native UPDATE để đưa deleted row trở lại active.

**Hỏi:** Hai điều gì phải đảm bảo?

**Đáp án:** Database unique index sẽ kiểm tra active-key conflict; service phải kiểm soát quyền restore và xử lý persistence context/cache stale, cùng version/audit.

### Bài 24 — Bảng claims

Business rule giữ email 30 ngày sau delete rồi mới reuse.

**Hỏi:** Partial index `WHERE deleted_at IS NULL` đã đủ không?

**Đáp án:** Chưa. Nó giải phóng key ngay khi soft-delete. Cần reserved/claim state, transaction-controlled release hoặc một cơ chế tương đương rõ ràng.

### Bài 25 — Tác động tới cache

ETL dùng JDBC soft-delete một row rồi Hibernate Session mới vẫn trả bản active từ L2/query cache.

**Hỏi:** Unique index có giải quyết dữ liệu stale này không?

**Đáp án:** Không. Unique index bảo vệ write integrity; cache cần invalidation/refresh policy riêng. External JDBC không tự thông báo cho ORM cache.

### Bài 26 — Soft delete bằng bulk HQL

Bulk HQL UPDATE đặt `deletedAt=now` cho 10.000 users.

**Hỏi:** `@PreUpdate`, `@Version` và L1 có tự xử lý như entity-by-entity update không?

**Đáp án:** Không. Bulk DML bypass per-entity callbacks/dirty checking và không tự cập nhật managed objects; cần SQL/version/audit/cache strategy riêng.

### Bài 27 — Error mapping

Spring trả `DataIntegrityViolationException` khi INSERT.

**Hỏi:** Có nên luôn dịch thành “Email đã tồn tại” không?

**Đáp án:** Không. Nó có thể là NOT NULL/FK/CHECK. Cần xác định đúng constraint name/error code trước khi map thành duplicate email/409.

### Bài 28 — Kiểm thử quan trọng nhất

**Hỏi:** Test nào dễ phát hiện `UNIQUE(email, deleted BOOLEAN)` sai ngay cả khi “delete rồi recreate” chạy thành công?

**Đáp án:** Test soft-delete **thế hệ thứ hai**: A deleted, B active cùng key, rồi B cũng deleted. Constraint sai sẽ chặn B chuyển sang deleted.

## 23. Checklist chọn chiến lược triển khai

Khi một dự án Hibernate muốn cho phép tái sử dụng business key sau soft delete, hãy xác nhận:

1. Quy tắc nghiệp vụ là **no-reuse**, **active-only**, hay **reservation theo thời gian**?
2. Key scope là global, per-tenant hay theo parent/group?
3. Giá trị key được normalize bằng quy tắc nào, tại application hay DB?
4. Active state là `deleted=false` hay `deleted_at IS NULL`?
5. Nullability của mọi unique key components có đúng business policy không?
6. Database production hỗ trợ partial/filtered unique index hay phải dùng generated/functional expressions?
7. Có full-table UNIQUE constraint/index cũ đang chặn reuse không?
8. Migration đã xử lý existing duplicates và tương thích DDL/version chưa?
9. Hibernate `@SoftDelete`/`@SQLDelete`/`@Filter` có cùng active predicate với DB không?
10. Creation/restore/rename đều bắt unique violation ở đúng transaction boundary không?
11. Soft-delete rồi tạo lại key trong một transaction có flush/order phù hợp không?
12. Restore conflict và ownership verification được định nghĩa chưa?
13. FK dùng surrogate ID thay vì email/slug tái sử dụng chưa?
14. Bulk/native/JDBC writers có tuân thủ cùng version/normalization/state policy không?
15. L1/L2/query/application caches có invalidation khi direct SQL thay đổi trạng thái không?
16. Query admin/history có quyền truy cập riêng và index riêng khi cần không?
17. Tests chạy trên database engine/version tương ứng production chưa?
18. Security/PII/retention requirements có cho phép tái sử dụng key không?

## 24. Tổng kết

### 24.1. Những cấu hình cần phân biệt

| Cấu hình | Một active key | Nhiều deleted rows trùng key | Nhận xét |
|---|---|---|---|
| `UNIQUE(tenant_id, email)` | Có | **Không** | Giữ key xuyên lịch sử, đúng nếu no-reuse |
| `UNIQUE(tenant_id, email, deleted BOOLEAN)` | Có | **Không** | Chặn nhiều tombstones cùng key |
| `UNIQUE(tenant_id, email, deleted_at NULL)` | **Không đảm bảo** với NULL DISTINCT | Thường có thể | Sai cho active-only dưới default PostgreSQL/MySQL |
| Partial unique `WHERE deleted_at IS NULL` | Có | Có | Phù hợp với PostgreSQL/SQLite/SQL Server-filtered tương ứng |
| MySQL generated active key + UNIQUE | Có | Có | Dùng NULL cho deleted, non-NULL cho active |
| Oracle function-based unique với active CASE | Có | Có | Theo Oracle B-tree/NULL semantics |
| Bảng active/reserved claims có PK key | Có | Có trong users history | Hữu ích khi có thời gian giữ chỗ/transfer workflow |

**Các kết quả giả định tenant/key của active rows có nullability hợp lệ và trạng thái deleted được thể hiện nhất quán.**

### 24.2. Mẫu nhớ nhanh

~~~text
Soft-delete filter:
  quyết định entity/row nào được application đọc.

Conditional unique index:
  quyết định active rows nào được phép cùng tồn tại.

Transaction + flush ordering:
  quyết định khi nào database quan sát việc giải phóng key.

Restore policy:
  quyết định xử lý thế nào nếu key đã có chủ mới.

Stable primary key + FK:
  giữ identity lịch sử không bị thay thế khi key được reuse.
~~~

### 24.3. Ba nguyên tắc quan trọng nhất

**Một:** Ẩn bản ghi khỏi truy vấn Hibernate **không giải phóng unique key** trong database. `@SoftDelete`/`@Filter` là tầng đọc/ghi ORM, không thay thế DDL constraint.

**Hai:** Với yêu cầu “một active, nhiều deleted”, hãy dùng conditional uniqueness đúng DB: partial/filtered unique index hoặc generated/functional active key, chứ không chỉ thêm cột `deleted` vào UNIQUE.

**Ba:** Database uniqueness là **ràng buộc tính toàn vẹn cuối cùng**, nhưng không thay thế transaction design, optimistic locking, quyền sở hữu tài khoản, restore policy, stable FKs, audit và cache invalidation.

### 24.4. Tài liệu chính thức để đối chiếu

- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/) — `@Table`, `@UniqueConstraint`, entity lifecycle và transaction.
- [Hibernate ORM Documentation](https://docs.hibernate.org/orm/) — User Guide và Javadocs cho đúng version.
- [Hibernate ORM 6.6 User Guide](https://docs.hibernate.org/orm/6.6/userguide/html_single/Hibernate_User_Guide.html) — soft delete, filters, mapping, flush/transaction.
- [Hibernate ORM 6.6 @SoftDelete Javadoc](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/annotations/SoftDelete.html) — indicator strategy và scope.
- [Hibernate ORM 6.6 @SQLDelete Javadoc](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/annotations/SQLDelete.html) — custom SQL cho entity delete.
- [PostgreSQL — Partial Indexes](https://www.postgresql.org/docs/current/indexes-partial.html) — partial unique index và predicate matching.
- [PostgreSQL — Unique Indexes](https://www.postgresql.org/docs/current/indexes-unique.html) — unique constraints, NULL semantics.
- [PostgreSQL — CREATE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html) — `CONCURRENTLY`, predicates và index options.
- [MySQL Reference Manual — CREATE TABLE Generated Columns](https://dev.mysql.com/doc/refman/8.4/en/create-table-generated-columns.html) — generated-column definitions.
- [MySQL Reference Manual — Multiple-Column Indexes](https://dev.mysql.com/doc/refman/8.4/en/multiple-column-indexes.html) — index design; đối chiếu UNIQUE và NULL docs cùng phiên bản.
- [Microsoft Learn — Create Filtered Indexes](https://learn.microsoft.com/en-us/sql/relational-databases/indexes/create-filtered-indexes) — SQL Server filtered indexes.
- [SQLite — Partial Indexes](https://www.sqlite.org/partialindex.html) — partial unique indexes.
- [Oracle Database — Function-Based Indexes](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-INDEX.html) — function-based unique index và expression constraints.
- [Spring Data JPA Reference](https://docs.spring.io/spring-data/jpa/reference/) — repository transactions, modifying queries, exception handling.
- [Flyway Documentation](https://documentation.red-gate.com/fd) / [Liquibase Documentation](https://docs.liquibase.com/) — quản lý migrations có điều kiện theo database.

> SQL/annotation trong bài là các mô hình minh họa, không phải một migration portable cho mọi hệ quản trị. Khi đưa vào production, xác nhận DB engine/version, Hibernate version, active-state mapping, collation, nullable columns, concurrency/transaction behavior, existing constraints và authorization policy. **Một partial index đúng cú pháp nhưng sai scope hoặc normalization vẫn có thể bảo vệ sai quy tắc nghiệp vụ.**


