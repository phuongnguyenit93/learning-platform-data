# Named interface

Trong Spring Modulith, một **module ứng dụng** không chỉ là nhóm package cùng tên. Nó là một ranh giới sở hữu nghiệp vụ: module khác chỉ nên dùng những kiểu dữ liệu và hành vi được công bố có chủ ý. Nhưng điều gì xảy ra khi một module `orders` muốn đặt hợp đồng sự kiện `OrderPaid` trong package con `orders.events` để các module `loyalty` và `notifications` lắng nghe?

Theo quy ước module mặc định của Spring Modulith, các kiểu ở **package gốc của module** thuộc API công khai mặc định, còn các kiểu trong package con được xem là nội bộ, trừ khi được công bố theo cơ chế thích hợp. Đặt một Java `public record` vào `orders.events` **chưa đủ** để biến nó thành API được phép sử dụng xuyên module theo kiểm tra kiến trúc Spring Modulith.

**Named interface** giải quyết chính bài toán này: đặt tên cho một **phần API công khai** của module, cho phép công bố chính xác các kiểu cần dùng ở package con mà vẫn giữ phần triển khai khác ở phía sau ranh giới. Trong mô-đun học **SPRING_MODULITH_APPLICATION_EVENTS**, đây là công cụ quan trọng để công bố *event contract* cho publisher và listener mà không kéo theo phụ thuộc vào repository, entity hay service nội bộ.

Sau bài này, bạn cần thực hiện được bốn việc: xác định package nào là API mặc định; định nghĩa một named interface qua `@NamedInterface`; ràng buộc module consumer bằng `@ApplicationModule(allowedDependencies = ...)`; và kiểm chứng ranh giới bằng `ApplicationModules.verify()`.

## 1. Vấn đề: một event được public trong Java vẫn có thể là nội bộ module

Xét ứng dụng modular monolith với các module:

- **orders** ghi nhận đơn hàng và phát `OrderPaid` khi trạng thái thanh toán được xác nhận;
- **loyalty** nhận `OrderPaid` để cộng điểm cho khách;
- **notifications** nhận `OrderPaid` để tạo yêu cầu gửi thông báo.

Thiết kế ban đầu có thể như sau:

~~~text
com.example.shop
├── ShopApplication.java
├── orders
│   ├── OrderService.java
│   ├── events
│   │   └── OrderPaid.java
│   └── internal
│       ├── OrderEntity.java
│       └── OrderRepository.java
├── loyalty
│   └── LoyaltyOnOrderPaid.java
└── notifications
    └── NotifyOnOrderPaid.java
~~~

Cả `OrderPaid` và `OrderEntity` có thể được khai báo `public` theo cú pháp Java. Tuy nhiên, quyền truy cập của Java và **quy tắc API module** là hai tầng khác nhau.

| Góc nhìn | Điều nó kiểm tra | Giới hạn |
| --- | --- | --- |
| **Java `public`** | Có thể tham chiếu kiểu giữa những package nhìn thấy nhau trên classpath | Không tự phân biệt loại phụ thuộc nào phù hợp kiến trúc |
| **API của application module** | Module nào được phép sử dụng kiểu nào của module khác | Cần công bố bề mặt API và chạy kiểm tra kiến trúc |
| **Named interface** | Một tập kiểu công khai có tên nằm trong module | Không tự tạo mạng, message broker hoặc transaction |
| **`allowedDependencies`** | Những module hoặc named interface mà module hiện tại được phép phụ thuộc | Không thay thế cho kiểm thử transaction và nghiệp vụ |

Theo cách phát hiện module thông thường, `orders` là package gốc module. Các kiểu `public` trong package `com.example.shop.orders` nằm trên **unnamed/default interface** của module. Các subpackage như `orders.events` và `orders.internal` không mặc nhiên là bề mặt API cho module khác.

Nếu `loyalty` import `com.example.shop.orders.events.OrderPaid` khi package này chưa được công bố, Java có thể biên dịch được nhưng phép kiểm tra cấu trúc Spring Modulith có thể báo rằng module đang truy cập vào một package nội bộ. Đổi event về package gốc là một cách, nhưng sẽ kém thuận tiện nếu module muốn tổ chức nhiều hợp đồng sự kiện trong `events`, `api`, `spi`... Named interface cho phép giữ cấu trúc rõ ràng hơn.

## 2. Named interface là gì?

**Named interface** là một *bề mặt công khai có tên* thuộc một application module. Nó mô tả một tập kiểu mà module khác được phép sử dụng. Tên của interface giúp phụ thuộc trở nên cụ thể hơn: `loyalty` không cần quyền sử dụng mọi API của `orders`, mà chỉ cần tập hợp hợp đồng sự kiện `orders::events`.

Cú pháp tham chiếu thường dùng là:

~~~text
<module-name>::<interface-name>
~~~

Với tên module mặc định `orders`, `events` là named interface có định danh `orders::events`. Hai phần mang ý nghĩa khác nhau:

- **Module name = `orders`**: module sở hữu các hợp đồng;
- **Interface name = `events`**: phần API cụ thể được công bố.

Một module có thể có nhiều named interface tùy ranh giới: `orders::events`, `orders::queries` hoặc `orders::spi`. Việc chia bề mặt API theo nhu cầu của consumer giúp tránh tình trạng một package `api` quá lớn cho phép mọi module dùng mọi thứ.

~~~mermaid
flowchart LR
    subgraph Orders["orders — application module"]
        Events["Named interface: events<br/>OrderPaid"]
        Default["Default interface<br/>Các kiểu public tại package gốc"]
        Internal["internal<br/>Entity, Repository, Implementation"]
    end
    Loyalty["loyalty"] -->|"orders::events"| Events
    Notify["notifications"] -->|"orders::events"| Events
    Loyalty -. "không truy cập" .-> Internal
    Notify -. "không truy cập" .-> Internal
~~~

Trong sơ đồ, module `orders` vẫn sở hữu `OrderPaid`; việc consumer import record chỉ tạo phụ thuộc **vào hợp đồng**. `orders` không phải import `LoyaltyService` hay `NotificationService`, nên producer có thể công bố event mà không biết những consumer cụ thể sẽ phản ứng.

> **Phân biệt:** “interface” trong *named interface* là khái niệm bề mặt API của module, **không bắt buộc là một Java `interface`**. Nó có thể công bố `record`, `class`, `enum` và những kiểu Java phù hợp khác, tùy cách bạn tổ chức API.

## 3. Định nghĩa `@NamedInterface` bằng `package-info.java`

Cách thông dụng để công bố một package con là đặt annotation `@NamedInterface` lên package thông qua `package-info.java`.

Giả sử hợp đồng sự kiện nằm trong:

~~~text
src/main/java/com/example/shop/orders/events/
├── package-info.java
└── OrderPaid.java
~~~

Tệp `orders/events/package-info.java`:

~~~java
@org.springframework.modulith.NamedInterface("events")
package com.example.shop.orders.events;
~~~

Tệp `orders/events/OrderPaid.java`:

~~~java
package com.example.shop.orders.events;

import java.time.Instant;
import java.util.UUID;

/**
 * Đơn hàng đã được xác nhận thanh toán theo quy tắc của module orders.
 */
public record OrderPaid(
        UUID eventId,
        UUID orderId,
        UUID customerId,
        UUID paymentId,
        Instant occurredAt
) {}
~~~

Ở đây:

1. `package-info.java` gắn **một tên interface** với package `orders.events`.
2. `OrderPaid` là kiểu `public` thuộc phần API đã công bố.
3. Consumer có thể import `com.example.shop.orders.events.OrderPaid` theo ranh giới này.
4. Các package con khác như `orders.internal` **không được công khai chỉ vì `orders.events` có annotation**.

Annotation nằm ở **đúng package cần công bố**. Đặt `@NamedInterface` trong `orders/package-info.java` rồi cho rằng nó tự áp dụng cho mọi subpackage là sai mục tiêu. Tương tự, tạo Java class tên `NamedInterface` hoặc đặt tên folder là `events` không khiến Spring Modulith tự công bố API.

### Vì sao dùng `package-info.java`?

Trong Java, `package-info.java` chứa khai báo package và metadata áp dụng cho package. Cách này giúp quyền công bố API được duy trì cùng source code và không bị phân tán vào lớp service hay controller. Người review chỉ cần mở file để biết `orders.events` là một bề mặt module được công bố có chủ đích.

Giả sử sau này `orders.events` có thêm `OrderCancelled` và `OrderShipped`, các kiểu công khai thích hợp đặt trong cùng package sẽ thuộc bề mặt `orders::events`. Vì vậy **mọi kiểu `public` được thêm vào package này cần được review như một thay đổi API**. Không nên vô tình đặt `OrderRepository`, DTO chứa dữ liệu nhạy cảm hoặc helper implementation vào package `events`.

### Cách đặt tên named interface

| Tên | Dùng khi nào | Lưu ý |
| --- | --- | --- |
| `events` | Consumer chỉ cần các hợp đồng application event | Phù hợp cho bài học giao tiếp qua event |
| `api` | Có các DTO/service API công khai, không riêng event | Dễ mở rộng quá mức nếu đưa đủ loại thực thể vào |
| `queries` | Module khác chỉ cần truy vấn đọc theo contract được cung cấp | Không xuất thẳng internal repository nếu không kiểm soát được nghiệp vụ |
| `spi` | Module cho phép bên ngoài triển khai một điểm mở rộng có chủ ý | Cần tài liệu về trách nhiệm và vòng đời của implementer |

Tên `events` là tên do nhóm dự án lựa chọn, không phải một tên cứng bắt buộc của Spring Modulith. Điều quan trọng là tên đó **biểu thị quyền sử dụng** và được dùng nhất quán trong cấu hình phụ thuộc.

## 4. Producer ở module sở hữu event

Sau khi công bố `orders::events`, code producer vẫn thuộc `orders`. Nó có quyền sử dụng contract do chính module mình sở hữu và chỉ cần biết `ApplicationEventPublisher`.

Ví dụ tối giản:

~~~java
package com.example.shop.orders.internal;

import com.example.shop.orders.events.OrderPaid;
import java.time.Clock;
import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderPaymentService {

    private final OrderRepository repository;
    private final ApplicationEventPublisher publisher;
    private final Clock clock;

    public OrderPaymentService(
            OrderRepository repository,
            ApplicationEventPublisher publisher,
            Clock clock
    ) {
        this.repository = repository;
        this.publisher = publisher;
        this.clock = clock;
    }

    @Transactional
    public void recordVerifiedPayment(UUID orderId, UUID paymentId) {
        Order order = repository.findById(orderId).orElseThrow();

        // API miền minh họa: chỉ true khi thật sự có transition mới.
        boolean newlyPaid = order.markPaidIfNew(paymentId);
        if (!newlyPaid) {
            return;
        }

        publisher.publishEvent(new OrderPaid(
                UUID.randomUUID(),
                order.getId(),
                order.getCustomerId(),
                paymentId,
                clock.instant()
        ));
    }
}
~~~

`Order`, `OrderRepository` và `markPaidIfNew` là các thành phần giả định cần tự triển khai trong module `orders`; đoạn mã không xác thực thanh toán bên ngoài, mà nhận một kết quả **đã được xác minh**. Khi dùng JPA, ví dụ giả định `Order` là entity được quản lý trong transaction để cập nhật được ghi khi commit.

Những nguyên tắc cần giữ:

- Producer sở hữu **ý nghĩa** của `OrderPaid`: sự kiện được tạo khi thanh toán hợp lệ làm đơn chuyển trạng thái nghiệp vụ.
- Event có **eventId** để consumer nhận diện một lần xảy ra; `paymentId` giúp nhận diện giao dịch thanh toán và bảo vệ producer khỏi lặp callback.
- Producer không import `loyalty` hay `notifications`.
- `publishEvent` **không đồng nghĩa transaction đã commit**; cách chạy listener phụ thuộc loại listener và cấu hình transaction.
- Named interface chỉ quy định **phụ thuộc mã nguồn hợp lệ**; nó không tự thay đổi thời điểm phát, lưu event bền vững hoặc kích hoạt retry.

## 5. Consumer chỉ import hợp đồng đã công bố

Trong `loyalty`, listener nhận `OrderPaid` từ **`orders::events`** và chịu trách nhiệm riêng về việc ghi điểm.

~~~java
package com.example.shop.loyalty.internal;

import com.example.shop.orders.events.OrderPaid;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class AwardPointsOnOrderPaid {

    private final LoyaltyLedger ledger;

    AwardPointsOnOrderPaid(LoyaltyLedger ledger) {
        this.ledger = ledger;
    }

    @ApplicationModuleListener
    void on(OrderPaid event) {
        ledger.awardOnce(
                event.eventId(),
                event.orderId(),
                event.customerId()
        );
    }
}
~~~

`LoyaltyLedger.awardOnce(...)` là API minh họa thuộc **loyalty**, không phải API sẵn có của Spring Modulith. Khi triển khai, ledger nên ghi nhận `eventId` với một ràng buộc duy nhất trong transaction để việc giao lại cùng event không cộng điểm hai lần.

Với `notifications`, code listener có thể chỉ phụ thuộc cùng contract:

~~~java
package com.example.shop.notifications.internal;

import com.example.shop.orders.events.OrderPaid;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class NotifyOnOrderPaid {

    private final NotificationRequests requests;

    NotifyOnOrderPaid(NotificationRequests requests) {
        this.requests = requests;
    }

    @ApplicationModuleListener
    void on(OrderPaid event) {
        requests.enqueueOnce(
                event.eventId(),
                event.customerId(),
                event.orderId()
        );
    }
}
~~~

Như vậy có **một producer, nhiều consumer** phản ứng với cùng event. `orders` không cần thêm một lời gọi mới khi có consumer mới; `loyalty` và `notifications` không cần tham chiếu `OrderRepository` để biết cách tạo phản ứng. Mỗi consumer quản lý tình huống nhận trùng, lỗi và trạng thái hoàn tất trong module mình.

**`@ApplicationModuleListener`** hỗ trợ xử lý event sau commit, bất đồng bộ và trong transaction riêng. Nó thuận tiện cho sự kiện giữa module, nhưng **không phải một phần bắt buộc của named interface**. Consumer có thể dùng listener khác tùy nghiệp vụ; ranh giới vẫn được quyết định bởi việc import những kiểu nào của `orders`.

## 6. Giới hạn quyền phụ thuộc bằng `allowedDependencies`

Công bố `orders::events` trả lời câu hỏi **“orders cho phép module khác nhìn thấy API nào?”**. Một bước chặt chẽ hơn là để `loyalty` tuyên bố **“tôi chỉ muốn phụ thuộc phần nào của module khác?”**.

Trong `loyalty/package-info.java`:

~~~java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "orders::events"
)
package com.example.shop.loyalty;
~~~

Với tên module mặc định `orders`, cấu hình trên cho phép module `loyalty` phụ thuộc vào named interface `orders::events`. Phụ thuộc khác từ `loyalty` sang các phần không được liệt kê của `orders` sẽ bị kiểm tra kiến trúc phát hiện khi chạy verify.

`notifications` cũng có thể đặt một ràng buộc riêng:

~~~java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "orders::events"
)
package com.example.shop.notifications;
~~~

Phần `allowedDependencies` là **tùy chọn**, nhưng đặc biệt hữu ích trong ứng dụng lớn vì nó tạo một danh sách phụ thuộc được cho phép có thể review và kiểm tra. Nếu `loyalty` còn phải gọi một API công khai khác của `orders`, cần chủ động quyết định và khai báo quyền phụ thuộc phù hợp. Không nên mở rộng toàn bộ `orders` chỉ để vượt qua một lỗi verify.

### Công bố và cho phép là hai chiều kiểm soát

| Khai báo | Đặt ở đâu? | Câu hỏi được trả lời |
| --- | --- | --- |
| `@NamedInterface("events")` | `orders.events/package-info.java` | “Kiểu nào thuộc API có tên `events` mà orders công bố?” |
| `@ApplicationModule(allowedDependencies = "orders::events")` | `loyalty/package-info.java` | “Loyalty được phép phụ thuộc vào phần API nào của orders?” |
| `ApplicationModules.verify()` | Kiểm thử kiến trúc | “Code đang import có tuân thủ ranh giới đã công bố và các quy tắc module hay không?” |

Nếu định danh module đã được tùy biến thay vì tên mặc định từ package, hãy dùng **tên module được Spring Modulith nhận diện thực tế** trong `allowedDependencies`. Không suy đoán chuỗi `orders::events` sẽ đúng cho mọi sơ đồ module ở mọi dự án.

### Phụ thuộc nào nên bị chặn?

Ví dụ **không nên dùng** trong `loyalty`:

~~~java
package com.example.shop.loyalty.internal;

// Không phải API công khai của orders:
import com.example.shop.orders.internal.OrderRepository;
import com.example.shop.orders.internal.OrderEntity;
~~~

Ngay cả khi kiểu Java được khai báo `public` và code biên dịch, việc import vào `orders.internal` vẫn phá vỡ module boundary. Với cấu hình ranh giới nêu trên, kiểm tra cấu trúc Spring Modulith sẽ phát hiện phụ thuộc này.

Nếu consumer cần dữ liệu mà event chưa mang theo, có các hướng hợp lý:

1. **Thêm field snapshot cần thiết vào contract** nếu đó là thông tin đúng ngữ nghĩa tại thời điểm event xảy ra.
2. **Công bố một API truy vấn riêng có chủ đích**, chẳng hạn `orders::queries`, nếu consumer thực sự cần dữ liệu hiện tại.
3. **Duy trì projection thuộc consumer** nếu nhu cầu đọc là dài hạn và có thể chấp nhận nhất quán cuối cùng.

Chọn phương án dựa trên trách nhiệm dữ liệu; đừng công khai internal repository vì tiện.

## 7. Kiểm chứng ranh giới bằng Spring Modulith

Cấu trúc Java có `public` không tự ngăn một lập trình viên mới import nhầm package nội bộ. Vì vậy, **lời cam kết kiến trúc phải được kiểm tra tự động**.

Một bài kiểm thử điển hình:

~~~java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleStructureTests {

    @Test
    void verifiesModuleBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Ví dụ giả định `ShopApplication` là lớp khởi động tại `com.example.shop`, các module là package con trực tiếp `orders`, `loyalty`, `notifications`, và project có các dependency Spring Modulith/JUnit thích hợp.

Phép verify giúp phát hiện những vấn đề như phụ thuộc đến package nội bộ không được công bố, phụ thuộc vượt danh sách `allowedDependencies` hoặc vòng phụ thuộc trái quy tắc module. Nó là **kiểm tra cấu trúc**, không chứng minh listener đã nhận event, transaction đã commit hay registry đã lưu publication.

### Bài tập kiểm tra lỗi có chủ đích

Thực hiện một kịch bản tích cực và một kịch bản tiêu cực:

| Bước | Thay đổi | Kỳ vọng |
| --- | --- | --- |
| 1 | `loyalty` import `orders.events.OrderPaid`, `orders.events` có `@NamedInterface("events")` | Verify PASS nếu các phụ thuộc khác đều hợp lệ |
| 2 | Bỏ annotation `@NamedInterface` khỏi package `orders.events` | Verify phát hiện consumer đang tham chiếu package không được công bố |
| 3 | Khôi phục annotation, thêm import từ `orders.internal` trong `loyalty` | Verify FAIL vì phụ thuộc vào nội bộ |
| 4 | Xóa phụ thuộc sai, giữ `allowedDependencies = "orders::events"` | Verify trở lại PASS |
| 5 | Cố tình phụ thuộc vào một named interface khác chưa được cho phép | Verify FAIL cho đến khi thiết kế hoặc danh sách quyền được sửa có chủ đích |

Đây là bài tập **cố ý làm hỏng code trong một nhánh/sandbox rồi khôi phục**, không phải lời khuyên để giữ những import sai trong code chính thức.

### Cần kiểm tra điều gì ngoài `verify()`?

- Producer chỉ phát `OrderPaid` khi một chuyển trạng thái hợp lệ xảy ra.
- Consumer thật sự nhận event sau commit nếu dùng `@ApplicationModuleListener`.
- Transaction rollback không tạo side effect hậu commit.
- Consumer xử lý lặp cùng eventId mà không nhân đôi kết quả nghiệp vụ.
- Khi có Event Publication Registry, lỗi consumer sau commit để lại publication chưa hoàn tất và có cơ chế khôi phục.

Có thể dùng `@ApplicationModuleTest` và các công cụ hỗ trợ như `PublishedEvents` hoặc `Scenario` để kiểm tra hành vi sự kiện. **`ApplicationModules.verify()` và kiểm thử giao sự kiện phục vụ hai mục tiêu khác nhau; cả hai đều cần thiết** khi đánh giá chất lượng module.

## 8. Named interface và độ tin cậy của application events

Named interface **giải quyết ranh giới mã nguồn**, còn tính đáng tin cậy của event phụ thuộc vào transaction và hạ tầng giao nhận. Không nên nhầm hai nhóm này.

~~~mermaid
flowchart TD
    Contract["orders::events<br/>API event được công bố"] --> Dependency["Dependency verification<br/>allowedDependencies"]
    Contract --> Publish["Producer publish OrderPaid"]
    Publish --> Commit["Transaction nguồn commit"]
    Commit --> Registry["Publication Registry<br/>nếu đã cấu hình storage bền vững"]
    Registry --> Listener["Consumer xử lý sau commit"]
    Listener --> Outcome{"Thành công?"}
    Outcome -->|"Có"| Done["Hoàn tất publication"]
    Outcome -->|"Chưa"| Recovery["Publication tồn đọng<br/>retry/resubmit có kiểm soát"]
    Recovery --> Listener
~~~

**Trục kiến trúc:** `@NamedInterface` và `allowedDependencies` quy định consumer được dùng kiểu `OrderPaid` ở đâu. Chúng không làm event tự động bất đồng bộ, tự tạo transaction mới, ghi message bền vững hay bảo đảm giao đúng một lần.

**Trục vận hành:** sau khi producer phát event trong transaction, listener hậu commit có thể gặp lỗi dù dữ liệu nguồn đã commit. Khi dùng registry phù hợp và storage bền vững, ứng dụng có thể theo dõi publication chưa hoàn tất rồi tổ chức resubmit. Consumer phải idempotent vì một event có thể được giao lại sau crash hoặc retry.

| Câu hỏi | Cơ chế cần xét |
| --- | --- |
| Consumer có được import `OrderPaid`? | Named interface, allowed dependencies và verify |
| Listener chạy trước hay sau commit? | `@EventListener`, `@TransactionalEventListener`, `@ApplicationModuleListener` |
| Sau commit JVM dừng thì công việc còn dấu vết không? | Event Publication Registry với persistence và cấu hình phù hợp |
| Giao lại event có cộng điểm hai lần không? | Idempotency, khóa duy nhất và transaction consumer |
| Event tồn đọng có bị bỏ quên không? | Log, metric, cảnh báo, quy trình retry/resubmit |

Bởi vậy `orders::events` là một **hợp đồng** chứ không phải một **kênh vận chuyển message**. Cùng contract có thể được consumer đồng bộ hoặc hậu commit sử dụng theo nhu cầu, nhưng nên có quy ước thống nhất để tránh side effect chạy trước khi trạng thái nguồn được commit.

## 9. Quản trị thay đổi named interface

Khi nhiều consumer cùng dựa vào `orders::events`, mọi thay đổi contract có thể lan đến các module còn lại. Named interface giúp nhìn rõ nơi tạo phụ thuộc, nhưng không làm mọi thay đổi đều tương thích.

### Các kiểu thay đổi thường gặp

| Thay đổi | Rủi ro | Cách xử lý |
| --- | --- | --- |
| Thêm `OrderRefunded` vào `orders.events` | Mở rộng public API và cần mô tả rõ ngữ nghĩa | Review schema, event semantics và test contract |
| Thêm thành phần vào Java `record OrderPaid` | Constructor/accessor hoặc code biên dịch của consumer có thể cần cập nhật | Sửa producer và các consumer tương ứng; đánh giá tương thích |
| Đổi ý nghĩa `OrderPaid` thành “đã gửi yêu cầu thanh toán” | Consumer có thể cộng điểm dù chưa thanh toán thành công | Không thay đổi ngữ nghĩa im lặng; định nghĩa event khác đúng mốc |
| Di chuyển `OrderPaid` sang `orders.internal` | Các consumer đang dùng contract mất quyền phụ thuộc | Giữ API hợp lệ hoặc lập kế hoạch migration |
| Công bố cả `orders.internal` để tắt lỗi verify | Làm lộ toàn bộ chi tiết triển khai | Chỉ công bố đúng kiểu có mục đích |
| Xóa `orders::events` | Phá mọi module đang được phép phụ thuộc named interface này | Đánh giá consumer, thay thế/migrate trước khi xóa |

Đối với modular monolith biên dịch chung, lỗi contract thường xuất hiện khi build; nhưng thay đổi ý nghĩa nghiệp vụ có thể không có lỗi biên dịch. Vì vậy ngoài test cấu trúc, cần những test diễn đạt **khi nào OrderPaid hợp lệ** và **consumer phản ứng ra sao**.

### Đừng thiết kế named interface quá rộng

Nếu bạn tạo:

~~~text
orders.api
├── OrderPaid.java
├── OrderEntity.java
├── OrderRepository.java
├── DiscountCalculator.java
└── PaymentGatewayClient.java
~~~

rồi công bố toàn bộ `orders::api`, module nhận có thể phụ thuộc vào quá nhiều chi tiết của `orders`. Thiết kế này hợp lệ về mặt công bố nhưng làm yếu khả năng thay đổi độc lập. **Không nên lấy “được verify” làm thước đo duy nhất của thiết kế tốt**: cần xem việc công bố đó có thực sự cần cho consumer không.

Có thể tách rõ `events` cho fact đã xảy ra, `queries` cho API đọc, và `spi` cho điểm mở rộng. Mỗi nhóm có vòng đời thay đổi và tập consumer riêng. Tuy nhiên cũng không nên tạo hàng chục interface chỉ vì có thể; bắt đầu với một ranh giới rõ nhu cầu thực tế rồi tách khi có lý do nghiệp vụ.

## 10. Những nhầm lẫn thường gặp

**Nhầm lẫn 1: `public record` đồng nghĩa public API của module.** `public` là mức truy cập Java. Một kiểu trong package con chưa được công bố có thể vẫn là nội bộ theo Spring Modulith. Muốn dùng qua module boundary, công bố package hoặc kiểu bằng cơ chế được framework hỗ trợ và kiểm tra lại.

**Nhầm lẫn 2: Đặt tên package `events` là Spring Modulith tự nhận.** Tên folder chỉ tổ chức code; annotation và cấu trúc API mới giúp công bố ý định. Với ví dụ đang học, dùng `orders.events/package-info.java` chứa `@NamedInterface("events")`.

**Nhầm lẫn 3: Named interface là Java `interface` phải có implementation.** Không. Đây là bề mặt API gồm các kiểu Java, có thể là record sự kiện hoặc DTO.

**Nhầm lẫn 4: Có `@NamedInterface` thì tự hạn chế mọi consumer.** Không. Named interface công bố API ở phía module sở hữu; muốn quy định consumer chỉ được phụ thuộc `orders::events`, dùng `allowedDependencies` và kiểm thử kiến trúc.

**Nhầm lẫn 5: Kiểm tra verify thay thế cho test business.** Không. Verify cho biết quan hệ phụ thuộc có phù hợp; nó không biết listener đã cộng điểm đúng, transaction rollback hay event bị giao hai lần.

**Nhầm lẫn 6: Named interface là một broker/topic.** Không. Một package named interface không có hàng đợi, offset hay cơ chế phát lại. Khi cần giao event sau commit đáng tin cậy, học riêng transaction listener, publication registry, retry và idempotency.

**Nhầm lẫn 7: Chỉ cần import contract là không còn coupling.** Vẫn có coupling với tên, field và ý nghĩa `OrderPaid`. Mục tiêu là làm **phụ thuộc có chủ đích, nhỏ và ổn định**, không phải loại bỏ mọi phụ thuộc.

**Nhầm lẫn 8: Cứ bật quyền phụ thuộc rộng để test xanh.** Khi verify thất bại, phải xác định import nào sai và chọn sửa code hoặc công bố API phù hợp. Mở toàn bộ module chỉ che giấu vấn đề kiến trúc.

## 11. Bài thực hành có hướng dẫn

### Đề bài

Một ứng dụng bán vé có module `payments`, `tickets` và `notifications`. Sau khi ghi nhận thanh toán thành công, `payments` phát `PaymentCompleted`. `tickets` cần phát hành vé, còn `notifications` tạo yêu cầu gửi email. Không module nào được import repository nội bộ của `payments`.

**Mục tiêu:** thiết lập named interface **`payments::events`** và chỉ cho phép hai consumer phụ thuộc vào hợp đồng đó.

### Các bước triển khai

1. **Thiết kế module:** tạo các package gốc `com.example.ticketing.payments`, `com.example.ticketing.tickets`, `com.example.ticketing.notifications`.
2. **Công bố sự kiện:** tạo `payments.events.PaymentCompleted` với `eventId`, `reservationId`, `paymentId`, `occurredAt`.
3. **Khai báo named interface:** thêm `@NamedInterface("events")` trong `payments.events/package-info.java`.
4. **Ràng buộc consumer:** thêm `@ApplicationModule(allowedDependencies = "payments::events")` vào `tickets/package-info.java` và `notifications/package-info.java`.
5. **Viết publisher:** khi thanh toán thật sự chuyển trạng thái mới, phát `PaymentCompleted` bằng `ApplicationEventPublisher` trong transaction thích hợp.
6. **Viết listener:** hai consumer dùng `@ApplicationModuleListener` để tạo phản ứng độc lập, không import `payments.internal`.
7. **Kiểm tra cấu trúc:** chạy `ApplicationModules.of(TicketingApplication.class).verify()`; sửa những phụ thuộc vượt ranh giới.
8. **Thử lỗi:** cố ý import một repository nội bộ từ consumer và quan sát lỗi verify; xóa import sai rồi kiểm tra PASS.
9. **Kiểm tra hành vi:** tạo test sau commit, rollback và nhận trùng; dùng storage/registry phù hợp nếu bài thực hành triển khai khôi phục publication.
10. **Quan sát:** ghi log với `eventId`, tên consumer và trạng thái xử lý; phân biệt lỗi phụ thuộc cấu trúc với lỗi runtime listener.

### Tiêu chí chấm bài

| Tiêu chí | Đạt khi |
| --- | --- |
| **Ranh giới module** | `payments` không import tickets/notifications; consumer không import internal của payments |
| **Named interface** | `payments::events` công bố được contract và chỉ contract cần thiết |
| **Allowed dependencies** | Consumer chỉ kê đúng interface cần phụ thuộc |
| **Verify** | Cấu trúc hợp lệ PASS; cố ý tạo phụ thuộc sai có thể tái hiện lỗi |
| **Event semantics** | `PaymentCompleted` phản ánh thanh toán đã được ghi nhận, không phải yêu cầu thanh toán |
| **Transaction** | Listener hậu commit không tạo tác dụng phụ khi transaction nguồn rollback |
| **Idempotency** | Nhận lại cùng một event không phát hành trùng vé |
| **Quan sát** | Có thể tìm transaction/eventId bị lỗi và biết consumer nào chưa hoàn tất |

### Câu hỏi tự đánh giá

**Câu 1. Vì sao `OrderPaid` là `public record` mà `loyalty` vẫn có thể vi phạm module boundary khi import?**

Vì Java `public` và API module là hai quy tắc khác nhau. Nếu record nằm trong subpackage nội bộ chưa công bố, nó chưa nằm trong interface mà Spring Modulith cho phép consumer sử dụng.

**Câu 2. Khi nào nên dùng named interface thay vì đặt record vào package gốc module?**

Khi muốn phân nhóm một phần API riêng, như các event ở `orders.events`, và chỉ công bố nhóm đó với tên rõ ràng. Với module rất nhỏ và một ít kiểu API, đặt trong package gốc có thể đủ; named interface hữu ích khi API mở rộng và cần quyền phụ thuộc chi tiết.

**Câu 3. `orders::events` có thể đảm bảo mọi listener chạy sau commit không?**

Không. Nó là định danh bề mặt API, không quyết định thời điểm listener. Sau commit phải được chọn bằng listener giao dịch như `@TransactionalEventListener` hoặc cơ chế của `@ApplicationModuleListener`.

**Câu 4. Vì sao vẫn cần `allowedDependencies` khi đã khai báo `@NamedInterface`?**

Vì một bên định nghĩa **phần API có thể được sử dụng**, còn bên kia định nghĩa **phần API module consumer thực sự được phép phụ thuộc**. Kết hợp hai phía sẽ làm rõ và kiểm tra được ý định kiến trúc.

**Câu 5. Có thể bỏ thử nghiệm nhận trùng chỉ vì application module verify PASS không?**

Không. Verify kiểm tra phụ thuộc tĩnh. Consumer vẫn có thể gặp lỗi sau commit, nhận lại event và nhân đôi tác dụng nếu không có idempotency.

## 12. Checklist áp dụng vào dự án thật

- [ ] Xác định module nào **sở hữu sự kiện** và thời điểm nghiệp vụ làm event hợp lệ.
- [ ] Phân biệt package gốc public API với subpackage internal theo quy ước ứng dụng.
- [ ] Tạo package chuyên biệt cho event contract cần công bố.
- [ ] Thêm đúng `package-info.java` với `@NamedInterface("events")`.
- [ ] Chỉ đặt kiểu `public` cần thiết trong named interface.
- [ ] Consumer import event contract, không import JPA entity/repository nội bộ của producer.
- [ ] Cân nhắc `@ApplicationModule(allowedDependencies = "orders::events")` để hạn chế phụ thuộc.
- [ ] Chạy `ApplicationModules.verify()` trong bộ test kiến trúc.
- [ ] Kiểm tra ít nhất một trường hợp vi phạm boundary phải FAIL.
- [ ] Kiểm thử riêng transaction, after commit, retry/idempotency và publication registry khi nghiệp vụ yêu cầu.
- [ ] Review thay đổi field/ý nghĩa của event như thay đổi hợp đồng API giữa các module.
- [ ] Có log, metric và cách truy vết `eventId` cho những consumer xử lý sau commit.

## Ghi nhớ

**Named interface** trong Spring Modulith là cách công bố một phần **API của application module** bằng tên rõ ràng. Với `@NamedInterface("events")` trong `orders.events/package-info.java`, module `orders` có thể cho phép `loyalty` và `notifications` sử dụng `OrderPaid` mà vẫn giữ `orders.internal` ở phía sau ranh giới. Dùng `@ApplicationModule(allowedDependencies = "orders::events")` ở module nhận và `ApplicationModules.verify()` để ràng buộc, kiểm chứng thiết kế.

Named interface bảo vệ **quan hệ phụ thuộc giữa các module**; việc xử lý sự kiện đáng tin cậy vẫn cần chọn listener đúng thời điểm, quản lý transaction, event publication registry, retry, idempotency, kiểm thử và khả năng quan sát. Đây là hai phần bổ trợ để một hệ thống modular monolith vừa mở rộng chức năng mà ít phụ thuộc, vừa giải quyết tốt các lỗi sau commit.
