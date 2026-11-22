# Tạo bế tắc có kiểm soát bằng thứ tự khóa đảo ngược

Deadlock (bế tắc) xảy ra khi các transaction chờ lẫn nhau theo một vòng khép kín. Một cách dễ quan sát hiện tượng này là dùng hai session và hai hàng: session A khóa hàng 1 rồi yêu cầu hàng 2; session B khóa hàng 2 rồi yêu cầu hàng 1. Mỗi session giữ tài nguyên mà session còn lại cần, vì vậy không session nào có thể tự tiếp tục.

Thí nghiệm này giúp hiểu cách hệ quản trị phát hiện deadlock, chọn transaction làm nạn nhân, giải phóng khóa và báo lỗi cho ứng dụng. Có thể dùng cùng một bài lab để so sánh PostgreSQL, MySQL InnoDB, SQL Server và Oracle. Cần chạy trên cơ sở dữ liệu thử nghiệm với dữ liệu riêng, bởi mục tiêu là cố ý tạo một vòng chờ.

## 1. Deadlock khác gì một lần chờ khóa thông thường?

Một transaction phải chờ khóa khi tài nguyên nó cần đang được transaction khác giữ. Chờ khóa đơn lẻ chưa phải deadlock: nếu transaction giữ khóa hoàn tất, khóa được nhả và transaction đang chờ có thể tiếp tục.

Deadlock xuất hiện khi có một chu trình chờ. Với hai transaction:

- T1 giữ khóa trên hàng A và chờ hàng B.
- T2 giữ khóa trên hàng B và chờ hàng A.
- T1 không thể tiếp tục trước khi T2 nhả B; T2 không thể tiếp tục trước khi T1 nhả A.

Đồ thị chờ (wait-for graph):

```text
T1 giữ A, chờ B  ───────>  T2 giữ B
       ^                     |
       |                     |
       +────── chờ A ────────+
```

Một chu trình trong đồ thị cho biết không transaction nào trong chu trình có thể tự giải phóng khóa bằng cách hoàn tất. Hệ quản trị cần phát hiện và hủy ít nhất một transaction để phá vòng chờ.

## 2. Chuẩn bị dữ liệu thử nghiệm

Tạo một bảng nhỏ với hai hàng. Chạy phần chuẩn bị một lần, trước khi mở hai session thí nghiệm:

```sql
CREATE TABLE deadlock_lab (
    id INTEGER PRIMARY KEY,
    touch_count INTEGER NOT NULL
);

INSERT INTO deadlock_lab (id, touch_count)
VALUES (1, 0), (2, 0);
```

Nếu bảng đã tồn tại, hãy dùng một tên riêng cho lần thí nghiệm hoặc xóa dữ liệu thử cũ sau khi chắc chắn không còn session nào giữ transaction. Không dùng bảng tài khoản, đơn hàng hay dữ liệu nghiệp vụ thật.

Mỗi câu `UPDATE` dưới đây sửa một hàng và giữ khóa ghi đến khi transaction kết thúc. Tăng `touch_count` chỉ để tạo một thao tác ghi có thể quan sát; cả hai transaction sẽ rollback nên giá trị ban đầu được giữ nguyên.

## 3. Kịch bản hai session theo thứ tự đảo ngược

Mở hai cửa sổ SQL độc lập, kết nối cùng database và cùng bảng `deadlock_lab`. Không chạy hai luồng trên cùng một connection: mỗi session cần transaction và khóa riêng.

### Bước 1: Session A khóa hàng 1

Trong session A, chạy:

```sql
BEGIN;

UPDATE deadlock_lab
SET touch_count = touch_count + 1
WHERE id = 1;
```

Lệnh hoàn tất. A đang giữ khóa ghi trên hàng 1 vì transaction chưa commit hoặc rollback.

### Bước 2: Session B khóa hàng 2

Trong session B, chạy:

```sql
BEGIN;

UPDATE deadlock_lab
SET touch_count = touch_count + 1
WHERE id = 2;
```

Lệnh cũng hoàn tất. B đang giữ khóa ghi trên hàng 2. Tại thời điểm này, hai transaction giữ hai hàng khác nhau nên chưa có ai phải chờ.

### Bước 3: A yêu cầu hàng 2

Quay lại session A và chạy:

```sql
UPDATE deadlock_lab
SET touch_count = touch_count + 1
WHERE id = 2;
```

Lệnh bị chặn vì B đang giữ khóa trên hàng 2. Để A tiếp tục chờ; không hủy hoặc commit session B.

### Bước 4: B yêu cầu hàng 1

Trong session B, chạy:

```sql
UPDATE deadlock_lab
SET touch_count = touch_count + 1
WHERE id = 1;
```

Lệnh này cần hàng 1 do A đang giữ. Bây giờ B chờ A, trong khi A đã chờ B. Vòng chờ hoàn chỉnh và bộ phát hiện deadlock của hệ quản trị sẽ chọn một nạn nhân.

### Bước 5: Quan sát nạn nhân và dọn dẹp

Một trong hai session nhận lỗi deadlock. Transaction còn lại được giải phóng khỏi trạng thái chờ và câu lệnh đang chờ có thể tiếp tục. Không giả định A hay B luôn là nạn nhân; quyết định phụ thuộc DBMS và trạng thái hệ thống.

Sau khi quan sát:

- Nếu transaction còn sống và câu lệnh của nó đã tiếp tục, chạy `ROLLBACK` trong session đó.
- Nếu transaction bị hủy tự động, xác nhận trạng thái session rồi rollback nếu hệ quản trị vẫn để transaction mở.
- Không chạy `COMMIT` trong thí nghiệm này. Mục tiêu là giải phóng mọi khóa và giữ `touch_count` ở giá trị ban đầu.

Kiểm tra kết quả bằng session thứ ba hoặc sau khi hai transaction đã kết thúc:

```sql
SELECT id, touch_count
FROM deadlock_lab
ORDER BY id;
```

Hai hàng phải có `touch_count = 0` sau khi cả hai transaction đã rollback. Nếu một hàng có giá trị khác 0, kiểm tra xem có session nào đã commit hoặc một phần thí nghiệm chưa được dọn dẹp.

## 4. Lịch thực thi và thời điểm deadlock hình thành

Toàn bộ lịch có thể biểu diễn như sau:

| Thứ tự | Session A | Session B | Trạng thái khóa |
|---:|---|---|---|
| 1 | `BEGIN` | | Chưa có khóa hàng. |
| 2 | Cập nhật hàng 1 | | A giữ hàng 1. |
| 3 | | `BEGIN` | A vẫn giữ hàng 1. |
| 4 | | Cập nhật hàng 2 | A giữ hàng 1, B giữ hàng 2. |
| 5 | Yêu cầu hàng 2, bị chặn | | A chờ B. |
| 6 | | Yêu cầu hàng 1, bị chặn | A chờ B và B chờ A: có chu trình. |
| 7 | Một transaction bị chọn làm nạn nhân | | Hệ quản trị rollback theo hành vi của nó và nhả khóa cần thiết. |
| 8 | Transaction còn lại được tiếp tục hoặc nhận lỗi theo DBMS | | Vòng chờ bị phá. |
| 9 | Rollback transaction còn lại | | Tất cả khóa của bài lab được giải phóng. |

Điểm quan trọng là thứ tự lấy khóa bị đảo ngược: A lấy 1 rồi 2; B lấy 2 rồi 1. Nếu cả hai lấy 1 rồi 2, một transaction sẽ phải chờ ngay ở khóa đầu tiên và không giữ khóa thứ hai để tạo vòng chờ.

## 5. Vì sao cần hai session và điều phối thời điểm?

Deadlock là hiện tượng đồng thời. Nếu chạy toàn bộ câu lệnh của A trước rồi mới chạy B, A có thể hoàn tất và nhả khóa trước khi B yêu cầu tài nguyên. Không có chu trình nào hình thành.

Trong bài lab thủ công, thứ tự thực hiện là cơ chế điều phối:

1. A lấy khóa thứ nhất.
2. B lấy khóa thứ nhất của mình.
3. A yêu cầu khóa đang do B giữ và bắt đầu chờ.
4. B yêu cầu khóa đang do A giữ để đóng chu trình.

Trong kiểm thử tự động, dùng hai connection và barrier/latch thay vì `sleep()` cố định. Mỗi worker báo hiệu sau khi đã lấy khóa đầu tiên; test harness chỉ cho cả hai đi tiếp khi cả hai đã giữ khóa. Sau đó mỗi worker yêu cầu khóa còn lại. Barrier làm lịch tái hiện ổn định hơn vì thời gian chạy của máy và tải database có thể thay đổi.

Pseudocode cho test harness:

```text
connectionA = openConnection()
connectionB = openConnection()
barrier = Barrier(2)

workerA:
    begin(connectionA)
    update row 1 using connectionA
    barrier.await()                 // A đã giữ hàng 1
    update row 2 using connectionA  // chờ B

workerB:
    begin(connectionB)
    update row 2 using connectionB
    barrier.await()                 // B đã giữ hàng 2
    update row 1 using connectionB  // đóng vòng chờ

assert one transaction is selected as victim
rollback or close both sessions safely
```

Test phải đặt timeout để không treo vô hạn nếu DBMS hoặc môi trường không phát hiện deadlock như dự kiến. Trong `finally`, kết thúc transaction còn hoạt động và đóng/discard connection theo đúng trạng thái driver.

## 6. Dấu hiệu nhận biết deadlock so với lock timeout

Hai lỗi có thể trông giống nhau vì câu lệnh đều dừng sau khi chờ khóa, nhưng nguyên nhân khác nhau:

| Đặc điểm | Deadlock | Lock wait timeout |
|---|---|---|
| Điều kiện | Có chu trình chờ giữa các transaction. | Một yêu cầu chờ quá thời hạn cấu hình. |
| Hệ quản trị cần làm gì? | Phải phá chu trình bằng cách hủy ít nhất một transaction/câu lệnh. | Có thể hủy câu lệnh đang chờ hoặc transaction theo chính sách DBMS. |
| Thời điểm | Khi bộ phát hiện xác định được chu trình. | Khi bộ đếm thời gian hết hạn. |
| Cách khắc phục | Xác định thứ tự khóa gây vòng chờ, sau đó retry nếu an toàn. | Giảm thời gian chờ, tối ưu truy vấn hoặc điều chỉnh timeout theo SLA. |

Nếu chỉ có A chờ B và B không chờ tài nguyên do A giữ, đây là lock wait bình thường. Khi B yêu cầu hàng 1 và tạo cạnh chờ ngược lại, mới xuất hiện deadlock.

## 7. Hành vi của các hệ quản trị phổ biến

Cùng một lịch khóa đảo ngược có thể tạo cùng một chu trình logic, nhưng cách báo lỗi và trạng thái transaction sau đó khác nhau.

| DBMS | Lỗi thường gặp | Hành vi cần lưu ý sau khi chọn nạn nhân |
|---|---|---|
| PostgreSQL | SQLSTATE `40P01` (`deadlock_detected`). | Transaction nạn nhân bị lỗi và chuyển sang trạng thái aborted; cần `ROLLBACK` trước khi tiếp tục dùng transaction. |
| MySQL InnoDB | Error `1213` (`ER_LOCK_DEADLOCK`), thường có SQLSTATE `40001`. | InnoDB thường rollback toàn bộ transaction nạn nhân và giải phóng khóa. |
| SQL Server | Error `1205` (`deadlock victim`). | Transaction nạn nhân bị rollback; ứng dụng cần chạy lại toàn bộ đơn vị công việc nếu an toàn. |
| Oracle Database | `ORA-00060` (`deadlock detected while waiting for resource`). | Oracle thường rollback câu lệnh gây deadlock; transaction có thể vẫn còn mở, vì vậy ứng dụng cần rollback nếu toàn bộ nghiệp vụ phải nguyên tử. |

Các chi tiết phụ thuộc phiên bản, driver và loại tài nguyên bị khóa. Không viết logic chung dựa trên giả định mọi DBMS tự rollback toàn transaction khi deadlock. Sau lỗi, kiểm tra trạng thái connection/transaction theo driver và tài liệu của sản phẩm.

## 8. Quan sát deadlock trong PostgreSQL

Trong lúc session A đang chờ session B, có thể mở session thứ ba để xem hoạt động và blocker:

```sql
SELECT pid,
       state,
       wait_event_type,
       wait_event,
       pg_blocking_pids(pid) AS blocking_pids,
       query
FROM pg_stat_activity
WHERE datname = current_database()
  AND state <> 'idle';
```

`wait_event_type = 'Lock'` cho biết session đang chờ khóa. `pg_blocking_pids(pid)` cho biết process đang chặn nó. Sau khi B yêu cầu hàng 1, deadlock detector sẽ xử lý chu trình; cửa sổ quan sát có thể rất ngắn.

Để xem khóa liên quan:

```sql
SELECT locktype,
       relation::regclass AS relation,
       page,
       tuple,
       transactionid,
       mode,
       granted,
       pid
FROM pg_locks
WHERE pid IN (
    SELECT pid
    FROM pg_stat_activity
    WHERE datname = current_database()
)
ORDER BY pid, granted;
```

Thông tin khóa hàng được lưu chủ yếu trong tuple; một session chờ khóa hàng có thể hiển thị chờ transaction ID của session giữ hàng. Vì vậy, hãy kết hợp `pg_locks`, `pg_stat_activity` và `pg_blocking_pids()` thay vì mong đợi một dòng `tuple` luôn đại diện đầy đủ cho mọi khóa hàng.

PostgreSQL ghi chi tiết deadlock vào server log khi phát hiện. `deadlock_timeout` quyết định thời gian chờ trước khi chạy kiểm tra deadlock; giá trị mặc định thường là 1 giây. Không cần thay đổi cấu hình này cho bài lab cơ bản.

## 9. Quan sát deadlock trong MySQL InnoDB

Sau khi deadlock xảy ra, có thể xem thông tin gần nhất bằng:

```sql
SHOW ENGINE INNODB STATUS;
```

Phần `LATEST DETECTED DEADLOCK` thường cho biết hai transaction, câu lệnh đang chạy, khóa đang giữ, khóa đang chờ và transaction bị rollback làm nạn nhân. Vì đây là thông tin deadlock gần nhất, hãy thu thập ngay sau khi thí nghiệm kết thúc.

Ở MySQL 8, các view trong `performance_schema` như `data_locks` và `data_lock_waits` có thể giúp quan sát khóa đang tồn tại và quan hệ chờ. Deadlock được xử lý nhanh nên trạng thái có thể biến mất trước khi truy vấn kịp đọc; server log hoặc InnoDB status thường hữu ích hơn cho lịch sử sự kiện.

## 10. Quan sát deadlock trong SQL Server

SQL Server có thể lưu deadlock graph trong Extended Events, thường có sẵn trong session `system_health`. Deadlock graph cho biết process, resource và victim được chọn. Có thể dùng Extended Events riêng để lưu các sự kiện `xml_deadlock_report` trong môi trường kiểm thử.

Các DMV như `sys.dm_tran_locks` và `sys.dm_os_waiting_tasks` giúp quan sát khóa đang giữ và session đang chờ. Tuy nhiên, deadlock được phát hiện nhanh nên trạng thái chờ có thể đã biến mất khi truy vấn DMV. Deadlock graph là bằng chứng hữu ích hơn để phân tích chu trình sau khi sự kiện kết thúc.

## 11. Quan sát deadlock trong Oracle

Oracle báo `ORA-00060` và ghi thông tin chẩn đoán vào trace file tương ứng trong Automatic Diagnostic Repository (ADR). Trace thường chứa deadlock graph với tài nguyên và session liên quan. Dùng công cụ quản trị phù hợp để xác định trace file; không nên chỉ dựa vào message trong ứng dụng vì message thường không mô tả đầy đủ chu trình.

Do Oracle có thể chỉ rollback câu lệnh gây deadlock, hãy kiểm tra transaction còn mở sau khi nhận `ORA-00060`. Nếu thao tác gồm nhiều bước cần nguyên tử, rollback toàn bộ transaction trước khi retry.

## 12. Ngăn deadlock bằng thứ tự lấy khóa nhất quán

Nguyên nhân trực tiếp trong bài lab là hai transaction lấy cùng tập khóa theo thứ tự ngược nhau. Một quy tắc phổ biến là sắp xếp tài nguyên theo thứ tự toàn cục và yêu cầu mọi transaction lấy khóa theo thứ tự đó.

Ví dụ, mọi thao tác chuyển tiền luôn khóa tài khoản theo `account_id` tăng dần:

```text
transfer(sourceId, targetId, amount):
    ids = unique([sourceId, targetId])
    ids.sortAscending()

    BEGIN
    lock account[ids[0]]
    lock account[ids[1]]

    validate source balance
    update source and target
    COMMIT
```

Khi T1 chuyển từ tài khoản 1 sang 2 và T2 chuyển từ 2 sang 1, cả hai đều yêu cầu hàng 1 trước rồi mới đến hàng 2. Một transaction có thể chờ ở khóa đầu tiên, nhưng không giữ khóa thứ hai để tạo vòng chờ đảo ngược.

Thứ tự toàn cục phải áp dụng trên mọi đường code, bao gồm tác vụ nền, service khác, trigger, foreign key và quy trình quản trị. `ORDER BY` trong truy vấn không phải trên mọi DBMS là cam kết về thứ tự lấy khóa vật lý; nếu thứ tự là yêu cầu đúng đắn, hãy xác nhận bằng tài liệu và thử nghiệm trên engine thực tế.

## 13. Các cách giảm khả năng deadlock khác

Thứ tự khóa nhất quán là biện pháp quan trọng, nhưng không phải giải pháp duy nhất:

- **Giữ transaction ngắn:** không gọi HTTP, chờ người dùng hoặc xử lý file trong lúc giữ khóa.
- **Khóa đúng phạm vi:** tránh khóa bảng hoặc phạm vi rộng nếu chỉ cần bảo vệ một nhóm hàng nhỏ.
- **Tạo index phù hợp:** giảm số hàng phải quét và giảm thời gian truy cập/giữ khóa.
- **Cập nhật nguyên tử:** dùng một câu lệnh có điều kiện khi invariant có thể bảo vệ trực tiếp, giảm số bước đọc rồi ghi.
- **Tránh nâng cấp khóa không cần thiết:** xác định trước thao tác cần đọc hay ghi và chọn chế độ khóa phù hợp.
- **Phân lô hợp lý:** giảm số tài nguyên giữ cùng lúc, nhưng bảo đảm ranh giới commit phù hợp nghiệp vụ.
- **Dùng hàng điều phối khi thích hợp:** nhiều transaction cùng khóa một hàng đại diện có thể tuần tự hóa thao tác theo tài nguyên logic.
- **Quan sát deadlock graph:** sửa nguyên nhân thực tế thay vì chỉ tăng timeout.

Ngay cả khi đã áp dụng các biện pháp trên, deadlock vẫn có thể xảy ra do khóa ngầm từ index, constraint, trigger, cascade hoặc một luồng code chưa tuân thủ thứ tự chung. Ứng dụng cần có xử lý deadlock như một kết quả cạnh tranh có thể xảy ra.

## 14. Retry sau deadlock

Khi DBMS chọn transaction làm nạn nhân, ứng dụng thường nên chạy lại toàn bộ đơn vị transaction nếu thao tác có thể lặp an toàn. Không chỉ chạy lại câu lệnh cuối, bởi các lần đọc và quyết định trước đó có thể dựa trên dữ liệu không còn hiện hành.

Một quy trình retry:

1. Nhận diện mã lỗi deadlock của driver/DBMS.
2. Rollback transaction nếu nó còn mở; nếu DBMS đã rollback toàn bộ, xác nhận connection đã ở trạng thái sạch.
3. Chờ một khoảng ngắn với backoff và jitter.
4. Mở transaction mới, đọc lại dữ liệu và kiểm tra lại điều kiện nghiệp vụ.
5. Thực hiện lại tất cả thay đổi database rồi commit.
6. Giới hạn số lần retry; nếu vẫn thất bại, trả lỗi tạm thời để tầng trên quyết định.

Ví dụ pseudocode:

```text
for attempt in 1..MAX_RETRIES:
    begin transaction
    try:
        read current values
        validate business rules
        update all required rows in consistent order
        commit
        return SUCCESS
    catch deadlock:
        rollback if needed
        sleep(backoffWithJitter(attempt))

return RETRYABLE_FAILURE
```

Retry không được lặp tác dụng phụ ngoài database như gửi email hoặc gọi API thanh toán. Dùng idempotency key hoặc transactional outbox để tách tác dụng phụ khỏi transaction có thể bị chạy lại.

## 15. Không nhầm deadlock với serialization failure

Deadlock là vòng chờ khóa. Serialization failure là hệ quản trị từ chối transaction vì lịch đọc–ghi không thể được đảm bảo tương đương một thứ tự tuần tự, dù không nhất thiết có vòng chờ khóa.

Ví dụ PostgreSQL:

- `40P01`: deadlock detected.
- `40001`: serialization failure.

Hai lỗi đều có thể yêu cầu retry toàn transaction, nhưng chẩn đoán khác nhau. Deadlock thường cần xem thứ tự lấy khóa và deadlock graph. Serialization failure cần xem phụ thuộc đọc–ghi, predicate và isolation level. Không gộp mọi lỗi concurrency thành một loại nếu cần quan sát và tối ưu chính xác.

## 16. Các biến thể mở rộng của thí nghiệm

Sau khi tái hiện thành công với hai hàng, có thể thay đổi từng yếu tố để quan sát:

### 16.1. Cùng thứ tự lấy khóa

Cho cả A và B lấy hàng 1 rồi hàng 2. Một transaction sẽ chờ ở hàng 1; khi transaction đầu commit hoặc rollback, transaction sau tiếp tục. Không có chu trình chờ nếu mọi transaction tuân thủ cùng thứ tự và không có khóa khác tạo vòng chờ.

### 16.2. Một hàng duy nhất

Cho cả hai transaction cập nhật cùng một hàng. Một transaction chờ transaction còn lại, nhưng với chỉ một tài nguyên và không có khóa khác, không hình thành chu trình hai chiều.

### 16.3. Thêm hàng thứ ba

Tạo ba transaction giữ các hàng A, B, C rồi lần lượt chờ B, C, A. Đồ thị tạo chu trình ba đỉnh. Điều này cho thấy deadlock không giới hạn ở hai transaction.

### 16.4. Thay khóa hàng bằng advisory/application lock

Nếu hệ quản trị có khóa tư vấn hoặc khóa ứng dụng, yêu cầu các khóa logic theo thứ tự ngược nhau cũng có thể tạo deadlock. Nguyên tắc wait-for graph vẫn giống nhau dù tài nguyên không phải hàng trong bảng.

### 16.5. Thêm một truy vấn đọc

Thử thay đổi isolation level hoặc dùng snapshot read để thấy đọc không khóa có thể không chờ như locking read. Tuy nhiên, một transaction vẫn có thể tạo deadlock khi các câu lệnh ghi hoặc khóa tường minh xung đột. Snapshot isolation không phải bảo đảm rằng deadlock không thể xảy ra.

## 17. Checklist cho bài lab hai session

- [ ] Đã dùng database thử nghiệm và bảng riêng với hai hàng xác định.
- [ ] Đã mở hai session/connection độc lập.
- [ ] A khóa hàng 1 trước; B khóa hàng 2 trước.
- [ ] A yêu cầu hàng 2 và được xác nhận đang chờ.
- [ ] B yêu cầu hàng 1 để tạo chu trình.
- [ ] Đã ghi nhận session nào bị chọn làm nạn nhân và mã lỗi cụ thể.
- [ ] Đã quan sát blocker/wait graph hoặc log deadlock của DBMS.
- [ ] Đã rollback transaction còn lại và giải phóng mọi session.
- [ ] Đã xác nhận dữ liệu thử nghiệm trở về giá trị ban đầu.
- [ ] Đã phân biệt deadlock với lock wait timeout.
- [ ] Đã thử lại với thứ tự khóa nhất quán và quan sát việc chờ tuần tự thay cho deadlock.
- [ ] Đã thử retry toàn transaction với giới hạn và idempotency phù hợp.

## 18. Kết luận thực hành

Tạo deadlock có kiểm soát bằng thứ tự khóa đảo ngược giúp biến một lỗi cạnh tranh khó tái hiện thành một thí nghiệm rõ ràng: A giữ hàng 1 và chờ hàng 2; B giữ hàng 2 và chờ hàng 1. Chu trình chờ buộc hệ quản trị chọn nạn nhân, giải phóng khóa và trả lỗi. Quan sát kết quả trên từng DBMS giúp hiểu sự khác nhau giữa rollback câu lệnh và rollback toàn transaction.

Trong ứng dụng, giảm deadlock bằng thứ tự khóa toàn cục, transaction ngắn, index phù hợp và cập nhật nguyên tử. Vẫn phải xử lý deadlock như một kết quả có thể xảy ra: rollback hoặc xác nhận transaction đã sạch, retry toàn bộ đơn vị công việc với backoff, và bảo vệ tác dụng phụ bằng idempotency. Thí nghiệm chỉ hoàn tất khi cả hai session đã kết thúc và dữ liệu thử nghiệm trở về trạng thái ban đầu.
