# Dependency, array job, retry và timeout cho Batch job

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Giải thích vòng đời của AWS Batch job và phân biệt các trạng thái PENDING, RUNNABLE, STARTING, RUNNING, SUCCEEDED và FAILED.
- Thiết kế dependency graph để điều phối các bước ingest, preprocess, compute, aggregate và publish.
- Chọn job dependency thông thường, SEQUENTIAL hoặc N_TO_N cho array jobs.
- Chia workload lớn thành array children bằng AWS_BATCH_JOB_ARRAY_INDEX.
- Cấu hình retry strategy với attempts và evaluateOnExit theo từng loại lỗi.
- Thiết kế job idempotent để retry không tạo dữ liệu hoặc side effect trùng.
- Chọn timeout theo thời gian xử lý, xử lý SIGTERM và lưu checkpoint khi job sắp bị dừng.
- Phân biệt retry của AWS Batch với retry/catch của AWS Step Functions.
- Theo dõi queue backlog, job duration, retry, failure và queue-blocked events.
- Xây dựng runbook để điều tra job bị kẹt, retry liên tục, timeout hoặc dependency thất bại.

## 1. AWS Batch job là gì?

AWS Batch lập lịch và chạy container workloads trên compute environments. Một job có thể là tác vụ độc lập, một child trong array job hoặc một node trong multi-node parallel job. Job definition mô tả image, command, tài nguyên, role, retry strategy và timeout; job queue quyết định nơi job chờ; compute environment cung cấp capacity để chạy.

Một workload batch thường gồm nhiều bước:

~~~mermaid
flowchart TD
    A["Nhận dữ liệu"] --> B["Validate / preprocess"]
    B --> C["Chia partitions"]
    C --> D["Compute song song"]
    D --> E["Aggregate kết quả"]
    E --> F["Publish / notify"]
~~~

Dependency đảm bảo bước sau chỉ chạy khi bước trước đạt điều kiện hoàn thành. Array job giúp chia một bước thành nhiều phần độc lập. Retry giúp thử lại một attempt thất bại. Timeout ngăn một attempt chạy mãi khi bị treo hoặc vượt ngân sách thời gian.

Bốn cơ chế này giải quyết các vấn đề khác nhau. Chúng cần được phối hợp cùng queue capacity, idempotency, logging và cách xử lý lỗi nghiệp vụ.

## 2. Vòng đời và trạng thái của Batch job

Khi gọi SubmitJob, job đi qua các trạng thái:

| Trạng thái | Ý nghĩa | Việc cần kiểm tra |
|---|---|---|
| SUBMITTED | Job vừa được gửi và chưa được scheduler đánh giá | Job definition, queue, dependency |
| PENDING | Job đang chờ dependency hoặc một resource dependency | Job upstream, consumable resources |
| RUNNABLE | Không còn dependency; sẵn sàng được scheduler cấp host | Compute environment, capacity, quota, queue policy |
| STARTING | Đã được chọn host; container đang khởi tạo | Image pull, init container, container dependencies |
| RUNNING | Container đang thực thi | Logs, CPU/memory, application progress |
| SUCCEEDED | Container kết thúc với exit code 0 | Kết quả, output manifest, audit |
| FAILED | Đã hết attempts hoặc job bị hủy/dừng/thất bại | statusReason, attempts, CloudWatch Logs |

~~~mermaid
stateDiagram-v2
    [*] --> SUBMITTED
    SUBMITTED --> PENDING: Có dependency/resource chưa sẵn sàng
    SUBMITTED --> RUNNABLE: Không có dependency chờ
    PENDING --> RUNNABLE: Dependency được thỏa
    RUNNABLE --> STARTING: Scheduler cấp capacity
    STARTING --> RUNNING: Container khởi tạo xong
    RUNNING --> SUCCEEDED: Exit code 0
    RUNNING --> RUNNABLE: Attempt lỗi và còn retry
    RUNNING --> FAILED: Hết retry hoặc lỗi không retry
    RUNNABLE --> FAILED: Cancel / terminate / lỗi quản lý
    SUCCEEDED --> [*]
    FAILED --> [*]
~~~

Phân biệt PENDING và RUNNABLE rất quan trọng:

- PENDING thường chờ job khác thành công hoặc chờ resource dependency.
- RUNNABLE đã đủ điều kiện logic nhưng có thể chưa có compute capacity.
- STARTING tính cả thời gian pull image và khởi tạo container. Timeout của Batch bắt đầu khi attempt chuyển sang RUNNING, không tính thời gian STARTING.

Một job ở RUNNABLE lâu không nhất thiết bị lỗi. Kiểm tra statusReason, compute environment, vCPU/memory capacity, service quotas và queue policy trước khi tăng retry.

## 3. Dependency graph và DAG

Dependency là quan hệ giữa các job: job B chỉ được chạy khi các job mà B phụ thuộc đã hoàn thành thành công.

Ví dụ:

~~~mermaid
flowchart LR
    A["Extract"] --> B["Normalize"]
    B --> C["Partition"]
    C --> D1["Compute shard 0"]
    C --> D2["Compute shard 1"]
    C --> D3["Compute shard N"]
    D1 --> E["Aggregate"]
    D2 --> E
    D3 --> E
    E --> F["Publish"]
~~~

Đây là một directed acyclic graph (DAG): cạnh thể hiện thứ tự, còn các nhánh không phụ thuộc nhau có thể chạy song song.

Một job có thể khai báo tối đa 20 dependencies. Scheduler đợi tất cả dependencies thành công trước khi chuyển dependent job từ PENDING sang RUNNABLE. Nếu một dependency thất bại, dependent job tự động chuyển sang FAILED.

Native Batch dependencies biểu diễn nhánh “chạy khi upstream SUCCEEDED”. Chúng không tự biểu diễn nhánh xử lý lỗi như “nếu extract thất bại thì gửi cảnh báo, chạy compensation hoặc tiếp tục với dữ liệu cũ”. Với workflow có nhánh lỗi, điều kiện, phê duyệt hoặc vòng lặp, dùng AWS Step Functions hoặc orchestrator phù hợp.

## 4. Khai báo dependency cho job thông thường

Giả sử có hai job:

- prepare-dataset tạo dữ liệu đầu vào.
- train-model chỉ chạy sau khi prepare thành công.

Gửi job đầu tiên:

~~~bash
aws batch submit-job \
  --job-name prepare-dataset \
  --job-queue arn:aws:batch:ap-southeast-1:111122223333:job-queue/research-queue \
  --job-definition prepare-dataset:4 \
  --region ap-southeast-1
~~~

Lưu job ID được trả về vào file depends-on.json:

~~~json
[
  {
    "jobId": "11111111-2222-3333-4444-555555555555"
  }
]
~~~

Gửi job phụ thuộc:

~~~bash
aws batch submit-job \
  --job-name train-model \
  --job-queue arn:aws:batch:ap-southeast-1:111122223333:job-queue/research-queue \
  --job-definition train-model:7 \
  --depends-on file://depends-on.json \
  --region ap-southeast-1
~~~

train-model ở trạng thái PENDING trong khi prepare-dataset chưa SUCCEEDED. Nếu job upstream hết retry và thành FAILED, job downstream cũng thành FAILED; nó không tự chạy theo nhánh thay thế.

### 4.1 Nhiều dependencies

Một bước publish có thể cần cả aggregate và validation thành công:

~~~json
[
  {
    "jobId": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
  },
  {
    "jobId": "11111111-2222-3333-4444-555555555555"
  }
]
~~~

Khi đó job chỉ RUNNABLE sau khi cả hai job kết thúc thành công. Giữ dependency graph nhỏ, rõ và có tên phản ánh business step để dễ điều tra.

## 5. Thiết kế DAG dễ vận hành

Một DAG tốt có các đặc điểm:

- Mỗi node làm một nhiệm vụ có đầu vào/đầu ra rõ ràng.
- Mỗi cạnh thể hiện một điều kiện thực sự cần thiết.
- Những nhánh độc lập được phép chạy song song.
- Có bước validation trước khi publish dữ liệu.
- Có cách xử lý khi upstream thất bại.
- Có correlation ID hoặc workflow ID xuyên suốt các job.
- Output được ghi vào vùng staging theo workflow/run ID.
- Có bước commit/publish cuối để người dùng chỉ nhìn thấy kết quả hoàn chỉnh.

Tránh tạo một job khổng lồ thực hiện mọi bước nếu các bước có thể retry, scale hoặc quan sát độc lập. Ngược lại, không chia quá nhỏ đến mức thời gian khởi tạo container và orchestration lớn hơn thời gian xử lý thực tế.

Không dùng dependency để thay thế kiểm tra dữ liệu. Một job có thể exit code 0 nhưng tạo output rỗng hoặc sai schema. Bước downstream cần kiểm tra manifest, row count, checksum hoặc business invariants trước khi tiếp tục.

## 6. Array job: chạy cùng một job trên nhiều phần dữ liệu

Array job là một job cha quản lý nhiều child jobs có chung job definition và cấu hình tài nguyên. Mỗi child xử lý một phần dữ liệu độc lập và có thể chạy đồng thời trên nhiều hosts.

- Array size phải từ 2 đến 10.000.
- Job cha là handle quản lý các children.
- Job ID của child có dạng parent-job-id:index.
- Index bắt đầu từ 0.
- Container nhận biến môi trường AWS_BATCH_JOB_ARRAY_INDEX.
- Timeout áp dụng cho từng child; parent array job không có timeout.

Ví dụ một workload xử lý 500 partitions có thể được gửi bằng một lệnh SubmitJob với array size 500 thay vì gửi 500 requests riêng.

~~~mermaid
flowchart TD
    P["Array parent: 500 children"] --> C0["Child 0"]
    P --> C1["Child 1"]
    P --> C2["Child 2"]
    P --> CN["Child 499"]
    C0 --> S["S3 result partitions"]
    C1 --> S
    C2 --> S
    CN --> S
~~~

Array size là số lượng child jobs được tạo, không phải số lượng job chắc chắn chạy đồng thời. Concurrency thực tế phụ thuộc queue, compute environment, vCPU/memory, quotas và scheduling policy.

## 7. Dùng AWS_BATCH_JOB_ARRAY_INDEX

Mỗi child cần xác định phần dữ liệu của mình. Dùng array index để ánh xạ tới partition, file, shard hoặc parameter set.

Ví dụ shell entrypoint:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

index="$AWS_BATCH_JOB_ARRAY_INDEX"

python process_partition.py \
  --partition-index "$index" \
  --manifest "s3://research-data/manifests/run-2026-11-20.json"
~~~

Ví dụ Python:

~~~python
import os

index = int(os.environ["AWS_BATCH_JOB_ARRAY_INDEX"])
manifest_uri = os.environ["INPUT_MANIFEST"]

print(f"Processing partition {index} from {manifest_uri}")
process_partition(manifest_uri=manifest_uri, partition_index=index)
~~~

Manifest nên chứa mapping ổn định từ index sang input object hoặc partition range. Không giả định tên file luôn là part-index.csv nếu dữ liệu có thể được repartition giữa các lần chạy.

Gắn workflow ID, dataset version và array index vào output path, ví dụ:

~~~text
s3://research-results/run-2026-11-20/partition=0042/
~~~

Mỗi child chỉ ghi vào output partition của chính nó. Bước aggregate kiểm tra đủ partitions trước khi publish.

## 8. Dependency SEQUENTIAL cho array jobs

Nếu các child phải chạy lần lượt theo index, khai báo dependency có type SEQUENTIAL mà không cần jobId.

Ví dụ sequential-dependency.json:

~~~json
[
  {
    "type": "SEQUENTIAL"
  }
]
~~~

Submit array:

~~~bash
aws batch submit-job \
  --job-name process-sequentially \
  --job-queue research-queue \
  --job-definition process-partition:3 \
  --array-properties size=20 \
  --depends-on file://sequential-dependency.json \
  --region ap-southeast-1
~~~

Thứ tự sẽ là:

- Child 0 chạy trước.
- Child 1 chờ child 0 thành công.
- Child 2 chờ child 1 thành công.
- Tiếp tục cho tới child cuối cùng.

SEQUENTIAL hữu ích khi mỗi bước cập nhật state dùng chung hoặc phải theo thứ tự. Nó loại bỏ phần lớn lợi ích parallelism của array job, vì vậy không dùng chỉ để “đảm bảo chắc chắn”.

## 9. Dependency N_TO_N cho hai array jobs

N_TO_N dùng khi một array job là bước tiếp theo tương ứng với từng child của array job trước. Child index i ở array B đợi child index i của array A thành công.

~~~mermaid
flowchart LR
    A0["Array A:0"] --> B0["Array B:0"]
    A1["Array A:1"] --> B1["Array B:1"]
    A2["Array A:2"] --> B2["Array B:2"]
    AN["Array A:N"] --> BN["Array B:N"]
~~~

Sau khi submit array A, lưu parent job ID. Tạo file n-to-n-dependency.json:

~~~json
[
  {
    "jobId": "PARENT-ARRAY-JOB-ID",
    "type": "N_TO_N"
  }
]
~~~

Submit array B với array size được thiết kế để index mapping tương ứng:

~~~bash
aws batch submit-job \
  --job-name transform-partitions \
  --job-queue research-queue \
  --job-definition transform-partition:2 \
  --array-properties size=100 \
  --depends-on file://n-to-n-dependency.json \
  --region ap-southeast-1
~~~

Với N_TO_N, child 42 của array B chờ child 42 của array A. Đây là lựa chọn phù hợp cho pipeline map từng partition qua nhiều stage mà không phải đợi toàn bộ array A hoàn tất.

Thiết kế index mapping rõ ràng giữa các arrays. Nếu các bước cần gom toàn bộ kết quả trước khi chạy, dùng một job aggregate phụ thuộc parent array thay vì N_TO_N.

## 10. Trạng thái của parent và child array job

Parent array job là đại diện quản lý; nó không phải container chạy công việc. Parent có thể ở SUBMITTED, PENDING, FAILED hoặc SUCCEEDED. Parent thường ở PENDING trong khi children đang chuyển sang RUNNABLE và chạy.

Các quy tắc vận hành:

- Cancel hoặc terminate parent sẽ cancel/terminate tất cả children.
- Cancel/terminate một child làm child đó thành FAILED nhưng không trực tiếp dừng các siblings khác.
- Nếu một child thất bại, parent array job cuối cùng cũng thành FAILED khi các children hoàn tất.
- Có thể xem từng child bằng job ID có hậu tố :index.

Không chỉ kiểm tra parent status để tìm nguyên nhân. Hãy xác định child index lỗi, statusReason, attempt history và log stream của child đó.

## 11. Retry strategy: số lần thử của một job

Retry strategy cho phép AWS Batch tự động chạy lại job khi attempt thất bại. Các lỗi có thể retry gồm:

- Container kết thúc với exit code khác 0.
- EC2 instance gặp lỗi hoặc bị terminate.
- AWS service gặp lỗi nội bộ hoặc outage.
- Một số lỗi khởi tạo container hoặc agent tùy evaluateOnExit.

attempts có giá trị từ 1 đến 10; giá trị bao gồm lần chạy đầu tiên. Mặc định là 1, tức không có retry thêm. Khi một attempt thất bại và còn attempts, job quay lại RUNNABLE.

Biến môi trường AWS_BATCH_JOB_ATTEMPT bắt đầu từ 1 và tăng theo từng lần chạy. Có thể dùng để log attempt number hoặc thay đổi mức chẩn đoán, nhưng không dùng attempt number làm idempotency key vì cùng một business operation sẽ có nhiều attempt.

Jobs bị cancel/terminate hoặc lỗi do job definition không hợp lệ không được retry theo retry strategy thông thường. Job timeout cũng không tự retry.

## 12. evaluateOnExit: retry theo loại lỗi

evaluateOnExit cho phép quyết định RETRY hoặc EXIT theo:

- onExitCode: glob pattern trên exit code.
- onReason: pattern trên reason của container/job.
- onStatusReason: pattern trên status reason.

Nếu một rule có nhiều điều kiện, các điều kiện được khai báo trong rule phải cùng thỏa để action áp dụng. Nếu không có rule nào match, AWS Batch mặc định retry khi còn attempts. Vì vậy, thêm một rule cuối EXIT cho các lỗi còn lại nếu muốn chính sách rõ ràng.

Ví dụ chiến lược:

~~~json
{
  "attempts": 4,
  "evaluateOnExit": [
    {
      "action": "RETRY",
      "onReason": "AGENT"
    },
    {
      "action": "EXIT",
      "onExitCode": "2"
    },
    {
      "action": "EXIT",
      "onReason": "*"
    }
  ]
}
~~~

Trong ví dụ:

- Lỗi liên quan agent có thể là transient nên retry.
- Exit code 2 được quy ước là input/business validation error nên fail ngay.
- Những lỗi còn lại exit thay vì retry đến hết attempts.

Đây là chính sách minh họa; hãy định nghĩa exit codes trong ứng dụng và kiểm thử reason/statusReason thực tế. Đừng phân loại mọi lỗi thành retry, vì lỗi schema, permission hoặc tham số sai sẽ không tự biến mất.

## 13. Chọn lỗi nào retry và lỗi nào exit

| Loại lỗi | Ví dụ | Hành động thường phù hợp |
|---|---|---|
| Hạ tầng tạm thời | Host/agent failure, container start issue | RETRY |
| Dependency tạm thời | API throttling, timeout ngắn | Retry có giới hạn/backoff trong app hoặc orchestrator |
| Input không hợp lệ | Thiếu file, schema sai, tham số sai | EXIT |
| Permission | AccessDenied do IAM/bucket policy | EXIT và sửa cấu hình |
| Business rule | Dữ liệu không đủ điều kiện xử lý | EXIT hoặc đưa vào exception workflow |
| Out of memory | Memory request quá thấp hoặc leak | Thường EXIT, điều tra rồi tăng resource |
| Application bug | Null pointer, logic lỗi | EXIT để tránh retry lặp cùng lỗi |
| Service outage | Backend tạm thời unavailable | RETRY có giới hạn |

Một retry policy tốt trả lời ba câu hỏi:

1. Lỗi nào có khả năng tự hết?
2. Có thể thử lại bao nhiêu lần trước khi chi phí vượt lợi ích?
3. Sau khi hết retry, ai nhận cảnh báo và dữ liệu nào cần điều tra?

Không retry lỗi không thể phục hồi. Một job sai tham số chạy lại 10 lần vẫn sai, đồng thời chiếm queue capacity và làm chậm workload khác.

## 14. Retry và idempotency

AWS Batch có thể chạy lại container sau khi attempt thất bại. Attempt trước có thể đã ghi một phần dữ liệu, gửi message hoặc gọi API trước khi crash. Nếu lần chạy tiếp theo lặp lại side effect, kết quả có thể bị duplicate.

Thiết kế idempotent:

- Dùng một workflowId hoặc businessRunId ổn định xuyên suốt retries.
- Với array job, kết hợp workflowId + arrayIndex để xác định partition.
- Ghi output vào staging path riêng theo run ID.
- Dùng conditional write, transaction hoặc idempotency token ở backend.
- Chỉ publish/commit khi validation của toàn bộ workflow thành công.
- Ghi attempt number để chẩn đoán, không đưa nó vào business identity.
- Không ghi trực tiếp vào bảng tổng hợp nếu child có thể retry sau khi đã commit một phần.

Ví dụ key ổn định:

~~~text
run-2026-11-20:partition-0042
~~~

Nếu attempt 1 ghi file thành công nhưng container chết trước khi trả exit code 0, attempt 2 phải nhận diện output đã có và xác minh checksum hoặc thay thế an toàn.

## 15. Retry không phải backoff policy đầy đủ

Retry strategy của AWS Batch quyết định số attempts và loại lỗi được retry. Nó không cung cấp một trường backoffSeconds để cấu hình exponential backoff tùy ý.

Nếu dependency cần cooldown hoặc retry theo lịch:

- Thực hiện retry có backoff/jitter bên trong ứng dụng cho request ngắn.
- Đẩy công việc sang SQS delay/retry queue nếu phù hợp.
- Dùng Step Functions Wait và Retry để điều phối thời gian giữa các job submissions.
- Dùng EventBridge để khởi động lại workflow theo lịch hoặc điều kiện.

Không sleep trong container nhiều giờ để thay thế scheduler. Job đang ngủ vẫn chiếm compute capacity và có thể làm giảm throughput của queue.

## 16. Timeout của một job attempt

Mặc định AWS Batch không đặt timeout. Nếu không cấu hình, container chạy cho đến khi process kết thúc.

attemptDurationSeconds xác định thời lượng tối đa của một attempt:

- Giá trị tối thiểu là 60 giây.
- Đếm từ timestamp startedAt khi attempt bắt đầu RUNNING.
- Thời gian STARTING, gồm image pull, không được tính.
- Khi quá hạn, Batch gửi SIGTERM để ứng dụng dừng có kiểm soát.
- Nếu container vẫn chạy sau 30 giây, Batch gửi SIGKILL.
- Việc terminate được thực hiện best-effort; không kỳ vọng chính xác đến từng giây.
- AWS Batch không đặt maximum timeout chung, nhưng Fargate jobs không nên được kỳ vọng chạy quá 14 ngày.

Timeout được cấu hình trong job definition hoặc SubmitJob. Timeout ở SubmitJob ghi đè timeout của job definition. Timeout termination làm job thất bại và không được retry tự động.

## 17. Timeout với array và multi-node parallel jobs

| Loại job | Timeout áp dụng |
|---|---|
| Job thông thường | Từng attempt của job |
| Array job | Mỗi child job có cùng timeout cấu hình; parent array không có timeout |
| Multi-node parallel (MNP) | Toàn bộ job, không phải riêng từng node |

Nếu array có 10.000 children, mỗi child có timeout 1 giờ, không có nghĩa parent kết thúc sau 1 giờ. Parent chỉ hoàn tất khi các children đạt trạng thái cuối.

Timeout của MNP áp dụng cho cả job group. Nếu một node không phản hồi, thiết kế MPI/NCCL application cần xử lý lỗi node và phối hợp shutdown; không giả định mỗi node có một timeout độc lập.

## 18. Chọn timeout theo workload

Không chọn timeout bằng cách lấy một con số quá rộng cho tất cả job. Hãy dùng lịch sử runtime và business objective.

| Workload | Thời gian thường gặp | Timeout minh họa |
|---|---:|---:|
| Validate một file | 1–3 phút | 5 phút |
| Transform một partition | 5–20 phút | 30 phút |
| Render một scene | 20–90 phút | 2 giờ |
| Train một model | 2–6 giờ | 8 giờ |
| Batch reconciliation | 15–45 phút | 1 giờ |

Các giá trị là ví dụ, không phải AWS defaults. Dùng p95/p99 runtime, input size và thời gian cleanup để chọn timeout. Nếu workload có nhiều loại input, tách job queues/job definitions hoặc dùng timeout override phù hợp khi submit.

Timeout quá ngắn gây false failure và mất compute đã sử dụng. Timeout quá dài làm job treo giữ capacity và trì hoãn phát hiện sự cố.

## 19. Xử lý SIGTERM và checkpoint

Ứng dụng nên bắt SIGTERM để:

1. Ngừng nhận thêm work units.
2. Flush dữ liệu đã hoàn tất.
3. Ghi checkpoint hoặc progress marker.
4. Đóng file và connection.
5. Ghi log trạng thái dừng.
6. Thoát trong khoảng thời gian shutdown cho phép.

Ví dụ Python:

~~~python
import signal
import sys

shutdown_requested = False

def handle_sigterm(signum, frame):
    global shutdown_requested
    shutdown_requested = True

signal.signal(signal.SIGTERM, handle_sigterm)

for item in load_work_items():
    if shutdown_requested:
        save_checkpoint()
        flush_outputs()
        sys.exit(143)

    process(item)

flush_outputs()
~~~

Trong production, save_checkpoint() phải ghi trạng thái bền vững và có tính idempotent. Đừng chỉ lưu index trong memory. Nếu công việc không thể resume, hãy bảo đảm partial outputs không được publish và lần chạy mới có thể bắt đầu an toàn.

## 20. Retry và timeout tương tác thế nào?

| Tình huống | Kết quả |
|---|---|
| Application exit non-zero, còn attempts | Có thể retry theo evaluateOnExit |
| Application exit 0 | SUCCEEDED, không retry |
| Timeout hết hạn | Batch terminate attempt, job FAILED, không tự retry |
| User cancel/terminate | Không retry tự động |
| Job definition không hợp lệ | Không retry |
| Dependency job retry rồi thành công | Downstream tiếp tục sau khi upstream SUCCEEDED |
| Dependency job hết retry và FAILED | Dependent job tự FAILED |

Nếu muốn timeout dẫn tới một lần thử lại có kiểm soát, không thể chỉ bật attempts rồi kỳ vọng Batch retry timeout. Hãy để workflow orchestrator phát hiện trạng thái timeout/failure và quyết định có submit một job mới, thay đổi resource hoặc thay đổi timeout hay không.

Không tạo vòng lặp submit vô hạn từ EventBridge khi job liên tục timeout. Dùng retry budget, maximum workflow duration và failure route.

## 21. Dùng AWS Step Functions để điều phối Batch

Native Batch dependencies phù hợp với DAG đơn giản. Step Functions phù hợp khi workflow cần:

- Branching theo kết quả.
- Retry với interval/backoff.
- Catch lỗi và chạy compensation.
- Chờ phê duyệt hoặc timer.
- Parallel/Map processing và tổng hợp kết quả.
- Lưu workflow state và theo dõi execution history.

Với service integration arn:aws:states:::batch:submitJob.sync, Step Functions đợi Batch job hoàn tất trước khi chuyển sang state tiếp theo.

Ví dụ Task state:

~~~json
{
  "RunPreprocess": {
    "Type": "Task",
    "Resource": "arn:aws:states:::batch:submitJob.sync",
    "Parameters": {
      "JobName": "preprocess-dataset",
      "JobQueue": "arn:aws:batch:ap-southeast-1:111122223333:job-queue/research-queue",
      "JobDefinition": "arn:aws:batch:ap-southeast-1:111122223333:job-definition/preprocess:4"
    },
    "Next": "RunCompute"
  }
}
~~~

Có thể dùng Retry và Catch ở Task state. Hãy phân biệt:

- Batch retry: chạy lại attempt trong cùng một Batch job ID.
- Step Functions retry: gọi lại service integration, có thể submit một Batch job mới.
- Application retry: thử lại một API/request bên trong cùng container.

Nếu bật cả ba lớp, số lần thực thi thực tế có thể nhân lên. Tính retry budget tổng và bảo đảm mọi side effect idempotent.

## 22. Array job và Step Functions Map

Array jobs thích hợp khi nhiều child chạy cùng một job definition và khác nhau chủ yếu ở input index. Step Functions Map phù hợp khi từng item cần orchestration state riêng, branching, retry/catch riêng hoặc input khác cấu trúc.

| Tiêu chí | AWS Batch Array Job | Step Functions Map |
|---|---|---|
| Work units | Cùng job definition, phân biệt bằng array index | Mỗi item có thể mang input riêng |
| Orchestration | Native Batch scheduler | State machine |
| Dependency | SEQUENTIAL/N_TO_N | State transitions, Map/Parallel |
| Retry | Retry strategy theo job/child | Retry theo Task/Map item |
| Error branch | Chủ yếu FAILED/SUCCEEDED | Catch, Choice, compensation |
| Theo dõi | Batch job/child states | Workflow execution và state history |

Có thể kết hợp cả hai: Step Functions điều phối các stage lớn, mỗi stage submit một array job cho workload embarrassingly parallel.

## 23. Capacity, concurrency và resource-aware scheduling

Array size 10.000 không có nghĩa compute environment phải chạy 10.000 containers đồng thời. Scheduler đặt job vào RUNNABLE khi dependencies đã thỏa; sau đó chỉ cấp host khi đủ vCPU, memory, GPU và capacity.

Để tránh queue overload:

- Chọn vCPU/memory requests sát workload.
- Đặt compute environment maximum vCPUs phù hợp budget.
- Dùng nhiều queues hoặc fair-share scheduling khi workload có priority khác nhau.
- Giới hạn array size hoặc chia wave nếu downstream không chịu được burst.
- Dùng consumable resources/resource-aware scheduling cho tài nguyên dùng chung như license, GPU slot hoặc quota nội bộ.
- Đặt concurrency limit ở downstream APIs/database.
- Theo dõi queue head và RUNNABLE reasons.

Resource-aware scheduling có thể tính các consumable resources vào quyết định schedule trên FIFO/fair-share policies và các compute platforms được hỗ trợ. Nó giúp tránh cấp job khi tài nguyên logic cần thiết chưa sẵn sàng.

## 24. Observability: Batch metrics trong CloudWatch

AWS Batch phát metrics trong namespace AWS/Batch, với dimension JobQueueName. Từ 06/10/2026, AWS công bố native job state-transition và duration metrics để theo dõi queue health, failures và thời gian trong từng state.

| Metric | Ý nghĩa | Cách sử dụng |
|---|---|---|
| JobsSubmitted | Số jobs được submit | Theo dõi volume đầu vào |
| JobsMovedToPending | Jobs chuyển sang PENDING | Tìm dependency/resource wait |
| JobsMovedToRunnable | Jobs chuyển sang RUNNABLE | Theo dõi readiness/retry |
| JobsMovedToStarting | Jobs chuyển sang STARTING | Đo khả năng cấp host |
| JobsMovedToRunning | Jobs bắt đầu chạy | Theo dõi throughput |
| JobsMovedToSucceeded | Jobs hoàn tất thành công | Theo dõi success rate |
| JobsMovedToFailed | Jobs chuyển FAILED | Theo dõi failures |
| JobsRetried | Attempts được retry | Phát hiện retry storm |
| JobSubmittedToRunnableDuration | Thời gian từ submit tới RUNNABLE | Đo dependency wait |
| JobAttemptRunnableToStartingDuration | Thời gian RUNNABLE tới STARTING | Đo capacity wait |
| JobAttemptStartingToRunningDuration | Thời gian khởi tạo container | Đo image pull/init overhead |
| JobAttemptExecutionDuration | Thời gian attempt ở RUNNING | Theo dõi runtime |
| JobAttemptDuration | Thời gian attempt từ STARTING đến kết thúc | Đo tổng attempt duration |

Metrics được phát theo sự kiện và theo best-effort; đôi khi state transition rất nhanh có thể không tạo đủ datapoints. Dùng metrics cho monitoring và baseline, không dùng làm nguồn kiểm toán chính xác hoặc đối soát billing.

JobAttemptRunnableToStartingDuration và JobSubmittedToFirstStartingDuration áp dụng cho AWS Batch compute jobs. Service jobs có nhóm metrics riêng quanh trạng thái SCHEDULED. JobsMovedToFailed cũng bao gồm các job bị cancel hoặc terminate, vì vậy cần đối chiếu DescribeJobs/EventBridge khi phân tích failure rate.

Với array jobs, JobsSubmitted được phát ở parent với giá trị bằng array size; các state/duration metrics khác được phát theo child jobs. Không cộng parent và child như thể chúng là hai nhóm job riêng.

## 25. EventBridge và job state change events

AWS Batch gửi Batch Job State Change events tới EventBridge khi job đã submit chuyển trạng thái. Có thể route events tới Lambda, SNS, SQS hoặc Step Functions để:

- Thông báo job FAILED.
- Khởi chạy bước tiếp theo khi job SUCCEEDED.
- Ghi audit record.
- Tạo báo cáo runtime.
- Khởi chạy workflow xử lý dữ liệu lỗi.

EventBridge delivery có thể có duplicate; consumer nên idempotent theo event ID hoặc job ID + state + timestamp. Không giả định có event cho lần submit đầu tiên.

Ví dụ event pattern cho job thất bại:

~~~json
{
  "source": ["aws.batch"],
  "detail-type": ["Batch Job State Change"],
  "detail": {
    "status": ["FAILED"]
  }
}
~~~

Có thêm Batch Job Queue Blocked events khi Batch phát hiện một job RUNNABLE ở đầu queue đang chặn queue. Event và statusReason trong DescribeJobs giúp phân biệt capacity, misconfiguration và invalid compute environment.

## 26. Logs và lịch sử attempts

Mặc định logs của Batch jobs được gửi vào CloudWatch Logs log group:

~~~text
/aws/batch/job
~~~

Stream name có thể lấy qua DescribeJobs; định dạng hiện hành thường gồm tên job definition, default và ECS task ID. Không hard-code tên stream nếu API có thể trả chính xác.

Khi điều tra job thất bại, xem:

- statusReason.
- attempts[] và từng attempt's container exit code.
- startedAt, stoppedAt.
- container.reason.
- logStreamName.
- AWS_BATCH_JOB_ATTEMPT.
- AWS_BATCH_JOB_ARRAY_INDEX nếu là array child.
- Input/output manifest và workflow ID.

Thiết lập CloudWatch Logs retention phù hợp. Logs mặc định có thể được giữ vô thời hạn nếu không đặt retention; tránh lưu dữ liệu nhạy cảm trong stdout/stderr.

## 27. Troubleshooting dependency và array jobs

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Job ở PENDING lâu | Dependency chưa SUCCEEDED | DescribeJobs upstream và xem status/attempts |
| Downstream thành FAILED ngay | Một dependency thất bại | Kiểm tra job ID và lỗi upstream |
| Array child không chạy | Parent/dependency chưa thỏa hoặc queue thiếu capacity | Xem child state và queue metrics |
| Parent array ở PENDING | Children đang được xử lý | Xem child IDs; parent không phải container |
| Một child lỗi làm parent FAILED | Child exhausted retries/cancelled | Xác định index và rerun partition |
| SEQUENTIAL chạy rất lâu | Mỗi child chờ child trước | Chỉ dùng khi thật sự cần thứ tự |
| N_TO_N child chờ | Corresponding upstream index chưa thành công | So sánh array parent IDs và child indexes |
| Array children ghi đè output | Output path dùng chung | Tách theo workflow ID và array index |
| Array tạo nhiều jobs nhưng ít chạy song song | Compute capacity/quotas thấp | Kiểm tra RUNNABLE, vCPU/memory và CE |
| Cancel parent nhưng children dừng | Hành vi cascade theo thiết kế | Chỉ cancel parent khi muốn dừng toàn array |

## 28. Troubleshooting retry và timeout

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Job retry tới 10 lần | attempts đặt cao hoặc lỗi luôn match RETRY | Phân loại exit code/reason và thêm catch-all EXIT |
| Job không retry sau cancel | Cancelled/terminated không được retry | Dùng orchestrator nếu cần submit job mới |
| Job timeout rồi FAILED | Timeout termination không tự retry | Điều chỉnh timeout hoặc xử lý ở Step Functions |
| Job dừng đúng ngưỡng nhưng cleanup chưa xong | SIGTERM handler không flush kịp | Checkpoint sớm, shutdown gọn, tăng timeout |
| Job bị SIGKILL | Không thoát trong 30 giây sau SIGTERM | Giảm thời gian cleanup và lưu progress thường xuyên |
| Job retry tạo duplicate | Side effect đã commit trước khi attempt chết | Idempotency key, staging và conditional commit |
| Job retry mãi vì permission error | AccessDenied bị phân loại RETRY | Chuyển sang EXIT, sửa IAM/resource policy |
| Job vượt timeout trước khi chạy được | Nhầm thời gian STARTING là timeout | Batch timeout bắt đầu khi RUNNING; theo dõi start duration riêng |
| Fargate job dừng gần 14 ngày | Giới hạn thời gian khả dụng của Fargate resources | Chia workload thành checkpoints/stages ngắn hơn |
| Step Functions tạo quá nhiều job | Retry của state machine nhân với Batch attempts | Tính tổng retry budget và dùng idempotency |

## 29. Case study: pipeline mô phỏng Monte Carlo

Một nhóm nghiên cứu cần chạy 4.000 mô phỏng với cùng một image và job definition. Mỗi mô phỏng nhận seed khác nhau, ghi kết quả vào S3. Sau khi tất cả hoàn tất, một job aggregate tính percentile và publish báo cáo.

### Thiết kế

1. Job prepare-input xác thực dataset và tạo manifest có 4.000 seeds.
2. Array job simulate có size 4.000; mỗi child đọc seed tại AWS_BATCH_JOB_ARRAY_INDEX.
3. Mỗi child ghi vào output path theo runId/index.
4. Job aggregate phụ thuộc array parent và chỉ chạy khi array thành công.
5. Job publish phụ thuộc aggregate và validation.

~~~mermaid
flowchart TD
    A["prepare-input"] --> B["simulate array: 4,000 children"]
    B --> C["aggregate"]
    C --> D["validate report"]
    D --> E["publish"]
~~~

### Retry và timeout

- Simulation attempt có timeout 45 phút dựa trên p99 runtime.
- Retry 3 attempts cho host/agent failures.
- Input validation errors exit ngay.
- Mỗi child ghi checkpoint và output có thể xác minh lại.
- Aggregate kiểm tra đủ 4.000 partitions trước khi tính kết quả.

### Quan sát

- JobsMovedToPending đo thời gian chờ prepare dependency.
- JobsMovedToRunnable và JobAttemptRunnableToStartingDuration cho biết capacity wait.
- JobsRetried phát hiện transient infrastructure errors.
- JobAttemptExecutionDuration xác định các seed có runtime bất thường.
- EventBridge báo FAILED child để điều tra index cụ thể.

### Bài học

Array job giúp gửi một workload lớn bằng một submission. Nhưng kết quả chỉ đáng tin khi mỗi child có input/output mapping ổn định, retry idempotent và bước aggregate xác minh completeness trước publish.

## 30. Lab: dependency, array, retry và timeout

Lab dùng AWS sandbox có sẵn job queue, compute environment và quyền batch:SubmitJob, batch:DescribeJobs, batch:ListJobs. Không dùng queue production. Thay queue, Region và job definition bằng tài nguyên sandbox đã được cấp.

### Bước 1: đăng ký job definition có retry và timeout

Tạo file partition-job.json:

~~~json
{
  "jobDefinitionName": "partition-worker-lab",
  "type": "container",
  "platformCapabilities": ["EC2"],
  "containerProperties": {
    "image": "public.ecr.aws/docker/library/python:3.12",
    "command": [
      "python",
      "-c",
      "import os,time; print('index=',os.getenv('AWS_BATCH_JOB_ARRAY_INDEX')); time.sleep(5)"
    ],
    "resourceRequirements": [
      {
        "type": "VCPU",
        "value": "1"
      },
      {
        "type": "MEMORY",
        "value": "1024"
      }
    ]
  },
  "retryStrategy": {
    "attempts": 3,
    "evaluateOnExit": [
      {
        "action": "RETRY",
        "onReason": "AGENT"
      },
      {
        "action": "EXIT",
        "onReason": "*"
      }
    ]
  },
  "timeout": {
    "attemptDurationSeconds": 300
  }
}
~~~

Đăng ký:

~~~bash
aws batch register-job-definition \
  --cli-input-json file://partition-job.json \
  --region ap-southeast-1
~~~

Image và command chỉ là ví dụ. Trong sandbox, dùng image đã được phép pull và kiểm tra compute platform tương thích.

### Bước 2: submit một job

~~~bash
aws batch submit-job \
  --job-name partition-single-lab \
  --job-queue lab-queue \
  --job-definition partition-worker-lab \
  --region ap-southeast-1
~~~

Ghi lại job ID và xem trạng thái bằng DescribeJobs.

### Bước 3: submit array job

~~~bash
aws batch submit-job \
  --job-name partition-array-lab \
  --job-queue lab-queue \
  --job-definition partition-worker-lab \
  --array-properties size=10 \
  --region ap-southeast-1
~~~

Kiểm tra parent job và children. Xác nhận AWS_BATCH_JOB_ARRAY_INDEX lần lượt từ 0 tới 9.

### Bước 4: thử SEQUENTIAL dependency

Tạo sequential-dependency.json:

~~~json
[
  {
    "type": "SEQUENTIAL"
  }
]
~~~

Submit array khác với --depends-on file://sequential-dependency.json. Quan sát child index tiếp theo chỉ chuyển sang chạy sau khi child trước thành công.

### Bước 5: thử dependency thông thường

Submit job A, lưu ID. Tạo depends-on.json với job ID đó rồi submit job B. Quan sát B ở PENDING, sau đó chuyển RUNNABLE khi A thành công.

### Bước 6: quan sát retry

Dùng một test image/script có thể cố ý exit non-zero trong lần đầu và thành công ở lần sau. Xem attempts, AWS_BATCH_JOB_ATTEMPT và metric JobsRetried. Không dùng test lỗi này trên production queue.

### Bước 7: quan sát timeout

Dùng job test có command chạy lâu hơn timeout 60 giây. Kiểm tra SIGTERM handler, status reason và xác nhận timeout termination không được retry tự động.

### Bước 8: cleanup

Xác nhận mọi test jobs đã kết thúc. Không xóa job queue hoặc compute environment dùng chung. Chỉ deregister job definition revision hoặc xóa tài nguyên lab riêng nếu được phép và không còn job tham chiếu.

## 31. Best practices

### Dependency và orchestration

- Thiết kế DAG nhỏ, có tên stage rõ ràng.
- Dùng native dependencies khi chỉ cần upstream SUCCEEDED.
- Dùng Step Functions khi cần branch, catch, wait, approval hoặc compensation.
- Không tạo dependency quá sâu nếu có thể gom stage.
- Xác minh output trước khi downstream chạy.
- Có failure route và người chịu trách nhiệm xử lý.

### Array jobs

- Dùng array cho workload độc lập và cùng job definition.
- Giữ mapping index-to-input ổn định.
- Tách output path theo run ID và array index.
- Chọn array size theo queue capacity và downstream limits.
- Dùng SEQUENTIAL chỉ khi bắt buộc có thứ tự.
- Dùng N_TO_N cho stage tương ứng theo index.
- Theo dõi child jobs thay vì chỉ parent status.

### Retry và idempotency

- Mặc định chỉ retry lỗi transient.
- Dùng evaluateOnExit để phân biệt RETRY và EXIT.
- Thêm catch-all rule EXIT khi muốn tránh default retry cho lỗi chưa phân loại.
- Đặt retry budget tổng giữa Batch, application và Step Functions.
- Dùng idempotency key ổn định qua mọi attempts.
- Không retry permission/schema/business validation errors.
- Có failure workflow cho job hết attempts.

### Timeout và graceful shutdown

- Chọn timeout dựa trên p95/p99 runtime và cleanup.
- Nhớ timeout bắt đầu ở RUNNING, không phải SUBMITTED/STARTING.
- Bắt SIGTERM, checkpoint và flush output.
- Giữ shutdown trong 30 giây trước SIGKILL.
- Tách job dài thành checkpointable stages khi cần.
- Không kỳ vọng timeout termination được retry tự động.
- Tính giới hạn thực tế của Fargate với workload dài ngày.

### Monitoring

- Theo dõi queue wait, capacity wait, startup và execution duration riêng.
- Theo dõi JobsRetried, JobsMovedToFailed và JobsMovedToSucceeded.
- Dùng EventBridge state-change và queue-blocked events.
- Dùng DescribeJobs cho statusReason/attempt history.
- Cấu hình CloudWatch Logs retention.
- Không dùng best-effort metrics làm audit ledger.
- Đối soát output manifest để xác định completeness.

## 32. Bài tập tự luyện

1. Dependency trong AWS Batch được thỏa khi upstream ở trạng thái nào?
2. Một job có thể khai báo tối đa bao nhiêu dependencies?
3. Nếu một dependency thất bại, dependent job sẽ ở trạng thái nào?
4. PENDING khác RUNNABLE thế nào?
5. Vì sao job RUNNABLE vẫn có thể chưa chạy?
6. Array job hỗ trợ bao nhiêu children?
7. AWS_BATCH_JOB_ARRAY_INDEX bắt đầu từ số nào?
8. Array parent có phải container chạy workload không?
9. SEQUENTIAL dependency hoạt động thế nào?
10. N_TO_N dependency ánh xạ child jobs ra sao?
11. Khi nào không nên dùng SEQUENTIAL?
12. Điều gì xảy ra nếu cancel parent array job?
13. Điều gì xảy ra nếu một child array job thất bại?
14. attempts: 4 nghĩa là bao nhiêu lần chạy tối đa?
15. AWS_BATCH_JOB_ATTEMPT bắt đầu từ số nào?
16. evaluateOnExit dùng để phân loại những loại lỗi nào?
17. Nếu không có rule nào match, AWS Batch làm gì?
18. Vì sao nên có catch-all EXIT?
19. Những lỗi nào không được retry theo retry strategy thông thường?
20. Vì sao retry cần idempotency?
21. attemptDurationSeconds tối thiểu là bao nhiêu?
22. Timeout bắt đầu tính từ trạng thái nào?
23. AWS Batch gửi signal nào khi timeout?
24. Sau bao lâu không thoát thì container nhận SIGKILL?
25. Timeout termination có tự retry không?
26. Fargate jobs nên giới hạn thời gian thực tế thế nào?
27. Timeout của array parent và children khác nhau ra sao?
28. Retry của AWS Batch khác retry của Step Functions thế nào?
29. batch:submitJob.sync giúp gì trong Step Functions?
30. Metric nào đo thời gian job chờ từ RUNNABLE tới STARTING?
31. EventBridge có thể phát sự kiện nào khi queue bị blocked?
32. Vì sao không dùng CloudWatch metrics best-effort làm nguồn audit chính xác?

### Gợi ý đáp án

1. Khi upstream SUCCEEDED.
2. Tối đa 20.
3. Tự chuyển FAILED.
4. PENDING còn chờ dependency/resource; RUNNABLE đã sẵn sàng nhưng chờ scheduler cấp capacity.
5. Compute environment thiếu vCPU/memory/GPU, quota hoặc queue policy chưa cấp được host.
6. Từ 2 đến 10.000.
7. 0.
8. Không; parent là handle quản lý children.
9. Child index kế tiếp chờ child index trước thành công.
10. Child i của array sau chờ child i của array trước.
11. Khi workload độc lập và cần parallelism.
12. Tất cả children bị cancel/terminate cùng parent.
13. Parent cuối cùng thành FAILED sau khi children kết thúc.
14. Tối đa bốn attempts, gồm lần đầu.
15. 1.
16. Exit code, reason và status reason.
17. Job được retry nếu còn attempts.
18. Để lỗi chưa phân loại không mặc định retry.
19. Cancelled, terminated, invalid job definition và timeout termination.
20. Attempt trước có thể đã commit side effect rồi mới crash.
21. 60 giây.
22. Khi attempt bắt đầu RUNNING.
23. SIGTERM.
24. 30 giây.
25. Không.
26. Không kỳ vọng Fargate job chạy quá 14 ngày.
27. Parent array không có timeout; timeout áp dụng từng child.
28. Batch retry attempt trong cùng job ID; Step Functions retry có thể submit job mới.
29. Workflow chờ Batch job hoàn tất rồi mới sang state tiếp theo.
30. JobAttemptRunnableToStartingDuration.
31. Batch Job Queue Blocked.
32. Vì state-transition metrics được phát best-effort và có thể thiếu datapoint.

## 33. Câu hỏi phỏng vấn

### Dependency có giống queue priority không?

Không. Dependency quyết định một job có đủ điều kiện logic để chạy hay chưa. Priority quyết định thứ tự scheduling giữa các jobs đủ điều kiện trong queue policy.

### Tại sao job PENDING không phải lúc nào cũng là lỗi?

Nó có thể đang chờ một upstream job hợp lệ hoặc một resource dependency. Cần xem dependency graph và thời gian chờ trước khi can thiệp.

### Khi nào dùng array job thay cho gửi nhiều SubmitJob requests?

Khi nhiều work units dùng chung job definition và có thể phân biệt bằng index/parameters. Array giảm số lần submit và cung cấp parent/child tracking.

### Vì sao retry timeout không tự động?

AWS Batch timeout termination được thiết kế để dừng attempt quá thời gian và không tự retry. Nếu muốn chạy lại với timeout/resource khác, orchestrator cần quyết định submit job mới.

### Làm sao ngăn retry tạo duplicate output?

Dùng stable run ID + array index, idempotent writes, conditional commit và staging output. Chỉ publish khi validation hoàn tất.

### Vì sao cần phân biệt Batch retry và Step Functions retry?

Batch retry chạy lại container attempt của cùng job. Step Functions retry Task có thể gọi SubmitJob lần nữa và tạo job ID mới. Kết hợp cả hai mà không tính retry budget có thể nhân số lần thực thi.

### Timeout có tính thời gian pull container image không?

Không. Timeout bắt đầu từ RUNNING; image pull và khởi tạo nằm trong STARTING. Theo dõi startup duration riêng.

### Array parent FAILED có nghĩa mọi child đều thất bại không?

Không. Chỉ cần một child thất bại thì parent cuối cùng có thể FAILED sau khi các children hoàn tất. Phải xem trạng thái từng child để biết phần nào thành công.

### CloudWatch metrics có đủ để kiểm toán số jobs không?

Không. Metrics là best-effort và có thể thiếu transition datapoints. Dùng Batch APIs, EventBridge events được lưu bền vững và output manifests cho audit/reconciliation.

### Khi nào nên chuyển DAG từ native dependencies sang Step Functions?

Khi cần branch theo kết quả, Catch/Retry/Wait, human approval, compensation, Map/Parallel state hoặc lịch sử workflow đầy đủ.

## 34. Checklist production

### Dependency và workflow

- [ ] DAG không có bước phụ thuộc không cần thiết.
- [ ] Mỗi job có input/output contract rõ.
- [ ] Downstream chỉ chạy sau upstream success.
- [ ] Có nhánh xử lý upstream failure.
- [ ] Output được validation trước khi publish.
- [ ] Workflow/run ID được truyền qua mọi stages.

### Array jobs

- [ ] Array size nằm trong giới hạn 2–10.000.
- [ ] AWS_BATCH_JOB_ARRAY_INDEX được dùng để ánh xạ input.
- [ ] Output path tách theo run ID và child index.
- [ ] Concurrency phù hợp queue capacity và downstream limits.
- [ ] SEQUENTIAL/N_TO_N được chọn đúng semantics.
- [ ] Có cách xác định và rerun riêng child thất bại.

### Retry và idempotency

- [ ] attempts phản ánh retry budget.
- [ ] evaluateOnExit phân biệt lỗi transient và permanent.
- [ ] Có catch-all rule phù hợp.
- [ ] Cancel/terminate/timeout không bị kỳ vọng tự retry.
- [ ] Side effects idempotent xuyên mọi attempts.
- [ ] Batch và Step Functions retry không nhân vượt budget.
- [ ] Có failure route cho jobs hết attempts.

### Timeout và shutdown

- [ ] Timeout tối thiểu 60 giây và phù hợp p95/p99 runtime.
- [ ] Timeout được hiểu là bắt đầu khi RUNNING.
- [ ] Ứng dụng bắt SIGTERM và lưu checkpoint.
- [ ] Cleanup hoàn tất trong khoảng grace period.
- [ ] Fargate duration được thiết kế dưới giới hạn thực tế.
- [ ] Array child/MNP timeout semantics đã được xác nhận.

### Observability và operations

- [ ] CloudWatch dashboards theo JobQueueName.
- [ ] Theo dõi queue wait, capacity wait, startup và execution.
- [ ] Theo dõi retries, failures và timeout.
- [ ] EventBridge state change và queue blocked events có consumer idempotent.
- [ ] Logs có retention và không chứa secrets.
- [ ] Runbook có DescribeJobs, attempts và statusReason.
- [ ] Output manifests có completeness/checksum validation.
- [ ] Có owner và escalation cho failed jobs.

## 35. Tài liệu tham khảo chính thức

- [AWS Batch job dependencies](https://docs.aws.amazon.com/batch/latest/userguide/job_dependencies.html)
- [AWS Batch array jobs](https://docs.aws.amazon.com/batch/latest/userguide/array_jobs.html)
- [Use the array job index to control job differentiation](https://docs.aws.amazon.com/batch/latest/userguide/array_index_example.html)
- [Automated job retries](https://docs.aws.amazon.com/batch/latest/userguide/job_retries.html)
- [EvaluateOnExit API](https://docs.aws.amazon.com/batch/latest/APIReference/API_EvaluateOnExit.html)
- [AWS Batch job timeouts](https://docs.aws.amazon.com/batch/latest/userguide/job_timeouts.html)
- [AWS Batch job states](https://docs.aws.amazon.com/batch/latest/userguide/job_states.html)
- [AWS Batch SubmitJob API](https://docs.aws.amazon.com/batch/latest/APIReference/API_SubmitJob.html)
- [AWS Batch job definition parameters](https://docs.aws.amazon.com/batch/latest/userguide/job_definition_parameters.html)
- [AWS Batch job queue blocked events](https://docs.aws.amazon.com/batch/latest/userguide/batch-job-queue-blocked-events.html)
- [AWS Batch event stream for EventBridge](https://docs.aws.amazon.com/batch/latest/userguide/cloudwatch_event_stream.html)
- [AWS Batch job state change events](https://docs.aws.amazon.com/batch/latest/userguide/batch_job_events.html)
- [AWS Batch CloudWatch metrics](https://docs.aws.amazon.com/batch/latest/userguide/using_cloudwatch_metrics.html)
- [Jobs stuck in RUNNABLE status](https://docs.aws.amazon.com/batch/latest/userguide/job_stuck_in_runnable.html)
- [Resource-aware scheduling](https://docs.aws.amazon.com/batch/latest/userguide/resource-aware-scheduling.html)
- [Run AWS Batch workloads with Step Functions](https://docs.aws.amazon.com/step-functions/latest/dg/connect-batch.html)


