# Theo dõi từng listener bằng Event Publication Registry trong Spring Modulith

## 1. Vì sao phải theo dõi đến từng listener?

Một application event trong Spring Modulith có thể được phát **một lần** nhưng được **nhiều listener** xử lý. Khi `orders` xác nhận đơn hàng và phát `OrderConfirmed`, ba module khác nhau có thể phản ứng:

- `notifications` gửi thông báo xác nhận.
- `reporting` xây dựng dữ liệu báo cáo doanh số.
- `loyalty` cộng điểm thưởng cho khách hàng.

Nếu `notifications` xử lý thành công, `reporting` lỗi database và `loyalty` đang chờ executor, câu hỏi “event này đã xong chưa?” **không có một câu trả lời yes/no cho toàn bộ hệ thống**. Cần biết **listener nào đã hoàn tất, listener nào chưa hoàn tất và listener nào cần được xử lý lại**.

Đó là trọng tâm của bài **Theo dõi từng listener**, thuộc chương **Publication Registry**, trong module học `SPRING_MODULITH_APPLICATION_EVENTS`. Module này tập trung tổ chức giao tiếp giữa các Spring Modulith application modules bằng application events để giảm phụ thuộc, bảo vệ boundary và cải thiện khả năng phát, nghe, xử lý sau commit, retry, kiểm thử và quan sát giao sự kiện đáng tin cậy.

### 1.1. Một event, ba trách nhiệm độc lập

~~~mermaid
flowchart LR
    P[orders: OrderConfirmed E-100] --> R[(Event Publication Registry)]
    R --> N[Publication P-N: notifications]
    R --> B[Publication P-B: reporting]
    R --> L[Publication P-L: loyalty]
    N --> NC[Completed]
    B --> BF[Failed / incomplete]
    L --> LC[Chưa có bằng chứng completed]
~~~

Sơ đồ dùng các nhãn trạng thái **mang tính khái niệm**. Registry thực tế có thể lưu các mốc thời gian, danh tính target hoặc trạng thái với cấu trúc khác tùy phiên bản Spring Modulith và persistence backend. Không mặc định có một enum `FAILED` hoặc `IN_PROGRESS` tương ứng cho từng mũi tên.

**Điểm cần nhớ:** event là **sự thật nghiệp vụ được phát ra**; publication là **nghĩa vụ giao sự thật đó cho một listener/target được quản lý**. Một event có thể liên quan tới nhiều publication.

### 1.2. Khi nào cách theo dõi này hữu ích?

Theo dõi từng listener đặc biệt quan trọng khi:

1. Những listener cập nhật dữ liệu ở các module khác nhau và có transaction riêng.
2. Listener chạy bất đồng bộ hoặc hậu commit.
3. Một listener gặp lỗi nhưng các listener khác vẫn phải hoạt động bình thường.
4. Có nhu cầu resubmit đúng publication thất bại mà không xử lý lại toàn bộ phản ứng.
5. Ứng dụng khởi động lại khi một số publication chưa hoàn tất.
6. Vận hành cần phát hiện backlog theo module, listener và độ tuổi công việc.
7. Một event được externalize ra broker nhưng consumer bên ngoài có trạng thái xử lý riêng.

Không phải mọi event nội bộ đều cần registry. Một `@EventListener` đồng bộ chỉ tính toán thông tin phụ, không có yêu cầu khôi phục, có thể không cần lưu publication. Chọn mức độ bền vững theo **hậu quả của việc mất một lần xử lý**, không theo việc dự án có sử dụng Spring Modulith hay không.

## 2. Phân biệt event, publication, listener và target

Để đọc số liệu registry đúng, cần phân biệt bốn khái niệm:

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Event** | Object mô tả một sự thật nghiệp vụ | `OrderConfirmed(eventId=E-100)` |
| **Listener** | Method/thành phần nhận loại event đó | `ReportingOrderListener.on(...)` |
| **Target identifier** | Danh tính đích mà cơ chế publication sử dụng để liên kết publication với listener | Danh tính tương ứng listener reporting theo phiên bản framework |
| **Publication** | Bản ghi theo dõi một event dành cho một target cụ thể | P-B: E-100 → reporting listener |

Một listener đăng ký nhận nhiều **event khác nhau** có thể có nhiều publication. Một event được nhiều listener nhận cũng có thể có nhiều publication. Vì vậy, chỉ dùng `eventType` hoặc `orderId` để đánh giá hoàn tất là thiếu chính xác.

### 2.1. Phân biệt các loại ID

~~~text
Order:
  orderId = O-17

Event:
  eventId = E-100
  orderId = O-17

Publications:
  P-N: event E-100 -> notifications target
  P-B: event E-100 -> reporting target
  P-L: event E-100 -> loyalty target
~~~

**`orderId`** định danh aggregate; một đơn có thể phát nhiều event và có nhiều lần đổi trạng thái.

**`eventId`** là định danh do ứng dụng đặt trong event contract (nếu thiết kế có trường này), hữu ích để correlation và idempotency. Không mặc định Spring Modulith sử dụng chính field này làm khóa primary của registry.

**Publication ID** (nếu backend lưu bản ghi với ID riêng) định danh một nghĩa vụ xử lý. Nó không đồng nghĩa với `eventId`, bởi event E-100 có thể được giao cho ba target khác nhau.

**Target identifier** giúp liên kết bản ghi publication với listener đích. Cách biểu diễn và xác định identifier là chi tiết phải đối chiếu API/version của Spring Modulith; không tự giả định nó luôn bằng tên class Java.

### 2.2. Tại sao không dùng một cờ processed trên event?

Giả sử thêm `processed = true` vào record event sau khi `notifications` xử lý xong. Điều này tạo ngộ nhận:

- `reporting` vẫn lỗi nhưng event đã bị đánh dấu “xử lý xong”.
- `loyalty` chưa hoàn tất cũng có thể bị bỏ qua.
- Retry một target độc lập khó hơn vì không biết chính xác ai cần xử lý.
- Không thể phân tích downtime theo module từ một cờ chung.

Cách hiểu đúng là **hoàn tất theo từng publication**, và khi cần một kết quả tổng hợp, phải tính trên **tập target kỳ vọng**.

## 3. Publication Registry ghi nhận điều gì?

Spring Modulith cung cấp cơ chế **Event Publication Registry** để theo dõi những publication dành cho transactional event listeners mà nó quản lý, khi backend lưu trữ phù hợp được cấu hình.

Về mặt logic, một publication có thể được xem xét theo:

- **Event được phát:** kiểu và dữ liệu event cần thiết cho xử lý.
- **Target:** listener nào có trách nhiệm nhận event.
- **Registration/publication time:** khi công việc được đăng ký.
- **Completion:** công việc của target được ghi nhận hoàn tất hay chưa.
- **Dữ liệu vận hành khác:** tùy backend/version có thể có ID, thời điểm hoàn tất hoặc thông tin trạng thái bổ sung.

Không nên mặc định registry luôn lưu sẵn số lần retry, nội dung exception hoặc một trạng thái “đang chạy” bền vững. Một số metric và nhật ký lỗi cần được ứng dụng hoặc hệ thống quan sát bên ngoài bổ sung.

### 3.1. Các mốc lifecycle liên quan tới một listener

~~~mermaid
sequenceDiagram
    participant Orders as orders
    participant TX as Business transaction
    participant Reg as Publication Registry
    participant Report as reporting listener
    participant DB as Reporting data

    Orders->>TX: Begin + confirm order
    Orders->>Reg: Register publication cho reporting
    Orders->>TX: Commit
    alt Commit thành công
        Reg-->>Report: Event được dispatch sau commit
        Report->>DB: Cập nhật projection
        alt Listener thành công
            DB-->>Report: Commit/ack phù hợp
            Report-->>Reg: Completion qua cơ chế framework
        else Listener lỗi hoặc bị gián đoạn
            Note over Reg,Report: Publication chưa có dấu completed
        end
    else Rollback
        Note over TX,Reg: Publication của transaction rollback không được commit nếu dùng cùng TX đúng cách
    end
~~~

Đây là sơ đồ **ngữ nghĩa**, không phải cam kết thứ tự callback và API nội bộ giống nhau ở mọi phiên bản. Đặc biệt, việc publication được ghi nguyên tử với nghiệp vụ phụ thuộc **backend và transaction manager** mà dự án thực sự sử dụng.

### 3.2. Những trạng thái nên diễn giải thận trọng

| Quan sát | Kết luận an toàn | Điều không được suy ra |
| --- | --- | --- |
| Có publication, chưa completed | Target chưa có bằng chứng hoàn tất theo registry | Listener chưa từng bắt đầu chạy |
| Publication completed | Công việc của target được ghi nhận thành công theo contract listener | Hệ thống ngoài chắc chắn đã thực hiện tác vụ end-to-end |
| Không thấy publication incomplete | Hiện không thấy backlog chưa hoàn tất theo cách truy vấn | Event chắc chắn đã được đăng ký và giao đúng |
| Publication biến mất khỏi store | Có thể do chính sách lưu trữ/dọn dữ liệu | Mặc nhiên là xử lý thành công |
| Một target completed, target khác incomplete | Hai trách nhiệm có kết quả khác nhau | Event toàn cục “đã hoàn tất hết” |

Nhiều backend/version có cách lưu giữ publication hoàn tất khác nhau; một query chỉ đọc “incomplete” không đủ để xác nhận **có bao nhiêu publication đã từng được đăng ký**.

## 4. Điều kiện tiên quyết để theo dõi từng listener

Không thể quan sát một công việc chưa được đăng ký. Trước khi dựa vào registry, hãy xác nhận các điều kiện:

1. Publisher phát event trong transaction nghiệp vụ đúng ngữ nghĩa.
2. Listener được Spring đăng ký và thuộc loại **transactional event listener được registry quản lý**.
3. Đã cấu hình một backend event publication có persistence phù hợp, ví dụ JDBC/JPA/MongoDB nếu được phiên bản dự án hỗ trợ.
4. Backend có khả năng ghi publication bền vững và tham gia transaction tương thích nếu cần atomicity với dữ liệu nghiệp vụ.
5. Các dependency auto-configuration, transaction manager và serialization đã được kiểm tra thực tế.
6. Có chính sách quan sát, truy vấn publication chưa hoàn tất và resubmit khi cần.

### 4.1. Listener nào thường được theo dõi?

`@ApplicationModuleListener` là lựa chọn phổ biến trong Spring Modulith. Nó kết hợp ngữ nghĩa listener hậu commit, bất đồng bộ và transaction xử lý riêng. Các `@TransactionalEventListener` tương ứng cũng có thể thuộc phạm vi quản lý publication tùy cơ chế tích hợp/phiên bản.

Ngược lại, một `@EventListener` đồng bộ thông thường **không tự biến thành publication bền vững** chỉ vì ứng dụng có dependency Spring Modulith.

| Cách xử lý | Có thể cần theo dõi bằng registry? | Cần kiểm tra |
| --- | --- | --- |
| `@EventListener` đồng bộ cho logic nhẹ | Không phải mục tiêu mặc định của registry | Exception, độ trễ, transaction hiện tại |
| `@TransactionalEventListener(AFTER_COMMIT)` | Có thể thuộc phạm vi quản lý | Registry backend, transaction, completion |
| `@ApplicationModuleListener` | Thường là use case chính | Async executor, transaction riêng, retry và idempotency |
| Externalization adapter | Có thể được theo dõi như target gửi message | Semantics gửi broker, cấu hình externalizer |
| Consumer thuộc microservice ngoài | Không thuộc registry nội bộ producer | ACK/offset và trạng thái phía consumer riêng |

Nếu listener chạy trong application context nhưng registry luôn trả về không có bản ghi, hãy **kiểm tra wiring và phạm vi hỗ trợ** trước khi tuyên bố rằng backlog bằng 0 có nghĩa hệ thống khỏe.

### 4.2. Transaction nguồn rất quan trọng

Một mẫu thường dùng:

~~~java
@Transactional
public void confirm(UUID orderId) {
    Order order = orders.findById(orderId).orElseThrow();
    order.requireCanConfirm();
    order.confirm();
    publisher.publishEvent(new OrderConfirmed(
        UUID.randomUUID(), orderId, clock.instant()
    ));
}
~~~

`Order`, `orders` và `clock` là thành phần minh họa của ứng dụng. Khi method bị gọi qua Spring transaction proxy, transaction nguồn có thể ghi cả thay đổi nghiệp vụ và publication theo cấu hình backend phù hợp.

**Bẫy:** `@Transactional` có thể không được áp dụng nếu gọi method nội bộ cùng bean qua `this.confirm(...)` trong AOP proxy mặc định. Nếu event được phát ngoài transaction, các transactional listener có thể không chạy khi `fallbackExecution` không bật.

### 4.3. Đừng bật fallback để “chữa” việc thiếu transaction

`@TransactionalEventListener` có tùy chọn `fallbackExecution = true` để xử lý khi không có transaction. Tuy nhiên, như vậy **không có commit nguồn để ràng buộc**. Nếu hệ thống yêu cầu sự kiện chỉ phản ánh trạng thái đã lưu bền, phải sửa entry point/transaction thay vì bật fallback một cách tùy tiện.

## 5. Ví dụ thực tế: ba target theo dõi độc lập

Giả sử ứng dụng modular monolith có những application modules:

~~~text
com.example.shop
├── ShopApplication.java
├── orders
│   ├── events
│   │   ├── package-info.java
│   │   └── OrderConfirmed.java
│   └── internal
│       └── OrderManagement.java
├── notifications
│   └── internal
│       └── ConfirmationNotificationListener.java
├── reporting
│   └── internal
│       └── SalesProjectionListener.java
└── loyalty
    └── internal
        └── LoyaltyPointsListener.java
~~~

### 5.1. Contract event nằm ở module sở hữu

~~~java
package com.example.shop.orders.events;

import java.time.Instant;
import java.util.UUID;

public record OrderConfirmed(
    UUID eventId,
    UUID orderId,
    Instant occurredAt
) {}
~~~

Cho phép những module khác phụ thuộc contract qua named interface:

~~~java
// orders/events/package-info.java
@org.springframework.modulith.NamedInterface("events")
package com.example.shop.orders.events;
~~~

Event có `eventId` để hỗ trợ correlation và idempotency, nhưng registry **không bắt buộc** dùng trường đó làm khóa nội bộ. Các module nhận không import entity hoặc repository từ `orders.internal`.

### 5.2. Listener notifications

~~~java
package com.example.shop.notifications.internal;

import com.example.shop.orders.events.OrderConfirmed;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class ConfirmationNotificationListener {
    private final ConfirmationSender sender;

    ConfirmationNotificationListener(ConfirmationSender sender) {
        this.sender = sender;
    }

    @ApplicationModuleListener
    void on(OrderConfirmed event) {
        sender.sendOnce(event.eventId(), event.orderId());
    }
}
~~~

`ConfirmationSender` do module `notifications` triển khai; method `sendOnce(...)` ở đây biểu thị **contract idempotent mong muốn**, không phải method do Spring tự sinh. Nếu email provider không hỗ trợ idempotency, module phải thiết kế trạng thái gửi/đối soát phù hợp.

### 5.3. Listener reporting

~~~java
package com.example.shop.reporting.internal;

import com.example.shop.orders.events.OrderConfirmed;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class SalesProjectionListener {
    private final SalesProjectionService projections;

    SalesProjectionListener(SalesProjectionService projections) {
        this.projections = projections;
    }

    @ApplicationModuleListener
    void on(OrderConfirmed event) {
        projections.applyIdempotently(
            event.eventId(), event.orderId()
        );
    }
}
~~~

`SalesProjectionService` cập nhật dữ liệu do module reporting sở hữu; nó phải có transaction và idempotency đúng với việc xử lý lại event. `@ApplicationModuleListener` đã cung cấp ngữ nghĩa giao dịch cho listener theo Spring Modulith; không tự thêm một transaction lồng mới khi chưa hiểu cấu hình thực tế.

### 5.4. Listener loyalty

~~~java
package com.example.shop.loyalty.internal;

import com.example.shop.orders.events.OrderConfirmed;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class LoyaltyPointsListener {
    private final LoyaltyService loyalty;

    LoyaltyPointsListener(LoyaltyService loyalty) {
        this.loyalty = loyalty;
    }

    @ApplicationModuleListener
    void on(OrderConfirmed event) {
        loyalty.awardOnce(
            event.eventId(), event.orderId()
        );
    }
}
~~~

Một lần phát `OrderConfirmed E-100` tạo ra **ba trách nhiệm xử lý** ở ba target nếu cả ba listener được registry quản lý và đăng ký tại thời điểm phát.

### 5.5. Điều gì xảy ra khi reporting thất bại?

~~~text
Event: OrderConfirmed E-100

notifications target
   -> listener sendOnce thành công
   -> publication có thể được đánh dấu completed

reporting target
   -> truy cập database thất bại
   -> listener ném exception
   -> publication chưa completed; cần điều tra/khôi phục

loyalty target
   -> awardOnce thành công
   -> publication có thể được đánh dấu completed
~~~

Một reporting failure **không nên** buộc `orders` rollback dữ liệu đã commit, vì listener hậu commit có transaction riêng. Nhưng nếu reporting thiếu dữ liệu kinh doanh quan trọng, hệ thống phải nhìn thấy trạng thái incompletion thay vì chấp nhận mất báo cáo âm thầm.

## 6. Đọc trạng thái theo từng listener: ba truy vấn nghiệp vụ

Khi vận hành, thường cần trả lời ba nhóm câu hỏi:

**Theo event:** Với E-100, những target nào đang có nghĩa vụ xử lý? Trong số đó target nào hoàn tất và target nào còn dang dở?

**Theo listener:** Trong 30 phút qua, `SalesProjectionListener` có bao nhiêu publication chưa completed? Publication cũ nhất bao lâu? Có dồn backlog không?

**Theo module:** Module `reporting` có đang tụt sau `orders` không, hay chỉ có vài event lỗi dữ liệu đặc biệt?

### 6.1. Bảng đối chiếu kỳ vọng

| Event | Target | Kỳ vọng | Quan sát tại thời điểm T | Hành động |
| --- | --- | --- | --- | --- |
| E-100 | notifications | Gửi thông báo | Completed | Không retry target này |
| E-100 | reporting | Cập nhật báo cáo | Chưa completed | Xem lỗi DB, kiểm tra idempotency |
| E-100 | loyalty | Cộng điểm | Completed | Không retry target này |
| E-101 | notifications | Gửi thông báo | Chưa completed | Kiểm tra queue/worker/provider |
| E-101 | reporting | Cập nhật báo cáo | Completed | Không cần xử lý thêm |

Bảng là **cách trình bày vận hành minh họa**, không khẳng định Spring Modulith có sẵn dashboard hay API trả về đúng những tên cột này.

### 6.2. Điều gì cần để query có ý nghĩa?

Cần xác định:

1. Registry backend đang lưu các bản ghi nào.
2. Cách truy cập publication chưa hoàn tất và dữ liệu completion theo API/schema **đã được xác minh** của version.
3. Listener target được nhận diện như thế nào trong dữ liệu truy vấn.
4. Publication hoàn tất được giữ lại hay bị dọn theo retention policy.
5. Cách phân biệt **chưa xử lý** với **không được đăng ký**.
6. Bản ghi có đủ dữ liệu liên kết tới event nghiệp vụ không (hoặc cần correlation bổ sung).

Không nên tự viết một lớp phụ thuộc tên bảng/column được đoán từ tutorial khác rồi đưa vào production. JDBC, JPA, MongoDB và các phiên bản Spring Modulith có thể khác nhau về cấu trúc, API và chính sách lưu dữ liệu.

### 6.3. Một lớp quan sát ứng dụng là lựa chọn tốt

Để dashboard không phụ thuộc trực tiếp hạ tầng, có thể định nghĩa **interface thuộc ứng dụng**:

~~~java
package com.example.shop.operations;

import java.time.Instant;
import java.util.List;

public interface PublicationMonitoring {

    List<IncompletePublicationView> findIncompleteFor(
        String target, Instant createdBefore
    );

    record IncompletePublicationView(
        String publicationKey,
        String eventType,
        String target,
        Instant registeredAt
    ) {}
}
~~~

Đây là **API minh họa do ứng dụng tự xây dựng**, không phải interface chính thức của Spring Modulith. Adapter thật phải chuyển từ dữ liệu publication được API/backend hỗ trợ; `publicationKey` là khóa hiển thị/tra cứu do adapter định nghĩa, không khẳng định registry dùng kiểu string.

Lợi ích của adapter:

- Giữ dashboard/alerting độc lập với chi tiết persistence.
- Dễ kiểm thử mapping “publication → target”.
- Dễ thay backend registry có kiểm soát.
- Có thể lọc dữ liệu nhạy cảm trước khi đưa ra vận hành.
- Có thể thống nhất định dạng metric giữa các phiên bản triển khai.

## 7. Hoàn tất một listener không có nghĩa toàn event hoàn tất

Giả sử tại thời điểm T:

~~~text
E-100:
  notifications: completed
  reporting: incomplete
  loyalty: completed
~~~

Kết luận đúng: **hai trên ba target được theo dõi đã hoàn tất; reporting chưa hoàn tất**.

Không nên nói:

- “Event E-100 đã xử lý thành công” nếu ý nghĩa câu nói là **mọi module đã xử lý**.
- “Loyalty sẽ retry” vì reporting lỗi; hai publication độc lập.
- “Không cần quan sát nữa” vì email đã được gửi.
- “Đơn hàng phải rollback” chỉ vì reporting xử lý sau commit thất bại.

### 7.1. Tổng hợp trạng thái chỉ có nghĩa khi biết tập target kỳ vọng

Giả sử service phát event E-200 khi chỉ có hai listener; hôm sau deploy thêm listener thứ ba. Registry **không tự bảo đảm** sẽ tạo publication lịch sử cho listener mới.

Vì thế muốn tính “100% listener đã xử lý” phải làm rõ tập listener:

- Những listener nào được đăng ký ở thời điểm E-200 được phát?
- Có listener nào cố ý không nhận event theo phiên bản?
- Có cần backfill cho listener vừa được thêm không?

Một dashboard lấy **danh sách listener hiện tại** rồi áp vào toàn bộ event lịch sử sẽ dễ tạo false alarm hoặc bỏ qua nhu cầu backfill thật.

### 7.2. Bổ sung listener mới không phải cơ chế tự phát lại lịch sử

Nếu `fraud-detection` được thêm vào sau này và cần xử lý 1 triệu đơn cũ, nên có **quy trình backfill chính thức**:

1. Xác định phạm vi dữ liệu nguồn và trạng thái nghiệp vụ hợp lệ.
2. Quyết định đọc từ database nguồn, event store hoặc source-of-truth được hỗ trợ.
3. Xây dựng luồng phát lại có khóa idempotency và giới hạn tải.
4. Tách trạng thái backfill khỏi publication phát trực tiếp nếu hai workflow có semantics khác nhau.
5. Kiểm tra reconciliation và các trường hợp event schema cũ.

Không nên coi registry là một **event sourcing store** giữ toàn bộ lịch sử nghiệp vụ để mọi consumer mới chạy lại từ đầu.

## 8. Đánh dấu completed: điều kiện thành công của mỗi listener

Thông thường, framework có thể đánh dấu publication hoàn tất khi listener được quản lý **trả về thành công** theo ngữ nghĩa tích hợp. Nhưng “listener thành công” cần phải tương đương với **trách nhiệm mà listener đã nhận**.

### 8.1. Trả về bình thường nhưng chưa hoàn tất thực sự

Phản ví dụ:

~~~java
@ApplicationModuleListener
void on(OrderConfirmed event) {
    try {
        projections.applyIdempotently(
            event.eventId(), event.orderId()
        );
    } catch (RuntimeException error) {
        log.error("Reporting failed", error);
        // Nuốt lỗi: framework có thể coi listener thành công.
    }
}
~~~

Nếu reporting cần retry mà method trả về bình thường, publication có thể bị **đánh dấu completed sai** (*false completion*) dù projection chưa tồn tại.

Hướng phù hợp khi lỗi cần phục hồi:

~~~java
@ApplicationModuleListener
void on(OrderConfirmed event) {
    try {
        projections.applyIdempotently(
            event.eventId(), event.orderId()
        );
    } catch (RuntimeException error) {
        log.error(
            "Failed reporting eventId={}",
            event.eventId(),
            error
        );
        throw error;
    }
}
~~~

Nếu sự cố vĩnh viễn không thể retry, cần một **chính sách xử lý lỗi có trạng thái, bằng chứng và người chịu trách nhiệm**, không chỉ bắt exception rồi làm đẹp số liệu.

### 8.2. Nested async cũng có thể tạo completion sai

~~~java
@ApplicationModuleListener
void on(OrderConfirmed event) {
    CompletableFuture.runAsync(() ->
        notifications.sendOnce(
            event.eventId(), event.orderId()
        )
    );
    // Method đã return dù task nền chưa hoàn tất.
}
~~~

Nếu completion được quyết định khi method listener return, publication có thể completed **trước khi tác vụ gửi thực sự chạy xong**. Khi cần tách job, nên ghi job vào queue/store bền vững có lifecycle riêng và chỉ coi listener hoàn tất **trách nhiệm enqueue đã cam kết**, hoặc thực hiện tác vụ trực tiếp trong lượt listener.

### 8.3. Completed không đồng nghĩa end-to-end exactly-once

Một listener có thể:

1. Gửi email thành công.
2. Process chết trước khi registry ghi completed.
3. Registry thấy publication chưa hoàn tất và resubmit.
4. Listener gửi lại email nếu không có idempotency.

Registry không tự bảo đảm **exactly-once side effect** với database khác hoặc hệ thống ngoài. Theo dõi publication và xử lý lặp phải được thiết kế **cùng nhau**.

## 9. Theo dõi lỗi riêng theo target thay vì retry toàn event

Trong ví dụ E-100:

~~~text
completed:   notifications, loyalty
incomplete:  reporting
~~~

Hành động khôi phục hợp lý là **đưa publication dành cho reporting về trạng thái có thể xử lý lại** theo chính sách và API phiên bản ứng dụng, thay vì phát một `OrderConfirmed` hoàn toàn mới.

### 9.1. Vì sao không phát lại event mới một cách tùy tiện?

Nếu phát `OrderConfirmed E-101` mới chỉ để reporting xử lý:

- Notifications có thể gửi thêm email.
- Loyalty có thể cộng điểm lần nữa.
- Registry có thể đăng ký publication mới cho cả ba target.
- `eventId` mới khiến một số cơ chế deduplication không nhận ra công việc cũ.

**Resubmit publication** nghĩa là cố gắng xử lý lại nghĩa vụ còn dang dở của event **đã có**. **Phát event nghiệp vụ mới** chỉ hợp lệ nếu có một sự thật nghiệp vụ mới.

### 9.2. Kiểm tra trước khi resubmit

- Target còn tồn tại và còn nhận cùng event type không?
- Listener có được đổi tên hoặc chuyển package từ lần phát đầu không?
- Payload cũ còn deserialize được không?
- Nguyên nhân lỗi đã được giải quyết chưa?
- Listener đã ghi một phần/tất cả side effect trước khi lỗi chưa?
- Có khóa idempotency hoặc cách rebuild an toàn không?
- Số lượng publication cần xử lý lại có vượt khả năng backend không?
- Cần backoff, batching, rate limit hoặc kiểm soát concurrency không?

Không nên gọi “resubmit all” trong tình huống database đích đang sập hoặc lỗi contract vẫn chưa được sửa; việc đó chỉ tạo thêm tải và log.

### 9.3. Retry và retry policy không đồng nghĩa một tính năng duy nhất

Một event có thể được thử lại ở nhiều tầng:

| Tầng | Ví dụ | Điều cần kiểm soát |
| --- | --- | --- |
| Thử lại lời gọi bên trong listener | HTTP retry, JDBC retry | Timeout, backoff, tác dụng phụ lặp |
| Resubmission publication | Registry giao lại event cho target còn incomplete | Target identity, số lần thử, idempotency |
| Retry ở broker/consumer ngoài | Kafka consumer reprocess, DLQ | Offset, partition, ordering |
| Retry ở workflow nghiệp vụ | Process manager thử lại một bước | Trạng thái quy trình, timeout, compensation |

Không được suy ra registry tự động retry vô hạn chỉ vì nó lưu publication. Hãy kiểm tra API, điều kiện kích hoạt và cấu hình phục hồi của **phiên bản thực tế**.

## 10. Listener identity có thể thay đổi khi refactor

Đây là vấn đề quan trọng của theo dõi **từng listener**. Một publication chưa hoàn tất cần được liên kết lại đúng **target** khi resubmit.

Nếu version A có listener:

~~~java
package com.example.shop.reporting.internal;

@Component
class SalesProjectionListener {
    @ApplicationModuleListener
    void on(OrderConfirmed event) {
        // ...
    }
}
~~~

Và version B đổi thành:

~~~java
package com.example.shop.analytics.internal;

@Component
class RevenueAnalysisListener {
    @ApplicationModuleListener
    void on(OrderConfirmed event) {
        // ...
    }
}
~~~

Thì về mặt nghiệp vụ có thể vẫn là “cập nhật báo cáo”, nhưng framework có thể **nhận diện target khác** tùy cách tạo identifier của phiên bản đã dùng. Một publication cũ đang chỉ đến listener trước có thể không được resubmit đúng như mong muốn sau khi rename/move.

### 10.1. Kiểm tra gì trước khi đổi tên listener?

1. Có publication chưa hoàn tất cho listener cũ không?
2. Registry định danh listener bằng những thành phần nào (bean, method, class, signature, target ID)?
3. API của phiên bản có cơ chế ánh xạ/migration identifier hay không?
4. Payload cũ có còn deserialize với type hiện hành không?
5. Có thể triển khai giai đoạn chuyển tiếp để xử lý hết backlog cũ trước khi xóa listener cũ không?
6. Nếu đổi ý nghĩa listener, có nên tạo target mới thay vì ép target cũ xử lý theo logic khác?

**Không tự giả định** đổi tên class luôn phá recovery, cũng không tự giả định luôn an toàn. Đây là đặc tính phải **kiểm thử theo phiên bản và backend**.

### 10.2. Tránh vừa thay target vừa thay event schema không có kế hoạch

Một release vừa đổi `orders.events.OrderConfirmed` sang package mới, vừa đổi payload record, vừa đổi tên listener có thể tạo nhiều nguyên nhân khiến publication cũ không xử lý được. Nên tách thay đổi:

- Duy trì khả năng deserialize event cũ trong khoảng chuyển tiếp.
- Giữ hoặc migrate danh tính listener theo hỗ trợ thực tế.
- Xử lý/đối soát publication tồn đọng trước khi xóa mã cũ.
- Có integration test chứa publication được tạo ở version trước.

Publication registry không phải cơ chế tự động di chuyển contract khi ứng dụng refactor.

## 11. Tập target theo dõi và ranh giới module

Một listener trong `reporting` nên nhận sự kiện qua contract `orders::events`, không truy cập implementation nội bộ của `orders`.

~~~java
// reporting/package-info.java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "orders::events"
)
package com.example.shop.reporting;
~~~

Ở ví dụ này, contract `OrderConfirmed` nằm trong named interface `orders::events`. Kiểm tra dependency qua:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleArchitectureTest {
    @Test
    void verifiesModuleBoundaries() {
        ApplicationModules
            .of(ShopApplication.class)
            .verify();
    }
}
~~~

Test này xác minh **module structure**, không chứng minh publication được ghi hoặc listener đã hoàn tất. Muốn bảo đảm registry theo dõi từng listener, phải có **integration test** với hạ tầng publication phù hợp.

### 11.1. Một target không nên ghi dữ liệu của target khác

Nếu `reporting` cần dữ liệu từ `orders`, nó có thể dùng event payload có ý nghĩa hoặc public API tương ứng. Không nên bypass boundary bằng import `orders.internal.OrderRepository` chỉ để xử lý nhanh. Khi listener sở hữu dữ liệu của chính module mình, publication cũng phản ánh **một trách nhiệm độc lập** và dễ đối soát hơn.

### 11.2. Hai listener ở cùng một module vẫn là hai nghĩa vụ

Trong `reporting` có thể tồn tại:

- `SalesProjectionListener` dựng tổng doanh số.
- `DailyReportListener` tổng hợp dashboard theo ngày.

Nếu chúng đều thuộc diện được registry quản lý, một event có thể dẫn tới **hai publication** cho module reporting. Đừng gộp “reporting completed” chỉ vì một listener đã chạy. Mức tổng hợp theo module là một **phép nhóm trên các target**, không phải đơn vị hoàn tất mặc định.

## 12. Theo dõi publication theo thời gian và backlog

Một dashboard hữu ích cần quan sát **công việc còn dang dở** chứ không chỉ đếm số event phát ra. Các chỉ số gợi ý:

| Chỉ số | Cách hiểu | Gợi ý cảnh báo |
| --- | --- | --- |
| Số incomplete publication theo target | Listener nào đang tồn backlog? | Tăng liên tục qua nhiều chu kỳ |
| Tuổi publication incomplete cũ nhất | Công việc cũ nhất chưa có bằng chứng hoàn tất bao lâu? | Quá mức trễ nghiệp vụ cho phép |
| Thời gian từ đăng ký tới completed | Độ trễ end-to-end của nhiệm vụ listener | p95/p99 tăng cao |
| Số lỗi listener theo target và nguyên nhân | Backend nào đang lỗi thường xuyên? | Lỗi liên tiếp hoặc cùng một nguyên nhân |
| Số resubmission | Có recovery storm không? | Tăng đột ngột sau deploy/restart |
| Số duplicate được bỏ qua | Listener có nhận lại event cũ nhiều không? | Tăng bất thường, cần điều tra |
| Số publication kỳ vọng và thực tế | Có mất đăng ký do wiring? | Phát event nhưng không tạo target publication dự kiến |

Những tên metric trên mang tính **thiết kế**, không phải cam kết Spring Modulith tự xuất đầy đủ metric và dashboard này. Cần xây instrumentation hoặc adapter quan sát theo khả năng version/backend và hệ thống Micrometer/Actuator/OpenTelemetry đang dùng.

### 12.1. Cảnh báo theo business SLA

Với `notifications`, có thể yêu cầu thông báo xác nhận trong một khoảng trễ cho phép.

Với `reporting`, việc cập nhật chậm vài phút có thể chấp nhận được nếu có khả năng build lại.

Với `loyalty`, cộng điểm sai hoặc thất lạc có thể ảnh hưởng lợi ích kinh tế nên cần reconciliation và cảnh báo mạnh hơn.

Không áp một ngưỡng backlog bằng nhau cho mọi listener. Nên xác định **chính sách theo trách nhiệm**:

- Dữ liệu nào là critical?
- Độ trễ tối đa chấp nhận được?
- Có thể rebuild từ nguồn không?
- Việc xử lý trùng có hậu quả gì?
- Ai chịu trách nhiệm điều tra khi vượt ngưỡng?

### 12.2. Cảnh báo về cardinality

Không nên đưa `eventId`, `orderId` hoặc `publicationId` thành **metric label** cho mọi bản ghi. Điều đó có thể tạo số lượng time series rất lớn.

Thường nên:

- Metric label: module, target type, event type, kết quả, nhóm lỗi.
- Structured logs/traces: event ID, publication key, correlation ID khi cần điều tra.
- Registry query: dùng publication ID/target cụ thể để xem chi tiết.

Không ghi nguyên payload chứa dữ liệu cá nhân vào metric hoặc log một cách mặc định.

## 13. Phân biệt incomplete, processing và failed khi quan sát

Khi nhìn thấy một publication chưa completed, có thể xảy ra các trường hợp:

1. Chưa được dispatch vì worker đang bận.
2. Đã dispatch và đang chạy nhưng chưa hoàn tất.
3. Listener đã ném exception.
4. Process bị crash giữa chừng.
5. Listener xử lý nghiệp vụ thành công nhưng registry chưa ghi completion.
6. Event cũ không deserialize được.
7. Target identifier không còn khớp listener sau deploy.

Registry không nhất thiết cung cấp một trạng thái cụ thể để phân biệt mọi khả năng. Cần kết hợp:

- Dữ liệu incomplete từ registry.
- Structured logs của listener.
- Kết quả nghiệp vụ trong database module nhận.
- Số lần thử/resubmit do hệ thống tự theo dõi nếu cần.
- Health của executor, database, external provider và serialization.

### 13.1. Một bảng chẩn đoán thực tế

| Hiện tượng | Nguyên nhân khả dĩ | Việc cần xác minh |
| --- | --- | --- |
| Incomplete tăng đều ở mọi target | Backend/event executor gặp vấn đề chung | Transaction, executor, registry persistence |
| Chỉ reporting incomplete | Reporting DB lỗi hoặc code mapping thất bại | Log reporting, schema, permission |
| Một publication rất cũ | Event không đọc được, target đổi tên hoặc lỗi dữ liệu cố định | Payload cũ, target ID, version |
| Incomplete biến mất nhưng dữ liệu đích thiếu | Listener nuốt exception hoặc hoàn tất sớm | Semantics return/async, data commit |
| Nhiều email trùng sau retry | Side effect thành công trước completion | Idempotency key và đối soát |
| Không có publication nào từ đầu | Registry/handler chưa đăng ký hoặc query sai | Wiring, transaction, target discovery |

Một dashboard chỉ hiển thị “0 incomplete” có thể che lỗi **không tạo publication**. Nên kèm một kiểm tra tích hợp sinh event thử nghiệm được quản lý (trong môi trường phù hợp) và quan sát expected target count.

### 13.2. Log correlation cho từng target

Ví dụ structured log **do ứng dụng định nghĩa**:

~~~json
{
  "eventType": "OrderConfirmed",
  "eventId": "7b80a06e-c1d9-48e7-a403-86bb8a3d0c3d",
  "target": "reporting.SalesProjectionListener",
  "publicationStatus": "incomplete",
  "attempt": 2,
  "failureCategory": "database_unavailable",
  "elapsedMillis": 18000
}
~~~

Không mặc định những tên trường, giá trị trạng thái hoặc attempt counter là schema có sẵn của Spring Modulith. Đây là ví dụ về cách **thêm khả năng quan sát** khi triển khai.

## 14. Transaction, concurrency và idempotency của từng listener

Theo dõi per-listener giúp xác định ai cần xử lý lại, nhưng không loại bỏ được việc một listener có thể **thực thi nhiều lần**.

### 14.1. Crash window giữa side effect và completed

~~~mermaid
sequenceDiagram
    participant Registry as Registry
    participant Report as ReportingListener
    participant DB as Reporting DB

    Registry-->>Report: Deliver E-100
    Report->>DB: BEGIN local transaction
    Report->>DB: Upsert projection + eventId
    Report->>DB: COMMIT
    Note over Report,Registry: Process chết trước khi mark completed
    Registry->>Registry: E-100 -> reporting còn incomplete
    Registry-->>Report: Resubmit E-100
    Report->>DB: Nhận diện eventId đã xử lý
    DB-->>Report: Không thay đổi dữ liệu lần nữa
    Report-->>Registry: Return success
    Registry->>Registry: Completed cho reporting publication
~~~

**Đây là lý do completion và idempotency không thể tách rời.** Muốn resubmit an toàn, cần thiết kế xử lý lặp ngay từ đầu.

### 14.2. Deduplication bằng khóa có unique constraint

Ví dụ bảng của module `loyalty`:

~~~sql
CREATE TABLE loyalty_processed_events (
    event_id VARCHAR(36) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

Pseudocode trong một transaction local:

~~~text
on OrderConfirmed(event):
    BEGIN transaction loyalty
        INSERT event.eventId vào loyalty_processed_events (unique)
        nếu đã tồn tại:
            bỏ qua lần cập nhật điểm lặp
        nếu insert mới:
            cộng điểm cho orderId đúng một lần
    COMMIT
    return success
~~~

Ghi dấu `eventId` và cập nhật điểm phải nằm trong transaction phù hợp để không tạo trạng thái “đã xử lý” nhưng điểm chưa được cộng. Chỉ đọc `exists(eventId)` rồi cộng điểm không có unique constraint/locking có thể sai khi hai worker xử lý đồng thời.

Nếu một listener xử lý **hai mục đích độc lập** trong một method, phải xác định liệu chúng được commit atomically không. Khi không, nên tách trách nhiệm/transaction hoặc có state machine đủ chi tiết để tránh completion che phần việc chưa thành công.

### 14.3. Registry không tự bảo đảm FIFO per aggregate

Ví dụ `OrderConfirmed(E-100)` của order O-17 thất bại, sau đó `OrderCancelled(E-101)` được xử lý. Khi E-100 được resubmit, reporting có thể nhận event **cũ sau event mới**.

Nếu consumer duy trì trạng thái mới nhất, nên dùng `aggregateVersion`, sequence, compare-and-set hoặc state machine để chống lùi trạng thái. Không mặc định thứ tự timestamp/publication ID sẽ là thứ tự xử lý tuyệt đối.

### 14.4. Nhiều instance cùng phục hồi

Khi triển khai nhiều replica, không nên tự mở một vòng scheduler riêng trên mỗi node và coi chúng chắc chắn chỉ claim một publication một lần. Việc claim/resubmit/concurrency thực tế phụ thuộc phiên bản registry backend, API và cách cấu hình.

Thiết kế idempotent vẫn là lớp bảo vệ cần có ngay cả khi framework/DB cố ngăn chạy đồng thời.

## 15. Gửi event ra broker: theo dõi từng target không tương đương tracking downstream

Một ứng dụng có thể externalize `OrderConfirmed` qua Kafka/AMQP để service bên ngoài nhận. Trong trường hợp này, **externalization adapter** là một loại target công việc ở phía producer.

~~~text
orders DB transaction COMMITTED
    |
    v
Spring Modulith publication for externalizer
    |
    v
Externalizer sends message to broker
    |
    +-- Producer-side publication completed
            |
            v
       Broker queue/topic
            |
            v
       External consumer processes
            |
            v
       Consumer ACK / offset / DB transaction
~~~

Publication completed của externalizer có thể chỉ chứng minh adapter đã thực hiện bước gửi thành công **theo semantics transport/configuration**, không chứng minh consumer đã tạo dữ liệu nghiệp vụ.

| Mốc | Nơi theo dõi | Ý nghĩa |
| --- | --- | --- |
| Event được đăng ký cho externalizer | Spring Modulith registry producer | Producer có trách nhiệm giao event |
| Externalizer completed | Registry producer | Giai đoạn gửi đã hoàn tất theo contract adapter |
| Broker accepted | Broker/producer client | Message được broker xác nhận theo chính sách |
| Consumer offset committed | Hạ tầng broker/consumer group | Tiến độ đọc message của consumer |
| Consumer business committed | Database/service bên ngoài | Nghiệp vụ đích đã được lưu bền |

Vì vậy “theo dõi từng listener” vẫn cần **phân biệt listener nội bộ và externalizer**; một biểu đồ per-target của Spring Modulith chỉ cho biết phạm vi mà registry kiểm soát.

## 16. Kiểm thử registry theo từng listener

Test publication registry cần vượt ra ngoài kiểm tra method listener được gọi. Một test đúng phải tạo **transaction nguồn commit thật**, chạy listener trong Spring context và đọc lại dữ liệu publication từ backend đúng phiên bản.

### 16.1. Ma trận kiểm thử cốt lõi

| Kịch bản | Điều cần chứng minh |
| --- | --- |
| Event được phát trong transaction commit | Publication xuất hiện cho những target được quản lý |
| Transaction nguồn rollback | Không còn publication đã commit cho sự thật bị rollback nếu backend chia sẻ transaction như thiết kế |
| Hai target đều thành công | Cả hai được đánh dấu completed theo semantics backend |
| Target A thành công, B lỗi | A completed, B chưa completed |
| Target B được phục hồi | Chỉ công việc còn dang dở được giao lại; A không bị xử lý lại vô cớ |
| B lỗi sau khi đã ghi database | Retry không tạo duplicate dữ liệu |
| Listener nuốt exception | Test phát hiện false completion hoặc side effect thiếu |
| Thêm listener C sau thời điểm publish | Không suy ra publication lịch sử tự xuất hiện cho C |
| Đổi tên/move listener | Publication cũ có thể được xử lý theo kế hoạch migration |
| Đổi serialized event schema | Publication cũ còn deserialize được hoặc có migration |
| Restart ứng dụng | Publication còn incomplete vẫn được quan sát theo backend |
| Nhiều event cùng orderId | Mỗi event/publication được đối chiếu độc lập |

### 16.2. Không dùng @Transactional test rollback mặc định

Một bài test Spring có `@Transactional` thường rollback khi kết thúc. Khi đó `@TransactionalEventListener(AFTER_COMMIT)` hoặc `@ApplicationModuleListener` **không được kích hoạt** cho event trong transaction test.

Có thể chọn `TransactionTemplate`:

~~~java
import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.transaction.support.TransactionTemplate;

class PublicationScenario {
    private final TransactionTemplate tx;
    private final ApplicationEventPublisher publisher;

    PublicationScenario(TransactionTemplate tx,
                        ApplicationEventPublisher publisher) {
        this.tx = tx;
        this.publisher = publisher;
    }

    void publishAndCommit(OrderConfirmed event) {
        tx.executeWithoutResult(status ->
            publisher.publishEvent(event)
        );
    }

    void publishAndRollback(OrderConfirmed event) {
        tx.executeWithoutResult(status -> {
            publisher.publishEvent(event);
            status.setRollbackOnly();
        });
    }
}
~~~

Đây là **test helper minh họa**, không phải API Spring Modulith. `TransactionTemplate` cần transaction manager được cấu hình. Để kiểm thử nghiệp vụ đầy đủ, thay vì chỉ phát event, nên chạy use case thật cập nhật order cùng transaction rồi kiểm tra trạng thái database nguồn.

### 16.3. Test một listener lỗi và một listener thành công

Thiết kế hai handler thử nghiệm có thể điều khiển kết quả:

~~~text
Test arrangement:
    Listener A: luôn thành công, lưu side effect kiểm chứng được
    Listener B: lần đầu ném RuntimeException
    Registry: persistence backend thật

Act:
    commit event E

Assert:
    A đã commit side effect
    B chưa có side effect hoàn tất
    Publication A completed (hoặc bằng chứng equivalent theo retention)
    Publication B incomplete

Recover:
    B không còn ném lỗi
    resubmit B theo API/chính sách version

Assert:
    B đã commit side effect
    B completed
    A không bị chạy lại ngoài yêu cầu
~~~

Đừng chỉ mock `ApplicationEventPublisher`, bởi khi mock phương thức publish, Spring không thực hiện listener dispatch hoặc registry lifecycle thật.

### 16.4. Một abstraction test theo target

Có thể tạo **test-facing adapter** của ứng dụng:

~~~java
interface PublicationAssertionsPort {
    boolean hasRegisteredTarget(
        String eventCorrelationKey, String target
    );

    boolean hasIncompleteTarget(
        String eventCorrelationKey, String target
    );

    boolean hasEvidenceOfCompletion(
        String eventCorrelationKey, String target
    );
}
~~~

Đây **không phải interface chính thức** của Spring Modulith. Cài đặt thực tế phải sử dụng public API/backend được dự án xác minh, và bảo đảm `eventCorrelationKey` ánh xạ được tới publication cần kiểm tra. Nếu backend không giữ completed records, `hasEvidenceOfCompletion` phải được định nghĩa lại theo bằng chứng mà hệ thống có thể hỗ trợ, không tự suy “không incomplete = completed”.

Test nên assert **theo target cụ thể**, không chỉ số tổng publication:

~~~java
// Pseudocode: publicationAssertions là test adapter của ứng dụng.
await().atMost(Duration.ofSeconds(10)).untilAsserted(() -> {
    assertThat(publicationAssertions.hasIncompleteTarget(
        "E-100", "reporting"
    )).isTrue();
    assertThat(reportingDatabase.hasProcessed("E-100")).isFalse();
});
~~~

Đây là minh họa ý tưởng, không phải test chạy độc lập. Nếu mã `E-100` là UUID trong event, adapter phải biết ánh xạ sang representation tương ứng. Với listener async, polling phải có timeout; không dùng `Thread.sleep(500)` như một điều kiện chính xác.

### 16.5. Kiểm tra dữ liệu đã commit

Một listener có thể được framework gọi thành công nhưng transaction cập nhật database của listener không commit như kỳ vọng, nhất là khi viết dữ liệu trong `AFTER_COMMIT` mà không tạo transaction mới.

Khi kiểm thử:

- Đọc database module nhận **sau khi transaction của listener hoàn tất**.
- Tránh assertion trong một transaction test dài đang giữ snapshot cũ.
- Với `@TransactionalEventListener(AFTER_COMMIT)` ghi DB, xem xét writer bean có `@Transactional(propagation = REQUIRES_NEW)`.
- Với `@ApplicationModuleListener`, hiểu transaction được annotation cung cấp và xác minh kết quả thật.
- Không coi Mockito `verify(repository).save(...)` là bằng chứng database đã commit.

### 16.6. Kiểm tra không tạo publication khi rollback

Test:

1. Tạo một order hợp lệ trong database test.
2. Mở transaction nguồn rồi phát `OrderConfirmed`.
3. Đánh dấu rollback-only hoặc tạo lỗi để transaction rollback.
4. Xác nhận order chưa ở trạng thái `CONFIRMED`.
5. Xác nhận listener hậu commit không tạo side effect.
6. Nếu registry và nghiệp vụ cùng transaction phù hợp, xác nhận không còn publication **đã commit** cho sự thật đã rollback.

Không kết luận registry đúng chỉ vì không có incomplete: có thể event không được phát hoặc listener chưa đăng ký. Cần kiểm thử commit path và rollback path đối chiếu nhau.

## 17. Bài tập thực hành: điều tra một publication lỗi

### 17.1. Bối cảnh

Ứng dụng có ba module nhận `OrderConfirmed`:

~~~text
orders
  -> notifications: ConfirmationNotificationListener
  -> reporting: SalesProjectionListener
  -> loyalty: LoyaltyPointsListener
~~~

Với event E-501, DB nguồn đã commit. Dashboard ghi:

| Target | Trạng thái quan sát | Dữ liệu nghiệp vụ |
| --- | --- | --- |
| notifications | Completed | Email đã được provider nhận |
| reporting | Chưa completed, tuổi 2 giờ | Projection chưa có |
| loyalty | Completed | Điểm thưởng đã cộng |

Sau một lần deploy, `SalesProjectionListener` được đổi tên thành `RevenueProjectionListener`. Nhóm vận hành muốn phát `OrderConfirmed` mới để “kích hoạt lại mọi listener”.

### 17.2. Nhiệm vụ của người học

1. Giải thích vì sao hoàn tất của notifications/loyalty không chứng minh reporting đã hoàn tất.
2. Xác định vì sao **không nên phát event mới** chỉ để sửa reporting.
3. Kiểm tra target identifier gắn với publication cũ trước và sau refactor.
4. Kiểm tra payload E-501 còn deserialize được không.
5. Xác định reporting đã thực hiện một phần side effect trước khi lỗi chưa.
6. Thiết kế khóa idempotency cho reporting.
7. Đề xuất cách resubmit đúng publication theo API/version dự án.
8. Thiết kế alert khi reporting incomplete quá SLA.
9. Viết integration test chứng minh target còn lại không bị xử lý lại ngoài chủ đích.
10. Lập phương án xử lý event lịch sử nếu thêm một target mới.

### 17.3. Phương án xử lý đề xuất

~~~mermaid
flowchart TD
    A[Phát hiện incomplete cho reporting] --> B[Định danh publication và target cũ]
    B --> C{Target còn giải mã/định tuyến đúng?}
    C -->|Không| D[Kế hoạch migration hoặc giữ handler tương thích]
    C -->|Có| E[Kiểm tra lỗi DB và side effect cũ]
    D --> E
    E --> F{Có idempotency không?}
    F -->|Không| G[Bổ sung chống trùng / quy trình đối soát]
    F -->|Có| H[Resubmit publication đúng target]
    G --> H
    H --> I{Listener thành công?}
    I -->|Không| J[Giữ cảnh báo và điều tra]
    I -->|Có| K[Xác minh projection và completion]
~~~

Đây là luồng thao tác **định hướng**; cơ chế migration/resubmit chính xác phụ thuộc Spring Modulith version và backend. Không tự sửa trực tiếp ID hoặc xóa bản ghi incomplete chỉ để làm dashboard sạch.

### 17.4. Tiêu chí nghiệm thu

- [ ] Event E-501 vẫn là sự kiện gốc được xử lý lại.
- [ ] Notifications và loyalty không thực hiện tác dụng phụ trùng.
- [ ] Reporting cập nhật đúng dữ liệu một lần dù có retry.
- [ ] Publication reporting chuyển sang trạng thái hoàn tất theo semantics registry.
- [ ] Listener target vẫn được resolve đúng sau refactor/migration.
- [ ] Log đủ event ID, target, nguyên nhân lỗi và kết quả phục hồi.
- [ ] Alert theo dõi tuổi incomplete hoạt động với ngưỡng phù hợp.
- [ ] Không tạo dependency từ reporting tới `orders.internal`.

## 18. Checklist vận hành và thiết kế theo dõi từng listener

- [ ] Đã phân biệt event ID, aggregate ID, publication ID và listener target identifier.
- [ ] Có khả năng xác định **target nào** đã hoàn tất và target nào chưa.
- [ ] Registry backend thực sự được cấu hình và kiểm thử với transaction manager phù hợp.
- [ ] Không coi `@EventListener` đồng bộ thông thường là publication bền vững mặc định.
- [ ] Không lấy “0 incomplete” làm bằng chứng đầy đủ nếu chưa biết các target đã được đăng ký.
- [ ] Listener không nuốt exception của công việc cần retry.
- [ ] Listener không return trước khi công việc đã cam kết hoàn tất hoặc enqueue bền vững.
- [ ] Transaction ghi dữ liệu module nhận được xác minh đã commit.
- [ ] Side effect có idempotency hoặc chính sách đối soát khi xử lý lặp.
- [ ] Recovery resubmit **đúng publication/target**, không phát event mới vô cớ.
- [ ] Có giới hạn retry, backoff và xử lý lỗi vĩnh viễn.
- [ ] Có kiểm tra tương thích target identifier khi đổi tên/move listener.
- [ ] Có kiểm tra serializer/event schema khi còn publication cũ.
- [ ] Có kế hoạch backfill riêng khi thêm listener cần xử lý dữ liệu lịch sử.
- [ ] Có metric backlog và tuổi incomplete theo target, không chỉ tổng event count.
- [ ] Có log correlation đủ điều tra nhưng không chứa payload nhạy cảm tùy tiện.
- [ ] Đã phân biệt completion của externalizer với ACK và business completion ở consumer ngoài.
- [ ] Có integration tests commit, rollback, nhiều target, lỗi, resubmit, duplicate và restart.
- [ ] Đã kiểm tra module boundary và quyền sở hữu dữ liệu ở từng listener.

## 19. Câu hỏi tự kiểm tra

1. Vì sao một event phát một lần có thể tạo ba publication?
2. Sự khác biệt giữa `eventId` của ứng dụng và identifier của publication là gì?
3. “Notification listener completed” cho biết gì về reporting listener?
4. Vì sao không thể tính tỷ lệ “hoàn tất toàn event” nếu không biết tập target kỳ vọng?
5. Tại sao query “không còn incomplete” chưa đủ chứng minh registry có hoạt động?
6. Nếu listener bắt exception rồi return bình thường, completion có thể sai như thế nào?
7. Vì sao `CompletableFuture.runAsync(...)` bên trong listener có thể tạo false completion?
8. Tại sao nên resubmit một publication cũ thay vì phát event mới có `eventId` mới?
9. Khi một listener đổi class/package, có rủi ro gì đối với publication chưa hoàn tất?
10. Khi thêm listener mới, registry có tự bảo đảm replay toàn bộ event lịch sử không?
11. Registry per-target có tự giữ thứ tự xử lý event theo aggregate không?
12. Vì sao local database transaction và email provider không thể dễ dàng cam kết exactly-once end-to-end?
13. Listener có thể đã hoàn thành side effect nhưng vẫn còn incomplete trong registry như thế nào?
14. Khi externalizer completed, tại sao consumer Kafka vẫn có thể chưa xử lý message?
15. Những test nào phát hiện sự khác biệt giữa “listener không đăng ký” và “listener đã completed”?
16. Khi nào nên đưa target name vào metric label và khi nào phải dùng ID trong structured log?
17. Cần làm gì nếu một publication incomplete đã tồn tại lâu hơn SLA?
18. Vì sao module reporting không được dùng repository nội bộ của orders để xử lý event?

## 20. Tài liệu đối chiếu và kết luận

Khi triển khai với **phiên bản Spring Modulith thực tế**, cần tham khảo tài liệu và public APIs của phiên bản đã khóa dependency:

- [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html): publication registry, transactional listeners và resubmission.
- [Spring Modulith — Application Module Testing](https://docs.spring.io/spring-modulith/reference/testing.html): kiểm thử phạm vi module, published events và module boundaries.
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): thời điểm `@TransactionalEventListener` chạy theo transaction phase.
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): transaction nguồn, transaction mới và isolation giữa các tác vụ.

Tên method API truy vấn publication, target identifier, schema database, cơ chế retention và cấu hình recovery có thể thay đổi theo version/backend. Khi cần viết lệnh resubmit, adapter query hoặc migration thật, hãy **xác minh API chính thức của dependency dự án** và chạy integration test thay vì tự suy ra từ pseudocode.

**Ghi nhớ:** Event Publication Registry có giá trị bởi nó giúp quan sát **trách nhiệm xử lý riêng của từng listener/target**. Một event có thể đã được `notifications` xử lý thành công, còn `reporting` vẫn cần phục hồi, và `loyalty` không cần chạy lại. Để theo dõi đáng tin cậy, phải kết hợp việc đăng ký publication đúng transaction, định danh target ổn định hoặc migration an toàn, listener báo kết quả thật, idempotency khi retry, truy vấn/metric theo target và kiểm thử các khoảng lỗi. **Không đánh đồng event đã phát, publication đã đăng ký, một listener completed và toàn hệ thống đã nhất quán.**
