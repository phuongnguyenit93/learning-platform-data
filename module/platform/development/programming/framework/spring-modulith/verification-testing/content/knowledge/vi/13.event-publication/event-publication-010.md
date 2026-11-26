# Retry event publication và khả năng quan sát

## 1. Vì sao cần retry và quan sát event publication?

Trong một ứng dụng Spring Modulith, module `orders` có thể hoàn tất transaction đặt hàng và phát `OrderPlaced`. Các module `inventory`, `billing` hoặc `notifications` xử lý sự kiện này sau commit. Khi listener gặp lỗi tạm thời, ví dụ database hết kết nối hoặc một dịch vụ bên ngoài trả HTTP 503, dữ liệu đơn hàng **vẫn đã commit**, nhưng công việc ở module nhận có thể chưa hoàn tất.

Nếu chỉ ghi log exception mà không theo dõi lần giao event chưa hoàn tất, hệ thống sẽ có trạng thái nghiệp vụ lệch nhau:

- Module `orders` đã xác nhận đơn hàng.
- Module `inventory` chưa giữ tồn kho.
- Module `notifications` có thể đã gửi email hoặc chưa gửi.
- Người vận hành không biết target nào đang chờ, target nào đã lỗi và có nên thử lại hay không.

**Retry event publication** là việc cố gắng **giao/xử lý lại một publication chưa được xác nhận hoàn tất**, thường theo **từng transactional listener target**. Nó **không có nghĩa gọi lại `OrderService.place(...)`** để sinh một đơn hàng hoặc một event hoàn toàn mới.

**Khả năng quan sát (observability)** là khả năng trả lời bằng bằng chứng: publication nào được tạo, giao cho listener nào, khi nào bắt đầu, đã hoàn tất chưa, lỗi ở đâu, đã thử lại mấy lần và tác động nghiệp vụ cuối cùng là gì.

Chủ đề thuộc chương **Event publication** của học phần **SPRING_MODULITH_VERIFICATION_TESTING**. Mục tiêu là kết hợp kiểm chứng ranh giới kiến trúc bằng `ApplicationModules`, kiểm thử module bằng `@ApplicationModuleTest`, kiểm thử event/database và đặt quality gate trong CI để ngăn hồi quy.

### Sau bài học, bạn có thể

1. Giải thích vì sao `publishEvent`, publication được lưu và listener completed là ba bước khác nhau.
2. Phân loại publication đang chờ, đang xử lý, thất bại, đã resubmit và hoàn tất theo khả năng của phiên bản Spring Modulith.
3. Thiết kế chính sách retry an toàn theo tuổi publication, target, loại lỗi, số lần thử và thời gian chờ.
4. Dùng các API quan sát và resubmission của Spring Modulith với lưu trữ bền vững.
5. Thiết kế **idempotent consumer** để retry không nhân đôi dữ liệu nghiệp vụ.
6. Xây dựng log, metric, trace và cảnh báo theo từng target thay vì chỉ đếm tổng số event.
7. Kiểm thử đường lỗi → incomplete → retry → completed, song song với kiến trúc module và tích hợp CI.

## 2. Cần phân biệt ba giai đoạn của một event

`ApplicationEventPublisher.publishEvent(event)` đưa sự kiện vào cơ chế phân phối event của Spring. Với transactional listener, thời điểm callback được gọi phụ thuộc pha transaction; mặc định `@TransactionalEventListener` dùng `AFTER_COMMIT`.

| Giai đoạn | Điều xảy ra | Bằng chứng kiểm chứng |
| --- | --- | --- |
| **Publish** | Module nguồn gọi `publishEvent` với payload. | `PublishedEvents` trong `@ApplicationModuleTest`. |
| **Register publication** | Registry ghi lần giao event tới từng transactional listener, trong transaction nguồn nếu cấu hình đúng. | Kho publication và API `EventPublicationRegistry`. |
| **Process + complete** | Listener đích xử lý thành công, registry ghi nhận hoàn tất. | Side effect, completion status, completion time. |

Một event nghiệp vụ có thể có nhiều publication:

~~~text
OrderPlaced(eventId = E-101, orderId = O-42)
|
+-- Publication P-1 --> inventory.ReservationListener    COMPLETED
|
+-- Publication P-2 --> notifications.EmailListener     FAILED
|
+-- Publication P-3 --> analytics.OrderListener         PROCESSING
~~~

Ở đây **một lời gọi publish** không đồng nghĩa ba lời gọi publish; có ba **listener target**, nên có ba publication. Việc target tồn kho completed không làm publication gửi email hoặc phân tích dữ liệu tự completed.

### 2.1. Transaction nguồn và transaction listener

~~~mermaid
sequenceDiagram
    participant API as Client
    participant Orders as orders.OrderService
    participant DB as Database
    participant Registry as Publication Registry
    participant Stock as inventory.Listener
    participant Mail as notifications.Listener

    API->>Orders: place(orderId)
    Orders->>DB: Lưu order trong transaction nguồn
    Orders->>Registry: publishEvent(OrderPlaced)
    Registry->>DB: Ghi publication theo target
    Orders->>DB: COMMIT nguồn
    par Từng target xử lý sau commit
        Registry-->>Stock: Giao event
        Stock-->>Registry: Thành công → completed
    and
        Registry-->>Mail: Giao event
        Mail-->>Registry: Ném lỗi → chưa completed
    end
    Note over DB,Registry: Order đã commit dù email listener lỗi
~~~

Nếu transaction nguồn **rollback trước commit**, bản ghi publication lưu trong cùng transaction cũng rollback và `AFTER_COMMIT` listener không được kích hoạt. Nếu nguồn đã commit nhưng listener sau commit thất bại, **không thể đơn giản rollback transaction nguồn đã hoàn tất**.

Một `@EventListener` thông thường được xử lý đồng bộ trong lúc phát theo cấu hình mặc định. Nó **không mặc nhiên** được registry theo dõi như transactional listener và có thể tạo side effect trước khi transaction nguồn hoàn tất. `@ApplicationModuleListener` của Spring Modulith kết hợp transactional event listener, xử lý bất đồng bộ và transaction mới; vì vậy test phải tính đến thời điểm hoàn thành không đồng bộ.

## 3. Event Publication Registry và các đối tượng cần theo dõi

Khi có persistence starter và transaction phù hợp, Event Publication Registry theo dõi những lần giao sự kiện tới transactional listener. Những khái niệm quan trọng:

| Thành phần | Vai trò | Lưu ý |
| --- | --- | --- |
| `EventPublicationRegistry` | Tra cứu và cập nhật publication ở tầng registry. | Mã nghiệp vụ thông thường không tự đánh dấu completed. |
| `TargetEventPublication` | Bản ghi publication có event, UUID publication, ngày phát và target identifier. | Mỗi target có bản ghi riêng. |
| `PublicationTargetIdentifier` | Giá trị định danh listener đích. | Không mặc nhiên là tên module. |
| `IncompleteEventPublications` | API cho việc resubmit các publication chưa hoàn tất. | Phải chọn tuổi/phạm vi phù hợp, tránh retry mù. |
| `CompletedEventPublications` | Truy vấn/dọn publication đã completed theo cấu hình. | Có thể không giữ bản ghi khi completion mode là `DELETE`. |
| `FailedEventPublications` *(phiên bản hỗ trợ)* | Làm việc với publication ở trạng thái `FAILED`. | Đối chiếu API của phiên bản đang dùng. |

### 3.1. Incomplete không nhất thiết là lỗi

`findIncompletePublications()` và `findIncompletePublicationsOlderThan(Duration)` giúp tìm publication chưa hoàn tất. Tuy nhiên một bản ghi chưa completed có thể:

- Vừa được tạo và **chưa đến lượt xử lý**.
- Đang **PROCESSING** trên một thread hoặc instance khác.
- Đã lỗi nhưng chưa được đánh dấu rõ trạng thái trong phiên bản đang sử dụng.
- Đang chờ một lần **RESUBMIT** hợp lệ.
- Bị kẹt vì listener đã đổi tên, không còn được đăng ký hoặc deserialize thất bại.

Không được suy ra “cứ incomplete là gọi lại ngay”. Cần một **chính sách đủ điều kiện retry**, gồm tuổi tối thiểu, trạng thái, số lần thử, thông tin lỗi và khả năng có xử lý đồng thời.

### 3.2. Trạng thái lifecycle khi phiên bản hỗ trợ

Các bản Spring Modulith có lifecycle chi tiết cung cấp trạng thái như:

| Trạng thái | Ý nghĩa vận hành | Xử lý thường phù hợp |
| --- | --- | --- |
| `PUBLISHED` | Đã có publication, đang chờ thực thi. | Theo dõi tuổi hàng chờ, không retry ngay. |
| `PROCESSING` | Listener đã bắt đầu xử lý. | Theo dõi timeout/staleness thay vì giao lại đồng thời. |
| `COMPLETED` | Listener được ghi nhận hoàn tất thành công. | Đo độ trễ, áp dụng chính sách lưu trữ. |
| `FAILED` | Listener xử lý thất bại hoặc publication được xác định stale theo cơ chế hỗ trợ. | Phân loại lỗi rồi chọn retry/bỏ qua/can thiệp. |
| `RESUBMITTED` | Publication đã được gửi lại. | Theo dõi số lần thử và tránh retry chồng. |
| `ABANDONED` *(phiên bản hỗ trợ)* | Hệ thống quyết định ngừng resubmit. | Báo động/can thiệp; **không coi là xử lý thành công**. |

Ở các bản Spring Modulith cũ hơn, cách diễn đạt và API có thể chủ yếu xoay quanh **incomplete/completed**; không copy nguyên mã `getStatus()` từ phiên bản mới vào bản cũ. Cần đối chiếu dependency và tài liệu API tương ứng trước khi triển khai.

### 3.3. Completion mode ảnh hưởng observability

Property `spring.modulith.events.completion-mode` quy định cách lưu publication sau khi listener completed:

| Mode | Khi completed | Ảnh hưởng đến metric/test |
| --- | --- | --- |
| `UPDATE` (mặc định) | Giữ bản ghi, cập nhật thời điểm hoàn tất. | Có thể phân tích completed còn lưu; cần purge lịch sử. |
| `DELETE` | Xóa publication đã completed. | “Không thấy bản ghi” **không tự chứng minh** đã xử lý thành công. |
| `ARCHIVE` | Chuyển/lưu bản ghi đã hoàn tất vào vùng archive. | Truy vấn lịch sử đúng API/kho archive, quản lý dung lượng. |

Ví dụ:

~~~properties
# Ví dụ cần giữ dấu hoàn tất để phân tích.
spring.modulith.events.completion-mode=UPDATE
~~~

Nếu chuyển sang `DELETE`, dashboard cần ghi metric **tại lúc hoàn tất** hoặc sử dụng nguồn dữ liệu khác; không thể dựa vào bảng chính để đếm mọi publication từng hoàn tất.

## 4. Chuẩn bị persistence và payload cho khả năng retry

Registry chỉ có thể hỗ trợ **khôi phục sau restart** khi publication được lưu bền vững theo cấu hình phù hợp. Ứng dụng cần:

1. Một Spring Modulith event registry starter tương ứng với persistence, ví dụ JDBC/JPA.
2. Database, transaction manager và schema publication.
3. Event payload có thể serialize và deserialize lại sau khi tiến trình khởi động lại.
4. Transaction nguồn chứa thao tác nghiệp vụ và lời gọi `publishEvent`.
5. Transactional listener thuộc phạm vi theo dõi của registry.

Ví dụ Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.modulith:spring-modulith-starter-jdbc'
    testImplementation 'org.springframework.modulith:spring-modulith-starter-test'
}
~~~

Đoạn ví dụ giả định dự án đã quản lý phiên bản Spring Modulith bằng BOM/Spring Boot, có JDBC datasource, driver, transaction manager và schema tương ứng. **Chỉ thêm dependency không có nghĩa persistence đã chạy đúng**.

### 4.1. Event đủ ổn định để xử lý lại

File `orders/events/OrderPlaced.java`:

~~~java
package com.example.shop.orders.events;

import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

public record OrderPlaced(
        UUID eventId,
        UUID orderId,
        Instant occurredAt
) {
    public OrderPlaced {
        Objects.requireNonNull(eventId);
        Objects.requireNonNull(orderId);
        Objects.requireNonNull(occurredAt);
    }
}
~~~

`eventId` là ID nghiệp vụ ổn định cho **lần phát sự kiện**, không phải ID của bản ghi publication. Một `OrderPlaced` được giao lại cho cùng listener vẫn giữ `eventId`. Không sinh `eventId` mới **bên trong listener** hoặc mỗi lần retry, vì như vậy consumer mất khả năng nhận diện sự kiện đã xử lý.

Không chuyển JPA entity, Hibernate proxy, repository hoặc Spring service vào payload. Nếu thay đổi cấu trúc record giữa hai bản deploy, cần kiểm tra khả năng **đọc lại các publication còn tồn** bằng serializer đang cấu hình.

### 4.2. Ranh giới module không phụ thuộc cơ chế retry

Với `ShopApplication` ở `com.example.shop`, hai module `orders` và `inventory`:

~~~text
com.example.shop
├── ShopApplication.java
├── orders
│   ├── OrderService.java
│   └── events
│       ├── OrderPlaced.java
│       └── package-info.java
└── inventory
    ├── StockListener.java
    └── package-info.java
~~~

File `orders/events/package-info.java`:

~~~java
@org.springframework.modulith.NamedInterface("events")
package com.example.shop.orders.events;
~~~

File `inventory/package-info.java`:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "orders :: events"
)
package com.example.shop.inventory;
~~~

Sự kiện được phát từ `orders`:

~~~java
@Service
class OrderService {

    private final OrderRepository orders;
    private final ApplicationEventPublisher publisher;

    OrderService(OrderRepository orders,
                 ApplicationEventPublisher publisher) {
        this.orders = orders;
        this.publisher = publisher;
    }

    @Transactional
    public void place(UUID orderId) {
        orders.save(new OrderEntity(orderId));
        publisher.publishEvent(
                new OrderPlaced(UUID.randomUUID(), orderId, Instant.now()));
    }
}
~~~

Đây là đoạn rút gọn nằm trong module `orders`: `OrderEntity`, `OrderRepository` và các import cần được triển khai theo dự án. Event chỉ dùng API công khai, còn các chi tiết persistence nằm bên trong module nguồn.

Listener ở module `inventory`:

~~~java
@Component
class StockListener {

    private final StockReservationService reservations;

    StockListener(StockReservationService reservations) {
        this.reservations = reservations;
    }

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        reservations.reserveOnce(event);
    }
}
~~~

`StockReservationService` là bean nội bộ có nhiệm vụ cập nhật tồn kho một cách idempotent. Annotation `@ApplicationModuleListener` kết hợp xử lý theo transaction, bất đồng bộ và transaction mới. Khi listener ném exception, publication chưa được coi là hoàn tất; nếu được resubmit, cùng event có thể đi qua listener lần nữa.

**Không gọi lại `OrderService.place(orderId)` để retry `StockListener`**: làm vậy có nguy cơ tạo một sự kiện mới hoặc thao tác đặt hàng lần hai. Retry đúng tầng là xử lý lại publication hiện có tới target phù hợp.

## 5. Xây dựng chính sách retry thay vì retry mù

Một chính sách retry an toàn phải trả lời được năm câu hỏi:

1. **Retry cái gì?** Publication theo `eventId` và **target**, không phải toàn bộ use case nguồn.
2. **Retry lúc nào?** Sau một khoảng chờ tối thiểu; cân nhắc trạng thái `PROCESSING` và lỗi stale.
3. **Retry bao nhiêu lần?** Có giới hạn hoặc cơ chế can thiệp khi lỗi kéo dài.
4. **Retry bằng cách nào?** Dùng API resubmission phù hợp với phiên bản Spring Modulith; theo dõi kết quả.
5. **Nếu retry gây trùng side effect thì sao?** Consumer phải idempotent hoặc có idempotency key ở provider ngoài.

### 5.1. Phân loại lỗi

| Lỗi | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| **Tạm thời** | Database connection reset, HTTP 503, timeout. | Retry có backoff và giới hạn, quan sát tỷ lệ phục hồi. |
| **Quá tải** | Downstream rate limit/HTTP 429. | Tôn trọng thời gian chờ phù hợp, giới hạn concurrency. |
| **Payload không hợp lệ** | Bản ghi cũ không deserialize được, thiếu field bắt buộc. | Sửa serializer/migration; không retry vô hạn cùng payload hỏng. |
| **Sai quy tắc nghiệp vụ** | SKU không tồn tại, trạng thái không cho giữ hàng. | Can thiệp hoặc quy trình bù trừ; cần phân loại có thể phục hồi không. |
| **Không rõ side effect đã xảy ra** | Timeout sau khi gọi email provider hoặc thanh toán. | Kiểm tra idempotency key/trạng thái đối tác trước khi gọi lại. |
| **Target không còn tồn tại** | Listener bị đổi tên hoặc không được nạp sau deploy. | Kiểm tra target identifier/phiên bản và chiến lược migration. |

Một quy tắc minh họa (không phải mặc định của Spring Modulith) cho lỗi tạm thời:

~~~text
Lần thử 1: chờ 1 phút
Lần thử 2: chờ 2 phút
Lần thử 3: chờ 4 phút
Lần thử 4: chờ 8 phút
Các lần sau: giới hạn tối đa 30 phút và thêm jitter
Vượt ngưỡng/không phục hồi: cảnh báo và chuyển sang xử lý vận hành
~~~

Đây là **chính sách ứng dụng tự thiết kế**, không hàm ý `IncompleteEventPublications` tự cung cấp exponential backoff. Với phiên bản hỗ trợ trạng thái và số lần thử, có thể dùng các trường lifecycle để quyết định khi nào đủ điều kiện resubmit.

### 5.2. Truy vấn publication cũ trước khi hành động

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

    private PendingPublication toView(TargetEventPublication p) {
        return new PendingPublication(
                p.getIdentifier(),
                p.getTargetIdentifier().getValue(),
                p.getEvent().getClass().getSimpleName(),
                p.getPublicationDate());
    }

    record PendingPublication(
            UUID publicationId,
            String target,
            String eventType,
            Instant publishedAt) {}
}
~~~

Đây là **API chỉ đọc**, hữu ích để chẩn đoán và tạo dashboard. Không trả toàn bộ `p.getEvent()` ra API quản trị công khai, vì payload có thể mang dữ liệu nhạy cảm. Khi cần phân nhóm theo module, hãy ánh xạ **target listener** đến module tương ứng bằng tri thức kiến trúc thay vì tùy tiện đoán chuỗi target là tên module.

### 5.3. Resubmit bằng API của Spring Modulith

Ví dụ một service thao tác recovery **có chủ đích**:

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

    public void resubmitOldPublications() {
        incomplete.resubmitIncompletePublicationsOlderThan(
                Duration.ofMinutes(15));
    }
}
~~~

Lời gọi này minh họa API cho publication chưa hoàn tất **quá một ngưỡng tuổi**. Không có nghĩa đây là bộ retry hoàn chỉnh:

- Cần xem bản Spring Modulith đang dùng và API resubmission/selection thực tế.
- Một publication “cũ” có thể vẫn đang được xử lý trong một job dài; phải xác định chính sách stale.
- Trong hệ thống nhiều instance, không để nhiều scheduler resubmit cùng publication không kiểm soát.
- Cần giới hạn batch, concurrency, số lần thử và theo dõi lỗi từ downstream.
- Với các phiên bản có `FailedEventPublications` và cấu hình resubmission, có thể chọn riêng publication `FAILED` và dùng các tùy chọn lọc hỗ trợ.

**Không gọi phương thức này trực tiếp sau mỗi request đặt hàng.** Recovery nên thuộc công việc vận hành có giám sát, có thể chạy định kỳ hoặc qua thao tác quản trị được phân quyền.

### 5.4. Phát lại khi restart

Spring Modulith có tùy chọn:

~~~properties
spring.modulith.events.republish-outstanding-events-on-restart=true
~~~

Nó có thể được dùng để xử lý lại các publication còn tồn khi ứng dụng khởi động. Không bật một cách máy móc trong triển khai nhiều replica: instance vừa restart có thể nhìn thấy publication vẫn đang được instance khác xử lý, khiến side effect trùng. Cần kiểm tra chính sách recovery, vòng đời trạng thái và thiết kế idempotency trước khi bật.

**Restart không phải phương án duy nhất:** một publication lỗi trong hệ thống chạy liên tục vẫn cần được phát hiện, cảnh báo và xử lý mà không đòi hỏi restart ứng dụng.

## 6. Idempotency là điều kiện bắt buộc để retry an toàn

Một tình huống nguy hiểm:

1. Listener gửi email thành công.
2. Tiến trình dừng trước khi registry kịp ghi nhận publication completed.
3. Registry vẫn thấy publication chưa hoàn tất.
4. Recovery giao lại event; listener gửi thêm email.

Do đó, registry hỗ trợ **at-least-once style recovery** cho những publication còn tồn nhưng **không tự bảo đảm exactly-once side effect**. Cần thiết kế consumer lặp an toàn.

### 6.1. Sử dụng event ID ổn định

`OrderPlaced` cần có một `eventId` ổn định từ lúc được phát. Các lần retry publication không sinh `eventId` mới. Nếu mỗi lần retry dùng ID mới, cơ chế chống trùng dựa vào ID sẽ không hoạt động.

### 6.2. Ghi dữ liệu và marker trong cùng transaction

Ví dụ phần xử lý ở `inventory`:

~~~java
@Service
class StockReservationService {

    private final ProcessedEventRepository processed;
    private final StockReservationRepository reservations;

    StockReservationService(ProcessedEventRepository processed,
                            StockReservationRepository reservations) {
        this.processed = processed;
        this.reservations = reservations;
    }

    @Transactional
    public void reserveOnce(OrderPlaced event) {
        if (processed.existsById(event.eventId())) {
            return;
        }

        reservations.save(new StockReservation(event.orderId()));
        processed.save(new ProcessedEvent(event.eventId()));
    }
}
~~~

Đây là mẫu rút gọn: `ProcessedEvent` có khóa chính `eventId`, còn `StockReservation` và các repository cần được định nghĩa. Hai thao tác phải thuộc **cùng transaction** để khi một thao tác lỗi, transaction không để lại trạng thái nửa vời.

**Cạnh tranh:** kiểm tra `existsById` một mình không chống được hai transaction đồng thời đều thấy `false`. Cần unique constraint (khóa chính `eventId`), xử lý lỗi ràng buộc và đảm bảo transaction rollback đúng; có thể dùng update có điều kiện hoặc lock tùy bài toán.

Với side effect ngoài database như email, HTTP call hoặc charge, một transaction JPA **không rollback được lời gọi ngoài**. Ưu tiên idempotency key do đối tác hỗ trợ hoặc mô hình outbox/dispatcher phù hợp với mức độ bảo đảm nghiệp vụ.

### 6.3. Đừng nuốt exception của listener

~~~java
@ApplicationModuleListener
void on(OrderPlaced event) {
    try {
        reservations.reserveOnce(event);
    } catch (Exception ex) {
        log.warn("Reservation failed", ex);
        // Sai nếu trả về bình thường rồi kỳ vọng registry tự retry.
    }
}
~~~

Nếu listener bắt lỗi rồi trả về bình thường, hạ tầng có thể coi invocation thành công và đánh dấu publication completed. Hãy để lỗi cần retry được phản ánh theo chính sách; lỗi vĩnh viễn cần được phân loại và can thiệp có chủ đích, không giấu trong một khối `catch`.

## 7. Khả năng quan sát: từ một exception đến câu trả lời vận hành

Một hệ thống có observability tốt cần trả lời:

1. Event và target nào đang bị tồn đọng?
2. Tồn đọng bao lâu so với SLA nghiệp vụ?
3. Có bao nhiêu publication đang `PROCESSING`, `FAILED` hoặc `RESUBMITTED`?
4. Publication nào đã được retry, retry bao nhiêu lần và kết quả lần mới?
5. Side effect ở database hoặc dịch vụ ngoài có thành công không?
6. Có lỗi tăng bất thường sau khi deploy một phiên bản mới không?

### 7.1. Metric/SLI nên đo

| Metric hoặc SLI | Cách diễn giải | Lưu ý |
| --- | --- | --- |
| **Incomplete publication count theo target** | Backlog của từng consumer. | Tăng đột biến có thể là lỗi downstream hoặc lượng event tăng. |
| **Oldest incomplete age** | Publication tồn đọng lâu nhất. | So sánh với SLA; tránh coi mọi incomplete là lỗi. |
| **Completion latency** | Khoảng từ `publicationDate` tới `completionDate`. | Với mode `DELETE`, cần ghi metric khi hoàn tất. |
| **Retry attempts / resubmission rate** | Tần suất thử lại theo target. | Tăng cao mà completion không tăng là dấu hiệu retry storm. |
| **Failure rate theo loại lỗi** | Lỗi network/database/payload/nghiệp vụ. | Phân loại để chọn backoff hoặc xử lý vĩnh viễn. |
| **Recovery success rate** | Tỷ lệ publication failed được xử lý thành công sau retry. | Cần định nghĩa cửa sổ đo và tập mẫu rõ ràng. |
| **Abandoned count (nếu hỗ trợ)** | Publication đã ngừng tự retry. | Cần cảnh báo hoặc quy trình can thiệp. |
| **Business convergence** | Đơn hàng đã commit nhưng inventory chưa giữ hàng quá ngưỡng. | Đo hệ quả nghiệp vụ, không chỉ tình trạng hạ tầng. |

Không dùng mỗi metric “số event được publish” để kết luận độ tin cậy. Một luồng phát rất nhiều event có thể tạo backlog mà các consumer không xử lý kịp.

### 7.2. Ví dụ xuất gauge bằng Micrometer

Đây là ví dụ đơn giản cho môi trường nhỏ hoặc test. Nó **đọc toàn bộ incomplete publications** nên có thể tốn chi phí trong hệ thống lớn; production cần giới hạn kết quả hoặc truy vấn aggregate được tối ưu:

~~~java
package com.example.shop.operations;

import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.modulith.events.core.EventPublicationRegistry;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.time.Duration;
import java.time.Instant;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

@Component
class PublicationMetrics {

    private final EventPublicationRegistry registry;
    private final AtomicInteger incompleteCount;
    private final AtomicLong oldestAgeSeconds;

    PublicationMetrics(EventPublicationRegistry registry,
                       MeterRegistry meterRegistry) {
        this.registry = registry;
        this.incompleteCount = meterRegistry.gauge(
                "app.modulith.publications.incomplete",
                new AtomicInteger());
        this.oldestAgeSeconds = meterRegistry.gauge(
                "app.modulith.publications.oldest.age.seconds",
                new AtomicLong());
    }

    @Scheduled(fixedDelay = 60_000)
    void sample() {
        var incomplete = registry.findIncompletePublications();
        incompleteCount.set(incomplete.size());

        var oldest = incomplete.stream()
                .map(publication -> publication.getPublicationDate())
                .min(Instant::compareTo);

        long age = oldest.map(value ->
                Math.max(0, Duration.between(value, Instant.now())
                        .getSeconds())).orElse(0L);
        oldestAgeSeconds.set(age);
    }
}
~~~

Cần có dependency Micrometer và bật scheduling (ví dụ `@EnableScheduling`) trong ứng dụng. Gauge chỉ phản ánh **snapshot gần nhất**, không lưu lịch sử publication. Trong hệ thống lớn, không poll toàn bộ payload mỗi phút: nên truy vấn `COUNT` và `MIN(publication_date)` qua storage phù hợp hoặc dùng cơ chế instrumentation ít tốn tài nguyên hơn.

Nếu dashboard cần **theo target**, cần aggregate thêm nhóm target. Đừng đưa `eventId`, `orderId` hoặc publication ID làm **label của metric** vì cardinality sẽ tăng liên tục; chúng phù hợp với log/trace có phân quyền hơn.

### 7.3. Structured logging: đủ điều tra mà không lộ payload

Khi ghi log một publication chưa hoàn tất, tối thiểu nên có:

- `publicationId`, `eventType`, `targetIdentifier`.
- `eventId` hoặc correlation ID nếu payload cung cấp.
- `publishedAt`, tuổi publication, trạng thái, số lần thử (nếu có).
- Nhóm lỗi và mã lỗi, **không in toàn bộ event payload** hoặc thông tin cá nhân.

Ví dụ một log message:

~~~text
WARN publication_incomplete
     publicationId=...
     eventType=OrderPlaced
     target=inventory.StockListener
     ageSeconds=902
     attempts=3
     errorCategory=DATABASE_TIMEOUT
~~~

Số liệu chỉ minh họa, không phải kết quả của hệ thống đang chạy. Trước khi xuất log, phải phân quyền, làm sạch dữ liệu nhạy cảm và thống nhất retention. Tên listener/target có thể thay đổi sau deploy; nên lưu đủ thông tin version để đối chiếu.

### 7.4. Distributed tracing cho listener async

Một event có thể được xử lý trên thread khác hoặc sau khi ứng dụng restart. MDC/thread-local context của request nguồn **không tự động đảm bảo tồn tại** trong listener async hoặc đợt resubmit. Muốn trace liên kết được:

1. Đưa correlation ID/tracing context cần thiết vào metadata hoặc event contract theo chính sách bảo mật.
2. Cấu hình context propagation cho executor khi phù hợp.
3. Tạo observation/span riêng cho lần xử lý listener, ghi target, kết quả, thời gian, số lần thử.
4. Với replay sau restart, dùng span mới và liên kết theo event/correlation ID; không giả định span gốc còn đang mở.
5. Tránh đưa dữ liệu nghiệp vụ nhạy cảm thành trace attribute.

Một trace hữu ích không chỉ cho biết `orders` đã gọi publisher, mà còn thể hiện `inventory` xử lý lần 1 lỗi, publication được resubmit và lần 2 thành công.

### 7.5. Cảnh báo theo SLA, không cảnh báo theo mọi incomplete

Ví dụ chính sách vận hành (phải điều chỉnh theo ứng dụng):

| Điều kiện | Mức độ | Hành động |
| --- | --- | --- |
| Publication `inventory` chưa complete quá 5 phút | Warning | Kiểm tra queue/backlog và dependency. |
| Lỗi `DATABASE_TIMEOUT` tăng đột biến | Warning/Critical tùy ngưỡng | Kiểm tra database, rate limit retry. |
| Backlog tăng liên tục 15 phút | Critical nếu ảnh hưởng SLA | Tạm dừng retry hàng loạt, điều tra bottleneck. |
| Một event bị retry nhiều lần mà không tiến triển | Critical | Chặn retry vô hạn, can thiệp/migration. |
| Lỗi deserialize sau deploy | Critical | Kiểm tra tương thích payload, rollback/migrate có kiểm soát. |

Các ngưỡng trên là **ví dụ thiết kế**, không phải mức mặc định do Spring Modulith cung cấp.

## 8. Nhiều instance: retry có thể tạo cạnh tranh

Trong deployment có nhiều replica, instance A có thể đang xử lý `P-42`, còn instance B đọc thấy `P-42` là incomplete. Nếu B resubmit ngay, hai listener invocation có thể chạy đồng thời.

~~~mermaid
flowchart TD
    A["Publication P-42 chưa completed"] --> B{"Có invocation đang chạy?"}
    B -->|"Có/không chắc"| C["Không resubmit mù; kiểm tra stale/age"]
    B -->|"Không, đủ điều kiện"| D["Chọn publication để recovery"]
    D --> E["Giới hạn batch / concurrency"]
    E --> F["Consumer xử lý idempotent"]
    F --> G{"Thành công?"}
    G -->|"Có"| H["Registry ghi completed"]
    G -->|"Không"| I["Ghi lỗi, backoff hoặc can thiệp"]
~~~

Những nguyên tắc cần giữ:

- Không bật scheduler retry trên mọi replica mà không có chiến lược coordination/claim phù hợp.
- Đánh giá cách phiên bản Spring Modulith và storage đánh dấu `PROCESSING`, `FAILED`, stale hoặc các cơ chế lựa chọn publication.
- Dùng giới hạn số lượng publication được resubmit mỗi đợt để tránh “thundering herd”.
- Consumer vẫn phải idempotent: distributed lock không thay thế việc xử lý trùng sau crash.
- Không đổi tên listener/target identifier tùy tiện khi còn publication cũ; test deploy/upgrade có backlog.

**Retry hoàn toàn không có bảo đảm exactly once** cho email, payment gateway hoặc HTTP call. Nếu kết quả từ đối tác không rõ, cần query trạng thái hoặc idempotency key trước lần thử lại.

## 9. Kiểm thử module nguồn bằng @ApplicationModuleTest

Kiểm thử nguồn phát nên đặt ở package `com.example.shop.orders`:

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
    void publishesOrderPlacedWithStableEventIdentity(
            PublishedEvents events) {
        UUID orderId = UUID.randomUUID();

        orders.place(orderId);

        assertThat(events.ofType(OrderPlaced.class)
                .matching(OrderPlaced::orderId, orderId))
                .singleElement()
                .satisfies(event -> {
                    assertThat(event.eventId()).isNotNull();
                    assertThat(event.occurredAt()).isNotNull();
                });
    }
}
~~~

Test này bảo vệ **module nguồn có phát đúng event/payload**. Nó **không chứng minh**:

- Registry đã ghi publication cho tất cả listener ở module khác.
- Listener `inventory` có thể xử lý event thành công.
- Publication lỗi được resubmit đúng target.
- Side effect cuối cùng của listener xảy ra một lần.

Với bootstrap mặc định `STANDALONE`, module test có thể không nạp listener của module khác. Đây là lý do **integration test có registry và listener thật** cần được tách khỏi `PublishedEvents` test.

## 10. Integration test: thất bại lần đầu, resubmit rồi hoàn tất

Một test có giá trị phải kiểm tra **toàn bộ vòng đời**:

~~~text
publish trong transaction nguồn
   -> nguồn commit
   -> listener đích thử lần 1 và ném lỗi
   -> publication còn incomplete
   -> recovery resubmit đúng publication
   -> listener đích thử lần 2 thành công
   -> publication không còn incomplete
   -> side effect nghiệp vụ đúng một lần
~~~

### 10.1. Điều kiện test

- `@SpringBootTest` nạp ứng dụng, registry persistence và test listener.
- Có datasource/transaction manager và schema tương ứng.
- Event test serializable với serializer được cấu hình.
- Không dùng `@Transactional` trên test rồi mặc định rollback cuối test; cần **commit thật**.
- Dùng listener đồng bộ `@TransactionalEventListener` trong ví dụ để tách khỏi race async; nếu production dùng `@ApplicationModuleListener`, thêm test async riêng.
- Recovery thử lại trên **database test cô lập**, tránh resubmit publication tồn đọng của test khác.

### 10.2. Test harness cố tình lỗi lần đầu

~~~java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.modulith.events.IncompleteEventPublications;
import org.springframework.modulith.events.core.EventPublicationRegistry;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.support.TransactionTemplate;

import java.time.Duration;
import java.util.UUID;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

@SpringBootTest
@Import(PublicationRetryTests.TestListeners.class)
class PublicationRetryTests {

    @Autowired ApplicationEventPublisher publisher;
    @Autowired PlatformTransactionManager transactionManager;
    @Autowired EventPublicationRegistry registry;
    @Autowired IncompleteEventPublications incomplete;
    @Autowired FlakyListener listener;

    // Kiểu sự kiện chỉ phục vụ test recovery.
    public record RetryProbe(UUID eventId) {}

    @Test
    void failedPublicationCanBeResubmittedAndCompleted() {
        UUID eventId = UUID.randomUUID();
        var transaction = new TransactionTemplate(transactionManager);

        try {
            transaction.executeWithoutResult(status ->
                    publisher.publishEvent(new RetryProbe(eventId)));
        } catch (SimulatedListenerFailure expected) {
            // Listener đồng bộ AFTER_COMMIT cố tình lỗi lần đầu.
        }

        assertThat(listener.attemptsFor(eventId)).isEqualTo(1);
        assertThat(registry.findIncompletePublications())
                .anyMatch(publication ->
                        publication.getEvent() instanceof RetryProbe e
                                && e.eventId().equals(eventId));

        // Chỉ dùng trên test DB cô lập, không có publication
        // không liên quan cần giữ nguyên.
        incomplete.resubmitIncompletePublicationsOlderThan(Duration.ZERO);

        await().atMost(Duration.ofSeconds(10))
                .untilAsserted(() -> {
                    assertThat(listener.hasProcessed(eventId)).isTrue();
                    assertThat(listener.attemptsFor(eventId))
                            .isEqualTo(2);
                    assertThat(registry.findIncompletePublications())
                            .noneMatch(publication ->
                                    publication.getEvent()
                                            instanceof RetryProbe e
                                    && e.eventId().equals(eventId));
                });
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class TestListeners {
        @Bean
        FlakyListener flakyListener() {
            return new FlakyListener();
        }
    }

    static class SimulatedListenerFailure extends RuntimeException {}

    static class FlakyListener {

        private final ConcurrentHashMap<UUID, AtomicInteger> attempts =
                new ConcurrentHashMap<>();
        private final Set<UUID> processed =
                ConcurrentHashMap.newKeySet();

        int attemptsFor(UUID eventId) {
            return attempts.getOrDefault(
                    eventId, new AtomicInteger()).get();
        }

        boolean hasProcessed(UUID eventId) {
            return processed.contains(eventId);
        }

        @TransactionalEventListener
        public void on(RetryProbe event) {
            int invocation = attempts.computeIfAbsent(
                    event.eventId(), id -> new AtomicInteger())
                    .incrementAndGet();

            if (invocation == 1) {
                throw new SimulatedListenerFailure();
            }

            processed.add(event.eventId());
        }
    }
}
~~~

**Cách đọc test:** lần đầu listener ném exception sau commit, publication còn incomplete. Recovery giao lại cùng `RetryProbe(eventId)`, listener xử lý thành công và registry xác nhận hoàn tất. `Set` chỉ là probe quan sát trong bộ nhớ test; **không phải** cách thiết kế idempotency bền vững cho production.

**Giới hạn của ví dụ:** hành vi exception propagation, chuyển trạng thái và API resubmission có thể khác giữa các phiên bản Spring Modulith; cần đối chiếu bản thực tế trước khi chạy. Test dùng `Duration.ZERO` **chỉ an toàn trong môi trường cô lập**; với CI dùng chung database hoặc production, phải lọc/chọn publication theo chính sách và tránh retry mọi incomplete. Nếu resubmit async, Awaitility giúp chờ kết quả thay vì giả định hoàn tất ngay.

### 10.3. Bổ sung kiểm tra side effect database

Một test mạnh hơn không chỉ đo số lần listener vào method, mà còn xác nhận trạng thái bền vững của module nhận:

~~~java
// Đoạn assertion sau bước resubmit và xử lý thành công.
assertThat(reservationRepository.countByOrderId(orderId))
        .isEqualTo(1);
assertThat(processedEventRepository.existsById(eventId))
        .isTrue();
~~~

Đây là **đoạn assertion**, cần thêm `reservationRepository`, `processedEventRepository`, entity và logic listener. Hãy thử giao **lại cùng event** thêm một lần trong integration test, rồi xác minh số bản ghi nghiệp vụ vẫn bằng một. Không dùng mỗi bộ đếm invocation để kết luận side effect đúng một lần.

### 10.4. Test rollback nguồn và commit đối chứng

Một integration test khác nên kiểm tra:

~~~java
var tx = new TransactionTemplate(transactionManager);

tx.executeWithoutResult(status -> {
    publisher.publishEvent(new RetryProbe(eventId));
    status.setRollbackOnly();
});

assertThat(registry.findIncompletePublications())
        .noneMatch(publication ->
                publication.getEvent() instanceof RetryProbe e
                        && e.eventId().equals(eventId));
~~~

Với registry cùng transaction nguồn, rollback không để lại publication bền vững. Nhưng test “không tìm thấy publication” **có thể pass giả** nếu registry chưa được cấu hình hoặc listener không tồn tại. Vì vậy phải có nhánh đối chứng **commit rồi listener lỗi** (như mục 10.2) để chứng minh registry thực sự ghi publication.

### 10.5. Test restart và payload cũ

Nếu mục tiêu là phục hồi **sau restart**, test in-memory chưa đủ. Cần integration test nâng cao:

1. Khởi động ứng dụng với registry persistence thật.
2. Tạo publication incomplete rồi kết thúc tiến trình.
3. Khởi động lại bằng **cùng database**, với listener phù hợp.
4. Kích hoạt policy recovery/republication đã cấu hình.
5. Assert publication được đọc lại và side effect thành công đúng một lần.

Kịch bản này còn phát hiện lỗi **serializer compatibility** và listener target bị đổi khi nâng cấp. Nó có thể được chạy ở CI integration stage riêng do chi phí cao hơn unit/module test.

## 11. Kiểm chứng ranh giới kiến trúc

Retry không thay thế nguyên tắc phụ thuộc module. Module `inventory` chỉ nên dùng `OrderPlaced` từ named interface `orders :: events`, không import repository/service nội bộ của `orders`.

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

`verify()` giúp ngăn vòng phụ thuộc và truy cập API không được module khác công bố theo các quy tắc Spring Modulith. Nó **không chạy listener**, không resubmit publication và không đo backlog. Ngược lại, integration test retry pass cũng không chứng minh kiến trúc không vi phạm boundary. Hai nhóm test cần chạy song song trong CI.

## 12. Ma trận quality gate CI cho retry và observability

| Quality gate | Bảo vệ điều gì? | Assertion/đầu ra tiêu biểu |
| --- | --- | --- |
| **Architecture test** | Module không phụ thuộc vòng hoặc truy cập nội bộ sai. | `ApplicationModules.of(...).verify()` pass. |
| **Publisher module test** | Event type/payload do use case phát đúng. | `@ApplicationModuleTest` + `PublishedEvents`. |
| **Commit/rollback test** | Publication bền vững chỉ tồn tại theo kết quả transaction nguồn. | Registry còn publication sau commit + lỗi listener; không còn sau rollback. |
| **Fail-once / retry test** | Listener lỗi lần đầu và xử lý lại thành công. | Incomplete → resubmit → completed. |
| **Per-target test** | Một target lỗi không làm target khác bị đánh dấu completed sai. | Kiểm tra từng target cùng event ID. |
| **Idempotency test** | Giao trùng không tạo side effect trùng. | DB unique marker và số lượng bản ghi nghiệp vụ. |
| **Serialization test** | Event cũ còn deserialize được khi retry/restart. | Round-trip qua serializer đang dùng. |
| **Observability contract test** | Metric/log có target, tuổi, retry và không lộ PII. | Assert cấu trúc/nhãn, ngưỡng cảnh báo được áp dụng. |
| **Recovery after restart** | Registry lưu bền vững qua lifecycle ứng dụng. | Hai lần khởi động dùng chung database test. |

Đặt các test trong job CI thích hợp; test kiến trúc/module chạy nhanh, còn integration có DB hoặc restart có thể nằm trong job riêng nhưng **phải là quality gate** trước khi triển khai thay đổi liên quan publication. Với listener bất đồng bộ, dùng điều kiện chờ và timeout rõ ràng thay vì `Thread.sleep` cố định.

Đo “đã log exception” hoặc “đã gọi resubmit method” là chưa đủ: kết quả cần đạt là **publication hoàn tất và dữ liệu nghiệp vụ đúng sau retry**, đồng thời telemetry phản ánh được các bước.

## 13. Những anti-pattern cần tránh

1. **Retry bằng cách gọi lại use case nguồn.** Có nguy cơ sinh order/event mới; nên resubmit publication hiện có cho đúng target.
2. **Retry mọi incomplete ngay lập tức.** Có thể giao lặp công việc đang `PROCESSING`; cần age/status/coordination.
3. **Không giới hạn batch hoặc concurrency.** Downstream đang lỗi có thể bị quá tải nặng hơn do retry storm.
4. **Dùng `@EventListener` thường rồi kỳ vọng registry theo dõi mặc định.** Registry tập trung vào transactional listener theo cấu hình.
5. **Nuốt exception rồi trả về bình thường.** Publication có thể bị đánh dấu completed dù side effect lỗi.
6. **Lưu idempotency trong một `HashSet` trong RAM.** Không bền vững qua restart hoặc nhiều instance.
7. **Dùng publication ID thay business event ID một cách thiếu suy xét.** Một event có thể có nhiều publication theo nhiều target; khóa chống trùng phải phù hợp nghiệp vụ.
8. **Chỉ xem số incomplete toàn hệ thống.** Không biết target nào lỗi, tuổi bao lâu hoặc bao nhiêu lần đã retry.
9. **Gắn event ID, order ID làm metric label.** Cardinality tăng không kiểm soát; dùng log/trace có phân quyền.
10. **Cho rằng không thấy completed record nghĩa là lỗi.** Mode `DELETE` có thể xóa bản ghi hoàn tất.
11. **Cho rằng restart tự sửa mọi lỗi.** Payload/target không tương thích hoặc dependency vẫn hỏng thì restart không giải quyết vấn đề.
12. **Cho rằng registry bảo đảm đúng một lần với API ngoài.** Side effect có thể thành công trước khi registry ghi completed; consumer cần idempotency.

## 14. Bài tập tình huống

Một hệ thống có `checkout` phát `PaymentAccepted` trong transaction. Ba transactional listener:

- `ledger`: cập nhật sổ cái thành công.
- `inventory`: gọi database giữ hàng, lỗi timeout ở lần đầu.
- `email`: nhà cung cấp báo timeout dù có thể email đã gửi.

Ứng dụng chạy hai replica và lưu publication trong JDBC. Dashboard chỉ hiển thị tổng số publication chưa hoàn tất.

**Câu hỏi:**

1. Với một `PaymentAccepted`, có thể có mấy publication và vì sao?
2. Nếu `ledger` completed, điều đó có làm publication `inventory` completed theo không?
3. Vì sao `inventory` có thể retry, còn `email` cần kiểm tra idempotency key/kết quả provider trước?
4. Vì sao không nên bật job trên cả hai replica để resubmit mọi incomplete mỗi giây?
5. Nên thêm metric và log field nào để dashboard giúp điều tra nhanh hơn?
6. Test `PublishedEvents` ở `checkout` đã đủ chứng minh recovery sau restart chưa?
7. Nếu application nâng cấp và đổi tên listener, publication tồn đọng có rủi ro gì?

**Gợi ý đáp án:**

1. Có thể có **ba publication**, mỗi transactional listener target một bản ghi, mặc dù chỉ một event được phát.
2. Không. Completion là theo **target**; inventory có thể vẫn incomplete hoặc failed.
3. Timeout database thường có thể retry khi cơ sở dữ liệu phục hồi. Với email, side effect có thể đã xảy ra nên cần chống gửi trùng.
4. Hai instance có thể cùng xử lý một publication đang chạy; gây tải và tác động trùng. Cần age/status, coordination và rate limit.
5. Đếm incomplete/failed theo target, tuổi lâu nhất, retry attempts, completion latency; log publication ID, target, event type, correlation ID và nhóm lỗi, không log PII.
6. Không. Nó chỉ chứng minh event được phát; cần DB, registry, serializer, listener và restart test thực sự.
7. Target identifier cũ có thể không còn ánh xạ được đến listener hiện tại; cần kế hoạch tương thích/migration và thử nghiệm recovery.

## 15. Checklist triển khai và vận hành

- [ ] Event được phát trong transaction nguồn khi yêu cầu publication gắn với commit.
- [ ] Có registry persistence starter, schema, transaction manager và serializer hoạt động.
- [ ] Event payload bất biến, có ID nghiệp vụ ổn định và deserialize được sau upgrade.
- [ ] Phân biệt số lời gọi publish với số publication theo target.
- [ ] Không coi mọi incomplete là lỗi; theo dõi trạng thái, tuổi và target.
- [ ] Chính sách retry nêu rõ trường hợp đủ điều kiện, backoff, batch, concurrency và điểm dừng.
- [ ] Không resubmit bằng cách gọi lại use case nguồn.
- [ ] Consumer idempotent qua khóa bền vững hoặc cơ chế của provider ngoài.
- [ ] Listener không nuốt lỗi cần retry; không tự đánh dấu completed khi side effect chưa thành công.
- [ ] Observability có backlog, oldest age, completion latency, failure/retry rate theo target.
- [ ] Log/trace có correlation phù hợp, không làm lộ payload và không tạo metric label cardinality cao.
- [ ] Với nhiều replica, đã đánh giá nguy cơ retry đồng thời và chính sách recovery khi restart.
- [ ] Có `@ApplicationModuleTest` + `PublishedEvents` cho module phát.
- [ ] Có integration test fail-once → incomplete → resubmit → completed và kiểm tra side effect thực.
- [ ] Có test rollback, serialization/restart khi hệ thống yêu cầu, và `ApplicationModules.verify()` trong CI.

**Kết luận:** Retry an toàn không phải là gọi lại chức năng đã phát event, mà là **xử lý lại publication chưa hoàn tất đúng listener target, đúng điều kiện và có kiểm soát**. Observability phải cho biết publication nào đang chờ, lỗi ở đâu, đã thử lại bao nhiêu lần và liệu dữ liệu nghiệp vụ đã hội tụ hay chưa. Kết hợp registry bền vững, idempotency, metrics/log/tracing, `@ApplicationModuleTest`, integration test và quality gate CI giúp Spring Modulith phục hồi từ lỗi downstream mà không đánh đổi tính nhất quán.

### Tài liệu đối chiếu

- [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html): transactional listener, registry, lifecycle và resubmission.
- [EventPublicationRegistry API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/events/core/EventPublicationRegistry.html): phương thức quan sát publication.
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): các pha `@TransactionalEventListener`.
- [Micrometer Documentation](https://docs.micrometer.io/micrometer/reference/): mô hình gauge, counter và các nguyên tắc instrumentation.

> Ghi chú tương thích: API resubmission, trạng thái chi tiết và cơ chế staleness có thể khác nhau theo phiên bản Spring Modulith. Mẫu mã và property phải được đối chiếu với dependency/transaction manager đang dùng trước khi đưa vào production.
