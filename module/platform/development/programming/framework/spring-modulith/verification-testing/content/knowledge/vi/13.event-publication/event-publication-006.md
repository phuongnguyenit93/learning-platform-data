# Publication target và trạng thái hoàn tất

## 1. Publication target là gì?

Trong Spring Modulith, khi một module phát sự kiện nghiệp vụ, có thể có nhiều **transactional event listener** quan tâm đến sự kiện đó. Spring Modulith Event Publication Registry theo dõi **một publication cho mỗi listener đích**, thay vì gộp mọi lần giao sự kiện vào một trạng thái chung.

**Publication target** là **đích nhận của một lần công bố event**: một listener được hạ tầng Spring Modulith nhận diện bằng `PublicationTargetIdentifier`. Trạng thái hoàn tất thuộc về **cặp event được phát và target cụ thể**. Nếu một target xử lý thành công, không có nghĩa tất cả target khác đều đã hoàn tất.

Ví dụ module `orders` phát `OrderPlaced`:

~~~text
orders.OrderService
   |
   | publishEvent(OrderPlaced(orderId = O-42))
   v
Event Publication Registry
   |
   +-- publication P1 --> inventory.OrderPlacedListener    [COMPLETED]
   |
   +-- publication P2 --> notifications.EmailListener     [FAILED]
~~~

Có **một event nghiệp vụ** nhưng **hai bản ghi publication** do có hai transactional listener đích. Hệ thống đã cập nhật tồn kho thành công, trong khi gửi email còn lỗi và cần xử lý riêng.

Đây là trọng tâm trong chương **Event publication** của học phần **SPRING_MODULITH_VERIFICATION_TESTING**: kiểm chứng ranh giới kiến trúc bằng `ApplicationModules`, kiểm thử phát và nhận event bằng `@ApplicationModuleTest`, kiểm chứng transaction/database, rồi đặt quality gate CI để phát hiện phụ thuộc sai và hồi quy.

### Sau bài này, bạn có thể

1. Giải thích quan hệ giữa **business event**, **publication ID** và **publication target**.
2. Đọc các API `TargetEventPublication`, `PublicationTargetIdentifier`, `EventPublicationRegistry` và `CompletedEventPublications`.
3. Hiểu vì sao trạng thái hoàn tất được ghi **riêng cho từng target**.
4. Phân biệt `COMPLETED`, `FAILED`, `PROCESSING` và những trạng thái khác theo phiên bản Spring Modulith.
5. Kiểm thử một target thành công trong khi target khác thất bại, kể cả tác động lên database và retry.
6. Kết hợp kiểm chứng module boundary và publication lifecycle trong CI.

## 2. Phân biệt event, publication và target

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Business event** | Sự thật nghiệp vụ được phát từ module nguồn. | `OrderPlaced("O-42")` |
| **Event payload** | Các dữ kiện công khai của sự thật nghiệp vụ. | `orderId`, `occurredAt` |
| **Publication** | Bản ghi việc event được giao cho một target. | `P1` và `P2` |
| **Publication ID** | Định danh riêng của **bản ghi publication**, do registry quản lý. | `UUID` của `P1` |
| **Publication target** | Định danh listener cần nhận event. | Listener cập nhật tồn kho |
| **Completion** | Việc **một target** xử lý thành công và registry ghi nhận hoàn tất. | `P1` completed, `P2` chưa |

Hãy phân biệt các ID:

- `orderId`: định danh đơn hàng, do nghiệp vụ quyết định.
- `eventId` nếu payload có: định danh lần phát sự kiện nghiệp vụ, hữu ích cho idempotency.
- `publication.getIdentifier()`: UUID của **một lần giao tới một target**. Nhiều target cho cùng event sẽ có các UUID publication khác nhau.
- `publication.getTargetIdentifier()`: đối tượng đại diện **listener đích**, không phải order ID, event ID hay mặc nhiên là module ID.

**Không suy ra module đích trực tiếp từ một chuỗi target bất kỳ.** Spring Modulith xác định target từ listener mà hạ tầng biết đến. Target thường gắn với danh tính listener, nhưng cách biểu diễn/khởi tạo phụ thuộc cơ chế nhận diện listener và phiên bản. Khi cần hiển thị theo module, hãy đối chiếu listener với ranh giới `ApplicationModules` thay vì đoán tên module từ chuỗi.

### 2.1. Những listener nào được registry theo dõi?

Trong cấu hình mặc định, registry tìm các listener được gắn `@TransactionalEventListener` (trực tiếp hoặc qua meta-annotation), bao gồm trường hợp sử dụng `@ApplicationModuleListener` của Spring Modulith.

~~~java
@Component
class StockListener {

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        // Công việc của module inventory.
    }
}

@Component
class EmailListener {

    @TransactionalEventListener
    void on(OrderPlaced event) {
        // Công việc của module notifications sau commit.
    }
}
~~~

`@TransactionalEventListener` mặc định dùng pha `AFTER_COMMIT` và `fallbackExecution=false`. Một `@EventListener` thông thường **không mặc nhiên có publication bền vững trong registry**. Có thể tùy chỉnh phạm vi annotation được theo dõi; khi làm vậy, một số transactional listener có thể bị loại khỏi registry theo cấu hình.

Nếu hệ thống chưa bật persistence starter tương ứng, đừng kết luận rằng event đã có bản ghi bền vững chỉ vì code dùng `publishEvent`.

## 3. Mô hình API: TargetEventPublication

Các abstraction quan trọng trong Spring Modulith:

| Kiểu | Package | Trách nhiệm |
| --- | --- | --- |
| `EventPublication` | `org.springframework.modulith.events` | Thông tin chung: event, ID, thời điểm phát, thời điểm hoàn tất, trạng thái phiên bản hỗ trợ. |
| `TargetEventPublication` | `org.springframework.modulith.events.core` | Mở rộng `EventPublication`, thêm `getTargetIdentifier()`. |
| `PublicationTargetIdentifier` | `org.springframework.modulith.events.core` | Giá trị định danh target; có `of(String)` và `getValue()`. |
| `EventPublicationRegistry` | `org.springframework.modulith.events.core` | Ghi nhận, đánh dấu hoàn tất và tra cứu publication chưa hoàn tất. |
| `CompletedEventPublications` | `org.springframework.modulith.events` | Truy vấn và dọn publication đã hoàn tất. |

Một `TargetEventPublication` có những thông tin cốt lõi sau:

~~~java
UUID publicationId = publication.getIdentifier();
Object payload = publication.getEvent();
Instant publishedAt = publication.getPublicationDate();
PublicationTargetIdentifier target = publication.getTargetIdentifier();
String targetValue = target.getValue();
Optional<Instant> completedAt = publication.getCompletionDate();
boolean done = publication.isCompleted();
~~~

Đây là đoạn dùng khi biến `publication` có kiểu `TargetEventPublication` và đã import các kiểu Java tương ứng. `getCompletionDate()` trả về `Optional<Instant>`: khi publication chưa hoàn tất, thường không có completion date. `isCompleted()` diễn đạt kết quả hoàn tất ở mức API.

Với Spring Modulith 2.0 trở lên còn có:

~~~java
EventPublication.Status status = publication.getStatus();
int attempts = publication.getCompletionAttempts();
Instant lastResubmission = publication.getLastResubmissionDate();
~~~

`getLastResubmissionDate()` có thể trả về `null` khi chưa từng resubmit. Những phương thức và lifecycle mới phải được đối chiếu với **phiên bản Spring Modulith thực tế**; không đưa code dành cho 2.x vào một dự án 1.x rồi kỳ vọng mọi API đều có sẵn.

### 3.1. Target ID có phải tên module không?

Không. Trong ví dụ, hai listener thuộc `inventory` và `notifications`, nhưng target là **listener cụ thể**. Một module có thể chứa **nhiều listener cùng xử lý một event**, dẫn tới nhiều publication đích trong **cùng một module**.

Ví dụ module `notifications` có:

~~~java
@Component
class CustomerEmailListener {
    @TransactionalEventListener
    void on(OrderPlaced event) { /* gửi email */ }
}

@Component
class SalesAlertListener {
    @TransactionalEventListener
    void on(OrderPlaced event) { /* báo cho bộ phận sales */ }
}
~~~

Cả hai đều thuộc `notifications` nhưng là hai target khác nhau và có trạng thái hoàn tất độc lập. Bởi vậy, **đếm module lắng nghe không đủ để dự đoán số publication**. Cần xem các transactional listener thực sự được đăng ký và có phù hợp event hay không.

### 3.2. Điều kiện hoàn tất gắn với target

Framework đánh dấu publication đã hoàn tất khi việc thực thi listener tương ứng **kết thúc thành công**. Nếu listener ném exception, hạ tầng sẽ không coi lần thực thi đó là completed thành công; cách lưu trạng thái thất bại phụ thuộc phiên bản/lifecycle.

Nếu listener **tự bắt exception rồi nuốt lỗi** và trả về bình thường, registry có thể coi publication đã hoàn tất dù nghiệp vụ downstream thực tế thất bại. Đó là lý do không nên bắt rồi bỏ qua lỗi khi muốn registry hỗ trợ recovery.

**Completion kỹ thuật không tự chứng minh nghiệp vụ đúng.** Ví dụ listener cập nhật sai số lượng tồn kho nhưng không ném exception vẫn có thể được đánh dấu hoàn tất. Phải có integration test kiểm tra side effect.

## 4. Lifecycle và trạng thái hoàn tất

Với Spring Modulith **2.0+**, mỗi `EventPublication` có `EventPublication.Status`:

| Trạng thái | Ý nghĩa | Có thể hiểu là đã hoàn tất thành công? |
| --- | --- | --- |
| `PUBLISHED` | Bản ghi đã được tạo; target chưa bắt đầu hoặc đang chờ thực thi. | Không |
| `PROCESSING` | Listener đã nhận việc và đang xử lý. | Không |
| `COMPLETED` | Listener thực thi thành công. | **Có** |
| `FAILED` | Listener thất bại hoặc publication bị xác định stale. | Không |
| `RESUBMITTED` | Publication trước đó lỗi đã được gửi lại, chờ xử lý tiếp. | Không |
| `ABANDONED` (**2.2+**) | Chính sách quyết định ngừng cố gắng xử lý publication lỗi. | **Không** |

~~~mermaid
stateDiagram-v2
    [*] --> PUBLISHED: Registry tạo publication
    PUBLISHED --> PROCESSING: Target bắt đầu
    PROCESSING --> COMPLETED: Listener xử lý thành công
    PROCESSING --> FAILED: Listener báo lỗi
    FAILED --> RESUBMITTED: Chính sách retry
    RESUBMITTED --> PROCESSING: Target thử lại
    PUBLISHED --> FAILED: Bị xác định stale
    PROCESSING --> FAILED: Bị xác định stale
    FAILED --> ABANDONED: Chính sách từ bỏ (2.2+)
~~~

Sơ đồ mô tả các chuyển tiếp chính; việc đánh dấu stale, retry, abandon và các tối ưu trong nhiều instance còn phụ thuộc cấu hình.

Ở các phiên bản **1.x**, có thể làm việc chủ yếu theo khái niệm **incomplete/completed**, dựa vào completion date hoặc API truy vấn, mà không có toàn bộ enum trạng thái của 2.x. Để viết tài liệu hoặc test tương thích, cần ghi rõ phiên bản.

### 4.1. Incomplete không đồng nghĩa FAILED

`EventPublicationRegistry.findIncompletePublications()` trả về các publication chưa completed. Trong số đó có thể có publication mới phát, đang xử lý hoặc có lỗi. Không nên viết code “cứ incomplete là retry ngay”, đặc biệt khi listener có thể xử lý lâu hoặc nhiều instance đang chạy.

`findIncompletePublicationsOlderThan(Duration)` giúp xem publication cũ hơn ngưỡng thời gian; đây là tín hiệu quan sát **tuổi tồn đọng**, không tự chứng minh nguyên nhân lỗi.

### 4.2. Khi nào trạng thái được ghi là COMPLETED?

Hãy tưởng tượng hai publication của cùng event:

| Thời điểm | Publication `P1` tới inventory | Publication `P2` tới email |
| --- | --- | --- |
| Sau khi transaction nguồn commit | `PUBLISHED` | `PUBLISHED` |
| Listener bắt đầu | `PROCESSING` | `PROCESSING` |
| Sau khi listener trả về | `COMPLETED` | `FAILED` |
| Sau retry | Vẫn completed | `RESUBMITTED` rồi `PROCESSING` |
| Email thành công lần sau | Vẫn completed | `COMPLETED` |

**Từng target có thể tiến triển khác nhau.** Không được đánh dấu toàn bộ event completed chỉ vì một target thành công. Nếu chỉ có một listener đích phù hợp, event đó có thể chỉ tạo một publication.

## 5. Completion mode thay đổi cách lưu bản ghi

Một publication được xử lý thành công không nhất thiết vẫn có một dòng trong bảng đang hoạt động. Property `spring.modulith.events.completion-mode` hỗ trợ các chế độ từ Spring Modulith 1.3:

| Mode | Khi target hoàn tất | Có thể truy vấn lịch sử completed? |
| --- | --- | --- |
| `UPDATE` (mặc định) | Cập nhật bản ghi, lưu completion date/trạng thái tương ứng. | Có, qua `CompletedEventPublications`. |
| `DELETE` | Xóa bản ghi của target đã hoàn tất. | Không thể lấy bản ghi đã xóa từ registry. |
| `ARCHIVE` | Chuyển publication đã hoàn tất sang vùng lưu trữ archive. | Có, qua API completed tương ứng. |

Ví dụ:

~~~properties
# Giữ lịch sử hoàn tất trong kho hiện tại (mặc định).
spring.modulith.events.completion-mode=UPDATE
~~~

Chọn `DELETE` khi muốn giảm dữ liệu lưu giữ:

~~~properties
spring.modulith.events.completion-mode=DELETE
~~~

**Không đồng nhất “không tìm thấy publication” với “listener đã thành công”.** Bản ghi có thể không tồn tại vì target không thuộc phạm vi theo dõi, transaction nguồn rollback, lỗi cấu hình, hoặc vì đã completed và bị xóa theo mode `DELETE`.

Với `UPDATE` và `ARCHIVE`, cần kế hoạch purge dữ liệu cũ hoặc quản lý archive. Nếu kiểm thử dựa vào `CompletedEventPublications.findAll()`, phải chọn completion mode tương ứng; test đó sẽ không hợp lệ với `DELETE`.

## 6. Ví dụ kiến trúc: orders, inventory, notifications

Giả sử ứng dụng Spring Boot đặt lớp `ShopApplication` ở `com.example.shop`, Spring Modulith dùng cách phát hiện module mặc định theo package con:

~~~text
com.example.shop
├── ShopApplication.java
├── orders
│   ├── OrderService.java
│   ├── internal
│   │   └── OrderEntity.java
│   └── events
│       ├── OrderPlaced.java
│       └── package-info.java
├── inventory
│   ├── StockListener.java
│   └── package-info.java
└── notifications
    ├── EmailListener.java
    └── package-info.java
~~~

### 6.1. Event payload và API được công bố

File `orders/events/OrderPlaced.java`:

~~~java
package com.example.shop.orders.events;

import java.time.Instant;
import java.util.UUID;

public record OrderPlaced(UUID orderId, Instant occurredAt) {}
~~~

File `orders/events/package-info.java`:

~~~java
@org.springframework.modulith.NamedInterface("events")
package com.example.shop.orders.events;
~~~

Record mang dữ kiện nghiệp vụ ổn định. Không đưa `OrderEntity` hoặc `OrderRepository` nội bộ vào payload, vì module khác chỉ cần biết API sự kiện.

### 6.2. Module nguồn phát event

File `orders/OrderService.java` (rút gọn phần persistence):

~~~java
package com.example.shop.orders;

import com.example.shop.orders.events.OrderPlaced;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.UUID;

@Service
public class OrderService {

    private final ApplicationEventPublisher events;

    OrderService(ApplicationEventPublisher events) {
        this.events = events;
    }

    @Transactional
    public void place(UUID id) {
        // Trong ứng dụng thật: kiểm tra điều kiện và lưu order.
        events.publishEvent(new OrderPlaced(id, Instant.now()));
    }
}
~~~

`orders` là **module phát**, vì mã use case gọi `publishEvent`. Registry xác định các **listener target** có liên quan và ghi publication khi được cấu hình với persistence phù hợp. Một lần gọi `publishEvent` không làm `OrderService` nhận trách nhiệm đánh dấu completed cho mọi target.

### 6.3. Hai module nhận với hai publication

File `inventory/StockListener.java`:

~~~java
package com.example.shop.inventory;

import com.example.shop.orders.events.OrderPlaced;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class StockListener {

    private final StockReservationService reservations;

    StockListener(StockReservationService reservations) {
        this.reservations = reservations;
    }

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        reservations.reserveFor(event.orderId());
    }
}
~~~

File `notifications/EmailListener.java`:

~~~java
package com.example.shop.notifications;

import com.example.shop.orders.events.OrderPlaced;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class EmailListener {

    private final ConfirmationSender sender;

    EmailListener(ConfirmationSender sender) {
        this.sender = sender;
    }

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        sender.sendFor(event.orderId());
    }
}
~~~

`StockReservationService` và `ConfirmationSender` là các bean nghiệp vụ nội bộ cần tự triển khai. `@ApplicationModuleListener` có ngữ nghĩa transactional, bất đồng bộ và chạy listener trong transaction riêng theo cơ chế Spring Modulith.

Nếu `reservations.reserveFor(...)` thành công mà `sender.sendFor(...)` ném exception, publication tới `StockListener` được xác nhận thành công, còn publication tới `EmailListener` chưa completed. Không viết listener bắt lỗi rồi bỏ qua nếu muốn registry theo dõi thất bại.

### 6.4. Ranh giới module vẫn cần được kiểm chứng

File `inventory/package-info.java` (module notifications cũng khai báo tương tự):

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "orders :: events"
)
package com.example.shop.inventory;
~~~

Trong module test kiến trúc:

~~~java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleArchitectureTests {

    @Test
    void verifiesBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

`verify()` ngăn phụ thuộc vòng/truy cập API nội bộ trái quy tắc. Nó **không kiểm tra** có đúng hai target được đăng ký, publication đã completed hay listener đã cập nhật database. Những điều đó phải kiểm thử ở runtime.

## 7. Truy vấn publication chưa hoàn tất theo target

Ví dụ một service **chỉ đọc**:

~~~java
package com.example.shop.operations;

import org.springframework.modulith.events.core.EventPublicationRegistry;
import org.springframework.modulith.events.core.TargetEventPublication;
import org.springframework.stereotype.Service;

import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

@Service
class PublicationInspector {

    private final EventPublicationRegistry registry;

    PublicationInspector(EventPublicationRegistry registry) {
        this.registry = registry;
    }

    List<PendingTarget> olderThanTenMinutes() {
        return registry.findIncompletePublicationsOlderThan(
                        Duration.ofMinutes(10))
                .stream()
                .map(this::describe)
                .toList();
    }

    private PendingTarget describe(TargetEventPublication publication) {
        return new PendingTarget(
                publication.getIdentifier(),
                publication.getTargetIdentifier().getValue(),
                publication.getEvent().getClass().getSimpleName(),
                publication.getPublicationDate());
    }

    record PendingTarget(
            UUID publicationId,
            String targetId,
            String eventType,
            Instant publishedAt) {}
}
~~~

Mỗi dòng trả về tương ứng một **publication của một target**. Nếu hai publication thuộc cùng event nhưng chỉ email chưa hoàn tất, danh sách kết quả có thể chỉ chứa target email. Không nên nhầm việc không xuất hiện trong incomplete với bằng chứng một target chắc chắn đã từng được đăng ký.

Đây là API chẩn đoán; không mặc định đưa `getEvent()` (toàn bộ payload) ra màn hình hoặc log vì có thể làm lộ dữ liệu nghiệp vụ. Hãy phân quyền endpoint vận hành và giới hạn số lượng kết quả trên hệ thống lớn.

### 7.1. Xem trạng thái trong Spring Modulith 2.0+

Trong một method có field `registry`:

~~~java
for (var publication : registry.findIncompletePublications()) {
    var target = publication.getTargetIdentifier().getValue();
    var status = publication.getStatus();
    var attempts = publication.getCompletionAttempts();

    System.out.printf("target=%s status=%s attempts=%d%n",
            target, status, attempts);
}
~~~

Với các hệ thống có retry, việc quan sát `getLastResubmissionDate()`, số lần xử lý và tuổi publication theo **từng target** hữu ích hơn việc chỉ đếm tổng số event phát.

### 7.2. Xem publication completed

`CompletedEventPublications` trả về các `EventPublication` đã hoàn tất. Với `UPDATE` hoặc `ARCHIVE`:

~~~java
import org.springframework.modulith.events.CompletedEventPublications;

// Trong một bean được inject CompletedEventPublications completed:
long completedCount = completed.findAll().stream()
        .filter(publication ->
                publication.getEvent() instanceof OrderPlaced)
        .count();
~~~

`CompletedEventPublications.findAll()` có kiểu kết quả là các `EventPublication`, **không nên giả định mọi biến ở đây có sẵn `getTargetIdentifier()`** nếu chưa kiểm tra kiểu `TargetEventPublication`. Nếu dashboard cần nhóm bản ghi completed theo target, hãy dùng API/kiểu dữ liệu cung cấp target một cách an toàn.

Chế độ `DELETE` sẽ xóa bản ghi completed, vì vậy `findAll()` có thể rỗng sau một lần xử lý hoàn toàn thành công. Một test chỉ đếm bản ghi completed sẽ cho kết quả khác nhau tùy completion mode.

## 8. Kiểm thử registry: hoàn tất một target không hoàn tất target khác

Để kiểm chứng nguyên tắc **per-target completion** ở mức registry, có thể lưu hai publication giả lập trong một integration test rồi chủ động đánh dấu completed **một target**. Đây là bài test cơ chế registry, **không phải** cách code nghiệp vụ nên gọi `store` hay `markCompleted` trong production.

Điều kiện chạy: đã có Spring Boot, một starter registry persistence, database test, schema phù hợp, transaction manager; test chủ động dùng mode `UPDATE`.

~~~java
package com.example.shop;

import com.example.shop.orders.events.OrderPlaced;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.modulith.events.CompletedEventPublications;
import org.springframework.modulith.events.core.EventPublicationRegistry;
import org.springframework.modulith.events.core.PublicationTargetIdentifier;
import org.springframework.test.context.TestPropertySource;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

import java.time.Instant;
import java.util.UUID;
import java.util.stream.Stream;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@TestPropertySource(properties =
        "spring.modulith.events.completion-mode=UPDATE")
class PublicationTargetRegistryTests {

    @Autowired EventPublicationRegistry registry;
    @Autowired CompletedEventPublications completed;
    @Autowired PlatformTransactionManager transactionManager;

    @Test
    void completesOnlyTheSelectedTarget() {
        var event = new OrderPlaced(UUID.randomUUID(), Instant.now());
        var stock = PublicationTargetIdentifier.of("test-stock-target");
        var email = PublicationTargetIdentifier.of("test-email-target");
        var transaction = new TransactionTemplate(transactionManager);

        // Chỉ kiểm tra registry: không tự publish event lên Spring bus.
        transaction.executeWithoutResult(status ->
                registry.store(event, Stream.of(stock, email)));

        transaction.executeWithoutResult(status ->
                registry.markCompleted(event, stock));

        var incompleteForEvent = registry.findIncompletePublications()
                .stream()
                .filter(publication ->
                        publication.getEvent() instanceof OrderPlaced placed
                                && placed.orderId().equals(event.orderId()))
                .toList();

        assertThat(incompleteForEvent).hasSize(1);
        assertThat(incompleteForEvent.get(0).getTargetIdentifier())
                .isEqualTo(email);

        var completedForEvent = completed.findAll().stream()
                .filter(publication ->
                        publication.getEvent() instanceof OrderPlaced placed
                                && placed.orderId().equals(event.orderId()))
                .toList();

        assertThat(completedForEvent).hasSize(1);
        assertThat(completedForEvent.get(0).isCompleted()).isTrue();
    }
}
~~~

Hai `PublicationTargetIdentifier` trong test là **ID giả lập** để kiểm tra bản ghi riêng theo target. Trong ứng dụng thật, listener identifier do Spring Modulith cung cấp; không nên đặt một chuỗi tùy ý rồi coi đó là ID của listener production. Test này giả định registry có thể lưu và deserialize payload `OrderPlaced` đúng cách.

Để tránh xung đột dữ liệu khi chạy CI song song, mỗi lần test sử dụng `orderId` mới và nên dọn các publication thử nghiệm theo chính sách fixture. Nếu thử nhiều mode, tách test context tương ứng; không suy ra completed record còn lưu trong `DELETE`.

### 8.1. Test module nguồn với PublishedEvents

Test ở package `com.example.shop.orders`:

~~~java
package com.example.shop.orders;

import com.example.shop.orders.events.OrderPlaced;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.PublishedEvents;

import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;

@ApplicationModuleTest
class OrderPublicationTests {

    @Autowired OrderService orders;

    @Test
    void publishesOrderPlaced(PublishedEvents events) {
        UUID id = UUID.randomUUID();

        orders.place(id);

        assertThat(events.ofType(OrderPlaced.class)
                .matching(OrderPlaced::orderId, id))
                .hasSize(1);
    }
}
~~~

Test này chỉ xác nhận module `orders` phát sự kiện với payload phù hợp. Nếu `@ApplicationModuleTest` chỉ bootstrap module nguồn, listener của `inventory` và `notifications` có thể không có trong context; **không được suy ra có hai publication** chỉ từ `PublishedEvents`.

### 8.2. Integration test với listener thật

Để kiểm chứng registry tự tạo và tự hoàn tất các publication, xây dựng một `@SpringBootTest` có cả hai listener, datasource và transaction thật. Dùng một event test riêng với hai listener có thể điều khiển kết quả, sau đó:

1. Phát event **trong transaction**, commit thật; không đặt `@Transactional` quanh test rồi để Spring Test rollback.
2. Listener A xử lý thành công và cập nhật dữ liệu test.
3. Listener B ném exception có chủ đích. Với listener async, chờ cho tới khi kết quả được ghi nhận; không dùng `Thread.sleep` cố định.
4. Truy vấn `findIncompletePublications()` và lọc bằng event ID test, rồi kiểm tra **chỉ target B** còn chưa completed.
5. Ở mode `UPDATE` hoặc `ARCHIVE`, kiểm tra publication của A đã completed; xác nhận side effect trong database đúng.
6. Cho B xử lý lại theo API recovery phù hợp rồi kiểm tra B completed mà A không bị chạy lại ngoài dự kiến.

Ở phiên bản 2.0+, có thể kiểm tra `FAILED` và số lần thử. Ở phiên bản 1.x, kiểm tra incomplete/completed bằng API được hỗ trợ. Nếu kết quả có thể đến bất đồng bộ, dùng `Scenario` của Spring Modulith hoặc công cụ chờ theo điều kiện như Awaitility.

**Lưu ý transaction:** `@TransactionalEventListener` mặc định chạy sau commit. Một test tự gắn `@Transactional` và rollback cuối test sẽ không kích hoạt listener `AFTER_COMMIT`. `@ApplicationModuleListener` cũng xử lý bất đồng bộ, nên assertion ngay sau `publishEvent` chưa chứng minh callback đã hoàn tất.

## 9. Retry, xử lý lỗi và ý nghĩa của COMPLETED

Một publication không completed có thể được xử lý lại theo chính sách. Spring Modulith cung cấp:

- `IncompleteEventPublications`: hỗ trợ resubmit publication chưa hoàn tất theo bộ lọc/độ tuổi.
- `FailedEventPublications` (**2.0+**): hỗ trợ chọn các publication ở trạng thái `FAILED` để resubmit.
- Cơ chế staleness (**2.0+**): có thể đánh dấu publication ở trạng thái chờ hoặc xử lý quá lâu thành `FAILED` nếu được cấu hình.
- `AbandonedEventPublications` và chính sách `ABANDONED` (**2.2+**): theo dõi những publication mà ứng dụng quyết định ngừng resubmit.

Không bật retry cho mọi incomplete mà không xét tuổi/trạng thái: target có thể còn đang xử lý trên instance khác. Trong môi trường nhiều instance, cần cơ chế tránh claim trùng và bảo đảm side effect idempotent.

### 9.1. COMPLETED có chứng minh “đúng một lần” không?

Không. Ví dụ:

1. Listener email gửi thư thành công.
2. Tiến trình dừng trước khi registry ghi completed.
3. Publication được resubmit, listener gửi thư lần nữa.

Registry sẽ vẫn cho phép recovery publication chưa hoàn tất, nhưng việc gửi email **có thể đã xảy ra**. `COMPLETED` chỉ phản ánh hạ tầng ghi nhận listener hoàn tất thành công, không phải chứng nhận delivery đúng một lần đến hệ thống bên ngoài.

Vì vậy cần idempotency:

- Sinh `eventId` ổn định ở nguồn nếu một event có thể được phát hoặc xử lý lại.
- Lưu dấu xử lý theo event ID hoặc một khóa nghiệp vụ duy nhất cùng transaction với thay đổi database của listener.
- Sử dụng idempotency key của nhà cung cấp API ngoài nếu được hỗ trợ.
- Không biến một lỗi tạm thời thành “success” bằng cách bắt và nuốt exception.
- Có chính sách cảnh báo cho publication `FAILED` nhiều lần hoặc `ABANDONED`, và cách can thiệp vận hành.

### 9.2. Đổi tên listener và mapping target

Do registry lưu **target identifier**, khi thay đổi tên lớp, tên method, cấu hình hoặc cách Spring nhận diện listener giữa các phiên bản deploy, publication tồn đọng có thể không còn ánh xạ như trước. Cần đánh giá khả năng khôi phục publication chưa hoàn tất trước những thay đổi lớn của listener; kiểm thử restart/upgrade nếu hệ thống yêu cầu delivery bền vững.

Không nên tự chỉnh dữ liệu target identifier trong database production khi chưa hiểu cơ chế nhận diện và tương thích của phiên bản đang dùng.

## 10. Theo dõi và quality gate trong CI

Một dashboard publication nên xem **theo từng target**:

| Chỉ số | Dùng để phát hiện |
| --- | --- |
| Số incomplete theo target | Listener nào tồn đọng nhiều publication. |
| Tuổi publication cũ nhất theo target | Sự kiện nào có nguy cơ vượt SLA xử lý. |
| Số `FAILED`/`ABANDONED` (phiên bản hỗ trợ) | Lỗi downstream kéo dài hoặc đã từ bỏ xử lý. |
| Thời gian từ `getPublicationDate()` tới `getCompletionDate()` | Độ trễ xử lý của từng target. |
| Số completion attempts / lần resubmit (2.0+) | Lỗi lặp, nguy cơ bão retry. |
| Số completed giữ lại theo mode `UPDATE`/`ARCHIVE` | Nhu cầu purge và dung lượng lưu trữ. |

Không công bố toàn bộ payload ra endpoint metrics hoặc log vì sự kiện có thể chứa dữ liệu riêng tư. Với `DELETE`, muốn quan sát thành công dài hạn cần metrics riêng vì completed record không còn lưu trong registry.

| Kiểm tra CI | Điều xác nhận | Điều không thể suy ra chỉ từ test đó |
| --- | --- | --- |
| `ApplicationModules.verify()` | Dependency giữa `orders`, `inventory`, `notifications` hợp lệ. | Target publication đã được tạo. |
| `@ApplicationModuleTest` + `PublishedEvents` | Use case đã phát `OrderPlaced` đúng payload. | Listener nào completed. |
| Registry contract test hai target | Mark completed target A không làm B completed. | Listener thực tế đã được Spring tự đăng ký. |
| Integration test có listener/database | Publication được tạo theo target, xử lý sau commit và cập nhật trạng thái. | Tác động bên ngoài JVM chính xác một lần. |
| Retry/idempotency/serialization test | Publication lỗi xử lý lại mà không nhân đôi dữ liệu; payload còn đọc được. | Hệ thống không bao giờ có sự cố trong production. |

Đặt các test quan trọng vào tác vụ test của dự án trong pipeline CI và coi failure là tín hiệu chặn thay đổi. Các test liên quan database phải chạy với transaction manager/schema phù hợp; test async cần chờ theo điều kiện. `ApplicationModules.verify()` là quality gate kiến trúc, còn target completion là quality gate hành vi và tích hợp.

## 11. Tình huống luyện tập

Hệ thống thương mại điện tử có ba module:

- `checkout` phát `PaymentAccepted` sau khi lưu thanh toán trong transaction.
- `fulfillment` có listener `reserveStock(...)` và `createShipment(...)`, cả hai đều transactional.
- `loyalty` có listener `addPoints(...)`.

Một `PaymentAccepted` được phát với ba listener phù hợp. Sau commit:

| Target | Kết quả |
| --- | --- |
| `fulfillment.reserveStock` | Thành công |
| `fulfillment.createShipment` | Thất bại vì database không sẵn sàng |
| `loyalty.addPoints` | Thành công |

Hãy trả lời:

1. Có bao nhiêu publication về mặt logic? Có bao nhiêu module nhận?
2. Publication nào completed? Publication nào cần phục hồi?
3. Khi kiểm tra `findIncompletePublications()`, vì sao không thể kết luận mọi phần tử đều `FAILED`?
4. Nếu bật completion mode `DELETE`, việc không tìm thấy bản ghi `reserveStock` có đủ chứng minh listener đã thành công không?
5. Vì sao không nên dùng `publicationId` thay thế hoàn toàn `eventId` để chống tác động lặp tại business consumer?
6. Những test nào cần có để chứng minh cả ranh giới module và trạng thái xử lý event?

**Đáp án tham khảo:**

1. **Ba publication**, tương ứng ba listener target; chỉ có **hai module nhận** là `fulfillment` và `loyalty`.
2. Hai publication tới `reserveStock`, `addPoints` completed; `createShipment` chưa completed và cần đánh giá retry.
3. Vì incomplete có thể gồm publication mới được tạo hoặc đang xử lý. Trạng thái chi tiết tùy phiên bản.
4. Không. Bản ghi có thể bị xóa sau thành công, nhưng cũng có thể không tồn tại do một nguyên nhân cấu hình/đăng ký/rollback khác.
5. Một event có nhiều publication ID, còn `eventId` có thể đại diện cùng sự kiện nghiệp vụ xuyên các lần giao lại; chính sách chống trùng phải khớp hành vi nghiệp vụ.
6. Có architecture test `ApplicationModules.verify()`, test phát `PublishedEvents`, integration test với các listener thật và registry, cùng test lỗi/rollback/retry/idempotency.

## 12. Checklist khi kiểm chứng publication target

- [ ] Xác định event nguồn và **tất cả transactional listener** phù hợp event.
- [ ] Phân biệt số lượng module nhận với số lượng listener target.
- [ ] Dùng `getTargetIdentifier()` để xác định **target** của một `TargetEventPublication`; không suy đoán từ tên payload.
- [ ] Phân biệt `orderId`, `eventId`, `publicationId` và `PublicationTargetIdentifier`.
- [ ] Kiểm tra đúng version khi sử dụng `Status`, attempts, staleness hoặc `ABANDONED`.
- [ ] Hiểu completion mode `UPDATE`, `DELETE`, `ARCHIVE` trước khi viết assertion.
- [ ] Test chỉ completed target được chọn, target khác vẫn incomplete khi chưa xử lý.
- [ ] Test event phát trong transaction commit thật; rollback không tạo publication bền vững sai.
- [ ] Test side effect của listener trên database, không chỉ nhìn publication status.
- [ ] Có idempotency và quy trình xử lý khi retry; không tự động resubmit công việc vẫn đang chạy.
- [ ] Event type thuộc API được công bố; chạy `ApplicationModules.verify()` trong CI.
- [ ] Chạy module test, registry integration test và retry test qua quality gate CI.

**Ghi nhớ:** Publication target là **listener đích**, còn trạng thái `COMPLETED` là kết quả **riêng của lần giao event tới listener đó**. Một event được phát thành công vẫn có thể để lại nhiều publication ở trạng thái khác nhau. Hãy kiểm chứng cả target, completion mode, side effect và ranh giới module trước khi kết luận luồng sự kiện hoàn tất.

### Tài liệu tham khảo

- [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html): event publication registry, completion mode và lifecycle.
- [EventPublication API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/events/EventPublication.html): publication ID, event, completion date, status.
- [TargetEventPublication API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/events/core/TargetEventPublication.html): `getTargetIdentifier()`.
- [PublicationTargetIdentifier API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/events/core/PublicationTargetIdentifier.html): `of(String)`, `getValue()`.
- [EventPublicationRegistry API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/events/core/EventPublicationRegistry.html): truy vấn incomplete, ghi nhận và hoàn tất publication.

> Ghi chú tương thích: trạng thái chi tiết `EventPublication.Status` xuất hiện từ Spring Modulith 2.0; `ABANDONED` từ 2.2. Cần đối chiếu đúng phiên bản ứng dụng trước khi áp dụng ví dụ API.
