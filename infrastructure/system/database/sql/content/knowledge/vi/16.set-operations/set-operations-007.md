# Tên cột, ép kiểu và thứ tự kết quả sau hợp nhất

Trong **Database SQL**, các phép toán tập hợp như `UNION`, `UNION ALL`, `INTERSECT` và `EXCEPT` cho phép kết hợp hoặc so sánh **kết quả của nhiều câu `SELECT`**. Khác với `JOIN` — ghép các cột của những dòng có quan hệ — phép toán tập hợp đặt các kết quả **theo chiều dọc**, hoặc chọn những dòng chung/khác nhau giữa các tập kết quả.

Một câu SQL có thể chạy hợp lệ nhưng vẫn trả dữ liệu sai nếu người viết không hiểu ba quy tắc:

1. **Các cột được ghép theo vị trí**, không ghép theo tên.
2. **Tên cột của kết quả hợp nhất** được quyết định theo quy tắc của DBMS, thông thường dựa trên `SELECT` đầu tiên; kiểu dữ liệu phải tương thích ở từng vị trí.
3. **Thứ tự các dòng sau hợp nhất không được bảo đảm** nếu không có `ORDER BY` ở cấp kết quả cuối cùng.

Bài học tập trung vào ba vấn đề này, đồng thời giải thích cách chuẩn hóa tên và kiểu dữ liệu, cách sắp xếp sau `UNION`/`INTERSECT`/`EXCEPT`, tác động của `DISTINCT`, `NULL`, collation và cách viết truy vấn có thể bảo trì.

## 1. Phép toán tập hợp làm việc với những gì?

Giả sử có hai nguồn đơn hàng:

```text
Kênh ONLINE                          Kênh STORE
+------+----------+--------+         +------+----------+--------+
| id   | customer | amount |         | code | buyer    | amount |
+------+----------+--------+         +------+----------+--------+
| 101  | An       | 120.50 |         | S01  | An       | 120.50 |
| 102  | Bình     |  80.00 |         | S02  | Dũng     |  90.00 |
| 103  | Chi      | 120.50 |         | S03  | Chi      | 120.50 |
+------+----------+--------+         +------+----------+--------+
                     |
                     | Ghép SELECT theo chiều dọc
                     v
              Kết quả hợp nhất
              customer | amount
              ----------+--------
              An        | 120.50
              Bình      |  80.00
              Chi       | 120.50
              An        | 120.50
              Dũng      |  90.00
              Chi       | 120.50
```

Nếu giữ tất cả dòng của hai nguồn, đó là ý nghĩa của `UNION ALL`. Nếu loại các dòng trùng **toàn bộ cột được chọn**, dùng `UNION` mặc định, tương đương ý tưởng `UNION DISTINCT` trong các hệ hỗ trợ.

Các phép toán thường gặp:

| Phép toán | Ý nghĩa trên các dòng kết quả | Có tự loại dòng trùng? |
| --- | --- | --- |
| `UNION ALL` | Ghép tất cả dòng từ các nhánh | Không |
| `UNION` | Lấy các dòng có trong ít nhất một nhánh | Có, theo toàn bộ cột kết quả |
| `INTERSECT` | Lấy những dòng xuất hiện ở cả hai nhánh | Thông thường có |
| `EXCEPT` | Lấy các dòng có ở nhánh trái nhưng không có ở nhánh phải | Thông thường có |
| `INTERSECT ALL`, `EXCEPT ALL` | Phiên bản xét cả số lần xuất hiện | Chỉ trên DBMS hỗ trợ, có quy tắc bội số riêng |

Oracle Database có tên toán tử `MINUS` trong nhiều phiên bản để biểu diễn ý tưởng hiệu tập tương tự `EXCEPT`. Mức hỗ trợ `EXCEPT`, `INTERSECT` và dạng `ALL` cần kiểm tra theo phiên bản từng DBMS.

**Không phải phép toán tập hợp nào cũng “nối thêm dòng”.** `INTERSECT` và `EXCEPT` là các phép **chọn dòng theo quan hệ tập hợp**; chúng vẫn tuân theo nguyên tắc tương thích số lượng cột, vị trí, kiểu dữ liệu và thứ tự đầu ra.

## 2. Hai điều kiện cấu trúc trước khi hợp nhất

Để hợp nhất hai kết quả, cần quan tâm:

- **Số cột:** mỗi nhánh `SELECT` phải trả **cùng số lượng cột**.
- **Kiểu dữ liệu theo từng vị trí:** mỗi cặp cột cùng vị trí phải có kiểu **có thể đối chiếu/hoà giải** theo quy tắc DBMS.

Ví dụ đúng về số lượng cột:

```sql
-- PostgreSQL:
SELECT 1 AS id, 'An' AS name
UNION ALL
SELECT 2 AS code, 'Bình' AS customer_name;
```

Cả hai nhánh có **hai cột**. Tên `id` và `code` khác nhau nhưng không làm SQL sai; DBMS ghép **cột 1 với cột 1**, **cột 2 với cột 2**.

Ví dụ sai về số cột:

```sql
-- SAI: nhánh đầu có 2 cột; nhánh sau có 3 cột.
SELECT 1 AS id, 'An' AS name
UNION ALL
SELECT 2 AS id, 'Bình' AS name, 'VIP' AS segment;
```

Một truy vấn khác tuy có số cột bằng nhau nhưng có thể sai kiểu:

```sql
-- PostgreSQL: numeric và date ở cùng một vị trí
-- không phải kiểu UNION tương thích theo mặc định.
SELECT CAST(100.50 AS NUMERIC(12,2)) AS value
UNION ALL
SELECT DATE '2026-04-01';
```

**Nguyên tắc:** đừng chỉ nhìn số cột để kết luận có thể ghép. Cần xác định **mỗi vị trí diễn tả dữ liệu gì và kiểu chung hợp lệ là gì**.

## 3. Cột được ghép theo vị trí, không theo tên

Xét hai bảng hoặc hai nguồn có cùng ý nghĩa nhưng thứ tự chọn cột khác nhau.

```sql
-- PostgreSQL: chạy được vì hai cột đều có kiểu text tương thích,
-- nhưng kết quả ghép sai ý nghĩa.
SELECT
    'C01'::text AS customer_code,
    'An'::text AS customer_name

UNION ALL

SELECT
    'Bình'::text AS customer_name,
    'C02'::text AS customer_code;
```

Kết quả có **hai cột** mang tên từ nhánh đầu:

| customer_code | customer_name |
| --- | --- |
| C01 | An |
| **Bình** | **C02** |

Dòng thứ hai bị đảo dữ liệu. SQL không nhất thiết báo lỗi vì hai vị trí đều thuộc kiểu `text`.

Cách đúng là **đặt cột theo cùng thứ tự nghiệp vụ**:

```sql
SELECT
    'C01'::text AS customer_code,
    'An'::text AS customer_name

UNION ALL

SELECT
    'C02'::text AS customer_code,
    'Bình'::text AS customer_name;
```

Kết quả:

| customer_code | customer_name |
| --- | --- |
| C01 | An |
| C02 | Bình |

Sơ đồ ghép vị trí:

```text
Nhánh 1                      Nhánh 2
[customer_code, name]   +    [code, customer_name]
       |       |                 |       |
       +-------+-----------------+       |
               |                         |
       cột 1 <- vị trí 1         cột 2 <- vị trí 2

Không có bước tự tìm tên cột giống nhau để ghép.
```

Khi đọc một truy vấn `UNION` dài, nên kiểm tra từng nhánh theo **một danh sách cột chuẩn**. Việc đổi tên alias ở nhánh sau không tự sửa được lỗi **sai vị trí**.

## 4. Tên cột đầu ra thường lấy từ nhánh SELECT đầu tiên

Trong PostgreSQL, MySQL/MariaDB, SQL Server, SQLite và Oracle Database ở các cách dùng phổ biến, **tên cột của kết quả phép toán tập hợp** được xác định từ **danh sách cột đầu ra của `SELECT` đầu tiên** trong phép hợp nhất.

Ví dụ PostgreSQL:

```sql
SELECT
    101 AS order_id,
    'ONLINE' AS sales_channel,
    120.50::numeric(12,2) AS amount

UNION ALL

SELECT
    201 AS store_order_number,
    'STORE' AS source_type,
    90.00::numeric(12,2) AS total_value;
```

Ba cột kết quả mang tên:

```text
order_id | sales_channel | amount
---------+---------------+--------
101      | ONLINE        | 120.50
201      | STORE         |  90.00
```

Các alias của nhánh thứ hai — `store_order_number`, `source_type`, `total_value` — **không làm đổi** tên cột chung thành những tên đó.

Điều này quan trọng với ứng dụng, báo cáo, API và truy vấn ngoài. Ví dụ:

```sql
SELECT merged.order_id, merged.sales_channel, merged.amount
FROM (
    SELECT
        101 AS order_id,
        'ONLINE' AS sales_channel,
        120.50::numeric(12,2) AS amount

    UNION ALL

    SELECT
        201 AS store_order_number,
        'STORE' AS source_type,
        90.00::numeric(12,2) AS total_value
) AS merged;
```

`merged` công bố các tên `order_id`, `sales_channel` và `amount` — **không** công bố `merged.total_value`.

### Vì sao nên đặt alias tường minh ngay ở nhánh đầu?

Nếu nhánh đầu là biểu thức không có alias:

```sql
SELECT 120.50 * 2
UNION ALL
SELECT 90.00 * 2;
```

DBMS phải đặt tên hệ thống cho cột biểu thức đó. Tên có thể không thân thiện, không đồng nhất giữa DBMS và khó tham chiếu ở truy vấn ngoài. Hãy viết:

```sql
SELECT 120.50 * 2 AS doubled_amount
UNION ALL
SELECT 90.00 * 2 AS doubled_amount;
```

Viết cùng alias ở các nhánh sau **không bắt buộc để parser ghép cột**, nhưng giúp con người kiểm tra truy vấn: vị trí nào cũng có cùng ý nghĩa, dễ phát hiện thiếu/đảo cột trong code review.

### Tên đầu ra là giao diện của truy vấn

Nếu một báo cáo đang đọc cột `amount` từ kết quả UNION, sau này đổi alias của nhánh đầu thành `total` có thể làm hỏng đoạn SQL ngoài hoặc code lấy dữ liệu theo tên cột, dù số dòng và giá trị không đổi.

Vì thế, với truy vấn dùng lâu dài, nên coi **danh sách tên cột đầu ra là một giao diện cần ổn định**.

## 5. Dùng derived table hoặc CTE để chủ động đặt tên kết quả

Nếu không muốn người đọc phụ thuộc vào alias nhánh đầu, có thể **bọc phép hợp nhất trong bảng dẫn xuất** và đặt tên công bố ở lớp ngoài.

```sql
-- PostgreSQL:
SELECT
    combined.entity_key AS record_key,
    combined.display_name AS name_to_show
FROM (
    SELECT
        CAST(101 AS text) AS entity_key,
        'An'::text AS display_name

    UNION ALL

    SELECT
        'S01'::text AS store_code,
        'Bình'::text AS buyer_name
) AS combined;
```

Truy vấn con vẫn áp dụng quy tắc tên từ nhánh đầu; truy vấn ngoài đặt tên cho kết quả cuối là `record_key` và `name_to_show`.

Trên PostgreSQL, còn có thể đặt **danh sách tên cột theo vị trí** sau alias bảng dẫn xuất:

```sql
SELECT
    u.record_key,
    u.person_name
FROM (
    SELECT CAST(101 AS text), 'An'::text
    UNION ALL
    SELECT 'S01'::text, 'Bình'::text
) AS u(record_key, person_name);
```

Danh sách `(record_key, person_name)` gắn **theo vị trí** với hai cột của kết quả bên trong. Đây là cú pháp có hỗ trợ theo dialect; không nên chép nguyên sang mọi DBMS mà chưa kiểm tra. Đặt alias bên trong `SELECT` đầu tiên vẫn là cách dễ chuyển hệ.

### CTE giúp đọc các truy vấn hợp nhất dài

```sql
WITH combined AS (
    SELECT
        CAST(101 AS text) AS record_key,
        'ONLINE'::text AS source_name

    UNION ALL

    SELECT
        'S01'::text AS record_key,
        'STORE'::text AS source_name
)
SELECT record_key, source_name
FROM combined
ORDER BY source_name, record_key;
```

CTE (`WITH`) cho phép đặt tên khối kết quả và tái sử dụng trong câu truy vấn. Nó không tự tạo bảng lâu dài hay bảo đảm vật lý materialize dữ liệu. **Không mặc nhiên cho rằng CTE hoặc derived table sẽ nhanh hơn UNION trực tiếp**: bộ tối ưu có thể biến đổi chúng.

## 6. Chuẩn bị dữ liệu thực hành trên PostgreSQL

Các ví dụ dưới đây chạy với **PostgreSQL** trên database học tập. Hai bảng có **tên cột và kiểu dữ liệu không hoàn toàn giống nhau** để minh họa nhu cầu chuẩn hóa trước `UNION`. Chỉ tạo chúng trong môi trường được phép thực hành.

### 6.1. Tạo hai bảng nguồn

```sql
CREATE TABLE sql208_online_orders (
    online_id     INTEGER PRIMARY KEY,
    customer_name VARCHAR(80) NOT NULL,
    gross_amount  NUMERIC(12,2) NOT NULL,
    created_on    DATE NOT NULL
);

CREATE TABLE sql208_store_orders (
    store_code VARCHAR(20) PRIMARY KEY,
    buyer_name VARCHAR(80) NOT NULL,
    total_text VARCHAR(30) NOT NULL,
    sold_on    DATE NOT NULL
);
```

Bảng online lưu tiền bằng `NUMERIC(12,2)`, còn bảng cửa hàng **cố ý** lưu tiền bằng `VARCHAR(30)` dưới tên `total_text`. Đây chỉ là cấu trúc mô phỏng nguồn dữ liệu không đồng nhất; trong hệ thống nghiệp vụ, **không nên lưu số tiền bằng chuỗi văn bản** nếu có thể sử dụng kiểu số phù hợp.

### 6.2. Chèn dữ liệu

```sql
INSERT INTO sql208_online_orders
    (online_id, customer_name, gross_amount, created_on)
VALUES
    (101, 'An',   120.50, DATE '2026-04-01'),
    (102, 'Bình',  80.00, DATE '2026-04-02'),
    (103, 'Chi',  120.50, DATE '2026-04-03');

INSERT INTO sql208_store_orders
    (store_code, buyer_name, total_text, sold_on)
VALUES
    ('S01', 'An',   '120.50', DATE '2026-04-01'),
    ('S02', 'Dũng', '90.00',  DATE '2026-04-04'),
    ('S03', 'Chi',  '120.50', DATE '2026-04-03');
```

Bảng online có 3 dòng, cửa hàng có 3 dòng. Khách `An` và `Chi` có cùng **cặp tên + số tiền** ở cả hai nguồn; tình huống này giúp phân biệt `UNION` và `UNION ALL`.

## 7. Chuẩn hóa số lượng, vị trí, tên và kiểu cột

Hai bảng ở mục 6 có sơ đồ khác nhau:

| Vị trí chuẩn | Ý nghĩa cần trả | Cột online | Cột cửa hàng | Kiểu đích |
| ---: | --- | --- | --- | --- |
| 1 | Nguồn | Literal `'ONLINE'` | Literal `'STORE'` | `text` |
| 2 | Khóa dòng nguồn | `online_id` kiểu integer | `store_code` kiểu varchar | `text` |
| 3 | Tên khách | `customer_name` | `buyer_name` | `text` |
| 4 | Số tiền | `gross_amount` kiểu numeric | `total_text` kiểu varchar | `numeric(12,2)` |
| 5 | Ngày | `created_on` | `sold_on` | `date` |

Hãy đưa từng nhánh về **cùng giao diện**:

```sql
-- PostgreSQL:
SELECT
    'ONLINE'::text AS source_name,
    CAST(o.online_id AS text) AS record_key,
    CAST(o.customer_name AS text) AS customer_name,
    CAST(o.gross_amount AS numeric(12,2)) AS amount,
    CAST(o.created_on AS date) AS occurred_on
FROM sql208_online_orders AS o

UNION ALL

SELECT
    'STORE'::text AS source_name,
    CAST(s.store_code AS text) AS record_key,
    CAST(s.buyer_name AS text) AS customer_name,
    CAST(s.total_text AS numeric(12,2)) AS amount,
    CAST(s.sold_on AS date) AS occurred_on
FROM sql208_store_orders AS s;
```

Kết quả có 6 dòng và 5 cột:

| source_name | record_key | customer_name | amount | occurred_on |
| --- | --- | --- | ---: | --- |
| ONLINE | 101 | An | 120.50 | 2026-04-01 |
| ONLINE | 102 | Bình | 80.00 | 2026-04-02 |
| ONLINE | 103 | Chi | 120.50 | 2026-04-03 |
| STORE | S01 | An | 120.50 | 2026-04-01 |
| STORE | S02 | Dũng | 90.00 | 2026-04-04 |
| STORE | S03 | Chi | 120.50 | 2026-04-03 |

**Lưu ý:** thứ tự sáu dòng trong bảng minh họa chỉ để dễ đọc. Vì câu SQL **chưa có `ORDER BY`**, không được mặc nhiên coi đó là thứ tự truy xuất được bảo đảm.

### Vì sao giữ cả source_name và record_key?

Khóa `online_id = 101` của online không cùng miền với `store_code = 'S01'` của cửa hàng. Chỉ `CAST` chúng về `text` không làm các mã trở thành khóa toàn cục. Cặp `(source_name, record_key)` có thể đóng vai trò **định danh của một bản ghi nguồn** trong kết quả hợp nhất khi mỗi nguồn bảo đảm khóa riêng là duy nhất.

Khi phân trang hoặc cần giải thích dòng đến từ đâu, việc giữ định danh nguồn giúp xác định thứ tự ổn định và xử lý trùng lặp có chủ đích.

## 8. CAST giải quyết sự không tương thích kiểu như thế nào?

Hai phép toán có số cột bằng nhau nhưng kiểu không tương thích có thể bị từ chối. Trong PostgreSQL, truy vấn sau không nên dùng:

```sql
-- PostgreSQL: numeric và varchar không tạo cặp kiểu UNION
-- tương thích chỉ vì giá trị chữ nhìn giống một con số.
SELECT gross_amount AS amount
FROM sql208_online_orders

UNION ALL

SELECT total_text AS amount
FROM sql208_store_orders;
```

Cách phù hợp là **chuyển nguồn lưu tiền dạng text về numeric trước khi hợp nhất**:

```sql
SELECT
    gross_amount AS amount
FROM sql208_online_orders

UNION ALL

SELECT
    CAST(total_text AS numeric(12,2)) AS amount
FROM sql208_store_orders;
```

Với dữ liệu mẫu, tất cả chuỗi `total_text` đều chuyển được thành số. Nếu có chuỗi `'không rõ'` hoặc dấu phân cách tiền theo locale không đúng cú pháp, `CAST` có thể **báo lỗi**. Không coi `CAST` là công cụ tự động làm sạch mọi dữ liệu văn bản.

### Những chuyển kiểu cần cân nhắc

| Tình huống | Ví dụ | Cách xử lý có chủ đích |
| --- | --- | --- |
| `INTEGER` cùng vị trí với `BIGINT` | Mã/số lượng lớn | Chọn kiểu đủ rộng theo quy tắc DBMS |
| `INTEGER` cùng vị trí với mã `VARCHAR` | `101` và `'S01'` | `CAST(integer_key AS text)` nếu cả hai thực chất là mã hiển thị |
| `NUMERIC` cùng vị trí với văn bản số | `120.50` và `'120.50'` | Chuẩn hóa văn bản, `CAST` sang numeric phù hợp |
| `DATE` cùng vị trí với `TIMESTAMP` | Ngày với ngày giờ | Quyết định có cần giờ hay không, rồi ép kiểu rõ ràng |
| `DATE` cùng vị trí với chuỗi ngày | `DATE '2026-04-01'` và `'2026-04-01'` | Chuyển chuỗi có định dạng được kiểm soát thành `DATE` |
| `TEXT` với `VARCHAR` | Tên khách ở hai bảng | Thường tương thích theo engine, nhưng có thể chuẩn hóa kiểu nếu giao diện cần ổn định |
| `NULL` không có kiểu rõ | `SELECT NULL` ở một nhánh | Dùng `CAST(NULL AS target_type)` để biểu đạt ý định |
| `DECIMAL` với số thực dấu phẩy động | `NUMERIC` và `FLOAT` | Chọn mức chính xác phù hợp, tránh mất độ chính xác tiền tệ |

**Không phải mọi kiểu đều có thể chuyển an toàn.** Ép `'S01'` thành integer sẽ lỗi; ép số tiền sang kiểu nguyên có thể mất phần thập phân hoặc làm tròn theo quy tắc engine; ép timestamp sang date làm mất giờ. Trước khi viết `CAST`, cần xác định kiểu đích phản ánh **ý nghĩa dữ liệu**, không chỉ giúp SQL parser chấp nhận.

### CAST và chuyển kiểu ngầm (implicit conversion)

Một số DBMS tự tìm kiểu chung giữa hai nhánh, chẳng hạn `integer` và `bigint` trong nhiều trường hợp. Nhưng quy tắc suy luận kiểu có thể khác giữa PostgreSQL, SQL Server, MySQL/MariaDB, SQLite và Oracle. Việc một query chạy trên engine này **không bảo đảm** nó chạy hoặc cho cùng kiểu/giá trị trên engine khác.

Với truy vấn dùng trong báo cáo hoặc API, **ép kiểu tường minh ở ranh giới các nguồn không đồng nhất** giúp định nghĩa giao diện nhất quán và tránh phụ thuộc quá nhiều vào implicit conversion.

## 9. Kiểu kết quả được suy luận theo vị trí, không theo alias

Xét:

```sql
-- PostgreSQL:
SELECT
    CAST(10 AS integer) AS value
UNION ALL
SELECT
    CAST(20 AS bigint) AS value;
```

Tên cột chung là `value`. Nhưng **kiểu của `value` là kiểu kết quả mà PostgreSQL suy luận cho cả hai nhánh**, không đơn giản bằng kiểu của nhánh đầu. Trong ví dụ này, hệ có thể nâng kiểu kết quả lên `bigint` để chứa cả hai nguồn.

Tương tự, một nhánh `VARCHAR(20)` và một nhánh `TEXT` có thể dẫn tới một kiểu chuỗi chung theo quy tắc DBMS. Alias của nhánh đầu định danh cột, còn **cơ chế hòa giải kiểu** xác định kiểu trả về.

### Độ dài và độ chính xác dữ liệu

Với chuỗi, khác biệt `VARCHAR(20)` và `VARCHAR(200)` có thể liên quan đến giới hạn kiểu trả về của một số DBMS. Với số thập phân, sự kết hợp `DECIMAL(10,2)` và `DECIMAL(18,4)` có thể tạo quy tắc về **precision** và **scale**; không nên tự khẳng định kết quả luôn có chính xác định nghĩa kiểu của nhánh đầu.

Trong ứng dụng, kiểm tra metadata cột kết quả hoặc tạo giao diện bằng `CAST(... AS DECIMAL(p,s))` theo yêu cầu nghiệp vụ. Với tiền, số liệu lớn hoặc phép cộng/tổng hợp, lựa chọn precision và scale phải đủ rộng cho kết quả thực tế; một `CAST` quá hẹp có thể gây tràn hoặc làm tròn.

### Kiểu NULL cần được chỉ định rõ

Ví dụ muốn có một cột ngày ở cả hai nguồn, nhưng cửa hàng chưa lưu ngày:

```sql
SELECT
    created_on AS occurred_on
FROM sql208_online_orders

UNION ALL

SELECT
    CAST(NULL AS DATE) AS occurred_on
FROM sql208_store_orders;
```

Nhánh thứ hai vẫn phải có **một cột** ở vị trí ngày; `CAST(NULL AS DATE)` nói rõ kiểu đích và cho phép hợp nhất với ngày của nhánh đầu.

Có thể nhiều DBMS suy ra kiểu cho literal `NULL` không có `CAST`, nhưng **không nên phụ thuộc vào điều đó** trong truy vấn có nhiều tầng, nhiều nguồn hoặc phải chạy trên các hệ khác nhau.

## 10. UNION ALL giữ mọi dòng; UNION loại dòng trùng theo toàn bộ cột

Để thấy rõ khác biệt, tạm chỉ chọn hai cột **tên khách và số tiền**:

```sql
-- PostgreSQL: sáu dòng (giữ lần xuất hiện ở mỗi nguồn).
SELECT
    customer_name AS person_name,
    gross_amount AS amount
FROM sql208_online_orders

UNION ALL

SELECT
    buyer_name AS buyer,
    CAST(total_text AS numeric(12,2)) AS value
FROM sql208_store_orders;
```

Có sáu dòng, trong đó cặp `('An',120.50)` xuất hiện hai lần và cặp `('Chi',120.50)` cũng xuất hiện hai lần.

Nếu thay `UNION ALL` bằng `UNION`:

```sql
-- PostgreSQL: chỉ còn các cặp (person_name, amount) khác nhau.
SELECT
    customer_name AS person_name,
    gross_amount AS amount
FROM sql208_online_orders

UNION

SELECT
    buyer_name AS buyer,
    CAST(total_text AS numeric(12,2)) AS value
FROM sql208_store_orders

ORDER BY person_name, amount;
```

Kết quả **bốn dòng**:

| person_name | amount |
| --- | ---: |
| An | 120.50 |
| Bình | 80.00 |
| Chi | 120.50 |
| Dũng | 90.00 |

**Dòng nào được coi là trùng?** Cả **hai cột được trả ra** phải tương đương theo quy tắc so sánh của toán tử/DBMS. Cùng tên khác số tiền không phải một dòng trùng; cùng số tiền khác tên cũng không phải dòng trùng.

### Thêm cột nguồn sẽ thay đổi tiêu chí loại trùng

Nếu đưa `source_name` vào danh sách `SELECT`:

```sql
SELECT
    'ONLINE'::text AS source_name,
    customer_name AS person_name,
    gross_amount AS amount
FROM sql208_online_orders

UNION

SELECT
    'STORE'::text,
    buyer_name,
    CAST(total_text AS numeric(12,2))
FROM sql208_store_orders

ORDER BY source_name, person_name, amount;
```

thì các dòng `An` của ONLINE và STORE **không còn trùng toàn bộ cột**, vì `source_name` khác nhau. Kết quả có thể giữ cả sáu dòng.

Đây không phải lỗi của `UNION` mà là thay đổi **đơn vị so sánh**: khi có nguồn, `('ONLINE','An',120.50)` khác `('STORE','An',120.50)`.

Nếu cần “khách hàng duy nhất” theo định danh khách hàng, không nên xem tên + số tiền là khóa người dùng; hãy chọn **định danh nghiệp vụ đúng** rồi mới xác định `DISTINCT`.

## 11. INTERSECT và EXCEPT vẫn so toàn bộ dòng theo vị trí

Ngoài `UNION`, tên cột và kiểu dữ liệu cũng quan trọng khi tìm giao hoặc hiệu của hai kết quả.

### INTERSECT: chỉ những dòng cùng xuất hiện ở hai bên

```sql
-- PostgreSQL:
SELECT
    customer_name AS person_name,
    gross_amount AS amount
FROM sql208_online_orders

INTERSECT

SELECT
    buyer_name AS buyer,
    CAST(total_text AS numeric(12,2)) AS value
FROM sql208_store_orders

ORDER BY person_name, amount;
```

Dữ liệu mẫu có **hai cặp chung**:

| person_name | amount |
| --- | ---: |
| An | 120.50 |
| Chi | 120.50 |

Alias `buyer`, `value` của nhánh sau không đổi tên cột đầu ra; `person_name` và `amount` là tên dùng ở kết quả.

### EXCEPT: dòng có ở bên trái nhưng không có bên phải

```sql
-- PostgreSQL:
SELECT
    customer_name AS person_name,
    gross_amount AS amount
FROM sql208_online_orders

EXCEPT

SELECT
    buyer_name AS buyer,
    CAST(total_text AS numeric(12,2)) AS value
FROM sql208_store_orders

ORDER BY person_name, amount;
```

Kết quả là **một cặp**:

| person_name | amount |
| --- | ---: |
| Bình | 80.00 |

Nếu **đổi chỗ hai nhánh**:

```sql
SELECT
    buyer_name AS person_name,
    CAST(total_text AS numeric(12,2)) AS amount
FROM sql208_store_orders

EXCEPT

SELECT
    customer_name AS customer,
    gross_amount AS amount_value
FROM sql208_online_orders

ORDER BY person_name;
```

kết quả là `('Dũng',90.00)`, vì `EXCEPT` **không giao hoán**: `A EXCEPT B` khác `B EXCEPT A`.

### Phép giao/hiệu cũng không tự là khóa-join

`INTERSECT` với cặp `(person_name, amount)` chỉ tìm cặp giá trị có mặt ở cả nguồn; nó không kiểm tra một khách hàng có **cùng ID** trong hai hệ. Nếu cần so sánh theo `customer_id` hoặc `(tenant_id, customer_id)`, hãy chiếu đúng khóa đó và chuẩn hóa kiểu/giá trị trước phép toán tập hợp.

## 12. NULL và phép loại trùng trong toán tử tập hợp

`NULL` có hai đặc điểm dễ gây nhầm:

- Trong điều kiện thông thường, `NULL = NULL` không trả `TRUE` mà trả trạng thái UNKNOWN.
- Trong cơ chế **loại dòng trùng của các toán tử tập hợp**, các giá trị `NULL` ở cùng vị trí có thể được xem **không phân biệt** để xác định hai dòng giống nhau.

Ví dụ PostgreSQL:

```sql
-- UNION loại dòng trùng: một dòng NULL.
SELECT CAST(NULL AS integer) AS x
UNION
SELECT CAST(NULL AS integer) AS x;
```

Kết quả chỉ có **một dòng `NULL`**.

Trong khi:

```sql
-- UNION ALL giữ đủ hai dòng NULL.
SELECT CAST(NULL AS integer) AS x
UNION ALL
SELECT CAST(NULL AS integer) AS x;
```

trả **hai dòng `NULL`**.

`INTERSECT` cũng có thể tìm phần chung là một dòng `NULL`:

```sql
SELECT CAST(NULL AS integer) AS x
INTERSECT
SELECT CAST(NULL AS integer) AS x;
```

Kết quả có một dòng `NULL`.

Còn:

```sql
SELECT CAST(NULL AS integer) AS x
EXCEPT
SELECT CAST(NULL AS integer) AS x;
```

không trả dòng nào, vì hai tập kết quả có cùng dòng theo phép so sánh dành cho loại trùng trong set operation.

### NULL trong dòng nhiều cột

`UNION` xem xét **cả bộ cột**. Hai dòng `(1, NULL)` và `(1, NULL)` được xem trùng trong loại trùng của `UNION`; nhưng `(1, NULL)` khác `(2, NULL)` vì vị trí đầu khác nhau.

Không dùng trực giác `NULL = NULL` trong `WHERE` để suy ra kết quả `UNION`/`INTERSECT`/`EXCEPT`. Hai ngữ cảnh có **quy tắc so sánh khác nhau**.

## 13. Collation và văn bản ảnh hưởng DISTINCT lẫn ORDER BY

Khi các cột là chuỗi, **collation** (quy tắc đối chiếu) có thể quyết định:

- `'An'` và `'an'` có được coi tương đương không.
- Chuỗi có dấu và không dấu có được coi tương đương trong một số trường hợp không.
- Thứ tự sắp xếp của chữ hoa, chữ thường và ký tự tiếng Việt.
- Các chuỗi chứa khoảng trắng cuối, ký tự Unicode khác biểu diễn có được xử lý ra sao theo engine/kiểu/collation.

Ví dụ:

```sql
SELECT 'An' AS person_name
UNION
SELECT 'an' AS person_name;
```

Số dòng có thể phụ thuộc vào **DBMS, collation và quy tắc so sánh**. Không được đưa ra một khẳng định chung rằng luôn có một hoặc hai dòng.

Trên PostgreSQL, có thể chủ động gắn collation `"C"` khi cần phép so sánh chuỗi theo quy tắc đó:

```sql
-- PostgreSQL:
SELECT ('An'::text COLLATE "C") AS person_name
UNION
SELECT ('an'::text COLLATE "C") AS person_name
ORDER BY person_name;
```

Với collation `"C"`, hai chuỗi khác nhau và được giữ là hai dòng. Cú pháp điều chỉnh collation, cách hòa giải collation từ nhiều nhánh và khả năng dùng collation đặc biệt khác nhau giữa các DBMS.

**Chuẩn hóa dữ liệu** và **chọn collation** là hai quyết định khác nhau. Nếu báo cáo cần đếm khách hàng duy nhất, điều kiện đúng có thể phải dựa trên ID và quy tắc trùng thực thể, chứ không chỉ dựa trên chữ hoa/thường của tên.

## 14. Không có ORDER BY thì không có thứ tự kết quả được bảo đảm

Hãy xét:

```sql
SELECT customer_name AS person_name
FROM sql208_online_orders

UNION ALL

SELECT buyer_name AS person_name
FROM sql208_store_orders;
```

Người viết có thể thấy ba tên online xuất hiện trước rồi ba tên store. Nhưng SQL **không bảo đảm** `UNION ALL` luôn trả nhánh đầu trước nhánh sau theo thứ tự dòng gốc, cũng không bảo đảm kết quả giữ thứ tự chèn dữ liệu.

Với `UNION`, `INTERSECT` hoặc `EXCEPT`, engine còn có thể dùng hash/sort để loại trùng và so sánh tập hợp. Thứ tự đầu ra có thể thay đổi theo execution plan, version, số dòng hoặc chỉ mục.

**Không nên suy diễn:**

- `UNION ALL` = “các dòng nhánh đầu luôn nằm trước các dòng nhánh sau”.
- `UNION` = “kết quả đã tự sắp xếp theo alphabet”.
- `INTERSECT` = “kết quả theo thứ tự của nguồn trái”.
- `EXCEPT` = “kết quả theo ID tăng vì engine dùng index”.

Một kết quả **trông có thứ tự** không có nghĩa thứ tự đó là hợp đồng của câu SQL.

## 15. ORDER BY cuối câu áp dụng cho toàn bộ kết quả hợp nhất

Muốn sắp xếp kết quả sau phép toán tập hợp, đặt `ORDER BY` ở **cuối biểu thức hợp nhất**:

```sql
-- PostgreSQL:
SELECT
    customer_name AS person_name,
    gross_amount AS amount
FROM sql208_online_orders

UNION ALL

SELECT
    buyer_name AS buyer,
    CAST(total_text AS numeric(12,2)) AS value
FROM sql208_store_orders

ORDER BY amount DESC, person_name ASC;
```

`ORDER BY amount DESC, person_name ASC` sắp xếp **cả sáu dòng** sau khi ghép, không chỉ nhánh cửa hàng.

Cần phân biệt hai thao tác:

1. **Hợp nhất:** quyết định dòng nào có mặt và có loại trùng hay không.
2. **Sắp xếp:** quyết định trình tự trình bày những dòng đã có trong kết quả.

Đổi thứ tự `ORDER BY` **không tự đổi** bộ giá trị do `UNION`/`INTERSECT`/`EXCEPT` xác định (trừ khi truy vấn còn có `LIMIT`/`FETCH` áp dụng lên kết quả đã sắp xếp).

### ORDER BY dùng tên cột của kết quả, không lấy alias nhánh sau

Ở câu trên, nhánh đầu đặt tên `person_name`, `amount`; nhánh sau đặt `buyer`, `value`. Trên PostgreSQL, dùng:

```sql
ORDER BY amount DESC, person_name ASC
```

là đúng. Dùng `ORDER BY value` hoặc `ORDER BY buyer` như thể chúng là tên cột chung có thể gây lỗi vì hai tên đó chỉ là alias ở nhánh sau.

### Thứ tự khi có giá trị bằng nhau

Ngay cả khi dùng `ORDER BY amount DESC`, các dòng có cùng `amount` vẫn **đồng hạng**. Nếu phân trang, xuất dữ liệu theo thứ tự tái lập hoặc so sánh hai lần chạy, hãy thêm khóa phụ đủ phân biệt:

```sql
SELECT
    'ONLINE'::text AS source_name,
    CAST(online_id AS text) AS record_key,
    customer_name AS person_name,
    gross_amount AS amount
FROM sql208_online_orders

UNION ALL

SELECT
    'STORE'::text,
    store_code,
    buyer_name,
    CAST(total_text AS numeric(12,2))
FROM sql208_store_orders

ORDER BY amount DESC, source_name ASC, record_key ASC;
```

Trong ví dụ, cặp `(source_name, record_key)` là duy nhất vì khóa của mỗi bảng nguồn không trùng. Nó đóng vai trò **tie-breaker**, tạo thứ tự xác định khi số tiền bằng nhau.

Nếu dữ liệu nguồn cho phép một `record_key` lặp lại trong cùng `source_name`, thứ tự này chưa đủ toàn phần; cần bổ sung một định danh dòng duy nhất hoặc quy tắc khác.

## 16. ORDER BY theo vị trí cột và rủi ro khi thay đổi SELECT

Nhiều DBMS cho phép chỉ định vị trí cột kết quả bằng số thứ tự bắt đầu từ 1:

```sql
-- PostgreSQL: cột 1 = person_name; cột 2 = amount.
SELECT
    customer_name AS person_name,
    gross_amount AS amount
FROM sql208_online_orders

UNION ALL

SELECT
    buyer_name,
    CAST(total_text AS numeric(12,2))
FROM sql208_store_orders

ORDER BY 2 DESC, 1 ASC;
```

Ở đây:

- `ORDER BY 2 DESC`: sắp theo **cột thứ hai**, tức `amount`.
- `ORDER BY 1 ASC`: khi số tiền bằng nhau, sắp theo **cột thứ nhất**, tức `person_name`.

Đây không phải `ORDER BY` theo **số 2** như một giá trị dữ liệu, cũng không phải thứ tự nhánh thứ hai. Số `1` và `2` là **vị trí trong danh sách cột kết quả**.

### Vì sao ORDER BY vị trí dễ lỗi?

Nếu sau này người khác thêm cột `source_name` vào trước `person_name`:

```sql
SELECT source_name, person_name, amount
...
ORDER BY 2 DESC, 1 ASC;
```

thì `2` không còn là `amount`, mà là `person_name`. SQL có thể vẫn chạy nhưng kết quả bị sắp xếp theo **cột khác**.

Vì vậy, trong truy vấn báo cáo và code ứng dụng dùng lâu dài, **ưu tiên ORDER BY bằng tên cột đầu ra rõ nghĩa**. Thứ tự số phù hợp cho các truy vấn ngắn có cấu trúc ổn định hoặc khi dialect cần một cách tham chiếu đơn giản, nhưng phải được kiểm tra nếu danh sách SELECT thay đổi.

## 17. Giới hạn ORDER BY biểu thức trực tiếp sau UNION trên PostgreSQL

Với một `SELECT` thông thường, có thể sắp bằng biểu thức:

```sql
SELECT customer_name
FROM sql208_online_orders
ORDER BY LOWER(customer_name);
```

Nhưng trong PostgreSQL, khi `ORDER BY` áp dụng **trực tiếp cho kết quả của `UNION`/`INTERSECT`/`EXCEPT`**, danh sách sắp xếp bị giới hạn ở **tên cột đầu ra hoặc vị trí cột**, không phải biểu thức tùy ý:

```sql
-- PostgreSQL: không dùng biểu thức LOWER(...) trực tiếp
-- trong ORDER BY của kết quả UNION.
SELECT customer_name AS person_name
FROM sql208_online_orders
UNION ALL
SELECT buyer_name
FROM sql208_store_orders
ORDER BY LOWER(person_name);
```

Cách xử lý là **bọc hợp nhất trong một derived table** rồi sắp ở truy vấn ngoài:

```sql
SELECT
    u.person_name
FROM (
    SELECT customer_name AS person_name
    FROM sql208_online_orders

    UNION ALL

    SELECT buyer_name
    FROM sql208_store_orders
) AS u
ORDER BY LOWER(u.person_name), u.person_name;
```

Bây giờ `u.person_name` là cột của nguồn `u` trong một truy vấn `SELECT` thông thường, nên `ORDER BY LOWER(u.person_name)` hợp lệ.

### Sắp theo cột không muốn hiển thị

Một trường hợp khác: cần sắp theo `occurred_on` nhưng kết quả cuối chỉ hiển thị tên và tiền.

Có thể công bố **khóa sắp xếp ở bên trong**, rồi ẩn nó ở danh sách `SELECT` ngoài:

```sql
SELECT
    u.person_name,
    u.amount
FROM (
    SELECT
        customer_name AS person_name,
        gross_amount AS amount,
        created_on AS sort_day,
        'ONLINE'::text AS source_name,
        CAST(online_id AS text) AS record_key
    FROM sql208_online_orders

    UNION ALL

    SELECT
        buyer_name,
        CAST(total_text AS numeric(12,2)),
        sold_on,
        'STORE'::text,
        store_code
    FROM sql208_store_orders
) AS u
ORDER BY u.sort_day DESC, u.source_name, u.record_key;
```

Kết quả chỉ **hiển thị hai cột** `person_name` và `amount` nhưng được sắp theo **ngày + khóa phụ**. Ở truy vấn ngoài thông thường không có `DISTINCT`, có thể `ORDER BY` những cột của nguồn `u` dù không đưa chúng ra danh sách hiển thị.

**Đừng dùng cách “thêm khóa nguồn vào UNION DISTINCT rồi ẩn ở ngoài” mà tưởng ý nghĩa DISTINCT không đổi.** Một khi đưa `source_name`/`record_key` vào phép `UNION` bên trong, tiêu chí trùng đã đổi; những cặp tên + tiền giống nhau giữa hai nguồn có thể trở thành hai dòng khác nhau. Nếu yêu cầu là một dòng duy nhất cho mỗi cặp, phải thiết kế lớp distinct và quy tắc chọn ngày/khóa sort nhất quán với định nghĩa đó.

## 18. ORDER BY bên trong từng nhánh không thay cho ORDER BY cuối

Một số người viết:

```sql
-- Không nên coi đây là một mẫu SQL di động để sắp thứ tự
-- cuối cùng: ORDER BY được đặt riêng ở mỗi nhánh.
SELECT customer_name AS person_name, gross_amount AS amount
FROM sql208_online_orders
ORDER BY amount DESC

UNION ALL

SELECT buyer_name, CAST(total_text AS numeric(12,2))
FROM sql208_store_orders
ORDER BY amount DESC;
```

Trên nhiều DBMS, cú pháp này **không hợp lệ** nếu không có dấu ngoặc hoặc các cấu trúc đặc thù. Ngay cả khi engine cho phép sort trong từng nhánh, điều đó **không bảo đảm** kết quả ghép được sắp tổng thể.

Cần quyết định mục tiêu:

- **Sắp toàn bộ sau hợp nhất:** một `ORDER BY` ở cuối.
- **Chọn TOP N từ mỗi nguồn trước khi hợp nhất:** dùng subquery có `ORDER BY` + `LIMIT`/`FETCH` đúng dialect trong từng nhánh, sau đó `ORDER BY` kết quả ngoài nếu cần.
- **Ưu tiên nhánh A trước nhánh B khi hiển thị:** xuất thêm `source_rank` và sắp theo nó, không dựa vào thứ tự viết nhánh.

### Chọn 2 giao dịch có số tiền lớn nhất từ mỗi nguồn

Ví dụ PostgreSQL:

```sql
SELECT
    u_online.source_name,
    u_online.record_key,
    u_online.person_name,
    u_online.amount
FROM (
    SELECT
        'ONLINE'::text AS source_name,
        CAST(online_id AS text) AS record_key,
        customer_name AS person_name,
        gross_amount AS amount
    FROM sql208_online_orders
    ORDER BY gross_amount DESC, online_id ASC
    LIMIT 2
) AS u_online

-- Cấu trúc trên là một nguồn SELECT độc lập. Để ghép hai nguồn
-- bằng UNION ALL trong một derived table, xem câu hoàn chỉnh dưới đây.
;
```

Câu trên chỉ minh họa một nhánh chọn TOP 2; **không phải câu hợp nhất** vì chưa có nguồn thứ hai. Câu đầy đủ:

```sql
-- PostgreSQL:
SELECT
    merged.source_name,
    merged.record_key,
    merged.person_name,
    merged.amount
FROM (
    SELECT source_name, record_key, person_name, amount
    FROM (
        SELECT
            'ONLINE'::text AS source_name,
            CAST(online_id AS text) AS record_key,
            customer_name AS person_name,
            gross_amount AS amount
        FROM sql208_online_orders
        ORDER BY gross_amount DESC, online_id ASC
        LIMIT 2
    ) AS online_top

    UNION ALL

    SELECT source_name, record_key, person_name, amount
    FROM (
        SELECT
            'STORE'::text AS source_name,
            store_code AS record_key,
            buyer_name AS person_name,
            CAST(total_text AS numeric(12,2)) AS amount
        FROM sql208_store_orders
        ORDER BY CAST(total_text AS numeric(12,2)) DESC, store_code ASC
        LIMIT 2
    ) AS store_top
) AS merged
ORDER BY merged.amount DESC, merged.source_name, merged.record_key;
```

Các lớp có vai trò:

1. `online_top` chọn **2 đơn lớn nhất của ONLINE**.
2. `store_top` chọn **2 đơn lớn nhất của STORE**.
3. `UNION ALL` ghép hai tập đã giới hạn, tối đa 4 dòng.
4. `ORDER BY` ngoài cùng sắp **bốn dòng chung** và thêm khóa phụ để ổn định.

Nếu viết `UNION ALL` trên toàn bộ sáu đơn trước rồi mới `LIMIT 2`, ý nghĩa đổi thành **chọn hai đơn lớn nhất của toàn bộ hai nguồn**, không phải hai đơn mỗi nguồn.

### Muốn hiển thị nhánh online trước?

Thêm một cột có chủ đích:

```sql
SELECT
    1 AS source_rank,
    'ONLINE'::text AS source_name,
    customer_name AS person_name
FROM sql208_online_orders

UNION ALL

SELECT
    2 AS source_rank,
    'STORE'::text AS source_name,
    buyer_name AS person_name
FROM sql208_store_orders

ORDER BY source_rank, person_name;
```

Nếu cần ẩn `source_rank` khỏi giao diện, bọc kết quả trong derived table và chỉ xuất các cột muốn hiển thị, nhưng giữ `ORDER BY source_rank` ở ngoài.

## 19. Phép toán tập hợp kết hợp nhiều nhánh: cần kiểm soát thứ tự áp dụng

Ví dụ:

```sql
SELECT ...
UNION
SELECT ...
INTERSECT
SELECT ...;
```

có thể gây hiểu lầm về **thứ tự ưu tiên toán tử**. Một số DBMS áp dụng `INTERSECT` với độ ưu tiên cao hơn `UNION`/`EXCEPT`; ở những dialect/phiên bản khác, quy tắc kết hợp có thể khác.

Nếu biểu thức có **hơn một loại toán tử tập hợp**, hãy dùng **dấu ngoặc hoặc CTE/derived table** để thể hiện nhóm phép toán theo mục tiêu:

```sql
-- PostgreSQL: lấy (A UNION B) rồi chỉ giữ dòng có trong C.
WITH combined_ab AS (
    SELECT person_name, amount FROM source_a
    UNION
    SELECT person_name, amount FROM source_b
)
SELECT person_name, amount FROM combined_ab
INTERSECT
SELECT person_name, amount FROM source_c;
```

`source_a`, `source_b`, `source_c` ở đây là các tên bảng minh họa, không thuộc bộ dữ liệu thực hành. Phép `INTERSECT` được áp dụng **trên kết quả của `combined_ab`**, đúng mục tiêu “(A hợp B) giao C”.

Nếu cần sắp xếp cuối cùng:

```sql
WITH combined_ab AS (
    SELECT person_name, amount FROM source_a
    UNION
    SELECT person_name, amount FROM source_b
)
SELECT person_name, amount FROM combined_ab
INTERSECT
SELECT person_name, amount FROM source_c
ORDER BY person_name, amount;
```

`ORDER BY` cuối sắp kết quả sau khi phép giao hoàn tất. Không coi cách viết truy vấn nhiều tầng mà thiếu dấu ngoặc là một phương án di động nếu thứ tự phép toán mang ý nghĩa nghiệp vụ.

## 20. Cẩn trọng khi LIMIT, OFFSET và phân trang sau hợp nhất

Một API có thể hợp nhất nhiều nguồn đơn hàng và phân trang:

```sql
SELECT
    'ONLINE'::text AS source_name,
    CAST(online_id AS text) AS record_key,
    customer_name AS person_name,
    gross_amount AS amount,
    created_on AS occurred_on
FROM sql208_online_orders

UNION ALL

SELECT
    'STORE'::text,
    store_code,
    buyer_name,
    CAST(total_text AS numeric(12,2)),
    sold_on
FROM sql208_store_orders

ORDER BY occurred_on DESC, source_name ASC, record_key ASC
LIMIT 3 OFFSET 0;
```

`ORDER BY` xác định thứ tự **của tập kết quả hợp nhất**, sau đó `LIMIT 3 OFFSET 0` lấy trang đầu gồm tối đa ba dòng.

Trang thứ hai có thể dùng `LIMIT 3 OFFSET 3` với **chính cùng bộ lọc và thứ tự**.

### Thứ tự phải đủ phân biệt

Nếu chỉ dùng `ORDER BY occurred_on DESC`, nhiều đơn cùng ngày sẽ đồng hạng; trang 1 và trang 2 có thể trùng/bỏ sót khi bộ tối ưu chọn thứ tự khác nhau cho các dòng cùng ngày. Thêm `source_name` và `record_key` giúp xác định một thứ tự ổn định khi định danh nguồn là duy nhất.

### Dữ liệu thay đổi giữa các lần tải trang

Ngay cả khi có `ORDER BY` toàn phần, `OFFSET` vẫn đếm theo **vị trí của tập kết quả hiện tại**. Nếu có đơn mới chen vào trước ranh giới, một dòng ở trang trước có thể lặp lại ở trang sau. Nếu một dòng bị xóa hoặc thay đổi bộ lọc/sort, một dòng chưa xem có thể bị bỏ qua.

Do đó:

- Với danh sách nhỏ, ít thay đổi, cần đi trực tiếp đến trang N: `LIMIT/OFFSET` có thể phù hợp.
- Với feed liên tục thay đổi, cuộn “Xem tiếp”: cân nhắc **keyset/seek pagination** trên bộ khóa sort của kết quả đã chuẩn hóa.
- Với export cần mỗi dòng đúng một lần tại cùng thời điểm: cân nhắc snapshot hoặc tập ID đã cố định; chỉ có `ORDER BY` không thể thay thế yêu cầu nhất quán dữ liệu.

### Keyset trên kết quả hợp nhất

Giả sử sắp `occurred_on DESC, source_name ASC, record_key ASC`. Cursor phải chứa **đủ bộ khóa sắp xếp**, và điều kiện lấy trang sau phải tuân theo **thứ tự hỗn hợp DESC/ASC**. Không thể đơn giản dùng một phép so sánh tuple `<` cho tất cả cột nếu hướng sort khác nhau.

Cách diễn đạt dễ hiểu hơn là chọn **cùng một quy tắc sort** và xây dựng điều kiện từ điển phù hợp:

- Ngày **nhỏ hơn** ngày của dòng cuối → nằm sau vì ngày DESC.
- Nếu cùng ngày, `source_name` **lớn hơn** nguồn của dòng cuối → nằm sau vì nguồn ASC.
- Nếu cùng ngày và nguồn, `record_key` **lớn hơn** khóa dòng cuối → nằm sau vì khóa ASC.

Cần lưu ý collation của các cột chuỗi và không `NULL` ở bộ khóa nếu muốn điều kiện cursor có ngữ nghĩa rõ ràng. Keyset giảm tác động dịch vị trí do insert ở phía trước, nhưng không tự tạo snapshot nếu dữ liệu bị update/delete.

## 21. Tên cột và ORDER BY trong truy vấn dùng UNION rồi JOIN

Một truy vấn hợp nhất cũng có thể là nguồn cho `JOIN`:

```sql
-- PostgreSQL:
SELECT
    m.source_name,
    m.record_key,
    m.person_name,
    m.amount
FROM (
    SELECT
        'ONLINE'::text AS source_name,
        CAST(online_id AS text) AS record_key,
        customer_name AS person_name,
        gross_amount AS amount
    FROM sql208_online_orders

    UNION ALL

    SELECT
        'STORE'::text,
        store_code,
        buyer_name,
        CAST(total_text AS numeric(12,2))
    FROM sql208_store_orders
) AS m
WHERE m.amount >= 100
ORDER BY m.person_name, m.source_name, m.record_key;
```

Ở đây `m` công bố **bốn cột từ SELECT đầu tiên**. `WHERE m.amount >= 100` lọc kết quả đã hợp nhất; `ORDER BY` ngoài cùng điều khiển thứ tự hiển thị.

Nếu JOIN thêm một bảng khách hàng:

```sql
-- Minh họa khung JOIN, chỉ chạy khi có bảng customers phù hợp:
SELECT
    m.source_name,
    m.record_key,
    c.customer_id,
    m.amount
FROM (
    SELECT customer_id, CAST(online_id AS text) AS record_key,
           'ONLINE'::text AS source_name, gross_amount AS amount
    FROM online_orders_with_customer_id

    UNION ALL

    SELECT customer_id, store_code, 'STORE'::text,
           CAST(total_text AS numeric(12,2))
    FROM store_orders_with_customer_id
) AS m
JOIN customers AS c
  ON c.customer_id = m.customer_id
ORDER BY c.customer_id, m.source_name, m.record_key;
```

Đây là **mẫu cấu trúc**, vì các bảng `online_orders_with_customer_id`, `store_orders_with_customer_id` và `customers` không được tạo ở phần thực hành. Nó nhấn mạnh rằng sau khi `UNION` công bố `customer_id`, truy vấn ngoài JOIN bằng **tên và kiểu thống nhất**, không quan tâm từng nguồn gọi cột gốc là gì.

Nếu hai nguồn có mã khách hàng thuộc **hai miền định danh khác nhau**, việc CAST về cùng kiểu không đủ để bảo đảm `JOIN` đúng thực thể. Cần bảng ánh xạ ID hoặc quy tắc định danh chung.

## 22. UNION ALL trước hay sau GROUP BY?

Một câu hỏi quan trọng khi tổng hợp dữ liệu từ nhiều nguồn: nên tổng hợp từng nguồn rồi ghép, hay ghép trước rồi tổng hợp?

### Ghép dữ liệu rồi tổng hợp toàn hệ

```sql
-- PostgreSQL:
SELECT
    u.person_name,
    SUM(u.amount) AS total_amount
FROM (
    SELECT
        customer_name AS person_name,
        gross_amount AS amount
    FROM sql208_online_orders

    UNION ALL

    SELECT
        buyer_name,
        CAST(total_text AS numeric(12,2))
    FROM sql208_store_orders
) AS u
GROUP BY u.person_name
ORDER BY total_amount DESC, u.person_name;
```

Với dữ liệu mẫu:

| person_name | total_amount |
| --- | ---: |
| An | 241.00 |
| Chi | 241.00 |
| Dũng | 90.00 |
| Bình | 80.00 |

`UNION ALL` giữ **mọi giao dịch**. Sau đó `SUM` cộng các số tiền theo tên khách.

**Cảnh báo nghiệp vụ:** vì nhóm bằng `person_name`, hai người khác nhau trùng tên sẽ bị gộp thành một. Ví dụ chỉ minh họa kỹ thuật; với dữ liệu thật cần dùng **khóa khách hàng** phù hợp.

### Vì sao UNION thay UNION ALL có thể làm sai tổng?

Nếu dùng `UNION` trước khi `SUM`:

```sql
-- Sai nếu mỗi dòng nguồn là một giao dịch độc lập cần cộng:
SELECT u.person_name, SUM(u.amount)
FROM (
    SELECT customer_name AS person_name, gross_amount AS amount
    FROM sql208_online_orders

    UNION

    SELECT buyer_name, CAST(total_text AS numeric(12,2))
    FROM sql208_store_orders
) AS u
GROUP BY u.person_name;
```

thì các dòng `('An',120.50)` ở hai nguồn bị gộp thành một, khiến tổng tiền của An chỉ còn **120.50** thay vì **241.00**. Tương tự với Chi.

**UNION DISTINCT không phải phép loại đơn hàng trùng ID** nếu chỉ chọn tên và số tiền. Hai giao dịch thật có cùng số tiền không được tự coi là một giao dịch. Nếu cần deduplicate sự kiện từ nhiều nguồn, phải có khóa hoặc quy tắc nhận diện bản ghi trùng **đúng nghiệp vụ**.

### Tổng hợp từng nguồn rồi UNION ALL

Có thể tổng hợp theo kênh trước:

```sql
SELECT 'ONLINE'::text AS source_name,
       SUM(gross_amount) AS channel_total
FROM sql208_online_orders

UNION ALL

SELECT 'STORE'::text,
       SUM(CAST(total_text AS numeric(12,2)))
FROM sql208_store_orders

ORDER BY source_name;
```

Kết quả:

| source_name | channel_total |
| --- | ---: |
| ONLINE | 321.00 |
| STORE | 330.50 |

Truy vấn này trả **một dòng trên một nguồn**, khác với truy vấn tổng hợp theo khách ở trên. Chúng đều dùng `UNION ALL`, nhưng **đơn vị nhóm và mục tiêu báo cáo khác nhau**.

## 23. Khi muốn giữ đúng kiểu và tên: hợp đồng đầu ra của UNION

Trong thực tế, một API có thể gom log hoặc giao dịch từ nhiều bảng qua một câu UNION. Nên xem các cột kết quả như một **hợp đồng dữ liệu**:

| Cột chuẩn | Kiểu dự kiến | Có thể NULL? | Quy tắc |
| --- | --- | --- | --- |
| `source_name` | `text` | Không | Nhãn nguồn được xác định trước |
| `record_key` | `text` | Không | Khóa bản ghi trong nguồn, đi kèm `source_name` |
| `person_name` | `text` | Theo nghiệp vụ | Tên hiển thị, không mặc nhiên là ID |
| `amount` | `numeric(12,2)` | Theo nghiệp vụ | Số tiền đã chuyển kiểu rõ ràng |
| `occurred_on` | `date` | Theo nghiệp vụ | Ngày theo quy ước lưu trữ đã xác định |

Nếu một nguồn mới được thêm vào, trước khi viết `UNION ALL` hãy kiểm tra:

1. Có đúng **năm cột** theo thứ tự trên không?
2. Cột `record_key` đã được đổi về kiểu text hợp lệ chưa?
3. Cột số tiền đã được chuẩn hóa và kiểm tra chuyển kiểu chưa?
4. Cột ngày là `DATE` hay `TIMESTAMP`, cần bảo toàn giờ hay không?
5. Có tên cột đầu ra duy nhất và rõ nghĩa ở nhánh đầu không?
6. Có cần `UNION ALL` giữ mọi dòng hay `UNION` loại trùng theo *toàn bộ năm cột*?
7. `ORDER BY` cuối có đủ tie-breaker nếu ứng dụng phân trang không?

### Kỹ thuật NULL cho cột chỉ có ở một nguồn

Giả sử bảng cửa hàng không có `person_name` nhưng API vẫn yêu cầu cột này:

```sql
SELECT
    CAST(online_id AS text) AS record_key,
    CAST(customer_name AS text) AS person_name
FROM sql208_online_orders

UNION ALL

SELECT
    store_code,
    CAST(NULL AS text)
FROM sql208_store_orders;
```

Đặt `NULL` ở đúng **vị trí** và **đúng kiểu** giúp giữ hợp đồng hai cột. `NULL` không phải chuỗi `'NULL'`; ép `NULL` thành `text` vẫn là giá trị thiếu, không phải một chữ được hiển thị nguyên văn.

Nếu nguồn có người mua nhưng ở tên cột khác, phải dùng cột dữ liệu đó thay vì điền `NULL` chỉ để câu SQL chạy. Mục tiêu là bảo toàn **ý nghĩa**, không chỉ số cột và kiểu.

## 24. Khác biệt theo DBMS cần biết

| DBMS | UNION/UNION ALL | INTERSECT/EXCEPT hoặc tương đương | Lưu ý tên, kiểu và ORDER BY |
| --- | --- | --- | --- |
| **PostgreSQL** | Có | Có `INTERSECT`, `EXCEPT`; có dạng `ALL` cho các phép này | Tên cột từ nhánh đầu; kiểu phải hòa giải được; `ORDER BY` trực tiếp sau set operation chỉ dùng tên/vị trí cột kết quả |
| **MySQL** | Có | `INTERSECT` và `EXCEPT` từ MySQL 8.0.31; phiên bản cũ cần cách khác | Derived table cần alias; quy tắc chuyển kiểu và collation riêng; `ORDER BY` cuối |
| **MariaDB** | Có | Hỗ trợ `INTERSECT`/`EXCEPT` trên các phiên bản có tính năng này | Kiểm tra engine/phiên bản, cú pháp đặt ngoặc và ép kiểu |
| **SQL Server** | Có | Có `INTERSECT` và `EXCEPT`; không dùng `INTERSECT ALL`/`EXCEPT ALL` như PostgreSQL | Kiểu dữ liệu theo precedence/conversion; `ORDER BY` cuối, phân trang dùng `OFFSET ... FETCH` |
| **SQLite** | Có | Có `INTERSECT`/`EXCEPT` theo ngữ nghĩa distinct; không có dạng `ALL` tương ứng | Type affinity và collation có đặc thù; `ORDER BY` trên compound SELECT bị giới hạn theo biểu thức/cột đầu ra |
| **Oracle Database** | Có | `MINUS` phổ biến cho phép hiệu; `EXCEPT` có trên những phiên bản hiện đại hỗ trợ | Quy tắc nhóm kiểu số/chuỗi, alias và cú pháp hạn chế theo phiên bản; dùng `ORDER BY` cuối |

Những dòng trong bảng là **định hướng**, không thay thế việc xem tài liệu đúng DBMS và phiên bản. Đặc biệt, **MySQL** và **MariaDB** là hai sản phẩm với lịch sử hỗ trợ các toán tử khác nhau; không suy ra tính năng MariaDB chỉ từ phiên bản MySQL hoặc ngược lại.

### SQL Server: không dùng LIMIT

Ví dụ ghép rồi lấy 5 dòng trên SQL Server:

```sql
-- SQL Server:
SELECT customer_name AS person_name, gross_amount AS amount
FROM dbo.online_orders

UNION ALL

SELECT buyer_name, CAST(total_text AS decimal(12,2))
FROM dbo.store_orders

ORDER BY amount DESC, person_name ASC
OFFSET 0 ROWS FETCH NEXT 5 ROWS ONLY;
```

SQL Server còn có `TOP` nhưng với set operation nhiều nhánh phải chú ý `TOP` áp dụng ở cấp nào. Đoạn trên dùng `OFFSET ... FETCH` ở cuối để giới hạn **kết quả sau hợp nhất**, không phải tự chọn 5 dòng riêng từ mỗi nhánh.

### SQLite: kiểu dữ liệu và phép so sánh

SQLite linh hoạt về kiểu lưu trữ (type affinity). Việc ghép một cột nhìn như số với một cột chứa văn bản số không đồng nghĩa phép toán tập hợp sẽ luôn coi chúng như cùng kiểu/giá trị theo mong muốn. Nếu yêu cầu là tiền, hãy dùng `CAST`/chuẩn hóa theo cấu trúc dữ liệu của ứng dụng và kiểm tra kết quả bằng dữ liệu thử có đủ trường hợp đặc biệt.

### Oracle: MINUS và kiểu dữ liệu

Với nhiều phiên bản Oracle, phép hiệu thường viết:

```sql
-- Oracle Database:
SELECT customer_id
FROM source_a

MINUS

SELECT customer_id
FROM source_b;
```

`MINUS` ở đây có ý nghĩa “có ở A nhưng không có ở B” theo ngữ nghĩa distinct. Một số phiên bản Oracle mới hỗ trợ tên `EXCEPT` và các biến thể khác, nhưng không tự mang mọi cú pháp `EXCEPT ALL` của PostgreSQL vào Oracle. Tương tự, Oracle có quy tắc chặt về nhóm kiểu dữ liệu trong phép toán tập hợp; dùng `CAST` tường minh khi có sự khác biệt.

### Khi cần bảo toàn alias đầu ra trên mọi hệ

Một cách viết rõ ràng là:

```sql
SELECT
    'ONLINE' AS source_name,
    CAST(101 AS VARCHAR(20)) AS record_key

UNION ALL

SELECT
    'STORE',
    CAST('S01' AS VARCHAR(20));
```

Cú pháp `CAST(... AS VARCHAR(20))` và cách diễn giải literal có thể được điều chỉnh theo DBMS; **nguyên tắc** là công bố kiểu/alias ổn định từ nhánh đầu và giữ **cùng vị trí ý nghĩa** ở các nhánh tiếp theo.

## 25. Hiệu năng của phép hợp nhất và sắp xếp

Không phải phép toán tập hợp nào cũng có cùng chi phí.

### UNION ALL thường tránh bước loại trùng

`UNION ALL` giữ mọi dòng, nên về mặt mục tiêu không cần xác định dòng nào trùng để loại. `UNION`/`INTERSECT`/`EXCEPT` dạng distinct có thể cần so sánh/hashing/sorting để xác định các dòng giống nhau.

Tuy nhiên, không có quy tắc tuyệt đối rằng `UNION ALL` luôn nhanh hơn mọi câu `UNION` trong mọi trường hợp. Bộ lọc, số dòng, chỉ mục, kế hoạch song song và thứ tự dữ liệu đều ảnh hưởng. Điểm đáng nhớ là **chọn ALL hay DISTINCT theo đúng dữ liệu nghiệp vụ trước khi tối ưu**.

### ORDER BY cuối có thể phải sắp nhiều dòng

```sql
SELECT ...
FROM source_a
UNION ALL
SELECT ...
FROM source_b
ORDER BY some_column;
```

Khi dữ liệu hai nguồn rất lớn, bước sort toàn bộ kết quả có thể cần nhiều bộ nhớ hoặc ghi tạm ra đĩa. Index ở mỗi bảng nguồn **không tự bảo đảm** kết quả UNION đã được sắp toàn cục theo thứ tự mong muốn.

Các chiến lược thường cân nhắc:

- Chỉ chọn những cột thực sự cần; tránh `SELECT *` từ các bảng có schema khác nhau.
- Dùng `WHERE` để giảm số dòng nguồn khi điều kiện lọc cho phép.
- Không dùng `UNION` để loại trùng nếu nghiệp vụ cần giữ mọi dòng; chọn `UNION ALL`.
- Với báo cáo lớn, cân nhắc tổng hợp theo nhóm phù hợp trước hoặc sau hợp nhất theo đúng ý nghĩa.
- Với trang sâu, xem chi phí `OFFSET` và cân nhắc phương án seek trên khóa sắp xếp chung.
- Sử dụng `EXPLAIN` hoặc công cụ execution plan tương ứng để xem thực tế.

### PostgreSQL: quan sát kế hoạch

```sql
EXPLAIN
SELECT customer_name AS person_name, gross_amount AS amount
FROM sql208_online_orders
UNION ALL
SELECT buyer_name, CAST(total_text AS numeric(12,2))
FROM sql208_store_orders
ORDER BY amount DESC, person_name;
```

Với bảng học tập chỉ ba dòng mỗi nguồn, planner có thể chọn kế hoạch rất khác bảng thật. `EXPLAIN` hiển thị **kế hoạch dự kiến**, không thực thi dữ liệu như `EXPLAIN ANALYZE`.

**Không nên cố thay đổi SQL chỉ để thấy một tên operator cụ thể** như `Append` hoặc `Sort` trên bảng nhỏ; mục tiêu là hiểu có cần hợp nhất, loại trùng và sắp xếp đến cấp nào.

## 26. Lỗi thường gặp và cách sửa

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Lỗi “different number of columns” | Hai nhánh SELECT không cùng số cột | Lập danh sách cột chuẩn, thêm cột/`CAST(NULL AS type)` đúng vị trí |
| SQL chạy nhưng tên khách xuất hiện ở cột mã | Đảo vị trí hai cột cùng kiểu giữa các nhánh | Đối chiếu vị trí cột theo ý nghĩa, không theo alias |
| Truy vấn ngoài báo không tìm thấy alias của nhánh thứ hai | Tên kết quả dùng alias từ nhánh đầu | Dùng alias cột đầu ra của nhánh đầu hoặc đặt tên ở lớp ngoài |
| UNION không hợp nhất được kiểu | Cùng vị trí có `numeric` và `text`/`date` không tương thích | Chọn kiểu chung đúng nghiệp vụ, `CAST` rõ ràng |
| CAST chuỗi tiền báo lỗi | Có ký tự không phải số hoặc định dạng nguồn sai | Chuẩn hóa/kiểm tra dữ liệu trước CAST |
| Giá trị tiền bị làm tròn hoặc tràn | Kiểu `DECIMAL` đích có precision/scale không phù hợp | Thiết kế kiểu đủ rộng, kiểm tra metadata |
| Cột ngày mất phần giờ | Ép `TIMESTAMP` về `DATE` | Chỉ CAST khi mục tiêu đúng là ngày lịch |
| `UNION` trả ít dòng hơn tổng nguồn | Các dòng trùng toàn bộ cột bị loại | Dùng `UNION ALL` nếu cần giữ mọi giao dịch |
| `UNION` vẫn giữ hai dòng cùng khách | Có cột khác nhau, chẳng hạn `source_name` hoặc `amount` | Xác định đúng bộ cột đại diện cho việc trùng |
| Kết quả `UNION ALL` “đổi thứ tự” | Không có ORDER BY cuối | Đặt ORDER BY rõ ràng ở cấp kết quả cần hiển thị |
| ORDER BY tên alias nhánh sau bị lỗi | Alias đó không phải tên cột đầu ra chung | Sắp theo alias nhánh đầu hoặc dùng derived table |
| ORDER BY `LOWER(name)` sau UNION lỗi ở PostgreSQL | Compound query giới hạn biểu thức sắp xếp trực tiếp | Bọc UNION trong derived table rồi ORDER BY biểu thức ở ngoài |
| ORDER BY 2 đột nhiên sắp sai | Danh sách SELECT đổi vị trí | Ưu tiên sắp theo tên cột |
| Phân trang có dòng trùng dù đã ORDER BY | Sort chưa toàn phần hoặc dữ liệu đổi giữa request | Thêm tie-breaker, xem snapshot/keyset |
| LIMIT chọn sai số dòng trên từng nguồn | LIMIT đang áp dụng sau UNION, không phải cho từng nhánh | Dùng subquery với LIMIT cho mỗi nguồn rồi UNION |
| Tháng/ngày bị trùng sai khi dùng DISTINCT | Chỉ chọn thành phần tháng hoặc ngày, bỏ năm | Dùng khóa thời gian đầy đủ |
| Kết quả thay đổi theo DBMS | Collation, implicit cast, cú pháp EXCEPT, ORDER BY khác | Xác minh dialect/phiên bản, thử trên dữ liệu đại diện |
| NULL bị coi là trùng trong UNION | Distinct set operation dùng quy tắc loại trùng khác `=` thông thường | Xem ngữ nghĩa distinct và chọn ALL khi muốn giữ từng dòng |

## 27. Bài tập thực hành

### Bài 1 — Tên cột sau UNION

Cho truy vấn PostgreSQL:

```sql
SELECT
    10 AS customer_id,
    'An' AS customer_name

UNION ALL

SELECT
    20 AS user_code,
    'Bình' AS full_name;
```

Tên **hai cột kết quả** là gì? Có thể viết `ORDER BY full_name` ở cuối thay cho `ORDER BY customer_name` không? Vì sao?

### Bài 2 — Phát hiện ghép sai vị trí

Hai nguồn:

```sql
SELECT 'C01'::text AS code, 'An'::text AS name
UNION ALL
SELECT 'Bình'::text AS name, 'C02'::text AS code;
```

Truy vấn có thể chạy được không? Dòng thứ hai nằm ở cột nào? Sửa lại thứ tự nhánh thứ hai.

### Bài 3 — Chuẩn hóa kiểu dữ liệu

Bảng online có `online_id INTEGER` và `amount NUMERIC(12,2)`; bảng store có `store_code VARCHAR(20)` và `amount_text VARCHAR(30)`. Viết câu `UNION ALL` trả `record_key TEXT` và `amount NUMERIC(12,2)` trên PostgreSQL.

### Bài 4 — Đếm kết quả UNION và UNION ALL

Từ dữ liệu ở mục 6, chỉ chọn **tên khách và số tiền**.

1. `UNION ALL` trả bao nhiêu dòng?
2. `UNION` trả bao nhiêu dòng?
3. Những cặp nào bị hợp nhất?
4. Điều gì xảy ra nếu thêm cột `source_name` vào cả hai nhánh và dùng `UNION`?

### Bài 5 — INTERSECT và EXCEPT

Trên bảng mẫu, dùng cặp `(person_name, amount)`:

1. Kết quả `online INTERSECT store` là gì?
2. Kết quả `online EXCEPT store` là gì?
3. Kết quả `store EXCEPT online` là gì?
4. Vì sao `EXCEPT` không thể đổi nhánh tùy tiện?

### Bài 6 — NULL và loại trùng

Dự đoán số dòng từ từng truy vấn PostgreSQL:

```sql
-- A
SELECT CAST(NULL AS integer) AS x
UNION
SELECT CAST(NULL AS integer) AS x;

-- B
SELECT CAST(NULL AS integer) AS x
UNION ALL
SELECT CAST(NULL AS integer) AS x;

-- C
SELECT CAST(NULL AS integer) AS x
INTERSECT
SELECT CAST(NULL AS integer) AS x;

-- D
SELECT CAST(NULL AS integer) AS x
EXCEPT
SELECT CAST(NULL AS integer) AS x;
```

Giải thích vì sao không thể suy luận kết quả chỉ từ biểu thức `NULL = NULL` trong `WHERE`.

### Bài 7 — Sắp theo alias sau hợp nhất

Cho:

```sql
SELECT customer_name AS person_name, gross_amount AS amount
FROM sql208_online_orders
UNION ALL
SELECT buyer_name AS buyer, CAST(total_text AS numeric(12,2)) AS value
FROM sql208_store_orders;
```

Hãy thêm `ORDER BY` để sắp tiền giảm dần, tên tăng dần. Vì sao không dùng `ORDER BY value` trên PostgreSQL?

### Bài 8 — ORDER BY biểu thức

Viết truy vấn PostgreSQL hợp nhất tên khách từ online và store, rồi sắp theo `LOWER(person_name)`. Không dùng biểu thức `LOWER(...)` trực tiếp trong `ORDER BY` của compound SELECT; hãy dùng derived table.

### Bài 9 — Ẩn khóa sắp xếp

Cần hiển thị chỉ `person_name` và `amount` nhưng sắp theo ngày mới nhất, nguồn và khóa dòng. Hãy viết derived table có đủ `sort_day`, `source_name`, `record_key`, rồi chọn hai cột ở bên ngoài.

### Bài 10 — Top N trước hay sau UNION?

Hai nguồn có nhiều đơn. Yêu cầu A: **hai đơn lớn nhất của mỗi nguồn**. Yêu cầu B: **hai đơn lớn nhất của toàn bộ hai nguồn**. Hai truy vấn phải đặt `ORDER BY` và `LIMIT` ở vị trí nào để cho kết quả khác nhau đúng mục tiêu?

### Bài 11 — Tổng tiền và loại trùng

Dùng dữ liệu mẫu, `UNION ALL` các cặp `(person_name, amount)` rồi `SUM(amount) GROUP BY person_name`. Tổng của An và Chi là bao nhiêu? Điều gì sẽ sai nếu đổi thành `UNION` trước khi tính tổng?

### Bài 12 — Thiết kế hợp đồng dữ liệu

Một nguồn mới có các cột `order_uuid UUID`, `client_label TEXT`, `value_cents BIGINT` và `created_at TIMESTAMPTZ`. Kết quả chung yêu cầu `record_key TEXT`, `person_name TEXT`, `amount NUMERIC(12,2)` và `occurred_on DATE`. Hãy nêu các chuyển đổi và rủi ro cần xét **trước** khi viết `UNION ALL`.

### Bài 13 — Truy vấn đa hệ

Phân biệt hỗ trợ của PostgreSQL, MySQL phiên bản cũ, MySQL 8.0.31+, SQL Server, SQLite và Oracle với `INTERSECT`/`EXCEPT`. Tại sao không nên giả định `EXCEPT ALL` chạy được trên mọi DBMS? Với Oracle dùng phiên bản chưa hỗ trợ `EXCEPT`, phép hiệu thường được gọi là gì?

## 28. Gợi ý lời giải

**Bài 1:** Hai tên cột đầu ra là `customer_id` và `customer_name`. Alias `user_code`, `full_name` ở nhánh hai không quyết định tên cột chung. Vì vậy sắp bằng `ORDER BY customer_name`, không dùng `full_name` như tên kết quả.

**Bài 2:** Trên PostgreSQL, hai vị trí đều là `text` nên câu SQL có thể chạy nhưng dữ liệu dòng hai bị đảo: `code='Bình'`, `name='C02'`. Sửa thành:

```sql
SELECT 'C01'::text AS code, 'An'::text AS name
UNION ALL
SELECT 'C02'::text AS code, 'Bình'::text AS name;
```

**Bài 3:**

```sql
-- Giả sử tên bảng/cột như bài tập và các chuỗi tiền đều hợp lệ.
SELECT
    CAST(online_id AS text) AS record_key,
    CAST(amount AS numeric(12,2)) AS amount
FROM online

UNION ALL

SELECT
    CAST(store_code AS text),
    CAST(amount_text AS numeric(12,2))
FROM store;
```

`online`, `store` là tên bảng minh họa. Nếu muốn chạy với bảng học tập, thay bằng `sql208_online_orders`/`sql208_store_orders` và tên cột `gross_amount`/`total_text` tương ứng.

**Bài 4:** `UNION ALL` có **6 dòng**. `UNION` có **4 dòng** vì hai cặp `('An',120.50)` và `('Chi',120.50)` xuất hiện ở cả hai nguồn. Khi thêm `source_name` với giá trị khác nhau, các dòng từ hai nguồn không còn trùng **toàn bộ cột**, nên `UNION` có thể giữ đủ 6 dòng của dữ liệu mẫu.

**Bài 5:** `INTERSECT` trả `('An',120.50)`, `('Chi',120.50)`. `online EXCEPT store` trả `('Bình',80.00)`. `store EXCEPT online` trả `('Dũng',90.00)`. `EXCEPT` có hướng trái–phải rõ ràng.

**Bài 6:** A có **1 dòng NULL**; B có **2 dòng NULL**; C có **1 dòng NULL**; D có **0 dòng**. Phép loại trùng/so dòng của set operation xử lý `NULL` theo quy tắc riêng, khác phép so sánh `=` trong `WHERE`.

**Bài 7:**

```sql
SELECT customer_name AS person_name, gross_amount AS amount
FROM sql208_online_orders
UNION ALL
SELECT buyer_name, CAST(total_text AS numeric(12,2))
FROM sql208_store_orders
ORDER BY amount DESC, person_name ASC;
```

`value` chỉ là alias của nhánh sau. Trên PostgreSQL, `ORDER BY` trực tiếp cho compound SELECT dựa vào tên/vị trí cột kết quả chung.

**Bài 8:**

```sql
SELECT u.person_name
FROM (
    SELECT customer_name AS person_name
    FROM sql208_online_orders
    UNION ALL
    SELECT buyer_name
    FROM sql208_store_orders
) AS u
ORDER BY LOWER(u.person_name), u.person_name;
```

**Bài 9:**

```sql
SELECT u.person_name, u.amount
FROM (
    SELECT customer_name AS person_name,
           gross_amount AS amount,
           created_on AS sort_day,
           'ONLINE'::text AS source_name,
           CAST(online_id AS text) AS record_key
    FROM sql208_online_orders
    UNION ALL
    SELECT buyer_name,
           CAST(total_text AS numeric(12,2)),
           sold_on,
           'STORE'::text,
           store_code
    FROM sql208_store_orders
) AS u
ORDER BY u.sort_day DESC, u.source_name, u.record_key;
```

**Bài 10:** Yêu cầu A cần `ORDER BY amount DESC ... LIMIT 2` ở **từng nhánh trong subquery** rồi `UNION ALL`. Yêu cầu B cần `UNION ALL` **toàn bộ dòng trước**, sau đó `ORDER BY amount DESC, ... LIMIT 2` **ở cuối**.

**Bài 11:** An = **241.00**, Chi = **241.00**. Nếu dùng `UNION`, các cặp trùng bị loại trước khi `SUM`; mỗi người có thể chỉ còn **120.50**, làm thiếu tiền của những giao dịch thật ở hai nguồn.

**Bài 12:** Chuyển UUID sang text theo cú pháp DBMS; giữ `client_label` là text; đổi `value_cents` sang tiền đơn vị bằng `CAST(value_cents AS numeric)/100` với precision/scale phù hợp; xác định **múi giờ nghiệp vụ** trước khi chuyển `TIMESTAMPTZ` sang `DATE`, vì cùng instant có thể thuộc ngày khác ở UTC và địa phương. Cần kiểm tra overflow, phần lẻ, số âm, currency, NULL, độ dài khóa và chuẩn định dạng.

**Bài 13:** PostgreSQL có `INTERSECT`/`EXCEPT` cùng một số dạng `ALL`; MySQL trước 8.0.31 không có hỗ trợ trực tiếp hai toán tử này, còn từ MySQL 8.0.31 có; SQL Server và SQLite hỗ trợ dạng distinct phổ biến nhưng không hỗ trợ mọi dạng `ALL` của PostgreSQL; Oracle truyền thống dùng `MINUS` cho hiệu tập, với tính năng mới tùy phiên bản. Không chuyển nguyên cú pháp khi chưa xác minh engine/phiên bản.

## 29. Dọn dữ liệu thực hành

Khi kết thúc, chỉ chạy nếu hai bảng đã được **chính bạn tạo** cho bài học và không còn cần dữ liệu:

```sql
DROP TABLE sql208_store_orders;
DROP TABLE sql208_online_orders;
```

Không dùng `DROP TABLE` trên bảng nghiệp vụ thật hoặc database dùng chung. Các lệnh SELECT trong bài không tự tạo bảng kết quả lâu dài; chỉ các câu `CREATE TABLE` và `INSERT` ở phần thực hành đã tạo và ghi dữ liệu.

## 30. Kết luận

Trong phép toán tập hợp SQL, hãy tư duy bằng **giao diện cột chung** thay vì các tên cột của từng bảng nguồn:

- **Vị trí** quyết định cột nào được ghép với cột nào.
- **Tên đầu ra** thường được xác định từ nhánh đầu, nên phải đặt alias rõ nghĩa và ổn định.
- **Kiểu đầu ra** phải được hòa giải theo từng vị trí; `CAST` tường minh giúp giảm nhập nhằng khi nguồn khác schema.
- **UNION ALL** giữ toàn bộ dòng; **UNION/INTERSECT/EXCEPT** kiểu distinct so sánh toàn bộ dòng kết quả và có quy tắc cho `NULL`, collation, bội số.
- **ORDER BY cuối cùng** mới xác định trình tự trình bày của kết quả hợp nhất. Muốn sắp theo biểu thức hoặc khóa không hiển thị, có thể bọc phép toán trong derived table.
- **LIMIT/OFFSET** ở cuối phân trang **tập hợp nhất**; LIMIT trong từng nhánh chọn **tập con của từng nguồn** trước khi hợp nhất.

Một truy vấn `UNION` đúng cú pháp vẫn có thể sai nghiệp vụ nếu các nhánh đảo vị trí cột, ép kiểu làm mất thông tin, loại nhầm giao dịch trùng giá trị hoặc dựa vào thứ tự kết quả không được bảo đảm. Trước khi triển khai, hãy kiểm tra **số cột, thứ tự, tên, kiểu, quy tắc loại trùng và ORDER BY ở đúng cấp truy vấn**.
