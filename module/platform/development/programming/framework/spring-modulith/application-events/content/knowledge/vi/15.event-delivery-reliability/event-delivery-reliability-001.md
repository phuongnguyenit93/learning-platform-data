# At-most-once: giao sự kiện tối đa một lần trong Spring Modulith

Trong một ứng dụng đặt hàng, module `ordering` có thể phát sự kiện để `notification` gửi xác nhận, `analytics` cập nhật thống kê hoặc `audit` ghi nhận dấu vết nghiệp vụ. Khi thiết kế cơ chế giao sự kiện, câu hỏi quan trọng không chỉ là **ai phát và ai nhận**, mà còn là: *Nếu có sự cố thì hệ thống có thể bỏ lỡ event không, có phát lại không, và consumer có thể xử lý trùng không?*

**At-most-once delivery** là một chiến lược trong đó, đối với **một sự kiện đã được định danh và một consumer cụ thể**, hệ thống dự kiến giao sự kiện **không quá một lần** trong phạm vi bảo đảm đã xác định. Điều đó có nghĩa consumer có thể nhận **một lần hoặc không lần nào**. Ưu điểm là tránh cơ chế phát lại gây trùng ở tầng giao nhận; nhược điểm là **có thể mất sự kiện khi lỗi xảy ra**.

Bài này thuộc chương **Đảm bảo tin cậy** của `SPRING_MODULITH_APPLICATION_EVENTS`. Trong phạm vi giao tiếp giữa các module Spring Modulith bằng application events, chúng ta sẽ phân biệt at-most-once với at-least-once, tìm hiểu giới hạn của `ApplicationEventPublisher`, `@EventListener`, `@Async`, `@TransactionalEventListener`, Event Publication Registry và retry, rồi thực hành chọn cơ chế phù hợp với yêu cầu nghiệp vụ và ranh giới module.

> **Thông điệp quan trọng:** At-most-once là một **thỏa thuận về số lần giao nhận**, không phải lời hứa rằng event đã được giao thành công, đã commit, được consumer xử lý xong hoặc side effect chỉ xảy ra đúng một lần.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Định nghĩa chính xác at-most-once theo **event ID**, **consumer** và **ranh giới giao nhận**.
2. Phân biệt “đã publish”, “đã dispatch”, “đã được listener gọi”, “đã xử lý thành công” và “đã hoàn tất tác dụng phụ”.
3. Vẽ các cửa sổ lỗi có thể làm mất sự kiện khi sử dụng Spring events đồng bộ hoặc bất đồng bộ.
4. Hiểu vì sao `@Async` không đồng nghĩa at-most-once bền vững và vì sao `@TransactionalEventListener(AFTER_COMMIT)` không loại bỏ mọi nguy cơ mất event.
5. So sánh at-most-once với at-least-once và các mục tiêu xử lý hiệu quả đúng một lần.
6. Giải thích tác động của acknowledgement/offset khi đưa integration event qua broker.
7. Xác định tình huống at-most-once chấp nhận được và những nghiệp vụ không nên dùng cơ chế này.
8. Thiết kế kiểm thử, log, metric, cảnh báo và kế hoạch nâng cấp sang giao nhận có recovery khi yêu cầu tăng lên.

## 2. Định nghĩa rõ “tối đa một lần”

Hãy xét một event có `eventId = E1` và một listener cụ thể `analytics.OrderViewListener`.

| Số lượt giao event E1 tới listener | At-most-once có cho phép? | Nhận xét |
| --- | --- | --- |
| 0 | Có | Event có thể bị bỏ lỡ trước khi listener nhận |
| 1 | Có | Listener có cơ hội xử lý; thành công hay không là chuyện khác |
| 2 | Không | Cùng event đã được giao lại cho cùng consumer |
| 3 hoặc nhiều hơn | Không | Vi phạm mục tiêu at-most-once tại ranh giới này |

Một cách diễn đạt khái niệm:

\[
\forall(e,c),\quad \text{deliveryAttempts}(e,c) \leq 1
\]

Trong đó `e` là **một event identity** và `c` là **một consumer identity**. Công thức chỉ có ý nghĩa khi hệ thống xác định rõ event và consumer được nhận diện ra sao. Nếu mỗi lần retry tạo `eventId` mới, chỉ đếm theo event ID mới có thể che giấu việc **cùng hành động nghiệp vụ bị phát nhiều lần**.

### 2.1. Phải nêu phạm vi bảo đảm

Một câu như “ứng dụng dùng at-most-once” còn thiếu thông tin. Cần xác định:

- **Nguồn:** một lời gọi `publishEvent(...)` của ứng dụng, một bản ghi outbox hay một message trên broker?
- **Đích:** một listener bean, một consumer group, một tiến trình hay một tác dụng phụ nghiệp vụ?
- **Khoảng thời gian:** trong một lần chạy JVM, qua quá trình restart, hay xuyên suốt thời gian lưu message?
- **Cơ chế retry:** có tự động replay, retry do HTTP caller, resubmission của registry hoặc thao tác replay thủ công không?
- **Định danh:** event ID có ổn định xuyên suốt các lần thử không?

Ví dụ: “Trong một lần publish và không cấu hình retry, listener in-memory được lập lịch tối đa một lần” là phát biểu **hẹp hơn**, có thể kiểm tra được. Phát biểu đó **không chứng minh** toàn bộ luồng từ HTTP request tới email sẽ luôn xử lý một lần hay không bao giờ trùng.

### 2.2. Giao tối đa một lần khác xử lý tối đa một lần

Một listener có thể nhận event đúng **một lần** nhưng thực hiện hai lần gọi API vì bug. Hoặc một yêu cầu HTTP được gửi lại sau timeout khiến publisher tạo **hai event khác nhau** cho cùng nghiệp vụ.

Do đó, cần tách ít nhất ba khái niệm:

| Khái niệm | Điều được đếm | Ví dụ |
| --- | --- | --- |
| **Delivery** | Số lần hệ thống chuyển một event tới consumer | Broker chuyển message E1 cho listener |
| **Processing** | Số lần consumer bắt đầu/thực hiện xử lý event | Handler chạy và ghi trạng thái |
| **Business effect** | Số kết quả nghiệp vụ thực tế | Số email đã gửi hoặc số điểm đã cộng |

At-most-once **delivery** không tự bảo đảm at-most-once **business effect**. Ngược lại, hệ thống có thể giao event **nhiều lần** nhưng nhờ idempotency vẫn chỉ tạo một kết quả nghiệp vụ.

## 3. So sánh at-most-once, at-least-once và exactly-once

| Chiến lược | Số lần giao dự kiến | Điều nổi bật | Đánh đổi |
| --- | --- | --- | --- |
| **At-most-once** | 0 hoặc 1 | Không chủ động giao lại cùng event trong phạm vi bảo đảm | Event có thể mất |
| **At-least-once** | 1 hoặc nhiều hơn, nếu điều kiện lưu bền/khôi phục được đáp ứng | Ưu tiên không bỏ sót event đã được hệ thống chấp nhận bền vững | Consumer có thể nhận trùng |
| **Exactly-once** | Đúng một lần trong một phạm vi được định nghĩa và chứng minh | Mục tiêu mạnh hơn về delivery/processing | Khó bảo đảm xuyên nhiều hệ thống và side effect bên ngoài |
| **Effectively-once** | Có thể giao nhiều lần; tác dụng phụ được khử trùng lặp | Kết quả nghiệp vụ tương đương một lần xử lý | Cần idempotency, transaction/unique constraint hoặc API đích phù hợp |

Không nên xem ba tên gọi là “chế độ” có thể bật chỉ bằng một annotation Spring Modulith. Mỗi cơ chế có **điểm chấp nhận thành công**, **phạm vi lỗi** và **ranh giới nhất quán** riêng.

Ví dụ, khi consumer nhận E1 hai lần nhưng chỉ tạo một bản ghi có unique constraint theo `eventId`, delivery là **at-least-once/duplicate-tolerant**, còn business effect có thể đạt **effectively-once** trong database của consumer. Không được gọi delivery ấy là at-most-once.

## 4. Tại sao at-most-once có thể làm mất sự kiện?

Một chính sách không phát lại có điểm yếu: nếu công việc đã được coi là “đã giao” nhưng consumer chưa xử lý xong, sự cố có thể để lại **không có kết quả** và **không có lần xử lý tiếp theo**.

~~~mermaid
sequenceDiagram
    participant P as Publisher
    participant T as Executor / transport
    participant C as Consumer
    P->>T: Giao event E1
    T-->>P: Đã tiếp nhận / lên lịch
    Note over T,C: Crash trước khi consumer chạy
    X--xC: Không có lần giao lại
    Note over P,C: E1 có thể bị mất ở tầng xử lý
~~~

Trong môi trường bất đồng bộ, “task đã được executor chấp nhận” khác với “listener đã xử lý thành công”. Với broker, “message đã được broker gửi/ack theo cấu hình” khác với “consumer đã commit thay đổi nghiệp vụ”.

Các cửa sổ lỗi thường gặp:

1. **Trước khi event được publish:** publisher dừng hoặc nhánh code lỗi; event chưa tồn tại để giao.
2. **Sau publish nhưng trước khi listener được lập lịch:** cấu hình dispatch/executor có lỗi hoặc task bị từ chối.
3. **Sau khi lên lịch vào bộ nhớ nhưng trước khi worker chạy:** tiến trình crash; in-memory queue không có khả năng phục hồi.
4. **Trong lúc listener xử lý:** listener ném exception hoặc hệ thống ngoài timeout; nếu không retry thì công việc có thể không hoàn tất.
5. **Sau tác dụng phụ nhưng trước khi ghi nhận kết quả:** có thể không biết chắc side effect đã thành công; nếu cố phát lại, cần quan tâm trùng kết quả.

**Không retry** giúp hạn chế số lần thử của hệ thống giao nhận, nhưng nó **không giải quyết** việc xác định có hay không có side effect trong những thời điểm mơ hồ.

## 5. At-most-once trong Spring application events nội bộ

Spring `ApplicationEventPublisher` cho phép publish Java object tới listener trong cùng Spring ApplicationContext:

~~~java
applicationEventPublisher.publishEvent(event);
~~~

Với `@EventListener` thông thường và dispatcher mặc định đồng bộ, mỗi listener đủ điều kiện thường được gọi một lần **cho mỗi lần publish**. Nhưng cần hiểu rõ giới hạn:

- Spring không tự ngăn caller **gọi publish hai lần** cho cùng event.
- Hai bean listener đăng ký cho cùng kiểu event là **hai consumer**; cả hai có thể nhận.
- Nếu publisher được caller retry, event có thể bị tạo và publish lại.
- Exception của listener đồng bộ có thể ảnh hưởng luồng publish hoặc transaction nguồn; caller retry toàn bộ nghiệp vụ có thể tạo tác dụng phụ trùng.
- Event trong cùng JVM không mặc nhiên có bản ghi bền vững để khôi phục sau crash.

Do đó, không nên tuyên bố `@EventListener` mặc định cung cấp at-most-once **end-to-end**. Điều có thể kiểm chứng là cách dispatcher xử lý **một lần phát sự kiện cụ thể** trong cấu hình và phạm vi đang dùng.

### 5.1. Listener đồng bộ và lỗi xử lý

~~~java
package com.example.shop.analytics.internal;

import com.example.shop.ordering.events.OrderDetailsViewed;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
class OrderViewCounterListener {

    private final ViewCounter counter;

    OrderViewCounterListener(ViewCounter counter) {
        this.counter = counter;
    }

    @EventListener
    void on(OrderDetailsViewed event) {
        counter.increment(event.orderId());
    }
}
~~~

Đây là ví dụ cho một **phản ứng thống kê có thể chấp nhận thiếu một vài lượt xem**. `ViewCounter` là abstraction của module `analytics`. Listener đồng bộ có thể làm tăng thời gian phản hồi của publisher và exception chưa xử lý có thể lan về luồng publish. Nếu nhiệm vụ chỉ mang tính quan sát, có thể muốn tách khỏi đường đi chính bằng async; song việc chuyển sang async tạo thêm cửa sổ mất task.

## 6. Ví dụ nghiệp vụ: sự kiện lượt xem đơn hàng

Ta chọn một tình huống **có thể chấp nhận mất dữ liệu**: thống kê xấp xỉ số lượt xem trang chi tiết đơn hàng. Khi người dùng đã được xác thực và phân quyền xem đơn, module `ordering` phát `OrderDetailsViewed`; `analytics` nhận để tăng một bộ đếm. Mất một lượt xem không làm sai trạng thái đơn, tiền hay quyền lợi khách hàng.

### 6.1. Cấu trúc package

~~~text
com.example.shop
├── ShopApplication.java
├── ordering/
│   ├── OrderViewReporter.java            # Public API mặc định
│   ├── events/
│   │   ├── package-info.java             # @NamedInterface("events")
│   │   └── OrderDetailsViewed.java       # Hợp đồng sự kiện
│   └── internal/
│       └── OrderViewEventPublisher.java
└── analytics/
    ├── package-info.java                 # allowedDependencies
    └── internal/
        ├── OrderViewCounterListener.java
        └── ViewCounter.java
~~~

Module `ordering` sở hữu sự thật “chi tiết đơn hàng đã được xem”; module `analytics` sở hữu bộ đếm. Publisher **không import** listener hoặc repository nội bộ của `analytics`.

### 6.2. Hợp đồng event

~~~java
// com/example/shop/ordering/events/OrderDetailsViewed.java
package com.example.shop.ordering.events;

import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

public record OrderDetailsViewed(
        UUID eventId,
        UUID orderId,
        Instant occurredAt
) {
    public OrderDetailsViewed {
        Objects.requireNonNull(eventId, "eventId");
        Objects.requireNonNull(orderId, "orderId");
        Objects.requireNonNull(occurredAt, "occurredAt");
    }
}
~~~

`eventId` định danh **một sự kiện lượt xem**, còn `orderId` định danh **đơn hàng**. Một đơn có thể có nhiều lượt xem hợp lệ, nên không thể dùng `orderId` làm khóa để loại bỏ mọi lượt xem trùng.

Nếu package sự kiện nằm trong subpackage, có thể công bố named interface:

~~~java
// com/example/shop/ordering/events/package-info.java
@org.springframework.modulith.NamedInterface("events")
package com.example.shop.ordering.events;
~~~

### 6.3. Public API và publisher

~~~java
// com/example/shop/ordering/OrderViewReporter.java
package com.example.shop.ordering;

import java.util.UUID;

public interface OrderViewReporter {
    void recordAuthorizedView(UUID orderId);
}
~~~

~~~java
// com/example/shop/ordering/internal/OrderViewEventPublisher.java
package com.example.shop.ordering.internal;

import com.example.shop.ordering.OrderViewReporter;
import com.example.shop.ordering.events.OrderDetailsViewed;
import java.time.Clock;
import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

@Service
class OrderViewEventPublisher implements OrderViewReporter {

    private final ApplicationEventPublisher events;
    private final Clock clock;

    OrderViewEventPublisher(
            ApplicationEventPublisher events,
            Clock clock
    ) {
        this.events = events;
        this.clock = clock;
    }

    @Override
    public void recordAuthorizedView(UUID orderId) {
        events.publishEvent(new OrderDetailsViewed(
                UUID.randomUUID(),
                orderId,
                clock.instant()
        ));
    }
}
~~~

Ví dụ giả định `recordAuthorizedView` chỉ được gọi **sau khi** hệ thống kiểm tra quyền truy cập đơn hàng và thực sự ghi nhận lượt xem. Tên method không thay thế authorization; ở production phải có service/caller kiểm tra quyền theo phiên đăng nhập và `orderId`. Bean `Clock` cần được cấu hình trong ứng dụng.

### 6.4. Giới hạn phụ thuộc của consumer

~~~java
// com/example/shop/analytics/package-info.java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "ordering::events"
)
package com.example.shop.analytics;
~~~

Module `analytics` được phép import `OrderDetailsViewed` nhưng không cần import `ordering.internal`. Đây là **ranh giới kiến trúc**; at-most-once là **chính sách giao nhận**. Hai khái niệm bổ sung cho nhau chứ không thay thế nhau.

## 7. Dùng `@Async` với listener best-effort

Khi một tác vụ thống kê không nên giữ luồng xử lý request, có thể chạy listener bằng executor:

~~~java
package com.example.shop.analytics.internal;

import com.example.shop.ordering.events.OrderDetailsViewed;
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Component;

@Component
public class OrderViewCounterListener {

    private final ViewCounter counter;

    public OrderViewCounterListener(ViewCounter counter) {
        this.counter = counter;
    }

    @Async("telemetryExecutor")
    @EventListener
    public void on(OrderDetailsViewed event) {
        counter.increment(event.orderId());
    }
}
~~~

**Lưu ý:** phương án này thay thế listener đồng bộ ở mục 5. Không đăng ký cả hai bean cùng tăng một chỉ số trong dự án thật, trừ khi cố ý muốn đếm hai kiểu dữ liệu khác nhau.

### 7.1. Cấu hình executor

~~~java
package com.example.shop.config;

import java.util.concurrent.Executor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
class TelemetryAsyncConfiguration {

    @Bean(name = "telemetryExecutor")
    Executor telemetryExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("telemetry-");
        executor.initialize();
        return executor;
    }
}
~~~

Các tham số chỉ mang tính minh họa; lựa chọn thật phải dựa trên thời gian xử lý, tài nguyên, tải và giới hạn dịch vụ đích. Nếu executor chấp nhận task rồi ứng dụng crash trước khi task chạy, dữ liệu có thể mất. Nếu task bị từ chối vì queue đầy, lỗi lập lịch có thể xuất hiện ở luồng publish tùy cơ chế cấu hình.

### 7.2. At-most-once ở đây là chiến lược nào?

Ở ví dụ **không có recovery/retry**:

1. Publisher tạo một event mới cho mỗi lượt xem hợp lệ.
2. Spring chuyển event cho listener đã đăng ký trong lần publish đó.
3. Listener async được lên lịch **một lần** theo dispatcher thông thường.
4. Nếu task bị mất hoặc thất bại, ứng dụng **không chủ động giao lại cùng event**.

Đó là một mô hình **best-effort/no-retry tương tự at-most-once trong phạm vi một lần dispatch**, không phải chứng minh hệ thống toàn cục có một giao thức at-most-once bất chấp publisher retry, duplicate registration hoặc thay đổi runtime.

Nếu lượt xem bị ghi trùng từ HTTP client do người dùng tải lại trang, đó có thể là **hai sự kiện nghiệp vụ hợp lệ**. Nếu HTTP client tự retry một yêu cầu do timeout nhưng mục tiêu chỉ ghi một lần cho cùng thao tác, cần thêm **request ID và deduplication ở tầng nghiệp vụ**; event delivery policy không giải quyết tự động vấn đề này.

## 8. `@Async` không phải durable queue

Thread pool và queue trong bộ nhớ giúp chuyển công việc sang worker, nhưng chúng không phải bản ghi sự kiện bền vững.

| Thời điểm xảy ra sự cố | Điều có thể xảy ra khi không có recovery |
| --- | --- |
| Trước khi task được submit | Event chưa được listener nhận |
| Queue bị đầy và task bị từ chối | Việc xử lý không được lập lịch; publisher có thể nhận lỗi submit |
| Task nằm trong queue khi JVM dừng cưỡng bức | Task mất |
| Worker đang xử lý rồi process crash | Có thể chưa hoàn thành side effect |
| Method async `void` ném exception | Publisher không nhận exception theo cách đồng bộ; task thất bại nếu không có cơ chế riêng |
| Ứng dụng được restart | Queue in-memory cũ không tự được khôi phục |

Ngay cả khi cấu hình executor chờ task khi shutdown bình thường, sự cố mất điện, process kill hoặc node crash vẫn có thể làm mất việc. Nếu KPI hoặc nghiệp vụ không chấp nhận mất event, **đừng dùng `@Async` thuần túy làm cơ chế bảo đảm giao nhận**.

### Exception trong listener đồng bộ và async

Với listener đồng bộ, exception có thể lan về `publishEvent(...)`. Với listener async trả về `void`, exception xảy ra sau submit thường được xử lý qua cơ chế async exception handling/logging. Cả hai đều không mặc định làm lại event theo một chính sách durable retry.

Nếu chọn at-most-once cho telemetry, cần định nghĩa chính sách lỗi tường minh: **được phép bỏ qua thất bại**, ghi nhận metric/log an toàn và không kéo theo retry làm tăng tải. Nếu không muốn làm ảnh hưởng request, còn phải xử lý tình huống executor từ chối task theo cách đã thống nhất; không nên âm thầm nuốt tất cả exception của publisher.

## 9. At-most-once và ranh giới transaction

Spring giao tiếp bằng events có thể gắn với transaction của nghiệp vụ phát. Hai câu hỏi khác nhau:

1. **Khi nào listener được phép bắt đầu?** Trước commit, sau commit hay khi rollback?
2. **Nếu listener không hoàn tất, có giao lại không?** Đây mới là phần thuộc delivery policy.

### 9.1. Publish trong transaction

~~~java
@Transactional
public UUID placeOrder(PlaceOrderRequest request) {
    UUID orderId = repository.create(request);
    events.publishEvent(new OrderPlaced(
            UUID.randomUUID(),
            orderId,
            clock.instant()
    ));
    return orderId;
}
~~~

`OrderPlaced`, `repository` và `clock` ở đây là thành phần của ví dụ nghiệp vụ đặt hàng. `publishEvent(...)` được gọi **trước khi transaction nguồn được xác nhận commit**. Listener `@EventListener` mặc định có thể chạy ngay lúc publish; nếu gửi email và transaction sau đó rollback, email không tự được hoàn tác.

### 9.2. Listener sau commit giải quyết vấn đề gì?

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
void on(OrderPlaced event) {
    // Phản ứng với transaction đã commit thành công.
}
~~~

`AFTER_COMMIT` giúp tránh phản ứng với dữ liệu bị rollback. Tuy nhiên, nếu ứng dụng đã commit database nhưng bị dừng trước khi callback hoàn tất, **phản ứng vẫn có thể bị bỏ lỡ nếu không có persistence/recovery**.

~~~mermaid
sequenceDiagram
    participant O as ordering
    participant DB as Database
    participant E as Spring event infrastructure
    participant C as notification
    O->>DB: Ghi Order trong transaction
    O->>E: publish OrderPlaced
    O->>DB: Commit
    DB-->>O: Commit thành công
    Note over E,C: JVM dừng trước khi listener xử lý xong
    Note over E,C: Không có recovery -> có thể mất phản ứng
~~~

**Không có transaction:** `@TransactionalEventListener` mặc định không kích hoạt khi publisher không có transaction đang hoạt động, trừ khi bật `fallbackExecution`. Đây là hành vi phụ thuộc phase, không phải một cam kết at-most-once cho toàn bộ hệ thống.

### 9.3. `@ApplicationModuleListener` và registry

`@ApplicationModuleListener` của Spring Modulith kết hợp mô hình listener **sau commit**, **bất đồng bộ** và **transaction mới**. Nó là lựa chọn thường phù hợp với phản ứng giữa application modules, nhưng bản thân annotation không tuyên bố mọi publication được xử lý exactly-once.

Nếu ứng dụng cấu hình **Event Publication Registry** với persistence và cơ chế recovery/resubmission để chạy lại publication chưa hoàn tất, một consumer có thể nhận **lại cùng event** sau lỗi. Hệ thống khi đó đang ưu tiên **không bỏ sót công việc**, không còn giữ chiến lược “không bao giờ giao lại” tại ranh giới ấy.

Do vậy, một bài toán yêu cầu “tối đa một lần, mất được” và một bài toán yêu cầu “không được mất, retry được” **không nên bị gộp thành cùng một chính sách delivery**.

## 10. Tại sao Event Publication Registry không phải công cụ bảo đảm at-most-once?

Event Publication Registry của Spring Modulith phục vụ việc theo dõi publication của các listener/hạ tầng được hỗ trợ khi cấu hình persistence thích hợp. Nó giúp nhận diện publication đã hoàn tất hoặc còn dang dở và có thể hỗ trợ xử lý lại publication chưa hoàn tất.

Khi một publication đã được ghi nhận bền vững nhưng listener bị lỗi:

- **Nếu không có recovery:** công việc có thể chưa hoàn tất; có thể có trạng thái chưa hoàn tất để vận hành điều tra.
- **Nếu cho phép replay/resubmission:** listener có thể được gọi thêm lần nữa với cùng event.
- **Nếu side effect đã xảy ra nhưng completion chưa được ghi:** lần replay có thể tạo tác dụng phụ trùng nếu consumer không idempotent.

Registry không tự loại bỏ yêu cầu idempotency và cũng không bảo đảm việc phục hồi sẽ diễn ra đúng theo kỳ vọng nếu storage, transaction manager hoặc job recovery chưa được cấu hình và kiểm tra.

### 10.1. Hai lựa chọn có chủ đích

| Mục tiêu | Cách tiếp cận |
| --- | --- |
| **Telemetry không quan trọng, cho phép mất** | In-memory `@Async @EventListener`, không chủ động replay; theo dõi lỗi/rejection ở mức phù hợp |
| **Thông báo hoặc cập nhật dữ liệu cần recovery** | Listener sau commit với persistence/registry hoặc outbox phù hợp, retry có kiểm soát, consumer idempotent |

Việc lựa chọn phụ thuộc yêu cầu nghiệp vụ hơn là mong muốn dùng ít hoặc nhiều annotation. Không nên tắt recovery cho event tài chính, trạng thái đơn hàng quan trọng hoặc nghiệp vụ pháp lý chỉ để giữ nhãn “at-most-once”.

### 10.2. At-most-once không đồng nghĩa idempotency

**Idempotency** là khả năng xử lý một yêu cầu nhiều lần mà không tạo thêm kết quả ngoài ý muốn. Nó hữu ích nhất khi hệ thống có thể retry và giao trùng.

Trong một hệ thống at-most-once **chỉ xét tầng delivery**, consumer vẫn có thể cần idempotency vì nguồn phát lặp lại cùng nghiệp vụ, API client retry hoặc một tác dụng phụ được gọi nhiều lần bởi lỗi code. At-most-once delivery không thay thế bất biến nghiệp vụ ở database.

## 11. So sánh với message broker: ack/offset quyết định trade-off

Khi event nội bộ được externalize thành integration message, cơ chế giao nhận phụ thuộc vào broker và consumer protocol. At-most-once thường được mô hình hóa bằng quyết định **ghi nhận đã nhận/xử lý trước khi thực sự hoàn thành công việc**.

### 11.1. Minh họa với message queue

~~~mermaid
sequenceDiagram
    participant B as Broker
    participant C as Consumer
    participant D as Consumer DB
    B->>C: Gửi message E1
    C-->>B: Ack sớm / broker xem như đã giao
    Note over C,D: Process crash trước khi ghi DB
    Note over B,C: Broker không phát lại E1 theo chính sách đã chọn
    Note over D: Side effect bị thiếu
~~~

Với một số message queue như RabbitMQ, chế độ automatic acknowledgement có thể khiến broker xem delivery đã được giao mà không đợi callback nghiệp vụ của ứng dụng xác nhận thành công. **Đây là một cách tạo rủi ro mất message**, không phải lời khuyên sử dụng cho tác vụ quan trọng.

Không được suy rằng mọi chế độ ack trong mọi broker đều có semantics giống nhau. Cần đọc tài liệu chính xác của phiên bản broker/client đang triển khai và kiểm tra khi xảy ra disconnect, failover hoặc consumer crash.

### 11.2. Minh họa với Kafka offset

Để cố ý ưu tiên không xử lý trùng trong một consumer workflow, người ta có thể **commit offset đã đọc trước khi thực hiện tác vụ nghiệp vụ**:

~~~text
1. Poll record E1 ở offset N
2. Commit thành công offset N+1 (vị trí đọc kế tiếp)
3. Xử lý E1
4. Nếu crash tại bước 3, lần khởi động sau có thể không đọc lại E1
~~~

Đây là **pseudocode về thứ tự**, không phải cấu hình Kafka client hoàn chỉnh. Trong trường hợp commit offset thất bại, rebalance xảy ra hoặc có nhiều consumer, cần xét thêm các điều kiện hệ thống. Đặc biệt, **bật auto-commit không mặc nhiên đồng nghĩa at-most-once**: offset có thể được commit ở thời điểm khác với quá trình xử lý, và consumer vẫn có khả năng nhận lại record sau sự cố.

Đối với xử lý cần tránh mất, một chiến lược thường là xử lý và ghi dữ liệu trước rồi commit offset/ack; nhưng nếu crash giữa xử lý thành công và ack, message có thể được giao lại. Đó là lý do nhiều hệ thống chọn **at-least-once + idempotency** thay cho at-most-once.

### 11.3. Một broker có durability vẫn có thể cho at-most-once ở consumer

Ngay cả khi broker lưu message bền vững, việc consumer ack quá sớm vẫn có thể khiến công việc không được xử lý. **Durable storage của broker** và **chính sách xác nhận ở consumer** là hai yếu tố riêng biệt.

Tương tự, bảo đảm producer ghi đúng một message vào topic chưa đủ chứng minh side effect ở database consumer xảy ra đúng một lần.

## 12. Bài toán phù hợp và không phù hợp với at-most-once

### Khi có thể chấp nhận

- **Telemetry xấp xỉ:** lượt xem trang, sự kiện sử dụng tính năng để ước lượng xu hướng, nơi một phần mẫu bị mất không gây sai quyết định nghiệp vụ quan trọng.
- **Tín hiệu best-effort có thể tự hồi phục:** ví dụ cập nhật gợi ý UI không quan trọng và sẽ được làm mới định kỳ bằng nguồn trạng thái chuẩn.
- **Thông báo phụ không bắt buộc:** một event không ảnh hưởng quyền lợi hoặc quyết định giao dịch và có cơ chế khác để người dùng truy cập trạng thái thật.

Những trường hợp này phải có **chấp nhận mất dữ liệu rõ ràng**. Ngay cả với telemetry, mất event có thể tạo thiên lệch thống kê; không nên chọn at-most-once nếu dữ liệu ấy được dùng để tính tiền, báo cáo tuân thủ hoặc đánh giá pháp lý.

### Khi thường không phù hợp

| Nghiệp vụ | Tác hại khi mất event | Hướng cân nhắc |
| --- | --- | --- |
| Ghi nhận thu tiền thành công | Không cập nhật sổ sách, trạng thái thanh toán sai | Publication bền vững, recovery, idempotency và đối soát |
| Gửi yêu cầu giao hàng bắt buộc | Đơn đã thanh toán nhưng không được tạo vận đơn | Outbox/registry phù hợp, retry và trạng thái workflow |
| Cộng/trừ điểm hoặc tiền | Quyền lợi hoặc số dư sai | Transaction rõ, log nghiệp vụ bền vững, dedupe |
| Bút toán audit bắt buộc | Mất bằng chứng tuân thủ | Ghi audit bền vững theo policy, kiểm tra reconciliation |
| Đồng bộ dữ liệu giữa hệ thống là nguồn sự thật | Chênh lệch trạng thái kéo dài | At-least-once + idempotency, reconcile |

**Cách chọn:** hỏi “Nếu mất một event này và không ai tự động giao lại, điều gì sai?” Nếu câu trả lời liên quan tài chính, dữ liệu cốt lõi, nghĩa vụ pháp lý hoặc trải nghiệm bắt buộc, at-most-once thuần túy thường không đáp ứng yêu cầu.

## 13. Không retry có thật sự giảm phức tạp?

At-most-once có thể giảm một phần độ phức tạp ở tầng vận chuyển vì không cần cơ chế phát lại event. Tuy nhiên, nó **chuyển chi phí sang khả năng chấp nhận thiếu kết quả**.

| Khía cạnh | Khi chọn no-retry/at-most-once best-effort |
| --- | --- |
| Storage publication | Có thể không cần đối với telemetry mất được |
| Consumer deduplication | Có thể đơn giản hơn ở ranh giới delivery, nhưng vẫn cần nếu nguồn phát có thể lặp |
| Chi phí xử lý trùng | Thường thấp hơn nếu thật sự chỉ giao một lần |
| Chi phí mất dữ liệu | Có thể cao nếu chọn sai nghiệp vụ |
| Khả năng điều tra | Khó biết event bị mất nếu không ghi nhận tại các mốc |
| Khả năng tự phục hồi | Không có nếu không thiết kế một kênh khác |

Không nên gọi at-most-once là “đơn giản và nhanh hơn” trong mọi tình huống. Nếu nhóm phải điều tra thủ công các bản ghi nghiệp vụ bị thiếu, **tổng chi phí vận hành có thể lớn hơn** việc thiết kế recovery ngay từ đầu.

## 14. Thiết kế ranh giới module đúng dù chọn at-most-once

Chính sách giao nhận không quyết định quyền sở hữu code. Trong ví dụ lượt xem, `ordering` công bố hợp đồng ở `ordering.events`, còn `analytics` lắng nghe trong `analytics.internal`.

Spring Modulith có thể kiểm tra hướng phụ thuộc:

~~~java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleBoundaryTest {

    @Test
    void keepsModulesWithinPublishedApis() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Một lỗi cần tránh:

~~~java
// Không nên đưa vào analytics:
import com.example.shop.ordering.internal.OrderRepository;
~~~

Ngay cả khi repository là class Java `public`, việc consumer import kiểu ở subpackage nội bộ của module phát có thể vi phạm ranh giới Spring Modulith. Hãy sử dụng event contract, API công khai hoặc một query API được công bố có chủ đích.

`verify()` **không chứng minh** rằng at-most-once đã được thực hiện ở runtime. Nó kiểm tra kiến trúc phụ thuộc, còn số lần giao và hành vi lỗi cần test riêng.

## 15. Kiểm thử publisher: đã phát event nào?

Spring Modulith hỗ trợ `@ApplicationModuleTest` và `PublishedEvents` để kiểm chứng sự kiện được publish từ module đang test.

~~~java
package com.example.shop.ordering;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.shop.ordering.events.OrderDetailsViewed;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.PublishedEvents;

@ApplicationModuleTest
class OrderViewPublishingTest {

    @Autowired OrderViewReporter reporter;

    @Test
    void publishesOneViewEventForOneInvocation(PublishedEvents published) {
        UUID orderId = UUID.randomUUID();

        reporter.recordAuthorizedView(orderId);

        assertThat(published.ofType(OrderDetailsViewed.class))
                .extracting(OrderDetailsViewed::orderId)
                .containsExactly(orderId);
    }
}
~~~

Đoạn test giả định `OrderViewReporter` hoạt động trong test context, bean `Clock` đã được cấu hình, và authorization được kiểm tra trước khi gọi facade của ví dụ. Nó xác minh **một lời gọi publisher tạo một event đúng loại**; không đo số lần listener nhận hoặc chứng minh no-retry sau crash.

### Cần kiểm thử cả việc caller publish lại

Nếu service bị gọi hai lần, test trên không đảm bảo chỉ một event được sinh ra cho cùng hành động. Có thể tạo hai event khác `eventId`. Khi HTTP client có cơ chế retry, cần thiết kế request ID hoặc idempotency key ở tầng nghiệp vụ nếu phải ngăn lặp yêu cầu.

Điều này cho thấy **giới hạn bảo đảm**: test một lần publish không tương đương kiểm chứng at-most-once trên toàn bộ luồng client → publisher → consumer.

## 16. Kiểm thử listener và tình huống mất sự kiện

Để đánh giá chính sách at-most-once, cần test cả *điều không xảy ra*: không có lần phát lại sau khi consumer thất bại, nếu chính sách ứng dụng thật sự là no-retry.

### 16.1. Unit test xử lý một event

~~~java
package com.example.shop.analytics.internal;

import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;

import com.example.shop.ordering.events.OrderDetailsViewed;
import java.time.Instant;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class OrderViewCounterListenerTest {

    @Test
    void delegatesOneInvocationToCounter() {
        ViewCounter counter = mock(ViewCounter.class);
        OrderViewCounterListener listener =
                new OrderViewCounterListener(counter);
        OrderDetailsViewed event = new OrderDetailsViewed(
                UUID.randomUUID(),
                UUID.randomUUID(),
                Instant.parse("2026-11-25T08:00:00Z")
        );

        listener.on(event);

        verify(counter).increment(event.orderId());
    }
}
~~~

Test gọi trực tiếp method listener, nên chứng minh **logic delegate khi được gọi một lần**. Nó **không kiểm tra `@Async`, Spring event dispatch, transaction hay khả năng retry của hệ thống**.

### 16.2. Integration test cần điều khiển điều kiện

Các tình huống nên được thiết kế theo cấu hình thực:

| Tình huống | Điều cần đo | Ý nghĩa |
| --- | --- | --- |
| Publish E1, executor hoạt động bình thường | Handler nhận E1 và tạo một kết quả thống kê | Happy path |
| Executor queue đầy, task bị từ chối | Có biết task không được chạy? Caller phản ứng ra sao? | Kiểm tra handling của rejection |
| Handler ném exception | Có lần gọi lại tự động hay không? Lỗi được ghi ở đâu? | Xác minh no-retry thực tế |
| Process dừng khi task còn trong queue | Sau restart, E1 có được khôi phục không? | Kiểm chứng rủi ro mất task |
| Publisher gọi hai lần với cùng ý nghĩa nghiệp vụ | Consumer nhận hai event hay dedupe theo request? | Phân biệt source duplicate với delivery duplicate |
| Nhiều listener cùng nhận một event | Mỗi consumer được xác định độc lập | Không nhầm fan-out với duplicate delivery |

**Không dùng thời gian ngủ cố định làm bằng chứng** async hoặc retry. Hãy dùng barrier/latch có timeout, probe trong Spring test hoặc điều kiện side effect có thể quan sát. Với test crash cần môi trường tích hợp có thể dừng tiến trình thật; unit test thông thường không chứng minh durability.

### 16.3. Cố tình nhận lại cùng event

Nếu một test gọi `publishEvent(event)` **hai lần với cùng object và cùng `eventId`**, hai lời gọi là **hai lần publish**. Khi listener nhận hai lần, điều đó không chứng minh Spring đã tự retry; source chủ động phát hai lần.

Ví dụ pseudocode:

~~~java
OrderDetailsViewed event = new OrderDetailsViewed(
        eventId, orderId, clock.instant()
);

publisher.publishEvent(event);
publisher.publishEvent(event); // Lần publish thứ hai do caller.
~~~

Nếu ứng dụng bắt buộc một sự kiện không được tạo tác dụng phụ hai lần ngay cả khi publisher lặp, cần deduplication hoặc invariant riêng. No-retry ở tầng delivery **không xử lý** tình huống này.

## 17. Quan sát at-most-once: đo phần có thể bị mất

Với chiến lược no-retry, một event không đến consumer có thể **không để lại publication pending** trong registry để điều tra. Vì vậy cần thống nhất mức độ quan sát tương ứng với giá trị dữ liệu.

| Điểm đo | Metric/log gợi ý | Đọc kết quả thế nào? |
| --- | --- | --- |
| Publisher | Số event được tạo/phát theo loại | Cho biết hoạt động ở phía nguồn, không chứng minh đã giao |
| Dispatcher/executor | Task được submit, task bị từ chối, queue depth | Phát hiện quá tải trước consumer |
| Listener | Số event bắt đầu xử lý, thành công, thất bại | Thấy được phần việc thực sự nhận/hoàn tất |
| Business effect | Số lượt xem được ghi nhận | Đánh giá tính đầy đủ của dữ liệu cuối |
| Tỷ lệ thiếu hụt ước lượng | So sánh các tổng đếm tại các mốc | Gợi ý sự cố, nhưng không phải bằng chứng delivery chính xác |

Nếu mỗi event đi qua nhiều consumer, **không** cộng chung số lượt xử lý của các listener rồi so với số lượt publish; cần so sánh theo **event type và consumer identity**. Một event có thể tạo một task cho `analytics` và một task cho `recommendation`.

### 17.1. Giới hạn của metric

Nếu toàn bộ tiến trình crash trước khi flush log/metric, ngay cả chỉ số “đã publish” cũng có thể mất. Vì vậy số liệu telemetry chỉ giúp **ước lượng và cảnh báo**, không biến at-most-once thành hệ thống delivery được đối soát tuyệt đối.

Với dữ liệu quan trọng cần reconciliation chính xác, nên có nguồn trạng thái bền vững để đối chiếu (ví dụ bảng nghiệp vụ/outbox) thay vì chỉ dựa vào counter trong bộ nhớ.

### 17.2. Tránh rò rỉ thông tin

Log nên ưu tiên loại event, tên consumer, kết quả và correlation ID an toàn. Không ghi nguyên payload chứa thông tin cá nhân; `orderId` vẫn có thể là dữ liệu nhạy cảm khi kết hợp với dữ liệu khác nên phải tuân thủ chính sách log/truy cập.

## 18. Ra quyết định: chọn at-most-once có chủ đích

Trước khi chốt thiết kế, hãy trả lời:

1. **Mất event có chấp nhận được không?** Nêu tác động cụ thể, không chỉ nói “ít quan trọng”.
2. **Nếu mất, ai phát hiện?** Có metric, đối soát hoặc kênh thông tin khác không?
3. **Có thể tái tạo trạng thái từ nguồn chuẩn không?** Ví dụ dashboard có thể tính lại từ database giao dịch đã commit?
4. **Publisher hoặc client có tự retry không?** Nếu có, có thể tạo duplicate ở tầng nguồn.
5. **Listener có side effect không thể hoàn tác không?** Nếu có, cần idempotency dù delivery được thiết kế no-retry.
6. **Điều kiện transaction của event là gì?** Cần sau commit hay có thể xử lý ngay?
7. **Chi phí mất so với chi phí trùng?** Nghiệp vụ nào nghiêm trọng hơn?
8. **Khi yêu cầu thay đổi, có đường nâng cấp sang durable delivery không?** Có event ID, contract ổn định và consumer đủ độc lập chưa?

### Ma trận quyết định ngắn

~~~mermaid
flowchart TD
    A["Có một event nghiệp vụ"] --> B{"Mất event có chấp nhận được?"}
    B -->|Không| C["Ưu tiên durable publication và recovery"]
    C --> D["At-least-once + idempotency / workflow phù hợp"]
    B -->|Có| E{"Có thể xử lý best-effort không?"}
    E -->|Có| F["Cân nhắc no-retry / at-most-once có giới hạn"]
    E -->|Không| C
    F --> G["Test mất event, rejection, metric và source duplicate"]
~~~

Sơ đồ là cách lựa chọn ở cấp thiết kế, không khẳng định Spring Modulith có một công tắc `deliveryGuarantee = AT_MOST_ONCE`.

## 19. Bài thực hành: đo lường một listener best-effort

**Bối cảnh:** `ordering` phát `OrderDetailsViewed` sau khi người dùng có quyền xem trang chi tiết đơn. `analytics` chỉ cần ước lượng lượt xem; bỏ sót một số lượt xem trong sự cố được chấp thuận bằng yêu cầu nghiệp vụ.

### Phần A — Xây dựng đường đi sự kiện

1. Định nghĩa record `OrderDetailsViewed(eventId, orderId, occurredAt)`.
2. Công bố package `ordering.events` bằng `@NamedInterface("events")`.
3. Viết `OrderViewReporter` trong API module `ordering`; publisher tạo `eventId` mới cho mỗi lượt xem hợp lệ.
4. Viết listener `analytics.internal` với `@Async("telemetryExecutor") @EventListener`.
5. Không cấu hình replay cho luồng telemetry này; ghi rõ chính sách **mất được, không tự retry**.

### Phần B — Kiểm thử khi gặp lỗi

1. Kiểm tra một lần gọi publisher tạo đúng một event bằng `PublishedEvents`.
2. Kiểm tra listener xử lý event bình thường, tăng bộ đếm một lần.
3. Làm cho counter ném exception; quan sát log/exception handler và xác nhận ứng dụng **không chủ động phát lại** khi không cấu hình retry.
4. Làm executor bị quá tải và từ chối task; quan sát caller và chỉ số rejection.
5. Gửi hai lệnh publish với cùng object event; giải thích vì sao đây là **hai lần phát từ nguồn**, không phải retry tự động của Spring.
6. Chạy test kiến trúc `ApplicationModules.verify()` để bảo đảm consumer chỉ biết public event contract.

### Phần C — So sánh với luồng quan trọng

Giả sử `OrderPaid` phải kích hoạt phát hành hóa đơn và cập nhật sổ sách, không được mất:

1. Giải thích vì sao dùng cùng chính sách no-retry của lượt xem là sai.
2. Đề xuất publication persistence/registry hoặc outbox phù hợp với transaction thanh toán.
3. Thiết kế consumer idempotent với `eventId` và transaction ghi dữ liệu.
4. Lập các kịch bản crash *trước xử lý*, *sau side effect nhưng trước completion* và *khi recovery*.
5. Giải thích vì sao “có replay” làm việc giao nhận có thể lặp nhưng business effect vẫn có thể được giới hạn nhờ idempotency.

### Bảng nghiệm thu

| Tiêu chí | Bằng chứng mong đợi |
| --- | --- |
| Hợp đồng được công bố đúng ranh giới | `ApplicationModules.verify()` PASS |
| Một lần gọi publisher sinh một event | `PublishedEvents` xác nhận payload/định danh |
| Listener chạy trên executor phù hợp | Spring integration test/metric thread pool |
| Failure không được tự retry trong luồng telemetry | Test exception/rejection theo cấu hình |
| Có thể phát hiện phần lớn quá tải | Counter queue depth, rejection và lỗi listener |
| Nhận biết duplicate từ nguồn | Test gọi publisher hai lần, kiểm tra event ID |
| Giải thích được giới hạn at-most-once | Chỉ ra ít nhất hai cửa sổ mất event và phạm vi bảo đảm |
| Luồng tài chính có phương án recovery | Đề xuất storage, retry/idempotency và đối soát |

## 20. Những ngộ nhận thường gặp

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| “At-most-once nghĩa là event chắc chắn được xử lý một lần.” | Có thể được giao **0 lần** và không có kết quả |
| “Có `publishEvent` là đạt at-most-once end-to-end.” | Đây là thao tác publish; caller có thể lặp, listener có thể thất bại |
| “`@Async` bảo đảm sẽ không mất event.” | Queue in-memory có thể bị mất khi crash hoặc từ chối task |
| “`AFTER_COMMIT` giúp không bao giờ mất event.” | Nó gắn callback với commit, không tự cung cấp durability/recovery |
| “Có registry là mặc nhiên at-most-once.” | Registry/recovery có thể giao lại publication chưa hoàn tất |
| “Nếu nhận event một lần thì side effect chỉ xảy ra một lần.” | Logic consumer có thể lặp tác vụ; nguồn nghiệp vụ có thể phát hai event |
| “Bật Kafka auto-commit là at-most-once.” | Cần xem thời điểm commit offset so với xử lý; auto-commit không tự tạo guarantee đó |
| “Có durable broker là consumer chắc chắn xử lý event.” | Ack/offset quá sớm vẫn có thể làm mất cơ hội xử lý |
| “Không retry thì không cần quan sát lỗi.” | Ngược lại, việc bỏ lỡ có thể âm thầm; cần metric theo giá trị nghiệp vụ |
| “Idempotency vô nghĩa với at-most-once.” | Nó vẫn bảo vệ trước duplicate từ caller, publisher hoặc code nghiệp vụ |
| “At-most-once phù hợp cho mọi thứ không cần realtime.” | Chấp nhận **trễ** khác chấp nhận **mất**; hai yêu cầu không đồng nghĩa |

## 21. Câu hỏi tự kiểm tra

**Câu 1. Vì sao at-most-once cho phép consumer không nhận event?**

Vì mục tiêu là *không giao quá một lần*, không phải *phải giao ít nhất một lần*. Khi sự cố xảy ra mà không có replay/recovery, event có thể bị bỏ lỡ.

**Câu 2. Một publisher gọi `publishEvent(E1)` hai lần; Spring gọi listener hai lần. Có phải Spring tự retry sai không?**

Không. Đây là hai lời gọi từ publisher. Để nói về duplicate delivery phải định nghĩa ranh giới và phân biệt hành vi nguồn phát với cơ chế transport/replay.

**Câu 3. `@Async @EventListener` có phải là một durable at-most-once queue không?**

Không. Nó lập lịch công việc trên executor; task có thể bị mất khi process crash hoặc bị từ chối khi quá tải, và không tự ghi publication bền vững.

**Câu 4. `@TransactionalEventListener(AFTER_COMMIT)` có giải quyết trường hợp gửi email cho đơn bị rollback không?**

Có thể giúp tránh gửi email khi transaction nguồn rollback, nếu event được publish trong transaction hợp lệ. Nhưng nó không bảo đảm xử lý thành công khi listener hoặc ứng dụng thất bại sau commit.

**Câu 5. Vì sao nên ưu tiên at-least-once + idempotency cho event tài chính quan trọng?**

Vì mất event có thể làm lệch dữ liệu giao dịch; có lưu bền và khả năng replay giúp phục hồi, còn idempotency giới hạn kết quả trùng khi consumer nhận lại.

**Câu 6. Broker đã lưu message trên đĩa thì consumer có thể mất cơ hội xử lý không?**

Có. Nếu message được ack hoặc offset được commit **trước khi công việc hoàn tất**, consumer crash có thể khiến broker không phát lại dù dữ liệu từng được lưu bền.

**Câu 7. Không có cơ chế retry, listener thất bại; làm sao chứng minh hệ thống vẫn đáp ứng yêu cầu?**

Cần yêu cầu nghiệp vụ chấp nhận mất event, test failure/rejection phù hợp, quan sát mức thiếu hụt và chứng minh tác động của dữ liệu thiếu nằm trong ngưỡng chấp nhận. Không nên chỉ dựa vào việc không xuất hiện exception ở publisher.

## 22. Kết luận

**At-most-once là chiến lược giao một event tới một consumer tối đa một lần trong một phạm vi đã định nghĩa, chấp nhận khả năng giao không lần nào.** Trong Spring Modulith, application events giúp tách module phát khỏi module nhận, nhưng `@EventListener`, `@Async` hay `@TransactionalEventListener` không tự tạo bảo đảm delivery end-to-end. Cần tách rời việc publish, dispatch, xử lý và hoàn tất business effect để không đánh giá sai hệ thống.

Với tác vụ best-effort như telemetry xấp xỉ, **không retry** có thể là lựa chọn hợp lý nếu mất event được chấp nhận và có cách phát hiện quá tải/lỗi. Với thanh toán, vận chuyển, hóa đơn hoặc audit quan trọng, nên ưu tiên một thiết kế có **durable publication, Event Publication Registry/outbox khi phù hợp, recovery, retry và consumer idempotent**. Đánh giá đúng trade-off giữa **mất event** và **xử lý trùng** là nền tảng để xây dựng giao tiếp liên module vừa ít phụ thuộc vừa đáp ứng mức độ tin cậy mà nghiệp vụ thật sự yêu cầu.
