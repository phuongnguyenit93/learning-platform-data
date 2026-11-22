# Tránh tối ưu thông lượng bằng cách làm mất bảo đảm tính đúng đắn

Khi database chịu tải cao, những cách tăng throughput thường được nghĩ đến đầu tiên là giảm isolation level, bỏ khóa, rút ngắn transaction, tăng số connection, dùng cache hoặc chuyển một phần công việc sang xử lý bất đồng bộ. Các biện pháp này có thể cải thiện tốc độ, nhưng cũng có thể làm thay đổi những bảo đảm mà nghiệp vụ đang dựa vào. Một hệ thống xử lý được nhiều request hơn nhưng cho phép số dư âm, đặt trùng chỗ, mất cập nhật hoặc đánh dấu công việc hoàn tất sai thì không phải là hệ thống được tối ưu thành công.

Nguyên tắc quan trọng là xác định **bất biến dữ liệu và kết quả nghiệp vụ phải được bảo vệ trước**, rồi mới chọn cách giảm chi phí để duy trì chúng. Không phải mọi thao tác đều cần Serializable hoặc khóa độc quyền; nhiều workload có thể chạy nhanh với atomic update, constraint, optimistic concurrency, transaction ngắn, index phù hợp và queue. Nhưng mỗi lần bỏ một cơ chế bảo vệ phải có một cơ chế khác chứng minh được cùng bất biến vẫn được giữ.

Bài học này tập trung vào cách phân biệt tối ưu an toàn với tối ưu làm yếu tính đúng đắn, cách chọn mức bảo vệ theo loại dữ liệu, và cách đo throughput mà không bỏ qua lỗi dữ liệu, retry, tail latency hoặc độ trễ đồng bộ.

## 1. Xác định đúng mục tiêu tối ưu

Throughput là số đơn vị công việc hoàn tất trong một khoảng thời gian, ví dụ transaction commit mỗi giây hoặc đơn hàng hoàn tất mỗi phút. Latency là thời gian một request cần để hoàn tất. Hai chỉ số này có liên quan nhưng không đồng nghĩa: tăng throughput bằng cách gom batch có thể làm latency của từng request tăng; tăng connection có thể làm số request chờ trong database tăng mà throughput thực tế không cải thiện.

Khi đánh giá một thay đổi, không nên chỉ nhìn số câu SQL/giây. Cần đo tối thiểu:

- Số giao dịch nghiệp vụ hoàn tất thành công trên một đơn vị thời gian.
- Latency p50, p95, p99 và thời gian chờ lâu nhất.
- Tỷ lệ lỗi nghiệp vụ, constraint violation, deadlock và serialization failure.
- Số lần retry trên mỗi request gốc và tỷ lệ retry thành công.
- Lock wait, transaction duration và số session hoạt động.
- Độ trễ đọc sau ghi nếu có cache hoặc replica.
- Các bất biến dữ liệu sau khi tải kết thúc: không mất cập nhật, không vượt giới hạn, không có bản ghi trùng hoặc trạng thái sai.

Ví dụ, sau khi bỏ khóa, ứng dụng có thể tăng từ 500 lên 900 request/giây nhưng đồng thời tạo 20 giao dịch đặt chỗ trùng nhau. Throughput tăng 80% không bù được việc dữ liệu nghiệp vụ bị sai.

### 1.1. Viết bất biến trước khi tối ưu

Bất biến (invariant) là điều kiện phải luôn đúng đối với dữ liệu đã commit. Hãy viết chúng thành câu cụ thể trước khi đổi isolation, khóa hoặc cấu trúc dữ liệu.

| Nghiệp vụ | Bất biến cần giữ |
|---|---|
| Tài khoản | Số dư không được âm; một giao dịch chuyển tiền chỉ được ghi nhận một lần |
| Kho hàng | Số lượng tồn không âm; một đơn hàng không giữ vượt số lượng có thể bán |
| Đặt phòng | Hai reservation cùng phòng không được chồng lấn thời gian |
| Đăng ký | Một email hoặc mã định danh chỉ được gắn với một tài khoản |
| Hạn mức | Tổng sử dụng của một nhóm không vượt quota |
| Ca trực | Mỗi ca phải có ít nhất một người trực |
| Hàng đợi | Một job chỉ có một owner hợp lệ tại một thời điểm; job không bị mất khi worker chết |

Sau đó phân loại bất biến thuộc một hàng, nhiều hàng, một khoảng dữ liệu, một transaction hay nhiều hệ thống. Phạm vi này quyết định cơ chế bảo vệ phù hợp.

## 2. Các kiểu tối ưu dễ làm mất tính đúng đắn

### 2.1. Hạ isolation level mà không phân tích anomaly

Giảm từ Serializable xuống Read Committed có thể giảm blocking hoặc serialization failure. Nhưng nếu ứng dụng dựa vào nhiều lần đọc để kiểm tra một điều kiện rồi ghi các hàng khác nhau, mức thấp hơn có thể cho phép write skew hoặc phantom.

Ví dụ, hai bác sĩ A và B cùng trực một ca và quy tắc là phải có ít nhất một người trực. T1 đọc thấy hai người trực rồi cho A nghỉ; T2 cũng đọc thấy hai người trực rồi cho B nghỉ. Nếu hai transaction cập nhật hai hàng khác nhau và isolation không phát hiện xung đột predicate, cả hai có thể commit và ca trực không còn ai.

Hạ isolation chỉ an toàn khi đã chứng minh thao tác không phụ thuộc vào những anomaly mà mức mới cho phép, hoặc đã bổ sung constraint/guard/atomic update để bảo vệ bất biến.

### 2.2. Bỏ SELECT FOR UPDATE rồi vẫn read-modify-write

Một ứng dụng có thể bỏ locking read để giảm lock wait nhưng vẫn giữ logic cũ:

```sql
SELECT balance
FROM account
WHERE account_id = 42;

-- Ứng dụng tính balance mới trong bộ nhớ.

UPDATE account
SET balance = :new_balance
WHERE account_id = 42;
```

Hai transaction có thể cùng đọc balance cũ, cùng tính toán và ghi đè lẫn nhau. Kết quả là lost update.

Nếu muốn giảm khóa, hãy chuyển phép tính thành atomic update hoặc dùng version column để phát hiện xung đột. Bỏ khóa mà không đổi giao thức ghi là một tối ưu không an toàn.

### 2.3. Xóa constraint vì insert bị chậm

Unique constraint, foreign key, check constraint và exclusion constraint có chi phí kiểm tra, nhưng chúng cũng là hàng rào bảo vệ dữ liệu trước mọi caller. Xóa constraint để insert nhanh hơn có thể biến một lỗi được DBMS từ chối thành dữ liệu sai đã commit.

Ví dụ, nếu ứng dụng chỉ chạy `SELECT` kiểm tra email trước khi insert mà bỏ unique constraint, hai request có thể cùng thấy email chưa tồn tại và cùng insert. Kiểm tra ở tầng ứng dụng không thay thế được unique index có đồng bộ cạnh tranh.

Nếu constraint là điểm nóng, hãy xem index, kiểu dữ liệu, batch size và mô hình ghi trước khi cân nhắc thay đổi. Chỉ bỏ constraint khi đã có cơ chế tương đương được chứng minh và mọi đường ghi đều tuân thủ.

### 2.4. Dùng SKIP LOCKED cho truy vấn cần đầy đủ dữ liệu

`SKIP LOCKED` giúp worker queue bỏ qua hàng đang bị worker khác khóa để nhận việc khác. Nhưng nó cố ý trả về tập hàng không đầy đủ theo nghĩa toàn bộ predicate.

Dùng nó cho báo cáo đối soát, đếm chính xác, kiểm tra bất biến hoặc export toàn bộ dữ liệu có thể làm kết quả thiếu hàng đang bị khóa. Công cụ phù hợp cho queue không tự động phù hợp cho truy vấn nghiệp vụ khác.

### 2.5. Tăng connection và worker không giới hạn

Tăng concurrency có thể giúp tận dụng database khi hệ thống còn tài nguyên rảnh. Nhưng nếu mọi worker tranh chấp cùng một hàng hoặc index key, nhiều connection chỉ làm hàng đợi khóa dài hơn, tăng context switching, memory, I/O và retry.

Khi database đã bão hòa, admission control và giới hạn concurrency thường hiệu quả hơn việc tăng pool size. Số worker phải dựa trên throughput thực tế và loại contention, không dựa trên số CPU hoặc số connection tối đa mà driver cho phép.

## 3. Ví dụ lost update: throughput cao nhưng dữ liệu mất

Giả sử số dư ban đầu là 100. T1 muốn cộng 10, T2 muốn cộng 20. Cả hai đọc 100, sau đó ghi giá trị đã tính:

```text
T1                                      T2
-----------------------------------     -----------------------------------
SELECT balance -> 100                  SELECT balance -> 100
Tính 100 + 10 = 110                    Tính 100 + 20 = 120
UPDATE balance = 110                   UPDATE balance = 120
COMMIT                                  COMMIT

Kết quả cuối có thể là 110 hoặc 120.
Một trong hai khoản cộng đã bị mất.
```

Nếu mục tiêu là cộng dồn, hãy để database thực hiện phép cộng nguyên tử:

```sql
UPDATE account
SET balance = balance + :amount
WHERE account_id = :account_id;
```

Hai câu update cùng hàng vẫn được database điều phối, nhưng mỗi phép cộng được áp dụng trên giá trị hiện hành theo thứ tự ghi. Kết quả cuối là 130 nếu cả hai transaction commit.

Atomic update không tự bảo vệ mọi quy tắc. Nếu số dư không được âm, phải đưa điều kiện vào câu lệnh:

```sql
UPDATE account
SET balance = balance - :amount
WHERE account_id = :account_id
  AND balance >= :amount;
```

Ứng dụng kiểm tra row count. Một hàng được cập nhật nghĩa là khoản trừ được chấp nhận; 0 hàng nghĩa là tài khoản không tồn tại hoặc không đủ số dư theo điều kiện. Không thực hiện bước ghi tiếp theo nếu cập nhật không thành công.

## 4. Write skew: mỗi hàng hợp lệ nhưng quy tắc chung bị phá

Atomic update trên một hàng giải quyết tốt nhiều lost update, nhưng không đủ cho mọi bất biến nhiều hàng.

Giả sử bảng `doctor_on_call` có hai hàng đang trực. Mỗi transaction đọc `count(*) = 2`, sau đó cập nhật một hàng khác nhau thành `on_call = false`. Mỗi hàng vẫn hợp lệ, nhưng tổng số người trực trở thành 0.

```sql
SELECT count(*)
FROM doctor_on_call
WHERE shift_id = 10
  AND on_call = true;

-- Nếu count > 1 thì cập nhật một bác sĩ thành off-call.
```

Hai transaction chạy đồng thời có thể cùng qua điều kiện. Để bảo vệ bất biến, cần một điểm đồng bộ chung hoặc isolation đủ mạnh:

- Duy trì `on_call_count` trên hàng guard và giảm bằng `UPDATE ... WHERE on_call_count > 1` trong cùng transaction.
- Khóa một hàng đại diện cho ca trực trước khi đếm và cập nhật; mọi writer phải tuân thủ cùng giao thức.
- Dùng Serializable và retry toàn bộ transaction khi DBMS phát hiện lịch không tuần tự hóa.

Không nên chọn Read Committed chỉ vì ít abort hơn nếu ứng dụng vẫn dựa trên phép đếm nhiều hàng để quyết định.

## 5. Chọn cơ chế bảo vệ theo loại bất biến

Không phải mọi thao tác đều cần cùng isolation level. Có thể dùng cơ chế hẹp hơn nếu nó trực tiếp bảo vệ điều kiện cần giữ.

| Loại bất biến | Cơ chế phù hợp thường gặp | Ví dụ |
|---|---|---|
| Điều kiện trên một hàng | `NOT NULL`, `CHECK` | `quantity >= 0` |
| Duy nhất giữa các hàng | `UNIQUE`/unique index | Một email cho một tài khoản |
| Quan hệ tham chiếu | `FOREIGN KEY` | Order phải thuộc customer tồn tại |
| Cập nhật cộng/trừ một hàng | Atomic conditional `UPDATE` | Trừ tồn kho nếu đủ số lượng |
| Phát hiện object cũ | Version column/optimistic lock | Không ghi đè form đã được người khác sửa |
| Tuần tự hóa một tài nguyên nóng | Row lock/guard row | Cập nhật quota của một tenant |
| Không chồng lấn khoảng | Exclusion constraint, range lock hoặc Serializable | Đặt phòng |
| Predicate phức tạp nhiều hàng | Serializable hoặc giao thức guard rõ ràng | Ít nhất một bác sĩ trực |
| Phân phối job cho worker | Atomic claim, lease, token | Queue dùng `SKIP LOCKED` |

Ưu tiên constraint mà DBMS có thể thực thi trực tiếp khi quy tắc khớp với semantics của constraint. Với bất biến aggregate hoặc predicate phức tạp, chọn guard/counter/locking/Serializable dựa trên access path và isolation thực tế.

## 6. Tối ưu an toàn bằng atomic update

Atomic update chuyển thao tác đọc-tính-ghi thành một statement mà database có thể thực hiện nguyên tử trên hàng.

Ví dụ trừ tồn kho:

```sql
UPDATE inventory
SET quantity = quantity - :requested
WHERE product_id = :product_id
  AND quantity >= :requested;
```

Trong cùng transaction, chỉ tạo reservation hoặc order item nếu update ảnh hưởng đúng một hàng:

```sql
BEGIN;

UPDATE inventory
SET quantity = quantity - :requested
WHERE product_id = :product_id
  AND quantity >= :requested;

-- Nếu row count != 1: ROLLBACK và trả kết quả hết hàng.

INSERT INTO order_item(order_id, product_id, quantity)
VALUES (:order_id, :product_id, :requested);

COMMIT;
```

Phép cập nhật có điều kiện vừa bảo vệ số lượng không âm, vừa giảm khoảng thời gian giữa đọc và ghi. Transaction vẫn cần để giữ atomicity giữa inventory và order item.

Không được bỏ kiểm tra row count. Nếu update ảnh hưởng 0 hàng mà ứng dụng vẫn insert order item, dữ liệu sẽ sai dù câu update là atomic.

### 6.1. Chuyển tiền giữa hai tài khoản

Một giao dịch chuyển tiền cần trừ một tài khoản và cộng tài khoản kia trong cùng transaction. Khóa theo thứ tự ID ổn định giúp giảm deadlock khi hai request chuyển tiền ngược chiều.

```sql
BEGIN;

-- Khóa/đọc theo account_id tăng dần nếu cần locking read.
SELECT account_id, balance
FROM account
WHERE account_id IN (:from_id, :to_id)
ORDER BY account_id
FOR UPDATE;

UPDATE account
SET balance = balance - :amount
WHERE account_id = :from_id
  AND balance >= :amount;

-- Xác nhận đúng một hàng được cập nhật.

UPDATE account
SET balance = balance + :amount
WHERE account_id = :to_id;

COMMIT;
```

Ví dụ cần bổ sung kiểm tra tài khoản đích tồn tại, amount dương, không chuyển vào cùng tài khoản và row count đúng. Nếu bất kỳ bước nào thất bại, rollback toàn transaction. Tùy DBMS, cú pháp locking read và cách khóa thứ tự có thể khác.

## 7. Tối ưu an toàn bằng optimistic concurrency

Khi xung đột hiếm, optimistic locking có thể tránh khóa bi quan trong phần lớn thời gian. Mỗi hàng có một version tăng khi cập nhật.

```sql
UPDATE document
SET body = :new_body,
    version = version + 1
WHERE document_id = :id
  AND version = :observed_version;
```

Nếu row count là 0, một transaction khác đã thay đổi hàng sau lần đọc. Ứng dụng phải thông báo conflict hoặc đọc lại và tính lại theo nghiệp vụ.

Optimistic locking không làm xung đột biến mất; nó chuyển một phần chi phí từ chờ khóa sang phát hiện conflict và retry. Nếu cùng một hàng bị cập nhật liên tục, retry có thể tốn hơn việc dùng khóa bi quan hoặc queue theo key.

Mọi đường ghi phải tăng version, kể cả native SQL, batch job và stored procedure. Nếu một đường ghi bỏ qua version, ORM có thể không phát hiện stale object.

## 8. Dùng constraint thay cho pre-check ở ứng dụng

Mẫu “SELECT trước, nếu chưa có thì INSERT” dễ gặp race condition:

```sql
SELECT user_id
FROM app_user
WHERE email = :email;

-- Nếu không thấy thì INSERT.
```

Hai transaction có thể cùng đọc kết quả rỗng. Constraint `UNIQUE` là cơ chế bảo vệ cuối cùng:

```sql
CREATE TABLE app_user (
    user_id bigint PRIMARY KEY,
    email   varchar(320) NOT NULL,
    CONSTRAINT uq_app_user_email UNIQUE (email)
);
```

DBMS điều phối hai insert cạnh tranh để chỉ một giá trị duy nhất được commit. Ứng dụng có thể dùng upsert hoặc bắt unique violation theo nghiệp vụ, nhưng không nên bỏ constraint chỉ để tránh lỗi đồng thời.

Constraint không chỉ bảo vệ ứng dụng hiện tại; nó còn bảo vệ dữ liệu khi có script quản trị, batch import, service khác hoặc code mới ghi trực tiếp vào database.

## 9. Rút ngắn transaction mà không phá atomicity

Transaction dài làm lock được giữ lâu hơn, snapshot tồn tại lâu hơn và connection bị chiếm dụng lâu hơn. Có thể rút ngắn bằng cách chuyển công việc không cần nằm trong transaction ra ngoài:

- Tính toán thuần túy trước khi mở transaction nếu dữ liệu đầu vào không cần được bảo vệ trong transaction.
- Chuẩn bị payload, validate định dạng và gọi dịch vụ đọc độc lập trước transaction nếu không tạo tác động không thể đảo ngược.
- Trong transaction chỉ thực hiện đọc/ghi cần tính nguyên tử, kiểm tra bất biến và ghi outbox.
- Commit sớm sau khi trạng thái bền vững đã được ghi.
- Gửi email, gọi HTTP hoặc phát message qua worker/outbox sau commit.

Không di chuyển một bước ra ngoài transaction nếu bước đó là một phần của bất biến. Ví dụ, không commit trừ tồn kho trước rồi tạo order item trong transaction khác nếu nghiệp vụ yêu cầu hai thay đổi cùng thành công hoặc cùng thất bại.

### 9.1. Outbox cho tác động bên ngoài

Nếu transaction cập nhật đơn hàng và cần phát sự kiện, ghi sự kiện vào bảng outbox trong cùng transaction:

```sql
BEGIN;

UPDATE orders
SET status = 'CONFIRMED'
WHERE order_id = :order_id
  AND status = 'PENDING';

INSERT INTO outbox(event_id, aggregate_id, event_type, payload)
VALUES (:event_id, :order_id, 'OrderConfirmed', :payload);

COMMIT;
```

Worker đọc outbox và gửi message sau commit. Việc ghi order và ý định phát event được nguyên tử trong database. Message có thể được gửi lặp nếu worker mất phản hồi; consumer cần idempotency/deduplication.

Không gửi HTTP hoặc email trước commit rồi giả định rollback database có thể thu hồi tác động đó. Database không thể rollback một hệ thống ngoài đã chấp nhận lệnh.

## 10. Tối ưu index và execution plan để giảm lock footprint

Một truy vấn dùng index phù hợp thường phải xem xét ít hàng hơn, chạy nhanh hơn và giảm thời gian giữ lock. Đây là tối ưu có thể cải thiện throughput mà vẫn giữ nguyên bất biến.

Ví dụ:

```sql
SELECT order_id
FROM orders
WHERE customer_id = :customer_id
  AND status = 'PENDING'
ORDER BY created_at, order_id;
```

Một index ghép phù hợp có thể là:

```sql
CREATE INDEX idx_orders_customer_status_created
ON orders(customer_id, status, created_at, order_id);
```

Thứ tự cột phải dựa trên predicate và kế hoạch thực tế. Index không tự làm truy vấn Serializable hoặc locking read có cùng semantics giữa các DBMS; nó giúp thu hẹp access path và có thể thu hẹp range được bảo vệ.

Khi tối ưu, hãy xem:

- Index seek hay scan.
- Seek predicate và residual predicate.
- Số hàng ước lượng so với thực tế.
- Join order và số hàng trung gian.
- Lock mode/range thực tế trong DBMS.
- Chi phí duy trì index khi insert/update/delete.

Không tạo index hàng loạt mà không đo. Index làm tăng dung lượng và chi phí ghi; index order sai có thể không giúp điều kiện truy vấn.

## 11. Chọn isolation theo bất biến, không theo khẩu hiệu

Không có một isolation level tối ưu cho mọi thao tác. Có thể phân loại workload:

| Loại thao tác | Mức/cơ chế có thể phù hợp | Điều kiện cần xác minh |
|---|---|---|
| Đọc dashboard chấp nhận dữ liệu trễ nhẹ | Snapshot/MVCC read hoặc cache | Độ trễ dữ liệu được nghiệp vụ chấp nhận |
| Cộng/trừ một counter | Atomic update | Predicate update bảo vệ giới hạn; kiểm tra row count |
| Cập nhật form có thể bị người khác sửa | Optimistic version | Conflict được hiển thị hoặc hợp nhất đúng cách |
| Sửa một hàng nóng cần tuần tự hóa | Pessimistic row lock hoặc atomic statement | Transaction ngắn, timeout và lock order |
| Kiểm tra tổng hợp nhiều hàng | Guard/counter hoặc Serializable | Mọi writer tham gia giao thức; retry toàn transaction |
| Không cho phép hai khoảng chồng lấn | Exclusion/range protection/Serializable | DBMS và index thực sự bảo vệ predicate |
| Claim job độc lập | Atomic claim với `SKIP LOCKED`, lease | Chấp nhận kết quả claim không đầy đủ và xử lý at-least-once |

Read Committed có thể hoàn toàn đủ cho một câu `UPDATE` nguyên tử. Serializable có thể cần thiết cho một quy tắc nhiều predicate. Hãy chọn theo điều kiện phải giữ và semantics thực tế của DBMS, không nâng hoặc hạ isolation chỉ để đạt một con số throughput.

## 12. Snapshot, cache và replica: tăng tốc đọc có thể làm dữ liệu cũ

Cache và read replica giảm tải đọc trên primary. Nhưng chúng có thể trả dữ liệu chưa phản ánh commit mới nhất.

Trước khi dùng cache/replica, hãy phân loại yêu cầu đọc:

- **Eventual consistency chấp nhận được:** danh sách sản phẩm, dashboard tổng hợp hoặc số liệu phân tích có thể trễ vài giây nếu nghiệp vụ cho phép.
- **Read-your-writes:** người dùng cần thấy thay đổi vừa ghi; có thể định tuyến đọc về primary hoặc chờ replica replay đến vị trí commit.
- **Strong consistency:** số dư, hạn mức hoặc quyền truy cập nhạy cảm cần đọc từ nguồn có semantics nhất quán phù hợp.

Một transaction commit trên primary không có nghĩa asynchronous replica đã replay thay đổi. Một cache local cũng không tự invalidated khi service khác cập nhật database. Cần hợp đồng freshness rõ, version/event invalidation và cơ chế đọc sau ghi.

Không dùng cache cũ để quyết định một thao tác cần bất biến mạnh, chẳng hạn “còn đủ tồn kho không”, rồi ghi vào database mà không kiểm tra lại bằng atomic update hoặc constraint.

## 13. SKIP LOCKED chỉ phù hợp với công việc có thể bỏ qua tạm thời

`SKIP LOCKED` giúp nhiều worker claim các hàng khác nhau mà không phải chờ hàng đang khóa. Nó phù hợp với queue khi các job độc lập và việc xử lý job sau trước job đang bận được chấp nhận.

Không dùng `SKIP LOCKED` cho:

- Báo cáo cần mọi hàng thỏa predicate.
- Đếm chính xác hoặc đối soát.
- Kiểm tra “không tồn tại hàng nào” để bảo vệ một bất biến.
- Luồng sự kiện phải giữ strict FIFO toàn cục.

Queue cần lease, token, retry, idempotency và dead-letter để phục hồi worker chết hoặc job lỗi. Nếu yêu cầu strict ordering theo một account, partition theo account và chỉ cho job đầu trong partition được claim; không bỏ qua hàng trước rồi xử lý hàng sau.

## 14. Batch và commit theo lô: cân bằng throughput với ranh giới nguyên tử

Batching giảm round trip và chi phí commit, nhưng tăng kích thước transaction, thời gian giữ lock và lượng công việc có thể rollback cùng lúc.

Ví dụ, cập nhật 10.000 hàng trong một transaction có thể hiệu quả về round trip nhưng giữ lock lâu và tạo log lớn. Chia thành 100 batch, mỗi batch 100 hàng, giảm thời gian giữ lock từng đợt nhưng làm thay đổi semantics: nếu batch 7 thất bại, sáu batch trước có thể đã commit.

Trước khi chia batch, xác định nghiệp vụ cần:

- **Atomic all-or-nothing:** mọi hàng phải cùng commit; không thể tùy tiện commit từng batch.
- **Progressive processing:** có thể chấp nhận từng phần hoàn tất; cần checkpoint, trạng thái tiến độ và idempotency.
- **Eventually complete:** worker có thể tiếp tục sau crash; cần retry và cơ chế phục hồi.

Nếu chia batch, lưu checkpoint hoặc keyset cursor ổn định, cập nhật trạng thái batch trong cùng transaction và bảo đảm chạy lại không tạo tác động trùng. Tránh `OFFSET` trên tập dữ liệu thay đổi liên tục nếu nó có thể làm bỏ sót hoặc xử lý lặp hàng.

## 15. Retry là phục hồi có giới hạn, không phải cách che lỗi

Deadlock victim và serialization failure thường cần rollback rồi retry toàn bộ transaction. Nhưng retry vô hạn hoặc retry ngay có thể tạo retry storm.

Một chính sách cơ bản:

```text
for attempt in 1..MAX_ATTEMPTS:
    try:
        BEGIN
        đọc trạng thái mới
        kiểm tra bất biến
        thực hiện thay đổi
        COMMIT
        return success
    catch retryable_concurrency_error:
        ROLLBACK
        if attempt == MAX_ATTEMPTS:
            return retry_exhausted
        delay = random(0, min(MAX_DELAY, BASE_DELAY * 2^(attempt - 1)))
        wait outside transaction
```

Chỉ retry lỗi được phân loại rõ là có thể phục hồi. Không retry lỗi nghiệp vụ như không đủ số dư, không đủ tồn kho hoặc unique violation không phải race có thể phục hồi. Dùng deadline, retry budget và jitter. Không ngủ trong transaction hoặc giữ connection khi backoff.

Nếu commit đã xảy ra nhưng response bị mất, kết quả là ambiguous. Dùng idempotency key để tra cứu thao tác trước khi gửi lại; không mặc định lỗi kết nối đồng nghĩa transaction chưa commit.

## 16. Đo trade-off bằng tải đồng thời có kiểm soát

So sánh trước/sau tối ưu cần dùng cùng dữ liệu, workload, cấu hình và thời gian chạy. Tăng số thread mà không kiểm soát phân phối key có thể làm kết quả không đại diện cho production.

Một kế hoạch benchmark nên có:

1. **Workload không tranh chấp:** các transaction cập nhật những hàng khác nhau để đo throughput cơ sở.
2. **Workload tranh chấp thấp:** nhiều request cùng cập nhật một số ít key để xem behavior khi contention bắt đầu.
3. **Workload hot key:** phần lớn request chạm cùng một tài khoản/hàng để đo giới hạn tuần tự hóa.
4. **Workload range/predicate:** insert/update vào khoảng mà transaction khác đang đọc hoặc khóa.
5. **Burst và steady state:** kiểm tra cả tải tăng đột ngột và tải ổn định.
6. **Failure injection:** tạo deadlock, timeout, worker crash hoặc mất kết nối để kiểm tra retry và phục hồi.

Với mỗi kịch bản, ghi throughput commit thành công, p95/p99 latency, lock wait, abort/retry rate, connection pool wait và kết quả kiểm tra bất biến.

### 16.1. Không chỉ benchmark đường đi thành công

Một tối ưu có thể làm transaction thành công nhanh hơn nhưng khiến lỗi xung đột tăng mạnh. Nếu benchmark chỉ đếm request nhận HTTP 200 hoặc số statement thực thi, nó có thể đếm cả request bị retry hoặc xử lý lặp.

Hãy đếm kết quả nghiệp vụ duy nhất: một order được tạo, một payment được ghi nhận, một reservation hợp lệ hoặc một job hoàn tất. Tách request gốc khỏi số attempt.

## 17. Kiểm thử correctness bằng hai hoặc nhiều transaction

Unit test chạy tuần tự không phát hiện lost update, write skew hoặc phantom. Cần kiểm thử bằng nhiều connection độc lập và điều khiển thứ tự qua barrier/latch.

### 17.1. Test lost update

1. T1 và T2 cùng đọc một giá trị ban đầu.
2. Cả hai tính toán dựa trên giá trị đó.
3. Cho T1 ghi và commit.
4. Cho T2 ghi sau.
5. Xác nhận atomic update hoặc version check bảo toàn cả hai thay đổi hoặc từ chối một conflict để ứng dụng xử lý.

### 17.2. Test write skew

1. T1 và T2 cùng đọc số lượng hàng thỏa predicate.
2. Hai transaction cập nhật hai hàng khác nhau.
3. Cho cả hai thử commit.
4. Xác nhận guard/counter/Serializable giữ bất biến.

### 17.3. Test phantom

1. T1 đọc một range hoặc xác nhận chưa có hàng.
2. T2 insert hoặc cập nhật hàng để nó thỏa predicate.
3. Cho T1 đọc lại hoặc commit.
4. Xác nhận constraint/range protection/Serializable đáp ứng quy tắc.

### 17.4. Test retry và idempotency

1. Cho transaction thất bại do deadlock hoặc serialization conflict.
2. Xác nhận transaction cũ được rollback.
3. Retry toàn bộ đơn vị công việc với dữ liệu mới.
4. Giả lập mất response sau commit.
5. Gửi lại cùng idempotency key.
6. Xác nhận chỉ một tác động nghiệp vụ được ghi nhận.

Sau mỗi test, truy vấn database để kiểm tra bất biến cuối cùng. Không coi test pass chỉ vì không có exception.

## 18. Tối ưu theo DBMS mà vẫn giữ semantics

Các engine có cơ chế khác nhau, nên không có một câu SQL hoặc lock hint tối ưu giống nhau trên mọi DBMS.

| DBMS | Cơ chế thường dùng | Điều cần giữ khi tối ưu |
|---|---|---|
| PostgreSQL | MVCC, row lock, SSI ở Serializable, `SKIP LOCKED`, exclusion constraint | SIREAD/SSI không phải gap lock chặn insert; retry SQLSTATE `40001`/`40P01` đúng transaction |
| MySQL InnoDB | MVCC, record/gap/next-key lock, locking read, unique/FK | Lock footprint phụ thuộc index và isolation; `READ COMMITTED`/`REPEATABLE READ` khác nhau |
| SQL Server | Locking, row versioning/RCSI, Snapshot Isolation, key-range lock | Kiểm tra RCSI, snapshot setting, lock escalation và semantics của hints như `READPAST` |
| Oracle | Consistent read qua undo, row lock, Serializable | Xử lý `ORA-08177`, row lock và DDL implicit commit theo quy tắc Oracle |

Khi chuyển hoặc tối ưu trên một engine, hãy kiểm tra phiên bản, cấu hình, execution plan và lock diagnostics. Tên isolation level hoặc lock hint gần giống không đảm bảo cùng kết quả.

## 19. Ví dụ: tối ưu đặt chỗ mà không cho phép đặt trùng

Một cách triển khai yếu là:

```sql
BEGIN;

SELECT count(*)
FROM reservation
WHERE room_id = :room_id
  AND starts_at < :requested_end
  AND ends_at > :requested_start;

-- Nếu count = 0 thì INSERT.

COMMIT;
```

Nếu nhiều transaction cùng thấy `count = 0`, chúng có thể cùng insert khoảng thời gian chồng lấn. Tăng throughput bằng cách bỏ khóa hoặc hạ isolation có thể làm lỗi này dễ xảy ra hơn.

Với PostgreSQL, exclusion constraint có thể diễn đạt trực tiếp bất biến:

```sql
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE reservation (
    reservation_id bigint PRIMARY KEY,
    room_id        bigint NOT NULL,
    starts_at      timestamptz NOT NULL,
    ends_at        timestamptz NOT NULL,
    CONSTRAINT ck_reservation_time CHECK (ends_at > starts_at),
    CONSTRAINT ex_room_no_overlap
        EXCLUDE USING gist (
            room_id WITH =,
            tstzrange(starts_at, ends_at, '[)') WITH &&
        )
);
```

Sau khi constraint bảo vệ overlap, ứng dụng không cần dựa riêng vào một lần `SELECT count(*)` để quyết định. Có thể giữ transaction ngắn và xử lý exclusion violation thành kết quả “khung giờ đã được đặt”. Với DBMS khác, chọn key-range lock, guard row hoặc Serializable theo semantics của engine.

## 20. Các dấu hiệu tối ưu đã làm yếu correctness

Sau khi triển khai một thay đổi hiệu năng, cần chú ý những dấu hiệu sau:

- Số hàng trùng hoặc unique violation biến mất bất thường sau khi bỏ unique constraint.
- Tổng counter không còn khớp với dữ liệu chi tiết.
- Tồn kho hoặc số dư vượt giới hạn dù mọi request đều báo thành công.
- Một transaction ghi đè thay đổi đã commit của transaction khác.
- Job được xử lý lặp hoặc bị đánh dấu `DONE` dù tác động ngoài chưa hoàn tất.
- Báo cáo có số lượng thay đổi theo worker đang giữ lock.
- Read-after-write thỉnh thoảng trả dữ liệu cũ do cache/replica.
- Throughput tăng nhưng retry, abort hoặc tail latency tăng nhanh.
- Tỷ lệ lỗi dữ liệu chỉ xuất hiện dưới tải cao, không tái hiện trong unit test tuần tự.

Những dấu hiệu này cần được đối chiếu với transaction timeline, execution plan, lock graph và lịch sử thay đổi cấu hình. Đừng chỉ tăng timeout hoặc retry để che triệu chứng.

## 21. Quy trình quyết định trước khi áp dụng tối ưu

Với mỗi đề xuất thay đổi hiệu năng, hãy trả lời theo trình tự:

1. **Nút thắt hiện tại là gì?** CPU, I/O, lock wait, connection pool, network, hot row hay retry storm?
2. **Bất biến nào liên quan?** Ghi rõ điều kiện phải luôn đúng sau commit.
3. **Transaction hiện tại bảo vệ bất biến bằng gì?** Constraint, row/range lock, version, Serializable hay giao thức ứng dụng?
4. **Tối ưu thay đổi semantics nào?** Isolation, visibility, lock footprint, transaction boundary, cache freshness hay delivery guarantee?
5. **Cơ chế nào thay thế bảo đảm cũ?** Atomic update, unique/exclusion constraint, guard row, token, outbox hoặc version check?
6. **Có đường ghi nào bỏ qua cơ chế mới không?** Batch, admin script, worker, service khác và native SQL đều phải được xét.
7. **Có concurrency test chứng minh không?** Tái hiện lost update, write skew, phantom, duplicate request hoặc worker crash phù hợp.
8. **Benchmark đo kết quả nghiệp vụ hay chỉ số kỹ thuật?** Đếm commit hợp lệ, không chỉ số attempt.
9. **Có thể rollback thay đổi không?** Chuẩn bị quan sát và đối soát nếu canary phát hiện sai lệch.

Nếu chưa trả lời được bất biến nào đang được bảo vệ, chưa nên bỏ cơ chế khóa hoặc constraint chỉ để giảm thời gian chờ.

## 22. Những điểm cần ghi nhớ

- Throughput chỉ có ý nghĩa khi các kết quả commit vẫn đúng với bất biến nghiệp vụ.
- Hạ isolation, bỏ lock hoặc xóa constraint có thể làm xuất hiện lost update, write skew, phantom, duplicate hoặc trạng thái sai.
- Atomic conditional update thường giảm read-modify-write mà vẫn bảo vệ điều kiện trên một hàng; phải kiểm tra row count.
- Optimistic locking chuyển một phần chi phí chờ thành phát hiện conflict; cần version được cập nhật bởi mọi đường ghi.
- Constraint chuyên biệt như UNIQUE, FOREIGN KEY, CHECK và exclusion bảo vệ dữ liệu ở database, kể cả khi có nhiều caller.
- Bất biến nhiều hàng cần guard/counter, range protection hoặc Serializable; một phép đếm trước khi ghi không tự bảo vệ concurrency.
- Rút ngắn transaction bằng cách chuyển công việc ngoài database ra sau commit, nhưng giữ các thay đổi cần atomicity trong cùng transaction.
- Index phù hợp giảm scan và thời gian giữ khóa; phải xác nhận execution plan và lock footprint thực tế.
- Cache, replica và xử lý bất đồng bộ chỉ an toàn khi độ trễ nhất quán được nghiệp vụ chấp nhận và có cơ chế read-your-writes khi cần.
- `SKIP LOCKED` phù hợp cho worker queue có thể bỏ qua hàng đang bận, không phù hợp cho báo cáo cần đầy đủ hoặc strict FIFO.
- Batch nhỏ có thể giảm lock duration nhưng làm thay đổi all-or-nothing; cần checkpoint và idempotency nếu chia transaction.
- Retry phải có phân loại lỗi, giới hạn, backoff/jitter và chạy lại đúng đơn vị transaction.
- Benchmark phải đo commit hợp lệ, tail latency, lock wait, retry và kiểm tra bất biến dưới tải đồng thời.

Tối ưu thông lượng đúng cách là giảm chi phí để đạt cùng một kết quả nghiệp vụ, hoặc thay đổi hợp đồng nhất quán một cách có chủ đích và được chấp nhận. Nếu một tối ưu làm mất khả năng bảo vệ bất biến, throughput cao hơn chỉ che giấu lỗi cho đến khi dữ liệu hoặc khách hàng chịu hậu quả. Hãy giữ tính đúng đắn làm điều kiện đầu vào, rồi đo và tối ưu cơ chế thực thi quanh điều kiện đó.
