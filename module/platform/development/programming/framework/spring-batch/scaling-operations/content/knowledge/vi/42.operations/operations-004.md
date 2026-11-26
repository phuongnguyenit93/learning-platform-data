# Xem worker đang lỗi khi vận hành Spring Batch mở rộng

Khi một Spring Batch job được mở rộng bằng nhiều thread, nhiều step, partition hoặc worker chạy trên các tiến trình khác nhau, thông báo “job chạy chậm” hoặc “một worker bị lỗi” chưa đủ để xác định nguyên nhân. Người vận hành cần biết **job execution nào bị ảnh hưởng, step/partition nào không tiến triển, worker đang chạy ở đâu và bằng chứng lỗi xuất hiện ở lớp nào**.

Bài này tập trung vào cách tìm worker lỗi trong hệ thống Spring Batch xử lý dữ liệu lớn: đọc trạng thái từ `JobRepository`, đối chiếu log và metric, kiểm tra tiến trình/container và hàng đợi, sau đó quyết định có thể retry/restart hay phải cô lập lỗi. Mục tiêu là **xác định đúng điểm hỏng, tránh chạy trùng dữ liệu và giữ khả năng khôi phục**.

## 1. Trước tiên, xác định “worker” trong kiến trúc hiện tại

Từ “worker” có thể chỉ một thread, một step, một partition hoặc một tiến trình độc lập. Cách xem lỗi khác nhau theo mô hình:

| Mô hình mở rộng | Đơn vị thực thi cần theo dõi | Dấu vết lỗi nên tìm |
| --- | --- | --- |
| **Multi-threaded step** | Các thread cùng xử lý một step/chunk trong một JVM | Log có tên thread, lỗi reader/processor/writer, trạng thái `StepExecution` dùng chung, tình trạng `TaskExecutor` |
| **Parallel steps** | Nhiều `StepExecution` chạy đồng thời, có thể trong cùng JVM | Trạng thái từng step, exception của step lỗi, thread pool, quan hệ luồng job |
| **Local partitioning** | Mỗi partition có `StepExecution` riêng, thường được thực thi bởi thread pool | Tên step có hậu tố partition, `StepExecutionId`, dải dữ liệu, log thread |
| **Remote partitioning** | Manager chia partition; worker JVM/container chạy worker step | Trạng thái từng partition trong `JobRepository`, log worker, trạng thái pod/process, kết nối tới middleware |
| **Remote chunking** | Manager đọc và phát chunk; worker nhận, xử lý rồi gửi kết quả | Log consumer, yêu cầu/đáp ứng qua broker, queue lag, retry/DLQ, trạng thái chunk step ở manager |

**Giới hạn quan sát quan trọng:** `JobRepository` phản ánh trạng thái batch do framework ghi nhận; nó **không phải danh sách process/thread đang sống**. Một worker bị hệ điều hành kill đột ngột có thể không kịp ghi `FAILED`. Ngược lại, một pod đang `Running` vẫn có thể không xử lý được bất kỳ dữ liệu nào.

## 2. Những dấu hiệu worker đang lỗi

Không kết luận chỉ từ một tín hiệu. Ghép các nguồn sau theo cùng khoảng thời gian:

| Nguồn | Tín hiệu cần xem | Cách diễn giải |
| --- | --- | --- |
| `JobRepository` | `JobExecution`/`StepExecution` có `FAILED`, `UNKNOWN`, `STOPPED` hoặc còn `STARTED` quá lâu | Xác định phần công việc chưa hoàn tất; `STARTED` kéo dài **chỉ là dấu hiệu nghi ngờ**, không đủ kết luận worker chết |
| Log ứng dụng | Stack trace, lỗi I/O, DB, broker, `OutOfMemoryError`, tên step/partition, mã execution | Giúp tìm nguyên nhân trực tiếp và dữ liệu gây lỗi |
| Runtime/container | Restart count tăng, `OOMKilled`, `CrashLoopBackOff`, container terminated, node mất kết nối | Chứng minh worker process gặp sự cố; đối chiếu thời điểm với batch |
| Metrics xử lý | `readCount`, `writeCount`, commit/rollback, throughput, thời gian xử lý, pool utilization | Phân biệt xử lý chậm, bị block, retry liên tục và ngừng tiến triển |
| Broker (remote) | Queue depth/lag tăng, message redelivery, DLQ, consumer count bằng 0, timeout | Tìm worker mất kết nối, quá tải hoặc bản tin lỗi lặp lại |
| Hạ tầng phụ thuộc | DB connection pool cạn, lock kéo dài, CPU/memory, lỗi mạng, giới hạn tài nguyên | Xác định nguyên nhân gốc nằm ngoài logic xử lý |

Các trạng thái cần hiểu:

- `FAILED`: framework đã đánh dấu step/job thất bại. Đọc `EXIT_MESSAGE` và log để biết nguyên nhân.
- `STARTING`/`STARTED`: đang khởi động/đang chạy theo metadata; nếu process chết bất ngờ, trạng thái có thể còn tồn tại. Phải xác nhận bằng runtime và log.
- `STOPPING`/`STOPPED`: có yêu cầu dừng hoặc đã dừng; không mặc định coi là lỗi.
- `UNKNOWN`: trạng thái không xác định; cần điều tra trước khi tiếp tục.
- `COMPLETED`: phần batch đã hoàn tất theo framework, nhưng vẫn cần kiểm tra tính đúng đắn của dữ liệu đầu ra nếu có dấu hiệu bất thường.

`BatchStatus` và `ExitStatus` khác nhau: `BatchStatus` biểu diễn vòng đời thực thi, còn `ExitStatus` có thể mang mã nghiệp vụ tùy biến. Khi đánh giá kết quả, kiểm tra cả `STATUS`, `EXIT_CODE` và `EXIT_MESSAGE`.

## 3. Quy trình xác định worker lỗi

Thực hiện lần lượt từ phạm vi rộng đến chính xác, giữ lại bằng chứng trước khi restart.

1. **Khoanh vùng một lần chạy:** lấy `jobName`, `jobExecutionId`, thời điểm bắt đầu, môi trường, job parameters phù hợp và triệu chứng đang báo động. Không trộn dữ liệu của hai lần chạy có cùng `jobName`.
2. **Tìm step/partition bất thường:** truy vấn `JobRepository`; so sánh `STATUS`, số lần commit/rollback, read/write count và thời điểm cập nhật. Với partitioning, tìm partition khác biệt hẳn các partition cùng job.
3. **Định vị đơn vị thực thi:** từ `stepExecutionId`, tên partition, request/message ID hoặc khóa tương quan trong log, truy ra thread, worker process, pod/container. Nếu không có trường tương quan, dùng thêm thời gian và phạm vi dữ liệu, ghi rõ mức độ chắc chắn.
4. **Đối chiếu runtime:** kiểm tra pod/process có bị restart, kill, mất mạng hoặc còn sống nhưng chờ DB/broker. Với remote chunking, xem consumer và queue; với local multi-thread, xem thread pool/stack trace.
5. **Xác định nguyên nhân và ảnh hưởng:** dữ liệu đầu vào lỗi, bug xử lý, contention, thiếu connection, cạn memory, broker timeout hay sự cố triển khai? Xác định các chunk đã commit, chunk đang xử lý và nguy cơ tạo tác dụng phụ trùng lặp.
6. **Chọn hành động phục hồi có kiểm soát:** xử lý nguyên nhân, bảo đảm không còn worker cũ ghi dữ liệu, sau đó mới retry/restart theo chính sách job. Quan sát các chỉ số tiến triển sau phục hồi.

Một thông báo sự cố có ích thường ghi: `jobExecutionId`, `stepExecutionId`, tên partition, pod/thread tương ứng, thời điểm cuối có tiến triển, exception gốc, số bản ghi/chunk ảnh hưởng và hành động đang thực hiện.

## 4. Xem trạng thái từ JobRepository

Spring Batch sử dụng các bảng metadata như `BATCH_JOB_INSTANCE`, `BATCH_JOB_EXECUTION` và `BATCH_STEP_EXECUTION`. Với ứng dụng dùng `JobRepository` chuẩn trên cơ sở dữ liệu quan hệ, có thể dùng truy vấn chỉ đọc sau.

### 4.1. Xác định lần chạy cụ thể

```sql
SELECT
    ji.JOB_NAME,
    je.JOB_EXECUTION_ID,
    je.STATUS,
    je.EXIT_CODE,
    je.START_TIME,
    je.END_TIME,
    je.LAST_UPDATED
FROM BATCH_JOB_EXECUTION je
JOIN BATCH_JOB_INSTANCE ji
    ON ji.JOB_INSTANCE_ID = je.JOB_INSTANCE_ID
WHERE ji.JOB_NAME = ?
ORDER BY je.JOB_EXECUTION_ID DESC;
```

Dấu `?` là tham số cho prepared statement; dùng tên bảng/schema/prefix thực tế của môi trường. Chọn đúng `JOB_EXECUTION_ID` trước khi đào sâu.

### 4.2. Tìm step hoặc partition có vấn đề

```sql
SELECT
    STEP_EXECUTION_ID,
    JOB_EXECUTION_ID,
    STEP_NAME,
    STATUS,
    EXIT_CODE,
    READ_COUNT,
    WRITE_COUNT,
    COMMIT_COUNT,
    ROLLBACK_COUNT,
    READ_SKIP_COUNT,
    PROCESS_SKIP_COUNT,
    WRITE_SKIP_COUNT,
    START_TIME,
    END_TIME,
    LAST_UPDATED,
    EXIT_MESSAGE
FROM BATCH_STEP_EXECUTION
WHERE JOB_EXECUTION_ID = ?
ORDER BY STEP_EXECUTION_ID;
```

Chẳng hạn, kết quả dưới đây là **dữ liệu minh họa** cho một remote partitioning job:

| `STEP_NAME` | `STATUS` | `READ_COUNT` | `WRITE_COUNT` | `ROLLBACK_COUNT` | Nhận xét |
| --- | --- | ---: | ---: | ---: | --- |
| `workerStep:partition0` | `COMPLETED` | 10.000 | 10.000 | 0 | Đã xong |
| `workerStep:partition1` | `COMPLETED` | 10.000 | 10.000 | 0 | Đã xong |
| `workerStep:partition2` | `FAILED` | 4.200 | 4.000 | 6 | Ưu tiên tra lỗi |
| `workerStep:partition3` | `STARTED` | 3.000 | 3.000 | 0 | Cần xác minh còn xử lý hay bị kẹt |

Tên hậu tố partition phụ thuộc cách đặt tên của `Partitioner`/`PartitionHandler`; không nên viết công cụ giám sát phụ thuộc cứng vào `partition0`. Các số đếm thể hiện tiến độ framework ghi nhận, **không thay thế** kiểm tra dữ liệu đích hoặc giao dịch bên ngoài.

**Lưu ý về thời gian:** `LAST_UPDATED` là thời điểm metadata được cập nhật, không phải heartbeat liên tục của worker. Không gắn nhãn worker “đã chết” chỉ vì trường này đứng yên. Hãy kiểm tra cùng log, throughput, trạng thái thread/process và một heartbeat riêng nếu hệ thống đã triển khai.

**Phân biệt theo mô hình:**

- **Local/remote partitioning:** các partition thường có `StepExecution` riêng, nên bảng step giúp chỉ ra partition bị lỗi.
- **Multi-threaded step:** nhiều thread có thể chia sẻ một `StepExecution`; bản ghi `FAILED` không tự chỉ ra thread nào phát sinh lỗi. Phải tìm trong log/thread dump.
- **Remote chunking:** không giả định mỗi consumer hoặc mỗi message đều tạo một `StepExecution` riêng. Trạng thái step ở manager cần được ghép với broker và log worker.

Có thể dùng `JobExplorer`/`JobOperator` qua ứng dụng để quan sát metadata thay cho SQL trực tiếp. Chỉ đọc khi chẩn đoán; **không tự sửa trạng thái bằng câu lệnh `UPDATE`** để “mở khóa” job.

## 5. Xem worker chạy trên Kubernetes

Với remote partitioning/remote chunking triển khai bằng container, một quy trình phổ biến là:

```bash
# Tìm worker pods theo label đã cấu hình trong hệ thống.
kubectl get pods -n data-jobs -l app=batch-worker -o wide

# Đọc điều kiện container, restart count, lý do terminated và các event.
kubectl describe pod -n data-jobs <worker-pod>

# Tìm lỗi gần đây, dùng timestamps để đối chiếu JobRepository.
kubectl logs -n data-jobs <worker-pod> --since=30m --timestamps

# Nếu container vừa restart, xem log instance trước (nếu còn).
kubectl logs -n data-jobs <worker-pod> --previous --timestamps

# Đọc các event và tài nguyên hiện tại nếu cluster hỗ trợ metrics-server.
kubectl get events -n data-jobs --sort-by=.lastTimestamp
kubectl top pod -n data-jobs <worker-pod>
```

`data-jobs`, `app=batch-worker` và `<worker-pod>` là ví dụ; thay bằng namespace, label, pod name thật. Nếu pod có nhiều container, chỉ định `-c <container-name>` cho `kubectl logs`.

Cách đọc một số tín hiệu:

- `OOMKilled`: tiến trình vượt giới hạn memory. Đối chiếu memory graph, chunk size, số partition đồng thời, số object giữ trong RAM, GC và giới hạn pod.
- `CrashLoopBackOff`: container khởi động rồi thoát lặp lại. Xem `--previous`, entrypoint, cấu hình, dependency và lỗi khi boot; tên trạng thái này chưa nói rõ nguyên nhân.
- `Running` nhưng dữ liệu không tiến triển: xem CPU, pool/connection, lock, thread dump, queue consumption, các lệnh gọi mạng đang chờ và logic retry.
- Pod biến mất hoặc node mất kết nối: đối chiếu sự kiện cluster, scheduler và thời điểm broker redelivery/metadata ngừng cập nhật.

Nếu worker chạy trên VM, hệ thống process hoặc máy chủ ứng dụng thay cho Kubernetes, áp dụng cùng nguyên tắc: tìm instance, tiến trình, exit code, log và resource metric tương ứng.

## 6. Ghép log và metric để tìm đúng nguyên nhân

### 6.1. Thiết kế log để truy được worker

Một log có ích nên chứa tối thiểu:

```text
timestamp=2026-11-26T03:40:12Z
level=ERROR
jobName=importOrders
jobExecutionId=421
stepName=workerStep:partition2
stepExecutionId=890
workerId=batch-worker-7
chunkId=partition2-18
errorType=SQLTransientConnectionException
message="Timeout acquiring database connection"
```

Đây là mẫu log minh họa, không phải định dạng tự sinh sẵn của Spring Batch. `workerId` có thể là pod name/instance ID, còn `chunkId` phải do ứng dụng gắn nếu cần. Với remote messaging, bổ sung request ID, message ID, delivery attempt và partition key. Không log credential, nội dung nhạy cảm của record hoặc toàn bộ job parameters nếu chúng có thể chứa bí mật.

Ở multi-threaded step, thêm thread name và bảo đảm context được truyền đúng qua thread pool; `MDC` gắn trên thread khởi chạy **không tự động truyền** sang thread xử lý. Với remote worker, context cũng phải được đưa qua message headers/payload phù hợp rồi dựng lại tại consumer.

### 6.2. Đọc metric theo tiến triển thực tế

Theo dõi các nhóm metric (tên cụ thể phụ thuộc cấu hình Micrometer, Spring Boot Actuator, Spring Batch và hệ thống giám sát):

- Tỷ lệ job/step thành công, thất bại, thời lượng và số lần retry/rollback.
- Throughput đọc/ghi theo job/step/partition; số chunk commit theo thời gian, không chỉ tổng số đếm tại một thời điểm.
- Số worker sống và worker đang xử lý, thread pool active/queue/rejected tasks.
- CPU, heap, GC pause, memory limit, DB pool active/pending connections, query latency.
- Với broker: consumer count, số message tồn đọng, tuổi message cũ nhất, tỷ lệ redelivery/DLQ và độ trễ phản hồi.

Ví dụ: nếu backlog tăng trong khi consumer count bằng 0 và không có log worker nhận message, hướng điều tra đầu tiên là worker deployment, kết nối hoặc subscription. Nếu consumer vẫn nhận message nhưng `ROLLBACK_COUNT` tăng liên tục với cùng một business key, cần kiểm tra dữ liệu lỗi và chính sách retry.

Không đặt cảnh báo cứng như “5 phút không commit = worker chết” cho mọi job: partition lớn, một giao dịch dài hay bước gọi API chậm có thể làm commit thưa. Ngưỡng nên dựa vào thời gian xử lý bình thường, SLA, kích thước chunk và loại step. Nếu cần kiểm tra liveness độc lập với commit, xuất heartbeat hoặc metric tiến độ riêng.

## 7. Tình huống minh họa: một partition lỗi giữa chừng

Giả sử job import đơn hàng chia thành 16 partition; manager báo 14 partition `COMPLETED`, một partition `FAILED`, một partition còn `STARTED`. Đội vận hành thấy job chưa kết thúc.

**Bước 1 — Xác nhận metadata:** truy vấn bằng `JOB_EXECUTION_ID`; partition `workerStep:partition2` có `STEP_EXECUTION_ID=890`, `EXIT_CODE=FAILED`, `ROLLBACK_COUNT` tăng. Không suy ra partition `STARTED` còn lại đã chết.

**Bước 2 — Tìm log tương quan:** log worker `batch-worker-7` có `stepExecutionId=890` và exception timeout lấy connection DB. Kiểm tra cùng lúc: số connection active đạt trần pool, số partition chạy song song và truy vấn chậm.

**Bước 3 — Kiểm tra tác động:** đối chiếu bản ghi đã commit với output; xác định chunk cuối có thể bị chạy lại hay không. Nếu writer gọi hệ thống bên ngoài không tham gia transaction, cần kiểm tra idempotency theo khóa nghiệp vụ.

**Bước 4 — Khắc phục:** giảm mức đồng thời hoặc điều chỉnh pool và timeout dựa trên năng lực DB; theo dõi worker/partition đang chạy để tránh hai lần xử lý cùng dải dữ liệu. Sau khi nguyên nhân đã được xử lý, thực hiện restart theo cấu hình và quy trình của job, rồi kiểm tra không còn rollback lặp lại.

Nếu log thay vào đó có `NullPointerException` luôn xảy ra trên cùng bản ghi, tăng số worker hay kích thước pool sẽ không giải quyết lỗi. Cần sửa logic hoặc xử lý dữ liệu gây lỗi, rồi đánh giá chính sách retry/skip theo yêu cầu nghiệp vụ.

## 8. Các bẫy thường gặp khi kết luận worker bị lỗi

| Hiện tượng | Kết luận vội cần tránh | Kiểm tra tiếp |
| --- | --- | --- |
| `StepExecution` còn `STARTED` lâu | “Worker chắc chắn đã chết” | Process/thread còn sống? Có chunk dài, lock DB, chờ network hay retry? |
| Pod báo `Running` | “Worker vẫn đang xử lý tốt” | Log nhận việc, metric throughput, pool, thread dump, broker |
| `FAILED` ở manager | “Chính manager có bug” | Partition worker lỗi, timeout giao tiếp, consumer biến mất, exception nguồn |
| `readCount` tăng, `writeCount` thấp | “Writer bị lỗi” | Có filter hợp lệ, processor bỏ qua, skip, chunk chưa commit hay không? |
| Cùng message được xử lý nhiều lần | “Có hai worker cố ý xử lý trùng” | Broker redelivery sau timeout/crash, ack, retry, khả năng idempotent |
| Thêm worker nhưng throughput giảm | “Cần scale tiếp” | DB pool, lock, partition skew, I/O, CPU/GC, bão retry |

**Lỗi của worker không đồng nghĩa thất bại cuối cùng của job ngay lập tức.** Tùy cấu hình retry, timeout, `PartitionHandler`, broker và chính sách stop, manager có thể còn đợi hoặc nhận phản hồi trễ. Lấy chính xác execution ID và trạng thái thực tế trước khi xử lý.

## 9. Phục hồi an toàn sau khi xác định lỗi

Điều kiện cần trước mọi restart là hiểu job đã commit gì và có còn worker cũ đang thực thi không.

1. **Lưu bằng chứng:** execution IDs, exception đầu tiên, log của container trước khi restart, thời điểm bắt đầu/ngừng tiến triển, số liệu commit và rollback.
2. **Ngăn xử lý đồng thời ngoài ý muốn:** xác nhận worker lỗi đã ngừng hoặc được cách ly; đặc biệt quan trọng với partition remote và message có thể được gửi lại.
3. **Sửa nguyên nhân gốc:** dữ liệu sai, lỗi ứng dụng, cấu hình timeout/pool, giới hạn memory, kết nối broker hoặc dịch vụ phụ thuộc.
4. **Đánh giá khả năng phát lại:** chunk đã commit sẽ được cơ chế restart xử lý theo trạng thái/checkpoint; các thao tác gửi email, gọi API, ghi hệ thống khác có thể không rollback cùng transaction. Sử dụng khóa duy nhất, upsert/idempotency key hoặc cơ chế chống trùng thích hợp.
5. **Restart bằng API/cơ chế vận hành của Spring Batch:** Spring Batch thường tạo `JobExecution` mới cho cùng `JobInstance` khi restart một job thất bại và đủ điều kiện restart. Tránh khởi chạy một job instance mới vô tình bằng cách thay đổi identifying parameters khi mục tiêu chỉ là tiếp tục công việc cũ.
6. **Xác nhận kết quả:** step/partition cần chạy lại tiến triển, job kết thúc ở trạng thái mong đợi, số bản ghi và tính nhất quán đầu ra đạt tiêu chí, không xuất hiện vòng retry/rollback hay DLQ tăng.

Với trạng thái `STARTED` còn sót lại sau crash, Spring Batch có thể từ chối restart vì hệ thống vẫn xem execution đang chạy. Hãy xác minh toàn bộ worker liên quan đã dừng và dùng quy trình phục hồi được hệ thống hỗ trợ; **không cập nhật thủ công `BATCH_*_EXECUTION.STATUS`** nếu chưa có quy trình kiểm soát metadata riêng.

Khi lỗi đến từ dữ liệu có thể skip, chỉ áp dụng skip/retry nếu quy tắc nghiệp vụ cho phép và có giới hạn rõ ràng. Khi dữ liệu tiền tệ, đơn hàng hoặc đối soát bị tác động, ưu tiên tính đúng đắn và khả năng kiểm toán hơn việc đưa job về `COMPLETED` bằng mọi giá.

## 10. Checklist trực vận hành

Trước khi kết luận và bàn giao sự cố, người trực có thể điền bảng ngắn sau:

| Câu hỏi | Bằng chứng cần có |
| --- | --- |
| Lần chạy nào bị ảnh hưởng? | `jobName`, `jobExecutionId`, thời gian, môi trường |
| Lỗi nằm ở đâu? | `stepExecutionId`, `stepName`, partition/worker ID; mô hình scale |
| Trạng thái batch là gì? | `STATUS`, `EXIT_CODE`, `EXIT_MESSAGE`, count và thời gian |
| Worker runtime có vấn đề gì? | Pod/process state, restart/exit reason, log tương quan |
| Công việc còn tiến triển không? | Throughput, commit, queue age/lag, metric heartbeat (nếu có) |
| Nguyên nhân đã được chứng minh chưa? | Exception gốc cùng metric/event liên quan; tránh chỉ suy đoán |
| Có nguy cơ chạy trùng/mất dữ liệu không? | Chunk đã commit, side effect ngoài transaction, key chống trùng |
| Phục hồi đã thành công chưa? | Job/step mới kết thúc đúng, số liệu output đối chiếu, alert trở lại bình thường |

**Thực hành tự kiểm tra:** nếu `workerStep:partition8` vẫn `STARTED` nhưng `LAST_UPDATED` không đổi 20 phút, trong khi pod đang `Running`, bạn cần thêm bằng chứng nào? Câu trả lời tối thiểu gồm log gần nhất của partition, thread state hoặc trạng thái consumer, độ dài chunk thông thường, throughput thực tế, DB/broker latency và thông tin worker có đang retry. Chỉ sau khi ghép các bằng chứng này mới phân biệt được worker chết, bị kẹt, chạy chậm hay đang thực hiện một chunk hợp lệ.

Kỹ năng cốt lõi của việc **xem worker đang lỗi** là liên kết `JobRepository → step/partition → worker runtime → log/metric → dữ liệu đã commit`. Chuỗi bằng chứng đó cho phép xử lý đúng điểm nghẽn trong Spring Batch mở rộng mà vẫn bảo toàn khả năng restart và tính nhất quán dữ liệu.

