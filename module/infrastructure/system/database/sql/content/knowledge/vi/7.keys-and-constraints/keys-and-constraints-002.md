# PRIMARY KEY và yêu cầu định danh duy nhất

Trong cơ sở dữ liệu quan hệ, **PRIMARY KEY (khóa chính)** là ràng buộc dùng để **định danh duy nhất mỗi hàng trong một bảng**. Khóa chính cho hệ quản trị cơ sở dữ liệu (DBMS) biết tập cột nào đóng vai trò định danh chính thức của bản ghi, để các thao tác truy xuất, cập nhật và liên kết dữ liệu có căn cứ rõ ràng.

Khóa chính không chỉ là một cột `id` thường gặp trong ví dụ SQL. Nó thể hiện một cam kết ở cấp lược đồ: **không có hai hàng cùng giá trị khóa chính, và không thành phần nào của khóa chính được là `NULL`**. DBMS phải bảo vệ cam kết này trước mọi câu lệnh ghi hợp lệ, kể cả khi nhiều kết nối cập nhật đồng thời.

Bài học tập trung vào ý nghĩa của định danh duy nhất, cách khai báo và chọn khóa chính, mối quan hệ với `UNIQUE`, `NOT NULL` và `FOREIGN KEY`, cùng những tác động khi thiết kế dữ liệu và vận hành hệ thống. Ví dụ thực hành dùng **PostgreSQL**; nguyên lý cốt lõi của khóa chính thuộc SQL nói chung, nhưng một số chi tiết cú pháp, chỉ mục và tự sinh mã phụ thuộc DBMS.

## 1. Vì sao mỗi hàng cần được nhận diện rõ?

Giả sử hệ thống lưu dữ liệu sản phẩm:

| product_name | price |
| --- | ---: |
| Bút bi | 8000 |
| Bút bi | 8000 |
| Bút bi | 10000 |

Nếu dùng `product_name` để xác định một bản ghi, thao tác “sửa giá bút bi” trở nên mơ hồ. Hai hàng cùng tên, cùng giá có thể đại diện cho hai sản phẩm khác mã, hoặc là dữ liệu bị ghi lặp do lỗi. Chỉ nhìn tên và giá không đủ để khẳng định hàng nào phải sửa.

Có thể thêm một mã định danh:

| product_id | product_name | price |
| ---: | --- | ---: |
| 101 | Bút bi | 8000 |
| 102 | Bút bi | 8000 |
| 103 | Bút bi | 10000 |

Giờ đây câu SQL có thể chọn một hàng cụ thể:

```sql
UPDATE products
SET price = 9000
WHERE product_id = 102;
```

**Có cột tên là `id` không tự động làm các giá trị trở nên duy nhất.** Nếu chỉ khai báo một cột số thường, DBMS vẫn có thể cho phép nhiều hàng mang cùng số hoặc giá trị `NULL` tùy các ràng buộc khác. Khóa chính là cách đưa quy tắc “mỗi hàng có một định danh hợp lệ, không trùng” vào database.

### 1.1. Định danh ở cấp bảng có phạm vi như thế nào?

Giá trị khóa chính duy nhất **trong bảng mà ràng buộc được khai báo**. `customers.id = 1` và `orders.id = 1` có thể cùng tồn tại; chúng chỉ tới hai loại đối tượng khác nhau. Bản thân số `1` không phải định danh toàn cục. Khi giao tiếp giữa dịch vụ hoặc nhiều hệ thống, cần biết thêm loại đối tượng, phạm vi tổ chức/tenant, nguồn dữ liệu hoặc sử dụng chiến lược định danh phù hợp.

Khóa chính bảo vệ tính duy nhất của **các hàng đang tồn tại theo trạng thái database**. Nó không tự ngăn một giá trị bị xóa rồi được sử dụng lại về sau nếu ứng dụng cho phép. Yêu cầu “mã không bao giờ được tái sử dụng” là một quy tắc bổ sung cần thiết kế rõ.

## 2. Hai tính chất bắt buộc của PRIMARY KEY

Mọi khóa chính có hai tính chất nền tảng:

1. **Duy nhất (`UNIQUE`):** không có hai hàng nào trong bảng có cùng tổ hợp giá trị khóa chính.
2. **Không chứa `NULL` (`NOT NULL`):** từng cột tham gia khóa chính đều phải có giá trị.

Các tính chất ấy được kiểm tra trên thao tác `INSERT` và `UPDATE`, không chỉ lúc đọc bằng `SELECT`.

```sql
CREATE TABLE demo_students (
    student_id INTEGER PRIMARY KEY,
    full_name TEXT NOT NULL
);

INSERT INTO demo_students (student_id, full_name)
VALUES
    (1, 'An'),
    (2, 'Binh');

-- Lỗi: student_id = 1 đã tồn tại.
-- INSERT INTO demo_students VALUES (1, 'Chi');

-- Lỗi: khóa chính không được NULL.
-- INSERT INTO demo_students VALUES (NULL, 'Dung');
```

Trong PostgreSQL, hai lệnh bị chú thích sẽ bị ràng buộc khóa chính từ chối. Không cần viết một câu `SELECT` thủ công để kiểm tra trùng trước mỗi `INSERT`; database đã có trách nhiệm thực thi bất biến.

### 2.1. PRIMARY KEY là ràng buộc dữ liệu, không chỉ là tên cột

Hai cách khai báo sau tương đương về mục đích với khóa đơn:

```sql
CREATE TABLE demo_a (
    id BIGINT PRIMARY KEY,
    name TEXT NOT NULL
);
```

```sql
CREATE TABLE demo_b (
    id BIGINT NOT NULL,
    name TEXT NOT NULL,
    CONSTRAINT pk_demo_b PRIMARY KEY (id)
);
```

Với PostgreSQL, PRIMARY KEY tự bao gồm yêu cầu NOT NULL; ghi thêm NOT NULL trực tiếp trong định nghĩa cột không bắt buộc để đạt hai tính chất trên. Việc **đặt tên ràng buộc** (`pk_demo_b`) giúp thông báo lỗi và script migration dễ đọc hơn.

Một bảng có thể có **tối đa một ràng buộc PRIMARY KEY**, nhưng khóa đó có thể gồm **một hoặc nhiều cột**. Một bảng vẫn có thể có nhiều ràng buộc `UNIQUE` cho những cách định danh khác.

## 3. Khóa chính một cột và khóa chính ghép

### 3.1. Khóa chính một cột

Đây là dạng quen thuộc khi mỗi đối tượng được gán một mã:

```sql
CREATE TABLE products (
    product_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    product_name TEXT NOT NULL,
    unit_price NUMERIC(12, 2) NOT NULL CHECK (unit_price >= 0)
);
```

Trong ví dụ:

- `product_id` là khóa chính, định danh mỗi hàng sản phẩm.
- `sku` là mã nghiệp vụ có ràng buộc `UNIQUE` và `NOT NULL`; nó cũng xác định một sản phẩm, nhưng không được chọn làm khóa chính.
- `product_name` có thể trùng, vì nhiều sản phẩm có thể có tên tương tự.
- `unit_price` có ràng buộc miền hợp lệ, **không tham gia định danh**.

`GENERATED ALWAYS AS IDENTITY` là cú pháp PostgreSQL cho giá trị do DBMS tạo từ cơ chế identity/sequence. Nó giúp tạo số mới khi INSERT mà không cần ứng dụng tự lấy `MAX(id) + 1`. **Chính PRIMARY KEY mới bảo đảm không trùng trong bảng**; việc tự sinh giá trị và việc kiểm tra tính duy nhất là hai chức năng liên quan nhưng không đồng nhất.

Tạo sản phẩm:

```sql
INSERT INTO products (sku, product_name, unit_price)
VALUES ('PEN-BLUE-01', 'Bút bi xanh', 8000)
RETURNING product_id, sku;
```

`RETURNING` là cách PostgreSQL lấy lại mã vừa tạo từ chính lệnh ghi; cách lấy mã sinh tự động ở JDBC/DBMS khác có thể khác.

### 3.2. Khóa chính ghép (composite primary key)

Khi định danh tự nhiên của một hàng phụ thuộc **nhiều cột cùng lúc**, có thể chọn khóa ghép. Ví dụ mỗi dòng hàng trong một đơn có số thứ tự riêng:

```sql
CREATE TABLE customers (
    customer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL
);

CREATE TABLE orders (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customers(customer_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE order_items (
    order_id BIGINT NOT NULL REFERENCES orders(order_id),
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    product_id BIGINT NOT NULL REFERENCES products(product_id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(12, 2) NOT NULL CHECK (unit_price >= 0),
    CONSTRAINT pk_order_items PRIMARY KEY (order_id, line_no)
);
```

Ở đây `line_no = 1` có thể xuất hiện trong nhiều đơn hàng, nhưng **cặp `(order_id, line_no)`** phải duy nhất:

| order_id | line_no | product_id | quantity |
| ---: | ---: | ---: | ---: |
| 500 | 1 | 101 | 2 |
| 500 | 2 | 102 | 1 |
| 501 | 1 | 101 | 1 |

Ba dòng này có thể hợp lệ khi mã sản phẩm và đơn hàng tương ứng đã tồn tại. Cặp `(500, 1)` lặp lần thứ hai sẽ bị từ chối, dù `product_id` hoặc `quantity` khác.

Khóa ghép đặt ở **cấp bảng** với `PRIMARY KEY (order_id, line_no)`. Không thể tạo hai khóa chính độc lập bằng cách thêm `PRIMARY KEY` ở mỗi cột; điều đó không diễn tả “hai cột cùng định danh một dòng”.

Vì mọi thành phần khóa chính đều không được NULL, trong ví dụ cả `order_id` và `line_no` đều phải có giá trị. Khóa ghép không yêu cầu từng cột duy nhất khi đứng riêng: chỉ **tổ hợp đầy đủ** mới cần duy nhất.

### 3.3. Chọn khóa một cột hay khóa ghép?

| Tiêu chí | Khóa một cột | Khóa ghép |
| --- | --- | --- |
| Tính dễ tham chiếu | Một giá trị để JOIN/FOREIGN KEY | Cần mang đủ các cột định danh |
| Phù hợp mô hình | Thực thể có mã độc lập | Bản ghi chỉ có ý nghĩa trong phạm vi thực thể cha hoặc tổ hợp |
| Kích thước khóa và chỉ mục | Thường gọn nếu dùng BIGINT | Có thể lớn hơn, tùy kiểu/số lượng cột |
| Cập nhật khóa | Thường ít thay đổi nếu mã sinh ổn định | Rủi ro nếu một thành phần mang ý nghĩa có thể thay đổi |
| Tính duy nhất nghiệp vụ | Có thể cần UNIQUE bổ sung | Có thể thể hiện trực tiếp tổ hợp nghiệp vụ |

Không có dạng nào luôn tốt hơn. Chọn dựa trên **định danh có ổn định không, các bảng khác cần tham chiếu như thế nào và mẫu truy vấn thực tế**.

## 4. Khóa tự nhiên, khóa thay thế và khóa ứng viên

Trong thiết kế quan hệ, một bảng có thể có **nhiều khóa ứng viên (candidate keys)**: mỗi tập cột có thể định danh duy nhất hàng và là tối thiểu theo ý nghĩa khóa. Người thiết kế chọn một trong số đó làm PRIMARY KEY, những cách định danh còn lại có thể được bảo vệ bằng `UNIQUE` kèm yêu cầu không NULL nếu cần.

- **Khóa tự nhiên (natural key):** xuất phát từ miền nghiệp vụ, ví dụ mã quốc gia ISO hoặc số định danh đã được đảm bảo duy nhất trong phạm vi xác định.
- **Khóa thay thế (surrogate key):** được tạo để định danh hàng, ví dụ `BIGINT IDENTITY` hoặc UUID; bản thân giá trị không nhất thiết mang ý nghĩa nghiệp vụ.
- **Khóa chính (primary key):** khóa được chọn làm định danh chính thức trong bảng.
- **Khóa thay thế khác (alternate key):** khóa ứng viên không được chọn làm PRIMARY KEY, thường khai báo bằng các ràng buộc phù hợp.

Ví dụ một bảng mã quốc gia nhỏ, trong một hệ thống tin cậy bộ mã tiêu chuẩn:

```sql
CREATE TABLE countries (
    iso_code CHAR(2) PRIMARY KEY,
    country_name TEXT NOT NULL
);
```

Mã ISO hai ký tự có thể phù hợp làm khóa tự nhiên nếu bộ mã là nguồn chuẩn và chính sách thay đổi rõ ràng. Tuy nhiên, không phải khóa tự nhiên nào cũng ổn định:

```sql
CREATE TABLE app_users (
    user_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL
);
```

Email thường được yêu cầu không trùng trong hệ thống, nhưng người dùng có thể đổi email. Để các bảng con tham chiếu qua `user_id`, ứng dụng có thể thay đổi email mà không phải cập nhật toàn bộ khóa ngoại gắn với người dùng.

**Khóa sinh tự động không thay thế ràng buộc duy nhất của nghiệp vụ.** Nếu chỉ dùng `user_id` mà bỏ `UNIQUE(email)` trong khi sản phẩm cấm hai tài khoản có cùng email chuẩn hóa, hệ thống vẫn có thể lưu hai hàng khác ID nhưng vi phạm quy tắc tài khoản.

### 4.1. Yêu cầu duy nhất phải xác định theo phạm vi và phép so sánh

Không phải mọi trường tên, email, SKU hay mã hợp đồng đều duy nhất trên toàn hệ thống.

Ví dụ trong ứng dụng nhiều tổ chức (*multi-tenant*), mã đơn hàng `ORDER-001` có thể tồn tại ở hai tổ chức khác nhau. Yêu cầu có thể là **mỗi tổ chức không có hai đơn cùng số thứ tự**, thay vì số thứ tự duy nhất toàn cầu:

```sql
CREATE TABLE tenants (
    tenant_id BIGINT PRIMARY KEY,
    tenant_name TEXT NOT NULL
);

CREATE TABLE tenant_invoices (
    tenant_id BIGINT NOT NULL REFERENCES tenants(tenant_id),
    invoice_no TEXT NOT NULL,
    issued_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, invoice_no)
);
```

Trong bảng này, `(tenant_id = 1, invoice_no = 'INV-001')` và `(tenant_id = 2, invoice_no = 'INV-001')` không trùng khóa. Nếu sản phẩm yêu cầu định danh độc lập để chia sẻ qua nhiều hệ thống, có thể dùng một khóa thay thế toàn cục và thêm `UNIQUE(tenant_id, invoice_no)`.

Với email hoặc mã văn bản, cần xác định các quy tắc chuẩn hóa chữ hoa/chữ thường, khoảng trắng, collation và độ dài trước khi áp dụng duy nhất. Ví dụ, PostgreSQL so sánh văn bản theo kiểu và collation được cấu hình; `UNIQUE(email)` thông thường không tự đồng nghĩa với chính sách “email không phân biệt chữ hoa/chữ thường” trong mọi cấu hình. Có thể cần một cột `normalized_email` được chuẩn hóa theo chính sách và ràng buộc UNIQUE trên cột đó, hoặc kiểu/chỉ mục phù hợp.

## 5. PRIMARY KEY khác gì với UNIQUE, NOT NULL và FOREIGN KEY?

Bốn ràng buộc này phối hợp nhưng không thay thế cho nhau:

| Ràng buộc | Trả lời câu hỏi | Đảm bảo chính |
| --- | --- | --- |
| `PRIMARY KEY` | Hàng này được định danh chính thức bằng gì? | Một tổ hợp giá trị duy nhất, mọi thành phần NOT NULL |
| `UNIQUE` | Tổ hợp nào khác cũng không được trùng? | Chống lặp trên cột/tổ hợp, với quy tắc NULL theo DBMS |
| `NOT NULL` | Trường nào bắt buộc có giá trị? | Không cho phép NULL |
| `FOREIGN KEY` | Bản ghi này tham chiếu tới bản ghi hợp lệ nào? | Bảo vệ tính toàn vẹn tham chiếu theo khóa được tham chiếu |

### 5.1. PRIMARY KEY và UNIQUE có giống nhau?

Trong PostgreSQL:

```sql
CREATE TABLE demo_codes (
    id BIGINT PRIMARY KEY,
    code TEXT UNIQUE
);

INSERT INTO demo_codes (id, code)
VALUES
    (1, NULL),
    (2, NULL),
    (3, 'A-001');
```

Hai hàng có `code = NULL` được chấp nhận bởi `UNIQUE` mặc định của PostgreSQL; còn `id` không thể là NULL và không thể lặp. Ràng buộc UNIQUE có thể phối hợp với NOT NULL để đảm bảo cả hai thuộc tính của một khóa ứng viên:

```sql
CREATE TABLE demo_accounts (
    account_id BIGINT PRIMARY KEY,
    account_no TEXT NOT NULL UNIQUE,
    display_name TEXT
);
```

Ở đây `account_id` là PRIMARY KEY và `account_no` vẫn được bảo vệ như một cách định danh không trùng, không NULL. Bảng vẫn chỉ có **một** PRIMARY KEY.

Quy tắc về NULL trong UNIQUE có khác biệt giữa DBMS. PostgreSQL từ phiên bản 15 hỗ trợ tùy chọn `NULLS NOT DISTINCT` khi cần coi những NULL trùng nhau cho kiểm tra duy nhất. Không áp dụng kết luận “UNIQUE luôn nhận nhiều NULL” cho mọi hệ SQL.

### 5.2. Khóa chính và khóa ngoại

Một `FOREIGN KEY` không tự sinh ID; nó yêu cầu giá trị đang tham chiếu phải tồn tại ở khóa đích hợp lệ (PRIMARY KEY hoặc ràng buộc/cấu trúc UNIQUE được hệ quản trị hỗ trợ).

Ví dụ:

```sql
CREATE TABLE customer_settings (
    customer_id BIGINT PRIMARY KEY
        REFERENCES customers(customer_id),
    language_code TEXT NOT NULL DEFAULT 'vi'
);
```

`customer_settings.customer_id` vừa là PRIMARY KEY (mỗi khách có **tối đa một** dòng settings) vừa là FOREIGN KEY (không có dòng settings cho khách không tồn tại). Đây là cách thể hiện quan hệ **một-một tùy chọn** từ khách tới cài đặt: không có gì buộc mỗi khách phải có một dòng settings, trừ khi có quy tắc bổ sung.

Với khóa ghép, khóa ngoại thường phải tham chiếu đủ các thành phần:

```sql
CREATE TABLE invoice_payments (
    payment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    invoice_no TEXT NOT NULL,
    amount NUMERIC(12, 2) NOT NULL CHECK (amount > 0),
    CONSTRAINT fk_payment_invoice FOREIGN KEY (tenant_id, invoice_no)
        REFERENCES tenant_invoices(tenant_id, invoice_no)
);
```

Ví dụ trên bảo đảm khoản thanh toán chỉ được gắn với một hóa đơn thuộc **đúng tenant** và có mã tương ứng. Khóa ngoại hai cột tránh một lỗi thiết kế khi chỉ kiểm tra `invoice_no` mà bỏ phạm vi tenant.

### 5.3. Định danh khác thứ tự và quan hệ

- PRIMARY KEY không tự xác định hàng nào “mới nhất”. Muốn hiển thị theo thời gian cần `ORDER BY created_at`, thêm khóa phụ khi cần ổn định.
- PRIMARY KEY không làm dữ liệu có quan hệ đúng nếu thiếu `FOREIGN KEY`. Ví dụ, một `orders.customer_id` có thể không hợp lệ nếu chỉ lưu giá trị mà không kiểm tra tham chiếu.
- PRIMARY KEY không chứng minh hàng có đúng nội dung nghiệp vụ. Hai khách hàng khác `customer_id` vẫn có thể là cùng một người thật nếu quy trình đăng ký trùng.
- PRIMARY KEY cũng không tự bảo đảm tính duy nhất của tập kết quả JOIN: một khách có nhiều đơn sẽ xuất hiện nhiều dòng khi JOIN với orders.

## 6. PRIMARY KEY bảo đảm điều gì khi nhiều người ghi cùng lúc?

Giả sử hai kết nối thực hiện đồng thời:

```sql
-- Kết nối A:
INSERT INTO demo_students (student_id, full_name)
VALUES (10, 'Hà');

-- Kết nối B:
INSERT INTO demo_students (student_id, full_name)
VALUES (10, 'Huy');
```

DBMS phải bảo vệ ràng buộc duy nhất. Tùy thời điểm và trạng thái giao dịch, một phiên có thể phải **chờ** phiên kia hoàn thành; khi xung đột được xác nhận, thao tác vi phạm sẽ bị từ chối. Không thể có hai hàng đã commit cùng PRIMARY KEY nếu constraint hợp lệ và đang được thực thi.

### 6.1. Vì sao kiểm tra bằng SELECT trước rồi INSERT chưa đủ?

Một cách làm dễ phát sinh lỗi:

```text
Kết nối A: SELECT ... WHERE id = 10  → chưa có
Kết nối B: SELECT ... WHERE id = 10  → chưa có
Kết nối A: INSERT id = 10            → thành công
Kết nối B: INSERT id = 10            → xung đột
```

Cả hai phiên đều có thể nhìn thấy “chưa có” tại thời điểm SELECT. Do đó, **kiểm tra tồn tại ở ứng dụng chỉ giúp trải nghiệm hoặc xác minh nghiệp vụ, không thay thế ràng buộc duy nhất tại database**. Hệ thống cần xử lý lỗi trùng khóa như một tình huống bình thường có thể xảy ra khi cạnh tranh.

Trong PostgreSQL, khi yêu cầu nghiệp vụ cho phép bỏ qua lần thêm bị trùng, có thể dùng:

```sql
INSERT INTO demo_students (student_id, full_name)
VALUES (10, 'Hà')
ON CONFLICT (student_id) DO NOTHING;
```

`ON CONFLICT` chỉ phù hợp nếu hành vi mong muốn khi trùng đã được xác định. Không nên dùng `DO NOTHING` cho mọi lỗi vì có thể che giấu lỗi nghiệp vụ. Nếu muốn cập nhật bản ghi có sẵn, `DO UPDATE` cần định nghĩa cột nào được cập nhật, quyền tác giả của dữ liệu và cách ngăn ghi đè ngoài ý muốn.

### 6.2. Khóa sinh tự động không có nghĩa “liên tục, không có khoảng trống”

Với `BIGINT GENERATED ... AS IDENTITY` ở PostgreSQL:

- Số mới thường được cấp qua sequence để các phiên không phải cùng tự tính `MAX(id) + 1`.
- Có thể có **khoảng trống** do giao dịch rollback, xung đột khi chèn, cấp trước hoặc thao tác quản trị.
- ID không nhất thiết phản ánh chính xác thứ tự commit, thời gian nghiệp vụ hay mức ưu tiên.
- Các thao tác cấp hoặc khôi phục giá trị không phải cam kết khóa sẽ tăng đúng 1 mãi mãi hay không bao giờ tái sử dụng trong mọi tình huống quản trị.

**Không dùng khóa chính sinh tự động làm số hóa đơn pháp lý liên tục** nếu quy định yêu cầu dãy mã không có khoảng trống. Những yêu cầu đó cần cơ chế đánh số nghiệp vụ riêng, kiểm soát giao dịch và quy trình vận hành phù hợp.

## 7. Chọn kiểu dữ liệu cho khóa chính

Chọn kiểu khóa có tác động tới kích thước chỉ mục, khóa ngoại, khả năng nhập/xuất dữ liệu và cách tạo ID.

| Kiểu / cách định danh | Ưu điểm | Giới hạn và điều cần cân nhắc |
| --- | --- | --- |
| `INTEGER` | Gọn, đơn giản | Miền số hữu hạn, có thể sớm cạn nếu bảng tăng lớn |
| `BIGINT` + identity | Gọn, dễ JOIN; phổ biến cho dữ liệu giao dịch | Cần lưu ý sequence, phạm vi giữa các hệ và việc lộ ID tuần tự |
| `UUID` | Có thể sinh phân tán, giảm phụ thuộc một bộ cấp số tập trung | 16 byte cho giá trị UUID; index và thứ tự chèn khác BIGINT, cần chọn chiến lược tạo UUID |
| Mã nghiệp vụ dạng `TEXT` | Dễ đọc và đối chiếu bằng mắt | Có thể dài, đổi quy tắc, khác collation/chữ hoa, thay đổi gây phức tạp FK |
| Khóa ghép | Diễn đạt trực tiếp phạm vi duy nhất | Các bảng con phải mang đủ thành phần; chỉ mục và JOIN thường rộng hơn |

Ví dụ chỉ định kiểu UUID do ứng dụng tạo:

```sql
CREATE TABLE external_events (
    event_id UUID PRIMARY KEY,
    event_type TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

Trong ví dụ này ứng dụng/nguồn bên ngoài cung cấp `event_id`. Việc chọn cơ chế sinh UUID, phiên bản UUID và chính sách trùng cần được xác định riêng. UUID được thiết kế để có xác suất va chạm thấp theo cơ chế sinh phù hợp, nhưng **PRIMARY KEY vẫn là lớp kiểm tra cuối cùng trong bảng**; UUID không loại bỏ nhu cầu ràng buộc.

Khi cần chuyển một hệ thống nhiều node hoặc nhập dữ liệu offline, một định danh sinh phân tán có thể phù hợp hơn ID sequence cục bộ. Ngược lại, nếu một DBMS duy nhất quản lý một bảng giao dịch lớn, BIGINT thường đơn giản và hiệu quả. Quyết định phụ thuộc quy mô, triển khai, môi trường bảo mật và đặc tính truy cập.

## 8. Khóa chính và chỉ mục: liên quan nhưng khác nhau

Trong PostgreSQL, tạo `PRIMARY KEY` thông thường sẽ tự động tạo **chỉ mục B-tree duy nhất** để hỗ trợ kiểm tra trùng và tra cứu khóa:

```sql
CREATE TABLE example_items (
    item_id BIGINT PRIMARY KEY,
    description TEXT NOT NULL
);

-- PostgreSQL tạo chỉ mục hỗ trợ PRIMARY KEY trên item_id.
```

Nhưng **ràng buộc** và **chỉ mục** không phải hai khái niệm đồng nhất:

- Ràng buộc PRIMARY KEY phát biểu tính đúng của dữ liệu (duy nhất, không NULL).
- Chỉ mục là cấu trúc DBMS dùng để kiểm tra và tìm kiếm hiệu quả.
- Không phải mọi truy vấn đều dùng chỉ mục khóa chính; bộ tối ưu có thể chọn quét bảng khi rẻ hơn.
- Chỉ mục không mặc nhiên thay thế mọi điều kiện lọc khác: cần xem mẫu truy vấn và kế hoạch thực thi.

Ví dụ:

```sql
SELECT item_id, description
FROM example_items
WHERE item_id = 42;
```

Một chỉ mục theo item_id là đường truy cập tốt khi bảng đủ lớn và điều kiện chọn ít hàng. Nhưng:

```sql
SELECT item_id, description
FROM example_items
ORDER BY description;
```

Chỉ mục khóa chính theo item_id không tự đáp ứng sắp xếp theo description. Cần đánh giá kế hoạch, thống kê và chỉ mục phù hợp nếu truy vấn này quan trọng.

### 8.1. Khóa ghép và tiền tố trái của chỉ mục

Với `PRIMARY KEY (order_id, line_no)` trong PostgreSQL, chỉ mục B-tree tạo từ khóa chính có thể hữu ích cho tra cứu:

```sql
SELECT *
FROM order_items
WHERE order_id = 500
ORDER BY line_no;
```

Hai cột theo đúng thứ tự khóa hỗ trợ việc tìm các dòng thuộc đơn và có khả năng trả theo line_no. Nhưng truy vấn chỉ có `WHERE line_no = 1` trên toàn hệ thống không nhất thiết tận dụng hiệu quả cùng một chỉ mục khi thiếu điều kiện trên cột dẫn `order_id`; planner có thể chọn kế hoạch khác. Cần chọn **thứ tự cột khóa ghép** dựa trên cả ý nghĩa định danh và nhu cầu truy vấn, hoặc thêm chỉ mục thứ cấp khi tải thực sự yêu cầu.

**PRIMARY KEY không bảo đảm thứ tự đầu ra nếu thiếu `ORDER BY`.** Dù dữ liệu được lưu hoặc đọc theo một chỉ mục tại thời điểm nhất định, thứ tự trả về của SELECT không có ORDER BY vẫn không được SQL cam kết.

### 8.2. Tác động lên ghi dữ liệu

Khi INSERT hoặc cập nhật giá trị khóa, DBMS phải duy trì cấu trúc chỉ mục và kiểm tra trùng. Khóa rộng hơn có thể tăng dung lượng chỉ mục và chi phí cập nhật, đặc biệt khi nhiều khóa ngoại và chỉ mục thứ cấp tham chiếu/đi kèm. Không nên đổi khóa chính chỉ vì quan sát một truy vấn đơn lẻ; hãy xét tổng tải đọc/ghi, cách JOIN và tiến trình migration.

## 9. Tính ổn định của định danh theo thời gian

PRIMARY KEY **không tự cấm cập nhật khóa**. Tuy nhiên, việc thay đổi khóa chính có thể ảnh hưởng tới mọi hàng ở bảng con đang tham chiếu nó.

```sql
-- Chỉ minh họa khả năng cập nhật giá trị khóa:
-- UPDATE customers SET customer_id = 9001 WHERE customer_id = 1001;
```

Nếu đơn hàng tham chiếu customer_id và khóa ngoại không có chính sách cập nhật dây chuyền, DBMS có thể chặn thao tác làm mất tính toàn vẹn tham chiếu. Có thể cấu hình `ON UPDATE CASCADE` nếu nghiệp vụ đòi hỏi và đã đánh giá tác động, nhưng **ổn định khóa ngay từ thiết kế thường đơn giản hơn**.

Một bộ mã có ý nghĩa nghiệp vụ có thể đổi theo năm hoặc chính sách. Một địa chỉ email, số điện thoại hoặc tên đăng nhập có thể thay đổi; dùng trực tiếp làm khóa chính của hàng triệu bảng con sẽ tăng chi phí. Khóa thay thế ổn định giúp tách **danh tính bản ghi** khỏi **thuộc tính có thể đổi**.

Mặt khác, không nên tạo một khóa surrogate rồi xem nhẹ các khóa ứng viên thực tế. Ví dụ hai dòng order_items có cùng `(order_id, line_no)` nhưng khác một id mới vẫn có thể vi phạm luật “mỗi dòng đơn chỉ có một vị trí”. Khi chuyển sang surrogate key, cần giữ `UNIQUE(order_id, line_no)` nếu đó là bất biến nghiệp vụ.

## 10. Các lỗi thiết kế định danh thường gặp

### 10.1. Dùng tên người hoặc tên sản phẩm làm khóa

Tên có thể trùng, thay đổi, phụ thuộc ngôn ngữ và cách nhập liệu. Dùng tên làm khóa có thể làm mất khả năng biểu diễn hai người trùng tên. Hãy chọn khóa bảo đảm duy nhất đúng theo phạm vi dữ liệu; tên là thuộc tính thông thường trừ khi miền nghiệp vụ có cam kết khác.

### 10.2. Tự lấy MAX(id) + 1

```sql
-- Tránh mô hình tự cấp mã kiểu này khi nhiều phiên chèn:
SELECT COALESCE(MAX(student_id), 0) + 1
FROM demo_students;
```

Hai phiên có thể cùng tính ra một số mới trước khi ai kịp INSERT. Dùng identity/sequence, UUID hoặc bộ cấp định danh có phối hợp. Giữ PRIMARY KEY để bảo vệ dữ liệu khỏi va chạm cuối cùng.

### 10.3. Mặc định mọi `id` đều duy nhất toàn hệ thống

`product_id = 10` chỉ định danh trong bảng products, không tự phân biệt sản phẩm ở một database hoặc môi trường khác. Khi nhập dữ liệu từ nhiều nguồn, cần thiết kế phạm vi định danh, mapping ID hoặc khóa gồm `(source_system, source_id)`.

### 10.4. Để cột định danh nghiệp vụ không có UNIQUE

Có `user_id PRIMARY KEY` nhưng không có bất cứ ràng buộc duy nhất nào cho mã tài khoản mà nghiệp vụ yêu cầu có một bản ghi duy nhất sẽ cho phép hai user_id khác nhau có cùng mã tài khoản. Đây không phải lỗi PRIMARY KEY; đó là **thiếu ràng buộc cho khóa ứng viên khác**.

### 10.5. Tin rằng kiểm tra trùng ở giao diện là đủ

Kiểm tra form và API có ích để báo lỗi nhanh, nhưng các kết nối đồng thời hoặc script dữ liệu có thể bỏ qua quy trình kiểm tra ấy. Ràng buộc tại DBMS mới bảo vệ nhất quán ở tầng lưu trữ.

### 10.6. Nhầm JOIN theo PRIMARY KEY với JOIN luôn một-một

```sql
SELECT c.customer_id, o.order_id
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.customer_id;
```

Một khách hàng có thể có nhiều đơn, nên hàng khách lặp lại trong kết quả JOIN. Khóa chính chỉ bảo đảm `customers.customer_id` duy nhất **trong bảng customers**, không làm kết quả JOIN tự duy nhất theo customer_id. Muốn một hàng trên mỗi khách cần xác định quy tắc GROUP BY, EXISTS hoặc cách lựa chọn đơn.

## 11. Thêm PRIMARY KEY cho bảng đã có dữ liệu

Khi một bảng cũ chưa có PRIMARY KEY, không nên lập tức `ALTER TABLE ... ADD PRIMARY KEY` mà bỏ qua dữ liệu đang tồn tại. Trước tiên cần biết **cột dự định làm khóa có NULL hoặc giá trị trùng không**:

```sql
-- Ví dụ giả sử bảng legacy_orders đang có cột legacy_id.

-- Đếm giá trị NULL:
SELECT COUNT(*) AS missing_ids
FROM legacy_orders
WHERE legacy_id IS NULL;

-- Tìm các giá trị bị lặp:
SELECT legacy_id, COUNT(*) AS occurrences
FROM legacy_orders
WHERE legacy_id IS NOT NULL
GROUP BY legacy_id
HAVING COUNT(*) > 1
ORDER BY occurrences DESC, legacy_id;
```

Hai truy vấn trên là minh họa để áp dụng với bảng nguồn thật; `legacy_orders` không được tạo trong ví dụ thực hành ở trên.

Nếu có trùng hoặc NULL, phải xác định **cách hợp nhất hoặc gán lại định danh** dựa trên nghiệp vụ. Không được tùy tiện xóa dòng trùng vì chúng có thể đang được tham chiếu hoặc biểu diễn những giao dịch khác nhau. Đồng thời kiểm tra các bảng con, khóa ngoại, tích hợp bên ngoài và ứng dụng đang đọc ID.

### 11.1. Một quy trình migration ở mức nguyên tắc

1. **Chọn định danh đích:** khóa nào đáp ứng không NULL, duy nhất, ổn định và có phạm vi rõ ràng?
2. **Khảo sát dữ liệu hiện hữu:** phát hiện NULL, trùng khóa, kiểu không hợp lệ và các tham chiếu tới mã cũ.
3. **Chuẩn bị thay đổi tương thích:** thêm cột hoặc cơ chế sinh ID nếu cần; bảo đảm ứng dụng cũ và mới có giai đoạn cùng hoạt động an toàn.
4. **Bổ sung/backfill dữ liệu:** điền mã thiếu một cách có kiểm soát, duy trì mapping mã cũ–mới và xử lý các quan hệ.
5. **Ngăn phát sinh dữ liệu lỗi mới:** cập nhật luồng ghi, ràng buộc tạm hoặc cơ chế đồng bộ phù hợp trong giai đoạn chuyển tiếp.
6. **Áp dụng PRIMARY KEY và FOREIGN KEY cần thiết:** dùng quy trình DDL phù hợp DBMS, đo thời gian khóa và ảnh hưởng tới hệ thống.
7. **Chuyển ứng dụng sang khóa mới và theo dõi:** kiểm tra tính tham chiếu, lỗi trùng khóa, hiệu năng; chỉ bỏ cấu trúc cũ sau khi chắc chắn không còn bên sử dụng.

Thêm PRIMARY KEY có thể xây dựng chỉ mục, quét dữ liệu và khóa bảng, tùy DBMS/phiên bản/kích thước. Trong PostgreSQL có kỹ thuật chuẩn bị unique index đồng thời cho một số kịch bản rồi gắn constraint, nhưng các điều kiện về NOT NULL, tính hợp lệ index và khóa cần được nghiên cứu cho từng migration. Một script chạy nhanh trên bảng 100 dòng không bảo đảm có thể chạy an toàn trên bảng hàng trăm triệu dòng.

### 11.2. Không nên mặc định xóa và cấp ID lại

Việc gán ID tuần tự mới cho toàn bộ bảng có thể làm hỏng các liên kết, URL, dữ liệu audit, cache và tham chiếu ngoài database. Nếu phải đổi khóa, cần mapping rõ ràng, chuyển bảng con và phối hợp phiên bản ứng dụng. Khóa là **hợp đồng định danh**, nên thay đổi phải được xem như migration dữ liệu và giao diện tích hợp, không chỉ thay một dòng DDL.

## 12. PRIMARY KEY trong các mô hình quan hệ phổ biến

| Mô hình | Khóa chính gợi ý | Lý do |
| --- | --- | --- |
| Khách hàng | `customer_id` | Định danh độc lập, ổn định; email thay đổi được |
| Sản phẩm | `product_id`, với `sku UNIQUE` | Phân biệt ID lưu trữ và mã nghiệp vụ |
| Đơn hàng | `order_id` | Dễ tham chiếu từ dòng hàng, thanh toán, vận chuyển |
| Dòng hàng | `(order_id, line_no)` | Vị trí dòng là duy nhất trong phạm vi đơn |
| Bảng nối nhiều-nhiều | `(student_id, course_id)` | Mỗi cặp đăng ký xuất hiện tối đa một lần |
| Cài đặt một-một của khách | `customer_id` vừa PK vừa FK | Một dòng cài đặt tối đa cho mỗi khách |
| Hóa đơn theo tổ chức | `(tenant_id, invoice_no)` hoặc surrogate PK + UNIQUE tổ hợp | Mã hóa đơn chỉ cần duy nhất trong tenant |

Ví dụ bảng nối nhiều-nhiều:

```sql
CREATE TABLE students (
    student_id BIGINT PRIMARY KEY,
    full_name TEXT NOT NULL
);

CREATE TABLE courses (
    course_id BIGINT PRIMARY KEY,
    course_name TEXT NOT NULL
);

CREATE TABLE enrollments (
    student_id BIGINT NOT NULL REFERENCES students(student_id),
    course_id BIGINT NOT NULL REFERENCES courses(course_id),
    enrolled_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (student_id, course_id)
);
```

Mỗi sinh viên có thể học nhiều khóa; mỗi khóa có nhiều sinh viên. Khóa chính tổ hợp ngăn cùng một cặp `(student_id, course_id)` bị đăng ký trùng, nếu quy tắc nghiệp vụ chỉ cho phép một lần đăng ký hiện hành. Nếu cần lưu lịch sử nhiều lần đăng ký cùng một khóa, mô hình phải bổ sung một định danh cho **lần đăng ký** và ràng buộc nghiệp vụ khác, thay vì cố ép dữ liệu vào khóa ghép không còn phù hợp.

## 13. Bài tập thực hành

### Bài 1 — Xác định khóa hợp lý

Cho bảng nhân viên gồm `employee_no`, `full_name`, `email`, `department`:

- `full_name` có thể trùng.
- `email` có thể đổi.
- `employee_no` do tổ chức cấp, không đổi và duy nhất trong tổ chức.

Hãy xác định khóa ứng viên và khóa chính phù hợp. Nếu nhiều tổ chức dùng chung một database và có thể cấp trùng `employee_no`, cần bổ sung cột nào để biểu diễn đúng phạm vi? So sánh `(organization_id, employee_no)` với một `employee_id` sinh riêng và `UNIQUE(organization_id, employee_no)`.

### Bài 2 — Phân biệt UNIQUE và PRIMARY KEY

Với bảng:

```sql
CREATE TABLE demo_members (
    member_id BIGINT PRIMARY KEY,
    phone TEXT UNIQUE
);
```

Hãy dự đoán điều gì xảy ra nếu:

1. Hai hàng có hai `member_id` khác nhau và cùng `phone = NULL` trong PostgreSQL.
2. Hai hàng có cùng `member_id` và hai số điện thoại khác nhau.
3. Hai hàng có `member_id` khác nhau nhưng cùng số điện thoại xác định.

Để bắt buộc mỗi thành viên phải có số điện thoại, cần thêm ràng buộc nào? Nếu cùng một số điện thoại có thể được dùng bởi nhiều thành viên, `UNIQUE(phone)` có còn đúng nghiệp vụ không?

### Bài 3 — Thiết kế khóa ghép

Một đơn hàng chứa nhiều dòng. Mỗi dòng được đánh số từ 1 trong phạm vi một đơn. Hãy viết DDL dùng `PRIMARY KEY(order_id, line_no)` và giải thích tại sao `line_no` không thể là PRIMARY KEY một mình. Viết một câu SELECT lấy các dòng của một đơn theo đúng thứ tự dòng.

### Bài 4 — Mô phỏng ghi đồng thời

Hai phiên cùng kiểm tra rằng mã SKU mới chưa tồn tại, rồi cùng INSERT. Hãy giải thích vì sao kết quả SELECT trước INSERT không đủ để bảo đảm không trùng. Ràng buộc nào phải tồn tại tại database? Khi nhận lỗi duplicate key, ứng dụng cần đưa ra phản hồi nào hoặc có thể dùng `ON CONFLICT` theo chính sách nào?

### Bài 5 — Khóa và quan hệ nhiều-nhiều

Một học viên có thể đăng ký nhiều khóa học, nhưng không thể đăng ký trùng cùng khóa học trong trạng thái hiện hành. Hãy sử dụng bảng `enrollments` phía trên, thử lý giải vì sao `(student_id, course_id)` là khóa phù hợp. Nếu yêu cầu mở rộng để lưu nhiều lần học lại, khóa và mô hình phải thay đổi thế nào?

### Bài 6 — Phân biệt định danh và thứ tự thời gian

Một bảng giao dịch có `transaction_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY` và `created_at TIMESTAMPTZ`. Có thể kết luận transaction_id lớn hơn **chắc chắn** được commit muộn hơn hoặc được tạo vào ngày muộn hơn không? Vì sao? Viết SELECT để trả các giao dịch theo thời điểm tạo và thêm khóa phụ để xử lý trường hợp trùng thời điểm.

Gợi ý:

```sql
SELECT transaction_id, created_at
FROM transactions
ORDER BY created_at DESC, transaction_id DESC;
```

Truy vấn dùng bảng `transactions` giả định; yêu cầu của `ORDER BY` độc lập với cách ID được sinh.

## 14. Checklist tư duy khi chọn PRIMARY KEY

Trước khi tạo bảng, hãy tự trả lời:

1. **Đối tượng nào đang được định danh?** Một người, một đơn hàng, một dòng hàng hay một lần đăng ký?
2. **Phạm vi duy nhất là gì?** Một bảng, một tenant, một hệ thống nguồn hay nhiều môi trường?
3. **Khóa có thể NULL hoặc trùng không?** Nếu có, chưa phù hợp làm PRIMARY KEY.
4. **Khóa có ổn định không?** Tên, email và mã nghiệp vụ có thể thay đổi theo thời gian không?
5. **Các bảng khác sẽ tham chiếu ra sao?** Khóa một cột có đơn giản hơn khóa ghép không, và có làm mất quy tắc duy nhất nghiệp vụ không?
6. **Cần UNIQUE nào ngoài PRIMARY KEY?** Surrogate ID không tự cấm lặp email, SKU hoặc mã hóa đơn trong tenant.
7. **Định danh được tạo thế nào khi ghi đồng thời?** Dùng cơ chế sinh mã phù hợp, luôn để DBMS bảo vệ ràng buộc.
8. **Có cần migration từ dữ liệu cũ không?** Đánh giá trùng, NULL, khóa ngoại và tác động vận hành trước khi thêm ràng buộc.

## 15. Kết luận

**PRIMARY KEY là hợp đồng định danh chính thức của một bảng:** một hàng có đúng một giá trị khóa chính xác định và không trùng với bất kỳ hàng đang tồn tại nào khác trong bảng. Nó có thể là một cột hoặc một tổ hợp cột; trong PostgreSQL, DBMS thường tạo chỉ mục B-tree duy nhất để hỗ trợ thực thi ràng buộc.

Khóa chính không giải quyết mọi quy tắc về dữ liệu. `UNIQUE` bảo vệ những cách định danh bổ sung; `FOREIGN KEY` bảo vệ liên kết; `NOT NULL` và `CHECK` bảo vệ tính hiện diện và miền giá trị. Một khóa sinh tự động giúp cấp ID nhưng không thay thế quy tắc duy nhất nghiệp vụ, không bảo đảm số liên tục và không chứng minh thứ tự thời gian.

Khi thiết kế, hãy **chọn đơn vị bản ghi và phạm vi duy nhất trước, rồi mới quyết định tên cột và kiểu ID**. Một khóa chính ổn định, đúng nghĩa và được ràng buộc tại database giúp hệ thống cập nhật chính xác, tham chiếu nhất quán và an toàn trước các thao tác ghi đồng thời.
