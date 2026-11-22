# Chính sách bảo vệ hàng, cột và view theo khả năng hỗ trợ

Một ứng dụng quản lý khách hàng có thể lưu tên, email, mã số thuế và lịch sử đơn hàng trong cùng database. Nhân viên hỗ trợ cần xem tên và email của khách mình phụ trách; bộ phận báo cáo chỉ cần tên và tổng tiền; mỗi khách hàng chỉ được xem đơn của tenant mình.

Nếu chỉ cấp SELECT trên toàn bộ bảng, người dùng có thể nhìn thấy nhiều hàng và cột hơn nhiệm vụ yêu cầu. Nếu chỉ tạo view lọc dữ liệu nhưng vẫn để người dùng đọc bảng gốc, lớp lọc đó có thể bị bỏ qua. Vì vậy, bảo vệ dữ liệu cần phối hợp nhiều lớp:

- **Quyền đối tượng:** ai được SELECT, INSERT, UPDATE, DELETE hoặc EXECUTE.
- **Quyền cột:** người dùng được đọc hoặc sửa những cột nào.
- **Chính sách hàng:** người dùng được nhìn thấy hoặc thay đổi những hàng nào.
- **View:** công bố một giao diện dữ liệu đã chọn cột, đổi tên, tính toán hoặc lọc hàng.
- **Danh tính và ngữ cảnh:** database xác định người gọi bằng role, session context hoặc application context.

Bài **“Chính sách bảo vệ hàng, cột và view theo khả năng hỗ trợ”** thuộc chương **Quyền và SQL an toàn**, module **Database SQL**. Phần thực hành chính dùng **PostgreSQL 15+** để giải thích GRANT, column privileges, Row-Level Security (RLS), USING, WITH CHECK, FORCE ROW LEVEL SECURITY, security_invoker và security_barrier. Phần sau đối chiếu **SQL Server RLS, MySQL views/column grants, Oracle VPD/DBMS_RLS và giới hạn bảo mật của SQLite**.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt quyền trên database/schema/table/column/view/routine và chính sách lọc hàng.
2. Áp dụng nguyên tắc **least privilege**: chỉ cấp quyền cần thiết cho từng vai trò.
3. Dùng GRANT/REVOKE để giới hạn cột SELECT hoặc UPDATE khi hệ quản trị hỗ trợ.
4. Tạo view công bố tập cột an toàn và hiểu vì sao view không tự động là ranh giới bảo mật.
5. Thiết lập PostgreSQL RLS bằng CREATE POLICY, USING và WITH CHECK.
6. Phân biệt policy cho hàng hiện có với kiểm tra hàng mới khi INSERT/UPDATE.
7. Hiểu FORCE ROW LEVEL SECURITY, table owner, superuser và BYPASSRLS.
8. Phân biệt quyền của view owner và người gọi qua security_invoker.
9. Giải thích security_barrier bảo vệ thứ tự đánh giá predicate ở mức nào.
10. Kiểm thử quyền bằng đúng role ứng dụng, bao gồm truy cập hàng/cột bị cấm.
11. So sánh RLS, column privileges, views, dynamic masking và VPD theo từng RDBMS.
12. Tránh dùng biến session do người dùng tự đặt như bằng chứng xác thực tenant.
13. Thiết kế quyền cho ứng dụng đa tenant, connection pool và SQL động an toàn.

## 2. Bảo vệ dữ liệu có nhiều lớp

Giả sử bảng customers có customer_id, tenant_id, display_name, email, tax_id và internal_note. Bảng orders có order_id, tenant_id, customer_id, amount, status và internal_note.

Có ba câu hỏi độc lập:

1. **Hàng nào?** Người dùng tenant 10 chỉ được xem hàng tenant 10.
2. **Cột nào?** Người dùng công khai chỉ thấy display_name, không thấy email hoặc tax_id.
3. **Qua giao diện nào?** Ứng dụng đọc view đã được thiết kế thay vì bảng gốc có nhiều thông tin nội bộ.

~~~text
              Danh tính / vai trò
                      |
                      v
                Quyền đối tượng
                SELECT / UPDATE
                      |
                      v
                  Quyền cột
             customer_id, display_name
                      |
                      v
                Chính sách hàng
               tenant_id = 10
                      |
                      v
                    VIEW
          chỉ công bố dữ liệu cần thiết
                      |
                      v
                  Ứng dụng
~~~

Đây là cách nhìn theo lớp. Trong từng hệ quản trị, thứ tự và cơ chế kiểm tra quyền có chi tiết riêng; không phải mọi database đều hỗ trợ đầy đủ từng lớp.

### 2.1. Quyền và chính sách không thay thế nhau

| Cơ chế | Câu hỏi được giải quyết | Ví dụ |
| --- | --- | --- |
| GRANT SELECT | Role có được đọc đối tượng không? | Cho report_reader đọc bảng báo cáo |
| Column privilege | Role được đọc/sửa cột nào? | Chỉ đọc customer_id, display_name |
| Row-Level Security | Role được nhìn thấy hoặc tác động hàng nào? | tenant_id khớp tenant của phiên |
| View | Công bố giao diện dữ liệu nào? | Ẩn tax_id và internal_note |
| Data masking/redaction | Giá trị hiển thị được che thế nào? | Hiển thị email ở dạng đã che |
| Transaction/constraint | Dữ liệu ghi vào có hợp lệ không? | FK, CHECK, UNIQUE |

**Masking không tự đồng nghĩa với quyền truy cập**, và **view không tự thay thế RLS**. Cần hiểu cách hệ quản trị kiểm tra quyền trên bảng nguồn khi đọc view.

## 3. Least privilege và các loại quyền

Nguyên tắc **least privilege (đặc quyền tối thiểu)**: một vai trò chỉ nhận quyền cần cho công việc.

| Vai trò | Quyền phù hợp |
| --- | --- |
| customer_reader | Đọc view công khai, chỉ hàng của tenant mình |
| support_agent | Đọc tên/email và cập nhật một số trường hỗ trợ |
| finance_reader | Đọc view tổng hợp tài chính đã công bố |
| app_writer | Gọi routine nghiệp vụ để cập nhật đơn |
| migration_owner | Quản lý schema/DDL, không dùng làm tài khoản ứng dụng |
| audit_reader | Đọc dữ liệu audit theo phạm vi được phép |

Không cấp SUPERUSER, db_owner, quyền ALTER schema hoặc quyền đọc toàn bộ bảng cho tài khoản chạy API thông thường chỉ để giảm số lỗi permission.

### 3.1. GRANT và REVOKE

~~~sql
GRANT SELECT ON some_table TO report_reader;
REVOKE SELECT ON some_table FROM report_reader;
~~~

Quyền có thể đến từ nhiều nguồn: cấp trực tiếp cho user/role, kế thừa từ role thành viên, cấp cho PUBLIC, quyền owner hoặc quyền đặc biệt của hệ thống, ownership chaining hay ngữ cảnh thực thi của routine/view.

Do đó, **REVOKE một grant trực tiếp không nhất thiết loại bỏ quyền nếu role vẫn kế thừa quyền từ một role khác**. Khi kiểm tra bảo mật, phải xem toàn bộ đường cấp quyền và role membership.

### 3.2. Role và user khác nhau theo RDBMS

PostgreSQL dùng role cho cả người dùng có thể đăng nhập lẫn nhóm quyền; SQL Server có database role/server login; MySQL có account dạng user@host; Oracle có user và role. Không port nguyên văn lệnh CREATE ROLE giữa các hệ.

## 4. Quyền ở mức cột

Một bảng có thể chứa cả dữ liệu công khai lẫn dữ liệu nhạy cảm. **Column-level privilege** cho phép cấp quyền trên một tập cột cụ thể khi hệ quản trị hỗ trợ.

~~~text
app_reader:
  SELECT customer_id, display_name

support_reader:
  SELECT customer_id, display_name, email

Role ứng dụng thông thường:
  không SELECT tax_id, internal_note
~~~

### 4.1. Quyền cột khác che giá trị

- **Không có quyền SELECT tax_id:** truy vấn trực tiếp cột này bị từ chối.
- **Có quyền SELECT tax_id nhưng giá trị bị mask:** truy vấn vẫn được phép, song kết quả hiển thị đã che theo cơ chế của hệ.

Quyền cột là **authorization**; masking/redaction là cách kiểm soát biểu diễn dữ liệu. Một số hệ có dynamic data masking nhưng người có quyền cao hoặc đường truy cập khác vẫn có thể đọc giá trị thật.

## 5. View để công bố tập cột

~~~sql
CREATE VIEW v_customer_directory AS
SELECT customer_id, display_name
FROM customers;

GRANT SELECT ON v_customer_directory TO customer_reader;
~~~

View chỉ công bố customer_id và display_name. Nhưng nếu customer_reader vẫn có SELECT trực tiếp trên bảng customers, họ có thể bỏ qua view. Cần thu hồi quyền bảng nguồn hoặc thiết kế quyền theo cơ chế của hệ.

Một view lọc hàng cũng có giới hạn tương tự:

~~~sql
CREATE VIEW v_active_customers AS
SELECT customer_id, display_name
FROM customers
WHERE is_active = TRUE;
~~~

View giới hạn tập hàng **qua view**. Nếu người dùng vẫn SELECT được bảng customers, họ có thể đọc cả khách inactive.

View chỉ trở thành lớp truy cập đáng tin khi người dùng không có đường đọc bảng nguồn rộng hơn ngoài ý muốn, quyền trên view/bảng nguồn được hiểu đúng, và điều kiện hàng được bảo vệ bởi chính sách database khi cần.

### 5.1. View không phải bản sao dữ liệu

Ordinary view thường lưu định nghĩa SELECT. Khi bảng nguồn đổi, lần đọc sau phản ánh dữ liệu nguồn theo snapshot của câu truy vấn. View có thể đặt tên cột, giới hạn cột/hàng và đóng gói phép tính; nó không mặc định tạo snapshot bảo mật độc lập.

## 6. PostgreSQL: chuẩn bị dữ liệu đa tenant

Phần thực hành dùng PostgreSQL 15+. Mục tiêu:

- Tenant 10 và tenant 20 có khách/đơn riêng.
- Role tenant chỉ nhìn thấy hàng của tenant được ánh xạ.
- Role hỗ trợ tenant 10 được đọc email.
- View chỉ công bố một số cột.
- RLS bảo vệ bảng ngay cả khi truy vấn trực tiếp.

### 6.1. Tạo role và schema

Chạy bằng tài khoản quản trị trên **database học tập**. Không dùng các tên role này nếu chúng đã tồn tại.

~~~sql
CREATE ROLE data_owner NOLOGIN;
CREATE ROLE security_owner NOLOGIN;
CREATE ROLE view_owner NOLOGIN;

CREATE ROLE tenant10_login LOGIN;
CREATE ROLE tenant20_login LOGIN;
CREATE ROLE tenant10_support_login LOGIN;

CREATE SCHEMA secure_demo AUTHORIZATION data_owner;
CREATE SCHEMA security AUTHORIZATION security_owner;

REVOKE CREATE ON SCHEMA security FROM PUBLIC;

GRANT USAGE ON SCHEMA secure_demo
TO tenant10_login, tenant20_login, tenant10_support_login, view_owner;

GRANT USAGE ON SCHEMA security
TO tenant10_login, tenant20_login, tenant10_support_login, view_owner;
~~~

Role LOGIN là danh tính database riêng cho từng tenant. Bài không đặt password; quản trị viên cấp credential theo chính sách môi trường. Role NOLOGIN dùng sở hữu đối tượng, không phải tài khoản ứng dụng.

### 6.2. Tạo bảng khách hàng và đơn hàng

~~~sql
CREATE TABLE secure_demo.customers (
    tenant_id     INTEGER NOT NULL,
    customer_id   INTEGER NOT NULL,
    display_name  TEXT NOT NULL,
    email         TEXT,
    tax_id        TEXT,
    internal_note TEXT,
    PRIMARY KEY (tenant_id, customer_id)
);

CREATE TABLE secure_demo.orders (
    order_id      INTEGER PRIMARY KEY,
    tenant_id     INTEGER NOT NULL,
    customer_id   INTEGER NOT NULL,
    amount_vnd    NUMERIC(14,2) NOT NULL CHECK (amount_vnd >= 0),
    status        TEXT NOT NULL
        CHECK (status IN ('NEW', 'PAID', 'CANCELLED')),
    internal_note TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    FOREIGN KEY (tenant_id, customer_id)
        REFERENCES secure_demo.customers(tenant_id, customer_id)
);

ALTER TABLE secure_demo.customers OWNER TO data_owner;
ALTER TABLE secure_demo.orders OWNER TO data_owner;
~~~

Khóa ngoại ghép **(tenant_id, customer_id)** ngăn đơn tenant 10 tham chiếu nhầm customer_id của tenant 20. RLS vẫn cần thiết để giới hạn quyền nhìn thấy và thao tác hàng; FK chỉ bảo vệ tính toàn vẹn quan hệ.

### 6.3. Nạp dữ liệu trước khi bật RLS

~~~sql
INSERT INTO secure_demo.customers
    (tenant_id, customer_id, display_name, email, tax_id, internal_note)
VALUES
    (10, 1, 'An Nguyen', 'an@example.test', 'TAX-10-A', 'VIP account'),
    (10, 2, 'Binh Tran', 'binh@example.test', 'TAX-10-B', 'Call after 5pm'),
    (20, 1, 'Chi Le', 'chi@example.test', 'TAX-20-C', 'Review pending');

INSERT INTO secure_demo.orders
    (order_id, tenant_id, customer_id, amount_vnd, status, internal_note)
VALUES
    (1001, 10, 1, 120000, 'PAID', 'Priority shipment'),
    (1002, 10, 2,  50000, 'NEW',  'Check address'),
    (2001, 20, 1, 250000, 'PAID', 'Internal fraud review');
~~~

Kiểm tra dưới tài khoản quản trị:

~~~sql
SELECT tenant_id, customer_id, display_name
FROM secure_demo.customers
ORDER BY tenant_id, customer_id;

SELECT order_id, tenant_id, amount_vnd, status
FROM secure_demo.orders
ORDER BY order_id;
~~~

Tài khoản quản trị seed có thể nhìn thấy cả hai tenant. Sau khi bật RLS, hãy kiểm thử bằng **login role ứng dụng thực sự**, không kết luận từ kết quả superuser.

## 7. PostgreSQL: column-level GRANT

Thu hồi quyền rộng được cấp qua PUBLIC (nếu có) và cấp các cột cần thiết:

~~~sql
REVOKE ALL ON secure_demo.customers FROM PUBLIC;
REVOKE ALL ON secure_demo.orders FROM PUBLIC;

GRANT SELECT (
    tenant_id,
    customer_id,
    display_name
)
ON secure_demo.customers
TO tenant10_login, tenant20_login;

GRANT SELECT (
    tenant_id,
    customer_id,
    display_name,
    email
)
ON secure_demo.customers
TO tenant10_support_login;

GRANT SELECT, INSERT, UPDATE, DELETE
ON secure_demo.orders
TO tenant10_login, tenant20_login, tenant10_support_login;

GRANT UPDATE (display_name)
ON secure_demo.customers
TO tenant10_support_login;
~~~

Kết quả mong muốn:

- Tenant login có thể đọc tenant_id, customer_id, display_name.
- Support login có thể đọc thêm email và cập nhật display_name.
- Không role nào trong ví dụ được cấp quyền đọc tax_id hoặc internal_note.

### 7.1. Cảnh báo table-level GRANT

~~~sql
GRANT SELECT ON secure_demo.customers TO tenant10_login;
~~~

Nếu cấp SELECT toàn bảng như trên, quyền đọc sẽ rộng hơn giới hạn cột mong muốn. **Không cấp SELECT ở mức bảng cho role đang cần bị giới hạn cột**, trừ khi có thiết kế khác cố ý cho phép.

Quyền cũng có thể đến qua role membership, PUBLIC hoặc quyền owner. Phải xét **tổng hợp tất cả quyền hiệu lực**, không chỉ một câu GRANT.

### 7.2. Column privileges không lọc hàng

Role tenant10 có thể được SELECT cột display_name nhưng nếu không có RLS, nó vẫn có thể đọc display_name của **mọi tenant**. Quyền cột và chính sách hàng giải quyết hai chiều khác nhau.

## 8. PostgreSQL: ánh xạ danh tính database sang tenant

Policy cần biết tenant nào gắn với phiên hiện tại. Ví dụ này dùng **một database login riêng cho mỗi tenant** và ánh xạ danh tính **session_user** sang tenant.

~~~sql
CREATE TABLE security.role_tenants (
    login_role NAME PRIMARY KEY,
    tenant_id  INTEGER NOT NULL
);

ALTER TABLE security.role_tenants OWNER TO security_owner;

INSERT INTO security.role_tenants(login_role, tenant_id)
VALUES
    ('tenant10_login', 10),
    ('tenant20_login', 20),
    ('tenant10_support_login', 10);
~~~

Function lấy tenant của login:

~~~sql
CREATE FUNCTION security.current_tenant_id()
RETURNS INTEGER
LANGUAGE SQL
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, security
AS $$
    SELECT rt.tenant_id
    FROM security.role_tenants AS rt
    WHERE rt.login_role = session_user;
$$;

ALTER FUNCTION security.current_tenant_id()
OWNER TO security_owner;

REVOKE ALL ON FUNCTION security.current_tenant_id() FROM PUBLIC;

GRANT EXECUTE ON FUNCTION security.current_tenant_id()
TO tenant10_login, tenant20_login, tenant10_support_login, view_owner;
~~~

Giải thích:

- **session_user** là danh tính login ban đầu của kết nối, khác với current_user có thể thay đổi khi SET ROLE hoặc trong SECURITY DEFINER.
- Function SECURITY DEFINER đọc bảng ánh xạ dưới quyền owner.
- search_path được đặt cố định và schema security không cho PUBLIC tạo object, giảm rủi ro đối tượng giả mạo trong đường tìm kiếm.
- Function trả NULL nếu login chưa được ánh xạ; so sánh tenant với NULL không thành TRUE, nên policy không mở hàng nào.
- Chỉ cấp EXECUTE cho những role cần dùng function.

**Đây là mẫu cho mô hình database login riêng theo tenant.** Nếu ứng dụng dùng một login chung, session_user giống nhau trong mọi request và không thể tự phân biệt tenant. Khi ấy cần một context được thiết lập từ danh tính đã xác thực và kiểm soát chặt chẽ; không coi giá trị do người dùng tự SET là bằng chứng xác thực.

## 9. PostgreSQL: bật Row-Level Security

**Row-Level Security (RLS)** cho phép database giới hạn các hàng mà một role có thể nhìn thấy hoặc thao tác.

~~~sql
ALTER TABLE secure_demo.customers ENABLE ROW LEVEL SECURITY;
ALTER TABLE secure_demo.orders ENABLE ROW LEVEL SECURITY;

ALTER TABLE secure_demo.customers FORCE ROW LEVEL SECURITY;
ALTER TABLE secure_demo.orders FORCE ROW LEVEL SECURITY;
~~~

- **ENABLE ROW LEVEL SECURITY** bật kiểm tra policy cho bảng.
- **FORCE ROW LEVEL SECURITY** làm table owner cũng chịu policy trong các trường hợp thông thường.
- **Superuser** và role có thuộc tính **BYPASSRLS** vẫn có thể bỏ qua RLS.
- Nếu RLS bật mà không có policy phù hợp, hành vi mặc định là **default deny**: không hàng nào được cho phép qua policy.

### 9.1. Tạo policy theo tenant

~~~sql
CREATE POLICY customers_tenant_isolation
ON secure_demo.customers
AS PERMISSIVE
FOR ALL
TO PUBLIC
USING (
    tenant_id = security.current_tenant_id()
)
WITH CHECK (
    tenant_id = security.current_tenant_id()
);

CREATE POLICY orders_tenant_isolation
ON secure_demo.orders
AS PERMISSIVE
FOR ALL
TO PUBLIC
USING (
    tenant_id = security.current_tenant_id()
)
WITH CHECK (
    tenant_id = security.current_tenant_id()
);
~~~

Policy dùng **TO PUBLIC** để áp dụng cả khi truy vấn qua view owner ở phần sau; function ánh xạ theo session_user, không theo view owner. Role không được ánh xạ sẽ nhận NULL và không thấy hàng.

Trong sản phẩm, có thể chọn role cụ thể thay PUBLIC, nhưng phải xét tất cả vai trò thực sự tham gia truy vấn, bao gồm view owner nếu view chạy theo quyền owner.

### 9.2. USING và WITH CHECK khác nhau

| Thành phần | Kiểm tra gì? | Dùng trong thao tác |
| --- | --- | --- |
| USING | Hàng hiện có có được phép nhìn thấy/được tác động không? | SELECT, DELETE, UPDATE và ngữ cảnh phù hợp |
| WITH CHECK | Hàng mới sau INSERT/UPDATE có thỏa policy không? | INSERT và giá trị mới của UPDATE |

Ví dụ:

- Role tenant 10 SELECT chỉ thấy hàng tenant 10.
- UPDATE chỉ tác động hàng tenant 10 mà role được phép nhìn thấy.
- INSERT hàng tenant 20 bị chặn vì hàng mới không thỏa WITH CHECK.
- UPDATE tenant_id từ 10 sang 20 bị chặn vì giá trị sau cập nhật không còn thỏa.

**USING không thay thế WITH CHECK.** Nếu chỉ kiểm tra hàng hiện có mà không kiểm tra hàng mới, người dùng có thể tìm cách chuyển hàng sang tenant khác qua UPDATE nếu policy không có ràng buộc thích hợp.

### 9.3. Policy riêng theo lệnh

~~~sql
CREATE POLICY orders_read_tenant
ON secure_demo.orders
FOR SELECT
TO tenant10_login, tenant20_login
USING (tenant_id = security.current_tenant_id());

CREATE POLICY orders_insert_tenant
ON secure_demo.orders
FOR INSERT
TO tenant10_login, tenant20_login
WITH CHECK (tenant_id = security.current_tenant_id());
~~~

Đây là **mẫu thay thế** cho policy FOR ALL ở trên, không nên tạo chồng lên policy trước nếu chưa tính cách chúng kết hợp. Có thể phân biệt quyền đọc, thêm, sửa và xóa để dễ review.

## 10. Quy tắc kết hợp nhiều RLS policy

PostgreSQL có hai kiểu policy:

- **PERMISSIVE:** các policy áp dụng được kết hợp theo logic **OR**.
- **RESTRICTIVE:** các policy áp dụng được kết hợp theo logic **AND**.

Ví dụ:

~~~text
Policy A (PERMISSIVE): tenant_id = current_tenant
Policy B (PERMISSIVE): is_public = TRUE

Điều kiện cho phép:
  tenant_id = current_tenant OR is_public = TRUE
~~~

Nếu policy thứ hai nhằm thêm điều kiện bắt buộc, có thể dùng RESTRICTIVE:

~~~text
Policy tenant (PERMISSIVE):
  tenant_id = current_tenant

Policy published (RESTRICTIVE):
  published = TRUE

Điều kiện cuối:
  tenant_id = current_tenant AND published = TRUE
~~~

Policy restrictive không tự tạo quyền cho role khi không có policy permissive phù hợp. Hãy test tổ hợp policy, không đọc riêng từng WHERE rồi kết luận.

## 11. Kiểm thử PostgreSQL bằng đúng role

**Không test RLS chỉ bằng superuser hoặc table owner.** Những role đặc biệt có thể bypass policy.

### 11.1. Cấp quyền schema và bảng

~~~sql
GRANT USAGE ON SCHEMA secure_demo
TO tenant10_login, tenant20_login, tenant10_support_login;

GRANT SELECT, INSERT, UPDATE, DELETE
ON secure_demo.orders
TO tenant10_login, tenant20_login, tenant10_support_login;
~~~

Đối với customers, ta đã cấp quyền cột ở phần 7; không cấp SELECT toàn bảng.

### 11.2. Kết nối bằng tenant10_login

Mở **connection mới** với credential database của tenant10_login:

~~~sql
SELECT session_user, current_user;

SELECT order_id, tenant_id, amount_vnd, status
FROM secure_demo.orders
ORDER BY order_id;
~~~

Kết quả chỉ có đơn **1001 và 1002**, tenant_id = 10.

~~~sql
SELECT customer_id, tenant_id, display_name
FROM secure_demo.customers
ORDER BY customer_id;
~~~

Chỉ có **An Nguyen** và **Binh Tran**.

### 11.3. Kết nối bằng tenant20_login

~~~sql
SELECT order_id, tenant_id, amount_vnd, status
FROM secure_demo.orders
ORDER BY order_id;
~~~

Chỉ thấy đơn **2001**, tenant_id = 20.

### 11.4. Thử truy cập cột không được cấp

Khi kết nối bằng tenant10_login:

~~~sql
SELECT tax_id
FROM secure_demo.customers;
~~~

Truy vấn phải bị từ chối vì role không được cấp quyền SELECT trên tax_id.

### 11.5. Thử ghi sang tenant khác

~~~sql
INSERT INTO secure_demo.orders
    (order_id, tenant_id, customer_id, amount_vnd, status)
VALUES
    (1010, 20, 1, 10000, 'NEW');
~~~

Khi thực hiện bằng tenant10_login, WITH CHECK phải từ chối vì hàng mới thuộc tenant 20.

~~~sql
UPDATE secure_demo.orders
SET tenant_id = 20
WHERE order_id = 1001;
~~~

Hàng 1001 thuộc tenant 10 và giá trị sau UPDATE là tenant 20, nên policy không cho phép.

### 11.6. Vai trò đặc biệt

| Vai trò | Có thể bypass RLS? |
| --- | --- |
| Role thường được policy áp dụng | Không, bị giới hạn theo policy |
| Table owner mặc định | Thường bypass RLS |
| Table owner khi FORCE RLS | Chịu policy, trừ ngoại lệ đặc quyền |
| Superuser | Bypass |
| Role có BYPASSRLS | Bypass |

**FORCE ROW LEVEL SECURITY không làm superuser bị giới hạn.** Tài khoản quản trị/migration cần được bảo vệ và không dùng cho truy vấn từ ứng dụng.

## 12. PostgreSQL view: quyền của owner và người gọi

View là giao diện quan trọng nhưng phải hiểu **ai có quyền trên bảng nguồn khi SELECT view**.

### 12.1. View mặc định dùng quyền owner

Thông thường, quyền truy cập bảng nguồn của view được kiểm tra theo **view owner**. Điều này cho phép một role được SELECT view mà không cần SELECT trực tiếp toàn bộ bảng nguồn.

Tạo view chỉ công bố một số cột:

~~~sql
CREATE VIEW secure_demo.v_customer_public
WITH (security_barrier = true)
AS
SELECT tenant_id, customer_id, display_name
FROM secure_demo.customers;
~~~

Gán owner và quyền:

~~~sql
GRANT SELECT (
    tenant_id,
    customer_id,
    display_name
)
ON secure_demo.customers
TO view_owner;

ALTER VIEW secure_demo.v_customer_public
OWNER TO view_owner;

GRANT SELECT ON secure_demo.v_customer_public
TO tenant10_login, tenant20_login;
~~~

View owner cần quyền đọc các cột mà view tham chiếu. Người gọi chỉ cần quyền SELECT trên view. Trong ví dụ này tax_id, email và internal_note không được đưa vào view công khai.

### 12.2. RLS qua view mặc định

Với view mặc định, quyền và RLS trên bảng nguồn có thể được xét theo **view owner**. Nếu view owner là table owner hoặc role BYPASSRLS, dữ liệu có thể vượt phạm vi RLS mong muốn, tùy cấu hình FORCE RLS.

Nếu dùng view như lớp bảo mật:

1. Chọn view owner chuyên biệt, không phải superuser.
2. Không cấp BYPASSRLS cho view owner.
3. Không để view owner là table owner nếu không có chủ đích; hoặc bật FORCE RLS và kiểm tra policy.
4. Thiết kế policy áp dụng được trong ngữ cảnh view owner.
5. Test bằng login tenant thật.

### 12.3. security_invoker trên PostgreSQL 15+

~~~sql
CREATE VIEW secure_demo.v_customer_invoker
WITH (
    security_invoker = true,
    security_barrier = true
)
AS
SELECT tenant_id, customer_id, display_name
FROM secure_demo.customers;
~~~

Với **security_invoker = true**, quyền truy cập bảng nền được xét theo **người gọi view**; RLS cũng được xét theo người gọi theo cơ chế tương ứng. Người gọi cần quyền SELECT phù hợp trên những cột bảng nguồn mà view sử dụng.

| Chế độ | Quyền truy cập bảng nguồn | RLS trên bảng nguồn |
| --- | --- | --- |
| View mặc định | View owner | Theo view owner |
| security_invoker = true | Người gọi | Theo người gọi |

security_invoker hữu ích khi muốn view tuân theo quyền caller, nhưng không tự cấp quyền nguồn. Nếu caller chỉ được SELECT view và không có quyền bảng nguồn, truy vấn invoker view có thể thất bại.

### 12.4. security_barrier không phải GRANT hoặc RLS

**security_barrier = true** ảnh hưởng cách PostgreSQL tối ưu hóa và đánh giá điều kiện của view, nhằm tránh một số trường hợp predicate do người gọi cung cấp hoặc hàm không leakproof được đánh giá theo thứ tự có thể làm lộ thông tin qua side channel.

Nó **không tự giới hạn tenant**, không tự ẩn cột, không thay quyền SELECT và không thay RLS. Hãy xem đây là thuộc tính về an toàn khi tối ưu hóa view, không phải chính sách phân quyền hoàn chỉnh.

## 13. View, column privilege và RLS kết hợp

~~~text
Role tenant10_login
   |
   +-- SELECT trên v_customer_public
   |
   +-- Không có SELECT tax_id
   |
   +-- RLS chỉ cho tenant_id = 10
   |
   +-- View chỉ công bố customer_id/display_name
~~~

Một view riêng cho hỗ trợ có thể công bố email:

~~~sql
CREATE VIEW secure_demo.v_customer_support
WITH (security_barrier = true)
AS
SELECT tenant_id, customer_id, display_name, email
FROM secure_demo.customers;

ALTER VIEW secure_demo.v_customer_support
OWNER TO view_owner;

GRANT SELECT (
    tenant_id,
    customer_id,
    display_name,
    email
)
ON secure_demo.customers
TO view_owner;

GRANT SELECT ON secure_demo.v_customer_support
TO tenant10_support_login;
~~~

tenant10_support_login được ánh xạ tenant 10 trong role_tenants. Nếu kết nối bằng role này, view có thể trả email của khách tenant 10 theo policy.

Không tạo view all-columns rồi trông chờ ứng dụng tự ẩn dữ liệu. Nếu API SELECT * từ view chứa tax_id/internal_note rồi chỉ không serialize hai trường ấy, dữ liệu nhạy cảm vẫn đã được đọc vào tầng ứng dụng. Hãy giới hạn projection ngay ở database.

## 14. Context của ứng dụng và rủi ro giả mạo tenant

Một mẫu thường gặp trong hệ đa tenant là đặt tenant_id vào session context:

~~~sql
SELECT set_config('app.tenant_id', '10', false);
~~~

Rồi policy đọc:

~~~sql
tenant_id = current_setting('app.tenant_id', true)::INTEGER
~~~

Nhưng **custom setting của PostgreSQL không tự chứng minh người gọi thuộc tenant đó**. Nếu user có thể chạy SQL tùy ý trên connection, họ có thể thử SET app.tenant_id sang tenant khác. Một SQL injection đủ quyền cũng có thể thao túng ngữ cảnh.

### 14.1. Khi nào session context có thể được sử dụng?

Nó có thể là một phần của thiết kế khi:

- Người dùng cuối không được kết nối trực tiếp và không có quyền gửi SQL tùy ý.
- Middleware xác thực danh tính trước khi lấy tenant.
- Connection pool thiết lập context đúng trước mỗi request và reset khi trả connection.
- Không cho người dùng kiểm soát câu lệnh set context.
- Có kiểm thử SQL injection và truy cập chéo tenant.
- Có ranh giới tin cậy rõ ràng giữa ứng dụng và database.

Nếu cần database tự xác thực tenant dựa trên login, mô hình login riêng/role mapping có thể rõ hơn.

### 14.2. Connection pool

~~~text
Request tenant 10 → connection A → set context 10
Request tenant 20 → connection A → set context 20
~~~

Nếu lần thứ hai quên cập nhật hoặc reset context, tenant 20 có thể kế thừa tenant 10. Vì thế, hãy thiết lập context mỗi lần mượn connection, không tin giá trị cũ, reset trạng thái khi trả connection và test tái sử dụng connection chéo tenant.

**Một session variable đúng giá trị trong một truy vấn không đủ chứng minh pool an toàn.**

## 15. SQL Server: Row-Level Security bằng Security Policy

SQL Server có **Row-Level Security** thông qua:

- Inline table-valued function làm security predicate.
- Security policy gắn predicate với bảng.
- **Filter predicate** lọc hàng khi đọc/cập nhật/xóa.
- **Block predicate** chặn ghi hàng vi phạm.

### 15.1. Predicate dựa trên SESSION_CONTEXT

Ví dụ SQL Server 2016+:

~~~sql
CREATE SCHEMA Security;
GO

CREATE FUNCTION Security.fn_tenant_access(
    @TenantId INT
)
RETURNS TABLE
WITH SCHEMABINDING
AS
RETURN
    SELECT 1 AS fn_securitypredicate_result
    WHERE @TenantId =
        TRY_CONVERT(INT, SESSION_CONTEXT(N'tenant_id'));
GO
~~~

Nếu context chưa được đặt hoặc không chuyển được thành số nguyên, điều kiện không TRUE và không cho hàng qua.

### 15.2. Gắn Security Policy

~~~sql
CREATE SECURITY POLICY Security.TenantPolicy
ADD FILTER PREDICATE
    Security.fn_tenant_access(TenantId)
    ON dbo.Orders,
ADD BLOCK PREDICATE
    Security.fn_tenant_access(TenantId)
    ON dbo.Orders AFTER INSERT,
ADD BLOCK PREDICATE
    Security.fn_tenant_access(TenantId)
    ON dbo.Orders BEFORE UPDATE,
ADD BLOCK PREDICATE
    Security.fn_tenant_access(TenantId)
    ON dbo.Orders AFTER UPDATE
WITH (STATE = ON);
GO
~~~

- **FILTER PREDICATE:** người dùng chỉ nhìn/thao tác hàng được predicate cho phép theo lệnh tương ứng.
- **AFTER INSERT:** kiểm tra hàng sau INSERT.
- **BEFORE UPDATE:** kiểm soát hàng đang bị cập nhật.
- **AFTER UPDATE:** kiểm tra trạng thái hàng sau cập nhật để không cho chuyển sang tenant khác.

Filter và block predicate khác nhau. Đừng chỉ thêm filter rồi cho rằng mọi đường INSERT/UPDATE đều tự động bị chặn theo tenant mong muốn.

### 15.3. Thiết lập session context

Một lớp ứng dụng đáng tin có thể thiết lập:

~~~sql
EXEC sys.sp_set_session_context
    @key = N'tenant_id',
    @value = 10;
~~~

Sau đó:

~~~sql
SELECT OrderId, TenantId, Amount
FROM dbo.Orders;
~~~

Database áp dụng security policy cho bảng. **SESSION_CONTEXT không tự xác thực người dùng**: nếu principal có thể chạy SQL tùy ý và thay đổi context, họ có thể giả mạo tenant. Giá trị phải đến từ tầng xác thực tin cậy và session phải được kiểm soát.

Tùy chọn **@read_only = 1** có thể ngăn thay đổi giá trị trong phần còn lại của logical connection. Connection pool phải được thiết kế tương ứng, không tái sử dụng connection đã khóa context cho tenant khác.

### 15.4. Column-level permissions trên SQL Server

~~~sql
GRANT SELECT
ON OBJECT::dbo.Customers (CustomerId, DisplayName)
TO app_reader;

GRANT UPDATE (DisplayName)
ON OBJECT::dbo.Customers
TO support_agent;
~~~

Nếu role có quyền SELECT toàn bảng qua grant khác, column restriction không còn tạo giới hạn mong muốn. Cần kiểm tra quyền hiệu lực, membership và ownership.

### 15.5. View và Dynamic Data Masking

~~~sql
CREATE VIEW dbo.v_customer_public
AS
SELECT CustomerId, DisplayName
FROM dbo.Customers;
GO

GRANT SELECT ON dbo.v_customer_public TO app_reader;
~~~

SQL Server còn có **Dynamic Data Masking (DDM)**:

~~~sql
-- Mẫu trên bảng đã tồn tại, cần quyền ALTER.
ALTER TABLE dbo.Customers
ALTER COLUMN Email
ADD MASKED WITH (FUNCTION = 'email()');
~~~

DDM che dữ liệu trong kết quả với principal không có quyền UNMASK tương ứng, nhưng **không phải ranh giới bảo mật mạnh thay cho quyền SELECT**. Người dùng vẫn có thể suy luận dữ liệu qua điều kiện hoặc đường truy cập khác nếu được cấp quyền; principal đặc quyền có thể xem giá trị thật.

## 16. MySQL: column privileges và view thay cho RLS native

MySQL có **column-level privileges** và **view security**, nhưng không có cơ chế native Row-Level Security tương đương CREATE POLICY của PostgreSQL hoặc Security Policy của SQL Server.

### 16.1. Cấp quyền theo cột

~~~sql
GRANT SELECT (customer_id, display_name)
ON sales_db.customers
TO 'app_reader'@'%';

GRANT SELECT (customer_id, display_name, email)
ON sales_db.customers
TO 'support_agent'@'%';
~~~

Tài khoản app_reader chỉ được đọc các cột được liệt kê nếu không có grant rộng hơn từ nguồn khác.

### 16.2. View cố định theo tenant

~~~sql
CREATE DEFINER = 'view_owner'@'localhost'
SQL SECURITY DEFINER
VIEW sales_db.v_tenant10_orders AS
SELECT order_id, tenant_id, amount, status
FROM sales_db.orders
WHERE tenant_id = 10;
~~~

Cấp quyền:

~~~sql
GRANT SELECT
ON sales_db.v_tenant10_orders
TO 'tenant10_reader'@'%';
~~~

Với **SQL SECURITY DEFINER**, quyền truy cập bảng nguồn của view được kiểm tra theo definer theo cơ chế MySQL. Người đọc view có thể không cần SELECT trực tiếp bảng gốc.

Đây là view cố định cho tenant 10, không phải policy động tự xác định tenant của từng request. Nếu tạo một view cho từng tenant, số lượng đối tượng và migration sẽ tăng theo số tenant.

### 16.3. SQL SECURITY INVOKER

~~~sql
CREATE
    SQL SECURITY INVOKER
VIEW sales_db.v_order_summary AS
SELECT order_id, tenant_id, amount, status
FROM sales_db.orders;
~~~

Với INVOKER, quyền bảng nguồn được xét theo người gọi; người gọi cần quyền thích hợp trên bảng/cột được truy vấn.

### 16.4. WITH CHECK OPTION không phải RLS

~~~sql
CREATE VIEW sales_db.v_tenant10_open_orders AS
SELECT order_id, tenant_id, amount, status
FROM sales_db.orders
WHERE tenant_id = 10
  AND status = 'NEW'
WITH CASCADED CHECK OPTION;
~~~

Với view có thể cập nhật, **CHECK OPTION** yêu cầu thao tác ghi qua view vẫn tạo ra hàng thỏa điều kiện view. Nhưng nó không phải RLS tổng quát, không ngăn người có quyền UPDATE trực tiếp bảng gốc đi vòng qua view, và không tự xác định danh tính tenant.

### 16.5. Thiết kế multi-tenant MySQL

Có thể dùng database account riêng và view theo tenant, hoặc một lớp ứng dụng kiểm tra tenant với quyền bảng giới hạn. Nếu dùng biến session hay điều kiện view phụ thuộc thông tin do caller tự gửi, phải kiểm soát nguồn tin cậy. **Không có native RLS không có nghĩa chỉ cần WHERE tenant_id là đủ an toàn.**

## 17. Oracle: VPD / Virtual Private Database

Oracle cung cấp **Virtual Private Database (VPD)**, còn gọi là **Fine-Grained Access Control (FGAC)**, thông qua package **DBMS_RLS**. Database có thể tự thêm predicate vào truy vấn theo policy function.

### 17.1. Application context

Mẫu khái quát:

~~~sql
CREATE OR REPLACE PACKAGE security_ctx_pkg AS
    PROCEDURE set_tenant(p_tenant_id NUMBER);
END;
/

CREATE OR REPLACE PACKAGE BODY security_ctx_pkg AS
    PROCEDURE set_tenant(p_tenant_id NUMBER) IS
    BEGIN
        DBMS_SESSION.SET_CONTEXT(
            'APP_CTX',
            'TENANT_ID',
            TO_CHAR(p_tenant_id)
        );
    END;
END;
/

CREATE CONTEXT APP_CTX
USING security_ctx_pkg;
/
~~~

**CREATE CONTEXT** gắn namespace APP_CTX với package tin cậy. Trong ứng dụng thật, package phải xác minh danh tính/tenant từ nguồn đáng tin trước khi đặt context. Không để người dùng cuối tự gọi setter không kiểm tra và tùy ý chọn tenant.

### 17.2. Policy function

~~~sql
CREATE OR REPLACE FUNCTION security_tenant_predicate(
    p_schema IN VARCHAR2,
    p_object IN VARCHAR2
)
RETURN VARCHAR2
AS
BEGIN
    RETURN
        'tenant_id = SYS_CONTEXT(''APP_CTX'', ''TENANT_ID'')';
END;
/
~~~

Function trả về một **đoạn predicate SQL** mà VPD gắn vào câu truy vấn. Nếu context không có giá trị, phép so sánh với NULL không thành TRUE, do đó không trả hàng theo predicate này.

### 17.3. Gắn policy bằng DBMS_RLS

~~~sql
BEGIN
    DBMS_RLS.ADD_POLICY(
        object_schema   => 'APP',
        object_name     => 'ORDERS',
        policy_name     => 'ORDERS_TENANT_POLICY',
        function_schema => 'SECURITY',
        policy_function => 'SECURITY_TENANT_PREDICATE',
        statement_types => 'SELECT,INSERT,UPDATE,DELETE',
        update_check    => TRUE
    );
END;
/
~~~

Ví dụ giả định schema APP, bảng ORDERS và function SECURITY_TENANT_PREDICATE đã được tạo với quyền thích hợp. **update_check => TRUE** yêu cầu kiểm tra predicate đối với giá trị hàng sau thao tác ghi theo cơ chế VPD.

### 17.4. VPD không phải view

VPD áp dụng predicate theo policy trên đối tượng; ứng dụng có thể truy vấn bảng trực tiếp nhưng database tự giới hạn tập hàng. Điều này khác view tĩnh có WHERE tenant_id = 10.

Oracle còn có tùy chọn policy theo statement, kiểu policy và cột liên quan. Cần xem tài liệu Oracle Database/DBMS_RLS đúng phiên bản và quyền trước khi triển khai.

### 17.5. Column-level SELECT và view trên Oracle

Oracle có quyền theo cột trong những trường hợp như **INSERT, UPDATE, REFERENCES**, nhưng không có mô hình **column-level SELECT privilege tổng quát** giống PostgreSQL/MySQL/SQL Server. Để giới hạn cột đọc, cách thông dụng là tạo **view chỉ chiếu cột được phép** và cấp SELECT trên view.

### 17.6. Data Redaction

Oracle có **Data Redaction** qua DBMS_REDACT để che một số giá trị trong kết quả theo policy. Đây là lớp bảo vệ cách hiển thị; cần phân biệt với VPD lọc hàng và quyền SELECT. Không coi redaction là thay thế quyền truy cập, vì người có đặc quyền hoặc đường truy vấn khác có thể xem dữ liệu thật theo cấu hình.

## 18. SQLite: giới hạn về quyền và RLS

SQLite là database nhúng, thường được truy cập qua thư viện trong tiến trình ứng dụng. **SQLite core không có mô hình server users/roles, GRANT/REVOKE và Row-Level Security native** như PostgreSQL/SQL Server/Oracle.

### 18.1. View giới hạn projection nhưng không phải ranh giới nếu người dùng mở file

~~~sql
CREATE VIEW v_customer_public AS
SELECT customer_id, display_name
FROM customers;
~~~

Ứng dụng có thể dùng view này làm giao diện đọc. Nhưng nếu người dùng/tiến trình khác có thể mở trực tiếp file database và gửi SQL tùy ý, họ có thể truy vấn bảng customers nếu file không được bảo vệ ở lớp khác.

### 18.2. Authorizer callback

SQLite có **sqlite3_set_authorizer()** trong C API để callback quyết định một số thao tác SQL được chuẩn bị có được phép hay không, dựa trên action/table/column/nguồn trigger hoặc view.

Authorizer hữu ích để ngăn một connection thực hiện SELECT trên bảng/cột nhất định, nhưng **không phải bộ lọc từng hàng** thay thế RLS. Nó thường quyết định quyền của hành động khi statement được phân tích/chuẩn bị.

### 18.3. Bảo vệ file và tầng ứng dụng

Với SQLite, các lớp bảo vệ thường gồm:

- Quyền hệ điều hành trên file database, thư mục, file journal/WAL và backup.
- Mã hóa file bằng giải pháp/extension phù hợp khi yêu cầu.
- Không cho người dùng không tin cậy mở trực tiếp database file.
- Dùng prepared statements và kiểm tra tenant trong repository/service.
- Có thể tách file theo tenant khi kiến trúc và vận hành cho phép.
- Dùng authorizer để giới hạn câu SQL của connection.
- Kiểm thử backup/export, log và đường truy cập khác.

**WHERE tenant_id = ? trong ứng dụng không phải RLS của SQLite**. Nó chỉ an toàn nếu ranh giới ứng dụng thực sự kiểm soát mọi đường truy cập.

## 19. So sánh khả năng bảo vệ hàng, cột và view

| Khả năng | PostgreSQL | SQL Server | MySQL 8.0 | Oracle | SQLite core |
| --- | --- | --- | --- | --- | --- |
| Column-level SELECT | Có | Có | Có | Không theo mô hình tổng quát; dùng view | Không có GRANT |
| Column-level UPDATE | Có | Có | Có | Có | Không có GRANT |
| Native row-level policy | RLS | RLS Security Policy | Không có native RLS tương đương | VPD/DBMS_RLS | Không |
| View giới hạn cột | Có | Có | Có | Có | Có |
| View invoker/definer | security_invoker option (PG15+) và mặc định owner rights | Ownership chaining/EXECUTE AS theo ngữ cảnh | SQL SECURITY DEFINER/INVOKER | Definer/invoker rights của PL/SQL; view có quy tắc riêng | Không có GRANT view như server RDBMS |
| Dynamic masking/redaction | Không có DDM core tương đương; dùng view/logic | Dynamic Data Masking | View/logic ứng dụng | Data Redaction | Ứng dụng/extension |
| Context cho tenant | Role mapping hoặc context được kiểm soát | SESSION_CONTEXT | Account/view/application context | SYS_CONTEXT/Application Context | Host application |
| Bảo vệ trực tiếp file DB | Không phải mô hình server chính | Không phải mô hình server chính | Không phải mô hình server chính | Không phải mô hình server chính | Rất quan trọng |

Tên tính năng giống nhau không có nghĩa semantics giống nhau. Đặc biệt, view owner, RLS predicate, definer rights và session context cần được kiểm tra theo đúng engine/version.

## 20. Kiểm thử chính sách bảo vệ dữ liệu

Một policy chỉ được coi là có hiệu lực sau khi kiểm thử bằng **các principal thật** và cả truy vấn thành công lẫn truy vấn phải bị từ chối.

### 20.1. Ma trận kiểm thử hàng

| Principal | Hành động | Hàng tenant 10 | Hàng tenant 20 |
| --- | --- | --- | --- |
| tenant10_login | SELECT | Cho phép | Không nhìn thấy |
| tenant20_login | SELECT | Không nhìn thấy | Cho phép |
| tenant10_login | INSERT tenant 10 | Cho phép nếu quyền/constraint hợp lệ | — |
| tenant10_login | INSERT tenant 20 | Từ chối bởi WITH CHECK | — |
| tenant10_login | UPDATE hàng tenant 10 sang tenant 20 | Từ chối | — |
| role chưa được ánh xạ | SELECT | Không nhìn thấy | Không nhìn thấy |
| superuser/BYPASSRLS | SELECT | Có thể bypass | Có thể bypass |

### 20.2. Ma trận kiểm thử cột

| Principal | display_name | email | tax_id |
| --- | --- | --- | --- |
| tenant10_login | Cho phép | Từ chối trực tiếp | Từ chối |
| tenant10_support_login | Cho phép | Cho phép | Từ chối |
| app_reader qua public view | Có trong view | Không có trong view | Không có trong view |

Phải test SELECT cột được phép/bị cấm, SELECT * trên bảng nguồn, SELECT * trên view, JOIN view với bảng khác, routine/view khác và quyền kế thừa qua role membership.

### 20.3. Kiểm thử view

1. Người dùng có thể SELECT view không?
2. Người dùng có thể SELECT bảng nguồn trực tiếp không?
3. View có vô tình chứa cột nhạy cảm không?
4. RLS được áp dụng dưới quyền owner hay invoker?
5. View owner có phải table owner hoặc BYPASSRLS không?
6. security_invoker có khiến caller cần quyền bảng nguồn không?
7. security_barrier có được dùng đúng mục tiêu, không bị hiểu thành GRANT/RLS không?

### 20.4. Kiểm thử session context và connection pool

1. Gọi request tenant 10 trên connection A.
2. Trả connection A về pool.
3. Request tenant 20 lấy lại chính connection A.
4. Kiểm tra context đã được thiết lập lại trước truy vấn.
5. Thử lỗi giữa request và xem cleanup/reset có được thực hiện không.
6. Thử SQL injection để đánh giá khả năng đổi context.

Đây là lỗi multi-tenant có hậu quả lớn: **context của request trước bị dùng lại cho request sau**.

## 21. SQL injection và quyền truy cập

Bind parameter giúp tách dữ liệu khỏi cú pháp SQL:

~~~sql
SELECT order_id, amount_vnd
FROM secure_demo.orders
WHERE tenant_id = $1
  AND status = $2;
~~~

Nhưng **bind parameter không tự xác thực tenant**. Nếu ứng dụng lấy tenant_id từ request chưa xác minh rồi bind vào $1, người dùng vẫn có thể yêu cầu tenant khác.

Thiết kế an toàn cần:

- Xác thực danh tính ở server.
- Lấy tenant từ claim/quan hệ được kiểm chứng.
- Thiết lập role/context theo quy trình tin cậy.
- Dùng prepared statement.
- Không cấp quyền đọc bảng gốc rộng cho role ứng dụng.
- Áp dụng RLS/VPD hoặc lớp kiểm soát phù hợp.
- Test các đường gọi trực tiếp, view, function và export.

**Prepared statement ngăn một loại tấn công cú pháp; nó không thay thế authorization.**

## 22. Những lỗi thường gặp

| Lỗi/nhầm lẫn | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Chỉ tạo view rồi vẫn GRANT SELECT bảng gốc | Người dùng bỏ qua view | Thu hồi quyền nguồn hoặc dùng policy |
| GRANT SELECT toàn bảng rồi thêm grant cột hạn chế | Quyền rộng vẫn có hiệu lực | Xem tổng quyền, bỏ grant rộng |
| Dùng column privilege để lọc tenant | Vẫn thấy cột của mọi tenant | Kết hợp RLS/VPD/kiểm soát hàng |
| Dùng RLS để ẩn cột | Cột nhạy cảm vẫn đọc được trên hàng được phép | Column grants hoặc view projection |
| Quên WITH CHECK | Có thể ghi hàng mới/chuyển tenant sai policy | Kiểm tra cả hàng sau INSERT/UPDATE |
| Nghĩ FORCE RLS chặn superuser | Superuser/BYPASSRLS vẫn bypass | Không dùng tài khoản đặc quyền cho ứng dụng |
| Test RLS bằng table owner | Owner có thể bypass mặc định | Test bằng role ứng dụng |
| View owner bypass RLS | Có thể lộ hàng qua view | Owner chuyên biệt, FORCE/policy, test |
| Nhầm security_barrier là quyền truy cập | Không có giới hạn hàng/cột | Dùng GRANT/RLS và view đúng cách |
| SECURITY DEFINER dùng search_path không tin cậy | Rủi ro gọi nhầm object/leo thang quyền | search_path cố định, schema-qualify |
| Tin custom GUC/session context là danh tính | Người gọi có thể tự đổi tenant | Map login hoặc context tin cậy |
| Quên reset context trong pool | Request sau dùng tenant cũ | Set/reset mỗi lần mượn và trả connection |
| MySQL view được coi là native RLS | Không có policy động cho mọi bảng | Quản lý view/account hoặc app authorization |
| MySQL CHECK OPTION được coi là bảo vệ bảng gốc | Direct DML bypass view | Thu hồi quyền nguồn, kiểm soát ghi |
| Oracle Data Redaction được coi là VPD | Che giá trị nhưng không lọc hàng | Phân biệt VPD, quyền, redaction |
| Oracle VPD context do client tự chọn | Có thể giả mạo tenant | Package context tin cậy |
| SQLite view được coi là ranh giới bảo mật file | Người có file có thể đọc bảng gốc | OS/file security và kiểm soát ứng dụng |
| SQLite authorizer được coi là RLS | Không lọc từng hàng | Host layer hoặc tách database |
| Chỉ test SELECT | Bỏ sót INSERT/UPDATE vượt tenant | Test block/check policy |
| Không kiểm tra quyền kế thừa | Role vẫn có quyền từ nhóm khác | Kiểm tra membership/PUBLIC/owner |
| Bỏ qua backup/log/export | Dữ liệu lộ qua đường ngoài truy vấn | Bảo vệ toàn bộ vòng đời dữ liệu |

## 23. Bài tập thực hành

Các bài PostgreSQL dùng schema **secure_demo** ở phần 6. Hãy thực hiện trong database học tập và dùng login role riêng để quan sát RLS. Các phần phương ngữ khác cần hệ tương ứng.

1. Phân biệt quyền đối tượng, quyền cột, RLS, view và data masking.
2. Tạo role NOLOGIN cho owner và login role tenant 10/20.
3. Tạo bảng customers có display_name, email, tax_id và internal_note.
4. Tạo bảng orders có tenant_id và khóa ngoại ghép tới customers.
5. Giải thích vì sao FK ghép tenant_id/customer_id bổ sung cho RLS.
6. Cấp SELECT chỉ cho customer_id, tenant_id, display_name của tenant login.
7. Thử cấp SELECT toàn bảng rồi quan sát vì sao giới hạn cột không còn như mong muốn.
8. Cấp UPDATE chỉ cho display_name của role support.
9. Tạo bảng security.role_tenants và ánh xạ session_user sang tenant.
10. Viết security.current_tenant_id() SECURITY DEFINER, cố định search_path và thu hồi EXECUTE PUBLIC.
11. Bật ENABLE ROW LEVEL SECURITY và FORCE ROW LEVEL SECURITY trên orders.
12. Tạo policy FOR ALL có USING và WITH CHECK.
13. Kết nối bằng tenant10_login và xác nhận chỉ thấy hàng tenant 10.
14. Kết nối bằng tenant20_login và xác nhận chỉ thấy hàng tenant 20.
15. Thử INSERT hàng tenant 20 bằng tenant10_login; ghi nhận WITH CHECK.
16. Thử UPDATE tenant_id của một hàng tenant 10 thành 20.
17. Thử SELECT tax_id bằng tenant10_login; giải thích lỗi quyền cột.
18. Tạo hai policy permissive A/B và dự đoán tập hàng khi kết hợp OR.
19. Thêm policy restrictive để buộc published = TRUE; giải thích phép AND.
20. Tạo view công khai không có email/tax_id và chỉ cấp SELECT view.
21. Tạo view owner riêng; kiểm tra quyền nguồn và RLS khi truy vấn view mặc định.
22. Tạo view security_invoker = true; kiểm tra vì sao caller cần quyền cột bảng nguồn.
23. Bật security_barrier và mô tả mục tiêu optimizer/predicate.
24. Giải thích vì sao view owner là table owner hoặc BYPASSRLS có thể làm hỏng thiết kế.
25. So sánh truy vấn bằng superuser và tenant login.
26. Thiết kế mô hình shared application login dùng context; liệt kê điều kiện tin cậy.
27. Mô phỏng connection pool tái sử dụng session context sai tenant.
28. Viết SQL Server inline TVF dựa trên SESSION_CONTEXT và security policy filter/block.
29. Viết SQL Server column-level GRANT SELECT và một view công khai.
30. Bật Dynamic Data Masking cho Email; giải thích vì sao nó không thay GRANT SELECT.
31. Viết MySQL column-level GRANT cho app_reader và support_agent.
32. Tạo MySQL SQL SECURITY DEFINER view lọc tenant cố định và cấp SELECT trên view.
33. So sánh SQL SECURITY DEFINER với INVOKER; vai trò của WITH CHECK OPTION.
34. Viết Oracle application context package và CREATE CONTEXT.
35. Viết VPD policy function trả predicate tenant_id và gọi DBMS_RLS.ADD_POLICY.
36. Giải thích khác biệt Oracle VPD với view có WHERE tenant_id = 10.
37. Dùng Oracle view để ẩn cột nhạy cảm; phân biệt Data Redaction với VPD.
38. Dùng SQLite view projection và authorizer callback; giải thích giới hạn row-level.
39. Thiết kế cách bảo vệ file SQLite nhiều tenant khi người dùng có quyền filesystem.
40. Lập test matrix gồm SELECT/INSERT/UPDATE/DELETE, cột nhạy cảm, tenant sai, role không mapping, view owner và context bị reset.

### Câu hỏi tự kiểm tra

**Câu 1.** GRANT SELECT trên một view có tự ngăn người dùng đọc bảng nguồn nếu họ vẫn được SELECT bảng đó không?

**Đáp án:** **Không.** Họ có thể bỏ qua view và truy cập trực tiếp bảng nguồn.

**Câu 2.** Column-level GRANT có tự lọc hàng theo tenant không?

**Đáp án:** **Không.** Nó giới hạn cột; RLS/VPD hoặc lớp kiểm soát hàng mới giới hạn tenant.

**Câu 3.** Trong PostgreSQL RLS, USING và WITH CHECK có cùng nhiệm vụ không?

**Đáp án:** **Không.** USING xét hàng hiện có/được phép tác động; WITH CHECK kiểm tra hàng mới sau INSERT/UPDATE.

**Câu 4.** RLS bật mà không có policy phù hợp thì mặc định cho phép tất cả hàng không?

**Đáp án:** **Không.** PostgreSQL áp dụng default deny.

**Câu 5.** FORCE ROW LEVEL SECURITY có làm superuser bị policy giới hạn không?

**Đáp án:** **Không.** Superuser và role BYPASSRLS vẫn có thể bypass.

**Câu 6.** PostgreSQL view mặc định dùng quyền của ai trên bảng nguồn?

**Đáp án:** Thông thường là **view owner**; với security_invoker = true, quyền được xét theo người gọi.

**Câu 7.** security_barrier có thay thế GRANT và RLS không?

**Đáp án:** **Không.** Nó liên quan an toàn thứ tự đánh giá predicate/optimizer của view.

**Câu 8.** Custom setting app.tenant_id có tự chứng minh user thuộc tenant đó không?

**Đáp án:** **Không.** Giá trị context phải được thiết lập từ nguồn tin cậy; người có khả năng chạy SQL tùy ý có thể thử giả mạo.

**Câu 9.** MySQL 8.0 có native RLS policy giống CREATE POLICY của PostgreSQL không?

**Đáp án:** **Không.** Có thể kết hợp views, grants và kiểm soát ứng dụng, nhưng không tương đương native RLS.

**Câu 10.** Oracle Data Redaction có thay thế VPD không?

**Đáp án:** **Không.** Redaction che giá trị; VPD lọc hàng bằng predicate policy.

**Câu 11.** SQLite view có phải ranh giới bảo mật nếu người dùng mở trực tiếp file database không?

**Đáp án:** **Không.** SQLite core không có GRANT/RLS; cần bảo vệ file và đường truy cập ở OS/ứng dụng.

**Câu 12.** Prepared statement có tự xác thực tenant_id được truyền vào không?

**Đáp án:** **Không.** Nó ngăn dữ liệu bị hiểu thành cú pháp SQL, nhưng authorization vẫn phải được xác minh.

## 24. Ghi nhớ cốt lõi

**Bảo vệ hàng, cột và view là ba vấn đề liên quan nhưng khác nhau.**

- **Quyền cột** quyết định role được đọc/sửa trường nào.
- **RLS/VPD** quyết định role được nhìn thấy hoặc tác động hàng nào.
- **View** công bố giao diện dữ liệu đã chọn cột, đổi tên, lọc hoặc tính toán.
- **Masking/redaction** che cách giá trị hiển thị trong một số ngữ cảnh; không tự thay thế authorization.

Trên **PostgreSQL**, phối hợp GRANT/REVOKE, column privileges, RLS với **USING/WITH CHECK**, hiểu table owner và **BYPASSRLS**, đồng thời kiểm tra view mặc định với **security_invoker** và **security_barrier**. Trên **SQL Server**, dùng Security Policy với filter/block predicate và kiểm soát SESSION_CONTEXT. Trên **MySQL**, dùng column grants, view DEFINER/INVOKER và CHECK OPTION, nhưng không giả định có native RLS tương đương. Trên **Oracle**, VPD/DBMS_RLS có thể áp dụng predicate theo application context; view và Data Redaction giải quyết nhu cầu khác nhau. Trên **SQLite**, quyền file và lớp ứng dụng giữ vai trò trung tâm vì core không có users/GRANT/RLS.

Cuối cùng, **đừng kiểm thử chính sách bằng tài khoản quản trị rồi kết luận dữ liệu đã an toàn**. Hãy kiểm tra bằng role thực tế, cả truy vấn được phép lẫn bị từ chối, qua bảng gốc, view, routine, connection pool và các đường export/backup. Bind parameter giúp chống SQL injection nhưng không thay xác thực tenant; session context chỉ đáng tin khi được thiết lập từ danh tính đã kiểm chứng. Một thiết kế an toàn cần mọi lớp quyền cùng khớp với hợp đồng truy cập của ứng dụng.
