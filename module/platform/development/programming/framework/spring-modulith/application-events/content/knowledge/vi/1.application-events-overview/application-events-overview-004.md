# Producer và consumer

Trong **Spring Modulith**, một ứng dụng có thể chia thành nhiều module nghiệp vụ chạy chung trong một tiến trình Spring Boot. Các module cần phối hợp mà vẫn bảo vệ ranh giới: module xử lý thanh toán không nên phải gọi trực tiếp mọi module gửi thông báo, tích điểm, xuất hóa đơn hay cập nhật báo cáo. **Application events** cho phép module phát thông báo về một sự việc đã xảy ra; các module nhận tự quyết định cách phản ứng.

Bài học thuộc chương **Tổng quan ứng dụng sự kiện**, tập trung vào hai vai trò cốt lõi của **SPRING_MODULITH_APPLICATION_EVENTS**: **producer** (bên phát sự kiện) và **consumer** (bên xử lý sự kiện). Qua một tình huống thanh toán đơn hàng, ta sẽ thực hành publish, đăng ký listener, chọn thời điểm xử lý sau commit, nhận diện rủi ro mất hoặc lặp việc, sử dụng event publication registry, kiểm thử và quan sát dòng sự kiện.

## 1. Producer và consumer là ai?

Giả sử hệ thống thương mại điện tử có các module **orders**, **notifications**, **loyalty** và **analytics**. Khi một đơn hàng được xác nhận đã thanh toán, những việc tiếp theo có thể là gửi thông báo, ghi điểm thưởng và cập nhật báo cáo doanh thu.

| Thành phần | Vai trò | Sở hữu những gì? | Không cần biết những gì? |
| --- | --- | --- | --- |
| **Producer** | Phát ra sự kiện từ một thay đổi nghiệp vụ do mình kiểm soát | Quy tắc tạo sự kiện, thời điểm phát, hợp đồng sự kiện thuộc API module | Danh sách listener và cách mỗi listener thực thi |
| **Event** | Chuyển tải thông tin về sự thật đã xảy ra | Tên, ý nghĩa, định danh và dữ liệu cần thiết | Các thao tác chi tiết của consumer |
| **Consumer** | Lắng nghe loại sự kiện quan tâm rồi thực hiện phản ứng của mình | Điều kiện xử lý, transaction riêng, chống trùng, lỗi và retry | Chi tiết nội bộ của producer như repository, entity hay service implementation |
| **Event infrastructure** | Phân phối event tới listener và, khi được cấu hình, ghi nhận publication | Cơ chế gọi listener, registry, theo dõi trạng thái xử lý | Quy tắc nghiệp vụ của từng module |

Trong ví dụ này:

- **orders là producer** của sự kiện **OrderPaid** sau khi ghi nhận trạng thái thanh toán hợp lệ.
- **notifications là consumer** để tạo yêu cầu gửi xác nhận thanh toán.
- **loyalty là consumer** để ghi nhận điểm thưởng.
- **analytics là consumer** để cập nhật dữ liệu báo cáo.

~~~mermaid
flowchart LR
    Client["Ứng dụng khách"] --> Orders["orders<br/>Producer"]
    Orders --> Event(("OrderPaid"))
    Event --> Notifications["notifications<br/>Consumer"]
    Event --> Loyalty["loyalty<br/>Consumer"]
    Event --> Analytics["analytics<br/>Consumer"]
~~~

Sơ đồ thể hiện **một producer, nhiều consumer**. Đây là kiểu *publish/subscribe*: mỗi listener phù hợp đều có thể nhận cùng một event. Nó không đồng nghĩa với một hàng đợi nơi nhiều worker cạnh tranh lấy một message để chỉ một worker xử lý. Nếu có ba listener cho **OrderPaid**, hệ thống có ba phản ứng riêng, mỗi phản ứng cần được theo dõi và bảo vệ khỏi xử lý trùng.

### Sự khác biệt với gọi service trực tiếp

Khi gọi trực tiếp, producer phải chỉ định service đích:

~~~java
// Minh họa phụ thuộc trực tiếp, không phải mẫu khuyến nghị
orderRepository.save(order);
notificationService.notifyPayment(order);
loyaltyService.addPoints(order);
analyticsService.recordRevenue(order);
~~~

Mỗi tính năng mới có thể buộc sửa module **orders**. Khi phát sự kiện, module **orders** chỉ công bố điều đã xảy ra:

~~~java
orderRepository.save(order);
events.publishEvent(new OrderPaid(/* dữ liệu sự kiện */));
~~~

Sau này, module **fraud-monitoring** có thể bổ sung listener mà không yêu cầu **orders** gọi thêm service. Dù vậy, consumer vẫn phải phụ thuộc vào **hợp đồng OrderPaid**: cấu trúc và ý nghĩa của event là một API cần được quản lý cẩn thận.

## 2. Event contract: producer và consumer thỏa thuận điều gì?

Đặt tên event bằng **sự kiện đã xảy ra** trong nghiệp vụ, thường ở thì quá khứ: **OrderPaid**, **PaymentCaptured**, **ShipmentDispatched**. Tên cần phản ánh mốc nghiệp vụ chính xác.

**OrderPaid** chỉ phù hợp khi đơn đã được xác nhận thanh toán theo quy tắc hệ thống. Nếu mới nhận yêu cầu thanh toán nhưng chưa được bên thanh toán chấp nhận, event nên có tên diễn đạt trạng thái thực tế như **PaymentRequested**, không phát **OrderPaid** quá sớm.

Một contract tương đối ổn định:

~~~java
package com.example.shop.orders;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

public record OrderPaid(
        UUID eventId,
        UUID orderId,
        UUID customerId,
        BigDecimal paidAmount,
        String currency,
        Instant occurredAt
) {}
~~~

Đây là **mã minh họa**, với lớp **OrderPaid** nằm trong package API công khai của module **orders**. Vì Java **record** bất biến ở mức tham chiếu field, nó phù hợp để vận chuyển dữ liệu sự kiện; tuy nhiên nếu field tham chiếu đến một đối tượng có thể thay đổi, cần tự bảo vệ tính bất biến sâu của payload.

| Field | Ý nghĩa | Tại sao consumer cần? |
| --- | --- | --- |
| **eventId** | ID riêng của một lần xảy ra sự kiện | Log, correlation và chống xử lý trùng |
| **orderId** | ID của đơn hàng | Liên hệ sự kiện với đơn; có thể dùng để đọc API công khai hoặc dữ liệu projection |
| **customerId** | ID khách hàng | Xác định đối tượng thông báo hoặc điểm thưởng |
| **paidAmount** | Số tiền đã được ghi nhận cho lần thanh toán | Phản ứng cần snapshot số tiền ở thời điểm phát event |
| **currency** | Đơn vị tiền của số tiền | Tránh diễn giải sai khi nhiều loại tiền |
| **occurredAt** | Thời điểm producer tạo thông tin event | Đo độ trễ và phục vụ truy vết, không phải bảo đảm thứ tự tuyệt đối |

Không truyền entity JPA đang quản lý, lazy proxy, service Spring hay toàn bộ object graph của đơn hàng. Một consumer chỉ cần ID và một vài thông tin snapshot có ý nghĩa. Dữ liệu thay đổi sau khi event xảy ra không nên làm thay đổi ý nghĩa lịch sử của event đã phát.

**Contract bao gồm cả ngữ nghĩa, không chỉ các field Java.** Producer phải nói rõ: khi nào phát event, có thể phát lại hay không, số tiền phản ánh thời điểm nào, một đơn có thể có nhiều **OrderPaid** không, và consumer phải làm gì khi nhận lại cùng **eventId**.

### Event khác command như thế nào?

- **Command: SendPaymentEmail** hướng một yêu cầu vào hành vi cụ thể của notifications.
- **Event: OrderPaid** báo rằng nghiệp vụ thanh toán đã đạt một mốc. Notifications có thể gửi email; loyalty có thể cộng điểm; analytics có thể cập nhật báo cáo.

Nếu producer phát một event giả dạng command để điều khiển từng bước trong consumer, phụ thuộc nghiệp vụ vẫn còn. Nên chọn tên theo **sự thật producer sở hữu**, còn phản ứng thuộc về consumer.

## 3. Producer: ghi nhận nghiệp vụ và phát event

Producer trong Spring sử dụng **ApplicationEventPublisher**. Trong Spring Modulith, cơ chế application event này là nền tảng để các module giao tiếp với nhau.

~~~java
package com.example.shop.orders;

import java.time.Clock;
import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderPaymentService {

    private final OrderRepository orders;
    private final ApplicationEventPublisher events;
    private final Clock clock;

    public OrderPaymentService(
            OrderRepository orders,
            ApplicationEventPublisher events,
            Clock clock
    ) {
        this.orders = orders;
        this.events = events;
        this.clock = clock;
    }

    @Transactional
    public void recordVerifiedPayment(
            UUID orderId,
            VerifiedPayment payment
    ) {
        Order order = orders.findById(orderId).orElseThrow();

        // Phương thức nghiệp vụ minh họa: true khi trạng thái
        // thực sự chuyển sang PAID, false nếu đã ghi nhận cùng giao dịch.
        boolean transitioned = order.markPaidIfNew(payment.reference());
        if (!transitioned) {
            return;
        }

        events.publishEvent(new OrderPaid(
                UUID.randomUUID(),
                order.getId(),
                order.getCustomerId(),
                payment.amount(),
                payment.currency(),
                clock.instant()
        ));
    }
}
~~~

**Các lớp Order, OrderRepository và VerifiedPayment là kiểu miền minh họa**, cần được triển khai trong module **orders**. Đoạn code giả định receipt thanh toán đã được xác thực trước khi gọi phương thức này; nó không thực hiện thanh toán với bên ngoài. Với JPA, thay đổi entity managed được ghi lại khi transaction commit; nếu dùng một kiểu repository khác, có thể phải gọi thao tác lưu tường minh.

Producer cần thực hiện bốn việc:

1. **Kiểm tra điều kiện nghiệp vụ**: đã nhận kết quả thanh toán hợp lệ, đơn tồn tại và transition được phép.
2. **Thay đổi trạng thái nguồn** theo transaction: chuyển đơn sang **PAID** một lần có kiểm soát.
3. **Tạo event có ngữ nghĩa đúng**: chỉ khi transition xảy ra; dùng **eventId** mới cho lần thay đổi mới.
4. **Publish trong cùng transaction nghiệp vụ** khi muốn một registry bền vững có thể gắn publication với commit của trạng thái nguồn.

**Gọi publishEvent không đồng nghĩa event đã được consumer xử lý.** Với các listener thông thường, có thể có xử lý ngay trong luồng publish; với listener hậu commit, xử lý chỉ diễn ra sau khi transaction thành công. Producer không nên suy ra “đã gửi email” hoặc “đã cộng điểm” chỉ từ việc **publishEvent(...)** trả về.

Nếu xử lý thanh toán cần tránh ghi nhận trùng từ webhook, module **orders** cần idempotency riêng cho webhook hoặc payment reference. **eventId** giúp consumer nhận lại một sự kiện, còn payment reference giúp producer không phát một sự kiện nghiệp vụ mới cho cùng một giao dịch thanh toán lặp lại.

## 4. Consumer: đăng ký listener và sở hữu phản ứng

Trong module **loyalty**, consumer có thể nghe **OrderPaid** và tạo một bản ghi điểm thưởng.

~~~java
package com.example.shop.loyalty;

import com.example.shop.orders.OrderPaid;
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
                event.customerId(),
                event.paidAmount(),
                event.currency()
        );
    }
}
~~~

**LoyaltyLedger.awardOnce(...)** là API nghiệp vụ minh họa của module **loyalty**, không phải API do Spring Modulith cung cấp. Nó nên thực thi việc kiểm tra/chèn bản ghi điểm trong cùng transaction và có **unique constraint** để bảo đảm cùng event không tạo hai khoản điểm nếu được giao lại.

Module **notifications** có thể triển khai một consumer khác:

~~~java
package com.example.shop.notifications;

import com.example.shop.orders.OrderPaid;
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

Ở đây, **NotificationRequests.enqueueOnce(...)** biểu thị việc ghi một yêu cầu gửi thông báo vào storage của chính notifications. Worker gửi email có thể xử lý yêu cầu đó sau, với cơ chế retry/idempotency phù hợp nhà cung cấp. Việc ghi yêu cầu vào database có thể quản lý transaction tốt hơn so với gọi trực tiếp email provider rồi xem đó là hiệu ứng không thể thu hồi.

Consumer chịu trách nhiệm tự quyết định:

- Có cần phản ứng với event không? Ví dụ không gửi email nếu người dùng đã tắt loại thông báo đó.
- Có cần dữ liệu bổ sung không? Nếu có, ưu tiên API công khai hoặc projection sở hữu bởi consumer, tránh đọc repository nội bộ của producer.
- Hành vi nào được coi là thành công? Hoàn tất ghi điểm, lưu yêu cầu gửi hay nhận xác nhận từ dịch vụ ngoài?
- Nếu gặp lỗi, consumer có thể retry, xử lý trùng hoặc xử lý bù như thế nào?

Một listener chỉ nên chứa điều phối mỏng, chuyển công việc cho service của module mình. Điều này giúp kiểm thử các quy tắc nghiệp vụ độc lập với hạ tầng nhận event.

## 5. Chọn listener theo thời điểm và transaction

Spring cung cấp nhiều cách nhận cùng một loại event. Chọn đúng kiểu listener là điều quan trọng vì publisher có thể chạy trong transaction.

| Listener | Cách xử lý thường gặp | Tác động chính |
| --- | --- | --- |
| **@EventListener** | Mặc định đồng bộ ngay khi publish, có thể trước commit | Consumer nằm gần luồng gọi producer; exception có thể lan ngược và làm rollback transaction |
| **@TransactionalEventListener(phase = AFTER_COMMIT)** | Chỉ được gọi khi transaction phát event commit thành công | Tránh phản ứng cho giao dịch nguồn đã rollback; annotation này không tự động tạo thread hay transaction mới |
| **@ApplicationModuleListener** | Annotation Spring Modulith kết hợp transactional event listener, bất đồng bộ và transaction mới | Thuận tiện cho phản ứng độc lập của một module sau commit |

**@ApplicationModuleListener** là lựa chọn thường gặp khi notifications hoặc loyalty xử lý **OrderPaid** mà không cần làm chậm đường đi chính của producer. Về mặt cấu hình, annotation này kết hợp đặc tính của **@Async**, **@TransactionalEventListener** và **@Transactional** với propagation **REQUIRES_NEW**. Consumer cần thiết kế transaction riêng vì dữ liệu nguồn đã commit; thất bại ở consumer không thể rollback việc thanh toán đã hoàn tất.

### Dòng thời gian với hai listener hậu commit

~~~mermaid
sequenceDiagram
    participant Client
    participant Orders as orders / Producer
    participant DB as Database
    participant Events as Event infrastructure
    participant Loyalty as loyalty / Consumer
    participant Notify as notifications / Consumer
    Client->>Orders: recordVerifiedPayment(...)
    Orders->>DB: Ghi PAID trong T1
    Orders->>Events: publishEvent(OrderPaid)
    Events->>DB: Ghi publication trong T1 (nếu cấu hình registry)
    Orders->>DB: Commit T1
    Orders-->>Client: Trả kết quả nghiệp vụ
    par Các consumer nhận event hậu commit
        Events-->>Loyalty: on(OrderPaid)
        Loyalty->>DB: awardOnce(...) trong T2
    and
        Events-->>Notify: on(OrderPaid)
        Notify->>DB: enqueueOnce(...) trong T3
    end
    Events->>DB: Hoàn tất publication thành công
~~~

Sơ đồ là mô hình khái niệm, **không cam kết** listener luôn bắt đầu sau khi HTTP response đã trả. Các tác vụ sau commit có thể bắt đầu rất sớm. **T2** và **T3** là transaction độc lập, và hệ thống không nên giả định hai consumer hoàn thành theo thứ tự cố định.

Listener dùng **@TransactionalEventListener** mặc định không thực thi khi event được phát ngoài transaction, trừ khi chủ động dùng **fallbackExecution**. Vì vậy publisher phải thống nhất chính sách transaction, tránh khiến event “mất” chỉ vì một đường gọi không có transaction như mong đợi.

### Fan-out không đồng nghĩa với đảm bảo thứ tự

Một lần **publishEvent(OrderPaid)** có thể kích hoạt nhiều listener, nhưng:

- Không có bảo đảm mọi listener luôn thành công đồng thời.
- Một consumer lỗi không có nghĩa là trạng thái nguồn được hoàn tác khi đã commit.
- Consumer xử lý bất đồng bộ có thể hoàn tất theo thứ tự khác nhau.
- Nếu **OrderPaid** và **OrderRefunded** gần nhau, consumer phải xem xét rủi ro nhận/hoàn thành lệch thứ tự.

Khi thứ tự là bất biến nghiệp vụ, hãy mô hình hóa version, trạng thái tiến trình hoặc quy trình điều phối rõ ràng. Không dựa vào tốc độ thread hay thứ tự tình cờ của listener.

## 6. Event publication registry và bài toán consumer thất bại

**Bất đồng bộ không tự tạo độ tin cậy.** Giả sử transaction **orders** đã commit, nhưng máy chủ dừng trước khi loyalty cập nhật điểm. Nếu chỉ có event nằm trong bộ nhớ, tiến trình mới không chắc biết còn một việc phải làm.

Spring Modulith cung cấp **Event Publication Registry** để theo dõi publication của các transactional event listener được hỗ trợ. Khi tích hợp storage bền vững phù hợp, registry có thể ghi ý định giao cho từng listener trong transaction phát event. Khi listener xử lý thành công, publication tương ứng được đánh dấu hoàn tất. Nếu chưa hoàn tất, có thể truy vấn và tổ chức việc gửi lại theo chính sách khôi phục.

| Tình huống | Ý nghĩa với producer/consumer | Giải pháp cần có |
| --- | --- | --- |
| Transaction producer rollback | Không nên có phản ứng hậu commit cho trạng thái chưa được lưu | Transactional listener và publication ghi cùng transaction nguồn |
| Producer commit, JVM dừng trước khi consumer xử lý | Việc sau commit có nguy cơ thất lạc | Publication repository bền vững và cơ chế resubmit |
| Consumer ném exception | Phản ứng chưa hoàn thành | Giữ publication chưa hoàn tất, ghi lỗi, retry có kiểm soát |
| Consumer đã tạo hiệu ứng nhưng crash trước khi đánh dấu xong | Cùng event có thể được giao lại | Idempotency trong consumer |
| Consumer lỗi vĩnh viễn vì dữ liệu không hợp lệ | Retry vô hạn không giải quyết vấn đề | Phân loại lỗi, cảnh báo, sửa dữ liệu/quy trình vận hành |
| Một consumer thành công, consumer khác thất bại | Chỉ một nhánh phản ứng còn dang dở | Theo dõi trạng thái theo từng publication/listener, không coi tất cả như một bước nguyên tử |

Để có registry bền vững cần **cấu hình module lưu trữ publication thích hợp**, chẳng hạn tích hợp JDBC hoặc JPA theo phiên bản Spring Modulith và database đang dùng. Phải kiểm tra cả cơ chế tái phát publication chưa hoàn tất; việc dùng annotation listener **không đồng nghĩa** có retry vô hạn hoặc một broker bền vững tự động.

Cơ chế này phù hợp với mức bảo đảm xử lý có thể **giao lại**. Consumer cần chuẩn bị tinh thần rằng cùng một event được xử lý hơn một lần. **Exactly-once side effect xuyên nhiều hệ thống** không thể suy ra chỉ từ registry.

## 7. Idempotency: làm sao tránh xử lý trùng?

Giả sử consumer loyalty thực hiện:

~~~java
// Không an toàn nếu event bị giao lại
balance.setPoints(balance.getPoints() + 10);
~~~

Nếu event được giao hai lần, khách có thể nhận 20 điểm. Ngay cả khi listener chỉ được gọi một lần trong thử nghiệm đơn giản, restart và retry có thể làm hành vi khác đi.

Một cách triển khai là thiết kế **ledger** có khóa duy nhất cho sự kiện đã xử lý:

~~~sql
CREATE TABLE loyalty_awards (
    id BIGINT PRIMARY KEY,
    source_event_id VARCHAR(36) NOT NULL,
    customer_id VARCHAR(36) NOT NULL,
    points INTEGER NOT NULL,
    CONSTRAINT uq_loyalty_awards_event UNIQUE (source_event_id)
);
~~~

Trong cùng một transaction consumer, cố gắng ghi ledger cho **source_event_id** trước khi cập nhật số điểm. Nếu bản ghi đó đã tồn tại, trả về kết quả đã xử lý thay vì cộng điểm lần nữa. Dùng **unique constraint** ở database để tránh race condition khi hai worker nhận cùng event đồng thời; chỉ dùng câu lệnh **SELECT trước rồi INSERT** không đảm bảo an toàn trong cạnh tranh.

Nếu có nhiều loại ledger xử lý cùng event, khóa có thể là cặp **(consumer_name, event_id)**. Chọn khóa dựa trên *một tác động nghiệp vụ được phép xảy ra bao nhiêu lần*. Đôi khi idempotency theo **paymentReference** hoặc **orderId + transition** mới là đúng, đặc biệt khi producer vô tình phát ra **hai eventId khác nhau** cho cùng một thao tác nguồn.

Với gửi email hay gọi API ngoài, cần xét kịch bản “bên ngoài đã thực hiện nhưng consumer chưa ghi nhận hoàn tất”. Dùng idempotency key nếu provider hỗ trợ, hoặc ghi yêu cầu gửi và trạng thái xử lý riêng, đồng thời xác định rõ giới hạn chống gửi trùng. Database trong ứng dụng không thể tự rollback một email đã được gửi.

## 8. Bảo vệ ranh giới module và quản lý contract

Với cấu trúc module minh họa:

~~~text
com.example.shop
├── orders
│   ├── OrderPaid.java
│   ├── OrderPaymentService.java
│   └── internal
│       └── OrderRepositoryImpl.java
├── loyalty
│   ├── AwardPointsOnOrderPaid.java
│   └── internal
│       └── LoyaltyLedgerImpl.java
└── notifications
    ├── NotifyOnOrderPaid.java
    └── internal
        └── NotificationRequestsImpl.java
~~~

Trong ví dụ, **OrderPaid** nằm tại package gốc công khai của **orders**, để **loyalty** và **notifications** được phép tham chiếu. Nếu contract đặt ở subpackage riêng, cần khai báo API cho subpackage đúng theo cơ chế **named interface** của Spring Modulith khi cần. Các consumer không nên import lớp từ **orders.internal**.

~~~mermaid
flowchart LR
    OrdersAPI["orders public API<br/>OrderPaid"]
    OrdersPrivate["orders.internal<br/>Entity, Repository"]
    Loyalty["loyalty"]
    Notify["notifications"]
    Loyalty --> OrdersAPI
    Notify --> OrdersAPI
    OrdersPrivate -. "không công khai" .- Loyalty
    OrdersPrivate -. "không công khai" .- Notify
~~~

Các nguyên tắc giữ contract ổn định:

1. **Công khai có chủ ý**: giới hạn những kiểu mà module khác được tham chiếu; dùng kiểm tra cấu trúc module để phát hiện phụ thuộc vi phạm.
2. **Thêm field có kiểm soát**: với Java record, thêm thành phần làm đổi constructor và có thể phá consumer phải biên dịch lại; đánh giá tương thích khi nâng phiên bản.
3. **Không thay đổi ý nghĩa thầm lặng**: chuyển **OrderPaid** từ “tiền đã thu” thành “đã gửi yêu cầu thu tiền” là thay đổi nghiệp vụ nghiêm trọng dù các field không đổi.
4. **Phân biệt domain event và integration event**: application event trong Spring Modulith là cơ chế cùng ứng dụng; khi cần gửi ra process/service khác, thường cần adapter, outbox/broker và contract giao tiếp liên hệ thống.
5. **Định nghĩa người sở hữu contract**: producer kiểm soát tên và ý nghĩa của event; mỗi consumer kiểm soát việc mình làm khi nhận.

Sự kiện không buộc tất cả các module phải phụ thuộc vào một package **shared** chung chứa mọi entity. Thường hợp lý hơn khi sự kiện thuộc **public API của module phát**, còn hạ tầng phân phối giúp consumer đăng ký phản ứng.

## 9. Kiểm thử producer và consumer theo trách nhiệm

Có ba nhóm câu hỏi khác nhau: producer có phát đúng event không, consumer có xử lý đúng không, và phối hợp qua transaction/registry có hoạt động thật không?

| Kiểm thử | Đầu vào | Điều cần xác minh |
| --- | --- | --- |
| **Producer - business transition** | Thanh toán hợp lệ làm trạng thái chuyển thành PAID | Phát đúng một **OrderPaid**, dữ liệu khớp và một eventId cho transition |
| **Producer - duplicate input** | Nhận lại webhook/payment reference đã xử lý | Không tạo transition hoặc event nghiệp vụ mới sai |
| **Producer - rollback** | Có lỗi trước commit | Không gọi listener sau commit; publication không được commit |
| **Consumer - rule** | Một **OrderPaid** phù hợp | Tạo ledger/yêu cầu thông báo theo đúng quy tắc module |
| **Consumer - duplicate** | Giao cùng **eventId** hai lần, kể cả song song | Chỉ một hiệu ứng hợp lệ; database unique key bảo vệ |
| **Integration - after commit** | Transaction producer commit | Các listener hậu commit thực hiện trong phạm vi transaction phù hợp |
| **Integration - failure/recovery** | Listener lỗi sau commit rồi được giao lại | Publication chưa hoàn tất được khôi phục, consumer hoàn thành mà không nhân đôi hiệu ứng |
| **Structure** | Quét cấu trúc các module | Consumer chỉ phụ thuộc public API cho phép |

Spring Modulith hỗ trợ **@ApplicationModuleTest** và các công cụ hỗ trợ quan sát event đã publish như **PublishedEvents** hoặc kịch bản **Scenario**. Có thể dùng kiểm tra ranh giới cấu trúc:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ArchitectureTests {

    @Test
    void modulesRespectBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Đoạn code giả định **ShopApplication** là lớp ứng dụng tại package gốc, và phụ thuộc Spring Modulith Test/Core được cấu hình tương ứng.

Khi kiểm tra listener hậu commit, cần để transaction trong test **thực sự commit**. Một bài test mặc định rollback ở cuối có thể khiến **@TransactionalEventListener** không bao giờ được gọi. Với listener bất đồng bộ, dùng cách chờ điều kiện có giới hạn thời gian thay vì **Thread.sleep** cố định. Với registry, mock publisher đơn thuần không thể chứng minh dữ liệu publication đã được ghi và hồi phục qua restart; nên có integration test dùng storage thực hoặc tương đương.

## 10. Quan sát hệ thống: từ một event đến từng consumer

Khi một đơn đã thanh toán mà điểm thưởng chưa xuất hiện, cần trả lời được: producer đã phát event chưa, transaction đã commit chưa, publication có được tạo không, listener nào nhận, listener nào lỗi, và tác dụng phụ đã hoàn thành chưa.

Gợi ý những thông tin tối thiểu:

| Dữ liệu quan sát | Mục đích |
| --- | --- |
| **eventId** và **eventType** | Liên kết log từ producer qua từng consumer |
| **orderId** hoặc business correlation ID | Tra cứu theo giao dịch nghiệp vụ cụ thể |
| **listener/module** | Biết nhánh xử lý nào đang chờ hoặc bị lỗi |
| **occurredAt**, thời điểm bắt đầu/kết thúc | Đo độ trễ từ lúc phát đến lúc hoàn tất |
| **publication status**, số publication chưa hoàn tất | Phát hiện công việc hậu commit đang tồn đọng |
| **retry count**, loại lỗi, tuổi publication cũ nhất | Cảnh báo và ưu tiên xử lý |
| **duplicate suppressed** | Theo dõi lượng event được giao lại mà idempotency đã chặn |

Không log toàn bộ event nếu payload chứa dữ liệu cá nhân hay chi tiết thanh toán nhạy cảm. Kết hợp correlation ID, tracing và các metric cho độ trễ, lỗi, số retry, tuổi publication còn mở. Để hỗ trợ vận hành, cần quy trình tìm publication chưa hoàn tất, xử lý nguyên nhân gốc rồi resubmit có kiểm soát; không tự đánh dấu “đã xử lý” chỉ để xóa cảnh báo.

## 11. Khi nào producer nên dùng event, khi nào gọi trực tiếp?

Event là cách tốt để giảm phụ thuộc khi consumer là **phản ứng độc lập** và được phép hoàn thành muộn hơn nghiệp vụ nguồn. Tuy nhiên, có nhiều trường hợp cần phối hợp đồng bộ:

| Nhu cầu | Hướng thiết kế phù hợp |
| --- | --- |
| Gửi thông báo hoặc cập nhật báo cáo sau khi đơn đã được trả tiền | Phát **OrderPaid**; consumer xử lý sau commit |
| Bắt buộc giữ kho thành công trước khi xác nhận đơn | Kiểm tra/giữ kho đồng bộ hoặc quy trình trạng thái có điều phối và xử lý bù |
| Người dùng cần phí vận chuyển trong response hiện tại | API/query đồng bộ có contract rõ |
| Muốn thêm một phản ứng mới mà không sửa logic module nguồn | Listener mới cho event đã có ý nghĩa phù hợp |
| Phải giao message ra microservice khác | Integration event và cơ chế broker/outbox phù hợp |
| Nhiều bước phải chạy theo thứ tự nghiệp vụ nghiêm ngặt | Workflow/process manager, trạng thái chuyển tiếp và sự kiện cho từng mốc |

Một producer tốt không phải producer phát càng nhiều event càng tốt. Nó phát **sự kiện có ý nghĩa rõ và gắn với trạng thái đúng**. Một consumer tốt không phải consumer chạy nhanh nhất mà là consumer có **kết quả đúng, xử lý lại được và quan sát được**.

## 12. Bài tập thực hành

Một ứng dụng đặt vé có module **reservations**, **payments**, **tickets**, **notifications** và **analytics**. Khi thanh toán thành công, hệ thống cần phát hành vé, gửi email và cập nhật báo cáo.

Hãy thực hiện lần lượt:

1. Chọn producer phù hợp cho event **PaymentCompleted**. Mô tả điều kiện đảm bảo việc thanh toán đã thực sự được ghi nhận.
2. Thiết kế một **record PaymentCompleted** gồm **eventId**, **reservationId**, **paymentId**, **occurredAt** và những trường thật sự cần thiết.
3. Viết một producer dùng **ApplicationEventPublisher** trong transaction thay đổi trạng thái thanh toán; tránh phát event mới khi nhận lại cùng webhook.
4. Viết hai consumer ở module **tickets** và **analytics** bằng **@ApplicationModuleListener**. Mỗi consumer chỉ truy cập public event contract và dữ liệu do module mình sở hữu.
5. Định nghĩa unique key để không phát hành trùng vé dù listener nhận cùng event hai lần.
6. Mô phỏng transaction producer rollback, listener tickets lỗi sau commit và restart khi còn publication chưa hoàn tất. Kiểm tra sự khác biệt giữa “producer đã commit” và “mọi consumer đã hoàn tất”.
7. Ghi metric về publication còn chờ, độ trễ và retry; giải thích cách tra cứu một payment khi có báo cáo “đã trả tiền nhưng chưa nhận vé”.

**Tình huống cần suy luận:** tickets tạo vé thành công nhưng application crash ngay trước khi registry đánh dấu publication hoàn tất. Khi hệ thống phục hồi, event có thể được giao lại. Nếu consumer có khóa duy nhất theo **paymentId** hoặc cặp khóa nghiệp vụ tương đương và xử lý transaction đúng, vé không bị nhân đôi. Nếu chỉ dựa vào giả định listener “chạy một lần”, lỗi này sẽ xuất hiện ngoài production dù các test happy-path đều xanh.

### Câu hỏi tự kiểm tra

**1. Producer có biết chính xác consumer nào đã hoàn tất ngay sau khi gọi publishEvent không?** Không. Nó chỉ thông báo event; việc consumer chạy ngay hay sau commit, đồng bộ hay bất đồng bộ, và kết quả xử lý là chuyện của cơ chế listener và các module nhận.

**2. Hai consumer nghe cùng một event có phải chỉ một consumer được chạy?** Không. Với Spring application events, nhiều listener phù hợp có thể cùng nhận một event. Mỗi listener chịu trách nhiệm riêng và có thể có trạng thái publication riêng khi được theo dõi bởi registry.

**3. Registry có bảo đảm gửi email đúng một lần không?** Không. Registry hỗ trợ ghi nhận publication chưa hoàn tất và khôi phục giao nhận khi được cấu hình đúng; tác dụng phụ ra bên ngoài vẫn có thể lặp, do đó consumer cần idempotency và thỏa thuận với nhà cung cấp dịch vụ.

**4. Consumer có nên import entity JPA nội bộ của producer cho tiện không?** Không. Consumer nên dựa trên public event contract và public API có chủ ý của producer. Như vậy mỗi module giữ được quyền sở hữu dữ liệu và mô hình nghiệp vụ riêng.

## Ghi nhớ

**Producer** sở hữu sự thật nghiệp vụ và công bố event qua **ApplicationEventPublisher**; **consumer** đăng ký listener để phản ứng trong ranh giới của module mình. Trong Spring Modulith, **@ApplicationModuleListener** hỗ trợ consumer xử lý sự kiện sau commit, bất đồng bộ và trong transaction riêng. Khi cần giao sự kiện đáng tin cậy, phải kết hợp **Event Publication Registry** đã cấu hình storage, cơ chế retry/resubmit, chống xử lý trùng, kiểm thử rollback/phục hồi và khả năng quan sát. Giữ event contract công khai, nhỏ gọn và có ý nghĩa ổn định chính là cách hai bên giao tiếp mà không làm đổ vỡ ranh giới module.
