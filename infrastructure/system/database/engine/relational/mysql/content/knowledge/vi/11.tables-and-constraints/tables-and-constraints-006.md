# CHECK constraint và khác biệt thực thi giữa các phiên bản

`CHECK` constraint là ràng buộc dùng biểu thức Boolean để giới hạn giá trị hợp lệ của một hàng. Ví dụ, số lượng sản phẩm phải lớn hơn 0, giá không âm hoặc ngày bắt đầu không được sau ngày kết thúc. Ràng buộc được khai báo ngay trong schema để MySQL kiểm tra dữ liệu khi `INSERT` hoặc `UPDATE`.

Điểm quan trọng khi làm việc với MySQL là **phiên bản server quyết định `CHECK` có thực sự được thực thi hay không**. MySQL trước 8.0.16 chấp nhận cú pháp `CHECK` nhưng bỏ qua ràng buộc. Từ MySQL 8.0.16, `CHECK` được thực thi; có thể khai báo `ENFORCED` hoặc `NOT ENFORCED`. Vì vậy, nhìn thấy câu lệnh `CREATE TABLE` thành công hoặc thấy từ khóa `CHECK` trong DDL chưa đủ để kết luận dữ liệu đang được bảo vệ.

Bài học này giải thích cách khai báo, cách MySQL đánh giá biểu thức, giới hạn của `CHECK`, cách kiểm tra metadata và cách triển khai an toàn khi hệ thống có nhiều phiên bản MySQL.

## 1. CHECK constraint giải quyết vấn đề gì?

Một bảng có thể có kiểu dữ liệu hợp lệ nhưng vẫn nhận được giá trị không đúng quy tắc nghiệp vụ. Ví dụ, `quantity` là số nguyên nhưng số lượng âm không hợp lệ; `price` là số thập phân nhưng giá âm không được phép; `start_date` và `end_date` đều là ngày hợp lệ nhưng khoảng thời gian có thể bị đảo ngược.

Có thể kiểm tra các điều kiện này trong ứng dụng, nhưng nếu có nhiều ứng dụng, script import hoặc người quản trị cùng ghi database, mỗi nơi phải tự triển khai đúng một quy tắc. `CHECK` đặt điều kiện tại database để mọi câu lệnh ghi vào bảng đều chịu cùng một kiểm tra khi constraint được bật.

Ví dụ các quy tắc thường gặp:

| Quy tắc | Biểu thức CHECK minh họa |
| --- | --- |
| Số lượng phải dương | `quantity > 0` |
| Giá không âm | `unit_price >= 0` |
| Phần trăm nằm trong khoảng 0 đến 100 | `discount_percent BETWEEN 0 AND 100` |
| Ngày kết thúc không trước ngày bắt đầu | `start_date <= end_date` |
| Trạng thái thuộc tập giá trị cho phép | `status IN ('draft', 'active', 'archived')` |

`CHECK` phù hợp với quy tắc có thể đánh giá từ các giá trị trong cùng một hàng. Nó không thay thế primary key, unique constraint, foreign key hoặc validation nghiệp vụ phức tạp ở tầng ứng dụng.

## 2. Khác biệt phiên bản: trước và từ MySQL 8.0.16

Đây là điểm cần kiểm tra đầu tiên trước khi dựa vào `CHECK`:

| Phiên bản MySQL | Hành vi của CHECK |
| --- | --- |
| MySQL 5.7 và các phiên bản cũ hơn | Cú pháp `CHECK` được parser chấp nhận trong nhiều trường hợp nhưng constraint bị bỏ qua, không bảo vệ dữ liệu |
| MySQL 8.0.0 đến 8.0.15 | Tương tự: cú pháp được chấp nhận nhưng `CHECK` chưa được thực thi |
| MySQL 8.0.16 trở lên | `CHECK` được thực thi mặc định; có thể chỉ định `ENFORCED` hoặc `NOT ENFORCED` |
| MySQL 8.4 | Tiếp tục hỗ trợ thực thi `CHECK` theo cơ chế của MySQL 8.0.16 trở lên |

Ví dụ sau có thể chạy thành công trên cả phiên bản cũ và mới:

```sql
CREATE TABLE products (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    name VARCHAR(150) NOT NULL,
    price DECIMAL(13, 2) NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT chk_products_price_nonnegative
        CHECK (price >= 0)
) ENGINE=InnoDB;
```

Trên MySQL trước 8.0.16, câu lệnh có thể tạo bảng mà không báo lỗi, nhưng `price >= 0` không được thực thi. Một lệnh `INSERT` có giá âm vẫn có thể được chấp nhận. Trên MySQL 8.0.16 trở lên, constraint được thực thi mặc định và giá trị âm bị từ chối.

Kiểm tra phiên bản server trước khi triển khai:

```sql
SELECT VERSION() AS mysql_version;
```

Không dùng việc DDL chạy thành công làm bằng chứng rằng constraint hoạt động. Hãy kiểm tra phiên bản, trạng thái enforcement trong metadata và thử một giá trị vi phạm trên môi trường kiểm thử.

## 3. Cú pháp CHECK ở cấp cột và cấp bảng

Có thể khai báo `CHECK` ngay sau định nghĩa cột hoặc ở cấp bảng.

### 3.1. CHECK ở cấp cột

```sql
CREATE TABLE products (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    name VARCHAR(150) NOT NULL,
    price DECIMAL(13, 2) NOT NULL
        CONSTRAINT chk_products_price_nonnegative CHECK (price >= 0),
    PRIMARY KEY (id)
) ENGINE=InnoDB;
```

Cách này làm điều kiện gần với cột được kiểm tra, dễ đọc khi quy tắc chỉ liên quan một thuộc tính.

### 3.2. CHECK ở cấp bảng

```sql
CREATE TABLE order_items (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    order_id BIGINT UNSIGNED NOT NULL,
    quantity INT NOT NULL,
    unit_price DECIMAL(13, 2) NOT NULL,
    discount_percent DECIMAL(5, 2) NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    CONSTRAINT chk_order_items_quantity_positive
        CHECK (quantity > 0),
    CONSTRAINT chk_order_items_unit_price_nonnegative
        CHECK (unit_price >= 0),
    CONSTRAINT chk_order_items_discount_range
        CHECK (discount_percent BETWEEN 0 AND 100)
) ENGINE=InnoDB;
```

Table-level `CHECK` thuận tiện khi điều kiện kết hợp nhiều cột trong cùng một hàng. Ví dụ:

```sql
CONSTRAINT chk_events_date_range
    CHECK (starts_at <= ends_at)
```

Biểu thức chỉ được kiểm tra trên dữ liệu của hàng hiện tại. `CHECK` không thực hiện truy vấn sang bảng khác để kiểm tra một quy tắc liên bảng.

## 4. MySQL đánh giá CHECK như thế nào?

Khi `INSERT` hoặc `UPDATE`, MySQL đánh giá biểu thức của constraint. Kết quả có ba trạng thái theo logic SQL:

- `TRUE`: hàng thỏa điều kiện và được chấp nhận.
- `FALSE`: hàng vi phạm điều kiện và bị từ chối nếu constraint đang được enforce.
- `UNKNOWN` (`NULL`): hàng được chấp nhận; biểu thức không trả về `FALSE`.

Điểm `UNKNOWN` rất quan trọng. Ví dụ:

```sql
CREATE TABLE inventory (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    quantity INT NULL,
    PRIMARY KEY (id),
    CONSTRAINT chk_inventory_quantity_positive
        CHECK (quantity > 0)
) ENGINE=InnoDB;
```

Kết quả:

| Giá trị `quantity` | `quantity > 0` | CHECK |
| ---: | --- | --- |
| `5` | `TRUE` | Chấp nhận |
| `0` | `FALSE` | Từ chối |
| `-2` | `FALSE` | Từ chối |
| `NULL` | `UNKNOWN` | Chấp nhận |

Nếu nghiệp vụ không cho phép `NULL`, cần khai báo cả `NOT NULL`:

```sql
quantity INT NOT NULL,
CONSTRAINT chk_inventory_quantity_positive CHECK (quantity > 0)
```

`CHECK (quantity > 0)` không đồng nghĩa với `quantity IS NOT NULL`. Hãy thiết kế nullability và điều kiện giá trị như hai quy tắc riêng.

## 5. Ví dụ kiểm tra dữ liệu khi INSERT và UPDATE

Tạo bảng sản phẩm:

```sql
CREATE TABLE catalog_products (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    sku VARCHAR(50) NOT NULL,
    price DECIMAL(13, 2) NOT NULL,
    stock_quantity INT NOT NULL DEFAULT 0,
    status VARCHAR(20) NOT NULL DEFAULT 'draft',
    PRIMARY KEY (id),
    UNIQUE KEY uq_catalog_products_sku (sku),
    CONSTRAINT chk_catalog_products_price
        CHECK (price >= 0),
    CONSTRAINT chk_catalog_products_stock
        CHECK (stock_quantity >= 0),
    CONSTRAINT chk_catalog_products_status
        CHECK (status IN ('draft', 'active', 'archived'))
) ENGINE=InnoDB;
```

Các thao tác hợp lệ:

```sql
INSERT INTO catalog_products (sku, price, stock_quantity, status)
VALUES ('KB-001', 1250000.00, 10, 'active');

UPDATE catalog_products
SET stock_quantity = 8
WHERE sku = 'KB-001';
```

Các thao tác vi phạm:

```sql
-- Giá âm vi phạm chk_catalog_products_price
INSERT INTO catalog_products (sku, price, stock_quantity, status)
VALUES ('KB-002', -100.00, 5, 'active');

-- Tồn kho âm vi phạm chk_catalog_products_stock
UPDATE catalog_products
SET stock_quantity = -1
WHERE sku = 'KB-001';

-- Trạng thái ngoài danh sách cho phép
INSERT INTO catalog_products (sku, price, stock_quantity, status)
VALUES ('KB-003', 500000.00, 2, 'deleted');
```

Trên MySQL 8.0.16 trở lên khi các constraint được enforce, thao tác vi phạm bị từ chối với lỗi CHECK constraint. Mã lỗi thường gặp là `3819` (`ER_CHECK_CONSTRAINT_VIOLATED`). Ứng dụng nên xử lý lỗi theo constraint/ngữ cảnh nghiệp vụ thay vì coi mọi lỗi ghi dữ liệu là lỗi kết nối.

## 6. CHECK có thể kết hợp nhiều cột

Một số quy tắc chỉ có ý nghĩa khi so sánh nhiều cột trong cùng hàng:

```sql
CREATE TABLE promotions (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    regular_price DECIMAL(13, 2) NOT NULL,
    sale_price DECIMAL(13, 2) NOT NULL,
    starts_on DATE NOT NULL,
    ends_on DATE NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT chk_promotions_regular_price
        CHECK (regular_price >= 0),
    CONSTRAINT chk_promotions_sale_price
        CHECK (sale_price >= 0 AND sale_price <= regular_price),
    CONSTRAINT chk_promotions_date_range
        CHECK (starts_on <= ends_on)
) ENGINE=InnoDB;
```

Các constraint đảm bảo giá khuyến mãi không âm và không vượt giá thường, đồng thời ngày bắt đầu không sau ngày kết thúc. Đây là các điều kiện cục bộ, chỉ cần giá trị trong cùng một hàng nên phù hợp với `CHECK`.

Nếu một trong các cột có thể `NULL`, biểu thức so sánh có thể trả về `UNKNOWN` và hàng vẫn được chấp nhận. Hãy quyết định rõ cột nào bắt buộc, cột nào có thể chưa xác định và bổ sung `NOT NULL` hoặc biểu thức xử lý `NULL` khi cần.

## 7. Những biểu thức CHECK được phép và giới hạn

Biểu thức `CHECK` phải có thể được đánh giá ổn định từ dữ liệu của hàng. MySQL giới hạn các thành phần trong biểu thức để tránh phụ thuộc vào trạng thái thay đổi hoặc dữ liệu bên ngoài.

Không dùng các thành phần sau trong biểu thức CHECK:

- Subquery.
- Stored function hoặc loadable function.
- Biến hệ thống, biến người dùng hoặc parameter.
- Hàm không xác định (nondeterministic) như `NOW()`, `CURRENT_TIMESTAMP` hoặc `RAND()`.
- Tham chiếu đến cột của bảng khác.

Ví dụ sau không phù hợp:

```sql
-- Không dùng thời điểm hiện tại trong CHECK
CHECK (expires_at > CURRENT_TIMESTAMP)
```

Điều kiện thời gian thay đổi theo từng thời điểm; một hàng hợp lệ lúc insert có thể trở thành “không hợp lệ” chỉ vì thời gian trôi qua, dù không có câu lệnh update nào. MySQL không dùng `CHECK` để duy trì kiểu điều kiện động như vậy.

Nếu cần kiểm tra thời điểm hết hạn so với thời gian hiện tại, hãy kiểm tra trong truy vấn hoặc tầng nghiệp vụ khi thực hiện hành động. Nếu cần tự động xử lý bản ghi hết hạn, dùng job/event scheduler hoặc cơ chế phù hợp, không đặt điều kiện động vào `CHECK`.

## 8. CHECK không thay thế các loại ràng buộc khác

Mỗi loại constraint có mục đích riêng:

| Cơ chế | Điều nó bảo đảm | Ví dụ |
| --- | --- | --- |
| `NOT NULL` | Cột bắt buộc có giá trị | `email VARCHAR(254) NOT NULL` |
| `PRIMARY KEY` | Định danh duy nhất và không NULL | `PRIMARY KEY (id)` |
| `UNIQUE` | Không có hai giá trị trùng theo quy tắc index/collation | `UNIQUE (email)` |
| `FOREIGN KEY` | Giá trị tham chiếu phải tồn tại theo quan hệ | `customer_id REFERENCES customers(id)` |
| `CHECK` | Biểu thức trên giá trị hàng phải không trả về FALSE | `CHECK (quantity > 0)` |

Ví dụ `CHECK (customer_id > 0)` chỉ đảm bảo ID dương; nó không đảm bảo khách hàng có ID đó tồn tại. Muốn kiểm tra quan hệ giữa đơn hàng và khách hàng, dùng foreign key.

`CHECK` cũng không đảm bảo duy nhất. `CHECK (email <> '')` chỉ kiểm tra email không rỗng; muốn ngăn trùng email, cần `UNIQUE`. Khi một quy tắc cần dữ liệu từ nhiều hàng hoặc nhiều bảng, hãy cân nhắc foreign key, unique index, transaction hoặc logic nghiệp vụ phù hợp.

## 9. Khai báo ENFORCED và NOT ENFORCED

Từ MySQL 8.0.16, constraint có thể được khai báo rõ trạng thái thực thi:

```sql
CREATE TABLE shipment_rules (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    weight_kg DECIMAL(8, 3) NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT chk_shipment_weight_positive
        CHECK (weight_kg > 0) ENFORCED
) ENGINE=InnoDB;
```

`ENFORCED` là trạng thái mặc định, vì vậy có thể bỏ từ khóa này. Khi khai báo `NOT ENFORCED`, constraint được lưu trong schema nhưng MySQL không kiểm tra nó khi ghi dữ liệu:

```sql
ALTER TABLE shipment_rules
ADD CONSTRAINT chk_shipment_weight_reasonable
CHECK (weight_kg <= 5000) NOT ENFORCED;
```

`NOT ENFORCED` có thể hữu ích trong giai đoạn chuẩn bị migration hoặc tài liệu hóa một quy tắc chưa thể bật ngay. Tuy nhiên, nó không bảo vệ dữ liệu. Ứng dụng và quy trình vận hành phải coi constraint này là chưa hoạt động cho đến khi chuyển sang `ENFORCED`.

Có thể thay đổi trạng thái constraint trên MySQL hỗ trợ:

```sql
ALTER TABLE shipment_rules
ALTER CHECK chk_shipment_weight_reasonable ENFORCED;
```

Hoặc tạm tắt enforcement:

```sql
ALTER TABLE shipment_rules
ALTER CHECK chk_shipment_weight_reasonable NOT ENFORCED;
```

Không nên tắt constraint chỉ để import dữ liệu nhanh mà không có kế hoạch kiểm tra và bật lại. Trong thời gian `NOT ENFORCED`, các câu lệnh ghi có thể đưa dữ liệu vi phạm vào bảng.

## 10. Thêm CHECK vào bảng đã có dữ liệu

Trước khi thêm một constraint đang được enforce, hãy kiểm tra dữ liệu hiện có. Ví dụ muốn thêm `CHECK (price >= 0)` vào bảng sản phẩm:

```sql
SELECT id, price
FROM catalog_products
WHERE (price >= 0) IS FALSE;
```

`IS FALSE` giúp tìm những hàng mà biểu thức thực sự trả về FALSE. Hàng có `price IS NULL` sẽ cho biểu thức `UNKNOWN`, không bị `CHECK` từ chối chỉ vì điều kiện này; nếu cột phải có giá trị, kiểm tra riêng:

```sql
SELECT id
FROM catalog_products
WHERE price IS NULL;
```

Sau khi xử lý các hàng vi phạm, thêm constraint:

```sql
ALTER TABLE catalog_products
ADD CONSTRAINT chk_catalog_products_price_nonnegative
CHECK (price >= 0) ENFORCED;
```

Nếu dữ liệu hiện tại còn hàng vi phạm, thao tác thêm constraint được enforce có thể thất bại. Với bảng lớn, cần đánh giá chi phí kiểm tra dữ liệu, thời gian DDL, metadata lock và ảnh hưởng tới workload trên đúng phiên bản MySQL. Hãy thử trên staging với kích thước dữ liệu gần production.

## 11. Đổi tên, tắt, bật và xóa CHECK

Kiểm tra DDL trước khi thay đổi:

```sql
SHOW CREATE TABLE catalog_products\G
```

Đổi trạng thái enforcement:

```sql
ALTER TABLE catalog_products
ALTER CHECK chk_catalog_products_price_nonnegative NOT ENFORCED;

ALTER TABLE catalog_products
ALTER CHECK chk_catalog_products_price_nonnegative ENFORCED;
```

Xóa constraint khi quy tắc không còn áp dụng:

```sql
ALTER TABLE catalog_products
DROP CHECK chk_catalog_products_price_nonnegative;
```

Tên constraint cần được quản lý qua migration để các môi trường dùng cùng schema. Trước khi xóa, xác nhận ứng dụng hoặc pipeline không còn dựa vào quy tắc đó. Nếu quy tắc thay đổi, thường nên thêm constraint mới hoặc cập nhật DDL theo migration có kiểm soát thay vì sửa thủ công trên từng môi trường.

## 12. Kiểm tra trạng thái CHECK qua metadata

`SHOW CREATE TABLE` cho biết constraint có trong định nghĩa bảng và có thể hiển thị trạng thái `NOT ENFORCED`:

```sql
SHOW CREATE TABLE catalog_products\G
```

Trên MySQL 8.0.16 trở lên, có thể truy vấn `INFORMATION_SCHEMA.TABLE_CONSTRAINTS` để kiểm tra loại và trạng thái enforcement:

```sql
SELECT
    TABLE_NAME,
    CONSTRAINT_NAME,
    CONSTRAINT_TYPE,
    ENFORCED
FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
WHERE CONSTRAINT_SCHEMA = DATABASE()
  AND CONSTRAINT_TYPE = 'CHECK'
ORDER BY TABLE_NAME, CONSTRAINT_NAME;
```

Để xem biểu thức của từng constraint, kết hợp với `INFORMATION_SCHEMA.CHECK_CONSTRAINTS`:

```sql
SELECT
    tc.TABLE_NAME,
    tc.CONSTRAINT_NAME,
    tc.ENFORCED,
    cc.CHECK_CLAUSE
FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS AS tc
JOIN INFORMATION_SCHEMA.CHECK_CONSTRAINTS AS cc
  ON cc.CONSTRAINT_SCHEMA = tc.CONSTRAINT_SCHEMA
 AND cc.CONSTRAINT_NAME = tc.CONSTRAINT_NAME
WHERE tc.CONSTRAINT_SCHEMA = DATABASE()
  AND tc.CONSTRAINT_TYPE = 'CHECK'
ORDER BY tc.TABLE_NAME, tc.CONSTRAINT_NAME;
```

Các cột metadata này phụ thuộc phiên bản. Trên MySQL cũ trước 8.0.16, không dựa vào `ENFORCED` để suy ra enforcement vì các CHECK chưa được thực thi. Hãy dùng `SELECT VERSION()` và kiểm thử hành vi thực tế.

## 13. Khác biệt khi triển khai trên nhiều phiên bản

Trong hệ thống có development, staging, production, replica hoặc nhiều cụm database, không phải mọi server đều nhất thiết chạy cùng phiên bản. Điều này tạo ra rủi ro khi triển khai CHECK:

1. Một migration tạo `CHECK` có thể chạy thành công trên server cũ nhưng constraint bị bỏ qua.
2. Một server mới có thể từ chối dữ liệu mà ứng dụng cũ trước đây vẫn ghi được.
3. Một replica cũ có thể không thực thi CHECK dù source mới có enforcement.
4. Các môi trường có cùng DDL nhưng hành vi dữ liệu khác nhau nếu phiên bản không đồng nhất.

Trước khi bật constraint, cần kiểm kê phiên bản của mọi node có thể nhận ghi, gồm primary, replica có thể promote, môi trường báo cáo có ghi dữ liệu và các job ETL/import. Không coi replica chỉ đọc là nơi có thể bỏ qua khác biệt phiên bản nếu nó có thể được promote thành primary.

Nếu hệ thống còn server trước 8.0.16, hãy dùng validation ở ứng dụng và các cơ chế phù hợp khác cho đến khi toàn bộ đường ghi dữ liệu hỗ trợ enforcement. Trong giai đoạn nâng cấp hỗn hợp, không dựa vào CHECK như lớp bảo vệ duy nhất.

## 14. Quy trình rollout CHECK an toàn

Với bảng đã có dữ liệu và ứng dụng đang chạy, có thể triển khai theo các bước:

1. **Xác định phiên bản:** kiểm tra tất cả server có thể nhận ghi và xác nhận hỗ trợ CHECK enforcement.
2. **Định nghĩa quy tắc:** mô tả rõ miền giá trị, nullability và trường hợp ngoại lệ nghiệp vụ.
3. **Kiểm tra dữ liệu hiện tại:** chạy truy vấn tìm hàng vi phạm; tách riêng trường hợp `NULL` vì CHECK chấp nhận `UNKNOWN`.
4. **Làm sạch dữ liệu:** sửa hoặc cách ly bản ghi sai theo quy tắc nghiệp vụ, lưu dấu vết thay đổi.
5. **Triển khai tương thích ứng dụng:** bảo đảm ứng dụng xử lý lỗi constraint và không tiếp tục gửi dữ liệu sai.
6. **Thêm constraint:** thêm ở trạng thái `ENFORCED`, hoặc dùng `NOT ENFORCED` trong giai đoạn chuẩn bị nếu cần.
7. **Bật enforcement:** nếu đã tạo `NOT ENFORCED`, kiểm tra dữ liệu và chuyển sang `ENFORCED`.
8. **Kiểm thử âm/dương:** xác nhận dữ liệu hợp lệ được chấp nhận và dữ liệu vi phạm bị từ chối.
9. **Kiểm tra metadata:** đối chiếu `SHOW CREATE TABLE` và `INFORMATION_SCHEMA` trên từng môi trường.
10. **Theo dõi ứng dụng:** quan sát lỗi CHECK, log import và số lần ghi bị từ chối sau release.

Nếu cần rollback, hãy xác định rõ việc tắt hoặc xóa constraint có làm dữ liệu không hợp lệ quay trở lại hay không. Rollback DDL không tự khôi phục các giá trị đã bị sửa trong bước làm sạch.

## 15. Xử lý lỗi CHECK trong ứng dụng

Khi một thao tác ghi vi phạm constraint đang được enforce, MySQL từ chối thao tác và trả lỗi. Với MySQL 8.x, mã lỗi thường gặp là `3819` và thông điệp nêu tên constraint vi phạm.

Ứng dụng nên:

- Phân biệt lỗi constraint với lỗi mạng, timeout hoặc lỗi server.
- Trả thông báo nghiệp vụ dễ hiểu, chẳng hạn “Số lượng phải lớn hơn 0”.
- Không hiển thị nguyên văn SQL hoặc thông tin nội bộ database cho người dùng cuối.
- Ghi log tên constraint và ngữ cảnh cần thiết nhưng không ghi dữ liệu nhạy cảm không cần thiết.
- Không retry vô hạn một giá trị sai; retry chỉ có ích với lỗi tạm thời, không có ích với vi phạm dữ liệu cố định.

Validation ở giao diện vẫn hữu ích để phản hồi sớm. CHECK ở database là lớp bảo vệ cuối cùng cho quy tắc cục bộ, bảo đảm các client khác nhau cùng tuân theo điều kiện.

## 16. Những hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế |
| --- | --- |
| MySQL 5.7 tạo được CHECK nghĩa là đã bảo vệ dữ liệu | Trước 8.0.16, CHECK được parser chấp nhận nhưng bị bỏ qua |
| CHECK chỉ nhận TRUE hoặc FALSE | Biểu thức có thể trả UNKNOWN do `NULL`; UNKNOWN được chấp nhận |
| `CHECK (quantity > 0)` ngăn NULL | Không; cần thêm `NOT NULL` nếu NULL không hợp lệ |
| CHECK có thể truy vấn bảng khác | CHECK chỉ đánh giá biểu thức trên hàng hiện tại, không dùng subquery hay tham chiếu bảng khác |
| `NOT ENFORCED` vẫn kiểm tra dữ liệu | Không; constraint được lưu nhưng không được thực thi |
| CHECK bảo đảm duy nhất hoặc quan hệ tồn tại | Dùng `UNIQUE` và `FOREIGN KEY` cho các mục tiêu đó |
| Thêm CHECK luôn là DDL tức thời | MySQL có thể phải kiểm tra dữ liệu hiện có và thực hiện công việc DDL ảnh hưởng tới bảng |
| Tất cả node cùng có DDL nên hành vi giống nhau | Node trước 8.0.16 không thực thi CHECK; cần đồng nhất phiên bản đường ghi |

## 17. Bài tập thực hành

1. Tạo bảng `products` với `CHECK (price >= 0)` và `CHECK (stock_quantity >= 0)` trên MySQL 8.0.16 trở lên.
2. Insert một giá trị hợp lệ, một giá trị âm và một giá trị `NULL`; giải thích kết quả theo ba trạng thái TRUE/FALSE/UNKNOWN.
3. Bổ sung `NOT NULL` cho cột không cho phép thiếu giá trị và thử lại.
4. Tạo CHECK liên cột `sale_price <= regular_price` và `starts_on <= ends_on`.
5. Thêm một constraint `NOT ENFORCED`, ghi dữ liệu vi phạm rồi thử bật `ENFORCED`; quan sát việc kiểm tra dữ liệu hiện có.
6. Truy vấn `INFORMATION_SCHEMA.TABLE_CONSTRAINTS` và `CHECK_CONSTRAINTS` để xem trạng thái và biểu thức.
7. Thử cùng một DDL trên môi trường MySQL trước 8.0.16 nếu có; kiểm tra rằng cú pháp được chấp nhận nhưng dữ liệu vi phạm không bị chặn.
8. Thiết kế kế hoạch rollout CHECK cho một bảng đang có dữ liệu và nhiều ứng dụng ghi đồng thời.

## 18. Ghi nhớ

`CHECK` constraint kiểm tra biểu thức trên dữ liệu của cùng một hàng khi insert hoặc update. Biểu thức trả `FALSE` làm thao tác bị từ chối; `TRUE` và `UNKNOWN` được chấp nhận, vì vậy cần kết hợp `NOT NULL` nếu không cho phép thiếu dữ liệu.

Khác biệt phiên bản là điều bắt buộc phải nhớ: MySQL trước 8.0.16 chấp nhận cú pháp nhưng bỏ qua CHECK; từ 8.0.16, constraint được thực thi mặc định và có thể chuyển giữa `ENFORCED` và `NOT ENFORCED`. Hãy kiểm tra phiên bản trên mọi node có thể ghi, kiểm tra dữ liệu hiện tại, dùng metadata để xác minh enforcement và rollout qua migration có kiểm thử. Dùng CHECK cho quy tắc cục bộ; dùng `NOT NULL`, `UNIQUE`, `FOREIGN KEY` và logic nghiệp vụ cho những bảo đảm tương ứng.
