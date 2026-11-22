# PostgreSQL: khóa hàng, khóa tư vấn và SERIALIZABLE với SSI

PostgreSQL cung cấp nhiều cơ chế phối hợp transaction, mỗi cơ chế giải quyết một loại xung đột khác nhau. Khóa hàng bảo vệ các bản ghi cụ thể khi transaction đọc rồi cập nhật. Khóa tư vấn (advisory lock) cho phép ứng dụng phối hợp những tài nguyên được định danh theo quy ước riêng. Ở mức `SERIALIZABLE`, PostgreSQL dùng Serializable Snapshot Isolation (SSI) để phát hiện các phụ thuộc đọc–ghi có thể tạo ra lịch không khả tuần tự.

Ba cơ chế này không thay thế lẫn nhau. Khóa hàng phù hợp khi cần bảo vệ hàng cụ thể; advisory lock phù hợp khi nhiều luồng phải cùng tuân thủ một khóa logic; SSI phù hợp khi tính đúng đắn phụ thuộc vào toàn bộ quan hệ đọc–ghi và predicate mà transaction đã quan sát. Thiết kế tốt bắt đầu từ invariant nghiệp vụ rồi chọn đúng cơ chế và xử lý các lỗi cạnh tranh có thể xảy ra.

## 1. Bức tranh các loại khóa trong PostgreSQL

PostgreSQL có khóa ở nhiều cấp:

- **Table-level locks:** điều phối các thao tác trên quan hệ (bảng, index và một số đối tượng liên quan). Ví dụ, `INSERT`, `UPDATE` và `DELETE` lấy `ROW EXCLUSIVE` trên bảng; locking read như `SELECT ... FOR UPDATE` lấy `ROW SHARE` trên bảng.
- **Row-level locks:** bảo vệ các hàng cụ thể khỏi thao tác cập nhật hoặc xóa xung đột. Các chế độ khóa hàng có mức xung đột khác nhau.
- **Predicate locks trong Serializable:** được PostgreSQL biểu diễn bằng khóa `SIReadLock` để theo dõi dữ liệu đã đọc và phát hiện phụ thuộc. Đây là cơ chế theo dõi, không phải khóa chặn thông thường.
- **Advisory locks:** khóa do ứng dụng chủ động yêu cầu bằng một hoặc hai số nguyên làm khóa định danh. PostgreSQL không tự hiểu tài nguyên nghiệp vụ phía sau các con số đó.

Không nên suy luận rằng `SELECT ... FOR UPDATE` chỉ lấy đúng một khóa hàng và không lấy khóa nào khác. Một câu lệnh có thể đồng thời lấy khóa bảng, khóa hàng, khóa index hoặc các khóa phục vụ constraint. Cần phân biệt loại khóa và tài nguyên mà mỗi khóa bảo vệ.

## 2. Các chế độ khóa hàng

PostgreSQL cung cấp bốn chế độ khóa hàng thường gặp:

| Chế độ | Ý nghĩa chính | Các thao tác khác có thể bị chặn |
|---|---|---|
| `FOR KEY SHARE` | Bảo vệ khóa được tham chiếu khỏi bị xóa hoặc thay đổi. | `DELETE` và `UPDATE` làm thay đổi khóa được tham chiếu. |
| `FOR SHARE` | Cho phép đọc chung và ngăn cập nhật/xóa hàng trong thời gian khóa. | Các chế độ cập nhật `FOR NO KEY UPDATE` và `FOR UPDATE`. |
| `FOR NO KEY UPDATE` | Khóa hàng để cập nhật nhưng không yêu cầu bảo vệ khóa định danh ở mức mạnh nhất. | Một cập nhật/xóa xung đột khác; tương thích với `FOR KEY SHARE`. |
| `FOR UPDATE` | Chế độ mạnh nhất, bảo vệ hàng khỏi mọi thao tác khóa hàng xung đột. | Các chế độ khóa hàng còn lại. |

Tóm tắt tương thích giữa các chế độ khóa hàng:

| Khóa đang giữ \ Yêu cầu | KEY SHARE | SHARE | NO KEY UPDATE | UPDATE |
|---|---:|---:|---:|---:|
| KEY SHARE | Có | Có | Có | Không |
| SHARE | Có | Có | Không | Không |
| NO KEY UPDATE | Có | Không | Không | Không |
| UPDATE | Không | Không | Không | Không |

`FOR UPDATE` thường là lựa chọn mạnh nhất, nhưng không phải lúc nào cũng cần thiết. Nếu chỉ cần ngăn một hàng bị xóa hoặc đổi khóa trong khi vẫn cho phép cập nhật cột không phải khóa, `FOR KEY SHARE` có thể phù hợp hơn. Chọn chế độ yếu nhất vẫn bảo vệ được invariant giúp tăng khả năng đồng thời.

PostgreSQL tự chọn chế độ khóa hàng cho `UPDATE` dựa trên loại cột được sửa. Cập nhật làm thay đổi khóa có thể lấy khóa mạnh hơn cập nhật cột không phải khóa. Các thao tác kiểm tra foreign key cũng sử dụng cơ chế bảo vệ hàng cha tương ứng để tránh một khóa được tham chiếu biến mất giữa lúc kiểm tra.

## 3. Dùng SELECT FOR UPDATE để bảo vệ hàng trước khi ghi

Ví dụ, hai request có thể cùng muốn trừ tiền từ một tài khoản. Transaction cần khóa hàng tài khoản trước khi đọc số dư và đưa ra quyết định:

```sql
BEGIN;

SELECT account_id, balance
FROM account
WHERE account_id = 42
FOR UPDATE;

-- Ứng dụng kiểm tra balance >= :amount.

UPDATE account
SET balance = balance - :amount
WHERE account_id = 42;

COMMIT;
```

`FOR UPDATE` khóa hàng được chọn đến khi transaction kết thúc. Một transaction khác muốn cập nhật hoặc lấy khóa xung đột trên cùng hàng phải chờ. Sau khi transaction đầu commit, transaction sau tiếp tục theo quy tắc isolation level và có thể nhìn thấy phiên bản mới.

Nếu chỉ cần thực hiện phép trừ có điều kiện, câu lệnh nguyên tử có thể ngắn gọn hơn:

```sql
UPDATE account
SET balance = balance - :amount
WHERE account_id = 42
  AND balance >= :amount;
```

Kiểm tra số hàng bị ảnh hưởng để biết phép trừ có thành công hay không. Dùng khóa hàng tường minh khi ứng dụng cần đọc nhiều giá trị, thực hiện nhiều bước quyết định rồi ghi trên cùng tài nguyên. Dùng cập nhật có điều kiện khi invariant có thể được bảo vệ trực tiếp trong một câu lệnh.

### 3.1. NOWAIT

`NOWAIT` yêu cầu PostgreSQL báo lỗi ngay nếu không lấy được khóa hàng cần thiết, thay vì chờ:

```sql
SELECT order_id, status
FROM orders
WHERE order_id = :order_id
FOR UPDATE NOWAIT;
```

Điều này hữu ích khi nghiệp vụ muốn trả về thông báo “đang được xử lý” hoặc để người dùng thử lại sau. Cần lưu ý `NOWAIT` áp dụng cho khóa hàng; khóa ở cấp bảng vẫn được yêu cầu theo cách thông thường và có thể phải chờ.

### 3.2. SKIP LOCKED

`SKIP LOCKED` bỏ qua hàng đang bị transaction khác khóa:

```sql
SELECT job_id
FROM job_queue
WHERE status = 'PENDING'
ORDER BY job_id
LIMIT 20
FOR UPDATE SKIP LOCKED;
```

Đây là lựa chọn phù hợp cho hàng đợi nhiều worker: mỗi worker có thể lấy các hàng khác nhau mà không phải chờ hàng đang được worker khác claim. Tuy nhiên, kết quả không phải một ảnh chụp đầy đủ của mọi hàng phù hợp. Nó bỏ qua các hàng đang khóa và không bảo đảm FIFO tuyệt đối.

Giống `NOWAIT`, `SKIP LOCKED` chỉ thay đổi cách xử lý chờ khóa hàng; khóa bảng vẫn được lấy bình thường. Hãy cập nhật trạng thái claim và commit trong cùng transaction, rồi xử lý công việc bên ngoài transaction claim.

## 4. Khóa hàng không tự bảo vệ predicate

Giả sử một lớp học còn sức chứa và transaction kiểm tra số đăng ký:

```sql
SELECT COUNT(*)
FROM enrollment
WHERE class_id = :class_id;
```

Nếu transaction khác thêm một hàng đăng ký mới, câu truy vấn lặp lại có thể trả về kết quả khác. Khóa những hàng đã tìm thấy không nhất thiết ngăn hàng mới xuất hiện. Đây là vấn đề phantom hoặc phụ thuộc trên predicate.

`SELECT ... FOR UPDATE` khóa các hàng được chọn, không phải một cam kết chung rằng mọi hàng tương lai thỏa điều kiện đều bị chặn. Nếu invariant phụ thuộc vào tập hàng hoặc kết quả tổng hợp, có thể dùng:

- Một hàng điều phối đại diện cho lớp học và khóa hàng đó trước khi đếm/cập nhật.
- Cập nhật nguyên tử trên một hàng bộ đếm có điều kiện sức chứa.
- Một ràng buộc dữ liệu phù hợp.
- `SERIALIZABLE` để PostgreSQL theo dõi các phụ thuộc đọc–ghi.

Không dùng khóa hàng như một giải pháp thay thế tự động cho khóa predicate. Hãy xác định rõ transaction khác có thể thêm hàng mới làm thay đổi quyết định hay không.

## 5. Khóa tư vấn (advisory locks) là gì?

Advisory lock là khóa do ứng dụng yêu cầu dựa trên một khóa logic. PostgreSQL cung cấp các hàm khóa tư vấn với một khóa 64-bit hoặc một cặp số nguyên 32-bit. Database không gắn khóa đó tự động với một hàng hoặc bảng; ý nghĩa của khóa do ứng dụng quy ước.

Ví dụ, chỉ cho phép một tiến trình tính lại báo cáo cho khách hàng 123 tại một thời điểm:

```sql
SELECT pg_advisory_xact_lock(7001, 123);

-- Chỉ một transaction có thể giữ khóa logic (7001, 123).
-- Thực hiện việc tính lại báo cáo ở đây.
```

Hai số nguyên có thể dùng để phân vùng namespace: `7001` đại diện cho loại tài nguyên “rebuild report”, còn `123` là customer ID. Điều này giảm nguy cơ hai module khác nhau vô tình dùng cùng khóa cho hai ý nghĩa không liên quan.

Các transaction khác muốn phối hợp cùng tài nguyên phải yêu cầu đúng cùng khóa. Nếu một luồng bỏ qua advisory lock, khóa tư vấn không ngăn luồng đó sửa dữ liệu.

## 6. Khóa tư vấn theo transaction và theo session

PostgreSQL cung cấp hai vòng đời chính:

| Loại | Ví dụ hàm | Thời điểm nhả khóa |
|---|---|---|
| Transaction-level | `pg_advisory_xact_lock`, `pg_try_advisory_xact_lock` | Tự động nhả khi transaction commit hoặc rollback. |
| Session-level | `pg_advisory_lock`, `pg_try_advisory_lock` | Khi gọi hàm unlock tương ứng hoặc session kết thúc. Không tự nhả khi transaction rollback. |

### 6.1. Transaction-level advisory lock

```sql
BEGIN;

SELECT pg_advisory_xact_lock(7001, 123);

UPDATE report_state
SET status = 'BUILDING'
WHERE customer_id = 123;

COMMIT;
```

Khóa tự được giải phóng ở cuối transaction. Đây thường là lựa chọn an toàn khi vùng phối hợp trùng với một đơn vị transaction và tránh quên unlock.

### 6.2. Session-level advisory lock

```sql
SELECT pg_advisory_lock(7001, 123);

-- Thực hiện nhiều transaction hoặc thao tác theo quy trình dài.

SELECT pg_advisory_unlock(7001, 123);
```

Khóa session tồn tại qua commit và rollback. Điều này hữu ích khi cần khóa một tài nguyên logic xuyên suốt nhiều transaction, nhưng phải giải phóng tường minh. Nếu connection được trả về pool trong khi session lock vẫn còn, request khác có thể nhận một session đang giữ khóa và gây ra hành vi khó hiểu. Với pool, cần quản lý session lock rất cẩn thận; transaction-level thường dễ kiểm soát hơn.

### 6.3. Try-lock

Các hàm `pg_try_advisory_xact_lock` và `pg_try_advisory_lock` trả về boolean thay vì chờ vô hạn:

```sql
SELECT pg_try_advisory_xact_lock(7001, 123);
```

Nếu trả `true`, transaction đã lấy được khóa; nếu `false`, một session khác đang giữ khóa xung đột. Ứng dụng có thể bỏ qua công việc, trả trạng thái bận hoặc lên lịch thử lại.

## 7. Thiết kế khóa logic và tránh deadlock

Advisory lock có thể được yêu cầu theo nhiều thứ tự giống khóa hàng. Nếu transaction T1 giữ khóa logic A rồi chờ B, trong khi T2 giữ B rồi chờ A, deadlock vẫn xảy ra.

Hãy định nghĩa thứ tự toàn cục cho các khóa logic, ví dụ:

```text
1. Khóa tenant
2. Khóa customer theo ID tăng dần
3. Khóa report theo loại và ID
```

Mọi luồng yêu cầu nhiều advisory lock phải lấy chúng theo cùng thứ tự. Cũng cần tính đến việc một transaction kết hợp advisory lock với khóa hàng hoặc khóa bảng. Nếu một luồng lấy advisory lock rồi khóa hàng, còn luồng khác khóa hàng rồi lấy advisory lock, hai loại khóa có thể tạo thành vòng chờ chung.

Một số nguyên tắc:

- Dùng namespace riêng cho từng module hoặc loại tài nguyên.
- Chuẩn hóa cách ánh xạ ID nghiệp vụ sang khóa advisory.
- Không tạo khóa từ hash có khả năng va chạm mà không xem xét hậu quả; hai tài nguyên khác nhau có thể bị tuần tự hóa không cần thiết.
- Lấy nhiều khóa theo thứ tự ổn định.
- Dùng transaction-level lock nếu chỉ cần bảo vệ trong một transaction.
- Không giữ session-level lock qua connection pool nếu không có cơ chế cleanup chắc chắn.
- Vẫn xử lý deadlock và timeout vì advisory lock không tự loại bỏ vòng chờ.

## 8. Khóa hàng, advisory lock và SSI khác nhau thế nào?

| Cơ chế | Tài nguyên được bảo vệ | Có chặn transaction khác? | Ai phải tuân thủ? | Dùng khi nào? |
|---|---|---|---|---|
| Row-level lock | Hàng cụ thể trong bảng. | Có, nếu yêu cầu khóa xung đột. | Các thao tác database tương ứng bị engine điều phối tự động. | Cập nhật hàng, bảo vệ trạng thái của bản ghi. |
| Advisory lock | Tài nguyên logic do ứng dụng đặt tên bằng khóa số. | Có, nếu cùng yêu cầu khóa. | Mọi luồng ứng dụng liên quan phải dùng cùng quy ước. | Công việc logic không ánh xạ trực tiếp vào một hàng, singleton job, rebuild tài nguyên. |
| SSI trong SERIALIZABLE | Quan hệ đọc–ghi và predicate mà transaction quan sát. | Predicate SIREAD không chặn writer theo cách khóa thông thường; engine có thể hủy transaction khi phát hiện nguy cơ không khả tuần tự. | Mọi transaction liên quan phải chạy trong Serializable để được kiểm soát đầy đủ theo cơ chế này. | Invariant phụ thuộc nhiều hàng hoặc predicate, cần bảo đảm serializability. |

Không dùng advisory lock để thay thế FK, unique constraint hoặc các ràng buộc có thể được database thực thi trực tiếp. Constraint bảo vệ dữ liệu kể cả khi có client không tuân thủ giao thức advisory lock.

## 9. SERIALIZABLE trong PostgreSQL dùng SSI

PostgreSQL hỗ trợ mức cô lập `SERIALIZABLE` bằng kỹ thuật Serializable Snapshot Isolation (SSI). Các transaction vẫn đọc snapshot nhất quán như snapshot isolation, nhưng PostgreSQL theo dõi phụ thuộc đọc–ghi để phát hiện những lịch có thể tạo chu trình tuần tự hóa.

Điểm quan trọng:

- Các lần đọc thông thường không cần chặn writer như khóa hàng truyền thống.
- PostgreSQL ghi nhận vùng dữ liệu đã đọc bằng predicate lock nội bộ gọi là `SIReadLock`.
- Khi transaction khác ghi dữ liệu có thể làm thay đổi kết quả đọc, PostgreSQL ghi nhận read–write anti-dependency.
- Nếu các phụ thuộc tạo thành cấu trúc nguy hiểm có thể dẫn đến chu trình, PostgreSQL hủy một transaction để giữ bảo đảm Serializable.
- Ứng dụng nhận lỗi serialization và phải retry toàn bộ transaction nếu nghiệp vụ cho phép.

Predicate lock trong SSI là cơ chế theo dõi phụ thuộc, không phải khóa chặn thông thường. Một writer không nhất thiết phải chờ vì một `SIReadLock`; thay vào đó, hệ quản trị có thể để các transaction chạy rồi hủy một transaction khi phát hiện lịch không an toàn.

## 10. Ví dụ write skew được SSI ngăn chặn

Giả sử ca trực phải luôn có ít nhất một bác sĩ đang trực:

```text
on_call(A) + on_call(B) >= 1
```

Ban đầu cả A và B đều đang trực. Hai transaction chạy đồng thời ở mức Serializable:

```sql
-- Transaction T1
BEGIN ISOLATION LEVEL SERIALIZABLE;

SELECT COUNT(*)
FROM doctor
WHERE on_call = TRUE;

UPDATE doctor
SET on_call = FALSE
WHERE doctor_id = 'A';

COMMIT;
```

```sql
-- Transaction T2
BEGIN ISOLATION LEVEL SERIALIZABLE;

SELECT COUNT(*)
FROM doctor
WHERE on_call = TRUE;

UPDATE doctor
SET on_call = FALSE
WHERE doctor_id = 'B';

COMMIT;
```

Mỗi transaction đọc cùng snapshot và cập nhật một hàng riêng. Với Snapshot Isolation thông thường, cả hai có thể commit và làm invariant sai. Ở PostgreSQL Serializable, SSI theo dõi các phụ thuộc đọc–ghi ngược chiều. PostgreSQL sẽ từ chối ít nhất một transaction khi nhận diện lịch có nguy cơ không khả tuần tự.

Lỗi thường được ứng dụng nhận là SQLSTATE `40001` (`serialization_failure`). Transaction bị từ chối không được coi là đã commit một phần; ứng dụng phải bắt đầu lại toàn bộ đơn vị transaction với snapshot mới.

## 11. Retry serialization failure đúng cách

Không chỉ chạy lại câu lệnh cuối. Những lần đọc trước đó đã tạo ra quyết định nghiệp vụ, và snapshot cũ có thể không còn hợp lệ. Hãy rollback transaction lỗi, bắt đầu transaction mới, đọc lại dữ liệu và thực hiện lại toàn bộ logic.

Pseudocode:

```text
for attempt in 1..MAX_RETRIES:
    try:
        BEGIN ISOLATION LEVEL SERIALIZABLE

        read business state
        validate invariant
        write changes

        COMMIT
        return SUCCESS

    catch SQLSTATE 40001:
        ROLLBACK if transaction is still open
        wait with bounded backoff and jitter

return RETRYABLE_FAILURE
```

Các điểm cần nhớ:

- Giới hạn số lần retry; không lặp vô hạn khi workload luôn xung đột.
- Dùng backoff và jitter để các transaction bị hủy không lập tức va chạm lại cùng thời điểm.
- Retry toàn transaction, bao gồm các lần đọc và kiểm tra invariant.
- Không thực hiện email, thanh toán hoặc tác dụng phụ ngoài database trước commit nếu thao tác không idempotent.
- Dùng idempotency key hoặc transactional outbox để xử lý tác dụng phụ sau commit.
- Phân biệt `40001` với lỗi dữ liệu, quyền truy cập hoặc lỗi nghiệp vụ không nên retry.

SSI có thể hủy transaction dù không có transaction nào đang chờ khóa hàng. Vì vậy, chỉ theo dõi lock wait sẽ không phát hiện đầy đủ vấn đề; cần theo dõi lỗi serialization trong ứng dụng.

## 12. Read-only deferrable transaction

PostgreSQL có tùy chọn `DEFERRABLE` dành cho transaction `SERIALIZABLE READ ONLY`:

```sql
BEGIN TRANSACTION
ISOLATION LEVEL SERIALIZABLE
READ ONLY
DEFERRABLE;

SELECT ...;

COMMIT;
```

Transaction có thể chờ khi bắt đầu để nhận một snapshot an toàn (safe snapshot). Sau khi có snapshot an toàn, transaction đọc-only có thể chạy mà không có nguy cơ bị hủy do serialization anomaly theo SSI. Đổi lại, thời gian bắt đầu có thể phải chờ.

Đây là lựa chọn hữu ích cho báo cáo hoặc tác vụ phân tích dài cần một kết quả Serializable và không ghi dữ liệu. `DEFERRABLE` không áp dụng như một cách tăng an toàn cho transaction ghi; nó được thiết kế cho transaction Serializable chỉ đọc.

## 13. Predicate lock và ảnh hưởng của kế hoạch truy vấn

SSI cần theo dõi những vùng dữ liệu transaction đã đọc. PostgreSQL có thể ghi nhận predicate lock ở mức tuple, page hoặc relation tùy cách truy cập và áp lực tài nguyên. Các khóa `SIReadLock` không chặn writer như khóa hàng thông thường; chúng giúp xác định có phụ thuộc đọc–ghi hay không.

Kế hoạch truy vấn có thể ảnh hưởng độ chi tiết của theo dõi:

- Index scan có thể cho phép theo dõi phạm vi đọc chi tiết hơn.
- Sequential scan có thể dẫn đến predicate lock ở mức relation, khiến nhiều thay đổi trên bảng được xem là có liên quan.
- Khi số lượng predicate lock vượt ngưỡng cấu hình, PostgreSQL có thể gộp nhiều khóa chi tiết thành khóa phạm vi rộng hơn.

Khóa theo dõi rộng hơn có thể làm tăng serialization failure bảo thủ (false positive) vì hệ thống không phân biệt được hai vùng dữ liệu nhỏ hơn. Điều đó không làm mất bảo đảm Serializable; nó có thể khiến một số transaction bị hủy nhiều hơn.

Index phù hợp có thể cải thiện hiệu năng và giúp theo dõi phạm vi đọc chi tiết hơn, nhưng không nên thêm index chỉ dựa trên giả định rằng SSI sẽ luôn tạo ít xung đột hơn. Hãy kiểm tra execution plan, `SIReadLock` và tỷ lệ lỗi serialization trên workload thực tế.

## 14. SSI không loại bỏ mọi deadlock

SSI phát hiện nguy cơ không khả tuần tự, nhưng PostgreSQL vẫn có thể gặp deadlock do khóa tường minh hoặc khóa do thao tác ghi lấy tự động. Ví dụ:

- Hai transaction lấy `FOR UPDATE` trên hai hàng theo thứ tự ngược nhau.
- Một transaction lấy advisory lock rồi khóa hàng; transaction khác làm ngược lại.
- Trigger hoặc FK tạo thêm khóa trên bảng khác.
- Nhiều transaction cập nhật index hoặc hàng liên quan theo thứ tự khác nhau.

Do đó, Serializable và SSI không thay thế thiết kế thứ tự khóa. Ứng dụng vẫn cần xử lý SQLSTATE `40P01` (`deadlock_detected`) riêng với `40001` (`serialization_failure`). Cả hai có thể retry toàn transaction khi thao tác an toàn để thử lại, nhưng nguyên nhân và cách điều tra khác nhau.

## 15. Quan sát khóa và phụ thuộc trong PostgreSQL

Các view hệ thống giúp điều tra khóa đang chờ và phụ thuộc:

### 15.1. Session và truy vấn đang hoạt động

```sql
SELECT pid,
       state,
       wait_event_type,
       wait_event,
       query,
       pg_blocking_pids(pid) AS blocking_pids
FROM pg_stat_activity
WHERE state <> 'idle';
```

`pg_blocking_pids(pid)` cho biết các process đang chặn process đó. `wait_event_type = 'Lock'` giúp nhận diện session đang chờ khóa.

### 15.2. Xem khóa trong pg_locks

```sql
SELECT locktype,
       relation::regclass AS relation,
       page,
       tuple,
       virtualtransaction,
       transactionid,
       mode,
       granted,
       pid
FROM pg_locks
ORDER BY granted, pid;
```

`pg_locks` hiển thị khóa relation, transaction ID, advisory và `SIReadLock` cùng nhiều loại tài nguyên khác. Khóa hàng thông thường thường không xuất hiện như một hàng khóa đang được giữ trong view này vì thông tin khóa hàng được lưu trong tuple; process đang chờ khóa hàng thường hiển thị dưới dạng chờ transaction ID của transaction giữ hàng. Vì vậy, cần kết hợp `pg_locks`, `pg_stat_activity` và `pg_blocking_pids()` để hiểu chuỗi chờ.

### 15.3. Ghi log chờ khóa và deadlock

Các cấu hình như `log_lock_waits` và `deadlock_timeout` giúp ghi nhận những lần chờ đủ lâu và hỗ trợ điều tra deadlock. Điều chỉnh cấu hình cần cân nhắc lượng log và tải hệ thống. Khi có deadlock, log PostgreSQL thường cung cấp thông tin về process, câu lệnh và các tài nguyên tạo vòng chờ.

Đối với SSI, cần theo dõi số transaction thất bại với SQLSTATE `40001` ở tầng ứng dụng. `pg_locks` có thể cho thấy `SIReadLock`, nhưng lỗi serialization mới là tín hiệu trực tiếp để đo mức độ retry mà workload đang tạo ra.

## 16. Chọn cơ chế nào cho từng nhu cầu?

| Nhu cầu | Cơ chế gợi ý | Lý do |
|---|---|---|
| Cập nhật một tài khoản hoặc đơn hàng cụ thể | `SELECT ... FOR UPDATE` hoặc `UPDATE` có điều kiện | Bảo vệ hàng cụ thể và cho phép transaction khác chờ. |
| Không muốn chờ hàng đang bận | `FOR UPDATE NOWAIT` | Trả lỗi sớm để ứng dụng báo bận hoặc thử lại. |
| Nhiều worker lấy job khác nhau | `FOR UPDATE SKIP LOCKED` | Bỏ qua hàng đã được worker khác khóa. |
| Chỉ một tiến trình rebuild tài nguyên logic | Advisory transaction lock | Khóa một tài nguyên do ứng dụng định danh, không cần hàng đại diện. |
| Phối hợp một quy trình kéo dài qua nhiều transaction | Advisory session lock, với quản lý unlock nghiêm ngặt | Khóa tồn tại qua commit/rollback. |
| Invariant phụ thuộc nhiều hàng/predicate | `SERIALIZABLE` với SSI | Theo dõi phụ thuộc đọc–ghi và ngăn lịch không khả tuần tự. |
| Báo cáo chỉ đọc cần snapshot Serializable ổn định | `SERIALIZABLE READ ONLY DEFERRABLE` | Có thể chờ snapshot an toàn rồi chạy mà không bị hủy do SSI. |

Không nhất thiết chỉ chọn một cơ chế. Một transaction Serializable vẫn có thể dùng khóa hàng để bảo vệ tài nguyên cụ thể; một quy trình dùng advisory lock vẫn cần FK và unique constraint để bảo vệ dữ liệu. Tuy nhiên, kết hợp nhiều loại khóa làm tăng khả năng deadlock nếu không có thứ tự lấy khóa toàn cục.

## 17. Những sai lầm thường gặp

- Dùng `FOR UPDATE` cho mọi truy vấn dù chỉ cần đọc, làm giảm khả năng đồng thời.
- Nghĩ rằng khóa hàng bảo vệ cả những hàng chưa tồn tại thỏa predicate.
- Dùng advisory lock nhưng có một service khác sửa dữ liệu mà không lấy cùng khóa.
- Giữ session-level advisory lock rồi trả connection về pool mà quên unlock.
- Nghĩ `SKIP LOCKED` bảo đảm FIFO hoặc cho kết quả đầy đủ.
- Nghĩ `SERIALIZABLE` không bao giờ trả lỗi; SSI có thể hủy transaction để bảo vệ tính đúng đắn.
- Retry riêng câu lệnh cuối thay vì toàn bộ transaction sau `40001`.
- Chỉ theo dõi lock wait mà bỏ qua serialization failure.
- Thực hiện tác dụng phụ ngoài database trong transaction có thể bị retry.
- Cho rằng `pg_locks` luôn hiển thị trực tiếp mọi khóa hàng đang được giữ.

## 18. Quy trình thiết kế và kiểm chứng

Khi chọn cơ chế phối hợp cho một chức năng PostgreSQL:

1. Viết invariant nghiệp vụ và xác định nó phụ thuộc vào một hàng, nhiều hàng hay predicate.
2. Nếu chỉ bảo vệ hàng cụ thể, chọn chế độ row lock đủ dùng hoặc câu cập nhật nguyên tử.
3. Nếu tài nguyên logic không có hàng đại diện, cân nhắc advisory lock và quy ước namespace.
4. Nếu quyết định phụ thuộc vào nhiều lần đọc hoặc tập hàng, cân nhắc Serializable/SSI.
5. Xác định thứ tự lấy khóa giữa row lock, advisory lock, FK và trigger để giảm deadlock.
6. Thiết kế xử lý `40001`, `40P01`, timeout và lỗi nghiệp vụ riêng biệt.
7. Kiểm thử bằng nhiều connection với lịch đọc–ghi xen kẽ được điều khiển.
8. Quan sát `pg_stat_activity`, `pg_locks`, blocking PID, deadlock log và tỷ lệ serialization retry.
9. Đo thông lượng, độ trễ, thời gian chờ và tỷ lệ transaction bị hủy dưới tải đại diện.

Một bài kiểm thử SSI quan trọng là tạo write skew: hai transaction cùng đọc một invariant, sau đó cập nhật các hàng khác nhau. Chạy ở `REPEATABLE READ` để thấy snapshot isolation có thể cho phép kết quả không hợp lệ, rồi chạy ở `SERIALIZABLE` và xác nhận một transaction bị từ chối với lỗi serialization. Một bài kiểm thử advisory lock nên dùng hai session yêu cầu cùng khóa, xác nhận session thứ hai phải chờ hoặc nhận `false` với try-lock, rồi xác nhận khóa được giải phóng đúng lúc.

## 19. Checklist triển khai

- [ ] Đã xác định đúng tài nguyên cần bảo vệ: hàng, predicate hay tài nguyên logic.
- [ ] Đã chọn row lock mode yếu nhất vẫn đáp ứng yêu cầu.
- [ ] Đã hiểu `NOWAIT` và `SKIP LOCKED` chỉ thay đổi cách chờ khóa hàng, còn khóa bảng vẫn được lấy.
- [ ] Đã thiết kế namespace và thứ tự cho advisory lock.
- [ ] Đã ưu tiên transaction-level advisory lock khi vòng đời khóa trùng với transaction.
- [ ] Đã có cơ chế unlock và cleanup nếu dùng session-level advisory lock.
- [ ] Đã hiểu `SIReadLock` là cơ chế theo dõi phụ thuộc, không phải khóa chặn thông thường.
- [ ] Đã xử lý retry toàn transaction khi nhận SQLSTATE `40001`.
- [ ] Đã xử lý deadlock `40P01` và timeout riêng.
- [ ] Đã bảo vệ tác dụng phụ ngoài database bằng idempotency hoặc outbox.
- [ ] Đã kiểm thử write skew, khóa hàng, advisory lock và các thứ tự lấy khóa kết hợp.
- [ ] Đã giám sát `pg_stat_activity`, `pg_locks`, blocking PID và tỷ lệ serialization failure.

PostgreSQL cung cấp ba công cụ phối hợp bổ sung cho nhau: row lock bảo vệ hàng cụ thể, advisory lock bảo vệ tài nguyên logic theo quy ước ứng dụng, và SSI ở mức Serializable phát hiện các phụ thuộc đọc–ghi có thể tạo lịch không khả tuần tự. Chọn đúng cơ chế đòi hỏi hiểu phạm vi bảo vệ và cách giải phóng khóa, đồng thời thiết kế retry cho lỗi serialization/deadlock. Khi kết hợp chúng với constraint, cập nhật nguyên tử và quan sát runtime, ứng dụng có thể giữ invariant dưới tải đồng thời mà vẫn kiểm soát được thời gian chờ.
