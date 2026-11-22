# MERGE và các nhánh xử lý theo phương ngữ

Khi đồng bộ dữ liệu từ một hệ thống sang hệ thống khác, ta thường cần quyết định **mỗi hàng nguồn phải làm gì với bảng đích**:

- Nếu khóa đã tồn tại trong bảng đích, **cập nhật** những cột thay đổi.
- Nếu khóa chưa tồn tại, **chèn** một hàng mới.
- Nếu nguồn báo đối tượng đã ngừng sử dụng, có thể **xóa** hoặc **đánh dấu ngừng hoạt động**.
- Nếu dữ liệu không thay đổi hoặc không thuộc phạm vi xử lý, **bỏ qua**.

Trong SQL, lệnh **`MERGE`** diễn đạt nhiều quyết định như vậy trong một câu lệnh, bằng cách so khớp dữ liệu nguồn với bảng đích rồi chọn các **nhánh `WHEN`** thích hợp. Tuy nhiên, `MERGE` **không có cùng cú pháp và cùng tập tính năng ở mọi hệ quản trị**. PostgreSQL từ phiên bản 15 có `MERGE`; SQL Server và Oracle cũng có `MERGE` nhưng cách viết nhánh xóa, cách báo kết quả và giới hạn khác nhau. MySQL và SQLite thường thực hiện nhu cầu *upsert* bằng `INSERT ... ON DUPLICATE KEY UPDATE` hoặc `INSERT ... ON CONFLICT`, **không phải cùng một lệnh `MERGE` tiêu chuẩn**.

Bài học này tập trung vào **các nhánh của MERGE và sự khác nhau giữa các phương ngữ**, từ những tình huống đơn giản đến các lỗi quan trọng như nhiều hàng nguồn cùng khớp một hàng đích, khóa `NULL`, thiếu hàng trong nguồn và xóa dây chuyền. Ví dụ thực hành chính dùng **PostgreSQL**, đi kèm mẫu tương ứng cho **SQL Server, Oracle, MySQL và SQLite**.

> **Phạm vi:** Các đoạn SQL thay đổi dữ liệu chỉ nên chạy trên database thực hành hoặc môi trường đã được phép. Mỗi ví dụ thao tác có thể làm thay đổi hoặc xóa hàng; hãy xem trước dữ liệu và dùng transaction phù hợp trước khi thực thi.

## 1. MERGE giải quyết bài toán gì?

Hãy hình dung bảng tồn kho hiện tại có sản phẩm `A` với số lượng 5. Một tệp mới gửi số lượng 8 của sản phẩm `A`, đồng thời gửi sản phẩm `F` chưa tồn tại. Ứng dụng cần:

```text
Nguồn mới                     Bảng tồn kho hiện tại
---------                     ---------------------
A: 8                          A: 5
F: 6                          B: 12
                              C: 4

So khớp theo SKU:
A đã tồn tại  -> UPDATE A thành 8
F chưa tồn tại -> INSERT F với số lượng 6
```

Nếu còn một sự kiện `REMOVE` cho sản phẩm `C`, quy trình có thể cần xóa `C` hoặc đánh dấu sản phẩm ngừng hoạt động. Khi những quy tắc đó nằm trong một lệnh `MERGE`, người đọc có thể nhìn rõ **điều kiện so khớp** và **hành động trên từng loại hàng**.

### 1.1. Ba tình huống so khớp cần phân biệt

Về mặt khái niệm, các hệ quản trị có thể phân loại hàng như sau:

| Tình huống | Cách hiểu | Hành động thường gặp |
|---|---|---|
| `MATCHED` | Một hàng nguồn đã tìm thấy hàng đích theo điều kiện `ON` | `UPDATE`, `DELETE`, bỏ qua |
| `NOT MATCHED` hoặc `NOT MATCHED BY TARGET` | Hàng **nguồn** không tìm thấy hàng đích | `INSERT`, bỏ qua |
| `NOT MATCHED BY SOURCE` | Hàng **đích** không xuất hiện ở tập nguồn | `UPDATE` thành inactive hoặc `DELETE`, khi DBMS/phiên bản hỗ trợ |

Hai tình huống “không khớp” **khác hướng**:

```text
Nguồn có, đích không có   -> NOT MATCHED BY TARGET -> có thể INSERT
Đích có, nguồn không có   -> NOT MATCHED BY SOURCE -> có thể deactive/DELETE
```

Đặc biệt, **không xuất hiện ở nguồn** không tự nhiên có nghĩa “đã bị xóa”. Nếu dữ liệu nguồn chỉ là **các thay đổi phát sinh trong ngày**, sản phẩm không xuất hiện có thể đơn giản là **không thay đổi**. Chỉ nên dùng nhánh `NOT MATCHED BY SOURCE` để xóa/đánh dấu ngừng hoạt động khi nguồn thực sự là **ảnh chụp đầy đủ của phạm vi được đồng bộ**.

### 1.2. Cấu trúc ý tưởng của MERGE

Ở mức tổng quát:

```sql
MERGE INTO target_table AS t
USING source_data AS s
ON (t.business_key = s.business_key)

WHEN MATCHED AND some_condition THEN
    UPDATE SET ...

WHEN NOT MATCHED AND another_condition THEN
    INSERT (...) VALUES (...);
```

Trong đó:

- `MERGE INTO` chỉ định **bảng đích** được phép thay đổi.
- `USING` cung cấp **nguồn dữ liệu**: một bảng, một truy vấn, bảng tạm hoặc tập bản ghi thích hợp.
- `ON` quyết định **nguồn và đích khớp theo tiêu chí nào**, thường là khóa nghiệp vụ.
- Các mệnh đề `WHEN` phân nhánh theo tình trạng khớp và điều kiện bổ sung.
- `UPDATE`, `INSERT`, `DELETE`, `DO NOTHING` hoặc các dạng bỏ qua tùy thuộc **phương ngữ và phiên bản**.

Không nên xem mẫu trên như một câu SQL chạy nguyên văn trên mọi DBMS. Ví dụ SQL Server thường viết rõ `WHEN NOT MATCHED BY TARGET`, Oracle có `DELETE WHERE` gắn với nhánh `UPDATE`, còn PostgreSQL có `DO NOTHING` trong những nhánh được hỗ trợ.

## 2. Dữ liệu mẫu: bảng tồn kho và luồng cập nhật

Để có thể dự đoán kết quả từng nhánh, ta tạo một bộ dữ liệu nhỏ, cố ý có sản phẩm cần cập nhật, cần chèn, cần xóa, cần bỏ qua và sản phẩm **vắng mặt ở nguồn**.

### 2.1. Tạo bảng PostgreSQL

```sql
CREATE TABLE inventory_demo (
    sku TEXT PRIMARY KEY,
    quantity INTEGER NOT NULL CHECK (quantity >= 0),
    status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'INACTIVE'))
);

CREATE TABLE stock_feed_demo (
    feed_id INTEGER PRIMARY KEY,
    sku TEXT NOT NULL,
    operation TEXT NOT NULL
        CHECK (operation IN ('UPSERT', 'REMOVE', 'SKIP')),
    quantity INTEGER NOT NULL CHECK (quantity >= 0),
    received_at TIMESTAMP NOT NULL
);
```

**Hai khóa cần hiểu rõ:**

- `inventory_demo.sku` là **khóa chính** của bảng đích. Không thể có hai hàng đích cùng `sku`.
- `stock_feed_demo.feed_id` chỉ xác định **dòng dữ liệu nhập**. `sku` của bảng feed **chưa được ràng buộc duy nhất**, để ta có thể thảo luận về trường hợp nguồn có nhiều sự kiện cho cùng sản phẩm. Bộ dữ liệu khởi tạo dưới đây mỗi `sku` chỉ xuất hiện một lần.

### 2.2. Nạp bảng đích ban đầu

```sql
INSERT INTO inventory_demo (sku, quantity, status)
VALUES
    ('A',  5, 'ACTIVE'),
    ('B', 12, 'ACTIVE'),
    ('C',  4, 'ACTIVE'),
    ('D',  9, 'ACTIVE'),
    ('E',  0, 'INACTIVE'),
    ('H',  3, 'ACTIVE');
```

| sku | quantity | status | Ý nghĩa |
|---|---:|---|---|
| A | 5 | ACTIVE | Nguồn mới sẽ đổi thành 8 |
| B | 12 | ACTIVE | Nguồn mới giống dữ liệu hiện tại |
| C | 4 | ACTIVE | Nguồn yêu cầu REMOVE |
| D | 9 | ACTIVE | Nguồn yêu cầu SKIP |
| E | 0 | INACTIVE | Không xuất hiện trong nguồn |
| H | 3 | ACTIVE | Không xuất hiện trong nguồn |

Trước khi đồng bộ, bảng đích có **6 hàng**.

### 2.3. Nạp dữ liệu nguồn

```sql
INSERT INTO stock_feed_demo
    (feed_id, sku, operation, quantity, received_at)
VALUES
    (1, 'A', 'UPSERT',  8, TIMESTAMP '2025-09-01 08:00:00'),
    (2, 'B', 'UPSERT', 12, TIMESTAMP '2025-09-01 08:01:00'),
    (3, 'C', 'REMOVE',  0, TIMESTAMP '2025-09-01 08:02:00'),
    (4, 'D', 'SKIP',    9, TIMESTAMP '2025-09-01 08:03:00'),
    (5, 'F', 'UPSERT',  6, TIMESTAMP '2025-09-01 08:04:00'),
    (6, 'G', 'UPSERT',  2, TIMESTAMP '2025-09-01 08:05:00');
```

| feed_id | sku | operation | quantity | Tình huống |
|---:|---|---|---:|---|
| 1 | A | UPSERT | 8 | Đã có A, cần cập nhật |
| 2 | B | UPSERT | 12 | Đã có B, nhưng không đổi |
| 3 | C | REMOVE | 0 | Đã có C, cần xóa |
| 4 | D | SKIP | 9 | Đã có D, bỏ qua |
| 5 | F | UPSERT | 6 | Chưa có F, cần chèn |
| 6 | G | UPSERT | 2 | Chưa có G, cần chèn |

Các giá trị `operation` mang ý nghĩa **nghiệp vụ của ví dụ**:

- `UPSERT`: nếu đã có thì cập nhật; chưa có thì chèn.
- `REMOVE`: nếu đã có thì xóa sản phẩm; chưa có thì không tạo hàng.
- `SKIP`: không làm gì.

**Đây là feed thay đổi theo sự kiện, không phải ảnh chụp đầy đủ của tồn kho.** Vì vậy, sự vắng mặt của `E` và `H` trong nguồn **chưa phải lý do để xóa hoặc vô hiệu hóa** hai sản phẩm đó.

## 3. Trước MERGE: xem trước mối quan hệ nguồn–đích

Một lệnh `MERGE` thay đổi dữ liệu; nên bắt đầu bằng `SELECT` chỉ đọc để nhìn thấy nhánh dự kiến của từng hàng nguồn.

```sql
SELECT
    s.feed_id,
    s.sku,
    s.operation,
    s.quantity AS source_qty,
    t.quantity AS target_qty,
    t.status AS target_status,
    CASE
        WHEN t.sku IS NULL AND s.operation = 'UPSERT'
            THEN 'INSERT'
        WHEN t.sku IS NULL
            THEN 'NO ACTION - SOURCE ONLY'
        WHEN s.operation = 'REMOVE'
            THEN 'DELETE'
        WHEN s.operation = 'UPSERT'
             AND (
                 t.quantity IS DISTINCT FROM s.quantity
                 OR t.status IS DISTINCT FROM 'ACTIVE'
             )
            THEN 'UPDATE'
        ELSE 'NO ACTION - MATCHED'
    END AS expected_action
FROM stock_feed_demo AS s
LEFT JOIN inventory_demo AS t
    ON t.sku = s.sku
ORDER BY s.feed_id;
```

Kết quả:

| sku | source_qty | target_qty | expected_action |
|---|---:|---:|---|
| A | 8 | 5 | UPDATE |
| B | 12 | 12 | NO ACTION - MATCHED |
| C | 0 | 4 | DELETE |
| D | 9 | 9 | NO ACTION - MATCHED |
| F | 6 | `NULL` | INSERT |
| G | 2 | `NULL` | INSERT |

`LEFT JOIN` bắt đầu từ **nguồn**, nên hiển thị được hai sản phẩm `F` và `G` chưa có ở đích. Việc dùng `t.sku IS NULL` để phát hiện không khớp là hợp lý ở bảng mẫu vì `sku` là **khóa chính không `NULL`**. Không nên sử dụng một cột đích có thể `NULL` như `status` để suy ra “không tìm thấy hàng”.

Truy vấn xem trước trên chỉ mô tả **hành động dự kiến theo dữ liệu tại thời điểm đọc**. Dữ liệu có thể thay đổi trước khi `MERGE` thực thi trong môi trường có nhiều phiên đồng thời; vẫn phải kiểm tra kết quả sau câu DML.

### 3.1. Xem thêm những hàng chỉ có ở đích

```sql
SELECT t.sku, t.quantity, t.status
FROM inventory_demo AS t
WHERE NOT EXISTS (
    SELECT 1
    FROM stock_feed_demo AS s
    WHERE s.sku = t.sku
)
ORDER BY t.sku;
```

Kết quả: **E và H**.

Đây là các hàng **NOT MATCHED BY SOURCE**, nhưng trong kịch bản feed thay đổi ta **không có quyền suy luận rằng chúng đã bị loại khỏi danh mục nguồn**. Chỉ khi nguồn thật sự là snapshot đầy đủ và phạm vi so sánh đã được chốt, các hàng vắng mặt mới có thể trở thành ứng viên cho một nhánh xóa mềm/xóa cứng.

## 4. PostgreSQL 15+: MERGE với nhiều nhánh

PostgreSQL hỗ trợ `MERGE` từ **phiên bản 15**. Trên PostgreSQL 15 và những phiên bản hỗ trợ các nhánh tương ứng, ta có thể viết:

```sql
BEGIN;

MERGE INTO inventory_demo AS t
USING stock_feed_demo AS s
ON t.sku = s.sku

WHEN MATCHED AND s.operation = 'REMOVE' THEN
    DELETE

WHEN MATCHED
     AND s.operation = 'UPSERT'
     AND (
         t.quantity IS DISTINCT FROM s.quantity
         OR t.status IS DISTINCT FROM 'ACTIVE'
     ) THEN
    UPDATE
    SET quantity = s.quantity,
        status = 'ACTIVE'

WHEN MATCHED THEN
    DO NOTHING

WHEN NOT MATCHED AND s.operation = 'UPSERT' THEN
    INSERT (sku, quantity, status)
    VALUES (s.sku, s.quantity, 'ACTIVE')

WHEN NOT MATCHED THEN
    DO NOTHING;

SELECT sku, quantity, status
FROM inventory_demo
ORDER BY sku;

ROLLBACK;
```

Đây là **một câu MERGE**, dù nó có nhiều nhánh `WHEN`. `BEGIN`/`ROLLBACK` đặt lệnh vào giao dịch thử nghiệm. Nếu chạy phần giữa trên bộ dữ liệu ban đầu, kết quả sau `MERGE` nhưng trước `ROLLBACK` là:

| sku | quantity | status | Diễn giải |
|---|---:|---|---|
| A | 8 | ACTIVE | Cập nhật từ 5 thành 8 |
| B | 12 | ACTIVE | Giữ nguyên vì dữ liệu trùng |
| D | 9 | ACTIVE | Giữ nguyên do SKIP |
| E | 0 | INACTIVE | Giữ nguyên vì không có trong feed |
| F | 6 | ACTIVE | Chèn mới |
| G | 2 | ACTIVE | Chèn mới |
| H | 3 | ACTIVE | Giữ nguyên vì không có trong feed |

Từ **6 hàng đích** thành **7 hàng**: cập nhật A, xóa C, chèn F và G, trong khi B, D, E, H giữ nguyên.

Trong kịch bản ban đầu, các thao tác **trực tiếp làm thay đổi hàng** của bảng đích gồm:

- **1 UPDATE**: A.
- **1 DELETE**: C.
- **2 INSERT**: F và G.
- Tổng **4 hàng được thay đổi trực tiếp**.
- **Không thao tác**: B và D do nhánh `DO NOTHING`, E và H do không có hàng nguồn và chưa dùng nhánh `NOT MATCHED BY SOURCE`.

Số thao tác trên được tính theo dữ liệu mẫu. Trên các hệ và phiên bản khác, cách hiển thị số hàng bị ảnh hưởng có thể khác; đừng dùng một con số từ ví dụ như kết luận cho mọi câu `MERGE`.

### 4.1. Nhánh MATCHED + DELETE

```sql
WHEN MATCHED AND s.operation = 'REMOVE' THEN
    DELETE
```

Nếu nguồn yêu cầu `REMOVE` và khóa `sku` đã tồn tại ở đích, PostgreSQL xóa **hàng đích tương ứng**. Với nguồn `C`, hành động là xóa `inventory_demo('C', 4, 'ACTIVE')`.

Nếu một yêu cầu `REMOVE` không tìm thấy hàng đích, nó không được xếp vào nhóm `MATCHED`. Với các nhánh mẫu, nó rơi vào `WHEN NOT MATCHED THEN DO NOTHING`, tức không cần xóa thêm hàng nào.

**Cẩn thận:** một số phương ngữ, đặc biệt các phiên bản Oracle truyền thống, **không viết nhánh `WHEN MATCHED THEN DELETE` độc lập theo đúng mẫu PostgreSQL**. Phải dùng cú pháp xóa riêng của hệ đó.

### 4.2. Nhánh MATCHED + UPDATE

```sql
WHEN MATCHED
     AND s.operation = 'UPSERT'
     AND (
         t.quantity IS DISTINCT FROM s.quantity
         OR t.status IS DISTINCT FROM 'ACTIVE'
     ) THEN
    UPDATE
    SET quantity = s.quantity,
        status = 'ACTIVE'
```

Nhánh này chỉ cập nhật những sản phẩm:

1. **Đã có ở bảng đích**.
2. Được nguồn gửi với `operation = 'UPSERT'`.
3. Có số lượng hoặc trạng thái **thật sự khác** trạng thái mong muốn.

Sản phẩm `A` có `quantity = 5` trong đích, nguồn gửi `8`, nên cập nhật. Sản phẩm `B` đã có `quantity = 12`, `status = 'ACTIVE'`, khớp nguồn nên **không cần UPDATE**.

Việc tránh cập nhật giá trị không đổi có ích vì cập nhật vẫn có thể kích hoạt trigger, ghi log, tạo phiên bản hàng mới hoặc tăng tải ghi tùy DBMS. Trong PostgreSQL, `IS DISTINCT FROM` là so sánh **null-safe**, hữu ích khi cột có thể `NULL`; ở bảng mẫu, `quantity` và `status` đều `NOT NULL` nhưng cách viết vẫn thể hiện rõ ý định.

### 4.3. Nhánh MATCHED + DO NOTHING

```sql
WHEN MATCHED THEN
    DO NOTHING
```

Đây là **nhánh mặc định cho hàng đã khớp nhưng không thỏa hai nhánh phía trên**:

- `B`: `UPSERT` nhưng số lượng và trạng thái không đổi.
- `D`: `SKIP` theo yêu cầu của feed.

Trong PostgreSQL, `DO NOTHING` diễn đạt rõ rằng không thay đổi hàng. Trong SQL Server và một số hệ quản trị khác, người ta thường **bỏ nhánh** không cần thao tác, vì không có cú pháp `DO NOTHING` tương đương trong `MERGE`.

### 4.4. Nhánh NOT MATCHED + INSERT

```sql
WHEN NOT MATCHED AND s.operation = 'UPSERT' THEN
    INSERT (sku, quantity, status)
    VALUES (s.sku, s.quantity, 'ACTIVE')
```

Sản phẩm `F` và `G` có ở nguồn nhưng **chưa có ở đích**, nên trở thành hàng mới. Những hàng nguồn không tồn tại ở đích nhưng có `operation = 'REMOVE'` hoặc `SKIP` sẽ **không** được chèn bởi điều kiện `s.operation = 'UPSERT'`.

### 4.5. Thứ tự nhánh WHEN rất quan trọng

Với một hàng ứng viên, hệ quản trị chọn hành động dựa trên tình trạng khớp và **nhánh đủ điều kiện đầu tiên** theo quy tắc của lệnh. Vì vậy các nhánh **cụ thể** nên đặt trước nhánh **bao quát**.

Chẳng hạn, cách viết này phá ý định nghiệp vụ:

```sql
-- KHÔNG dùng trong bài toán đã nêu:
WHEN MATCHED THEN
    UPDATE SET quantity = s.quantity

WHEN MATCHED AND s.operation = 'REMOVE' THEN
    DELETE
```

Nhánh `WHEN MATCHED` không điều kiện có thể nhận **mọi hàng đã khớp** trước khi nhánh `REMOVE` có cơ hội chạy; một số DBMS còn từ chối cách sắp xếp điều kiện không hợp lệ. Cần để nhánh `REMOVE` và nhánh `UPSERT` có điều kiện **trước** nhánh bắt tất cả.

**Một hàng ứng viên không phải lần lượt trải qua DELETE rồi UPDATE rồi INSERT.** MERGE là **chọn nhánh xử lý**, không phải thực thi mọi mệnh đề `WHEN` theo kiểu chuỗi câu lệnh lập trình.

## 5. Điều kiện ON phải xác định danh tính, không nên trộn quy tắc hành động

Điều kiện `ON` nên diễn đạt câu hỏi: **“Hàng nguồn này có tương ứng với hàng đích nào?”**

Trong bảng tồn kho:

```sql
ON t.sku = s.sku
```

`sku` là khóa chính của đích, đồng thời được giả định là khóa nghiệp vụ của feed. Ta **không** đưa `status` hay `quantity` vào tiêu chí xác định cùng sản phẩm.

### 5.1. Một ON sai có thể biến UPDATE thành INSERT

Ví dụ ý tưởng sai:

```sql
-- Không dùng làm điều kiện nhận diện sản phẩm:
ON t.sku = s.sku
   AND t.status = 'ACTIVE'
```

Nếu sản phẩm `E` đang `INACTIVE` nhưng nguồn gửi `UPSERT` cho chính `E`, điều kiện trên coi hai hàng là **không khớp** chỉ vì trạng thái đích khác `ACTIVE`. Nhánh `INSERT` có thể cố chèn thêm `E`, rồi gặp lỗi `PRIMARY KEY`.

Nếu muốn **tái kích hoạt hàng inactive**, hãy giữ khóa nhận diện trong `ON`:

```sql
ON t.sku = s.sku
```

sau đó đưa điều kiện trạng thái vào `WHEN MATCHED AND ... THEN UPDATE`.

### 5.2. Trường hợp khóa nhiều cột

Không phải mọi bảng đều có một mã `sku` duy nhất. Một bảng tồn kho theo kho có thể dùng **khóa ghép**:

```sql
PRIMARY KEY (warehouse_id, sku)
```

Lúc đó điều kiện khớp phải dùng **cả hai cột**:

```sql
ON t.warehouse_id = s.warehouse_id
AND t.sku = s.sku
```

Nếu chỉ dùng `sku`, dữ liệu của hai kho có thể bị nhập nhằng, một hàng nguồn có thể khớp nhiều hàng đích và thao tác trở nên sai hoặc bị từ chối.

### 5.3. Khóa NULL là vấn đề khác với hàng không khớp

Trong SQL, `NULL = NULL` không trả `TRUE` mà trả `UNKNOWN`. Nếu một khóa nghiệp vụ có thể `NULL`, hai hàng đều thiếu khóa có thể không khớp bằng dấu `=`; điều này có thể tạo lỗi chèn trùng hoặc báo kết quả không mong muốn.

Trong bảng mẫu, `inventory_demo.sku` là `PRIMARY KEY` và `stock_feed_demo.sku` là `NOT NULL`, nên không phát sinh trường hợp này.

Trong hệ thống thật nên ưu tiên:

- Khóa nghiệp vụ **có giá trị, được chuẩn hóa và duy nhất**.
- Ràng buộc `UNIQUE`/`PRIMARY KEY` thích hợp trên bảng đích.
- Kiểm tra hoặc cách ly hàng nguồn **thiếu khóa** trước khi MERGE.
- Nếu thực sự cần so khớp `NULL` như một giá trị, phải thiết kế **so sánh null-safe** theo DBMS và hiểu tác động với uniqueness; không chỉ đổi `=` thành một biểu thức bất kỳ.

## 6. Nguồn trùng khóa: bẫy quan trọng nhất của MERGE

Trong bảng `stock_feed_demo`, `feed_id` là duy nhất nhưng `sku` không có ràng buộc `UNIQUE`. Một feed lớn có thể chứa nhiều bản ghi cho cùng SKU do gửi lại thông điệp, cập nhật nhiều lần hoặc lỗi nhập.

Giả sử có hai dòng nguồn:

```text
feed_id  sku  operation  quantity
1        A    UPSERT        8
7        A    UPSERT        9
```

Cả hai có thể cùng khớp **một hàng đích `A`**. Trên các DBMS như PostgreSQL và SQL Server, việc một câu `MERGE` cố cập nhật/xóa cùng hàng đích nhiều lần thường gây **lỗi cardinality hoặc lỗi tương đương**, thay vì chọn hàng nguồn bất kỳ như mong muốn.

Nếu hai dòng nguồn cùng là `F` trong khi `F` chưa có ở đích, chúng có thể cùng cố `INSERT` một khóa và vấp **ràng buộc duy nhất**.

### 6.1. Kiểm tra khóa nguồn trước khi MERGE

```sql
SELECT
    sku,
    COUNT(*) AS source_rows
FROM stock_feed_demo
GROUP BY sku
HAVING COUNT(*) > 1
ORDER BY source_rows DESC, sku;
```

Với bộ dữ liệu khởi tạo, kết quả **rỗng** vì mỗi SKU xuất hiện một lần.

Nếu truy vấn trả hàng, cần làm rõ **nghiệp vụ nào đúng**:

- Một bản ghi là **gửi lại** cùng dữ liệu nên bỏ bản sao?
- Một SKU có **nhiều lần cập nhật theo thời gian** cần lấy sự kiện mới nhất?
- Các dòng là **chênh lệch cần cộng dồn** (increment) thay vì giá trị tuyệt đối?
- Có một bản ghi `REMOVE` và một bản ghi `UPSERT` cùng SKU; thứ tự sự kiện nào được phép thắng?

**Không phải mọi trường hợp trùng khóa đều được xử lý đúng bằng `DISTINCT`**. `DISTINCT` chỉ loại hàng giống nhau trên các cột được chọn, không giải quyết xung đột giữa số lượng 8 và 9.

### 6.2. Chọn một phiên bản nguồn có thứ tự xác định

Giả sử hợp đồng dữ liệu quy định: **lấy bản ghi được nhận mới nhất của mỗi SKU; nếu cùng thời điểm, chọn `feed_id` lớn hơn**. PostgreSQL có thể chuẩn hóa nguồn:

```sql
WITH ranked_feed AS (
    SELECT
        f.*,
        ROW_NUMBER() OVER (
            PARTITION BY f.sku
            ORDER BY f.received_at DESC, f.feed_id DESC
        ) AS rn
    FROM stock_feed_demo AS f
)
SELECT
    feed_id,
    sku,
    operation,
    quantity,
    received_at
FROM ranked_feed
WHERE rn = 1
ORDER BY sku;
```

`feed_id` là khóa kỹ thuật duy nhất, nên tiêu chí sắp xếp có **khóa phân định** khi thời điểm bằng nhau. CTE này chọn tối đa **một hàng nguồn mỗi SKU**.

Nếu định dùng nó làm nguồn của MERGE:

```sql
MERGE INTO inventory_demo AS t
USING (
    SELECT sku, operation, quantity
    FROM (
        SELECT
            f.*,
            ROW_NUMBER() OVER (
                PARTITION BY sku
                ORDER BY received_at DESC, feed_id DESC
            ) AS rn
        FROM stock_feed_demo AS f
    ) AS ranked
    WHERE rn = 1
) AS s
ON t.sku = s.sku
WHEN MATCHED AND s.operation = 'REMOVE' THEN
    DELETE
WHEN MATCHED
     AND s.operation = 'UPSERT'
     AND (
         t.quantity IS DISTINCT FROM s.quantity
         OR t.status IS DISTINCT FROM 'ACTIVE'
     ) THEN
    UPDATE SET quantity = s.quantity,
               status = 'ACTIVE'
WHEN NOT MATCHED AND s.operation = 'UPSERT' THEN
    INSERT (sku, quantity, status)
    VALUES (s.sku, s.quantity, 'ACTIVE');
```

Lệnh này **vẫn thực sự thay đổi dữ liệu** nếu chạy. Trong thực hành, dùng giao dịch `BEGIN ... ROLLBACK`. Khi nguồn không trùng như dữ liệu mẫu, kết quả nghiệp vụ giống mục 4.

**Điều kiện tiên quyết:** chọn sự kiện có `received_at` mới nhất chỉ đúng nếu hệ thống nguồn xác nhận thời điểm nhận là thứ tự sự kiện đáng tin cậy. Nếu feed có **event_version**, sequence theo SKU hay thời điểm hiệu lực, nên dùng tiêu chí nghiệp vụ đó. Một sự kiện cũ đến muộn có thể làm “mới nhất theo thời điểm nhận” trở thành **phiên bản sai**.

### 6.3. Chênh lệch số lượng không giống trạng thái số lượng

Nếu `quantity = 8` nghĩa “số lượng tồn kho hiện tại là 8”, nhánh cập nhật phải **gán**:

```sql
SET quantity = s.quantity
```

Nếu `quantity = 8` nghĩa “tăng thêm 8 đơn vị”, có thể cần:

```sql
SET quantity = t.quantity + s.quantity
```

Đây là hai nghĩa khác nhau. Đối với các **sự kiện cộng dồn**, chỉ chọn một bản ghi mới nhất có thể làm **mất những thay đổi hợp lệ trước đó**. Cần thiết kế quy tắc chống xử lý lặp, thứ tự sự kiện và tính đúng đắn trong điều kiện đồng thời.

## 7. Phân biệt đồng bộ tăng dần và đồng bộ snapshot đầy đủ

Hai mô hình nhập dữ liệu thường gặp:

| Thuộc tính | **Incremental feed** | **Full snapshot** |
|---|---|---|
| Nội dung nguồn | Chỉ những bản ghi/sự kiện thay đổi | Toàn bộ bản ghi hiện hành trong một phạm vi |
| Hàng đích không xuất hiện ở nguồn | Thường **giữ nguyên** | Có thể là hàng đã bị loại khỏi nguồn |
| Nhánh `NOT MATCHED BY SOURCE` | Thường **không dùng** để xóa | Có thể đánh dấu inactive hoặc xóa sau khi xác minh |
| Điều kiện cần | Xử lý trùng sự kiện, thứ tự và idempotency | Xác nhận snapshot hoàn chỉnh và phạm vi |
| Rủi ro | Bỏ sót sự kiện, gửi lại sự kiện | Xóa nhầm hàng khi snapshot thiếu dữ liệu |

Bộ dữ liệu thực hành ở mục 2 là **incremental feed**. Do đó câu `MERGE` PostgreSQL ở mục 4 **không** động đến E/H, dù E/H không xuất hiện ở nguồn.

### 7.1. Vì sao xóa theo “vắng mặt ở nguồn” nguy hiểm?

Giả sử nguồn chỉ gửi những SKU thuộc kho số 1, nhưng bảng đích chứa cả kho số 1 và số 2. Nếu viết một nhánh kiểu “đích không có trong nguồn thì xóa” trên **toàn bộ đích**, mọi sản phẩm của kho số 2 có thể bị chọn nhầm.

Tương tự, nếu pipeline nạp lỗi và snapshot chỉ chứa một nửa bản ghi, nhánh xóa theo vắng mặt có thể làm **mất một nửa dữ liệu đang đúng**.

Muốn áp dụng nhánh đó cần:

1. Xác nhận đây là **snapshot đầy đủ** và đã tải xong.
2. Xác định **phạm vi snapshot** (đơn vị kinh doanh, kho, khu vực, ngày hiệu lực).
3. Kiểm tra số hàng nguồn, khóa phân biệt và số hàng đích dự kiến bị ảnh hưởng.
4. Chọn **xóa mềm** hay **xóa cứng** theo chính sách.
5. Có transaction, audit, giới hạn tác động và khả năng phục hồi.

### 7.2. Xóa mềm thường phù hợp hơn xóa cứng

Nếu sản phẩm không còn trong snapshot mới, một hành động:

```sql
SET status = 'INACTIVE'
```

có thể phù hợp hơn `DELETE` vì giữ bản ghi cho đơn hàng lịch sử, phân tích báo cáo hoặc khôi phục khi lỗi đồng bộ. Khi cần xóa cứng, phải biết các khóa ngoại, yêu cầu lưu trữ và hệ thống liên quan.

## 8. SQL Server: MATCHED, NOT MATCHED BY TARGET, NOT MATCHED BY SOURCE

SQL Server hỗ trợ `MERGE` với các nhánh phân biệt rõ **nguồn-only** và **đích-only**. Mẫu sau có **nhánh đồng bộ snapshot đầy đủ** để minh họa; nó **không** mang cùng ý định với nguồn incremental của bài nếu chạy trực tiếp trên feed thay đổi.

Giả sử các bảng tương đương đã được tạo trong schema `dbo`:

```sql
-- SQL Server: chỉ dùng WHEN NOT MATCHED BY SOURCE khi dữ liệu
-- nguồn là snapshot đầy đủ của phạm vi đồng bộ.
MERGE INTO dbo.inventory_demo AS t
USING dbo.stock_feed_demo AS s
    ON t.sku = s.sku

WHEN MATCHED AND s.operation = 'REMOVE' THEN
    DELETE

WHEN MATCHED
     AND s.operation = 'UPSERT'
     AND (
         t.quantity <> s.quantity
         OR t.status <> 'ACTIVE'
     ) THEN
    UPDATE
    SET quantity = s.quantity,
        status = 'ACTIVE'

WHEN NOT MATCHED BY TARGET
     AND s.operation = 'UPSERT' THEN
    INSERT (sku, quantity, status)
    VALUES (s.sku, s.quantity, 'ACTIVE')

WHEN NOT MATCHED BY SOURCE
     AND t.status = 'ACTIVE' THEN
    UPDATE
    SET status = 'INACTIVE'

OUTPUT
    $action AS merge_action,
    deleted.sku AS old_sku,
    inserted.sku AS new_sku,
    deleted.quantity AS old_qty,
    inserted.quantity AS new_qty;
```

**Lưu ý bắt buộc của SQL Server:** câu `MERGE` phải được kết thúc bằng **dấu chấm phẩy** như ở trên.

### 8.1. So sánh với ví dụ PostgreSQL

Ở SQL Server:

- `WHEN MATCHED ... DELETE`: xóa C.
- `WHEN MATCHED ... UPDATE`: cập nhật A.
- Không viết nhánh `DO NOTHING`: B và D không thỏa nhánh thay đổi nào nên được giữ.
- `WHEN NOT MATCHED BY TARGET ... INSERT`: chèn F và G.
- `WHEN NOT MATCHED BY SOURCE AND t.status = 'ACTIVE' THEN UPDATE`: đánh dấu **H** thành `INACTIVE` vì H vắng mặt trong nguồn; E vốn đã inactive nên giữ nguyên.

Kết quả **có 5 hàng trực tiếp được thay đổi** nếu áp dụng nhánh đích-only này trên trạng thái ban đầu: 1 UPDATE A, 1 DELETE C, 2 INSERT F/G và 1 UPDATE H. Tổng số hàng đích sau vẫn là **7**, nhưng `H.status` đã trở thành `INACTIVE`.

Sự khác biệt này **không phải vì SQL Server tự quyết định xóa H**, mà vì **người viết đã thêm nhánh `NOT MATCHED BY SOURCE`**. Trên incremental feed của bài, phải **bỏ nhánh đó** để giữ H như cũ.

### 8.2. OUTPUT $action giúp kiểm tra nhánh thực thi

`OUTPUT` có thể trả thông tin của hàng đã thay đổi:

| Giá trị `$action` | Ý nghĩa |
|---|---|
| `INSERT` | Đã chèn hàng mới |
| `UPDATE` | Đã cập nhật hàng đích |
| `DELETE` | Đã xóa hàng đích |

Các bảng logic `inserted` và `deleted` thể hiện hình ảnh sau/trước thay đổi theo cơ chế `OUTPUT`. Không phải mọi hành động đều có giá trị ở cả hai phía:

- `INSERT` có hàng mới; phía `deleted` không có hàng trước.
- `DELETE` có hàng cũ; phía `inserted` không có hàng mới.
- `UPDATE` có cả giá trị trước và sau.

Nếu cần báo cáo “đã chèn bao nhiêu, sửa bao nhiêu, xóa bao nhiêu”, ứng dụng có thể thu và nhóm các hàng `OUTPUT` theo `$action`. Các hàng không thay đổi **không có hành động DML để báo**.

SQL Server còn có `@@ROWCOUNT` để đọc số hàng ảnh hưởng của lệnh vừa thực thi. Cần đọc ngay sau lệnh liên quan, vì một câu SQL tiếp theo có thể làm thay đổi trạng thái này.

### 8.3. Giới hạn nhánh MATCHED trong SQL Server

SQL Server có các giới hạn cú pháp cho số nhánh `WHEN MATCHED` và các kiểu hành động có thể kết hợp. Một mô hình thường gặp là:

```sql
WHEN MATCHED AND s.operation = 'REMOVE' THEN DELETE
WHEN MATCHED AND s.operation = 'UPSERT' THEN UPDATE SET ...
```

Không được tùy tiện thêm nhiều nhánh `WHEN MATCHED` cùng loại hành động rồi nghĩ chúng sẽ chạy tuần tự. Hãy đối chiếu tài liệu của **đúng SQL Server phiên bản đang chạy** và thiết kế các điều kiện sao cho mỗi hàng đủ điều kiện cho **một hành động có chủ đích**.

### 8.4. Những lưu ý vận hành riêng của SQL Server

`MERGE` của SQL Server có các khuyến cáo và tình huống cần thận trọng về **đồng thời, khóa, trigger, kế hoạch thực thi và hành vi theo phiên bản**. Với bài toán rất đơn giản, nhiều hệ thống chọn **lệnh `UPDATE` và `INSERT` riêng** thay vì một `MERGE` phức tạp để dễ quan sát, tối ưu và kiểm thử.

Không cho rằng một lệnh `MERGE` tự giải quyết hoàn toàn race condition của hai phiên cùng chèn một khóa. Cần ràng buộc duy nhất, transaction và chiến lược khóa/phân lập phù hợp. Trên SQL Server, có thể gặp các mẫu dùng `HOLDLOCK` hoặc cơ chế khóa khác, nhưng phải đánh giá tác động với mức đồng thời của hệ thống, không chèn hint tùy tiện vào mọi câu.

## 9. Oracle Database: MERGE có UPDATE, INSERT và DELETE WHERE

Oracle Database có `MERGE` từ lâu, nhưng **cách xóa hàng trong MERGE truyền thống khác PostgreSQL và SQL Server**.

Trong nhiều phiên bản Oracle, khi muốn xóa một hàng đích bằng `MERGE`, dùng mệnh đề **`DELETE WHERE` nằm trong nhánh `WHEN MATCHED THEN UPDATE`**, không phải một nhánh `WHEN MATCHED THEN DELETE` độc lập theo mẫu PostgreSQL.

### 9.1. Ví dụ Oracle tương đương về ý định

Giả sử hai bảng `inventory_demo` và `stock_feed_demo` có cấu trúc cột tương đương trên Oracle:

```sql
-- Oracle Database: minh họa cú pháp MERGE truyền thống.
MERGE INTO inventory_demo t
USING stock_feed_demo s
ON (t.sku = s.sku)

WHEN MATCHED THEN
    UPDATE SET
        t.quantity = CASE
            WHEN s.operation = 'UPSERT' THEN s.quantity
            ELSE t.quantity
        END,
        t.status = CASE
            WHEN s.operation = 'UPSERT' THEN 'ACTIVE'
            ELSE t.status
        END
    WHERE
        s.operation = 'REMOVE'
        OR (
            s.operation = 'UPSERT'
            AND (
                t.quantity <> s.quantity
                OR t.status <> 'ACTIVE'
            )
        )
    DELETE WHERE s.operation = 'REMOVE'

WHEN NOT MATCHED THEN
    INSERT (sku, quantity, status)
    VALUES (s.sku, s.quantity, 'ACTIVE')
    WHERE s.operation = 'UPSERT';
```

Diễn giải:

- Hàng **A** thỏa `UPSERT` và khác số lượng, được cập nhật.
- Hàng **B** không khác số lượng/trạng thái, nên điều kiện `UPDATE WHERE` bỏ qua.
- Hàng **C** có `operation = 'REMOVE'`, được đưa qua nhánh cập nhật rồi thỏa **`DELETE WHERE`**, nên bị xóa.
- Hàng **D** có `SKIP`, không thỏa điều kiện cập nhật.
- F/G không khớp đích và là `UPSERT`, nên được chèn.
- E/H vắng mặt trong nguồn và không có nhánh độc lập dành cho hàng đích-only trong mẫu Oracle truyền thống, nên được giữ.

### 9.2. DELETE WHERE của Oracle có hai điều đặc biệt

**Thứ nhất:** `DELETE WHERE` áp dụng đối với những hàng đích đã **được cập nhật bởi phần `UPDATE` của MERGE**. Nó không phải một thao tác `DELETE` độc lập trên toàn bảng.

**Thứ hai:** điều kiện `DELETE WHERE` được đánh giá theo **giá trị sau cập nhật** của cột đích khi tham chiếu các cột đó. Trong ví dụ, `DELETE WHERE s.operation = 'REMOVE'` dựa trên loại sự kiện nguồn nên ý định dễ đọc.

Điều này giải thích vì sao nhánh Oracle có `UPDATE SET ... WHERE ... DELETE WHERE ...` thay vì đặt `DELETE` như một nhánh ngang hàng với `UPDATE`.

### 9.3. Không cập nhật cột được tham chiếu trong ON ở Oracle

Oracle có giới hạn quan trọng: **không thể cập nhật cột đích đã được tham chiếu trong điều kiện `ON` của MERGE** theo cú pháp truyền thống. Ví dụ:

```sql
ON (t.sku = s.sku)
```

đã dùng `t.sku` để nhận diện hàng; không nên cố `UPDATE SET t.sku = ...` trong cùng MERGE. Nếu cần thay đổi khóa nghiệp vụ, hãy thiết kế quy trình di chuyển/đổi khóa riêng, kiểm tra các bảng tham chiếu và quy tắc duy nhất.

### 9.4. Oracle và điều kiện không khớp

Ở Oracle, phần chèn thường viết:

```sql
WHEN NOT MATCHED THEN
    INSERT (sku, quantity, status)
    VALUES (s.sku, s.quantity, 'ACTIVE')
    WHERE s.operation = 'UPSERT'
```

Khác cách viết của PostgreSQL:

```sql
WHEN NOT MATCHED AND s.operation = 'UPSERT' THEN
    INSERT (...)
    VALUES (...)
```

Hai cách có mục tiêu giống nhau nhưng **vị trí điều kiện khác**. Không chỉ sao chép nguyên mệnh đề `WHEN NOT MATCHED AND ...` giữa Oracle và PostgreSQL mà chưa kiểm tra phiên bản.

Khi cần làm thao tác “hàng ở đích nhưng không có trong nguồn thì inactive”, các phiên bản Oracle truyền thống thường dùng **một câu `UPDATE ... WHERE NOT EXISTS (...)` riêng** với giao dịch phù hợp. Không tự giả định mọi Oracle có nhánh `WHEN NOT MATCHED BY SOURCE` giống SQL Server.

## 10. PostgreSQL: MERGE khác INSERT ... ON CONFLICT

Trên PostgreSQL, một cách rất phổ biến để **chèn nếu chưa có, cập nhật nếu đã có** là:

```sql
INSERT INTO inventory_demo (sku, quantity, status)
VALUES ('A', 8, 'ACTIVE')
ON CONFLICT (sku) DO UPDATE
SET quantity = EXCLUDED.quantity,
    status = EXCLUDED.status;
```

`EXCLUDED` là tên đặc biệt cho **giá trị hàng đang được thử chèn** nhưng gặp xung đột khóa. `ON CONFLICT (sku)` dựa trên ràng buộc duy nhất/khóa chính phù hợp ở bảng đích.

### 10.1. Khi nào ON CONFLICT đơn giản hơn MERGE?

Nếu nghiệp vụ chỉ có hai hành động:

```text
Khóa chưa tồn tại -> INSERT
Khóa đã tồn tại  -> UPDATE
```

thì `INSERT ... ON CONFLICT DO UPDATE` thường rất phù hợp. Nó cũng cung cấp cơ chế upsert gắn với ràng buộc duy nhất. PostgreSQL mô tả `ON CONFLICT DO UPDATE` với những bảo đảm về kết quả **chèn hoặc cập nhật** trong các điều kiện đồng thời mà không nên đánh đồng với `MERGE`.

Ngược lại, khi cần nhiều nhánh như `REMOVE`, `SKIP`, cập nhật có điều kiện và phân loại nguồn/đích, `MERGE` có thể mô tả quy tắc tập trung và dễ theo dõi hơn.

### 10.2. ON CONFLICT cho tập UPSERT của feed

```sql
BEGIN;

INSERT INTO inventory_demo (sku, quantity, status)
SELECT
    s.sku,
    s.quantity,
    'ACTIVE'
FROM stock_feed_demo AS s
WHERE s.operation = 'UPSERT'
ON CONFLICT (sku) DO UPDATE
SET quantity = EXCLUDED.quantity,
    status = EXCLUDED.status
WHERE inventory_demo.quantity IS DISTINCT FROM EXCLUDED.quantity
   OR inventory_demo.status IS DISTINCT FROM EXCLUDED.status;

SELECT sku, quantity, status
FROM inventory_demo
ORDER BY sku;

ROLLBACK;
```

Lệnh trên xử lý:

- A: cập nhật.
- B: trùng dữ liệu nên bỏ qua cập nhật nhờ điều kiện `WHERE`.
- F/G: chèn.
- **C: không bị xóa**, vì nguồn `REMOVE` bị loại khỏi phần `SELECT`.

Đây là điểm khác biệt quan trọng: `ON CONFLICT` giải quyết **xung đột khóa khi chèn**, không tự mang các nhánh `DELETE` hoặc **NOT MATCHED BY SOURCE** của `MERGE`.

Nếu cần xóa C, phải có thao tác riêng hoặc chọn `MERGE` phù hợp.

### 10.3. MERGE không phải lúc nào cũng tương đương upsert nguyên tử theo khóa

Khi hai phiên đồng thời đều thấy một khóa “chưa có”, `MERGE` có thể gặp **xung đột ràng buộc duy nhất** lúc cố chèn, tùy DBMS, điều kiện và chiến lược khóa. Không mặc định chỉ vì `MERGE` là một câu lệnh thì mọi race condition đã được xử lý tự động.

Trên PostgreSQL, `INSERT ... ON CONFLICT DO UPDATE` là cơ chế upsert chuyên dụng trên khóa duy nhất; `MERGE` là cơ chế **so khớp và chọn nhiều loại hành động**. Chọn đúng công cụ theo nhu cầu và vẫn giữ ràng buộc khóa ở database.

## 11. MySQL: không có MERGE tiêu chuẩn, dùng ON DUPLICATE KEY UPDATE

Trong MySQL, mẫu phổ biến cho insert-or-update là:

```sql
-- MySQL: nếu sku đã tồn tại theo PRIMARY KEY/UNIQUE,
-- cập nhật quantity và status.
INSERT INTO inventory_demo (sku, quantity, status)
VALUES ('A', 8, 'ACTIVE')
ON DUPLICATE KEY UPDATE
    quantity = 8,
    status = 'ACTIVE';
```

Nếu `A` chưa có, MySQL chèn hàng. Nếu `A` đã có với khóa xung đột, MySQL chạy nhánh cập nhật.

### 11.1. Điểm khác MERGE

| Đặc điểm | `MERGE` theo nhánh | MySQL `ON DUPLICATE KEY UPDATE` |
|---|---|---|
| Xác định khớp | `ON` do người viết chỉ định | Xung đột `PRIMARY KEY`/`UNIQUE` |
| INSERT khi chưa có | Có | Có |
| UPDATE khi đã có | Có, kèm điều kiện nhánh | Có khi xung đột khóa |
| DELETE theo sự kiện REMOVE | Có ở các MERGE hỗ trợ | Không nằm trong cùng mẫu upsert này |
| NOT MATCHED BY SOURCE | Có trên một số DBMS | Không có nhánh tương đương trực tiếp |
| Lấy kết quả theo từng nhánh | Tùy DBMS, ví dụ `OUTPUT $action` | Cơ chế số hàng bị ảnh hưởng có quy tắc riêng |

**Cẩn thận với nhiều khóa duy nhất:** Nếu bảng có nhiều `UNIQUE` constraint/index khác nhau, `ON DUPLICATE KEY UPDATE` có thể phát sinh từ **bất kỳ xung đột khóa duy nhất nào** đủ điều kiện, không đơn thuần từ một `ON t.sku = s.sku` như MERGE. Cần kiểm tra cấu trúc ràng buộc trước khi dùng.

### 11.2. Cách tham chiếu giá trị được chèn

Nhiều ví dụ cũ viết:

```sql
-- Cú pháp lịch sử của MySQL; cần xem tài liệu phiên bản:
INSERT INTO inventory_demo (sku, quantity, status)
VALUES ('A', 8, 'ACTIVE')
ON DUPLICATE KEY UPDATE
    quantity = VALUES(quantity),
    status = VALUES(status);
```

Trong các bản MySQL hiện đại, cách dùng `VALUES(col)` ở phần này đã có thay đổi về khuyến cáo/tính tương lai. Khi xây dựng ứng dụng mới, hãy kiểm tra cú pháp **row alias** của phiên bản cụ thể thay vì sao chép mẫu cũ một cách máy móc. Với ví dụ đơn giản, dùng tham số được truyền ở cả giá trị `INSERT` và nhánh `UPDATE` cũng có thể làm rõ ý định.

### 11.3. Số hàng bị ảnh hưởng không luôn bằng số khóa xử lý

MySQL có quy ước số hàng bị ảnh hưởng khác nhau khi `INSERT ... ON DUPLICATE KEY UPDATE`:

- Hàng được chèn mới.
- Hàng tồn tại và bị cập nhật thành giá trị khác.
- Hàng tồn tại nhưng được gán lại **chính giá trị cũ**.

Các trường hợp này có thể được tính/hiển thị khác nhau theo hành động và cờ kết nối như `CLIENT_FOUND_ROWS`. Vì thế không nên suy luận “`ROW_COUNT() = 2` nghĩa là đã xử lý đúng hai sản phẩm” nếu chưa biết chính xác quy ước của MySQL và driver đang dùng.

**Một nguồn UPSERT có nhiều hàng cùng SKU vẫn cần được chuẩn hóa**. Không mặc định mọi hệ thống sẽ chọn “sự kiện mới nhất” đúng nghiệp vụ nếu đưa nhiều hàng xung đột vào cùng một đợt chèn.

## 12. SQLite: INSERT ... ON CONFLICT DO UPDATE

SQLite cũng không sử dụng cú pháp `MERGE INTO ... USING ... WHEN ...` cho bài toán upsert thông thường. Từ phiên bản **3.24.0**, SQLite hỗ trợ dạng:

```sql
-- SQLite
INSERT INTO inventory_demo (sku, quantity, status)
VALUES ('A', 8, 'ACTIVE')
ON CONFLICT(sku) DO UPDATE SET
    quantity = excluded.quantity,
    status = excluded.status;
```

`excluded.quantity` là giá trị được thử chèn; `inventory_demo.quantity` là giá trị hiện có của bảng đích trong biểu thức cập nhật.

### 12.1. Chỉ cập nhật khi thật sự khác

```sql
-- SQLite
INSERT INTO inventory_demo (sku, quantity, status)
VALUES ('A', 8, 'ACTIVE')
ON CONFLICT(sku) DO UPDATE SET
    quantity = excluded.quantity,
    status = excluded.status
WHERE inventory_demo.quantity IS NOT excluded.quantity
   OR inventory_demo.status IS NOT excluded.status;
```

Với các cột không `NULL` của bộ dữ liệu mẫu, điều kiện này giúp bỏ cập nhật không cần thiết. SQLite có những phép so sánh null-safe như `IS`/`IS NOT`; cú pháp và ý nghĩa không cần trùng nguyên văn với `IS DISTINCT FROM` của PostgreSQL.

Nếu chỉ muốn bỏ qua xung đột:

```sql
INSERT INTO inventory_demo (sku, quantity, status)
VALUES ('A', 8, 'ACTIVE')
ON CONFLICT(sku) DO NOTHING;
```

`DO NOTHING` ở đây thuộc **nhánh upsert của `INSERT`**, **không phải** nhánh `DO NOTHING` trong lệnh `MERGE` của PostgreSQL.

### 12.2. Tránh nhầm REPLACE với UPDATE

SQLite còn có `INSERT OR REPLACE` hoặc hành vi xung đột `REPLACE`. Trong nhiều trường hợp, nó **xóa hàng cũ rồi chèn hàng mới**, thay vì cập nhật tại chỗ. Điều đó có thể ảnh hưởng khóa ngoại, trigger và ID; không nên mặc định `REPLACE` là phiên bản khác của `DO UPDATE`.

### 12.3. SQLite và RETURNING

SQLite từ phiên bản **3.35.0** hỗ trợ `RETURNING` cho những lệnh DML phù hợp. Tuy nhiên, nó không biến `INSERT ... ON CONFLICT` thành một `MERGE` có đầy đủ nhánh `MATCHED DELETE`/`NOT MATCHED BY SOURCE`. Nếu cần đồng bộ kèm xóa, thường phải dùng **nhiều câu lệnh có giao dịch** hoặc cơ chế ứng dụng phù hợp.

## 13. Bảng đối chiếu các nhánh theo phương ngữ

| Tình huống | PostgreSQL 15+ | SQL Server | Oracle Database truyền thống | MySQL | SQLite |
|---|---|---|---|---|---|
| Nguồn khớp đích → UPDATE | `WHEN MATCHED ... UPDATE` | `WHEN MATCHED ... UPDATE` | `WHEN MATCHED THEN UPDATE SET ... WHERE ...` | `ON DUPLICATE KEY UPDATE` dựa trên khóa duy nhất | `ON CONFLICT(...) DO UPDATE` |
| Nguồn chưa có ở đích → INSERT | `WHEN NOT MATCHED ... INSERT` | `WHEN NOT MATCHED BY TARGET ... INSERT` | `WHEN NOT MATCHED THEN INSERT ... WHERE ...` | `INSERT` thông thường nếu không xung đột | `INSERT` thông thường nếu không xung đột |
| Nguồn khớp, yêu cầu REMOVE | Có nhánh `WHEN MATCHED ... DELETE` | Có nhánh `WHEN MATCHED ... DELETE` | `DELETE WHERE` gắn với `UPDATE` | `DELETE` riêng | `DELETE` riêng |
| Nhánh không cần làm gì | `DO NOTHING` | Không thêm nhánh hành động | Điều kiện `UPDATE WHERE`/`INSERT WHERE` lọc hàng | `DO NOTHING` không phải cú pháp tương ứng của MySQL; có thể bỏ cập nhật theo thiết kế | `DO NOTHING` trong `ON CONFLICT` |
| Đích không có ở nguồn | Phụ thuộc phiên bản và tập nhánh được hỗ trợ; không giả định có trên PG15 | `WHEN NOT MATCHED BY SOURCE` | Thường xử lý bằng câu `UPDATE/DELETE ... NOT EXISTS` riêng trên phiên bản truyền thống | Thường dùng câu riêng | Thường dùng câu riêng |
| Trả hành động/hàng thay đổi | Phụ thuộc phiên bản `MERGE` và khả năng `RETURNING` | `OUTPUT $action, inserted..., deleted...` | Cơ chế `RETURNING`/API phụ thuộc loại lệnh và phiên bản | Đọc số hàng, truy vấn kiểm tra theo nhu cầu | `RETURNING` trên DML hỗ trợ, theo phiên bản |
| Khai báo khóa khớp | Điều kiện `ON` | Điều kiện `ON` | Điều kiện `ON` | Xung đột ràng buộc `UNIQUE`/`PRIMARY KEY` | Đích xung đột `ON CONFLICT(...)` |

**Bảng này mô tả các mẫu thường gặp, không khẳng định mọi phiên bản có cùng khả năng.** Đặc biệt với PostgreSQL, hỗ trợ `MERGE` bắt đầu từ 15 và các tùy chọn `WHEN NOT MATCHED BY SOURCE`, `RETURNING` hoặc tính năng phụ có thể được mở rộng ở các bản sau. Với sản phẩm đang triển khai, phải tra cú pháp của **đúng phiên bản**.

### 13.1. Các hệ quản trị phân tích dữ liệu

Một số hệ như BigQuery và Snowflake cũng có `MERGE` phục vụ đồng bộ bảng trong data warehouse. Chúng có thể hỗ trợ các nhánh `MATCHED`, `NOT MATCHED` và `NOT MATCHED BY SOURCE` với cú pháp/giới hạn riêng.

Tuy nhiên, dữ liệu warehouse thường được nạp theo lô, snapshot, partition và các tệp lớn. Khi dùng `MERGE` ở đó cần kiểm tra:

- **Phạm vi hàng nguồn** có phải một lô hay snapshot đầy đủ.
- **Khóa match** đã chuẩn hóa và nguồn có duy nhất theo khóa không.
- **Chi phí quét dữ liệu**, cách lọc partition và kích thước bảng đích.
- **Các hàng khớp nhiều lần** có gây lỗi hay kết quả không xác định theo quy tắc của hệ.
- **Khả năng rollback, lịch sử phiên bản và thông tin hàng bị ảnh hưởng**.

Không nên port một câu `MERGE` từ PostgreSQL sang data warehouse chỉ bằng cách đổi tên schema. Ngữ nghĩa nhập dữ liệu và các giới hạn vận hành cũng cần được đánh giá.

## 14. WHEN NOT MATCHED BY SOURCE: chỉ khi nguồn là snapshot hoàn chỉnh

Xét một bảng snapshot **giả định** chứa toàn bộ SKU hiện hành. Nếu trong snapshot không còn `H`, thì mục tiêu có thể là `H.status = 'INACTIVE'`.

Một mẫu SQL Server:

```sql
-- SQL Server; chỉ minh họa khi s là snapshot ĐẦY ĐỦ.
MERGE INTO dbo.inventory_demo AS t
USING dbo.full_stock_snapshot AS s
    ON t.sku = s.sku

WHEN MATCHED AND (
    t.quantity <> s.quantity
    OR t.status <> 'ACTIVE'
) THEN
    UPDATE SET quantity = s.quantity,
               status = 'ACTIVE'

WHEN NOT MATCHED BY TARGET THEN
    INSERT (sku, quantity, status)
    VALUES (s.sku, s.quantity, 'ACTIVE')

WHEN NOT MATCHED BY SOURCE
     AND t.status = 'ACTIVE' THEN
    UPDATE SET status = 'INACTIVE';
```

Ví dụ này **không thể chạy nguyên văn** trên bộ dữ liệu hiện tại vì bài không tạo bảng `full_stock_snapshot`. Nó minh họa **mẫu cấu trúc** và yêu cầu nguồn đầy đủ, không nhằm bổ sung một bảng mới vào phần thực hành.

### 14.1. Hạn chế phạm vi xóa mềm

Nếu snapshot chỉ đầy đủ cho `warehouse_id = 10`, bảng đích phải có khóa `warehouse_id` và nhánh đích-only chỉ được tác động **phạm vi kho 10**. Ví dụ điều kiện trên SQL Server có thể cần:

```sql
WHEN NOT MATCHED BY SOURCE
     AND t.warehouse_id = 10
     AND t.status = 'ACTIVE' THEN
    UPDATE SET status = 'INACTIVE'
```

Đồng thời `ON` phải ghép đúng `warehouse_id` và `sku` của các hàng cần xử lý. Không dùng một nguồn chỉ có kho 10 rồi đánh dấu inactive mọi SKU của các kho khác.

### 14.2. Không hiểu NOT MATCHED BY SOURCE là “xóa ngay”

Ngay cả khi snapshot đầy đủ, còn cần xét:

- Sản phẩm bị **ẩn tạm thời** do lỗi cấp dữ liệu?
- Dữ liệu nguồn vừa **đóng kỳ** hay còn đang nạp?
- Có chính sách **grace period** trước khi inactive/xóa?
- Hàng đích còn đơn hàng lịch sử hoặc khóa ngoại tham chiếu?
- Có quy tắc **khôi phục hoạt động** nếu sản phẩm xuất hiện lại?

Một lệnh `MERGE` mô tả thao tác kỹ thuật; nó **không tự quyết định chính sách lưu trữ đúng**.

## 15. MERGE và xóa cứng: khóa ngoại, trigger, audit

Nhánh:

```sql
WHEN MATCHED AND s.operation = 'REMOVE' THEN DELETE
```

có thể xóa một hàng đích. Nếu các bảng khác có khóa ngoại tham chiếu hàng đó:

- Ràng buộc `ON DELETE RESTRICT` hoặc `NO ACTION` có thể **ngăn xóa**.
- `ON DELETE CASCADE` có thể xóa **thêm hàng con**.
- `ON DELETE SET NULL` có thể sửa khóa ngoại của hàng con nếu cấu trúc cho phép.
- Trigger có thể ghi audit hoặc tạo side effect.

**Số hàng do MERGE báo cáo không nhất thiết bằng tổng mọi hàng bị thay đổi trên tất cả bảng liên quan.** Trong SQL Server, `OUTPUT $action` mô tả các hành động trên hàng đích của MERGE, không mặc định liệt kê mọi hàng bị thay đổi gián tiếp do khóa ngoại hoặc trigger.

### 15.1. Ghi lại nguồn gốc sự kiện

Nếu cần truy vết, một feed thực tế nên có thêm:

- `batch_id` hoặc `source_file_id`.
- `event_id` duy nhất để xử lý **sự kiện gửi lại**.
- `event_version` hoặc thứ tự nghiệp vụ của bản cập nhật.
- `received_at` và `effective_at` nếu hai thời điểm có ý nghĩa khác nhau.
- Hệ thống nguồn và trạng thái xử lý.

Đừng sử dụng riêng số hàng được MERGE để kết luận pipeline đã “xử lý đủ sự kiện”. Có thể có những hàng nguồn **không tạo hành động** do `SKIP` hoặc đã khớp giá trị, và cũng có thể có hàng nguồn bị cách ly vì sai khóa.

### 15.2. Lưu lịch sử thay vì cập nhật đè mọi lần

`MERGE` ở bài học đang xử lý mô hình **current state**, tức bảng đích chỉ lưu giá trị hiện tại. Trong kho dữ liệu cần lưu lịch sử thay đổi thuộc tính, mô hình **Slowly Changing Dimension Type 2 (SCD2)** thường yêu cầu:

1. Kết thúc hiệu lực phiên bản cũ.
2. Thêm một hàng phiên bản mới.
3. Giữ ngày hiệu lực, cờ hiện hành và khóa lịch sử.

Không thể xem câu `UPDATE t.quantity = s.quantity` đơn giản là đủ cho mọi yêu cầu lưu lịch sử. Một số DBMS có thể dùng MERGE kết hợp bước khác, nhưng phải thiết kế **mức chi tiết phiên bản và thứ tự hành động** rõ ràng.

## 16. Transaction, tính nguyên tử và cạnh tranh đồng thời

### 16.1. Một câu MERGE không đồng nghĩa với toàn bộ pipeline nguyên tử

Một câu lệnh `MERGE` được thực thi như một thao tác DML theo quy tắc của database. Nhưng một pipeline có thể gồm:

```text
1. Tải feed từ API
2. Ghi bảng staging
3. Kiểm tra trùng khóa
4. MERGE vào bảng hiện hành
5. Ghi audit
6. Gửi thông báo sang hệ thống khác
```

Không thể mặc định tất cả sáu bước được rollback chung chỉ vì bước 4 dùng `MERGE`. Cần thiết kế transaction, cơ chế retry, idempotency và xử lý side effect ngoài database.

### 16.2. Ràng buộc duy nhất là lớp bảo vệ bắt buộc

Hai tiến trình có thể cùng đọc và muốn chèn SKU `F`. Nếu bảng đích **không có khóa duy nhất**, chúng có thể tạo hai hàng `F` làm sai tồn kho. Nếu có `PRIMARY KEY (sku)`, database từ chối dữ liệu trùng, nhưng ứng dụng vẫn phải **xử lý lỗi xung đột/retry** theo khả năng của DBMS.

Không dựa vào việc `MERGE ... ON t.sku = s.sku` để thay thế `UNIQUE`/`PRIMARY KEY`. Điều kiện `ON` là mô tả truy vấn, không tự trở thành ràng buộc dữ liệu lâu dài.

### 16.3. Một snapshot thay đổi giữa lúc xem trước và lúc MERGE

Quy trình:

```text
SELECT xem trước -> chờ -> MERGE
```

có thể gặp dữ liệu thay đổi ở khoảng giữa. Chẳng hạn một tiến trình khác cập nhật `A.quantity` từ 5 thành 7 trước khi `MERGE` cập nhật lên 8. Nếu nghiệp vụ nói “feed hiện hành ghi đè mọi thay đổi cũ” thì có thể chấp nhận; nếu nói “chỉ ghi đè khi phiên bản khớp”, cần cột version/điều kiện cập nhật thích hợp.

Một ý tưởng là kiểm tra phiên bản nguồn mới hơn phiên bản đích trong nhánh `WHEN MATCHED AND ...`, ví dụ:

```sql
-- Minh họa điều kiện nghiệp vụ, cần có các cột version tương ứng.
WHEN MATCHED AND s.source_version > t.source_version THEN
    UPDATE SET
        quantity = s.quantity,
        source_version = s.source_version
```

Bảng mẫu không có `source_version`; đây là **mẫu thiết kế**, không phải đoạn có thể chạy ngay. Nó cho thấy `MERGE` thường cần **quy tắc chống ghi đè dữ liệu mới bằng feed cũ**, không chỉ cần khóa SKU.

### 16.4. Kiểm tra kết quả trước khi COMMIT

Trong PostgreSQL, ta có thể thử:

```sql
BEGIN;

SELECT COUNT(*) AS before_rows FROM inventory_demo;
-- 6

-- Chạy MERGE ở mục 4.

SELECT COUNT(*) AS after_rows FROM inventory_demo;
-- 7, theo dữ liệu mẫu

SELECT sku, quantity, status
FROM inventory_demo
ORDER BY sku;

ROLLBACK;
```

Không nên chỉ kiểm tra `COUNT(*) = 7`, vì một tập 7 hàng vẫn có thể chứa sai SKU hoặc sai số lượng. Hãy kiểm tra **khóa và trạng thái** thực tế; với SQL Server có thể dùng `OUTPUT $action`, với PostgreSQL các phiên bản hỗ trợ có thể dùng khả năng trả dữ liệu phù hợp hoặc truy vấn kiểm tra trong transaction.

PostgreSQL 15 không có cùng cú pháp `MERGE ... RETURNING` như một số bản mới hơn; đừng sao chép mẫu `DELETE ... RETURNING` sang `MERGE` mà chưa kiểm tra phiên bản. Nếu cần log chi tiết từng hành động trên phiên bản cũ, có thể cần thiết kế audit/trigger hoặc quy trình khác.

## 17. Hiệu năng và cách tổ chức nguồn để MERGE ổn định

MERGE là một thao tác so khớp và ghi dữ liệu; hiệu năng phụ thuộc số lượng hàng nguồn, chỉ mục đích, điều kiện `ON`, lượng cập nhật thực tế, khóa và cách tối ưu của DBMS.

### 17.1. Ưu tiên khóa đích có chỉ mục duy nhất

Trong ví dụ:

```sql
CREATE TABLE inventory_demo (
    sku TEXT PRIMARY KEY,
    ...
);
```

`PRIMARY KEY (sku)` tạo cơ sở để nhận diện duy nhất một SKU trong đích và thường có chỉ mục hỗ trợ tìm hàng. Nếu bảng lớn và khóa match nhiều cột, phải có cấu trúc khóa/unique index phù hợp.

### 17.2. Không cập nhật các hàng không thay đổi

Điều kiện:

```sql
t.quantity IS DISTINCT FROM s.quantity
OR t.status IS DISTINCT FROM 'ACTIVE'
```

giúp bỏ `UPDATE` cho B. Trên hệ có audit trigger, việc ghi lại giá trị cũ có thể vẫn bị tính là một lần cập nhật và phát sinh chi phí. Nhưng kiểm tra khác biệt cũng có chi phí tính toán; với hệ lớn cần đo thực tế.

### 17.3. Chuẩn hóa nguồn trước khi MERGE

Các bước nguồn thường có:

```text
Raw feed
   |
   v
Kiểm tra khóa/kiểu/trạng thái
   |
   v
Giải quyết bản ghi trùng và thứ tự sự kiện
   |
   v
Một hàng nguồn cho mỗi khóa MERGE
   |
   v
MERGE vào bảng đích
```

Đừng gộp mọi phép chuẩn hóa vào một câu MERGE quá phức tạp mà không có cách quan sát. Có thể dùng CTE hoặc staging đã kiểm tra để giữ nguồn rõ và tái lập.

### 17.4. Đếm nguồn và đếm hành động là hai việc khác

Feed có **6 dòng**, nhưng MERGE cơ bản chỉ tạo **4 thao tác**. Lý do:

- A update.
- B không đổi.
- C delete.
- D skip.
- F/G insert.

Đếm số hàng feed **không** thể dùng thay số hành động; ngược lại số hành động **không** chứng minh đã xem xét đủ mọi sự kiện nguồn. Pipeline nên ghi riêng:

| Chỉ số | Giá trị mẫu |
|---|---:|
| Số dòng feed | 6 |
| Số SKU nguồn phân biệt | 6 |
| Dự kiến UPDATE | 1 |
| Dự kiến DELETE | 1 |
| Dự kiến INSERT | 2 |
| Dự kiến bỏ qua vì không đổi/SKIP | 2 |
| Tổng hàng đích sau MERGE | 7 |

Với MERGE có thêm nhánh `NOT MATCHED BY SOURCE` của SQL Server, số thao tác có thể tăng vì **hành động trên hàng chỉ có ở đích không tương ứng dòng nguồn**.

## 18. Những lỗi thường gặp

### Lỗi 1 — Nghĩ MERGE đồng nghĩa với UPSERT đơn giản

`MERGE` có thể xử lý các nhánh `UPDATE`, `INSERT`, `DELETE` hoặc bỏ qua; `UPSERT` thường chỉ là **insert-or-update trên khóa**. Không mặc định MySQL `ON DUPLICATE KEY UPDATE` hoặc SQLite `ON CONFLICT` tương đương toàn bộ MERGE.

### Lỗi 2 — Đưa điều kiện trạng thái vào ON

`ON t.sku = s.sku AND t.status = 'ACTIVE'` có thể làm hàng `INACTIVE` cùng SKU bị coi là không khớp, khiến nhánh INSERT đụng khóa chính. Dùng `ON` để nhận diện bản ghi; đưa quy tắc xử lý vào `WHEN`.

### Lỗi 3 — Nguồn có nhiều hàng cùng khóa

Hai nguồn cùng SKU có thể làm một hàng đích bị sửa hai lần hoặc làm hai dòng cố chèn cùng khóa. Kiểm tra và chuẩn hóa **một bản ghi cho mỗi khóa match** trước MERGE, hoặc dùng thuật toán phù hợp với sự kiện cộng dồn.

### Lỗi 4 — Không xét thứ tự WHEN

Nhánh `WHEN MATCHED` không điều kiện đặt trước có thể chiếm hết các hàng đã khớp, khiến nhánh cụ thể `REMOVE` không còn cơ hội thực thi. Đặt các điều kiện cụ thể trước nhánh bao quát.

### Lỗi 5 — Dùng NOT MATCHED BY SOURCE với feed thay đổi

Một SKU không xuất hiện trong **feed hôm nay** không có nghĩa sản phẩm bị ngừng hoạt động. Chỉ dùng nhánh đích-only khi nguồn là snapshot đầy đủ, đúng phạm vi và đã qua kiểm tra chất lượng.

### Lỗi 6 — Không giới hạn phạm vi snapshot

Snapshot chỉ có dữ liệu kho 10 nhưng nhánh đích-only thao tác mọi kho có thể xóa/inactive hàng của kho khác. Cần khóa ghép và điều kiện phạm vi đúng.

### Lỗi 7 — Tin rằng khóa đích được bảo đảm duy nhất chỉ nhờ MERGE ON

`ON` không thay thế ràng buộc `UNIQUE`/`PRIMARY KEY`. Trong môi trường đồng thời vẫn phải xử lý xung đột khóa.

### Lỗi 8 — Xem mọi bản ghi nguồn là một thao tác thay đổi

`B` không đổi, `D` SKIP. Feed 6 hàng không có nghĩa MERGE phải báo 6 hàng thay đổi. Đếm theo **hành động thực tế**, không theo kích thước nguồn.

### Lỗi 9 — Gán giá trị cũ nhưng tưởng là không UPDATE

Một nhánh `UPDATE SET quantity = s.quantity` vẫn có thể thực hiện UPDATE khi giá trị bằng nhau. Nếu cần bỏ cập nhật không đổi, viết điều kiện khác biệt và hiểu logic `NULL`.

### Lỗi 10 — Sao chép WHEN MATCHED THEN DELETE của PostgreSQL sang Oracle

Trong mẫu Oracle truyền thống, thao tác xóa dùng `DELETE WHERE` gắn với `WHEN MATCHED THEN UPDATE`. Hai cú pháp không thể hoán đổi nguyên văn.

### Lỗi 11 — Quên dấu chấm phẩy kết thúc MERGE SQL Server

SQL Server yêu cầu `MERGE` kết thúc bằng `;`. Đừng dựa vào cách công cụ SQL tự chia câu lệnh.

### Lỗi 12 — Thêm DO NOTHING của PostgreSQL vào MERGE SQL Server

`DO NOTHING` được PostgreSQL hỗ trợ như hành động trong MERGE; SQL Server thường biểu diễn bỏ qua bằng **không có nhánh hành động khớp**. Hai cách không chung cú pháp.

### Lỗi 13 — Dùng DELETE cứng khi còn hàng tham chiếu

Khóa ngoại có thể từ chối xóa hoặc cascade sang dữ liệu khác. Kiểm tra quan hệ và chính sách trước khi dùng nhánh `DELETE`; nhiều trường hợp chỉ nên đặt `INACTIVE`.

### Lỗi 14 — Tin MERGE tự giải quyết mọi xung đột đồng thời

Hai tiến trình đồng thời vẫn có thể gặp lỗi khóa duy nhất, khóa chờ hoặc thay đổi phiên bản. Sử dụng transaction, ràng buộc duy nhất, chiến lược khóa/phiên bản và retry thích hợp.

### Lỗi 15 — Dùng ROW_NUMBER không có khóa phân định để chọn feed mới nhất

Nếu hai sự kiện có cùng `received_at`, `ROW_NUMBER ORDER BY received_at DESC` không xác định sự kiện nào được giữ. Thêm khóa phụ, tốt hơn nữa dùng **event_version** đáng tin cậy của nguồn.

### Lỗi 16 — Nhầm dữ liệu trạng thái với sự kiện tăng/giảm

`quantity = 8` có thể nghĩa “còn 8” hoặc “tăng 8”. `SET quantity = s.quantity` và `SET quantity = t.quantity + s.quantity` rất khác nhau; chọn sai sẽ làm lệch tồn kho.

### Lỗi 17 — Chỉ xem tổng số hàng sau MERGE

Số hàng đích từ 6 thành 7 không bảo đảm A được cập nhật đúng, C bị xóa đúng hay H được giữ đúng. Cần kiểm tra các SKU và số lượng, đồng thời lưu dấu vết sự kiện.

### Lỗi 18 — Không phân biệt phiên bản DBMS

PostgreSQL chỉ có `MERGE` từ 15; các tính năng mở rộng và trả kết quả có thể khác theo phiên bản. Oracle, SQL Server, MySQL, SQLite và các hệ warehouse cũng không có cùng ngữ nghĩa. Chọn ví dụ theo **hệ quản trị đang chạy**, không theo tên từ khóa chung.

## 19. Bài tập thực hành

Sử dụng dữ liệu `inventory_demo` và `stock_feed_demo` ở mục 2. Các câu hỏi độc lập và giả định dữ liệu đang ở trạng thái ban đầu. Khi chạy DML trong PostgreSQL, dùng `BEGIN ... ROLLBACK` để thử nhiều bài mà không phải nạp lại.

### Bài 1 — Nhận diện các nhánh trên từng SKU

Hãy dự đoán hành động của MERGE PostgreSQL ở mục 4 đối với từng hàng `A, B, C, D, F, G`.

**Đáp án:**

| SKU | Nhánh |
|---|---|
| A | MATCHED + UPDATE |
| B | MATCHED + DO NOTHING vì không đổi |
| C | MATCHED + DELETE |
| D | MATCHED + DO NOTHING vì SKIP |
| F | NOT MATCHED + INSERT |
| G | NOT MATCHED + INSERT |

### Bài 2 — Kết quả bảng đích sau MERGE

Cho biết số hàng đích và nội dung các SKU nếu chạy MERGE nhưng **chưa rollback**.

**Đáp án:** 7 SKU: **A=8 ACTIVE, B=12 ACTIVE, D=9 ACTIVE, E=0 INACTIVE, F=6 ACTIVE, G=2 ACTIVE, H=3 ACTIVE**. SKU C không còn.

### Bài 3 — Đếm số hành động

Trong MERGE mục 4, có bao nhiêu UPDATE, DELETE, INSERT và hàng bỏ qua?

**Đáp án:** **1 UPDATE, 1 DELETE, 2 INSERT**; B/D là hai hàng nguồn bỏ qua. Tổng **4 thao tác hàng đích**. E/H không thuộc tập nguồn nên không có hành động.

### Bài 4 — Vì sao ON không nên chứa status?

Giả sử một nguồn mới gửi `('E', 'UPSERT', 4)` cho hàng `E` đang inactive. Nếu viết:

```sql
ON t.sku = s.sku AND t.status = 'ACTIVE'
```

điều gì có thể xảy ra?

**Đáp án:** E bị coi là không khớp dù đã có hàng đích. Nhánh INSERT có thể cố chèn E và vi phạm `PRIMARY KEY`. Cần `ON t.sku = s.sku`, rồi nhánh UPDATE chuyển E sang ACTIVE và thay quantity.

### Bài 5 — Phát hiện trùng SKU trong feed

Viết truy vấn đếm số hàng mỗi SKU, chỉ hiện SKU có từ hai hàng nguồn trở lên.

```sql
SELECT sku, COUNT(*) AS copies
FROM stock_feed_demo
GROUP BY sku
HAVING COUNT(*) > 1;
```

**Đáp án:** dữ liệu ban đầu trả **0 hàng**. Nếu bổ sung thêm một sự kiện của A, truy vấn trả A với `copies = 2`.

### Bài 6 — Giải quyết sự kiện trùng theo thứ tự xác định

Giả sử nguồn có hai sự kiện A:

```text
feed_id 1, received_at 08:00, quantity 8
feed_id 7, received_at 08:06, quantity 9
```

Viết `ROW_NUMBER() OVER (PARTITION BY sku ORDER BY received_at DESC, feed_id DESC)` và giữ `rn = 1`.

**Đáp án:** chọn `feed_id = 7`, quantity = 9 cho A **nếu** quy tắc nghiệp vụ nói thời điểm nhận mới nhất là phiên bản đúng. Không tự dùng cách này cho các sự kiện tăng tồn kho cần cộng dồn.

### Bài 7 — Xóa khi nhận REMOVE

Trong PostgreSQL 15+, viết nhánh MERGE phù hợp để xóa C:

```sql
WHEN MATCHED AND s.operation = 'REMOVE' THEN
    DELETE
```

**Đáp án:** C bị xóa khỏi `inventory_demo`; nếu một SKU REMOVE không có ở đích và không có nhánh INSERT cho REMOVE, không có hàng mới được tạo.

### Bài 8 — Thay DELETE bằng xóa mềm

Chính sách mới không cho phép xóa hẳn SKU mà chỉ đánh dấu inactive. Hãy đổi nhánh REMOVE:

```sql
WHEN MATCHED AND s.operation = 'REMOVE' THEN
    UPDATE SET status = 'INACTIVE'
```

**Đáp án:** C vẫn tồn tại với `quantity = 4` và `status = 'INACTIVE'` nếu chỉ đổi trạng thái. Tổng số hàng cuối sẽ là **8** thay vì 7: không xóa C, chèn F/G. Nếu chính sách còn yêu cầu đặt quantity = 0, phải bổ sung điều kiện `SET quantity = 0` riêng.

### Bài 9 — So sánh incremental và full snapshot

Tại sao không thể dùng `WHEN NOT MATCHED BY SOURCE THEN DELETE` cho bảng `stock_feed_demo` của bài?

**Đáp án:** vì đó chỉ là **feed sự kiện**, không bao gồm toàn bộ SKU hiện có. E/H không xuất hiện không có nghĩa chúng bị xóa khỏi nguồn; nhánh như vậy có thể xóa nhầm E/H.

### Bài 10 — Nhánh NOT MATCHED BY SOURCE trên SQL Server

Giả sử một snapshot đầy đủ cho phép đánh dấu inactive các SKU không có ở nguồn:

```sql
WHEN NOT MATCHED BY SOURCE
     AND t.status = 'ACTIVE' THEN
    UPDATE SET status = 'INACTIVE'
```

Trong dữ liệu ban đầu, SKU nào được thêm thao tác và tổng số thay đổi là bao nhiêu nếu vẫn giữ các nhánh khác?

**Đáp án:** **H** đổi ACTIVE → INACTIVE, **E** đã INACTIVE nên không đổi. Tổng hành động đích là **5**: UPDATE A/H, DELETE C, INSERT F/G.

### Bài 11 — Oracle DELETE WHERE khác PostgreSQL thế nào?

Vì sao không thể viết nguyên `WHEN MATCHED AND s.operation = 'REMOVE' THEN DELETE` của PostgreSQL trong MERGE Oracle truyền thống?

**Đáp án:** Oracle truyền thống gắn `DELETE WHERE` với **nhánh `WHEN MATCHED THEN UPDATE`**. Hàng phải được xử lý ở nhánh UPDATE rồi mới được xét xóa theo điều kiện đó. Không có cùng cấu trúc nhánh DELETE độc lập của PostgreSQL/SQL Server.

### Bài 12 — PostgreSQL ON CONFLICT làm được gì?

Chạy ý tưởng:

```sql
INSERT INTO inventory_demo (sku, quantity, status)
VALUES ('A', 8, 'ACTIVE')
ON CONFLICT (sku) DO UPDATE
SET quantity = EXCLUDED.quantity,
    status = EXCLUDED.status;
```

**Đáp án:** cập nhật A nếu đã tồn tại, hoặc chèn A nếu chưa có. Câu lệnh **không tự xử lý yêu cầu REMOVE của C**, và không có nhánh đích-only như một số MERGE.

### Bài 13 — MySQL ON DUPLICATE KEY UPDATE

Hãy viết:

```sql
INSERT INTO inventory_demo (sku, quantity, status)
VALUES ('F', 6, 'ACTIVE')
ON DUPLICATE KEY UPDATE
    quantity = 6,
    status = 'ACTIVE';
```

**Đáp án:** nếu F chưa có, chèn; nếu xung đột khóa duy nhất, cập nhật. Không suy ra khóa khớp từ một mệnh đề `ON` tùy ý và không coi đây là một MERGE có DELETE.

### Bài 14 — SQLite ON CONFLICT

Viết lệnh SQLite chèn/cập nhật G:

```sql
INSERT INTO inventory_demo (sku, quantity, status)
VALUES ('G', 2, 'ACTIVE')
ON CONFLICT(sku) DO UPDATE SET
    quantity = excluded.quantity,
    status = excluded.status;
```

**Đáp án:** SQLite dùng `excluded` để lấy giá trị hàng đang thử chèn, không dùng nguyên cú pháp `USING ... WHEN MATCHED` của MERGE.

### Bài 15 — Thiết kế khóa ghép cho tồn kho nhiều kho

Bảng `warehouse_stock` có `(warehouse_id, sku, quantity)`, trong đó cùng một SKU có thể tồn tại ở nhiều kho. Điều kiện MERGE nên là gì?

**Đáp án:**

```sql
ON t.warehouse_id = s.warehouse_id
AND t.sku = s.sku
```

và bảng đích nên có `PRIMARY KEY (warehouse_id, sku)` hoặc ràng buộc duy nhất tương ứng. Không khớp chỉ bằng `sku` vì có thể sửa nhầm nhiều kho.

### Bài 16 — Chống cập nhật không đổi

Sản phẩm B đã có quantity 12, status ACTIVE; nguồn gửi đúng 12, UPSERT. Có nên cập nhật B?

**Đáp án:** trong quy tắc bài học, **không**. Nhánh `WHEN MATCHED` chỉ UPDATE nếu quantity khác hoặc status khác ACTIVE. Điều này tránh tác động ghi và trigger/audit không cần thiết.

### Bài 17 — Race condition khi chèn khóa chưa có

Hai phiên cùng nhập `F` khi bảng đích chưa có F. Chỉ dùng `MERGE ON t.sku = s.sku` có đủ bảo đảm không tạo trùng F?

**Đáp án:** không nên dựa vào MERGE một mình. Cần `PRIMARY KEY`/`UNIQUE` trên SKU và xử lý cạnh tranh bằng transaction, khóa/phiên bản hoặc retry phù hợp. PostgreSQL `ON CONFLICT` là lựa chọn chuyên cho insert-or-update theo khóa duy nhất trong nhiều tình huống.

### Bài 18 — Một nguồn có 6 hàng, MERGE chỉ thay đổi 4 hàng

Một hệ thống báo “MERGE chỉ ảnh hưởng 4 hàng trên 6 sự kiện nguồn”. Đây có nhất thiết là lỗi không?

**Đáp án:** không. Trong ví dụ A UPDATE, C DELETE, F/G INSERT tạo **4 hành động**, còn B không thay đổi và D SKIP. Cần đối chiếu **số lượng sự kiện đã xem xét**, **số hành động** và **số lỗi/cách ly** như các chỉ số khác nhau.

### Bài 19 — Phân biệt snapshot thiếu và hàng cần inactive

Snapshot của kho 10 bị lỗi truyền tải, chỉ còn 70% SKU. Có nên chạy `NOT MATCHED BY SOURCE THEN UPDATE status='INACTIVE'` ngay?

**Đáp án:** không. Phải xác minh snapshot đã đầy đủ và được chốt, giới hạn phạm vi kho 10, kiểm tra số hàng dự kiến ảnh hưởng và có cơ chế khôi phục. Nếu chạy ngay, nhiều SKU còn hoạt động có thể bị vô hiệu hóa sai.

### Bài 20 — Chọn MERGE hay UPSERT đơn giản?

Hai yêu cầu:

1. Cập nhật giá bán nếu sản phẩm tồn tại, chèn nếu chưa có; không có xóa.
2. Đồng bộ feed có `UPSERT`, `REMOVE`, `SKIP` và yêu cầu phân loại chính xác hành động.

**Đáp án định hướng:** yêu cầu 1 có thể dùng PostgreSQL `INSERT ... ON CONFLICT`, MySQL `ON DUPLICATE KEY UPDATE` hoặc SQLite `ON CONFLICT DO UPDATE` khi khóa và phiên bản phù hợp. Yêu cầu 2 thường phù hợp hơn với `MERGE` trên DBMS hỗ trợ các nhánh cần thiết, hoặc với nhiều câu DML trong một transaction được thiết kế rõ ràng.

## 20. Bảng ghi nhớ nhanh

| Câu hỏi | Điều cần nhớ |
|---|---|
| `MERGE` làm gì? | So khớp nguồn–đích theo `ON` rồi chọn một nhánh hành động đủ điều kiện |
| `MATCHED` là gì? | Hàng nguồn có hàng đích tương ứng |
| `NOT MATCHED`/`BY TARGET` là gì? | Hàng nguồn không có hàng đích; thường dùng `INSERT` |
| `NOT MATCHED BY SOURCE` là gì? | Hàng đích không có trong nguồn; **chỉ an toàn với snapshot đầy đủ đúng phạm vi** |
| `ON` nên chứa gì? | Khóa nghiệp vụ nhận diện cùng đối tượng, không trộn điều kiện trạng thái làm đổi danh tính |
| Vì sao nguồn cần duy nhất theo khóa? | Nhiều hàng nguồn khớp một đích có thể gây lỗi hoặc thao tác không xác định |
| Nhánh cụ thể đặt ở đâu? | Trước nhánh bắt tất cả |
| Bỏ qua trong PostgreSQL MERGE? | `DO NOTHING` |
| Bỏ qua trong SQL Server MERGE? | Thường không có nhánh hành động khớp |
| Xóa trong MERGE Oracle truyền thống? | `DELETE WHERE` gắn với `UPDATE` |
| SQL Server trả hành động thế nào? | `OUTPUT $action` cùng `inserted`/`deleted` |
| PostgreSQL có MERGE từ khi nào? | PostgreSQL 15 |
| MySQL có MERGE tiêu chuẩn không? | Không phải mẫu thông dụng; dùng `ON DUPLICATE KEY UPDATE` cho upsert |
| SQLite dùng gì cho upsert? | `INSERT ... ON CONFLICT(...) DO UPDATE` |
| PostgreSQL `ON CONFLICT` khác MERGE? | Upsert dựa trên khóa duy nhất, không thay toàn bộ nhánh MERGE |
| Một feed 6 dòng có thể chỉ thay đổi 4 hàng? | Có: vì một số hàng giống dữ liệu cũ hoặc SKIP |
| Dùng MERGE có tự an toàn với concurrency? | Không; vẫn cần ràng buộc khóa, transaction và chiến lược xử lý cạnh tranh |
| Có nên DELETE khi nguồn thiếu hàng? | Không, trừ khi thiếu hàng trong snapshot đã xác nhận mang nghĩa nghiệp vụ cần xóa |

## Kết luận

`MERGE` là công cụ tổ chức **nhiều nhánh xử lý dữ liệu dựa trên quan hệ giữa nguồn và đích**. Để viết đúng, trước tiên cần xác định:

1. **Khóa nào nhận diện cùng một đối tượng?** Điều kiện `ON` phải khớp đúng mức chi tiết và thường đi kèm ràng buộc duy nhất ở bảng đích.
2. **Nguồn có loại dữ liệu nào?** Feed incremental hay snapshot đầy đủ; một SKU là trạng thái hiện tại hay một sự kiện tăng/giảm?
3. **Hàng thuộc nhánh nào?** `MATCHED` để UPDATE/DELETE/bỏ qua; `NOT MATCHED` để INSERT; `NOT MATCHED BY SOURCE` chỉ khi thật sự cần xử lý những hàng chỉ có ở đích.
4. **Nguồn đã đủ sạch chưa?** Kiểm tra khóa thiếu, trùng khóa, thứ tự phiên bản, sự kiện gửi lại và phạm vi snapshot trước khi MERGE.
5. **DBMS cho phép cú pháp nào?** PostgreSQL 15+ có `MERGE`; SQL Server có `OUTPUT $action` và nhánh BY SOURCE; Oracle truyền thống có `DELETE WHERE` đi cùng UPDATE; MySQL và SQLite dùng các dạng UPSERT riêng nếu chỉ cần chèn/cập nhật.
6. **Làm sao biết kết quả đúng?** So danh tính khóa và trạng thái, số hàng được chèn/sửa/xóa/bỏ qua, tác động khóa ngoại, transaction, audit và khả năng cạnh tranh.

Điều quan trọng nhất không phải dùng được từ khóa `MERGE`, mà là **chọn đúng hành động cho từng tình huống và không suy diễn thêm hành động từ những dữ liệu nguồn chưa đầy đủ**. Khi phân biệt rõ MATCHED, NOT MATCHED BY TARGET, NOT MATCHED BY SOURCE và các giới hạn theo phương ngữ, bạn có thể xây dựng quy trình đồng bộ SQL rõ ràng, dễ kiểm chứng và ít rủi ro mất dữ liệu hơn.
