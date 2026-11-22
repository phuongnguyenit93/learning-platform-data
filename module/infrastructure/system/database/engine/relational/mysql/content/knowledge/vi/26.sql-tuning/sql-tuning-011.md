# Batch DML, INSERT nhiều dòng và giới hạn kích thước gói

Khi một ứng dụng cần ghi hàng nghìn hoặc hàng triệu dòng, gửi một câu SQL cho từng dòng thường tạo nhiều lượt trao đổi mạng và nhiều lần xử lý statement. **Batch DML** gom nhiều thao tác dữ liệu thành các nhóm có kích thước phù hợp. Với MySQL, có thể dùng `INSERT` nhiều dòng, `INSERT ... SELECT`, transaction theo lô hoặc API batch của client. Tuy nhiên, lô quá lớn có thể vượt giới hạn packet, giữ khóa lâu, tạo nhiều undo/redo và làm tăng thời gian rollback hoặc replication lag.

Bài học thuộc phần **Tối ưu SQL** của MySQL. Bạn sẽ chọn cách ghi theo lô, thiết kế `INSERT` nhiều dòng, xử lý duplicate key, chia transaction, ước lượng kích thước payload, kiểm tra `max_allowed_packet` ở cả client và server, và xây dựng quy trình retry có thể tiếp tục an toàn sau lỗi.

## 1. Vì sao nên gom DML theo lô?

Giả sử ứng dụng cần chèn 10.000 bản ghi. Nếu gửi 10.000 câu `INSERT` riêng biệt, mỗi câu có thể phát sinh chi phí gửi statement, parse, lập kế hoạch, thực hiện và phản hồi. Nếu gom thành các câu `INSERT` nhiều dòng hoặc batch prepared statement, số lượt trao đổi giảm xuống.

Batch DML có thể cải thiện:

- **Network round trips:** giảm số lần client gửi lệnh và chờ phản hồi.
- **Statement overhead:** giảm số lần parse và xử lý câu lệnh khi dùng multi-row INSERT hoặc prepared statement phù hợp.
- **Transaction overhead:** nhiều thay đổi trong một transaction có thể chia sẻ chi phí commit và flush log.
- **Throughput:** tăng số dòng ghi được trong một đơn vị thời gian khi batch size phù hợp với máy chủ và workload.

Gom lô cũng làm tăng phạm vi ảnh hưởng của mỗi lần lỗi. Một batch lớn có thể giữ nhiều row lock, tạo nhiều undo record, chiếm bộ nhớ và khiến rollback kéo dài. Vì vậy, mục tiêu không phải tạo batch lớn nhất có thể, mà là tìm kích thước cân bằng giữa throughput, latency, khả năng khôi phục và giới hạn tài nguyên.

## 2. INSERT nhiều dòng bằng một câu lệnh

Cú pháp cơ bản cho phép chèn nhiều bộ giá trị trong cùng một câu:

```sql
INSERT INTO import_orders (
    order_id,
    customer_id,
    status,
    total_amount
)
VALUES
    (1001, 501, 'NEW', 125.00),
    (1002, 502, 'PAID', 89.50),
    (1003, 501, 'NEW', 240.00);
```

MySQL xử lý ba bộ giá trị trong một statement. Luôn chỉ rõ danh sách cột để câu lệnh không phụ thuộc thứ tự cột vật lý của bảng và dễ bảo trì khi schema thay đổi.

Ví dụ bảng đích:

```sql
CREATE TABLE import_orders (
    order_id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (order_id),
    KEY ix_customer (customer_id)
) ENGINE = InnoDB;
```

Nếu bỏ qua `created_at`, MySQL dùng giá trị mặc định. Các bộ giá trị phải cung cấp số cột và kiểu dữ liệu tương thích với danh sách cột.

### INSERT nhiều dòng so với nhiều câu INSERT

Hai cách sau có thể tạo cùng dữ liệu nhưng khác số statement:

```sql
-- Nhiều statement
INSERT INTO import_orders (order_id, customer_id, status, total_amount)
VALUES (2001, 501, 'NEW', 10.00);

INSERT INTO import_orders (order_id, customer_id, status, total_amount)
VALUES (2002, 502, 'NEW', 20.00);

-- Một statement nhiều dòng
INSERT INTO import_orders (order_id, customer_id, status, total_amount)
VALUES
    (2001, 501, 'NEW', 10.00),
    (2002, 502, 'NEW', 20.00);
```

Multi-row INSERT thường giảm round trip và chi phí xử lý statement. Với InnoDB, một câu lệnh nhiều dòng là một statement; nếu statement lỗi do duplicate key hoặc constraint, hành vi của statement phụ thuộc loại lỗi và engine. Với InnoDB, lỗi statement thông thường làm statement thất bại và các thay đổi của statement được rollback, trong khi transaction có thể vẫn mở tùy loại lỗi.

Khi `autocommit=1`, mỗi statement thành công thường được commit riêng. Nếu dùng nhiều câu INSERT trong một transaction tường minh, các statement có thể được commit cùng nhau bằng một `COMMIT`.

## 3. Các cách nạp dữ liệu theo lô khác

### INSERT ... SELECT

Khi dữ liệu đã nằm trong MySQL, có thể chèn trực tiếp kết quả truy vấn vào bảng đích:

```sql
INSERT INTO archived_orders (
    order_id,
    customer_id,
    status,
    total_amount
)
SELECT
    order_id,
    customer_id,
    status,
    total_amount
FROM orders
WHERE created_at < '2025-01-01';
```

`INSERT ... SELECT` tránh phải chuyển dữ liệu qua client rồi gửi lại server. Tuy nhiên, truy vấn nguồn có thể quét nhiều dòng, giữ tài nguyên lâu và tạo một transaction lớn. Hãy kiểm tra `EXPLAIN` cho phần SELECT, index lọc và số dòng dự kiến.

### INSERT ... SELECT theo từng khoảng

Nếu cần chia nhỏ quá trình chuyển dữ liệu, dùng khóa tăng dần hoặc khoảng thời gian làm checkpoint:

```sql
INSERT INTO archived_orders (
    order_id,
    customer_id,
    status,
    total_amount
)
SELECT
    order_id,
    customer_id,
    status,
    total_amount
FROM orders
WHERE order_id > 100000
  AND order_id <= 110000;
```

Sau khi xác minh số dòng và commit, lưu mốc cuối đã xử lý. Batch tiếp theo bắt đầu sau mốc đó. Dùng khoảng khóa rõ ràng giúp quy trình có thể tiếp tục sau khi job bị dừng.

### LOAD DATA cho tệp lớn

Khi nguồn là tệp CSV hoặc dữ liệu dạng dòng, `LOAD DATA [LOCAL] INFILE` thường phù hợp hơn việc tạo một câu INSERT khổng lồ:

```sql
LOAD DATA LOCAL INFILE '/data/orders.csv'
INTO TABLE import_orders
FIELDS TERMINATED BY ','
OPTIONALLY ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 LINES
(order_id, customer_id, status, total_amount);
```

`LOCAL` đọc tệp từ máy client; không có `LOCAL` thì tệp được đọc từ máy chủ và phải đáp ứng cấu hình/quyền truy cập file của server. Hành vi bảo mật và khả năng bật `LOCAL` phụ thuộc cấu hình client/server. Với dữ liệu rất lớn, cần kiểm tra quyền, encoding, dấu phân cách, newline, dữ liệu lỗi và kế hoạch rollback.

`LOAD DATA` không loại bỏ mọi giới hạn tài nguyên, nhưng tránh phải gửi một statement SQL chứa toàn bộ dữ liệu. Hãy benchmark nó với multi-row INSERT trên kích thước tệp và yêu cầu kiểm tra dữ liệu thực tế.

## 4. Batch transaction: chọn ranh giới commit

Có hai quyết định độc lập:

1. **Kích thước statement:** số dòng hoặc số byte trong một câu INSERT/UPDATE/DELETE.
2. **Kích thước transaction:** tổng số statement hoặc thay đổi được commit cùng nhau.

Một transaction có thể chứa nhiều statement nhỏ. Ngược lại, một multi-row INSERT có thể là một statement duy nhất và cũng là một transaction riêng khi autocommit bật.

### Một transaction cho toàn bộ dữ liệu

```sql
START TRANSACTION;

INSERT INTO import_orders (order_id, customer_id, status, total_amount)
VALUES
    (3001, 501, 'NEW', 10.00),
    (3002, 502, 'NEW', 20.00),
    (3003, 503, 'NEW', 30.00);

INSERT INTO import_orders (order_id, customer_id, status, total_amount)
VALUES
    (3004, 504, 'NEW', 40.00),
    (3005, 505, 'NEW', 50.00);

COMMIT;
```

Nếu transaction thất bại trước commit, có thể `ROLLBACK` toàn bộ thay đổi transactional trong InnoDB. Cách này phù hợp khi nghiệp vụ yêu cầu tất cả lô cùng thành công hoặc cùng thất bại và quy mô transaction vẫn nằm trong giới hạn vận hành.

### Commit theo từng batch

Với dữ liệu rất lớn, có thể chia thành nhiều transaction nhỏ:

```sql
START TRANSACTION;

INSERT INTO import_orders (order_id, customer_id, status, total_amount)
VALUES
    (4001, 501, 'NEW', 10.00),
    (4002, 502, 'NEW', 20.00);

COMMIT;

START TRANSACTION;

INSERT INTO import_orders (order_id, customer_id, status, total_amount)
VALUES
    (4003, 503, 'NEW', 30.00),
    (4004, 504, 'NEW', 40.00);

COMMIT;
```

Commit từng batch giới hạn thời gian giữ lock và lượng undo/redo gắn với một transaction. Đổi lại, nếu batch thứ ba lỗi thì hai batch trước vẫn đã commit. Job cần có checkpoint, khả năng retry và cơ chế nhận diện dữ liệu đã nạp.

Không nên mở một transaction rồi giữ kết nối chờ đọc tệp, gọi API hoặc chờ người dùng. Hãy chuẩn bị dữ liệu ngoài transaction nếu có thể, sau đó mở transaction trong khoảng thời gian cần ghi.

## 5. Batch UPDATE và DELETE

Batch DML không chỉ dành cho INSERT. Khi cần cập nhật hoặc xóa số lượng lớn dòng, có thể chia theo khóa hoặc khoảng thời gian.

### UPDATE theo khoảng khóa

```sql
UPDATE orders
SET status = 'EXPIRED'
WHERE order_id > 100000
  AND order_id <= 110000
  AND status = 'PENDING';
```

Sau khi kiểm tra số dòng bị ảnh hưởng, commit và lưu checkpoint `110000`. Batch tiếp theo xử lý khoảng kế tiếp. Cột chia lô nên có index để tránh mỗi batch quét lại toàn bảng.

### DELETE theo từng nhóm

Với single-table DELETE, MySQL hỗ trợ `ORDER BY` và `LIMIT`:

```sql
DELETE FROM audit_events
WHERE created_at < '2024-01-01'
ORDER BY created_at, event_id
LIMIT 1000;
```

Có thể lặp lại theo từng batch cho đến khi không còn dòng thỏa điều kiện. Dùng thêm khóa phụ trong `ORDER BY` để thứ tự ổn định khi nhiều dòng có cùng thời gian. Cần kiểm tra số dòng bị xóa và thời gian từng batch.

### Dùng CASE để cập nhật nhiều giá trị khác nhau

Khi mỗi khóa cần một giá trị mới khác nhau, một câu UPDATE có thể dùng CASE:

```sql
UPDATE inventory
SET quantity = CASE product_id
    WHEN 101 THEN 25
    WHEN 102 THEN 40
    WHEN 103 THEN 12
    ELSE quantity
END
WHERE product_id IN (101, 102, 103);
```

Đối với danh sách rất dài, câu lệnh CASE cũng tăng kích thước statement. Cần chia nhóm và đo kích thước packet như multi-row INSERT.

## 6. Chọn kích thước batch

Không có một batch size tối ưu cho mọi bảng. Kích thước phù hợp phụ thuộc vào:

- Kích thước trung bình của mỗi dòng và payload lớn như `TEXT`, `BLOB`, JSON.
- Số index và constraint cần cập nhật.
- Trigger, generated column và công việc phụ phát sinh khi ghi.
- Tốc độ I/O, CPU, redo log và buffer pool.
- Mức độ đồng thời với truy vấn/transaction khác.
- Giới hạn packet ở server, client và driver.
- Thời gian rollback có thể chấp nhận và mục tiêu replication lag.

Hãy đo cả số dòng lẫn số byte. Một batch 1.000 dòng chỉ chứa vài số nguyên nhỏ khác xa batch 1.000 dòng có JSON vài trăm KB hoặc BLOB nhiều MB.

### Quy trình tìm batch size

1. Bắt đầu với một batch nhỏ, ví dụ 100 hoặc 500 dòng trong môi trường thử nghiệm.
2. Đo số byte của payload, thời gian thực thi, thời gian commit và số dòng bị ảnh hưởng.
3. Tăng batch theo từng bước có kiểm soát, ví dụ gấp đôi, cho đến khi throughput không tăng đáng kể hoặc xuất hiện dấu hiệu bão hòa.
4. Theo dõi p95/p99 latency của workload khác, lock wait, redo log pressure, disk I/O và replication lag.
5. Chọn kích thước thấp hơn điểm bắt đầu gây biến động lớn để có khoảng an toàn.
6. Lặp lại phép đo khi kích thước dòng, tỷ lệ BLOB hoặc concurrency thay đổi.

Không lấy batch size tối đa có thể gửi qua packet làm batch size vận hành mặc định. Giới hạn packet chỉ là một ràng buộc kỹ thuật; transaction và hệ thống có thể quá tải từ trước khi đạt giới hạn đó.

## 7. MySQL packet và max_allowed_packet

Client và server trao đổi lệnh cùng kết quả qua giao thức MySQL. Một **packet** logic có thể chứa câu lệnh SQL, một phần dữ liệu hoặc một row kết quả. `max_allowed_packet` đặt giới hạn kích thước packet hoặc chuỗi trung gian mà MySQL xử lý.

Nếu client gửi một statement hoặc payload vượt giới hạn của server/client, MySQL có thể trả lỗi `ER_NET_PACKET_TOO_LARGE` (thường hiển thị mã lỗi 1153) và đóng kết nối. Ứng dụng cần xử lý tình huống kết nối bị đóng, không giả định chỉ statement đó thất bại nhưng connection vẫn dùng được.

Kiểm tra giới hạn trên server:

```sql
SHOW GLOBAL VARIABLES LIKE 'max_allowed_packet';
SHOW SESSION VARIABLES LIKE 'max_allowed_packet';
```

Giá trị hiển thị tính bằng byte. `max_allowed_packet` là giới hạn ở phía server; client library hoặc chương trình dòng lệnh cũng có thể có giới hạn riêng. Payload phải nằm trong giới hạn của cả hai đầu.

### Thay đổi giới hạn phía server

Trong MySQL hỗ trợ thay đổi động, quản trị viên có thể điều chỉnh giá trị GLOBAL:

```sql
SET GLOBAL max_allowed_packet = 67108864;
```

Ví dụ đặt 64 MiB (`64 × 1024 × 1024` byte). Quyền cần thiết phụ thuộc phiên bản và cấu hình quyền quản trị. Thay đổi GLOBAL không nhất thiết cập nhật giá trị đã được session hiện tại đọc trước đó; hãy kiểm tra lại bằng kết nối mới và xác nhận hành vi theo phiên bản MySQL đang chạy.

Để duy trì sau restart, cấu hình trong file cấu hình máy chủ dưới nhóm `[mysqld]`:

```ini
[mysqld]
max_allowed_packet=64M
```

Không tăng giới hạn lên mức tối đa một cách mặc định. Packet lớn tiêu thụ bộ nhớ theo kết nối và có thể làm tăng rủi ro khi nhiều client đồng thời gửi payload lớn.

### Giới hạn phía client

MySQL command-line client có tùy chọn riêng:

```bash
mysql --max-allowed-packet=64M -u app_user -p app_db
```

Với ứng dụng, kiểm tra cấu hình driver hoặc connector đang sử dụng. Một số thư viện có tham số packet riêng; không phải mọi client đều tự động lấy giá trị từ server. Nếu server chấp nhận 64 MiB nhưng client chỉ cho phép 16 MiB, payload lớn hơn giới hạn client vẫn có thể thất bại trước khi đến server.

## 8. max_allowed_packet khác net_buffer_length như thế nào?

`net_buffer_length` là kích thước ban đầu của buffer giao tiếp; buffer có thể tăng lên khi cần nhưng không vượt giới hạn packet. Nó không phải giới hạn tối đa thay thế cho `max_allowed_packet`.

Kiểm tra:

```sql
SHOW VARIABLES LIKE 'net_buffer_length';
SHOW VARIABLES LIKE 'max_allowed_packet';
```

Không cần tăng `net_buffer_length` chỉ vì batch lớn. Trước tiên hãy xác định packet thực tế, giới hạn server/client và nhu cầu bộ nhớ. Cũng cần phân biệt packet size với transaction size: một transaction có thể gửi nhiều packet nhỏ trong suốt thời gian thực thi nhưng vẫn tạo lượng undo/redo lớn.

## 9. Ước lượng kích thước payload và xử lý dữ liệu lớn

Kích thước câu SQL nhiều dòng phụ thuộc số dòng, kiểu dữ liệu, độ dài chuỗi, encoding và cách client serialize tham số. Khi dùng literal SQL, ký tự quote và escape làm câu lệnh dài hơn dữ liệu gốc. Với prepared statement, tham số có thể được gửi theo binary protocol, nhưng payload vẫn phải nằm trong giới hạn client/server.

Một cách ước lượng đơn giản:

\[
\text{Payload batch} \approx
\text{overhead statement} +
\sum_{i=1}^{N}\text{encoded row}_i
\]

Đây là ước lượng, không phải công thức tính chính xác byte của packet. Hãy đo kích thước serialized payload từ client hoặc log an toàn trong môi trường thử nghiệm. Không log giá trị nhạy cảm chỉ để đo kích thước.

Với BLOB hoặc JSON lớn:

- Giới hạn số dòng mỗi batch theo tổng byte, không chỉ theo số dòng.
- Cân nhắc gửi từng payload lớn riêng hoặc dùng cơ chế streaming/LOAD DATA phù hợp.
- Tránh nhân bản payload lớn trong nhiều buffer của ứng dụng.
- Đảm bảo timeout của client, proxy và server đủ cho thời gian truyền dữ liệu.
- Không tăng packet limit nếu nguyên nhân thực sự là thiết kế batch không giới hạn.

## 10. Duplicate key và tính idempotent khi nạp lại

Một job batch có thể bị retry sau timeout hoặc mất kết nối. Nếu batch đã commit nhưng client không nhận được phản hồi, gửi lại có thể tạo duplicate key. Cần chọn chính sách rõ ràng.

### INSERT thông thường

```sql
INSERT INTO import_orders (order_id, customer_id, status, total_amount)
VALUES
    (5001, 501, 'NEW', 10.00),
    (5002, 502, 'NEW', 20.00);
```

Nếu primary key đã tồn tại, statement có thể thất bại với duplicate key. Không nên retry vô hạn cùng payload mà không xác minh trạng thái.

### INSERT IGNORE

```sql
INSERT IGNORE INTO import_orders
    (order_id, customer_id, status, total_amount)
VALUES
    (5001, 501, 'NEW', 10.00),
    (5002, 502, 'NEW', 20.00);
```

`IGNORE` có thể bỏ qua một số lỗi duplicate và chuyển một số lỗi dữ liệu thành warning hoặc giá trị điều chỉnh tùy trường hợp. Nó có thể khiến một phần dòng không được nạp như mong đợi mà statement vẫn thành công. Hãy kiểm tra warnings và số dòng bị ảnh hưởng; không dùng `IGNORE` như cách tổng quát để che mọi lỗi dữ liệu.

### INSERT ... ON DUPLICATE KEY UPDATE

Nếu muốn cập nhật dòng đã tồn tại:

```sql
INSERT INTO import_orders
    (order_id, customer_id, status, total_amount)
VALUES
    (5001, 501, 'PAID', 10.00),
    (5002, 502, 'PAID', 20.00) AS incoming
ON DUPLICATE KEY UPDATE
    status = incoming.status,
    total_amount = incoming.total_amount;
```

Alias của row mới trong cú pháp trên được hỗ trợ ở các phiên bản MySQL 8.0 mới; kiểm tra cú pháp theo phiên bản đang dùng. Trong các phiên bản cũ hơn, tài liệu có thể dùng `VALUES(column)`, nhưng hàm `VALUES()` trong nhánh `ON DUPLICATE KEY UPDATE` đã bị deprecated từ MySQL 8.0.20.

`ON DUPLICATE KEY UPDATE` có thể cập nhật khi xung đột với bất kỳ unique key nào. Nếu bảng có nhiều unique key, cần hiểu rõ key nào có thể gây xung đột và liệu dòng được cập nhật có đúng thực thể nghiệp vụ hay không. Upsert không tự động làm thao tác trở nên idempotent nếu phần UPDATE cộng dồn hoặc tạo tác dụng phụ.

## 11. Batch checkpoint và retry an toàn

Với job xử lý dữ liệu lớn, hãy lưu tiến độ theo một khóa ổn định. Ví dụ, mỗi batch xử lý khoảng `order_id` liên tiếp:

```sql
CREATE TABLE import_job_checkpoint (
    job_name VARCHAR(100) PRIMARY KEY,
    last_order_id BIGINT NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP
) ENGINE = InnoDB;
```

Quy trình của ứng dụng:

1. Đọc `last_order_id` đã commit gần nhất.
2. Chọn một khoảng khóa kế tiếp có giới hạn số dòng.
3. Trong cùng transaction, ghi dữ liệu đích và cập nhật checkpoint.
4. Commit cả dữ liệu và checkpoint cùng nhau.
5. Nếu kết nối lỗi, đọc lại checkpoint bằng kết nối mới rồi tiếp tục từ mốc đã commit.

Nếu checkpoint được cập nhật ngoài transaction chứa dữ liệu, có thể xảy ra hai trạng thái sai: checkpoint đi trước dữ liệu (bỏ sót dòng khi resume) hoặc dữ liệu đã commit nhưng checkpoint chưa cập nhật (nạp lặp). Đặt chúng trong cùng transaction InnoDB giúp trạng thái tiến độ nhất quán.

Nếu nguồn không có khóa tăng dần, dùng khóa nghiệp vụ duy nhất hoặc bảng staging có trạng thái xử lý. Tránh dùng `OFFSET` lớn để chia batch vì các trang sau có thể phải quét và bỏ qua nhiều dòng; dùng keyset/range pagination trên index ổn định thường hiệu quả hơn.

## 12. Lỗi thường gặp khi batch quá lớn

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `ER_NET_PACKET_TOO_LARGE` / connection closed | Packet vượt giới hạn server hoặc client. | Đo payload, giảm batch hoặc điều chỉnh giới hạn có kiểm soát ở cả hai đầu. |
| Duplicate entry | Retry batch đã commit hoặc khóa nguồn trùng. | Tra cứu checkpoint, dùng khóa idempotency và xác định chính sách upsert. |
| Lock wait timeout | Batch giữ khóa lâu hoặc xung đột với workload khác. | Giảm transaction size, thêm index lọc và điều chỉnh lịch chạy. |
| Deadlock | Nhiều transaction cập nhật cùng tập dòng theo thứ tự khác nhau. | Chuẩn hóa thứ tự xử lý khóa, giữ transaction ngắn và retry transaction bị chọn rollback. |
| Rollback kéo dài | Một transaction thay đổi quá nhiều dòng. | Chia batch nhỏ hơn và thiết kế checkpoint/resume. |
| Replication lag | Batch tạo lượng binlog lớn hoặc replica xử lý chậm. | Giảm batch, theo dõi lag và cân nhắc lịch nạp. |
| Throughput không tăng khi tăng batch | Bottleneck chuyển sang I/O, index maintenance, redo hoặc lock. | Đo CPU/I/O, redo, page flush, concurrency và thời gian commit. |
| Bộ nhớ client tăng mạnh | Tạo toàn bộ payload trong RAM trước khi gửi. | Stream dữ liệu, giới hạn buffer và chia batch theo byte. |

Với InnoDB, deadlock khiến một transaction được chọn làm nạn nhân và rollback; ứng dụng nên retry toàn bộ transaction theo chính sách có giới hạn và backoff. Không retry riêng statement giữa một transaction đã bị rollback mà không dựng lại trạng thái nghiệp vụ.

## 13. Đo hiệu năng batch

Ghi lại ít nhất các chỉ số sau cho từng batch size:

- Số dòng thành công và số dòng bị bỏ qua/cập nhật.
- Số byte payload và số statement gửi.
- Thời gian truyền, thời gian thực thi và thời gian commit.
- Throughput (rows/second) và latency p50/p95/p99.
- Rows examined, warnings, duplicate count và lỗi.
- CPU, disk I/O, redo log pressure, lock wait và replication lag.

Ví dụ bảng ghi kết quả benchmark:

| Batch rows | Payload bytes | Insert time | Commit time | Rows/sec | p95 latency | Lỗi |
| ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 100 | Đo thực tế | Đo thực tế | Đo thực tế | Tính từ kết quả | Đo nhiều lần | Ghi nhận |
| 500 | Đo thực tế | Đo thực tế | Đo thực tế | Tính từ kết quả | Đo nhiều lần | Ghi nhận |
| 1.000 | Đo thực tế | Đo thực tế | Đo thực tế | Tính từ kết quả | Đo nhiều lần | Ghi nhận |
| 5.000 | Đo thực tế | Đo thực tế | Đo thực tế | Tính từ kết quả | Đo nhiều lần | Ghi nhận |

Đừng đưa các giá trị minh họa thành cam kết hiệu năng. Cùng batch 1.000 dòng có thể chạy khác nhau nhiều lần tùy độ rộng row, index, cache, phần cứng và số transaction đồng thời.

## 14. Quy trình thực hành an toàn

1. Xác định nguồn dữ liệu, số dòng, kích thước row và yêu cầu xử lý duplicate.
2. Kiểm tra `max_allowed_packet` trên server và client/driver; kiểm tra timeout và quyền cần thiết.
3. Chọn multi-row INSERT, `INSERT ... SELECT` hoặc `LOAD DATA` theo loại nguồn.
4. Chọn batch size theo cả số dòng và tổng byte; bắt đầu nhỏ rồi benchmark.
5. Quyết định ranh giới transaction: all-or-nothing hay commit từng batch.
6. Dùng khóa ổn định/checkpoint để có thể tiếp tục sau lỗi.
7. Đo thời gian thực thi và commit, throughput, tail latency, lock wait và replication lag.
8. Xác minh số dòng, duplicate, warning và tính đúng đắn nghiệp vụ sau mỗi batch.
9. Chạy thử rollback và resume trong môi trường test trước khi triển khai job dài.

Với production, nên có giới hạn tốc độ, khả năng tạm dừng job và cảnh báo khi latency hoặc replication lag vượt ngưỡng vận hành. Một job nạp dữ liệu không nên chiếm toàn bộ I/O hoặc làm truy vấn trực tuyến mất khả năng đáp ứng.

## 15. Bài tập tự kiểm tra

1. Vì sao multi-row INSERT thường nhanh hơn gửi một INSERT cho mỗi dòng?
2. Phân biệt kích thước statement với kích thước transaction.
3. Khi nào `INSERT ... SELECT` phù hợp hơn chuyển dữ liệu qua client?
4. Vì sao `LOAD DATA` thường phù hợp với tệp lớn?
5. `max_allowed_packet` giới hạn điều gì? Vì sao cần kiểm tra cả server và client?
6. `net_buffer_length` khác `max_allowed_packet` ở điểm nào?
7. Vì sao batch có BLOB/JSON lớn phải được giới hạn theo byte thay vì chỉ theo số dòng?
8. So sánh `INSERT IGNORE` và `INSERT ... ON DUPLICATE KEY UPDATE`.
9. Vì sao checkpoint cần được commit cùng transaction chứa dữ liệu đích?
10. Kể tên các chỉ số cần đo khi tăng batch size và giải thích dấu hiệu batch đã quá lớn.

Batch DML hiệu quả khi giảm được overhead mà vẫn giữ transaction trong giới hạn tài nguyên. Hãy chọn batch theo **số dòng và số byte**, xác định rõ **ranh giới commit**, xử lý **retry/idempotency**, rồi đo **throughput, latency và tác động lên workload khác** trước khi đưa vào vận hành.
