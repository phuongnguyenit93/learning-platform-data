# Điểm nóng trên một hàng, một khóa duy nhất hoặc một khoảng chỉ mục

Một hệ thống có thể có hàng nghìn transaction chạy đồng thời nhưng vẫn bị nghẽn vì tất cả cùng cần một tài nguyên nhỏ: một hàng tổng hợp, một khóa duy nhất phổ biến hoặc một khoảng trên index. Đây là **contention hotspot** — điểm nóng tranh chấp tài nguyên.

Điểm nóng thường không xuất hiện vì database thiếu khả năng chạy song song trên toàn bộ bảng. Nó xuất hiện vì nhiều transaction cùng cần một tài nguyên mà database phải bảo vệ theo thứ tự. Các transaction khác nhau có thể cập nhật những hàng độc lập rất nhanh, nhưng khi tất cả cùng sửa một hàng hoặc cùng cạnh tranh một key, throughput của nhóm thao tác đó bị giới hạn bởi khả năng tuần tự hóa tài nguyên.

Bài học này phân biệt ba dạng điểm nóng:

1. **Hot row:** nhiều transaction cùng đọc để cập nhật hoặc ghi vào một hàng.
2. **Hot unique key:** nhiều transaction cùng tranh chấp một giá trị duy nhất, hoặc cùng thao tác trên một business key phổ biến.
3. **Hot index range/page:** nhiều transaction quét, khóa hoặc chèn vào cùng một vùng index; đôi khi điểm nghẽn là lock logic trên range, đôi khi là latch/mutex bảo vệ trang B-tree.

Cần phân biệt **lock contention** với **latch/page contention**. Lock thường bảo vệ tính nhất quán giữa các transaction và có thể tồn tại đến COMMIT/ROLLBACK. Latch hoặc mutex thường bảo vệ cấu trúc nội bộ trong thời gian ngắn, ví dụ một trang index đang được sửa. Cả hai đều có thể làm truy vấn chậm, nhưng cách chẩn đoán và tối ưu khác nhau.

## 1. Dấu hiệu nhận biết một điểm nóng

Một điểm nóng thường thể hiện qua một hoặc nhiều dấu hiệu:

- Nhiều request cùng chờ một row, key hoặc index resource.
- CPU tổng thể không cao nhưng latency tăng khi concurrency tăng.
- Thêm worker không làm throughput tăng; đôi khi còn làm p95/p99 xấu hơn.
- Một câu UPDATE rất ngắn nhưng có nhiều session chờ.
- Một hàng bộ đếm hoặc trạng thái được cập nhật liên tục.
- Nhiều request cùng tạo một mã, cùng claim một job hoặc cùng xử lý một idempotency key.
- Transaction range scan giữ lock trên cùng một khoảng index.
- Chèn dữ liệu vào cuối một B-tree index gây page latch contention dù các key khác nhau.
- Deadlock hoặc lock timeout tăng trong giờ cao điểm.

Không phải mọi lock wait đều là điểm nóng. Một transaction quên COMMIT có thể chặn nhiều session dù tài nguyên chỉ bị truy cập ít. Một query thiếu index có thể khóa quá nhiều hàng. Cần xem tần suất, số waiter, thời gian chờ và resource cụ thể trước khi kết luận.

Một chỉ số hữu ích là throughput theo mức concurrency:

~~~text
Throughput
  ^
  |                  _________
  |              ___/
  |          ___/
  |      ___/
  |  ___/
  +----------------------------> Concurrent workers
                 |
                 +-- Điểm nóng bắt đầu giới hạn throughput
~~~

Khi thêm worker mà throughput gần như đứng yên, thời gian chờ tăng, hệ thống đang dành thêm thời gian xếp hàng để truy cập cùng tài nguyên.

## 2. Ba dạng hotspot thường gặp

| Dạng | Tài nguyên tranh chấp | Ví dụ | Dấu hiệu thường thấy |
|---|---|---|---|
| Hot row | Một record trong clustered/heap/index | Một hàng tồn kho, số dư, bộ đếm tổng | Nhiều lock wait trên cùng khóa chính |
| Hot unique key | Một giá trị trong unique index | Cùng email, mã đơn, idempotency key | Duplicate-key, chờ kiểm tra uniqueness |
| Hot index range | Một khoảng key hoặc các record trong range | Worker claim job theo trạng thái, cập nhật theo tenant/time | Gap/next-key/key-range lock, nhiều record bị chặn |
| Hot index page | Một trang B-tree hoặc cấu trúc nội bộ | Insert key tăng dần vào cuối index | Latch/mutex/page contention dù key khác nhau |

Một hệ thống có thể gặp nhiều dạng cùng lúc. Ví dụ bảng job có UNIQUE(job_key), index theo status và created_at, worker cùng claim một range READY. Nó có thể vừa có cạnh tranh trên một số job record, vừa có range lock, vừa có page contention khi cập nhật index.

## 3. Lock contention và latch contention khác nhau thế nào?

Đây là phân biệt quan trọng nhất khi điều tra điểm nóng.

### Lock contention

Lock điều phối các transaction để bảo vệ dữ liệu và isolation. Ví dụ transaction A UPDATE một hàng; transaction B UPDATE cùng hàng và phải chờ A COMMIT hoặc ROLLBACK.

Đặc điểm:

- Có quan hệ transaction giữ lock và transaction đang chờ.
- Có thể kéo dài trong suốt transaction.
- Có thể nhìn thấy qua lock manager hoặc catalog/Performance Schema/DMV.
- Giải quyết bằng transaction ngắn, giảm phạm vi lock, thứ tự lấy lock, schema/index phù hợp hoặc thay đổi mô hình ghi.

### Latch hoặc mutex contention

Latch/mutex bảo vệ cấu trúc nội bộ của database, ví dụ trang B-tree, buffer pool hoặc cấu trúc quản lý bộ nhớ. Nó thường được giữ trong thời gian rất ngắn để tránh hai thread sửa cấu trúc nội bộ đồng thời.

Đặc điểm:

- Không nhất thiết tương ứng với một transaction đang giữ row lock.
- Thường được giữ trong thời gian ngắn hơn transaction lock.
- Có thể xảy ra khi nhiều key khác nhau cùng rơi vào một trang index.
- Chẩn đoán qua wait event, latch/mutex instrumentation hoặc wait statistics.
- Giải quyết bằng thay đổi access pattern, index design, insert pattern, partitioning hoặc cấu hình phù hợp.

Ví dụ: 10.000 transaction chèn 10.000 ID khác nhau vào cùng vùng cuối của một B-tree. Không có duplicate key và không nhất thiết có row lock conflict, nhưng các thread vẫn có thể tranh chấp trang index hoặc latch nội bộ.

| Câu hỏi | Lock contention | Latch/page contention |
|---|---|---|
| Bảo vệ gì? | Tính nhất quán transaction | Cấu trúc dữ liệu nội bộ |
| Thời gian giữ | Có thể đến COMMIT/ROLLBACK | Thường rất ngắn |
| Có transaction blocker rõ ràng? | Thường có | Không nhất thiết |
| Ví dụ | Hai UPDATE cùng hàng | Nhiều INSERT vào cùng leaf page |
| Công cụ | Lock wait graph, transaction views | Wait events, latch/mutex statistics |

Không nên dùng cách sửa row lock để xử lý latch contention. Tăng lock timeout cũng không giải quyết được page latch hotspot.

## 4. Hot row: nhiều transaction cùng cập nhật một hàng

Một ví dụ kinh điển là bảng inventory:

~~~sql
CREATE TABLE inventory (
    product_id BIGINT NOT NULL PRIMARY KEY,
    available_quantity INT NOT NULL
) ENGINE = InnoDB;

INSERT INTO inventory (product_id, available_quantity)
VALUES (42, 100);
~~~

Nhiều request cùng mua sản phẩm 42. Mỗi request cần giảm available_quantity.

Một cách an toàn là cập nhật nguyên tử có điều kiện:

~~~sql
UPDATE inventory
SET available_quantity = available_quantity - 1
WHERE product_id = 42
  AND available_quantity > 0;
~~~

Database bảo đảm phép kiểm tra và phép trừ diễn ra như một statement nguyên tử. Ứng dụng kiểm tra affected rows:

- 1 row: đã giữ được một đơn vị.
- 0 row: không còn hàng hoặc product_id không tồn tại; cần phân biệt nếu nghiệp vụ yêu cầu.

Cách này tránh lỗi read-modify-write ở ứng dụng, nhưng **không loại bỏ hot-row contention**. Mọi request vẫn cần cập nhật cùng record, vì vậy database phải tuần tự hóa các thao tác ghi xung đột trên hàng đó.

Nếu 500 request cùng mua sản phẩm 42, chúng không thể đồng thời sửa cùng một giá trị balance theo cách không xung đột. Một số request sẽ chờ. Đây là giới hạn tự nhiên của một trạng thái được lưu trong một hàng duy nhất.

### 4.1. Thực nghiệm hai session

Dùng hai session MySQL InnoDB.

Session A:

~~~sql
START TRANSACTION;

UPDATE inventory
SET available_quantity = available_quantity - 1
WHERE product_id = 42
  AND available_quantity > 0;

-- Chưa COMMIT.
~~~

Session B:

~~~sql
START TRANSACTION;

UPDATE inventory
SET available_quantity = available_quantity - 1
WHERE product_id = 42
  AND available_quantity > 0;
~~~

UPDATE của B sẽ chờ lock trên hàng 42 do A đang giữ.

Khi A COMMIT:

~~~sql
COMMIT;
~~~

B có thể tiếp tục, đánh giá điều kiện trên trạng thái hiện hành và thực hiện cập nhật nếu quantity vẫn lớn hơn 0. Sau đó B COMMIT.

Thử nghiệm này cho thấy một statement ngắn có thể trở thành điểm tuần tự hóa nếu tất cả request cùng chạm một hàng.

## 5. Tại sao không nên đọc rồi ghi một giá trị tuyệt đối?

Giả sử quantity ban đầu là 10.

~~~text
Session A                         Session B
---------                         ---------
SELECT quantity = 10              SELECT quantity = 10
Tính 9                            Tính 9
UPDATE quantity = 9               UPDATE quantity = 9
COMMIT                            COMMIT
~~~

Nếu ứng dụng đọc giá trị rồi tính toán ở ngoài database và ghi một giá trị tuyệt đối, một cập nhật có thể ghi đè kết quả của cập nhật khác. Đây là lost update ở cấp logic.

Dùng UPDATE nguyên tử:

~~~sql
UPDATE inventory
SET available_quantity = available_quantity - 1
WHERE product_id = 42
  AND available_quantity > 0;
~~~

giúp database thực hiện phép tính trên giá trị hiện hành. Nhưng tất cả writer vẫn cạnh tranh cùng một hàng. Tính đúng và khả năng mở rộng là hai vấn đề riêng:

- UPDATE nguyên tử giải quyết tính đúng của phép cập nhật.
- Thay đổi mô hình dữ liệu hoặc phân phối ghi mới có thể giảm hotspot.

## 6. Cách giảm hot-row contention

Không có một kỹ thuật phù hợp cho mọi hàng nóng. Cần xem yêu cầu nhất quán, tốc độ ghi, cách đọc và khả năng chấp nhận dữ liệu trễ.

### 6.1. Rút ngắn transaction

Giữ lock càng ngắn càng tốt:

- Chỉ thực hiện thao tác cần thiết trong transaction.
- Không gọi HTTP API khi đang giữ row lock.
- Không gửi email hoặc chờ message broker trong transaction.
- Tránh đọc thêm dữ liệu không liên quan sau khi đã khóa hàng.
- Commit ngay khi bất biến nghiệp vụ đã được bảo vệ.

Ví dụ, không nên:

~~~text
BEGIN
  UPDATE inventory
  Call payment API
  Wait for external response
  Write audit
COMMIT
~~~

Một thiết kế tốt hơn thường chia quy trình thành trạng thái và event, dùng idempotency, Outbox hoặc Saga để xử lý phần ngoài database.

### 6.2. Giảm số lần ghi

Nếu mỗi request tăng một bộ đếm tổng, có thể gom nhiều increment thành một lần ghi theo batch. Ví dụ buffer event trong ứng dụng hoặc queue, sau đó cập nhật tổng theo lô.

Đánh đổi:

- Số lần cập nhật hàng nóng giảm.
- Giá trị tổng có thể trễ.
- Cần xử lý crash, retry và duplicate event.
- Cần định nghĩa rõ thời điểm số liệu phải chính xác tức thời.

Không batch nếu nghiệp vụ yêu cầu mỗi request phải được phản ánh ngay và có thể kiểm tra giới hạn dựa trên counter đó.

### 6.3. Chia bộ đếm thành nhiều bucket (striped counter)

Nếu một counter chỉ cần tổng hợp khi đọc, thay vì một hàng duy nhất, có thể chia thành nhiều bucket:

~~~sql
CREATE TABLE counter_shards (
    counter_name VARCHAR(100) NOT NULL,
    shard_id INT NOT NULL,
    counter_value BIGINT NOT NULL,
    PRIMARY KEY (counter_name, shard_id)
) ENGINE = InnoDB;
~~~

Mỗi writer chọn một shard trong số N shard:

~~~sql
UPDATE counter_shards
SET counter_value = counter_value + 1
WHERE counter_name = 'page_views'
  AND shard_id = 3;
~~~

Đọc tổng:

~~~sql
SELECT SUM(counter_value) AS total_views
FROM counter_shards
WHERE counter_name = 'page_views';
~~~

Thay vì tất cả writer cập nhật một hàng, chúng phân tán trên nhiều hàng. Nếu chọn shard tương đối đều, contention có thể giảm.

Cần cân nhắc:

- Chọn shard bằng hash ổn định hoặc phân phối ngẫu nhiên phù hợp.
- Một shard vẫn có thể nóng nếu phân phối lệch.
- Đọc tổng tốn nhiều phép cộng hơn.
- Reset hoặc rollover counter phải xử lý đồng bộ.
- Nếu counter dùng để kiểm soát quota tức thời, tổng hợp trễ hoặc cập nhật phân tán có thể làm vượt quota.

Striped counter phù hợp với metric, view count hoặc thống kê có thể tổng hợp. Không dùng trực tiếp cho số dư tiền hoặc giới hạn tồn kho nếu việc chia bucket làm mất bất biến toàn cục.

### 6.4. Phân vùng theo tenant hoặc tài nguyên

Nếu một hàng tổng hợp toàn hệ thống được cập nhật bởi mọi tenant, có thể lưu trạng thái riêng theo tenant hoặc theo nhóm tài nguyên:

~~~sql
CREATE TABLE tenant_counters (
    tenant_id BIGINT NOT NULL PRIMARY KEY,
    request_count BIGINT NOT NULL
);
~~~

Các request thuộc tenant khác nhau cập nhật các hàng khác nhau. Phạm vi contention được chia theo tenant.

Nếu một tenant đơn lẻ có tải rất cao, partition theo tenant chưa đủ; có thể cần nhiều bucket trong tenant đó.

### 6.5. Dùng queue hoặc single-writer cho tài nguyên thực sự cần tuần tự

Một số nghiệp vụ cần thứ tự xử lý rõ ràng trên một tài nguyên, ví dụ cấp số thứ tự hoặc cập nhật một aggregate có invariant phức tạp. Có thể đưa yêu cầu vào queue và dùng một consumer hoặc một nhóm consumer có partition key theo resource.

Ưu điểm:

- Thứ tự xử lý có thể được kiểm soát.
- Có thể gom batch.
- Giảm số transaction tranh chấp trực tiếp.

Đánh đổi:

- Queue trở thành nơi xếp hàng.
- Cần bảo đảm message idempotent.
- Throughput của một partition/single-writer vẫn có giới hạn.
- Latency tăng nếu backlog lớn.
- Cần xử lý poison message và retry.

Queue không làm biến mất giới hạn của một tài nguyên tuần tự; nó làm hàng đợi rõ ràng và có thể kiểm soát tốt hơn.

## 7. Hot row trong số dư tài khoản và tồn kho

Không nên chia nhỏ mọi hot row một cách máy móc. Một số trạng thái phải có một giá trị nhất quán duy nhất.

### Số dư tài khoản

Nếu balance của một tài khoản là invariant tài chính, các thao tác debit/credit cần tuần tự hóa trên tài khoản đó hoặc dùng một ledger có quy tắc cộng dồn và kiểm tra số dư rõ ràng.

Một mô hình phổ biến là ghi các entry bất biến vào ledger:

~~~sql
CREATE TABLE account_entries (
    entry_id BIGINT NOT NULL PRIMARY KEY,
    account_id BIGINT NOT NULL,
    amount DECIMAL(18, 2) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_account_created (account_id, created_at)
);
~~~

Ledger append-only giảm việc cập nhật cùng một hàng balance cho mỗi giao dịch. Nhưng nếu cần ngăn số dư âm, hệ thống vẫn phải có cơ chế đồng bộ/kiểm soát tổng số dư, ví dụ account guard row, hạn mức được phân bổ hoặc transaction theo tài khoản.

Có thể duy trì balance projection để đọc nhanh, cập nhật cùng transaction với ledger. Khi đó hàng balance vẫn có thể nóng. Mục tiêu là tách lịch sử bất biến khỏi projection và chọn chiến lược concurrency đúng cho invariant tài chính.

### Tồn kho

Nếu cần bảo đảm không bán vượt tồn kho, điều kiện phải được kiểm tra nguyên tử:

~~~sql
UPDATE inventory
SET available_quantity = available_quantity - 1
WHERE product_id = 42
  AND available_quantity >= 1;
~~~

Nếu số lượng rất lớn và một sản phẩm cực kỳ nóng, có thể phân bổ quota tồn kho cho các bucket/warehouse/region. Mỗi bucket có quota riêng, tổng quota không vượt tổng tồn kho. Cách này phân tán ghi nhưng làm phức tạp luồng chuyển quota, hoàn hàng và xử lý bucket hết quota.

Không nên dùng eventual consistency đơn giản cho hàng tồn kho nếu nghiệp vụ không chấp nhận oversell.

## 8. Hot unique key: nhiều transaction tranh chấp cùng một giá trị duy nhất

Một unique index bảo đảm không có hai hàng cùng business key. Nhưng khi nhiều transaction cùng INSERT một giá trị, chúng phải được điều phối.

Ví dụ:

~~~sql
CREATE TABLE idempotency_keys (
    tenant_id BIGINT NOT NULL,
    request_key VARCHAR(100) NOT NULL,
    request_hash CHAR(64) NOT NULL,
    result_id BIGINT,
    PRIMARY KEY (tenant_id, request_key)
) ENGINE = InnoDB;
~~~

Hai request cùng gửi (tenant_id = 7, request_key = K-123).

~~~text
Transaction A                         Transaction B
-------------                         -------------
INSERT (7, K-123)                     INSERT (7, K-123)
Đang giữ unique entry                 Chờ kết quả của A
COMMIT                                Nhận duplicate-key
~~~

Nếu A commit, B không thể tạo hàng thứ hai. Nếu A rollback, B có thể tiếp tục INSERT và trở thành transaction thắng.

Đây không phải lỗi của unique index. Đây là cơ chế database bảo vệ invariant. Nhưng nếu một key được nhiều request cùng sử dụng, nó có thể trở thành điểm nóng với lock wait hoặc duplicate-key tăng cao.

### 8.1. Khi nào đây là hành vi mong muốn?

Nếu nhiều request là retry của cùng một thao tác, chỉ một thao tác nên được thực hiện. Unique key trên idempotency key là cơ chế đúng để deduplicate.

Ứng dụng cần:

1. Dùng idempotency key ổn định cho cùng một ý định.
2. Lưu request hash hoặc fingerprint.
3. Nếu cùng key và cùng payload, trả lại kết quả đã lưu.
4. Nếu cùng key nhưng payload khác, trả conflict.
5. Nếu transaction đầu tiên còn xử lý, request sau chờ hoặc nhận trạng thái đang xử lý theo API contract.
6. Không chạy lại side effect trước khi xác định request có phải duplicate không.

### 8.2. Khi nào unique-key contention là dấu hiệu thiết kế chưa tốt?

Ví dụ một mã chung được dùng cho mọi request:

~~~text
request_key = "DEFAULT"
~~~

Nếu mọi request đều INSERT cùng một key, chúng sẽ tranh chấp cùng một entry. Có thể key đang bị tạo sai phạm vi. Nếu idempotency key phải duy nhất theo client request, hãy tạo một key riêng cho từng ý định, không dùng một giá trị chung.

Tuy nhiên, không được tạo key ngẫu nhiên mới cho mỗi retry của cùng một ý định. Điều đó phá hỏng idempotency. Key cần vừa phân biệt các ý định độc lập, vừa ổn định qua retry của cùng ý định.

## 9. Phân biệt duplicate-key conflict với index-page hotspot

Hai tình huống có vẻ giống nhau nhưng nguyên nhân khác:

### Duplicate-key conflict

Hai transaction cố tạo cùng một giá trị duy nhất. Một transaction có thể phải chờ transaction kia commit/rollback; sau đó nhận duplicate-key hoặc tiếp tục nếu transaction trước rollback.

Dấu hiệu:

- Error 1062 ở MySQL.
- SQLSTATE 23505 ở PostgreSQL.
- Error 2601/2627 ở SQL Server.
- Lock wait liên quan đến unique index entry.

### Index-page/latch hotspot

Nhiều transaction chèn các key khác nhau nhưng các key rơi vào cùng một trang B-tree hoặc vùng index nóng. Không có duplicate business key, nhưng thread vẫn tranh chấp latch/mutex hoặc page-level synchronization.

Ví dụ:

~~~text
Index tăng dần:

... 1001, 1002, 1003, 1004, 1005, 1006
                                      ^
                                nhiều INSERT mới
                                cùng chạm trang cuối
~~~

Đây có thể là điểm nóng ở rightmost leaf page. Khác với unique conflict, mỗi key đều khác nhau và tất cả INSERT có thể hợp lệ.

Để xử lý, phải xác định wait thực tế là transaction lock hay latch/page wait. Chỉ thêm unique constraint không giải quyết page latch. Ngược lại, đổi kiểu ID để giảm page contention không giải quyết duplicate business key.

## 10. Hot index range: nhiều transaction cùng truy cập một khoảng

Một truy vấn range có thể trở thành điểm nóng nếu nhiều transaction cùng khóa hoặc cập nhật cùng một khoảng index.

Ví dụ bảng jobs:

~~~sql
CREATE TABLE jobs (
    job_id BIGINT NOT NULL PRIMARY KEY,
    status VARCHAR(20) NOT NULL,
    priority INT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    KEY idx_status_priority_created
        (status, priority, created_at)
) ENGINE = InnoDB;
~~~

Nhiều worker cùng tìm job READY có priority cao:

~~~sql
SELECT job_id
FROM jobs
WHERE status = 'READY'
ORDER BY priority DESC, created_at
LIMIT 10
FOR UPDATE;
~~~

Nếu mọi worker quét cùng một vùng index READY, chúng có thể cạnh tranh trên các record và gap được khóa. Tùy isolation level, index và plan, InnoDB có thể sử dụng record/next-key locks trên vùng quét.

Một query trả về 10 job không có nghĩa chỉ 10 index entry đã được truy cập hoặc khóa. Cần xem execution plan và lock instrumentation.

### 10.1. Thực nghiệm range contention trong InnoDB

Chuẩn bị dữ liệu:

~~~sql
DROP TABLE IF EXISTS jobs_lab;

CREATE TABLE jobs_lab (
    job_id BIGINT NOT NULL PRIMARY KEY,
    status VARCHAR(20) NOT NULL,
    priority INT NOT NULL,
    created_at DATETIME NOT NULL,
    KEY idx_status_priority (status, priority, job_id)
) ENGINE = InnoDB;

INSERT INTO jobs_lab (job_id, status, priority, created_at)
VALUES
    (1, 'READY', 100, '2026-11-14 10:00:00'),
    (2, 'READY', 90,  '2026-11-14 10:01:00'),
    (3, 'READY', 80,  '2026-11-14 10:02:00'),
    (4, 'DONE',  70,  '2026-11-14 10:03:00');
~~~

Session A ở REPEATABLE READ:

~~~sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT job_id
FROM jobs_lab
WHERE status = 'READY'
  AND priority >= 80
FOR UPDATE;
~~~

Session B thử chèn một job mới vào vùng liên quan:

~~~sql
START TRANSACTION;

INSERT INTO jobs_lab (job_id, status, priority, created_at)
VALUES (5, 'READY', 85, '2026-11-14 10:04:00');
~~~

Tùy execution plan và phạm vi index được quét, INSERT có thể phải chờ gap/next-key lock của A. Quan sát bằng Performance Schema rồi kết thúc transaction A để giải phóng wait.

Đây là ví dụ về range locking. Không nên giả định một lock mode hay đúng một khoảng cụ thể chỉ từ WHERE; cần xem index thực tế và lock data.

### 10.2. Vì sao range hotspot dễ xuất hiện?

- Nhiều worker cùng dùng một predicate như status = 'READY'.
- Một range scan khóa nhiều index entry hơn số hàng trả về.
- Index thiếu cột lọc hoặc thứ tự cột không phù hợp.
- Transaction giữ FOR UPDATE trong lúc xử lý job lâu.
- Nhiều request cùng cập nhật một tenant/time range.
- Range chứa một tỷ lệ lớn dữ liệu hoạt động.

## 11. Giảm contention trên index range

### 11.1. Thu hẹp phạm vi scan bằng index

Index nên hỗ trợ điều kiện lọc và thứ tự truy cập.

Ví dụ:

~~~sql
KEY idx_status_priority (status, priority, job_id)
~~~

có thể giúp truy cập vùng status và priority. Nhưng thứ tự cột cần dựa vào query workload và cách optimizer sử dụng B-tree.

Dùng EXPLAIN để xem key, access type, estimated rows và thứ tự truy cập. Đo lock thực tế sau khi thay đổi index.

### 11.2. Chia phạm vi theo tenant hoặc partition key

Thay vì mọi worker cùng claim toàn bộ READY jobs, chia theo tenant, queue name, region hoặc hash bucket:

~~~sql
SELECT job_id
FROM jobs
WHERE tenant_id = 7
  AND status = 'READY'
ORDER BY priority DESC, created_at
LIMIT 10
FOR UPDATE;
~~~

Nếu workload cho phép, worker có thể nhận một tenant hoặc partition khác nhau. Phạm vi truy cập ít chồng lấn hơn.

### 11.3. Dùng SKIP LOCKED cho hàng đợi

MySQL 8 hỗ trợ:

~~~sql
START TRANSACTION;

SELECT job_id
FROM jobs
WHERE status = 'READY'
ORDER BY priority DESC, created_at
LIMIT 10
FOR UPDATE SKIP LOCKED;

-- Đánh dấu các job đã claim trong cùng transaction.
UPDATE jobs
SET status = 'RUNNING'
WHERE job_id IN (/* các ID vừa chọn */);

COMMIT;
~~~

Worker bỏ qua các record đã bị worker khác khóa, thay vì chờ cùng một job.

PostgreSQL cũng hỗ trợ FOR UPDATE SKIP LOCKED. SQL Server có thể triển khai queue pattern bằng lock hints như UPDLOCK, READPAST và ROWLOCK trong một thiết kế phù hợp.

Cần hiểu các giới hạn:

- SKIP LOCKED có thể làm worker bỏ qua job đang bị khóa lâu.
- Thứ tự xử lý thực tế có thể khác thứ tự ưu tiên toàn cục.
- Job bị khóa lâu có thể bị trì hoãn.
- Không dùng SKIP LOCKED cho truy vấn cần kết quả đầy đủ hoặc báo cáo nhất quán.
- Claim và đổi trạng thái phải nằm trong cùng transaction để tránh worker khác lấy cùng job.
- Cần cơ chế lease/recovery cho job worker chết sau khi claim.

### 11.4. Chia queue thành nhiều partition

Có thể phân chia queue theo hash hoặc tenant để giảm số worker cùng chạm một range. Cần cân nhắc khả năng mất cân bằng: một tenant lớn có thể trở thành hot partition.

### 11.5. Giữ transaction claim thật ngắn

Claim job trong transaction, commit ngay, rồi xử lý công việc bên ngoài transaction. Khi xử lý xong, cập nhật trạng thái bằng transaction riêng.

Không giữ FOR UPDATE trong lúc gọi API hoặc chạy tác vụ dài. Nếu cần bảo vệ quyền sở hữu job trong thời gian xử lý, dùng lease_until, worker_id và token/version để phát hiện worker hết hạn hoặc mất quyền sở hữu.

## 12. Key-range lock và gap lock khác nhau theo database

Cùng một truy vấn range có thể tạo locking behavior khác nhau.

| Database | Cơ chế liên quan | Lưu ý |
|---|---|---|
| MySQL InnoDB | Record, gap, next-key lock | Ở REPEATABLE READ, locking range scan có thể khóa record và gap; READ COMMITTED giảm gap locking cho search thông thường |
| SQL Server | Key-range lock ở SERIALIZABLE | HOLDLOCK có thể áp dụng semantics SERIALIZABLE cho table reference; index và plan ảnh hưởng phạm vi |
| PostgreSQL | Predicate lock/SIREAD trong SERIALIZABLE | SIREAD thường không chặn writer trực tiếp; SSI phát hiện xung đột và có thể abort transaction |
| PostgreSQL READ COMMITTED | Row/table locks theo statement | SELECT thông thường không có gap lock tổng quát để khóa row chưa tồn tại |

Trong PostgreSQL SERIALIZABLE, predicate lock là thông tin để phát hiện serialization conflict, không tương đương gap lock của InnoDB. Một transaction có thể không bị block ngay nhưng về sau nhận serialization failure.

Trong SQL Server, key-range lock là lock thực sự bảo vệ khoảng index khi dùng SERIALIZABLE. Với index phù hợp, database có thể khóa khoảng key để ngăn phantom insert.

Không chuyển một giải pháp locking từ database này sang database khác chỉ bằng cách giữ nguyên tên isolation level.

## 13. Hot index page do key tăng dần

Một dạng hotspot khác xuất hiện khi phần lớn INSERT tạo key lớn hơn mọi key hiện có, ví dụ ID tăng dần.

B-tree cần chèn các entry theo thứ tự. Nếu các giá trị mới liên tục nằm ở cuối index, nhiều thread cùng sửa rightmost leaf page. Engine có thể phải đồng bộ truy cập trang đó.

Ví dụ:

~~~text
B-tree leaf pages:

[1 ... 100] [101 ... 200] [201 ... 300]
                                      ^
                                phần lớn INSERT mới
                                đi vào trang cuối
~~~

Đây là page/latch contention, khác với nhiều transaction INSERT cùng một giá trị unique.

### 13.1. Auto-increment và sequence

Auto-increment hoặc sequence vẫn là lựa chọn tốt trong nhiều workload. Không nên thay đổi chỉ vì có giả thuyết về hotspot.

Cần đo trước:

- Wait event có phải latch/page contention không?
- Có nhiều insert vào cùng index không?
- Có phải insert bottleneck thực sự nằm ở log flush, disk hoặc foreign key?
- Throughput có giảm theo concurrency không?

MySQL InnoDB có cơ chế quản lý AUTO_INCREMENT với các lock mode/configuration khác nhau. SQL Server có thể gặp last-page insert contention trên index tăng dần. PostgreSQL sequence cấp giá trị độc lập với transaction và không rollback giá trị đã cấp; index vẫn có thể có page-level contention ở điểm chèn.

### 13.2. UUID ngẫu nhiên có phải luôn tốt hơn?

UUID ngẫu nhiên phân tán vị trí chèn trong B-tree, có thể giảm điểm nóng ở trang cuối. Nhưng nó cũng có đánh đổi:

- Chèn rải rác làm tăng random I/O.
- Page split và fragmentation có thể tăng.
- Khóa lớn hơn integer làm index và foreign key tốn không gian.
- Cache locality có thể kém hơn.

UUID có thứ tự thời gian như UUIDv7 cải thiện locality so với UUID hoàn toàn ngẫu nhiên, nhưng vẫn có thể tập trung insert vào vùng mới nhất. Nó không đảm bảo xóa bỏ mọi page hotspot.

Chọn key dựa trên workload, kích thước index, locality và yêu cầu phân tán ID. Đo trên dữ liệu và concurrency gần production.

### 13.3. Một số hướng giảm rightmost-page contention

- Batch insert để giảm overhead mỗi row.
- Dùng partitioning hoặc nhiều index bucket nếu mô hình dữ liệu cho phép.
- Chọn key distribution phù hợp với workload.
- Giảm số secondary index phải cập nhật trên mỗi INSERT.
- Kiểm tra fill factor/page split với engine có hỗ trợ cấu hình phù hợp.
- Cân nhắc sequence cache hoặc allocation block khi phù hợp.
- Đo lại insert throughput và chi phí đọc sau thay đổi.

Không dùng key ngẫu nhiên nếu truy vấn range theo thời gian và locality là yêu cầu quan trọng mà chưa đo tác động.

## 14. Đo và chẩn đoán hotspot trong MySQL InnoDB

### 14.1. Tìm lock wait trên record/index

MySQL 8:

~~~sql
SELECT
    w.REQUESTING_ENGINE_TRANSACTION_ID AS waiting_trx,
    req.OBJECT_SCHEMA,
    req.OBJECT_NAME,
    req.INDEX_NAME,
    req.LOCK_MODE AS waiting_lock_mode,
    req.LOCK_DATA AS waiting_lock_data,
    w.BLOCKING_ENGINE_TRANSACTION_ID AS blocking_trx,
    blk.LOCK_MODE AS blocking_lock_mode,
    blk.LOCK_DATA AS blocking_lock_data
FROM performance_schema.data_lock_waits AS w
JOIN performance_schema.data_locks AS req
  ON req.ENGINE = w.ENGINE
 AND req.ENGINE_LOCK_ID = w.REQUESTING_ENGINE_LOCK_ID
JOIN performance_schema.data_locks AS blk
  ON blk.ENGINE = w.ENGINE
 AND blk.ENGINE_LOCK_ID = w.BLOCKING_ENGINE_LOCK_ID;
~~~

Nhóm kết quả theo table/index/lock data để xem một resource có lặp lại thường xuyên không.

### 14.2. Xem transaction mở lâu

~~~sql
SELECT
    trx_id,
    trx_state,
    trx_started,
    TIMESTAMPDIFF(SECOND, trx_started, NOW()) AS trx_age_seconds,
    trx_mysql_thread_id AS connection_id,
    trx_rows_locked,
    trx_rows_modified,
    trx_query
FROM information_schema.innodb_trx
ORDER BY trx_started;
~~~

Transaction lâu có thể giữ lock trên hàng nóng dù query đã hoàn tất và session Sleep.

### 14.3. Xem wait instrumentation

Performance Schema có các bảng wait summary và history. Có thể kiểm tra các event đồng bộ nội bộ:

~~~sql
SELECT
    EVENT_NAME,
    COUNT_STAR,
    SUM_TIMER_WAIT,
    AVG_TIMER_WAIT,
    MAX_TIMER_WAIT
FROM performance_schema.events_waits_summary_global_by_event_name
WHERE EVENT_NAME LIKE 'wait/synch/%'
ORDER BY SUM_TIMER_WAIT DESC
LIMIT 30;
~~~

Các instrument phải được bật để có dữ liệu. Không phải mọi event đứng đầu đều là hotspot của ứng dụng; cần liên hệ với workload, thời gian và các chỉ số khác.

### 14.4. Xem execution plan

~~~sql
EXPLAIN
SELECT job_id
FROM jobs_lab
WHERE status = 'READY'
  AND priority >= 80
FOR UPDATE;
~~~

Xem index được chọn, access type, rows ước lượng và điều kiện lọc. Một range scan rộng có thể làm lock footprint lớn hơn mong muốn.

### 14.5. Đọc InnoDB status

~~~sql
SHOW ENGINE INNODB STATUS;
~~~

Phần TRANSACTIONS cho biết lock wait và transaction đang hoạt động. Phần SEMAPHORES có thể cung cấp dấu hiệu về contention nội bộ, nhưng cần diễn giải cùng phiên bản và workload.

## 15. PostgreSQL: phân biệt lock wait với LWLock/buffer contention

### 15.1. Tìm session đang chờ lock

~~~sql
SELECT
    a.pid,
    a.usename,
    a.application_name,
    a.state,
    a.wait_event_type,
    a.wait_event,
    a.xact_start,
    now() - a.xact_start AS transaction_age,
    pg_blocking_pids(a.pid) AS blockers,
    a.query
FROM pg_stat_activity AS a
WHERE a.wait_event_type = 'Lock'
ORDER BY a.xact_start;
~~~

Nếu wait_event_type là Lock, xem blocker bằng pg_blocking_pids và lock catalog.

### 15.2. Tìm wait nội bộ

Nếu wait_event_type là LWLock, BufferPin hoặc một wait event khác, đây có thể là tranh chấp tài nguyên nội bộ thay vì transaction lock thông thường.

Xem các wait event đang xuất hiện:

~~~sql
SELECT
    wait_event_type,
    wait_event,
    COUNT(*) AS session_count
FROM pg_stat_activity
WHERE wait_event IS NOT NULL
GROUP BY wait_event_type, wait_event
ORDER BY session_count DESC;
~~~

### 15.3. Theo dõi câu SQL nóng

Nếu có pg_stat_statements:

~~~sql
SELECT
    queryid,
    calls,
    total_exec_time,
    mean_exec_time,
    rows,
    query
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
~~~

Cần kết hợp calls, mean latency, wait events và số lần chạy. Một câu SQL có tổng thời gian lớn có thể chỉ do chạy rất nhiều lần; chưa chắc nó là điểm nóng duy nhất.

PostgreSQL không biểu diễn mọi row lock như một tuple độc lập trong pg_locks. Khi transaction chờ row lock, wait có thể xuất hiện dưới dạng transaction ID lock. Dùng pg_blocking_pids để tìm blocker trực tiếp thay vì tự suy luận chỉ từ lock catalog.

## 16. SQL Server: LCK_M khác PAGELATCH

SQL Server cung cấp wait statistics giúp phân biệt transaction lock với page latch.

### 16.1. Lock wait

Các wait type thường gặp:

- LCK_M_S
- LCK_M_U
- LCK_M_X
- LCK_M_IS
- LCK_M_IX

Chúng biểu thị request đang chờ lock mode tương ứng.

Tìm request đang chờ:

~~~sql
SELECT
    session_id,
    blocking_session_id,
    wait_type,
    wait_time,
    wait_resource,
    status,
    command
FROM sys.dm_exec_requests
WHERE wait_type LIKE 'LCK_M_%'
ORDER BY wait_time DESC;
~~~

### 16.2. Page latch wait

Các wait type như PAGELATCH_EX hoặc PAGELATCH_UP thường liên quan đến tranh chấp latch trong memory trên page. Chúng có thể xuất hiện với last-page insert contention.

PAGEIOLATCH_* thường liên quan đến chờ I/O để đưa page vào buffer pool; đây là vấn đề khác với PAGELATCH contention trên page đã ở memory.

~~~sql
SELECT
    session_id,
    wait_type,
    wait_time,
    wait_resource,
    blocking_session_id
FROM sys.dm_exec_requests
WHERE wait_type LIKE 'PAGELATCH%'
   OR wait_type LIKE 'PAGEIOLATCH%'
ORDER BY wait_time DESC;
~~~

### 16.3. Theo dõi wait statistics

~~~sql
SELECT TOP (30)
    wait_type,
    waiting_tasks_count,
    wait_time_ms,
    signal_wait_time_ms
FROM sys.dm_os_wait_stats
WHERE wait_type LIKE 'LCK_M_%'
   OR wait_type LIKE 'PAGELATCH%'
   OR wait_type LIKE 'PAGEIOLATCH%'
ORDER BY wait_time_ms DESC;
~~~

Wait stats thường tích lũy từ lần reset hoặc lần khởi động gần nhất. Cần lấy baseline và so sánh delta trong khoảng thời gian xác định; đừng coi tổng tích lũy là tình trạng hiện tại.

## 17. Chọn giải pháp theo loại điểm nóng

| Nguyên nhân | Hướng xử lý | Đánh đổi cần hiểu |
|---|---|---|
| Một counter row bị ghi liên tục | Striped counter, batch, queue | Đọc tổng tốn thêm; có thể eventual consistency |
| Một inventory row bị ghi liên tục | Atomic conditional UPDATE, quota bucket, phân bổ tồn kho | Phải bảo toàn invariant không oversell |
| Một account balance bị ghi liên tục | Ledger, account-level serialization, partition theo account | Tính đúng tài chính và thứ tự giao dịch vẫn cần bảo vệ |
| Nhiều request cùng idempotency key | Deduplicate, trả kết quả cũ, lưu request hash | Cùng key nhưng payload khác phải conflict |
| Unique key được tạo sai phạm vi | Thiết kế lại business key và unique constraint | Cần migration dữ liệu cũ |
| Nhiều worker khóa cùng queue range | SKIP LOCKED/READPAST, partition queue, claim nhanh | Có thể bỏ qua job đang khóa và thay đổi fairness |
| Range scan khóa quá rộng | Index phù hợp, predicate hẹp, transaction ngắn | Thêm index tăng chi phí ghi |
| B-tree rightmost page nóng | Batch, key distribution, partition/index design | UUID ngẫu nhiên có thể tăng fragmentation |
| Page latch/mutex contention | Đo wait nội bộ, giảm tập trung page, giảm index maintenance | Không giải quyết bằng lock timeout |
| Transaction giữ lock quá lâu | Thu hẹp transaction, bỏ external I/O khỏi transaction | Cần thiết kế state machine/outbox |

## 18. Không nên giải quyết hotspot bằng cách tăng timeout

Tăng lock wait timeout có thể làm request chờ lâu hơn trước khi thất bại. Nó không làm tài nguyên nóng xử lý nhanh hơn.

Nếu một hàng chỉ có thể được cập nhật tuần tự, tăng timeout có thể làm hàng đợi dài hơn và giữ nhiều connection hơn.

Cần xác định:

- Tài nguyên nào đang nóng?
- Có bao nhiêu transaction cùng chờ?
- Thời gian giữ lock là bao lâu?
- Có transaction mở lâu hoặc idle không?
- Throughput có bị giới hạn bởi một hàng hay một index page?
- Chờ là transaction lock, latch, I/O hay log flush?
- Có thể phân tán ghi mà vẫn giữ invariant không?

Timeout có thể được cấu hình như giới hạn bảo vệ request, nhưng không phải biện pháp chữa gốc cho hotspot.

## 19. Kiểm thử hotspot bằng tải đồng thời

Một query chạy đơn lẻ không đủ để đánh giá contention. Cần test với nhiều connection và mức concurrency tăng dần.

### Kịch bản test

1. Chuẩn bị dữ liệu và index tương tự production.
2. Tạo workload chỉ cập nhật một hàng nóng.
3. Tạo workload cập nhật nhiều hàng độc lập làm baseline.
4. Tạo workload insert các key duy nhất tăng dần.
5. Tạo workload insert key phân tán.
6. Tạo workload range scan/claim cùng một khoảng.
7. Tăng worker theo các mức cố định.
8. Đo throughput, p50/p95/p99, lock wait, latch wait, deadlock và CPU.
9. Lặp lại sau mỗi thay đổi schema hoặc code.
10. Xác nhận invariant nghiệp vụ không bị phá vỡ.

### Ma trận so sánh

| Workload | Mục tiêu quan sát |
|---|---|
| 1 hàng, 1 worker | Baseline latency |
| 1 hàng, nhiều worker | Hot-row serialization |
| Nhiều hàng độc lập, nhiều worker | Khả năng chạy song song bình thường |
| Nhiều key khác nhau, cùng index | Index-page contention |
| Cùng unique key, nhiều worker | Unique conflict và duplicate handling |
| Cùng range, nhiều locking read | Range/gap/key-range contention |
| Nhiều range không chồng nhau | Hiệu quả partitioning |

### Chỉ số nên ghi nhận

- Transactions/second.
- Rows affected/second.
- p50, p95, p99 latency.
- Số lock waits và tổng thời gian chờ.
- Deadlock count.
- Duplicate-key count.
- Latch/mutex wait time.
- CPU, I/O và log flush latency.
- Số connection active/idle.
- Transaction duration và transaction age.

Kết quả cần được đo trên cùng dữ liệu, cùng phần cứng, cùng cấu hình và cùng thời gian warm-up. Một thay đổi giảm lock wait nhưng làm tăng I/O hoặc retry có thể không cải thiện throughput tổng thể.

## 20. Các lỗi thiết kế thường gặp

**Cập nhật một hàng tổng hợp cho mọi request.**

Một hàng global counter, last_seen hoặc system status có thể thành điểm nóng. Hãy xem có thể chia theo tenant/bucket hoặc tổng hợp theo batch không.

**Dùng một idempotency key chung cho nhiều request.**

Key chung khiến mọi request cạnh tranh cùng unique entry. Key phải đại diện cho một ý định cụ thể và ổn định qua retry của ý định đó.

**Chạy SELECT FOR UPDATE trên một range rộng rồi gọi API bên ngoài.**

Transaction giữ lock trong lúc chờ mạng. Hãy claim ngắn, commit, xử lý bên ngoài, sau đó cập nhật trạng thái bằng transaction mới.

**Thêm index mà không kiểm tra lock footprint.**

Index mới có thể thu hẹp scan, nhưng mỗi index cũng tăng chi phí ghi và có thể tạo thêm resource contention.

**Dùng UUID ngẫu nhiên chỉ vì nghe nói giảm hotspot.**

Có thể giảm rightmost-page contention nhưng tăng page split, random I/O và kích thước index. Phải đo workload đọc/ghi thực tế.

**Dùng optimistic locking trên một hàng cực nóng và kỳ vọng throughput tăng.**

Optimistic locking chuyển blocking thành conflict/retry. Khi mọi request đều cập nhật cùng hàng, tỷ lệ retry có thể tăng mạnh mà throughput không tăng.

**Dùng SKIP LOCKED cho dữ liệu cần đầy đủ.**

SKIP LOCKED phù hợp với queue claim, không phù hợp với báo cáo hoặc nghiệp vụ cần toàn bộ bản ghi trong range.

**Chia counter nhưng không định nghĩa độ chính xác.**

Striped counter có thể làm tổng đọc trễ hoặc cần cộng nhiều bucket. Không dùng cho invariant tài chính/tồn kho nếu chưa có cơ chế bảo vệ tổng.

**Kill session mà chưa xác định transaction owner.**

Có thể rollback một transaction lớn và gây thêm tải. Hãy xác định root cause, ownership và tác động trước khi can thiệp.

## 21. Quy trình xử lý incident hotspot

Khi latency tăng do contention:

1. Xác định câu SQL và endpoint có p95/p99 tăng.
2. Phân loại wait: transaction lock, latch/page, I/O, log flush hay CPU.
3. Nếu là lock, tìm waiter, blocker, resource và transaction age.
4. Nhóm các wait theo row/key/index/table để tìm resource lặp lại.
5. Xem execution plan và phạm vi index được truy cập.
6. Xác định hotspot là một hàng, một unique value, một range hay một page.
7. Kiểm tra transaction có gọi external service hoặc giữ lock lâu không.
8. Chọn giải pháp theo invariant: rút ngắn transaction, atomic update, bucket, queue, index, partition hoặc thay đổi key.
9. Kiểm thử với concurrency tăng dần.
10. So sánh throughput và latency trước/sau.
11. Xác nhận không có lost update, duplicate, oversell hoặc vi phạm thứ tự nghiệp vụ.
12. Theo dõi retry, deadlock, wait time và dữ liệu sau triển khai.

Không tối ưu chỉ dựa trên một snapshot. Hotspot thường phụ thuộc thời điểm, skew dữ liệu và phân phối request. Cần đo đủ lâu để bắt được peak load và key nóng thực tế.

## Kết luận

Điểm nóng xảy ra khi nhiều transaction cùng tranh chấp một hàng, một giá trị unique hoặc một vùng index. Hot row thường tạo transaction lock wait; hot unique key có thể tạo duplicate conflict và chờ uniqueness check; hot index range có thể tạo gap/next-key/key-range lock. Insert vào cùng trang B-tree có thể tạo latch/page contention dù các key hoàn toàn khác nhau.

Hãy phân loại đúng tài nguyên trước khi tối ưu. Transaction lock cần giảm thời gian giữ lock, thu hẹp phạm vi scan và bảo vệ invariant bằng câu lệnh nguyên tử hoặc constraint phù hợp. Một hàng tổng hợp có thể được chia thành bucket hoặc batch nếu nghiệp vụ cho phép. Queue và SKIP LOCKED phù hợp với workload claim công việc. Page/latch contention cần quan sát wait nội bộ và thiết kế lại access pattern hoặc index.

Mỗi giải pháp có đánh đổi về tính nhất quán, latency, chi phí index, độ phức tạp retry và cách tổng hợp dữ liệu. Kiểm thử bằng nhiều connection, đo throughput cùng p95/p99 và xác nhận invariant sau tải là cách đáng tin cậy để biết điểm nóng đã được xử lý hay chỉ chuyển sang một tài nguyên khác.
