# Thay đổi kiểu, giá trị mặc định và khả năng nhận NULL

Lược đồ cơ sở dữ liệu (*database schema*) không phải lúc nào cũng cố định. Khi ứng dụng phát triển, một cột ban đầu lưu giá tiền bằng chuỗi có thể cần đổi sang kiểu số; một trạng thái đơn hàng cần giá trị mặc định; hoặc một trường trước đây được phép bỏ trống nay phải bắt buộc có dữ liệu. Những thay đổi này thường được thực hiện bằng **`ALTER TABLE`**, nhưng việc sửa lược đồ của bảng **đã có dữ liệu** khác nhiều so với tạo bảng mới.

Ví dụ, thay đổi `total_amount` từ văn bản sang số sẽ thất bại nếu có giá trị `'không rõ'` không thể chuyển đổi. Thêm `NOT NULL` vào cột đang chứa `NULL` cũng không thành công. Đặt `DEFAULT 'NEW'` cho trạng thái không tự động sửa những đơn cũ đang có trạng thái `NULL`. Hiểu rõ ba cơ chế **kiểu dữ liệu, mặc định và khả năng nhận NULL** giúp thay đổi bảng đúng ý nghĩa nghiệp vụ và tránh làm mất dữ liệu.

Bài này dùng **PostgreSQL** làm môi trường minh họa, với SQL có thể chạy tuần tự trong một database thực hành riêng. Các nguyên tắc áp dụng rộng rãi cho hệ quản trị quan hệ, nhưng cú pháp `ALTER TABLE` và cách xử lý khi chuyển kiểu không hoàn toàn giống nhau giữa PostgreSQL, MySQL, SQL Server và Oracle Database.

## 1. Ba thuộc tính cột cần phân biệt

Một cột thường có tên, **kiểu dữ liệu**, **giá trị mặc định** và **quy tắc cho phép `NULL`**. Các thuộc tính đó giải quyết những câu hỏi khác nhau:

| Thuộc tính | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| **Data type** | Cột lưu loại giá trị nào, phạm vi và độ chính xác ra sao? | `VARCHAR(30)`, `INTEGER`, `NUMERIC(12,2)`, `DATE` |
| **DEFAULT** | Nếu câu lệnh `INSERT` **không cung cấp** giá trị cho cột thì dùng gì? | `DEFAULT 'NEW'`, `DEFAULT 0` |
| **NULL / NOT NULL** | Cột có được phép thiếu giá trị hay không? | `status VARCHAR(20) NOT NULL` |

Ví dụ:

```sql
CREATE TABLE example_orders (
    id INTEGER PRIMARY KEY,
    status VARCHAR(20) NOT NULL DEFAULT 'NEW',
    total_amount NUMERIC(12, 2) DEFAULT 0
);
```

Từ định nghĩa này:

- `status` lưu chuỗi tối đa 20 ký tự, **không cho phép `NULL`**; nếu bỏ qua cột trong `INSERT` thì mặc định là `'NEW'`.
- `total_amount` lưu số thập phân có tối đa 12 chữ số, trong đó 2 chữ số thập phân; có mặc định `0` nhưng **vẫn cho phép `NULL`** vì không khai báo `NOT NULL`.
- `DEFAULT` và `NOT NULL` là **hai quy tắc độc lập**. Một cột có mặc định không có nghĩa nó bắt buộc có giá trị trong mọi tình huống.

Các thao tác đổi kiểu, đổi mặc định và đổi khả năng nhận `NULL` chủ yếu được biểu diễn bằng `ALTER TABLE`, một phần của ngôn ngữ định nghĩa dữ liệu (DDL).

## 2. Tạo bảng và dữ liệu mẫu để theo dõi thay đổi

Thực hiện ví dụ trong **database học tập riêng**, tránh dùng bảng hoặc dữ liệu thật. Đầu tiên tạo bảng `orders_demo` với thiết kế ban đầu chưa hoàn chỉnh:

```sql
CREATE TABLE orders_demo (
    order_id INTEGER PRIMARY KEY,
    status VARCHAR(20),
    total_text VARCHAR(20),
    customer_email VARCHAR(120)
);

INSERT INTO orders_demo (order_id, status, total_text, customer_email)
VALUES
    (101, 'PAID',    '120000.50', 'an@example.com'),
    (102, NULL,      '0',         NULL),
    (103, 'PENDING', NULL,        'chi@example.com');

SELECT order_id, status, total_text, customer_email
FROM orders_demo
ORDER BY order_id;
```

| order_id | status | total_text | customer_email |
|---:|---|---|---|
| 101 | PAID | `'120000.50'` | an@example.com |
| 102 | `NULL` | `'0'` | `NULL` |
| 103 | PENDING | `NULL` | chi@example.com |

Bảng có ba điểm cần cải thiện:

1. `total_text` là kiểu `VARCHAR(20)`, dù dữ liệu biểu diễn số tiền; cần đổi thành `NUMERIC(12,2)` để có phép tính và quy tắc lưu số phù hợp.
2. `status` đang không có mặc định; cần đặt `'NEW'` cho đơn mới khi ứng dụng không truyền trạng thái.
3. `status` đang chứa `NULL`; sau khi xác định cách xử lý bản ghi cũ, cần chuyển thành **`NOT NULL`**.

`customer_email` tiếp tục là trường tùy chọn; ví dụ này sẽ không biến email thiếu thành một địa chỉ giả để vượt qua ràng buộc.

## 3. Thay đổi kiểu dữ liệu của cột

### 3.1. Cú pháp PostgreSQL

Để sửa kiểu một cột:

```sql
ALTER TABLE ten_bang
ALTER COLUMN ten_cot TYPE kieu_moi;
```

Khi cần xác định cách biến đổi giá trị cũ, PostgreSQL hỗ trợ biểu thức `USING`:

```sql
ALTER TABLE ten_bang
ALTER COLUMN ten_cot TYPE kieu_moi
USING bieu_thuc_chuyen_doi;
```

`USING` diễn tả **cách tính giá trị mới cho từng hàng từ giá trị cũ**. Nó đặc biệt hữu ích khi DBMS không thể tự suy ra phép chuyển kiểu hợp lệ.

Với bảng mẫu, trước tiên cần kiểm tra dữ liệu văn bản có thể chuyển thành số:

```sql
SELECT order_id, total_text
FROM orders_demo
ORDER BY order_id;
```

Ba giá trị ban đầu là `'120000.50'`, `'0'` và `NULL`, đều có thể chuyển sang `NUMERIC(12,2)`; `NULL` vẫn là `NULL` sau khi chuyển kiểu. Chạy:

```sql
ALTER TABLE orders_demo
ALTER COLUMN total_text TYPE NUMERIC(12, 2)
USING total_text::NUMERIC(12, 2);
```

Ký hiệu `::` là phép ép kiểu thường dùng trong PostgreSQL, tương đương với cách viết `CAST(total_text AS NUMERIC(12,2))`. Sau khi chuyển kiểu thành công, đổi tên cột để phản ánh ý nghĩa mới:

```sql
ALTER TABLE orders_demo
RENAME COLUMN total_text TO total_amount;

SELECT order_id, total_amount
FROM orders_demo
ORDER BY order_id;
```

Kết quả:

| order_id | total_amount |
|---:|---:|
| 101 | 120000.50 |
| 102 | 0.00 |
| 103 | `NULL` |

Giờ `total_amount` có thể tham gia các phép `SUM`, so sánh số học và ràng buộc giá trị. Việc đổi tên cột được minh họa vì tên `total_text` không còn diễn tả đúng kiểu; trong ứng dụng thật, mọi SQL, ORM mapping, view và các thành phần phụ thuộc tên cũ cần được cập nhật.

### 3.2. Giá trị không chuyển được sẽ khiến thao tác thất bại

Giả sử một hàng chứa `total_text = 'N/A'`. Biểu thức `'N/A'::NUMERIC` không có kết quả số hợp lệ, nên phép đổi kiểu sẽ báo lỗi. PostgreSQL không tự hiểu `'N/A'` là `0` hay `NULL`.

Trước khi áp dụng thay đổi, cần quyết định rõ:

- Các chuỗi có đúng định dạng số theo quy ước lưu trữ không?
- Chuỗi rỗng `''` nghĩa là giá trị thiếu, hay là lỗi nhập liệu?
- Có giá trị tiền âm, dấu phẩy phân cách hàng nghìn, đơn vị tiền hoặc khoảng trắng không?
- Kiểu đích có đủ phạm vi và độ chính xác để chứa tất cả giá trị hiện có không?

Ví dụ riêng cho trường hợp **nghiệp vụ xác nhận chuỗi rỗng chỉ biểu thị “chưa biết”**, có thể dùng biểu thức:

```sql
-- Ví dụ thay thế (chạy trên cột văn bản trước khi đổi kiểu):
ALTER TABLE orders_demo
ALTER COLUMN total_text TYPE NUMERIC(12, 2)
USING NULLIF(BTRIM(total_text), '')::NUMERIC(12, 2);
```

`BTRIM` bỏ khoảng trắng hai đầu; `NULLIF(x, '')` trả về `NULL` khi `x` bằng chuỗi rỗng. **Đây là phương án thay thế cho lệnh ở mục 3.1, không chạy tiếp sau khi cột đã đổi tên và đổi kiểu.** Nó không xử lý được chuỗi tùy ý như `'N/A'`. Không tự chuyển dữ liệu “không rõ” thành số `0` nếu chưa có quy tắc nghiệp vụ.

### 3.3. Đổi kiểu có thể làm thay đổi giá trị hoặc mất thông tin

Không phải mọi phép chuyển kiểu đều bảo toàn đầy đủ dữ liệu:

| Thay đổi | Điều cần chú ý |
|---|---|
| `VARCHAR(20)` → `VARCHAR(40)` | Tăng giới hạn ký tự thường ít rủi ro hơn thu hẹp |
| `VARCHAR(40)` → `VARCHAR(10)` | Hàng có chuỗi dài có thể gây lỗi hoặc cần quy tắc cắt; không âm thầm cắt dữ liệu |
| `VARCHAR` → `INTEGER` | Chuỗi không phải số nguyên sẽ không chuyển được |
| `NUMERIC(14,4)` → `NUMERIC(12,2)` | Có thể làm tròn số thập phân hoặc vượt giới hạn phần nguyên |
| `TIMESTAMP` ↔ `TIMESTAMPTZ` | Cần xác định múi giờ và ngữ nghĩa thời điểm |
| `TEXT` → `DATE` | Cần chuẩn định dạng và xử lý ngày không hợp lệ |

Ngay cả khi câu lệnh chạy thành công, thay đổi kiểu vẫn phải giữ **ý nghĩa** của dữ liệu. Đừng đổi đơn vị “đồng” thành “xu”, hay từ giây thành mili giây, chỉ bằng cách thay kiểu cột; phải có phép chuyển giá trị phù hợp.

### 3.4. Khi kiểu mới tương thích trực tiếp

Để tăng giới hạn độ dài của `status` từ 20 lên 30 ký tự:

```sql
ALTER TABLE orders_demo
ALTER COLUMN status TYPE VARCHAR(30);
```

Với thay đổi đơn giản, PostgreSQL thường có thể suy ra cách chuyển mà không cần `USING`. Tuy nhiên, dù câu lệnh ngắn, bạn vẫn cần kiểm tra tác động đến câu SQL ứng dụng, chỉ mục, ràng buộc và các đối tượng phụ thuộc.

## 4. Thay đổi giá trị mặc định bằng SET DEFAULT và DROP DEFAULT

### 4.1. Đặt mặc định cho hàng mới

Trong bảng hiện tại, `status` là cột có thể `NULL` và chưa có mặc định. Giả sử quy tắc nghiệp vụ là **đơn mới không truyền trạng thái thì bắt đầu ở `NEW`**:

```sql
ALTER TABLE orders_demo
ALTER COLUMN status SET DEFAULT 'NEW';
```

Ví dụ khác: nếu nghiệp vụ cho phép xem **số tiền chưa nhập lúc tạo đơn là 0**, có thể đặt:

```sql
ALTER TABLE orders_demo
ALTER COLUMN total_amount SET DEFAULT 0.00;
```

Chỉ nên chọn `0` khi “0 đồng” thực sự là giá trị hợp lệ cho tình huống đó. Nếu “chưa tính được tổng tiền” khác “tổng tiền bằng 0”, giữ `NULL` có thể diễn đạt dữ liệu chính xác hơn.

Sau khi đặt hai mặc định, thêm một đơn **không ghi rõ** `status` và `total_amount`:

```sql
INSERT INTO orders_demo (order_id, customer_email)
VALUES (104, 'dung@example.com');

SELECT order_id, status, total_amount
FROM orders_demo
WHERE order_id = 104;
```

Kết quả:

| order_id | status | total_amount |
|---:|---|---:|
| 104 | NEW | 0.00 |

DBMS áp dụng giá trị mặc định vì hai cột đó **không có mặt trong danh sách cột của `INSERT`**. Có thể yêu cầu mặc định tường minh bằng từ khóa `DEFAULT`:

```sql
INSERT INTO orders_demo (order_id, status, total_amount)
VALUES (106, DEFAULT, DEFAULT);
```

Lệnh này, nếu chạy trong môi trường mẫu, cũng cho trạng thái `NEW` và số tiền `0.00`.

### 4.2. DEFAULT không tự thay thế NULL được truyền rõ ràng

Đặt mặc định **không** tương đương với “mọi lần cột `NULL` đều tự thành mặc định”. Ví dụ sau vẫn có `NULL` vì câu lệnh chỉ định chúng một cách rõ ràng:

```sql
INSERT INTO orders_demo (order_id, status, total_amount)
VALUES (105, NULL, NULL);
```

Tại thời điểm này, cả hai cột còn được phép `NULL`, nên bản ghi 105 được thêm thành công. Một quy tắc `NOT NULL` về sau sẽ chặn `NULL` rõ ràng ở cột tương ứng, bất kể cột có mặc định hay không.

### 4.3. SET DEFAULT không sửa dữ liệu đã lưu

Sau khi đặt `DEFAULT 'NEW'`, đơn **102** vẫn có `status = NULL`; đơn **103** vẫn có `total_amount = NULL`. `ALTER COLUMN ... SET DEFAULT` tác động đến hành vi **ghi dữ liệu trong tương lai**, không phải một lệnh `UPDATE` cho các hàng hiện có.

| Tình huống | Có áp dụng DEFAULT không? |
|---|---|
| `INSERT` bỏ qua cột có mặc định | **Có** |
| `INSERT` dùng từ khóa `DEFAULT` | **Có** |
| `INSERT` truyền giá trị thông thường | **Không**, dùng giá trị được truyền |
| `INSERT` truyền `NULL` rõ ràng | **Không**, dùng `NULL` nếu được phép |
| `UPDATE ... SET col = DEFAULT` | **Có**, dùng biểu thức mặc định hiện hành |
| `UPDATE` không nhắc đến cột | **Không**, giữ giá trị cũ |
| Hàng đã tồn tại trước khi thêm DEFAULT | **Không** tự được cập nhật |

Ví dụ, khi có mặc định:

```sql
UPDATE orders_demo
SET status = DEFAULT
WHERE order_id = 102;
```

Lệnh trên **chủ động cập nhật** trạng thái đơn 102 thành `NEW`. Nó là thao tác thay đổi dữ liệu (DML), khác với `SET DEFAULT` chỉ sửa định nghĩa cột.

### 4.4. Bỏ mặc định

Khi không muốn DBMS tự điền giá trị nữa:

```sql
-- Ví dụ độc lập; nếu chạy sẽ thay đổi hành vi INSERT về sau.
ALTER TABLE orders_demo
ALTER COLUMN status DROP DEFAULT;
```

`DROP DEFAULT` **không xóa những giá trị đã tồn tại** và không tự thay đổi thuộc tính `NOT NULL`. Nếu cột vẫn có `NOT NULL` mà không còn mặc định, một `INSERT` bỏ qua cột đó thường lỗi vì không tạo được giá trị hợp lệ; ứng dụng phải cung cấp cột (hoặc một cơ chế khác bảo đảm giá trị).

Trong kịch bản xuyên suốt, **giữ `DEFAULT 'NEW'`**; đoạn `DROP DEFAULT` ở đây chỉ để minh họa cú pháp. Nếu đã chạy nó trong lúc thực hành, hãy đặt lại `SET DEFAULT 'NEW'` trước khi tiếp tục.

## 5. Thay đổi khả năng nhận NULL: SET NOT NULL và DROP NOT NULL

### 5.1. Trước khi đặt NOT NULL, dữ liệu cũ phải hợp lệ

Giả sử yêu cầu mới là: **mọi đơn phải có trạng thái**. Ta muốn biến `status` thành cột bắt buộc:

```sql
ALTER TABLE orders_demo
ALTER COLUMN status SET NOT NULL;
```

Nhưng nếu chạy ngay lúc này, thao tác sẽ thất bại vì còn đơn có `status = NULL` (ít nhất đơn 105 nếu đã chạy ví dụ mục 4.2; trước khi cập nhật thì đơn 102 cũng vậy). Ràng buộc `NOT NULL` không tự quyết định cách điền giá trị thiếu.

Xem những hàng cần giải quyết:

```sql
SELECT order_id, status
FROM orders_demo
WHERE status IS NULL
ORDER BY order_id;
```

Trong bảng đã thực hiện tuần tự các ví dụ ở mục 4, sau khi cập nhật riêng đơn 102 bằng `DEFAULT`, kết quả sẽ còn **105**; nếu bạn bỏ qua ví dụ `UPDATE`, kết quả là **102 và 105**. Khi chuẩn bị triển khai, điều quan trọng là kiểm tra **trạng thái thực tế của dữ liệu**, không dựa vào giả định.

### 5.2. Xử lý NULL có chủ đích, sau đó đặt NOT NULL

Với bài thực hành này, giả sử đã xác nhận quy tắc: **bản ghi chưa có trạng thái được xem như đơn mới**. Có thể điền giá trị thiếu:

```sql
UPDATE orders_demo
SET status = 'NEW'
WHERE status IS NULL;
```

Kiểm tra lại:

```sql
SELECT COUNT(*) AS remaining_null_status
FROM orders_demo
WHERE status IS NULL;
-- Kỳ vọng: 0
```

Bây giờ mới thực hiện:

```sql
ALTER TABLE orders_demo
ALTER COLUMN status SET NOT NULL;
```

Sau thay đổi, những lệnh sau có hành vi khác nhau:

```sql
-- Hợp lệ vì DEFAULT 'NEW' được dùng:
INSERT INTO orders_demo (order_id) VALUES (107);

-- Không hợp lệ vì NULL rõ ràng vi phạm NOT NULL:
-- INSERT INTO orders_demo (order_id, status)
-- VALUES (108, NULL);
```

**Trong hệ thống thật không nên tự ý biến trạng thái “chưa biết” thành “NEW”.** Chọn dữ liệu để backfill theo quy tắc nghiệp vụ, lịch sử hoặc đối chiếu nguồn đáng tin cậy. Nếu không thể xác định chính xác, có thể cần trạng thái `UNKNOWN` hoặc thiết kế cho phép `NULL` tạm thời; việc đặt `NOT NULL` phải đợi khi dữ liệu và ứng dụng đã sẵn sàng.

### 5.3. Cho phép NULL trở lại bằng DROP NOT NULL

Nếu yêu cầu thay đổi và muốn cột được phép thiếu giá trị:

```sql
-- Ví dụ độc lập:
ALTER TABLE orders_demo
ALTER COLUMN status DROP NOT NULL;
```

`DROP NOT NULL` chỉ bỏ ràng buộc bắt buộc; **không biến những trạng thái đã có thành `NULL`**. Nếu cột vẫn có `DEFAULT 'NEW'`, `INSERT` bỏ qua cột vẫn nhận `NEW`; còn `INSERT` truyền `NULL` có thể được phép trở lại (nếu không có ràng buộc khác cấm).

Ngược lại, thêm `NOT NULL` cho `customer_email` sẽ lỗi khi bảng còn khách không có email. Việc email là tùy chọn hay bắt buộc phải được quyết định theo nghiệp vụ; không tự đặt một email giả để vượt qua kiểm tra.

### 5.4. DEFAULT, NULL và CHECK khác nhau

Nếu nghiệp vụ yêu cầu **tiền không âm**, một ràng buộc có thể là:

```sql
ALTER TABLE orders_demo
ADD CONSTRAINT orders_demo_total_nonnegative
CHECK (total_amount >= 0);
```

Trong SQL, một điều kiện `CHECK` thường chỉ từ chối khi biểu thức đánh giá thành `FALSE`; với `total_amount = NULL` thì `NULL >= 0` là `UNKNOWN` và bản ghi vẫn được chấp nhận. Nếu cần **tiền vừa bắt buộc, vừa không âm**, phải dùng thêm `NOT NULL`:

```sql
-- Chỉ chạy sau khi mọi NULL đã được xử lý đúng nghiệp vụ:
ALTER TABLE orders_demo
ALTER COLUMN total_amount SET NOT NULL;
```

**`DEFAULT` không thay cho `NOT NULL`; `CHECK (col >= 0)` cũng không thay cho `NOT NULL`.** Ba cơ chế bổ sung nhau: mặc định cho thao tác ghi thiếu cột, `NOT NULL` cho tính bắt buộc, `CHECK` cho miền giá trị hợp lệ.

## 6. Quy trình thay đổi cột khi bảng đã có dữ liệu

Thay đổi cấu trúc của một bảng trong môi trường đang hoạt động nên được coi như **migration có kiểm soát**, gồm cả phần dữ liệu và phần ứng dụng sử dụng dữ liệu.

### Bước 1 — Xác định trạng thái hiện tại

Trong PostgreSQL, có thể xem định nghĩa cột bằng `information_schema.columns`:

```sql
SELECT
    column_name,
    data_type,
    character_maximum_length,
    numeric_precision,
    numeric_scale,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'orders_demo'
ORDER BY ordinal_position;
```

Truy vấn này cho biết loại dữ liệu, giới hạn ký tự, độ chính xác số, khả năng nhận `NULL` và mặc định hiện tại. Đồng thời kiểm tra số hàng và phân bố giá trị:

```sql
SELECT COUNT(*) AS total_rows,
       COUNT(*) FILTER (WHERE status IS NULL) AS missing_status
FROM orders_demo;
```

`FILTER` trên hàm tổng hợp ở đây là cú pháp PostgreSQL. Với DBMS khác, có thể dùng `SUM(CASE WHEN status IS NULL THEN 1 ELSE 0 END)`.

### Bước 2 — Xác định ý nghĩa dữ liệu và thay đổi mong muốn

Trước khi đổi kiểu hoặc áp `NOT NULL`, cần trả lời:

- Dữ liệu cũ có chuyển đổi chính xác sang kiểu mới không? Có giá trị ngoại lệ nào?
- Giá trị mặc định chỉ dùng cho bản ghi mới hay cũng cần cập nhật bản ghi cũ?
- Những hàng có `NULL` cần được điền bằng cách nào? Có thật sự được suy diễn thành một giá trị cố định không?
- Các API, câu SQL, ORM, báo cáo, view, trigger, chỉ mục và ứng dụng khác có phụ thuộc kiểu cột hay tên cột cũ không?
- Nếu cần quay về phiên bản trước, liệu dữ liệu có còn biểu diễn được bằng kiểu cũ?

Ví dụ chuyển `VARCHAR` sang `NUMERIC` có thể cần bước làm sạch dữ liệu; chuyển `NUMERIC(14,4)` sang `NUMERIC(12,2)` có thể làm tròn hoặc mất độ chính xác. Không nên giả định mọi `ALTER TABLE` đều đảo ngược được mà không mất dữ liệu.

### Bước 3 — Thay đổi theo thứ tự phù hợp

Với ví dụ `orders_demo`, một thứ tự hợp lý là:

```text
Kiểm tra dữ liệu và bản sao lưu/snapshot khi cần
    |
    v
Chuyển total_text từ VARCHAR sang NUMERIC
    |
    v
Đổi tên total_text thành total_amount
    |
    v
Đặt DEFAULT cho status, total_amount
    |
    v
Backfill các status đang NULL theo quyết định nghiệp vụ
    |
    v
Kiểm tra lại dữ liệu
    |
    v
Đặt status NOT NULL
    |
    v
Xác nhận schema và cách INSERT hoạt động
```

Nếu thực hiện với bảng thật có lưu lượng ghi, ứng dụng có thể tiếp tục tạo thêm `NULL` trong lúc backfill. **Đặt mặc định trước** có thể giúp các lệnh `INSERT` không truyền trạng thái, nhưng không ngăn ứng dụng truyền `NULL` rõ ràng. Vì vậy cần phối hợp thay đổi ứng dụng, đồng bộ dữ liệu và bước đặt `NOT NULL` để tránh lỗi cạnh tranh.

### Bước 4 — Kiểm tra lại định nghĩa và hành vi

Với dữ liệu mẫu đã chuyển kiểu và điền trạng thái thiếu:

```sql
SELECT order_id, status, total_amount, customer_email
FROM orders_demo
ORDER BY order_id;
```

Nếu đã chạy các `INSERT` minh họa ở mục 4 và 5, bạn sẽ thấy các hàng mới cùng mặc định tương ứng; phần quan trọng là **không còn `status = NULL`**, `total_amount` có kiểu `NUMERIC(12,2)`, và các bản ghi cũ giữ số tiền đã biết.

Thực hiện lại truy vấn `information_schema.columns` để xác nhận `status` có `is_nullable = 'NO'`, mặc định của nó là `'NEW'` và kiểu của `total_amount` đã đổi đúng kỳ vọng.

## 7. Ví dụ migration gọn từ bảng ban đầu

Nếu muốn áp dụng tất cả các thay đổi đã giải thích từ **trạng thái bảng chỉ có ba hàng ban đầu ở mục 2**, đoạn sau là một chuỗi có thể thực thi lần lượt trong PostgreSQL:

```sql
BEGIN;

-- 1. Chuyển kiểu và đổi tên cột.
ALTER TABLE orders_demo
ALTER COLUMN total_text TYPE NUMERIC(12, 2)
USING total_text::NUMERIC(12, 2);

ALTER TABLE orders_demo
RENAME COLUMN total_text TO total_amount;

-- 2. Mặc định cho các INSERT sau này.
ALTER TABLE orders_demo
ALTER COLUMN status SET DEFAULT 'NEW';

ALTER TABLE orders_demo
ALTER COLUMN total_amount SET DEFAULT 0.00;

-- 3. Điền trạng thái thiếu sau khi đã xác định chính sách nghiệp vụ.
UPDATE orders_demo
SET status = 'NEW'
WHERE status IS NULL;

-- 4. Áp ràng buộc sau khi không còn trạng thái NULL.
ALTER TABLE orders_demo
ALTER COLUMN status SET NOT NULL;

COMMIT;
```

Đoạn trên **dành cho bảng vừa được tạo theo mục 2 và chưa chạy các lệnh thay đổi ở mục 3–5**. Nếu bạn đã thực hiện tuần tự bài học, không chạy lại phép chuyển `total_text` vì cột đó đã đổi tên. Muốn thử lại từ đầu, nên tạo một bảng thực hành mới bằng script khởi tạo, không xóa bảng có dữ liệu cần giữ.

PostgreSQL cho phép nhiều lệnh DDL kiểu này tham gia giao dịch: nếu một lệnh thất bại, có thể `ROLLBACK` thay đổi chưa được `COMMIT`. Tuy nhiên, **giao dịch thành công không bảo đảm một migration không làm mất ý nghĩa dữ liệu**, và khả năng transaction DDL không giống nhau trên mọi DBMS.

## 8. Thay đổi lược đồ khi ứng dụng đang chạy

Trong môi trường phát triển nhỏ, vài lệnh `ALTER TABLE` có thể chạy rất nhanh. Với bảng có hàng triệu bản ghi hoặc được truy cập liên tục, tác động có thể đáng kể:

- **Chuyển kiểu** có thể phải đọc/viết lại nhiều dữ liệu, xây dựng lại chỉ mục hoặc xử lý các đối tượng phụ thuộc. Thời gian và cơ chế thực thi tùy phiên bản PostgreSQL, kiểu cũ và kiểu mới.
- **Đặt `NOT NULL`** có thể cần kiểm tra dữ liệu hiện có và ảnh hưởng thao tác đồng thời.
- Nhiều lệnh `ALTER TABLE` cần **khóa bảng** trong quá trình thực hiện; câu lệnh đơn giản không có nghĩa không gây chờ hoặc chặn giao dịch khác.
- **Đặt `DEFAULT`** thay đổi cách ghi dữ liệu tương lai; ứng dụng cũ vẫn có thể truyền `NULL` tường minh hoặc áp mặc định khác ở tầng ứng dụng.
- Thay đổi kiểu, tên hoặc điều kiện bắt buộc có thể làm **SQL cũ và mã ORM** không còn tương thích.

Một chiến lược triển khai nhiều giai đoạn thường an toàn hơn việc thay tất cả tại một thời điểm:

1. **Mở rộng tương thích:** chuẩn bị cột mới, logic chuyển dữ liệu hoặc cách ghi phù hợp mà phiên bản ứng dụng cũ và mới có thể cùng hoạt động.
2. **Chuyển dữ liệu (backfill):** xử lý các hàng cũ theo lô nếu cần, có thể theo dõi tiến độ mà không kéo dài một giao dịch quá lớn.
3. **Cập nhật ứng dụng:** đưa các phiên bản sử dụng kiểu dữ liệu, giá trị mặc định hoặc trường bắt buộc mới vào hoạt động.
4. **Siết ràng buộc:** sau khi dữ liệu và các luồng ghi đều tuân theo quy tắc, mới áp `NOT NULL`, loại bỏ đường ghi cũ và dọn cấu trúc không dùng.

Cách này thường được gọi là **expand–migrate–contract**. Khi chỉ sửa bảng thực hành nhỏ, bạn có thể chạy một giao dịch như ví dụ. Khi làm việc với sản xuất, cần dự kiến bản sao lưu, phương án khôi phục, giới hạn thời gian khóa, các đối tượng phụ thuộc và kế hoạch triển khai ứng dụng tương ứng.

## 9. Khác biệt cú pháp giữa các hệ quản trị

Không nên sao chép nguyên cú pháp PostgreSQL sang DBMS khác. Một vài ví dụ minh họa cho cùng nhu cầu:

| Nhu cầu | PostgreSQL | MySQL | SQL Server |
|---|---|---|---|
| Đổi kiểu cột | `ALTER TABLE t ALTER COLUMN col TYPE NUMERIC(12,2);` | `ALTER TABLE t MODIFY COLUMN col DECIMAL(12,2);` | `ALTER TABLE t ALTER COLUMN col DECIMAL(12,2) NULL;` |
| Đặt mặc định | `ALTER TABLE t ALTER COLUMN col SET DEFAULT 0;` | `ALTER TABLE t ALTER COLUMN col SET DEFAULT 0;` | Thường thêm một ràng buộc `DEFAULT` bằng `ADD CONSTRAINT ... DEFAULT ... FOR col` |
| Bắt buộc có giá trị | `ALTER TABLE t ALTER COLUMN col SET NOT NULL;` | `ALTER TABLE t MODIFY COLUMN col DECIMAL(12,2) NOT NULL;` | `ALTER TABLE t ALTER COLUMN col DECIMAL(12,2) NOT NULL;` |
| Cho phép NULL | `ALTER TABLE t ALTER COLUMN col DROP NOT NULL;` | `ALTER TABLE t MODIFY COLUMN col DECIMAL(12,2) NULL;` | `ALTER TABLE t ALTER COLUMN col DECIMAL(12,2) NULL;` |

Các đoạn trong bảng chỉ minh họa **cú pháp khái quát**, không phải một chuỗi lệnh áp trực tiếp cho mọi bảng: kiểu cột hiện tại, các thuộc tính khác, tên constraint, dependency và phiên bản DBMS phải được kiểm tra trước. Đặc biệt ở MySQL, lệnh `MODIFY COLUMN` có thể cần khai báo lại những thuộc tính muốn giữ như `NOT NULL` và `DEFAULT`; ở SQL Server, `DEFAULT` thường là ràng buộc tách biệt. Oracle Database dùng biến thể `ALTER TABLE ... MODIFY (...)`. Với các thao tác triển khai thật, luôn đối chiếu tài liệu chính thức của phiên bản DBMS đang sử dụng.

## 10. Những lỗi thường gặp và cách hiểu đúng

**“Đã `SET DEFAULT 'NEW'` nhưng các hàng cũ vẫn NULL.”** Đây là hành vi đúng: mặc định áp dụng khi tạo/ghi giá trị theo quy tắc `DEFAULT`, không phải lệnh backfill. Muốn sửa dữ liệu đã có, dùng `UPDATE` phù hợp.

**“Có `DEFAULT 0` thì không cần `NOT NULL`.”** Không đúng. Nếu cột cho phép `NULL`, ứng dụng có thể chèn `NULL` rõ ràng. Mặc định và khả năng nhận `NULL` là hai quy tắc khác nhau.

**“`ALTER COLUMN ... SET NOT NULL` sẽ tự tìm giá trị để điền.”** Không. Nếu còn `NULL`, hệ quản trị sẽ từ chối thay đổi hoặc yêu cầu xử lý trước, tùy DBMS và ngữ cảnh.

**“Đổi `VARCHAR` sang số chỉ là thay nhãn kiểu.”** Không. DBMS phải chuyển dữ liệu đang lưu; chuỗi không đúng định dạng, giá trị quá lớn hoặc số có độ chính xác không phù hợp có thể gây lỗi hoặc làm mất thông tin.

**“`NULL` và 0 là như nhau nếu cột chứa tiền.”** Không. `NULL` thường thể hiện chưa biết hoặc không áp dụng; `0` là con số đã xác định. Mọi phép backfill cần tôn trọng ý nghĩa này.

**“Bỏ `NOT NULL` làm những giá trị cũ thành NULL.”** Không. `DROP NOT NULL` chỉ thay đổi quy tắc chấp nhận giá trị cho các thao tác ghi tiếp theo.

**“DDL luôn có thể rollback trên mọi hệ quản trị.”** Không. PostgreSQL hỗ trợ giao dịch cho nhiều thao tác DDL thông thường, còn MySQL và các hệ khác có quy tắc commit riêng; cần hiểu hành vi của DBMS và câu lệnh cụ thể.

**“Nếu migration chạy thành công thì ứng dụng chắc chắn chạy được.”** Chưa chắc. SQL trong ứng dụng, ánh xạ kiểu ở Java/JPA, phép serialize, báo cáo và các client khác có thể vẫn trông đợi tên hoặc kiểu cũ. Thay đổi lược đồ cần phối hợp với thay đổi phần mềm sử dụng nó.

## 11. Bài tập thực hành

### Bài 1 — Thay kiểu có kiểm soát

Tạo bảng sau:

```sql
CREATE TABLE scores_demo (
    id INTEGER PRIMARY KEY,
    score_text VARCHAR(10)
);

INSERT INTO scores_demo (id, score_text)
VALUES (1, '95'), (2, '80'), (3, NULL);
```

Yêu cầu: đổi `score_text` sang `INTEGER`, giữ nguyên `NULL`, rồi đổi tên thành `score`.

Gợi ý:

```sql
ALTER TABLE scores_demo
ALTER COLUMN score_text TYPE INTEGER
USING score_text::INTEGER;

ALTER TABLE scores_demo
RENAME COLUMN score_text TO score;
```

Nếu bạn thêm hàng `(4, 'absent')` trước khi đổi kiểu, dự đoán lỗi và giải thích tại sao không được tự coi `'absent'` là `0`.

### Bài 2 — Phân biệt DEFAULT và NULL

Tạo:

```sql
CREATE TABLE tickets_demo (
    ticket_id INTEGER PRIMARY KEY,
    priority VARCHAR(10)
);

ALTER TABLE tickets_demo
ALTER COLUMN priority SET DEFAULT 'NORMAL';
```

So sánh kết quả ba lệnh:

```sql
INSERT INTO tickets_demo (ticket_id) VALUES (1);
INSERT INTO tickets_demo (ticket_id, priority) VALUES (2, NULL);
INSERT INTO tickets_demo (ticket_id, priority) VALUES (3, DEFAULT);

SELECT * FROM tickets_demo ORDER BY ticket_id;
```

Đáp án: ticket 1 và 3 nhận `'NORMAL'`; ticket 2 vẫn có `NULL`. Nếu sau đó thêm `NOT NULL` mà chưa sửa ticket 2, thao tác không thành công.

### Bài 3 — Đặt NOT NULL đúng thứ tự

Với `tickets_demo` ở bài 2:

1. Đếm số hàng có `priority IS NULL`.
2. Giả sử đã được xác nhận rằng mọi ticket thiếu mức ưu tiên đều mang mức `'NORMAL'`, cập nhật chúng.
3. Áp `ALTER COLUMN priority SET NOT NULL`.
4. Thử một `INSERT` bỏ qua `priority` và một `INSERT` truyền `NULL` rõ ràng. Giải thích vì sao chúng có kết quả khác nhau.

Gợi ý cho bước 2 và 3:

```sql
UPDATE tickets_demo
SET priority = 'NORMAL'
WHERE priority IS NULL;

ALTER TABLE tickets_demo
ALTER COLUMN priority SET NOT NULL;
```

### Bài 4 — Chọn kiểu dữ liệu và quy tắc thiếu giá trị

Một hệ thống có cột `delivery_fee`. Yêu cầu: “Phí giao hàng có thể chưa được xác định. Nếu đã có phí thì không âm.” Bạn sẽ chọn định nghĩa cột nào?

```sql
-- Phương án A
delivery_fee NUMERIC(12,2) DEFAULT 0 NOT NULL

-- Phương án B
delivery_fee NUMERIC(12,2) CHECK (delivery_fee >= 0)
```

Với yêu cầu đã nêu, **B** diễn tả chính xác hơn: `NULL` biểu thị chưa xác định, còn `CHECK` chặn phí âm khi có số. Phương án A áp mặc định bằng 0 và cấm `NULL`, phù hợp với nghiệp vụ khác: “phí mặc định miễn phí và luôn phải có giá trị”.

### Bài 5 — Lập kế hoạch migration cho bảng lớn

Giả sử bảng có một triệu hàng với `status VARCHAR(20)` cho phép `NULL`. Tính năng mới yêu cầu `status NOT NULL DEFAULT 'NEW'`. Hãy mô tả:

- Cách kiểm tra bao nhiêu hàng còn `NULL` và nguồn gốc của các giá trị thiếu.
- Cách bảo đảm ứng dụng không tiếp tục ghi `NULL` trong lúc chuyển đổi.
- Cách điền dữ liệu cũ theo quy tắc nghiệp vụ và kiểm tra lại.
- Khi nào đặt `NOT NULL`, và cần dự liệu điều gì về khóa bảng hay thời gian thực thi.

Đáp án định hướng: đổi ứng dụng và thiết lập mặc định phù hợp, backfill có kiểm soát, xác minh không còn `NULL`, sau đó mới siết ràng buộc; kế hoạch phải tính đến ghi đồng thời và khả năng bảo trì hoặc triển khai nhiều giai đoạn.

## Kết luận

Trong SQL, **đổi kiểu dữ liệu**, **đổi giá trị mặc định** và **đổi khả năng nhận `NULL`** là ba thao tác khác nhau trên định nghĩa cột:

- **`ALTER COLUMN ... TYPE ... [USING ...]`** thay đổi cách biểu diễn và có thể chuyển đổi dữ liệu đang tồn tại.
- **`SET DEFAULT` / `DROP DEFAULT`** thay đổi giá trị được sử dụng khi thao tác ghi không cung cấp giá trị cho cột; chúng không tự sửa dữ liệu cũ.
- **`SET NOT NULL` / `DROP NOT NULL`** kiểm soát việc cột được phép thiếu giá trị; khi siết thành `NOT NULL`, phải xử lý các hàng thiếu trước.

Điểm quan trọng nhất khi sửa bảng đã có dữ liệu là **xác định chính xác ý nghĩa dữ liệu trước khi đổi schema**. Kiểm tra dữ liệu cũ, chuẩn bị cách chuyển đổi và backfill, phối hợp ứng dụng, rồi xác nhận cả cấu trúc lẫn hành vi ghi sau migration sẽ giúp thay đổi được triển khai có thể kiểm soát và tránh sai lệch dữ liệu.
