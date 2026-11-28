# Trace bị tách khi đổi thread, dùng executor hoặc SDK streaming

> **Chương:** Chẩn đoán sự cố  
> **Module:** SPRING_AI_EVALUATION_OBSERVABILITY — đánh giá chất lượng ứng dụng Spring AI bằng tập dữ liệu, tiêu chí relevance, fact checking và kiểm thử luồng RAG hoặc gọi công cụ; đồng thời đo metrics, traces, chi phí và độ trễ để phát hiện nguyên nhân suy giảm qua từng phiên bản prompt, model và pipeline.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vì sao trace context gắn với execution context và có thể bị mất khi code chuyển thread.
2. Phân biệt Reactor Context, ThreadLocal, Observation scope và distributed trace context.
3. Cấu hình Micrometer Context Propagation và Spring TaskDecorator cho executor.
4. Truyền context qua CompletableFuture, @Async, Reactor và SDK callback/streaming.
5. Quản lý vòng đời Observation/span theo thời gian hoàn tất thực tế của tác vụ bất đồng bộ.
6. Chẩn đoán trace ID bị đổi, span con thành root span hoặc span bị thiếu ở nhánh streaming.
7. Viết kiểm thử để xác nhận trace ID, parent span, error, completion và cancellation qua các ranh giới bất đồng bộ.

## 1. Triệu chứng: một request nhưng thành nhiều trace

Một API RAG nhận câu hỏi, gọi embedding, truy xuất VectorStore rồi stream câu trả lời. Ở trace backend, người vận hành thấy:

- HTTP request có trace A.
- Span truy xuất VectorStore lại có trace B.
- Callback của model streaming xuất hiện thành trace C hoặc không có trace.
- Một số chunk có span, chunk khác không.
- Root span kết thúc trước khi stream hoàn tất.
- Trace chỉ có một phần hoạt động sau khi dùng CompletableFuture hoặc @Async.

Các triệu chứng này thường xuất hiện khi execution chuyển sang thread khác, một SDK gọi callback trên thread nội bộ hoặc một publisher reactive phát signal sau khi method tạo publisher đã trả về.

Nguyên nhân gốc thường là context propagation hoặc vòng đời Observation không khớp với vòng đời tác vụ.

**Trace context không tự động đi theo mọi thread.** Nhiều tracing integration lưu current span trong ThreadLocal; khi code chạy ở thread khác, ThreadLocal của thread mới có thể trống hoặc chứa context khác.

### 1.1. Đường đi có thể bị đứt

~~~mermaid
flowchart TD
  A["HTTP request: Trace A"] --> B["RAG service / Observation"]
  B --> C["Thread T1"]
  C --> D["Submit task"]
  D --> E["Executor thread T2"]
  E --> F{"Context restored?"}
  F -->|Yes| G["Child span in Trace A"]
  F -->|No| H["New root / no parent"]
  G --> I["VectorStore / Embedding"]
  H --> I
  B --> J["SDK streaming call"]
  J --> K["SDK callback thread T3"]
  K --> L{"Snapshot / Reactor context?"}
  L -->|Yes| M["Callback stays in Trace A"]
  L -->|No| N["Detached callback"]
  M --> O["Chunk / completion"]
  N --> O
~~~

Nếu context được truyền đúng, span tạo trên thread T2/T3 vẫn có cùng Trace ID và parent relationship phù hợp. Nếu context mất, tracing library có thể tạo root span mới hoặc chỉ ghi log mà không có span cha.

### 1.2. Dấu hiệu nhận biết

| Dấu hiệu | Khả năng cần kiểm tra |
|---|---|
| Trace ID đổi ngay sau submit executor | Không capture/restore context tại executor |
| Span con có Trace ID đúng nhưng không có parent như mong đợi | Parent scope đã đóng, tạo span ở sai thời điểm hoặc dùng link thay vì parent |
| Chỉ mất span trong CompletableFuture | Dùng common pool hoặc stage async không có executor đã instrument |
| @Async tách trace | Executor của @Async chưa có TaskDecorator/context propagation |
| Reactor đổi thread nhưng trace vẫn liền mạch ở vài operator | Reactor Context được giữ, nhưng ThreadLocal accessor hoặc automatic propagation có thể thiếu |
| Spring AI stream có root span nhưng thiếu chunk callbacks | SDK callback chạy ngoài context hoặc span kết thúc quá sớm |
| Root span kết thúc ngay khi trả Flux/CompletableFuture | Dùng Observation đồng bộ quanh thao tác tạo publisher/future |
| Callback error không gắn với trace ban đầu | Error handler chạy ở thread khác hoặc context snapshot không được dùng |

## 2. Hiểu đúng các loại context

### 2.1. ThreadLocal

ThreadLocal giữ một giá trị riêng trên từng thread. Nó hữu ích cho code đồng bộ vì current observation/span có thể được truy cập từ thread hiện tại.

Nhưng ThreadLocal không phải một cơ chế truyền dữ liệu giữa thread:

~~~text
Thread T1:
  currentTrace = Trace A
  executor.submit(task)

Thread T2:
  currentTrace = null
~~~

Thread pool còn làm vấn đề khó phát hiện hơn: thread được tái sử dụng, nên nếu context không được restore/clear đúng cách, một tác vụ có thể thấy context cũ của tác vụ trước. Context propagation phải vừa khôi phục context phù hợp, vừa dọn trạng thái sau khi callback kết thúc.

### 2.2. Observation và Observation.Scope

Observation mô tả một operation. Khi mở scope, Observation trở thành current context trên thread hiện tại:

~~~java
Observation observation =
        Observation.createNotStarted("app.rag.retrieve", registry);

observation.start();
try (Observation.Scope scope = observation.openScope()) {
    // Code đồng bộ chạy trong scope của observation.
    retrieve();
}
finally {
    observation.stop();
}
~~~

Scope có tính chất gắn với thread đang mở nó. Không mở scope trên T1 rồi đóng scope đó trên T2. Không giữ một scope mở qua thời gian chờ callback hoặc qua ranh giới async mà không dùng cơ chế context propagation phù hợp.

Observation có thể sống lâu hơn một đoạn scope: operation có thể bắt đầu, scope trên thread khởi tạo đóng lại, callback sau đó mở lại context đã capture khi xử lý signal. Việc start/stop Observation phải theo lifecycle thật của operation.

### 2.3. Reactor Context

Reactor Context là context bất biến đi cùng reactive subscription, không phải ThreadLocal. Nó có thể tiếp tục tồn tại khi publisher chuyển giữa scheduler/thread.

Một pipeline có thể giữ Reactor Context nhưng code thư viện cũ chỉ đọc ThreadLocal vẫn không thấy context nếu không có cầu nối. Micrometer Context Propagation cung cấp cơ chế accessor để capture/restore các giá trị giữa ThreadLocal và Reactor Context.

### 2.4. Distributed trace context

Khi request đi qua HTTP/gRPC hoặc message broker sang process khác, context cần được inject/extract qua carrier, ví dụ W3C Trace Context với traceparent/tracestate. Chuyển ThreadLocal trong một process không thay thế distributed propagation giữa service.

Không tự truyền một chuỗi Trace ID làm business attribute rồi coi đó là tracing đầy đủ. Cần giữ trace ID, span ID, sampled flag và quan hệ parent/span theo propagator chuẩn.

## 3. Quy tắc quan trọng với tác vụ bất đồng bộ

Có hai lỗi phổ biến khi bọc code async bằng Observation.

### 3.1. Đừng dùng Observation đồng bộ quanh việc tạo Future

Ví dụ sai về lifecycle:

~~~java
return observation.observe(() ->
        CompletableFuture.supplyAsync(this::retrieve, executor));
~~~

Observation.observe() kết thúc khi lambda trả về đối tượng CompletableFuture. Công việc retrieve có thể vẫn chưa bắt đầu hoặc chưa hoàn tất. Kết quả là span cha đóng sớm, còn child work chạy ngoài scope.

Cách đúng là dùng executor có context propagation và quản lý Observation/span theo completion của Future, hoặc dùng instrumentation reactive/async đã được framework hỗ trợ. Không kết luận rằng chỉ thêm TaskDecorator đã tự kéo dài lifecycle của mọi Observation; decorator truyền context cho task, còn code vẫn phải quản lý start/stop đúng thời điểm.

### 3.2. Đừng giữ Observation.Scope mở trên thread khởi tạo

Ví dụ sai:

~~~java
Observation.Scope scope = observation.openScope();
executor.execute(() -> {
    try {
        retrieve();
    }
    finally {
        scope.close(); // Scope được mở trên thread khác.
    }
});
~~~

Scope phải được mở/đóng đúng thread. Dùng context snapshot hoặc TaskDecorator để callback khôi phục scope trong thread thực thi; không chuyển đối tượng Scope giữa các thread.

### 3.3. Quản lý ba mốc riêng

| Mốc | Ý nghĩa |
|---|---|
| Submit | Tác vụ được gửi tới executor/SDK |
| Execute | Tác vụ bắt đầu trên thread thực thi |
| Terminal | Tác vụ hoàn tất, lỗi hoặc bị hủy |

Parent Observation thường cần bao trọn khoảng operation theo semantics của ứng dụng. Child Observation cần mở trong thread thực thi. Nếu task bị reject trước khi chạy, cần xử lý lỗi submit/rejection; nếu task bị cancel, cần kết thúc lifecycle theo quy ước đã chọn.

## 4. Truyền context qua Executor với Spring TaskDecorator

Với Spring Framework hỗ trợ Micrometer Context Propagation, có thể dùng ContextPropagatingTaskDecorator cho executor do Spring quản lý.

### 4.1. Cấu hình ThreadPoolTaskExecutor

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
class RagAsyncConfiguration {
    @Bean("ragExecutor")
    ThreadPoolTaskExecutor ragExecutor() {
        var executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(12);
        executor.setQueueCapacity(200);
        executor.setThreadNamePrefix("rag-worker-");
        executor.setTaskDecorator(
                new ContextPropagatingTaskDecorator());
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(20);
        return executor;
    }
}
~~~

TaskDecorator capture/restore context theo cơ chế Micrometer Context Propagation mà Spring tích hợp. Class này có từ các phiên bản Spring Framework tương ứng với hệ sinh thái Spring Boot mới; kiểm tra version Spring Framework/Spring Boot thực tế và dependency context-propagation.

Không tạo executor không giới hạn. Core/max size, queue capacity và shutdown policy phải phù hợp tải; queue quá lớn có thể làm request chờ lâu và tăng memory.

### 4.2. Dùng executor tường minh trong CompletableFuture

~~~java
import java.util.List;
import java.util.concurrent.CompletableFuture;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.task.TaskExecutor;
import org.springframework.stereotype.Service;

@Service
class AsyncRetrievalService {
    private final TaskExecutor ragExecutor;

    AsyncRetrievalService(
            @Qualifier("ragExecutor") TaskExecutor ragExecutor) {
        this.ragExecutor = ragExecutor;
    }

    CompletableFuture<RetrievalResult> retrieveAsync(String question) {
        return CompletableFuture.supplyAsync(
                () -> retrieveSynchronously(question),
                ragExecutor);
    }

    private RetrievalResult retrieveSynchronously(String question) {
        // Gọi EmbeddingModel / VectorStore theo luồng đồng bộ.
        return new RetrievalResult(List.of());
    }
}
~~~

Đoạn code minh họa executor được cấu hình TaskDecorator. Ví dụ cần định nghĩa RetrievalResult trong ứng dụng thật.

Điểm quan trọng:

- Luôn truyền executor đã cấu hình vào supplyAsync/thenApplyAsync/thenComposeAsync.
- Tránh overload không nhận executor vì nó thường dùng ForkJoinPool.commonPool().
- Mỗi async stage có thể chạy trên thread khác; stage dùng async variant cần executor phù hợp.
- Stage không có async variant thường chạy trên thread hoàn tất stage trước đó; không dựa vào đó để giả định thread cố định.
- TaskDecorator chỉ áp dụng cho task đi qua executor được trang bị decorator.

### 4.3. Dùng @Async

~~~java
import java.util.List;
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
class AsyncVectorStoreService {
    @Async("ragExecutor")
    public CompletableFuture<RetrievalResult> retrieve(String question) {
        return CompletableFuture.completedFuture(
                performRetrieval(question));
    }

    private RetrievalResult performRetrieval(String question) {
        return new RetrievalResult(List.of());
    }
}
~~~

Ứng dụng cần bật async support theo cấu hình Spring tương ứng. Phương thức được gọi qua Spring proxy mới được @Async intercept; self-invocation trong cùng bean có thể không đi qua proxy. Executor ragExecutor phải là executor đã cài TaskDecorator.

### 4.4. Các lỗi khi dùng TaskDecorator

- Decorator gắn vào executor khác với executor thực sự được dùng.
- Code vẫn gọi commonPool.
- Custom executor được tạo ngoài Spring và không dùng decorator.
- Context accessor không được đăng ký hoặc dependency Micrometer context-propagation thiếu.
- Task được submit trước khi Observation scope mở.
- Scope bị đóng trước khi capture context.
- Callback tự tạo thread mới sau executor; thread mới đó cần cơ chế propagation riêng.

## 5. Micrometer Context Propagation API

Khi không thể dùng Spring TaskDecorator hoặc SDK có callback riêng, có thể capture context và wrap task bằng Micrometer Context Propagation.

### 5.1. Capture và restore

Ví dụ minh họa:

~~~java
import java.util.concurrent.Executor;
import io.micrometer.context.ContextRegistry;
import io.micrometer.context.ContextSnapshot;
import io.micrometer.context.ContextSnapshotFactory;

public final class ContextAwareSubmitter {
    private final ContextSnapshotFactory snapshots =
            ContextSnapshotFactory.builder()
                    .contextRegistry(ContextRegistry.getInstance())
                    .build();

    public void submit(Executor executor, Runnable task) {
        ContextSnapshot snapshot = snapshots.captureAll();
        executor.execute(snapshot.wrap(task));
    }
}
~~~

Capture phải diễn ra khi context nguồn đang hiện diện trên thread gọi. snapshot.wrap(task) tạo task khôi phục context khi chạy và dọn context theo contract của library. API và cách đăng ký accessor có thể khác theo version Micrometer Context Propagation; kiểm tra Javadoc/dependency đang dùng.

### 5.2. Chỉ capture context cần thiết

Context có thể bao gồm observation, tracing, security hoặc dữ liệu request. Không nên truyền toàn bộ ThreadLocal tùy tiện:

- Chỉ đăng ký accessor cho context có mục đích rõ ràng.
- Không đưa raw prompt, document hoặc credential vào baggage.
- Không dùng ThreadLocal chứa mutable request object để truyền giữa nhiều task song song.
- Không giữ ContextSnapshot lâu hơn vòng đời cần thiết.
- Đảm bảo context được restore và cleanup khi task thành công, lỗi hoặc bị cancel.

### 5.3. Không copy Trace ID thủ công

Ví dụ sau không thay thế context propagation:

~~~java
executor.execute(() -> {
    log.info("traceId={}", capturedTraceId);
    retrieve();
});
~~~

Log có thể in đúng Trace ID nhưng retrieve() vẫn không có current span/parent context. Kết quả là trace backend vẫn tách. Hãy dùng propagator/snapshot để khôi phục trace context thật, không chỉ gắn ID vào log.

## 6. Reactor và Spring AI streaming

Reactor xử lý bất đồng bộ bằng subscription và Reactor Context. Pipeline có thể chuyển thread qua publishOn/subscribeOn mà vẫn giữ Reactor Context, nhưng ThreadLocal-based instrumentation cần cầu nối phù hợp.

### 6.1. Reactor Context khác ThreadLocal

~~~mermaid
flowchart TD
  A["Subscriber / request"] --> B["Reactor Context"]
  B --> C["map / flatMap"]
  C --> D["publishOn scheduler"]
  D --> E["Worker thread changes"]
  E --> F["Context restored for operator"]
  F --> G["Micrometer / tracing instrumentation"]
~~~

Reactor Context đi cùng subscription. ThreadLocal chỉ thuộc thread. Một operator có thể chạy trên thread khác nhưng vẫn truy cập Reactor Context; code chỉ đọc ThreadLocal cần context propagation bridge để thấy current observation/span.

### 6.2. Automatic context propagation

Trong các phiên bản Reactor/Micrometer hỗ trợ, có thể bật automatic context propagation:

~~~java
import jakarta.annotation.PostConstruct;
import org.springframework.context.annotation.Configuration;
import reactor.core.publisher.Hooks;

@Configuration
class ReactorContextConfiguration {
    @PostConstruct
    void enableContextPropagation() {
        Hooks.enableAutomaticContextPropagation();
    }
}
~~~

Đây là hook toàn cục cho Reactor trong JVM và cần bật sớm trước khi tạo subscriptions cần được propagate. Kiểm tra Reactor version, Micrometer Context Propagation và framework auto-configuration; nếu Spring Boot đã cấu hình chế độ này thì không thêm hook lần nữa một cách tùy tiện.

Automatic propagation có thể thêm overhead cho operator. Kiểm tra hiệu năng và chỉ dùng với phiên bản đã được xác minh tương thích.

### 6.3. Spring AI ChatClient streaming

Ví dụ stream nội dung:

~~~java
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.scheduler.Scheduler;

@Service
class StreamingAnswerService {
    private final ChatClient chatClient;
    private final Scheduler ragScheduler;

    StreamingAnswerService(ChatClient chatClient, Scheduler ragScheduler) {
        this.chatClient = chatClient;
        this.ragScheduler = ragScheduler;
    }

    Flux<String> answerStream(String question) {
        return chatClient.prompt()
                .user(question)
                .stream()
                .content()
                .publishOn(ragScheduler)
                .doOnNext(this::processChunk)
                .doOnError(this::recordSafeFailure)
                .doFinally(signal -> recordTerminalSignal(signal.name()));
    }

    private void processChunk(String chunk) {
        // Xử lý chunk theo policy; tránh log nội dung nhạy cảm.
    }

    private void recordSafeFailure(Throwable error) {
        // Ghi error category, không log raw prompt/response.
    }

    private void recordTerminalSignal(String signal) {
        // Ghi complete/error/cancel bằng giá trị hữu hạn.
    }
}
~~~

Ví dụ giả định ChatClient streaming API trả về Flux và ứng dụng đã cấu hình ChatClient/Scheduler. Spring AI có thể tự instrument ChatClient/ChatModel theo phiên bản. Context propagation qua publishOn cần Reactor/Micrometer integration phù hợp.

**Trả Flux về cho tầng web/subscriber thay vì tự gọi subscribe() bên trong service.** Khi service tự subscribe, nó tách lifecycle khỏi caller, làm khó cancellation, error propagation và trace parent relationship.

### 6.4. Không kết thúc span khi mới tạo Flux

Một Flux là mô tả publisher; công việc có thể chỉ chạy khi có subscription và tiếp tục phát nhiều signal sau đó. Nếu bọc việc tạo Flux bằng Observation.observe() đồng bộ, Observation có thể dừng ngay khi publisher được trả về.

Ưu tiên instrumentation reactive-aware của framework. Nếu cần custom Observation cho một stream, phải gắn lifecycle vào subscription và terminal signal:

- Start khi subscription bắt đầu.
- Propagate context qua các operator.
- Record error nếu stream lỗi.
- Stop khi complete, error hoặc cancel.
- Đảm bảo stop đúng một lần.

Không giữ Observation.Scope mở trong suốt stream trên một thread; stream có thể chạy trên nhiều thread và kéo dài lâu.

### 6.5. subscribeOn và publishOn

| Operator | Tác động |
|---|---|
| subscribeOn(scheduler) | Chuyển nơi subscription/source thực thi |
| publishOn(scheduler) | Chuyển nơi các operator downstream xử lý signal |
| flatMap(async publisher) | Có thể chạy nhiều nhánh đồng thời |
| parallel/runOn | Phân phối xử lý trên nhiều worker |

Khi thêm scheduler/operator, kiểm tra trace ID ở trước và sau ranh giới. Đừng giả định một thread duy nhất xử lý cả stream.

## 7. SDK streaming callback chạy trên thread nội bộ

Một số model/provider SDK không trả Flux trực tiếp. SDK có thể nhận callback:

- onChunk khi có token/chunk.
- onError khi stream lỗi.
- onComplete khi kết thúc.
- onCancel khi caller hủy hoặc connection đóng.

SDK có thể gọi các callback trên thread do chính SDK quản lý. Context của request ban đầu không tự động có mặt trên những thread đó.

### 7.1. Capture context trước khi đăng ký callback

Ví dụ khái niệm với Micrometer Context Propagation:

~~~java
ContextSnapshot snapshot = snapshotFactory.captureAll();

Consumer<Chunk> onChunk = chunk ->
        snapshot.wrap(() -> processChunk(chunk)).run();

Consumer<Throwable> onError = error ->
        snapshot.wrap(() -> recordSafeFailure(error)).run();

Runnable onComplete = snapshot.wrap(this::finishStream);

vendorSdk.startStream(request, onChunk, onError, onComplete);
~~~

Đây là adapter pattern minh họa; kiểu callback và method startStream phụ thuộc SDK cụ thể. Capture snapshot trong khi parent Observation/trace context còn current. Mỗi callback được wrap để restore context trên thread SDK sử dụng.

### 7.2. Lifecycle của stream

Nếu tạo một Observation cha riêng cho SDK stream, cần:

1. Tạo và start Observation trước khi khởi động SDK stream.
2. Mở scope trên thread khởi tạo để capture đúng parent context.
3. Capture ContextSnapshot trước khi gọi SDK.
4. Wrap callback chunk/error/complete/cancel bằng snapshot.
5. Ghi error/status theo policy, không đưa exception message nhạy cảm vào span.
6. Stop Observation đúng một lần ở terminal callback.
7. Xử lý trường hợp SDK từ chối request đồng bộ trước khi stream bắt đầu.
8. Xử lý timeout/cancellation để Observation không bị treo vô hạn.

Nếu callback có thể chạy song song, đồng bộ việc cập nhật state và đảm bảo terminal event chỉ kết thúc span một lần. Có thể dùng AtomicBoolean hoặc một state machine phù hợp.

### 7.3. Pseudocode lifecycle an toàn

~~~java
Observation streamObservation =
        Observation.createNotStarted("app.model.stream", registry);

streamObservation.start();

try (Observation.Scope scope = streamObservation.openScope()) {
    ContextSnapshot callbackContext = snapshotFactory.captureAll();
    AtomicBoolean terminated = new AtomicBoolean();

    vendorSdk.startStream(
        request,
        chunk -> callbackContext.wrap(() -> {
            if (!terminated.get()) {
                processChunk(chunk);
            }
        }).run(),
        error -> callbackContext.wrap(() -> {
            if (terminated.compareAndSet(false, true)) {
                streamObservation.lowCardinalityKeyValue(
                        "outcome", "error");
                streamObservation.stop();
            }
            recordSafeFailure(error);
        }).run(),
        () -> callbackContext.wrap(() -> {
            if (terminated.compareAndSet(false, true)) {
                streamObservation.lowCardinalityKeyValue(
                        "outcome", "success");
                streamObservation.stop();
            }
        }).run()
    );
}
catch (RuntimeException startFailure) {
    // Kết thúc Observation nếu SDK từ chối request trước terminal callback.
    streamObservation.lowCardinalityKeyValue(
            "outcome", "start_error");
    streamObservation.stop();
    throw startFailure;
}
~~~

Đây là pseudocode để giải thích lifecycle; thay API callback và state handling theo SDK thật. Trong production, state terminal phải dùng chung cho start/error/complete/cancel. SDK có thể gọi callback đồng bộ ngay trong startStream, callback song song hoặc phát nhiều terminal signals; cần bảo vệ khỏi stop trùng và xử lý cancellation theo hợp đồng SDK.

### 7.4. Cancellation không phải success

Streaming có thể bị hủy khi:

- Người dùng đóng kết nối.
- Client timeout.
- Server hủy subscription.
- Model SDK bị cancel.
- Backpressure hoặc downstream consumer dừng nhận.

Nếu bỏ qua cancellation, span có thể treo đến hết timeout hoặc bị stop như success dù stream chưa hoàn tất. Định nghĩa outcome hữu hạn như success/error/cancelled và bảo đảm terminal callback/cancel handler được nối với Observation lifecycle.

## 8. Message queue và tác vụ tách rời thời gian

Không phải mọi tác vụ async đều nên giữ parent span mở cho tới khi worker hoàn thành.

Ví dụ request RAG tạo job indexing chạy sau vài phút hoặc vài giờ. Khi đó:

- Trace request có thể kết thúc sau khi job được enqueue.
- Worker xử lý job ở thời điểm khác.
- Quan hệ parent-child kéo dài quá lâu có thể không phù hợp retention/timeout của tracing backend.

Trong trường hợp này, inject trace context vào message metadata theo propagator chuẩn. Khi consumer nhận message, có thể tạo consumer span mới và dùng span link tới context producer nếu semantics là công việc tách rời/asynchronous. W3C trace context không nên bị biến thành raw business payload.

### 8.1. Parent-child hay span link?

| Tình huống | Quan hệ thường phù hợp |
|---|---|
| Task ngắn, được submit ngay trong request và là phần của request | Child span với parent context được propagate |
| Message được xử lý độc lập sau thời gian dài | Consumer span mới có link tới producer context |
| Batch gom nhiều message từ nhiều trace | Batch span có thể link tới nhiều producer contexts |
| Scheduled job không bắt nguồn từ request cụ thể | Root span mới với job identity an toàn |

Span links là khả năng của tracing API/SDK; cách biểu diễn qua Micrometer Observation phụ thuộc bridge và version. Nếu cần link, dùng API tracing implementation được hỗ trợ thay vì gán parent sai.

## 9. Chẩn đoán theo trace ID, parent ID và thread

### 9.1. Kiểm tra trước/sau ranh giới

Tạo một fixture request và quan sát:

| Điểm kiểm tra | Trường cần so |
|---|---|
| HTTP entry | trace ID, span ID |
| Trước submit | current trace ID, current span ID |
| Executor task start | trace ID, parent span ID |
| VectorStore call | trace ID, span ID, parent span |
| Streaming callback | trace ID, parent span, callback thread |
| Terminal signal | trace ID, span status, duration |

Không log raw prompt hoặc document. Có thể log opaque trace reference, operation name và thread name ở môi trường được kiểm soát.

### 9.2. Dùng W3C traceparent ở ranh giới service

Header có dạng tổng quát:

~~~text
traceparent: 00-<trace-id>-<parent-id>-<trace-flags>
~~~

Trace ID và parent ID phải được inject/extract bởi propagator. Không tự nối chuỗi header bằng string manipulation nếu đã có tracing instrumentation của HTTP client/server.

Nếu downstream trace ID khác, kiểm tra:

- Header có được gửi không?
- Reverse proxy có xóa header không?
- Client/server propagator có thống nhất W3C/B3 không?
- Downstream có nhận và extract context không?
- Có sampler hoặc instrumentation tạo root mới có chủ đích không?

### 9.3. Thread name chỉ là manh mối

Thread name giúp thấy code đã chuyển executor, nhưng không chứng minh context bị mất. Có thread switch mà trace vẫn liền mạch nếu propagation hoạt động; có thể mất context ngay cả khi thread name không đổi nếu scope bị đóng quá sớm.

## 10. Những lỗi lifecycle và cách xử lý

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Scope mở ở T1, đóng ở T2 | Context corruption hoặc close sai | Mở/đóng scope trong cùng thread |
| Dùng commonPool không propagate | Span con thành root/mất parent | Truyền executor có TaskDecorator |
| Capture snapshot sau khi parent scope đóng | Snapshot không chứa parent context | Capture khi context nguồn còn current |
| Observation.observe() bọc việc tạo Future | Span kết thúc quá sớm | Stop theo Future completion/error/cancel |
| Observation.observe() bọc việc tạo Flux | Span kết thúc trước subscription | Dùng reactive-aware instrumentation/lifecycle |
| Callback SDK chạy trên thread riêng | Không thấy current span | Wrap callback bằng ContextSnapshot |
| Không xử lý cancel | Span treo hoặc status sai | Kết nối cancellation với terminal lifecycle |
| Callback terminal chạy hai lần | Stop/record outcome trùng | State machine/AtomicBoolean |
| Dùng trace ID làm tag metric | Cardinality bùng nổ | Chỉ dùng trace ID trong trace/log correlation |
| Async message xử lý rất muộn nhưng ép làm child | Trace parent kéo dài không hợp lý | Cân nhắc consumer span và span link |

## 11. Kiểm thử context propagation

Kiểm thử cần chứng minh mối quan hệ trace, không chỉ chứng minh Runnable chạy được.

### 11.1. Ma trận test

| Test case | Kỳ vọng |
|---|---|
| Đồng bộ trong cùng thread | Span con có cùng Trace ID và parent đúng |
| ThreadPoolTaskExecutor có TaskDecorator | Task thấy parent context |
| CompletableFuture với executor tường minh | Async stage giữ trace context |
| CompletableFuture commonPool | Test có thể phát hiện context bị mất nếu không được instrument |
| @Async với ragExecutor | Method chạy async nhưng trace vẫn nối |
| Reactor publishOn | Reactor Context và tracing context được phục hồi |
| Spring AI ChatClient stream | Span bao trọn subscription/terminal lifecycle |
| SDK callback thread | Chunk/error/complete thuộc đúng trace |
| Cancellation | Observation kết thúc một lần với outcome cancelled |
| Error callback | Error span gắn đúng trace và không lộ message |
| Message consumer | Parent hoặc span link đúng semantics |

### 11.2. Assertions cần có

- Root và child có cùng Trace ID khi quan hệ parent-child được mong đợi.
- Child span có Parent Span ID trỏ tới span cha.
- Child span không vô tình trở thành root.
- Span kết thúc sau terminal signal, không kết thúc khi mới submit.
- Error và cancellation được biểu diễn đúng.
- Không có duplicate terminal stop.
- Không rò raw prompt, document, token hoặc user data trong attributes.
- Context của request trước không rò sang task kế tiếp trong thread pool.

### 11.3. Integration test với in-memory exporter

Một test tracing thực tế có thể dùng OpenTelemetry SDK testing exporter hoặc test Collector:

1. Khởi tạo tracing bridge và SDK/exporter dành cho test.
2. Cấu hình sampler giữ trace trong test.
3. Gửi request fixture qua endpoint RAG.
4. Chạy retrieval qua executor và model stream qua callback/Flux.
5. Chờ terminal signal và flush exporter.
6. Thu các spans từ in-memory exporter.
7. Tìm root span và các span con theo Trace ID.
8. Assert Parent Span ID, span names và thời điểm kết thúc.
9. Lặp lại với error và cancellation.
10. Kiểm tra context không rò giữa hai request chạy liên tiếp trên cùng worker thread.

API của in-memory exporter phụ thuộc OpenTelemetry SDK testing version. Dùng đúng artifact/version trong test scope và không mang test exporter vào production.

## 12. Runbook khi trace bị tách

1. **Tạo fixture:** một request RAG có trace reference ngẫu nhiên và dữ liệu tổng hợp.
2. **Xác nhận root:** tìm root span ở HTTP entry và ghi trace ID/span ID.
3. **Đánh dấu ranh giới:** trước submit, sau executor start, trước VectorStore, trước stream, trong callback và terminal.
4. **Kiểm tra executor:** xác định thread pool thực tế, TaskDecorator và các stage có dùng commonPool không.
5. **Kiểm tra context source:** snapshot được capture khi parent scope còn current hay không.
6. **Kiểm tra async lifecycle:** Observation có bị stop khi Future/Flux mới được tạo không?
7. **Kiểm tra Reactor:** phân biệt Reactor Context với ThreadLocal; xác minh automatic propagation/hook theo version.
8. **Kiểm tra SDK callback:** callback chạy trên thread nào, có wrap snapshot không, terminal/cancel có được nối không.
9. **Kiểm tra distributed boundary:** W3C/B3 headers có được inject/extract không?
10. **Kiểm tra span relationships:** cùng Trace ID? Parent ID? Nếu task tách rời, có cần span link?
11. **Kiểm tra lỗi và cleanup:** callback error/cancel, rejection, timeout, duplicate completion và context cleanup.
12. **Thêm regression tests:** đồng bộ, executor, reactive, stream callback, cancellation và thread reuse.

### 12.1. Chẩn đoán nhanh theo biểu hiện

| Biểu hiện | Điểm bắt đầu |
|---|---|
| Trace ID đổi ngay khi vào executor | TaskDecorator/context snapshot |
| Trace ID đúng nhưng root kết thúc quá sớm | Future/Flux lifecycle |
| Chỉ mất trace sau publishOn | Reactor Context/ThreadLocal bridge |
| Chỉ mất trace ở model stream callback | SDK callback context snapshot |
| Trace nối đúng nhưng callback không có parent | Observation scope tại thời điểm callback |
| Callback có trace nhưng stream không có terminal span | Completion/error/cancel lifecycle |
| Request thứ hai nhận context request đầu | Cleanup ThreadLocal/context snapshot |
| Message consumer tạo trace mới | Propagator/message metadata và span links |

## 13. Bảo mật và hiệu năng

Context propagation có thể mang theo nhiều thông tin hơn Trace ID:

- Security context.
- Request metadata.
- Baggage.
- Tenant/user identifiers.
- Observation attributes.

Chỉ propagate dữ liệu được phép. Không lưu prompt, retrieved documents, credentials hoặc token trong ThreadLocal/baggage để “dễ debug”.

Các snapshot và tracing scopes cũng có chi phí. Hãy:

- Dùng executor có giới hạn concurrency/queue.
- Tránh capture toàn bộ context không cần thiết.
- Không tạo span cho từng token/chunk nếu số lượng quá lớn; dùng event/aggregate hoặc span theo operation.
- Không log mỗi callback với payload.
- Đảm bảo cancellation giải phóng tài nguyên.
- Kiểm tra overhead khi bật automatic Reactor context propagation.

## 14. Những sai lầm thường gặp

1. **Cho rằng ThreadLocal tự đi theo executor.** Thread pool dùng thread khác và tái sử dụng thread.
2. **Chỉ truyền Trace ID bằng biến.** Không khôi phục current span hoặc parent relationship.
3. **Dùng CompletableFuture commonPool.** Executor mặc định có thể không được cấu hình propagation.
4. **Bọc Future bằng Observation.observe() đồng bộ.** Span có thể kết thúc khi Future chưa hoàn tất.
5. **Bọc việc tạo Flux bằng Observation đồng bộ.** Publisher có thể chạy sau khi scope đã đóng.
6. **Giữ Observation.Scope mở qua thread switch.** Scope phải được mở/đóng đúng thread.
7. **Capture snapshot sau khi rời parent scope.** Snapshot không còn parent context mong muốn.
8. **Cho rằng Reactor Context chính là ThreadLocal.** Chúng có semantics và cơ chế propagation khác nhau.
9. **Gọi subscribe() trong service rồi trả về void.** Lifecycle/cancel tách khỏi caller.
10. **Bỏ qua callback error/complete/cancel.** Span có thể treo hoặc stop sai.
11. **Không bảo vệ terminal callback khỏi chạy hai lần.** Dẫn đến stop/outcome trùng.
12. **Tạo span con cho job chạy độc lập nhiều giờ.** Consumer span/link có thể phù hợp hơn.
13. **Không kiểm tra thread reuse.** Context cũ có thể rò sang request kế tiếp.
14. **Tạo span cho từng chunk/token mà không giới hạn.** Trace payload và storage tăng nhanh.
15. **Đưa baggage nhạy cảm vào context.** Dữ liệu có thể lan qua nhiều service.

## 15. Bài thực hành tự luyện

**Bối cảnh:** Một ứng dụng Spring AI trả lời RAG bằng streaming. Khi chạy đồng bộ, trace có đủ ChatClient, EmbeddingModel và VectorStore spans. Sau khi chuyển retrieval sang CompletableFuture và xử lý stream trên scheduler riêng, trace bị tách thành nhiều Trace ID.

Yêu cầu:

1. Ghi nhận Trace ID và Parent Span ID ở HTTP entry.
2. Kiểm tra executor thực tế của CompletableFuture; loại bỏ commonPool khỏi đường cần propagation.
3. Cấu hình ThreadPoolTaskExecutor với ContextPropagatingTaskDecorator.
4. Thêm test chứng minh async stage giữ cùng Trace ID và parent relationship.
5. Bật Reactor automatic context propagation trong môi trường test nếu version hỗ trợ.
6. Thử publishOn/subscribeOn và xác minh context trước/sau scheduler.
7. Trả Flux từ service, không tự subscribe nội bộ.
8. Tạo SDK callback fixture phát chunk, error, completion và cancellation trên thread khác.
9. Capture ContextSnapshot khi parent scope còn current và wrap callback.
10. Đảm bảo Observation stream dừng ở terminal event, không dừng khi mới tạo Future/Flux.
11. Chạy hai request liên tiếp trên cùng worker thread để phát hiện context leak.
12. Nếu dùng message queue, quyết định parent-child hay span link theo thời gian xử lý.
13. Kiểm tra trace payload không chứa raw prompt/document/token.
14. Viết integration test với in-memory exporter cho sync, executor, Reactor và callback.

**Câu hỏi tự kiểm tra:**

- Vì sao ThreadLocal không tự truyền sang thread của executor?
- Observation.Scope khác Observation lifecycle như thế nào?
- Vì sao không thể chuyển Scope từ thread submit sang thread thực thi?
- TaskDecorator có tác dụng gì và giới hạn ở đâu?
- Vì sao CompletableFuture không có executor có thể làm trace bị tách?
- Reactor Context khác ThreadLocal như thế nào?
- Vì sao Observation.observe() quanh việc tạo Flux có thể kết thúc quá sớm?
- SDK callback chạy trên thread nội bộ cần được xử lý thế nào?
- Khi nào nên dùng span link thay vì giữ parent span mở?
- Những assertion nào chứng minh context không bị rò giữa hai request?

## 16. Checklist triển khai

- [ ] Xác định mọi ranh giới đổi thread, executor, Reactor scheduler và SDK callback.
- [ ] Phân biệt ThreadLocal, Observation scope, Reactor Context và distributed trace context.
- [ ] Không chuyển Observation.Scope giữa các thread.
- [ ] Capture context khi parent scope còn current.
- [ ] Executor dùng TaskDecorator hoặc ContextSnapshot phù hợp.
- [ ] CompletableFuture và @Async dùng executor đã cấu hình propagation.
- [ ] Không dựa vào commonPool cho đường tracing quan trọng nếu chưa instrument.
- [ ] Reactor Context Propagation được cấu hình theo version và kiểm thử sau publishOn/subscribeOn.
- [ ] Spring AI streaming giữ lifecycle đến complete/error/cancel.
- [ ] SDK callbacks được wrap bằng context snapshot khi chạy trên thread riêng.
- [ ] Terminal callback chỉ stop Observation một lần.
- [ ] Error/rejection/timeout/cancel đều có cleanup.
- [ ] Message queue dùng parent hoặc span link theo semantics.
- [ ] Context không chứa raw prompt, document, credentials hoặc baggage nhạy cảm.
- [ ] Có test thread reuse để phát hiện context leak.
- [ ] Có integration test kiểm tra Trace ID, Parent Span ID và span lifecycle.

## Tổng kết

Trace bị tách khi đổi thread hoặc dùng streaming thường xuất phát từ việc context gắn với ThreadLocal không được capture/restore, hoặc Observation kết thúc theo thời điểm method trả về thay vì thời điểm tác vụ bất đồng bộ hoàn tất. Reactor Context, ThreadLocal và distributed trace context có vai trò khác nhau; không thể thay thế lẫn nhau bằng cách copy một chuỗi Trace ID.

Với executor, dùng TaskDecorator hoặc Micrometer ContextSnapshot để khôi phục context trong thread thực thi. Với CompletableFuture, chỉ định executor đã cấu hình propagation. Với Reactor/Spring AI streaming, giữ publisher lifecycle, cấu hình context propagation tương thích và trả Flux về caller. Với SDK callback, capture context trước khi đăng ký callback, wrap chunk/error/complete/cancel và stop Observation đúng một lần ở terminal event. Với message xử lý tách rời thời gian, cân nhắc consumer span và span link. Cuối cùng, kiểm thử Trace ID, Parent Span ID, cancellation và thread reuse để phát hiện lỗi propagation trước khi phát hành.

## Tài liệu tham khảo

- [Micrometer Context Propagation](https://docs.micrometer.io/context-propagation/reference/): ContextRegistry, ContextSnapshot và context propagation.
- [Micrometer — Observation](https://docs.micrometer.io/micrometer/reference/observation.html): Observation lifecycle và scope.
- [Micrometer Tracing](https://docs.micrometer.io/tracing/reference/): tracing bridge, span và propagation.
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): TaskExecutor, @Async và task decoration.
- [Spring Framework — ContextPropagatingTaskDecorator](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/task/support/ContextPropagatingTaskDecorator.html): truyền context qua task execution.
- [Project Reactor — Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html): Reactor Context và subscriber context.
- [Project Reactor — Context Propagation](https://projectreactor.io/docs/core/release/reference/advanced-contextPropagation.html): tích hợp ThreadLocal với Reactor Context.
- [Spring AI — Observability](https://docs.spring.io/spring-ai/reference/observability/): Observation của ChatClient, ChatModel, EmbeddingModel và VectorStore.
- [OpenTelemetry — Context Propagation](https://opentelemetry.io/docs/concepts/context-propagation/): truyền trace context giữa service.
- [OpenTelemetry — Span Links](https://opentelemetry.io/docs/concepts/signals/traces/#span-links): liên kết span cho công việc bất đồng bộ/tách rời.
- [W3C Trace Context](https://www.w3.org/TR/trace-context/): traceparent và tracestate.
