# MERGE và xử lý dữ liệu theo điều kiện khớp trong PostgreSQL

Trong các hệ thống có nhập dữ liệu từ file, đồng bộ danh mục, cập nhật trạng thái đơn hàng hoặc xử lý dữ liệu từ dịch vụ khác, một batch đầu vào có thể chứa đồng thời những tình huống:

- Hàng đã tồn tại trong database và cần **cập nhật**.
- Hàng chưa tồn tại và cần **thêm mới**.
- Hàng đã tồn tại nhưng không có thay đổi mới, nên cần **bỏ qua**.
- Hàng đã tồn tại nhưng nguồn yêu cầu **xóa** hoặc **vô hiệu hóa**.
- Trong một snapshot đầy đủ, một hàng ở bảng đích không còn xuất hiện trong nguồn.

`MERGE` là câu lệnh SQL hỗ trợ thực hiện những hành động có điều kiện đó từ một nguồn dữ liệu và một điều kiện khớp. Nó đặc biệt hữu ích khi một quy trình cần đồng bộ nhiều loại thay đổi trong một statement thay vì viết nhiều lệnh độc lập.

Ví dụ khái niệm:

~~~sql
MERGE INTO products AS t
USING incoming_products AS s
ON t.sku = s.sku
WHEN MATCHED AND s.version > t.version THEN
    UPDATE SET
        product_name = s.product_name,
        price = s.price,
        version = s.version
WHEN NOT MATCHED THEN
    INSERT (sku, product_name, price, version)
    VALUES (s.sku, s.product_name, s.price, s.version);
~~~

Trong bài học thuộc chương **Thay đổi dữ liệu** của module **Database Engine Relational PostgreSQL**, chúng ta sẽ tìm hiểu cách nhận diện hàng khớp, chọn hành động, kiểm soát source duplicates, xử lý transaction và concurrency, so sánh với UPSERT, cùng những điểm khác biệt giữa các phiên bản PostgreSQL.

Một điều quan trọng cần giữ xuyên suốt: **`MERGE` không thay thế việc thiết kế khóa, constraint, quyền truy cập và chính sách dữ liệu**. Một câu MERGE đúng cú pháp nhưng dùng nguồn sai hoặc điều kiện `ON` sai vẫn có thể gây mất dữ liệu.

## 1. Phiên bản PostgreSQL nào hỗ trợ MERGE?

`MERGE` xuất hiện từ **PostgreSQL 15**. Các phiên bản tiếp theo bổ sung tính năng.

| Tính năng | PostgreSQL 15–16 | PostgreSQL 17 | PostgreSQL 18 |
|---|---|---|---|
| `MERGE INTO ... USING ... ON ...` | Có | Có | Có |
| `WHEN MATCHED THEN UPDATE/DELETE/DO NOTHING` | Có | Có | Có |
| `WHEN NOT MATCHED THEN INSERT/DO NOTHING` | Có | Có | Có |
| `WHEN NOT MATCHED BY SOURCE` | Chưa có | Có | Có |
| `WHEN NOT MATCHED BY TARGET`, viết tường minh | Chưa có | Có | Có |
| `MERGE ... RETURNING` | Chưa có | Có | Có |
| `merge_action()` trong `RETURNING` | Chưa có | Có | Có |
| Tham chiếu `OLD`/`NEW` trong `MERGE RETURNING` theo cú pháp mở rộng | Chưa có | Chưa hỗ trợ như PG18 | Có |

Kiểm tra phiên bản của **server**:

~~~sql
SHOW server_version;

SELECT current_setting('server_version_num')::INTEGER
    AS server_version_num;
~~~

Không suy phiên bản server từ bản `psql`/pgAdmin hoặc JDBC driver đang cài ở máy người dùng.

**Quy ước của bài:**

- Các ví dụ cơ bản dùng cú pháp từ PostgreSQL 15 trở lên.
- Ví dụ ghi rõ **PostgreSQL 17+** mới sử dụng `BY SOURCE`, `BY TARGET` hoặc `MERGE RETURNING`.
- Ví dụ ghi rõ **PostgreSQL 18+** mới sử dụng `OLD` và `NEW` trong `MERGE RETURNING`.

Nếu hệ thống dùng phiên bản cũ hơn, cần chọn cách viết tương thích và kiểm tra tài liệu chính thức của major version tương ứng.

## 2. MERGE gồm những thành phần nào?

Cấu trúc cơ bản:

~~~sql
MERGE INTO target_table AS t
USING source_table AS s
ON matching_condition
WHEN MATCHED AND condition_1 THEN
    UPDATE SET column_a = expression
WHEN MATCHED AND condition_2 THEN
    DELETE
WHEN MATCHED THEN
    DO NOTHING
WHEN NOT MATCHED AND condition_3 THEN
    INSERT (column_a, column_b)
    VALUES (s.value_a, s.value_b);
~~~

Đây chỉ là khung cú pháp, chưa phải câu lệnh chạy trực tiếp vì các tên bảng/cột là placeholder.

| Thành phần | Ý nghĩa |
|---|---|
| `MERGE INTO` | Xác định bảng đích sẽ nhận thay đổi |
| `USING` | Cung cấp các hàng nguồn |
| `ON` | Xác định hàng nguồn có khớp hàng đích hay không |
| `WHEN MATCHED` | Nhánh xử lý khi tìm được hàng đích phù hợp |
| `WHEN NOT MATCHED` | Nhánh xử lý khi hàng nguồn không có hàng đích phù hợp |
| `WHEN NOT MATCHED BY SOURCE` | PG17+: nhánh xử lý hàng đích vắng mặt trong nguồn |
| `AND condition` | Điều kiện bổ sung để chọn hành động trong loại khớp tương ứng |
| `UPDATE SET` | Cập nhật hàng đích |
| `INSERT ... VALUES` | Thêm hàng đích mới từ nguồn |
| `DELETE` | Xóa hàng đích |
| `DO NOTHING` | Không thay đổi ứng viên đó |

Có thể hình dung:

~~~text
                Source rows
                     |
                     v
             So khớp với target
                     |
          +----------+----------+
          |                     |
        MATCHED            NOT MATCHED
          |                (source-only)
          v                     |
    Xét WHEN MATCHED            v
     UPDATE/DELETE/         Xét WHEN NOT MATCHED
       DO NOTHING               INSERT/DO NOTHING

PG17+: target-only có thêm nhánh WHEN NOT MATCHED BY SOURCE
~~~

### 2.1. Một ứng viên không chạy nhiều nhánh WHEN

PostgreSQL xét các nhánh `WHEN` theo thứ tự. **Nhánh đầu tiên phù hợp** được thực hiện. Một candidate change row không phải quy trình gồm nhiều bước `WHEN` tuần tự.

Ví dụ:

~~~sql
WHEN MATCHED AND s.stock = 0 THEN
    UPDATE SET is_active = FALSE
WHEN MATCHED THEN
    UPDATE SET stock = s.stock
~~~

Nếu `s.stock = 0`, nhánh đầu chạy và nhánh thứ hai **không chạy tiếp**.

### 2.2. Không có nhánh phù hợp thì không thay đổi

Nếu matched row không thỏa bất cứ `WHEN MATCHED AND ...` nào, PostgreSQL có thể đơn giản bỏ qua hàng đó. Không bắt buộc luôn có một nhánh `DO NOTHING` tường minh.

## 3. Chuẩn bị schema và dữ liệu mẫu

Chúng ta dùng một bảng danh mục sản phẩm với khóa `sku` và phiên bản dữ liệu đến từ hệ thống nguồn. Dữ liệu dưới đây là giả lập.

**Chỉ chạy trong database thực hành riêng.** Nếu schema đã tồn tại, nên chọn database lab mới thay vì xóa các đối tượng đang được ứng dụng sử dụng.

~~~sql
CREATE SCHEMA merge_lab;

CREATE TABLE merge_lab.product (
    sku TEXT PRIMARY KEY,
    product_name TEXT NOT NULL,
    price NUMERIC(12, 2) NOT NULL CHECK (price >= 0),
    stock INTEGER NOT NULL CHECK (stock >= 0),
    source_version BIGINT NOT NULL CHECK (source_version >= 1),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT statement_timestamp()
);

INSERT INTO merge_lab.product
    (sku, product_name, price, stock, source_version, is_active)
VALUES
    ('A100', 'Sổ tay', 30000.00, 10, 1, TRUE),
    ('B200', 'Bút mực', 15000.00, 40, 3, TRUE),
    ('C300', 'Bìa hồ sơ', 25000.00, 20, 2, TRUE),
    ('D400', 'Nhãn dán', 12000.00, 8, 1, TRUE);
~~~

Trạng thái ban đầu:

| SKU | Tên | Giá | Tồn kho | Version |
|---|---|---:|---:|---:|
| A100 | Sổ tay | 30000.00 | 10 | 1 |
| B200 | Bút mực | 15000.00 | 40 | 3 |
| C300 | Bìa hồ sơ | 25000.00 | 20 | 2 |
| D400 | Nhãn dán | 12000.00 | 8 | 1 |

Các constraint giúp giữ bất biến:

- `PRIMARY KEY(sku)` bảo đảm mỗi SKU có nhiều nhất một hàng.
- Giá và số lượng tồn không âm.
- Version là số nguyên dương.
- `is_active` dùng cho vô hiệu hóa logic, không tương đương hard delete.
- `updated_at` có default lúc INSERT; nó **không tự cập nhật** khi UPDATE trừ khi lệnh SQL hoặc trigger đặt lại.

## 4. Ví dụ MERGE đầu tiên: cập nhật hoặc thêm mới

Giả sử nguồn gửi:

| SKU | Giá nguồn | Tồn nguồn | Version nguồn |
|---|---:|---:|---:|
| A100 | 35000.00 | 12 | 2 |
| B200 | 16000.00 | 38 | 3 |
| E500 | 45000.00 | 5 | 1 |

Quy tắc: bản ghi matched chỉ được cập nhật khi version nguồn **mới hơn**, bản ghi chưa tồn tại thì insert.

~~~sql
MERGE INTO merge_lab.product AS t
USING (
    VALUES
        ('A100'::TEXT, 'Sổ tay mới'::TEXT,
         35000.00::NUMERIC, 12::INTEGER, 2::BIGINT),
        ('B200', 'Bút mực', 16000.00::NUMERIC,
         38, 3::BIGINT),
        ('E500', 'Hộp bút', 45000.00::NUMERIC,
         5, 1::BIGINT)
) AS s(sku, product_name, price, stock, source_version)
ON t.sku = s.sku
WHEN MATCHED AND s.source_version > t.source_version THEN
    UPDATE SET
        product_name = s.product_name,
        price = s.price,
        stock = s.stock,
        source_version = s.source_version,
        is_active = TRUE,
        updated_at = statement_timestamp()
WHEN NOT MATCHED THEN
    INSERT (
        sku, product_name, price,
        stock, source_version, is_active
    )
    VALUES (
        s.sku, s.product_name, s.price,
        s.stock, s.source_version, TRUE
    );
~~~

Kết quả logic khi chạy từ dữ liệu ban đầu:

- A100 đã có, source version 2 > target version 1 → **UPDATE**.
- B200 đã có, source version 3 = target version 3 → **không thay đổi**.
- E500 chưa có → **INSERT**.
- C300 và D400 không có trong source → **giữ nguyên** vì câu lệnh chưa có nhánh xử lý target-only.

~~~sql
SELECT
    sku, product_name, price, stock, source_version, is_active
FROM merge_lab.product
ORDER BY sku;
~~~

Kỳ vọng:

| SKU | Tên | Giá | Stock | Version |
|---|---|---:|---:|---:|
| A100 | Sổ tay mới | 35000.00 | 12 | 2 |
| B200 | Bút mực | 15000.00 | 40 | 3 |
| C300 | Bìa hồ sơ | 25000.00 | 20 | 2 |
| D400 | Nhãn dán | 12000.00 | 8 | 1 |
| E500 | Hộp bút | 45000.00 | 5 | 1 |

**Lưu ý B200:** dù source có giá/stock khác, version không lớn hơn nên giữ target. Quy tắc này chỉ đúng nếu upstream bảo đảm version phản ánh thứ tự thông tin. Nếu “cùng version nhưng nội dung khác” là lỗi upstream, cần đối soát chứ không âm thầm bỏ qua vĩnh viễn.

### 4.1. Vì sao dùng cast trong VALUES?

Dùng `::TEXT`, `::NUMERIC`, `::INTEGER` và `::BIGINT` giúp xác định rõ các kiểu cột trong nguồn. Khi dữ liệu có `NULL` hoặc trộn kiểu, suy luận kiểu tự động có thể gây kết quả không mong muốn.

Với source đã nằm trong bảng staging có schema rõ, thường không cần cast từng literal.

## 5. Điều kiện ON xác định danh tính khớp

Trong ví dụ:

~~~sql
ON t.sku = s.sku
~~~

nghĩa là source và target đại diện cho **cùng một sản phẩm** nếu SKU bằng nhau.

Một lỗi nguy hiểm:

~~~sql
-- Không nên:
-- ON t.sku = s.sku AND t.is_active = TRUE
~~~

Giả sử SKU A100 đã tồn tại nhưng `is_active = FALSE`. Điều kiện trên không match target, nên source A100 bị xem là NOT MATCHED. Nhánh INSERT có thể cố tạo SKU A100 thứ hai và gây unique violation.

Nếu mục tiêu là kích hoạt lại sản phẩm không hoạt động, cần đưa trạng thái vào `WHEN`:

~~~sql
MERGE INTO merge_lab.product AS t
USING (
    VALUES
        ('A100'::TEXT, 'Sổ tay tái bán'::TEXT)
) AS s(sku, product_name)
ON t.sku = s.sku
WHEN MATCHED AND NOT t.is_active THEN
    UPDATE SET
        is_active = TRUE,
        product_name = s.product_name,
        updated_at = statement_timestamp()
WHEN NOT MATCHED THEN
    INSERT (
        sku, product_name, price, stock, source_version
    )
    VALUES (
        s.sku, s.product_name, 0, 0, 1
    );
~~~

**Quy tắc:** `ON` xác định cùng đối tượng, `WHEN ... AND` xác định hành động theo trạng thái và version.

### 5.1. Tại sao không lọc target bằng ON?

Điều kiện chỉ liên quan trạng thái target có thể thay đổi **loại ứng viên** (matched hay not matched). Điều này đặc biệt nguy hiểm nếu nhánh NOT MATCHED có INSERT hoặc nhánh PG17+ BY SOURCE có DELETE.

Nếu muốn chọn source theo batch hoặc status, lọc nguồn ở `USING (SELECT ... WHERE ...)`. Nếu muốn quyết định hành động theo trạng thái target, đặt trong `WHEN` phù hợp.

## 6. Nhánh WHEN được xét theo thứ tự

Ví dụ một batch gửi yêu cầu giữ nguyên, cập nhật hoặc vô hiệu hóa:

~~~sql
MERGE INTO merge_lab.product AS t
USING (
    VALUES
        ('A100'::TEXT, 0::INTEGER, 'DISABLE'::TEXT),
        ('B200'::TEXT, 32::INTEGER, 'SET'::TEXT),
        ('C300'::TEXT, 99::INTEGER, 'IGNORE'::TEXT)
) AS s(sku, new_stock, operation)
ON t.sku = s.sku
WHEN MATCHED AND s.operation = 'IGNORE' THEN
    DO NOTHING
WHEN MATCHED AND s.operation = 'DISABLE' THEN
    UPDATE SET
        stock = 0,
        is_active = FALSE,
        updated_at = statement_timestamp()
WHEN MATCHED AND s.operation = 'SET' THEN
    UPDATE SET
        stock = s.new_stock,
        updated_at = statement_timestamp();
~~~

Một candidate chỉ chọn **nhánh đầu tiên có điều kiện đúng**.

Không viết:

~~~sql
-- Sai logic/có thể bị từ chối vì nhánh sau không thể tới:
-- WHEN MATCHED THEN UPDATE SET stock = s.new_stock
-- WHEN MATCHED AND s.operation = 'DISABLE' THEN DELETE
~~~

Nhánh MATCHED không điều kiện đã bắt tất cả các hàng matched, nên nhánh MATCHED sau không thể được thực hiện. Hãy đặt nhánh **cụ thể** trước nhánh **tổng quát**.

### 6.1. DO NOTHING có cần thiết không?

Không bắt buộc. Nếu hàng matched không thỏa nhánh nào thì nó không bị thay đổi. Tuy nhiên `DO NOTHING` hữu ích để thể hiện chủ đích bỏ qua một loại hành động trước những nhánh khác.

`DO NOTHING` trong MERGE không đồng nghĩa cơ chế `ON CONFLICT DO NOTHING` của INSERT.

## 7. WHEN MATCHED AND: chỉ UPDATE khi dữ liệu thay đổi

Nếu MERGE luôn UPDATE mọi hàng matched, kể cả giá và tồn kho giống nhau, PostgreSQL vẫn có thể phát sinh công việc ghi theo MVCC.

Có thể kiểm tra sự khác biệt:

~~~sql
MERGE INTO merge_lab.product AS t
USING (
    VALUES
        ('A100'::TEXT, 35000.00::NUMERIC, 12::INTEGER),
        ('B200'::TEXT, 15000.00::NUMERIC, 40::INTEGER)
) AS s(sku, new_price, new_stock)
ON t.sku = s.sku
WHEN MATCHED AND (
    t.price IS DISTINCT FROM s.new_price
    OR t.stock IS DISTINCT FROM s.new_stock
) THEN
    UPDATE SET
        price = s.new_price,
        stock = s.new_stock,
        updated_at = statement_timestamp();
~~~

`IS DISTINCT FROM` có semantics rõ khi một phía là `NULL`:

| A | B | `A IS DISTINCT FROM B` |
|---|---|---|
| 10 | 10 | FALSE |
| 10 | 20 | TRUE |
| NULL | NULL | FALSE |
| NULL | 10 | TRUE |

Với các cột đã `NOT NULL`, `<>` cũng có thể phù hợp, nhưng `IS DISTINCT FROM` tiện cho các cột optional.

### 7.1. Vì sao tránh UPDATE không cần thiết?

UPDATE có thể:

- Ghi phiên bản tuple mới.
- Tạo WAL và dead tuples.
- Làm tăng chi phí VACUUM.
- Thay đổi `updated_at` dù nghiệp vụ không đổi.
- Kích hoạt trigger và CDC downstream.
- Tạo lock contention nếu nhiều writer.

Dù vậy, nếu nghiệp vụ cần lưu “đã xác nhận nguồn lúc này”, một bản ghi xác nhận riêng có thể đúng hơn việc update hàng chính. Quyết định phụ thuộc mục tiêu audit.

## 8. NULL trong khóa và điều kiện so sánh

SQL sử dụng logic ba giá trị: `NULL = NULL` không trả TRUE. Nếu khóa match nullable:

~~~sql
ON t.external_code = s.external_code
~~~

thì source và target cùng `external_code IS NULL` **không tự được xem là matched**.

Có thể viết:

~~~sql
ON t.external_code IS NOT DISTINCT FROM s.external_code
~~~

để coi hai NULL là giống nhau, nhưng điều đó dễ gây **nhiều hàng cùng match** nếu nhiều bản ghi thiếu khóa.

**Ưu tiên** khóa nhận diện có `NOT NULL` và `UNIQUE/PRIMARY KEY`. Với dữ liệu upstream thiếu khóa, tốt hơn tách vào vùng lỗi để xử lý, không mặc định mọi NULL cùng một đối tượng.

### 8.1. Nullable attribute khác nullable identity

Một cột `description` nullable có thể cần:

~~~sql
WHEN MATCHED
    AND t.description IS DISTINCT FROM s.description
THEN UPDATE SET description = s.description
~~~

Đây là kiểm tra thay đổi **thuộc tính**, không phải khóa nhận diện. Thường hợp lệ hơn việc coi NULL như một định danh.

## 9. USING có thể là VALUES, bảng, SELECT hoặc CTE

### 9.1. Một danh sách ngắn qua VALUES

~~~sql
MERGE INTO merge_lab.product AS t
USING (
    VALUES
        ('A100'::TEXT, 25::INTEGER),
        ('B200'::TEXT, 35::INTEGER)
) AS s(sku, new_stock)
ON t.sku = s.sku
WHEN MATCHED THEN
    UPDATE SET
        stock = s.new_stock,
        updated_at = statement_timestamp();
~~~

Dễ đọc và phù hợp vài hàng nguồn được kiểm soát.

### 9.2. Một bảng staging

Trong thực tế, nguồn có thể nằm trong bảng đã nạp từ file. Nên lọc đúng batch ở `USING` và bảo đảm khóa source duy nhất:

~~~sql
MERGE INTO merge_lab.product AS t
USING (
    SELECT sku, product_name, price, stock, source_version
    FROM merge_lab.product_feed
    WHERE batch_id = 20261114
      AND is_valid = TRUE
) AS s
ON t.sku = s.sku
WHEN MATCHED AND s.source_version > t.source_version THEN
    UPDATE SET
        product_name = s.product_name,
        price = s.price,
        stock = s.stock,
        source_version = s.source_version
WHEN NOT MATCHED THEN
    INSERT (sku, product_name, price, stock, source_version)
    VALUES (
        s.sku, s.product_name,
        s.price, s.stock, s.source_version
    );
~~~

Bảng `product_feed` sẽ được tạo trong mục tiếp theo; đây là mẫu query dùng với nó.

### 9.3. Dùng WITH

~~~sql
WITH incoming AS (
    SELECT sku, product_name, price, stock, source_version
    FROM merge_lab.product_feed
    WHERE batch_id = 20261114
)
MERGE INTO merge_lab.product AS t
USING incoming AS s
ON t.sku = s.sku
WHEN MATCHED AND s.source_version > t.source_version THEN
    UPDATE SET
        price = s.price,
        stock = s.stock,
        source_version = s.source_version
WHEN NOT MATCHED THEN
    INSERT (sku, product_name, price, stock, source_version)
    VALUES (
        s.sku, s.product_name,
        s.price, s.stock, s.source_version
    );
~~~

CTE làm rõ bước chuẩn bị nguồn, nhưng không tự biến MERGE thành một workflow nhiều transaction. Mọi hành động vẫn nằm trong semantics của statement.

## 10. Thiết kế bảng staging cho batch

Với ETL, bảng staging giúp nhận dữ liệu, kiểm tra cấu trúc và chỉ merge các hàng đã xác nhận.

~~~sql
CREATE TABLE merge_lab.product_feed (
    batch_id BIGINT NOT NULL,
    sku TEXT NOT NULL,
    product_name TEXT NOT NULL,
    price NUMERIC(12, 2) NOT NULL CHECK (price >= 0),
    stock INTEGER NOT NULL CHECK (stock >= 0),
    source_version BIGINT NOT NULL CHECK (source_version >= 1),
    is_valid BOOLEAN NOT NULL DEFAULT TRUE,
    received_at TIMESTAMPTZ NOT NULL DEFAULT statement_timestamp(),
    PRIMARY KEY (batch_id, sku)
);

INSERT INTO merge_lab.product_feed
    (batch_id, sku, product_name, price, stock, source_version)
VALUES
    (20261114, 'A100', 'Sổ tay mới', 35000.00, 12, 2),
    (20261114, 'B200', 'Bút mực', 16000.00, 38, 3),
    (20261114, 'E500', 'Hộp bút', 45000.00, 5, 1);
~~~

Khóa `PRIMARY KEY(batch_id, sku)` có tác dụng:

- Trong một batch, mỗi SKU có nhiều nhất một hàng.
- Các batch khác nhau được phép có cùng SKU.
- Truy vấn lọc theo batch có cấu trúc index phù hợp để đánh giá.

Nếu import thật có duplicate, việc nạp có thể bị từ chối ngay, trước khi MERGE tác động tới bảng đích.

### 10.1. Preflight trước khi merge

~~~sql
SELECT
    COUNT(*) AS total_rows,
    COUNT(*) FILTER (WHERE is_valid) AS valid_rows,
    COUNT(*) FILTER (WHERE NOT is_valid) AS invalid_rows
FROM merge_lab.product_feed
WHERE batch_id = 20261114;
~~~

Đối chiếu source–target:

~~~sql
SELECT
    s.sku,
    s.source_version AS incoming_version,
    t.source_version AS current_version,
    s.price AS incoming_price,
    t.price AS current_price
FROM merge_lab.product_feed AS s
LEFT JOIN merge_lab.product AS t
    ON t.sku = s.sku
WHERE s.batch_id = 20261114
ORDER BY s.sku;
~~~

Những truy vấn này không tự ghi dữ liệu, phù hợp để kiểm tra phạm vi source trước khi thực thi MERGE.

## 11. WHEN MATCHED THEN DELETE

MERGE có thể dùng một nhánh xóa hàng target đang khớp:

~~~sql
BEGIN;

MERGE INTO merge_lab.product AS t
USING (
    VALUES
        ('C300'::TEXT, 'REMOVE'::TEXT),
        ('B200'::TEXT, 'KEEP'::TEXT)
) AS s(sku, operation)
ON t.sku = s.sku
WHEN MATCHED AND s.operation = 'REMOVE' THEN
    DELETE
WHEN MATCHED AND s.operation = 'KEEP' THEN
    DO NOTHING;

ROLLBACK;
~~~

Ví dụ dùng `ROLLBACK` để minh họa an toàn trong database lab. Nếu commit và không có constraint ngăn cản, C300 bị **xóa vật lý**.

Không viết hành động như một lệnh DELETE độc lập:

~~~sql
-- Sai trong nhánh MERGE:
-- WHEN MATCHED THEN DELETE FROM merge_lab.product WHERE sku = s.sku
~~~

Trong MERGE, chỉ viết `THEN DELETE`; điều kiện thuộc `ON` và `WHEN MATCHED AND ...`.

### 11.1. Xóa mềm khác DELETE

Nếu chỉ muốn sản phẩm không còn bán nhưng vẫn giữ lịch sử:

~~~sql
WHEN MATCHED AND s.operation = 'DISABLE' THEN
    UPDATE SET
        is_active = FALSE,
        updated_at = statement_timestamp()
~~~

Đó là UPDATE trạng thái, không phải xóa vật lý. Quyết định cần xét lịch sử đơn hàng, foreign keys, retention và chính sách nghiệp vụ.

## 12. PostgreSQL 17+: WHEN NOT MATCHED BY SOURCE

Trên PostgreSQL 17 trở lên, có thể xử lý các **hàng target không có hàng source tương ứng**.

Giả sử:

~~~text
Target: A100, B200, C300
Source snapshot đầy đủ: A100, B200, E500
~~~

Các nhóm:

| SKU | Source | Target | Loại |
|---|---|---|---|
| A100 | Có | Có | MATCHED |
| B200 | Có | Có | MATCHED |
| E500 | Có | Không | NOT MATCHED BY TARGET |
| C300 | Không | Có | NOT MATCHED BY SOURCE |

Một câu MERGE toàn bộ theo snapshot:

~~~sql
-- PostgreSQL 17+.
-- Chỉ an toàn khi source là SNAPSHOT ĐẦY ĐỦ của phạm vi target.
MERGE INTO merge_lab.product AS t
USING (
    VALUES
        ('A100'::TEXT, 'Sổ tay mới'::TEXT,
         35000.00::NUMERIC, 12::INTEGER, 2::BIGINT),
        ('B200', 'Bút mực', 15000.00::NUMERIC,
         40, 3::BIGINT),
        ('E500', 'Hộp bút', 45000.00::NUMERIC,
         5, 1::BIGINT)
) AS s(sku, product_name, price, stock, source_version)
ON t.sku = s.sku
WHEN MATCHED AND s.source_version > t.source_version THEN
    UPDATE SET
        product_name = s.product_name,
        price = s.price,
        stock = s.stock,
        source_version = s.source_version,
        is_active = TRUE,
        updated_at = statement_timestamp()
WHEN NOT MATCHED BY TARGET THEN
    INSERT (
        sku, product_name, price, stock,
        source_version, is_active
    )
    VALUES (
        s.sku, s.product_name, s.price, s.stock,
        s.source_version, TRUE
    )
WHEN NOT MATCHED BY SOURCE AND t.is_active THEN
    UPDATE SET
        is_active = FALSE,
        updated_at = statement_timestamp();
~~~

Với target-only rows, nhánh BY SOURCE có thể vô hiệu hóa chúng. **Nó không giới hạn thao tác vào những SKU “đã từng thấy trong batch trước”**, mà dựa vào **tất cả target rows nằm ngoài nguồn theo điều kiện khớp**.

### 12.1. Khi nào nguồn không đủ để dùng BY SOURCE?

Nếu source chỉ gồm **những SKU thay đổi hôm nay** chứ không phải toàn bộ danh mục, tất cả SKU khác sẽ vắng mặt trong source. Nếu dùng BY SOURCE DELETE/UPDATE sẽ có nguy cơ tác động hàng loạt ngoài dự kiến.

Phải phân biệt:

- **Delta feed:** chỉ những bản ghi cần thay đổi.
- **Complete snapshot:** tất cả bản ghi thuộc một phạm vi xác định tại một mốc hợp lệ.

Chỉ dùng BY SOURCE với hành động loại bỏ/vô hiệu hóa khi **tính đầy đủ và phạm vi** được xác nhận.

### 12.2. Phạm vi tenant/danh mục

Với nhiều tenant hoặc nhiều catalog, source chỉ chứa catalog A thì không được vô hiệu hóa sản phẩm của catalog B.

Mẫu cho một schema có cột `catalog_id` (không chạy trên bảng demo thiếu cột này):

~~~sql
MERGE INTO catalog_product AS t
USING (
    SELECT catalog_id, sku, product_name, price
    FROM catalog_snapshot
    WHERE catalog_id = 42
      AND snapshot_id = 1001
) AS s
ON t.catalog_id = s.catalog_id
   AND t.sku = s.sku
WHEN MATCHED AND t.price IS DISTINCT FROM s.price THEN
    UPDATE SET
        price = s.price,
        product_name = s.product_name
WHEN NOT MATCHED BY TARGET THEN
    INSERT (catalog_id, sku, product_name, price)
    VALUES (s.catalog_id, s.sku, s.product_name, s.price)
WHEN NOT MATCHED BY SOURCE AND t.catalog_id = 42 THEN
    UPDATE SET is_active = FALSE;
~~~

Việc giới hạn target-only bằng `t.catalog_id = 42` là cần thiết trong ví dụ. Trong ứng dụng thật, catalog ID còn phải được xác thực và thống nhất với contract source/snapshot.

### 12.3. PG15/16 làm thế nào?

Cú pháp BY SOURCE chưa có. Có thể thực hiện một `UPDATE ... WHERE NOT EXISTS (...)` riêng trong transaction, sau khi xác nhận snapshot đầy đủ và phạm vi target.

Không ép server 15/16 chạy câu SQL dành cho 17+.

## 13. PostgreSQL 17+: BY TARGET và BY SOURCE khác nhau

Trong PostgreSQL 17+:

- `WHEN NOT MATCHED BY TARGET`: **source row không có target**; thường INSERT.
- `WHEN NOT MATCHED BY SOURCE`: **target row không có source**; thường UPDATE/DELETE/DO NOTHING.

`WHEN NOT MATCHED` không có qualifier vẫn có nghĩa source-only, tương ứng BY TARGET.

Điều này dễ nhầm vì “không khớp” phải nói rõ **vắng mặt ở phía nào**.

Nếu MERGE cần xử lý cả hai chiều, PostgreSQL có thể dùng một dạng full join để tạo candidate rows; điều kiện `ON` phải phù hợp với yêu cầu JOIN. Với khóa bằng bình thường `t.sku = s.sku`, mô hình rõ ràng hơn các điều kiện phức tạp hoặc chỉ lọc một bên.

### 13.1. Cột nào có thể dùng trong điều kiện?

- `WHEN MATCHED`: source và target cùng hiện diện; có thể tham chiếu cả hai.
- `WHEN NOT MATCHED BY TARGET`: không có target row; hành động INSERT dựa trên source.
- `WHEN NOT MATCHED BY SOURCE`: không có source row; hành động UPDATE/DELETE dựa trên target.

Không đưa `s.stock` vào điều kiện target-only như thể một source row thực tế vẫn có giá trị.

## 14. BY SOURCE và hard delete cần kiểm soát đặc biệt

Ví dụ quá rủi ro nếu source không đầy đủ:

~~~sql
-- PostgreSQL 17+, KHÔNG dùng với nguồn delta:
-- WHEN NOT MATCHED BY SOURCE THEN DELETE
~~~

Hậu quả có thể gồm:

- Xóa những sản phẩm không nằm trong batch một phần.
- Xóa hoặc không xóa được do FK tới order lines.
- Phát sinh WAL và dead tuples lớn.
- Gây tải cao cho VACUUM/replica.
- Đưa audit/CDC downstream vào trạng thái không mong muốn.
- Tạo yêu cầu restore/đối soát phức tạp.

Một nhánh `UPDATE SET is_active=FALSE` thường phù hợp hơn với danh mục cần giữ lịch sử. Khi thật sự cần purge, nên thiết kế quy trình riêng theo chính sách retention và quyền.

### 14.1. Snapshot rỗng không luôn có nghĩa “xóa mọi thứ”

Nếu upstream gửi 0 hàng do lỗi mạng, đó không phải bằng chứng toàn bộ danh mục đã biến mất. Cần xác nhận snapshot complete, số lượng kỳ vọng, checksum hoặc tín hiệu kết thúc từ nguồn trước khi dùng phép đối chiếu target-only.

## 15. Duplicate source và cardinality violation

Một source row phải khớp theo quan hệ được thiết kế; đặc biệt **mỗi target row không được bị cố tác động nhiều lần trong cùng một MERGE**.

Ví dụ lỗi:

~~~sql
-- Chỉ minh họa lỗi: hai hàng nguồn cùng SKU.
MERGE INTO merge_lab.product AS t
USING (
    VALUES
        ('A100'::TEXT, 10::INTEGER),
        ('A100'::TEXT, 20::INTEGER)
) AS s(sku, new_stock)
ON t.sku = s.sku
WHEN MATCHED THEN
    UPDATE SET stock = s.new_stock;
~~~

Hai hàng nguồn đều khớp cùng target A100. Một lần UPDATE/DELETE lặp lên cùng target row trong MERGE có thể dẫn tới **cardinality violation**. Nếu hai source rows đều định INSERT cùng một SKU chưa tồn tại, có thể gặp **unique violation**.

Không dựa vào việc database “tự chọn hàng cuối” hoặc “tự bỏ một hàng”. Đó không phải contract của MERGE.

### 15.1. Tìm duplicate trong nguồn raw

~~~sql
WITH incoming(sku, stock) AS (
    VALUES
        ('A100'::TEXT, 10),
        ('A100', 20),
        ('B200', 30)
)
SELECT sku, COUNT(*) AS count_per_sku
FROM incoming
GROUP BY sku
HAVING COUNT(*) > 1;
~~~

Kết quả: A100 có 2 hàng.

### 15.2. Khử trùng phải có quy tắc nghiệp vụ

Giả sử source có version và received_at, có thể chọn bản mới nhất:

~~~sql
WITH incoming(sku, stock, version, received_at) AS (
    VALUES
        ('A100'::TEXT, 10, 2::BIGINT,
         TIMESTAMPTZ '2026-11-14 08:00:00+00'),
        ('A100', 20, 3::BIGINT,
         TIMESTAMPTZ '2026-11-14 08:05:00+00'),
        ('B200', 30, 1::BIGINT,
         TIMESTAMPTZ '2026-11-14 08:10:00+00')
)
SELECT DISTINCT ON (sku)
    sku, stock, version, received_at
FROM incoming
ORDER BY sku, version DESC, received_at DESC;
~~~

Nếu hai hàng vẫn có cùng version và timestamp nhưng nội dung khác, phải thêm tie-breaker được định nghĩa hoặc từ chối nguồn bất thường. `DISTINCT ON` không tự biết bản nào đúng về nghiệp vụ.

## 16. Target cũng phải có khóa xác định

Nếu target có hai hàng SKU A100 do thiếu unique constraint, một source A100 có thể match cả hai và làm thay đổi nhiều hàng đích.

Điều này không nhất thiết cùng loại lỗi với **một target bị sửa hai lần**. Nhưng nếu SKU là định danh duy nhất, việc cập nhật hai target A100 là sai nghiệp vụ.

Nên đặt `PRIMARY KEY` hoặc `UNIQUE` theo khóa nhận diện thật. Với multi-tenant:

~~~text
identity = (tenant_id, sku)
~~~

thì cả index/constraint và `ON` cần thể hiện cặp đó.

## 17. MERGE khác UPDATE ... FROM

PostgreSQL cho phép:

~~~sql
UPDATE merge_lab.product AS t
SET
    stock = s.stock,
    updated_at = statement_timestamp()
FROM (
    VALUES
        ('A100'::TEXT, 12::INTEGER),
        ('B200'::TEXT, 20::INTEGER)
) AS s(sku, stock)
WHERE t.sku = s.sku;
~~~

Đây là cập nhật target khi tìm được hàng nguồn khớp. Nó **không tự thêm** các SKU chưa tồn tại.

`MERGE` có thể kết hợp nhiều hành động theo điều kiện.

| Tiêu chí | UPDATE ... FROM | MERGE |
|---|---|---|
| Update hàng khớp | Có | Có |
| Chèn hàng không khớp | Không trong cùng statement | Có |
| Xóa hàng matched theo nhánh | Không trong cùng UPDATE | Có |
| Nhiều nhánh điều kiện | Không cùng mô hình WHEN | Có |
| Duplicate source khớp một target | Kết quả chọn source có thể không rõ | Có thể cardinality violation |
| Thích hợp update đơn giản | Thường gọn | Có thể không cần thiết |
| Thích hợp đồng bộ đa hành động | Cần kết hợp statement | Phù hợp hơn |

Khi chỉ cần cập nhật một tập hàng, `UPDATE ... FROM` vẫn là công cụ tốt nếu bảo đảm source keys duy nhất.

## 18. MERGE khác INSERT ... ON CONFLICT

UPSERT truyền thống trong PostgreSQL:

~~~sql
INSERT INTO merge_lab.product
    (sku, product_name, price, stock, source_version)
VALUES
    ('A100', 'Sổ tay mới', 35000.00, 12, 2)
ON CONFLICT (sku)
DO UPDATE SET
    product_name = EXCLUDED.product_name,
    price = EXCLUDED.price,
    stock = EXCLUDED.stock,
    source_version = EXCLUDED.source_version;
~~~

`ON CONFLICT` xuất phát từ việc **INSERT gặp unique conflict**, còn MERGE xuất phát từ **khớp source–target theo ON**.

| Tiêu chí | INSERT ... ON CONFLICT | MERGE |
|---|---|---|
| Điểm xuất phát | INSERT + xử lý conflict | JOIN/matching |
| Unique arbiter | Cần cho conflict phù hợp | ON xác định match; unique vẫn bảo vệ target |
| Upsert đơn giản | Rất phù hợp | Làm được |
| DELETE matched | Không qua DO UPDATE | Có |
| Target-only trong snapshot | Không | PG17+ |
| Nhiều nhánh hành động | Hạn chế | Linh hoạt |
| Concurrent INSERT cùng khóa | Có cơ chế xử lý conflict riêng | Không có cùng bảo đảm chuyển nhánh |

### 18.1. Chọn ON CONFLICT khi nào?

Nếu chỉ cần:

> Insert một SKU; nếu đã có thì update.

và có unique constraint phù hợp, `INSERT ... ON CONFLICT DO UPDATE` thường dễ đọc và có semantics cạnh tranh insert thích hợp hơn.

### 18.2. Chọn MERGE khi nào?

Nếu cần đồng thời:

- Update khi version mới.
- Bỏ qua khi version cũ.
- Delete nếu có operation REMOVE.
- Insert hàng chưa tồn tại.
- PG17+: vô hiệu hóa hàng target-only trong snapshot đầy đủ.

MERGE giúp mô tả nhiều nhánh trong một statement rõ ràng hơn.

**Hai câu lệnh không hoàn toàn tương đương về concurrency.**

## 19. Concurrency: MERGE vẫn có thể gặp unique violation

Giả sử hai transaction cùng MERGE SKU E500 chưa có:

~~~text
Transaction A                 Transaction B
-------------                 -------------
đọc: E500 chưa có             đọc: E500 chưa có
chọn nhánh INSERT             chọn nhánh INSERT
insert thành công             có thể lỗi unique conflict
commit                        retry/rollback theo chính sách
~~~

Primary key giúp không tạo hai hàng E500, nhưng không bảo đảm cả hai MERGE đều thành công.

Những lỗi có thể cần xử lý:

- Unique violation trong cuộc đua INSERT.
- Lock contention khi nhiều transaction cập nhật cùng hàng.
- Deadlock nếu khóa nhiều hàng theo thứ tự khác.
- Serialization failure nếu dùng isolation phù hợp và có xung đột.

### 19.1. Phương án kiểm soát

- Có unique constraint đúng khóa nghiệp vụ.
- Dùng UPSERT khi chỉ cần INSERT/UPDATE cạnh tranh cao.
- Chia công việc theo tenant hoặc nhóm khóa để giảm tranh chấp.
- Thiết kế retry cho lỗi có thể phục hồi, giới hạn số lần.
- Đảm bảo thao tác có tính idempotent.
- Tối ưu transaction ngắn và quan sát lock waits.

### 19.2. Retry phải xử lý transaction đã lỗi

Nếu một statement thất bại trong transaction explicit, PostgreSQL thường yêu cầu `ROLLBACK` hoặc quay về savepoint hợp lệ trước khi tiếp tục. Không gọi lại MERGE trong transaction đang ở trạng thái aborted rồi kỳ vọng nó sẽ chạy thành công.

Với `SERIALIZABLE`, ứng dụng cần retry **toàn bộ transaction** khi gặp serialization failure, sau khi đọc lại điều kiện cần thiết.

## 20. Idempotency: chạy lại batch có an toàn không?

Một batch có thể được gửi lại do timeout. So sánh hai chính sách:

**Đặt giá trị tuyệt đối:**

~~~sql
WHEN MATCHED THEN
    UPDATE SET stock = s.absolute_stock
~~~

Khi nguồn giống nhau, chạy lại thường giữ giá trị stock như cũ (dù có thể vẫn tốn UPDATE nếu không có điều kiện bỏ qua).

**Áp dụng delta:**

~~~sql
WHEN MATCHED THEN
    UPDATE SET stock = t.stock + s.stock_delta
~~~

Nếu chạy lại cùng batch, delta bị cộng lần nữa và số lượng sai.

Ví dụ:

~~~text
Tồn ban đầu: 10
Delta: +5

Lần 1: 15
Retry lần 2: 20    <-- sai nếu cùng một event
~~~

Với delta, cần event ID/batch ID và cơ chế ghi nhận đã áp dụng **cùng transaction**. MERGE tự nó không biết một delta đã được xử lý trước đó.

### 20.1. Versioning đúng nghĩa

Nếu dùng `source_version > target_version`, upstream phải bảo đảm version đơn điệu theo phạm vi phù hợp. Cùng một version nhưng nội dung khác cần được phân loại, không mặc định version bảo đảm tính đúng nếu upstream không có contract rõ ràng.

## 21. MERGE trong transaction

Một câu MERGE được PostgreSQL xử lý theo semantics atomic statement trong transaction. Khi constraint lỗi, không được commit những thay đổi một phần của chính statement như thể MERGE đã thành công một nửa.

Quy trình nhiều bước có thể dùng:

~~~sql
BEGIN;

-- 1. Kiểm tra trạng thái batch.
-- 2. Thực hiện MERGE từ nguồn đã xác minh.
-- 3. Ghi metadata hoàn tất nếu mọi điều kiện đạt.

COMMIT;
~~~

Đây là khung quy trình. Với production, kiểm tra lock, timeout, rollback, audit và tác động hệ thống phụ.

### 21.1. Tác động ngoài database không tự rollback

Nếu code gọi HTTP tới search engine hoặc gửi message trong lúc transaction PostgreSQL chưa commit, việc rollback DB không tự hoàn tác message đã gửi.

Một mẫu kiến trúc thường cân nhắc là **transactional outbox**: cùng transaction ghi thay đổi bảng đích và một event trong outbox; worker phát ra ngoài sau commit, có retry/idempotency.

## 22. Constraints của target vẫn áp dụng

Trong bảng demo:

~~~sql
price NUMERIC(12,2) NOT NULL CHECK (price >= 0)
stock INTEGER NOT NULL CHECK (stock >= 0)
sku TEXT PRIMARY KEY
~~~

Các hành động MERGE vẫn phải thỏa các ràng buộc này.

- Insert stock âm → có thể bị CHECK từ chối.
- Insert SKU đã tồn tại → có thể bị PK từ chối.
- Delete hàng cha còn child FK → có thể bị FK từ chối.
- Cập nhật giá trị không phù hợp kiểu → lỗi chuyển kiểu hoặc constraint.

Không bỏ constraint chỉ để batch MERGE chạy qua. Hãy validate source, phân loại lỗi, rồi xử lý theo chính sách.

### 22.1. Foreign key và DELETE

Một sản phẩm đã xuất hiện trong đơn hàng có thể cần được giữ để đối soát. Nếu bảng chi tiết đơn có FK tới product, hard delete có thể thất bại. Một giải pháp nghiệp vụ có thể là `UPDATE is_active=FALSE`, nhưng phải phân biệt vô hiệu hóa bán hàng với xóa dữ liệu theo retention.

## 23. Trigger khi MERGE thay đổi hàng

MERGE có thể kích hoạt trigger tương ứng với hành động được khai báo.

- Row-level trigger chạy cho những hàng thật sự trải qua loại thao tác tương ứng.
- Statement-level trigger có thể được gọi cho các loại hành động xuất hiện trong MERGE, kể cả khi không có hàng thật sự thực hiện nhánh đó, theo quy tắc PostgreSQL.

Vì vậy một MERGE có cả INSERT và UPDATE, nhưng chỉ UPDATE có hàng, vẫn có thể liên quan statement-level trigger loại INSERT. Không dùng số lần trigger statement để suy số hàng inserted.

Khi bảng có trigger:

- Kiểm tra loại trigger và thời điểm BEFORE/AFTER.
- Đánh giá tác động audit/CDC.
- Xem trigger có thay khóa hoặc cột trong ON không.
- Cẩn thận với side effects ra ngoài PostgreSQL.
- Không mặc định logic MERGE trên giấy là toàn bộ thay đổi cuối cùng.

## 24. Quyền của role chạy MERGE

PostgreSQL không có một quyền `MERGE` độc lập thay thế tất cả quyền DML.

Role thực thi có thể cần:

- `SELECT` trên những cột đọc từ source và target.
- `INSERT` nếu MERGE chứa nhánh INSERT.
- `UPDATE` trên các cột được SET.
- `DELETE` nếu có nhánh DELETE.
- Quyền schema/đối tượng theo cấu hình.

Quyền được kiểm tra với các hành động được **khai báo trong statement**, không chỉ những nhánh tình cờ xảy ra với batch cụ thể.

Một role chỉ được UPDATE có thể không chạy được MERGE có cả nhánh DELETE dù người vận hành tin rằng batch này không có hàng nào cần xóa.

**Nguyên tắc:** cấp quyền tối thiểu, tách job chỉ cập nhật khỏi job được phép hard delete, và thử dưới role thật trước production.

## 25. PostgreSQL 17+: RETURNING và merge_action()

Từ PostgreSQL 17, MERGE có thể trả những hàng thực sự được thay đổi:

~~~sql
-- PostgreSQL 17+.
MERGE INTO merge_lab.product AS t
USING (
    VALUES
        ('A100'::TEXT, 33::INTEGER),
        ('B200'::TEXT, 44::INTEGER)
) AS s(sku, new_stock)
ON t.sku = s.sku
WHEN MATCHED AND t.stock IS DISTINCT FROM s.new_stock THEN
    UPDATE SET
        stock = s.new_stock,
        updated_at = statement_timestamp()
RETURNING
    merge_action() AS action,
    t.sku,
    t.stock;
~~~

`merge_action()` có thể trả `INSERT`, `UPDATE` hoặc `DELETE` cho các hàng được thay đổi.

**Không sử dụng hàm này trong SELECT thông thường**; nó dành cho phần RETURNING của MERGE theo tài liệu phiên bản hỗ trợ.

### 25.1. DO NOTHING không xuất hiện như một thay đổi

Nếu một hàng được bỏ qua vì không nhánh phù hợp hoặc `DO NOTHING`, nó không phải hàng INSERT/UPDATE/DELETE để `RETURNING` thông báo như một thay đổi.

Nếu cần số hàng skipped theo lý do, phải có logic preflight/đối soát hoặc audit riêng.

### 25.2. Command tag của MERGE

Khi thành công, PostgreSQL trả command tag dạng:

~~~text
MERGE total_count
~~~

`total_count` là tổng số hàng đã thay đổi. Nó **không phải số source rows** và không tự phân biệt số INSERT/UPDATE/DELETE.

## 26. PostgreSQL 18+: OLD và NEW trong RETURNING

PostgreSQL 18 hỗ trợ tham chiếu giá trị cũ/mới trong `MERGE RETURNING`.

~~~sql
-- PostgreSQL 18+.
MERGE INTO merge_lab.product AS t
USING (
    VALUES ('A100'::TEXT, 25::INTEGER)
) AS s(sku, new_stock)
ON t.sku = s.sku
WHEN MATCHED AND t.stock IS DISTINCT FROM s.new_stock THEN
    UPDATE SET
        stock = s.new_stock,
        updated_at = statement_timestamp()
RETURNING
    merge_action() AS action,
    t.sku,
    old.stock AS previous_stock,
    new.stock AS current_stock;
~~~

Với UPDATE, có thể nhìn stock trước và sau. Với INSERT, không có giá trị OLD của target; với DELETE, không có giá trị NEW theo semantics tương ứng.

Một cú pháp mở rộng khác trên PG18:

~~~sql
-- Minh họa phần RETURNING:
-- RETURNING WITH (OLD AS o, NEW AS n)
--     merge_action(), o.stock, n.stock
~~~

Không chèn những cú pháp này vào code phải chạy PostgreSQL 15–17.

## 27. Preview trước khi thực thi MERGE

Trước khi cập nhật một batch quan trọng, có thể viết SELECT dự đoán hành động:

~~~sql
WITH incoming AS (
    SELECT
        sku, price, stock, source_version
    FROM merge_lab.product_feed
    WHERE batch_id = 20261114
      AND is_valid = TRUE
)
SELECT
    s.sku,
    t.source_version AS target_version,
    s.source_version AS source_version,
    CASE
        WHEN t.sku IS NULL THEN 'would_insert'
        WHEN s.source_version > t.source_version
            THEN 'would_update'
        ELSE 'would_skip'
    END AS planned_action
FROM incoming AS s
LEFT JOIN merge_lab.product AS t
    ON t.sku = s.sku
ORDER BY s.sku;
~~~

Đếm theo hành động:

~~~sql
WITH incoming AS (
    SELECT sku, source_version
    FROM merge_lab.product_feed
    WHERE batch_id = 20261114
),
planned AS (
    SELECT
        CASE
            WHEN t.sku IS NULL THEN 'insert'
            WHEN s.source_version > t.source_version THEN 'update'
            ELSE 'skip'
        END AS action
    FROM incoming AS s
    LEFT JOIN merge_lab.product AS t
        ON t.sku = s.sku
)
SELECT action, COUNT(*) AS candidate_count
FROM planned
GROUP BY action
ORDER BY action;
~~~

Preview phản ánh snapshot của **câu SELECT**. Nếu transaction khác thay đổi target giữa preview và MERGE, kết quả thực tế có thể khác.

Một hệ thống cần độ tin cậy cao nên có validation và transaction strategy rõ thay vì tin tuyệt đối vào số preview.

## 28. EXPLAIN và kế hoạch thực thi MERGE

Để xem kế hoạch **không thực thi thay đổi**, dùng `EXPLAIN`:

~~~sql
EXPLAIN
MERGE INTO merge_lab.product AS t
USING (
    SELECT sku, price, stock, source_version
    FROM merge_lab.product_feed
    WHERE batch_id = 20261114
) AS s
ON t.sku = s.sku
WHEN MATCHED AND s.source_version > t.source_version THEN
    UPDATE SET
        price = s.price,
        stock = s.stock,
        source_version = s.source_version
WHEN NOT MATCHED THEN
    INSERT (
        sku, product_name, price,
        stock, source_version
    )
    VALUES (
        s.sku, 'Chưa đặt tên', s.price,
        s.stock, s.source_version
    );
~~~

Những điều cần quan sát:

- Target có được tìm theo khóa match phù hợp không?
- Source có được giới hạn theo batch không?
- Planner chọn Hash Join, Nested Loop hay Merge Join?
- Ước lượng số hàng source/target có hợp lý?
- Có sort/scan lớn ngoài dự kiến?
- Index và thống kê của staging có đủ không?

### 28.1. Cẩn thận với EXPLAIN ANALYZE

`EXPLAIN (ANALYZE, BUFFERS)` **thực thi DML**. Không chạy trực tiếp trên production chỉ vì muốn xem thời gian.

Trong lab có thể:

~~~sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS)
MERGE INTO merge_lab.product AS t
USING (
    VALUES ('A100'::TEXT, 12::INTEGER)
) AS s(sku, new_stock)
ON t.sku = s.sku
WHEN MATCHED THEN
    UPDATE SET stock = s.new_stock;

ROLLBACK;
~~~

`ROLLBACK` khôi phục thay đổi transaction trong DB, nhưng không tự thu hồi mọi side effect đã gửi ra ngoài database. Với production, cần thử nghiệm và chính sách an toàn riêng.

## 29. Index nào giúp MERGE?

Nếu `ON t.sku = s.sku`, target cần tra cứu SKU. Bảng demo đã có `PRIMARY KEY(sku)`, vì vậy có unique B-tree index phục vụ lookup.

Không cần tạo một index thứ hai giống hệt chỉ để MERGE.

Với multi-tenant, nếu SKU chỉ unique trong tenant:

~~~text
PRIMARY KEY (tenant_id, sku)

ON t.tenant_id = s.tenant_id
   AND t.sku = s.sku
~~~

Cả khóa target, điều kiện ON và phạm vi source phải đồng nhất.

Với source bảng staging:

~~~text
PRIMARY KEY (batch_id, sku)
~~~

giúp tra theo batch và ngăn duplicate trong một batch.

Nhưng planner vẫn có thể chọn Hash Join/Seq Scan khi source hoặc target lớn. **Có index không bảo đảm engine luôn dùng Index Scan**. Tùy dữ liệu và query, join toàn tập có thể rẻ hơn hàng triệu lần lookup từng khóa.

## 30. MERGE batch lớn và chi phí vận hành

Một MERGE xử lý hàng triệu rows có thể:

- Giữ locks nhiều hàng trong thời gian dài.
- Sinh lượng WAL lớn.
- Tạo dead tuples.
- Tăng áp lực autovacuum.
- Gây replication lag.
- Tốn CPU/memory cho JOIN.
- Làm rollback chậm nếu lỗi gần cuối.

Nếu là **delta feed**, có thể chia theo batch/khóa không chồng lấn và checkpoint mỗi phần theo cơ chế xử lý.

Nếu là **full snapshot** và cần BY SOURCE, không được chạy logic “target không có trong source” sau từng batch nhỏ, bởi mỗi batch chỉ chứa một phần snapshot. Cần nạp/kiểm tra **toàn bộ snapshot** trước khi quyết định target-only.

### 30.1. Một quy trình nhiều batch an toàn hơn

~~~text
Nhận snapshot_id
    |
    v
Nạp staging phần 1..N
    |
    v
Kiểm tra số hàng + duplicate + checksum
    |
    v
Đánh dấu snapshot COMPLETE
    |
    v
MERGE các source rows hợp lệ
    |
    v
Chỉ khi source là full snapshot:
  đối chiếu target-only trong scope
    |
    v
Audit + kiểm tra + checkpoint
~~~

Không được coi một batch rỗng là bằng chứng toàn bộ dữ liệu upstream đã bị xóa.

## 31. Deadlock và thứ tự xử lý

Hai transaction đồng thời có thể:

~~~text
T1 khóa SKU-A, chờ SKU-B
T2 khóa SKU-B, chờ SKU-A
~~~

PostgreSQL có thể phát hiện deadlock và hủy một transaction.

Biện pháp:

- Chia công việc theo tenant hoặc nhóm khóa.
- Giữ transaction ngắn.
- Cân nhắc thứ tự xử lý source nhất quán.
- Retry đúng loại lỗi với giới hạn.
- Theo dõi lock waits và các batch chồng lấn.

Sắp `ORDER BY sku` trong source query có thể hỗ trợ một số trường hợp nhưng không bảo đảm tuyệt đối không deadlock do optimizer, triggers hoặc hành động khác. Cần đo và thiết kế theo workload.

## 32. PostgreSQL partitioned table và MERGE

Khi target là partitioned table:

- INSERT có thể phải được route vào partition.
- Constraint của partition vẫn áp dụng.
- Khóa unique/primary key của partitioned table có hạn chế liên quan partition key theo phiên bản.
- UPDATE khóa partition có thể liên quan di chuyển hàng hoặc hạn chế phiên bản.
- Planner/locks có thể liên quan nhiều partitions.
- Trigger/FK/rules có thể có tương tác cần kiểm tra.

Không chuyển một câu MERGE từ bảng thường sang partitioned target rất lớn mà chưa thử trên đúng phiên bản, kiểu partition key và ràng buộc.

## 33. View và foreign table có dùng làm target được không?

Hỗ trợ target không đồng nhất giữa các dạng object và major versions:

- Materialized views không phải target MERGE thông thường.
- Foreign tables có những hạn chế/không hỗ trợ target MERGE theo tài liệu hiện hành.
- Views có điều kiện hỗ trợ riêng, như updatable views/INSTEAD OF triggers ở những phiên bản hỗ trợ.
- Rules, triggers và partitioning có thể ảnh hưởng việc chấp nhận lệnh.

Không suy rằng một đối tượng `SELECT` được thì chắc chắn `MERGE INTO` được. Hãy đối chiếu tài liệu server và thử trên staging.

## 34. Java JDBC: một SKU bằng PreparedStatement

Với Java, không nên nối dữ liệu người dùng trực tiếp vào SQL. PreparedStatement giúp bind giá trị:

~~~java
import javax.sql.DataSource;
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;

public final class ProductMergeRepository {
    private final DataSource dataSource;

    public ProductMergeRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public int mergeOne(
        String sku,
        String name,
        BigDecimal price,
        int stock,
        long version
    ) throws SQLException {
        String sql = """
            MERGE INTO merge_lab.product AS t
            USING (
                VALUES (
                    CAST(? AS TEXT),
                    CAST(? AS TEXT),
                    CAST(? AS NUMERIC(12,2)),
                    CAST(? AS INTEGER),
                    CAST(? AS BIGINT)
                )
            ) AS s(sku, name, price, stock, version)
            ON t.sku = s.sku
            WHEN MATCHED AND s.version > t.source_version THEN
                UPDATE SET
                    product_name = s.name,
                    price = s.price,
                    stock = s.stock,
                    source_version = s.version,
                    updated_at = statement_timestamp()
            WHEN NOT MATCHED THEN
                INSERT (
                    sku, product_name, price,
                    stock, source_version
                )
                VALUES (
                    s.sku, s.name, s.price,
                    s.stock, s.version
                )
            """;

        try (Connection con = dataSource.getConnection();
             PreparedStatement ps = con.prepareStatement(sql)) {
            ps.setString(1, sku);
            ps.setString(2, name);
            ps.setBigDecimal(3, price);
            ps.setInt(4, stock);
            ps.setLong(5, version);
            return ps.executeUpdate();
        }
    }
}
~~~

Ví dụ giả định Java 17+ (text blocks), PostgreSQL JDBC driver và `DataSource` đã cấu hình.

Lưu ý:

- `executeUpdate()` phản ánh số hàng được cập nhật theo semantics JDBC/driver; nó không thay một audit chi tiết.
- Cần validate giá, stock, version và quyền.
- Với nhiều writer có thể gặp unique conflict/deadlock, nên có chính sách retry phù hợp.
- Với batch lớn nên nạp staging và MERGE từ SELECT thay vì sinh SQL có hàng trăm nghìn placeholder.
- Đừng chèn tên bảng/cột do client gửi trực tiếp vào SQL.

## 35. Quan sát kết quả và audit

Một job đồng bộ nên phân biệt:

| Chỉ số | Ý nghĩa |
|---|---|
| `source_rows` | Tổng hàng nhận được |
| `valid_rows` | Hàng qua validation |
| `duplicate_keys` | Số khóa bị trùng trong nguồn |
| `would_insert` | Số hàng dự đoán insert tại thời điểm preview |
| `would_update` | Số hàng dự đoán update |
| `actual_changed` | Số hàng thực tế được thay đổi |
| `skipped_rows` | Hàng không có hành động do version/condition |
| `failed_batches` | Số batch bị rollback/lỗi |
| `target_only_rows` | Hàng chỉ có ở target trong phạm vi full snapshot |
| `processed_batch_id` | Định danh đợt đã xử lý |

Đừng suy từ `MERGE 2` rằng nguồn có đúng hai hàng hoặc đã xử lý thành công mọi hàng đầu vào.

### 35.1. Đối soát sau MERGE

~~~sql
SELECT
    s.sku,
    s.source_version,
    t.source_version AS target_version,
    s.price AS source_price,
    t.price AS target_price,
    s.stock AS source_stock,
    t.stock AS target_stock
FROM merge_lab.product_feed AS s
LEFT JOIN merge_lab.product AS t
    ON t.sku = s.sku
WHERE s.batch_id = 20261114
ORDER BY s.sku;
~~~

Nếu target version cao hơn source version, việc khác giá có thể là chủ đích **không cho batch cũ ghi đè**. Vì vậy đối soát phải hiểu version policy thay vì yêu cầu hai bên luôn bằng nhau trong mọi trường hợp.

### 35.2. Ghi lịch sử thao tác

Audit nên lưu ít nhất batch ID, source system, snapshot flag, version/policy, thời điểm áp dụng, số hàng thay đổi và lỗi. Tránh lưu thông tin nhạy cảm không cần thiết vào log. Với PG17+ có thể dùng kết quả RETURNING để ghi nhận loại hành động, nhưng kết quả trả về client không tự là audit bền vững.

## 36. Những sai lầm phổ biến

### Sai lầm 1 — Chạy MERGE trên PostgreSQL cũ hơn 15

Server không hỗ trợ MERGE. Kiểm tra `server_version` trước.

### Sai lầm 2 — Chạy BY SOURCE/RETURNING trên PG15/16

Những khả năng này chỉ có từ PostgreSQL 17; dùng cú pháp tương thích.

### Sai lầm 3 — Đặt trạng thái target trong ON

Một hàng tồn tại bị coi là NOT MATCHED, có thể gây duplicate INSERT. Dùng ON cho khóa nhận diện, WHEN cho điều kiện hành động.

### Sai lầm 4 — Không bảo đảm source unique theo khóa

Một target bị cập nhật/xóa nhiều lần trong MERGE có thể bị cardinality violation. Cần staging constraint và validation.

### Sai lầm 5 — Target không có khóa unique

Một source row có thể match nhiều target rows. Định nghĩa PK/UNIQUE đúng nghiệp vụ.

### Sai lầm 6 — Thứ tự WHEN sai

Nhánh tổng quát trước nhánh cụ thể làm nhánh sau không thể tới. Sắp cụ thể trước, fallback sau.

### Sai lầm 7 — Dùng BY SOURCE với source delta

Vô hiệu hóa hoặc xóa hàng loạt hàng hợp lệ không xuất hiện trong delta. Chỉ dùng với snapshot đầy đủ và scope an toàn.

### Sai lầm 8 — Dùng DELETE thay cho vô hiệu hóa

Có thể phá lịch sử, FK hoặc chính sách retention. Chọn hành động theo vòng đời nghiệp vụ.

### Sai lầm 9 — Nhầm MERGE với INSERT ON CONFLICT

Khác nhau về matching và concurrency. Với upsert đơn giản nhiều writer, xem xét ON CONFLICT.

### Sai lầm 10 — Retry delta không có idempotency

Cộng tồn kho hai lần. Dùng event/batch ID và checkpoint.

### Sai lầm 11 — Cập nhật mọi hàng dù không thay đổi

Tăng WAL, dead tuples, triggers và updated_at không cần thiết. Dùng điều kiện khác biệt nếu phù hợp.

### Sai lầm 12 — Bỏ qua NULL semantics

`NULL = NULL` không TRUE; dùng khóa NOT NULL, còn thuộc tính nullable dùng `IS DISTINCT FROM` nếu cần.

### Sai lầm 13 — Không kiểm tra CHECK/UNIQUE/FK

MERGE không vô hiệu constraints; phải validate source và giữ ràng buộc.

### Sai lầm 14 — Không tính đến trigger

Statement-level trigger có thể xảy ra dù nhánh không sửa hàng; cần kiểm tra side effects.

### Sai lầm 15 — EXPLAIN ANALYZE trên production

ANALYZE thực sự thực thi MERGE. Chỉ dùng khi đã có biện pháp an toàn phù hợp.

### Sai lầm 16 — MERGE batch quá lớn

Lock/WAL/vacuum/replication lag có thể tăng. Phân chia và giám sát workload.

### Sai lầm 17 — Không phân quyền theo hành động khai báo

Role có thể cần cả INSERT/UPDATE/DELETE tùy nhánh, dù batch dự kiến chỉ một loại.

### Sai lầm 18 — Không có snapshot validation/checksum

Source rỗng do lỗi có thể bị coi là snapshot đầy đủ và gây xóa target. Cần tín hiệu COMPLETE đáng tin cậy.

### Sai lầm 19 — Không lưu audit/checkpoint

Không biết batch đã xử lý, retry hay rollback. Cần metadata và đối soát.

### Sai lầm 20 — Sai tenant trong điều kiện ON

Cùng SKU ở nhiều tenant có thể khớp nhầm. Dùng khóa ghép và authorization.

## 37. Quy trình triển khai MERGE có kiểm soát

**Bước 1 — Kiểm tra phiên bản PostgreSQL.** Chọn cú pháp phù hợp với server.

**Bước 2 — Định nghĩa mục tiêu.** Upsert đơn giản, delta changes, hay full snapshot reconciliation?

**Bước 3 — Xác định khóa khớp.** ON phải bám vào PK/UNIQUE hoặc khóa nghiệp vụ đã được bảo đảm.

**Bước 4 — Chuẩn bị staging.** Có batch ID, NOT NULL, CHECK, unique constraint và chính sách duplicate.

**Bước 5 — Validate source.** Số hàng, schema, version, scope tenant, checksum và trạng thái đầy đủ.

**Bước 6 — Thiết kế WHEN.** Nhánh đặc biệt trước, fallback sau; xác định skip/update/insert/delete.

**Bước 7 — Thiết kế xử lý NULL.** Tránh nullable identity, dùng IS DISTINCT FROM cho thuộc tính khi cần.

**Bước 8 — Preview bằng SELECT.** Phân loại would_insert/would_update/would_skip và kiểm tra số lượng.

**Bước 9 — Kiểm tra constraints/quyền.** Đảm bảo role có quyền tối thiểu và FK/triggers phù hợp.

**Bước 10 — Xem EXPLAIN.** Đối chiếu index, join plan và khối lượng dự đoán.

**Bước 11 — Thực thi transaction.** Giữ ngắn, có timeout, retry policy, idempotency và audit.

**Bước 12 — Đối soát sau commit.** So source–target theo version, kiểm tra actual changes và xử lý lỗi.

**Bước 13 — Riêng cho BY SOURCE.** Chỉ thực thi khi snapshot đầy đủ, scope được chứng minh và đã đặt guard chống xóa hàng loạt.

## 38. Bài tập thực hành

### Bài 1 — MATCHED và NOT MATCHED

Target có A100, B200; source có B200, C300. Phân loại B200, C300 và A100 theo hai phía.

**Gợi ý:** B200 matched; C300 source-only; A100 target-only nếu dùng logic PG17+.

### Bài 2 — MERGE cơ bản

Viết MERGE cập nhật stock A100 và chèn SKU X900 từ một `VALUES`.

**Gợi ý:** ON theo SKU, WHEN MATCHED UPDATE và WHEN NOT MATCHED INSERT.

### Bài 3 — Version guard

Target A100 version 10, source version 8. Điều kiện nào ngăn ghi đè dữ liệu mới bằng dữ liệu cũ?

**Gợi ý:** `s.source_version > t.source_version`.

### Bài 4 — Điều kiện ON sai

Vì sao `ON t.sku=s.sku AND t.is_active=TRUE` có thể gây INSERT trùng?

**Gợi ý:** hàng inactive vẫn tồn tại nhưng không khớp.

### Bài 5 — WHEN order

Muốn vô hiệu hóa khi stock=0 và cập nhật bình thường nếu stock>0, đặt nhánh nào trước?

**Gợi ý:** nhánh có stock=0 trước nhánh MATCHED tổng quát.

### Bài 6 — DO NOTHING

Viết MERGE chỉ cập nhật SKU đã có, bỏ qua SKU chưa có.

**Gợi ý:** không cần nhánh NOT MATCHED hoặc dùng DO NOTHING.

### Bài 7 — DELETE matched

Viết nhánh xóa target khi source operation='REMOVE'.

**Gợi ý:** `WHEN MATCHED AND s.operation='REMOVE' THEN DELETE`.

### Bài 8 — Vô hiệu hóa logic

Thay vì hard delete, cập nhật `is_active=FALSE`.

**Gợi ý:** WHEN MATCHED ... THEN UPDATE SET is_active=FALSE.

### Bài 9 — NULL

Cột description nullable. So sánh nào phát hiện cả thay đổi NULL → chuỗi và chuỗi → NULL?

**Gợi ý:** `IS DISTINCT FROM`.

### Bài 10 — Duplicate source

Hai hàng nguồn cùng A100 với stock khác nhau sẽ gây rủi ro gì cho MERGE UPDATE?

**Gợi ý:** cardinality violation khi cùng target bị sửa nhiều lần.

### Bài 11 — Deduplicate

Hãy dùng `DISTINCT ON(sku)` chọn source version cao nhất và nêu rủi ro nếu cùng version có nhiều bản ghi khác nhau.

**Gợi ý:** ORDER BY với tie-breaker, hoặc từ chối dữ liệu mơ hồ.

### Bài 12 — Khóa target

Target cho phép hai hàng cùng SKU, source có một hàng. MERGE có chắc chỉ tác động một target không?

**Gợi ý:** không; cần PK/UNIQUE phù hợp.

### Bài 13 — Staging

Vì sao `PRIMARY KEY(batch_id,sku)` hợp lý cho bảng feed?

**Gợi ý:** một SKU duy nhất trong batch, vẫn tồn tại ở nhiều batch.

### Bài 14 — Source delta

Một batch chỉ gồm 10 SKU mới thay đổi. Dùng BY SOURCE DELETE để dọn những SKU vắng mặt có an toàn không?

**Gợi ý:** không; delta không phải snapshot đầy đủ.

### Bài 15 — PostgreSQL 17+

Viết nhánh vô hiệu hóa target-only row khi snapshot đã được xác minh.

**Gợi ý:** `WHEN NOT MATCHED BY SOURCE AND t.is_active THEN UPDATE SET is_active=FALSE`.

### Bài 16 — BY TARGET

Phân biệt source-only và target-only, và cú pháp tương ứng trên PostgreSQL 17+.

**Gợi ý:** BY TARGET là source-only, BY SOURCE là target-only.

### Bài 17 — RETURNING

Trên PG17+, dùng gì để biết hàng nào INSERT hay UPDATE?

**Gợi ý:** `RETURNING merge_action(), t.sku`.

### Bài 18 — PostgreSQL 16

Có thể dùng `MERGE RETURNING` không?

**Gợi ý:** không.

### Bài 19 — OLD/NEW

Trên PG18+, làm sao trả stock trước và sau UPDATE trong MERGE?

**Gợi ý:** `old.stock` và `new.stock` trong RETURNING.

### Bài 20 — UPSERT so với MERGE

Một API có nhiều writer chỉ cần insert hoặc update theo unique SKU. Nên cân nhắc công cụ nào?

**Gợi ý:** `INSERT ... ON CONFLICT DO UPDATE`.

### Bài 21 — Concurrent insert

Hai MERGE cùng thấy E500 chưa có. Có bảo đảm cả hai thành công không?

**Gợi ý:** không; một lệnh có thể gặp unique violation.

### Bài 22 — Constraint

Nguồn có stock=-5 nhưng target `CHECK(stock>=0)`. MERGE có bỏ qua CHECK được không?

**Gợi ý:** không.

### Bài 23 — EXPLAIN

Vì sao `EXPLAIN ANALYZE MERGE` có thể nguy hiểm trên production?

**Gợi ý:** nó thực thi DML.

### Bài 24 — Index

Bảng product đã có PRIMARY KEY(sku). Có nên tạo B-tree trùng trên sku chỉ để MERGE không?

**Gợi ý:** thường không cần.

### Bài 25 — Idempotency

Vì sao `SET stock=t.stock+s.delta` có thể sai nếu batch retry?

**Gợi ý:** delta bị cộng lại.

### Bài 26 — Transaction lỗi

Khi MERGE lỗi trong transaction explicit, có thể tiếp tục statement khác ngay không?

**Gợi ý:** cần ROLLBACK hoặc rollback tới savepoint hợp lệ.

### Bài 27 — Privileges

Role chỉ có UPDATE nhưng MERGE khai báo nhánh INSERT và DELETE. Có thể chạy vì batch dự kiến toàn UPDATE không?

**Gợi ý:** quyền kiểm tra theo các hành động được khai báo trong statement.

### Bài 28 — Trigger

MERGE có nhánh INSERT nhưng batch không có hàng nào chèn. Statement-level INSERT trigger có thể chạy không?

**Gợi ý:** có thể; khác row-level INSERT trigger.

### Bài 29 — Preview

Hãy viết SELECT với CASE phân loại source thành would_insert, would_update, would_skip.

**Gợi ý:** LEFT JOIN target, so version.

### Bài 30 — Multi-tenant

Hai tenant đều có SKU A100. Vì sao ON chỉ theo SKU là sai?

**Gợi ý:** cần tenant_id + SKU và scope quyền.

### Bài 31 — Snapshot rỗng

Job import lỗi nhưng báo source 0 hàng. Có nên chạy BY SOURCE DELETE không?

**Gợi ý:** không; cần xác thực completeness.

### Bài 32 — Command tag

`MERGE 2` có nghĩa source có 2 hàng không?

**Gợi ý:** không; số hàng thay đổi.

## 39. Tổng kết

- **MERGE có từ PostgreSQL 15**, dùng `MERGE INTO ... USING ... ON ...` cùng các nhánh `WHEN` để thay đổi dữ liệu theo trạng thái khớp.
- `ON` là **điều kiện nhận diện**, không phải nơi đặt mọi filter trạng thái; điều kiện lựa chọn hành động thuộc `WHEN ... AND`.
- `WHEN MATCHED` xử lý hàng có cả source và target; `WHEN NOT MATCHED` xử lý source-only.
- **PostgreSQL 17+** bổ sung `WHEN NOT MATCHED BY SOURCE`, cách viết rõ `BY TARGET` và `MERGE RETURNING`/`merge_action()`.
- **PostgreSQL 18+** bổ sung tham chiếu `OLD`/`NEW` trong RETURNING.
- Các nhánh `WHEN` được xét **theo thứ tự** và chỉ một nhánh được thực hiện cho mỗi candidate row.
- **Duplicate source** có thể gây cardinality/unique violations; khóa target và staging cần được thiết kế rõ.
- **BY SOURCE chỉ an toàn với source snapshot đầy đủ** đã được xác minh và giới hạn phạm vi. Không dùng để xóa target khi nguồn là delta.
- `MERGE` vẫn tuân thủ `CHECK`, `UNIQUE`, `FOREIGN KEY`, triggers, quyền và transaction rules.
- `MERGE` **không giống `INSERT ... ON CONFLICT` về concurrency**. Unique constraints, retry, isolation và idempotency vẫn cần thiết.
- Preview, staging, index, EXPLAIN, audit và đối soát là những bước quan trọng trước khi xử lý dữ liệu lớn.
- Đối với cập nhật đơn giản, `UPDATE` hoặc UPSERT có thể dễ hiểu hơn; chọn MERGE khi logic khớp và nhiều hành động thật sự cần nó.

Điểm mấu chốt của MERGE là tách bạch hai câu hỏi: **“Source và target có phải cùng một đối tượng theo khóa ON?”** và **“Với trạng thái khớp đó, hành động nào được phép theo chính sách?”**. Khi hai câu hỏi được định nghĩa đúng, PostgreSQL cho phép tổ chức việc đồng bộ dữ liệu nhiều nhánh trong một câu lệnh rõ ràng và dễ kiểm soát.

## Tham khảo chính thức

- [PostgreSQL 15 — MERGE](https://www.postgresql.org/docs/15/sql-merge.html): cú pháp cơ bản.
- [PostgreSQL 17 — MERGE](https://www.postgresql.org/docs/17/sql-merge.html): BY SOURCE/BY TARGET, RETURNING.
- [PostgreSQL 18 — MERGE](https://www.postgresql.org/docs/18/sql-merge.html): các tính năng mới hơn, OLD/NEW trong RETURNING.
- [PostgreSQL 18 — Merge support functions](https://www.postgresql.org/docs/18/functions-merge-support.html): `merge_action()`.
