# Worker health và readiness trong Spring Batch

## Mục tiêu bài học

Một worker Spring Batch có thể **vẫn chạy JVM**, **vẫn trả HTTP 200 ở health endpoint**, nhưng không thể xử lý partition nào vì consumer chưa kết nối broker, JDBC pool cạn connection hoặc JobRepository không truy cập được. Ngược lại, một worker đang chạy chunk dài có thể tạm thời không nhận việc mới nhưng **không nên bị kill**: nó có thể đang giữ transaction và checkpoint chưa hoàn tất.

**Worker health và readiness** là thiết kế trả lời các câu hỏi: *process còn sống?*, *worker có thể nhận phần việc mới?*, *phần việc đã nhận có tiến triển?* và *dữ liệu được commit có đúng không?* Các câu hỏi này cần bằng chứng và hành động khác nhau.

Bài thuộc chương **Thiết kế worker**, module **SPRING_BATCH_SCALING_OPERATIONS**: mở rộng Spring Batch cho workload dữ liệu lớn qua multi-threaded step, parallel steps, partitioning và các mô hình phân tán; đồng thời đo bottleneck, bảo đảm thread safety, retry/restart và khả năng vận hành theo tài nguyên thực tế.

Học xong, bạn có thể:

- Phân biệt liveness, startup, readiness, draining, progress và business correctness.
- Thiết kế trạng thái sẵn sàng của worker remote chunking và remote partitioning.
- Sử dụng Spring Boot Actuator health groups, Kubernetes probes và custom HealthIndicator.
- Hiểu vì sao HTTP readiness **không tự pause RabbitMQ/Kafka consumers**.
- Gắn worker admission với consumer lifecycle, DB/HTTP pools và JobRepository.
- Triển khai graceful drain, rolling deploy, retry/restart và phát hiện stuck partitions.
- Viết unit/integration/fault-injection tests và runbook vận hành.

## 1. Health endpoint UP chưa chứng minh worker xử lý được việc

Một cluster có bốn worker JVM:

~~~text
worker-01  process=UP  HTTP /health=200  consumer=READY
worker-02  process=UP  HTTP /health=200  broker=DISCONNECTED
worker-03  process=UP  HTTP /health=200  jdbcPoolPending=25
worker-04  process=UP  HTTP /health=200  partition 20 phút không progress
~~~

Các process đều còn sống, nhưng trạng thái vận hành khác nhau. Worker 02 cần reconnect hoặc ngừng intake; worker 03 cần điều tra DB bottleneck hoặc điều chỉnh concurrency; worker 04 cần đối chiếu StepExecution, checkpoint, lock và thread dump.

Nếu cùng cấu hình liveness dựa vào broker connection, một outage chung có thể khiến **toàn bộ worker bị restart liên tục** đúng lúc broker/DB đang phục hồi. Vì vậy health signal phải gắn với **hành động cụ thể** của orchestrator và ứng dụng.

Một boolean healthy không thay thế được tiến độ từng partition, ACK/offset commit hay đối soát dữ liệu nghiệp vụ.

## 2. Phân biệt các trạng thái

| Khái niệm | Câu hỏi | Hành động |
| --- | --- | --- |
| **Liveness** | Process hỏng nội bộ đến mức phải restart? | Kubelet/supervisor restart khi lỗi thực sự không phục hồi |
| **Startup** | Đã hoàn tất bootstrap cần thiết chưa? | Cho đủ thời gian start trước khi áp probes thường |
| **Readiness** | Worker có an toàn để nhận **work mới**? | Cho phép hoặc ngừng admission |
| **Draining** | Có chủ động dừng nhận việc mới để shutdown? | Ngừng intake, giải quyết work đang chạy |
| **Progress** | Work đã nhận có thực sự tiến triển? | Metric, watchdog, cảnh báo và điều tra |
| **Correctness** | Business output đã commit đúng, đủ, không trùng? | JobRepository và business reconciliation |

**Liveness ≠ readiness**: worker có thể sống nhưng broker tạm unavailable; restart process không giúp broker khôi phục.

**Readiness ≠ progress**: worker đang drain có thể NOT_READY nhưng vẫn chạy một chunk.

**Progress ≠ correctness**: readCount tăng không chứng minh writer đã commit hoặc side effect không bị trùng.

## 3. Vòng đời worker có trạng thái rõ

Một state machine **do ứng dụng đề xuất**:

~~~mermaid
stateDiagram-v2
    [*] --> STARTING
    STARTING --> READY: Init, handler, consumer OK
    STARTING --> BLOCKED: Chưa đủ điều kiện
    BLOCKED --> READY: Phục hồi
    READY --> DEGRADED: Capacity giảm
    DEGRADED --> READY: Tài nguyên ổn định
    READY --> DRAINING: Scale-down/shutdown
    DEGRADED --> DRAINING: Scale-down/shutdown
    BLOCKED --> DRAINING: Scale-down/shutdown
    DRAINING --> STOPPED: Cleanup
    STOPPED --> [*]
~~~

- **STARTING:** context, listener hoặc dependencies đang bootstrap.
- **READY:** đã thỏa contract nhận thêm work.
- **DEGRADED:** vẫn có capacity hạn chế hoặc gần saturation.
- **BLOCKED:** tạm không được tiếp nhận work mới.
- **DRAINING:** ngừng intake nhưng cho phần việc đã nhận cơ hội hoàn thành.
- **STOPPED:** đóng process.

Đây không phải enum sẵn của Spring Batch/Kubernetes. Có thể ánh xạ READY sang readiness UP; trạng thái còn lại sang OUT_OF_SERVICE. Liveness vẫn UP khi BLOCKED do outage có thể hồi phục hoặc khi DRAINING.

### Một trạng thái hợp lệ

~~~text
admission = NOT_READY
activeStepExecutions = 1
currentStep = RUNNING
~~~

Worker đang drain: không nhận partition mới nhưng vẫn hoàn tất chunk/StepExecution hiện tại. Không được xem NOT_READY đồng nghĩa FAILED.

## 4. Liveness: chỉ dùng cho lỗi cục bộ khó phục hồi

Liveness nên trả lời: **restart chính process này có giúp nó quay lại trạng thái an toàn không?**

Không nên biến các điều sau thành điều kiện liveness mặc định:

- DB/broker/API ngoài có trả lời ngay thời điểm probe?
- JDBC pool có đang active bằng maximum?
- Queue age có vượt SLA?
- Worker CPU đang 100% trong lúc xử lý CPU-bound?
- Một partition có bị chậm do hot row/DB lock?

Nếu DB outage và mọi worker restart liên tục, khi DB phục hồi nó phải chịu cả reconnect storm lẫn request retry storm.

Liveness có thể thất bại khi phát hiện fatal local state corruption, core runtime chết vĩnh viễn hoặc deadlock cục bộ đã chứng minh không có đường recovery. Một probe khỏe mạnh phải **rẻ, nhanh và không có side effect**: không tạo test JobExecution, không scan bảng, không gọi API đắt tiền.

## 5. Readiness nghĩa là có thể nhận work mới

Một worker sẵn sàng có thể đang bận, miễn là có admission/backpressure đảm bảo không nhận vượt budget.

Các điều kiện thường cần:

1. Cấu hình, secrets và schema quan trọng hợp lệ.
2. Handler/StepLocator cần thiết đã đăng ký.
3. Broker consumer hoặc listener có thể tiếp nhận request theo protocol.
4. JobRepository và resource bắt buộc khả dụng theo policy.
5. DB/HTTP pools có cơ chế giới hạn tải, không nhận work vượt capacity an toàn.
6. Reply path hoạt động nếu worker phải gửi response để manager xác nhận completion.
7. Worker không đang drain/shutdown.

**Readiness không nên chạy một transaction DB nặng mỗi vài giây.** Dùng thông tin listener lifecycle, connection events, circuit breaker, pool metrics và lightweight cached checks.

### Tránh oscillation

Hikari pool có thể chuyển active từ 9/10 sang 10/10 connections trong milliseconds. Nếu mỗi lần đó readiness đổi UP/DOWN, worker sẽ bị flap. Sử dụng thresholds, hysteresis và khoảng thời gian ổn định; giữ readiness UP khi một pending request ngắn vẫn nằm trong capacity policy.

## 6. Startup khác sự cố vận hành

Worker có thể phải đọc config, init DataSource, load serializer, đăng ký StepLocator, kết nối broker và kiểm tra metadata schema trước khi nhận job.

Trong Kubernetes, **startupProbe** cho phép một ngân sách bootstrap dài hơn. Nếu startup chưa hoàn tất, liveness/readiness probes được trì hoãn theo cơ chế Kubernetes.

`ApplicationReadyEvent` chỉ cho biết Boot đã đi qua một mốc lifecycle, **không tự chứng minh** Kafka consumer đã được gán topic partitions, RabbitMQ listener đã subscribe hoặc JobRepository usable. Controller chỉ nên bật READY khi các điều kiện của worker thực sự thỏa.

Startup cần một deadline hợp lý: nếu schema không tương thích hoặc cấu hình step name sai, fail rõ thay vì kẹt vô hạn.

## 7. Kubernetes readiness không tự pause broker consumer

Đây là bẫy quan trọng nhất với message-driven worker. Kubernetes readiness thường dùng để quyết định pod có được đưa vào **Service endpoints** cho HTTP/gRPC traffic không. Nhưng Kafka/RabbitMQ consumers là các client chủ động kết nối ra broker.

~~~mermaid
flowchart TB
    K["Kubelet readinessProbe"] --> S["Pod Ready/Service endpoints"]
    S -. "Không tự điều khiển" .-> C["Kafka/RabbitMQ consumer"]
    A["Worker admission controller"] -->|pause/stop/start theo contract| C
    C --> W["Handler / StepExecution"]
~~~

Nếu `/readyz` trả 503 nhưng listener vẫn hoạt động, worker **vẫn có thể nhận partition mới**. Muốn thực sự dừng cấp việc phải điều khiển listener/consumer qua API của adapter hoặc có admission boundary phù hợp.

Readiness cũng không hủy message đã prefetched/unacked hay StepExecution đang RUNNING. Cần **drain/recovery policy** cho work đã nhận.

## 8. Remote chunking: cần kiểm tra cả reply path

Ở remote chunking, manager thường đọc/chia chunk; worker nhận chunk, process/write và trả reply.

~~~mermaid
flowchart LR
    M["Manager read/chunk"] --> B[["Request queue"]]
    B --> C["Worker consumer"]
    C --> P["Processor/Writer"]
    P --> DB[("Business DB")]
    P --> R[["Reply destination"]]
    R --> M
~~~

Readiness của worker remote chunking cần xem:

- Consumer có thể nhận chunk và deserialize đúng version.
- Processor/writer/SDK đã init, tài nguyên DB/API thiết yếu phù hợp.
- Có đường publish reply và correlation hợp lệ.
- Có giới hạn số chunk inflight.
- Không trong trạng thái drain.

### Worker commit nhưng reply bị mất

~~~text
Manager: request C42 SENT
Worker:  DB COMMITTED
Reply:   LOST / UNKNOWN
Manager: TIMEOUT
~~~

Manager timeout **không** chứng minh DB chưa commit. Broker redelivery có thể đưa chunk C42 tới worker lần nữa. Writer cần idempotency theo business key, request/reply correlation và reconciliation, không retry blind.

**Remote chunking không mặc nhiên có worker StepExecution riêng cho mỗi chunk**, khác với remote partitioning.

## 9. Remote partitioning: JobRepository và StepExecution ownership

Trong remote partitioning, manager tạo worker StepExecutions/ExecutionContexts rồi dispatch yêu cầu; worker đọc metadata và tự chạy worker step.

~~~mermaid
sequenceDiagram
    participant M as Manager
    participant J as JobRepository
    participant B as Broker
    participant W as Worker
    participant D as Business DB

    M->>J: Tạo worker StepExecution
    M->>B: Dispatch StepExecutionRequest
    B->>W: Yêu cầu
    W->>J: Load StepExecution/context
    W->>W: Run worker step
    W->>D: Commit chunks
    W->>J: Update checkpoint/status
    W-->>M: Reply/status theo protocol
~~~

Readiness cần xét handler/StepLocator đã đăng ký, JobRepository/metadata schema đúng, resource pools đủ, consumer intake và chính sách drain. Nhưng readiness **không phải lease**: nếu manager timeout, worker cũ có thể vẫn đang xử lý StepExecution. Không tự dispatch cùng StepExecution tới worker mới khi chưa reconcile ownership/metadata và recovery policy.

### Readiness không phải status của StepExecution

Worker có thể NOT_READY vì đang drain trong khi một StepExecution vẫn RUNNING. Cũng có thể READY khi không có partition active. JobRepository giữ metadata từng execution, health state chỉ nói về khả năng worker nhận work mới.

## 10. Spring Boot Actuator health groups

Với worker Spring Boot có web server và `spring-boot-starter-actuator`, có thể bật các health groups cho kubelet:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
      group:
        readiness:
          include: readinessState,workerAdmission
  endpoints:
    web:
      exposure:
        include: health,info
~~~

Ở cấu hình Boot 3.x tương ứng, các paths thường có:

- `/actuator/health/liveness`
- `/actuator/health/readiness`
- `/livez` và `/readyz` trên main server port khi additional paths được hỗ trợ/bật.

Giả định có custom indicator ID `workerAdmission` ở phần tiếp theo. Spring Boot availability state **không tự kiểm tra toàn bộ broker consumer lifecycle**. Cũng cần kiểm tra health status mapping; DOWN/OUT_OF_SERVICE thường trả HTTP 503 theo cấu hình mặc định.

Nếu management port khác main application port, endpoint trên management port UP chưa chứng minh main server hoạt động. Cần kiểm thử paths và ports thực trong image đã triển khai.

## 11. Java: custom HealthIndicator cho worker admission

Một HealthIndicator phản ánh trạng thái **đã được lifecycle controller cập nhật** thay vì tự query DB/broker mỗi lần kubelet poll.

~~~java
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component("workerAdmissionHealthIndicator")
public final class WorkerAdmissionHealthIndicator
        implements HealthIndicator {

    public enum State {
        STARTING, READY, BLOCKED, DRAINING
    }

    private final AtomicReference<State> state =
            new AtomicReference<>(State.STARTING);

    public State currentState() {
        return state.get();
    }

    public void markReady() {
        state.set(State.READY);
    }

    public void markBlocked() {
        state.set(State.BLOCKED);
    }

    public void markDraining() {
        state.set(State.DRAINING);
    }

    @Override
    public Health health() {
        State current = state.get();

        if (current == State.READY) {
            return Health.up()
                    .withDetail("workerState", current.name())
                    .build();
        }
        return Health.outOfService()
                .withDetail("workerState", current.name())
                .build();
    }
}
~~~

Spring Boot thường rút suffix `HealthIndicator` từ bean name `workerAdmissionHealthIndicator` để tạo contributor ID `workerAdmission`. Cần test endpoint ở version thật nếu có custom registry.

### Điều ví dụ cố ý không làm

- Không truy vấn JobRepository hoặc broker trong `health()`.
- Không tự biết listener đã subscribe hay executor còn capacity.
- Không tự pause/start consumer.
- Không thay đổi StepExecution status hoặc transaction.
- Không tự bảo đảm idempotency.

**Indicator chỉ hiển thị trạng thái.** Một component điều phối vòng đời phải gọi `markReady()` **sau khi** kiểm tra đầy đủ điều kiện nhận work, `markBlocked()` khi intake không còn an toàn, và `markDraining()` trước khi dừng nhận việc mới.

### Tránh controller rời rạc

Nếu listener reconnect gọi `markReady()` nhưng database vẫn down, readiness sẽ sai. Cần một controller hợp nhất **nhiều nguồn sự kiện** thay vì để callback cuối ghi đè một boolean.

## 12. Admission controller: một nguồn tính trạng thái đáng tin

Những sự kiện đầu vào:

~~~text
onBootstrapComplete
onListenerStarted
onListenerDisconnected
onRequiredDatabaseUnavailable
onRequiredDatabaseRecovered
onJobRepositoryFailure
onJobRepositoryRecovered
onDrainRequested
onShutdownComplete
~~~

Pseudocode:

~~~text
readyToAccept =
    bootstrapComplete
    AND handlersRegistered
    AND listenerCanReceive
    AND requiredDependenciesWithinPolicy
    AND admissionEnabled
    AND NOT draining
~~~

Đây là hợp đồng ứng dụng, không phải cấu hình tự động của Spring Integration.

### Hai hướng triển khai

**Hướng A — Event-driven:** cập nhật trạng thái dựa trên listener lifecycle events, error/recovery callbacks và scheduled lightweight checks. Ưu điểm ít tạo tải mới cho downstream.

**Hướng B — Cached health state:** định kỳ kiểm tra thành phần thực sự cần thiết với deadline ngắn rồi cache trạng thái. Probe HTTP đọc cache, không tự thực hiện network call tốn thời gian.

Dù chọn hướng nào, phải xử lý concurrency của các callbacks, stale state, timeout và transitions. Một reducer thread-safe hoặc snapshot trạng thái immutable giúp tránh race.

### Điều quan trọng: health signal và actual intake phải nhất quán

Khi controller đánh dấu BLOCKED, cần điều khiển listener theo API được hỗ trợ hoặc chặn admission trước lúc nhận phần việc. Nếu `/readyz` trả 503 nhưng consumer vẫn đọc và ACK request sai, chính sách chưa được thực thi.

Đừng để health controller tạo thêm một hệ thống JobRepository/partition ownership song song; nó chỉ điều phối intake theo metadata và protocol của framework.

## 13. Kubernetes: startup, liveness và readiness probes

Ví dụ worker có main HTTP server port 8080, cấu hình Actuator additional paths như phần 10:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: batch-worker
spec:
  replicas: 4
  selector:
    matchLabels:
      app: batch-worker
  template:
    metadata:
      labels:
        app: batch-worker
    spec:
      terminationGracePeriodSeconds: 120
      containers:
        - name: worker
          image: example.internal/batch-worker:versioned
          ports:
            - containerPort: 8080
          startupProbe:
            httpGet:
              path: /livez
              port: 8080
            periodSeconds: 5
            failureThreshold: 30
            timeoutSeconds: 2
          livenessProbe:
            httpGet:
              path: /livez
              port: 8080
            periodSeconds: 10
            failureThreshold: 3
            timeoutSeconds: 2
          readinessProbe:
            httpGet:
              path: /readyz
              port: 8080
            periodSeconds: 5
            failureThreshold: 3
            timeoutSeconds: 2
~~~

**Cách đọc:**

- `startupProbe` cho khoảng 30 lần × 5 giây, tức **xấp xỉ 150 giây** startup budget; scheduling/timeout thực tế còn phụ thuộc kubelet.
- Khi startup chưa thành công, liveness/readiness probes được trì hoãn.
- Liveness failure đủ ngưỡng có thể khiến container restart.
- Readiness failure chủ yếu tác động Service endpoint membership, **không tự dừng consumer broker**.
- `terminationGracePeriodSeconds` là ngân sách xử lý termination, không phải bảo đảm mọi chunk được commit.

Các giá trị chỉ minh họa; phải điều chỉnh theo JVM startup, time-to-ready của listener, GC pauses, p99 chunk duration và SLA thực tế.

### Cảnh báo về management port

Nếu health endpoint chạy trên management port riêng, main application server có thể hỏng trong khi management port vẫn trả 200. Additional health paths trên main port giúp nhận biết một số lỗi đó. Tuy nhiên trong worker chỉ có broker consumer, **main HTTP port vẫn không chứng minh consumer hoạt động**; custom admission indicator mới là tín hiệu bổ sung.

## 14. Worker headless: readiness không nhất thiết phải là HTTP

Một worker có thể là Java process thuần message consumer, không bật `spring-boot-starter-web`. Khi đó không có HTTP URL health mặc định.

Các cách triển khai:

| Cách | Ưu điểm | Cần lưu ý |
| --- | --- | --- |
| Bật management HTTP server nhẹ | Dùng Actuator và Kubernetes HTTP probe | Cần bảo vệ port, cấu hình web server phù hợp |
| Sidecar/supervisor health endpoint | Tách vận hành | Sidecar phải nhận trạng thái **thật** của worker, không stale |
| Kubernetes exec probe | Không mở HTTP | Spawn process tốn chi phí, command timeout và marker stale |
| TCP socket probe | Đơn giản | Socket mở không đồng nghĩa worker có consumer |
| External monitoring | Có góc nhìn cluster | Không thay admission control nội bộ |

Nếu dùng ready marker file, phải xóa/đặt lại đúng khi start, broker disconnect và drain. File cũ còn tồn tại sau crash **không** chứng minh worker ready.

**Readiness là hợp đồng vận hành**, không bắt buộc mọi worker phải dùng HTTP. Dù chọn cách nào, process vẫn phải điều khiển intake và phục hồi phù hợp Spring Batch.

## 15. RabbitMQ: listener state, prefetch, ACK và drain

Với RabbitMQ, cần phân biệt các lớp:

~~~text
Connection → Channel → Consumer registration
    → Prefetched/unacked messages → Handler
    → DB transaction → Reply publish → ACK theo container policy
~~~

Một connection khỏe không chứng minh consumer đã subscribe đúng queue. Một consumer được stop có thể vẫn còn message chưa ACK hoặc handler đang chạy.

### Khi worker trở thành NOT_READY

- Giảm/dừng intake thông qua lifecycle API **đúng loại inbound adapter/gateway/container**.
- Quan sát số active handlers và prefetched/unacked.
- Để work đang chạy có deadline rõ.
- Không báo work đã hoàn thành chỉ vì health đã đổi.
- Nếu worker chết trước ACK, broker có thể redeliver; writer phải idempotent.

### Lỗi sau DB commit

~~~text
T0  RabbitMQ giao chunk C42
T1  Worker xử lý và DB COMMIT
T2  Worker chết trước ACK/reply
T3  Broker có thể redeliver C42
~~~

Đây là cửa sổ duplicate tự nhiên. **ACK broker không atomic với business DB commit** nếu không có thiết kế transaction chuyên biệt bao trùm cả hai. Readiness không ngăn ghi trùng; cần khóa nghiệp vụ, transaction, idempotency ledger và reconciliation.

### Không dùng requeue nóng làm chiến lược health

Nếu DB outage mà worker liên tục NACK/requeue ngay, nó có thể tiêu CPU và tăng tải DB. Dùng bounded retry, backoff/jitter, DLQ/quarantine và trạng thái BLOCKED khi cần thiết.

## 16. Kafka: pause/stop không giống readiness hay offset commit

Trong Kafka, consumer group sở hữu topic partitions theo cơ chế assignment/rebalance. Một worker NOT_READY có thể tạm pause listener để không tiếp nhận thêm records, nếu container hỗ trợ, nhưng phải hiểu:

- Pause không hủy record đã poll/đang xử lý.
- Consumer có thể vẫn cần poll để duy trì group membership.
- Stop container có thể gây rebalance và chuyển ownership partitions.
- Offset commit không mặc nhiên atomic với writer DB transaction.
- Kafka partition order không tự bảo đảm DB commit order khi handler async.
- Retry topic có thể cho record sau vượt record lỗi trước.

Nếu handler block quá lâu so với `max.poll.interval.ms` hoặc không đáp ứng poll contract, Kafka có thể trigger rebalance. HTTP liveness vẫn UP không có nghĩa consumer còn quyền sở hữu partition.

### Readiness nên dùng tín hiệu nào?

Listener/container running state, assignment/paused state, reconnect/rebalance activity, offset errors và downstream admission budget. Không nên lấy **số JVM** hoặc **consumer group size** làm bằng chứng duy nhất.

**Không dùng Thread.sleep dài trong Kafka poll thread** để tạo backpressure. Dùng pause/resume và cấu hình listener theo API/version, sau đó kiểm tra behavior khi DB outage/rebalance.

## 17. Manager dispatch và worker capacity phải cùng được giới hạn

Trong partitioning, manager có thể tạo 100 partitions nhưng cluster chỉ xử lý tám worker StepExecutions cùng lúc. Điều này không mặc nhiên là lỗi nếu có queue và SLA rõ.

Nên phối hợp:

1. Manager outstanding requests/partitions limit.
2. Broker queue depth, oldest message age hoặc consumer lag.
3. Consumer concurrency và worker executor queue.
4. JDBC/HTTP pool budgets trên mọi worker JVM.
5. JobRepository metadata load và transaction capacity.
6. Reply/correlation handling khi worker hoàn thành đảo thứ tự.

~~~mermaid
flowchart LR
    M["Manager dispatch"] --> G{"Outstanding dưới ngưỡng?"}
    G -->|Có| B[["Broker queue"]]
    G -->|Không| WAIT["Backpressure"]
    B --> A["Admission boundary"]
    A --> W["Worker step/handler"]
    W --> DB[("DB/JobRepository")]
    W -. "Reply/status" .-> M
~~~

Sơ đồ là luồng logic: broker **không tự gọi /readyz** để quyết định message delivery. Ứng dụng phải làm chủ listener/admission thực.

Nếu mọi worker BLOCKED nhưng manager tiếp tục publish, queue age tăng; cần chính sách throttle, stop/fail job có kiểm soát hoặc chờ trong deadline, tránh khiến broker retention/message TTL thành nguồn mất việc ngoài dự tính.

## 18. Resource pool saturation không phải liveness failure

Một worker có thể có 16 consumer threads nhưng chỉ bốn JDBC connections. Khi DB query chậm, JDBC pool pending tăng và các consumer chờ connection. JVM còn sống, không nên restart chỉ vì pool active bằng maximum.

| Metric | Tín hiệu cần điều tra |
| --- | --- |
| JDBC active, idle, pending | Pool có bị nghẽn không? |
| Connection acquire p95/p99 | Handler chờ bao lâu trước query? |
| DB lock wait/deadlocks | Nguồn nghẽn có phải contention? |
| CPU/throttling | Worker có CPU-bound không? |
| Heap/GC pauses | Prefetch/chunk buffers có quá lớn không? |
| HTTP 429/503 và client pending | Quota hay API outage? |
| Queue age/unacked/lag | Công việc đang chờ ở đâu? |
| Active StepExecutions | Có work đang chạy và progress không? |

### Cách xử lý

- Nếu DB còn capacity và pool nhỏ thật: cân nhắc tăng pool **có ngân sách**.
- Nếu DB đã bão hòa: giảm concurrency, tối ưu query/index/lock.
- Nếu API quota thấp: rate limit, bulkhead và Retry-After.
- Nếu executor queue dài: giới hạn inflight, tránh queue vô hạn.
- Nếu SDK mất thread safety: sửa object lifecycle trước khi tăng worker.

**Không biến transient resource saturation thành NOT_READY theo kiểu bật/tắt liên tục.** Có thể giữ READY với backpressure hoặc chuyển DEGRADED; nếu không thể nhận thêm work an toàn trong thời gian đủ dài, chuyển BLOCKED có hysteresis.

## 19. Work progress khác process health

Một worker có thể READY nhưng đang có StepExecution chạy quá lâu mà không tiến triển. Cần metric/work monitoring riêng.

Gợi ý quan sát mỗi StepExecution/partition:

- `lastCommittedChunkAt`: mốc commit gần nhất nếu được instrument đáng tin.
- `readCount`, `writeCount`, `commitCount` và `rollbackCount`.
- `lastProgressAt`: mốc có thay đổi có ý nghĩa, không phải mỗi heartbeat timer.
- `stepExecutionId`, partition name, worker instance.
- `queueAge`/message processing duration khi có middleware.
- DB lock wait, connection acquire latency và thread stack trong khoảng chậm.

**Đừng dùng mỗi HTTP heartbeat** để kết luận một partition còn đang làm việc. Timer có thể tiếp tục phát heartbeat dù handler bị treo trong DB lock.

### Vì sao slow partition chưa chắc bị kẹt?

Một chunk CPU nặng có thể xử lý hợp lệ 15 phút mà readCount chỉ tăng sau commit. Nếu watchdog dựa cứng vào “không có commit trong 60 giây” rồi kill worker, nó sẽ liên tục hủy những chunk lớn.

Cần phân loại processing phases, p99 duration và business deadline. Watchdog là cơ chế **cảnh báo và đối soát**, không tự nhận quyền restart StepExecution thiếu an toàn.

## 20. Stale StepExecution và worker zombie

Trong remote partitioning, manager giao partition A cho worker-1. Sau đó mất kết nối:

~~~text
Manager: chưa nhận reply từ worker-1
Worker-1: vẫn đang chạy, DB transaction active
Worker-2: sẵn sàng nhận việc
~~~

Nếu hệ thống tự giao A ngay cho worker-2 chỉ vì manager timeout, cả hai có thể ghi cùng dữ liệu. Đây là **duplicate execution** ở cấp StepExecution, không phải lỗi readiness đơn thuần.

### Những bằng chứng cần kết hợp

1. Trạng thái StepExecution trong JobRepository.
2. Worker instance còn sống không và có còn chạy work đó không.
3. Heartbeat/progress có thực sự mới và gắn đúng execution không.
4. Business DB/ledger đã commit phần nào.
5. Broker request/reply/ACK state.
6. Lease/ownership/fencing nếu kiến trúc có bổ sung chúng.

Spring Batch JobRepository **không mặc nhiên là distributed lease/fencing token** cho mọi mô hình tự retry dispatch. Nếu cần bảo đảm một partition không bị hai worker thực thi đồng thời, phải thiết kế ownership/recovery riêng hoặc dùng cơ chế framework đã hỗ trợ đúng phạm vi.

### Stuck không đồng nghĩa crash

Một partition bị kẹt DB lock có thể cần cancel query, giảm concurrency hoặc sửa transaction chứ không cần khởi pod mới. Kill worker khi transaction đang commit có thể tạo thêm trạng thái “commit đã xảy ra nhưng manager chưa biết”.

## 21. Graceful shutdown: draining trước, shutdown sau

Một quy trình scale-down/rolling deploy an toàn:

1. **Đánh dấu DRAINING** và readiness NOT_READY để orchestrator thấy trạng thái.

2. **Ngừng nhận work mới** qua broker listener/admission boundary tương ứng. Không chỉ đổi HTTP status.

3. **Theo dõi active handlers/StepExecutions** và message prefetched/unacked. Không cho task queue phát sinh thêm mà không kiểm soát.

4. **Cho work đang chạy kết thúc trong deadline hợp lý**, commit/rollback và gửi reply theo protocol.

5. **Dọn resource**: đóng listener/consumer, executors, JDBC/HTTP clients và flush telemetry theo lifecycle.

6. **Nếu hết deadline**, phần chưa hoàn tất cần được broker/JobRepository phục hồi; không giả định mọi work đã commit.

7. **Đối soát sau rollout**: StepExecution status, duplicate, lag, DLQ và business keys.

Một trạng thái không hiếm:

~~~text
workerAdmission = DRAINING
readiness = OUT_OF_SERVICE
liveness = UP
activeStepExecutions = 1
lastCommitAt = gần đây
~~~

Đây là healthy drain, không phải lỗi cần liveness restart.

### Spring Boot graceful shutdown không đủ cho worker messaging

Với web server, cấu hình như sau hỗ trợ HTTP graceful shutdown:

~~~yaml
server:
  shutdown: graceful
spring:
  lifecycle:
    timeout-per-shutdown-phase: 90s
~~~

Nhưng cấu hình đó **không tự đảm bảo** mọi Spring Integration inbound adapter, RabbitMQ/Kafka listener và worker step được drain đúng protocol. Cần lifecycle hooks đúng component, thứ tự đóng và test khi process bị kill.

## 22. Kubernetes termination, preStop và thứ tự ngắt intake

Khi kubelet terminate pod, tín hiệu stop và grace period có thể đến khi worker vẫn giữ partition. Cần xác định:

- Ai đổi worker sang DRAINING trước?
- Ai tắt consumer intake?
- Ai chờ handler active?
- Khi nào gửi reply/ACK/commit offset?
- Bao lâu chờ trước khi force terminate?
- Ai reconcile work chưa rõ kết quả?

### Grace period phải có ngân sách

Giả sử chunk p99 duration 45 giây, có thể cần thêm thời gian gửi reply, rollback và đóng connection. Một grace period 10 giây thường không đủ cho load này, nhưng tăng vô hạn cũng không giải quyết hung worker. Chọn thời gian dựa trên SLO và failure test.

### preStop hook không phải transaction protocol

Kubernetes `preStop` có thể gọi endpoint nội bộ để bắt đầu drain, nhưng endpoint phải được xác thực và idempotent; hook cũng có deadline và có thể không chạy trong một số failure/crash. Không dựa toàn bộ tính đúng vào hook.

**Thiết kế bắt buộc phải chịu kill đột ngột.** Graceful shutdown giảm xác suất redelivery, không loại bỏ cửa sổ worker commit trước khi manager nhận reply.

### Rolling deploy khác phiên bản

Manager/worker khác phiên bản có thể không tương thích message payload, StepExecutionRequest hoặc serializer. Health READY phải phản ánh khả năng dùng protocol tương ứng; nhưng cần thêm compatibility test và rollout strategy. Tăng replica không sửa protocol mismatch.

## 23. Worker thuần scheduled job: readiness phải gắn với cách nhận việc

Không phải mọi Spring Batch worker đều là message consumer. Một process có thể:

- Nhận request qua RabbitMQ/Kafka.
- Được manager điều phối qua remote partitioning.
- Nhận lệnh qua HTTP endpoint nội bộ.
- Tự launch Job qua scheduler hoặc command-line.
- Chạy một worker step định kỳ bằng orchestration bên ngoài.

Mỗi mô hình có **admission boundary** khác nhau. Với HTTP worker, readiness false giúp Service không định tuyến thêm HTTP request. Với message worker, phải điều khiển consumer. Với scheduler/CLI worker, readiness HTTP **không tự ngăn cron/scheduler launch job**.

Nếu process vẫn có scheduled job triggers khi `ready=false`, scheduler phải tham chiếu admission policy hoặc được pause/disallow launch theo lifecycle. Nhưng **không tự hủy job đang RUNNING** chỉ vì readiness false: nó có transaction, checkpoint và stop/restart protocol riêng.

### Một câu hỏi thiết kế bắt buộc

**Ai có quyền cấp work cho worker khi nó NOT_READY?**

Nếu không trả lời bằng một component và API cụ thể, hệ thống mới có tín hiệu observability chứ chưa có kiểm soát readiness thật.

## 24. Retry storm: đừng dùng readiness và liveness để che nguyên nhân

Khi DB down, nhiều tầng có thể tự retry:

- Producer publish retry.
- Broker requeue/redelivery.
- Integration handler retry advice.
- Spring Batch chunk/item retry.
- Manager request timeout/retry.
- Job restart.

Nếu worker liveness cũng fail theo DB, container restart liên tục; mỗi lần khởi động lại có thể làm mất counters trong memory và tạo thêm reconnect/publish attempts.

### Retry budget có chủ đích

| Tầng | Giới hạn |
| --- | --- |
| Handler/worker | Max attempts, backoff + jitter |
| Broker | Delayed retry/DLQ, không requeue nóng vô hạn |
| Manager | Outstanding requests limit, timeout/reconciliation |
| Batch step | Fault-tolerant retry/skip theo business exception |
| Job restart | Checkpoint ổn định, giới hạn số execution |
| Database/API | Idempotency key, unique constraint, quota |

Readiness BLOCKED có thể **giảm intake khi downstream outage**, nhưng không đồng nghĩa các request đã nhận được ACK thành công. Các request đang inflight phải được drain, fail có trạng thái rõ hoặc redeliver theo policy.

### Phân loại lỗi

- Lỗi mạng/DB tạm thời: reconnect/backoff, có thể giữ liveness UP.
- Payload sai schema hoặc step name không đăng ký: thường fail fast, quarantine/DLQ.
- Lỗi permission/secret invalid: BLOCKED hoặc fail startup theo chính sách, không retry liên tục.
- Deadlock SQL: phân tích transaction, có thể retry bounded.
- Business validation không thể phục hồi bằng chờ: không dùng readiness flap để “sửa”.

## 25. Health và idempotency: hai ranh giới khác nhau

Giả sử một worker xử lý chunk chứa event E42:

~~~text
T0  Broker giao request C42
T1  Worker ghi event E42
T2  Business DB COMMIT
T3  JVM chết trước reply/ACK
T4  Request C42 redeliver tới worker khác
~~~

Cả hai worker có thể có liveness/readiness hoàn toàn hợp lệ ở thời điểm xử lý. **Không có health probe nào tự ngăn side effect bị nhân đôi**.

Cần business idempotency. Với event identity ổn định, mẫu ledger:

~~~sql
CREATE TABLE applied_business_event (
    event_id UUID PRIMARY KEY,
    payload_sha256 CHAR(64) NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

Trong cùng business transaction, xác lập event theo unique constraint và thực hiện business update một lần. Nếu duplicate cùng event ID và payload hợp lệ, tránh áp dụng lại; nếu cùng ID nhưng payload khác, báo conflict.

Không dùng `messageId`, `correlationId`, `partitionName` hoặc `jobExecutionId` mặc định làm khóa chống lặp xuyên job restart. Các ID đó có phạm vi giao nhận/execution khác business operation.

Với HTTP side effect ngoài DB transaction, cần idempotency key ở API, outbox/inbox hoặc reconciliation riêng. Health READY chỉ nói **khả năng nhận việc**, không chứng minh exactly-once effect.

## 26. Metrics tối thiểu cho readiness và tiến độ worker

Một dashboard hữu ích cần tách **worker admission** khỏi **execution progress**.

| Metric/log field | Câu hỏi |
| --- | --- |
| `worker_admission_state` | READY/BLOCKED/DRAINING đang ở trạng thái nào? |
| `worker_readiness_transition_total` | Có flap nhiều lần không? |
| `worker_listener_connected` | Consumer có kết nối/bound không? |
| `worker_active_handlers` | Bao nhiêu request đang xử lý? |
| `worker_active_step_executions` | Bao nhiêu partition StepExecution đang chạy? |
| `worker_oldest_active_work_age` | Work lâu nhất đã chạy bao lâu? |
| `worker_last_progress_age` | Đã bao lâu không có progress thực? |
| `broker_oldest_message_age` | Công việc đang chờ trong broker bao lâu? |
| `broker_redeliveries_total` | Có nhiều request giao lại không? |
| `worker_reply_failures_total` | Có xử lý xong mà reply lỗi không? |
| `job_repository_write_latency` | Metadata/checkpoint có chậm không? |
| `jdbc_pool_pending` | Pool có cạn hoặc chờ không? |
| `db_lock_wait` | Worker có tranh lock? |
| `worker_retry_attempts_total` | Retry đang khuếch đại tải? |
| `business_reconciliation_failures_total` | Kết quả cuối có sai? |

Tên metric chỉ là **gợi ý**, không phải metric tự sinh mặc định của Spring Batch/Actuator.

### Tránh high cardinality

Không đưa mỗi `stepExecutionId`, `partitionName`, `correlationId` hoặc business customer ID làm Prometheus label mặc định khi số giá trị có thể lên hàng chục nghìn/hàng triệu. Đặt chúng trong structured logs/traces; metric labels nên là `job`, `step`, `status`, `workerPool`, `errorCategory` có số giá trị kiểm soát.

## 27. Log readiness transitions có lý do, không log mỗi probe

Một endpoint được kubelet gọi mỗi năm giây có thể tạo hàng triệu log vô ích nếu ghi INFO mỗi lần.

Thay vào đó log **khi state thay đổi**:

~~~text
INFO  event=worker_admission_changed
      from=STARTING to=READY
      reason=CONSUMER_BOUND
      workerInstance=worker-03

WARN  event=worker_admission_changed
      from=READY to=BLOCKED
      reason=REPLY_BROKER_UNAVAILABLE
      activeStepExecutions=2
      workerInstance=worker-03

INFO  event=worker_admission_changed
      from=BLOCKED to=READY
      reason=DEPENDENCY_RECOVERED
      workerInstance=worker-03

INFO  event=worker_admission_changed
      from=READY to=DRAINING
      reason=ROLLING_DEPLOY
      activeStepExecutions=1
      workerInstance=worker-03
~~~

Với mỗi transition nên có:

- Timestamp UTC và worker instance/version.
- State trước/sau.
- Mã lý do có tập giá trị hữu hạn.
- Active handlers/StepExecutions và queue age nếu phù hợp.
- Job/StepExecution IDs liên quan trong logs/traces chi tiết, không phải metric label.
- Mốc drain deadline khi chuyển sang DRAINING.

**Đừng log secret, password, toàn message payload hay raw exception có token** chỉ vì readiness sai. Health response cũng nên hạn chế chi tiết hiển thị cho đối tượng không có quyền.

## 28. Hysteresis: tránh READY/BLOCKED flap

Một readiness controller thay trạng thái mỗi lần connection pool hết một slot có thể khiến:

1. Một loạt pod NOT_READY đồng thời.
2. Controller tạm dừng consumer hàng loạt.
3. Queue age tăng, manager timeout.
4. Pod READY trở lại và nhận flood requests.
5. DB chưa phục hồi bị quá tải lần nữa.

### Chính sách minh họa

| Tín hiệu | Thời gian/ngưỡng giả định | Hành động |
| --- | --- | --- |
| Broker disconnect | Mất connection chưa phục hồi trong 5 giây | Chuyển BLOCKED, giảm intake |
| DB pool pending | Cao trên ngưỡng liên tục 30 giây | DEGRADED, hạn chế concurrency |
| DB không thể thực hiện thao tác thiết yếu | Lỗi xác định qua nhiều lần quan sát | BLOCKED |
| Dependency phục hồi | 20 giây ổn định và listener bound | Chuyển READY |
| Shutdown requested | Ngay sau khi đánh dấu drain | DRAINING, không nhận work mới |

Các giá trị **chỉ minh họa**. Mọi delay làm tăng reaction time; với lỗi nguy hiểm, không nên đợi 30 giây nếu nhận thêm work có thể làm mất dữ liệu. Với lỗi chập chờn, hysteresis giúp hệ thống ổn định.

Quan trọng là tách **health observations** khỏi **admission decision**. Một số lần timeout riêng lẻ có thể đưa worker DEGRADED mà không cần tuyên bố process chết.

## 29. Unit test HealthIndicator và lifecycle state

Kiểm thử nhỏ nên chứng minh trạng thái ban đầu không READY, chuyển trạng thái đúng và không nhầm liveness với readiness.

Ví dụ JUnit 5 cho lớp ở phần 11:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.boot.actuate.health.Status;

class WorkerAdmissionHealthIndicatorTest {

    @Test
    void notReadyUntilExplicitlyAllowedAndBlockedDuringDrain() {
        WorkerAdmissionHealthIndicator indicator =
                new WorkerAdmissionHealthIndicator();

        assertEquals(
                Status.OUT_OF_SERVICE,
                indicator.health().getStatus());

        indicator.markReady();
        assertEquals(
                Status.UP,
                indicator.health().getStatus());

        indicator.markDraining();
        assertEquals(
                Status.OUT_OF_SERVICE,
                indicator.health().getStatus());
    }
}
~~~

Test này xác minh **indicator state machine đơn giản**, không chứng minh listener đã pause hay JobRepository đang chạy. Cần thêm tests ở các boundary thật.

### Test nâng cao controller

- Consumer bound nhưng DB unavailable → vẫn BLOCKED.
- DB recovered nhưng handler chưa đăng ký → vẫn BLOCKED.
- Tất cả điều kiện đạt → READY đúng một lần.
- Broker disconnect từ READY → BLOCKED và intake thực sự dừng theo policy.
- Transition DRAINING → không được tự READY lại vì một callback reconnect muộn.
- Event đến đồng thời từ hai threads → state nhất quán.
- Flapping threshold/hysteresis → không toggle liên tục.
- Indicator `health()` không gọi DB/API; thời gian đáp ứng thấp và ổn định.

## 30. Integration test Actuator và consumer admission

Với Spring Boot test có Actuator và messaging listener thật, phải kiểm tra cả **HTTP response** lẫn **khả năng nhận work**.

| Bước | HTTP readiness | Consumer behavior kỳ vọng |
| --- | --- | --- |
| Khởi tạo nhưng chưa bound | 503/OUT_OF_SERVICE | Không xử lý request mới |
| Listener ready + dependencies OK | 200/UP | Nhận request theo budget |
| Chủ động BLOCKED | 503/OUT_OF_SERVICE | Ngừng intake mới; work cũ theo drain policy |
| Đang DRAINING | 503/OUT_OF_SERVICE | Không nhận việc mới, có thể hoàn tất work active |
| Sau stop/restart hợp lệ | Theo bootstrap rồi READY | Consumer reconnect và khôi phục state |

HTTP status ở đây dựa trên default Boot mapping và group configuration đang kiểm thử; nếu app custom status mapping, assertions phải theo hợp đồng thật.

### Đừng kiểm tra bằng sleep cố định

Một test như:

~~~java
startWorker();
Thread.sleep(3000);
assertReady();
~~~

dễ flaky trên CI. Dùng polling theo điều kiện với deadline hữu hạn, ví dụ Awaitility cho HTTP state và listener state, và kiểm tra business/metadata đầu ra sau khi request hoàn tất.

### Broker thật quan trọng

In-memory Spring Integration `DirectChannel` không mô phỏng ACK, offset commit, redelivery, reply route hay consumer rebalance. Dùng Testcontainers/broker thật theo transport production để xác minh readiness gần với thực tế.

## 31. Fault injection matrix: worker thật và các điểm lỗi

| Vị trí lỗi | Cách mô phỏng | Điều cần kiểm tra |
| --- | --- | --- |
| Trước listener subscribe | Block broker DNS/connect | Liveness có thể UP, readiness không được READY |
| Sau listener subscribe | Cắt broker connection | Admission xuống và reconnect có kiểm soát |
| JobRepository unavailable | Tạm ngắt metadata DB | Worker không nhận StepExecution mới thiếu an toàn |
| Business DB pool cạn | Giữ connections trong test | Backpressure, không restart storm |
| API 503/429 | Fault stub/circuit breaker | Retry budget và readiness policy hợp lý |
| Handler kẹt DB lock | Giữ lock cố ý | Progress alert, không auto reassign thiếu ownership |
| Worker chết trước commit | Kill process | Request/partition recovery đúng |
| Worker chết sau commit trước ACK/reply | Kill đúng mốc | Business side effect không trùng |
| Reply route unavailable | Chặn reply broker | Correlation/reconciliation, không blind retry |
| DRAINING giữa chunk | Scale-down/hook | Không intake mới, work hiện tại có outcome rõ |
| Kafka rebalance | Stop một consumer | Assignment/offset/idempotency đúng |
| Rolling upgrade | Hai worker versions | Protocol/schema tương thích hoặc fail rõ |

**Phải kiểm tra cả ba mặt:** trạng thái health/admission, JobRepository/broker state và business data. Một test trả 503 đúng chưa chứng minh work không bị ACK nhầm.

### Test tối thiểu nhiều JVM

Dựng manager, hai worker processes, broker và JobRepository thật. Cho worker A đang commit chunk/partition rồi ngắt kết nối; worker B còn sống. Xác minh manager không nhận nhầm reply, StepExecution ownership/recovery đúng, không nhân đôi dữ liệu và worker readiness thể hiện đúng trạng thái intake.

## 32. Case study: 48 triệu giao dịch trong 40 phút

Một hệ thống xử lý **48.000.000 giao dịch** trong **40 phút**, dùng remote partitioning với 12 worker JVM, Kafka/RabbitMQ theo transport được chọn và PostgreSQL cho JobRepository/đích.

Throughput tối thiểu lý tưởng:

\[
R_{\mathrm{required}}=
\frac{48.000.000}{40 \times 60}
=20.000\ \mathrm{items/s}
\]

Đây là cận lý tưởng, chưa tính startup, queuing, retry, commit overhead hoặc thời gian tail partition.

### Thiết kế ban đầu có lỗi

- Worker readiness báo UP ngay sau Spring Boot ApplicationReadyEvent.
- Broker consumer chưa subscribe xong nhưng pod đã READY.
- Manager gửi nhiều partition requests vào broker.
- DB đích bị quá tải; một số handler retry liên tục.
- Liveness kiểm tra DB ping, vì vậy nhiều JVM bị restart cùng lúc.
- Reply mất, một số work bị gửi lại và writer chưa hoàn toàn idempotent.

Báo cáo chỉ nói nhiều message processed, nhưng JobExecution không hoàn thành đúng SLA và business reconciliation phát hiện duplicate.

### Phương án cải tiến

1. Readiness chỉ READY sau khi handler, JobRepository và consumer intake thật sự hoạt động.
2. Liveness không phụ thuộc trực tiếp DB/broker shared outage.
3. Có worker admission controller đồng bộ trạng thái HTTP với listener pause/stop.
4. Throttle manager outstanding partitions, giới hạn consumer concurrency.
5. Có retry budget, exponential backoff + jitter và DLQ/quarantine.
6. Writer upsert/ledger idempotent theo business key.
7. Đo worker progress, DB lock wait, pool pending và broker queue age.
8. Drain khi rolling deploy, không giao cùng StepExecution thiếu ownership policy.

### Ngân sách JDBC giả định

DB cho phép 140 connections. Nếu 12 worker JVM, mỗi pool max 8 connections thì trần worker là `12 × 8 = 96`. Dành 16 cho manager/metadata pool khác và 24 cho ứng dụng khác/headroom:

\[
96+16+24=136 \leq 140
\]

Đây chỉ là **trần connection cấu hình**, không chứng minh DB CPU/I/O/lock chịu được tải. Nếu scale lên 16 worker mà giữ max 8, trần riêng worker là 128, cộng phần còn lại 40 thành 168, vượt ngân sách.

### Benchmark minh họa

| Cấu hình | Throughput hữu ích | Thời gian lý tưởng N/R | Kết quả |
| --- | ---: | ---: | --- |
| 8 workers, DB contention | 17.000 item/s | 47,1 phút | Chậm SLA |
| 12 workers, DB contention | 21.000 item/s | 38,1 phút | Rất ít headroom |
| 12 workers, sửa contention và bounded retries | 24.000 item/s | 33,3 phút | Có headroom |
| 16 workers, DB sát trần | 25.000 item/s | 32,0 phút | Lợi ích biên nhỏ |
| 12 workers, retry không idempotent | 26.000 attempts/s báo cáo | Không đáng tin | FAIL correctness |

Tất cả con số là **giả định**. Thời gian `N/R` là ước lượng theo throughput, không phải thời gian JobExecution thực tế. Phải benchmark toàn job với retry/failover và đối soát business keys trước khi chọn.

### Bài học từ sự cố

Readiness đúng giúp điều phối **khi nào nhận thêm phần việc**, không tự sửa DB contention hay duplicate. Liveness đúng tránh restart storm, nhưng không tự ngăn StepExecution zombie. Cần kết hợp ownership/recovery, backpressure, idempotency và observability.

## 33. Runbook xử lý worker NOT_READY

Khi alert cho thấy nhiều worker NOT_READY, đừng mặc định restart toàn bộ.

**Bước 1 — Phân loại tín hiệu.** Kiểm tra readiness state/reason, liveness, startup status và active handlers. Nếu DRAINING trong một rollout có kế hoạch, đó có thể là trạng thái bình thường.

**Bước 2 — Kiểm tra broker.** RabbitMQ connection/channel/consumer count, ready/unacked; hoặc Kafka consumer assignments, lag, rebalance, paused state.

**Bước 3 — Kiểm tra JobRepository.** Metadata schema, connection wait, status các StepExecutions RUNNING/FAILED và số execution có dấu hiệu stale.

**Bước 4 — Kiểm tra downstream.** JDBC active/pending, SQL latency, lock waits, HTTP 429/503, CPU/heap/GC.

**Bước 5 — Kiểm tra admission thực.** Worker đã pause intake chưa? Có còn active work không? Queue có đang bị flood vì manager tiếp tục publish không?

**Bước 6 — Kiểm tra retry.** Attempts/backoff/DLQ và mức khuếch đại tải; không bật requeue nóng chỉ để “chữa” readiness.

**Bước 7 — Chọn recovery.** Reconnect/tune capacity/restart từng worker theo nguyên nhân; với StepExecution chưa rõ kết quả phải reconcile trước khi dispatch lại.

**Bước 8 — Đối soát.** Xác nhận JobExecution outcomes và dữ liệu cuối; log/health UP không tự chứng minh output đúng.

### Khi nào restart process?

Chỉ khi có lỗi cục bộ không tự phục hồi, hoặc runbook đã xác định restart an toàn cho những StepExecutions đang hoạt động. Với outage chung của DB/broker, restart đồng loạt thường không giúp ích.

## 34. Các ngộ nhận phổ biến

| Ngộ nhận | Sự thật |
| --- | --- |
| “/health trả 200 nghĩa worker xử lý được partition.” | Có thể chưa có consumer/JobRepository/reply path. |
| “Pod readiness false làm Kafka/RabbitMQ ngừng giao message.” | Không tự động; cần listener/admission control. |
| “Broker down thì liveness DOWN để kubelet restart.” | Restart storm có thể làm outage tệ hơn. |
| “ApplicationReadyEvent đồng nghĩa consumer subscribed.” | Hai lifecycle khác nhau, cần xác minh. |
| “Readiness false nghĩa mọi chunk bị rollback.” | Worker có thể đang drain và commit. |
| “Health UP chứng minh StepExecution đang tiến triển.” | Phải theo dõi progress riêng. |
| “Manager timeout nghĩa worker cũ đã dừng.” | Worker cũ có thể vẫn chạy/đã commit. |
| “JobRepository RUNNING luôn chứng minh process còn sống.” | Metadata có thể stale sau crash/network issue. |
| “Restart pod sẽ đảm bảo không ghi trùng.” | Duplicate vẫn có thể xảy ra sau commit-before-reply. |
| “Kafka pause đồng nghĩa stop và commit offset.” | Pause/stop/offset là các contract khác nhau. |
| “RabbitMQ ACK là DB commit exactly once.” | Không mặc nhiên atomic. |
| “Tăng worker giải quyết được pool exhaustion.” | Thêm connections/locks có thể làm DB chậm hơn. |
| “Probe cứ query toàn bộ dependency là chắc.” | Probe nặng có thể gây overload và false failure. |
| “Một lần JDBC pool full nên NOT_READY ngay.” | Cần capacity policy/hysteresis. |
| “Không có partition_finished log tức transaction rollback.” | JVM có thể chết trước log sau khi commit. |
| “Health là cơ chế idempotency/restart.” | Health là observability/admission; correctness cần transaction/metadata. |

## 35. Checklist production readiness cho worker

- [ ] Có định nghĩa rõ liveness/startup/readiness/progress/correctness.
- [ ] Liveness không fail theo mọi outage chung của DB/broker/API.
- [ ] Startup probe cho phép thời gian bootstrap thực tế và có deadline.
- [ ] Readiness không READY trước khi handler/listener/các dependency cần thiết sẵn sàng.
- [ ] `ApplicationReadyEvent` không bị dùng làm tín hiệu duy nhất.
- [ ] Custom HealthIndicator trả trạng thái nhanh và không tạo side effect.
- [ ] Broker consumer intake thực sự dừng/giảm khi BLOCKED/DRAINING.
- [ ] Kubernetes readiness false không bị nhầm với pause broker.
- [ ] Remote chunking kiểm tra đường reply/correlation.
- [ ] Remote partitioning kiểm tra JobRepository/StepLocator/ExecutionContext.
- [ ] Có cơ chế giới hạn outstanding work và executor/consumer concurrency.
- [ ] JDBC/HTTP pools có budget toàn cluster, không chỉ từng JVM.
- [ ] Readiness thresholds có hysteresis để tránh flap.
- [ ] Có metric progress cho active StepExecutions và queue age.
- [ ] Có phương án xử lý stuck worker, stale metadata và ownership an toàn.
- [ ] Không tự giao cùng StepExecution khi worker cũ có thể đang chạy.
- [ ] Retry có giới hạn, backoff/jitter và DLQ policy.
- [ ] Writer idempotent, checkpoint/restart có thể đối soát.
- [ ] Worker có graceful drain trước khi scale-down/rolling deploy.
- [ ] Termination grace period phù hợp chunk p99/rollback/reply.
- [ ] Vẫn an toàn khi worker bị kill đột ngột, bỏ qua lifecycle hooks.
- [ ] Health endpoints hạn chế chi tiết/được bảo vệ; không tiết lộ secrets.
- [ ] Logs ghi readiness transition reasons, IDs động không vào metric labels quá lớn.
- [ ] Có unit/integration test cho NOT_READY mà consumer không intake.
- [ ] Có fault injection trước/sau commit và khi reply mất.
- [ ] Có runbook xử lý outage mà không restart đồng loạt.
- [ ] Chỉ công nhận phương án đạt khi throughput hữu ích, SLA **và** dữ liệu đúng.

## 36. Câu hỏi tự kiểm tra

**1. Worker trả HTTP 200 nhưng Kafka listener chưa assigned partition. Có được coi READY không?**

Không nếu hợp đồng readiness đòi khả năng nhận record. Cần đo listener/assignment/admission thực tế; HTTP liveness UP chỉ nói process còn sống.

**2. DB tạm ngừng 20 giây. Vì sao thường không nên fail liveness?**

Vì đây là shared dependency outage, không phải lỗi process không phục hồi. Restart tất cả worker có thể tạo reconnect/retry storm.

**3. Pod NOT_READY có ngừng nhận RabbitMQ message không?**

Không tự động. Worker phải điều khiển listener/container intake theo lifecycle API hoặc admission boundary tương đương.

**4. Worker đang DRAINING có thể còn StepExecution RUNNING không?**

Có. Nó đang hoàn tất phần đã nhận và không nhận thêm work mới. Đây không tự động là lỗi.

**5. Tại sao JobRepository quan trọng với readiness remote partitioning?**

Worker cần truy xuất StepExecution/ExecutionContext và lưu checkpoint/status theo giao thức. Không truy cập metadata có thể khiến xử lý/recovery sai.

**6. Remote chunking còn cần kiểm tra đường nào ngoài inbound và writer?**

Đường gửi reply/correlation để manager nhận kết quả; commit DB rồi mất reply có thể dẫn tới timeout và redelivery.

**7. HikariCP pending tăng, có nên lập tức restart worker không?**

Không. Xem DB load/locks/query latency và pool budget; có thể cần giảm concurrency hoặc tối ưu DB.

**8. ApplicationReadyEvent có đảm bảo Kafka consumer đã subscribe không?**

Không. Nó là mốc Spring Boot lifecycle, cần kiểm tra trạng thái listener/consumer thực.

**9. Worker gửi heartbeat mỗi giây có chứng minh partition đang tiến triển không?**

Không. Timer có thể hoạt động trong khi handler kẹt DB lock. Cần progress theo work và metadata.

**10. Manager timeout một StepExecution, có nên giao ngay cho worker khác?**

Không khi worker cũ có thể còn chạy. Phải reconcile ownership/metadata và side effect trước.

**11. Liveness, readiness và idempotency giải quyết ba vấn đề gì?**

Liveness giúp quyết định restart process; readiness quyết định admission work mới; idempotency bảo vệ business effect khi work được chạy lại.

**12. HealthIndicator được gọi mỗi năm giây có nên query toàn bảng nguồn không?**

Không. Probe phải nhanh, nhẹ, tránh tạo tải phụ và deadlock/timeout khi hệ thống đang stress.

**13. Kafka pause có tự commit offset những record đã xử lý không?**

Không. Pause intake và offset commit là hai hợp đồng khác nhau, phải tuân listener ack/transaction policy.

**14. Khi worker chết sau DB commit nhưng trước ACK, điều gì có thể xảy ra?**

Broker có thể redeliver; cần idempotent writer, correlation và reconciliation để không tạo duplicate side effects.

**15. Khi tăng số replica từ 12 lên 16, tại sao phải tính lại JDBC pool?**

Tổng trần connection của cluster tăng theo số pool. Có thể vượt DB connection budget hoặc gây lock contention dù mỗi JVM vẫn dùng pool như cũ.

**16. Khi nào readiness DOWN lại là hành vi tốt?**

Khi worker chủ động DRAINING, chưa bootstrap xong hoặc tạm không thể nhận work mới an toàn. Liveness vẫn có thể UP và work đang chạy được drain.

---

**Ghi nhớ:** **Liveness quyết định có cần restart process; readiness quyết định có thể nhận work mới; progress cho biết StepExecution có tiếp tục; correctness cần JobRepository và đối soát dữ liệu.** Với worker Spring Batch chạy qua RabbitMQ/Kafka, readiness HTTP **không tự điều khiển consumer**. Thiết kế tốt phải nối admission signal với listener lifecycle, backpressure và graceful drain, đồng thời chịu được crash sau commit trước reply, xử lý retry/restart an toàn và tránh restart storm khi dependency chung gặp sự cố. Mục tiêu là **worker có khả năng nhận việc rõ ràng, phục hồi được và hoàn thành đúng dữ liệu trong SLA**.
