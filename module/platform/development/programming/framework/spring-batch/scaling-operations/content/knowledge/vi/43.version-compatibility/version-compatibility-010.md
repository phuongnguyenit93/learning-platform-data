# Chiến lược rollback phiên bản trong Spring Batch

> **Chương:** Tương thích phiên bản  
> **Phạm vi module:** `SPRING_BATCH_SCALING_OPERATIONS` — mở rộng Spring Batch cho workload dữ liệu lớn với multi-threaded step, parallel steps, partitioning và xử lý phân tán; đo nút thắt, bảo đảm thread safety, retry/restart và vận hành job trên tài nguyên thực tế.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **rollback phiên bản ứng dụng**, **restart job**, **khôi phục dữ liệu** và **compensation** khi một release Spring Batch gặp sự cố.
2. Đánh giá tương thích hai chiều của `JobRepository`, `ExecutionContext`, schema nghiệp vụ, giao thức message và các side effect ngoài transaction.
3. Lựa chọn chiến lược rollback cho scheduled job, long-running job, multi-threaded step, parallel steps, remote chunking và remote partitioning.
4. Thiết kế quy trình **stop dispatch → drain → chuyển route/phiên bản → restart có kiểm soát → đối soát**, có điều kiện go/no-go và phương án khi không thể quay về bản cũ.
5. Kiểm thử rollback trên môi trường gần production, bao gồm worker chết sau commit, job restart từ checkpoint cũ và dữ liệu do phiên bản mới tạo ra.

## 1. Rollback phiên bản giải quyết vấn đề gì?

Giả sử đêm nay nhóm triển khai `settlement-batch:2.8.0` thay cho `2.7.3`. Bản mới có thuật toán partition nhanh hơn và một thay đổi schema. Sau 20 phút, metric cho thấy retry tăng mạnh, một số partition đã ghi dữ liệu nhưng manager chưa nhận đủ reply. Nếu thay image về `2.7.3` ngay, hệ thống có thể tiếp tục gặp lỗi vì:

- Job đang chạy giữ state trong `ExecutionContext` theo định dạng của phiên bản mới.
- `JobRepository` đã được cập nhật bởi bản mới hoặc vừa qua một đợt migration không tương thích.
- Worker mới đã commit kết quả nghiệp vụ; thay image không tự hoàn nguyên những bản ghi này.
- Broker còn request/reply được serialize theo hợp đồng mới, có thể bị bản cũ tiêu thụ.
- Một số worker còn transaction đang chạy; dừng đột ngột có thể gây redelivery.

Vì vậy, **rollback trong batch là khôi phục một trạng thái xử lý an toàn có thể kiểm chứng**, không đơn thuần là đưa container image cũ trở lại.

### 1.1. Bốn thao tác dễ bị nhầm lẫn

| Thao tác | Mục đích | Việc nó không tự giải quyết |
|---|---|---|
| **Application rollback** | Chuyển code, image, cấu hình hoặc route về release trước | Không hoàn tác business row hoặc message đã phát |
| **Spring Batch restart** | Tiếp tục một `JobInstance` thất bại/đã dừng bằng `JobExecution` mới từ checkpoint hợp lệ | Không bảo đảm code cũ đọc được state mới |
| **Data restore / repair** | Khôi phục, sửa hoặc replay dữ liệu nghiệp vụ theo bằng chứng | Không tự sửa tương thích runtime/message |
| **Compensation** | Phát hành thao tác nghiệp vụ bù trừ cho side effect đã xảy ra | Không tương đương transaction rollback kỹ thuật |

Ví dụ: worker gọi API thanh toán, phía nhận đã thực hiện lệnh nhưng response mất. Rollback image có thể làm việc xử lý lại trên phiên bản cũ; chỉ **idempotency key và đối soát phía nhận** mới giúp tránh tạo giao dịch thứ hai. Trường hợp phải đảo giao dịch, cần một quy trình compensation được nghiệp vụ cho phép.

### 1.2. Trạng thái Spring Batch khác trạng thái release

`BatchStatus.COMPLETED`, `FAILED`, `STOPPED` và các trạng thái thực thi khác thuộc một `JobExecution`/`StepExecution`. “Blue”, “green”, “canary”, “rollback” là nhãn **phiên bản triển khai** do hệ thống vận hành quản lý. Một bản blue có thể còn job `STARTED`, còn green đã nhận những job mới.

Một `JobInstance` được xác định bởi tên job và bộ `JobParameters` có thuộc tính *identifying*. Khi restart, Spring Batch có thể tạo một `JobExecution` mới cho cùng `JobInstance`. Tự thêm tham số kiểu `run.id` để “chạy lại từ đầu” có thể tạo **instance khác**, dẫn đến xử lý dữ liệu trùng nếu không có khóa idempotency.

## 2. Bản đồ những thứ phải tương thích khi rollback

Quyết định quay về bản trước cần đánh giá theo **phiên bản cũ đọc/ghi được trạng thái đã được bản mới để lại hay không**.

| Ranh giới | Câu hỏi rollback phải trả lời | Rủi ro khi không tương thích |
|---|---|---|
| **Binary / runtime** | Image cũ có chạy với Java, Spring Boot, driver và cấu hình hiện tại? | Không khởi động được hoặc lỗi runtime |
| **JobRepository** | Schema metadata hiện tại có được bản cũ hỗ trợ và đọc/ghi đúng? | Không truy vấn được job, mất khả năng restart |
| **`ExecutionContext`** | Serializer và các field checkpoint có được code cũ đọc/hiểu? | Reader restart sai vị trí, `ClassNotFoundException`/deserialize lỗi |
| **Job/step identity** | Tên job, step, partition và identifying parameters còn ổn định? | Step bị nhận thành step mới hoặc không tìm được state cũ |
| **Business schema** | Bản cũ có đọc/ghi được bảng sau migration? | Cột bị đổi tên/xóa, dữ liệu mới ngoài phạm vi hiểu của bản cũ |
| **Business semantics** | Kết quả do bản mới ghi còn hợp lệ với quy tắc bản cũ? | Ghi đè, bỏ sót, tính toán theo hai phiên bản khác nhau |
| **Message request/reply** | Bản cũ có deserialize, xử lý và correlate message còn trong queue? | Poison message, retry vô hạn, mất phản hồi |
| **Broker topology** | Queue, topic, consumer group, routing key còn tương thích? | Nhận nhầm việc hoặc mất đường trả lời |
| **External systems** | API, file format, object store, downstream contract có còn tương thích? | Không thể dùng bản cũ để hoàn thành luồng xử lý |
| **Idempotency** | Cùng business operation key có dùng được xuyên release? | Redelivery/restart gây hiệu ứng trùng |

**Rollback readiness** phải là một thuộc tính đã được kiểm thử cho **cặp release cụ thể**. “Version trước đã từng chạy ổn định” không chứng minh rằng version trước tương thích với schema, message hoặc dữ liệu do version mới tạo.

### 2.1. Ma trận quyết định

| Điều kiện quan sát | Hướng xử lý ưu tiên |
|---|---|
| Green chưa nhận production work, schema/config vẫn tương thích | Chuyển routing/scheduler về blue rồi xác minh |
| Green đã nhận work nhưng chưa commit side effect, có thể drain | Ngừng dispatch, drain, rollback app và restart phần việc hợp lệ |
| Green đã commit nhưng output idempotent và blue hiểu state/data | Quay route việc mới về blue; với execution cũ, chọn phiên bản restart đã kiểm thử |
| Green đã ghi dữ liệu hoặc metadata **không tương thích** với blue | Dừng cutover, cô lập phạm vi ảnh hưởng; ưu tiên fix-forward/khôi phục có kế hoạch |
| Hệ thống ngoài đã thực hiện side effect không đảo ngược tự động | Đối soát external receipt và chạy compensation nghiệp vụ khi được phê duyệt |
| Không xác định được in-flight state hoặc kết quả nghiệp vụ | Giữ trạng thái `UNKNOWN/INCONCLUSIVE`, chặn xử lý tiếp và điều tra trước khi replay |

Không được dùng “rollback thành công” làm nhãn cho một tình huống chỉ có image chạy lại nhưng dữ liệu chưa được đối soát.

## 3. Thiết kế phiên bản để còn đường rollback

Rollback hiệu quả nhất khi **được thiết kế trước khi release mới ghi dữ liệu**.

### 3.1. Giữ artifact và cấu hình có thể tái tạo

Lưu chính xác image digest/build, dependency lock, biến cấu hình, cấu trúc queue, database migration version và feature flags của bản đang chạy. Nếu dùng image tag có thể bị ghi đè, rollback về một tag không bảo đảm quay về đúng mã nguồn cũ. Ưu tiên **immutable image digest** cùng manifest cấu hình đã kiểm thử.

Không mang theo mọi cấu hình hiện tại khi lùi image: ví dụ release mới có serializer mặc định hoặc batch size khác, bản cũ có thể không hiểu. “Release” nên bao gồm **artifact + config + migration compatibility + messaging contract**, không chỉ image.

### 3.2. Database migration theo expand → migrate → contract

Giả sử bản mới cần một trường `risk_category` trong bảng kết quả. Chiến lược cho phép rollback:

1. **Expand:** thêm cột mới dưới dạng nullable hoặc có default phù hợp; giữ cột cũ và kiểu dữ liệu mà cả hai version đọc được.
2. **Migrate:** backfill và/hoặc dual read/write theo kế hoạch, bảo đảm bản cũ và mới cùng hoạt động được trong cửa sổ rollback.
3. **Switch:** đưa bản mới chạy theo feature flag hoặc cohort đã được kiểm thử.
4. **Contract:** chỉ xóa cột cũ, đổi tên bắt buộc hoặc áp constraint không tương thích **sau khi hết nhu cầu rollback** và đã xác nhận các execution cũ không còn phải restart.

Ví dụ migration PostgreSQL mở rộng:

~~~sql
ALTER TABLE settlement_result
    ADD COLUMN risk_category VARCHAR(32);

-- Khi cần cập nhật dữ liệu cũ, backfill theo batch nhỏ có kiểm soát.
-- Chưa DROP hoặc RENAME các cột đang được release cũ sử dụng.
~~~

Việc thêm cột nullable thường dễ tương thích hơn xóa hoặc đổi tên cột, nhưng vẫn phải kiểm tra kiểu câu lệnh SQL/ORM, constraint, trigger và performance trên schema thực tế. Một migration “có lệnh DOWN” không có nghĩa rollback an toàn: chạy DOWN có thể **làm mất dữ liệu** mà version mới đã ghi hoặc phá những execution còn hoạt động.

### 3.3. JobRepository không phải bảng nghiệp vụ để sửa bằng tay

Các bảng metadata của Spring Batch lưu định danh và trạng thái job/step, execution parameters và context phục vụ restart. Khi nâng phiên bản Spring Batch, **schema, serializer hoặc quy ước metadata có thể thay đổi**. Cần tra migration guide và chạy thử trên bản sao metadata hợp lệ của chính hệ thống trước khi triển khai.

Không tự sửa trực tiếp `BATCH_JOB_EXECUTION.STATUS` thành `FAILED`/`COMPLETED` để “mở khóa” rollback. Trạng thái này liên quan tới step execution, checkpoint và transaction; sửa một cột có thể che giấu việc vẫn còn worker chạy và gây xử lý trùng. Dùng API/đường vận hành hợp lệ, đối chiếu thực tế rồi xử lý các execution treo theo runbook.

Nếu migration metadata không tương thích ngược, **không chạy song song hai phiên bản trên cùng JobRepository** trừ khi đã có bằng chứng tương thích và chính sách hỗ trợ. Có thể cần giai đoạn nâng cấp một chiều có downtime được kiểm soát, backup/restore theo kế hoạch hoặc giữ toàn bộ execution cũ ở phiên bản cũ đến khi hoàn tất.

### 3.4. Bảo vệ `ExecutionContext` và checkpoint

Một bản mới có thể đổi field lưu trong `ExecutionContext` từ `lastProcessedId` thành một object Java mới. Nếu bản cũ phải restart từ checkpoint đó, nó có thể không deserialize được hoặc tiếp tục sai con trỏ.

Khuyến nghị:

- Lưu checkpoint bằng **giá trị nhỏ, ổn định, có version schema** như cursor, sort key, partition range và source snapshot ID.
- Tránh lưu entity ORM, object không ổn định theo class name hoặc dữ liệu cá nhân thô trong `ExecutionContext`.
- Giữ tương thích đọc ngược trong cửa sổ rollback hoặc **pin execution đang chạy** vào release ban đầu.
- Dùng khóa sắp xếp ổn định/duy nhất cho paging reader; bảo đảm dữ liệu nguồn giữ cùng snapshot khi restart.
- Test restart thật qua các phiên bản, không chỉ test deserialize một object riêng lẻ.

Ví dụ context logic tự thiết kế:

~~~json
{
  "checkpointSchema": 1,
  "sourceSnapshotId": "snapshot-2026-11-26-A",
  "partitionStartInclusive": 1000000,
  "partitionEndExclusive": 1250000,
  "lastCommittedBusinessKey": 1174231
}
~~~

Đây là **hợp đồng checkpoint minh họa**, không phải định dạng mặc định của Spring Batch. Muốn rollback an toàn, bản cũ phải biết đọc/hiểu các key được sử dụng và cách ranh giới transaction liên hệ tới `lastCommittedBusinessKey`.

### 3.5. Message contract phải được version hóa

Trong remote chunking, manager có thể gửi `ChunkRequest` chứa danh sách item; worker xử lý/ghi và phản hồi. Trong remote partitioning, manager gửi work cho partition và worker cập nhật đúng `StepExecution`. Khi đổi serializer, DTO, tên step hoặc reply routing, request còn trong broker có thể không tương thích với bản cũ.

Ví dụ envelope minh họa do **ứng dụng định nghĩa**, không phải wire format bắt buộc của Spring Batch:

~~~json
{
  "protocolVersion": 2,
  "releaseRoute": "green",
  "jobExecutionId": 9132,
  "stepExecutionId": 29324,
  "partitionId": "range-017",
  "correlationId": "exec-9132-range-017-attempt-1",
  "operationKey": "settlement:2026-11-26:range-017"
}
~~~

Khi rollback, cần biết message nào **đã được cấp cho green**, message nào chưa nhận, đang prefetch, đã commit nhưng chưa ack hoặc còn trong DLQ. `releaseRoute` giúp vận hành định tuyến, nhưng **không tự chống replay**; khóa idempotency phải mang ý nghĩa nghiệp vụ ổn định qua các version.

## 4. Chọn ranh giới rollback theo mô hình scaling

Chiến lược thay đổi tùy nơi đặt state và cách công việc được phân phối.

| Mô hình | Ranh giới chuyển phiên bản ưu tiên | Điều phải kiểm tra trước rollback |
|---|---|---|
| **Scheduled single-process job** | Giữa hai lần khởi chạy job | Scheduler ownership, JobInstance mới, output của kỳ vừa chạy |
| **Multi-threaded step** | Khi mọi thread hoàn tất chunk/step, hoặc sau stop hợp lệ | Thread safety, checkpoint và side effect ngoài transaction |
| **Parallel steps** | Khi các nhánh đang chạy đạt trạng thái cuối | Phụ thuộc giữa nhánh, output trung gian, step statuses |
| **Local partitioning** | Giữa các JobExecution hoặc sau drain partition | Coverage/overlap partition, restart của partition |
| **Remote chunking** | Sau khi manager ngừng dispatch, drain request/reply còn treo | Queue unacked, worker commits, reply correlation, serializer |
| **Remote partitioning** | Theo cohort/JobExecution với version affinity | Partition ownership, StepExecution metadata, worker protocol |

### 4.1. Ranh giới ít rủi ro nhất: một release cho một JobExecution

Nếu có thể, cho tất cả worker của một `JobExecution` sử dụng cùng bộ logic/contract đã chốt; chỉ chuyển **JobExecution kế tiếp** sang release mới. Việc trộn green và blue trong cùng một execution chỉ nên thực hiện khi hai phiên bản đã được kiểm chứng tương thích hoàn toàn về dữ liệu, serializer, metadata và kết quả.

Nếu một execution dài 6 giờ vẫn dùng blue trong lúc green nhận những execution độc lập khác, rollback green có thể chỉ là **ngừng nhận job mới ở green** và giữ blue xử lý execution đã sở hữu. Cần có cơ chế lưu `releaseAffinity` theo execution trong một control store bền vững do ứng dụng quản lý.

### 4.2. Blue-green và route riêng

~~~mermaid
flowchart LR
    SCH[Scheduler / launcher] --> M[Manager]
    M --> AFF[(Execution-to-release affinity)]
    AFF --> ROUTE{Route công việc}
    ROUTE -->|blue| QB[(work.blue)]
    ROUTE -->|green| QG[(work.green)]
    QB --> WB[Blue workers]
    QG --> WG[Green workers]
    WB --> DB[(Business database)]
    WG --> DB
    WB --> JR[(JobRepository)]
    WG --> JR
    WB -. reply .-> M
    WG -. reply .-> M
~~~

Sơ đồ chỉ là một kiến trúc khả thi; `work.blue` và `work.green` không phải queue mặc định của Spring Batch. Phải tự hiện thực route/affinity phù hợp với broker và cấu hình Spring Integration. **Đổi Kubernetes Service selector không tự dừng Kafka/RabbitMQ consumer** đang kéo message từ broker.

Với **queue chung**, hai version có thể cùng nhận message nếu consumer chạy đồng thời. Khi message contract không tương thích, phải ngừng cấp mới cho bản cần rút, drain in-flight, rồi chuyển quyền tiêu thụ một cách điều phối. Không dùng thao tác thay replica để giả định broker đã ngừng giao message.

### 4.3. Version affinity cho remote partitioning

Giả sử một `JobExecution` có 64 partition, bản green đang xử lý 20 partition. Nếu rollback route toàn bộ về blue, những partition đã gán cho green có thể bị blue restart trong một môi trường chưa tương thích. Giải pháp an toàn thường là:

1. Ghi lại partition nào đã bắt đầu, hoàn tất, thất bại; và release sở hữu.
2. Ngừng phân phối partition mới sang green.
3. Để partition đã commit được công nhận chính xác; chờ partition chưa xong drain hoặc đánh dấu theo quy trình lỗi hợp lệ.
4. Giữ bản green đủ lâu để hoàn tất/restart những partition cần cùng semantics, hoặc chỉ chuyển chúng về blue sau khi đã kiểm thử restart cross-version.
5. Đối soát đầu vào/đầu ra từng partition và toàn bộ job theo business key.

Mục tiêu là không có partition bị chạy hai lần với kết quả mâu thuẫn hoặc bị bỏ sót vì đổi manager/worker giữa chừng.

## 5. Thiết lập điều kiện go/no-go trước khi release

Rollback cần các tiêu chí có thể đo, xác nhận được trong lúc sự cố. Thiết kế trước khi triển khai:

| Nhóm | Điều kiện tối thiểu | Bằng chứng |
|---|---|---|
| Artifact | Có image/config của bản ổn định trước, có thể khởi động | Immutable digest, smoke test |
| Metadata | Bản cũ đọc được `JobRepository` sau migration hoặc execution đã cách ly | Thử restart trên bản sao metadata |
| Data schema | Bản cũ đọc/ghi được dữ liệu do bản mới đã ghi | Migration compatibility test |
| Messaging | Request/reply còn trong queue có route hoặc decoder tương thích | Contract + retry/DLQ test |
| In-flight | Có phép đo và thao tác ngừng nhận việc mới, drain | Dashboard inflight, unacked, reply lag |
| Idempotency | Redelivery/restart không sinh business side effect trùng | Unique key, replay test |
| Data correctness | Có manifest/snapshot và phép đối soát độc lập | Count, control totals, key diff |
| Operations | Biết người có quyền quyết định, trigger, timeout, kế hoạch B | Runbook đã diễn tập |

Không có cách đo in-flight và dữ liệu đích thì không nên hứa có thể rollback “không mất dữ liệu” trong mọi trường hợp.

### 5.1. Trigger rollback

Ngưỡng phụ thuộc SLO của từng hệ thống. Ví dụ **minh họa**, cần hiệu chỉnh từ baseline:

- `failed_partition_rate` hoặc `chunk_retry_rate` tăng bất thường so với bản ổn định trên workload tương đương.
- `p95_chunk_latency` vượt ngưỡng trong cửa sổ quan sát đã định và queue lag tăng liên tục.
- Phát hiện record trùng, missing key, sai tổng tiền hoặc external side effect không đúng.
- Không đạt điều kiện bảo mật/authorization, chẳng hạn worker mới có quyền truy cập vượt phạm vi.
- Có lỗi deserialize `ExecutionContext` hoặc message từ release đang chạy.

Với lỗi ảnh hưởng tính đúng đắn dữ liệu, nên **ngừng dispatch ngay** và phân loại phạm vi ảnh hưởng; không đợi vượt ngưỡng hiệu năng. Với lỗi chỉ liên quan throughput, cân nhắc giảm concurrency, giới hạn workload hoặc rollback theo runbook.

## 6. Runbook rollback phiên bản

### Pha 0 — Ghi nhận phạm vi sự cố

Trước khi thay đổi hệ thống, chốt:

- Release/build digest hiện tại và release dự định quay lại.
- `jobName`, `JobInstance`, `JobExecution`, `StepExecution` đang chạy; các partition/worker gắn với chúng.
- `batchId`/snapshot/watermark, kết quả đã commit, ngoại lệ đã được chấp thuận.
- Trạng thái broker: queued, unacked, in-flight, pending replies, DLQ.
- Mốc schema migration, dạng `ExecutionContext` và protocol version.

Lưu lại dữ liệu điều tra đủ để đối soát và audit; tránh đưa PII thô vào log hoặc ticket.

### Pha 1 — Fencing: ngăn sinh việc mới

1. Tắt/giành lại quyền scheduler/JobLauncher để không khởi chạy job trùng trong lúc rollback.
2. Ngừng manager phân phối chunk/partition mới cho release lỗi. Nếu có nhiều manager, sử dụng cơ chế **một chủ sở hữu dispatch** hoặc fencing để chặn instance cũ tiếp tục gửi sau khi mất quyền.
3. Ngăn green consumer nhận message mới bằng route/queue hoặc listener stop/pause được thiết kế cho broker đang dùng; bảo toàn message và trạng thái unacked.
4. Phân biệt thao tác “ngừng nhận mới” với “hủy công việc đã commit hoặc đang chạy”.

Khi `JobOperator.stop(executionId)` được sử dụng trong Spring Batch, lệnh có thể yêu cầu dừng **bất đồng bộ**; chỉ tiếp tục khi trạng thái execution/worker và checkpoint đã được xác minh. Một số step không thể dừng tức thì hoặc không restartable; kiểm tra implementation cụ thể.

### Pha 2 — Drain và xác nhận in-flight

Để các transaction/chunk/partition đang xử lý đạt trạng thái xác định. Đối chiếu:

~~~text
dispatch mới đến green = 0
queued work được gán cho green = đã phân loại rõ
in-flight/unacked work = 0 hoặc đã bàn giao theo quy trình retry
pending replies = 0 hoặc đã xử lý/correlate theo execution
step executions = terminal hoặc được xử lý riêng với nguyên nhân cụ thể
business commits = đã ghi nhận và có khóa đối soát
~~~

**Không dùng một chỉ báo duy nhất** như queue depth bằng 0 hoặc Kubernetes pod `Ready=false` để kết luận drain xong: worker có thể đang giữ message prefetch, đã commit mà chưa reply, hoặc broker còn pending acknowledgment.

Nếu hết thời hạn drain, chuyển tình huống sang điều tra có kiểm soát. Có thể cần giữ worker green sống để hoàn tất partition hoặc để message được redeliver vào route phù hợp. Không tuyên bố thành công chỉ vì hết timeout.

### Pha 3 — Đánh giá điểm khôi phục

Sử dụng ma trận tương thích ở phần 2 để trả lời:

1. **Có thể chạy code blue trên metadata/database hiện tại?** Nếu có, tiếp tục rollback ứng dụng.
2. **Job green đã commit gì?** Nếu có, dữ liệu được bảo toàn theo business key hay cần remediation?
3. **Những execution hiện tại có thể restart trên blue?** Nếu chưa được kiểm thử, pin về green để hoàn thành hoặc sửa/fix-forward.
4. **Message còn lại thuộc protocol nào?** Định tuyến đúng consumer hoặc chuyển đổi message theo kế hoạch đã kiểm thử.
5. **Có external side effect không?** Xác minh receipt và idempotency key trước khi gửi lại.

Nếu một câu hỏi trọng yếu chưa có bằng chứng, trạng thái rollback phải là **chưa đủ điều kiện**. Không tự động phát lại toàn bộ dữ liệu bằng cách tạo `JobInstance` mới.

### Pha 4 — Chuyển phiên bản

Khi đủ điều kiện, khởi động release blue từ artifact/config đã chốt, health check, xác minh kết nối tới JobRepository/broker/database và cấp **một phạm vi công việc nhỏ có kiểm soát**. Sau đó chuyển scheduler/manager/route cho **công việc mới** về blue. Với execution đang chạy, tuân theo `releaseAffinity` đã xác định thay vì thay image cho mọi worker cùng lúc.

Không áp dụng tự động một migration `DOWN` cho business DB hoặc bảng metadata. Chỉ thực hiện nếu tương thích, tác động dữ liệu và kế hoạch phục hồi đã được kiểm chứng.

### Pha 5 — Restart/replay theo đúng trạng thái

Nếu một `JobInstance` chưa hoàn tất và được đánh giá restartable, thực hiện restart bằng API/vận hành Spring Batch tương thích với phiên bản sở hữu metadata, sau khi đã xác nhận không còn process cũ tiếp tục ghi.

Ví dụ **pseudocode vận hành**, không phải lệnh shell/CLI hoàn chỉnh:

~~~java
// Chỉ chạy sau khi hoàn tất fencing, drain và kiểm tra tương thích.
Long executionId = incident.getFailedOrStoppedExecutionId();

// Yêu cầu dừng có thể bất đồng bộ; cần chờ trạng thái thật.
jobOperator.stop(executionId);
verifyStepAndWorkerTermination(executionId);
verifyCheckpointCompatibility(executionId, targetRelease);
verifyBusinessIdempotency(incident.getBatchId());

// Chỉ restart khi trạng thái JobInstance cho phép,
// không có writer cũ còn chạy và release mục tiêu đọc được checkpoint.
jobOperator.restart(executionId);
~~~

Đoạn trên mang tính mô tả trình tự, không nên copy vào production như một thủ tục tự động vô điều kiện: một execution đã ở trạng thái cuối có thể không cần gọi `stop`; restart có điều kiện trạng thái, có thể lỗi hoặc bị cấm; các hàm `verify...` là kiểm tra ứng dụng tự xây dựng. Khi rollback cần phân biệt **đường restart có metadata** với **replay dữ liệu có kiểm soát**; replay có thể tạo job instance mới và phải dùng idempotency/đối soát độc lập.

### Pha 6 — Đối soát trước khi đóng sự cố

Xác minh ít nhất:

- Input snapshot theo `batchId` và output business key có đúng tập khóa mong đợi.
- Không có duplicate, missing item, extra item, số tiền sai, ngoại lệ chưa phê duyệt.
- Trạng thái step/partition theo `JobRepository` phản ánh đúng các lần xử lý.
- Broker không còn request/reply hoặc DLQ chưa phân loại thuộc release lỗi.
- External sink có receipt/watermark tương ứng, hoặc đang ở trạng thái `INCONCLUSIVE` cần điều tra.
- Throughput, latency, CPU/heap/DB pool và retry sau rollback đạt ngưỡng đủ an toàn.

Chỉ mở lịch batch tiếp theo hoặc phát hành dữ liệu khi những kiểm soát bắt buộc đạt. Ghi lại thời điểm chuyển route, quyết định rollback/fix-forward, evidence và người chịu trách nhiệm.

## 7. Minh họa cách route theo phiên bản

Để tránh thay đổi logic cho một execution đang chạy, manager có thể chốt route khi tạo logical job:

~~~java
// Pseudocode: ExecutionRouteStore và WorkPublisher do ứng dụng xây dựng.
void dispatch(PartitionWork work) {
    ReleaseRoute route = executionRouteStore.getRequired(
            work.jobExecutionId()
    );

    // Một JobExecution giữ route ổn định qua retry.
    String destination = switch (route.release()) {
        case "blue" -> "settlement.work.blue";
        case "green" -> "settlement.work.green";
        default -> throw new IllegalStateException("Unknown release route");
    };

    workPublisher.publish(destination, work.withCorrelationId(
            correlationFor(work.jobExecutionId(), work.partitionName())
    ));
}
~~~

`ExecutionRouteStore` cần lưu bền vững, có xử lý cạnh tranh và phân biệt **job logical key** với từng lần restart. Khi `JobExecution` thay đổi do restart của cùng `JobInstance`, phải giữ được chính sách version affinity đã chốt hoặc chủ động migrate có kiểm thử. Mã trên không tự bảo đảm transaction giữa lưu route, gửi message và cập nhật Batch metadata; hệ thống thực cần cơ chế outbox/inbox hoặc retry/reconciliation khi có mất kết nối.

### Ví dụ cấu hình deploy

~~~yaml
# Trích đoạn minh họa; phải kết hợp vào manifest Kubernetes hoàn chỉnh.
metadata:
  labels:
    app: settlement-worker
    release: blue
spec:
  template:
    spec:
      terminationGracePeriodSeconds: 600
      containers:
        - name: worker
          image: registry.example/settlement-worker@sha256:REPLACE_WITH_DIGEST
          env:
            - name: RELEASE_ID
              value: blue
            - name: SPRING_BATCH_JOB_ENABLED
              value: "false"
            - name: WORK_REQUEST_QUEUE
              value: settlement.work.blue
~~~

Đây là **mẫu cấu hình**, chưa phải manifest `Deployment` deploy được trực tiếp. `WORK_REQUEST_QUEUE` là biến do ứng dụng tự định nghĩa và phải được ánh xạ tới listener của broker tương ứng; Spring Batch không mặc định hiểu biến này. `terminationGracePeriodSeconds` là khoảng chờ dừng container, **không bảo đảm** mọi partition hoàn thành trước hạn. Với worker kéo message, cần ngừng listener và xử lý acknowledgment đúng cách; không chỉ đổi Kubernetes `Service`.

## 8. Xử lý dữ liệu đã ghi và side effect

Đối với workload lớn, rollback binary thường xảy ra **sau một phần dữ liệu đã commit**. Tính đúng đắn phụ thuộc thiết kế giao dịch và idempotency.

### 8.1. Ma trận lỗi quanh commit

| Điểm thất bại | Có thể đã xảy ra | Hành động an toàn |
|---|---|---|
| Trước business DB commit | Chưa có kết quả bền vững từ transaction đó | Rollback transaction, retry/restart hợp lệ |
| Sau DB commit, trước broker ack/reply | Đã có kết quả nhưng message có thể redeliver | Idempotent writer, kiểm tra output trước khi replay |
| Sau reply, trước JobRepository update | Worker hoàn thành nhưng metadata/manager còn nghi ngờ | Correlate reply, đối soát metadata và output |
| Sau gọi external API, trước nhận response | Phía nhận có thể đã thực hiện side effect | Tra cứu receipt/idempotency key phía nhận; tránh gửi lại mù quáng |
| Sau schema migration không tương thích | Blue không hiểu dữ liệu/metadata mới | Dừng rollback binary, thiết kế fix-forward hoặc restore có kiểm soát |

Một message được broker giao lại **không đồng nghĩa** business transaction lần trước đã thất bại. Không dựa vào “exactly once” chỉ từ queue, Spring Batch hoặc Kubernetes. Thiết kế writer idempotent theo khóa nghiệp vụ ổn định.

### 8.2. Ví dụ ghi idempotent

Với nghiệp vụ cho phép duy nhất một kết quả settlement trên mỗi giao dịch của một kỳ:

~~~sql
CREATE TABLE settlement_result (
    settlement_date DATE NOT NULL,
    transaction_id UUID NOT NULL,
    amount NUMERIC(18,2) NOT NULL,
    calculation_version INTEGER NOT NULL,
    PRIMARY KEY (settlement_date, transaction_id)
);

-- Ví dụ PostgreSQL: chống tạo dòng trùng khi chunk bị phát lại.
INSERT INTO settlement_result (
    settlement_date, transaction_id, amount, calculation_version
) VALUES (
    :settlement_date, :transaction_id, :amount, :calculation_version
)
ON CONFLICT (settlement_date, transaction_id) DO NOTHING;
~~~

`DO NOTHING` chỉ là biện pháp chặn trùng dòng; nếu release mới tính `amount` khác với bản cũ, bỏ qua xung đột có thể **che giấu sai lệch nghiệp vụ**. Trong hệ thống thật, cần kiểm tra giá trị hiện có, calculation version và rule; nếu không tương đương, đưa vào trạng thái conflict để điều tra hoặc dùng adjustment đã được phê duyệt.

### 8.3. Restore database không phải lựa chọn mặc định

Khôi phục toàn bộ database về thời điểm cũ có thể xóa những giao dịch hợp lệ phát sinh sau thời điểm backup, làm sai quan hệ với message đã ack và hệ thống ngoài. Cần kiểm soát write freeze, replication/PITR point, phạm vi tác động, downstream coordination và reconciliation. Khi đã có lệnh thanh toán/email/API hoàn tất, backup DB không tự đảo chúng.

Với dữ liệu nghiệp vụ đã sai nhưng vẫn có đủ metadata, thường cần **repair/compensation chọn lọc theo business key**; thực hiện bởi quy trình có quyền phù hợp và lưu bằng chứng audit. Chỉ restore toàn hệ thống khi đã hiểu và kiểm soát nhất quán xuyên các thành phần.

## 9. Ví dụ thực tế: rollback đợt scale remote partitioning

Một hệ thống đối soát giao dịch xử lý **12 triệu bản ghi mỗi đêm**. Release blue `3.4` chia 48 partition, green `3.5` dùng 96 partition và bổ sung field kết quả. Nhóm triển khai theo phương án **expand schema, không xóa cột cũ**, đồng thời giữ hai release và queue riêng.

### Trước cutover

1. Green được thử trên bản sao JobRepository, snapshot input và message hợp lệ, gồm một kịch bản restart từ checkpoint của blue.
2. Các execution blue còn chạy được pin vào blue; green nhận execution của một phạm vi ngày/kỳ nghiệp vụ khác.
3. Writer dùng business key `(businessDate, transactionId)` để chặn xử lý trùng; báo cáo reconciliation kiểm tra key set và tổng tiền.
4. Release store ghi image digest, config và schema version; bảng phân tuyến ghi `JobExecution → release`.

### Sự cố

Sau khi green xử lý 15 partition, các partition tiếp theo lỗi timeout do connection pool thiếu. Tăng replicas không giải quyết được vì DB đã sát giới hạn connection. Các partition đầu đã commit một phần kết quả; một số response chưa được manager ghi nhận.

### Quyết định rollback

1. Ngừng phân phối partition mới cho green, không tạo thêm `JobInstance` bằng `run.id` để chạy lại 12 triệu dòng.
2. Kiểm tra 15 partition đã commit và message pending/reply; giữ worker green cho những partition cần drain.
3. Nếu blue tương thích với checkpoint và dữ liệu của execution này, có thể cân nhắc restart theo kế hoạch; nếu chưa có bằng chứng, giữ execution green cho đến khi kết thúc hoặc sửa cấu hình pool tại green (**fix-forward**).
4. Chuyển **execution mới** trở về blue, giữ tương thích schema đã expand và tạm ngừng rollout green.
5. Đối soát snapshot với business sink theo `transactionId`, sum, missing/extra và các partition ranges. Chỉ công bố kỳ batch hoàn tất khi dữ liệu khớp.

**Bài học:** rollback phiên bản không nhất thiết buộc mọi worker lập tức về bản cũ. Giữ version affinity cho những execution cũ và chuyển việc mới sang release ổn định thường bảo toàn checkpoint và dữ liệu tốt hơn.

### Nếu lỗi do schema mới

Giả sử green đã ghi một giá trị `risk_category` mà blue không hiểu, hoặc xóa/đổi schema cũ. Khi đó phải dừng rollback tự động, cô lập cohort dữ liệu và chọn:

- **Fix-forward:** sửa green để tiếp tục xử lý trên schema hiện tại, rồi sau đó lên lịch quay lại chiến lược tương thích.
- **Migration tương thích ngược:** nếu có thể chuyển đổi dữ liệu an toàn, cung cấp lại contract mà blue đọc được.
- **Restore có kiểm soát:** khi đã xác định rõ phạm vi và side effect xuyên hệ thống, có backup hợp lệ và kế hoạch đồng bộ lại.

Không cố cưỡng bức image blue chạy trên schema không tương thích chỉ vì cần khôi phục nhanh.

## 10. Kiểm thử rollback trước production

Rollback chỉ đáng tin khi đã **diễn tập từ trạng thái mà phiên bản mới đã tạo ra**, không chỉ “deploy blue lên môi trường sạch”.

| Kiểm thử | Cách tạo tình huống | Kỳ vọng |
|---|---|---|
| **Binary + config** | Deploy green, sau đó nạp lại image/config blue | Blue khởi động và kết nối các phụ thuộc hiện tại |
| **Metadata migration** | Chạy green trên bản sao JobRepository thật, thử blue đọc metadata | Không lỗi schema/serializer trong tình huống cho phép rollback |
| **Checkpoint restart** | Dừng giữa chunk/partition, thử restart trên release mục tiêu | Không đọc thiếu, đọc sai con trỏ hoặc tạo side effect trùng |
| **Message compatibility** | Để request/reply của green tồn trong broker khi đổi route | Không poison message, correlation đúng, DLQ được phân loại |
| **Crash after commit** | Worker commit DB rồi chết trước ack/reply | Redelivery không làm trùng output |
| **Concurrent scheduler** | Cho blue/green cùng có khả năng launch job | Có cơ chế ownership/fencing, không khởi chạy lặp logic |
| **Schema dual compatibility** | Green ghi dữ liệu mới rồi blue đọc/ghi tiếp | Dữ liệu giữ nguyên ý nghĩa và ràng buộc |
| **External side effect** | API bên ngoài thành công nhưng trả timeout | Retry dùng operation key không tạo giao dịch thứ hai |
| **Partition coverage** | Cố tình tạo gap/overlap khi thay grid size | Đối soát phát hiện thiếu/thừa theo key |
| **Drain timeout** | Giữ một worker treo lâu hơn grace period | Kết quả được phân loại, không tuyên bố drain thành công |
| **Load rollback** | Chuyển về blue dưới backlog thực tế | Pool/throughput/latency đạt mức vận hành cho phép |
| **Data reconciliation** | Tạo missing key, extra key và wrong amount bù trừ | Báo cáo vẫn phát hiện sai dù count/sum tổng nhìn đúng |

Với Spring Batch nâng major version, không nên suy đoán khả năng downgrade/restart từ tên phiên bản; kiểm tra **migration guide đúng version** và thử trên bản sao metadata, payload và dữ liệu thực tế đã được ẩn danh/phân quyền. Không chạy các thử nghiệm phá dữ liệu trực tiếp trên JobRepository production.

## 11. Chỉ số và cảnh báo phục vụ rollback

| Nhóm | Chỉ số gợi ý | Dùng để |
|---|---|---|
| Batch metadata | Job/step executions theo status, duration, read/write/filter/skip/retry | Khoanh vùng execution và lỗi |
| Dispatch & messaging | Queue depth, unacked, pending replies, redelivery, DLQ | Đo drain và nguy cơ replay |
| Worker runtime | Số active threads, chunk p95, partition p95, GC, heap, CPU | Phát hiện resource bottleneck |
| Pool & external | JDBC active/wait, broker connections, API timeout, error rate | Phân biệt lỗi release với nghẽn hạ tầng |
| Data correctness | Missing, extra, duplicates, value mismatch, control total | Chứng minh kết quả đúng |
| Rollback progress | Thời điểm fence, route change, active release, remaining old executions | Chứng minh rollback đã hoàn tất đúng phạm vi |

Gắn nhãn `release`, `jobName`, `stepName` và loại lỗi với độ phân biệt hợp lý. `jobExecutionId` và `correlationId` nên có trong log/tracing có quyền kiểm soát khi cần, **không** dùng business ID/PII hoặc ID có cardinality quá cao làm metric labels.

### Các điều kiện đóng rollback

Một quy trình có thể định nghĩa:

~~~text
ROLLBACK_REQUESTED
    -> DISPATCH_FENCED
    -> INFLIGHT_DRAINED (hoặc PENDING_RECOVERY được ghi nhận)
    -> OLD_RELEASE_ACTIVE_FOR_NEW_WORK
    -> DATA_RECONCILED
    -> INCIDENT_CLOSED
~~~

Đây là trạng thái **runbook do ứng dụng định nghĩa**, không phải `BatchStatus` mặc định. Nếu chưa đạt `DATA_RECONCILED`, trạng thái vận hành vẫn cần thể hiện **PENDING/INCONCLUSIVE**; không chỉ dựa vào “pod blue đã Ready” để đóng incident.

## 12. Các sai lầm thường gặp

| Sai lầm | Nguy cơ | Cách xử lý |
|---|---|---|
| Rollback image nhưng giữ cấu hình/serializer mới | Runtime lỗi hoặc đọc message sai | Rollback theo release manifest và contract đã kiểm thử |
| Chạy migration `DOWN` tự động | Mất dữ liệu mới, phá rollback window | Expand/contract, kiểm tra ảnh hưởng rồi mới contract |
| Sửa tay `BATCH_JOB_EXECUTION` để đổi status | Metadata và business state mất nhất quán | Dùng quy trình Batch hợp lệ và xác minh worker |
| Restart bằng `run.id` mới cho nhanh | Tạo `JobInstance` mới, xử lý dữ liệu trùng | Restart đúng instance hoặc replay có idempotency |
| Scale worker green về 0 ngay lập tức | Bỏ dở transaction và request đang unacked | Fencing, drain rồi thu hồi |
| Tin Kubernetes Service chuyển được broker consumer | Consumer vẫn nhận message trực tiếp từ broker | Điều phối listener, route và consumer group |
| Quay lại blue để xử lý toàn bộ partition green đã commit | Duplicate/khác semantics | Version affinity, checkpoint test và business key |
| Chỉ dựa vào `writeCount` | Không phát hiện thiếu/thừa bù trừ và output sai | Đối soát snapshot, key set, value và totals |
| Quên reply/error/DLQ | Message cũ gây poison hoặc phát lại sau rollback | Kiểm kê và xử lý tất cả messaging path |
| Tuyên bố rollback xong khi pod healthy | External side effect và output vẫn sai | Reconciliation trước khi đóng sự cố |

## 13. Checklist cho release manager và batch operator

### Trước khi nâng phiên bản

- [ ] Có image digest, config, dependency/runtime và thông tin schema của bản đang ổn định.
- [ ] Đã thử tương thích `JobRepository` và `ExecutionContext` theo **hai chiều cần thiết** trong cửa sổ rollback.
- [ ] Migration nghiệp vụ thực hiện theo expand/migrate/contract, chưa loại bỏ contract cũ quá sớm.
- [ ] Đã ghi nhận mọi thay đổi job/step names, identifying parameters, serialization và message topology.
- [ ] Có cơ chế chọn một chủ sở hữu scheduler/manager và version affinity theo execution.
- [ ] Writer/downstream xử lý được redelivery bằng business idempotency key.
- [ ] Có snapshot/manifest đầu vào và phép đối soát độc lập ở business sink.
- [ ] Đã diễn tập crash sau commit, rollback khi queue còn request và restart với checkpoint cũ.

### Khi xảy ra sự cố

- [ ] Đã chốt phạm vi release, batch, job/step/partition và dữ liệu đã commit.
- [ ] Scheduler/manager đã bị fencing, worker release lỗi không nhận work mới.
- [ ] In-flight, unacked, pending replies và DLQ đã được drain hoặc phân loại.
- [ ] Đã đánh giá tương thích metadata, DB, message và external side effect trước khi đổi image.
- [ ] Mỗi execution có kế hoạch tiếp tục/restart/repair cụ thể và người chịu trách nhiệm.
- [ ] Không phát lại toàn bộ bằng cách tạo instance mới khi chưa kiểm tra dữ liệu.
- [ ] Có kết quả đối soát input/output sau khôi phục; mismatch vẫn được giữ mở.
- [ ] Đã lưu timeline, config version, bằng chứng và quyết định go/no-go.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Blue chạy được trên image cũ sau khi rollback. Điều đó có chứng minh rollback thành công không?

*Gợi ý:* Chưa. Phải kiểm tra metadata, message còn treo, business outputs và side effect ngoài transaction; một pod khỏe không bảo đảm dữ liệu đúng.

**Câu 2.** Bản green thêm field vào `ExecutionContext`, sau đó rollback blue và restart job. Rủi ro là gì?

*Gợi ý:* Bản cũ có thể không deserialize hoặc không hiểu checkpoint; cần compatibility test hoặc giữ execution đó trên green.

**Câu 3.** Worker commit dữ liệu rồi crash trước khi gửi reply, sau rollback broker phát lại work item. Cần điều gì?

*Gợi ý:* Business idempotency key ổn định, writer nhận diện kết quả đã commit và đối soát theo business key.

**Câu 4.** Release mới đã xóa một cột mà release cũ cần. Có nên chạy migration `DOWN` ngay không?

*Gợi ý:* Không được coi là giải pháp mặc định. Đánh giá dữ liệu đã ghi, tính tương thích, side effect và khả năng restore; có thể cần fix-forward.

**Câu 5.** Tại sao không nên chia một JobExecution đang chạy cho cả blue lẫn green tùy số worker sẵn có?

*Gợi ý:* Hai phiên bản có thể khác checkpoint, business rule, message contract và serializer. Phải kiểm chứng tương thích hoặc gắn version affinity.

## Kết luận

**Chiến lược rollback phiên bản** trong Spring Batch là quản lý an toàn **trạng thái đã tồn tại qua nhiều bước thực thi**, đặc biệt khi workload được phân phối qua nhiều thread, partition, process hoặc broker. Muốn có đường quay về bản ổn định, cần bảo vệ tương thích của `JobRepository`, `ExecutionContext`, schema nghiệp vụ, message và idempotency ngay từ khi thiết kế release. Khi sự cố xảy ra, thứ tự xử lý là **chặn việc mới, drain công việc cũ, đánh giá tương thích, chuyển release theo execution, khôi phục có kiểm soát và đối soát dữ liệu**. Nếu code cũ không thể hiểu trạng thái mới, fix-forward hoặc remediation có kế hoạch an toàn hơn việc ép rollback binary.
