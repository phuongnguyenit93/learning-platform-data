# Enum, domain và kiểu tổng hợp trong PostgreSQL

Trong một hệ thống quản lý đơn hàng, cột `status` chỉ nên nhận một số trạng thái như `pending`, `paid` và `cancelled`; `quantity` phải là số nguyên dương; còn địa chỉ giao hàng có thể gồm nhiều thành phần như đường phố, thành phố và mã bưu chính. Nếu dùng `text`, `integer` và các cột rời rạc mà không có quy tắc nhất quán, ứng dụng phải tự lặp lại nhiều bước kiểm tra và có nguy cơ lưu dữ liệu không hợp lệ.

PostgreSQL cho phép định nghĩa những **kiểu dữ liệu riêng** để diễn đạt các quy tắc đó ở cấp cơ sở dữ liệu:

- **Enum (*enumerated type*)**: một tập giá trị có tên, hữu hạn và có thứ tự được quy định.
- **Domain**: một kiểu xây trên kiểu dữ liệu có sẵn, có thể kèm `DEFAULT`, `NOT NULL` và `CHECK` để dùng lại quy tắc giá trị.
- **Kiểu tổng hợp (*composite type*)**: một kiểu gồm nhiều trường có tên, mỗi trường mang một kiểu riêng, tương tự cấu trúc một dòng bản ghi.

Bài học giải thích cú pháp, cách sử dụng, khác biệt với `CHECK` và bảng tra cứu, cách truy vấn, thay đổi kiểu sau khi có dữ liệu, cũng như những giới hạn ảnh hưởng tới thiết kế lược đồ PostgreSQL. Các ví dụ thích hợp với PostgreSQL 16 và các phiên bản hiện đại; khi triển khai thực tế, hãy đối chiếu tính năng với phiên bản server đang chạy.

## 1. Vì sao cần kiểu dữ liệu do người dùng định nghĩa?

Hãy xét ba cột:

~~~sql
status text,
quantity integer,
shipping_address text
~~~

Nếu chỉ khai báo như vậy, database có thể lưu:

~~~text
status           = 'paidd'
quantity         = -10
shipping_address = 'Da Nang / 123 / unknown format'
~~~

Không phải mọi giá trị trên đều sai với mọi nghiệp vụ, nhưng chúng **không diễn đạt rõ ràng** những quy tắc của một đơn hàng thông thường.

Có thể thêm `CHECK` riêng trên từng bảng. Tuy nhiên, nếu 15 bảng đều có một cột số lượng dương hoặc mã trạng thái cùng ý nghĩa, việc lặp lại quy tắc trong từng `CREATE TABLE` gây khó khăn khi cần bảo trì hoặc mở rộng.

Các kiểu định nghĩa riêng cho phép:

~~~text
                     QUY TẮC DỮ LIỆU
                             |
             +---------------+----------------+
             |               |                |
             v               v                v
          ENUM             DOMAIN          COMPOSITE
       Tập trạng thái    Miền giá trị      Nhóm các trường
       có tên và thứ tự  của một scalar    thành một giá trị
             |               |                |
             v               v                v
       order_status     positive_quantity  shipping_address
             |               |                |
             +---------------+----------------+
                             |
                             v
                    Các cột và hàm SQL
~~~

Điểm mạnh chung là **kiểu mang ý nghĩa miền nghiệp vụ**, thay vì chỉ mang ý nghĩa biểu diễn vật lý. Tuy nhiên, ba loại không thay thế hoàn toàn cho primary key, foreign key, unique index hoặc ràng buộc giữa nhiều hàng.

## 2. Bảng so sánh nhanh

| Tiêu chí | Enum | Domain | Composite |
| --- | --- | --- | --- |
| Mục đích | Chọn một giá trị từ danh sách cố định | Tái sử dụng kiểm tra trên một kiểu nền | Gom nhiều trường thành một giá trị có cấu trúc |
| Tạo bằng | `CREATE TYPE ... AS ENUM (...)` | `CREATE DOMAIN ... AS ...` | `CREATE TYPE ... AS (...)` |
| Cấu trúc | Nhãn có tên, có thứ tự | Một kiểu nền và các ràng buộc | Danh sách các thuộc tính và kiểu dữ liệu |
| Ví dụ | `'pending'`, `'paid'` | Số lượng lớn hơn 0 | `(street, city, postal_code)` |
| Có `CHECK` ngay trong định nghĩa? | Không theo cách domain | Có | Không trực tiếp ở mức toàn composite |
| Dùng trong bảng? | Có | Có | Có |
| Dùng làm tham số/trả về của hàm? | Có | Có | Có |
| Thay đổi về sau | Thêm/đổi tên nhãn; bỏ nhãn khó hơn | Thêm/sửa constraint và default | Thêm/đổi thuộc tính theo cú pháp hỗ trợ |
| Phù hợp khi | Tập giá trị nhỏ, tương đối ổn định | Một quy tắc scalar được dùng ở nhiều nơi | Một giá trị có các phần luôn đi cùng nhau |

Một quyết định thiết kế cần xét cả **cách ứng dụng truy vấn** và **khả năng thay đổi trong tương lai**, không chỉ việc cú pháp có ngắn hơn hay không.

## 3. Chuẩn bị database thực hành

Các ví dụ dùng schema riêng `types_lab` để không ảnh hưởng các bảng khác:

~~~sql
CREATE SCHEMA types_lab;
~~~

Bạn cần tài khoản có quyền `CREATE` trong database và quyền tạo đối tượng ở schema phù hợp. Không chạy các ví dụ tạo/xóa kiểu trực tiếp trên database sản xuất.

Nếu đang dùng `psql`, có thể kiểm tra:

~~~sql
SELECT current_database(), current_user, version();
~~~

Nên viết tên đối tượng **có schema**, như `types_lab.order_status`, để tránh tạo nhầm trong schema khác khi `search_path` thay đổi.

Thực hành sẽ đi qua ba bước:

1. Tạo riêng một enum, một số domain và một kiểu composite.
2. Dùng các kiểu này trong bảng đơn hàng.
3. Thử các truy vấn và thay đổi DDL có kiểm soát.

## 4. Enum: biểu diễn tập trạng thái hữu hạn

Một enum trong PostgreSQL là kiểu mà những giá trị hợp lệ phải thuộc về **tập nhãn đã được định nghĩa**.

Tạo kiểu trạng thái đơn hàng:

~~~sql
CREATE TYPE types_lab.order_status AS ENUM (
    'pending',
    'paid',
    'cancelled'
);
~~~

Sau lệnh này, `types_lab.order_status` là **một kiểu dữ liệu**, không phải một bảng.

Thử chuyển chuỗi thành giá trị enum:

~~~sql
SELECT 'pending'::types_lab.order_status AS status;

SELECT CAST('paid' AS types_lab.order_status) AS status;
~~~

Ký hiệu `::` là cú pháp ép kiểu của PostgreSQL; `CAST(... AS ...)` là dạng SQL tương đương.

### 4.1. Enum từ chối nhãn ngoài tập

~~~sql
-- Cố ý gây lỗi để quan sát:
SELECT 'finished'::types_lab.order_status;
~~~

PostgreSQL dự kiến từ chối vì `finished` không phải một nhãn của `types_lab.order_status`.

Giá trị enum **phân biệt chữ hoa/chữ thường** trong nhãn. `'Paid'` không tự được coi là `'paid'`:

~~~sql
-- Cố ý gây lỗi:
SELECT 'Paid'::types_lab.order_status;
~~~

Điều này giúp tránh một số lỗi nhập liệu, nhưng application vẫn cần quyết định cách chuyển đổi, hiển thị và quốc tế hóa trạng thái.

> Khi thử các câu SQL cố ý gây lỗi bên trong `BEGIN`, transaction có thể chuyển sang trạng thái aborted. Dùng `ROLLBACK` trước khi tiếp tục các câu lệnh khác trong cùng phiên.

### 4.2. Thứ tự enum được quyết định lúc khai báo

Điểm đặc biệt của enum PostgreSQL là các giá trị có **thứ tự so sánh** theo vị trí trong `CREATE TYPE`, không theo thứ tự chữ cái:

~~~sql
SELECT status
FROM (
    VALUES
        ('cancelled'::types_lab.order_status),
        ('paid'::types_lab.order_status),
        ('pending'::types_lab.order_status)
) AS v(status)
ORDER BY status;
~~~

Với định nghĩa đã tạo, thứ tự là:

~~~text
pending
paid
cancelled
~~~

Thứ tự này xuất phát từ khai báo:

~~~text
pending < paid < cancelled
~~~

Nó không có nghĩa nghiệp vụ luôn muốn sắp đơn theo chuỗi trên. Nếu giao diện cần hiển thị `paid` trước `pending`, hãy xác định rõ thứ tự mong muốn trong `ORDER BY` hoặc lưu một cột/tập quy tắc xếp hạng riêng.

Enum hỗ trợ so sánh giữa các giá trị **cùng kiểu enum**:

~~~sql
SELECT
    'pending'::types_lab.order_status
        < 'paid'::types_lab.order_status AS is_before;
~~~

Nhưng hai enum khác nhau, dù có nhãn giống nhau, là **hai kiểu riêng**. Không giả định có thể so sánh hoặc gán trực tiếp giữa chúng mà không cần xử lý chuyển đổi.

### 4.3. Khi dùng enum trong bảng

~~~sql
CREATE TABLE types_lab.enum_demo (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    status types_lab.order_status NOT NULL DEFAULT 'pending'
);

INSERT INTO types_lab.enum_demo (status)
VALUES ('pending'), ('paid');

INSERT INTO types_lab.enum_demo DEFAULT VALUES;

SELECT id, status
FROM types_lab.enum_demo
ORDER BY id;
~~~

Vì cột có kiểu `types_lab.order_status`, PostgreSQL biết cách ép các literal chuỗi không xác định kiểu trong `VALUES` sang enum phù hợp. Nhưng một **biểu thức đã có kiểu `text`** không phải lúc nào cũng tự động chuyển thành enum.

Ví dụ ép kiểu rõ ràng:

~~~sql
SELECT 'paid'::text::types_lab.order_status AS status;
~~~

Đối với driver JDBC, kiểu tham số và cách bind ảnh hưởng tới việc PostgreSQL có chấp nhận giá trị truyền vào hay không. Không nên giả định một cột enum và một cột `text` có thể trao đổi không cần cast trong mọi ngữ cảnh.

## 5. Thay đổi một enum sau khi đã sử dụng

Trong thực tế, trạng thái nghiệp vụ có thể phát triển. PostgreSQL hỗ trợ thêm nhãn:

~~~sql
ALTER TYPE types_lab.order_status
ADD VALUE IF NOT EXISTS 'refunded' AFTER 'paid';
~~~

Thứ tự so sánh sau thay đổi:

~~~text
pending < paid < refunded < cancelled
~~~

`IF NOT EXISTS` giúp tránh lỗi khi nhãn đã có. `BEFORE` và `AFTER` cho phép chỉ vị trí tương đối của giá trị mới.

### 5.1. Lưu ý transaction khi thêm giá trị enum

Ở các phiên bản PostgreSQL hiện đại, lệnh thêm giá trị enum có thể được thực thi bên trong transaction block, nhưng **giá trị mới không thể được dùng trong cùng transaction cho tới khi transaction ấy commit**.

Ví dụ cần tách:

~~~sql
BEGIN;

ALTER TYPE types_lab.order_status
ADD VALUE IF NOT EXISTS 'reviewing' BEFORE 'paid';

COMMIT;

-- Dùng giá trị mới sau khi transaction đã commit.
INSERT INTO types_lab.enum_demo (status)
VALUES ('reviewing');
~~~

Khi viết migration, đừng gộp việc `ADD VALUE` và cập nhật dữ liệu dùng giá trị mới vào cùng một transaction mà chưa kiểm tra giới hạn phiên bản và quy tắc enum của PostgreSQL.

### 5.2. Đổi tên nhãn

~~~sql
ALTER TYPE types_lab.order_status
RENAME VALUE 'cancelled' TO 'voided';
~~~

Đổi tên nhãn làm **giá trị hiển thị/tham chiếu theo tên cũ thay đổi** đối với các hàng đang dùng enum này. Những truy vấn hoặc mã ứng dụng vẫn gửi chuỗi `cancelled` có thể lỗi sau khi thay đổi. Đây là thay đổi hợp đồng dữ liệu (*data contract*), không chỉ là chỉnh tên trong một bảng tra cứu.

Nếu tiếp tục bài thực hành và muốn giữ tên `cancelled` cho các ví dụ sau, **không chạy câu `RENAME VALUE` phía trên**, hoặc dùng một môi trường thử riêng rồi chủ động điều chỉnh dữ liệu và ứng dụng.

### 5.3. Bỏ nhãn enum có đơn giản không?

PostgreSQL **không cung cấp một thao tác `ALTER TYPE ... DROP VALUE` thông thường** để xóa an toàn một nhãn đã định nghĩa. Nếu muốn loại một trạng thái cũ, quy trình thường là:

1. Kiểm kê mọi cột, view, hàm và câu SQL sử dụng enum.
2. Chuyển dữ liệu khỏi giá trị cần bỏ.
3. Tạo một **enum mới** với tập nhãn mong muốn.
4. Chuyển cột sang enum mới bằng phép chuyển đổi được kiểm soát.
5. Cập nhật default, index, constraint, hàm và các dependency liên quan.
6. Chỉ xóa enum cũ khi không còn đối tượng sử dụng.

Ví dụ minh họa nguyên tắc chuyển kiểu:

~~~sql
-- Một enum mới với tập nhãn khác:
CREATE TYPE types_lab.order_status_v2 AS ENUM (
    'pending',
    'paid',
    'cancelled',
    'refunded'
);

-- Minh họa một bước migration trên bảng enum_demo.
-- CHỈ thực hiện khi mọi giá trị hiện tại đều có nhãn tương ứng
-- ở order_status_v2 và đã kiểm tra dependency khác.

ALTER TABLE types_lab.enum_demo
ALTER COLUMN status DROP DEFAULT;

ALTER TABLE types_lab.enum_demo
ALTER COLUMN status TYPE types_lab.order_status_v2
USING status::text::types_lab.order_status_v2;

ALTER TABLE types_lab.enum_demo
ALTER COLUMN status SET DEFAULT 'pending'::types_lab.order_status_v2;
~~~

Nếu bạn đã đổi nhãn `cancelled` thành `voided` ở mục trước, phép cast sang `order_status_v2` trong ví dụ này **sẽ không hợp lệ với những hàng mang `voided`**, trừ khi lập kế hoạch ánh xạ giá trị. Điều đó minh họa tại sao migration enum cần xem **dữ liệu đang có**, không chỉ kiểu đích.

Đây là ví dụ giải thích thiết kế, **không phải lệnh dọn dẹp bắt buộc** cho các bước thực hành tiếp theo. Tốt nhất giữ nguyên `order_status` khi tạo bảng tổng hợp ở các phần sau.

## 6. Domain: tạo một kiểu có ràng buộc tái sử dụng

Nếu enum mô tả **danh sách nhãn**, domain mô tả **giới hạn hợp lệ của một giá trị thuộc kiểu nền**.

Ví dụ mọi số lượng sản phẩm phải là số nguyên lớn hơn 0:

~~~sql
CREATE DOMAIN types_lab.positive_quantity
AS integer
NOT NULL
CHECK (VALUE > 0);
~~~

Trong định nghĩa domain:

- `integer` là **kiểu nền (*base type*)**.
- `NOT NULL` thể hiện giá trị không được null trong ngữ cảnh áp dụng ràng buộc.
- `VALUE` là ký hiệu đặc biệt đại diện **giá trị đang được kiểm tra**.
- `CHECK (VALUE > 0)` là điều kiện domain áp dụng khi giá trị được chuyển/nhận vào domain.

Thử:

~~~sql
SELECT 5::types_lab.positive_quantity AS valid_quantity;
~~~

Những trường hợp không hợp lệ:

~~~sql
-- Cố ý gây lỗi: không lớn hơn 0.
SELECT 0::types_lab.positive_quantity;

-- Cố ý gây lỗi: là số âm.
SELECT (-3)::types_lab.positive_quantity;

-- Cố ý gây lỗi: domain khai báo NOT NULL.
SELECT NULL::types_lab.positive_quantity;
~~~

### 6.1. Vì sao domain khác một CHECK trên từng bảng?

Nếu chỉ định nghĩa:

~~~sql
CREATE TABLE example_a (
    quantity integer NOT NULL CHECK (quantity > 0)
);

CREATE TABLE example_b (
    quantity integer NOT NULL CHECK (quantity > 0)
);
~~~

thì cùng quy tắc được lặp ở hai nơi.

Với domain:

~~~sql
CREATE TABLE example_domain_a (
    quantity types_lab.positive_quantity
);

CREATE TABLE example_domain_b (
    quantity types_lab.positive_quantity
);
~~~

cả hai cột đều dùng chung kiểu mô tả số lượng dương. Domain còn có thể được dùng làm kiểu tham số hoặc kiểu trả về của hàm khi cần.

Tuy nhiên, **domain không xóa bỏ nhu cầu đặt constraint ở cấp bảng** khi quy tắc đặc thù của bảng mạnh hơn hoặc liên quan tới nhiều cột.

### 6.2. Domain cho số tiền

~~~sql
CREATE DOMAIN types_lab.nonnegative_money
AS numeric(14, 2)
NOT NULL
CONSTRAINT ck_nonnegative_money
CHECK (VALUE >= 0);
~~~

Ví dụ:

~~~sql
SELECT 125000.50::types_lab.nonnegative_money
       AS accepted_amount;

-- Cố ý gây lỗi:
SELECT (-0.01)::types_lab.nonnegative_money;
~~~

`numeric(14,2)` biểu diễn số thập phân với precision 14 và scale 2, phù hợp những giá trị tiền cần tránh lỗi làm tròn kiểu floating point trong nhiều tình huống. Dẫu vậy, chọn scale 2 **không tự giải quyết** mọi vấn đề tiền tệ như đơn vị tiền, số chữ số thập phân đặc thù, quy tắc thuế hay làm tròn.

Nếu số tiền **không thể là 0**, hãy tạo domain dương với `VALUE > 0` thay vì domain không âm. Tên miền dữ liệu phải phản ánh đúng business rule.

### 6.3. Domain cho mã đơn hàng

~~~sql
CREATE DOMAIN types_lab.order_code
AS text
CONSTRAINT ck_order_code_format
CHECK (VALUE ~ '^[A-Z0-9-]{3,20}$');
~~~

`~` là toán tử so khớp regular expression của PostgreSQL; mẫu trên minh họa mã dài 3–20 ký tự, chỉ gồm chữ hoa Latin, chữ số và dấu gạch nối.

~~~sql
SELECT 'ORD-2026-001'::types_lab.order_code;

-- Cố ý gây lỗi vì chứa chữ thường:
SELECT 'ord-001'::types_lab.order_code;
~~~

Đây là **quy tắc minh họa**, không phải chuẩn duy nhất cho mã đơn hàng. Việc mã đơn có duy nhất hay không vẫn cần `UNIQUE` hoặc một thiết kế định danh tương đương. **Domain `CHECK` chỉ kiểm tra từng giá trị, không bảo đảm không có hai hàng mang cùng mã.**

## 7. Domain, NULL và biểu thức CHECK

PostgreSQL xử lý `CHECK` theo logic ba giá trị SQL: một biểu thức `CHECK` được coi là đạt khi trả về **true hoặc null/unknown**; nó chỉ từ chối khi trả về **false**.

Ví dụ nếu domain chỉ khai báo:

~~~sql
CREATE DOMAIN types_lab.quantity_check_only
AS integer
CHECK (VALUE > 0);
~~~

thì:

~~~sql
SELECT NULL::types_lab.quantity_check_only;
~~~

có thể được chấp nhận, bởi `NULL > 0` cho kết quả unknown chứ không phải false.

Muốn chặn null ở ràng buộc domain, thêm `NOT NULL` hoặc viết biểu thức `CHECK` chủ động từ chối null, tùy yêu cầu.

### 7.1. Có NOT NULL trên domain rồi, có cần NOT NULL trên cột?

Một domain có `NOT NULL` mang ý nghĩa kiểu không nhận null theo các thao tác ép kiểu và lưu trữ bình thường. Nhưng PostgreSQL lưu ý những **tình huống biểu thức SQL có thể sinh NULL mà không luôn đi qua bước kiểm tra của domain**, chẳng hạn kết quả phía không khớp của outer join hoặc một scalar subquery không có hàng.

Vì vậy, khi một **cột bảng bắt buộc không null**, nên thể hiện quy tắc ở **cấp cột**:

~~~sql
CREATE TABLE types_lab.quantity_example (
    quantity types_lab.positive_quantity NOT NULL
);
~~~

Việc lặp `NOT NULL` ở cấp cột không làm mất giá trị của domain: domain vẫn tái sử dụng kiểm tra dương, còn ràng buộc cấp cột thể hiện rõ nghĩa vụ toàn vẹn của bản ghi.

### 7.2. Giới hạn của CHECK trong domain

Domain thích hợp cho điều kiện chỉ phụ thuộc **giá trị cần kiểm tra**, chẳng hạn:

~~~text
quantity > 0
amount >= 0
code khớp một biểu thức chính quy
ngày nằm trong một khoảng hợp lệ cố định
~~~

Không dùng domain như cách thay thế foreign key:

~~~text
customer_id phải tồn tại trong bảng customers
order.total_amount = SUM(order_items...)
start_date <= end_date của cùng một hàng
hai hàng khác nhau không được dùng cùng mã
~~~

Những quy tắc đó cần **FOREIGN KEY, CHECK ở cấp bảng, UNIQUE/EXCLUDE**, trigger, transaction hoặc mô hình dữ liệu phù hợp, chứ không được giải quyết chỉ bằng một domain kiểm tra scalar.

Một domain `CHECK` nên dùng biểu thức có **ngữ nghĩa ổn định/immutable** với cùng giá trị đầu vào. Nếu dựa vào function thay đổi hành vi theo thời gian hoặc cấu hình bên ngoài, những giá trị đã lưu có thể không còn đáp ứng quy tắc mới mà PostgreSQL không tự quét lại mọi lúc. Việc thay đổi function được dùng bởi CHECK cần được quản lý như một migration dữ liệu.

## 8. Thay đổi domain khi quy tắc nghiệp vụ phát triển

Một domain là đối tượng độc lập, vì vậy có thể cập nhật ràng buộc mà không sửa lại DDL của từng cột đang tham chiếu nó.

Ví dụ bổ sung giới hạn số tiền:

~~~sql
ALTER DOMAIN types_lab.nonnegative_money
ADD CONSTRAINT ck_money_upper_limit
CHECK (VALUE <= 999999999999.99)
NOT VALID;
~~~

Ý nghĩa:

- `ADD CONSTRAINT` thêm quy tắc mới.
- `NOT VALID` cho phép trì hoãn việc xác minh mọi dữ liệu cũ đang chứa kiểu domain trong các đối tượng liên quan.
- Những giá trị mới hoặc thay đổi theo cách ràng buộc được áp dụng vẫn phải tuân thủ kiểm tra mới.
- Sau khi rà soát dữ liệu lịch sử, có thể yêu cầu PostgreSQL validate.

~~~sql
ALTER DOMAIN types_lab.nonnegative_money
VALIDATE CONSTRAINT ck_money_upper_limit;
~~~

Nếu dữ liệu cũ vi phạm quy tắc, bước xác minh có thể thất bại; cần sửa dữ liệu hoặc thiết kế trước khi coi ràng buộc mới là hợp lệ.

Để bỏ một constraint domain không còn phù hợp:

~~~sql
ALTER DOMAIN types_lab.nonnegative_money
DROP CONSTRAINT ck_money_upper_limit;
~~~

**Không tự thêm/bỏ constraint domain dùng chung trên production mà không kiểm kê các bảng đang sử dụng.** Một thay đổi ở một domain có thể ảnh hưởng nhiều cột, hàm và ứng dụng đồng thời.

### 8.1. Domain DEFAULT có thể giúp gì?

Domain có thể có default:

~~~sql
CREATE DOMAIN types_lab.default_priority
AS integer
DEFAULT 1
CHECK (VALUE BETWEEN 1 AND 5);
~~~

Khi một cột dùng domain nhưng không có default cụ thể riêng, PostgreSQL có thể sử dụng default của domain trong những ngữ cảnh phù hợp. **Default cấp cột có thể ghi đè default của domain**, vì vậy không nên dùng domain default để thay thế hoàn toàn chính sách mặc định tại bảng.

Đặt default không tương đương với `NOT NULL`: giá trị mặc định chỉ có hiệu lực trong những tình huống sử dụng default, không tự biến mọi giá trị null tường minh thành 1.

### 8.2. Domain có thể dựa trên kiểu khác ngoài integer

Domain có thể được xây trên `text`, `numeric`, `date` và nhiều kiểu nền tương thích. Trong PostgreSQL, có thể tạo domain trên một kiểu enum hoặc kiểu composite khi cần kết hợp những quy tắc thích hợp.

Ví dụ một miền trạng thái cho một quy trình hẹp hơn:

~~~sql
CREATE DOMAIN types_lab.open_order_status
AS types_lab.order_status
CHECK (VALUE IN ('pending', 'paid'));
~~~

Nhưng nếu phải liên tục tạo nhiều domain chỉ để chọn từng tập con enum cho các trạng thái luôn thay đổi, hãy cân nhắc một mô hình bảng tra cứu/trạng thái có quan hệ rõ ràng hơn.

## 9. Composite type: một giá trị gồm nhiều thuộc tính

Một composite type mô tả **cấu trúc nhiều trường**:

~~~sql
CREATE TYPE types_lab.shipping_address AS (
    line1 text,
    city text,
    postal_code text
);
~~~

Kiểu `shipping_address` gồm ba trường:

~~~text
shipping_address
├── line1        text
├── city         text
└── postal_code  text
~~~

Đây là **một kiểu dữ liệu**, không phải bảng. Nó không tự lưu hàng dữ liệu và không có primary key hay index riêng.

### 9.1. Tạo giá trị composite bằng ROW

~~~sql
SELECT ROW(
    '12 Nguyen Hue',
    'Ho Chi Minh City',
    '700000'
)::types_lab.shipping_address AS destination;
~~~

`ROW(...)` là *row constructor*. Kết quả được ép thành kiểu `types_lab.shipping_address`, trong đó vị trí giá trị phải phù hợp với thứ tự các thuộc tính của type.

Có thể dùng cú pháp biểu diễn composite bằng chuỗi, nhưng với dữ liệu có dấu phẩy, dấu nháy và null, format literal phức tạp và dễ sai. Trong truy vấn có thể kiểm soát, dùng `ROW(...)::type` thường dễ đọc hơn.

### 9.2. Truy cập trường của composite

Đặt một giá trị trong CTE:

~~~sql
WITH sample AS (
    SELECT ROW(
        '12 Nguyen Hue',
        'Ho Chi Minh City',
        '700000'
    )::types_lab.shipping_address AS address
)
SELECT
    (address).line1 AS line1,
    (address).city AS city,
    (address).postal_code AS postal_code
FROM sample;
~~~

Chú ý dấu ngoặc trong `(address).city`. PostgreSQL thường yêu cầu dấu ngoặc khi tham chiếu một field của **biểu thức composite**, để không nhầm với cú pháp `table.column`.

Có thể trải các trường của composite ra thành nhiều cột:

~~~sql
WITH sample AS (
    SELECT ROW('A', 'Da Nang', '550000')
           ::types_lab.shipping_address AS address
)
SELECT (address).*
FROM sample;
~~~

Trong truy vấn thực tế, nếu biểu thức phía trong dấu ngoặc là một **hàm tốn kém**, cách mở rộng `(function_call(...)).*` có thể khiến function được đánh giá nhiều lần theo plan. Nên dùng subquery, `LATERAL` hoặc cấu trúc rõ ràng để tránh tính lặp khi cần.

## 10. Dùng composite type trong bảng

Ví dụ bảng lưu một giá trị địa chỉ có cấu trúc:

~~~sql
CREATE TABLE types_lab.address_demo (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    recipient text NOT NULL,
    destination types_lab.shipping_address NOT NULL,
    CONSTRAINT ck_address_city_present
        CHECK (
            (destination).city IS NOT NULL
            AND length(btrim((destination).city)) > 0
        )
);
~~~

Thêm dữ liệu:

~~~sql
INSERT INTO types_lab.address_demo
    (recipient, destination)
VALUES
    (
        'Lan',
        ROW('12 Nguyen Hue', 'Ho Chi Minh City', '700000')
            ::types_lab.shipping_address
    ),
    (
        'Minh',
        ROW('8 Bach Dang', 'Da Nang', '550000')
            ::types_lab.shipping_address
    );
~~~

Đọc từng trường:

~~~sql
SELECT
    id,
    recipient,
    (destination).line1 AS line1,
    (destination).city AS city
FROM types_lab.address_demo
ORDER BY id;
~~~

Lọc theo thuộc tính của composite:

~~~sql
SELECT id, recipient
FROM types_lab.address_demo
WHERE (destination).city = 'Da Nang';
~~~

### 10.1. Cập nhật một field của composite

~~~sql
UPDATE types_lab.address_demo
SET destination.city = 'Hue'
WHERE recipient = 'Minh';
~~~

Trong vị trí `SET`, PostgreSQL hỗ trợ cú pháp gán một field của cột composite như `destination.city`. Còn trong biểu thức đọc ở `SELECT` hoặc `WHERE`, viết `(destination).city` giúp phân biệt rõ.

Bạn cũng có thể thay **toàn bộ giá trị composite**:

~~~sql
UPDATE types_lab.address_demo
SET destination = ROW(
    '22 Le Loi',
    'Da Nang',
    '550000'
)::types_lab.shipping_address
WHERE recipient = 'Minh';
~~~

Mỗi lệnh `UPDATE` ở trên thực sự sửa dữ liệu thử nghiệm. Nếu chỉ muốn quan sát rồi hoàn nguyên, hãy thực hiện trong transaction:

~~~sql
BEGIN;

UPDATE types_lab.address_demo
SET destination.city = 'Can Tho'
WHERE recipient = 'Lan';

SELECT (destination).city
FROM types_lab.address_demo
WHERE recipient = 'Lan';

ROLLBACK;
~~~

### 10.2. Composite không tự áp dụng constraint cho từng thuộc tính

Trong cú pháp:

~~~sql
CREATE TYPE types_lab.shipping_address AS (
    line1 text,
    city text,
    postal_code text
);
~~~

không thể khai báo `city text NOT NULL` hay `CHECK (length(city) > 0)` ngay bên trong `CREATE TYPE ... AS (...)` theo cùng cách như `CREATE TABLE`.

Nếu một bảng cần bắt buộc thành phố:

~~~sql
CHECK (
    (destination).city IS NOT NULL
    AND btrim((destination).city) <> ''
)
~~~

thì đặt constraint tại **bảng** hoặc sử dụng domain cho các field liên quan.

Ví dụ dùng domain để ràng buộc một thuộc tính:

~~~sql
CREATE DOMAIN types_lab.nonblank_text AS text
NOT NULL
CHECK (length(btrim(VALUE)) > 0);

CREATE TYPE types_lab.strong_address AS (
    line1 types_lab.nonblank_text,
    city types_lab.nonblank_text,
    postal_code text
);
~~~

Domain trên `line1` và `city` giúp chặn giá trị rỗng/trắng ở những phép gán được kiểm tra, nhưng **toàn bộ giá trị composite vẫn có thể là null trong ngữ cảnh biểu thức**. Nếu một cột bắt buộc có địa chỉ, hãy giữ `NOT NULL` ở cấp cột và xem xét ràng buộc cấp bảng phù hợp.

### 10.3. Composite có thể chứa NULL ở một vài trường

~~~sql
SELECT ROW(
    '12 Nguyen Hue',
    'Ho Chi Minh City',
    NULL
)::types_lab.shipping_address AS address;
~~~

Giá trị trên có thể hợp lệ vì `postal_code` được khai báo `text` và không có ràng buộc không null. Điều đó khác với một bản ghi mà **toàn bộ composite** mang giá trị null.

PostgreSQL có quy tắc đặc biệt cho `IS NULL` / `IS NOT NULL` khi áp dụng với row/composite: một row mà tất cả field đều null có thể được coi là `IS NULL`; row chỉ có một vài field null có thể **không thỏa cả hai phép kiểm tra theo trực giác thông thường**. Vì thế, khi muốn kiểm tra một field bắt buộc, hãy kiểm tra **trực tiếp field đó**, thay vì suy từ `destination IS NOT NULL`.

## 11. Composite có thể làm kiểu tham số và kết quả của hàm

Không chỉ cột bảng, composite rất hữu ích trong chữ ký hàm.

~~~sql
CREATE FUNCTION types_lab.format_shipping_city(
    p_address types_lab.shipping_address
)
RETURNS text
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT ($1).city || ' - ' || ($1).line1
$$;
~~~

Gọi hàm:

~~~sql
SELECT types_lab.format_shipping_city(
    ROW(
        '12 Nguyen Hue',
        'Ho Chi Minh City',
        '700000'
    )::types_lab.shipping_address
) AS formatted_address;
~~~

Hàm nhận **một giá trị địa chỉ** thay vì ba tham số `line1`, `city` và `postal_code` riêng lẻ. Điều này làm chữ ký hàm gắn với một khái niệm miền dữ liệu có cấu trúc.

Đổi lại, thay cấu trúc composite có thể ảnh hưởng tất cả hàm, bảng và truy vấn đang dùng kiểu ấy. Lợi ích tái sử dụng đi kèm **mối phụ thuộc DDL**.

### 11.1. Function trả về composite

~~~sql
CREATE FUNCTION types_lab.make_shipping_address(
    p_line1 text,
    p_city text,
    p_postal_code text
)
RETURNS types_lab.shipping_address
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT ROW(
        p_line1, p_city, p_postal_code
    )::types_lab.shipping_address
$$;
~~~

Ví dụ:

~~~sql
SELECT (
    types_lab.make_shipping_address(
        '18 Tran Phu', 'Hue', '530000'
    )
).city AS city_name;
~~~

Cách viết này hữu ích cho API SQL có cấu trúc cố định. Nhưng nếu kết quả là **một tập nhiều hàng** với nhiều quan hệ và cần lọc/join thường xuyên, bảng quan hệ hoặc `RETURNS TABLE (...)` có thể phù hợp hơn một composite đóng gói mọi thứ.

## 12. Bảng tự động có một row type

Một điểm dễ nhầm: PostgreSQL **tự tạo composite row type** khi bạn tạo một bảng:

~~~sql
CREATE TABLE types_lab.warehouses (
    warehouse_id bigint PRIMARY KEY,
    name text NOT NULL
);
~~~

Bảng `types_lab.warehouses` vừa là một **relation**, vừa có một **row type** mô tả các cột của nó. Vì vậy, hàm PostgreSQL có thể trả về giá trị kiểu hàng của bảng, và các biểu thức row có thể dùng type tương ứng.

Tuy nhiên, row type của bảng và những **constraint của bảng** không có quan hệ “được áp dụng ở mọi nơi” như khi insert vào bảng:

- `PRIMARY KEY` và `UNIQUE` là các ràng buộc liên quan dữ liệu **trong bảng**.
- Nếu một biểu thức tạo giá trị composite mang row type của bảng, không nên giả định các constraint của bảng tự chạy trên mọi biểu thức độc lập ấy.
- Những quy tắc scalar cần tái sử dụng ngoài bảng có thể phù hợp hơn với **domain**.

Đây cũng là lý do tránh tạo một `CREATE TYPE` trùng tên với row type mà PostgreSQL sẽ sinh cho bảng trong cùng schema.

## 13. Kiểu tổng hợp, mảng và JSONB: nên chọn cách nào?

Nếu một đơn có một địa chỉ gồm ba thuộc tính cố định, composite có thể gọn. Nhưng nếu một đơn có **nhiều sản phẩm**, mỗi sản phẩm có giá, số lượng, SKU và lịch sử cập nhật, dùng một mảng composite duy nhất bên trong đơn hàng thường làm khó việc truy vấn và bảo vệ quan hệ.

| Nhu cầu | Hướng thiết kế thường hợp lý |
| --- | --- |
| Một giá trị có vài field cố định, thường đọc/ghi cùng nhau | Composite |
| Một giá trị scalar cần điều kiện tái sử dụng | Domain |
| Một danh sách trạng thái cố định ít thay đổi | Enum |
| Nhiều hàng con cần foreign key, index và truy vấn riêng | Bảng quan hệ |
| Metadata thay đổi cấu trúc thường xuyên | `jsonb` khi phù hợp |
| Một danh sách phần tử cùng kiểu với cấu trúc đơn giản | Array, sau khi cân nhắc giới hạn truy vấn |

### 13.1. Composite khác JSONB

Composite:

~~~sql
ROW('12 Nguyen Hue', 'Da Nang', '550000')
    ::types_lab.shipping_address
~~~

JSONB:

~~~sql
'{
  "line1": "12 Nguyen Hue",
  "city": "Da Nang",
  "postal_code": "550000"
}'::jsonb
~~~

Composite có cấu trúc trường và kiểu **được định nghĩa trước**, được PostgreSQL kiểm tra khi ép kiểu. JSONB linh hoạt hơn khi key khác nhau giữa các bản ghi, nhưng việc bảo đảm một key phải có mặt, đúng kiểu và thỏa quy tắc nghiệp vụ thường cần thêm giải pháp.

Nếu ứng dụng liên tục lọc theo `city`, cần đánh giá index phù hợp, thống kê và chi phí cập nhật cho **cả hai** cách biểu diễn. Composite không tự động tạo index theo từng field.

### 13.2. Composite khác nhóm cột rời trong bảng

Thiết kế cột rời:

~~~sql
CREATE TABLE types_lab.address_columns_demo (
    id bigint PRIMARY KEY,
    line1 text,
    city text,
    postal_code text
);
~~~

Cách này cho phép:

- Index đơn giản trực tiếp trên `city`.
- Constraint ở cấp từng cột, foreign key hoặc kết hợp nhiều cột.
- Truy vấn, thống kê và migration cột theo mô hình bảng thông thường.

Composite phù hợp khi muốn sử dụng **một giá trị địa chỉ như một đơn vị** trong cột/hàm, không phải vì nó luôn nhanh hoặc an toàn hơn ba cột tách biệt.

## 14. Bài thực hành tổng hợp ba loại kiểu

Tạo bảng `orders` gồm enum cho trạng thái, domain cho số lượng/đơn giá/mã đơn và composite cho địa chỉ.

> Nếu đã chạy các lệnh `RENAME VALUE` hoặc migration `order_status_v2` ở mục 5, hãy bảo đảm `types_lab.order_status` vẫn có các nhãn sử dụng dưới đây. Phần này giả định bạn giữ nguyên enum ban đầu với `pending`, `paid` và `cancelled`.

~~~sql
CREATE TABLE types_lab.orders (
    order_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_code types_lab.order_code NOT NULL UNIQUE,
    status types_lab.order_status NOT NULL DEFAULT 'pending',
    quantity types_lab.positive_quantity NOT NULL,
    unit_price types_lab.nonnegative_money NOT NULL,
    shipping_address types_lab.shipping_address NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_order_shipping_city
        CHECK (
            (shipping_address).city IS NOT NULL
            AND btrim((shipping_address).city) <> ''
        )
);
~~~

Đây là một bảng **rút gọn cho bài học kiểu dữ liệu**, chưa mô tả mô hình đơn hàng nhiều dòng sản phẩm hoặc hoàn tiền thực tế.

### 14.1. Chèn giá trị hợp lệ

~~~sql
INSERT INTO types_lab.orders (
    order_code,
    status,
    quantity,
    unit_price,
    shipping_address
)
VALUES
    (
        'ORD-001',
        'paid',
        2,
        75000.00,
        ROW(
            '12 Nguyen Hue',
            'Ho Chi Minh City',
            '700000'
        )::types_lab.shipping_address
    ),
    (
        'ORD-002',
        'pending',
        1,
        125000.00,
        ROW(
            '8 Bach Dang',
            'Da Nang',
            '550000'
        )::types_lab.shipping_address
    );
~~~

Các chuỗi `'paid'` và `'pending'` được suy diễn thành enum theo kiểu cột đích; số lượng và số tiền được kiểm tra theo domain.

### 14.2. Đọc và tính giá trị

~~~sql
SELECT
    order_id,
    order_code,
    status,
    quantity,
    unit_price,
    quantity * unit_price AS estimated_total,
    (shipping_address).city AS shipping_city
FROM types_lab.orders
ORDER BY order_id;
~~~

Vì `quantity` là domain trên `integer` và `unit_price` là domain trên `numeric`, các phép toán được hỗ trợ theo quy tắc giải quyết kiểu của PostgreSQL. Biểu thức `quantity * unit_price` có kiểu kết quả được suy ra từ các toán hạng/kiểu nền và **không tự trở thành `types_lab.nonnegative_money` chỉ vì một toán hạng dùng domain ấy**.

Nếu kết quả tính toán cần tuân theo domain riêng, có thể ép kiểu rõ ràng:

~~~sql
SELECT
    (quantity * unit_price)
        ::types_lab.nonnegative_money AS total_amount
FROM types_lab.orders;
~~~

### 14.3. Thử lỗi để thấy vai trò của kiểu

Chạy **từng câu riêng**:

~~~sql
-- Nhãn enum không tồn tại:
INSERT INTO types_lab.orders (
    order_code, status, quantity, unit_price, shipping_address
)
VALUES (
    'ORD-003',
    'in_delivery',
    1,
    15000.00,
    ROW('A', 'Da Nang', '550000')
        ::types_lab.shipping_address
);
~~~

~~~sql
-- Vi phạm domain số lượng:
INSERT INTO types_lab.orders (
    order_code, status, quantity, unit_price, shipping_address
)
VALUES (
    'ORD-004',
    'pending',
    -2,
    15000.00,
    ROW('A', 'Da Nang', '550000')
        ::types_lab.shipping_address
);
~~~

~~~sql
-- Vi phạm CHECK ở cấp bảng vì thành phố rỗng:
INSERT INTO types_lab.orders (
    order_code, status, quantity, unit_price, shipping_address
)
VALUES (
    'ORD-005',
    'pending',
    2,
    15000.00,
    ROW('A', '', '550000')
        ::types_lab.shipping_address
);
~~~

Ba lỗi trên xảy ra tại **ba tầng kiểm tra khác nhau**:

| Trường hợp | Lớp bảo vệ |
| --- | --- |
| `status = 'in_delivery'` | Enum không có nhãn đó |
| `quantity = -2` | Domain `positive_quantity` |
| `shipping_address.city = ''` | `CHECK` trên bảng `orders` |

Điều này cho thấy kiểu dữ liệu và constraint bảng **bổ sung cho nhau**, không phải mọi quy tắc có thể gom vào một loại kiểu duy nhất.

### 14.4. Truy vấn lọc theo enum và field composite

~~~sql
SELECT
    order_code,
    status,
    (shipping_address).city AS city
FROM types_lab.orders
WHERE status = 'paid'::types_lab.order_status
ORDER BY created_at DESC;
~~~

~~~sql
SELECT order_code
FROM types_lab.orders
WHERE (shipping_address).city = 'Da Nang';
~~~

Nếu truy vấn theo trạng thái hoặc thành phố diễn ra thường xuyên trên bảng lớn, có thể cân nhắc index.

~~~sql
CREATE INDEX idx_orders_status_created
ON types_lab.orders (status, created_at DESC);

CREATE INDEX idx_orders_shipping_city
ON types_lab.orders (((shipping_address).city));
~~~

`idx_orders_shipping_city` là **expression index** trên field của composite. Cần dấu ngoặc tương ứng để PostgreSQL phân tích biểu thức đúng. Index chỉ nên tạo khi workload và `EXPLAIN` cho thấy lợi ích đáng kể; mỗi index có chi phí lưu trữ và duy trì khi ghi.

## 15. Enum và bảng tra cứu trạng thái: lựa chọn thiết kế

Một thiết kế thay thế enum là bảng trạng thái:

~~~sql
CREATE TABLE types_lab.order_status_lookup (
    status_code text PRIMARY KEY,
    display_name text NOT NULL,
    sort_rank integer NOT NULL UNIQUE,
    is_active boolean NOT NULL DEFAULT true
);

INSERT INTO types_lab.order_status_lookup
    (status_code, display_name, sort_rank)
VALUES
    ('pending', 'Đang chờ', 10),
    ('paid', 'Đã thanh toán', 20),
    ('cancelled', 'Đã hủy', 30);
~~~

Một bảng nghiệp vụ có thể dùng:

~~~sql
status_code text NOT NULL
    REFERENCES types_lab.order_status_lookup(status_code)
~~~

Đây là **minh họa một thiết kế khác**, không phải thay đổi trực tiếp cột `orders.status` trong bài thực hành hiện tại.

| Tiêu chí | Enum | Bảng tra cứu + FK |
| --- | --- | --- |
| Tập giá trị nhỏ và hiếm đổi | Rất phù hợp | Cũng phù hợp |
| Thêm nhãn | `ALTER TYPE ... ADD VALUE` | `INSERT` thêm hàng tra cứu |
| Bỏ hoặc ngưng trạng thái | Khó xóa hẳn nhãn | Có thể đánh dấu `is_active` hoặc di chuyển dữ liệu trước khi xóa |
| Nhãn hiển thị đa ngôn ngữ | Thường quản lý ở ứng dụng/bảng khác | Có thể bổ sung bảng dịch hoặc metadata |
| Thứ tự hiển thị linh hoạt | Thứ tự enum cố định theo khai báo | Có thể dùng `sort_rank` |
| Cần metadata của trạng thái | Không chứa metadata tùy ý trong enum | Dễ có thêm cột |
| Áp dụng giá trị hợp lệ | Ràng buộc bởi bản thân kiểu | Ràng buộc bằng foreign key |

**Chọn enum khi tập nhãn ổn định và có ý nghĩa kiểu rõ ràng.** Nếu sản phẩm yêu cầu đội vận hành tự thêm trạng thái, thay đổi nhãn, gắn nhiều metadata hoặc quản lý vòng đời trạng thái liên tục, bảng tra cứu thường linh hoạt hơn.

Trạng thái không phải lúc nào cũng chỉ là danh sách giá trị. Quy tắc **được chuyển từ pending sang paid hay không** là một *state transition rule*, có thể cần transaction, logic nghiệp vụ hoặc trigger. Enum chỉ bảo đảm giá trị thuộc tập đã định nghĩa, **không tự giới hạn mọi chuyển trạng thái**.

## 16. Domain hay CHECK tại bảng?

Hai lựa chọn:

~~~sql
-- Quy tắc gắn trực tiếp với một cột của bảng.
quantity integer NOT NULL CHECK (quantity > 0)

-- Quy tắc được định nghĩa thành một kiểu chung.
quantity types_lab.positive_quantity NOT NULL
~~~

Domain có ích khi:

- Nhiều bảng hoặc hàm dùng cùng một ý nghĩa số lượng dương, mã vùng hoặc số tiền không âm.
- Muốn gom quy tắc chuyển đổi/kiểm tra scalar vào một đối tượng có tên dễ hiểu.
- Việc thay đổi quy tắc chung phải được quản lý tập trung và có quy trình kiểm thử.

`CHECK` ở cấp bảng có ích khi:

- Quy tắc chỉ áp dụng cho một bảng.
- Điều kiện phụ thuộc **nhiều cột của cùng một hàng**, ví dụ `end_at >= start_at`.
- Cần giữ business rule gần với cấu trúc bảng cụ thể.

Ví dụ:

~~~sql
CREATE TABLE types_lab.booking_demo (
    starts_at timestamptz NOT NULL,
    ends_at timestamptz NOT NULL,
    CONSTRAINT ck_booking_period
        CHECK (ends_at > starts_at)
);
~~~

Không có một domain scalar nào trên `ends_at` tự biết giá trị `starts_at` của **cùng hàng**. Đây là trường hợp tự nhiên cho `CHECK` ở cấp bảng.

### Khi domain quá dùng chung cũng có thể là nhược điểm

Giả sử domain `nonnegative_money` được dùng cho **giá gốc**, **giá hoàn tiền** và **hạn mức tín dụng**. Một ngày nghiệp vụ thay đổi: một loại số tiền cần được phép âm trong bút toán điều chỉnh, còn loại khác không.

Nếu mọi cột chia sẻ đúng một domain, việc sửa constraint chung có thể làm mất bảo vệ ở các bảng không liên quan. Khi đó nên có **những domain khác nhau theo ý nghĩa**, hoặc dùng kiểu nền với constraint riêng ở cấp bảng. Tái sử dụng chỉ tốt khi **quy tắc thực sự giống nhau**, không phải chỉ vì các cột đều là `numeric`.

## 17. Thay đổi cấu trúc composite và tác động phụ thuộc

PostgreSQL có cú pháp thay đổi thuộc tính composite:

~~~sql
ALTER TYPE types_lab.shipping_address
ADD ATTRIBUTE country_code text;
~~~

Sau khi bổ sung thuộc tính, kiểu có thêm field:

~~~text
shipping_address
├── line1
├── city
├── postal_code
└── country_code
~~~

Nhưng điều đó ảnh hưởng những nơi đang tạo giá trị composite theo **vị trí**:

~~~sql
ROW('A', 'Da Nang', '550000')::types_lab.shipping_address
~~~

vốn có ba trường, có thể không còn ép kiểu được theo kiểu mới có bốn thuộc tính. Function, script import, prepared statement hoặc driver có mapping theo số/thứ tự trường cũng cần được xem xét.

Thêm một thuộc tính vào composite **không tự tạo một giá trị country_code hợp lệ cho mọi dòng**. Cần kế hoạch cập nhật dữ liệu và ứng dụng, xử lý null/default và khả năng tương thích giữa các phiên bản.

### 17.1. Một số thao tác ALTER TYPE dành cho composite

PostgreSQL hỗ trợ các thao tác như:

~~~sql
-- Minh họa cú pháp, không chạy đồng loạt trên kiểu đang dùng.
ALTER TYPE types_lab.shipping_address
RENAME ATTRIBUTE postal_code TO zip_code;

ALTER TYPE types_lab.shipping_address
ALTER ATTRIBUTE postal_code TYPE varchar(20);

ALTER TYPE types_lab.shipping_address
DROP ATTRIBUTE postal_code;
~~~

Những câu trên là **các phương án thay đổi riêng biệt**; nếu đã chạy `RENAME ATTRIBUTE` thì tên `postal_code` không còn cho hai câu sau. Không chạy như một chuỗi bắt buộc. Những đối tượng đang phụ thuộc có thể khiến PostgreSQL từ chối thay đổi hoặc cần xử lý bổ sung.

### 17.2. Khi nào nên tránh composite trong API bền vững?

Nếu nhiều ứng dụng bên ngoài phụ thuộc vào một kiểu composite có nhiều trường và schema thay đổi thường xuyên, việc thêm/đổi tên field có thể trở thành **breaking change**.

Một giải pháp có thể là:

- Giữ kiểu composite ổn định làm giao diện của hàm.
- Tạo một kiểu `shipping_address_v2` khi hợp đồng dữ liệu thay đổi lớn.
- Dùng migration rõ ràng để chuyển cột/hàm sang kiểu mới.
- Với payload biến đổi hoặc tài liệu trao đổi linh hoạt, cân nhắc JSONB có validation thích hợp.

Không nên sửa một composite đang dùng khắp hệ thống chỉ vì muốn thêm một cột cho một màn hình.

## 18. Kiểm tra metadata của enum, domain và composite

Sau khi tạo các kiểu, có thể kiểm tra trực tiếp qua system catalog.

### 18.1. Liệt kê kiểu do người dùng định nghĩa

~~~sql
SELECT
    n.nspname AS schema_name,
    t.typname AS type_name,
    t.typtype,
    CASE t.typtype
        WHEN 'e' THEN 'enum'
        WHEN 'd' THEN 'domain'
        WHEN 'c' THEN 'composite'
        ELSE 'other'
    END AS type_kind
FROM pg_type AS t
JOIN pg_namespace AS n
    ON n.oid = t.typnamespace
WHERE n.nspname = 'types_lab'
  AND t.typtype IN ('e', 'd', 'c')
ORDER BY type_kind, type_name;
~~~

`typtype = 'c'` còn bao gồm các **row type được tự tạo cho bảng**, không chỉ composite được khai báo rõ bằng `CREATE TYPE ... AS (...)`. Khi liệt kê phải hiểu danh sách này có thể có `orders`, `address_demo` hoặc bảng thực hành khác.

### 18.2. Xem nhãn enum và thứ tự

~~~sql
SELECT
    t.typname AS enum_name,
    e.enumlabel AS label,
    e.enumsortorder AS sort_order
FROM pg_type AS t
JOIN pg_namespace AS n
    ON n.oid = t.typnamespace
JOIN pg_enum AS e
    ON e.enumtypid = t.oid
WHERE n.nspname = 'types_lab'
  AND t.typname = 'order_status'
ORDER BY e.enumsortorder;
~~~

`pg_enum.enumsortorder` lưu thông tin thứ tự; không nên coi OID của từng nhãn hoặc thứ tự chữ cái là cách thay thế chắc chắn cho `ORDER BY` enum.

### 18.3. Xem domain và kiểu nền

~~~sql
SELECT
    t.typname AS domain_name,
    format_type(t.typbasetype, t.typtypmod) AS base_type,
    t.typnotnull AS domain_not_null,
    t.typdefault AS domain_default
FROM pg_type AS t
JOIN pg_namespace AS n
    ON n.oid = t.typnamespace
WHERE n.nspname = 'types_lab'
  AND t.typtype = 'd'
ORDER BY t.typname;
~~~

Để xem các domain CHECK constraints:

~~~sql
SELECT
    t.typname AS domain_name,
    c.conname AS constraint_name,
    pg_get_constraintdef(c.oid) AS definition,
    c.convalidated AS is_validated
FROM pg_constraint AS c
JOIN pg_type AS t
    ON t.oid = c.contypid
JOIN pg_namespace AS n
    ON n.oid = t.typnamespace
WHERE n.nspname = 'types_lab'
  AND t.typtype = 'd'
ORDER BY t.typname, c.conname;
~~~

### 18.4. Xem các field của composite đã khai báo riêng

~~~sql
SELECT
    t.typname AS composite_name,
    a.attnum AS attribute_position,
    a.attname AS attribute_name,
    format_type(a.atttypid, a.atttypmod) AS attribute_type
FROM pg_type AS t
JOIN pg_namespace AS n
    ON n.oid = t.typnamespace
JOIN pg_class AS cl
    ON cl.oid = t.typrelid
   AND cl.relkind = 'c'
JOIN pg_attribute AS a
    ON a.attrelid = cl.oid
WHERE n.nspname = 'types_lab'
  AND a.attnum > 0
  AND NOT a.attisdropped
ORDER BY t.typname, a.attnum;
~~~

`relkind = 'c'` giúp tập trung vào composite type được khai báo rõ, thay vì lấy row type của mọi bảng thông thường.

Trong `psql`, các meta-command như `\dT+` có thể giúp xem các kiểu dữ liệu do người dùng định nghĩa. Khi cần biết **dependency thật sự**, có thể dùng `pg_depend` cùng các catalog liên quan, vì một kiểu có thể đang được sử dụng ở nhiều bảng và function.

## 19. Quyền, schema và vòng đời các kiểu

Enum, domain và composite đều là các **đối tượng schema** của PostgreSQL.

Một tài khoản cần quyền phù hợp:

- Để tạo kiểu trong schema, role cần quyền tạo đối tượng trong schema đó.
- Để sử dụng kiểu trong đối tượng hay biểu thức, có thể cần quyền `USAGE` trên schema và trên type theo quy tắc áp dụng.
- Để thay đổi hoặc xóa kiểu, cần quyền sở hữu/quản trị tương ứng.

Ví dụ minh họa cấp quyền:

~~~sql
GRANT USAGE ON SCHEMA types_lab TO app_role;

GRANT USAGE ON TYPE
    types_lab.order_status,
    types_lab.positive_quantity,
    types_lab.shipping_address
TO app_role;
~~~

Lệnh trên chỉ minh họa; `app_role` phải tồn tại. Nó **không cấp quyền `SELECT`, `INSERT` hoặc `UPDATE` trên bảng**. Quyền sử dụng kiểu và quyền thao tác dữ liệu bảng là các lớp kiểm soát khác nhau.

### 19.1. DROP TYPE RESTRICT và CASCADE

~~~sql
-- Mặc định thận trọng khi còn đối tượng phụ thuộc:
DROP TYPE types_lab.order_status RESTRICT;

-- Nguy hiểm hơn: có thể kéo theo đối tượng phụ thuộc.
DROP TYPE types_lab.order_status CASCADE;
~~~

Khi type đang là kiểu của một cột bảng, `RESTRICT` thường từ chối xóa. `CASCADE` có thể làm PostgreSQL **xóa những đối tượng phụ thuộc cần thiết**, trong đó có cột hoặc thành phần schema sử dụng type, tùy đồ thị dependency.

Vì vậy **không chạy `DROP TYPE ... CASCADE` chỉ để dọn lỗi tên trùng trên môi trường có dữ liệu thật**. Hãy kiểm kê các cột, view, hàm và constraint liên quan trước.

### 19.2. Thay đổi kiểu ảnh hưởng nhiều nơi

Trong một schema lớn, một domain `positive_quantity` có thể được dùng ở 12 bảng, nhiều hàm và view. Chỉnh constraint của domain làm thay đổi **quy tắc chung**, còn chỉnh một field của composite hoặc nhãn enum có thể làm thay đổi hợp đồng dữ liệu ở nhiều client.

Nên có:

1. Danh sách nơi dùng kiểu.
2. Kế hoạch cập nhật code và schema đồng thời.
3. Migration trên môi trường staging với dữ liệu đại diện.
4. Kế hoạch backfill/đối soát.
5. Backup và phương án rollback phù hợp.

Sự tái sử dụng giúp giảm lặp định nghĩa, nhưng cũng làm thay đổi kiểu trở thành một thao tác có **phạm vi ảnh hưởng rộng hơn**.

## 20. Lựa chọn kiểu khi tích hợp Java/JDBC

Khi làm việc từ Java, các kiểu PostgreSQL tự định nghĩa có thể cần xử lý rõ hơn những kiểu cơ bản như `integer` và `varchar`.

### Enum và tham số bind

Một cách rõ ràng khi viết SQL có tham số chuỗi:

~~~sql
SELECT order_id, order_code
FROM types_lab.orders
WHERE status = CAST(? AS types_lab.order_status);
~~~

Với PostgreSQL JDBC, cú pháp dấu `?` được driver xử lý dưới dạng tham số prepared statement. Cách bind giá trị phụ thuộc driver và mapping ứng dụng. Có thể dùng các loại wrapper như `PGobject` hoặc framework mapping phù hợp; không nên đoán rằng enum PostgreSQL **tự biến thành** `java.lang.Enum` trong mọi môi trường.

### Domain ở phía Java

Domain có kiểu nền, nên giá trị đọc về qua driver thường có thể được xử lý như kiểu nền tương ứng (ví dụ `integer` hoặc `BigDecimal`) tùy API và mapping. Nhưng ràng buộc domain được PostgreSQL kiểm tra khi nhận giá trị, không phải một lớp validation Java tự phát sinh.

Ứng dụng vẫn cần kiểm tra đầu vào để trả thông báo thân thiện, nhưng **không nên coi validation phía ứng dụng là lớp bảo vệ duy nhất**.

### Composite ở phía Java

Composite có định dạng chuyển đổi qua PostgreSQL protocol; mapping tự động sang Java record/POJO không phải lúc nào được cung cấp sẵn bởi driver JDBC cơ bản. Các lựa chọn:

- Viết SQL tách field: `(shipping_address).city AS city` để ánh xạ từng cột.
- Sử dụng API/mapping tùy chỉnh của driver hoặc ORM nếu được hỗ trợ.
- Dùng các cột thông thường hoặc JSONB khi API và yêu cầu thay đổi cấu trúc khiến composite trở nên bất tiện.

Đừng chọn composite chỉ vì nó “giống object Java”. Hãy ưu tiên cấu trúc hợp lý cho **query, constraint và migration ở PostgreSQL**.

## 21. Những sai lầm thường gặp

### Sai lầm 1: Dùng enum cho danh mục được thêm/xóa mỗi ngày

Enum phù hợp tập nhãn ổn định. Với danh mục quản trị động, bảng tra cứu thường dễ thêm metadata, tạm ngừng hoặc xóa theo chính sách hơn.

### Sai lầm 2: Nghĩ thứ tự enum là thứ tự từ điển

`ORDER BY status` sắp theo thứ tự khai báo giá trị enum, không theo chữ cái. Nếu cần thứ tự nghiệp vụ khác, hãy viết quy tắc sắp xếp tương ứng.

### Sai lầm 3: Nghĩ có thể xóa nhãn enum bằng một DROP VALUE

Đổi tập nhãn theo hướng loại giá trị thường đòi hỏi migration sang enum mới cùng xử lý dữ liệu và dependency.

### Sai lầm 4: Dùng domain để kiểm tra quan hệ giữa nhiều bảng

Domain `CHECK (VALUE > 0)` bảo vệ scalar. Nó không thay thế foreign key, unique constraint hoặc transaction cần thiết cho những điều kiện liên quan nhiều hàng.

### Sai lầm 5: Viết CHECK rồi quên NULL

`CHECK (VALUE > 0)` không tự chặn null, vì unknown không phải false. Dùng `NOT NULL` ở domain/cột khi nghiệp vụ yêu cầu.

### Sai lầm 6: Nghĩ composite tự có NOT NULL, UNIQUE và FK cho field

`CREATE TYPE ... AS (...)` định nghĩa cấu trúc field, không cung cấp toàn bộ hệ ràng buộc của `CREATE TABLE`. Dùng domain cho field hoặc constraint tại bảng khi cần.

### Sai lầm 7: Dùng composite thay cho bảng chi tiết một-nhiều

Một mảng composite trong cột không tự có foreign key theo từng phần tử, index theo quan hệ hay cơ chế cập nhật độc lập như bảng quan hệ.

### Sai lầm 8: Đổi cấu trúc composite mà không kiểm tra ROW constructor

Thêm một field làm những lời gọi `ROW(...)::type` theo số vị trí cũ có thể thất bại. Cần kiểm kê hàm, ứng dụng và dữ liệu.

### Sai lầm 9: Thêm index cho kiểu mới mà không nhìn workload

Enum/domain/composite **không tự đảm bảo truy vấn nhanh**. Chỉ mục cần chọn theo `WHERE`, `JOIN`, `ORDER BY` và phân bố dữ liệu; đánh giá cả chi phí ghi.

### Sai lầm 10: Chỉ xác thực giá trị bằng ứng dụng

Ứng dụng có thể có đường ghi khác như import, script vận hành hoặc service mới. Kiểu dữ liệu và constraint ở PostgreSQL giúp giữ tính nhất quán ngay tại nơi lưu dữ liệu.

## 22. Bài tập thực hành

Các bài tập dựa trên schema `types_lab`, có thể làm bằng cách dự đoán trước rồi thử trên PostgreSQL lab. Không thực hiện các lệnh xóa/cấu trúc trên database có dữ liệu cần giữ.

### Bài 1. Chọn kiểu phù hợp

Chọn enum, domain, composite hoặc bảng quan hệ cho từng trường hợp:

1. Trạng thái bài viết: `draft`, `published`, `archived`, rất hiếm bổ sung.
2. Một số lượng đặt hàng phải lớn hơn 0, áp dụng ở nhiều bảng.
3. Một tọa độ gồm kinh độ và vĩ độ, được truyền vào một số hàm.
4. Một đơn hàng có nhiều dòng sản phẩm, mỗi dòng cần khóa ngoại và index riêng.

### Bài 2. Tạo enum mới

Viết lệnh tạo `types_lab.review_state` có các nhãn `new`, `approved`, `rejected` theo thứ tự đó. Sau đó tạo một giá trị `'approved'` được ép kiểu rõ ràng.

### Bài 3. Dự đoán ORDER BY

Với:

~~~sql
CREATE TYPE types_lab.level_code AS ENUM (
    'medium', 'low', 'high'
);
~~~

`ORDER BY level_code` sẽ đưa `low` trước `medium` không? Vì sao?

### Bài 4. Domain và NULL

Cho:

~~~sql
CREATE DOMAIN types_lab.score AS integer
CHECK (VALUE >= 0 AND VALUE <= 100);
~~~

`NULL::types_lab.score` có thể được chấp nhận không? Nếu cột `score` của bảng phải bắt buộc có giá trị, hãy viết khai báo cột phù hợp.

### Bài 5. Domain và UNIQUE

Domain `types_lab.order_code` chỉ có constraint format. Hai hàng có thể cùng `order_code = 'ORD-001'` không? Cần thêm constraint nào ở bảng để ngăn trùng?

### Bài 6. Truy cập field của composite

Cho cột `destination types_lab.shipping_address`, viết truy vấn trả về `line1` và `city` của từng hàng trong `types_lab.address_demo`.

### Bài 7. Thiết kế constraint cho composite

Vì sao `CREATE TYPE shipping_address AS (city text)` không đủ để buộc `city` luôn khác null và không rỗng trong mọi hàng bảng? Nêu cách bổ sung ràng buộc.

### Bài 8. Enum và migration

Vì sao loại hẳn nhãn `cancelled` khỏi `types_lab.order_status` thường cần migration riêng? Nêu các bước chính trước khi bỏ kiểu cũ.

### Bài 9. Composite thay JSONB?

Một event nhận metadata từ nhiều đối tác, mỗi đối tác có tập field khác nhau và thay đổi liên tục. Có nên tạo một composite duy nhất gồm hàng trăm field tùy chọn không? Hãy giải thích.

### Bài 10. Truy vấn metadata

Viết truy vấn liệt kê các nhãn của enum `types_lab.order_status` theo thứ tự so sánh, sử dụng `pg_type` và `pg_enum`.

### Bài 11. Dự đoán lỗi tổng hợp

Giả sử bảng `types_lab.orders` có domain `quantity > 0` và enum `status`. Xác định lớp kiểm tra từ chối các giá trị:

~~~text
quantity = -1
status = 'unknown'
shipping_address.city = ''
order_code trùng một đơn đã có
~~~

### Bài 12. Đánh giá hiệu năng

Một bảng dùng cột composite `shipping_address` và thường lọc bằng `(shipping_address).city = 'Da Nang'`. Có thể lập index theo biểu thức này không? Index ấy có nên tạo chỉ vì cú pháp cho phép?

### Gợi ý đáp án

**Bài 1:** (1) enum; (2) domain; (3) composite; (4) bảng quan hệ con vì cần quản lý nhiều hàng với constraint và index riêng.

**Bài 2:**

~~~sql
CREATE TYPE types_lab.review_state AS ENUM (
    'new',
    'approved',
    'rejected'
);

SELECT 'approved'::types_lab.review_state;
~~~

**Bài 3:** không. Thứ tự enum là `medium < low < high` vì được định nghĩa theo thứ tự đó, không phải theo bảng chữ cái.

**Bài 4:** có thể chấp nhận null vì biểu thức `CHECK` trả unknown. Đặt `score types_lab.score NOT NULL` ở cột để bảo vệ không null; có thể cân nhắc `NOT NULL` trong domain khi quy tắc dùng chung cũng yêu cầu.

**Bài 5:** format domain không bảo đảm uniqueness giữa các hàng; thêm `UNIQUE (order_code)` hoặc unique index phù hợp ở bảng.

**Bài 6:**

~~~sql
SELECT
    (destination).line1 AS line1,
    (destination).city AS city
FROM types_lab.address_demo;
~~~

**Bài 7:** composite chỉ định nghĩa các trường và kiểu; cần `CHECK`/`NOT NULL` ở bảng hoặc domain cho các thuộc tính có quy tắc scalar tương ứng.

**Bài 8:** không có `ALTER TYPE ... DROP VALUE` thông dụng; cần chuyển dữ liệu khỏi giá trị cũ, tạo kiểu mới, xử lý default, cast cột, dependency và chỉ xóa kiểu cũ khi an toàn.

**Bài 9:** thường không nên nếu field biến đổi liên tục. JSONB hoặc mô hình sự kiện phù hợp có thể linh hoạt hơn, với validation/index có chủ đích.

**Bài 10:**

~~~sql
SELECT
    e.enumlabel,
    e.enumsortorder
FROM pg_enum AS e
JOIN pg_type AS t
    ON t.oid = e.enumtypid
JOIN pg_namespace AS n
    ON n.oid = t.typnamespace
WHERE n.nspname = 'types_lab'
  AND t.typname = 'order_status'
ORDER BY e.enumsortorder;
~~~

**Bài 11:** số âm bị domain `positive_quantity` từ chối; `unknown` bị enum từ chối; thành phố rỗng bị `CHECK` tại bảng; mã trùng bị unique constraint trên `orders.order_code` từ chối.

**Bài 12:** có thể tạo expression index trên `((shipping_address).city)`; chỉ nên làm sau khi đo workload, độ chọn lọc và chi phí duy trì index.

## 23. Danh sách kiểm tra trước khi đưa kiểu mới vào production

| Câu hỏi | Enum | Domain | Composite |
| --- | --- | --- | --- |
| Tập giá trị/quy tắc có ổn định lâu dài? | Rất quan trọng | Quan trọng nếu dùng lại ở nhiều bảng | Quan trọng nếu nhiều hàm/client dùng |
| Có cần metadata và bảng tra cứu? | Nếu có, cân nhắc lookup table | Không phải chức năng chính | Không thay thế bảng quan hệ |
| Có ràng buộc scalar tái sử dụng? | Tập nhãn | `CHECK`, `NOT NULL` | Có thể dùng domain cho từng field |
| Có nhiều hàng con cần khóa riêng? | Không giải quyết | Không giải quyết | Không thay bảng quan hệ |
| Thay đổi kiểu ảnh hưởng những gì? | Nhãn, so sánh, cast và SQL ứng dụng | Cột/hàm đang dùng domain | Field, ROW constructor, mapping và hàm |
| Có cần index? | Theo truy vấn enum | Theo cột/biểu thức thực tế | Có thể dùng index theo field |
| Có thể migration và rollback? | Cần kế hoạch cẩn thận nếu bỏ/đổi nhãn | Kiểm tra dữ liệu cũ trước khi validate | Kiểm tra tương thích chữ ký và field |

## 24. Bảng cú pháp tra cứu nhanh

| Nhiệm vụ | Cú pháp |
| --- | --- |
| Tạo enum | `CREATE TYPE schema.name AS ENUM ('a', 'b');` |
| Thêm nhãn enum | `ALTER TYPE schema.name ADD VALUE 'c' AFTER 'b';` |
| Đổi nhãn enum | `ALTER TYPE schema.name RENAME VALUE 'a' TO 'x';` |
| Ép giá trị thành enum | `'a'::schema.name` |
| Tạo domain | `CREATE DOMAIN schema.name AS integer CHECK (VALUE > 0);` |
| Domain không null | `CREATE DOMAIN schema.name AS integer NOT NULL CHECK (...);` |
| Thêm constraint domain | `ALTER DOMAIN schema.name ADD CONSTRAINT ... CHECK (...);` |
| Validate domain constraint | `ALTER DOMAIN schema.name VALIDATE CONSTRAINT constraint_name;` |
| Tạo composite | `CREATE TYPE schema.name AS (field1 text, field2 integer);` |
| Tạo giá trị composite | `ROW('abc', 123)::schema.name` |
| Đọc field composite | `(composite_value).field1` |
| Trải các field | `(composite_value).*` |
| Thêm field composite | `ALTER TYPE schema.name ADD ATTRIBUTE field3 text;` |
| Liệt kê nhãn enum | `pg_enum` + `pg_type` |
| Xem constraint domain | `pg_constraint` với `contypid` |
| Xem thuộc tính composite | `pg_attribute` + `pg_type.typrelid` |

## 25. Tổng kết

**Enum** làm rõ một giá trị thuộc **tập nhãn hữu hạn và có thứ tự**. Nó phù hợp trạng thái ổn định, nhưng việc loại bỏ nhãn hoặc thay đổi hợp đồng dữ liệu về sau không đơn giản như sửa một hàng trong bảng tra cứu.

**Domain** gói một kiểu nền cùng **quy tắc hợp lệ của một giá trị**. Nó giúp tái sử dụng kiểm tra scalar như số lượng dương, số tiền không âm hoặc mã có định dạng cố định; nhưng không tự thay thế khóa ngoại, tính duy nhất giữa các hàng hoặc constraint so sánh nhiều cột.

**Composite** biểu diễn **một giá trị có nhiều trường có tên**, hữu ích trong cột và chữ ký hàm. Tuy nhiên, nó không tự mang đầy đủ constraint của bảng quan hệ, và thay đổi cấu trúc có thể ảnh hưởng các phép tạo `ROW`, function, mapping và truy vấn.

Khi chọn một trong ba loại, hãy đặt câu hỏi: **đây là một tập trạng thái, một giá trị có điều kiện, hay một cấu trúc nhiều thuộc tính?** Sau đó xét thêm tốc độ thay đổi nghiệp vụ, khả năng truy vấn/index, ràng buộc còn thiếu, dependency và kế hoạch migration. Một kiểu dữ liệu được đặt tên rõ ràng có thể làm schema dễ hiểu hơn, nhưng chỉ thật sự hữu ích khi nó giúp **bảo vệ đúng dữ liệu mà không tạo ra phụ thuộc khó kiểm soát**.
