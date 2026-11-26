# Scale worker theo replica trong Spring Batch

> **Chương:** Triển khai
>
> **Module:** SPRING_BATCH_SCALING_OPERATIONS — Mở rộng Spring Batch cho workload dữ liệu lớn qua multi-threaded step, parallel steps, partitioning và các mô hình xử lý phân tán phù hợp. Học đo nút thắt, bảo đảm thread safety, retry/restart, vận hành job và lựa chọn kiến trúc theo tài nguyên thực tế.

Khi Spring Batch đã được tách thành **manager** và nhiều **remote worker**, cách tăng năng lực dễ thấy nhất là nâng số replicas của worker Deployment từ 4 lên 12, hoặc để HPA/KEDA điều chỉnh tự động. Nhưng **12 replicas không đồng nghĩa 12 partitions**, không đảm bảo 12 requests được xử lý đồng thời và càng không bảo đảm throughput tăng gấp ba.

**Scale worker theo replica** là thay đổi số tiến trình/pod có thể tiêu thụ công việc. Để việc này đúng và có ích, phải hiểu **work ownership**, số partitions hoặc chunks cần xử lý, cơ chế request/reply/ACK của broker, `JobRepository`, trạng thái không chắc chắn khi worker bị kill, connection pools, resource quotas và cách làm sạch dữ liệu sau retry/restart.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **replica count**, worker concurrency, partitions, `gridSize`, chunk size và số JobInstances.
2. Giải thích khi nào tăng số remote workers làm throughput tăng, khi nào chỉ làm tăng contention, queue depth, DB sessions hoặc retry.
3. Triển khai worker dưới Kubernetes Deployment, cấu hình resource requests/limits, probes, graceful termination và bảo mật.
4. Chọn mô hình **remote partitioning** hoặc **remote chunking**, xác định metadata/transport cần chia sẻ và quyền sở hữu nhiệm vụ.
5. Thiết kế HPA/KEDA theo CPU/queue lag với minimum/maximum replicas, admission/backpressure và giới hạn kết nối downstream.
6. Scale down không mất/cấp trùng dữ liệu, đối soát work còn in-flight và xử lý late replies, ACK loss, old worker vẫn chạy.
7. Kiểm thử scale up/down, crash, pod eviction, broker redelivery, job restart và business idempotency trong môi trường nhiều JVM.
8. Đo hiệu quả scaling bằng **unique successful business operations**, latency, worker utilization, backlog age và SLA.

## 1. Từ một JVM đến nhiều worker pods

Ở mô hình đơn giản:

~~~text
Spring Batch JVM
  JobLauncher
  JobRepository
  Step
    ItemReader -> ItemProcessor -> ItemWriter
~~~

Khi một node không đủ tài nguyên, có thể chuyển sang remote partitioning:

~~~mermaid
flowchart TB
    S["Scheduler / JobLauncher"] --> M["Manager JobExecution"]
    M --> P["Partitioner & manager Step"]
    P --> B[("Broker requests")]
    B --> W1["Worker pod 1"]
    B --> W2["Worker pod 2"]
    B --> W3["Worker pod N"]
    W1 --> DB[("Business DB / object storage")]
    W2 --> DB
    W3 --> DB
    W1 --> JR[("Shared JobRepository")]
    W2 --> JR
    W3 --> JR
    JR --> M
~~~

Mỗi worker pod là **một tiến trình ứng dụng có khả năng xử lý worker step**. Khi thêm replicas, Kubernetes tạo thêm pods với cùng image/configuration; Spring Batch **không tự lấy một StepExecution rồi chia nhỏ chỉ vì có thêm pods**.

### Phân biệt các khái niệm

| Khái niệm | Nó quyết định điều gì? | Không đồng nghĩa với |
| --- | --- | --- |
| **Worker replica** | Số JVM/pod worker được triển khai | JobInstance hoặc partition |
| **Consumer concurrency/pod** | Số message deliveries một pod có thể xử lý đồng thời | Một thread luôn có JDBC connection riêng |
| **Active workers** | Số workers đang thực sự bận | Số replicas ở trạng thái Ready |
| **Logical partitions** | Số phần nguồn do `Partitioner` xác định | `gridSize` trong mọi implementation |
| **`gridSize`** | Tham số cho partitioner/handler khi tạo hoặc điều phối việc | Số pods đang có mặt |
| **Chunk size** | Số items mục tiêu trong một transaction chunk | Số chunk requests outstanding |
| **JobInstance** | Một job name + identifying parameters | Một worker pod hoặc một lần broker delivery |
| **JobExecution / StepExecution** | Những lần thực thi được JobRepository ghi nhận | Business operation ID bất biến |

Ví dụ, 80 partitions và 8 replicas, mỗi pod có một consumer:

~~~text
logical partitions       = 80
worker replicas          = 8
consumer concurrency/pod = 1
max nominal consumers    = 8

Không phải cùng lúc chạy 80 partitions.
~~~

Nếu scale lên 16 replicas, số consumer tối đa danh nghĩa tăng, **nhưng 80 logical partitions vẫn là 80** khi đã tạo từ một input manifest cố định. Mức chạy thực còn phụ thuộc message broker, handler, CPU, DB pool và work ownership.

## 2. Chọn đúng mô hình trước khi scale replicas

Spring Batch có nhiều kiểu song song, nhưng chỉ một số kiểu thật sự tận dụng pod replicas tự nhiên:

| Kiến trúc | Phần việc | Nơi chạy | Tăng replicas có tác dụng gì? |
| --- | --- | --- | --- |
| **Multi-threaded Step** | Chunk tasks | Nhiều threads trong **cùng JVM** | Không tăng throughput trực tiếp nếu chỉ thêm pods không tham gia step |
| **Parallel Steps** | Các steps/flows | Thường trong một JobExecution/JVM | Không tự phân phối sang pods |
| **Local partitioning** | Worker StepExecutions | Local `TaskExecutor` | Tăng replicas deployment không tự mở rộng handler local |
| **Remote partitioning** | Partition/worker StepExecution requests | Remote worker JVMs qua middleware | Thêm consumers/pods có thể xử lý nhiều partitions đồng thời |
| **Remote chunking** | Chunk requests chứa items | Manager đọc, worker xử lý/ghi | Thêm consumers/pods có thể tăng chunk throughput |
| **Custom work queue** | Work IDs do ứng dụng quản lý | Claim/lease trên workers | Thêm pods tăng claimers nếu state machine và fencing đúng |

**Không dùng chung cấu hình Kubernetes rồi giả định tất cả kiến trúc scale giống nhau.** Chọn worker app đúng vai trò:

- Với **remote partitioning**, mỗi worker chạy worker step dựa trên `StepExecution`/`ExecutionContext` được manager giao.
- Với **remote chunking**, worker tiếp nhận `ChunkRequest` theo Spring Batch Integration adapter, xử lý/ghi chunk và phản hồi; manager thường giữ reader.
- Với **custom queue**, worker tự claim một work ID đã có; việc quản lý idempotency, lease và checkpoint phải do kiến trúc ứng dụng xác định.

### Remote partitioning hay remote chunking?

| Câu hỏi | Remote partitioning | Remote chunking |
| --- | --- | --- |
| Worker cần đọc file/object/range trực tiếp? | Thường phù hợp | Manager thường đọc input |
| Broker có vận chuyển mọi items? | Chủ yếu metadata partition request | Có thể vận chuyển payload cả chunk |
| Worker có `StepExecution`/checkpoint riêng? | Có, theo partition model | Mô hình state/request-reply khác |
| Cần per-partition restart? | Hợp lý theo `StepExecution` và `ExecutionContext` | Phải hiểu checkpoint/request durability của manager |
| Manager có thể thành bottleneck reader? | Thường giảm nếu input được chia ở worker | Có thể |
| Backlog unit quan trọng | Partition requests/active StepExecutions | Chunk requests/ready/unacked/replies |

**Kết luận có điều kiện:** Dữ liệu đã shard theo nhiều files/ranges thường phù hợp remote partitioning; một reader tập trung nhưng phần process/write nặng có thể phù hợp remote chunking. Nên benchmark và thử nghiệm fault thay vì chọn kiến trúc chỉ dựa trên khả năng tăng pod count.

## 3. Từ manager StepExecution đến worker replica

Mỗi logical partition nên có **identity ổn định**:

~~~text
jobName       = settleOrders
businessDate  = 2026-11-25
manifestId    = settle-orders-2026-11-25-v1
managerStep   = partitionManager
partitionName = tenant-001-range-0007
sourceRange   = [000700000, 000799999]
~~~

Manager tạo `ExecutionContext` cho partition với source range/object metadata, chuyển sang worker theo cơ chế framework/adapter, và workers thực thi bằng bean worker step phù hợp. Nếu một pod mất mạng và worker StepExecution phải restart, **partitionName phải vẫn ánh xạ đến cùng input**.

~~~mermaid
sequenceDiagram
    participant M as Manager Step
    participant Q as Broker
    participant A as Worker replica A
    participant B as Worker replica B
    participant R as JobRepository
    M->>R: Create/track worker StepExecution
    M->>Q: Dispatch partition P-007
    Q->>A: Deliver request P-007
    A->>R: Read context; update checkpoint/status
    A--xM: Worker crashes / reply lost
    Note over M,R: Outcome must be reconciled
    M->>R: Inspect state before restart
    M->>Q: Redispatch/restart if policy allows
    Q->>B: Worker replica B handles P-007
    B->>R: Resume eligible execution safely
~~~

Đây là sơ đồ **logic**, không phải cam kết Spring Batch adapter sẽ tự redispatch và restart như một transaction atomic. Cách xử lý requests/replies, correlation, timeout, status và broker redelivery phụ thuộc **Spring Batch Integration, Spring Integration transport và cấu hình cụ thể**.

### Vì sao không để mỗi worker tự launch job?

Anti-pattern:

~~~java
// Không đặt trên tất cả worker pods:
@Scheduled(cron = "0 0 1 * * *")
void runJob() {
    jobLauncher.run(job, new JobParametersBuilder()
            .addLong("run.id", System.currentTimeMillis())
            .toJobParameters());
}
~~~

Nếu 12 replicas cùng thực thi đoạn này, mỗi pod có thể tạo **JobInstance riêng** trên cùng dữ liệu. Thay vì worker xử lý partition của một manager, bạn có 12 manager jobs cạnh tranh dữ liệu và side effects.

**Manager launcher/scheduler và worker consumer là hai vai trò khác nhau.** Có thể dùng cùng image với profile/entrypoint khác nhau, nhưng chỉ manager nhận quyền launch job theo schedule; workers không tự tạo identifying parameters.

## 4. Kiến trúc triển khai tách manager và worker

~~~text
Kubernetes namespace: batch-prod

CronJob/Job hoặc coordinator Deployment:
  profile = manager
  trách nhiệm:
    - nhận trigger theo businessDate/manifestId
    - JobLauncher.run(...)
    - JobRepository/Partitioner/manager step
    - theo dõi JobExecution và worker StepExecutions

Worker Deployment:
  profile = worker
  replicas = 4..N
  trách nhiệm:
    - kết nối broker request channel
    - chạy worker step hoặc chunk handler
    - ghi business output idempotent
    - ACK/reply theo transport contract

Shared services:
  JobRepository JDBC database
  message broker
  business DB/object storage
  metrics/log/tracing
~~~

### Phân lập cấu hình theo role

- Dùng `spring.profiles.active=manager` và `worker`, hoặc entrypoints riêng.
- Worker không cần chạy `ApplicationRunner` gọi `JobLauncher`.
- Manager không cần bật worker consumers nếu không cố ý chạy hybrid.
- Nếu app Spring Boot tự launch jobs lúc startup, cấu hình để **không auto-run trong worker** (ví dụ `spring.batch.job.enabled=false` với Boot version phù hợp).
- Đặt broker destinations, serializers, correlation ID, repository database và worker step name khớp chính xác.
- Worker phải có access đến business input (DB/object storage), không phụ thuộc local path của manager.

### Shared JobRepository không phải shared JVM state

`JobRepository` là metadata store để Spring Batch quản lý JobInstance/JobExecution/StepExecution; nó **không** vận chuyển contents của mỗi file hay tự đồng bộ `ThreadLocal`/MDC giữa pods. Remote partitioning cần worker lấy đúng execution/context từ metadata theo adapter.

Không dùng H2 in-memory độc lập trên từng pod rồi gọi đó là remote partitioning restartable. Repository/transaction semantics phải được kiểm chứng trên database dùng chung phù hợp phiên bản.

## 5. Kubernetes Deployment cho remote worker

Một manifest **minh họa**, cố ý dùng image và môi trường giả:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: batch-partition-worker
  namespace: batch-prod
  labels:
    app: batch-partition-worker
spec:
  replicas: 4
  selector:
    matchLabels:
      app: batch-partition-worker
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  template:
    metadata:
      labels:
        app: batch-partition-worker
    spec:
      serviceAccountName: batch-worker
      terminationGracePeriodSeconds: 120
      containers:
        - name: worker
          image: registry.example.internal/batch-worker:1.0.0
          imagePullPolicy: IfNotPresent
          env:
            - name: SPRING_PROFILES_ACTIVE
              value: worker
            - name: SPRING_BATCH_JOB_ENABLED
              value: "false"
            - name: JAVA_TOOL_OPTIONS
              value: "-XX:MaxRAMPercentage=65"
          ports:
            - containerPort: 8080
              name: http
          resources:
            requests:
              cpu: "500m"
              memory: "1Gi"
            limits:
              cpu: "2"
              memory: "2Gi"
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
            failureThreshold: 30
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
            failureThreshold: 6
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 5
            failureThreshold: 3
          lifecycle:
            preStop:
              exec:
                command: ["/bin/sh", "-c", "sleep 10"]
~~~

**Điều kiện triển khai thực:**

1. Image chứa Spring Batch worker service cùng Spring Integration/broker adapter phù hợp; tên image trên chỉ là placeholder.
2. Spring Boot Actuator health endpoints phải được bật/cấu hình. Nếu sử dụng actuator trên management port khác, chỉnh probes đúng port/path.
3. `SPRING_BATCH_JOB_ENABLED=false` là cấu hình Spring Boot ngăn auto-launch job lúc startup theo môi trường hỗ trợ; **không** tắt các worker message listeners. Kiểm chứng version và profile.
4. `serviceAccountName` cần cấu hình quyền tối thiểu tới object storage/broker secrets theo nền tảng. Không nhúng password vào manifest plain text.
5. `preStop: sleep 10` **chỉ là thời gian đệm**, không tự dừng nhận messages hay hoàn tất chunk. Production cần **drain** listener/consumer thực tế trước khi hết `terminationGracePeriodSeconds`.
6. CPU/memory requests/limits và 120 giây grace period chỉ minh họa; benchmark theo P95/P99 work-unit duration và thời gian transaction commit.
7. `maxUnavailable: 0` giúp rolling update cố duy trì pod count nhưng **không** bảo vệ transaction in-flight hay chứng minh không duplicate business effects.

### Một pod Ready chưa chắc còn capacity

Một worker có thể báo readiness thành công nhưng:

- Đang xử lý một chunk dài.
- Hikari pool cạn.
- CPU đang throttled.
- Broker đã giao nhiều messages theo prefetch.
- Thao tác idempotency/lock làm work phải chờ.

**Ready** chỉ phản ánh phép kiểm readiness đã triển khai. Muốn auto-scale hoặc điều phối chính xác, phải đo **active consumers, inflight requests, worker busy và downstream headroom**.

## 6. Worker pod nên stateless ở ranh giới restart

Kubernetes có thể xóa/tạo lại pod bất cứ lúc nào khi rollout, lỗi node, eviction, OOM hoặc autoscaling. Worker phải có khả năng thay node mà không làm mất logical work.

### State nào cần bền vững?

| State | Vị trí nên đặt | Vì sao |
| --- | --- | --- |
| Job/StepExecution/checkpoint | Shared JobRepository | Restart được khi worker pod khác nhận việc |
| Input file identity, version/checksum | Immutable manifest / `ExecutionContext` | Không đọc nhầm bytes sau restart |
| Broker request và reply correlation | Durable middleware + state đúng adapter | Giải quyết redelivery, reply lost |
| Unique business operation ID | Business ledger/DB | Chống duplicate external effects |
| Output stage artifact | Object storage/shared durable output | Không mất report do ephemeral disk bị xóa |
| Local staged file/cache | Pod ephemeral storage | Có thể tải/tạo lại, không làm nguồn checkpoint duy nhất |
| Structured trace/span context | Log/trace backend | Điều tra xuyên processes |

### Anti-pattern về local disk

~~~text
Manager path: /data/input.csv
Worker pod A: /tmp/import-123.csv
Worker pod B: không có file đó
~~~

Với input object storage, worker nhận bucket/key/version/checksum rồi đọc qua SDK hoặc stage local, và restart tải lại **đúng version**. Không lưu `/tmp/import-123.csv` thành durable source pointer trong `ExecutionContext`.

### Không dùng biến mutable toàn cục cho partition identity

~~~java
// Sai nếu nhiều worker StepExecutions chia một JVM:
static String currentPartitionName;
~~~

Trong Spring Batch, reader/processor/writer stateful nên nhận partition-specific metadata bằng `@StepScope`/late binding phù hợp, không cập nhật singleton state giữa các executions. `@StepScope` **không tự làm** mọi stateful component thread-safe trong một multi-threaded step.

## 7. Mối quan hệ replica, consumer concurrency và pool

Một mô hình sizing sơ bộ:

~~~text
R = số worker replicas Ready
C = số consumers xử lý đồng thời / pod

Danh nghĩa concurrent handlers ≈ R × C
~~~

Giả sử:

~~~text
R = 12 replicas
C = 2 consumers/pod
Nominal handlers = 24
Hikari maxPoolSize = 8 / pod
~~~

Không thể kết luận 24 SQL statements luôn chạy đồng thời, hoặc DB sử dụng đúng 96 connections. Một handler có thể giữ connection, có thể xử lý CPU trước khi cần DB, có thể gọi nhiều datasources, và pool 8 là **giới hạn tối đa mỗi pod**, không phải active connections chắc chắn.

### Tổng connection budget toàn cụm

Nếu:

~~~text
Business DB available connection budget for Batch = 160
Maximum replicas = 16
Per-replica Hikari maxPoolSize = 8
Nominal max business DB connections = 128
~~~

thì còn 32 connections làm headroom **trong giả định** chưa tính manager, `JobRepository`, health checks, metrics, admin operations và workload khác. Nếu đặt `maxReplicas=40` cùng pool 8, potential peak là 320 — dễ vượt ngân sách.

**Tăng replicas kéo theo tăng tổng số connection pools**, metrics exporters, broker consumers và JVM heaps. Phải tính capacity **toàn cluster**, không chỉ của một pod.

### Khi nào thêm replica phản tác dụng?

- Database writers tranh cùng hot row/index.
- Pool wait/DB locks tăng, throughput plateau.
- Nhiều DB connections làm tăng context switches/IO contention.
- Broker prefetch lớn khiến nhiều messages đang in-flight khó drain.
- Tăng concurrency làm downstream API trả 429/503.
- JobRepository chịu hàng nghìn StepExecution updates.

Worker autoscaling cần xem các điều kiện này trước khi nâng từ 8 lên 32 pods.

## 8. Hạn chế số partitions và skew

Giả sử `Partitioner` tạo 16 partitions cho một JobInstance và hiện có 20 worker replicas. Dù cluster có 20 pods, **tối đa 16 logical partitions riêng biệt** có thể được thực thi đồng thời (và thực tế có thể ít hơn do handler/broker).

~~~text
partition count = 16
worker replicas = 20
consumer/pod = 1

At most 16 useful active partition executions.
4 pods có thể idle.
~~~

Mặt khác, 4 partitions mỗi cái 50 triệu rows và 100 partitions mỗi cái 1.000 rows là một workload skew nặng. Scale replicas không chia nhỏ một partition lớn đã giao.

### Thiết kế partition plan trước khi tăng pods

1. Định nghĩa source ranges/files/object versions bất biến.
2. Ước lượng cost theo bytes, expected items hoặc hot keys.
3. Chọn số partitions **đủ để phân phối đều** nhưng không tạo quá nhiều `StepExecution` metadata.
4. Giữ `partitionName → input range` ổn định qua restart.
5. Khi đổi partitioning strategy, làm ở một **logical input/job instance mới được quản lý**, không remap ngầm các partitions đang checkpoint.

### gridSize có ý nghĩa gì?

Trong Spring Batch, `partitioner.partition(gridSize)` nhận một tham số sizing; implementation có thể sử dụng hoặc bỏ qua. `gridSize` cũng ảnh hưởng cách partition handler thực hiện theo builder/adapter cụ thể, nhưng **không phải lệnh Kubernetes scale replicas**.

Nếu remote manager tạo đúng 8 partitions, tăng HPA từ 8 lên 40 pods không tự tạo thêm 32 partitions.

## 9. Remote partition worker không cần JobLauncher mới

Ở remote partitioning, manager quản lý JobExecution, partition requests và worker StepExecutions. Worker cần nhận một request gắn với StepExecution có trong repository theo contract của integration adapter.

~~~text
Manager:
    JobInstance + JobExecution
    manager Step / partition plan
    StepExecution for worker partition
    send request (step execution identity)

Worker:
    receive request
    load metadata / execution context
    run configured worker step
    update StepExecution status/checkpoint
    report result/correlation
~~~

**Không** tạo `JobInstance` mới trên mỗi worker replica hoặc tự gọi `jobLauncher.run(job, randomParameters)` cho mỗi partition. Việc phân công partition thuộc manager/handler; transport request/reply phải tương thích với Spring Batch Integration.

### Local partitioning minh họa, không phải remote

~~~java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.core.task.TaskExecutor;

@Bean
Step localPartitionManager(
        JobRepository jobRepository,
        Partitioner stablePartitioner,
        Step workerStep,
        TaskExecutor partitionTaskExecutor) {
    return new StepBuilder("localPartitionManager", jobRepository)
            .partitioner(workerStep.getName(), stablePartitioner)
            .step(workerStep)
            .gridSize(16)
            .taskExecutor(partitionTaskExecutor)
            .build();
}
~~~

Đây là **local partitioning** chỉ để phân biệt các tham số. Nó không tạo remote worker consumers. Khi chuyển sang remote partitioning, dùng các components/channels/`PartitionHandler` của Spring Batch Integration phù hợp phiên bản, broker serialization và manager/worker configurations rõ ràng.

## 10. Remote chunking: scale consumer pods có thể gây backlog khác

~~~mermaid
flowchart LR
    R["Manager ItemReader"] --> M["Chunk requests"]
    M --> Q[("Request queue")]
    Q --> W1["Worker 1"]
    Q --> W2["Worker 2"]
    Q --> WN["Worker N"]
    W1 --> D[("Business DB")]
    W2 --> D
    WN --> D
    W1 --> REP[("Reply queue")]
    W2 --> REP
    WN --> REP
    REP --> M
~~~

Tăng replicas có thể làm **worker processing capacity** tăng, nhưng manager reader, message serialization, broker throughput hoặc reply aggregation có thể trở thành bottleneck.

### Tách các metrics

| Tín hiệu | Vì sao quan trọng |
| --- | --- |
| Ready chunk requests | Còn requests chưa giao cho workers |
| Unacked/in-flight requests | Đã giao nhưng chưa được ACK/commit theo contract |
| Chunk completion throughput | Workers đang hoàn tất nhanh không |
| Reply latency/correlation | Manager đang nhận kết quả kịp không |
| Outstanding unresolved requests | Một work có thể commit rồi reply mất |
| DB active connections/lock wait | Tăng pods có gây nghẽn DB không |
| Business unique operation count | Actual throughput không bị duplicate |

**Broker queue depth = 0 không chứng minh job đã hoàn tất.** Có thể toàn bộ chunks đang in-flight, một số workers đã commit nhưng reply chưa đến, hoặc output đang ở tầng reconciliation.

### Prefetch và consumer concurrency

Nếu mỗi worker nhận trước 100 messages nhưng chỉ xử lý 1 mỗi lần, scale down có thể để hàng nghìn messages đang **reserved/unacked**, làm worker mới không nhận được ngay. Cấu hình prefetch cần phù hợp concurrency thực, chunk duration và broker semantics.

Không dùng `prefetch=1` như bảo đảm total ordering hoặc exactly-once effects khi có nhiều replicas; việc commit và retry vẫn có thể lệch và trùng.

## 11. Scale thủ công trước khi bật autoscaling

Trước khi để HPA/KEDA ra quyết định, cần kiểm tra một lần scale thủ công có đúng không:

~~~text
Initial:
  worker replicas = 4
  logical partitions = 80
  max consumer concurrency = 1/pod

Scale to:
  worker replicas = 8

Expected:
  new pods become Ready and subscribe đúng request destination;
  more pending partitions can run concurrently;
  no new JobInstance is created;
  no change to partitionName -> source mapping;
  business unique operations remain correct;
  DB pool/lock latency still within budget.
~~~

Ví dụ lệnh của Kubernetes CLI:

~~~bash
kubectl -n batch-prod scale deployment/batch-partition-worker \
  --replicas=8

kubectl -n batch-prod rollout status \
  deployment/batch-partition-worker
~~~

Đây là **lệnh minh họa**, không chạy trong quá trình viết bài. Trước khi áp dụng trên hệ thống thật, người vận hành phải có quyền cluster và change plan. `rollout status` cho thấy deployment rollout/readiness, **không xác nhận Batch job hoàn tất hoặc business output đúng**.

### Kiểm tra sau scale up

1. Replicas desired/current/ready của worker Deployment.
2. Số broker consumers và active/idle consumers.
3. Số `StepExecution` đang xử lý hoặc unresolved chunk requests.
4. Pending/backlog age, completion throughput và request/reply latency.
5. Hikari active/pending connections, SQL latency/lock waits.
6. Unique committed business operations và reconciliation.

Nếu pod count tăng mà broker consumer count không tăng, vấn đề có thể nằm ở **profile/config listener/broker credentials**, không phải thiếu replica.

### Sự khác biệt giữa Ready pods và active handlers

~~~text
replicas Ready   = 8
broker consumers = 8
active handlers  = 3
pending work     = 0

Thêm replicas không làm tăng throughput, vì không còn việc.
~~~

Ngược lại:

~~~text
replicas Ready    = 8
active handlers   = 8
pending work      = 1.000
DB lock wait P95  = 900ms

Thêm replicas có thể khiến DB tệ hơn;
cần phân tích nút thắt trước.
~~~

## 12. Horizontal Pod Autoscaler theo CPU

Kubernetes HPA có thể điều chỉnh replicas dựa trên tài nguyên, ví dụ CPU utilization. Manifest mẫu:

~~~yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: batch-worker-cpu-hpa
  namespace: batch-prod
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: batch-partition-worker
  minReplicas: 2
  maxReplicas: 16
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
  behavior:
    scaleUp:
      stabilizationWindowSeconds: 0
      policies:
        - type: Pods
          value: 4
          periodSeconds: 60
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
        - type: Pods
          value: 2
          periodSeconds: 60
~~~

### HPA cần những điều kiện nào?

- Metrics Server/resource metrics hoạt động và có quyền truy cập phù hợp.
- CPU `requests` trong worker container được cấu hình; utilization thường tính tương đối với CPU requests.
- Resource limits đủ thực tế; nếu CPU throttling quá mạnh, tăng replicas có thể chưa giải quyết đúng bottleneck.
- Cấu hình HPA behavior phải phù hợp thời gian xử lý work unit, tránh scale dao động.
- Controller hoạt động trong cluster hỗ trợ `autoscaling/v2` và schema đang dùng.

**CPU HPA có thể không phù hợp khi workers chủ yếu chờ database.** CPU pods thấp trong khi backlog cao và DB pool bị bão hòa: HPA có thể không scale dù backlog tăng. Ngược lại, nếu CPU tăng vì retry/serialization không tạo thêm business success, scale CPU có thể làm tình hình tệ hơn.

### Không tạo hai controllers cùng quản lý replicas

Nếu vừa tạo HPA theo CPU ở trên, vừa dùng KEDA ScaledObject tạo HPA riêng cho **cùng Deployment**, hai controllers có thể tranh quyền cập nhật `replicas`. Cần chọn một **chủ sở hữu autoscaling** hoặc cách tích hợp nhiều metrics được hỗ trợ, không gắn hai cơ chế độc lập cùng target mà không có thiết kế rõ.

## 13. KEDA scale theo queue backlog

Với worker Deployment tiêu thụ từ broker, KEDA có thể dùng queue/lag metric để scale theo lượng work chưa xử lý. Ví dụ minh họa ScaledObject cho RabbitMQ:

~~~yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: partition-worker-queue-scaler
  namespace: batch-prod
spec:
  scaleTargetRef:
    name: batch-partition-worker
  pollingInterval: 30
  cooldownPeriod: 300
  minReplicaCount: 2
  maxReplicaCount: 16
  triggers:
    - type: rabbitmq
      metadata:
        hostFromEnv: RABBITMQ_HOST
        queueName: batch-partition-requests
        mode: QueueLength
        value: "20"
~~~

Đây là **cấu hình học tập**; cần cài KEDA version tương thích, cung cấp `RABBITMQ_HOST` bằng cách được hỗ trợ, thiết lập authentication (`TriggerAuthentication`/secret/workload identity khi phù hợp), network permission và chính xác queue request của adapter. Kiểm tra schema KEDA scaler/version đang dùng trước khi triển khai; tên queue ở đây là ví dụ, không phải tên mặc định của Spring Batch.

### Ý nghĩa value không phải replica count

`value: "20"` mô tả target queue length theo semantics của scaler KEDA cụ thể, **không** yêu cầu tạo đúng 20 worker pods. KEDA/HPA tính desired replicas từ metric, min/max, polling và policy. Khi queue ready=800, không được kết luận mỗi consumer nhận chính xác 20 partitions hoặc desired replicas luôn là 40 vì còn max replicas, lag in-flight và controller behavior.

### Khi queue metric không phản ánh số work thật

- **Remote partitioning:** manager có thể dispatch một số partition requests hữu hạn; broker ready nhỏ dù còn nhiều partitions chưa lên queue hoặc những StepExecutions đang chạy lâu.
- **Remote chunking:** request queue có thể rỗng trong khi **unacked chunks** hoặc replies pending nhiều.
- **Custom work queue:** database ready rows có thể cao nhưng KEDA đang scale theo một queue broker khác.
- **Kafka lag:** offset lag phụ thuộc committed offsets, không tự bằng số unique business operations chưa áp dụng.

Do đó, cần kết hợp queue backlog với **active workers, inflight age, DB health, deadline**. KEDA là **công cụ capacity control**, không phải business correctness engine.

## 14. Tính maxReplicas theo tài nguyên dùng chung

Một phép sizing hữu ích:

~~~text
Wmax = giới hạn replicas do cluster/DB/API cho phép
Cpod = consumers đồng thời / pod
Ppod = max JDBC connections / pod

Nominal handlers = Wmax × Cpod
Potential DB connections = Wmax × Ppod
~~~

Ví dụ:

~~~text
Database dành cho Batch tối đa: 100 connections
Manager/metadata dự phòng:    12
Safety headroom:              16
Ngân sách workers:            72

Worker pool tối đa/pod:         6
maxReplicas lý thuyết:        12
~~~

**12 replicas chỉ là cận theo connection budget**, không có nghĩa DB CPU/locks/IO xử lý tốt 72 connections hoặc cluster đủ CPU, memory và network. Nếu có **hai Batch jobs** cùng dùng deployment/pool, phải tính **tổng concurrency across jobs**.

### Cơ chế giới hạn nhiều tầng

| Tầng | Giới hạn | Rủi ro nếu quên |
| --- | --- | --- |
| Scheduler/launcher | Số JobExecutions active | Nhiều jobs cùng tranh DB |
| Partition manager | Partitions in flight | Broker/repository bị quá tải |
| Worker Deployment | Max replicas | Quá nhiều JVMs/resources |
| Worker consumer | Concurrency/prefetch | Quá nhiều messages unacked |
| JDBC pool | Connections/pod | Bùng số sessions toàn cluster |
| HTTP client | Calls in flight/rate limit | API 429/timeout |
| Broker | Queue/partition quotas | Latency/reject/broker overload |
| Business DB | CPU/IO/locks/connection budget | Throughput plateau/giảm |

Nếu điều chỉnh một tầng mà không đo tầng còn lại, khả năng cao không tìm được bottleneck thật.

## 15. Benchmark scaling curve trước production

Một ma trận thử nghiệm cơ bản:

| Scenario | Replicas | Consumer/pod | Chunk/partition plan | Mục tiêu |
| --- | ---: | ---: | --- | --- |
| R1 | 1 | 1 | Cố định | Baseline |
| R2 | 2 | 1 | Cố định | Scaling ban đầu |
| R4 | 4 | 1 | Cố định | Phân phối work |
| R8 | 8 | 1 | Cố định | Tìm plateau |
| R16 | 16 | 1 | Cố định | Kiểm tra DB/pool contention |
| C2 | 4 | 2 | Cố định | So replica vs consumer concurrency |
| C4 | 4 | 4 | Cố định | Kiểm tra per-pod resource saturation |
| S1 | 8 → 2 | 1 | Cố định | Graceful scale-down |
| S2 | 2 → 8 | 1 | Cố định | Catch-up backlog |
| F1 | 8, kill 1 | 1 | Cố định | Restart/redelivery correctness |

**Thay một biến mỗi lượt:** cố định input manifest, schema, index, DB instance, chunk size, worker image và mức tải OLTP. Số replicas/pods tăng cũng tăng **tổng CPU/RAM budget**, cần ghi rõ để so sánh đúng.

### Throughput đo thế nào?

~~~text
uniqueBusinessItemsPerSecond =
  số business operation IDs mới được commit hợp lệ
  / thời gian đo
~~~

Không dùng số callbacks `ItemWriter.write(...)`, `readCount` hay số broker ACKs làm business throughput. Chúng có thể tăng vì retries, rollback hoặc redelivery.

### Scaling efficiency

~~~text
Speedup(R) = Throughput(R) / Throughput(1)
Efficiency(R) = Speedup(R) / R
~~~

Ví dụ giả định:

| Replicas | Unique items/s | Speedup vs 1 | Efficiency |
| ---: | ---: | ---: | ---: |
| 1 | 1.500 | 1,00× | 100% |
| 2 | 2.900 | 1,93× | 97% |
| 4 | 5.100 | 3,40× | 85% |
| 8 | 6.300 | 4,20× | 53% |
| 16 | 5.800 | 3,87× | 24% |

Đây là **synthetic data minh họa**, không phải benchmark thật. Kết quả cho thấy lợi ích có thể giảm dần và throughput suy giảm khi replicas quá nhiều. Nếu concurrency bị giới hạn bởi 10 partitions hoặc DB, thêm 16 pods chưa chắc cần thiết.

### Đừng bỏ qua tail latency

Một job có 80 partitions, 79 partitions hoàn tất sau 20 phút nhưng một partition nặng mất 3 giờ; peak throughput 10.000 items/s không đảm bảo deadline. Đo:

- Whole-run time và P95/P99 partition duration.
- Per-worker utilization và idle time.
- DB lock/pool wait P95.
- Backlog ready vs in-flight vs failed/unknown.
- Business output reconciliation và publish time.

## 16. Scale-down an toàn: không chỉ sleep trước SIGTERM

Kubernetes scale-down/rollout có thể chọn pod đang xử lý chunk hoặc partition. Nếu pod bị dừng giữa transaction:

~~~text
Worker:
  nhận work W
  ghi business DB COMMIT
  mất kết nối trước ACK/reply
  pod bị terminate

Manager/broker:
  chưa thấy reply
  có thể gửi lại W hoặc timeout
~~~

**Không có transaction atomic tự động giữa business DB, broker và JobRepository** chỉ vì worker đang trong một `@Transactional` method.

### Quy trình drain có kiểm soát

1. Pod nhận tín hiệu shutdown/được đánh dấu **không tiếp tục nhận việc mới**.
2. Dừng consumer listener/disable new claims theo API của adapter.
3. Giữ các requests **đã nhận** đến khi transaction/chunk boundary an toàn, hoặc rollback nếu bắt buộc.
4. ACK/reply/update StepExecution theo transport/framework contract khi outcome đã xác nhận.
5. Đóng reader, flush/dọn local temp resources có kiểm soát.
6. Sau khi active handlers về 0 hoặc hết bounded grace period, kết thúc process.
7. Nếu hết hạn và bị SIGKILL, coi work còn in-flight là **chưa chắc chắn**, kiểm tra old ownership/DB output trước replay.

~~~mermaid
flowchart TD
    SIG["SIGTERM / scale-down signal"] --> PAUSE["Stop receiving new work"]
    PAUSE --> DRAIN["Drain in-flight tasks within grace"]
    DRAIN --> DONE{"All tasks settled?"}
    DONE -- "Có" --> ACK["Persist status + ACK/reply safely"]
    ACK --> EXIT["Close resources & exit"]
    DONE -- "Không" --> UNC["Unresolved / timed out"]
    UNC --> REC["Manager reconciliation, idempotent retry/restart"]
~~~

**Phải dùng API/lifecycle thực** của message listener container hoặc custom queue dispatcher. `preStop: sleep 10` và readiness false **không tự đóng broker consumers**; worker vẫn có thể nhận messages trong lúc Kubernetes bắt đầu dừng.

### Vì sao terminationGracePeriodSeconds phải đo?

Giả sử một partition xử lý trong 20 phút. Grace period 120 giây không thể cho partition hoàn tất nếu nó không có checkpoint/stop boundary trong thời gian đó. Lựa chọn:

- Thiết kế worker chunk/partition có các **safe checkpoints** và stop hợp tác.
- Dùng work units nhỏ hơn khi phù hợp.
- Cho thời gian grace hợp lý nếu cluster và SLO cho phép.
- Giữ idempotent recovery sau hard termination; không hứa mỗi pod luôn drain xong.

### RollingUpdate khác scale-to-zero

RollingUpdate với `maxUnavailable: 0` cố duy trì số pods khả dụng khi đổi image, nhưng **không** ngăn pod cũ đang giữ message bị kill khi grace hết. Scale to zero cố ý dừng toàn bộ consumers và có thể làm manager remote chunking chờ replies; không áp dụng nếu không có durable requests và một quy trình restart đã kiểm chứng.

## 17. Kubernetes PodDisruptionBudget có thể giúp gì?

Ví dụ:

~~~yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: batch-worker-pdb
  namespace: batch-prod
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app: batch-partition-worker
~~~

PDB giúp kiểm soát **một số voluntary evictions qua Eviction API**, chẳng hạn trong quy trình drain node có tôn trọng PDB. Nó **không** bảo vệ khỏi mọi loại failure/termination (node chết, OOM, xóa cưỡng bức, app crash), và **không thay thế** graceful shutdown hay idempotent writer.

PDB không phải cơ chế ngăn HPA/KEDA hợp lệ giảm replicas xuống mức thấp theo policy; kiểm tra cách controller/cluster xử lý eviction và scale-down thực tế. Đừng thiết kế PDB như một transaction coordinator.

## 18. Crash window, redelivery và idempotency

Một work unit có thể bị thực thi lại trong cả hai mô hình remote.

~~~mermaid
sequenceDiagram
    participant M as Manager
    participant B as Broker
    participant W as Worker
    participant D as Business DB
    M->>B: Send work W-17
    B->>W: Deliver W-17
    W->>D: Write operation OP-17
    D-->>W: COMMIT
    W--xM: Reply/ACK lost
    Note over M: Cannot infer DB rollback
    B->>W: Redelivery or controlled retry
    W->>D: Replay OP-17 same stable key
    D-->>W: Same payload -> idempotent outcome
    W-->>M: Correlated reply
~~~

Sơ đồ **chỉ minh họa một recovery path**: broker redelivery không tự động đúng trong mọi middleware/adapter, và timeout không chứng minh chưa commit. Cần test transport thực tế.

### Business operation ID khác attempt ID

| ID | Ví dụ | Có ổn định qua retry? |
| --- | --- | --- |
| JobInstance identity | `settleOrders + businessDate + manifestId` | Có |
| Logical partition | `tenant-001-range-0007` | Có |
| Business operation | `(tenantId, transactionId)` | **Phải có** |
| JobExecutionId | `501` rồi `502` | Không nhất thiết |
| StepExecutionId | `701` rồi `743` | Không nhất thiết |
| Pod name | `worker-7d6bf...` | Không |
| Broker delivery tag/message attempt | Tùy transport | Không |

Nếu sinh `UUID.randomUUID()` khi retry thanh toán, cùng giao dịch nguồn có thể tạo tác dụng kép. **Stable business ID + unique constraint/recipient idempotency** mới là lớp bảo vệ.

### PostgreSQL uniqueness làm hàng rào

~~~sql
CREATE TABLE settled_operation (
    tenant_id      VARCHAR(80) NOT NULL,
    operation_id   VARCHAR(160) NOT NULL,
    payload_hash   VARCHAR(128) NOT NULL,
    amount_minor   BIGINT NOT NULL,
    result_status  VARCHAR(32) NOT NULL,
    PRIMARY KEY (tenant_id, operation_id)
);
~~~

Khi replay:

1. Cùng key + cùng business payload → no-op hoặc đọc kết quả đã lưu.
2. Cùng key + payload khác → **conflict**, không âm thầm ghi đè.
3. Chưa commit → retry trong transaction đúng.
4. Provider API outcome chưa rõ → query/reconcile trước khi gửi lại, giữ **cùng idempotency key** khi provider hỗ trợ.

### Outbox

Nếu worker cần vừa ghi database vừa publish message/gọi API:

- Ghi business state và **outbox intent** trong **cùng DB transaction** khi có thể.
- Dispatcher gửi idempotently theo stable operation ID.
- Consumer nhận có thể dedupe; outbox vẫn có thể phát lại sau crash.
- Không coi một `@Transactional` tại worker bảo đảm atomic commit với object storage, Kafka hoặc HTTP bên ngoài.

## 19. Worker replica mới có thể trùng worker cũ

Một worker cũ không nhất thiết đã chết khi manager timeout hoặc lease hết hạn.

~~~text
02:00 Worker A nhận partition P-7
02:05 A bị network partition, không báo heartbeat/reply
02:06 Worker B được cấp lại P-7
02:07 A kết nối lại và tiếp tục ghi
~~~

Nếu cả A và B cùng xử lý source range, unique operation constraint có thể chống tác dụng kép ở DB, nhưng:

- Cả hai có thể ghi output object key giống nhau.
- API bên ngoài không dedupe có thể bị gọi hai lần.
- StepExecution metadata có thể bị race nếu ownership không được adapter/queue kiểm soát.
- Một kết quả sai có thể được publish nếu không reconcile output.

### Fencing khi dùng custom work queue

Nếu ứng dụng tự quản lý queue/lease, có thể lưu `claim_generation` tăng mỗi lần ownership đổi:

~~~sql
UPDATE batch_work_queue
SET worker_id = :newWorkerId,
    claim_generation = claim_generation + 1,
    lease_until = NOW() + INTERVAL '5 minutes'
WHERE work_id = :workId
  AND state = 'RETRYABLE';
~~~

Worker phải mang đúng generation và **đích ghi** kiểm tra generation/ownership ở transaction boundary. Nếu chỉ kiểm tra trước khi gọi external API rồi lease hết giữa lúc call, fencing **không tự ngăn** request đã gửi; vẫn cần provider-side idempotency/outbox.

**Cảnh báo:** `batch_work_queue` là ví dụ cho **custom queue**, không phải bảng `BATCH_*` của Spring Batch. Không thêm lease riêng chồng lên `StepExecution` remote partitioning mà không định nghĩa rõ cơ chế ownership giữa manager, handler, broker và repository.

## 20. Restart phải giữ logical input cố định

Giả sử scale-down làm một số StepExecutions fail giữa chunk. Khi restart:

~~~text
JobInstance:
  jobName = settleOrders
  businessDate = 2026-11-25  (identifying)
  manifestId = settle-v1      (identifying)

Run 1:
  JobExecutionId = 501 FAILED
  P-007 StepExecutionId = 701

Restart:
  JobExecutionId = 502
  P-007 StepExecutionId = 743 (có thể)
  P-007 input range/checksum vẫn giống ban đầu
~~~

- Không đổi identifying `run.id` chỉ để được launch lại cùng dữ liệu.
- Không đổi `partitionName` → source mapping vì số replicas thay đổi.
- `@StepScope` reader cần checkpoint keys/name ổn định.
- Mỗi partition source/worker state cần restart contract rõ, không dùng local pod path làm durable checkpoint.
- Writer idempotent để replay phần việc quanh rollback/ACK loss.
- Nếu source object đã bị xóa hoặc version mismatch, **fail rõ** hoặc phục hồi source đúng bytes; không lấy latest version thay thế.

### Kubernetes pod restart không bằng Spring Batch job restart

Kubernetes có thể thay pod nhưng **không tự tạo một JobExecution restart hợp lệ**. Việc Spring Batch restart cần JobRepository state và orchestration của manager/JobOperator theo điều kiện framework. Không coi Deployment có `restartPolicy: Always` là tất cả failed worker StepExecutions sẽ tự trở lại đúng checkpoint.

## 21. Rolling deployment worker: tương thích request và checkpoint

Một Deployment rollout không đơn giản là thay image và tăng replica count. Trong lúc chuyển từ `worker:1.0.0` sang `worker:1.1.0`, **cả hai phiên bản có thể chạy đồng thời**, nhận requests từ cùng queue.

### Những hợp đồng phải tương thích

| Hợp đồng | Ví dụ lỗi nếu thay không tương thích |
| --- | --- |
| **Message serialization** | Worker mới không deserialize được request cũ |
| **Worker step name** | Request chỉ tới step tên đã bị đổi |
| **ExecutionContext keys** | Reader mới tìm `rangeStart` nhưng context cũ chỉ có `startId` |
| **Input schema** | Writer mới parse format nhưng manager vẫn phát payload cũ |
| **Business DB schema** | Worker mới ghi column chưa tồn tại, worker cũ đọc sai |
| **Checkpoint structure** | ItemStream mới không thể khôi phục state đã ghi |
| **Reply/correlation protocol** | Manager không ghép được reply từ worker version khác |
| **Idempotency semantics** | Hai versions sinh operation ID khác nhau cho cùng event |

### Quy tắc expand → deploy → contract

1. **Expand schema** theo cách worker cũ và mới cùng chạy được.
2. Deploy worker version mới **canary** với concurrency thấp và quan sát lỗi.
3. Khi tất cả manager/worker paths tương thích, mới tăng rollout.
4. Chỉ sau khi không còn requests/checkpoints dùng schema cũ mới **contract** columns/fields không còn cần.

Nếu thay đổi không backward compatible, cần **ngừng nhận work mới có kiểm soát, drain những requests cũ, hoàn tất/reconcile**, rồi mới cập nhật đồng bộ; không giả định rolling update luôn an toàn.

### Canary khác production replica tăng đồng loạt

Một canary worker có thể kết nối **cùng broker queue** với workers cũ. Không đảm bảo nó nhận đúng 5% requests trừ khi có routing/weighting cụ thể. Muốn canary có tỷ lệ xác định có thể dùng **routing key/destination riêng**, một tập partitions được phép, hoặc cơ chế broker/test queue chủ động; phải tránh double processing cùng work ID.

## 22. Deploy manager theo lịch, scale workers theo tải

Một manager job thường có thể chạy bằng Kubernetes CronJob/Job, còn workers là Deployment luôn sẵn sàng hoặc autoscaled:

~~~yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: settle-orders-manager
  namespace: batch-prod
spec:
  schedule: "0 1 * * *"
  timeZone: "Asia/Ho_Chi_Minh"
  concurrencyPolicy: Forbid
  startingDeadlineSeconds: 900
  jobTemplate:
    spec:
      backoffLimit: 1
      template:
        spec:
          restartPolicy: Never
          serviceAccountName: batch-manager
          containers:
            - name: manager
              image: registry.example.internal/batch-manager:1.0.0
              args:
                - "--app.batch.run-once=true"
~~~

**Điều kiện:** `app.batch.run-once` là argument **do ứng dụng tự định nghĩa**, cần runner đọc businessDate/manifest rồi gọi JobLauncher và theo dõi execution đến trạng thái terminal, đồng thời trả exit code phù hợp. `spec.timeZone` yêu cầu Kubernetes version/controller hỗ trợ. `concurrencyPolicy: Forbid` chỉ tác động các Jobs thuộc **cùng CronJob resource**, không khóa mọi manual/external triggers của cùng Spring Batch JobInstance.

### Tránh trùng launch khi CronJob retry

~~~text
JobInstance:
  jobName = settleOrders
  businessDate = 2026-11-25 (identifying)
  manifestId = settle-orders-v1 (identifying)

CronJob retry / manager pod restart:
  vẫn phải dùng cùng identifying parameters.
~~~

Không tạo `run.id=System.currentTimeMillis()` identifying khi Kubernetes thử lại manager container, vì điều đó sinh một **JobInstance mới** trên cùng input. Cần JobRepository, business run registry/lock và idempotency.

### Đừng tắt tất cả workers theo cron một cách thô bạo

Nếu manager đang xử lý partitions kéo dài qua giờ cao điểm, scale workers về 0 ngay có thể làm job stuck hoặc tạo many unresolved requests. Tầng orchestration cần **admission window**, lịch giảm concurrency theo từng bước và drain/restart policy, chứ không chỉ một cron patch Deployment.

## 23. Worker health checks không nên tạo retry storm

Kubernetes có ba kiểu health probe thường gặp:

- **Startup:** cho app đủ thời gian khởi tạo trước khi liveness/readiness giám sát.
- **Liveness:** quyết định khi nào restart container vì app không còn hoạt động.
- **Readiness:** quyết định pod có sẵn sàng cho các cơ chế routing/traffic phù hợp; với broker consumer, cần ứng dụng chủ động điều khiển listener nếu muốn readiness đồng nghĩa không claim work.

### Tránh liveness check nặng

Anti-pattern: liveness query business DB bằng SQL có lock/latency cao. Khi DB outage, tất cả workers cùng fail liveness rồi restart liên tục, làm broker redelivery, connection churn và JobRepository pressure nặng hơn.

Nên phân biệt:

~~~text
Liveness:
  JVM/event loop/application process còn vận hành?

Readiness:
  app đã khởi tạo và đủ điều kiện nhận work mới?

Dependency health:
  broker, DB, object storage, provider API có đang healthy?

Worker admission:
  đang trong safe window và có capacity nhận request?
~~~

Readiness và liveness phải được định nghĩa rõ ở cấp ứng dụng. Một node đã mất DB connection có thể vẫn **sống** để ghi log, chờ recover/backoff và drain. Quyết định terminate/restart cần dựa trên khả năng phục hồi và failure mode, không coi mọi external dependency lỗi là JVM lỗi.

### Readiness chưa chắc có nghĩa broker dừng giao việc

Kubernetes không tự deregister một RabbitMQ consumer chỉ vì HTTP readiness endpoint trả 503. Khi pod dùng direct broker connections, ứng dụng cần **stop/pause listener container** theo API Spring Integration/Spring AMQP/Kafka được dùng. Kiểm thử này trong môi trường đa pod, không chỉ đơn JVM.

## 24. Bảo mật khi scale số workers

Tăng replicas làm tăng số workload identities, connections, secrets mounts và nơi dữ liệu có thể được truy cập. Nguyên tắc:

1. Worker dùng **ServiceAccount/Workload Identity** phù hợp môi trường, không hardcode broker/DB passwords.
2. Chỉ cho worker quyền **read** input snapshot/object và **write** output prefix/DB tables cần thiết.
3. Manager chỉ có quyền launch/metadata cần thiết; không nhất thiết được phép ghi business output trực tiếp.
4. NetworkPolicy giới hạn worker tới broker, JobRepository, target DB/object store và observability backend cần thiết.
5. Áp dụng TLS và secret rotation, biết worker connection/session xử lý thay đổi credentials ra sao.
6. Không đưa access token/presigned URL vào `ExecutionContext`/logs lâu dài.
7. Log correlation ID/partitionName được sanitize; không log raw business payload hay personal identifiers.
8. Mỗi environment (dev/staging/prod) nên tách namespace, data, queues và permissions.

### Secret rotation có thể gây restart

Một số app không reload secrets tự động; rotation có thể yêu cầu rollout. Vì vậy **secret rotation cũng là một kịch bản worker drain/recovery**, không chỉ một thao tác bảo mật. Test rotation khi nhiều chunks/partitions đang chạy và đảm bảo worker cũ/new không cùng gây double side effect.

## 25. Observability khi tăng/giảm replicas

Dashboard phải cho thấy cả **desired capacity** và **actual business progress**.

| Metric/tín hiệu | Câu hỏi cần trả lời |
| --- | --- |
| `kube_deployment_spec_replicas` | Muốn có bao nhiêu pods? |
| `kube_deployment_status_replicas_available` | Bao nhiêu pods sẵn sàng theo Deployment? |
| Broker consumer count | Bao nhiêu workers thực sự đang nhận work? |
| Active/inflight worker requests | Bao nhiêu work units đang xử lý? |
| Pending ready backlog + age | Có thêm throughput thật không? |
| `StepExecution` completed/failed/restarted | Partition đang đi tới terminal state? |
| Unique business commits/s | Thành quả nghiệp vụ, không phải attempts |
| Hikari active/pending/acquire latency | DB pool có bị nghẽn khi tăng pods? |
| DB lock waits/deadlocks/SQL P95 | Shared DB có chịu được concurrency? |
| JVM CPU/GC/heap/CPU throttling | Pod resources có đủ không? |
| Broker redelivery/reply timeouts | Scale-down có làm tăng work không rõ? |
| Reconciliation mismatch/UNKNOWN | Có thể publish an toàn không? |

`kube_*` metrics thường đến từ **kube-state-metrics** theo version/exporter tương ứng, không phải Spring Batch tự sinh. Tên metrics, labels và availability phải kiểm tra thực tế trên cluster.

### Không dùng worker replica name làm metric labels không giới hạn

Nếu một job có hàng nghìn StepExecutions, không gắn `StepExecutionId`, `operationId`, full `objectKey` hoặc mỗi pod UUID làm labels cho **business metrics lâu dài**. Dùng structured logs/audit/tracing để tra từng partition; metrics tổng hợp theo environment, pipeline, status, dependency và worker role.

### Ví dụ structured log

~~~json
{
  "event": "worker_partition_completed",
  "jobName": "settleOrders",
  "jobExecutionId": 502,
  "stepExecutionId": 743,
  "partitionName": "tenant-001-range-0007",
  "manifestId": "settle-orders-2026-11-25-v1",
  "workerPod": "batch-worker-abc123",
  "workerVersion": "1.1.0",
  "durationMs": 121045,
  "readCount": 100000,
  "writeCount": 100000,
  "rollbackCount": 0
}
~~~

Đây là **log do ứng dụng thiết kế**, không phải event mặc định Spring Batch. `writeCount` không đồng nghĩa số business rows mới khi writer idempotent; đối soát unique business IDs riêng.

## 26. Cảnh báo scaling sai hoặc workers không nhận việc

Các alert hữu ích:

- Desired replicas > available replicas quá ngưỡng và quá `for`.
- Worker pods Ready nhưng broker consumer count bằng 0 trong cửa sổ active.
- Ready backlog tăng liên tục trong khi unique commit throughput giảm.
- In-flight/unacked request age vượt safe limit.
- Reply timeouts/redelivery tăng sau scale-down hoặc rollout.
- DB pool wait và lock contention tăng khi replicas tăng.
- StepExecution FAILED/UNKNOWN không có recovery.
- Publisher bị chặn do missing/duplicate operations.

### Không tự điều chỉnh theo queue depth một chiều

~~~text
Backlog tăng
    ↘
     Check completion rate, DB health, HTTP 429, worker idle
       ↘
        nếu workers bão hòa và DB còn headroom: scale up dần
        nếu DB bão hòa: giảm dispatch/concurrency
        nếu consumer chết: sửa connectivity/deployment
        nếu UNKNOWN: reconcile, không requeue mù
~~~

Khi backlog tăng vì publisher/ordered projector phía sau worker, thêm worker ingestion có thể làm downstream backlog lớn hơn. Cần đo **full pipeline đến business outcome**, không chỉ queue ngay sau manager.

### Worker utilization có thể đánh lừa

Một pod CPU chỉ 10% có thể:

- Đợi database lock.
- Đợi HTTP response.
- Đợi một slow partition.
- Đợi broker request vì đang dư capacity.

Chỉ khi đo thêm **pending/active work, connection wait, DB/HTTP latency** mới biết CPU thấp nghĩa là thiếu work hay đang bị block.

## 27. Test tăng replicas theo từng mốc

### 27.1. Test baseline

Fixture:

~~~text
Input manifest: 64 immutable partitions
Expected unique business operations: 6.400.000
Worker replicas: 1
Consumer concurrency: 1
DB resources: fixed
Broker config: fixed
Chunk size: 200
~~~

Chạy job, đo:

- Unique committed operations/s.
- End-to-end duration, P95/P99 partition times.
- Active JDBC connections và pool acquisition waits.
- Input-output reconciliation.
- Job/StepExecution statuses và restartability.

### 27.2. Scale 1 → 4 → 8 → 16

Với cùng input fixture/DB budget, đo cùng metric window và áp dụng warm-up/repetition protocol. Không đổi partition plan trong lúc restart cùng JobInstance. Nếu test run mới với cùng data, dùng **datasetId/namespace output riêng** hoặc restore DB state để tránh idempotent no-op làm throughput giả cao/thấp.

Kỳ vọng:

1. Số ready pods/consumers tăng theo Deployment.
2. Active work tăng nếu còn pending và DB có headroom.
3. Throughput tăng tới một plateau rồi có thể giảm.
4. Không mất/trùng operation IDs.
5. Tail latency, DB locks/connection pool và broker retry vẫn trong guardrails.

### 27.3. Test scale down khi đang commit

~~~text
Given:
  8 workers, 64 partitions, 6 in-flight worker steps

When:
  scale deployment to 2 replicas

Then:
  new work admission stopped on terminating pods
  in-flight work drains/rolls back/reconciles by policy
  no unique business operation applied twice
  no partition silently marked COMPLETED without output
  manager can resume/restart appropriately
  output manifest not published while unresolved
~~~

Không chỉ assert `Deployment.status.availableReplicas==2`. Điều này nói về **pod availability**, không chứng minh correctness của Spring Batch.

## 28. Fault-injection matrix: những cửa sổ cần test

| Kịch bản | Kết quả cần chứng minh |
| --- | --- |
| Tăng replicas khi không có pending work | Pods có thể idle, không tạo JobInstances mới |
| Tăng replicas vượt partition count | Không tạo thêm logical partitions ngoài plan |
| Scale CPU HPA khi worker chủ yếu chờ DB | Không suy scale success từ CPU; đo throughput |
| Scale queue KEDA khi broker lag cao | Replica tăng trong max, DB còn headroom |
| Scale down khi worker có active chunk | Drain/rollback và work được recovery |
| Pod bị SIGKILL không kịp drain | Recovery theo metadata/replay, không double effect |
| Worker COMMIT DB rồi reply mất | Reconcile output trước redelivery |
| Broker redelivery cùng message | Stable operation ID tạo idempotent effect |
| Worker cũ chạy sau timeout/lease | Fencing/ownership và business idempotency |
| Rollout 1.0.0 → 1.1.0 với pending requests | Message/context schema compatible |
| Rollout đổi Step name không tương thích | Fail/hold có cảnh báo; không âm thầm mất work |
| Source object thay đổi version | Worker đọc đúng pinned version hoặc fail rõ |
| Worker pod mất local cache | Restart stage lại source, checkpoint vẫn đúng |
| DB connection pool saturated | Scale thêm không làm job bể dữ liệu/retry vô hạn |
| HTTP 429/503 | Bounded backoff, không scale mù |
| Manager crash khi worker còn chạy | Reconcile JobRepository/outcomes, không launch trùng |
| CronJob trigger lặp | Cùng identifying parameters và JobInstance |
| HPA scale xuống 0 qua policy khác | Không mất pending, có cơ chế wake/restart |
| Metrics exporter chết | Alert stale/missing; không báo backlog=0 giả |
| Job COMPLETED nhưng output thiếu | Business reconciliation làm test FAIL |
| Worker quay lại sau node outage | Không ghi lại business side effects hai lần |

### Test thật với nhiều JVM/container

Unit tests trong cùng JVM có thể bỏ sót:

- Broker redelivery/ACK và request/reply correlation.
- JVMs có clocks/MDC/thread state khác nhau.
- Pod termination grace hết trước transaction hoàn tất.
- Network partition giữa broker/JobRepository/business DB.
- Secret rotation, service account và network policies.

Tối thiểu một bộ integration test cần **manager process và nhiều worker processes độc lập**, broker thực loại tương ứng, shared JobRepository và business DB có unique constraints thật. Có thể dùng container orchestration test/lab được cấp phép; dùng resource quotas để không ảnh hưởng cluster dùng chung.

## 29. Kiểm thử restart theo business identity

Giả sử worker A đã ghi 200 items đầu của partition P-7, rồi bị kill sau commit:

~~~text
Run 501:
  P-7 stepExecution=701, chunk A committed
  pod A killed before reply

Run 502 (restart same JobInstance):
  P-7 stepExecution=743 (có thể)
  worker B tiếp tục/replay theo checkpoint
~~~

Phải xác minh:

1. Identifying `businessDate`/`manifestId` không đổi.
2. `partitionName` vẫn trỏ cùng source range/object version.
3. Reader checkpoint hợp lệ khi worker chuyển sang pod mới.
4. Writer dùng stable business key để replay không double effect.
5. Broker deliveries/manager replies được correlate đúng.
6. Business output đủ đúng tập expected IDs sau reconciliation.
7. Không có UNKNOWN chưa được giải quyết khi publish.

Không dùng `JobExecutionId` mới làm idempotency key, vì nó sẽ biến replay thành operation khác.

## 30. Runbook khi scale worker không tăng throughput

Operator thấy 8 → 24 replicas nhưng throughput giảm từ 11.000 xuống 8.000 items/s:

1. **Chốt JobInstance/manifest:** cùng dữ liệu, source version, output dataset và metric semantics?
2. **Kiểm tra Deployment:** desired/ready pods, failures, OOM, CPU throttling, crash loop.
3. **Kiểm tra broker:** consumer count, ready/unacked, lag, redelivery, reply timeouts.
4. **Kiểm tra active work:** số partitions/chunks in-flight có đủ để tận dụng 24 workers không?
5. **Xem pool toàn cụm:** Hikari maxPoolSize × replicas, pending/active connections và timeout.
6. **Xem DB:** lock waits, slow SQL, WAL/IO, CPU và OLTP SLO.
7. **Xem JobRepository:** StepExecution update latency, contention, failed/restarted executions.
8. **Xem worker JVM:** heap/GC/CPU, processor duration, local disk/object GET.
9. **Đo business throughput:** unique committed operations/s; tách attempted writes và retries.
10. **Tìm plateau:** thử hạ concurrency/prefetch/pool/replicas từng bước, giữ các biến khác ổn định.
11. **Kiểm tra worker cũ:** Có pods vẫn in-flight sau scale-down, requests UNKNOWN hoặc double claims?
12. **Bảo vệ correctness:** Không tăng skipLimit để làm backlog giảm giả, không xóa messages đang chờ.
13. **Đối soát output:** expected IDs, duplicate/conflict, unknown/reconciliation và publish gate.
14. **Ghi nhận cấu hình mới:** throughput, latency, resource budget, retry rate, deadline margin.

### Khi cần rollback rollout

Nếu worker version mới lỗi deserialize request, reader schema hoặc SQL:

- Ngừng dispatch requests mới vào phiên bản lỗi.
- Giữ durable queue, không xóa messages cũ để trống dashboard.
- Drain/reconcile inflight và xác nhận old version còn tương thích input/context.
- Roll back image **theo kế hoạch** rồi resume consumption.
- Không ép `JobRepository` status thành COMPLETED hoặc tạo JobInstance identifying mới để né lỗi.

### Khi DB quá tải

Nếu P95 pool wait, lock contention và rollback tăng sau scale up:

- Giảm consumer concurrency/replicas và kiểm tra kết quả.
- Áp rate limit/admission để bảo vệ OLTP.
- Tối ưu SQL/index/partitioning theo hot keys khi có bằng chứng.
- Điều chỉnh chunk size có kiểm soát; transaction lớn không luôn tốt hơn.
- Chỉ tăng pool/DB capacity nếu connection/CPU/IO budget đã được đánh giá.

## 31. Bài tập tình huống: 40 worker replicas trên 16 partitions

Một hệ thống xử lý 20 triệu giao dịch mỗi đêm bằng remote partitioning. Manager tạo **16 logical partitions**, mỗi partition từ file object storage riêng. Kubernetes Deployment ban đầu có 8 worker replicas, mỗi pod dùng 1 consumer và Hikari pool tối đa 16 connections.

Để tăng throughput, đội vận hành:

1. Bật KEDA với `maxReplicaCount=40` theo request queue depth.
2. Đồng thời bật thêm HPA CPU trực tiếp trên cùng Deployment.
3. Tăng `gridSize` lên 64 trong khi restart lại cùng JobInstance.
4. Đặt `terminationGracePeriodSeconds=10` dù một chunk thường mất 45 giây.
5. Cho manager thêm identifying `run.id=now()` mỗi lần thấy reply timeout.
6. Cho worker mới dùng `source latest` thay vì pinned object version.
7. Worker gọi payment API với `UUID.randomUUID()` mỗi attempt.
8. Đánh dấu báo cáo hoàn tất khi broker queue ready về 0.

Sau thay đổi:

~~~text
Ready worker replicas    = 40
Active partition workers = 16 (tối đa theo current logical work)
Unique business rows/s   = không tăng
DB connection count      = tăng mạnh
API 429                  = tăng
Broker unacked           = tăng
Worker restarts          = tăng
Một số business operations bị duplicate
~~~

**Câu hỏi:**

1. Vì sao 40 replicas không thể làm 16 logical partitions chạy thành 40 độc lập?
2. `gridSize` có bảo đảm tạo đúng 64 partitions không? Vì sao không nên remap input của partition cũ khi restart?
3. Hai autoscalers quản lý cùng Deployment có rủi ro gì?
4. Tính sơ bộ budget JDBC nếu 40 pods × pool 16, và vì sao potential peak không bằng active connections thực?
5. `terminationGracePeriodSeconds=10` có đủ cho chunk dài 45 giây? Cần drain/correctness policy nào?
6. Mất reply có chứng minh worker chưa commit DB/API không?
7. Vì sao `run.id` và `UUID.randomUUID()` làm cùng input có thể bị áp dụng hai lần?
8. Nên giữ input identity/checkpoint gì khi worker chuyển pod?
9. Cần metric nào để phân biệt thiếu worker với DB/API đã bão hòa?
10. Thiết kế test scale 8 → 16 → 40, worker crash và rollback image sao cho kết quả vẫn đúng.

**Định hướng trả lời:** Chỉ có 16 logical partitions được manager tạo nên thêm 40 pods có thể sinh idle workers; `gridSize` không tương đương replicas hay partition count mặc định. Một controller nên sở hữu autoscaling. Max DB potential connections là 40 × 16 = **640**, nhưng usage thực tùy đồng thời; cần cluster-wide budget. Khi scale-down phải ngừng nhận request mới và drain/rollback ở safe boundary; 10 giây có thể không đủ. JobInstance và partition input manifest/versions phải ổn định, business operation ID phải bền vững. Mất reply phải reconcile; không tạo identifying timestamp mới. Queue ready=0 chưa chứng minh business commit/publish hoàn tất. Test cần xác minh unique operations, StepExecution/restart, ACK/redelivery, pool/locks/429 và quality gate.

## 32. Checklist triển khai worker replicas

| Hạng mục | Tiêu chí đạt |
| --- | --- |
| **Kiến trúc** | Rõ remote partitioning, remote chunking hay custom queue |
| **Role** | Manager launch job; worker không auto-launch JobInstance |
| **Identity** | JobParameters/manifest, partition key và business operation ID ổn định |
| **Repository** | Shared JobRepository và transaction managers đúng |
| **Transport** | Broker request/reply/ACK/correlation được kiểm chứng |
| **Worker image** | Version tương thích message/StepExecutionContext/schema |
| **Replica control** | Một controller autoscaling sở hữu Deployment |
| **Concurrency** | Replicas, consumers/pod, partitions, gridSize được phân biệt |
| **DB budget** | Pool connections toàn cụm, OLTP headroom, lock/IO |
| **Resources** | CPU/memory/ephemeral disk requests/limits được benchmark |
| **Health** | Startup/liveness/readiness đúng, broker listener có drain |
| **Scaling** | HPA/KEDA trigger, min/max, cooldown và stabilization hợp lý |
| **Shutdown** | Graceful drain, ACK/reply, bounded grace và hard-stop recovery |
| **Restart** | Worker pod restart khác Spring Batch JobInstance restart |
| **Idempotency** | Stable business key, unique constraint/provider dedupe |
| **Fencing** | Custom queue có ownership/lease token khi cần |
| **Security** | ServiceAccount, secrets, TLS, least privilege, network policy |
| **Observability** | Worker/pod/broker/DB/JobRepository/business throughput |
| **Testing** | Scale up/down, rollout, crash, reply loss, restart, fault injection |
| **Reconciliation** | Source-output expected set, UNKNOWN và publish gate |
| **Runbook** | Có hướng xử lý worker stuck, DB overload, schema mismatch |

## Tài liệu tham khảo

- [Spring Batch Reference — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): phân biệt multi-threaded step, parallel steps và partitioning.
- [Spring Batch Reference — Spring Batch Integration](https://docs.spring.io/spring-batch/reference/spring-batch-integration.html): remote chunking và remote partitioning.
- [Spring Batch Reference — Configuring a Step for Restart](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/restart.html): `ItemStream`, ExecutionContext và checkpoint.
- [Spring Batch Reference — JobRepository](https://docs.spring.io/spring-batch/reference/job/configuring-repository.html): JobInstance, JobExecution và metadata.
- [Spring Batch Reference — Metadata Schema](https://docs.spring.io/spring-batch/reference/schema-appendix.html): trạng thái và counters của `StepExecution`.
- [Spring Batch Reference — Step Scope](https://docs.spring.io/spring-batch/reference/step/late-binding.html): late binding metadata theo partition.
- [Kubernetes — Deployments](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/): replicas, rollout strategy và availability.
- [Kubernetes — Horizontal Pod Autoscaling](https://kubernetes.io/docs/tasks/run-application/horizontal-pod-autoscale/): HPA metrics và behavior.
- [Kubernetes — Pod Lifecycle](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/): SIGTERM, graceful termination và readiness.
- [Kubernetes — Pod Disruptions](https://kubernetes.io/docs/concepts/workloads/pods/disruptions/): voluntary evictions và PodDisruptionBudget.
- [Kubernetes — CronJob](https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/): lịch manager jobs và missed schedules.
- [Kubernetes — Resource Management](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/): CPU/memory requests/limits.
- [Kubernetes — Network Policies](https://kubernetes.io/docs/concepts/services-networking/network-policies/): cô lập kết nối giữa workloads.
- [KEDA — Scalers](https://keda.sh/docs/latest/scalers/): event-driven scaling.
- [KEDA — RabbitMQ Queue Scaler](https://keda.sh/docs/latest/scalers/rabbitmq-queue/): scale theo queue length.
- [Spring Boot — Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): Micrometer/JVM metrics và exporters.
- [Spring Integration Reference](https://docs.spring.io/spring-integration/reference/): message channels và adapters.
- [PostgreSQL — Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html): transaction/row locks trong concurrent writers.

> **Ghi nhớ:** **Replica là năng lực chạy worker, không phải JobInstance, partition hay commit guarantee.** Scale up chỉ giúp khi còn parallel work **và** downstream còn khả năng xử lý. Scale down/rollout an toàn cần **dừng nhận việc mới, drain/reconcile in-flight, giữ checkpoint và business idempotency**; Kubernetes pod restart không tự giải quyết Spring Batch restart. Hãy quyết định replicas dựa trên **business throughput, backlog age, DB/broker saturation, SLA và tính đúng dữ liệu** — không chỉ số pods Ready.
