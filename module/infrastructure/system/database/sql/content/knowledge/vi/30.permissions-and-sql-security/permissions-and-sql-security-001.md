# Người dùng, vai trò và nguyên tắc cấp quyền tối thiểu

Một ứng dụng bán hàng cần đọc danh sách đơn, tạo đơn mới và cập nhật trạng thái xử lý. Điều đó **không có nghĩa** tài khoản kết nối database của ứng dụng cần quyền xóa tất cả dữ liệu, sửa bảng khách hàng, tạo thủ tục có đặc quyền cao hoặc quản lý tài khoản khác. Nếu ứng dụng bị lỗi hoặc một kẻ tấn công khai thác lỗ hổng SQL injection, các quyền thừa sẽ làm **phạm vi thiệt hại lớn hơn**.

**Nguyên tắc cấp quyền tối thiểu** (*principle of least privilege*) yêu cầu mỗi người dùng, ứng dụng hoặc quy trình chỉ nhận **những quyền thực sự cần để hoàn thành nhiệm vụ**, trên **đúng đối tượng** và trong **thời gian cần thiết**. Quyền truy cập phải được xem xét lại khi vai trò công việc thay đổi.

Bài học **Database SQL → Quyền và SQL an toàn** tập trung vào:

- Phân biệt **người dùng/định danh**, **vai trò** và **quyền**; ai đăng nhập, ai sở hữu đối tượng, ai được phép làm gì.
- Sử dụng `CREATE ROLE`, `LOGIN`/`NOLOGIN`, `GRANT`, `REVOKE` và **role membership** trong PostgreSQL.
- Phân quyền theo **database → schema → table/view → column → sequence → function**, thay vì cấp quyền toàn database.
- Hiểu `PUBLIC`, quyền kế thừa, `SET ROLE`, `WITH GRANT OPTION`, quyền mặc định và quyền của owner.
- Kiểm tra quyền thực tế bằng các hàm/catalog PostgreSQL; thử hành vi được phép và bị từ chối.
- Bảo vệ dữ liệu nhiều tenant bằng **row-level security (RLS)** khi cần, và tránh lỗ hổng từ `SECURITY DEFINER`, `search_path` hay quyền mặc định của function.
- So sánh PostgreSQL, MySQL, SQL Server, Oracle và SQLite; thực hành với bài tập có lời giải.

**Ngôn ngữ SQL chính của bài: PostgreSQL.** Các câu tạo role và cấp quyền cần chạy bằng **tài khoản quản trị/owner có thẩm quyền** trên **database sandbox**. Không chạy nguyên các ví dụ quản trị quyền trên production, không sửa quyền của tài khoản thật và không lưu mật khẩu thật trong bài hoặc repository.

## 1. Xác thực khác phân quyền

Hai câu hỏi liên quan nhưng không giống nhau:

1. **Authentication — xác thực:** kết nối này **là ai**? Họ có thông tin xác thực phù hợp không?
2. **Authorization — phân quyền:** định danh đã xác thực **được phép thực hiện thao tác nào** trên đối tượng nào?

Ví dụ:

~~~text
             Ung dung ban hang
                     |
          Ket noi va xac thuc
                     |
                     v
              app_order_user
                     |
               Role membership
                     |
                     v
               order_writer
                     |
                     v
          USAGE schema sales
          SELECT id, status
          INSERT columns can thiet
          UPDATE status
                     |
                     x
          DROP TABLE / DELETE all
          SELECT thong tin bi mat
~~~

Ứng dụng **đăng nhập được** chưa đủ để `SELECT` một bảng. Ngược lại, một role có quyền `SELECT` nhưng **không có `LOGIN`** không tự trở thành một tài khoản có thể đăng nhập trực tiếp.

### 1.1. Các thành phần thường gặp

| Khái niệm | Mục đích |
| --- | --- |
| **Identity / account** | Định danh của người hoặc dịch vụ được xác thực |
| **Role** | Tập thuộc tính và quyền; có thể dùng làm nhóm quyền |
| **Privilege** | Hành động được phép: `SELECT`, `INSERT`, `UPDATE`, `EXECUTE`... |
| **Membership** | Role này là thành viên của role khác, có thể thừa hưởng/sử dụng quyền theo quy tắc DBMS |
| **Object owner** | Role sở hữu bảng, schema hoặc routine, có quyền quản lý đặc biệt |
| **Grantor** | Role thực hiện việc cấp quyền |
| **Grantee** | Role nhận quyền |
| **PUBLIC** | Pseudo-role đại diện cho mọi role trong PostgreSQL |
| **Security policy** | Điều kiện bổ sung như RLS, giới hạn hàng nào role được phép nhìn/sửa |

**Tài khoản, nhóm vai trò và đối tượng dữ liệu phải được thiết kế cùng nhau.** Một kết nối chạy với tài khoản có quyền quá rộng thì cả chương trình có thể dùng các quyền đó, dù giao diện người dùng chỉ hiện vài nút.

## 2. PostgreSQL: user và role là một hệ thống

Trong PostgreSQL, `CREATE ROLE` là cơ chế tạo định danh/nhóm quyền. Một role có thuộc tính `LOGIN` có thể đăng nhập khi hệ thống xác thực cho phép; role `NOLOGIN` phù hợp làm **nhóm quyền**.

~~~sql
-- PostgreSQL: mot role lam nhom quyen, khong dang nhap truc tiep.
CREATE ROLE lab_r373_report_reader NOLOGIN;

-- PostgreSQL: mot role co kha nang dang nhap.
-- Khong co password trong vi du; administrator phai provision
-- authentication an toan neu muon dang nhap that.
CREATE ROLE lab_r373_report_account LOGIN;
~~~

Một cách viết PostgreSQL tương đương về ý định đăng nhập là:

~~~sql
-- CREATE USER la dang tien cua CREATE ROLE ... LOGIN.
-- Chi minh hoa, khong tao them tai khoan neu khong can.
-- CREATE USER lab_r373_another_account;
~~~

**`LOGIN` không có nghĩa tài khoản đã có mật khẩu.** Ví dụ tạo account không gắn password nhằm tránh đưa bí mật vào script; nó chỉ có thể kết nối nếu cơ chế xác thực được cấu hình phù hợp. Trong hệ thống thật, tài khoản dịch vụ cần thông tin xác thực được cấp phát qua **secret manager, cơ chế quản lý định danh hoặc quy trình bảo mật**.

### 2.1. Một người có thể mang nhiều role

Ví dụ nhân viên báo cáo có tài khoản `lab_r373_report_account`, còn bộ quyền báo cáo được định nghĩa trên `lab_r373_report_reader`. Ta có thể:

~~~sql
GRANT lab_r373_report_reader TO lab_r373_report_account;
~~~

Đây là **cấp membership role cho role**, không phải một câu `GRANT SELECT ON table`. Các quyền mà `lab_r373_report_reader` được cấp có thể được sử dụng/kế thừa theo **thuộc tính role và tùy chọn membership** của PostgreSQL.

### 2.2. PostgreSQL không phân biệt “user object” và “role object” như hai bảng tài khoản riêng

Không cần tạo một `USER` rồi tạo thêm một đối tượng `ROLE` định danh khác để cùng tài khoản có quyền. Trong PostgreSQL, user về thực chất là **role có khả năng LOGIN**. Các DBMS khác (đặc biệt SQL Server) có mô hình user/login riêng.

### 2.3. Những thuộc tính nguy hiểm cần hạn chế

| Thuộc tính PostgreSQL | Ý nghĩa | Dùng cho ứng dụng bình thường? |
| --- | --- | --- |
| `LOGIN` | Có thể đăng nhập khi authentication chấp nhận | Có, cho account cần kết nối |
| `NOLOGIN` | Không trực tiếp đăng nhập | Có, nhóm quyền |
| `SUPERUSER` | Quyền quản trị rất mạnh, vượt nhiều kiểm soát | **Không** |
| `CREATEDB` | Có thể tạo database | Thường **không** |
| `CREATEROLE` | Có thể tạo/quản lý role theo quy tắc phiên bản | Thường **không** |
| `BYPASSRLS` | Bỏ qua row-level security | **Không** cho tài khoản bị RLS bảo vệ |
| `REPLICATION` | Quyền liên quan replication | Không nếu không làm replication |
| `INHERIT` / `NOINHERIT` | Ảnh hưởng tới kế thừa quyền từ role thành viên | Cần thiết kế theo ý định |

Đừng tạo `SUPERUSER` chỉ để hết lỗi `permission denied`. Lỗi thường chỉ ra **một quyền cần được xác định và cấp đúng chỗ**.

## 3. Thiết kế một ma trận quyền trước khi viết GRANT

Giả sử hệ thống có bảng `customers`, `orders` và `audit_events`.

| Công việc | Cần đọc gì? | Cần ghi gì? | Tuyệt đối không cần |
| --- | --- | --- | --- |
| **Người xem báo cáo** | ID khách, mã khách, tên; cột báo cáo đơn hàng | Không | Email riêng tư, sửa/xóa đơn, quản lý role |
| **Dịch vụ nhận đơn** | ID, trạng thái đơn để xác nhận | Chèn đơn, đổi trạng thái | Xem toàn bộ bảng khách, xóa bảng |
| **Kiểm toán viên** | Event audit | Không | Sửa/xóa audit, sửa thông tin khách |
| **Người triển khai schema** | Metadata và đối tượng cần triển khai | DDL theo quy trình | Tài khoản ứng dụng không cần quyền deploy |

**Ma trận quyền là hợp đồng nghiệp vụ.** Nếu app chỉ được cập nhật `order_status`, đừng cấp `UPDATE` trên cả bảng vì điều đó còn cho phép đổi `total_amount` hoặc `customer_id` theo quyền PostgreSQL tương ứng.

### 3.1. Quyền là phép giao của nhiều lớp

Để đọc một cột trong một bảng PostgreSQL, người dùng thường cần:

~~~text
Co the ket noi database?
          |
          v
Co USAGE tren schema?
          |
          v
Co SELECT tren bang hoac cot?
          |
          v
Co bi RLS loc hang khong?
          |
          v
Truy van co hop le theo cac rang buoc va chinh sach khac?
          |
          v
Ket qua
~~~

Một `GRANT SELECT` trên bảng không tự cấp `USAGE` trên schema. Ngược lại, `GRANT USAGE ON SCHEMA` cũng **không** tự cấp `SELECT` trên mọi bảng trong schema.

## 4. Khởi tạo sandbox để thực hành

Các lệnh trong mục này cần chạy dưới **owner/administrator** có quyền tạo schema và bảng. Đối với `CREATE ROLE` ở mục sau, tài khoản cần quyền quản trị role phù hợp. Nếu không có quyền quản trị, hãy học bằng script và nhờ người quản trị tạo **các role thử nghiệm**, không xin superuser trên môi trường dùng chung.

### 4.1. Tạo schema riêng

~~~sql
CREATE SCHEMA lab_r373;
~~~

Schema giúp nhóm đối tượng của bài và tách tên khỏi các bảng production. Chúng ta sẽ ghi rõ tên schema trong SQL, ví dụ `lab_r373.orders`, để tránh phụ thuộc vào `search_path` không rõ ràng.

### 4.2. Tạo ba bảng

~~~sql
CREATE TABLE lab_r373.customers (
    customer_id INTEGER PRIMARY KEY,
    customer_code TEXT NOT NULL UNIQUE,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL
);

CREATE TABLE lab_r373.orders (
    order_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id INTEGER NOT NULL
        REFERENCES lab_r373.customers(customer_id),
    order_status TEXT NOT NULL
        CHECK (order_status IN ('NEW', 'PAID', 'CANCELLED')),
    total_amount NUMERIC(12, 2) NOT NULL
        CHECK (total_amount >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE lab_r373.audit_events (
    event_id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL,
    event_name TEXT NOT NULL,
    event_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

`email` là dữ liệu riêng tư minh họa: người làm báo cáo trong bài **không cần quyền xem** cột đó. Bảng `audit_events` được giữ riêng để chỉ role kiểm toán đọc.

### 4.3. Nạp dữ liệu

~~~sql
INSERT INTO lab_r373.customers
    (customer_id, customer_code, full_name, email)
VALUES
    (1, 'C001', 'An Nguyen',  'an.example@invalid.test'),
    (2, 'C002', 'Binh Tran',  'binh.example@invalid.test'),
    (3, 'C003', 'Chi Le',     'chi.example@invalid.test');

INSERT INTO lab_r373.orders
    (customer_id, order_status, total_amount)
VALUES
    (1, 'PAID', 120000.00),
    (1, 'NEW',   50000.00),
    (2, 'PAID', 220000.00),
    (3, 'CANCELLED', 80000.00);

INSERT INTO lab_r373.audit_events
    (event_id, order_id, event_name)
VALUES
    (1, 1, 'ORDER_CREATED'),
    (2, 1, 'PAYMENT_CONFIRMED'),
    (3, 2, 'ORDER_CREATED');
~~~

Các địa chỉ có miền `invalid.test` chỉ dùng làm **dữ liệu giả**, không đại diện người thật. `order_id` được sinh tự động, trên bảng mới các đơn mẫu thường nhận ID từ 1 đến 4.

Kiểm tra với owner:

~~~sql
SELECT
    o.order_id,
    c.customer_code,
    o.order_status,
    o.total_amount
FROM lab_r373.orders AS o
JOIN lab_r373.customers AS c
    ON c.customer_id = o.customer_id
ORDER BY o.order_id;
~~~

| order_id | customer_code | order_status | total_amount |
| ---: | --- | --- | ---: |
| 1 | C001 | PAID | 120000.00 |
| 2 | C001 | NEW | 50000.00 |
| 3 | C002 | PAID | 220000.00 |
| 4 | C003 | CANCELLED | 80000.00 |

## 5. Tạo nhóm quyền và tài khoản thử nghiệm

Chạy khi bạn có quyền quản trị role trong sandbox:

~~~sql
-- Nhom quyen, khong dang nhap truc tiep.
CREATE ROLE lab_r373_order_reader NOLOGIN;
CREATE ROLE lab_r373_order_writer NOLOGIN;
CREATE ROLE lab_r373_audit_reader NOLOGIN;

-- Hai account co the dang nhap neu he thong xac thuc
-- duoc provision theo chinh sach an toan.
CREATE ROLE lab_r373_app_login LOGIN;
CREATE ROLE lab_r373_report_login LOGIN;
CREATE ROLE lab_r373_audit_login LOGIN;

-- Account nhan quyen thong qua membership.
GRANT lab_r373_order_writer TO lab_r373_app_login;
GRANT lab_r373_order_reader TO lab_r373_report_login;
GRANT lab_r373_audit_reader TO lab_r373_audit_login;
~~~

**Không có câu `PASSWORD '...'` trong bài.** Account LOGIN mới không đương nhiên có thể kết nối bằng mật khẩu; quản trị viên cần cấu hình xác thực/secret thích hợp để sử dụng thật. Ví dụ tạo account nhằm giải thích **phân quyền**, không dạy cách phát tán mật khẩu.

### 5.1. Tại sao không cấp quyền trực tiếp cho từng người?

Giả sử có 100 nhân viên báo cáo. Nếu cấp `SELECT` riêng cho từng người trên 20 bảng, việc kiểm kê quyền và chuyển vị trí công tác dễ sai. Với role nhóm:

~~~text
report_login_1 ----\
report_login_2 -----+--> order_reader --> SELECT cac cot bao cao
report_login_3 ----/
~~~

Khi bổ sung một bảng báo cáo cần thiết, có thể cập nhật quyền **cho nhóm**, thay vì lặp 100 câu GRANT. Khi một nhân viên rời nhóm, thu hồi **membership** sẽ giảm đường đi của quyền ấy, trừ khi họ còn quyền qua một nhánh khác.

### 5.2. Một role có thể nhận nhiều nhóm

Một tài khoản có thể là thành viên của hai hoặc nhiều role nhóm. Hệ quả là **tổng quyền hiệu lực có thể rộng hơn từng nhóm riêng lẻ**. Khi audit quyền, phải xem cả **membership trực tiếp, gián tiếp, PUBLIC, quyền trực tiếp và owner privileges**.

## 6. GRANT USAGE trên schema trước khi cấp quyền đối tượng

Để role truy cập đối tượng đặt trong `lab_r373`:

~~~sql
GRANT USAGE ON SCHEMA lab_r373
TO
    lab_r373_order_reader,
    lab_r373_order_writer,
    lab_r373_audit_reader;
~~~

`USAGE` cho phép tham chiếu những đối tượng trong schema khi role có quyền tương ứng trên đối tượng. Nó **không cấp `CREATE` trong schema**.

### 6.1. USAGE khác CREATE

| Schema privilege | Ý nghĩa cơ bản |
| --- | --- |
| `USAGE` | Cho phép tra cứu/tham chiếu tên đối tượng trong schema, với quyền đối tượng phù hợp |
| `CREATE` | Có thể tạo đối tượng trong schema, theo các kiểm soát liên quan |

Một tài khoản chỉ cần đọc báo cáo **không cần `CREATE ON SCHEMA`**. Nếu có `CREATE` trong schema được các routine có quyền cao tin cậy, kẻ tấn công có thể thử tạo đối tượng trùng tên để gây nhầm lẫn `search_path`.

### 6.2. CONNECT là quyền cấp database, không phải quyền trên schema

Trong PostgreSQL có thể cấp:

~~~sql
-- MINH HOA, thay training_db bang ten database SANDBOX that.
-- GRANT CONNECT ON DATABASE training_db TO lab_r373_app_login;
~~~

Quyền `CONNECT` kiểm soát khả năng kết nối **database tương ứng**, khác `USAGE` của schema. Trong nhiều cấu hình PostgreSQL, `PUBLIC` vốn có `CONNECT` mặc định trên database; không được suy rằng role chỉ có thể kết nối sau một GRANT CONNECT tường minh.

**Không tự ý `REVOKE CONNECT ... FROM PUBLIC` trên database dùng chung**: thay đổi đó có thể làm các kết nối dịch vụ khác mất quyền. Hãy thiết kế quyền database với quản trị viên và kiểm tra tác động trước khi thay đổi.

## 7. GRANT SELECT ở cấp bảng và cấp cột

### 7.1. Role báo cáo chỉ được xem cột cần thiết

~~~sql
GRANT SELECT (
    order_id,
    customer_id,
    order_status,
    total_amount,
    created_at
)
ON lab_r373.orders
TO lab_r373_order_reader;

GRANT SELECT (
    customer_id,
    customer_code,
    full_name
)
ON lab_r373.customers
TO lab_r373_order_reader;
~~~

Role báo cáo có thể đọc những cột đã được cấp:

~~~sql
SELECT
    o.order_id,
    c.customer_code,
    c.full_name,
    o.total_amount
FROM lab_r373.orders AS o
JOIN lab_r373.customers AS c
    ON c.customer_id = o.customer_id
WHERE o.order_status = 'PAID'
ORDER BY o.order_id;
~~~

Kết quả dữ liệu mẫu:

| order_id | customer_code | full_name | total_amount |
| ---: | --- | --- | ---: |
| 1 | C001 | An Nguyen | 120000.00 |
| 3 | C002 | Binh Tran | 220000.00 |

### 7.2. Tại sao không cấp SELECT trên toàn customers?

~~~sql
-- KHONG CHON CAU NAY cho nhom chi can bao cao khong PII:
-- GRANT SELECT ON lab_r373.customers TO lab_r373_order_reader;
~~~

`GRANT SELECT ON table` cấp quyền đọc **bảng như một đối tượng**, bao gồm các cột hiện có và các cột được thêm về sau theo ngữ nghĩa quyền bảng. Nếu tương lai có cột `identity_number` hoặc `bank_account`, role có SELECT toàn bảng có thể đọc thêm dữ liệu không dự kiến.

Ngược lại, với **column-level grant** trong bài, role báo cáo **không được cấp quyền đọc `email`**:

~~~sql
-- DU KIEN BI TU CHOI neu chay duoi report role,
-- khi role khong co quyen tu duong khac.
-- SELECT email FROM lab_r373.customers;
~~~

Trong PostgreSQL, `SELECT * FROM lab_r373.customers` cũng có thể thất bại dưới role chỉ được đọc vài cột, vì `*` mở rộng đến **email**. Hãy liệt kê cột có chủ đích thay vì dùng `SELECT *` trong API cần giới hạn dữ liệu.

### 7.3. Quyền cột không thay thế row filtering

Column-level privilege kiểm soát **cột nào được đọc**. Nó không tự giới hạn **khách nào** được xem. Nếu nhân viên chỉ được nhìn đơn của chi nhánh mình, cần thêm mô hình dữ liệu và cơ chế như **RLS**, hoặc view/API có kiểm soát.

## 8. GRANT INSERT và UPDATE ở cấp cột

Dịch vụ tiếp nhận đơn cần:

- Thêm đơn với `customer_id`, `order_status`, `total_amount`.
- Đọc `order_id` và `order_status` để xác nhận/kiểm tra.
- Đổi `order_status` khi nghiệp vụ cho phép.
- **Không** sửa `total_amount` hoặc xóa đơn bằng quyền của role.

~~~sql
GRANT INSERT (
    customer_id,
    order_status,
    total_amount
)
ON lab_r373.orders
TO lab_r373_order_writer;

GRANT SELECT (
    order_id,
    order_status
)
ON lab_r373.orders
TO lab_r373_order_writer;

GRANT UPDATE (
    order_status
)
ON lab_r373.orders
TO lab_r373_order_writer;
~~~

### 8.1. INSERT chỉ chèn những cột được phép

~~~sql
-- Chay bang role order_writer trong transaction sandbox.
BEGIN;

INSERT INTO lab_r373.orders (
    customer_id,
    order_status,
    total_amount
)
VALUES (2, 'NEW', 75000.00);

ROLLBACK;
~~~

`order_id` được sinh từ identity, `created_at` dùng DEFAULT. Câu lệnh không nêu hai cột đó trong danh sách INSERT.

Trong PostgreSQL, **identity column** có ngữ nghĩa cấp quyền khác việc gọi trực tiếp `nextval` trên một sequence `SERIAL`. Không suy từ ví dụ identity rằng mọi bảng dùng sequence đều không cần quyền sequence.

### 8.2. UPDATE cột được phép, nhưng cần quyền đọc cột dùng trong điều kiện

~~~sql
BEGIN;

UPDATE lab_r373.orders
SET order_status = 'PAID'
WHERE order_id = 2
  AND order_status = 'NEW'
RETURNING order_id, order_status;

ROLLBACK;
~~~

Để đọc `order_id` và `order_status` trong `WHERE`/`RETURNING`, role phải có quyền SELECT tương ứng; lệnh GRANT ở trên đã cấp.

### 8.3. UPDATE tiền phải bị từ chối

~~~sql
-- DU KIEN PERMISSION DENIED voi order_writer neu khong co
-- quyen UPDATE total_amount qua role, PUBLIC hay duong khac.
-- UPDATE lab_r373.orders
-- SET total_amount = 1
-- WHERE order_id = 1;
~~~

Đây là **quyền cấp cột**. Dù ứng dụng bị lỗi và cố cập nhật giá trị tiền, database vẫn có một lớp từ chối nếu kết nối chỉ có role được thiết kế.

### 8.4. Quyền INSERT không đồng nghĩa quyền SELECT

Một role có thể **chèn dữ liệu** mà không được phép xem toàn bộ nội dung bảng. Tuy nhiên nếu câu `INSERT ... RETURNING` trả các cột, role cần quyền SELECT thích hợp trên các cột được trả.

Ngoài ra, một FK trên `customer_id` được PostgreSQL kiểm tra theo cơ chế ràng buộc nội bộ; role chỉ chèn vào `orders` **không nhất thiết cần `SELECT` bảng `customers`** chỉ để tham chiếu ID hợp lệ. Nhưng nếu ứng dụng muốn tự hiển thị tên khách, nó cần quyền đọc tương ứng.

## 9. Role kiểm toán: đọc audit nhưng không được sửa

~~~sql
GRANT SELECT ON lab_r373.audit_events
TO lab_r373_audit_reader;
~~~

Account thuộc nhóm kiểm toán có thể:

~~~sql
SELECT event_id, order_id, event_name, event_at
FROM lab_r373.audit_events
ORDER BY event_id;
~~~

Nhưng không được cấp:

~~~sql
-- KHONG CAP neu muc dich chi la doc:
-- GRANT INSERT, UPDATE, DELETE
-- ON lab_r373.audit_events TO lab_r373_audit_reader;
~~~

**Audit đáng tin cậy không chỉ là cấm UPDATE cho kiểm toán viên.** Ứng dụng ghi audit, owner, DBA và các routine đặc quyền cần được phân quyền, giám sát và kiểm soát thay đổi riêng. Trong hệ thống có yêu cầu chống sửa/xóa mạnh, có thể cần cơ chế append-only, lưu ngoài hệ thống hoặc audit service độc lập.

## 10. Thử quyền hiệu lực trong một session

Để thử bằng SQL, phải thực sự thực thi với **định danh bị hạn chế**, không phải tài khoản owner vốn có quyền cao.

Trong PostgreSQL:

~~~sql
SELECT
    session_user,
    current_user,
    current_role;
~~~

- `session_user` thường phản ánh định danh mở session ban đầu.
- `current_user`/`current_role` phản ánh role hiệu lực hiện tại, có thể thay đổi bằng `SET ROLE` khi được phép.

### 10.1. SET ROLE không dành cho bất kỳ ai

~~~sql
-- Chi chay neu session co quyen SET role nay.
SET ROLE lab_r373_report_login;

SELECT current_user, session_user;

SELECT
    o.order_id,
    o.total_amount
FROM lab_r373.orders AS o
ORDER BY o.order_id;

RESET ROLE;
~~~

**Điều kiện:** session cần có quyền chuyển sang role đó theo membership/tùy chọn `SET` và phiên bản PostgreSQL, hoặc là một phiên quản trị có thẩm quyền. `SET ROLE` **không** cho phép người dùng bất kỳ mạo danh role khác.

Để thử như một account thực sự, tốt nhất là **kết nối bằng account thử nghiệm đã được provisioning an toàn**. `SET ROLE` hữu ích cho quản trị viên hoặc thành viên được phép giả lập quyền nhưng không phải một phép thay thế hoàn hảo cho kiểm thử authentication.

### 10.2. Thử thao tác bị từ chối

Trong phiên report role, câu sau dự kiến bị từ chối:

~~~sql
-- KHONG CHAY trong mot transaction ban con muon tiep tuc:
-- SELECT email FROM lab_r373.customers;
~~~

Nếu gặp `permission denied` trong transaction PostgreSQL, transaction có thể vào trạng thái **aborted**; cần `ROLLBACK` trước khi chạy tiếp. Trong môi trường học, hãy thử **một câu lỗi ở một thời điểm**, không chạy cả script dài rồi ngạc nhiên thấy các câu sau cũng bị từ chối.

### 10.3. Đừng kết luận role không có quyền chỉ vì một lần test lỗi

Lỗi có thể đến từ **schema USAGE**, quyền cột, table privilege, RLS, function EXECUTE hoặc transaction đang lỗi. Phân tích từng lớp và xem role hiệu lực thay vì đoán rằng thiếu `SELECT` trên bảng.

## 11. Vai trò nhóm, membership và INHERIT

Trong PostgreSQL:

~~~sql
GRANT lab_r373_order_reader TO lab_r373_report_login;
~~~

là một phép **gán membership**.

Thông thường, các quyền từ role nhóm có thể được sử dụng theo cấu hình `INHERIT`/membership; nhưng một role có membership **không đồng nghĩa mọi quyền được kế thừa trong mọi ngữ cảnh**. Từ PostgreSQL 16, tùy chọn membership như `INHERIT`, `SET`, `ADMIN` được diễn đạt rõ hơn cho từng membership; các phiên bản cũ có quy tắc kế thừa liên quan thuộc tính role.

### 11.1. SET ROLE chuyển role hiệu lực

~~~sql
-- Chi chay neu co quyen SET role.
SET ROLE lab_r373_order_reader;
SELECT current_user, session_user;
RESET ROLE;
~~~

`SET ROLE` đổi **ngữ cảnh quyền và current_user**, không phải một câu `GRANT` hay cấp membership mới. Khi session không có quyền SET vào role đó, PostgreSQL từ chối.

### 11.2. Quyền có thể đến từ nhiều đường

~~~text
report_login
    |
    +--> order_reader --SELECT--> orders
    |
    +--> another_group --SELECT--> customers.email
    |
    +--> PUBLIC -------EXECUTE--> some_function
~~~

Thu hồi quyền từ `order_reader` **không loại bỏ** quyền vẫn có từ `another_group` hoặc `PUBLIC`. Muốn biết người dùng thực sự làm được gì, phải xem toàn bộ đường cấp quyền.

### 11.3. Vai trò quản trị không nên trở thành tài khoản ứng dụng

Tài khoản deploy/migration có thể cần `CREATE`/`ALTER` trong schema khi phát hành phiên bản mới, nhưng ứng dụng chạy hằng ngày **không cần** những quyền ấy. Tách vai trò:

~~~text
deployment_role -> DDL trong schema duoc phep
app_runtime     -> DML gioi han
report_reader   -> SELECT gioi han
audit_reader    -> SELECT audit
~~~

Tách định danh giảm khả năng một lỗi runtime sửa cấu trúc database.

## 12. REVOKE: thu hồi đúng quyền và hiểu hiệu lực

Ví dụ thu hồi quyền đọc một cột đã cấp:

~~~sql
REVOKE SELECT (full_name)
ON lab_r373.customers
FROM lab_r373_order_reader;
~~~

Sau câu này, `lab_r373_order_reader` không còn quyền SELECT `full_name` **từ grant cấp cột ấy**. Tuy nhiên role có thể vẫn đọc được nếu tồn tại quyền khác qua một role khác hoặc `GRANT SELECT` cấp bảng.

Để tiếp tục các ví dụ của bài cần tên khách:

~~~sql
GRANT SELECT (full_name)
ON lab_r373.customers
TO lab_r373_order_reader;
~~~

### 12.1. REVOKE không phải DENY

PostgreSQL không có một lệnh `DENY` chung tương đương SQL Server cho quyền đối tượng. `REVOKE` **rút một đường cấp quyền**, không tạo một lệnh cấm có ưu tiên tuyệt đối nếu người dùng còn quyền từ đường khác.

Ví dụ:

~~~sql
-- Neu mot role da duoc cap SELECT truc tiep va qua nhom,
-- REVOKE truc tiep khong nhat thiet xoa quyen qua nhom.
~~~

Muốn giảm quyền thật, cần điều chỉnh **mọi nguồn quyền liên quan**.

### 12.2. REVOKE ALL không nhất thiết xóa quyền owner

Role sở hữu một đối tượng có các khả năng quản lý đặc biệt, bao gồm quyền thay đổi hoặc xóa đối tượng theo quy tắc PostgreSQL. **Không thể biến owner thành role hoàn toàn không có quyền quản lý chỉ bằng REVOKE ALL PRIVILEGES trên chính đối tượng của họ.**

Vì vậy không nên để tài khoản runtime là **owner** của toàn bộ schema/table nếu mục tiêu là giới hạn khả năng thay đổi cấu trúc.

### 12.3. Khi tách quyền của ứng dụng

Giả sử ứng dụng trước đây được DELETE nhưng công việc không cần nữa:

~~~sql
REVOKE DELETE ON lab_r373.orders
FROM lab_r373_order_writer;
~~~

Câu lệnh chỉ bỏ quyền DELETE **nếu nó đã được cấp qua role này**. Không tự thu hồi những quyền tương đương từ `PUBLIC`, một role nhóm khác hoặc quyền owner.

## 13. PUBLIC: role đại diện cho mọi người

Trong PostgreSQL, `PUBLIC` không phải tài khoản có thể đăng nhập; nó là **pseudo-role** đại diện cho **mọi role**, kể cả role tạo sau này.

Ví dụ:

~~~sql
GRANT SELECT ON lab_r373.orders TO PUBLIC;
~~~

Nếu dùng câu này trong sandbox, **mọi role đủ điều kiện truy cập schema** có thể nhận quyền đọc bảng thông qua PUBLIC. Đây thường là phạm vi **quá rộng** đối với bảng đơn hàng.

Để rút quyền ấy:

~~~sql
-- Chi thuc hien khi biet chinh xac grant da ton tai va
-- xac dinh tac dong tren database thuc hanh.
REVOKE SELECT ON lab_r373.orders FROM PUBLIC;
~~~

### 13.1. Không phải mọi đối tượng có mặc định giống nhau

Trong PostgreSQL, quyền mặc định của các loại đối tượng có sự khác nhau; đặc biệt **function/procedure thường có EXECUTE cho PUBLIC theo mặc định**, trong khi bảng thường không được tự cấp SELECT cho PUBLIC theo cách tương tự.

Quyền trên schema `public` cũng phụ thuộc phiên bản/cách khởi tạo database; từ PostgreSQL 15, quyền `CREATE` cho PUBLIC trong schema `public` đã được thay đổi cho database được khởi tạo theo mặc định mới. **Không suy từ tên schema `public` rằng mọi người chắc chắn có CREATE hoặc chắc chắn không có CREATE trên một database đang chạy**. Phải kiểm tra thực tế.

### 13.2. Dùng GRANT PUBLIC khi dữ liệu thật sự công khai

PUBLIC có chỗ dùng hợp lệ cho **những đối tượng thực sự dành cho mọi role**, ví dụ một function tính toán vô hại theo chính sách tổ chức. Nhưng với dữ liệu cá nhân, số dư và các routine có tác dụng phụ, cần cấp cho **role cụ thể**.

## 14. GRANT OPTION: quyền cấp quyền cho người khác

Không chỉ có quyền `SELECT`, một role còn có thể được cấp khả năng **ủy quyền SELECT** cho role khác:

~~~sql
-- MINH HOA, chi cap khi that su muon uy quyen:
-- GRANT SELECT ON lab_r373.orders
-- TO lab_r373_reporting_manager WITH GRANT OPTION;
~~~

`WITH GRANT OPTION` cho phép grantee **cấp lại một quyền đối tượng** trong phạm vi phù hợp. Nó **không phải chỉ cho phép SELECT nhiều hàng hơn**.

Đối với membership role, PostgreSQL có cơ chế quản lý membership như `WITH ADMIN OPTION`; từ các phiên bản mới có thêm các tùy chọn membership chi tiết. **GRANT OPTION của quyền bảng** và **ADMIN OPTION của quyền quản lý membership** là hai năng lực khác nhau.

### 14.1. Vì sao nên hạn chế ủy quyền?

Nếu ứng dụng có quyền SELECT kèm GRANT OPTION, một tài khoản ứng dụng bị chiếm có thể cố **mở rộng quyền cho tài khoản khác**. App runtime bình thường chỉ cần **sử dụng** quyền, không cần **phân phát** quyền.

### 14.2. Thu hồi quyền đã ủy quyền

PostgreSQL có `REVOKE GRANT OPTION FOR ...` với hành vi `RESTRICT`/`CASCADE` theo dependency grant. Cần biết ai đã cấp lại quyền cho ai trước khi thu hồi, vì CASCADE có thể làm các grant phụ thuộc bị rút theo.

~~~sql
-- Minh hoa, can co role manager va grant ban dau:
-- REVOKE GRANT OPTION FOR SELECT
-- ON lab_r373.orders
-- FROM lab_r373_reporting_manager CASCADE;
~~~

Không dùng CASCADE trên quyền production mà chưa xem tác động tới các grantee phụ thuộc.

## 15. Quyền trên sequence: dễ quên khi INSERT

Một bảng dùng `SERIAL` có thể gọi `nextval(...)` trên sequence liên quan. Role có `INSERT` vào bảng chưa chắc có quyền `USAGE` thích hợp trên sequence đó.

### 15.1. Ví dụ sequence riêng

~~~sql
CREATE SEQUENCE lab_r373.ticket_counter START WITH 100;
~~~

Quản trị viên cấp quyền cho nhóm cần lấy số ticket:

~~~sql
GRANT USAGE ON SEQUENCE lab_r373.ticket_counter
TO lab_r373_order_writer;
~~~

Khi thực thi dưới role có quyền:

~~~sql
SELECT nextval('lab_r373.ticket_counter') AS ticket_number;
~~~

`nextval` có thể cần quyền `USAGE` hoặc `UPDATE` trên sequence; `USAGE` phù hợp khi chỉ muốn lấy số tuần tự, không cấp các quyền sequence không cần thiết.

### 15.2. Không nhầm quyền sequence với quyền bảng

| Đối tượng | Quyền tiêu biểu |
| --- | --- |
| Table | `SELECT`, `INSERT`, `UPDATE`, `DELETE`, `TRUNCATE`, `REFERENCES`, `TRIGGER` |
| Sequence | `USAGE`, `SELECT`, `UPDATE` theo ngữ nghĩa thao tác |
| Schema | `USAGE`, `CREATE` |
| Database | `CONNECT`, `CREATE`, `TEMPORARY` |
| Function/procedure | `EXECUTE` |

Identity columns trong PostgreSQL có cơ chế cấp giá trị khác một lời gọi `nextval` trực tiếp của ứng dụng; không nên tự cấp `ALL ON ALL SEQUENCES` chỉ vì có một cột auto-generated.

### 15.3. Cấp ALL SEQUENCES có thể rộng quá mức

~~~sql
-- KHONG MAC DINH CAP:
-- GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA lab_r373
-- TO lab_r373_order_writer;
~~~

Nếu ứng dụng chỉ dùng một sequence, cấp trên **đúng sequence đó** sẽ hạn chế hơn.

## 16. Quyền EXECUTE trên function và procedure

Routine là một đối tượng có quyền thực thi:

~~~sql
GRANT EXECUTE
ON FUNCTION lab_r373.some_function(INTEGER)
TO lab_r373_order_reader;
~~~

Đoạn trên chỉ minh họa cú pháp; cần tạo function `some_function` trước khi thực thi.

### 16.1. Tạo một function chỉ đọc

~~~sql
CREATE OR REPLACE FUNCTION lab_r373.paid_order_count()
RETURNS BIGINT
LANGUAGE sql
STABLE
SECURITY INVOKER
AS $fn$
    SELECT COUNT(*)
    FROM lab_r373.orders
    WHERE order_status = 'PAID';
$fn$;
~~~

`SECURITY INVOKER` có nghĩa routine thực thi theo ngữ cảnh quyền người gọi, theo quy tắc PostgreSQL. Role có quyền EXECUTE nhưng **không có quyền đọc những cột mà thân hàm yêu cầu** vẫn có thể bị `permission denied` khi function chạy. **EXECUTE không phải giấy phép tự bỏ qua quyền bảng** đối với SECURITY INVOKER.

### 16.2. Function có thể mặc định cho PUBLIC EXECUTE

Đối với PostgreSQL, quyền EXECUTE cho PUBLIC trên function mới thường được cấp theo mặc định, trừ khi quyền mặc định của role tạo đã thay đổi.

Muốn function này chỉ dùng bởi nhóm báo cáo:

~~~sql
REVOKE ALL PRIVILEGES
ON FUNCTION lab_r373.paid_order_count()
FROM PUBLIC;

GRANT EXECUTE
ON FUNCTION lab_r373.paid_order_count()
TO lab_r373_order_reader;
~~~

Trong hệ thống triển khai thật, nên **tạo function và REVOKE quyền PUBLIC trong cùng một transaction**, để tránh có khoảng thời gian function mới được tạo nhưng chưa kịp khóa quyền.

### 16.3. CREATE FUNCTION có thể tạo đường đi đặc quyền

Nếu một function đọc bảng nhạy cảm dưới quyền owner và được cấp EXECUTE quá rộng, người dùng không có SELECT bảng vẫn có thể lấy thông tin qua output của function. Vì vậy cần review **nội dung và kết quả function**, không chỉ nhìn GRANT SELECT trực tiếp trên bảng.

## 17. SECURITY DEFINER: công cụ mạnh, có rủi ro

PostgreSQL có:

- `SECURITY INVOKER`: thực thi với quyền của người gọi (mặc định thường dùng).
- `SECURITY DEFINER`: thực thi với quyền của **owner của routine** theo quy tắc PostgreSQL.

### 17.1. Ví dụ có kiểm soát: chỉ trả tổng số khách

Nếu một ứng dụng không được xem danh sách email nhưng cần **số lượng khách**, chủ sở hữu routine có thể cung cấp một API trả **một số tổng hợp**:

~~~sql
BEGIN;

CREATE OR REPLACE FUNCTION lab_r373.customer_count()
RETURNS BIGINT
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, lab_r373, pg_temp
AS $fn$
    SELECT COUNT(*)
    FROM lab_r373.customers;
$fn$;

REVOKE ALL PRIVILEGES
ON FUNCTION lab_r373.customer_count()
FROM PUBLIC;

GRANT EXECUTE
ON FUNCTION lab_r373.customer_count()
TO lab_r373_order_reader;

COMMIT;
~~~

Khi role báo cáo gọi:

~~~sql
SELECT lab_r373.customer_count() AS number_of_customers;
~~~

trên dữ liệu ban đầu, kết quả là **3**. Function không trả email hoặc tên khách.

### 17.2. Vì sao cần cố định search_path?

Một `SECURITY DEFINER` function có quyền cao có thể bị lợi dụng nếu tên bảng/function không được giải quyết trong các schema đáng tin cậy, hoặc một người dùng thiếu tin cậy có thể tạo đối tượng trùng tên trong schema xuất hiện sớm trong `search_path`.

Ví dụ ở trên:

1. **Schema-qualify** bảng nguồn bằng `lab_r373.customers`.
2. Cố định `search_path` vào những schema đáng tin cậy, đặt `pg_temp` ở cuối theo chiến lược an toàn.
3. Không cấp `CREATE ON SCHEMA lab_r373` cho tài khoản không đáng tin.
4. Không dùng SQL động ghép trực tiếp input không tin cậy.

**SECURITY DEFINER không phải cách “sửa lỗi permission denied” tùy tiện.** Nó làm rộng quyền có thể thực hiện qua routine; phải kiểm tra cả **đầu vào, đầu ra, đường gọi, trạng thái phụ và quyền owner**.

### 17.3. RLS và SECURITY DEFINER cần xem xét cùng nhau

Nếu owner của function có quyền bỏ qua chính sách RLS trên bảng nguồn (ví dụ là table owner trong một số điều kiện, superuser hoặc `BYPASSRLS`), function SECURITY DEFINER có thể trả dữ liệu khác với truy vấn cùng bảng của người gọi. **Không giả định RLS của người gọi tự động áp dụng nguyên vẹn bên trong mọi SECURITY DEFINER function.**

## 18. Quyền của view thường: có thể tạo một giao diện hẹp

Một view có thể chỉ công bố **các cột cần đọc**:

~~~sql
CREATE VIEW lab_r373.customer_directory AS
SELECT
    customer_id,
    customer_code,
    full_name
FROM lab_r373.customers;

GRANT SELECT
ON lab_r373.customer_directory
TO lab_r373_order_reader;
~~~

Role báo cáo có thể dùng:

~~~sql
SELECT customer_code, full_name
FROM lab_r373.customer_directory
ORDER BY customer_code;
~~~

### 18.1. Quyền view và bảng gốc khác nhau

Theo hành vi mặc định truyền thống của PostgreSQL, truy cập bảng nguồn bên trong view thường dựa trên quyền **chủ sở hữu view**, trừ khi dùng chế độ như `security_invoker` ở PostgreSQL 15+ trong ngữ cảnh hỗ trợ.

Vì vậy một role **không được SELECT trực tiếp cột email** vẫn có thể dùng view được cấp, nhưng view chỉ trả các cột mà người tạo đã công bố. Ngược lại, nếu view vô tình `SELECT *` cả email, việc cấp SELECT view có thể làm lộ dữ liệu ngay cả khi role không có quyền đọc bảng gốc trực tiếp.

### 18.2. View không thay thế mọi chính sách bảo mật

Một view lọc theo điều kiện có thể là một phần của lớp truy cập, nhưng muốn đảm bảo cách biệt tenant và các truy vấn khác nhau, cần đánh giá **RLS, security_invoker, quyền underlying tables, quyền owner và các đường truy cập khác**. Không suy rằng thêm `WHERE tenant_id = ...` trong một view bất kỳ là đủ cho mọi mô hình tấn công.

## 19. Quyền mặc định: ALTER DEFAULT PRIVILEGES

Vấn đề: đã cấp SELECT trên tất cả bảng báo cáo hôm nay, nhưng **ngày mai triển khai một bảng mới**. Quyền đã cấp trên các bảng hiện tại **không tự áp dụng** cho bảng mới nếu không có chính sách mặc định.

Trong PostgreSQL:

~~~sql
-- Cap cho cac bang DA ton tai trong schema:
GRANT SELECT ON ALL TABLES IN SCHEMA lab_r373
TO lab_r373_order_reader;
~~~

**Câu này quá rộng với ví dụ của bài**, vì nó còn cấp SELECT toàn bảng `customers` bao gồm email, `audit_events` và các bảng tương lai không liên quan. **Không chạy** câu trên trong sandbox nếu mục tiêu giữ chính sách cấp cột tối thiểu.

### 19.1. Quyền hiện tại và quyền đối tượng tương lai là hai bài toán

Để minh họa cách chỉ cấp mặc định trên vùng báo cáo:

~~~sql
CREATE SCHEMA lab_r373_reporting;

GRANT USAGE ON SCHEMA lab_r373_reporting
TO lab_r373_order_reader;

ALTER DEFAULT PRIVILEGES
IN SCHEMA lab_r373_reporting
GRANT SELECT ON TABLES
TO lab_r373_order_reader;
~~~

Lệnh `ALTER DEFAULT PRIVILEGES` ở đây áp dụng cho **các đối tượng tương lai được tạo bởi role chạy lệnh** trong schema được chỉ định, không tự áp dụng cho mọi role creator khác. Nếu pipeline deploy bằng một role khác, phải cấu hình default privileges **cho đúng role tạo đối tượng**, với quyền quản trị thích hợp.

### 19.2. Kiểm tra với bảng mới

~~~sql
CREATE TABLE lab_r373_reporting.monthly_totals (
    month_start DATE NOT NULL,
    total_amount NUMERIC(14, 2) NOT NULL
);
~~~

Nếu tạo bảng với **cùng role đã thiết lập default privileges**, nhóm `lab_r373_order_reader` có thể nhận SELECT trên bảng mới qua quyền mặc định.

Không phải mọi bảng trong schema dữ liệu nghiệp vụ đều nên mở SELECT cho role báo cáo. Dùng **schema báo cáo riêng, view đã kiểm tra hoặc grant cụ thể** giúp giảm nguy cơ lộ cột nhạy cảm.

### 19.3. ALTER DEFAULT PRIVILEGES không hồi tố

Các bảng đã tồn tại **không tự đổi quyền** chỉ vì bạn cấu hình default privileges về sau. Cần GRANT/REVOKE riêng cho đối tượng cũ. PostgreSQL cũng có quy tắc khác nhau về default privilege **toàn cục theo creator** và **bổ sung theo schema**, đặc biệt với việc thu hồi quyền mặc định trên function.

### 19.4. Quyền EXECUTE mặc định của function phải xử lý đúng phạm vi

Nếu muốn những function mới do **role creator hiện tại** tạo không tự cấp EXECUTE cho PUBLIC, một mẫu:

~~~sql
-- Chay duoi role se TAO function ve sau, sau khi danh gia
-- chinh sach quyen cua role do.
ALTER DEFAULT PRIVILEGES
REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
~~~

Đây là điều chỉnh **default privileges ở phạm vi phù hợp của role tạo**, khác `REVOKE EXECUTE` trên một function hiện hữu. Trong PostgreSQL, `REVOKE` riêng theo schema **không thể xóa quyền mặc định toàn cục** chỉ bằng cách viết thêm `IN SCHEMA ...` nếu quyền PUBLIC vốn đến từ mặc định toàn cục.

**Không thay đổi default privileges của owner/deploy role trên production** mà chưa rà những function/ứng dụng cần quyền EXECUTE.

## 20. Row-level security: giới hạn hàng, không chỉ cột

Cấp SELECT trên một bảng nhiều tenant chưa chắc đủ an toàn: một role có thể nhìn thấy hàng của **mọi tenant**. PostgreSQL hỗ trợ **row-level security (RLS)**, thêm chính sách xác định **hàng được đọc/sửa** theo role và điều kiện.

### 20.1. Dữ liệu mẫu nhiều tenant

~~~sql
CREATE TABLE lab_r373.tenant_documents (
    doc_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_role TEXT NOT NULL,
    title TEXT NOT NULL
);

INSERT INTO lab_r373.tenant_documents (tenant_role, title)
VALUES
    ('lab_r373_tenant_a', 'Hop dong cua A'),
    ('lab_r373_tenant_a', 'Bao cao cua A'),
    ('lab_r373_tenant_b', 'Hop dong cua B');
~~~

Tạo hai account tenant thử nghiệm:

~~~sql
CREATE ROLE lab_r373_tenant_a LOGIN;
CREATE ROLE lab_r373_tenant_b LOGIN;

GRANT USAGE ON SCHEMA lab_r373
TO lab_r373_tenant_a, lab_r373_tenant_b;

GRANT SELECT
ON lab_r373.tenant_documents
TO lab_r373_tenant_a, lab_r373_tenant_b;

GRANT INSERT (tenant_role, title)
ON lab_r373.tenant_documents
TO lab_r373_tenant_a, lab_r373_tenant_b;

GRANT UPDATE (title)
ON lab_r373.tenant_documents
TO lab_r373_tenant_a, lab_r373_tenant_b;
~~~

Chưa có RLS, hai role đều đã được cấp SELECT trên **toàn bảng**. Ta sẽ ràng buộc theo role hiệu lực.

### 20.2. Bật RLS

~~~sql
ALTER TABLE lab_r373.tenant_documents
ENABLE ROW LEVEL SECURITY;
~~~

Nếu bật RLS nhưng không có policy cho thao tác của một role thông thường, PostgreSQL áp dụng cơ chế **default-deny** đối với hàng theo quy tắc RLS, trừ các trường hợp bypass.

### 20.3. Chính sách SELECT

~~~sql
CREATE POLICY lab_r373_tenant_select
ON lab_r373.tenant_documents
FOR SELECT
TO lab_r373_tenant_a, lab_r373_tenant_b
USING (tenant_role = CURRENT_USER);
~~~

`USING` nói hàng **được hiển thị** khi `tenant_role` bằng tên role hiệu lực. Trên account `lab_r373_tenant_a`:

~~~sql
-- Thuc thi bang ket noi tenant_a hoac SET ROLE khi duoc phep.
SELECT doc_id, tenant_role, title
FROM lab_r373.tenant_documents
ORDER BY doc_id;
~~~

Theo policy, role A chỉ thấy **hai tài liệu của A**, còn role B chỉ thấy **một tài liệu của B**, nếu không có policy/bypass/quyền bổ sung làm thay đổi kết quả.

### 20.4. Chính sách INSERT và UPDATE

~~~sql
CREATE POLICY lab_r373_tenant_insert
ON lab_r373.tenant_documents
FOR INSERT
TO lab_r373_tenant_a, lab_r373_tenant_b
WITH CHECK (tenant_role = CURRENT_USER);

CREATE POLICY lab_r373_tenant_update
ON lab_r373.tenant_documents
FOR UPDATE
TO lab_r373_tenant_a, lab_r373_tenant_b
USING (tenant_role = CURRENT_USER)
WITH CHECK (tenant_role = CURRENT_USER);
~~~

- `USING` của UPDATE xét **hàng cũ được phép nhắm tới**.
- `WITH CHECK` xét **hàng mới sau thao tác** phải tiếp tục phù hợp chính sách.
- Chúng bổ sung cho **GRANT UPDATE** cột `title`; role không có quyền thay `tenant_role` thành tenant khác chỉ vì policy tồn tại.

Không có GRANT DELETE và không có DELETE policy trong bài, nên role tenant **không được phép xóa tài liệu** chỉ bằng các quyền đã cấp.

### 20.5. Chủ sở hữu và BYPASSRLS

Trong PostgreSQL, **superuser và role có `BYPASSRLS`** có thể bỏ qua RLS. **Table owner** thông thường cũng có khả năng bypass RLS theo mặc định; `ALTER TABLE ... FORCE ROW LEVEL SECURITY` làm owner chịu policy trong những trường hợp phù hợp, nhưng không biến superuser thành role bị RLS hạn chế.

Vì vậy **không kiểm thử RLS bằng owner rồi kết luận ứng dụng cũng sẽ nhìn như vậy**. Hãy kiểm thử dưới role thật bị hạn chế.

### 20.6. Điều kiện dựa trên current_user cần thiết kế membership chặt

Chính sách minh họa dựa vào `CURRENT_USER`. Trong hệ thống thực:

- Nếu một account được phép `SET ROLE` sang **cả hai tenant**, nó có thể đổi ngữ cảnh và xem dữ liệu theo role được chọn; đây là **lỗi phân quyền membership**, không phải lớp bảo vệ tenant.
- Nếu một account chỉ thừa hưởng role tenant mà không `SET ROLE`, `CURRENT_USER` có thể vẫn là tên account gốc, không trùng giá trị `tenant_role`; cần thiết kế identity mapping rõ ràng.
- Không viết policy dựa vào một biến session như `current_setting('app.tenant_id')` rồi mặc định an toàn, nếu chính account đó có thể tự `SET app.tenant_id` sang tenant khác không qua kiểm soát.
- Với hệ thống multi-tenant thật, cần danh tính tenant **được gắn bởi một thành phần tin cậy**, kiểm soát role, chuẩn hóa quyền và kiểm thử các đường truy cập qua view/function.

**RLS không thay thế quyền bảng, kiểm tra đầu vào, ràng buộc khóa hay chính sách xác thực.**

## 21. Quyền và lỗi SQL injection

Nguyên tắc cấp quyền tối thiểu **giảm hậu quả** khi chương trình bị khai thác, nhưng **không ngăn SQL injection**.

### 21.1. Sai: nối đầu vào người dùng vào SQL

~~~java
// KHONG DUNG:
String sql = "SELECT order_id FROM lab_r373.orders "
           + "WHERE order_status = '" + userInput + "'";
~~~

Nếu đầu vào được ghép trực tiếp thành câu SQL, người dùng xấu có thể tìm cách sửa cấu trúc biểu thức. Cho dù account DB chỉ có SELECT, việc injection vẫn có thể đọc **nhiều dữ liệu hơn dự định** trong phạm vi quyền hiện có.

### 21.2. Đúng: dùng tham số bind

~~~java
String sql =
    "SELECT order_id FROM lab_r373.orders WHERE order_status = ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, userInput);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getInt("order_id"));
        }
    }
}
~~~

Đây là **đoạn minh họa Java/JDBC**, giả định có `connection` và import hợp lệ, không phải chương trình Java đầy đủ. Prepared statement truyền `userInput` dưới dạng **dữ liệu**, không ghép nó thành cú pháp SQL.

### 21.3. Kết hợp hai lớp bảo vệ

~~~text
Prepared statement
   -> chan du lieu nhap bien thanh SQL tuy y

Least privilege
   -> neu con lo hong, tai khoan van chi co
      tap quyen duoc phep
~~~

Hai lớp **bổ sung cho nhau**, không thay thế nhau. Cần thêm kiểm soát endpoint, authorization ở cấp nghiệp vụ, RLS khi phù hợp, logging và xử lý lỗi không tiết lộ thông tin nhạy cảm.

## 22. Mật khẩu, tài khoản dịch vụ và vòng đời quyền

Nguyên tắc tối thiểu còn áp dụng cho **thời gian sống và mức độ chia sẻ**:

1. **Không dùng chung** một tài khoản database cực mạnh cho ứng dụng web, ETL, dashboard và công cụ triển khai.
2. **Không ghi mật khẩu thật** trong source code, tài liệu, CI logs hoặc file cấu hình không được bảo vệ.
3. Sử dụng secret manager, tài khoản dịch vụ chuyên biệt hoặc phương pháp xác thực được tổ chức phê duyệt.
4. Có quy trình **xoay vòng, thu hồi và vô hiệu hóa credential** khi sự cố hoặc nhân viên rời nhóm.
5. Không cấp quyền lâu dài nếu nhu cầu chỉ tạm thời; dùng quy trình cấp quyền có thời hạn hoặc phê duyệt.
6. Kiểm kê định kỳ các role không còn chủ sở hữu, grant thừa, membership quá rộng và function đặc quyền.

### 22.1. CREATEROLE không dành cho ứng dụng

App chỉ nhận đơn **không cần tạo role mới**, **không cần cấp lại quyền**, **không cần tạo database**. Nếu ứng dụng cần tạo account cho khách hàng trong giao diện web, thường đó là **định danh ở tầng ứng dụng**, không nhất thiết là một PostgreSQL role riêng cho mỗi khách.

### 22.2. Migrations nên chạy bằng identity tách biệt

Một deployment tool có thể cần tạo index, thêm cột hoặc cập nhật view. Hãy tách **migration principal** khỏi **runtime principal**:

~~~text
CI/CD migration account -> DDL co kiem soat
Application runtime     -> DML gioi han
Reporting service       -> SELECT gioi han
Audit service           -> INSERT audit / hoac read audit theo nhiem vu
~~~

Thay đổi schema phải có kiểm tra phụ thuộc, quản lý version và cơ chế rollback phù hợp; không chỉ “GRANT ALL cho app để migration tiện hơn”.

## 23. Kiểm tra quyền bằng system catalogs và hàm PostgreSQL

### 23.1. Liệt kê thuộc tính role

~~~sql
SELECT
    rolname,
    rolcanlogin,
    rolsuper,
    rolcreatedb,
    rolcreaterole,
    rolbypassrls
FROM pg_roles
WHERE rolname LIKE 'lab_r373_%'
ORDER BY rolname;
~~~

Truy vấn giúp thấy role nào có khả năng LOGIN, SUPERUSER, CREATEDB, CREATEROLE hoặc BYPASSRLS. `pg_roles` là catalog **PostgreSQL**, không có tương đương đồng tên trên MySQL/SQL Server/Oracle.

### 23.2. Kiểm tra quyền schema

~~~sql
SELECT
    has_schema_privilege(
        'lab_r373_report_login',
        'lab_r373',
        'USAGE'
    ) AS report_can_use_schema;
~~~

Trả BOOLEAN theo quyền hiệu lực tại thời điểm kiểm tra, có xét những cơ chế cấp quyền phù hợp; không chỉ đọc một dòng GRANT.

### 23.3. Kiểm tra quyền trên cột

~~~sql
SELECT
    has_column_privilege(
        'lab_r373_report_login',
        'lab_r373.customers',
        'customer_code',
        'SELECT'
    ) AS can_read_code,
    has_column_privilege(
        'lab_r373_report_login',
        'lab_r373.customers',
        'email',
        'SELECT'
    ) AS can_read_email;
~~~

Theo những GRANT trong bài và nếu không có đường cấp quyền khác, ta kỳ vọng:

| can_read_code | can_read_email |
| --- | --- |
| true | false |

Đây là kiểm tra **quyền cột**, chưa cho biết dữ liệu hàng có bị RLS lọc hay không.

### 23.4. Kiểm tra quyền trên bảng và function

~~~sql
SELECT
    has_table_privilege(
        'lab_r373_audit_login',
        'lab_r373.audit_events',
        'SELECT'
    ) AS auditor_can_read_events,
    has_function_privilege(
        'lab_r373_report_login',
        'lab_r373.customer_count()',
        'EXECUTE'
    ) AS report_can_call_customer_count;
~~~

Hai giá trị dự kiến **true** nếu script grant đã chạy thành công và role inheritance có hiệu lực như thiết kế.

### 23.5. Xem grant ở information_schema

~~~sql
SELECT
    table_schema,
    table_name,
    grantee,
    privilege_type
FROM information_schema.role_table_grants
WHERE table_schema = 'lab_r373'
ORDER BY table_name, grantee, privilege_type;
~~~

Metadata trong `information_schema` thường bị giới hạn bởi **quyền của người đang truy vấn**. Không kết luận toàn hệ thống không có grant chỉ vì account hạn chế không nhìn thấy hết các hàng metadata.

### 23.6. \du và \dp là lệnh psql, không phải SQL chuẩn

Nếu dùng **psql**, có thể xem:

~~~text
\du
\dp lab_r373.*
~~~

Đây là **meta-command của psql**, không phải câu SQL để gửi nguyên xi qua mọi JDBC driver hoặc SQL Editor. Với công cụ khác, sử dụng catalog views/functions tương ứng.

## 24. Cách điều tra một lỗi permission denied

Giả sử ứng dụng báo:

~~~text
ERROR: permission denied for schema lab_r373
~~~

Hãy kiểm tra lần lượt:

1. **Kết nối đang là ai?** Xem `current_user` và `session_user`.
2. **Có quyền CONNECT database không?** Với account phù hợp và chính sách PUBLIC hiện có.
3. **Có USAGE trên schema không?** Dùng `has_schema_privilege(...)`.
4. **Có quyền trên đối tượng hoặc cột không?** Dùng `has_table_privilege`/`has_column_privilege`.
5. **Có đủ quyền đọc cột trong WHERE/RETURNING không?**
6. **Có dùng sequence hoặc function không?** Kiểm tra `USAGE`/`EXECUTE`.
7. **RLS có lọc hàng không?** Một SELECT trả 0 hàng không nhất thiết là lỗi permission; có thể bị policy lọc.
8. **Có quyền qua membership/PUBLIC khác không?** Nếu có, thu hồi một grant có thể chưa đủ.

**Không phản xạ xử lý bằng `GRANT ALL PRIVILEGES`**. Xác định **một quyền thiếu chính xác**, rồi cập nhật role nhóm phù hợp với ma trận nghiệp vụ.

### 24.1. Lỗi có thể do search_path

Khi ứng dụng truy vấn `SELECT * FROM orders` mà bảng thực nằm trong `lab_r373.orders`, lỗi có thể là **không tìm thấy quan hệ** do `search_path`, chứ không phải thiếu SELECT. Dùng tên schema rõ ràng trong SQL quan trọng để chẩn đoán.

### 24.2. Lỗi trong transaction PostgreSQL

Nếu một câu bị permission denied sau `BEGIN`, transaction có thể chuyển sang trạng thái aborted. Trước khi thử lại:

~~~sql
ROLLBACK;
~~~

Đừng gộp nhiều câu “dự kiến lỗi” vào một transaction rồi xem kết quả các câu sau như bằng chứng quyền đã cấp.

## 25. Những bẫy cấp quyền theo chiều rộng

### 25.1. GRANT ALL trên bảng không phải quyền superuser, nhưng vẫn quá rộng

~~~sql
-- KHONG MAC DINH CAP CHO RUNTIME:
-- GRANT ALL PRIVILEGES ON lab_r373.orders
-- TO lab_r373_app_login;
~~~

`ALL PRIVILEGES` có phạm vi **theo loại đối tượng**, không tự biến role thành SUPERUSER. Nhưng với một bảng, nó vẫn có thể cho nhiều hành động hơn app cần, chẳng hạn `DELETE`, `TRUNCATE` hoặc `REFERENCES`/`TRIGGER` theo ngữ nghĩa PostgreSQL.

### 25.2. GRANT ON ALL TABLES IN SCHEMA không tự giới hạn cột

~~~sql
-- KHONG CAP TRONG VI DU CO EMAIL NHAY CAM:
-- GRANT SELECT ON ALL TABLES IN SCHEMA lab_r373
-- TO lab_r373_order_reader;
~~~

Nó áp dụng quyền bảng trên **mọi đối tượng phù hợp hiện hữu** trong schema, kể cả bảng chứa email. Không dùng khi role chỉ cần một số cột hoặc một số bảng.

### 25.3. Quyền schema CREATE là khả năng mở rộng tấn công

Nếu role runtime có thể tạo function/bảng trong schema được một `SECURITY DEFINER` routine sử dụng qua `search_path`, có thể tạo nguy cơ mạo danh đối tượng. Hạn chế CREATE ở schema tin cậy, dùng schema-qualified names và search_path an toàn.

### 25.4. Quyền owner có thể phá thiết kế tối thiểu

Không dùng account runtime để tạo và sở hữu mọi bảng sản xuất. Owner có khả năng quản lý đối tượng mạnh hơn việc chỉ được `GRANT SELECT/UPDATE`; REVOKE không thu hồi đầy đủ năng lực đặc biệt của owner.

### 25.5. Quyền trên view/function cũng là quyền tiếp cận dữ liệu

Một account không có SELECT bảng khách nhưng được EXECUTE function `SECURITY DEFINER` trả toàn bộ email vẫn có thể lấy email. Đánh giá **kết quả đầu ra và cách thực thi** của view/function, không chỉ quyền bảng trực tiếp.

## 26. Khác biệt giữa các SQL dialect

Khái niệm **user, role, grant/revoke và least privilege** có thể áp dụng rộng rãi, nhưng cú pháp và lớp định danh khác nhau.

### 26.1. PostgreSQL

Các mẫu:

~~~sql
CREATE ROLE report_reader NOLOGIN;
CREATE ROLE app_user LOGIN;
GRANT report_reader TO app_user;

GRANT USAGE ON SCHEMA some_schema TO report_reader;
GRANT SELECT (id, status)
ON some_schema.orders TO report_reader;

REVOKE SELECT (status)
ON some_schema.orders FROM report_reader;
~~~

PostgreSQL dùng hệ thống role thống nhất; có schema `USAGE`/`CREATE`, quyền bảng/cột, function `EXECUTE`, `PUBLIC`, `ALTER DEFAULT PRIVILEGES` và RLS. `REVOKE` không phải explicit DENY.

### 26.2. MySQL

MySQL xác định account thường theo cặp **tên người dùng + host**. Ví dụ minh họa MySQL 8.0:

~~~sql
-- MySQL minh hoa: tai khoan theo user@host.
CREATE ROLE 'app_reader';

-- Account nay khong duoc provision password trong bai.
CREATE USER 'report_user'@'localhost';

GRANT SELECT
ON training_db.orders
TO 'app_reader';

GRANT 'app_reader' TO 'report_user'@'localhost';
~~~

MySQL có cơ chế **active/default roles**, nên đã được GRANT membership chưa chắc tương đương role đã được kích hoạt trong mọi session/configuration. Các quyền ở cấp schema/table/column và các đặc quyền toàn server cần kiểm tra đúng phiên bản.

MySQL **không sử dụng cùng ngữ nghĩa `USAGE ON SCHEMA` PostgreSQL**; `GRANT USAGE` của MySQL thường liên quan tới account/không cấp thêm quyền, không phải quyền namespace cho truy cập schema giống PostgreSQL.

### 26.3. SQL Server

SQL Server có phân tầng:

~~~text
Server login
     |
     v
Database user
     |
     v
Database role
     |
     v
Object permissions
~~~

Ví dụ T-SQL:

~~~sql
-- SQL Server minh hoa, database user da duoc tao dung cach.
CREATE ROLE order_reader;

ALTER ROLE order_reader ADD MEMBER report_user;

GRANT SELECT ON OBJECT::dbo.Orders TO order_reader;

-- SQL Server co DENY, khac PostgreSQL.
DENY DELETE ON OBJECT::dbo.Orders TO order_reader;
~~~

SQL Server hỗ trợ `GRANT`, `REVOKE` và **`DENY`**, cùng quyền ở các **securables** (server, database, schema, object, column). `DENY` có quy tắc ưu tiên/ngoại lệ theo đối tượng và membership; không thể sao chép khái niệm này sang PostgreSQL như một cú pháp tương đương.

SQL Server có row-level security thông qua **security policy** và predicate function, khác cú pháp PostgreSQL `CREATE POLICY ... USING`.

### 26.4. Oracle Database

Oracle có **database users và roles**, đặc quyền hệ thống và đặc quyền đối tượng:

~~~sql
-- Oracle minh hoa, role/object duoc tao boi account co quyen.
CREATE ROLE order_reader;
GRANT SELECT ON app_owner.orders TO order_reader;

-- Account/role nhan membership theo quy trinh quan tri.
-- GRANT order_reader TO report_user;
~~~

Oracle thường gắn một **schema** với một database user và có các quy tắc về **role trong definer-rights PL/SQL**: quyền qua role có thể không được sử dụng trong một số ngữ cảnh stored PL/SQL, cần **direct grants** cho owner/routine theo yêu cầu. Không đoán rằng đã GRANT role cho user thì mọi stored procedure của user sẽ đọc được tất cả bảng được role ấy cấp.

Oracle có cơ chế Virtual Private Database (VPD) và các lựa chọn quản lý chính sách hàng khác với PostgreSQL RLS.

### 26.5. SQLite

SQLite không có một **database server với CREATE ROLE, GRANT và REVOKE native** giống PostgreSQL. Quyền truy cập file database chủ yếu phụ thuộc hệ điều hành, ứng dụng, quy trình kết nối và những cơ chế bảo vệ bổ sung nếu có.

~~~sql
-- CAC LENH SAU KHONG PHAI CU PHAP SQLITE NATIVE:
-- CREATE ROLE app_reader;
-- GRANT SELECT ON orders TO app_reader;
~~~

Nếu ứng dụng SQLite cần nhiều vai trò người dùng, việc xác thực và phân quyền thường được thực hiện ở **tầng ứng dụng**, phối hợp quyền file, cơ chế tách dữ liệu và truy vấn an toàn. Đừng nghĩ một tài khoản app chỉ thấy một nút trong UI là đủ bảo vệ file SQLite nếu người dùng có thể truy cập trực tiếp file database.

### 26.6. Bảng so sánh nhanh

| Vấn đề | PostgreSQL | MySQL | SQL Server | Oracle | SQLite |
| --- | --- | --- | --- | --- | --- |
| Người dùng và role | Role thống nhất, `LOGIN`/`NOLOGIN` | Account `user@host` và roles | Login, database user, roles | Database user và roles | Không có hệ thống server roles native |
| GRANT/REVOKE | Có | Có | Có | Có | Không có cú pháp native tương đương |
| DENY tường minh | Không có DENY đối tượng chung | Không tương đương PostgreSQL/SQL Server | **Có** | Không giống SQL Server | Không |
| Quyền namespace/schema | `USAGE`, `CREATE` | Cấp theo database/schema theo cách MySQL | Schema securable | Quyền hệ thống/đối tượng theo mô hình Oracle | Quyền file/app |
| Role membership | Có, inheritance/SET theo quy tắc phiên bản | Có active/default roles | Database/server role memberships | Có role grants | Không native |
| Row filtering trong DB | RLS policy | Cơ chế khác tùy sản phẩm/cách thiết kế | Row-Level Security policy | VPD / các tính năng bảo mật | Thường tại app |
| Function có thể chạy quyền owner? | `SECURITY DEFINER` | `SQL SECURITY DEFINER` theo cơ chế MySQL | `EXECUTE AS` và các cơ chế khác | Definer/invoker rights | Host application định nghĩa |

**Mục tiêu khi chuyển hệ là giữ nguyên ranh giới an toàn**, chứ không sao chép từ khóa GRANT ở hệ này sang hệ khác mà không kiểm tra ngữ nghĩa.

## 27. Các tình huống thiết kế quyền thực tế

### 27.1. Dashboard chỉ xem số liệu tổng

Không nhất thiết cấp SELECT mọi hàng trong `orders`. Có thể cung cấp **view báo cáo tổng hợp** chỉ chứa số lượng và doanh thu, cấp SELECT trên view và kiểm soát quyền underlying data theo quy tắc DBMS.

### 27.2. Dịch vụ thanh toán

Một dịch vụ chỉ xác nhận thanh toán có thể cần SELECT những cột định danh/trạng thái và UPDATE một số cột có điều kiện. Không cấp DELETE, ALTER TABLE, CREATE ROLE, đọc PII không liên quan hoặc thay tổng tiền nếu nghiệp vụ không yêu cầu.

### 27.3. Worker nhập dữ liệu

Worker ETL có thể cần INSERT vào **bảng staging** và SELECT từ nguồn đã xác định. Nếu cần chuyển dữ liệu sang bảng chính, hãy cho phép qua **role hoặc routine cụ thể**, có transaction và audit; không mặc định dùng account chủ sở hữu toàn database.

### 27.4. Đội phân tích dữ liệu

Nhà phân tích có thể đọc **schema analytics** có dữ liệu được ẩn danh/tổng hợp, không nhất thiết trực tiếp truy cập schema chứa dữ liệu khách thô. Nếu cần truy cập ngoại lệ, dùng quy trình phê duyệt, thời hạn và logging phù hợp.

### 27.5. Nhân viên rời công ty hoặc chuyển bộ phận

Thu hồi membership khỏi nhóm cũ, vô hiệu hóa hoặc xử lý account theo chính sách tổ chức, thu hồi token/credential và rà quyền trực tiếp. Không chỉ xóa người khỏi danh sách UI trong khi account database và secret vẫn hoạt động.

## 28. Những lỗi thường gặp

| Cách hiểu hoặc thao tác | Vấn đề | Hướng sửa |
| --- | --- | --- |
| Đăng nhập được nghĩa là đọc được mọi bảng | Authentication khác authorization | Kiểm tra schema và object privileges |
| Tạo role NOLOGIN rồi muốn đăng nhập trực tiếp | NOLOGIN không có khả năng LOGIN | Tạo account LOGIN và cấp membership phù hợp |
| Cấp SUPERUSER cho app để hết permission denied | Phá vỡ giới hạn an toàn | Xác định quyền chính xác cần cấp |
| Cấp `GRANT ALL ON ALL TABLES` cho báo cáo | Mở quá nhiều bảng, cột nhạy cảm | Grant đúng bảng/cột/view |
| Grant SELECT bảng customers khi chỉ cần tên | Có thể mở email và cột thêm về sau | Column-level SELECT hoặc view hẹp |
| Grant USAGE schema rồi nghĩ đủ đọc bảng | USAGE không phải SELECT | Cấp cả quyền đối tượng đúng |
| Grant SELECT bảng nhưng thiếu USAGE schema | Không tham chiếu được bảng theo đường quyền hiện có | Kiểm tra cả hai lớp |
| Cấp UPDATE toàn orders khi chỉ đổi trạng thái | Có thể sửa tiền hoặc customer_id | GRANT UPDATE (order_status) |
| UPDATE có WHERE dùng cột chưa có SELECT | Có thể bị permission denied | Cấp SELECT đúng cột cần dùng |
| INSERT vào bảng SERIAL bị lỗi sequence | Quyền INSERT không đồng nghĩa quyền sequence | Kiểm tra USAGE sequence cần thiết |
| Thu hồi một GRANT mà quyền vẫn còn | Membership/PUBLIC/đường cấp khác | Audit quyền hiệu lực và mọi grant |
| Nghĩ PostgreSQL REVOKE là DENY tuyệt đối | Không có DENY chung | Xóa mọi nguồn quyền không mong muốn |
| App runtime là owner của bảng | Owner có quyền quản lý đặc biệt | Tách deploy/owner khỏi runtime |
| Quên quyền PUBLIC của function | Function có thể mặc định EXECUTE rộng | REVOKE PUBLIC và GRANT cụ thể |
| Để function SECURITY DEFINER dùng search_path không an toàn | Có thể bị lợi dụng tên đối tượng | Cố định search_path, schema qualify |
| Cấp CREATE ON SCHEMA cho user không đáng tin | Tăng rủi ro mạo danh đối tượng | Hạn chế CREATE |
| Bật RLS rồi test bằng superuser | Có thể bypass policy | Kiểm thử dưới role bị hạn chế |
| RLS dùng tenant ID do user tự SET | User có thể đổi tenant ID | Dùng identity tenant được gắn tin cậy |
| App có membership cả hai tenant role | Có thể SET ROLE sang tenant kia | Tách role/tập quyền chặt |
| Nghĩ chỉ cần app role thấp là chống SQL injection | Injection vẫn đọc/sửa trong quyền còn lại | Prepared statements + least privilege |
| Lưu password role trong repository | Lộ credential | Secret manager/provision an toàn |
| Cấp quyền mặc định trên schema chứa PII | Bảng mới có thể bị lộ tự động | Tách schema báo cáo/role creator |
| Nghĩ ALTER DEFAULT PRIVILEGES sửa mọi bảng cũ | Nó chủ yếu tác động đối tượng tương lai | GRANT/REVOKE hiện hữu riêng |
| Role membership là quyền tức thì trong mọi ngữ cảnh | INHERIT/SET/active role khác nhau | Kiểm tra role hiệu lực theo DBMS |
| Dùng kết quả 0 hàng để kết luận thiếu SELECT | RLS có thể lọc hàng | Phân biệt permission error và policy |
| Quên quyền EXECUTE của function trong view/routine path | Có nhiều lớp đối tượng | Kiểm tra mọi lớp quyền liên quan |
| Thử truy vấn lỗi trong transaction rồi tiếp tục | PostgreSQL transaction aborted | ROLLBACK trước khi kiểm tra tiếp |
| Mang PostgreSQL GRANT USAGE schema sang MySQL | Khác ngữ nghĩa SQL dialect | Viết quyền theo đúng hệ quản trị |
| Nghĩ SQLite có CREATE ROLE/GRANT server-side | SQLite không hỗ trợ cơ chế ấy native | Kiểm soát bằng app và quyền file |

## 29. Bài tập thực hành có đáp án

Các bài dựa trên schema `lab_r373` và role đã tạo. Những bài tạo/xóa quyền phải thực hiện **trong sandbox bởi owner/quản trị viên được ủy quyền**. Các ví dụ truy vấn lỗi được ghi chú rõ để bạn không làm cả transaction dừng giữa chừng.

### Bài 1 — Phân biệt authentication và authorization

**Tình huống:** tài khoản ứng dụng kết nối PostgreSQL thành công nhưng nhận lỗi `permission denied for table customers`.

**Đáp án:** xác thực **đã thành công**, nhưng **chưa đủ quyền trên đối tượng**. Kiểm tra `current_user`, `USAGE` schema, quyền bảng/cột, membership, RLS và chức năng thực sự cần. Không nâng lên SUPERUSER.

### Bài 2 — LOGIN và NOLOGIN

**Yêu cầu:** tạo một role nhóm chỉ đọc, không có khả năng đăng nhập trực tiếp.

**Đáp án:**

~~~sql
-- Chi chay neu ten chua ton tai.
CREATE ROLE lab_r373_ex_readonly NOLOGIN;
~~~

`NOLOGIN` phù hợp cho nhóm quyền. Người dùng thực tế sẽ đăng nhập bằng account được cấu hình authentication và nhận membership của nhóm.

### Bài 3 — Cấp membership

**Yêu cầu:** cấp nhóm `lab_r373_ex_readonly` cho `lab_r373_report_login`.

**Đáp án:**

~~~sql
GRANT lab_r373_ex_readonly
TO lab_r373_report_login;
~~~

Câu này cấp membership, **không tự cấp SELECT cho nhóm**. Phải GRANT SELECT lên các đối tượng thích hợp cho `lab_r373_ex_readonly` nếu muốn nhóm thực sự có quyền đọc.

### Bài 4 — USAGE schema nhưng không SELECT

**Tình huống:** role đã có `USAGE ON SCHEMA lab_r373` nhưng chưa có `SELECT` trên `lab_r373.orders`.

**Đáp án:** role **chưa được đọc bảng** chỉ nhờ schema USAGE. Cần thêm `SELECT` trên bảng/cột tương ứng, hoặc quyền thích hợp qua view/function có kiểm soát.

### Bài 5 — Chỉ cho đọc mã và tên khách

**Yêu cầu:** cấp quyền cho `lab_r373_ex_readonly` xem mã và tên khách, nhưng không email.

**Đáp án:**

~~~sql
GRANT USAGE ON SCHEMA lab_r373
TO lab_r373_ex_readonly;

GRANT SELECT (
    customer_id, customer_code, full_name
)
ON lab_r373.customers
TO lab_r373_ex_readonly;
~~~

Không cấp `SELECT ON lab_r373.customers` toàn bảng. Nếu tài khoản còn quyền email qua role khác hoặc PUBLIC, vẫn cần thu hồi các đường ấy.

### Bài 6 — Đếm đơn PAID bằng các cột được cấp

**Yêu cầu:** với account báo cáo trong bài, đếm đơn PAID từ `orders`.

**Đáp án:**

~~~sql
SELECT COUNT(*) AS paid_orders
FROM lab_r373.orders
WHERE order_status = 'PAID';
~~~

Kết quả **2** trong dữ liệu ban đầu. Account phải có quyền đọc cột `order_status`, schema USAGE và chính sách tương ứng. Không cần SELECT cột email để tính.

### Bài 7 — INSERT có column grant

**Yêu cầu:** thêm đơn khách 3 trạng thái NEW, 45000 vào `orders` bằng role writer; không nêu cột identity hoặc created_at.

**Đáp án:**

~~~sql
BEGIN;
INSERT INTO lab_r373.orders(
    customer_id, order_status, total_amount
) VALUES (3, 'NEW', 45000.00);
ROLLBACK;
~~~

Role writer có INSERT ba cột đó; `order_id` được identity sinh và `created_at` có DEFAULT. Rollback giúp không lưu đơn thử.

### Bài 8 — Chỉ cập nhật trạng thái

**Yêu cầu:** cập nhật đơn 2 từ NEW sang PAID nếu trạng thái vẫn NEW.

**Đáp án:**

~~~sql
BEGIN;
UPDATE lab_r373.orders
SET order_status = 'PAID'
WHERE order_id = 2 AND order_status = 'NEW'
RETURNING order_id, order_status;
ROLLBACK;
~~~

Role cần UPDATE cột `order_status` và SELECT các cột dùng ở WHERE/RETURNING. Không cần UPDATE `total_amount`.

### Bài 9 — Thao tác bị từ chối

**Yêu cầu:** role writer cố đổi `total_amount` của đơn 1; theo ma trận quyền chuyện gì xảy ra?

**Đáp án:** nếu chỉ nhận đúng các grant của bài và không có đường khác, PostgreSQL **từ chối** vì thiếu UPDATE trên `total_amount`. Đây là kết quả mong muốn của least privilege.

### Bài 10 — REVOKE membership

**Yêu cầu:** account `lab_r373_report_login` không còn thuộc nhóm `lab_r373_order_reader`.

**Đáp án minh họa:**

~~~sql
-- Chi chay neu muon thay doi quyen sandbox that.
REVOKE lab_r373_order_reader
FROM lab_r373_report_login;
~~~

Membership bị rút. Nếu account còn quyền trực tiếp/qua nhóm khác/PUBLIC, nó vẫn có thể đọc một số đối tượng. Khi muốn dùng các bài sau, admin có thể cấp lại role theo chính sách.

### Bài 11 — PUBLIC

**Câu hỏi:** nếu chạy `GRANT SELECT ON lab_r373.customers TO PUBLIC`, quyền được mở cho ai?

**Đáp án:** `PUBLIC` đại diện **tất cả roles** của PostgreSQL. Bất kỳ role nào có những quyền liên quan khác, như schema USAGE, đều có thể dùng SELECT đó. Điều này quá rộng với bảng có email, nên **không chạy** trên dữ liệu nhạy cảm.

### Bài 12 — Quyền sequence

**Yêu cầu:** cho nhóm writer lấy số từ `lab_r373.ticket_counter` bằng `nextval`, không cấp mọi quyền sequence.

**Đáp án:**

~~~sql
GRANT USAGE ON SEQUENCE lab_r373.ticket_counter
TO lab_r373_order_writer;
~~~

`nextval` phù hợp với `USAGE` sequence; bảng và sequence có hệ quyền khác nhau.

### Bài 13 — Quyền function

**Yêu cầu:** chỉ cho nhóm báo cáo gọi `lab_r373.customer_count()`; không để PUBLIC có EXECUTE theo grant mặc định.

**Đáp án:**

~~~sql
REVOKE ALL PRIVILEGES
ON FUNCTION lab_r373.customer_count()
FROM PUBLIC;

GRANT EXECUTE
ON FUNCTION lab_r373.customer_count()
TO lab_r373_order_reader;
~~~

Hàm SECURITY DEFINER vẫn cần được rà đầu vào/đầu ra và `search_path` vì có thể thực thi với quyền của owner.

### Bài 14 — ALTER DEFAULT PRIVILEGES

**Câu hỏi:** câu `ALTER DEFAULT PRIVILEGES IN SCHEMA lab_r373_reporting GRANT SELECT ON TABLES TO ...` có tự cấp SELECT trên các bảng đã tạo hôm qua không?

**Đáp án:** **không**. Nó dành cho **đối tượng tương lai do role creator phù hợp tạo**. Các bảng hiện tại cần `GRANT` riêng. Không đặt default SELECT trên schema chứa PII nếu không phải mọi bảng tương lai đều được phép công bố.

### Bài 15 — RLS: A nhìn thấy gì?

**Tình huống:** `lab_r373_tenant_a` có SELECT bảng `tenant_documents`, RLS policy `USING (tenant_role = CURRENT_USER)`.

**Đáp án:** khi role hiệu lực đúng là `lab_r373_tenant_a`, với dữ liệu mẫu, nó nhìn **hai tài liệu của A**, không nhìn tài liệu của B. Nếu thử bằng table owner hoặc superuser, kết quả có thể khác vì RLS bypass; phải kiểm thử bằng account hạn chế.

### Bài 16 — RLS: INSERT tenant B từ tenant A

**Yêu cầu:** tenant A muốn INSERT hàng `tenant_role = 'lab_r373_tenant_b'`. Điều gì xảy ra?

**Đáp án:** policy `WITH CHECK (tenant_role = CURRENT_USER)` của INSERT phải được thỏa. Với `CURRENT_USER = lab_r373_tenant_a`, hàng của B **không hợp lệ theo policy** và bị từ chối, giả sử không có chính sách/bypass khác mở rộng quyền.

### Bài 17 — SECURITY INVOKER và DEFINER

**Yêu cầu:** giải thích vì sao function SECURITY DEFINER có thể đọc dữ liệu nguồn mà người gọi không có SELECT trực tiếp.

**Đáp án:** function có thể chạy theo **quyền owner**, trong khi SECURITY INVOKER dùng quyền người gọi. Vì vậy chỉ nên cấp EXECUTE khi output và hành vi của function được kiểm soát; schema-qualified SQL và search_path an toàn đặc biệt quan trọng.

### Bài 18 — SQL injection và least privilege

**Câu hỏi:** ứng dụng chỉ có SELECT đơn hàng nhưng ghép `userInput` trực tiếp vào WHERE. Có hết nguy cơ SQL injection không?

**Đáp án:** **không**. Least privilege giới hạn phạm vi dữ liệu có thể bị lạm dụng, nhưng lỗi SQL injection vẫn tồn tại. Dùng prepared statements/bind parameters, kiểm tra quyền nghiệp vụ và RLS khi cần.

### Bài 19 — Kiểm tra quyền cột

**Yêu cầu:** dùng PostgreSQL kiểm tra account báo cáo có SELECT cột `email` không.

**Đáp án:**

~~~sql
SELECT has_column_privilege(
    'lab_r373_report_login',
    'lab_r373.customers',
    'email',
    'SELECT'
) AS can_read_email;
~~~

Theo cấu hình tối thiểu của bài, kết quả **false** nếu không có grant khác mở rộng. Hàm giúp kiểm tra quyền cột hiệu lực thay vì chỉ xem một câu GRANT.

### Bài 20 — Vai trò migration và runtime

**Yêu cầu:** một ứng dụng xử lý đơn hằng ngày cần chạy migration thêm cột mỗi khi deploy. Có nên cấp `CREATE ON SCHEMA` và quyền owner thường trực cho app runtime?

**Đáp án:** **không nên**. Dùng **tài khoản triển khai riêng** có DDL đúng phạm vi và quy trình kiểm soát. Runtime chỉ cần INSERT/UPDATE/SELECT tối thiểu; đây là cách tách nhiệm vụ và giảm phạm vi khai thác.

### Bài 21 — Thu hồi quyền từ một đường

**Tình huống:** report_user được SELECT bảng qua role A và role B. Admin REVOKE SELECT từ role A.

**Đáp án:** report_user có thể **vẫn SELECT** do role B. PostgreSQL REVOKE không phải DENY tuyệt đối. Muốn loại bỏ quyền cần kiểm tra cả membership, PUBLIC, direct grants và owner.

### Bài 22 — Chọn hệ thống kiểm soát quyền cho SQLite

**Câu hỏi:** muốn giới hạn mỗi nhân viên chỉ đọc một phần SQLite database, có thể tạo `CREATE ROLE ...; GRANT SELECT ...` native không?

**Đáp án:** **không**. SQLite không cung cấp hệ thống GRANT/ROLE server-side tương đương PostgreSQL. Cần thiết kế xác thực/phân quyền ở tầng ứng dụng, quyền truy cập file và mô hình tách dữ liệu phù hợp; không dựa vào UI để bảo vệ file có thể truy cập trực tiếp.

## 30. Checklist cấp quyền tối thiểu

Trước khi cấp quyền cho người dùng hoặc dịch vụ, hãy kiểm tra:

1. **Ai đang kết nối?** Có một account dịch vụ riêng, không phải SUPERUSER/owner không?
2. **Nhiệm vụ thực sự là gì?** Xem báo cáo, nhập đơn, ghi audit hay triển khai schema?
3. **Đối tượng nào là tối thiểu?** Database, schema, table, view, column, sequence, function?
4. **Hành động nào là tối thiểu?** SELECT, INSERT, UPDATE cột, EXECUTE — có thật sự cần DELETE/CREATE không?
5. **Phạm vi dữ liệu nào?** Có cần RLS, view hạn chế hàng hoặc cột không?
6. **Quyền đang đến từ đâu?** Direct grant, membership, inherited role, PUBLIC, owner, SECURITY DEFINER?
7. **Quyền cấp mới có cho phép ủy quyền không?** Tránh GRANT OPTION/ADMIN OPTION nếu không cần.
8. **Đã kiểm thử bằng role hạn chế chưa?** Không chỉ thử bằng DBA/superuser.
9. **Đã thử cả hành vi bị từ chối chưa?** Chẳng hạn không xem email, không sửa tiền, không xóa đơn.
10. **Tài khoản có password/secret được quản lý đúng không?** Không ghi vào source hoặc log.
11. **Bảng và function tạo sau này sẽ có quyền gì?** Kiểm tra default privileges và role creator.
12. **Quyền có được thu hồi khi đổi công việc không?** Có quy trình audit, review, rotation và offboarding.

## 31. Tổng kết

| Nhu cầu | Cách làm đáng cân nhắc trong PostgreSQL |
| --- | --- |
| Định nghĩa nhóm quyền không đăng nhập | `CREATE ROLE ... NOLOGIN` |
| Tạo account có khả năng đăng nhập | `CREATE ROLE ... LOGIN`, provision authentication an toàn |
| Gán nhóm quyền cho account | `GRANT group_role TO account_role` |
| Cho tham chiếu schema | `GRANT USAGE ON SCHEMA ...` |
| Cho tạo đối tượng trong schema | `GRANT CREATE ON SCHEMA ...`, chỉ khi cần |
| Chỉ đọc một vài cột | `GRANT SELECT (col1, col2) ON table ...` |
| Chỉ chèn một số cột | `GRANT INSERT (col1, col2) ON table ...` |
| Chỉ cập nhật trạng thái | `GRANT UPDATE (status) ON table ...` |
| Lấy số từ sequence | `GRANT USAGE ON SEQUENCE ...` khi phù hợp |
| Cho gọi function | `GRANT EXECUTE ON FUNCTION ...` |
| Thu hồi một grant | `REVOKE ... FROM role` |
| Kiểm soát quyền tương lai | `ALTER DEFAULT PRIVILEGES` theo role creator/schema |
| Giới hạn hàng theo tenant | `ENABLE ROW LEVEL SECURITY` + policy phù hợp |
| Kiểm tra quyền hiệu lực | `has_schema_privilege`, `has_column_privilege`, `has_table_privilege` |
| Không cấp quyền cho tất cả | Tránh `PUBLIC`/`ALL PRIVILEGES` trừ khi được thiết kế có chủ đích |
| Tránh mở rộng quyền qua routine | Rà `SECURITY DEFINER`, `search_path`, EXECUTE grants |
| Giảm nguy cơ từ input không tin cậy | Prepared statements **và** least privilege |
| Tách triển khai và vận hành | Migration role khác runtime role |

**Nguyên tắc cốt lõi:** không hỏi “làm sao cấp đủ quyền để câu SQL hết lỗi?”, mà hỏi **“định danh này cần làm đúng việc gì, trên đối tượng nào, với phạm vi dữ liệu và thời gian bao lâu?”**. Hãy tạo role theo nhiệm vụ, cấp `GRANT` trên đúng đối tượng/cột, kiểm tra các đường quyền gián tiếp, thử bằng account hạn chế và thu hồi quyền không còn cần. Khi được áp dụng nhất quán, **least privilege** giúp giảm rủi ro lộ dữ liệu, sửa dữ liệu ngoài ý muốn và phạm vi tác động nếu ứng dụng hoặc thông tin xác thực bị xâm phạm.
