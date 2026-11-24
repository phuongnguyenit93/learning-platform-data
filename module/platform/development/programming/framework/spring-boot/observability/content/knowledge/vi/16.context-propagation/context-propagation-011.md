# Kiểm thử context propagation trong Spring Boot

Một request Spring Boot có trace context hợp lệ, nhưng khi service chuyển công việc sang executor hoặc gọi HTTP downstream, span phía sau lại mang trace ID mới. Log của worker có thể không có trace ID, hoặc tệ hơn, task tiếp theo trên cùng thread pool lại mang trace ID của task trước.

Những lỗi này thường không làm unit test nghiệp vụ thất bại. Chúng xuất hiện ở **ranh giới thực thi**: thread khác, thread pool tái sử dụng, HTTP client/server, message consumer hoặc scheduler Reactor. Vì vậy, cần kiểm thử context propagation độc lập để chứng minh context được capture, truyền, khôi phục và dọn đúng nơi.

Bài học thuộc chương **Context propagation** của module **SPRING_BOOT_OBSERVABILITY**. Module hướng dẫn thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing; học propagation ngữ cảnh, tag/cardinality, exporter, sampling và liên kết tín hiệu để điều tra lỗi, độ trễ và hành vi ứng dụng trên môi trường thực. Bài này tập trung vào chiến lược kiểm thử unit, integration và end-to-end cho context propagation.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Xác định boundary cần kiểm thử: thread, executor, HTTP, messaging và Reactor.
2. Phân biệt kiểm thử current context, quan hệ parent-child, trace header, log correlation và export.
3. Dùng TestObservationRegistry để kiểm tra vòng đời observation.
4. Kiểm thử executor để chứng minh context được capture/restore và không rò sang task kế tiếp.
5. Kiểm tra HTTP client inject và server extract trace context bằng B3 hoặc W3C.
6. Kiểm thử CompletableFuture, @Async và Reactor theo thời điểm callback/subscription thực thi.
7. Thiết kế test cho success, exception, cancellation, rejection, timeout và thread reuse.
8. Tách lỗi propagation khỏi sampling, reporter, exporter, collector và backend.
9. Viết assertion ổn định, không phụ thuộc trace ID ngẫu nhiên.
10. Kết hợp metrics, logs và traces để phát hiện context leakage và cardinality regressions.

## 1. Kiểm thử propagation cần chứng minh điều gì?

Một test chỉ xác nhận tác vụ hoàn tất hoặc HTTP response là 200 **chưa chứng minh context đã được truyền**. Trước khi viết test, xác định các invariant cần giữ tại mỗi ranh giới:

- **Trước khi submit:** request thread có current trace/span mong đợi.
- **Khi worker bắt đầu:** worker nhìn thấy context của đúng lần submit.
- **Trong task:** span mới có trace ID mong đợi và parent relationship phù hợp.
- **Sau task:** scope được đóng; worker không giữ context đã dùng.
- **Outbound HTTP:** client inject đúng header format.
- **Downstream:** server extract được context và tạo span liên kết.
- **Logs:** trace ID/span ID tại thời điểm ghi log phản ánh scope hiện hành.
- **Export:** span được gửi khi sampler và exporter được cấu hình để giữ dữ liệu.

```text
Request thread: trace T / span A
       |
       +-- submit executor task
       |      worker restores context A
       |      task span B belongs to trace T
       |
       +-- HTTP client call
              outbound header identifies T / span B
                       |
                       v
                downstream server
                  extracts T / parent B
                  creates span C
```

Không phải test nào cũng cần kiểm tra mọi invariant. Unit test tập trung một ranh giới; integration test xác minh Spring wiring; end-to-end test xác minh trace qua nhiều process.

### 1.1. Phân biệt propagation với export

Propagation đưa **trace context** sang execution boundary để span kế tiếp có thể nối đúng. Export chuyển span đã kết thúc tới collector/backend.

| Quan sát | Có thể là lỗi propagation? | Có thể là lỗi export? |
|---|---:|---:|
| Worker không có current trace context | Có | Không nhất thiết |
| Downstream tạo trace ID mới | Có | Không nhất thiết |
| Log có trace ID nhưng Zipkin không có span | Không nhất thiết | Có |
| Span có parent đúng trong test nhưng không lên backend | Không | Có |
| Task B mang trace ID task A trên cùng worker | Có, thường là cleanup/restore lỗi | Không nhất thiết |

Đừng sửa sampling hoặc Zipkin endpoint khi context ở worker đã sai. Ngược lại, đừng thay TaskDecorator khi context đúng nhưng reporter không gửi span.

## 2. Chọn tầng kiểm thử phù hợp

| Tầng test | Mục tiêu | Công cụ thường dùng | Không nên phụ thuộc |
|---|---|---|---|
| Unit test | Capture/restore, scope cleanup, logic tạo observation | JUnit, executor đơn luồng, Micrometer Context Propagation | Network/backend |
| Observation test | Lifecycle và handlers quan sát event/error | TestObservationRegistry, assertion hỗ trợ Micrometer | Zipkin UI |
| Spring integration | Bean wiring, TaskDecorator, auto-configuration, client instrumentation | SpringBootTest, TestConfiguration, MockMvc | Backend công khai |
| HTTP boundary | Inject/extract headers và trace ID continuity | Mock HTTP server, WireMock hoặc MockWebServer | Việc export đã lưu |
| Async/reactive | Context tại callback/signal | CompletableFuture, executor kiểm soát, Reactor StepVerifier | Giả định callback ở thread gọi |
| End-to-end | Trace xuyên nhiều service và pipeline | Testcontainers hoặc môi trường tích hợp | ID cố định hoặc thứ tự spans tuyệt đối |

Test tầng thấp thường nhanh và ổn định hơn; test tầng cao xác minh wiring thực tế nhưng cần quản lý môi trường.

## 3. Kiểm thử observation lifecycle

Micrometer cung cấp test support cho Observation, thường qua artifact micrometer-observation-test. TestObservationRegistry ghi nhận observations và sự kiện lifecycle để assertion trong unit test. Phiên bản dependency phải tương thích với BOM Spring Boot/Micrometer của dự án.

```groovy
dependencies {
    testImplementation 'io.micrometer:micrometer-observation-test'
}
```

Ví dụ tạo registry test riêng:

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.tck.TestObservationRegistry;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class PaymentObservationTest {

    @Test
    void recordsObservationAroundOperation() {
        TestObservationRegistry registry =
                TestObservationRegistry.create();

        String result = Observation.createNotStarted(
                        "payment.authorize", registry)
                .contextualName("authorize payment")
                .observe(() -> "approved");

        assertEquals("approved", result);
        // Dùng assertion API/TestObservationRegistryAssert
        // của Micrometer version để kiểm tra lifecycle, name và tags.
    }
}
```

Assertion kết quả callback chỉ chứng minh code nghiệp vụ chạy. Trong test thật, hãy dùng assertion API của phiên bản Micrometer hoặc test handler để kiểm tra start/stop/error và context. TestObservationRegistry không tự mô phỏng Brave/OpenTelemetry tracer đầy đủ; muốn kiểm tra trace ID/span ID cần tracer test hoặc kiểm tra boundary thực tế.

### 3.1. Kiểm tra nhánh lỗi

```java
@Test
void operationFailureIsPropagated() {
    TestObservationRegistry registry =
            TestObservationRegistry.create();

    IllegalStateException thrown = assertThrows(
            IllegalStateException.class,
            () -> Observation.createNotStarted(
                            "payment.authorize", registry)
                    .observe(() -> {
                        throw new IllegalStateException("boom");
                    }));

    assertEquals("boom", thrown.getMessage());
    // Thêm assertion theo Micrometer version để xác nhận
    // observation stop và error context đã được ghi.
}
```

Mục tiêu là xác nhận exception được truyền đúng và lifecycle được kết thúc. Không kết luận backend đã nhận span từ test này.

## 4. Kiểm thử capture/restore bằng executor đơn luồng

Single-thread executor hữu ích vì cùng một worker thực hiện task A, task B và task C. Kịch bản:

- Task A được submit khi context A hiện hành.
- Task B được submit khi context B hiện hành.
- Task C được submit khi không có context.
- A thấy A, B thấy B, C thấy null.
- Không task nào nhìn thấy context của task trước.

### 4.1. Dùng ContextSnapshot

Micrometer Context Propagation cung cấp ContextSnapshot để capture/restore những context có accessor tương ứng đã đăng ký.

```java
import io.micrometer.context.ContextSnapshot;
import io.micrometer.context.ContextSnapshotFactory;

import java.util.concurrent.Executor;

final class ContextAwareSubmitter {
    private final Executor delegate;
    private final ContextSnapshotFactory factory;

    ContextAwareSubmitter(
            Executor delegate, ContextSnapshotFactory factory) {
        this.delegate = delegate;
        this.factory = factory;
    }

    void execute(Runnable task) {
        ContextSnapshot snapshot = factory.captureAll();
        delegate.execute(snapshot.wrap(task));
    }
}
```

Mỗi lần submit capture context hiện tại. snapshot.wrap(task) phục hồi context trong scope khi worker chạy và đóng scope sau callback. API builder và accessor registration cần đối chiếu version Micrometer thực tế.

### 4.2. Mẫu test thread reuse

```java
@Test
void doesNotLeakContextBetweenTasks() throws Exception {
    ExecutorService worker = Executors.newSingleThreadExecutor();
    try {
        // Pseudocode: submitUnderTrace phải submit ngay khi span/scope
        // nguồn còn active; currentTraceId đọc từ tracer thật.
        Future<String> a = submitUnderTrace(
                "trace-A", worker, this::currentTraceId);
        Future<String> b = submitUnderTrace(
                "trace-B", worker, this::currentTraceId);
        Future<String> c = submitWithoutTrace(
                worker, this::currentTraceId);

        assertEquals("trace-A", a.get(2, TimeUnit.SECONDS));
        assertEquals("trace-B", b.get(2, TimeUnit.SECONDS));
        assertNull(c.get(2, TimeUnit.SECONDS));
    } finally {
        worker.shutdownNow();
    }
}
```

Đây là pseudocode: helper phải mở span/scope trên thread test, submit trong lúc context còn active, sau đó đóng scope nguồn. Không dùng một ThreadLocal tự tạo không liên quan tracer rồi coi nó chứng minh trace propagation.

Dùng Future.get với timeout hữu hạn hoặc CountDownLatch để đồng bộ. Không dùng Thread.sleep làm điều kiện đoán callback đã chạy. Luôn shutdown executor trong finally.

## 5. Kiểm thử Spring ContextPropagatingTaskDecorator

Spring Framework 6.1+ có ContextPropagatingTaskDecorator để tích hợp Micrometer Context Propagation. Tính khả dụng phụ thuộc phiên bản Spring Framework đi kèm Spring Boot.

```java
@Configuration(proxyBeanMethods = false)
class AsyncConfiguration {

    @Bean
    ThreadPoolTaskExecutor applicationTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(1);
        executor.setMaxPoolSize(1);
        executor.setQueueCapacity(20);
        executor.setThreadNamePrefix("app-worker-");
        executor.setTaskDecorator(
                new ContextPropagatingTaskDecorator());
        executor.initialize();
        return executor;
    }
}
```

Kiểm thử cần xác nhận:

- Bean executor đúng tên/qualifier được ứng dụng inject.
- TaskDecorator được gắn trước khi executor nhận task.
- Code dùng @Async("applicationTaskExecutor") thực sự qua Spring proxy.
- Không có nhánh code bypass bằng raw Executor hoặc new Thread.
- Task kế tiếp trên cùng worker không nhìn thấy context của task lỗi.
- Spring context shutdown không để worker chạy ngoài dự kiến.

**Không chỉ assert bean tồn tại.** Service có thể dùng executor khác; @Async có thể chọn executor mặc định. Integration test nên inject service từ ApplicationContext và chạy đúng đường gọi thật.

TaskDecorator khôi phục context; nó không tự quyết định span cần đo. Nếu muốn đo thời gian gửi receipt, tạo observation bên trong callback worker để lifecycle bao quanh công việc thật. Nếu task sống lâu hơn request, cân nhắc trace/consumer độc lập có span link thay vì giữ parent request scope mở nhiều phút.

## 6. Kiểm thử HTTP propagation

HTTP propagation có hai phần: client inject context vào request headers và server extract headers để tạo span liên kết. HTTP status 200 không chứng minh hai phần này hoạt động.

### 6.1. W3C và B3

W3C Trace Context:

```http
traceparent: 00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01
tracestate: vendor=value
```

B3 multi-header:

```http
X-B3-TraceId: 0af7651916cd43dd8448eb211c80319c
X-B3-SpanId: b7ad6b7169203331
X-B3-Sampled: 1
```

Ứng dụng có thể dùng W3C, B3 single hoặc B3 multi tùy bridge/propagator. Test phải xác minh đúng format production đang cấu hình.

### 6.2. Test outbound bằng mock HTTP server

Một mock server như MockWebServer hoặc WireMock có thể nhận request và cho test đọc headers:

```java
// Pseudocode: mock server đã start trên cổng động.
server.enqueue(new MockResponse()
        .setResponseCode(200)
        .setBody("approved"));

withActiveSpan("parent-span", () -> paymentClient.authorize());

RecordedRequest request =
        server.takeRequest(2, TimeUnit.SECONDS);
assertNotNull(request);

// W3C: parse traceparent.
// B3: đọc X-B3-TraceId và X-B3-SpanId.
// So sánh trace ID với context test đã tạo;
// không hard-code ID ngẫu nhiên.
```

Assertion nên kiểm tra header đúng format, trace ID đúng nguồn, span ID outbound thích hợp, sampling flag đúng test policy và không có secret/baggage ngoài allowlist.

### 6.3. Test server extraction

Gửi request inbound với traceparent hoặc B3 header đã biết, để Spring server instrumentation tạo server span, rồi kiểm tra:

- Server span có trace ID bằng ID inbound.
- Span ID mới khác parent ID inbound.
- Parent relationship đúng theo instrumentation.
- Request không có header được xử lý theo chính sách root trace.
- Header lỗi/không hợp lệ không được tin cậy ngoài trust policy.

MockMvc trong cùng process không mô phỏng đầy đủ network/proxy. Muốn test hai ứng dụng, dùng server/client thật hoặc mock HTTP server ở boundary.

## 7. Kiểm thử @Async và CompletableFuture

Method @Async thường hoạt động qua Spring proxy. Gọi method nội bộ từ cùng object có thể bỏ qua proxy.

```java
@Service
class ReceiptService {
    @Async("applicationTaskExecutor")
    public CompletableFuture<String> sendReceipt() {
        return CompletableFuture.completedFuture(
                currentTraceIdOrNull());
    }
}
```

Test phải inject ReceiptService từ Spring context, gọi qua bean được inject, chờ bằng get(timeout, unit), rồi so sánh trace ID trong callback với context nguồn. Không tự khởi tạo service bằng new.

Với CompletableFuture:

```java
CompletableFuture
        .supplyAsync(this::loadPayment, contextAwareExecutor)
        .thenApplyAsync(this::mapResult, contextAwareExecutor);
```

Mỗi callback async có thể dùng executor khác. Kiểm tra supplyAsync, thenApplyAsync, thenComposeAsync, handleAsync, whenCompleteAsync và callback thư viện ngoài. Callback non-async có thể chạy trên thread hoàn tất stage trước hoặc caller tùy trạng thái; không suy ra thread chỉ từ tên method.

## 8. Kiểm thử Reactor và WebFlux

Trong Reactor, Context gắn với subscription; thread có thể đổi khi pipeline chạy. Test cần kiểm tra context tại thời điểm signal được xử lý.

```java
StepVerifier.create(
        Mono.deferContextual(context ->
                Mono.just(context.get("request-key")))
            .contextWrite(context ->
                context.put("request-key", "request-A")))
    .expectNext("request-A")
    .verifyComplete();
```

Ví dụ chỉ chứng minh Reactor Context được truyền qua pipeline, không tự chứng minh Micrometer/Brave trace context được nối đúng. Để kiểm tra tracing, cần integration phù hợp và assertion current span tại nơi operator thực thi.

Cần test context qua contextWrite, publishOn/subscribeOn, flatMap, onErrorResume và cancellation. Tránh dùng ThreadLocal trực tiếp trong operator nếu chưa có context bridge phù hợp. Automatic context propagation hoặc Reactor hook có ảnh hưởng rộng, nên cần kiểm tra cả pipeline độc lập để phát hiện rò context giữa subscriptions.

## 9. Test failure, cancellation, timeout và rejection

| Trường hợp | Điều cần kiểm tra |
|---|---|
| Callback thành công | Context đúng; scope đóng sau hoàn tất |
| Callback ném exception | Error gắn đúng span/observation; worker cleanup |
| Future exceptional completion | Callback lỗi có context đúng |
| Cancellation | Lifecycle kết thúc theo chính sách; không giữ scope vô hạn |
| Timeout | Không giả định task đã dừng nếu chưa cancel |
| Executor rejection | Task không chạy; không tạo span giả cho phần chưa thực thi |
| Shutdown | Task queued/running được xử lý rõ |
| Caller-runs policy | Task có thể chạy trên thread submitter; context caller được khôi phục |
| Nested task | Child task nhận context đúng từ parent task |

Với CallerRunsPolicy, task bị từ chối có thể chạy trên thread gửi. Test phải xác nhận decorator không làm bẩn context caller sau khi callback hoàn thành.

Không assert mỗi task submit đều có span export nếu executor có thể từ chối hoặc sampler có thể drop. Assert lifecycle/context theo nhánh; export là tầng riêng.

## 10. Kiểm thử exporter và backend

| Test assertion | Điều nó chứng minh | Điều nó không chứng minh |
|---|---|---|
| Worker đọc đúng trace ID | Context được khôi phục trong worker | Reporter gửi span |
| Outbound có traceparent | Client inject W3C context | Server extract hoặc backend lưu |
| Server span có cùng trace ID | Server extract và tạo span liên kết | Mọi downstream spans được export |
| Collector nhận span | Export pipeline chuyển dữ liệu | UI/retention hoạt động đúng |
| Zipkin UI hiển thị trace | Trace được ingest và tìm thấy | Mọi request đều được sample |
| Log có trace ID | Log correlation hoạt động tại thời điểm ghi | Span tồn tại trong backend |

Ở tầng unit/integration có thể dùng tracer/exporter test để thu spans trong bộ nhớ. API tùy Brave, OpenTelemetry SDK và Micrometer version; không dùng API của implementation khác.

E2E test nên giới hạn số lượng:

1. Khởi động hai service và backend trace trong môi trường cô lập.
2. Cấu hình sampler deterministic để giữ trace test.
3. Gọi request xuyên service.
4. Lấy trace ID từ context hoặc response correlation test.
5. Query backend theo trace ID.
6. Assert client/server spans và parent relationship phù hợp.
7. Kiểm tra lỗi reporter/collector.
8. Dọn containers/processes.

Backend có thể ingest bất đồng bộ; dùng polling theo deadline hữu hạn thay vì sleep cố định dài.

## 11. Assertions ổn định và tránh test chập chờn

**Nên assert:** trace ID continuity, parent/link semantics, header format, scope cleanup, không có trace cũ ở task kế tiếp, error/cancellation lifecycle.

**Tránh assert:**

- Trace ID hard-code.
- Timestamp chính xác đến nano/microsecond không cần thiết.
- Thứ tự tuyệt đối của spans chạy song song.
- Tổng duration bằng tổng duration mọi child spans.
- Mọi request xuất hiện trong backend khi sampling chưa cố định.
- Toàn bộ thuộc tính nội bộ của library có thể đổi theo version.
- Log line chính xác từng ký tự nếu pattern không phải hợp đồng ứng dụng.

Dùng Future/latch/StepVerifier với timeout hữu hạn. Một test tốt giải thích vì sao assertion quan trọng; ví dụ task C không context bảo vệ khỏi rò rỉ context giữa các request dùng chung worker.

## 12. Kiểm tra metrics và logs đi cùng context

### 12.1. Log correlation

Một test log capture có thể tạo trace/span scope, ghi log trên thread hiện tại, ghi log trong executor đã decor, capture qua appender/test sink, rồi assert trace ID/span ID đúng. Submit thêm task không context trên cùng worker để đảm bảo ID cũ không còn.

Đọc MDC trực tiếp chỉ kiểm tra một phần; nếu format log là hợp đồng vận hành, hãy thêm log capture test. Không dùng System.out làm bằng chứng cho MDC nếu logging pattern không in MDC.

### 12.2. Metrics không gắn trace ID làm tag

Metric nên dùng dimensions ổn định như operation, route template, method, status group hoặc dependency. Không gắn trace ID vào metric labels vì cardinality cao. Nếu backend hỗ trợ exemplar, test liên kết metric sample với trace theo cơ chế đó.

Sampling có thể bỏ trace nhưng metrics vẫn cần phản ánh request theo thiết kế. Kiểm tra để business metrics không vô tình phụ thuộc vào việc sampler có giữ span hay không.

## 13. Ma trận kiểm thử gợi ý

| Scenario | Unit | Spring integration | E2E |
|---|:---:|:---:|:---:|
| Observation start/stop/error | ✓ |  |  |
| ContextSnapshot capture/restore | ✓ | ✓ |  |
| Thread pool reuse / task không context | ✓ | ✓ |  |
| TaskDecorator bean wiring |  | ✓ |  |
| @Async qua Spring proxy |  | ✓ |  |
| CompletableFuture qua nhiều executor | ✓ | ✓ |  |
| Reactor Context/scheduler | ✓ | ✓ |  |
| HTTP client inject header |  | ✓ | ✓ |
| HTTP server extract header |  | ✓ | ✓ |
| B3/W3C giữa hai service |  | ✓ | ✓ |
| Sampling policy | ✓ | ✓ | ✓ có mục tiêu |
| Reporter/collector/backend ingestion |  |  | ✓ |
| Log MDC correlation | ✓ | ✓ |  |
| Metrics còn ghi khi trace bị sample | ✓ | ✓ |  |
| Security/privacy telemetry |  | ✓ | ✓ theo security test |

Chọn tổ hợp đại diện cho executor, client, messaging và reactive path mà ứng dụng thật sự dùng; không cần nhân mọi tổ hợp thành hàng trăm test.

## 14. Quy trình chẩn đoán khi test fail

1. **Thread nguồn:** trace/span context có active trước submit không?
2. **Executor:** code dùng bean đã decor hay raw executor?
3. **Accessor:** context registry biết cách capture/restore trace/MDC/custom ThreadLocal không?
4. **Thời điểm capture:** snapshot được tạo ở mỗi lần submit hay dùng lại snapshot cũ?
5. **Worker:** context trong callback có đúng? Task tiếp theo có mang ID cũ?
6. **Lifecycle:** scope/span đóng ở thread thực thi? Callback hoàn tất trước khi observation stop?
7. **Network:** client inject header, proxy giữ header, server extract đúng propagator?
8. **Sampling/export:** context đúng nhưng backend trống thì sampler, reporter, collector, retention và query có hoạt động?

| Kết quả kiểm tra | Hướng xử lý |
|---|---|
| Source không có context | Server instrumentation và scope trước submit |
| Source có, worker không có | Executor, decorator, snapshot, accessor |
| Worker có trace, child ID mới | Current span/parent creation, tracer bridge |
| Worker đúng, outbound header thiếu | HTTP client instrumentation/propagator |
| Header đúng, server trace khác | Server extraction, gateway, format |
| Context/parent đúng, Zipkin trống | Reporter, sampler, collector, backend |
| Task B thấy trace A | Cleanup/restore và worker reuse |
| Task không context thấy trace trước | Context leakage; kiểm tra scope/finally/reset |

## 15. Các anti-pattern khi kiểm thử propagation

| Anti-pattern | Vì sao yếu/sai | Cách thay thế |
|---|---|---|
| Chỉ assert HTTP 200 | Không chứng minh trace context | Assert current trace và headers |
| Chỉ kiểm tra log có traceId | Có thể chỉ truyền chuỗi, không có parent span | Kiểm tra tracer context và span relationship |
| Chỉ test task A | Không phát hiện leakage | Single-thread executor, task B/C |
| Dùng Thread.sleep | Test phụ thuộc tốc độ máy | Future/latch/StepVerifier |
| Hard-code trace ID | Test giòn | Capture ID trong test |
| Bỏ Spring proxy trong test @Async | Không kiểm tra wiring | Inject bean qua context |
| Mock executor chạy inline | Không tạo thread boundary | Test real worker thread |
| Test ContextSnapshot không accessor | Không chứng minh trace context | Assert tracer integration thật |
| Dùng E2E backend cho mọi test | Chậm, khó chẩn đoán | Unit/integration là chủ đạo |
| Tăng sampling 100% trong production | Chi phí/rủi ro | Sampler test riêng |
| Trace không xuất hiện đồng nghĩa propagation fail | Có thể do export/retention | Kiểm tra context trước, pipeline sau |
| Bỏ qua cancellation/exception | Scope có thể không cleanup | Test mọi terminal path |

## 16. Checklist trước khi merge

1. Ranh giới thread/executor/HTTP/messaging/Reactor đã có test?
2. Thread nguồn có current context trước submit?
3. Snapshot capture ở từng lần submit, không dùng chung giữa request?
4. Callback thấy đúng trace/span/tenant context?
5. Scope được đóng và worker được restore cả khi lỗi/cancel?
6. Task A, B và task không context chạy cùng worker mà không leakage?
7. Observation/span bao quanh công việc thực tế, không chỉ thời gian enqueue?
8. HTTP client inject và server extract đúng B3/W3C?
9. Reactor/messaging dùng đúng propagation model?
10. @Async và executor thực tế được test qua Spring bean?
11. Log correlation đúng và không sót sang task khác?
12. Metrics không gắn trace ID làm label và không phụ thuộc sampling ngoài ý muốn?
13. Test phân biệt context correctness với export?
14. Headers/baggage/attributes không chứa token, PII ngoài allowlist?
15. Test dùng executor/latch/Future/StepVerifier xác định và timeout hữu hạn?
16. API tương thích Spring Boot, Spring Framework, Micrometer và tracer version?

## 17. Câu hỏi tự đánh giá

**Câu 1.** Method async trả kết quả đúng nhưng trace ID trong worker null. Test đã pass propagation chưa?

**Gợi ý:** Chưa. Test nghiệp vụ và test context là hai hợp đồng riêng.

**Câu 2.** Vì sao single-thread executor hữu ích để test context leakage?

**Gợi ý:** Các task chắc chắn tái sử dụng cùng worker, dễ phát hiện ThreadLocal/MDC của task trước còn sót.

**Câu 3.** Task A thấy trace A và task B thấy trace B đã đủ chứng minh cleanup chưa?

**Gợi ý:** Thêm task C không context và xác nhận C thấy null.

**Câu 4.** Outbound có traceparent đúng. Đã chứng minh downstream có span cùng trace chưa?

**Gợi ý:** Chưa. Cần kiểm tra server extraction và span context downstream.

**Câu 5.** TestObservationRegistry có kiểm tra Zipkin đã lưu span không?

**Gợi ý:** Không. Nó hỗ trợ test Observation lifecycle; export/ingestion/backend cần test riêng.

**Câu 6.** Vì sao không hard-code trace ID trong assertion?

**Gợi ý:** ID thường ngẫu nhiên; capture ID từ test rồi parse và so sánh.

**Câu 7.** Worker thấy current span và outbound header đúng nhưng backend không có trace. Kiểm tra gì?

**Gợi ý:** Sampling, span end, reporter/exporter, collector, storage, retention và query.

**Câu 8.** Task gửi email chạy sau khi request trả response có bắt buộc là child span của request không?

**Gợi ý:** Không. Với công việc độc lập lâu dài, consumer/root span có link tới producer context có thể đúng semantics hơn.

**Câu 9.** Vì sao mock executor chạy inline không đủ kiểm thử propagation qua thread?

**Gợi ý:** Nó không tạo execution boundary; ThreadLocal vẫn trên thread gọi.

**Câu 10.** Sampling 10% có thể assert mọi lần chạy đều có trace trong Zipkin không?

**Gợi ý:** Không. Dùng sampler deterministic riêng trong test cần kiểm tra export.

## Kết luận

**Kiểm thử context propagation phải chứng minh context đúng tại từng ranh giới thực thi và được dọn đúng sau khi công việc kết thúc.** Trong Spring Boot, kết hợp unit test cho ContextSnapshot/lifecycle, single-thread executor để bắt thread reuse leakage, integration test cho TaskDecorator/@Async/HTTP client và một số E2E test xuyên service. Assert trace context và quan hệ parent/link theo semantics, kiểm tra B3/W3C headers, error/cancellation và log correlation; đồng thời phân biệt lỗi propagation với sampling, reporter, exporter và backend. Một pipeline chỉ đáng tin khi không chỉ truyền đúng context cho task hiện tại mà còn bảo đảm task tiếp theo không thừa hưởng context cũ.
