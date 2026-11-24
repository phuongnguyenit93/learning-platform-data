# Observation.Scope và việc đóng phạm vi đúng vòng đời

Observation.Scope xác định khoảng mã lệnh mà một Observation được xem là hiện hành trên thread đang thực thi. Khi mở scope, các ObservationHandler có thể đưa context vào ThreadLocal, chẳng hạn thông tin tracing hoặc dữ liệu để logging framework bổ sung vào MDC. Khi đóng scope, các giá trị gắn với scope được dọn dẹp và scope trước đó được khôi phục.

Scope có vòng đời riêng với Observation. Đóng scope chỉ kết thúc việc đặt Observation vào phạm vi hiện hành; thao tác này không tự dừng Observation và cũng không tự hoàn tất việc ghi nhận thời lượng. Observation vẫn cần được stop đúng lúc. Nếu quên đóng scope, thông tin context có thể rò rỉ sang công việc tiếp theo trên cùng thread. Nếu dừng Observation quá sớm, các handler có thể kết thúc phép đo khi công việc vẫn đang chạy.

Bài học thuộc module OBSERVABILITY_INSTRUMENTATION_MICROMETER. Module này hướng dẫn sử dụng Micrometer để đo lường ứng dụng Java bằng counter, gauge, timer, distribution summary và nhãn có kiểm soát; tích hợp Spring Boot, xuất metrics đến hệ giám sát, kiểm soát cardinality, kiểm thử instrumentation và diễn giải số đo vận hành.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích Observation.Scope và vai trò của scope trong vòng đời Observation.
- Phân biệt Observation.start/stop với Scope.openScope/close.
- Đọc Observation hiện hành trong phạm vi thực thi.
- Dùng try-with-resources để đóng scope ngay cả khi có exception.
- Quản lý scope lồng nhau và khôi phục scope cha theo đúng thứ tự.
- Chọn giữa observe(), scoped() và cách quản lý scope thủ công.
- Hiểu vì sao ThreadLocal scope không tự truyền sang thread khác.
- Dùng Micrometer Context Propagation hoặc Reactor Context khi chuyển thread.
- Kiểm thử việc mở, đóng và khôi phục scope.

## 1. Observation và Scope giải quyết hai việc khác nhau

Observation đại diện cho một thao tác cần quan sát, chẳng hạn xử lý đơn hàng, gọi dịch vụ thanh toán hoặc tiêu thụ một message. Nó có trạng thái bắt đầu, có thể nhận thông tin lỗi và kết thúc khi thao tác hoàn tất.

Scope biểu diễn khoảng thực thi mà Observation được đặt làm current trên thread hiện tại. Các handler có thể dựa vào sự kiện mở/đóng scope để quản lý dữ liệu theo thread.

| Thành phần | Câu hỏi được trả lời | API chính | Ý nghĩa |
| --- | --- | --- | --- |
| Observation lifecycle | Thao tác bắt đầu và kết thúc khi nào? | start(), error(), stop() | Điều khiển thời lượng và kết quả của thao tác |
| Observation scope | Trong đoạn code nào Observation là current? | openScope(), close() | Đặt và gỡ context hiện hành trên thread |
| Observation.Context | Handler cần chia sẻ dữ liệu gì? | getContext(), put(), get() | Lưu trạng thái dùng chung giữa instrumentation và handler |
| ObservationRegistry | Observation nào và handler nào đang được quản lý? | create(), getCurrentObservation() | Cấu hình và truy xuất Observation hiện hành |

Một Observation có thể đã được start nhưng chưa được đặt vào scope. Khi đó, thao tác đã bắt đầu về mặt lifecycle, nhưng các API truy xuất current observation trên thread có thể chưa tìm thấy nó.

Ngược lại, scope chỉ có ý nghĩa khi được mở cho một Observation. Scope không phải một meter và không tự tạo Timer. Metrics hoặc trace được tạo bởi các ObservationHandler đã đăng ký trong ObservationRegistry khi lifecycle tương ứng diễn ra.

## 2. Vòng đời Observation và Scope

Hai vòng đời liên quan nhưng độc lập:

~~~mermaid
flowchart TD
    A["Observation được tạo"] --> B["start()"]
    B --> C["Observation đang hoạt động"]
    C --> D["stop()"]
    D --> E["Observation kết thúc"]

    C --> F["openScope()"]
    F --> G["Scope đang mở<br/>Observation là current trên thread"]
    G --> H["close()"]
    H --> I["Scope kết thúc<br/>Khôi phục scope trước đó"]
~~~

Các sự kiện thường gặp:

- Gọi ~Observation.start()~ sẽ phát sự kiện bắt đầu cho các handler.
- Gọi ~Observation.openScope()~ mở phạm vi current và thông báo cho handler rằng scope đã được mở.
- Gọi ~Observation.Scope.close()~ đóng phạm vi current và thông báo cho handler rằng scope đã kết thúc.
- Gọi ~Observation.error(exception)~ ghi nhận lỗi vào context của Observation.
- Gọi ~Observation.stop()~ kết thúc Observation và cho phép handler hoàn tất Timer, span hoặc tín hiệu liên quan.

Scope thường được mở sau khi Observation đã start và được đóng trước khi Observation stop. Thứ tự này giúp context còn hiện hành trong toàn bộ đoạn code cần quan sát, rồi được dọn dẹp trước khi Observation hoàn tất.

### Scope không thay thế stop()

Đoạn code sau chỉ đóng scope:

~~~java
try (Observation.Scope scope = observation.openScope()) {
    processOrder();
}
~~~

Sau khối lệnh, Observation vẫn chưa được stop. Nếu không gọi stop hoặc dùng API tự quản lý lifecycle, phép đo có thể chưa hoàn tất.

Đoạn code sau chỉ stop Observation:

~~~java
observation.stop();
~~~

Lệnh này không phải cách thay thế cho việc đóng một scope đang mở. Nếu đã gọi openScope(), hãy đóng scope tương ứng trước khi stop Observation.

## 3. Mở và đóng scope bằng try-with-resources

~Observation.Scope~ triển khai ~AutoCloseable~, vì vậy Java try-with-resources là cách thông thường để quản lý scope:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

public final class OrderService {

    private final ObservationRegistry observationRegistry;

    public OrderService(ObservationRegistry observationRegistry) {
        this.observationRegistry = observationRegistry;
    }

    public void processOrder() {
        Observation observation = Observation
                .createNotStarted("order.process", observationRegistry)
                .lowCardinalityKeyValue("operation", "reserve")
                .start();

        try (Observation.Scope scope = observation.openScope()) {
            reserveInventory();
            chargePayment();
        } catch (RuntimeException | Error error) {
            observation.error(error);
            throw error;
        } finally {
            observation.stop();
        }
    }

    private void reserveInventory() {
        // Kiểm tra và giữ tồn kho
    }

    private void chargePayment() {
        // Gọi dịch vụ thanh toán
    }
}
~~~

Trong ví dụ:

1. Observation được tạo và start.
2. openScope() đặt Observation thành current trên thread.
3. Các lời gọi nghiệp vụ chạy trong scope.
4. Khi khối try kết thúc, Java tự gọi close() trên scope.
5. Nếu có RuntimeException hoặc Error, lỗi được ghi vào Observation và tiếp tục được ném ra.
6. finally gọi stop() để kết thúc Observation.

Điểm quan trọng là try-with-resources đóng scope trước khi đi vào catch hoặc finally bên ngoài. Vì vậy, scope được dọn dẹp ngay cả khi nghiệp vụ ném exception.

Không nên giữ một Scope trong field để đóng ở một thời điểm không xác định. Scope gắn với đoạn thực thi và thread đã mở nó; hãy giới hạn thời gian sống của scope bằng một khối code dễ nhận biết.

## 4. Dùng observe() khi muốn Micrometer quản lý toàn bộ vòng đời

Nếu chỉ cần bao quanh một đoạn code đồng bộ, không nhất thiết phải gọi start(), openScope(), error(), close() và stop() thủ công. API observe() thực hiện các bước này:

~~~java
Observation.createNotStarted("order.process", observationRegistry)
        .lowCardinalityKeyValue("operation", "reserve")
        .observe(() -> {
            reserveInventory();
            chargePayment();
        });
~~~

Với Supplier, observe() còn trả lại kết quả của nghiệp vụ:

~~~java
Order order = Observation.createNotStarted(
                "order.load",
                observationRegistry
        )
        .observe(() -> orderRepository.findById(orderId));
~~~

Về mặt thực thi, observe():

1. Start Observation.
2. Mở Scope.
3. Gọi Runnable hoặc Supplier.
4. Đóng Scope khi đoạn code kết thúc.
5. Ghi nhận exception nếu có rồi ném lại exception.
6. Stop Observation trong finally.

Dùng observe() khi ranh giới Observation trùng với ranh giới đoạn code cần chạy. Cách này giảm nguy cơ quên close scope hoặc stop Observation.

### scoped() chỉ quản lý phạm vi

Micrometer cũng cung cấp scoped() để chạy code bên trong scope của một Observation đã có:

~~~java
Observation parent = Observation.start(
        "http.server.request",
        observationRegistry
);

try {
    parent.scoped(() -> {
        enrichRequestContext();
        callBusinessService();
    });
} finally {
    parent.stop();
}
~~~

scoped() mở và đóng Scope cho đoạn code, đồng thời báo lỗi cho Observation nếu đoạn code ném exception. Nó không tự start hoặc stop Observation.

Phân biệt:

| API | Start Observation | Mở/đóng Scope | Báo lỗi | Stop Observation |
| --- | --- | --- | --- | --- |
| ~openScope()~ và ~close()~ | Không | Có | Không tự động | Không |
| ~scoped(...)~ | Không | Có | Có | Không |
| ~observe(...)~ | Có | Có | Có | Có |
| Quản lý thủ công | Theo code | Theo code | Theo code | Theo code |

Nếu Observation đã được start ở tầng gọi, scoped() phù hợp để đặt nó thành current trong một đoạn xử lý con. Nếu muốn một API bao trọn lifecycle, hãy dùng observe().

## 5. Current Observation và ThreadLocal

Khi scope được mở, Observation hiện hành có thể được truy xuất qua ObservationRegistry:

~~~java
Observation current = observationRegistry.getCurrentObservation();

if (current != null) {
    String name = current.getContextView().getName();
    // Sử dụng thông tin Observation hiện hành
}
~~~

Current Observation thường được lưu theo thread thông qua cơ chế context propagation. Điều này cho phép các thành phần ở sâu trong call stack truy cập context hiện tại mà không cần truyền Observation qua từng tham số method.

Ví dụ, một logging handler có thể sử dụng context hiện hành để đưa trace ID hoặc span ID vào MDC. Một tracing handler có thể đặt span tương ứng làm current để lời gọi HTTP client tiếp theo tạo span con đúng quan hệ.

Tuy nhiên, không nên giả định mọi handler đều dùng ThreadLocal. Scope chỉ phát ra sự kiện để handler triển khai hành vi tương ứng. Việc thêm MDC, span hoặc các giá trị thread-local phụ thuộc handler và accessor đã đăng ký.

Nếu không có Observation hiện hành, ~getCurrentObservation()~ có thể trả về null. Hãy kiểm tra null trước khi truy cập context.

### Scope đóng sẽ dọn context theo thread

Khi close() được gọi, handler có thể xóa các giá trị đã gắn vào ThreadLocal hoặc khôi phục giá trị trước đó. Điều này rất quan trọng với thread pool: cùng một worker thread có thể xử lý nhiều request khác nhau trong suốt vòng đời process.

Nếu scope của request A không được đóng, thread có thể tiếp tục mang context của A khi xử lý request B. Log, trace hoặc các thao tác downstream của B khi đó có thể bị gắn nhầm thông tin của A.

## 6. Scope lồng nhau và thứ tự đóng

Một thao tác lớn có thể tạo Observation con cho từng bước nhỏ. Khi parent scope đang mở, Observation con có thể được start và mở scope riêng.

~~~java
Observation parent = Observation.start(
        "checkout.process",
        observationRegistry
);

try (Observation.Scope parentScope = parent.openScope()) {
    validateOrder();

    Observation child = Observation.start(
            "checkout.payment",
            observationRegistry
    );

    try {
        try (Observation.Scope childScope = child.openScope()) {
            chargePayment();
        }
    } catch (RuntimeException | Error error) {
        child.error(error);
        throw error;
    } finally {
        child.stop();
    }

    // Sau khi child scope đóng, parent trở lại là current.
    continueCheckout();
} catch (RuntimeException | Error error) {
    parent.error(error);
    throw error;
} finally {
    parent.stop();
}
~~~

Khi child scope được mở, child là current. Khi child scope đóng, scope cha được khôi phục. Khi parent scope đóng, current Observation trước parent được khôi phục, thường là null nếu không có scope ngoài.

Quy tắc đóng là LIFO (Last In, First Out):

1. Mở parent scope.
2. Mở child scope.
3. Đóng child scope.
4. Đóng parent scope.

Try-with-resources hỗ trợ quy tắc này tự nhiên. Nếu có nhiều scope được khai báo trong cùng một try-with-resources, Java đóng chúng theo thứ tự ngược lại với thứ tự mở.

Không đóng parent scope khi child scope vẫn đang mở. Việc đóng sai thứ tự có thể làm current context bị khôi phục sai và gây rò rỉ ThreadLocal.

## 7. Scope phải được đóng trên thread đã mở nó

Scope thường gắn với ThreadLocal của thread đang thực thi. Do đó, thread mở scope cũng phải là thread đóng scope đó.

Không làm như sau:

~~~java
Observation.Scope scope = observation.openScope();

executor.submit(() -> {
    scope.close(); // Đóng scope từ thread khác
});
~~~

Scope không phải một token có thể chuyển tự do giữa các thread. Cách làm trên có thể không dọn đúng ThreadLocal của thread ban đầu và để context sai ở một hoặc cả hai thread.

Nếu công việc chuyển sang thread khác, hãy truyền context bằng cơ chế Context Propagation. Ở thread đích, cơ chế này tạo phạm vi context tương ứng và tự khôi phục khi task kết thúc.

## 8. Truyền Observation context qua Executor

Micrometer Context Propagation cung cấp ContextSnapshot và ContextExecutorService để chụp context hiện tại khi submit task rồi khôi phục nó trong thread thực thi.

Ví dụ:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import io.micrometer.context.ContextExecutorService;
import io.micrometer.context.ContextSnapshotFactory;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

public final class AsyncOrderService {

    private final ObservationRegistry registry;
    private final ExecutorService executor =
            Executors.newFixedThreadPool(4);

    private final ContextSnapshotFactory snapshotFactory =
            ContextSnapshotFactory.builder().build();

    public AsyncOrderService(ObservationRegistry registry) {
        this.registry = registry;
    }

    public void submit() {
        Observation parent = Observation.start(
                "order.submit",
                registry
        );

        ExecutorService contextAwareExecutor =
                ContextExecutorService.wrap(executor, snapshotFactory);

        try (Observation.Scope scope = parent.openScope()) {
            contextAwareExecutor.submit(() -> {
                // Context của parent được khôi phục trên worker thread.
                Observation.createNotStarted("order.persist", registry)
                        .observe(this::persistOrder);
            });
        } catch (RuntimeException | Error error) {
            parent.error(error);
            throw error;
        } finally {
            // Parent này chỉ đo thao tác submit, không đo thời gian xử lý nền.
            parent.stop();
        }
    }

    private void persistOrder() {
        // Lưu đơn hàng
    }
}
~~~

ContextExecutorService chụp context ở thời điểm submit và khôi phục context đã đăng ký trên thread thực thi. Khi task kết thúc, context được khôi phục về trạng thái trước task. Trong ví dụ, parent Observation chỉ đo thao tác submit; Observation con ~order.persist~ đo công việc thực tế trên worker.

Nếu muốn một Observation cha đo toàn bộ công việc bất đồng bộ, hãy quản lý lifecycle theo tín hiệu hoàn tất của Future hoặc CompletionStage. Chỉ gọi error() khi có lỗi và stop() sau khi công việc thực sự kết thúc. Không để observe() trả về một Future chưa hoàn tất rồi cho rằng Observation tự chờ Future đó.

Không giữ scope của thread submit mở cho đến khi task ở thread khác kết thúc. Scope ở thread submit cần được đóng ngay khi đoạn submit kết thúc; context ở thread worker được khôi phục bởi Context Propagation.

## 9. Scope trong Reactor và reactive pipeline

Reactive pipeline có thể chuyển thread giữa các operator. ThreadLocal scope không tự đi theo tín hiệu Reactor. Reactor Context là nơi lưu context theo subscription, còn Micrometer Context Propagation hỗ trợ chuyển đổi giữa Reactor Context và ThreadLocal khi cần.

Với Reactor 3.5.3 trở lên, có thể bật automatic context propagation:

~~~java
import reactor.core.publisher.Hooks;

Hooks.enableAutomaticContextPropagation();
~~~

Khi dùng Observation cùng Reactor, cần bảo đảm ObservationThreadLocalAccessor được cấu hình với ObservationRegistry phù hợp. Phiên bản Reactor, Micrometer Context Propagation, Micrometer và Micrometer Tracing phải tương thích với nhau.

Nếu code đang ở ngoài reactive chain và cần chụp ThreadLocal vào Reactor Context, có thể cần dùng operator ~contextCapture()~. Khi code nằm trong reactive chain, hãy ưu tiên đưa Observation vào Reactor Context theo đúng mô hình của ứng dụng.

Không mở một Observation.Scope thủ công rồi giả định scope sẽ tồn tại xuyên suốt Mono hoặc Flux. Subscription có thể chạy trên nhiều thread và tại nhiều thời điểm khác nhau. Hãy để Reactor Context hoặc integration được hỗ trợ quản lý việc khôi phục context cho từng callback.

## 10. Scope và Observation không phải tài nguyên giống nhau

Cần phân biệt hai loại cleanup:

- Scope cleanup: loại bỏ hoặc khôi phục context hiện hành trên thread.
- Observation cleanup: hoàn tất phép đo, Timer, span hoặc các handler liên quan.

Đóng scope không có nghĩa là span đã kết thúc. Stop Observation không có nghĩa là một scope đang mở được đóng thay bạn. Một thao tác có thể cần cả hai.

Ví dụ:

~~~java
Observation observation = Observation.start(
        "inventory.reserve",
        observationRegistry
);

try (Observation.Scope scope = observation.openScope()) {
    reserveInventory();
} finally {
    observation.stop();
}
~~~

Trong cấu trúc này, try-with-resources đảm bảo scope đóng trước khi finally chạy. finally đảm bảo Observation stop ngay cả khi reserveInventory() ném exception.

### Khi nào cần quản lý scope thủ công?

Một số tình huống cần tự gọi openScope():

- Chỉ một đoạn con của Observation cần current context.
- Observation được start ở một tầng nhưng scope chỉ mở tại tầng thực thi.
- Cần mở scope cho một Observation đã tồn tại trong callback.
- Cần quản lý quan hệ parent/child trong một đoạn code đồng bộ cụ thể.
- Cần kiểm tra current Observation hoặc context trong phạm vi giới hạn.

Nếu toàn bộ method cần được quan sát từ đầu đến cuối, observe() thường ngắn gọn và ít rủi ro hơn.

## 11. Kiểm thử việc mở và đóng scope

Có thể dùng ObservationRegistry trong bộ nhớ để kiểm tra current Observation. Test nên xác nhận cả trạng thái trong scope và trạng thái sau khi scope đóng.

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.junit.jupiter.api.Test;

class ObservationScopeTest {

    @Test
    void restoresCurrentObservationAfterScopeCloses() {
        ObservationRegistry registry = ObservationRegistry.create();

        Observation parent = Observation.start("parent", registry);

        try {
            try (Observation.Scope parentScope = parent.openScope()) {
                assertThat(registry.getCurrentObservation())
                        .isSameAs(parent);

                Observation child = Observation.start("child", registry);

                try {
                    try (Observation.Scope childScope = child.openScope()) {
                        assertThat(registry.getCurrentObservation())
                                .isSameAs(child);
                    }

                    assertThat(registry.getCurrentObservation())
                            .isSameAs(parent);
                } finally {
                    child.stop();
                }
            }

            assertThat(registry.getCurrentObservation()).isNull();
        } finally {
            parent.stop();
        }
    }
}
~~~

Test xác nhận:

- Parent trở thành current khi parent scope mở.
- Child thay parent làm current trong child scope.
- Đóng child scope khôi phục parent.
- Đóng parent scope đưa registry về trạng thái không có current Observation.
- Cả hai Observation đều được stop.

### Kiểm thử exception safety

Thêm một test cho đường exception:

~~~java
@Test
void closesScopeWhenWorkThrows() {
    ObservationRegistry registry = ObservationRegistry.create();
    Observation observation = Observation.start("operation", registry);

    try {
        try (Observation.Scope scope = observation.openScope()) {
            assertThat(registry.getCurrentObservation())
                    .isSameAs(observation);

            throw new IllegalStateException("operation failed");
        }
    } catch (IllegalStateException expected) {
        observation.error(expected);
    } finally {
        observation.stop();
    }

    assertThat(registry.getCurrentObservation()).isNull();
}
~~~

Test xác nhận scope được đóng dù code bên trong ném exception. Nếu scope không được đóng, current Observation có thể vẫn tồn tại trên thread sau test.

### Kiểm thử với ObservationHandler

Nếu muốn xác nhận handler nhận sự kiện scope, có thể đăng ký handler thử nghiệm và ghi nhận số lần mở/đóng. Handler có thể quan sát các callback lifecycle của scope. Số lần mở và đóng phải cân bằng cho mỗi đường thực thi, kể cả khi code ném exception hoặc scope lồng nhau.

Test handler giúp phát hiện các lỗi mà chỉ kiểm tra current Observation chưa thể hiện hết, chẳng hạn handler tùy chỉnh không khôi phục MDC đúng cách.

## 12. Các lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Gọi openScope() nhưng không close() | Context có thể rò rỉ sang task tiếp theo trên thread | Dùng try-with-resources |
| Nghĩ close() tự stop Observation | Timer hoặc span chưa hoàn tất | Gọi stop() đúng lifecycle |
| Gọi stop() nhưng quên close scope | Current context có thể còn tồn tại | Đóng scope trước khi stop |
| Giữ Scope trong field hoặc biến chia sẻ | Khó kiểm soát thời điểm đóng và thread sở hữu | Giới hạn Scope trong một block |
| Đóng scope trên thread khác | ThreadLocal của thread mở có thể không được dọn | Dùng Context Propagation |
| Đóng parent trước child | Khôi phục current scope sai thứ tự | Đóng LIFO bằng try-with-resources |
| Dùng observe() rồi tự mở cùng Observation thêm scope không cần thiết | Scope lồng nhau khó hiểu, dễ quản lý sai | Chỉ mở scope thủ công khi cần |
| Gọi observe() cho task async rồi trả Future ngay | Observation có thể stop khi công việc async chưa hoàn tất | Quản lý lifecycle theo completion |
| Nghĩ Scope tự tạo metrics | Không có handler hoặc Observation lifecycle tương ứng | Đăng ký ObservationHandler và quản lý start/stop |
| Giả định ThreadLocal tự truyền qua Reactor | Callback ở thread khác không thấy current Observation | Dùng Reactor Context và Context Propagation |
| Gọi reset() hoặc makeCurrent() như API thường ngày | Dùng các API low-level/deprecated và dễ phá trạng thái scope | Dùng openScope()/close() |
| Chỉ test đường thành công | Lỗi có thể làm rò context khi exception | Test cả exception và scope lồng nhau |

## 13. Checklist quản lý Scope

Trước khi đưa instrumentation vào production, hãy xác nhận:

1. Observation đã được start trước khi mở scope chưa?
2. Scope có được giới hạn trong một đoạn code rõ ràng không?
3. Mỗi openScope() có một close() tương ứng không?
4. Scope được đóng trên cùng thread đã mở nó không?
5. Scope lồng nhau có được đóng theo thứ tự ngược lại không?
6. Observation có được stop sau khi scope đóng không?
7. Exception có được gửi qua observation.error() và tiếp tục được xử lý đúng không?
8. Công việc async có dùng Context Propagation hoặc cơ chế tích hợp phù hợp không?
9. Reactive pipeline có dùng Reactor Context thay vì dựa vào ThreadLocal thuần túy không?
10. Test đã kiểm tra current Observation trước, trong và sau scope chưa?

## Kết luận

Observation.Scope xác định khoảng thực thi mà một Observation là current trên thread hiện tại. openScope() mở phạm vi, close() dọn context và khôi phục scope trước đó. Observation.start()/stop() quản lý lifecycle của thao tác; hai cặp API này bổ sung cho nhau và không thay thế nhau.

Hãy dùng try-with-resources cho mọi scope thủ công, đóng scope theo thứ tự LIFO và stop Observation sau khi phạm vi cần quan sát đã kết thúc. Khi công việc chuyển thread hoặc chạy trong Reactor, dùng Context Propagation hoặc Reactor Context để khôi phục context đúng nơi. Kiểm thử cả đường exception và scope lồng nhau giúp phát hiện context leak trước khi nó ảnh hưởng đến request hoặc task tiếp theo.

## Tài liệu tham khảo

- [Micrometer Observation: Introduction](https://docs.micrometer.io/micrometer/reference/observation/introduction.html) — vòng đời Observation, scope lifecycle và ObservationRegistry.
- [Micrometer Observation: Components](https://docs.micrometer.io/micrometer/reference/observation/components.html) — Observation.Context, ObservationHandler và cách các handler xử lý lifecycle.
- [Micrometer Observation: Instrumentation](https://docs.micrometer.io/micrometer/reference/observation/instrumenting.html) — context propagation qua Executor và Reactor.
- [Micrometer Tracing: Configuring](https://docs.micrometer.io/tracing/reference/configuring.html) — dùng Observation.Scope để đặt tracing context hiện hành và đóng scope bằng try-with-resources.
- [Observation.Scope Javadoc](https://javadoc.io/doc/io.micrometer/micrometer-observation/latest/io/micrometer/observation/Observation.Scope.html) — AutoCloseable, close() và current Observation của scope.
