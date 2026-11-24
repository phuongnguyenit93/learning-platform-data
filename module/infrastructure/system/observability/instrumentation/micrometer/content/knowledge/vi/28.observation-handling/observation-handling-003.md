# Giữ dữ liệu giữa onStart, onError, onEvent và onStop

## ObservationHandler xử lý một lifecycle qua nhiều callback

Micrometer Observation mô tả một hoạt động có vòng đời, chẳng hạn xử lý đơn hàng, thanh toán, nhận message hoặc chạy một tác vụ nền. ObservationRegistry chuyển các sự kiện lifecycle đến các ObservationHandler đã đăng ký.

Một handler có thể nhận nhiều callback trong cùng một Observation:

- **onStart:** được gọi khi Observation bắt đầu.
- **onEvent:** được gọi khi Observation phát sinh một event.
- **onError:** được gọi khi Observation ghi nhận lỗi.
- **onStop:** được gọi khi Observation kết thúc.

Một handler có thể cần nhớ dữ liệu được tạo ở callback trước để xử lý ở callback sau. Ví dụ, onStart khởi tạo bộ đếm event; onEvent tăng bộ đếm; onError đánh dấu operation thất bại; onStop tổng hợp trạng thái và ghi metrics cuối cùng.

Câu hỏi quan trọng là lưu dữ liệu đó ở đâu. Handler thường là bean dùng chung cho toàn ứng dụng và có thể nhận callback từ nhiều Observation đồng thời. Nếu lưu trạng thái của một operation vào field mutable của handler, các operation có thể ghi đè dữ liệu của nhau. Cách phù hợp là lưu state riêng vào **Observation.Context** của chính Observation đó.

Trong module **OBSERVABILITY_INSTRUMENTATION_MICROMETER**, cách tổ chức này giúp custom handler phối hợp metrics, traces và event mà vẫn giữ đúng ranh giới của từng operation.

## Vai trò của Observation.Context

### Context thuộc về một Observation

Mỗi Observation có một context đi kèm. Context giữ metadata và trạng thái của chính lần thực thi đó, ví dụ:

- Tên Observation và contextual name.
- Low-cardinality và high-cardinality key-values.
- Error được ghi nhận.
- Các event được gắn vào Observation.
- Dữ liệu bổ sung do ứng dụng hoặc handler lưu.

Handler có thể dùng context để trao đổi trạng thái giữa các callback mà không cần một map toàn cục keyed theo trace ID hoặc một ThreadLocal tự quản lý.

Ví dụ, một tác vụ xử lý message có thể lưu thời điểm bắt đầu, số lần phát event và cờ lỗi vào context. Khi onStop được gọi, handler đọc lại đúng state của tác vụ đó để ghi kết quả.

### Dùng key riêng cho dữ liệu của handler

Observation.Context cho phép lưu dữ liệu theo key. Nên dùng một key riêng, thường là một static final Object không public, để tránh xung đột với key của handler khác.

~~~java
private static final Object STATE_KEY = new Object();

context.put(STATE_KEY, new ProcessingState());
ProcessingState state = context.get(STATE_KEY);
context.remove(STATE_KEY);
~~~

Key riêng giúp handler quản lý đúng dữ liệu do chính nó sở hữu. Không dùng tên chuỗi chung chung như "state" nếu nhiều thư viện hoặc handler cùng ghi vào context.

State nên nhỏ và chỉ chứa thông tin cần cho callback tiếp theo. Tránh giữ toàn bộ request, entity lớn, payload hoặc object nghiệp vụ lâu hơn vòng đời cần thiết.

## Thứ tự và ý nghĩa của các callback

Một lifecycle phổ biến có dạng:

~~~text
create Observation
       |
       v
    onStart
       |
       +------ onEvent (zero or more times)
       |
       +------ onError (zero or one or more error reports)
       |
       v
    onStop
~~~

onEvent và onError có thể xuất hiện trong quá trình operation đang chạy. onStop là điểm kết thúc để tổng hợp state và giải phóng dữ liệu handler đã lưu.

Không nên xem callback là bốn bước luôn xuất hiện đúng một lần theo cùng một mẫu. Một Observation có thể không có event hoặc error. Một operation thành công thường không gọi onError. Việc một Observation có event hay lỗi phụ thuộc code nghiệp vụ và cách instrumentation phát tín hiệu.

### onStart: khởi tạo state

onStart là thời điểm thích hợp để tạo state ban đầu cho Observation. Handler có thể lưu Timer.Sample, timestamp, bộ đếm event hoặc trạng thái phân loại ban đầu.

Không nên khởi tạo state của mọi Observation nếu handler chỉ hỗ trợ một nhóm context. Hãy triển khai supportsContext để handler chỉ nhận loại context mà nó xử lý.

### onEvent: cập nhật state theo event

onEvent nhận Observation.Event và context tương ứng. Handler có thể tăng số event, đánh dấu một mốc đã xảy ra hoặc cập nhật state theo loại event.

Nếu event name được dùng để phân loại metrics, tập tên cần ổn định và hữu hạn. Không biến nội dung động như message ID hoặc request path đầy đủ thành tag.

### onError: ghi nhận trạng thái lỗi

onError được gọi khi Observation ghi nhận một Throwable. Handler có thể đặt cờ thất bại hoặc chuẩn hóa loại lỗi thành một nhóm giới hạn như timeout, validation, dependency hoặc internal.

Không cần giữ toàn bộ Throwable trong state của handler nếu context đã giữ error. Đặc biệt, không đưa exception message hoặc stack trace vào metric tag; chúng có thể chứa dữ liệu động và thông tin nhạy cảm.

### onStop: tổng hợp và hoàn tất

onStop là nơi phù hợp để ghi kết quả tổng hợp dựa trên state đã tích lũy. Handler có thể ghi số event, số operation thất bại, thời lượng hoặc một metric kết thúc.

Sau khi xử lý xong, nên xóa key riêng khỏi context nếu state không còn cần thiết. Việc cleanup rõ ràng giúp tránh giữ tham chiếu không cần thiết khi context được lưu hoặc truyền sang phần khác của hệ thống.

## Ví dụ: giữ số event và trạng thái lỗi đến onStop

Ví dụ sau tạo một handler cho nhóm Observation xử lý job. Handler lưu state trong context, cộng số event ở onEvent, đánh dấu lỗi ở onError và ghi hai Counter khi onStop.

### Context riêng cho nhóm job

~~~java
public final class JobObservationContext extends Observation.Context {
}
~~~

Context riêng giúp handler chỉ xử lý Observation được tạo với loại context này. Các Observation khác trong ứng dụng không bị handler can thiệp.

### State riêng cho từng lần thực thi

~~~java
final class ProcessingState {

    private final LongAdder eventCount = new LongAdder();
    private final AtomicBoolean failed = new AtomicBoolean();

    void recordEvent() {
        eventCount.increment();
    }

    long eventCount() {
        return eventCount.sum();
    }

    void markFailed() {
        failed.set(true);
    }

    boolean failed() {
        return failed.get();
    }
}
~~~

State dùng LongAdder để cộng event và AtomicBoolean để đánh dấu lỗi. Cách này an toàn hơn nếu nhiều luồng cùng cập nhật hai giá trị trong cùng một Observation. Nếu lifecycle bảo đảm mọi callback chạy tuần tự trên một luồng, có thể dùng cấu trúc đơn giản hơn; khi có context propagation hoặc callback từ nhiều luồng, cần xác định rõ quy tắc đồng bộ.

### Handler đọc và cập nhật context

~~~java
public final class JobLifecycleHandler
        implements ObservationHandler<Observation.Context> {

    private static final Object STATE_KEY = new Object();

    private final Counter events;
    private final Counter failures;

    public JobLifecycleHandler(MeterRegistry registry) {
        this.events = registry.counter("jobs.observation.events");
        this.failures = registry.counter("jobs.observation.failures");
    }

    @Override
    public boolean supportsContext(Observation.Context context) {
        return context instanceof JobObservationContext;
    }

    @Override
    public void onStart(Observation.Context context) {
        context.put(STATE_KEY, new ProcessingState());
    }

    @Override
    public void onEvent(
            Observation.Event event,
            Observation.Context context
    ) {
        ProcessingState state = context.get(STATE_KEY);
        if (state != null) {
            state.recordEvent();
        }
    }

    @Override
    public void onError(Observation.Context context) {
        ProcessingState state = context.get(STATE_KEY);
        if (state != null) {
            state.markFailed();
        }
    }

    @Override
    public void onStop(Observation.Context context) {
        ProcessingState state = context.get(STATE_KEY);
        if (state == null) {
            return;
        }

        try {
            long eventCount = state.eventCount();
            if (eventCount > 0) {
                events.increment(eventCount);
            }
            if (state.failed()) {
                failures.increment();
            }
        } finally {
            context.remove(STATE_KEY);
        }
    }
}
~~~

State được tạo ở onStart và được lấy lại bằng cùng key trong các callback sau. Mỗi Observation có context riêng nên event của job A không bị cộng vào job B. onStop ghi tổng số event và số operation thất bại, rồi xóa state.

Handler không lưu ProcessingState vào field instance. Field của handler chỉ giữ Counter dùng chung, vốn được thiết kế để ghi nhận đồng thời. Dữ liệu thay đổi theo từng operation nằm trong context.

Ví dụ này cố ý chỉ ghi hai Counter bổ sung. Nếu ứng dụng đã đăng ký metrics handler mặc định để tạo Timer từ Observation, không nên tạo thêm một Timer trùng ý nghĩa trong custom handler. Chỉ thêm metric riêng khi nó đo một khía cạnh khác mà handler mặc định không cung cấp.

## Tạo Observation với context riêng và phát event

Có thể tạo Observation bằng context supplier để handler nhận đúng loại context:

~~~java
Observation observation = Observation.createNotStarted(
    "jobs.process",
    JobObservationContext::new,
    observationRegistry
);

observation.lowCardinalityKeyValue("job.type", "reconciliation");

observation.observe(() -> {
    observation.event(Observation.Event.of("job.validated"));
    jobProcessor.validate();

    observation.event(Observation.Event.of("job.started"));
    jobProcessor.process();
});
~~~

Khi Observation bắt đầu, handler hỗ trợ JobObservationContext nhận onStart. Mỗi lần event được phát, handler nhận onEvent và tăng bộ đếm. Nếu validate hoặc process ném lỗi và lỗi được ghi vào Observation, onError đánh dấu state. Khi observe kết thúc, onStop ghi kết quả cuối.

Event name trong ví dụ là hằng số. Không thêm job ID vào event name hoặc metric tag. Nếu cần tìm một job cụ thể trong trace, hãy dùng thuộc tính trace phù hợp, đã được kiểm tra an toàn và không làm lộ dữ liệu nhạy cảm.

## Đăng ký ObservationHandler

### Với Spring Boot

Có thể đăng ký custom handler dưới dạng bean:

~~~java
@Configuration(proxyBeanMethods = false)
public class JobObservationConfiguration {

    @Bean
    ObservationHandler<Observation.Context> jobLifecycleHandler(
            MeterRegistry registry
    ) {
        return new JobLifecycleHandler(registry);
    }
}
~~~

Spring Boot có thể phát hiện các ObservationHandler bean và thêm chúng vào ObservationRegistry được auto-configure. Hành vi cụ thể cần được xác minh theo phiên bản Spring Boot và cấu hình ứng dụng.

Nếu ứng dụng tự tạo ObservationRegistry ngoài Spring Boot, cần đăng ký handler rõ ràng:

~~~java
observationRegistry.observationConfig()
    .observationHandler(jobLifecycleHandler);
~~~

Chọn một đường đăng ký phù hợp. Không thêm cùng handler hai lần vì callback có thể được gọi lặp và metrics bị ghi trùng.

### supportsContext giới hạn phạm vi handler

Một ObservationRegistry có thể có nhiều handler. Mỗi handler nên triển khai supportsContext để xác định context mà nó hiểu.

Ví dụ JobLifecycleHandler chỉ hỗ trợ JobObservationContext. Handler này không nên xử lý mọi Observation trong ứng dụng, vì có thể đọc nhầm state hoặc ghi metrics cho các operation không thuộc nhóm job.

Nếu cần handler chung cho mọi context, phải thiết kế state và key sao cho an toàn với tất cả loại Observation. Tuy nhiên, handler chuyên biệt thường dễ hiểu và dễ kiểm thử hơn.

## Không lưu state theo từng Observation vào field của handler

ObservationHandler thường là singleton hoặc được chia sẻ bởi nhiều luồng. Ví dụ sau là sai:

~~~java
public final class UnsafeHandler
        implements ObservationHandler<Observation.Context> {

    private ProcessingState currentState;

    @Override
    public void onStart(Observation.Context context) {
        currentState = new ProcessingState();
    }

    @Override
    public void onError(Observation.Context context) {
        currentState.markFailed();
    }
}
~~~

Nếu hai Observation chạy đồng thời, onStart của B có thể ghi đè currentState được tạo bởi A. Khi A nhận onError hoặc onStop, handler có thể cập nhật state của B. Kết quả là metrics sai và lỗi khó tái hiện.

Cũng không nên dùng một ThreadLocal tự quản lý làm kho state chính. Observation có thể đi qua nhiều scope hoặc thread nếu ứng dụng có context propagation; ThreadLocal dễ bị rò rỉ giữa tác vụ trên thread pool nếu không cleanup đúng cách.

Hãy dùng Observation.Context để gắn state với đúng lifecycle. Dùng scope chỉ để truy cập current observation trong phạm vi thực thi, không dùng scope thay cho nơi lưu state bền qua các callback.

## Phân biệt lifecycle callback với scope callback

ObservationHandler còn có callback liên quan đến scope như onScopeOpened, onScopeClosed và onScopeReset. Chúng không thay thế onStart, onError, onEvent hoặc onStop.

- onStart và onStop mô tả vòng đời Observation.
- onError và onEvent cập nhật thông tin của Observation.
- onScopeOpened và onScopeClosed mô tả lúc Observation trở thành hoặc rời khỏi current scope trên thread.
- onScopeReset phục vụ việc khôi phục scope theo cơ chế context.

Một Observation có thể được start, mở scope, đóng scope, rồi tiếp tục hoạt động và mở scope lại trước khi stop. Vì vậy, không xóa state của handler trong onScopeClosed. Nếu xóa ở đó, onStop có thể không còn dữ liệu đã tích lũy.

Đóng Scope đúng cách bằng try-with-resources. State thuộc context chỉ nên được cleanup khi lifecycle kết thúc hoặc theo một quy tắc sở hữu rõ ràng.

## Giữ dữ liệu nào trong context?

Context phù hợp với state nhỏ, gắn với một lần thực thi:

- Thời điểm bắt đầu hoặc Timer.Sample.
- Số event đã phát.
- Cờ có lỗi hay không.
- Nhóm outcome đã chuẩn hóa.
- Một reference an toàn cần cho handler.
- Kết quả trung gian mà callback sau cần đọc.

Tránh lưu:

- Toàn bộ request/response body.
- Entity graph hoặc object lớn.
- Credential, token, password hay dữ liệu thanh toán.
- Một collection không giới hạn theo số event.
- Thread, Executor hoặc tài nguyên phải đóng nhưng không có lifecycle quản lý.
- Throwable hoặc stack trace nếu chỉ cần cờ lỗi hay error type.

Nếu cần giữ nhiều event, đặt giới hạn hoặc chỉ lưu thống kê cần thiết. Một Observation có thể tồn tại lâu; collection tăng không giới hạn sẽ biến context thành vùng giữ bộ nhớ khó kiểm soát.

## Đồng bộ và tính an toàn đa luồng

Observation.Context gắn với một Observation, nhưng điều đó không tự bảo đảm mọi callback hoặc thao tác cập nhật state luôn diễn ra trên cùng thread. Với ứng dụng đồng bộ đơn giản, callback thường theo thứ tự trên luồng thực thi. Với async, executor hoặc context propagation, cần hiểu nơi event và error được phát.

Một số nguyên tắc:

1. Handler dùng chung không giữ mutable state của operation trong field.
2. State trong context dùng cấu trúc thread-safe nếu có thể được cập nhật từ nhiều luồng.
3. Không giả định callback sau stop là hợp lệ.
4. Không cho phép event mới đến sau khi onStop đã tổng hợp state.
5. Nếu nhiều tác vụ con cập nhật cùng Observation, cần chờ chúng hoàn tất trước khi stop hoặc đồng bộ rõ ràng.
6. Không giữ lock dài trong callback vì handler có thể chạy trên đường xử lý request.

LongAdder phù hợp cho bộ đếm được cập nhật đồng thời khi không cần snapshot tuyến tính tuyệt đối ở từng thời điểm. Nếu cần một snapshot nhất quán giữa nhiều trường, dùng synchronization hoặc một cấu trúc state có giao thức cập nhật rõ ràng.

## Hiệu năng và hành vi của handler

Callback của Observation nằm trên đường thực thi của instrumentation. Handler nên nhanh, không blocking và không thực hiện I/O mạng hoặc truy vấn database.

Không gửi HTTP request, ghi file lớn hoặc gọi service bên ngoài trong onEvent hay onStop. Nếu cần xử lý nặng, chỉ đưa một tín hiệu nhỏ vào cơ chế bất đồng bộ có giới hạn và có chính sách backpressure. Bản thân handler không nên làm chậm operation được quan sát.

Các thao tác Counter.increment thường nhẹ và thread-safe. Tuy nhiên, việc tạo meter mới theo giá trị event hoặc error động có thể gây cardinality tăng không kiểm soát. Đăng ký meter ổn định từ trước và dùng tag có tập giá trị hữu hạn.

Không để exception từ logic phụ trong handler làm thay đổi kết quả nghiệp vụ. Handler nên xử lý state null hoặc context không đầy đủ một cách an toàn và không dựa vào thứ tự đăng ký không được bảo đảm giữa các handler.

## Kiểm thử state qua các callback

### Kiểm tra đường thành công có nhiều event

Tạo một Observation với JobObservationContext, phát hai event và kết thúc thành công. Kỳ vọng event counter tăng hai, failure counter không tăng.

~~~java
Observation observation = Observation.createNotStarted(
    "jobs.process",
    JobObservationContext::new,
    observationRegistry
);

observation.observe(() -> {
    observation.event(Observation.Event.of("job.validated"));
    observation.event(Observation.Event.of("job.processed"));
});

assertThat(registry.counter("jobs.observation.events").count())
    .isEqualTo(2.0);
assertThat(registry.counter("jobs.observation.failures").count())
    .isZero();
~~~

Test cần dùng registry và handler đã được đăng ký. Nếu ObservationRegistry không có JobLifecycleHandler, Counter sẽ không được cập nhật.

### Kiểm tra onError trước onStop

Tạo một Observation mà khối mã ném exception. Xác minh lỗi được truyền đến caller, failure counter tăng đúng một và state được cleanup.

~~~java
assertThrows(IllegalStateException.class, () ->
    Observation.createNotStarted(
            "jobs.process",
            JobObservationContext::new,
            observationRegistry
        )
        .observe(() -> {
            throw new IllegalStateException("processing failed");
        })
);

assertThat(registry.counter("jobs.observation.failures").count())
    .isEqualTo(1.0);
~~~

Không so exception message thành metric tag. Test chỉ xác minh trạng thái lỗi và kết quả handler.

### Kiểm tra không rò state giữa hai Observation

Chạy hai Observation riêng với số event khác nhau và một Observation thất bại. Xác minh:

- Event count của mỗi Observation được tổng hợp độc lập.
- Lỗi của Observation A không làm Observation B bị đánh dấu lỗi.
- onStop của mỗi Observation chỉ đọc state gắn với context của nó.
- State key được remove sau khi xử lý.
- Handler vẫn đúng khi hai Observation chạy đồng thời.

Có thể dùng ExecutorService và CountDownLatch trong test concurrency để buộc hai operation chồng thời gian. Không dùng sleep tùy ý nếu có thể điều phối thứ tự bằng latch.

### Kiểm tra callback và scope

Nếu handler còn xử lý scope callback, viết test riêng để xác minh đóng/mở scope không xóa state. Một Observation có thể rời current scope rồi được mở lại trước khi stop. State cần tồn tại xuyên suốt khoảng này.

## Những sai lầm thường gặp

**Lưu state trong field của handler.** Handler dùng chung cho nhiều Observation nên dữ liệu có thể ghi đè lẫn nhau. Lưu state trong context.

**Dùng ThreadLocal thay cho context.** Observation có thể đi qua scope và thread khác. Dùng context propagation và Observation.Context đúng mục đích.

**Xóa state trong onScopeClosed.** Scope có thể đóng trước khi Observation kết thúc. Cleanup state ở onStop.

**Chỉ ghi nhận lỗi mà không tổng hợp ở onStop.** Nếu metrics cuối cùng cần count theo outcome, giữ cờ lỗi hoặc loại lỗi đã chuẩn hóa rồi ghi ở điểm kết thúc.

**Giữ toàn bộ Throwable hoặc payload.** Context có thể sống lâu hơn dự kiến và giữ nhiều object lớn. Lưu cờ lỗi hoặc error category cần thiết.

**Tạo meter theo event name động.** Giá trị động tạo nhiều series. Dùng event count tổng hoặc nhóm event có tập giá trị hữu hạn.

**Đăng ký handler hai lần.** Callback lặp có thể làm metrics tăng gấp đôi. Kiểm tra bean và đăng ký thủ công trước khi thêm handler.

**Không kiểm tra supportsContext.** Handler có thể xử lý context không đúng loại. Giới hạn handler theo context mà nó hiểu.

**Làm I/O trong callback.** Handler làm chậm request và tăng độ trễ. Giữ callback ngắn, không blocking.

**Cho phép event đến sau stop.** State đã được tổng hợp và cleanup. Đồng bộ lifecycle để mọi công việc con hoàn tất trước khi stop.

## Checklist thiết kế ObservationHandler

Trước khi triển khai handler giữ state qua nhiều callback, hãy xác minh:

1. Handler hỗ trợ loại Observation.Context nào?
2. State có được lưu trong context riêng của Observation không?
3. Key lưu state có private và duy nhất không?
4. onStart khởi tạo state đúng một lần không?
5. onEvent cập nhật state mà không tạo tag động không?
6. onError lưu trạng thái lỗi đã chuẩn hóa không?
7. onStop tổng hợp state và cleanup trong mọi trường hợp không?
8. Handler có tránh mutable state dùng chung và ThreadLocal không?
9. State có thread-safe nếu callback có thể chạy đồng thời không?
10. Scope callback có bị nhầm với lifecycle callback không?
11. Handler có nhanh, không blocking và không làm thay đổi kết quả nghiệp vụ không?
12. Kiểm thử có bao phủ success, error, nhiều event, concurrency và cleanup không?

## Kết luận

Muốn giữ dữ liệu giữa onStart, onError, onEvent và onStop, hãy gắn state vào Observation.Context của chính Observation. onStart tạo state; onEvent tích lũy event; onError đánh dấu lỗi; onStop đọc state để ghi metrics cuối cùng rồi xóa key do handler sở hữu.

ObservationHandler thường được chia sẻ giữa nhiều luồng, vì vậy không lưu state theo từng operation trong field mutable hoặc ThreadLocal. Dùng supportsContext để giới hạn phạm vi, cấu trúc thread-safe khi cần, giữ context nhỏ và không chứa dữ liệu nhạy cảm. Phân biệt lifecycle callback với scope callback, đăng ký handler đúng một lần và kiểm thử cả thành công, lỗi, nhiều event lẫn concurrency để bảo đảm dữ liệu của mỗi Observation không bị trộn lẫn.
