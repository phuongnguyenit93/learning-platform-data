# Đo thời gian cấp phát, số tác vụ chờ và tuổi tác vụ chưa hoàn tất

## Bối cảnh

Service broker theo Open Service Broker API (OSB API) tiếp nhận các yêu cầu provision, update, deprovision và binding từ platform. Một số thao tác hoàn tất ngay trong HTTP request; các thao tác dài thường được broker chấp nhận bằng response 202 Accepted, lưu thành operation rồi xử lý qua queue và worker. Khi số lượng service instance tăng, operator cần biết broker đang cấp phát nhanh hay chậm, backlog có đang tăng hay không và operation nào đã chờ quá lâu.

Ba chỉ số trong bài có ý nghĩa khác nhau:

- **Thời gian cấp phát (provision duration):** khoảng thời gian từ khi broker chấp nhận yêu cầu provision đến khi operation đạt trạng thái terminal như succeeded hoặc failed.
- **Số tác vụ chờ (pending/backlog):** số operation đã được chấp nhận nhưng chưa được worker hoàn tất, cần phân biệt queued, retry-wait, đang chạy và đang reconcile.
- **Tuổi tác vụ chưa hoàn tất (oldest incomplete operation age):** thời gian đã trôi qua kể từ lúc operation cũ nhất được chấp nhận mà vẫn chưa terminal.

Đo cả ba giúp phân biệt provider chậm, worker thiếu năng lực, queue bị nghẽn, retry storm và operation bị kẹt. Chỉ nhìn CPU hoặc HTTP request latency không đủ: một request có thể trả 202 trong vài mili giây nhưng database chỉ sẵn sàng sau nhiều phút.

## 1. Xác định vòng đời cần đo

Một operation provision bất đồng bộ có thể đi qua các mốc:

1. received_at: broker nhận HTTP request.
2. accepted_at: broker đã xác thực, validate, ghi instance/operation bền vững và cam kết xử lý.
3. enqueued_at: operation được đưa vào hàng đợi xử lý.
4. claimed_at: worker nhận quyền xử lý.
5. provider_started_at: broker bắt đầu gọi provider.
6. provider_finished_at: lần gọi provider kết thúc.
7. completed_at: broker xác minh kết quả và ghi operation terminal.

Không phải hệ thống nào cũng cần lưu mọi timestamp. Tuy nhiên, accepted_at và completed_at cần có để đo tuổi operation và thời gian end-to-end một cách nhất quán. Nếu cần chẩn đoán sâu, lưu thêm timestamp cho queue, provider call và từng attempt.

~~~mermaid
flowchart LR
    A[HTTP request received] --> B[Validate and persist]
    B --> C[Operation accepted]
    C --> D[Queued]
    D --> E[Worker claimed]
    E --> F[Provider call]
    F --> G[Reconcile target state]
    G --> H[Terminal: succeeded or failed]
    C -. accepted_at .-> H
~~~

### Thời điểm bắt đầu của provision duration

Với thao tác async, nên đo thời gian nghiệp vụ từ accepted_at đến completed_at. Thời gian trước khi accept thuộc request processing/validation và nên được đo bằng HTTP server timer riêng. Nếu dùng received_at làm mốc cho mọi trường hợp, một request bị từ chối trước khi tạo operation có thể làm sai số liệu provision.

Với thao tác đồng bộ, có thể đo từ lúc bắt đầu xử lý provision đến khi response kết thúc. Nếu muốn so sánh sync và async, hãy định nghĩa metric rõ ràng và gắn execution_mode với tập giá trị hữu hạn (SYNC, ASYNC).

### Terminal và non-terminal

Một số trạng thái tham khảo:

| Nhóm | Trạng thái ví dụ | Có tính vào backlog chưa hoàn tất? |
|---|---|---|
| Chờ xử lý | ACCEPTED, QUEUED, PENDING | Có |
| Đang chạy | RUNNING, IN_PROGRESS | Có |
| Chờ retry | RETRY_WAIT | Có |
| Đang xác minh kết quả | RECONCILING, UNKNOWN | Có |
| Hoàn tất thành công | SUCCEEDED | Không |
| Kết thúc lỗi | FAILED, CANCELLED | Không |

Tên state thực tế phụ thuộc state machine của broker. Cần định nghĩa một tập terminal duy nhất và dùng cùng quy tắc ở database query, metric, dashboard và alert.

## 2. Bộ metric tối thiểu

Một bộ metric khởi đầu có thể gồm:

| Metric logic | Loại | Ý nghĩa |
|---|---|---|
| service_broker_operation_duration_seconds | Histogram/Timer | Thời gian từ accept đến terminal |
| service_broker_operation_queue_wait_seconds | Histogram/Timer | Thời gian từ enqueue đến lần worker claim đầu tiên |
| service_broker_provider_call_duration_seconds | Histogram/Timer | Thời gian một lần gọi provider |
| service_broker_operations | Gauge | Số operation theo state |
| service_broker_operations_oldest_age_seconds | Gauge | Tuổi operation non-terminal cũ nhất |
| service_broker_operation_attempts_total | Counter | Tổng số attempt provider/worker theo loại thao tác và kết quả |
| service_broker_operation_transitions_total | Counter | Số lần chuyển trạng thái theo transition |
| service_broker_operation_failures_total | Counter | Số operation terminal failed theo error category |

Tên hiển thị khi export Prometheus có thể được chuẩn hóa từ tên Micrometer. Chọn một naming convention, dùng hậu tố đơn vị _seconds cho duration và _total cho counter, rồi giữ ổn định qua các lần phát hành.

### Không gộp mọi duration thành một số

Provision duration end-to-end trả lời người dùng phải chờ bao lâu. Queue wait cho biết operation mất bao lâu trước khi worker bắt đầu. Provider duration cho biết dependency mất bao lâu cho một lần gọi. Reconciliation duration cho biết broker mất bao lâu để xác minh target state. Các metric này giúp xác định đúng tầng gây chậm.

Ví dụ:

- Provision p95 tăng, queue wait ổn định, provider duration tăng: điều tra provider.
- Provision p95 tăng, queue wait tăng, provider duration ổn định: điều tra worker capacity hoặc queue.
- Provider call nhanh nhưng oldest operation age tăng: có thể worker bị kẹt ở phase khác, retry schedule sai hoặc reconciliation không hoàn tất.

## 3. Đo thời gian provision end-to-end

Với asynchronous operation, không giữ một Timer.Sample trong bộ nhớ từ HTTP request tới lúc worker kết thúc. Worker có thể chạy ở process khác hoặc sau khi broker restart. Hãy lưu accepted_at trong operation record, sau đó tính duration khi operation chuyển sang terminal.

Ví dụ record:

~~~sql
CREATE TABLE service_operation (
    operation_id       VARCHAR(128) PRIMARY KEY,
    platform_id        VARCHAR(128) NOT NULL,
    tenant_id          VARCHAR(128) NOT NULL,
    instance_id        VARCHAR(128) NOT NULL,
    operation_type     VARCHAR(32) NOT NULL,
    state              VARCHAR(24) NOT NULL,
    accepted_at        TIMESTAMP WITH TIME ZONE NOT NULL,
    enqueued_at        TIMESTAMP WITH TIME ZONE,
    first_claimed_at   TIMESTAMP WITH TIME ZONE,
    completed_at       TIMESTAMP WITH TIME ZONE,
    attempt_count      INTEGER NOT NULL DEFAULT 0,
    version            BIGINT NOT NULL DEFAULT 0
);
~~~

Đây là schema minh họa. Có thể tách attempt thành bảng riêng để lưu lịch sử nhiều provider call. platform_id, tenant_id và instance_id là dữ liệu nghiệp vụ; không đưa chúng thành label metric không giới hạn.

Khi operation chuyển sang terminal:

~~~java
Duration duration = Duration.between(
        operation.acceptedAt(),
        clock.instant());

Timer.builder("service.broker.operation.duration")
        .description("Time from operation acceptance to terminal state")
        .tag("operation_type", operation.type().name())
        .tag("outcome", operation.state().name())
        .register(meterRegistry)
        .record(duration);
~~~

Đoạn mã minh họa cách ghi Timer bằng Micrometer. Trong ứng dụng thực tế, nên đăng ký Timer một lần qua component/builder phù hợp thay vì tạo meter mới theo mỗi request; Micrometer tái sử dụng meter cùng tên và tập tags, nhưng tránh tạo tags động.

### Ghi nhận đúng một lần

Operation có thể được xử lý lại do queue redelivery, worker retry hoặc restart. Chỉ ghi duration khi state transition thực sự chuyển từ non-terminal sang terminal. Dùng optimistic locking, compare-and-set hoặc transaction để bảo đảm chỉ một worker thắng transition.

Nếu worker nhận lại event sau khi operation đã SUCCEEDED, không ghi thêm một mẫu duration cho cùng operation. Metrics là dữ liệu quan sát, không phải nguồn sự thật nghiệp vụ; database operation record vẫn là nguồn chuẩn để đối soát.

### Phân biệt success và failure

Ghi outcome với tập giá trị hữu hạn, ví dụ SUCCEEDED, FAILED, CANCELLED. Không đưa exception message hoặc operation ID vào tag. Khi tính p95 thời gian provision thành công, lọc outcome=SUCCEEDED; theo dõi duration tới failure riêng vì failure sớm không có nghĩa trải nghiệm provision thành công nhanh.

## 4. Đo queue wait và provider duration

### Queue wait

Queue wait ban đầu có thể được tính:

\[
queue\_wait = first\_claimed\_at - enqueued\_at
\]

Chỉ đo từ lần enqueue đầu đến lần worker claim đầu tiên. Nếu operation bị retry, thời gian chờ retry nên được đo riêng (retry_wait_seconds) hoặc lưu theo attempt. Nếu gộp toàn bộ khoảng chờ vào queue wait, dashboard sẽ khó phân biệt backlog mới với retry delay.

### Provider call duration

Mỗi lần gọi provider nên có Timer riêng với các tags giới hạn như:

- provider: tên adapter hoặc nhóm provider.
- operation_type: PROVISION, UPDATE, DEPROVISION, BIND, UNBIND.
- outcome: SUCCESS, RETRYABLE_ERROR, PERMANENT_ERROR, TIMEOUT.

Không gắn instance_id, tenant_id, request_identity, URL đầy đủ hoặc resource name vào tag. Các giá trị này có cardinality lớn hoặc có thể chứa dữ liệu nhạy cảm; ghi chúng trong structured log/trace đã kiểm soát thay vì metric label.

Ví dụ:

~~~java
Timer.Sample sample = Timer.start(meterRegistry);
String outcome = "SUCCESS";
try {
    providerAdapter.provision(command);
} catch (ProviderTimeoutException ex) {
    outcome = "TIMEOUT";
    throw ex;
} catch (ProviderTransientException ex) {
    outcome = "RETRYABLE_ERROR";
    throw ex;
} catch (ProviderPermanentException ex) {
    outcome = "PERMANENT_ERROR";
    throw ex;
} catch (RuntimeException ex) {
    outcome = "ERROR";
    throw ex;
} finally {
    sample.stop(Timer.builder("service.broker.provider.call.duration")
            .tag("provider", providerName)
            .tag("operation_type", "PROVISION")
            .tag("outcome", outcome)
            .register(meterRegistry));
}
~~~

Mỗi loại exception cần được ánh xạ sang một outcome hữu hạn. Nhánh RuntimeException cuối cùng bảo đảm lỗi chưa được phân loại không bị ghi nhầm thành SUCCESS. Mã trên là khung minh họa; điều chỉnh các kiểu exception theo taxonomy của provider adapter thực tế.

## 5. Đo số tác vụ chờ

Một queue có thể chứa nhiều loại message: operation mới, retry, reconcile, event cleanup. Độ dài queue hạ tầng và số operation chưa hoàn tất là hai số liệu khác nhau.

- **Queue depth/consumer lag:** số message đang chờ trong RabbitMQ, Kafka hoặc queue backend.
- **Operation backlog:** số operation trong database vẫn ở trạng thái non-terminal.

Message có thể đã được lấy khỏi queue nhưng worker vẫn đang xử lý; ngược lại một operation có thể ở RETRY_WAIT trong database nhưng chưa có message sẵn sàng trong queue. Dashboard nên hiển thị cả hai.

### Đếm theo state

Ví dụ query:

~~~sql
SELECT state, COUNT(*) AS operation_count
FROM service_operation
WHERE completed_at IS NULL
GROUP BY state;
~~~

Nếu state terminal không luôn đồng nghĩa completed_at có giá trị, hãy dùng điều kiện theo state machine đã chuẩn hóa. Tốt nhất là có invariant: mọi terminal transition đều ghi completed_at trong cùng transaction.

Metric gauge có thể được export theo state:

~~~text
service_broker_operations{state="QUEUED"} 120
service_broker_operations{state="RUNNING"} 18
service_broker_operations{state="RETRY_WAIT"} 7
service_broker_operations{state="RECONCILING"} 3
~~~

Đây là ví dụ số liệu. Tập state phải cố định; không tạo label từ state tự do hoặc exception message.

### Lấy snapshot backlog

Không nên chạy query COUNT/GROUP BY tốn kém mỗi lần Prometheus scrape. Có thể chạy một scheduled sampler theo chu kỳ, truy vấn aggregate một lần và cập nhật snapshot trong bộ nhớ. Gauge đọc snapshot gần nhất. Nếu snapshot quá cũ hoặc query thất bại, export thêm metric tuổi snapshot hoặc đánh dấu telemetry stale để operator biết dashboard không còn mới.

Với broker có nhiều replica, snapshot cục bộ của từng replica có thể bị cộng trùng hoặc không đầy đủ. Nên chọn một cách:

- Mỗi replica query aggregate toàn cục và export cùng giá trị; khi scrape nhiều target, dashboard dùng max hoặc chọn một collector chuyên trách, không sum các bản sao giống nhau.
- Dùng một metrics collector/leader duy nhất để export aggregate toàn cục.
- Dùng metrics của database/queue exporter và query ở Prometheus.

Chọn cách phù hợp, ghi rõ semantics và tránh cộng số gauge global từ mọi replica.

## 6. Đo tuổi operation chưa hoàn tất

Tuổi operation là thời gian kể từ lúc broker chấp nhận công việc đến thời điểm hiện tại:

\[
age = now - accepted\_at
\]

Để phát hiện backlog bị kẹt, chỉ số quan trọng là tuổi của operation non-terminal cũ nhất:

\[
oldest\_age = now - \min(accepted\_at \mid state \notin terminal)
\]

Nếu không còn operation non-terminal, gauge bằng 0 hoặc không có sample theo convention đã chọn. Nên giữ một convention thống nhất để alert không diễn giải nhầm missing series.

Ví dụ query:

~~~sql
SELECT EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - MIN(accepted_at)))
       AS oldest_age_seconds
FROM service_operation
WHERE state IN (
    'ACCEPTED',
    'QUEUED',
    'RUNNING',
    'RETRY_WAIT',
    'RECONCILING'
);
~~~

Tên state trong ví dụ cần thay bằng state thực tế của broker. Nếu database lưu completed_at, có thể lọc completed_at IS NULL với điều kiện invariant terminal đã được bảo đảm.

### Vì sao oldest age khác backlog count?

100 operation vừa được nhận trong một giây có thể là tải bình thường nếu worker đang xử lý nhanh. Chỉ số count cao chưa chắc có sự cố. Ngược lại, chỉ một operation bị kẹt nhiều giờ có thể quan trọng dù queue depth gần bằng 0.

Kết hợp:

- Backlog count cho biết khối lượng.
- Oldest age cho biết thời gian chờ tệ nhất.
- Provision duration histogram cho biết phân phối trải nghiệm đã hoàn tất.
- Queue wait và provider duration cho biết điểm nghẽn.

Có thể bổ sung tuổi p95 của operation đang mở bằng query percentile trên now - accepted_at, nhưng cần đánh giá chi phí query. Oldest age dễ tính và hữu ích cho alert stuck operation; histogram terminal duration phù hợp để đo phân phối đã hoàn tất.

## 7. Triển khai metric bằng Micrometer trong Spring Boot

Spring Boot Actuator và Micrometer cung cấp abstraction cho Timer, Counter, Gauge và registry. Ví dụ cấu hình Prometheus:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-prometheus</artifactId>
</dependency>
~~~

Dependency version nên được quản lý bởi Spring Boot dependency management của dự án. Không tự gán version khác với BOM nếu chưa kiểm tra compatibility.

Ví dụ cấu hình endpoint:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,prometheus
  endpoint:
    prometheus:
      access: read-only
  metrics:
    tags:
      application: spring-cloud-service-broker
~~~

Các thuộc tính Actuator có thể thay đổi theo phiên bản Spring Boot. Chỉ expose endpoint cần thiết; bảo vệ endpoint metrics bằng network policy, authentication hoặc scrape network riêng. Không công khai toàn bộ Actuator ra Internet.

### Component ghi operation duration

~~~java
@Component
public class OperationMetrics {

    private final MeterRegistry registry;

    public OperationMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void recordTerminal(
            String operationType,
            String outcome,
            Duration duration) {

        Timer.builder("service.broker.operation.duration")
                .description("Accepted operation duration")
                .tag("operation_type", operationType)
                .tag("outcome", outcome)
                .register(registry)
                .record(duration);
    }

    public void incrementAttempt(
            String operationType,
            String outcome) {

        Counter.builder("service.broker.operation.attempts")
                .tag("operation_type", operationType)
                .tag("outcome", outcome)
                .register(registry)
                .increment();
    }
}
~~~

Trước khi gọi recordTerminal, application service phải xác nhận state transition thành công. Nếu update database thất bại hoặc một worker khác đã terminal operation, không ghi mẫu duration lần nữa.

### Gauge cho backlog snapshot

~~~java
public final class BacklogSnapshot {
    private final AtomicLong queued = new AtomicLong();
    private final AtomicLong running = new AtomicLong();
    private final AtomicLong retryWait = new AtomicLong();
    private final AtomicLong reconciling = new AtomicLong();
    private final AtomicLong oldestAgeSeconds = new AtomicLong();

    public long queued() { return queued.get(); }
    public long running() { return running.get(); }
    public long retryWait() { return retryWait.get(); }
    public long reconciling() { return reconciling.get(); }
    public long oldestAgeSeconds() { return oldestAgeSeconds.get(); }

    public void update(
            long queuedCount,
            long runningCount,
            long retryWaitCount,
            long reconcilingCount,
            long oldestAge) {
        queued.set(queuedCount);
        running.set(runningCount);
        retryWait.set(retryWaitCount);
        reconciling.set(reconcilingCount);
        oldestAgeSeconds.set(oldestAge);
    }
}
~~~

Đăng ký Gauge từ snapshot singleton:

~~~java
Gauge.builder("service.broker.operations", snapshot, s -> s.queued())
        .tag("state", "QUEUED")
        .register(registry);
Gauge.builder("service.broker.operations", snapshot, s -> s.running())
        .tag("state", "RUNNING")
        .register(registry);
Gauge.builder("service.broker.operations", snapshot, s -> s.retryWait())
        .tag("state", "RETRY_WAIT")
        .register(registry);
Gauge.builder("service.broker.operations", snapshot, s -> s.reconciling())
        .tag("state", "RECONCILING")
        .register(registry);
Gauge.builder("service.broker.operations.oldest.age.seconds", snapshot,
        s -> s.oldestAgeSeconds())
        .register(registry);
~~~

Đây là ví dụ cấu trúc. Cần đăng ký các Gauge đúng một lần trong lifecycle của ứng dụng. Snapshot phải được cập nhật từ aggregate query hoặc nguồn metrics có semantics toàn cục; không tạo Gauge mới mỗi lần scheduler chạy.

### Scheduled sampler

~~~java
@Component
public class BacklogSampler {

    private final OperationRepository repository;
    private final BacklogSnapshot snapshot;
    private final Clock clock;

    @Scheduled(fixedDelay = 15000)
    public void refresh() {
        var counts = repository.countOpenOperationsByState();
        var oldestAcceptedAt = repository.findOldestOpenAcceptedAt();
        long oldestAge = oldestAcceptedAt
                .map(at -> Math.max(0,
                        Duration.between(at, clock.instant()).toSeconds()))
                .orElse(0L);

        snapshot.update(
                counts.queued(),
                counts.running(),
                counts.retryWait(),
                counts.reconciling(),
                oldestAge);
    }
}
~~~

Đây là pseudocode Spring. Cần constructor injection, bật scheduling có kiểm soát và xử lý exception để một lần query lỗi không làm scheduler dừng vĩnh viễn. Với nhiều replica, chọn semantics aggregate global như phần trên; không để mọi replica export cùng gauge rồi cộng tất cả.

## 8. Histogram buckets và percentile

Timer/histogram cho phép theo dõi p50, p90, p95, p99 thay vì chỉ trung bình. Trung bình có thể che khuất một nhóm operation rất chậm.

Ví dụ ngưỡng bucket cho provision:

| Bucket | Ý nghĩa |
|---:|---|
| 5 giây | Provision rất nhanh |
| 15 giây | Hoàn tất trong thời gian ngắn |
| 30 giây | Một mức chờ thường cần theo dõi |
| 60 giây | Có thể vượt kỳ vọng của một số plan |
| 180 giây | Thao tác dài |
| 600 giây | Cần phân tích theo loại service |
| 1800 giây | Provision rất dài, có thể chạm deadline |

Đây chỉ là bucket ví dụ. Database tạo mới, cluster provisioning hoặc dịch vụ cần backup/restore có đặc tính thời gian khác nhau. Chọn bucket dựa trên SLO, phân phối latency thực tế và thời hạn platform chấp nhận.

Trong Micrometer có thể cấu hình percentile histogram:

~~~yaml
management:
  metrics:
    distribution:
      percentiles-histogram:
        service.broker.operation.duration: true
      slo:
        service.broker.operation.duration: 5s,15s,30s,60s,180s,600s
~~~

Kiểm tra property binding theo Spring Boot/Micrometer version đang dùng. Với Prometheus, histogram buckets được tổng hợp từ các series _bucket; percentile thường được tính ở PromQL bằng histogram_quantile.

Không bật histogram cho mọi metric có tags động. Mỗi tổ hợp tag nhân số series với số bucket, làm tăng memory, scrape payload và chi phí lưu trữ.

## 9. PromQL và dashboard

Các ví dụ sau giả định Prometheus scrape metric đã được export với tên tương ứng. Tên thực tế có thể khác do naming convention của Micrometer.

### p95 provision thành công

~~~promql
histogram_quantile(
  0.95,
  sum by (le, operation_type) (
    rate(service_broker_operation_duration_seconds_bucket{
      operation_type="PROVISION",
      outcome="SUCCEEDED"
    }[5m])
  )
)
~~~

Biểu đồ cho biết 95% operation provision thành công trong cửa sổ đo có duration không vượt quá giá trị ước lượng. Cần xem theo thời gian và so với SLO, không đánh giá từ một điểm đơn lẻ.

### Số operation đang mở

~~~promql
sum by (state) (service_broker_operations)
~~~

Hiển thị queued, running, retry-wait và reconciling. Nếu metric đã export là gauge global lặp ở nhiều replica, không sum trực tiếp qua instance; dùng collector duy nhất hoặc phép tổng hợp phù hợp semantics.

### Tuổi operation cũ nhất

~~~promql
max(service_broker_operations_oldest_age_seconds)
~~~

Nếu mỗi replica export snapshot khác nhau, max có thể hữu ích để nhìn giá trị lớn nhất nhưng vẫn cần xác định replica nào có quyền tính aggregate. Với một global gauge được export lặp, dùng max tránh nhân số; cách tốt hơn là có một nguồn metric global rõ ràng.

### Queue wait p95

~~~promql
histogram_quantile(
  0.95,
  sum by (le, operation_type) (
    rate(service_broker_operation_queue_wait_seconds_bucket[5m])
  )
)
~~~

### Tỷ lệ lỗi terminal

~~~promql
sum(rate(service_broker_operation_transitions_total{
  to_state="FAILED"
}[5m]))
/
clamp_min(
  sum(rate(service_broker_operation_transitions_total{
    to_state=~"SUCCEEDED|FAILED|CANCELLED"
  }[5m])),
  1e-9
)
~~~

Ví dụ này yêu cầu metric transition có label to_state với tập giá trị hữu hạn. Nếu implementation dùng counter khác, thay query theo schema metric thực tế.

### Bố cục dashboard

Một dashboard vận hành nên có:

1. Provision duration p50/p95/p99 theo operation type.
2. Số operation theo state.
3. Oldest incomplete operation age.
4. Queue depth/consumer lag của queue backend.
5. Queue wait p95 và provider call p95.
6. Retry attempts, retry exhaustion và provider error category.
7. Operation completed/failed rate.
8. Worker active count, throughput và error rate.

Đặt oldest age và backlog ở phần đầu dashboard vì đây là tín hiệu dễ cho biết công việc đã bị ùn tắc. Dùng drill-down từ metric sang log/trace qua operation ID trong log context, không gắn operation ID vào metric label.

## 10. Alert và SLO

Alert nên dựa trên ngưỡng nghiệp vụ và duy trì trong một khoảng thời gian để tránh báo động do spike ngắn. Không dùng cùng một ngưỡng provision cho mọi plan.

Ví dụ policy minh họa:

| Tín hiệu | Điều kiện ví dụ | Hành động |
|---|---|---|
| Oldest operation age | Lớn hơn 10 phút liên tục 5 phút | Kiểm tra worker, queue và provider |
| Queue backlog | Tăng liên tục và throughput không theo kịp | Kiểm tra capacity/consumer lag |
| Provision p95 | Vượt SLO của plan trong 15 phút | Phân tích queue/provider phase |
| Retry exhaustion | Tăng đột biến | Kiểm tra provider errors và retry policy |
| RECONCILING age | Một operation vượt deadline | Kiểm tra unknown outcome/resource orphan |
| Snapshot stale | Không cập nhật trong nhiều chu kỳ | Kiểm tra sampler/database |

Các ngưỡng trên không phải mặc định cho production. Cần đặt SLO theo loại service, plan, provider và cam kết với Platform.

### Ví dụ alert rule

~~~yaml
groups:
  - name: service-broker-operations
    rules:
      - alert: ServiceBrokerOldestOperationTooOld
        expr: max(service_broker_operations_oldest_age_seconds) > 600
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: Oldest service broker operation is too old
          description: Check queue backlog, worker health and provider status.
~~~

Alert cần có runbook: kiểm tra dashboard, operation state distribution, queue lag, worker availability, provider status và database latency. Không tự động xóa operation cũ để làm gauge giảm; trước hết phải reconcile hoặc xử lý theo quy trình phục hồi.

### SLO cho thời gian provision

Ví dụ SLO có thể là 95% provision của plan standard hoàn tất trong 5 phút trong cửa sổ 30 ngày. Cần xác định rõ:

- Bắt đầu tính từ accepted_at.
- Kết thúc ở terminal succeeded.
- Failed operation được theo dõi riêng trong availability/error budget.
- Retry do provider và queue đều nằm trong thời gian end-to-end.
- Hủy bởi caller có semantics riêng.
- Chỉ tính các operation hợp lệ đã được accept.

Không loại operation chậm hoặc failed ra khỏi báo cáo chỉ để làm đẹp percentile.

## 11. Đo backlog trong hệ thống nhiều replica

Broker thường có nhiều API replica và worker replica. Metric phải có semantics rõ ràng giữa các instance.

### Per-instance và global metric

| Metric | Phạm vi phù hợp |
|---|---|
| HTTP request rate/latency | Per instance, sau đó tổng hợp |
| Worker active count | Per instance |
| Provider call duration | Per instance hoặc global histogram tổng hợp |
| Operation state count | Global theo database, hoặc per-shard có nhãn shard hữu hạn |
| Oldest incomplete age | Global hoặc theo queue/operation type |
| Queue consumer lag | Theo queue/topic/consumer group |

Không cộng global database count được lặp ở mọi replica. Nếu mỗi replica chạy sampler query cùng một bảng, Prometheus sẽ có nhiều sample cùng giá trị; dùng max/min phù hợp hoặc triển khai collector chuyên trách.

### Leader election và collector

Có thể dùng leader election để chỉ một replica cập nhật global snapshot, nhưng cần xử lý khi leader mất và tránh stale gauge. Cách khác là dùng exporter chuyên đọc database/queue. Nếu dùng singleton collector, dashboard cần có alert khi target đó down.

### Sharding

Nếu operation được chia theo shard/tenant region, metric có thể gắn shard hoặc region khi tập giá trị được giới hạn và được quản trị. Dashboard tính tổng backlog và oldest age bằng aggregation phù hợp. Không dùng tenant ID tùy ý làm label.

## 12. Độ tin cậy của timestamp và metric

Timestamp cần được lưu ở UTC và dùng cùng quy ước. Instant phù hợp trong Java cho mốc thời gian tuyệt đối. Để đo một call trong cùng process, có thể dùng monotonic clock (System.nanoTime) qua Micrometer Timer; không dùng wall clock nếu có thể bị điều chỉnh giữa hai lần đọc.

Đối với operation tồn tại qua restart hoặc nhiều replica, cần timestamp bền vững như accepted_at. Khi tính oldest age, dùng clock đồng bộ và cân nhắc lấy CURRENT_TIMESTAMP từ database để tránh clock skew giữa broker replicas.

Các nguyên tắc:

- Không để completed_at trước accepted_at; validate timestamp và ghi nhận clock anomaly.
- Dùng transaction để ghi terminal state và completed_at cùng nhau.
- Nếu update terminal bị retry, không thay completed_at hoặc ghi duration thêm lần nữa.
- Nếu sampler query lỗi, giữ snapshot cuối cùng nhưng đánh dấu stale.
- Metrics process-local có thể reset khi restart; database vẫn là nguồn sự thật để phục hồi gauge.
- Counter Prometheus reset khi process restart là bình thường; không dùng counter process-local làm số liệu audit chính xác lâu dài.

### Metrics không phải nguồn dữ liệu nghiệp vụ

Metric có thể bị mất trong lúc process crash hoặc scrape gián đoạn. Nếu cần báo cáo chính xác số provision thành công theo ngày/tháng, truy vấn operation ledger hoặc analytics store. Không dùng Counter trong bộ nhớ để quyết toán hoặc audit.

## 13. Log và trace bổ sung cho metrics

Metrics cho biết xu hướng; log và trace giúp điều tra một operation cụ thể.

Structured log nên có:

- operation_id
- instance_id
- platform_id/tenant reference theo policy
- operation_type
- state_from, state_to
- attempt
- queue_name hoặc worker pool
- provider
- duration_ms
- error_category

Các ID này nên nằm trong log có kiểm soát, không phải metric labels. Không ghi password, token, private key hoặc binding credentials.

Trace có thể tách span:

~~~text
osb.provision
  ├── operation.persist
  ├── queue.publish
  ├── worker.claim
  ├── provider.create
  └── provider.reconcile
~~~

Với async worker, truyền trace context qua message hoặc tạo trace mới có liên kết tới trace nhận request ban đầu. Không phụ thuộc ThreadLocal của HTTP request. Giữ sampling policy để tránh trace volume quá lớn khi polling hoặc retry dồn dập.

## 14. Kiểm thử metric và alert

Không chỉ kiểm tra metric có xuất hiện. Test phải xác minh giá trị và thời điểm cập nhật theo state transition.

| Tình huống | Kết quả cần xác minh |
|---|---|
| Accept provision | Non-terminal count tăng; oldest age bắt đầu từ accepted_at |
| Worker claim | Queued giảm, running tăng; queue wait được ghi khi claim đầu |
| Provider retry | Attempt counter tăng; operation vẫn non-terminal |
| Retry wait | Operation vẫn được tính trong backlog và oldest age tiếp tục tăng |
| Provision succeeded | Non-terminal count giảm; terminal duration được ghi đúng một lần |
| Provision failed | Failed count tăng; duration failure được ghi riêng |
| Duplicate queue event | Không ghi duration terminal lần hai |
| Broker restart | Gauge được dựng lại từ operation repository |
| Sampler lỗi | Snapshot stale được phát hiện |
| Không còn operation mở | Oldest age trở về 0 hoặc absent theo convention |
| Nhiều API replica | Global backlog không bị nhân lên do scrape nhiều target |
| Tenant ID mới | Không tạo metric series mới theo tenant |

### Unit test với SimpleMeterRegistry

~~~java
@Test
void recordsProvisionDurationOnTerminalTransition() {
    var registry = new SimpleMeterRegistry();
    var metrics = new OperationMetrics(registry);

    metrics.recordTerminal(
            "PROVISION",
            "SUCCEEDED",
            Duration.ofSeconds(42));

    Timer timer = registry.find("service.broker.operation.duration")
            .tag("operation_type", "PROVISION")
            .tag("outcome", "SUCCEEDED")
            .timer();

    assertThat(timer).isNotNull();
    assertThat(timer.count()).isEqualTo(1);
    assertThat(timer.totalTime(TimeUnit.SECONDS)).isEqualTo(42);
}
~~~

Đây là ví dụ unit test cho recorder. Test state transition cần bổ sung để chứng minh recorder chỉ được gọi khi database compare-and-set thành công.

### Test oldest age với clock giả

Dùng Clock.fixed hoặc clock có thể điều khiển để tạo operation accepted tại một thời điểm xác định. Sau khi tăng clock 120 giây, sampler phải báo oldest age xấp xỉ 120 giây. Test này tránh phụ thuộc Thread.sleep và giảm flaky test.

### Integration test với database

Dùng database test tương thích production để:

- Tạo operation ở từng state.
- Kiểm tra aggregate count theo state.
- Kiểm tra oldest accepted_at chỉ tính non-terminal.
- Chuyển một operation sang terminal và xác nhận count/age thay đổi.
- Kiểm tra transaction rollback không làm snapshot sai.
- Chạy nhiều worker transition đồng thời để xác nhận chỉ một terminal event được ghi nhận.

## 15. Lỗi quan sát thường gặp

### Chỉ đo HTTP latency

Request trả 202 nhanh không có nghĩa service đã provision xong. Cần đo end-to-end operation duration và oldest age.

### Chỉ đếm queue message

Message đã được worker claim có thể không còn trong queue nhưng operation vẫn chạy hoặc bị kẹt. Theo dõi operation backlog từ durable state.

### Không tính RETRY_WAIT là backlog

Operation chờ retry vẫn chưa hoàn tất. Nếu loại nó khỏi gauge, dashboard có thể báo queue rỗng trong khi hàng trăm operation đang chờ retry.

### Ghi duration mỗi lần polling

GET last_operation có thể được gọi nhiều lần. Không ghi provision duration ở endpoint polling; chỉ ghi khi operation chuyển terminal một lần.

### Gắn instance/tenant ID vào metric label

Cardinality tăng nhanh và có nguy cơ lộ metadata. Đưa ID vào log/trace có kiểm soát, dùng metric label hữu hạn.

### Cộng global gauge từ mọi replica

Một giá trị count toàn database được export giống nhau bởi năm replica có thể bị Prometheus cộng thành năm lần. Xác định global/per-instance semantics và aggregation.

### Chỉ lưu metric trong bộ nhớ

Restart làm mất gauge/counter process-local. Gauge backlog và oldest age phải có thể dựng lại từ operation store; counter quan sát không thay thế ledger.

### Đo provider call nhưng quên reconciliation

Provider call có thể nhanh nhưng tài nguyên vẫn chưa READY. Theo dõi thời gian từ provider response đến khi broker xác minh target state.

## 16. Checklist triển khai

- [ ] Định nghĩa accepted_at, completed_at và tập terminal state.
- [ ] Đo provision duration từ accept đến terminal.
- [ ] Đo riêng HTTP request latency, queue wait và provider call duration.
- [ ] Ghi duration terminal đúng một lần sau state transition thành công.
- [ ] Đếm operation theo state, gồm retry-wait và reconciling.
- [ ] Đo oldest incomplete operation age từ accepted_at.
- [ ] Phân biệt operation backlog với queue depth/consumer lag.
- [ ] Dựng lại global gauge từ durable operation store sau restart.
- [ ] Xác định global/per-instance metric và tránh cộng trùng giữa replica.
- [ ] Dùng Timer/histogram và bucket theo SLO của plan.
- [ ] Dùng labels hữu hạn; không gắn tenant, instance, binding hoặc operation ID.
- [ ] Bảo vệ endpoint Prometheus/Actuator.
- [ ] Có dashboard p95/p99, backlog, oldest age, retry và provider latency.
- [ ] Có alert kèm runbook và ngưỡng theo loại service.
- [ ] Có test SimpleMeterRegistry, fake Clock và database aggregate.
- [ ] Kiểm tra stale snapshot, duplicate event và restart recovery.
- [ ] Dùng log/trace để drill-down mà không ghi credentials.

## Kết luận

Để vận hành service broker hiệu quả, cần đo thời gian provision end-to-end từ lúc operation được chấp nhận đến khi terminal, số operation còn mở theo state và tuổi operation non-terminal cũ nhất. Queue depth, queue wait và provider duration bổ sung góc nhìn để tìm đúng điểm nghẽn. Trong Spring Boot, Micrometer Timer/Counter/Gauge có thể xuất dữ liệu qua Actuator/Prometheus; các gauge backlog phải được dựng từ trạng thái bền vững và có semantics rõ ràng giữa nhiều replica. Ghi duration đúng một lần, tính cả retry-wait/reconciliation, tránh metric cardinality cao và kiểm thử bằng clock/database giả lập sẽ giúp operator phát hiện backlog và operation bị kẹt trước khi người dùng marketplace chịu ảnh hưởng kéo dài.

## Tài liệu tham khảo

- [Spring Boot Reference — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Micrometer Documentation — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)
- [Prometheus Documentation — Histograms and Summaries](https://prometheus.io/docs/practices/histograms/)
- [Prometheus Documentation — Querying basics](https://prometheus.io/docs/prometheus/latest/querying/basics/)
