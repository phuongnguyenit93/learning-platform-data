# RETURNING và nhận kết quả thay đổi trong một câu lệnh PostgreSQL

## 1. Vấn đề: ghi dữ liệu xong, lấy kết quả như thế nào?

Một thao tác thay đổi dữ liệu không chỉ có ý nghĩa “thành công hay thất bại”. Ứng dụng thường còn phải biết **hàng nào đã thay đổi** và **giá trị cuối cùng là gì**:

- Tạo khách hàng và lấy `customer_id` do PostgreSQL sinh.
- Tạo đơn hàng và nhận số đơn, thời điểm tạo, trạng thái mặc định.
- Trừ tồn kho và biết **số lượng còn lại**, chỉ khi có đủ hàng.
- Đổi trạng thái đơn và biết **đơn nào thực sự chuyển trạng thái**.
- Xóa bản ghi và lấy nội dung bản ghi vừa bị xóa để trả về API hoặc chuyển vào bảng lưu trữ.
- Chèn hoặc cập nhật theo khóa duy nhất (*upsert*) rồi nhận dữ liệu thực sự được ghi.
- Lấy tập các hàng bị ảnh hưởng để tạo nhật ký trong **cùng một câu SQL**.

PostgreSQL cung cấp mệnh đề **`RETURNING`** cho các câu lệnh sửa dữ liệu:

```sql
INSERT INTO ...
VALUES (...)
RETURNING ...;

UPDATE ...
SET ...
WHERE ...
RETURNING ...;

DELETE FROM ...
WHERE ...
RETURNING ...;
```

Khi dùng `RETURNING`, câu lệnh vẫn thực hiện thay đổi dữ liệu, nhưng đồng thời trả một **result set** gồm các hàng phù hợp với thao tác đã thực sự tác động.

Ví dụ ngắn:

```sql
INSERT INTO app_customers(email, full_name)
VALUES ('an@example.test', 'An')
RETURNING customer_id, email;
```

Trong ví dụ trên, `app_customers` là tên bảng minh họa. Nếu bảng tồn tại và câu INSERT thành công, ta lấy ngay ID được sinh mà không cần đoán khóa bằng `MAX(id)` hoặc thực hiện truy vấn đọc bảng lần thứ hai.

**Ý chính:** `RETURNING` biến “ghi rồi hỏi lại” thành “ghi và nhận giá trị thay đổi” trong một thao tác SQL.

### Mục tiêu bài học

Sau bài này, bạn sẽ hiểu và áp dụng được:

1. Cú pháp `RETURNING` sau `INSERT`, `UPDATE` và `DELETE`.
2. Khác biệt giữa **số hàng bị ảnh hưởng** và **các hàng được trả về**.
3. Cách nhận `IDENTITY`, `DEFAULT`, timestamp và các cột tính toán.
4. Cách lấy kết quả chính xác của `UPDATE ... WHERE ...` khi có điều kiện nghiệp vụ.
5. Cách `INSERT ... ON CONFLICT ... RETURNING` xử lý hàng insert, update hoặc không thay đổi.
6. Cách dùng `WITH ... RETURNING` để chuyển dữ liệu giữa các bước DML trong **một statement**.
7. Giới hạn của `RETURNING` đối với transaction, concurrency, trigger và các biến thể PostgreSQL.
8. Cách dùng `RETURNING` từ JDBC/Java, kể cả khi không có hàng nào được trả về.
9. Những lỗi phổ biến: đoán ID, đọc lại dữ liệu không nguyên tử, hiểu sai UPSERT, rò rỉ cột và dùng `RETURNING *` thiếu kiểm soát.
10. Bài tập thực hành đầy đủ, từ tạo đơn đến điều chỉnh tồn kho và ghi nhật ký.

## 2. RETURNING khác một câu SELECT theo sau

Không có `RETURNING`, một ứng dụng có thể viết:

```text
1. INSERT khách hàng.
2. SELECT để tìm khóa mới.
3. Dùng khóa mới để tạo bản ghi liên quan.
```

Cách này thường làm phát sinh thêm một lần trao đổi giữa ứng dụng và database. Nếu SELECT tìm theo điều kiện thiếu tính duy nhất hoặc đọc bảng vào thời điểm khác, kết quả có thể không phải hàng vừa ghi.

Một lỗi nghiêm trọng:

```sql
-- Không an toàn trong hệ thống nhiều phiên ghi:
SELECT MAX(customer_id) FROM customers;
```

Giá trị lớn nhất có thể thuộc về giao dịch khác. Ngay cả khi hệ thống dùng sequence, ID cũng không nhất thiết tăng liên tục theo thứ tự commit.

Với `RETURNING`:

```sql
INSERT INTO customers(email, full_name)
VALUES ('an@example.test', 'An')
RETURNING customer_id;
```

ID trả về gắn với **chính hàng mà câu INSERT đã tác động**. Không cần suy luận từ các hàng khác.

### 2.1. RETURNING không phải một câu SELECT độc lập

Các biểu thức trong `RETURNING` được đánh giá trong ngữ cảnh DML tương ứng. Kết quả không phải “toàn bộ bảng sau khi ghi”, mà chỉ gồm **những hàng liên quan đến thao tác thay đổi**.

| Câu lệnh | Những hàng có thể xuất hiện trong RETURNING |
|---|---|
| `INSERT ... RETURNING` | Hàng thực sự được chèn |
| `UPDATE ... RETURNING` | Hàng thực sự được cập nhật |
| `DELETE ... RETURNING` | Hàng thực sự bị xóa |
| `INSERT ... ON CONFLICT DO NOTHING RETURNING` | Hàng mới thực sự chèn; hàng bị bỏ qua không xuất hiện |
| `INSERT ... ON CONFLICT DO UPDATE RETURNING` | Hàng được chèn hoặc thực sự cập nhật |

Nếu điều kiện `WHERE` không tìm được hàng nào, `UPDATE ... RETURNING` hoặc `DELETE ... RETURNING` trả **0 hàng**. Đây là kết quả bình thường của một thao tác không tìm được đối tượng phù hợp.

### 2.2. RETURNING có bảo đảm đã COMMIT không?

**Không.** Một câu DML có thể trả dữ liệu trong transaction đang mở, nhưng transaction sau đó vẫn có thể `ROLLBACK`. Kết quả `RETURNING` phản ánh thao tác trong câu lệnh, **không phải giấy chứng nhận transaction đã commit thành công và bền vững**.

## 3. Chuẩn bị môi trường thực hành

Chúng ta xây dựng một schema lab nhỏ cho hệ thống bán hàng. Các ví dụ có tính minh họa; nên dùng **database thử nghiệm**. Không chạy câu xóa/chỉnh sửa trên production.

### 3.1. Khách hàng và hàng tồn kho

```sql
CREATE SCHEMA IF NOT EXISTS returning203;

CREATE TABLE returning203.customers (
    customer_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email text NOT NULL UNIQUE,
    full_name text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE returning203.inventory (
    sku text PRIMARY KEY,
    product_name text NOT NULL,
    stock integer NOT NULL CHECK (stock >= 0),
    unit_price numeric(12, 2) NOT NULL CHECK (unit_price >= 0),
    updated_at timestamptz NOT NULL DEFAULT now()
);
```

`GENERATED ALWAYS AS IDENTITY` giao PostgreSQL cấp giá trị khóa theo một identity sequence. `DEFAULT now()` tạo thời điểm dựa trên thời gian bắt đầu transaction; nếu muốn thời gian đồng hồ hiện tại ở thời điểm đánh giá, có thể cân nhắc `clock_timestamp()` với ngữ nghĩa khác.

### 3.2. Đơn hàng và nhật ký thay đổi tồn kho

```sql
CREATE TABLE returning203.orders (
    order_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id bigint NOT NULL
        REFERENCES returning203.customers(customer_id),
    sku text NOT NULL
        REFERENCES returning203.inventory(sku),
    quantity integer NOT NULL CHECK (quantity > 0),
    total_amount numeric(12, 2) NOT NULL
        CHECK (total_amount >= 0),
    status text NOT NULL DEFAULT 'NEW'
        CHECK (status IN ('NEW', 'PAID', 'CANCELLED')),
    client_request_id text NOT NULL UNIQUE,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE returning203.inventory_movements (
    movement_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku text NOT NULL REFERENCES returning203.inventory(sku),
    stock_delta integer NOT NULL CHECK (stock_delta <> 0),
    reason text NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now()
);
```

`client_request_id` là khóa nghiệp vụ do client tạo để phân biệt những lần yêu cầu. Dùng UNIQUE giúp database phát hiện yêu cầu trùng, nhưng **cách xử lý retry và cập nhật tồn kho phải được thiết kế cùng nhau**; chỉ có UNIQUE không tự làm cả workflow idempotent.

### 3.3. Thêm dữ liệu nền

```sql
INSERT INTO returning203.customers(email, full_name)
VALUES
    ('an@example.test', 'An'),
    ('binh@example.test', 'Bình');

INSERT INTO returning203.inventory(
    sku, product_name, stock, unit_price
)
VALUES
    ('BOOK-PG', 'Sách PostgreSQL', 5, 120000.00),
    ('KEYBOARD', 'Bàn phím', 2, 350000.00),
    ('MOUSE', 'Chuột', 0, 150000.00);
```

Để xác minh dữ liệu nền:

```sql
SELECT customer_id, email, full_name
FROM returning203.customers
ORDER BY customer_id;

SELECT sku, stock, unit_price
FROM returning203.inventory
ORDER BY sku;
```

**Quy ước lab:** các ví dụ sau thường là **kịch bản độc lập** trên trạng thái ban đầu này. Một câu `UPDATE` hoặc `DELETE` có thể làm thay đổi kết quả của những ví dụ tiếp theo nếu bạn chạy nối tiếp. Có thể dùng `BEGIN ... ROLLBACK` khi chỉ muốn quan sát, hoặc tạo lại fixture đúng quyền tại một môi trường test mới. Không dựa vào ID sinh ra bằng một con số cố định khi chưa nhận kết quả thực tế.

## 4. INSERT ... RETURNING: nhận khóa mới và dữ liệu đã lưu

### 4.1. Một hàng

```sql
INSERT INTO returning203.customers(email, full_name)
VALUES ('chi@example.test', 'Chi')
RETURNING
    customer_id,
    email,
    full_name,
    created_at;
```

Kết quả minh họa:

| customer_id | email | full_name | created_at |
|---:|---|---|---|
| 3 | chi@example.test | Chi | Thời điểm tạo do DB ghi |

Số `3` **chỉ là minh họa** trên một database lab mới, chưa từng tiêu thụ các identity khác. Trong môi trường thực, đọc trực tiếp giá trị `customer_id` được trả về, không tự cộng từ ID trước đó.

Các giá trị đáng chú ý:

- `customer_id` được sinh bởi identity.
- `created_at` là giá trị từ `DEFAULT now()`.
- `email` và `full_name` là giá trị đã ghi.

Ứng dụng có thể dùng ngay ID trả về để tạo tài nguyên liên quan mà không cần tự truy vấn tìm lại hàng theo email.

### 4.2. RETURNING có thể chọn biểu thức

```sql
INSERT INTO returning203.customers(email, full_name)
VALUES ('dung@example.test', 'Dũng')
RETURNING
    customer_id,
    lower(email) AS normalized_email,
    full_name,
    created_at::date AS created_date;
```

`RETURNING` không chỉ cho phép tên cột: nó có thể chứa những biểu thức trả giá trị, ví dụ `lower(email)` và phép ép kiểu `created_at::date`.

**Lưu ý:** `created_at::date` chịu ảnh hưởng cách diễn giải vùng giờ của session với giá trị `timestamptz`. Nếu API phải thể hiện ngày ở vùng cụ thể, cần chuyển đổi múi giờ tường minh.

### 4.3. Nhiều hàng

```sql
INSERT INTO returning203.customers(email, full_name)
VALUES
    ('lan@example.test', 'Lan'),
    ('minh@example.test', 'Minh')
RETURNING
    customer_id,
    email,
    full_name;
```

Câu lệnh trả **hai hàng** nếu cả hai đều được chèn thành công.

Không nên giả định thứ tự các hàng `RETURNING` là một cam kết sắp xếp cho mọi biến thể SQL và mọi kế hoạch. Nếu kết quả cần thứ tự chắc chắn, hãy sắp xếp ở lớp đọc hoặc bọc DML trong CTE rồi `SELECT ... ORDER BY`.

### 4.4. Không cần RETURNING * trong mọi API

```sql
INSERT INTO returning203.customers(email, full_name)
VALUES ('phuc@example.test', 'Phúc')
RETURNING *;
```

Đây là cú pháp hợp lệ, tiện khi học hoặc debug. Nhưng ở API thật, nên chọn cụ thể những cột cần dùng:

```sql
RETURNING customer_id, email, created_at;
```

Lý do: tránh trả dữ liệu nhạy cảm, giảm dữ liệu truyền qua mạng và tránh hợp đồng API thay đổi ngoài ý muốn khi bảng thêm cột.

## 5. INSERT ... DEFAULT VALUES RETURNING

Một số bảng có thể tạo hàng mà không cần cung cấp cột bắt buộc, vì mọi cột đều có identity/default thích hợp.

Trong schema lab, tạo bảng thử:

```sql
CREATE TABLE returning203.job_tokens (
    token_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    token_state text NOT NULL DEFAULT 'CREATED',
    generated_at timestamptz NOT NULL DEFAULT now()
);
```

Chèn hàng chỉ bằng default:

```sql
INSERT INTO returning203.job_tokens
DEFAULT VALUES
RETURNING token_id, token_state, generated_at;
```

Kết quả minh họa:

```text
token_id = <ID thực tế do PostgreSQL cấp>
token_state = CREATED
generated_at = <thời điểm mặc định>
```

Ở bảng `customers`, ta **không thể** dùng `DEFAULT VALUES` nếu cột `email`/`full_name` bắt buộc mà không có default; `RETURNING` không bỏ qua quy tắc `NOT NULL` hoặc các ràng buộc khác.

### 5.1. RETURNING và sequence

Identity thường dựa trên sequence. Trong PostgreSQL, các giá trị sequence được cấp **không nhất thiết được thu hồi sau rollback**. Do đó:

- ID có thể có khoảng trống.
- ID cao hơn không chứng minh transaction commit sau hơn một transaction khác.
- Không suy ra số lượng bản ghi bằng `MAX(id) - MIN(id) + 1`.
- Dùng `RETURNING` để nhận đúng ID đã được cấp cho hàng của statement.

## 6. INSERT ... SELECT RETURNING

Không nhất thiết phải chèn từ danh sách `VALUES`. Có thể chèn từ một truy vấn:

```sql
CREATE TABLE returning203.signup_queue (
    queue_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id bigint NOT NULL,
    email text NOT NULL,
    queued_at timestamptz NOT NULL DEFAULT now()
);
```

Ví dụ xếp hàng những khách có email ở domain test:

```sql
INSERT INTO returning203.signup_queue(customer_id, email)
SELECT c.customer_id, c.email
FROM returning203.customers AS c
WHERE c.email LIKE '%@example.test'
RETURNING queue_id, customer_id, email;
```

Kết quả gồm các hàng **được chèn vào `signup_queue`**, với `queue_id` mới của bảng đích. Nó không phải toàn bộ dữ liệu query SELECT nguồn, và chỉ chứa những cột được liệt kê ở RETURNING.

### 6.1. Trả kết quả theo thứ tự

Nếu cần danh sách được sắp xếp:

```sql
WITH inserted AS (
    INSERT INTO returning203.signup_queue(customer_id, email)
    SELECT c.customer_id, c.email
    FROM returning203.customers AS c
    WHERE c.email = 'an@example.test'
    RETURNING queue_id, customer_id, email
)
SELECT *
FROM inserted
ORDER BY queue_id;
```

Đây là **một câu SQL**: CTE chạy INSERT và cung cấp tập các hàng RETURNING; SELECT ngoài định dạng kết quả.

**Chú ý:** các ví dụ chèn dữ liệu vào `signup_queue` có thể thêm bản ghi trùng khách nếu chạy lại vì schema này chưa định nghĩa UNIQUE(customer_id). Hệ thống thật cần chính sách uniqueness và idempotency theo nghiệp vụ.

## 7. UPDATE ... RETURNING: lấy giá trị sau khi thay đổi

Ví dụ giảm giá sách PostgreSQL từ mức đã lưu:

```sql
UPDATE returning203.inventory AS i
SET
    unit_price = 110000.00,
    updated_at = now()
WHERE i.sku = 'BOOK-PG'
RETURNING
    i.sku,
    i.product_name,
    i.unit_price AS new_price,
    i.updated_at;
```

Nếu tìm được một hàng SKU, `RETURNING` trả giá trị **sau UPDATE**. Nếu không có SKU như vậy, nó trả 0 hàng.

### 7.1. Không cần SELECT lại giá sau UPDATE

Mẫu dùng hai statement:

```sql
UPDATE returning203.inventory
SET unit_price = 110000
WHERE sku = 'BOOK-PG';

SELECT unit_price
FROM returning203.inventory
WHERE sku = 'BOOK-PG';
```

có thể là hợp lệ nếu quản lý transaction phù hợp, nhưng tạo thêm vòng đọc. Trong hệ thống nhiều giao dịch, một SELECT độc lập sau khi transaction đầu đã commit có thể nhìn thấy thay đổi mới hơn từ transaction khác. Nó không luôn là bằng chứng nguyên trạng của **UPDATE vừa thực hiện**.

Nếu chỉ cần giá mà chính câu UPDATE tạo ra, `UPDATE ... RETURNING` diễn đạt trực tiếp và gọn hơn.

### 7.2. UPDATE nhiều hàng

```sql
UPDATE returning203.inventory AS i
SET
    unit_price = ROUND(i.unit_price * 1.05, 2),
    updated_at = now()
WHERE i.stock > 0
RETURNING
    i.sku,
    i.stock,
    i.unit_price AS increased_price;
```

Câu lệnh có thể trả nhiều hàng; mỗi hàng tương ứng với một hàng tồn kho đã được UPDATE. Không mặc định thứ tự trả về trùng thứ tự trên đĩa hoặc thứ tự khóa chính.

## 8. UPDATE có điều kiện nghiệp vụ và tính nguyên tử

Một tình huống quan trọng hơn cập nhật giá là **trừ tồn kho có kiểm tra đủ hàng**.

Giả sử SKU BOOK-PG có `stock = 5` và người dùng muốn lấy 2 sản phẩm. Viết một UPDATE có điều kiện:

```sql
UPDATE returning203.inventory AS i
SET
    stock = i.stock - 2,
    updated_at = now()
WHERE i.sku = 'BOOK-PG'
  AND i.stock >= 2
RETURNING
    i.sku,
    i.stock AS remaining_stock,
    i.unit_price;
```

Nếu có đủ hàng, PostgreSQL cập nhật và trả hàng chứa `remaining_stock = 3` trong trạng thái lab ban đầu.

Nếu không đủ hàng hoặc SKU không tồn tại, **không có hàng nào được cập nhật**, nên RETURNING trả tập rỗng.

### 8.1. Vì sao nên đưa điều kiện vào UPDATE?

Mẫu dễ gặp nhưng không an toàn nếu thiếu khóa/transaction phù hợp:

```text
Request A: SELECT stock -> 5
Request B: SELECT stock -> 5
Request A: trừ 4
Request B: trừ 4
```

Hai request đều có thể nghĩ “còn đủ 4”, nhưng lượng tồn thực tế không đủ phục vụ cả hai.

Với:

```sql
UPDATE ... SET stock = stock - 4
WHERE sku = 'BOOK-PG' AND stock >= 4
RETURNING stock;
```

việc kiểm tra điều kiện và sửa hàng được thực hiện trong **một câu lệnh**. PostgreSQL xử lý cập nhật cùng hàng bằng cơ chế khóa/MVCC phù hợp, và ở mức cô lập `READ COMMITTED`, một UPDATE chờ transaction khác thường phải đánh giá lại điều kiện trên phiên bản hàng hiện hành trước khi quyết định.

Do đó, hai transaction cạnh tranh cho năm sản phẩm không thể đều thành công trừ bốn trên cùng hàng nhờ mẫu cập nhật có điều kiện này.

### 8.2. Cách diễn giải 0 hàng

Không có hàng RETURNING có thể nghĩa là:

- SKU không tồn tại.
- SKU tồn tại nhưng tồn kho thấp hơn số cần lấy.
- Điều kiện khác trong `WHERE` không còn đúng.
- Một transaction khác vừa thay đổi hàng khiến điều kiện không còn thỏa.

Vì vậy, không nên tự động trả thông báo “hết hàng” chỉ dựa vào `0 rows` nếu hệ thống cần phân biệt lỗi không tồn tại SKU với lỗi thiếu tồn kho. Có thể truy vấn tiếp để giải thích nguyên nhân nếu cần, nhưng kết luận nguồn dữ liệu sau đó vẫn có thể thay đổi dưới concurrency.

### 8.3. RETURNING không thay thế CHECK

Constraint:

```sql
CHECK (stock >= 0)
```

ngăn dữ liệu âm. Trong khi đó:

```sql
WHERE stock >= requested_quantity
```

ngăn thao tác giảm quá số lượng tồn theo chính sách nghiệp vụ.

Hai cơ chế bổ sung nhau: điều kiện UPDATE quyết định có cấp hàng hay không, còn CHECK bảo vệ bất biến dữ liệu ở nhiều đường ghi khác nhau.

## 9. Trả “trước” và “sau” khi UPDATE: cần cẩn trọng

Với câu UPDATE thông thường, `RETURNING stock` cho giá trị **mới sau thay đổi**. Nó không mặc định sinh hai cột `old_stock` và `new_stock` trong mọi phiên bản PostgreSQL.

Nếu phép biến đổi chắc chắn là trừ đúng 2 đơn vị và không có trigger/rule thay đổi thêm, có thể **suy ra toán học**:

```sql
UPDATE returning203.inventory AS i
SET stock = i.stock - 2
WHERE i.sku = 'BOOK-PG'
  AND i.stock >= 2
RETURNING
    i.sku,
    i.stock + 2 AS previous_stock_inferred,
    i.stock AS current_stock;
```

Nhưng `previous_stock_inferred` là **giá trị suy ra từ công thức**, không phải một snapshot độc lập của cột trước UPDATE. Nếu trigger có sửa stock, hoặc công thức thay đổi, suy luận này có thể sai.

### 9.1. Khi cần giá trị cũ/chính xác phục vụ audit

Các phương án phù hợp tùy phiên bản và hệ thống:

- Sử dụng khả năng tham chiếu giá trị cũ/mới trong `RETURNING` **nếu phiên bản PostgreSQL đang dùng hỗ trợ**, theo tài liệu của phiên bản đó.
- Dùng trigger có ngữ nghĩa `OLD`/`NEW` để ghi audit ở mức hàng.
- Thiết kế một transaction với khóa/kiểm soát thích hợp để đọc trạng thái cũ và sau đó cập nhật.
- Sử dụng event log/outbox được ghi nguyên tử với thay đổi nghiệp vụ.

Không nên viết một self-join vào cùng bảng rồi mặc định dữ liệu trong `FROM` luôn là **bản cũ an toàn trước cạnh tranh**. Khi nhiều transaction đồng thời sửa một hàng, sự khác biệt giữa snapshot truy vấn và phiên bản hàng được cập nhật cần được xem xét kỹ.

### 9.2. Lưu ý khả năng theo phiên bản

Cú pháp và khả năng xử lý giá trị `OLD`/`NEW` trong mệnh đề `RETURNING` đã thay đổi qua các phiên bản PostgreSQL. Ví dụ cốt lõi của bài sử dụng những cú pháp ổn định: `INSERT/UPDATE/DELETE ... RETURNING col`. Nếu dự án phụ thuộc vào cú pháp `old.column` hoặc `new.column`, hãy kiểm tra đúng tài liệu và chạy thử ở phiên bản server mục tiêu trước khi triển khai.

## 10. Chuyển trạng thái có điều kiện

Một đơn hàng thường chỉ được chuyển sang `PAID` nếu đang ở trạng thái `NEW`.

Ví dụ tạo đơn seed trong lab bằng cách lấy ID khách qua email và SKU đã tồn tại:

```sql
INSERT INTO returning203.orders(
    customer_id,
    sku,
    quantity,
    total_amount,
    status,
    client_request_id
)
SELECT
    c.customer_id,
    'BOOK-PG',
    1,
    120000.00,
    'NEW',
    'seed-order-status-203'
FROM returning203.customers AS c
WHERE c.email = 'an@example.test'
RETURNING order_id, client_request_id, status;
```

Giả sử đã nhận được `order_id` thực tế. Có thể cập nhật dựa vào `client_request_id`, tránh tự đoán ID:

```sql
UPDATE returning203.orders AS o
SET status = 'PAID'
WHERE o.client_request_id = 'seed-order-status-203'
  AND o.status = 'NEW'
RETURNING
    o.order_id,
    o.client_request_id,
    o.status AS new_status;
```

Nếu thành công, kết quả trả hàng với `new_status = PAID`.

Nếu chạy cùng câu lần thứ hai, điều kiện `status = 'NEW'` không còn đúng, nên kết quả **0 hàng**. Đây là hành vi hữu ích khi áp dụng **state transition** theo trạng thái hiện tại.

### 10.1. Không đánh đồng 0 hàng với idempotent success

Lần gọi thứ hai không làm thay đổi gì có thể là vì đơn đã PAID, nhưng cũng có thể do mã yêu cầu không tồn tại, đơn bị CANCELLED hoặc bộ lọc khác.

Nếu API muốn coi “đã PAID” là thành công của một request lặp lại, cần **kiểm tra trạng thái hiện có và bảo đảm semantics/idempotency**; không đơn giản trả “thành công” cho mọi trường hợp UPDATE trả 0 hàng.

## 11. DELETE ... RETURNING: nhận dữ liệu của hàng vừa xóa

Với DELETE, các giá trị thông thường ở `RETURNING` là dữ liệu của **những hàng bị xóa**, tức trạng thái mà câu DELETE đã tác động.

Ví dụ chèn một đơn thử ở trạng thái hủy:

```sql
INSERT INTO returning203.orders(
    customer_id, sku, quantity, total_amount,
    status, client_request_id
)
SELECT
    c.customer_id, 'MOUSE', 1, 150000.00,
    'CANCELLED', 'seed-delete-203'
FROM returning203.customers AS c
WHERE c.email = 'binh@example.test'
RETURNING order_id, status, client_request_id;
```

Sau đó:

```sql
DELETE FROM returning203.orders AS o
WHERE o.client_request_id = 'seed-delete-203'
  AND o.status = 'CANCELLED'
RETURNING
    o.order_id,
    o.customer_id,
    o.sku,
    o.quantity,
    o.total_amount,
    o.status,
    o.created_at;
```

Nếu hàng tồn tại và đúng trạng thái, PostgreSQL xóa hàng và trả nội dung được yêu cầu. Không phải thực hiện một SELECT trước để lưu lại các cột đó.

Nếu gọi DELETE lần hai, hàng đã biến mất, nên `RETURNING` trả 0 hàng.

### 11.1. DELETE RETURNING khác SELECT rồi DELETE

```text
SELECT để xem hàng -> DELETE hàng
```

là hai statement; nếu không có quản lý transaction/khóa thích hợp, dữ liệu có thể thay đổi giữa hai statement.

`DELETE ... RETURNING` gắn kết quả trả về với **hàng thực sự bị DELETE**, giúp ứng dụng tránh đoán dữ liệu đã xóa.

### 11.2. Ràng buộc khóa ngoại vẫn có hiệu lực

Nếu một hàng được tham chiếu bởi khóa ngoại `ON DELETE RESTRICT` hoặc ràng buộc khác, câu DELETE có thể thất bại. `RETURNING` **không vượt qua khóa ngoại, trigger, RLS hoặc bất kỳ constraint nào**.

Với `ON DELETE CASCADE`, những hàng bị xóa do hành động cascade ở bảng khác không mặc nhiên trở thành các hàng của `DELETE ... RETURNING` trên bảng gốc. Muốn có nhật ký toàn bộ thay đổi liên bảng, cần thiết kế audit phù hợp.

## 12. RETURNING * và RETURNING các biểu thức

Giống phần `SELECT`, mệnh đề `RETURNING` có thể chọn cột, phép tính và alias:

```sql
UPDATE returning203.inventory AS i
SET unit_price = ROUND(i.unit_price * 0.90, 2)
WHERE i.sku = 'KEYBOARD'
RETURNING
    i.sku AS product_code,
    i.product_name,
    i.unit_price AS discounted_price,
    ROUND(i.unit_price * 1.10, 2) AS illustrative_markup;
```

Cột `illustrative_markup` chỉ là phép tính minh họa **trên giá mới**; nó không phải giá cũ nếu công thức UPDATE khác 10% hoặc có trigger thay đổi giá.

### 12.1. Không dùng RETURNING để tính một tổng nhóm trực tiếp

Nếu cần một dòng tóm tắt “đã sửa bao nhiêu SKU, tổng tồn sau sửa là bao nhiêu”, nên bọc DML trong CTE rồi aggregate bên ngoài:

```sql
WITH changed AS (
    UPDATE returning203.inventory AS i
    SET updated_at = now()
    WHERE i.stock > 0
    RETURNING i.sku, i.stock
)
SELECT
    COUNT(*) AS changed_products,
    COALESCE(SUM(stock), 0) AS total_stock_after
FROM changed;
```

Ở đây `changed` là **tập hàng được UPDATE RETURNING**. Câu SELECT ngoài có thể dùng `COUNT`/`SUM`/`GROUP BY` như khi đọc một bảng tạm logic.

### 12.2. Sắp xếp kết quả DML

Không nên viết `ORDER BY` trực tiếp sau `RETURNING` theo cách `SELECT` thông thường:

```sql
-- Không phải cú pháp UPDATE ... RETURNING ... ORDER BY phổ quát.
-- UPDATE ... RETURNING sku ORDER BY sku;
```

Cách rõ ràng là:

```sql
WITH changed AS (
    UPDATE returning203.inventory
    SET updated_at = now()
    WHERE stock > 0
    RETURNING sku, stock
)
SELECT sku, stock
FROM changed
ORDER BY sku;
```

## 13. INSERT ... ON CONFLICT DO NOTHING RETURNING

Đôi khi ứng dụng muốn tạo một bản ghi chỉ nếu chưa có khóa duy nhất.

Ví dụ SKU `BOOK-PG` đã có sẵn trong inventory:

```sql
INSERT INTO returning203.inventory(
    sku, product_name, stock, unit_price
)
VALUES ('BOOK-PG', 'Sách PostgreSQL', 7, 125000.00)
ON CONFLICT (sku) DO NOTHING
RETURNING sku, stock, unit_price;
```

Vì SKU đã có, PostgreSQL bỏ qua thao tác insert cho hàng đó. Kết quả `RETURNING` là **0 hàng**.

Quan trọng:

- `DO NOTHING` không cập nhật bản ghi đã tồn tại.
- Nó **không trả bản ghi đang tồn tại**.
- Tập rỗng không phải dữ liệu SKU hiện có.
- Nếu insert một SKU mới chưa có, nó trả hàng mới được tạo.

### 13.1. Muốn “insert nếu chưa có, nếu có thì trả bản ghi cũ” thì sao?

Cú pháp `DO NOTHING RETURNING` **không tự đáp ứng** yêu cầu này. Có thể cần một bước SELECT bổ sung hoặc một chiến lược upsert/idempotency khác, với kiểm soát concurrency thích hợp.

Tránh lấy một kết quả rỗng rồi khẳng định “khóa đã tồn tại với giá trị X” khi chưa có dữ liệu chứng minh.

### 13.2. Trong bulk insert có xung đột một phần

Nếu INSERT nhiều hàng và chỉ một số hàng bị conflict:

```sql
INSERT INTO returning203.inventory(
    sku, product_name, stock, unit_price
)
VALUES
    ('BOOK-PG', 'Sách PostgreSQL', 9, 130000.00),
    ('PAD-NEW', 'Bàn di chuột', 5, 70000.00)
ON CONFLICT (sku) DO NOTHING
RETURNING sku, stock;
```

Nếu BOOK-PG đã tồn tại và PAD-NEW chưa có, chỉ **PAD-NEW** được trả về. Đây là cách nhìn chính xác hơn “hai hàng đầu vào nghĩa là RETURNING luôn có hai hàng”.

## 14. INSERT ... ON CONFLICT DO UPDATE RETURNING (UPSERT)

Khi có khóa duy nhất, một câu INSERT có thể xử lý hai hướng:

- Không có xung đột → **INSERT**.
- Có xung đột → **UPDATE** hàng hiện có.

Ví dụ:

```sql
INSERT INTO returning203.inventory AS i(
    sku, product_name, stock, unit_price
)
VALUES (
    'KEYBOARD', 'Bàn phím mới', 2, 360000.00
)
ON CONFLICT (sku) DO UPDATE
SET
    product_name = EXCLUDED.product_name,
    unit_price = EXCLUDED.unit_price,
    updated_at = now()
RETURNING
    i.sku,
    i.product_name,
    i.stock,
    i.unit_price,
    i.updated_at;
```

Ý nghĩa:

- `EXCLUDED.product_name` là giá trị sản phẩm **được đề xuất chèn**.
- `i.product_name` trong RETURNING là giá trị trên hàng đích sau khi câu lệnh thực hiện nhánh insert/update.
- `stock` trong ví dụ không bị ghi đè khi conflict, vì phần `DO UPDATE SET` không thay đổi stock.

Nếu KEYBOARD đã có, câu lệnh cập nhật tên/giá và trả hàng đã cập nhật.

### 14.1. UPSERT không đồng nghĩa luôn thay đổi hàng

Có thể thêm một điều kiện cho nhánh UPDATE:

```sql
INSERT INTO returning203.inventory AS i(
    sku, product_name, stock, unit_price
)
VALUES ('KEYBOARD', 'Bàn phím', 2, 360000.00)
ON CONFLICT (sku) DO UPDATE
SET
    unit_price = EXCLUDED.unit_price,
    updated_at = now()
WHERE i.unit_price IS DISTINCT FROM EXCLUDED.unit_price
RETURNING i.sku, i.unit_price;
```

Nếu KEYBOARD đã tồn tại **và giá giống giá đề xuất**, điều kiện của nhánh DO UPDATE không thỏa. Hàng đó không được cập nhật và **không xuất hiện trong RETURNING**.

Vì vậy, `RETURNING` ở UPSERT phản ánh **những hàng thực sự chèn/cập nhật**, không nhất thiết mọi hàng đầu vào.

### 14.2. Vì sao dùng IS DISTINCT FROM?

`IS DISTINCT FROM` so sánh hai biểu thức theo cách có kết quả TRUE/FALSE rõ ràng kể cả khi một giá trị NULL. Nó hữu ích khi chỉ muốn cập nhật những cột thực sự thay đổi.

Trong schema này `unit_price` NOT NULL, nên khác biệt với `<>` chưa bộc lộ rõ; trong các cột cho phép NULL, `IS DISTINCT FROM` giúp tránh logic ba giá trị gây bất ngờ.

### 14.3. Không ghi đè trạng thái nghiệp vụ trong UPSERT một cách mù quáng

Ví dụ tồn kho, số dư hoặc trạng thái đơn hàng thường **không** nên được upsert bằng cách gán toàn bộ cột từ EXCLUDED, vì một request lặp lại có thể xóa thay đổi mới hơn.

Hãy quyết định cột nào được phép cập nhật, điều kiện trạng thái và chiến lược idempotency dựa trên nghiệp vụ. `ON CONFLICT DO UPDATE` là cơ chế thao tác dữ liệu, không tự định nghĩa chính sách “latest write wins” an toàn.

## 15. Một câu SQL nhiều bước: data-modifying CTE

PostgreSQL cho phép đưa các câu `INSERT`, `UPDATE`, `DELETE` vào `WITH` dưới dạng **data-modifying common table expressions**, và dùng `RETURNING` làm đầu ra cho những bước khác.

Dạng ý tưởng:

```sql
WITH changed AS (
    UPDATE some_table
    SET ...
    WHERE ...
    RETURNING key, new_value
)
SELECT *
FROM changed;
```

Ở đây `changed` không phải bảng thật được lưu lâu dài. Nó là **tập kết quả của RETURNING** trong phạm vi câu SQL hiện tại.

### 15.1. Vì sao data-modifying CTE hữu ích?

Khi cần:

1. Thay đổi hàng trong bảng A.
2. Dùng **chính các hàng đã thay đổi** để chèn một bảng B.
3. Có kết quả trả về từ toàn bộ workflow.

`WITH ... RETURNING` có thể giảm vòng đi lại giữa ứng dụng và database, đồng thời thực hiện những thao tác thuộc cùng một statement **nguyên tử**: nếu statement lỗi và bị rollback thì các thay đổi của statement không được giữ.

### 15.2. Nhưng một statement không thay thế toàn bộ thiết kế transaction

Một DML CTE không tự làm hợp lệ mọi kịch bản kinh doanh. Cần xem:

- Các điều kiện của hàng cha và hàng con.
- Constraint/khóa ngoại.
- Có hành động nào bị **bỏ qua** bằng DO NOTHING làm bước trước vẫn ghi hay không.
- Retry có trừ tồn kho hai lần hay không.
- Có tạo đối tượng ngoài database (email, HTTP, file) không.
- Statement có đang chạy trong transaction lớn hơn có thể rollback không.

**Atomic ở mức database không đồng nghĩa workflow ngoài hệ thống sẽ exactly-once.**

## 16. UPDATE ... RETURNING rồi chèn nhật ký trong cùng statement

Ta muốn trừ 2 sản phẩm BOOK-PG và ghi lại một dòng vào `inventory_movements` **chỉ khi việc trừ tồn kho thành công**.

```sql
WITH reduced_stock AS (
    UPDATE returning203.inventory AS i
    SET
        stock = i.stock - 2,
        updated_at = now()
    WHERE i.sku = 'BOOK-PG'
      AND i.stock >= 2
    RETURNING
        i.sku,
        i.stock AS remaining_stock
)
INSERT INTO returning203.inventory_movements(
    sku,
    stock_delta,
    reason
)
SELECT
    r.sku,
    -2,
    'reservation'
FROM reduced_stock AS r
RETURNING
    movement_id,
    sku,
    stock_delta,
    reason,
    recorded_at;
```

Cách hiểu:

1. CTE `reduced_stock` cố trừ tồn kho một cách có điều kiện.
2. Nếu đủ hàng, nó trả một hàng chứa SKU và số lượng mới.
3. `INSERT ... SELECT FROM reduced_stock` thêm một bản ghi nhật ký cho chính SKU đã được sửa.
4. Nếu không đủ hàng, CTE trả 0 hàng và bước INSERT **không có hàng nguồn**, nên không thêm movement.
5. Nếu việc chèn nhật ký vi phạm constraint hay lỗi, **cả statement thất bại**, thao tác trừ tồn không được commit một phần.

`RETURNING` ở **cuối câu** là của thao tác INSERT vào bảng nhật ký, nên trả các cột của **movement**, không phải tự động các cột tồn kho ở CTE đầu.

### 16.1. Nếu muốn trả số lượng tồn mới cho client

Có thể dùng SELECT ngoài:

```sql
WITH reduced_stock AS (
    UPDATE returning203.inventory AS i
    SET stock = i.stock - 2, updated_at = now()
    WHERE i.sku = 'BOOK-PG'
      AND i.stock >= 2
    RETURNING i.sku, i.stock, i.unit_price
)
SELECT sku, stock AS remaining_stock, unit_price
FROM reduced_stock;
```

Đây là một câu SQL; câu SELECT ngoài đọc **tập RETURNING của CTE**, không cần query đọc bảng inventory lần nữa.

### 16.2. Ghi audit qua trigger hay qua CTE?

- **Trigger audit:** áp dụng trên nhiều đường ghi vào bảng, phù hợp khi mọi thay đổi đều cần ghi log.
- **DML CTE:** diễn đạt rõ một workflow nghiệp vụ cụ thể, ví dụ “trừ tồn do đặt hàng và ghi movement”.
- **Outbox/event log:** phục vụ tích hợp ngoài database; có thể dùng transaction hoặc trigger theo thiết kế.

Không có công cụ nào tự thay thế toàn bộ chính sách audit. Hãy chọn theo nơi cần kiểm soát và khả năng bảo đảm tất cả đường ghi đều tuân thủ.

## 17. Cùng statement: trừ tồn kho rồi tạo đơn hàng

Đây là tình huống điển hình dùng kết quả của `UPDATE RETURNING` làm **nguồn tạo đơn**, không cần đọc lại tồn kho.

Yêu cầu:

> “Chỉ tạo đơn BOOK-PG số lượng 1 nếu khách hàng tồn tại và tồn kho còn ít nhất 1; giá đơn lấy từ hàng inventory đã tham gia cập nhật.”

Ví dụ trong schema lab:

```sql
WITH buyer AS (
    SELECT customer_id
    FROM returning203.customers
    WHERE email = 'an@example.test'
),
reserved AS (
    UPDATE returning203.inventory AS i
    SET
        stock = i.stock - 1,
        updated_at = now()
    WHERE i.sku = 'BOOK-PG'
      AND i.stock >= 1
      AND EXISTS (SELECT 1 FROM buyer)
    RETURNING
        i.sku,
        i.unit_price,
        i.stock AS remaining_stock
),
created_order AS (
    INSERT INTO returning203.orders(
        customer_id, sku, quantity, total_amount,
        status, client_request_id
    )
    SELECT
        b.customer_id,
        r.sku,
        1,
        r.unit_price,
        'NEW',
        'checkout-example-203'
    FROM buyer AS b
    CROSS JOIN reserved AS r
    RETURNING
        order_id,
        customer_id,
        sku,
        quantity,
        total_amount,
        status,
        client_request_id
)
SELECT *
FROM created_order;
```

Điểm quan trọng:

- `buyer` tra cứu khách với `email UNIQUE`.
- `EXISTS (SELECT 1 FROM buyer)` trong UPDATE tránh trừ tồn nếu khách không tồn tại.
- `reserved` chỉ trả hàng nếu UPDATE đủ điều kiện và thực sự giảm tồn.
- `created_order` chỉ có hàng nguồn nếu có buyer và reserved.
- Mã `client_request_id` có UNIQUE. Nếu đã có một đơn với mã đó, lần insert sẽ lỗi unique và **cả statement bị rollback**; tồn kho không bị trừ rồi để lại đơn không tạo thành.
- Kết quả cuối trả **đơn mới thực sự tạo**, không phải chỉ một cờ boolean.

### 17.1. Cẩn trọng nếu thêm ON CONFLICT DO NOTHING vào bước tạo đơn

Một thay đổi tưởng là “an toàn khi retry”:

```sql
-- Không tự thêm nhánh này vào ví dụ trên nếu chưa thiết kế lại workflow:
ON CONFLICT (client_request_id) DO NOTHING
```

Khi request trùng, bước INSERT đơn có thể bị **bỏ qua** thay vì báo lỗi, trong khi CTE `reserved` đã trừ tồn kho. Nếu statement vẫn commit, hệ thống có thể **mất tồn kho mà không tạo đơn mới**.

**Bài học thiết kế:** RETURNING chỉ phản ánh từng thao tác; nó **không tự ràng buộc** rằng mọi DML CTE phải sửa cùng số hàng hoặc mọi thao tác bị bỏ qua sẽ tự rollback.

Để hỗ trợ retry idempotent an toàn, cần cơ chế xác định yêu cầu đã xử lý, điều phối khóa/unique state, và bảo đảm chỉ trừ tồn đúng một lần. Đây là bài toán workflow/transaction, không chỉ thêm `DO NOTHING`.

### 17.2. Không đọc lại bảng được UPDATE trong cùng statement để truyền giá trị

Các data-modifying CTE trong một câu statement hoạt động theo cơ chế snapshot và giao tiếp thay đổi qua **tập RETURNING**. Không nên kỳ vọng một SELECT cùng statement trực tiếp đọc `inventory` sẽ nhất thiết thấy giá trị do một CTE UPDATE khác vừa ghi.

Khi cần `remaining_stock`, dùng `reserved.remaining_stock` từ RETURNING; đó chính là kênh dữ liệu được thiết kế cho trường hợp này.

## 18. DELETE ... RETURNING rồi chuyển vào bảng lưu trữ

Có thể chuyển các bản ghi đã hủy sang bảng lưu trữ trong một statement. Ví dụ tạo bảng:

```sql
CREATE TABLE returning203.orders_archive (
    order_id bigint PRIMARY KEY,
    customer_id bigint NOT NULL,
    sku text NOT NULL,
    quantity integer NOT NULL,
    total_amount numeric(12, 2) NOT NULL,
    status text NOT NULL,
    created_at timestamptz NOT NULL,
    archived_at timestamptz NOT NULL DEFAULT now()
);
```

Giả sử có những đơn `CANCELLED` đủ điều kiện được đưa vào archive theo chính sách lưu trữ. Chuyển trực tiếp:

```sql
WITH removed AS (
    DELETE FROM returning203.orders AS o
    WHERE o.status = 'CANCELLED'
      AND o.created_at < TIMESTAMPTZ '2026-11-01 00:00+07'
    RETURNING
        o.order_id,
        o.customer_id,
        o.sku,
        o.quantity,
        o.total_amount,
        o.status,
        o.created_at
)
INSERT INTO returning203.orders_archive(
    order_id,
    customer_id,
    sku,
    quantity,
    total_amount,
    status,
    created_at
)
SELECT
    r.order_id,
    r.customer_id,
    r.sku,
    r.quantity,
    r.total_amount,
    r.status,
    r.created_at
FROM removed AS r
RETURNING
    order_id,
    status,
    archived_at;
```

Ý nghĩa:

1. DELETE chọn các hàng đã hủy và cũ hơn thời điểm giới hạn.
2. `RETURNING` cung cấp **toàn bộ dữ liệu cần chuyển** sang archive.
3. INSERT vào archive đọc từ tập removed.
4. Nếu INSERT archive lỗi (ví dụ `order_id` đã tồn tại trong archive), statement thất bại, nên việc xóa cũng không được giữ lại như một phần thành công đơn lẻ.

### 18.1. Archive không chỉ là copy hàng

Trong hệ thống thật, quy trình lưu trữ có thể cần:

- Khóa ngoại ở các bảng liên quan.
- Retention policy và quyền truy cập dữ liệu lưu trữ.
- Mã hóa dữ liệu nhạy cảm.
- Lịch sử audit đúng chuẩn.
- Định nghĩa archive nên lưu dữ liệu trước hay sau các trigger.
- Giới hạn batch để không giữ khóa quá lâu.
- Xử lý retry/idempotency.

Ví dụ trên chỉ minh họa cách **truyền dữ liệu qua DELETE RETURNING** trong PostgreSQL.

### 18.2. Trả dữ liệu xóa cho API

Nếu chỉ muốn trả bản ghi bị xóa:

```sql
DELETE FROM returning203.orders
WHERE client_request_id = 'old-cancelled-order-203'
  AND status = 'CANCELLED'
RETURNING order_id, client_request_id, status;
```

Nếu 0 hàng, API cần quyết định trạng thái HTTP hoặc thông báo dựa trên hợp đồng nghiệp vụ; không tự suy ra “đã xóa thành công trước đó”.

## 19. UPDATE ... FROM RETURNING với dữ liệu nguồn

PostgreSQL hỗ trợ `UPDATE ... FROM` khi giá trị mới được tính hoặc lấy từ một nguồn khác.

Giả sử có một bảng giá được gửi từ hệ thống quản lý sản phẩm:

```sql
WITH new_prices(sku, new_price) AS (
    VALUES
        ('BOOK-PG'::text, 125000.00::numeric),
        ('KEYBOARD'::text, 365000.00::numeric)
)
UPDATE returning203.inventory AS i
SET
    unit_price = np.new_price,
    updated_at = now()
FROM new_prices AS np
WHERE i.sku = np.sku
RETURNING
    i.sku,
    i.product_name,
    np.new_price AS submitted_price,
    i.unit_price AS saved_price;
```

Kết quả có các SKU đã thực sự được UPDATE.

### 19.1. Một bẫy lớn của UPDATE ... FROM

Nếu một hàng đích có thể ghép với **nhiều hàng nguồn**, kết quả cập nhật phụ thuộc cách PostgreSQL chọn một hàng ghép, điều mà ứng dụng không nên dựa vào.

Ví dụ bảng giá nguồn có hai giá khác nhau cho cùng một SKU là dữ liệu **không duy nhất**. Cần giải quyết trùng khóa nguồn bằng constraint, grouping hoặc chọn một bản ghi đúng nghiệp vụ **trước UPDATE**.

`RETURNING` sẽ trả hàng đích đã được thay đổi, nhưng không biến một phép JOIN mơ hồ thành lựa chọn giá nghiệp vụ đúng.

### 19.2. RETURNING trên nguồn FROM

Trong các trường hợp phù hợp, biểu thức `RETURNING` có thể tham chiếu các cột của bảng nguồn `FROM`, ví dụ `np.new_price` trong truy vấn trên.

Khi có nhiều bảng cùng tên cột, hãy dùng alias rõ ràng để tránh nhập nhằng giá đề xuất và giá đã lưu.

## 20. Đếm hàng thay đổi bằng RETURNING

Nếu mục tiêu là biết chính xác **bao nhiêu hàng được cập nhật** và muốn lấy thêm các chỉ số, có thể dùng:

```sql
WITH updated AS (
    UPDATE returning203.inventory AS i
    SET updated_at = now()
    WHERE i.stock > 0
    RETURNING i.sku, i.stock
)
SELECT
    COUNT(*) AS changed_count,
    COALESCE(SUM(stock), 0) AS remaining_total_stock
FROM updated;
```

### 20.1. COUNT(*) ngoài CTE khác số hàng được hỏi trong SQL client

Với `UPDATE ... RETURNING` thuần túy, một driver thường nhận result set có mỗi hàng ứng với một bản ghi bị thay đổi. Với CTE tổng hợp như trên, result set ngoài cùng có **một hàng** mang `changed_count`, kể cả khi `changed_count = 0`.

Điều này rất quan trọng khi code mong “0 result rows” để xác định thao tác không tác động gì. Bọc trong aggregate sẽ làm quy ước kiểm tra thay đổi, vì `SELECT COUNT(*)` thường trả một hàng.

### 20.2. Không phải mọi UPDATE đều làm giá trị khác trước

Câu:

```sql
UPDATE returning203.inventory
SET stock = stock
WHERE sku = 'BOOK-PG'
RETURNING sku, stock;
```

vẫn là một `UPDATE` đối với hàng phù hợp. Nó có thể kích hoạt xử lý update/trigger và trả hàng, dù giá trị `stock` sau update bằng trước.

Vì vậy “hàng được UPDATE” không nhất thiết nghĩa “giá trị business khác trước”. Nếu ứng dụng chỉ muốn cập nhật khi giá trị đổi, hãy đưa điều kiện phù hợp vào WHERE, ví dụ:

```sql
UPDATE returning203.inventory AS i
SET unit_price = 125000
WHERE i.sku = 'BOOK-PG'
  AND i.unit_price IS DISTINCT FROM 125000::numeric
RETURNING i.sku, i.unit_price;
```

## 21. Số hàng kết quả và các tình huống biên

Bảng sau giúp phân biệt “không có gì được trả” theo từng câu lệnh:

| Kịch bản | DML có tác động? | RETURNING |
|---|---|---|
| INSERT một hàng hợp lệ | Có | 1 hàng |
| INSERT ba hàng hợp lệ | Có | 3 hàng |
| UPDATE WHERE tìm 0 hàng | Không | 0 hàng |
| UPDATE WHERE tìm 5 hàng | Có | 5 hàng |
| DELETE WHERE tìm 0 hàng | Không | 0 hàng |
| DELETE WHERE xóa 2 hàng | Có | 2 hàng |
| UPSERT DO NOTHING gặp conflict | Không chèn hàng xung đột | 0 hàng cho hàng đó |
| UPSERT DO UPDATE và nhánh WHERE không thỏa | Không UPDATE hàng xung đột đó | 0 hàng cho hàng đó |
| CTE UPDATE RETURNING rồi SELECT COUNT(*) | Tùy UPDATE | Một hàng số đếm |
| DML lỗi constraint/permission | Statement thất bại | Không phải result set thành công đáng dùng |

### 21.1. RETURNING trả các hàng được thay đổi, không trả nguyên bảng

Ví dụ inventory có ba SKU, nhưng chỉ BOOK-PG thỏa WHERE:

```sql
UPDATE returning203.inventory
SET updated_at = now()
WHERE sku = 'BOOK-PG'
RETURNING sku;
```

Nếu thành công, tập RETURNING chỉ chứa BOOK-PG, không tự kèm KEYBOARD/MOUSE.

### 21.2. Một điều kiện WHERE bỏ sót có thể phá dữ liệu

```sql
-- Không chạy nếu chưa chủ ý cập nhật toàn bộ bảng:
UPDATE returning203.inventory
SET unit_price = 100000
RETURNING sku, unit_price;
```

Câu này không có WHERE nên có thể sửa **mọi sản phẩm**. `RETURNING` không tự giới hạn phạm vi; nó chỉ làm hiển thị những hàng đã bị sửa.

Với UPDATE/DELETE có rủi ro cao, xác định điều kiện đúng, thử trong transaction lab và cân nhắc quy trình phê duyệt/thao tác theo batch.

## 22. RETURNING và trigger/default/generated columns

Kết quả `RETURNING` có thể phản ánh các giá trị do database tự tính:

- `IDENTITY` hoặc giá trị sequence được gán.
- `DEFAULT`.
- Cột generated được PostgreSQL hỗ trợ.
- Giá trị được thay đổi bởi trigger thích hợp trước khi hàng được ghi.

Ví dụ:

```sql
CREATE TABLE returning203.line_items_demo (
    line_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    quantity integer NOT NULL CHECK (quantity > 0),
    unit_price numeric(12, 2) NOT NULL,
    line_total numeric(14, 2)
        GENERATED ALWAYS AS (quantity * unit_price) STORED
);
```

Chèn:

```sql
INSERT INTO returning203.line_items_demo(
    quantity, unit_price
)
VALUES (3, 120000.00)
RETURNING
    line_id,
    quantity,
    unit_price,
    line_total;
```

Kết quả có `line_total = 360000.00`, không cần ứng dụng tính lại rồi SELECT lần nữa.

### 22.1. Có trigger thì cần hiểu kết quả thực tế

Một row-level `BEFORE INSERT/UPDATE` trigger có thể điều chỉnh dữ liệu hàng thông qua `NEW`. Trong những tình huống đó, `RETURNING` phản ánh hàng được ghi sau các thay đổi tương ứng của trigger.

Tuy nhiên:

- `RETURNING` không tự đưa ra báo cáo mọi side effect của mọi trigger.
- Một `AFTER` trigger có thể chèn bảng nhật ký hoặc thực hiện logic khác mà không trở thành cột trong RETURNING.
- Nếu trigger dẫn tới exception, statement có thể thất bại.
- Không dùng `RETURNING` thay thế cơ chế audit bắt buộc.

### 22.2. Có nên tin DEFAULT now() là “thời điểm cuối cùng”?

`now()` trong PostgreSQL thường biểu diễn thời điểm bắt đầu transaction, không phải đồng hồ thay đổi tại từng lệnh. Nếu giao dịch kéo dài, nhiều hàng có thể nhận cùng timestamp `now()`.

Nếu yêu cầu nghiệp vụ cần một timestamp ở thời điểm đánh giá tức thời, cân nhắc `clock_timestamp()` và hiểu tính biến đổi của nó. Nhưng dù timestamp được RETURNING, **transaction vẫn có thể rollback**.

## 23. Transaction: RETURNING không đồng nghĩa commit

Một ví dụ cho thấy khác biệt:

```sql
BEGIN;

INSERT INTO returning203.customers(email, full_name)
VALUES ('rollback@example.test', 'Khách test rollback')
RETURNING customer_id, email;

ROLLBACK;
```

Câu INSERT có thể trả ID trước khi rollback. Nhưng sau `ROLLBACK`, hàng không tồn tại trong database.

### 23.1. Hệ quả trong thiết kế API

Không nên:

1. Bắt đầu transaction.
2. INSERT RETURNING ID.
3. Gửi email xác nhận hoặc phát event ra hệ thống ngoài.
4. Transaction bị rollback.

Khi đó người dùng có thể nhận thông báo về một đối tượng chưa từng được commit.

Nếu cần phối hợp hiệu ứng ngoài DB, cân nhắc **transactional outbox**: trong cùng transaction ghi bản ghi nghiệp vụ và bản ghi outbox, chỉ publish sau commit qua worker. RETURNING hỗ trợ lấy ID để ghi outbox, nhưng không tự bảo đảm chuyển phát exactly-once.

### 23.2. Gaps trong identity vẫn có thể xuất hiện

Dù hàng được rollback, identity/sequence đã cấp giá trị có thể không được trả lại. Không dựa vào chuỗi ID liên tục để suy ra các transaction đã commit.

### 23.3. SAVEPOINT và lỗi constraint

Trong transaction thủ công, nếu một statement lỗi, transaction thường vào trạng thái lỗi cho tới khi `ROLLBACK` hoặc rollback về savepoint phù hợp. `RETURNING` không làm lỗi constraint trở nên có thể bỏ qua.

Một workflow API nên để transaction manager của ứng dụng xử lý rollback đúng, nhất là khi câu DML có nhiều bước.

## 24. RETURNING và concurrency: đúng giá trị của thao tác, không phải ảnh chụp vĩnh viễn

Tưởng tượng hai request giảm tồn kho của cùng SKU.

Một câu:

```sql
UPDATE returning203.inventory
SET stock = stock - 1
WHERE sku = 'BOOK-PG'
  AND stock >= 1
RETURNING sku, stock;
```

trả số tồn **sau chính UPDATE đó**. Nếu request khác sửa hàng sau khi transaction của bạn commit, kết quả RETURNING không còn đại diện cho tồn kho **hiện tại ở mọi thời điểm tiếp theo**.

Đây là điểm cần diễn giải đúng khi trả API:

> “Sau thao tác đặt hàng này, tồn kho ghi nhận là 3.”

khác:

> “Tồn kho chắc chắn luôn là 3 cho tới khi người dùng refresh trang.”

### 24.1. Các mức isolation khác nhau

Ở `READ COMMITTED`, những transaction cạnh tranh cập nhật cùng hàng được kiểm soát qua khóa và đánh giá lại điều kiện cần thiết. Ở `REPEATABLE READ` hoặc `SERIALIZABLE`, một transaction có thể gặp lỗi serialization khi có cạnh tranh, tùy tình huống.

Ứng dụng phải:

- Bắt các SQLSTATE lỗi giao dịch phù hợp.
- Rollback transaction thất bại.
- Retry **toàn transaction** khi có chính sách hợp lệ, không chỉ chạy lại một statement đã tách khỏi ngữ cảnh.
- Dùng idempotency key cho các yêu cầu có thể được gửi lại.
- Không giả định RETURNING có thể bỏ qua lock hoặc xung đột concurrency.

### 24.2. RETURNING có tự LOCK hàng không?

`UPDATE` và `DELETE` phải phối hợp khóa/MVCC để sửa hàng; `RETURNING` chỉ là **cách lấy kết quả**, không phải một lệnh khóa riêng. Nếu muốn khóa một tập hàng để thực hiện nhiều bước sau đó trong cùng transaction, cân nhắc cơ chế khóa phù hợp như `SELECT ... FOR UPDATE` theo thiết kế, nhưng không lạm dụng SELECT rồi UPDATE khi một UPDATE có điều kiện đã đáp ứng nghiệp vụ.

## 25. Data-modifying CTE: nguyên tắc snapshot và tránh sửa cùng hàng hai lần

Một câu có nhiều DML CTE là công cụ mạnh, nhưng cần hiểu các quy tắc:

1. Các DML CTE trong một statement được thực thi với ngữ nghĩa **cùng snapshot**; thứ tự vật lý giữa những DML sibling không phải một cơ chế điều phối mà ứng dụng được phép dựa vào.
2. **RETURNING** là kênh truyền giá trị những hàng được sửa giữa các thành phần của statement.
3. Không nên cố sửa **cùng một hàng hai lần** trong một statement qua nhiều CTE; kết quả của những tình huống sửa trùng như vậy không được bảo đảm theo cách có thể dùng làm logic nghiệp vụ.
4. DML CTE có thể được thực thi ngay cả khi kết quả RETURNING của nó không được đọc, theo quy tắc thực thi data-modifying statements; không nghĩ “không SELECT FROM changed thì UPDATE không chạy”.
5. Nếu một phần của statement phát sinh exception, toàn statement thất bại thay vì commit những thay đổi con như thành công độc lập.
6. Sử dụng `RETURNING` để truyền các giá trị đã thay đổi, thay vì đọc lại bảng cơ sở với hy vọng nhìn thấy tác động của sibling CTE.

### 25.1. Mẫu không nên dùng

```sql
-- Khuôn mẫu minh họa một thiết kế có rủi ro:
WITH first_change AS (
    UPDATE inventory
    SET stock = stock - 1
    WHERE sku = 'BOOK-PG'
    RETURNING sku
),
second_change AS (
    UPDATE inventory
    SET stock = stock - 1
    WHERE sku = 'BOOK-PG'
    RETURNING sku
)
SELECT *
FROM first_change;
```

Vấn đề là **hai DML cùng muốn sửa hàng inventory của cùng SKU** trong một statement, không phải thiếu `RETURNING`.

Nếu muốn trừ 2, hãy viết **một UPDATE trừ 2** với điều kiện đủ tồn; nếu muốn trừ cho hai request khác nhau, cần workflow transaction/đồng bộ phù hợp thay vì cùng lúc sửa hai lần một hàng qua sibling CTE.

### 25.2. Tách nhiều statement trong transaction cũng hợp lệ

Không bắt buộc mọi workflow phải viết một câu SQL rất dài. Một transaction gồm các statement riêng có thể rõ hơn khi cần:

- Kiểm tra quyền/phê duyệt.
- Đọc dữ liệu trả về từ statement đầu.
- Tính quyết định logic ở application.
- Ghi các bảng liên quan.
- Trả API sau commit.

Dùng `RETURNING` phù hợp trong từng statement. Một câu SQL ít round trip không tự động tốt hơn một transaction rõ ràng, an toàn và dễ kiểm thử.

## 26. RETURNING với quyền truy cập và RLS

`RETURNING` có thể tiết lộ dữ liệu của những cột vừa ghi/xóa/cập nhật. Vì vậy, nó phải tuân thủ quyền SQL và các chính sách truy cập của database.

### 26.1. Quyền cột được đọc trong RETURNING

Ngoài quyền `INSERT`, `UPDATE` hoặc `DELETE` phù hợp, ứng dụng có thể cần quyền `SELECT` trên các cột được tham chiếu trong `RETURNING` hoặc trong điều kiện đọc.

Ví dụ một role được phép cập nhật trạng thái nhưng không được đọc một cột nhạy cảm thì không nên giả định có thể:

```sql
UPDATE some_table
SET status = 'DONE'
WHERE id = 123
RETURNING secret_token;
```

mà không bị database kiểm tra quyền tương ứng.

### 26.2. RLS ảnh hưởng đến hàng nào được sửa/trả

Row-Level Security (RLS) có thể hạn chế những hàng một role được phép nhìn thấy hoặc sửa. Khi policy có hiệu lực, UPDATE/DELETE có thể không tác động những hàng ngoài phạm vi role; INSERT có thể bị kiểm tra policy `WITH CHECK`.

`RETURNING` không phải phương tiện vượt RLS. Kết quả có thể rỗng do **quyền hoặc policy**, không chỉ vì bản ghi không tồn tại.

Nếu API cần phân biệt “404 không có tài nguyên” với “403 không có quyền”, phải thiết kế hợp đồng bảo mật cẩn thận; tiết lộ sự tồn tại của hàng ngoài tenant cũng có thể là vấn đề an ninh.

### 26.3. Tránh RETURNING * trên bảng chứa thông tin nhạy cảm

Một bảng người dùng có thể chứa email, số điện thoại, hash mật khẩu, thông tin nội bộ. Ở phần API, nên:

```sql
RETURNING user_id, display_name, created_at
```

thay vì:

```sql
RETURNING *
```

Điều này hạn chế dữ liệu trả về và giúp hợp đồng API ổn định khi schema thêm cột.

## 27. JDBC/Java: đọc ResultSet của câu DML RETURNING

Với PostgreSQL JDBC, một statement có `RETURNING` có result set. Có thể dùng `PreparedStatement.executeQuery()` để đọc kết quả.

Ví dụ giảm tồn kho có điều kiện:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public class InventoryRepository {
    public Integer reserve(
            Connection connection,
            String sku,
            int quantity) throws SQLException {

        if (quantity <= 0) {
            throw new IllegalArgumentException(
                "quantity phải lớn hơn 0");
        }

        String sql = """
            UPDATE returning203.inventory
            SET stock = stock - ?,
                updated_at = now()
            WHERE sku = ?
              AND stock >= ?
            RETURNING stock
            """;

        try (PreparedStatement ps =
                 connection.prepareStatement(sql)) {

            ps.setInt(1, quantity);
            ps.setString(2, sku);
            ps.setInt(3, quantity);

            try (ResultSet rs = ps.executeQuery()) {
                if (rs.next()) {
                    return rs.getInt("stock");
                }
                return null;
            }
        }
    }
}
```

Ý nghĩa:

- Kết quả `Integer` là tồn kho sau UPDATE nếu có hàng.
- `null` ở Java trong ví dụ nghĩa là **0 hàng RETURNING**, không phải tồn kho SQL NULL; cột `stock` được khai báo `NOT NULL`.
- Chỗ gọi phải quyết định trả lỗi thiếu hàng/không có SKU ra sao.
- Nếu connection nằm trong transaction thủ công, phần commit/rollback vẫn là trách nhiệm của transaction manager.

### 27.1. Có nên dùng executeUpdate()?

Thông thường `executeUpdate()` được dùng cho DML **không trả result set**. Với câu PostgreSQL DML có `RETURNING`, nên sử dụng cách API driver hỗ trợ việc đọc kết quả, ví dụ `executeQuery()` hoặc `execute()` rồi lấy ResultSet.

Không viết code `executeUpdate()` xong mong có thể lấy trực tiếp các cột RETURNING như kết quả SELECT nếu driver/API không cung cấp đường truy cập tương ứng.

### 27.2. Nhận ID do INSERT sinh

```java
String sql = """
    INSERT INTO returning203.customers(email, full_name)
    VALUES (?, ?)
    RETURNING customer_id
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, "jdbc@example.test");
    ps.setString(2, "Khách JDBC");

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            long id = rs.getLong("customer_id");
            // Dùng id thực tế trong workflow đã thiết kế.
        }
    }
}
```

Ví dụ Java giả định có driver PostgreSQL JDBC, datasource và connection hợp lệ. Trong hệ thống thật nên dùng email độc lập theo fixture để tránh lỗi UNIQUE, đóng transaction đúng lúc và trả API sau commit.

### 27.3. RETURNING và getGeneratedKeys()

JDBC cũng có cơ chế `getGeneratedKeys()`, và PostgreSQL JDBC có hỗ trợ tương ứng. Nếu bạn cần chủ động lựa chọn **nhiều cột** hoặc biểu thức trả về, mệnh đề `RETURNING` tường minh thường dễ thấy và dễ kiểm soát.

Không nên sử dụng đồng thời hai cơ chế theo cách không rõ hợp đồng của driver/framework. Chọn cách được dự án chuẩn hóa và kiểm thử kết quả.

### 27.4. Spring/JdbcTemplate

Khi một truy vấn có `RETURNING`, cần API có khả năng đọc row mapper/result set, thay vì mặc định dùng phương thức update chỉ trả một số nguyên.

Ví dụ ý tưởng:

```java
String sql = """
    UPDATE returning203.inventory
    SET stock = stock - ?
    WHERE sku = ? AND stock >= ?
    RETURNING sku, stock
    """;

List<InventoryResult> rows = jdbcTemplate.query(
    sql,
    (rs, rowNum) -> new InventoryResult(
        rs.getString("sku"),
        rs.getInt("stock")
    ),
    quantity, sku, quantity
);
```

`InventoryResult` là kiểu dữ liệu do ứng dụng định nghĩa, đoạn trên là ví dụ tích hợp. Với service thật, cần xử lý `rows.isEmpty()`, mapping transaction và SQL exception.

## 28. RETURNING trong API: mã lỗi và phản hồi phù hợp

Giả sử API:

```text
POST /inventory/{sku}/reserve
{
  "quantity": 2
}
```

Có thể map kết quả:

- **1 hàng RETURNING** → cập nhật thành công, trả SKU và số tồn còn lại.
- **0 hàng RETURNING** → không tìm thấy hàng phù hợp điều kiện; cần phân loại nguyên nhân để trả mã lỗi nghiệp vụ thích hợp.
- **Constraint violation** → lỗi nghiệp vụ hoặc lỗi toàn vẹn cần xử lý theo SQLSTATE.
- **Serialization/deadlock/timeout** → chính sách retry có kiểm soát.
- **Commit thất bại** → không thể coi result set RETURNING đã đọc là một thành công bền vững.

Ví dụ phản hồi thành công minh họa:

```json
{
  "sku": "BOOK-PG",
  "reservedQuantity": 2,
  "remainingStock": 3
}
```

Số tồn này là kết quả **sau thao tác**, không bảo đảm giữ nguyên khi các request khác tiếp tục cập nhật.

### 28.1. Không để client tin rằng nhận ID nghĩa là giao dịch đã tồn tại vĩnh viễn

Nếu request vẫn đang nằm trong transaction chưa commit, việc trả response thành công sớm có thể gây sai lệch. API nên xác định rõ transaction boundary và chỉ xác nhận thao tác theo chính sách sau commit thành công.

### 28.2. Đừng tiết lộ nội dung lỗi DB không cần thiết

Thông điệp của PostgreSQL có thể chứa tên constraint, giá trị khóa, thông tin hàng hoặc tên bảng. Thông tin chi tiết hữu ích cho log nội bộ, nhưng response người dùng nên được thiết kế an toàn theo quyền và ngữ nghĩa nghiệp vụ.

## 29. RETURNING và idempotency: chỗ dễ mắc sai lầm

Một API có thể nhận lại cùng yêu cầu do timeout hoặc client retry. Dùng `client_request_id UNIQUE` giúp nhận biết một yêu cầu đã từng được tạo, nhưng vẫn cần xử lý nhiều tình huống:

- Client chưa biết request đầu đã commit hay chưa.
- Request đầu có thể commit rồi nhưng response thất lạc.
- Hai request cùng khóa idempotency có thể đến **đồng thời**.
- Client có thể gửi cùng khóa nhưng payload khác.
- Workflow có thể sửa nhiều bảng như tồn kho, đơn hàng và điểm thưởng.

### 29.1. Bẫy “DO NOTHING rồi xem RETURNING rỗng là success”

Ví dụ:

```sql
INSERT INTO returning203.orders(...)
VALUES (...)
ON CONFLICT (client_request_id) DO NOTHING
RETURNING order_id;
```

Khi conflict, kết quả rỗng. Nó **không chứa order_id của đơn trước đó**, và không tự xác nhận payload khớp yêu cầu đầu.

Nếu dùng kết quả này để quyết định có trừ tồn lần nữa hay không, rất dễ tạo bug.

### 29.2. Một hướng thiết kế đúng hơn

Tùy ứng dụng, có thể:

1. Định nghĩa khóa idempotency gắn với tenant/user và phạm vi nghiệp vụ.
2. Lưu payload hash/status của yêu cầu đã được xử lý.
3. Kiểm soát concurrency qua khóa duy nhất/transaction.
4. Khi request trùng, lấy lại **kết quả của yêu cầu cũ** thay vì lặp lại mọi side effect.
5. Chỉ trừ tồn và tạo đơn đúng một lần trong transaction an toàn.
6. Nếu commit thất bại, cho phép retry theo trạng thái quan sát được.

`RETURNING` rất hữu ích để lấy ID/kết quả chính xác, nhưng không tự thực hiện các bước điều phối này.

## 30. Phân biệt RETURNING với các cách lấy dữ liệu khác

| Cách làm | Mục đích | Rủi ro/giới hạn |
|---|---|---|
| `INSERT ... RETURNING id` | Lấy ID của hàng mới | Không bảo đảm commit nếu transaction còn mở |
| `SELECT MAX(id)` | Xem ID lớn nhất toàn bảng | Không biết đó là hàng vừa insert, sai dưới concurrency |
| `SELECT currval(...)` | Lấy giá trị sequence gần nhất trong session cho sequence cụ thể | Cần biết sequence và đã gọi trong session; không tự thay thế đa cột RETURNING |
| `SELECT sau UPDATE` | Đọc trạng thái bảng ở thời điểm query | Có thể nhìn thấy thay đổi tiếp theo nếu là statement/transaction khác |
| `UPDATE ... RETURNING stock` | Lấy tồn sau chính UPDATE | Kết quả không phải trạng thái vĩnh viễn |
| `DELETE ... RETURNING ...` | Lấy hàng bị xóa | Không tự ghi audit hoặc backup |
| `WITH changed AS (UPDATE ... RETURNING) SELECT ...` | Biến hàng thay đổi thành nguồn cho SELECT | Cần hiểu snapshot/DML CTE |
| `INSERT ... ON CONFLICT DO NOTHING RETURNING` | Biết hàng nào thực sự được chèn | Hàng xung đột không được trả về |
| `INSERT ... ON CONFLICT DO UPDATE RETURNING` | Biết hàng đã chèn hoặc cập nhật | WHERE của DO UPDATE có thể khiến hàng conflict không được sửa/trả |
| `getGeneratedKeys()` qua JDBC | Lấy khóa sinh theo API driver | Hợp đồng driver/framework khác với RETURNING tường minh |

### 30.1. RETURNING khác SELECT có FOR UPDATE

`SELECT ... FOR UPDATE` khóa những hàng đã chọn để hỗ trợ transaction với nhiều bước. Nó **không tự sửa dữ liệu**. Ngược lại, `UPDATE ... RETURNING` vừa sửa hàng vừa trả kết quả của thay đổi.

Không chọn `FOR UPDATE` chỉ vì muốn nhận giá trị mới: một UPDATE có điều kiện và RETURNING có thể ngắn gọn hơn nếu nghiệp vụ chỉ cần một thay đổi nguyên tử.

## 31. Những lỗi thường gặp

### 31.1. Chèn dữ liệu rồi SELECT MAX(id)

ID lớn nhất có thể thuộc giao dịch khác. **Sửa:** `INSERT ... RETURNING id`.

### 31.2. Nghĩ RETURNING trả mọi hàng thỏa SELECT nguồn

`INSERT ... SELECT ... ON CONFLICT DO NOTHING RETURNING ...` chỉ trả những hàng thực sự được chèn. Hàng đầu vào bị bỏ qua không xuất hiện.

### 31.3. Coi 0 hàng RETURNING là thành công

Một UPDATE trạng thái có 0 hàng có thể do hàng không tồn tại, trạng thái sai, điều kiện cạnh tranh không còn thỏa hoặc RLS. **Sửa:** định nghĩa rõ ý nghĩa 0 hàng theo từng API.

### 31.4. Quên WHERE trong UPDATE/DELETE

`RETURNING` không ngăn update/delete toàn bảng. **Sửa:** giới hạn đúng tập hàng được tác động; thao tác thử nghiệm nên đặt trong transaction lab.

### 31.5. Dùng RETURNING * rồi trả nguyên result cho client

Có thể làm lộ cột nhạy cảm và gây phụ thuộc schema. **Sửa:** liệt kê cột cụ thể.

### 31.6. Coi ID đã trả về là dữ liệu đã commit

Transaction có thể rollback sau RETURNING. **Sửa:** xác định commit boundary trước khi xác nhận API.

### 31.7. Dùng DO NOTHING trong bước tạo đơn sau khi đã trừ tồn

Khi đơn trùng khóa idempotency, INSERT bỏ qua nhưng tồn có thể đã giảm. **Sửa:** thiết kế điều phối retry theo transaction và trạng thái yêu cầu.

### 31.8. Mong DO NOTHING RETURNING trả hàng cũ

Nó không trả hàng bị bỏ qua. **Sửa:** nếu cần hàng hiện có, thiết kế đường đọc bổ sung an toàn hoặc cơ chế upsert phù hợp.

### 31.9. Dùng UPDATE FROM với nhiều hàng nguồn cho một khóa

PostgreSQL không bảo đảm chọn hàng nguồn theo logic nghiệp vụ mong muốn. **Sửa:** chuẩn hóa/khử trùng theo khóa nguồn trước khi UPDATE.

### 31.10. Dùng nhiều sibling DML CTE cùng sửa một hàng

Không có bảo đảm đáng tin cậy về việc sửa cùng hàng hai lần trong một statement. **Sửa:** gộp phép tính vào một UPDATE hoặc dùng transaction nhiều statement có kiểm soát.

### 31.11. SELECT lại bảng gốc trong cùng statement để quan sát CTE thay đổi

Sibling CTE hoạt động theo ngữ nghĩa snapshot; kết quả sửa nên được truyền qua `RETURNING`, không đọc lại bảng đích rồi kỳ vọng thấy mọi thay đổi.

### 31.12. Dùng công thức suy ra old value như bằng chứng tuyệt đối

`RETURNING stock + quantity` chỉ suy ra giá trị trước khi trừ nếu đúng giả định và không có yếu tố điều chỉnh khác. **Sửa:** cần log old/new chính xác thì dùng cơ chế phiên bản/trigger hoặc kỹ thuật được hỗ trợ đúng server.

### 31.13. Không xử lý lỗi khi JDBC đọc result set

Result set có thể rỗng. DML có thể lỗi unique/check/foreign key, serialization hoặc timeout. **Sửa:** try-with-resources, mapping kết quả, transaction rollback và chính sách retry.

### 31.14. Coi RETURNING là hàng đợi sự kiện ngoài hệ thống

RETURNING trả dữ liệu về client; nó không tự chuyển sự kiện ra Kafka/email. **Sửa:** dùng outbox/event infrastructure khi cần.

### 31.15. Lấy cả dữ liệu nhạy cảm của hàng DELETE để log công khai

Kết quả DELETE RETURNING có thể chứa dữ liệu cá nhân. **Sửa:** giới hạn trường, áp dụng retention và phân quyền audit.

### 31.16. Coi RETURNING luôn có thứ tự

Không tự giả định thứ tự result set DML. **Sửa:** bọc DML trong CTE rồi SELECT ORDER BY nếu cần thứ tự ổn định.

## 32. Bài tập thực hành có lời giải

Các bài tập dưới đây giả định schema lab `returning203` đã được tạo. Nếu thực hiện lần lượt, những lệnh DML có thể thay đổi fixture; hãy dùng SKU/khóa yêu cầu riêng, chạy trong transaction để rollback khi học, hoặc kiểm tra dữ liệu hiện tại trước khi áp dụng.

### Bài 1. Tạo khách và trả ID thực tế

**Yêu cầu:** tạo khách `qa-203@example.test`, không đoán ID.

```sql
INSERT INTO returning203.customers(email, full_name)
VALUES ('qa-203@example.test', 'Khách QA')
RETURNING customer_id, email, created_at;
```

**Lời giải:** dùng `INSERT ... RETURNING`; ID trả về là giá trị thực do PostgreSQL gán cho hàng chèn.

### Bài 2. Vì sao SELECT MAX(customer_id) không phù hợp?

**Lời giải:** ID lớn nhất có thể thuộc request/giao dịch khác; sequence không cam kết liên tục hoặc đồng bộ với thứ tự commit. RETURNING gắn ID với chính hàng được insert.

### Bài 3. Chèn hai SKU mới, nhận cả hai mã

```sql
INSERT INTO returning203.inventory(
    sku, product_name, stock, unit_price
)
VALUES
    ('PEN-203', 'Bút', 10, 10000),
    ('NOTE-203', 'Sổ ghi chú', 5, 25000)
RETURNING sku, product_name, stock, unit_price;
```

**Lời giải:** nếu cả hai hàng được chèn thành công, RETURNING trả hai hàng. Không tự giả định thứ tự kết quả nếu không sắp xếp.

### Bài 4. Cập nhật giá và nhận giá mới

```sql
UPDATE returning203.inventory
SET unit_price = 115000, updated_at = now()
WHERE sku = 'BOOK-PG'
RETURNING sku, unit_price AS new_price;
```

**Lời giải:** giá mới được trả từ chính UPDATE; không cần SELECT lại.

### Bài 5. Trừ tồn kho chỉ khi có đủ

```sql
UPDATE returning203.inventory
SET stock = stock - 2
WHERE sku = 'BOOK-PG'
  AND stock >= 2
RETURNING sku, stock AS remaining_stock;
```

**Lời giải:** trả một hàng nếu đủ tồn; 0 hàng nếu không có hàng thỏa điều kiện. Cần phân biệt SKU không tồn tại và thiếu tồn nếu API yêu cầu.

### Bài 6. Nếu hai transaction cùng muốn trừ 4 từ stock 5?

**Lời giải:** với mẫu `UPDATE ... WHERE stock >= 4 RETURNING ...`, hai thao tác cạnh tranh trên cùng hàng không thể đều trừ 4 thành công dưới điều kiện được đánh giá đúng. Một thao tác sẽ không còn thỏa điều kiện hoặc gặp lỗi giao dịch theo mức cô lập/tình huống.

### Bài 7. Xóa hàng và nhận dữ liệu xóa

```sql
DELETE FROM returning203.orders
WHERE client_request_id = 'unused-cancelled-203'
  AND status = 'CANCELLED'
RETURNING order_id, sku, quantity, status;
```

**Lời giải:** nếu có hàng phù hợp, PostgreSQL trả giá trị của hàng bị xóa; nếu không có, trả 0 hàng. Không cần SELECT trước.

### Bài 8. UPSERT DO NOTHING và RETURNING

```sql
INSERT INTO returning203.inventory(
    sku, product_name, stock, unit_price
)
VALUES ('BOOK-PG', 'Sách', 5, 120000)
ON CONFLICT (sku) DO NOTHING
RETURNING sku;
```

**Đáp án:** trong dữ liệu mẫu BOOK-PG đã tồn tại, nên 0 hàng được trả. Điều này không trả giá trị hàng cũ.

### Bài 9. UPSERT giá có điều kiện

```sql
INSERT INTO returning203.inventory AS i(
    sku, product_name, stock, unit_price
)
VALUES ('KEYBOARD', 'Bàn phím', 2, 350000)
ON CONFLICT (sku) DO UPDATE
SET unit_price = EXCLUDED.unit_price
WHERE i.unit_price IS DISTINCT FROM EXCLUDED.unit_price
RETURNING i.sku, i.unit_price;
```

**Lời giải:** nếu giá đang bằng giá đề xuất, nhánh UPDATE bị bỏ qua và RETURNING rỗng. Nếu khác, hàng được cập nhật và trả về.

### Bài 10. Chỉ trả số hàng đã UPDATE

```sql
WITH changed AS (
    UPDATE returning203.inventory
    SET updated_at = now()
    WHERE stock > 0
    RETURNING sku
)
SELECT COUNT(*) AS changed_count
FROM changed;
```

**Lời giải:** SELECT ngoài luôn trả một hàng COUNT; số đếm cho biết bao nhiêu hàng inventory được UPDATE.

### Bài 11. Sau khi UPDATE CTE, nên đọc gì?

**Câu hỏi:** nếu cần số tồn mới từ `UPDATE ... RETURNING stock`, nên SELECT lại bảng inventory hay SELECT từ CTE?

**Đáp án:** trong cùng statement, đọc **tập RETURNING của CTE** để dùng giá trị mới. Không dựa vào việc đọc lại bảng cơ sở với kỳ vọng nhìn thấy các thay đổi sibling theo thứ tự mong muốn.

### Bài 12. Tạo movement chỉ khi tồn kho giảm thành công

```sql
WITH changed AS (
    UPDATE returning203.inventory
    SET stock = stock - 1
    WHERE sku = 'KEYBOARD'
      AND stock >= 1
    RETURNING sku
)
INSERT INTO returning203.inventory_movements(
    sku, stock_delta, reason
)
SELECT sku, -1, 'practice-203'
FROM changed
RETURNING movement_id, sku, stock_delta;
```

**Lời giải:** nếu UPDATE 0 hàng, không có movement nào được insert. Nếu INSERT lỗi, cả statement thất bại.

### Bài 13. Tại sao không thêm DO NOTHING vào insert đơn một cách mù quáng?

**Đáp án:** nếu bước trước đã giảm tồn kho mà insert đơn gặp conflict và bị DO NOTHING bỏ qua, transaction có thể commit giảm tồn nhưng không tạo đơn mới. Phải thiết kế idempotency và điều kiện phối hợp giữa các bước.

### Bài 14. Nhận default/generation từ database

```sql
INSERT INTO returning203.job_tokens
DEFAULT VALUES
RETURNING token_id, token_state, generated_at;
```

**Lời giải:** RETURNING lấy ID/timestamp/state do database gán, không cần tính ở client.

### Bài 15. Tính tổng sau UPDATE từ tập RETURNING

```sql
WITH changed AS (
    UPDATE returning203.inventory
    SET updated_at = now()
    WHERE stock >= 1
    RETURNING sku, stock
)
SELECT
    COUNT(*) AS products_changed,
    COALESCE(SUM(stock),0) AS total_remaining
FROM changed;
```

**Lời giải:** aggregate thực hiện trên các hàng đã UPDATE, không phải mặc định toàn inventory.

### Bài 16. Vì sao RETURNING không bảo đảm transaction đã commit?

```sql
BEGIN;
INSERT INTO returning203.job_tokens
DEFAULT VALUES
RETURNING token_id;
ROLLBACK;
```

**Lời giải:** ID có thể đã được trả trong transaction, nhưng hàng bị rollback; sequence vẫn có thể giữ khoảng trống. API không nên xác nhận commit thành công trước khi commit thực sự hoàn tất.

### Bài 17. Khi DELETE gặp foreign key?

**Đáp án:** nếu ràng buộc không cho xóa và không có cơ chế cascade phù hợp, câu DELETE thất bại. RETURNING không bỏ qua constraint và không biến thao tác thất bại thành một result set thành công.

### Bài 18. Nhận kết quả RETURNING trong Java

**Lời giải:** sử dụng `PreparedStatement` và API đọc `ResultSet`, ví dụ `executeQuery()` với SQL UPDATE ... RETURNING; kiểm tra `rs.next()`, xử lý 0 hàng và transaction.

### Bài 19. Có nên viết RETURNING * cho endpoint công khai?

**Lời giải:** thường không. Liệt kê các cột cần trả, ví dụ `RETURNING order_id, status, created_at`, để tránh lộ trường nhạy cảm và phụ thuộc schema.

### Bài 20. Phân biệt thao tác với snapshot lâu dài

**Câu hỏi:** `UPDATE inventory SET stock=stock-1 RETURNING stock` trả 4. Sau đó có request khác trừ tiếp 1. Giá trị trả về 4 có bị sai không?

**Lời giải:** không. Nó mô tả giá trị **sau thao tác thứ nhất**; tồn kho có thể là 3 khi request thứ hai hoàn tất. RETURNING không tạo một bảo đảm tồn kho bất biến theo thời gian.

## 33. Câu hỏi kiểm tra kiến thức

### Câu 1. RETURNING có phải hàm SQL không?

Không. Đây là một **mệnh đề** của câu DML trong PostgreSQL.

### Câu 2. INSERT RETURNING có thay INSERT không?

Không. INSERT vẫn ghi dữ liệu; RETURNING chỉ yêu cầu trả thêm kết quả các hàng được ghi.

### Câu 3. DELETE RETURNING có giữ hàng trong bảng không?

Không. Nếu DELETE thành công và transaction commit, hàng bị xóa. RETURNING trả các giá trị của hàng bị xóa trong statement.

### Câu 4. UPDATE RETURNING trả giá trị cũ hay mới?

Các biểu thức cột thông thường trong UPDATE RETURNING biểu diễn giá trị **sau update**. Việc truy cập đồng thời old/new có cú pháp/phụ thuộc phiên bản, cần xem tài liệu server mục tiêu.

### Câu 5. DO NOTHING RETURNING có trả hàng xung đột không?

Không. Hàng bị bỏ qua không được chèn và không xuất hiện trong RETURNING.

### Câu 6. Có thể dùng biểu thức trong RETURNING không?

Có. Ví dụ `RETURNING quantity * unit_price AS total` với các cột thích hợp.

### Câu 7. Có thể SELECT từ RETURNING của DML CTE không?

Có:

```sql
WITH changed AS (
    UPDATE ...
    RETURNING ...
)
SELECT ...
FROM changed;
```

Cú pháp trên là **khuôn mẫu**; các dấu ba chấm phải thay bằng SQL cụ thể trước khi chạy.

### Câu 8. RETURNING có tự bảo đảm người dùng có quyền đọc mọi cột không?

Không. Cần quyền DML/SELECT thích hợp và tuân thủ RLS cùng các chính sách bảo mật.

### Câu 9. RETURNING có tự kiểm tra đủ tồn kho không?

Không. Điều kiện `WHERE stock >= quantity` và constraint mới quyết định có cho giảm tồn hay không. RETURNING chỉ trả hàng thực sự được tác động.

### Câu 10. Có thể dùng RETURNING để tạo audit tự động mọi nơi không?

Không tự động. Trigger/audit/outbox hoặc các workflow DML CTE cần được thiết kế và áp dụng cho mọi đường ghi tương ứng.

## 34. Bảng tra cứu nhanh

| Mục tiêu | Mẫu cú pháp | Điểm cần nhớ |
|---|---|---|
| Lấy ID sau insert | `INSERT ... RETURNING id` | Lấy ID do đúng statement tạo |
| Lấy nhiều cột | `RETURNING id, status, created_at` | Giới hạn dữ liệu cần trả |
| Lấy giá trị default | `INSERT ... RETURNING created_at` | DB quyết định giá trị |
| Lấy computed/generated | `INSERT ... RETURNING generated_col` | Nhận giá trị đã ghi |
| Lấy giá sau update | `UPDATE ... RETURNING price` | Giá sau thao tác |
| Trừ tồn an toàn | `UPDATE ... SET stock=stock-? WHERE stock>=? RETURNING stock` | 0 hàng = không có hàng đạt điều kiện |
| Thay đổi trạng thái có điều kiện | `UPDATE ... WHERE status='NEW' RETURNING ...` | Chặn transition không hợp lệ |
| Lấy hàng đã xóa | `DELETE ... RETURNING ...` | Trả nội dung hàng bị xóa |
| Insert bỏ qua xung đột | `ON CONFLICT DO NOTHING RETURNING ...` | Chỉ trả hàng thật sự chèn |
| UPSERT và trả giá trị cuối | `ON CONFLICT DO UPDATE ... RETURNING ...` | Có thể là nhánh insert/update |
| Chỉ UPDATE khi giá trị khác | `WHERE col IS DISTINCT FROM proposed` | Nếu không sửa, RETURNING không có hàng |
| Kết quả từ DML CTE | `WITH changed AS (UPDATE ... RETURNING ...) SELECT ...` | Đọc tập changed |
| Ghi audit trong một statement | `WITH changed AS (...) INSERT ... SELECT FROM changed` | Cần hiểu atomicity và trigger |
| Chuyển hàng xóa sang archive | `WITH removed AS (DELETE ... RETURNING ...) INSERT ... SELECT ...` | Xóa + insert trong một statement |
| Đếm hàng đã sửa | `WITH changed AS (...) SELECT COUNT(*) FROM changed` | COUNT trả một hàng số đếm |
| Sắp xếp kết quả DML | `WITH changed AS (...) SELECT ... ORDER BY ...` | Không dựa vào thứ tự RETURNING |
| Kiểm tra kết quả JDBC | `PreparedStatement.executeQuery()` | Đọc ResultSet và 0 hàng |
| Bảo vệ thông tin nhạy cảm | Chỉ chọn cột cần thiết trong RETURNING | Không tự dùng RETURNING * cho API |
| Kiểm soát commit | Transaction manager / COMMIT | RETURNING không phải commit |
| Kiểm soát idempotency | UNIQUE + workflow/transaction đúng | DO NOTHING một mình chưa đủ |

## 35. Tổng kết: ghi đúng hàng và nhận ngay kết quả đã ghi

`RETURNING` giải quyết một nhu cầu rất cụ thể nhưng cực kỳ quan trọng trong PostgreSQL:

> **Sau khi INSERT, UPDATE hoặc DELETE, làm sao nhận chính xác những giá trị mà câu lệnh vừa tác động, mà không cần phỏng đoán hoặc tìm lại bằng một SELECT độc lập?**

Ba mẫu nền tảng:

```sql
-- Tạo đối tượng và lấy khóa được sinh:
INSERT INTO returning203.customers(email, full_name)
VALUES ('new@example.test', 'New Customer')
RETURNING customer_id, created_at;
```

```sql
-- Thay đổi có điều kiện rồi trả trạng thái mới:
UPDATE returning203.inventory
SET stock = stock - 1
WHERE sku = 'BOOK-PG' AND stock >= 1
RETURNING sku, stock AS remaining_stock;
```

```sql
-- Xóa rồi lấy dữ liệu của hàng đã xóa:
DELETE FROM returning203.orders
WHERE client_request_id = 'cancelled-example-203'
  AND status = 'CANCELLED'
RETURNING order_id, sku, quantity, status;
```

Khi cần nối tiếp nhiều thao tác trong **một statement**, dùng data-modifying CTE:

```sql
WITH changed AS (
    UPDATE returning203.inventory
    SET stock = stock - 1
    WHERE sku = 'BOOK-PG' AND stock >= 1
    RETURNING sku, stock
)
SELECT sku, stock
FROM changed;
```

Những nguyên tắc không được quên:

1. **RETURNING chỉ trả các hàng thực sự bị tác động**; khi WHERE không thỏa, result set có thể rỗng.
2. **INSERT** trả hàng mới, **UPDATE** trả giá trị sau sửa, **DELETE** trả nội dung hàng bị xóa theo ngữ nghĩa thông thường.
3. **DEFAULT/IDENTITY/generated columns** có thể được trả ngay từ database, không cần tìm lại ID qua MAX.
4. **UPSERT DO NOTHING** không trả hàng bị bỏ qua; **DO UPDATE có WHERE** cũng có thể không trả hàng conflict nếu điều kiện không thỏa.
5. **WITH ... RETURNING** giúp truyền dữ liệu giữa các DML và SELECT trong một statement; không dựa vào việc đọc lại bảng gốc để nhìn các thay đổi sibling CTE.
6. **RETURNING không tự commit**. Transaction vẫn có thể rollback và identity có thể có khoảng trống.
7. **RETURNING không tự giải quyết toàn bộ concurrency/idempotency**. Điều kiện UPDATE, UNIQUE/CHECK, isolation, khóa và transaction vẫn phải được thiết kế đúng.
8. **Bảo mật và API:** chỉ trả những cột cần thiết, kiểm tra quyền/RLS, xử lý 0 hàng, lỗi constraint và kết quả commit.
9. **Chọn cách viết dễ hiểu trước:** một statement với CTE hữu ích, nhưng không nên nhồi mọi workflow vào một truy vấn nếu transaction nhiều bước rõ ràng và an toàn hơn.

**Một câu để nhớ:** `RETURNING` không chỉ cho biết “đã sửa bao nhiêu hàng”; nó cho phép lấy **chính những hàng và giá trị mà PostgreSQL vừa thay đổi**, rồi sử dụng kết quả đó ngay trong ứng dụng hoặc bước SQL tiếp theo.

