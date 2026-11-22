# Thiết kế giao dịch ngắn, xử lý lỗi và thực hiện lại có kiểm soát

Transaction trong MySQL cần bao quanh đúng phần công việc dữ liệu phải cùng thành công hoặc cùng thất bại. Một transaction quá dài giữ khóa lâu, làm tăng lock wait, deadlock, undo history và thời gian phản hồi. Một transaction quá ngắn hoặc bị chia sai ranh giới lại có thể để dữ liệu ở trạng thái dở dang. Thiết kế tốt cần cân bằng tính nguyên tử, thời gian giữ khóa và khả năng phục hồi khi có lỗi tạm thời.

Với InnoDB, ứng dụng nên chuẩn bị dữ liệu trước khi mở transaction, thực hiện nhanh các thao tác database cần tính nguyên tử, kiểm tra kết quả từng bước, rồi commit hoặc rollback ngay. Khi gặp deadlock hoặc lock wait timeout, cần rollback sạch và thực hiện lại **toàn bộ đơn vị nghiệp vụ** với số lần giới hạn. Khi kết quả commit không rõ do mất kết nối, cần idempotency để tránh áp dụng nghiệp vụ hai lần.

## 1. Ranh giới transaction nên theo đơn vị nghiệp vụ

Một transaction nên gom những thay đổi phải được nhìn nhận như một kết quả nghiệp vụ duy nhất. Ví dụ tạo đơn hàng có thể gồm:

1. Ghi đơn hàng.
2. Giữ hoặc trừ tồn kho.
3. Ghi các dòng hàng.
4. Ghi sự kiện cần phát ra sau khi đơn hàng được xác nhận.

Nếu một bước thất bại, các thay đổi database liên quan cần được rollback cùng nhau. Tuy nhiên, việc gửi email, gọi cổng thanh toán hoặc chờ người dùng xác nhận không thể được hoàn tác bằng `ROLLBACK` của MySQL. Các hành động ngoài database cần cơ chế phối hợp riêng như outbox, idempotent consumer hoặc saga.

Trước khi thiết kế transaction, hãy xác định:

- Bất biến nghiệp vụ nào phải luôn đúng?
- Những hàng/bảng nào cần thay đổi cùng nhau?
- Điều kiện nào phải được kiểm tra dưới khóa hoặc trong câu DML nguyên tử?
- Khi một bước thất bại, toàn bộ công việc có phải hủy không?
- Có hành động bên ngoài nào cần phát sau khi commit không?

Ranh giới này giúp tránh cả hai cực: commit quá sớm làm lộ trạng thái dở dang và transaction kéo dài qua những công việc không cần khóa database.

## 2. Vì sao transaction cần ngắn?

Trong InnoDB, transaction có thể giữ record lock, gap lock hoặc next-key lock cho đến khi kết thúc. Transaction dài làm tăng xác suất transaction khác phải chờ và tạo chu trình deadlock.

Transaction mở lâu còn giữ các phiên bản cũ cần thiết cho consistent read. Điều này có thể làm undo history khó được purge, tăng dung lượng undo và gây áp lực lên hệ thống. Một transaction đọc snapshot rồi để connection nhàn rỗi trong nhiều phút vẫn có thể gây vấn đề vận hành dù không chạy câu SQL liên tục.

Các nguyên tắc thực tế:

- Xác thực đầu vào và tính toán không cần dữ liệu khóa trước khi mở transaction.
- Mở transaction ngay trước thao tác dữ liệu cần tính nguyên tử.
- Dùng index để tìm đúng hàng và giới hạn phạm vi quét/khóa.
- Khóa nhiều hàng theo thứ tự nhất quán.
- Không gọi HTTP, gửi email, upload file, chờ người dùng hoặc sleep khi transaction đang mở.
- Commit hoặc rollback ngay khi hoàn thành công việc database.
- Không để connection có transaction chưa kết thúc quay lại connection pool.

## 3. Chuẩn bị trước transaction, thực hiện phần tối thiểu bên trong

Ví dụ khi tạo đơn hàng, ứng dụng có thể làm trước transaction:

- Kiểm tra cú pháp và cấu trúc request.
- Tính tổng tiền từ dữ liệu đã được xác thực, nếu phép tính không phụ thuộc trạng thái đồng thời trong database.
- Chuẩn hóa mã sản phẩm và sắp xếp danh sách ID theo thứ tự cố định.
- Tạo request ID/idempotency key.
- Chuẩn bị payload sự kiện cần ghi vào outbox.

Sau đó transaction chỉ thực hiện các bước cần đồng bộ với dữ liệu hiện hành: xác nhận tồn kho, ghi đơn, ghi dòng hàng, ghi outbox và lưu kết quả idempotency. Không chuyển một phép kiểm tra quan trọng ra ngoài transaction nếu giá trị có thể thay đổi đồng thời trước lúc ghi. Ví dụ, kiểm tra tồn kho ở ngoài transaction rồi mới trừ kho sẽ tạo race condition.

## 4. Dùng UPDATE có điều kiện thay cho read-modify-write khi có thể

Nếu chỉ cần giảm tồn kho khi còn đủ số lượng, một câu lệnh có điều kiện thường ngắn và an toàn hơn việc đọc số lượng về ứng dụng rồi tự tính:

```sql
UPDATE inventory
SET available_quantity = available_quantity - 2
WHERE product_id = 501
  AND available_quantity >= 2;
```

Ứng dụng kiểm tra số hàng bị ảnh hưởng:

- `1`: điều kiện đã thỏa và tồn kho được giảm.
- `0`: sản phẩm không tồn tại hoặc không đủ tồn kho theo điều kiện.

Nếu cần phân biệt hai nguyên nhân, có thể đọc thêm trong cùng transaction theo logic phù hợp. Không nên bỏ điều kiện `available_quantity >= 2` rồi tin rằng kiểm tra trước đó ở ứng dụng vẫn còn đúng.

Với bảng InnoDB, câu `UPDATE` là một thao tác nguyên tử. Hai transaction cạnh tranh trên cùng sản phẩm được điều phối qua khóa; câu lệnh thứ hai đánh giá điều kiện trên hàng hiện hành khi thực hiện cập nhật. Đây là mẫu hữu ích để giảm thời gian giữ transaction và tránh lost update.

## 5. Ví dụ transaction ngắn cho đặt hàng và giữ tồn kho

Giả sử có các bảng đơn hàng, tồn kho, dòng hàng và outbox:

```sql
CREATE TABLE inventory (
    product_id BIGINT UNSIGNED NOT NULL,
    available_quantity INT NOT NULL,
    PRIMARY KEY (product_id)
) ENGINE=InnoDB;

CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    total_amount DECIMAL(13, 2) NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (order_id)
) ENGINE=InnoDB;

CREATE TABLE order_items (
    order_id BIGINT UNSIGNED NOT NULL,
    product_id BIGINT UNSIGNED NOT NULL,
    quantity INT NOT NULL,
    unit_price DECIMAL(13, 2) NOT NULL,
    PRIMARY KEY (order_id, product_id)
) ENGINE=InnoDB;

CREATE TABLE outbox_events (
    event_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    event_key VARCHAR(100) NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    payload JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMP NULL,
    PRIMARY KEY (event_id),
    UNIQUE KEY uq_outbox_event_key (event_key)
) ENGINE=InnoDB;
```

Ứng dụng chuẩn bị request, kiểm tra định dạng và sắp xếp các `product_id` trước khi bắt đầu transaction. Trong transaction:

```sql
START TRANSACTION;

-- Lặp qua product_id theo thứ tự tăng dần.
-- Mỗi UPDATE phải ảnh hưởng đúng một hàng; nếu không, ROLLBACK.
UPDATE inventory
SET available_quantity = available_quantity - 2
WHERE product_id = 501
  AND available_quantity >= 2;

UPDATE inventory
SET available_quantity = available_quantity - 1
WHERE product_id = 502
  AND available_quantity >= 1;

-- Sau khi ứng dụng xác nhận cả hai UPDATE thành công:
INSERT INTO orders (customer_id, total_amount, status)
VALUES (42, 250000.00, 'pending');

-- Ứng dụng lấy order_id vừa tạo trên cùng connection.
SET @order_id = LAST_INSERT_ID();
INSERT INTO order_items (order_id, product_id, quantity, unit_price)
VALUES
    (@order_id, 501, 2, 75000.00),
    (@order_id, 502, 1, 100000.00);

INSERT INTO outbox_events (event_key, event_type, payload)
VALUES (
    'order-created:request-abc',
    'OrderCreated',
    JSON_OBJECT('customer_id', 42, 'request_id', 'request-abc')
);

COMMIT;
```

Đây là khung minh họa. Trong code thực tế, hãy lấy `order_id` ngay sau insert bằng API generated keys của driver hoặc lưu vào biến session trên cùng connection; không gọi một thao tác khác có thể thay đổi `LAST_INSERT_ID()` giữa lúc lấy ID và ghi dòng hàng. Nếu bất kỳ UPDATE tồn kho nào ảnh hưởng 0 hàng, ứng dụng phải rollback và trả lỗi hết hàng/sản phẩm không hợp lệ. Không được tiếp tục insert đơn rồi commit.

Sau commit, worker riêng đọc outbox và gửi sự kiện. Việc gửi thông báo không giữ transaction tạo đơn mở trong lúc chờ mạng.

## 6. Khóa nhiều hàng theo cùng một thứ tự

Deadlock thường xuất hiện khi các transaction khóa cùng tập hàng theo thứ tự khác nhau:

- Transaction A khóa sản phẩm 501 rồi chờ 502.
- Transaction B khóa sản phẩm 502 rồi chờ 501.

Để giảm rủi ro, mọi luồng cập nhật nhiều sản phẩm nên khóa hoặc cập nhật theo cùng thứ tự, chẳng hạn `product_id` tăng dần. Sắp xếp danh sách ID ở ứng dụng trước khi thực hiện các câu lệnh trong transaction.

Nếu cần lấy khóa trước khi tính toán:

```sql
START TRANSACTION;

SELECT product_id, available_quantity
FROM inventory
WHERE product_id IN (501, 502)
ORDER BY product_id
FOR UPDATE;

-- Kiểm tra và cập nhật trong cùng transaction.

COMMIT;
```

Thứ tự kết quả của `SELECT` không phải là lời bảo đảm tuyệt đối về thứ tự nội bộ mà mọi kế hoạch khóa sẽ dùng trong mọi tình huống. Với các luồng phức tạp, cần kiểm tra access path và cách lấy khóa thực tế; quy tắc nhất quán về thứ tự truy cập vẫn là biện pháp giảm deadlock quan trọng.

## 7. Index tốt giúp transaction ngắn và khóa hẹp

Một câu `UPDATE` thiếu index trên điều kiện tìm hàng có thể quét nhiều record hơn cần thiết. Với locking read hoặc DML, số index record được quét ảnh hưởng đến phạm vi khóa và khả năng xung đột.

Ví dụ:

```sql
UPDATE inventory
SET available_quantity = available_quantity - 1
WHERE product_id = 501
  AND available_quantity >= 1;
```

`product_id` là primary key nên MySQL có thể tìm hàng trực tiếp. Nếu truy vấn lọc theo một cột không có index, cần đánh giá index phù hợp và kiểm tra kế hoạch bằng `EXPLAIN`.

Không tạo index tràn lan. Mỗi index làm tăng chi phí insert/update/delete và dung lượng lưu trữ. Chọn index theo workload, tính chọn lọc và thứ tự cột; kiểm tra cả hiệu năng truy vấn lẫn chi phí ghi.

## 8. Phân biệt lỗi có thể retry và lỗi nghiệp vụ

Không phải lỗi SQL nào cũng nên thực hiện lại. Một số lỗi là tạm thời do cạnh tranh, một số là vi phạm dữ liệu hoặc quy tắc nghiệp vụ sẽ tiếp tục thất bại nếu gửi lại cùng đầu vào.

| Lỗi/tình huống | Mã MySQL thường gặp | Hướng xử lý |
| --- | ---: | --- |
| Deadlock được InnoDB phát hiện | `1213` (`ER_LOCK_DEADLOCK`) | Transaction nạn nhân bị rollback; có thể retry toàn bộ transaction với giới hạn |
| Lock wait timeout | `1205` (`ER_LOCK_WAIT_TIMEOUT`) | Mặc định statement bị rollback; ứng dụng nên rollback transaction rõ ràng rồi mới cân nhắc retry |
| NOWAIT không lấy được khóa | `3572` (`ER_LOCK_NOWAIT`) | Xử lý như tài nguyên đang bận; trả lỗi hoặc retry theo chính sách ngắn, có giới hạn |
| Duplicate key | `1062` (`ER_DUP_ENTRY`) | Thường là xung đột nghiệp vụ/idempotency; kiểm tra bản ghi hiện có, không retry mù quáng |
| Foreign key/check/data validation | Ví dụ `1452`, `3819`, `1406` | Sửa dữ liệu hoặc trả lỗi nghiệp vụ; không retry cùng đầu vào |
| Mất kết nối trong lúc commit | Có thể là lỗi kết nối như `2013` | Kết quả commit có thể chưa xác định với client; tra cứu bằng idempotency key trước khi gửi lại |

Deadlock thường đi kèm SQLSTATE `40001`. Nên phân loại bằng SQLSTATE và mã lỗi vendor của driver thay vì chỉ so khớp thông điệp văn bản, vì message có thể thay đổi theo phiên bản/ngôn ngữ.

Mã lỗi chỉ là một phần thông tin. Ứng dụng nên kiểm tra SQLSTATE, mã vendor, trạng thái connection và giai đoạn lỗi. Không retry tất cả lỗi `HY000` hoặc mọi lỗi mạng như thể chúng đều có cùng ngữ nghĩa.

## 9. Deadlock: rollback toàn transaction và retry toàn bộ

Khi InnoDB phát hiện deadlock, nó chọn một transaction làm nạn nhân và rollback transaction đó. Các câu lệnh đã chạy trước trong transaction nạn nhân không còn hiệu lực.

Ứng dụng không được chỉ chạy lại câu SQL cuối. Cần bắt đầu một transaction mới và chạy lại toàn bộ đơn vị nghiệp vụ từ đầu, gồm các lần đọc/kiểm tra cần thiết. Giá trị đọc ở lần thử trước có thể đã cũ; lần thử mới phải đọc lại trạng thái hiện hành.

Ví dụ logic xử lý:

```text
for attempt from 1 to MAX_ATTEMPTS:
    acquire connection
    begin transaction
    try:
        read current state
        validate conditions
        perform all database writes
        commit
        return success
    catch error:
        rollback if transaction is still active
        if error is retryable and attempt < MAX_ATTEMPTS:
            release connection
            wait with exponential backoff and jitter
            continue with a new transaction
        raise error
    finally:
        return only a clean connection to the pool
```

Đây là pseudocode, không phải cú pháp SQL. Khi retry, phải dùng một transaction mới; không tiếp tục chạy câu lệnh trong transaction đã bị InnoDB rollback.

## 10. Lock wait timeout khác deadlock

Khi chờ khóa vượt `innodb_lock_wait_timeout`, InnoDB mặc định rollback câu lệnh đang chờ, không nhất thiết rollback toàn transaction. Nếu biến `innodb_rollback_on_timeout` được bật, hành vi rollback toàn transaction sẽ được áp dụng.

Kiểm tra cấu hình:

```sql
SHOW VARIABLES LIKE 'innodb_lock_wait_timeout';
SHOW VARIABLES LIKE 'innodb_rollback_on_timeout';
```

Để ứng dụng có trạng thái đơn giản và tránh giữ các khóa từ phần transaction đã chạy trước đó, cách xử lý an toàn thường là rollback toàn bộ transaction sau timeout rồi đánh giá có nên retry toàn bộ đơn vị nghiệp vụ hay không. Không giả định timeout luôn tự kết thúc transaction.

Trước khi retry, cần tìm nguyên nhân chờ khóa: transaction khác mở lâu, thiếu index, thứ tự truy cập hàng không nhất quán, hoặc thao tác quét phạm vi quá rộng. Retry liên tục mà không giảm tranh chấp chỉ làm tải hệ thống nặng hơn.

## 11. Retry có giới hạn, exponential backoff và jitter

Nếu nhiều request cùng retry ngay lập tức sau deadlock, chúng có thể lại tranh chấp đúng các hàng đó và tạo thêm deadlock. Backoff làm các lần thử lệch thời gian; jitter ngẫu nhiên giúp tránh nhiều client cùng thức dậy tại một thời điểm.

Một chính sách khởi đầu có thể là:

- Tối đa 3 đến 5 lần thử cho một đơn vị nghiệp vụ.
- Thời gian chờ tăng theo cấp số nhân, ví dụ `base_delay * 2^(attempt - 1)`.
- Thêm jitter ngẫu nhiên trong một khoảng phù hợp.
- Đặt trần cho thời gian chờ, ví dụ vài trăm mili giây đến khoảng một giây tùy SLA.
- Tổng thời gian retry phải nằm trong deadline của request.

Ví dụ công thức minh họa:

```text
delay = min(max_delay, base_delay * 2^(attempt - 1))
sleep_for(random(0, delay))
```

Các con số phải được điều chỉnh theo latency, throughput và thời gian lock wait của hệ thống. Không sleep trong lúc giữ transaction hoặc khóa. Hãy rollback, giải phóng connection/khóa rồi mới chờ.

## 12. Không retry lỗi nghiệp vụ hoặc lỗi dữ liệu một cách mù quáng

Những trường hợp sau thường không thể giải quyết bằng retry cùng dữ liệu:

- Không đủ tồn kho.
- Tài khoản bị khóa hoặc không đủ số dư.
- Dữ liệu vi phạm `NOT NULL`, `CHECK`, `FOREIGN KEY`.
- Mã nghiệp vụ đã tồn tại và phải được xử lý theo quy tắc duplicate.
- Giá trị đầu vào vượt giới hạn cột hoặc sai định dạng.
- Người dùng không có quyền thực hiện thao tác.

Retry chỉ phù hợp khi lỗi có khả năng biến mất sau một khoảng thời gian, chẳng hạn deadlock hoặc lock contention tạm thời. Với lỗi dữ liệu, hãy trả kết quả có ý nghĩa hoặc yêu cầu client điều chỉnh đầu vào.

## 13. Idempotency: bảo vệ khi client gửi lại yêu cầu

Một request có thể được gửi lại vì client timeout, người dùng nhấn nút nhiều lần, proxy retry hoặc phản hồi commit bị mất. Nếu mỗi lần gửi lại đều tạo đơn mới, một yêu cầu nghiệp vụ có thể được thực hiện nhiều lần.

Idempotency key là mã duy nhất đại diện cho một yêu cầu nghiệp vụ. Database dùng unique constraint để bảo đảm một key chỉ được xử lý một lần. Ví dụ bảng lưu kết quả:

```sql
CREATE TABLE idempotency_requests (
    request_key VARCHAR(100) NOT NULL,
    request_hash BINARY(32) NOT NULL,
    status VARCHAR(20) NOT NULL,
    response_payload JSON NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP NULL,
    PRIMARY KEY (request_key)
) ENGINE=InnoDB;
```

Trong cùng transaction với nghiệp vụ:

```sql
START TRANSACTION;

INSERT INTO idempotency_requests
    (request_key, request_hash, status)
VALUES
    ('request-abc', UNHEX(SHA2('{"customer_id":42}', 256)), 'processing');

-- Thực hiện giữ tồn kho, tạo order, order_items và outbox event.

UPDATE idempotency_requests
SET status = 'completed',
    response_payload = JSON_OBJECT('order_id', @order_id),
    completed_at = CURRENT_TIMESTAMP
WHERE request_key = 'request-abc';

COMMIT;
```

Ví dụ minh họa cần dùng request hash được tính từ payload đã chuẩn hóa, không dùng chuỗi JSON tùy ý nếu thứ tự key hoặc cách biểu diễn có thể thay đổi. Trong ứng dụng, tạo hash ổn định và bind bằng prepared statement.

Trong cùng transaction, ứng dụng phải gán `@order_id` bằng ID vừa tạo trên connection hiện tại (hoặc truyền ID lấy qua API generated keys của driver) trước khi cập nhật `response_payload`. Biến session chỉ minh họa luồng SQL; ứng dụng có thể bind trực tiếp ID vào câu `UPDATE`.

Nếu một request khác dùng cùng `request_key`, `INSERT` sẽ gặp duplicate key sau khi transaction đầu commit. Ứng dụng rollback lần thử trùng, đọc bản ghi idempotency đã tồn tại và trả lại kết quả đã lưu nếu `request_hash` khớp. Nếu cùng key nhưng payload khác, trả lỗi xung đột; không coi đó là cùng yêu cầu.

Nếu transaction đầu rollback trước commit, hàng idempotency cũng bị rollback; request retry có thể tạo reservation mới và thực hiện nghiệp vụ. Vì bản ghi idempotency và thay đổi nghiệp vụ nằm trong cùng transaction, chúng không bị lệch trạng thái.

## 14. Commit không rõ kết quả khi mất kết nối

Một tình huống khó xử lý là ứng dụng gửi `COMMIT`, MySQL xử lý và commit thành công, nhưng kết nối bị đứt trước khi client nhận phản hồi. Client không thể biết chắc transaction đã commit hay chưa chỉ từ lỗi mạng.

Không được giả định mọi lỗi kết nối trong lúc commit đều có nghĩa rollback. Cũng không được gửi lại một thao tác không idempotent với request ID mới, vì giao dịch đầu có thể đã thành công.

Quy trình an toàn:

1. Giữ nguyên idempotency key của request gốc.
2. Dùng connection mới để tra cứu kết quả theo key.
3. Nếu trạng thái `completed` và hash khớp, trả lại kết quả đã lưu.
4. Nếu không tìm thấy bản ghi, có thể thử lại cùng key theo chính sách; unique constraint sẽ bảo vệ nếu transaction trước thực tế đã commit.
5. Nếu cùng key nhưng payload hash khác, trả lỗi xung đột và cần điều tra.

Nếu không có idempotency hoặc khóa nghiệp vụ duy nhất, hệ thống khó phân biệt “commit đã thành công nhưng mất phản hồi” với “transaction chưa commit”. Đây là lý do idempotency là một phần của thiết kế retry, không chỉ là tiện ích API.

## 15. Outbox: đưa side effect ra ngoài transaction

Nếu sau khi tạo đơn hàng cần phát event, ghi một hàng outbox trong cùng transaction với đơn hàng. Worker đọc các event chưa gửi và phát ra message broker sau commit.

Luồng:

1. Transaction ghi đơn hàng và outbox event.
2. Commit xác nhận cả hai.
3. Worker lấy event chưa phát, gửi đến broker.
4. Worker đánh dấu event đã phát sau khi nhận xác nhận phù hợp.
5. Consumer xử lý idempotent vì worker có thể gửi lại nếu crash sau khi gửi nhưng trước khi đánh dấu.

Outbox bảo đảm sự kiện cần phát không bị mất khỏi database khi transaction tạo đơn commit. Nó không tự tạo exactly-once delivery đến broker; thường hệ thống đạt at-least-once delivery kết hợp consumer idempotency.

Không gọi broker hoặc API bên ngoài trong lúc transaction tạo đơn đang mở. Một lần gọi mạng chậm có thể giữ khóa lâu và tạo chuỗi lock wait cho các request khác.

## 16. Optimistic locking cho cập nhật ít tranh chấp

Không phải nghiệp vụ nào cũng cần `SELECT ... FOR UPDATE`. Với dữ liệu ít xung đột, optimistic locking dùng cột version để phát hiện một hàng đã bị thay đổi kể từ lúc ứng dụng đọc:

```sql
CREATE TABLE documents (
    document_id BIGINT UNSIGNED NOT NULL,
    body TEXT NOT NULL,
    version BIGINT UNSIGNED NOT NULL DEFAULT 1,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (document_id)
) ENGINE=InnoDB;
```

Ứng dụng đọc `version = 7`, chỉnh sửa nội dung rồi ghi:

```sql
UPDATE documents
SET body = 'Nội dung mới',
    version = version + 1
WHERE document_id = 10
  AND version = 7;
```

Nếu affected rows bằng 1, cập nhật thành công. Nếu bằng 0, version đã thay đổi hoặc hàng không còn tồn tại; ứng dụng cần đọc lại và xử lý xung đột, không ghi đè mù quáng. Cách này phù hợp khi xung đột hiếm và không cần giữ khóa trong lúc người dùng chỉnh sửa.

Optimistic locking không thay thế transaction khi một nghiệp vụ cập nhật nhiều bảng cần tính nguyên tử. Nó là một kỹ thuật phát hiện xung đột ở cấp hàng.

## 17. Xử lý batch và công việc dài

Không nên giữ một transaction duy nhất mở trong lúc xử lý hàng trăm nghìn hoặc hàng triệu bản ghi nếu nghiệp vụ cho phép chia nhỏ. Chia thành batch có kích thước hợp lý giúp:

- Giảm thời gian giữ khóa mỗi lần.
- Giảm undo log và lượng dữ liệu cần rollback.
- Giảm tác động của deadlock và lock wait.
- Cho phép theo dõi tiến độ và tiếp tục từ checkpoint.

Ví dụ quy trình:

1. Xác định một tập ID ổn định cần xử lý.
2. Chia thành batch, ví dụ vài trăm hoặc vài nghìn hàng tùy kích thước row và tải.
3. Mỗi batch chạy trong một transaction riêng.
4. Ghi checkpoint hoặc trạng thái xử lý cùng batch.
5. Retry riêng batch thất bại bằng khóa idempotent.

Batching thay đổi ranh giới atomicity: toàn bộ job không còn atomic như một transaction duy nhất. Chỉ dùng khi nghiệp vụ chấp nhận trạng thái tiến độ từng phần và có thể resume/đối soát. Nếu tất cả hàng phải cùng thành công hoặc thất bại, không thể tùy tiện chia transaction.

## 18. Quản lý connection và trạng thái transaction trong ứng dụng

Transaction thuộc về một connection. Toàn bộ câu lệnh cần tính nguyên tử phải chạy trên cùng connection và cùng transaction.

Một mẫu quản lý ở tầng ứng dụng:

```text
connection = pool.acquire()
try:
    begin transaction on connection
    try:
        execute all database steps on this connection
        verify affected-row counts
        commit on this connection
    catch error:
        rollback if the connection is usable
        throw error
finally:
    ensure no transaction remains open
    return a clean connection to the pool
```

Nếu rollback thất bại vì connection đã chết, không đưa connection đó trở lại pool như thể nó sạch; loại bỏ hoặc để driver quản lý theo chính sách pool. Khi một connection được tái sử dụng, cần bảo đảm autocommit, isolation level, session variables và trạng thái transaction đúng với cấu hình mong muốn.

Không mở transaction trên connection A rồi thực hiện một câu lệnh trên connection B và kỳ vọng commit ở A sẽ xác nhận cả hai. Điều đó phá vỡ ranh giới transaction.

## 19. Quan sát transaction lâu và nguyên nhân lock wait

Khi transaction chậm, hãy tìm nguyên nhân thay vì tăng timeout hoặc retry nhiều hơn ngay lập tức.

Kiểm tra transaction đang mở:

```sql
SELECT
    trx_id,
    trx_state,
    trx_started,
    trx_wait_started,
    trx_mysql_thread_id,
    trx_query
FROM information_schema.innodb_trx
ORDER BY trx_started;
```

Kiểm tra trạng thái InnoDB:

```sql
SHOW ENGINE INNODB STATUS\G
```

Trên MySQL 8.0, các bảng `performance_schema.data_locks` và `performance_schema.data_lock_waits` giúp xem khóa và quan hệ chờ khóa. Quyền đọc và cấu hình Performance Schema cần phù hợp với môi trường.

Các dấu hiệu cần chú ý:

- Transaction mở lâu nhưng không có truy vấn đang chạy.
- Một connection giữ khóa trong lúc ứng dụng chờ dịch vụ bên ngoài.
- Lock wait tập trung trên cùng một bảng hoặc khóa nóng.
- Query plan quét quá nhiều hàng do thiếu index hoặc điều kiện không sargable.
- Deadlock lặp lại giữa cùng các luồng cập nhật nhưng theo thứ tự khóa khác nhau.
- Undo history tăng do transaction snapshot kéo dài.

Ghi nhận thời gian transaction, số lần retry, mã lỗi, thời gian chờ khóa và request ID. Không log dữ liệu nhạy cảm không cần thiết.

## 20. Những lỗi và hiểu nhầm thường gặp

| Hiểu nhầm / lỗi | Thực tế | Cách xử lý |
| --- | --- | --- |
| Transaction càng dài càng an toàn | Transaction dài giữ khóa và undo history lâu hơn | Chỉ bao quanh các thao tác cần atomicity |
| Có thể gọi API ngoài trong transaction rồi rollback nếu thất bại | Rollback MySQL không hoàn tác dịch vụ bên ngoài | Dùng outbox/saga hoặc action bù |
| Deadlock chỉ cần retry câu SQL cuối | InnoDB rollback toàn transaction nạn nhân | Retry toàn bộ đơn vị nghiệp vụ trong transaction mới |
| Lock wait timeout luôn rollback toàn transaction | Mặc định chỉ statement bị rollback; cấu hình có thể thay đổi | Rollback rõ ràng trước khi retry |
| Retry mọi lỗi database | Lỗi dữ liệu/nghiệp vụ không tự hết khi gửi lại | Chỉ retry lỗi tạm thời đã phân loại |
| Retry ngay lập tức là đủ | Nhiều client có thể tranh chấp lại cùng lúc | Dùng backoff, jitter và giới hạn số lần |
| Mất kết nối khi COMMIT nghĩa là rollback | Commit có thể đã thành công nhưng phản hồi bị mất | Tra cứu theo idempotency key |
| Idempotency key chỉ cần ở API | Tính duy nhất phải được bảo vệ bằng unique constraint ở database | Lưu key cùng kết quả trong transaction nghiệp vụ |
| Outbox bảo đảm exactly-once delivery | Worker có thể gửi lặp khi crash | Consumer cần idempotent |
| Chia batch luôn giữ atomicity của cả job | Mỗi batch commit độc lập | Chỉ chia khi nghiệp vụ chấp nhận tiến độ từng phần |
| Có thể trả connection đang mở transaction về pool | Request sau có thể kế thừa trạng thái và khóa cũ | Commit/rollback, reset hoặc loại bỏ connection |

## 21. Quy trình thiết kế và retry transaction

Khi xây dựng một thao tác ghi quan trọng, hãy làm theo thứ tự:

1. **Xác định bất biến:** dữ liệu nào phải luôn đúng sau thao tác?
2. **Chốt ranh giới:** các thay đổi nào phải cùng commit/rollback?
3. **Chuẩn bị trước:** validate request, chuẩn hóa dữ liệu và tạo idempotency key ngoài transaction.
4. **Tối ưu access path:** có index cho các điều kiện tìm hàng và khóa không?
5. **Thống nhất thứ tự khóa:** mọi luồng chạm nhiều hàng theo cùng thứ tự.
6. **Mở transaction muộn:** chỉ ngay trước phần đọc/ghi cần nhất quán.
7. **Thực hiện ít câu lệnh nhất:** dùng DML có điều kiện khi phù hợp; kiểm tra affected rows.
8. **Ghi outbox và idempotency:** cùng transaction với thay đổi nghiệp vụ.
9. **Commit sớm:** không giữ transaction trong lúc gọi dịch vụ ngoài.
10. **Phân loại lỗi:** deadlock, timeout, duplicate, validation hay connection failure.
11. **Rollback sạch:** không retry trong transaction đã lỗi.
12. **Retry có giới hạn:** transaction mới, đọc lại trạng thái, exponential backoff và jitter.
13. **Xử lý commit không rõ:** tra cứu cùng idempotency key trước khi thực hiện lại.
14. **Quan sát và cải thiện:** theo dõi transaction duration, lock wait, deadlock và retry rate.

## 22. Bài tập thực hành

1. Viết một transaction đặt hàng gồm trừ tồn kho, tạo đơn và dòng hàng; rollback nếu một sản phẩm không đủ số lượng.
2. Sửa quy trình bằng `UPDATE ... WHERE available_quantity >= ?` và kiểm tra affected rows.
3. Tạo hai session cập nhật hai sản phẩm theo thứ tự ngược nhau để quan sát deadlock; sau đó chuẩn hóa thứ tự truy cập.
4. Tạo lock wait timeout và so sánh hành vi khi `innodb_rollback_on_timeout` bật/tắt trong môi trường lab.
5. Viết pseudocode retry toàn transaction với tối đa 3 lần thử và exponential backoff có jitter.
6. Tạo bảng idempotency với primary key `request_key`; gửi cùng một request hai lần và xác minh chỉ tạo một đơn hàng.
7. Thử gửi cùng idempotency key nhưng payload hash khác; thiết kế phản hồi xung đột.
8. Mô phỏng mất phản hồi sau commit bằng cách ngắt client ở thời điểm phù hợp trong môi trường thử nghiệm; xác minh kết quả bằng idempotency key.
9. Ghi outbox event cùng transaction tạo đơn; tạo worker gửi event và consumer xử lý idempotent.
10. Thêm cột `version` vào một bảng tài liệu và thử optimistic locking với hai client cùng cập nhật.
11. Chia một job cập nhật lớn thành batch; thiết kế checkpoint, retry và đối soát để có thể tiếp tục sau lỗi.
12. Dùng `information_schema.innodb_trx`, `SHOW ENGINE INNODB STATUS` và Performance Schema để tìm transaction lâu hoặc lock wait.

## 23. Ghi nhớ

Transaction nên bao quanh đúng đơn vị công việc nghiệp vụ cần atomicity và kết thúc càng sớm càng tốt. Chuẩn bị dữ liệu trước, dùng index phù hợp, cập nhật có điều kiện, khóa nhiều hàng theo thứ tự nhất quán và không gọi dịch vụ bên ngoài trong lúc giữ transaction.

Deadlock (`1213`) làm InnoDB rollback toàn transaction nạn nhân; lock wait timeout (`1205`) mặc định chỉ rollback statement, nên ứng dụng thường cần rollback toàn bộ trước khi retry. Retry phải chạy lại toàn bộ nghiệp vụ trong transaction mới, có giới hạn, exponential backoff và jitter; không retry mù quáng lỗi validation hoặc duplicate. Khi mất kết nối trong lúc commit, kết quả có thể không rõ với client: dùng idempotency key được bảo vệ bằng unique constraint để tra cứu hoặc gửi lại an toàn. Outbox đưa side effect ra sau commit, còn consumer phải idempotent. Theo dõi transaction duration, lock wait, deadlock, retry và connection pool để phát hiện vấn đề trước khi chúng trở thành sự cố dữ liệu.
