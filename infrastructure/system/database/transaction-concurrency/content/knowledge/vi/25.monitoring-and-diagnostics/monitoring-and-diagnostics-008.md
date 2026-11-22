# Đo tỷ lệ bế tắc, lỗi tuần tự hóa và thực thi lại

Deadlock, serialization failure và retry đều là tín hiệu về cách các transaction cạnh tranh tài nguyên và cách ứng dụng phục hồi sau xung đột. Đếm riêng số lần lỗi trong log chưa đủ để đánh giá sức khỏe hệ thống. Một hệ thống có 20 deadlock trong một phút có thể đang gặp sự cố nghiêm trọng nếu chỉ chạy 1.000 transaction, nhưng có thể là tỷ lệ thấp nếu xử lý hàng triệu transaction trong cùng khoảng thời gian. Tương tự, tỷ lệ retry cao có thể che giấu một vấn đề contention đang làm latency tăng và tiêu thụ thêm connection.

Muốn quan sát có ý nghĩa, cần đo đồng thời **số sự kiện, tỷ lệ đã chuẩn hóa theo lưu lượng, thời gian chờ, số lần thực thi lại và kết quả cuối của yêu cầu nghiệp vụ**. Các chỉ số database cho biết engine phát hiện deadlock hoặc lock wait; metric ở ứng dụng cho biết lỗi ảnh hưởng đến transaction nào, có retry hay không và caller cuối cùng có nhận được kết quả hay không.

## 1. Phân biệt các hiện tượng cần đo

### Deadlock

Deadlock xảy ra khi các transaction tạo thành chu trình chờ tài nguyên. Database phát hiện chu trình và chọn ít nhất một transaction làm victim để rollback, giải phóng khóa cho các transaction còn lại.

Một deadlock event không đồng nghĩa toàn bộ request thất bại. Nếu ứng dụng nhận diện lỗi victim, rollback và retry toàn bộ transaction thành công, thao tác nghiệp vụ có thể vẫn hoàn tất. Tuy vậy, deadlock vẫn tiêu thụ công việc đã thực hiện, thời gian chờ và tài nguyên database.

### Serialization failure

Serialization failure xảy ra khi database không thể chấp nhận một transaction vì kết quả đồng thời không thỏa semantics của isolation level Serializable hoặc cơ chế kiểm tra xung đột tương ứng. Database hủy transaction để ngăn một lịch thực thi không hợp lệ.

Serialization failure khác deadlock. Deadlock là chu trình chờ khóa; serialization failure có thể xuất hiện do phát hiện phụ thuộc đọc/ghi không thể sắp xếp thành một lịch tuần tự hợp lệ, ngay cả khi không có chu trình lock wait truyền thống.

Ví dụ PostgreSQL thường trả SQLSTATE `40001` cho serialization failure và `40P01` cho deadlock detected. Hai mã này không nên bị gom vào một nhóm lỗi chung nếu cần chẩn đoán nguyên nhân.

### Lock timeout và blocking

Blocking là trạng thái một transaction phải chờ tài nguyên mà transaction khác đang giữ. Chờ khóa tự nó chưa phải deadlock. Lock timeout xảy ra khi thời gian chờ vượt giới hạn được cấu hình; nó cũng khác với serialization failure.

Nên đo lock wait duration và lock timeout riêng. Nếu chỉ đếm deadlock, hệ thống có thể bỏ sót một hàng nóng khiến request chờ nhiều giây nhưng cuối cùng vẫn thành công.

### Retry

Retry là một lần thực hiện lại sau khi một attempt thất bại vì lỗi được xem là có thể phục hồi. Một logical operation có thể gồm lần đầu và nhiều retry. Cần phân biệt:

- **Logical operation/request:** ý định nghiệp vụ ban đầu, ví dụ một lần chuyển tiền hoặc xác nhận đơn.
- **Transaction attempt:** một lần chạy transaction database. Một logical operation có thể có nhiều attempt.
- **Retry:** attempt sau lần đầu.
- **Retry success:** logical operation cuối cùng thành công sau ít nhất một retry.
- **Retry exhaustion:** thao tác hết số attempt hoặc deadline mà vẫn chưa thành công.

Đếm request, transaction attempt và retry như cùng một đơn vị sẽ làm tỷ lệ sai lệch.

## 2. Chọn mẫu số trước khi tính tỷ lệ

Số đếm thô hữu ích để điều tra một sự kiện, nhưng tỷ lệ giúp so sánh giữa các giờ, ngày và mức lưu lượng khác nhau. Mỗi metric cần định nghĩa rõ tử số, mẫu số, đơn vị và khoảng thời gian.

Các công thức thường dùng:

| Chỉ số | Công thức | Câu hỏi được trả lời |
|---|---|---|
| Deadlock rate | `deadlock victim attempts / total transaction attempts × 1.000` | Có bao nhiêu transaction attempt bị deadlock trên mỗi 1.000 attempt? |
| Serialization failure rate | `serialization-aborted attempts / total transaction attempts × 1.000` | Có bao nhiêu attempt bị hủy do serialization conflict trên mỗi 1.000 attempt? |
| Lock timeout rate | `lock-timeout attempts / total transaction attempts × 1.000` | Bao nhiêu attempt không lấy được khóa trong ngân sách chờ? |
| Operation retry rate | `logical operations with ≥1 retry / eligible logical operations × 100%` | Bao nhiêu yêu cầu phải thực hiện lại ít nhất một lần? |
| Retry amplification | `total transaction attempts / logical operations` | Trung bình mỗi ý định nghiệp vụ tạo ra bao nhiêu attempt? |
| Retry recovery rate | `operations succeeding after retry / operations entering retry × 100%` | Bao nhiêu thao tác được cứu thành công nhờ retry? |
| Retry exhaustion rate | `operations exhausting attempts/deadline / logical operations × 100%` | Bao nhiêu yêu cầu vẫn thất bại sau khi đã dùng hết ngân sách? |

`× 1.000` là cách biểu diễn tỷ lệ trên 1.000 attempt; có thể chọn 10.000 hoặc phần trăm tùy quy mô. Quan trọng là giữ cùng định nghĩa khi so sánh các khoảng thời gian.

### Ví dụ tính tỷ lệ

Trong một cửa sổ 5 phút, ứng dụng có:

- 100.000 transaction attempts.
- 20 attempt bị chọn làm deadlock victim.
- 800 attempt bị serialization failure.
- 5.000 logical operations.
- 250 logical operations cần ít nhất một retry.
- 5.300 transaction attempts tổng cộng cho 5.000 operations.
- 200 trong 250 operations đã retry cuối cùng thành công.
- 50 operations hết ngân sách và thất bại.

Kết quả:

| Chỉ số | Tính toán | Kết quả |
|---|---|---:|
| Deadlock rate | `20 / 100.000 × 1.000` | `0,2` victim / 1.000 attempts |
| Serialization failure rate | `800 / 100.000 × 1.000` | `8` failures / 1.000 attempts |
| Operation retry rate | `250 / 5.000 × 100%` | `5%` |
| Retry amplification | `5.300 / 5.000` | `1,06` attempts / operation |
| Retry recovery rate | `200 / 250 × 100%` | `80%` |
| Retry exhaustion rate | `50 / 5.000 × 100%` | `1%` |

Các con số này chỉ minh họa phép tính, không phải ngưỡng tốt/xấu chung cho mọi hệ thống. Một tỷ lệ serialization failure cao có thể là điều chấp nhận được trong một workload Serializable có retry được thiết kế tốt, nhưng vẫn cần đánh giá chi phí và latency.

### Đừng trộn các mẫu số

Deadlock counter của database thường đếm sự kiện deadlock, trong khi metric ứng dụng có thể đếm transaction attempt nhận lỗi. Retry metric có thể đếm logical operation được retry. Ba mẫu số này khác nhau.

Khi đối chiếu, hãy đặt tên metric cụ thể, ví dụ `db_deadlock_events_total`, `db_deadlock_victim_attempts_total`, `app_transaction_attempts_total` và `app_operations_retried_total`. Đừng cộng trực tiếp các counter từ database và ứng dụng nếu chúng đo cùng một sự kiện ở hai tầng.

## 3. Đo deadlock và serialization failure ở tầng database

Database là nguồn đáng tin cậy để biết engine có phát hiện deadlock hoặc lock wait hay không. Nhưng khả năng thống kê khác nhau giữa sản phẩm.

### PostgreSQL

PostgreSQL cung cấp counter deadlock tích lũy theo database trong `pg_stat_database`:

```sql
SELECT datname,
       deadlocks,
       stats_reset
FROM pg_stat_database
WHERE datname = current_database();
```

`deadlocks` là số deadlock được phát hiện kể từ lần reset thống kê gần nhất. Để tính số sự kiện trong một cửa sổ, thu thập giá trị định kỳ và lấy chênh lệch giữa hai lần scrape, đồng thời xử lý trường hợp server restart hoặc statistics reset. Không lấy giá trị tích lũy làm số sự kiện trong mỗi phút.

PostgreSQL không cung cấp một counter toàn cục tương đương `deadlocks` trong `pg_stat_database` cho mọi serialization failure của ứng dụng. Hãy đếm SQLSTATE `40001` từ application/driver log hoặc instrumentation tại nơi bắt exception. Không nhầm cột `conflicts` trong `pg_stat_database` với serialization failure của transaction thông thường: nó chủ yếu thống kê recovery conflicts trên standby.

Để thu thập bằng chứng chờ khóa, có thể bật `log_lock_waits` và điều chỉnh `deadlock_timeout` theo mục tiêu quan sát:

```sql
SHOW log_lock_waits;
SHOW deadlock_timeout;
```

`log_lock_waits` giúp ghi log những lần chờ khóa vượt ngưỡng `deadlock_timeout`. Deadlock report được ghi khi PostgreSQL phát hiện chu trình. Cần cấu hình log prefix có PID/session và transaction context đủ để ghép các dòng log với trace ứng dụng. Không giảm `deadlock_timeout` tùy tiện trên production vì có thể tăng chi phí kiểm tra deadlock.

Để quan sát session đang chờ:

```sql
SELECT pid,
       state,
       wait_event_type,
       wait_event,
       pg_blocking_pids(pid) AS blocking_pids,
       xact_start,
       query
FROM pg_stat_activity
WHERE datname = current_database();
```

`wait_event_type = 'Lock'` và `pg_blocking_pids` giúp tìm blocking session tại thời điểm truy vấn. Đây là ảnh chụp trạng thái hiện tại; một deadlock đã xảy ra và được giải quyết có thể không còn xuất hiện trong view này, nên cần giữ server log hoặc hệ thống thu thập sự kiện.

### MySQL InnoDB

MySQL cung cấp các status variable liên quan đến deadlock và row lock. Có thể xem các counter được server hỗ trợ:

```sql
SHOW GLOBAL STATUS LIKE 'Innodb_deadlocks';
SHOW GLOBAL STATUS LIKE 'Innodb_row_lock_waits';
SHOW GLOBAL STATUS LIKE 'Innodb_row_lock_time';
```

Tên và phạm vi counter có thể thay đổi theo phiên bản MySQL. Hãy xác nhận biến thực sự có trong phiên bản đang chạy. Các giá trị global status thường là counter tích lũy; lấy delta giữa hai lần thu thập để tính tốc độ sự kiện.

`SHOW ENGINE INNODB STATUS` cung cấp phần `LATEST DETECTED DEADLOCK`, gồm transaction, statement, index/record và victim gần nhất. Đây là thông tin hữu ích để chẩn đoán, nhưng chỉ lưu deadlock gần nhất; nếu cần lịch sử đầy đủ, phải thu thập log hoặc dùng công cụ giám sát phù hợp.

Trên các phiên bản có Performance Schema tương ứng, có thể quan sát khóa và quan hệ chờ:

```sql
SELECT * FROM performance_schema.data_locks;
SELECT * FROM performance_schema.data_lock_waits;
```

Các bảng này phản ánh lock state hiện tại. Chúng hữu ích để tìm index record hoặc transaction đang chờ, nhưng không thay thế việc lưu lại deadlock đã xảy ra.

InnoDB deadlock error thường là mã `1213` với SQLSTATE `40001`. Lock wait timeout thường là mã `1205`. Không gộp hai lỗi này thành cùng một metric nếu cần phân biệt chu trình deadlock với chờ quá lâu.

### SQL Server

SQL Server cung cấp deadlock graph qua Extended Events. Session hệ thống `system_health` thường thu thập sự kiện `xml_deadlock_report`; có thể đọc event file để xem các deadlock graph đã ghi lại. Graph thể hiện process, resource, owner, waiter, statement và victim.

Để quan sát blocking đang diễn ra, có thể kết hợp `sys.dm_exec_requests`, `sys.dm_tran_locks` và `sys.dm_exec_sessions`. Cột `blocking_session_id` trong request giúp nhận diện session đang chặn request khác. Với deadlock đã được giải quyết, dùng Extended Events hoặc Performance Monitor thay vì chỉ truy vấn DMV hiện tại.

Các lỗi thường gặp cần phân biệt:

- Error `1205`: transaction được chọn làm deadlock victim.
- Error `3960`: snapshot isolation update conflict trong những tình huống tương ứng.

`1205` và `3960` phản ánh hai loại xung đột khác nhau. Serialization-like conflict cần được đếm từ lỗi transaction phù hợp ở ứng dụng; không suy ra toàn bộ serialization failure chỉ từ deadlock counter.

### Lưu ý khi đọc counter tích lũy

Counter database thường tăng dần từ lúc khởi động hoặc reset. Để tính rate trong khoảng `Δt`:

\[
rate = \frac{counter_{new} - counter_{old}}{\Delta t}
\]

Nếu counter giảm, có thể database restart hoặc statistics bị reset. Không diễn giải delta âm thành số lỗi âm; bắt đầu một chu kỳ baseline mới và ghi nhận sự kiện reset.

## 4. Đo lỗi ở tầng ứng dụng

Database biết transaction bị hủy, nhưng ứng dụng biết logical operation nào bị ảnh hưởng và có retry hay không. Vì vậy, instrumentation ở tầng retry policy là cần thiết.

Tối thiểu nên ghi nhận:

- Tổng logical operations bắt đầu và kết thúc.
- Tổng transaction attempts.
- Số attempt thất bại theo nhóm lỗi.
- Số operation có ít nhất một retry.
- Số retry theo nguyên nhân: deadlock, serialization, lock timeout, transient connection hoặc dependency error.
- Số operation thành công sau retry.
- Số operation hết `maxAttempts`, deadline hoặc retry budget.
- Backoff duration và thời gian còn lại trước mỗi attempt.
- Thời gian transaction và latency tổng của logical operation.

### Đếm logical operation và attempt riêng

Ví dụ một request chuyển tiền được retry hai lần:

```text
Logical operation transfer-42
  Attempt 1: deadlock victim
  Attempt 2: serialization failure
  Attempt 3: commit thành công
```

Metric đúng có thể là:

```text
logical_operations_total             +1
transaction_attempts_total           +3
deadlock_victim_attempts_total       +1
serialization_failure_attempts_total +1
operations_retried_total             +1
operations_recovered_after_retry     +1
```

Nếu chỉ ghi “3 requests”, dashboard có thể hiểu nhầm ứng dụng nhận ba yêu cầu từ client. Thực tế chỉ có một ý định nghiệp vụ nhưng tạo ba transaction attempt.

### Phân loại lỗi bằng mã có cấu trúc

Đừng phân loại lỗi bằng cách tìm từ `deadlock` trong message exception. Message có thể thay đổi theo ngôn ngữ, driver và phiên bản. Ưu tiên SQLSTATE, vendor error code và loại exception đã được chuẩn hóa ở tầng repository/transaction boundary.

Một enum nội bộ có thể gồm:

```text
DEADLOCK
SERIALIZATION_FAILURE
LOCK_TIMEOUT
CONNECTION_FAILURE
QUERY_TIMEOUT
CONSTRAINT_VIOLATION
VALIDATION_FAILURE
UNKNOWN
```

Chỉ những nhóm lỗi được chính sách cho phép mới được retry. Unique constraint violation, check violation, foreign key violation hoặc lỗi validation thường cần trả kết quả nghiệp vụ thay vì lặp lại cùng transaction một cách mù quáng.

## 5. Thiết kế metric retry có ý nghĩa

Một bộ metric có thể được tổ chức như sau:

| Metric | Loại đo | Gợi ý nhãn |
|---|---|---|
| `app_operations_total` | Counter logical operation | `operation`, `outcome` |
| `app_transaction_attempts_total` | Counter attempt | `operation`, `outcome` |
| `app_retry_attempts_total` | Counter retry | `reason`, `operation` |
| `app_operations_retried_total` | Counter operation có retry | `operation` |
| `app_retry_exhausted_total` | Counter hết ngân sách | `reason`, `operation` |
| `app_retry_delay_seconds` | Histogram thời gian backoff | `reason` |
| `app_operation_duration_seconds` | Histogram latency tổng | `operation`, `outcome` |
| `app_transaction_duration_seconds` | Histogram duration từng attempt | `operation`, `outcome` |
| `db_lock_wait_seconds` | Histogram thời gian chờ khóa nếu thu thập được | `database`, `operation` hoặc query fingerprint có kiểm soát |
| `db_deadlock_events_total` | Counter sự kiện từ database | `database`, `instance` |
| `db_serialization_failures_total` | Counter lỗi được chuẩn hóa | `database`, `instance` |

Tên metric là ví dụ; hãy theo convention của hệ thống telemetry hiện tại. Dùng counter cho số sự kiện tích lũy, histogram cho thời gian hoặc phân phối attempt. Gauge phù hợp với trạng thái hiện tại như số session đang chờ hoặc số connection active.

### Tránh cardinality quá cao

Không dùng `requestId`, `transactionId`, account ID, customer ID hoặc raw SQL làm label của metric. Mỗi giá trị mới có thể tạo một time series mới và làm hệ thống metrics tốn bộ nhớ.

Dùng trace/log để giữ định danh chi tiết; metric chỉ dùng nhãn có tập giá trị giới hạn như:

- Tên operation: `transfer`, `reserve_inventory`, `confirm_order`.
- Nhóm lỗi: `DEADLOCK`, `SERIALIZATION_FAILURE`, `LOCK_TIMEOUT`.
- Outcome: `success`, `failed`, `exhausted`.
- Database instance hoặc cluster có danh sách quản lý.
- Query fingerprint đã được chuẩn hóa, nếu số lượng fingerprint được giới hạn.

## 6. Theo dõi retry bằng trace và log

Metric cho biết xu hướng tổng thể; trace giúp hiểu một request cụ thể đã trải qua bao nhiêu attempt và thời gian tiêu thụ ở đâu.

Một trace có thể biểu diễn:

```text
POST /transfers                         1.420 ms
  ├─ transaction attempt 1                310 ms
  │    └─ COMMIT -> deadlock victim
  ├─ backoff                                80 ms
  ├─ transaction attempt 2                470 ms
  │    └─ COMMIT -> serialization failure
  ├─ backoff                               140 ms
  └─ transaction attempt 3                390 ms
       └─ COMMIT -> success
```

Các span/field hữu ích:

- `operation.name` hoặc tên use case.
- `attempt.number` và `attempt.max`.
- `retry.reason` theo enum.
- `retry.delay_ms`.
- `deadline.remaining_ms`.
- `db.system`, `db.name` và query fingerprint phù hợp.
- `db.session_id` hoặc transaction identifier trong log có kiểm soát.
- `db.error_code` và SQLSTATE.
- `transaction.outcome`: committed, rolled_back, deadlock_victim, serialization_aborted.

Log nên có trace ID/correlation ID để nối application attempt với database log. Không ghi bind parameter nhạy cảm hoặc toàn bộ payload chỉ để chẩn đoán retry. Dùng redaction và sampling phù hợp.

## 7. Dashboard: xem cả lỗi, retry và trải nghiệm người dùng

Một dashboard hữu ích không chỉ hiển thị deadlock count. Nó nên ghép ba góc nhìn:

### Database contention

- Deadlock events/victims theo thời gian.
- Serialization failures theo thời gian.
- Lock wait duration p50/p95/p99.
- Lock timeout count.
- Số transaction đang chờ và thời gian transaction mở.
- Các query fingerprint hoặc index/table xuất hiện nhiều trong deadlock graph.

### Application retry

- Retry rate theo operation.
- Retry amplification.
- Attempt distribution: thành công ở attempt 1, 2, 3...
- Retry recovery rate.
- Retry exhaustion rate.
- Backoff duration và deadline remaining.
- Tỷ lệ lỗi theo nguyên nhân.

### User-facing outcome

- Request success/error rate.
- End-to-end latency p50/p95/p99.
- Số request vượt SLA hoặc hết deadline.
- Tỷ lệ thao tác thành công sau retry nhưng latency đã tăng cao.
- Pool acquisition wait và active/pending connections.

Một hệ thống có thể giữ success rate gần 100% nhờ retry, nhưng latency p99 tăng gấp đôi và retry amplification tăng mạnh. Nếu chỉ nhìn tỷ lệ lỗi cuối cùng, dashboard sẽ bỏ lỡ suy giảm trải nghiệm và tải phụ.

## 8. Truy vấn tỷ lệ từ metric time series

Với hệ thống dùng Prometheus, giả sử có các counter do ứng dụng xuất ra:

```text
db_deadlock_victim_attempts_total
db_serialization_failure_attempts_total
app_transaction_attempts_total
app_operations_total
app_operations_retried_total
app_retry_exhausted_total
```

Một biểu thức minh họa cho deadlock victim trên mỗi 1.000 transaction attempt trong 5 phút:

```promql
1000 * rate(db_deadlock_victim_attempts_total[5m])
      / rate(app_transaction_attempts_total[5m])
```

Serialization failure rate:

```promql
1000 * rate(db_serialization_failure_attempts_total[5m])
      / rate(app_transaction_attempts_total[5m])
```

Operation retry rate:

```promql
100 * rate(app_operations_retried_total[5m])
      / rate(app_operations_total[5m])
```

Retry amplification:

```promql
rate(app_transaction_attempts_total[5m])
  / rate(app_operations_total[5m])
```

Các biểu thức này giả định counter được định nghĩa cùng phạm vi service/operation và cùng cửa sổ. Cần xử lý mẫu số bằng `0` hoặc thiếu dữ liệu; không để dashboard hiển thị `NaN` như một tỷ lệ thực. `rate()` xử lý counter reset theo cách phù hợp hơn so với lấy chênh lệch thô trong từng scrape, nhưng vẫn cần kiểm tra scrape interval và dữ liệu bị mất.

Nếu database counter được scrape riêng, không chia trực tiếp cho application attempts của một service nếu database còn phục vụ nhiều ứng dụng khác mà chưa lọc được phạm vi. Có thể báo riêng deadlock events trên mỗi phút ở database và retry rate theo operation ở ứng dụng; chỉ chuẩn hóa chung khi mẫu số tương ứng đúng phạm vi.

## 9. Đo latency và chi phí của retry

Retry thường tăng latency vì logical operation phải chờ attempt thất bại, backoff và attempt tiếp theo. Cần đo:

- Thời gian của từng transaction attempt.
- Thời gian chờ khóa trước khi attempt kết thúc.
- Thời gian backoff.
- Tổng thời gian logical operation.
- Thời gian chờ connection pool trước mỗi attempt.

Không cộng p95 của từng thành phần để suy ra p95 tổng; percentile của các phân phối không cộng tuyến tính. Hãy đo trực tiếp histogram end-to-end và dùng trace để phân tích các thành phần.

Ví dụ:

| Thành phần | Thời gian |
|---|---:|
| Attempt 1 | 300 ms |
| Backoff 1 | 100 ms |
| Attempt 2 | 450 ms |
| Backoff 2 | 200 ms |
| Attempt 3 | 350 ms |
| Tổng logical operation | 1.400 ms |

Nếu deadline của API là `1.000 ms`, request này đã vượt ngân sách dù attempt cuối thành công. Không nên đánh giá retry chỉ theo outcome; latency và deadline exhaustion cũng quan trọng.

### Theo dõi phân phối attempt

Thống kê số operation kết thúc ở từng attempt:

| Attempt thành công | Ý nghĩa |
|---:|---|
| 1 | Không cần retry. |
| 2 | Một lần retry đã phục hồi. |
| 3 | Hai lần retry đã phục hồi. |
| Không thành công | Hết attempt, deadline hoặc gặp lỗi không retry được. |

Nếu tỷ lệ thành công ở attempt 1 giảm dần trong khi attempt 2/3 tăng, contention có thể đang tăng dù success rate tổng chưa thay đổi.

## 10. Đọc deadlock và serialization failure như hai nhóm riêng

Không nên gom mọi lỗi transaction bị hủy thành `concurrency_error` duy nhất. Cách phân nhóm giúp chọn giải pháp khác nhau.

| Tín hiệu | Nguyên nhân thường gặp | Hướng điều tra |
|---|---|---|
| Deadlock | Thứ tự khóa không nhất quán, conversion deadlock, index/foreign key interaction | Đọc deadlock graph, owner/waiter, resource và thứ tự truy cập. |
| Serialization failure | Write skew, predicate dependency hoặc snapshot conflict ở isolation nghiêm ngặt | Xem transaction read/write set, isolation level và bất biến được bảo vệ. |
| Lock timeout | Transaction giữ khóa quá lâu, hàng nóng hoặc phạm vi khóa rộng | Đo wait duration, transaction age, blocker và query plan. |
| Connection timeout | Pool cạn, connection leak hoặc database không nhận thêm kết nối | Đối chiếu pool active/pending, acquisition latency và session count. |
| Query timeout | Query chậm, I/O, CPU, blocking hoặc timeout quá thấp | Kiểm tra wait event, execution plan và query duration. |

Một serialization failure có thể cần retry toàn bộ transaction ở snapshot mới. Một deadlock victim cũng thường retry toàn bộ transaction, nhưng deadlock graph giúp tìm thứ tự khóa gây chu trình. Lock timeout không nhất thiết có chu trình; retry nhanh có thể làm hàng nóng càng quá tải.

## 11. Retry phải được đo cùng chính sách giới hạn

Retry chỉ có ích khi được giới hạn bởi số attempt và deadline tổng. Cần quan sát:

- `maxAttempts` thực tế của operation.
- Số attempt trung bình và phân phối attempt.
- Số lần retry bị bỏ qua vì lỗi không retry được.
- Số lần dừng vì deadline đã hết.
- Số lần dừng vì retry budget hoặc circuit breaker.
- Backoff được áp dụng và jitter thực tế.
- Số transaction rollback trước khi backoff.

Không giữ transaction hoặc connection trong thời gian backoff. Sau deadlock/serialization failure, rollback transaction cũ rồi mở transaction mới, đọc dữ liệu mới và chạy lại toàn bộ logic. Nếu chỉ chạy lại câu SQL cuối với dữ liệu đã tính từ snapshot cũ, retry có thể tái tạo lỗi logic.

### Retry recovery rate có thể gây hiểu nhầm

Retry recovery rate cao không nhất thiết là tốt. Ví dụ 99% request có retry cuối cùng thành công, nhưng mỗi request phải thực hiện trung bình 4 attempt và p99 latency vượt SLA. Hệ thống vẫn đang chịu contention cao.

Đọc recovery rate cùng retry amplification, deadline exhaustion, latency và throughput. Nếu retry thành công nhưng số attempt tăng liên tục, hãy xử lý nguyên nhân contention thay vì tăng `maxAttempts` để che lỗi.

## 12. Phân biệt lỗi database với lỗi do retry ở tầng ứng dụng

Một logical operation có thể được retry ở nhiều tầng: HTTP client, service, repository hoặc database driver. Nếu mỗi tầng có giới hạn riêng, số lần gọi thực tế có thể nhân lên.

Ví dụ ba tầng cùng cho tối đa ba attempt:

```text
API retry:        3 lần gọi Order Service
Order retry:      mỗi lần gọi tối đa 3 lần Inventory
Inventory retry:  mỗi lần gọi tối đa 3 lần Database

Tối đa: 3 × 3 × 3 = 27 lần gọi Database
```

Để đo đúng, gắn logical operation ID ở đầu request và attempt ID/number ở mỗi tầng. Chọn một tầng sở hữu retry cho từng loại lỗi; truyền deadline xuống dưới và không để tầng trên retry lại một thao tác mà tầng dưới đã dùng hết ngân sách.

Dashboard nên có metric retry theo tầng hoặc dependency, nhưng không dùng ID riêng của từng request làm label. Trace có thể cho thấy toàn bộ cây gọi và attempt tương ứng.

## 13. Cảnh báo theo baseline và SLO

Không có một ngưỡng deadlock rate hoặc serialization failure rate đúng cho mọi hệ thống. Ngưỡng phụ thuộc workload, isolation level, mức contention chấp nhận được, khả năng retry và SLO của nghiệp vụ.

Một cách xây dựng cảnh báo:

1. Đo baseline theo giờ/ngày và phân loại theo operation.
2. Xác định tỷ lệ lỗi, retry và latency mà SLO cho phép.
3. Đặt cảnh báo cho cả spike tức thời và xu hướng tăng kéo dài.
4. Kết hợp tỷ lệ chuẩn hóa với số lượng tối thiểu để tránh cảnh báo nhiễu khi lưu lượng rất thấp.
5. Cảnh báo khi retry exhaustion hoặc request deadline vượt ngưỡng nghiệp vụ.
6. Cảnh báo khi lock wait p95/p99 tăng mạnh hoặc pool acquisition wait kéo dài.
7. Đưa link tới trace, deadlock graph và query fingerprint để rút ngắn thời gian điều tra.

Ví dụ, một deadlock đơn lẻ có thể không cần page on-call nếu retry phục hồi và không ảnh hưởng SLO. Nhưng deadlock rate tăng gấp nhiều lần baseline cùng lúc retry amplification và p99 latency tăng là dấu hiệu cần điều tra ngay.

### Burn rate quan trọng hơn một counter đơn lẻ

Nếu hệ thống có SLO về tỷ lệ request thành công hoặc latency, hãy xem lỗi concurrency đang tiêu thụ error budget nhanh đến đâu. Deadlock được retry thành công có thể không làm request cuối thất bại, nhưng vẫn làm latency tăng và throughput giảm. Do đó, SLO latency và saturation có thể báo vấn đề trước khi success-rate SLO bị ảnh hưởng.

Không tạo cảnh báo chỉ từ counter tích lũy. Dùng rate/delta trong cửa sổ thời gian và đối chiếu với traffic.

## 14. Quy trình chẩn đoán khi tỷ lệ tăng

Khi dashboard cho thấy deadlock, serialization failure hoặc retry tăng, thực hiện theo thứ tự:

### Bước 1: xác nhận metric và mẫu số

Kiểm tra counter có reset không, scrape có thiếu dữ liệu không, số transaction attempts có tăng/giảm bất thường không và metric database/app có cùng phạm vi hay không. Một tỷ lệ tăng có thể do mẫu số giảm chứ không phải số lỗi tăng.

### Bước 2: phân loại lỗi

Tách deadlock victim, serialization failure, lock timeout, query timeout và connection acquisition timeout. Xác định SQLSTATE/vendor code thay vì chỉ dựa vào message text.

### Bước 3: xác định operation và resource nóng

Nhóm theo operation, query fingerprint, bảng/index hoặc aggregate key đã được chuẩn hóa. Đọc deadlock graph để xác định chu trình; xem lock wait để tìm blocker; kiểm tra execution plan và transaction duration.

### Bước 4: ghép database event với application trace

Dùng timestamp, session ID, trace ID, transaction label và SQL fingerprint để tìm logical operation tương ứng. Xác định lỗi xảy ra ở attempt nào, retry có bắt đầu transaction mới không và caller cuối cùng nhận outcome gì.

### Bước 5: đánh giá tác động retry

Xem retry amplification, recovery rate, exhaustion, deadline remaining và p95/p99 latency. Nếu retry đang che lỗi nhưng làm request vượt SLA, vẫn cần xử lý nguyên nhân gốc.

### Bước 6: thay đổi và kiểm chứng

Tùy nguyên nhân, có thể thống nhất thứ tự khóa, rút ngắn transaction, thêm index phù hợp, thu hẹp phạm vi truy vấn, dùng conditional update/constraint hoặc điều chỉnh isolation. Kiểm tra lại bằng reproducer nhiều connection và theo dõi metric sau triển khai.

## 15. Ví dụ instrumentation ở tầng retry policy

Instrumentation nên đặt tại nơi ứng dụng biết cả logical operation lẫn từng transaction attempt. Ví dụ giả mã Java:

```java
Result executeWithRetry(Command command) {
    operationStarted.increment();
    long started = System.nanoTime();
    boolean retried = false;

    for (int attempt = 1; attempt <= maxAttempts; attempt++) {
        transactionAttempts.increment();
        Timer.Sample sample = Timer.start(registry);

        try {
            Result result = transactionWorker.executeOnce(command);
            sample.stop(transactionDuration);
            operationSucceeded.increment();
            operationDuration.record(elapsedSince(started));

            if (retried) {
                recoveredAfterRetry.increment();
            }
            return result;
        } catch (Exception error) {
            sample.stop(transactionDuration);
            RetryReason reason = classify(error);
            attemptFailures(reason).increment();

            if (!isRetryable(reason) || attempt == maxAttempts) {
                operationFailed.increment();
                operationDuration.record(elapsedSince(started));
                throw error;
            }

            retried = true;
            retryAttempts(reason).increment();
            // Rollback đã hoàn tất khi executeOnce kết thúc bằng lỗi.
            // Backoff có giới hạn bởi deadline và dùng jitter.
            waitBeforeNextAttempt(reason, attempt, remainingBudget(started));
        }
    }

    throw new IllegalStateException("Unreachable");
}
```

Đây là cấu trúc minh họa, không phải mã có thể biên dịch nguyên trạng. Cần bảo đảm `transactionWorker.executeOnce` thực sự tạo transaction mới cho mỗi lần gọi, exception được phân loại đúng, timer ghi đúng outcome và nhánh deadline/exhaustion được đo riêng. Nếu một lần thực thi thất bại trước khi transaction bắt đầu, hãy phân biệt pool acquisition failure với database transaction failure.

Không ghi một metric `retry_attempts` tăng cho lần đầu. Chỉ tăng counter retry khi ứng dụng thực sự quyết định sẽ thực hiện attempt tiếp theo. Nếu đã gặp lỗi retryable nhưng deadline hết trước khi thử lại, ghi nhận deadline exhaustion riêng.

## 16. Những sai lầm thường gặp khi đo

- **Chỉ đếm deadlock thô:** không biết mức độ ảnh hưởng khi throughput thay đổi. Chuẩn hóa theo transaction attempts và traffic.
- **Dùng request làm mẫu số cho database deadlock counter:** một request có thể có nhiều transaction attempt; cần định nghĩa rõ đơn vị.
- **Gộp deadlock và serialization failure:** hai hiện tượng có nguyên nhân và cách chẩn đoán khác nhau.
- **Nhầm PostgreSQL `conflicts` với serialization failures:** counter đó chủ yếu liên quan recovery conflict trên standby.
- **Đọc counter tích lũy như số lỗi trong cửa sổ hiện tại:** phải lấy delta/rate và xử lý reset.
- **Chỉ đo lỗi cuối cùng:** retry có thể phục hồi nhưng làm latency và tải tăng mạnh.
- **Không đo retry amplification:** nhiều tầng retry có thể nhân số lần gọi.
- **Ghi raw SQL hoặc request ID làm label:** cardinality quá cao làm hỏng hệ thống metrics.
- **Retry mọi lỗi database:** constraint violation và validation thường không thể khắc phục bằng cách chạy lại cùng thao tác.
- **Retry statement cuối thay vì toàn transaction:** logic có thể dùng dữ liệu từ snapshot cũ.
- **Đánh giá recovery rate mà bỏ qua deadline:** thao tác thành công sau khi caller đã timeout vẫn là trải nghiệm thất bại.
- **Coi lock wait timeout là deadlock:** timeout không chứng minh có chu trình chờ.
- **Tăng maxAttempts để che contention:** có thể làm retry storm và pool saturation nặng hơn.

## 17. Cách thiết kế bộ chỉ số cho một hệ thống

Trước khi triển khai dashboard, hãy xác định:

1. Logical operation nào cần theo dõi và transaction attempt nào thuộc operation đó?
2. Database counter nào đo deadlock event, lock wait và transaction abort?
3. SQLSTATE/vendor code nào tương ứng deadlock, serialization failure và lock timeout trên engine đang dùng?
4. Mẫu số của mỗi tỷ lệ là transaction attempts, logical operations hay tổng request?
5. Retry rate có đếm operation được retry ít nhất một lần hay số retry attempt?
6. Retry amplification, recovery và exhaustion có được đo riêng không?
7. Latency histogram có bao gồm backoff, pool wait và toàn bộ attempt không?
8. Có thể nối application trace với session/database log bằng ID hoặc timestamp nào?
9. Metric labels có giới hạn cardinality không?
10. Counter reset, restart, scrape gap và traffic thấp được xử lý ra sao?
11. Baseline và SLO nào quyết định cảnh báo?
12. Khi cảnh báo kích hoạt, dashboard có dẫn tới deadlock graph, blocker và query fingerprint không?

Một bộ đo tốt phải cho biết không chỉ “có bao nhiêu deadlock”, mà còn “trên bao nhiêu attempt”, “operation nào bị ảnh hưởng”, “retry có cứu được không”, “đã tiêu tốn bao nhiêu thời gian” và “caller cuối cùng có đạt SLO không”.

## 18. Kết luận

Đo deadlock, serialization failure và retry cần tách rõ event ở database, transaction attempt và logical operation ở ứng dụng. Dùng counter của engine để theo dõi deadlock/lock wait, đếm serialization error theo SQLSTATE hoặc vendor code tại application boundary, rồi đo retry rate, amplification, recovery, exhaustion và latency theo từng operation.

Luôn công bố mẫu số của tỷ lệ, lấy delta từ counter tích lũy và xử lý restart/reset. Kết hợp dashboard database contention với trace attempt và outcome cuối để phát hiện trường hợp retry đang che lỗi nhưng làm tăng latency hoặc tải. Cảnh báo nên dựa trên baseline, SLO và xu hướng đã chuẩn hóa theo lưu lượng; không có một ngưỡng chung cho mọi hệ thống. Khi các chỉ số tăng, dùng deadlock graph, lock wait, query plan và application trace để tìm resource/transaction gây tranh chấp, sau đó kiểm chứng thay đổi bằng test đồng thời có thể tái hiện.
