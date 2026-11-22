# Ghi nhận số lần thử, nguyên nhân thất bại và kết quả cuối

Trong hệ thống có retry, một yêu cầu nghiệp vụ có thể được thực hiện nhiều lần trước khi thành công hoặc kết thúc thất bại. Ví dụ, một giao dịch cập nhật đơn hàng có thể gặp deadlock, được chạy lại, rồi thành công ở lần thử thứ ba. Nếu chỉ ghi một dòng log “request failed” hoặc chỉ đếm số request, đội vận hành khó biết có bao nhiêu lần thử đã xảy ra, lỗi nào kích hoạt retry và kết quả cuối cùng của yêu cầu là gì.

Để quan sát và xử lý retry đúng cách, cần phân biệt ba khái niệm:

- **Yêu cầu/operation:** một đơn vị nghiệp vụ mà người dùng hoặc hệ thống muốn hoàn thành, chẳng hạn tạo đơn hàng có mã yêu cầu `REQ-123`.
- **Lần thử/attempt:** một lần thực thi operation. Lần chạy đầu tiên là attempt 1; mỗi lần retry tạo một attempt tiếp theo.
- **Kết quả cuối/final outcome:** trạng thái kết thúc của operation sau khi đã thành công, thất bại vĩnh viễn, hết ngân sách retry, bị hủy hoặc cần xử lý tiếp ở hàng đợi lỗi.

Một operation có thể có nhiều attempt nhưng chỉ có một kết quả cuối được công bố. Việc ghi nhận đầy đủ lịch sử giúp trả lời các câu hỏi: operation đã thử bao nhiêu lần, mỗi lần thất bại vì sao, lỗi có được xem là retryable không, lần nào thành công và cuối cùng người dùng nhận kết quả gì.

## 1. Phân biệt operation, attempt và retry

Giả sử một API nhận yêu cầu chuyển tiền. Ứng dụng thử thực hiện transaction, nhưng lần đầu database báo deadlock. Chính sách cho phép retry tối đa hai lần sau lần chạy đầu. Lần thứ hai gặp lock timeout; lần thứ ba thành công.

```text
Operation: transfer-REQ-123

Attempt 1: bắt đầu -> deadlock -> thất bại, có thể retry
    |
    +-- backoff
         |
Attempt 2: bắt đầu -> lock timeout -> thất bại, có thể retry
    |
    +-- backoff
         |
Attempt 3: bắt đầu -> commit thành công
    |
Final outcome: SUCCEEDED
Total attempts: 3
Retries: 2
```

Quy ước nên thống nhất trong toàn hệ thống:

- `attempt_number` bắt đầu từ 1, bao gồm cả lần chạy đầu tiên.
- `retry_count = attempt_count - 1` khi operation đã có ít nhất một lần thử.
- `max_attempts` là tổng số lần thực thi tối đa, không phải số lần retry bổ sung. Ví dụ `max_attempts = 3` nghĩa là một lần đầu và tối đa hai lần retry.
- Mỗi attempt có một định danh riêng, nhưng tất cả attempt của cùng operation dùng chung `operation_id` hoặc `correlation_id`.
- Kết quả cuối được gắn với operation, không bị nhầm với kết quả của một attempt riêng lẻ.

Không thống nhất cách đếm thường dẫn đến số liệu sai. Một dashboard ghi “retry count = 3” có thể được hiểu là ba lần chạy tổng cộng hoặc ba lần chạy lại sau lần đầu. Hãy ghi rõ `attempt_count` và `retry_count` thành hai trường riêng nếu cả hai đều cần thiết.

## 2. Phân loại nguyên nhân thất bại

Không phải mọi lỗi đều nên retry. Trước khi ghi nhận lỗi, ứng dụng cần phân loại nguyên nhân để chính sách retry và báo cáo phản ánh đúng bản chất.

| Nhóm lỗi | Ví dụ | Có thể retry? | Hướng xử lý |
|---|---|---|---|
| Xung đột đồng thời tạm thời | Deadlock, serialization failure, optimistic version conflict | Thường có, nếu toàn bộ operation có thể chạy lại an toàn | Rollback, đọc lại dữ liệu và retry toàn transaction |
| Chờ tài nguyên quá hạn | Lock wait timeout, pool acquisition timeout | Có thể, tùy ngân sách và mức tranh chấp | Backoff, giới hạn lần thử và thời gian tổng |
| Lỗi kết nối/tạm thời | Mất kết nối, database failover, HTTP 503 | Có thể, nhưng cần xác định kết quả trước đó có rõ ràng không | Retry có kiểm soát và dùng idempotency |
| Dữ liệu/nghiệp vụ không hợp lệ | Vi phạm constraint, số dư không đủ, trạng thái không cho phép | Thường không | Trả lỗi nghiệp vụ hoặc yêu cầu người dùng sửa dữ liệu |
| Xác thực/phân quyền | Sai thông tin đăng nhập, thiếu quyền | Thường không | Sửa cấu hình hoặc quyền; không retry liên tục |
| Hết hạn hoặc bị hủy | Request deadline, người dùng hủy, worker bị dừng | Không tự động retry nếu không còn ngân sách hoặc yêu cầu đã bị hủy | Ghi nhận trạng thái hủy/hết hạn và chuyển giao nếu cần |
| Kết quả không xác định | Mất kết nối khi gửi COMMIT hoặc khi gọi dịch vụ ngoài | Không thể kết luận chỉ từ lỗi | Tra cứu trạng thái bằng idempotency key hoặc reconciliation |

`retryable` là quyết định của chính sách ứng dụng, không nên suy ra chỉ từ việc có exception. Ví dụ, lỗi kết nối có thể xảy ra trước khi database nhận lệnh, nhưng cũng có thể xảy ra sau khi database đã commit mà phản hồi chưa tới client. Hai trường hợp cần cách xử lý khác nhau.

### Ghi mã lỗi có cấu trúc

Thay vì chỉ lưu thông điệp tự do như `Something went wrong`, nên ghi các trường có thể lọc và thống kê:

- `failure_category`: `DEADLOCK`, `LOCK_TIMEOUT`, `SERIALIZATION_FAILURE`, `VALIDATION`, `CONNECTION`, `DEADLINE_EXCEEDED`...
- `error_code`: SQLState, mã lỗi vendor, mã HTTP hoặc mã lỗi nghiệp vụ.
- `exception_type`: tên lớp exception hoặc loại lỗi từ thư viện.
- `failure_phase`: `START`, `DATABASE`, `COMMIT`, `REMOTE_CALL`, `CANCELLED`...
- `retryable`: quyết định của chính sách tại thời điểm lỗi.
- `safe_message`: thông tin ngắn đã loại bỏ dữ liệu nhạy cảm.

Giữ cả mã lỗi gốc và phân loại chuẩn hóa. Mã gốc giúp điều tra theo database/driver; phân loại chuẩn hóa giúp dashboard tổng hợp lỗi từ nhiều dịch vụ.

## 3. Phân biệt lỗi của attempt và kết quả cuối của operation

Một attempt thất bại không có nghĩa operation đã thất bại cuối cùng. Nếu attempt 1 gặp deadlock nhưng attempt 2 thành công, lịch sử attempt phải giữ cả hai kết quả, trong khi final outcome của operation là `SUCCEEDED`.

Các trạng thái operation thường gặp:

| Final outcome | Ý nghĩa |
|---|---|
| `SUCCEEDED` | Operation hoàn thành và kết quả đã được xác nhận |
| `FAILED_PERMANENT` | Lỗi không thể khắc phục bằng retry, ví dụ dữ liệu không hợp lệ hoặc không đủ quyền |
| `FAILED_RETRY_EXHAUSTED` | Đã dùng hết số lần thử hoặc ngân sách retry mà vẫn chưa thành công |
| `TIMED_OUT` | Hết deadline tổng của operation |
| `CANCELLED` | Operation bị hủy theo yêu cầu hoặc chính sách |
| `PENDING_RECONCILIATION` | Chưa xác định được kết quả, cần tra cứu hoặc đối soát trước khi kết luận |
| `DEAD_LETTERED` | Công việc được chuyển sang hàng đợi lỗi để điều tra hoặc xử lý thủ công |

Không nhất thiết mọi hệ thống phải dùng tất cả trạng thái này. Hãy chọn tập trạng thái vừa đủ cho nghiệp vụ và định nghĩa rõ chuyển trạng thái nào được phép. Đặc biệt, không đánh dấu `FAILED_PERMANENT` khi kết quả thực tế còn chưa xác định.

Ví dụ state flow:

```text
PENDING
   |
   v
RUNNING (attempt 1)
   |
   +-- success ------------------------> SUCCEEDED
   |
   +-- permanent failure -------------> FAILED_PERMANENT
   |
   +-- retryable failure
          |
          +-- còn ngân sách -----------> WAITING_RETRY -> RUNNING (attempt 2...)
          |
          +-- hết ngân sách -----------> FAILED_RETRY_EXHAUSTED
   |
   +-- kết quả không rõ ---------------> PENDING_RECONCILIATION
```

Operation chỉ được chuyển sang một trạng thái cuối theo quy tắc nghiệp vụ. Nếu có nhiều worker xử lý đồng thời, việc cập nhật trạng thái cuối phải được bảo vệ bằng optimistic version, khóa hoặc câu lệnh cập nhật có điều kiện để tránh hai worker cùng ghi hai kết quả khác nhau.

## 4. Thiết kế dữ liệu để lưu lịch sử attempt

Với operation quan trọng, log ứng dụng có thể chưa đủ vì log có thể bị xoay vòng, thất lạc hoặc không được lưu cùng trạng thái nghiệp vụ. Có thể lưu một bản ghi operation và một bảng attempt history trong database.

Ví dụ schema khái quát theo PostgreSQL:

```sql
CREATE TABLE operation_run (
    operation_id UUID PRIMARY KEY,
    idempotency_key VARCHAR(120) UNIQUE,
    operation_type VARCHAR(80) NOT NULL,
    status VARCHAR(40) NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    final_error_category VARCHAR(60),
    final_error_code VARCHAR(120),
    result_reference VARCHAR(200),
    version BIGINT NOT NULL DEFAULT 0
);

CREATE TABLE operation_attempt (
    attempt_id UUID PRIMARY KEY,
    operation_id UUID NOT NULL REFERENCES operation_run(operation_id),
    attempt_number INTEGER NOT NULL,
    status VARCHAR(30) NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    failure_category VARCHAR(60),
    error_code VARCHAR(120),
    exception_type VARCHAR(200),
    failure_phase VARCHAR(40),
    retryable BOOLEAN,
    next_retry_at TIMESTAMPTZ,
    duration_ms BIGINT,
    UNIQUE (operation_id, attempt_number)
);
```

Bảng `operation_run` lưu trạng thái tổng thể và kết quả cuối. Bảng `operation_attempt` lưu từng lần thực thi. Ràng buộc `UNIQUE (operation_id, attempt_number)` ngăn ghi trùng số lần thử cho cùng operation.

Một số trường có thể bổ sung tùy nhu cầu:

- `correlation_id` hoặc `trace_id` để liên kết với log và distributed trace.
- `worker_id` hoặc `instance_id` để biết worker nào xử lý attempt.
- `scheduled_at` và `next_retry_at` để quan sát lịch retry.
- `retry_delay_ms` để biết chính sách backoff thực tế.
- `input_hash` hoặc `payload_reference` để liên kết payload mà không sao chép dữ liệu nhạy cảm.
- `result_reference` để trỏ đến đơn hàng, giao dịch hoặc kết quả nghiệp vụ đã tạo.

Không nên lưu toàn bộ payload nhạy cảm, access token, mật khẩu hoặc dữ liệu thẻ thanh toán vào bảng lịch sử lỗi. Chỉ lưu mã tham chiếu hoặc các trường đã được lọc cần thiết cho điều tra.

## 5. Ghi nhận attempt bắt đầu và kết thúc

Một attempt có vòng đời rõ ràng:

1. Tạo attempt record với `status = RUNNING`, số thứ tự và thời điểm bắt đầu.
2. Thực thi transaction hoặc lời gọi dịch vụ.
3. Nếu thành công, ghi `status = SUCCEEDED`, `finished_at`, `duration_ms` và tham chiếu kết quả.
4. Nếu thất bại, ghi `status = FAILED`, phân loại nguyên nhân, mã lỗi, giai đoạn lỗi và quyết định có retry hay không.
5. Nếu sẽ retry, ghi `next_retry_at` và cập nhật operation sang trạng thái chờ retry.
6. Nếu không retry nữa, cập nhật final outcome của operation.

```text
Tạo operation
   |
Tạo attempt 1: RUNNING
   |
Thực thi nghiệp vụ
   |
   +-- thành công --> attempt 1 SUCCEEDED --> operation SUCCEEDED
   |
   +-- thất bại --> attempt 1 FAILED
                       |
                       +-- retryable và còn ngân sách
                       |      -> WAITING_RETRY
                       |      -> tạo attempt 2
                       |
                       +-- không retry
                              -> operation FAILED_...
```

`started_at` và `finished_at` giúp tính thời gian của mỗi attempt. `next_retry_at` cho biết hệ thống dự kiến chạy lại lúc nào. Nếu worker chết khi đang chạy, attempt có thể còn `RUNNING`; hệ thống cần lease, heartbeat hoặc timeout để xác định attempt bị bỏ dở và xử lý lại một cách an toàn.

## 6. Ghi lịch sử khi transaction bị rollback

Một vấn đề thực tế là nếu attempt history được ghi trong chính transaction nghiệp vụ rồi transaction rollback, bản ghi lịch sử cũng bị rollback. Khi đó, hệ thống không lưu được nguyên nhân thất bại.

Có một số cách thiết kế:

### Ghi lịch sử bằng transaction riêng

Khi transaction nghiệp vụ thất bại và đã rollback, ứng dụng mở transaction khác để ghi attempt failure. Cách này đơn giản, nhưng có một khoảng thời gian giữa lúc lỗi xảy ra và lúc lịch sử được ghi. Nếu tiến trình chết trong khoảng đó, attempt có thể không có bản ghi kết thúc.

### Ghi attempt start trước khi thực thi

Tạo bản ghi `RUNNING` trước khi bắt đầu transaction nghiệp vụ. Nếu worker chết hoặc transaction rollback, một bộ giám sát có thể phát hiện attempt đã quá lâu không được cập nhật và đánh dấu `ABANDONED`/`TIMED_OUT` theo chính sách. Cần heartbeat hoặc lease để phân biệt worker chết với tác vụ vẫn đang chạy lâu.

### Dùng event/outbox hoặc hệ thống quan sát bên ngoài

Có thể phát sự kiện attempt started/failed vào hệ thống log hoặc message broker. Nếu cần bảo đảm sự kiện được phát cùng với thay đổi nghiệp vụ đã commit, dùng transactional outbox: ghi sự kiện outbox trong cùng transaction với dữ liệu nghiệp vụ, rồi worker phát sự kiện sau commit. Với sự kiện về transaction đã rollback, cần ghi bằng transaction riêng hoặc phát ra hệ thống quan sát bên ngoài sau khi xác định rollback.

Không có cách nào bảo đảm tuyệt đối lịch sử đầy đủ nếu tiến trình có thể chết đúng giữa mọi bước. Vì vậy, thiết kế cần kết hợp bản ghi start, lease/heartbeat, recovery và đối soát để tìm attempt bị bỏ dở.

## 7. Ghi log có cấu trúc cho từng attempt

Log nên là dữ liệu có cấu trúc để có thể lọc theo operation, attempt, loại lỗi hoặc thời gian. Ví dụ JSON:

```json
{
  "event": "operation_attempt_failed",
  "operation_id": "7e2c1b7a-8a3d-4b22-9a0c-1d6d10c00001",
  "attempt_id": "c12b5d80-5c9a-4e4d-9c3e-3a1d5f000002",
  "attempt_number": 2,
  "max_attempts": 4,
  "operation_type": "TRANSFER",
  "failure_category": "DEADLOCK",
  "error_code": "40P01",
  "failure_phase": "DATABASE",
  "retryable": true,
  "duration_ms": 184,
  "next_retry_delay_ms": 250,
  "trace_id": "trace-example-001"
}
```

Các trường giúp người vận hành biết đây là attempt thứ hai của operation nào, lỗi gì, có retry hay không và khi nào dự kiến chạy lại. Không nên đưa nội dung exception đầy đủ vào mọi log nếu nó có thể chứa SQL parameters hoặc dữ liệu cá nhân. Có thể ghi `exception_type`, mã lỗi và thông điệp đã làm sạch.

Nên phân biệt event log với access log. Một request có thể sinh nhiều event: operation accepted, attempt started, attempt failed, retry scheduled và operation completed. Mỗi event có timestamp riêng nhưng dùng chung `operation_id` để nối chuỗi.

## 8. Liên kết attempt với trace và correlation ID

Trong hệ thống nhiều dịch vụ, operation có thể đi qua API gateway, service nghiệp vụ, database và worker queue. Mỗi attempt có thể chạy ở một process hoặc instance khác nhau. Nếu chỉ dựa vào thread ID hoặc request ID của lần gọi HTTP ban đầu, việc theo dõi có thể bị đứt khi message được đưa vào queue.

Nên duy trì các định danh:

- `operation_id`: định danh ổn định cho một yêu cầu nghiệp vụ xuyên suốt các lần retry.
- `attempt_id`: định danh riêng cho một lần thực thi.
- `correlation_id`: định danh liên kết các thành phần tham gia cùng luồng nghiệp vụ.
- `trace_id` và `span_id`: định danh trong distributed tracing; mỗi attempt hoặc lần gọi phụ có thể tạo span riêng nhưng vẫn nằm trong trace phù hợp.
- `idempotency_key`: khóa chống thực thi trùng cho operation từ phía client hoặc producer.

Không dùng `attempt_id` làm idempotency key vì mỗi lần retry có attempt ID khác nhau. Nếu dùng ID khác nhau cho mỗi lần gửi lại, dịch vụ đích có thể hiểu đó là những yêu cầu nghiệp vụ mới và thực hiện trùng lặp.

## 9. Ghi nhận nguyên nhân và quyết định retry

Nguyên nhân lỗi và quyết định retry nên là hai thông tin riêng:

- `failure_category = DEADLOCK` mô tả điều gì đã xảy ra.
- `retryable = true` mô tả chính sách ứng dụng cho phép thử lại.
- `retry_policy = DB_TRANSIENT_V2` cho biết quy tắc nào đã đưa ra quyết định.
- `next_retry_at` hoặc `retry_delay_ms` ghi lại lịch thử lại đã chọn.

Cùng một loại lỗi có thể có quyết định retry khác nhau theo operation. Ví dụ, lock timeout trong một tác vụ đọc báo cáo có thể retry một lần; lock timeout khi deadline request gần hết có thể không retry. Việc lưu quyết định và phiên bản chính sách giúp giải thích tại sao hai operation gặp cùng mã lỗi nhưng có kết quả khác nhau.

Ví dụ:

| Lỗi | Bối cảnh | Quyết định có thể dùng |
|---|---|---|
| Deadlock | Transaction cập nhật có thể chạy lại an toàn | Retry toàn transaction |
| Optimistic version conflict | Người dùng chỉnh sửa biểu mẫu | Trả conflict để người dùng hợp nhất thay đổi |
| Lock timeout | Worker queue còn nhiều thời gian | Backoff rồi retry |
| Validation/constraint violation | Dữ liệu đầu vào sai | Không retry |
| HTTP 503 | Dịch vụ đích hỗ trợ idempotency | Retry có backoff và cùng idempotency key |
| Timeout khi commit | Không rõ database đã commit hay chưa | Tra cứu trạng thái, không tạo operation mới |

## 10. Kết quả cuối và trường hợp không rõ kết quả

Một operation chỉ nên được đánh dấu `SUCCEEDED` khi ứng dụng có bằng chứng rằng kết quả nghiệp vụ đã được xác nhận. Với transaction database, đó thường là commit được xác nhận. Với lời gọi dịch vụ ngoài, cần dựa vào phản hồi hoặc cơ chế tra cứu trạng thái được dịch vụ đó hỗ trợ.

Nếu kết nối bị mất đúng lúc gửi `COMMIT`, ứng dụng có thể không biết transaction đã commit hay chưa. Nếu ghi `FAILED` rồi chạy lại bằng operation ID mới, có nguy cơ thực hiện chuyển tiền hoặc tạo đơn hàng hai lần. Nếu ghi `SUCCEEDED` mà database thực tế rollback, hệ thống lại báo thành công sai.

Trong tình huống này, nên ghi trạng thái trung gian như `PENDING_RECONCILIATION` hoặc `UNKNOWN_OUTCOME`, rồi tra cứu theo idempotency key, business reference hoặc transaction reference. Chỉ sau khi xác định trạng thái mới chuyển operation sang `SUCCEEDED` hoặc `FAILED_PERMANENT`.

Ví dụ luồng:

```text
Gửi COMMIT
   |
   +-- nhận xác nhận commit ----------> SUCCEEDED
   |
   +-- nhận lỗi rollback rõ ràng -----> FAILED / có thể retry
   |
   +-- mất kết nối, kết quả không rõ -> PENDING_RECONCILIATION
                                           |
                                           +-- tra cứu thấy đã commit -> SUCCEEDED
                                           +-- tra cứu thấy chưa commit -> retry an toàn
                                           +-- vẫn chưa rõ -> tiếp tục đối soát
```

## 11. Chống thực thi trùng bằng idempotency

Ghi nhận attempt chỉ giúp quan sát; nó không tự ngăn một operation được thực hiện hai lần. Với operation tạo dữ liệu hoặc gọi dịch vụ ngoài, cần một khóa idempotency ổn định.

Ví dụ bảng lưu kết quả idempotency:

```sql
CREATE TABLE idempotency_record (
    idempotency_key VARCHAR(120) PRIMARY KEY,
    request_hash VARCHAR(128) NOT NULL,
    status VARCHAR(30) NOT NULL,
    result_reference VARCHAR(200),
    created_at TIMESTAMP NOT NULL
);
```

Khi nhận request:

1. Tìm `idempotency_key` đã tồn tại chưa.
2. Nếu chưa có, tạo record và thực hiện operation theo transaction phù hợp.
3. Nếu đã hoàn tất, trả lại kết quả đã lưu.
4. Nếu đang xử lý, trả trạng thái đang xử lý hoặc cho phép caller tra cứu sau.
5. Nếu key tồn tại nhưng request hash khác, từ chối vì cùng key đang được dùng cho payload khác.

Mọi retry của cùng một operation phải dùng lại idempotency key. Nếu mỗi attempt dùng key mới, lớp idempotency không thể nhận ra các lần gửi lại là cùng một yêu cầu nghiệp vụ.

## 12. Metrics để hiểu chất lượng retry

Log cho biết chi tiết một operation; metrics cho thấy xu hướng toàn hệ thống. Nên tách số lượng operation khỏi số lượng attempt.

Một số metrics hữu ích:

| Metric | Ý nghĩa |
|---|---|
| `operations_started_total` | Tổng số operation được tiếp nhận |
| `operations_succeeded_total` | Tổng số operation kết thúc thành công |
| `operations_failed_total` | Tổng số operation kết thúc thất bại |
| `attempts_started_total` | Tổng số attempt đã bắt đầu, bao gồm lần đầu và retry |
| `attempts_failed_total` | Tổng số attempt thất bại |
| `retries_scheduled_total` | Số lần retry được lên lịch |
| `retry_exhausted_total` | Số operation hết ngân sách retry |
| `attempt_duration_seconds` | Thời gian của mỗi attempt |
| `operation_duration_seconds` | Tổng thời gian từ lúc nhận operation đến kết quả cuối |
| `retry_delay_seconds` | Khoảng chờ giữa các attempt |
| `unknown_outcome_total` | Số operation cần đối soát vì kết quả chưa rõ |

Có thể tính:

\[
\text{Average attempts per operation} =
\frac{\text{attempts started}}{\text{operations started}}
\]

\[
\text{Retry rate} =
\frac{\text{retries scheduled}}{\text{operations started}}
\times 100\%
\]

Hai chỉ số này cần được xem cùng tỷ lệ thành công cuối, độ trễ operation và số operation hết retry. Retry rate tăng có thể là dấu hiệu database quá tải, deadlock, dịch vụ phụ thuộc không ổn định hoặc chính sách retry quá nhạy.

Tránh dùng `operation_id`, `attempt_id`, email, user ID hoặc idempotency key làm nhãn metric có cardinality cao. Những giá trị này phù hợp với log/trace; metrics nên dùng nhãn có tập giá trị hữu hạn như `operation_type`, `failure_category`, `service` và `final_outcome`.

## 13. Dashboard và cảnh báo

Một dashboard retry nên giúp trả lời:

- Tỷ lệ operation thành công cuối cùng là bao nhiêu?
- Bao nhiêu operation cần nhiều hơn một attempt?
- Nhóm lỗi nào đang tạo ra nhiều retry nhất?
- Thời gian trung bình, p95 và p99 của attempt và operation thay đổi ra sao?
- Bao nhiêu operation đang chờ retry, đã hết retry hoặc chờ đối soát?
- Có operation nào có attempt `RUNNING` quá lâu mà không có heartbeat không?
- Retry tăng có tập trung vào một database, shard, endpoint hoặc loại nghiệp vụ không?

Ví dụ một tình huống cần điều tra:

```text
Operations started:           ổn định
Attempts per operation:       tăng từ 1.02 lên 1.80
Deadlock failures:            tăng mạnh
Final success rate:           giảm
Operation p99 duration:       tăng

Diễn giải:
Nhiều operation phải thử lại do deadlock; retry làm tăng tải và kéo dài thời gian hoàn tất.
Hãy tìm các transaction cùng khóa tài nguyên theo thứ tự khác nhau, rồi điều chỉnh thứ tự truy cập hoặc giảm thời gian giữ khóa.
```

Không nên chỉ cảnh báo khi `attempts_failed_total` tăng. Một operation có thể có một attempt thất bại rồi thành công; chỉ số này tăng nhưng trải nghiệm người dùng vẫn tốt. Cần theo dõi đồng thời final outcome, retry rate, thời gian hoàn tất và số operation chưa được giải quyết.

## 14. Lưu lịch sử lâu dài và quyền riêng tư

Lịch sử attempt có thể tăng nhanh trong hệ thống có lưu lượng lớn. Nên xác định thời hạn lưu theo nhu cầu điều tra, kiểm toán và quy định dữ liệu:

- Lưu chi tiết attempt trong khoảng thời gian cần cho điều tra sự cố.
- Giữ số liệu tổng hợp lâu hơn để phân tích xu hướng.
- Có thể phân vùng bảng attempt theo thời gian để dọn dữ liệu cũ hiệu quả.
- Lưu thông điệp lỗi đã làm sạch; tránh lưu payload đầy đủ hoặc bí mật xác thực.
- Hạn chế quyền đọc lịch sử có chứa thông tin nghiệp vụ nhạy cảm.
- Đảm bảo thao tác xóa hoặc ẩn danh dữ liệu tuân theo chính sách lưu trữ của hệ thống.

Không nên dùng bảng attempt như một nơi lưu trữ vô hạn mọi request body. Chỉ ghi dữ liệu cần thiết để giải thích nguyên nhân và kết quả.

## 15. Quy trình thiết kế ghi nhận retry

Khi xây dựng một operation có thể retry, hãy xác định trước:

1. **Định danh operation:** tạo `operation_id` và idempotency key ổn định xuyên suốt các lần thử.
2. **Định danh attempt:** tạo `attempt_id`, đánh số từ 1 và quy định `max_attempts` là tổng số lần chạy.
3. **Phân loại lỗi:** chuẩn hóa category, error code, exception type và failure phase.
4. **Quyết định retry:** lưu `retryable`, phiên bản retry policy và delay/next retry time.
5. **Lưu trạng thái attempt:** ghi start, finish, duration và kết quả của từng lần.
6. **Lưu final outcome:** chỉ kết luận thành công hoặc thất bại cuối khi có bằng chứng; dùng trạng thái chờ đối soát khi kết quả chưa rõ.
7. **Chọn nơi ghi lịch sử:** tách transaction history khỏi transaction nghiệp vụ có thể rollback; dùng lease/heartbeat để phát hiện attempt bị bỏ dở.
8. **Liên kết quan sát:** truyền operation ID, correlation ID và trace context qua queue và dịch vụ phụ thuộc.
9. **Tạo metrics:** tách operation metrics khỏi attempt metrics và tránh nhãn cardinality cao.
10. **Đặt retention và quyền truy cập:** lưu đủ để điều tra nhưng không giữ dữ liệu nhạy cảm không cần thiết.

## 16. Những điểm cần nhớ

- Operation là yêu cầu nghiệp vụ; attempt là một lần thực thi; retry là lần thực thi bổ sung sau lần đầu.
- `attempt_count` bao gồm lần đầu; `retry_count` bằng số attempt trừ một.
- Một attempt thất bại không đồng nghĩa operation thất bại cuối cùng.
- Lưu cả nguyên nhân gốc, phân loại chuẩn hóa và quyết định retry.
- Phân biệt lỗi retryable, lỗi vĩnh viễn và kết quả chưa xác định.
- Lịch sử attempt trong transaction bị rollback cũng sẽ mất; cần thiết kế ghi độc lập, lease/heartbeat hoặc event phù hợp.
- Dùng operation ID ổn định, attempt ID riêng và idempotency key không đổi qua retry.
- Không đánh dấu thành công nếu commit chưa được xác nhận; kết quả không rõ cần đối soát.
- Theo dõi operation metrics và attempt metrics riêng để không nhầm retry tăng với operation tăng.
- Bảo vệ log và lịch sử khỏi payload nhạy cảm, đồng thời đặt retention phù hợp.

Ghi nhận retry đầy đủ giúp hệ thống giải thích được không chỉ một câu lệnh đã lỗi, mà cả hành trình của yêu cầu nghiệp vụ từ lần chạy đầu đến kết quả cuối. Khi mỗi attempt có định danh, thời gian, nguyên nhân và quyết định rõ ràng, đội phát triển có thể phân biệt lỗi tạm thời với lỗi vĩnh viễn, phát hiện retry bất thường và xác định chính xác operation nào cần đối soát hoặc can thiệp.
