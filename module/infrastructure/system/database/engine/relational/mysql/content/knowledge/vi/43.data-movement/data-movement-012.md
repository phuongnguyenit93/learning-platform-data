# Nhập xuất và di chuyển

## Đối soát số dòng, tổng kiểm tra và các bất biến nghiệp vụ

Sau khi nhập dữ liệu vào một máy chủ MySQL mới, việc lệnh import kết thúc với exit code 0 chưa đủ để kết luận dữ liệu đã được chuyển chính xác. Một số dòng có thể bị thiếu hoặc lặp, giá trị có thể bị chuyển kiểu, quan hệ giữa các bảng có thể bị đứt, hoặc tổng tiền và tồn kho có thể không còn khớp với nghiệp vụ. Đối soát cần nhiều lớp kiểm tra để phát hiện cả sai lệch kỹ thuật lẫn sai lệch có ý nghĩa đối với ứng dụng.

Trong module **DATABASE_MYSQL**, bạn học cách làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction và kiểm soát đồng thời. Bạn cũng thực hành đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và xử lý các vấn đề vận hành cơ sở dữ liệu quan hệ. Những kỹ năng này giúp bạn xác minh dữ liệu sau export/import, restore hoặc chuyển hệ thống: biết transaction nào thuộc cùng một snapshot, khóa nào định danh một hàng và quy tắc nghiệp vụ nào phải giữ nguyên.

Bài này xây dựng quy trình đối soát từ row count, khóa, checksum/hash theo phạm vi đến tổng hợp và bất biến nghiệp vụ. Các ví dụ dùng bảng đơn hàng, chi tiết đơn hàng, thanh toán và tồn kho; hãy điều chỉnh công thức theo quy tắc thật của hệ thống.

### 1. Đối soát cần trả lời những câu hỏi nào?

Đối soát dữ liệu sau di chuyển nên trả lời ít nhất năm câu hỏi:

1. **Đủ số lượng chưa?** Có thiếu hoặc thừa hàng, bảng, partition hay đối tượng không?
2. **Đúng định danh chưa?** Các primary key và business key có còn đầy đủ, duy nhất và ánh xạ đúng không?
3. **Giá trị có giống nhau không?** Các cột quan trọng có bị cắt cụt, đổi charset, làm tròn hoặc chuyển timezone không?
4. **Quan hệ có nguyên vẹn không?** Foreign key, quan hệ cha-con và liên kết nghiệp vụ có bị đứt không?
5. **Kết quả có đúng nghiệp vụ không?** Tổng đơn hàng, thanh toán, công nợ, tồn kho và sổ cái có giữ các bất biến đã định nghĩa không?

Không có một phép kiểm tra đơn lẻ nào trả lời đủ cả năm câu hỏi. Hai bảng có cùng COUNT(*) vẫn có thể chứa các tập primary key khác nhau. Hai bảng có cùng tổng tiền vẫn có thể thiếu một đơn hàng và thừa một đơn hàng khác có giá trị bằng nhau. Một checksum tổng hợp trùng nhau cũng không thay thế việc kiểm tra các quan hệ và quy tắc nghiệp vụ.

### 2. Chốt cùng một mốc dữ liệu trước khi so sánh

So sánh source và target chỉ có ý nghĩa khi hai phía đại diện cho cùng một trạng thái logic. Nếu source vẫn nhận ghi trong lúc bạn đếm hàng, còn target đang được import từ một backup cũ hơn, chênh lệch có thể là giao dịch hợp lệ phát sinh sau snapshot.

#### 2.1. Dùng consistent snapshot với InnoDB

Trong một kết nối đọc trên source, có thể mở consistent snapshot ở mức cô lập REPEATABLE READ:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION WITH CONSISTENT SNAPSHOT;

SELECT COUNT(*) FROM appdb.orders;
SELECT COUNT(*) FROM appdb.order_items;
SELECT SUM(total_amount) FROM appdb.orders;

COMMIT;
```

Các consistent read của InnoDB trong transaction này nhìn thấy cùng một snapshot. Hãy thực hiện các truy vấn cần đối chiếu trong cùng transaction và cùng kết nối. Snapshot này không bao gồm thay đổi commit sau thời điểm tạo snapshot.

START TRANSACTION WITH CONSISTENT SNAPSHOT có ý nghĩa đối với InnoDB và isolation level phù hợp; nó không tạo snapshot phân tán tự động giữa hai máy chủ độc lập. Nếu chạy các truy vấn ở nhiều kết nối hoặc trên nhiều hệ thống, phải phối hợp mốc dữ liệu.

#### 2.2. Chọn watermark cho quá trình di chuyển có ghi liên tục

Với hệ thống vẫn nhận ghi, một quy trình thường dùng là:

1. Tạo full backup hoặc snapshot nhất quán và ghi metadata của nó.
2. Ghi nhận tọa độ binlog/GTID tương ứng với snapshot theo công cụ backup.
3. Nạp snapshot vào target.
4. Phát lại thay đổi phát sinh sau snapshot bằng replication hoặc CDC.
5. Đến cutover, chặn ghi mới, drain transaction đang chạy và ghi một watermark cuối.
6. Chờ target áp dụng đến watermark; sau đó đối soát trên trạng thái ổn định.

Với GTID, có thể dùng WAIT_FOR_EXECUTED_GTID_SET() trên target để đợi tập giao dịch đã ghi nhận ở source được thực thi. Với file/position, dùng tọa độ do backup hoặc công cụ CDC cung cấp. Không lấy trạng thái binlog ở một thời điểm tùy ý rồi coi đó là tọa độ của một snapshot đã tạo trước đó.

Nếu không thể chặn ghi hoặc bắt kịp thay đổi, hãy định nghĩa rõ cửa sổ đối soát và phân loại phần chênh lệch phát sinh sau watermark. Đừng sửa dữ liệu target chỉ để làm cho hai con số tạm thời bằng nhau.

### 3. Kiểm tra số dòng và phạm vi dữ liệu

#### 3.1. Đếm chính xác

Với bảng InnoDB, COUNT(*) là phép đếm chính xác tại snapshot của truy vấn:

```sql
SELECT COUNT(*) AS order_count
FROM appdb.orders;

SELECT COUNT(*) AS item_count
FROM appdb.order_items;
```

INFORMATION_SCHEMA.TABLES.TABLE_ROWS đối với InnoDB thường là ước lượng. Dùng nó để quan sát quy mô, không dùng làm bằng chứng đối soát chính xác.

Kiểm tra thêm số khóa chính không NULL và số khóa duy nhất:

```sql
SELECT
  COUNT(*) AS total_rows,
  COUNT(order_id) AS nonnull_order_ids,
  COUNT(DISTINCT order_id) AS distinct_order_ids
FROM appdb.orders;
```

Nếu order_id là primary key, các số đếm phải phù hợp với định nghĩa schema. Với bảng không có primary key, cần xác định business key hoặc một tổ hợp cột có thể nhận diện từng bản ghi; nếu không có khóa ổn định, đối soát hàng theo hàng sẽ khó hơn và cần quy tắc riêng.

#### 3.2. Đếm theo partition nghiệp vụ

Đếm tổng toàn bảng có thể che khuất sai lệch giữa các nhóm. Hãy phân rã theo ngày, trạng thái, tenant hoặc partition:

```sql
SELECT
  DATE(created_at) AS order_date,
  status,
  COUNT(*) AS row_count
FROM appdb.orders
GROUP BY DATE(created_at), status
ORDER BY order_date, status;
```

So sánh cùng nhóm trên source và target. Nếu tổng số đơn giống nhau nhưng một ngày thiếu 100 đơn và ngày khác thừa 100 đơn, báo cáo theo partition sẽ làm lộ sai lệch.

Với bảng partition lớn, dùng điều kiện trên partition key và primary key để chia thành các chunk ổn định. Ví dụ:

```sql
SELECT COUNT(*) AS chunk_rows,
       MIN(order_id) AS min_id,
       MAX(order_id) AS max_id
FROM appdb.orders
WHERE order_id >= 100000
  AND order_id < 110000;
```

Ranh giới chunk nên không chồng lấn, không bỏ sót và dựa trên khóa ổn định. Tránh phân trang bằng LIMIT offset trên bảng lớn vì offset tăng dần có thể tốn kém và dễ gây khó khăn khi dữ liệu thay đổi.

#### 3.3. Tìm khóa bị thiếu hoặc thừa

Nếu có thể truy vấn hai schema trong cùng một MySQL instance, dùng anti-join để tìm khóa chỉ có ở một phía:

```sql
-- Có ở source nhưng không có ở target.
SELECT s.order_id
FROM source_db.orders AS s
LEFT JOIN target_db.orders AS t
  ON t.order_id = s.order_id
WHERE t.order_id IS NULL;

-- Có ở target nhưng không có ở source.
SELECT t.order_id
FROM target_db.orders AS t
LEFT JOIN source_db.orders AS s
  ON s.order_id = t.order_id
WHERE s.order_id IS NULL;
```

Nếu source và target ở hai máy chủ riêng, xuất danh sách khóa hoặc hash theo chunk vào file/staging table rồi so sánh bằng công cụ di chuyển dữ liệu. Không giả định MySQL có thể join trực tiếp hai máy chủ độc lập nếu chưa cấu hình cơ chế truy cập từ xa.

Kiểm tra business key có bị lặp:

```sql
SELECT external_order_no, COUNT(*) AS occurrences
FROM appdb.orders
GROUP BY external_order_no
HAVING COUNT(*) > 1;
```

Một khóa kỹ thuật có thể duy nhất trong từng database nhưng business key vẫn bị trùng do mapping sai hoặc import lặp. Hãy kiểm tra cả khóa kỹ thuật lẫn định danh nghiệp vụ.

### 4. Tổng kiểm tra và checksum

#### 4.1. Tổng hợp các cột quan trọng

Row count cần được bổ sung bằng tổng, min/max và phân bố dữ liệu:

```sql
SELECT
  COUNT(*) AS order_count,
  COUNT(DISTINCT customer_id) AS customer_count,
  COALESCE(SUM(total_amount), 0) AS total_order_amount,
  MIN(created_at) AS first_order_at,
  MAX(created_at) AS last_order_at
FROM appdb.orders;
```

So sánh thêm theo trạng thái:

```sql
SELECT
  status,
  COUNT(*) AS order_count,
  COALESCE(SUM(total_amount), 0) AS total_amount
FROM appdb.orders
GROUP BY status
ORDER BY status;
```

Các tổng hợp giúp tìm sai lệch nhanh nhưng không chứng minh từng hàng giống nhau. Hãy dùng chúng như lớp sàng lọc trước khi kiểm tra khóa và giá trị cụ thể.

#### 4.2. Lưu ý về kiểu dữ liệu và chuẩn hóa

Hai giá trị chỉ có thể so sánh đáng tin cậy khi đã xác định cùng cách biểu diễn:

- **Tiền tệ:** dùng DECIMAL với precision/scale phù hợp; tránh cộng số tiền bằng FLOAT hoặc DOUBLE nếu cần đối chiếu chính xác.
- **NULL:** phân biệt NULL với chuỗi rỗng, số 0 và giá trị mặc định. SUM() trả NULL khi không có giá trị đầu vào; dùng COALESCE() khi nghiệp vụ quy định tổng rỗng là 0.
- **Thời gian:** thống nhất timezone của session. TIMESTAMP được chuyển đổi theo timezone của session; DATETIME lưu giá trị ngày giờ không tự chuyển đổi theo timezone. Không so sánh hai cột thời gian trước khi xác định quy ước UTC/local.
- **Chuỗi:** kiểm tra charset, collation, chữ hoa/thường, dấu, khoảng trắng cuối và quy tắc chuẩn hóa Unicode. Hai chuỗi được collation xem là bằng nhau chưa chắc có cùng byte.
- **Số nguyên:** đối chiếu signed/unsigned và miền giá trị; giá trị ngoài miền có thể gây lỗi hoặc chuyển đổi tùy SQL mode.
- **JSON:** so sánh nội dung logic theo schema ứng dụng; không mặc định byte serialization giữa các phiên bản/công cụ luôn giống nhau.
- **Generated/default values:** kiểm tra generated column, default, trigger và biểu thức thời gian. Import có thể tạo giá trị khác nếu không giữ nguyên dữ liệu hoặc ngữ cảnh session.

Ghi lại sql_mode, charset/collation và timezone dùng trong cả quá trình export/import. Nếu nguồn và đích dùng quy tắc khác nhau, hãy chuẩn hóa rõ ràng trước khi tính tổng kiểm tra.

#### 4.3. CHECKSUM TABLE và giới hạn

MySQL có lệnh:

```sql
CHECKSUM TABLE appdb.orders;
```

Lệnh có thể hữu ích khi so sánh hai bảng tương thích trong cùng môi trường, nhưng không phải giải pháp checksum logic phổ quát cho mọi engine và phiên bản. Khả năng hỗ trợ và kết quả có thể phụ thuộc storage engine, cấu trúc bảng và cách triển khai. Không dùng một checksum duy nhất làm bằng chứng duy nhất rằng dữ liệu đã chuyển đúng giữa các engine hoặc phiên bản khác nhau.

Các công cụ như pt-table-checksum của Percona Toolkit có thể chia bảng thành chunk và hỗ trợ phát hiện khác biệt trong môi trường replication. Trước khi dùng, hãy kiểm tra phiên bản công cụ, quyền, tải truy vấn, cấu hình replication/filter và hướng dẫn cho topology cụ thể. Công cụ checksum cũng cần một trạng thái dữ liệu có thể so sánh; nó không thay thế watermark và kiểm tra nghiệp vụ.

### 5. Hash từng hàng và đối soát theo chunk

Khi cần tìm giá trị nào khác nhau, có thể tạo hash từ biểu diễn chuẩn hóa của các cột quan trọng rồi so sánh theo primary key.

Ví dụ minh họa cho bảng orders:

```sql
SELECT
  order_id,
  SHA2(
    CONCAT(
      IF(customer_code IS NULL,
         'N;',
         CONCAT('V', OCTET_LENGTH(CAST(customer_code AS BINARY)),
                ':', HEX(CAST(customer_code AS BINARY)), ';')),
      IF(status IS NULL,
         'N;',
         CONCAT('V', OCTET_LENGTH(CAST(status AS BINARY)),
                ':', HEX(CAST(status AS BINARY)), ';')),
      IF(total_amount IS NULL,
         'N;',
         CONCAT('V', CAST(total_amount AS CHAR), ';')),
      IF(created_at IS NULL,
         'N;',
         CONCAT('V', DATE_FORMAT(created_at,
                 '%Y-%m-%dT%H:%i:%s.%f'), ';'))
    ),
    256
  ) AS row_hash
FROM appdb.orders
WHERE order_id >= 100000
  AND order_id < 110000
ORDER BY order_id;
```

Ví dụ dùng marker N cho NULL và marker V cho giá trị có thật; chuỗi được mã hóa HEX kèm độ dài để tránh nhập nhằng do ký tự phân cách xuất hiện trong dữ liệu. DECIMAL được chuyển sang chuỗi theo scale của cột. Trước khi so sánh TIMESTAMP, đặt cùng timezone, ví dụ SET time_zone = '+00:00' ở cả hai session; với DATETIME, thống nhất ý nghĩa timezone theo nghiệp vụ. Hãy thêm tất cả cột có ý nghĩa vào payload và dùng cùng một biểu thức ở hai phía.

Hash cần có thiết kế chuẩn hóa rõ ràng:

- Chọn cột có ý nghĩa; bỏ qua cột chỉ mang tính môi trường nếu giá trị được phép khác nhau.
- Xác định cách biểu diễn NULL, chuỗi, số, thời gian và JSON.
- Dùng cùng thứ tự cột và cùng biểu thức trên source/target.
- Bao gồm primary key hoặc so sánh hash gắn với primary key để biết hàng nào khác.
- Nếu cần xác minh byte chính xác, hash byte gốc; nếu cần so sánh giá trị logic, chuẩn hóa theo quy tắc đã thống nhất.

Không chỉ lấy một hash tổng hợp cho toàn bảng. Hãy chia theo khoảng khóa hoặc partition, so sánh số hàng và hash theo từng chunk, rồi drill down đến các primary key ở chunk sai lệch. Có thể lưu cặp (chunk_id, row_count, digest) vào bảng staging để lập báo cáo.

Các digest tổng hợp kiểu BIT_XOR(CRC32(...)) có thể dùng làm bộ lọc nhanh nhưng có nguy cơ va chạm và không chứng minh dữ liệu giống hệt. GROUP_CONCAT() toàn bộ hash có thể vượt group_concat_max_len, tiêu tốn bộ nhớ và tạo kết quả bị cắt cụt. Với kiểm tra nghiêm ngặt, so sánh hash SHA-256 theo khóa hoặc đối chiếu từng hàng ở các chunk bị nghi ngờ.

Hash chỉ có ý nghĩa khi canonicalization đúng. Nếu hai bên dùng collation khác nhau nhưng hash byte chuỗi, kết quả có thể khác dù phép so sánh SQL cho là bằng nhau; ngược lại, nếu chuẩn hóa quá mạnh, hash có thể che mất khác biệt byte cần bảo toàn. Hãy ghi rõ mục tiêu là so sánh byte hay so sánh giá trị nghiệp vụ.

### 6. Kiểm tra quan hệ và toàn vẹn tham chiếu

Một bảng có đủ số dòng vẫn có thể chứa khóa ngoại không còn hàng cha. Với quan hệ orders và order_items, kiểm tra:

```sql
SELECT COUNT(*) AS orphan_item_count
FROM appdb.order_items AS i
LEFT JOIN appdb.orders AS o
  ON o.order_id = i.order_id
WHERE o.order_id IS NULL;
```

Kết quả phải bằng 0 nếu mỗi dòng chi tiết bắt buộc thuộc một đơn hàng. Lặp lại cho các quan hệ quan trọng như payment-to-order, shipment-to-order, invoice-to-customer và inventory movement-to-product.

Kiểm tra duplicate business key, NULL ngoài dự kiến, trạng thái không hợp lệ và giá trị nằm ngoài miền:

```sql
SELECT COUNT(*) AS invalid_amount_count
FROM appdb.orders
WHERE total_amount < 0;

SELECT COUNT(*) AS missing_customer_count
FROM appdb.orders
WHERE customer_id IS NULL;
```

Điều kiện kiểm tra phải theo nghiệp vụ. Ví dụ, đơn hàng hoàn tiền có thể có tổng âm nếu mô hình dữ liệu cho phép; khi đó total_amount < 0 không tự động là lỗi. Viết rõ phạm vi trạng thái và ngoại lệ trước khi đánh dấu sai lệch.

### 7. Đối soát các bất biến nghiệp vụ

Bất biến nghiệp vụ là quan hệ phải đúng giữa các dữ liệu dù chúng nằm ở nhiều bảng. Đây là lớp kiểm tra quan trọng vì một import có thể giữ nguyên row count nhưng thay đổi quan hệ hoặc giá trị.

#### 7.1. Đơn hàng và chi tiết đơn hàng

Nếu subtotal được định nghĩa là tổng quantity * unit_price trước thuế, giảm giá và phí vận chuyển, có thể kiểm tra:

```sql
SELECT
  o.order_id,
  o.subtotal,
  COALESCE(SUM(i.quantity * i.unit_price), 0) AS calculated_subtotal
FROM appdb.orders AS o
LEFT JOIN appdb.order_items AS i
  ON i.order_id = o.order_id
GROUP BY o.order_id, o.subtotal
HAVING o.subtotal <> calculated_subtotal;
```

Trong hệ thống thực tế, cần xử lý discount ở cấp dòng/đơn, thuế, phí, làm tròn và đơn bị hủy theo đúng quy tắc. Nếu tiền được lưu theo DECIMAL, biểu thức tính cũng phải giữ precision/scale phù hợp.

Một công thức tổng quát có thể là:

**order_total = item_subtotal - discount + tax + shipping_fee**

Nhưng chỉ áp dụng khi đây đúng là quy tắc của sản phẩm. Không tự suy ra thứ tự làm tròn hoặc cách phân bổ giảm giá.

#### 7.2. Thanh toán, hoàn tiền và công nợ

Đối soát thanh toán cần phân biệt trạng thái AUTHORIZED, CAPTURED, SETTLED, REFUNDED, VOIDED và CHARGEBACK. Một giao dịch được authorize chưa chắc đã thu tiền; refund có thể một phần hoặc nhiều lần.

Ví dụ nếu mô hình lưu mỗi capture/refund thành một dòng với amount dương và status rõ ràng:

```sql
SELECT
  order_id,
  SUM(
    CASE
      WHEN status IN ('CAPTURED', 'SETTLED') THEN amount
      WHEN status = 'REFUNDED' THEN -amount
      ELSE 0
    END
  ) AS net_collected
FROM appdb.payments
GROUP BY order_id;
```

Đối chiếu net_collected với số tiền đã thu theo sổ nghiệp vụ hoặc trạng thái đơn hàng. Công thức phải điều chỉnh nếu refund được lưu ở bảng riêng, amount có dấu âm, settlement có phí hoặc chargeback được xử lý theo kỳ kế toán.

Với sổ cái kép, tổng debit và credit phải cân bằng theo từng journal/batch và đơn vị tiền tệ:

```sql
SELECT journal_id, currency,
       SUM(debit_amount) AS total_debit,
       SUM(credit_amount) AS total_credit
FROM appdb.ledger_lines
GROUP BY journal_id, currency
HAVING SUM(debit_amount) <> SUM(credit_amount);
```

Không cộng các đồng tiền khác nhau vào một tổng duy nhất nếu chưa quy đổi theo quy tắc tỷ giá và thời điểm đã định.

#### 7.3. Tồn kho và luồng hàng

Nếu mô hình tính tồn kho từ số dư đầu kỳ và các movement:

**on_hand = opening_balance + receipts - shipments + adjustments**

cần đối chiếu số dư tính lại với bảng balance hiện tại. Ví dụ:

```sql
SELECT
  b.product_id,
  b.warehouse_id,
  b.on_hand,
  COALESCE(SUM(
    CASE
      WHEN m.movement_type = 'RECEIPT' THEN m.quantity
      WHEN m.movement_type = 'SHIPMENT' THEN -m.quantity
      WHEN m.movement_type = 'ADJUSTMENT' THEN m.signed_quantity
      ELSE 0
    END
  ), 0) + b.opening_balance AS calculated_on_hand
FROM appdb.inventory_balance AS b
LEFT JOIN appdb.inventory_movements AS m
  ON m.product_id = b.product_id
 AND m.warehouse_id = b.warehouse_id
GROUP BY b.product_id, b.warehouse_id, b.on_hand, b.opening_balance
HAVING b.on_hand <> calculated_on_hand;
```

Ví dụ giả định movement có quy ước dấu như trên và bảng balance lưu opening balance. Hệ thống có thể dùng snapshot theo kỳ, transfer giữa kho, hàng đang giữ chỗ, hàng trả lại hoặc movement đảo; hãy đưa tất cả loại giao dịch đó vào công thức chính thức. Đối soát theo product_id và warehouse_id, không chỉ so tổng tồn kho toàn hệ thống.

#### 7.4. Các bất biến khác

- Số lượng shipment không vượt số lượng được phép giao của order line, theo chính sách backorder.
- Tổng allocation/fulfillment không vượt số lượng tồn có thể phân bổ.
- Invoice đã phát hành phải liên kết đúng customer và order; tổng dòng invoice phải khớp total theo quy tắc thuế.
- Mọi payment/refund phải liên kết tới order hoặc account hợp lệ.
- Mỗi journal entry phải cân bằng theo currency và kỳ.
- Trạng thái order, payment và shipment phải nằm trong tập chuyển trạng thái hợp lệ.

Hãy chuyển các bất biến quan trọng thành truy vấn có thể chạy lặp lại và lưu kết quả cùng báo cáo migration. Những ngoại lệ hợp lệ cần được định nghĩa bằng điều kiện rõ ràng, không loại trừ tùy tiện sau khi thấy truy vấn trả về lỗi.

### 8. Quy trình đối soát trong một lần di chuyển dữ liệu

**Trước khi export**

1. Lập danh sách schema, table, partition, view, trigger, routine và event cần di chuyển.
2. Xác định primary key/business key và các quan hệ cần kiểm tra.
3. Chốt snapshot/watermark, charset/collation, timezone, SQL mode và kiểu dữ liệu nguồn/đích.
4. Chạy baseline: row count, count theo nhóm, tổng tiền, min/max thời gian và bất biến nghiệp vụ.
5. Lưu truy vấn, thời điểm chạy, GTID/file-position và phiên bản schema để có thể tái lập.

**Trong khi import**

1. Nạp vào target theo thứ tự phụ thuộc, bảo đảm schema và constraint phù hợp.
2. Ghi nhận lỗi, warning, số dòng được chèn và bảng/partition hoàn tất.
3. Không bỏ qua lỗi chuyển kiểu, duplicate key hoặc constraint chỉ để import tiếp mà không có quyết định.
4. Nếu có CDC/replication catch-up, theo dõi watermark và lỗi apply.

**Trước cutover**

1. Chặn ghi mới ở source và drain transaction đang chạy theo kế hoạch.
2. Ghi watermark cuối cùng sau khi nguồn ghi đã dừng.
3. Chờ target áp dụng đến watermark.
4. Chạy row count, key coverage, chunk checksum/hash và bất biến nghiệp vụ trên cùng trạng thái logic.
5. Drill down mọi chunk hoặc nhóm có sai lệch; sửa từ nguyên nhân và chạy lại kiểm tra.
6. Chỉ phê duyệt cutover khi các sai lệch đã được giải thích và chấp nhận bằng văn bản.

**Sau cutover**

1. Kiểm tra ứng dụng đọc/ghi trên target và xác minh kết quả nghiệp vụ.
2. Theo dõi lỗi constraint, duplicate, dữ liệu mới, tổng tiền và tồn kho trong một chu kỳ vận hành.
3. Giữ source ở trạng thái có thể đối chiếu/rollback theo kế hoạch đã phê duyệt; không cho hai phía cùng nhận ghi độc lập.
4. Lưu báo cáo, watermark, checksum, truy vấn, sai lệch đã chấp nhận và người phê duyệt.

### 9. Phân loại sai lệch và xử lý

| Kết quả đối soát | Khả năng nguyên nhân | Hướng xử lý |
|---|---|---|
| Row count thiếu trên target | Import bị ngắt, filter, partition bỏ sót hoặc watermark sai | So sánh theo chunk/partition, kiểm tra log import và nguồn dữ liệu |
| Row count bằng nhau nhưng key khác | Thiếu một tập khóa và thừa tập khác, mapping ID sai hoặc import lặp | Anti-join hai chiều theo primary/business key |
| Key giống nhưng hash khác | Giá trị cột bị chuyển đổi, cắt cụt, timezone/collation/precision khác | So sánh từng cột sau chuẩn hóa, kiểm tra warning và cấu hình session |
| Checksum khác nhưng row count giống | Một hoặc nhiều hàng khác giá trị, hoặc thuật toán checksum phụ thuộc engine/phiên bản | Drill down theo chunk và hash theo khóa; xác nhận cách tính checksum |
| Orphan foreign key | Bảng cha thiếu, import sai thứ tự hoặc filter không đồng bộ | Tìm khóa cha thiếu, khôi phục dữ liệu và kiểm tra quan hệ |
| Tổng tiền khác | Thiếu giao dịch, trạng thái thanh toán khác, rounding hoặc kiểu dữ liệu | Đối soát theo order/currency/status và kiểm tra quy tắc làm tròn |
| Tồn kho khác | Movement bị thiếu/lặp, snapshot sai hoặc công thức không tính transfer/return | Đối soát theo sản phẩm/kho và dựng lại từ ledger movement |
| Source/target chênh lệch theo thời gian | Snapshot hoặc watermark không trùng nhau | Chốt lại watermark, catch-up và chạy lại đối soát trên trạng thái ổn định |

Không cập nhật target bằng một câu UPDATE tổng quát chỉ để làm cho aggregate khớp. Trước khi sửa, xác định bản ghi nguồn nào là chuẩn, thao tác nào đã xảy ra, có cần giữ audit trail không và việc sửa có làm phát sinh transaction mới trong replication/CDC hay không.

### 10. Báo cáo và tiêu chí nghiệm thu

Một báo cáo đối soát có thể được lưu dưới dạng bảng hoặc file với các trường:

| Trường | Nội dung |
|---|---|
| migration_id | Định danh lần di chuyển |
| source_id, target_id | Instance/schema nguồn và đích |
| snapshot_id / watermark | GTID, file/position hoặc ID snapshot |
| table_name, chunk_id | Bảng và phạm vi khóa được kiểm tra |
| source_count, target_count | Số dòng hai phía |
| source_digest, target_digest | Digest/hash theo cùng canonicalization |
| business_check | Tên bất biến hoặc truy vấn nghiệp vụ |
| mismatch_count | Số sai lệch tìm được |
| result, approved_by | Kết quả và người chấp nhận ngoại lệ |
| checked_at | Thời điểm đối soát |

Tiêu chí nghiệm thu nên được định nghĩa trước:

- Không thiếu hoặc thừa bảng/partition trong phạm vi migration.
- Row count và key coverage khớp tại cùng watermark, hoặc sai lệch đã được phân loại và phê duyệt.
- Hash theo chunk không có khác biệt chưa giải thích.
- Foreign key/business key và các quan hệ bắt buộc nguyên vẹn.
- Các bất biến orders, payments, ledger và inventory đạt yêu cầu.
- Không còn lỗi/warning import chưa được giải thích có thể làm đổi dữ liệu.
- Ứng dụng chạy thử trên target cho kết quả đúng.

Không nên đặt một ngưỡng chung như “99,9% số dòng khớp” cho mọi bảng. Một bản ghi tài chính bị thiếu có thể nghiêm trọng dù tỷ lệ sai lệch rất nhỏ. Mức chấp nhận phải theo loại dữ liệu, tác động nghiệp vụ và yêu cầu kiểm soát.

### 11. Bài tập thực hành

Bạn cần chuyển database bán hàng sales sang một MySQL instance mới. Sau import, tổng số dòng của orders trên hai phía bằng nhau, nhưng tổng tiền khác 0,8%. Bảng order_items có số dòng thấp hơn 12 dòng; payments có cùng số dòng nhưng số tiền đã refund khác. Source đã tiếp tục nhận giao dịch trong lúc import.

1. Vì sao row count tổng của orders bằng nhau chưa chứng minh hai bảng giống nhau?
2. Bạn cần xác định snapshot và watermark nào trước khi so sánh lại?
3. Viết truy vấn anti-join để tìm order_id thiếu trên target và order_id thừa trên target.
4. Bạn sẽ phân rã tổng tiền theo ngày, trạng thái và currency như thế nào?
5. Những trạng thái payment nào cần đưa vào công thức net collected? Cần hỏi chủ nghiệp vụ điều gì trước khi viết công thức?
6. Làm thế nào kiểm tra subtotal của order với tổng các order item, có tính đến discount, tax và rounding?
7. Tạo một chiến lược hash theo primary key và chunk để tìm các hàng khác nhau mà không gom toàn bộ hash vào một GROUP_CONCAT().
8. Viết một bất biến tồn kho theo product và warehouse, rồi nêu các loại movement phải tính.
9. Hãy lập tiêu chí nghiệm thu và báo cáo sai lệch trước khi cho ứng dụng ghi vào target.

### 12. Nguyên tắc vận hành

Đối soát đáng tin cậy bắt đầu từ một snapshot hoặc watermark có thể giải thích. Row count phát hiện chênh lệch số lượng; primary key và business key tìm bản ghi thiếu/thừa; checksum/hash khoanh vùng khác biệt giá trị; quan hệ và bất biến nghiệp vụ xác nhận dữ liệu còn đúng ý nghĩa. Chuẩn hóa kiểu dữ liệu, NULL, timezone, charset và collation trước khi so sánh. Chỉ cutover khi các sai lệch đã được điều tra, khắc phục hoặc chấp nhận theo tiêu chí đã định nghĩa, và lưu lại bằng chứng đủ để người khác có thể lặp lại quá trình kiểm tra.
