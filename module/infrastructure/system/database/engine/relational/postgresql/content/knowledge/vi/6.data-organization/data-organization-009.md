# COMMENT và tài liệu hóa đối tượng ngay trong cơ sở dữ liệu PostgreSQL

Khi một cơ sở dữ liệu có hàng trăm bảng và hàng nghìn cột, tên đối tượng không phải lúc nào cũng giải thích được ý nghĩa nghiệp vụ. Cột `status` có thể chứa những trạng thái nào? `amount` là giá trước hay sau thuế? `customer_id` tham chiếu khách hàng mua hàng hay khách hàng được lập hóa đơn? Một index được tạo để phục vụ API nào? Nếu thông tin chỉ tồn tại trong đầu một lập trình viên hoặc một tài liệu nằm ngoài repository, người bảo trì rất dễ hiểu sai khi viết truy vấn hay migration.

PostgreSQL hỗ trợ **`COMMENT ON`** để lưu mô tả trực tiếp vào **metadata của đối tượng trong database**. Các mô tả đó có thể được xem bằng `psql</BT>, đọc qua system catalogs như `pg_description`, truy vấn qua những hàm như `obj_description()` và `col_description()`, hoặc được đưa vào bản xuất schema để lưu cùng lịch sử migration.

Tài liệu hóa ngay trong database giúp người làm việc với dữ liệu có thêm ngữ cảnh đúng tại nơi họ thao tác. Tuy nhiên, comment **không thay thế** ràng buộc, thiết kế mô hình, phân quyền, tài liệu nghiệp vụ đầy đủ hoặc quy trình kiểm soát phiên bản. Bài này thuộc chương **Tổ chức dữ liệu** của PostgreSQL: tập trung vào cú pháp, cách đặt mô tả hữu ích, ví dụ thực hành, cách truy xuất và cách quản trị comment an toàn trong dự án.

## 1. COMMENT ON là gì?

`COMMENT ON` là câu lệnh DDL của PostgreSQL dùng để **gắn một đoạn mô tả văn bản vào một đối tượng database**. Ví dụ:

~~~sql
COMMENT ON TABLE public.orders IS
    'Đơn hàng do khách đặt. Mỗi hàng biểu diễn một đơn duy nhất.';

COMMENT ON COLUMN public.orders.created_at IS
    'Thời điểm tạo đơn; lưu theo kiểu timestamptz.';
~~~

Hai câu lệnh trên không thêm hàng và không đổi kiểu cột. Chúng thêm **metadata giải thích đối tượng**.

Một comment có thể giúp trả lời:

- Đối tượng này phục vụ nghiệp vụ gì?
- Ý nghĩa chính xác của cột là gì?
- Đơn vị đo, múi giờ hoặc độ chính xác của giá trị là gì?
- Những giá trị hoặc trạng thái nào được kỳ vọng?
- Dữ liệu do hệ thống nào tạo và được cập nhật theo quy tắc nào?
- Vì sao một index hoặc constraint được giữ lại?
- Có lưu ý nào khi dùng view, function hoặc khóa ngoại?

### 1.1. Khác biệt giữa tên, kiểu dữ liệu, constraint và comment

Giả sử có cột:

~~~sql
amount NUMERIC(14, 2) NOT NULL
~~~

Những thông tin đã biết:

- Tên là `amount`.
- Kiểu dữ liệu là `NUMERIC(14,2)`.
- Không được lưu `NULL`.

Những thông tin **chưa biết**:

- Đây là tổng tiền của đơn hay tổng tiền đã hoàn?
- Tiền tệ là VND, USD hay được quyết định bởi cột khác?
- Giá trị có gồm thuế và phí vận chuyển hay không?
- Có được phép âm khi đơn hoàn tiền không?
- Giá trị là tổng tại thời điểm tạo hay được tính lại?

Một comment có thể làm rõ:

~~~sql
COMMENT ON COLUMN public.orders.amount IS
    'Tổng tiền đơn sau giảm giá, chưa gồm phí vận chuyển; '
    'đơn vị là VND theo cấu hình của hệ thống này.';
~~~

Nhưng nếu database thật cho phép nhiều tiền tệ, việc ghi “đơn vị VND” sẽ trở thành mô tả sai. **Chỉ viết comment khi đã xác định đúng quy tắc nghiệp vụ**; không tự suy luận ý nghĩa từ tên cột.

### 1.2. Comment không phải constraint

~~~sql
COMMENT ON COLUMN public.products.price IS
    'Giá không được âm.';
~~~

Đây chỉ là văn bản mô tả. Nó **không chặn** việc ghi `-100</BT> vào cột. Muốn PostgreSQL thực thi quy tắc, cần constraint thích hợp:

~~~sql
ALTER TABLE public.products
ADD CONSTRAINT chk_products_price
CHECK (price >= 0);
~~~

Khi đó, comment có thể giải thích **lý do** của constraint:

~~~sql
COMMENT ON CONSTRAINT chk_products_price
ON public.products IS
    'Không cho phép giá bán âm khi tạo hoặc cập nhật sản phẩm.';
~~~

Nói ngắn gọn:

> **Constraint giúp hệ quản trị kiểm tra quy tắc; comment giúp con người hiểu quy tắc.**

## 2. Đối tượng PostgreSQL nào có thể được comment?

PostgreSQL hỗ trợ comment cho nhiều loại đối tượng. Các nhóm thường gặp gồm:

| Đối tượng | Mẫu cú pháp | Nội dung nên ghi |
|---|---|---|
| Schema | `COMMENT ON SCHEMA ... IS ...` | Phạm vi nghiệp vụ và quy ước |
| Table | `COMMENT ON TABLE ... IS ...` | Vai trò của một hàng, vòng đời dữ liệu |
| Column | `COMMENT ON COLUMN table.column IS ...` | Ý nghĩa, đơn vị, NULL, thời điểm |
| View | `COMMENT ON VIEW ... IS ...` | Mục đích truy vấn và giới hạn sử dụng |
| Materialized view | `COMMENT ON MATERIALIZED VIEW ... IS ...` | Dữ liệu tổng hợp, lịch refresh |
| Index | `COMMENT ON INDEX ... IS ...` | Mẫu truy vấn được hỗ trợ, lý do tồn tại |
| Constraint | `COMMENT ON CONSTRAINT ... ON table IS ...` | Quy tắc nghiệp vụ được thực thi |
| Sequence | `COMMENT ON SEQUENCE ... IS ...` | Mục đích cấp giá trị |
| Function | `COMMENT ON FUNCTION name(types) IS ...` | Đầu vào, đầu ra, tính chất và giới hạn |
| Procedure | `COMMENT ON PROCEDURE name(types) IS ...` | Công việc và tác động phụ |
| Type / domain | `COMMENT ON TYPE/DOMAIN ... IS ...` | Ý nghĩa kiểu, phạm vi giá trị |
| Trigger | `COMMENT ON TRIGGER name ON table IS ...` | Khi nào kích hoạt và tác động |
| Policy | `COMMENT ON POLICY name ON table IS ...` | Mục tiêu của chính sách RLS |
| Database | `COMMENT ON DATABASE ... IS ...` | Vai trò database trong hệ thống |
| Role | `COMMENT ON ROLE ... IS ...` | Mục đích tài khoản/nhóm quyền |

PostgreSQL còn có thể hỗ trợ comment trên những loại đối tượng khác như tablespace, extension, text-search objects, operators, publication hoặc subscription tùy phiên bản. Không cần ghi nhớ toàn bộ danh sách ngay: trong `psql`, tra cứu cú pháp của phiên bản đang dùng bằng:

~~~text
\h COMMENT
~~~

**Cú pháp của các nhóm khác nhau không hoàn toàn đồng nhất.** Đặc biệt, comment một column, constraint, trigger hay routine có phần xác định đối tượng riêng; không thể lấy cú pháp `COMMENT ON TABLE` rồi thay một từ tùy ý mà luôn đúng.

## 3. Cú pháp chung và cách viết chuỗi mô tả

Dạng tổng quát:

~~~sql
COMMENT ON object_type object_identity IS 'mô tả';
~~~

Trong đó:

- `object_type` là loại đối tượng, ví dụ `TABLE`, `COLUMN`, `VIEW`.
- `object_identity` xác định chính xác đối tượng cần mô tả.
- Phần sau `IS` là **giá trị chuỗi văn bản** hoặc `NULL` để xóa comment.

Ví dụ:

~~~sql
COMMENT ON SCHEMA sales IS
    'Dữ liệu nghiệp vụ bán hàng của ứng dụng.';

COMMENT ON TABLE sales.orders IS
    'Mỗi hàng là một đơn hàng do khách tạo.';

COMMENT ON COLUMN sales.orders.status IS
    'Trạng thái nghiệp vụ của đơn theo luồng xử lý.';
~~~

### 3.1. Một đối tượng có một comment hiện hành

Khi chạy lại `COMMENT ON` trên cùng đối tượng, PostgreSQL **thay thế mô tả trước đó** bằng mô tả mới:

~~~sql
COMMENT ON TABLE sales.orders IS
    'Đơn hàng được tạo từ ứng dụng.';

COMMENT ON TABLE sales.orders IS
    'Mỗi hàng là một đơn; dữ liệu do dịch vụ bán hàng quản lý.';
~~~

Sau câu thứ hai, mô tả hiện hành là chuỗi thứ hai. Đây không phải cơ chế ghi thêm nhật ký hay giữ mọi phiên bản comment.

Nếu cần biết lịch sử mô tả thay đổi thế nào, cần **migration history, hệ thống quản lý phiên bản hoặc audit log**, không chỉ đọc comment hiện tại.

### 3.2. Dùng IS NULL để xóa comment

~~~sql
COMMENT ON TABLE sales.orders IS NULL;
~~~

Đối tượng `sales.orders` vẫn tồn tại, chỉ phần comment bị xóa.

Phân biệt:

~~~sql
-- Xóa mô tả:
COMMENT ON TABLE sales.orders IS NULL;

-- Đặt mô tả là chuỗi rỗng:
COMMENT ON TABLE sales.orders IS '';
~~~

Một câu dùng SQL `NULL`, câu kia dùng **chuỗi rỗng**. Trong báo cáo tài liệu hóa, có thể coi cả hai là “thiếu mô tả hữu ích”, nhưng không nên mặc định chúng có cùng biểu diễn metadata.

### 3.3. Dấu nháy đơn bên trong comment

Chuỗi SQL sử dụng dấu nháy đơn. Nếu comment cần có dấu nháy đơn, hãy lặp dấu nháy:

~~~sql
COMMENT ON COLUMN sales.orders.customer_note IS
    'Nội dung do khách nhập; không coi chữ ''confirmed'' là trạng thái hệ thống.';
~~~

PostgreSQL hỗ trợ văn bản Unicode nếu client/server encoding tương thích; có thể ghi comment tiếng Việt:

~~~sql
COMMENT ON TABLE sales.orders IS
    'Thông tin đơn hàng; phục vụ xử lý bán hàng và đối soát.';
~~~

Khi dùng một công cụ migration, nên bảo đảm tệp SQL được lưu với encoding tương thích, thường là UTF-8.

### 3.4. Mô tả dài nhiều dòng

Có thể tạo chuỗi dài hơn, ví dụ dùng **dollar-quoted string** để dễ chứa dấu nháy và xuống dòng:

~~~sql
COMMENT ON TABLE sales.orders IS $doc$
Đơn hàng do hệ thống bán hàng tạo.

Phạm vi:
- Mỗi hàng đại diện cho một đơn.
- Không phải bảng kế toán tổng hợp.
- Việc xóa/ẩn đơn phải tuân thủ chính sách lưu giữ dữ liệu.
$doc$;
~~~

Cú pháp dollar quoting hữu ích khi mô tả có dấu nháy hoặc nhiều đoạn văn. Tuy nhiên, comment quá dài sẽ khó đọc qua `\d+` và khó bảo trì; nên giữ phần mô tả trong database **ngắn, chính xác và hữu dụng**, còn tài liệu quy trình dài đặt ở nguồn tài liệu có quản lý phiên bản phù hợp.

## 4. Thực hành: tạo schema để tài liệu hóa

Phần này dùng **PostgreSQL 12+** trong database thử nghiệm. Các lệnh tạo đối tượng chỉ nên chạy ở môi trường lab có quyền `CREATE`. Nếu bạn đã có schema `comment_lab` từ lần thử trước, hãy đổi tên hoặc sử dụng database khác để tránh xung đột; không xóa dữ liệu thật chỉ để làm lại ví dụ.

### 4.1. Tạo schema

~~~sql
CREATE SCHEMA comment_lab;
~~~

### 4.2. Tạo bảng khách hàng

~~~sql
CREATE TABLE comment_lab.customers (
    customer_id BIGINT GENERATED ALWAYS AS IDENTITY,
    customer_code TEXT NOT NULL,
    customer_name TEXT NOT NULL,
    email TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT pk_customers PRIMARY KEY (customer_id),
    CONSTRAINT uq_customers_code UNIQUE (customer_code)
);
~~~

### 4.3. Tạo bảng đơn hàng

~~~sql
CREATE TABLE comment_lab.orders (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY,
    customer_id BIGINT NOT NULL,
    order_status TEXT NOT NULL DEFAULT 'pending',
    total_amount NUMERIC(14, 2) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT pk_orders PRIMARY KEY (order_id),
    CONSTRAINT fk_orders_customers
        FOREIGN KEY (customer_id)
        REFERENCES comment_lab.customers(customer_id),
    CONSTRAINT chk_orders_amount
        CHECK (total_amount >= 0),
    CONSTRAINT chk_orders_status
        CHECK (order_status IN ('pending', 'paid', 'cancelled'))
);
~~~

### 4.4. Tạo index và view

~~~sql
CREATE INDEX idx_orders_created_at
ON comment_lab.orders (created_at DESC);

CREATE VIEW comment_lab.v_paid_orders AS
SELECT
    o.order_id,
    c.customer_code,
    o.total_amount,
    o.created_at
FROM comment_lab.orders AS o
JOIN comment_lab.customers AS c
    ON c.customer_id = o.customer_id
WHERE o.order_status = 'paid';
~~~

### 4.5. Tạo một function

~~~sql
CREATE FUNCTION comment_lab.line_amount(
    p_quantity INTEGER,
    p_unit_price NUMERIC
)
RETURNS NUMERIC
LANGUAGE SQL
IMMUTABLE
STRICT
AS $$
    SELECT p_quantity * p_unit_price;
$$;
~~~

Function này dùng phép nhân để minh họa chữ ký gồm hai kiểu tham số. Nó **không** thực hiện quy tắc định giá phức tạp, không tự xử lý thuế hay tiền tệ. Tất cả các phần sau đều hoạt động với **metadata**, ngay cả khi bảng chưa có hàng dữ liệu.

## 5. COMMENT ON SCHEMA: mô tả phạm vi nghiệp vụ

~~~sql
COMMENT ON SCHEMA comment_lab IS
    'Schema thực hành tài liệu hóa PostgreSQL; chứa dữ liệu khách hàng và đơn hàng mẫu.';
~~~

Một comment tốt ở cấp schema thường giải thích:

- Schema thuộc lĩnh vực nào.
- Đối tượng trong schema được hệ thống nào quản lý.
- Có chứa dữ liệu nguồn, dữ liệu báo cáo hay dữ liệu trung gian không.
- Những quy ước tổ chức quan trọng.

Không nên ghi mật khẩu, token, chuỗi kết nối hay thông tin bí mật trong comment của schema.

Ví dụ cho một hệ thống thật:

~~~sql
COMMENT ON SCHEMA reporting IS
    'Dữ liệu phục vụ truy vấn báo cáo; không sử dụng làm nguồn sự thật cho giao dịch.';
~~~

Đây là một **quy ước bằng văn bản**, không tự chặn ai đó ghi dữ liệu vào schema. Nếu cần hạn chế thao tác, phải cấp quyền phù hợp bằng `GRANT`/`REVOKE` và quản lý ownership.

## 6. COMMENT ON TABLE: một hàng có ý nghĩa gì?

Comment ở cấp bảng nên bắt đầu từ **đơn vị của một hàng**:

~~~sql
COMMENT ON TABLE comment_lab.customers IS
    'Mỗi hàng đại diện cho một khách hàng trong hệ thống bán hàng mẫu; customer_code là mã nghiệp vụ duy nhất.';

COMMENT ON TABLE comment_lab.orders IS
    'Mỗi hàng đại diện cho một đơn hàng; bản ghi tham chiếu đúng một khách hàng qua customer_id.';
~~~

Cách mô tả “một hàng là gì” giúp tránh những sai lầm phổ biến:

- Coi bảng nhật ký event như bảng trạng thái hiện hành.
- Coi bảng snapshot là bảng dữ liệu có thể cập nhật.
- Nhầm bảng ghi nhận đơn hàng với bảng dòng hàng.
- Nhầm bảng lịch sử với bảng đang hoạt động.

### 6.1. Một mẫu comment hữu ích cho bảng

Khi cần nhiều hơn một câu, có thể ghi:

~~~sql
COMMENT ON TABLE comment_lab.orders IS $doc$
Mục đích: lưu đơn hàng thuộc quy trình bán hàng.
Granularity: một hàng = một đơn hàng.
Nguồn ghi: dịch vụ xử lý đơn.
Quan hệ chính: customer_id tham chiếu customers.
Lưu ý: không sử dụng bảng này như số dư kế toán.
$doc$;
~~~

Các trường như *nguồn ghi* hoặc *thời gian lưu giữ* chỉ nên được ghi nếu có người quản lý chính sách và quy trình đồng bộ khi nghiệp vụ thay đổi.

### 6.2. Comment table khác COMMENT ON COLUMN

Mô tả bảng giải thích **đối tượng tổng thể**. Không nên nhồi vào đó toàn bộ ý nghĩa mọi cột; khi bảng lớn, người sử dụng cần truy cập mô tả từng cột bằng công cụ metadata.

Một lựa chọn tốt là:

- Table comment: mục đích, granularity, ownership nghiệp vụ.
- Column comment: ý nghĩa, kiểu đơn vị và quy ước cụ thể.
- Constraint comment: quy tắc được ràng buộc bảo vệ.
- Index comment: lý do phục vụ truy vấn hoặc uniqueness.
- View/function comment: hợp đồng dữ liệu hoặc chức năng được công bố.

## 7. COMMENT ON COLUMN: trường hợp quan trọng nhất

Cột thường có tên ngắn vì xuất hiện trong SQL nhiều lần. Comment cho phép giữ tên dễ dùng đồng thời làm rõ ý nghĩa.

~~~sql
COMMENT ON COLUMN comment_lab.customers.customer_id IS
    'Khóa chính kỹ thuật do PostgreSQL cấp bằng identity.';

COMMENT ON COLUMN comment_lab.customers.customer_code IS
    'Mã khách hàng dùng trong nghiệp vụ; không chuyển thành số vì có thể có số 0 ở đầu.';

COMMENT ON COLUMN comment_lab.customers.customer_name IS
    'Tên hiển thị của khách hàng.';

COMMENT ON COLUMN comment_lab.customers.email IS
    'Email liên hệ tùy chọn; NULL nghĩa là chưa có email được lưu.';

COMMENT ON COLUMN comment_lab.customers.created_at IS
    'Thời điểm bản ghi khách hàng được tạo; dùng timestamptz.';
~~~

Với bảng đơn hàng:

~~~sql
COMMENT ON COLUMN comment_lab.orders.order_id IS
    'Khóa định danh kỹ thuật của đơn hàng.';

COMMENT ON COLUMN comment_lab.orders.customer_id IS
    'Khách hàng sở hữu đơn; tham chiếu comment_lab.customers(customer_id).';

COMMENT ON COLUMN comment_lab.orders.order_status IS
    'Trạng thái đơn: pending, paid hoặc cancelled; danh sách được kiểm tra bằng chk_orders_status.';

COMMENT ON COLUMN comment_lab.orders.total_amount IS
    'Tổng tiền của đơn theo đơn vị tiền tệ của hệ thống mẫu; NUMERIC(14,2), không âm.';

COMMENT ON COLUMN comment_lab.orders.created_at IS
    'Thời điểm tạo đơn theo kiểu timestamptz; không phải thời điểm thanh toán.';
~~~

### 7.1. Cột tiền: không chỉ ghi “số tiền”

Comment về số tiền nên nói rõ:

- Giá trị trước hay sau thuế?
- Trước hay sau giảm giá?
- Có gồm phí vận chuyển không?
- Tiền tệ lấy từ đâu?
- Số thập phân được làm tròn theo quy tắc nào?
- Có thể âm hay không?

Nếu mô hình chỉ có một cột `total_amount` mà chưa xác định các quy tắc đó, đừng đặt comment khẳng định chúng. Metadata sai làm giảm niềm tin hơn là thiếu metadata.

### 7.2. Cột thời gian: biết rõ mốc và múi giờ

Ví dụ:

~~~sql
COMMENT ON COLUMN comment_lab.orders.created_at IS
    'Thời điểm bản ghi đơn được tạo; TIMESTAMPTZ. Không dùng làm thời gian giao hàng.';
~~~

`TIMESTAMPTZ` trong PostgreSQL lưu thời điểm có ngữ nghĩa tuyệt đối và hiển thị theo timezone của session. Nó **không lưu nguyên tên múi giờ do client gửi** như một trường riêng.

Nếu nghiệp vụ cần “ngày giao dịch theo múi giờ Việt Nam”, tài liệu cần giải thích quy tắc chuyển ngày; có thể cần thêm cột nghiệp vụ hoặc phép tính được quy định rõ, không chỉ dựa vào tên `created_at`.

### 7.3. Cột trạng thái: mô tả vòng đời

Một cột `status` thường cần hơn danh sách giá trị:

~~~text
pending   -> đang chờ xử lý
paid      -> thanh toán đã được xác nhận
cancelled -> đơn đã hủy
~~~

Comment có thể liên kết tới quy trình nghiệp vụ, nhưng **không tự thực thi chuyển trạng thái hợp lệ**. `CHECK` chỉ kiểm tra tập giá trị được phép; nếu cần ngăn chuyển từ `cancelled` về `paid`, ứng dụng hoặc cơ chế database bổ sung phải xử lý quy tắc đó.

### 7.4. Cột có NULL: giải thích “thiếu” nghĩa là gì

Hai trường hợp sau không tương đương:

- `email IS NULL`: chưa thu thập email.
- `email = ''`: đã lưu chuỗi rỗng.

Một comment có thể giúp người viết báo cáo phân biệt hai trạng thái, nhưng chỉ khi ứng dụng thực sự dùng chúng nhất quán.

Nếu dữ liệu nguồn dùng `NULL` với nhiều ý nghĩa lẫn lộn, cần sửa mô hình/luồng ghi thay vì chỉ ghi một comment đẹp.

## 8. COMMENT ON CONSTRAINT: giải thích luật toàn vẹn

Ràng buộc có tên thường giống ngôn ngữ kỹ thuật:

~~~text
fk_orders_customers
chk_orders_amount
chk_orders_status
uq_customers_code
~~~

Comment giải thích **vì sao** chúng cần thiết.

~~~sql
COMMENT ON CONSTRAINT fk_orders_customers
ON comment_lab.orders IS
    'Mỗi đơn hàng phải thuộc về một khách hàng tồn tại.';

COMMENT ON CONSTRAINT chk_orders_amount
ON comment_lab.orders IS
    'Tổng tiền đơn thông thường không được âm; các khoản hoàn tiền cần mô hình riêng.';

COMMENT ON CONSTRAINT chk_orders_status
ON comment_lab.orders IS
    'Giới hạn trạng thái đơn trong tập giá trị được quy trình xử lý hỗ trợ.';

COMMENT ON CONSTRAINT uq_customers_code
ON comment_lab.customers IS
    'Mã khách hàng phải duy nhất để hỗ trợ đối soát với hệ thống bên ngoài.';
~~~

Cú pháp lưu ý:

~~~sql
COMMENT ON CONSTRAINT ten_constraint
ON schema.ten_bang IS '...';
~~~

**Tên bảng là cần thiết**, vì PostgreSQL phải xác định constraint thuộc bảng nào.

### 8.1. Constraint mới có tác động tới dữ liệu; comment không có

Hai thao tác khác nhau:

~~~sql
-- Thay đổi quy tắc kiểm tra dữ liệu.
ALTER TABLE comment_lab.orders
ADD CONSTRAINT chk_orders_example
CHECK (total_amount <= 999999999999.99);

-- Chỉ thay đổi mô tả của quy tắc đã tồn tại.
COMMENT ON CONSTRAINT chk_orders_amount
ON comment_lab.orders IS
    'Tổng tiền không được nhỏ hơn 0.';
~~~

Ví dụ `ALTER TABLE` chỉ minh họa sự khác nhau, không cần chạy trong bài thực hành. Việc bổ sung constraint trên bảng thật có thể yêu cầu quét dữ liệu hoặc ảnh hưởng khóa, nên phải có migration phù hợp.

### 8.2. Đặt comment cho primary key có hữu ích?

Primary key có thể hiển nhiên ở những bảng đơn giản. Nhưng khi một bảng dùng composite primary key hoặc có khóa nghiệp vụ đặc biệt, comment giải thích cách định danh hàng rất hữu ích.

~~~sql
COMMENT ON CONSTRAINT pk_orders
ON comment_lab.orders IS
    'Khóa chính kỹ thuật; không dùng như số đơn hàng hiển thị cho khách.';
~~~

Không cần lặp một định nghĩa hiển nhiên trong mọi comment. Ưu tiên giải thích **quyết định thiết kế và điểm dễ hiểu sai**.

## 9. COMMENT ON INDEX: vì sao chỉ mục tồn tại?

Index thường được tạo để tăng tốc truy vấn hoặc hỗ trợ ràng buộc. Sau một thời gian, người vận hành có thể thấy nhiều index gần giống nhau nhưng không biết index nào còn cần.

~~~sql
COMMENT ON INDEX comment_lab.idx_orders_created_at IS
    'Phục vụ truy vấn danh sách đơn theo thời điểm tạo mới nhất; dùng cho màn hình tra cứu lịch sử.';
~~~

Một index comment hữu ích có thể ghi:

- Mẫu lọc/sắp xếp chính mà index phục vụ.
- API/report quan trọng đang sử dụng.
- Tại sao thứ tự cột của composite index được chọn.
- Có yêu cầu uniqueness hoặc constraint phụ thuộc không.
- Khi nào cần đánh giá lại index.

Ví dụ index ghép giả định:

~~~sql
-- Chỉ thực hiện nếu workload cần, trong môi trường thử nghiệm.
CREATE INDEX idx_orders_customer_created
ON comment_lab.orders (customer_id, created_at DESC);

COMMENT ON INDEX comment_lab.idx_orders_customer_created IS
    'Phục vụ tìm các đơn mới nhất của một khách hàng: customer_id = ? ORDER BY created_at DESC.';
~~~

### 9.1. Comment không bảo đảm optimizer dùng index

Một index được ghi “phục vụ truy vấn lịch sử” không có nghĩa PostgreSQL bắt buộc dùng nó. Planner có thể chọn sequential scan nếu bảng nhỏ hoặc chi phí dự kiến thấp hơn.

Nếu muốn biết index có còn hữu ích, cần kết hợp `EXPLAIN`, thống kê truy cập, chi phí ghi và workload thực tế. **Comment nêu chủ đích thiết kế, không phải chứng nhận hiệu năng.**

### 9.2. Comment trên index của khóa chính

PostgreSQL thường tạo index cho primary key và unique constraint. Khi muốn tài liệu hóa **quy tắc toàn vẹn**, nên comment chính constraint. Chỉ comment trên index nếu cần giải thích đặc điểm index cụ thể.

Việc xóa một index dùng để thực thi constraint có thể bị ràng buộc bởi quan hệ phụ thuộc. Một mô tả tốt giúp người bảo trì không nhầm index độc lập với index thuộc constraint.

## 10. COMMENT ON VIEW và MATERIALIZED VIEW

### 10.1. View là giao diện truy vấn

~~~sql
COMMENT ON VIEW comment_lab.v_paid_orders IS
    'Danh sách các đơn có trạng thái paid; chỉ công bố mã khách, tổng tiền và thời điểm tạo đơn.';
~~~

View thường được dùng để tạo giao diện dữ liệu cho reporting hoặc tầng ứng dụng. Comment nên làm rõ:

- Tiêu chí chọn hàng.
- Ý nghĩa và độ chi tiết của kết quả.
- Những điều kiện lọc ngầm trong view.
- Nguồn bảng liên quan.
- Phạm vi được phép sử dụng theo nghiệp vụ.

Không nên ghi “view an toàn cho mọi tài khoản” chỉ vì nó chỉ chọn một số cột. **Phân quyền** còn phụ thuộc quyền truy cập view/bảng, chủ sở hữu và cấu hình security liên quan.

### 10.2. Materialized view có dữ liệu được lưu

Ví dụ tạo materialized view:

~~~sql
CREATE MATERIALIZED VIEW comment_lab.mv_daily_order_total AS
SELECT
    created_at::date AS order_date,
    COUNT(*) AS order_count,
    SUM(total_amount) AS total_amount
FROM comment_lab.orders
GROUP BY created_at::date;
~~~

Gắn mô tả:

~~~sql
COMMENT ON MATERIALIZED VIEW comment_lab.mv_daily_order_total IS
    'Tổng hợp đơn theo ngày dựa trên created_at; kết quả được lưu tại lần refresh gần nhất.';
~~~

Khác với view thường, materialized view có dữ liệu được lưu và cần được làm mới theo cơ chế thích hợp:

~~~sql
REFRESH MATERIALIZED VIEW comment_lab.mv_daily_order_total;
~~~

Trong hệ thống thật, comment còn nên chỉ rõ **job nào refresh, tần suất và độ trễ dữ liệu cho phép** nếu thông tin này được quản lý rõ ràng.

### 10.3. Đừng mô tả materialized view là dữ liệu thời gian thực

Nếu materialized view chỉ refresh hằng ngày, comment phải tránh khẳng định dữ liệu “luôn mới nhất”. Một người dùng BI có thể đưa ra quyết định sai nếu không biết dữ liệu có độ trễ.

## 11. COMMENT ON FUNCTION và PROCEDURE

Các function/procedure không chỉ có tên, mà còn có **chữ ký tham số**. PostgreSQL hỗ trợ nhiều function cùng tên nhưng khác kiểu đối số (*function overloading*).

Đã tạo:

~~~sql
CREATE FUNCTION comment_lab.line_amount(
    p_quantity INTEGER,
    p_unit_price NUMERIC
)
RETURNS NUMERIC
LANGUAGE SQL
IMMUTABLE
STRICT
AS $$
    SELECT p_quantity * p_unit_price;
$$;
~~~

Gắn comment:

~~~sql
COMMENT ON FUNCTION comment_lab.line_amount(INTEGER, NUMERIC) IS
    'Nhân số lượng với đơn giá; đầu vào không chứa thuế hoặc giảm giá; NULL trả NULL do STRICT.';
~~~

Điểm cần nhớ:

- Tên function phải chỉ đúng schema khi có thể.
- Phần trong ngoặc là **kiểu các tham số định danh function**.
- Không tùy ý bỏ chữ ký nếu có overload.
- Comment nên nêu **hợp đồng đầu vào/đầu ra** và những giới hạn, không chỉ lặp “function tính số tiền”.

### 11.1. Khi có nhiều overload

Giả sử có:

~~~text
comment_lab.calculate_fee(integer)
comment_lab.calculate_fee(numeric)
~~~

Hai function khác nhau. Cần dùng chữ ký đúng để gắn comment chính xác:

~~~sql
COMMENT ON FUNCTION comment_lab.calculate_fee(INTEGER)
IS 'Tính phí từ một giá trị nguyên.';

COMMENT ON FUNCTION comment_lab.calculate_fee(NUMERIC)
IS 'Tính phí từ một giá trị thập phân.';
~~~

Hai lệnh là **ví dụ cú pháp**, chỉ chạy nếu các function đó thật sự tồn tại. Nếu không có overload tương ứng, PostgreSQL sẽ báo không tìm thấy đối tượng.

### 11.2. Comment cho stored procedure

Ví dụ cú pháp cho một procedure đã tồn tại:

~~~sql
COMMENT ON PROCEDURE comment_lab.close_order(BIGINT) IS
    'Xác nhận hoàn tất đơn hàng theo ID; cần gọi trong luồng có kiểm tra quyền nghiệp vụ.';
~~~

Ví dụ giả định procedure `close_order(BIGINT)` đã được tạo. Không phải câu SQL có thể chạy độc lập trong bài lab hiện tại.

Với procedure có tác dụng ghi, comment nên mô tả:

- Tham số và tiền điều kiện.
- Bảng hoặc loại dữ liệu bị tác động.
- Lỗi nghiệp vụ có thể xảy ra.
- Yêu cầu idempotency nếu liên quan.
- Quyền được phép gọi hoặc nơi thực hiện kiểm tra quyền.

Những thông tin này giúp người sử dụng, nhưng **không thay thế phân quyền SQL và kiểm tra nghiệp vụ**.

## 12. Các loại comment khác: trigger, policy, type, domain

### 12.1. Trigger

Với một trigger có tên `trg_orders_audit` gắn vào bảng `comment_lab.orders`, cú pháp:

~~~sql
COMMENT ON TRIGGER trg_orders_audit
ON comment_lab.orders IS
    'Ghi nhận thay đổi đơn hàng vào bảng audit sau thao tác cập nhật.';
~~~

Đây chỉ là ví dụ nếu trigger đã tồn tại. Trigger có thể gây các tác động phụ quan trọng, nên comment tốt cần nêu **thời điểm, sự kiện và mục đích**.

### 12.2. Row-level security policy

Nếu một bảng có policy `orders_tenant_policy`, có thể tài liệu hóa:

~~~sql
COMMENT ON POLICY orders_tenant_policy
ON comment_lab.orders IS
    'Giới hạn phạm vi hàng theo chính sách phân tách tenant của ứng dụng.';
~~~

Không có policy đó trong schema lab ban đầu; ví dụ minh họa cú pháp. **Comment không làm policy có hiệu lực**. Muốn RLS hoạt động phải có các câu lệnh tạo/bật policy và cấu hình quyền phù hợp.

Đặc biệt, comment “chỉ tenant hiện tại đọc được” không chứng minh rằng hệ thống thực sự chống rò rỉ tenant. Cần kiểm thử bằng những tài khoản và ngữ cảnh truy cập có quyền khác nhau.

### 12.3. Domain

Domain có thể gói một kiểu dữ liệu cùng ràng buộc thường dùng:

~~~sql
CREATE DOMAIN comment_lab.nonnegative_amount
AS NUMERIC(14, 2)
CHECK (VALUE >= 0);

COMMENT ON DOMAIN comment_lab.nonnegative_amount IS
    'Số thập phân không âm dùng cho giá trị tiền trong schema thực hành.';
~~~

Nếu nhiều bảng dùng domain này, comment giúp giải thích ý nghĩa thống nhất của kiểu dữ liệu. Tuy nhiên, domain cũng không tự quyết định loại tiền tệ hoặc các quy tắc tính thuế.

### 12.4. Enum type

~~~sql
CREATE TYPE comment_lab.order_priority AS ENUM (
    'low',
    'normal',
    'high'
);

COMMENT ON TYPE comment_lab.order_priority IS
    'Mức ưu tiên xử lý đơn: low, normal hoặc high.';
~~~

Nếu tập giá trị enum thay đổi, comment cũng phải được cập nhật trong cùng quy trình migration.

## 13. Ai được phép tạo hoặc sửa comment?

COMMENT là thao tác trên metadata đối tượng, nên không phải người dùng chỉ có quyền `SELECT` dữ liệu là tự nhiên được sửa comment.

Theo quy tắc PostgreSQL, **người sở hữu đối tượng** thường là người được phép thay đổi comment, cùng các trường hợp được ủy quyền/quyền đặc biệt phù hợp. Đối với một số loại đối tượng hệ thống hoặc đối tượng dùng chung, có các điều kiện đặc quyền riêng theo phiên bản.

Ví dụ:

~~~sql
SELECT
    current_user,
    session_user,
    current_database();
~~~

Trong psql, có thể kiểm tra quyền và ownership:

~~~text
\dn+
\dt+ comment_lab.*
\du
~~~

Nếu tài khoản chỉ có:

~~~sql
GRANT SELECT ON comment_lab.orders TO report_reader;
~~~

thì quyền `SELECT` đó không đồng nghĩa được sửa comment của bảng.

### 13.1. Tài khoản migration thường sở hữu schema

Trong nhiều dự án, tài khoản chạy migration tạo và sở hữu bảng, index, view hoặc function. Khi đó, đặt COMMENT ngay cùng migration giúp giữ metadata đồng bộ với DDL.

Nếu có nhiều người dùng cùng tạo đối tượng bằng tài khoản khác nhau, quyền sửa comment có thể trở nên không nhất quán. Điều này là lý do nên quản lý ownership và role được phép DDL theo quy trình rõ ràng.

### 13.2. COMMENT không cấp quyền đọc dữ liệu

~~~sql
COMMENT ON TABLE comment_lab.orders IS
    'Dữ liệu đơn hàng dành cho nội bộ.';
~~~

Câu lệnh trên **không chặn** người đã có `SELECT` xem dữ liệu. Nếu cần hạn chế, phải dùng cơ chế quyền:

~~~sql
REVOKE SELECT ON comment_lab.orders FROM report_reader;
~~~

Đây là ví dụ phân biệt, không nên chạy tùy tiện trong lab có tài khoản khác hoặc production. Comment có thể mô tả phân loại dữ liệu, nhưng **quyền thực tế** phải được cấu hình, đo kiểm và giám sát riêng.

## 14. Xem comment bằng psql: \d+, \dd và \df+

Cách nhanh nhất để khám phá mô tả ngay trong terminal là dùng chương trình **psql**.

### 14.1. \d+ cho bảng và cột

~~~text
\d+ comment_lab.orders
~~~

Lệnh mô tả bảng với các cột, kiểu dữ liệu, default, constraints/indexes và những chi tiết bổ sung. Tùy phiên bản psql, comment trên cột có thể xuất hiện trong phần **Description** và comment bảng cũng có thể được hiển thị trong metadata mở rộng.

Thử:

~~~text
\d+ comment_lab.customers
\d+ comment_lab.v_paid_orders
\d+ comment_lab.mv_daily_order_total
~~~

Cần phân biệt:

- `\d</BT>: mô tả đối tượng ở mức cơ bản.
- `\d+`: yêu cầu mô tả chi tiết hơn, thường gồm comment khi phù hợp.
- `\dd`: liệt kê description của những đối tượng phù hợp.

Các meta-command này do **psql xử lý phía client**, không phải SQL gửi nguyên văn tới server. Đừng gửi `\d+</BT> qua JDBC và kỳ vọng PostgreSQL hiểu.

### 14.2. \dd liệt kê đối tượng có description

~~~text
\dd comment_lab.*
~~~

Lệnh có thể giúp kiểm kê những comment mà psql hiển thị được theo pattern và loại đối tượng. Nội dung và phạm vi phụ thuộc phiên bản psql cùng quyền.

Một số mô tả ở mức column hoặc object cụ thể có thể cần `\d+` hoặc truy vấn `pg_catalog` để xem đầy đủ. Không coi một kết quả `\dd` rỗng là bằng chứng mọi cột đều chưa có comment.

### 14.3. \df+ với function

~~~text
\df+ comment_lab.line_amount
~~~

psql có thể hiển thị mô tả, chữ ký, tính chất và chi tiết khác của function tùy phiên bản. Với function overloaded, cần nhìn đúng kiểu tham số.

### 14.4. \l+ và \dn+ cho database/schema

~~~text
\l+
\dn+
~~~

Các lệnh này giúp xem thông tin nâng cao của database/schema, có thể bao gồm phần mô tả khi phù hợp. Đây là công cụ nhanh để kiểm tra chú thích cấp cao trước khi đi vào từng bảng.

## 15. Comment được lưu ở đâu trong PostgreSQL?

Ở mức catalog, PostgreSQL có **`pg_catalog.pg_description`** để lưu mô tả cho nhiều đối tượng thuộc database và **`pg_catalog.pg_shdescription`** cho một số đối tượng dùng chung ở cấp cluster.

Không cần thao tác trực tiếp với các bảng catalog này để tạo comment. **Hãy dùng `COMMENT ON`**, thay vì cố `INSERT/UPDATE pg_description`.

### 15.1. pg_description có những trường nào?

Các trường quan trọng:

| Trường | Ý nghĩa |
|---|---|
| `objoid` | OID của đối tượng được mô tả |
| `classoid` | OID của catalog quản lý loại đối tượng đó |
| `objsubid` | ID thành phần con; thường bằng 0 với toàn đối tượng, dùng số thuộc tính với cột |
| `description` | Văn bản comment |

Tại sao cần cả `objoid` và `classoid`? Vì cùng một OID dạng số có thể thuộc các namespace catalog khác nhau; để xác định đúng đối tượng cần biết catalog tương ứng.

### 15.2. Comment bảng và comment cột dùng khác objsubid

Ở cấp quan hệ (relation):

- Comment trên bảng dùng OID của relation, `objsubid = 0`.
- Comment trên cột liên kết tới OID của relation và **attribute number** của cột.

Vì vậy, không nên tự lấy một dòng trong `pg_description` rồi kết luận nó mô tả cả bảng nếu chưa xem `objsubid`.

### 15.3. Không tự sửa system catalogs

Cách đúng:

~~~sql
COMMENT ON TABLE comment_lab.orders IS
    'Mỗi hàng là một đơn hàng.';
~~~

Cách không nên làm:

~~~sql
-- Không thực hiện:
-- UPDATE pg_catalog.pg_description
-- SET description = '...'
-- WHERE ...;
~~~

Catalog là cấu trúc nội bộ được PostgreSQL quản lý. Thao tác trực tiếp trái phép có thể làm hỏng metadata hoặc bị hệ thống từ chối. DDL chính thức tồn tại để đảm bảo PostgreSQL cập nhật metadata nhất quán.

## 16. Đọc comment table bằng obj_description()

Hàm `obj_description()` cho phép lấy comment của đối tượng thông qua OID và catalog thích hợp.

Ví dụ bảng:

~~~sql
SELECT obj_description(
    'comment_lab.orders'::regclass,
    'pg_class'
) AS orders_description;
~~~

`'comment_lab.orders'::regclass` phân giải tên relation sang OID theo cú pháp PostgreSQL. `pg_class` là catalog quản lý relation như bảng, index, view, sequence.

Nếu bảng tồn tại và có comment, hàm trả văn bản đã lưu. Nếu không có comment phù hợp, thường nhận `NULL`.

### 16.1. Liệt kê comment của các relation trong schema

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS object_name,
    c.relkind AS object_kind,
    obj_description(c.oid, 'pg_class') AS description
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE n.nspname = 'comment_lab'
  AND c.relkind IN ('r', 'p', 'v', 'm', 'i', 'I', 'S')
ORDER BY c.relkind, c.relname;
~~~

Một số ký hiệu `relkind` thường gặp:

| relkind | Loại relation |
|---|---|
| `r` | Ordinary table |
| `p` | Partitioned table |
| `v` | View |
| `m` | Materialized view |
| `i` | Index |
| `I` | Partitioned index |
| `S` | Sequence |

Danh sách trên dùng các loại quan trọng đối với bài học; PostgreSQL còn có những loại relation khác. Chỉ lọc schema mục tiêu giúp báo cáo ngắn và hạn chế đọc những metadata không liên quan.

### 16.2. Đọc comment schema

Schema nằm trong `pg_namespace`, không phải `pg_class`:

~~~sql
SELECT
    n.nspname,
    obj_description(n.oid, 'pg_namespace') AS schema_description
FROM pg_catalog.pg_namespace AS n
WHERE n.nspname = 'comment_lab';
~~~

**Tham số catalog phải khớp loại đối tượng.** Không dùng `pg_class` cho mọi thứ; role, function, constraint và schema thuộc những catalog khác.

## 17. Đọc comment cột bằng col_description()

Với cột của một relation, dùng `col_description(relation_oid, attribute_number)`.

Ví dụ đọc các cột của `orders`:

~~~sql
SELECT
    a.attnum AS ordinal_position,
    a.attname AS column_name,
    pg_catalog.format_type(a.atttypid, a.atttypmod) AS column_type,
    pg_catalog.col_description(c.oid, a.attnum) AS description
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = c.relnamespace
JOIN pg_catalog.pg_attribute AS a
    ON a.attrelid = c.oid
WHERE n.nspname = 'comment_lab'
  AND c.relname = 'orders'
  AND a.attnum > 0
  AND NOT a.attisdropped
ORDER BY a.attnum;
~~~

Giải thích các phần:

- `pg_class` định danh relation.
- `pg_namespace` giúp giới hạn đúng schema.
- `pg_attribute` mô tả các thuộc tính/cột.
- `a.attnum > 0` bỏ các thuộc tính hệ thống ở phần truy vấn này.
- `NOT a.attisdropped` bỏ những cột đã bị đánh dấu xóa ở mức catalog.
- `col_description(c.oid, a.attnum)` trả mô tả tương ứng.

### 17.1. Vì sao cần attnum thay vì thứ tự hiển thị?

`attnum` là số thuộc tính được PostgreSQL quản lý. Sau khi thêm/xóa cột, các số có thể không còn liên tiếp. Không nên tự dùng một bộ đếm từ 1 đến số cột đang nhìn thấy để suy ra đúng `attnum`.

Hãy lấy `a.attnum` từ catalog thay vì đoán.

### 17.2. Tổng hợp comment toàn bộ cột trong một schema

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    a.attname AS column_name,
    pg_catalog.format_type(a.atttypid, a.atttypmod) AS data_type,
    pg_catalog.col_description(c.oid, a.attnum) AS description
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = c.relnamespace
JOIN pg_catalog.pg_attribute AS a
    ON a.attrelid = c.oid
WHERE n.nspname = 'comment_lab'
  AND c.relkind IN ('r', 'p')
  AND a.attnum > 0
  AND NOT a.attisdropped
ORDER BY c.relname, a.attnum;
~~~

Câu SQL này hữu ích để xuất dữ liệu tài liệu hóa sang báo cáo nội bộ hoặc kiểm tra chất lượng metadata. Khi dùng trên database lớn, nên lọc schema và giới hạn phạm vi cần thiết.

## 18. Đọc comment constraint qua pg_constraint

Ràng buộc được mô tả trong `pg_catalog.pg_constraint`.

~~~sql
SELECT
    n.nspname AS schema_name,
    t.relname AS table_name,
    con.conname AS constraint_name,
    con.contype AS constraint_kind,
    pg_catalog.pg_get_constraintdef(con.oid) AS constraint_definition,
    obj_description(con.oid, 'pg_constraint') AS description
FROM pg_catalog.pg_constraint AS con
JOIN pg_catalog.pg_class AS t
    ON t.oid = con.conrelid
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = t.relnamespace
WHERE n.nspname = 'comment_lab'
ORDER BY t.relname, con.conname;
~~~

Trong `pg_constraint.contype`, các ký hiệu thường gặp gồm:

| contype | Ý nghĩa |
|---|---|
| `p` | Primary key |
| `u` | Unique |
| `f` | Foreign key |
| `c` | Check |
| `x` | Exclusion constraint |

Các constraint khác như constraint của domain có thể không được biểu diễn bằng cách nối `conrelid` tới bảng như ví dụ trên. Câu truy vấn tập trung vào **ràng buộc gắn với bảng**.

### 18.1. Vì sao comment constraint quan trọng khi migration?

Giả sử migration thay `CHECK (amount >= 0)` thành luật phức tạp hơn. Nếu chỉ đổi constraint mà giữ comment cũ, tài liệu hóa sẽ không còn đúng.

Trong một migration tốt, thay đổi logic và cập nhật comment được xét **cùng nhau**. Thông tin “vì sao có luật này” giúp người sửa sau không vô tình nới lỏng invariant mà ứng dụng đang dựa vào.

## 19. Đọc comment function từ pg_proc

Các function/procedure được PostgreSQL lưu trong catalog `pg_proc`. Vì function có thể overloaded, nên báo cáo cần nhận diện chữ ký đầy đủ.

~~~sql
SELECT
    n.nspname AS schema_name,
    p.proname AS routine_name,
    pg_catalog.pg_get_function_identity_arguments(p.oid) AS identity_args,
    obj_description(p.oid, 'pg_proc') AS description
FROM pg_catalog.pg_proc AS p
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = p.pronamespace
WHERE n.nspname = 'comment_lab'
ORDER BY p.proname, identity_args;
~~~

`pg_get_function_identity_arguments()` hỗ trợ biểu diễn những tham số cần thiết để định danh routine. Đây là cách thuận tiện hơn việc chỉ ghi tên `proname` rồi có nguy cơ gộp các overload khác nhau.

### 19.1. Đọc một function cụ thể qua regprocedure

~~~sql
SELECT obj_description(
    'comment_lab.line_amount(integer, numeric)'::regprocedure,
    'pg_proc'
) AS function_description;
~~~

`regprocedure` phân giải theo **chữ ký**. Nếu không có đối tượng tương ứng, PostgreSQL sẽ báo lỗi thay vì tự chọn một function gần giống.

### 19.2. Function comment không phải API contract được engine kiểm tra

Nếu comment ghi “trả về số tiền đã làm tròn 2 chữ số” nhưng thân function không dùng `ROUND(...,2)`, PostgreSQL vẫn thực thi thân function theo định nghĩa của nó. Comment không tự khớp với code.

Để giữ độ tin cậy cần kiểm thử hành vi, migration và rà soát metadata khi thay đổi chức năng.

## 20. Comment trên đối tượng dùng chung: pg_shdescription

Không phải mọi đối tượng PostgreSQL đều thuộc một database riêng. Một số đối tượng như **database**, **role** hoặc **tablespace** có phạm vi chung ở cấp cluster.

Thông tin mô tả của những đối tượng dùng chung có thể nằm ở **`pg_shdescription`** thay vì `pg_description`.

Ví dụ khi tài khoản có quyền phù hợp và database `training_db` tồn tại:

~~~sql
COMMENT ON DATABASE training_db IS
    'Database đào tạo PostgreSQL; không chứa dữ liệu khách hàng thật.';
~~~

Đọc qua hàm:

~~~sql
SELECT
    d.datname,
    pg_catalog.shobj_description(d.oid, 'pg_database') AS description
FROM pg_catalog.pg_database AS d
WHERE d.datname = 'training_db';
~~~

**Chỉ chạy câu COMMENT khi database đó thật sự tồn tại và bạn có quyền thích hợp.** Nếu tên database của môi trường khác, phải thay tên tương ứng.

### 20.1. Vì sao không dùng obj_description cho mọi object?

`obj_description()` và `pg_description` phục vụ mô tả đối tượng trong những catalog phù hợp. Với object dùng chung, `shobj_description()` và `pg_shdescription` là cơ chế tương ứng.

Đây là lý do báo cáo tài liệu hóa “mọi object trên server” cần phân loại **đối tượng thuộc database** và **đối tượng shared ở cấp cluster**, không chỉ truy vấn một bảng catalog duy nhất.

## 21. Phát hiện bảng và cột chưa có comment

Một lợi ích của lưu comment trong metadata là có thể tạo báo cáo về mức độ tài liệu hóa.

### 21.1. Tìm bảng chưa có comment

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE n.nspname = 'comment_lab'
  AND c.relkind IN ('r', 'p')
  AND obj_description(c.oid, 'pg_class') IS NULL
ORDER BY c.relname;
~~~

Câu SQL chỉ phát hiện comment **NULL**. Nếu tổ chức cũng coi chuỗi rỗng hoặc toàn khoảng trắng là thiếu, có thể dùng thêm:

~~~sql
AND NULLIF(
    btrim(obj_description(c.oid, 'pg_class')),
    ''
) IS NULL
~~~

Cần hiểu tiêu chí báo cáo: không phải mọi bảng kỹ thuật, bảng staging hoặc temporary object đều cần lượng mô tả giống nhau.

### 21.2. Tìm cột chưa có comment

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    a.attname AS column_name,
    pg_catalog.format_type(a.atttypid, a.atttypmod) AS data_type
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = c.relnamespace
JOIN pg_catalog.pg_attribute AS a
    ON a.attrelid = c.oid
WHERE n.nspname = 'comment_lab'
  AND c.relkind IN ('r', 'p')
  AND a.attnum > 0
  AND NOT a.attisdropped
  AND NULLIF(
      btrim(pg_catalog.col_description(c.oid, a.attnum)),
      ''
  ) IS NULL
ORDER BY c.relname, a.attnum;
~~~

Đây là một **báo cáo kiểm kê**, không phải lệnh tự động tạo comment. Nếu tự thêm các mô tả như “Cột customer_id” cho mọi cột chỉ để đạt 100% coverage, tài liệu sẽ có vẻ đầy đủ nhưng giá trị sử dụng rất thấp.

### 21.3. Độ phủ và chất lượng là hai chuyện khác nhau

Ví dụ:

~~~sql
COMMENT ON COLUMN comment_lab.orders.total_amount IS
    'Số tiền.';
~~~

Comment tồn tại nhưng gần như không giải đáp các vấn đề thực tế: thuế, phí, đơn vị, thời điểm và quy tắc làm tròn.

Một chỉ số “95% cột có comment” hữu ích cho việc theo dõi **độ phủ**, nhưng không chứng minh tài liệu đúng và dễ sử dụng. Cần bảo trì chất lượng nội dung như các phần khác của mô hình dữ liệu.

## 22. Tài liệu hóa bằng migration và quản lý phiên bản

Một comment được gõ thủ công trên production dễ bị mất khi tạo lại schema, hoặc không đồng bộ giữa development, staging và production.

Phương án bền vững hơn là đưa câu `COMMENT ON` vào **migration có quản lý phiên bản** cùng DDL liên quan.

Ví dụ một migration:

~~~sql
BEGIN;

ALTER TABLE comment_lab.orders
ADD COLUMN payment_reference TEXT;

COMMENT ON COLUMN comment_lab.orders.payment_reference IS
    'Mã tham chiếu thanh toán do hệ thống thanh toán cung cấp; có thể NULL trước khi có giao dịch.';

COMMENT ON TABLE comment_lab.orders IS
    'Mỗi hàng đại diện cho một đơn; có thể liên kết giao dịch qua payment_reference.';

COMMIT;
~~~

Trong PostgreSQL, nhiều thao tác DDL và COMMENT có thể tham gia transaction, giúp thay đổi schema và metadata cùng được xác nhận hoặc hoàn tác theo quy tắc của PostgreSQL.

Cần lưu ý:

- Không phải **mọi** lệnh DDL đều chạy được trong transaction block.
- Thêm cột hoặc thay constraint có thể phát sinh lock và ảnh hưởng runtime.
- Chạy migration cần quyền và kế hoạch rollback phù hợp.
- Nếu cột mới có ngữ nghĩa khác khi dữ liệu cũ được backfill, comment cũng cần phản ánh giai đoạn chuyển đổi.

### 22.1. Đổi tên cột và comment

Khi đổi tên một cột bằng `ALTER TABLE ... RENAME COLUMN`, metadata của đối tượng thường được duy trì theo cách PostgreSQL quản lý định danh của nó. Tuy nhiên, **nội dung văn bản** có thể vẫn nhắc tên cũ hoặc ý nghĩa cũ.

Ví dụ, comment ghi “tham chiếu mã khách hàng theo customer_code” nhưng dự án đổi thiết kế sang một khóa mới. Metadata tự tồn tại không có nghĩa nó đã được sửa ngữ nghĩa.

Do đó, mỗi migration quan trọng cần xem cả **cấu trúc**, **query phụ thuộc** và **comment liên quan**.

### 22.2. Đối tượng bị DROP

Khi một đối tượng bị xóa thực sự, comment gắn với nó cũng không còn là metadata hiện hành của đối tượng đó. Nếu migration drop rồi recreate, cần bảo đảm lệnh `COMMENT ON` được thực hiện lại theo định nghĩa mới.

### 22.3. Tái chạy migration

`COMMENT ON</BT> trên một đối tượng đã tồn tại thường có tính chất **thay thế mô tả**, nên việc đặt cùng nội dung có thể cho kết quả mô tả giống nhau. Nhưng lệnh vẫn yêu cầu đối tượng tồn tại và người thực thi có quyền.

Một migration không nên được xem là idempotent hoàn toàn chỉ vì các câu COMMENT có thể lặp lại; những câu `CREATE TABLE`, `ALTER TABLE` và thay đổi dữ liệu cùng migration vẫn cần quản lý riêng.

## 23. Export schema với pg_dump

Trong quá trình sao lưu logic hoặc triển khai schema, công cụ **`pg_dump`** có thể xuất cả định nghĩa đối tượng và các comment.

Ví dụ từ shell, khi đã có quyền kết nối:

~~~bash
pg_dump --schema-only --dbname=appdb --schema=comment_lab
~~~

Đây là lệnh **shell** gọi chương trình `pg_dump`, không phải SQL gửi trực tiếp qua JDBC. Tên `appdb` là ví dụ; thay bằng database thực tế của môi trường.

Trong bản dump, các comment có thể được biểu diễn bằng các câu:

~~~sql
COMMENT ON TABLE comment_lab.orders IS
    'Mỗi hàng đại diện cho một đơn.';
~~~

### 23.1. Không phải mọi cách export đều giữ comment

Nếu công cụ xuất lược đồ có lựa chọn bỏ comment như `--no-comments`, hoặc pipeline tự tạo lại bảng bằng cách chỉ đọc `information_schema.columns`, comment có thể bị bỏ sót.

Vì vậy:

- Kiểm tra cấu hình export và restore.
- Xem liệu comment có nằm trong migration/schema artifact hay không.
- Thử restore ở môi trường phù hợp.
- Không tự tin “đã có comment trong database thì chắc chắn mọi bản dump đều có”.

### 23.2. Dump không tự bảo đảm nội dung mô tả đúng

`pg_dump` có thể lưu lại comment hiện có, kể cả một comment đã lỗi thời. Quy trình backup/restore giải quyết **sao chép metadata**, không phải kiểm tra nghiệp vụ của câu mô tả.

## 24. INFORMATION_SCHEMA và PostgreSQL catalog khác nhau

PostgreSQL cung cấp cả **`information_schema`** và **`pg_catalog`**.

`information_schema.columns` có các trường như:

~~~sql
SELECT
    table_schema,
    table_name,
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_schema = 'comment_lab'
ORDER BY table_name, ordinal_position;
~~~

Nhưng mô tả COMMENT **không phải một cột tiêu chuẩn phổ biến của `information_schema.columns` trong PostgreSQL**. Muốn lấy comment, dùng `col_description()` hoặc join hệ thống catalog như đã minh họa.

### 24.1. Khi nào dùng nguồn nào?

| Cần làm gì? | Nguồn phù hợp |
|---|---|
| Xem nhanh mô tả một bảng trong terminal | `psql \d+ schema.table` |
| Xem mô tả function | `psql \df+` hoặc catalog/hàm |
| Lấy comment của một table | `obj_description(..., 'pg_class')` |
| Lấy comment của một column | `col_description(..., attnum)` |
| Lấy comment của một constraint | `obj_description(..., 'pg_constraint')` |
| Lấy comment routine | `pg_proc` và `obj_description` |
| Lấy comment shared object | `shobj_description` |
| Kiểm kê cột theo giao diện SQL chuẩn | `information_schema.columns` |
| Xuất DDL và mô tả | `pg_dump` theo tùy chọn phù hợp |
| Theo dõi lịch sử thay đổi comment | Migration/audit/version control |

Các thư viện JDBC cũng có API metadata, nhưng khả năng trả về mô tả trong trường như `REMARKS` phụ thuộc driver, phiên bản và cách cấu hình. Không suy luận mọi ứng dụng dùng JDBC đều tự động hiển thị comment.

## 25. Bảo mật: comment không phải nơi chứa bí mật

Comment thường là **metadata có thể quan sát bởi người dùng phù hợp trong database**. Không nên coi comment là vùng dữ liệu riêng tư chỉ dành cho người sở hữu object.

Tuyệt đối tránh ghi:

- Mật khẩu database, token hoặc API key.
- Chuỗi kết nối chứa secret.
- Thông tin xác thực nội bộ.
- Giá trị cá nhân nhạy cảm của một khách hàng cụ thể.
- SQL động chứa dữ liệu thực không cần thiết.
- Mô tả chi tiết sơ hở bảo mật hoặc đường bypass quyền.

Ví dụ không nên:

~~~sql
-- Không thực hiện:
-- COMMENT ON TABLE comment_lab.customers IS
-- 'Admin password = ...';
~~~

Thay vào đó, comment có thể nêu **phân loại và yêu cầu quản lý**:

~~~sql
COMMENT ON COLUMN comment_lab.customers.email IS
    'Thông tin liên hệ cá nhân; chỉ sử dụng theo chính sách bảo vệ dữ liệu của hệ thống.';
~~~

Câu mô tả này có ích với người dùng dữ liệu, nhưng quyền truy cập email vẫn phải được **cấp và kiểm tra** bằng PostgreSQL role/privilege, RLS nếu phù hợp, cùng chính sách ứng dụng.

### 25.1. Comment không phải lớp phân quyền

Một cột có comment “chỉ bộ phận kế toán xem” không có nghĩa PostgreSQL tự giới hạn `SELECT`.

Các biện pháp đúng có thể gồm:

- Giới hạn quyền bảng/cột/view.
- Áp dụng chính sách RLS khi kiến trúc cần và phù hợp.
- Dùng các role chức năng.
- Ghi log/audit truy cập cần thiết.
- Bảo vệ dữ liệu khi xuất sang BI hoặc công cụ kiểm kê.

**Tài liệu hóa chính sách** và **thực thi chính sách** là hai việc khác nhau.

## 26. Quy ước viết comment chất lượng

Một comment hữu ích nên trả lời **điều mà tên/kiểu dữ liệu chưa nói được**.

### 26.1. Ví dụ kém và tốt hơn

| Đối tượng | Comment kém | Comment hữu ích hơn |
|---|---|---|
| `customers` | “Bảng khách hàng” | “Một hàng = một khách hàng; customer_code là định danh nghiệp vụ” |
| `orders.total_amount` | “Số tiền” | “Tổng tiền đơn tại thời điểm xác nhận; đơn vị và cách tính theo hợp đồng nghiệp vụ” |
| `orders.created_at` | “Ngày tạo” | “Thời điểm tạo bản ghi, lưu TIMESTAMPTZ; không phải lúc thanh toán” |
| `orders.order_status` | “Trạng thái” | “pending/paid/cancelled; CHECK giới hạn tập giá trị, luồng chuyển trạng thái ở service” |
| `idx_orders_created_at` | “Index” | “Phục vụ danh sách đơn mới nhất theo created_at” |
| `v_paid_orders` | “Đơn đã trả tiền” | “View lọc status=paid; không bao gồm pending/cancelled” |
| `line_amount` | “Tính tiền” | “Tích số lượng và đơn giá; không bao gồm thuế/giảm giá” |

Cần điều chỉnh ví dụ theo **sự thật của hệ thống**. Một mô tả “tại thời điểm xác nhận” chỉ đúng nếu cột thực tế được chốt tại thời điểm đó.

### 26.2. Một khuôn mẫu ngắn

Với bảng:

~~~text
Mục đích:
Đơn vị mỗi hàng:
Nguồn ghi/chủ sở hữu nghiệp vụ:
Đối tượng liên quan:
Lưu ý sử dụng:
~~~

Với cột:

~~~text
Ý nghĩa:
Đơn vị/kiểu thời gian:
NULL/giá trị đặc biệt:
Nguồn hoặc cách tính:
Lưu ý về quyền/chất lượng dữ liệu:
~~~

Với view/report:

~~~text
Mục đích:
Điều kiện lọc:
Độ chi tiết kết quả:
Nguồn:
Độ trễ dữ liệu (nếu có):
~~~

Không cần sử dụng tất cả các dòng nếu một câu ngắn đã đủ. Comment là **metadata để đọc nhanh**, không phải nơi sao chép toàn bộ tài liệu quy trình.

### 26.3. Ngôn ngữ và thuật ngữ

Trong một dự án đa quốc gia, cần thống nhất ngôn ngữ comment. PostgreSQL lưu chuỗi Unicode phù hợp encoding nên có thể dùng tiếng Việt. Quan trọng là người dùng hệ thống hiểu được, không phải bắt buộc viết tiếng Anh.

Nên thống nhất những thuật ngữ như:

- “Đơn hàng” khác “giao dịch thanh toán”.
- “Thời điểm tạo” khác “ngày nghiệp vụ”.
- “Doanh thu” khác “tiền đã thu”.
- “Giá hiện hành” khác “giá tại thời điểm đặt”.

Một thuật ngữ thống nhất giúp báo cáo và migration giảm sai lệch khi dùng dữ liệu.

## 27. Chuỗi định danh và an toàn khi sinh COMMENT động

Khi tự động hóa đặt comment cho nhiều đối tượng, ứng dụng có thể cần sinh câu `COMMENT ON</BT> từ một danh sách schema/bảng/cột.

Không nên nối trực tiếp một tên đối tượng hoặc chuỗi mô tả do người dùng không tin cậy cung cấp vào SQL:

~~~text
"COMMENT ON TABLE " + tableName + " IS '" + description + "'"
~~~

Mẫu này có thể sai với identifier chứa chữ hoa/dấu cách, dấu nháy hoặc nguy hiểm hơn là tạo **SQL injection** nếu đầu vào không được kiểm soát.

### 27.1. Identifier và string literal là hai loại khác nhau

- Tên schema, table, column là **SQL identifier**.
- Mô tả sau `IS</BT> là **SQL string literal** hoặc `NULL`.

Trong một function PL/pgSQL có quyền và nguồn đầu vào được kiểm soát, có thể dùng `format()` theo kiểu:

~~~sql
-- Mẫu minh họa để sinh câu lệnh từ giá trị đã xác thực.
SELECT format(
    'COMMENT ON TABLE %I.%I IS %L',
    'comment_lab',
    'orders',
    'Đơn hàng theo quy trình bán hàng.'
);
~~~

Ở đây:

- `%I` giúp quote identifier.
- `%L` giúp quote giá trị thành SQL literal.

Câu trên **chỉ trả chuỗi văn bản**, không tự thực thi COMMENT. Nếu thực thi SQL động trong ứng dụng/procedure, vẫn cần allowlist, kiểm tra quyền và giới hạn đối tượng được phép thay đổi.

### 27.2. Tránh tên không đầy đủ

Khi có hai bảng tên `orders` ở hai schema, một câu:

~~~sql
COMMENT ON TABLE orders IS '...';
~~~

phụ thuộc `search_path` của session. Trong migration, nên ghi rõ:

~~~sql
COMMENT ON TABLE comment_lab.orders IS '...';
~~~

Điều này giúp tránh cập nhật nhầm đối tượng do cấu hình search path khác giữa môi trường.

## 28. Ảnh hưởng vận hành và transaction

`COMMENT ON</BT> là thao tác DDL metadata. Nó không đòi hỏi quét toàn bộ dữ liệu để “điền comment cho từng hàng”, nhưng vẫn tham gia cơ chế khóa/catalog và transaction của PostgreSQL.

Không nên kết luận “chỉ đổi metadata nên hoàn toàn không thể chặn query” trên mọi loại đối tượng, mọi tải và mọi phiên bản. Các thay đổi DDL đồng thời cần được triển khai theo lịch và chính sách phù hợp.

### 28.1. COMMENT có thể rollback

Trong database thử nghiệm:

~~~sql
BEGIN;

COMMENT ON TABLE comment_lab.orders IS
    'Mô tả thử nghiệm trong transaction.';

SELECT obj_description(
    'comment_lab.orders'::regclass,
    'pg_class'
);

ROLLBACK;
~~~

Sau `ROLLBACK`, comment trước transaction được giữ lại nếu không có thay đổi khác ảnh hưởng và transaction chưa commit.

Ví dụ này minh họa rằng comment có thể nằm trong quy trình migration có transaction. Nó không có nghĩa mọi DDL PostgreSQL đều transaction-safe theo cùng cách; một số lệnh quản trị có hạn chế riêng.

### 28.2. Sửa comment không đổi nội dung truy vấn nghiệp vụ

Nếu đang có:

~~~sql
SELECT order_id, total_amount
FROM comment_lab.orders;
~~~

Việc đổi comment của `total_amount` không làm PostgreSQL tự thay đổi giá trị cột, kiểu dữ liệu, điều kiện truy vấn hoặc quyền. **Ảnh hưởng chủ yếu là metadata mà con người và các công cụ đọc**.

Tuy nhiên, những công cụ tự sinh tài liệu hoặc code từ metadata có thể phản ánh comment mới; vì vậy sửa comment vẫn nên được xem là thay đổi có quản lý phiên bản.

## 29. Tài liệu hóa trong hệ thống lớn: chủ sở hữu và trách nhiệm bảo trì

Khi nhiều đội cùng dùng PostgreSQL, comment có thể lỗi thời nhanh nếu không có người chịu trách nhiệm.

Một quy trình hiệu quả:

1. **Quy định đối tượng nào bắt buộc có comment:** bảng nghiệp vụ, cột không rõ nghĩa, view báo cáo, chức năng public.
2. **Xác định owner nghiệp vụ:** đội chịu trách nhiệm ý nghĩa dữ liệu.
3. **Đặt comment trong migration:** tránh thay đổi thủ công không được kiểm soát.
4. **Tạo báo cáo độ phủ:** tìm bảng/cột thiếu comment.
5. **Kiểm tra độ chính xác khi sửa logic:** đổi kiểu, enum, currency, timezone, luồng trạng thái.
6. **Kiểm tra khả năng xuất/restore:** bảo đảm comment không biến mất giữa môi trường.
7. **Không đưa secret vào metadata:** người có quyền đọc catalog không được học thêm bí mật.
8. **Có nơi lưu tài liệu dài:** thiết kế API, luồng trạng thái và ownership có thể cần tài liệu ngoài database.

### 29.1. Comment và data catalog

Một tổ chức có thể dùng data catalog, BI metadata hoặc hệ thống lineage. Comment trong PostgreSQL đóng vai trò **nguồn mô tả gần đối tượng nhất**, giúp bổ sung hoặc đồng bộ sang catalog lớn hơn.

Nhưng comment tự nó không chứng minh:

- Dữ liệu có chất lượng tốt.
- Bảng được update theo lịch.
- Có lineage đầy đủ giữa mọi dịch vụ.
- Người dùng có quyền xem dữ liệu.
- Report dùng logic KPI đã được phê duyệt.

Những vấn đề này cần công cụ và quy trình khác.

### 29.2. Schema drift của comment

Development có thể ghi một mô tả, production giữ mô tả cũ. Khi chỉ so kiểu cột/index, hệ thống sẽ không phát hiện **drift của metadata tài liệu hóa**.

Có thể xuất danh sách comment từ catalog ở hai môi trường, chuẩn hóa theo khóa ổn định như:

~~~text
(schema, relation, object_kind)
(schema, table, column)
(schema, table, constraint_name)
(schema, routine_name, argument_types)
~~~

Rồi so sánh. **Không dùng OID làm định danh ổn định giữa các database** vì OID có thể khác nhau khi tạo lại đối tượng.

## 30. Bài tập thực hành

### Bài 1 — Mô tả đúng đơn vị hàng

Bảng `order_items` lưu nhiều dòng cho mỗi đơn hàng. Hãy viết comment thể hiện **mỗi hàng là một dòng sản phẩm trong đơn**, không phải cả đơn hàng.

**Gợi ý:**

~~~sql
COMMENT ON TABLE comment_lab.order_items IS
    'Mỗi hàng là một sản phẩm và số lượng trong một đơn hàng.';
~~~

Câu này chỉ chạy nếu bảng `comment_lab.order_items` đã được tạo.

### Bài 2 — Mô tả cột trạng thái

Viết comment cho `comment_lab.orders.order_status` để người dùng biết ba trạng thái hợp lệ. Tại sao comment đó không thay được `CHECK`?

**Gợi ý:**

~~~sql
COMMENT ON COLUMN comment_lab.orders.order_status IS
    'Trạng thái đơn: pending, paid, cancelled.';
~~~

Vì comment không thực thi quy tắc; constraint mới kiểm tra dữ liệu khi ghi theo ngữ nghĩa PostgreSQL.

### Bài 3 — Sửa mô tả mà không đổi cấu trúc

Đổi mô tả bảng `comment_lab.customers` để giải thích `customer_code` là mã nghiệp vụ, nhưng không thay schema.

**Gợi ý:** Dùng `COMMENT ON TABLE</BT>, không cần `ALTER TABLE`.

### Bài 4 — Xóa comment

Viết câu lệnh xóa mô tả của cột `email` mà không xóa cột.

**Đáp án gợi ý:**

~~~sql
COMMENT ON COLUMN comment_lab.customers.email IS NULL;
~~~

### Bài 5 — Comment ràng buộc khóa ngoại

Viết comment cho `fk_orders_customers`, mô tả đơn phải trỏ đến khách hàng tồn tại.

**Đáp án gợi ý:**

~~~sql
COMMENT ON CONSTRAINT fk_orders_customers
ON comment_lab.orders IS
    'Không cho phép đơn tham chiếu khách hàng không tồn tại.';
~~~

### Bài 6 — Function overloaded

Có hai function `compute_fee(integer)` và `compute_fee(numeric)`. Vì sao khi comment phải ghi chữ ký chính xác?

**Gợi ý:** PostgreSQL cho phép trùng tên khác kiểu tham số, nên chỉ tên có thể mơ hồ hoặc không định danh đúng routine.

### Bài 7 — Xem comment của table

Viết câu SQL trả comment của bảng `comment_lab.orders` bằng `obj_description()`.

**Đáp án gợi ý:**

~~~sql
SELECT obj_description(
    'comment_lab.orders'::regclass,
    'pg_class'
);
~~~

### Bài 8 — Xem comment từng cột

Cần lấy tên cột và comment của bảng `comment_lab.customers`. Vì sao không nên tự đánh số cột từ 1 tới N khi gọi `col_description()`?

**Gợi ý:** `attnum` của PostgreSQL có thể có khoảng trống sau khi xóa cột; lấy từ `pg_attribute` với `attnum > 0 AND NOT attisdropped`.

### Bài 9 — Tìm đối tượng thiếu comment

Viết truy vấn liệt kê những bảng thường trong `comment_lab` chưa có table comment.

**Gợi ý:** Dùng `pg_class`, `pg_namespace`, lọc `relkind IN ('r','p')`, `obj_description(..., 'pg_class') IS NULL`.

### Bài 10 — Comment và bảo mật

Một developer muốn ghi password của một dịch vụ vào comment vì tiện tìm khi dùng psql. Có nên làm không?

**Gợi ý:** Không. Comment là metadata, có thể bị người dùng có quyền truy cập catalog đọc; secret phải được lưu trong hệ thống quản lý bí mật thích hợp.

### Bài 11 — Materialized view

Một materialized view được refresh mỗi đêm. Comment nào quan trọng hơn: “view tổng hợp” hay “dữ liệu chỉ được cập nhật mỗi đêm”?

**Gợi ý:** Cần ghi cả mục đích và **độ trễ dữ liệu** vì người đọc có thể hiểu sai báo cáo là thời gian thực.

### Bài 12 — Migration thay đổi kiểu dữ liệu

Một cột `total_amount` đổi ngữ nghĩa từ “giá trước thuế” sang “giá sau thuế”. Ngoài DDL và code, cần làm gì với comment?

**Gợi ý:** Cập nhật comment trong migration cùng thay đổi, kiểm tra report và tài liệu liên quan, tránh giữ mô tả cũ.

### Bài 13 — Comment và psql

Trong terminal psql, dùng những lệnh nào để xem mô tả chi tiết của bảng và function?

**Gợi ý:**

~~~text
\d+ comment_lab.orders
\df+ comment_lab.line_amount
~~~

### Bài 14 — Đối tượng dùng chung

Tại sao mô tả của một database có thể nằm trong `pg_shdescription` thay vì `pg_description`?

**Gợi ý:** Database thuộc nhóm đối tượng cấp cluster; PostgreSQL quản lý metadata dùng chung bằng cơ chế riêng.

### Bài 15 — Tự động hóa

Một script nhận tên schema, bảng và comment từ tệp cấu hình. Vì sao không nên ghép chuỗi trực tiếp để sinh SQL?

**Gợi ý:** Identifier có thể cần quote, description có dấu nháy, và dữ liệu không tin cậy có thể dẫn tới SQL injection. Dùng kiểm tra allowlist, quote identifier và literal phù hợp.

## 31. Bảng tra nhanh

| Muốn làm gì? | Cú pháp/nguồn |
|---|---|
| Ghi mô tả schema | `COMMENT ON SCHEMA s IS '...';` |
| Ghi mô tả bảng | `COMMENT ON TABLE s.t IS '...';` |
| Ghi mô tả cột | `COMMENT ON COLUMN s.t.c IS '...';` |
| Ghi mô tả view | `COMMENT ON VIEW s.v IS '...';` |
| Ghi mô tả materialized view | `COMMENT ON MATERIALIZED VIEW s.mv IS '...';` |
| Ghi mô tả index | `COMMENT ON INDEX s.idx IS '...';` |
| Ghi mô tả constraint | `COMMENT ON CONSTRAINT c ON s.t IS '...';` |
| Ghi mô tả function | `COMMENT ON FUNCTION s.f(types) IS '...';` |
| Ghi mô tả procedure | `COMMENT ON PROCEDURE s.p(types) IS '...';` |
| Ghi mô tả trigger | `COMMENT ON TRIGGER tr ON s.t IS '...';` |
| Ghi mô tả domain | `COMMENT ON DOMAIN s.domain IS '...';` |
| Ghi mô tả type | `COMMENT ON TYPE s.type IS '...';` |
| Thay comment | Chạy `COMMENT ON</BT> mới trên cùng đối tượng |
| Xóa comment | `COMMENT ON ... IS NULL;` |
| Xem cú pháp COMMENT theo phiên bản | `psql: \h COMMENT` |
| Xem bảng và column comments | `psql: \d+ schema.table` |
| Xem comment function | `psql: \df+ schema.function` |
| Xem danh sách description | `psql: \dd schema.*` |
| Đọc comment table bằng SQL | `obj_description(oid,'pg_class')` |
| Đọc comment column bằng SQL | `col_description(table_oid,attnum)` |
| Đọc comment constraint | `obj_description(oid,'pg_constraint')` |
| Đọc comment function | `obj_description(oid,'pg_proc')` |
| Đọc comment database | `shobj_description(oid,'pg_database')` |
| Xuất schema và comment | `pg_dump --schema-only` với tùy chọn thích hợp |
| Kiểm soát lịch sử comment | Migration/version control |
| Thực thi quyền hay quy tắc nghiệp vụ | GRANT/REVOKE, constraints, RLS và logic phù hợp — **không phải comment** |

---

## Kết luận

**`COMMENT ON` là công cụ tài liệu hóa đối tượng ngay bên trong PostgreSQL**. Nó giúp diễn đạt mục đích của schema và bảng, ý nghĩa của từng cột, lý do có constraint/index, hợp đồng của view/function và lưu ý về dữ liệu tổng hợp. Những mô tả này có thể được xem nhanh trong `psql`, truy vấn bằng các hàm của `pg_catalog`, hoặc xuất cùng schema để quản lý theo migration.

Để tài liệu hóa đáng tin cậy, hãy ưu tiên **ngữ nghĩa nghiệp vụ thực sự**, đặt mô tả ở đúng đối tượng, kiểm soát thay đổi comment cùng DDL và tránh lưu bí mật trong metadata. Comment không kiểm tra dữ liệu, không thay phân quyền và không tự cập nhật khi logic ứng dụng thay đổi. Khi được quản lý như một phần của lược đồ, nó giúp người phát triển, phân tích và vận hành hiểu PostgreSQL nhanh hơn, giảm sai sót khi truy vấn hoặc thay đổi cấu trúc dữ liệu.
