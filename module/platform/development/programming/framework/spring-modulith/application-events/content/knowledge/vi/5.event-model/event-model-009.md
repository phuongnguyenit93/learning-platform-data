# Thời điểm phát sinh

Trong ứng dụng Spring Modulith, một sự kiện như `OrderPaid` không đơn giản là “được phát khi phương thức gọi `publishEvent()`”. Để thiết kế giao tiếp giữa các module đáng tin cậy, cần phân biệt **thời điểm một sự thật nghiệp vụ được xác lập**, **thời điểm đối tượng event được tạo**, **thời điểm publish vào cơ chế Spring**, **thời điểm transaction nguồn commit**, và **thời điểm mỗi consumer thực sự xử lý xong**.

Bài học thuộc chương **Mô hình sự kiện** của **SPRING_MODULITH_APPLICATION_EVENTS**. Phạm vi ứng dụng là tổ chức giao tiếp qua application events giữa các module Spring Modulith nhằm giảm phụ thuộc và giữ ranh giới nghiệp vụ; đặc biệt chú trọng xử lý sau commit, Event Publication Registry, retry, kiểm thử và quan sát quá trình giao sự kiện. Đặt sai thời điểm phát sinh có thể dẫn đến email xác nhận được gửi cho giao dịch đã rollback, cộng điểm khi thanh toán chưa hoàn tất, hoặc mất một tác vụ hậu commit sau khi JVM dừng.

Sau bài học, bạn phải lý giải được **event nên đại diện cho mốc nghiệp vụ nào**, event được publish **ở đâu trong transaction**, consumer được kích hoạt **ở pha nào**, và vì sao timestamp trong payload **không phải** bằng chứng rằng listener đã hoàn tất.

## 1. “Thời điểm phát sinh” có nhiều nghĩa

Xét luồng thanh toán đơn hàng. Người dùng bấm “Thanh toán”, hệ thống gọi một cổng thanh toán, nhận kết quả, ghi nhận trạng thái đơn hàng và có thể cần gửi thông báo hoặc tích điểm. Các mốc sau khác nhau:

| Mốc | Ý nghĩa | Có phải bằng chứng nghiệp vụ đã commit? |
| --- | --- | --- |
| **Yêu cầu đến** (`requestedAt`) | Server nhận yêu cầu/command hoặc webhook | Không |
| **Sự thật nghiệp vụ được xác lập trong logic** | Ứng dụng đã kiểm tra và chấp nhận chuyển trạng thái `PENDING → PAID` | Chưa; transaction vẫn có thể rollback |
| **Event được tạo** (`occurredAt` theo quy ước contract) | Tạo payload `OrderPaid` biểu diễn transition đó | Chưa |
| **Event được publish** | Gọi `ApplicationEventPublisher.publishEvent(...)` | Chưa; API publish không tự commit transaction |
| **Transaction nguồn commit** | Dữ liệu nguồn trở thành trạng thái đã commit | Có, đối với dữ liệu trong transaction nguồn |
| **Listener bắt đầu/hoàn thành** (`startedAt`, `processedAt`) | Consumer thực thi và hoàn tất phản ứng của riêng mình | Chỉ là bằng chứng của consumer tương ứng |

Các mốc này có thể cách nhau vài mili giây hoặc lâu hơn nhiều nếu listener xử lý bất đồng bộ, gặp lỗi rồi retry. Khi có nhiều consumer, **mỗi consumer có thời điểm hoàn tất riêng**; không tồn tại một thời điểm “tất cả đã xong” chỉ vì producer vừa gọi `publishEvent()`.

~~~mermaid
sequenceDiagram
    participant Client
    participant Orders as orders / Producer
    participant DB as Database
    participant Events as Event infrastructure
    participant Loyalty as loyalty / Consumer

    Client->>Orders: Xác nhận thanh toán hợp lệ
    Orders->>Orders: Kiểm tra + chuyển PENDING sang PAID
    Orders->>Orders: Tạo OrderPaid(occurredAt)
    Orders->>Events: publishEvent(OrderPaid)
    Note over Orders,Events: Event đã publish, transaction nguồn chưa chắc commit
    Orders->>DB: COMMIT transaction nguồn
    Events-->>Loyalty: Phân phối sau commit
    Loyalty->>DB: Ghi điểm trong transaction riêng
    Loyalty-->>Events: Xử lý thành công
~~~

Sơ đồ minh họa listener **sau commit**. Nếu consumer dùng `@EventListener` mặc định đồng bộ, nó có thể chạy **ngay trong lời gọi publish**, trước cả commit. Vì vậy phải xem annotation và cấu hình listener trước khi kết luận mốc xử lý.

### Hai “đồng hồ” không nên nhập làm một

- **Đồng hồ nghiệp vụ:** khi nào thanh toán/đặt hàng/hoàn tiền có hiệu lực theo quy tắc của miền nghiệp vụ?
- **Đồng hồ kỹ thuật:** khi nào event được phát, ghi vào registry, nhận, retry và xử lý xong?

Ví dụ ngân hàng xác nhận giao dịch lúc 10:00:00, webhook đến lúc 10:00:05, ứng dụng chấp nhận chuyển trạng thái lúc 10:00:06 và hệ thống gửi email lúc 10:00:08. Nếu yêu cầu nghiệp vụ cần thời gian thật của giao dịch từ nguồn thanh toán, `paidAt` có thể là 10:00:00 sau khi xác thực nguồn. Nếu chỉ cần thời điểm hệ thống ghi nhận trạng thái, `occurredAt` có thể là 10:00:06. Hai field phải có định nghĩa chính xác, không gộp lại thành một timestamp mơ hồ.

## 2. Trước hết phải chọn đúng mốc nghiệp vụ

Một event nên mô tả **sự thật đã được nghiệp vụ chấp nhận**, thay vì chỉ mô tả việc một phương thức đã được gọi. Với `OrderPaid`, mốc phù hợp có thể là *đơn đã được xác nhận thanh toán theo chính sách của orders*. Đừng tạo `OrderPaid` ngay khi người dùng nhấn nút “Thanh toán” nếu hệ thống còn chờ cổng thanh toán phản hồi.

| Tình huống | Event phù hợp | Có nên phát `OrderPaid`? |
| --- | --- | --- |
| Người dùng nhấn nút thanh toán | `PaymentRequested` nếu sự kiện này có ý nghĩa riêng | Chưa |
| Đã gửi yêu cầu tới cổng thanh toán | `PaymentSubmissionAccepted` nếu cần ghi nhận | Chưa |
| Cổng thanh toán trả trạng thái đang xử lý | `PaymentPending` nếu thật sự cần các module khác biết | Chưa |
| Nguồn thanh toán hợp lệ xác nhận thành công, đơn được chuyển `PAID` | `OrderPaid` | Có, khi thực sự có transition |
| Webhook thành công được gửi lại cho cùng payment reference | Không phát event transition mới nếu đã xử lý | Không phát lần thứ hai |
| Giao dịch sau đó bị hoàn tiền | `PaymentRefunded` hoặc `OrderRefunded` theo miền nghiệp vụ | Không dùng lại `OrderPaid` |

Quy tắc này quan trọng vì consumer thường chỉ biết **contract của event**, không biết chi tiết nội bộ của module phát. Nếu `loyalty` nhận `OrderPaid`, nó phải được phép hiểu rằng điểm thưởng đã có căn cứ nghiệp vụ để xử lý. Đổi nghĩa `OrderPaid` thành “người dùng đã yêu cầu thanh toán” sẽ phá vỡ hợp đồng dù chữ ký Java không thay đổi.

### Phát event cho transition, không cho mọi lần gọi service

Một endpoint có thể bị retry bởi client, gateway hoặc hệ thống webhook. Nếu producer tạo `OrderPaid` ở mỗi lần gọi, hai lần yêu cầu giống nhau có thể tạo **hai `eventId` khác nhau** cho cùng một payment và làm khó việc chống lặp ở consumer.

Cần bảo vệ hai tầng:

1. **Producer:** `paymentId` hoặc một khóa nghiệp vụ thích hợp giúp nhận biết transition đã được ghi nhận; chỉ phát `OrderPaid` khi trạng thái thật sự chuyển.
2. **Consumer:** `eventId` giúp nhận biết **cùng một event** được giao lại; khóa nghiệp vụ có thể bổ sung lớp bảo vệ với các event khác nhau nhưng phản ánh cùng một tác động.

Vì vậy, thời điểm phát sinh gắn với **chuyển trạng thái thực**, không gắn với số lần request hoặc số lần publish.

## 3. Thiết kế timestamp trong event contract

Một contract nên phân biệt thời gian nghiệp vụ với các mốc kỹ thuật. Ví dụ:

~~~java
package com.example.shop.orders.events;

import java.time.Instant;
import java.util.UUID;

public record OrderPaid(
        UUID eventId,
        UUID orderId,
        UUID customerId,
        UUID paymentId,
        Instant paidAt,
        Instant occurredAt
) {}
~~~

Ở ví dụ này:

- `paidAt`: thời điểm thanh toán thành công được nguồn đáng tin xác nhận, sau khi quy đổi về `Instant`. Nếu không có timestamp đủ tin cậy từ bên ngoài, hãy định nghĩa rõ thời điểm ứng dụng xác nhận thanh toán thay thế.
- `occurredAt`: thời điểm module `orders` chấp nhận **transition** nghiệp vụ và tạo event. Nó là một mốc trong luồng nghiệp vụ, **không cam kết đã commit** tại thời điểm tạo.
- `eventId`: định danh của lần phát sinh sự kiện, dùng để liên kết log/registry và xử lý trùng.
- `paymentId`: nhận diện giao dịch thanh toán gốc, cần cho tính nhất quán nghiệp vụ qua webhook lặp.

**Đừng thêm `committedAt` như một giá trị đã biết ngay khi tạo event trong transaction** nếu bạn không có nguồn xác thực thời điểm commit. Commit diễn ra **sau đó**; không thể dự đoán chính xác nó từ `Instant.now()` lúc publish. Nếu cần thời điểm hệ thống lưu bản ghi thành công, đo và ghi nó bằng cơ chế phù hợp, trình bày rõ đây là mốc kỹ thuật và không thay thế cho commit marker.

Những timestamp thường thấy nhưng **không nhất thiết nằm trong payload**:

| Timestamp | Thuộc về | Nên lưu ở đâu? |
| --- | --- | --- |
| `requestedAt` | Request/command đầu vào | Request audit hoặc trace nếu cần |
| `paidAt` | Nghiệp vụ thanh toán | Hợp đồng event nếu consumer thật sự cần |
| `occurredAt` | Transition phát event tại producer | Payload, đồng bộ với định nghĩa nghiệp vụ |
| `publishedAt` | Hạ tầng phát event | Log/metadata publication nếu cần, tránh nhầm với commit |
| `receivedAt` | Mỗi lần consumer nhận event | Log/telemetry của listener |
| `processedAt` | Consumer hoàn tất hiệu ứng | Metadata, ledger hoặc lịch sử xử lý của consumer |
| `retriedAt` | Một lần thử lại | Nhật ký retry/publication, có thể có nhiều bản ghi |

**Dùng `Instant` cho mốc tuyệt đối** để tránh mơ hồ múi giờ, đồng hồ mùa hè và `LocalDateTime` không có offset. Khi hiển thị cho người dùng, chuyển `Instant` sang múi giờ mong muốn ở tầng giao diện. Trong test, inject `Clock` để khống chế thời gian, tránh phụ thuộc đồng hồ hệ thống.

Không dùng `occurredAt` làm định danh duy nhất: độ phân giải đồng hồ không đảm bảo không trùng, các máy có thể lệch giờ và nhiều event có thể phát trong cùng một thời điểm.

## 4. Vị trí publish trong transaction nguồn

Trong Spring, `ApplicationEventPublisher` là cơ chế phát application event tới các listener đăng ký. Nó **không tự xác lập giao dịch**, không tự lưu event bền vững và không đảm bảo sau commit. Quan hệ với transaction phụ thuộc vào nơi publisher được gọi và kiểu listener đang sử dụng.

Mô hình hợp lý cho transition `OrderPaid` là:

1. Nhận và xác thực kết quả thanh toán từ nguồn có thẩm quyền.
2. Mở transaction nghiệp vụ và đọc trạng thái đơn.
3. Kiểm tra điều kiện transition; bỏ qua đầu vào trùng.
4. Cập nhật trạng thái đơn và tạo event đại diện cho transition đó.
5. Gọi `publishEvent(...)` **trong transaction còn hoạt động**, sau khi điều kiện nghiệp vụ đã được xác nhận.
6. Transaction commit. Những consumer chỉ chạy sau commit mới bắt đầu phản ứng khi transaction nguồn thành công.

### Ví dụ producer có đồng hồ kiểm soát được

~~~java
package com.example.shop.orders.internal;

import com.example.shop.orders.events.OrderPaid;
import java.time.Clock;
import java.time.Instant;
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
    public void recordVerifiedPayment(
            UUID orderId,
            VerifiedPayment payment
    ) {
        Order order = orders.findById(orderId).orElseThrow();

        // Domain method minh họa: trả false khi đã ghi nhận paymentId.
        boolean transitioned = order.markPaidIfNew(payment.id());
        if (!transitioned) {
            return;
        }

        Instant occurredAt = clock.instant();
        OrderPaid event = new OrderPaid(
                UUID.randomUUID(),
                order.getId(),
                order.getCustomerId(),
                payment.id(),
                payment.confirmedAt(),
                occurredAt
        );

        // Giả sử orders.save tham gia cùng transaction nguồn.
        orders.save(order);
        publisher.publishEvent(event);
    }
}
~~~

`Order`, `OrderRepository`, `VerifiedPayment` và `markPaidIfNew` là các thành phần nghiệp vụ minh họa cần tự triển khai. `VerifiedPayment` phải chứa thông tin **đã xác thực**, chứ không phải dữ liệu người dùng tự khai “đã thanh toán”. `payment.confirmedAt()` cần được xử lý theo quy định tin cậy về thời gian của nguồn thanh toán.

Trong cùng transaction, lệnh `save` và lệnh `publishEvent` xuất hiện liên tiếp trong mã Java, nhưng **database commit xảy ra sau khi phương thức giao dịch hoàn tất**. Vì vậy event được tạo và publish ở bước này vẫn phải được xem là **dự kiến hợp lệ nếu transaction commit thành công**.

Nếu sau `publishEvent` có exception làm transaction rollback, `OrderPaid` đã được tạo trong bộ nhớ nhưng dữ liệu `PAID` không thành công. Một listener đồng bộ có thể đã nhận event; listener sau commit sẽ không chạy cho transaction đã rollback.

### Đừng publish trước khi kiểm tra bất biến

~~~java
// Sai: công bố sự thật trước khi biết transaction/logic có thành công hay không.
publisher.publishEvent(new OrderPaid(/* ... */));
order.validatePayment(...);
order.markPaid(...);
~~~

Một consumer có thể nhìn thấy event quá sớm. Cách phù hợp là kiểm tra điều kiện và chuyển trạng thái trước, rồi publish **bên trong transaction** để subscriber hậu commit chỉ xử lý khi commit thành công.

Điều này cũng không có nghĩa phải publish **sau khi phương thức @Transactional trả về**. Nếu ứng dụng sử dụng Event Publication Registry với bản ghi publication được lưu cùng transaction nguồn, việc publish **trong** transaction là yếu tố quan trọng để lưu ý định giao event nguyên tử với thay đổi nguồn. Nếu publish ở một đoạn code chạy bên ngoài transaction, bạn có thể làm mất liên kết nguyên tử này.

## 5. Lúc publish khác lúc listener chạy

Hai listener cùng nghe `OrderPaid` có thể phản ứng ở những pha khác nhau. Bản chất của event không thay đổi, nhưng thời điểm **hành động** thay đổi đáng kể.

| Loại listener | Thời điểm xử lý thông thường | Phù hợp cho | Rủi ro phải hiểu |
| --- | --- | --- | --- |
| `@EventListener` | Với multicaster mặc định, đồng bộ trong lời gọi publish | Logic cần thực hiện ngay, quan sát bước publish | Có thể chạy trước commit; exception lan về producer |
| `@TransactionalEventListener(BEFORE_COMMIT)` | Trước khi transaction nguồn commit | Kiểm tra/chuẩn bị nội bộ có ràng buộc transaction | Vẫn có thể rollback; không an toàn cho side effect không thể hoàn tác |
| `@TransactionalEventListener(AFTER_COMMIT)` | Sau khi transaction nguồn commit thành công | Phản ứng chỉ nên có khi dữ liệu nguồn đã commit | Không tự bất đồng bộ, không mặc nhiên mở transaction mới |
| `@TransactionalEventListener(AFTER_ROLLBACK)` | Khi transaction nguồn rollback | Theo dõi/cleanup kỹ thuật có chủ đích | Không dùng để giả lập nghiệp vụ đã thành công |
| `@TransactionalEventListener(AFTER_COMPLETION)` | Sau khi transaction kết thúc, bất kể commit hay rollback | Quan sát kết thúc transaction khi cần | Phải tự phân biệt kết quả nếu tác vụ cần biết thành công |
| `@ApplicationModuleListener` | Spring Modulith hỗ trợ sau commit, bất đồng bộ và transaction riêng | Consumer độc lập giữa các module | Kết quả có thể đến muộn, thất bại hoặc bị giao lại |

`AFTER_COMMIT` là **pha mặc định** của `@TransactionalEventListener` khi không ghi `phase`. Nếu event được publish **ngoài transaction**, transactional listener mặc định không xử lý, trừ khi chủ động bật `fallbackExecution`. Cấu hình fallback phải được cân nhắc vì ý nghĩa “sau commit” không còn giống khi thực sự có transaction nguồn.

### Ví dụ đồng bộ và sau commit

~~~java
package com.example.shop.orders.internal;

import com.example.shop.orders.events.OrderPaid;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
class PaymentAuditLog {

    @EventListener
    void on(OrderPaid event) {
        // Thường gọi ngay trong publishEvent() với multicaster mặc định.
        // Không suy luận transaction nguồn đã commit.
    }
}
~~~

Một consumer khác dùng:

~~~java
package com.example.shop.notifications.internal;

import com.example.shop.orders.events.OrderPaid;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class NotifyWhenPaid {

    private final NotificationRequests requests;

    NotifyWhenPaid(NotificationRequests requests) {
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

`NotificationRequests.enqueueOnce(...)` là phương thức minh họa của module `notifications`, không phải API của Spring Modulith. Nó nên tạo yêu cầu gửi trong storage riêng theo khóa idempotency. Gửi email trực tiếp ngay trong listener có thể tạo side effect khó phục hồi nếu tiến trình dừng sau khi nhà cung cấp đã nhận email.

**Lưu ý với `AFTER_COMMIT` thuần Spring:** khi callback chạy, một số resource của transaction cũ có thể vẫn còn gắn với luồng. Nếu callback cần ghi dữ liệu mới, phải bảo đảm có transaction độc lập thích hợp (ví dụ `REQUIRES_NEW`). `@ApplicationModuleListener` giúp xử lý trường hợp này với transaction mới và thực thi bất đồng bộ theo cơ chế Spring Modulith.

## 6. Tạo event khi dữ liệu chưa commit có mâu thuẫn không?

Không, nếu hiểu **tạo event** và **xác nhận trạng thái đã commit** là hai chuyện khác nhau.

Trong transaction nguồn, module nghiệp vụ có thể đã xác định rằng transition `PAID` hợp lệ. Nó tạo event ngay tại đó để **gắn ý định phản ứng với thay đổi nguồn**. Nếu transaction thành công, event phản ánh một mốc đã được lưu; nếu rollback, consumer sau commit không được phép thực hiện phản ứng đó.

~~~mermaid
flowchart TD
    A["Nhận kết quả thanh toán đã xác thực"] --> B["Bắt đầu transaction T1"]
    B --> C{"Có transition mới sang PAID?"}
    C -->|Không| Z["Không phát OrderPaid"]
    C -->|Có| D["Cập nhật trạng thái, tạo event"]
    D --> E["publishEvent trong T1"]
    E --> F{"T1 hoàn tất?"}
    F -->|Rollback| G["Không kích hoạt listener AFTER_COMMIT"]
    F -->|Commit| H["Listener AFTER_COMMIT có thể xử lý"]
    H --> I["Consumer mở transaction riêng"]
    I --> J{"Consumer thành công?"}
    J -->|Có| K["Ghi nhận xử lý hoàn tất"]
    J -->|Không| L["Giữ việc chưa hoàn tất nếu có registry"]
~~~

**Mốc business occurrence** có thể được đặt lúc transition được chấp nhận, nhưng bằng chứng bền vững của occurrence chỉ có khi commit thành công. Vì vậy khi dùng event cho phản ứng phụ thuộc vào dữ liệu đã lưu, listener sau commit thường hợp lý hơn listener gọi trực tiếp ngay lúc publish.

Một ví dụ đối chứng:

- `OrderPaid(occurredAt=10:00:00)` được tạo và publish trong transaction lúc 10:00:00.
- Hệ thống phát hiện vi phạm ràng buộc database lúc commit và rollback lúc 10:00:01.
- Bản ghi `PAID` không tồn tại; event trong bộ nhớ từng được tạo, nhưng **không nên dẫn tới việc gửi email “đã thanh toán”**.
- Listener `@TransactionalEventListener(AFTER_COMMIT)` không được gọi, còn `@EventListener` đồng bộ trước đó có thể đã chạy.

Đây là lý do **không thể giải quyết đúng thời điểm phản ứng chỉ bằng cách đặt `occurredAt` trong payload**. Phải có cơ chế transactional listener phù hợp.

## 7. Thời điểm phát sinh trong Event Publication Registry

Khi có nhiều module consumer, việc phản ứng sau commit có thể bị gián đoạn:

1. Transaction `orders` commit thành công.
2. JVM dừng ngay trước khi `loyalty` hoàn tất.
3. Khi khởi động lại, hệ thống cần biết có publication nào còn chờ.

**Event Publication Registry** của Spring Modulith theo dõi những publication chưa hoàn tất cho transactional listener được hỗ trợ. Khi đã cấu hình **repository lưu publication bền vững** (chẳng hạn tích hợp JDBC/JPA phù hợp phiên bản và hạ tầng) và publish trong transaction nguồn, việc ghi publication có thể cùng tham gia transaction đó. Sau khi listener hoàn tất thành công, publication liên quan được đánh dấu hoàn tất; publication chưa hoàn tất cần được kiểm tra, khôi phục và resubmit theo chính sách đã cấu hình.

| Thời điểm | Publication trong thiết kế có registry bền vững |
| --- | --- |
| **Publish trong T1** | Ý định giao event cho listener được đăng ký, gắn với transaction nguồn |
| **T1 rollback** | Các publication ghi trong T1 không được commit |
| **T1 commit** | Dữ liệu nguồn và publication tương ứng đã bền vững nếu cùng transaction và storage được cấu hình đúng |
| **Listener chạy** | Consumer thực thi phản ứng, có thể thất bại hoặc mất kết nối |
| **Listener hoàn tất** | Publication của listener đó được đánh dấu hoàn tất |
| **Crash/retry** | Publication còn chưa hoàn tất có thể được xác định để xử lý lại |

Registry **không biến một lần publish thành hiệu ứng “chính xác một lần”**. Nếu `loyalty` đã cộng điểm trong database của nó nhưng JVM dừng trước lúc registry ghi completion, publication có thể được giao lại. Consumer phải thiết kế idempotency.

Một quan sát quan trọng về thời gian: **publication được tạo trước commit, nhưng chỉ bền vững sau commit** nếu transaction nguồn và publication cùng được commit. `occurredAt` trong event có thể sớm hơn thời điểm transaction commit; hoàn toàn bình thường. Đừng lấy timestamp tạo publication làm bằng chứng rằng bên nhận đã xử lý thành công.

Registry cũng không tự đảm bảo vô hạn retry cho mọi lỗi. Ứng dụng phải có chính sách tìm publication chưa hoàn tất, resubmit, phân loại lỗi, cảnh báo và xác minh tác dụng nghiệp vụ.

## 8. Thời điểm retry và xử lý trùng

Một event **phát sinh một lần** có thể được **giao nhiều lần**. Ví dụ:

| Lần | Thời gian minh họa | Điều xảy ra |
| --- | --- | --- |
| Tạo event | 10:00:00 | `eventId=E-1`, `occurredAt=10:00:00` |
| Transaction nguồn commit | 10:00:01 | `OrderPaid` trở thành sự thật đã lưu |
| Consumer nhận lần 1 | 10:00:02 | Ghi điểm thành công nhưng crash trước completion |
| Registry resubmit | 10:00:30 | Cùng `eventId=E-1`, không phải một sự thật nghiệp vụ mới |
| Consumer nhận lần 2 | 10:00:31 | Nhận ra đã xử lý, không cộng điểm tiếp |
| Publication hoàn tất | 10:00:31 | Registry ghi nhận listener đã hoàn thành |

**Đừng gán lại `occurredAt` bằng thời điểm retry.** Một lần giao lại phản ánh một sự kiện cũ, không biến sự kiện thành một occurrence mới. Ghi các thời điểm giao/lặp ở metadata hoặc log xử lý riêng.

Ví dụ schema idempotency đơn giản:

~~~sql
CREATE TABLE loyalty_award (
    id BIGINT PRIMARY KEY,
    source_event_id VARCHAR(36) NOT NULL,
    customer_id VARCHAR(36) NOT NULL,
    points INTEGER NOT NULL,
    processed_at TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT uq_loyalty_award_event UNIQUE (source_event_id)
);
~~~

`source_event_id` bảo đảm mỗi event chỉ được ghi nhận một lần trong ledger nếu logic chèn và cập nhật điểm diễn ra cùng transaction. `processed_at` là thời điểm consumer ghi hiệu ứng thành công, **khác** với `occurredAt` của producer.

Nếu cùng payment reference bị producer phát thành **hai eventId khác nhau**, idempotency theo `eventId` không đủ; producer phải ngăn transition lặp và consumer có thể cân nhắc khóa nghiệp vụ như `paymentId` tùy quy tắc. Với side effect bên ngoài như email, phải xác định liệu nhà cung cấp có hỗ trợ idempotency key hay không.

## 9. Thứ tự thời gian của nhiều event

Giả sử một đơn hàng có các event:

- `OrderPlaced` khi đơn được tạo;
- `OrderPaid` khi xác nhận thanh toán;
- `OrderRefunded` khi có giao dịch hoàn tiền.

Trong mô hình nghiệp vụ, thứ tự transition có thể là `PLACED → PAID → REFUNDED`. Tuy vậy, **thứ tự consumer xử lý** có thể khác thứ tự producer phát nếu listener chạy bất đồng bộ hoặc một publication bị retry muộn.

~~~mermaid
sequenceDiagram
    participant Orders as orders
    participant Queue as Publication/dispatch
    participant Consumer as reporting
    Orders->>Queue: OrderPaid (version 2)
    Orders->>Queue: OrderRefunded (version 3)
    Queue-->>Consumer: OrderRefunded (đến trước)
    Consumer->>Consumer: Chỉ xử lý khi trạng thái/version phù hợp
    Queue-->>Consumer: OrderPaid (đến sau)
    Consumer->>Consumer: Không được ghi lùi trạng thái xuống PAID
~~~

Sơ đồ là tình huống có thể phát sinh khi lịch xử lý, retry hoặc đường giao nhận cho phép lệch thứ tự; không phải cam kết mọi ứng dụng Spring Modulith luôn đảo thứ tự. Nếu consumer yêu cầu thứ tự nghiêm ngặt, hãy **thiết kế rõ một cơ chế bảo đảm**: version tăng dần theo aggregate, kiểm tra transition hợp lệ, kiểm soát serial processing hoặc điều phối quy trình. `occurredAt` có thể hỗ trợ phân tích, nhưng **timestamp một mình không phải khóa thứ tự đáng tin cậy** vì đồng hồ lệch giờ, độ phân giải và retry.

Đừng giả định transaction bắt đầu trước sẽ commit trước. Hai transaction cạnh tranh có thể có thời điểm bắt đầu/ghi event khác với thứ tự commit. Nếu thứ tự là bất biến nghiệp vụ, phải bảo vệ nó ở lớp dữ liệu hoặc workflow.

### Eventual consistency là một hệ quả của thời điểm xử lý

Khi `orders` commit lúc 10:00:01, `loyalty` có thể chỉ hoàn thành lúc 10:00:04. Trong khoảng đó:

- Trạng thái đơn đã `PAID`.
- Điểm thưởng trong module `loyalty` có thể chưa cập nhật.
- Reporting có thể chưa có doanh thu mới.
- Response API không nên hứa rằng mọi consumer đã hoàn tất nếu các consumer là bất đồng bộ.

Ứng dụng cần chọn mức độ nhất quán phù hợp: cập nhật ngay khi nghiệp vụ bắt buộc, hoặc hiển thị trạng thái “đang xử lý” cho các phản ứng có thể hoàn tất muộn. Nếu một bất biến bắt buộc phải đúng trước khi trả thành công, không nên đẩy toàn bộ quyết định đó sang listener bất đồng bộ mà không có cơ chế điều phối và trạng thái chuyển tiếp.

## 10. Bảo vệ ranh giới module khi mô hình hóa thời điểm

Đối với Spring Modulith, sự kiện nên thuộc **public API có chủ đích của module sở hữu sự thật nghiệp vụ**, chẳng hạn `orders.events.OrderPaid` được công bố qua named interface `orders::events`. Consumer chỉ cần ID, trạng thái và mốc thời gian được contract công bố; không được dùng repository hoặc entity nội bộ của `orders` để tự suy thời điểm xảy ra event.

~~~text
com.example.shop
├── orders
│   ├── events
│   │   ├── package-info.java  // @NamedInterface("events")
│   │   └── OrderPaid.java     // public event contract
│   └── internal
│       ├── OrderPaymentService.java  // producer
│       └── OrderRepository.java
├── loyalty
│   └── internal
│       └── OrderPaidListener.java    // consumer
└── notifications
    └── internal
        └── OrderPaidListener.java    // consumer
~~~

Nếu `loyalty` phải hỏi trực tiếp entity hiện tại của `orders` để tự suy ra `paidAt`, có thể hình thành phụ thuộc nội bộ hoặc đọc thấy dữ liệu mới hơn thời điểm event. Hãy cân nhắc đưa snapshot cần thiết vào event hoặc công bố một query API có chủ đích. Chọn dữ liệu event theo **ý nghĩa tại thời điểm phát sinh**, không theo trạng thái “mới nhất” vốn có thể đã thay đổi.

Producer chịu trách nhiệm xác định `OrderPaid` **đã xảy ra theo nghiệp vụ khi nào**. Consumer chịu trách nhiệm ghi `receivedAt`, `processedAt` và trạng thái công việc của mình. Việc tách quyền sở hữu này giúp bảo vệ ranh giới và tránh một module thao túng thời gian nghiệp vụ của module khác.

## 11. Kiểm thử thời điểm phát sinh và giao sự kiện

Các lỗi liên quan thời điểm thường không lộ trong test chỉ xác minh `publishEvent()` được gọi. Cần kiểm chứng mốc nghiệp vụ, transaction, listener và cơ chế phục hồi.

| Kiểm thử | Cách tạo tình huống | Điều kiện PASS |
| --- | --- | --- |
| **Transition hợp lệ** | Thanh toán hợp lệ cho đơn đang PENDING | Chỉ tạo đúng event `OrderPaid` với ID và thời gian phù hợp |
| **Request lặp** | Gửi lại cùng payment reference | Không tạo occurrence nghiệp vụ hoặc eventId mới không cần thiết |
| **Clock xác định** | Inject `Clock.fixed(...)` | `occurredAt` đúng mốc được chọn |
| **Rollback sau publish** | Ném exception trước commit | Listener `AFTER_COMMIT` không tạo hiệu ứng; dữ liệu nguồn rollback |
| **Commit thành công** | Cho transaction nguồn commit | Consumer hậu commit xử lý trên dữ liệu đã được commit |
| **Publish ngoài transaction** | Phát từ nơi không có transaction | Biết rõ hành vi listener transactional mặc định và xử lý fallback nếu được cấu hình |
| **Consumer lỗi sau commit** | Listener ném exception | Trạng thái nguồn đã commit không bị rollback theo |
| **Registry bền vững** | Commit rồi làm hỏng listener | Publication chưa hoàn tất còn có thể phát hiện |
| **Retry cùng event** | Giao cùng `eventId` hai lần | Chỉ một hiệu ứng nghiệp vụ; `occurredAt` không bị thay đổi |
| **Lệch thứ tự** | Xử lý `OrderRefunded` trước `OrderPaid` | Projection không ghi lùi trạng thái không hợp lệ |

Với Spring Modulith, có thể dùng `@ApplicationModuleTest`, `PublishedEvents`, `Scenario` và kiểm tra `ApplicationModules.verify()` cho các nhu cầu tương ứng. Các test kiểm tra **sau commit** phải để transaction thực sự commit. Một test bọc `@Transactional` rồi rollback ở cuối thường không kích hoạt listener `AFTER_COMMIT` như dự kiến.

Ví dụ tạo clock kiểm soát được:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

Clock fixedClock = Clock.fixed(
        Instant.parse("2026-01-15T10:00:00Z"),
        ZoneOffset.UTC
);
// Inject fixedClock vào producer và kiểm tra event.occurredAt().
~~~

Không dùng `Thread.sleep` cố định để suy đoán listener bất đồng bộ đã hoàn tất. Với listener async, hãy đợi **điều kiện nghiệp vụ quan sát được** trong một khoảng giới hạn và báo lỗi nếu không hội tụ.

## 12. Quan sát thời điểm để phát hiện lỗi

Để trả lời câu hỏi “đơn đã thanh toán nhưng chưa cộng điểm”, cần liên kết nhiều mốc thời gian và trạng thái của từng consumer. Tối thiểu nên có:

| Trường/tín hiệu | Mục đích |
| --- | --- |
| `eventId`, `eventType`, `orderId`, `paymentId` | Liên kết sự kiện và nghiệp vụ |
| `occurredAt`, `paidAt` | Phân biệt mốc nghiệp vụ với thời điểm nguồn ngoài |
| `listenerName`, `receivedAt`, `processedAt` | Tìm consumer chậm hoặc chưa hoàn tất |
| Số publication chưa hoàn tất | Phát hiện công việc tồn đọng |
| Tuổi publication còn mở | Xác định công việc bị kẹt lâu |
| Số lần retry và lỗi theo listener | Phát hiện lỗi lặp, retry quá mức |
| Độ trễ từ `occurredAt` đến completion | Đánh giá eventual consistency theo SLO nghiệp vụ |

**Không diễn giải độ trễ âm hoặc timestamp lệch nhau như bằng chứng tuyệt đối về thứ tự.** Đồng hồ các máy có thể không đồng bộ; với đo thời gian thực thi trong cùng tiến trình có thể dùng công cụ đo monotonic duration, còn timestamp là mốc thời gian tuyệt đối để tra cứu. Nếu đo xuyên nhiều hệ thống, cần đồng bộ đồng hồ và chấp nhận sai số.

Một quy trình điều tra ví dụ:

1. Tìm `OrderPaid` theo `paymentId` và `eventId`.
2. Xác nhận transaction nguồn đã commit và đơn ở trạng thái phù hợp.
3. Kiểm tra publication của từng listener để biết nhánh nào hoàn tất.
4. Xem lần nhận gần nhất, loại lỗi, độ tuổi publication và số lần retry.
5. Nếu side effect bên ngoài có thể đã thực hiện, kiểm tra idempotency/trạng thái thực tế trước khi resubmit.
6. Sau khôi phục, xác nhận consumer hoàn tất và hiệu ứng nghiệp vụ đúng một lần.

Việc in `occurredAt` ra console chỉ là một phần rất nhỏ của quan sát; không thay thế được publication registry, log có correlation ID, metric và quy trình phục hồi.

## 13. Bài thực hành: xác nhận thanh toán, rollback và retry

### Đề bài

Ứng dụng bán vé có ba module:

- `payments`: xác nhận thanh toán và phát `PaymentCompleted`;
- `tickets`: phát hành vé sau khi thanh toán đã commit;
- `notifications`: tạo yêu cầu gửi email khi vé đã được phát hành hoặc khi đã thanh toán, tùy ranh giới nghiệp vụ đã thiết kế.

Hãy xác định chính xác các mốc sau: `paidAt` từ nguồn thanh toán, `occurredAt` khi transition được chấp nhận, `publishedAt` nếu có trong metadata, thời điểm commit, thời điểm `tickets` nhận event và thời điểm vé được lưu thành công.

### Các bước

1. **Định nghĩa hợp đồng.** Tạo `PaymentCompleted(eventId, paymentId, reservationId, paidAt, occurredAt)`, mô tả nguồn và ý nghĩa của mỗi thời điểm.
2. **Thiết kế producer.** Trong transaction, chỉ phát event khi payment reference được ghi nhận thành công lần đầu; dùng `Clock` inject được.
3. **Đặt listener phù hợp.** `tickets` dùng `@ApplicationModuleListener` để chỉ tạo vé sau commit, trong transaction xử lý riêng.
4. **Kiểm chứng rollback.** Tạo lỗi trước commit; xác nhận không có vé hoặc email được tạo từ phản ứng hậu commit.
5. **Kiểm chứng lặp.** Gửi callback trùng payment reference; xác nhận producer không tạo occurrence mới.
6. **Cấu hình publication registry.** Chọn storage bền vững phù hợp ứng dụng; làm listener lỗi sau commit và quan sát publication chưa hoàn tất.
7. **Khôi phục.** Resubmit sau khi khắc phục lỗi; nhận lại cùng `eventId` và xác minh vé không bị phát hành trùng.
8. **Thử đảo thứ tự.** Nếu hệ thống có hoàn tiền/hủy vé, xác định cơ chế không ghi lùi trạng thái khi event đến muộn.
9. **Đo độ trễ.** Ghi nhận thời gian từ `occurredAt` đến `processedAt` và giải thích sai số do đồng hồ/transaction.

### Tình huống suy luận

Giả sử event `PaymentCompleted` được tạo lúc 14:00:00 nhưng transaction chỉ commit lúc 14:00:03. Listener `tickets` bắt đầu lúc 14:00:04, ghi vé lúc 14:00:05. Sau đó registry không kịp đánh dấu completion vì JVM dừng, và event được giao lại lúc 14:01:00.

**Câu hỏi 1: thời điểm phát sinh của PaymentCompleted nên thay thành 14:01:00 không?** Không. Đó là thời điểm giao lại, còn occurrence nghiệp vụ của event là mốc cũ.

**Câu hỏi 2: có thể kết luận vé đã được phát hành ở 14:00:00 không?** Không. `occurredAt` của payment không nói về thời điểm `tickets` hoàn tất; cần tra ledger/trạng thái vé tại consumer.

**Câu hỏi 3: nếu transaction nguồn rollback ở 14:00:03 thì consumer hậu commit có được phát hành vé không?** Không. Nếu có hiệu ứng, cần xem lại annotation listener, đường gọi ngoài transaction hoặc việc side effect được thực hiện trước commit.

**Câu hỏi 4: resubmit lúc 14:01:00 có an toàn không?** Chỉ khi consumer idempotent, có thể kiểm tra tác dụng thực tế và không tạo vé trùng nếu trước đó đã hoàn tất nhưng chưa đánh dấu publication.

## 14. Checklist thiết kế thời điểm phát sinh

- [ ] Định nghĩa mốc nghiệp vụ mà tên event diễn đạt.
- [ ] Không phát event “đã thành công” khi mới chỉ có request hoặc trạng thái PENDING.
- [ ] Producer chỉ phát event khi một transition hợp lệ thực sự xảy ra.
- [ ] Có cơ chế ngăn input lặp ở producer và event lặp ở consumer.
- [ ] Phân biệt `paidAt` (nếu có), `occurredAt`, thời điểm publish, commit, nhận và xử lý.
- [ ] Không dùng thời điểm tạo event để khẳng định transaction đã commit.
- [ ] Publish trong transaction nguồn khi cần gắn publication bền vững với nghiệp vụ.
- [ ] Chọn listener hậu commit cho các side effect chỉ hợp lệ sau khi dữ liệu nguồn commit.
- [ ] Nếu consumer cần ghi database sau commit, sử dụng transaction phù hợp.
- [ ] Kiểm thử rollback, commit, publish ngoài transaction và consumer lỗi.
- [ ] Có registry/storage và đường resubmit khi cần bảo đảm phục hồi sau restart.
- [ ] Không thay đổi `occurredAt` khi retry cùng event.
- [ ] Không dựa vào timestamp để bảo đảm thứ tự giữa các event.
- [ ] Quan sát trạng thái publication, độ trễ và lỗi theo từng consumer.

## Ghi nhớ

Trong mô hình sự kiện của Spring Modulith, **thời điểm phát sinh** trước hết là **mốc nghiệp vụ làm cho sự kiện trở thành sự thật có ý nghĩa**, không phải thời điểm một listener nhận được lời gọi. Event thường được tạo và publish **bên trong transaction nguồn** sau khi transition hợp lệ, còn dữ liệu nguồn chỉ được xác nhận bền vững khi transaction **commit**. `@TransactionalEventListener(AFTER_COMMIT)` và `@ApplicationModuleListener` giúp consumer phản ứng sau commit, trong khi Event Publication Registry được cấu hình phù hợp hỗ trợ theo dõi việc giao còn dang dở.

`occurredAt` phải giữ nguyên cho cùng một lần xảy ra khi event được giao lại. **Received, processed, retried** là các mốc khác, thuộc từng lần giao và từng consumer. Việc phân biệt rõ các thời điểm này, kết hợp retry có kiểm soát, idempotency, kiểm thử rollback và observability, là nền tảng để các module Spring Modulith giao tiếp đáng tin cậy mà vẫn bảo vệ ranh giới nghiệp vụ.
