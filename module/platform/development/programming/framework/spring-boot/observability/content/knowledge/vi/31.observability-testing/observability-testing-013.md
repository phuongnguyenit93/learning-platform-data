# Test lỗi mà không làm mất telemetry

Trong chương **Testing observability** của mô-đun **SPRING_BOOT_OBSERVABILITY**, test lỗi mà không làm mất telemetry là nhóm kiểm thử xác minh ứng dụng vẫn ghi nhận được metrics, logs và traces khi operation thất bại. Một exception không chỉ là kết quả nghiệp vụ; nó còn là tình huống cần quan sát rõ nhất để đội vận hành xác định lỗi xảy ra ở đâu, ảnh hưởng bao nhiêu request và dependency nào liên quan.

Telemetry có thể bị mất nếu Observation không được đóng đúng lifecycle, exception bị catch rồi không được ghi nhận, context bị mất khi chuyển thread, exporter không flush trước shutdown hoặc chính instrumentation ném lỗi làm che exception gốc. Vì vậy, test cần kích hoạt cả success và failure paths, kiểm tra từng signal và xác minh error telemetry vẫn được export ngay cả khi application operation thất bại.

Bài này tập trung vào cách kiểm thử error recording trong Micrometer Observation/Tracing, metrics và structured logs; cách bảo toàn context trong async execution; xử lý exporter failures; dùng test exporters/in-memory registries; và tạo fault-injection tests có thể tái lập.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:
1. Giải thích telemetry cần được ghi nhận thế nào khi operation ném exception.
2. Phân biệt exception propagation, error recording và business outcome.
3. Kiểm thử Observation lifecycle và handlers khi success/failure.
4. Xác minh span status, exception event và parent-child relationship.
5. Xác minh metrics count, duration và bounded error classification.
6. Kiểm tra logs có error type và trace correlation nhưng không lộ dữ liệu nhạy cảm.
7. Bảo đảm context propagation qua executor/async boundaries.
8. Phát hiện exporter failure, queue overflow và flush/shutdown loss.
9. Dùng in-memory test exporters và fault injection để tái lập lỗi.
10. Thiết lập regression tests bảo đảm lỗi ứng dụng không làm mất telemetry.

## 2. Vì sao telemetry dễ mất trên error path?

Một happy-path test thường chỉ xác minh operation trả về kết quả và một meter/span được tạo. Error path có thêm nhiều nhánh:
- Exception thoát khỏi method hoặc bị catch/translate.
- Observation có thể được stop trước hoặc sau khi error được ghi nhận.
- Error handler có thể trả fallback khiến instrumentation nghĩ operation thành công.
- Async callback có thể chạy ngoài current Observation scope.
- Logging có thể ghi exception nhưng thiếu trace/span correlation.
- Span có thể được tạo nhưng status vẫn UNSET nếu exception không được record.
- Exporter có thể drop data do queue đầy, endpoint lỗi hoặc process shutdown quá sớm.
- Instrumentation code có thể ném exception và che lỗi gốc.

~~~mermaid
flowchart TD
    Start["Start operation"]
    Start --> Obs["Start Observation / span"]
    Obs --> Work["Execute business work"]
    Work -->|success| Success["Record success and stop"]
    Work -->|exception| Error["Record exception and error outcome"]
    Error --> Stop["Stop Observation / span"]
    Success --> Export["Export telemetry"]
    Stop --> Export
    Export --> Verify["Verify metrics, logs and trace"]
~~~

Mục tiêu kiểm thử là xác minh cả hai nhánh đều kết thúc lifecycle và dữ liệu được chuyển tới các sinks cần thiết.

## 3. Phân biệt exception, error và outcome

Không phải mọi exception đều có nghĩa business operation thất bại, và không phải mọi business failure đều được biểu diễn bằng exception.

| Khái niệm | Ví dụ | Điều cần kiểm thử |
| --- | --- | --- |
| Exception | SQLException, TimeoutException | Exception type được ghi nhận và propagation đúng. |
| Span error | Span status ERROR hoặc exception event | Tracing handler áp dụng error semantics. |
| Metric outcome | success, failure, rejected | Tag thuộc tập hữu hạn và đúng nghiệp vụ. |
| HTTP result | 400, 404, 500 | Status/outcome phản ánh contract của request. |
| Business rejection | Insufficient balance | Có thể là kết quả hợp lệ, không nhất thiết là exception. |

Một method có thể catch exception và trả fallback. Khi đó, Observation callback thấy method hoàn tất bình thường. Nếu operation vẫn cần được phân loại là degraded/failure, code phải ghi outcome tường minh. Ngược lại, không đánh dấu mọi exception là ERROR nếu đó là kết quả nghiệp vụ được dự kiến và xử lý bình thường.

## 4. Observation lifecycle phải được đóng đúng

Với Micrometer Observation, nên dùng `observe(...)` khi có thể để API quản lý start/stop và error handling quanh callback.

~~~java
Observation.createNotStarted("payment.authorize", registry)
        .lowCardinalityKeyValue("operation", "authorize")
        .observe(() -> paymentService.authorize(command));
~~~

Nếu callback ném exception, Observation lifecycle kết thúc theo API/handler semantics và exception tiếp tục được truyền tới caller. Test cần xác minh Observation được tạo, error được record theo handler/convention, stop được gọi đúng một lần, exception gốc vẫn tới caller và current Observation/trace scope được khôi phục sau callback.

Nếu tự quản lý lifecycle bằng start/stop, dùng try/finally:

~~~java
Observation observation =
        Observation.start("inventory.reconcile", registry);
try {
    reconciler.reconcile();
} catch (RuntimeException error) {
    observation.error(error);
    throw error;
} finally {
    observation.stop();
}
~~~

Không gọi stop trước khi record error. Không swallow exception chỉ để tránh test fail. Nếu error đã được catch và chuyển thành fallback, hãy ghi nhận business outcome phù hợp trước khi kết thúc Observation.

## 5. Unit test Observation error recording

Có thể dùng ObservationRegistry với test handler để quan sát lifecycle mà không cần backend bên ngoài. Ví dụ một handler đơn giản ghi nhận callbacks:

~~~java
class RecordingObservationHandler
        implements ObservationHandler<Observation.Context> {

    final List<String> events = new ArrayList<>();
    Throwable recordedError;

    @Override
    public boolean supportsContext(Observation.Context context) {
        return true;
    }

    @Override
    public void onStart(Observation.Context context) {
        events.add("start");
    }

    @Override
    public void onError(Observation.Context context) {
        events.add("error");
        recordedError = context.getError();
    }

    @Override
    public void onStop(Observation.Context context) {
        events.add("stop");
    }
}
~~~

Ví dụ test:

~~~java
@Test
void recordsErrorAndStopsObservation() {
    ObservationRegistry registry = ObservationRegistry.create();
    RecordingObservationHandler handler =
            new RecordingObservationHandler();
    registry.observationConfig().observationHandler(handler);

    RuntimeException failure = new IllegalStateException("simulated failure");

    assertThatThrownBy(() ->
            Observation.createNotStarted("job.execute", registry)
                    .observe(() -> { throw failure; }))
            .isSameAs(failure);

    assertThat(handler.events).contains("start", "error", "stop");
    assertThat(handler.recordedError).isSameAs(failure);
}
~~~

Đây là skeleton minh họa; thứ tự callback và handler APIs cần xác minh theo Micrometer version do Spring Boot quản lý. Trong test thực tế, assert lifecycle contract thay vì phụ thuộc thứ tự tuyệt đối giữa nhiều handlers nếu API không cam kết thứ tự đó.

## 6. Kiểm thử span status và exception event

Khi Micrometer Tracing bridge được cấu hình, Observation có thể tạo span. Test cần dùng tracer/test exporter tương thích để xác minh:
- Span được tạo cho operation.
- Span kết thúc dù callback thất bại.
- Error status được đặt theo convention.
- Exception event hoặc error attributes được ghi nếu bridge hỗ trợ.
- Trace ID/span ID có giá trị hợp lệ.
- Parent span được giữ khi operation là child của request.
- Không tạo duplicate spans do hai instrumentation layers.

Không assert tên attribute hoặc event fields theo phỏng đoán. Micrometer Tracing bridge, OpenTelemetry/Brave và semantic conventions có thể khác nhau. Kiểm tra contract và payload theo version thực tế.

~~~java
assertThat(exportedSpan.getName()).isEqualTo("payment.authorize");
assertThat(exportedSpan.getStatus()).isEqualTo(StatusCode.ERROR);
assertThat(exportedSpan.getEvents())
        .extracting(EventData::getName)
        .contains("exception");
~~~

Đoạn trên phụ thuộc loại exporter và span model được sử dụng. Nếu dùng Brave, API đọc span khác OpenTelemetry SDK. Đặt adapter test nhỏ để test suite không phụ thuộc implementation ở mọi test.

## 7. Metrics vẫn phải ghi nhận khi operation thất bại

Timer thường ghi nhận duration/count khi Observation dừng, kể cả callback kết thúc bằng exception nếu handler được cấu hình đúng. Counter error có thể bổ sung số lần thất bại với outcome/error category có tập giá trị hữu hạn.

~~~java
@Test
void timerRecordsFailedInvocation() {
    SimpleMeterRegistry meters = new SimpleMeterRegistry();
    ObservationRegistry observations = ObservationRegistry.create();
    observations.observationConfig()
            .observationHandler(new DefaultMeterObservationHandler(meters));

    assertThatThrownBy(() ->
            Observation.createNotStarted("catalog.lookup", observations)
                    .lowCardinalityKeyValue("operation", "lookup")
                    .observe(() -> {
                        throw new IllegalArgumentException("not found");
                    }))
            .isInstanceOf(IllegalArgumentException.class);

    Timer timer = meters.find("catalog.lookup").timer();
    assertThat(timer).isNotNull();
    assertThat(timer.count()).isEqualTo(1);
}
~~~

Đây là ví dụ khái niệm; meter name và handler constructor phụ thuộc Micrometer version. Kiểm tra meter thật qua registry thay vì hard-code assumptions về naming convention.

Không đưa exception message vào metric tag. Dùng error.type hoặc outcome với tập giá trị bounded như timeout, validation, dependency, unexpected. Nếu exception type có nhiều subclasses/generated classes, map về taxonomy hữu hạn.

## 8. Structured logs và trace correlation trên error path

Error logs cần có đủ thông tin điều tra nhưng không chứa secrets/PII. Các fields hữu ích: event.name hoặc operation, error.type/category, service và route/task identity ổn định, trace_id/span_id khi context có mặt, retry attempt nếu số lần thử có giới hạn, outcome và duration.

~~~java
try {
    inventoryService.reserve(command);
} catch (RuntimeException error) {
    log.atError()
            .addKeyValue("event.name", "inventory.reserve.failed")
            .addKeyValue("error.type", error.getClass().getSimpleName())
            .addKeyValue("outcome", "failure")
            .log("Inventory reservation failed", error);
    throw error;
}
~~~

Logging framework/encoder có thể tự đưa exception stack trace và MDC fields vào output. Test nên xác minh trace correlation được giữ và message/stack không chứa token, password hoặc payload nhạy cảm. Không log toàn bộ request/response body khi failure.

## 9. Async execution và context propagation

Một lỗi phổ biến là Observation bắt đầu trên thread A nhưng callback thất bại trên thread B. Nếu context không được propagate, child span và log có thể mất trace ID hoặc trở thành root trace không liên quan.

~~~mermaid
sequenceDiagram
    participant A as Request thread
    participant E as Executor thread
    participant T as Trace backend
    A->>A: Start parent Observation
    A->>E: Submit task with context
    E->>E: Start child Observation
    E->>E: Operation throws exception
    E->>T: Export child error span
    A->>A: Complete parent request
~~~

Kiểm thử cần:
1. Tạo parent Observation/trace.
2. Submit công việc qua executor đã cấu hình context propagation.
3. Ném exception trong worker thread.
4. Xác minh child span có cùng trace ID và parent span ID đúng.
5. Xác minh exception được record dù callback ở thread khác.
6. Xác minh context được restore/clear sau khi task hoàn tất, tránh leak sang task tiếp theo.

Spring/Micrometer context propagation có thể dùng TaskDecorator hoặc integration phù hợp với stack/version. Không giả định MDC copy thủ công cũng đồng nghĩa toàn bộ Observation/Tracing context được truyền.

## 10. Kiểm thử lỗi ở HTTP server/client và database boundaries

Một service request có thể thất bại tại nhiều lớp:
- HTTP server: controller ném exception và trả 5xx.
- HTTP client: timeout, connection refused hoặc downstream 5xx.
- JDBC: SQLException, pool acquisition timeout hoặc transaction rollback.
- Messaging: publish/consume failure, nack hoặc retry.
- Scheduled task: task exception không có HTTP request parent.

Với mỗi boundary, test cần xác minh parent/child span relationship đúng, error được ghi ở span phù hợp, HTTP status/outcome hoặc operation outcome đúng, Timer/count vẫn được ghi nhận, log có correlation ID khi context tồn tại, không ghi raw payload/credentials và retry tạo telemetry theo policy mà không duplicate instrumentation.

Đừng chỉ kiểm tra controller trả status 500. Cần kiểm tra telemetry của dependency call đã thất bại để phân biệt lỗi local với downstream.

## 11. Exporter failure và telemetry delivery

Một operation có thể tạo span/meter/log trong process nhưng dữ liệu không đến backend. Nguyên nhân gồm Collector/backend unavailable, export queue đầy, network timeout hoặc TLS/authentication failure, shutdown trước flush, exporter timeout quá ngắn, sampling loại trace trước export hoặc logging appender async chưa drain queue.

Test exporter failure nên phân biệt **recorded in-process** với **delivered to backend**. Không để exporter exception làm che exception nghiệp vụ hoặc khiến request chính thất bại, trừ khi ứng dụng có yêu cầu rõ ràng về synchronous audit delivery.

Kiểm tra các chỉ số exporter/SDK như queue size, dropped spans, export failures và batch timeout nếu implementation expose. Tên metrics phụ thuộc SDK/exporter version.

## 12. Flush và shutdown không làm mất telemetry

Trong integration test dùng process/context thật, xác minh:
- Observation đã stop trước khi exporter đóng.
- Batch span processor flush được trước process exit.
- Logging appender được drain/flush.
- Shutdown timeout đủ cho flush trong giới hạn.
- Exporter close/flush không được gọi nhiều lần theo cách gây lỗi.
- Lỗi flush được báo qua diagnostics phù hợp nhưng không che shutdown cause gốc.

Có thể gọi forceFlush trong test exporter/SDK khi API hỗ trợ để làm test deterministic. Không dùng sleep tùy tiện để chờ exporter; chờ completion signal hoặc flush future với timeout có giới hạn.

## 13. Fault injection và test matrix

Tạo lỗi có kiểm soát, không phụ thuộc outage bên ngoài:
- Throw exception trực tiếp.
- Mock HTTP client timeout/5xx.
- Mock repository ném DataAccessException.
- Từ chối publish message.
- Executor task fail sau khi context được truyền.
- Exporter test double ném lỗi hoặc trả timeout.
- Làm queue test đầy để kiểm tra drop policy.
- Trigger shutdown ngay sau khi tạo telemetry để kiểm tra flush.

| Kịch bản | Assertion chính |
| --- | --- |
| Business method throws | Exception propagate, Observation stop và error được record. |
| Exception caught/fallback | Outcome được ghi tường minh theo business semantics. |
| HTTP downstream timeout | Client span/error và parent trace được giữ. |
| JDBC exception | Database span và request timer được ghi nhận. |
| Async task failure | Trace context/parent relationship không mất. |
| Exporter unavailable | Business error không bị che; exporter failure được quan sát. |
| Shutdown during export | Flush/close có deadline và dropped telemetry được phát hiện. |

## 14. Kiểm thử bằng test exporter/in-memory registry

Dùng in-memory exporter để kiểm tra spans mà không cần backend ngoài. Với OpenTelemetry SDK, dùng exporter/testing utilities phù hợp version; với Micrometer Tracing, chọn bridge và test facilities tương ứng. Với metrics, SimpleMeterRegistry giúp xác minh timer/counter; với logs, dùng appender test hoặc captured output.

Một test harness tốt nên:
- Tạo registry/tracer mới cho mỗi test.
- Đăng ký đúng Observation handlers.
- Không chia sẻ exporter mutable giữa tests chạy song song.
- Flush exporter trước khi đọc exported spans.
- Reset meter/log state sau mỗi test.
- Có timeout để test không treo.
- Không dùng backend production hoặc credentials thật.

Không trộn Brave và OpenTelemetry bridge trong cùng test context chỉ để lấy API tiện hơn. Test cùng stack với ứng dụng thực.

## 15. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Exception tới caller nhưng không có span | Observation không được tạo hoặc tracing handler thiếu. | Kiểm tra ObservationRegistry/bridge. |
| Có span nhưng status không ERROR | Exception bị catch hoặc error recording convention không áp dụng. | Kiểm tra catch/fallback và error API. |
| Có log lỗi nhưng thiếu trace ID | Context không active hoặc MDC propagation thiếu. | Kiểm tra scope và executor decorator. |
| Timer không tăng khi lỗi | Observation handler không stop hoặc meter filter loại bỏ. | Kiểm tra lifecycle và registry. |
| Child span thành trace root | Context không propagate qua thread boundary. | Kiểm tra TaskDecorator/context propagation. |
| Exporter không nhận span | Sampling, queue drop, endpoint/network/auth lỗi. | Kiểm tra sampler, exporter diagnostics và Collector. |
| Test không thấy span ngay | Batch exporter chưa flush. | Gọi forceFlush hoặc chờ completion có timeout. |
| Exporter exception che lỗi gốc | Custom handler/export call ném exception đồng bộ. | Cô lập exporter failure và giữ business exception. |
| Error tags tăng cardinality | Exception message/class động được dùng làm tag. | Map sang error category bounded. |
| Telemetry mất khi shutdown | Processor/appender chưa flush trước process exit. | Kiểm tra lifecycle order và shutdown timeout. |

## 16. Runbook khi error telemetry bị mất

1. Xác định operation và error path bị ảnh hưởng.
2. Kiểm tra exception có thoát khỏi callback hay bị catch/translate.
3. Xác minh Observation được start, error-record và stop.
4. Kiểm tra tracing bridge và Observation handlers.
5. Tìm span trong process/test exporter trước khi kiểm tra backend.
6. Kiểm tra sampling decision và parent context.
7. Nếu async, kiểm tra trace ID/parent span qua executor boundary.
8. Kiểm tra Timer/counter và meter filters.
9. Kiểm tra structured logs, MDC và masking policy.
10. Kiểm tra exporter queue, drop counters, network và Collector receiver.
11. Kiểm tra forceFlush/shutdown ordering và timeout.
12. Thêm fault-injection regression test cho nguyên nhân đã xác định.

## 17. Bài tập tự kiểm tra

### Bài 1 — Observation không stop

Một method ném exception và code tự gọi start() nhưng không có finally. Rủi ro là gì?

**Đáp án:** Observation có thể không stop, khiến scope/lifecycle không được dọn và Timer/span không hoàn tất/export. Dùng observe() hoặc try/finally với error recording.

### Bài 2 — Exception bị catch

Service catch exception, trả fallback và test không thấy span ERROR. Vì sao?

**Đáp án:** Callback kết thúc bình thường nên handler không thấy exception thoát ra. Nếu business outcome là degraded/failure, ghi error/outcome tường minh.

### Bài 3 — Async context

Request submit task vào executor; worker ném lỗi nhưng log thiếu trace ID. Cần kiểm tra gì?

**Đáp án:** Context propagation qua executor, TaskDecorator hoặc Micrometer context mechanism và MDC correlation.

### Bài 4 — Span đã tạo nhưng backend không thấy

Test exporter có span nhưng trace backend không có. Có thể lỗi ở đâu?

**Đáp án:** Exporter/Collector network, auth/TLS, queue/drop, sampling hoặc backend ingestion. Phân biệt record trong process với delivery tới backend.

### Bài 5 — Exporter failure

Collector unavailable khiến exporter ném exception. Có nên làm request nghiệp vụ thất bại theo không?

**Đáp án:** Thông thường không; telemetry delivery nên được cô lập khỏi business path. Ngoại lệ là audit delivery có yêu cầu đồng bộ rõ ràng. Ghi nhận exporter failure riêng.

### Bài 6 — Shutdown flush

Ứng dụng đóng ngay sau khi task fail, span không tới backend. Cần xác minh gì?

**Đáp án:** Observation stop, batch processor forceFlush/close, logging queue drain và shutdown timeout. Dùng completion signal thay sleep trong test.

## 18. Checklist triển khai

- [ ] Error paths tạo và stop Observation đúng lifecycle.
- [ ] Exception gốc được propagate hoặc business outcome được ghi tường minh.
- [ ] Span status/error event được kiểm tra theo tracer bridge thực tế.
- [ ] Timer/count vẫn được ghi nhận khi operation thất bại.
- [ ] Error type/outcome dùng tập giá trị bounded.
- [ ] Logs có trace/span correlation khi context tồn tại.
- [ ] Logs/traces không chứa secrets, PII hoặc raw payload ngoài policy.
- [ ] Async executor truyền context và restore sau khi task hoàn tất.
- [ ] HTTP/JDBC/messaging/scheduled boundaries có fault tests phù hợp.
- [ ] Exporter failures/drop/queue saturation có diagnostics.
- [ ] Telemetry failure không che exception nghiệp vụ.
- [ ] Test exporter/in-memory registry được cô lập giữa tests.
- [ ] Batch exporter và logging appenders được flush trước shutdown.
- [ ] Tests dùng completion/flush signal thay sleep tùy tiện.
- [ ] CI có fault-injection regression cases.
- [ ] Production theo dõi dropped telemetry và exporter failures.

**Ghi nhớ:** Error path phải kết thúc Observation đúng lifecycle, ghi nhận exception/outcome, giữ trace context và xuất metrics/logs/traces trong giới hạn delivery policy. Kiểm thử riêng việc record trong process và việc export tới backend; fault injection cho HTTP/JDBC/async/exporter/shutdown giúp phát hiện telemetry loss trước production. Giữ error tags bounded và không để lỗi telemetry che lỗi nghiệp vụ gốc.
