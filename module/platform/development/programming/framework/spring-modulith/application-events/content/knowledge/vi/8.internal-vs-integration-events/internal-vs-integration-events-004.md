# Internal event trong Spring Modulith

## 1. Internal event là gì?

**Internal event** là thông điệp mô tả một sự thật hoặc một biến cố xảy ra **bên trong ranh giới triển khai của ứng dụng**, để các thành phần hoặc application module trong cùng ứng dụng có thể phản ứng mà không phải gọi trực tiếp từng service nhận. Với Spring Modulith, cách thực hành phổ biến là phát event qua Spring `ApplicationEventPublisher` và đăng ký các listener phù hợp.

Ví dụ, module **Orders** xác nhận thành công một đơn hàng. Sau khi sự thay đổi này được lưu, module **Notifications** muốn lên lịch gửi email và module **Reporting** muốn cập nhật dữ liệu báo cáo. Orders có thể phát một `OrderConfirmed`; hai module còn lại nghe cùng sự kiện và xử lý trách nhiệm riêng.

Internal event giải quyết bài toán **giảm phụ thuộc giữa các module trong modular monolith**, phù hợp với mục tiêu của `SPRING_MODULITH_APPLICATION_EVENTS`: giữ ranh giới nghiệp vụ, tổ chức publisher/listener, xử lý sau commit và tăng độ tin cậy bằng publication registry, retry, kiểm thử cùng khả năng quan sát.

> **Điểm phân biệt:** “Internal” mô tả phạm vi sử dụng và vận chuyển của event. Nó không tự đồng nghĩa “private Java class”, “chỉ dùng trong một module” hoặc “chỉ có một listener”. Một internal event có thể nằm trong hợp đồng công khai giữa **nhiều module** cùng tiến trình, nhưng chưa được công bố ra hệ thống bên ngoài.

### Mục tiêu của bài học

Sau bài này, bạn có thể:

- Giải thích internal event, phạm vi của nó và vai trò trong kiến trúc Spring Modulith.
- Phân biệt internal event, command, state, domain event và integration event.
- Tổ chức event contract, publisher và consumer đúng ranh giới module.
- Hiểu sự khác nhau giữa listener đồng bộ, listener sau commit và listener bất đồng bộ.
- Thiết kế xử lý lỗi, publication registry, retry và idempotency phù hợp.
- Xác định khi nào internal event chưa đủ cho một yêu cầu tích hợp liên tiến trình.
- Viết những bài kiểm thử xác minh sự kiện, transaction và trạng thái ở module nhận.

## 2. Hai cấp độ “nội bộ” trong kiến trúc module

Thuật ngữ **internal event** có thể xuất hiện ở hai cấp độ:

| Phạm vi | Ví dụ | Hợp đồng cần bảo vệ |
| --- | --- | --- |
| **Bên trong một module** | Orders phát `OrderPricingCalculated` chỉ để một thành phần khác của Orders quan sát | Có thể là chi tiết implementation của Orders; không buộc module ngoài phải biết |
| **Giữa các module trong một ứng dụng** | Orders phát `OrderConfirmed` để Notifications và Reporting xử lý | Event cần nằm trong API được công bố của Orders; các consumer phụ thuộc vào tên, ngữ nghĩa và payload |
| **Ngoài ứng dụng** | Hệ thống xuất `OrderConfirmed` sang một dịch vụ khác qua broker | Khi đó có giao tiếp tích hợp; cần thêm contract truyền qua mạng, versioning và độ tin cậy liên hệ thống |

Điểm quan trọng là **module boundary** và **deployment boundary** không phải một. Trong modular monolith, các module Orders, Notifications và Reporting tách trách nhiệm và dependency ở cấp kiến trúc, nhưng cùng chạy trong một tiến trình JVM. Spring `ApplicationEventPublisher` có thể chuyển event trong Spring application context của tiến trình đó.

Một event được dùng giữa các module vẫn là **internal event của ứng dụng**, mặc dù nó cần có contract công khai ở ranh giới module. Sự “công khai” này là công khai cho **module khác trong ứng dụng**, không có nghĩa công khai cho dịch vụ bên ngoài.

~~~mermaid
flowchart LR
    subgraph App["Một ứng dụng Spring Modulith / JVM"]
        subgraph Orders["Module Orders"]
            A["Xác nhận đơn"] --> B["publish OrderConfirmed"]
        end
        B --> E(("Spring application events"))
        E --> C["Module Notifications"]
        E --> D["Module Reporting"]
    end
    X["Hệ thống ngoài JVM"]:::external
    E -.-|"Chưa tự truyền tới"| X
    classDef external fill:#f3f3f3,stroke:#888,color:#333
~~~

Sơ đồ event bus chỉ mang tính logic. Nó không ngụ ý `ApplicationEventPublisher` cung cấp message broker, disk queue hay kết nối mạng.

## 3. Internal event truyền tải điều gì?

Một event được thiết kế tốt ghi nhận **sự thật đã xảy ra**, không chỉ là lời yêu cầu thực hiện công việc.

| Khái niệm | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Command | `ConfirmOrder` | Yêu cầu xác nhận đơn; có thể bị từ chối |
| State | `Order.status = CONFIRMED` | Trạng thái hiện tại do Orders sở hữu |
| Internal event | `OrderConfirmed` | Orders công bố một lần xác nhận đơn thành công |
| Consumer action | `scheduleConfirmationEmail` | Notifications quyết định phải làm gì khi nhận event |
| Integration event | Thông điệp `OrderConfirmed` đã được chuyển sang hệ thống ngoài | Hợp đồng vận chuyển xuyên ranh giới ứng dụng, có thể dựa trên cùng sự thật nghiệp vụ |

Trong thực tế, `OrderConfirmed` có thể là **domain event** (vì mô tả sự thật nghiệp vụ), đồng thời được chuyển bằng **Spring application event** (vì đó là cơ chế truyền). Đây là hai chiều phân loại khác nhau: **ý nghĩa nghiệp vụ** và **cách truyền thông điệp**.

Internal event có thể là application event không thuần domain, ví dụ thông báo một bước xử lý nội bộ đã hoàn thành. Tuy nhiên, nếu event được dùng để giao tiếp giữa module, nên ưu tiên tên và ngữ nghĩa ổn định, không lệ thuộc vào ORM, service method hoặc transaction implementation.

### Tên event phải đủ chính xác

Nên dùng tên thể hiện kết quả:

- `OrderConfirmed` — đơn được Orders xác nhận thành công.
- `InvoiceIssued` — hóa đơn được phát hành thành công.
- `InventoryReserved` — tồn kho được giữ thành công.
- `PaymentCaptured` — cổng thanh toán xác nhận đã thu tiền ở bước capture.

Tránh dùng tên thiếu ngữ nghĩa như `DataChanged`, `OrderProcessed`, `SaveEntityEvent` hoặc tên command `SendEmailNow` khi ý định thật sự là công bố một biến cố nghiệp vụ.

Chọn tên theo thời điểm thực sự xảy ra. `PaymentAuthorized` khác `PaymentCaptured`, và cả hai không tự đồng nghĩa `PaymentSettled`. Nếu một HTTP call tới payment provider bị timeout, chưa thể khẳng định `PaymentFailed` chỉ từ việc không nhận được phản hồi.

## 4. Vì sao giao tiếp nội bộ bằng event làm giảm phụ thuộc?

Giả sử sau khi xác nhận đơn, Orders gọi trực tiếp:

~~~java
fulfillment.prepare(orderId);
notifications.scheduleConfirmation(orderId);
reporting.recordConfirmedOrder(orderId);
~~~

Ở cách này, Orders phải biết ít nhất ba service API và quyết định thứ tự gọi. Muốn thêm consumer Loyalty, người phát có thể phải sửa code. Nếu một lời gọi gặp lỗi, cần giải quyết rõ lỗi ảnh hưởng gì tới transaction chính.

Với internal event, Orders chỉ phát:

~~~java
events.publishEvent(new OrderConfirmed(eventId, orderId, occurredAt));
~~~

Các module nhận đăng ký listener. Orders không biết hoặc không import repository, service, bean của Notifications hay Reporting.

~~~mermaid
flowchart LR
    O["Orders"] -->|"OrderConfirmed"| E(("Internal event"))
    E --> N["Notifications"]
    E --> R["Reporting"]
    E --> L["Loyalty"]
~~~

**Giảm phụ thuộc không có nghĩa không còn phụ thuộc.** Mọi consumer của `OrderConfirmed` vẫn phụ thuộc vào public event contract của Orders. Khi thêm field, đổi tên, đổi điều kiện phát hoặc thay ngữ nghĩa, publisher phải coi đó là thay đổi API.

Cũng không có bảo đảm rằng internal event luôn tốt hơn một method call. Nếu Orders cần kết quả kiểm tra tồn kho **trước khi quyết định có xác nhận đơn**, một lời gọi đồng bộ tới public API của Inventory có thể phù hợp hơn. Internal event xử lý rất tốt những phản ứng độc lập mà nghiệp vụ chấp nhận thực hiện sau khi sự thật chính đã được commit.

## 5. Thiết kế package và quyền sở hữu event contract

Ví dụ ứng dụng có package gốc `com.acme.shop`:

~~~text
com.acme.shop
├── ShopApplication.java
├── orders
│   ├── OrderConfirmed.java             # contract công khai
│   └── internal
│       ├── Order.java
│       ├── OrderRepository.java
│       └── OrderApplicationService.java
├── notifications
│   └── internal
│       ├── OrderConfirmedListener.java
│       └── NotificationService.java
└── reporting
    └── internal
        └── OrderProjectionService.java
~~~

Với mô hình phát hiện module mặc định của Spring Modulith, package con trực tiếp dưới package gốc thường biểu diễn application module. Các type thuộc package gốc của module được dùng như API công khai theo quy ước; package `internal` nằm trong chi tiết implementation.

Ở ví dụ trên, Notifications import `com.acme.shop.orders.OrderConfirmed` là hợp lệ theo ranh giới thiết kế, còn import `com.acme.shop.orders.internal.OrderRepository` là không phù hợp. Notifications có thể xây state riêng của mình nhưng không sở hữu entity và repository của Orders.

### Khi muốn dùng package `orders.events`

Nếu đưa event vào subpackage `com.acme.shop.orders.events`, hãy kiểm tra cách công bố API. Có thể đánh dấu package này bằng Spring Modulith `@NamedInterface`:

~~~java
@org.springframework.modulith.NamedInterface("events")
package com.acme.shop.orders.events;
~~~

Khi đó đây là một named interface có thể được module khác sử dụng theo quy tắc phụ thuộc được cấu hình. Không nên mặc định mọi subpackage đều công khai.

**Chủ sở hữu contract** phải rõ: event của Orders do Orders định nghĩa và bảo đảm điều kiện phát; Notifications nhận sự kiện rồi làm việc trong phạm vi quyền sở hữu của Notifications.

## 6. Tạo internal event bất biến

Một event Java có thể dùng `record` để truyền dữ liệu giá trị:

~~~java
package com.acme.shop.orders;

import java.time.Instant;
import java.util.UUID;

public record OrderConfirmed(
        UUID eventId,
        UUID orderId,
        Instant occurredAt
) {}
~~~

Ở đây:

- `eventId` là định danh **một lần xảy ra sự kiện**. Khi hệ thống thử giao lại cùng publication, ID này phải giữ nguyên.
- `orderId` là định danh aggregate nguồn. Một đơn có thể phát nhiều loại event theo vòng đời.
- `occurredAt` là thời điểm sự kiện xảy ra theo publisher; không đồng nghĩa thời điểm listener nhận và không tự bảo đảm ordering giữa các luồng.

Event không nên chứa entity JPA, `EntityManager`, service bean hoặc một object mutable có thể thay đổi khi consumer sử dụng. Đặc biệt, việc gửi entity có quan hệ lazy có thể tạo lỗi khi listener xử lý sau transaction hoặc rò rỉ dữ liệu nội bộ của publisher.

Payload nên đủ để consumer thực hiện trách nhiệm cần thiết mà không phá ranh giới module. Nếu Notifications cần ngôn ngữ nhận email hoặc thông tin tại thời điểm xác nhận, có thể cân nhắc công bố một snapshot tối thiểu phù hợp chính sách dữ liệu. Nếu consumer cần *trạng thái mới nhất*, nên xác định public query API hoặc cơ chế đồng bộ phù hợp; event lịch sử không phải bản sao luôn cập nhật của entity.

### Event là một contract, không phải một object chung có thể sửa

Không đặt setter để listener A sửa event rồi listener B nhìn thấy dữ liệu đã sửa. Mỗi listener nhận cùng một sự thật và tự quản lý state của mình. Các trường kiểu `UUID`, `Instant` và value object bất biến giúp dễ giữ hợp đồng này.

## 7. Publisher: phát event khi sự thật nghiệp vụ xảy ra

Ví dụ module Orders xác nhận đơn:

~~~java
package com.acme.shop.orders.internal;

import com.acme.shop.orders.OrderConfirmed;
import java.time.Clock;
import java.time.Instant;
import java.util.UUID;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderApplicationService {

    private final OrderRepository repository;
    private final ApplicationEventPublisher events;
    private final Clock clock;

    public OrderApplicationService(
            OrderRepository repository,
            ApplicationEventPublisher events,
            Clock clock
    ) {
        this.repository = repository;
        this.events = events;
        this.clock = clock;
    }

    @Transactional
    public void confirm(UUID orderId) {
        Order order = repository.findById(orderId)
                .orElseThrow(() -> new IllegalArgumentException("Order not found"));

        if (order.isConfirmed()) {
            return; // Lệnh lặp không sinh một lần xác nhận mới.
        }

        order.confirm(); // Domain kiểm tra tính hợp lệ của chuyển trạng thái.
        repository.save(order);

        events.publishEvent(new OrderConfirmed(
                UUID.randomUUID(),
                order.getId(),
                Instant.now(clock)
        ));
    }
}
~~~

Đoạn code giả định `Order`, `OrderRepository` và bean `Clock` đã được định nghĩa. Đây là ví dụ về thứ tự nghiệp vụ, không phải một ứng dụng hoàn chỉnh.

Ba điều bắt buộc về mặt thiết kế:

1. **State transition phải hợp lệ:** `Order.confirm()` kiểm tra điều kiện, không phát `OrderConfirmed` khi xác nhận bị từ chối.
2. **Publisher không điều khiển consumer:** Orders không import hoặc gọi `NotificationService` hay `ReportingService`.
3. **Không bỏ qua concurrency:** kiểm tra `isConfirmed()` không đủ ngăn hai request đồng thời cùng tạo event. Có thể cần optimistic locking `@Version`, biện pháp đồng bộ hoặc database constraint theo quy tắc nghiệp vụ.

### Event được phát trước hay sau commit?

Trong ví dụ, `publishEvent(...)` được gọi **trong transaction** của `confirm`. Việc gọi publisher không tự chứng minh database đã commit. Nó đặt event vào cơ chế phân phối của Spring; hành vi của listener phụ thuộc vào annotation và cách cấu hình event multicaster.

Nếu transaction rollback sau khi gọi `publishEvent(...)`, sự thật `OrderConfirmed` chưa được xác nhận bền vững. Những consumer phải dựa trên state đã commit nên dùng transactional listener phù hợp thay vì thực hiện side effect ngay trước commit.

## 8. Listener nội bộ: đồng bộ và sau commit

Spring hỗ trợ nhiều cách đăng ký listener. Sự khác biệt ảnh hưởng trực tiếp đến transaction, lỗi và tính nhất quán.

| Cách lắng nghe | Thời điểm điển hình | Transaction và lỗi |
| --- | --- | --- |
| `@EventListener` | Mặc định chạy đồng bộ ngay khi publish, nếu multicaster không được cấu hình executor khác | Có thể chạy trong transaction publisher; exception có thể truyền ngược tới caller |
| `@TransactionalEventListener` | Mặc định ở phase `AFTER_COMMIT` của transaction đang hoạt động | Chỉ kích hoạt sau commit; bản thân annotation không tự tạo async hoặc transaction ghi mới |
| `@Async` cùng transactional listener | Lập lịch callback trên executor bất đồng bộ khi async support được bật | Lỗi không còn truyền như lỗi đồng bộ cho transaction nguồn; cần giám sát và xử lý |
| `@ApplicationModuleListener` của Spring Modulith | Tiện ích cho listener sau commit, bất đồng bộ và transaction riêng | Phù hợp cho các side effect liên module độc lập với commit của publisher |

`@ApplicationModuleListener` kết hợp ngữ nghĩa của `@Async`, `@TransactionalEventListener` và `@Transactional(propagation = REQUIRES_NEW)`. Cần chuẩn bị cấu hình async execution phù hợp và hiểu rõ ranh giới transaction của listener, đặc biệt khi ứng dụng có tải cao.

Một `@TransactionalEventListener` mặc định không được gọi nếu lúc phát không có transaction phù hợp; `fallbackExecution` là một lựa chọn cấu hình riêng khi muốn xử lý cả trường hợp không có transaction.

### Ví dụ consumer của Notifications

~~~java
package com.acme.shop.notifications.internal;

import com.acme.shop.orders.OrderConfirmed;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
public class OrderConfirmedListener {

    private final NotificationService notifications;

    public OrderConfirmedListener(NotificationService notifications) {
        this.notifications = notifications;
    }

    @ApplicationModuleListener
    public void on(OrderConfirmed event) {
        notifications.scheduleConfirmationIfAbsent(
                event.orderId(),
                event.eventId()
        );
    }
}
~~~

`scheduleConfirmationIfAbsent` là phương thức nghiệp vụ minh họa do Notifications triển khai. Nó nên lưu trạng thái yêu cầu gửi theo transaction của module nhận, kiểm tra duplicate và có database constraint phù hợp.

**Đặt đúng trách nhiệm:** listener này có thể lên lịch thông báo, nhưng không được xác nhận đơn thay Orders. Nếu gửi email thất bại, Orders vẫn có thể đã hoàn tất `CONFIRMED`. Hai state thuộc hai module khác nhau.

## 9. Luồng event và ranh giới transaction

~~~mermaid
sequenceDiagram
    autonumber
    actor Client
    participant O as Orders
    participant DB as Database
    participant E as ApplicationEventPublisher
    participant N as Notifications
    participant R as Reporting
    Client->>O: confirm(orderId)
    O->>DB: Order -> CONFIRMED (trong TX Orders)
    O->>E: publish OrderConfirmed
    O->>DB: COMMIT
    E-->>N: Listener AFTER_COMMIT
    E-->>R: Listener AFTER_COMMIT
    N->>N: schedule email (transaction riêng)
    R->>R: update projection (transaction riêng)
~~~

Sơ đồ trên mô tả mô hình khi listener được cấu hình chạy **sau commit**, ví dụ với `@ApplicationModuleListener`. Nó không mô tả hành vi mặc định của tất cả `@EventListener`.

Các tình huống cần phân biệt:

- **Orders rollback:** `Order.status` không trở thành `CONFIRMED` trong DB; listener `AFTER_COMMIT` không xử lý một lần xác nhận bị rollback.
- **Orders commit, cả hai consumer thành công:** state của Orders, Notifications và Reporting cuối cùng hội tụ theo các quy tắc riêng.
- **Orders commit, Notifications lỗi:** trạng thái Orders không tự rollback. Reporting vẫn có thể hoàn thành, còn Notifications phải có cơ chế khôi phục.
- **Event lặp:** cùng `OrderConfirmed` có thể được giao lại; Notifications phải idempotent.
- **Listener chạy muộn:** trong khoảng giữa commit và xử lý, Orders đã xác nhận nhưng Notifications vẫn chưa tạo yêu cầu gửi. Đây có thể là trạng thái eventual consistency hợp lệ.

Vì thế, một trang quản trị có thể phải hiển thị “Đơn đã xác nhận; thông báo đang xử lý” và cung cấp cách quan sát lỗi giao event. Không nên suy ra tất cả module đã cập nhật xong ngay khi phương thức `publishEvent` trả về.

## 10. Độ tin cậy của internal event: publication registry

Spring `ApplicationEventPublisher` làm việc trong Spring application context. Trong cấu hình đơn giản, cơ chế phát event không mặc nhiên tạo một message queue bền vững. Nếu JVM dừng sau commit nhưng trước khi listener hoàn tất, có rủi ro bỏ lỡ side effect nếu không có cơ chế ghi nhận và khôi phục publication.

Spring Modulith cung cấp **Event Publication Registry** để theo dõi việc phát event tới các **transactional event listener**, khi ứng dụng đã cấu hình một backend lưu trữ publication phù hợp.

Ở mức khái niệm, registry hỗ trợ:

1. Ghi nhận publication cần được listener xử lý.
2. Theo dõi listener nào đã hoàn thành và publication nào còn dang dở.
3. Đánh dấu publication hoàn thành khi việc xử lý đạt điều kiện tương ứng.
4. Hỗ trợ cơ chế xử lý lại publication chưa hoàn thành, theo cấu hình và phiên bản thư viện.

~~~mermaid
flowchart TD
    A["Orders phát OrderConfirmed"] --> B["Publication được theo dõi"]
    B --> C["Transaction Orders commit"]
    C --> D{"Listener xử lý thành công?"}
    D -->|Có| E["Đánh dấu publication completed"]
    D -->|Không| F["Publication chưa hoàn thành"]
    F --> G["Theo dõi và khôi phục / republish"]
    G --> D
~~~

Khi bảo đảm tính bền vững, cần triển khai lưu trữ publication theo loại database và cách cấu hình Spring Modulith đang dùng; các thư viện hỗ trợ JDBC/JPA hoặc lựa chọn khác phụ thuộc phiên bản. Cần chuẩn bị schema/migration và vận hành khôi phục publication chưa hoàn thành.

**Registry không tự biến internal event thành integration event**, cũng không tự bảo đảm giao **exactly-once**. Việc khôi phục publication có thể khiến listener nhận lại event sau khi nó đã ghi dữ liệu của mình; vì vậy **idempotency luôn là trách nhiệm thiết kế quan trọng của consumer**.

### Retry và thất bại không đồng nghĩa phải phát event nghiệp vụ mới

Nếu Notifications thất bại khi gửi email, không cần tạo `OrderConfirmedRetry` từ Orders. Có thể xử lý lại publication `OrderConfirmed` hiện có, hoặc retry tác vụ gửi ở module Notifications theo chính sách được định nghĩa. Khi giao lại chính event đó, giữ `eventId` để nhận biết duplicate.

Một exception do dữ liệu sai quy tắc không nên được retry vô hạn như lỗi timeout. Hệ thống cần phân loại nguyên nhân thất bại, cơ chế backoff/giới hạn, logging và quy trình khắc phục thủ công hoặc tự động tương ứng.

## 11. Idempotency và sự kiện đến trễ

Giả sử ứng dụng bị dừng sau khi Notifications đã commit bản ghi gửi email nhưng trước khi publication được đánh dấu hoàn thành. Khi phục hồi, Notifications có thể xử lý lại `OrderConfirmed`.

Consumer không nên thực thi logic kiểu:

~~~java
public void on(OrderConfirmed event) {
    notifications.insertNewEmailJob(event.orderId());
}
~~~

nếu hành động này mỗi lần đều sinh một job mới. Thay vào đó, việc lập lịch phải idempotent theo `eventId` hoặc một **business key** hợp lệ. Ví dụ, nếu mỗi Order chỉ có một email xác nhận đơn:

~~~text
notification_job
-------------------------------------
id | order_id | event_id | status
-------------------------------------
1  | A        | E1       | PENDING

UNIQUE(order_id, notification_type)
~~~

Cơ chế kiểm tra “nếu chưa tồn tại thì tạo” trong Java cần được bổ sung unique constraint hoặc phương pháp concurrency phù hợp tại database. Nếu dùng bảng `processed_events`, thao tác ghi dấu event và cập nhật state phải nằm trong **cùng transaction** của consumer để tránh đánh dấu thành công khi tác vụ chưa thực sự commit.

Với side effect ngoài database như email hoặc API nhà vận chuyển, DB transaction không thể rollback một email đã gửi. Cần idempotency key từ nhà cung cấp, durable job/outbox hoặc quy tắc nghiệp vụ chấp nhận và phát hiện gửi lặp.

### Event đến muộn vẫn là sự thật lịch sử

Ví dụ:

~~~text
T1: OrderConfirmed(orderId = A)
T2: OrderCancelled(orderId = A)
T3: Notifications được giao lại OrderConfirmed của T1
~~~

Ở T3, điều “Order từng được xác nhận” vẫn đúng nhưng không có nghĩa Order **đang** xác nhận. Nếu chính sách không gửi thông báo xác nhận sau hủy, Notifications phải kiểm tra quy tắc thông qua state đã biết, version hoặc public query API thích hợp.

`occurredAt` hữu ích để truy vết nhưng không bảo đảm thứ tự toàn cục. Nếu consumer xây projection cần bảo toàn thứ tự theo aggregate, hãy xem xét `aggregateVersion`, state transition guard hoặc cơ chế đồng bộ lại dữ liệu.

## 12. Internal event khác integration event thế nào?

Mặc dù cả hai có thể mô tả cùng sự thật, **đích đến, hợp đồng và vận hành** của chúng khác nhau.

| Tiêu chí | Internal event | Integration event |
| --- | --- | --- |
| **Phạm vi** | Thành phần/module trong cùng ứng dụng | Consumer ở ngoài ứng dụng, thường khác tiến trình |
| **Vận chuyển thông dụng** | Spring event infrastructure trong JVM | Broker, queue, HTTP/webhook hoặc hạ tầng integration |
| **Payload** | Java object theo event contract nội bộ | Cần representation/serialization và schema tương thích giữa hệ thống |
| **API** | Public API của module nếu nhiều module cùng sử dụng | Hợp đồng tích hợp được version và công bố cho consumer ngoài |
| **Transaction** | Có thể liên kết transaction publisher và listener sau commit | Không có transaction database chung xuyên hệ thống theo mặc định |
| **Độ bền / retry** | Phụ thuộc listener và cấu hình publication registry | Phụ thuộc broker, outbox, consumer offset/ack và cơ chế khôi phục |
| **Bảo mật** | Chia sẻ theo phạm vi ứng dụng và ranh giới module | Cần tính thêm authentication, authorization, secret, network exposure |
| **Sự tiến hóa** | Các module có thể được triển khai cùng bản ứng dụng | Hệ thống ngoài có vòng đời triển khai riêng; yêu cầu tương thích lâu hơn |

**Ví dụ:** Orders phát internal `OrderConfirmed`. Notifications trong cùng ứng dụng nghe event để lên lịch email. Một hệ thống CRM ngoài ứng dụng cũng cần biết đơn đã được xác nhận; khi đó cần xuất thông điệp integration qua broker/API và một contract phù hợp. Phương thức `ApplicationEventPublisher.publishEvent(...)` tự thân chưa gửi gì tới CRM.

Spring Modulith có các cơ chế **event externalization** khi cần tích hợp ra broker; đó là một quyết định kiến trúc và cấu hình riêng, không phải thuộc tính mặc định của mọi internal event. Có thể mapping một internal domain event sang một integration event riêng để kiểm soát schema, dữ liệu nhạy cảm, tính ổn định và ý nghĩa công bố.

### Không phải internal event nào cũng nên externalize

Một event như `OrderPriceCacheInvalidated` có thể hữu ích cho cache nội bộ nhưng không có ý nghĩa cho CRM. Ngược lại, `OrderConfirmed` có thể là thông tin có ích với đối tác ngoài; cần đánh giá dữ liệu được phép xuất, hợp đồng versioning, yêu cầu bảo mật và độ bền giao.

Không nên dùng một payload nội bộ giàu chi tiết ORM làm hợp đồng công khai qua broker. Cần tách lớp transport nếu vòng đời tích hợp và quyền sở hữu schema đòi hỏi.

## 13. Khi nào nên chọn internal event?

Có thể dùng bảng quyết định sau trong thiết kế module:

| Tình huống | Gợi ý | Vì sao |
| --- | --- | --- |
| Orders cần kiểm tra hạn mức trước khi xác nhận | Gọi public API đồng bộ của module sở hữu hạn mức | Kết quả là điều kiện bắt buộc của transaction hiện tại |
| Orders đã xác nhận, Notifications cần gửi email | Internal event sau commit | Công việc độc lập, có thể xử lý trễ hoặc retry |
| Reporting cần cập nhật projection khi đơn xác nhận | Internal event sau commit | Giảm phụ thuộc và chấp nhận eventual consistency |
| Một component nội bộ muốn ghi metrics không quyết định nghiệp vụ | Internal listener hoặc instrumentation phù hợp | Không cần làm thay đổi API nghiệp vụ cho mọi module |
| Dịch vụ CRM ngoài ứng dụng cần biết đơn đã xác nhận | Integration event / externalization | Phải vượt deployment boundary |
| Tác vụ phải chạy đúng một lần tuyệt đối ở hệ thống bên ngoài | Thiết kế idempotency/protocol và reconciliation | Event bus đơn lẻ không bảo đảm exactly-once side effect |
| Nhiều bước bắt buộc cùng thành công mới được trả kết quả | Phối hợp đồng bộ hoặc workflow/compensation rõ ràng | Event bất đồng bộ không tự cung cấp invariant tức thời |

Nguyên tắc thực tế: trước tiên hãy xác định **ràng buộc nhất quán** của use case. Sau đó mới chọn truyền qua event hay API đồng bộ. Nếu một bước bắt buộc hoàn thành ngay trước khi xác nhận giao dịch chính, chỉ thêm listener sau commit có thể khiến hệ thống báo thành công quá sớm.

## 14. Kiểm thử internal event trong Spring Modulith

Một bài test tốt cần chứng minh:

1. Publisher chỉ tạo event khi sự thật nghiệp vụ thực sự xảy ra.
2. Event contract nằm ở API module hợp lệ.
3. Listener nhận event và xử lý state thuộc module mình.
4. Rollback, duplicate, exception và retry không làm hỏng nghiệp vụ.
5. Xử lý sau commit có thể hoàn thành trong thời gian chấp nhận được.

### 14.1. Kiểm tra ranh giới module

Spring Modulith cho phép xác minh dependency giữa các module:

~~~java
import com.acme.shop.ShopApplication;
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleArchitectureTest {

    @Test
    void noIllegalDependencies() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Kiểm tra này giúp phát hiện những vi phạm phụ thuộc và ranh giới mà `ApplicationModules` có thể phân tích, nhưng không chứng minh hành vi xử lý event đúng.

### 14.2. Kiểm tra publisher

Trong bài test module Orders, cần kiểm tra:

- `confirm(orderId)` thành công cập nhật state và publish `OrderConfirmed` có `orderId` đúng.
- `confirm(orderId)` bị từ chối không phát event “đã xác nhận”.
- Lời gọi lặp không tạo một sự kiện nghiệp vụ mới nếu không có state transition.
- Một transaction bị rollback không dẫn đến listener `AFTER_COMMIT` xử lý như đã commit.

Có thể dùng `@ApplicationModuleTest` và tiện ích kiểm tra event đã publish của Spring Modulith theo API phiên bản đang dùng. Khi kiểm tra after-commit, bảo đảm test có transaction thực sự commit; test mặc định mở transaction rồi rollback có thể khiến callback sau commit không chạy.

### 14.3. Kiểm tra listener và vận hành

| Trường hợp | Điều cần xác minh |
| --- | --- |
| `OrderConfirmed` lần đầu | Notifications tạo đúng một job gửi có trạng thái hợp lệ |
| Nhận lại cùng `eventId` | Không nhân đôi job |
| Notifications lỗi tạm thời | Có dấu vết publication chưa hoàn thành khi registry được cấu hình |
| Publication được xử lý lại | Job không trùng và publication hoàn thành theo hệ thống theo dõi |
| Orders đã hủy trước khi event cũ được xử lý | Listener không tạo side effect trái chính sách của Notifications |
| Reporting lỗi nhưng Notifications thành công | Lỗi của Reporting không tự đảo transaction đã commit của Orders |

Với listener bất đồng bộ, **đợi một điều kiện kết thúc với timeout hữu hạn** thay vì dùng `Thread.sleep(...)` cố định. Nếu cần mô phỏng sự cố process restart, phải dùng bài kiểm thử tích hợp phù hợp với backend registry; unit test không thể tự chứng minh độ bền qua việc JVM dừng đột ngột.

### 14.4. Quan sát nội bộ

Cần ghi nhận những thông tin như `eventId`, `eventType`, `aggregateId`, `listener`, `publicationStatus` và độ trễ từ commit tới xử lý. Theo dõi số publication chưa hoàn thành, tuổi của chúng, lỗi theo listener và tốc độ xử lý để phát hiện trục trặc sớm.

Không log toàn bộ payload chứa dữ liệu cá nhân hoặc bí mật nghiệp vụ. Nếu có retry, log nên nối được các lần thử bằng cùng event ID và correlation ID, giúp điều tra mà không tạo các event “Retry” nghiệp vụ mới.

## 15. Bài thực hành từ giao tiếp trực tiếp sang internal event

Giả sử ban đầu Orders gọi Notifications sau khi xác nhận:

~~~java
@Transactional
public void confirmOrder(UUID id) {
    orders.confirm(id);
    notifications.sendConfirmation(id);
}
~~~

Hãy refactor phần thông báo được phép thực hiện sau commit:

1. Định nghĩa public event `OrderConfirmed(eventId, orderId, occurredAt)` trong Orders.
2. Cho application service Orders cập nhật state rồi gọi `ApplicationEventPublisher.publishEvent(...)`.
3. Cho Notifications đăng ký `@ApplicationModuleListener` và tạo job gửi email theo `eventId`/business key.
4. Bổ sung unique constraint để hai lần giao cùng event không tạo hai job.
5. Nếu yêu cầu độ tin cậy sau restart, cấu hình publication registry và cơ chế phát lại publication chưa hoàn thành phù hợp.
6. Viết test cho thành công, rollback, listener thất bại và nhận trùng.
7. Quan sát độ trễ và xác định cách UI hiển thị state trung gian.

**Thử trả lời các câu hỏi:**

- Vì sao `OrderConfirmed` là internal event dù Notifications thuộc một module khác?
- Vì sao `ApplicationEventPublisher` tự thân không đủ để gửi thông điệp tới Kafka hoặc hệ thống CRM ngoài ứng dụng?
- Nếu Orders rollback thì listener sau commit có được xử lý không?
- Khi listener đã commit job gửi email nhưng bị crash trước khi registry đánh dấu hoàn thành, điều gì xảy ra khi redelivery?
- Nếu nghiệp vụ bắt buộc tồn kho phải được giữ *trước* khi Orders xác nhận, có nên chỉ dùng internal event bất đồng bộ?

## 16. Tổng kết

**Internal event** là phương tiện giao tiếp trong ranh giới ứng dụng, giúp module công bố sự thật nghiệp vụ mà không cần biết các consumer cụ thể. Trong Spring Modulith, một event có thể được dùng giữa nhiều module trong cùng JVM và vẫn là internal event; vì vậy contract phải nằm ở API module thích hợp và được bảo vệ về tên, ý nghĩa, payload.

Khi triển khai, cần phân biệt việc **publish trong transaction** và **xử lý sau commit**, cũng như chấp nhận eventual consistency giữa các module. `@ApplicationModuleListener` hỗ trợ listener sau commit, bất đồng bộ và transaction riêng. Event Publication Registry và retry hỗ trợ phục hồi publication khi cấu hình lưu trữ phù hợp, nhưng consumer vẫn phải idempotent và quan sát được lỗi.

Khi có yêu cầu truyền sang tiến trình hoặc hệ thống khác, cần thiết kế **integration event** hoặc cơ chế externalization riêng. Giữ ranh giới này rõ ràng giúp kiến trúc Spring Modulith vừa giảm phụ thuộc nội bộ vừa tránh nhầm lẫn về độ bền, transaction và bảo đảm giao sự kiện.
