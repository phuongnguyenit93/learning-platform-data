# Vai trò Event Publication Registry trong Spring Modulith

## 1. Vì sao cần Event Publication Registry?

Trong ứng dụng Spring Modulith, các module dùng **application events** để giao tiếp mà không gọi trực tiếp implementation của nhau. Module `orders` có thể công bố `OrderPlaced`; module `notifications` gửi xác nhận, `loyalty` cộng điểm, còn `analytics` cập nhật dữ liệu báo cáo. Đây là mô hình phù hợp để **giảm coupling** và **bảo vệ ranh giới nghiệp vụ**.

Nhưng một câu hỏi quan trọng xuất hiện khi các handler chạy sau commit và bất đồng bộ:

> Đơn hàng đã được lưu thành công, nhưng tiến trình ứng dụng bị dừng trước khi listener hoàn tất. Hệ thống dựa vào đâu để biết công việc nào còn dang dở?

**Event Publication Registry** của Spring Modulith là một cơ chế nhằm **ghi nhận và theo dõi việc công bố event tới các transactional event listener**. Với bộ lưu trữ bền vững được cấu hình phù hợp, registry cho biết publication nào chưa được xử lý hoàn tất và tạo cơ sở để **khôi phục/phát lại** công việc sau sự cố.

~~~mermaid
flowchart LR
    O["orders<br/>Đơn hàng được tạo"] --> E(("OrderPlaced"))
    E --> R["Event Publication Registry<br/>Ghi nhận publication"]
    R --> N["notifications<br/>Handler"]
    R --> L["loyalty<br/>Handler"]
    R --> A["analytics<br/>Handler"]
    N -->|"Completed"| R
    L -. "Lỗi / chưa hoàn tất" .-> R
    A -->|"Completed"| R
~~~

Sơ đồ minh họa **vai trò theo dõi publication**; nó không có nghĩa registry là một message broker chủ động chuyển mọi message qua mạng.

Trong chương **Publication Registry** thuộc module học **SPRING_MODULITH_APPLICATION_EVENTS**, bài viết giải thích vai trò kiến trúc, ranh giới transaction, vòng đời publication, khôi phục khi lỗi, giới hạn của registry và cách kiểm thử/quan sát việc giao sự kiện đáng tin cậy.

## 2. Phân biệt event, publication và kết quả nghiệp vụ

Ba khái niệm thường bị trộn lẫn:

| Khái niệm | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **Event** | `OrderPlaced(eventId, orderId, occurredAt)` | Sự thật nghiệp vụ đã xảy ra, được mô tả bằng dữ liệu. |
| **Publication** | Bản ghi theo dõi `OrderPlaced` hướng đến listener notifications | Nỗ lực/công việc giao **một event cho một listener** do registry theo dõi. |
| **Business side effect** | Email xác nhận được gửi, điểm thưởng được ghi | Kết quả mà consumer chịu trách nhiệm thực hiện. |

Một event có thể tương ứng **nhiều publication**, vì nhiều transactional listener có thể cùng quan tâm. Và một publication được đánh dấu hoàn tất không phải là một bảo đảm độc lập rằng mọi side effect ở một dịch vụ bên ngoài đã thực hiện **đúng một lần** trong mọi tình huống lỗi.

Ví dụ một đơn hàng phát `OrderPlaced(E-101)` và có ba module tiêu thụ:

~~~text
Event: OrderPlaced(eventId=E-101, orderId=O-101)

Publication cho notifications : COMPLETED
Publication cho loyalty       : INCOMPLETE
Publication cho analytics     : COMPLETED
~~~

Đây là **biểu diễn trạng thái logic** để giải thích khái niệm, không phải tên bảng hay tập giá trị trạng thái vật lý bắt buộc của mọi phiên bản Spring Modulith.

Điểm quan trọng: **một lỗi của loyalty không được phép biến hai publication đã hoàn tất của notifications và analytics thành một công việc bắt buộc chạy lại**. Registry giúp theo dõi theo listener, thay vì chỉ biết “event đã phát” như một cờ chung.

## 3. Vấn đề mà registry giải quyết: khoảng trống sau khi commit

Nếu chỉ dùng `ApplicationEventPublisher` với listener xử lý bất đồng bộ:

1. Module orders lưu đơn trong transaction T1.
2. Orders công bố `OrderPlaced`.
3. T1 commit.
4. Listener sau commit được lên lịch.
5. Ứng dụng dừng trước khi listener hoàn tất.

Nếu application event chỉ tồn tại trong bộ nhớ mà không có thông tin theo dõi bền vững, một tiến trình mới **không tự biết chắc** nhiệm vụ hậu xử lý nào đã bị bỏ dở.

~~~mermaid
sequenceDiagram
    autonumber
    participant O as orders / T1
    participant DB as Database
    participant E as Application events
    participant N as notifications

    O->>DB: Lưu đơn hàng
    O->>E: publishEvent(OrderPlaced)
    O->>DB: COMMIT
    Note over E,N: Tiến trình dừng trước khi listener hoàn tất
    Note over DB,N: Đơn đã có nhưng email có thể chưa gửi
~~~

**Registry được thiết kế để giảm rủi ro mất dấu vết của publication**, bằng cách lưu thông tin công việc cần giao cho transactional listener và ghi nhận khi hoàn tất, với điều kiện integration lưu trữ và transaction phù hợp đã được cấu hình.

### Không đồng nghĩa “bật registry thì mất event trở thành bất khả thi”

Vẫn có rủi ro nếu:

- Publisher không hề gọi `publishEvent` do lỗi logic.
- Không cấu hình backend persistent hoặc backend không khả dụng.
- Việc ghi dữ liệu nghiệp vụ và publication không cùng ranh giới transaction đáng tin cậy.
- Publication đã lưu nhưng không có quy trình recovery thực tế.
- Event/consumer thay đổi schema hoặc tên định danh làm publication cũ không thể xử lý.
- Một handler nuốt exception và báo thành công dù side effect chưa hoàn tất.

Registry là **một thành phần trong thiết kế độ tin cậy**, không thay thế toàn bộ thiết kế transaction, idempotency hay vận hành.

## 4. Vị trí của registry trong kiến trúc Spring Modulith

Có thể nhìn kiến trúc theo bốn trách nhiệm:

~~~mermaid
flowchart TB
    B["Business module<br/>orders"] -->|"publishEvent(OrderPlaced)"| S["Spring Application Events"]
    S --> R["Event Publication Registry<br/>Tracking per transactional listener"]
    S --> N["Transactional listener<br/>notifications"]
    S --> L["Transactional listener<br/>loyalty"]
    R -. "Theo dõi publication" .-> N
    R -. "Theo dõi publication" .-> L
    N -. "Hoàn tất" .-> R
    L -. "Lỗi còn dang dở" .-> R
    R --> P[("Persistent publication store<br/>khi được cấu hình")]
    R --> K["Recovery / republication<br/>khi được kích hoạt"]
~~~

- **Publisher** sở hữu sự thật nghiệp vụ và hợp đồng event.
- **Spring event infrastructure** nhận `publishEvent` và thực hiện điều phối event tới các listener phù hợp.
- **Transactional listener** quyết định xử lý ở phase giao dịch thích hợp; `@ApplicationModuleListener` dành cho xử lý sau commit, bất đồng bộ và transaction riêng.
- **Registry + storage** ghi nhận những publication liên quan và trạng thái hoàn tất; cơ chế recovery sử dụng thông tin này để xử lý công việc còn dang dở.

Không nên tưởng tượng rằng registry có API để mọi module gửi trực tiếp `registry.sendEmail()` hay `registry.awardPoints()`. Quy tắc nghiệp vụ vẫn nằm trong các consumer; registry chỉ theo dõi **giao event**.

## 5. Registry gắn với transactional event listener như thế nào?

Trong Spring, có nhiều cách đăng ký listener:

| Loại | Thời điểm phổ biến | Ý nghĩa đối với publication tracking |
| --- | --- | --- |
| `@EventListener` | Đồng bộ ngay khi publish theo cấu hình mặc định. | Không mặc định mang ngữ nghĩa giao dịch và theo dõi bền vững của registry. |
| `@TransactionalEventListener` | Mặc định ở phase `AFTER_COMMIT`; có thể chọn phase khác. | Là loại listener gắn với transaction; registry được thiết kế để theo dõi transactional event publication tương ứng. |
| `@ApplicationModuleListener` | Spring Modulith: sau commit, bất đồng bộ, transaction riêng. | Lựa chọn quen thuộc cho giao tiếp module cần theo dõi publication. |

Ví dụ listener gửi email:

~~~java
package com.acme.shop.notifications.internal;

import com.acme.shop.orders.events.OrderPlaced;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class OrderConfirmationListener {

    private final ConfirmationService confirmations;

    OrderConfirmationListener(ConfirmationService confirmations) {
        this.confirmations = confirmations;
    }

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        confirmations.sendForOrder(
                event.eventId(),
                event.orderId()
        );
    }
}
~~~

`ConfirmationService` là component do dự án triển khai. Annotation không cung cấp một hàm gửi email hoặc khóa chống trùng tự động.

**Lưu ý về transaction:** `@TransactionalEventListener` mặc định **không chạy** nếu publisher công bố event ngoài một transaction đang hoạt động. Có thể dùng `fallbackExecution = true` khi phù hợp, nhưng như vậy phải đánh giá lại kỳ vọng về việc chỉ xử lý sau commit.

Trong ứng dụng cần publication bền vững, nên **tạo và publish event ở ranh giới transaction nghiệp vụ rõ ràng**, rồi kiểm thử cả commit và rollback.

## 6. Vòng đời publication: từ ghi nhận đến hoàn tất

Một vòng đời khái niệm có các bước:

1. Publisher tạo `OrderPlaced` với hợp đồng dữ liệu phù hợp.
2. Publisher gọi `ApplicationEventPublisher.publishEvent(event)` trong transaction.
3. Hạ tầng có registry nhận diện những transactional listener liên quan và **ghi nhận publication** theo backend được cấu hình.
4. Transaction nghiệp vụ commit, làm sự thật nghiệp vụ có hiệu lực.
5. Listener sau commit thực thi công việc của module tiêu thụ.
6. Nếu listener xử lý thành công, registry **đánh dấu publication hoàn tất** theo cơ chế hỗ trợ.
7. Nếu listener thất bại hoặc tiến trình dừng, publication có thể **chưa hoàn tất**.
8. Công cụ recovery/republication có thể sử dụng publication còn dang dở để thử xử lý lại.

~~~mermaid
stateDiagram-v2
    [*] --> Recorded: Ghi nhận publication
    Recorded --> RolledBack: Transaction nghiệp vụ rollback
    Recorded --> Pending: Transaction nghiệp vụ commit
    Pending --> Processing: Listener được kích hoạt
    Processing --> Completed: Listener thành công
    Processing --> Pending: Lỗi / chưa hoàn tất
    Pending --> Processing: Recovery / republication
    Completed --> [*]
    RolledBack --> [*]
~~~

**Đây là state machine khái niệm phục vụ học tập**, không phải toàn bộ trạng thái được export nguyên văn bởi API Spring Modulith.

Nếu rollback xảy ra, publication được ghi **trong cùng transaction** với nghiệp vụ thông thường cũng bị rollback. Nếu phần ghi publication dùng storage hoặc transaction manager không tương thích, không thể tự giả định kết quả đó.

### Khi nào được xem là completed?

Trong mô hình theo dõi, một transactional listener đã được đánh dấu hoàn tất khi cơ chế xử lý của registry xác nhận listener thành công. Nhưng nếu listener nuốt lỗi hoặc trả về trước khi side effect thực sự hoàn tất, việc đánh dấu đó có thể **không phản ánh trạng thái nghiệp vụ mong muốn**.

Vì vậy, định nghĩa thế nào là “handler thành công” là trách nhiệm của consumer, đặc biệt với tác vụ gọi email, webhook hoặc API thanh toán bên ngoài.

## 7. Mối quan hệ giữa publication và transaction gốc

Giả sử `OrderService.placeOrder` chạy trong transaction T1:

~~~java
package com.acme.shop.orders.events;

import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

public record OrderPlaced(
        UUID eventId,
        UUID orderId,
        UUID customerId,
        Instant occurredAt
) {
    public OrderPlaced {
        Objects.requireNonNull(eventId, "eventId");
        Objects.requireNonNull(orderId, "orderId");
        Objects.requireNonNull(customerId, "customerId");
        Objects.requireNonNull(occurredAt, "occurredAt");
    }
}
~~~

~~~java
package com.acme.shop.orders.internal;

import com.acme.shop.orders.events.OrderPlaced;
import java.time.Clock;
import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    private final OrderRepository orders;
    private final ApplicationEventPublisher publisher;
    private final Clock clock;

    public OrderService(
            OrderRepository orders,
            ApplicationEventPublisher publisher,
            Clock clock
    ) {
        this.orders = orders;
        this.publisher = publisher;
        this.clock = clock;
    }

    @Transactional
    public UUID placeOrder(PlaceOrderCommand command) {
        Order saved = orders.save(Order.create(command));

        publisher.publishEvent(new OrderPlaced(
                UUID.randomUUID(),
                saved.getId(),
                saved.getCustomerId(),
                clock.instant()
        ));

        return saved.getId();
    }
}
~~~

Các kiểu `Order`, `OrderRepository`, `PlaceOrderCommand` và `Clock` bean là các thành phần minh họa, phải được định nghĩa theo ứng dụng thật. Ví dụ giả định `save` trả về một order đã có ID ổn định.

Ý nghĩa transaction:

- T1 có trách nhiệm **chấp nhận và lưu đơn hàng**.
- `publishEvent` diễn ra trong T1, làm cơ sở cho transactional event publication.
- Listener `@ApplicationModuleListener` xử lý hậu nghiệp vụ **sau khi T1 commit**.
- Nếu T1 rollback, listener sau commit không nên thực hiện tác dụng phụ cho đơn không tồn tại.
- Với backend registry và transaction phù hợp, việc ghi publication có thể đồng bộ về mặt commit với dữ liệu nghiệp vụ.

**Không có một lệnh `publishEvent` nào tự tạo distributed transaction** giữa orders, loyalty, notifications hoặc hệ thống email. Tính nguyên tử của việc ghi đơn và lưu publication phải được xem xét theo **nguồn dữ liệu, integration và transaction manager cụ thể**.

## 8. Vì sao cần ghi publication trong cùng ranh giới commit?

Hãy xem một thiết kế dễ gặp:

~~~text
Bước 1: Lưu đơn hàng rồi COMMIT.
Bước 2: Gọi publishEvent(OrderPlaced).
~~~

Nếu tiến trình dừng **giữa hai bước**, đơn hàng đã tồn tại nhưng event có thể chưa từng được công bố hoặc lưu ở đâu. Không có publication để recovery.

~~~mermaid
sequenceDiagram
    participant O as OrderService
    participant DB as Database
    participant E as Event Infrastructure

    O->>DB: INSERT order; COMMIT
    Note over O,E: Crash window giữa commit và publish
    O-xE: publishEvent chưa diễn ra
~~~

Một mẫu đáng tin cậy hơn khi có transaction nghiệp vụ là **ghi nhận thông tin cần giao trong cùng ranh giới transaction**, sau đó xử lý sau commit. Registry của Spring Modulith hỗ trợ theo dõi publication theo mô hình này khi integration lưu trữ và transaction được cấu hình thích hợp.

Vì vậy, không nên thực hiện “commit trước, publish sau” bằng hai thao tác không có cơ chế nối bền vững, nếu yêu cầu nghiệp vụ là không được âm thầm mất tác vụ hậu xử lý.

### Một trường hợp không thể cứu bằng registry

Nếu code path tạo order **không hề gọi** `publishEvent`, registry không thể tự suy ra một `OrderPlaced` cần tồn tại.

Ví dụ, hai nhánh code:

~~~java
if (order.isExpress()) {
    orders.save(order);
    // Quên publish OrderPlaced.
} else {
    orders.save(order);
    publisher.publishEvent(new OrderPlaced(...));
}
~~~

Đây là lỗi nghiệp vụ của publisher, không phải lỗi giao event. Cần test tất cả nhánh use case và, khi cần, đối soát giữa dữ liệu nghiệp vụ đã commit với dấu vết event/consumer để phát hiện thiếu hụt.

## 9. Fan-out: một event có thể có nhiều publication

Một `OrderPlaced` được ba listener quan tâm:

~~~text
OrderPlaced(E-101)
    ├── notifications.on(OrderPlaced) : INCOMPLETE
    ├── loyalty.on(OrderPlaced)       : COMPLETED
    └── analytics.on(OrderPlaced)     : COMPLETED
~~~

Mỗi consumer tự có trạng thái xử lý và lỗi. Registry giúp theo dõi **việc giao một event cho từng listener** thay vì chỉ có một cờ toàn cục “event này đã xong”.

Điều này đặc biệt cần thiết khi:

- Notifications gọi email provider và bị timeout.
- Loyalty ghi điểm vào database riêng và thành công.
- Analytics ghi projection và thành công.

Nếu chỉ phát lại một cách mù quáng cho mọi handler, hai tác vụ đã thành công có nguy cơ thực hiện lại. Với publication tracking, có thể định hướng phục hồi **nhánh còn dang dở**, dù consumer vẫn phải thiết kế idempotency vì một lần xử lý đã thực hiện side effect vẫn có thể chưa kịp được ghi nhận completion.

### Đừng suy ra fan-out có thứ tự cố định

Các `@ApplicationModuleListener` chạy bất đồng bộ. Không có cơ sở để cho rằng notifications luôn hoàn tất trước loyalty hoặc ngược lại. Nếu nghiệp vụ yêu cầu “chỉ cộng điểm sau khi thanh toán thành công”, nên nghe một event `PaymentCaptured` do module payments sở hữu hoặc điều phối workflow rõ ràng; không dùng `@Order` để áp đặt thứ tự hoàn tất của các handler async.

## 10. Registry không phải message broker hay queue tổng quát

Cần phân biệt:

| Thành phần | Mục tiêu | Không nên nhầm với |
| --- | --- | --- |
| `ApplicationEventPublisher` | Công bố event qua hệ thống application event trong Spring. | Durable broker hoặc outbox mặc định. |
| **Event Publication Registry** | Ghi nhận và theo dõi publication đến transactional listener. | Hàng đợi phân tán có consumer groups/partition/offset. |
| Transactional outbox | Lưu thông điệp dự kiến truyền đi cùng transaction nghiệp vụ. | Mọi chức năng quản lý listener của Spring Modulith. |
| Kafka/RabbitMQ hoặc broker tương tự | Chuyên chở message theo cơ chế broker có cấu hình và bảo đảm riêng. | Cơ chế `publishEvent` nội bộ của JVM. |
| Consumer idempotency ledger | Đảm bảo một tác dụng phụ nghiệp vụ không bị áp dụng trùng. | Registry đánh dấu giao sự kiện đã hoàn tất. |

Event Publication Registry **không mặc nhiên** đem lại những đặc tính như durable topic đa tiến trình, partition ordering, consumer group rebalancing, lịch sử để subscriber mới đọc lại hoặc phát event xuyên mạng.

Nếu hệ thống cần gửi sự kiện sang service độc lập, phải thiết kế cơ chế integration event, externalization, outbox hoặc broker phù hợp. Việc có registry trong một ứng dụng Modulith không tự làm `OrderPlaced` xuất hiện tại mọi service khác.

## 11. Các lựa chọn persistence và trách nhiệm cấu hình

Spring Modulith có những tích hợp lưu trữ publication phù hợp với các công nghệ persistence khác nhau, tùy phiên bản và bộ dependency ứng dụng sử dụng. Trong một ứng dụng thực tế, nhóm phát triển phải lựa chọn **backend lưu trữ được hỗ trợ**, cấu hình transaction và kiểm tra cơ chế lưu/recovery.

Một thiết lập thực sự có độ tin cậy cần trả lời:

1. **Backend nào giữ publication?** Một database quan hệ, một data store khác hay một triển khai không bền vững?
2. **Publication được commit ra sao?** Gắn với cùng database/transaction manager của thay đổi nghiệp vụ hay chỉ là ghi độc lập?
3. **Ai tạo schema storage?** Quy trình migration/mặc định tích hợp có được kiểm soát trong production không?
4. **Số lượng publication tăng thế nào?** Mỗi sự kiện có thể tạo nhiều mục theo listener.
5. **Dữ liệu nào được lưu?** Event payload có thông tin nhạy cảm cần bảo vệ/retention không?
6. **Khôi phục được kích hoạt bằng cách nào?** Startup, scheduler, thao tác vận hành hoặc API phù hợp?
7. **Phiên bản đang chạy có hỗ trợ đủ tính năng không?** Không suy từ ví dụ của phiên bản khác về package, tên dependency, API hoặc cấu hình.
8. **Môi trường kiểm thử có tương đương production không?** Một test chỉ chạy với event trong bộ nhớ chưa kiểm chứng storage bền vững.

Ví dụ cấu hình mong muốn ở mức **kiến trúc**:

~~~text
orders database
    ├── Business records: orders, order_items
    └── Persistent publications: trạng thái giao đến từng listener
        (lưu qua integration được Spring Modulith hỗ trợ)

Business transaction T1:
    persist(order) + record(publications) -> COMMIT

After commit:
    handle(listener publication)
    -> mark completed / leave incomplete
~~~

Đây là **sơ đồ khái niệm**, không đưa tên bảng, dependency hay thuộc tính cấu hình giả định vì các thành phần đó cần chọn đúng phiên bản thư viện và persistence integration thực tế.

### Nhiều datasource là một ranh giới quan trọng

Nếu business data được commit ở database A nhưng registry lưu publication ở database B mà không có cơ chế atomic commit giữa hai bên, có thể xảy ra:

~~~text
A: Order COMMITTED
B: Ghi publication FAILED
=> Đơn tồn tại nhưng không có publication để khôi phục.
~~~

Một `@Transactional` thông thường không tự biến hai datasource thành distributed transaction. Khi cần độ tin cậy, phải xác minh transaction manager, storage và thiết kế ghi publication thực sự có bảo đảm phù hợp.

## 12. Registry có tự retry mọi event bị lỗi không?

**Không nên giả định như vậy.** Registry theo dõi các publication chưa hoàn tất, nhưng **lịch, cách thức và điều kiện phát lại** phụ thuộc tính năng/phiên bản Spring Modulith, configuration và cơ chế recovery mà ứng dụng sử dụng.

Ví dụ một publication bị lỗi do email provider mất kết nối. Cần trả lời:

- Event còn được lưu bền vững hay không?
- Publication được xem là incomplete theo tiêu chí nào?
- Có cơ chế republication sau startup hoặc theo lịch không?
- Ai là thành phần kích hoạt recovery, với quyền hạn nào?
- Tần suất retry có giới hạn và có backoff không?
- Khi lỗi do dữ liệu không hợp lệ thay vì timeout, phải dừng retry ra sao?
- Listener được định danh có còn tương thích sau khi deploy không?
- Publication quá hạn được cảnh báo, khoanh vùng và xử lý thủ công như thế nào?

~~~mermaid
flowchart TD
    I["Publication chưa hoàn tất"] --> V{"Payload và listener còn tương thích?"}
    V -->|"Không"| Q["Khoanh vùng và sửa schema/consumer"]
    V -->|"Có"| C{"Lỗi còn có thể retry?"}
    C -->|"Không"| Q
    C -->|"Có"| R["Chọn lịch retry có giới hạn"]
    R --> D["Consumer kiểm tra idempotency"]
    D --> E{"Xử lý thành công?"}
    E -->|"Có"| F["Publication hoàn tất"]
    E -->|"Không"| G{"Còn retry budget?"}
    G -->|"Có"| R
    G -->|"Không"| Q
~~~

Đây là **quy trình recovery gợi ý**, không phải khẳng định Spring Modulith mặc định cài sẵn toàn bộ các nhánh, policy và cơ chế lưu lịch.

### Không xử lý poison event bằng retry vô hạn

Nếu consumer không deserialize được event vì đã đổi schema, retry liên tục chỉ tạo lỗi giống nhau và tăng tải. Cần có đường xử lý các publication lỗi vĩnh viễn: giữ dấu vết, cảnh báo, sửa mã/adapter/migration hoặc thực hiện đối soát có kiểm soát.

## 13. Idempotency: mảnh ghép bắt buộc khi có recovery

Kịch bản rất quan trọng:

1. Registry có publication `OrderPlaced(E-101)` cho loyalty.
2. Loyalty cộng điểm thành công và commit dữ liệu.
3. Ứng dụng dừng trước khi publication được đánh dấu hoàn tất.
4. Publication được khôi phục.
5. Loyalty nhận lại `OrderPlaced(E-101)`.

Nếu listener cộng điểm lại vô điều kiện, cùng một sự kiện khiến khách được cộng điểm hai lần. Registry giúp biết publication **chưa có dấu completion**, nhưng **không thể suy ra liệu side effect trước đó đã thực hiện hay chưa** trong mọi failure window.

Vì vậy, consumer phải **idempotent**: xử lý nhiều lần cùng một event cho cùng tác vụ mà vẫn đạt kết quả nghiệp vụ tương đương một lần.

### Khóa idempotency nào phù hợp?

- `eventId`: định danh ổn định của một lần xảy ra sự kiện.
- `orderId`: định danh đơn hàng, có thể xuất hiện trong nhiều sự kiện.
- `consumerName` hoặc `effectType`: phân biệt các tác vụ độc lập với cùng event.

Nếu nhiều consumer cùng dùng một kho dấu vết, khóa thường cần dạng **`(consumerName, eventId)`**. Không được để notifications đánh dấu `E-101` đã xong khiến loyalty vô tình bỏ qua `E-101`.

## 14. Ví dụ idempotency với ledger điểm thưởng

Một bảng ledger có thể dùng unique constraint:

~~~sql
CREATE TABLE loyalty_awards (
    event_id VARCHAR(36) PRIMARY KEY,
    order_id VARCHAR(36) NOT NULL,
    customer_id VARCHAR(36) NOT NULL,
    awarded_points BIGINT NOT NULL,
    created_at TIMESTAMP NOT NULL
);
~~~

Service loyalty có thể thực hiện một transaction ghi ledger cùng thay đổi số điểm:

~~~java
package com.acme.shop.loyalty.internal;

import com.acme.shop.orders.events.OrderPlaced;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class LoyaltyAwardService {

    private final AwardLedger awards;
    private final LoyaltyBalances balances;

    LoyaltyAwardService(
            AwardLedger awards,
            LoyaltyBalances balances
    ) {
        this.awards = awards;
        this.balances = balances;
    }

    @Transactional
    public void creditOnce(OrderPlaced event) {
        // insertIfAbsent là API minh họa cần triển khai NGUYÊN TỬ.
        boolean firstTime = awards.insertIfAbsent(
                event.eventId(), event.orderId(), event.customerId()
        );

        if (!firstTime) {
            return;
        }

        // Ghi ledger và cập nhật điểm cùng transaction.
        balances.addPointsAtomically(event.customerId(), 20L);
    }
}
~~~

`AwardLedger`, `LoyaltyBalances` và các phương thức trong ví dụ không phải API Spring Modulith; chúng là lớp nội bộ minh họa. Ví dụ dùng `customerId` trong event làm khóa tìm tài khoản loyalty; dự án thật cần kiểm tra quyền, quan hệ khách hàng–tài khoản và quy tắc cộng điểm phù hợp.

**Điều cốt lõi không nằm ở tên method** mà ở ranh giới nguyên tử:

- Ghi dấu event được xử lý và ghi điểm ở **cùng database transaction** khi phù hợp.
- Unique constraint là hàng rào chống trùng giữa các worker đồng thời.
- Không chỉ kiểm tra `exists` rồi insert trong hai thao tác không khóa.
- Nếu database ném duplicate-key exception và transaction bị đánh dấu rollback-only, phải xử lý theo đặc tính database/transaction; không bắt exception rồi tiếp tục ghi tùy tiện.
- Nếu transaction cộng điểm rollback, ghi dấu cũng cần rollback để recovery còn cơ hội làm lại.

Trong ví dụ này, `@ApplicationModuleListener` vốn có ngữ nghĩa transaction riêng. Nếu service nội bộ tự có `@Transactional`, cần hiểu propagation mặc định của nó và cách lời gọi qua Spring proxy, tránh tạo transaction lồng nhau vô tình.

## 15. Side effect ngoài DB không thể được registry làm nguyên tử

Xem tác vụ gửi email:

~~~text
1. Notification listener gọi email provider.
2. Provider nhận yêu cầu và gửi email.
3. Kết nối bị ngắt trước khi trả lời.
4. Listener ghi nhận lỗi/timeout.
5. Publication còn incomplete.
6. Recovery gọi gửi email lần nữa.
~~~

Ứng dụng không thể chắc chắn email lần đầu đã gửi hay chưa chỉ từ một timeout. Đây là **kết quả chưa xác định**, không đơn thuần là “chưa xử lý”.

Với các dịch vụ ngoài database, phải bổ sung chiến lược phù hợp:

| Chiến lược | Tác dụng | Giới hạn |
| --- | --- | --- |
| Idempotency key do downstream hỗ trợ | Downstream nhận ra yêu cầu trùng. | Phụ thuộc API, thời hạn lưu key và cách downstream định nghĩa retry. |
| Delivery log có trạng thái | Theo dõi `PENDING`, `SENT`, `FAILED` hoặc trạng thái tương tự. | Phải xử lý crash window giữa ghi trạng thái và gọi network. |
| Outbox/dispatcher cho tác vụ gửi | Quản lý một luồng gửi có persistence, retry và đối soát. | Dispatcher vẫn có thể giao trùng sau crash. |
| Đối soát với provider | Xác minh trạng thái thực tế khi kết quả gọi chưa rõ. | Phụ thuộc dữ liệu tra cứu mà provider cung cấp. |
| Chấp nhận at-least-once có kiểm soát | Không âm thầm bỏ tác vụ dù có khả năng trùng. | Trải nghiệm/đối soát phải chịu được duplicate. |

**Registry theo dõi publication, không thể thay thế hợp đồng idempotency của email provider hay một giao dịch phân tán với hệ thống bên ngoài.**

## 16. Sau commit và transaction riêng: vì sao quan trọng với registry?

Với `@ApplicationModuleListener`, tác vụ phản ứng chỉ hợp lệ sau khi nghiệp vụ gốc được commit, và listener hoạt động bất đồng bộ với transaction riêng.

~~~mermaid
sequenceDiagram
    autonumber
    participant API as Client
    participant O as OrderService
    participant DB as DB / T1
    participant R as Registry
    participant N as Notifications / T2

    API->>O: placeOrder
    O->>DB: INSERT order
    O->>R: Record publication (khi cấu hình)
    O->>DB: COMMIT T1
    R-->>N: Kích hoạt OrderPlaced sau commit
    N->>N: Gửi xác nhận / ghi nhận tác vụ
    alt Thành công
        N-->>R: Mark publication completed
    else Lỗi
        Note over R: Publication còn incomplete
    end
    O-->>API: orderId
~~~

Sơ đồ trình bày **ý nghĩa ranh giới**, không phải log trace chuẩn xác của từng lớp nội bộ; vị trí callback và completion thay đổi theo integration/version.

Điều cần phân biệt:

- **T1** là transaction tạo đơn hàng.
- **T2** là transaction cho phần xử lý listener, nếu listener được cấu hình như `@ApplicationModuleListener`.
- Registry theo dõi publication từ quá trình phát event; không có nghĩa T1 và T2 commit cùng nhau.
- Lỗi ở T2 **không rollback lại T1** đã commit.
- Nếu T2 cần đọc dữ liệu đã commit ở T1, độ nhất quán còn phụ thuộc datasource/replica và isolation; after-commit không tự mang snapshot của publisher.

Khi chỉ dùng `@TransactionalEventListener(AFTER_COMMIT)`, callback không mặc định tạo transaction mới cho các lệnh ghi DB. Nếu cần lưu dữ liệu trong một transaction tách biệt, có thể gọi service khác với `@Transactional(propagation = REQUIRES_NEW)` phù hợp. Không đánh đồng một callback after-commit với một transaction ghi DB tự động tồn tại.

## 17. Schema event và định danh listener ảnh hưởng recovery

Publication được lưu để phát lại có **vòng đời dài hơn một lần chạy của JVM**. Vì thế, một thay đổi code có thể làm mất khả năng xử lý các publication đã ghi.

Các rủi ro phổ biến:

- Rename package/class `OrderPlaced`.
- Thay kiểu `UUID` bằng `String` mà không có mapping.
- Thêm field bắt buộc không có dữ liệu trong payload cũ.
- Đổi tên bean/method listener khi backend sử dụng thông tin định danh listener để ánh xạ publication.
- Xóa listener trong khi vẫn có publication đang chờ dành cho nó.
- Đổi serializer mà không kiểm tra dữ liệu đã tồn tại.

Ví dụ thay đổi record:

~~~java
// Hợp đồng lúc publication được tạo:
public record OrderPlaced(UUID eventId, UUID orderId) {}

// Hợp đồng mới:
public record OrderPlaced(
        UUID eventId,
        UUID orderId,
        String currencyCode
) {}
~~~

Dù đã sửa toàn bộ source code để biên dịch, dữ liệu đã serialize có thể không có `currencyCode`. Không nên mặc định serializer sẽ tự đưa giá trị đúng hoặc record Java tự tương thích.

Một kế hoạch nâng cấp an toàn:

1. Kiểm tra publication chưa hoàn tất trước khi deploy.
2. Lưu fixture của payload cũ theo serializer thực tế.
3. Test deserialize và listener routing ở phiên bản mới.
4. Nếu breaking change, cân nhắc V1/V2 song hành, adapter hoặc migration.
5. Giữ định danh event ổn định trong cùng một publication được replay.
6. Theo dõi lỗi deserialize và publication không còn listener nhận sau triển khai.

Registry **có thể lưu dữ liệu để phục hồi**, nhưng khả năng đọc dữ liệu đó là nghĩa vụ thiết kế tương thích của ứng dụng.

## 18. Observability: registry cung cấp gì cho vận hành?

Để trả lời “đơn đã tạo nhưng chưa có email”, cần biết không chỉ event đã publish mà **publication của notifications đang ở trạng thái nào**.

Một tập tín hiệu hữu ích:

| Tín hiệu | Ý nghĩa |
| --- | --- |
| `eventType`, `eventId` | Xác định sự kiện cần theo dõi. |
| `orderId` | Liên hệ publication với dữ liệu nghiệp vụ. |
| `listenerId` / `consumerModule` | Xác định consumer nào còn chưa hoàn tất. |
| `publicationCreatedAt` | Tính tuổi publication. |
| `publicationCompletionAt` | Xác định thời điểm xử lý xong. |
| `incompletePublications` | Đếm công việc đang tồn. |
| `oldestIncompleteAge` | Phát hiện công việc kẹt lâu bất thường. |
| `retryAttempts`, `lastError` | Chẩn đoán lỗi lặp hoặc poison event khi ứng dụng có ghi nhận. |
| `executorQueueDepth` | Xác định nghẽn xử lý bất đồng bộ nếu có executor queue. |
| `deserializeFailures` | Phát hiện schema không tương thích sau deploy. |

Không phải mọi field trên đều được một registry backend mặc định lưu hoặc xuất dưới dạng metric. Một số phải do ứng dụng **tự bổ sung logging, tracing, metrics và quy trình đối soát**.

Ví dụ log do ứng dụng tự quy ước:

~~~text
event=OrderPlaced eventId=E-101 listener=notifications status=INCOMPLETE attempt=1 error=MAIL_TIMEOUT
event=OrderPlaced eventId=E-101 listener=loyalty status=COMPLETED attempt=1
event=OrderPlaced eventId=E-101 listener=notifications status=COMPLETED attempt=2
~~~

Đây là log **minh họa**, không phải format Spring Modulith mặc định.

**Không log toàn bộ event payload chứa thông tin cá nhân hoặc dữ liệu nhạy cảm** chỉ để gỡ lỗi. Khi publication được lưu lâu, cũng cần chính sách quyền truy cập, retention và xóa dữ liệu sau khi hoàn tất phù hợp yêu cầu hệ thống.

## 19. Cách điều tra một publication bị kẹt

Quy trình kiểm tra có thể đi từ nghiệp vụ đến registry rồi consumer:

~~~mermaid
flowchart TD
    A["Đơn đã commit, tác vụ phụ chưa xong"] --> B{"Publisher có publish event?"}
    B -->|"Không"| P["Sửa code path và đối soát nghiệp vụ"]
    B -->|"Có"| C{"Registry có publication cho listener?"}
    C -->|"Không"| D["Kiểm tra transaction, registry integration, listener discovery"]
    C -->|"Có"| E{"Publication đã completed?"}
    E -->|"Có"| F["Đối soát side effect/downstream"]
    E -->|"Không"| G["Xem lỗi consumer, schema và cơ chế recovery"]
    G --> H["Retry có kiểm soát + idempotency"]
    H --> I["Xác minh hoàn tất và xóa backlog"]
~~~

Các bước cụ thể:

1. **Xác nhận nghiệp vụ chính:** order đã commit hay transaction đã rollback?
2. **Xác minh publisher:** use case có tạo và publish event theo đúng điều kiện không?
3. **Xác minh listener:** bean đã được đăng ký, kiểu event và transaction phase có đúng không?
4. **Xác minh registry:** backend có đang lưu publication không, có mục của consumer cần tìm không?
5. **Xem trạng thái chưa hoàn tất:** có lỗi delivery, lỗi serializer, lỗi DB hay executor quá tải?
6. **Kiểm tra side effect thực tế:** email/provider hoặc điểm thưởng có thể đã hoàn tất dù registry chưa ghi completion.
7. **Quyết định replay:** bảo đảm idempotency và kiểm soát tải trước khi tái xử lý.
8. **Đối soát sau retry:** xác minh nghiệp vụ consumer đúng, publication hoàn tất, không có dữ liệu trùng.
9. **Sửa nguyên nhân gốc:** lỗi code publisher, sai transaction, thiếu registration, schema không tương thích hoặc chính sách retry chưa có.
10. **Bổ sung regression test:** ngăn tái diễn đúng failure window vừa gặp.

Đừng tạo **một event mới với `UUID.randomUUID()`** để thay thế bừa cho một publication tồn đọng. Nếu chỉ đang giao lại cùng sự thật nghiệp vụ, cần giữ danh tính event và xác định consumer nào thực sự chưa xử lý.

## 20. Kiểm thử Event Publication Registry ở các lớp

### 20.1. Publisher đã thực sự công bố event

Spring Modulith có hỗ trợ `@ApplicationModuleTest` và `PublishedEvents` để kiểm tra application events của module.

~~~java
package com.acme.shop.orders;

import com.acme.shop.orders.events.OrderPlaced;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.PublishedEvents;

import static org.assertj.core.api.Assertions.assertThat;

@ApplicationModuleTest
class OrdersModuleTest {

    @Autowired
    OrderService orders;

    @Test
    void publishesOrderPlaced(PublishedEvents published) {
        var command = TestOrders.validOrder(); // Fixture của dự án.
        UUID orderId = orders.placeOrder(command);

        assertThat(published.ofType(OrderPlaced.class)
                .matching(OrderPlaced::orderId, orderId))
                .hasSize(1);
    }
}
~~~

`OrderService` và `TestOrders` phải được import/định nghĩa phù hợp với project thật. Test này kiểm chứng **đã publish** nhưng **chưa chứng minh** publication có persistence hay listener đã hoàn tất.

### 20.2. Commit và rollback

Test transaction T1:

- Khi T1 commit, listener sau commit được kích hoạt và publication được theo dõi theo cấu hình.
- Khi T1 rollback, listener `AFTER_COMMIT` không được chạy.
- Nếu business data và publication cùng transaction, các thay đổi này rollback cùng nhau.

Trong Spring test framework, test có `@Transactional` thường rollback khi kết thúc. Nếu đang chờ listener after-commit trong khi transaction test còn mở, listener chưa có điều kiện chạy. Dùng transaction thật có commit rõ ràng hoặc `TestTransaction` phù hợp.

### 20.3. Listener lỗi sau khi đơn commit

Tạo một listener có chủ đích ném exception:

1. Tạo order, commit thành công.
2. Cho notifications lỗi.
3. Xác minh order vẫn tồn tại.
4. Kiểm tra registry còn publication notifications chưa hoàn tất.
5. Kích hoạt recovery theo cơ chế ứng dụng đã chọn.
6. Xác minh publication hoàn tất sau khi xử lý thành công.

Không nuốt exception trong listener và sau đó khẳng định đã test được behavior của registry khi lỗi.

### 20.4. Crash/restart với storage bền vững

Bài kiểm thử quan trọng nhất cho durability:

1. Khởi chạy ứng dụng với database và registry backend persistent.
2. Tạo order rồi cho listener bị chặn trước khi completion.
3. Xác nhận T1 đã commit và có publication chưa hoàn tất.
4. Dừng tiến trình kiểm thử tại failure window này.
5. Khởi động lại ứng dụng cùng database bền vững.
6. Kích hoạt recovery/republication theo cơ chế đã cấu hình.
7. Xác minh consumer xử lý thành công và publication được ghi hoàn tất.

Dùng môi trường test cách ly với production. Tránh kiểm thử crash bằng cách tắt hệ thống đang phục vụ người dùng.

### 20.5. Retry cùng eventId không được tạo side effect trùng

Cho consumer ghi điểm thành công nhưng giả lập việc completion chưa được lưu. Sau replay, kiểm tra ledger/số dư không tăng lần nữa. Với email hoặc API ngoài, kiểm thử chính sách idempotency, trạng thái chưa rõ và khả năng đối soát theo API thực tế.

### 20.6. Test nâng cấp version

Lưu fixture publication bằng serializer đang dùng ở phiên bản V1; kiểm tra phiên bản V2 có đọc lại, tìm đúng listener và hoàn tất hay không. Test với persistence thật có giá trị hơn việc chỉ deserialize một JSON viết tay nếu backend đang dùng định dạng khác.

## 21. So sánh registry với transactional outbox

Hai giải pháp có điểm chung là **giảm nguy cơ mất công việc sau commit**, nhưng có trọng tâm khác nhau.

| Tiêu chí | Event Publication Registry | Transactional outbox |
| --- | --- | --- |
| Đối tượng chính | Publication của application event đến transactional listener. | Thông điệp dự định được chuyển đi. |
| Gắn với consumer | Theo dõi publication đến các listener của Modulith. | Tùy thiết kế dispatcher/broker/consumer. |
| Tích hợp với module | Hỗ trợ mô hình event của Spring Modulith. | Thường dùng khi cần phát message ra hệ thống bên ngoài. |
| Persistence | Cần backend hỗ trợ và cấu hình transaction phù hợp. | Outbox record được commit cùng business record. |
| Khôi phục | Recovery/republication còn dang dở. | Dispatcher/CDC đọc outbox, retry truyền message. |
| Xử lý trùng | Consumer vẫn cần idempotency. | Consumer cũng cần idempotency vì dispatch có thể lặp. |

Ví dụ outbox thủ công ở mức ý tưởng:

~~~sql
BEGIN;

INSERT INTO orders(order_id, status)
VALUES (:orderId, 'CREATED');

INSERT INTO outbox_events(
    event_id, event_type, payload, created_at
) VALUES (
    :eventId, 'OrderPlaced', :payload, CURRENT_TIMESTAMP
);

COMMIT;
~~~

Một dispatcher đọc outbox sau commit, sau đó gửi đi theo phương tiện tích hợp được chọn. Nếu dispatcher gửi thành công nhưng dừng trước khi đánh dấu hoàn tất, message có thể được gửi lặp.

**Không phải ứng dụng nào cũng phải dùng cả registry lẫn outbox.** Chọn dựa trên consumer trong hay ngoài ứng dụng, yêu cầu durability, phương thức triển khai, transaction và vận hành. Nếu phối hợp nhiều lớp, cần nêu rõ từng lớp sở hữu tracking/acknowledgement nào để tránh phát trùng thiếu kiểm soát.

## 22. Những hiểu lầm thường gặp về vai trò registry

### 22.1. “Có registry thì không bao giờ mất event”

Sai. Publisher có thể không publish, storage có thể sai cấu hình, transaction có thể không nguyên tử, publication có thể bị purge hoặc không recovery. Registry giúp **theo dõi và hỗ trợ phục hồi**, không sửa được mọi lỗi.

### 22.2. “Mọi @EventListener đều tự có durable publication”

Không nên giả định. Registry gắn với cơ chế **transactional event publication**; listener đồng bộ thông thường không mặc nhiên được theo dõi như một publication bền vững.

### 22.3. “Tự động retry vô hạn với backoff”

Không có cơ sở để suy ra lịch retry, giới hạn và backoff chỉ từ việc có registry. Cần chọn cơ chế recovery phù hợp và cấu hình/kiểm chứng vận hành.

### 22.4. “Completed nghĩa email chắc chắn được gửi đúng một lần”

Không. Side effect network có thể thành công nhưng kết quả trả về bị timeout, hoặc listener có thể báo thành công không đúng. Cần idempotency và đối soát downstream.

### 22.5. “Nếu loyalty thất bại thì đơn hàng rollback”

Không đúng nếu transaction orders đã commit và loyalty xử lý sau commit trong transaction riêng. Một lỗi consumer cần được xử lý/recovery mà không hủy ngược đơn đã tồn tại.

### 22.6. “Chỉ cần đổi isolation sang SERIALIZABLE”

Isolation bảo vệ giao dịch dữ liệu đồng thời; nó **không làm event tự được lưu bền vững**, không tạo recovery và không giải quyết xử lý trùng.

### 22.7. “Publication đã lưu sẽ đọc được qua mọi lần nâng cấp”

Không mặc định. Serializer/schema, listener identity, package/class và migration là các ràng buộc tương thích.

### 22.8. “Registry tự thay cho broker hoặc hàng đợi phân tán”

Không. Nó phục vụ publication tracking của Spring Modulith, không mặc nhiên cung cấp consumer groups, partition, offset hoặc giao message xuyên tiến trình.

## 23. Checklist thiết kế và vận hành

| Câu hỏi | Điều cần xác nhận |
| --- | --- |
| Publisher có phát đúng sự thật nghiệp vụ? | Event chỉ được công bố ở nhánh tạo đơn hợp lệ. |
| Event phát trong transaction thật? | Kiểm tra `@Transactional`, Spring proxy và test commit/rollback. |
| Listener thuộc loại được tracking? | Chọn transactional listener/`@ApplicationModuleListener` phù hợp. |
| Registry có persistence? | Backend lưu trữ được cấu hình, không chỉ suy từ annotation. |
| Publication và business data có ranh giới commit phù hợp? | Kiểm tra datasource/transaction manager và failure window. |
| Có nhiều consumer nhận một event? | Theo dõi trạng thái hoàn tất theo từng listener. |
| Consumer có chịu được replay? | Idempotency theo event/consumer hoặc khóa nghiệp vụ đúng nghĩa. |
| Có recovery thực sự? | Cơ chế kích hoạt, lịch, số lần thử, backoff/giới hạn được xác minh. |
| Có cách xử lý lỗi vĩnh viễn? | Quarantine/manual remediation thay vì retry vô hạn. |
| Event còn đọc được sau deploy? | Test fixture từ phiên bản cũ và serializer thật. |
| Dữ liệu registry có nhạy cảm? | Quyền truy cập, retention, log và purge an toàn. |
| Có đủ observability? | Incomplete count/age, listener error, attempt, completion. |
| Có kiểm thử restart/crash? | Dùng database persistent và recovery thực tế. |
| Có quy trình đối soát? | So sánh event/consumer outcome với dữ liệu nghiệp vụ đã commit. |

## 24. Bài tập thực hành: một publication chưa hoàn tất

### Bối cảnh

Ứng dụng có ba module:

- `orders` tạo order và công bố `OrderPlaced(eventId, orderId, occurredAt)`.
- `notifications` nhận event để gửi email xác nhận.
- `loyalty` nhận cùng event để cộng điểm.

Yêu cầu: **đơn đã commit thì công việc hậu xử lý phải có dấu vết kiểm soát**, và khi phát lại publication không được nhân đôi side effect.

### Yêu cầu triển khai

1. Tạo record `OrderPlaced` bất biến có `eventId` ổn định và `customerId` cho nghiệp vụ cộng điểm.
2. Trong `OrderService.placeOrder`, dùng `@Transactional` để lưu order và publish event.
3. Đăng ký hai `@ApplicationModuleListener` trong notifications và loyalty, mỗi module tự sở hữu tác vụ.
4. Chọn persistence backend được Spring Modulith phiên bản đang dùng hỗ trợ; cấu hình registry và xác minh publication được lưu.
5. Khi orders commit, cho notifications thành công nhưng loyalty ném exception.
6. Kiểm tra trong registry: publication notifications hoàn tất, publication loyalty chưa hoàn tất theo cơ chế được cấu hình.
7. Kích hoạt recovery/republication dành cho publication loyalty và kiểm tra kết quả.
8. Tạo bảng ledger chống trùng theo `eventId` hoặc `(consumerName,eventId)`, bảo đảm không cộng điểm hai lần khi replay.
9. Giả lập crash/restart giữa lúc xử lý, giữ database bền vững qua lần chạy mới.
10. Thay schema event trong môi trường thử nghiệm để kiểm tra compatibility với publication cũ.
11. Thêm metric/log `eventId`, listener, trạng thái publication, tuổi backlog và lỗi gần nhất.
12. Đối soát từng consumer đã xử lý sự kiện theo nghiệp vụ, không chỉ nhìn mỗi trạng thái orders đã commit.

### Câu hỏi tự kiểm tra

- Vì sao một `OrderPlaced` có thể tạo nhiều publication?
- Publication completed và email delivered có cùng nghĩa trong mọi failure window không?
- Nếu publisher không từng gọi `publishEvent`, registry có thể tự dựng lại sự kiện ấy không?
- Khi tiến trình dừng sau khi loyalty cộng điểm nhưng trước khi ghi completion, cơ chế nào ngăn điểm bị cộng hai lần?
- Vì sao ghi business data ở database A, publication ở database B có thể làm mất tính nguyên tử?
- Nếu một phiên bản mới xóa listener cũ nhưng vẫn còn publication chờ, cần làm gì trước khi phát lại?
- Registry, transactional outbox và Kafka giải quyết những trách nhiệm nào khác nhau?

**Ghi nhớ:** **Event Publication Registry** giúp Spring Modulith **ghi nhận, theo dõi và hỗ trợ khôi phục việc giao application events tới từng transactional listener**. Khi có persistence và ranh giới transaction phù hợp, nó giảm nguy cơ một đơn đã commit nhưng tác vụ hậu xử lý âm thầm thất lạc. Tuy nhiên, độ tin cậy thực tế còn phụ thuộc publisher phát đúng sự kiện, consumer idempotent, schema tương thích, cơ chế recovery được vận hành, kiểm thử crash/restart và observability. Registry là nền tảng theo dõi publication — không phải broker, không phải distributed transaction và không tự bảo đảm exactly-once side effects.

