# Tắt có trật tự, thu hồi kết nối và xử lý yêu cầu chưa hoàn tất

> **Chương:** Hiệu năng và vận hành  
> **Module:** SPRING_WEB_SERVICES — phát triển dịch vụ SOAP theo hướng contract-first với Spring Web Services, thiết kế XSD/WSDL, ánh xạ JAXB và xây dựng endpoint cùng SOAP client; xử lý SOAP Fault, interceptor, XML security, WS-Security, chứng chỉ và kiểm thử tương thích trong tích hợp doanh nghiệp ổn định.

## 1. Vì sao SOAP service cần graceful shutdown?

Một SOAP request đi qua HTTP connector, servlet container, MessageDispatcherServlet, XML parser, endpoint interceptors, JAXB, business service, database và có thể gọi tiếp sang SOAP partner. Khi process dừng đột ngột, request có thể đang parse attachment, chờ database, gọi đối tác hoặc commit giao dịch. Socket bị đóng không cho biết business operation đã chạy đến đâu.

Tắt có trật tự là quy trình ngừng nhận công việc mới, cho công việc đã được chấp nhận thời gian hoàn tất, thu hồi tài nguyên theo thứ tự và kết thúc process trước deadline của nền tảng. Cần phối hợp nhiều nhóm tài nguyên:

- **Server:** ngừng nhận request mới, drain request đang chạy, hoàn tất hoặc abort an toàn.
- **Client:** ngừng tạo outbound calls mới, đợi calls đang chạy, đóng connection pools và executors.
- **Business workflow:** xác định request nào đã commit, request nào chưa xử lý và request nào có kết quả không chắc chắn.
- **Platform:** gửi tín hiệu dừng, dành đủ grace period và không kill process trước khi ứng dụng hoàn tất.

Nếu chỉ dừng HTTP listener, executor có thể vẫn giữ JVM sống. Nếu đóng connection pool quá sớm, request đang gọi partner có thể bị cắt. Nếu chỉ đợi HTTP threads, background jobs hoặc temporary files vẫn có thể bị bỏ lại.

Sau bài này, bạn có thể mô hình hóa lifecycle shutdown, cấu hình graceful shutdown của Spring Boot, dùng readiness để rút instance khỏi traffic, drain SOAP requests, dừng workers, thu hồi HTTP pools, xử lý retry/idempotency và kiểm thử SIGTERM.

**Nguyên tắc:** Graceful shutdown không bảo đảm mọi request luôn hoàn tất. Nó tạo một khoảng thời gian có kiểm soát để hoàn tất việc đang chạy và để phần còn lại có thể retry/reconcile an toàn.

## 2. Mô hình lifecycle shutdown

~~~mermaid
stateDiagram-v2
    [*] --> Starting
    Starting --> Ready
    Ready --> Quiescing: shutdown requested
    Quiescing --> Draining: reject new work
    Draining --> StoppingWorkers: drained or deadline
    StoppingWorkers --> ClosingClients
    ClosingClients --> ClosingContext
    ClosingContext --> Stopped
    Draining --> ForcedStop: deadline exceeded
    StoppingWorkers --> ForcedStop: deadline exceeded
    ClosingClients --> ForcedStop: deadline exceeded
    ForcedStop --> Stopped
~~~

| Trạng thái | Hành vi |
|---|---|
| Starting | Khởi tạo context, server, pools, schema và keys |
| Ready | Nhận traffic mới |
| Quiescing | Đánh dấu instance không còn nhận traffic mới |
| Draining | Chờ request đã accept hoàn tất |
| StoppingWorkers | Ngừng scheduler/consumer, drain queue |
| ClosingClients | Đóng outbound clients và pools |
| ClosingContext | Đóng Spring application context |
| ForcedStop | Deadline hết, hủy phần việc còn lại theo policy |
| Stopped | Process dừng |

Thứ tự thực tế phụ thuộc container/framework. Phải xác định component nào chặn việc nhận request, component nào đo in-flight requests và component nào sở hữu từng resource.

## 3. Readiness khác liveness

Readiness trả lời instance có nên nhận traffic mới hay không. Liveness trả lời process có còn sống/tiến triển theo tiêu chí health check hay không. Khi shutdown bắt đầu, readiness thường cần chuyển DOWN trước khi đóng listener, trong khi liveness vẫn UP trong giai đoạn drain.

Trình tự đề xuất:

1. Nhận tín hiệu shutdown.
2. Đặt application thành quiescing.
3. Readiness chuyển DOWN để load balancer/orchestrator ngừng route traffic mới.
4. Chờ endpoint removal propagate.
5. HTTP server ngừng nhận connections mới và drain exchanges đã accept.
6. Dừng background producers/consumers.
7. Chờ in-flight SOAP operations và jobs.
8. Thu hồi outbound clients, pools và application context.

Readiness không thay server-side graceful shutdown. Request vẫn có thể đến trong khoảng propagation hoặc qua keep-alive connection đã tồn tại. Nếu cả readiness và liveness cùng fail ngay, orchestrator có thể kill process trước khi drain xong.

## 4. Graceful shutdown trong Spring Boot

Các phiên bản Spring Boot hiện đại hỗ trợ graceful shutdown cho embedded web servers. Cấu hình điển hình:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~

server.shutdown yêu cầu embedded web server ngừng nhận requests mới và cho requests đang xử lý thời gian hoàn tất. spring.lifecycle.timeout-per-shutdown-phase giới hạn thời gian cho từng Spring lifecycle shutdown phase. Kiểm tra tài liệu đúng Spring Boot version, embedded container và deployment model; behavior không giống nhau trên mọi Tomcat/Jetty/Undertow version.

### 4.1. Timeout phase và tổng deadline

Timeout của Spring lifecycle phase không nhất thiết bằng tổng thời gian process được orchestrator cho phép. Platform grace period còn phải bao gồm readiness propagation, HTTP drain, background workers, outbound calls, cleanup và context destruction.

Đừng để nhiều component tự chờ tối đa 30 giây nối tiếp nếu platform chỉ cho process 30 giây tổng cộng. Đặt deadline tổng lớn hơn các phase nội bộ với headroom hợp lý.

### 4.2. Embedded và external servlet container

Với embedded server, Spring Boot quản lý web server lifecycle. Với WAR deploy trong external servlet container, lifecycle do container quản lý nhiều hơn; thuộc tính Boot không tự điều khiển mọi behavior bên ngoài. Test đúng mô hình deploy production.

## 5. Readiness và drain trong Kubernetes

Một deployment cần phối hợp readiness, SIGTERM, preStop và terminationGracePeriodSeconds. Readiness DOWN để rút instance khỏi routing; SIGTERM kích hoạt shutdown hook/framework lifecycle; preStop nếu có không được tiêu hết grace period; termination grace phải đủ cho drain và cleanup; load balancer cần thời gian propagate endpoint removal.

Ví dụ phân bổ budget 60 giây:

| Giai đoạn | Budget minh họa |
|---|---:|
| Readiness propagation | 5 giây |
| Drain SOAP requests | 35 giây |
| Stop workers và client pools | 10 giây |
| Context cleanup/headroom | 10 giây |
| Tổng | 60 giây |

Đây là ví dụ planning, không phải default. Dựa trên p99 request duration, downstream timeout và platform behavior thực tế.

Không dùng sleep cứng dài trong preStop nếu readiness/drain signal có thể làm tốt hơn. Nếu cần delay, đo propagation time và bảo đảm còn đủ thời gian cho process cleanup.

## 6. Dừng nhận request mới

Readiness là tín hiệu ngoài; application có thể cần trạng thái quiescing nội bộ để chặn traffic từ nguồn khác hoặc background producers.

~~~java
import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.stereotype.Component;

@Component
public class ShutdownGate {
    private final AtomicBoolean accepting = new AtomicBoolean(true);

    public boolean isAccepting() {
        return accepting.get();
    }

    public void stopAccepting() {
        accepting.set(false);
    }
}
~~~

Admission filter/interceptor có thể kiểm tra trạng thái này. Với SOAP, định nghĩa response phù hợp khi request mới đến sau quiescing: HTTP/service unavailable hoặc SOAP Fault theo API contract. Không trả success giả.

Chặn sớm ở ingress/container tốt hơn chỉ kiểm tra trong endpoint vì request có thể đã tiêu tốn parser/heap trước khi tới method business.

### 6.1. In-flight request counter

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public final class InFlightRequests {
    private final AtomicInteger active = new AtomicInteger();

    public void entered() {
        active.incrementAndGet();
    }

    public void completed() {
        int remaining = active.decrementAndGet();
        if (remaining < 0) {
            throw new IllegalStateException(
                    "Unbalanced request accounting");
        }
    }

    public int current() {
        return active.get();
    }
}
~~~

Đây chỉ là building block. completed phải được gọi đúng một lần trong finally sau khi request kết thúc, kể cả parse error, Fault, timeout và exception. Không đếm riêng ở endpoint nếu request có thể fail trước endpoint. Spring/container đã có graceful behavior; chỉ thêm custom counter khi có nhu cầu đo/điều phối rõ ràng.

## 7. Drain SOAP requests đang xử lý

Một request có thể đang đọc HTTP body/MIME attachment, verify WS-Security, validate XSD, unmarshal JAXB, chạy transaction, gọi downstream hoặc serialize response. Không phải mọi stage có thể dừng an toàn. Transaction đã commit không thể bị coi như chưa chạy chỉ vì response socket đóng.

| Loại operation | Drain policy |
|---|---|
| Read-only query nhanh | Cho hoàn tất trong drain window |
| Write transaction ngắn | Đợi commit/rollback |
| Long-running synchronous | Giới hạn duration, cân nhắc async |
| Large upload/attachment | Không nhận mới; hoàn tất hoặc abort/cleanup |
| Outbound partner call | Timeout nằm trong shutdown budget |
| Background job | Ngừng claim job mới; xử lý lease/current job |

Không đóng datasource/connection pool trong khi request còn dùng transaction. Đóng dependencies sau khi consumers của chúng đã dừng.

## 8. Background executors và schedulers

SOAP systems có thể chạy audit, outbox publisher, attachment scanner, partner polling, reconciliation hoặc cleanup jobs. Shutdown cần ngừng tạo tasks mới, dừng scheduler triggers, drain bounded queues, đợi workers trong budget và để durable queue/lease khôi phục phần còn lại sau restart.

~~~java
@Bean
ThreadPoolTaskExecutor documentExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(8);
    executor.setQueueCapacity(100);
    executor.setThreadNamePrefix("document-worker-");
    executor.setWaitForTasksToCompleteOnShutdown(true);
    executor.setAwaitTerminationSeconds(20);
    return executor;
}
~~~

Setter shutdown behavior cần kiểm tra trên Spring Framework version thực tế. Bounded queue quan trọng vì queue vô hạn có thể giữ request/attachment references và làm shutdown kéo dài.

Không chờ vô hạn một task bị block trong network call hoặc scanner. Đặt timeout cho dependencies, await termination hữu hạn và định nghĩa cách retry/requeue. Dừng schedule triggers trước worker executor để không phát task mới khi executor đã đóng. Dùng distributed lease/lock nếu cron task chỉ được chạy một lần trên cluster.

## 9. Thu hồi WebServiceTemplate và outbound HTTP connections

WebServiceTemplate là abstraction client. HTTP connections thuộc message sender và underlying HTTP client/pool. Đóng template không nhất thiết đóng pool nếu pool được quản lý bởi bean khác hoặc dùng chung.

Xác định rõ:
- Template dùng sender nào?
- Sender dùng HTTP client/connection manager nào?
- Pool có shared giữa nhiều templates không?
- Bean nào sở hữu trách nhiệm close?
- Có eviction/housekeeping threads không?
- Interceptor có resource riêng không?

Trình tự phía client: quiesce gateway để không nhận calls mới; đợi in-flight calls hoặc tới deadline; cancel/abort calls còn lại theo policy; đóng pool bởi owner; dừng housekeeping threads; rồi đóng context.

Nếu nhiều templates dùng chung pool, chỉ owner pool nên đóng sau khi tất cả callers đã dừng. Connection pool có API shutdown khác nhau theo Apache HttpComponents, JDK HttpClient và custom sender; dùng lifecycle callback đúng version. Không đóng pool shared quá sớm.

### 9.1. Keep-alive và stale connections

Client có thể giữ persistent connections tới instance đang shutdown. Server graceful shutdown cần ngừng nhận exchanges mới trong khi drain existing exchanges. Load balancer/client phải xử lý connection close và reconnect sang instance healthy. Kiểm tra behavior với keep-alive, proxy và TLS termination thực tế.

## 10. Timeout nằm trong shutdown budget

Request gọi partner có read timeout 90 giây nhưng platform chỉ cho process 30 giây grace period thì không thể bảo đảm request hoàn tất. Outbound deadline phải nhỏ hơn thời gian drain còn lại, có tính serialization, DB commit và response flush.

~~~text
Platform termination deadline
  ├─ readiness propagation
  ├─ in-flight SOAP drain
  │    ├─ downstream connect timeout
  │    ├─ downstream response timeout
  │    └─ business commit + response write
  ├─ worker drain
  └─ client pool + context cleanup
~~~

Đặt per-operation timeout, deadline propagation nếu ứng dụng hỗ trợ, graceful cancellation và metrics cho requests còn lại. Không tăng timeout vô hạn để “bảo vệ” request; điều đó có thể khiến shutdown không bao giờ kết thúc.

## 11. Request chưa hoàn tất và kết quả không chắc chắn

Khi kết nối bị đóng, client có thể không biết server đã xử lý tới đâu:

1. Request chưa tới server hoặc bị reject trước business execution.
2. Server đang xử lý và chưa commit.
3. Server đã commit nhưng response chưa tới client.

Client không thể suy ra business state chỉ từ socket reset/timeout.

### 11.1. Idempotency

Với write operations:
- Có request ID/idempotency key ổn định qua retry.
- Scope key theo authenticated partner/tenant và operation.
- Lưu trạng thái processing/completed cùng result.
- Cùng key/cùng payload trả kết quả trước đó.
- Cùng key nhưng payload khác bị reject conflict.
- Retry sau timeout truy vấn trạng thái trước khi thực hiện lại.

Không dùng SOAP MessageID làm idempotency key nếu contract không bảo đảm uniqueness, persistence và retention.

### 11.2. Retry classification

Không retry mọi lỗi:
- SOAP Sender/Client Fault thường là request/contract error.
- Receiver/Server Fault chỉ retry nếu fault code/operation policy cho phép.
- Connection reset/timeout có outcome không chắc chắn; cần idempotency/status lookup.
- HTTP 429/503 cần tôn trọng retry hints nếu contract cho phép.
- TLS/certificate failure không nên retry liên tục như lỗi transient.

Khi local app đã quiescing, không bắt đầu retry mới làm tăng load. Retry phải nằm trong deadline của caller.

## 12. Database transaction, outbox và background jobs

Operation có thể commit DB rồi mới publish event/call partner. Shutdown giữa hai bước tạo trạng thái nửa hoàn tất.

Dùng outbox để commit business state và message record trong cùng transaction. Publisher ngừng claim jobs mới khi shutdown; job đang chạy hoàn tất hoặc lease hết hạn để instance mới claim lại. Consumer downstream idempotent theo job/event ID. Reconciliation phát hiện state đã commit nhưng notification chưa gửi.

| State | Shutdown behavior |
|---|---|
| PENDING | Giữ trong durable queue |
| CLAIMED/LEASED | Đợi trong budget hoặc để lease expire |
| PROCESSING | Ghi checkpoint/idempotency; không giả định rollback |
| COMPLETED | Không chạy lại nếu không cần |
| FAILED_RETRYABLE | Retry theo schedule |
| FAILED_TERMINAL | Giữ diagnostic và xử lý theo policy |

Không dựa vào in-memory queue duy nhất cho công việc không được phép mất.

## 13. Uploads, MTOM và temporary files

Request MTOM có thể đang stream attachment vào disk khi shutdown bắt đầu. Phải xác định có ngừng upload mới không, upload đang nhận được hoàn tất hay abort, partial file được đánh dấu incomplete/xóa ra sao, async scanner còn ownership không, durable storage đã commit chưa và retry có tạo duplicate không.

Không xóa temp file trong finally của HTTP request nếu worker async còn dùng. Chuyển ownership qua job/storage lifecycle. Orphan cleanup cần nhận biết file nào thuộc job còn lease hợp lệ để không xóa nhầm.

## 14. Spring lifecycle và thứ tự dừng

Spring cung cấp Lifecycle, SmartLifecycle, bean destroy methods và context close callbacks. Dùng chúng cho resources do ứng dụng sở hữu; không xây shutdown framework riêng phức tạp nếu Boot/embedded server đã xử lý web server lifecycle.

SmartLifecycle cho component tham gia start/stop và khai báo phase. Phase cao hơn thường start sau và stop trước phase thấp hơn. Có thể dùng để dừng producers trước workers hoặc đóng clients sau workers. Kiểm tra phase ordering theo Spring version.

~~~java
@Component
public class PartnerPollingLifecycle implements SmartLifecycle {
    private volatile boolean running;

    @Override
    public void start() {
        running = true;
        // Start polling trigger.
    }

    @Override
    public void stop(Runnable callback) {
        running = false;
        // Cancel trigger and stop scheduling new polls.
        callback.run();
    }

    @Override
    public void stop() {
        running = false;
    }

    @Override
    public boolean isRunning() {
        return running;
    }

    @Override
    public int getPhase() {
        return 100;
    }

    @Override
    public boolean isAutoStartup() {
        return true;
    }
}
~~~

Ví dụ rút gọn. Trong implementation thật, callback chỉ gọi khi component đã hoàn tất stop, không gọi ngay nếu còn async work. Implement đầy đủ lifecycle methods theo interface/version. Tránh đóng cùng một resource ở nhiều callbacks không idempotent.

## 15. Logging, metrics và readiness trong lúc drain

Theo dõi shutdown requested timestamp/reason, readiness state, in-flight SOAP requests, requests mới bị reject, active/queued jobs, outbound calls, pool active/idle connections, temp files/bytes, phase duration, deadline exceeded, forced cancellation và uncertain outcomes.

Dùng labels có cardinality thấp. Không log SOAP body, tokens, private keys hoặc PII. Log request/correlation ID cùng phase và outcome để điều tra.

## 16. Kiểm thử graceful shutdown

### 16.1. Test cơ bản

1. Khởi động server trên random port.
2. Gửi SOAP request chậm và giữ bằng latch/barrier.
3. Đặt application thành quiescing hoặc kích hoạt shutdown.
4. Xác minh readiness DOWN và request mới bị rút khỏi routing/reject.
5. Cho request đang chạy hoàn tất trong deadline.
6. Xác minh response và transaction.
7. Xác minh executors/client pools được đóng.
8. Xác minh context/process kết thúc.

### 16.2. Test deadline exceeded

Tạo downstream call lâu hơn shutdown budget. Xác minh process không chờ vô hạn, request bị cancel/connection close theo policy, không trả success giả, uncertain outcome được ghi nhận, client có thể query/retry idempotently và metrics ghi timeout.

### 16.3. Test background worker và outbound pool

Giữ một job trong trạng thái processing rồi bắt đầu shutdown. Xác minh không claim job mới, job hoàn tất hoặc lease cho instance mới, không duplicate side effect. Với outbound client, giữ partner response đang chờ; shutdown chỉ đóng pool sau khi call drain hoặc cancel.

### 16.4. Test SIGTERM thật

Context close test không hoàn toàn giống process nhận SIGTERM trong container. Với release quan trọng, chạy process/container test, gửi SIGTERM, đo thời gian exit, readiness transition, việc ngừng accept calls mới, active request policy và xác minh process không bị SIGKILL quá sớm.

## 17. Runbook deployment và case study

### 17.1. Trước rolling deployment

1. Xác nhận replica mới Ready và đủ capacity.
2. Rút replica cũ khỏi routing trước terminate.
3. Kiểm termination grace period lớn hơn shutdown budget.
4. Theo dõi drain duration, in-flight requests và connection pools.
5. Theo dõi error/timeout/retry spike.
6. Xác nhận durable jobs/outbox tiếp tục ở replica mới.
7. Chỉ xem deployment hoàn tất khi old instance đã exit.

Khi rollback, không xóa jobs/outbox mà phiên bản cũ cần đọc; giữ idempotency records đủ lâu; reconcile uncertain outcomes; không xóa attachments thuộc active jobs.

### 17.2. Case study: mất response sau SubmitOrder commit

Trong rolling deployment, client gửi SubmitOrder. Instance cũ commit order vào database nhưng bị terminate trước khi SOAP response tới client. Client nhận connection reset và retry instance mới. Không có idempotency có thể tạo hai orders.

Nguyên nhân có thể là readiness không DOWN, drain window quá ngắn, grace period nhỏ hơn tổng phases, client không có request identity ổn định hoặc DB pool bị đóng quá sớm.

Khắc phục bằng readiness-first, graceful shutdown với deadline phù hợp, drain HTTP requests, giữ datasource mở đến hết in-flight transactions, lưu idempotency key/result trong transaction và cho client retry bằng cùng key. Thêm integration test gửi SIGTERM khi request đang chờ response.

Tiêu chí đóng: request mới không vào instance quiescing; request đã commit nhưng mất response không duplicate; in-flight operations hoàn tất trong budget hoặc được phân loại uncertain; workers/outbox resume; pools đóng sau drain; temp files không orphan ngoài cleanup policy.

## 18. Bài tập và checklist nghiệm thu

### 18.1. Bài tập

**Bài 1 — Readiness:** Khi shutdown bắt đầu, có nên fail liveness ngay?

**Đáp án:** Thông thường không. Readiness DOWN để rút traffic; liveness vẫn UP khi process đang drain bình thường.

**Bài 2 — Graceful property:** Bật server.shutdown=graceful có bảo đảm mọi async jobs hoàn tất?

**Đáp án:** Không. Embedded web server request handling và background executor có lifecycle riêng.

**Bài 3 — Response mất:** Client nhận connection reset có biết server đã commit chưa?

**Đáp án:** Không. Cần idempotency/status lookup và reconciliation.

**Bài 4 — Client pool:** Đóng pool ngay khi nhận SIGTERM?

**Đáp án:** Không nếu in-flight calls còn dùng pool. Quiesce, drain/cancel rồi đóng bởi owner.

**Bài 5 — Executor queue:** Queue vô hạn gây rủi ro gì?

**Đáp án:** Giữ task/request references, tăng heap và khiến shutdown kéo dài. Dùng bounded queue/durable jobs.

**Bài 6 — Timeout:** Downstream timeout lớn hơn platform grace period?

**Đáp án:** Request có thể bị kill trước timeout; đặt deadline trong shutdown budget.

**Bài 7 — Temporary file:** Async scanner đang đọc file, HTTP request kết thúc. Có xóa ngay?

**Đáp án:** Không. Chuyển ownership sang job lifecycle.

**Bài 8 — Database:** Đóng datasource trước HTTP drain?

**Đáp án:** Không. In-flight transactions có thể fail; đóng dependency sau consumers.

**Bài 9 — preStop:** Sleep cố định 30 giây luôn an toàn?

**Đáp án:** Không. Nó tiêu tốn grace period; cần đo readiness propagation và budget.

**Bài 10 — Background job:** Job đang leased khi instance chết?

**Đáp án:** Lease expiry/reclaim, checkpoint và idempotent processing cho phép instance mới tiếp tục.

**Bài 11 — Retry:** Có retry Sender/Client SOAP Fault?

**Đáp án:** Thông thường không tự retry vì thường là request/contract error; phân loại theo operation policy.

**Bài 12 — Shutdown test:** Đóng ApplicationContext có chứng minh SIGTERM container behavior?

**Đáp án:** Không hoàn toàn. Cần process/container test gửi SIGTERM và đo readiness, drain, exit.

### 18.2. Checklist admission và readiness
- [ ] Có trạng thái quiescing rõ ràng.
- [ ] Readiness DOWN trước khi server dừng.
- [ ] Liveness không fail chỉ vì đang drain.
- [ ] Ingress/load balancer có thời gian remove endpoint.
- [ ] Request mới trong quiescing bị reject theo contract.

### 18.3. Checklist HTTP/SOAP drain
- [ ] Graceful shutdown bật và kiểm đúng Spring Boot/container version.
- [ ] MessageDispatcherServlet và active exchanges được drain.
- [ ] Có in-flight request metrics.
- [ ] Upload/MTOM có abort và cleanup policy.
- [ ] DB/dependencies mở đến khi request consumers dừng.
- [ ] Shutdown deadline nằm trong platform grace period.

### 18.4. Checklist workers và clients
- [ ] Scheduler ngừng trigger trước worker shutdown.
- [ ] Executor queue bounded, await termination hữu hạn.
- [ ] Durable jobs/outbox có lease/recovery.
- [ ] Client gateways không nhận outbound calls mới.
- [ ] In-flight WebServiceTemplate calls drain/cancel.
- [ ] HTTP pool đóng bởi owner sau drain.
- [ ] Housekeeping threads được dừng.

### 18.5. Checklist consistency, tests và observability
- [ ] Write requests có idempotency key.
- [ ] Timeout/connection reset có trạng thái uncertain.
- [ ] Retry phân loại theo Fault/transport/business semantics.
- [ ] DB commit/outbox phối hợp nhất quán.
- [ ] Temporary files có ownership, retention và orphan cleanup.
- [ ] Test readiness, in-flight completion, deadline và cancellation.
- [ ] Test background worker lease/resume và outbound pool drain.
- [ ] Có actual SIGTERM process/container test.
- [ ] Metrics có drain duration, in-flight, forced stop và uncertain outcomes.
- [ ] Logs không chứa SOAP secrets/PII; runbook deployment/rollback đã xác minh.

**Ghi nhớ:** Tắt có trật tự là một giao thức lifecycle giữa ứng dụng, HTTP server, background workers, outbound clients, storage và platform. Hãy rút instance khỏi traffic bằng readiness trước, drain request đã accept trong deadline hữu hạn, dừng producers trước workers, đóng connection pools sau in-flight calls và giữ database/storage đủ lâu để hoàn tất giao dịch. Với request có kết quả không chắc chắn, idempotency và reconciliation bảo vệ dữ liệu; một kết nối đóng không chứng minh operation chưa commit.
