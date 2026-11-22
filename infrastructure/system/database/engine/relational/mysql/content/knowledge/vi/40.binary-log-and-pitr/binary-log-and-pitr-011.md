# Kiểm chứng kết quả PITR bằng dữ liệu nghiệp vụ

Point-in-time recovery (PITR) khôi phục MySQL từ một bản backup nền rồi phát lại binary log đến một thời điểm hoặc vị trí đã chọn. Việc MySQL khởi động thành công và các bảng xuất hiện đầy đủ mới chỉ chứng minh quá trình phục hồi đã đi qua bước kỹ thuật cơ bản. Để xác nhận dữ liệu có thể sử dụng, cần kiểm tra thêm các quy tắc nghiệp vụ: đơn hàng có đủ dòng chi tiết, tổng tiền khớp, thanh toán không bị ghi nhận hai lần, tồn kho hợp lý và trạng thái giao dịch phù hợp với thời điểm khôi phục.

Trong module `DATABASE_MYSQL`, bài học này nối binary log và PITR với dữ liệu quan hệ, khóa ngoại, giao dịch, truy vấn tổng hợp và vận hành. Mục tiêu là xây dựng một cách kiểm chứng có bằng chứng, có thể lặp lại và có tiêu chí chấp nhận rõ ràng.

Sau bài học, bạn có thể:

- Xác định mốc PITR cần kiểm chứng và hiểu vì sao phải dừng tại ranh giới giao dịch.
- Kiểm tra metadata của backup, binary log, GTID và thời điểm phục hồi.
- Đối chiếu số lượng, khóa, quan hệ và tổng hợp dữ liệu với quy tắc nghiệp vụ.
- Phát hiện bản ghi thiếu, trùng, mồ côi hoặc có trạng thái không hợp lệ.
- Dùng bằng chứng độc lập như log ứng dụng, mã giao dịch và báo cáo đối soát.
- Lập báo cáo kiểm chứng và quyết định chấp nhận hoặc làm lại lần phục hồi.

## 1. PITR cần được kiểm chứng ở những lớp nào?

PITR gồm hai phần dữ liệu: trạng thái của database tại thời điểm tạo backup nền và các thay đổi được ghi trong binary log sau thời điểm đó. Khi phát lại log, MySQL áp dụng các sự kiện theo thứ tự. Nếu chọn sai mốc dừng, có thể thiếu giao dịch hợp lệ hoặc đưa cả giao dịch gây lỗi vào dữ liệu phục hồi.

Một lần PITR cần được kiểm chứng ở bốn lớp:

| Lớp kiểm chứng | Câu hỏi cần trả lời | Ví dụ bằng chứng |
|---|---|---|
| Kỹ thuật | Instance có mở được dữ liệu và hoàn tất recovery không? | Error log, trạng thái InnoDB, metadata backup, phiên bản MySQL |
| Cấu trúc | Các schema, bảng, index và ràng buộc cần thiết có tồn tại không? | `INFORMATION_SCHEMA`, `SHOW CREATE TABLE`, `CHECK TABLE` |
| Dữ liệu | Bản ghi, quan hệ và giá trị có nhất quán không? | Số lượng hàng, khóa ngoại, checksum, truy vấn tìm bản ghi mồ côi |
| Nghiệp vụ | Dữ liệu có phản ánh đúng hoạt động kinh doanh tại mốc cần khôi phục không? | Tổng tiền, trạng thái đơn, đối soát thanh toán, tồn kho, log ứng dụng |

Không một truy vấn đơn lẻ nào chứng minh toàn bộ dữ liệu chính xác. `COUNT(*)` có thể đúng dù một số đơn hàng bị thiếu dòng chi tiết; `CHECK TABLE` có thể báo bảng ổn định về cấu trúc nhưng không phát hiện tổng tiền sai. Cần kết hợp nhiều kiểm tra độc lập và xác định trước kết quả mong đợi.

## 2. Xác định chính xác mốc dữ liệu cần phục hồi

Trước khi kiểm tra dữ liệu, cần xác định câu hỏi: hệ thống phải phản ánh trạng thái tại thời điểm nào? Ví dụ, nhóm vận hành phát hiện một lệnh xóa nhầm lúc 14:35 và muốn khôi phục tới ngay trước giao dịch đó. Mốc mục tiêu phải được xác định bằng bằng chứng, không chỉ dựa trên giờ người dùng báo sự cố.

### 2.1. Ghi nhận thông tin của backup nền

Với mỗi bộ backup, thu thập:

- Thời điểm bắt đầu và hoàn tất backup.
- Phiên bản MySQL và công cụ đã tạo backup.
- Danh sách schema hoặc phạm vi dữ liệu được backup.
- Vị trí binary log và file/position được ghi nhận tại thời điểm backup, nếu công cụ cung cấp.
- GTID set tương ứng, nếu hệ thống sử dụng GTID.
- Các incremental backup cần áp dụng và thứ tự của chúng.
- Trạng thái mã hóa và keyring cần thiết để mở dữ liệu.

Metadata đi kèm backup là điểm xuất phát để xác định phần binary log cần phát lại. Không tự suy ra vị trí bắt đầu từ tên file hoặc thời điểm tạo file. Với backup vật lý, hãy dùng metadata do công cụ backup ghi lại; với backup logic, dùng thông tin nhất quán được ghi nhận khi dump và quy trình PITR của hệ thống.

### 2.2. Tìm ranh giới giao dịch trong binary log

Binary log có thể chứa sự kiện GTID, sự kiện câu lệnh, sự kiện thay đổi hàng và dấu kết thúc giao dịch. Với row-based logging, dữ liệu thay đổi được ghi dưới dạng sự kiện hàng thay vì luôn xuất hiện thành câu SQL dễ đọc. Có thể giải mã để điều tra:

```bash
mysqlbinlog \
  --base64-output=DECODE-ROWS \
  -vv \
  --start-position=4 \
  /backup/binlog.000123 > /tmp/binlog-decoded.txt
```

Trong đầu ra, quản trị viên có thể xem GTID, thời gian sự kiện, `Table_map`, các sự kiện `Write_rows`/`Update_rows`/`Delete_rows` và dấu kết thúc giao dịch như `Xid` hoặc sự kiện commit tương ứng. Cấu trúc cụ thể phụ thuộc định dạng và phiên bản MySQL.

Khi chọn vị trí dừng, phải xác định giao dịch cuối cùng cần giữ và ranh giới commit của nó. Tránh dừng giữa một giao dịch nhiều câu lệnh hoặc giữa các sự kiện hàng của cùng giao dịch. Nếu dừng quá sớm, dữ liệu có thể thiếu một phần nghiệp vụ; nếu dừng quá muộn, giao dịch gây lỗi có thể được phát lại.

Có thể lọc log theo thời gian để hỗ trợ điều tra:

```bash
mysqlbinlog \
  --start-datetime="2026-11-19 13:00:00" \
  --stop-datetime="2026-11-19 14:34:59" \
  /backup/binlog.000123 > /tmp/binlog-window.sql
```

Thời gian trong ví dụ chỉ để minh họa. Trước khi dùng `--start-datetime` hoặc `--stop-datetime`, phải xác nhận múi giờ của máy chủ, cách ghi thời gian của log và thời điểm giao dịch thực tế. Thời gian sự kiện là công cụ định vị; với sự cố cần độ chính xác cao, hãy đối chiếu vị trí sự kiện và ranh giới giao dịch. Không coi mốc thời gian trên đồng hồ ứng dụng là tương đương tuyệt đối với thời điểm commit trong MySQL.

### 2.3. Phát lại log trên máy chủ cô lập

Chỉ phát lại binary log vào instance phục hồi đã được tách biệt. Ví dụ minh họa dùng file/position đã được xác minh trước:

```bash
mysqlbinlog \
  --start-position=4 \
  --stop-position=456789 \
  /backup/binlog.000123 \
  /backup/binlog.000124 | \
mysql --host=127.0.0.1 --port=3307 --user=restore_admin -p
```

`456789` là vị trí giả định, không dùng nguyên trạng. Nếu cần phát lại nhiều file, giữ đúng thứ tự log và kiểm tra không bỏ sót file ở giữa. Với MySQL sử dụng GTID, cần tuân thủ quy trình tương ứng với GTID set của backup và trạng thái thực thi trên máy chủ đích; không thay đổi `gtid_purged` hoặc tắt ghi log một cách tùy tiện để làm lệnh import chạy qua.

Sau khi phát lại, ghi nhận file/position cuối cùng hoặc GTID cuối cùng đã áp dụng theo cơ chế của hệ thống. Đây là một phần của bằng chứng cho biết dữ liệu đã được đưa tới đúng mốc nào.

## 3. Chuẩn bị dữ liệu tham chiếu để đối chiếu

Truy vấn trên máy chủ phục hồi chỉ cho biết trạng thái hiện tại của máy chủ đó. Để biết trạng thái có đúng hay không, cần một nguồn tham chiếu độc lập hoặc một bộ quy tắc đã được xác nhận.

Nguồn tham chiếu có thể gồm:

- Báo cáo nghiệp vụ được chốt tại thời điểm gần mốc PITR.
- Log ứng dụng ghi nhận mã đơn hàng, mã thanh toán hoặc thao tác của người dùng.
- Báo cáo đối soát từ cổng thanh toán hoặc hệ thống kế toán.
- Số lượng bản ghi và checksum được ghi nhận trong một lần backup/đối soát trước đó.
- Danh sách giao dịch đã được xác nhận hoàn tất bởi hệ thống upstream.
- Sổ ghi nhận thay đổi hoặc nhật ký vận hành có người xác nhận.

Chọn dữ liệu tham chiếu cùng phạm vi và cùng mốc thời gian với PITR. Không so sánh tổng đơn hàng của database đã phục hồi tại 14:30 với báo cáo production được tạo lúc 15:00 nếu trong 30 phút đó có thêm giao dịch hợp lệ. Khi không có nguồn tham chiếu đầy đủ, hãy ghi rõ phần nào chỉ được kiểm tra bằng quy tắc nội bộ và mức độ tin cậy còn hạn chế.

Trước khi chạy truy vấn, xác định:

1. Mốc thời gian và múi giờ của dữ liệu phục hồi.
2. Phạm vi schema, bảng và loại giao dịch cần kiểm tra.
3. Quy tắc nghiệp vụ được áp dụng tại mốc đó, bao gồm trạng thái nào được xem là hợp lệ.
4. Nguồn tham chiếu, người sở hữu dữ liệu và cách xác minh tính độc lập.
5. Ngưỡng sai lệch được phép. Với số tiền và số lượng hàng, ngưỡng thường phải bằng 0 hoặc theo quy tắc làm tròn đã công bố.

## 4. Kiểm tra cấu trúc và tính toàn vẹn quan hệ

Trước khi đối chiếu số liệu nghiệp vụ, xác nhận schema và quan hệ bảng đã được phục hồi.

### 4.1. Kiểm tra bảng và định nghĩa

```sql
SHOW DATABASES;
SHOW TABLES FROM shop_restore;
SHOW CREATE TABLE shop_restore.orders\G
SHOW CREATE TABLE shop_restore.order_items\G
```

So sánh định nghĩa bảng với schema đã được phê duyệt: kiểu dữ liệu, khóa chính, unique key, index, foreign key, charset/collation và engine. Nếu PITR có bao gồm một thay đổi DDL, xác nhận cấu trúc sau phục hồi đúng với thời điểm mục tiêu.

### 4.2. Kiểm tra trạng thái bảng

```sql
CHECK TABLE shop_restore.orders;
CHECK TABLE shop_restore.order_items;
CHECK TABLE shop_restore.payments;
```

`CHECK TABLE` có thể giúp phát hiện một số vấn đề về bảng, nhưng không thay thế kiểm tra nghiệp vụ và có thể tiêu tốn tài nguyên trên bảng lớn. Chạy trên instance phục hồi và chọn phạm vi phù hợp.

### 4.3. Tìm bản ghi mồ côi

Giả sử `order_items.order_id` tham chiếu `orders.order_id`:

```sql
SELECT COUNT(*) AS orphan_item_count
FROM shop_restore.order_items AS i
LEFT JOIN shop_restore.orders AS o
    ON o.order_id = i.order_id
WHERE o.order_id IS NULL;
```

Kết quả mong đợi là `0`. Nếu khác 0, lấy một số mẫu để điều tra:

```sql
SELECT i.order_id, i.product_id, i.quantity
FROM shop_restore.order_items AS i
LEFT JOIN shop_restore.orders AS o
    ON o.order_id = i.order_id
WHERE o.order_id IS NULL
ORDER BY i.order_id
LIMIT 20;
```

Thực hiện kiểm tra tương tự với payment, shipment, inventory movement hoặc các bảng con khác. Một số hệ thống cho phép bản ghi tham chiếu bị xóa theo chính sách lưu trữ; khi đó cần xác định ngoại lệ hợp lệ thay vì mặc định mọi quan hệ thiếu đều là lỗi PITR.

## 5. Kiểm tra số lượng và phạm vi dữ liệu

Số lượng bản ghi là phép kiểm tra nhanh để phát hiện thiếu dữ liệu trên diện rộng. Cần so sánh với số liệu tham chiếu đúng mốc thời gian và đúng phạm vi.

```sql
SELECT 'orders' AS table_name, COUNT(*) AS row_count
FROM shop_restore.orders
UNION ALL
SELECT 'order_items', COUNT(*)
FROM shop_restore.order_items
UNION ALL
SELECT 'payments', COUNT(*)
FROM shop_restore.payments;
```

Kiểm tra khoảng khóa và thời gian:

```sql
SELECT
    MIN(order_id) AS min_order_id,
    MAX(order_id) AS max_order_id,
    MIN(created_at) AS first_order_at,
    MAX(created_at) AS last_order_at
FROM shop_restore.orders;
```

Phạm vi `MIN`/`MAX` giống nhau không chứng minh không thiếu bản ghi ở giữa. Kết hợp thêm phân bố theo ngày hoặc theo phân vùng nghiệp vụ:

```sql
SELECT
    DATE(created_at) AS order_day,
    COUNT(*) AS order_count
FROM shop_restore.orders
WHERE created_at >= '2026-11-01 00:00:00'
  AND created_at <  '2026-11-20 00:00:00'
GROUP BY DATE(created_at)
ORDER BY order_day;
```

Các ngày trong truy vấn chỉ là ví dụ. Dùng khoảng thời gian phù hợp với mốc PITR và quy tắc múi giờ của hệ thống. Nếu ứng dụng lưu UTC, nên lọc theo UTC và chuyển đổi sang giờ nghiệp vụ ở lớp báo cáo.

Để tìm bản ghi trùng theo một mã nghiệp vụ phải duy nhất:

```sql
SELECT external_order_ref, COUNT(*) AS duplicate_count
FROM shop_restore.orders
WHERE external_order_ref IS NOT NULL
GROUP BY external_order_ref
HAVING COUNT(*) > 1;
```

Kết quả mong đợi là không có nhóm trùng nếu `external_order_ref` được quy định là duy nhất. Nếu tính duy nhất chỉ có hiệu lực trong từng cửa hàng hoặc từng tenant, phải đưa khóa phạm vi vào `GROUP BY`.

## 6. Đối chiếu các bất biến nghiệp vụ

Bất biến nghiệp vụ là điều kiện dữ liệu phải luôn thỏa mãn nếu giao dịch được ghi nhận đúng. Đây là phần quan trọng nhất để phát hiện PITR có thiếu hoặc thừa giao dịch.

### 6.1. Tổng tiền đơn hàng khớp với dòng chi tiết

Giả sử `orders.total_amount` được tính từ `order_items.quantity * order_items.unit_price`. Truy vấn sau tìm đơn hàng có tổng dòng chi tiết khác tổng đã lưu:

```sql
SELECT
    o.order_id,
    o.total_amount,
    ROUND(SUM(i.quantity * i.unit_price), 2) AS item_total
FROM shop_restore.orders AS o
LEFT JOIN shop_restore.order_items AS i
    ON i.order_id = o.order_id
GROUP BY o.order_id, o.total_amount
HAVING ABS(
    o.total_amount - ROUND(COALESCE(SUM(i.quantity * i.unit_price), 0), 2)
) > 0.01;
```

Đây chỉ là ví dụ nếu tổng đơn không bao gồm thuế, phí vận chuyển, chiết khấu hoặc điều chỉnh khác. Với hệ thống thực tế, phải dùng đúng công thức nghiệp vụ và kiểu `DECIMAL` đã quy định. Không dùng `FLOAT` để đối chiếu tiền khi hệ thống yêu cầu số học thập phân chính xác.

### 6.2. Thanh toán khớp với trạng thái đơn hàng

Giả sử bảng `payments` ghi các khoản đã thanh toán và `payment_status='SETTLED'` biểu thị giao dịch đã quyết toán. Có thể tìm đơn hàng đã đánh dấu thanh toán nhưng số tiền quyết toán không khớp:

```sql
SELECT
    o.order_id,
    o.total_amount,
    COALESCE(SUM(
        CASE WHEN p.payment_status = 'SETTLED'
             THEN p.amount ELSE 0 END
    ), 0) AS settled_amount
FROM shop_restore.orders AS o
LEFT JOIN shop_restore.payments AS p
    ON p.order_id = o.order_id
WHERE o.order_status = 'PAID'
GROUP BY o.order_id, o.total_amount
HAVING ABS(
    o.total_amount - COALESCE(SUM(
        CASE WHEN p.payment_status = 'SETTLED'
             THEN p.amount ELSE 0 END
    ), 0)
) > 0.01;
```

Kết quả cần được diễn giải theo mô hình thanh toán. Một đơn có thể được thanh toán nhiều lần từng phần, hoàn tiền một phần hoặc có phí khác nhau. Hãy điều chỉnh công thức theo chính sách của hệ thống và kiểm tra thêm mã giao dịch của cổng thanh toán để phát hiện giao dịch trùng.

### 6.3. Tồn kho phù hợp với sổ biến động

Nếu hệ thống lưu số lượng tồn hiện tại trong `inventory_balance` và lịch sử biến động trong `inventory_movements`, có thể kiểm tra quan hệ tổng quát:

```sql
SELECT
    b.product_id,
    b.warehouse_id,
    b.quantity_on_hand,
    b.opening_quantity,
    COALESCE(SUM(m.quantity_delta), 0) AS movement_total
FROM shop_restore.inventory_balance AS b
LEFT JOIN shop_restore.inventory_movements AS m
    ON m.product_id = b.product_id
   AND m.warehouse_id = b.warehouse_id
GROUP BY
    b.product_id,
    b.warehouse_id,
    b.quantity_on_hand,
    b.opening_quantity
HAVING b.quantity_on_hand <>
       b.opening_quantity + COALESCE(SUM(m.quantity_delta), 0);
```

Truy vấn này giả định bảng số dư có `opening_quantity` và toàn bộ biến động kể từ mốc mở sổ được lưu trong bảng movement. Nếu hệ thống có kiểm kê, điều chỉnh, chuyển kho hoặc snapshot định kỳ, phải đưa các nghiệp vụ đó vào công thức. Bất biến phải phản ánh đúng cách hệ thống tính tồn kho.

### 6.4. Trạng thái và chuỗi sự kiện hợp lệ

Một số trạng thái chỉ được chuyển theo thứ tự nhất định, ví dụ đơn hàng không thể chuyển thẳng từ `CREATED` sang `SHIPPED` nếu chưa qua các bước xác nhận thanh toán và đóng gói. Nếu hệ thống lưu lịch sử trạng thái, hãy kiểm tra các chuyển đổi không hợp lệ theo state machine đã định nghĩa.

Ví dụ, nếu `order_status_history` lưu trạng thái sau mỗi lần thay đổi:

```sql
SELECT order_id, COUNT(*) AS invalid_transition_count
FROM shop_restore.order_status_history
WHERE (previous_status = 'CREATED' AND new_status = 'SHIPPED')
   OR (previous_status = 'CANCELLED' AND new_status = 'PAID')
GROUP BY order_id;
```

Các chuyển đổi trên chỉ là ví dụ. Có hệ thống cho phép giao hàng thu tiền hoặc mở lại đơn đã hủy theo quy trình riêng. Dùng danh sách chuyển đổi được nghiệp vụ phê duyệt để tránh báo lỗi giả.

## 7. Đối chiếu với nguồn bằng chứng độc lập

Các bất biến nội bộ giúp tìm dữ liệu bất hợp lý, nhưng một bộ dữ liệu sai vẫn có thể tự nhất quán. Ví dụ, nếu cả đơn hàng và thanh toán cùng bị thiếu, tổng tiền của các bảng còn lại vẫn có thể khớp. Vì vậy cần đối chiếu với hệ thống độc lập.

### 7.1. Đối chiếu theo mã giao dịch

Chọn một tập mã giao dịch đã được hệ thống upstream xác nhận trước mốc sự cố. Với mỗi mã, kiểm tra:

- Có tồn tại đúng một đơn hàng trong schema phục hồi hay không.
- Có đủ các dòng chi tiết và số lượng sản phẩm không.
- Mã giao dịch thanh toán có tồn tại và trạng thái có đúng không.
- Số tiền và tiền tệ có khớp với bằng chứng độc lập không.
- Thời gian tạo, thời gian thanh toán và thời gian cập nhật có nằm trước mốc dừng không.

Không cần chỉ chọn các giao dịch đầu/cuối. Nên chọn mẫu theo khoảng thời gian, giá trị, trạng thái và nhóm sản phẩm; đồng thời kiểm tra toàn bộ các giao dịch trọng yếu được nghiệp vụ đánh dấu.

### 7.2. Đối chiếu tổng hợp

Ví dụ báo cáo tổng hợp số đơn và tổng tiền theo ngày:

```sql
SELECT
    DATE(created_at) AS order_day,
    COUNT(*) AS order_count,
    SUM(total_amount) AS gross_amount
FROM shop_restore.orders
WHERE created_at >= '2026-11-01 00:00:00'
  AND created_at <  '2026-11-20 00:00:00'
  AND order_status IN ('PAID', 'SHIPPED', 'COMPLETED')
GROUP BY DATE(created_at)
ORDER BY order_day;
```

So sánh với báo cáo nghiệp vụ cùng điều kiện lọc, cùng múi giờ và cùng mốc PITR. Hai báo cáo chỉ có ý nghĩa khi cách định nghĩa doanh thu, hoàn tiền, hủy đơn và thuế giống nhau.

### 7.3. Phân biệt dữ liệu thiếu với dữ liệu phát sinh sau mốc

Một giao dịch không xuất hiện trong database phục hồi chưa chắc là bị mất. Nếu giao dịch được tạo sau mốc PITR, việc không có nó là đúng. Ngược lại, giao dịch được xác nhận trước mốc dừng nhưng không xuất hiện có thể cho thấy backup nền hoặc binlog chưa đầy đủ.

Để phân loại, đối chiếu ba thời điểm:

1. Thời điểm sự kiện được ghi nhận ở hệ thống upstream.
2. Thời điểm giao dịch commit trong MySQL hoặc sự kiện tương ứng trong binary log.
3. Mốc dừng đã chọn của PITR.

Đối với hệ thống có đồng bộ bất đồng bộ, độ trễ giữa upstream và MySQL có thể làm hai thời điểm khác nhau. Cần hiểu thứ tự ghi nhận của kiến trúc trước khi kết luận mất dữ liệu.

## 8. Kiểm tra PITR không phát lại giao dịch gây lỗi

Một mục tiêu thường gặp của PITR là giữ lại mọi giao dịch hợp lệ trước một thao tác sai và loại trừ thao tác đó cùng các giao dịch không mong muốn sau nó.

Ví dụ, lúc 14:20 một quản trị viên chạy nhầm `DELETE` trên bảng `orders`; lúc 14:35 nhóm vận hành bắt đầu phục hồi. Cần xác định:

- Giao dịch cuối cùng hợp lệ trước lệnh xóa.
- GTID hoặc file/position của giao dịch đó, nếu có.
- Vị trí và phạm vi giao dịch xóa.
- Các giao dịch hợp lệ khác xảy ra sau đó nhưng trước khi phát hiện sự cố.
- Quyết định có cần tái áp dụng thủ công các giao dịch hợp lệ sau mốc dừng hay không.

Không chỉ nhìn timestamp rồi dừng tùy ý. Một giao dịch có thể bắt đầu trước mốc đồng hồ nhưng commit sau đó; transaction lớn có thể bao gồm nhiều sự kiện binlog. Xác nhận ranh giới commit và kiểm tra các mã nghiệp vụ quan trọng trước khi chấp nhận.

Nếu có giao dịch hợp lệ sau giao dịch gây lỗi, có thể cần phục hồi tới trước giao dịch sai rồi tái áp dụng có chọn lọc bằng quy trình được kiểm soát. Việc tái áp dụng phải bảo đảm tính idempotent hoặc có kiểm tra chống trùng, đồng thời ghi nhận đầy đủ các thay đổi thủ công. Không phát lại lại toàn bộ log sau mốc sai mà chưa phân tích phụ thuộc giữa các giao dịch.

## 9. Quy trình kiểm chứng sau PITR

Một quy trình có thể lặp lại nên thực hiện theo thứ tự sau:

1. **Đóng băng mục tiêu:** ghi rõ mốc thời gian, múi giờ, file/position hoặc GTID cần đạt và lý do chọn mốc.
2. **Xác minh nguồn:** kiểm tra backup nền, checksum, metadata và toàn bộ binary log cần thiết.
3. **Phục hồi cô lập:** restore backup nền, chuẩn bị keyring, phát lại log và giữ instance ngoài mạng production.
4. **Ghi nhận trạng thái:** lưu phiên bản MySQL, file/position cuối, GTID set, error log và thời gian hoàn tất.
5. **Kiểm tra cấu trúc:** xác minh schema, bảng, index, khóa ngoại, view, trigger và routine.
6. **Kiểm tra dữ liệu:** đối chiếu số lượng, phạm vi ID, khoảng thời gian, bản ghi trùng và bản ghi mồ côi.
7. **Kiểm tra nghiệp vụ:** chạy các bất biến về đơn hàng, thanh toán, tồn kho hoặc nghiệp vụ đặc thù.
8. **Đối chiếu độc lập:** so sánh với báo cáo, log ứng dụng hoặc hệ thống upstream tại cùng mốc.
9. **Kiểm tra ứng dụng:** chạy smoke test đọc dữ liệu và các luồng nghiệp vụ an toàn trên môi trường thử nghiệm.
10. **Ra quyết định:** chấp nhận, chấp nhận có giới hạn hoặc phục hồi lại từ đầu; lưu bằng chứng và người phê duyệt.

Giữ `event_scheduler` tắt và chặn kết nối ra các dịch vụ production trong toàn bộ giai đoạn kiểm chứng. Nếu cần thử luồng ghi, dùng endpoint và dữ liệu giả lập của môi trường thử nghiệm, sau đó khôi phục trạng thái ban đầu hoặc dựng lại môi trường sạch.

## 10. Mẫu báo cáo kiểm chứng

Ghi kết quả theo từng nhóm kiểm tra để người khác có thể đánh giá lại. Một báo cáo ngắn có thể có cấu trúc sau:

| Trường | Giá trị cần ghi |
|---|---|
| Incident / yêu cầu | Mã sự cố hoặc yêu cầu diễn tập |
| Backup nền | ID, thời điểm, checksum và công cụ tạo backup |
| Mốc PITR | Múi giờ, thời gian, binlog file/position hoặc GTID cuối |
| Môi trường | Host thử nghiệm, port, phiên bản MySQL và trạng thái cô lập |
| Kiểm tra kỹ thuật | Kết quả khởi động, error log, InnoDB và keyring |
| Kiểm tra cấu trúc | Số schema/bảng/view/routine, khóa và index |
| Kiểm tra dữ liệu | Số hàng, bản ghi trùng/mồ côi và checksum nếu có |
| Kiểm tra nghiệp vụ | Tổng đơn, tổng thanh toán, tồn kho và quy tắc khác |
| Bằng chứng độc lập | Báo cáo upstream, log ứng dụng, đối soát và phạm vi so sánh |
| Sai lệch | Số lượng, mức độ, nguyên nhân và cách xử lý |
| Kết luận | PASS, PASS WITH LIMITATIONS hoặc FAIL |
| Người xác nhận | Người thực hiện và người sở hữu nghiệp vụ |

Không ghi mật khẩu, token, nội dung keyring hoặc bí mật KMS vào báo cáo. Dùng định danh tham chiếu đến kho bí mật có kiểm soát nếu cần lưu thông tin truy cập.

### 10.1. Tiêu chí chấp nhận gợi ý

Một lần PITR có thể được chấp nhận khi:

- Mốc dừng được xác định rõ và kết thúc tại ranh giới giao dịch hợp lệ.
- MySQL khởi động và mở được các tablespace cần thiết; không có lỗi nghiêm trọng chưa giải thích.
- Các schema và đối tượng thiết yếu tồn tại đúng với thời điểm mục tiêu.
- Các kiểm tra quan hệ không phát hiện bản ghi mồ côi ngoài các ngoại lệ đã được giải thích.
- Các bất biến nghiệp vụ trọng yếu đạt ngưỡng đã thống nhất.
- Mẫu giao dịch được đối chiếu với bằng chứng độc lập và không có sai lệch chưa giải thích.
- Máy chủ phục hồi vẫn được cô lập và không phát sinh tác động ngoài ý muốn.

Nếu không có nguồn tham chiếu độc lập cho một nhóm dữ liệu, không nên đánh dấu nhóm đó là đã kiểm chứng đầy đủ. Ghi rõ giới hạn, rủi ro còn lại và người có thẩm quyền chấp nhận giới hạn đó.

## 11. Sai lệch thường gặp và cách điều tra

| Dấu hiệu | Nguyên nhân có thể | Hướng điều tra |
|---|---|---|
| Số đơn thấp hơn báo cáo | Backup nền thiếu dữ liệu hoặc binlog dừng quá sớm | Đối chiếu metadata backup, binlog, GTID và các mã đơn bị thiếu |
| Số đơn cao hơn dự kiến | PITR phát lại quá mốc, import lặp hoặc tái áp dụng giao dịch hai lần | Kiểm tra mốc dừng, transaction ID, GTID và mã nghiệp vụ trùng |
| Tổng tiền không khớp | Thiếu dòng chi tiết, sai trạng thái, hoàn tiền hoặc công thức tổng hợp không đồng nhất | So sánh từng đơn, payment reference và quy tắc tính doanh thu |
| Bản ghi con không có bản ghi cha | Thiếu một phần giao dịch hoặc schema được restore không đầy đủ | Kiểm tra foreign key, thứ tự import và các sự kiện binlog liên quan |
| Tồn kho lệch | Thiếu movement, phát lại giao dịch trùng hoặc bỏ sót snapshot kiểm kê | Đối chiếu ledger, snapshot và mã giao dịch kho |
| Có đơn sau mốc PITR | Mốc thời gian/múi giờ bị hiểu sai hoặc log được phát lại quá xa | Kiểm tra timestamp, transaction boundary, file/position và nguồn thời gian |
| Bảng hợp lệ nhưng nghiệp vụ sai | Kiểm tra chỉ dừng ở cấu trúc hoặc số lượng | Bổ sung bất biến nghiệp vụ và đối chiếu độc lập |
| Không thể mở bảng mã hóa | Keyring hoặc quyền truy cập khóa không khớp backup | Kiểm tra cấu hình keyring, lịch sử khóa và error log |

Khi phát hiện sai lệch, giữ nguyên backup gốc, bản phục hồi và log điều tra. Ghi rõ truy vấn, tham số, thời điểm chạy và kết quả. Nếu cần thay đổi mốc PITR, nên dựng lại từ backup nền sạch rồi phát lại log tới mốc mới; tránh tiếp tục phát log trên instance đã ở trạng thái không rõ ràng.

## 12. Tình huống thực hành

Một cửa hàng trực tuyến sử dụng ba bảng chính:

- `orders`: mã đơn, trạng thái, tổng tiền và thời gian tạo.
- `order_items`: các sản phẩm, số lượng và đơn giá của từng đơn.
- `payments`: mã giao dịch thanh toán, số tiền và trạng thái quyết toán.

Lúc 14:20, một lệnh xóa nhầm làm mất một nhóm đơn hàng. Nhóm vận hành có backup nền và binary log liên tục tới sau thời điểm sự cố. Yêu cầu là phục hồi tới ngay trước giao dịch xóa, sau đó chứng minh dữ liệu phù hợp với hoạt động kinh doanh tại mốc đó.

Thực hiện trong môi trường lab:

1. Ghi lại metadata backup nền, file/position hoặc GTID và phiên bản MySQL.
2. Dùng `mysqlbinlog` đọc log quanh thời điểm sự cố, xác định giao dịch xóa và giao dịch commit hợp lệ ngay trước nó.
3. Restore backup vào instance cô lập và phát lại binary log đến ranh giới đã chọn.
4. Ghi nhận vị trí hoặc GTID cuối cùng đã áp dụng; kiểm tra error log và khả năng mở bảng.
5. Chạy truy vấn đếm đơn, dòng chi tiết và thanh toán; tìm bản ghi mồ côi và mã đơn trùng.
6. Tính lại tổng tiền từ dòng chi tiết theo đúng quy tắc thuế, phí và chiết khấu của lab.
7. Đối chiếu một tập mã đơn và mã thanh toán với log ứng dụng hoặc file đối soát được tạo tại cùng mốc thời gian.
8. Xác minh các đơn được tạo sau mốc dừng không xuất hiện và các giao dịch hợp lệ trước mốc vẫn tồn tại.
9. Lập báo cáo PASS/FAIL cho từng nhóm kiểm tra, ghi sai lệch và nguyên nhân.
10. Thử thay đổi mốc dừng trong một lần phục hồi mới để quan sát cách thiếu hoặc thừa một giao dịch ảnh hưởng tới các bất biến nghiệp vụ.

**Câu hỏi tự đánh giá:**

- Vì sao MySQL khởi động thành công chưa đủ chứng minh PITR chính xác?
- Vì sao phải dừng binary log tại ranh giới commit của giao dịch?
- Tại sao `COUNT(*)` và `CHECK TABLE` không thể thay thế đối chiếu nghiệp vụ?
- Làm thế nào phân biệt một giao dịch bị mất với giao dịch phát sinh sau mốc PITR?
- Vì sao cần đối chiếu tổng thanh toán với nguồn độc lập thay vì chỉ so sánh hai bảng trong cùng database?
- Khi có giao dịch hợp lệ sau giao dịch gây lỗi, cần xử lý thế nào để tránh phát lại trùng hoặc phá vỡ thứ tự nghiệp vụ?
- Báo cáo kiểm chứng cần ghi những thông tin nào để một người khác có thể đánh giá lại kết quả?

## Kết luận

Kiểm chứng PITR phải trả lời được hai câu hỏi: MySQL đã phục hồi tới đúng ranh giới giao dịch chưa, và dữ liệu tại ranh giới đó có phản ánh đúng hoạt động nghiệp vụ không. Hãy kết hợp metadata backup, vị trí hoặc GTID cuối, kiểm tra cấu trúc, truy vấn quan hệ, bất biến nghiệp vụ và bằng chứng độc lập. Chỉ chấp nhận kết quả khi sai lệch đã được giải thích, giới hạn còn lại được ghi nhận và môi trường phục hồi vẫn nằm trong phạm vi cô lập.
