# UPDATE FROM và nguy cơ nhiều hàng nguồn khớp một hàng đích trong PostgreSQL

Trong hệ thống bán hàng, giá sản phẩm có thể được cập nhật từ bảng nhập giá mới; số lượng tồn kho được tổng hợp từ nhiều giao dịch; trạng thái đơn hàng được cập nhật từ những sự kiện thanh toán. PostgreSQL hỗ trợ cú pháp **`UPDATE ... FROM`** để lấy dữ liệu từ một hoặc nhiều bảng nguồn khi thay đổi bảng đích. Cú pháp này gọn và mạnh, nhưng có một rủi ro quan trọng: **nếu cùng một hàng đích khớp nhiều hàng nguồn, PostgreSQL không đảm bảo sẽ chọn hàng nguồn nào để lấy giá trị cho phép cập nhật**.

Ví dụ, bảng sản phẩm có SKU `BK-01`, còn bảng giá nhập có hai đề xuất cho cùng SKU: `110000` và `115000`. Câu lệnh `UPDATE products SET price = feed.new_price FROM price_feed AS feed WHERE products.sku = feed.sku` có thể thay giá bằng một trong hai đề xuất. Kết quả thực tế phụ thuộc cách thực thi truy vấn, **không phải quy tắc “hàng mới nhất thắng”** nếu bạn chưa diễn đạt quy tắc ấy trong SQL.

Bài này tập trung vào:

1. Cú pháp và ngữ nghĩa của `UPDATE ... FROM` trong PostgreSQL.
2. Cách nhận biết quan hệ **một–một**, **nhiều–một** và **một hàng đích khớp nhiều hàng nguồn**.
3. Vì sao `RETURNING` hoặc `ORDER BY` tùy tiện không biến một phép cập nhật mơ hồ thành đúng.
4. Các chiến lược sửa: **`GROUP BY`**, **`DISTINCT ON` có thứ tự quyết định duy nhất**, **`ROW_NUMBER()`**, **scalar subquery**, **staging table có `UNIQUE`**.
5. Xử lý nguồn không khớp, giá trị `NULL`, duplicate từ join nhiều bảng, transaction, đồng thời, hiệu năng và kiểm tra tác động trước khi ghi.

Ví dụ được viết cho PostgreSQL hiện đại, có dữ liệu tự tạo trong schema thực hành. Những lệnh có thể thay đổi dữ liệu được bao bằng transaction và `ROLLBACK` khi mục tiêu chỉ là quan sát. **Không thực hành trực tiếp trên bảng production.**

## 1. Mục tiêu học tập

Sau bài học, bạn cần có thể:

- Đọc được cấu trúc `UPDATE target AS t SET ... FROM source AS s WHERE ...` và phân biệt phần `SET` với phần chọn hàng nguồn.
- Giải thích vì sao **mỗi hàng đích phải khớp nhiều nhất một hàng nguồn có ý nghĩa** nếu muốn giá trị cập nhật không mơ hồ.
- Phát hiện trước các SKU/ID bị khớp nhiều lần bằng `SELECT` và `GROUP BY ... HAVING COUNT(*) > 1`.
- Chọn đúng hàng nguồn theo quy tắc **mới nhất, ưu tiên cao nhất, trạng thái hợp lệ** và dùng khóa phụ để giải quyết hòa (*tie-breaker*).
- Biết tại sao `DISTINCT` đơn thuần, `MAX(price)` hoặc `LIMIT 1` thiếu thứ tự rõ ràng thường không giải quyết đúng vấn đề.
- So sánh `UPDATE ... FROM` với **scalar subquery** khi nguồn trả 0, 1 hoặc nhiều hàng.
- Biết cách dùng `RETURNING`, transaction và staging để làm thay đổi dữ liệu có thể kiểm tra được.
- Nhận diện những tình huống cần index, unique constraint, kiểm soát concurrent writes hoặc thay đổi mô hình dữ liệu.

## 2. Cú pháp tổng quát của UPDATE FROM

Mẫu căn bản:

~~~sql
UPDATE target_table AS t
SET target_column = s.source_value
FROM source_table AS s
WHERE t.business_key = s.business_key;
~~~

Vai trò của từng phần:

| Thành phần | Ý nghĩa |
| --- | --- |
| `UPDATE target_table AS t` | Xác định bảng **bị ghi thay đổi** |
| `SET target_column = ...` | Xác định giá trị mới của cột đích |
| `FROM source_table AS s` | Cung cấp bảng/quan hệ **nguồn dữ liệu** cho biểu thức và điều kiện |
| `WHERE t.key = s.key` | Liên kết hàng đích với hàng nguồn; đồng thời quyết định hàng đích được cập nhật |
| `RETURNING ...` | Trả thông tin những hàng được cập nhật |

### 2.1. Khác SELECT JOIN ở điểm nào?

Truy vấn `SELECT ... JOIN` có thể trả **nhiều hàng kết quả** cho cùng một hàng ở bảng bên trái nếu có nhiều bản ghi khớp. Trong `UPDATE ... FROM`, PostgreSQL xây kết quả join phục vụ việc cập nhật; nếu join tạo nhiều hàng cho cùng một hàng đích, **một hàng join được dùng** để cung cấp giá trị cho hàng đích, nhưng PostgreSQL **không hứa hẹn hàng nào được chọn**.

~~~text
Bảng đích products                 Bảng nguồn price_feed
-------------------------          ------------------------------
SKU = BK-01 | price=100000          SKU=BK-01 | new_price=110000
                                    SKU=BK-01 | new_price=115000

Kết quả JOIN:
    BK-01 + 110000
    BK-01 + 115000
          |
          v
UPDATE chỉ nhận một hàng nguồn cho BK-01,
nhưng không có quy tắc đảm bảo chọn 110000 hay 115000.
~~~

**Không diễn giải đây là hai lần cập nhật nối tiếp cùng một sản phẩm.** Tài liệu PostgreSQL lưu ý rằng trong trường hợp nhiều hàng join khớp một hàng đích, chỉ **một** hàng join được sử dụng để cập nhật hàng đích và việc chọn hàng không thể dự đoán ổn định. Khi xây hệ thống nghiệp vụ, coi trường hợp này là **sai thiết kế truy vấn** cho đến khi xác định được nguồn duy nhất.

### 2.2. Không nên nghĩ PostgreSQL sẽ chọn “hàng cuối”

Những giả định nguy hiểm:

- “Bảng nguồn chèn hàng mới sau nên `UPDATE` chọn hàng mới.”
- “`feed_id` lớn hơn nên được lấy tự động.”
- “Trong `SELECT` thử nghiệm dòng này xuất hiện trước nên `UPDATE` sẽ dùng nó.”
- “Tạo thêm index sẽ làm thứ tự chọn ổn định.”
- “Tôi chạy ba lần đều ra một giá, vậy hành vi được bảo đảm.”

Không giả định nào trong số đó là **hợp đồng ngữ nghĩa** của `UPDATE ... FROM` khi có nhiều hàng nguồn khớp. PostgreSQL có thể chọn kế hoạch thực thi khác do dữ liệu, thống kê, index hoặc phiên bản server thay đổi.

### 2.3. Điều kiện WHERE là phần bắt buộc phải cân nhắc

Trong PostgreSQL, `UPDATE` có thể không cần `WHERE` về mặt cú pháp. Nhưng nếu bỏ hoặc viết sai điều kiện nối, bạn có thể cập nhật **rất nhiều hàng đích ngoài ý muốn**:

~~~sql
-- CẢNH BÁO: ví dụ không có điều kiện nối đúng.
-- Không chạy trên dữ liệu thực.
--
-- UPDATE products AS p
-- SET unit_price = f.new_price
-- FROM price_feed AS f;
~~~

Câu này không nối `p.sku` với `f.sku`; nó tạo quan hệ kiểu cross join giữa bảng đích và nguồn và có thể gây cập nhật với giá trị tùy ý. `FROM` **không tự hiểu khóa nào cần dùng để ghép**.

## 3. Tạo bộ dữ liệu thực hành

Ta mô phỏng một ứng dụng đồng bộ **giá sản phẩm hiện hành** từ các bản ghi đề xuất giá. Mỗi sản phẩm có một SKU duy nhất; mỗi SKU có thể nhận nhiều đề xuất giá theo thời gian.

Chạy trên database lab có quyền tạo schema. Nếu `upd_lab_201` đã tồn tại và có dữ liệu, hãy dùng tên schema khác thay vì xóa dữ liệu sẵn có.

### 3.1. Bảng đích: products

~~~sql
CREATE SCHEMA upd_lab_201;

CREATE TABLE upd_lab_201.products (
    product_id BIGINT PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    product_name TEXT NOT NULL,
    unit_price NUMERIC(12, 2) NOT NULL
        CHECK (unit_price >= 0),
    status TEXT NOT NULL DEFAULT 'ACTIVE'
        CHECK (status IN ('ACTIVE', 'INACTIVE')),
    price_source_note TEXT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

`sku` là khóa nghiệp vụ dùng để ghép dữ liệu. `UNIQUE(sku)` đảm bảo một mã SKU chỉ ứng với một sản phẩm đích trong bảng này.

~~~sql
INSERT INTO upd_lab_201.products
    (product_id, sku, product_name, unit_price)
VALUES
    (1, 'BK-01',    'Sách PostgreSQL',    100000),
    (2, 'MOUSE-01', 'Chuột không dây',    250000),
    (3, 'PEN-01',   'Bút bi',              15000),
    (4, 'CABLE-01', 'Cáp USB-C',          120000),
    (5, 'BAG-01',   'Ba lô',              200000);
~~~

### 3.2. Bảng nguồn: price_feed

~~~sql
CREATE TABLE upd_lab_201.price_feed (
    feed_id BIGINT PRIMARY KEY,
    sku TEXT NOT NULL,
    new_price NUMERIC(12, 2) NOT NULL
        CHECK (new_price >= 0),
    feed_at TIMESTAMPTZ NOT NULL,
    provider TEXT NOT NULL,
    is_approved BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX idx_price_feed_sku_approved_time
ON upd_lab_201.price_feed
    (sku, feed_at DESC, feed_id DESC)
WHERE is_approved;
~~~

Không khai báo `UNIQUE(sku)` ở bảng feed vì **nhiều lần đề xuất giá cho cùng SKU là dữ liệu hợp lệ**. Cũng không tạo FK từ `price_feed.sku` tới `products.sku` để có thể quan sát trường hợp nguồn chứa SKU chưa có ở đích.

### 3.3. Nạp các bản ghi đề xuất giá

~~~sql
INSERT INTO upd_lab_201.price_feed
    (
        feed_id, sku, new_price, feed_at,
        provider, is_approved
    )
VALUES
    (
        101, 'BK-01', 110000,
        TIMESTAMPTZ '2026-11-11 09:00:00+07',
        'VENDOR-A', TRUE
    ),
    (
        102, 'BK-01', 115000,
        TIMESTAMPTZ '2026-11-12 09:00:00+07',
        'VENDOR-B', TRUE
    ),
    (
        103, 'MOUSE-01', 270000,
        TIMESTAMPTZ '2026-11-12 11:00:00+07',
        'VENDOR-A', TRUE
    ),
    (
        104, 'PEN-01', 16000,
        TIMESTAMPTZ '2026-11-12 12:00:00+07',
        'VENDOR-A', FALSE
    ),
    (
        105, 'CABLE-01', 130000,
        TIMESTAMPTZ '2026-11-13 09:00:00+07',
        'VENDOR-A', TRUE
    ),
    (
        106, 'CABLE-01', 125000,
        TIMESTAMPTZ '2026-11-13 09:00:00+07',
        'VENDOR-B', TRUE
    ),
    (
        107, 'UNKNOWN-01', 90000,
        TIMESTAMPTZ '2026-11-13 15:00:00+07',
        'VENDOR-A', TRUE
    ),
    (
        108, 'MOUSE-01', 265000,
        TIMESTAMPTZ '2026-11-10 09:00:00+07',
        'VENDOR-B', TRUE
    );
~~~

Bộ dữ liệu được cố tình thiết kế để xuất hiện nhiều loại tình huống:

| SKU | Hàng feed | Đặc điểm |
| --- | --- | --- |
| `BK-01` | 101, 102 | **Hai hàng đã duyệt**, timestamp khác nhau |
| `MOUSE-01` | 103, 108 | **Hai hàng đã duyệt**, giá mới nhất khác giá cũ |
| `CABLE-01` | 105, 106 | Hai hàng đã duyệt **cùng timestamp**, cần tie-break |
| `PEN-01` | 104 | Chỉ có đề xuất **chưa được duyệt** |
| `BAG-01` | Không có | Sản phẩm **không có hàng nguồn** |
| `UNKNOWN-01` | 107 | Nguồn có SKU **không tồn tại ở đích** |

### 3.4. Xem dữ liệu trước khi cập nhật

~~~sql
SELECT
    product_id, sku, unit_price, price_source_note
FROM upd_lab_201.products
ORDER BY product_id;
~~~

Kỳ vọng:

| ID | SKU | Giá hiện tại |
| ---: | --- | ---: |
| 1 | BK-01 | 100.000 |
| 2 | MOUSE-01 | 250.000 |
| 3 | PEN-01 | 15.000 |
| 4 | CABLE-01 | 120.000 |
| 5 | BAG-01 | 200.000 |

Mọi `price_source_note` ban đầu đều `NULL`.

## 4. Một ví dụ UPDATE FROM đúng khi nguồn duy nhất

Giả sử chỉ cập nhật từ một hàng feed xác định:

~~~sql
BEGIN;

UPDATE upd_lab_201.products AS p
SET
    unit_price = f.new_price,
    price_source_note = 'feed=' || f.feed_id::text,
    updated_at = clock_timestamp()
FROM upd_lab_201.price_feed AS f
WHERE p.sku = f.sku
  AND f.feed_id = 103
  AND f.is_approved
RETURNING
    p.product_id,
    p.sku,
    p.unit_price,
    f.feed_id AS chosen_feed_id;

ROLLBACK;
~~~

Ở đây `feed_id` là khóa chính. `f.feed_id=103` xác định **đúng một** hàng nguồn, trỏ tới `MOUSE-01` với giá `270000`. Câu lệnh cập nhật **một** hàng đích trong transaction, rồi `ROLLBACK` để bảo toàn dữ liệu mẫu.

**Điểm cần học:** `UPDATE ... FROM` không sai về bản chất. Nó hoạt động rõ ràng khi điều kiện nối tạo **tối đa một hàng nguồn cho mỗi hàng đích** hoặc khi bạn đã chủ động đưa nguồn về quan hệ duy nhất.

## 5. Ví dụ nguy hiểm: nhiều hàng feed khớp cùng một sản phẩm

Xét câu sau:

~~~sql
BEGIN;

UPDATE upd_lab_201.products AS p
SET
    unit_price = f.new_price,
    price_source_note = 'feed=' || f.feed_id::text
FROM upd_lab_201.price_feed AS f
WHERE p.sku = f.sku
  AND f.is_approved
RETURNING
    p.product_id,
    p.sku,
    p.unit_price,
    f.feed_id AS chosen_feed_id;

-- Chỉ xem kết quả trong transaction, không commit ví dụ mơ hồ.
ROLLBACK;
~~~

Vấn đề:

- `BK-01` khớp hai hàng `101`/`102`, giá `110000`/`115000`.
- `MOUSE-01` khớp hai hàng `103`/`108`, giá `270000`/`265000`.
- `CABLE-01` khớp hai hàng `105`/`106`, giá `130000`/`125000`.

PostgreSQL **không bảo đảm** sẽ dùng feed mới nhất, ID lớn nhất hay giá lớn nhất. `RETURNING f.feed_id` giúp **quan sát hàng nguồn được dùng ở lần chạy đó**, không biến sự lựa chọn thành quy tắc ổn định.

### 5.1. Ba hàng đích, sáu hàng ghép

Trước khi chạy `UPDATE`, xem tập join:

~~~sql
SELECT
    p.product_id,
    p.sku,
    p.unit_price AS old_price,
    f.feed_id,
    f.new_price,
    f.feed_at
FROM upd_lab_201.products AS p
JOIN upd_lab_201.price_feed AS f
    ON f.sku = p.sku
WHERE f.is_approved
ORDER BY p.product_id, f.feed_at DESC, f.feed_id DESC;
~~~

Kết quả có **6 hàng join** cho **3 sản phẩm đích**:

| Sản phẩm | Hàng feed khớp |
| --- | --- |
| BK-01 | 102, 101 |
| MOUSE-01 | 103, 108 |
| CABLE-01 | 106, 105 |

`PEN-01` không khớp vì chỉ có đề xuất chưa duyệt; `BAG-01` không có feed; `UNKNOWN-01` không có sản phẩm đích.

### 5.2. Đừng nhầm số hàng join với số hàng cập nhật

Nếu `SELECT ... JOIN` trả sáu hàng, điều đó **không có nghĩa** PostgreSQL sẽ cập nhật sáu sản phẩm. Ba SKU đích có nguồn khớp nên ba hàng sản phẩm có thể được cập nhật; sự mơ hồ nằm ở **giá trị từ hàng feed nào được dùng cho mỗi hàng sản phẩm**.

Nếu có ràng buộc, trigger hoặc biểu thức phức tạp trong `SET`, việc không chắc nguồn nào được chọn còn nguy hiểm hơn việc chỉ chọn sai giá: nó có thể dẫn tới metadata, thời điểm hoặc log nghiệp vụ không đúng.

### 5.3. Số lần chạy ra cùng kết quả không chứng minh an toàn

Không nên cố “sửa” bằng cách chạy lại đến khi giá trị mong muốn xuất hiện. Thứ tự vật lý, thứ tự chèn, index và kế hoạch thực thi **không phải hợp đồng lựa chọn hàng nguồn**. Câu lệnh phải có quy tắc xác định được một winner trước khi ghi.

## 6. Kiểm tra nguy cơ trước khi UPDATE

Một bước preflight quan trọng là **chạy `SELECT` tái tạo đúng join và filter dự định dùng trong UPDATE**, rồi kiểm tra số hàng nguồn cho mỗi khóa đích.

~~~sql
SELECT
    p.product_id,
    p.sku,
    COUNT(*) AS matching_source_rows,
    ARRAY_AGG(f.feed_id ORDER BY f.feed_at DESC, f.feed_id DESC)
        AS feed_ids
FROM upd_lab_201.products AS p
JOIN upd_lab_201.price_feed AS f
    ON f.sku = p.sku
WHERE f.is_approved
GROUP BY p.product_id, p.sku
HAVING COUNT(*) > 1
ORDER BY p.product_id;
~~~

Kết quả:

| product_id | sku | matching_source_rows | feed_ids |
| ---: | --- | ---: | --- |
| 1 | BK-01 | 2 | `{102,101}` |
| 2 | MOUSE-01 | 2 | `{103,108}` |
| 4 | CABLE-01 | 2 | `{106,105}` |

**Cách kiểm tra này đặc biệt quan trọng trong quy trình ETL/migration**, vì một bảng nguồn “trông như mỗi mã chỉ có một hàng” có thể đã tích lũy nhiều phiên bản theo thời gian.

### 6.1. Kiểm tra toàn bộ số khớp kể cả 0

~~~sql
SELECT
    p.product_id,
    p.sku,
    COUNT(f.feed_id) AS approved_feed_rows
FROM upd_lab_201.products AS p
LEFT JOIN upd_lab_201.price_feed AS f
    ON f.sku = p.sku
   AND f.is_approved
GROUP BY p.product_id, p.sku
ORDER BY p.product_id;
~~~

| sku | approved_feed_rows |
| --- | ---: |
| BK-01 | 2 |
| MOUSE-01 | 2 |
| PEN-01 | 0 |
| CABLE-01 | 2 |
| BAG-01 | 0 |

Ở `LEFT JOIN`, phải dùng `COUNT(f.feed_id)` hoặc một cột nguồn **NOT NULL khi hàng nguồn tồn tại**. Nếu dùng `COUNT(*)`, những sản phẩm không có feed vẫn có thể cho kết quả **1** vì outer join sinh ra một hàng phía nguồn toàn NULL.

### 6.2. Đếm theo khóa nguồn trước khi join

Nếu đã chắc bảng sản phẩm có `sku UNIQUE`, có thể xem duplicate ngay trong bảng feed:

~~~sql
SELECT
    sku,
    COUNT(*) AS approved_rows
FROM upd_lab_201.price_feed
WHERE is_approved
GROUP BY sku
HAVING COUNT(*) > 1
ORDER BY sku;
~~~

Nhưng trong truy vấn thật có **nhiều bảng nguồn**, việc kiểm tra riêng từng bảng chưa chắc đủ. Một join tới bảng phụ có quan hệ 1:N có thể **nhân số hàng** dù bảng feed đã có một hàng cho mỗi SKU. Cần kiểm tra **quan hệ nguồn cuối cùng** mà `UPDATE` sử dụng.

### 6.3. Kiểm tra giá trị chứ không chỉ số lượng

~~~sql
SELECT
    sku,
    COUNT(*) AS rows_count,
    COUNT(DISTINCT new_price) AS distinct_prices,
    MIN(new_price) AS min_price,
    MAX(new_price) AS max_price
FROM upd_lab_201.price_feed
WHERE is_approved
GROUP BY sku
ORDER BY sku;
~~~

Hai hàng nguồn có **cùng giá tiền** vẫn là hai hàng nguồn khớp. Chúng có thể không tạo khác biệt ở `unit_price`, nhưng `feed_id`, `provider` hoặc các thuộc tính khác có thể khác. Do đó **`COUNT(DISTINCT new_price)=1` không chứng minh join là một–một**.

## 7. Định nghĩa một quy tắc chọn nguồn minh bạch

Với dữ liệu lab, ta chọn quy tắc nghiệp vụ:

> Trong số các đề xuất **đã duyệt** của cùng SKU, lấy đề xuất có `feed_at` mới nhất; nếu nhiều đề xuất cùng thời điểm, chọn `feed_id` lớn nhất.

Quy tắc này tạo **thứ tự toàn phần** trên mỗi SKU của nguồn vì `feed_id` là khóa chính và `feed_at` không NULL. Hai hàng có cùng `feed_at` vẫn được phân xử bằng `feed_id`.

Kết quả winner mong đợi:

| SKU | feed_id được chọn | new_price | Lý do |
| --- | ---: | ---: | --- |
| BK-01 | 102 | 115.000 | Timestamp mới hơn 101 |
| MOUSE-01 | 103 | 270.000 | Timestamp mới hơn 108 |
| CABLE-01 | 106 | 125.000 | Cùng timestamp với 105, ID cao hơn |
| UNKNOWN-01 | 107 | 90.000 | Winner nguồn nhưng không có sản phẩm đích |

`PEN-01` không có nguồn đã duyệt, `BAG-01` không có nguồn. Hai sản phẩm này sẽ **không bị cập nhật** theo quy tắc `UPDATE ... FROM` với `INNER JOIN` tương ứng.

### 7.1. Vì sao cần tie-breaker?

Nếu chỉ ghi:

~~~sql
ORDER BY sku, feed_at DESC
~~~

thì ở `CABLE-01` hai hàng nguồn có timestamp bằng nhau. Một cách chọn “hàng đầu” chưa thêm tie-breaker **chưa xác định duy nhất winner** theo nghiệp vụ. Với yêu cầu tái lập (*reproducibility*), hãy thêm `feed_id DESC` hoặc một thuộc tính được nghiệp vụ xác nhận có độ ưu tiên rõ ràng.

**ID lớn nhất ở đây chỉ là tie-breaker được chọn cho bài lab**, không phải quy luật bắt buộc trong mọi hệ thống. Nếu nguồn có phiên bản sửa đổi, độ ưu tiên nhà cung cấp hay trạng thái phê duyệt khác, cần thống nhất quy tắc winner phù hợp.

## 8. Cách 1: DISTINCT ON chọn đúng một nguồn cho mỗi SKU

PostgreSQL hỗ trợ `DISTINCT ON (key)`: giữ **hàng đầu tiên** của mỗi nhóm khóa theo `ORDER BY` đi kèm. Nó đặc biệt tiện cho bài toán **latest row per group**.

### 8.1. Xem winner trước khi update

~~~sql
SELECT DISTINCT ON (f.sku)
    f.sku,
    f.feed_id,
    f.new_price,
    f.feed_at,
    f.provider
FROM upd_lab_201.price_feed AS f
WHERE f.is_approved
ORDER BY
    f.sku,
    f.feed_at DESC,
    f.feed_id DESC;
~~~

Với `DISTINCT ON (f.sku)`, PostgreSQL giữ một hàng cho mỗi SKU. **`ORDER BY` phải bắt đầu bằng các biểu thức `DISTINCT ON`**, rồi mới dùng `feed_at DESC`, `feed_id DESC` để xác định winner trong nhóm.

### 8.2. UPDATE FROM trên nguồn đã khử đa trị

~~~sql
BEGIN;

WITH latest_approved AS (
    SELECT DISTINCT ON (f.sku)
        f.sku,
        f.feed_id,
        f.new_price,
        f.feed_at,
        f.provider
    FROM upd_lab_201.price_feed AS f
    WHERE f.is_approved
    ORDER BY
        f.sku,
        f.feed_at DESC,
        f.feed_id DESC
)
UPDATE upd_lab_201.products AS p
SET
    unit_price = s.new_price,
    price_source_note = 'feed=' || s.feed_id::text,
    updated_at = clock_timestamp()
FROM latest_approved AS s
WHERE p.sku = s.sku
RETURNING
    p.product_id,
    p.sku,
    p.unit_price,
    p.price_source_note,
    s.feed_id AS chosen_feed_id;

-- Kiểm tra trong transaction rồi hoàn tác ví dụ.
ROLLBACK;
~~~

**Ba sản phẩm đích** có approved source sẽ được cập nhật theo winner:

| SKU | Giá sau UPDATE trong transaction | feed_id |
| --- | ---: | ---: |
| BK-01 | 115.000 | 102 |
| MOUSE-01 | 270.000 | 103 |
| CABLE-01 | 125.000 | 106 |

`PEN-01` và `BAG-01` giữ nguyên; `UNKNOWN-01` không tạo sản phẩm mới vì `UPDATE` chỉ thay đổi hàng đã có trong bảng đích.

### 8.3. DISTINCT ON không giống DISTINCT

~~~sql
SELECT DISTINCT sku, new_price
FROM upd_lab_201.price_feed
WHERE is_approved;
~~~

`DISTINCT sku, new_price` loại những hàng giống nhau **ở cả hai cột**, nhưng với `BK-01` có giá `110000` và `115000`, hai hàng **khác nhau**, nên cả hai vẫn tồn tại. Vì vậy:

- `DISTINCT` **không đảm bảo** duy nhất `sku` khi có nhiều giá khác nhau.
- `DISTINCT ON (sku)` chỉ giữ một hàng cho mỗi SKU, nhưng muốn **đúng winner** phải đi kèm `ORDER BY` đầy đủ.

### 8.4. ORDER BY không tạo tie-breaker tự động

Nếu thiếu `feed_id DESC`, hàng `CABLE-01` còn mơ hồ về mặt ưu tiên. `DISTINCT ON` vẫn giữ một hàng, nhưng **không đảm bảo đó là hàng nghiệp vụ bạn muốn**. Một truy vấn chỉ trả một hàng **chưa đủ**; cách chọn hàng đó cũng phải được xác định.

## 9. Cách 2: ROW_NUMBER() và lọc rn = 1

Window function `ROW_NUMBER()` đánh số các hàng trong từng nhóm, cho phép chọn winner theo thứ tự mong muốn.

### 9.1. Phân hạng nguồn trước

~~~sql
SELECT
    f.sku,
    f.feed_id,
    f.new_price,
    f.feed_at,
    ROW_NUMBER() OVER (
        PARTITION BY f.sku
        ORDER BY f.feed_at DESC, f.feed_id DESC
    ) AS rn
FROM upd_lab_201.price_feed AS f
WHERE f.is_approved
ORDER BY f.sku, rn;
~~~

Mỗi SKU có hàng `rn=1` là winner. `PARTITION BY sku` chia nguồn thành các nhóm; `ORDER BY feed_at DESC, feed_id DESC` thiết lập ưu tiên trong mỗi nhóm.

### 9.2. UPDATE dùng winner đã lọc

~~~sql
BEGIN;

WITH ranked AS (
    SELECT
        f.sku,
        f.feed_id,
        f.new_price,
        f.provider,
        ROW_NUMBER() OVER (
            PARTITION BY f.sku
            ORDER BY f.feed_at DESC, f.feed_id DESC
        ) AS rn
    FROM upd_lab_201.price_feed AS f
    WHERE f.is_approved
),
winner AS (
    SELECT
        sku, feed_id, new_price, provider
    FROM ranked
    WHERE rn = 1
)
UPDATE upd_lab_201.products AS p
SET
    unit_price = w.new_price,
    price_source_note = 'feed=' || w.feed_id::text,
    updated_at = clock_timestamp()
FROM winner AS w
WHERE p.sku = w.sku
RETURNING
    p.product_id,
    p.sku,
    p.unit_price,
    w.feed_id AS chosen_feed_id;

ROLLBACK;
~~~

Kết quả winner giống cách `DISTINCT ON`: 102, 103, 106 ở ba sản phẩm đích.

### 9.3. ROW_NUMBER khác RANK hoặc DENSE_RANK

Khi hai hàng cùng `feed_at`:

~~~sql
SELECT
    sku,
    feed_id,
    feed_at,
    ROW_NUMBER() OVER (
        PARTITION BY sku
        ORDER BY feed_at DESC
    ) AS row_number_by_time,
    RANK() OVER (
        PARTITION BY sku
        ORDER BY feed_at DESC
    ) AS rank_by_time
FROM upd_lab_201.price_feed
WHERE is_approved
ORDER BY sku, feed_id;
~~~

Với `CABLE-01`, hai hàng cùng timestamp có thể cùng `RANK() = 1`. Do đó **lọc `RANK()=1` không đảm bảo một hàng nguồn cho mỗi SKU** khi có tie. `ROW_NUMBER()=1` chọn một hàng, nhưng nếu thứ tự chỉ gồm timestamp trùng nhau, winner vẫn không có tie-breaker ổn định.

**Cách đúng:** sử dụng `ROW_NUMBER()` và `ORDER BY ... feed_id DESC` (hoặc quy tắc tie-break đầy đủ).

### 9.4. Khi nào dùng DISTINCT ON hay ROW_NUMBER?

| Tình huống | Công cụ thuận tiện |
| --- | --- |
| PostgreSQL, chỉ cần một hàng mới nhất mỗi SKU | `DISTINCT ON` thường ngắn gọn |
| Cần top-N mỗi nhóm | `ROW_NUMBER`, lọc `rn <= N` |
| Cần thấy thứ hạng và giải thích tie | Window functions |
| Muốn cú pháp dễ chuyển giữa nhiều DBMS | `ROW_NUMBER()` thường phổ biến hơn `DISTINCT ON` |
| Cần bảo đảm một hàng winner | Cả hai **khi thứ tự quyết định đầy đủ** |

Không nên chọn chỉ vì một cú pháp “nhanh hơn” trong mọi trường hợp. Hãy đo trên dữ liệu thật; index và cách PostgreSQL thực thi sort/window cũng ảnh hưởng hiệu năng.

## 10. Cách 3: GROUP BY khi nghiệp vụ thật sự cần tổng hợp

Không phải trường hợp nhiều hàng nguồn nào cũng là “chọn bản ghi mới nhất”. Với hệ thống tồn kho, bảng nguồn có thể chứa **nhiều biến động cần cộng**:

~~~text
SKU BK-01:
    nhập +10
    bán  -3
    kiểm kê +2
Kết quả biến động: +9
~~~

Nếu nghiệp vụ yêu cầu **tổng biến động**, không nên chọn một dòng bằng `DISTINCT ON` hoặc `ROW_NUMBER`, vì sẽ bỏ mất các giao dịch khác. Phải **tổng hợp theo khóa trước** rồi cập nhật một hàng đích bằng một giá trị tổng.

### 10.1. Tạo bảng tồn kho và biến động mẫu

~~~sql
CREATE TABLE upd_lab_201.stock_balance (
    sku TEXT PRIMARY KEY,
    on_hand INTEGER NOT NULL CHECK (on_hand >= 0)
);

CREATE TABLE upd_lab_201.stock_movements (
    movement_id BIGINT PRIMARY KEY,
    sku TEXT NOT NULL,
    delta_qty INTEGER NOT NULL,
    is_posted BOOLEAN NOT NULL DEFAULT FALSE
);

INSERT INTO upd_lab_201.stock_balance
    (sku, on_hand)
VALUES
    ('BK-01', 50),
    ('MOUSE-01', 20),
    ('PEN-01', 100);

INSERT INTO upd_lab_201.stock_movements
    (movement_id, sku, delta_qty, is_posted)
VALUES
    (1, 'BK-01', 10, TRUE),
    (2, 'BK-01', -3, TRUE),
    (3, 'BK-01', 2, TRUE),
    (4, 'MOUSE-01', -5, TRUE),
    (5, 'MOUSE-01', 99, FALSE),
    (6, 'PEN-01', -10, TRUE);
~~~

### 10.2. Sai: UPDATE trực tiếp từ nhiều movement

~~~sql
-- CẢNH BÁO: chỉ minh họa thiết kế sai, không chạy như nghiệp vụ.
-- UPDATE upd_lab_201.stock_balance AS b
-- SET on_hand = b.on_hand + m.delta_qty
-- FROM upd_lab_201.stock_movements AS m
-- WHERE b.sku = m.sku
--   AND m.is_posted;
~~~

Với `BK-01` có ba movement, câu trên **không có ý nghĩa “cộng 10 rồi trừ 3 rồi cộng 2”**. Nó chỉ chọn một hàng join để cấp `delta_qty` cho lần cập nhật của `BK-01`. Đây là lỗi **mất giao dịch nguồn**, không chỉ là chọn nhầm bản ghi mới nhất.

### 10.3. Đúng: tổng hợp delta trước

~~~sql
BEGIN;

WITH movement_totals AS (
    SELECT
        sku,
        SUM(delta_qty) AS total_delta
    FROM upd_lab_201.stock_movements
    WHERE is_posted
    GROUP BY sku
)
UPDATE upd_lab_201.stock_balance AS b
SET on_hand = b.on_hand + t.total_delta
FROM movement_totals AS t
WHERE b.sku = t.sku
  AND b.on_hand + t.total_delta >= 0
RETURNING
    b.sku,
    b.on_hand AS new_on_hand,
    t.total_delta;

ROLLBACK;
~~~

Kết quả trong transaction:

| SKU | Tồn ban đầu | Tổng delta đã posted | Tồn mới |
| --- | ---: | ---: | ---: |
| BK-01 | 50 | +9 | 59 |
| MOUSE-01 | 20 | -5 | 15 |
| PEN-01 | 100 | -10 | 90 |

`movement_totals` chỉ có **một hàng mỗi SKU** vì `GROUP BY sku`. Nhưng lưu ý `SUM(delta_qty)` cần đúng quy tắc nghiệp vụ: đã posted hay chưa, có bị ghi trùng, có hủy giao dịch hay không, batch nào đã áp dụng — những điều này không được `GROUP BY` tự giải quyết.

### 10.4. GROUP BY không phải cái cớ để dùng MAX tùy tiện

~~~sql
SELECT sku, MAX(new_price)
FROM upd_lab_201.price_feed
WHERE is_approved
GROUP BY sku;
~~~

Truy vấn này có **một hàng mỗi SKU**, nhưng nó chọn **giá cao nhất**, không chọn **đề xuất mới nhất**. Với `CABLE-01` giá cao nhất là `130000` (feed 105), trong khi quy tắc mới nhất + ID cao hơn chọn `125000` (feed 106).

**Đầu ra duy nhất không đủ để khẳng định đúng nghiệp vụ.** Phải biết mình cần tính **SUM/MAX/MIN/AVG** hay cần **chọn một bản ghi có thứ tự**.

## 11. Cách 4: scalar subquery như một kiểm tra cardinality

PostgreSQL hỗ trợ gán giá trị bằng **subquery trả một cột**:

~~~sql
UPDATE target AS t
SET value = (
    SELECT s.value
    FROM source AS s
    WHERE s.key = t.key
)
WHERE ...;
~~~

Với subquery scalar:

- **Một hàng** → lấy giá trị của hàng đó.
- **Không hàng** → biểu thức scalar subquery trả `NULL`.
- **Hơn một hàng** → PostgreSQL báo lỗi vì subquery được dùng làm biểu thức phải trả **tối đa một hàng** (thông thường `SQLSTATE 21000`, cardinality violation).

Điều này khác `UPDATE ... FROM`, nơi nhiều hàng nguồn khớp có thể tạo một cập nhật với nguồn không dự đoán được.

### 11.1. Chứng minh lỗi thay vì chọn tùy ý

Trên bộ dữ liệu có hai feed đã duyệt cho `BK-01`, câu sau được thiết kế **cố ý gây lỗi**:

~~~sql
BEGIN;
SAVEPOINT before_scalar_demo;

UPDATE upd_lab_201.products AS p
SET unit_price = (
    SELECT f.new_price
    FROM upd_lab_201.price_feed AS f
    WHERE f.sku = p.sku
      AND f.is_approved
)
WHERE p.sku = 'BK-01';
-- Dự kiến: ERROR:
-- more than one row returned by a subquery used as an expression
-- SQLSTATE thường là 21000.

ROLLBACK TO SAVEPOINT before_scalar_demo;
ROLLBACK;
~~~

Nếu SQL client dừng ngay sau lỗi, hãy chủ động rollback trong session trước khi tiếp tục. Với PostgreSQL, một statement lỗi có thể khiến transaction hiện tại ở trạng thái aborted cho đến khi rollback hoặc rollback về savepoint.

### 11.2. Scalar subquery không tự giải quyết bài toán

Lỗi cardinality **chỉ giúp phát hiện** rằng query không đáp ứng giả định một hàng; nó không chọn giúp winner đúng. Nếu bạn viết:

~~~sql
SET unit_price = (
    SELECT f.new_price
    FROM upd_lab_201.price_feed AS f
    WHERE f.sku = p.sku
      AND f.is_approved
    LIMIT 1
)
~~~

thì lỗi biến mất, nhưng **`LIMIT 1` không có `ORDER BY` đầy đủ vẫn chọn một hàng tùy ý**. Đây không phải cách sửa đúng.

### 11.3. Scalar subquery có ORDER BY và LIMIT 1

Nếu hợp đồng muốn một nguồn theo thứ tự cụ thể:

~~~sql
BEGIN;

UPDATE upd_lab_201.products AS p
SET unit_price = (
    SELECT f.new_price
    FROM upd_lab_201.price_feed AS f
    WHERE f.sku = p.sku
      AND f.is_approved
    ORDER BY f.feed_at DESC, f.feed_id DESC
    LIMIT 1
)
WHERE EXISTS (
    SELECT 1
    FROM upd_lab_201.price_feed AS f
    WHERE f.sku = p.sku
      AND f.is_approved
)
RETURNING p.sku, p.unit_price;

ROLLBACK;
~~~

`ORDER BY` cộng `LIMIT 1` xác định một giá nguồn cho mỗi sản phẩm (feed_id là unique). `WHERE EXISTS` rất quan trọng: nó đảm bảo chỉ cập nhật sản phẩm **có ít nhất một nguồn đã duyệt**.

### 11.4. Không có nguồn: UPDATE FROM và scalar subquery khác nhau

Giả sử `BAG-01` không có bản ghi feed:

- `UPDATE ... FROM feed WHERE p.sku=f.sku` → không có join row, **không cập nhật BAG-01**.
- `UPDATE products SET unit_price=(SELECT ...)` **không có `WHERE EXISTS`** → scalar subquery trả `NULL`, có thể khiến cột đích thành NULL hoặc vi phạm `NOT NULL`.

Đây là khác biệt cần nhớ khi chuyển đổi cú pháp giữa các loại update.

### 11.5. Một điểm cần cân nhắc hiệu năng

Scalar correlated subquery có thể được thực hiện/được lập kế hoạch khác với join update; trên bảng lớn, cost có thể khác. Không xem scalar subquery luôn chậm hơn hoặc luôn nhanh hơn `UPDATE ... FROM`. Chọn cách thể hiện đúng cardinality trước, sau đó đo kế hoạch với `EXPLAIN` và dữ liệu đại diện.

## 12. Một nguồn duy nhất bằng staging table có UNIQUE

Nếu một job ETL thường xuyên nhận batch dữ liệu, giải pháp bền vững là **chuẩn hóa nguồn vào staging table có khóa duy nhất** trên khóa ghép với target.

Ví dụ trong transaction:

~~~sql
BEGIN;

CREATE TEMP TABLE selected_price_feed (
    sku TEXT PRIMARY KEY,
    feed_id BIGINT NOT NULL UNIQUE,
    new_price NUMERIC(12, 2) NOT NULL
) ON COMMIT DROP;

INSERT INTO selected_price_feed (sku, feed_id, new_price)
SELECT DISTINCT ON (f.sku)
    f.sku,
    f.feed_id,
    f.new_price
FROM upd_lab_201.price_feed AS f
WHERE f.is_approved
ORDER BY f.sku, f.feed_at DESC, f.feed_id DESC;

-- Một SKU chỉ có một dòng winner do PRIMARY KEY(sku).
SELECT sku, feed_id, new_price
FROM selected_price_feed
ORDER BY sku;

UPDATE upd_lab_201.products AS p
SET
    unit_price = s.new_price,
    price_source_note = 'feed=' || s.feed_id::text
FROM selected_price_feed AS s
WHERE p.sku = s.sku
RETURNING p.product_id, p.sku, p.unit_price;

ROLLBACK;
~~~

`PRIMARY KEY(sku)` trên staging là **rào chắn kỹ thuật**. Nếu một quy trình lỗi cố chèn hai winner cho cùng SKU, câu `INSERT` vào staging sẽ thất bại thay vì âm thầm cho phép `UPDATE` chọn tùy ý.

### 12.1. Unique constraint bảo vệ điều gì?

Nó chứng minh bảng staging có **tối đa một hàng trên mỗi SKU**. Tuy nhiên, nó **không chứng minh** hàng winner được chọn là đúng về mặt nghiệp vụ. Nếu upstream sắp sai timestamp hoặc chọn nhầm nhà cung cấp, staging vẫn có thể có mỗi SKU một hàng nhưng giá sai.

Do đó cần hai lớp:

1. **Quy tắc chọn winner đúng**: mới nhất, duyệt hợp lệ, tie-breaker rõ ràng.
2. **Ràng buộc cardinality**: nguồn đã chuẩn hóa có `UNIQUE(sku)`.

### 12.2. Staging cho batch nhập thực tế

Trong production, có thể bổ sung:

~~~text
batch_id
source_system
ingested_at
validation_status
approved_by
source_row_hash
~~~

và unique key phù hợp như `(batch_id, sku)` nếu mỗi batch có một giá được chọn cho mỗi SKU. Khi đó `UPDATE` phải ghép theo **đúng batch_id**, tránh lẫn giá giữa các lần import.

## 13. Nguy cơ duplicate xuất hiện từ JOIN bổ sung

Ngay cả khi bảng `price_feed` đã được đưa về **một winner mỗi SKU**, một join tới bảng phụ có quan hệ một–nhiều có thể làm nguồn bị nhân hàng.

Giả sử mỗi nhà cung cấp có nhiều người liên hệ:

~~~sql
CREATE TABLE upd_lab_201.provider_contacts (
    contact_id BIGINT PRIMARY KEY,
    provider TEXT NOT NULL,
    contact_name TEXT NOT NULL
);

INSERT INTO upd_lab_201.provider_contacts
    (contact_id, provider, contact_name)
VALUES
    (1, 'VENDOR-A', 'Liên hệ A1'),
    (2, 'VENDOR-A', 'Liên hệ A2'),
    (3, 'VENDOR-B', 'Liên hệ B1');
~~~

Một đề xuất giá `VENDOR-A` có thể ghép được **hai** liên hệ. Truy vấn:

~~~sql
WITH latest AS (
    SELECT DISTINCT ON (sku)
        sku, feed_id, new_price, provider
    FROM upd_lab_201.price_feed
    WHERE is_approved
    ORDER BY sku, feed_at DESC, feed_id DESC
)
SELECT
    latest.sku,
    latest.feed_id,
    c.contact_id,
    c.contact_name
FROM latest
JOIN upd_lab_201.provider_contacts AS c
    ON c.provider = latest.provider
ORDER BY latest.sku, c.contact_id;
~~~

Các winner của `VENDOR-A` có thể bị nhân theo hai contact. Nếu đưa toàn bộ kết quả join này vào `UPDATE FROM` và dùng `contact_name` làm giá trị cập nhật, hàng đích lại có **nhiều lựa chọn nguồn**.

### 13.1. Kiểm tra cardinality sau tất cả các JOIN

~~~sql
WITH latest AS (
    SELECT DISTINCT ON (sku)
        sku, feed_id, new_price, provider
    FROM upd_lab_201.price_feed
    WHERE is_approved
    ORDER BY sku, feed_at DESC, feed_id DESC
),
source_rows AS (
    SELECT
        latest.sku,
        latest.feed_id,
        c.contact_id
    FROM latest
    JOIN upd_lab_201.provider_contacts AS c
        ON c.provider = latest.provider
)
SELECT sku, COUNT(*) AS source_rows_per_sku
FROM source_rows
GROUP BY sku
HAVING COUNT(*) > 1
ORDER BY sku;
~~~

**Đừng chỉ kiểm tra uniqueness ở CTE `latest` rồi cho rằng mọi join kế tiếp vẫn giữ một hàng/SKU.** Tính duy nhất có thể mất tại bất kỳ phép join 1:N nào.

### 13.2. Nếu chỉ cần xác nhận nguồn có liên hệ

Dùng `EXISTS` thay vì join chi tiết:

~~~sql
WITH latest AS (
    SELECT DISTINCT ON (sku)
        sku, feed_id, new_price, provider
    FROM upd_lab_201.price_feed
    WHERE is_approved
    ORDER BY sku, feed_at DESC, feed_id DESC
)
SELECT
    l.sku, l.feed_id, l.new_price
FROM latest AS l
WHERE EXISTS (
    SELECT 1
    FROM upd_lab_201.provider_contacts AS c
    WHERE c.provider = l.provider
);
~~~

`EXISTS` chỉ hỏi có hay không, không nhân bản winner theo số contact. Nếu cần lưu một contact cụ thể, phải định nghĩa rõ **contact được ưu tiên**, ví dụ có vai trò chính và khóa unique, hoặc chọn bằng thứ tự + tie-breaker.

## 14. Không nên dùng LIMIT, ORDER BY hay DISTINCT sai chỗ

### 14.1. ORDER BY chỉ ở SELECT kiểm tra không sửa UPDATE

~~~sql
SELECT *
FROM upd_lab_201.price_feed
ORDER BY feed_at DESC;
~~~

Việc query hiển thị nguồn theo thứ tự mới nhất **không làm câu UPDATE khác tự chọn hàng theo thứ tự ấy**.

### 14.2. ORDER BY bên trong một nguồn vẫn có thể để nhiều hàng khớp

~~~sql
-- VẪN MƠ HỒ nếu nhiều hàng cho cùng SKU:
-- UPDATE upd_lab_201.products AS p
-- SET unit_price = s.new_price
-- FROM (
--     SELECT sku, new_price
--     FROM upd_lab_201.price_feed
--     WHERE is_approved
--     ORDER BY feed_at DESC
-- ) AS s
-- WHERE p.sku = s.sku;
~~~

Subquery có `ORDER BY` nhưng **không loại các hàng khác cùng SKU**. Cardinality vẫn lớn hơn 1; `UPDATE ... FROM` vẫn mơ hồ.

### 14.3. LIMIT 1 ở phạm vi toàn nguồn không chọn mỗi SKU một hàng

~~~sql
SELECT sku, feed_id, new_price
FROM upd_lab_201.price_feed
WHERE is_approved
ORDER BY feed_at DESC, feed_id DESC
LIMIT 1;
~~~

Truy vấn này chọn **một hàng cho toàn bảng**, không phải **một hàng cho mỗi SKU**. Đưa nó vào nguồn `UPDATE` sẽ khiến đa số sản phẩm không có hàng khớp.

Muốn **một hàng mỗi nhóm SKU**, phải dùng `DISTINCT ON (sku)`, `ROW_NUMBER() OVER (PARTITION BY sku ...)` hoặc một thiết kế tương đương.

### 14.4. DISTINCT chỉ loại bản ghi giống nhau theo cột được chọn

~~~sql
SELECT DISTINCT sku, new_price
FROM upd_lab_201.price_feed
WHERE is_approved;
~~~

Hai bản ghi BK với giá khác nhau vẫn là hai hàng. Nếu nguồn có hai bản ghi cùng giá nhưng khác `feed_id`, việc loại trùng `(sku,new_price)` vẫn không diễn đạt chính xác quy tắc “đề xuất mới nhất đã duyệt”.

## 15. UPDATE ... FROM khi nguồn không khớp

Một nguồn không khớp không có nghĩa là `SET` tự đặt `NULL`. Với kiểu update dựa trên inner join:

~~~sql
UPDATE upd_lab_201.products AS p
SET unit_price = f.new_price
FROM upd_lab_201.price_feed AS f
WHERE p.sku = f.sku
  AND f.is_approved;
~~~

chỉ các sản phẩm có ít nhất một hàng feed duyệt được cập nhật. Với bộ dữ liệu:

- `PEN-01` không có nguồn **approved** → giữ nguyên giá.
- `BAG-01` không có bất kỳ feed nào → giữ nguyên giá.
- `UNKNOWN-01` tồn tại trong feed nhưng không có đích → không có sản phẩm nào được tạo.

### 15.1. Nếu nghiệp vụ muốn cập nhật cả hàng không khớp

Phải diễn đạt điều kiện đó riêng. Ví dụ chuyển trạng thái sản phẩm không có feed approved thành cần rà soát:

~~~sql
BEGIN;

UPDATE upd_lab_201.products AS p
SET status = 'INACTIVE'
WHERE NOT EXISTS (
    SELECT 1
    FROM upd_lab_201.price_feed AS f
    WHERE f.sku = p.sku
      AND f.is_approved
)
RETURNING p.sku, p.status;

ROLLBACK;
~~~

Trong bộ dữ liệu, ví dụ này ảnh hưởng `PEN-01` và `BAG-01`. **Đây chỉ là minh họa cú pháp**, không phải khuyến nghị rằng sản phẩm không có feed mới phải ngừng bán. Nghiệp vụ thực tế có thể cần giữ giá cũ và trạng thái active.

### 15.2. Tránh đặt giá bằng NULL do scalar subquery rỗng

Nếu cần hỗ trợ cả hàng không có nguồn, có thể dùng `CASE`, `COALESCE` hoặc hai lệnh `UPDATE` khác nhau, nhưng phải xác định **NULL có nghĩa gì**. Với cột `unit_price NOT NULL`, đặt giá chưa biết thành `NULL` sẽ vi phạm ràng buộc, và đặt thành 0 để “qua lỗi” có thể tạo giá bán sai.

## 16. NULL trong khóa nối và dữ liệu cập nhật

Khi `WHERE t.key = s.key`, nếu một trong hai khóa là `NULL`, phép so sánh `=` không trả TRUE, nên hai hàng không được join theo điều kiện ấy.

Ví dụ:

~~~sql
SELECT
    NULL::text = NULL::text AS regular_equality,
    NULL::text IS NOT DISTINCT FROM NULL::text
        AS null_safe_equality;
~~~

Kết quả: `NULL` và `TRUE`.

### 16.1. Có nên join NULL với NULL?

Trong hệ thống dùng khóa nghiệp vụ như SKU, thường **không nên cho SKU NULL**. Đặt `NOT NULL` và `UNIQUE` ở đích giúp xác định đối tượng rõ ràng.

Nếu một quan hệ thực sự coi hai giá trị NULL là một khóa tương đương, PostgreSQL có `IS NOT DISTINCT FROM` để so null-safe:

~~~sql
-- Minh họa về mặt ngữ nghĩa; chỉ áp dụng nếu nghiệp vụ yêu cầu.
-- WHERE t.optional_key IS NOT DISTINCT FROM s.optional_key
~~~

Nhưng nếu có **nhiều** hàng nguồn với khóa NULL, null-safe join sẽ khiến **tất cả** chúng có thể khớp một hàng đích NULL, làm tăng nguy cơ nhiều nguồn khớp. Vì thế không nên sửa lỗi thiếu khóa bằng cách đổi tất cả `=` thành `IS NOT DISTINCT FROM`.

### 16.2. Không dùng COALESCE để giấu nguồn thiếu giá trị

~~~sql
SET unit_price = COALESCE(s.new_price, p.unit_price)
~~~

Biểu thức này giữ giá cũ nếu `new_price` NULL. Nó có thể phù hợp khi nguồn cho phép “không đổi giá”, nhưng cũng có thể che lỗi import nếu **giá mới bắt buộc phải có**. Trong bộ lab, `new_price NOT NULL` giúp loại nguy cơ ngay từ cấu trúc bảng.

Khi cập nhật nhiều cột, hãy xét từng cột:

- Giá mới NULL → bỏ qua, từ chối hay giữ giá cũ?
- `provider` NULL → có được ghi đè ghi chú cũ không?
- `feed_at` trễ hơn → có chấp nhận cập nhật ngược phiên bản không?

Một câu `UPDATE` chạy thành công chỉ đảm bảo tuân theo ràng buộc SQL, **không chứng minh mọi quy tắc nghiệp vụ đã đúng**.

## 17. RETURNING để quan sát hàng đã cập nhật

PostgreSQL hỗ trợ `RETURNING` sau `UPDATE`:

~~~sql
UPDATE target AS t
SET column = expression
FROM source AS s
WHERE ...
RETURNING t.id, t.column;
~~~

Nếu nguồn được tham chiếu trong `FROM`, có thể trả thêm giá trị nguồn liên quan trong biểu thức `RETURNING` phù hợp, ví dụ `s.feed_id`.

### 17.1. Quan sát sau cập nhật, không suy đoán từ rowcount

~~~sql
BEGIN;

WITH winner AS (
    SELECT DISTINCT ON (sku)
        sku, feed_id, new_price
    FROM upd_lab_201.price_feed
    WHERE is_approved
    ORDER BY sku, feed_at DESC, feed_id DESC
)
UPDATE upd_lab_201.products AS p
SET unit_price = w.new_price
FROM winner AS w
WHERE p.sku = w.sku
RETURNING
    p.product_id,
    p.sku,
    p.unit_price AS applied_price,
    w.feed_id;

ROLLBACK;
~~~

Trong transaction lab, kết quả `RETURNING` cho biết ba sản phẩm đã bị tác động và feed được dùng. Trên production, có thể dùng kết quả này làm căn cứ ghi log ứng dụng hoặc đối soát, nhưng cần quản lý quyền truy cập/độ nhạy dữ liệu và quy trình ghi log.

### 17.2. UPDATE có thể ghi một hàng dù giá không đổi

Ví dụ:

~~~sql
UPDATE products
SET unit_price = unit_price
WHERE product_id = 1;
~~~

vẫn là một lệnh `UPDATE` đối với hàng khớp điều kiện. Trong PostgreSQL, nó có thể tạo phiên bản hàng mới, tác động trigger/WAL/bloat tùy ngữ cảnh. Vì vậy không nên hiểu rowcount của `UPDATE` là “số hàng có giá trị thật sự thay đổi”.

### 17.3. Chỉ update khi giá thực sự khác

~~~sql
BEGIN;

WITH winner AS (
    SELECT DISTINCT ON (sku)
        sku, feed_id, new_price
    FROM upd_lab_201.price_feed
    WHERE is_approved
    ORDER BY sku, feed_at DESC, feed_id DESC
)
UPDATE upd_lab_201.products AS p
SET
    unit_price = w.new_price,
    price_source_note = 'feed=' || w.feed_id::text,
    updated_at = clock_timestamp()
FROM winner AS w
WHERE p.sku = w.sku
  AND p.unit_price IS DISTINCT FROM w.new_price
RETURNING p.sku, p.unit_price, w.feed_id;

ROLLBACK;
~~~

`IS DISTINCT FROM` là phép so sánh null-safe; nếu hai giá giống nhau, điều kiện FALSE và không có UPDATE. Nhưng nếu **giá không đổi mà nguồn cần được ghi nhận lại**, điều kiện chỉ so giá có thể bỏ qua metadata cần cập nhật. Khi đó phải định nghĩa chính xác trường nào cấu thành “thay đổi có ý nghĩa”.

## 18. Ghi nhận giá cũ và giá mới để đối soát

Trong nhiều hệ thống, sau khi cập nhật người quản trị muốn thấy:

~~~text
product_id | old_price | new_price | chosen_feed_id
~~~

Một cách trong lab là tạo bảng tạm lưu giá trước khi chạy update. Trên PostgreSQL hiện đại, `RETURNING` có khả năng tham chiếu giá trị mới; những tính năng truy cập trực tiếp old/new trong `RETURNING` phụ thuộc phiên bản, nên mẫu sau cố tình không dựa vào cú pháp old/new mở rộng.

### 18.1. Snapshot trước khi UPDATE trong cùng transaction

~~~sql
BEGIN;

CREATE TEMP TABLE before_prices ON COMMIT DROP AS
SELECT
    product_id,
    sku,
    unit_price AS old_price
FROM upd_lab_201.products;

WITH winner AS (
    SELECT DISTINCT ON (sku)
        sku, feed_id, new_price
    FROM upd_lab_201.price_feed
    WHERE is_approved
    ORDER BY sku, feed_at DESC, feed_id DESC
),
applied AS (
    UPDATE upd_lab_201.products AS p
    SET unit_price = w.new_price
    FROM winner AS w
    WHERE p.sku = w.sku
    RETURNING p.product_id, p.sku, p.unit_price, w.feed_id
)
SELECT
    a.product_id,
    a.sku,
    b.old_price,
    a.unit_price AS new_price,
    a.feed_id
FROM applied AS a
JOIN before_prices AS b
    ON b.product_id = a.product_id
ORDER BY a.product_id;

ROLLBACK;
~~~

Trong **bài lab không có concurrent changes**, truy vấn cho bảng giá trước/sau dễ kiểm tra. Trong production, việc snapshot rồi update ở isolation level thông thường **không tự bảo đảm** một transaction khác không thay giá giữa bước snapshot và bước update. Cần thiết kế khóa, isolation và nguồn audit đúng yêu cầu nhất quán nếu đòi giá cũ tuyệt đối chính xác.

### 18.2. Khi cần lịch sử giá chuẩn

Một hệ thống nghiêm túc có thể lưu lịch sử:

~~~text
product_price_history(
    history_id,
    product_id,
    old_price,
    new_price,
    feed_id,
    changed_at,
    changed_by,
    batch_id
)
~~~

Việc ghi lịch sử phải được phối hợp **cùng transaction** với thay đổi giá, qua quy trình DML/trigger hoặc cơ chế được thiết kế có chủ đích. Không dựa vào query `SELECT` chạy ở thời điểm khác để tái dựng chắc chắn mọi giá cũ.

## 19. Thực hiện thay đổi an toàn trong transaction

Quy trình thực tế nên có ba giai đoạn: **chuẩn bị, kiểm tra, ghi và xác nhận**.

<escape>**Bước 1 — Chuẩn bị nguồn winner:**</escape> chỉ lấy dữ liệu đã duyệt, có batch rõ, chọn thứ tự phù hợp và xác nhận mỗi SKU một hàng.

<escape>**Bước 2 — Kiểm tra tác động dự kiến:**</escape> chạy `SELECT` join winner với đích, so giá cũ/mới, đếm số sản phẩm, kiểm tra nguồn không khớp đích và các bất thường.

<escape>**Bước 3 — UPDATE trong transaction:**</escape> dùng đúng winner đã được xác nhận, kiểm tra `RETURNING`/rowcount, ghi audit cần thiết rồi mới `COMMIT` nếu mọi điều kiện được đáp ứng.

Mẫu thực hành với một CTE nguồn winner:

~~~sql
BEGIN;

-- Trong môi trường lab, hạn chế thời gian giữ khóa.
SET LOCAL lock_timeout = '3s';
SET LOCAL statement_timeout = '20s';

WITH winner AS (
    SELECT DISTINCT ON (sku)
        sku, feed_id, new_price
    FROM upd_lab_201.price_feed
    WHERE is_approved
    ORDER BY sku, feed_at DESC, feed_id DESC
)
SELECT
    p.sku,
    p.unit_price AS old_price,
    w.new_price,
    w.feed_id
FROM upd_lab_201.products AS p
JOIN winner AS w
    ON w.sku = p.sku
ORDER BY p.sku;

-- Chỉ khi đã nắm được tác động, chạy UPDATE tương ứng.
WITH winner AS (
    SELECT DISTINCT ON (sku)
        sku, feed_id, new_price
    FROM upd_lab_201.price_feed
    WHERE is_approved
    ORDER BY sku, feed_at DESC, feed_id DESC
)
UPDATE upd_lab_201.products AS p
SET
    unit_price = w.new_price,
    price_source_note = 'feed=' || w.feed_id::text
FROM winner AS w
WHERE p.sku = w.sku
RETURNING p.sku, p.unit_price, w.feed_id;

-- Bài lab luôn rollback để giữ seed.
ROLLBACK;
~~~

### 19.1. Vì sao phải giữ thời gian transaction hợp lý?

`UPDATE` cần khóa các hàng đích bị ghi và có thể tranh chấp với transaction khác. Transaction mở lâu có thể:

- Khiến các request ghi khác phải chờ.
- Tăng nguy cơ deadlock khi nhiều nguồn cập nhật theo thứ tự khác nhau.
- Giữ phiên bản cũ lâu hơn, ảnh hưởng vacuum/bloat.
- Làm hàng loạt sửa đổi khó rollback hoặc khôi phục nhanh nếu phạm vi quá lớn.

Đừng để transaction production mở trong lúc chờ duyệt thủ công nhiều phút/giờ. Chuẩn bị và kiểm tra ở staging trước, rồi triển khai batch có kiểm soát và audit phù hợp.

### 19.2. Preflight và UPDATE là hai câu SQL riêng

Ngay cả ở `READ COMMITTED`, hai statement có thể nhìn thấy dữ liệu nguồn khác nhau nếu transaction khác commit giữa chúng. **Preflight đúng tại thời điểm T không tự bảo đảm UPDATE ở T+1 dùng đúng cùng snapshot nguồn.**

Nếu yêu cầu **áp dụng chính xác tập feed đã duyệt**:

- Đưa winner vào staging có khóa duy nhất và `batch_id` cố định.
- Kiểm soát việc sửa staging sau khi chốt batch.
- Chạy update từ tập winner ổn định.
- Chọn isolation/locking phù hợp với yêu cầu cạnh tranh cụ thể.

`BEGIN` hữu ích để rollback thay đổi của chính transaction, nhưng **không biến mọi nguồn dữ liệu đang thay đổi thành snapshot bất biến xuyên suốt bằng phép màu**.

## 20. Các nguy cơ khi nhiều transaction cùng UPDATE

Giả sử hai job A/B cùng muốn cập nhật `BK-01` từ hai batch khác nhau:

~~~text
Job A: đọc feed approved, chọn price 115000
Job B: nhận feed mới approved, chọn price 119000
Job A: UPDATE BK-01
Job B: UPDATE BK-01
~~~

Kết quả cuối phụ thuộc chính sách transaction, trình tự commit, điều kiện update và khả năng kiểm soát phiên bản. **Chọn winner duy nhất trong mỗi job không tự ngăn tình trạng ghi đè theo thứ tự sai giữa các job.**

### 20.1. Cần quy tắc không ghi đè bởi nguồn cũ

Một thiết kế thường giữ thêm các trường:

~~~text
products.applied_feed_at
products.applied_feed_id
~~~

Rồi chỉ cho phép áp dụng nguồn nếu phiên bản nguồn **mới hơn** phiên bản đã ghi. Nếu dùng timestamp làm thứ tự ưu tiên, cần xử lý tie-breaker ID và điều kiện kiểm tra **ngay trong statement UPDATE**, không chỉ ở bước `SELECT` trước đó.

Đây là thiết kế mở rộng: schema lab ban đầu không có hai cột này nên đoạn minh họa sau là **ý tưởng**, không phải SQL chạy trực tiếp:

~~~sql
-- Ý tưởng nếu schema có applied_feed_at và applied_feed_id:
-- WHERE p.sku = w.sku
--   AND (
--       p.applied_feed_at IS NULL
--       OR (p.applied_feed_at, p.applied_feed_id)
--          < (w.feed_at, w.feed_id)
--   )
~~~

Với hai cột phía đích **NOT NULL** sau khi khởi tạo, row comparison đơn giản hơn. Nếu `applied_feed_id` có thể NULL, cần xử lý toàn bộ trường hợp NULL tường minh thay vì dựa vào tuple comparison sẽ trả UNKNOWN.

### 20.2. Khóa hàng và điều kiện WHERE

PostgreSQL khóa hàng đích khi cập nhật; transaction khác cập nhật cùng hàng có thể phải chờ. Trong `READ COMMITTED`, PostgreSQL có cơ chế kiểm tra lại điều kiện của hàng đích sau các thay đổi đồng thời trong những tình huống thích hợp. Nhưng **chỉ dựa vào khóa ngầm không đảm bảo mọi quy tắc phiên bản do ứng dụng tự đặt ra**.

Nên phối hợp:

- Một thứ tự nguồn có nghĩa nghiệp vụ;
- Điều kiện cập nhật so sánh phiên bản;
- Batch idempotent và ghi nhận feed đã áp dụng;
- Lock/isolation phù hợp khi nhiều writer cạnh tranh;
- Retry có giới hạn cho deadlock/serialization failure khi nghiệp vụ cho phép.

### 20.3. Đừng retry mù lỗi dữ liệu

Một lỗi `23505` do khóa duy nhất hoặc `21000` do scalar subquery nhiều hàng thường chỉ ra **vấn đề dữ liệu/logic**, không phải lý do để chạy lại y hệt cho đến khi “may mắn thành công”. Ngược lại, lỗi deadlock `40P01` hoặc serialization failure `40001` có thể được retry **toàn bộ transaction** theo chính sách phù hợp.

## 21. UPDATE FROM khi dùng self-join

PostgreSQL cho phép dùng cùng một bảng làm nguồn trong `FROM`, nhưng phải phân biệt **bảng đích** với **bản sao được alias làm nguồn**.

Ví dụ bảng nhân viên có manager:

~~~sql
CREATE TABLE upd_lab_201.staff (
    staff_id BIGINT PRIMARY KEY,
    manager_id BIGINT NULL
        REFERENCES upd_lab_201.staff(staff_id),
    staff_name TEXT NOT NULL,
    manager_name_cache TEXT NULL
);

INSERT INTO upd_lab_201.staff
    (staff_id, manager_id, staff_name)
VALUES
    (1, NULL, 'An'),
    (2, 1, 'Bình'),
    (3, 1, 'Chi');
~~~

Mỗi `manager_id` trỏ tới **tối đa một** manager vì `staff.staff_id` là khóa chính:

~~~sql
BEGIN;

UPDATE upd_lab_201.staff AS employee
SET manager_name_cache = manager.staff_name
FROM upd_lab_201.staff AS manager
WHERE employee.manager_id = manager.staff_id
RETURNING
    employee.staff_id,
    employee.staff_name,
    employee.manager_name_cache;

ROLLBACK;
~~~

Vì `manager.staff_id` unique, mỗi nhân viên chỉ khớp tối đa một hàng manager. Đây là self-join an toàn về cardinality.

### 21.1. Vì sao phải đặt alias?

Nếu muốn bảng đích xuất hiện lại trong `FROM`, phải đặt **alias khác** để rõ mỗi tham chiếu đóng vai trò nào. Không viết:

~~~sql
-- Không phải dạng tự nối đúng:
-- UPDATE staff SET ... FROM staff WHERE ...;
~~~

và trông đợi PostgreSQL tự biết hàng nào là nhân viên, hàng nào là quản lý. Dùng alias như `employee` và `manager` cho thấy một bản là **đích ghi**, một bản là **nguồn đọc**.

### 21.2. Denormalization là quyết định riêng

`manager_name_cache` chỉ là ví dụ thực hành. Trong production, tên manager thay đổi sẽ khiến cache có thể cũ; nhiều hệ thống nên **JOIN khi đọc** thay vì lưu tên trùng. Nếu thật sự cần cache, phải có cơ chế đồng bộ/chấp nhận độ trễ và kiểm soát cập nhật.

## 22. UPDATE FROM với CTE nhiều bước

Một câu `WITH` có thể chia logic thành các bước: lọc feed, xếp hạng, chọn winner, sau đó update.

~~~sql
BEGIN;

WITH approved AS (
    SELECT
        feed_id, sku, new_price, feed_at, provider
    FROM upd_lab_201.price_feed
    WHERE is_approved
),
ranked AS (
    SELECT
        approved.*,
        ROW_NUMBER() OVER (
            PARTITION BY sku
            ORDER BY feed_at DESC, feed_id DESC
        ) AS rn
    FROM approved
),
winner AS (
    SELECT
        feed_id, sku, new_price, feed_at, provider
    FROM ranked
    WHERE rn = 1
),
applied AS (
    UPDATE upd_lab_201.products AS p
    SET
        unit_price = w.new_price,
        price_source_note = 'feed=' || w.feed_id::text
    FROM winner AS w
    WHERE p.sku = w.sku
    RETURNING
        p.product_id,
        p.sku,
        p.unit_price,
        w.feed_id
)
SELECT *
FROM applied
ORDER BY product_id;

ROLLBACK;
~~~

Việc chia thành CTE giúp người đọc thấy **mỗi lớp đảm nhận nhiệm vụ gì**:

1. `approved` loại bản ghi chưa duyệt.
2. `ranked` thể hiện rõ thứ tự ưu tiên.
3. `winner` bảo đảm một hàng mỗi SKU.
4. `applied` là phần **ghi** và trả kết quả.

**CTE không tự làm join trở thành một–một.** Nếu `winner` được viết sai, vẫn có thể có nhiều hàng cho mỗi SKU. Giá trị của thiết kế nằm ở **quy tắc và ràng buộc cardinality**, không nằm ở tên `WITH`.

### 22.1. CTE không phải cơ chế khóa nguồn

Một CTE đọc dữ liệu trong phạm vi statement, nhưng không có nghĩa nó tự khóa mọi hàng nguồn để chống người khác cập nhật. Nếu yêu cầu snapshot cố định xuyên nhiều statement, cần thiết kế transaction/isolation/staging phù hợp.

### 22.2. Không dùng CTE MATERIALIZED như lời giải tính không xác định

Ép materialize một tập nguồn có **hai hàng cùng SKU** không khiến `UPDATE ... FROM` biết hàng nào phải thắng. `MATERIALIZED` có thể ảnh hưởng cách lập kế hoạch/tái sử dụng CTE, **không sửa ngữ nghĩa duplicate join**.

## 23. MERGE và INSERT ON CONFLICT DO UPDATE khác gì?

PostgreSQL có những phương thức ghi dữ liệu khác:

- `UPDATE ... FROM`: cập nhật các hàng đã có trong bảng đích từ một tập nguồn.
- `INSERT ... ON CONFLICT DO UPDATE`: chèn hàng mới hoặc cập nhật khi gặp conflict trên unique constraint/index hợp lệ.
- `MERGE` (từ PostgreSQL 15): diễn đạt các nhánh `WHEN MATCHED`/`WHEN NOT MATCHED` và những hành động tương ứng.

**Đổi cú pháp không đồng nghĩa tự sửa vấn đề nguồn trùng.** Các công cụ có quy tắc về duplicate/cardinality riêng, và cần đọc tài liệu đúng phiên bản.

### 23.1. ON CONFLICT DO UPDATE không cho một command cập nhật cùng hàng nhiều lần

Trong PostgreSQL, một câu `INSERT ... ON CONFLICT DO UPDATE` không được phép tác động cùng một hàng đích hơn một lần trong cùng command. Nếu input chứa nhiều hàng conflict lên cùng khóa, có thể nhận lỗi cardinality violation.

Ví dụ ý tưởng:

~~~sql
-- Không chạy trên production; ví dụ nguồn có SKU trùng:
-- INSERT INTO products(sku, unit_price, ...)
-- VALUES ('BK-01', 110000, ...),
--        ('BK-01', 115000, ...)
-- ON CONFLICT (sku) DO UPDATE
-- SET unit_price = EXCLUDED.unit_price;
~~~

Muốn upsert từ feed, vẫn nên **đưa feed về một hàng mỗi SKU** theo quy tắc nghiệp vụ trước.

### 23.2. MERGE không phải thay thế trực tiếp cho UPDATE FROM

`MERGE` hỗ trợ thao tác khác nhau tùy match/no match, nhưng nguồn không duy nhất vẫn có thể gây lỗi cardinality hoặc những hành vi không phù hợp với mục tiêu. Khi một hàng đích khớp nhiều hàng nguồn và nhiều hành động muốn tác động nó, PostgreSQL có những kiểm tra khác `UPDATE ... FROM`. Vì vậy phải thiết kế quan hệ nguồn với cardinality rõ trước khi `MERGE`.

Lựa chọn công cụ phải dựa trên việc bạn cần **update**, **upsert** hay **nhiều nhánh hành động**; không chọn `MERGE` chỉ để né quy tắc nguồn duy nhất.

## 24. Chỉ mục và hiệu năng

### 24.1. Index ở bảng đích

~~~sql
CREATE TABLE upd_lab_201.products (
    ...
    sku TEXT NOT NULL UNIQUE,
    ...
);
~~~

`UNIQUE(sku)` đã tạo index hỗ trợ tra cứu SKU và đảm bảo một SKU có một sản phẩm đích. Không tạo thêm một index B-tree trùng hệt `products(sku)` nếu không có lý do đặc biệt.

### 24.2. Index trên bảng nguồn

Trong bộ lab đã có:

~~~sql
CREATE INDEX idx_price_feed_sku_approved_time
ON upd_lab_201.price_feed
    (sku, feed_at DESC, feed_id DESC)
WHERE is_approved;
~~~

Đây là **partial B-tree index** cho các hàng đã duyệt, theo SKU và thứ tự dùng để chọn winner. Nó có thể giúp kế hoạch tính `DISTINCT ON (sku) ORDER BY sku, feed_at DESC, feed_id DESC` khi điều kiện lọc phù hợp.

Tuy vậy, index không bảo đảm query luôn nhanh nhất hay planner sẽ sử dụng nó. Các phép sort, số hàng, tính chọn lọc, thống kê và chi phí ghi đều quan trọng.

### 24.3. Kiểm tra bằng EXPLAIN trước khi chạy

~~~sql
EXPLAIN
WITH winner AS (
    SELECT DISTINCT ON (sku)
        sku, feed_id, new_price
    FROM upd_lab_201.price_feed
    WHERE is_approved
    ORDER BY sku, feed_at DESC, feed_id DESC
)
UPDATE upd_lab_201.products AS p
SET unit_price = w.new_price
FROM winner AS w
WHERE p.sku = w.sku;
~~~

`EXPLAIN` không có `ANALYZE` chỉ giải thích kế hoạch dự kiến, **không thực hiện UPDATE**.

Nếu dùng:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
UPDATE ...;
~~~

thì PostgreSQL **chạy thật câu UPDATE** để đo. Chỉ dùng trong transaction có rollback trên môi trường thực hành hoặc sau khi đánh giá tác động; một số tác động ngoài database của trigger/hàm có thể không được rollback như mong muốn.

### 24.4. Không cập nhật tràn lan nếu giá không đổi

`UPDATE` có thể tạo phiên bản hàng mới và ghi WAL ngay cả khi đặt lại cùng giá trị. Với bảng hàng triệu sản phẩm, cân nhắc điều kiện:

~~~sql
AND p.unit_price IS DISTINCT FROM w.new_price
~~~

để tránh ghi không cần thiết, nếu quy tắc nghiệp vụ không yêu cầu cập nhật metadata/audit khi giá giữ nguyên.

### 24.5. Batch lớn và lock contention

Thay hàng trăm nghìn sản phẩm trong một transaction có thể tạo lock lâu và WAL lớn. Có thể cần:

- Chọn batch theo khóa ổn định `product_id`.
- Giới hạn số lượng hàng mỗi transaction, có checkpoint/audit.
- Chốt nguồn theo batch để các lượt không dùng giá không nhất quán.
- Quan sát `pg_stat_activity`, thời gian chờ lock và replication lag.
- Có chiến lược retry, rollback và idempotency.

**Không đặt `LIMIT` trực tiếp trong kỳ vọng nó sẽ tự giới hạn `UPDATE ... FROM` theo mỗi SKU.** PostgreSQL `UPDATE` không có cú pháp `LIMIT` kiểu MySQL thông thường; nếu cần batch, phải chọn trước một tập khóa đích duy nhất bằng CTE/subquery rồi cập nhật trên tập đó, có kế hoạch lock và cạnh tranh phù hợp.

## 25. Kiểm tra số nguồn khớp bằng dữ liệu tạm trước khi ghi

Trên batch ETL, có thể làm rõ kỳ vọng bằng ba truy vấn đọc:

### 25.1. Tập nguồn đã chọn có một hàng/SKU chưa?

~~~sql
WITH winner AS (
    SELECT DISTINCT ON (sku)
        sku, feed_id, new_price
    FROM upd_lab_201.price_feed
    WHERE is_approved
    ORDER BY sku, feed_at DESC, feed_id DESC
)
SELECT
    sku,
    COUNT(*) AS rows_per_sku
FROM winner
GROUP BY sku
HAVING COUNT(*) > 1;
-- Kỳ vọng: không có hàng.
~~~

Đây là quan sát của truy vấn; nếu muốn ràng buộc vật lý, đưa kết quả vào staging `PRIMARY KEY(sku)`.

### 25.2. Nguồn nào không có sản phẩm đích?

~~~sql
WITH winner AS (
    SELECT DISTINCT ON (sku)
        sku, feed_id, new_price
    FROM upd_lab_201.price_feed
    WHERE is_approved
    ORDER BY sku, feed_at DESC, feed_id DESC
)
SELECT
    w.sku,
    w.feed_id,
    w.new_price
FROM winner AS w
LEFT JOIN upd_lab_201.products AS p
    ON p.sku = w.sku
WHERE p.product_id IS NULL
ORDER BY w.sku;
-- UNKNOWN-01, feed_id 107.
~~~

Không nên tự thêm sản phẩm giả vào production để “làm khớp” nguồn. Có thể cần đưa SKU lạ vào hàng chờ kiểm duyệt hoặc tạo product qua một workflow độc lập.

### 25.3. Sản phẩm nào không nhận nguồn approved?

~~~sql
SELECT
    p.product_id,
    p.sku,
    p.unit_price
FROM upd_lab_201.products AS p
WHERE NOT EXISTS (
    SELECT 1
    FROM upd_lab_201.price_feed AS f
    WHERE f.sku = p.sku
      AND f.is_approved
)
ORDER BY p.product_id;
-- PEN-01 và BAG-01.
~~~

Hai tập **nguồn không có đích** và **đích không có nguồn** là hai loại vấn đề khác nhau. Báo cáo pipeline nên phân loại rõ thay vì gộp thành “missing rows”.

## 26. Lỗi thường gặp và hướng giải quyết

| Triệu chứng/cách viết | Rủi ro | Hướng khắc phục |
| --- | --- | --- |
| `UPDATE FROM` nối feed chỉ bằng SKU, feed có nhiều phiên bản | Chọn một nguồn không xác định | `DISTINCT ON`/`ROW_NUMBER` với thứ tự đầy đủ |
| Có `ORDER BY` ở truy vấn SELECT trước đó | Không điều khiển UPDATE | Chọn winner **trong chính nguồn của UPDATE** |
| `DISTINCT sku, price` | Một SKU vẫn nhiều giá | `DISTINCT ON (sku)` hoặc group đúng |
| `RANK() = 1` | Có thể nhiều hàng cùng hạng | `ROW_NUMBER()=1` với tie-break |
| `LIMIT 1` không `ORDER BY` | Chọn tùy ý | Thêm thứ tự phù hợp, ổn định |
| `LIMIT 1` trên toàn bảng nguồn | Chỉ lấy một hàng toàn bảng | Chọn một hàng **mỗi khóa** |
| `MAX(new_price)` để lấy giá mới nhất | Nhầm giá cao nhất với thời điểm mới nhất | Chọn bản ghi theo `feed_at` và tie-break |
| `SUM(...)` trên nguồn giá phiên bản | Cộng giá của nhiều phiên bản thành giá bán | Tổng hợp chỉ khi nghiệp vụ thật sự cần tổng |
| Một bảng phụ 1:N được JOIN sau khi chọn winner | Nhân nguồn trở lại | Kiểm tra cardinality **sau mọi join**, dùng `EXISTS` nếu phù hợp |
| JOIN thiếu điều kiện nối | Cross join, update sai hàng | Ghi rõ khóa t–s và điều kiện batch |
| Scalar subquery trả >1 hàng | Lỗi cardinality `21000` | Sửa quy tắc nguồn, không chỉ thêm `LIMIT 1` mù |
| Scalar subquery không có hàng | Trả NULL, có thể ghi NULL/lỗi NOT NULL | `WHERE EXISTS` hoặc quy tắc riêng cho missing |
| `RETURNING` thấy 3 hàng, tưởng không có duplicate | Rowcount đích không phản ánh số nguồn khớp | Preflight `COUNT(*)` theo khóa đích |
| Dùng `COUNT(*)` sau LEFT JOIN để đếm nguồn | Hàng không match vẫn có count 1 | `COUNT(source_not_null_key)` |
| Chỉ kiểm tra `COUNT(DISTINCT price)=1` | Nhiều nguồn khác metadata vẫn bị bỏ qua | Kiểm tra `COUNT(*)` và khóa nguồn |
| Cập nhật giá cũ bởi batch trễ | Lost ordering/business version | Lưu phiên bản đã áp dụng và guard ngay trong UPDATE |
| Dùng `COALESCE(new_price, old_price)` để “không lỗi” | Có thể che dữ liệu feed sai | Quy định ý nghĩa NULL, reject invalid source |
| Giữ transaction mở quá lâu | Lock contention, deadlock, bloat | Chốt staging, batch hợp lý, giám sát |
| Tin `MATERIALIZED` sửa duplicate | Materialization không chọn winner | Làm đúng cardinality và thứ tự |
| Dùng `MERGE` hoặc `ON CONFLICT` để né nguồn trùng | Vẫn có cardinality/semantics riêng | Dedupe/aggregate nguồn đúng nghiệp vụ |

## 27. Bài tập thực hành

### Bài 1 — Đọc join trước khi update

Viết `SELECT` join `products` với `price_feed` chỉ lấy `is_approved=TRUE`. Trả `sku`, `unit_price`, `feed_id`, `new_price` và sắp theo SKU rồi timestamp giảm dần.

**Kỳ vọng:** có **6 hàng join** cho **3 sản phẩm đích**: BK-01, MOUSE-01, CABLE-01.

### Bài 2 — Phát hiện duplicate source

Viết:

~~~sql
SELECT
    p.sku,
    COUNT(*) AS matched_source_rows
FROM upd_lab_201.products AS p
JOIN upd_lab_201.price_feed AS f
    ON p.sku = f.sku
WHERE f.is_approved
GROUP BY p.sku
HAVING COUNT(*) > 1;
~~~

**Đáp án:** BK-01, MOUSE-01, CABLE-01 đều có **2** hàng nguồn.

### Bài 3 — Đánh giá câu UPDATE mơ hồ

Trên dữ liệu gốc, giải thích vì sao:

~~~sql
UPDATE upd_lab_201.products AS p
SET unit_price = f.new_price
FROM upd_lab_201.price_feed AS f
WHERE p.sku = f.sku
  AND f.is_approved;
~~~

không đảm bảo lấy giá mới nhất. **Không cần chạy nếu chưa bọc transaction rollback.**

### Bài 4 — Chọn winner bằng DISTINCT ON

Viết `SELECT DISTINCT ON (sku)` chọn các bản ghi approved có timestamp mới nhất, dùng `feed_id DESC` giải quyết tie.

**Đáp án winner:** `102` của BK-01, `103` của MOUSE-01, `106` của CABLE-01, `107` của UNKNOWN-01.

### Bài 5 — UPDATE FROM dùng winner

Bọc transaction:

~~~sql
BEGIN;

WITH winner AS (
    SELECT DISTINCT ON (sku)
        sku, feed_id, new_price
    FROM upd_lab_201.price_feed
    WHERE is_approved
    ORDER BY sku, feed_at DESC, feed_id DESC
)
UPDATE upd_lab_201.products AS p
SET unit_price = w.new_price
FROM winner AS w
WHERE p.sku = w.sku
RETURNING p.sku, p.unit_price, w.feed_id;

ROLLBACK;
~~~

**Đáp án:** BK-01 → 115000; MOUSE-01 → 270000; CABLE-01 → 125000. Hai sản phẩm PEN-01/BAG-01 không bị cập nhật.

### Bài 6 — Chọn winner bằng ROW_NUMBER

Dùng `ROW_NUMBER() OVER (PARTITION BY sku ORDER BY feed_at DESC, feed_id DESC)` rồi lọc `rn=1`. So sánh các feed được chọn với bài 4.

**Kỳ vọng:** cùng winner.

### Bài 7 — Vì sao RANK không đảm bảo một hàng?

Chạy `RANK() OVER (PARTITION BY sku ORDER BY feed_at DESC)` cho `CABLE-01`. Giải thích vì sao hai feed cùng timestamp có thể cùng `RANK=1`. Nếu lọc theo `RANK=1` rồi dùng `UPDATE FROM` thì còn rủi ro gì?

### Bài 8 — Cùng timestamp nhưng khác giá

Với `CABLE-01`, dùng `MAX(new_price)` sẽ nhận **130000** hay **125000**? Còn thứ tự `feed_at DESC, feed_id DESC` chọn giá nào?

**Đáp án:** `MAX` chọn 130000; thứ tự winner chọn 125000. Hãy nêu rõ vì sao không thể thay quy tắc “mới nhất” bằng `MAX(price)`.

### Bài 9 — Aggregate đúng nghiệp vụ tồn kho

Từ bảng `stock_movements`, tổng hợp `SUM(delta_qty)` theo SKU với `is_posted=TRUE` rồi dùng `UPDATE FROM` lên `stock_balance`.

**Đáp án trong transaction:** BK-01=59, MOUSE-01=15, PEN-01=90. Sau đó rollback.

### Bài 10 — Chọn một movement là lỗi

Nếu viết `SET on_hand = on_hand + m.delta_qty` với mỗi SKU có nhiều movement, điều gì xảy ra? Có phải PostgreSQL sẽ cộng tất cả biến động tuần tự không?

**Đáp án:** không; một hàng join được dùng để cấp `delta_qty`, gây nguy cơ bỏ các movement còn lại.

### Bài 11 — Scalar subquery nhiều hàng

Viết scalar subquery lấy `new_price` của approved feed cho `BK-01` **không giới hạn số hàng**, trong một transaction có savepoint. Quan sát lỗi cardinality, rollback về savepoint. Giải thích vì sao lỗi này hữu ích để phát hiện giả định cardinality bị sai.

### Bài 12 — Scalar subquery không có hàng

Nếu dùng `SET unit_price=(SELECT new_price FROM feed WHERE sku=p.sku AND is_approved)` cho tất cả sản phẩm mà không `WHERE EXISTS`, điều gì xảy ra với `BAG-01`? Vì sao schema `unit_price NOT NULL` có thể khiến command thất bại?

### Bài 13 — Nguồn không có đích

Tìm những SKU đã duyệt trong feed nhưng không có trong `products` bằng `LEFT JOIN` hoặc `NOT EXISTS`.

**Đáp án:** `UNKNOWN-01` (feed 107).

### Bài 14 — Đích không có nguồn approved

Tìm sản phẩm không có nguồn approved.

**Đáp án:** `PEN-01` và `BAG-01`.

### Bài 15 — Duplicate do join phụ

Join winner theo SKU tới `provider_contacts`. Đếm số hàng mỗi SKU sau join. Giải thích vì sao kết quả winner đã unique **vẫn có thể bị nhân hàng**, và khi nào dùng `EXISTS` thay join.

### Bài 16 — Chỉ cập nhật khi giá khác

Thêm điều kiện:

~~~sql
AND p.unit_price IS DISTINCT FROM w.new_price
~~~

vào `UPDATE` dùng winner. Chạy hai lần **trong cùng transaction** (không rollback giữa hai lần) và so số hàng `RETURNING` của lần đầu/lần sau, rồi rollback cuối cùng. Vì sao cập nhật metadata `price_source_note` cần quy tắc khác?

### Bài 17 — Staging có primary key

Tạo `TEMP TABLE selected_price_feed(sku PRIMARY KEY, ...)`, chèn winner và thử chèn thêm một dòng **cùng SKU** với giá khác. Quan sát lỗi unique violation `23505` trong savepoint; rollback về savepoint. Giải thích lợi ích của constraint trong pipeline ETL.

### Bài 18 — CTE nhiều bước

Tổ chức truy vấn thành `approved` → `ranked` → `winner` → `UPDATE RETURNING`. Kiểm tra logic của từng CTE có đúng một nhiệm vụ rõ ràng hay không.

### Bài 19 — Self-join

Dùng `UPDATE staff AS employee SET manager_name_cache = manager.staff_name FROM staff AS manager WHERE employee.manager_id=manager.staff_id` trên bảng lab. Vì sao `staff_id PRIMARY KEY` bảo đảm một manager khớp tối đa một hàng nguồn?

### Bài 20 — Kiểm tra COUNT(*) sau LEFT JOIN

Viết một báo cáo thống kê số hàng feed approved theo **mọi sản phẩm** bằng `LEFT JOIN`. So sánh `COUNT(*)` với `COUNT(f.feed_id)` ở BAG-01.

**Đáp án:** `COUNT(*)=1` trên hàng outer join không match, `COUNT(f.feed_id)=0`.

### Bài 21 — Chọn batch idempotent

Thiết kế metadata `batch_id`, `feed_id`, `applied_feed_at` để cùng một batch chạy lại không làm giá nhảy ngược. Hãy trình bày **quy tắc winner**, **điều kiện phiên bản** và **audit** cần có trước khi triển khai.

### Bài 22 — Kiểm tra plan

Dùng `EXPLAIN` (không `ANALYZE`) cho câu `UPDATE` có `DISTINCT ON`. Liệt kê các thành phần có thể thấy (scan nguồn, unique/sort, join tới target, update) và giải thích vì sao plan thực tế phụ thuộc thống kê.

### Bài 23 — Code review một câu lệnh nguy hiểm

Đồng nghiệp đề xuất:

~~~sql
UPDATE product AS p
SET price = s.price
FROM (
    SELECT sku, price
    FROM supplier_prices
    ORDER BY changed_at DESC
) AS s
WHERE s.sku = p.sku;
~~~

Hãy liệt kê ít nhất **5 vấn đề/câu hỏi** cần giải quyết trước khi approve:

1. Có bao nhiêu hàng nguồn cho mỗi SKU?
2. `ORDER BY` đã chọn winner mỗi SKU chưa?
3. Nếu timestamp trùng, dùng tie-breaker nào?
4. Nguồn đã được duyệt/hợp lệ chưa?
5. Điều gì xảy ra với SKU không có nguồn?
6. Có cần lưu phiên bản/nguồn đã áp dụng?
7. Có transaction/audit/rollback plan và đo tác động dự kiến không?

### Bài 24 — Chọn chiến lược đúng

Với bốn tình huống sau, hãy chọn cách xử lý trước `UPDATE FROM`:

| Tình huống | Gợi ý |
| --- | --- |
| Nhiều đề xuất giá theo thời gian | Chọn một winner theo thời gian + tie-break |
| Nhiều giao dịch nhập/xuất kho | `GROUP BY` và `SUM(delta_qty)` |
| Một SKU trong staging bắt buộc đúng một hàng | `PRIMARY KEY/UNIQUE` trên staging |
| Chỉ cần biết một nhà cung cấp có liên hệ hợp lệ | `EXISTS` thay join 1:N |

Giải thích vì sao **không có một cách khử trùng chung** phù hợp cho mọi nghiệp vụ.

## 28. Mẫu quy trình an toàn có thể tái sử dụng

<escape>**1. Xác định khóa đích:**</escape> một hàng đích ứng với đối tượng nào? SKU, order_id, user_id hay cặp khóa tổng hợp? Khóa có `UNIQUE` không?

<escape>**2. Xác định ngữ nghĩa nguồn:**</escape> nhiều bản ghi có phải những **phiên bản thay thế** nhau, những **giao dịch cần cộng**, hay các **chi tiết phụ** không?

<escape>**3. Tạo một hàng nguồn đúng ý nghĩa cho mỗi khóa:**</escape> dùng `DISTINCT ON`/`ROW_NUMBER` với thứ tự, `GROUP BY` với aggregate, hoặc staging `UNIQUE`.

<escape>**4. Kiểm tra cardinality cuối cùng:**</escape> sau **tất cả join**, nhóm theo khóa đích và tìm `HAVING COUNT(*) > 1`. Không chỉ tin nguồn ban đầu unique.

<escape>**5. Phân loại giá trị thiếu:**</escape> đích không có nguồn, nguồn không có đích, nguồn có NULL/corrupt, bản ghi chưa duyệt, batch cũ.

<escape>**6. Xem trước tác động:**</escape> `SELECT` khóa đích, giá cũ, giá mới, ID nguồn, số hàng dự kiến. Không lấy `RETURNING` làm kiểm tra duy nhất sau khi ghi.

<escape>**7. Bảo vệ concurrency:**</escape> chốt batch, so phiên bản, chọn isolation/locking và cơ chế idempotency nếu nhiều worker có thể ghi cùng hàng.

<escape>**8. UPDATE và audit trong transaction:**</escape> hạn chế phạm vi, dùng `RETURNING`, kiểm tra count và ghi lịch sử đúng nghiệp vụ.

<escape>**9. Xác minh rồi commit:**</escape> nếu kết quả không phù hợp, rollback. Trên production, sử dụng migration/runbook được duyệt và có cơ chế phục hồi.

### 28.1. Một mẫu thực thi an toàn cho bài lab

~~~sql
BEGIN;

WITH winner AS (
    SELECT DISTINCT ON (f.sku)
        f.sku,
        f.feed_id,
        f.new_price
    FROM upd_lab_201.price_feed AS f
    WHERE f.is_approved
    ORDER BY f.sku, f.feed_at DESC, f.feed_id DESC
)
UPDATE upd_lab_201.products AS p
SET
    unit_price = w.new_price,
    price_source_note = 'feed=' || w.feed_id::text,
    updated_at = clock_timestamp()
FROM winner AS w
WHERE p.sku = w.sku
  AND (
      p.unit_price IS DISTINCT FROM w.new_price
      OR p.price_source_note
         IS DISTINCT FROM ('feed=' || w.feed_id::text)
  )
RETURNING
    p.product_id,
    p.sku,
    p.unit_price,
    p.price_source_note,
    w.feed_id;

ROLLBACK;
~~~

Đặc điểm:

- Nguồn `winner` trả một hàng mỗi SKU theo quy tắc mới nhất + ID lớn nhất khi hòa.
- `WHERE p.sku = w.sku` nối theo khóa nghiệp vụ có unique ở target.
- `IS DISTINCT FROM` tránh ghi khi **cả giá và ghi chú nguồn đều đã đúng**.
- `RETURNING` cho phép thấy những sản phẩm đã bị tác động.
- `ROLLBACK` giúp thực hành nhiều lần mà không biến đổi seed.

Trong production, mẫu này còn cần ràng buộc phiên bản/batch, quy tắc dữ liệu và audit tùy mục tiêu. **Không copy nguyên câu rồi áp dụng đại trà cho một hệ thống chưa xác nhận chính sách giá.**

## 29. Tài liệu PostgreSQL chính thức

- [UPDATE — PostgreSQL Documentation](https://www.postgresql.org/docs/current/sql-update.html): cú pháp `UPDATE ... FROM`, cảnh báo nhiều hàng join khớp một hàng đích, `RETURNING` và trường hợp dùng subquery.
- [SELECT / DISTINCT ON](https://www.postgresql.org/docs/current/sql-select.html): `DISTINCT ON`, `ORDER BY` và lựa chọn hàng đầu trong nhóm.
- [Window Functions](https://www.postgresql.org/docs/current/functions-window.html): `ROW_NUMBER`, `RANK`, `PARTITION BY`.
- [Common Table Expressions](https://www.postgresql.org/docs/current/queries-with.html): `WITH`, data-modifying statements và `RETURNING`.
- [Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html): snapshot và ảnh hưởng của cập nhật đồng thời.
- [MERGE](https://www.postgresql.org/docs/current/sql-merge.html): các nhánh match/no match và những lưu ý cardinality.
- [INSERT / ON CONFLICT](https://www.postgresql.org/docs/current/sql-insert.html): cú pháp upsert và ràng buộc cardinality khi conflict.
- [EXPLAIN](https://www.postgresql.org/docs/current/sql-explain.html): phân tích kế hoạch và việc `EXPLAIN ANALYZE` thực thi câu lệnh.

Các URL `/docs/current/` trỏ tới bản tài liệu ổn định hiện hành. Khi hệ thống chạy một major version cụ thể, hãy đối chiếu đúng tài liệu phiên bản đó, đặc biệt với những tính năng mới của `RETURNING` hoặc `MERGE`.

## 30. Tổng kết

**`UPDATE ... FROM` là công cụ thuận tiện để cập nhật bảng đích dựa vào dữ liệu bảng nguồn, nhưng nó không tự bảo đảm chọn đúng một hàng nguồn cho mỗi hàng đích.** Nếu join tạo nhiều hàng nguồn khớp một hàng đích, PostgreSQL dùng một hàng join để cập nhật và **không đảm bảo lựa chọn nào sẽ được dùng**. Do đó, không được coi thứ tự chèn, index, `ORDER BY` không có bước chọn winner, hay kết quả chạy thử là bằng chứng truy vấn đúng.

Cách xử lý phụ thuộc bản chất nguồn: với **nhiều phiên bản**, chọn đúng bản ghi ưu tiên bằng `DISTINCT ON` hoặc `ROW_NUMBER()=1` kèm tie-breaker; với **nhiều biến động cần cộng**, tổng hợp bằng `GROUP BY`/`SUM`; với batch nghiêm ngặt, dùng **staging table có `PRIMARY KEY/UNIQUE`**. Scalar subquery có thể báo lỗi khi nhiều hàng thay vì chọn tùy ý, nhưng vẫn phải giải quyết quy tắc nguồn và trường hợp không có hàng.

Trước khi ghi, hãy **kiểm tra cardinality sau mọi join**, xem trước thay đổi bằng `SELECT`, phân loại nguồn/đích không khớp, bảo vệ transaction và concurrency, rồi dùng `RETURNING` để đối soát. Một phép cập nhật **đúng số hàng** chưa chắc cập nhật **đúng giá trị**: chất lượng của `UPDATE ... FROM` được quyết định trước hết bởi **tính duy nhất và ý nghĩa của dữ liệu nguồn mà bạn đã thiết kế**.
