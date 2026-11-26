# Nhận event

Trong Spring Modulith, một module có thể phát sự kiện nghiệp vụ bằng `ApplicationEventPublisher`, nhưng **được phát không đồng nghĩa với đã được nhận và xử lý thành công**. Việc nhận event phụ thuộc vào loại listener, transaction của producer, cơ chế gọi đồng bộ hay bất đồng bộ và trạng thái của tiến trình. Khi nhiều module cùng nghe một event, mỗi module nhận có kết quả xử lý độc lập.

Bài này thuộc chương **Chu kỳ phát hành** của **SPRING_MODULITH_APPLICATION_EVENTS**. Trọng tâm là **bước nhận event** trong quá trình giao tiếp giữa các module Spring Modulith: listener được lựa chọn và gọi như thế nào; khi nào nó chạy sau commit; cách Event Publication Registry hỗ trợ khôi phục lần giao chưa hoàn tất; và làm sao kiểm thử, quan sát, chống xử lý trùng khi event được giao lại. Những cơ chế này giúp giảm phụ thuộc giữa module mà vẫn bảo vệ ranh giới nghiệp vụ.

Sau khi học, bạn cần phân biệt rõ **publish → đủ điều kiện được giao → listener bắt đầu → ghi hiệu ứng nghiệp vụ → publication hoàn tất**. Bạn cũng cần nhận diện lúc nào có thể nói một listener đã xử lý thành công, điều gì còn thiếu khi chỉ nhìn log “event received”, và làm thế nào chứng minh khả năng khôi phục khi consumer gặp lỗi.

## 1. “Nhận event” nghĩa là gì?

Giả sử module `orders` công bố `OrderPaid` sau khi một đơn được ghi nhận thanh toán. Hai module `loyalty` và `notifications` có listener tương ứng. Các hành động sau là **những mốc khác nhau**:

| Mốc | Bên thực hiện | Điều có thể khẳng định |
| --- | --- | --- |
| **Tạo event** | `orders` | Có đối tượng `OrderPaid` trong bộ nhớ; transaction chưa chắc commit |
| **Publish event** | `orders` gọi `publishEvent` | Event được chuyển cho cơ chế phân phối sự kiện trong ứng dụng |
| **Đủ điều kiện giao** | Spring chọn listener theo loại event và phase | Listener có cơ hội được gọi theo quy tắc cấu hình |
| **Listener bắt đầu** | `loyalty` hoặc `notifications` | Một lần thực thi consumer đã bắt đầu; chưa chứng minh hiệu ứng hoàn tất |
| **Hiệu ứng nghiệp vụ commit** | Consumer | Dữ liệu hoặc yêu cầu gửi của consumer đã được ghi thành công theo transaction tương ứng |
| **Publication được đánh dấu hoàn tất** | Hạ tầng publication, nếu được cấu hình | Registry đã ghi nhận listener tương ứng hoàn tất |

**Nhận event** trong nghĩa hẹp là *listener bắt đầu được gọi với payload phù hợp*. Trong nghĩa vận hành, người ta thường muốn biết thêm *listener có xử lý thành công hay không*. Hai việc này không thể đồng nhất.

Một listener có thể nhận `OrderPaid`, ghi log rồi ném exception khi cập nhật cơ sở dữ liệu. Khi đó log chứng minh **có lời gọi vào consumer**, nhưng không chứng minh điểm thưởng đã được cộng. Ngay cả khi consumer đã commit hiệu ứng, tiến trình vẫn có thể dừng trước khi hạ tầng kịp ghi nhận publication hoàn tất, dẫn đến khả năng giao lại.

~~~mermaid
flowchart TD
    A["Producer tạo OrderPaid"] --> B["publishEvent(OrderPaid)"]
    B --> C{"Listener có phù hợp<br/>và phase được kích hoạt?"}
    C -->|Không| X["Listener không được gọi"]
    C -->|Có| D["Listener bắt đầu nhận"]
    D --> E{"Xử lý nghiệp vụ thành công?"}
    E -->|Có| F["Transaction consumer commit"]
    F --> G["Publication được ghi hoàn tất<br/>nếu có registry"]
    E -->|Không| H["Lỗi hoặc publication chưa hoàn tất"]
    H --> I["Khôi phục/resubmit khi đã cấu hình"]
    I --> D
~~~

Sơ đồ thể hiện **một nhánh listener**, không phải quy tắc toàn bộ ứng dụng phải chạy tuần tự. Hai consumer của cùng event có thể thực thi song song và kết thúc tại những thời điểm khác nhau.

## 2. Ai quyết định listener nào nhận event?

Trong Spring, `ApplicationEventPublisher` phát application event. Hạ tầng sự kiện tìm và gọi các listener tương ứng đã được đăng ký trong **application context**, chẳng hạn phương thức có `@EventListener` hoặc `@TransactionalEventListener`. Spring Modulith dựa trên cơ chế này và bổ sung những tiện ích cho giao tiếp giữa các module.

Một listener chỉ có thể nhận event nếu đáp ứng các điều kiện căn bản:

1. Bean chứa listener đã được Spring phát hiện, khởi tạo và quản lý trong application context.
2. Phương thức listener được đăng ký đúng annotation, chữ ký và kiểu sự kiện.
3. Event được publish qua đúng application context chứa listener đó.
4. Với transactional listener, phase của transaction tương ứng thực sự xảy ra.
5. Không có cấu hình lọc hoặc điều kiện nào loại bỏ lời gọi dành cho listener.

Ví dụ nhận đồng bộ đơn giản:

~~~java
package com.example.shop.reporting.internal;

import com.example.shop.orders.events.OrderPaid;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
class OrderPaidLogListener {

    @EventListener
    void on(OrderPaid event) {
        System.out.println("Received: " + event.eventId());
    }
}
~~~

Nếu `orders` phát một đối tượng `OrderPaid`, listener trên là ứng viên phù hợp theo kiểu tham số. Với cấu hình multicaster mặc định của Spring, listener `@EventListener` thông thường chạy **đồng bộ trong luồng publish**. Nếu một listener đồng bộ ném exception, lỗi có thể truyền ngược về producer và ảnh hưởng transaction đang chạy.

Đừng dùng `System.out.println` ở ví dụ trên làm bằng chứng đạt yêu cầu giao sự kiện đáng tin cậy: nó chỉ cho thấy lời gọi vào listener, còn dữ liệu đã commit hay publication đã hoàn tất phải kiểm tra riêng.

### Có nhiều consumer cùng nhận thì sao?

Giả sử có ba listener:

~~~text
orders publishes OrderPaid
    |
    +--> loyalty.on(OrderPaid)
    |
    +--> notifications.on(OrderPaid)
    |
    +--> reporting.on(OrderPaid)
~~~

Đây là kiểu **fan-out**: ba consumer quan tâm cùng một sự kiện, và mỗi consumer sở hữu phản ứng của mình. Không giống **competing consumers** trong một hàng đợi chia tải, việc `loyalty` nhận event không khiến `notifications` mất quyền nhận event đó.

| Tình huống | Kết quả cần hiểu |
| --- | --- |
| Ba listener phù hợp kiểu `OrderPaid` | Cả ba có thể được gọi theo cơ chế listener đã cấu hình |
| Chỉ `loyalty` lỗi | Không suy ra `notifications` cũng lỗi; trạng thái thực tế tùy kiểu xử lý |
| Thêm `fraud-monitoring` listener | Producer có thể tiếp tục publish cùng contract mà không import implementation mới |
| Không có listener nào phù hợp | Publish có thể kết thúc mà không có hiệu ứng consumer |
| Listener nằm ngoài application context hoặc bean chưa được quét | Annotation trong source code không đủ để đăng ký nhận |

Với listener đồng bộ thông thường, exception có thể khiến quá trình phân phối bị ngắt; đừng hứa rằng mọi listener phía sau chắc chắn đã được gọi. Với các listener hậu commit bất đồng bộ, lịch thực thi và trạng thái của từng consumer được tách hơn; vẫn phải dựa vào bằng chứng khi khẳng định đã hoàn tất.

## 3. Nhận trong lúc publish hay sau khi commit?

Đây là quyết định ảnh hưởng trực tiếp tới tính đúng đắn của luồng event. Một event có thể được tạo và publish **trong transaction nguồn**, nhưng listener được gọi trước hay sau commit phụ thuộc vào annotation.

| Cơ chế | Thời điểm nhận thường gặp | Có bảo đảm sau commit? | Có tự mở transaction mới? |
| --- | --- | --- | --- |
| `@EventListener` | Ngay khi publish, đồng bộ với multicaster mặc định | **Không** | **Không** |
| `@TransactionalEventListener` mặc định | `AFTER_COMMIT` của transaction nguồn | **Có**, nếu thực sự có transaction và commit | **Không** |
| `@TransactionalEventListener(phase = BEFORE_COMMIT)` | Trước commit | **Không** | **Không** |
| `@TransactionalEventListener(phase = AFTER_ROLLBACK)` | Sau rollback | Dành cho nhánh rollback | **Không** |
| `@ApplicationModuleListener` | Sau commit, bất đồng bộ, trong transaction riêng | **Có** theo cấu hình chuẩn | **Có**, với `REQUIRES_NEW` |

`@ApplicationModuleListener` là annotation tiện ích của Spring Modulith, kết hợp xử lý sự kiện transactional, bất đồng bộ và transaction mới cho consumer. Nó phù hợp với nhiều phản ứng độc lập giữa module, ví dụ cộng điểm sau khi đơn đã commit.

### Khi transaction nguồn rollback

~~~mermaid
sequenceDiagram
    participant P as orders / Producer
    participant Spring as Application events
    participant Sync as @EventListener
    participant Tx as @ApplicationModuleListener
    participant DB as Database

    P->>DB: Bắt đầu T1, lưu trạng thái PAID
    P->>Spring: publishEvent(OrderPaid)
    Spring->>Sync: Gọi listener đồng bộ
    Sync-->>Spring: Đã chạy trước commit
    P->>DB: Rollback T1
    Note over Spring,Tx: Không có pha AFTER_COMMIT
    Note over Tx: Listener hậu commit không chạy
~~~

Nếu email được gửi ngay trong `@EventListener`, email đã gửi không thể được rollback theo database. Nếu email chỉ được gửi từ `@ApplicationModuleListener` sau commit, luồng rollback sẽ không kích hoạt phản ứng đó.

### Khi transaction nguồn commit

~~~mermaid
sequenceDiagram
    participant P as orders / Producer
    participant DB as Database
    participant Spring as Spring event infrastructure
    participant L as loyalty / Consumer

    P->>DB: Cập nhật đơn trong T1
    P->>Spring: publishEvent(OrderPaid)
    P->>DB: Commit T1
    Spring-->>L: Gọi listener sau commit
    L->>DB: Ghi ledger trong transaction T2
    DB-->>L: Commit T2
    L-->>Spring: Listener trả về thành công
~~~

Mốc **listener trả về** chưa chắc là cùng mốc với **registry ghi nhận publication hoàn tất**. Nếu có hạ tầng registry, việc cập nhật completion là một bước riêng; nếu không có registry, ứng dụng cần cơ chế khác để theo dõi hiệu ứng hậu commit.

### Khi publish ngoài transaction

`@TransactionalEventListener` mặc định không thực thi nếu không có transaction phù hợp. Tùy mục tiêu, có thể bật `fallbackExecution` để listener chạy khi không có transaction; tuy nhiên khi đó phải hiểu rõ rằng nhánh fallback **không được bảo vệ bởi cam kết “transaction nguồn đã commit”**.

Vì vậy, trước khi điều tra một listener “không nhận event”, hãy xác minh **đường gọi producer thực sự chạy trong transaction**. Ví dụ phương thức `@Transactional` bị gọi nội bộ theo self-invocation mà proxy giao dịch không được áp dụng có thể khiến giả định về transaction sai.

## 4. Chuẩn bị event contract để consumer nhận đúng dữ liệu

Mọi consumer đều cần một hợp đồng rõ ràng. Trong ví dụ bán hàng, `orders` sở hữu `OrderPaid`; các module nhận không nên phụ thuộc vào JPA entity hoặc repository nội bộ của `orders`.

~~~java
package com.example.shop.orders.events;

import java.time.Instant;
import java.util.UUID;

public record OrderPaid(
        UUID eventId,
        UUID orderId,
        UUID customerId,
        UUID paymentId,
        Instant occurredAt
) {}
~~~

Có thể công bố package chứa event bằng named interface:

~~~java
@org.springframework.modulith.NamedInterface("events")
package com.example.shop.orders.events;
~~~

Đối với module `loyalty`, có thể giới hạn quyền phụ thuộc:

~~~java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "orders::events"
)
package com.example.shop.loyalty;
~~~

`orders::events` là định danh minh họa khi module có tên mặc định `orders`. Nếu project thay đổi tên module, cần dùng đúng định danh đã được Spring Modulith nhận diện. `@NamedInterface` và `allowedDependencies` giúp **kiểm soát phụ thuộc mã nguồn**; chúng không tự chọn phase, không biến event thành message ngoài JVM và không bảo đảm delivery.

### Những gì contract nên cung cấp

| Field | Ý nghĩa | Consumer sử dụng để |
| --- | --- | --- |
| `eventId` | Một lần xảy ra event | Correlation, chống nhận trùng, liên kết publication |
| `orderId` | Aggregate nguồn | Liên hệ nghiệp vụ và truy vết |
| `customerId` | Khách hàng liên quan | Xác định sổ điểm hoặc đối tượng thông báo |
| `paymentId` | Giao dịch đã được xác thực | Đối chiếu với khóa nghiệp vụ; hỗ trợ chống ghi nhận thanh toán lặp |
| `occurredAt` | Lúc producer tạo event cho transition được chấp nhận | Đo độ trễ và giải thích mốc nghiệp vụ |

Không truyền entity JPA đang ở trạng thái managed, session hoặc các đối tượng nội bộ vào event. Một listener chạy bất đồng bộ sau commit không nên phụ thuộc vào lazy loading qua persistence context của producer, vốn có thể đã đóng.

**`occurredAt` không phải `receivedAt` hay `processedAt`.** Một lần retry sẽ tạo thời điểm nhận mới, nhưng vẫn là cùng occurrence nghiệp vụ, cùng `eventId`.

## 5. Producer gửi event để consumer nhận sau commit

Một producer mẫu:

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

    private final OrderRepository orders;
    private final ApplicationEventPublisher publisher;
    private final Clock clock;

    public OrderPaymentService(
            OrderRepository orders,
            ApplicationEventPublisher publisher,
            Clock clock
    ) {
        this.orders = orders;
        this.publisher = publisher;
        this.clock = clock;
    }

    @Transactional
    public void recordVerifiedPayment(UUID orderId, UUID paymentId) {
        Order order = orders.findById(orderId).orElseThrow();

        // Domain method minh họa: false nếu paymentId đã được ghi nhận.
        if (!order.markPaidIfNew(paymentId)) {
            return;
        }

        orders.save(order);

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

`Order`, `OrderRepository` và `markPaidIfNew` là thành phần nghiệp vụ minh họa cần tự xây dựng; đoạn code giả định payment đã được xác thực bằng nguồn đáng tin. `@Transactional` phải được Spring áp dụng thật, các thao tác lưu và publication phải tham gia transaction dự kiến.

**Điểm then chốt:** producer phát event **sau khi xác định transition hợp lệ** nhưng **trước khi transaction commit**. Nếu transaction rollback, listener hậu commit không chạy. Nếu application event được lưu bằng publication registry trong cùng transaction, bản ghi publication cũng không được commit khi T1 rollback.

Không nên đợi “đã gửi email xong” mới xem transition thanh toán là hợp lệ, nếu email vốn chỉ là phản ứng phụ trợ. Ngược lại, nếu một bước là bất biến bắt buộc trước khi xác nhận thanh toán, hãy tổ chức bước đó đồng bộ hoặc dùng quy trình trạng thái được điều phối rõ ràng.

## 6. Consumer nhận và xử lý event bằng `@ApplicationModuleListener`

Bây giờ triển khai module `loyalty`. Một listener tốt có trách nhiệm nhỏ: nhận contract, gọi service nghiệp vụ của module mình, và cho hạ tầng biết việc xử lý thành công **chỉ khi hiệu ứng thật sự hoàn tất theo định nghĩa của consumer**.

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
        ledger.grantOnce(
                event.eventId(),
                event.orderId(),
                event.customerId()
        );
    }
}
~~~

`LoyaltyLedger.grantOnce` là phương thức **minh họa của module loyalty**, không phải API mặc định của Spring Modulith. Nó cần giao dịch và ràng buộc dữ liệu để chống cộng điểm trùng khi cùng event được nhận lại.

Một listener thuộc module `notifications` có thể làm việc khác, độc lập với loyalty:

~~~java
package com.example.shop.notifications.internal;

import com.example.shop.orders.events.OrderPaid;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class PaymentNotificationOnOrderPaid {

    private final NotificationRequests requests;

    PaymentNotificationOnOrderPaid(NotificationRequests requests) {
        this.requests = requests;
    }

    @ApplicationModuleListener
    void on(OrderPaid event) {
        requests.enqueueOnce(
                event.eventId(),
                event.orderId(),
                event.customerId()
        );
    }
}
~~~

`enqueueOnce` nên tạo yêu cầu gửi thông báo có định danh và trạng thái trong storage của `notifications`. Nếu việc gửi email thực tế chạy ở bước sau, phải **phân biệt hoàn tất của listener “đã tạo yêu cầu gửi” với việc email provider đã gửi xong**. Đặt đúng tiêu chí thành công giúp tránh báo rằng người dùng đã nhận email khi ứng dụng mới ghi một yêu cầu gửi.

### Consumer nhận event nhưng không nhất thiết xử lý ngay

Vì `@ApplicationModuleListener` chạy bất đồng bộ, API gọi producer có thể trả kết quả khi `loyalty` chưa cập nhật điểm. Đây là **eventual consistency**.

Ở thời điểm `orders` đã commit, có thể xảy ra:

~~~text
orders: PAID
loyalty: chưa có điểm
notifications: đã có yêu cầu gửi
reporting: đang đợi xử lý
~~~

Đó có thể là trạng thái hợp lệ trong khoảng thời gian ngắn nếu nghiệp vụ chấp nhận độ trễ. Giao diện người dùng nên thể hiện trạng thái rõ ràng, chẳng hạn “điểm thưởng đang được cập nhật”. Không nên kiểm tra bảng loyalty ngay sau HTTP response rồi kết luận event “không nhận” nếu listener vốn được xử lý bất đồng bộ.

## 7. Event Publication Registry: được giao, còn chờ và hoàn tất

**Event Publication Registry** hỗ trợ theo dõi các publication dành cho những transactional listener phù hợp. Khi được cấu hình với một repository bền vững (ví dụ tích hợp JDBC hoặc JPA thích hợp), registry có thể ghi nhận ý định giao event cho từng listener trong transaction của publisher và đánh dấu hoàn tất sau khi listener xử lý thành công.

Quan trọng: **trạng thái “đã nhận” trong mô tả sau là một mốc logic**, không phải lời khẳng định mọi phiên bản hoặc repository Spring Modulith đều có cột/enum `RECEIVED`. Schema và API trạng thái cụ thể phụ thuộc phiên bản và integration được chọn.

| Mốc logic | Ý nghĩa cho một publication | Điều gì có thể xảy ra tiếp? |
| --- | --- | --- |
| **Dự kiến giao** | Registry ghi ý định giao cho listener khi publisher phát event trong transaction | Transaction nguồn có thể commit hoặc rollback |
| **Đã commit và còn chờ** | Bản ghi publication tồn tại bền vững sau commit | Listener được kích hoạt hoặc tiến trình bị dừng |
| **Đã bắt đầu xử lý** | Listener được gọi với payload | Có thể thành công, lỗi hoặc bị dừng giữa chừng |
| **Hoàn tất** | Listener trả về thành công theo cơ chế theo dõi và registry ghi completion | Công việc của publication đó được xem là hoàn thành |
| **Chưa hoàn tất sau lỗi/crash** | Không có bằng chứng completion | Cần điều tra và có thể resubmit theo chiến lược phục hồi |

Một event có **nhiều transactional listener** có thể dẫn đến **nhiều publication tương ứng**. Khi `loyalty` thành công nhưng `notifications` lỗi, trạng thái hoàn tất của `loyalty` không thể được dùng để coi `notifications` cũng đã xử lý.

~~~mermaid
sequenceDiagram
    participant O as orders
    participant DB as Database
    participant R as Publication Registry
    participant L as loyalty listener
    participant N as notifications listener

    O->>DB: Cập nhật Order (T1)
    O->>R: publishEvent(OrderPaid)
    R->>DB: Ghi publication cho L và N trong T1
    O->>DB: Commit T1
    par Sau commit
        R-->>L: Giao OrderPaid
        L->>DB: Ghi điểm (T2)
        L-->>R: Hoàn tất thành công
        R->>DB: Đánh dấu publication L hoàn tất
    and
        R-->>N: Giao OrderPaid
        N-->>R: Lỗi trước khi hoàn tất
        Note over R,N: Publication N còn chưa hoàn tất
    end
~~~

Sơ đồ thể hiện mô hình có registry bền vững **đã được cấu hình phù hợp**. Các lời gọi đến listener sau commit không nhất thiết xảy ra trước hoặc sau HTTP response theo một thứ tự cố định.

**Không tự động đánh đồng registry với broker:** registry theo dõi việc giao trong cơ chế Spring Modulith; nó không phải một Kafka topic, không có cùng ngữ nghĩa offset/partition/consumer group, và không tự chuyển `OrderPaid` đến ứng dụng khác chạy ngoài JVM.

### Khoảng trống quan trọng: listener làm xong nhưng registry chưa kịp ghi

Giả sử `loyalty` đã commit điểm thưởng, nhưng JVM dừng **trước khi bản ghi publication được đánh dấu hoàn tất**. Khi khởi động lại, registry có thể vẫn xem publication đó còn chờ. Một lần resubmit sẽ giao **cùng event** cho listener lần nữa.

Vì vậy:

- Hoàn tất business side effect và ghi completion của registry **có thể là hai thao tác không nguyên tử với nhau**.
- **At-least-once** là mô hình thiết kế an toàn khi có cơ chế giao lại.
- Consumer phải được thiết kế **idempotent** để lần giao lại không tạo thêm tác động.
- Nếu side effect là email hoặc HTTP ngoài hệ thống, phải đánh giá khả năng đã thành công bên ngoài nhưng chưa được ghi nhận ở trong.

## 8. Vì sao nhận event cần idempotency?

Cùng `OrderPaid(eventId = E1)` có thể đến consumer hai lần. Một cách làm sai là tăng số điểm trực tiếp ở mỗi lần gọi:

~~~java
void on(OrderPaid event) {
    balance.addPoints(10); // Nhận lại E1 sẽ cộng thêm 10 điểm.
}
~~~

Consumer đúng hơn cần một dấu hiệu đã xử lý **được lưu bền vững**. Ví dụ một ledger:

~~~sql
CREATE TABLE loyalty_awards (
    award_id BIGINT PRIMARY KEY,
    source_event_id VARCHAR(36) NOT NULL,
    customer_id VARCHAR(36) NOT NULL,
    points INTEGER NOT NULL,
    CONSTRAINT uq_loyalty_awards_event UNIQUE (source_event_id)
);
~~~

Trong **một transaction consumer**, xử lý cần bảo đảm rằng chỉ một lần chèn ledger cho `source_event_id` có thể dẫn tới cập nhật điểm. Có thể dùng cơ chế insert có xử lý xung đột của database hoặc unique constraint với nhánh “đã có thì bỏ qua”, đồng thời giữ thao tác ghi điểm trong cùng transaction.

~~~text
on(OrderPaid E1):
    BEGIN TRANSACTION
    thử ghi ledger với source_event_id = E1.eventId
    nếu đã có:
        kết thúc an toàn (hiệu ứng đã được xử lý)
    nếu chèn mới thành công:
        áp dụng điểm thưởng theo quy tắc
    COMMIT
~~~

Đây là **pseudocode**, không phải API Spring Modulith. Các thao tác phải được triển khai có tính nguyên tử theo database thực tế. Chỉ thực hiện `SELECT exists` rồi `INSERT` mà không có unique constraint vẫn có race condition khi hai worker xử lý trùng đồng thời.

### Hai kiểu trùng phải phân biệt

| Loại trùng | Ví dụ | Nơi xử lý chính |
| --- | --- | --- |
| **Cùng event được giao lại** | `eventId = E1` xuất hiện lần hai sau resubmit | Consumer chống trùng theo eventId/handler hoặc khóa hiệu ứng |
| **Hai event khác nhau cho cùng nghiệp vụ** | Webhook thanh toán lặp làm producer phát `E1`, `E2` cho cùng paymentId | Producer chống transition lặp; consumer có thể thêm khóa nghiệp vụ nếu phù hợp |

Chống trùng bằng `eventId` không tự bảo vệ trường hợp producer tạo ra hai eventId khác nhau cho cùng thanh toán. Vì vậy ở producer cũng cần kiểm soát input lặp và transition dựa trên payment reference hoặc một khóa nghiệp vụ phù hợp.

Đối với `notifications`, nếu listener chỉ ghi **yêu cầu gửi** thì có thể chống trùng trong database riêng. Khi gửi email thật, nhà cung cấp có thể đã chấp nhận email nhưng tiến trình ngắt trước lúc lưu trạng thái; cần idempotency key nếu provider hỗ trợ, hoặc chiến lược reconciliation và công bố rõ giới hạn giao hàng trùng.

## 9. Lỗi khi nhận và xử lý: ai chịu trách nhiệm?

Các lỗi thường gặp không giống nhau, nên cần phân loại trước khi retry.

| Tình huống | Dấu hiệu | Hướng xử lý |
| --- | --- | --- |
| **Listener không được đăng ký** | Không thấy phương thức nhận được gọi; có thể không có publication phù hợp | Kiểm tra bean scan, annotation, kiểu tham số và application context |
| **Không có transaction phù hợp** | `@TransactionalEventListener` không chạy | Kiểm tra producer có transaction thật, phase và fallbackExecution |
| **Producer rollback** | Không có phản ứng hậu commit | Đây là hành vi mong muốn; kiểm tra nguyên nhân rollback |
| **Consumer thiếu dữ liệu/hợp đồng sai** | Deserialize hoặc logic nghiệp vụ lỗi, nếu có lớp lưu/đọc event | Sửa contract, dữ liệu hoặc cách diễn giải; tránh retry vô hạn lỗi vĩnh viễn |
| **Database consumer tạm mất kết nối** | Listener ném exception sau commit | Giữ publication chưa hoàn tất và retry sau khi khôi phục |
| **Side effect đã xảy ra nhưng completion lỗi** | Event có thể bị giao lại | Idempotency; kiểm tra trạng thái tác động thực tế |
| **Consumer xử lý rất chậm** | Publication còn mở lâu, độ trễ tăng | Theo dõi bottleneck, giới hạn đồng thời và cảnh báo |
| **Event bị giao lệch thứ tự** | Projection nhận trạng thái mới trước trạng thái cũ | Thiết kế version/transition guard hoặc điều phối thứ tự |
| **Exception bị bắt rồi bỏ qua** | Registry có thể đánh dấu thành công dù nghiệp vụ thất bại | Chỉ trả thành công khi tiêu chí hoàn tất đã đạt; ném lỗi cần retry |

Ví dụ **không nên làm**:

~~~java
@ApplicationModuleListener
void on(OrderPaid event) {
    try {
        ledger.grantOnce(event.eventId(), event.orderId(), event.customerId());
    } catch (Exception failure) {
        log.warn("Cannot award points", failure);
        // Nuốt lỗi: hạ tầng có thể coi listener đã hoàn thành.
    }
}
~~~

Với lỗi khiến điểm thưởng chưa được ghi, cần cho phép exception được ghi nhận như một lần xử lý thất bại, hoặc chuyển công việc sang một hàng đợi/yêu cầu bền vững thuộc consumer theo quy trình được định nghĩa. Đừng nuốt exception rồi hy vọng registry vẫn biết phải retry.

### Retry không đồng nghĩa tự động, vô hạn và an toàn

Spring Modulith hỗ trợ theo dõi publication chưa hoàn tất, nhưng **cần cấu hình lưu trữ và chính sách phục hồi/resubmit phù hợp**. Cách kích hoạt resubmission, các API vận hành, cấu hình khởi động lại và hành vi mặc định có thể thay đổi theo phiên bản, vì vậy phải kiểm tra dependency đang dùng.

Một chính sách vận hành nên trả lời:

1. Publication lỗi được phát hiện từ đâu và sau bao lâu?
2. Lỗi nào có thể thử lại ngay, lỗi nào nên chờ với backoff, lỗi nào phải sửa dữ liệu?
3. Ai chịu trách nhiệm giới hạn retry để không gây quá tải?
4. Khi nào cảnh báo hoặc đưa publication vào luồng xử lý thủ công?
5. Cách xác minh side effect trước khi giao lại nếu trạng thái hoàn tất không chắc chắn?
6. Dấu hiệu nào chứng minh resubmit đã xử lý xong mà không tạo tác động trùng?

**Không sửa thủ công trạng thái publication thành “hoàn tất” chỉ để xóa cảnh báo** khi chưa xác định kết quả nghiệp vụ.

## 10. Nhận event không mặc định bảo đảm thứ tự

Giả sử `orders` lần lượt phát `OrderPaid` rồi `OrderRefunded`. Consumer `reporting` có thể nhận các event với độ trễ khác nhau vì bất đồng bộ, lỗi hoặc retry. Một publication cũ được giao lại sau khi publication mới đã được xử lý.

~~~mermaid
sequenceDiagram
    participant O as orders
    participant R as reporting listener
    O-->>R: OrderPaid (version 2)
    Note over R: Tạm lỗi; chưa hoàn tất
    O-->>R: OrderRefunded (version 3)
    R->>R: Cập nhật trạng thái REFUNDED
    O-->>R: Resubmit OrderPaid (version 2)
    R->>R: Bỏ qua cập nhật trạng thái cũ không hợp lệ
~~~

Đây là kịch bản minh họa rủi ro **out-of-order**, không phải cam kết Spring Modulith luôn đảo thứ tự. Nếu dữ liệu của consumer yêu cầu một tiến trình tuyến tính, dùng version tăng dần theo aggregate, điều kiện transition, optimistic locking hoặc workflow có điều phối rõ ràng. `occurredAt` giúp phân tích nhưng **timestamp một mình không đủ để bảo đảm thứ tự** khi đồng hồ lệch, độ phân giải thấp hoặc transaction commit theo thứ tự khác.

Không nên ngầm dựa vào thứ tự chạy của listener, tên method hay tốc độ thread để thực thi một bất biến nghiệp vụ.

## 11. Quan sát việc nhận: log nào thực sự có giá trị?

Một dòng log `Received event E1` hữu ích để biết listener đã bắt đầu, nhưng không đủ chẩn đoán vì sao sau đó khách hàng không có điểm thưởng. Nên quan sát xuyên các mốc.

| Tín hiệu | Ghi ở đâu? | Câu hỏi nó trả lời |
| --- | --- | --- |
| `eventId`, `eventType`, `orderId` | Producer và mỗi consumer | Sự kiện nào đang được xét? |
| `publishedAt` hoặc timestamp publication | Hạ tầng/event log | Publish xảy ra khi nào? |
| `listenerName`, `receivedAt`, `attempt` | Consumer | Ai đã nhận, ở lần thứ mấy? |
| `processedAt`, `outcome` | Consumer/ledger | Hiệu ứng đã hoàn tất chưa? |
| Publication chưa hoàn tất | Registry/storage | Những listener nào còn công việc? |
| Tuổi publication cũ nhất | Monitoring | Có công việc bị kẹt lâu không? |
| Retry/error count theo listener | Log và metric | Lỗi nào lặp lại và ở đâu? |
| Duplicate suppressed | Consumer | Idempotency có đang chặn nhận trùng? |
| Correlation/trace ID | Các điểm giao nhận | Có thể lần theo một request tới từng consumer không? |

Hạn chế log toàn bộ payload có dữ liệu cá nhân hoặc dữ liệu thanh toán. `eventId` và định danh nghiệp vụ có quyền truy cập phù hợp thường đủ để tìm kiếm, đặc biệt khi có structured logging và tracing.

### Ba mức xác nhận nên phân biệt trong dashboard

- **Published**: producer đã đưa event tới cơ chế publish; chưa chứng minh nguồn commit hoặc consumer thành công.
- **Received/started**: listener đã bắt đầu lần xử lý; chưa chứng minh hiệu ứng.
- **Completed**: tiêu chí thành công của listener đã đạt và nếu dùng registry, publication tương ứng đã được đánh dấu hoàn tất.

Nếu ứng dụng cần phân biệt **đã ghi yêu cầu gửi email** với **email provider đã chấp nhận** và **người nhận đã nhận email**, phải đặt tên trạng thái chính xác. Listener hoàn tất không tự chứng minh email đã đến hộp thư.

## 12. Kiểm thử việc nhận event

Kiểm thử cần chứng minh cả **bạn đã phát đúng event**, **listener thực thi đúng pha** và **hiệu ứng consumer đúng kể cả khi giao lại**. Có thể dùng các công cụ Spring Modulith như `@ApplicationModuleTest`, `PublishedEvents`, `Scenario` và `ApplicationModules.verify()` theo phiên bản/phụ thuộc của dự án.

### Ma trận tối thiểu

| Bài kiểm thử | Cách thiết lập | Kỳ vọng |
| --- | --- | --- |
| Đăng ký listener | Khởi chạy Spring context chứa consumer | Listener phù hợp được phát hiện |
| Producer phát event | Thanh toán hợp lệ lần đầu | Có một `OrderPaid` đúng ID/contract |
| Input trùng | Gửi lại cùng paymentId | Không có transition mới hoặc eventId nghiệp vụ mới sai |
| `@EventListener` đồng bộ | Publish khi T1 chưa commit | Listener được gọi theo cấu hình đồng bộ |
| Rollback | Publish rồi chủ động rollback T1 | Listener `AFTER_COMMIT` không tạo side effect |
| Commit | Cho T1 commit thật | Listener `@ApplicationModuleListener` xử lý trong transaction phù hợp |
| Consumer lỗi | Ném exception khi ghi ledger | T1 vẫn commit; publication có thể vẫn chưa hoàn tất khi registry được cấu hình |
| Giao lại cùng event | Resubmit cùng eventId hai lần | Chỉ một hiệu ứng điểm thưởng |
| Crash trước completion | Hoàn tất side effect rồi mất kết nối trước completion | Recovery không cộng điểm lần hai |
| Nhiều listener | Cho notifications thành công, loyalty lỗi | Trạng thái hai consumer được quan sát riêng |
| Module boundary | Consumer thử import kiểu internal của producer | `ApplicationModules.verify()` phát hiện vi phạm |

Ví dụ kiểm tra kiến trúc:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ShopArchitectureTests {

    @Test
    void modulesRespectBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

`ShopApplication` là lớp ứng dụng minh họa nằm ở package gốc phù hợp. Kiểm tra cấu trúc giúp xác nhận consumer chỉ dùng API công khai, nhưng không chứng minh việc giao event sau commit hay registry hoạt động.

### Hai bẫy kiểm thử phổ biến

**Bẫy 1 — Transaction test tự rollback.** Test có `@Transactional` ở cấp phương thức/lớp thường được rollback khi kết thúc. Listener `AFTER_COMMIT` có thể không bao giờ được gọi. Muốn kiểm chứng sau commit, hãy tạo kịch bản khiến transaction nguồn **thực sự commit** và kiểm tra hiệu ứng sau đó.

**Bẫy 2 — Dùng thời gian ngủ cố định.** Listener `@ApplicationModuleListener` bất đồng bộ nên `Thread.sleep(100)` có thể khiến test lúc pass lúc fail. Hãy dùng công cụ chờ theo **điều kiện nghiệp vụ với timeout**, chẳng hạn hỗ trợ kiểm thử kịch bản của Spring Modulith khi phù hợp, hoặc polling có giới hạn thời gian.

Muốn chứng minh Event Publication Registry bền vững, cần test tích hợp với storage thật hoặc tương đương: publication được ghi khi commit; không được ghi khi rollback; listener lỗi để lại publication chưa hoàn tất; resubmit sau khi sửa lỗi hoàn tất mà không nhân đôi tác dụng. Mock riêng `ApplicationEventPublisher` không thể chứng minh các tính chất này.

## 13. Khi listener không nhận event: quy trình chẩn đoán

Một sự cố “publish nhưng không nhận” nên được chẩn đoán theo các lớp, bắt đầu từ sự thật gần nhất có thể quan sát.

~~~mermaid
flowchart TD
    A["Có bằng chứng producer publish đúng loại?"] -->|Không| B["Kiểm tra transition, điều kiện và đường gọi producer"]
    A -->|Có| C{"Bean listener có được đăng ký?"}
    C -->|Không| D["Kiểm tra component scan, annotation, kiểu tham số"]
    C -->|Có| E{"Listener transactional?"}
    E -->|Không| F["Kiểm tra multicaster và exception đồng bộ"]
    E -->|Có| G{"Transaction nguồn commit thật?"}
    G -->|Không| H["Kiểm tra rollback / publish ngoài transaction"]
    G -->|Có| I{"Listener đã bắt đầu?"}
    I -->|Không| J["Kiểm tra cấu hình async, executor và publication"]
    I -->|Có| K{"Consumer commit hiệu ứng?"}
    K -->|Không| L["Xem lỗi business/DB, publication chưa hoàn tất"]
    K -->|Có| M["Xem completion registry và idempotency"]
~~~

Thứ tự kiểm tra thực tế:

1. Xác định **eventId**, loại event, `orderId` và đường gọi producer. Bảo đảm producer thực sự tạo event cho một transition hợp lệ.
2. Kiểm tra listener là **Spring bean**, có annotation và chữ ký đúng; package nhận được component scan.
3. Phân biệt `@EventListener` với transactional listener, kiểm tra transaction nguồn có tồn tại và commit hay không.
4. Xem hạ tầng async/executor nếu listener chạy bất đồng bộ, cùng lỗi khởi tạo bean hoặc cấu hình event.
5. Với registry, kiểm tra publication tương ứng có tồn tại, đã hoàn tất hay còn chờ. Đừng dùng việc thiếu publication để khẳng định Spring không phát nếu registry chưa được cấu hình.
6. Nếu listener có log bắt đầu nhưng không có hiệu ứng, tập trung vào transaction consumer, exception, idempotency và storage của consumer.
7. Nếu listener đã tạo side effect nhưng completion còn chờ, tránh phát lại mù quáng: xác minh idempotency rồi mới resubmit theo chính sách vận hành.

**Không nên sửa bằng cách chuyển hết listener sang `@EventListener` đồng bộ** chỉ để nhìn thấy log ngay. Điều đó có thể thay đổi thời điểm xử lý, làm lỗi lan về producer và tạo side effect trước commit.

## 14. Bài thực hành: chứng minh nhận event và khôi phục sau lỗi

### Đề bài

Ứng dụng đặt vé có module `payments`, `tickets`, `notifications`. Khi thanh toán được xác nhận và transaction nguồn commit, `payments` phát `PaymentCompleted`. `tickets` tạo vé, `notifications` tạo yêu cầu gửi email.

Yêu cầu: không phát hành vé cho transaction rollback; không phát hành vé hai lần nếu cùng event được giao lại; khi `tickets` lỗi sau commit, hệ thống biết có publication chưa hoàn tất và có khả năng xử lý lại.

### Các bước thực hiện

1. **Thiết kế contract:** tạo `PaymentCompleted(eventId, paymentId, reservationId, occurredAt)` ở public API của `payments`. Ghi rõ event chỉ hợp lệ khi thanh toán đã được xác nhận.
2. **Tạo producer:** dùng `ApplicationEventPublisher` trong phương thức transaction, sau khi thật sự chuyển trạng thái thanh toán. Chống callback trùng theo `paymentId`.
3. **Tạo hai listener:** `@ApplicationModuleListener` tại `tickets` và `notifications`. Mỗi listener chỉ import contract công khai từ `payments`.
4. **Định nghĩa “hoàn tất” riêng:** `tickets` hoàn tất khi vé và khóa xử lý được commit; `notifications` hoàn tất khi yêu cầu gửi được lưu hợp lệ.
5. **Thử rollback:** ném exception trước commit tại producer; xác nhận không có vé và không có yêu cầu email từ listener hậu commit.
6. **Bật publication persistence:** cấu hình một integration registry bền vững được hỗ trợ bởi phiên bản Spring Modulith đang dùng.
7. **Gây lỗi consumer:** để `tickets` ném exception sau commit; xác minh `payments` vẫn hoàn tất nghiệp vụ, `notifications` có thể thành công và publication của `tickets` chưa hoàn tất.
8. **Khôi phục:** sửa lỗi, resubmit theo cơ chế được cấu hình; kiểm tra vé được phát hành và publication hoàn tất.
9. **Thử nhận trùng:** đưa cùng `eventId` vào consumer hai lần; kiểm tra ràng buộc idempotency không tạo vé thứ hai.
10. **Quan sát:** lưu eventId, listener name, thời điểm nhận, trạng thái xử lý, tuổi publication chưa hoàn tất và số lần thử.

### Tình huống suy luận

Giả sử event `PaymentCompleted(E42)` được publish trong transaction T1. T1 commit lúc 10:00:01. `tickets` nhận E42 lúc 10:00:02, commit vé lúc 10:00:03 nhưng JVM dừng trước khi publication được đánh dấu hoàn tất. Sau restart, E42 được giao lại lúc 10:01:00.

**Câu hỏi 1: Lần đầu đã “nhận” event chưa?** Có, listener đã được gọi và đã tạo hiệu ứng nghiệp vụ. Tuy vậy registry có thể chưa ghi nhận completion.

**Câu hỏi 2: Có nên tạo một vé mới khi nhận lại E42 không?** Không. `tickets` phải nhận ra hiệu ứng đã tồn tại nhờ khóa bền vững như `paymentId`, `reservationId` hoặc `eventId` theo quy tắc phát hành, và kết thúc an toàn.

**Câu hỏi 3: Cùng lúc `notifications` đã hoàn tất thì có phải làm lại thông báo không?** Không thể suy ra như vậy. Mỗi listener cần được theo dõi theo publication riêng; tác vụ đã hoàn tất nên được giữ nguyên.

**Câu hỏi 4: Nếu T1 rollback, lý do gì khiến listener hậu commit không tạo vé?** Vì pha AFTER_COMMIT không xảy ra; publication ghi trong transaction nguồn cùng rollback khi storage được cấu hình phù hợp.

**Câu hỏi 5: Nếu ứng dụng không bật registry bền vững, sau crash có chắc tìm lại được E42 không?** Không. Chỉ có event trong bộ nhớ và annotation listener không đủ để bảo đảm phục hồi sau restart.

## 15. Checklist khi thiết kế và kiểm tra bước nhận event

- [ ] Producer chỉ phát event cho một sự thật nghiệp vụ có ý nghĩa và đúng transition.
- [ ] Event contract được công bố qua API module; consumer không import dữ liệu nội bộ của producer.
- [ ] Listener là Spring bean được quét và được đăng ký đúng loại event.
- [ ] Biết rõ listener chạy đồng bộ, sau commit hay bất đồng bộ.
- [ ] Không dùng `publishEvent()` trả về làm chứng cứ mọi consumer đã xử lý.
- [ ] Có transaction nguồn đúng khi dùng transactional listener.
- [ ] Có test rollback chứng minh consumer hậu commit không tạo side effect.
- [ ] Consumer dùng transaction phù hợp và xác định rõ tiêu chí hoàn tất.
- [ ] Phân biệt listener bắt đầu với side effect commit và publication completion.
- [ ] Có storage Event Publication Registry khi cần khôi phục công việc sau crash.
- [ ] Có chính sách phát hiện/resubmit publication chưa hoàn tất; không mặc định retry vô hạn.
- [ ] Có idempotency cho cùng event được giao lại và producer chống transition nghiệp vụ lặp.
- [ ] Không phụ thuộc thứ tự listener bất đồng bộ khi nghiệp vụ cần thứ tự chặt chẽ.
- [ ] Ghi log/metric theo eventId, listener, trạng thái, retry và độ trễ.
- [ ] Kiểm thử nhiều consumer trong tình huống một bên thành công, một bên thất bại.
- [ ] Không nhầm cơ chế nhận event nội bộ với message broker liên tiến trình.

## Ghi nhớ

Trong **chu kỳ phát hành** của Spring Modulith, bước **nhận event** bắt đầu khi một listener phù hợp được gọi với event đã publish. `@EventListener` thường nhận đồng bộ trong lúc publish; `@TransactionalEventListener` có thể đợi một pha transaction; `@ApplicationModuleListener` hỗ trợ xử lý sau commit, bất đồng bộ và trong transaction riêng. Vì vậy cần biết rõ **listener nhận lúc nào** trước khi quyết định một side effect có an toàn hay không.

Độ tin cậy còn phụ thuộc vào những gì xảy ra **sau khi listener bắt đầu**. Event Publication Registry, khi có storage bền vững và cơ chế khôi phục phù hợp, giúp theo dõi publication chưa hoàn tất; retry có thể giao lại event; idempotency giúp consumer không nhân đôi tác động. Kiểm thử commit/rollback, lỗi sau commit và phục hồi, cùng observability theo từng consumer, là cơ sở để khẳng định giao tiếp giữa các module được thực hiện đáng tin cậy.

