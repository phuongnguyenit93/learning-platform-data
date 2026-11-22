# Phân chia kiểm tra dữ liệu giữa cơ sở dữ liệu và ứng dụng

Một form đặt hàng có thể từ chối số lượng âm, cảnh báo email sai định dạng hoặc thông báo rằng mã giảm giá đã hết hiệu lực. Tuy nhiên, dữ liệu còn được ghi từ API, ứng dụng di động, worker nền, script nhập liệu và công cụ quản trị. Nếu chỉ kiểm tra ở giao diện, những đường ghi khác có thể tạo bản ghi sai. Ngược lại, nếu mọi kiểm tra chỉ xảy ra khi PostgreSQL từ chối một câu `INSERT`, người dùng sẽ nhận lỗi kỹ thuật khó hiểu, còn các quy tắc phụ thuộc thanh toán, quyền truy cập và luồng nghiệp vụ vẫn không được xử lý đầy đủ.

Bài học thuộc chương **Ràng buộc** của PostgreSQL, tập trung vào cách **phân chia trách nhiệm kiểm tra dữ liệu giữa database và ứng dụng**. Mục tiêu là giữ dữ liệu đúng trong mọi đường ghi, không bỏ sót lỗi đồng thời, đồng thời cung cấp trải nghiệm và quy trình nghiệp vụ dễ kiểm soát.

Nguyên tắc cốt lõi:

> **Ứng dụng kiểm tra sớm để giải thích và điều phối; PostgreSQL giữ những bất biến dữ liệu mà mọi thao tác ghi phải tuân thủ.** Một quy tắc có thể được kiểm tra ở nhiều lớp có chủ đích, nhưng không vì thế mà hai lớp có cùng trách nhiệm.

## 1. Các khái niệm phải phân biệt

**Input validation**: xác định request có đúng cấu trúc và định dạng không. Ví dụ `quantity` phải là số nguyên, ngày đặt có parse được không, chuỗi không được chỉ có khoảng trắng.

**Business validation**: quyết định thao tác có được phép theo quy tắc nghiệp vụ hay không. Ví dụ đơn đang shipped không thể quay lại draft, voucher không áp dụng cho sản phẩm bị loại trừ.

**Data integrity**: giữ những điều kiện phải đúng đối với dữ liệu đã được chấp nhận. Ví dụ khóa chính duy nhất, không có dòng hàng thiếu đơn cha, giá không âm.

**Authorization**: người đang gọi có quyền thao tác trên đối tượng hay không. Một order ID tồn tại không có nghĩa mọi người dùng đều được hủy đơn đó.

**External verification**: xác nhận sự thật bên ngoài database, chẳng hạn đã nhận thanh toán từ nhà cung cấp hay số điện thoại đã hoàn thành OTP.

Bảng minh họa:

| Yêu cầu | PostgreSQL | Ứng dụng |
|---|---|---|
| Cột bắt buộc có dữ liệu | `NOT NULL` | Kiểm tra required, báo lỗi sớm |
| Giá không âm | `CHECK` | Kiểm tra trước khi gửi |
| Mã khách duy nhất | `UNIQUE` | Pre-check tùy UX, bắt lỗi ghi |
| Đơn phải tham chiếu khách tồn tại | `FOREIGN KEY` | Tra cứu/lựa chọn hợp lệ |
| Hai lịch đặt phòng không trùng | `EXCLUDE` khi phù hợp | Hiển thị giờ còn trống |
| Chuyển trạng thái theo workflow | Một phần constraint, có thể cần transaction/trigger | Domain service quyết định |
| Không bán vượt tồn kho | CHECK + cập nhật nguyên tử/khóa | Điều phối đặt hàng |
| Người dùng chỉ sửa đơn của mình | Quyền DB/RLS nếu áp dụng | Authorization theo identity |
| Email có thể nhận thư | Không suy ra chỉ từ regex | Email verification |
| PSP đã xác nhận thanh toán | Lưu kết quả và bảo vệ quan hệ | Xác minh callback/provider |

Một rule cần được mô tả rõ trước khi chọn vị trí triển khai.

## 2. Mô hình nhiều lớp kiểm tra

~~~text
                  Người dùng
                       |
                       v
              +----------------+
              | UI / Client    |
              | Format, gợi ý  |
              +----------------+
                       |
                       v
              +----------------+
              | API boundary   |
              | Parse, authN   |
              | Request schema |
              +----------------+
                       |
                       v
              +----------------+
              | Domain service |
              | Workflow, authZ |
              | External rules |
              +----------------+
                       |
                       v
              +----------------+
              | SQL transaction|
              | Atomic writes  |
              | Concurrency    |
              +----------------+
                       |
                       v
              +----------------+
              | PostgreSQL     |
              | Constraints    |
              | Integrity      |
              +----------------+
                       |
                       v
                 Dữ liệu
~~~

UI bị bỏ qua dễ dàng bằng HTTP request trực tiếp, vì vậy kiểm tra ở client **không phải ranh giới tin cậy**. API phải parse lại dữ liệu và xác thực quyền; service áp dụng nghiệp vụ; database bảo vệ invariants thông qua constraint và giao dịch.

### 2.1. Lặp validation có chủ đích

Một trường `quantity` bắt buộc phải lớn hơn 0:

- UI hiển thị: “Số lượng phải từ 1 trở lên”.
- API từ chối `quantity</BT> là chuỗi hoặc số thập phân nếu hợp đồng yêu cầu integer.
- Service kiểm tra sản phẩm được phép mua.
- PostgreSQL dùng `quantity INTEGER NOT NULL CHECK (quantity > 0)`.

Đây không phải sự lặp lại vô ích: UI tối ưu trải nghiệm, còn database chịu trách nhiệm về tính đúng cuối cùng.

### 2.2. Không cần sao chép mọi quy tắc ở mọi nơi

Một quy tắc thay đổi hằng ngày theo chiến dịch, có thể gọi dịch vụ ngoài, không nên bị sao chép thành nhiều bản JavaScript, Java, PL/pgSQL và trigger không có cơ chế đồng bộ. Hãy đặt quy tắc nghiệp vụ ở nơi sở hữu nó; ở database, giữ phần invariant tối thiểu có thể bảo vệ ổn định.

## 3. Xác định bất biến trước khi viết SQL

Một **bất biến** là điều không được sai trong dữ liệu đã commit.

Ví dụ:

~~~text
Mỗi customer có một primary key duy nhất.
Mỗi order.customer_id tham chiếu customer có thật.
Mỗi order_item.quantity lớn hơn 0.
Mỗi product.stock không âm.
Email đã chuẩn hóa không trùng trong phạm vi một tenant.
Một phòng không có hai booking confirmed chồng thời gian.
~~~

Các câu này cụ thể hơn “dữ liệu phải hợp lệ”.

### 3.1. Phạm vi của bất biến rất quan trọng

“Email duy nhất” chưa đủ rõ. Cần hỏi:

- Duy nhất toàn hệ thống hay theo tenant?
- Có phân biệt chữ hoa không?
- Có được bỏ trống email không?
- Soft delete có giải phóng email để dùng lại không?
- Email cần được xác minh trước khi sử dụng không?

Nếu chưa xác định phạm vi, một constraint `UNIQUE(email)` có thể giữ **sai quy tắc nghiệp vụ**.

### 3.2. Không phải quy tắc nào cũng là bất biến vĩnh viễn

“Khách phải có địa chỉ giao hàng” có thể không đúng với hồ sơ khách chỉ mới đăng ký. Nhưng “đơn hàng ở trạng thái submitted phải có địa chỉ giao hàng” có thể là bất biến hợp lý.

Chọn **thời điểm** rule cần đúng: ngay khi nhập, khi submit, khi thanh toán, khi commit hay khi hoàn tất workflow.

## 4. NOT NULL: cột bắt buộc

~~~sql
CREATE TABLE customers_simple (
    customer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    full_name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

PostgreSQL không cho lưu SQL `NULL` ở `full_name`. Nếu một worker bỏ qua form và gửi `NULL`, database vẫn từ chối.

### 4.1. NOT NULL không ngăn chuỗi rỗng

`''` hoặc `'   '` không phải `NULL`.

~~~sql
CREATE TABLE contacts_simple (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    display_name TEXT NOT NULL,
    CONSTRAINT chk_display_name_not_blank
        CHECK (btrim(display_name) <> '')
);
~~~

Ứng dụng nên trim và giải thích lỗi; database giữ invariant.

### 4.2. NULL có thể là trạng thái hợp lệ

Cột `delivered_at TIMESTAMPTZ` có thể là NULL khi đơn chưa giao. Ép mọi cột `NOT NULL` không làm mô hình tốt hơn nếu NULL có ý nghĩa nghiệp vụ hợp pháp.

## 5. CHECK: điều kiện xác định của một hàng

~~~sql
CREATE TABLE product_prices (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    amount NUMERIC(12, 2) NOT NULL,
    currency_code TEXT NOT NULL,
    CONSTRAINT chk_amount_nonnegative
        CHECK (amount >= 0),
    CONSTRAINT chk_currency_format
        CHECK (currency_code ~ '^[A-Z]{3}$')
);
~~~

Constraint trên bảo vệ số tiền không âm và mã tiền tệ ba chữ cái. Nhưng regex **không xác nhận loại tiền đó thực sự nằm trong danh sách được doanh nghiệp cho phép**.

### 5.1. CHECK và logic ba giá trị

Trong SQL, phép so sánh có thể là `TRUE`, `FALSE` hoặc `UNKNOWN`. CHECK từ chối khi điều kiện là **FALSE**; giá trị **UNKNOWN** thường được chấp nhận.

~~~sql
CREATE TABLE nullable_prices (
    amount NUMERIC CHECK (amount > 0)
);
~~~

`INSERT ... VALUES (NULL)` vào cột này không bị CHECK từ chối, vì `NULL > 0` cho kết quả UNKNOWN. Nếu cần bắt buộc giá dương:

~~~sql
amount NUMERIC NOT NULL CHECK (amount > 0)
~~~

### 5.2. CHECK trên nhiều cột cùng hàng

~~~sql
CREATE TABLE appointment_windows (
    appointment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    starts_at TIMESTAMPTZ NOT NULL,
    ends_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT chk_appointment_interval
        CHECK (ends_at > starts_at)
);
~~~

Rule này phù hợp DB vì đơn giản, ổn định và chỉ dựa trên giá trị cùng một hàng.

### 5.3. CHECK có điều kiện

~~~sql
CREATE TABLE order_headers (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    status TEXT NOT NULL
        CHECK (status IN ('draft', 'submitted', 'cancelled')),
    shipping_address TEXT,
    CONSTRAINT chk_submitted_has_address
        CHECK (
            status <> 'submitted'
            OR NULLIF(btrim(shipping_address), '') IS NOT NULL
        )
);
~~~

Đơn draft có thể thiếu địa chỉ; đơn submitted phải có địa chỉ không rỗng.

### 5.4. Không dùng CHECK để đếm hàng ở bảng khác

Rule “mỗi đơn submitted phải có ít nhất một dòng hàng” liên quan dữ liệu ở bảng khác. Không nên viết hàm CHECK tùy ý thực hiện `SELECT COUNT(*)` để giả lập constraint nhiều hàng: dữ liệu có thể thay đổi đồng thời, việc kiểm tra có thể trở nên sai sau thay đổi khác và khó bảo đảm khi restore.

Hãy dùng transaction, thiết kế đường ghi, khóa hoặc DB mechanism thích hợp với quy tắc đa hàng.

### 5.5. CHECK không phù hợp với điều kiện thay đổi theo đồng hồ

Một rule “ngày đặt phải lớn hơn hoặc bằng hôm nay” phụ thuộc thời điểm hiện tại. Nếu đưa vào CHECK với hàm phụ thuộc thời gian, dữ liệu đang hợp lệ hôm nay có thể không còn hợp lệ ngày mai mà PostgreSQL không tự kiểm tra lại mọi hàng.

Cần xác định việc kiểm tra nên diễn ra **khi người dùng đặt** hay phải giữ đúng vĩnh viễn, rồi đặt logic tại service hoặc một mô hình dữ liệu phù hợp.

## 6. UNIQUE: bảo vệ tính duy nhất trước concurrency

~~~sql
CREATE TABLE customer_emails (
    customer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email TEXT NOT NULL
);

CREATE UNIQUE INDEX uq_customer_email_normalized
ON customer_emails (lower(btrim(email)));
~~~

Một ứng dụng có thể kiểm tra trước:

~~~sql
SELECT EXISTS (
    SELECT 1 FROM customer_emails
    WHERE lower(btrim(email)) = lower(btrim('Alice@example.com'))
);
~~~

Nhưng kiểm tra trước **không đủ để ngăn trùng**.

### 6.1. Race condition điển hình

~~~text
Request A                     Request B
    |                             |
SELECT email có chưa?        SELECT email có chưa?
    |                             |
   Chưa                          Chưa
    |                             |
INSERT email                INSERT cùng email
    |                             |
  Thành công                UNIQUE từ chối
~~~

Không có unique constraint/index, hai request có thể cùng commit dữ liệu trùng. Vì thế database phải là lớp quyết định cuối cùng; ứng dụng bắt `unique_violation` và trả lỗi dễ hiểu.

### 6.2. UNIQUE theo tenant

~~~sql
CREATE TABLE tenant_customers (
    customer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    customer_code TEXT NOT NULL,
    CONSTRAINT uq_tenant_customer_code
        UNIQUE (tenant_id, customer_code)
);
~~~

Nếu hai tenant được dùng cùng mã khách, uniqueness theo toàn bảng chỉ trên `customer_code` sẽ quá chặt.

### 6.3. NULL và UNIQUE

Theo mặc định, UNIQUE trong PostgreSQL có thể cho phép nhiều hàng cùng NULL ở cột nullable. PostgreSQL 15+ hỗ trợ `UNIQUE NULLS NOT DISTINCT` để coi NULL như bằng nhau khi áp dụng tính duy nhất.

~~~sql
-- PostgreSQL 15+:
CREATE TABLE external_mappings (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    external_code TEXT,
    CONSTRAINT uq_external_code
        UNIQUE NULLS NOT DISTINCT (external_code)
);
~~~

Không sử dụng cú pháp phiên bản mới trên server cũ không hỗ trợ.

### 6.4. Partial unique index

Nếu email chỉ duy nhất trong các khách **chưa xóa mềm**:

~~~sql
CREATE TABLE customers_soft_delete (
    customer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email TEXT NOT NULL,
    deleted_at TIMESTAMPTZ
);

CREATE UNIQUE INDEX uq_active_email
ON customers_soft_delete (lower(btrim(email)))
WHERE deleted_at IS NULL;
~~~

Ứng dụng phải thống nhất việc có cho sử dụng lại email sau soft delete hay không. Partial index bảo vệ đúng phạm vi đã thiết kế, không tự quyết định chính sách.

## 7. PRIMARY KEY và FOREIGN KEY

~~~sql
CREATE TABLE sales_customers (
    customer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_code TEXT NOT NULL UNIQUE
);

CREATE TABLE sales_orders (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL
        REFERENCES sales_customers(customer_id),
    status TEXT NOT NULL DEFAULT 'draft'
);
~~~

Foreign key bảo vệ rằng một đơn không tham chiếu khách không tồn tại, kể cả khi:

- Một job nhập nhầm ID.
- API khác bỏ qua kiểm tra trước.
- Khách hàng bị xóa trong một transaction liên quan.
- Có nhiều writer chạy đồng thời.

### 7.1. ON DELETE cần lựa chọn theo nghiệp vụ

~~~sql
CREATE TABLE sales_order_lines (
    order_line_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL
        REFERENCES sales_orders(order_id)
        ON DELETE CASCADE,
    quantity INTEGER NOT NULL CHECK (quantity > 0)
);
~~~

`ON DELETE CASCADE` có thể xóa dòng hàng khi đơn bị xóa. Với dữ liệu thanh toán, kế toán hay audit, hành vi đó có thể không phù hợp chính sách retention. Không chọn cascade chỉ vì nó tiện.

### 7.2. FK không thay authorization

Một `customer_id` có thật vẫn có thể thuộc tenant khác. Foreign key chỉ bảo đảm quan hệ tồn tại, không chứng minh người gửi request có quyền sử dụng đối tượng đó.

Authorization và tenant isolation cần được xử lý ở các lớp khác, có thể bổ sung bằng RLS hoặc thiết kế khóa gồm tenant ID nếu phù hợp.

## 8. EXCLUDE: tránh trùng khoảng đặt phòng

Quy tắc “hai booking đã xác nhận không được chồng lấn cho cùng một phòng” liên quan **nhiều hàng**. Pre-check ở ứng dụng có thể race; CHECK trên một hàng không đủ.

PostgreSQL có exclusion constraint qua GiST và range type.

~~~sql
-- Chạy trong database thử nghiệm khi có quyền tạo extension.
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE booking_rooms (
    room_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    room_name TEXT NOT NULL
);

CREATE TABLE room_bookings (
    booking_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    room_id BIGINT NOT NULL REFERENCES booking_rooms(room_id),
    booking_period TSTZRANGE NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('draft', 'confirmed', 'cancelled')),

    CONSTRAINT chk_period_nonempty
        CHECK (NOT isempty(booking_period)),

    CONSTRAINT ex_confirmed_room_overlap
        EXCLUDE USING gist (
            room_id WITH =,
            booking_period WITH &&
        )
        WHERE (status = 'confirmed')
);
~~~

- `TSTZRANGE`: khoảng các instant.
- `&&`: hai khoảng có giao nhau.
- `room_id WITH =`: so cùng phòng.
- Predicate lọc những booking confirmed.
- `btree_gist` hỗ trợ operator class cho equality ở kiểu cần thiết.

Ví dụ tạo khoảng `[09:00,10:00)`:

~~~sql
INSERT INTO booking_rooms (room_name)
VALUES ('Phòng A');

INSERT INTO room_bookings (
    room_id, booking_period, status
)
VALUES (
    1,
    tstzrange(
        TIMESTAMPTZ '2026-11-14 09:00:00+07',
        TIMESTAMPTZ '2026-11-14 10:00:00+07',
        '[)'
    ),
    'confirmed'
);
~~~

Một booking bắt đầu đúng 10:00 có thể được phép vì khoảng trên không bao gồm mốc cuối 10:00. Nhưng booking confirmed từ 09:30 đến 10:30 cùng phòng sẽ xung đột.

Database đảm bảo **không trùng lịch**. Service vẫn phải xem phòng có bị bảo trì không, khách được đặt không, ngày có nằm trong lịch mở cửa không và khi nào gửi thông báo.

## 9. DEFERRABLE và thời điểm kiểm tra constraint

Một số loại constraint như FK, UNIQUE, PRIMARY KEY, EXCLUDE có thể hỗ trợ `DEFERRABLE`, cho phép trì hoãn kiểm tra tới cuối transaction trong những trường hợp được khai báo phù hợp.

~~~sql
CREATE TABLE departments (
    department_id BIGINT PRIMARY KEY
);

CREATE TABLE employees (
    employee_id BIGINT PRIMARY KEY,
    department_id BIGINT NOT NULL,
    CONSTRAINT fk_employees_departments
        FOREIGN KEY (department_id)
        REFERENCES departments(department_id)
        DEFERRABLE INITIALLY IMMEDIATE
);
~~~

Trong một transaction:

~~~sql
BEGIN;

SET CONSTRAINTS fk_employees_departments DEFERRED;

INSERT INTO employees (employee_id, department_id)
VALUES (1, 10);

INSERT INTO departments (department_id)
VALUES (10);

COMMIT;
~~~

Tại thời điểm commit, FK hợp lệ.

### 9.1. CHECK và NOT NULL không deferrable theo cách tương tự

Không thể tùy ý trì hoãn mọi CHECK/NOT NULL tới cuối transaction. Cần chọn đúng loại constraint và hiểu giới hạn PostgreSQL.

### 9.2. ON CONFLICT và unique deferrable

Một unique constraint deferrable không được dùng làm arbiter cho `INSERT ... ON CONFLICT` theo cách các unique index/constraint immediate được dùng. Khi thiết kế upsert cần xem khả năng tương thích trước.

### 9.3. Lỗi có thể xuất hiện ở COMMIT

Ứng dụng không được coi `INSERT</BT> chạy xong là transaction chắc chắn thành công nếu có deferrable constraint. Tầng quản lý transaction phải xử lý exception khi commit.

## 10. Domain cho quy tắc kiểu dữ liệu dùng lại

~~~sql
CREATE DOMAIN positive_quantity AS INTEGER
CHECK (VALUE > 0);

CREATE TABLE shipment_lines (
    line_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    quantity positive_quantity NOT NULL
);
~~~

Domain có thể giúp dùng lại ràng buộc đơn giản ở nhiều bảng. Nhưng không phải mọi giá trị quantity đều luôn dương: dòng điều chỉnh tồn kho có thể cần số âm. Chọn domain theo ngữ nghĩa của loại dữ liệu, không đặt một quy tắc rộng hơn nghiệp vụ.

## 11. Các kiểm tra nên ưu tiên ở ứng dụng

### 11.1. Cấu trúc và format request

API cần xác nhận:

- JSON đúng schema.
- Không nhận số lượng dưới dạng chuỗi khi API yêu cầu integer.
- Ngày tháng parse được.
- Không có trường thừa nguy hiểm cho mass assignment.
- Giới hạn kích thước request.
- Các trường cần thiết có mặt.

Database có thể trả lỗi parse nhưng ứng dụng có khả năng trả thông báo cụ thể, ổn định hơn.

### 11.2. Email, điện thoại, địa chỉ

Một regex SQL đơn giản không đủ xác nhận địa chỉ email có thể nhận thư, số điện thoại thuộc thuê bao hợp lệ hay địa chỉ nằm trong vùng vận chuyển. Ứng dụng thường cần thư viện, danh sách quy tắc theo quốc gia hoặc dịch vụ chuyên dụng.

Database vẫn giữ những điều có thể xác định ổn định: NOT NULL khi cần, không chỉ khoảng trắng, key/uniqueness và tham chiếu.

### 11.3. Quy tắc phụ thuộc dịch vụ ngoài

Ví dụ:

- Voucher đang hoạt động trên promotion platform.
- Giao dịch đã được cổng thanh toán xác nhận.
- OTP còn hiệu lực.
- Địa chỉ được đơn vị vận chuyển hỗ trợ.
- KYC đã được phê duyệt.

Đây là những sự thật nằm ngoài database. PostgreSQL có thể lưu trạng thái xác nhận và bảo vệ integrity, nhưng không nên đặt HTTP request vào `CHECK`.

### 11.4. Trải nghiệm người dùng

UI có thể đánh dấu lỗi khi người dùng nhập, giữ dữ liệu form, gợi ý định dạng, giải thích rule theo ngôn ngữ gần gũi. Nếu chỉ trả message lỗi DB nguyên văn, UX thường kém và có thể lộ cấu trúc nội bộ.

## 12. Chuyển trạng thái cần nhiều hơn CHECK

Một CHECK:

~~~sql
CHECK (status IN ('draft','submitted','paid','shipped','cancelled'))
~~~

chỉ xác nhận giá trị thuộc tập cho phép. Nó **không** cấm chuyển từ `shipped` về `draft`.

Workflow có thể là:

~~~text
draft -> submitted -> paid -> shipped
                 \
                  -> cancelled
~~~

Service cần kiểm tra trạng thái hiện hành, tiền điều kiện, quyền và sự kiện bên ngoài.

### 12.1. UPDATE có điều kiện để chống race

~~~sql
UPDATE sales_orders
SET status = 'submitted'
WHERE order_id = 1001
  AND status = 'draft'
RETURNING order_id, status;
~~~

Nếu không trả hàng, trạng thái đã thay đổi hoặc order không tồn tại. Service phải xử lý thay vì giả định update thành công.

### 12.2. Nhiều writer độc lập thì sao?

Nếu rất nhiều service/job có quyền cập nhật trực tiếp status, chỉ một service kiểm tra workflow là không đủ. Các lựa chọn:

- Giới hạn quyền ghi và buộc đi qua service thống nhất.
- Dùng câu UPDATE có điều kiện và transaction.
- Dùng stored procedure có kiểm soát quyền.
- Dùng trigger khi thật sự cần một bất biến chuyển trạng thái tại DB.

Trigger có thể hữu ích nhưng tạo logic ẩn và phức tạp bảo trì, nên không tự động là lựa chọn tốt nhất.

## 13. Transaction giúp nhiều thay đổi cùng thành công

Đặt hàng có thể cần:

1. Tạo đơn.
2. Tạo dòng hàng.
3. Trừ tồn kho.
4. Ghi một trạng thái giữ hàng.

Nếu mỗi câu được commit riêng, lỗi giữa chừng có thể để lại đơn không đầy đủ.

~~~sql
BEGIN;

-- INSERT order
-- INSERT order_items
-- UPDATE inventory theo điều kiện còn đủ hàng

COMMIT;
~~~

Nếu bất kỳ bước nào thất bại, service phải `ROLLBACK` theo chính sách transaction.

### 13.1. Transaction không thay business rules

Một transaction có thể commit thành công dữ liệu **sai ngữ nghĩa** nếu các giá trị vẫn thỏa constraint. Transaction cho atomicity và các mức isolation, nhưng không tự biết “người này có được hưởng mã giảm giá không”.

### 13.2. SELECT rồi UPDATE không nguyên tử

Mẫu lỗi:

~~~text
SELECT stock;
Nếu stock >= 1:
    UPDATE stock = stock - 1;
~~~

Hai người có thể đọc cùng stock = 1 và cùng quyết định mua. Phải có cập nhật nguyên tử, locking hoặc isolation thích hợp.

## 14. Cập nhật kho nguyên tử

~~~sql
CREATE TABLE inventory_products (
    product_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    available_quantity INTEGER NOT NULL
        CHECK (available_quantity >= 0)
);
~~~

Khi cần cấp phát hai đơn vị:

~~~sql
UPDATE inventory_products
SET available_quantity = available_quantity - 2
WHERE product_id = 10
  AND available_quantity >= 2
RETURNING product_id, available_quantity;
~~~

Nếu trả **một hàng**, thao tác cấp phát đã thành công trong phạm vi statement/transaction. Nếu trả **0 hàng**, sản phẩm có thể không tồn tại hoặc không còn đủ hàng.

**CHECK available_quantity >= 0** vẫn bảo vệ khi một writer khác gửi UPDATE thiếu điều kiện.

### 14.1. Vì sao điều kiện ngay trong UPDATE quan trọng?

PostgreSQL thực hiện kiểm tra và cập nhật trên hàng theo cơ chế đồng thời của engine, giúp tránh race của bước đọc trước rồi cập nhật mù.

Service vẫn cần:

- Liên kết cấp phát với order đúng.
- Kiểm soát idempotency khi retry.
- Hủy giữ hàng nếu thanh toán không thành công.
- Cập nhật những bảng liên quan trong transaction.
- Xử lý trường hợp không đủ hàng với thông báo dễ hiểu.

### 14.2. SELECT FOR UPDATE

Trong một số quy trình phải đọc nhiều thuộc tính rồi quyết định:

~~~sql
BEGIN;

SELECT product_id, available_quantity
FROM inventory_products
WHERE product_id = 10
FOR UPDATE;

-- Kiểm tra và cập nhật trong transaction.

COMMIT;
~~~

Row locking có thể hữu ích. Nhưng cần tránh giữ khóa trong khi gọi API ngoài có độ trễ lớn và cần thống nhất thứ tự khóa để giảm deadlock.

## 15. Bất biến nhiều hàng/bảng

Ví dụ “tổng đơn bằng tổng tiền các dòng hàng” hoặc “đơn submitted phải có ít nhất một item”.

Đây là rule liên quan nhiều hàng, không nên cố giải quyết chỉ bằng CHECK trên một dòng.

### 15.1. Tránh lưu dư thừa khi không cần

Nếu tổng đơn được tính bằng:

~~~sql
SELECT
    order_id,
    SUM(quantity * unit_price) AS total_amount
FROM order_items
GROUP BY order_id;
~~~

có thể cân nhắc **tính lúc truy vấn** thay vì lưu thêm một `orders.total_amount` dễ lệch dữ liệu, tùy yêu cầu hiệu năng và snapshot nghiệp vụ.

Nếu lưu tổng vì audit/hiệu năng, phải đảm bảo service hoặc DB write protocol cập nhật nhất quán.

### 15.2. “Có item trước khi submit”

Service có thể kiểm tra trong transaction trước khi chuyển trạng thái. Nhưng nếu một writer khác có thể xóa item đồng thời sau khi kiểm tra, rule vẫn có thể bị phá. Cần xét tất cả đường ghi, locking, conditional update, chính sách xóa item và isolation thích hợp.

### 15.3. Trigger không tự sửa mọi race

Một trigger chạy `SELECT COUNT(*)` trên bảng khác vẫn chịu các quy tắc MVCC và concurrency. Nếu cần bảo vệ bất biến đa hàng, phải thiết kế khóa, isolation hoặc bảng điều phối phù hợp.

## 16. External workflow: thanh toán và webhook

Một luồng điển hình:

~~~text
Client yêu cầu thanh toán
           |
           v
Service validate request + authorize
           |
           v
Gọi payment provider
           |
           v
Nhận webhook có xác thực
           |
           v
Xử lý idempotency
           |
           v
Transaction ghi payment/order state
           |
           v
PostgreSQL constraints bảo vệ dữ liệu
~~~

Không có CHECK nào chứng minh được một khoản tiền đã thực sự đến tài khoản ngân hàng. Rule “paid” phụ thuộc sự kiện được xác thực từ provider, cùng cơ chế retry/reconciliation.

Một số công cụ thường cần:

- Idempotency key.
- Chữ ký webhook.
- Outbox/inbox cho sự kiện phân tán.
- Retry có giới hạn.
- Đối soát giữa provider và database.
- Đảm bảo các thay đổi DB trong cùng transaction.

## 17. Validation không thay authorization

Một request có `order_id</BT> hợp lệ và status hợp lệ vẫn có thể trái phép nếu người gửi không sở hữu đơn.

Các lớp bảo vệ bao gồm:

- Authentication ở API.
- Authorization ở domain service.
- PostgreSQL GRANT/REVOKE.
- Row-Level Security khi mô hình tenant yêu cầu.
- Quyền tối thiểu cho database roles.
- Audit đối với thao tác quan trọng.

Foreign key xác nhận đối tượng tham chiếu **tồn tại**; nó không xác nhận người dùng được quyền sử dụng đối tượng đó.

### 17.1. Kết nối qua pool cần quản lý tenant context

Nếu RLS sử dụng cấu hình session để biết tenant hiện hành, ứng dụng cần đặt/reset ngữ cảnh chính xác cho từng request hoặc transaction. Không để session được tái sử dụng mang ngữ cảnh của người dùng trước.

## 18. SQLSTATE: giao diện lỗi kỹ thuật giữa PostgreSQL và ứng dụng

PostgreSQL trả mã lỗi SQLSTATE, thường gồm năm ký tự. Ứng dụng nên dùng mã và tên constraint/index để ánh xạ lỗi, không dựa vào việc tách chuỗi thông báo từ DB.

| SQLSTATE | Tên thường gặp | Nguyên nhân |
|---|---|---|
| `23502` | not_null_violation | NULL trong cột NOT NULL |
| `23503` | foreign_key_violation | Vi phạm FK |
| `23505` | unique_violation | Trùng unique key |
| `23514` | check_violation | CHECK không thỏa |
| `23P01` | exclusion_violation | Vi phạm exclusion |
| `22P02` | invalid_text_representation | Chuỗi không parse được thành kiểu cần |
| `22001` | string_data_right_truncation | Vượt độ dài kiểu dữ liệu |
| `40001` | serialization_failure | Transaction cần retry |
| `40P01` | deadlock_detected | PostgreSQL phát hiện deadlock |

### 18.1. Chuyển lỗi sang ngôn ngữ người dùng

| Lỗi | Ví dụ thông báo API |
|---|---|
| `23502` | “Thiếu trường bắt buộc” |
| `23505` của email | “Email đã được sử dụng” |
| `23503` của customer | “Khách hàng không còn tồn tại” |
| `23514` của quantity | “Số lượng phải lớn hơn 0” |
| `23P01` của booking | “Khung giờ đã có người đặt” |

Không ánh xạ **mọi 23505 thành lỗi email**: còn có SKU, số hóa đơn, mã đơn và idempotency key.

### 18.2. Đừng trả nguyên SQL error message ra client

Lỗi DB có thể chứa tên bảng/cột và giá trị dữ liệu. API nên trả thông báo ổn định theo ngữ cảnh; log nội bộ phải tuân thủ chính sách bảo vệ dữ liệu nhạy cảm.

### 18.3. Lỗi có thể xảy ra ở COMMIT

Với constraint deferrable, câu INSERT có thể tạm thành công nhưng transaction thất bại tại COMMIT. Tầng quản lý transaction phải bắt lỗi ngay cả khi mọi statement riêng đã chạy xong.

## 19. Java: nhận diện lỗi bằng SQLSTATE

~~~java
import java.sql.SQLException;

public final class DbValidationErrors {

    public static String message(SQLException error) {
        String sqlState = error.getSQLState();

        if (sqlState == null) {
            return "Không thể lưu dữ liệu.";
        }

        return switch (sqlState) {
            case "23502" -> "Thiếu trường bắt buộc.";
            case "23503" -> "Dữ liệu tham chiếu không còn hợp lệ.";
            case "23505" -> "Giá trị đã được sử dụng.";
            case "23514" -> "Giá trị vi phạm quy tắc dữ liệu.";
            case "23P01" -> "Dữ liệu xung đột với bản ghi khác.";
            case "40001", "40P01" ->
                "Giao dịch xung đột, cần thực hiện lại.";
            default -> "Không thể lưu dữ liệu.";
        };
    }
}
~~~

Đây là ví dụ minh họa. Trong hệ thống thật, muốn thông báo chính xác cần phân biệt constraint cụ thể và nghiệp vụ của endpoint.

Với pgJDBC, có thể đọc tên constraint từ lỗi server:

~~~java
import java.sql.SQLException;
import org.postgresql.util.PSQLException;
import org.postgresql.util.ServerErrorMessage;

public final class ConstraintInfo {

    public static String getConstraintName(SQLException error) {
        if (error instanceof PSQLException pgError) {
            ServerErrorMessage details = pgError.getServerErrorMessage();
            return details == null ? null : details.getConstraint();
        }
        return null;
    }
}
~~~

Không để người dùng gửi một tên constraint tùy ý để quyết định quyền hay loại thao tác. Tên constraint chỉ là metadata giúp API ánh xạ lỗi.

### 19.1. Retry serialization failure

Nếu PostgreSQL trả `40001`, thường phải **retry toàn transaction** theo giới hạn lần thử và backoff phù hợp. Chỉ lặp lại câu UPDATE cuối có thể dùng dữ liệu đọc từ snapshot cũ.

Khi transaction đi cùng gửi email hoặc gọi provider, cần idempotency/outbox để tránh tác động ngoài DB bị lặp.

## 20. Lab PostgreSQL: một mô hình bán hàng có nhiều lớp bảo vệ

Thực hành trong **database thử nghiệm** với quyền CREATE SCHEMA. Không chạy trên production. Nếu schema `validation_lab` đã tồn tại, chọn database hoặc tên schema khác.

### 20.1. Tạo schema và khách hàng

~~~sql
CREATE SCHEMA validation_lab;

CREATE TABLE validation_lab.customers (
    customer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email TEXT NOT NULL,
    full_name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_customers_email_not_blank
        CHECK (btrim(email) <> ''),

    CONSTRAINT chk_customers_name_not_blank
        CHECK (btrim(full_name) <> '')
);

CREATE UNIQUE INDEX uq_customers_email_normalized
ON validation_lab.customers (lower(btrim(email)));
~~~

PostgreSQL giữ bất biến không NULL, không rỗng và email canonical duy nhất. Nhưng backend vẫn phải kiểm tra format, quyền tạo tài khoản và email verification.

Quy tắc normalize `lower(btrim(email))` chỉ là quy ước của lab, không có nghĩa mọi hệ thống email thực đều có thể so sánh không phân biệt chữ hoa theo cách đó.

### 20.2. Tạo sản phẩm

~~~sql
CREATE TABLE validation_lab.products (
    product_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    product_name TEXT NOT NULL,
    price NUMERIC(12, 2) NOT NULL,
    stock INTEGER NOT NULL DEFAULT 0,
    active BOOLEAN NOT NULL DEFAULT TRUE,

    CONSTRAINT chk_product_name_not_blank
        CHECK (btrim(product_name) <> ''),
    CONSTRAINT chk_product_price_nonnegative
        CHECK (price >= 0),
    CONSTRAINT chk_product_stock_nonnegative
        CHECK (stock >= 0)
);
~~~

### 20.3. Tạo đơn và dòng hàng

~~~sql
CREATE TABLE validation_lab.orders (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    shipping_address TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES validation_lab.customers(customer_id),

    CONSTRAINT chk_orders_status
        CHECK (status IN ('draft', 'submitted', 'cancelled')),

    CONSTRAINT chk_submitted_address
        CHECK (
            status <> 'submitted'
            OR NULLIF(btrim(shipping_address), '') IS NOT NULL
        )
);

CREATE TABLE validation_lab.order_items (
    order_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price NUMERIC(12, 2) NOT NULL,

    CONSTRAINT pk_order_items
        PRIMARY KEY (order_id, product_id),

    CONSTRAINT fk_items_order
        FOREIGN KEY (order_id)
        REFERENCES validation_lab.orders(order_id),

    CONSTRAINT fk_items_product
        FOREIGN KEY (product_id)
        REFERENCES validation_lab.products(product_id),

    CONSTRAINT chk_item_quantity
        CHECK (quantity > 0),

    CONSTRAINT chk_item_unit_price
        CHECK (unit_price >= 0)
);
~~~

### 20.4. Vai trò mỗi constraint

| Rule | Constraint |
|---|---|
| Đơn phải có khách hợp lệ | FK |
| Status thuộc tập cho phép | CHECK |
| Submitted cần địa chỉ | CHECK cùng hàng |
| Một sản phẩm xuất hiện tối đa một dòng trong một đơn | Composite PK |
| Quantity dương | NOT NULL + CHECK |
| Đơn giá không âm | NOT NULL + CHECK |
| Khách được phép đặt hàng | Service/authorization |
| Sản phẩm active và tồn kho đủ | Service + atomic UPDATE |
| Đơn submitted có ít nhất một item | Service/transaction và bảo vệ các đường ghi |
| Tổng tiền có đúng không | Logic tính và cơ chế đồng bộ |

### 20.5. Chèn dữ liệu hợp lệ

~~~sql
INSERT INTO validation_lab.customers (email, full_name)
VALUES ('alice@example.com', 'Alice');

INSERT INTO validation_lab.products (
    sku, product_name, price, stock
)
VALUES ('BOOK-001', 'Sách PostgreSQL', 150000.00, 10);
~~~

Tạo đơn draft và dòng hàng mà không đoán identity ID:

~~~sql
WITH new_order AS (
    INSERT INTO validation_lab.orders (customer_id, status)
    SELECT customer_id, 'draft'
    FROM validation_lab.customers
    WHERE email = 'alice@example.com'
    RETURNING order_id
)
INSERT INTO validation_lab.order_items (
    order_id, product_id, quantity, unit_price
)
SELECT
    o.order_id, p.product_id, 2, p.price
FROM new_order AS o
CROSS JOIN validation_lab.products AS p
WHERE p.sku = 'BOOK-001';
~~~

Ví dụ trên **chưa trừ tồn kho**. Ở ứng dụng thật, tạo đơn, dòng hàng và cấp phát tồn kho cần transaction phù hợp với chính sách đặt hàng.

### 20.6. Thử CHECK

~~~sql
-- Dự kiến bị DB từ chối.
UPDATE validation_lab.products
SET stock = -1
WHERE sku = 'BOOK-001';
~~~

### 20.7. Thử UNIQUE

~~~sql
-- Dự kiến bị unique index từ chối.
INSERT INTO validation_lab.customers (email, full_name)
VALUES ('  ALICE@EXAMPLE.COM  ', 'Alice Duplicate');
~~~

`lower(btrim(email))` của email thứ hai bằng email trước.

### 20.8. Thử FOREIGN KEY

~~~sql
-- Dự kiến bị FK từ chối nếu ID này không tồn tại.
INSERT INTO validation_lab.orders (customer_id)
VALUES (999999);
~~~

### 20.9. Thử CHECK theo trạng thái

~~~sql
-- Đơn draft thiếu địa chỉ không được chuyển thành submitted.
UPDATE validation_lab.orders
SET status = 'submitted'
WHERE customer_id = (
    SELECT customer_id
    FROM validation_lab.customers
    WHERE email = 'alice@example.com'
);
~~~

Cập nhật hợp lệ cần có địa chỉ:

~~~sql
UPDATE validation_lab.orders
SET shipping_address = '123 Example Street',
    status = 'submitted'
WHERE customer_id = (
    SELECT customer_id
    FROM validation_lab.customers
    WHERE email = 'alice@example.com'
)
  AND status = 'draft'
RETURNING order_id, status;
~~~

### 20.10. Thử cập nhật kho nguyên tử

~~~sql
UPDATE validation_lab.products
SET stock = stock - 2
WHERE sku = 'BOOK-001'
  AND active = TRUE
  AND stock >= 2
RETURNING product_id, stock;
~~~

Trả 0 hàng nghĩa là điều kiện cấp phát không thỏa hoặc sản phẩm không tồn tại. Ứng dụng không được coi đây là thành công.

## 21. Migration khi thêm constraint cho dữ liệu hiện hữu

Bảng lớn đã có dữ liệu sai có thể không thêm được CHECK mới nếu PostgreSQL phải xác nhận toàn bộ hàng ngay.

Một cách triển khai theo giai đoạn cho loại constraint phù hợp:

~~~sql
ALTER TABLE validation_lab.products
ADD CONSTRAINT chk_products_price_v2
CHECK (price >= 0) NOT VALID;
~~~

`NOT VALID` cho phép thêm một số loại constraint như CHECK/FK mà chưa quét xác nhận mọi hàng cũ ngay. Tuy nhiên các ghi/cập nhật mới vẫn chịu rule theo quy tắc tương ứng.

Sau khi sửa dữ liệu cũ:

~~~sql
ALTER TABLE validation_lab.products
VALIDATE CONSTRAINT chk_products_price_v2;
~~~

### 21.1. NOT VALID không có nghĩa bỏ kiểm tra cho hàng mới

Không giữ constraint chưa validate như một chế độ “bỏ qua validation”. Cần thống kê dữ liệu cũ, làm sạch, validate và theo dõi.

### 21.2. Không phải mọi constraint có NOT VALID

Không suy ra `UNIQUE NOT VALID` hoạt động giống CHECK. Với unique trên bảng lớn, có thể xem cách tạo unique index concurrently rồi gắn constraint theo quy trình/phiên bản phù hợp.

### 21.3. CREATE INDEX CONCURRENTLY

`CREATE INDEX CONCURRENTLY` có những ràng buộc vận hành, bao gồm không chạy trong transaction block thông thường. Nếu dữ liệu còn trùng, unique index creation có thể thất bại và để lại index chưa hợp lệ cần xử lý.

Không chạy migration production chỉ vì cú pháp đúng; phải xem khóa, thời gian, dung lượng đĩa, quyền và khả năng rollback.

### 21.4. Thêm NOT NULL

Nếu cột đang có NULL, `SET NOT NULL` cần chiến lược sửa dữ liệu trước. Cần xem phiên bản PostgreSQL và cách hạn chế scan/lock, không giả định đổi schema luôn tức thì.

## 22. Phối hợp rollout giữa ứng dụng và DB

Ví dụ rule mới: đơn submitted phải có địa chỉ. Một rollout có thể:

1. Thống nhất chính xác rule và ngoại lệ (giao tại cửa hàng, đơn kỹ thuật).
2. Kiểm kê đơn submitted hiện thiếu địa chỉ.
3. Cập nhật service/API không cho tạo thêm dữ liệu sai.
4. Cập nhật job nền, mobile client và admin tool.
5. Làm sạch dữ liệu cũ theo nghiệp vụ.
6. Thêm constraint theo chiến lược phù hợp.
7. Validate và theo dõi lỗi sau triển khai.
8. Đưa test tương ứng vào pipeline.

Nếu siết DB trước khi các writer cũ thích ứng, có thể tăng lỗi; nếu chỉ đổi ứng dụng rồi không bao giờ bổ sung DB invariant, một đường ghi khác vẫn có thể tạo dữ liệu sai. Cần kế hoạch tương thích theo giai đoạn.

### 22.1. Tên constraint có ý nghĩa

~~~sql
CONSTRAINT chk_submitted_address ...
CONSTRAINT uq_tenant_customer_code ...
CONSTRAINT fk_items_order ...
~~~

Tên rõ ràng giúp debug, mapping SQLSTATE và tra migration. Nhưng không cần hiển thị tên kỹ thuật cho người dùng cuối.

## 23. Kiểm thử các lớp validation

### 23.1. UI tests

- Trường bắt buộc được đánh dấu.
- Số lượng âm bị chặn tại form.
- Người dùng nhận thông báo đúng ngôn ngữ.
- Các trường hợp trạng thái khác nhau được hiển thị nhất quán.

### 23.2. API/service tests

- JSON sai kiểu bị từ chối.
- Không thể cập nhật đơn người khác.
- Transition trái workflow bị từ chối.
- Callback thanh toán không hợp lệ không đổi order thành paid.
- Retry không tạo giao dịch trùng.
- Lỗi từ PostgreSQL được ánh xạ có cấu trúc.

### 23.3. Database integration tests

~~~sql
-- Dự kiến vi phạm CHECK quantity.
INSERT INTO validation_lab.order_items (
    order_id, product_id, quantity, unit_price
)
VALUES (1, 1, 0, 10000);

-- Dự kiến vi phạm FK customer.
INSERT INTO validation_lab.orders (customer_id)
VALUES (999999);

-- Dự kiến vi phạm UNIQUE sku.
INSERT INTO validation_lab.products (
    sku, product_name, price, stock
)
VALUES ('BOOK-001', 'Duplicate', 100000, 1);
~~~

Các test nên assert mã SQLSTATE và constraint tương ứng trong môi trường chuẩn bị dữ liệu đúng; không chỉ assert có exception bất kỳ.

### 23.4. Concurrency tests

Kịch bản quan trọng:

~~~text
Stock ban đầu = 1

Worker A muốn mua 1 đơn vị.
Worker B muốn mua 1 đơn vị.
Cả hai chạy đồng thời.

Kỳ vọng:
- Chỉ một worker cấp phát thành công.
- Worker còn lại được thông báo thiếu hàng.
- Stock cuối không âm.
- Không phát sinh hai đơn xác nhận sử dụng cùng tồn kho.
~~~

Unit test một service chạy tuần tự không chứng minh tính đúng dưới concurrency. Cần integration test trên PostgreSQL thật.

### 23.5. Migration tests

- Dữ liệu cũ vi phạm được phát hiện.
- Làm sạch không phá nghiệp vụ.
- New writes bị ràng buộc trong thời gian chuyển đổi.
- Constraint được validate thành công.
- Kế hoạch rollback/recovery có thể thực hiện khi gặp lỗi.

## 24. Quan sát lỗi validation trong vận hành

Sau deploy, tỷ lệ lỗi constraint tăng có thể chỉ ra:

- Mobile client cũ chưa cập nhật.
- Job import gửi dữ liệu sai.
- Có race ở service.
- Dữ liệu tham chiếu bị thay đổi.
- Rule DB và ứng dụng bị lệch.
- Migration bổ sung constraint khi dữ liệu chưa sạch.

Nên quan sát:

| Nguồn | Chỉ số |
|---|---|
| API | Số lỗi validation theo endpoint |
| Application | SQLSTATE, constraint name, correlation ID |
| PostgreSQL | Lỗi integrity, deadlock, serialization, lock waits |
| Business metrics | Đơn bị từ chối, booking conflict, thất bại cấp phát |

Không log dữ liệu nhạy cảm từ DB error detail một cách tùy tiện. Mã lỗi và tên constraint thường đủ để phân loại lỗi mà không cần lưu toàn bộ email, token hoặc thông tin khách hàng.

## 25. Những hiểu lầm thường gặp

### 25.1. “UI đã kiểm tra rồi, DB không cần constraint”

Sai. API, job và script có thể không qua UI.

### 25.2. “Database kiểm tra rồi, ứng dụng không cần validation”

Sai. Còn UX, parse request, quyền và quy trình nghiệp vụ.

### 25.3. “SELECT kiểm tra email chưa trùng rồi INSERT là an toàn”

Sai dưới concurrency. UNIQUE ở DB cần quyết định cuối cùng.

### 25.4. “CHECK (amount > 0) tự ngăn NULL”

Sai. UNKNOWN được chấp nhận; dùng NOT NULL nếu bắt buộc.

### 25.5. “Foreign key chứng minh user được quyền tham chiếu”

Không. FK kiểm tra quan hệ tồn tại; authZ là vấn đề riêng.

### 25.6. “Trigger đếm hàng sẽ tự tránh race”

Không chắc. Cần thiết kế transaction và locking phù hợp.

### 25.7. “Transaction đảm bảo mọi logic nghiệp vụ đúng”

Không. Transaction có thể commit giá trị sai ngữ nghĩa nếu code và constraints không bảo vệ rule đó.

### 25.8. “Mọi lỗi 23505 là trùng email”

Sai. Cần biết constraint/index cụ thể.

### 25.9. “CHECK status IN (...) quản lý transition”

Không. Nó chỉ bảo vệ tập trạng thái hợp lệ.

### 25.10. “Gọi HTTP trong CHECK là giải pháp xác minh thanh toán”

Không nên. External system không thuộc transaction PostgreSQL và có thể timeout/thay đổi trạng thái.

### 25.11. “NOT VALID cho phép dữ liệu mới tiếp tục sai”

Sai. Đối với CHECK/FK áp dụng theo cơ chế đó, ghi/cập nhật mới vẫn bị kiểm tra.

### 25.12. “NOT VALID dùng cho mọi constraint”

Sai. Unique có chiến lược riêng.

### 25.13. “Retry chỉ statement cuối sau SQLSTATE 40001”

Không đúng. Cần retry toàn transaction và kiểm soát tác động ngoài DB.

### 25.14. “Mọi validation phải được đưa vào trigger”

Không. Logic điều phối, UX và dịch vụ ngoài thường thuộc service. Trigger cần lý do cụ thể và kiểm thử.

### 25.15. “Rule có hai bản UI/DB tự nhiên luôn giống nhau”

Không. Cần quản lý hợp đồng và test để tránh drift.

## 26. Khung quyết định rule đặt ở đâu

Khi gặp một rule mới, tự trả lời:

1. Nó có phải điều luôn đúng trong dữ liệu đã commit không?
2. Nó chỉ dựa vào một hàng hay nhiều hàng/bảng?
3. Có constraint PostgreSQL phù hợp không?
4. Nó cần đúng dưới nhiều transaction đồng thời không?
5. Nó phụ thuộc identity/tenant/quyền không?
6. Nó phụ thuộc hệ thống ngoài hoặc thời gian không?
7. Nó thay đổi thường xuyên theo nghiệp vụ không?
8. Người dùng có cần được báo sớm để sửa không?
9. Khi DB từ chối, API có chuyển thành lỗi dễ hiểu không?
10. Có thể tránh lưu dữ liệu dư thừa không?
11. Các writer cũ và dữ liệu lịch sử có đáp ứng rule không?
12. Có concurrency test và migration test chưa?

### 26.1. Bảng phân chia đề xuất

| Rule | Database | Ứng dụng |
|---|---|---|
| Tên bắt buộc | NOT NULL | Required |
| Tên không rỗng | CHECK | Trim/UX |
| Giá không âm | CHECK | Báo lỗi sớm |
| Email unique trong tenant | UNIQUE phù hợp | Pre-check + bắt 23505 |
| Order tham chiếu customer | FK | Tra cứu và xử lý 23503 |
| Stock không âm | CHECK + atomic UPDATE | Điều phối và thông báo thiếu hàng |
| Booking confirmed không chồng lấn | EXCLUDE khi phù hợp | Chọn slot và giải thích conflict |
| Đơn submitted có địa chỉ | CHECK cùng hàng | Form và transition |
| Provider xác nhận thanh toán | Lưu integrity nội bộ | Webhook, auth, retry |
| Người dùng sửa đúng đơn | RLS/GRANT nếu dùng | Authorization |
| Tổng dòng hàng bằng tổng đơn | Thiết kế dữ liệu/transaction | Tính toán và đồng bộ |
| Promotion eligibility | Bảo vệ dữ liệu tham chiếu | Domain và campaign rules |

## 27. Bài tập vận dụng

### Bài 1 — Số lượng hàng

Phân chia kiểm tra số lượng phải là số nguyên dương giữa UI, API, service và database.

**Gợi ý:** UI thông báo; API parse integer; service kiểm tra mua được; DB dùng `INTEGER NOT NULL CHECK (quantity > 0)`.

### Bài 2 — Email trùng dưới concurrency

Hai request cùng thấy email chưa tồn tại. Vì sao pre-check không đủ?

**Gợi ý:** Race giữa SELECT và INSERT; unique index bảo vệ kết quả cuối.

### Bài 3 — NULL trong CHECK

`amount NUMERIC CHECK (amount > 0)` có chặn NULL không?

**Gợi ý:** Không; dùng NOT NULL nếu yêu cầu.

### Bài 4 — Chuỗi chỉ toàn khoảng trắng

Viết constraint cấm tên `'   '`.

~~~sql
display_name TEXT NOT NULL
CHECK (btrim(display_name) <> '')
~~~

### Bài 5 — Unique đa tenant

Mỗi tenant có mã khách riêng. Hai tenant được dùng cùng mã. Hãy viết constraint.

~~~sql
UNIQUE (tenant_id, customer_code)
~~~

### Bài 6 — Authorization

Order ID có thật nhưng thuộc khách khác. FK và CHECK có đủ không?

**Gợi ý:** Không. Cần authorization và chính sách truy cập.

### Bài 7 — Trừ kho nguyên tử

Stock = 1, hai người cùng mua. Viết UPDATE an toàn:

~~~sql
UPDATE inventory_products
SET available_quantity = available_quantity - 1
WHERE product_id = 10
  AND available_quantity >= 1
RETURNING available_quantity;
~~~

**Gợi ý:** Chỉ worker được cập nhật một hàng là thành công.

### Bài 8 — Booking trùng

Vì sao CHECK(start < end) không ngăn hai booking cùng phòng chồng thời gian?

**Gợi ý:** Check chỉ nhìn một hàng; cần EXCLUDE hoặc transaction protocol khác.

### Bài 9 — Lỗi SQLSTATE

Ghép `23505`, `23503`, `23514`, `23P01` với UNIQUE, FK, CHECK và EXCLUDE.

### Bài 10 — Thanh toán

Vì sao không nên gọi API thanh toán từ CHECK?

**Gợi ý:** Trạng thái ngoài DB và side effects không phù hợp constraint cùng hàng.

### Bài 11 — NOT VALID

Nêu cách thêm CHECK vào bảng có dữ liệu cũ chưa được xác minh.

**Gợi ý:** ADD CHECK NOT VALID, làm sạch, VALIDATE CONSTRAINT.

### Bài 12 — Retry

Một transaction nhận 40001. Có nên chỉ chạy lại câu INSERT cuối?

**Gợi ý:** Thường cần retry toàn transaction có giới hạn, đồng thời bảo vệ external side effects.

### Bài 13 — Status

CHECK status IN ('draft','submitted','cancelled') có cấm cancelled -> submitted không?

**Gợi ý:** Không; cần transition validation.

### Bài 14 — Client cũ

Một mobile app cũ không gửi địa chỉ khi submit. Nếu DB mới yêu cầu địa chỉ, điều gì xảy ra?

**Gợi ý:** DB từ chối; rollout cần xử lý tương thích writers và thông báo lỗi.

### Bài 15 — Dữ liệu dẫn xuất

Khi tổng đơn luôn bằng SUM(quantity*price), hãy nêu hai lựa chọn thiết kế.

**Gợi ý:** Tính khi truy vấn; hoặc lưu snapshot có transaction bảo vệ đồng bộ.

### Bài 16 — Error mapping

PostgreSQL trả 23505 từ index uq_customers_email_normalized. API nên trả gì?

**Gợi ý:** Thông báo người dùng “Email đã được sử dụng”, không lộ SQL nội bộ.

## 28. Ghi nhớ nhanh

| Câu hỏi | Trả lời |
|---|---|
| UI validation có bảo vệ DB khỏi mọi writer? | Không |
| DB nên giữ bất biến cơ bản? | Có, qua constraints |
| Ứng dụng còn cần validation không? | Có, cho UX, workflow, security |
| CHECK có tự cấm NULL? | Không |
| Pre-check UNIQUE có chống race? | Không |
| FK có đảm bảo authorization? | Không |
| Exclusion constraint dùng làm gì? | Bảo vệ quy tắc loại trừ đa hàng |
| Mọi CHECK có deferrable không? | Không |
| Có nên dùng trigger cho mọi business rule? | Không |
| Kho không âm và cấp phát đủ? | CHECK + atomic UPDATE/transaction |
| SQLSTATE UNIQUE? | 23505 |
| SQLSTATE FK? | 23503 |
| SQLSTATE CHECK? | 23514 |
| SQLSTATE EXCLUDE? | 23P01 |
| Serialization failure? | 40001 |
| Retry serialization failure? | Toàn transaction |
| NOT VALID có bỏ kiểm tra ghi mới? | Không |
| Rule thanh toán bên ngoài thuộc đâu? | Service/provider workflow |
| Rule user sửa đúng đơn thuộc đâu? | Authorization/RLS |
| Muốn UX tốt? | Validate trước và map DB errors |
| Muốn dữ liệu đáng tin cậy? | Ràng buộc và transaction cho mọi đường ghi |

---

## Kết luận

**Phân chia kiểm tra dữ liệu giữa PostgreSQL và ứng dụng** là cách phối hợp các thế mạnh khác nhau, không phải chọn một bên rồi loại bỏ bên còn lại. UI và API kiểm tra sớm để người dùng có thể sửa đầu vào; domain service điều phối quy tắc nghiệp vụ, quyền truy cập và dịch vụ ngoài; transaction cùng PostgreSQL constraints bảo vệ dữ liệu ở thời điểm ghi dưới nhiều đường ghi và nhiều request đồng thời.

Các bất biến như **NOT NULL, CHECK, UNIQUE, PRIMARY KEY, FOREIGN KEY, EXCLUDE** nên được giữ tại database khi phù hợp, còn các workflow phức tạp cần được quản lý bằng service và giao thức transaction rõ ràng. Đặc biệt, phương pháp “SELECT kiểm tra rồi INSERT” không thay thế uniqueness hoặc cập nhật nguyên tử khi có concurrency.

Khi triển khai quy tắc mới, hãy xem dữ liệu cũ, client cũ, migration, SQLSTATE, quyền truy cập, retry và khả năng kiểm thử đồng thời. Hệ thống được thiết kế tốt không chỉ **báo lỗi dễ hiểu ở đúng thời điểm**, mà còn **không cho phép dữ liệu vi phạm bất biến được commit**, dù nó đến từ form, API, batch job hay một writer khác.
