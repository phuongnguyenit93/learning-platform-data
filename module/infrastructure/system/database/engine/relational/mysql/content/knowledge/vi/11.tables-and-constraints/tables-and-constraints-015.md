# Kiểm tra dữ liệu mồ côi và rủi ro khi tắt foreign_key_checks

Trong hệ thống bán hàng, mỗi dòng `order_items` phải tham chiếu đến một đơn hàng có thật trong `orders`. Nếu một tiến trình import ghi chi tiết đơn hàng trước khi tạo đơn hàng, hoặc một script tắt kiểm tra khóa ngoại rồi nạp dữ liệu sai, bảng con có thể chứa `order_id` không tồn tại ở bảng cha. Những hàng như vậy được gọi là **dữ liệu mồ côi** (orphan rows).

MySQL có thể bảo vệ quan hệ cha-con bằng foreign key, nhưng biến `foreign_key_checks` cho phép tạm tắt việc kiểm tra này trong một session hoặc thay đổi mặc định cho các kết nối mới. Việc bật lại biến không tự quét và xác minh những hàng đã được ghi trong thời gian kiểm tra bị tắt. Vì vậy, cần biết cách phát hiện orphan, xử lý dữ liệu sai và kiểm soát chặt mọi quy trình có sử dụng `foreign_key_checks=0`.

## 1. Dữ liệu mồ côi là gì?

Một foreign key (khóa ngoại) quy định giá trị ở bảng con phải tham chiếu đến một khóa hợp lệ ở bảng cha, trừ trường hợp khóa ngoại được phép `NULL` theo quy tắc của MySQL.

Ví dụ:

```sql
CREATE TABLE customers (
    id BIGINT UNSIGNED NOT NULL,
    full_name VARCHAR(150) NOT NULL,
    PRIMARY KEY (id)
) ENGINE=InnoDB;

CREATE TABLE orders (
    id BIGINT UNSIGNED NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_orders_customer_id (customer_id),
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers (id)
        ON UPDATE RESTRICT
        ON DELETE RESTRICT
) ENGINE=InnoDB;
```

Mỗi `orders.customer_id` phải khớp với `customers.id`. Nếu bảng `orders` có hàng `customer_id = 900` nhưng không có khách hàng `id = 900`, hàng đơn hàng đó là orphan đối với quan hệ `fk_orders_customer`.

Phân biệt hai trường hợp:

- **Orphan child:** hàng con có khóa ngoại khác `NULL` nhưng không tìm thấy hàng cha tương ứng. Đây là vấn đề toàn vẹn tham chiếu.
- **Parent không có child:** hàng cha chưa được hàng con nào tham chiếu. Ví dụ khách hàng chưa đặt đơn hàng. Đây thường là trạng thái nghiệp vụ hợp lệ, không phải orphan.

Không nên xóa một hàng cha chỉ vì nó không có hàng con, và cũng không nên xóa hàng con chỉ vì truy vấn phát hiện nó đang mồ côi. Trước hết phải xác định quan hệ và ý nghĩa nghiệp vụ của dữ liệu.

## 2. Foreign key bảo vệ dữ liệu như thế nào?

Với InnoDB, foreign key được kiểm tra trong các thao tác có thể phá vỡ quan hệ tham chiếu:

- Khi `INSERT` hoặc `UPDATE` hàng con, giá trị khóa ngoại phải tham chiếu đến hàng cha hợp lệ, trừ trường hợp được miễn kiểm tra do `NULL`.
- Khi `DELETE` hoặc `UPDATE` khóa được tham chiếu ở bảng cha, hành vi tuân theo `ON DELETE` và `ON UPDATE` như `RESTRICT`, `CASCADE` hoặc `SET NULL`.
- Constraint được lưu trong metadata của schema và được áp dụng khi `foreign_key_checks` đang bật.

Các kiểu dữ liệu của cột khóa ngoại và cột được tham chiếu phải tương thích. Với kiểu số, cần chú ý kích thước và thuộc tính `UNSIGNED`; với kiểu chuỗi, cần chú ý character set và collation. Bảng liên quan phải dùng storage engine hỗ trợ foreign key, phổ biến nhất là InnoDB.

InnoDB cần index để kiểm tra quan hệ. Cột được tham chiếu phải có index phù hợp, thường là `PRIMARY KEY` hoặc `UNIQUE`; phía bảng con cũng cần index trên các cột khóa ngoại. Nếu chưa có index phía con, InnoDB có thể tự tạo index khi khai báo foreign key. Nên chủ động thiết kế và đặt tên index để cấu trúc dễ đọc, dễ quản lý.

## 3. foreign_key_checks là gì?

`foreign_key_checks` là biến hệ thống điều khiển việc MySQL thực hiện kiểm tra foreign key. Giá trị thường dùng:

| Giá trị | Ý nghĩa |
|---|---|
| `1` hoặc `ON` | Bật kiểm tra foreign key |
| `0` hoặc `OFF` | Tắt kiểm tra foreign key trong phạm vi cấu hình |

Kiểm tra giá trị hiện tại:

```sql
SELECT
    @@SESSION.foreign_key_checks AS session_fk_checks,
    @@GLOBAL.foreign_key_checks AS global_fk_checks;
```

### 3.1. Phạm vi SESSION và GLOBAL

`foreign_key_checks` có phạm vi session và global:

- `SET SESSION foreign_key_checks = 0` chỉ tắt kiểm tra trong connection hiện tại.
- `SET GLOBAL foreign_key_checks = 0` thay đổi giá trị mặc định cho các connection được tạo sau đó; các session đang mở giữ trạng thái session riêng của chúng.
- Khi session kết thúc, trạng thái session của nó cũng kết thúc. Một connection được giữ trong connection pool có thể tiếp tục mang giá trị đã thay đổi nếu ứng dụng không reset.

Ví dụ chỉ tắt trong một session:

```sql
SET SESSION foreign_key_checks = 0;

-- Thao tác import được kiểm soát tại đây.

SET SESSION foreign_key_checks = 1;
```

Không dùng `SET GLOBAL` cho một lần import thông thường. Thay đổi global có thể làm các connection mới trong toàn hệ thống bỏ qua kiểm tra, khiến nhiều luồng ghi độc lập tạo dữ liệu không hợp lệ.

### 3.2. Bật lại không có nghĩa dữ liệu cũ đã được kiểm tra

Đây là điểm quan trọng nhất khi vận hành MySQL: **đặt `foreign_key_checks = 1` không khiến MySQL quét lại các hàng đã được ghi trong thời gian checks bị tắt**.

Ví dụ:

1. Session A tắt `foreign_key_checks`.
2. Session A chèn một hàng con có `customer_id` không tồn tại.
3. Session A bật lại `foreign_key_checks`.
4. Hàng con sai vẫn nằm trong bảng; MySQL không tự xóa, sửa hoặc từ chối hồi tố hàng đó.

Sau bước 3, các thao tác mới trong session sẽ được kiểm tra lại, nhưng orphan đã tạo trước đó vẫn tồn tại. Do đó, sau mỗi lần import hoặc migration có tắt checks, phải chạy truy vấn audit để xác minh dữ liệu.

## 4. Phát hiện orphan với khóa ngoại đơn

Giả sử `orders.customer_id` tham chiếu `customers.id`. Có hai mẫu truy vấn phổ biến.

### 4.1. LEFT JOIN và IS NULL

```sql
SELECT
    o.id AS order_id,
    o.customer_id
FROM orders AS o
LEFT JOIN customers AS c
    ON c.id = o.customer_id
WHERE o.customer_id IS NOT NULL
  AND c.id IS NULL;
```

`LEFT JOIN` giữ lại mọi hàng ở bảng con. Nếu không tìm được khách hàng tương ứng, các cột của phía `customers` nhận `NULL`; điều kiện `c.id IS NULL` chọn những hàng không có cha.

Điều kiện `o.customer_id IS NOT NULL` làm rõ rằng quan hệ tùy chọn có thể không có giá trị tham chiếu. Nếu cột là `NOT NULL`, điều kiện này không cần thiết nhưng vẫn giúp người đọc hiểu ý định.

### 4.2. NOT EXISTS

```sql
SELECT
    o.id AS order_id,
    o.customer_id
FROM orders AS o
WHERE o.customer_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM customers AS c
      WHERE c.id = o.customer_id
  );
```

`NOT EXISTS` diễn đạt trực tiếp ý nghĩa: không tồn tại hàng cha có khóa bằng khóa ngoại của hàng con. Đây là mẫu dễ mở rộng khi quan hệ có nhiều cột hoặc có thêm điều kiện.

### 4.3. Đếm trước, xem mẫu sau

Trên bảng lớn, nên đếm số orphan trước rồi mới lấy danh sách chi tiết:

```sql
SELECT COUNT(*) AS orphan_count
FROM orders AS o
WHERE o.customer_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM customers AS c
      WHERE c.id = o.customer_id
  );
```

Lấy một số hàng để điều tra:

```sql
SELECT o.id, o.customer_id, o.created_at
FROM orders AS o
WHERE o.customer_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM customers AS c
      WHERE c.id = o.customer_id
  )
ORDER BY o.id
LIMIT 100;
```

Không xuất toàn bộ hàng mồ côi ra terminal hoặc log nếu bảng chứa thông tin cá nhân. Hãy lấy các cột định danh tối thiểu, che dữ liệu nhạy cảm và giới hạn số hàng.

## 5. Phát hiện orphan với khóa ngoại ghép

Một foreign key có thể gồm nhiều cột. Ví dụ, bảng `order_lines` dùng khóa ghép `(order_id, line_no)` để định danh một dòng hàng; bảng `shipment_items` tham chiếu đến cặp khóa này.

```sql
CREATE TABLE order_lines (
    order_id BIGINT UNSIGNED NOT NULL,
    line_no INT UNSIGNED NOT NULL,
    product_id BIGINT UNSIGNED NOT NULL,
    PRIMARY KEY (order_id, line_no)
) ENGINE=InnoDB;

CREATE TABLE shipment_items (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    order_id BIGINT UNSIGNED NULL,
    line_no INT UNSIGNED NULL,
    shipped_qty INT UNSIGNED NOT NULL,
    PRIMARY KEY (id),
    KEY idx_shipment_order_line (order_id, line_no),
    CONSTRAINT fk_shipment_order_line
        FOREIGN KEY (order_id, line_no)
        REFERENCES order_lines (order_id, line_no)
) ENGINE=InnoDB;
```

Truy vấn kiểm tra orphan:

```sql
SELECT
    s.id,
    s.order_id,
    s.line_no
FROM shipment_items AS s
WHERE s.order_id IS NOT NULL
  AND s.line_no IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM order_lines AS ol
      WHERE ol.order_id = s.order_id
        AND ol.line_no = s.line_no
  );
```

Với foreign key ghép trong MySQL, nếu **bất kỳ thành phần nào của khóa ngoại là `NULL`**, hàng đó không phải tham chiếu bắt buộc đến một hàng cha và được miễn kiểm tra quan hệ. Vì vậy, khi tìm orphan theo quy tắc này, chỉ kiểm tra những hàng có đầy đủ tất cả thành phần khác `NULL`.

Nếu nghiệp vụ yêu cầu cặp khóa phải luôn có đủ hai giá trị, nên khai báo cả hai cột `NOT NULL`. Nếu cho phép quan hệ tùy chọn, hãy quy định rõ trường hợp một phần `NULL` có ý nghĩa gì; tránh để dữ liệu nửa cặp như `order_id` có giá trị nhưng `line_no` lại `NULL` nếu nghiệp vụ không chấp nhận.

## 6. Khám phá các foreign key đang tồn tại

Trước khi viết truy vấn audit, cần biết constraint nào đang được khai báo, cột nào tham gia và bảng nào được tham chiếu.

### 6.1. Liệt kê foreign key trong schema hiện tại

```sql
SELECT
    CONSTRAINT_SCHEMA,
    TABLE_NAME,
    CONSTRAINT_NAME,
    REFERENCED_TABLE_NAME,
    UPDATE_RULE,
    DELETE_RULE
FROM INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS
WHERE CONSTRAINT_SCHEMA = DATABASE()
ORDER BY TABLE_NAME, CONSTRAINT_NAME;
```

View `REFERENTIAL_CONSTRAINTS` cung cấp tên constraint và hành vi `ON UPDATE`/`ON DELETE`.

### 6.2. Xem các cột của từng khóa ngoại

```sql
SELECT
    CONSTRAINT_SCHEMA,
    TABLE_NAME,
    CONSTRAINT_NAME,
    COLUMN_NAME,
    ORDINAL_POSITION,
    REFERENCED_TABLE_SCHEMA,
    REFERENCED_TABLE_NAME,
    REFERENCED_COLUMN_NAME
FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
WHERE TABLE_SCHEMA = DATABASE()
  AND REFERENCED_TABLE_NAME IS NOT NULL
ORDER BY TABLE_NAME, CONSTRAINT_NAME, ORDINAL_POSITION;
```

`ORDINAL_POSITION` cho biết thứ tự cột trong khóa ghép. Hãy ghép các cột cùng `CONSTRAINT_SCHEMA`, `TABLE_NAME` và `CONSTRAINT_NAME` để dựng đúng cặp cột con-cha. Không kiểm tra từng cột độc lập nếu constraint là khóa ghép; cần so sánh toàn bộ tuple.

### 6.3. Xác minh DDL thực tế

```sql
SHOW CREATE TABLE orders\G
SHOW CREATE TABLE order_lines\G
SHOW CREATE TABLE shipment_items\G
```

`SHOW CREATE TABLE` cho biết constraint đang được định nghĩa trên server, tên index, kiểu cột và engine. Đối chiếu DDL thực tế với migration trong mã nguồn nếu nghi ngờ schema drift.

Các view metadata chỉ hiển thị đối tượng mà tài khoản hiện tại có quyền nhìn thấy. Nếu một constraint không xuất hiện, kiểm tra schema đang chọn và quyền trước khi kết luận constraint không tồn tại.

## 7. Orphan khác với parent không được sử dụng

Truy vấn tìm parent chưa có child có mục đích khác với truy vấn tìm orphan.

Ví dụ tìm khách hàng chưa có đơn hàng:

```sql
SELECT c.id, c.full_name
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.id
);
```

Đây có thể là báo cáo khách hàng chưa mua hàng, không phải lỗi toàn vẹn. Một orphan là hàng con không có cha; một parent không có child là hàng cha chưa được tham chiếu. Hai khái niệm có hướng kiểm tra ngược nhau.

Không dùng truy vấn parent không có child để quyết định xóa hàng loạt nếu chưa kiểm tra các quan hệ khác, thời hạn lưu trữ và quy tắc nghiệp vụ.

## 8. Vì sao orphan có thể xuất hiện?

Trong hệ thống được thiết kế và vận hành đúng, foreign key giúp ngăn orphan mới. Tuy nhiên, dữ liệu mồ côi vẫn có thể xuất hiện trong các trường hợp:

- Một tiến trình đã tắt `foreign_key_checks` rồi import hàng con tham chiếu đến parent không tồn tại.
- Dữ liệu được nạp từ file cũ, hệ thống khác hoặc bản dump không nhất quán.
- Ứng dụng ghi dữ liệu vào bảng không có foreign key hoặc dùng storage engine không enforce constraint.
- Một migration bỏ constraint, đổi kiểu dữ liệu hoặc đổi cấu trúc quan hệ không đầy đủ.
- Dữ liệu được sửa trực tiếp bởi script quản trị, ETL hoặc công cụ đồng bộ.
- Hệ thống từng dùng MyISAM hoặc engine không hỗ trợ foreign key, sau đó chuyển sang InnoDB nhưng chưa làm sạch dữ liệu.
- Một phần dữ liệu được phục hồi từ backup ở các thời điểm khác nhau, làm quan hệ cha-con không còn đồng bộ.

Nếu phát hiện orphan dù `foreign_key_checks` hiện đang bật, đừng giả định MySQL đã bỏ qua constraint. Kiểm tra thời điểm dữ liệu được ghi, engine của bảng, constraint thực tế, session nào đã thực hiện import và lịch sử migration.

## 9. Rủi ro khi tắt foreign_key_checks

Tắt kiểm tra có thể hữu ích trong một số quy trình import có kiểm soát, nhưng nó loại bỏ lớp bảo vệ tham chiếu trong phạm vi session bị ảnh hưởng.

### 9.1. Có thể ghi dữ liệu không có parent

Khi checks tắt, câu `INSERT` hoặc `UPDATE` có thể ghi giá trị khóa ngoại không tồn tại ở bảng cha. Những hàng này vẫn còn sau khi checks bật lại.

Ví dụ trong session thử nghiệm:

```sql
SET SESSION foreign_key_checks = 0;

INSERT INTO orders (id, customer_id)
VALUES (7001, 999999);

SET SESSION foreign_key_checks = 1;
```

Nếu khách hàng `999999` không tồn tại, hàng đơn hàng vẫn có thể được lưu. Lệnh bật lại không tự rollback hoặc xóa hàng này.

### 9.2. Có thể tạo khoảng trống trong tính toàn vẹn tham chiếu

Trong thời gian checks tắt, hệ thống có thể:

- Ghi hàng con trước khi hàng cha được nạp.
- Thay đổi khóa tham chiếu mà không có hàng cha tương ứng.
- Thực hiện thay đổi cấu trúc hoặc import khiến các quan hệ không còn đồng nhất.
- Để các luồng ứng dụng đọc thấy dữ liệu chưa hoàn chỉnh.

Nếu có nhiều tiến trình hoặc nhiều session cùng thao tác, cần xác định chính xác connection nào đã tắt checks. `SET SESSION` chỉ ảnh hưởng session đó; một thao tác tắt GLOBAL lại có thể ảnh hưởng các connection mới, mở rộng phạm vi rủi ro.

### 9.3. Bật lại không xác nhận dữ liệu hợp lệ

Không có bước tự động kiểm tra lại dữ liệu cũ khi đặt biến về `1`. Vì vậy, câu lệnh:

```sql
SET SESSION foreign_key_checks = 1;
```

chỉ khôi phục việc kiểm tra cho các thao tác tiếp theo trong session. Nó không chứng minh các hàng hiện có đã tuân thủ foreign key.

### 9.4. Tắt checks không phải cách sửa lỗi foreign key

Nếu `INSERT` báo lỗi `1452`, nguyên nhân thường là hàng cha chưa tồn tại hoặc giá trị khóa ngoại sai. Tắt checks để lệnh chạy qua chỉ che giấu lỗi và có thể tạo orphan. Hãy kiểm tra parent, dữ liệu đầu vào và thứ tự import trước.

Nếu `DELETE` hoặc `UPDATE` parent báo lỗi `1451`, cần xem quan hệ child và quy tắc `ON DELETE`/`ON UPDATE`. Không tắt checks để xóa parent khi chưa xác định dữ liệu con cần giữ, chuyển hoặc xóa theo nghiệp vụ.

## 10. Khi nào có thể tạm tắt foreign_key_checks?

Một số tình huống có thể cân nhắc tắt checks trong một session cô lập:

- Import bộ dữ liệu lớn đã được xác minh từ nguồn đáng tin cậy và có quy trình audit sau import.
- Nạp nhiều bảng theo thứ tự không thuận tiện, nhưng bộ dữ liệu đã được kiểm tra quan hệ trước.
- Tạo lại hoặc phục hồi schema trong môi trường bảo trì, khi toàn bộ quy trình được kiểm soát.

Ngay cả trong các trường hợp này, lựa chọn ưu tiên vẫn là nạp bảng cha trước rồi nạp bảng con để giữ checks bật. Chỉ tắt khi có lý do kỹ thuật rõ ràng và lợi ích đã được đo lường.

Không nên tắt checks trong các tình huống:

- Request nghiệp vụ thông thường của ứng dụng.
- Giao dịch thanh toán, đơn hàng, tồn kho hoặc số dư.
- Script chạy định kỳ không có bước audit và báo cáo lỗi.
- Production đang nhận ghi đồng thời mà không có cửa sổ bảo trì hoặc kế hoạch kiểm soát.
- Khi chưa biết các foreign key nào bị ảnh hưởng và chưa có cách sửa orphan.

## 11. Quy trình import an toàn nếu bắt buộc tắt checks

Giả sử cần nạp dữ liệu từ file dump vào một schema đã được tạo. Hãy thực hiện trong một connection riêng, ghi log và có thể kiểm soát toàn bộ tiến trình.

### Bước 1: Xác nhận nguồn và cấu trúc

- Kiểm tra file nguồn, thời điểm export và schema đích.
- Xác nhận engine và DDL của các bảng.
- Liệt kê foreign key bằng `INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS` và `KEY_COLUMN_USAGE`.
- Đảm bảo có backup và phương án phục hồi.
- Nếu có thể, sắp xếp import parent trước child để không cần tắt checks.

### Bước 2: Lưu trạng thái ban đầu của session

```sql
SET @old_foreign_key_checks = @@SESSION.foreign_key_checks;
SELECT @old_foreign_key_checks;
```

Ghi nhận giá trị để khôi phục đúng trạng thái ban đầu. Không mặc định trạng thái ban đầu luôn là `1` nếu quy trình kết nối có thể đã thay đổi session.

### Bước 3: Tắt checks trong đúng session

```sql
SET SESSION foreign_key_checks = 0;
SELECT @@SESSION.foreign_key_checks;
```

Xác nhận kết quả là `0` trên đúng connection sẽ chạy import. Không mở một tab hoặc connection khác rồi giả định nó cũng có cùng trạng thái.

### Bước 4: Nạp dữ liệu và kiểm tra kết quả import

Thực hiện import trong cùng connection hoặc công cụ đã được cấu hình rõ phạm vi session. Kiểm tra exit code, log lỗi, số hàng nguồn/đích và các bảng đã nạp. Nếu công cụ tạo connection mới cho từng phần, phải kiểm tra mode trên từng connection; session setting không tự truyền sang connection khác.

### Bước 5: Bật lại ngay cả khi import thất bại

```sql
SET SESSION foreign_key_checks = @old_foreign_key_checks;
SELECT @@SESSION.foreign_key_checks;
```

Trong ứng dụng, việc khôi phục nên đặt trong khối cleanup tương đương `finally`. Không trả connection về pool nếu chưa khôi phục/reset trạng thái session. Nếu kết nối bị ngắt, session cũ kết thúc; khi mở connection mới, kiểm tra lại giá trị mặc định trước khi tiếp tục.

### Bước 6: Audit orphan trước khi mở lưu lượng

Chạy truy vấn orphan cho tất cả foreign key có liên quan, gồm khóa đơn và khóa ghép. Kiểm tra số lượng bằng `0`, hoặc có danh sách ngoại lệ được phê duyệt và xử lý rõ ràng. Chỉ mở lại lưu lượng ứng dụng khi dữ liệu đã đạt điều kiện toàn vẹn.

### Bước 7: Ghi nhận và đối soát

Lưu lại nguồn import, thời gian, connection, trạng thái checks trước/sau, số hàng nạp, số orphan phát hiện và hành động sửa. Nếu dữ liệu lớn, có thể chạy thêm kiểm tra checksum hoặc đối soát nghiệp vụ.

## 12. Xử lý dữ liệu mồ côi

Không có một cách sửa chung cho mọi orphan. Chọn hành động dựa trên ý nghĩa dữ liệu.

### 12.1. Khôi phục hàng cha bị thiếu

Nếu hàng con hợp lệ và hàng cha bị thiếu do import không đầy đủ, có thể khôi phục hàng cha từ nguồn chuẩn. Trước khi insert, xác minh khóa, thuộc tính bắt buộc và các quan hệ khác của parent.

```sql
-- Chỉ là ví dụ sau khi đã xác minh khách hàng 999999 thực sự tồn tại
-- trong nguồn chuẩn và có thể phục hồi.
INSERT INTO customers (id, full_name)
VALUES (999999, 'Khách hàng được khôi phục');
```

Không tạo một parent giả với tên như `Unknown` chỉ để làm biến mất kết quả orphan. Cách đó khiến dữ liệu có vẻ hợp lệ về mặt khóa nhưng sai về nghiệp vụ.

### 12.2. Sửa khóa ngoại sang parent đúng

Nếu `customer_id` bị gán nhầm, tìm đúng khách hàng từ nguồn chuẩn hoặc bảng mapping rồi cập nhật:

```sql
UPDATE orders
SET customer_id = 120
WHERE id = 7001
  AND customer_id = 999999;
```

Điều kiện cũ trong `WHERE` giúp tránh ghi đè nếu hàng đã được một tiến trình khác sửa. Trong hệ thống thực tế, cần xác nhận mapping và kiểm tra số hàng bị ảnh hưởng.

### 12.3. Đặt NULL nếu quan hệ là tùy chọn

Nếu nghiệp vụ cho phép đơn hàng không gắn với khách hàng, cột phải cho phép `NULL` và quy tắc nghiệp vụ phải chấp nhận trạng thái này:

```sql
UPDATE orders
SET customer_id = NULL
WHERE id = 7001
  AND customer_id = 999999;
```

Không dùng `NULL` để né constraint nếu quan hệ thực tế là bắt buộc. Trước khi sửa, kiểm tra ứng dụng, báo cáo và các truy vấn có giả định `customer_id` luôn tồn tại hay không.

### 12.4. Lưu trữ hoặc xóa hàng con

Nếu hàng con là dữ liệu thử nghiệm, rác import hoặc không còn giá trị nghiệp vụ, có thể archive hoặc xóa sau khi được phê duyệt. Trước khi xóa, lưu bản sao cần thiết, kiểm tra các bảng con khác và tính toán tác động đến báo cáo/audit.

Không chạy `DELETE` hàng loạt chỉ dựa trên một truy vấn orphan chưa được xem xét. Hãy tạo danh sách ID cần xử lý, đối chiếu với chủ sở hữu dữ liệu và kiểm tra số hàng bị ảnh hưởng.

## 13. Transaction và tính nhất quán khi audit

Truy vấn audit trên bảng InnoDB có thể quan sát dữ liệu thay đổi đồng thời. Nếu cần báo cáo tại một thời điểm nhất quán, có thể dùng consistent snapshot:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION WITH CONSISTENT SNAPSHOT;

SELECT COUNT(*) AS orphan_count
FROM orders AS o
WHERE o.customer_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM customers AS c
      WHERE c.id = o.customer_id
  );

COMMIT;
```

Với InnoDB, các consistent read trong transaction sử dụng cùng read view theo isolation level và thời điểm tạo snapshot. Kết quả cho biết trạng thái tại snapshot đó; dữ liệu có thể thay đổi sau khi transaction kết thúc.

Nếu cần vừa audit vừa sửa, phải kiểm soát các luồng ghi đồng thời. Có thể tạm dừng writer, dùng cửa sổ bảo trì hoặc triển khai quy trình sửa có khóa và điều kiện cập nhật rõ ràng. Một truy vấn `SELECT` audit đơn thuần không ngăn ứng dụng khác tạo thay đổi ngay sau đó.

Không giữ transaction snapshot quá lâu trên bảng lớn nếu không cần thiết. Read view dài có thể giữ phiên bản cũ trong undo log và làm tăng áp lực purge. Chia công việc theo batch hoặc dùng cửa sổ bảo trì phù hợp.

## 14. Thêm lại hoặc xác minh foreign key sau khi làm sạch

Nếu bảng chưa có foreign key, hãy audit và làm sạch dữ liệu trước khi thêm constraint:

```sql
ALTER TABLE orders
ADD CONSTRAINT fk_orders_customer
FOREIGN KEY (customer_id)
REFERENCES customers (id)
ON UPDATE RESTRICT
ON DELETE RESTRICT;
```

Khi checks đang bật, MySQL/InnoDB kiểm tra dữ liệu hiện có khi thêm foreign key; nếu có orphan, thao tác DDL có thể thất bại. DDL này có thể cần metadata lock và thực hiện công việc kiểm tra trên bảng lớn, nên phải đánh giá thời gian, tài nguyên và ảnh hưởng đến ứng dụng.

Nếu constraint đã tồn tại nhưng dữ liệu có thể đã được ghi khi checks tắt, bật lại biến không xác minh dữ liệu cũ. Hãy chạy audit query. Một cách buộc server kiểm tra lại dữ liệu theo định nghĩa constraint là thực hiện quy trình drop rồi add lại foreign key khi checks bật, sau khi đã làm sạch và trong cửa sổ bảo trì có kiểm soát. Đây là DDL có implicit commit, có thể cần khóa và có khoảng thời gian constraint không tồn tại; không coi nó là thao tác rollback được trong transaction thông thường.

Sau khi hoàn tất, xác minh:

```sql
SHOW CREATE TABLE orders\G

SELECT COUNT(*) AS orphan_count
FROM orders AS o
WHERE o.customer_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM customers AS c
      WHERE c.id = o.customer_id
  );
```

Kết quả cần cho thấy constraint đúng như mong đợi và không còn orphan trong quan hệ đó.

## 15. Hiệu năng khi kiểm tra orphan trên bảng lớn

Audit toàn bộ bảng có thể tốn I/O và CPU. Hãy tối ưu theo quy mô dữ liệu:

- Bảo đảm cột khóa ngoại phía con có index và cột được tham chiếu phía cha có index phù hợp.
- Dùng `NOT EXISTS` hoặc anti-join với điều kiện rõ ràng; đọc `EXPLAIN` để xem MySQL chọn kế hoạch nào.
- Đếm orphan trước; chỉ lấy chi tiết khi cần điều tra.
- Với bảng rất lớn, chia theo khoảng khóa chính hoặc thời gian để giảm lượng công việc mỗi batch.
- Chạy audit trong thời điểm tải thấp nếu truy vấn cạnh tranh tài nguyên với OLTP.
- Không thêm index trùng lặp chỉ để chạy audit một lần; cân nhắc chi phí ghi và dung lượng lâu dài.
- Ghi nhận thời gian chạy, số hàng quét và số orphan để so sánh giữa các lần audit.

Ví dụ kiểm tra theo dải ID:

```sql
SELECT COUNT(*) AS orphan_count
FROM orders AS o
WHERE o.id >= 100000
  AND o.id < 200000
  AND o.customer_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM customers AS c
      WHERE c.id = o.customer_id
  );
```

Chia batch chỉ là cách tổ chức công việc; để kết quả tổng thể nhất quán, cần cố định snapshot hoặc ngăn dữ liệu thay đổi trong toàn bộ khoảng audit. Nếu không, các batch chạy ở thời điểm khác nhau có thể phản ánh các trạng thái dữ liệu khác nhau.

## 16. Mã lỗi thường gặp liên quan đến foreign key

| Mã lỗi | Tình huống | Hướng điều tra |
|---:|---|---|
| `1452` | Không thể thêm/cập nhật hàng con vì không có hàng cha tương ứng | Kiểm tra giá trị FK, parent, thứ tự import và `foreign_key_checks` của session |
| `1451` | Không thể xóa/cập nhật hàng cha vì còn hàng con tham chiếu | Kiểm tra bảng con, số hàng tham chiếu và quy tắc `ON DELETE`/`ON UPDATE` |
| `1215` hoặc lỗi tạo FK tương ứng theo phiên bản | Không thể thêm foreign key | Kiểm tra engine, kiểu dữ liệu, signedness, charset/collation, index và tên constraint |
| `1005` với thông tin errno 150 trong một số trường hợp | Định nghĩa foreign key không đúng hoặc không tương thích | Đọc `SHOW ENGINE INNODB STATUS` và đối chiếu DDL hai bảng |

Sau lỗi tạo foreign key, có thể xem:

```sql
SHOW ENGINE INNODB STATUS\G
```

Phần `LATEST FOREIGN KEY ERROR` thường cung cấp thêm chi tiết về lần tạo hoặc thao tác foreign key thất bại gần nhất. Thông tin này có thể bị thay thế bởi lỗi mới, vì vậy hãy thu thập gần thời điểm xảy ra sự cố.

## 17. Checklist trước và sau khi tắt foreign_key_checks

Trước khi tắt:

- Tôi có lý do kỹ thuật cụ thể và đã thử nạp theo thứ tự parent trước child chưa?
- Đã xác định chính xác các foreign key và bảng bị ảnh hưởng chưa?
- Đã có backup, nguồn dữ liệu đáng tin cậy và kế hoạch phục hồi chưa?
- Có thể chạy trong một connection riêng và chỉ dùng `SESSION` không?
- Đã lưu giá trị `@@SESSION.foreign_key_checks` ban đầu chưa?
- Có writer khác hoặc connection pool có thể làm thay đổi session state không?

Sau khi import:

- Đã khôi phục `foreign_key_checks` về giá trị ban đầu chưa?
- Connection pool đã reset trạng thái trước khi trả connection chưa?
- Đã chạy audit cho từng khóa ngoại đơn và khóa ghép chưa?
- Các khóa ghép đã xử lý đúng hàng có một hoặc nhiều thành phần `NULL` chưa?
- Số orphan có bằng 0 hoặc đã được phê duyệt xử lý chưa?
- Đã xác minh DDL, số hàng, log lỗi và kết quả đối soát chưa?
- Đã ghi lại thời gian, nguồn import và kết quả audit chưa?

## Kết luận

Dữ liệu mồ côi là hàng con có khóa ngoại nhưng không tìm được hàng cha tương ứng. Dùng `LEFT JOIN ... IS NULL` hoặc `NOT EXISTS` để phát hiện, đồng thời xử lý đúng khóa ghép và các giá trị `NULL`. `foreign_key_checks=0` có thể hỗ trợ import được kiểm soát, nhưng nó cho phép dữ liệu vi phạm quan hệ đi vào bảng; bật lại checks không tự xác minh các hàng cũ. Hãy ưu tiên giữ checks bật, nạp parent trước child, chỉ tắt trong session riêng khi thật cần thiết và luôn audit, sửa dữ liệu, xác minh constraint trước khi mở lại lưu lượng ứng dụng.
