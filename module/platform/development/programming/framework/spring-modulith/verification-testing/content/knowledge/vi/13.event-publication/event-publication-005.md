# EventPublicationRegistry theo dõi publication

## 1. EventPublicationRegistry giải quyết vấn đề gì?

Trong Spring Modulith, một module có thể phát sự kiện bằng `ApplicationEventPublisher.publishEvent(...)` để các module khác xử lý sau khi transaction nghiệp vụ commit. Tuy nhiên, **phát thành công không đồng nghĩa mọi listener đã xử lý thành công**. Listener có thể lỗi database, timeout, mất kết nối đến dịch vụ ngoài, hoặc ứng dụng có thể dừng trước khi listener bất đồng bộ bắt đầu chạy.

`EventPublicationRegistry` là thành phần của Spring Modulith dùng để **theo dõi các lần công bố sự kiện tới những transactional listener cụ thể**. Khi được cấu hình với bộ lưu trữ bền vững, registry ghi nhận từng publication trong transaction nghiệp vụ nguồn và theo dõi khi listener hoàn tất. Nhờ vậy hệ thống có cơ sở để phát hiện publication chưa hoàn tất và triển khai chính sách xử lý lại.

**Phân biệt ba khái niệm:**

| Khái niệm | Câu hỏi trả lời | Bằng chứng |
| --- | --- | --- |
| **Event được phát** | Use case đã gọi `publishEvent` với payload nào? | Call site hoặc `PublishedEvents` trong module test. |
| **Publication được theo dõi** | Có bản ghi cho event gửi tới listener đích nào? | Event Publication Registry và kho lưu trữ đã cấu hình. |
| **Listener hoàn tất** | Listener đích đã xử lý thành công và trạng thái publication được cập nhật chưa? | Trạng thái registry **kết hợp** kết quả xử lý nghiệp vụ. |

Giả sử module `orders` phát `OrderPlaced`, hai module `inventory` và `notifications` cùng lắng nghe bằng transactional listener. Một lần gọi `publishEvent` có thể tạo **hai publication độc lập**: một cho listener tồn kho, một cho listener thông báo. Tồn kho xử lý thành công không làm publication gửi thông báo tự động hoàn tất.

Đây là trọng tâm của học phần **SPRING_MODULITH_VERIFICATION_TESTING**: kiểm chứng ranh giới kiến trúc bằng `ApplicationModules`, kiểm tra phát và nhận sự kiện bằng `@ApplicationModuleTest`, tích hợp database, và đưa phép kiểm tra publication vào quality gate CI để ngăn hồi quy.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Mô tả cách registry ghi lại event theo **từng listener**, không chỉ theo kiểu sự kiện.
2. Phân biệt publication đang chờ, đang xử lý, hoàn tất, lỗi và trường hợp có thể được gửi lại.
3. Thiết lập bộ lưu trữ registry và hiểu tác động của transaction commit/rollback.
4. Dùng `EventPublicationRegistry` quan sát publication chưa hoàn tất; phân biệt API quan sát với API resubmission.
5. Kiểm thử publication thành công, thất bại, rollback, retry và idempotency.
6. Kết hợp test boundary với integration test trong CI và các chỉ số giám sát vận hành.

## 2. Registry hoạt động như thế nào?

Trong luồng điển hình:

1. `OrderService.place(...)` mở transaction, lưu đơn hàng rồi phát `OrderPlaced`.
2. Registry nhận biết các transactional listener phù hợp và ghi **một publication cho mỗi listener đích** trong transaction nguồn.
3. Nếu transaction nguồn rollback, bản ghi publication trong transaction đó cũng rollback; listener `AFTER_COMMIT` không được kích hoạt.
4. Nếu commit thành công, listener được phép xử lý theo pha transaction của mình, có thể bất đồng bộ.
5. Khi listener thành công, registry ghi nhận hoàn tất. Nếu listener lỗi, publication còn thông tin để nhận diện và áp dụng chính sách xử lý lại.

~~~mermaid
sequenceDiagram
    participant API as Client
    participant Orders as orders.OrderService
    participant DB as Business DB
    participant Registry as EventPublicationRegistry
    participant Inventory as inventory.Listener
    participant Notification as notifications.Listener

    API->>Orders: place(orderId)
    Orders->>DB: Lưu đơn hàng (transaction nguồn)
    Orders->>Registry: publishEvent(OrderPlaced)
    Registry->>DB: Ghi publication cho 2 listener
    Orders->>DB: COMMIT
    par Hai listener xử lý độc lập
        Registry-->>Inventory: Giao event sau commit
        Inventory-->>Registry: Thành công, đánh dấu completed
    and
        Registry-->>Notification: Giao event sau commit
        Notification-->>Registry: Lỗi, còn publication cần xử lý
    end
~~~

Sơ đồ minh họa đường thành công/đường lỗi, không bảo đảm hai listener chạy đồng thời trong mọi cấu hình. Sự kiện được phân phối bởi cơ chế Spring; registry **ghi nhận và điều phối vòng đời publication**, không phải một message broker độc lập.

### 2.1. Bản ghi là một cặp event và target

Một publication thường gắn với:

- **Định danh publication**: ID riêng cho bản ghi giao sự kiện.
- **Event/payload**: dữ liệu nghiệp vụ cần chuyển đến listener.
- **Target identifier**: định danh listener đích.
- **Thời điểm công bố** và thông tin hoàn tất/trạng thái.

Với cùng một `OrderPlaced(orderId)`:

| Publication ID (minh họa) | Event | Listener đích | Kết quả |
| --- | --- | --- | --- |
| `pub-A` | `OrderPlaced(O-42)` | `inventory` | Đã hoàn tất |
| `pub-B` | `OrderPlaced(O-42)` | `notifications` | Thất bại hoặc chưa hoàn tất |

Các ID trong bảng chỉ để giải thích. Trong API thực tế, định danh publication là `UUID`; tên hiển thị của target phụ thuộc cách Spring Modulith nhận diện listener. **Publication ID không thay thế event ID nghiệp vụ**: cùng một event có thể có nhiều publication cho nhiều target.

### 2.2. Registry theo dõi những listener nào?

Theo cấu hình mặc định của Spring Modulith, các listener được gắn (trực tiếp hoặc thông qua meta-annotation) `@TransactionalEventListener` được xét để tạo publication. `@ApplicationModuleListener` cũng thuộc mô hình listener theo transaction. Một `@EventListener` thông thường **không mặc nhiên** được registry theo dõi như transactional listener.

Có thể tùy chỉnh annotation kích hoạt registry bằng property:

~~~properties
spring.modulith.events.registry-trigger-annotation=org.springframework.modulith.events.ApplicationModuleListener
~~~

**Chỉ dùng cấu hình này khi muốn giới hạn đối tượng theo dõi.** Nếu chọn chỉ `@ApplicationModuleListener`, các `@TransactionalEventListener` khác có thể không được registry ghi nhận. Cần kiểm tra phiên bản Spring Modulith và chính sách event của ứng dụng trước khi thay đổi.

## 3. Chuẩn bị ứng dụng và persistence cho registry

Để có bản ghi bền vững, ứng dụng cần cả cơ chế event của Spring Modulith và một triển khai persistence/serialization phù hợp. Các starter của Spring Modulith dành cho một số công nghệ lưu trữ gồm:

| Công nghệ | Starter | Ghi chú |
| --- | --- | --- |
| JDBC | `spring-modulith-starter-jdbc` | Ghi publication qua JDBC, dùng được cả trong ứng dụng có JPA. |
| JPA | `spring-modulith-starter-jpa` | Sử dụng persistence dựa trên JPA. |
| MongoDB | `spring-modulith-starter-mongodb` | Cần cấu hình transaction thích hợp; MongoDB transactions yêu cầu replica set. |
| Neo4j | `spring-modulith-starter-neo4j` | Dùng kho lưu trữ Spring Data Neo4j. |

Ví dụ Gradle với JDBC:

~~~groovy
dependencies {
    implementation 'org.springframework.modulith:spring-modulith-starter-jdbc'
    testImplementation 'org.springframework.modulith:spring-modulith-starter-test'
}
~~~

Ví dụ trên giả định ứng dụng có quản lý phiên bản dependency qua Spring Modulith BOM/Spring Boot và đã cấu hình datasource, transaction manager, driver. Không thể chỉ thêm dependency rồi mặc nhiên có một database đã sẵn sàng.

Đối với JDBC starter, cần xác nhận schema publication được tạo phù hợp. Ứng dụng có thể để cơ chế khởi tạo schema mặc định hoạt động hoặc quản lý DDL bằng Flyway/Liquibase. Ví dụ nếu schema được migration tự quản lý:

~~~properties
spring.modulith.events.jdbc.schema-initialization.enabled=false
~~~

Chỉ tắt schema initialization khi **đã có migration tạo đúng cấu trúc** cần thiết; nếu không, việc ghi publication sẽ thất bại.

### 3.1. Vì sao registry phải tham gia transaction nguồn?

Nếu việc ghi đơn hàng thành công nhưng không có publication nào được ghi bền vững, hệ thống có thể mất thông tin cần xử lý downstream. Nếu đơn hàng rollback nhưng publication vẫn tồn tại, listener có thể xử lý một sự kiện nghiệp vụ chưa từng commit.

Trong mô hình registry của Spring Modulith, bản ghi publication được lưu cùng transaction nghiệp vụ khi có cấu hình phù hợp. Khi transaction rollback, bản ghi publication cũng rollback. Đây là một lợi ích quan trọng của việc phát event **trong** transaction và dùng persistent event registry.

**Giới hạn:** registry không biến toàn bộ hiệu ứng của các listener thành cùng một transaction. `orders`, `inventory` và `notifications` có thể commit các transaction riêng; side effect ra mạng hoặc broker còn chịu mô hình xác nhận và retry riêng.

### 3.2. Payload cần có khả năng lưu và đọc lại

Publication bền vững thường phải lưu event ở dạng serialize. Một payload Java record thuần dữ liệu đơn giản:

~~~java
package com.example.shop.orders.events;

import java.time.Instant;
import java.util.UUID;

public record OrderPlaced(UUID orderId, Instant occurredAt) {}
~~~

Phù hợp hơn việc đưa JPA entity, Hibernate lazy proxy, Spring bean hoặc database connection vào event. Kiểm thử round-trip serialization bằng đúng `EventSerializer` được dùng trong ứng dụng. Các starter thông dụng dùng Jackson-based serializer theo tài liệu Spring Modulith; nếu ứng dụng tự cấu hình serializer hoặc kiểu ngày/giờ/value object phức tạp, phải kiểm thử cấu hình đó.

Không được coi một Java object gửi thành công tới listener trong cùng JVM là bằng chứng nó sẽ serialize và được đọc lại thành công sau restart.

## 4. Ví dụ modules: orders, inventory và notifications

Giả sử lớp `ShopApplication` nằm ở `com.example.shop`, Spring Modulith phát hiện các module từ các package con trực tiếp:

~~~text
com.example.shop
├── ShopApplication.java
├── orders
│   ├── OrderService.java
│   └── events
│       ├── OrderPlaced.java
│       └── package-info.java
├── inventory
│   ├── InventoryListener.java
│   └── package-info.java
└── notifications
    ├── NotificationListener.java
    └── package-info.java
~~~

### 4.1. Công bố event type qua named interface

File `orders/events/package-info.java`:

~~~java
@org.springframework.modulith.NamedInterface("events")
package com.example.shop.orders.events;
~~~

File `inventory/package-info.java` (module `notifications` có thể khai báo tương tự):

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "orders :: events"
)
package com.example.shop.inventory;
~~~

Nhờ đó, `inventory` được phép import `OrderPlaced` từ API `events` của `orders`, nhưng không cần truy cập service/repository nội bộ của module nguồn. `EventPublicationRegistry` **không thay thế** các quy tắc module boundary này.

### 4.2. Module nguồn phát event trong transaction

File `orders/OrderService.java`:

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

    private final ApplicationEventPublisher publisher;
    private final OrderRepository orders;

    public OrderService(ApplicationEventPublisher publisher,
                        OrderRepository orders) {
        this.publisher = publisher;
        this.orders = orders;
    }

    @Transactional
    public void place(UUID orderId) {
        orders.save(new OrderEntity(orderId));
        publisher.publishEvent(new OrderPlaced(orderId, Instant.now()));
    }
}
~~~

`OrderEntity` và `OrderRepository` là các lớp **nội bộ cần có trong ứng dụng thật**, được lược bỏ định nghĩa để tập trung vào registry. Đoạn ví dụ giả định repository lưu được entity và mọi ràng buộc transaction/JPA đã được cấu hình.

Module nguồn không cần gọi thủ công `registry.store(...)` trong use case: registry tích hợp với cơ chế phát event của Spring Modulith và tự xác định các transactional listener thuộc phạm vi theo dõi.

### 4.3. Các listener đích

File `inventory/InventoryListener.java`:

~~~java
package com.example.shop.inventory;

import com.example.shop.orders.events.OrderPlaced;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class InventoryListener {

    private final InventoryReservationService reservations;

    InventoryListener(InventoryReservationService reservations) {
        this.reservations = reservations;
    }

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        reservations.reserveFor(event.orderId());
    }
}
~~~

Ở đây `InventoryReservationService` là một bean nội bộ của `inventory` (lược bỏ định nghĩa) thực hiện thay đổi dữ liệu tồn kho. `@ApplicationModuleListener` có ngữ nghĩa transactional listener, bất đồng bộ và transaction mới cho công việc xử lý. Nếu service ném exception và không bị nuốt tại đây, invocation được xem là thất bại để registry theo dõi.

Listener `notifications` tương tự nhưng có thể gọi dịch vụ gửi email, và **cần chính sách idempotency** vì retry có thể khiến email được gửi lặp. Mỗi listener có một publication độc lập cho cùng event.

### 4.4. Cần chạy test kiến trúc

~~~java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleArchitectureTests {

    @Test
    void verifiesModuleBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

`ApplicationModules.verify()` kiểm chứng phụ thuộc tĩnh giữa module. Nó phát hiện những vi phạm như `inventory` import một repository nội bộ của `orders`, nhưng **không chứng minh** registry đã ghi publication hoặc listener đã xử lý thành công.

## 5. Vòng đời publication và trạng thái cần quan sát

Các phiên bản trước Spring Modulith 2.0 chủ yếu mô tả publication **incomplete** và **completed**; cách biểu diễn trạng thái hoặc API có thể khác giữa các phiên bản. **Từ Spring Modulith 2.0**, `EventPublication.Status` hỗ trợ vòng đời chi tiết hơn:

| Trạng thái | Ý nghĩa vận hành | Điều cần theo dõi |
| --- | --- | --- |
| `PUBLISHED` | Publication đã được lưu, đang chờ hoặc sắp được xử lý. | Bản ghi chờ quá lâu có thể báo hiệu listener chưa được tiếp nhận. |
| `PROCESSING` | Listener đã bắt đầu xử lý. | Nếu treo lâu, cần chính sách phát hiện stale phù hợp. |
| `COMPLETED` | Listener kết thúc thành công và publication đã được xác nhận hoàn tất. | Độ trễ từ publish đến complete; chính sách dọn dữ liệu. |
| `FAILED` | Invocation thất bại hoặc publication được xác định là stale. | Lỗi nguồn, số lần thử, khả năng retry. |
| `RESUBMITTED` | Publication lỗi đã được gửi lại để xử lý. | Số lần resubmit, khả năng gây tác động trùng. |
| `ABANDONED` *(từ 2.2)* | Hệ thống hoặc chính sách chủ động từ bỏ tiếp tục xử lý publication lỗi. | Cần điều tra hoặc can thiệp vận hành; **không** coi là hoàn tất thành công. |

~~~mermaid
stateDiagram-v2
    [*] --> PUBLISHED: Lưu publication
    PUBLISHED --> PROCESSING: Listener bắt đầu
    PROCESSING --> COMPLETED: Thành công
    PROCESSING --> FAILED: Thất bại
    FAILED --> RESUBMITTED: Cho phép retry
    RESUBMITTED --> PROCESSING: Xử lý lại
    PUBLISHED --> FAILED: Đánh dấu stale
    PROCESSING --> FAILED: Đánh dấu stale
    FAILED --> ABANDONED: Chính sách từ bỏ (2.2+)
~~~

Sơ đồ minh họa các chuyển tiếp quan trọng, không biểu diễn mọi tối ưu/lựa chọn completion mode. Trạng thái mới và cơ chế đánh dấu lỗi/stale phụ thuộc **phiên bản Spring Modulith** đang dùng.

### 5.1. Incomplete không đồng nghĩa thất bại

Một publication chưa completed có thể đang ở hàng chờ, đang xử lý, hoặc đang gặp lỗi. Nếu vừa phát event rồi gọi `findIncompletePublications()`, kết quả có thể bao gồm listener vẫn **đang chạy bình thường**. Không được mặc định retry tất cả publication chưa hoàn tất ngay lập tức, vì thao tác đó có thể gây xử lý đồng thời hoặc lặp.

Từ Spring Modulith 2.0, thông tin như `getStatus()`, `getCompletionAttempts()`, `getLastResubmissionDate()` giúp phân biệt những tình huống này. Hãy áp dụng ngưỡng tuổi, trạng thái và chính sách resubmission tương ứng thay vì chỉ nhìn số lượng incomplete.

### 5.2. Publication hoàn tất được lưu như thế nào?

Spring Modulith có các completion mode:

| Mode | Hành vi sau khi hoàn tất | Tác động tới giám sát |
| --- | --- | --- |
| `UPDATE` (mặc định) | Cập nhật thời điểm hoàn tất trên bản ghi. | Có thể truy vấn lịch sử completed; cần chính sách purge/archive để tránh bảng lớn vô hạn. |
| `DELETE` | Xóa bản ghi publication khi hoàn tất. | Không thể suy ra “chưa từng có publication” chỉ vì không tìm thấy bản ghi đã hoàn tất. |
| `ARCHIVE` | Chuyển/copy bản ghi đã hoàn tất sang vùng archive tương ứng. | Giữ dữ liệu để phân tích nhưng cần quản lý dung lượng và truy vấn. |

Ví dụ lựa chọn lưu lịch sử ít hơn:

~~~properties
spring.modulith.events.completion-mode=delete
~~~

Đây là quyết định vận hành cần thống nhất với nhu cầu audit/monitoring. Với `DELETE`, không thể test “đã completed” bằng cách tìm bản ghi completed trong bảng chính.

## 6. Quan sát trực tiếp bằng EventPublicationRegistry

Interface `org.springframework.modulith.events.core.EventPublicationRegistry` có các phương thức quan sát như:

- `findIncompletePublications()`: lấy các publication chưa hoàn tất.
- `findIncompletePublicationsOlderThan(Duration)`: lọc publication chưa hoàn tất quá một ngưỡng thời gian.
- `markCompleted(event, targetIdentifier)`: API ghi trạng thái hoàn tất theo event/target.
- `deleteCompletedPublicationsOlderThan(Duration)`: cơ chế dọn bản ghi hoàn tất.

Các API `store(...)`, `markCompleted(...)` hoặc các thao tác chuyển trạng thái thấp hơn chủ yếu do **hạ tầng registry** sử dụng trong luồng event thông thường. Mã nghiệp vụ không nên tự đánh dấu completed khi chưa thật sự thực hiện side effect, vì điều đó che giấu publication cần xử lý lại.

Ví dụ một thành phần chẩn đoán **chỉ đọc**:

~~~java
package com.example.shop.diagnostics;

import org.springframework.modulith.events.core.EventPublicationRegistry;
import org.springframework.modulith.events.core.TargetEventPublication;
import org.springframework.stereotype.Service;

import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

@Service
class PublicationDiagnostics {

    private final EventPublicationRegistry registry;

    PublicationDiagnostics(EventPublicationRegistry registry) {
        this.registry = registry;
    }

    List<PendingPublication> olderThanTenMinutes() {
        return registry.findIncompletePublicationsOlderThan(
                        Duration.ofMinutes(10))
                .stream()
                .map(this::toView)
                .toList();
    }

    private PendingPublication toView(TargetEventPublication publication) {
        return new PendingPublication(
                publication.getIdentifier(),
                publication.getTargetIdentifier().toString(),
                publication.getEvent().getClass().getSimpleName(),
                publication.getPublicationDate());
    }

    record PendingPublication(
            UUID publicationId,
            String target,
            String eventType,
            Instant publishedAt
    ) {}
}
~~~

Đoạn này minh họa truy vấn **publication cũ và chưa hoàn tất**, không tự retry. Kiểu `PendingPublication` cố ý không trả lại toàn bộ payload, vì event có thể chứa dữ liệu nghiệp vụ không phù hợp để đưa vào API giám sát. Nếu cần công bố dashboard hoặc endpoint, phải bổ sung phân quyền và giới hạn thông tin lộ ra ngoài.

### 6.1. Theo dõi trạng thái chi tiết ở Spring Modulith 2.0+

Với phiên bản có `EventPublication.Status`, có thể kiểm tra:

~~~java
registry.findIncompletePublications().forEach(publication -> {
    var status = publication.getStatus();
    var attempts = publication.getCompletionAttempts();
    var target = publication.getTargetIdentifier();

    // Đưa số liệu tổng hợp tới hệ thống metrics/log được phân quyền.
    System.out.printf("%s attempts=%d target=%s%n",
            status, attempts, target);
});
~~~

Đây là đoạn nằm trong service/bean đã có field `registry`, không phải file Java hoàn chỉnh. `getStatus()` và các thông tin lifecycle mới cần được đối chiếu với phiên bản Spring Modulith của dự án; không tự áp dụng code 2.x cho dự án 1.x.

### 6.2. Những gì registry không tự nói cho bạn

- **Không tự xác định “module nguồn” bằng package event**: phải xem nơi gọi `publishEvent`.
- **Không chứng minh dữ liệu downstream đúng về mặt nghiệp vụ** chỉ vì callback hoàn tất; listener có thể xử lý thành công theo kỹ thuật nhưng tính sai số lượng tồn kho.
- **Không chứng minh gửi email hoặc broker chính xác một lần**; một side effect ngoài transaction có thể xảy ra rồi tiến trình dừng trước khi ghi nhận completed.
- **Không thay thế distributed tracing**: registry theo dõi publication tới listener, không lưu toàn bộ đường đi của mọi request.
- **Không tự bảo vệ mọi `@EventListener`**: phạm vi đăng ký tùy loại listener và cấu hình trigger annotation.

## 7. Xử lý publication chưa hoàn tất và retry

Spring Modulith cung cấp các abstraction phục vụ quản lý publication ở mức ứng dụng:

| API | Vai trò |
| --- | --- |
| `EventPublicationRegistry` | Thao tác và truy vấn bản ghi publication ở mức registry. |
| `IncompleteEventPublications` | Resubmit các publication chưa hoàn tất theo tiêu chí/độ tuổi. |
| `CompletedEventPublications` | Xem và dọn publication đã hoàn tất. |
| `FailedEventPublications` *(từ 2.0)* | Resubmit riêng các publication ở trạng thái failed. |
| `AbandonedEventPublications` *(từ 2.2)* | Xem và quản lý publication đã bị từ bỏ. |

Ví dụ thao tác resubmit có điều kiện, cần dùng trong **job vận hành được kiểm soát**, không gọi tự động mỗi lần API nghiệp vụ chạy:

~~~java
package com.example.shop.operations;

import org.springframework.modulith.events.IncompleteEventPublications;
import org.springframework.stereotype.Service;

import java.time.Duration;

@Service
class PublicationRecovery {

    private final IncompleteEventPublications incomplete;

    PublicationRecovery(IncompleteEventPublications incomplete) {
        this.incomplete = incomplete;
    }

    void resubmitOldPublications() {
        incomplete.resubmitIncompletePublicationsOlderThan(
                Duration.ofMinutes(15));
    }
}
~~~

**Lưu ý:** ví dụ trên cho thấy API, không khuyến nghị chạy tất cả trong mọi môi trường. Cần cân nhắc publication thực sự còn đang xử lý, lượng tải, số instance, nguy cơ gửi lặp và khả năng downstream chịu được retry.

Từ Spring Modulith 2.0, có thể chọn resubmit riêng `FAILED` bằng `FailedEventPublications` với `ResubmissionOptions` để giới hạn batch, tuổi tối thiểu và điều kiện lọc. Từ 2.2 có thêm trạng thái `ABANDONED` cho lỗi mà hệ thống quyết định không tiếp tục resubmit. **Không đánh đồng `ABANDONED` với `COMPLETED`**.

### 7.1. Có nên bật republish khi restart?

Property:

~~~properties
spring.modulith.events.republish-outstanding-events-on-restart=true
~~~

cho phép tự phát lại các publication còn tồn khi ứng dụng khởi động theo cơ chế Spring Modulith. Mặc định property này là `false`. Với triển khai nhiều instance, một instance mới có thể thấy publication đang được instance khác xử lý, nên bật vô điều kiện có thể gây trùng. Cần thiết kế chính sách recovery theo topology triển khai và đảm bảo consumer idempotent.

### 7.2. Stale publication và trạng thái lỗi

Từ Spring Modulith 2.0, Staleness Monitor có thể đánh dấu publication quá lâu ở các trạng thái `PUBLISHED`, `PROCESSING`, `RESUBMITTED` thành `FAILED` theo ngưỡng cấu hình. Các ngưỡng stale mặc định không tự được bật nếu thời lượng bằng zero. Chỉ dùng monitor khi đã định nghĩa được thời gian xử lý hợp lý và cách xử lý false positive.

Ví dụ nên kiểm tra trong production: số publication `FAILED`, tuổi của publication cũ nhất, số lần retry, số publication hoàn tất theo thời gian và thời gian hoàn thành theo listener. Những chỉ số này có ý nghĩa hơn một con số “incomplete” đơn lẻ.

## 8. Vì sao cần idempotency?

Hãy xét listener gửi email:

1. Listener nhận `OrderPlaced` và gọi nhà cung cấp email; email đã được gửi.
2. Tiến trình dừng **trước khi** registry kịp đánh dấu publication completed.
3. Recovery gửi lại publication. Listener gọi email lần thứ hai.

Registry ghi nhận publication và hỗ trợ xử lý lại, nhưng **không thể tự bảo đảm hiệu ứng ngoài hệ thống diễn ra đúng một lần**. Khi side effect không nằm trong cùng transaction với bản ghi completed, có thể có một “khoảng trống xác nhận”.

Các cách giảm rủi ro:

- Event có `eventId` duy nhất ổn định qua các lần resubmit; không sinh event ID mới trong listener.
- Listener lưu một bảng `processed_event` hoặc khóa nghiệp vụ duy nhất trong cùng transaction với cập nhật database của mình.
- Với API bên ngoài, sử dụng idempotency key nếu đối tác hỗ trợ.
- Chỉ đánh dấu xử lý thành công sau khi side effect và xác nhận tương ứng được thực hiện theo thiết kế.
- Cấu hình retry có giới hạn/giám sát; lỗi không thể tự phục hồi phải được đưa vào quy trình vận hành.

Ví dụ ý tưởng cho nghiệp vụ lưu dữ liệu:

~~~java
@Transactional
public void reserveOnce(OrderPlaced event) {
    if (processedEventIds.existsById(event.eventId())) {
        return;
    }

    // Cập nhật tồn kho và lưu dấu xử lý trong cùng transaction.
    reservations.reserve(event.orderId());
    processedEventIds.save(new ProcessedEvent(event.eventId()));
}
~~~

Đoạn này là **mã minh họa**: để dùng, payload `OrderPlaced` phải bổ sung `eventId`, và cần implement repository/entity tương ứng. Chỉ kiểm tra `existsById` trước `save` chưa chống race hoàn toàn nếu nhiều consumer xử lý đồng thời; cần unique constraint cùng cách xử lý lỗi giao dịch phù hợp.

## 9. Kiểm thử nguồn phát: @ApplicationModuleTest + PublishedEvents

Đặt test trong package `com.example.shop.orders` để kiểm tra use case của module phát:

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
class OrderEventTests {

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

Test này chứng minh use case `orders.place(id)` đã phát đúng loại event và payload, **không chứng minh** registry đã lưu publication cho `inventory`, bởi vì module test ở phạm vi mặc định có thể không bootstrap các listener ở module khác.

`@ApplicationModuleTest` phù hợp để kiểm tra riêng hành vi module. Muốn kiểm tra việc registry tương tác với **tất cả listener đích, database và transaction**, thường cần một integration test có đúng các listener đó trong application context.

## 10. Integration test: kiểm chứng registry thực sự theo dõi publication

Để kiểm chứng persistence và lifecycle, hãy chuẩn bị:

- Registry starter và database test có transaction semantics phù hợp với production.
- Các listener đích được nạp vào context test.
- Fixture độc lập giữa test; không để dữ liệu publication cũ gây trùng giả.
- Test **không** gắn `@Transactional` bao ngoài rồi tự rollback nếu muốn xác nhận publication đã commit.

### 10.1. Kiểm thử một publication lỗi vẫn được lưu

Ví dụ dưới đây cố ý đăng ký transactional listener **luôn ném exception** cho một event chỉ dùng trong test. Nhờ vậy test kiểm tra chính khả năng registry ghi nhận một lần giao không hoàn tất. Đoạn mã giả định có database và cấu hình registry starter; nếu mã nguồn đã có `ShopApplication`, `@SpringBootTest` sẽ phát hiện lớp cấu hình ứng dụng.

~~~java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.modulith.events.core.EventPublicationRegistry;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.support.TransactionTemplate;

import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@Import(PublicationRegistryIntegrationTests.TestListeners.class)
class PublicationRegistryIntegrationTests {

    @Autowired ApplicationEventPublisher publisher;
    @Autowired PlatformTransactionManager transactionManager;
    @Autowired EventPublicationRegistry registry;

    record ProbeEvent(UUID id) {}

    @Test
    void committedEventCanLeaveAnIncompletePublication() {
        UUID id = UUID.randomUUID();
        var transaction = new TransactionTemplate(transactionManager);

        try {
            transaction.executeWithoutResult(
                    status -> publisher.publishEvent(new ProbeEvent(id)));
        } catch (IllegalStateException expected) {
            // Listener cố tình lỗi ở pha AFTER_COMMIT; transaction
            // nghiệp vụ đã commit trước khi callback được gọi.
        }

        assertThat(registry.findIncompletePublications())
                .anyMatch(publication ->
                        publication.getEvent() instanceof ProbeEvent event
                                && event.id().equals(id));
    }

    @Test
    void rollbackDoesNotPersistPublication() {
        UUID id = UUID.randomUUID();
        var transaction = new TransactionTemplate(transactionManager);

        transaction.executeWithoutResult(status -> {
            publisher.publishEvent(new ProbeEvent(id));
            status.setRollbackOnly();
        });

        assertThat(registry.findIncompletePublications())
                .noneMatch(publication ->
                        publication.getEvent() instanceof ProbeEvent event
                                && event.id().equals(id));
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class TestListeners {

        @Bean
        FailingListener failingListener() {
            return new FailingListener();
        }
    }

    static class FailingListener {

        @TransactionalEventListener
        public void on(ProbeEvent event) {
            throw new IllegalStateException("Simulated downstream failure");
        }
    }
}
~~~

Đây là mẫu integration test tập trung vào cơ chế, cần điều chỉnh theo phiên bản Spring Modulith, cách serial hóa event và hành vi propagation exception của transaction manager trong dự án. Không nên thêm `@Transactional` vào class test vì có thể khiến transaction bị Spring Test rollback. Listener cố tình ném exception có thể được ghi log hoặc ngoại lệ có thể truyền ra caller tùy cấu hình; việc test quan sát publication còn tồn mới là assertion chính.

Nếu dùng `@ApplicationModuleListener` bất đồng bộ, hãy **chờ trạng thái bằng điều kiện** trước khi assert, vì callback có thể chưa kịp thực hiện. Với timeout, cần phân biệt “listener chưa bắt đầu” và “listener đã lỗi” để tránh test flaky.

### 10.2. Kiểm thử hoàn tất và side effect

Một test thành công nên kiểm tra **cả hai điều**:

1. Side effect của listener đã tồn tại ở database của module nhận.
2. Publication tương ứng không còn nằm trong tập chưa hoàn tất, hoặc có trạng thái completed theo completion mode đã chọn.

Ví dụ phần assertion cho listener bất đồng bộ, giả định đã phát event thành công và có `reservations`, `registry`, `orderId`:

~~~java
await().atMost(Duration.ofSeconds(10))
        .untilAsserted(() ->
                assertThat(reservations.existsByOrderId(orderId)).isTrue());

await().atMost(Duration.ofSeconds(10))
        .untilAsserted(() ->
                assertThat(registry.findIncompletePublications())
                        .noneMatch(publication ->
                                publication.getEvent() instanceof OrderPlaced e
                                        && e.orderId().equals(orderId)));
~~~

Đây là một **đoạn assertion**, cần cấu hình Awaitility và các biến/bean tương ứng. Assertion thứ hai một mình **không chứng minh** registry đã từng có publication: với bộ test đầy đủ nên kiểm tra cấu hình persistence và thời điểm publication được tạo, ví dụ giữ listener test ở trạng thái chờ để chụp snapshot incomplete trước khi cho xử lý tiếp.

### 10.3. Kiểm thử retry và idempotency

Một kịch bản kiểm thử có giá trị:

1. Listener lần đầu được cấu hình lỗi có kiểm soát sau khi nhận event.
2. Assert registry còn publication chưa hoàn tất (hoặc `FAILED` ở phiên bản hỗ trợ).
3. Bật lại khả năng xử lý của listener, gọi API resubmit đúng publication/nhóm publication.
4. Chờ publication completed và assert dữ liệu downstream chính xác.
5. Phát lại event theo cơ chế retry một lần nữa để kiểm tra side effect không bị nhân đôi.

Hãy giữ sự kiện đủ lâu để registry vẫn deserialize được nó; nếu schema payload thay đổi, test cần bao phủ khả năng đọc lại sau deploy. Phép kiểm thử này có ý nghĩa hơn chỉ assert rằng `resubmit...` không ném exception.

## 11. Giám sát publication trong vận hành

Registry là nguồn dữ liệu hữu ích để tạo metrics/alert, nhưng cần định nghĩa rõ các phép đo:

| Metric/góc nhìn | Ý nghĩa | Cảnh báo cần cân nhắc |
| --- | --- | --- |
| Số publication chưa hoàn tất theo listener | Backlog của từng consumer. | Tăng liên tục ở một listener dù nguồn vẫn phát đều. |
| Tuổi publication chưa hoàn tất lâu nhất | Khả năng có publication bị kẹt. | Vượt ngưỡng theo SLA nghiệp vụ. |
| Tỷ lệ thành công/thất bại | Độ ổn định listener downstream. | Lỗi tăng sau deploy. |
| Số lần resubmit / completion attempts | Áp lực retry và lỗi lặp. | Nhiều lần thử nhưng không tiến triển. |
| Thời gian từ publish tới complete | Độ trễ xử lý event. | Chậm kéo dài gây sai lệch trạng thái giữa module. |
| Số bản ghi completed chưa purge | Dung lượng lưu trữ. | Bảng registry tăng vô hạn với mode `UPDATE`. |

Khi cấu hình `completion-mode=DELETE`, cần đo số liệu thành công qua hệ thống metrics/log thích hợp vì bản ghi completed đã bị xóa. Tránh log toàn bộ payload chứa thông tin cá nhân, token hoặc dữ liệu nhạy cảm.

### 11.1. Tình huống đặc biệt khi nhiều instance

Một instance có thể đang xử lý publication trong khi instance khác cũng nhìn thấy bản ghi chưa hoàn tất. Không nên tự động resubmit mọi incomplete ngay ở mỗi instance hay bật republish on restart mà chưa xem xét concurrency. Từ các phiên bản có lifecycle chi tiết, trạng thái `PROCESSING` và staleness policy giúp phân biệt công việc đang chạy với công việc có khả năng bị kẹt, nhưng xử lý lặp vẫn phải được dự phòng bằng idempotency.

### 11.2. Registry và broker/outbox

Registry theo dõi các publication tới transactional listener trong ứng dụng. Khi externalize event sang Kafka/AMQP/JMS bằng cơ chế Spring Modulith, việc gửi ra broker có thể được triển khai qua transactional listener và được registry hỗ trợ theo dõi. Tuy nhiên, **registry không phải broker**, không cấp ordering toàn cục, và không bảo đảm một consumer bên ngoài đã xử lý thông điệp chỉ vì một lời gọi publish lên broker thành công.

Nếu yêu cầu đòi hỏi các bảo đảm outbox nâng cao, cần đánh giá cơ chế outbox cụ thể và kiểm thử theo kiến trúc triển khai; không nên coi mọi mẫu event publication là tương đương nhau.

## 12. Quality gate CI: kiểm tra cả kiến trúc lẫn publication

Các kiểm tra trong CI của học phần `SPRING_MODULITH_VERIFICATION_TESTING` nên phối hợp:

| Nhóm test | Mục tiêu | Dấu hiệu thất bại |
| --- | --- | --- |
| **Architecture test** | `ApplicationModules.verify()` ngăn truy cập nội bộ và phụ thuộc vòng. | `inventory` import repository của `orders`. |
| **Module publication test** | `@ApplicationModuleTest` + `PublishedEvents` xác nhận event/payload do nguồn phát. | Service quên phát `OrderPlaced`. |
| **Transaction integration test** | Registry ghi publication khi commit và không giữ bản ghi từ transaction rollback. | Rollback vẫn có publication cần xử lý. |
| **Listener completion test** | Listener thành công tạo side effect và registry ghi nhận hoàn tất. | Listener xử lý nhưng publication tồn đọng, hoặc ngược lại. |
| **Failure/recovery test** | Lỗi downstream còn publication để retry; resubmit và idempotency đúng. | Mất event sau lỗi hoặc tác động lặp. |
| **Serialization test** | Payload có thể được lưu, đọc lại và tái giao. | Deserialization thất bại sau thay đổi payload. |

CI cần chạy các task test chuẩn của dự án và thất bại khi bất kỳ phép kiểm tra bắt buộc nào thất bại. Với test có database, dùng schema/transaction tương ứng production; với async listener, chờ điều kiện có timeout và cô lập fixture. Đừng dựa vào `Thread.sleep` cố định hoặc dùng một bài `verify()` để suy ra registry hoạt động đúng.

**Điều chưa được `ApplicationModules.verify()` chứng minh:** publication đã được lưu, listener có thể xử lý sau commit, completion update đã commit, sự kiện có thể deserialize sau restart. Đây là những vấn đề integration/runtime và phải được kiểm thử riêng.

## 13. Bài tập tình huống

Module `billing` phát `InvoicePaid` trong transaction. Hai listener độc lập:

- `reporting`: cập nhật báo cáo thành công.
- `email`: gửi thông báo, lần đầu lỗi timeout.

Ứng dụng sử dụng registry với database và listener `@ApplicationModuleListener`. Hãy trả lời:

1. Vì sao một `InvoicePaid` có thể tạo hai publication?
2. Khi transaction nguồn rollback, những publication vừa ghi trong transaction đó tồn tại bền vững không?
3. Khi `reporting` hoàn tất nhưng `email` thất bại, registry nên thể hiện sự khác biệt ra sao?
4. Vì sao một publication còn incomplete chưa chắc đã `FAILED`?
5. Nếu email thực sự được gửi nhưng tiến trình dừng trước khi ghi completed, làm sao giảm nguy cơ gửi trùng khi retry?
6. Test `PublishedEvents` ở `billing` có đủ chứng minh `email` sẽ retry được sau restart không?

**Đáp án gợi ý:**

1. Registry theo dõi **event đến từng listener đích**, vì vậy một event có nhiều transactional listener sẽ có nhiều publication.
2. Không, nếu registry lưu cùng transaction nguồn, rollback sẽ rollback luôn bản ghi publication.
3. Publication của `reporting` hoàn tất; publication của `email` chưa hoàn tất hoặc được ghi nhận thất bại tùy phiên bản/lifecycle.
4. Nó có thể mới được tạo hoặc đang xử lý bình thường. Cần xét tuổi và trạng thái, không retry mù.
5. Dùng event ID ổn định, idempotency key, lưu dấu xử lý hoặc cơ chế chống gửi lặp thích hợp ở phía email provider/consumer.
6. Không. `PublishedEvents` chỉ chứng minh phát event; cần integration test có registry bền vững, serialization, listener, recovery và dữ liệu thật.

## 14. Checklist trước khi đưa vào production

- [ ] Event được phát tại đúng module nguồn và trong transaction nghiệp vụ khi cần bảo đảm publication gắn với commit.
- [ ] Payload là hợp đồng công khai bất biến, serialize/deserialize được và không chứa entity/proxy nội bộ.
- [ ] Có registry starter, persistence, schema và transaction manager được cấu hình đúng.
- [ ] Listener cần theo dõi thuộc phạm vi trigger annotation đang dùng.
- [ ] Có kiến trúc `@NamedInterface`/`allowedDependencies` và test `ApplicationModules.verify()`.
- [ ] Có test `PublishedEvents` tại module phát và integration test registry tại context có listener.
- [ ] Test bao phủ commit, rollback, thất bại, completion, resubmit và idempotency.
- [ ] Có ngưỡng cảnh báo backlog/tuổi publication theo target, không coi mọi incomplete là failed.
- [ ] Chọn completion mode và chính sách purge/archive phù hợp dung lượng/audit.
- [ ] Nếu nhiều instance, quy trình recovery xử lý được concurrency và phát trùng.
- [ ] Nếu cần broker/outbox, đã phân biệt xác nhận gửi khỏi xác nhận consumer cuối.
- [ ] Chạy các kiểm tra cần thiết trong quality gate CI để ngăn hồi quy.

**Ghi nhớ:** `EventPublicationRegistry` theo dõi **mỗi lần giao sự kiện tới một transactional listener**, giúp biết publication nào đã hoàn tất và publication nào còn cần xử lý. Nó bổ sung độ tin cậy cho cơ chế event của Spring Modulith, nhưng kết quả cuối cùng vẫn phải được xác nhận bằng **transaction, dữ liệu nghiệp vụ, idempotency và integration test**.

### Tài liệu đối chiếu

- [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html): cơ chế registry, lifecycle, persistence, recovery và completion mode.
- [EventPublicationRegistry API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/events/core/EventPublicationRegistry.html): các phương thức tra cứu và quản lý publication.
- [EventPublication API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/events/EventPublication.html): thuộc tính publication và trạng thái ở các phiên bản hỗ trợ.

> Ghi chú tương thích: Phần lifecycle có `Status`/`FailedEventPublications` dựa trên Spring Modulith 2.0+; `ABANDONED` dựa trên 2.2+. Đối chiếu phiên bản ứng dụng trước khi áp dụng API hoặc property mới.
