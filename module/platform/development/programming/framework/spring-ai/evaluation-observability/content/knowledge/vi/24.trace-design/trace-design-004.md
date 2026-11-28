# Phân biệt span cha con với span link cho tác vụ bất đồng bộ

Một request Spring AI có thể trả lời người dùng trong một giây, sau đó một worker tiếp tục chấm relevance, groundedness và fact checking trong vài phút. Một message khác có thể gom hàng chục kết quả từ nhiều request để chạy batch evaluation. Nếu mọi tác vụ đều được gắn thành **span con của HTTP request ban đầu**, trace có thể kéo dài quá lâu, khó lấy mẫu và không phản ánh đúng vòng đời công việc. Nếu mỗi worker tự tạo trace mới mà không giữ mối liên hệ với request nguồn, ta lại mất khả năng lần ngược nguyên nhân.

Trong chương **Thiết kế trace** của module `SPRING_AI_EVALUATION_OBSERVABILITY`, bài học này tập trung vào hai quan hệ khác nhau của distributed tracing:

- **Parent–child (span cha–con):** một operation là phần thực thi nằm trong operation khác, cùng một trace tree và có đúng một parent.
- **Span link:** một operation có quan hệ nhân quả hoặc liên quan với span/trace khác, nhưng không nhất thiết thuộc cây cha–con của nó. Một span có thể có nhiều links.

Ta sẽ dùng các tình huống async executor, `@Async`, Reactor, message queue, retry, batch/fan-in và worker đánh giá Spring AI để quyết định khi nào dùng quan hệ nào. Đồng thời, bài học kết nối trace với `runId`, `caseId`, prompt/model/index/rubric version, metrics, latency, token và chi phí để điều tra regression của RAG hoặc tool calling.

> **Nguyên tắc:** Chọn quan hệ theo **vòng đời và ý nghĩa nhân quả của operation**, không theo việc code có chạy trên thread khác hay không. Async không tự động có nghĩa là span link; chạy cùng thread cũng không tự động bảo đảm parent–child đúng.

## 1. Trace tree và span link giải quyết hai câu hỏi khác nhau

Một **trace tree** mô tả các operation được tổ chức theo quan hệ cha–con. Mỗi span (trừ root) có một parent duy nhất. Các span con có thể chạy tuần tự hoặc song song, nhưng cùng thuộc một trace.

**Span link** biểu diễn mối quan hệ giữa span hiện tại với một hoặc nhiều span context khác. Link không làm span nguồn trở thành parent, và không gộp hai trace thành một cây duy nhất.

| Đặc điểm | Parent–child | Span link |
|---|---|---|
| Quan hệ | Một parent trực tiếp cho mỗi span con | Một span có thể link tới nhiều span context |
| Trace ID | Thường cùng trace với parent | Có thể cùng hoặc khác trace |
| Dùng khi | Operation là một phần của vòng đời operation cha | Có liên quan nhân quả nhưng có lifecycle/ownership độc lập |
| Ví dụ | HTTP request → truy vấn RAG đồng bộ | HTTP answer → job judge chạy sau khi response đã kết thúc |
| Biểu diễn | Cây span | Link metadata giữa các spans |
| Ảnh hưởng sampling | Parent-based sampler có thể kế thừa quyết định từ parent | Link không tự kế thừa sampled decision của trace nguồn |

### 1.1. Parent–child: operation thuộc cùng một luồng công việc

Giả sử HTTP request nhận câu hỏi và **đợi** retrieval, model và tool hoàn thành trước khi trả response:

```text
TRACE T1
SERVER POST /api/answers                 [root]
└── app.ai.answer
    ├── app.rag.retrieve
    │   └── vectorstore.search
    ├── chat.model.call
    ├── tool.getOrderStatus
    └── chat.model.call.after_tool
```

Các bước trên là phần công việc trực tiếp tạo ra response. Parent–child cho phép đọc một timeline từ request tới kết quả, đo end-to-end latency và tìm operation nào gây chậm.

### 1.2. Span link: công việc có liên quan nhưng chạy độc lập

Giả sử API đã lưu answer và trả HTTP response. Một queue nhận event, rồi worker đánh giá answer sau đó:

```text
TRACE T1: answer request
SERVER POST /api/answers
└── app.ai.answer
    └── answer.persist

TRACE T2: asynchronous evaluation
app.ai.evaluation.process
  links:
    - answer.persist (span thuộc TRACE T1)
  ├── judge.model.call
  ├── rubric.validate
  └── evaluation.result.persist
```

Worker có một trace riêng T2. Link nói rằng job này được khởi tạo từ answer span ở T1, nhưng **T2 không phải child trong trace tree T1**. Cách tổ chức này phù hợp khi HTTP request đã kết thúc, queue có thời gian chờ, worker có retry hoặc job được lên lịch lại.

### 1.3. Đừng dùng span link để che một trace tree bị đứt

Nếu một lời gọi retrieval chạy đồng bộ bên trong `app.rag.pipeline` nhưng mất parent do context propagation lỗi, tạo một link tới span cha **không sửa được lỗi propagation**. Cần khôi phục context để retrieval thực sự là child. Span link dành cho quan hệ độc lập có chủ đích, không phải cách chữa mọi span root bất thường.

## 2. Quy tắc quyết định: parent–child hay span link?

Hãy trả lời bốn câu hỏi:

1. **Operation cha còn đang thực hiện và thực sự sở hữu công việc này không?** Nếu có, parent–child thường phù hợp.
2. **Kết quả công việc con có cần hoàn thành trước khi cha hoàn tất không?** Nếu có, đó là dấu hiệu mạnh cho parent–child.
3. **Công việc được tách thành transaction/job độc lập, có thể bắt đầu sau khi cha kết thúc, retry hoặc được worker khác nhận không?** Span link thường phù hợp hơn.
4. **Một operation phụ thuộc vào nhiều nguồn/requests khác nhau không?** Nếu có, một parent duy nhất không thể biểu diễn toàn bộ provenance; dùng links tới các nguồn.

| Tình huống | Lựa chọn thường hợp lý | Vì sao |
|---|---|---|
| HTTP gọi RAG đồng bộ và chờ kết quả | Parent–child | Retrieval là một phần của response |
| ChatClient gọi model rồi gọi tool trước khi trả answer | Parent–child | Tool loop nằm trong cùng answer operation |
| Fan-out hai retrievers rồi join trước khi trả answer | Parent–child với hai child spans | Cả hai thuộc cùng pipeline |
| Task ngắn trong executor, được await trước khi HTTP kết thúc | Parent–child | Cùng operation và vòng đời cha bao phủ task |
| Fire-and-forget notification sau response | Trace riêng + link, tùy ý nghĩa nghiệp vụ | Operation thông báo có vòng đời độc lập |
| Judge worker xử lý event sau khi answer API đã trả response | Trace riêng + link | Không kéo dài HTTP span |
| Batch chấm 100 answers từ nhiều request | Trace batch + nhiều links | Một batch có nhiều nguồn |
| Scheduled evaluation ban đêm cho dataset | Root trace của batch; link nếu có nguồn answer cụ thể | Không có một HTTP parent duy nhất |
| Queue consumer xử lý một message ngay sau publish | Parent hoặc link theo mô hình messaging/lifecycle | Phải chọn rõ ownership và thời gian |
| Queue consumer gộp nhiều messages | Consumer span với nhiều links | Một span không thể có nhiều parent |

**Đây là hướng dẫn ra quyết định, không phải quy tắc bắt buộc cho mọi hệ thống.** Messaging semantic conventions, framework và backend có thể chọn mô hình parent/link khác nhau. Hãy định nghĩa chính sách nhất quán, kiểm tra dữ liệu trace thực và ghi rõ lý do.

### 2.1. Async không đồng nghĩa span link

Một method được đánh dấu `@Async` có thể chạy trên thread khác nhưng vẫn là **một phần của HTTP operation**. Nếu caller chờ `Future` và chỉ trả response khi task hoàn thành, child span là lựa chọn tự nhiên. Context cần được capture/propagate sang executor.

Ngược lại, một tác vụ chạy trên cùng thread nhưng được tạo như một job độc lập, không thuộc transaction của operation hiện tại, vẫn có thể cần root span riêng và link. **Thread là chi tiết thực thi; quan hệ span phản ánh ngữ nghĩa operation.**

### 2.2. Async không đồng nghĩa luôn phải giữ parent span mở

Không cần giữ HTTP server span mở nhiều phút chỉ để đợi job đánh giá sau response. Điều đó làm latency của HTTP bị thổi phồng, giữ lifecycle request lâu hơn cần thiết và làm trace khó lấy mẫu. Khi job độc lập, dùng trace riêng và link tới nguồn.

Về mặt kỹ thuật, một span con vẫn có thể được tạo từ **SpanContext đã capture** sau khi span cha kết thúc; mô hình tracing không yêu cầu parent phải còn active tại đúng thời điểm child bắt đầu. Tuy nhiên, duration của parent không bao phủ phần công việc chạy muộn, exporter/collector có thể đã xử lý trace nguồn, và lifecycle của job không còn đồng nhất với request. Chỉ giữ cùng trace khi job thực sự là một phần của operation cha và hệ thống chấp nhận mô hình này; nếu job được tách thành transaction độc lập, trace mới + link thường dễ diễn giải hơn.

## 3. Cây span chỉ có một parent, links có thể có nhiều nguồn

Một span trong mô hình trace tree có tối đa **một parent**. Điều này phù hợp với luồng lồng nhau thông thường, nhưng không diễn tả đủ các tình huống **fan-in**:

- Batch evaluator gom answer từ 20 request khác nhau.
- Một báo cáo tổng hợp lấy kết quả từ nhiều evaluation runs.
- Một workflow hợp nhất kết quả từ semantic search và keyword search độc lập.
- Một incident handler xử lý nhiều messages/alerts có nguồn khác nhau.

Nếu tạo batch span làm child của request đầu tiên, trace sẽ ngụ ý sai rằng request đầu tiên sở hữu toàn bộ batch. Nếu tạo các request khác thành child của batch, ta cũng không thể thay đổi parent của spans đã tồn tại để tạo một cây đa cha. **Span links** giải quyết phần quan hệ nhiều nguồn.

### 3.1. Ví dụ batch judge có ba nguồn

```text
TRACE A: request A -> answer span A
TRACE B: request B -> answer span B
TRACE C: request C -> answer span C

TRACE D: evaluation.batch
  links:
    - answer span A
    - answer span B
    - answer span C
  ├── judge.case A
  ├── judge.case B
  └── judge.case C
```

Trace D có root riêng. Các links thể hiện batch phụ thuộc vào ba answer spans. Các case con của batch vẫn là child của batch span, vì chúng thuộc vòng đời xử lý batch.

### 3.2. Link không thay thế business correlation

Link là metadata tracing để truy vấn quan hệ. Để bảo đảm một case được chấm đúng một lần và có thể replay, vẫn cần khóa nghiệp vụ:

```text
runId
caseId
variant
answerId
rubricVersion
attemptId
answerTraceId
answerSpanId
judgeTraceId
```

`answerTraceId` đơn lẻ chưa đủ để tạo span link OpenTelemetry: link cần **SpanContext hợp lệ**, gồm trace ID, span ID và flags/tracestate tương ứng. Nên truyền tracing context qua carrier/header hoặc lưu SpanContext có cấu trúc theo chính sách. Không tự tạo link từ một trace ID không có span ID.

## 4. SpanContext và Span Link trong OpenTelemetry

Trong OpenTelemetry, **SpanContext** là phần định danh và trạng thái cần thiết để liên kết spans, thường bao gồm trace ID, span ID, trace flags và trace state. Một **Link** chứa SpanContext của một span liên quan, có thể kèm attributes giải thích quan hệ.

Span link thường được thêm khi **tạo span**, thông qua `SpanBuilder.addLink(...)`. Điều này quan trọng với sampler: quyết định lấy mẫu tại lúc start span có thể cần biết các links đã tồn tại. Không nên tạo span trước, rồi mới mong thêm links sau sẽ thay đổi quyết định head sampling đã thực hiện.

### 4.1. Những điều link không làm

- Không biến hai trace thành một trace.
- Không tạo parent–child relationship.
- Không truyền Chat Memory hoặc user context.
- Không bảo đảm trace nguồn đã được lưu trong backend.
- Không thay thế `runId`, `caseId`, message ID hay idempotency key.
- Không tự động tạo link chỉ vì JSON payload có `answerTraceId`.

### 4.2. Span link có thể có attributes

Một link có thể gắn attributes ít nhạy cảm, ví dụ:

| Attribute gợi ý | Ví dụ | Mục đích |
|---|---|---|
| `link.type` | `answer_source` | Vai trò của span nguồn |
| `message.operation` | `process` | Operation messaging |
| `evaluation.variant` | `prompt-B` | Biến thể thí nghiệm |
| `batch.position` | `3` | Vị trí nguồn trong batch |

Đây là quy ước của ứng dụng, không phải các attribute bắt buộc của W3C. Không gắn full prompt, document text, email, token hoặc secret vào link attributes.

## 5. Chọn mô hình cho từng loại tác vụ bất đồng bộ

### 5.1. Task ngắn, được await trước khi trả response

Ví dụ một request cần gọi semantic retrieval và keyword retrieval song song, rồi join kết quả trước khi sinh answer. Cả hai operation là thành phần của **cùng một câu trả lời**:

```text
TRACE T1
SERVER POST /api/answers
└── app.ai.answer
    └── app.rag.hybrid.retrieve
        ├── app.rag.semantic.search
        └── app.rag.keyword.search
```

Đây là parent–child phù hợp dù hai search chạy trên hai threads. Caller vẫn sở hữu operation, chờ kết quả và chỉ hoàn tất HTTP sau khi cả hai nhánh hoàn tất hoặc bị hủy theo policy.

### 5.2. Fire-and-forget sau khi response hoàn tất

Ví dụ API lưu answer và phát sự kiện analytics không ảnh hưởng response. Operation analytics có thể chạy sau khi HTTP span kết thúc:

```text
TRACE T1
SERVER POST /api/answers
└── app.ai.answer
    └── answer.persist

TRACE T2
app.analytics.record
  link -> answer.persist in T1
```

Một span link giúp tìm request đã tạo sự kiện. Nếu analytics chỉ là một phần nhỏ được chạy và đợi trong cùng request, parent–child vẫn hợp lý; quyết định phụ thuộc **ownership/lifecycle**, không chỉ từ khóa “async”.

### 5.3. Queue consumer xử lý một message

Với một message duy nhất, có hai lựa chọn phổ biến:

- **Continue context làm parent:** consumer span dùng context được inject trong message làm parent. Hữu ích khi muốn xem đường đi producer → consumer như một trace nhân quả liên tục và khoảng chờ queue thuộc cùng transaction logic.
- **New trace + link:** consumer tạo trace riêng, link tới producer span. Hữu ích khi consumer là một transaction độc lập, có thể chạy muộn, retry/redelivery hoặc có lifecycle dài hơn producer.

Không có lựa chọn duy nhất cho mọi broker/framework. Cần xem messaging instrumentation đang áp dụng semantic convention nào và **không tự tạo thêm parent/link song song** nếu instrumentation đã quyết định một mô hình.

### 5.4. Batch consumer có nhiều messages

Một consumer span xử lý batch có thể nhận messages được tạo từ nhiều trace khác nhau. Một span chỉ có một parent, do đó không thể làm child của tất cả producer spans. Mô hình thường hợp lý là:

```text
TRACE T_BATCH
messaging.process.batch
  links:
    - producer span from TRACE T_A
    - producer span from TRACE T_B
    - producer span from TRACE T_C
  ├── process.message A
  ├── process.message B
  └── process.message C
```

### 5.5. Scheduled job và replay

Một job chạy mỗi đêm đánh giá lại dataset không có một HTTP parent duy nhất. Tạo root span cho job run; nếu từng case liên kết với answer/request đã có trace nguồn, thêm links cho các nguồn tương ứng. Nếu chỉ là benchmark mới trên corpus/dataset độc lập, không cần giả tạo links đến một request không liên quan.

Replay cũng nên có trace/run ID mới để phân biệt lần chạy gốc và lần tái hiện. Giữ `sourceRunId`, `sourceCaseId`, `sourceAnswerId` trong result manifest. Nếu replay thực sự được khởi tạo từ một span nguồn, có thể thêm link; nếu không, business correlation đủ để chỉ ra provenance.

## 6. Spring Boot/Micrometer: giữ parent context cho async child

Micrometer Observation/Tracing thường tích hợp với context hiện tại để tạo span con khi một observation bắt đầu bên trong scope đang active. Khi công việc chuyển sang executor, cần **capture/restore context** theo cơ chế được hỗ trợ.

### 6.1. Cấu hình executor cho Spring Framework 6.1+

```java
import java.util.concurrent.Executor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
class ObservedExecutorConfiguration {
    @Bean("observedExecutor")
    Executor observedExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(200);
        executor.setThreadNamePrefix("ai-work-");
        executor.setTaskDecorator(
                new ContextPropagatingTaskDecorator());
        executor.initialize();
        return executor;
    }
}
```

`ContextPropagatingTaskDecorator` của Spring Framework 6.1+ capture context lúc submit task và khôi phục trong lúc chạy. Nó chỉ truyền những context đã đăng ký/được framework hỗ trợ; **không tự biến một job dài thành span link** và cũng không quyết định lifecycle nghiệp vụ. Với Spring Framework cũ hơn, dùng cơ chế context propagation tương thích phiên bản, không sao chép class này nếu dependency chưa có.

### 6.2. Async child được chờ hoàn tất

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
class HybridRetrievalService {
    private final ObservationRegistry registry;
    private final SearchPort semantic;
    private final SearchPort keyword;

    HybridRetrievalService(
            ObservationRegistry registry,
            SearchPort semantic,
            SearchPort keyword) {
        this.registry = registry;
        this.semantic = semantic;
        this.keyword = keyword;
    }

    @Async("observedExecutor")
    public CompletableFuture<SearchResult> semanticSearch(String query) {
        SearchResult result = Observation.createNotStarted(
                        "app.rag.semantic.search", registry)
                .observe(() -> semantic.search(query));
        return CompletableFuture.completedFuture(result);
    }

    @Async("observedExecutor")
    public CompletableFuture<SearchResult> keywordSearch(String query) {
        SearchResult result = Observation.createNotStarted(
                        "app.rag.keyword.search", registry)
                .observe(() -> keyword.search(query));
        return CompletableFuture.completedFuture(result);
    }
}

interface SearchPort {
    SearchResult search(String query);
}

record SearchResult(int hitCount) {}
```

Caller có thể kết hợp hai futures và đợi trước khi hoàn tất operation:

```java
CompletableFuture<SearchResult> semantic =
        retrieval.semanticSearch(question);
CompletableFuture<SearchResult> keyword =
        retrieval.keywordSearch(question);

CompletableFuture.allOf(semantic, keyword).join();
SearchResult semanticResult = semantic.join();
SearchResult keywordResult = keyword.join();
```

Các đoạn trên minh họa **một thiết kế**, không phải một class có thể biên dịch độc lập: cần bean `SearchPort`, `SearchResult` và caller được cấu hình. `@Async` phải được gọi qua Spring proxy; self-invocation không kích hoạt async interception. Nếu caller chờ cả hai kết quả trong HTTP request, hai observations là child của operation đang active **khi context propagation được cấu hình đúng**.

**Không gọi `CompletableFuture.supplyAsync` trên common pool một cách tùy tiện** rồi giả định parent context được truyền. Dùng executor được quản lý và kiểm tra trace thực. Cũng cần bảo đảm task không tiếp tục chạy sau khi parent đã kết thúc do timeout/cancellation; nếu nó trở thành job độc lập, chuyển sang mô hình trace riêng/link theo policy.

### 6.3. Không double-wrap instrumentation

Nếu `@Async` executor đã có `ContextPropagatingTaskDecorator` và Spring Observation instrumentation hoạt động, không cần thêm một lớp tự capture/restore `ThreadLocal` nữa. Double propagation có thể làm khó xác định context nào đang active. Chọn một cơ chế chuẩn, test parent IDs và kiểm tra cleanup sau task.

## 7. Tạo root span mới có link bằng OpenTelemetry API

Micrometer Observation phù hợp để instrument operation thông thường và tạo metrics/traces qua bridge. **Span links là khả năng tracing cụ thể**; nếu abstraction đang dùng không cung cấp API links phù hợp, có thể sử dụng OpenTelemetry API được cấu hình trên **cùng tracing SDK** để tạo span có links.

Không khởi tạo một OpenTelemetry SDK thứ hai độc lập chỉ để tạo link khi ứng dụng đã dùng Micrometer Tracing bridge. Cần một pipeline tracing thống nhất để các spans có thể được export và truy vấn cùng backend.

### 7.1. Ví dụ detached evaluation span với một link

Giả sử worker nhận được `SpanContext` của answer span từ message headers đã được propagator extract. Worker tạo một root span mới và thêm link tới answer span:

```java
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.SpanContext;
import io.opentelemetry.api.trace.SpanKind;
import io.opentelemetry.api.trace.StatusCode;
import io.opentelemetry.api.trace.Tracer;
import io.opentelemetry.context.Scope;

final class EvaluationTraceWorker {
    private final Tracer tracer;
    private final JudgeService judge;

    EvaluationTraceWorker(Tracer tracer, JudgeService judge) {
        this.tracer = tracer;
        this.judge = judge;
    }

    JudgeResult evaluate(
            EvaluationEvent event, SpanContext answerSpanContext) {
        var builder = tracer.spanBuilder("app.ai.evaluation.process")
                .setNoParent()
                .setSpanKind(SpanKind.CONSUMER)
                .setAttribute("evaluation.variant", event.variant())
                .setAttribute("evaluation.rubric.version",
                        event.rubricVersion());

        if (answerSpanContext != null && answerSpanContext.isValid()) {
            builder.addLink(answerSpanContext);
        }

        Span span = builder.startSpan();
        try (Scope scope = span.makeCurrent()) {
            return judge.evaluate(event);
        } catch (RuntimeException error) {
            span.recordException(error);
            span.setStatus(StatusCode.ERROR);
            throw error;
        } finally {
            span.end();
        }
    }
}

interface JudgeService {
    JudgeResult evaluate(EvaluationEvent event);
}

record EvaluationEvent(
        String runId, String caseId,
        String variant, String rubricVersion) {}

record JudgeResult(String status) {}
```

Đây là ví dụ dùng OpenTelemetry API Java. Các dependency, bean `Tracer` và wiring với Micrometer bridge phải theo phiên bản Spring Boot/OTel của dự án. `setNoParent()` chủ động tạo root mới; `addLink(answerSpanContext)` thêm mối quan hệ tới answer span. Nếu bỏ `setNoParent()`, builder có thể lấy current context của worker làm parent, khiến mô hình không còn là root độc lập như dự định.

### 7.2. Khi nào không nên tạo link?

- Không có span nguồn thực sự, chỉ có một `caseId` trong dataset.
- Tác vụ chỉ là child đồng bộ và context hiện tại đã đúng.
- Chỉ biết trace ID nhưng không có span ID/SpanContext hợp lệ.
- Link sẽ làm lộ metadata nhạy cảm qua attributes.
- Backend/sampler policy không cần quan hệ này và result store đã đáp ứng nhu cầu correlation đơn giản.

Trong những trường hợp đó, giữ business correlation trong result store là đủ; đừng tạo link giả.

## 8. Truyền SpanContext qua message queue để tạo link

Để worker tạo link tới answer span, worker phải nhận được **SpanContext của span nguồn**, không chỉ một trace ID. Với message queue, cách chuẩn là inject/extract context qua message headers bằng propagator đã cấu hình.

### 8.1. Producer inject context

Ví dụ dưới đây dùng một `Map<String, String>` làm carrier minh họa. Kafka/RabbitMQ thực tế có kiểu headers riêng; dùng instrumentation hoặc adapter chuyển đổi carrier tương ứng:

```java
import io.opentelemetry.api.OpenTelemetry;
import io.opentelemetry.context.Context;
import io.opentelemetry.context.propagation.TextMapSetter;
import java.util.HashMap;
import java.util.Map;

final class EvaluationEventPublisher {
    private static final TextMapSetter<Map<String, String>> SETTER =
            (carrier, key, value) -> carrier.put(key, value);

    private final OpenTelemetry openTelemetry;
    private final MessageBroker broker;

    EvaluationEventPublisher(
            OpenTelemetry openTelemetry, MessageBroker broker) {
        this.openTelemetry = openTelemetry;
        this.broker = broker;
    }

    void publish(EvaluationEvent event) {
        Map<String, String> headers = new HashMap<>();

        // Gọi khi publish span/current context đang active.
        openTelemetry.getPropagators()
                .getTextMapPropagator()
                .inject(Context.current(), headers, SETTER);

        broker.send(event, headers);
    }
}

interface MessageBroker {
    void send(EvaluationEvent event, Map<String, String> headers);
}
```

Propagator có thể ghi `traceparent`, `tracestate` và baggage nếu đã bật. **Không tự ghi đè headers tracing bằng giá trị do payload hoặc user cung cấp.** Nếu Spring Kafka/AMQP hoặc agent đã tự động inject context, dùng một cơ chế thống nhất và kiểm tra header thực; không inject lần hai bằng code thủ công.

### 8.2. Consumer extract context

```java
import io.opentelemetry.api.OpenTelemetry;
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.SpanContext;
import io.opentelemetry.context.Context;
import io.opentelemetry.context.propagation.TextMapGetter;
import java.util.Map;

final class EvaluationMessageContextExtractor {
    private static final TextMapGetter<Map<String, String>> GETTER =
            new TextMapGetter<>() {
                @Override
                public Iterable<String> keys(Map<String, String> carrier) {
                    return carrier.keySet();
                }

                @Override
                public String get(
                        Map<String, String> carrier, String key) {
                    return carrier.get(key);
                }
            };

    private final OpenTelemetry openTelemetry;

    EvaluationMessageContextExtractor(OpenTelemetry openTelemetry) {
        this.openTelemetry = openTelemetry;
    }

    SpanContext extractProducerSpan(Map<String, String> headers) {
        Context extracted = openTelemetry.getPropagators()
                .getTextMapPropagator()
                .extract(Context.root(), headers, GETTER);

        return Span.fromContext(extracted).getSpanContext();
    }
}
```

Nếu header thiếu hoặc không hợp lệ, extracted context có thể không chứa SpanContext hợp lệ. Worker vẫn có thể xử lý event theo policy, nhưng không được tạo link giả. Ghi rõ tracing context missing/invalid bằng một attribute an toàn nếu cần điều tra; việc xử lý message không nên phụ thuộc trace header để quyết định quyền nghiệp vụ.

### 8.3. Chọn parent hoặc link sau khi extract

Sau khi extract, **chọn một trong hai cách**, không dùng cả hai cho cùng một quan hệ:

```java
// Lựa chọn A: consumer tiếp tục producer context làm parent.
var continued = tracer.spanBuilder("evaluation.consume")
        .setParent(extractedMessageContext)
        .setSpanKind(SpanKind.CONSUMER)
        .startSpan();

// Lựa chọn B: consumer mở trace riêng và link về producer.
var detached = tracer.spanBuilder("evaluation.consume")
        .setNoParent()
        .setSpanKind(SpanKind.CONSUMER)
        .addLink(producerSpanContext)
        .startSpan();
```

Đây là các **mẫu lựa chọn**, không chạy đồng thời. Lựa chọn A giữ một trace liên tục; lựa chọn B tạo một root mới có link. Nếu messaging instrumentation đã tạo consumer span, không tự tạo thêm một span `evaluation.consume` bọc cùng một thao tác trừ khi đó là operation nghiệp vụ khác.

## 9. Fan-in và batch: một span link tới nhiều nguồn

Batch evaluation là ví dụ điển hình cho span links. Một batch có thể chấm nhiều answer được tạo từ các request độc lập. Cây cha–con không thể có nhiều parent, vì vậy một batch span có thể là root mới và link tới từng answer span.

### 9.1. Tạo batch span có nhiều links

```java
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.SpanContext;
import io.opentelemetry.api.trace.SpanKind;
import io.opentelemetry.api.trace.Tracer;
import io.opentelemetry.context.Scope;
import java.util.List;

final class BatchEvaluationTracer {
    private final Tracer tracer;
    private final BatchJudge judge;

    BatchEvaluationTracer(Tracer tracer, BatchJudge judge) {
        this.tracer = tracer;
        this.judge = judge;
    }

    BatchResult evaluate(
            String runId,
            List<EvaluationEvent> events,
            List<SpanContext> sourceContexts) {
        var builder = tracer.spanBuilder("app.ai.evaluation.batch")
                .setNoParent()
                .setSpanKind(SpanKind.INTERNAL)
                .setAttribute("evaluation.run.id", runId)
                .setAttribute("evaluation.batch.size", events.size());

        sourceContexts.stream()
                .filter(context -> context != null && context.isValid())
                .forEach(builder::addLink);

        Span span = builder.startSpan();
        try (Scope scope = span.makeCurrent()) {
            return judge.evaluateBatch(events);
        } finally {
            span.end();
        }
    }
}

interface BatchJudge {
    BatchResult evaluateBatch(List<EvaluationEvent> events);
}

record BatchResult(int completed, int failed) {}
```

Đoạn code chỉ minh họa cách thêm nhiều links. Trong production:

- Giới hạn số links theo kích thước batch và giới hạn backend/SDK.
- Không gắn toàn bộ `caseId` hoặc raw payload vào link attributes.
- Nếu batch quá lớn, có thể chia thành các batch con, mỗi batch có links cho một nhóm nguồn.
- Bảo đảm `sourceContexts` thực sự đến từ message headers/span contexts tin cậy trong nội bộ tracing; không nhận SpanContext tự do từ client ngoài.
- Lưu danh sách case IDs và source trace/span IDs trong result store được phân quyền để truy vấn đầy đủ, vì backend có thể giới hạn số links hiển thị.

### 9.2. Batch span và child case spans

```text
TRACE T_BATCH
app.ai.evaluation.batch
  links -> answer A, answer B, answer C
  ├── app.ai.evaluation.case A
  ├── app.ai.evaluation.case B
  └── app.ai.evaluation.case C
```

Các `case` spans là child vì chúng được thực thi trong vòng đời batch. Nếu từng case lại được đẩy sang worker độc lập, mỗi worker có thể tạo trace riêng và link tới answer nguồn cùng batch span nếu có quan hệ. Không gắn tất cả vào một parent tùy tiện chỉ để có một trace lớn.

## 10. Retry, redelivery và idempotency không phải cùng một khái niệm

Một tác vụ bất đồng bộ có thể được chạy nhiều lần vì:

- HTTP client retry khi gặp 503/429.
- Queue redelivery do consumer lỗi trước khi ack.
- Worker retry vì judge timeout.
- Người vận hành replay case để điều tra regression.
- Một scheduler chạy lại toàn bộ dataset ở run mới.

Trace cần cho thấy **mỗi attempt** và quan hệ với công việc nguồn, còn result store cần bảo đảm **một final outcome theo khóa nghiệp vụ**.

### 10.1. Mô hình trace cho retry bên trong một worker invocation

Nếu một worker invocation thử lại judge ba lần trước khi kết thúc, các attempts có thể là child spans dưới operation xử lý:

```text
TRACE T_WORKER
app.ai.evaluation.process
  links -> answer span nguồn
  ├── judge.attempt 1   ERROR: timeout
  ├── retry.backoff    event hoặc span nếu đủ ý nghĩa
  ├── judge.attempt 2   ERROR: HTTP 503
  └── judge.attempt 3   PASS: valid verdict
```

Worker invocation là operation cha; attempts là các operation con. Không tạo một trace mới cho mỗi retry nếu chúng là các attempts của cùng một lần xử lý và cần quan sát chung budget/deadline.

### 10.2. Redelivery thành worker invocation mới

Nếu broker phát lại message sau khi consumer chết hoặc lease hết hạn, lần xử lý sau có thể là một invocation độc lập. Nó có thể tạo trace mới, link tới producer context và giữ `messageId`/`eventId` giống lần trước. Dùng `attemptNo`/delivery count để phân biệt lần thực thi, không ghi đè trace trước.

### 10.3. Idempotency key

Với evaluation:

```text
final_result_key =
  (runId, caseId, variant, rubricVersion)

attempt_key =
  (runId, caseId, variant, rubricVersion, attemptNo)

delivery_key =
  (messageId, deliveryCount)
```

Các khóa trên là **quy ước ví dụ**. Hệ thống thật có thể cần `pipelineVersion`, `judgeModelVersion` hoặc `datasetVersion` trong unique key. Trace ID không phải idempotency key: retry có thể cùng trace hoặc trace mới tùy mô hình, nhưng kết quả cuối vẫn phải tuân thủ hợp đồng nghiệp vụ.

### 10.4. Không chọn PASS bằng cách retry FAIL

Retry chỉ phục hồi lỗi tạm thời, không phải cách thử nhiều lần đến khi có verdict mong muốn. Nếu judge trả FAIL hợp lệ, không retry để tìm PASS. Nếu judge timeout/429/JSON invalid, giữ ERROR/INVALID hoặc retry trong giới hạn; nếu attempt sau trả PASS hợp lệ, final outcome có thể PASS nhưng phải giữ lịch sử attempts và chi phí của các lần trước.

## 11. Sampling và span links

Parent-based sampling thường dựa vào sampled decision của parent. Với một root span mới có links, **link không tự động khiến root kế thừa sampled decision của nguồn**. Nếu job T2 được tạo từ answer span T1 nhưng T2 dùng `setNoParent()`, sampler của T2 sẽ áp dụng chính sách cho root mới.

Điều này có hệ quả:

- T1 có thể được giữ, nhưng T2 bị head sampler bỏ.
- T2 có thể được giữ độc lập dù T1 không được giữ.
- Link có thể giúp tail sampler ở collector nhận diện trace liên quan, nếu spans/link được export đầy đủ và policy hỗ trợ.
- Nếu cần sampler dựa vào links, links phải được cung cấp **trước khi span bắt đầu** để sampler có thể xem chúng.

### 11.1. Chọn sampling theo mục tiêu

| Mục tiêu | Hướng cân nhắc |
|---|---|
| Theo dõi đầy đủ parent-child trong integration test | Sampling 100% trong môi trường test biệt lập |
| Giữ traces lỗi/chậm sau khi quan sát | Tail sampling ở collector nếu hạ tầng hỗ trợ |
| Giữ worker độc lập có link tới request critical | Root sampling policy có nhận biết links hoặc quyết định theo attributes an toàn |
| Thống kê toàn bộ evaluation cases | Metrics/result store luôn ghi theo case, không phụ thuộc trace sampling |
| Giảm chi phí production | Head sampling/parent-based sampling và retention phù hợp |

**Không dùng trace sampling để tính pass rate.** Một trace không được lưu không có nghĩa case không chạy. Result store phải giữ PASS/FAIL/INVALID/ERROR và coverage theo toàn bộ dataset đã lên lịch.

### 11.2. Link và head sampler

Với head sampling, quyết định thường diễn ra khi span được start. Vì vậy:

1. Thu thập các SpanContexts nguồn trước khi tạo batch/worker span.
2. Thêm links bằng `SpanBuilder.addLink(...)`.
3. Sau đó mới gọi `startSpan()`.
4. Nếu link chỉ được phát hiện sau khi span đã start, sampler head đã không thể dùng nó để ra quyết định.

Tail sampling có thể xét toàn bộ trace sau khi nhận spans, nhưng cần collector giữ dữ liệu đủ lâu và xử lý trường hợp các traces nguồn đến lệch thời gian. Đừng giả định một span link bảo đảm backend luôn giữ cả trace nguồn và trace đích.

## 12. Tích hợp Spring AI: request answer và job evaluation độc lập

Trong một ứng dụng Spring AI, luồng trả lời có thể dùng `ChatClient`, advisor RAG, model và tool. Worker đánh giá có thể dùng một `ChatClient` riêng hoặc evaluator khác. Cần phân biệt:

- **Answer operation:** công việc đồng bộ trả lời người dùng, thường thuộc HTTP trace.
- **Evaluation operation:** công việc chấm theo dataset/rubric, có thể chạy async sau response.
- **Case attempt:** một lần thực thi judge cụ thể, có thể là child của evaluation operation.
- **Provider request:** từng lần gọi model thật, có thể có transport retries bên trong.

### 12.1. Tạo event mang business correlation

Payload message có thể gồm:

```json
{
  "eventId": "evaluation-event-017",
  "runId": "run-2026-11-demo",
  "caseId": "rag-017",
  "answerId": "answer-017",
  "variant": "prompt-B",
  "datasetVersion": "policy-eval-v3",
  "promptVersion": "rag-prompt-07",
  "modelId": "configured-app-model",
  "indexVersion": "policy-index-v2",
  "rubricVersion": "groundedness-v2",
  "answerTraceId": "trace-id-for-lookup",
  "answerSpanId": "span-id-for-lookup"
}
```

Các giá trị chỉ minh họa. Payload giữ **business correlation và provenance**; trace context nên được truyền trong headers qua propagator nếu cần parent/link. Nếu chỉ lưu `answerTraceId`/`answerSpanId` như string để tra cứu, chưa thể coi đó là link trong telemetry cho đến khi SpanContext được tạo/khôi phục hợp lệ.

### 12.2. Hai mô hình xử lý worker

| Mô hình | Trace của worker | Khi phù hợp |
|---|---|---|
| Consumer tiếp tục message context | Worker span là child của producer context | Muốn một trace xuyên producer → queue → consumer, thời gian queue thuộc operation logic |
| Worker tạo root và link | Worker có trace mới, link tới producer span | Job độc lập, xử lý lâu, retry/redelivery, batch hoặc nhiều nguồn |

Khi dùng Spring Kafka/AMQP instrumentation, framework có thể đã chọn propagation model. Trước khi tạo span thủ công, xem spans thực tế và semantic convention của phiên bản đang dùng; không tạo consumer span trùng với span tự động.

### 12.3. Span cho judge attempts

Một trace worker có thể tổ chức:

```text
app.ai.evaluation.process
  link -> answer span
  ├── app.ai.judge.attempt
  │     └── HTTP CLIENT / model provider
  ├── app.ai.judge.retry
  ├── app.ai.judge.attempt
  │     └── HTTP CLIENT / model provider
  └── app.ai.result.persist
```

Mỗi attempt ghi model ID, rubric version, provider status, duration và usage nếu có. Không đặt toàn bộ prompt/evidence trong span attributes. Kết quả cuối ghi trạng thái rõ:

| Judge execution | Verdict | Ý nghĩa |
|---|---|---|
| Thành công | PASS | Judge trả phán quyết đạt hợp lệ |
| Thành công | FAIL | Judge trả phán quyết không đạt hợp lệ |
| Output không hợp đồng | INVALID | Chưa có verdict hợp lệ |
| Timeout/429/5xx | ERROR | Chưa hoàn tất việc chấm |

Một trace worker thành công về mặt kỹ thuật không có nghĩa answer PASS; trạng thái evaluation và verdict là dữ liệu khác nhau.

## 13. Bảo mật và giới hạn khi dùng span links

Trace context có thể đi qua HTTP headers, queue metadata và telemetry backend. Link cũng mang theo SpanContext của một nguồn; do đó cần quản lý **ai được phép tạo/đọc các quan hệ này**.

| Rủi ro | Cách xử lý |
|---|---|
| Caller bên ngoài gửi traceparent giả | Xử lý ở trust boundary theo policy; không dùng làm authentication |
| Payload chứa trace/span ID không đáng tin | Chỉ lấy context từ propagator/carrier đã kiểm soát; validate SpanContext |
| Baggage mang email/API key | Allowlist và loại bỏ trước egress |
| Link attributes chứa prompt/document text | Chỉ dùng metadata ít nhạy cảm |
| Batch link quá nhiều nguồn | Giới hạn kích thước, chia batch và lưu provenance trong result store |
| Trace nguồn đã hết retention | Link vẫn có thể tồn tại nhưng không mở được nguồn; lưu business correlation độc lập |
| Tenant A dò trace của tenant B | Phân quyền trace backend và result store theo tenant/run |
| Metric label chứa trace ID | Không dùng ID duy nhất làm metric label |

### 13.1. Không dùng link để vượt qua trust boundary

Một span link hợp lệ về cấu trúc chỉ cho biết có một SpanContext. Nó không chứng minh span nguồn đến từ một service đáng tin, cũng không cấp quyền truy cập dữ liệu nguồn. Nếu nhận context từ bên ngoài, gateway cần quyết định có tiếp tục context đó hay tạo trace mới; không dùng nó để chọn tenant, đọc memory hay mở result artifact.

### 13.2. Link có thể trỏ tới span không còn xem được

Trace backend có thể sampling hoặc retention khác nhau giữa T1 và T2. Worker T2 còn link tới T1 nhưng T1 đã bị xóa hoặc không được lưu. Đây không nhất thiết là lỗi tạo link. Hãy giữ `answerId`, `runId`, `caseId` và provenance trong result store theo retention phù hợp để điều tra khi trace gốc không còn.

## 14. Kiểm thử parent–child và span links

Kiểm thử phải xác nhận **ngữ nghĩa quan hệ**, không chỉ xác nhận có span cùng tên. Dùng fake worker và in-memory span exporter trong integration test; không cần gọi LLM thật để kiểm tra parent IDs hoặc links.

### 14.1. Ma trận kiểm thử

| ID | Kịch bản | Assertion |
|---|---|---|
| `TRACE-REL-01` | RAG đồng bộ trong HTTP request | RAG span cùng trace, parent là operation phù hợp |
| `TRACE-REL-02` | Async task được await trong request | Child span giữ trace context qua executor |
| `TRACE-REL-03` | Fire-and-forget sau response | Job có trace riêng và link tới nguồn theo policy |
| `TRACE-REL-04` | Worker nhận message context | Consumer dùng parent hoặc link đúng một mô hình |
| `TRACE-REL-05` | Batch nhận 3 message từ 3 traces | Batch span có links tới cả 3 source contexts |
| `TRACE-REL-06` | Source context invalid | Không tạo link giả; worker vẫn theo policy |
| `TRACE-REL-07` | Link được thêm trước startSpan | Sampler có thể quan sát links |
| `TRACE-REL-08` | Link được thêm sau khi span start | Test không kỳ vọng thay đổi head sampling |
| `TRACE-REL-09` | Judge retry trong một worker invocation | Attempts là child spans của worker |
| `TRACE-REL-10` | Queue redelivery thành invocation mới | Trace/attempt mới, cùng business event key |
| `TRACE-REL-11` | Two cases chạy song song | Không trộn parent context |
| `TRACE-REL-12` | Parent span kết thúc trước detached job | Job vẫn có trace độc lập và link |
| `TRACE-REL-13` | Sampling một phần | Result counts không phụ thuộc số traces được giữ |
| `TRACE-REL-14` | Baggage có secret giả | Secret không xuất hiện trong spans/links |
| `TRACE-REL-15` | Answer trace bị retention xóa | Result store vẫn tra cứu provenance bằng business IDs |

### 14.2. Assertion parent–child

Với test exporter, lấy các spans được export và kiểm tra:

```text
parentSpan.traceId == childSpan.traceId
childSpan.parentSpanId == parentSpan.spanId
childSpan.spanId != parentSpan.spanId
```

Nếu có HTTP client/server instrumentation trung gian, parent của server span có thể là client span chứ không phải business span. Test nên xác định đúng **span trực tiếp trước ranh giới service**, không so nhầm với root.

### 14.3. Assertion span link

```text
workerSpan.traceId != answerSpan.traceId       # nếu worker là trace mới
workerSpan.parentSpanId is empty/root          # không có parent answer
workerSpan.links contains answerSpan.context
workerSpan.links.count == expected source count
```

Nếu worker span được tạo trong một trace khác, trace IDs khác nhau là điều mong đợi. Nếu nó cùng trace nhưng link tới một span khác, link vẫn có thể hợp lệ, song cần xem có thực sự cần link thay vì parent–child hay không. Không chỉ assert trace ID khác nhau rồi kết luận mọi thứ đúng.

### 14.4. Test exporter không phải live quality test

In-memory exporter/fake tracer kiểm tra cấu trúc spans, parent, links, attributes và lỗi. Nó không xác minh:

- Judge có chấm đúng factuality hay không.
- Retriever có trả nguồn liên quan hay không.
- Model thật có chọn tool đúng hay không.
- Provider thực tế tính token/cost ra sao.

Các câu hỏi chất lượng cần golden dataset, verified facts, tool trace expectations và evaluation với model thật theo ngân sách. Không trộn kết quả kỹ thuật của instrumentation với quality verdict.

## 15. Phân tích trace khi async evaluation bị lỗi

Giả sử một answer API trả thành công, event vào queue và judge worker timeout:

```text
TRACE T1: answer-api
SERVER POST /api/answers
└── app.ai.answer
    ├── app.rag.retrieve
    ├── chat.model.call
    └── answer.persist

TRACE T2: judge-worker
app.ai.evaluation.process
  link -> answer.persist in T1
  ├── judge.attempt-1: TIMEOUT
  ├── judge.attempt-2: HTTP 429
  └── evaluation.result.persist: ERROR
```

Kết quả:

- HTTP answer API có thể là 2xx; answer đã được tạo.
- RAG/model spans ở T1 cho biết source IDs, prompt/model version, latency và token.
- T2 cho biết worker được tạo từ answer nào và judge đã thử bao nhiêu lần.
- Evaluation result là ERROR vì chưa có verdict hợp lệ.
- Release gate không được tự coi case này PASS; phải tính valid coverage và retry/defer theo policy.

### 15.1. Khi worker có trace riêng nhưng không tìm thấy trace nguồn

Kiểm tra theo thứ tự:

1. Message headers có chứa tracing context khi producer publish không?
2. Producer inject context lúc span nguồn còn active hay sau khi context đã đóng/mất?
3. Consumer có extract đúng carrier và propagator không?
4. Worker có gọi `setNoParent()` rồi thêm link trước `startSpan()` không?
5. Trace backend có lưu cả hai traces và hiển thị links không?
6. Retention/sampling có làm trace nguồn không còn truy vấn được không?
7. Result store có `answerId`, `answerTraceId`, `runId` và `caseId` để tra cứu dự phòng không?

Không khắc phục bằng cách gán `answerTraceId` thành `parentSpanId`; hai ID có định dạng/ý nghĩa khác nhau.

### 15.2. Khi worker bị gắn nhầm làm child của request

Nếu HTTP root kết thúc ngay sau khi enqueue nhưng worker span vẫn là child:

- Có thể context được capture từ producer và consumer tiếp tục cùng trace.
- Đây không tự động là sai, nếu mô hình messaging muốn một trace nhân quả liên tục.
- Nếu job có lifecycle độc lập, retry dài, batch/fan-in hoặc cần sampling riêng, cân nhắc root trace mới + link.
- Đừng sửa bằng cách xóa propagation hoàn toàn; vẫn cần link hoặc business correlation để giữ provenance.

## 16. Bài thực hành: thiết kế trace cho answer và judge worker

**Bối cảnh:** Một ứng dụng Spring AI nhận câu hỏi, truy xuất PGvector, gọi ChatClient và trả answer. Sau đó queue gửi event tới worker để chấm relevance, groundedness và fact checking. Dataset có nhiều cases, có retry và có batch report.

### Phần A — Quyết định quan hệ

1. Vẽ trace T1 cho HTTP answer: retrieval, model, tool (nếu có) và persist là các child operations.
2. Xác định judge worker chạy trước hay sau HTTP response; nếu sau response, tạo một trace/job độc lập.
3. Quyết định dùng message context làm parent hay dùng root mới + link; ghi lý do theo lifecycle và ownership.
4. Với batch chấm nhiều answers, tạo một root batch span và links tới các answer spans.
5. Giữ `runId`, `caseId`, `variant`, `rubricVersion`, `answerId` làm business correlation.

### Phần B — Implement propagation và links

1. Bật một tracing SDK thống nhất qua Micrometer/OTel theo version Spring Boot đã khóa.
2. Dùng propagator inject context vào queue headers tại producer.
3. Consumer extract context; kiểm tra SpanContext hợp lệ trước khi tạo link.
4. Dùng `SpanBuilder.setNoParent().addLink(...).startSpan()` cho detached worker.
5. Nếu task ngắn được await, dùng context propagation executor và child span thay vì link.

### Phần C — Retry, batch và idempotency

1. Mô phỏng judge timeout rồi HTTP 503 rồi thành công; attempts là child spans dưới worker invocation.
2. Mô phỏng queue redelivery; invocation mới có trace riêng hoặc parent theo policy, nhưng cùng event ID.
3. Chạy batch có ba answer traces; assert batch span có ba links.
4. Đảm bảo unique final result key không ghi đúp verdict.
5. Không retry một FAIL hợp lệ chỉ để tìm PASS.

### Phần D — Kiểm tra và điều tra

1. Dùng in-memory exporter kiểm tra trace IDs, parent IDs và links.
2. Cho worker nhận header thiếu/invalid; không tạo link giả và vẫn giữ event theo policy.
3. Chạy A/B trên cùng dataset/rubric; lưu answerTraceId/judgeTraceId và prompt/model/index versions.
4. Khi judge ERROR, xác minh answer trace vẫn tra cứu được và valid coverage giảm đúng.
5. Khi sampling giảm, xác minh metrics/result store vẫn ghi toàn bộ cases.

### Câu hỏi tự kiểm tra

**1. Một task chạy trên thread khác nhưng caller chờ Future trước khi trả HTTP response. Nên dùng link hay child span?**  
Thường dùng child span. Task là một phần của operation cha; cần propagate context sang executor. Thread khác không tự biến công việc thành operation độc lập.

**2. Worker chấm answer sau khi HTTP request đã kết thúc. Vì sao thường tạo trace riêng và link?**  
Worker có lifecycle, retry và sampling độc lập; giữ HTTP span mở sẽ làm latency request sai nghĩa. Link bảo toàn quan hệ tới answer nguồn mà không kéo dài trace gốc.

**3. Một batch chấm 50 answers từ 50 traces. Có thể chọn request đầu làm parent không?**  
Không nên, vì nó làm sai ownership và bỏ mất 49 nguồn còn lại. Tạo batch root và links tới các source spans; lưu đầy đủ correlation trong result store.

**4. Chỉ có answerTraceId, có thể gọi addLink bằng ID đó không?**  
Không. Link cần SpanContext hợp lệ, tối thiểu trace ID và span ID cùng trace state/flags; cần extract từ carrier hoặc lấy từ nguồn lưu trữ đáng tin.

**5. Worker root span có link tới answer span, vậy nó sẽ tự được sample nếu answer span được sample không?**  
Không. Link không tự kế thừa sampled decision của parent; root span áp dụng sampler của chính nó. Có thể dùng tail sampling hoặc policy nhận biết links nếu hạ tầng hỗ trợ.

**6. Judge timeout hai lần rồi PASS ở lần ba. Có thể bỏ hai attempts lỗi không?**  
Không. Cần giữ lịch sử attempts, latency và usage/chi phí nếu biết; final verdict PASS chỉ hợp lệ khi attempt cuối trả phán quyết hợp lệ theo policy.

## 17. Những sai lầm cần tránh

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Mọi async task đều dùng span link | Cây trace của task được await bị đứt | Dùng child nếu thuộc operation cha |
| Mọi background job đều là child HTTP | HTTP trace kéo dài/ownership sai | Trace riêng + link khi job độc lập |
| Dùng link để chữa context propagation bị mất | Che lỗi instrumentation | Khôi phục parent context đúng |
| Chọn một request làm parent cho batch nhiều nguồn | Mất provenance và sai quan hệ | Batch root + nhiều links |
| Chỉ lưu trace ID, không có span ID | Không tạo được link chính xác | Lưu/extract SpanContext |
| Tạo link sau startSpan rồi kỳ vọng head sampler dùng nó | Sampling decision đã xảy ra | Add links trước startSpan |
| Nghĩ link làm hai trace thành một | Hiểu sai trace tree | Link chỉ là quan hệ liên kết |
| Nghĩ link kế thừa sampled flag của nguồn | Worker có thể bị sampling độc lập | Sampling policy riêng/tail sampling |
| Dùng trace ID làm idempotency key | Retry/redelivery ghi đè hoặc đếm sai | Business key + attempt/delivery IDs |
| Không phân biệt retry và redelivery | Mất lịch sử execution | Worker invocation và attempt spans rõ |
| Tự tạo SDK/tracer thứ hai để addLink | Trace pipeline phân mảnh | Dùng chung tracing SDK/bridge |
| Inject/extract message context hai lần | Parent/link trùng và khó debug | Một instrumentation owner |
| Tin baggage/trace header để xác thực | Rủi ro vượt quyền | Authentication độc lập |
| Dùng pass rate từ traces đã sample | Sai mẫu số evaluation | Result store/metrics độc lập sampling |
| Coi judge ERROR là PASS | Thổi phồng chất lượng | ERROR/INVALID và coverage riêng |

## 18. Ghi nhớ

- **Parent–child** mô tả operation con thuộc vòng đời và trách nhiệm của operation cha; mỗi span chỉ có một parent.
- **Span link** mô tả quan hệ tới một hoặc nhiều spans khác mà không gộp chúng vào cùng trace tree.
- **Async không tự quyết định quan hệ:** task ngắn được await có thể là child; job độc lập sau response thường phù hợp trace riêng + link.
- **Fan-in/batch nhiều nguồn** là trường hợp điển hình cho một span có nhiều links, vì một span không thể có nhiều parents.
- **SpanContext đầy đủ** cần để tạo link; chỉ một trace ID trong payload không đủ.
- **OpenTelemetry SpanBuilder** cho phép thêm links trước `startSpan()`; điều này quan trọng nếu sampler cần xem links.
- **Micrometer Observation** hữu ích cho operation thông thường; với links, dùng API tương thích trên cùng tracing SDK hoặc instrumentation messaging đã hỗ trợ.
- **Queue producer inject, consumer extract** context qua propagator; chọn parent hoặc link theo semantic convention/lifecycle và tránh instrument trùng.
- **Retry, redelivery và replay** cần trace/attempt rõ cùng idempotency key nghiệp vụ; không retry FAIL hợp lệ để tìm PASS.
- **Sampling độc lập với evaluation coverage:** metrics và result store phải ghi toàn bộ cases, dù traces chỉ được lấy mẫu.
- **Trace links không thay authentication, authorization, business correlation hay result provenance.**
- **Quality verdict không phải span status:** HTTP/model/worker span OK không chứng minh relevance, groundedness, fact checking hoặc tool accuracy PASS.

Phân biệt đúng span cha–con với span link giúp một hệ thống Spring AI biểu diễn cả **luồng xử lý bên trong request** lẫn **công việc độc lập được kích hoạt từ request đó**. Khi answer trace, RAG/tool spans và async judge traces được liên kết theo đúng ngữ nghĩa, nhóm phát triển có thể lần ngược nguồn của từng kết quả, giữ đúng lifecycle, kiểm soát retry/sampling và giải thích biến động chất lượng, độ trễ, token cùng chi phí qua từng phiên bản prompt, model và pipeline.
