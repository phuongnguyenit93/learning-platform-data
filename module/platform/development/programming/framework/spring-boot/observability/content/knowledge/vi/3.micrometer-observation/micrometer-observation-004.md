# ObservationHandler trong Micrometer Observation: xử lý vòng đời một phép quan sát

> **Chương:** Micrometer Observation  
> **Bài:** ObservationHandler  
> **Module:** SPRING_BOOT_OBSERVABILITY — Thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing. Học propagation ngữ cảnh, tag/cardinality, exporter, sampling và liên kết tín hiệu để điều tra lỗi, độ trễ và hành vi ứng dụng trên môi trường thực.

## 1. ObservationHandler giải quyết vấn đề gì?

Trong Spring Boot, chúng ta muốn đo một thao tác nghiệp vụ, chẳng hạn `orders.process`, và khai thác cùng phép đo đó cho nhiều mục đích: ghi latency, mở một span để truy vết, bổ sung sự kiện hoặc ghi log chẩn đoán. Nếu mã xử lý đơn hàng phải gọi trực tiếp API của Timer, tracer và logger tại mỗi vị trí, nghiệp vụ sẽ bị gắn chặt với các công cụ observability.

**`ObservationHandler<T extends Observation.Context>`** là thành phần phản ứng với **vòng đời** của một `Observation`. Mã nghiệp vụ chỉ cần tạo, bắt đầu, đánh dấu lỗi/sự kiện và kết thúc `Observation`; các handler đã đăng ký trong `ObservationRegistry` thực hiện phần đo lường tương ứng.

~~~mermaid
flowchart TD
    A["Mã nghiệp vụ tạo Observation"] --> B["ObservationRegistry"]
    B --> C["Observation + Context"]
    C --> D["Vòng đời: start / scope / event / error / stop"]
    D --> E["ObservationHandler"]
    E --> F["Meter handler: Timer, metrics"]
    E --> G["Tracing handler: spans"]
    E --> H["Custom handler: log, audit kỹ thuật, thống kê riêng"]
    F --> I["Metrics backend qua exporter"]
    G --> J["Tracing backend qua reporter/exporter"]
~~~

Đây là cơ chế *instrument once, observe in several ways*: một thao tác được instrument một lần; các handler quyết định tín hiệu được tạo ra. **Handler không đồng nghĩa exporter.** Handler tạo hoặc cập nhật phép đo/span/sự kiện; registry, tracer và exporter phía sau mới quyết định đường đi tới Prometheus, OTLP hoặc hệ thống khác.

Ví dụ: thao tác tạo đơn mất 240 ms. Một handler metrics có thể ghi Timer `orders.process`; một handler tracing có thể tạo span tương ứng; một handler riêng có thể ghi debug khi thao tác thất bại. Cả ba dùng cùng `Observation.Context` nhưng không nhất thiết có cùng chính sách lưu trữ và sampling.

## 2. Các thành phần cùng tham gia

| Thành phần | Trách nhiệm | Mối quan hệ với ObservationHandler |
| --- | --- | --- |
| `Observation` | Đại diện cho thao tác được theo dõi; phát sự kiện `start`, `stop`, `error`, `event` và `scope` | Kích hoạt callback của handler |
| `ObservationRegistry` | Lưu cấu hình và danh sách handler, convention, predicate, filter | Nơi đăng ký/điều phối handler |
| `Observation.Context` | Chứa metadata và dữ liệu tạm có thể thay đổi trong vòng đời | Được truyền tới callback; cho phép trao đổi trạng thái giữa các callback |
| `ObservationConvention` | Xác định tên, contextual name và key-value theo quy ước | Giúp handler nhận metadata nhất quán |
| `ObservationPredicate` | Quyết định một observation có được tạo thực sự hay trở thành no-op | Nếu bị vô hiệu, không có chuỗi callback hữu ích để xử lý |
| `ObservationFilter` | Điều chỉnh `Context` trước khi observation kết thúc | Có thể bổ sung metadata phục vụ handler lúc `onStop` |
| `ObservationHandler` | Chuyển các tín hiệu vòng đời thành tác vụ đo lường hoặc xử lý riêng | Nơi hiện thực hóa logic cho metrics/traces/logs |

Hai khái niệm dễ nhầm:

- **`Observation.Context` là dữ liệu của một lần quan sát**, không phải singleton. Có thể đặt dữ liệu tạm trong context để `onStop` đọc lại những gì `onStart` đã ghi.
- **Scope** xác định observation nào đang là *current* trong ngữ cảnh thực thi. Thời gian sống của scope **không nhất thiết trùng** thời gian sống của observation: một observation có thể mở/đóng scope nhiều lần.

Khi dùng Spring Boot Actuator, ứng dụng thường nhận được `ObservationRegistry` qua dependency injection. Đối với ứng dụng Spring Boot đã cấu hình observability, các bean thuộc loại `ObservationHandler` được Spring Boot đăng ký vào registry tự động. Vì vậy, trong ví dụ Spring Boot, tạo một bean handler là cách tích hợp tự nhiên; không cần tự tạo registry thứ hai.

## 3. API vòng đời: callback chạy vào lúc nào?

`ObservationHandler` cung cấp các callback theo sự kiện. Những hook thường dùng nhất:

| API | Điều kiện kích hoạt | Việc thường làm |
| --- | --- | --- |
| `supportsContext(Observation.Context ctx)` | Registry xét handler có hỗ trợ context hay không | Chọn loại observation/context cần xử lý |
| `onStart(T ctx)` | `observation.start()` | Lưu trạng thái ban đầu, khởi tạo công việc đo |
| `onScopeOpened(T ctx)` | `observation.openScope()` | Thiết lập ngữ cảnh hiện hành (ví dụ trace/span trong thread) |
| `onEvent(Observation.Event event, T ctx)` | `observation.event(event)` | Ghi nhận một mốc/sự kiện giữa thao tác |
| `onError(T ctx)` | `observation.error(exception)` | Đọc `ctx.getError()`, đánh dấu lỗi vào tín hiệu |
| `onScopeClosed(T ctx)` | `scope.close()` | Dọn trạng thái gắn với scope/thực thi |
| `onScopeReset(T ctx)` | Khi cơ chế quản lý scope cần reset trạng thái | Khôi phục/dọn context do handler quản lý nếu áp dụng |
| `onStop(T ctx)` | `observation.stop()` | Hoàn tất timer/span, phát số liệu cuối cùng, giải phóng tài nguyên |

Không nên hiểu bảng trên là một lịch gọi cố định cho mọi observation. Ví dụ, `onError` **chỉ xuất hiện khi lỗi được báo cho Observation**. Nếu tự quản lý start/stop mà bắt exception rồi không gọi `observation.error(ex)`, handler sẽ không biết nguyên nhân thất bại. `onEvent` chỉ xuất hiện khi mã instrument gửi sự kiện. Callback scope cũng không chạy nếu không mở scope.

Một luồng đồng bộ tiêu biểu:

~~~mermaid
sequenceDiagram
    participant App as OrderService
    participant Obs as Observation
    participant Handler as ObservationHandler
    App->>Obs: createNotStarted(...)
    App->>Obs: start()
    Obs->>Handler: onStart(ctx)
    App->>Obs: openScope()
    Obs->>Handler: onScopeOpened(ctx)
    App->>Obs: event(validation.completed)
    Obs->>Handler: onEvent(event, ctx)
    alt thao tác ném exception
        App->>Obs: error(ex)
        Obs->>Handler: onError(ctx)
    end
    App->>Obs: scope.close()
    Obs->>Handler: onScopeClosed(ctx)
    App->>Obs: stop()
    Obs->>Handler: onStop(ctx)
~~~

Thứ tự này minh họa một lần dùng `try-with-resources` bình thường, với `stop()` ở `finally`. Đừng đặt giả định về số lần mở scope hoặc thứ tự tương đối giữa nhiều handler vào business logic; mỗi handler nên đảm nhận một trách nhiệm rõ ràng.

## 4. Viết một ObservationHandler tùy chỉnh trong Spring Boot

### 4.1. Handler chỉ quan tâm phép đo xử lý đơn

Giả sử mục tiêu là ghi log kỹ thuật mức thấp khi thao tác `orders.process` bắt đầu/kết thúc, đồng thời ghi loại exception khi lỗi xảy ra. Ta không cần xây dựng lại Timer hay span vì Micrometer đã có các handler chuyên trách.

~~~java
package example.observability;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

@Component
public final class OrderLifecycleHandler
        implements ObservationHandler<Observation.Context> {

    private static final Logger log =
            LoggerFactory.getLogger(OrderLifecycleHandler.class);

    @Override
    public boolean supportsContext(Observation.Context context) {
        return "orders.process".equals(context.getName());
    }

    @Override
    public void onStart(Observation.Context context) {
        log.debug("Observation started: {}", context.getName());
    }

    @Override
    public void onEvent(
            Observation.Event event, Observation.Context context) {
        log.debug("Observation event: name={}, event={}",
                context.getName(), event.getName());
    }

    @Override
    public void onError(Observation.Context context) {
        Throwable error = context.getError();
        String errorType = error == null
                ? "unknown" : error.getClass().getSimpleName();

        log.warn("Observation failed: name={}, errorType={}",
                context.getName(), errorType);
    }

    @Override
    public void onStop(Observation.Context context) {
        log.debug("Observation stopped: {}", context.getName());
    }
}
~~~

**Điểm cần hiểu:**

1. `supportsContext` chọn đúng observation cần xử lý; các observation HTTP, JDBC hoặc nghiệp vụ khác sẽ không bị handler này ghi log. Trong sản phẩm lớn, nên ưu tiên context có kiểu riêng khi phải phân biệt nhiều loại thao tác; lọc bằng tên hữu ích cho ví dụ nhỏ.
2. `onStart` và `onStop` dùng để phản ứng với vòng đời. Trong ví dụ, chúng chỉ ghi log, không tự tạo một Timer thứ hai.
3. `onError` chỉ đọc **loại** exception, tránh đẩy thông báo lỗi chứa token, email hoặc dữ liệu nghiệp vụ vào log.
4. Handler được đăng ký như bean `@Component`. Với cấu hình auto-configuration observability của Spring Boot Actuator, Spring Boot tự đăng ký handler vào `ObservationRegistry`. Đừng đồng thời thêm chính instance đó bằng một customizer, vì dễ làm callback chạy trùng.
5. Mã callback được thực thi trên đường xử lý observation; giữ nó **nhẹ, có thể chịu lỗi** và không gọi hệ thống mạng đồng bộ cho mỗi event. Logger ở mức DEBUG tránh phát sinh lượng log khổng lồ ở traffic cao.

### 4.2. Instrument mã nghiệp vụ để kích hoạt handler

~~~java
package example.observability;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final ObservationRegistry observationRegistry;

    public OrderService(ObservationRegistry observationRegistry) {
        this.observationRegistry = observationRegistry;
    }

    public void processOrder() {
        Observation observation = Observation.createNotStarted(
                "orders.process", observationRegistry)
            .contextualName("process order")
            .lowCardinalityKeyValue("operation", "create")
            .start();

        try (Observation.Scope scope = observation.openScope()) {
            validateOrder();
            observation.event(
                    Observation.Event.of("validation.completed"));
            persistOrder();
        } catch (RuntimeException ex) {
            observation.error(ex);
            throw ex;
        } finally {
            observation.stop();
        }
    }

    private void validateOrder() {
        // Logic kiểm tra đơn hàng
    }

    private void persistOrder() {
        // Logic lưu đơn hàng
    }
}
~~~

Nếu cả hai phương thức thực thi thành công, handler nhận `onStart`, `onScopeOpened`, `onEvent`, `onScopeClosed` và `onStop`. Nếu một phương thức ném `RuntimeException`, `onError` cũng được gọi. `finally` giúp `stop()` vẫn chạy. Việc đóng scope được `try-with-resources` đảm bảo khi thoát khối, kể cả khi có exception.

Cách viết ngắn `Observation.createNotStarted(...).observe(() -> {...})` phù hợp khi không cần điều khiển scope, event hay xử lý riêng. Khi cần kiểm soát rõ các bước, mẫu `start()` + `openScope()` + `error()` + `stop()` dễ giải thích và dễ bảo trì hơn.

## 5. supportsContext và Context có kiểu riêng

`ObservationHandler<T>` có tham số kiểu `T extends Observation.Context`. Nhờ đó một handler có thể chỉ phục vụ một loại context, đồng thời truy cập những thuộc tính riêng của thao tác mà không ép sang một đối tượng toàn cục.

Giả sử trong tương lai cần thông tin trạng thái xử lý đơn, ta định nghĩa:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;

final class OrderObservationContext extends Observation.Context {
    private String phase = "received";

    public void setPhase(String phase) {
        this.phase = phase;
    }

    public String getPhase() {
        return phase;
    }
}

final class OrderPhaseHandler
        implements ObservationHandler<OrderObservationContext> {

    @Override
    public boolean supportsContext(Observation.Context context) {
        return context instanceof OrderObservationContext;
    }

    @Override
    public void onStop(OrderObservationContext context) {
        // Ví dụ: đọc context.getPhase() và xử lý nhẹ,
        // không bắt buộc tạo thêm metrics hoặc logs.
        String phase = context.getPhase();
    }
}
~~~

Để dùng handler này, tạo observation với supplier của loại context mong muốn:

~~~java
Observation observation = Observation.createNotStarted(
        "orders.process",
        OrderObservationContext::new,
        observationRegistry
).start();

try (Observation.Scope scope = observation.openScope()) {
    OrderObservationContext context =
            (OrderObservationContext) observation.getContext();
    context.setPhase("persisted");
} catch (RuntimeException ex) {
    observation.error(ex);
    throw ex;
} finally {
    observation.stop();
}
~~~

Đoạn trên minh họa API của `Context`; class `OrderPhaseHandler` cần được đăng ký (ví dụ thêm `@Component` nếu dùng Spring) để callback thực sự chạy. Trong ứng dụng thực tế, các class nên tách thành các file Java theo cấu trúc dự án và đặt `phase` theo một tập giá trị định trước.

**Context không phải tag.** Dữ liệu lưu bằng getter/setter hoặc `put/get` trên `Observation.Context` chỉ là trạng thái của quá trình quan sát. Nó không tự động trở thành metric label hoặc span attribute. Khi thật sự cần phân nhóm theo dữ liệu có **cardinality thấp**, thêm key-value bằng API observation/convention thích hợp.

## 6. Handler có sẵn: metrics, tracing và những giới hạn quan trọng

### 6.1. DefaultMeterObservationHandler

`DefaultMeterObservationHandler` (thuộc Micrometer Core) nhận các tín hiệu vòng đời và biểu diễn chúng dưới dạng meter trong `MeterRegistry`. Ở các phiên bản Micrometer hiện đại, hành vi đáng chú ý gồm:

- **Timer:** ghi thời lượng từ `start` đến `stop` theo tên observation, thường kèm các low-cardinality tags và thông tin loại lỗi.
- **Event counter:** có thể ghi số sự kiện khi `Observation.event(...)` được gọi (cách đặt tên/khả năng xuất tùy phiên bản, cấu hình và meter handler).
- **LongTaskTimer:** hỗ trợ theo dõi observation đang chạy khi được cấu hình bật; không phải mặc định mọi observation đều có LongTaskTimer.

Trong một ví dụ Java độc lập **không dùng auto-configuration của Spring Boot**, đăng ký thủ công như sau:

~~~java
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import io.micrometer.core.instrument.observation.DefaultMeterObservationHandler;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

SimpleMeterRegistry meters = new SimpleMeterRegistry();
ObservationRegistry registry = ObservationRegistry.create();

registry.observationConfig()
        .observationHandler(new DefaultMeterObservationHandler(meters));

Observation.createNotStarted("orders.process", registry)
        .lowCardinalityKeyValue("operation", "create")
        .observe(() -> {
            // Thao tác cần đo
        });

long count = meters.get("orders.process")
        .tag("operation", "create")
        .timer()
        .count();  // Sau một lần thực thi: 1
~~~

Trong ứng dụng Spring Boot có Actuator và auto-configuration, hãy sử dụng registry mà Spring cung cấp. Tạo thêm `ObservationRegistry.create()` bên trong service dễ khiến custom observations tách khỏi các handler/metric/tracing cấu hình sẵn.

### 6.2. Tracing ObservationHandlers

Micrometer Tracing cung cấp các handler phục vụ tracing, ví dụ:

- `DefaultTracingObservationHandler`: tạo/điều khiển span cho observation thông thường.
- `PropagatingSenderTracingObservationHandler`: phục vụ việc gửi trace context qua lời gọi ra ngoài.
- `PropagatingReceiverTracingObservationHandler`: phục vụ ngữ cảnh nhận ở phía server/consumer.

Các handler này thường được ghép theo chiến lược **first matching** để chọn đúng cơ chế tracing cho loại observation tương ứng. Chúng cần tracer và propagator được cấu hình đúng; đăng ký một handler tùy chỉnh không tự biến ứng dụng thành hệ thống distributed tracing.

**Sampling** được áp dụng theo cơ chế của tracing stack, không có nghĩa Micrometer tự lấy mẫu Timer metrics theo cùng tỉ lệ. Ví dụ, 100 request có thể góp vào Timer trong khi chỉ một tập con được xuất thành trace. Vì vậy đừng suy số lượng request thật bằng số trace xuất hiện trên backend.

## 7. Ghép nhiều handler: all matching và first matching

Một `ObservationRegistry` có thể có nhiều handler. Hai composite thường gặp:

| Cơ chế | Ý nghĩa | Tình huống |
| --- | --- | --- |
| `AllMatchingCompositeObservationHandler` | Cho phép tất cả handler con phù hợp nhận sự kiện | Phối hợp các khả năng độc lập cần cùng quan sát một thao tác |
| `FirstMatchingCompositeObservationHandler` | Chọn handler con phù hợp đầu tiên theo thứ tự đã cấu hình | Chọn đúng một handler trong nhóm có chức năng thay thế nhau, ví dụ các trường hợp propagation phía gửi/nhận/default |
| Đăng ký nhiều handler độc lập | Registry điều phối tới những handler được hỗ trợ | Kết hợp meter handler, tracing handler và handler riêng |

Không nên gom mọi handler vào một `FirstMatchingCompositeObservationHandler`: nếu một handler chung có `supportsContext() == true` nằm đầu tiên, các handler sau có thể không được chọn. Trái lại, chạy nhiều tracing handler cùng tạo span cho cùng một context có thể dẫn tới đo trùng.

Một sơ đồ lựa chọn phổ biến:

~~~mermaid
flowchart TD
    A["Observation"] --> B["All matching: Metrics + Custom log"]
    A --> C["Tracing composite: First matching"]
    C --> D{"Đúng context?"}
    D -->|Sender| E["PropagatingSender"]
    D -->|Receiver| F["PropagatingReceiver"]
    D -->|Mặc định| G["DefaultTracing"]
~~~

Đây là sơ đồ ý tưởng, không phải cấu hình copy-paste. Trong Spring Boot, thứ tự handler và cách kết hợp chúng phụ thuộc vào tracing auto-configuration, nên phải đối chiếu phần tích hợp thực tế trước khi thêm composite thủ công.

## 8. Tags/cardinality: handler đọc gì, exporter nhận gì?

`Observation` phân biệt hai nhóm key-value quan trọng:

| Loại | Ví dụ | Phù hợp với |
| --- | --- | --- |
| **Low cardinality** | `operation=create`, `outcome=success/error`, `http.method=POST` | Metric tags và trace/span attributes |
| **High cardinality** | `order.id`, `request.id`, identifier riêng của một thao tác | Tracing khi cần và được phép; không đưa vào labels metrics |

Handler được quyền đọc `Context`, nhưng không vì thế mà nên log hoặc xuất mọi giá trị. Trong ứng dụng thực, nội dung chi tiết có thể chứa dữ liệu cá nhân, token hoặc dữ liệu có độ phân biệt quá cao.

Ví dụ, 20 URI template × 4 method × 5 trạng thái × 8 instance đã tạo tối đa **3.200 tổ hợp nhãn** cho một phép đo trước khi tính histogram buckets. Nếu dùng `orderId` gồm 100.000 giá trị làm metric label, số chuỗi có thể tăng theo cấp số lớn hơn nhiều. Khi cần liên kết với một yêu cầu riêng, dùng trace/span ID qua logs/traces hoặc exemplar nếu backend hỗ trợ; không chèn ID vào metric label.

**Thời điểm thêm tags cũng quan trọng.** Handler metrics tạo Timer ở `onStop` có thể nhận low-cardinality key-values được bổ sung trong quá trình xử lý. Nhưng phép đo dài đang hoạt động (*LongTaskTimer*) bắt đầu tại `onStart` chỉ có các tags đã sẵn sàng ở thời điểm đó. Hãy thiết kế convention và metadata cho vòng đời cụ thể, không giả định mọi handler nhận được cùng tập tags tại mọi callback.

## 9. Scope và context propagation khi xử lý bất đồng bộ

Handler có `onScopeOpened` / `onScopeClosed` để phản ứng với việc đặt/khôi phục observation đang hoạt động. Scope thường dựa vào ngữ cảnh thực thi của thread. Hai tình huống dễ gặp:

1. **Đồng bộ:** `try (Observation.Scope scope = observation.openScope())` đảm bảo đóng scope khi kết thúc khối, kể cả exception. Scope lồng nhau phải được khôi phục đúng thứ tự.
2. **Bất đồng bộ:** thực thi trên thread khác, executor, Reactor hoặc qua HTTP có thể cần context propagation riêng. Chỉ tạo observation ở thread A **không đảm bảo** thread B tự nhận được current observation hoặc trace context.

Với Spring Boot, cần chọn cơ chế context propagation phù hợp framework và phiên bản (ví dụ task decorator cho executor hoặc Reactor context propagation). Propagator trong tracing giữ vai trò gửi/nhận trace context qua ranh giới dịch vụ. `ObservationHandler` không thể tự sửa thiếu sót truyền ngữ cảnh chỉ bằng cách triển khai thêm `onScopeOpened`.

Một lỗi phổ biến là mở scope trong handler rồi quên đóng khi xong. Cách này có thể làm rò rỉ ngữ cảnh sang request khác trên thread được tái sử dụng. Nếu handler quản lý tài nguyên theo scope, phải xây dựng cách lưu và khôi phục đối xứng, kiểm soát cả nhánh lỗi.

## 10. Khi nào dùng handler, filter, convention hay predicate?

| Nhu cầu | Nơi phù hợp | Vì sao |
| --- | --- | --- |
| Đặt tên observation và quy ước tags | `ObservationConvention` | Thống nhất metadata cho mọi lần instrument |
| Bổ sung metadata chung trước khi stop | `ObservationFilter` | Tập trung việc sửa context trước khi hoàn tất |
| Bỏ hẳn observation theo điều kiện | `ObservationPredicate` | Giảm việc tạo các quan sát không cần thiết |
| Phản ứng với start/stop/error/event/scope | `ObservationHandler` | Gắn logic vào các mốc vòng đời |
| Tạo Timer hoặc span chuẩn | Handler có sẵn từ Micrometer | Tránh lặp lại logic, tích hợp tốt với registry/exporter |
| Lọc thuộc tính HTTP theo giá trị đã định nghĩa | Convention/filter hoặc các customization của instrumentation | Dễ kiểm soát cardinality và tái sử dụng |

Một handler tùy chỉnh hợp lý nếu cần tác vụ phát sinh **vì** sự kiện vòng đời mà không được các handler chuẩn đáp ứng. Tránh viết handler chỉ để sửa tên metric mỗi lần stop, hoặc tự tạo Timer song song với `DefaultMeterObservationHandler` khi chỉ muốn đo thời lượng cơ bản.

## 11. Kiểm tra và chẩn đoán handler

### 11.1. Checklist thực nghiệm

1. Xác nhận ứng dụng có `ObservationRegistry` hoạt động; khi dùng Spring Boot, kiểm tra dependency Actuator và cấu hình observability.
2. Đảm bảo bean handler được Spring quản lý hoặc được đăng ký thủ công vào đúng registry (với ứng dụng Java độc lập).
3. Tạo một observation khớp điều kiện `supportsContext`.
4. Phát lần lượt một `event`, một lỗi có kiểm soát và `stop`; quan sát callback tương ứng.
5. Với metrics, kiểm tra Timer/count/low-cardinality tags trong `MeterRegistry` hoặc endpoint Actuator/exporter đã cấu hình.
6. Với tracing, kiểm tra tracing dependencies, sampler, propagator, exporter và quan hệ parent/child của span; đừng kết luận handler không chạy chỉ vì không thấy trace được export.

### 11.2. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Không có callback | Handler chưa đăng ký, dùng sai registry, `supportsContext` trả `false` hoặc predicate chặn | Kiểm tra bean, registry được inject, điều kiện hỗ trợ và bộ lọc |
| Có `onStart` nhưng không có `onStop` | Thiếu `stop()` ở một nhánh hoặc thao tác chưa hoàn tất | Dùng `finally`; với async, dừng khi công việc thực sự xong |
| Không nhận `onError` khi code ném exception | Instrument thủ công quên gọi `observation.error(ex)` | Báo lỗi trước khi ném lại trong `catch` |
| Callback chạy lặp hoặc Timer/span bị đếm đôi | Cùng handler đăng ký hai lần hoặc nhiều handler cùng nhiệm vụ | Rà soát bean và registration thủ công; cấu hình composite phù hợp |
| Metrics có nhưng traces không xuất hiện | Chưa có tracing handler/exporter, propagation sai hoặc trace bị sampling | Kiểm tra tracing pipeline và sampler riêng |
| Context ở thread khác bị mất | Scope/current observation không được propagate | Kiểm tra executor decorator, Reactor và propagator của request xuyên dịch vụ |
| Quá nhiều series hoặc log | Low-cardinality tags bị lạm dụng, handler log quá chi tiết | Giới hạn giá trị tag, dùng log level phù hợp và thống kê chi phí |
| Tag trong `onStart` khác tag trong `onStop` | Metadata được bổ sung sau thời điểm bắt đầu | Xác định rõ khi nào convention/filter/logic nghiệp vụ thêm tags |

### 11.3. Mô hình kiểm tra bằng registry độc lập

Khi muốn hiểu chính xác giao thức callback mà không phụ thuộc network hay tracing backend, dựng `ObservationRegistry.create()` và một handler thử nghiệm đếm callback trong bộ nhớ. Điều cốt lõi là kiểm tra **tương ứng giữa API gọi và callback nhận được**, chẳng hạn:

- `start()` đúng một lần → `onStart` có mặt.
- `event(Observation.Event.of("validated"))` → `onEvent` nhận tên `validated`.
- `error(exception)` → `onError` đọc được exception từ `Context`.
- `openScope()` / `close()` → mở/đóng scope cân bằng.
- `stop()` trong `finally` → `onStop` được gọi cả khi nghiệp vụ thất bại.

Đây là kiểm tra có mục tiêu đối với handler; việc nhận được callback **không tự chứng minh** metrics đã được scrape hay traces đã tới backend. Cần kiểm tra từng chặng exporter riêng.

## 12. Tình huống tổng hợp: điều tra một API chậm và lỗi

Giả sử sau khi deploy, API `POST /api/orders` có p95 từ 150 ms tăng lên 800 ms, tỉ lệ 5xx tăng 0,2% → 3%, trong khi request rate gần như không đổi.

1. **Metrics handler** ghi nhận thay đổi Timer và số lỗi theo các tag hữu hạn như route/status. Dashboard xác định thời điểm bắt đầu suy giảm.
2. **Tracing handler** tạo span theo một số request (tùy sampler). Nếu propagation được cấu hình, trace nối server span với các lời gọi database/downstream.
3. **Custom handler** có thể ghi sự kiện kỹ thuật `validation.completed` hoặc loại exception; nội dung log cần đủ dùng cho điều tra và tránh dữ liệu nhạy cảm.
4. **Correlation:** tra cứu logs theo thời gian và trace ID, mở trace chậm để phân rã thời gian, kiểm chứng giả thuyết DB timeout hay downstream chậm.
5. **Xác minh sau khắc phục:** theo dõi p95, tỉ lệ lỗi và saturation trở về ngưỡng mong muốn. Một span riêng lẻ chỉ minh họa nguyên nhân tiềm năng, còn metrics xác nhận xu hướng toàn dịch vụ.

Mối quan hệ cần nhớ: **ObservationHandler là điểm nối giữa mã instrument nghiệp vụ và các tín hiệu quan sát**. Chất lượng chẩn đoán cuối cùng còn phụ thuộc định nghĩa metric, cách dùng tags, truyền ngữ cảnh, sampling và khả năng kết nối logs–metrics–traces ở môi trường thực.

## 13. Bài thực hành

Viết một service Spring Boot có `ObservationRegistry` và một custom handler quan sát `inventory.reserve`. Tự trả lời các câu hỏi sau bằng cách chạy thử:

1. Nếu gọi `createNotStarted(...)` nhưng không gọi `start()`, callback nào sẽ được phát?
2. Nếu tự quản lý observation và ném exception mà không gọi `error(ex)`, handler có biết loại lỗi không?
3. Nếu `supportsContext` chỉ chấp nhận `OrderObservationContext`, một observation tạo bằng `new Observation.Context()` có kích hoạt handler không?
4. Một observation mở và đóng scope hai lần nhưng chỉ start/stop một lần sẽ có bao nhiêu sự kiện scope và stop?
5. Khi thêm `sessionId` vào low-cardinality tags, chi phí time series có thể thay đổi như thế nào? Nếu cần ID để điều tra, nên lưu ở tín hiệu nào?
6. Nếu trên máy phát triển có metrics nhưng không có traces, hãy liệt kê các chặng của tracing pipeline cần xác minh, bao gồm sampler và exporter.

**Tiêu chí hoàn thành:** mô tả đúng nhiệm vụ và vòng đời `ObservationHandler`, tự viết một handler sử dụng `supportsContext` cùng `onError/onStop`, phân biệt registry/handler/exporter, biết cách tránh đo trùng, quản lý scope và giới hạn cardinality.

## Ghi nhớ

- `Observation` phát sự kiện; `ObservationRegistry` điều phối; `ObservationHandler` chuyển sự kiện thành hành vi như cập nhật Timer, span hoặc log kỹ thuật.
- `supportsContext` xác định handler áp dụng cho loại context nào; `onError` cần lỗi được báo qua `observation.error(ex)` khi instrument thủ công.
- Scope đại diện cho current observation; mở/đóng scope và start/stop observation là hai trách nhiệm khác nhau.
- Trong Spring Boot có Actuator, đăng ký handler bằng bean và tận dụng registry được auto-configure.
- Dùng meter/tracing handlers có sẵn khi phù hợp; chú ý composite, exporter, tracing sampling, context propagation và tag cardinality.

## Tài liệu tham khảo

- [Micrometer Observation — Introduction](https://docs.micrometer.io/micrometer/reference/observation/introduction.html)
- [Micrometer Observation — Components](https://docs.micrometer.io/micrometer/reference/observation/components.html)
- [Micrometer Tracing — Configuring with Micrometer Observation](https://docs.micrometer.io/tracing/reference/configuring.html)
- [Spring Boot Reference — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)

