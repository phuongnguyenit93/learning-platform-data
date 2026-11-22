# Row-Level Security, policy, USING và WITH CHECK trong PostgreSQL

Giả sử một ứng dụng SaaS lưu tài liệu của nhiều tổ chức trong cùng bảng `documents`. Mỗi tài liệu có `tenant_id` hoặc một định danh chủ sở hữu. Nếu tầng ứng dụng vô tình bỏ điều kiện `WHERE tenant_id = ...`, một truy vấn bình thường có thể làm lộ dữ liệu tổ chức khác. **Row-Level Security (RLS)** trong PostgreSQL giúp đặt thêm quy tắc quyền truy cập **ở cấp hàng ngay trong cơ sở dữ liệu**.

Ví dụ, thay vì chỉ dựa vào việc từng lập trình viên nhớ viết:

```sql
SELECT *
FROM documents
WHERE tenant_id = 42;
```

người quản trị có thể tạo một **policy** để PostgreSQL chỉ cho một database role nhìn thấy hoặc thay đổi những hàng thuộc phạm vi của role ấy. Quy tắc đó áp dụng khi người dùng truy vấn trực tiếp bảng, kể cả khi câu `SELECT` không có predicate tenant riêng.

Hai biểu thức cốt lõi trong policy là:

- **`USING`:** xác định những **hàng hiện có** được phép nhìn thấy hoặc là đối tượng của `UPDATE`/`DELETE`.
- **`WITH CHECK`:** xác định **hàng mới hoặc phiên bản mới của hàng sau thay đổi** có được phép ghi bằng `INSERT`/`UPDATE` hay không.

Đây là khác biệt rất quan trọng: người dùng có thể được phép sửa hàng họ đang sở hữu, nhưng **không nhất thiết được phép chuyển hàng sang tenant khác**. `USING` kiểm tra hàng cũ; `WITH CHECK` kiểm tra hàng được đề xuất ghi.

Tuy nhiên, RLS **không thay thế** `GRANT`, authentication, quyền trên cột, kiểm tra dữ liệu đầu vào hoặc bảo mật ứng dụng. Chủ sở hữu bảng, superuser, các role có `BYPASSRLS` và các object/function chạy bằng ngữ cảnh quyền khác có thể ảnh hưởng việc thực thi. Bài học này xây dựng đầy đủ một lab an toàn, giải thích chính xác khi nào RLS lọc hàng, khi nào từ chối ghi, cách ghép nhiều policy, và những bẫy khi ứng dụng dùng connection pool, view hoặc `SECURITY DEFINER`.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích RLS khác quyền bảng/cột (`GRANT`/`REVOKE`) ở điểm nào.
2. Bật/tắt RLS cho một bảng bằng `ALTER TABLE ... ENABLE/DISABLE ROW LEVEL SECURITY`.
3. Đọc cú pháp `CREATE POLICY`, `ALTER POLICY` và `DROP POLICY`.
4. Phân biệt ngữ nghĩa `USING` với `WITH CHECK` trên `SELECT`, `INSERT`, `UPDATE` và `DELETE`.
5. Hiểu mặc định **không có policy thì từ chối** đối với những role chịu RLS.
6. Giải thích `AS PERMISSIVE` và `AS RESTRICTIVE`, cách kết hợp chính sách bằng OR/AND và yêu cầu có ít nhất một policy permissive phù hợp.
7. Nhận diện ngoại lệ: table owner, `FORCE ROW LEVEL SECURITY`, superuser và role `BYPASSRLS`.
8. Xây ví dụ multi-tenant dùng database roles và kiểm thử với `SET ROLE` trong database lab.
9. Tách biệt quyền đọc hàng, quyền sửa hàng và quyền thay đổi giá trị tenant trong hàng.
10. Quan sát `pg_policies`, metadata catalog và xử lý các tình huống “SELECT thấy 0 hàng”, “UPDATE 0 rows”, “new row violates row-level security policy”.
11. Đánh giá giới hạn RLS với `SECURITY DEFINER`, view, connection pooling, session context, constraints và các lệnh không chịu row policy như `TRUNCATE`.
12. Thiết kế kiểm thử phòng rò rỉ dữ liệu giữa tenants và phân quyền tối thiểu cho môi trường production.

## 2. Phân biệt GRANT với Row-Level Security

PostgreSQL có nhiều tầng bảo vệ. Hai tầng thường gặp:

1. **Quyền đối tượng:** role có được `SELECT`, `INSERT`, `UPDATE`, `DELETE` trên bảng hay không; đây là quyền do `GRANT`/`REVOKE` cấp.
2. **Row-level policy:** nếu role có quyền thực hiện lệnh, **những hàng nào** được phép tham gia lệnh và **những giá trị mới nào** được phép lưu?

Ví dụ:

```sql
GRANT SELECT, UPDATE
ON TABLE app.documents
TO app_reader_writer;
```

Câu `GRANT` không giới hạn hàng theo tenant. Nếu RLS không được bật, role có thể SELECT/UPDATE các hàng theo quyền object đã có và những ràng buộc khác. Nếu RLS được bật và policy áp dụng, phép truy cập bị giới hạn thêm theo policy.

### 2.1. Hai cửa kiểm tra

```text
Database role gửi SQL
          |
          v
Kiểm tra quyền đối tượng/schema/column
          |
          +---- Không đủ -> ERROR: permission denied
          |
          v
Kiểm tra RLS có áp dụng cho role/bảng không
          |
          +---- Bypass/disabled -> Không giới hạn hàng bằng policy RLS
          |
          v
Áp policy cho command và role liên quan
          |
          +---- USING: chọn những hàng cũ có thể đọc/sửa/xóa
          |
          +---- WITH CHECK: kiểm tra hàng mới được INSERT/UPDATE
          |
          v
Thực thi lệnh theo các quy tắc SQL/MVCC/constraint
```

Sơ đồ mang tính khái niệm: thực tế các kiểm tra và biểu thức được planner/executor tích hợp theo quy tắc riêng, không phải mọi trường hợp đều có thứ tự vật lý đơn giản như sơ đồ.

### 2.2. RLS không tạo quyền SELECT

Một policy `USING (true)` cho role không có quyền bảng **không tự cấp** `SELECT`. Role vẫn cần các quyền phù hợp và `USAGE` trên schema.

### 2.3. GRANT SELECT không làm policy biến mất

Role có `GRANT SELECT ON documents` nhưng policy chỉ cho tenant A thì SELECT chỉ trả tập hàng tenant A, trừ khi role thuộc nhóm bypass RLS.

### 2.4. RLS không thay thế column permissions

Ví dụ role được phép xem mọi hàng của tenant A nhưng không được đọc cột `secret_token`. Cần `GRANT SELECT(col1,col2)`, view/API hoặc mô hình cột tách riêng phù hợp. RLS kiểm soát **hàng**, không tự che giá trị nhạy cảm trong từng cột của hàng được phép xem.

## 3. Khi nào RLS có hiệu lực?

RLS là thuộc tính **theo từng bảng**. Policy có thể đã tồn tại nhưng nếu bảng chưa `ENABLE ROW LEVEL SECURITY`, các policy chưa có hiệu lực giới hạn hàng như mong đợi.

```sql
ALTER TABLE app.documents
ENABLE ROW LEVEL SECURITY;
```

Từ đây, các role chịu RLS sẽ bị áp chính sách khi thao tác trên bảng.

### 3.1. Bật RLS khi chưa có policy: mặc định deny

Sau khi bật RLS, nếu không có policy áp dụng cho một role/lệnh, hành vi mặc định đối với role **chịu RLS** là:

- `SELECT` không thấy các hàng được policy cho phép → thường trả **0 rows**.
- `UPDATE`/`DELETE` không có hàng mục tiêu được policy cho phép → thường ảnh hưởng **0 rows**.
- `INSERT` tạo hàng mới không vượt qua phép kiểm tra → bị **từ chối** với lỗi RLS.

Lưu ý đây **không** phải kết quả quan sát của owner/superuser mặc định bypass. Phải kiểm thử bằng role chịu RLS thật.

### 3.2. Tắt RLS

```sql
ALTER TABLE app.documents
DISABLE ROW LEVEL SECURITY;
```

Việc tắt RLS **không xóa các policy**, nhưng chúng không còn lọc các lệnh thông thường trên bảng cho đến khi bật lại. Đây là thao tác DDL nhạy cảm, chỉ dành cho quản trị có ủy quyền.

### 3.3. Bật RLS không tự biến ứng dụng thành multi-tenant an toàn

RLS chỉ tốt bằng:

- Role/tenant identity được xác lập đáng tin cậy.
- Policy được viết đúng cho từng loại lệnh.
- Schema privileges, bypass roles, views, functions và jobs được rà soát.
- Application không cho người dùng tùy ý đặt ngữ cảnh tenant của nhau.
- Có kiểm thử phủ cả đường đọc lẫn đường ghi.

## 4. Cú pháp CREATE POLICY

Mẫu cú pháp quan trọng:

```sql
CREATE POLICY policy_name ON schema.table_name
    [ AS PERMISSIVE | RESTRICTIVE ]
    [ FOR ALL | SELECT | INSERT | UPDATE | DELETE ]
    [ TO role_name [, ...] ]
    [ USING ( using_expression ) ]
    [ WITH CHECK ( check_expression ) ];
```

Các thành phần:

| Thành phần | Ý nghĩa |
| --- | --- |
| `policy_name` | Tên policy, phải phân biệt duy nhất trong phạm vi bảng. |
| `ON schema.table` | Bảng được bảo vệ. |
| `AS PERMISSIVE` | Chính sách cho phép, mặc định; nhiều policy permissive kết hợp bằng OR. |
| `AS RESTRICTIVE` | Chính sách hạn chế bổ sung; nhiều restrictive kết hợp bằng AND. |
| `FOR ALL` | Áp dụng cho nhiều loại lệnh theo ngữ nghĩa tương ứng. |
| `FOR SELECT` | Điều kiện đọc hàng bằng `USING`. |
| `FOR INSERT` | Điều kiện kiểm tra hàng mới bằng `WITH CHECK`. |
| `FOR UPDATE` | `USING` lọc hàng cũ, `WITH CHECK` kiểm tra hàng mới. |
| `FOR DELETE` | `USING` lọc hàng có thể xóa. |
| `TO roles` | Các role mà policy áp dụng; mặc định `PUBLIC`. |
| `USING` | Boolean expression được đánh giá đối với hàng hiện có. |
| `WITH CHECK` | Boolean expression kiểm tra hàng đề xuất sau INSERT/UPDATE. |

### 4.1. Những tổ hợp không phù hợp

- `FOR SELECT` chỉ cần `USING`, không khai báo `WITH CHECK`.
- `FOR DELETE` chỉ có `USING` vì DELETE không tạo hàng mới.
- `FOR INSERT` chỉ dùng `WITH CHECK`; không dùng `USING` cho policy chỉ INSERT.
- `FOR UPDATE` có thể có cả hai.
- `FOR ALL` có thể có cả `USING` và `WITH CHECK`.

### 4.2. Policy biểu thức là Boolean SQL

`USING (tenant_id = current_setting('app.tenant_id')::integer)` hoặc `WITH CHECK (owner_name = current_user)` là các biểu thức SQL. Đối với phép cho phép theo policy, kết quả phải là **TRUE**. FALSE hoặc SQL NULL/UNKNOWN không phải “cho qua”.

### 4.3. Không nên đặt mọi logic vào một policy khó đọc

Chia theo loại lệnh giúp dễ review:

```sql
CREATE POLICY docs_read ... FOR SELECT ... USING (...);
CREATE POLICY docs_create ... FOR INSERT ... WITH CHECK (...);
CREATE POLICY docs_edit ... FOR UPDATE ... USING (...) WITH CHECK (...);
CREATE POLICY docs_remove ... FOR DELETE ... USING (...);
```

Đây là cú pháp minh họa; các ví dụ đầy đủ và chạy được ở phần lab tiếp theo.

## 5. Bảng ngữ nghĩa USING và WITH CHECK

| Command | `USING` xét hàng nào? | `WITH CHECK` xét hàng nào? | Hành vi khi điều kiện không đạt |
| --- | --- | --- | --- |
| `SELECT` | Hàng hiện có được đọc. | Không áp dụng. | Hàng không xuất hiện trong kết quả. |
| `INSERT` | Không áp dụng. | Hàng mới đề xuất INSERT. | INSERT bị lỗi RLS. |
| `UPDATE` | Hàng cũ được phép là mục tiêu UPDATE. | Phiên bản hàng mới sau SET/trigger phù hợp. | Hàng cũ bị lọc; hàng mới không hợp lệ gây lỗi. |
| `DELETE` | Hàng hiện có được phép xóa. | Không áp dụng. | Hàng không được xem là mục tiêu xóa. |

Ví dụ policy theo owner:

```sql
CREATE POLICY owner_can_update ON app.documents
FOR UPDATE
USING (owner_name = current_user)
WITH CHECK (owner_name = current_user);
```

Nếu `current_user` là `team_a`:

- UPDATE hàng của `team_a`: kiểm tra `USING` đạt.
- UPDATE hàng của `team_b`: hàng không được chọn làm mục tiêu bởi policy.
- UPDATE hàng team_a rồi `SET owner_name='team_b'`: hàng mới vi phạm `WITH CHECK` nên UPDATE bị từ chối.

**Phân biệt:** `USING` không chỉ là WHERE tùy chọn do application truyền vào; nó là row-level access predicate do database quản lý.

## 6. Chuẩn bị lab: mô phỏng hai tenant bằng database roles

Để lab không dựa vào biến tenant do application tùy ý gán, ta dùng **hai database roles khác nhau**. Mỗi row có `tenant_role` đúng tên role được cấp quyền.

**Điều kiện thực hành:** chạy trong database riêng bằng tài khoản quản trị có quyền tạo role, schema, table, policy và đủ khả năng `SET ROLE` sang hai role thử nghiệm (ví dụ superuser trong môi trường lab). Không dùng superuser cho ứng dụng production; chỉ dùng nó để khởi tạo và mô phỏng.

### 6.1. Tạo hai role mô phỏng

```sql
CREATE ROLE rls_demo_alpha NOLOGIN;
CREATE ROLE rls_demo_beta NOLOGIN;
```

`NOLOGIN` nghĩa không thể đăng nhập trực tiếp bằng role này. Tài khoản quản trị sẽ `SET ROLE` để thử quyền; nếu môi trường không cho phép `SET ROLE`, DBA cần cấu hình membership phù hợp. Đừng thêm password hard-code vào tài liệu chỉ để thử.

### 6.2. Tạo schema và bảng

```sql
CREATE SCHEMA rls_demo;

CREATE TABLE rls_demo.documents (
    document_id integer PRIMARY KEY,
    tenant_role text NOT NULL,
    title text NOT NULL,
    state text NOT NULL
        CHECK (state IN ('draft','published','archived')),
    amount numeric(12,2) NOT NULL
        CHECK (amount >= 0)
);
```

Đây là bảng mẫu đơn giản để tập trung vào policy. Trong ứng dụng thực, nên có khóa tenant ổn định riêng, FK/constraints phù hợp và account/role mapping được xác thực.

### 6.3. Chèn dữ liệu ban đầu bằng owner/quản trị

```sql
INSERT INTO rls_demo.documents
    (document_id, tenant_role, title, state, amount)
VALUES
    (1, 'rls_demo_alpha', 'Alpha draft',     'draft',     100),
    (2, 'rls_demo_alpha', 'Alpha released',  'published', 250),
    (3, 'rls_demo_beta',  'Beta draft',      'draft',      90),
    (4, 'rls_demo_beta',  'Beta released',   'published', 410),
    (5, 'rls_demo_alpha', 'Alpha archive',   'archived',   30),
    (6, 'rls_demo_beta',  'Beta archive',    'archived',   20);
```

Dữ liệu gốc:

| document_id | tenant_role | state | amount |
| ---: | --- | --- | ---: |
| 1 | rls_demo_alpha | draft | 100 |
| 2 | rls_demo_alpha | published | 250 |
| 3 | rls_demo_beta | draft | 90 |
| 4 | rls_demo_beta | published | 410 |
| 5 | rls_demo_alpha | archived | 30 |
| 6 | rls_demo_beta | archived | 20 |

### 6.4. Cấp quyền đối tượng cho roles

```sql
GRANT USAGE ON SCHEMA rls_demo
TO rls_demo_alpha, rls_demo_beta;

GRANT SELECT, INSERT, UPDATE, DELETE
ON TABLE rls_demo.documents
TO rls_demo_alpha, rls_demo_beta;
```

Các `GRANT` này chỉ là điều kiện tiên quyết cho lab; **chưa bảo đảm mỗi tenant chỉ thấy hàng của mình**.

### 6.5. Bật RLS

```sql
ALTER TABLE rls_demo.documents
ENABLE ROW LEVEL SECURITY;
```

Ngay lúc này **chưa tạo policy**, nên những role chịu RLS không được đọc/ghi hàng nào, dù đã được GRANT quyền bảng.

### 6.6. Kiểm tra default-deny bằng SET ROLE

```sql
SET ROLE rls_demo_alpha;

SELECT current_user AS active_role;

SELECT document_id, title
FROM rls_demo.documents
ORDER BY document_id;

RESET ROLE;
```

Với session quản trị đủ quyền `SET ROLE`, `current_user` trong đoạn thử là `rls_demo_alpha` và SELECT trả **0 rows** vì chưa có policy. Nếu nhận lỗi permission denied to set role, đó là vấn đề quyền chuyển role của session thử; hãy nhờ quản trị setup membership phù hợp, không tắt RLS để qua bài.

### 6.7. Tại sao người tạo bảng có thể vẫn thấy sáu hàng?

Theo mặc định, **table owner bypass RLS**; superuser và `BYPASSRLS` role cũng bypass. Tài khoản quản trị vừa tạo bảng có thể SELECT tất cả sáu rows ngay cả khi RLS đã bật. Vì thế **không kiểm thử RLS chỉ bằng tài khoản tạo bảng**; test dưới role thực tế chịu policy.

## 7. Policy SELECT: lọc hàng bằng USING

Tạo một policy cho phép mỗi role đọc các tài liệu gắn đúng tên role:

```sql
CREATE POLICY documents_select_own
ON rls_demo.documents
FOR SELECT
TO rls_demo_alpha, rls_demo_beta
USING (tenant_role = current_user::text);
```

Policy này không cấp quyền bảng mới; hai role đã có `GRANT SELECT` ở phần trước.

### 7.1. SELECT dưới role alpha

```sql
SET ROLE rls_demo_alpha;

SELECT document_id, tenant_role, title, state
FROM rls_demo.documents
ORDER BY document_id;

RESET ROLE;
```

Kết quả:

| document_id | tenant_role | title | state |
| ---: | --- | --- | --- |
| 1 | rls_demo_alpha | Alpha draft | draft |
| 2 | rls_demo_alpha | Alpha released | published |
| 5 | rls_demo_alpha | Alpha archive | archived |

Không cần ghi `WHERE tenant_role = 'rls_demo_alpha'` ở SQL của người dùng để đạt giới hạn hàng này: PostgreSQL áp policy.

### 7.2. SELECT dưới role beta

```sql
SET ROLE rls_demo_beta;

SELECT document_id, tenant_role, title, state
FROM rls_demo.documents
ORDER BY document_id;

RESET ROLE;
```

Kết quả chỉ có các ID **3, 4 và 6**.

### 7.3. Hỏi đích danh hàng tenant khác

```sql
SET ROLE rls_demo_alpha;

SELECT *
FROM rls_demo.documents
WHERE document_id = 4;

RESET ROLE;
```

Đối với role alpha, ID 4 không vượt qua predicate `USING`, vì vậy query thường **trả 0 rows**, không phải lỗi “đã yêu cầu tài liệu của tenant khác”.

Điều này có thể là hành vi mong muốn để không tiết lộ dữ liệu, nhưng API cần quy ước rõ việc trả HTTP 404/403 và không làm lộ sự tồn tại của hàng ngoài phạm vi theo cách không cần thiết.

### 7.4. SELECT COUNT(*) cũng chịu RLS

```sql
SET ROLE rls_demo_alpha;

SELECT COUNT(*) AS visible_documents,
       SUM(amount) AS visible_amount
FROM rls_demo.documents;

RESET ROLE;
```

Kết quả của alpha là **3 rows**, tổng amount **380**. Beta cũng có 3 rows với tổng amount **520**. Role có RLS không được tính tổng trên hàng không nhìn thấy.

### 7.5. JOIN và aggregation vẫn cần đúng semantics

Policy trên `documents` áp khi bảng này xuất hiện trong JOIN hoặc truy vấn con theo quy tắc RLS. Nhưng RLS **không tự ngăn join multiplication**, không thay quyền trên các bảng khác và không biến aggregate sai thành đúng. Mỗi bảng chứa dữ liệu tenant cần được đánh giá độc lập.

## 8. Policy INSERT: kiểm tra hàng mới bằng WITH CHECK

Tạo policy cho phép chỉ INSERT tài liệu có `tenant_role` tương ứng role hiện hành:

```sql
CREATE POLICY documents_insert_own
ON rls_demo.documents
FOR INSERT
TO rls_demo_alpha, rls_demo_beta
WITH CHECK (tenant_role = current_user::text);
```

### 8.1. INSERT đúng tenant

```sql
BEGIN;

SET LOCAL ROLE rls_demo_alpha;

INSERT INTO rls_demo.documents
    (document_id, tenant_role, title, state, amount)
VALUES
    (11, 'rls_demo_alpha', 'Alpha new', 'draft', 60)
RETURNING document_id, tenant_role, title;

ROLLBACK;
```

Hàng mới đáp ứng `WITH CHECK`, nên INSERT hợp lệ. `ROLLBACK` hoàn tác để bộ dữ liệu lab không đổi. `SET LOCAL ROLE` có hiệu lực trong transaction này; yêu cầu session có quyền chuyển role.

### 8.2. INSERT sai tenant

```sql
-- Chạy riêng trong lab nếu muốn quan sát lỗi:
-- SET ROLE rls_demo_alpha;
-- INSERT INTO rls_demo.documents
--     (document_id, tenant_role, title, state, amount)
-- VALUES
--     (12, 'rls_demo_beta', 'Injected beta document', 'draft', 10);
-- RESET ROLE;
```

Policy kiểm tra **giá trị của hàng sắp ghi**, thấy `tenant_role != current_user::text` nên câu INSERT bị **từ chối** (thường với thông điệp kiểu `new row violates row-level security policy for table ...`).

Lưu ý: khi cố tình chạy câu lỗi trong transaction, PostgreSQL có thể đánh dấu transaction đó là aborted cho đến `ROLLBACK` hoặc xử lý bằng savepoint phù hợp. Các câu lỗi được comment để không làm gián đoạn đường thực hành chính.

### 8.3. INSERT không có USING

Một INSERT thông thường không có “hàng cũ” trên bảng đích cần lọc. Đó là lý do policy chỉ `FOR INSERT` dùng `WITH CHECK`, không dùng `USING`.

### 8.4. Default values vẫn phải qua WITH CHECK

Nếu bảng có `DEFAULT` cho `tenant_role` hoặc một trigger `BEFORE INSERT` điền tenant, **hàng cuối cùng đề xuất lưu** vẫn phải thỏa điều kiện policy phù hợp. Không coi DEFAULT/trigger là ngoại lệ của RLS.

### 8.5. INSERT ... SELECT và COPY FROM

RLS không tự bỏ qua vì dữ liệu được chèn theo lô. `INSERT ... SELECT` vẫn phải tuân theo policy INSERT trên bảng đích. Đối với `COPY FROM` vào bảng có RLS, PostgreSQL có giới hạn riêng và thường yêu cầu dùng `INSERT` thay thế khi cần áp row security; không giả định bulk load sẽ áp RLS y hệt INSERT rồi âm thầm thành công.

## 9. Policy UPDATE: USING kiểm tra hàng cũ, WITH CHECK kiểm tra hàng mới

Đây là phần dễ sai nhất khi triển khai multi-tenant.

```sql
CREATE POLICY documents_update_own
ON rls_demo.documents
FOR UPDATE
TO rls_demo_alpha, rls_demo_beta
USING (tenant_role = current_user::text)
WITH CHECK (tenant_role = current_user::text);
```

### 9.1. Sửa một hàng đúng tenant

```sql
BEGIN;

SET LOCAL ROLE rls_demo_alpha;

UPDATE rls_demo.documents
SET title = 'Alpha draft revised'
WHERE document_id = 1
RETURNING document_id, tenant_role, title;

ROLLBACK;
```

ID 1 là hàng alpha nên `USING` TRUE. Sau khi đổi `title`, `tenant_role` vẫn alpha nên `WITH CHECK` TRUE. Câu lệnh hợp lệ và trả hàng đã UPDATE.

### 9.2. Thử UPDATE hàng tenant beta

```sql
BEGIN;

SET LOCAL ROLE rls_demo_alpha;

UPDATE rls_demo.documents
SET title = 'Unauthorized edit'
WHERE document_id = 4;

ROLLBACK;
```

ID 4 thuộc beta. Policy không cho nó là hàng cũ có thể UPDATE, nên kết quả thông thường là **UPDATE 0 rows**. Việc target row tồn tại vật lý nhưng không nhìn thấy qua RLS không làm nó trở thành mục tiêu hợp lệ.

### 9.3. Thử chuyển một hàng alpha sang beta

```sql
-- Lệnh dự kiến bị từ chối nếu chạy dưới role alpha:
-- SET ROLE rls_demo_alpha;
-- UPDATE rls_demo.documents
-- SET tenant_role = 'rls_demo_beta'
-- WHERE document_id = 1;
-- RESET ROLE;
```

Ở đây:

1. Hàng cũ `document_id=1` có `tenant_role='rls_demo_alpha'` → **USING TRUE**.
2. Hàng sau UPDATE sẽ có `tenant_role='rls_demo_beta'` → **WITH CHECK FALSE**.
3. PostgreSQL từ chối hành động vì phiên bản mới của hàng không thỏa policy.

**Nếu policy chỉ kiểm tra hàng cũ, người viết code rất dễ quên ràng buộc “không được ghi ra ngoài tenant”.**

### 9.4. USING và WITH CHECK không nhất thiết giống nhau

Nghiệp vụ có thể cho phép người dùng sửa **bản nháp của mình** nhưng chỉ được chuyển trạng thái theo một quy tắc nhất định. Khi đó `USING` kiểm tra “được sửa hàng cũ hay không” và `WITH CHECK` kiểm tra “hàng mới có trạng thái hợp lệ hay không”.

Ví dụ policy giả định:

```sql
CREATE POLICY editors_update_drafts ON app.documents
FOR UPDATE
TO app_editor
USING (
    tenant_id = app.current_tenant_id()
    AND state = 'draft'
)
WITH CHECK (
    tenant_id = app.current_tenant_id()
    AND state IN ('draft', 'review')
);
```

Cú pháp trên là **mẫu thiết kế** giả định bảng, role và hàm `app.current_tenant_id()` đã được tạo an toàn. Người dùng có thể sửa draft và chuyển draft sang review, nhưng sau khi thành review không còn qua `USING (state='draft')` để tiếp tục sửa bằng policy này.

### 9.5. Thiếu WITH CHECK trong UPDATE có nghĩa gì?

Với policy `FOR UPDATE` hoặc `FOR ALL` có `USING` nhưng **không ghi riêng `WITH CHECK`**, PostgreSQL có quy tắc sử dụng biểu thức `USING` làm kiểm tra cho hàng mới. Vì vậy:

```sql
CREATE POLICY example_update ON app.documents
FOR UPDATE
USING (tenant_id = app.current_tenant_id());
```

có thể vẫn ngăn chuyển tenant nếu `tenant_id` mới không khớp. Nhưng trong security review, khai báo **cả hai** thường rõ hơn và tránh hiểu nhầm khi logic cho phép đọc/sửa khác logic cho phép ghi.

Không được suy luận “không có WITH CHECK tức là ghi bất kỳ giá trị nào” mà bỏ qua cơ chế fallback của policy.

### 9.6. SELECT policy có liên quan UPDATE

UPDATE/DELETE thường cần khả năng xác định hàng, và khi câu UPDATE đọc các cột trong `WHERE` hoặc `RETURNING`, quyền `SELECT` và SELECT-policy có thể liên quan. Trong lab, chúng ta cấp SELECT và đã có policy `FOR SELECT`, nên các câu `UPDATE ... RETURNING` có ngữ nghĩa dễ dự đoán.

Không thiết kế policy UPDATE độc lập rồi cho rằng mọi câu `UPDATE ... RETURNING *` sẽ hoạt động dù role không thể SELECT bất kỳ cột/hàng nào. Phải kiểm thử command thực tế cùng quyền cột và policy SELECT.

## 10. Policy DELETE: chọn hàng được phép xóa bằng USING

```sql
CREATE POLICY documents_delete_own
ON rls_demo.documents
FOR DELETE
TO rls_demo_alpha, rls_demo_beta
USING (tenant_role = current_user::text);
```

### 10.1. Xóa hàng của chính tenant

```sql
BEGIN;

SET LOCAL ROLE rls_demo_alpha;

DELETE FROM rls_demo.documents
WHERE document_id = 5
RETURNING document_id, title;

ROLLBACK;
```

Hàng alpha `document_id=5` được phép xóa theo `USING`, nhưng ROLLBACK giúp dữ liệu lab không thay đổi.

### 10.2. Không xóa hàng tenant khác

```sql
BEGIN;

SET LOCAL ROLE rls_demo_alpha;

DELETE FROM rls_demo.documents
WHERE document_id = 6;

ROLLBACK;
```

Hàng beta ID 6 không vượt `USING`, nên lệnh thông thường ảnh hưởng **0 rows**.

### 10.3. DELETE không có WITH CHECK

DELETE không tạo hàng mới để kiểm tra, vì vậy policy FOR DELETE chỉ có `USING`. Các yêu cầu audit/retention/foreign key vẫn là trách nhiệm riêng.

### 10.4. Không đồng nhất 0 rows với “hàng không tồn tại”

Ứng dụng gọi DELETE theo ID nhận row count = 0 có thể do:

- Hàng không tồn tại vật lý.
- Hàng tồn tại nhưng không thuộc tenant của role.
- Hàng không đạt thêm policy restrictive.
- WHERE khác không khớp.

API nên định nghĩa hành vi và logging sao cho không lộ thông tin ngoài phạm vi, đồng thời đủ khả năng điều tra sự cố bằng vai trò quản trị phù hợp.

## 11. Bốn policy đầy đủ trên bảng lab

Sau khi tạo xong, hệ thống có:

```text
rls_demo.documents
     |
     +-- SELECT documents_select_own
     |       USING (tenant_role = current_user)
     |
     +-- INSERT documents_insert_own
     |       WITH CHECK (tenant_role = current_user)
     |
     +-- UPDATE documents_update_own
     |       USING (tenant_role = current_user)
     |       WITH CHECK (tenant_role = current_user)
     |
     +-- DELETE documents_delete_own
             USING (tenant_role = current_user)
```

### 11.1. Kiểm thử theo ma trận hành động

| Thử dưới role alpha | Kỳ vọng |
| --- | --- |
| SELECT tất cả | Chỉ thấy IDs 1, 2, 5. |
| SELECT ID 4 của beta | 0 rows. |
| INSERT tenant_role alpha | Hợp lệ. |
| INSERT tenant_role beta | Lỗi WITH CHECK. |
| UPDATE title ID 1 | Hợp lệ. |
| UPDATE title ID 4 | 0 rows. |
| UPDATE ID 1 thành tenant beta | Lỗi WITH CHECK. |
| DELETE ID 5 | Hợp lệ. |
| DELETE ID 6 | 0 rows. |

### 11.2. Lợi ích của việc test bằng role thật

Nếu dùng owner hoặc superuser để thử các thao tác, chúng có thể bypass policy và cho kết quả khác hoàn toàn. Viết test role alpha và role beta riêng, nhất là khi sửa policy hoặc đổi role mapping.

### 11.3. Quy tắc của lab không phải ràng buộc dữ liệu vĩnh viễn

Một quản trị viên bypass RLS vẫn có thể INSERT row với `tenant_role` bất kỳ (nếu thỏa constraints). Nếu invariant “một tài liệu luôn có tenant hợp lệ” cần đảm bảo cho **mọi đường ghi**, phải kết hợp FK/CHECK/constraints và kiến trúc ownership, không chỉ RLS của role ứng dụng.

## 12. FORCE ROW LEVEL SECURITY cho table owner

Mặc định **table owner bypass RLS**. Nếu ứng dụng kết nối bằng chính tài khoản sở hữu bảng, việc bật RLS có thể không tạo giới hạn như bạn tưởng.

Để buộc owner cũng chịu RLS:

```sql
ALTER TABLE rls_demo.documents
FORCE ROW LEVEL SECURITY;
```

Từ đó, table owner thông thường cũng chịu policy khi chạy query trên bảng, thay vì bypass theo quyền sở hữu mặc định.

### 12.1. FORCE không khống chế superuser/BYPASSRLS

`FORCE ROW LEVEL SECURITY` không làm superuser hoặc role có quyền `BYPASSRLS` trở thành role thông thường. Hai nhóm này có khả năng bypass theo thiết kế PostgreSQL.

### 12.2. Không áp FORCE giữa đường lab nếu còn cần owner nạp dữ liệu tùy tenant

Trong lab, các câu INSERT dữ liệu mẫu trước khi có policy được chạy bởi owner/quản trị. Nếu bật FORCE cho một owner **không phải superuser** rồi policy chỉ cho `tenant_role=current_user`, owner có thể không đọc được những hàng alpha/beta khi kiểm tra. Đây là chính sách đúng theo thiết lập, không phải lỗi dữ liệu.

Nếu cần thử:

```sql
-- Chạy bởi owner hoặc quản trị có quyền:
ALTER TABLE rls_demo.documents FORCE ROW LEVEL SECURITY;

-- Sau khi quan sát, có thể khôi phục tùy mục tiêu lab:
ALTER TABLE rls_demo.documents NO FORCE ROW LEVEL SECURITY;
```

Đối với role superuser, việc chạy hai câu trên không thể hiện chính xác sự khác biệt của owner thường; muốn kiểm thử FORCE thực tế, dùng owner riêng **không có BYPASSRLS/superuser** trong lab phù hợp.

### 12.3. Thận trọng với ứng dụng dùng owner role

Best practice thường là tách:

- **DDL owner/migration role:** sở hữu bảng, chạy schema migrations.
- **Application data role:** không phải owner, không có `BYPASSRLS`; chỉ có quyền DML tối thiểu.
- **Maintenance role:** được cấp quyền cần thiết cho bảo trì theo policy vận hành riêng.

Cách này giảm rủi ro bypass mặc định, đồng thời rõ trách nhiệm hơn so với kết nối ứng dụng bằng owner hoặc superuser.

## 13. Superuser, BYPASSRLS và row_security = off

Ba khái niệm này không được trộn lẫn.

### 13.1. Superuser

Superuser PostgreSQL có khả năng bypass RLS. Vì thế không sử dụng superuser làm tài khoản truy cập dữ liệu hằng ngày của API SaaS. Nó khiến một lỗi truy vấn ở application có phạm vi tác động rất lớn.

### 13.2. Role có BYPASSRLS

Một role có thuộc tính `BYPASSRLS` có thể bỏ qua row-level security. Đây là quyền mạnh, thường chỉ dành cho tác vụ quản trị được kiểm soát.

Truy vấn catalog bởi người có quyền:

```sql
SELECT rolname, rolsuper, rolbypassrls
FROM pg_roles
WHERE rolname IN (
    'rls_demo_alpha',
    'rls_demo_beta'
)
ORDER BY rolname;
```

Trong lab, hai roles được tạo không có `SUPERUSER`/`BYPASSRLS`, nên cột `rolsuper` và `rolbypassrls` thường là FALSE.

Chỉ một người có quyền quản trị role tương ứng mới có thể cấp/đổi thuộc tính mạnh này. Không đưa `BYPASSRLS` cho role ứng dụng để giải quyết một policy khó viết.

### 13.3. row_security = off không phải công tắc bypass

PostgreSQL có cấu hình:

```sql
SHOW row_security;
```

Giá trị `off` **không cấp quyền bỏ qua RLS** cho role bình thường. Thay vào đó, nó có thể làm lệnh lỗi nếu RLS sẽ lọc dữ liệu, để phát hiện xuất/backup dữ liệu không đầy đủ.

Ví dụ chỉ thực hiện trong lab:

```sql
-- Dự kiến cần xử lý lỗi/ROLLBACK khi policy thực sự lọc hàng:
-- SET ROLE rls_demo_alpha;
-- SET row_security = off;
-- SELECT * FROM rls_demo.documents;
-- RESET row_security;
-- RESET ROLE;
```

Không dùng `SET row_security=off` để chữa lỗi ứng dụng không thấy hàng; hãy xem policy, role, object grants và mục đích truy vấn.

### 13.4. Backup và export

Một tác vụ xuất toàn bộ dữ liệu chạy với role chịu RLS có thể chỉ thấy subset; đây là rủi ro backup thiếu dữ liệu. Tác vụ backup nên có quyền và quy trình được thiết kế, kiểm chứng restore, đồng thời kiểm soát ai được dùng vai trò bypass. `row_security=off` có ích để phát hiện việc xuất dữ liệu bị filter, không phải để cấp đặc quyền.

## 14. PERMISSIVE và RESTRICTIVE: OR và AND

Nếu nhiều policy cùng áp dụng cho một lệnh/role, PostgreSQL kết hợp chúng theo loại policy:

- Các policy **PERMISSIVE** phù hợp kết hợp bằng **OR**.
- Các policy **RESTRICTIVE** phù hợp kết hợp bằng **AND**.
- Kết quả cần qua ít nhất một policy permissive cho phép **và** tất cả policy restrictive áp dụng.

Có thể hình dung:

```text
Allowed =
    (P1 OR P2 OR ... Pn)
    AND
    (R1 AND R2 AND ... Rm)
```

Trong đó `P` là permissive, `R` là restrictive. Nếu **không có policy permissive phù hợp**, restrictive policy đơn lẻ **không tự cấp quyền**.

### 14.1. Ví dụ: ẩn tài liệu archived với policy restrictive

Các policy SELECT hiện tại cho tenant alpha nhìn thấy ID 1, 2, 5. Nếu muốn **mọi SELECT của hai tenant không thấy hàng archived**, có thể bổ sung policy restrictive.

Đoạn sau được bọc transaction để thử mà không thay đổi policy gốc:

```sql
BEGIN;

CREATE POLICY documents_hide_archived
ON rls_demo.documents
AS RESTRICTIVE
FOR SELECT
TO rls_demo_alpha, rls_demo_beta
USING (state <> 'archived');

SET LOCAL ROLE rls_demo_alpha;

SELECT document_id, title, state
FROM rls_demo.documents
ORDER BY document_id;

ROLLBACK;
```

Trong transaction này, alpha chỉ thấy ID **1 và 2**. Policy permissive cho hàng tenant alpha, policy restrictive thu hẹp tiếp thành hàng không archived. `ROLLBACK` loại bỏ policy thử nghiệm, nên lab trở về trạng thái trước.

### 14.2. Hai permissive policy có thể mở rộng quyền

Giả sử một hệ thống có:

```sql
CREATE POLICY p_own ON app.documents
FOR SELECT TO app_user
USING (tenant_id = app.current_tenant_id());

CREATE POLICY p_published ON app.documents
FOR SELECT TO app_user
USING (state = 'published');
```

Hai policy permissive được OR:

```text
(tenant_id = current tenant)
OR
(state = 'published')
```

Điều này cho phép user thấy **mọi hàng published, kể cả tenant khác** nếu hai policy áp dụng. Nếu ý định là “chỉ dữ liệu tenant hiện tại và chỉ published”, phải dùng một policy `AND` hoặc kết hợp một permissive với một restrictive hợp lý.

**Đây là một nguyên nhân rò rỉ dữ liệu đa tenant thường gặp: thêm một policy PERMISSIVE tưởng là siết chặt, thực tế lại mở rộng tập hàng qua OR.**

### 14.3. Restrictive policy riêng không đủ

Nếu chỉ có:

```sql
CREATE POLICY only_restrictive ON app.documents
AS RESTRICTIVE
FOR SELECT
TO app_user
USING (state = 'published');
```

mà không có bất kỳ permissive policy nào áp dụng để cấp quyền đọc hàng, kết quả vẫn là default deny. Restrictive làm **hẹp bớt** một tập đã được permissive cho phép, chứ không thay thế phép cho phép ban đầu.

### 14.4. Restrictive cho WITH CHECK

Một restrictive policy áp dụng cho INSERT/UPDATE có thể góp thêm điều kiện AND trên hàng mới. Tuy nhiên, đừng viết một policy `FOR SELECT` rồi kỳ vọng nó tự tạo quy tắc kiểm tra hàng mới của INSERT. Phải xác định đúng command và biểu thức check tương ứng.

### 14.5. Cẩn thận policy FOR ALL

Một policy `FOR ALL` có thể áp dụng thêm cho SELECT/INSERT/UPDATE/DELETE. Nếu nó là permissive và `USING (true)`, nó có thể vô tình nới rộng chính sách SELECT/UPDATE/DELETE dù trước đó đã có policy chặt.

Đừng thêm:

```sql
-- Rất nguy hiểm nếu áp mọi lệnh cho mọi role:
-- CREATE POLICY allow_everything
-- ON rls_demo.documents
-- FOR ALL TO PUBLIC
-- USING (true) WITH CHECK (true);
```

mà không hiểu cách OR với các policy hiện có.

## 15. Policy FOR ALL và fallback của WITH CHECK

Khi không cần phân biệt từng lệnh, một policy chung có thể viết:

```sql
CREATE POLICY documents_tenant_all ON app.documents
FOR ALL
TO app_user
USING (tenant_id = app.current_tenant_id())
WITH CHECK (tenant_id = app.current_tenant_id());
```

Đây là mẫu giả định `app.current_tenant_id()` an toàn và các objects đã có. Nó áp một quy tắc nhất quán cho các lệnh được hỗ trợ.

### 15.1. Ưu điểm

Ít chính sách hơn, dễ nhận ra điều kiện cốt lõi “không được vượt khỏi tenant”.

### 15.2. Hạn chế

Tình huống thực thường khác nhau:

- Ai cũng được đọc tài liệu published của tenant mình.
- Chỉ author được sửa draft.
- Chỉ moderator được xóa document vi phạm.
- Reviewer được xem hàng trước khi phê duyệt nhưng không được tự đổi tenant.

Một `FOR ALL` quá rộng sẽ khó giữ nguyên ranh giới quyền của từng command.

### 15.3. USING được dùng làm CHECK khi không khai báo riêng

Đối với policy `FOR ALL` hoặc `FOR UPDATE`, PostgreSQL sử dụng biểu thức `USING` cho kiểm tra hàng mới nếu không khai báo `WITH CHECK` riêng.

Ví dụ:

```sql
CREATE POLICY documents_tenant_all ON app.documents
FOR ALL
USING (tenant_id = app.current_tenant_id());
```

Điều kiện tenant vẫn áp cho hàng mới của INSERT/UPDATE theo quy tắc fallback của PostgreSQL. Tuy nhiên viết tường minh cả `USING` và `WITH CHECK` giúp người review hiểu rõ sự phân biệt giữa hàng cũ và hàng mới, đặc biệt khi policy thay đổi sau này.

### 15.4. Không được coi FOR ALL thay quyền bảng

Ngay cả khi policy `FOR ALL USING(true) WITH CHECK(true)`, role không có `INSERT`/`UPDATE`/`DELETE` vẫn không được thực hiện các thao tác tương ứng. `GRANT` và policy là hai tầng riêng biệt.

## 16. TO role và PUBLIC: policy áp dụng cho ai?

Ví dụ trong lab:

```sql
TO rls_demo_alpha, rls_demo_beta
```

giới hạn policy cho hai database roles đã định nghĩa. Nếu bỏ `TO`, policy mặc định áp dụng cho `PUBLIC` (pseudo-role gồm các roles, không phải tên người dùng tùy ý).

### 16.1. PUBLIC không giống GRANT PUBLIC

Policy áp dụng `TO PUBLIC` nói **quy tắc RLS của policy được xét cho tất cả roles**. Nó không tự `GRANT SELECT ON TABLE ... TO PUBLIC`. Nếu quyền bảng không có, SELECT vẫn lỗi permission denied.

### 16.2. Membership có thể ảnh hưởng phạm vi policy

Một policy hướng đến database role có thể áp dụng qua cơ chế role membership theo ngữ nghĩa PostgreSQL. Vì vậy audit quyền không chỉ đọc dòng `TO role` mà cần xem memberships, quyền kế thừa và khả năng `SET ROLE`/thực thi dưới vai trò khác.

Không giả định một user “không có tên trong policy” chắc chắn không chịu hoặc không hưởng policy nếu user là member của một role được policy liệt kê.

### 16.3. SET ROLE thay current_user

`SET ROLE rls_demo_alpha` thay **current role** dùng để xét quyền và `current_user` trong session phù hợp; `session_user` thường vẫn là identity gốc đăng nhập.

```sql
SET ROLE rls_demo_alpha;

SELECT
    current_user AS effective_role,
    session_user AS login_identity;

RESET ROLE;
```

Với demo, policy dựa trên `current_user`. Nếu hệ thống có các wrappers dùng `SECURITY DEFINER`, `current_user` bên trong wrapper có thể khác role app do ngữ cảnh definer — cần kiểm thử, không đưa ra kết luận chung.

### 16.4. Đừng tự tạo role mới cho từng request không cần thiết

Database role per end user/tenant có thể rất hữu ích để lập ranh giới trust, nhưng có chi phí quản trị role, membership, connection pooling và provisioning. Với số tenant rất lớn, ứng dụng có thể chọn một app role cộng context bảo mật đáng tin cậy; xem phần sau về rủi ro session variable spoofing.

## 17. ALTER POLICY, DROP POLICY và quản lý vòng đời

Khi đổi rule:

```sql
ALTER POLICY documents_select_own
ON rls_demo.documents
USING (tenant_role = current_user::text);
```

Đoạn trên biểu diễn update biểu thức (giữ nguyên logic trong lab).

### 17.1. ALTER POLICY được gì?

`ALTER POLICY` có thể đổi roles `TO ...`, biểu thức `USING` và `WITH CHECK`. Nhưng không phải mọi thuộc tính đều sửa trực tiếp được bằng ALTER: muốn đổi loại command (`FOR SELECT` → `FOR UPDATE`) hoặc permissive/restrictive, thường cần **DROP + CREATE** policy thích hợp.

### 17.2. DROP POLICY

```sql
-- Chỉ ví dụ, không chạy khi đang theo lab:
-- DROP POLICY documents_select_own
-- ON rls_demo.documents;
```

Nếu xóa policy SELECT duy nhất phù hợp, role alpha/beta có thể trở lại tình trạng không nhìn thấy hàng mặc dù GRANT SELECT vẫn còn.

### 17.3. Migration policy cần tính transaction và lock

Thay đổi policy là DDL nhạy cảm; deploy vào giờ cao điểm có thể tác động query plans/locks và thay tập hàng nhìn thấy. Nên chuẩn bị migration script, kiểm thử role matrices, đo ảnh hưởng, dự trù rollback và tránh khoảng thời gian vô tình mở rộng quyền.

### 17.4. Tách policy names theo ý nghĩa

Những tên như `documents_select_own`, `documents_insert_own`, `documents_reviewers_select` dễ audit hơn `policy1`, `p2`. Tên chỉ là metadata; giá trị bảo mật nằm ở biểu thức và roles áp dụng.

## 18. Kiểm tra policies bằng pg_policies

PostgreSQL cung cấp catalog view `pg_policies`:

```sql
SELECT
    schemaname,
    tablename,
    policyname,
    permissive,
    roles,
    cmd,
    qual,
    with_check
FROM pg_policies
WHERE schemaname = 'rls_demo'
  AND tablename = 'documents'
ORDER BY policyname;
```

Với lab gốc, kết quả cho biết bốn policies, commands SELECT/INSERT/UPDATE/DELETE và biểu thức `tenant_role = current_user::text` trong cột thích hợp.

### 18.1. qual và with_check

- `qual` tương ứng điều kiện `USING` ở dạng hiển thị của PostgreSQL.
- `with_check` tương ứng biểu thức `WITH CHECK` khai báo.

Nếu `with_check` trống trong một policy có USING, đừng kết luận tất cả INSERT/UPDATE được phép ghi mọi giá trị; xem quy tắc fallback.

### 18.2. Kiểm tra bảng có bật RLS không

```sql
SELECT
    c.oid::regclass AS table_name,
    c.relrowsecurity AS rls_enabled,
    c.relforcerowsecurity AS force_owner_rls
FROM pg_class AS c
WHERE c.oid = 'rls_demo.documents'::regclass;
```

Kỳ vọng `rls_enabled=true`. `force_owner_rls` phụ thuộc phần thử FORCE đã được khôi phục hay chưa.

### 18.3. Thông tin quyền vẫn cần xem riêng

```sql
SELECT
    has_table_privilege(
        'rls_demo_alpha',
        'rls_demo.documents',
        'SELECT'
    ) AS alpha_can_select,
    has_table_privilege(
        'rls_demo_alpha',
        'rls_demo.documents',
        'UPDATE'
    ) AS alpha_can_update;
```

Hai kết quả TRUE chỉ nói quyền object. Chúng **không nói alpha thấy mọi hàng**, vì row policy vẫn lọc.

### 18.4. psql \d và phiên bản

Trong `psql`, các lệnh `\d` hoặc `\d+ schema.table` có thể hiển thị thông tin RLS/policies tùy phiên bản. Đây là **psql meta-command**, không phải SQL gửi qua JDBC; `pg_policies` và `pg_class` hữu ích hơn cho script giám sát.

## 19. INSERT, UPDATE, DELETE có cần SELECT policy không?

Trong thực tế, **quyền thao tác** và **quyền đọc dữ liệu được tham chiếu** liên quan nhau. Một `UPDATE` có thể cần SELECT permission và policy cho những cột/hàng được dùng trong `WHERE`, `SET` hoặc `RETURNING`.

Ví dụ:

```sql
UPDATE rls_demo.documents
SET amount = amount + 5
WHERE document_id = 1
RETURNING document_id, amount;
```

Để tính `amount + 5`, kiểm tra WHERE và trả RETURNING, role cần những quyền đọc cần thiết. Trong lab các roles có `SELECT` và SELECT policy tương ứng.

### 19.1. Vì sao UPDATE policy đúng vẫn có thể không đủ?

Nếu người vận hành chỉ tạo policy `FOR UPDATE` mà không có policy đọc thích hợp, những biến thể UPDATE yêu cầu SELECT có thể không đạt kỳ vọng. Kết quả tùy câu lệnh/quyền có thể là hàng không đủ điều kiện hoặc lỗi privilege/RLS.

### 19.2. FOR UPDATE row locks

Một `SELECT ... FOR UPDATE` không đơn thuần giống SELECT read-only vì nó yêu cầu khóa hàng và quyền liên quan; policy áp dụng có thể khác SELECT thường. Đừng giả định SELECT chạy được thì mọi truy vấn `FOR UPDATE` cũng chạy được nếu policy UPDATE/đặc quyền tương ứng chưa được cấp.

### 19.3. RETURNING làm thay đổi yêu cầu đọc

Với DML có `RETURNING`, PostgreSQL phải đánh giá/trao trả những cột tương ứng. Điều này có thể yêu cầu SELECT permissions và row-security checks liên quan. Hãy đưa các biến thể `INSERT/UPDATE/DELETE ... RETURNING` vào test matrix, không chỉ thử command không RETURNING.

### 19.4. Không tự bỏ SELECT để “ẩn” dữ liệu rồi vẫn muốn WHERE tùy ý

Nếu API cho phép cập nhật một ID nhưng không cho đọc nội dung, hãy thiết kế những cột được phép cập nhật và lệnh SQL cụ thể, role grants/policies tương ứng, không dựa vào một `GRANT UPDATE` tổng quát với SQL động của người dùng.

## 20. Mô hình multi-tenant dùng biến cấu hình session

Trong một SaaS có hàng nghìn tenants, có thể không muốn tạo database login riêng cho từng tenant. Một mô hình ứng dụng thường gặp:

- Application dùng một database role `app_runtime` không sở hữu bảng và không có `BYPASSRLS`.
- Trusted backend xác thực user/tenant.
- Backend đặt một tenant context cho transaction.
- Policy đọc tenant context đó.

Ví dụ **mang tính thiết kế**, không chạy trực tiếp vì những objects sau là giả định:

```sql
CREATE POLICY orders_by_tenant ON app.orders
FOR ALL
TO app_runtime
USING (
    tenant_id = nullif(
        current_setting('app.tenant_id', true),
        ''
    )::bigint
)
WITH CHECK (
    tenant_id = nullif(
        current_setting('app.tenant_id', true),
        ''
    )::bigint
);
```

### 20.1. current_setting và missing_ok

`current_setting('app.tenant_id', true)` yêu cầu giá trị một cấu hình session/transaction và trả SQL NULL nếu setting chưa được nhận diện (trong tình huống `missing_ok=true`). Với những phiên/cấu hình mà giá trị có thể là chuỗi rỗng, `nullif(...,'')` biến chuỗi rỗng thành SQL NULL trước khi cast bigint.

Khi kết quả tenant context SQL NULL, phép so sánh `tenant_id = NULL` cho UNKNOWN, không TRUE; policy theo tenant không cho những hàng đó qua.

Tuy nhiên nếu setting chứa chuỗi không phải số, phép cast `::bigint` có thể báo lỗi. Context phải được validate và thiết lập trong luồng đáng tin cậy.

### 20.2. Đặt context theo transaction

```sql
BEGIN;

SET LOCAL app.tenant_id = '42';

-- Các SQL ở đây được gửi bằng app_runtime,
-- chịu policy app.orders dựa trên tenant_id = 42.

COMMIT;
```

`SET LOCAL` chỉ có hiệu lực trong transaction; có ích với connection pool khi muốn tránh lẫn context giữa requests. Trong JDBC/framework, phải bảo đảm có transaction thật bao quanh `SET LOCAL` và toàn bộ queries cần bảo vệ.

### 20.3. Cảnh báo quan trọng: custom GUC không tự xác thực tenant

**Một custom session variable không phải ranh giới bảo mật độc lập với role SQL.** Nếu kẻ tấn công có khả năng thực thi SQL tùy ý dưới cùng `app_runtime`, họ có thể thử đặt `app.tenant_id` sang tenant khác bằng SQL.

Vì vậy mô hình dùng `current_setting` cần:

- Trusted application server xác thực tenant và đặt giá trị.
- Không cho clients truy cập trực tiếp database với quyền tùy ý `SET` custom GUC và chạy SQL tự do.
- Chống SQL injection, parameterized queries, không cho user gửi tenant context trực tiếp như một giá trị đáng tin cậy.
- Phân quyền DB tối thiểu và giám sát các đường gọi SECURITY DEFINER.
- Đánh giá threat model: nếu cần database-level isolation giữa users SQL không tin cậy, chỉ custom GUC không đủ.

Đừng gắn nhãn mô hình này là “database đã bảo mật hoàn toàn ngay cả khi attacker điều khiển app role”.

### 20.4. Connection pooling làm lộ lỗi context như thế nào?

```text
Request A (tenant 42) -----> Connection #7
    SET app.tenant_id = 42
    SELECT ...
    return connection to pool

Request B (tenant 99) -----> Connection #7
    nếu không reset context:
    SELECT ... có thể vẫn dùng tenant 42
```

Giải pháp ưu tiên là gắn tenant context với **transaction** bằng `SET LOCAL` khi app kiểm soát transaction, và bảo đảm không có query ngoài transaction sử dụng nhầm giá trị. Với session-level `SET`, phải có cơ chế reset đáng tin cậy ở pool.

### 20.5. Transaction pooling

Nếu dùng PgBouncer transaction pooling hoặc cơ chế tương tự, các session settings kéo dài không được giả định sẽ gắn với một request qua nhiều transactions. Thiết kế nên dùng context được đặt lại trong từng transaction, đúng hợp đồng pool, và test với cấu hình thực.

### 20.6. current_user và tenant context là hai mô hình khác nhau

Lab chính dựa `tenant_role = current_user::text`, khá rõ ràng khi mỗi tenant có database role riêng. Mô hình GUC dựa trên tenant ID do backend đặt trong một shared role. Cả hai có ưu/nhược về trust, scale, role management và pooling; không trộn hai mô hình mà chưa xác định ai có quyền đặt tenant.

## 21. SECURITY DEFINER: đường bypass dễ bị quên

PostgreSQL hỗ trợ functions có thuộc tính `SECURITY DEFINER`: code bên trong function được thực thi với **quyền của chủ sở hữu function**, không đơn thuần bằng caller. Nếu function owner cũng là table owner được phép bypass RLS, function có thể trả nhiều dữ liệu hơn caller tự SELECT.

### 21.1. Ví dụ minh họa sự khác biệt

Đoạn sau chỉ chạy trong lab nếu bạn muốn thấy rủi ro; dùng transaction để hoàn tác function tạm:

```sql
BEGIN;

CREATE FUNCTION rls_demo.count_all_documents()
RETURNS bigint
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, rls_demo, pg_temp
AS $$
    SELECT COUNT(*) FROM rls_demo.documents;
$$;

REVOKE ALL
ON FUNCTION rls_demo.count_all_documents()
FROM PUBLIC;

GRANT EXECUTE
ON FUNCTION rls_demo.count_all_documents()
TO rls_demo_alpha;

SET LOCAL ROLE rls_demo_alpha;

SELECT COUNT(*) AS own_visible_count
FROM rls_demo.documents;

SELECT rls_demo.count_all_documents()
    AS definer_function_count;

ROLLBACK;
```

Nếu function được tạo bởi **superuser/owner có bypass** và lab có sáu rows nguyên trạng:

- `own_visible_count` = **3**.
- `definer_function_count` có thể = **6** vì function thực thi dưới ngữ cảnh definer có thể bypass policy.

Ví dụ cố tình phơi bày rủi ro, **không phải mẫu code nên triển khai trong production**.

### 21.2. FORCE và definer

`FORCE ROW LEVEL SECURITY` có thể khiến **table owner thông thường** cũng chịu RLS, nhưng superuser và BYPASSRLS vẫn là ngoại lệ. Vì thế không dùng FORCE rồi mặc định mọi SECURITY DEFINER function an toàn.

### 21.3. Ràng buộc search_path

Function `SECURITY DEFINER` cần được thiết kế chống tấn công qua object name resolution/search_path. Một thực hành quan trọng là schema-qualify objects và đặt `search_path` rõ ràng, đặt `pg_temp` ở vị trí an toàn. Không để object name resolution phụ thuộc một schema user không tin cậy có thể tạo objects.

### 21.4. Quyền EXECUTE trên function

Mặc định của PostgreSQL có thể cấp `EXECUTE` trên function mới cho `PUBLIC` nếu không thay đổi default privileges. Với function nhạy cảm, `REVOKE ALL FROM PUBLIC` và chỉ GRANT role cần thiết, lý tưởng trong cùng transaction tạo function để tránh cửa sổ quyền ngoài ý muốn.

### 21.5. Khi SECURITY DEFINER hợp lý

Có trường hợp cần function quản trị được kiểm tra để thực hiện nghiệp vụ cross-tenant (báo cáo tổng hợp, migration, maintenance). Nhưng phải xác định:

- Caller nào có EXECUTE.
- Function trả dữ liệu gì và có lọc scope ở bên trong không.
- Owner function có quyền bypass nào.
- Tính an toàn của search_path và input validation.
- Logging/audit và test negative cases.

Không dùng SECURITY DEFINER chỉ để “chữa” lỗi RLS mà không đánh giá ranh giới tin cậy.

## 22. VIEW có thể làm RLS áp dụng theo quyền khác

Trong PostgreSQL, view truyền thống thường kiểm tra quyền quan hệ nền theo ngữ cảnh **view owner** (một số chi tiết phụ thuộc cấu hình và major). Nếu owner có khả năng bypass RLS, người gọi SELECT view có thể nhận kết quả khác khi SELECT trực tiếp bảng.

### 22.1. Rủi ro view do owner/bypass tạo

```sql
-- Mẫu minh họa cần đánh giá quyền:
-- CREATE VIEW rls_demo.all_documents_v AS
-- SELECT * FROM rls_demo.documents;
-- GRANT SELECT ON rls_demo.all_documents_v TO rls_demo_alpha;
```

Nếu view dùng quyền/security context của owner và owner bypass policy, gọi view có thể làm lộ các rows ngoài tenant. Đừng coi “bảng nền có RLS” là bằng chứng mọi view trên bảng đều tự an toàn.

### 22.2. security_invoker view (PostgreSQL 15+)

Từ PostgreSQL 15, view có tùy chọn `security_invoker=true` để quyền và RLS trên các quan hệ nền được xét theo người gọi trong các điều kiện được mô tả.

Ví dụ lab:

```sql
CREATE VIEW rls_demo.documents_invoker_v
WITH (security_invoker = true)
AS
SELECT
    document_id, tenant_role, title, state, amount
FROM rls_demo.documents;

GRANT SELECT
ON rls_demo.documents_invoker_v
TO rls_demo_alpha, rls_demo_beta;
```

Thử:

```sql
SET ROLE rls_demo_alpha;

SELECT document_id, tenant_role, title
FROM rls_demo.documents_invoker_v
ORDER BY document_id;

RESET ROLE;
```

Trên PostgreSQL 15+ và bộ quyền lab, alpha thấy các IDs **1, 2, 5** vì view dùng caller context phù hợp. User gọi vẫn phải có quyền cần thiết trên bảng nền theo ngữ nghĩa security invoker; lab đã cấp các quyền ấy.

### 22.3. security_barrier không giống security_invoker

`security_barrier` là tùy chọn view liên quan thứ tự/khả năng tối ưu biểu thức lọc để hạn chế rò rỉ qua những function không an toàn. Nó **không đồng nghĩa** “mọi view chạy bằng quyền người gọi” và không thay `security_invoker=true`.

### 22.4. Cẩn thận PostgreSQL major

`security_invoker` ở view không được hỗ trợ cùng cú pháp trong mọi phiên bản PostgreSQL cũ. Kiểm tra:

```sql
SHOW server_version;
```

Trên môi trường chưa hỗ trợ, cần chọn thiết kế view/function/role khác phù hợp và kiểm chứng quyền RLS, không copy câu SQL rồi cho rằng luôn chạy được.

## 23. Các lệnh và cơ chế không bị bảo vệ như SELECT thông thường

RLS được thiết kế để lọc hàng cho những lệnh `SELECT`, `INSERT`, `UPDATE`, `DELETE` trong phạm vi hỗ trợ. Nó **không phải cơ chế áp cho mọi thao tác với table**.

### 23.1. TRUNCATE không có lọc theo policy

`TRUNCATE` không xóa “chỉ những hàng nhìn thấy qua RLS”. Đây là thao tác relation-level; PostgreSQL không áp row security như `DELETE`.

Vì vậy chỉ cấp quyền `TRUNCATE` cho vai trò quản trị được phép, không dùng `TRUNCATE` như lối tắt xóa tài liệu của một tenant.

### 23.2. REFERENCES và khóa ngoại

Các kiểm tra referential integrity (FK), uniqueness và constraints nhất định **không được lọc bởi RLS** theo cách một SELECT của user bị lọc, để giữ tính toàn vẹn dữ liệu. Điều đó tạo ra cơ hội rò rỉ gián tiếp qua thông báo lỗi/khác biệt hành vi.

### 23.3. COPY TO và COPY FROM

`COPY TO` có thể được dùng để xuất kết quả SELECT theo phạm vi quyền và row security phù hợp. `COPY FROM` trên bảng có RLS có hạn chế riêng và không nên được coi là tương đương bulk INSERT có policy tự động cho mọi tình huống.

Khi cần nạp dữ liệu cho application role chịu RLS, ưu tiên cơ chế `INSERT` được kiểm thử; batch/COPY phải xem đúng tài liệu major và quyền.

### 23.4. DDL và quyền chủ sở hữu

Role có quyền thay cấu trúc bảng/policy có thể thay đổi điều kiện RLS. Ranh giới bảo mật giữa tenants thường đòi ứng dụng **không sở hữu** bảng và không có quyền DDL nguy hiểm.

### 23.5. GRANT đặc biệt ngoài ý muốn

Đừng cấp `TRUNCATE`, `REFERENCES`, `BYPASSRLS` hoặc role memberships rộng một cách tùy tiện chỉ vì SELECT/UPDATE policy đang đúng.

## 24. Rò rỉ thông tin qua UNIQUE và FOREIGN KEY

Giả sử bảng:

```sql
CREATE TABLE app.users (
    user_id bigint PRIMARY KEY,
    tenant_id bigint NOT NULL,
    email text NOT NULL UNIQUE
);
```

RLS có thể chỉ cho user của tenant 42 nhìn những rows thuộc tenant 42. Nhưng nếu tenant 99 đã dùng email `a@example.com`, một INSERT từ tenant 42 với cùng email có thể báo lỗi `duplicate key` vì UNIQUE constraint được kiểm tra trên tập dữ liệu vật lý liên quan, không chỉ những rows tenant 42 nhìn thấy.

### 24.1. Đây là một side channel

Thông báo lỗi có thể tiết lộ “có một giá trị email trùng ở tenant khác”, dù RLS không cho SELECT hàng đó. Constraint vẫn phải đảm bảo tính duy nhất theo định nghĩa của nó.

### 24.2. Unique key theo tenant khi nghiệp vụ cho phép

Nếu email chỉ cần duy nhất **trong một tenant**:

```sql
CREATE TABLE app.users (
    user_id bigint PRIMARY KEY,
    tenant_id bigint NOT NULL,
    email text NOT NULL,
    UNIQUE (tenant_id, email)
);
```

Khi đó hai tenants có thể dùng cùng email mà không conflict. Nếu business bắt buộc email global unique, không được đổi sang per-tenant uniqueness chỉ để tránh error; thay vào đó chuẩn hóa thông báo lỗi/luồng đăng ký và đánh giá leakage.

### 24.3. FK cũng có thể là side channel

Một INSERT tham chiếu `parent_id` có thể thành công/thất bại tùy parent row tồn tại, dù parent không hiển thị cho caller qua RLS. Cần định nghĩa khả năng đoán IDs, authorization và cách xử lý lỗi một cách cẩn thận.

### 24.4. RLS không thể ngăn mọi kênh quan sát

Thời gian thực thi, khóa cạnh tranh, lỗi constraint, trigger/exception details và object privilege cũng có thể tạo tín hiệu ngoài dữ liệu hàng SELECT. RLS rất có ích, nhưng không thay threat modeling của toàn hệ thống.

## 25. Policy tham chiếu bảng khác và quyền phụ

Một policy có thể kiểm tra quan hệ membership:

```sql
CREATE POLICY projects_read ON app.projects
FOR SELECT
USING (
    EXISTS (
        SELECT 1
        FROM app.project_members AS m
        WHERE m.project_id = projects.project_id
          AND m.user_id = app.current_user_id()
    )
);
```

Đoạn SQL này là mẫu khái niệm; các objects `app.projects`, `app.project_members` và `app.current_user_id()` không được tạo trong lab.

### 25.1. Quyền trên bảng tham chiếu

Policy chạy trong ngữ cảnh quyền phù hợp của query. Nếu biểu thức policy đọc `app.project_members` mà role không có quyền SELECT cần thiết, query có thể **báo permission denied** dù chính bảng `app.projects` đã GRANT SELECT.

Giải pháp là thiết kế quyền tối thiểu cho bảng phụ hoặc một function bảo mật được review kỹ — không phải GRANT SELECT toàn bảng membership cho tất cả nếu nó chứa dữ liệu nhạy cảm.

### 25.2. Có thể xuất hiện vòng phụ thuộc policy

Nếu policy của A đọc B và policy của B lại đọc A, hoặc policy tham chiếu chính bảng đang được bảo vệ theo cách dẫn đến recursion, PostgreSQL có thể báo lỗi policy recursion hoặc query quá phức tạp. Thiết kế identity/membership schema sao cho đường kiểm tra quyền có thể đánh giá an toàn và hữu hạn.

### 25.3. Subquery policy và race condition

Khi policy dựa vào bảng trạng thái quyền thay đổi đồng thời với hàng đích, phải xem xét snapshot và tính nhất quán. Có những tình huống điều kiện membership được đọc tại một snapshot không đồng bộ với row target sau các thay đổi cạnh tranh. Tùy yêu cầu bảo mật, có thể cần khóa phù hợp, cập nhật đồng bộ, hoặc thiết kế bảng quyền với consistency rõ.

### 25.4. Chi phí JOIN trong policy

Một `EXISTS(...)` trong policy có thể ảnh hưởng chi phí trên hàng triệu rows. Tạo index phù hợp cho `(project_id,user_id)`, kiểm tra `EXPLAIN` và hạn chế UDF nặng trong policy. Không đánh đổi bảo mật lấy hiệu năng bằng cách bỏ policy.

## 26. Thứ tự xử lý biểu thức policy, triggers và SQL NULL

Policy không đơn giản là một lệnh IF của application. PostgreSQL tích hợp nó vào execution semantics.

### 26.1. USING trong đọc hàng

`USING` là một biểu thức SQL được áp trên những hàng liên quan. PostgreSQL có những quy tắc bảo mật về thứ tự đánh giá policy và biểu thức người dùng, trong đó các operator/function được đánh dấu **LEAKPROOF** có thể có những khả năng di chuyển trong kế hoạch đặc biệt.

Không xây security model dựa trên thứ tự đánh giá biểu thức như Java `if (a) { b }`. Một policy chỉ an toàn nếu chính biểu thức predicate của nó cho phép đúng tập hàng, không phải vì dự kiến `WHERE` của application sẽ chạy trước hay sau.

### 26.2. SQL NULL không phải TRUE

Giả sử:

```sql
USING (tenant_role = current_user::text)
```

và `tenant_role` là SQL NULL, phép so sánh là UNKNOWN. Đối với policy, một hàng chỉ được phép qua khi điều kiện TRUE. Trong lab `tenant_role` là `NOT NULL` để tránh ý nghĩa không rõ.

### 26.3. BEFORE ROW trigger và WITH CHECK

Với INSERT/UPDATE, PostgreSQL xét policy `WITH CHECK` đối với phiên bản hàng được đề xuất sau khi các thao tác `BEFORE ROW` trigger thích hợp đã tác động. Vì vậy trigger có thể làm thay đổi giá trị mà policy kiểm tra.

Ví dụ một BEFORE INSERT trigger có thể điền `tenant_role` nếu giá trị bị thiếu, rồi hàng cuối cùng phải vượt `WITH CHECK`. Ngược lại, một trigger có thể đổi tenant_role sai và gây lỗi policy.

**Không dùng trigger để giả định có thể vượt policy**, và không đặt tenant trực tiếp từ input không tin cậy nếu có thể lấy từ role/context đã xác thực.

### 26.4. AFTER trigger và tác dụng phụ

Một AFTER trigger dùng function với quyền cao có thể thực hiện SQL khác. Quyền function, owner và các bảng phụ phải được đánh giá riêng; RLS trên bảng đích ban đầu không bảo vệ mọi side effect do trigger tạo ra.

### 26.5. RLS không tự validate giá trị nghiệp vụ

Policy `WITH CHECK (tenant_role=current_user)` không kiểm tra:

- `amount` có nằm trong hạn mức kinh doanh không.
- `state` có được chuyển từ draft sang published theo workflow không.
- `title` có chứa nội dung nguy hiểm không.
- User có quyền sửa trường amount hay không.

Cần `CHECK`, FK, column grants, business validation, triggers hoặc application policy tương ứng.

## 27. Giới hạn UPDATE theo trạng thái bằng USING và WITH CHECK

Giả sử user chỉ được sửa tài liệu `draft` và sau sửa chỉ được để `draft` hoặc chuyển `review`.

### 27.1. Policy chuyên biệt

```sql
CREATE POLICY drafts_editor_update
ON app.documents
FOR UPDATE
TO app_editor
USING (
    tenant_id = app.current_tenant_id()
    AND state = 'draft'
)
WITH CHECK (
    tenant_id = app.current_tenant_id()
    AND state IN ('draft','review')
);
```

Đây là mẫu giả định, không chạy trong lab vì `app.documents`/`app_editor` chưa có.

### 27.2. Chuyển trạng thái được phép

Hàng cũ là `draft`, tenant đúng → USING TRUE. Hàng mới là `review`, tenant đúng → WITH CHECK TRUE. UPDATE được phép theo policy đó, nếu các quyền và policy khác cũng cho phép.

### 27.3. Sửa lại review có thể bị từ chối

Hàng cũ đã `review` thì USING FALSE, nên policy không cho nó là target UPDATE. Đây là cách hạn chế luồng dữ liệu thông qua **hàng cũ và hàng mới**.

### 27.4. Khi có thêm permissive policy

Nếu ai đó bổ sung một policy `FOR UPDATE AS PERMISSIVE USING(true) WITH CHECK(true)` cũng áp role này, phép OR có thể nới rộng cả điều kiện cũ/mới. Muốn một ràng buộc phải luôn đúng cho mọi đường update của role, cân nhắc restrictive policy hoặc thiết kế policies phân tách quyền chặt chẽ.

### 27.5. RLS không thay thế state machine phức tạp

Những quy tắc “chỉ reviewer đã ký mới được chuyển review→approved”, “không sửa khi invoice đã chốt” cần mô hình quyền, trạng thái và transaction rõ. Có thể dùng RLS như một tầng bảo vệ, nhưng không nên đặt toàn bộ workflow vào một biểu thức không thể kiểm thử.

## 28. ON CONFLICT và MERGE khi bảng có RLS

Các lệnh DML nhiều nhánh cần được kiểm tra theo **đường thao tác thực sự chạy**.

### 28.1. INSERT ... ON CONFLICT DO UPDATE

```sql
INSERT INTO app.documents AS d (
    document_id, tenant_id, title
)
VALUES (123, app.current_tenant_id(), 'New title')
ON CONFLICT (document_id)
DO UPDATE SET title = EXCLUDED.title;
```

Mẫu này có thể đi qua logic INSERT hoặc UPDATE tùy dữ liệu đã tồn tại. Policy INSERT `WITH CHECK` và policy UPDATE `USING`/`WITH CHECK` (cùng các quyền đọc liên quan) đều đáng xem xét, không chỉ policy INSERT.

### 28.2. Conflict với hàng tenant khác

Nếu primary key là toàn cục và hàng `document_id=123` thuộc tenant khác, UNIQUE conflict vẫn có thể được phát hiện dù hàng ấy không hiện qua SELECT của tenant hiện tại. Không dùng `ON CONFLICT` để dò ID của người khác hoặc tự động cập nhật hàng đó.

### 28.3. DO NOTHING không đồng nghĩa không có side channel

Nếu user cố INSERT một key trùng hàng không nhìn thấy, câu `ON CONFLICT DO NOTHING` có thể dẫn đến row count khác với key không trùng; constraint behavior có thể lộ tín hiệu tồn tại. Cần thiết kế khóa, lỗi và API phù hợp với threat model.

### 28.4. MERGE

`MERGE` được hỗ trợ từ PostgreSQL 15, kết hợp các nhánh matched/not matched. Nếu dùng trên bảng có RLS, phải kiểm tra policy/quyền cho từng hành động thực hiện theo tài liệu của major. Không giả định rằng một policy SELECT đủ cho mọi nhánh UPDATE/INSERT/DELETE hoặc MERGE có cùng concurrency semantics với ON CONFLICT.

### 28.5. Không viết một SQL quá rộng thay cho authorization

Một UPSERT có thể cập nhật những trường mà client không được phép sửa nếu application blindly truyền `EXCLUDED.column`. RLS theo hàng chỉ ngăn vượt scope, còn quyền cột và validation logic vẫn cần cho từng trường.

## 29. Indexing cho policy theo tenant

RLS có thể khiến mỗi câu query mang thêm predicate tenant. Khi bảng lớn, index phù hợp giúp giảm chi phí lọc:

```sql
CREATE INDEX idx_rls_demo_tenant_state
ON rls_demo.documents (tenant_role, state);
```

### 29.1. Khi nào index có ích?

Nếu bảng có hàng triệu rows của hàng nghìn tenants, query:

```sql
SELECT document_id, title
FROM rls_demo.documents
WHERE state = 'published';
```

chạy dưới role chịu RLS sẽ được áp thêm policy tenant, nên index có tiền tố `tenant_role` và `state` có thể hữu ích tùy số liệu/statistics.

### 29.2. Lab nhỏ có thể chọn Seq Scan

Với sáu rows, planner hoàn toàn có thể chọn Seq Scan. Điều đó không chứng minh RLS sai hoặc index không sử dụng được trong workload lớn.

### 29.3. EXPLAIN dưới role thực

```sql
SET ROLE rls_demo_alpha;

EXPLAIN (ANALYZE, BUFFERS)
SELECT document_id, title
FROM rls_demo.documents
WHERE state = 'published';

RESET ROLE;
```

Kế hoạch có thể phản ánh thêm điều kiện lọc theo tenant, nhưng planner có quyền tổ chức điều kiện và access path theo cách không nhất thiết in một dòng filter riêng đúng như policy SQL viết ban đầu.

`EXPLAIN (ANALYZE)` với SELECT thực thi query; nếu dữ liệu thật nhạy cảm, không phát plan/query text công khai vì chúng có thể chứa biểu thức, tên đối tượng và giá trị parameter.

### 29.4. Function trong policy có thể tốn chi phí

Nếu policy gọi function phức tạp cho mỗi hàng hoặc tham chiếu bảng membership thiếu index, latency có thể tăng mạnh. Không gắn nhãn `IMMUTABLE` sai cho function đọc session context hay bảng quyền chỉ để planner cache kết quả; điều đó có thể khiến security decision bị stale.

### 29.5. Tối ưu không được làm yếu phạm vi bảo mật

Giải pháp là index, query design, stable/volatile declarations đúng và cấu trúc bảng quyền có hiệu quả. Không đổi `tenant_id = current_tenant` thành `true` chỉ để giảm thời gian query.

## 30. RLS và partitioning

Với một bảng phân vùng theo tenant/date, policy cần được đánh giá theo cách người dùng **truy cập bảng cha hay bảng con**.

### 30.1. Query qua partitioned parent

Khi query đi qua parent partitioned table, row-security policy của parent được áp theo ngữ nghĩa truy cập qua parent. Planner có thể prune partitions nếu điều kiện cho phép.

### 30.2. Truy cập trực tiếp partition child

Nếu role được cấp quyền truy cập **trực tiếp** một partition như một bảng độc lập, phải kiểm tra chính sách của đường truy cập đó; không suy luận rằng mọi policy của parent tự bảo vệ mọi quyền SELECT trực tiếp trên child trong mọi major/cấu hình.

### 30.3. Đề xuất vận hành

Thông thường ứng dụng nên truy cập qua API/parent được thiết kế, hạn chế grants trực tiếp vào partitions khi không cần, và có negative tests cho cả đường parent lẫn các child tables mà role có thể truy cập.

### 30.4. Partition không thay RLS

Partition pruning là tối ưu truy vấn/định tuyến dữ liệu; nó không tự xác thực tenant. Một partition theo tenant mà app role được quyền SELECT trực tiếp mọi partition vẫn có thể lộ dữ liệu nếu không có thiết kế quyền/RLS đúng.

## 31. RLS và các role quản trị, background jobs

Trong hệ thống thật có nhiều loại workload:

| Role | Phạm vi điển hình |
| --- | --- |
| Application tenant role | Chỉ DML trên hàng tenant được phép. |
| Report reader | Chỉ đọc cột/hàng cần cho báo cáo. |
| Migration owner | Thực hiện DDL; được kiểm soát tách khỏi API. |
| Maintenance job | Vacuum/refresh/cleanup theo quyền quản trị phù hợp. |
| Cross-tenant analytics | Truy cập toàn hệ thống có mục đích rõ, logging và bảo vệ riêng. |

### 31.1. Cross-tenant báo cáo là một nhu cầu riêng

Đừng cấp `BYPASSRLS` cho ứng dụng người dùng chỉ vì đội analytics cần tính tổng toàn hệ thống. Nên có role/job được kiểm soát để xuất dữ liệu cần thiết vào nơi đã quản lý quyền, hoặc interface chuyên biệt có scope rõ.

### 31.2. Jobs thay trạng thái nhiều tenant

Một job “đóng mọi đơn quá hạn” nếu chạy dưới tenant-limited role sẽ chỉ tác động các hàng được phép nhìn thấy/sửa. Nếu ý định là nhiều tenants, phải dùng đường vận hành được ủy quyền, không âm thầm chuyển sang superuser mà không audit.

### 31.3. Chủ sở hữu đối tượng và migration

Khi tạo table/view mới, migration cần kiểm soát:

- Bảng có bật RLS sau tạo không?
- Default grants có cấp quyền quá rộng không?
- Policy đã được tạo trước khi ứng dụng nhận traffic chưa?
- View/functions do ai sở hữu?
- Owner có FORCE hay bypass theo mặc định?

Một bảng tenant mới không bật RLS có thể là khoảng hở dù các bảng cũ đã được bảo vệ đúng.

## 32. Hướng dẫn kiểm thử RLS theo vai trò

Kiểm thử bảo mật cần cả **positive tests** (được phép) và **negative tests** (bị từ chối/không thấy hàng).

### 32.1. Kiểm tra SELECT

- Alpha SELECT không WHERE → chỉ IDs 1, 2, 5.
- Beta SELECT không WHERE → chỉ IDs 3, 4, 6.
- Alpha SELECT ID 4 → 0 rows.
- Beta SELECT ID 1 → 0 rows.
- COUNT/SUM dưới từng role chỉ thấy tập của mình.

### 32.2. Kiểm tra INSERT

- Alpha INSERT hàng alpha → được phép.
- Alpha INSERT hàng beta → lỗi WITH CHECK.
- Alpha INSERT tenant_role SQL NULL → bị ràng buộc NOT NULL từ chối.
- INSERT hàng có giá trị state/amount sai → CHECK constraints từ chối.
- INSERT ... RETURNING và INSERT ... ON CONFLICT → kiểm thử đường đọc/ghi liên quan.

### 32.3. Kiểm tra UPDATE

- Alpha sửa title ID 1 → được phép.
- Alpha sửa ID 4 → thường UPDATE 0 rows.
- Alpha đổi tenant_role của ID 1 thành beta → lỗi WITH CHECK.
- Alpha đổi state hợp lệ theo constraint nhưng bị một policy state chuyên biệt cấm → bị giới hạn theo policy.
- UPDATE ... RETURNING → đủ SELECT permissions/policy cần thiết.

### 32.4. Kiểm tra DELETE

- Alpha DELETE ID 5 → được phép.
- Alpha DELETE ID 6 → thường DELETE 0 rows.
- Quy tắc retention/soft delete nếu có vẫn phải xác minh độc lập.

### 32.5. Kiểm tra bypass và đường gián tiếp

- Test owner bình thường trước/sau FORCE.
- Test role `BYPASSRLS` chỉ trong lab quản trị có kiểm soát.
- Test SELECT qua default view và security_invoker view.
- Test SECURITY DEFINER functions có thể trả dữ liệu ngoài tenant không.
- Test direct partition access nếu có quyền.
- Test custom GUC tenant và connection pooling giữa hai requests.

### 32.6. Test phải dùng quyền giống production

Một test suite chỉ chạy dưới superuser hoặc table owner không có FORCE sẽ có nguy cơ **cho kết quả xanh giả** vì bypass policy. Dùng role ứng dụng thực hoặc role test với cấu hình quyền tương đương; kiểm tra cả membership.

## 33. Xử lý lỗi RLS thường gặp

### 33.1. SELECT luôn trả 0 rows

Nguyên nhân có thể:

- Bảng đã ENABLE RLS nhưng không có permissive policy áp role/lệnh.
- Policy `TO role` không áp role hiện tại.
- `USING` trả FALSE/UNKNOWN, ví dụ tenant context chưa được đặt.
- Đang dùng `current_user` khác dự kiến do `SET ROLE` hoặc SECURITY DEFINER.
- Một policy RESTRICTIVE loại hết hàng.
- WHERE của query tự loại rows.

Khắc phục: kiểm tra `current_user`/`session_user`, `pg_policies`, cấu hình tenant và thử query bằng đúng role; không tắt RLS để tạo kết quả.

### 33.2. Permission denied

Role có thể thiếu:

- `USAGE` trên schema.
- `SELECT`/`INSERT`/`UPDATE`/`DELETE` phù hợp trên bảng/cột.
- Quyền SELECT trên bảng phụ mà policy tham chiếu.
- Quyền EXECUTE function do policy gọi.

Policy không thay GRANT, nên xác nhận object permissions trước.

### 33.3. new row violates row-level security policy

Thường xảy ra khi một INSERT/UPDATE tạo hàng không thỏa `WITH CHECK` tương ứng. Cần xem:

- Tenant của hàng mới có khớp role/context đã xác thực?
- BEFORE trigger có sửa tenant/state không?
- Có policy restrictive thêm điều kiện?
- Có policy FOR ALL/INSERT/UPDATE áp dụng bất ngờ?

Không tự bỏ `WITH CHECK` để cho dữ liệu qua nếu ràng buộc ấy phản ánh invariant bảo mật.

### 33.4. UPDATE 0 rows dù ID chắc chắn có thật

Có thể vì policy USING không cho hàng cũ làm mục tiêu. Kiểm tra bằng role admin được phép và logs/audit an toàn; tránh hiển thị chi tiết existence của hàng tenant khác cho caller.

### 33.5. Policy bảo vệ bảng, view lại thấy nhiều rows

Kiểm tra owner/security context của view. Với PostgreSQL 15+, đánh giá `security_invoker=true`; với major cũ chọn thiết kế khác. Kiểm thử cả view được cấp cho app role.

### 33.6. Query lỗi sau khi bổ sung policy EXISTS

Policy có thể đọc bảng membership/function mà caller thiếu quyền, hoặc tạo vòng đệ quy policy. Kiểm tra dependency permissions, thiết kế index và tránh reference cycle.

### 33.7. Backup thiếu hàng

Role backup có thể chịu RLS nên export thiếu rows. Cần backup role và chính sách quản trị rõ, phát hiện filtering bằng configuration/quy trình và xác minh restore; không coi `row_security=off` là quyền bypass.

### 33.8. Lúc được lúc không trong connection pool

Custom tenant GUC bị giữ giữa requests, SET LOCAL không nằm trong transaction như mong đợi, hoặc queries chạy trên connections khác nhau. Phải bảo đảm transaction-bound context và integration tests với pool thật.

### 33.9. CREATE POLICY rồi vẫn lộ tất cả rows

Có thể bảng chưa ENABLE RLS, role là table owner/superuser/BYPASSRLS, hoặc một policy permissive khác với `USING(true)` đã mở rộng phạm vi qua OR.

### 33.10. RLS chậm sau deploy

Policy có thể thêm predicate không có index, function phức tạp hoặc subquery membership thiếu statistics. Dùng EXPLAIN/ANALYZE dưới role thực, đo query plan và tối ưu mà không vô hiệu hóa isolation.

## 34. Bảng quyết định khi thiết kế policy

| Câu hỏi bảo mật | Công cụ cần xem xét | Điểm dễ nhầm |
| --- | --- | --- |
| Role có được SELECT trên bảng không? | `GRANT SELECT`. | RLS không tự cấp quyền. |
| Role được SELECT những hàng nào? | `FOR SELECT ... USING`. | SELECT policy không giới hạn INSERT mặc định. |
| Role được INSERT loại hàng nào? | `FOR INSERT ... WITH CHECK`. | INSERT sai policy thường lỗi, không âm thầm skip. |
| Role được UPDATE hàng cũ nào? | `FOR UPDATE ... USING`. | Hàng tenant khác thường UPDATE 0 rows. |
| Hàng mới sau UPDATE phải có giá trị gì? | `FOR UPDATE ... WITH CHECK`. | Chỉ kiểm tra hàng cũ không diễn đạt đủ ý định ghi. |
| Role được DELETE hàng nào? | `FOR DELETE ... USING`. | DELETE không có WITH CHECK. |
| Cần ràng buộc thêm cho mọi policy phù hợp? | `AS RESTRICTIVE`. | Restrictive không tự grant khi thiếu permissive. |
| Hai cách được cấp đọc độc lập? | Nhiều policy PERMISSIVE. | OR có thể mở rộng sang tenant khác. |
| Owner có phải chịu RLS? | `FORCE ROW LEVEL SECURITY`. | Không khống chế superuser/BYPASSRLS. |
| View đọc dữ liệu theo caller? | `security_invoker=true`, PG15+. | View mặc định có thể dùng owner context. |
| Function có vượt quyền caller? | `SECURITY DEFINER`/owner/EXECUTE. | Definer có thể bypass RLS. |
| App sử dụng một DB role cho nhiều tenant? | Trusted tenant context + policy. | Custom GUC có thể bị spoof khi user chạy SQL tùy ý. |
| Query dùng bảng phụ để kiểm tra membership? | `EXISTS`/function có kiểm soát. | Privileges, recursion, races và performance. |
| Bảng phân vùng? | Policy trên đúng đường parent/child. | Grants trực tiếp child có thể mở đường khác. |
| Cần ngăn TRUNCATE? | Không cấp `TRUNCATE`. | RLS không lọc TRUNCATE theo hàng. |
| Cần ngăn lộ qua duplicate key? | Constraint/schema/API error design. | UNIQUE/FK checks có thể tạo side channel. |
| Có cần biết policy đang hoạt động? | `pg_policies` + `pg_class` + role tests. | Có policy nhưng bảng RLS disabled thì chưa bảo vệ. |

### 34.1. “Deny by default” cần triển khai như một nguyên tắc

Đối với mỗi bảng chứa dữ liệu tenant:

1. Thu hẹp quyền đối tượng trước.
2. Bật RLS.
3. Thiết kế policy cho từng command thực sự cần.
4. Kiểm thử bằng role ít quyền nhất.
5. Phủ cả các đường view/function/jobs và constraints.

Không lấy quyền đọc toàn bộ rồi cố thu hẹp chỉ bằng application WHERE. RLS có giá trị nhất khi hoạt động như một lớp bảo vệ độc lập bổ sung.

## 35. Bài tập thực hành

Các bài dùng lab `rls_demo.documents` đã tạo sáu rows, bốn policies và hai roles. Những bài có lệnh dự kiến lỗi cần chạy riêng và `ROLLBACK` sau lỗi trong transaction. Những bài cần role/admin sử dụng tài khoản được phép `SET ROLE` trong database thực hành. Không chạy các lệnh cấp đặc quyền hoặc DISABLE RLS trên production.

### Bài 1. Hai tầng quyền

Giải thích vì sao `GRANT SELECT ON rls_demo.documents TO rls_demo_alpha` không đảm bảo alpha chỉ đọc dữ liệu của mình, và vì sao CREATE POLICY cũng không đủ nếu quên GRANT.

### Bài 2. Default deny

Sau `ALTER TABLE ... ENABLE ROW LEVEL SECURITY` nhưng chưa có policy, role alpha (không bypass) đã được GRANT SELECT sẽ thấy bao nhiêu hàng? Owner thường có thể thấy bao nhiêu?

### Bài 3. SELECT policy

Viết policy cho cả alpha và beta chỉ SELECT hàng có `tenant_role=current_user::text`.

### Bài 4. Kết quả SELECT của alpha

Trên sáu rows gốc, alpha thấy những document_id nào? Tổng `amount` bằng bao nhiêu?

### Bài 5. SELECT ID ngoài tenant

Alpha chạy `SELECT ... WHERE document_id=4`. Kỳ vọng lỗi permission denied hay kết quả 0 rows? Giải thích.

### Bài 6. INSERT policy

Viết policy chỉ cho alpha/beta INSERT hàng có tenant_role đúng với current_user.

### Bài 7. INSERT sai tenant

Alpha cố INSERT `(12, 'rls_demo_beta', 'x', 'draft', 10)`. Policy kiểm tra hàng nào và có cho qua không?

### Bài 8. UPDATE USING

Viết UPDATE policy cho phép mỗi tenant sửa các hàng cũ có tenant_role khớp role.

### Bài 9. UPDATE WITH CHECK

Alpha UPDATE ID 1 đổi `tenant_role='rls_demo_beta'`. Với USING và WITH CHECK cùng điều kiện tenant, giải thích từng giai đoạn và kết quả.

### Bài 10. Hàng khác tenant khi UPDATE

Alpha chạy `UPDATE ... SET title='bad' WHERE document_id=4`. Kết quả thường là mấy rows?

### Bài 11. DELETE policy

Viết policy FOR DELETE cho alpha và beta chỉ xóa hàng tenant của mình.

### Bài 12. Không có WITH CHECK cho DELETE

Vì sao `FOR DELETE` không có WITH CHECK? Khi nào một hàng bị loại khỏi DELETE?

### Bài 13. FOR ALL

Viết một policy FOR ALL cho role `app_user` trên bảng giả định `app.documents`, dùng `tenant_id=app.current_tenant_id()` cho cả điều kiện đọc/sửa hàng cũ và điều kiện ghi hàng mới.

### Bài 14. Fallback của WITH CHECK

Nếu policy FOR UPDATE khai báo USING nhưng không ghi WITH CHECK, có đúng rằng role sẽ được tự ý đổi tenant_id sang giá trị bất kỳ không?

### Bài 15. PERMISSIVE và OR

Hai policy SELECT permissive cho cùng role:

```sql
USING (tenant_id = 42)
USING (state = 'published')
```

Biểu thức hiệu lực là gì? Có khả năng lộ hàng tenant khác không?

### Bài 16. RESTRICTIVE và AND

Nếu có permissive `USING(tenant_role=current_user::text)` và restrictive `USING(state<>'archived')`, alpha thấy những IDs nào trong lab?

### Bài 17. Chỉ restrictive policy

Role có SELECT grant và bảng bật RLS, nhưng chỉ có một policy restrictive `USING(true)`, không có permissive policy. Role được xem tất cả rows không?

### Bài 18. FORCE OWNER

`FORCE ROW LEVEL SECURITY` thay đổi điều gì cho owner bình thường? Nó có khiến superuser/BYPASSRLS chịu RLS không?

### Bài 19. row_security off

Một app role không có BYPASSRLS đặt `SET row_security = off` rồi SELECT. Nó có được xem toàn bộ hàng không?

### Bài 20. pg_policies

Viết query liệt kê policy name, command, permissive, roles, USING và WITH CHECK của `rls_demo.documents`.

### Bài 21. Bật RLS thật hay chưa?

Viết query xem `relrowsecurity` và `relforcerowsecurity` cho bảng lab.

### Bài 22. Quyền đối tượng

Viết query xác định alpha có quyền SELECT và UPDATE trên bảng lab không. Kết quả ấy có nói alpha thấy được mọi row không?

### Bài 23. current_user vs session_user

Trong một session quản trị chạy `SET ROLE rls_demo_alpha`, `current_user` và `session_user` có nhất thiết giống nhau không? Policy lab đang dùng giá trị nào?

### Bài 24. Custom tenant GUC

Nêu điều kiện để policy dựa `current_setting('app.tenant_id',true)` có thể an toàn trong một backend đáng tin cậy. Vì sao đây không phải boundary bảo mật nếu client chạy SQL tùy ý dưới cùng app role?

### Bài 25. SET LOCAL và pool

Trong mô hình shared role + pool, vì sao đặt `SET LOCAL app.tenant_id` trong mỗi transaction có thể tốt hơn session-level SET?

### Bài 26. SECURITY DEFINER

Một function SECURITY DEFINER do owner bypass RLS sở hữu trả `SELECT COUNT(*) FROM documents`. Alpha có thể nhận số 6 dù SELECT trực tiếp chỉ nhận 3 không? Cần kiểm soát gì?

### Bài 27. security_invoker view

PostgreSQL từ major nào hỗ trợ `security_invoker=true` cho view? Nó khác view mặc định và `security_barrier` ra sao?

### Bài 28. TRUNCATE

Nếu một app role có quyền TRUNCATE bảng có RLS, TRUNCATE có chỉ xóa hàng tenant của role theo USING không? Bạn cần làm gì?

### Bài 29. UNIQUE side channel

Tại sao `UNIQUE(email)` toàn bảng có thể tiết lộ việc email đã có ở tenant khác dù RLS chặn SELECT? Nếu business chỉ cần email unique trong tenant, constraint nào phù hợp?

### Bài 30. FK side channel

Một lệnh INSERT tham chiếu ID hàng parent không nhìn thấy qua RLS. Vì sao kết quả FK check vẫn có thể tiết lộ sự tồn tại của parent?

### Bài 31. Policy subquery

Policy `USING(EXISTS(SELECT 1 FROM app.membership ...))` có thể gặp những vấn đề gì về quyền, hiệu năng và concurrency?

### Bài 32. Connection pool bug

Request tenant 42 dùng connection số 7 rồi trả vào pool mà không reset session GUC. Request tenant 99 nhận connection ấy có thể gặp chuyện gì? Viết hai cách phòng ngừa.

### Bài 33. SELECT và UPDATE RETURNING

Một role có UPDATE grant/policy nhưng không có SELECT permission/policy phù hợp. Vì sao `UPDATE ... RETURNING title` có thể không hoạt động như mong đợi?

### Bài 34. Policy đổi trạng thái

Viết hai điều kiện USING và WITH CHECK cho editor chỉ sửa tài liệu của tenant hiện tại khi state cũ là draft, và state mới chỉ draft/review.

### Bài 35. Tối ưu index

Với bảng 20 triệu documents và policy `tenant_role=current_user::text`, ứng dụng thường SELECT `WHERE state='published'`. Gợi ý một index và các bước đo hiệu năng.

### Bài 36. RLS và view owner

Tại sao một bảng có RLS vẫn có thể lộ dữ liệu qua view nếu view chạy theo owner bypass? Nêu cách thiết kế giảm rủi ro.

### Bài 37. Test negative

Đề xuất ít nhất tám negative tests cho tenant alpha để phát hiện lỗi SELECT/INSERT/UPDATE/DELETE, bypass qua view/function và context pool.

### Bài 38. Migrate policy

Một đội thêm policy PERMISSIVE `USING(true)` cho mọi role và nghĩ rằng nó sẽ “giúp các policy cũ chạy ổn định hơn”. Rủi ro là gì?

### Bài 39. Bảo trì cross-tenant

Một job cần dọn tài liệu archived của mọi tenants, trong khi app role chỉ được DELETE tài liệu tenant hiện tại. Có nên dùng app role rồi bỏ RLS không? Gợi ý mô hình an toàn hơn.

### Bài 40. Thiết kế tổng hợp

Bạn thiết kế SaaS multi-tenant: một bảng `invoices(tenant_id, invoice_id, amount, state)`, backend có hàng trăm tenants, dùng connection pool. Hãy đề xuất permission model, RLS policies cho SELECT/INSERT/UPDATE/DELETE, nguồn tenant identity đáng tin cậy, kiểu test và các điểm cần kiểm toán.

## 36. Hướng dẫn giải bài tập

### Đáp án 1. GRANT và RLS

`GRANT SELECT` xác định role có quyền đọc relation, không tự lọc hàng. Policy `USING` xác định tập hàng được phép nhưng không cấp quyền SELECT; thiếu một trong hai thì kết quả không đạt mục tiêu. Cần kết hợp schema USAGE, table/column GRANT và RLS.

### Đáp án 2. Default deny

Role alpha không bypass thấy **0 rows** khi RLS bật mà chưa có policy phù hợp. Table owner bình thường **mặc định bypass** nên có thể thấy cả sáu rows nếu không dùng FORCE; superuser cũng bypass.

### Đáp án 3. SELECT policy

```sql
CREATE POLICY documents_select_own
ON rls_demo.documents
FOR SELECT
TO rls_demo_alpha, rls_demo_beta
USING (tenant_role = current_user::text);
```

Trong lab policy đã được tạo; đây là đáp án mẫu, không chạy lại cùng tên.

### Đáp án 4. Alpha SELECT

Alpha thấy IDs **1, 2, 5**. Tổng amount là `100+250+30 = 380`. Beta thấy IDs **3, 4, 6**, tổng amount 520.

### Đáp án 5. Hàng tenant khác

`SELECT ... WHERE document_id=4` dưới alpha thường trả **0 rows** do policy USING loại hàng ID 4. Không mặc định trả lỗi permission denied chỉ vì hàng khác tenant tồn tại.

### Đáp án 6. INSERT policy

```sql
CREATE POLICY documents_insert_own
ON rls_demo.documents
FOR INSERT
TO rls_demo_alpha, rls_demo_beta
WITH CHECK (tenant_role = current_user::text);
```

`FOR INSERT` dùng `WITH CHECK` vì kiểm tra hàng mới. Policy đã tồn tại trong lab.

### Đáp án 7. INSERT sai tenant

Role alpha định ghi hàng có `tenant_role=rls_demo_beta`. Biểu thức WITH CHECK trả FALSE, nên INSERT bị từ chối bằng lỗi row-level security; không silently INSERT 0 rows.

### Đáp án 8. UPDATE policy

```sql
CREATE POLICY documents_update_own
ON rls_demo.documents
FOR UPDATE
TO rls_demo_alpha, rls_demo_beta
USING (tenant_role = current_user::text)
WITH CHECK (tenant_role = current_user::text);
```

USING lọc hàng cũ, WITH CHECK giới hạn hàng mới. Đáp án giả định policy chưa được tạo, không chạy lại trong lab đã chuẩn bị.

### Đáp án 9. Đổi tenant bằng UPDATE

ID 1 thuộc alpha nên USING TRUE; sau đổi `tenant_role=beta`, WITH CHECK FALSE. PostgreSQL từ chối UPDATE. Đây là lý do không chỉ kiểm tra hàng cũ khi business cấm chuyển quyền sở hữu.

### Đáp án 10. UPDATE tenant khác

Kết quả thông thường **UPDATE 0 rows** do hàng cũ ID 4 không vượt USING. Điều này không chứng minh hàng ID 4 không tồn tại vật lý.

### Đáp án 11. DELETE policy

```sql
CREATE POLICY documents_delete_own
ON rls_demo.documents
FOR DELETE
TO rls_demo_alpha, rls_demo_beta
USING (tenant_role = current_user::text);
```

DELETE chỉ cần xác định những hàng cũ được phép là mục tiêu.

### Đáp án 12. DELETE và WITH CHECK

DELETE không tạo phiên bản hàng mới cần kiểm tra, nên `WITH CHECK` không dùng trong `FOR DELETE`. Hàng không qua USING không tham gia DELETE, thường dẫn đến số rows bị xóa thấp hơn dự kiến hoặc 0.

### Đáp án 13. FOR ALL

Mẫu trên các objects đã được thiết lập:

```sql
CREATE POLICY app_docs_tenant_scope
ON app.documents
FOR ALL
TO app_user
USING (
    tenant_id = app.current_tenant_id()
)
WITH CHECK (
    tenant_id = app.current_tenant_id()
);
```

App role phải có các object privileges cần thiết và `app.current_tenant_id()` phải lấy tenant từ nguồn đáng tin cậy. Policy FOR ALL không tự grant quyền bảng.

### Đáp án 14. Fallback

Sai. Với policy UPDATE/ALL có USING nhưng không khai báo WITH CHECK, PostgreSQL dùng biểu thức USING làm kiểm tra hàng mới theo quy tắc fallback. Người viết vẫn nên khai báo tường minh hai điều kiện khi chúng mang ý nghĩa khác nhau.

### Đáp án 15. Permissive OR

Biểu thức hiệu lực:

```sql
(tenant_id = 42) OR (state = 'published')
```

Một hàng tenant khác nhưng published vẫn thỏa vế thứ hai, nên **có rủi ro lộ cross-tenant**. Nếu cần cả hai điều kiện, dùng AND trong policy hoặc một restrictive điều kiện phù hợp.

### Đáp án 16. Restrictive AND

Alpha ban đầu thấy 1, 2, 5. Policy restrictive loại `archived` nên chỉ còn **1, 2**. Khi thử trong transaction và rollback, policy mới được hoàn tác.

### Đáp án 17. Chỉ restrictive

Không. Restrictive policy chỉ thu hẹp tập đã được permissive policy cho phép. Không có permissive policy phù hợp thì vẫn default deny đối với role chịu RLS.

### Đáp án 18. FORCE

`FORCE ROW LEVEL SECURITY` khiến table owner bình thường cũng bị policy áp khi truy vấn bảng. Nó **không buộc superuser hoặc BYPASSRLS role** chịu RLS.

### Đáp án 19. row_security off

Không. `row_security=off` không cấp đặc quyền bypass; với role bị policy lọc, query có thể báo lỗi thay vì âm thầm chỉ trả subset. Muốn xem đầy đủ, cần quyền quản trị/bypass thích hợp và một luồng vận hành được kiểm soát.

### Đáp án 20. pg_policies

```sql
SELECT
    policyname,
    cmd,
    permissive,
    roles,
    qual,
    with_check
FROM pg_policies
WHERE schemaname = 'rls_demo'
  AND tablename = 'documents'
ORDER BY policyname;
```

`qual` biểu thị USING; `with_check` là check biểu thức khai báo. Không dựa vào cột rỗng để tự suy luận fallback.

### Đáp án 21. pg_class

```sql
SELECT
    c.relrowsecurity,
    c.relforcerowsecurity
FROM pg_class AS c
WHERE c.oid = 'rls_demo.documents'::regclass;
```

`relrowsecurity` kiểm tra ENABLE; `relforcerowsecurity` kiểm tra FORCE đối với owner.

### Đáp án 22. has_table_privilege

```sql
SELECT
    has_table_privilege(
        'rls_demo_alpha',
        'rls_demo.documents',
        'SELECT'
    ) AS can_select,
    has_table_privilege(
        'rls_demo_alpha',
        'rls_demo.documents',
        'UPDATE'
    ) AS can_update;
```

Hai TRUE nói role có quyền tương ứng, **không** nói role đọc/sửa mọi row; RLS vẫn áp riêng.

### Đáp án 23. current_user và session_user

`SET ROLE` làm `current_user` thay theo role effective, còn `session_user` thường là role gốc đăng nhập. Chúng không nhất thiết giống nhau. Lab so sánh `tenant_role = current_user::text`, nên role alpha chỉ thấy alpha rows.

### Đáp án 24. GUC và trust boundary

Backend phải xác thực tenant, tự đặt context trong transaction bằng đường tin cậy, dùng query parameterized, giới hạn quyền DB và cấm direct SQL không tin cậy dưới shared app role. Nếu kẻ tấn công điều khiển SQL của app role, họ có thể thay custom GUC `app.tenant_id` và thử đọc tenant khác; GUC tự nó không phải định danh không thể giả mạo.

### Đáp án 25. SET LOCAL

`SET LOCAL` tồn tại trong transaction nên tránh giữ tenant A trên connection khi pool trả connection cho request tenant B, miễn là mọi query liên quan được chạy trong đúng transaction và context được đặt lại đúng. Với session-level SET, phải reset đáng tin cậy; với transaction pooling không được giả định session context tồn tại qua các transactions.

### Đáp án 26. SECURITY DEFINER

Có. Function chạy theo quyền definer, và nếu definer có khả năng bypass RLS, nó có thể đọc cả sáu rows rồi trả COUNT=6, dù alpha trực tiếp chỉ thấy 3. Cần audit owner/function privileges, EXECUTE grants, input validation, `search_path` và nội dung dữ liệu function trả; không dùng SECURITY DEFINER như cách bypass tùy tiện.

### Đáp án 27. security_invoker view

PostgreSQL hỗ trợ `security_invoker=true` cho view từ **major 15**. View này dùng quyền/RLS của caller trên quan hệ nền theo ngữ nghĩa tương ứng; view thông thường có thể dùng context của view owner. `security_barrier` liên quan bảo vệ trước một số tối ưu/biểu thức có thể rò rỉ, không có nghĩa giống `security_invoker`.

### Đáp án 28. TRUNCATE

Không. `TRUNCATE` không chịu lọc row-by-row theo USING. Không cấp TRUNCATE cho app tenant roles, và khi cần xóa theo tenant phải dùng DELETE với điều kiện và RLS/constraints đúng, hoặc quy trình quản trị được phép.

### Đáp án 29. UNIQUE side channel

Unique check vẫn bảo đảm tính duy nhất của tập dữ liệu liên quan, có thể báo duplicate cho một giá trị bị tenant khác sử dụng mà caller không SELECT được. Nếu business chỉ cần unique per tenant, dùng:

```sql
UNIQUE (tenant_id, email)
```

Không đổi từ global unique sang tenant unique nếu yêu cầu nghiệp vụ bắt buộc khác.

### Đáp án 30. FK side channel

Referential integrity checks không hoạt động như SELECT thường chịu hàng bị RLS lọc; lệnh INSERT tham chiếu có thể thành công/thất bại tùy parent tồn tại, tạo tín hiệu sự tồn tại. Cần xác định IDs không đoán được, chính sách authorization và xử lý lỗi ít tiết lộ thông tin.

### Đáp án 31. Policy subquery

Các vấn đề gồm:

- Role cần quyền đọc bảng membership/hàm liên quan, nếu không query báo lỗi.
- Subquery tham chiếu lại bảng được RLS bảo vệ có thể gây policy recursion.
- Điều kiện membership thay đổi đồng thời có rủi ro snapshot/race.
- Truy vấn thiếu index có thể chậm khi được áp vào nhiều rows.

Cần thiết kế quyền/schema, isolation/locking phù hợp, index và đo EXPLAIN dưới role thật.

### Đáp án 32. Pool context

Request B tenant 99 có thể chạy queries với tenant context 42 còn sót nếu không reset, dẫn đến đọc nhầm dữ liệu hoặc lỗi. Hai hướng:

1. Dùng `SET LOCAL` trong transaction bao quanh tất cả queries của request.
2. Với session SET, thiết lập lại và reset connection context đáng tin cậy khi checkout/checkin; integration test qua pool.

Trong cả hai, tenant được xác thực ở server, không lấy trực tiếp từ input chưa tin cậy.

### Đáp án 33. UPDATE RETURNING

`RETURNING title` là một thao tác đọc giá trị; WHERE/SET cũng có thể tham chiếu cột. Role cần quyền SELECT và policy liên quan theo ngữ nghĩa của câu UPDATE. Chỉ có UPDATE grant/policy chưa đảm bảo mọi câu `UPDATE ... RETURNING` hợp lệ.

### Đáp án 34. Editor draft

```sql
USING (
    tenant_id = app.current_tenant_id()
    AND state = 'draft'
)
WITH CHECK (
    tenant_id = app.current_tenant_id()
    AND state IN ('draft', 'review')
)
```

USING kiểm tra hàng cũ, WITH CHECK kiểm tra hàng mới. Mẫu giả định app current tenant function đáng tin cậy; nếu có permissive policy khác, phải xem khả năng OR mở rộng quyền.

### Đáp án 35. Index và đo

Ví dụ:

```sql
CREATE INDEX idx_rls_demo_tenant_state
ON rls_demo.documents (tenant_role, state);
```

Index tương ứng hai predicate tenant và state; trên lab nếu index đã có thì không tạo lại. Với 20 triệu rows, so `EXPLAIN (ANALYZE, BUFFERS)` dưới role app, đo actual rows, buffers, planning/execution time, index size và write overhead. Không mặc định index scan luôn tốt hơn seq scan.

### Đáp án 36. View owner bypass

Một view bình thường có thể sử dụng quyền/security context của owner để đọc bảng nền. Nếu view owner bypass RLS, caller nhận dữ liệu vượt phạm vi khi được GRANT SELECT view. Từ PG15 có thể dùng `security_invoker=true` khi phù hợp, tách owner/bypass roles, hạn chế GRANT trên view và kiểm thử thực tế bằng role tenant.

### Đáp án 37. Tám negative tests

Một bộ tối thiểu:

1. Alpha SELECT row beta ID 4 → không trả row.
2. Alpha UPDATE row beta ID 4 → không sửa row.
3. Alpha DELETE row beta ID 6 → không xóa row.
4. Alpha INSERT row có tenant_role beta → lỗi RLS.
5. Alpha UPDATE row alpha chuyển tenant_role beta → lỗi RLS.
6. Alpha gọi một view được cấp quyền → không lộ beta rows (nếu contract yêu cầu).
7. Alpha gọi exposed SECURITY DEFINER function → không lộ số liệu/chi tiết ngoài scope.
8. Hai requests tenant khác nhau dùng cùng connection pool → không dùng lẫn tenant context.

Nên bổ sung test khi không có tenant context, test `FOR ALL USING(true)` vô tình mở quyền, test role membership và test INSERT ON CONFLICT.

### Đáp án 38. PERMISSIVE USING(true)

Policy PERMISSIVE cùng command/role được OR với các policy permissive hiện có. Thêm `USING(true)` có thể khiến tập cho phép trở thành TRUE cho mọi hàng, vô hiệu hóa về mặt lọc các điều kiện tenant cũ ở đường đọc/sửa/xóa liên quan. Đây là rủi ro nghiêm trọng; muốn siết quyền, dùng restrictive policy hoặc AND trong rule được kiểm soát.

### Đáp án 39. Cross-tenant maintenance

Không nên tắt RLS cho role ứng dụng hoặc cấp BYPASSRLS tùy tiện. Tạo maintenance job/role riêng có quyền được ủy quyền, quản lý secrets, giới hạn lịch/vùng dữ liệu, audit và dry-run/count. Một backend tenant role tiếp tục giữ RLS; cross-tenant job chạy qua đường quản trị chuyên biệt với kiểm soát riêng.

### Đáp án 40. Thiết kế hệ thống invoices

Một phương án:

1. **Owner migration** sở hữu bảng và policies; **app_runtime** không phải owner và không BYPASSRLS.
2. Bật `ENABLE ROW LEVEL SECURITY` trên `invoices`.
3. Chọn tenant identity đáng tin: separate DB roles hoặc trusted backend đặt context transaction-scope; không dựa custom GUC nếu client có SQL execution tùy ý.
4. Tạo policy SELECT `USING(tenant_id=current_tenant)`.
5. Tạo policy INSERT `WITH CHECK(tenant_id=current_tenant)`.
6. Tạo policy UPDATE `USING(tenant_id=current_tenant)` và `WITH CHECK(tenant_id=current_tenant)`, bổ sung state restrictions nếu cần.
7. Tạo policy DELETE theo `USING` nếu ứng dụng thực sự cần DELETE; nếu không, không cấp DELETE và không tạo policy.
8. Giới hạn `GRANT` theo cột/lệnh, không cấp TRUNCATE/DDL/BYPASS.
9. Dùng constraints cho invoice identity, numeric ranges, state transitions; xem unique key per tenant nếu phù hợp business.
10. Kiểm thử âm tính nhiều tenants, SQL không có WHERE, INSERT/UPDATE sai tenant, UPDATE RETURNING, UPSERT, view/functions, connection pooling và backup/maintenance roles.
11. Audit `pg_policies`/`pg_class`/role membership, theo dõi EXPLAIN và dữ liệu truy cập, không log secrets hay nội dung nhạy cảm.

Ví dụ policy tổng quát **sau khi đã có objects và function current_tenant được xác thực**:

```sql
CREATE POLICY invoices_read ON app.invoices
FOR SELECT TO app_runtime
USING (tenant_id = app.current_tenant_id());

CREATE POLICY invoices_insert ON app.invoices
FOR INSERT TO app_runtime
WITH CHECK (tenant_id = app.current_tenant_id());

CREATE POLICY invoices_update ON app.invoices
FOR UPDATE TO app_runtime
USING (tenant_id = app.current_tenant_id())
WITH CHECK (tenant_id = app.current_tenant_id());
```

Nếu ứng dụng không có nhu cầu xóa invoice, **không** tạo DELETE policy/GRANT DELETE. Nếu cần xóa, thêm policy delete theo tenant và luật nghiệp vụ tương ứng. Các câu này không chạy trực tiếp trong lab vì `app.invoices` và `app.current_tenant_id()` là objects giả định.

## 37. Checklist bảo mật Row-Level Security

### 37.1. Schema và quyền

1. Bảng chứa dữ liệu tenant đã `ENABLE ROW LEVEL SECURITY` chưa?
2. Mọi bảng tenant liên quan đều được bảo vệ, kể cả bảng mới trong migration?
3. Role app có phải owner, superuser hoặc `BYPASSRLS` không?
4. Có cần `FORCE ROW LEVEL SECURITY` cho owner thường hay không?
5. Schema `USAGE`, table/column GRANT có theo least privilege không?
6. Role app có bị cấp `TRUNCATE`, `REFERENCES` hoặc DDL ngoài nhu cầu không?
7. View, materialized view, functions và jobs có đường đọc/ghi nào bypass policy không?

### 37.2. Policy design

8. Policy SELECT `USING` có dùng tenant identity đáng tin không?
9. Policy INSERT `WITH CHECK` có chặn tạo hàng tenant khác không?
10. Policy UPDATE có kiểm tra **cả hàng cũ và hàng mới** không?
11. DELETE chỉ được mở nếu business thực sự cần?
12. Có policy PERMISSIVE nào mở rộng quyền bất ngờ qua OR không?
13. Restrictive policies có ít nhất một permissive policy phù hợp để hoạt động không?
14. Policy FOR ALL có làm thay đổi các command ngoài ý định không?
15. Policy expressions có xử lý SQL NULL/UNKNOWN đúng deny-by-default không?
16. Những hàm/bảng phụ policy tham chiếu có quyền và chi phí phù hợp không?

### 37.3. Tenant identity và application

17. Có phân biệt `current_user`, `session_user` và tenant context không?
18. Nếu dùng custom GUC, user không tin cậy có thể tự SET nó qua SQL không?
19. Với connection pool, context có được đặt theo từng transaction/reset đúng không?
20. SQL được parameterize và chống injection không?
21. Có giảm thiểu SECURITY DEFINER search_path/EXECUTE leakage không?
22. Với PG15+, view nào cần `security_invoker=true`?
23. App có quyền truy cập trực tiếp partitions hoặc bảng phụ không kiểm soát không?

### 37.4. Kiểm thử và vận hành

24. Đã test SELECT không WHERE dưới từng tenant chưa?
25. Đã test INSERT/UPDATE đổi tenant sai và xác nhận lỗi chưa?
26. Đã test UPDATE/DELETE ngoài tenant ảnh hưởng 0 rows chưa?
27. Đã test các câu `RETURNING`, UPSERT và paths qua view/function chưa?
28. Đã test tránh context leak qua pool với requests nối tiếp và song song chưa?
29. Đã đánh giá UNIQUE/FK errors như side channel chưa?
30. Có job backup và maintenance role chuyên biệt không?
31. Có quan sát `pg_policies`, `pg_class`, role grants/membership không?
32. Có đo EXPLAIN và indexes để RLS không làm workload suy giảm quá mức không?
33. Có test migration khi policy bị xóa/đổi loại hoặc một bảng mới chưa bật RLS không?
34. Có log/audit truy cập và errors theo nguyên tắc không lộ thông tin nhạy cảm không?

## 38. Tổng kết

**Row-Level Security** giúp PostgreSQL thực thi giới hạn truy cập ở **cấp hàng** dưới chính database role và policy, bổ sung một tầng an toàn quan trọng bên cạnh điều kiện WHERE của application.

Những quy tắc cần nhớ:

- **`GRANT` và RLS là hai lớp khác nhau:** role phải có quyền đối tượng rồi mới được xét hàng theo policy.
- **`ENABLE ROW LEVEL SECURITY` không tự tạo policy:** với role chịu RLS, không có permissive policy phù hợp nghĩa là default deny.
- **`USING` kiểm tra hàng hiện có** cho SELECT, UPDATE, DELETE.
- **`WITH CHECK` kiểm tra hàng mới** cho INSERT và phiên bản sau UPDATE; sai check thường bị lỗi, không âm thầm bỏ qua.
- **UPDATE cần nghĩ về hai trạng thái:** hàng cũ có được sửa không và hàng sau sửa có còn thuộc phạm vi được phép không.
- **Policy permissive OR, restrictive AND:** thêm một permissive policy có thể mở rộng quyền ngoài ý định.
- **Owner mặc định bypass RLS; FORCE chỉ buộc owner thông thường; superuser/BYPASSRLS vẫn có khả năng bypass.**
- **`row_security=off` không cấp bypass**, nó có thể báo lỗi để tránh xử lý dữ liệu bị lọc không biết.
- **Session GUC không phải danh tính bảo mật không thể giả mạo:** nếu app role cho user chạy SQL tùy ý, họ có thể đặt custom context; phải có trust boundary rõ.
- **Views và SECURITY DEFINER functions cần review riêng:** quyền owner có thể khiến đường truy cập gián tiếp không chịu chính sách của caller.
- **RLS không lọc mọi thao tác:** TRUNCATE, UNIQUE/FK checks và các side channels cần được kiểm soát bằng quyền và thiết kế schema/API.
- **Kiểm thử bằng role app ít quyền**, không chỉ bằng superuser; theo dõi `pg_policies`, quyền và execution plan.

Nguyên tắc an toàn:

> **Dùng USING để giới hạn những hàng người dùng được động tới; dùng WITH CHECK để giới hạn những hàng người dùng được phép tạo ra. Giữ tenant identity đáng tin và kiểm thử mọi đường truy cập, không chỉ một SELECT mẫu.**

RLS rất hữu ích cho hệ thống đa tenant, dữ liệu theo owner và các nhu cầu phân tách hàng, nhưng chỉ đáng tin khi kết hợp **least privilege, đúng policy semantics, constraints, isolation, kiểm thử âm tính và vận hành có kiểm soát**.

## 39. Tài liệu tham khảo

Tài liệu PostgreSQL chính thức; đối chiếu với major server đang chạy:

- [Row Security Policies — PostgreSQL Documentation](https://www.postgresql.org/docs/current/ddl-rowsecurity.html): RLS, default deny, USING/WITH CHECK, permissive/restrictive, bypass và giới hạn.
- [CREATE POLICY](https://www.postgresql.org/docs/current/sql-createpolicy.html): cú pháp, command applicability và policy expressions.
- [ALTER POLICY](https://www.postgresql.org/docs/current/sql-alterpolicy.html): thay roles và expressions.
- [DROP POLICY](https://www.postgresql.org/docs/current/sql-droppolicy.html): gỡ policy.
- [ALTER TABLE](https://www.postgresql.org/docs/current/sql-altertable.html): ENABLE/DISABLE/FORCE/NO FORCE ROW LEVEL SECURITY.
- [GRANT](https://www.postgresql.org/docs/current/sql-grant.html): quyền schema/table/column/function.
- [Role Attributes](https://www.postgresql.org/docs/current/role-attributes.html): superuser, BYPASSRLS và role privileges.
- [SET ROLE](https://www.postgresql.org/docs/current/sql-set-role.html): active role, CURRENT_USER và role context.
- [pg_policies](https://www.postgresql.org/docs/current/view-pg-policies.html): quan sát policy definitions.
- [CREATE VIEW](https://www.postgresql.org/docs/current/sql-createview.html): tùy chọn `security_invoker` và `security_barrier`.
- [CREATE FUNCTION](https://www.postgresql.org/docs/current/sql-createfunction.html): SECURITY DEFINER, search_path, EXECUTE grants.
- [CREATE TRIGGER](https://www.postgresql.org/docs/current/sql-createtrigger.html): ảnh hưởng trigger trong thao tác ghi.
- [EXPLAIN](https://www.postgresql.org/docs/current/sql-explain.html): đo kế hoạch truy vấn với RLS trong ngữ cảnh role thực.







