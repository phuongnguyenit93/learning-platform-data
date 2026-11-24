# ObservationHandler phản ứng với các sự kiện vòng đời

Micrometer Observation tách việc đo một thao tác khỏi hành động cụ thể cần thực hiện khi thao tác bắt đầu, kết thúc, phát sinh lỗi hoặc phát ra sự kiện. Observation mô tả vòng đời của thao tác; ObservationRegistry giữ cấu hình; ObservationHandler nhận các callback để tạo metrics, span, log hoặc xử lý bổ sung.

Nhờ cách tách này, cùng một đoạn instrumentation có thể tạo Timer khi có meter handler, tạo span khi có tracing handler và phát log kiểm toán khi có handler riêng. Code nghiệp vụ chỉ cần phát tín hiệu vòng đời một lần. Registry quyết định những handler nào nhận tín hiệu đó.

## Mục tiêu

Sau bài học, bạn có thể:

- Giải thích vai trò của ObservationHandler và ObservationRegistry.
- Mô tả các callback onStart, onError, onEvent, onStop, onScopeOpened và onScopeClosed.
- Phân biệt vòng đời Observation với vòng đời Scope.
- Dùng Observation.Context để truyền trạng thái giữa các callback.
- Viết handler chỉ hỗ trợ một loại context.
- Đăng ký nhiều handler và chọn composite phù hợp.
- Hiểu cách DefaultMeterObservationHandler tạo Timer, Counter và LongTaskTimer.
- Báo lỗi, phát event và đóng scope đúng cách.
- Kiểm thử callback và xử lý các tình huống handler không được gọi.

## Các thành phần tham gia xử lý Observation

Một luồng Observation thường có bốn thành phần:

| Thành phần | Trách nhiệm |
|---|---|
| Observation | Bao quanh một thao tác và phát tín hiệu lifecycle |
| ObservationRegistry | Lưu handler, predicate, filter và convention |
| Observation.Context | Chứa dữ liệu dùng chung giữa instrumentation và các handler |
| ObservationHandler | Phản ứng với callback để tạo telemetry hoặc thực hiện hành động bổ sung |

Handler không cần biết toàn bộ logic nghiệp vụ. Nó nhận context, đọc dữ liệu cần thiết và thực hiện phần việc của mình. Ví dụ, meter handler đo duration; tracing handler tạo span; handler tùy chỉnh có thể ghi audit event hoặc cập nhật bộ đếm đang chạy.

~~~mermaid
flowchart TD
    A[Code nghiệp vụ] --> B[Observation]
    B --> C[ObservationRegistry]
    C --> D{supportsContext?}
    D -->|Có| E[ObservationHandler]
    D -->|Không| F[Bỏ qua handler này]
    E --> G[Metrics]
    E --> H[Tracing]
    E --> I[Logging / audit]
~~~

Một Observation có thể được nhiều handler xử lý nếu các handler hỗ trợ context hiện tại. Handler chỉ được gọi khi đã đăng ký trên registry và supportsContext trả về true.

## Vòng đời Observation và callback tương ứng

Các callback chính phản ánh tín hiệu mà instrumentation gửi ra:

| Tín hiệu từ Observation | Callback của handler | Thời điểm |
|---|---|---|
| start() | onStart(context) | Khi thao tác bắt đầu |
| error(exception) | onError(context) | Khi instrumentation báo lỗi |
| event(event) | onEvent(event, context) | Khi thao tác phát một sự kiện |
| stop() | onStop(context) | Khi thao tác hoàn tất |
| openScope() | onScopeOpened(context) | Khi Observation được đưa vào scope hiện tại |
| Scope.close() | onScopeClosed(context) | Khi scope được đóng |

Các tín hiệu error và event là tùy chọn. Một Observation bình thường có thể chỉ đi qua start và stop. Scope có thể được mở và đóng nhiều lần trong khi Observation vẫn đang chạy.

~~~mermaid
sequenceDiagram
    participant App as Application
    participant Obs as Observation
    participant Handler as ObservationHandler
    App->>Obs: start()
    Obs->>Handler: onStart(context)
    App->>Obs: openScope()
    Obs->>Handler: onScopeOpened(context)
    App->>Obs: event(retry)
    Obs->>Handler: onEvent(event, context)
    App->>Obs: Scope.close()
    Obs->>Handler: onScopeClosed(context)
    opt Có lỗi
        App->>Obs: error(exception)
        Obs->>Handler: onError(context)
    end
    App->>Obs: stop()
    Obs->>Handler: onStop(context)
~~~

Sơ đồ thể hiện một luồng có event, scope và lỗi. Trong thực tế, event có thể xuất hiện nhiều lần; scope cũng có thể được mở/đóng lồng nhau hoặc lặp lại. onStop chỉ phản ánh việc Observation kết thúc, không phải việc một scope riêng lẻ kết thúc.

### onStart: khởi tạo trạng thái cho một lần quan sát

onStart được gọi khi Observation bắt đầu. Handler thường dùng callback này để:

- Lưu thời điểm bắt đầu hoặc trạng thái cần dùng về sau.
- Tạo đối tượng span hoặc bắt đầu một phép đo.
- Khởi tạo thông tin cần được dọn dẹp ở onStop.
- Đọc các low-cardinality key-values đã có trong context.

Nếu handler cần lưu dữ liệu riêng cho một Observation, hãy đặt dữ liệu đó vào Observation.Context. Handler thường là singleton dùng chung cho nhiều request; lưu thời điểm bắt đầu trong field của handler sẽ làm các request ghi đè trạng thái của nhau.

### onError: tiếp nhận tín hiệu lỗi

onError được gọi khi code instrumentation gọi observation.error(exception). Handler có thể đọc lỗi qua context.getError() và:

- Ghi nhận loại lỗi đã được phân loại.
- Đánh dấu span là lỗi.
- Ghi log hoặc bổ sung thông tin chẩn đoán.
- Đặt trạng thái lỗi vào context để onStop sử dụng.

onError không thay thế onStop. Khi thao tác kết thúc do exception, handler vẫn cần hoàn tất việc dọn dẹp hoặc ghi nhận kết quả trong onStop.

Không ghi nguyên văn exception message, payload hoặc dữ liệu nhạy cảm vào metric tag. Nếu cần chi tiết điều tra, dùng log/trace với chính sách redaction phù hợp.

### onEvent: xử lý sự kiện xảy ra trong thao tác

onEvent nhận một Observation.Event cùng context. Event có thể biểu diễn một mốc trong quá trình xử lý, chẳng hạn:

- retry khi một lần thử lại được lên lịch.
- cache.refresh khi bắt đầu làm mới cache.
- message.acknowledged khi message được xác nhận.
- fallback.used khi hệ thống dùng phương án dự phòng.

Event không kết thúc Observation. Một thao tác có thể phát nhiều event trước khi stop. Handler có thể chuyển event thành span event, tăng Counter hoặc ghi log theo nhu cầu.

Tên event cần ổn định và có cardinality thấp. Không dùng event name chứa request ID, order ID hoặc thông điệp động.

### onStop: hoàn tất xử lý

onStop được gọi khi Observation kết thúc. Đây là nơi phù hợp để:

- Ghi duration hoặc tổng hợp trạng thái cuối cùng.
- Đóng tài nguyên do handler tạo ở onStart.
- Hoàn tất span hoặc ghi bản ghi kết quả.
- Đọc context sau khi filter đã áp dụng.
- Xóa trạng thái riêng của lần quan sát nếu còn cần.

Với DefaultMeterObservationHandler, Timer được ghi khi Observation dừng. Nếu Observation có lỗi, Timer có tag error; nếu không, giá trị thường là none. Handler tùy chỉnh cũng nên xem onStop là điểm kết thúc của xử lý một Observation.

### onScopeOpened và onScopeClosed: quản lý ngữ cảnh hiện hành

Scope biểu diễn khoảng thực thi mà Observation được xem là current. Handler có thể dùng callback scope để cài đặt và khôi phục ngữ cảnh như:

- Current span cho distributed tracing.
- Observation hiện tại trong ThreadLocal.
- MDC hoặc context phục vụ log correlation.
- Context cần thiết để instrumentation con tìm được parent Observation.

onScopeOpened thường cài đặt giá trị hiện tại; onScopeClosed phải khôi phục hoặc xóa giá trị đó. Việc đóng scope là bắt buộc để tránh rò rỉ context sang request tiếp theo trên cùng thread.

Scope không đồng nghĩa với Observation. Một Observation có thể được mở scope trong một đoạn xử lý, đóng scope, rồi được mở lại ở đoạn khác. Đóng scope không tự động gọi onStop.

API còn giữ callback onScopeReset để tương thích với các thao tác reset scope cũ. Các thao tác Scope.reset() và makeCurrent() đã deprecated và không còn được Micrometer gọi trong luồng thông thường; handler mới nên tập trung vào onScopeOpened và onScopeClosed.

## Observation.Context truyền trạng thái giữa các callback

Observation.Context là một container dạng map, được chia sẻ giữa instrumentation và handler trong suốt vòng đời Observation. Handler có thể ghi một giá trị ở onStart rồi đọc lại ở onStop.

Ví dụ, handler cần thời điểm bắt đầu để phát hiện thao tác chậm. Tạo kiểu dữ liệu nhỏ để giữ timestamp:

~~~java
static final class StartedAt {
    final long nanoTime;

    StartedAt(long nanoTime) {
        this.nanoTime = nanoTime;
    }
}
~~~

Trong onStart, lưu timestamp vào context:

~~~java
context.put(StartedAt.class, new StartedAt(System.nanoTime()));
~~~

Trong onStop, đọc lại:

~~~java
StartedAt startedAt = context.get(StartedAt.class);

if (startedAt != null) {
    long elapsedNanos = System.nanoTime() - startedAt.nanoTime;
    // Dùng elapsedNanos để ghi nhận hoặc phân loại thời lượng.
}
~~~

Dùng một class key riêng cho từng loại state. Tránh dùng một key chung cho nhiều handler vì chúng có thể ghi đè giá trị của nhau. Không lưu context của request vào field mutable dùng chung trong handler.

## Chỉ xử lý context mà handler hỗ trợ

ObservationHandler<T> cho phép khai báo kiểu context mà handler quan tâm. Phương thức supportsContext quyết định handler có tham gia vào Observation hiện tại không.

Ví dụ handler chỉ xử lý PaymentContext:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;

public final class PaymentAuditHandler
        implements ObservationHandler<PaymentContext> {

    @Override
    public boolean supportsContext(Observation.Context context) {
        return context instanceof PaymentContext;
    }

    @Override
    public void onStart(PaymentContext context) {
        // Xử lý khi thao tác thanh toán bắt đầu.
    }

    @Override
    public void onStop(PaymentContext context) {
        // Hoàn tất audit khi thao tác thanh toán kết thúc.
    }
}
~~~

Nếu handler hỗ trợ mọi context, có thể dùng ObservationHandler<Observation.Context>. Tuy nhiên, handler chuyên biệt nên kiểm tra đúng kiểu context để tránh xử lý nhầm HTTP, database, messaging hoặc các Observation không liên quan.

Không dùng supportsContext để kiểm tra điều kiện nghiệp vụ phức tạp. Predicate hoặc logic tại instrumentation phù hợp hơn cho việc quyết định có tạo Observation hay không.

## Ví dụ hoàn chỉnh: handler đo thời gian và ghi nhận lỗi

Ví dụ dưới đây tạo context cho thao tác thanh toán. Handler lưu timestamp ở onStart, ghi nhận nhóm lỗi ở onError, nhận event và hoàn tất thời lượng ở onStop.

~~~java
import io.micrometer.observation.Observation;

public final class PaymentContext extends Observation.Context {

    private final String operation;

    public PaymentContext(String operation) {
        this.operation = operation;
    }

    public String getOperation() {
        return operation;
    }
}
~~~

Handler:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;

public final class PaymentLifecycleHandler
        implements ObservationHandler<PaymentContext> {

    private static final class StartedAt {
        private final long nanos;

        private StartedAt(long nanos) {
            this.nanos = nanos;
        }
    }

    private static final class FailureType {
        private final String value;

        private FailureType(String value) {
            this.value = value;
        }
    }

    @Override
    public boolean supportsContext(Observation.Context context) {
        return context instanceof PaymentContext;
    }

    @Override
    public void onStart(PaymentContext context) {
        context.put(StartedAt.class, new StartedAt(System.nanoTime()));
        System.out.println("START " + context.getOperation());
    }

    @Override
    public void onError(PaymentContext context) {
        Throwable error = context.getError();
        if (error != null) {
            context.put(
                FailureType.class,
                new FailureType(error.getClass().getSimpleName())
            );
        }
    }

    @Override
    public void onEvent(
        Observation.Event event,
        PaymentContext context
    ) {
        System.out.println(
            "EVENT operation=" + context.getOperation()
                + " event=" + event
        );
    }

    @Override
    public void onScopeOpened(PaymentContext context) {
        // Có thể cài đặt context phục vụ log hoặc tracing tại đây.
    }

    @Override
    public void onScopeClosed(PaymentContext context) {
        // Khôi phục context đã cài đặt trong onScopeOpened.
    }

    @Override
    public void onStop(PaymentContext context) {
        StartedAt startedAt = context.get(StartedAt.class);
        if (startedAt == null) {
            return;
        }

        long elapsedNanos = System.nanoTime() - startedAt.nanos;
        FailureType failure = context.get(FailureType.class);

        System.out.println(
            "STOP operation=" + context.getOperation()
                + " durationNanos=" + elapsedNanos
                + " error=" + (failure == null ? "none" : failure.value)
        );
    }
}
~~~

Đăng ký handler và chạy Observation:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

ObservationRegistry registry = ObservationRegistry.create();

registry.observationConfig()
    .observationHandler(new PaymentLifecycleHandler());

PaymentContext context = new PaymentContext("authorize");

Observation.createNotStarted(
    "business.payment.authorization",
    () -> context,
    registry
).observe(() -> paymentGateway.authorize(command));
~~~

observe(...) tự quản lý start, mở scope, chạy code, đóng scope, báo lỗi nếu có và stop Observation. Nếu paymentGateway.authorize ném exception, onError nhận tín hiệu trước khi onStop hoàn tất thao tác; exception vẫn được truyền về caller.

Ví dụ này minh họa callback và context. Trong ứng dụng production, dùng logger có cấu trúc thay cho System.out, phân loại lỗi về tập giá trị ổn định và cân nhắc dùng DefaultMeterObservationHandler cho Timer thay vì tự tạo một hệ thống đo thời gian riêng.

## Tự quản lý lifecycle khi cần kiểm soát chi tiết

observe(...) phù hợp với phần lớn trường hợp. Nếu framework yêu cầu bắt đầu Observation ở một nơi và kết thúc ở nơi khác, có thể điều khiển lifecycle thủ công:

~~~java
Observation observation = Observation.start(
    "business.payment.authorization",
    () -> new PaymentContext("authorize"),
    registry
);

try (Observation.Scope scope = observation.openScope()) {
    observation.event(Observation.Event.of("gateway.request.sent"));
    paymentGateway.authorize(command);
}
catch (RuntimeException exception) {
    observation.error(exception);
    throw exception;
}
finally {
    observation.stop();
}
~~~

Trong ví dụ:

1. start kích hoạt onStart.
2. openScope kích hoạt onScopeOpened.
3. event kích hoạt onEvent.
4. Khi thoát khỏi try, scope đóng và kích hoạt onScopeClosed.
5. Nếu có exception, error kích hoạt onError.
6. stop kích hoạt onStop.

Khi tự quản lý, luôn gọi stop() trong finally và luôn đóng Scope. Không gọi error() rồi bỏ qua stop(), vì Timer hoặc tài nguyên được handler tạo ở onStart có thể không được hoàn tất.

Với checked exception, dùng observeChecked(...) hoặc API observeChecked tương ứng nếu muốn API tự quản lý việc báo lỗi và truyền exception. Không bọc exception chỉ để tránh gọi observation.error(...); hãy giữ nguyên ngữ nghĩa lỗi của ứng dụng.

## Đăng ký nhiều handler trên ObservationRegistry

Một registry có thể đăng ký nhiều handler. Ví dụ, cùng một Observation có thể được xử lý bởi meter handler và handler tùy chỉnh:

~~~java
import io.micrometer.core.instrument.observation.DefaultMeterObservationHandler;
import io.micrometer.observation.ObservationRegistry;

ObservationRegistry registry = ObservationRegistry.create();

registry.observationConfig()
    .observationHandler(
        DefaultMeterObservationHandler.builder(meterRegistry).build()
    )
    .observationHandler(new PaymentLifecycleHandler());
~~~

DefaultMeterObservationHandler tự tạo Timer, Counter event và tùy chọn LongTaskTimer. Handler tùy chỉnh có thể ghi audit hoặc thực hiện logic riêng. Mỗi handler chỉ nhận context mà supportsContext của nó chấp nhận.

Khi Spring Boot đã cấu hình ObservationRegistry và các handler tự động, hãy bổ sung handler tùy chỉnh vào registry do ứng dụng quản lý. Khi tự tạo registry độc lập, phải tự đăng ký mọi handler cần thiết. Có Observation trong code nhưng không có handler tương ứng thì sẽ không có metrics, span hoặc log do handler đó tạo ra.

## AllMatchingCompositeObservationHandler và FirstMatchingCompositeObservationHandler

Composite handler gom nhiều handler thành một nhóm và quyết định cách phân phối callback:

| Composite | Cách hoạt động | Trường hợp phù hợp |
|---|---|---|
| AllMatchingCompositeObservationHandler | Gọi tất cả handler con có supportsContext trả về true | Nhóm nhiều handler cần cùng xử lý một context |
| FirstMatchingCompositeObservationHandler | Chỉ gọi handler đầu tiên phù hợp | Chọn một handler trong nhóm các lựa chọn loại trừ nhau |

FirstMatchingCompositeObservationHandler thường được dùng trong Micrometer Tracing để chọn handler phù hợp với sender context, receiver context hoặc handler mặc định. Không nên đặt các tracing handler loại trừ nhau vào một nhóm all-matching nếu chúng có thể tạo nhiều span cho cùng một Observation.

~~~java
registry.observationConfig()
    .observationHandler(
        new ObservationHandler.AllMatchingCompositeObservationHandler(
            new PaymentAuditHandler(),
            new AnotherPaymentHandler()
        )
    );
~~~

Ví dụ trên gọi cả hai handler nếu cả hai hỗ trợ PaymentContext.

Khi cần chỉ chọn một handler:

~~~java
registry.observationConfig()
    .observationHandler(
        new ObservationHandler.FirstMatchingCompositeObservationHandler(
            senderTracingHandler,
            receiverTracingHandler,
            defaultTracingHandler
        )
    );
~~~

Thứ tự handler trong composite có ý nghĩa với loại first-matching: handler đầu tiên phù hợp sẽ được chọn. Hãy sắp xếp các trường hợp chuyên biệt trước trường hợp mặc định.

## DefaultMeterObservationHandler xử lý lifecycle ra sao?

Micrometer cung cấp DefaultMeterObservationHandler để chuyển Observation thành metrics:

| Sự kiện | Meter được tạo hoặc cập nhật | Ý nghĩa |
|---|---|---|
| onStart | LongTaskTimer nếu bật | Theo dõi Observation đang chạy |
| onEvent | Counter <observation-name>.<event-name> | Đếm số lần event được phát |
| onStop | Timer <observation-name> | Đếm số lần hoàn tất và ghi duration |

Timer có các low-cardinality key-values và tag error. Khi Observation báo lỗi, tag error mang tên class của exception; khi không có lỗi, giá trị thường là none. High-cardinality key-values không được đưa vào meter tags.

LongTaskTimer không được bật mặc định. Có thể bật qua builder:

~~~java
registry.observationConfig()
    .observationHandler(
        DefaultMeterObservationHandler.builder(meterRegistry)
            .includeActiveObservationLongTaskTimer(true)
            .build()
    );
~~~

LongTaskTimer được tạo tại onStart, vì vậy chỉ nhận low-cardinality key-values đã có ở thời điểm bắt đầu. Nếu thêm tag sau khi Observation đã start, tag đó không xuất hiện trên LongTaskTimer đang chạy.

Nếu chỉ cần đo số lần và thời lượng hoàn tất, Timer thường đủ. LongTaskTimer hữu ích khi cần nhìn thấy số thao tác đang chạy và thời gian của những thao tác chưa kết thúc, ví dụ job dài hoặc request chờ dependency.

## Phân biệt Handler, Filter và Predicate

Ba extension point này có vai trò khác nhau:

| Thành phần | Câu hỏi nó trả lời | Ví dụ |
|---|---|---|
| ObservationHandler | Khi lifecycle xảy ra, cần làm gì? | Tạo Timer, span hoặc log |
| ObservationFilter | Context cần được bổ sung/chỉnh sửa gì trước khi stop? | Thêm metadata chung trước onStop |
| ObservationPredicate | Có nên tạo Observation này không? | Bỏ qua một nhóm operation không cần đo |

ObservationFilter chạy sau khi Observation được thực thi nhưng trước khi các handler nhận onStop. Vì vậy, low/high-cardinality key-values được thêm bởi filter có thể được handler sử dụng khi hoàn tất. Filter không thay thế callback onError và không nên dùng để làm công việc ghi nhận lifecycle.

ObservationPredicate được đánh giá khi tạo Observation. Nếu predicate từ chối, Micrometer trả về no-op Observation và handler sẽ không nhận lifecycle callbacks cho lần đo đó. Khi điều tra vì sao handler không chạy, hãy kiểm tra supportsContext, predicate và registry đang được dùng.

## Những lưu ý khi viết handler production

Handler thường được gọi đồng bộ trên luồng thực thi đang phát lifecycle event. Vì vậy:

- Giữ callback ngắn và tránh I/O mạng hoặc truy vấn database đồng bộ.
- Không giữ state của từng request trong field mutable dùng chung.
- Dùng Observation.Context để truyền state giữa onStart, onError, onEvent và onStop.
- Giới hạn supportsContext vào các loại context thực sự cần xử lý.
- Đảm bảo mọi context được cài đặt trong onScopeOpened được khôi phục trong onScopeClosed.
- Không giả định một Observation chỉ có một lần mở scope.
- Không tạo metric tag từ request ID, user ID hoặc exception message.
- Không ném exception từ handler để thay đổi kết quả nghiệp vụ; callback nên xử lý lỗi nội bộ an toàn.
- Tránh ghi log toàn bộ context hoặc payload nếu chứa dữ liệu nhạy cảm.
- Dùng onStop để hoàn tất tài nguyên và state được tạo ở onStart.

Nếu cần xử lý bất đồng bộ, hãy chuyển một bản dữ liệu nhỏ, an toàn và bất biến sang queue có kiểm soát. Không giữ toàn bộ context mutable rồi xử lý sau khi Observation đã kết thúc.

## Kiểm thử handler

Có thể dùng SimpleMeterRegistry để xác minh handler metrics và một danh sách để kiểm tra thứ tự callback của handler tùy chỉnh.

Ví dụ kiểm thử lifecycle cơ bản:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;
import io.micrometer.observation.ObservationRegistry;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class ObservationHandlerTest {

    @Test
    void receivesLifecycleCallbacksInExpectedOrder() {
        ObservationRegistry registry = ObservationRegistry.create();
        List<String> calls = new ArrayList<>();

        registry.observationConfig().observationHandler(
            new ObservationHandler<Observation.Context>() {
                @Override
                public boolean supportsContext(Observation.Context context) {
                    return true;
                }

                @Override
                public void onStart(Observation.Context context) {
                    calls.add("start");
                }

                @Override
                public void onScopeOpened(Observation.Context context) {
                    calls.add("scope-open");
                }

                @Override
                public void onEvent(
                    Observation.Event event,
                    Observation.Context context
                ) {
                    calls.add("event");
                }

                @Override
                public void onScopeClosed(Observation.Context context) {
                    calls.add("scope-close");
                }

                @Override
                public void onError(Observation.Context context) {
                    calls.add("error");
                }

                @Override
                public void onStop(Observation.Context context) {
                    calls.add("stop");
                }
            }
        );

        RuntimeException failure = new IllegalStateException("expected");
        Observation observation =
            Observation.createNotStarted("test.operation", registry);

        assertThrows(IllegalStateException.class, () ->
            observation.observe(() -> {
                observation.event(Observation.Event.of("retry"));
                throw failure;
            })
        );

        assertEquals(
            List.of("start", "scope-open", "event", "scope-close", "error", "stop"),
            calls
        );
    }
}
~~~

Test trên xác nhận observe(...) tự quản lý scope, báo lỗi và stop. Nếu dùng nhiều handler hoặc composite, bổ sung test xác minh handler nào nhận context nào.

Kiểm thử DefaultMeterObservationHandler riêng:

~~~java
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import io.micrometer.core.instrument.observation.DefaultMeterObservationHandler;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

import static org.junit.jupiter.api.Assertions.assertEquals;

SimpleMeterRegistry meterRegistry = new SimpleMeterRegistry();
ObservationRegistry registry = ObservationRegistry.create();

registry.observationConfig().observationHandler(
    DefaultMeterObservationHandler.builder(meterRegistry).build()
);

Observation.createNotStarted("test.operation", registry)
    .lowCardinalityKeyValue("region", "ap-southeast-1")
    .observe(() -> {
        // Công việc cần đo.
    });

assertEquals(
    1.0,
    meterRegistry.get("test.operation").timer().count(),
    0.0
);

meterRegistry.close();
~~~

Kiểm thử này xác nhận Timer được ghi khi Observation stop. Nếu cần kiểm tra event Counter, phát một Observation.Event bên trong observe rồi kiểm tra meter có tên <observation-name>.<event-name>. Nếu cần kiểm tra LongTaskTimer, bật tùy chọn trước khi start và kiểm tra activeTasks() trong lúc Observation vẫn đang chạy.

## Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Không đăng ký handler | Observation chạy nhưng không tạo metrics/span/log | Kiểm tra handler trên đúng ObservationRegistry |
| supportsContext luôn trả false | Handler không nhận callback | Kiểm tra kiểu context thực tế |
| Quên gọi stop() | Timer không hoàn tất và state có thể bị giữ | Dùng observe hoặc finally |
| Gọi error() nhưng không stop() | Handler biết có lỗi nhưng lifecycle chưa hoàn tất | Báo lỗi rồi vẫn stop |
| Chỉ dọn dẹp trong onError | Tài nguyên không được giải phóng khi thành công | Đặt cleanup cuối cùng trong onStop |
| Quên đóng Scope | ThreadLocal hoặc current span rò sang thao tác tiếp theo | Dùng try-with-resources |
| Dùng field handler để giữ start time | Request đồng thời ghi đè state | Lưu state trong Observation.Context |
| Đưa high-cardinality key vào meter tag | Cardinality tăng mạnh | Chỉ dùng low-cardinality values cho metrics |
| Dùng AllMatching cho các tracing handler loại trừ nhau | Có thể tạo nhiều span cho một Observation | Dùng FirstMatching khi chỉ một handler được chọn |
| Dùng FirstMatching cho các handler đều cần chạy | Một số handler không nhận callback | Dùng đăng ký riêng hoặc AllMatching |
| Thực hiện I/O nặng trong callback | Tăng latency của luồng nghiệp vụ | Giữ handler ngắn và chuyển việc nặng sang xử lý bất đồng bộ có kiểm soát |
| Nghĩ event kết thúc Observation | Timer hoặc span bị kết thúc sai thời điểm | Event chỉ là tín hiệu giữa vòng đời |

## Ghi nhớ

- ObservationHandler bổ sung hành vi cho instrumentation bằng các callback lifecycle.
- supportsContext quyết định handler có xử lý loại context hiện tại không.
- onStart khởi tạo state; onError nhận lỗi; onEvent nhận sự kiện; onStop hoàn tất xử lý.
- onScopeOpened và onScopeClosed quản lý context hiện hành; Scope không đồng nghĩa với Observation.
- Dùng Observation.Context để truyền state giữa callback, tránh field mutable dùng chung.
- observe(...) tự quản lý start, scope, error và stop; code thủ công phải đóng scope và stop trong mọi nhánh.
- AllMatchingCompositeObservationHandler chạy tất cả handler phù hợp; FirstMatchingCompositeObservationHandler chọn handler phù hợp đầu tiên.
- DefaultMeterObservationHandler tạo Timer khi stop, event Counter khi phát event và LongTaskTimer khi bật tùy chọn.
- Filter chạy trước onStop; predicate có thể biến Observation thành no-op.
- Handler nên ngắn, an toàn khi chạy đồng thời và không làm thay đổi kết quả nghiệp vụ.

ObservationHandler là điểm mở rộng để một instrumentation tạo ra nhiều loại telemetry mà không gắn chặt code nghiệp vụ với từng backend. Khi callback được đặt đúng trách nhiệm, context được quản lý an toàn và scope luôn được đóng, metrics, tracing và log có thể cùng mô tả một thao tác với chi phí vận hành dễ kiểm soát.

## Tài liệu tham khảo

- [Micrometer: Observation Introduction](https://docs.micrometer.io/micrometer/reference/observation/introduction.html) — lifecycle, ObservationRegistry, context và handler callbacks.
- [Micrometer: Observation Components](https://docs.micrometer.io/micrometer/reference/observation/components.html) — ví dụ ObservationHandler, DefaultMeterObservationHandler, errors, events, filters và composites.
- [Micrometer Tracing: Configuring with Micrometer Observation](https://docs.micrometer.io/tracing/reference/configuring.html) — đăng ký tracing handlers và cách dùng FirstMatchingCompositeObservationHandler.
- [ObservationHandler API](https://javadoc.io/doc/io.micrometer/micrometer-observation/latest/io/micrometer/observation/ObservationHandler.html) — callback signatures, supportsContext và composite handlers.
- [Observation API](https://javadoc.io/doc/io.micrometer/micrometer-observation/latest/io/micrometer/observation/Observation.html) — start, stop, error, event, observe và Scope.

