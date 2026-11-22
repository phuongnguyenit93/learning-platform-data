# Kiểm thử kết quả cuối, kết quả từng yêu cầu và số giao dịch xác nhận

Kiểm thử đồng thời không thể chỉ nhìn vào một giá trị cuối cùng rồi kết luận hệ thống đúng. Một bài test có thể cho số dư hoặc tồn kho cuối đúng nhưng vẫn trả kết quả sai cho một số request; ngược lại, từng request có thể nhận response thành công nhưng dữ liệu cuối bị ghi trùng hoặc mất cập nhật.

Để đánh giá một workload đồng thời, cần đối chiếu ít nhất ba lớp kết quả:

1. **Trạng thái cuối (final state):** các bất biến dữ liệu sau khi toàn bộ giao dịch đã kết thúc có còn đúng không?
2. **Kết quả từng yêu cầu (per-request outcome):** mỗi request logic được chấp nhận, từ chối, retry hay chưa xác định? Có request nào bị xử lý hai lần hoặc không có kết quả bền vững không?
3. **Số giao dịch được xác nhận (confirmed transactions):** có bao nhiêu thao tác nghiệp vụ thực sự được commit và có bằng chứng bền vững? Con số này có khớp với kết quả từng request và trạng thái cuối không?

Ba lớp này phải được liên kết bằng `test_run_id`, `request_id` và một định danh giao dịch nghiệp vụ. Không được đánh đồng số lần gửi HTTP, số lần retry, số transaction SQL bắt đầu, số transaction commit và số giao dịch nghiệp vụ được xác nhận.

## 1. Phân biệt các loại kết quả cần đếm

Một request từ client có thể được gửi nhiều lần. Mỗi lần gửi là một **attempt**; các attempt có cùng idempotency key vẫn thuộc một **logical request**. Một logical request có thể mở một hoặc nhiều database transaction do retry. Chỉ khi transaction ghi kết quả nghiệp vụ commit thành công mới có một giao dịch nghiệp vụ được xác nhận.

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Test run | Một lượt chạy kiểm thử có cấu hình và dữ liệu riêng | `run-2026-11-14-01` |
| Logical request | Một ý định nghiệp vụ duy nhất từ client | Yêu cầu mua 3 sản phẩm với `request_id=R17` |
| Attempt | Một lần gửi hoặc xử lý request; retry tạo attempt mới | Lần gửi đầu timeout, lần thứ hai gửi lại cùng key |
| Database transaction | Một đơn vị `BEGIN`/`COMMIT` hoặc `ROLLBACK` | Transaction kiểm tra tồn kho và tạo order |
| Business transaction | Một nghiệp vụ đã được lưu bền vững | Đơn hàng được xác nhận hoặc khoản chuyển tiền đã commit |
| Confirmed outcome | Kết quả logic đã được lưu và có thể tra cứu lại | `ACCEPTED` hoặc `REJECTED` cho request R17 |

Các con số có thể khác nhau hoàn toàn. Ví dụ 100 logical request có thể tạo 115 attempt do retry, 120 database transaction do một số request cần transaction phụ, 100 kết quả request đã được ghi nhận, nhưng chỉ 63 business transaction được xác nhận vì 37 request bị từ chối do hết hàng.

Nếu client timeout sau khi database commit, client chưa nhận được xác nhận nhưng business transaction có thể đã tồn tại. Trường hợp này là **unknown outcome từ góc nhìn client**, không được tự động tính là thất bại hay gửi một request mới với idempotency key khác.

## 2. Xác định bất biến trước khi chạy test

Mỗi kịch bản phải có kết quả mong đợi được tính trước. Không nên chạy tải rồi mới suy đoán giá trị nào là đúng.

Ví dụ kiểm thử kho hàng:

- Tồn kho ban đầu của SKU `BOOK-1` là 100.
- Có 80 logical request độc lập, mỗi request mua 1 sản phẩm.
- Có thêm 30 logical request độc lập, mỗi request mua 2 sản phẩm.
- Mỗi request được xử lý theo nguyên tắc all-or-nothing: hoặc chấp nhận đủ số lượng, hoặc từ chối toàn bộ.
- Không có nhập thêm hàng, hủy đơn hay hoàn kho trong lúc test.

Tổng nhu cầu là:

```text
80 x 1 + 30 x 2 = 140 sản phẩm
```

Với tồn kho 100, hệ thống không thể chấp nhận toàn bộ 110 request. Kết quả đúng phải thỏa:

```text
0 <= final_stock <= 100
accepted_quantity = 100 - final_stock
accepted_quantity <= 100
accepted_quantity + final_stock = 100
```

Với tập request trộn quantity 1 và 2, nếu mỗi request chỉ được thử một lần và kết quả từ chối là cuối cùng, tồn kho có thể còn 0 hoặc 1 tùy thứ tự xử lý: một số request mua 2 có thể bị từ chối khi chỉ còn 1 sản phẩm, dù request mua 1 được xử lý sau đó. Vì vậy, không nên khẳng định `final_stock = 0` cho workload này. Nếu muốn kỳ vọng chính xác tồn kho cuối bằng 0, hãy dùng kịch bản riêng gồm 100 request mua 1 sản phẩm (hoặc quy định retry/chính sách phân bổ rõ ràng). Số request được chấp nhận trong workload trộn cũng phụ thuộc thứ tự cạnh tranh.

Với bài test chuyển tiền giữa hai tài khoản cùng loại tiền, các bất biến có thể là:

- Tổng số dư hai tài khoản được bảo toàn nếu không có phí.
- Số dư không âm nếu nghiệp vụ không cho phép thấu chi.
- Mỗi `request_id` chỉ tạo tối đa một transfer.
- Mỗi transfer đã xác nhận có đủ bút toán debit/credit tương ứng.
- Mỗi request kết thúc có đúng một kết quả logic đã lưu.

Hãy ghi các bất biến thành phép kiểm tra cụ thể trước khi chạy test. Bất biến phải độc lập với cách triển khai để tránh viết assertion lặp lại chính lỗi của code đang kiểm thử.

## 3. Dùng test_run_id và request_id để liên kết dữ liệu

Mỗi lượt test cần một `test_run_id` duy nhất. Mỗi ý định nghiệp vụ cần một `request_id` duy nhất trong lượt test đó. Khi retry, giữ nguyên `request_id` và idempotency key; chỉ tăng `attempt_no`.

Một mô hình dữ liệu minh họa:

```sql
CREATE TABLE test_request_result (
    test_run_id  VARCHAR(80) NOT NULL,
    request_id   VARCHAR(100) NOT NULL,
    payload_hash VARCHAR(128) NOT NULL,
    outcome      VARCHAR(24) NOT NULL,
    reason       VARCHAR(120),
    business_txn_id VARCHAR(100),
    resolved_at TIMESTAMP,
    PRIMARY KEY (test_run_id, request_id)
);

CREATE TABLE test_run_submitted_request (
    test_run_id VARCHAR(80) NOT NULL,
    request_id  VARCHAR(100) NOT NULL,
    payload_hash VARCHAR(128) NOT NULL,
    submitted_at TIMESTAMP NOT NULL,
    PRIMARY KEY (test_run_id, request_id)
);

CREATE TABLE test_request_attempt (
    test_run_id VARCHAR(80) NOT NULL,
    request_id  VARCHAR(100) NOT NULL,
    attempt_no  INTEGER NOT NULL,
    started_at  TIMESTAMP NOT NULL,
    finished_at TIMESTAMP,
    transport_result VARCHAR(24),
    error_code  VARCHAR(120),
    PRIMARY KEY (test_run_id, request_id, attempt_no)
);

CREATE TABLE confirmed_business_txn (
    test_run_id  VARCHAR(80) NOT NULL,
    business_txn_id VARCHAR(100) NOT NULL,
    request_id   VARCHAR(100) NOT NULL,
    amount       INTEGER NOT NULL,
    status       VARCHAR(24) NOT NULL,
    committed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (test_run_id, business_txn_id),
    UNIQUE (test_run_id, request_id)
);
```

Schema trên phục vụ minh họa kiểm thử. Trong hệ thống thật, bảng kết quả request và bảng business transaction có thể là các bảng nghiệp vụ hiện có. Không nhất thiết tạo bảng test riêng trong production; có thể dùng correlation ID, audit log hoặc dữ liệu ledger tương đương.

`UNIQUE (test_run_id, request_id)` trong `confirmed_business_txn` giả định mỗi logical request tạo tối đa một business transaction. Nếu một request hợp lệ có thể tạo nhiều transaction con, hãy bỏ unique constraint đó và đối soát bằng bảng quan hệ cha-con hoặc khóa nghiệp vụ phù hợp.

Các khóa duy nhất có ý nghĩa quan trọng:

- `PRIMARY KEY (test_run_id, request_id)` bảo đảm một kết quả logic cho mỗi request trong một test run.
- `PRIMARY KEY (test_run_id, business_txn_id)` định danh giao dịch nghiệp vụ đã xác nhận.
- `UNIQUE (test_run_id, request_id)` ngăn một request tạo hai business transaction trong cùng lượt test.
- Khóa attempt gồm `attempt_no` để có thể ghi lại retry mà không nhầm thành request mới.

Nếu cùng `request_id` được gửi lại với payload khác, test phải xem đây là lỗi sử dụng idempotency key. Không được âm thầm trả kết quả cũ cho một yêu cầu có tài khoản, số lượng hoặc giá trị khác.

## 4. Phân loại kết quả của từng request

Không nên chỉ dùng hai trạng thái `SUCCESS` và `FAILED` cho mọi tầng. Một request có thể bị từ chối theo nghiệp vụ, thất bại tạm thời do deadlock, timeout khi chờ response hoặc có kết quả commit chưa rõ.

Nên tách **kết quả cuối của logical request** khỏi **kết quả của từng attempt**. Bảng kết quả logic thường giữ một trạng thái cuối như `ACCEPTED`, `REJECTED` hoặc `CANCELLED`. `UNKNOWN` thường là nhận định tạm thời của client khi chưa tra cứu được kết quả bền vững. `DUPLICATE_REPLAY` và `RETRYABLE_FAILURE` mô tả attempt hoặc response của một lần gửi, không nên ghi đè kết quả cuối đã có của logical request.

Một bộ trạng thái tham khảo:

| Outcome | Ý nghĩa | Có business transaction được xác nhận không? |
|---|---|---:|
| `ACCEPTED` | Nghiệp vụ được chấp nhận và transaction ghi kết quả đã commit | Có |
| `REJECTED` | Nghiệp vụ bị từ chối có chủ đích, ví dụ hết hàng hoặc không đủ số dư; kết quả từ chối đã được lưu | Không |
| `CANCELLED` | Request bị hủy theo một quy tắc nghiệp vụ đã xác định | Tùy quy trình; thường không có giao dịch mới |

`UNKNOWN` thường là trạng thái quan sát ở phía client/test harness, không nhất thiết là trạng thái cuối trong bảng nghiệp vụ. Test runner phải tra cứu bằng request ID sau đó để xác định request đã commit, bị từ chối hay chưa được xử lý. Nếu một attempt retry nhận lại kết quả cũ, attempt đó có thể được ghi `DUPLICATE_REPLAY` trong `test_request_attempt`, còn `test_request_result.outcome` vẫn giữ `ACCEPTED` hoặc `REJECTED` đã được xác nhận từ trước. Nếu một attempt deadlock rồi rollback, attempt đó có thể là `RETRYABLE_FAILURE`; logical request vẫn đang chờ retry và chưa có kết quả cuối.

Deadlock victim và serialization failure là lỗi thực thi của một attempt. Nếu ứng dụng retry thành công, logical request cuối cùng vẫn có thể là `ACCEPTED`. Khi báo cáo, cần lưu cả lịch sử attempt lẫn kết quả cuối của request.

## 5. Số giao dịch xác nhận phải lấy từ bằng chứng bền vững

Một log “HTTP 200” hoặc một counter trong bộ nhớ không đủ để khẳng định transaction đã commit. Response có thể được tạo trước commit do code sai; hoặc commit thành công nhưng response bị mất. Cần một dấu vết bền vững được ghi trong cùng transaction với nghiệp vụ.

Ví dụ khi một request được chấp nhận:

```text
BEGIN
  kiểm tra idempotency key
  cập nhật tồn kho hoặc số dư
  ghi order/transfer/ledger
  ghi test_request_result = ACCEPTED
  ghi confirmed_business_txn
COMMIT
```

Nếu transaction rollback, cả nghiệp vụ và marker xác nhận cùng rollback. Nếu commit thành công nhưng client mất response, test runner có thể dùng connection mới truy vấn `test_request_result` hoặc `confirmed_business_txn` để xác định kết quả.

Đối với request bị từ chối, hệ thống có thể commit một kết quả `REJECTED` trong transaction riêng hoặc trong transaction xử lý request, nhưng không tạo `confirmed_business_txn`. Vì vậy, số kết quả request đã xác nhận và số giao dịch nghiệp vụ thành công là hai con số khác nhau.

Không nên dùng `pg_stat_database.xact_commit`, `Com_commit` hay counter tương tự làm số giao dịch nghiệp vụ của một test run. Những counter này thường ở phạm vi database/server, có thể bao gồm hoạt động khác, transaction phụ, health check và công việc của hệ thống. Chúng hữu ích để quan sát tải tổng thể, nhưng không thay thế bảng ghi nhận theo `test_run_id`.

## 6. Kịch bản mẫu: cạnh tranh mua hàng với tồn kho giới hạn

Giả sử có bảng tồn kho và đơn hàng:

```sql
CREATE TABLE inventory_test (
    sku VARCHAR(40) PRIMARY KEY,
    available_qty INTEGER NOT NULL CHECK (available_qty >= 0)
);

CREATE TABLE purchase_test (
    test_run_id VARCHAR(80) NOT NULL,
    request_id VARCHAR(100) NOT NULL,
    sku VARCHAR(40) NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    status VARCHAR(24) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    PRIMARY KEY (test_run_id, request_id)
);

INSERT INTO inventory_test (sku, available_qty)
VALUES ('BOOK-1', 100);
```

Ví dụ sau dùng cú pháp PostgreSQL (`UPDATE ... RETURNING`). Các placeholder dạng `:quantity` và `:sku` là ký hiệu tham số minh họa; khi chạy bằng JDBC hoặc SQL client, thay bằng cú pháp bind parameter mà driver hỗ trợ.

Với mỗi request, transaction có thể dùng phép cập nhật có điều kiện:

```sql
BEGIN;

UPDATE inventory_test
SET available_qty = available_qty - :quantity
WHERE sku = :sku
  AND available_qty >= :quantity
RETURNING available_qty;

-- Nếu UPDATE trả về một dòng:
--   INSERT purchase_test với status = 'ACCEPTED'.
-- Nếu UPDATE không trả về dòng:
--   INSERT purchase_test với status = 'REJECTED'.

COMMIT;
```

Đoạn SQL là phần lõi minh họa; phần ghi kết quả request, kiểm tra idempotency và tạo business transaction phải được thực hiện trong cùng transaction theo schema của ứng dụng. Nếu request đã được xử lý trước đó, hệ thống phải trả kết quả cũ và không trừ tồn kho lần nữa.

Khi nhiều request cùng tranh chấp một SKU, câu `UPDATE` có điều kiện và row lock giúp database điều phối việc giảm tồn kho. Không thể có hai transaction cùng giảm tồn kho dựa trên cùng giá trị cũ mà làm `available_qty` âm nếu tất cả đường ghi đều tuân thủ điều kiện và constraint.

## 7. Đối chiếu trạng thái cuối

Sau khi tất cả worker đã kết thúc, không còn transaction test đang chạy và các request pending đã được giải quyết, truy vấn trạng thái cuối:

```sql
SELECT sku, available_qty
FROM inventory_test
WHERE sku = 'BOOK-1';
```

Tính tổng số lượng đã được chấp nhận:

```sql
SELECT COALESCE(SUM(quantity), 0) AS accepted_quantity,
       COUNT(*) AS accepted_request_count
FROM purchase_test
WHERE test_run_id = :test_run_id
  AND status = 'ACCEPTED';
```

Kiểm tra bảo toàn tồn kho:

```sql
SELECT i.available_qty,
       COALESCE(SUM(p.quantity), 0) AS accepted_quantity,
       i.available_qty + COALESCE(SUM(p.quantity), 0) AS reconciled_total
FROM inventory_test AS i
LEFT JOIN purchase_test AS p
  ON p.sku = i.sku
 AND p.test_run_id = :test_run_id
 AND p.status = 'ACCEPTED'
WHERE i.sku = 'BOOK-1'
GROUP BY i.sku, i.available_qty;
```

Với test không nhập thêm hàng, không hoàn kho và chỉ xử lý SKU này, `reconciled_total` phải bằng tồn kho ban đầu là 100. `available_qty` phải không âm. Nếu test dùng dữ liệu nền khác, phải lọc đúng `test_run_id` hoặc reset fixture trước khi đối soát.

Chỉ nhìn `available_qty = 0` là chưa đủ. Nếu 100 đơn vị được trừ nhưng chỉ có 90 đơn vị đơn hàng được ghi nhận, 10 đơn vị có thể bị mất khỏi dữ liệu nghiệp vụ. Ngược lại, nếu tổng đơn hàng accepted là 110 nhưng tồn kho chỉ giảm 100, hệ thống đã bán vượt tồn hoặc dữ liệu ghi nhận không nhất quán.

## 8. Đối chiếu kết quả từng request

Sau khi test kết thúc, lấy toàn bộ logical request đã gửi trong run và so sánh với kết quả bền vững trong database. Không chỉ đọc response cuối cùng của worker vì worker có thể crash hoặc timeout.

Ví dụ truy vấn kết quả:

```sql
SELECT request_id,
       outcome,
       reason,
       business_txn_id,
       resolved_at
FROM test_request_result
WHERE test_run_id = :test_run_id
ORDER BY request_id;
```

Kiểm tra request nào không có kết quả:

```sql
SELECT submitted.request_id
FROM test_run_submitted_request AS submitted
LEFT JOIN test_request_result AS result
  ON result.test_run_id = submitted.test_run_id
 AND result.request_id = submitted.request_id
WHERE submitted.test_run_id = :test_run_id
  AND result.request_id IS NULL;
```

Kết quả truy vấn phải rỗng sau khi mọi request đã được giải quyết. Nếu còn request không có kết quả, cần xác định nó chưa được worker nhận, đang pending, bị bỏ quên sau crash hay đã commit nhưng marker không được ghi cùng transaction.

Kiểm tra mỗi request chỉ có một kết quả logic:

```sql
SELECT request_id, COUNT(*) AS result_count
FROM test_request_result
WHERE test_run_id = :test_run_id
GROUP BY request_id
HAVING COUNT(*) <> 1;
```

Nếu bảng đã có primary key `(test_run_id, request_id)`, truy vấn này chủ yếu xác nhận cấu trúc/fixture đúng. Với log attempt, nhiều dòng cho cùng request là bình thường; không được dùng số dòng attempt để đếm logical request.

Kiểm tra request accepted nhưng thiếu business transaction:

```sql
SELECT r.request_id
FROM test_request_result AS r
LEFT JOIN confirmed_business_txn AS t
  ON t.test_run_id = r.test_run_id
 AND t.request_id = r.request_id
WHERE r.test_run_id = :test_run_id
  AND r.outcome = 'ACCEPTED'
  AND t.request_id IS NULL;
```

Kiểm tra request rejected nhưng lại có business transaction:

```sql
SELECT r.request_id
FROM test_request_result AS r
JOIN confirmed_business_txn AS t
  ON t.test_run_id = r.test_run_id
 AND t.request_id = r.request_id
WHERE r.test_run_id = :test_run_id
  AND r.outcome = 'REJECTED';
```

Cả hai truy vấn phải trả về rỗng nếu quy tắc là `ACCEPTED` có đúng một business transaction và `REJECTED` không có business transaction.

## 9. Đối chiếu số giao dịch được xác nhận

Đếm logical request theo kết quả cuối:

```sql
SELECT outcome, COUNT(*) AS request_count
FROM test_request_result
WHERE test_run_id = :test_run_id
GROUP BY outcome
ORDER BY outcome;
```

Đếm business transaction đã xác nhận:

```sql
SELECT COUNT(*) AS confirmed_transaction_count,
       COALESCE(SUM(amount), 0) AS confirmed_amount
FROM confirmed_business_txn
WHERE test_run_id = :test_run_id
  AND status = 'CONFIRMED';
```

Đếm theo request ID duy nhất:

```sql
SELECT COUNT(DISTINCT request_id) AS confirmed_request_count
FROM confirmed_business_txn
WHERE test_run_id = :test_run_id
  AND status = 'CONFIRMED';
```

Nếu mỗi request accepted tạo đúng một business transaction, các con số sau phải bằng nhau:

```text
COUNT(request_result WHERE outcome = 'ACCEPTED')
= COUNT(confirmed_business_txn WHERE status = 'CONFIRMED')
= COUNT(DISTINCT request_id trong confirmed_business_txn)
```

Nếu một request có thể tạo nhiều business transaction, ví dụ một đơn hàng tạo nhiều shipment hoặc một lệnh chuyển tiền tạo nhiều ledger entry, không dùng phép bằng này. Hãy định nghĩa rõ đơn vị đếm: một request, một order, một transfer, một shipment hay một ledger posting. Sau đó đối chiếu bằng quan hệ cha-con và các bất biến tương ứng.

## 10. Đếm attempt riêng với logical request

Để biết test runner có retry bao nhiêu lần:

```sql
SELECT COUNT(*) AS total_attempts,
       COUNT(DISTINCT request_id) AS logical_requests
FROM test_request_attempt
WHERE test_run_id = :test_run_id;
```

Phân bố số attempt trên mỗi request:

```sql
SELECT request_id,
       COUNT(*) AS attempt_count,
       MAX(attempt_no) AS last_attempt_no
FROM test_request_attempt
WHERE test_run_id = :test_run_id
GROUP BY request_id
ORDER BY attempt_count DESC, request_id;
```

Nếu có 100 logical request nhưng 135 attempt, điều đó có thể phản ánh 35 lần retry. Không thể kết luận hệ thống đã xử lý 135 nghiệp vụ. Hãy xem kết quả cuối theo request ID và số business transaction đã commit.

Một retry an toàn giữ nguyên idempotency key. Nếu test runner tạo key mới cho mỗi attempt, duplicate request sẽ bị tính thành nhiều logical request và có thể tạo nhiều business transaction; bài test khi đó không còn kiểm tra đúng hành vi idempotency.

## 11. Xử lý timeout và kết quả COMMIT chưa rõ

Một trong những assertion quan trọng nhất là không tính timeout như một kết quả nghiệp vụ cuối cùng.

Ví dụ:

```text
Client gửi request R17
Server BEGIN
Server ghi business transaction T900
Server COMMIT thành công
Response bị mất trên mạng
Client timeout và ghi nhận UNKNOWN
Client retry R17 với cùng idempotency key
Server tìm thấy kết quả đã commit và trả lại ACCEPTED/T900
```

Ở đây có hai attempt, một logical request, một business transaction được xác nhận và một kết quả cuối `ACCEPTED`. Nếu test runner đếm timeout đầu tiên là thất bại rồi đếm response retry là thành công, nó có thể báo một success và một failure cho cùng một request, làm sai tỷ lệ kết quả.

Khi client nhận `UNKNOWN`:

1. Không tạo request ID mới.
2. Tra cứu kết quả bằng request ID/idempotency key trên connection mới.
3. Nếu đã có kết quả `ACCEPTED`, xác nhận business transaction tương ứng.
4. Nếu đã có `REJECTED`, trả lại kết quả từ chối đã lưu.
5. Nếu chưa có kết quả bền vững, retry cùng key theo chính sách của ứng dụng.
6. Nếu database hoặc hệ thống điều phối vẫn không truy cập được, giữ trạng thái unknown/pending trong báo cáo; không tự suy diễn là rollback.

Test nên có fault injection ở các điểm: trước commit, ngay sau commit nhưng trước response, và sau khi response đã được gửi. Mỗi điểm có kết quả mong đợi riêng.

## 12. Kiểm thử duplicate request đồng thời

Một logical request có thể được gửi đồng thời bởi hai worker do client retry, queue redelivery hoặc timeout. Kịch bản này kiểm tra idempotency ở mức cạnh tranh thật, không chỉ retry tuần tự.

Kịch bản:

1. Reset dữ liệu và tạo request `R-DUP-1` với payload cố định.
2. Mở hai connection độc lập.
3. Cho cả hai gửi cùng idempotency key gần như đồng thời.
4. Chờ cả hai attempt kết thúc.
5. Tra cứu kết quả theo key và business transaction theo request ID.

Assertion:

- Có đúng một logical request result.
- Có tối đa một business transaction được xác nhận.
- Tác dụng phụ chỉ được áp dụng một lần.
- Cả hai attempt có thể nhận cùng kết quả cuối hoặc một attempt nhận trạng thái duplicate/replay.
- Payload khác nhau nhưng cùng key phải bị từ chối rõ ràng.

Unique constraint là hàng rào quan trọng để điều phối hai lần insert cùng key. Phần xử lý conflict cần đọc lại kết quả đã commit và xác minh payload. Không chỉ kiểm tra trong bộ nhớ kiểu `if (map.containsKey(key))`, vì hai process hoặc hai instance có thể cùng vượt qua kiểm tra đó.

## 13. Kiểm thử cạnh tranh với kết quả từng request khác nhau

Khi tồn kho hoặc số dư giới hạn, request không nhất thiết đều thành công. Một bài test đúng phải xác minh cả những request được chấp nhận lẫn bị từ chối.

Ví dụ tồn kho 10, có 20 request mua 1 sản phẩm. Kỳ vọng:

| Chỉ số | Kỳ vọng |
|---|---:|
| Logical request đã gửi | 20 |
| Request `ACCEPTED` | 10 |
| Request `REJECTED` do hết hàng | 10 |
| Business transaction được xác nhận | 10 |
| Tổng quantity đã bán | 10 |
| Tồn kho cuối | 0 |
| Request chưa có kết quả sau khi hệ thống ổn định | 0 |
| Duplicate business transaction theo request ID | 0 |

Trong kịch bản tất cả request có cùng quantity và không có retry gây lỗi cuối, số accepted cụ thể có thể xác định. Nếu request có quantity khác nhau hoặc có ưu tiên, chỉ các bất biến tổng hợp mới cố định; tập request nào được chấp nhận phụ thuộc lịch thực thi và chính sách nghiệp vụ.

Đừng assert rằng request đầu tiên theo thứ tự thread phải thắng nếu không có cơ chế ordering được thiết kế. Thứ tự bắt đầu thread không đồng nghĩa thứ tự transaction lấy lock hoặc commit.

## 14. Tổ chức concurrency test trong Java

Để bắt đầu nhiều request gần cùng thời điểm, có thể dùng `ExecutorService` và `CountDownLatch`. Mỗi task nên dùng connection riêng từ pool để tạo transaction độc lập.

```java
int workers = requests.size();
ExecutorService pool = Executors.newFixedThreadPool(workers);
CountDownLatch ready = new CountDownLatch(workers);
CountDownLatch start = new CountDownLatch(1);

List<Future<RequestResult>> futures = new ArrayList<>();

for (TransferRequest request : requests) {
    futures.add(pool.submit(() -> {
        ready.countDown();
        start.await();
        return transferService.execute(request);
    }));
}

ready.await();       // tất cả worker đã sẵn sàng
start.countDown();   // cho phép bắt đầu đồng thời

List<RequestResult> results = new ArrayList<>();
for (Future<RequestResult> future : futures) {
    results.add(future.get());
}

pool.shutdown();
```

Đoạn mã chỉ đồng bộ thời điểm bắt đầu ở mức gần nhau. Nó **không bảo đảm một interleaving cụ thể** bên trong database. Scheduler, connection pool, network và lock manager vẫn quyết định thứ tự thực tế.

Để tái hiện một lịch xác định như lost update, thêm test hook hoặc barrier ở điểm sau khi đọc nhưng trước khi ghi:

```java
// Chỉ dùng trong test harness, không đặt barrier này trong production.
int observed = repository.readBalance(accountId);
afterReadBarrier.await();
int newBalance = observed - amount;
repository.writeAbsoluteBalance(accountId, newBalance);
```

Cho cả hai worker vượt qua `afterReadBarrier` sau khi đã đọc cùng giá trị. Khi đó test có thể tái hiện lỗi một cách lặp lại. Với test xác minh bản sửa, barrier phải được đặt phù hợp với cơ chế mới; ví dụ test `SELECT FOR UPDATE` cần cho thấy worker thứ hai chờ trước khi đọc được giá trị mới.

Không dùng `Thread.sleep()` làm công cụ đồng bộ chính. Sleep chỉ tạo xác suất về thứ tự, phụ thuộc tải máy và có thể khiến test chập chờn. Dùng latch, barrier, hook hoặc tín hiệu đồng bộ rõ ràng.

## 15. Thu thập kết quả từng request trong test harness

Mỗi kết quả nên chứa tối thiểu:

```java
record RequestObservation(
    String testRunId,
    String requestId,
    int attemptNo,
    Instant startedAt,
    Instant finishedAt,
    String transportStatus,
    String businessOutcome,
    String businessTransactionId,
    String errorCode
) {}
```

Tách `transportStatus` khỏi `businessOutcome`. Ví dụ HTTP timeout có thể đi cùng business outcome `UNKNOWN`; HTTP 200 có thể đi cùng `REJECTED` nếu request hợp lệ về giao thức nhưng không đủ số dư. Một response duplicate/replay có thể trả kết quả nghiệp vụ `ACCEPTED` từ lần trước mà không tạo transaction mới.

Test runner nên giữ danh sách request dự kiến độc lập với danh sách kết quả nhận được. Sau khi workload kết thúc, so sánh tập ID:

```text
submitted_request_ids
    - resolved_request_ids = missing requests

resolved_request_ids
    - submitted_request_ids = unexpected results
```

Kiểm tra duplicate bằng grouping theo `(test_run_id, request_id)`. Kiểm tra retry bằng grouping theo request ID và `attempt_no`. Không dùng thứ tự phần tử trong `Future` hoặc thứ tự log để suy ra thứ tự commit.

## 16. Đối soát ba lớp bằng một báo cáo

Một báo cáo kết thúc test nên có cấu trúc rõ ràng:

| Nhóm | Chỉ số | Ý nghĩa |
|---|---|---|
| Input | Logical requests submitted | Số request logic được tạo cho run |
| Input | Total attempts | Số lần gửi/ xử lý, bao gồm retry |
| Per-request | Accepted | Số request có kết quả nghiệp vụ accepted |
| Per-request | Rejected | Số request bị từ chối có chủ đích |
| Per-request | Retryable failures | Request chưa có kết quả cuối do lỗi tạm thời |
| Per-request | Unknown/pending | Chưa xác định được kết quả bền vững |
| Persistence | Confirmed business transactions | Số nghiệp vụ thành công đã commit và có marker |
| Persistence | Duplicate transaction IDs | Số giao dịch bị tạo trùng theo request key |
| Final state | Balance/stock/counter | Giá trị cuối của dữ liệu nghiệp vụ |
| Invariant | Reconciled total | Tổng đã đối soát với giá trị ban đầu và biến động hợp lệ |
| Reliability | Deadlocks/serialization retries | Số lỗi đồng thời và số lần retry |
| Performance | Throughput/latency | Số request hoặc transaction mỗi giây và độ trễ |

Ví dụ báo cáo cho bài test kho hàng:

```text
test_run_id: inventory-race-01
submitted logical requests:       20
total attempts:                   24
accepted requests:                10
rejected requests:                10
unresolved requests:               0
confirmed business transactions: 10
duplicate business transactions:  0
initial stock:                    10
accepted quantity:                10
final stock:                       0
reconciled total:                 10
```

Các phép đối chiếu cần đúng:

```text
accepted requests = confirmed business transactions
accepted quantity + final stock = initial stock
submitted requests = accepted + rejected + unresolved
unresolved = 0 trước khi kết luận test hoàn tất
duplicate business transactions = 0
```

Nếu có request `CANCELLED`, `UNKNOWN` hoặc outcome khác, phải đưa chúng vào phương trình phân loại tương ứng. Không bỏ qua chúng để làm cho tổng số đẹp hơn.

## 17. Kiểm thử lỗi ở các ranh giới commit

Chỉ chạy workload thành công không đủ để kiểm tra độ tin cậy. Nên tiêm lỗi tại các điểm có thể làm client và database nhìn thấy kết quả khác nhau.

| Điểm tiêm lỗi | Trạng thái database mong đợi | Điều test cần xác nhận |
|---|---|---|
| Trước khi bắt đầu transaction | Không có business transaction | Request có thể retry |
| Sau khi đọc nhưng trước khi ghi | Không có thay đổi đã commit | Retry phải đọc trạng thái mới |
| Sau khi cập nhật dữ liệu nhưng trước COMMIT | Rollback toàn bộ nếu transaction bị hủy | Không có business marker/ledger một nửa |
| Deadlock trước commit | Transaction victim rollback | Retry không tạo nghiệp vụ trùng |
| Ngay sau COMMIT nhưng trước response | Business transaction có thể đã tồn tại | Tra cứu cùng request ID trả kết quả cũ |
| Sau khi response thành công | Kết quả đã commit | Retry cùng key không tạo transaction thứ hai |
| Consumer commit nhưng trước ACK | Consumer effect đã commit | Message giao lại không lặp tác dụng phụ |

Với tình huống mất kết nối quanh COMMIT, test không được giả định database đã rollback. Hãy xác định trạng thái bằng một truy vấn mới sau khi kết nối ổn định và dùng request ID để tìm kết quả.

## 18. Kiểm thử lặp lại và kiểm thử tải

Một lịch deterministic giúp tái hiện lỗi cụ thể; stress test giúp tìm lỗi chỉ xuất hiện dưới tải. Hai loại test bổ trợ nhau.

### Deterministic concurrency test

- Dùng fixture nhỏ, dữ liệu dễ tính bằng tay.
- Điều phối các điểm đọc/ghi bằng latch hoặc barrier.
- Tái hiện đúng một interleaving đã biết.
- Assert từng request, số transaction và trạng thái cuối.
- Chạy lại nhiều lần để xác nhận kết quả ổn định.

### Stress/load test

- Tăng số worker và số logical request theo từng mức.
- Dùng dữ liệu có mức tranh chấp khác nhau: một hot key, nhiều key độc lập, phân bố lệch.
- Giữ request ID ổn định qua retry.
- Thu thập latency, throughput, deadlock, timeout, serialization failure và retry count.
- Sau mỗi run, chờ hệ thống xử lý hết pending/unknown rồi đối soát database.
- Lặp nhiều seed hoặc nhiều run độc lập để phát hiện lỗi hiếm.

Stress test không nên chỉ assert response code. Một hệ thống có thể trả 99% HTTP 200 nhưng vẫn tạo duplicate business transaction hoặc sai tổng số dư. Đối soát dữ liệu bền vững là bước bắt buộc.

## 19. Các lỗi thường gặp khi đánh giá kết quả

**Chỉ kiểm tra trạng thái cuối.** Một giá trị cuối có vẻ hợp lệ không chứng minh từng request được xử lý đúng. Cần đối chiếu request ID và lịch sử giao dịch.

**Chỉ đếm HTTP 200.** Response thành công không nhất thiết bằng một business transaction mới; nó có thể là replay kết quả cũ hoặc response được gửi trước commit do code sai.

**Đếm số attempt thay cho số request.** Retry làm tăng attempt count nhưng không tạo logical request mới.

**Đếm số transaction SQL thay cho số nghiệp vụ.** Một request có thể mở nhiều transaction do retry; một transaction có thể tạo nhiều bản ghi nghiệp vụ; health check và công việc nền cũng tạo transaction.

**Coi timeout là thất bại chắc chắn.** Commit có thể thành công nhưng response bị mất. Cần tra cứu theo idempotency key.

**Không kiểm tra request bị thiếu.** Tổng accepted/rejected có thể nhỏ hơn số đã gửi vì một số worker crash hoặc request vẫn pending.

**Không phân biệt rejected với failed.** Rejected là kết quả nghiệp vụ hợp lệ; failed là lỗi thực thi hoặc hạ tầng. Hai nhóm có cách retry khác nhau.

**Dùng một test run chung cho nhiều lượt.** Dữ liệu cũ làm sai số lượng, tổng tiền và tồn kho. Mỗi run cần ID riêng hoặc fixture được reset có kiểm soát.

**Dựa vào thứ tự thread để đoán winner.** Thứ tự submit/start không bảo đảm thứ tự lock hoặc commit. Chỉ assert winner cố định khi test đã thiết kế cơ chế ordering rõ ràng.

## 20. Quy trình kết thúc một bài kiểm thử đồng thời

1. Chờ tất cả worker/attempt đã được khởi chạy kết thúc hoặc chuyển sang trạng thái timeout có quản lý.
2. Thu thập response và lịch sử attempt từ test harness.
3. Dùng connection mới tra cứu các request có outcome `UNKNOWN`.
4. Chờ hoặc xử lý hết trạng thái pending theo timeout của kịch bản.
5. Truy vấn kết quả cuối của từng request theo `test_run_id`.
6. Đếm logical request, attempt, accepted, rejected và unresolved riêng biệt.
7. Đếm business transaction đã xác nhận từ bảng nghiệp vụ/marker bền vững.
8. Kiểm tra không có duplicate theo request ID hoặc idempotency key.
9. Đối soát trạng thái cuối với tổng các giao dịch đã xác nhận.
10. Kiểm tra các bất biến: số dư, tồn kho, tổng debit/credit, version và trạng thái hợp lệ.
11. Ghi nhận deadlock, retry, timeout, serialization failure và latency.
12. Chỉ kết luận test pass khi không còn request chưa giải quyết và cả ba lớp kết quả khớp với kỳ vọng.

Một test run nên lưu lại seed, cấu hình worker, isolation level, dữ liệu ban đầu, phiên bản DBMS, test code revision và `test_run_id`. Nhờ vậy, khi phát hiện lỗi, nhóm phát triển có thể tái hiện cùng workload và so sánh trước/sau thay đổi.

## 21. Kết luận

Kiểm thử đồng thời cần chứng minh đồng thời ba điều: trạng thái cuối vẫn giữ bất biến, mỗi logical request có đúng một kết quả có thể tra cứu, và số business transaction đã xác nhận khớp với các request được chấp nhận. Số attempt, số transaction SQL và số response không thay thế được số nghiệp vụ đã commit.

Hãy gắn mọi dữ liệu kiểm thử với `test_run_id` và `request_id`, lưu kết quả nghiệp vụ cùng transaction, giữ idempotency key qua retry và xử lý riêng trạng thái `UNKNOWN` sau timeout. Khi test kết thúc, đối chiếu request đã gửi với kết quả từng request, đếm giao dịch được xác nhận từ dữ liệu bền vững rồi kiểm tra lại trạng thái cuối. Chỉ khi cả ba lớp khớp nhau mới có đủ bằng chứng để kết luận hệ thống xử lý đúng dưới tải đồng thời.
