# Mở rộng registry hoặc event consumer mà không chặn đường xử lý chính

Circuit Breaker phát ra sự kiện khi lời gọi thành công, thất bại, bị đánh dấu là chậm hoặc khi breaker chuyển trạng thái CLOSED, OPEN và HALF_OPEN. Các sự kiện này giúp ứng dụng quan sát tình trạng dependency, cập nhật metric và phát cảnh báo. Tuy nhiên, listener của Resilience4j thường được gọi ngay trên luồng đang phát sự kiện. Nếu listener thực hiện ghi log đồng bộ, gọi HTTP, gửi message hoặc truy vấn cơ sở dữ liệu, chính phần quan sát có thể làm chậm lời gọi đang được bảo vệ.

Trong chương **Registry và sự kiện** của module SPRING_CLOUD_CIRCUIT_BREAKER, bài này trình bày cách mở rộng CircuitBreakerRegistry để theo dõi cả instance hiện có và instance được tạo về sau, cách dùng EventConsumerRegistry để giữ lịch sử sự kiện có giới hạn, và cách chuyển công việc tốn thời gian sang hàng đợi bất đồng bộ có giới hạn. Mục tiêu là quan sát được hệ thống mà không biến event listener thành một dependency mới trên đường xử lý request.

## 1. Các loại sự kiện cần quan sát

Một Circuit Breaker phát ra nhiều loại sự kiện trong vòng đời của nó:

| Nhóm sự kiện | Ví dụ | Ý nghĩa vận hành |
|---|---|---|
| Kết quả lời gọi | success, error, ignored error | Biết dependency đang trả kết quả như thế nào |
| Độ trễ | slow call, slow call rate exceeded | Phát hiện dependency phản hồi chậm trước khi timeout hàng loạt |
| Trạng thái | state transition | Biết breaker chuyển CLOSED, OPEN hoặc HALF_OPEN |
| Từ chối lời gọi | call not permitted | Đếm số request bị fail fast khi breaker OPEN |
| Vòng đời registry | entry added, entry removed, entry replaced | Theo dõi khi breaker được tạo, gỡ bỏ hoặc thay thế |

Các sự kiện có thể được dùng để:

- Cập nhật counter, timer và gauge trong Micrometer.
- Ghi nhận chuyển trạng thái để vận hành biết dependency nào đang OPEN.
- Phát cảnh báo khi breaker mở kéo dài hoặc liên tục chuyển qua lại.
- Lưu dấu vết sự cố để đối chiếu với log và distributed trace.
- Phân tích tỷ lệ lỗi, lời gọi chậm và số request bị từ chối.

Không phải sự kiện nào cũng cần gửi tới hệ thống bên ngoài. Với metric, thường nên cập nhật bộ đếm trong bộ nhớ. Với log hoặc notification, chỉ nên gửi các sự kiện có ý nghĩa và có kiểm soát tần suất để tránh tạo lượng dữ liệu quá lớn khi dependency gặp sự cố.

## 2. Phân biệt Registry event và Circuit Breaker event

Có hai lớp sự kiện khác nhau:

- **Registry event** mô tả vòng đời của các entry trong registry, ví dụ một Circuit Breaker mới được thêm vào hoặc bị gỡ bỏ.
- **Circuit Breaker event** mô tả hoạt động của một instance, ví dụ lời gọi thành công, lỗi, slow call hoặc state transition.

Nếu chỉ đăng ký listener trực tiếp lên một Circuit Breaker được tạo sẵn, ứng dụng sẽ không tự động theo dõi những instance được tạo sau đó. Muốn mở rộng cho toàn bộ registry, hãy đăng ký listener vòng đời trước, sau đó gắn listener hoạt động vào từng entry mới.

Ví dụ với Resilience4j CircuitBreakerRegistry:

~~~java
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;

import jakarta.annotation.PostConstruct;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.stereotype.Component;

@Component
public class CircuitBreakerRegistryObserver {
    private final CircuitBreakerRegistry registry;
    private final CircuitBreakerEventBridge eventBridge;
    private final Set<String> attached = ConcurrentHashMap.newKeySet();

    public CircuitBreakerRegistryObserver(
            CircuitBreakerRegistry registry,
            CircuitBreakerEventBridge eventBridge) {
        this.registry = registry;
        this.eventBridge = eventBridge;
    }

    @PostConstruct
    void subscribeToRegistry() {
        // Theo dõi instance được thêm sau khi listener đã đăng ký.
        registry.getEventPublisher()
            .onEntryAdded(event -> attach(event.getAddedEntry()));

        // Gắn listener cho các instance đã tồn tại.
        registry.getAllCircuitBreakers().forEach(this::attach);
    }

    private void attach(CircuitBreaker circuitBreaker) {
        // Tránh đăng ký trùng khi entry xuất hiện đồng thời ở hai bước trên.
        if (!attached.add(circuitBreaker.getName())) {
            return;
        }

        circuitBreaker.getEventPublisher()
            .onEvent(eventBridge::enqueue);
    }
}
~~~

Listener registry được đăng ký trước khi duyệt các entry hiện có. Nếu một entry mới xuất hiện đúng lúc vòng lặp đang chạy, nó có thể được nhìn thấy ở cả hai nơi; tập tên trong ConcurrentHashMap ngăn việc gắn listener hai lần.

Trong ứng dụng dùng Spring Cloud CircuitBreaker, cần bảo đảm registry được inject ở đây chính là registry mà factory dùng để tạo các instance cần quan sát. Cách tạo và chia sẻ registry phụ thuộc phiên bản starter và cấu hình ứng dụng. Nếu factory đang dùng registry nội bộ khác, listener trên một registry độc lập sẽ không nhận sự kiện từ những breaker do factory tạo ra. Hãy cấu hình dùng chung registry hoặc đăng ký trực tiếp lên instance do factory cung cấp.

## 3. EventPublisher và giới hạn của listener đồng bộ

Resilience4j cung cấp EventPublisher trên từng Circuit Breaker. Có thể đăng ký callback theo loại sự kiện:

~~~java
circuitBreaker.getEventPublisher()
    .onSuccess(event -> metrics.recordSuccess(event))
    .onError(event -> metrics.recordError(event))
    .onStateTransition(event -> metrics.recordTransition(event))
    .onCallNotPermitted(event -> metrics.recordRejected(event));
~~~

Hoặc đăng ký một consumer nhận mọi sự kiện:

~~~java
circuitBreaker.getEventPublisher()
    .onEvent(event -> eventBridge.enqueue(event));
~~~

Điểm cần chú ý là callback thường được gọi trực tiếp khi Resilience4j phát sự kiện. Tùy loại sự kiện và phiên bản, callback có thể chạy trên luồng đang thực hiện lời gọi được bảo vệ hoặc luồng đang thực hiện chuyển trạng thái. Vì vậy, hãy xem listener là một phần có thể ảnh hưởng tới latency của luồng phát sự kiện.

Các thao tác sau không nên thực hiện trực tiếp trong callback:

- Gọi HTTP tới monitoring server hoặc notification service.
- Gửi message đồng bộ tới broker.
- Ghi dữ liệu vào cơ sở dữ liệu qua I/O blocking.
- Đọc file hoặc gọi dịch vụ bên ngoài.
- Chạy truy vấn tổng hợp hoặc xử lý dữ liệu lớn.
- Chờ lock, semaphore hoặc queue slot trong thời gian dài.

Nếu callback mất 100 ms để gửi cảnh báo, lời gọi dependency có thể phải chờ thêm 100 ms dù request đã nhận được response. Nếu dependency lỗi hàng loạt và mỗi request đều phát event, thời gian bị cộng thêm sẽ làm sự cố lan sang service gọi.

Listener nên làm công việc rất ngắn: lấy các trường cần thiết, cập nhật counter nhẹ hoặc đưa sự kiện vào hàng đợi có giới hạn rồi trả về.

## 4. Dùng EventConsumerRegistry để lưu lịch sử có giới hạn

Resilience4j có EventConsumerRegistry và EventConsumer để giữ một số lượng sự kiện gần nhất trong bộ nhớ. Đây là cách tiện lợi để kiểm tra sự kiện gần đây hoặc cung cấp dữ liệu cho endpoint chẩn đoán.

Ví dụ:

~~~java
import io.github.resilience4j.core.EventConsumer;
import io.github.resilience4j.core.EventConsumerRegistry;
import io.github.resilience4j.circuitbreaker.event.CircuitBreakerEvent;

EventConsumerRegistry<CircuitBreakerEvent> consumers =
    new EventConsumerRegistry<>();

EventConsumer<CircuitBreakerEvent> recentEvents =
    consumers.createEventConsumer("catalog-read-events", 100);

circuitBreaker.getEventPublisher().onEvent(recentEvents);
~~~

Với cấu hình trên, consumer giữ tối đa 100 sự kiện gần nhất cho Circuit Breaker được gắn vào. Có thể đọc snapshot lịch sử bằng:

~~~java
List<CircuitBreakerEvent> events = recentEvents.getBufferedEvents();
CircuitBreakerEvent latest = recentEvents.getLatestEvent();
~~~

EventConsumerRegistry hữu ích cho lịch sử ngắn hạn trong bộ nhớ, nhưng cần hiểu giới hạn của nó:

- Buffer có kích thước cố định; sự kiện cũ sẽ bị loại khi buffer đầy.
- Dữ liệu không bền vững qua lần khởi động lại ứng dụng.
- Buffer không phải message broker và không bảo đảm xử lý ít nhất một lần hoặc đúng một lần.
- Đăng ký EventConsumer không tự tạo một worker bất đồng bộ để xử lý sự kiện.
- Consumer nhận sự kiện trong đường phát event; thao tác ghi vào buffer không biến callback thành một pipeline I/O nền.

Vì vậy, dùng EventConsumerRegistry để xem lại các sự kiện gần nhất, hỗ trợ debug hoặc hiển thị trạng thái. Nếu cần gửi dữ liệu sang hệ thống khác hoặc thực hiện xử lý tốn thời gian, hãy tách công việc sang một cơ chế bất đồng bộ riêng.

## 5. Chuyển xử lý nặng sang hàng đợi có giới hạn

Một mẫu phổ biến là dùng một executor có queue bounded. Listener chỉ gọi execute để chuyển event sang worker; worker mới thực hiện ghi log, gửi message hoặc cập nhật hệ thống bên ngoài.

Cấu hình executor:

~~~java
import java.util.concurrent.ThreadPoolExecutor;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class CircuitBreakerEventExecutorConfiguration {

    @Bean
    ThreadPoolTaskExecutor circuitBreakerEventExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(1);
        executor.setMaxPoolSize(2);
        executor.setQueueCapacity(500);
        executor.setThreadNamePrefix("cb-event-");
        executor.setRejectedExecutionHandler(
            new ThreadPoolExecutor.AbortPolicy()
        );
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(5);
        return executor;
    }
}
~~~

Queue có 500 phần tử và tối đa hai worker thread trong ví dụ. Khi queue đầy, AbortPolicy từ chối tác vụ mới thay vì chạy tác vụ trên thread phát event. Điều này quan trọng: nếu dùng CallerRunsPolicy, callback có thể phải tự chạy công việc nặng khi executor quá tải, làm mất mục tiêu không chặn đường xử lý chính.

Bridge nhận event và đẩy sang executor:

~~~java
import io.github.resilience4j.circuitbreaker.event.CircuitBreakerEvent;

import java.util.concurrent.atomic.LongAdder;

import org.springframework.core.task.TaskRejectedException;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Component;

@Component
public class CircuitBreakerEventBridge {
    private final ThreadPoolTaskExecutor executor;
    private final CircuitBreakerEventHandler handler;
    private final LongAdder droppedEvents = new LongAdder();

    public CircuitBreakerEventBridge(
            ThreadPoolTaskExecutor circuitBreakerEventExecutor,
            CircuitBreakerEventHandler handler) {
        this.executor = circuitBreakerEventExecutor;
        this.handler = handler;
    }

    public void enqueue(CircuitBreakerEvent event) {
        try {
            executor.execute(() -> handler.handle(event));
        } catch (TaskRejectedException rejected) {
            // Không chờ queue và không chạy handler trên request thread.
            droppedEvents.increment();
        }
    }

    public long getDroppedEventCount() {
        return droppedEvents.sum();
    }
}
~~~

Handler chạy trên worker thread:

~~~java
@Component
public class CircuitBreakerEventHandler {
    public void handle(CircuitBreakerEvent event) {
        // Thực hiện công việc có thể chậm tại đây:
        // cập nhật hệ thống telemetry, ghi log có chọn lọc hoặc gửi notification.
        // Nếu I/O thất bại, ghi nhận lỗi xử lý event và áp dụng retry riêng.
    }
}
~~~

Trong thực tế, nên có metric cho số event bị drop, queue depth, thời gian xử lý và số lỗi của handler. Queue bounded buộc hệ thống có chính sách rõ ràng khi tốc độ phát event cao hơn tốc độ xử lý. Đối với metric quan trọng như số lần OPEN, có thể cập nhật counter nhẹ ngay trong listener rồi gửi notification bất đồng bộ. Với log chi tiết của từng request, có thể lấy mẫu hoặc giới hạn tần suất.

## 6. Không dùng hàng đợi không giới hạn

Một queue không giới hạn có vẻ giúp listener luôn gửi event thành công, nhưng khi dependency gặp sự cố, lượng event có thể tăng nhanh hơn tốc độ worker xử lý. Queue tiếp tục phình ra, chiếm heap và tạo độ trễ lớn. Hệ thống có thể hết bộ nhớ hoặc xử lý những cảnh báo đã lỗi thời sau khi sự cố kết thúc.

Khi chọn queue capacity, cần xem xét:

- Tốc độ phát event bình thường và trong sự cố.
- Thời gian trung bình worker xử lý một event.
- Số worker thread và năng lực I/O phía sau.
- Mức độ quan trọng của từng loại event.
- Hành vi khi queue đầy: drop, sample, coalesce hoặc ghi metric tổng hợp.

Không phải mọi event đều có giá trị như nhau. Ví dụ, hàng nghìn success event trong một phút có thể được tổng hợp thành counter; state transition OPEN hoặc HALF_OPEN có giá trị chẩn đoán cao hơn và có thể cần được ưu tiên. Có thể dùng một queue riêng cho sự kiện trạng thái hoặc giữ counter tại chỗ để không làm mất thông tin quan trọng khi queue đầy.

Nếu cần bảo đảm lưu trữ sự kiện quan trọng qua restart, hãy dùng một cơ chế bền vững phù hợp và chấp nhận chi phí I/O, nhưng không ghi trực tiếp vào kho bền vững trên luồng request. Một outbox hoặc message broker có thể phù hợp khi ứng dụng cần độ tin cậy cao; cần thiết kế giới hạn, retry và xử lý trùng ở tầng worker.

## 7. Theo dõi entry được thêm và gỡ khỏi registry

Khi registry quản lý nhiều Circuit Breaker theo ID, có thể gắn listener khi entry được tạo và tháo các tài nguyên liên quan khi entry bị xóa. Ví dụ:

~~~java
registry.getEventPublisher()
    .onEntryAdded(event -> {
        CircuitBreaker added = event.getAddedEntry();
        eventBridge.attach(added);
    })
    .onEntryRemoved(event -> {
        CircuitBreaker removed = event.getRemovedEntry();
        eventBridge.detach(removed.getName());
    });
~~~

Tên method của entry event có thể phụ thuộc kiểu registry và phiên bản Resilience4j; dùng API tương ứng trong phiên bản được dự án quản lý. Ý tưởng là listener vòng đời phải theo dõi cả việc thêm và gỡ entry. Nếu ứng dụng có thể thay thế entry, cũng cần xử lý sự kiện thay thế để gắn listener vào instance mới.

Một tập tên đã gắn listener giúp tránh đăng ký trùng. Khi entry bị gỡ, hãy cập nhật tập theo dõi và giải phóng subscription hoặc reference nếu API phiên bản đang dùng cung cấp cơ chế tháo listener. Không giữ reference vô thời hạn tới những breaker đã bị loại bỏ, vì registry động có thể làm tăng bộ nhớ theo thời gian.

Nếu registry được tạo lại theo từng context hoặc tenant, event bridge cần có phạm vi vòng đời tương ứng. Tránh một static registry hoặc static map dùng chung cho mọi application context vì dễ làm rò rỉ trạng thái giữa test, tenant hoặc lần khởi động.

## 8. Giữ callback nhỏ và tránh tạo vòng lặp sự kiện

Một event handler có thể vô tình tạo thêm event. Ví dụ, khi breaker chuyển OPEN, handler gọi một endpoint monitoring; endpoint đó lại gọi dependency được bảo vệ và tạo thêm sự kiện. Hoặc handler ghi vào một dịch vụ mà chính nó cũng được bảo vệ bằng Circuit Breaker đang theo dõi. Điều này có thể tạo vòng lặp hoặc làm số liệu khó giải thích.

Để tránh:

- Không gọi dependency được bảo vệ từ callback của chính breaker đó.
- Không dùng event handler để thực hiện fallback cho request đã phát event.
- Không ghi metric bằng một client HTTP đồng bộ trong callback.
- Dùng ID riêng cho dependency phục vụ telemetry nếu cần gọi mạng.
- Đặt timeout, Bulkhead và Circuit Breaker cho luồng telemetry như một dependency độc lập.
- Không phát lại cùng một event theo cách khiến handler tự kích hoạt vô hạn.

Sự kiện là tín hiệu quan sát, không phải nơi điều phối nghiệp vụ của request. Logic fallback nên nằm trong lời gọi được bảo vệ; logic telemetry nên tách biệt và có thể thất bại mà không ảnh hưởng kết quả chính.

## 9. Tránh cardinality cao khi chuyển event thành metric

Khi chuyển Circuit Breaker event thành metric, hãy chọn tag có số lượng giá trị hữu hạn. Tên breaker thường là tag hữu ích nếu số lượng breaker được kiểm soát. Event type và outcome cũng là các tag có miền giá trị nhỏ.

Không nên dùng các giá trị sau làm tag metric:

- User ID hoặc account ID.
- Request ID hoặc correlation ID.
- URL đầy đủ có path parameter.
- Exception message chứa dữ liệu động.
- Product ID, order ID hoặc transaction ID.

Các tag có vô số giá trị tạo high cardinality, làm tăng bộ nhớ và chi phí của hệ thống metrics. Những thông tin cần truy vết từng request nên đặt trong log hoặc trace, không phải tag của counter.

Một cách phân loại metric:

| Metric | Tag phù hợp |
|---|---|
| Số lần state transition | breaker name, from state, to state |
| Số lần lời gọi lỗi | breaker name, error category |
| Số lời gọi bị từ chối | breaker name |
| Số event bị drop | queue/consumer name |
| Thời gian xử lý event | handler name, outcome |

Nếu dùng Micrometer, có thể cập nhật counter và timer trong listener với thao tác ngắn. Các thao tác export hoặc gửi dữ liệu tới backend được thực hiện bởi registry và exporter riêng, không nên tự gọi HTTP trong listener.

## 10. Kiểm tra listener không làm chậm đường xử lý chính

Một bài kiểm tra cần xác minh cả tính đúng của sự kiện lẫn ảnh hưởng latency:

1. Tạo Circuit Breaker và đăng ký listener; xác nhận listener nhận event success, error và state transition.
2. Tạo thêm một breaker sau khi registry listener đã đăng ký; xác nhận instance mới cũng được gắn event listener.
3. Tạo nhiều event liên tiếp; xác nhận EventConsumer buffer chỉ giữ số lượng giới hạn.
4. Làm chậm worker handler có chủ đích; xác nhận request được bảo vệ không phải chờ I/O của handler.
5. Làm đầy executor queue; xác nhận callback trả về nhanh, số event drop tăng và không chạy handler trên caller thread.
6. Gỡ hoặc thay thế entry; xác nhận listener mới được gắn và reference cũ được quản lý.
7. Kiểm tra shutdown; xác nhận worker dừng trong thời gian giới hạn và không giữ ứng dụng treo vô hạn.

Đo latency của lời gọi có listener và không có listener trong cùng điều kiện tải. Listener chỉ enqueue nên phần thời gian thêm vào phải nhỏ và ổn định. Nếu latency tăng đáng kể, kiểm tra callback có đang serialize payload lớn, chờ lock, ghi log đồng bộ hoặc dùng rejection policy CallerRuns hay không.

## 11. Sơ đồ kiến trúc event consumer bất đồng bộ

~~~mermaid
flowchart TD
    A["Lời gọi được Circuit Breaker bảo vệ"] --> B["Resilience4j phát event"]
    B --> C["Listener ngắn: enqueue"]
    C --> D{"Bounded queue còn chỗ?"}
    D -- "Có" --> E["Worker thread lấy event"]
    E --> F["Metric, log hoặc notification"]
    D -- "Không" --> G["Drop/sample và tăng dropped counter"]
    G --> H["Request tiếp tục, không chờ worker"]
    F --> I["Theo dõi lỗi handler riêng"]
~~~

Kiến trúc này tách việc phát event khỏi xử lý tốn thời gian. Queue bounded bảo vệ bộ nhớ; rejection không chạy handler trên thread phát event; worker xử lý độc lập và có thể được giám sát riêng.

## Kết luận

Có thể mở rộng CircuitBreakerRegistry bằng listener vòng đời để tự động gắn event consumer cho cả instance hiện có và instance được tạo về sau. EventConsumerRegistry phù hợp để lưu lịch sử gần nhất trong buffer có giới hạn, nhưng không phải hàng đợi bất đồng bộ hay kho lưu trữ bền vững. Vì callback event thường chạy trên luồng phát sự kiện, hãy giữ listener ngắn và chuyển I/O hoặc xử lý nặng sang executor có queue bounded. Theo dõi event bị drop, queue depth và latency handler; tránh CallerRuns, queue không giới hạn và tag metric có cardinality cao. Khi telemetry có giới hạn tài nguyên riêng, việc quan sát Circuit Breaker sẽ không trở thành nguyên nhân làm chậm đường xử lý chính.

