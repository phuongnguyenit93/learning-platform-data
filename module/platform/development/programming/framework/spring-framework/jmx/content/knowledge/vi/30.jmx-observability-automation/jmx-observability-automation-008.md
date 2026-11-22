# Đối chiếu dữ liệu JMX với logs và traces trong Spring Framework

## Mục tiêu học tập

JMX cung cấp góc nhìn quản trị **trạng thái runtime** của JVM và các bean được Spring Framework export. Logs cho biết **sự kiện đã được ghi nhận** và chi tiết thực thi; distributed traces cho biết **đường đi của một yêu cầu hoặc công việc** qua các service, thread và dependency được instrument. Mỗi nguồn giải đáp một phần vấn đề, nhưng riêng một nguồn thường chưa đủ kết luận nguyên nhân sự cố.

Ví dụ JMX báo \`QueueDepth=2500\` và \`WorkerState=RUNNING\`. Con số này không giải thích vì sao hàng đợi tăng. Logs có thể chứa nhiều lần retry, còn traces cho thấy kết nối database chậm. Để kết luận đáng tin cậy, cần đối chiếu **đúng JVM/instance, thời điểm, phạm vi đo lường, trace context và phiên bản ứng dụng**.

Sau bài này, bạn có thể:
- Phân biệt tính chất dữ liệu của JMX attributes, notifications, logs và traces.
- Lập bộ định danh chung để ghép dữ liệu theo service, instance và thời gian.
- Thiết kế JMX management attributes có timestamp, freshness và semantic rõ ràng.
- Liên kết operation JMX với audit logs, request ID và traces khi phù hợp.
- Phân tích một incident từ dấu hiệu JMX đến log events, trace spans và dependency metrics.
- Tránh lỗi đối chiếu do clock skew, sampling, asynchronous work, stale snapshot và reset counters.
- Xây dựng dashboard, runbook, alert và integration tests hỗ trợ điều tra đa nguồn.
- Đảm bảo observability không làm lộ secrets hoặc gây tác động xấu lên runtime.

## 1. Ba góc nhìn bổ sung nhau

| Nguồn | Dữ liệu điển hình | Câu hỏi mạnh nhất | Giới hạn |
|---|---|---|---|
| JMX attributes | QueueDepth, ActiveThreads, ConnectionCount, ErrorCount | Hệ thống đang ở trạng thái nào? | Có thể là snapshot cũ; ít chi tiết nguyên nhân |
| JMX notifications | Worker paused, task failed, config reloaded | Có sự kiện quản trị nào vừa phát? | Không phải hàng đợi bền vững hoặc đảm bảo delivery |
| Logs | Exception, retry, business event, config change | Điều gì đã được code ghi nhận và tại đâu? | Có thể thiếu, nhiễu, mất thứ tự giữa node |
| Traces | Span, duration, parent-child relation, status | Yêu cầu đi qua đâu và tốn thời gian ở bước nào? | Sampling hoặc instrumentation có thể bỏ sót |
| Metrics/time-series | Rate, latency, errors, saturation | Xu hướng và mức độ lan rộng ra sao? | Aggregation làm mất chi tiết từng request |

Cần hiểu rằng JMX cũng có thể được monitoring agent chuyển thành metrics time-series. JMX attribute là một giá trị được đọc tại thời điểm polling; dữ liệu time-series là tập mẫu qua thời gian với interval/aggregation riêng.

Ví dụ:

\`\`\`text
10:00:00  JMX: QueueDepth=150, ActiveWorkers=8
10:00:03  LOG: retry batch=B45, reason=DB_TIMEOUT
10:00:04  TRACE: batch=B45, span=db.query duration=2.8s
10:00:10  JMX: QueueDepth=340, ActiveWorkers=8
\`\`\`

Điều này cho thấy queue tăng cùng lúc xuất hiện DB timeout và query chậm, nhưng chưa chứng minh DB là nguyên nhân duy nhất. Cần kiểm tra arrival rate, throughput, downstream dependency và phạm vi các worker.

## 2. Mô hình đối chiếu: Identity + Time + Semantics

Một phép join observability đáng tin cậy cần ba nhóm thông tin:

\`\`\`text
JMX sample ─────┐
Log entry ──────┼──> SAME IDENTITY + TIME WINDOW + SEMANTICS
Trace span ─────┘
\`\`\`

### 2.1 Identity — đang nhìn đúng đối tượng?

Các trường gợi ý:
- \`service.name\`: tên ứng dụng hoặc workload.
- \`deployment.environment\`: dev/staging/prod.
- \`service.version\`: release/build.
- \`service.instance.id\`: instance cụ thể.
- \`host.name\` hoặc node identity khi phù hợp.
- \`process.pid\`: hữu ích cục bộ, nhưng không đủ duy nhất qua thời gian.
- \`jvm.start.time\`: phân biệt các lần restart trên cùng host.
- \`ObjectName\`: định danh MBean trong một MBeanServer.
- \`tenant/region\` nếu có thể dùng an toàn và được thiết kế làm phạm vi.

Hai JVM khác nhau có thể có **cùng ObjectName**. Vì vậy \`com.example.ops:type=Worker,name=Import\` không đủ để join data từ nhiều node; cần identity của process/service instance.

### 2.2 Time — so sánh trong cửa sổ phù hợp

Log event có timestamp khi logging framework ghi, span có start/end time, còn JMX sample có timestamp lúc poll. Với JMX getter cached, giá trị có thể được tính từ trước thời điểm poll.

Cần phân biệt:
1. **Event time**: khi sự kiện thật xảy ra.
2. **Observation time**: khi agent đọc JMX attribute.
3. **Collection time**: khi backend nhận sample/log.
4. **Snapshot refresh time**: khi dữ liệu cached được cập nhật.
5. **Trace start/end time**: khoảng thực hiện request/span.

Không ghép cứng các bản ghi chỉ vì timestamp text giống nhau đến giây. Hãy chọn cửa sổ liên hệ dựa trên polling interval, network delay, log buffering, trace sampling và clock skew.

### 2.3 Semantics — hai trường có đo cùng một đại lượng?

\`CompletedCount\` thường là counter tích lũy kể từ startup, còn \`completed_requests_per_second\` là rate được suy ra trong cửa sổ. \`QueueDepth\` có thể là số job pending trong JVM, trong database hoặc toàn cluster. Logs \`job completed\` có thể được ghi trước hoặc sau transaction commit.

Phải đọc contract metric thay vì chỉ so sánh tên trường.

## 3. Ví dụ Spring JMX management bean cho đối chiếu

Thiết kế một bean quản trị chỉ công bố những số liệu ổn định:

\`\`\`java
package com.example.ops;

public interface ImportWorkerStatusMBean {
    String getEffectiveState();
    long getQueueDepth();
    long getCompletedCount();
    long getFailedCount();
    long getLastSuccessfulRefreshEpochMillis();
    String getSnapshotStatus();
}
\`\`\`

Implementation đơn giản:

\`\`\`java
package com.example.ops;

import java.time.Instant;
import java.util.concurrent.atomic.AtomicLong;

public final class ImportWorkerStatus implements ImportWorkerStatusMBean {
    private final AtomicLong completed = new AtomicLong();
    private final AtomicLong failed = new AtomicLong();

    private volatile String effectiveState = "STARTING";
    private volatile long queueDepth = -1L;
    private volatile long refreshedAtEpochMillis = 0L;
    private volatile String snapshotStatus = "NOT_READY";

    public void onCompleted() {
        completed.incrementAndGet();
    }

    public void onFailed() {
        failed.incrementAndGet();
    }

    public void publishSnapshot(long depth, String state) {
        queueDepth = depth;
        effectiveState = state;
        refreshedAtEpochMillis = Instant.now().toEpochMilli();
        snapshotStatus = "OK";
    }

    @Override public String getEffectiveState() { return effectiveState; }
    @Override public long getQueueDepth() { return queueDepth; }
    @Override public long getCompletedCount() { return completed.get(); }
    @Override public long getFailedCount() { return failed.get(); }
    @Override public long getLastSuccessfulRefreshEpochMillis() {
        return refreshedAtEpochMillis;
    }
    @Override public String getSnapshotStatus() { return snapshotStatus; }
}
\`\`\`

Đây là ví dụ minh họa. Việc ghi nhiều \`volatile\` fields riêng có thể cho reader thấy các trường thuộc các lần cập nhật khác nhau. Nếu cần consistent snapshot, dùng immutable object được publish bằng \`AtomicReference\` thay vì update nhiều field độc lập. Với JMX getter poll thường xuyên, không gọi DB hoặc HTTP trực tiếp nếu có thể lấy cached values.

### 3.1 Snapshot nhất quán hơn

\`\`\`java
public record WorkerSnapshot(
    long queueDepth,
    String effectiveState,
    long refreshedAtEpochMillis,
    String status
) {}
\`\`\`

\`\`\`java
private final AtomicReference<WorkerSnapshot> snapshot =
    new AtomicReference<>(
        new WorkerSnapshot(-1, "STARTING", 0L, "NOT_READY")
    );

public void refreshSnapshot(long depth, String state) {
    snapshot.set(new WorkerSnapshot(
        depth, state, System.currentTimeMillis(), "OK")
    );
}

public long getQueueDepth() {
    return snapshot.get().queueDepth();
}
\`\`\`

Mỗi getter đọc một snapshot nhất quán tại thời điểm gọi, dù nhiều getter liên tiếp vẫn có thể đọc các phiên bản khác nhau. Nếu cần client lấy tất cả trường cùng lúc, cân nhắc xuất một OpenType/CompositeData có schema ổn định.

## 4. Đặt ObjectName để nối với logs và traces

ObjectName nên phản ánh component và identity ổn định trong phạm vi server:

\`\`\`text
com.example.ops:type=Worker,name=Import
com.example.ops:type=Cache,name=Catalog
com.example.ops:type=ConnectionPool,name=Orders
\`\`\`

Đối với nhiều JVM, agent bổ sung instance identity ngoài ObjectName:

\`\`\`text
service.name=import-service
service.instance.id=import-node-03
deployment.environment=prod
jvm.start.time=1794350000000
jmx.object_name=com.example.ops:type=Worker,name=Import
\`\`\`

Các key trên là ví dụ telemetry fields, không phải bắt buộc hay tự động xuất hiện trong MBean. Trong hệ thống nhiều node, không dựa vào hostname trần nếu container đổi host hoặc nhiều JVM chia sẻ cùng host. Kết hợp instance ID và start time để tránh join nhầm sau restart.

Cần tránh đưa token, request IDs không giới hạn, user data hoặc secret vào ObjectName: JMX registry không nên trở thành nguồn lộ thông tin.

## 5. Correlation ID trong logs và traces

Để nối một request với log và trace, thường cần:
- \`trace_id\`: định danh toàn trace.
- \`span_id\`: định danh span hiện tại.
- \`request_id\` hoặc \`operation_id\`: định danh nghiệp vụ/operation.
- \`job_id\` hoặc \`batch_id\`: định danh công việc.
- \`service.instance.id\` để biết nó chạy ở đâu.

Ví dụ structured log:

\`\`\`json
{
  "timestamp": "2026-11-11T08:02:10.125Z",
  "level": "ERROR",
  "service": "import-service",
  "instance": "import-node-03",
  "trace_id": "4a3f120049e64f52938b5cbd8f851b7a",
  "span_id": "8f5ce2b7a9d23c10",
  "batch_id": "batch-42",
  "event": "import.retry",
  "error_code": "DB_TIMEOUT"
}
\`\`\`

Một span tương ứng có thể mang \`batch.id\` và \`error.type\` theo quy ước telemetry của tổ chức. Trong Spring Boot, Micrometer Tracing hoặc OpenTelemetry instrumentation có thể hỗ trợ correlation trong logging context, nhưng cấu hình cụ thể phụ thuộc phiên bản và instrumentation. Không nên khẳng định JMX tự động gắn trace_id cho mọi attribute.

### 5.1 MDC và giới hạn của ThreadLocal

Trong nhiều logging frameworks, MDC lưu context theo thread. Nếu một request chuyển sang thread khác, gọi \`@Async\`, scheduler hoặc queue consumer, trace/request context có thể mất nếu không được propagate đúng. Khi đó JMX count có thể tăng nhưng logs/traces không nối được.

Cần test context propagation qua executor và boundary async; tránh truyền \`trace_id\` thủ công vào mọi JMX attribute vì attribute đại diện trạng thái tổng hợp, không phải một request cụ thể.

## 6. JMX thường là aggregate, trace thường là từng yêu cầu

Ví dụ:

\`\`\`text
JMX:
  ActiveWorkers = 16
  QueueDepth = 1200
  FailedCount = 245

Traces:
  trace-001: import B42, db.query 900ms
  trace-002: import B43, db.query 1.2s
  trace-003: import B44, timeout after 3s
\`\`\`

JMX nói rằng backlog và errors đang hiện hữu. Traces giúp nhìn các request được sample có chung bottleneck không. Nhưng nếu trace sampling là 10%, ba trace có thể không đại diện đầy đủ toàn bộ các request. Không tính error rate từ số trace lỗi nếu chưa hiểu sampling policy và cardinality.

Trong một incident, nên:
1. Xác minh phạm vi JMX: JVM nào, instance nào, metric nào.
2. Tìm logs trong cùng timeframe và instance.
3. Phân tích các trace spans đại diện, đặc biệt error/slow traces nếu có.
4. Đối chiếu với database/network metrics để xác nhận giả thuyết.
5. Kiểm tra sampling, missing instrumentation và data lag.

## 7. Cách đọc counter JMX đúng qua thời gian

Counter tích lũy phải được diễn giải theo delta/rate, không dùng giá trị tuyệt đối để suy ra tốc độ:

\[
\text{rate} = \frac{C(t_2)-C(t_1)}{t_2-t_1}
\]

Nếu \`CompletedCount\` từ 1.000 lên 1.200 trong 20 giây, tốc độ gần đúng là 10 completion/giây.

Điều kiện:
- Hai sample thuộc cùng instance và cùng vòng đời process.
- Counter không reset giữa hai lần đọc.
- Timestamps phù hợp và interval khác 0.
- Nếu counter có wrap/reset, thuật toán rate nhận biết trạng thái đó.
- Counter nghĩa là số lượng event đã được ghi nhận, không nhất thiết transaction commit hoàn tất nếu instrumentation đặt sai chỗ.

Sau JVM restart, \`CompletedCount\` có thể về 0. Nếu không nối với \`jvm.start.time\`, đồ thị có thể hiện một “negative rate” gây hiểu nhầm. Traces/logs của lần process trước phải được phân biệt với instance mới.

## 8. Snapshot stale và vấn đề thời gian

Một JMX getter cached có thể trả số liệu \`QueueDepth=500\` với \`LastRefreshTime\` cách hiện tại 5 phút. Trong khi logs vài giây trước nói queue đã cạn. Nếu không xem freshness, hai nguồn có vẻ mâu thuẫn.

Cần công bố:
- \`LastSuccessfulRefreshEpochMillis\`.
- \`SnapshotStatus\` như \`OK\`, \`STALE\`, \`ERROR\`.
- \`SnapshotAgeSeconds\`.
- \`RefreshFailureCount\` nếu cần.
- Chính sách TTL và hành vi fallback.

Nếu snapshot stale, không dùng giá trị đó như bằng chứng hiện tại khi ra quyết định điều khiển. Đối với dashboard, có thể hiển thị stale state rõ thay vì giả định queue đứng yên.

### 8.1 Clock skew

Máy khác nhau có thể có đồng hồ lệch, logs được buffer rồi gửi trễ, spans có thời điểm đến sau sự kiện. Hãy:
- Dùng NTP/chrony hoặc đồng bộ thời gian hệ thống.
- Lưu timestamp UTC có timezone.
- Ưu tiên event timestamps thay vì chỉ ingestion timestamps.
- Chọn join window rộng vừa đủ theo độ trễ collection.
- Không sắp thứ tự nhân quả tuyệt đối giữa hai node chỉ từ milliseconds nếu chưa bảo đảm clock accuracy.

Trace parent-child relation thường giúp giải thích causality tốt hơn việc so timestamp text đơn giản.

## 9. Correlate JMX notification với log và trace

JMX notification có thể báo chuyển trạng thái:

\`\`\`java
Notification n = new Notification(
    "com.example.worker.paused",
    objectName,
    sequence.incrementAndGet(),
    System.currentTimeMillis(),
    "Worker paused by maintenance request"
);
n.setUserData("operation-739");
sendNotification(n);
\`\`\`

Một log có thể dùng cùng \`operation_id\`:

\`\`\`text
2026-11-11T08:05:00Z INFO operation_id=operation-739
event=worker.pause.accepted instance=import-node-03
\`\`\`

Trace của đường điều khiển có thể có span \`management.pause\` cùng operation ID, nếu ứng dụng đã instrument call path. Điều này không tự xuất hiện chỉ vì annotation \`@ManagedOperation\`; phải chủ động tạo observation/tracing context hoặc truyền ID đáng tin cậy.

Notification sequence number thường chỉ có ý nghĩa trong emitter/vòng đời; không dùng sequence đơn lẻ làm global correlation ID. Cũng không giả định notification sẽ được replay sau remote disconnect.

## 10. Với operation JMX, nên dùng operation ID

Một JMX operation có side effect cần được quan sát:

\`\`\`java
@ManagedOperation(description = "Request a bounded worker pause")
public String requestPause(String reason) {
    String operationId = UUID.randomUUID().toString();
    controlService.requestPause(operationId, reason);
    return operationId;
}
\`\`\`

Tầng service có thể ghi:

\`\`\`text
operation_id=... event=worker.pause.accepted
operation_id=... event=worker.pause.applied
operation_id=... event=worker.pause.failed
\`\`\`

JMX attributes có thể cung cấp \`LastOperationId\` và \`EffectiveState\` để đối chiếu. Nếu operation bất đồng bộ, response \`ACCEPTED\` không đồng nghĩa hành động đã hoàn thành.

Với thao tác có rủi ro, cần:
- Authentication và authorization ở JMX connector/control plane.
- Validate input và precondition server-side.
- Audit theo identity được xác thực, không tin \`actor\` do client tự gửi.
- Idempotency hoặc request ID để giảm double execution.
- Không retry mù sau client timeout.
- Giới hạn payload trong logs/traces để tránh lộ secrets.

## 11. Tracing và Spring AOP/JMX

Nếu MBean method gọi service qua Spring proxy:

\`\`\`text
JMX invoke
   |
   v
Management adapter
   |
   v
Spring service proxy (@Transactional / tracing advisor)
   |
   v
Business method
   |
   v
Repository / HTTP dependency
\`\`\`

Traces có thể bắt đầu từ adapter hoặc từ service instrumentation tùy cấu hình. Không mặc định JMX connector tự tạo incoming HTTP span hay propagate W3C trace context, vì JMX remote invocation không phải HTTP request thông thường.

Nếu muốn trace quản trị, tạo span thủ công tại boundary JMX operation bằng instrumentation API được chọn, ghi operation name, ObjectName đã được sanitize và operation ID. Tránh đặt high-cardinality raw parameters hoặc dữ liệu nhạy cảm trong span attributes.

Một cách tối giản là giữ JMX metrics aggregate và dùng logs có \`operation_id\` để nối với traces của service call. Cách này đủ cho nhiều runbook mà không cần instrument toàn bộ connector protocol.

## 12. Một quy trình incident thực tế

### Tình huống: backlog tăng nhanh, throughput giảm

Báo động:
\`\`\`text
QueueDepth > 1000 trong 5 phút
CompletedRate giảm hơn 50%
\`\`\`

Bước 1 — Xác minh JMX:
- Kiểm tra đúng instance và ObjectName.
- Đọc QueueDepth, ActiveWorkers, CompletedCount, FailedCount.
- Kiểm tra timestamp/freshness.
- Xem JVM ThreadCount, GC, heap/CPU nếu cần.

Bước 2 — Tìm logs tương ứng:
- Filter theo service/instance và khoảng 10–15 phút.
- Tìm retry, timeout, circuit breaker, task rejected và config changes.
- Nhóm theo error code/dependency, không chỉ đếm mọi ERROR.
- Kiểm tra deployment/restart gần thời điểm chỉ số đổi.

Bước 3 — Kiểm tra traces:
- Xem traces chậm/lỗi trong cùng time window.
- Kiểm tra span của database, HTTP, queue consumer.
- So sánh latency và tỷ lệ failed spans.
- Chú ý sampling: trace vắng mặt không chứng minh request không tồn tại.

Bước 4 — Kiểm tra giả thuyết:
\`\`\`text
QueueDepth tăng
  + DB query latency tăng
  + Retry logs tăng
  + CompletedRate giảm
       |
       v
Giả thuyết: downstream DB chậm đang giới hạn throughput
       |
       v
Xác nhận thêm bằng DB pool saturation, DB wait, deploy changes
\`\`\`

Bước 5 — Can thiệp:
- Dùng runbook và operation được phép.
- Ghi operation ID và audit.
- Kiểm tra trạng thái hiệu lực sau lệnh.
- Theo dõi QueueDepth/CompletedRate và trace latency sau thay đổi.

Không coi correlation là causation: DB chậm có thể là kết quả của overload do một nguyên nhân khác. Phải đánh giá bằng nhiều tín hiệu độc lập.

## 13. Mâu thuẫn giữa JMX và logs: các nguyên nhân thường gặp

| JMX | Logs/traces | Giải thích có thể |
|---|---|---|
| \`ErrorCount\` tăng | Không có ERROR log | Log sampling, cấp độ log khác, counter tăng không ghi log |
| QueueDepth cao | Logs nói queue empty | Snapshot cũ, khác partition/instance, semantics khác |
| ActiveWorkers=0 | Trace span vẫn chạy | Traces từ node khác, job đã hoàn tất, cache/collection lag |
| CompletedCount reset | Không có deployment log | JVM restart, counter reset, log thiếu |
| Operation status=RUNNING | Log nói completed | State snapshot cập nhật chậm hoặc status mapping sai |
| GC pause tăng | Không có application exception | Runtime pressure không nhất thiết ném exception |
| Latency JMX thấp | Trace latency cao | JMX getter đọc cache, trace đo dependency |
| Notification \`paused\` mất | Log \`pause applied\` có | Listener filter, remote disconnect, no replay |

Không sửa bằng cách thay một nguồn cho khớp nguồn khác mà chưa hiểu cách đo. Trước tiên xác định identity, timestamps, refresh interval và event semantics.

## 14. Dashboard kết hợp JMX, logs và traces

Một dashboard vận hành tốt có thể có:

\`\`\`text
Service / Instance / Version
-------------------------------------------
JMX/metrics: QueueDepth, ActiveWorkers,
             CompletedRate, FailedRate,
             SnapshotAgeSeconds

Logs:        Error count by code,
             recent retries,
             configuration changes

Traces:      Slow spans,
             dependency duration,
             failed request examples

Actions:     Link runbook,
             operation history,
             safe management control
-------------------------------------------
\`\`\`

Filter chung nên dùng service.name, environment, instance ID và time range. Một trace detail có thể liên kết tới logs cùng \`trace_id\`. Một JMX metric aggregate thường chỉ liên kết tới **time window và instance**, chứ không có trace_id duy nhất.

Đối với alert, không nên trigger operation có side effect tự động chỉ vì một chỉ số JMX vượt ngưỡng. Hãy kết hợp nhiều tín hiệu, hysteresis/cooldown và quyền phê duyệt khi cần.

## 15. Kết nối JMX tới observability backend

Một số kiến trúc:

1. JMX exporter/agent poll MBeanServer rồi chuyển attribute thành metrics.
2. Logging appender gửi structured logs tới log backend.
3. OpenTelemetry/Micrometer Tracing gửi spans tới tracing backend.
4. Dashboard truy vấn cả ba, nối bằng resource metadata và time range.

Cần tránh hai agent cùng đọc một expensive getter theo chu kỳ rất ngắn. JMX getter có thể thực hiện SQL/HTTP I/O; polling nhiều hơn không phải lúc nào cũng làm dữ liệu tốt hơn, có thể tạo thêm tải.

Thông số cần chuẩn hóa:
- Metric name/unit/type/counter reset behavior.
- Sampling interval và staleness.
- Resource attributes trên từng nguồn.
- Environment/version/instance identity.
- Timezone và clock synchronization.
- Retention và privacy.
- Access control cho management operation.

## 16. Structured logging và field design

Một log nên chứa dữ liệu giúp join nhưng không làm tăng cardinality hoặc lộ thông tin:

\`\`\`json
{
  "timestamp": "2026-11-11T09:15:00Z",
  "level": "WARN",
  "service.name": "import-service",
  "service.instance.id": "import-node-03",
  "event.name": "worker.retry",
  "operation_id": "op-739",
  "batch_id": "batch-42",
  "error.type": "DependencyTimeout",
  "attempt": 2
}
\`\`\`

Không nhất thiết mọi log phải có trace ID. Startup logs, scheduled tasks hoặc JMX polling có thể không nằm trong một trace đang active. Trong những trường hợp đó, instance ID/time window và operation ID vẫn đủ để điều tra.

Không ghi credentials, raw HTTP payload, customer identifiers, authorization headers hoặc stack trace chứa secrets. Với ID có tính nhạy cảm, cần pseudonymize/hash hoặc redaction theo chính sách tổ chức.

## 17. Không dùng JMX attribute cho mỗi request

Một anti-pattern:

\`\`\`java
@ManagedAttribute
public String getLastRequestTraceId() {
    return lastTraceId;
}
\`\`\`

Nếu nhiều request song song, giá trị thay đổi liên tục và không đại diện một request ổn định. Polling có thể bỏ lỡ gần như toàn bộ request. Trả trace ID qua JMX aggregate cũng có thể tăng rủi ro lộ thông tin và gây coupling giữa management API với telemetry.

Tốt hơn:
- Trace IDs nằm trong logs/spans của từng request.
- JMX công bố aggregate counters, effective state và last error category.
- Operation có side effect trả operation ID để audit.
- Khi cần tra một request cụ thể, dùng logs/traces backend có quyền truy cập thích hợp.

## 18. Testing việc đối chiếu dữ liệu

Một integration test có thể kiểm tra cả metric và log event của một business action:

\`\`\`java
@Test
void completedJobUpdatesMetricAndEmitsLogEvent() {
    // Arrange: worker service fixture và log appender test.
    // Act: process một job thành công.
    // Assert: completed counter tăng một đơn vị.
    // Assert: structured log event job.completed có job ID tương ứng.
}
\`\`\`

Đây là skeleton. Cần thiết lập test appender phù hợp logging framework, đảm bảo không dùng log global state làm test song song nhiễu nhau. Tracing test có thể dùng in-memory span exporter để xác minh span name, status và resource attributes.

Quan trọng: test "JMX counter tăng" không đồng nghĩa "trace chắc chắn tồn tại", vì tracing có sampling và instrumentation riêng. Trong integration test, cần cố định sampler để không phụ thuộc quyết định ngẫu nhiên.

### 18.1 Test JMX contract

\`\`\`java
MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName name = new ObjectName(
    "com.example.ops:type=Worker,name=Import");

assertTrue(server.isRegistered(name));

MBeanInfo info = server.getMBeanInfo(name);
assertNotNull(info);
\`\`\`

Trong fixture thực tế, dùng đúng server mà exporter chọn; nên có namespace test riêng. Xác minh attributes, units, count semantics và freshness metadata. Test cleanup khi Spring context đóng để không để lại MBean stale.

### 18.2 Test operation audit

1. Dùng MBean test an toàn có operation không phá dữ liệu.
2. Gọi operation qua \`MBeanServerConnection.invoke()\`.
3. Assert response operation ID hợp lệ.
4. Assert audit log có operation ID và outcome.
5. Nếu có spans, assert trace/span attributes đã được redact.
6. Assert post-state thể hiện operation đã hoàn tất, không chỉ accepted.
7. Đảm bảo test không dựa vào exact timing và không dùng remote production connector.

## 19. Notification như tín hiệu, không là nguồn duy nhất

JMX notifications có thể giúp giảm độ trễ phát hiện thay đổi trạng thái. Tuy nhiên:
- Remote clients có thể disconnect.
- Listener filters có thể loại event.
- Sequence number chỉ thuộc emitter/contract nhất định.
- Notification có thể đến chậm hoặc callback lỗi.
- Không mặc định có durability hoặc replay.

Khi một notification báo \`worker.failed\`, nên đối chiếu với logs/traces trong khoảng thời gian đó và đọc JMX effective state hiện tại. Khi reconnect sau sự cố mạng, client cần reconcile current state thay vì giả định mọi event đã được nhận đủ.

## 20. Security và observability

Dữ liệu quản trị có thể chứa thông tin nhạy cảm. Hãy tách:
- **Telemetry read-only:** metric/summary cho nhiều người quan sát.
- **Management control:** operation thay đổi trạng thái, cần quyền cao hơn.
- **Audit:** danh tính caller và hành động được bảo vệ.
- **Trace/log payload:** có redaction và giới hạn truy cập.

Khi dùng remote JMX, bảo vệ connector bằng authentication, TLS, network isolation và authorization. Spring \`@ManagedResource\` không tự kế thừa mọi HTTP Spring Security rule.

Nếu dùng management adapter tạo trace cho JMX operation, không tự tin rằng tham số \`actor\` do client gửi là identity đáng tin cậy. Identity cần đến từ boundary xác thực của connector/control plane.

## 21. Runbook đối chiếu dữ liệu cho incident

### Bước 1 — Chốt phạm vi
- Xác định environment, service, version, instance và JVM start time.
- Xác nhận connector JMX trỏ đúng MBeanServer.
- Chọn time window đủ bao phủ polling interval và log/trace lag.

### Bước 2 — Kiểm tra JMX/metrics
- Kiểm tra state, queue, counters và JVM pressure.
- Xác minh freshness/TTL.
- Tính delta/rate với restart detection.

### Bước 3 — Đọc logs
- Filter cùng instance/time window.
- Nhóm theo error code, retry và dependency.
- Tìm config/deploy/restart events.
- Kiểm tra trace_id hoặc operation_id khi có.

### Bước 4 — Phân tích traces
- Tìm slow/error traces tương ứng.
- Đọc parent-child spans và critical path.
- Kiểm tra sampling/instrumentation.
- So sánh latency, queueing và downstream duration.

### Bước 5 — Kiểm tra giả thuyết
- So khớp nhiều tín hiệu, không kết luận từ một metric.
- Loại trừ clock skew, stale snapshot và khác instance.
- Kiểm tra thay đổi gần thời điểm incident.

### Bước 6 — Can thiệp và xác minh
- Chỉ gọi control operation được phép.
- Ghi operation ID và audit.
- Đọc effective state và quan sát metrics/logs/traces sau can thiệp.
- Không retry mù sau timeout vì side effect có thể đã xảy ra.

## 22. Các lỗi phổ biến

**“JMX cho biết nguyên nhân gốc.”** Không thường xuyên. Nó thể hiện trạng thái; logs/traces và dependency metrics giúp điều tra nguyên nhân.

**“ObjectName đủ làm identity toàn cluster.”** Không. ObjectName chỉ duy nhất trong từng MBeanServer; cần service/instance/JVM identity.

**“Log timestamp trùng sample timestamp nghĩa là cùng sự kiện.”** Chưa chắc; polling, buffering, clock skew và snapshot freshness có thể lệch.

**“Một JMX counter lớn nghĩa là rate đang cao.”** Không. Counter tích lũy phải tính delta/rate và phát hiện reset.

**“Không thấy trace nên request không xảy ra.”** Không. Sampling hoặc instrumentation có thể bỏ sót.

**“Một operation JMX có trace_id tự động.”** Không mặc định. Muốn trace quản trị cần instrumentation riêng.

**“JMX notification sẽ bù event sau reconnect.”** Không mặc định; đọc lại trạng thái hiện tại.

**“Bật poll nhanh hơn luôn tốt.”** Không. Expensive getter có thể làm tăng tải và giảm ổn định.

**“Mỗi log đều phải có trace_id.”** Không. Startup, jobs và background tasks có thể cần correlation ID khác.

## 23. Bài tập vận dụng

**Bài 1 — Counter reset.** CompletedCount là 10.000 trước deploy, 200 sau deploy. Dashboard tính rate âm. Hãy thiết kế logic phát hiện JVM restart và reset counter.

**Bài 2 — Snapshot stale.** JMX QueueDepth=500 nhưng logs cho biết queue đã xử lý xong. Hãy tìm các trường timestamp/status cần kiểm tra trước khi kết luận có bug.

**Bài 3 — Multi-instance.** Hai JVM công bố cùng ObjectName. Hãy đề xuất bộ trường identity để join metric/logs/traces đúng instance.

**Bài 4 — Trace sampling.** JMX FailedCount tăng 100 nhưng chỉ có 5 error traces. Giải thích vì sao không thể kết luận 95 lỗi đã mất.

**Bài 5 — Operation audit.** JMX operation requestPause trả operation ID. Thiết kế log events accepted/applied/failed và test chứng minh có thể đối chiếu.

**Bài 6 — Incident.** QueueDepth tăng, ActiveWorkers ổn định, DB span latency tăng. Hãy lập giả thuyết, kiểm chứng bằng logs/metrics và chọn hành động ít rủi ro.

## Tổng kết

Đối chiếu JMX với logs và traces giúp chuyển từ **“hệ thống đang ở trạng thái nào?”** sang **“điều gì xảy ra và vì sao?”**. Để làm đúng, phải thống nhất identity của service/JVM, thời gian, metric semantics và mức độ freshness. JMX attributes phù hợp với trạng thái tổng hợp, logs ghi events có thể đối chiếu bằng operation ID/trace ID, còn traces cho biết đường đi và latency của công việc được instrument. Một kết luận có cơ sở cần kiểm tra sampling, counter resets, clock skew và khác biệt giữa từng instance. Với management operations, audit và post-state verification giúp nối hành động vận hành với tác động thực tế mà không phụ thuộc vào suy đoán hoặc retry mù.
