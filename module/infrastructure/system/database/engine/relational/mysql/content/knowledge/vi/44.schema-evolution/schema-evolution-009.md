# Backfill dữ liệu theo khóa ổn định và khả năng tiếp tục sau lỗi

Backfill là quá trình điền hoặc chuyển đổi dữ liệu cho các hàng đã tồn tại sau khi schema thay đổi. Ví dụ: thêm cột mới rồi tính giá trị từ cột cũ, chuẩn hóa dữ liệu lịch sử, bổ sung mã phân loại hoặc chuyển dữ liệu sang định dạng mới. Với bảng lớn, backfill cần chia thành các lô nhỏ, xác định vị trí tiến độ bằng khóa ổn định và lưu checkpoint để có thể tiếp tục sau khi tiến trình dừng.

Một backfill an toàn phải phối hợp ba việc: xác định chính xác hàng đã xử lý, tránh ghi đè thay đổi mới từ ứng dụng và lưu tiến độ cùng transaction cập nhật dữ liệu. Nếu chỉ lưu số hàng đã xử lý hoặc dùng OFFSET, tiến trình có thể bỏ sót hay xử lý lặp khi dữ liệu thay đổi. Nếu checkpoint được ghi trước dữ liệu, lần chạy sau có thể bỏ qua các hàng chưa được cập nhật.

Bài học thuộc chương **Thay đổi schema** của module **DATABASE_MYSQL**. Module bao quát thiết kế bảng, kiểu dữ liệu, khóa, truy vấn SQL, index, transaction, phân quyền, sao lưu và vận hành cơ sở dữ liệu quan hệ. Nội dung tập trung vào MySQL 8.0 và InnoDB; hãy kiểm tra phiên bản, isolation level, engine và hành vi DDL của hệ thống đang vận hành.

Sau bài học, bạn có thể:

- Thiết kế backfill theo primary key hoặc unique key ổn định.
- Dùng keyset pagination thay cho OFFSET.
- Chia batch, lưu checkpoint và tiếp tục tiến trình sau lỗi.
- Bảo vệ dữ liệu khi ứng dụng vẫn đọc/ghi trong lúc backfill.
- Xử lý khóa ghép, hàng bị xóa, dữ liệu mới và batch retry.
- Điều tiết tải lên source, replica, binary log và storage.
- Đối chiếu dữ liệu để xác nhận backfill hoàn tất.

## 1. Backfill xuất hiện khi nào?

Backfill thường là một bước trong chiến lược thay đổi schema theo hướng mở rộng rồi thu hẹp (expand-and-contract). Thay đổi được triển khai thành các giai đoạn nhỏ để ứng dụng cũ và mới có thể cùng hoạt động trong thời gian chuyển tiếp.

Ví dụ bảng đơn hàng ban đầu lưu tên khách hàng trong cột customer_name. Ứng dụng mới cần thêm customer_name_normalized để tìm kiếm không phân biệt hoa thường:

~~~sql
ALTER TABLE sales.orders
  ADD COLUMN customer_name_normalized VARCHAR(200) NULL;
~~~

Sau khi thêm cột, các hàng cũ vẫn có giá trị NULL. Backfill sẽ tính dữ liệu cho những hàng đó:

~~~sql
UPDATE sales.orders
SET customer_name_normalized = LOWER(TRIM(customer_name))
WHERE customer_name_normalized IS NULL;
~~~

Với vài nghìn hàng, một câu UPDATE có thể đủ nhanh. Với hàng chục hoặc hàng trăm triệu hàng, câu lệnh lớn có thể giữ khóa lâu, tạo lượng redo/undo và binary log lớn, làm tăng replica lag và ảnh hưởng giao dịch trực tuyến. Khi đó, chia thành batch nhỏ giúp kiểm soát thời gian khóa, tải và khả năng phục hồi.

Các trường hợp thường gặp:

- Thêm cột mới được tính từ cột hiện có.
- Chuyển định dạng ngày, mã vùng, số điện thoại hoặc chuỗi chuẩn hóa.
- Điền foreign key mới dựa trên bảng tham chiếu.
- Di chuyển dữ liệu từ cột cũ sang cấu trúc mới.
- Bổ sung giá trị mặc định theo quy tắc nghiệp vụ mới.
- Tạo dữ liệu phục vụ index hoặc tìm kiếm mới.

Nếu giá trị có thể được tính tự động bằng generated column và không cần lưu riêng, hãy đánh giá lựa chọn đó trước khi tạo một tiến trình backfill. Backfill phù hợp khi cần ghi dữ liệu vật lý, chuyển đổi có trạng thái hoặc tính toán không thể biểu diễn phù hợp bằng generated column.

## 2. Các nguyên tắc thiết kế

Một tiến trình backfill tốt cần các thuộc tính sau:

1. **Có thứ tự ổn định.** Mỗi hàng được định danh bằng khóa duy nhất, không thay đổi trong suốt tiến trình.
2. **Có thể lặp lại an toàn.** Chạy lại một batch không làm sai dữ liệu đã đúng.
3. **Có checkpoint bền vững.** Tiến độ được lưu trong database hoặc một kho trạng thái đáng tin cậy.
4. **Checkpoint nguyên tử với dữ liệu.** Một batch và vị trí hoàn tất của nó được commit trong cùng transaction.
5. **Tương thích với ghi đồng thời.** Ứng dụng vẫn có thể thay đổi dữ liệu mà backfill không ghi đè giá trị mới hơn.
6. **Có giới hạn tài nguyên.** Batch nhỏ, có thể tạm dừng và điều chỉnh tốc độ.
7. **Có bước đối chiếu cuối.** Không coi việc cursor đi đến cuối khóa là bằng chứng duy nhất rằng mọi hàng đã đúng.

Không nên xác định tiến độ chỉ bằng số hàng đã cập nhật. Hàng có thể bị xóa, thêm mới, bỏ qua do điều kiện hoặc có khóa bị khuyết. Khóa ổn định giúp xác định vị trí dữ liệu đã quét, còn điều kiện backfill và bước đối chiếu xác nhận giá trị đã được chuyển đúng.

## 3. Chọn khóa ổn định

### 3.1. Ưu tiên primary key bất biến

Ví dụ bảng có primary key order_id:

~~~sql
CREATE TABLE sales.orders (
  order_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  customer_name VARCHAR(200) NOT NULL,
  customer_name_normalized VARCHAR(200) NULL,
  updated_at TIMESTAMP NOT NULL
    DEFAULT CURRENT_TIMESTAMP
    ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (order_id)
) ENGINE=InnoDB;
~~~

order_id phù hợp làm cursor nếu ứng dụng không thay đổi giá trị khóa sau khi tạo hàng. Truy vấn batch có thể dùng:

~~~sql
SELECT order_id
FROM sales.orders
WHERE order_id > ?
ORDER BY order_id
LIMIT 500;
~~~

Mỗi batch lấy tối đa 500 khóa lớn hơn cursor hiện tại. Sau khi xử lý thành công, cursor chuyển đến khóa lớn nhất trong batch vừa quét.

Khóa ổn định không nhất thiết phải liên tục. Nếu các giá trị là 1, 2, 7, 20, tiến trình vẫn có thể đi từ 2 tới 7, rồi 20. Không cần giả định mọi số khóa đều tồn tại.

### 3.2. Tránh OFFSET trên bảng lớn

Cách phân trang bằng OFFSET thường không phù hợp cho backfill quy mô lớn:

~~~sql
SELECT order_id
FROM sales.orders
ORDER BY order_id
LIMIT 500 OFFSET 500000;
~~~

Khi offset tăng, server có thể phải đọc và bỏ qua nhiều hàng trước khi trả về batch cần lấy. Nếu dữ liệu bị thêm/xóa trong lúc chạy, vị trí theo offset cũng có thể dịch chuyển, gây lặp hoặc bỏ sót hàng.

Keyset pagination dùng giá trị khóa cuối cùng:

~~~sql
SELECT order_id
FROM sales.orders
WHERE order_id > ?
ORDER BY order_id
LIMIT 500;
~~~

Truy vấn này tận dụng index trên primary key và tiếp tục từ một vị trí rõ ràng. Với điều kiện lọc bổ sung, cần index phù hợp để tránh mỗi batch phải quét quá nhiều hàng.

### 3.3. Khóa ghép

Một số bảng dùng primary key ghép, ví dụ (tenant_id, order_id). Cursor phải lưu đủ các thành phần khóa để xác định vị trí duy nhất.

Điều kiện tiếp tục theo thứ tự từ điển có thể viết tường minh:

~~~sql
SELECT tenant_id, order_id
FROM sales.tenant_orders
WHERE tenant_id > ?
   OR (tenant_id = ? AND order_id > ?)
ORDER BY tenant_id, order_id
LIMIT 500;
~~~

Có thể dùng row constructor trong một số truy vấn:

~~~sql
SELECT tenant_id, order_id
FROM sales.tenant_orders
WHERE (tenant_id, order_id) > (?, ?)
ORDER BY tenant_id, order_id
LIMIT 500;
~~~

Hãy kiểm tra execution plan trên phiên bản MySQL đang dùng để xác nhận index được tận dụng. Trong checkpoint, lưu cả tenant_id và order_id; chỉ lưu một thành phần sẽ không xác định được vị trí duy nhất.

### 3.4. Khi không có khóa phù hợp

Nếu bảng không có primary key hoặc unique key ổn định, cần đánh giá cách nhận diện hàng trước khi backfill. Có thể bổ sung khóa phù hợp theo quy trình migration riêng, hoặc dùng một unique key hiện có nếu nó không thay đổi và thực sự duy nhất.

Không dùng updated_at làm cursor duy nhất nếu nhiều hàng có cùng timestamp hoặc timestamp có thể thay đổi trong lúc xử lý. Không dùng vị trí vật lý của hàng, thứ tự mặc định của SELECT hoặc một giá trị không duy nhất làm checkpoint.

## 4. Chọn phạm vi và high-water mark

Với bảng tiếp tục nhận hàng mới, có thể xác định một high-water mark ở đầu đợt backfill:

~~~sql
SELECT MAX(order_id) AS high_watermark
FROM sales.orders;
~~~

Giả sử kết quả là 9000000. Tiến trình xử lý phạm vi đến khóa đó:

~~~sql
SELECT order_id
FROM sales.orders
WHERE order_id > ?
  AND order_id <= 9000000
ORDER BY order_id
LIMIT 500;
~~~

High-water mark giúp một lượt chạy có điểm kết thúc xác định, tránh tiến trình liên tục đuổi theo các hàng mới được thêm vào. Tuy nhiên, nó không thay thế cơ chế xử lý ghi đồng thời.

Nếu ứng dụng hoặc hệ thống nhập dữ liệu có thể tạo hàng với khóa nhỏ hơn hoặc bằng high-water mark, một hàng mới có thể xuất hiện phía sau cursor và bị bỏ qua trong lượt quét đầu. Ngay cả với AUTO_INCREMENT, không nên coi giả định khóa mới luôn lớn hơn cursor là đủ cho mọi hệ thống, vì có thể có import ID tường minh hoặc dữ liệu được nạp trễ.

Cách xử lý:

- Bật dual-write hoặc cơ chế đồng bộ tương đương trước khi backfill.
- Chạy lượt reconciliation sau khi quét hết phạm vi ban đầu.
- Nếu có nguồn thay đổi liên tục, dùng change log/CDC hoặc một cơ chế theo dõi thay đổi để xử lý phần phát sinh.
- Chỉ kết thúc migration khi các hàng còn thiếu đã được đối chiếu và không còn đường ghi cũ tạo dữ liệu chưa chuyển.

Với khóa ghép, high-water mark cũng phải chứa toàn bộ các thành phần khóa.

## 5. Thiết kế checkpoint

Checkpoint lưu vị trí tiến độ của một job để tiến trình có thể tiếp tục sau khi ứng dụng, worker hoặc máy chủ bị dừng. Có thể dùng một bảng riêng:

~~~sql
CREATE TABLE ops.backfill_checkpoint (
  job_name VARCHAR(100) NOT NULL,
  last_order_id BIGINT UNSIGNED NULL,
  high_watermark BIGINT UNSIGNED NOT NULL,
  rows_scanned BIGINT UNSIGNED NOT NULL DEFAULT 0,
  rows_changed BIGINT UNSIGNED NOT NULL DEFAULT 0,
  status ENUM('PENDING', 'RUNNING', 'PAUSED', 'DONE', 'FAILED')
    NOT NULL DEFAULT 'PENDING',
  updated_at TIMESTAMP NOT NULL
    DEFAULT CURRENT_TIMESTAMP
    ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (job_name)
) ENGINE=InnoDB;
~~~

Các trường có ý nghĩa:

- job_name: tên duy nhất của đợt backfill; dùng để phân biệt các lần migration.
- last_order_id: khóa cuối cùng đã quét và commit thành công; NULL biểu thị chưa bắt đầu.
- high_watermark: giới hạn trên của lượt chạy hiện tại.
- rows_scanned: số hàng đã kiểm tra, có thể gồm cả hàng không cần cập nhật.
- rows_changed: số hàng thực sự được thay đổi theo điều kiện cập nhật.
- status: trạng thái vận hành để worker hoặc người quản trị biết job đang chạy, tạm dừng hay hoàn tất.

Kiểu khóa trong checkpoint phải khớp với kiểu khóa thực tế. Nếu primary key là BIGINT có dấu, UUID, chuỗi hoặc khóa ghép, hãy thiết kế các cột cursor tương ứng. Với khóa ghép, lưu từng thành phần và dùng một checkpoint cho mỗi worker/range nếu chạy song song.

Khởi tạo job sau khi đã xác định phạm vi:

~~~sql
INSERT INTO ops.backfill_checkpoint (
  job_name,
  last_order_id,
  high_watermark,
  status
)
SELECT
  'orders-normalize-name-v1',
  NULL,
  COALESCE(MAX(order_id), 0),
  'PENDING'
FROM sales.orders;
~~~

COALESCE(MAX(...), 0) trong ví dụ giả định khóa unsigned bắt đầu từ 1. Nếu khóa có thể bằng 0, âm hoặc không phải số, hãy dùng sentinel phù hợp hoặc lưu trạng thái bắt đầu riêng.

Không ghi checkpoint vào file log cục bộ như nguồn trạng thái duy nhất. Nếu máy chạy job bị mất, file có thể không đồng bộ với transaction dữ liệu đã commit.

## 6. Batch update có thể chạy lại an toàn

Ví dụ cần điền customer_name_normalized từ customer_name. Một batch xử lý khoảng khóa từ last_id đến batch_end:

~~~sql
UPDATE sales.orders
SET customer_name_normalized = LOWER(TRIM(customer_name))
WHERE order_id > ?
  AND order_id <= ?
  AND customer_name_normalized IS NULL;
~~~

Điều kiện customer_name_normalized IS NULL làm thao tác có tính idempotent trong tình huống giá trị đích chỉ cần điền một lần. Nếu batch được chạy lại, những hàng đã có giá trị sẽ không bị cập nhật lần nữa.

Tuy nhiên, NULL có thể là kết quả hợp lệ của phép chuyển đổi trong một số nghiệp vụ. Khi đó, không thể dùng target IS NULL làm dấu hiệu duy nhất cho biết hàng chưa xử lý. Hãy thêm cột trạng thái/version riêng hoặc xác định một điều kiện hoàn tất khác.

Ví dụ dùng cờ migration:

~~~sql
ALTER TABLE sales.orders
  ADD COLUMN name_backfill_version TINYINT UNSIGNED NOT NULL DEFAULT 0;
~~~

Sau đó:

~~~sql
UPDATE sales.orders
SET customer_name_normalized = LOWER(TRIM(customer_name)),
    name_backfill_version = 1
WHERE order_id > ?
  AND order_id <= ?
  AND name_backfill_version = 0;
~~~

Cờ chỉ có ý nghĩa nếu được cập nhật cùng giá trị đích trong một câu lệnh hoặc cùng transaction. Không tách hai thao tác thành hai commit độc lập.

## 7. Cập nhật dữ liệu và checkpoint trong cùng transaction

Nguyên tắc quan trọng nhất để resume chính xác: commit dữ liệu của batch và cursor của batch trong cùng một transaction InnoDB.

Luồng xử lý cho một batch:

1. Đọc checkpoint hiện tại và xác định khóa cuối batch.
2. Bắt đầu transaction.
3. Cập nhật các hàng trong batch.
4. Cập nhật checkpoint đến khóa cuối batch và số liệu tiến độ.
5. Commit transaction.
6. Chỉ sau commit mới báo batch hoàn tất hoặc tăng cursor trong bộ nhớ.

Ví dụ minh họa phần transaction khi ứng dụng đã xác định last_id, batch_end và scanned_count:

~~~sql
START TRANSACTION;

UPDATE sales.orders
SET customer_name_normalized = LOWER(TRIM(customer_name))
WHERE order_id > @last_id
  AND order_id <= @batch_end
  AND customer_name_normalized IS NULL;

SET @changed_rows = ROW_COUNT();

UPDATE ops.backfill_checkpoint
SET last_order_id = @batch_end,
    rows_scanned = rows_scanned + @scanned_count,
    rows_changed = rows_changed + @changed_rows,
    status = 'RUNNING'
WHERE job_name = 'orders-normalize-name-v1';

COMMIT;
~~~

Các biến session @last_id, @batch_end và @scanned_count phải được gán bởi chương trình điều phối trước khi chạy transaction. Trong ứng dụng, ưu tiên prepared statement và bind parameter.

Vì dữ liệu và checkpoint cùng commit:

- Nếu lỗi xảy ra trước commit, cả cập nhật dữ liệu và checkpoint đều rollback.
- Nếu commit thành công nhưng client mất kết nối trước khi nhận phản hồi, lần chạy sau đọc checkpoint đã commit và tiếp tục từ batch kế tiếp.
- Nếu vì một lỗi điều phối mà batch bị chạy lại, điều kiện idempotent giúp không ghi đè các hàng đã hoàn tất.

Không commit checkpoint trước khi commit dữ liệu. Nếu làm vậy, tiến trình có thể đánh dấu một khoảng khóa đã hoàn tất dù dữ liệu chưa được cập nhật.

### 7.1. Lưu ý về ROW_COUNT()

ROW_COUNT() trả về số hàng bị tác động bởi câu lệnh vừa thực thi theo quy tắc của MySQL. Với UPDATE, giá trị thường phản ánh số hàng thực sự thay đổi, không nhất thiết là số hàng đã được quét hoặc số hàng thỏa điều kiện nếu giá trị mới bằng giá trị cũ.

Nếu cần báo cáo cả ba đại lượng, hãy tách rõ:

- rows_scanned: số khóa đã duyệt.
- rows_matched: số hàng thỏa điều kiện nghiệp vụ.
- rows_changed: số hàng có giá trị thực sự thay đổi.

Đừng dùng một bộ đếm duy nhất để suy ra cả tiến độ lẫn số lượng dữ liệu đã biến đổi.

## 8. Chọn cách xác định batch

Có hai cách phổ biến.

### 8.1. Chọn danh sách khóa rồi cập nhật

Ứng dụng truy vấn tối đa N khóa tiếp theo:

~~~sql
SELECT order_id
FROM sales.orders
WHERE order_id > ?
  AND order_id <= ?
ORDER BY order_id
LIMIT 500;
~~~

Lấy khóa cuối cùng làm batch_end, rồi cập nhật phạm vi từ cursor cũ đến khóa đó trong cùng transaction với checkpoint. Cách này dễ triển khai và tận dụng index primary key.

Nếu muốn xử lý chính xác danh sách khóa đã chọn thay vì toàn khoảng, có thể dùng bảng tạm hoặc danh sách bind parameter với IN (...), nhưng cần giới hạn kích thước statement và số placeholder. Khi dùng khoảng khóa, các hàng mới xuất hiện trong khoảng trước câu update có thể cũng được cập nhật; dual-write vẫn cần để bảo vệ các hàng xuất hiện sau câu update.

### 8.2. Chia theo khoảng khóa cố định

Với khóa số có phân bố phù hợp, có thể tạo các khoảng như [1, 10000], [10001, 20000]. Mỗi range là một đơn vị công việc độc lập.

Cách này thuận lợi cho nhiều worker vì có thể phân chia range trước. Tuy nhiên, khoảng khóa không đồng nghĩa số hàng bằng nhau: dữ liệu có thể có nhiều khoảng trống hoặc tập trung ở một số đoạn. Hãy đo thời gian và số hàng thực tế trong từng range.

Với khóa ghép hoặc chuỗi, phân chia range cần tuân theo thứ tự so sánh của cột và collation. Không tự chia bằng phép cộng/trừ trên chuỗi hoặc UUID. Có thể tạo danh sách range từ các khóa thực tế đã sắp xếp hoặc phân công theo tenant.

## 9. Ghi đồng thời từ ứng dụng

Backfill thường chạy trong lúc ứng dụng vẫn đọc và ghi. Nếu ứng dụng tiếp tục chỉ ghi cột cũ trong khi backfill đã đi qua hàng đó, cột mới có thể trở nên lỗi thời ngay sau khi cập nhật.

Ví dụ:

1. Backfill đọc customer_name = 'An' và tính customer_name_normalized = 'an'.
2. Ứng dụng cập nhật customer_name = 'Bình'.
3. Nếu ứng dụng không cập nhật cột mới, giá trị chuẩn hóa vẫn là 'an', không còn khớp dữ liệu nguồn.

Cần triển khai dual-write hoặc cơ chế đồng bộ trước khi bắt đầu backfill:

- Phiên bản ứng dụng mới ghi cả cột cũ và cột mới trong cùng transaction.
- Hoặc dùng trigger được thiết kế và kiểm thử để đồng bộ hai cột.
- Hoặc ghi nhận thay đổi bằng change log/CDC rồi áp dụng vào cột mới.
- Chỉ ngừng ghi cột cũ sau khi mọi ứng dụng đã chuyển sang schema mới và đã đối chiếu dữ liệu.

Một thứ tự triển khai thường dùng:

1. Thêm cột mới ở trạng thái cho phép NULL.
2. Triển khai ứng dụng đọc tương thích và ghi đồng thời cả hai cột.
3. Xác nhận mọi writer đã dùng dual-write.
4. Chạy backfill theo batch.
5. Chạy reconciliation để bắt các hàng bị bỏ sót hoặc thay đổi trong lúc chạy.
6. Chuyển ứng dụng sang đọc cột mới.
7. Theo dõi một khoảng thời gian, sau đó mới ngừng ghi cột cũ.
8. Trong một migration riêng, cân nhắc đặt NOT NULL, bỏ cột cũ hoặc constraint không còn dùng.

Không chạy backfill trước khi có kế hoạch cho writer cũ. Nếu có nhiều phiên bản ứng dụng cùng hoạt động, cần biết chính xác phiên bản nào ghi cột nào.

## 10. Tránh ghi đè dữ liệu mới hơn

Nếu phép chuyển đổi chỉ được tính bằng SQL từ cột nguồn hiện tại, câu UPDATE đọc giá trị nguồn tại thời điểm thực thi và ghi đích trong cùng statement. Điều này thường an toàn hơn việc đọc dữ liệu ra ứng dụng, tính toán bên ngoài rồi ghi lại sau.

Nếu phép chuyển đổi được tính ở ngoài database, hãy dùng optimistic concurrency control. Ví dụ lưu updated_at hoặc version khi đọc hàng, rồi chỉ cập nhật nếu version chưa đổi:

~~~sql
UPDATE sales.orders
SET customer_name_normalized = ?,
    name_backfill_version = 1
WHERE order_id = ?
  AND updated_at = ?
  AND name_backfill_version = 0;
~~~

Nếu câu lệnh cập nhật 0 hàng, dữ liệu nguồn có thể đã thay đổi hoặc hàng đã được xử lý bởi writer khác. Đọc lại hàng và tính lại; không ép ghi giá trị cũ.

updated_at chỉ phù hợp khi được cập nhật tin cậy cho mọi thay đổi liên quan và độ chính xác đủ cho yêu cầu. Một cột version tăng đơn điệu thường rõ ràng hơn khi cần phát hiện cạnh tranh. Với timestamp có độ phân giải thấp hoặc có thể được gán thủ công, không nên coi nó là version duy nhất.

## 11. Transaction size và thời gian giữ khóa

Batch quá lớn có thể:

- Giữ row lock lâu và làm các request ứng dụng chờ.
- Tạo lượng undo/redo lớn.
- Làm tăng thời gian commit và binary log.
- Làm replica apply chậm.
- Tăng nguy cơ transaction rollback tốn thời gian.
- Chiếm buffer pool và I/O làm giảm hiệu năng workload khác.

Batch quá nhỏ lại tạo overhead lớn do nhiều transaction, round trip và cập nhật checkpoint. Cần chọn kích thước dựa trên thời gian thực tế, không chỉ số hàng.

Điểm bắt đầu có thể là vài trăm đến vài nghìn hàng mỗi batch, sau đó điều chỉnh theo độ rộng hàng và tốc độ storage. Mục tiêu thực tế là transaction đủ ngắn để giới hạn lock time và đủ lớn để không lãng phí phần lớn thời gian vào overhead.

Theo dõi latency của ứng dụng, lock wait, deadlock, redo generation, binary log growth và replica lag. Nếu các chỉ số vượt ngưỡng, giảm batch size hoặc tạm dừng.

## 12. Retry khi deadlock, timeout hoặc mất kết nối

Deadlock và lock wait timeout có thể xảy ra khi backfill cạnh tranh với giao dịch trực tuyến. Xử lý theo nguyên tắc:

1. Xác định lỗi có thể retry, ví dụ deadlock hoặc lock wait timeout.
2. Rollback toàn bộ transaction batch.
3. Đợi một khoảng ngắn có backoff và jitter.
4. Đọc lại checkpoint đã commit từ database.
5. Chạy lại batch từ cursor đó.
6. Giới hạn số lần retry và phát cảnh báo khi vượt ngưỡng.

Không tiếp tục từ khóa giữa batch đã rollback. Nếu batch transaction bao gồm update dữ liệu và checkpoint, rollback sẽ đưa cả hai về trạng thái trước batch.

Nếu client mất kết nối ngay sau lệnh COMMIT, không thể suy đoán chỉ từ timeout rằng commit đã thất bại. Hãy kết nối lại, đọc checkpoint trong database rồi quyết định. Đây là lý do checkpoint bền vững quan trọng hơn biến cursor chỉ tồn tại trong bộ nhớ worker.

Không tự động retry mọi lỗi SQL. Lỗi schema, thiếu privilege, dữ liệu không hợp lệ hoặc lỗi logic cần được phân loại và xử lý riêng.

## 13. Nhiều worker và phân chia công việc

Có thể chạy nhiều worker để tăng tốc khi các range độc lập và server còn đủ tài nguyên. Mỗi worker cần một phạm vi không chồng lấn hoặc một cơ chế claim công việc rõ ràng.

Ví dụ chia range:

| Worker | Phạm vi order_id |
|---|---|
| A | 1 đến 2.000.000 |
| B | 2.000.001 đến 4.000.000 |
| C | 4.000.001 đến 6.000.000 |
| D | 6.000.001 đến high-water mark |

Mỗi worker lưu checkpoint riêng theo job_name và worker_id, hoặc ghi trạng thái vào bảng quản lý range. Không để nhiều worker cùng cập nhật một cursor toàn cục mà không có khóa điều phối; một worker có thể ghi đè tiến độ của worker khác.

Có thể dùng bảng queue/range với trạng thái PENDING, RUNNING, DONE, thời gian lease và worker owner. Khi worker chết, lease hết hạn để range được claim lại. Việc claim range và gia hạn lease cần được thiết kế bằng transaction, tránh hai worker cùng nhận một range.

### 13.1. Cẩn trọng với SKIP LOCKED

SELECT ... FOR UPDATE SKIP LOCKED hữu ích cho hàng đợi nhiều worker, nhưng không tự động phù hợp với cursor đơn điệu. Nếu worker bỏ qua một hàng đang bị khóa rồi checkpoint vượt qua khóa đó, hàng bị bỏ qua có thể không được xử lý lại.

Nếu dùng SKIP LOCKED, phải lưu trạng thái từng hàng hoặc từng range và có cơ chế retry những hàng bị bỏ qua. Với backfill tuần tự theo keyset, thường đơn giản hơn khi không bỏ qua khóa: đợi khóa trong giới hạn timeout, rollback batch nếu cần và retry từ checkpoint.

### 13.2. Không tăng worker khi bottleneck là nguồn chung

Mọi worker vẫn cạnh tranh CPU, I/O, buffer pool, redo log, binary log và replica apply. Nếu nguồn đang bão hòa, thêm worker làm giảm hiệu năng tổng thể. Bắt đầu một worker, đo, sau đó tăng dần; chọn số worker theo throughput hữu ích và ảnh hưởng đến workload trực tuyến.

## 14. Điều tiết tải và giám sát

Backfill là workload nền nhưng vẫn tạo thay đổi dữ liệu thật. Hãy đặt ngưỡng để job tự giảm tốc hoặc tạm dừng khi hệ thống chịu tải cao.

Các tín hiệu cần theo dõi:

- Thời gian trung bình và p95 của transaction ứng dụng.
- Lock wait, deadlock và timeout.
- CPU, memory, disk IOPS và latency storage.
- InnoDB redo/undo pressure và dirty pages.
- Tốc độ tăng binary log.
- Replica lag và trạng thái applier.
- Số batch hoàn tất, hàng quét và hàng thay đổi.
- Số lần retry và thời gian chờ giữa các batch.

Có thể thêm khoảng nghỉ giữa batch:

~~~text
while còn range cần xử lý:
    đọc checkpoint đã commit
    xác định batch tiếp theo
    chạy update + checkpoint trong một transaction
    commit
    ghi metric
    nếu tải vượt ngưỡng:
        tạm dừng hoặc giảm batch
    nếu không:
        chờ một khoảng ngắn rồi tiếp tục
~~~

Đây là pseudocode mô tả luồng điều phối; phần truy vấn và retry cần được triển khai bằng client hoặc worker có kiểm soát transaction. Không chạy vòng lặp không giới hạn trong một transaction dài.

Nếu replica lag tăng liên tục, giảm tốc độ hoặc tạm dừng backfill để replica bắt kịp. Nếu binary log tăng nhanh, xác nhận dung lượng lưu trữ và retention đủ cho replica/PITR trước khi tiếp tục. Không purge log để giải phóng đĩa nếu replica hoặc quy trình phục hồi còn cần các file đó.

## 15. Reconciliation và xác nhận hoàn tất

Cursor đạt high-water mark chỉ chứng minh tiến trình đã quét qua phạm vi khóa theo quy tắc của nó. Nó không chứng minh mọi hàng đều có giá trị đúng. Có thể còn hàng được thêm trễ, hàng bị bỏ qua, lỗi chuyển đổi hoặc writer cũ chưa dual-write.

Chạy các truy vấn đối chiếu sau khi backfill:

~~~sql
-- Số hàng vẫn chưa được đánh dấu hoàn tất
SELECT COUNT(*) AS remaining
FROM sales.orders
WHERE order_id <= :high_watermark
  AND name_backfill_version = 0;

-- Kiểm tra một số hàng có giá trị không khớp
SELECT order_id, customer_name, customer_name_normalized
FROM sales.orders
WHERE order_id <= :high_watermark
  AND NOT (
    customer_name_normalized <=> LOWER(TRIM(customer_name))
  )
LIMIT 100;
~~~

Toán tử <=> là so sánh null-safe của MySQL. Nó giúp phát hiện cả trường hợp một bên NULL và bên kia không NULL. Nếu phép chuyển đổi có quy tắc nghiệp vụ khác, thay biểu thức so sánh bằng đúng quy tắc đó.

Với bảng lớn, truy vấn đối chiếu toàn bảng có thể tạo tải đáng kể. Có thể chia theo khoảng khóa và thực hiện từng batch, hoặc dùng aggregate/checksum theo lô. Đối chiếu trên cùng snapshot hoặc sau khi writer đã dual-write là cần thiết để tránh kết quả thay đổi liên tục trong lúc kiểm tra.

Sau khi tất cả range đã hoàn tất và reconciliation đạt yêu cầu, cập nhật trạng thái job:

~~~sql
UPDATE ops.backfill_checkpoint
SET status = 'DONE'
WHERE job_name = 'orders-normalize-name-v1'
  AND last_order_id >= high_watermark;
~~~

Điều kiện hoàn tất cần được kiểm tra cùng kết quả reconciliation và trạng thái writer. Không đặt DONE chỉ vì cursor lớn hơn high-water mark nếu còn hàng chưa được chuyển.

## 16. Ví dụ luồng backfill hoàn chỉnh

Giả sử bảng sales.orders có order_id là primary key, cần điền cột chuẩn hóa. Ứng dụng mới đã dual-write customer_name và customer_name_normalized.

Một worker có thể thực hiện quy trình sau:

~~~text
1. Đọc job checkpoint:
   last_order_id, high_watermark, status.

2. Nếu status = DONE:
   dừng.

3. Lấy batch:
   SELECT order_id
   FROM sales.orders
   WHERE order_id > last_order_id
     AND order_id <= high_watermark
   ORDER BY order_id
   LIMIT 500;

4. Nếu không có hàng:
   chạy reconciliation cho phạm vi;
   chỉ đánh dấu DONE nếu không còn hàng cần backfill.

5. Lấy batch_end = order_id cuối cùng được quét.

6. START TRANSACTION.

7. UPDATE các hàng trong khoảng:
   SET customer_name_normalized = LOWER(TRIM(customer_name))
   WHERE order_id > last_order_id
     AND order_id <= batch_end
     AND name_backfill_version = 0;

8. Lưu số hàng thay đổi ngay sau UPDATE.

9. UPDATE checkpoint:
   last_order_id = batch_end,
   cộng rows_scanned và rows_changed.

10. COMMIT.

11. Nếu transaction lỗi:
    ROLLBACK, đọc lại checkpoint, retry batch có giới hạn.

12. Ghi metric, điều tiết tốc độ và lặp lại.
~~~

Trong code thực tế, các bước đọc batch, update và checkpoint phải bảo đảm cursor không bị thay đổi bởi worker khác. Với một worker, có thể khóa dòng checkpoint bằng SELECT ... FOR UPDATE trong transaction. Với nhiều worker, dùng checkpoint/range riêng hoặc cơ chế claim range.

Ví dụ khóa dòng checkpoint:

~~~sql
START TRANSACTION;

SELECT last_order_id, high_watermark, status
FROM ops.backfill_checkpoint
WHERE job_name = 'orders-normalize-name-v1'
FOR UPDATE;
~~~

Sau khi lấy và kiểm tra trạng thái, worker xác định batch, cập nhật dữ liệu và checkpoint rồi commit. Không giữ khóa checkpoint trong lúc chờ lâu hoặc xử lý dữ liệu ngoài database; hãy giới hạn transaction và tránh để worker khác bị chặn không cần thiết.

## 17. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Batch chạy chậm dần | Dùng OFFSET lớn, thiếu index hoặc batch quá rộng | Chuyển sang keyset pagination, kiểm tra EXPLAIN và thu nhỏ phạm vi. |
| Có hàng bị bỏ sót | Cursor không ổn định, hàng mới xuất hiện sau cursor hoặc dùng SKIP LOCKED không có reconciliation | Dùng khóa duy nhất, dual-write/change capture và lượt đối chiếu cuối. |
| Dữ liệu mới bị ghi đè | Backfill tính giá trị cũ bên ngoài database rồi cập nhật không kiểm tra version | Tính từ cột nguồn hiện tại hoặc dùng optimistic version predicate. |
| Checkpoint đi trước dữ liệu | Cập nhật checkpoint ở transaction khác | Commit update và checkpoint trong cùng transaction InnoDB. |
| Job lặp lại hàng đã xử lý | Checkpoint không bền vững hoặc batch không idempotent | Lưu cursor trong database và dùng điều kiện cập nhật có thể lặp lại an toàn. |
| Job đánh dấu DONE nhưng còn NULL | Dùng cursor làm điều kiện hoàn tất duy nhất | Chạy reconciliation theo điều kiện dữ liệu thực tế. |
| Deadlock hoặc lock timeout | Batch cạnh tranh với transaction ứng dụng hoặc worker khác | Rollback toàn batch, backoff, giảm batch và phân chia range. |
| Replica lag tăng | Backfill tạo nhiều row event và tải apply | Giảm tốc độ, giảm worker, theo dõi binlog và replica. |
| Nhiều worker ghi đè checkpoint | Dùng chung cursor không có điều phối | Tạo checkpoint riêng theo worker/range hoặc khóa claim range. |
| Retry gây side effect lặp | Retry cả nghiệp vụ chứa thao tác ngoài database | Dùng idempotency key và transactional outbox cho side effect. |

## 18. Bài tập thực hành

### Bài 1: Backfill một cột mới

Tạo bảng sales.orders có ít nhất 100.000 hàng. Thêm customer_name_normalized và viết worker cập nhật theo order_id từng batch 500 hàng. So sánh thời gian với một câu UPDATE toàn bảng và quan sát lock wait, redo và replica lag.

### Bài 2: Dừng và tiếp tục

Dừng worker sau một số batch đã commit. Khởi động lại worker từ checkpoint trong database. Xác nhận không có khoảng khóa bị bỏ qua và các batch đã hoàn thành không bị ghi sai.

### Bài 3: Mô phỏng ghi đồng thời

Trong lúc backfill, dùng session khác thay đổi customer_name. Thử hai thiết kế: chỉ cập nhật cột cũ và dual-write cả hai cột. Quan sát trường hợp nào khiến cột chuẩn hóa bị lỗi thời và giải thích cách reconciliation phát hiện.

### Bài 4: Khóa ghép

Tạo bảng có primary key (tenant_id, order_id). Viết keyset pagination theo cả hai cột, lưu cursor ghép và chạy qua nhiều tenant. Xác nhận thứ tự không lặp hoặc bỏ sót hàng.

### Bài 5: Nhiều worker và retry

Chia bảng thành bốn range không chồng lấn. Chạy worker độc lập, tạo deadlock hoặc lock timeout trong môi trường thử nghiệm, sau đó kiểm tra worker rollback, đọc checkpoint và tiếp tục đúng range.

## 19. Checklist trước khi kết thúc backfill

- [ ] Bảng có primary key hoặc unique key ổn định để xác định thứ tự.
- [ ] Cursor chứa đủ thành phần nếu dùng khóa ghép.
- [ ] Truy vấn batch dùng keyset pagination và có index phù hợp.
- [ ] High-water mark được ghi nhận, cùng kế hoạch xử lý hàng phát sinh.
- [ ] Ứng dụng đã dual-write hoặc có change capture trước khi backfill.
- [ ] Điều kiện cập nhật idempotent và không ghi đè dữ liệu mới hơn.
- [ ] Checkpoint được lưu bền vững trong database.
- [ ] Update dữ liệu và checkpoint cùng nằm trong một transaction.
- [ ] Batch size, worker count và retry policy có giới hạn.
- [ ] Có cơ chế pause/resume và theo dõi lỗi.
- [ ] Đã giám sát lock wait, deadlock, redo, binlog và replica lag.
- [ ] Đã chạy reconciliation theo đúng quy tắc chuyển đổi.
- [ ] Chỉ đánh dấu DONE sau khi xác nhận dữ liệu thực sự hoàn tất.
- [ ] Chỉ ngừng dual-write hoặc xóa cột cũ trong giai đoạn contract riêng.

Backfill đáng tin cậy dựa trên khóa ổn định, batch có thể lặp lại và checkpoint commit cùng dữ liệu. Khi ứng dụng vẫn ghi trong lúc chuyển đổi, dual-write hoặc change capture bảo vệ các thay đổi mới, còn reconciliation phát hiện những hàng bị bỏ sót. Hãy bắt đầu với batch nhỏ, đo ảnh hưởng lên workload và replica, rồi tăng tốc có kiểm soát; chỉ kết thúc migration khi dữ liệu đã được đối chiếu và ứng dụng đã chuyển hoàn toàn sang schema mới.

