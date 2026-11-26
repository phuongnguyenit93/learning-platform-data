# Manager và worker tách deployment trong Spring Batch

## 1. Bài toán: một job, nhiều tiến trình triển khai

Một hệ thống phải xử lý hàng chục triệu bản ghi mỗi đêm. Khi chạy trên một JVM, việc tăng số thread cuối cùng sẽ gặp giới hạn CPU, heap, kết nối cơ sở dữ liệu hoặc băng thông mạng. Đội vận hành muốn **manager** điều phối job ở một nơi và chạy nhiều **worker** trên những máy hoặc container khác để tăng thông lượng, cô lập lỗi và mở rộng tài nguyên linh hoạt.

Đó là bối cảnh của bài **“Manager và worker tách deployment”**, thuộc chương **Triển khai** của module `SPRING_BATCH_SCALING_OPERATIONS`. Module hướng tới mở rộng Spring Batch cho workload dữ liệu lớn bằng multi-threaded step, parallel steps, partitioning và xử lý phân tán, đồng thời học cách đo nút thắt, bảo đảm thread safety, retry/restart và vận hành theo tài nguyên thực tế.

Kết thúc bài, bạn có thể:

- Phân biệt **tách deployment** với việc chỉ tách class hoặc tạo nhiều thread trong một JVM.
- Mô tả vòng đời **remote partitioning**: manager lập partition, worker nhận yêu cầu, thực thi step và báo kết quả.
- Thiết kế quyền truy cập `JobRepository`, message broker, cấu hình job và ranh giới dữ liệu để chạy nhiều instance an toàn.
- Quy hoạch triển khai bằng Kubernetes Job/Deployment, tài nguyên, secret, health check và quy trình phát hành phiên bản.
- Ứng phó với worker chết giữa chừng, message bị gửi lại, mất phản hồi, retry/restart và nhu cầu idempotency.
- Nhận biết khi nên dùng remote partitioning, remote chunking hoặc chỉ local partitioning.

**Phạm vi ví dụ:** Spring Batch 5.x trên Java 17+, Spring Batch Integration/Spring Integration và một message broker như RabbitMQ. Các cấu hình Kubernetes là minh họa về topology; tùy project và phiên bản thư viện, cần hoàn thiện wiring channel/adapter và các thuộc tính ứng dụng trước khi chạy.

## 2. Tách deployment nghĩa là gì?

Trong **local partitioning**, manager step và các worker step cùng chạy trong một JVM, thường qua `TaskExecutor`. Ở **remote partitioning**, manager và worker chạy trong các **tiến trình độc lập**, có thể nằm trên các node khác nhau. Chúng liên lạc bằng middleware; trạng thái điều phối và checkpoint gắn với metadata của Spring Batch.

| Thành phần | Vai trò khi triển khai riêng | Có cần truy cập? |
|---|---|---|
| **Manager service/process** | Khởi chạy job, xác định danh sách partition, phân phối yêu cầu thực thi và chờ tổng hợp kết quả | `JobRepository`, broker yêu cầu/phản hồi, nguồn lập partition |
| **Worker service/process** | Nhận yêu cầu, tải `StepExecution`, chạy đúng worker step, cập nhật trạng thái và phát phản hồi | `JobRepository`, broker, nguồn/đích dữ liệu phục vụ step |
| **Message broker** | Chuyển yêu cầu cho worker và phản hồi về manager; tách tốc độ xử lý giữa các tiến trình | Queue/topic, quyền publish/consume, chính sách durability và redelivery |
| **JobRepository** | Lưu `JobInstance`, `JobExecution`, `StepExecution` và `ExecutionContext` | Database metadata ổn định, cho manager và worker truy cập nhất quán |
| **Nguồn và đích dữ liệu** | Chứa dữ liệu nghiệp vụ được phân vùng xử lý | Kết nối/ủy quyền theo công việc, transaction và idempotency |
| **Scheduler/orchestrator** | Quyết định lúc nào khởi chạy manager, mở rộng worker và thu hồi instance | Kubernetes, scheduler doanh nghiệp hoặc cơ chế tương đương |

~~~mermaid
flowchart TB
    Scheduler[Scheduler / Kubernetes Job] --> Manager[Manager process<br/>Job + partition manager step]
    Manager -->|StepExecutionRequest| RequestQ[(Durable request queue)]
    RequestQ --> WorkerA[Worker pod A]
    RequestQ --> WorkerB[Worker pod B]
    RequestQ --> WorkerC[Worker pod C]
    WorkerA -->|StepExecution status / reply| ReplyQ[(Reply channel / queue)]
    WorkerB -->|StepExecution status / reply| ReplyQ
    WorkerC -->|StepExecution status / reply| ReplyQ
    ReplyQ --> Manager
    Manager <-->|Job/Step metadata| Repo[(Shared JobRepository DB)]
    WorkerA <-->|StepExecution, checkpoint| Repo
    WorkerB <-->|StepExecution, checkpoint| Repo
    WorkerC <-->|StepExecution, checkpoint| Repo
    WorkerA --> Data[(Business data)]
    WorkerB --> Data
    WorkerC --> Data
~~~

Sơ đồ mô tả phương án **remote partitioning có phản hồi qua middleware**. Có biến thể manager theo dõi trạng thái worker bằng cách polling metadata thay cho một reply channel tương đương. Chọn một cơ chế hoàn chỉnh và kiểm tra thời hạn chờ, trạng thái kết thúc, lỗi kết nối cũng như khả năng phục hồi của nó; không giả định mất reply là worker chưa xử lý dữ liệu.

### Phân biệt các cách song song hóa

| Mô hình | Ranh giới song song | Dùng khi |
|---|---|---|
| **Multi-threaded step** | Nhiều thread xử lý chunk trong cùng một step/JVM | Muốn tăng concurrency ở một bước, các component chia sẻ phải thread-safe |
| **Parallel steps/flows** | Các step/flow độc lập chạy cùng lúc | Các luồng công việc khác nhau không phụ thuộc thứ tự |
| **Local partitioning** | Nhiều `StepExecution` trong một JVM | Tập dữ liệu phân vùng được, một máy vẫn đủ tài nguyên |
| **Remote partitioning** | Nhiều `StepExecution` chạy trên các worker process | Cần mở rộng theo máy/pod; từng worker tự đọc/xử lý/ghi vùng dữ liệu của mình |
| **Remote chunking** | Manager đọc và tạo chunk; worker từ xa xử lý chunk | Muốn phân phối phần xử lý chunk, trong khi manager giữ logic đọc/định tuyến dữ liệu |

**Điểm mấu chốt:** remote partitioning phân phối *quyền thực thi một worker step với vùng dữ liệu được giao*; remote chunking phân phối *các chunk do manager tạo*. Hai mô hình có cách dùng broker, giới hạn throughput, checkpoint và yêu cầu dữ liệu khác nhau. Không xem chúng là hai tên gọi của cùng một topology.

## 3. Vòng đời một job remote partitioning

Giả sử job xử lý các đơn hàng có ID từ `1` đến `1.200.000`. Manager tạo 12 partition, mỗi partition có ranh giới và tên ổn định; sáu worker pod tiêu thụ các yêu cầu.

1. **Khởi chạy job:** scheduler gọi một manager với `JobParameters` nhận diện lần xử lý, ví dụ `businessDate=2026-11-26`. `JobRepository` cấp `JobExecution`.
2. **Lập kế hoạch partition:** `Partitioner` tạo các `ExecutionContext` mang các khoảng `minId`/`maxId`. Manager dùng tên partition nhất quán như `partition0` … `partition11` và lập metadata `StepExecution` tương ứng.
3. **Gửi yêu cầu:** manager phát thông tin định danh lần thực thi tới request queue. Với Spring Batch remote partitioning, message thường mang `StepExecutionRequest` (tên step, `jobExecutionId`, `stepExecutionId`), còn ranh giới dữ liệu nằm trong `ExecutionContext` đã lưu ở `JobRepository`.
4. **Nhận việc:** một worker lấy message, tìm `StepExecution` tương ứng và chạy worker step đã được đăng ký dưới đúng tên. Mỗi worker có thể nhận nhiều partition tuần tự hoặc đồng thời tùy giới hạn listener/executor.
5. **Đọc và ghi:** reader được tạo theo `@StepScope` lấy range của partition; các chunk commit và checkpoint theo `StepExecution` riêng.
6. **Hoàn tất/phản hồi:** worker cập nhật metadata và gửi trạng thái về manager theo cơ chế transport được cấu hình. Manager tổng hợp kết quả để quyết định step/job hoàn thành hay thất bại.
7. **Vận hành:** khi worker lỗi hoặc connection gián đoạn, manager phát hiện trạng thái không hoàn tất qua reply/polling/timeout, ghi nhận kết quả và cho phép restart job theo chính sách phù hợp.

~~~mermaid
sequenceDiagram
    participant S as Scheduler
    participant M as Manager
    participant R as JobRepository
    participant Q as Broker
    participant W as Worker
    participant D as Business DB
    S->>M: Start JobParameters
    M->>R: Create JobExecution + partition StepExecutions
    M->>Q: Dispatch StepExecutionRequest
    Q->>W: Deliver request
    W->>R: Load StepExecution + ExecutionContext
    W->>D: Read/process/write assigned range
    loop Every committed chunk
        W->>R: Save checkpoint/metrics
    end
    W->>R: Set worker step status
    W->>Q: Send completion/failure reply
    Q->>M: Deliver reply
    M->>R: Aggregate manager/job status
    M-->>S: Final job outcome
~~~

Khi thử nghiệm, nên đặt câu hỏi: *Nếu worker đã commit dữ liệu nhưng reply bị mất, manager sẽ biết điều gì?* Lúc này cần so sánh metadata từ `JobRepository` với giao thức phản hồi; không thể suy ra thất bại chỉ từ việc không nhận được reply đúng thời hạn.

## 4. Thiết kế hợp đồng manager–worker

Khi manager và worker chạy riêng, một message không chỉ là “lệnh chạy Java”. Nó phải ánh xạ tới một **lần thực thi xác định** và một phiên bản worker có thể hiểu kế hoạch công việc.

### Định danh và ranh giới

Các giá trị quan trọng trong luồng remote partitioning:

| Giá trị | Mục đích |
|---|---|
| `jobExecutionId` | Xác định lần thực thi job đang được quản lý |
| `stepExecutionId` | Xác định chính xác worker `StepExecution` và checkpoint tương ứng |
| `stepName` | Chọn cấu hình worker step phù hợp trong worker process |
| `partitionName` | Định danh ổn định của partition trong cùng manager step |
| `ExecutionContext` | Tham số partition, ví dụ `minId`/`maxId`, cutoff hoặc tên file |
| `JobParameters` | Xác định job instance/lần xử lý và các giá trị bất biến cần dùng khi restart |

Ví dụ bản ghi *minh họa logic* để quan sát vận hành (không phải JSON wire format bắt buộc của Spring Batch):

~~~yaml
jobExecutionId: 901
stepExecutionId: 930
stepName: processOrdersWorkerStep
partitionName: partition03
executionContext:
  minId: 300001
  maxId: 400000
  cutoffTime: "2026-11-26T00:00:00Z"
~~~

Với triển khai chuẩn dựa trên `StepExecutionRequest`, worker dùng ID và tên step để truy xuất metadata; **không tự tạo một `JobExecution` mới cho mỗi message**. Nếu bạn tự xây message transport, vẫn cần giữ định danh và lifecycle phù hợp với mô hình metadata của Spring Batch; tránh copy dữ liệu nghiệp vụ hoặc secret vào payload một cách tùy ý.

### Hợp đồng phải ổn định khi retry/restart

- Giữ nguyên tên worker step, định danh partition, quy tắc chia dữ liệu và cutoff của cùng một `JobInstance`.
- Tránh dùng “số worker đang chạy” làm tham số quyết định ranh giới dữ liệu nếu số worker có thể autoscale giữa chừng.
- Phân biệt **số partition** (độ chia nhỏ công việc) với **số worker** (capacity thực thi). 12 partition có thể được xử lý bởi 3, 6 hoặc 12 worker nếu broker và listener cho phép.
- Tính đến version compatibility khi rolling deploy: cùng một request có thể được worker image cũ hoặc mới nhận; thay đổi tên step, kiểu `ExecutionContext` hoặc schema dữ liệu phải có kế hoạch tương thích.
- Thiết kế bước xử lý **idempotent**; broker có thể gửi lại message, manager có thể restart, hoặc một worker có thể thất bại giữa commit dữ liệu và gửi reply.

**Tránh chia bằng các khoảng chỉ dựa trên `MAX(id)` thay đổi liên tục.** Nếu input nhận thêm bản ghi, nên chốt cutoff/snapshot theo từng lần chạy. Trong trường hợp dữ liệu được cập nhật trong lúc quét, cần bảo đảm reader không bị bỏ sót/nhảy vị trí vì chính writer sửa điều kiện lọc của reader.

## 5. Các thành phần Spring Batch cần cấu hình

Để tách tiến trình, một topology phổ biến dùng:

~~~text
Manager application:
  JobLauncher + Job + manager step
  Partitioner + partition handler / manager step builder
  Request output channel + optional reply input channel
  JobRepository + JobExplorer

Worker application:
  Worker step (reader, processor, writer)
  StepExecutionRequest handler / worker step integration
  Request input channel + optional reply output channel
  JobRepository + JobExplorer

Messaging infrastructure:
  outbound adapter -> durable request queue
  inbound adapter  <- durable request queue
  outbound reply / inbound reply hoặc metadata polling
~~~

### Phác thảo API của manager

Spring Batch Integration hỗ trợ `RemotePartitioningManagerStepBuilder` để xây partition manager step. Dưới đây là **khung cấu hình rút gọn**; các bean `requestChannel`/`replyChannel` phải nối với adapter transport phù hợp, và các API có thể khác nhau giữa các phiên bản Spring Batch:

~~~java
// Minh họa ý tưởng wiring trên Spring Batch 5.x.
// Cần khai báo các bean JobRepository, Partitioner,
// request/reply channel và message adapters.
Step managerStep = new RemotePartitioningManagerStepBuilder(
        "dispatchOrdersStep", jobRepository)
    .partitioner("processOrdersWorkerStep", orderPartitioner)
    .gridSize(12)
    .outputChannel(requestChannel)
    .inputChannel(replyChannel)
    .build();
~~~

`orderPartitioner` phải trả về `Map<String, ExecutionContext>` với các ranh giới không giao nhau. `gridSize(12)` là số partition mục tiêu mà manager yêu cầu, không phải số pod sẽ được tạo; số partition thực tế còn phụ thuộc cách cài `Partitioner`.

### Phác thảo API của worker

Worker đăng ký step có **tên khớp** với `processOrdersWorkerStep` mà manager yêu cầu. Sử dụng cấu hình worker của Spring Batch Integration, hoặc một flow Spring Integration xử lý `StepExecutionRequest` qua handler tương ứng; các thành phần phụ trợ giải quyết việc load `StepExecution` từ `JobRepository` và gửi kết quả theo transport.

~~~java
// Minh họa wiring worker, không phải một cấu hình ứng dụng hoàn chỉnh.
Step workerStep = new RemotePartitioningWorkerStepBuilder(
        "processOrdersWorkerStep", jobRepository)
    .inputChannel(requestChannel)
    .outputChannel(replyChannel)
    .<Order, Order>chunk(250, transactionManager)
    .reader(stepScopedReader)
    .processor(orderProcessor)
    .writer(orderWriter)
    .build();
~~~

Ở Spring Batch, reader có trạng thái, ví dụ `JdbcPagingItemReader` hoặc `FlatFileItemReader`, cần được tạo riêng cho mỗi `StepExecution`. Một bean reader singleton lưu con trỏ dùng chung giữa các partition có thể dẫn đến trùng/thiếu dữ liệu hoặc checkpoint hỏng. Cách phổ biến là dùng `@StepScope` và late binding:

~~~java
@Bean
@StepScope
public ItemReader<Order> stepScopedReader(
        @Value("#{stepExecutionContext['minId']}") Long minId,
        @Value("#{stepExecutionContext['maxId']}") Long maxId) {
    // Tạo reader mới và ràng buộc điều kiện truy vấn id BETWEEN minId AND maxId.
    // Với JdbcPagingItemReader, phải ORDER BY khóa ổn định, duy nhất.
    return createReaderForRange(minId, maxId);
}
~~~

Đoạn này chỉ minh họa contract; `createReaderForRange(...)` là hàm ứng dụng cần cài đặt. Đặc biệt, **tách deployment không tự làm reader, processor và writer trở nên thread-safe**. Worker có thể chạy nhiều partition đồng thời trong cùng một pod; các singleton không an toàn khi dùng chung vẫn phải được xử lý.

### Chọn cơ chế transport

| Thành phần | Yêu cầu tối thiểu |
|---|---|
| Request queue | Có cơ chế phân phối giữa nhiều consumer, durability phù hợp, xử lý ACK/redelivery và kiểm soát số message in-flight |
| Reply queue/channel | Định tuyến về đúng manager execution, tránh reply thất lạc hoặc bị tiêu thụ bởi manager không liên quan |
| Correlation | Gắn được kết quả với `StepExecution` đã gửi, kể cả khi có nhiều job chạy đồng thời |
| Serialization | Version và định dạng message tương thích với manager/worker cùng môi trường |
| Error channel / DLQ | Có cách quan sát request không xử lý được, timeout hoặc payload không hợp lệ; không coi DLQ là hoàn tất job |
| Message security | TLS, thông tin xác thực và quyền publish/consume tối thiểu theo role |

Broker cung cấp **at-least-once delivery** hoặc cơ chế redelivery thì worker cần ứng xử đúng với yêu cầu bị nhận lại. Việc ACK một message và commit transaction dữ liệu/`JobRepository` thường thuộc **các hệ thống transaction khác nhau**; không giả định exactly-once trên toàn bộ đường đi.

## 6. Chia vai trò vào các image và process

Có hai cách đóng gói:

**Một image, hai profile/role.** Cùng codebase chứa manager và worker nhưng dùng biến `APP_ROLE` để chọn bean và chế độ khởi chạy. Ưu điểm: giảm chênh lệch phiên bản; nhược điểm: image chứa cả các dependency mà một role không cần. Có thể dùng `@Profile("manager")` và `@Profile("worker")` cho bean đặc thù.

**Hai image độc lập.** Manager chỉ chứa code điều phối, worker chứa logic xử lý dữ liệu. Ưu điểm: cấp tài nguyên, quyền truy cập và lịch release riêng; nhược điểm: tăng yêu cầu quản lý compatibility, build và quan sát lỗi.

Với cả hai cách, nên giữ hợp đồng sau:

- Manager được phép **launch job**; worker chỉ xử lý yêu cầu remote partitioning. Worker khởi động không được vô tình chạy toàn bộ job do `spring.batch.job.enabled=true`.
- Mỗi worker có đủ cấu hình `JobRepository`, broker và data source cần thiết; không lưu state tiến độ chỉ trong bộ nhớ pod.
- Manager và worker dùng phiên bản schema metadata Spring Batch tương thích; migration schema cần được điều phối.
- Không để credential/database password vào source control, container image hoặc message. Sử dụng secret store, quyền truy cập phù hợp và cơ chế xoay vòng secret.
- Cấu hình log có `jobExecutionId`, `stepExecutionId`, partition, attempt và worker instance để truy vết.

Ví dụ cấu hình profile ứng dụng:

~~~yaml
# worker application.yml, minh họa cấu hình theo vai trò
spring:
  batch:
    job:
      enabled: false       # worker không tự launch toàn bộ Job lúc startup

app:
  role: worker
  messaging:
    request-queue: batch.orders.requests
    reply-queue: batch.orders.replies
  worker:
    consumer-concurrency: 2
~~~

Các khóa dưới `app.*` là **cấu hình tùy chỉnh của ứng dụng**, cần tự binding vào message adapter/listener. Chúng không tự động tạo Spring Integration flow hay RabbitMQ queue. Phần cấu hình hạ tầng như JDBC URL, credentials và queue declaration cần được bổ sung theo môi trường triển khai.

## 7. Mẫu triển khai trên Kubernetes

Một phương án thường gặp:

- Chạy **manager bằng Kubernetes Job** theo lịch của CronJob, workflow orchestrator hoặc tác vụ vận hành. Manager có điểm bắt đầu và kết thúc rõ ràng.
- Chạy **worker bằng Deployment** vì chúng có thể luôn chờ request và cần scale lên/xuống theo tải của queue.
- Dùng JobRepository DB và message broker được vận hành với độ bền dữ liệu phù hợp, tách vòng đời khỏi pod xử lý.

~~~mermaid
flowchart LR
    CJ[CronJob / Workflow] --> MJ[Kubernetes Job: manager]
    MJ --> MQ[(Request queue)]
    MQ --> WD[Deployment: workers]
    WD --> WP1[Pod worker-1]
    WD --> WP2[Pod worker-2]
    WD --> WPN[Pod worker-N]
    WP1 --> SQL[(JobRepository DB)]
    WP2 --> SQL
    WPN --> SQL
    MJ --> SQL
~~~

YAML rút gọn bên dưới minh họa **phân vai và giới hạn tài nguyên**; phần secret, service account, volumes và cấu hình môi trường thực tế cần được hoàn thiện:

~~~yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: orders-batch-manager-demo
spec:
  backoffLimit: 1
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: manager
          image: registry.example.com/orders-batch:1.2.3
          args: ["--spring.profiles.active=manager"]
          resources:
            requests: {cpu: "250m", memory: "512Mi"}
            limits: {cpu: "1", memory: "1Gi"}
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-batch-worker
spec:
  replicas: 4
  selector:
    matchLabels: {app: orders-batch-worker}
  template:
    metadata:
      labels: {app: orders-batch-worker}
    spec:
      containers:
        - name: worker
          image: registry.example.com/orders-batch:1.2.3
          args: ["--spring.profiles.active=worker",
                 "--spring.batch.job.enabled=false"]
          resources:
            requests: {cpu: "500m", memory: "768Mi"}
            limits: {cpu: "2", memory: "2Gi"}
~~~

**Lưu ý khi đưa vào thực tế:**

1. `backoffLimit` cho phép Kubernetes tạo pod manager mới sau thất bại, nhưng **không tự bảo đảm restart đúng `JobInstance` của Spring Batch**. Logic khởi chạy phải dùng `JobParameters` xác định và kiểm tra execution đang chạy/thất bại trước khi launch lại.
2. Khi dùng CronJob, `concurrencyPolicy: Forbid` có thể ngăn chồng lấn do **cùng CronJob**; nó không thay thế lock/điều phối ở mức toàn hệ thống nếu có người hoặc hệ thống khác cùng launch job instance.
3. Manager Job không nên exit thành công khi worker vẫn xử lý và chưa có kết quả cuối. Cần cấu hình timeout aggregation, lỗi transport, cancellation và tín hiệu exit code rõ ràng.
4. Worker Deployment có thể scale trong khi manager đang chạy. Hãy giữ partition plan ổn định và bảo đảm hệ thống vẫn có consumer cho queue khi scale xuống.
5. Kubernetes rolling update không đảm bảo worker đang xử lý có thể chạy hết một chunk trước khi bị dừng. Cần readiness/drain, `terminationGracePeriodSeconds`, shutdown hook và test stop/restart.
6. Với HPA/KEDA theo queue depth, đặt `minReplicaCount`, `maxReplicaCount`, cooldown và chính sách concurrency dựa trên DB/broker capacity; autoscaling không thay thế giới hạn tải.

### Sizing: số pod không bằng số partition

Giả sử manager tạo **40 partition**; mỗi pod nhận tối đa **2 yêu cầu đồng thời**, và chạy **5 pod**. Mức đồng thời lý thuyết là `5 × 2 = 10` worker step, dù có 40 partition. Những partition còn lại chờ. Nếu scale lên 8 pod, mức tối đa thành 16, nhưng DB connection pool và broker phải chịu thêm tải.

Để ước lượng ngân sách ban đầu:

\[
C_{\mathrm{workers}} =
\min\left(P_{\mathrm{partitions}},
N_{\mathrm{pods}}\times L_{\mathrm{perPod}}\right)
\]

Trong đó `P_partitions` là số partition, `N_pods` là số pod khỏe đang phục vụ queue, `L_perPod` là giới hạn số task đồng thời theo listener/executor. Con số này chỉ là **trần lý thuyết**, chưa phản ánh I/O, phân bố tải, giới hạn broker, thời gian start pod và tài nguyên thực tế.

Nếu mỗi partition đang xử lý có thể giữ một JDBC connection ở lúc chunk, cần dự trù tối thiểu sức chứa tương ứng **cho các tác vụ có thể đồng thời dùng DB**, cộng metadata `JobRepository`, health check và dự phòng. Pool size phía ứng dụng là **theo process/pod**; tổng áp lực lên DB phải tính trên toàn cụm, kể cả dịch vụ khác.

## 8. Retry, restart và lỗi phân tán

Tách deployment làm xuất hiện nhiều kiểu lỗi mà local partitioning ít gặp hơn:

| Tình huống | Điều gì có thể xảy ra | Hướng xử lý |
|---|---|---|
| Worker chết trước khi nhận request | Request còn trong durable queue và được consumer khác nhận, tùy chính sách broker | Xác minh redelivery/ACK và timeout manager; không bỏ sót partition |
| Worker chết giữa chunk | Chunk chưa commit có thể rollback, chunk đã commit còn nguyên; metadata có thể chưa kịp cập nhật | Dùng checkpoint, đảm bảo reader restartable, side effect idempotent |
| Worker commit dữ liệu nhưng chưa ACK request | Broker có thể giao lại cùng request | Chống thực thi trùng bằng trạng thái `StepExecution`, quản lý lease/duplicate và khóa nghiệp vụ |
| Worker hoàn thành nhưng reply thất lạc | Manager không có phản hồi mặc dù metadata đã hoàn tất | Đối soát `JobRepository`, reply correlation, timeout/polling phù hợp |
| Manager chết trong lúc worker đang chạy | Worker có thể tiếp tục chạy khi manager không còn | Khởi động lại đúng job instance, phục hồi/đối soát trạng thái; tránh chạy hai manager chồng nhau |
| Broker tạm mất kết nối | Request/reply chậm, client reconnect hoặc báo lỗi | Retry có giới hạn, backoff, giám sát queue, chính sách failure rõ ràng |
| Triển khai worker phiên bản mới giữa job | New worker có thể không hiểu payload hoặc schema cũ | Rolling compatibility, contract version hoặc tách queue theo phiên bản |

### “At least once” và idempotency

Trong mạng phân tán, không có một transaction đơn giản bao trùm broker, metadata DB, database nghiệp vụ và API bên ngoài. Một worker có thể thực hiện thành công rồi gặp lỗi khi gửi reply, dẫn đến request được thử lại.

Thiết kế step nên theo các nguyên tắc:

- Dùng khóa nghiệp vụ duy nhất và cập nhật có điều kiện/upsert để xử lý lặp không gây tác dụng phụ ngoài ý muốn.
- Nếu publish event hoặc gọi API không cùng transaction dữ liệu, cân nhắc **transactional outbox**, idempotency key, inbox/deduplication và xác nhận message thích hợp.
- Dùng `ExecutionContext` và tên `ItemStream` ổn định; với reader paging, sắp xếp theo khóa duy nhất và chốt tập input.
- Không tin vào việc “message được broker ACK” để kết luận kết quả nghiệp vụ đúng; cần đối soát số bản ghi, trạng thái step và side effect.
- Không tự động retry mọi lỗi. Sai cấu hình, dữ liệu hỏng hoặc schema không tương thích thường cần sửa nguyên nhân rồi restart có kiểm soát.

**Tránh tự chạy hai bản sao cùng một `StepExecution` song song.** Nếu broker redeliver trong khi worker cũ còn xử lý nhưng mất heartbeat/ACK, hai tiến trình có thể cùng gây side effect. Hệ thống cần cơ chế giới hạn thực thi, kiểm tra trạng thái/lease và khả năng nhận lại an toàn; với thay đổi nghiệp vụ quan trọng, ràng buộc idempotency ở đích là lớp bảo vệ cuối cùng.

### Restart đúng job instance

Giả sử job chạy với `businessDate=2026-11-26` và thất bại ở 3/12 partition. Khi restart cần dùng **cùng các identifying JobParameters**, giữ ranh giới/cutoff và cho Spring Batch dựa vào metadata để quyết định phần nào cần xử lý lại. Nếu tự đổi `run.id` hoặc business date để launch lại, có thể tạo job instance mới và khiến các partition hoàn tất trước đó cũng được xử lý lại.

Với partition đã `COMPLETED`, Spring Batch có thể bỏ qua khi restart theo cấu hình step và trạng thái metadata. Với partition lỗi, mức tiếp tục từ checkpoint phụ thuộc reader/writer, `ItemStream` và transaction. Không hứa “mỗi bản ghi được xử lý đúng một lần” chỉ bằng cách bật restart.

## 9. Observability, sức khỏe và quy trình vận hành

### Những chỉ số cần nhìn cùng lúc

| Tầng | Metric/log cần theo dõi | Câu hỏi chẩn đoán |
|---|---|---|
| Manager | Job/step duration, partition dự kiến/đã dispatch/COMPLETED/FAILED, timeout aggregation | Có partition nào bị kẹt hoặc thiếu reply? |
| Worker | Active worker step, throughput, `readCount`/`writeCount`, rollback, retry, skip, checkpoint age | Partition nào chạy chậm, dữ liệu lệch hoặc lỗi lặp? |
| Broker | Request/reply queue depth, unacked, redelivery, consumer count, DLQ, publish latency | Đang thiếu consumer hay broker bị nghẽn? |
| Database metadata | Lock wait, connection pool, failed update, thời gian đọc/ghi `StepExecution` | `JobRepository` có thành điểm nghẽn khi nhiều partition cùng checkpoint? |
| Database nghiệp vụ | SQL latency, row lock, deadlock, IOPS, connection wait | Thêm pod có gây tranh chấp ở bảng dữ liệu không? |
| Kubernetes/JVM | Pod restart, OOMKilled, CPU throttling, GC, readiness, termination | Worker chết vì hạ tầng hay vì dữ liệu? |
| Nghiệp vụ | Tổng record dự kiến/hoàn tất, trùng khóa/event, số record thiếu | Hệ thống có đúng dữ liệu sau restart không? |

Gắn correlation vào structured log để truy theo `jobName`, `jobExecutionId`, `stepName`, `stepExecutionId`, `partitionName`, `podName`. Với remote partitioning, log chỉ ở manager không đủ để hiểu lỗi SQL hoặc API tại worker.

### Health và readiness

**Liveness:** tiến trình và thành phần thiết yếu còn có khả năng hoạt động, nhưng không nên dựa vào một request dài để đánh dấu worker “chết”.

**Readiness:** chỉ nhận partition mới khi worker đã sẵn sàng với broker, configuration và các tài nguyên cần thiết. Khi shutdown, ngừng nhận request rồi để tác vụ hiện tại kết thúc hoặc dừng có kiểm soát theo thời hạn.

**Startup probe:** hữu ích khi ứng dụng khởi động chậm do JVM, migration ngoài tiến trình hoặc kết nối broker; tránh bị liveness giết trước khi sẵn sàng. Không dùng probe để tự động diễn giải trạng thái `COMPLETED` của một job.

### Runbook khi job đứng lâu

1. Từ `jobExecutionId`, xác định manager step và danh sách `StepExecution` chưa kết thúc; không chỉ nhìn số message trong queue.
2. Kiểm tra request queue: còn pending, unacked hay DLQ? Có bao nhiêu consumer khỏe?
3. Đối chiếu từng `stepExecutionId` với worker log, checkpoint timestamp và transaction DB. Tránh requeue thủ công trước khi biết worker có còn chạy.
4. Nếu worker không còn và metadata vẫn `STARTED`, áp dụng quy trình recovery của hệ thống: xác nhận không còn thực thi cũ, sửa trạng thái/khởi chạy lại bằng công cụ quản trị được kiểm soát.
5. Đo throughput và chờ I/O của DB/broker trước khi tăng replicas; partition lệch tải đôi khi không được giải quyết bằng thêm worker.
6. Sau restart, đối soát record và side effect để phát hiện thiếu/trùng; ghi rõ kết quả và nguyên nhân vào nhật ký vận hành.

## 10. Bảo mật và quản lý cấu hình giữa các deployment

Vì worker kết nối trực tiếp với broker, `JobRepository` và hệ thống nghiệp vụ, mỗi pod tạo thêm bề mặt truy cập.

- Dùng service account riêng cho manager/worker và quyền tối thiểu; nếu broker hỗ trợ ACL thì phân biệt quyền publish request, consume request và publish/consume reply.
- Dùng TLS/mTLS phù hợp cho broker và database, quản lý secret qua Kubernetes Secret hoặc secret manager, xoay vòng credential có kế hoạch.
- Giới hạn NetworkPolicy/egress tới các dịch vụ thực sự cần dùng; không mặc định mở đường mạng từ worker tới mọi hệ thống.
- Có giới hạn CPU/memory, maximum replicas, connection pools và retry; ngân sách tài nguyên phải tính tổng trên toàn cụm.
- Không gửi thông tin nhạy cảm hoặc toàn bộ dữ liệu nghiệp vụ qua `StepExecutionRequest` nếu worker có thể lấy dữ liệu trong vùng được cấp từ nguồn an toàn.
- Theo dõi schema/version cho Spring Batch metadata và message serialization, đặc biệt khi nâng cấp manager và worker độc lập.
- Chốt cấu hình job (cutoff, partitioning strategy, version thuật toán) gắn với job instance để vận hành và audit lại được.

## 11. Khi nào nên chọn tách deployment?

| Điều kiện | Gợi ý |
|---|---|
| Một máy còn nhiều CPU, RAM và DB chưa nghẽn | Bắt đầu bằng **local partitioning**; ít thành phần vận hành hơn |
| Workload chia vùng độc lập, dữ liệu lớn, cần scale worker theo pod/máy | **Remote partitioning** phù hợp |
| Manager cần đọc tập dữ liệu tập trung, muốn phân phối xử lý chunk, worker không tự chọn range | Cân nhắc **remote chunking** |
| Nguồn dữ liệu vốn chia shard/file độc lập, worker đọc được trực tiếp | Remote partitioning thường diễn đạt đúng đơn vị công việc |
| Database/third-party API đã bão hòa | Tối ưu truy vấn, giới hạn concurrency hoặc quota trước khi thêm worker |
| Cần phục hồi theo partition, theo dõi lỗi trên từng nhóm dữ liệu | Chọn thiết kế có `StepExecution` và checkpoint rõ ràng |
| Hạ tầng chưa có broker bền vững, JobRepository shared và công cụ quan sát | Ưu tiên mô hình đơn giản hơn cho tới khi đáp ứng điều kiện vận hành |

**Chi phí của việc tách deployment** là thêm network, broker, release coordination, trạng thái phân tán và lỗi truyền thông. Lợi ích là scale ngang theo tài nguyên thực tế, cô lập worker, đa dạng loại máy và triển khai workload lớn không phụ thuộc vào giới hạn của một JVM. Chỉ chọn khi phép đo và nhu cầu vận hành chứng minh lợi ích vượt chi phí.

## 12. Bài tập thực hành

### Bài 1 — Thiết kế topology

Cho job xử lý 8 triệu bản ghi, manager tạo 64 partition, mỗi worker pod xử lý tối đa 2 partition đồng thời. Vẽ topology với 6 pod và tính mức concurrency tối đa ban đầu. Nêu lý do 64 partition không có nghĩa cần 64 pod. Liệt kê những kết nối tối thiểu mỗi role phải có.

### Bài 2 — Thử sự cố worker

Thiết lập một job demo có reader `@StepScope`, writer idempotent và durable request queue. Khi worker đã commit vài chunk, dừng cưỡng bức pod đó. Quan sát `JobRepository`, queue unacked/redelivery và kết quả DB; sau đó restart cùng job instance. Đối soát xem đã đủ dữ liệu, có record hoặc event trùng hay không.

### Bài 3 — Mất phản hồi và manager restart

Cho worker xử lý hoàn tất nhưng cố tình chặn reply về manager. Ghi lại manager chờ trong bao lâu, metadata của `StepExecution` đang ở trạng thái nào và phản ứng khi khởi chạy lại. Thiết kế cách manager đối soát `JobRepository` để phân biệt job thực sự lỗi với reply thất lạc.

### Bài 4 — Tăng quy mô an toàn

Chạy 4, 8, 12 worker đồng thời với cùng snapshot dữ liệu. Đo wall-clock time, throughput, broker pending/unacked, DB connection wait, CPU và thời gian chậm nhất của partition. Xác định mức worker tối ưu theo số đo, không mặc định số lớn nhất là tốt nhất.

### Câu hỏi tự kiểm tra

1. Vì sao manager và worker tách deployment thường cần cùng truy cập một `JobRepository` nhất quán?
2. Tại sao một `StepExecutionRequest` bị gửi lại không nên khiến worker tạo `JobInstance` mới?
3. Điểm khác nhau quan trọng nhất giữa remote partitioning và remote chunking là gì?
4. Vì sao autoscale worker có thể tăng timeout hoặc deadlock ở database thay vì tăng throughput?
5. Khi manager chết nhưng worker còn chạy, những trạng thái nào phải đối soát trước khi restart?
6. Vì sao sử dụng lại identifying `JobParameters` quan trọng hơn việc tạo `run.id` mới khi khôi phục job lỗi?

Tách manager và worker thành các deployment độc lập là bước chuyển từ song song trong một JVM sang **xử lý phân tán có điều phối**. Khả năng thành công phụ thuộc vào partition plan ổn định, `JobRepository` nhất quán, broker có chính sách delivery rõ ràng, bước xử lý idempotent và quy trình đo lường/phục hồi đã được thử thực tế.
