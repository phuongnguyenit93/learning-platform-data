# Checklist production: Đã có runbook vận hành cho Spring Batch scaling

## 1. Vì sao có runbook là điều kiện trước khi lên production?

Module **SPRING_BATCH_SCALING_OPERATIONS** hướng tới mở rộng Spring Batch cho workload dữ liệu lớn bằng **multi-threaded step**, **parallel steps**, **partitioning** và các mô hình phân tán phù hợp. Khi đưa vào production, hiệu năng chỉ là một phần của bài toán: đội vận hành phải biết **phát hiện, khoanh vùng, dừng an toàn, khôi phục và đối soát dữ liệu** nếu JobRepository, worker, message broker, database hoặc external API gặp sự cố.

Trong chương **Checklist production**, mục **"Đã có runbook vận hành"** không đơn thuần là đánh dấu rằng có một tài liệu tên "Runbook". Điều kiện đạt phải là:

> **Người trực vận hành có thể nhận một cảnh báo thật, tìm đúng job/execution và dùng tài liệu được duyệt để thực hiện hoặc điều phối hành động an toàn, trong giới hạn quyền hạn, sau đó chứng minh trạng thái hệ thống và dữ liệu đã phục hồi đúng.**

Runbook tốt giảm thời gian xác định người phụ trách, tránh phán đoán lúc áp lực cao và nhất là ngăn những hành động gây mất dữ liệu như xóa message tồn đọng, đổi JobParameters tùy tiện hoặc sửa bảng metadata để "ép" job hoàn tất.

Sau bài học, bạn có thể:

- Xác định tiêu chuẩn **runbook production-ready** và phân biệt với tài liệu thiết kế/FAQ.
- Liệt kê những tình huống tối thiểu phải có playbook trong các kiểu Spring Batch scaling.
- Chuẩn hóa câu lệnh quan sát, quyết định **stop/restart/replay**, escalation và đối soát.
- Xây bảng cảnh báo, vai trò, quyền thao tác, điều kiện **GO/NO-GO** cho production.
- Diễn tập recovery, lưu bằng chứng và tổ chức vòng cải tiến runbook sau release/sự cố.

## 2. Runbook không phải design document

Một design document giải thích **vì sao** dùng remote partitioning hoặc cấu hình pool nào. Runbook trả lời **làm gì tiếp theo khi nhận triệu chứng cụ thể**, với đầu vào, quyền, hành động, tiêu chí an toàn và bước xác nhận.

| Loại tài liệu | Câu hỏi chính | Ví dụ |
|---|---|---|
| **Architecture/design** | Hệ thống được xây dựng thế nào? | Manager/worker, broker, JobRepository, transaction boundary |
| **Operating guide** | Vận hành thường ngày thế nào? | Lịch job, tăng giảm worker, bảo trì |
| **Runbook theo triệu chứng** | Khi một cảnh báo xảy ra, làm gì theo thứ tự? | Job stuck, DB lock, broker lag, worker crash |
| **Disaster recovery plan** | Khi mất hạ tầng hoặc dữ liệu lớn, khôi phục đến đâu? | Restore metadata DB, mất vùng triển khai |
| **Post-incident review** | Sự cố có nguyên nhân gì và cần cải thiện gì? | Timeline, root cause, action items |

Một runbook có thể liên kết tới architecture và dashboard, nhưng **không đẩy toàn bộ quyết định thao tác sang một đường dẫn mơ hồ**. Người trực phải thấy được ngay: tình trạng, nơi quan sát, hành động được phép, hành động bị cấm, khi nào chuyển cấp và điều kiện dừng xử lý.

## 3. Tiêu chuẩn "ĐÃ CÓ" – bằng chứng thay vì cam kết

| Yêu cầu | Bằng chứng chấp nhận | Không đạt khi |
|---|---|---|
| **Dễ tìm** | Đường dẫn cố định trong dashboard/alert hoặc trang vận hành chính; truy cập được khi service lỗi | Tài liệu nằm trong máy cá nhân hoặc link hỏng |
| **Có owner** | Tên nhóm/on-call, backup, kênh escalation và người phê duyệt hành động rủi ro | "Liên hệ dev" nhưng không rõ ai |
| **Đúng release** | Tên dịch vụ, môi trường, version, topology và ngày kiểm chứng | Lệnh/cấu hình của release cũ |
| **Có tiền điều kiện** | Quyền truy cập, môi trường, JobInstance/JobExecution, ảnh hưởng và rollback plan | Operator chạy lệnh khi chưa biết tác động |
| **Có bước phát hiện** | Alert cụ thể, ngưỡng, biểu đồ, log và cách phân biệt lỗi | Chỉ ghi "kiểm tra logs" |
| **Có thao tác chuẩn** | Các bước theo thứ tự, lệnh đọc/điều khiển qua công cụ được duyệt | Chỉ mô tả nguyên nhân mà không có hành động |
| **Có guardrails** | Danh sách điều cấm, approval gate, cách tránh mất/trùng dữ liệu | Khuyên kill process hoặc xóa queue vô điều kiện |
| **Có điểm thoát** | Điều kiện thành công, thất bại, thời hạn/escalation | Không biết khi nào kết thúc incident |
| **Có đối soát** | Cách kiểm chứng item/partition, business keys, side effects và checkpoint | Chỉ nhìn thấy trạng thái COMPLETED |
| **Được diễn tập** | Biên bản drill, người thực hiện, kết quả, lỗi phát hiện và phiên bản runbook | Runbook viết xong nhưng chưa thử |

Trạng thái **GO** chỉ được đưa ra khi các yêu cầu quan trọng đã qua kiểm chứng theo mức rủi ro của workload. Một runbook đầy đủ về câu chữ nhưng chưa xác minh được quyền operator, dashboard, JobRepository hay khôi phục từ lỗi là **NO-GO** hoặc cần chấp nhận rủi ro theo quy trình riêng của tổ chức.

## 4. Mẫu thông tin bắt buộc trên đầu mỗi runbook

Ví dụ bản ghi metadata **do dự án tự quản lý** (không phải file mà Spring Batch tự nạp):

~~~yaml
runbook:
  id: "batch-import-worker-unavailable"
  title: "Worker không phản hồi partition"
  service: "SPRING_BATCH_SCALING_OPERATIONS"
  environment: "production"
  ownerTeam: "data-platform"
  primaryOnCall: "on-call rotation / service directory"
  escalation: "database-oncall, messaging-oncall, incident-commander"
  supportedTopology: "remote-partitioning"
  releaseRange: "theo compatibility manifest đã kiểm chứng"
  lastVerified: "ghi ngày diễn tập thực tế"
  severity: "phân loại theo SLO và mức độ mất dữ liệu"
  evidence:
    - "jobExecutionId, stepExecutionId, partitionName"
    - "worker instance/release, request/reply correlation"
    - "StepExecution status, commit/rollback, backlog"
  recoveryApproval: "chỉ những hành động được cấp quyền"
~~~

Các giá trị owner và ngày ở trên **chỉ là placeholder**: trước production phải thay bằng danh bạ, lịch trực, nhóm hỗ trợ và bằng chứng diễn tập thật. Không ghi token, password, private key hay thông tin khách hàng vào runbook công khai.

Ngoài metadata, mỗi runbook nên có ít nhất các phần **Trigger → Impact → Preconditions → Triage → Mitigation → Recovery → Verification → Escalation → Rollback → Evidence**. Với sự cố gây hậu quả nghiệp vụ lớn, cần bổ sung bước xác nhận của business/data owner.

## 5. Ma trận các runbook bắt buộc theo kiểu scaling

| Tình huống | Multi-threaded step | Parallel steps | Local partitioning | Remote partitioning/chunking |
|---|---|---|---|---|
| Job chậm hoặc stuck | Thread dump, reader/writer, executor queue | Flow/step dependency, executor | Partition skew và active StepExecution | Broker lag, worker liveness, network |
| Pool/CPU/heap cạn | Executor, heap/GC, JDBC pool | Tổng tài nguyên nhiều flow | Tổng task trong một JVM | Tổng tài nguyên nhiều replica và broker |
| Retry/skip/rollback tăng | Chunk boundary, lỗi item/transaction | Step bị lỗi, luồng chờ | Retry theo partition | Ack/redelivery, idempotency và message timeout |
| JobRepository bị lock | Contention trên metadata | Nhiều step update | Nhiều partition update | Manager/worker dùng chung metadata DB |
| Crash và restart | Checkpoint, StepExecution, reader state | Trạng thái từng nhánh | Partition còn dang dở | Worker/manager crash, in-flight requests/replies |
| Deployment/rollback | Dừng job và restart cùng release | Thay đổi step graph | Partitioner/ExecutionContext version | Contract manager-worker, queue version, drain |
| Security/permission | Datasource/secret | Quyền step và dependency | File/DB access theo partition | Broker ACL, TLS/mTLS, credentials, worker identity |

Danh sách này là **tập tối thiểu để lập coverage**, không đòi hỏi mỗi ô tạo một tài liệu riêng. Có thể dùng một runbook chung với các nhánh theo topology, miễn rằng operator xác định chính xác **kiến trúc nào đang chạy** trước khi thao tác.

Không nên sao chép mù quáng runbook của local partitioning sang remote chunking: một bên có StepExecution/ExecutionContext theo partition, bên còn lại có payload chunk và reply correlation với rủi ro redelivery khác nhau.

## 6. Dữ liệu nhận diện một lần chạy: không được nhầm job với execution

Trước bất kỳ hành động nào, xác định chính xác:

- **Job name** và **identifying JobParameters**: thường dùng để xác định **JobInstance**.
- **JobInstance ID**: danh tính logic của một lần xử lý theo tham số định danh.
- **JobExecution ID**: một lần thử thực thi của JobInstance, có thể có nhiều lần qua restart.
- **StepExecution ID/name**: trạng thái một Step trong lần thực thi; với partitioning có thể có nhiều StepExecution.
- **BatchStatus/ExitStatus** và timestamp, commit/rollback/read/write counts, ExecutionContext checkpoint.
- **Worker process/container**, release, partition name, message ID/correlation khi có.

**Ví dụ:** JobInstance "import giao dịch ngày D" có thể có JobExecution đầu bị FAILED, sau đó được restart thành JobExecution tiếp theo. Chạy job với **JobParameters định danh mới** chỉ để vượt lỗi "already running" thường tạo JobInstance khác: nguy cơ xử lý lại cùng dữ liệu từ đầu.

Khi operator chỉ báo "job import đang lỗi" mà không có ID và tham số, runbook phải hướng dẫn tìm và **xác nhận phạm vi** trước khi stop/restart.

### 6.1. Trạng thái Spring Batch và ý nghĩa với runbook

| BatchStatus | Ý nghĩa vận hành cơ bản | Điều kiện xử lý |
|---|---|---|
| STARTING/STARTED | Đang bắt đầu hoặc đang chạy theo metadata | Kiểm tra tiến trình thật, StepExecution, transaction, broker trước khi can thiệp |
| STOPPING | Yêu cầu dừng đang được xử lý | Không mặc định đã dừng an toàn; xác minh worker/commit |
| STOPPED | Đã dừng có kiểm soát theo cơ chế framework | Kiểm tra restartable, checkpoint và trạng thái phụ thuộc |
| FAILED | Một lần thực thi thất bại | Chẩn đoán nguyên nhân rồi restart nếu job và dữ liệu cho phép |
| COMPLETED | Lần thực thi được đánh dấu hoàn tất | Vẫn phải đối soát dữ liệu nếu có sự cố trước đó |
| ABANDONED | Execution không được dự kiến restart theo trạng thái đó | Không ép restart; dùng quy trình xử lý riêng |
| UNKNOWN | Không rõ trạng thái nhất quán | Dừng tự động xử lý, điều tra commit/checkpoint và escalate |

**STARTED tồn tại lâu** có thể là job đang làm việc thật hoặc metadata cũ sau crash; không thể suy ra chỉ bằng một cột trạng thái. **Yêu cầu stop là hợp tác (cooperative)** và có thể không hoàn tất ngay nếu step đang chờ DB lock, network I/O hoặc có custom code không kiểm tra tín hiệu dừng.

## 7. Bảng cảnh báo gắn với hành động runbook

Cảnh báo phải có **hành động tiếp theo**, không chỉ hiển thị biểu đồ đỏ. Bảng dưới là ví dụ để thiết kế; ngưỡng cụ thể phải dựa trên baseline và SLO của hệ thống.

| Alert | Chẩn đoán đầu tiên | Điều kiện chuyển cấp |
|---|---|---|
| Job duration vượt SLO | JobExecution, step duration, phân bố partition, downstream | Có nguy cơ trễ cutoff hoặc chưa tìm được nguyên nhân trong thời hạn ứng cứu |
| Step không tiến triển quá thời hạn cho phép | So sánh thời gian last update, active worker, SQL wait, broker in-flight | Không xác định được worker/commit state |
| JDBC pending/timeout tăng | Pool active/pending, DB connection quota, lock wait | DB ảnh hưởng nhiều service hoặc có transaction blocker không rõ |
| JobRepository lock/deadlock | DB blocked/blocker, isolation, launcher trùng | Có nguy cơ metadata không nhất quán hoặc cần DBA can thiệp |
| Worker unavailable/restart loop | Pod/process event, image, secret, connection, StepExecution | Có request đang in-flight và chưa chứng minh idempotency |
| Broker request queue hoặc reply lag | Consumer count, unacked, routing, DLQ, connection | Message có nguy cơ hết hạn/đang được redeliver liên tục |
| Retry/rollback/skip tăng đột biến | Lỗi gốc, chunk commit, retry policy, dữ liệu nguồn | Có khả năng sai hoặc trùng business output |
| Heap/GC, CPU saturation | Executor active/queue, memory profile, load | OOM hoặc ảnh hưởng service khác |
| Không khớp đối soát | Business IDs, source/target count, side effects | Luôn chuyển cấp cho data owner trước replay diện rộng |

**Thực hành tốt:** thêm đường dẫn runbook, dashboard, môi trường và ID liên quan trong alert payload; tránh nhúng credential hoặc nội dung dữ liệu nhạy cảm.

## 8. Runbook tổng quát: từ nhận alert đến phục hồi

~~~mermaid
flowchart TD
    A[Alert / người dùng báo lỗi] --> B[Xác nhận environment, job và execution ID]
    B --> C{Rủi ro dữ liệu/ảnh hưởng diện rộng?}
    C -->|Có| D[Giảm nguồn việc mới, kích hoạt incident + owner]
    C -->|Chưa rõ/Không| E[Thu thập metrics/log và phân loại]
    D --> E
    E --> F{Bottleneck hoặc lỗi đã xác minh?}
    F -->|Chưa| G[Escalate, giữ bằng chứng; không thao tác phá hủy]
    F -->|Có| H[Mitigation trong quyền được cấp]
    H --> I[Xác minh DB, broker, worker, metadata ổn định]
    I --> J{State đủ tin để restart/replay?}
    J -->|Không| G
    J -->|Có| K[Khôi phục theo policy được thử nghiệm]
    K --> L[Đối soát output, side effects và SLA]
    L --> M{PASS?}
    M -->|Có| N[Mở tải dần, đóng incident, cập nhật runbook]
    M -->|Không| G
~~~

Luồng đề xuất theo thứ tự:

1. **Acknowledge và ghi incident ID.** Ghi thời gian bắt đầu, độ nghiêm trọng, ảnh hưởng tới deadline, service owner và người đang xử lý.
2. **Xác nhận execution.** Chụp metadata và thông tin phiên bản trước khi đổi hệ thống.
3. **Giảm blast radius.** Có thể tạm dừng việc launch job mới hoặc giảm concurrency nếu đã được phép; không dừng bừa các step có side effect đang commit.
4. **Phân loại nguyên nhân.** Chọn nhánh CPU/heap, DB locks, connection pool, broker/worker, data exception, credentials hoặc release mismatch.
5. **Mitigation có guardrail.** Chỉ dùng hành động đã được diễn tập; với hạ tầng dùng chung cần DBA/messaging owner phê duyệt.
6. **Phục hồi đúng semantics.** Xác định job có restart được không, partition/chunk nào đã commit, message nào unacked, worker cũ còn chạy không.
7. **Đối soát.** Kiểm tra cả metadata và dữ liệu nghiệp vụ, bao gồm side effect bên ngoài DB.
8. **Mở lại theo từng mức.** Theo dõi queue, rollback, duplicate, JDBC pending và thời gian hoàn thành; ghi timeline và action items.

Mọi runbook phải có nhánh **"không xác định được trạng thái"** để người trực **dừng và escalate**, thay vì suy đoán rồi replay.

## 9. Runbook tình huống 1: job hoặc partition bị stuck

### Trigger

Job vượt ngưỡng runtime/không tăng writeCount hay commitCount; một số partition vẫn STARTED hoặc manager không nhận reply đúng deadline.

### Triage

1. Xác nhận execution ID, release, StepExecution name, last updated, commit/rollback, số partition và worker active.
2. Kiểm tra CPU, GC, thread pool active/queue, JDBC pending, DB lock wait và query latency.
3. Với remote partitioning/chunking, kiểm tra broker request/reply queue, unacked, consumer count, DLQ và correlation.
4. Phân biệt **partition skew** (một partition quá lớn vẫn chạy) với **deadlock/DB wait**, **worker crash**, **broker misroute** hoặc **message serializer mismatch**.

### Mitigation và recovery

- Nếu partition hợp lệ vẫn tiến triển, theo dõi deadline và cân nhắc giảm việc mới thay vì giết worker.
- Nếu DB pool/CPU cạn, giảm áp lực theo resource budget; không đơn thuần tăng queue vô hạn hoặc số replica.
- Nếu worker đã chết, kiểm tra trạng thái persisted và in-flight trước khi lên lịch retry/restart.
- Nếu manager chờ reply nhưng worker đã commit, **không blind replay** vì có thể nhân đôi tác dụng phụ.

### Verification

Job/StepExecution đúng trạng thái; các partition dự kiến đều có kết quả; số key nghiệp vụ, tổng checksum/giá trị và side effect được đối soát. Queue trở lại mức nền, không có retry storm.

## 10. Runbook tình huống 2: JobRepository bị lock hoặc database quá tải

**Phân biệt trước:** row/table lock wait, deadlock victim, optimistic locking version conflict và JDBC connection acquisition timeout là **các nguyên nhân khác nhau**. Một log "metadata không cập nhật" chưa chứng minh bị khóa.

### Chuỗi hành động an toàn

1. Chụp lỗi SQLSTATE/vendor code, job/step ID, datasource, query bị chặn và timeline commit.
2. Xem session waiting/blocking, thời gian transaction, trạng thái idle-in-transaction hoặc DDL đang chạy với công cụ của database.
3. Kiểm tra **tổng** connections của manager/worker replica và các ứng dụng khác cùng dùng database.
4. Giảm scheduler/concurrent launcher hoặc worker pressure nếu được quyền; tránh thêm retry dồn dập.
5. Nếu cần terminate transaction/blocker, **escalate DBA và owner**; đánh giá rollback và dữ liệu đang commit trước khi can thiệp.
6. Chỉ restart sau khi resource ổn định và đã xác minh execution state/checkpoint.

**Không làm:** tự UPDATE/DELETE các bảng BATCH_*, sửa cột VERSION, đổi STATUS thành COMPLETED/FAILED hoặc hạ isolation chỉ để "mở khóa". Các thao tác này có thể phá tính nhất quán và làm restart xử lý trùng.

### Ví dụ truy vấn chỉ đọc cho PostgreSQL

Đây là ví dụ hỗ trợ xác định **session đang đợi và PID chặn**, không phải lệnh xử lý khóa; cần quyền giám sát phù hợp và kiểm tra SQL có chứa dữ liệu nhạy cảm trước khi chia sẻ:

~~~sql
SELECT
    waiting.pid AS waiting_pid,
    waiting.application_name AS waiting_app,
    waiting.wait_event_type,
    waiting.wait_event,
    waiting.query_start,
    blocker.pid AS blocking_pid,
    blocker.application_name AS blocking_app,
    blocker.state AS blocking_state,
    blocker.xact_start AS blocking_xact_start,
    waiting.query AS waiting_sql
FROM pg_stat_activity AS waiting
CROSS JOIN LATERAL unnest(
    pg_blocking_pids(waiting.pid)
) AS blocking_pid(pid)
JOIN pg_stat_activity AS blocker
  ON blocker.pid = blocking_pid.pid
WHERE waiting.datname = current_database()
ORDER BY waiting.query_start NULLS LAST;
~~~

Với MySQL, xem các view Performance Schema thích hợp như **data_lock_waits/data_locks** cho lock dữ liệu hoặc **metadata_locks** khi có DDL/MDL. Không dán SQL PostgreSQL vào DB vendor khác và không suy ra lock từ mỗi metric JDBC pending.

## 11. Runbook tình huống 3: worker/broker sự cố trong xử lý phân tán

Trong **remote partitioning**, worker thường chạy StepExecution đã được manager tạo và truy cập shared JobRepository. Trong **remote chunking**, manager gửi item/chunk, worker xử lý và trả response. Hai topology có failure boundary khác nhau.

| Giai đoạn xảy ra lỗi | Dữ liệu có thể đã tồn tại ở đâu? | Rủi ro nếu replay vô điều kiện |
|---|---|---|
| Request chưa được broker xác nhận | Chỉ có metadata manager hoặc producer buffer | Tạo thêm request cho execution đã có |
| Broker lưu request nhưng worker chưa nhận | Broker backlog | Gửi trùng message khi producer retry |
| Worker đang đọc/xử lý chưa commit | Transaction có thể rollback | Cần checkpoint và redelivery đúng |
| Worker commit business DB nhưng chưa ack/reply | Business data đã ghi, message có thể redeliver | Ghi trùng side effect |
| Worker update metadata nhưng reply mất | JobRepository có thể phản ánh tiến độ | Manager có thể tưởng execution còn chưa hoàn tất |
| Manager crash khi worker đang chạy | Worker có thể tiếp tục ghi | Worker mới/manager mới có thể xử lý chồng lấn |

### Recovery checklist

- Kiểm tra worker live/dead, log theo **jobExecutionId, stepExecutionId, partition name, message correlation**.
- Kiểm tra request/reply routing, queue depth, unacked, consumer count, DLQ, timeout, retry và retention.
- Xác định transaction nào đã commit; đối soát business key và side effects.
- Khôi phục kết nối broker/worker đúng release, secret và ACL; canary trước khi tăng consumer.
- Chỉ replay/restart theo quy trình đã kiểm thử với checkpoint và **idempotent writer**, không xóa queue để "dọn".

**Đặc biệt:** mTLS tới broker bảo vệ từng kết nối manager↔broker và worker↔broker; không tự bảo đảm mTLS cho đường JobRepository, cũng không giải quyết duplicate delivery.

## 12. Runbook tình huống 4: quá tải CPU/heap/queue/JDBC

Một hệ thống vừa mở rộng worker có thể chậm hơn vì database, broker hoặc API trở thành nút thắt chung. Runbook nên chỉ dẫn theo **nguyên nhân đã đo**, không chỉ có một nút "scale up".

| Dấu hiệu | Giả thuyết | Hành động cần được đánh giá |
|---|---|---|
| CPU worker cao, queue tăng, DB còn dư | CPU-bound và thiếu capacity xử lý | Scale worker trong ngân sách, benchmark throughput |
| Heap/GC tăng cùng queue | Unbounded queue/retained task hoặc memory leak | Giới hạn input, bounded queue, heap profile |
| JDBC pending tăng, DB lock wait cao | DB đang bão hòa hoặc transaction giữ lock | Giảm concurrency, rút ngắn transaction, DBA review |
| Broker lag tăng, consumer thấp | Worker down, routing/ACL lỗi hoặc capacity thấp | Khôi phục consumer và kiểm tra message compatibility |
| Retry và 429 API tăng khi scale | Rate limit/timeout downstream | Rate limit, backoff/jitter, giảm active worker |
| Nhiều partition chạy rất lâu, số item lệch | Partition skew | Phân tích phân bổ dữ liệu, chia lại ở release tương lai |

Giới hạn **executor threads, queue capacity, partition concurrency, consumer prefetch và JDBC pool** phải tính ở **toàn cụm**, không chỉ trên một pod. Tăng worker từ 8 lên 20 với pool 10 connections có thể tăng lượng kết nối tối đa tiềm năng từ 80 lên 200, trước khi tính manager và dịch vụ khác.

Runbook phải có **điểm dừng scaling**, ví dụ khi DB lock wait hoặc connection acquisition time vượt SLO, khi broker lag không giảm sau scale hoặc khi dữ liệu reconciliation thất bại.

## 13. Runbook tình huống 5: stop, restart và reprocess

Đây là nhánh rủi ro cao vì metadata và side effects phải nhất quán.

### Điều kiện trước khi bấm restart

- JobExecution đã ở trạng thái **cho phép restart** theo semantics và job configuration; **COMPLETED** không mặc nhiên được restart.
- Không còn manager/worker cũ đang thực thi cùng logical work, hoặc có **fencing/lease** và quy trình xử lý chồng lấn phù hợp.
- Lỗi gây FAILED/STOPPED đã được xử lý; resource như DB/broker/credentials hoạt động bình thường.
- Reader/processor/writer và ExecutionContext đủ tin cậy để tiếp tục từ checkpoint.
- Những side effect ngoài transaction (email, API, file, broker event) được thiết kế idempotent hoặc có đối soát/bù đắp.
- Người thực hiện có quyền thao tác đúng JobInstance, và có phương án rollback nếu restart gây vấn đề.

### Phân biệt thao tác

| Hành động | Ý nghĩa | Sai lầm cần tránh |
|---|---|---|
| **Stop** | Yêu cầu job đang chạy dừng có kiểm soát | Nghĩ rằng stop hoàn tất ngay khi API nhận yêu cầu |
| **Restart** | Khởi chạy lần thực thi tiếp cho cùng JobInstance được phép restart | Tự đổi identifying JobParameters |
| **Retry item/chunk** | Thử lại phần công việc trong chính sách fault tolerance | Retry vĩnh viễn lỗi không thể phục hồi |
| **Replay message** | Gửi/nhận lại request đã có | Bỏ qua commit/ack, gây duplicate side effects |
| **Reprocess toàn bộ** | Xử lý lại dữ liệu đã xử lý theo yêu cầu nghiệp vụ riêng | Gọi nhầm là restart và không có deduplication |

Với JobExecution còn **STARTED** nhưng process thực tế đã chết, **không sửa STATUS bằng SQL ngay**. Cần quy trình recovery dành cho stale executions, đánh giá transaction/in-flight, quyền thao tác và cách JobOperator/JobRepository phiên bản đang dùng xử lý. Nếu không chứng minh được state, dừng và escalate.

### Hậu kiểm

So sánh số item đọc/ghi với nguồn, skip/filter reason, khóa nghiệp vụ duy nhất, checksum/tổng tiền và số side effect đã phát. Dữ liệu đúng quan trọng hơn việc dashboard chuyển sang màu xanh.

## 14. Runbook tình huống 6: deployment, compatibility và rollback

Trong remote partitioning/remote chunking, manager và worker có thể được triển khai độc lập nên cần runbook cho **mixed-version**, **message tồn đọng** và **JobRepository schema/ExecutionContext**.

1. Xác định release manager và từng nhóm worker, phiên bản Spring Batch/Integration, message converter, tên step, contract ExecutionContext, schema repository.
2. Kiểm tra đã thử các cặp old/new cùng tồn tại hay chưa. Nếu không, áp dụng **quiesce/drain** thay vì rolling upgrade tự do.
3. Dừng nhận **job mới** theo quy trình đã duyệt; đợi active partitions/chunks, unacked messages và reply backlog về điều kiện được phép cắt.
4. Chụp metadata và backlog, ghi lại mọi job FAILED/STOPPED cần restart sau deploy.
5. Deploy canary một worker/manager với certificate và quyền phù hợp; đối soát kết quả request → worker → reply → metadata.
6. Mở lại tải theo mức tăng dần, theo dõi lỗi deserialize, unknown step, broker lag, JobRepository lock và duplicate keys.
7. Nếu rollback, kiểm tra bản cũ **có đọc được ExecutionContext và schema/message do bản mới tạo**. Chuyển image về A không đủ nếu B đã thay đổi dữ liệu lưu bền vững.

Mọi runbook deployment phải chứa điều kiện **abort/rollback**, người có quyền ra quyết định và phương án với những message đã vào queue mới.

## 15. Bảo mật, quyền operator và bằng chứng thao tác

Runbook chỉ hữu ích nếu người trực có **quyền đọc cần thiết** nhưng không có thừa quyền phá hủy.

| Role | Quyền nên có | Hành động cần phê duyệt/escalation |
|---|---|---|
| Viewer/on-call L1 | Xem dashboard, JobExplorer, log đã che dữ liệu nhạy cảm, trạng thái worker | Restart/replay/kill session |
| Batch operator L2 | Stop/restart job theo danh sách được cấp, điều chỉnh admission đã định nghĩa | Reprocess diện rộng, đổi metadata thủ công |
| DB on-call/DBA | Xem locks, transaction, connection và thao tác DB theo quy trình | Terminate blocker, migration, restore |
| Messaging/platform on-call | Quan sát queue/DLQ/consumer và vận hành broker được cấp quyền | Purge/replay diện rộng, thay retention/ACL |
| Data/business owner | Phê duyệt đối soát và xử lý dữ liệu sai/trùng | Xóa/bù đắp bản ghi nghiệp vụ |
| Incident commander | Điều phối quyết định tác động rộng và truyền thông | Hành động ngoài runbook/ngoài quyền thường lệ |

**Không đưa secret vào runbook**; dùng đường dẫn đến secret manager/quy trình truy cập đã phê duyệt. Audit log nên ghi **ai** thao tác, **lúc nào**, **đối tượng nào**, **lệnh/thay đổi gì**, **approval ticket** và kết quả, tránh ghi mật khẩu hoặc payload khách hàng.

Đối với remote execution, kiểm tra chính sách TLS/mTLS theo từng hop, broker queue ACL, database privilege và khả năng rotation certificate. Một service account đủ quyền publish request không có nghĩa được tự ý replay request của tenant khác.

## 16. Mẫu runbook thao tác có thể điền để đưa vào vận hành

Đây là **mẫu nội dung**, không phải lệnh tự động. Khi áp dụng cho một hệ thống cụ thể, thay toàn bộ dấu giữ chỗ và dùng công cụ thao tác đã được cấp quyền.

~~~text
RUNBOOK ID       : RB-BATCH-<system>-<symptom>
SERVICE / TOPOLOGY: <service>, <multi-threaded|parallel|local-partition|remote>
VERSION VERIFIED : <release> ; <date of last staging drill>
OWNER / BACKUP   : <oncall group> / <escalation group>
TRIGGER          : <alert name + threshold + dashboard URL>
BUSINESS IMPACT  : <deadline, affected data, downstream consumers>

PRECONDITIONS
  [ ] Xác nhận environment và quyền operator.
  [ ] Xác định job name, identifying parameters,
      JobInstance/JobExecution/StepExecution ID.
  [ ] Thu thập evidence và xác định điều không được làm.

TRIAGE
  1. <JobRepository/JobExplorer status and counts>
  2. <thread/CPU/heap/JDBC pool metrics>
  3. <DB lock/query/transaction evidence>
  4. <broker queue/reply/in-flight/worker release if remote>

MITIGATION
  <least risky approved action>
  <approval required, abort condition, expected result>

RECOVERY
  <when to stop/restart/replay and which exact JobInstance>
  <checkpoint, ack, idempotency, recovery owner>

VERIFY
  [ ] <Job/Step status>
  [ ] <source/target counts, business keys, side effects>
  [ ] <queue/DB metrics below agreed threshold>
  [ ] <deadline/recovery objective>

ESCALATE / ROLLBACK
  <owner, timing, exact NO-GO conditions>

EVIDENCE / AUDIT
  <incident ticket, timestamped metrics, actions and approvals>
~~~

**Chất lượng của một runbook được đo bằng khả năng thực hiện trong sự cố**. Nếu chỗ giữ `<...>` vẫn còn ở production hoặc operator không có quyền mở dashboard, mẫu trên vẫn **chưa đạt** điều kiện "Đã có runbook vận hành".

## 17. Ví dụ minh họa: job import qua remote partitioning bị ngắt

Giả sử một job nhập **8 triệu bản ghi** được chia 32 partition, tối đa 8 worker chạy đồng thời. Manager gửi request qua broker; các worker và manager truy cập shared JobRepository. Một worker restart khi đang ghi DB; manager chờ reply và queue request có message redelivery.

### Trình tự vận hành đúng

1. Operator nhận alert **partition không tiến triển**, ghi incident ID, JobExecution và StepExecution ID, thời gian, release worker.
2. Dashboard cho thấy một worker đã restart, broker có unacked/redelivered request, JobRepository vẫn lưu StepExecution. Chưa kết luận "chưa xử lý" chỉ vì reply chưa xuất hiện.
3. Operator tạm ngừng tạo job import mới theo quyền được cấp, tránh làm đầy broker và metadata DB.
4. Nhóm kiểm tra transaction của worker cũ: có commit dữ liệu hoặc side effect bên ngoài chưa? Đối soát các khóa trong partition.
5. Nếu writer có deduplication/idempotency và trạng thái StepExecution được xác nhận, tiến hành recovery theo cơ chế đã diễn tập. Nếu không có bằng chứng về commit, **chuyển cấp data owner** trước replay.
6. Sau phục hồi, kiểm tra tổng output, số business keys duy nhất, JobExecution status, thời gian hoàn thành, backlog và số retry.
7. Mở scheduler dần, bổ sung RCA về worker restart và xem lại limit CPU/RAM, DB pool, queue capacity.

### Hành động sai

Xóa toàn bộ request queue để "dọn tồn", rồi launch lại job với tham số ngày giờ khác. Cách này có thể làm **mất request chưa xử lý** và tạo **JobInstance mới xử lý trùng** những record đã commit.

### Bằng chứng PASS

Đủ 8 triệu bản ghi theo quy tắc nghiệp vụ (trừ các bản ghi filter/skip hợp lệ), không có business key trùng ngoài dự kiến, toàn bộ partition đạt trạng thái nhất quán, broker không còn backlog bất thường và có timeline ai đã cho phép recovery.

## 18. Diễn tập (game day) để chứng minh runbook có thể dùng

Không nên chấp nhận production readiness chỉ dựa trên việc review Markdown. Hãy có **game day** trong staging với dữ liệu, quota và topology đại diện. Một số bước có thể yêu cầu phối hợp DBA/platform để tránh ảnh hưởng môi trường dùng chung.

| Kịch bản diễn tập | Tác động test | Điều kiện PASS |
|---|---|---|
| Worker crash giữa chunk/partition | Dừng một worker test đúng thời điểm có in-flight | Phát hiện, khôi phục đúng state, output không trùng/thiếu |
| Manager crash khi worker còn chạy | Dừng manager test | Phân biệt worker còn chạy, không chạy chồng lấn |
| Broker reply mất hoặc bị delay | Mô phỏng lỗi route/reply trong test | Không blind replay, có alert và recovery |
| JobRepository lock/timeout | Gây lock có giới hạn trên test DB | Xác định blocker, giảm tải, không sửa BATCH_* |
| JDBC pool cạn | Giới hạn pool hoặc tải test theo guardrail | Phân biệt pool timeout với row lock |
| API downstream trả 429/5xx | Fault injection ở mock dependency | Retry/backoff giới hạn, không retry storm |
| Queue tăng/heap pressure | Tạo burst trong ngưỡng an toàn | Backpressure hoạt động, queue drain, không OOM |
| Manager-worker version mismatch | Dùng cặp release không tương thích trong test | Deployment gate hoặc error rõ ràng; không xử lý sai dữ liệu |
| Cert/ACL sai | Thay credential test hoặc chặn quyền queue | Không vượt bảo mật, lỗi được chẩn đoán |
| Rolling deploy/rollback | Có in-flight và dữ liệu đã commit | Drain/restart/rollback theo contract, output vẫn đúng |

Mỗi lần diễn tập cần lưu **operator tham gia, runbook version, input/steps, thời gian phát hiện, thời gian hoàn tất, số lần escalation, kết quả đối soát và lỗi tài liệu**. Nếu người trực làm khác tài liệu hoặc phải hỏi tác giả cách chạy bước quan trọng, cần sửa runbook rồi diễn tập lại.

## 19. Tiêu chí GO / NO-GO và ký duyệt production

Một checklist có thể đánh giá theo ba loại:

- **PASS:** có bằng chứng cấu hình thực tế, quyền truy cập, diễn tập và kết quả đối soát.
- **FAIL:** bước sai, thiếu hoặc chưa thể thực hiện; có nguy cơ mất dữ liệu, mất quyền kiểm soát hay không phục hồi được.
- **NOT APPLICABLE:** topology không dùng thành phần đó, **có giải thích và xác nhận**, không bỏ trống.

### Checklist cuối cùng

- [ ] Có **index runbook** với link ổn định từ alert/dashboard và được operator mở thử.
- [ ] Mỗi runbook ghi rõ service, topology, release, owner, backup, lịch trực, môi trường và lần kiểm chứng.
- [ ] Đã phân loại các tình huống stuck job, rollback/retry, JobRepository lock, worker/broker outage, quá tải và deployment failure.
- [ ] Có cách lấy **JobInstance, JobExecution, StepExecution, identifying JobParameters**, JobRepository status và counts.
- [ ] Có dashboard/queries cho executor queue, CPU/heap/GC, JDBC pool, database locks, broker request/reply/unacked, partition skew.
- [ ] Hướng dẫn xác định **đã commit hay chưa** trước stop/restart/replay; có quy tắc idempotency và checkpoint.
- [ ] Có điều kiện dừng, escalation, quyền operator, approval và bước **không được làm**.
- [ ] Có cách đối soát source/target, business key, tổng giá trị và side effects, không chỉ nhìn COMPLETED.
- [ ] Có phương án mixed-version, drain, rolling deploy, rollback và bảo vệ schema/ExecutionContext.
- [ ] Có chính sách TLS/mTLS, broker ACL, quyền DB và secret management cho remote workers.
- [ ] Đã diễn tập ít nhất những failure mode quan trọng với topology đang dùng; bằng chứng được lưu và review.
- [ ] Có kế hoạch cập nhật runbook khi release đổi Step name, schema, parameter, queue, metric hoặc quyền thao tác.

### Quy tắc ra quyết định

**GO:** Các mục bắt buộc PASS hoặc được đánh dấu N/A có giải thích; operator khác tác giả có thể thực hiện các bước an toàn; recovery và reconciliation đã được diễn tập.

**NO-GO:** Không có người chịu trách nhiệm, không biết restart đúng JobInstance, không xác định được dữ liệu đã commit, không có quyền/đường dẫn truy cập, hoặc chưa có phương án đối soát và rollback cho tình huống rủi ro cao.

**Exception có phê duyệt:** Nếu doanh nghiệp quyết định chấp nhận một khoảng thiếu coverage vì lý do đặc biệt, cần ghi **risk owner, phạm vi, biện pháp thay thế, thời hạn khắc phục và người ký**. Việc ghi exception không biến một runbook chưa được diễn tập thành PASS.

## 20. Duy trì runbook sau khi đã lên production

Runbook là **tài sản vận hành sống**. Các thay đổi sau đây phải kích hoạt review, và có thể cần game day lại:

- Nâng phiên bản Spring Batch/Spring Boot, thay JobRepository schema hoặc ExecutionContext serializer.
- Đổi partitioner, reader/writer, chunk size, retry/skip policy, transaction manager.
- Thay broker, message converter, request/reply routing, consumer concurrency hoặc TLS/mTLS.
- Thay worker image, service account, network policy, certificate/secret rotation.
- Điều chỉnh core/max pool, queue capacity, JDBC pool, DB quota, autoscaling hoặc scheduler.
- Thêm JobParameters định danh, step graph mới, business side effect hoặc SLA.
- Sau incident có bước làm người trực bối rối, alert false positive hoặc recovery không đúng như mong đợi.

Nên gắn phiên bản runbook với **release manifest**, có pull request/review của service owner và operator, kiểm tra link tự động khi có thể, và rà soát định kỳ kết quả drill/incident. Với job chỉ chạy cuối tháng/quý, điều quan trọng là runbook vẫn kiểm chứng được trước kỳ chạy, không đợi đến khi xảy ra sự cố thật.

## 21. Câu hỏi tự kiểm tra

1. Vì sao việc có file `runbook.md` không đủ để đánh dấu "Đã có runbook vận hành"?
2. Nếu JobExecution vẫn STARTED nhưng worker đã crash, bạn cần bằng chứng nào trước khi restart?
3. Sự khác biệt vận hành giữa **retry item/chunk**, **restart JobInstance** và **reprocess toàn bộ** là gì?
4. Khi broker reply mất sau khi worker đã commit business DB, điều gì giúp ngăn duplicate side effects?
5. Tại sao cùng một runbook không thể giả định cho multi-threaded step và remote chunking mà không có nhánh riêng?
6. Điều kiện nào khiến việc tăng số worker từ 8 lên 16 gây tác động xấu cho JDBC pool và metadata DB?
7. Nếu operator chỉ có thể xem log mà không có quyền đọc JobExplorer hoặc liên hệ DBA, checklist nên ở trạng thái gì?
8. Những bằng chứng nào chứng minh runbook đã được diễn tập bởi người trực thực tế?

## 22. Kết luận

**"Đã có runbook vận hành" là một production gate về khả năng khôi phục, không phải một ô đánh dấu tài liệu.** Với Spring Batch scaling, runbook phải cho phép nhận diện chính xác JobInstance/JobExecution/StepExecution, phân biệt nút thắt thread/queue/CPU/JDBC/DB/broker, điều phối stop/restart/replay theo trạng thái đã commit, và **đối soát dữ liệu sau sự cố**. Nó phải có owner, quyền, dashboard, guardrail, escalation, kịch bản rollout/rollback và **bằng chứng diễn tập**. Chỉ khi một operator có thể làm theo runbook và phục hồi an toàn dưới các tình huống thực tế, tiêu chí production này mới nên được coi là **PASS**.
