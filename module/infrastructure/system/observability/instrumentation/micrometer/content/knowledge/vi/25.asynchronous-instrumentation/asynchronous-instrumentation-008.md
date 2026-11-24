# Quan hệ giữa đo thời lượng và truyền ngữ cảnh qua ranh giới luồng

Trong ứng dụng Java, một tác vụ có thể bắt đầu trên request thread nhưng hoàn tất trên worker thread. Micrometer cần đo đúng khoảng thời gian của tác vụ, đồng thời tracing và logging cần giữ được Observation, trace ID hoặc các giá trị ngữ cảnh liên quan khi công việc chuyển sang thread khác. Hai yêu cầu này liên quan nhưng không đồng nhất: **đo thời lượng** xác định khi nào phép đo bắt đầu và kết thúc; **context propagation** đưa ngữ cảnh hiện hành sang nơi tác vụ tiếp tục chạy.

Nếu chỉ đo thời gian gọi phương thức submit, dashboard có thể ghi nhận vài mili giây dù tác vụ nền mất vài giây. Nếu chỉ đo đúng thời lượng nhưng không truyền context, Timer vẫn có thể đúng nhưng span con mất quan hệ parent-child, log không có trace ID và Observation hiện hành không còn truy cập được trong worker. Muốn observability đầy đủ, cần xử lý riêng cả lifecycle của phép đo lẫn lifecycle của context.

Bài này thuộc module **OBSERVABILITY_INSTRUMENTATION_MICROMETER**. Nội dung tập trung vào ThreadLocal, Observation scope, Micrometer Context Propagation, ExecutorService, Spring @Async, Reactor Context và cách kiểm thử khi công việc đi qua ranh giới luồng.

## 1. Hai vấn đề khác nhau: duration và context

Giả sử một request tạo báo cáo và giao phần tính toán cho executor:

~~~java
public CompletableFuture<Report> generate(String reportId) {
    return CompletableFuture.supplyAsync(
            () -> reportService.generate(reportId),
            executor
    );
}
~~~

Có hai câu hỏi vận hành:

1. Từ lúc nhận yêu cầu đến lúc báo cáo hoàn tất mất bao lâu?
2. Khi worker xử lý, nó có biết Observation hoặc trace của request ban đầu để tạo span con và ghi log có trace ID không?

Câu hỏi thứ nhất là đo thời lượng. Câu hỏi thứ hai là truyền ngữ cảnh.

| Khả năng | Cơ chế chính | Kết quả |
|---|---|---|
| Đo thời lượng toàn tác vụ | Timer, Timer.Sample, Observation | Ghi thời gian từ lúc bắt đầu đến lúc tác vụ hoàn tất |
| Giữ Observation hiện hành | Observation scope và Context Propagation | Worker nhìn thấy Observation cha phù hợp |
| Giữ trace context | Tracing bridge và context accessor | Span con nối đúng trace cha |
| Giữ MDC/log context | ThreadLocalAccessor cho MDC hoặc logging context | Log trên worker giữ trace ID/correlation fields |
| Chuyển ngữ cảnh vào Reactor | Reactor Context và Context Propagation | Các operator đọc đúng context dù đổi thread |

Một Timer không tự mang theo Observation hoặc trace context. Ngược lại, việc truyền context không tự quyết định Timer nên dừng ở thời điểm submit, lúc worker bắt đầu hay khi tác vụ hoàn tất.

## 2. Vì sao ThreadLocal không tự đi theo tác vụ?

Nhiều thư viện observability lưu trạng thái hiện hành trong ThreadLocal. Ví dụ, khi một Observation được mở scope, Micrometer đặt Observation hiện hành vào thread đang thực thi. Tracing bridge có thể dùng context tương tự để tìm span hiện hành.

ThreadLocal gắn dữ liệu với một thread, không gắn dữ liệu với Runnable hoặc Future. Khi tác vụ chuyển từ request thread sang worker thread, worker không tự nhìn thấy giá trị ThreadLocal của request thread.

~~~text
Request thread
  Observation A trong ThreadLocal
          |
          | submit(task)
          v
Executor queue
          |
          v
Worker thread
  ThreadLocal riêng của worker
  Observation A không tự xuất hiện
~~~

Vấn đề này càng quan trọng với thread pool. Một worker được tái sử dụng cho nhiều tác vụ khác nhau. Nếu một tác vụ tự đặt ThreadLocal nhưng không dọn dẹp, tác vụ tiếp theo có thể đọc nhầm dữ liệu cũ. Nếu một tác vụ cần context cha nhưng không được truyền, nó có thể tạo span gốc mới hoặc log thiếu trace ID.

Không dùng InheritableThreadLocal như giải pháp chung cho thread pool. Worker thường được tạo trước khi request đến và được tái sử dụng; việc kế thừa khi tạo thread không giải quyết được việc truyền context cho từng lần submit.

## 3. Observation scope có vòng đời riêng

Observation thường có ba thao tác quan trọng:

- start: bắt đầu Observation và cho phép các handler ghi nhận thời gian hoặc tạo span.
- openScope: đặt Observation làm context hiện hành trên thread đang chạy.
- stop: kết thúc Observation và thông báo cho các handler.

Scope chỉ áp dụng trên thread nơi nó được mở. Khi scope đóng, trạng thái trước đó được khôi phục. Observation có thể vẫn đang chạy sau khi scope trên thread gọi đã đóng, nhưng thread khác chỉ nhìn thấy nó nếu context được truyền sang đó.

~~~java
Observation observation =
        Observation.start("report.generate", observationRegistry);

try (Observation.Scope scope = observation.openScope()) {
    // Observation hiện hành trên thread này.
    reportService.prepare();
}

observation.stop();
~~~

Ví dụ trên minh họa scope của một thao tác đồng bộ. Với công việc bất đồng bộ, không nên stop Observation ngay sau lệnh submit nếu muốn Observation bao phủ toàn bộ tác vụ. Cần giữ lifecycle đến khi Future hoặc CompletionStage hoàn tất, đồng thời truyền context cần thiết vào worker.

Cũng cần phân biệt việc tạo Observation con với việc truyền Observation cha. Context propagation giữ quan hệ hiện hành qua ranh giới thread; mã chạy trong worker có thể tạo một Observation con để mô tả công việc riêng.

## 4. Micrometer Context Propagation giải quyết phần nào?

Thư viện Micrometer Context Propagation hỗ trợ chuyển giá trị giữa các cơ chế context khác nhau, chẳng hạn ThreadLocal và Reactor Context. Các thành phần chính gồm:

| Thành phần | Vai trò |
|---|---|
| ThreadLocalAccessor | Đọc, đặt và xóa một giá trị ThreadLocal đã đăng ký |
| ContextAccessor | Đọc/ghi một loại context dạng map như Reactor Context |
| ContextRegistry | Quản lý các accessor được sử dụng |
| ContextSnapshot | Chụp các giá trị context tại một thời điểm và khôi phục chúng ở nơi khác |
| ContextSnapshotFactory | Tạo snapshot và khôi phục context theo registry đã cấu hình |
| ContextExecutorService | Bọc ExecutorService để capture context lúc submit và restore khi chạy task |
| ContextScheduledExecutorService | Bọc ScheduledExecutorService để truyền context cho tác vụ được schedule |

Context Propagation không tự tạo Observation hoặc span. Nó chuyển những giá trị đã được đăng ký để tác vụ có thể tiếp tục dùng context đó. Việc tạo Observation, tạo span con và đo duration vẫn do instrumentation tương ứng thực hiện.

Một ThreadLocal chỉ được capture khi có ThreadLocalAccessor tương ứng. Các ThreadLocal tùy chỉnh không tự động được biết đến chỉ vì chúng tồn tại trong ứng dụng. Với Spring Boot và Micrometer Tracing, các accessor observability thường được tích hợp qua auto-configuration; ứng dụng thuần cần đăng ký accessor cần thiết.

## 5. Bọc ExecutorService để capture context lúc submit

Với executor Java thông thường, có thể dùng ContextExecutorService để chụp context tại thời điểm submit và khôi phục nó quanh phần chạy task.

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import io.micrometer.context.ContextExecutorService;
import io.micrometer.context.ContextSnapshotFactory;

public class ContextAwareExecutor {

    private final ExecutorService delegate =
            Executors.newFixedThreadPool(8);

    private final ExecutorService executor =
            ContextExecutorService.wrap(
                    delegate,
                    ContextSnapshotFactory.builder().build()
            );

    public ExecutorService executor() {
        return executor;
    }
}
~~~

Khi submit task trong lúc Observation cha đang mở scope, wrapper capture các ThreadLocal đã đăng ký. Khi worker chạy task, snapshot khôi phục các giá trị đó. Khi task kết thúc, scope của snapshot đóng và khôi phục trạng thái trước đó trên worker thread.

Ví dụ:

~~~java
Observation parent = Observation.start("invoice.process", registry);

try (Observation.Scope scope = parent.openScope()) {
    contextAwareExecutor.submit(() -> {
        Observation child = Observation.createNotStarted(
                "invoice.calculate", registry
        );

        child.observe(() -> invoiceService.calculate());
    });
}
~~~

Worker có thể nhìn thấy Observation cha được capture khi submit, nhờ đó Observation con được tạo trong đúng ngữ cảnh. Đối tượng executor đã bọc nên được tái sử dụng; không tạo wrapper mới cho mỗi task.

Nếu chỉ cần bọc một Runnable hoặc Callable, có thể capture snapshot trực tiếp:

~~~java
ContextSnapshot snapshot = ContextSnapshotFactory.builder()
        .build()
        .captureAll();

executor.execute(snapshot.wrap(() -> {
    // Các ThreadLocalAccessor đã đăng ký được khôi phục ở đây.
    doWork();
}));
~~~

Snapshot là ảnh chụp tại thời điểm capture. Thay đổi ThreadLocal sau thời điểm đó không tự cập nhật vào snapshot. Hãy capture ngay tại ranh giới submit cần truyền context.

## 6. Đo toàn bộ tác vụ bất đồng bộ đến completion

Đo duration từ lúc submit đến khi tác vụ hoàn tất cần một mốc bắt đầu ở thread gọi và một mốc kết thúc khi Future hoặc CompletionStage hoàn tất.

Có thể dùng Timer.Sample:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.Timer.Sample;

public class ReportService {

    private final MeterRegistry registry;
    private final ExecutorService contextAwareExecutor;

    public ReportService(
            MeterRegistry registry,
            ExecutorService contextAwareExecutor) {
        this.registry = registry;
        this.contextAwareExecutor = contextAwareExecutor;
    }

    public CompletionStage<Report> generate(String reportId) {
        Timer.Sample sample = Timer.start(registry);

        CompletionStage<Report> stage = CompletableFuture.supplyAsync(
                () -> createReport(reportId),
                contextAwareExecutor
        );

        return stage.whenComplete((report, error) -> {
            Timer timer = registry.timer(
                    "report.generate",
                    "outcome",
                    error == null ? "success" : "error"
            );
            sample.stop(timer);
        });
    }

    private Report createReport(String reportId) {
        return reportRepository.generate(reportId);
    }
}
~~~

Timer.Sample bắt đầu trước khi submit và dừng trong callback completion. Vì vậy, duration bao gồm thời gian chờ queue và thời gian thực thi. Nếu chỉ muốn đo thời gian worker thực thi, hãy bắt đầu sample bên trong task thay vì trước khi submit.

Nếu lệnh supplyAsync bị từ chối ngay lúc submit, CompletionStage chưa được tạo và callback whenComplete không chạy. Bắt RejectedExecutionException tại điểm submit, dừng sample với outcome cố định như rejected rồi ném lỗi lên caller.

Callback whenComplete có thể chạy trên thread hoàn tất stage. Việc dừng Timer không yêu cầu callback phải có ThreadLocal context; nếu callback cần đọc Observation, trace hoặc MDC hiện hành, hãy đưa callback qua executor có context propagation hoặc capture/restore context riêng.

Nếu method đã được instrument bằng TimedAspect và trả về CompletionStage, aspect có thể đo đến lúc stage hoàn tất. Trong trường hợp đó, không thêm Timer.Sample thứ hai cho cùng một đại lượng nếu không muốn hai bộ metrics trùng lặp. Context propagation vẫn cần cấu hình riêng; TimedAspect không tự biến executor thành context-aware executor.

## 7. Đo riêng queue wait và execution time

Một duration từ submit đến completion hữu ích cho trải nghiệm tổng thể, nhưng chưa cho biết tác vụ chậm vì phải chờ queue hay vì xử lý lâu.

Có thể chia thành hai phép đo:

- Queue wait: từ lúc submit đến khi worker bắt đầu chạy task.
- Execution time: từ lúc worker bắt đầu đến khi task kết thúc.

~~~java
import java.util.concurrent.TimeUnit;

Timer queueWait = registry.timer("report.queue.wait");
Timer execution = registry.timer("report.execution");

long submittedAt = registry.config().clock().monotonicTime();

executor.execute(() -> {
    long startedAt = registry.config().clock().monotonicTime();
    queueWait.record(startedAt - submittedAt, TimeUnit.NANOSECONDS);

    Timer.Sample executionSample = Timer.start(registry);
    try {
        createReport();
    }
    finally {
        executionSample.stop(execution);
    }
});
~~~

Ví dụ này dùng monotonic clock để đo duration, tránh sai lệch khi đồng hồ hệ thống được đồng bộ hoặc chỉnh giờ. Trong ứng dụng nhiều task đồng thời, mỗi task phải giữ timestamp riêng; không dùng một biến timestamp dùng chung cho cả executor.

Khi queue wait tăng nhưng execution time ổn định, pool có thể thiếu worker hoặc tốc độ submit vượt tốc độ xử lý. Khi execution time tăng, cần điều tra logic tác vụ hoặc dependency như database, HTTP client và dịch vụ bên ngoài. Hai chỉ số giúp chọn đúng hướng xử lý.

## 8. Spring @Async với context propagation

Với Spring Boot, nếu dùng AsyncTaskExecutor được auto-configure, có thể bật truyền context bằng thuộc tính:

~~~yaml
spring:
  task:
    execution:
      propagate-context: true
~~~

Thuộc tính này là opt-in cho AsyncTaskExecutor auto-configured và phụ thuộc phiên bản Spring Boot. Hãy đối chiếu metadata cấu hình của phiên bản dự án trước khi dùng.

Nếu ứng dụng tự cấu hình ThreadPoolTaskExecutor, gắn ContextPropagatingTaskDecorator:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class AsyncConfiguration {

    @Bean
    ThreadPoolTaskExecutor applicationTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(8);
        executor.setMaxPoolSize(32);
        executor.setQueueCapacity(200);
        executor.setThreadNamePrefix("application-");
        executor.setTaskDecorator(
                new ContextPropagatingTaskDecorator()
        );
        return executor;
    }
}
~~~

TaskDecorator bọc việc thực thi Runnable, capture context ở thời điểm task được submit và khôi phục các giá trị đã đăng ký khi worker chạy. Khi task kết thúc, context được khôi phục về trạng thái trước đó của worker.

ContextPropagatingTaskDecorator có overhead do capture và restore context. Không nên áp dụng một cách máy móc cho hàng triệu task rất nhỏ mà chưa đo chi phí. Nếu executor tự cấu hình nhưng không có decorator, việc dùng @Async không tự bảo đảm Observation hoặc MDC được truyền qua thread.

## 9. Đo thời lượng của tác vụ bất đồng bộ và giữ Observation cha

Ví dụ sau kết hợp Observation cha, executor có context propagation và CompletionStage:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.ExecutorService;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

public class InvoiceWorkflow {

    private final ObservationRegistry registry;
    private final ExecutorService contextAwareExecutor;
    private final InvoiceRepository invoiceRepository;

    public InvoiceWorkflow(
            ObservationRegistry registry,
            ExecutorService contextAwareExecutor,
            InvoiceRepository invoiceRepository) {
        this.registry = registry;
        this.contextAwareExecutor = contextAwareExecutor;
        this.invoiceRepository = invoiceRepository;
    }

    public CompletionStage<Invoice> generate(String orderId) {
        Observation parent = Observation.start(
                "invoice.generate", registry
        );

        CompletionStage<Invoice> stage;
        try (Observation.Scope scope = parent.openScope()) {
            stage = CompletableFuture.supplyAsync(() -> {
                Observation child = Observation.createNotStarted(
                        "invoice.calculate", registry
                );
                return child.observe(() -> calculate(orderId));
            }, contextAwareExecutor);
        }
        catch (RuntimeException submissionFailure) {
            parent.error(submissionFailure);
            parent.stop();
            throw submissionFailure;
        }

        return stage.whenComplete((invoice, error) -> {
            if (error != null) {
                parent.error(error);
            }
            parent.stop();
        });
    }

    private Invoice calculate(String orderId) {
        return invoiceRepository.calculate(orderId);
    }
}
~~~

Trình tự trong ví dụ:

1. Bắt đầu Observation cha.
2. Mở scope của Observation cha trên request thread.
3. Submit task qua executor đã bọc; context được capture lúc submit.
4. Worker khôi phục Observation cha và tạo Observation con.
5. Khi stage hoàn tất, callback đánh dấu lỗi nếu có và stop Observation cha.

Trong ứng dụng Spring Boot, ObservationRegistry cần có các ObservationHandler phù hợp để Observation sinh metrics và/hoặc span. Nếu chỉ tạo Observation mà không có handler xuất tín hiệu tương ứng, bạn có thể không thấy metric hoặc trace mong đợi.

Nếu submit bị từ chối trước khi stage được tạo, cần bắt RejectedExecutionException, đánh dấu parent.error(exception) và stop parent trong nhánh lỗi đó. Trong production, hãy bảo đảm mọi nhánh đều kết thúc Observation đúng một lần.

## 10. Context Propagation trong Reactor

Reactor không dựa vào ThreadLocal làm nguồn context chính. Reactor Context gắn với Subscriber và đi theo subscription, kể cả khi pipeline chuyển qua scheduler khác. Từ Reactor 3.5, Reactor tích hợp SPI của Micrometer Context Propagation để chuyển đổi giữa Reactor Context và ThreadLocal đã đăng ký.

Có hai chế độ chính:

| Chế độ | Hành vi |
|---|---|
| Default/limited mode | Khôi phục ThreadLocal trong các operator được chọn như tap và handle khi Context Propagation có mặt và context đã được capture |
| Automatic mode | Khôi phục ThreadLocal qua các operator và ranh giới thread dựa trên Reactor Context |

Automatic mode có thể bật bằng hook:

~~~java
import reactor.core.publisher.Hooks;

public class ReactorConfiguration {

    public void initialize() {
        Hooks.enableAutomaticContextPropagation();
    }
}
~~~

Hook nên được bật khi ứng dụng khởi động vì chế độ này chỉ áp dụng cho các subscription mới. Spring Boot cung cấp thuộc tính cấu hình tương ứng:

~~~yaml
spring:
  reactor:
    context-propagation: auto
~~~

Với ứng dụng dùng Spring Boot, ưu tiên cấu hình theo phiên bản Boot thay vì gọi hook ở nhiều nơi. Không bật hook lặp lại ở mỗi request.

Thuộc tính này chỉ có trong các phiên bản Spring Boot hỗ trợ Context Propagation cho Reactor. Nếu dự án dùng phiên bản cũ hơn, hãy kiểm tra tài liệu tương ứng và cân nhắc cấu hình Hook trực tiếp khi khởi động.

Automatic mode tiện lợi nhưng có chi phí capture/restore và yêu cầu dọn dẹp ThreadLocal đúng cách. Reactor dùng Context làm nguồn sự thật; key không có trong Context được dùng để xóa ThreadLocal tương ứng đã đăng ký, tránh để dữ liệu của subscriber trước rò sang subscriber sau. Hãy benchmark với tải đại diện trước khi chọn chế độ.

## 11. contextCapture và contextWrite khác nhau thế nào?

Hai operator này phục vụ hai hướng đưa dữ liệu vào Reactor Context:

- contextWrite: ghi giá trị một cách tường minh vào Reactor Context.
- contextCapture: chụp các ThreadLocal đã đăng ký tại thời điểm subscription và đưa giá trị vào Reactor Context.

Ví dụ dùng contextWrite khi dữ liệu đã có sẵn và muốn truyền rõ ràng:

~~~java
Mono.deferContextual(context -> {
    String correlationId = context.get("correlationId");
    return process(correlationId);
}).contextWrite(context ->
        context.put("correlationId", "corr-123")
);
~~~

Ví dụ dùng contextCapture khi gọi một reactive pipeline từ imperative code đang có ThreadLocal:

~~~java
Mono<Result> result = Mono.deferContextual(context ->
        processWithContext(context)
).contextCapture();
~~~

contextCapture chụp giá trị tại subscription, không phải lúc tạo Mono. Nếu ThreadLocal thay đổi giữa lúc dựng pipeline và lúc subscribe, giá trị được capture là giá trị ở thời điểm subscribe.

Trong ứng dụng WebFlux, framework thường đã đưa context của request vào Reactor Context. Không thêm contextCapture một cách máy móc nếu framework đã quản lý context; kiểm tra ranh giới imperative/reactive cụ thể.

## 12. Chuyển Observation vào Reactor Context

Khi một Observation được tạo bên ngoài reactive chain và cần làm parent cho các Observation trong pipeline, có thể đặt nó trực tiếp vào Reactor Context bằng accessor key của Micrometer Observation.

Với Micrometer Tracing/Observation, nên dùng integration có sẵn của Spring Boot và Reactor khi có thể. Nếu phải quản lý thủ công, cần bảo đảm Observation được stop ở terminal signal:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.contextpropagation.ObservationThreadLocalAccessor;
import reactor.core.publisher.Mono;

Observation parent = Observation.start("catalog.request", registry);

Mono<Product> pipeline = repository.findById(productId)
        .doFinally(signal -> parent.stop())
        .contextWrite(context ->
                context.put(ObservationThreadLocalAccessor.KEY, parent)
        );
~~~

Đoạn này minh họa việc đưa Observation vào Reactor Context; API accessor và cách đăng ký phụ thuộc phiên bản Micrometer. Trong pipeline thực tế, phải bảo đảm Observation được tạo một lần cho mỗi subscription nếu pipeline có thể được subscribe nhiều lần. Không chia sẻ một Observation đã stop cho nhiều subscriber.

Việc đặt Observation vào Reactor Context chưa đồng nghĩa ThreadLocal sẽ được khôi phục trong mọi callback. Ở default/limited mode, dùng các operator có hỗ trợ restoration như tap hoặc handle; nếu cần ThreadLocal qua toàn pipeline, cân nhắc automatic mode và đo overhead của nó.

Nếu tạo Observation bên trong Mono.defer, mỗi subscription có thể có lifecycle riêng:

~~~java
Mono<Product> lookup(String id) {
    return Mono.defer(() -> {
        Observation observation = Observation.start(
                "catalog.lookup", registry
        );

        return repository.findById(id)
                .doFinally(signal -> observation.stop())
                .contextWrite(context ->
                        context.put(
                                ObservationThreadLocalAccessor.KEY,
                                observation
                        )
                );
    });
}
~~~

Với ứng dụng Spring Boot, cần kiểm tra accessor được đăng ký và các ObservationHandler đang hoạt động. Không truy cập trực tiếp ThreadLocal của tracing implementation nếu đã có Observation/Context Propagation API.

## 13. Tự đăng ký ThreadLocalAccessor cho context riêng

Context Propagation chỉ biết các ThreadLocal đã được đăng ký. Nếu ứng dụng có một context riêng, chẳng hạn correlation ID, có thể cung cấp ThreadLocalAccessor.

~~~java
import io.micrometer.context.ThreadLocalAccessor;

public class CorrelationIdAccessor
        implements ThreadLocalAccessor<String> {

    public static final String KEY = "app.correlationId";
    private static final ThreadLocal<String> HOLDER =
            new ThreadLocal<>();

    @Override
    public Object key() {
        return KEY;
    }

    @Override
    public String getValue() {
        return HOLDER.get();
    }

    @Override
    public void setValue(String value) {
        HOLDER.set(value);
    }

    @Override
    public void setValue() {
        HOLDER.remove();
    }
}
~~~

Đăng ký accessor với ContextRegistry:

~~~java
ContextRegistry.getInstance()
        .registerThreadLocalAccessor(new CorrelationIdAccessor());
~~~

Khi ContextSnapshot được capture, accessor cho phép thư viện đọc correlation ID. Khi snapshot được restore, giá trị được đặt trên worker thread; khi scope đóng, trạng thái trước đó được khôi phục hoặc xóa.

Chỉ đăng ký những context cần thiết. Không capture mọi dữ liệu ứng dụng một cách tùy tiện, không đưa object lớn vào context và không dùng context propagation để truyền payload nghiệp vụ thay cho tham số method hoặc message.

## 14. Ranh giới thread và ranh giới mạng khác nhau

Context Propagation xử lý việc truyền context trong tiến trình qua thread, executor và reactive pipeline. Khi gọi một dịch vụ khác qua HTTP hoặc messaging, context cần được inject vào carrier của giao thức, chẳng hạn traceparent header theo W3C Trace Context.

| Ranh giới | Cơ chế |
|---|---|
| Request thread → worker thread | ContextSnapshot, ContextExecutorService, TaskDecorator |
| Imperative code → Reactor | contextCapture hoặc contextWrite |
| Reactor operator → ThreadLocal | Reactor Context Propagation, tap/handle hoặc automatic mode |
| Service A → Service B qua HTTP | Tracing instrumentation inject/extract trace headers |
| Producer → consumer qua message broker | Tracing instrumentation inject/extract message headers |

Không copy trace ID thành metric tag khi chuyển qua các ranh giới. Trace context nên được giữ trong tracing system và exemplar hoặc span metadata; metric labels cần cardinality thấp.

## 15. Các lỗi thường gặp và cách nhận biết

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Timer chỉ ghi vài mili giây | Timer dừng khi method trả về hoặc lúc submit | Kiểm tra callback completion hoặc aspect có hỗ trợ kiểu trả về không |
| Worker không có trace ID | ThreadLocal không được capture/restore | Kiểm tra executor wrapper, TaskDecorator và accessor |
| Span con trở thành trace mới | Parent Observation/trace context không có trên worker | Kiểm tra context tại thời điểm submit và trong worker |
| Log có trace ID của request trước | ThreadLocal/MDC không được dọn dẹp đúng | Dùng snapshot scope hoặc finally để reset |
| Reactor operator thấy ThreadLocal null | Đang ở default mode ngoài tap/handle hoặc thiếu contextCapture | Kiểm tra Reactor Context và chế độ propagation |
| Một pipeline có nhiều Timer giống nhau | Framework auto instrumentation và instrumentation thủ công cùng chạy | Kiểm tra handler, aspect và operator đã gắn |
| Queue wait tăng nhưng execution ổn định | Executor thiếu worker hoặc tốc độ submit tăng | Theo dõi queue depth, active threads và submit rate |
| Observation dừng trước khi task hoàn tất | Stop ngay sau submit | Dời stop đến completion/error/cancel |

Không xử lý bằng cách giữ một ThreadLocal global suốt vòng đời worker. Worker thread được tái sử dụng; context phải được capture theo task và restore trong scope có cleanup.

## 16. Kiểm thử context và thời lượng qua ranh giới luồng

Một test tốt cần xác nhận cả hai điều: context cha xuất hiện trong worker và Timer/Observation chỉ kết thúc khi công việc hoàn tất.

### Kiểm thử ContextExecutorService

Có thể tạo Observation cha, submit task qua executor đã bọc và xác nhận worker nhìn thấy đúng Observation:

~~~java
Observation parent = Observation.start("parent", registry);

try (Observation.Scope scope = parent.openScope()) {
    Future<Observation> result = contextAwareExecutor.submit(
            registry::getCurrentObservation
    );

    assertThat(result.get()).isSameAs(parent);
}
finally {
    parent.stop();
}
~~~

Test này kiểm tra context được capture lúc submit và restore trong worker. Cần dùng accessor Observation đã được đăng ký trong ContextRegistry; trong Spring Boot, kiểm tra auto-configuration trước khi tự đăng ký accessor.

### Kiểm thử duration đến completion

Dùng CompletableFuture chưa hoàn tất để giữ tác vụ ở trạng thái pending:

~~~java
import java.util.concurrent.CompletionStage;
import java.util.concurrent.CompletableFuture;

CompletableFuture<String> pending = new CompletableFuture<>();
CompletionStage<String> measured = service.measure(pending);

assertThat(timer.count()).isZero();

pending.complete("done");

assertThat(measured.toCompletableFuture().join()).isEqualTo("done");
assertThat(timer.count()).isEqualTo(1);
~~~

Bổ sung các trường hợp:

- Tác vụ hoàn tất exceptional và Observation được đánh dấu error.
- Tác vụ bị cancel và phép đo kết thúc theo chính sách đã chọn.
- Worker thread chạy task tiếp theo không nhìn thấy context của task trước.
- Tác vụ được submit từ hai request khác nhau không dùng nhầm trace ID.
- Queue wait và execution time được đo thành hai khoảng riêng.
- Callback hoàn tất chạy trên thread khác vẫn dừng Timer đúng một lần.

### Kiểm thử Reactor

Dùng StepVerifier để kiểm tra context qua scheduler:

~~~java
StepVerifier.create(
        Mono.deferContextual(context ->
                Mono.just(context.get("correlationId"))
        )
        .publishOn(Schedulers.boundedElastic())
        .contextWrite(context ->
                context.put("correlationId", "corr-123")
        )
)
.expectNext("corr-123")
.verifyComplete();
~~~

Nếu test cần kiểm tra ThreadLocal được restore, đăng ký accessor tương ứng và kiểm tra bên trong operator hỗ trợ restoration hoặc bật automatic mode trong fixture. Sau test, reset hook và context tùy theo cách cấu hình test để tránh ảnh hưởng test khác.

## 17. Checklist triển khai

Trước khi đưa context propagation và async timing vào production, xác nhận:

- Đã xác định phép đo bắt đầu lúc submit, lúc worker bắt đầu hay lúc một Observation được tạo.
- Đã xác định phép đo kết thúc khi complete, error hay cancel.
- Timer hoặc Observation được stop đúng một lần khi tác vụ hoàn tất.
- ThreadLocal cần truyền có ThreadLocalAccessor đã đăng ký.
- Executor được bọc bằng ContextExecutorService hoặc TaskDecorator phù hợp.
- Context được capture tại đúng thời điểm submit.
- Snapshot scope khôi phục và dọn ThreadLocal sau mỗi task.
- Với @Async auto-configured, đã kiểm tra cấu hình propagate-context theo phiên bản Spring Boot.
- Với executor tự cấu hình, đã gắn ContextPropagatingTaskDecorator.
- Với Reactor, đã chọn default/limited hay automatic mode và kiểm tra hiệu năng.
- Đã phân biệt Reactor Context với ThreadLocal.
- Đã phân biệt truyền context trong tiến trình với inject/extract trace qua mạng.
- Đã kiểm thử context isolation giữa hai task chạy liên tiếp trên cùng worker.
- Không tạo Timer/Observation trùng với instrumentation tự động của framework.

Đo thời lượng và truyền ngữ cảnh cần được thiết kế cùng nhau nhưng giữ đúng trách nhiệm riêng. Timer.Sample hoặc Observation xác định khoảng thời gian cần đo; Context Propagation đưa Observation, trace và logging context qua executor hoặc reactive pipeline. Khi capture ở đúng ranh giới, restore trong scope có cleanup và stop phép đo tại completion/error/cancel, metrics phản ánh đúng thời gian xử lý còn trace và log vẫn giữ được quan hệ xuyên suốt các thread.

## Tài liệu tham khảo

- [Micrometer Context Propagation - Purpose](https://docs.micrometer.io/context-propagation/reference/purpose.html)
- [Micrometer Context Propagation - Usage examples](https://docs.micrometer.io/context-propagation/reference/usage.html)
- [Micrometer Observation - Instrumentation and thread switching](https://docs.micrometer.io/micrometer/reference/observation/instrumenting.html)
- [Spring Boot - Context Propagation](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [Spring Framework - ContextPropagatingTaskDecorator](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/task/support/ContextPropagatingTaskDecorator.html)
- [Project Reactor - Context Propagation Support](https://projectreactor.io/docs/core/release/reference/advanced-contextPropagation.html)
