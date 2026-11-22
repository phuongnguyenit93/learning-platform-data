# FORCE ROW LEVEL SECURITY và các trường hợp được bỏ qua chính sách trong PostgreSQL

**Row-Level Security (RLS)** giúp PostgreSQL giới hạn **những hàng mà một vai trò được phép đọc, chèn, sửa hoặc xóa**. Tính năng đặc biệt hữu ích khi một bảng chứa dữ liệu của nhiều tenant, phòng ban, khách hàng hoặc nhóm có quyền khác nhau.

Tuy nhiên, một giả định rất nguy hiểm là: “Tôi đã bật RLS, nên mọi người truy cập bảng đều bị các policy giới hạn”. Trong PostgreSQL, một số chủ thể **có thể bỏ qua chính sách RLS**:

- **Superuser**.
- **Role có thuộc tính `BYPASSRLS`**.
- **Chủ sở hữu bảng (table owner)** theo mặc định, **trừ khi** bảng được đặt `FORCE ROW LEVEL SECURITY`.

Vì vậy, hai lệnh này có mục đích khác nhau:

~~~sql
ALTER TABLE secure.orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE secure.orders FORCE ROW LEVEL SECURITY;
~~~

Lệnh đầu bật cơ chế xét chính sách theo hàng; lệnh sau buộc **owner bình thường** cũng phải chịu chính sách khi RLS đang bật. **FORCE không ngăn superuser hoặc role BYPASSRLS bỏ qua RLS.**

Bài **“FORCE ROW LEVEL SECURITY và các trường hợp được bỏ qua chính sách”**, thuộc chương **Bảo mật**, module **Database Engine Relational PostgreSQL**, làm rõ các ngoại lệ, hành vi của table owner, mối quan hệ với `GRANT`, policy `USING`/`WITH CHECK`, `row_security=off`, sao lưu, view, `SECURITY DEFINER`, các đường thao tác đặc biệt và cách kiểm chứng bằng role thật.

> **Phạm vi thực hành:** chỉ thực hiện các lệnh tạo role, thay owner, FORCE/DISABLE RLS và các thử nghiệm DML trong database lab riêng. Trong production, thay đổi RLS có thể khiến dữ liệu bị lộ hoặc làm ứng dụng ngừng hoạt động. Không dùng superuser/BYPASSRLS làm tài khoản ứng dụng thông thường.

---

## 1. Hình dung RLS bằng bài toán đa tenant

Giả sử bảng orders chứa:

| order_id | tenant_id | amount | status |
|---:|---:|---:|---|
| 1 | 10 | 100.00 | paid |
| 2 | 10 | 80.00 | draft |
| 3 | 20 | 300.00 | paid |
| 4 | 20 | 40.00 | draft |

Ứng dụng cần bảo đảm:

- Người dùng tenant 10 chỉ đọc được đơn 1 và 2.
- Người dùng tenant 20 chỉ đọc được đơn 3 và 4.
- Người dùng không thể tự chèn hoặc sửa đơn thành tenant khác.
- Các tác vụ quản trị có quyền rộng hơn phải được kiểm soát.

Nếu chỉ dựa vào câu SQL của ứng dụng:

~~~sql
SELECT *
FROM orders
WHERE tenant_id = 10;
~~~

một endpoint quên điều kiện tenant có thể trả dữ liệu của người khác. RLS giúp đặt các điều kiện này ở cấp bảng.

~~~sql
CREATE POLICY tenant_read ON secure.orders
FOR SELECT
USING (/* biểu thức xác định tenant hợp lệ */);
~~~

Đây là hình dạng minh họa, không phải policy chạy nguyên dạng. Trong lab phía dưới ta sẽ viết biểu thức cụ thể.

## 2. RLS nằm ở đâu trong mô hình phân quyền?

Một truy vấn muốn đọc dữ liệu cần đi qua nhiều lớp:

~~~text
Authentication và vai trò kết nối
                 |
                 v
USAGE trên schema, SELECT trên table
                 |
                 v
Có ngoại lệ bypass RLS không?
                 |
                 v
RLS ENABLED và policy phù hợp?
                 |
                 v
Những hàng SQL được phép trả về
~~~

RLS **không cấp quyền SELECT**. Nó chỉ giới hạn hàng trong trường hợp role đã có quyền truy cập và cơ chế RLS áp dụng cho role đó.

Mặt khác, `GRANT SELECT` **không tự giới hạn tenant**. Nếu bảng RLS disabled hoặc role bypass, role có thể đọc nhiều hàng hơn dự định.

## 3. Bốn lệnh DDL cần phân biệt

~~~sql
ALTER TABLE secure.orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE secure.orders FORCE ROW LEVEL SECURITY;
ALTER TABLE secure.orders NO FORCE ROW LEVEL SECURITY;
ALTER TABLE secure.orders DISABLE ROW LEVEL SECURITY;
~~~

| Lệnh | Tác dụng |
|---|---|
| `ENABLE` | Bật việc áp dụng policies cho các role chịu RLS |
| `FORCE` | Buộc table owner bình thường chịu policies |
| `NO FORCE` | Khôi phục ngoại lệ owner mặc định |
| `DISABLE` | Tắt việc áp dụng row policies trên bảng |

FORCE chỉ có tác dụng lọc thực tế khi bảng đang **ENABLE** RLS. Hai trạng thái “RLS bật” và “owner bị buộc tuân RLS” được lưu riêng.

### 3.1. FORCE không tự tạo policy

Nếu không có SELECT policy cho owner, bật FORCE có thể khiến owner nhìn thấy **0 hàng**. PostgreSQL không tự tạo “policy dành riêng cho owner”.

### 3.2. NO FORCE không phải DISABLE

NO FORCE không giải phóng các role ứng dụng bình thường khỏi policies; nó chỉ trả lại ngoại lệ sở hữu bảng.

### 3.3. DISABLE có thể làm lộ dữ liệu

Khi DISABLE, một role đã được GRANT SELECT không còn bị RLS lọc. Do đó không dùng DISABLE như cách khắc phục tạm thời một lỗi policy trên bảng chứa dữ liệu nhiều tenant.

## 4. Ma trận hành vi trước và sau FORCE

Giả sử bảng đã ENABLE RLS, một policy chỉ cho xem một phần hàng, và role có quyền bảng cần thiết.

| Chủ thể | Không FORCE | Có FORCE |
|---|---|---|
| Role ứng dụng bình thường | Áp policy | Áp policy |
| Table owner bình thường | **Bypass** | **Áp policy** |
| Superuser | **Bypass** | **Bypass** |
| Role có `BYPASSRLS` | **Bypass** | **Bypass** |
| Role thiếu SELECT | Permission denied | Permission denied |

Đây là ma trận quan trọng nhất của bài.

**FORCE không phải công tắc bắt mọi role tuân RLS. Nó chỉ loại bỏ ngoại lệ mặc định của table owner không có đặc quyền bypass khác.**

## 5. Vì sao owner mặc định bỏ qua row policies?

Table owner có trách nhiệm quản trị một đối tượng: sửa cấu trúc, đặt grants và policies, thực hiện các thao tác bảo trì. PostgreSQL mặc định coi owner là chủ thể được miễn áp RLS cho chính bảng đó.

Hệ quả: nếu ứng dụng kết nối bằng role **sở hữu bảng** thì RLS có thể không lọc hàng, dù bạn đã viết policy đúng.

~~~text
Application connection = table owner
                  |
                  v
RLS ENABLED, NO FORCE
                  |
                  v
Owner bypass: policy không chặn các hàng
~~~

Để tránh:

1. Tách role **migration/table owner** khỏi runtime role.
2. Đừng cấp quyền DDL/ownership cho app khi không cần.
3. Cân nhắc FORCE cho bảng cần kiểm soát cả truy cập owner.
4. Kiểm thử bằng role ứng dụng thật, không chỉ superuser.

## 6. FORCE làm gì với owner?

~~~sql
ALTER TABLE secure.orders FORCE ROW LEVEL SECURITY;
~~~

Khi bảng RLS ENABLED:

- Owner bình thường không còn ngoại lệ RLS tự động.
- Những policy SELECT/INSERT/UPDATE/DELETE phù hợp có thể áp lên owner.
- Owner thấy hoặc ghi dữ liệu theo các policy áp dụng.
- Nếu không có policy phù hợp, operation có thể bị lọc hoặc từ chối.

FORCE **không** đổi owner, không thêm GRANT, không tạo policy, không làm bảng chứa dữ liệu mới.

### 6.1. Owner vẫn là người có quyền DDL

FORCE không tước mọi quyền quản trị cấu trúc khỏi owner. Một owner có quyền phù hợp có thể thay đổi policies hoặc cấu hình RLS của bảng. Vì vậy FORCE **không bảo vệ trước một table owner bị chiếm quyền và có khả năng sửa DDL**.

## 7. Superuser vẫn bypass khi FORCE

Superuser bỏ qua row security policies theo đặc quyền PostgreSQL, kể cả với bảng FORCE.

Nếu bạn kiểm tra:

~~~sql
SELECT COUNT(*) FROM secure.orders;
~~~

bằng tài khoản `postgres` superuser và thấy mọi hàng, điều đó **không chứng minh FORCE vô hiệu**. Bạn đang dùng role có ngoại lệ cao hơn.

Trong production, superuser nên dùng cho quản trị hệ thống được kiểm soát, không phải credentials của HTTP API hay job nghiệp vụ thường xuyên.

## 8. BYPASSRLS là thuộc tính role

Một role có `BYPASSRLS` bỏ qua RLS ở cấp database theo quyền đã được cấp. Nó không chỉ vượt policy của một bảng.

Đây không phải cú pháp hợp lệ:

~~~sql
-- Không có GRANT BYPASSRLS ON TABLE ...
~~~

BYPASSRLS là **role attribute**, không phải table-level grant.

Ví dụ quản trị (không chạy trên production để thử):

~~~sql
CREATE ROLE dedicated_audit_admin
NOLOGIN BYPASSRLS;
~~~

Việc tạo hay thay role có BYPASSRLS là thao tác dành cho superuser theo cơ chế đặc quyền PostgreSQL.

### 8.1. BYPASSRLS khác SELECT privilege

Role có BYPASSRLS **vẫn cần các table/schema privileges thông thường**, trừ các quyền rộng khác như superuser. BYPASSRLS không tương đương tự động GRANT SELECT trên toàn database.

### 8.2. Không cấp cho app_service

Nếu role dùng cho mọi request có BYPASSRLS, một câu query bị quên điều kiện tenant có thể nhìn xuyên tenant. FORCE trên bảng không khắc phục vấn đề đó.

## 9. Role membership và SET ROLE

Không nên suy rằng BYPASSRLS được kế thừa giống `GRANT SELECT` thông thường chỉ vì một role là thành viên role khác. Các role attributes đặc biệt có quy tắc riêng.

Tuy nhiên, quyền chuyển execution context bằng `SET ROLE` cũng quan trọng: một session được phép chuyển sang role đặc quyền có thể thay đổi quyền khi thực thi.

Hãy kiểm tra:

~~~sql
SELECT session_user, current_user, current_role;
~~~

- `session_user`: danh tính đăng nhập.
- `current_user`: execution role hiện tại trong ngữ cảnh phù hợp.
- `current_role`: thường phản ánh vai trò hiện tại.

Khi có `SET ROLE` hoặc `SECURITY DEFINER`, execution context có thể khác login ban đầu.

## 10. Quan sát rolbypassrls và rolsuper

~~~sql
SELECT
    rolname,
    rolsuper,
    rolbypassrls,
    rolcanlogin,
    rolinherit
FROM pg_roles
ORDER BY rolname;
~~~

Các trường:

- `rolsuper`: role có đặc quyền superuser.
- `rolbypassrls`: role có thuộc tính BYPASSRLS.
- `rolcanlogin`: có thể đăng nhập.
- `rolinherit`: thông tin liên quan kế thừa quyền membership.

Đây là truy vấn metadata; nên giới hạn đầu ra phù hợp đối tượng sử dụng và không public thông tin nội bộ không cần thiết.

## 11. Lab: các role dùng để thử RLS

Bài thực hành dùng một **database lab cô lập**, quyền tạo role và thay owner. Các lệnh tiếp theo cần được thực thi bởi người quản trị đủ quyền, chẳng hạn superuser trong database thử nghiệm.

Tạo ba role **NOLOGIN**:

~~~sql
CREATE ROLE rls_demo_owner NOLOGIN;
CREATE ROLE rls_demo_alice NOLOGIN;
CREATE ROLE rls_demo_bob NOLOGIN;
~~~

Chức năng:

| Role | Mục đích |
|---|---|
| `rls_demo_owner` | Table owner để thử exemption/FORCE |
| `rls_demo_alice` | Runtime role của tenant 10 |
| `rls_demo_bob` | Runtime role của tenant 20 |

Vì NOLOGIN, ta không cần mật khẩu. Admin đủ quyền có thể `SET ROLE` để mô phỏng từng role. Không tạo các role này trong môi trường đã có role trùng tên hoặc nơi bạn không được phép thao tác.

## 12. Lab: tạo schema, bảng và dữ liệu

~~~sql
CREATE SCHEMA rls_lab;

CREATE TABLE rls_lab.orders (
    order_id BIGINT PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    amount NUMERIC(12,2) NOT NULL CHECK (amount >= 0),
    status TEXT NOT NULL
        CHECK (status IN ('draft','paid','cancelled'))
);

INSERT INTO rls_lab.orders (
    order_id, tenant_id, amount, status
)
VALUES
    (1, 10, 100.00, 'paid'),
    (2, 10,  80.00, 'draft'),
    (3, 20, 300.00, 'paid'),
    (4, 20,  40.00, 'draft');

ALTER TABLE rls_lab.orders
OWNER TO rls_demo_owner;
~~~

Dữ liệu có đúng bốn rows như bảng ở đầu bài.

### 12.1. Cấp quyền cho runtime roles

~~~sql
GRANT USAGE ON SCHEMA rls_lab
TO rls_demo_alice, rls_demo_bob;

GRANT SELECT ON rls_lab.orders
TO rls_demo_alice, rls_demo_bob;
~~~

Alice và Bob có thể đọc bảng theo GRANT, nhưng chưa thể INSERT/UPDATE/DELETE bởi chỉ được cấp SELECT.

## 13. Lab: ENABLE RLS và policy đọc

~~~sql
ALTER TABLE rls_lab.orders
ENABLE ROW LEVEL SECURITY;

CREATE POLICY orders_tenant_read
ON rls_lab.orders
FOR SELECT
TO PUBLIC
USING (
    (current_user = 'rls_demo_alice' AND tenant_id = 10)
    OR
    (current_user = 'rls_demo_bob' AND tenant_id = 20)
    OR
    (current_user = 'rls_demo_owner' AND tenant_id = 10)
);
~~~

Policy dành cho mọi role (`TO PUBLIC`) nhưng biểu thức `USING` chỉ cho:

- Alice: tenant 10.
- Bob: tenant 20.
- Owner: tenant 10 **nếu owner đang chịu policy**.

Dùng `current_user` để biểu diễn rõ sự thay đổi execution role trong lab. Trong ứng dụng multi-tenant dùng chung một DB role, cần mô hình định danh tenant an toàn khác; sẽ bàn ở phần sau.

## 14. Lab: kiểm tra Alice

Trong một session admin được phép `SET ROLE`:

~~~sql
SET ROLE rls_demo_alice;

SELECT
    current_user,
    order_id,
    tenant_id,
    amount
FROM rls_lab.orders
ORDER BY order_id;

RESET ROLE;
~~~

Kết quả mong đợi:

| order_id | tenant_id | amount |
|---:|---:|---:|
| 1 | 10 | 100.00 |
| 2 | 10 | 80.00 |

Vì Alice không phải owner và không có BYPASSRLS, policy lọc hàng tenant 20.

## 15. Lab: kiểm tra Bob

~~~sql
SET ROLE rls_demo_bob;

SELECT
    current_user,
    order_id,
    tenant_id,
    amount
FROM rls_lab.orders
ORDER BY order_id;

RESET ROLE;
~~~

Kết quả mong đợi:

| order_id | tenant_id | amount |
|---:|---:|---:|
| 3 | 20 | 300.00 |
| 4 | 20 | 40.00 |

Hai role cùng có SELECT trên bảng, nhưng policy tạo hai tập dữ liệu khác nhau.

### 15.1. Không dùng kết quả superuser để thay test

Admin superuser có thể thấy cả bốn rows, vì vậy chỉ kiểm tra với superuser sẽ bỏ qua đúng cơ chế mà bài đang học.

## 16. Lab: owner trước FORCE

~~~sql
SET ROLE rls_demo_owner;

SELECT
    current_user,
    order_id,
    tenant_id
FROM rls_lab.orders
ORDER BY order_id;

RESET ROLE;
~~~

Khi RLS ENABLED **nhưng chưa FORCE**, owner bình thường bypass policy. Kết quả mong đợi: **cả bốn order 1, 2, 3, 4**.

Điểm đáng chú ý: biểu thức policy chỉ cho owner tenant 10, nhưng PostgreSQL không cần xét nó đối với owner đang được miễn RLS.

## 17. Lab: FORCE và chạy lại cùng query

Trở về quyền quản trị bảng:

~~~sql
ALTER TABLE rls_lab.orders
FORCE ROW LEVEL SECURITY;
~~~

Thử lại:

~~~sql
SET ROLE rls_demo_owner;

SELECT
    current_user,
    order_id,
    tenant_id
FROM rls_lab.orders
ORDER BY order_id;

RESET ROLE;
~~~

Kết quả mong đợi: **chỉ order 1 và 2**.

Thao tác FORCE không xóa hai rows tenant 20. Nó thay đổi việc owner có bị áp policy hay không.

### 17.1. Alice và Bob có thay đổi không?

Không theo logic policy hiện tại: cả hai đã phải chịu RLS từ trước FORCE. FORCE nhắm đến ngoại lệ của owner bình thường.

### 17.2. Owner vẫn là owner

Đổi FORCE không tương đương `ALTER TABLE ... OWNER TO ...`. Role sở hữu bảng vẫn là `rls_demo_owner`.

## 18. Lab: thử NO FORCE

~~~sql
ALTER TABLE rls_lab.orders
NO FORCE ROW LEVEL SECURITY;
~~~

Owner lại thấy cả bốn rows vì ngoại lệ ownership được khôi phục khi bảng RLS ENABLED.

Đưa bảng về trạng thái FORCE:

~~~sql
ALTER TABLE rls_lab.orders
FORCE ROW LEVEL SECURITY;
~~~

Đây là demo thay **metadata**, không thay dữ liệu nguồn.

## 19. DISABLE RLS gây thay đổi gì?

Ví dụ không nên chạy trong hệ thống thật chỉ để thử:

~~~sql
ALTER TABLE rls_lab.orders
DISABLE ROW LEVEL SECURITY;
~~~

Nếu Alice và Bob đã có quyền SELECT, truy vấn của họ **không còn bị RLS lọc** và có thể trả bốn hàng.

Để khôi phục lab:

~~~sql
ALTER TABLE rls_lab.orders
ENABLE ROW LEVEL SECURITY;

ALTER TABLE rls_lab.orders
FORCE ROW LEVEL SECURITY;
~~~

### 19.1. FORCE=true nhưng ENABLE=false?

Cờ FORCE có thể vẫn được lưu; nếu RLS disabled thì policy không áp dụng. Không chỉ nhìn thấy FORCE trong catalog rồi kết luận tenant isolation đang hoạt động.

## 20. Default deny khi thiếu policy

PostgreSQL áp dụng **default deny** với những role chịu RLS nếu không có policy nào cho phép thao tác tương ứng.

Ví dụ nếu bỏ mọi SELECT policy và vẫn ENABLE RLS:

- Alice SELECT: thường 0 rows.
- Bob SELECT: thường 0 rows.
- Owner với FORCE: thường 0 rows.
- Owner với NO FORCE: bypass.
- Superuser/BYPASSRLS: bypass.

Đừng nhầm “SELECT trả 0 rows” với “bảng đã bị xóa dữ liệu”.

Để bảo trì an toàn, hãy điều tra policy và role thay vì phản xạ DISABLE RLS.

## 21. Xem hai cờ RLS trong pg_class

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    pg_get_userbyid(c.relowner) AS owner_name,
    c.relrowsecurity AS rls_enabled,
    c.relforcerowsecurity AS rls_forced
FROM pg_class AS c
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE n.nspname = 'rls_lab'
  AND c.relname = 'orders';
~~~

| relrowsecurity | relforcerowsecurity | Ý nghĩa |
|---|---|---|
| false | false | Không áp row policies |
| true | false | Áp RLS, owner mặc định bypass |
| true | true | Áp RLS, owner bình thường chịu policy |
| false | true | FORCE flag có nhưng RLS disabled |

Hai cột là metadata độc lập. **Không được kết luận chỉ từ relforcerowsecurity**.

## 22. Xem policies trong pg_policies

~~~sql
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
WHERE schemaname = 'rls_lab'
  AND tablename = 'orders'
ORDER BY policyname;
~~~

Những trường quan trọng:

- `cmd`: `SELECT`, `INSERT`, `UPDATE`, `DELETE` hay `ALL`.
- `qual`: biểu thức `USING`.
- `with_check`: biểu thức `WITH CHECK`.
- `roles`: role scope.
- `permissive`: quy tắc kết hợp policy.

**Policy tồn tại không chứng minh nó có hiệu lực với một role cụ thể.** Cần kiểm tra cả ENABLE/FORCE, role bypass và command được thực thi.

## 23. Xem trong psql

Lệnh:

~~~text
\d+ rls_lab.orders
~~~

là meta-command của **psql**, có thể giúp quan sát bảng, policies và thuộc tính liên quan tùy version.

Nó không phải một câu SQL chuẩn để chạy trong JDBC.

## 24. row_security=off không dùng để bypass

PostgreSQL có tham số:

~~~sql
SHOW row_security;
SET row_security = off;
~~~

Rất dễ hiểu nhầm `row_security=off` là “không áp chính sách, trả mọi hàng”. **Đây là cách hiểu sai.**

Tham số này có tác dụng giúp tránh việc truy vấn bị chính sách lọc **một cách âm thầm**: nếu query sẽ bị ảnh hưởng bởi row security trong ngữ cảnh thích hợp, PostgreSQL có thể **báo lỗi**.

Nó **không cấp BYPASSRLS**, không tước row policies và không thay table ownership.

### 24.1. Thử nghiệm trên lab

~~~sql
SET ROLE rls_demo_alice;

SET row_security = off;

SELECT *
FROM rls_lab.orders;

RESET row_security;
RESET ROLE;
~~~

Đây là phép thử có thể tạo lỗi RLS dự kiến; mục đích **không phải** lấy các hàng tenant 20.

Khi statement gây lỗi bên trong một explicit transaction, transaction có thể ở trạng thái aborted cho đến khi ROLLBACK. Thử riêng trong session lab.

## 25. GUC row_security khác lệnh DISABLE

| Hành động | Đối tượng thay đổi | Ý nghĩa |
|---|---|---|
| `ALTER TABLE ... DISABLE ROW LEVEL SECURITY` | Trạng thái bảng | Tắt việc áp RLS trên bảng |
| `SET row_security=off` | Tham số cấu hình session/context | Báo lỗi khi có tình huống bị row security lọc theo quy tắc |
| `ALTER TABLE ... FORCE ROW LEVEL SECURITY` | Trạng thái owner enforcement của bảng | Buộc owner bình thường chịu policy |

Không dùng một cái như tên khác của cái còn lại.

## 26. Vì sao pg_dump liên quan đến RLS?

Khi sao lưu, thông thường cần **toàn bộ dữ liệu**, không phải các rows mà một runtime tenant role nhìn thấy.

`pg_dump` có hành vi liên quan `row_security=off` để tránh âm thầm xuất một tập thiếu hàng do policy. Nếu backup role chịu RLS mà không có quyền phù hợp để sao lưu toàn bộ, dump có thể báo lỗi.

Một số phiên bản cung cấp tùy chọn:

~~~text
pg_dump --enable-row-security ...
~~~

Nó cho phép dump dữ liệu theo RLS của role, nhưng **có thể chỉ xuất subset**. Đây không tự trở thành **full backup** để khôi phục toàn hệ thống.

### 26.1. FORCE có thể ảnh hưởng backup bằng owner

Khi FORCE, table owner bình thường cũng chịu policy. Một job trước đây dump đầy đủ vì dùng owner có thể giờ thiếu dữ liệu hoặc lỗi.

Hướng xử lý đúng:

1. Xác định mục đích full backup hay tenant-scoped export.
2. Chọn quyền/role backup theo cơ chế quản trị được duyệt.
3. Kiểm tra row counts, restore và tính đầy đủ.
4. Không cấp BYPASSRLS cho runtime app để sửa một lỗi backup.
5. Không DISABLE RLS trên production chỉ để chạy một lần pg_dump.

## 27. RLS kiểm soát những loại thao tác nào?

RLS liên quan các operations:

- `SELECT`: những hàng được đọc.
- `INSERT`: những hàng mới hợp lệ.
- `UPDATE`: những hàng cũ có thể sửa và hàng mới hợp lệ.
- `DELETE`: những hàng cũ có thể xóa.

Policy có thể khác nhau theo command.

Cơ chế cốt lõi:

- `USING (predicate)` thường kiểm soát các hàng **hiện có** mà role được thấy/nhắm thao tác.
- `WITH CHECK (predicate)` kiểm soát dữ liệu **mới sau INSERT/UPDATE**.

Không dùng duy nhất policy SELECT rồi cho rằng tất cả các thao tác ghi tự an toàn theo cùng điều kiện.

## 28. Policy INSERT cho Alice

Trong lab, có thể cho Alice chèn đơn tenant 10:

~~~sql
GRANT INSERT ON rls_lab.orders TO rls_demo_alice;

CREATE POLICY orders_alice_insert
ON rls_lab.orders
FOR INSERT
TO rls_demo_alice
WITH CHECK (tenant_id = 10);
~~~

Hợp lệ:

~~~sql
SET ROLE rls_demo_alice;

BEGIN;

INSERT INTO rls_lab.orders (
    order_id, tenant_id, amount, status
)
VALUES (100, 10, 25.00, 'draft');

ROLLBACK;

RESET ROLE;
~~~

Hàng mới có tenant 10 nên `WITH CHECK` chấp nhận; ROLLBACK giữ lab nguyên trạng.

### 28.1. Thử tạo đơn tenant 20

~~~sql
-- Chạy với role Alice trong lab; dự kiến bị từ chối:
INSERT INTO rls_lab.orders (
    order_id, tenant_id, amount, status
)
VALUES (101, 20, 25.00, 'draft');
~~~

Policy `WITH CHECK (tenant_id=10)` không cho phép tạo hàng tenant 20. Trong transaction có lỗi, phải ROLLBACK trước khi chạy thêm query.

## 29. Policy UPDATE phải xét trước và sau

~~~sql
GRANT UPDATE ON rls_lab.orders TO rls_demo_alice;

CREATE POLICY orders_alice_update
ON rls_lab.orders
FOR UPDATE
TO rls_demo_alice
USING (tenant_id = 10)
WITH CHECK (tenant_id = 10);
~~~

Ý nghĩa:

1. Alice chỉ được nhắm những hàng cũ thuộc tenant 10.
2. Alice không thể cập nhật hàng hợp lệ thành tenant 20.

Ví dụ bị từ chối theo `WITH CHECK`:

~~~sql
UPDATE rls_lab.orders
SET tenant_id = 20
WHERE order_id = 1;
~~~

Khi query UPDATE có `WHERE`, `RETURNING` hoặc biểu thức cần đọc cột, các SELECT privileges/policies liên quan cũng có thể ảnh hưởng; cần test SQL cụ thể mà JDBC/ORM dùng.

## 30. Policy DELETE và TRUNCATE

~~~sql
GRANT DELETE ON rls_lab.orders TO rls_demo_alice;

CREATE POLICY orders_alice_delete
ON rls_lab.orders
FOR DELETE
TO rls_demo_alice
USING (tenant_id = 10);
~~~

Policy DELETE không cho phép Alice nhắm hàng tenant 20 theo cơ chế RLS.

**Nhưng TRUNCATE là thao tác khác**, không bị policy DELETE giới hạn từng hàng. Không cấp TRUNCATE cho role ứng dụng tenant.

## 31. Owner sau FORCE và quyền ghi

Một điểm thường bị bỏ quên: FORCE áp cho owner không chỉ với SELECT, mà còn với những loại thao tác chịu RLS khác.

Trong lab chỉ có policy SELECT cho owner; không có policy INSERT/UPDATE/DELETE dành cho owner. Khi FORCE, các thao tác ghi của owner có thể bị hạn chế/từ chối dù owner sở hữu bảng.

Nếu một job owner phải UPDATE tenant 10:

~~~sql
CREATE POLICY orders_owner_update
ON rls_lab.orders
FOR UPDATE
TO rls_demo_owner
USING (tenant_id = 10)
WITH CHECK (tenant_id = 10);
~~~

Đây là một **permission do policy cấp**, không phải bypass.

Đừng tự tạo `USING(true)` cho owner chỉ để làm code cũ chạy lại mà chưa xem toàn bộ nhu cầu và rủi ro.

## 32. Policy TO PUBLIC có áp cho owner bị FORCE?

Có, khi policy phù hợp. Trong lab ta tạo:

~~~sql
CREATE POLICY orders_tenant_read
ON rls_lab.orders
FOR SELECT TO PUBLIC
USING (...);
~~~

Khi owner bị FORCE, nó được xét theo policy phù hợp với `TO PUBLIC`. Nếu policy có nhánh cho owner, các rows thỏa predicate được phép.

Nếu policy `USING(true)` áp với owner, owner bị FORCE vẫn thấy mọi row **vì policy cho phép**, không phải vì tự động bypass.

Phân biệt này quan trọng khi điều tra “FORCE rồi mà vẫn thấy mọi hàng”.

## 33. PERMISSIVE và RESTRICTIVE

PostgreSQL kết hợp những policies áp dụng theo cơ chế:

- **PERMISSIVE policies** kết hợp bằng logic **OR**.
- **RESTRICTIVE policies** bổ sung điều kiện **AND**.

Ví dụ hình dạng:

~~~sql
CREATE POLICY tenant_visible
ON secure.orders
AS PERMISSIVE FOR SELECT
USING (tenant_id = 10);

CREATE POLICY not_cancelled
ON secure.orders
AS RESTRICTIVE FOR SELECT
USING (status <> 'cancelled');
~~~

Role chịu RLS chỉ thấy những hàng được policy permissive cho phép **và** qua các điều kiện restrictive.

Cần có policy cho phép phù hợp; chỉ tạo restrictive policy không tạo quyền xem hàng từ con số 0.

### 33.1. Một permissive USING(true) có thể mở quá rộng

Nếu thêm policy rộng cho cùng role, phép OR có thể làm điều kiện tenant hẹp trở nên vô nghĩa, trừ khi restrictive policies vẫn giới hạn.

FORCE không đổi quy tắc tổ hợp policies.

## 34. SECURITY DEFINER function và ngoại lệ RLS

Một function:

~~~sql
CREATE FUNCTION secure.some_command(...)
RETURNS ...
LANGUAGE plpgsql
SECURITY DEFINER
AS $$ ... $$;
~~~

có thể thực thi với đặc quyền của **function owner** theo cơ chế PostgreSQL.

Khi function truy cập bảng có RLS:

- Function owner bình thường sở hữu bảng **chưa FORCE** có thể bypass nhờ ownership.
- Nếu cùng owner bình thường nhưng bảng đã FORCE, policies có thể được áp.
- Nếu function owner là superuser hoặc BYPASSRLS role, FORCE **không** vô hiệu hóa ngoại lệ đó.
- Nếu function owner không có quyền phù hợp, function không tự sở hữu mọi đặc quyền chỉ vì SECURITY DEFINER.

### 34.1. SECURITY DEFINER không phải tên khác của BYPASSRLS

Điều cần xét là **đặc quyền thực tế của routine owner**, bảng nguồn và policy context. Không gắn nhãn mọi SECURITY DEFINER function là tự động bypass.

## 35. Rò dữ liệu qua function có owner quá mạnh

Trong lab, giả sử một superuser tạo:

~~~sql
CREATE FUNCTION rls_lab.count_all_orders_admin()
RETURNS BIGINT
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
    SELECT COUNT(*) FROM rls_lab.orders;
$$;
~~~

Nếu owner function là superuser, SELECT bên trong có thể vượt RLS của bảng nguồn.

Nếu cấp:

~~~sql
GRANT EXECUTE
ON FUNCTION rls_lab.count_all_orders_admin()
TO rls_demo_alice;
~~~

Alice có thể biết tổng số đơn toàn hệ thống qua function, dù SELECT trực tiếp bảng chỉ thấy tenant 10.

**Không công bố function này cho runtime tenant role trong production**. Đây là ví dụ giải thích vì sao kiểm thử SELECT trực tiếp không đủ.

### 35.1. Cách thiết kế an toàn

- Không dùng superuser làm function owner trừ nhu cầu quản trị thực sự.
- Giới hạn quyền EXECUTE.
- Dùng owner có ít đặc quyền nhất.
- Kiểm tra policy/tenant trong routine khi cần.
- Audit những routine có khả năng trả dữ liệu xuyên tenant.
- Review toàn bộ SQL động và functions được gọi tiếp.

## 36. search_path trong SECURITY DEFINER

Một function SECURITY DEFINER có thể gọi nhầm object do người dùng không tin cậy tạo nếu dùng tên không schema-qualified và `search_path` sai.

Mẫu tổ chức:

~~~sql
-- Hình dạng minh họa, cần code thực tế thay dấu ba chấm:
CREATE FUNCTION secure.example(...)
RETURNS ...
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = secure, pg_temp
AS $$
BEGIN
    -- Tham chiếu secure.orders với tên đầy đủ.
    ...
END;
$$;
~~~

Các dấu `...` là placeholder, **không chạy nguyên dạng**.

Nguyên tắc:

1. Chỉ dùng trusted schemas.
2. Giữ `pg_temp` ở vị trí thích hợp.
3. Schema-qualify table/function references.
4. Không cho untrusted roles CREATE trong trusted schemas.
5. Dùng parameter binding, không ghép raw SQL.
6. Giới hạn quyền EXECUTE và theo dõi migration.

FORCE không tự sửa một SECURITY DEFINER function có lỗ hổng search_path.

## 37. View mặc định có thể thay security context

Một **view thông thường** có cơ chế kiểm tra quyền/policies trên bảng nguồn liên quan tới **view owner** trong cấu hình mặc định.

Nếu một view được sở hữu bởi role có đặc quyền rất rộng, người gọi view có thể nhận dữ liệu khác với khi truy vấn bảng trực tiếp.

~~~text
Alice SELECT base_table
          |
          v
RLS theo quyền/policy Alice
          |
          v
2 rows

Alice SELECT default_view
          |
          v
Underlying security context liên quan view owner
          |
          v
Có thể khác 2 rows
~~~

Điểm cần kiểm tra: view owner, table owner, FORCE, BYPASSRLS, grants, chính sách hiện có và các functions bên trong view.

## 38. Security-invoker view từ PostgreSQL 15

Trong PostgreSQL 15+, có thể khai báo:

~~~sql
CREATE VIEW rls_lab.v_orders_invoker
WITH (security_invoker = true) AS
SELECT
    order_id,
    tenant_id,
    amount,
    status
FROM rls_lab.orders;
~~~

Với chế độ security invoker, quyền và row policies trên underlying tables được xét theo **caller** theo cơ chế tương ứng.

~~~sql
GRANT SELECT ON rls_lab.v_orders_invoker
TO rls_demo_alice, rls_demo_bob;
~~~

Trong lab, Alice và Bob đã có quyền đọc bảng nguồn nên có thể kiểm tra view theo vai trò của mình.

### 38.1. Khác biệt về GRANT

Với security-invoker view, caller có thể phải có quyền trên **underlying tables**. GRANT SELECT chỉ trên view không nhất thiết đủ.

### 38.2. Không ngăn caller BYPASSRLS

Nếu caller là superuser/BYPASSRLS, security-invoker view dùng context đặc quyền ấy. Không coi security_invoker là cơ chế tước ngoại lệ của một role đặc quyền.

### 38.3. security_barrier không phải security_invoker

`security_barrier` liên quan planner/đánh giá điều kiện trong trường hợp bảo mật. Nó không đồng nghĩa chính sách quyền theo caller và không tự FORCE owner.

## 39. View được tạo bởi superuser: một trường hợp rủi ro

Một view do superuser sở hữu:

~~~sql
-- Chỉ minh họa trong database lab cô lập:
CREATE VIEW rls_lab.v_orders_admin_owned AS
SELECT
    order_id,
    tenant_id,
    amount,
    status
FROM rls_lab.orders;
~~~

Nếu cấp SELECT trên view này cho Alice, có rủi ro dữ liệu bị truy cập theo đặc quyền view owner rộng hơn caller, dù bảng nguồn FORCE.

Không dùng mô hình default view owner là superuser để public dữ liệu multi-tenant mà chưa kiểm thử chính xác. Một thiết kế cần caller policies có thể dùng security-invoker view và grants thích hợp.

## 40. Không chỉ có một lớp execution context

Một query thực tế có thể đi qua:

~~~text
Ứng dụng (login role)
       |
       v
SET ROLE hoặc connection context
       |
       v
View (default owner-based hoặc security-invoker)
       |
       +--> Base table RLS
       |
       +--> SECURITY DEFINER function
       |
       +--> SQL khác / bảng khác
~~~

Mỗi đoạn có thể được xét theo các quy tắc quyền khác nhau. FORCE chỉ tác động **table owner exemption đối với bảng đã FORCE**, không thay mọi execution context trong hệ thống.

## 41. TRUNCATE không bị policy DELETE giới hạn

PostgreSQL không áp row security policies cho `TRUNCATE`.

~~~sql
-- KHÔNG chạy trên dữ liệu cần giữ:
TRUNCATE TABLE rls_lab.orders;
~~~

Một role có quyền TRUNCATE có thể thực hiện thao tác không được lọc từng hàng bởi `USING` của DELETE.

**Bài học:** đừng cấp TRUNCATE cho runtime tenant role. Bảo vệ quyền DDL, quyền TRUNCATE và các administrative routines bằng cơ chế privilege/change control.

FORCE không biến TRUNCATE thành DELETE theo từng hàng.

## 42. REFERENCES và kiểm tra toàn vẹn

RLS cũng không áp cho quyền/thao tác `REFERENCES` theo cách áp cho SELECT/INSERT/UPDATE/DELETE từng hàng.

PostgreSQL phải kiểm tra những ràng buộc integrity như:

- `PRIMARY KEY`.
- `UNIQUE`.
- `FOREIGN KEY`.

Các kiểm tra bên trong có thể **bỏ qua row security** để đảm bảo bảng vẫn tuân constraints.

### 42.1. Vì sao phải nhìn cả hàng bị ẩn?

Nếu một hàng tồn tại nhưng bị policy ẩn, PostgreSQL vẫn phải nhận biết nó khi kiểm tra trùng khóa hoặc tính hợp lệ của foreign key; nếu không, tính toàn vẹn sẽ bị phá.

### 42.2. Side channel qua constraint error

Một INSERT có thể báo duplicate key dù role không SELECT được hàng trùng. Điều này có thể tiết lộ **sự tồn tại** của một giá trị bị ẩn.

Giảm rủi ro bằng:

- Thiết kế khóa và uniqueness scope phù hợp tenant.
- Không công bố raw constraint errors nhạy cảm ra API.
- Dùng IDs khó đoán khi thích hợp.
- Kiểm soát rate limits/abuse.
- Audit các hành vi dò tìm.
- Đánh giá threat model, không chỉ SELECT output.

FORCE không chặn các internal integrity checks cần thiết.

## 43. RLS không che mọi metadata

RLS trên một bảng không tự biến tên bảng, tên column, role metadata hay policy definition thành dữ liệu được lọc theo cùng policy.

Các system catalogs và information_schema có quy tắc privilege/visibility riêng. Không suy rằng “không SELECT được row” cũng có nghĩa user không thấy metadata nào về object.

Nếu schema metadata là dữ liệu cần bảo vệ, phải kiểm tra riêng các quyền và bề mặt thông tin.

## 44. Owner vẫn quản lý cấu trúc và policies

Dù FORCE:

- Table owner vẫn là owner.
- Owner có quyền DDL phù hợp.
- Owner có thể, theo quyền, đổi policies hoặc trạng thái FORCE/ENABLE.
- FORCE không tước quyền sở hữu hay tự phân quyền lại.

Do đó FORCE không phải biện pháp chống lại một application role **vừa là owner vừa có khả năng sửa RLS** bị tấn công.

Kiến trúc thường phù hợp hơn:

~~~text
Migration owner (NOLOGIN nếu phù hợp)
    - Sở hữu bảng, quản lý schema/policies

Application role
    - Không sở hữu bảng
    - Có DML tối thiểu
    - Chịu RLS

Backup/maintenance role
    - Dùng trong workflow quản trị tách biệt
    - Có quyền đầy đủ theo nhu cầu và audit

Security admin
    - Quản trị role đặc quyền, kiểm soát migration
~~~

## 45. Multi-tenant với một DB role dùng chung

Trong backend Java, connection pool có thể dùng một login như `app_service` cho mọi người dùng cuối. Khi đó `current_user` thường luôn là cùng một role.

Policy kiểu:

~~~sql
USING (current_user = 'tenant_10_role')
~~~

không đủ để phân biệt các tenant nếu mọi HTTP request dùng một database role.

Một kiểu policy khác dựa vào context:

~~~sql
-- Hình dạng minh họa, KHÔNG tự bảo đảm an toàn:
USING (
    tenant_id = NULLIF(
        current_setting('app.tenant_id', true),
        ''
    )::INTEGER
)
~~~

### 45.1. GUC không phải nguồn danh tính chống giả mạo tự thân

Nếu session role có thể tự `SET app.tenant_id` và có SQL injection hay đường thực thi SQL không tin cậy, attacker có thể cố thay context.

Cần bảo đảm application xác thực tenant thật, đặt context có kiểm soát, không cho client chạy SQL tùy ý, và kiểm thử policies trong threat model tương ứng.

### 45.2. Connection pooling và context leak

Nếu tenant context được đặt trên một connection lâu dài rồi request tiếp theo dùng lại connection mà không reset, có nguy cơ lẫn dữ liệu.

Thường nên sử dụng context ở **transaction scope**, kiểm tra cấu hình pool, commit/rollback và thử reuse connection. FORCE không giải quyết context leak.

## 46. INSERT ... ON CONFLICT DO UPDATE

UPSERT có thể kết hợp việc INSERT hàng mới và UPDATE hàng đã tồn tại:

~~~sql
INSERT INTO rls_lab.orders (
    order_id, tenant_id, amount, status
)
VALUES (1, 10, 120.00, 'paid')
ON CONFLICT (order_id)
DO UPDATE SET amount = EXCLUDED.amount;
~~~

Khi role chịu RLS, cần xét policies INSERT, UPDATE, `WITH CHECK` và các SELECT privileges/policies liên quan biểu thức đọc.

Không mặc định UPSERT được phép chỉ vì role có INSERT policy. Conflict với một hàng mà role không được thấy có thể gây lỗi hoặc hành vi không giống “không có hàng”.

### 46.1. Không dùng UPSERT làm cơ chế dò dữ liệu tenant khác

Nếu khóa chung toàn bảng, conflict hoặc constraint errors có thể tiết lộ một khóa đã tồn tại. Phải xử lý API error response và thiết kế identity phù hợp.

## 47. MERGE và các hành vi phụ thuộc phiên bản

Những phiên bản PostgreSQL khác nhau có thể có thay đổi chi tiết liên quan MERGE, RLS và execution paths. Đừng sao chép giả định từ Oracle hoặc SQL Server.

Với một phiên bản server cụ thể, cần kiểm tra:

- Có hỗ trợ MERGE với RLS trong trường hợp đó không?
- Những policy nào áp cho các nhánh INSERT/UPDATE/DELETE?
- Hàng bị ẩn được xử lý thế nào?
- Những quyền SELECT có liên quan không?
- Có trigger/constraint đặc biệt không?

Bài này tập trung vào FORCE và bypass; nguyên tắc xuyên suốt là **không mặc định FORCE khiến mọi DML phức tạp có semantics giống SELECT đơn giản**.

## 48. Partitioned tables và direct partition access

Với partitioned table, việc truy cập qua parent và truy cập trực tiếp từng partition có thể trải qua quyền và policy của quan hệ tương ứng.

Cần kiểm tra:

1. Truy vấn parent.
2. Truy vấn trực tiếp child partition.
3. Owner của parent/child.
4. Policies và FORCE trên những đối tượng liên quan.
5. Quyền SELECT/INSERT/UPDATE trực tiếp child.
6. Chuyển hàng giữa partitions.
7. Views hoặc functions truy cập partitions.

FORCE trên parent **không đủ để suy rằng mọi đường truy cập trực tiếp các partitions đã có cùng kết quả**. Thiết kế và thử trên PostgreSQL version thực tế.

## 49. SELECT FOR UPDATE và quyền đọc/khóa

Ví dụ:

~~~sql
SELECT *
FROM rls_lab.orders
WHERE tenant_id = 10
FOR UPDATE;
~~~

Câu query này có yêu cầu quyền và row-locking semantics riêng. Không suy rằng FOR UPDATE bỏ qua RLS để khóa những hàng caller không được phép truy cập.

RLS cũng không cách ly hoàn toàn tài nguyên hệ thống: tenant A và B có thể gây contention trên cùng bảng/index/locks. RLS chủ yếu là **row access policy**, không phải resource isolation.

## 50. EXPLAIN có thể gây hiểu nhầm khi test RLS

~~~sql
EXPLAIN
SELECT *
FROM rls_lab.orders;
~~~

Planner có thể kết hợp policy expressions trong plan theo quy tắc tối ưu/bảo mật.

Nhưng:

- Plan của superuser có thể khác plan của Alice.
- Không phải mọi policy đều hiện như một dòng filter dễ nhận biết.
- Query trả 0 rows có thể vì RLS, WHERE hoặc dữ liệu thực sự trống.
- `EXPLAIN ANALYZE` thực thi query; với DML, nó có side effects thật.

Cần test **kết quả và quyền bằng đúng role**, kết hợp quan sát metadata. Không coi một plan do admin xem là bằng chứng cuối cùng.

## 51. Kiểm tra cấu hình RLS cho nhiều bảng

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    pg_get_userbyid(c.relowner) AS owner_name,
    c.relrowsecurity AS enabled,
    c.relforcerowsecurity AS forced
FROM pg_class AS c
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE n.nspname = 'rls_lab'
  AND c.relkind IN ('r', 'p')
ORDER BY n.nspname, c.relname;
~~~

`relkind='r'` thường chỉ regular table; `'p'` chỉ partitioned table.

Một báo cáo posture đầy đủ cần kết hợp:

- Bảng nào RLS disabled.
- Bảng nào FORCE.
- Table owners.
- Role nào BYPASSRLS/superuser.
- Policy roles/commands/predicates.
- Grants và runtime connection identity.
- Views/SECURITY DEFINER functions.
- Partitions/direct access.
- Backup/export roles.

## 52. Ma trận test chức năng trong staging

| Kịch bản | Kết quả cần xác nhận |
|---|---|
| Alice SELECT trực tiếp | Chỉ tenant 10 |
| Bob SELECT trực tiếp | Chỉ tenant 20 |
| Owner ENABLE + NO FORCE | Bypass theo ownership |
| Owner ENABLE + FORCE | Chịu owner policy |
| Role không SELECT | Permission denied |
| Alice INSERT tenant 10 | Chấp nhận khi INSERT policy/GRANT hợp lệ |
| Alice INSERT tenant 20 | Từ chối |
| Alice UPDATE hàng tenant 20 | Không được target |
| Alice đổi tenant_id 10 → 20 | WITH CHECK từ chối |
| Alice DELETE tenant 20 | Không xóa được |
| View mặc định owner đặc quyền | Không vô tình trả hàng xuyên tenant |
| Security-invoker view | Xét quyền theo caller như thiết kế |
| SECURITY DEFINER function | Không có đường lộ dữ liệu |
| row_security=off | Không biến thành bypass |
| Superuser/BYPASSRLS | Hiểu rõ ngoại lệ FORCE |
| Backup role | Full dump hoặc partial export đúng mục đích |
| TRUNCATE | Không cấp quyền cho app tenant |
| Partition direct access | Không bỏ qua ranh giới đã thiết kế |

Cần test cả **positive cases** (được phép) lẫn **negative cases** (không được phép). Không chỉ test Alice thấy đúng hai hàng mà bỏ qua việc Alice có thể gọi một view đặc quyền để thấy tất cả.

## 53. Checklist trước khi bật FORCE ở production

1. Xác định bảng và table owner thực tế.
2. Xem `relrowsecurity` và `relforcerowsecurity`.
3. Liệt kê chính sách SELECT/INSERT/UPDATE/DELETE/ALL.
4. Xác định permissive/restrictive policies kết hợp thế nào.
5. Kiểm tra role nào là superuser/BYPASSRLS.
6. Kiểm tra table/schema privileges của runtime roles.
7. Liệt kê các truy vấn đang chạy bằng owner.
8. Kiểm tra views và SECURITY DEFINER functions.
9. Xem backup, ETL, maintenance jobs có dùng owner không.
10. Kiểm thử policy cho owner trước/sau FORCE.
11. Xác minh các đường partition/direct child access.
12. Kiểm tra TRUNCATE/REFERENCES và constraint side channels.
13. Lập kế hoạch DDL locks, timeouts, migration và rollback.
14. Có staging test với role app thật.
15. Có monitoring để nhận biết lỗi permission/RLS sau deploy.

**Không thay đổi FORCE chỉ bằng cảm giác**: nó có thể làm ứng dụng mất quyền đọc/ghi dù dữ liệu không đổi.

## 54. Migration FORCE có transaction

~~~sql
BEGIN;

SET LOCAL lock_timeout = '3s';
SET LOCAL statement_timeout = '30s';

ALTER TABLE rls_lab.orders
ENABLE ROW LEVEL SECURITY;

ALTER TABLE rls_lab.orders
FORCE ROW LEVEL SECURITY;

COMMIT;
~~~

Đây là ví dụ **chỉ dành cho lab**. PostgreSQL có hỗ trợ transactional DDL cho những thao tác thích hợp, nhưng DDL vẫn cần locks.

### 54.1. Không để transaction DDL idle

Transaction mở sau DDL có thể giữ locks khiến query khác chờ. Chuẩn bị thay đổi trước, review và kết thúc transaction nhanh theo quy trình được duyệt.

### 54.2. Sau COMMIT phải có migration bù

Không thể gửi ROLLBACK để hoàn tác một transaction đã COMMIT. Nếu cần điều chỉnh, thực hiện migration mới có review rủi ro lộ dữ liệu; không mặc định NO FORCE là rollback bảo mật an toàn.

## 55. Tình huống: owner đọc được hết dù đã FORCE

Nguyên nhân có thể:

- RLS đang DISABLE.
- Role thực thi là superuser/BYPASSRLS.
- Có policy permissive `USING(true)` hoặc policy khác cho phép hết.
- Query đi qua view/routine có security context đặc quyền.
- Bạn kiểm tra nhầm schema/table.
- Runtime session không thực sự là owner role bạn nghĩ.

Các bước kiểm tra:

~~~sql
SELECT current_user, session_user;

SELECT
    relrowsecurity,
    relforcerowsecurity
FROM pg_class
WHERE oid = 'rls_lab.orders'::regclass;

SELECT policyname, cmd, qual, with_check
FROM pg_policies
WHERE schemaname='rls_lab'
  AND tablename='orders';
~~~

**FORCE nghĩa owner không còn miễn policy**, không đồng nghĩa kết quả chắc chắn ít hàng hơn nếu policy cho phép toàn bộ.

## 56. Tình huống: owner thấy 0 rows sau FORCE

Nguyên nhân có thể:

- Không có SELECT policy cho owner.
- Policy TO role khác.
- Tenant context thiếu.
- Một restrictive policy loại hết hàng.
- Biểu thức predicate sai.
- Execution role khác dự kiến.

Không sửa bằng DISABLE RLS trên production; hãy xác định owner job thực sự cần truy cập phạm vi nào rồi cấp policy hay đường quản trị phù hợp.

## 57. Tình huống: export/backup báo lỗi sau FORCE

Giả sử job dùng table owner để dump dữ liệu. Trước FORCE, owner bypass; sau FORCE, owner chịu policy.

Nếu công cụ backup muốn tránh xuất thiếu hàng, nó có thể báo lỗi thay vì dump subset. Hãy:

1. Xác định full backup hay export một tenant.
2. Kiểm tra role/privileges và cờ FORCE.
3. Dùng đường backup được quản trị riêng.
4. Kiểm thử restore/row counts.
5. Không dùng app role BYPASSRLS hoặc DISABLE RLS để chữa cháy.

## 58. Tình huống: UPDATE trả 0 hàng dù ID tồn tại

~~~sql
UPDATE rls_lab.orders
SET amount = 250.00
WHERE order_id = 3;
~~~

Nếu thực hiện bằng Alice với UPDATE policy tenant 10, order 3 thuộc tenant 20 có thể không được nhắm tới; row count = 0.

Điều này khác với `WITH CHECK` error khi một hàng hiện tại được phép cập nhật nhưng giá trị **sau UPDATE** không hợp lệ.

Một HTTP API nên phân biệt “không tìm thấy/không được phép” theo policy tiết lộ thông tin đã định, thay vì trả raw lỗi có thể cho attacker đoán dữ liệu tenant khác.

## 59. Các sai lầm thường gặp

### 59.1. Chỉ ENABLE RLS rồi tin owner chịu policy

Table owner bypass mặc định nếu chưa FORCE.

### 59.2. Nghĩ FORCE chặn superuser/BYPASSRLS

Không. Đây là ngoại lệ vượt ra ngoài table-owner exemption.

### 59.3. Test bằng postgres rồi kết luận policy không hoạt động

Superuser có thể bypass. Hãy test dưới runtime role.

### 59.4. Dùng DISABLE để khắc phục thiếu policy

Có thể lộ mọi hàng cho role có SELECT.

### 59.5. Tưởng NO FORCE và DISABLE giống nhau

NO FORCE chỉ khôi phục owner exemption.

### 59.6. GRANT SELECT nhưng không tạo policy

Với RLS enabled, role bình thường có thể thấy 0 hàng.

### 59.7. Có policy nhưng thiếu GRANT SELECT

Query có thể permission denied.

### 59.8. Cấp BYPASSRLS cho service account

Mất lớp bảo vệ chống query thiếu điều kiện tenant.

### 59.9. SET row_security=off để bypass

GUC này không cấp đặc quyền; có thể báo lỗi.

### 59.10. Tưởng FORCE tự cấp policy cho owner

Nếu policy không có nhánh owner, owner có thể thấy 0 hàng.

### 59.11. Thêm permissive USING(true) ngoài ý định

Có thể làm policy tenant hẹp mất tác dụng.

### 59.12. Chỉ có restrictive policy

Chưa có policy permissive cho phép ban đầu.

### 59.13. Không viết WITH CHECK cho cập nhật tenant_id

Có thể thiết kế sai kiểm tra giá trị mới.

### 59.14. View owner đặc quyền không được kiểm thử

Truy vấn qua view có thể dùng context rộng hơn SELECT bảng trực tiếp.

### 59.15. SECURITY DEFINER superuser dùng cho API

Có thể làm lộ dữ liệu dù bảng FORCE.

### 59.16. Không bảo vệ search_path

Rủi ro resolve object do role không tin cậy tạo.

### 59.17. Nghĩ TRUNCATE chịu DELETE policy

TRUNCATE không bị lọc từng hàng bằng RLS.

### 59.18. Nghĩ UNIQUE/FK checks chỉ xem hàng role thấy

Integrity checks có thể bypass RLS và tạo side channel.

### 59.19. Dùng GUC tenant có thể tự sửa mà không kiểm soát

Có thể cho client chọn tenant khác qua SQL injection/context leak.

### 59.20. Không reset context khi connection pool reuse

Có thể rò dữ liệu xuyên request.

### 59.21. Chỉ nhìn relforcerowsecurity=true

RLS có thể vẫn DISABLE.

### 59.22. Không kiểm tra partitions/direct child access

Có thể có đường truy cập khác parent policy.

### 59.23. Sao lưu bằng owner FORCE và tưởng đó là full backup

Owner có thể chịu policy và chỉ thấy subset.

### 59.24. Dùng FORCE như biện pháp chống table owner DDL

Owner có thể đổi cấu hình theo quyền quản trị của mình.

## 60. Nguyên tắc least privilege

Một mô hình thực dụng:

| Loại role | Quyền hợp lý |
|---|---|
| Runtime app | Chỉ USAGE và các DML cần thiết, không sở hữu bảng |
| Table/migration owner | Quản lý schema, không làm login cho request |
| Reporting | SELECT giới hạn theo contract |
| Backup | Đường truy cập đầy đủ được quản trị và audit |
| Security admin | Quản trị policies, role privileges, không dùng cho request |

Không xây một tài khoản “all-purpose” vừa là owner, vừa superuser/BYPASSRLS, vừa dùng bởi ứng dụng và job backup.

### 60.1. FORCE là defense-in-depth, không phải biên an toàn duy nhất

Ngay cả khi FORCE, cần đảm bảo runtime role không thể tự DISABLE RLS, không truy cập view đặc quyền ngoài contract và không nhận quyền vượt hàng từ SECURITY DEFINER routine.

## 61. Quy trình điều tra RLS bị bỏ qua

~~~text
Query trả nhiều hàng hơn dự kiến
                 |
                 v
Xác định current_user/session_user
                 |
                 v
Kiểm tra role rolsuper/rolbypassrls
                 |
                 v
Kiểm tra table owner và FORCE/ENABLE flags
                 |
                 v
Kiểm tra pg_policies + GRANT
                 |
                 v
Query qua base table hay view/function?
                 |
                 v
Kiểm tra view owner/security_invoker/
SECURITY DEFINER/search_path
                 |
                 v
Kiểm tra runtime tenant context và pool
                 |
                 v
Thử lại dưới role ứng dụng trong staging
~~~

Đừng chỉ thêm `WHERE tenant_id` ở endpoint đang lỗi; cần xác định vì sao lớp bảo vệ cơ sở dữ liệu đã không hoạt động như mong đợi.

## 62. Bài tập thực hành

### Bài 1 — ENABLE vs FORCE

Giải thích sự khác nhau giữa `ENABLE ROW LEVEL SECURITY` và `FORCE ROW LEVEL SECURITY`.

**Gợi ý:** ENABLE bật policy enforcement; FORCE đưa owner bình thường vào phạm vi policy.

### Bài 2 — Bypass của owner

Khi RLS enabled nhưng chưa FORCE, owner nhìn thấy gì trong lab?

**Gợi ý:** cả bốn orders.

### Bài 3 — FORCE

Sau FORCE, owner trong lab thấy những order_id nào?

**Gợi ý:** 1, 2 theo owner policy.

### Bài 4 — Superuser

Superuser có bị FORCE bắt chịu policy không?

**Gợi ý:** không.

### Bài 5 — BYPASSRLS

BYPASSRLS là table grant hay role attribute?

**Gợi ý:** role attribute.

### Bài 6 — BYPASSRLS và SELECT

Role có BYPASSRLS nhưng thiếu quyền bảng, có tự được SELECT không?

**Gợi ý:** không tự được cấp mọi privilege.

### Bài 7 — NO FORCE

NO FORCE có tắt RLS cho Alice không?

**Gợi ý:** không, chỉ trả ngoại lệ owner.

### Bài 8 — DISABLE

Alice đã có GRANT SELECT. DISABLE RLS làm thay đổi kết quả thế nào?

**Gợi ý:** không còn lọc theo row policy.

### Bài 9 — Hai cờ

Ý nghĩa của relrowsecurity=true và relforcerowsecurity=true?

**Gợi ý:** RLS đang bật và FORCE owner.

### Bài 10 — Force flag khi disabled

relforcerowsecurity=true nhưng relrowsecurity=false có lọc không?

**Gợi ý:** không.

### Bài 11 — Default deny

Một role chịu RLS mà không có policy SELECT sẽ nhìn thấy bao nhiêu hàng?

**Gợi ý:** thường 0.

### Bài 12 — GRANT

Có policy SELECT nhưng thiếu GRANT SELECT gây điều gì?

**Gợi ý:** permission denied.

### Bài 13 — Xem role attributes

Viết truy vấn xem rolsuper và rolbypassrls.

**Gợi ý:** pg_roles.

### Bài 14 — Xem policies

Viết query xem qual và with_check của một bảng.

**Gợi ý:** pg_policies.

### Bài 15 — Current user

Vì sao session_user và current_user có thể khác nhau?

**Gợi ý:** SET ROLE/SECURITY DEFINER.

### Bài 16 — row_security=off

Đây có phải lệnh bypass RLS không?

**Gợi ý:** không.

### Bài 17 — pg_dump

Tại sao một owner bình thường trên bảng FORCE có thể không dump đầy đủ?

**Gợi ý:** owner chịu policy.

### Bài 18 — Partial export

`pg_dump --enable-row-security` có chắc tạo full backup không?

**Gợi ý:** không.

### Bài 19 — INSERT WITH CHECK

WITH CHECK kiểm tra cái gì trong INSERT?

**Gợi ý:** hàng mới.

### Bài 20 — UPDATE

Tại sao policy UPDATE nên có USING và WITH CHECK?

**Gợi ý:** kiểm tra old target và new values.

### Bài 21 — DELETE

DELETE policy có ngăn role thực hiện TRUNCATE khi được GRANT TRUNCATE không?

**Gợi ý:** không.

### Bài 22 — PUBLIC

`TO PUBLIC` có tự cho phép xem tất cả các hàng không?

**Gợi ý:** không, còn predicate và quyền bảng.

### Bài 23 — Permissive

Hai permissive policies có quan hệ OR hay AND?

**Gợi ý:** OR.

### Bài 24 — Restrictive

Một restrictive policy có tự tạo quyền xem hàng khi không có permissive policy không?

**Gợi ý:** không.

### Bài 25 — Security definer

Function owner superuser có thể bypass FORCE khi đọc bảng không?

**Gợi ý:** có.

### Bài 26 — Function owner bình thường

FORCE có thể thay kết quả của SECURITY DEFINER function do table owner bình thường sở hữu không?

**Gợi ý:** có vì owner giờ chịu policy.

### Bài 27 — View

Vì sao SELECT từ default view có thể khác SELECT trực tiếp bảng?

**Gợi ý:** quyền/policy trên bảng nguồn được xét trong context liên quan view owner.

### Bài 28 — security_invoker

Nó dùng quyền/policies của ai cho underlying tables?

**Gợi ý:** caller.

### Bài 29 — security_barrier

Nó có đồng nghĩa security_invoker không?

**Gợi ý:** không.

### Bài 30 — TRUNCATE

Tại sao không cấp TRUNCATE cho app tenant?

**Gợi ý:** không có row filter của DELETE policy.

### Bài 31 — Constraints

UNIQUE/FK checks có phải chỉ nhìn những hàng visible qua SELECT RLS không?

**Gợi ý:** không, phải giữ toàn vẹn dữ liệu.

### Bài 32 — Constraint error side channel

Một duplicate key error có thể làm lộ điều gì?

**Gợi ý:** sự tồn tại của một khóa bị ẩn.

### Bài 33 — Một shared DB role

Tại sao `current_user` không phân biệt được người dùng cuối khi app pool chung một login?

**Gợi ý:** execution role giống nhau.

### Bài 34 — GUC tenant

Một context tenant có thể tự SET bởi caller chưa tin cậy có an toàn không?

**Gợi ý:** không.

### Bài 35 — Connection pool

Vì sao cần reset tenant context ở transaction boundary?

**Gợi ý:** tránh lẫn request khác.

### Bài 36 — Partitions

FORCE parent có tự chứng minh mọi direct child access an toàn không?

**Gợi ý:** không, test từng đường.

### Bài 37 — UPSERT

Tại sao UPSERT có thể cần cả INSERT và UPDATE policies?

**Gợi ý:** nhánh ON CONFLICT.

### Bài 38 — Owner DDL

FORCE có làm owner mất khả năng thay cấu hình bảng không?

**Gợi ý:** không.

### Bài 39 — Test matrix

Liệt kê ít nhất ba negative tests ngoài SELECT.

**Gợi ý:** INSERT tenant khác, UPDATE tenant_id, DELETE hàng tenant khác.

### Bài 40 — Migration

Viết checklist ít nhất tám điều trước khi FORCE một bảng production.

**Gợi ý:** roles, bypass, policies, owner, privileges, views, jobs, backup, staging và rollback.

## 63. Câu hỏi thường gặp

### FORCE ROW LEVEL SECURITY có bắt buộc tất cả role tuân policy không?

**Không.** Nó buộc table owner bình thường tuân policy. Superuser/BYPASSRLS role vẫn được miễn.

### FORCE có tự bật RLS không?

Không. Cần `ENABLE ROW LEVEL SECURITY`.

### FORCE có tự tạo policy cho owner không?

Không. Nếu thiếu policy phù hợp, owner có thể thấy 0 rows hoặc bị từ chối DML.

### Owner bình thường có nên dùng làm role ứng dụng không?

Thường không. Nên tách migration owner và runtime roles. FORCE có thể là defense-in-depth nhưng không tước quyền DDL của owner.

### NO FORCE có giống DISABLE không?

Không. NO FORCE trả ngoại lệ owner; DISABLE tắt row policy enforcement trên bảng.

### row_security=off có cho xem mọi tenant không?

Không. Nó không bypass; có thể gây lỗi khi query chịu RLS lọc.

### Một role BYPASSRLS có tự có GRANT SELECT không?

Không. Đây là role attribute bỏ qua lớp RLS, không tự cấp toàn bộ table privileges.

### SECURITY DEFINER có tự bypass RLS không?

Tùy **function owner** và đặc quyền tại bảng nguồn. Nếu owner là superuser/BYPASSRLS thì có thể bypass ngay cả khi FORCE.

### Default view có thể trả hàng mà caller không thấy khi SELECT trực tiếp không?

Có thể, tùy view owner/security context. Kiểm tra security_invoker, grants và policies.

### security_invoker có từ PostgreSQL nào?

View option `security_invoker` được hỗ trợ từ PostgreSQL 15.

### TRUNCATE có bị policy DELETE giới hạn không?

Không. Phải bảo vệ bằng quyền TRUNCATE/DDL và quy trình vận hành.

### FK/UNIQUE checks có bị RLS làm thiếu dữ liệu kiểm tra không?

Không. Database phải bảo vệ toàn vẹn, vì vậy có thể tồn tại side channels qua constraint errors.

### ENABLE + FORCE có đủ an toàn cho multi-tenant không?

Chưa. Cần kiểm tra runtime role, owner privileges, policy predicates, views, functions, tenant context, backup, partitions, connection pooling và đường bypass khác.

## 64. Tổng kết

Các lệnh cần nhớ:

~~~sql
-- Bật policy enforcement.
ALTER TABLE rls_lab.orders
ENABLE ROW LEVEL SECURITY;

-- Buộc table owner bình thường chịu policy.
ALTER TABLE rls_lab.orders
FORCE ROW LEVEL SECURITY;

-- Khôi phục ngoại lệ owner.
ALTER TABLE rls_lab.orders
NO FORCE ROW LEVEL SECURITY;

-- Tắt RLS toàn bảng (rủi ro nếu role có GRANT rộng).
ALTER TABLE rls_lab.orders
DISABLE ROW LEVEL SECURITY;

-- Xem execution role.
SELECT session_user, current_user;

-- Xem trạng thái bảng.
SELECT
    relrowsecurity,
    relforcerowsecurity
FROM pg_class
WHERE oid = 'rls_lab.orders'::regclass;

-- Xem policies.
SELECT *
FROM pg_policies
WHERE schemaname = 'rls_lab'
  AND tablename = 'orders';

-- Xem các role đặc quyền.
SELECT rolname, rolsuper, rolbypassrls
FROM pg_roles;
~~~

**Những nguyên tắc quan trọng:**

1. RLS enabled **không đồng nghĩa mọi role đều bị lọc**.
2. Owner bình thường **bypass theo mặc định**.
3. FORCE buộc owner bình thường **chịu policy** khi RLS enabled.
4. Superuser và BYPASSRLS **vẫn bypass**, bất kể FORCE.
5. FORCE không tự tạo policy hoặc mở quyền đọc/ghi.
6. NO FORCE khác DISABLE: một cái chỉ đổi owner exemption, một cái tắt row filtering.
7. `row_security=off` **không** là công tắc bypass; nó giúp phát hiện export/query bị policy lọc.
8. GRANT và RLS là hai lớp quyền độc lập nhưng bổ sung.
9. USING kiểm soát hàng hiện có; WITH CHECK kiểm soát hàng sau INSERT/UPDATE.
10. View owner và SECURITY DEFINER có thể làm query dùng context đặc quyền khác caller.
11. security_invoker view trên PostgreSQL 15+ giúp xét underlying rights/policies theo caller.
12. TRUNCATE không chịu row policy như DELETE; integrity checks có thể bypass RLS.
13. Table owner vẫn có năng lực DDL; cần tách owner khỏi runtime application role.
14. Backup, partitions, UPSERT và connection pooling là các đường truy cập phải xem riêng.
15. Phải kiểm chứng cả hành vi được phép lẫn bị từ chối **dưới đúng execution role**.

Sơ đồ quyết định:

~~~text
Role thực thi truy vấn
         |
         v
Có các quyền SQL cần thiết?
    /                \
  Không               Có
    |                  |
 Permission denied    v
               RLS đang ENABLE?
                 /       \
               Không      Có
                 |         |
           Không áp RLS     v
                       Superuser/BYPASSRLS?
                         /        \
                        Có        Không
                         |           |
                      Bypass         v
                              Table owner?
                                /       \
                              Không      Có
                                |         |
                              Áp RLS    FORCE?
                                        /   \
                                      Có    Không
                                       |      |
                                     Áp RLS  Bypass
                                       |
                                       v
                               Policies phù hợp
                                       |
                                       v
                              Cho phép/lọc/từ chối
~~~

**Kết luận:** `FORCE ROW LEVEL SECURITY` giải quyết đúng một ngoại lệ quan trọng: **table owner bình thường được miễn RLS theo mặc định**. Nó không tước đặc quyền của superuser/BYPASSRLS và không thay thế kiến trúc bảo mật. Để bảo vệ dữ liệu theo hàng đáng tin cậy, hãy kết hợp policies chính xác, GRANT tối thiểu, tách owner/runtime roles, kiểm thử view và SECURITY DEFINER, quản lý tenant context và xác minh các đường backup, TRUNCATE và integrity checks.
