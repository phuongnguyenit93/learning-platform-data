# NOWAIT, SKIP LOCKED và bài toán nhận việc từ bảng

Khi nhiều worker cùng lấy công việc từ một bảng hàng đợi (queue table), mỗi worker cần nhận một nhóm hàng mà không giành cùng một công việc với worker khác. InnoDB cung cấp locking read với `NOWAIT` và `SKIP LOCKED` để điều khiển cách truy vấn phản ứng khi hàng cần đọc đang bị transaction khác khóa.

- `NOWAIT` yêu cầu MySQL trả lỗi ngay nếu không lấy được khóa cần thiết, thay vì chờ hết thời gian chờ khóa.
- `SKIP LOCKED` bỏ qua các hàng đang bị khóa và trả về những hàng có thể khóa ngay.

Hai tùy chọn đặc biệt hữu ích cho hệ thống nhận việc từ bảng: nhiều worker có thể cùng chọn các công việc sẵn sàng, khóa hàng được chọn, chuyển trạng thái sang đang xử lý rồi commit nhanh. Cần kết hợp chúng với transaction, chỉ mục phù hợp và cơ chế phục hồi công việc khi worker gặp sự cố.

## 1. Locking read với `FOR UPDATE`

Với InnoDB, `SELECT ... FOR UPDATE` là locking read. Truy vấn đọc các hàng phù hợp và lấy khóa độc quyền trên những hàng được chọn để transaction hiện tại có thể cập nhật chúng. Transaction khác muốn sửa hoặc khóa xung đột trên cùng hàng phải chờ, hoặc xử lý theo tùy chọn chờ khóa mà nó sử dụng.

Ví dụ khóa một đơn hàng trước khi chuyển trạng thái:

```sql
START TRANSACTION;

SELECT order_id, status
FROM orders
WHERE order_id = 7001
FOR UPDATE;

UPDATE orders
SET status = 'PROCESSING'
WHERE order_id = 7001;

COMMIT;
```

Khóa được giữ đến khi transaction commit hoặc rollback. Nhờ vậy, hai transaction không thể đồng thời thực hiện phần đọc-kiểm tra-cập nhật trên cùng hàng như thể mỗi transaction đang sở hữu hàng đó.

`FOR UPDATE` cần được dùng trong transaction tường minh, chẳng hạn sau `START TRANSACTION`, hoặc trong session đã tắt autocommit. Nếu mỗi câu lệnh tự chạy trong một transaction riêng do autocommit bật, khóa của câu `SELECT` có thể được giải phóng ngay khi câu lệnh kết thúc; khi đó câu `UPDATE` tiếp theo không còn được bảo vệ bởi khóa vừa đọc.

## 2. `NOWAIT`: không chờ khi hàng đang bị khóa

Mặc định, một locking read có thể phải chờ transaction khác nhả khóa. Thêm `NOWAIT` để yêu cầu MySQL báo lỗi ngay khi không thể lấy khóa:

```sql
START TRANSACTION;

SELECT order_id, status
FROM orders
WHERE order_id = 7001
FOR UPDATE NOWAIT;

COMMIT;
```

Nếu transaction khác đang giữ khóa xung đột trên hàng `order_id = 7001`, truy vấn trả lỗi lock-not-available (MySQL error `3572`, `ER_LOCK_NOWAIT`) thay vì chờ. Ứng dụng có thể rollback transaction và quyết định thử lại sau, trả thông báo bận hoặc chọn một công việc khác.

`NOWAIT` phù hợp khi độ trễ quan trọng và ứng dụng có cách xử lý tình huống tranh chấp. Nó giúp tránh một worker bị treo lâu chỉ vì một hàng đang bận. Tuy vậy, không nên retry liên tục ngay lập tức; hãy giới hạn số lần thử và cân nhắc backoff để tránh tạo thêm tải khi hệ thống đang tranh chấp.

## 3. `SKIP LOCKED`: bỏ qua hàng đang bị khóa

Thêm `SKIP LOCKED` để truy vấn bỏ qua những hàng có khóa xung đột thay vì chờ:

```sql
START TRANSACTION;

SELECT job_id, payload
FROM job_queue
WHERE status = 'READY'
ORDER BY available_at, job_id
LIMIT 10
FOR UPDATE SKIP LOCKED;

COMMIT;
```

Nếu một worker khác đang khóa một số hàng phù hợp, truy vấn trả về tối đa 10 hàng còn lại có thể khóa. Khi mọi hàng phù hợp đều đang bị khóa, truy vấn có thể trả về tập kết quả rỗng dù bảng vẫn còn công việc chưa xử lý.

`SKIP LOCKED` hữu ích cho queue vì mỗi worker có thể nhận các hàng khác nhau mà ít phải chờ nhau. Nhưng kết quả là một góc nhìn không nhất quán của tập hàng: những hàng đang bị khóa bị bỏ qua dù chúng có thể thỏa điều kiện truy vấn. Vì vậy, không dùng `SKIP LOCKED` cho truy vấn báo cáo hoặc nghiệp vụ cần đọc đầy đủ và nhất quán tất cả hàng phù hợp.

`NOWAIT` và `SKIP LOCKED` là hai lựa chọn khác nhau cho cùng locking clause. Dùng `NOWAIT` khi muốn nhận lỗi ngay; dùng `SKIP LOCKED` khi có thể bỏ qua hàng bận và tiếp tục với hàng khác.

## 4. Thiết kế bảng hàng đợi

Một bảng queue đơn giản có thể lưu trạng thái, thời điểm sẵn sàng, số lần thử và thông tin worker đang giữ công việc:

```sql
CREATE TABLE job_queue (
    job_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    payload JSON NOT NULL,
    status ENUM('READY', 'RUNNING', 'DONE', 'FAILED') NOT NULL DEFAULT 'READY',
    available_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    attempts INT UNSIGNED NOT NULL DEFAULT 0,
    worker_id VARCHAR(100) NULL,
    claim_token CHAR(36) NULL,
    locked_at DATETIME NULL,
    lease_until DATETIME NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (job_id),
    KEY idx_job_ready (status, available_at, job_id),
    KEY idx_job_lease (status, lease_until)
) ENGINE = InnoDB;
```

Ý nghĩa các cột chính:

- `status`: công việc đang sẵn sàng, đang chạy, đã hoàn thành hoặc thất bại.
- `available_at`: thời điểm sớm nhất công việc được phép nhận, hữu ích cho retry có trì hoãn.
- `attempts`: số lần công việc được nhận xử lý.
- `worker_id`: worker đang sở hữu lượt xử lý hiện tại.
- `claim_token`: mã nhận việc duy nhất cho lượt claim, dùng để ngăn một worker cũ cập nhật nhầm lượt xử lý mới.
- `lease_until`: thời hạn giữ quyền xử lý; công việc có thể được thu hồi nếu worker chết và lease hết hạn.

Chỉ mục `idx_job_ready (status, available_at, job_id)` hỗ trợ lọc trạng thái, giới hạn theo thời điểm sẵn sàng và duyệt theo thứ tự thời gian cùng khóa chính. Chỉ mục `idx_job_lease` hỗ trợ tìm các lượt chạy đã hết lease. Chỉ mục thực tế cần được kiểm tra bằng `EXPLAIN` với kích thước và phân bố dữ liệu của hệ thống.

## 5. Quy trình claim công việc bằng `SKIP LOCKED`

Một lượt nhận việc cần giữ khóa từ lúc chọn hàng đến lúc đổi trạng thái. Worker không được commit ngay sau `SELECT`, vì như vậy khóa sẽ được giải phóng trước khi công việc được đánh dấu `RUNNING`.

Quy trình gồm các bước:

1. Bắt đầu transaction.
2. Chọn một nhóm công việc `READY` đã đến thời điểm xử lý bằng `FOR UPDATE SKIP LOCKED`.
3. Trong cùng transaction, đổi các hàng đã chọn thành `RUNNING`, ghi worker, claim token, thời điểm khóa và thời hạn lease.
4. Commit ngay sau khi claim xong.
5. Xử lý payload bên ngoài transaction, sau đó cập nhật kết quả bằng điều kiện kiểm tra quyền sở hữu lượt claim.

Ví dụ SQL cho bước chọn:

```sql
START TRANSACTION;

SELECT job_id, payload
FROM job_queue
WHERE status = 'READY'
  AND available_at <= CURRENT_TIMESTAMP
ORDER BY available_at, job_id
LIMIT 10
FOR UPDATE SKIP LOCKED;
```

Ứng dụng lấy danh sách `job_id` trả về, tạo một `claim_token` ngẫu nhiên cho lượt nhận này, rồi chạy câu cập nhật trên **cùng connection và trước khi commit**. Với danh sách ID đã chọn, ứng dụng tạo số placeholder tương ứng và truyền các ID bằng prepared statement:

```sql
UPDATE job_queue
SET status = 'RUNNING',
    worker_id = ?,
    claim_token = ?,
    locked_at = CURRENT_TIMESTAMP,
    lease_until = CURRENT_TIMESTAMP + INTERVAL 5 MINUTE,
    attempts = attempts + 1
WHERE status = 'READY'
  AND job_id IN (?, ?, ?, ?);

COMMIT;
```

Số placeholder trong ví dụ là bốn để minh họa; ứng dụng phải tạo đúng số placeholder theo số ID đã chọn và bind từng giá trị. Không ghép giá trị đầu vào của người dùng trực tiếp vào SQL. Nếu không có hàng nào được chọn, commit transaction rỗng rồi chờ hoặc poll lại sau một khoảng thời gian phù hợp.

Nếu số hàng cập nhật khác số ID đã chọn, hãy rollback và điều tra thay vì bắt đầu xử lý một nhóm claim không đầy đủ. Trong điều kiện bình thường, các hàng vừa chọn vẫn đang bị transaction hiện tại khóa nên câu `UPDATE` phải đổi được đúng các hàng đó.

Sau `COMMIT`, worker có thể xử lý từng payload. Không giữ transaction mở trong suốt thời gian gọi API, gửi email, xử lý tệp hoặc thực hiện công việc kéo dài; làm vậy sẽ giữ khóa quá lâu và giảm khả năng các worker khác nhận việc.

## 6. Minh họa luồng nhiều worker

Giả sử queue có các công việc J1 đến J6. Worker A và B cùng chạy truy vấn nhận tối đa ba hàng:

| Lượt | Worker A | Worker B |
|---|---|---|
| 1 | Khóa J1, J2, J3 bằng `SKIP LOCKED` |  |
| 2 |  | Bỏ qua J1, J2, J3 đang bị khóa; khóa J4, J5, J6 |
| 3 | Đổi J1-J3 thành `RUNNING`, commit | Đổi J4-J6 thành `RUNNING`, commit |
| 4 | Xử lý J1-J3 sau commit | Xử lý J4-J6 sau commit |

Hai worker nhận các nhóm khác nhau mà không phải chờ nhau trên các hàng đã được khóa. Nếu Worker A rollback trước khi claim hoàn tất, khóa được giải phóng và các hàng đó có thể được worker khác nhận ở lượt tiếp theo.

Kết quả thực tế phụ thuộc thời điểm các transaction chạy và thứ tự khóa. `SKIP LOCKED` không đảm bảo worker nào nhận công việc cũ nhất tuyệt đối trong mọi tình huống; nó ưu tiên các hàng có thể khóa trong thứ tự truy vấn.

## 7. Cập nhật hoàn tất và kiểm tra quyền sở hữu

Sau khi xử lý thành công, worker đánh dấu công việc hoàn tất. Câu lệnh cần kiểm tra `worker_id` và `claim_token` của đúng lượt claim:

```sql
UPDATE job_queue
SET status = 'DONE',
    worker_id = NULL,
    claim_token = NULL,
    locked_at = NULL,
    lease_until = NULL
WHERE job_id = ?
  AND status = 'RUNNING'
  AND worker_id = ?
  AND claim_token = ?;
```

Nếu câu lệnh cập nhật một hàng, worker vẫn sở hữu lượt claim và đã hoàn tất trạng thái. Nếu cập nhật `0` hàng, lease có thể đã hết hạn và công việc được worker khác nhận lại, hoặc trạng thái đã thay đổi. Worker cũ không được ghi đè kết quả của lượt xử lý mới.

Nếu xử lý thất bại tạm thời, có thể đưa công việc về `READY` với thời điểm thử lại trong tương lai:

```sql
UPDATE job_queue
SET status = 'READY',
    available_at = CURRENT_TIMESTAMP + INTERVAL 30 SECOND,
    worker_id = NULL,
    claim_token = NULL,
    locked_at = NULL,
    lease_until = NULL
WHERE job_id = ?
  AND status = 'RUNNING'
  AND worker_id = ?
  AND claim_token = ?;
```

Lỗi không thể phục hồi có thể chuyển sang `FAILED` sau khi đạt giới hạn `attempts`. Chính sách retry cần phân biệt lỗi tạm thời (timeout, dịch vụ ngoài bận) và lỗi nghiệp vụ không thể tự khắc phục (dữ liệu không hợp lệ).

## 8. Lease và phục hồi khi worker bị dừng

Worker có thể chết sau khi claim nhưng trước khi đánh dấu `DONE`. Nếu không có cơ chế phục hồi, hàng sẽ nằm mãi ở trạng thái `RUNNING`. Cột `lease_until` cho phép xác định quyền xử lý đã hết hạn:

```sql
UPDATE job_queue
SET status = 'READY',
    worker_id = NULL,
    claim_token = NULL,
    locked_at = NULL,
    lease_until = NULL,
    available_at = CURRENT_TIMESTAMP
WHERE status = 'RUNNING'
  AND lease_until < CURRENT_TIMESTAMP;
```

Một tác vụ định kỳ có thể chạy câu lệnh này để đưa các công việc hết lease về hàng đợi. Worker xử lý lâu cần gia hạn lease bằng câu lệnh có điều kiện `job_id`, `worker_id`, `claim_token` và `status = 'RUNNING'`. Nếu cập nhật gia hạn không tác động hàng nào, worker đã mất quyền sở hữu và nên dừng xử lý nếu có thể.

Chọn thời lượng lease đủ dài cho công việc thông thường, đồng thời gia hạn theo heartbeat đối với tác vụ dài. Nếu lease quá ngắn, worker khỏe mạnh có thể bị thu hồi việc khi vẫn đang xử lý. Nếu lease quá dài, công việc bị kẹt sẽ mất nhiều thời gian mới được phục hồi.

Lease không đảm bảo một công việc chỉ được thực thi đúng một lần. Worker có thể hoàn tất tác động bên ngoài rồi chết trước khi ghi `DONE`; sau khi lease hết hạn, công việc sẽ được chạy lại. Vì vậy, handler nên có tính idempotent hoặc dùng idempotency key/unique business key để tránh tạo tác động trùng lặp. Với thao tác ghi dữ liệu quan trọng, có thể thiết kế outbox/inbox hoặc ràng buộc duy nhất để bảo vệ tính đúng đắn.

## 9. Khi nào dùng `NOWAIT`, khi nào dùng `SKIP LOCKED`?

| Tình huống | Lựa chọn | Cách ứng dụng xử lý |
|---|---|---|
| Cần khóa một bản ghi cụ thể và không muốn chờ | `FOR UPDATE NOWAIT` | Bắt lỗi lock-not-available, rollback và báo bận hoặc thử lại có backoff |
| Nhiều worker lấy các hàng khác nhau từ queue | `FOR UPDATE SKIP LOCKED` | Nhận các hàng không bị khóa, cập nhật trạng thái và commit nhanh |
| Cần đọc đầy đủ tập hàng để báo cáo hoặc đối soát | Consistent read phù hợp, không dùng `SKIP LOCKED` | Chọn isolation level và snapshot theo yêu cầu nhất quán |
| Hàng đang bị khóa nhưng cần chờ đến lượt | `FOR UPDATE` thông thường | Chờ theo cấu hình timeout và xử lý timeout/deadlock |

Không dùng `NOWAIT` và `SKIP LOCKED` như cách thay thế cho thiết kế transaction. Chúng chỉ điều khiển hành vi khi locking read gặp khóa xung đột.

## 10. Giới hạn và lưu ý vận hành

- `NOWAIT` và `SKIP LOCKED` áp dụng cho khóa ở mức hàng. Chúng không bỏ qua khóa ở mức bảng hoặc mọi loại chờ khác; ví dụ metadata lock vẫn có thể khiến câu lệnh phải chờ.
- Cần dùng engine hỗ trợ row-level locking như InnoDB. Hãy xác minh engine của bảng queue và bảng liên quan.
- `SKIP LOCKED` có thể bỏ qua hàng cũ đang bị giữ khóa nhiều lần, tạo nguy cơ starvation. Theo dõi tuổi của công việc chờ lâu, thời gian xử lý và số lần retry.
- Điều kiện lọc và thứ tự sắp xếp cần chỉ mục phù hợp. Nếu truy vấn phải quét quá nhiều hàng `READY` đã khóa hoặc hàng không đến hạn, lợi ích của `SKIP LOCKED` sẽ giảm.
- Giữ transaction claim ngắn và xử lý payload sau commit. Không gọi dịch vụ ngoài khi đang giữ khóa hàng trong transaction.
- Các câu lệnh dùng `SKIP LOCKED` không an toàn cho statement-based replication. Khi dùng replication, hãy chọn và kiểm tra định dạng binary log/replication phù hợp, thường là row-based, theo cấu hình phiên bản MySQL của hệ thống.
- Theo dõi deadlock và lock wait bằng log/metric của InnoDB. `SKIP LOCKED` giảm chờ trên các hàng bị khóa nhưng không loại bỏ mọi khả năng deadlock trong các thao tác khác của transaction.

## 11. Tự kiểm tra

1. `NOWAIT` khác gì với hành vi chờ khóa mặc định của `SELECT ... FOR UPDATE`?
2. Vì sao `SKIP LOCKED` phù hợp với queue table nhưng không phù hợp với truy vấn báo cáo cần tập dữ liệu đầy đủ?
3. Vì sao câu `SELECT ... FOR UPDATE SKIP LOCKED` và câu `UPDATE` đổi trạng thái phải nằm trong cùng transaction?
4. Nếu queue query trả về rỗng, có thể kết luận queue không còn công việc không? Vì sao?
5. `claim_token` giúp ngăn worker cũ ghi kết quả lên lượt claim mới như thế nào?
6. Lease giải quyết trường hợp worker bị dừng giữa chừng ra sao, và vì sao vẫn cần idempotency?
7. Những loại khóa hoặc chờ nào không được `SKIP LOCKED` bỏ qua?

