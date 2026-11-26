# Đánh dấu publication trong Spring Modulith

## 1. Publication được đánh dấu để làm gì?

Trong Spring Modulith, **event publication** là việc giao một application event cho **một listener mục tiêu** mà cơ chế quản lý publication có thể theo dõi. Khi event được phát trong transaction nghiệp vụ, event publication registry (nếu đã cấu hình backend phù hợp) giúp ghi nhận công việc cần thực hiện; khi listener hoàn tất thành công, publication tương ứng có thể được **đánh dấu hoàn tất** (*mark completed*).

Bài học **Đánh dấu publication** thuộc chương **Chu kỳ phát hành**, trong module học `SPRING_MODULITH_APPLICATION_EVENTS`. Mục tiêu chung là xây dựng giao tiếp giữa các module bằng application events: publisher phát sự kiện, listener nhận sau commit, registry lưu dấu tiến độ, và khi lỗi xảy ra hệ thống có thể kiểm tra, retry, kiểm thử và quan sát để tránh thất lạc công việc.

Hãy xét sự kiện `OrderConfirmed`:

- Module `orders` xác nhận đơn hàng và phát event.
- Module `notifications` nhận event để gửi thông báo.
- Module `reporting` nhận event để cập nhật dữ liệu thống kê.

Hai listener độc lập có hai kết quả riêng. Nếu `notifications` thành công nhưng `reporting` thất bại, ta không thể kết luận “event này đã được xử lý hết”. Để có khả năng khôi phục chính xác, trạng thái thường cần theo dõi **theo cặp event và listener**, chứ không chỉ một cờ trên event.

~~~mermaid
flowchart LR
    Orders[orders: OrderConfirmed] --> Registry[(Event Publication Registry)]
    Registry --> N[Publication cho notifications]
    Registry --> R[Publication cho reporting]
    N --> NS[Listener thành công]
    NS --> NC[Đánh dấu hoàn tất]
    R --> RF[Listener thất bại]
    RF --> RI[Chưa hoàn tất / cần xử lý lại]
~~~

Sơ đồ mô tả **trách nhiệm logic** của registry. Những tên trạng thái trong sơ đồ là mô tả khái niệm; tên trạng thái lưu trữ và các bảng/collection thực tế phụ thuộc phiên bản Spring Modulith và backend.

### 1.1. Phân biệt bốn mốc quan trọng

| Mốc | Diễn giải | Có đồng nghĩa publication hoàn tất? |
| --- | --- | --- |
| **Event được phát** | `ApplicationEventPublisher.publishEvent(...)` đã được gọi | Không |
| **Publication được ghi nhận** | Registry ghi việc cần giao event cho listener đích theo cấu hình | Không |
| **Listener được kích hoạt** | Cơ chế dispatch bắt đầu gọi logic xử lý | Chưa chắc |
| **Publication được đánh dấu hoàn tất** | Registry ghi nhận listener đã kết thúc thành công theo ngữ nghĩa theo dõi đang áp dụng | Có đối với publication đó |

“Hoàn tất” ở đây còn cần **đọc đúng phạm vi**: một listener báo xử lý thành công **không chứng minh** broker đã chuyển đến mọi consumer bên ngoài hoặc một tác vụ ngoài hệ thống đã chắc chắn hoàn thành đúng một lần.

### 1.2. Vì sao cần lưu trạng thái?

Application event mặc định hoạt động trong ứng dụng Spring. Nếu process chết sau khi transaction đơn hàng commit nhưng trước khi listener hậu commit hoàn tất, chỉ dựa vào event trong bộ nhớ có thể khiến một công việc bị bỏ sót. Registry cung cấp dữ liệu để **nhận biết publication chưa hoàn tất** và hỗ trợ cơ chế xử lý lại phù hợp.

Tuy nhiên, registry không tự làm mọi listener trở nên bền vững. Muốn có tiến độ được lưu, cần dùng loại transactional listener phù hợp, cấu hình module event publication registry có backend thực tế và xác minh transaction nguồn. Chỉ đặt `@EventListener` hoặc gọi `publishEvent(...)` chưa đủ để có một hàng đợi bền vững.

## 2. Đối tượng được đánh dấu: một publication cho một listener

Giả sử publisher phát một event E có hai listener:

~~~text
OrderConfirmed(eventId = E)
    |
    +---> Publication P1: E -> notifications listener
    |
    +---> Publication P2: E -> reporting listener
~~~

Mỗi publication đại diện cho **một nghĩa vụ xử lý riêng**. Ví dụ:

| Event | Listener đích | Tình huống sau xử lý | Kết luận |
| --- | --- | --- | --- |
| E | `notifications.on(OrderConfirmed)` | Hoàn tất | P1 được ghi nhận thành công |
| E | `reporting.on(OrderConfirmed)` | Exception | P2 chưa có bằng chứng hoàn tất |
| E | `loyalty.on(OrderConfirmed)` | Chưa đăng ký listener tại thời điểm phát | Không tự suy ra có publication cũ cho listener mới |

Thêm listener mới sau khi event được tạo **không có nghĩa registry phải tự tạo publication cho mọi event lịch sử**. Việc backfill là một bài toán riêng và có thể cần một quá trình nghiệp vụ được thiết kế chủ động.

Tùy phiên bản/backend, định danh publication có thể gồm ID của bản ghi publication, event, kiểu listener đích, thời điểm và trạng thái. Không nên tự xây logic “đánh dấu tất cả publication theo cùng `orderId`” vì:

- Một đơn hàng có thể phát nhiều event khác nhau.
- Một loại event có thể có nhiều lần phát với dữ liệu và thời điểm khác nhau.
- Một event có thể được xử lý thành công ở một listener nhưng thất bại ở listener khác.
- Các listener có quyền sở hữu dữ liệu và chính sách retry độc lập.

### 2.1. Event ID và publication ID không giống nhau

**Event ID** dùng để nhận diện một sự kiện nghiệp vụ hoặc một lần phát event theo contract ứng dụng. **Publication ID** nhận diện một bản ghi theo dõi việc giao event cho listener trong registry. Một event có thể tương ứng nhiều publication.

Không mặc định rằng `eventId` có sẵn trong mọi event hoặc registry luôn dùng chính field này để tạo khóa. Nếu ứng dụng cần deduplication nghiệp vụ, hãy chủ động thiết kế `eventId` ổn định trên các lần retry và không sinh ID mới khi chỉ xử lý lại cùng event.

## 3. Chu kỳ publication từ lúc phát đến lúc đánh dấu hoàn tất

Một luồng thường gặp với Spring Modulith:

1. Application service bắt đầu hoặc tham gia transaction.
2. Service thay đổi trạng thái nghiệp vụ, chẳng hạn xác nhận đơn.
3. Service gọi `publishEvent(...)`.
4. Registry ghi publication dành cho các transactional listeners mà nó quản lý, trong mối quan hệ với transaction theo backend cấu hình.
5. Transaction nghiệp vụ commit thành công.
6. Listener hậu commit thực hiện công việc đã đăng ký.
7. Nếu listener kết thúc thành công, cơ chế registry đánh dấu publication tương ứng hoàn tất.
8. Nếu listener lỗi hoặc tiến trình dừng ở một khoảng thời gian nguy hiểm, publication có thể còn chưa hoàn tất và cần được xem xét khôi phục.

~~~mermaid
sequenceDiagram
    participant Client as Client
    participant Orders as orders
    participant DB as Transaction / DB
    participant Pub as ApplicationEventPublisher
    participant Reg as Publication Registry
    participant Listener as reporting listener

    Client->>Orders: confirmOrder(orderId)
    Orders->>DB: Begin / join transaction
    Orders->>DB: Chuyển Order sang CONFIRMED
    Orders->>Pub: publishEvent(OrderConfirmed)
    Pub->>Reg: Ghi publication cần xử lý
    Orders->>DB: Commit
    alt Commit thành công
        Pub-->>Listener: Gọi listener sau commit
        Listener->>Listener: Cập nhật projection
        alt Xử lý thành công
            Listener-->>Reg: Hoàn tất qua cơ chế theo dõi
            Reg->>Reg: Ghi dấu completed
        else Exception hoặc process chết
            Note over Reg,Listener: Publication có thể chưa hoàn tất
        end
    else Rollback
        Note over Reg,Listener: Publication giao dịch không được commit
    end
~~~

**Giới hạn sơ đồ:** Thứ tự chi tiết của callback, commit transaction riêng của listener, ghi status, cơ chế dispatch và failure handling phụ thuộc phiên bản Spring Modulith, hạ tầng persistence và kiểu listener. Sơ đồ thể hiện mục đích của lifecycle, không khẳng định mỗi mũi tên là một API public hay một transaction riêng.

### 3.1. Trạng thái khái niệm cần hiểu

~~~mermaid
stateDiagram-v2
    [*] --> Registered: Transaction nguồn ghi nhận
    Registered --> PendingDelivery: Commit thành công
    Registered --> [*]: Rollback transaction
    PendingDelivery --> InProgress: Listener bắt đầu
    InProgress --> Completed: Listener báo thành công
    InProgress --> Incomplete: Lỗi / gián đoạn
    Incomplete --> InProgress: Resubmit / retry
    Completed --> [*]: Dọn lịch sử theo chính sách
~~~

Các nút `Registered`, `PendingDelivery`, `InProgress` và `Incomplete` là **nhãn diễn giải**. Không được mặc định cơ sở dữ liệu Spring Modulith lưu đủ những trạng thái này hoặc chúng trùng tên enum của một phiên bản cụ thể. Điểm chung cần nhớ: **publication được theo dõi cho đến khi có kết quả hoàn tất hoặc chính sách xử lý tiếp**.

### 3.2. Điều gì xảy ra khi transaction rollback?

Nếu registry có backend transaction tương thích, publication được ghi cùng transaction nguồn sẽ không trở thành một công việc đã commit khi transaction đó rollback. Một listener với pha `AFTER_COMMIT` không được kích hoạt để tạo tác dụng phụ cho thay đổi đã rollback.

Ngược lại, `@EventListener` đồng bộ mặc định có thể chạy ngay trong lúc transaction chưa kết thúc. Vì vậy, gửi email hoặc gọi HTTP từ listener đồng bộ vẫn có thể diễn ra trước khi transaction thất bại. Đánh dấu publication không thể **thu hồi** một tác dụng phụ đã xảy ra ngoài database.

## 4. “Completed” có nghĩa chính xác là gì?

**Publication completed** về cơ bản có nghĩa **cơ chế theo dõi đã ghi nhận kết quả thành công của việc xử lý event ở listener đích**. Đây là một kết quả ở tầng dispatch/listener, không phải một lời bảo đảm vô điều kiện cho tất cả những hệ thống nằm sau listener.

Ví dụ một listener của `notifications` gọi SMTP provider:

~~~text
OrderConfirmed
    -> NotificationListener
        -> gửi email / yêu cầu provider
    -> listener trả về bình thường
    -> registry ghi publication hoàn tất
~~~

Khi listener trả về bình thường, cơ chế đánh dấu có thể coi xử lý thành công. Nhưng nếu provider chỉ **nhận yêu cầu gửi** và giao email thực tế bị trễ, completion không chứng minh khách hàng đã đọc hoặc đã nhận email.

| Trường hợp | “Completed” cho publication khẳng định điều gì? | Điều còn cần xác minh |
| --- | --- | --- |
| Listener chỉ cập nhật DB local | Listener kết thúc thành công theo cơ chế theo dõi | Transaction thay đổi DB có thực sự commit không? |
| Listener gửi message tới broker | Bước gửi được adapter công nhận thành công theo semantics cấu hình | Consumer đã xử lý message chưa? |
| Listener gọi API gửi email | Listener hoàn thành luồng gọi theo mã triển khai | Provider đã giao email và có tác dụng phụ trùng không? |
| Listener khởi tạo tác vụ async rồi trả về | Method listener có thể kết thúc sớm | Công việc async có thực sự hoàn tất hay chỉ mới bắt đầu? |

### 4.1. Đánh dấu thành công phải khớp với cam kết của listener

Nếu listener có hợp đồng “cập nhật projection trong database”, chỉ trả về thành công **sau khi tác vụ ghi thực sự hoàn tất theo transaction phù hợp** mới có ý nghĩa. Nếu hợp đồng của listener chỉ là “đưa công việc vào một hàng đợi nội bộ bền vững”, có thể coi bước enqueue đã thành công, nhưng phải thiết kế một **chu kỳ theo dõi riêng** cho tác vụ trong hàng đợi đó.

Không nên đặt tên và ghi log “gửi thông báo thành công” chỉ vì đã tạo `CompletableFuture` để gửi, trong khi task thực tế chưa chạy xong.

### 4.2. Hoàn tất không đồng nghĩa exactly-once

Giả sử listener gửi email thành công, nhưng tiến trình dừng **trước khi registry lưu dấu completed**. Khi publication còn chưa hoàn tất được resubmit, listener có thể gửi email lần thứ hai. Từ góc nhìn consumer, thực thi **lặp** là một tình huống có thể xảy ra.

Registry cải thiện khả năng **theo dõi và phục hồi**, còn **idempotency** quyết định liệu xử lý lặp có gây tác dụng phụ ngoài ý muốn hay không.

## 5. Cách Spring Modulith đánh dấu publication khi listener thành công

Spring Modulith tích hợp hạ tầng publication registry với việc xử lý **transactional application event listeners**. Với cấu hình lưu trữ thích hợp, khi listener thuộc diện theo dõi hoàn tất thành công, framework có thể tự ghi dấu hoàn tất cho publication đó.

Đối với luồng ứng dụng bình thường, cách làm phổ biến là **để framework quản lý completion** và viết listener có ngữ nghĩa thành công/thất bại rõ ràng. Không cần gọi một phương thức “mark completed” thủ công ở mọi listener.

### 5.1. Publisher nghiệp vụ

Ví dụ rút gọn trong module `orders`:

~~~java
package com.example.shop.orders.internal;

import java.time.Clock;
import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class OrderManagement {

    private final OrderRepository orders;
    private final ApplicationEventPublisher publisher;
    private final Clock clock;

    OrderManagement(OrderRepository orders,
                    ApplicationEventPublisher publisher,
                    Clock clock) {
        this.orders = orders;
        this.publisher = publisher;
        this.clock = clock;
    }

    @Transactional
    public void confirm(UUID orderId) {
        var order = orders.findById(orderId).orElseThrow();
        order.requireCanConfirm();
        order.confirm();

        publisher.publishEvent(new OrderConfirmed(
            UUID.randomUUID(), orderId, clock.instant()
        ));
    }
}
~~~

`OrderRepository`, `OrderConfirmed` và bean `Clock` là thành phần của ứng dụng minh họa, không phải API tự sinh của Spring Modulith. Tùy công nghệ persistence, service cần thực hiện thao tác lưu qua repository hoặc để JPA flush/commit entity đang được quản lý.

Đoạn code này **chỉ phát sự kiện**. Nó không tự gọi registry để “đánh dấu hoàn tất”, vì kết quả hoàn tất của từng listener chưa tồn tại vào thời điểm `publishEvent(...)` được gọi.

### 5.2. Listener hậu commit có transaction riêng

Ví dụ module `reporting` dùng `@ApplicationModuleListener`:

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
        projections.applyOrderConfirmed(event);
    }
}
~~~

`@ApplicationModuleListener` là annotation tiện dụng của Spring Modulith cho listener bất đồng bộ, xử lý hậu commit trong transaction riêng theo ngữ nghĩa và cấu hình của framework. Cần có dependency, transaction manager, executor và backend phù hợp; listener bên trên là đoạn mã minh họa về trách nhiệm, không phải toàn bộ ứng dụng chạy độc lập.

Trong phương án này:

1. `orders` không import service của `reporting`.
2. `reporting` chỉ import một **event contract được công bố** từ `orders`.
3. `projections.applyOrderConfirmed(...)` thực hiện công việc thuộc `reporting`.
4. Nếu listener kết thúc thành công theo cơ chế theo dõi, publication tương ứng được đánh dấu completed.
5. Nếu lỗi được truyền ra khỏi listener, publication không được ghi nhận thành công theo cùng đường hoàn tất.

Nếu event nằm ở package `orders.events`, module `orders` cần công bố package như named interface hoặc đưa contract vào API phù hợp. Ví dụ:

~~~java
// orders/events/package-info.java
@org.springframework.modulith.NamedInterface("events")
package com.example.shop.orders.events;
~~~

### 5.3. Đánh dấu tự động dựa trên kết quả xử lý, không dựa trên log

Đoạn mã sau là **cách xử lý lỗi dễ gây sai**:

~~~java
@ApplicationModuleListener
void on(OrderConfirmed event) {
    try {
        projections.applyOrderConfirmed(event);
    } catch (Exception ex) {
        log.error("Projection failed", ex);
        // Trả về bình thường => framework có thể coi listener hoàn tất.
    }
}
~~~

Nếu listener được theo dõi và lời gọi trả về **bình thường**, framework có thể đánh dấu publication hoàn tất, trong khi projection chưa được cập nhật. Đây là kiểu **false completion**: registry báo đã xử lý nhưng tác vụ nghiệp vụ chưa đạt.

Hướng xử lý đúng khi lỗi cần retry là ghi log có ngữ cảnh rồi **để lỗi tiếp tục được báo ra**:

~~~java
@ApplicationModuleListener
void on(OrderConfirmed event) {
    try {
        projections.applyOrderConfirmed(event);
    } catch (RuntimeException ex) {
        log.error(
            "Cannot update projection, eventId={}",
            event.eventId(),
            ex
        );
        throw ex;
    }
}
~~~

Nếu lỗi là **không thể phục hồi** (ví dụ schema sai hoặc dữ liệu đầu vào không hợp lệ), cần chính sách riêng: phân loại, cảnh báo, lưu vào khu vực điều tra hoặc kết thúc có kiểm soát sau quyết định nghiệp vụ. Không nên nuốt exception chỉ để registry hiển thị “completed”.

### 5.4. Khi nào không dùng completion mặc định?

Một số hệ thống tích hợp cần **điều phối thủ công** trạng thái một công việc, chẳng hạn adapter tự triển khai, một quy trình nhiều bước hoặc workflow có xác nhận từ hệ thống ngoài. Khi đó có thể cần thao tác quản lý publication thông qua API phù hợp của phiên bản Spring Modulith/backend đang dùng.

Nguyên tắc:

- Xác định đúng **publication cụ thể và listener/target** đang xử lý.
- Chỉ hoàn tất khi điều kiện thành công của trách nhiệm đó thực sự được thỏa mãn.
- Bảo đảm thao tác completion/commit có tính chất transaction cần thiết.
- Không đánh dấu tràn lan mọi publication của cùng event hoặc cùng `orderId`.
- Xem xét rủi ro thực hiện lại nếu side effect thành công nhưng completion chưa kịp lưu.

**Tên class, method và signature của API quản lý publication có thể thay đổi theo phiên bản.** Bài này không tự đặt ra một lời gọi Java “markCompleted(id)” không được xác minh. Khi cần tự điều khiển completion, phải đối chiếu API công khai và cách backend thực thi trong phiên bản dự án đang chạy, rồi viết integration test tương ứng.

## 6. Transaction liên quan thế nào đến dấu hoàn tất?

Có ít nhất **hai vùng transaction** cần phân biệt:

1. **Transaction nguồn:** xác nhận đơn hàng và ghi nhận publication liên quan trước khi commit.
2. **Transaction xử lý listener:** cập nhật projection hoặc dữ liệu của module nhận, sau đó cơ chế registry ghi kết quả xử lý.

Không nên giả định hai transaction này là một. Với listener hậu commit, transaction nguồn đã hoàn tất trước khi tác vụ của module nhận bắt đầu hoặc kết thúc.

### 6.1. Tại sao có thể cần `REQUIRES_NEW`?

Với `@TransactionalEventListener(phase = AFTER_COMMIT)` thuần Spring, callback chạy sau commit nhưng tài nguyên transaction cũ có thể vẫn còn gắn với thread. Việc chỉ ghi thêm qua repository trong callback **không bảo đảm có một transaction mới để commit**.

Nếu listener cần ghi database, có thể chuyển công việc sang một Spring bean có:

~~~java
@Service
class SalesProjectionService {

    private final SalesProjectionRepository repository;

    SalesProjectionService(SalesProjectionRepository repository) {
        this.repository = repository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void applyOrderConfirmed(OrderConfirmed event) {
        repository.applyIdempotently(
            event.eventId(), event.orderId()
        );
    }
}
~~~

`SalesProjectionRepository.applyIdempotently(...)` là method ứng dụng tự xây dựng với semantics xử lý lặp an toàn; Spring Data không tự cung cấp method này. Ứng dụng cần import `Transactional`, `Propagation` và các kiểu event/repository.

Chú ý sử dụng **một bean khác** để interceptor `@Transactional` có hiệu lực trong ứng dụng dùng Spring proxy thông thường. Gọi method `REQUIRES_NEW` trên chính `this` có thể không được proxy intercept.

`@ApplicationModuleListener` đã có ngữ nghĩa giao dịch riêng, do đó không nên thêm `REQUIRES_NEW` một cách máy móc mà không hiểu cấu hình và luồng xử lý của dự án. Bảng dưới cho thấy từng lựa chọn cần được kiểm tra:

| Cách nghe | Vấn đề transaction cần xem xét |
| --- | --- |
| `@EventListener` đồng bộ | Có thể tham gia transaction nguồn; exception ảnh hưởng publisher |
| `@TransactionalEventListener(AFTER_COMMIT)` | Chạy sau commit, ghi DB mới cần transaction phù hợp |
| `@ApplicationModuleListener` | Hậu commit, bất đồng bộ, transaction xử lý riêng theo Spring Modulith |
| Tự gọi `CompletableFuture.runAsync(...)` từ listener | Mất đồng bộ giữa kết quả method listener và kết quả công việc thật |

### 6.2. Một khoảng lỗi quan trọng: ghi nghiệp vụ xong nhưng chưa ghi completed

~~~mermaid
sequenceDiagram
    participant Registry as Registry
    participant Listener as reporting listener
    participant DB as Reporting DB

    Registry-->>Listener: Giao publication P1
    Listener->>DB: Cập nhật projection
    DB-->>Listener: Commit thành công
    Note over Listener,Registry: Process crash trước khi mark completed
    Registry->>Registry: P1 vẫn cần xử lý theo trạng thái lưu
    Registry-->>Listener: Resubmit P1 khi khôi phục
    Listener->>DB: Áp dụng event lần nữa?
~~~

Nếu lần hai cộng số liệu một cách không kiểm soát, projection bị nhân đôi. Cho dù transaction của listener được thiết kế tốt, **thao tác nghiệp vụ và dấu completed có thể có khoảng lỗi riêng** tùy backend và thứ tự transaction. Do đó phải luôn thiết kế phương án xử lý lặp có thể kiểm chứng.

### 6.3. Dấu hoàn tất không thể thay thế transaction nguồn

Nếu `orders` đổi trạng thái trong DB nhưng không ghi publication một cách bền vững, process có thể chết trước khi registry biết công việc cần giao. Đánh dấu completed của một publication **chỉ có ý nghĩa khi publication đã được tạo đúng**.

Vì vậy, hệ thống tin cậy cần cả:

- Ghi publication liên quan một cách phù hợp với transaction nguồn.
- Xử lý listener với ngữ nghĩa transaction rõ ràng.
- Ghi kết quả completion và có kế hoạch khôi phục khi gián đoạn.
- Idempotency cho việc chạy lại những tác vụ đã có tác dụng phụ.

## 7. Lỗi nào nên khiến publication còn chưa hoàn tất?

Phải xác định **điều kiện thành công** trước khi quyết định một lỗi có thể bỏ qua hay không.

| Tình huống | Cách xử lý thường hợp lý | Ảnh hưởng kỳ vọng tới completion |
| --- | --- | --- |
| Database reporting không sẵn sàng | Propagate exception, retry sau | Chưa đánh dấu thành công |
| Lỗi kết nối tạm thời tới email provider | Ghi log có ID, retry có kiểm soát | Chưa hoàn tất nếu listener chịu trách nhiệm giao email |
| Event bị xử lý lại nhưng đã áp dụng đúng | Xác minh idempotency, trả về bình thường | Có thể ghi completed cho publication lần xử lý này |
| Payload thiếu trường bắt buộc | Phân loại lỗi dữ liệu, cảnh báo, có quy trình sửa/điều tra | Không âm thầm đánh dấu thành công |
| Tác vụ metric không quan trọng bị lỗi | Quy định rõ telemetry có thể bỏ qua và không làm ảnh hưởng nghiệp vụ | Có thể coi mục đích listener hoàn tất nếu đó thật sự là contract |
| Đã enqueue thành công vào hàng đợi bền vững do listener sở hữu | Theo dõi công việc ở hàng đợi riêng | Có thể hoàn tất giai đoạn enqueue, chưa coi downstream job xong |
| Listener tạo tác vụ background rồi trả về khi chưa lưu bền | Sửa thiết kế, chờ/lưu kết quả có thể xác minh | Không nên cho publication completed sớm |

### 7.1. Không dùng `catch (Exception) { return; }` để “ổn định” hệ thống

Câu lệnh này khiến lỗi thực tế biến mất khỏi cơ chế theo dõi. Sau một lần restart, registry có thể không còn publication để resubmit, mặc dù dữ liệu mà listener phải tạo vẫn thiếu.

Thay vào đó, có thể:

1. Ghi log có `eventId`, listener và nguyên nhân.
2. Phân loại lỗi có thể retry và lỗi dữ liệu cố định.
3. Với lỗi có thể retry, để cơ chế quản lý publication nhận biết lỗi.
4. Với lỗi không thể tự phục hồi, chuyển sang quy trình xử lý có kiểm soát và được ghi nhận.
5. Chỉ kết thúc listener thành công khi chính sách nghiệp vụ chấp nhận trạng thái cuối cùng đó.

### 7.2. Phân biệt retry ở ba tầng

Một luồng có thể có nhiều tầng retry:

- **Thư viện gọi HTTP/DB:** thử lại một lời gọi mạng thất bại trong cùng lượt xử lý listener.
- **Publication resubmission:** gọi lại listener với event đã được ghi trong registry.
- **Consumer ngoài hệ thống:** nhận lại message từ broker theo ACK/offset/retry của chính consumer.

Các tầng này có thể kết hợp làm số lần tác dụng phụ tăng lên. Cần giới hạn lần thử, backoff, xử lý lỗi vĩnh viễn và idempotency; không nên cho mỗi tầng retry vô hạn.

## 8. Đánh dấu hoàn tất khi có nhiều listener

Một event `OrderConfirmed` có thể được xử lý song song hoặc theo các cơ chế khác nhau:

~~~text
OrderConfirmed E-42
    |
    +-- notifications.on(E-42)  [completed]
    |
    +-- reporting.on(E-42)      [incomplete]
    |
    +-- loyalty.on(E-42)        [completed]
~~~

Nếu đội vận hành chỉ đếm “bao nhiêu event đã được phát”, họ không biết projection của reporting còn thiếu. Một hệ thống quan sát tốt nên thể hiện **publication chưa hoàn tất theo loại event và listener**.

### 8.1. Sai lầm: đánh dấu sự kiện “done” sau khi listener đầu tiên thành công

Trong luồng trên, `notifications` thành công không thay thế công việc của `reporting`. Mỗi bên sở hữu dữ liệu và kết quả riêng.

Tương tự, hai event khác nhau của cùng một đơn, như `OrderConfirmed` và `OrderCancelled`, không phải một publication. Nếu cần xử lý sự kiện theo thứ tự nghiệp vụ, listener phải có state machine hoặc version tương ứng thay vì suy từ dấu completed của event khác.

### 8.2. Sai lầm: dùng completed để suy ra không còn backlog consumer

Với externalization, “publication completed” có thể chỉ đại diện cho việc adapter đã gửi message ra transport thành công theo semantics được cấu hình. Broker có thể vẫn chứa message chưa được consumer bên ngoài đọc.

Muốn biết tiến độ của consumer, phải xem ACK/offset, backlog, database consumer hoặc thông điệp xác nhận nghiệp vụ riêng, tùy kiến trúc.

### 8.3. Sai lầm: xóa dấu lịch sử ngay khi hoàn tất

Một số backend/phiên bản có thể giữ hoặc dọn những publication đã hoàn tất theo chính sách. Không nên tự xóa bản ghi còn phục vụ audit hoặc điều tra, cũng không nên để bảng theo dõi tăng vô hạn.

Chính sách lưu trữ cần trả lời: thời gian cần tra cứu sự cố bao lâu, có yêu cầu tuân thủ/audit nào, publication completed có cần giữ toàn bộ payload, và quy trình dọn dữ liệu nào không phá hỏng resubmission.

## 9. Idempotency để completion và retry cùng an toàn

### 9.1. Trường `eventId` là khóa ứng viên hữu ích

Event có thể được thiết kế:

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

Nếu mỗi lần phát event thật sự có một `eventId` ổn định, listener có thể nhận diện việc xử lý lại cùng sự kiện. Không dùng `UUID.randomUUID()` **bên trong listener mỗi lần retry** để tạo khóa deduplication, vì nó khiến các lần xử lý của cùng event có khóa khác nhau.

### 9.2. Ghi dấu đã xử lý cùng thay đổi nghiệp vụ

Trong module `reporting`, ví dụ bảng:

~~~sql
CREATE TABLE reporting_processed_events (
    event_id VARCHAR(36) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

Pseudocode:

~~~text
handle(event):
    BEGIN local transaction
      INSERT event.eventId vào reporting_processed_events (unique)
      Nếu unique conflict:
          xem event là đã áp dụng trước đó; không tăng số liệu lần nữa
      Nếu insert mới:
          cập nhật projection báo cáo thuộc reporting
    COMMIT
    trả về thành công để cơ chế publication có thể hoàn tất
~~~

Việc insert khóa và cập nhật projection cần nằm trong **transaction phù hợp của module nhận** để tránh “đã đánh dấu xử lý nhưng chưa cập nhật số liệu”. Phải dùng unique constraint hoặc cơ chế tương đương để an toàn khi hai lượt xử lý chạy đồng thời.

Với một provider email bên ngoài, transaction database không thể commit nguyên tử cùng hành động gửi email. Khi đó cần idempotency key ở provider (nếu hỗ trợ), quy trình gửi có lưu trạng thái hoặc đối soát để giảm duplicate. Không nên tuyên bố cơ chế trên bảo đảm đúng một lần cho mọi tác dụng phụ.

### 9.3. Khi hoàn tất lại một publication đã được xử lý nghiệp vụ

Một tình huống điển hình:

1. Listener đã áp dụng projection và commit.
2. Ứng dụng dừng trước khi registry ghi completed.
3. Registry khôi phục publication còn dang dở.
4. Listener nhận lại event, thấy `eventId` đã được xử lý, nên **không cập nhật lần nữa**.
5. Listener kết thúc thành công; registry có thể đánh dấu publication hoàn tất.

Đây là một cách để **đóng khoảng lỗi** giữa business side effect và completion mark mà không đòi exactly-once end-to-end không thực tế.

## 10. Không đánh dấu thành công sớm khi khởi tạo công việc bất đồng bộ

Spring Modulith có thể đã gọi listener ở luồng bất đồng bộ thông qua `@ApplicationModuleListener`. Nếu bên trong listener lại tự tạo task mới rồi trả về ngay, registry có thể nhận **kết quả thành công của method** trong khi tác vụ thật chưa xong.

### 10.1. Ví dụ có vấn đề

~~~java
@ApplicationModuleListener
void on(OrderConfirmed event) {
    CompletableFuture.runAsync(() ->
        notificationSender.send(event.orderId())
    );
    // Method return trước khi send(...) thực sự hoàn tất.
}
~~~

Nếu `send(...)` lỗi trong `CompletableFuture`, ngoại lệ có thể không truyền về đường thực thi listener, nên publication bị coi là hoàn tất dù công việc gửi chưa xong.

### 10.2. Phương án an toàn hơn

Nếu tác vụ không cần chạy tách tiếp, thực hiện đồng bộ **bên trong lượt xử lý của listener**:

~~~java
@ApplicationModuleListener
void on(OrderConfirmed event) {
    notificationSender.send(event.orderId());
    // Chỉ trả về sau khi sender kết thúc theo contract của nó.
}
~~~

Nếu thực sự cần tách thành một job khác, listener phải **ghi job bền vững** rồi chỉ hoàn tất trách nhiệm enqueue; job phía sau có lifecycle riêng, có quan sát, retry và idempotency. Không thể đánh dấu “gửi email đã thành công” chỉ vì job đã được tạo trong bộ nhớ.

### 10.3. Listener trả về Future/Publisher cũng cần kiểm tra semantics

Đừng giả định framework luôn đợi kết quả của mọi `CompletionStage`, reactive publisher hoặc callback tùy biến trước khi đánh dấu completion. Cần kiểm tra hỗ trợ của chính annotation, phiên bản Spring và adapter, đồng thời viết integration test tạo lỗi **sau thời điểm method Java return** để xác minh publication không bị completed sớm.

## 11. Resubmission: đánh dấu hoàn tất sau một lần xử lý lại

Việc phục hồi publication chưa hoàn tất là **hoạt động quản lý vòng đời**, không phải bằng chứng rằng bản thân event được phát lại sẽ luôn an toàn.

### 11.1. Luồng phục hồi minh họa

~~~mermaid
flowchart TD
    A[Publication chưa hoàn tất] --> B{Điều kiện retry hợp lệ?}
    B -->|Chưa| C[Ghi cảnh báo / chờ can thiệp]
    B -->|Có| D[Giao lại cho listener]
    D --> E{Listener xử lý xong?}
    E -->|Có| F[Đánh dấu publication completed]
    E -->|Không| G[Ghi nhận lỗi / giữ khả năng khôi phục]
    G --> H[Backoff / giới hạn lần thử]
    H --> B
~~~

Spring Modulith có API quản lý các publication chưa hoàn tất và hỗ trợ resubmit theo phiên bản/backend phù hợp. **Không nên mặc định** tất cả publication được retry tự động vô hạn, hoặc luôn tự phát lại mỗi khi khởi động; chính sách khôi phục phải được cấu hình hoặc vận hành rõ ràng.

### 11.2. Cần làm gì trước khi resubmit?

Kiểm tra:

- Listener đích còn tồn tại và còn xử lý đúng loại event không?
- Payload cũ có còn deserialize được sau nâng cấp schema hoặc đổi package?
- Nguyên nhân lỗi là tạm thời (DB/network) hay vĩnh viễn (dữ liệu không hợp lệ)?
- Dữ liệu của listener đã được cập nhật một phần hoặc toàn bộ ở lần trước chưa?
- Listener đã có cơ chế idempotency khi nhận lại cùng event chưa?
- Nên giới hạn tốc độ retry để không gây quá tải hệ thống mới hồi phục không?

Một lệnh “retry all” không phân loại có thể làm bùng phát tải, tạo nhiều tác dụng phụ trùng và lặp lỗi dữ liệu vô hạn.

### 11.3. Resubmit khác phát một event mới

**Resubmit** nghĩa là thử xử lý lại một publication đã ghi nhận cho sự kiện cũ. **Phát event mới** nghĩa là công bố một sự thật nghiệp vụ mới hoặc một lần phát mới.

Nếu lỗi đã xảy ra ở listener `reporting` của `OrderConfirmed E-42`, hãy ưu tiên khôi phục publication E-42 đúng target. Phát một `OrderConfirmed E-43` mới chỉ để bù lỗi có thể khiến các listener đã thành công xử lý thêm lần nữa, gây email/điểm thưởng trùng nếu không có thiết kế xử lý idempotent.

## 12. Quan sát trạng thái publication trong vận hành

Để biết vì sao cần mark completion và vì sao không nên tự suy từ log, hãy hình dung dashboard:

| Thước đo | Giúp trả lời |
| --- | --- |
| Số publication chưa hoàn tất theo listener | Module nhận nào đang bị tồn đọng? |
| Tuổi publication lâu nhất | Có công việc bị treo quá ngưỡng chấp nhận? |
| Tỷ lệ publication hoàn tất | Bao nhiêu trách nhiệm xử lý được hoàn thành trong một khoảng thời gian? |
| Thời gian từ phát đến hoàn tất | Độ trễ xử lý hậu commit có tăng bất thường? |
| Số lần thử/resubmit | Có retry storm hoặc lỗi kéo dài? |
| Số lỗi theo loại event, listener, nguyên nhân | Lỗi do contract, DB, network hay nghiệp vụ? |
| Số event duplicate bị loại | Idempotency có đang được sử dụng nhiều? |

Đây là **nhóm metric gợi ý**, không khẳng định Spring Modulith mặc định cung cấp đầy đủ tên metric hay trường dữ liệu tương ứng. Khi đo, nên sử dụng event/publication identifier, module nhận, listener, thời điểm và lỗi; hạn chế ghi payload nhạy cảm vào log.

### 12.1. Ví dụ log có cấu trúc

~~~json
{
  "eventType": "OrderConfirmed",
  "eventId": "e620f311-89ed-408b-ad8f-9ecbfc1d14d5",
  "target": "reporting.SalesProjectionListener",
  "publicationStatus": "incomplete",
  "attempt": 3,
  "failureCategory": "database_unavailable"
}
~~~

Schema và giá trị trên **do ứng dụng tự thiết kế để quan sát**, không phải cấu trúc cố định của publication registry. Nếu dùng OpenTelemetry/Micrometer hoặc module observability, cần bảo đảm correlation ID được truyền và gắn với đúng event, tránh ghi thông tin khách hàng không cần thiết.

### 12.2. “Số publication chưa hoàn tất = 0” có đủ để khẳng định an toàn?

Không hoàn toàn. Con số 0 có thể là kết quả tốt khi mọi công việc theo dõi được xử lý, nhưng cũng có thể do:

- Registry chưa được cấu hình nên không có publication nào được ghi.
- Listener không thuộc nhóm được quản lý.
- Listener bắt exception rồi trả về như thành công.
- Event đã bị phát trước khi transaction được tạo hoặc ngoài lifecycle mong đợi.
- Một tác vụ async con vẫn đang xử lý sau khi method listener return.

Phải đối chiếu số sự kiện nghiệp vụ, số publication kỳ vọng, kết quả thực tế của các listener và các dấu hiệu lỗi khác. Không nên coi một metric registry đơn lẻ là bằng chứng end-to-end.

## 13. Phân biệt mark completed với ACK của message broker

Khi Spring Modulith externalize event ra Kafka, AMQP hoặc transport hỗ trợ khác, có thể có **nhiều dấu mốc hoàn tất độc lập**:

~~~text
orders transaction COMMITTED
    |
    v
Spring Modulith publication registered
    |
    v
Externalization adapter sends message
    |
    +--> Broker accepted (theo semantics adapter)
    |        |
    |        +--> Publication completed ở phía producer
    |
    v
Consumer service nhận và xử lý
    |
    +--> Consumer local transaction committed
    +--> Consumer ACK / offset updated
~~~

Completion ở registry của producer thường mô tả kết quả của **trách nhiệm externalizer**, không có nghĩa service tiêu thụ bên ngoài đã tạo dữ liệu đích. Consumer phải có hệ thống ACK/offset và idempotency của mình.

| Đánh dấu / tín hiệu | Thành phần sở hữu | Ý nghĩa |
| --- | --- | --- |
| Publication completed | Spring Modulith producer/registry | Listener mục tiêu hoặc externalizer đã hoàn tất theo cơ chế theo dõi |
| Kafka producer send acknowledged | Producer/broker | Broker đã phản hồi gửi theo cấu hình acknowledgment |
| Kafka consumer offset committed | Consumer group | Consumer đã cập nhật tiến độ đọc, chưa tự chứng minh DB nghiệp vụ đúng |
| Business process completed | Module/service đích | Công việc nghiệp vụ của consumer đã thỏa contract |

Đừng đánh đồng các mốc để tuyên bố “exactly-once” hoặc “tất cả hệ thống đã đồng bộ”. Mỗi ranh giới transaction hoặc mạng có thể phát sinh lỗi và retry độc lập.

## 14. Kiểm thử đúng việc đánh dấu publication

STEP viết bài Knowledge cần phân biệt **kiểm thử một listener thành công** với **kiểm thử registry thực sự lưu và đổi trạng thái**. Với registry, test phải dùng backend và transaction configuration tương tự thực tế; unit test chỉ gọi method listener không đủ để chứng minh integration wiring.

### 14.1. Bộ ca kiểm thử nền tảng

| Ca | Hành động | Kết quả cần xác nhận |
| --- | --- | --- |
| **Commit thành công** | Phát event trong transaction nguồn và commit | Publication được ghi, listener chạy, dấu completed phù hợp |
| **Rollback nguồn** | Phát event rồi rollback transaction | Không có publication đã commit cho sự thật không xảy ra |
| **Listener thành công** | Thực hiện tác vụ hợp lệ | Publication của listener đó được hoàn tất |
| **Listener lỗi** | Cho DB/network lỗi và để exception lan ra | Không có false completion; có thể quan sát publication chưa hoàn tất |
| **Hai listener khác kết quả** | Listener A thành công, B thất bại | Chỉ publication của A completed |
| **Resubmit** | Khôi phục B sau khi sửa lỗi | B xử lý và được đánh dấu completed |
| **Duplicate** | Cho B xử lý lặp event đã áp dụng | Không nhân đôi tác dụng phụ; publication có thể hoàn tất |
| **Lỗi sau side effect** | Commit công việc đích rồi giả lập crash trước dấu completed | Retry không làm sai dữ liệu |
| **Nested async** | Listener tạo task nền lỗi sau khi method return | Phát hiện completion sớm để sửa cách viết listener |
| **Application restart** | Tạo publication chưa hoàn tất rồi khởi động lại | Publication vẫn tồn tại và có thể được khôi phục theo chính sách |

### 14.2. Tránh bẫy transaction của bài test

Nếu test có `@Transactional` và mặc định **rollback sau test**, listener `AFTER_COMMIT` có thể không bao giờ được kích hoạt. Cần dùng một test có transaction nguồn **commit thực sự** hoặc công cụ quản lý test transaction phù hợp; sau đó mới kiểm tra dấu completed.

Khi listener chạy async, dùng điều kiện chờ có timeout để xác minh kết quả cuối cùng, tránh `Thread.sleep(...)` cố định. Đồng thời đừng chỉ kiểm tra event đã được publish; kiểm tra **side effect của module nhận và trạng thái registry**.

### 14.3. Phân biệt kiểm thử lớp nào

~~~mermaid
flowchart TD
    A[Kiểm thử] --> B[Publisher/domain]
    A --> C[Listener logic]
    A --> D[Transaction + registry integration]
    A --> E[Resubmission / restart]
    B --> B1[Event có đúng payload và thời điểm?]
    C --> C1[Thao tác idempotent và lỗi được báo ra?]
    D --> D1[Publication được đánh dấu đúng listener?]
    E --> E1[Không mất việc, không gây trùng khi retry?]
~~~

Kiểm thử Spring Modulith có thể dùng `@ApplicationModuleTest` để giới hạn ngữ cảnh theo module, và kiểm tra sự kiện phát ra bằng công cụ phù hợp như `PublishedEvents`. Tuy nhiên, để xác minh completion thật với JDBC/JPA/Mongo registry, cần load cấu hình registry/transaction và sử dụng tích hợp lưu trữ trong test.

### 14.4. Kiểm thử trường hợp listener bắt exception sai

Tạo một listener giả định:

~~~java
@ApplicationModuleListener
void on(OrderConfirmed event) {
    try {
        repository.failOnPurpose();
    } catch (RuntimeException ex) {
        log.error("Failed but swallowed", ex);
    }
}
~~~

Trong integration test, kiểm tra liệu publication có bị đánh dấu hoàn tất dù nghiệp vụ thất bại. Đây là một kiểm thử quan trọng để dạy **tại sao phải giữ đúng ngữ nghĩa return/exception**. Sau khi xác định hành vi, sửa listener để lỗi cần retry tiếp tục được ném ra hoặc được xử lý bằng workflow lỗi có trạng thái rõ ràng.

## 15. Tình huống thực hành: hai listener, một publication lỗi

Giả sử ứng dụng bán hàng có các module:

- `orders`: quản lý trạng thái đơn.
- `notifications`: gửi xác nhận.
- `reporting`: cập nhật projection doanh thu.

Một lần gọi API tạo `OrderConfirmed(eventId = E-100)`. Transaction nguồn commit thành công. `notifications` gửi thành công, còn `reporting` gặp lỗi database.

### 15.1. Trạng thái kỳ vọng

| Đối tượng | Kết quả | Trạng thái hợp lý |
| --- | --- | --- |
| Order | Đã được xác nhận | `CONFIRMED` |
| Notification listener | Xử lý thành công | Publication đã hoàn tất |
| Reporting listener | Lỗi DB, chưa có projection | Publication chưa hoàn tất |
| Event E-100 | Đã được phát cho các listener có liên quan | Không gộp thành “đã xong hết” |

Hệ thống vận hành cần trả lời được **listener nào đang thiếu việc**, đồng thời không yêu cầu `orders` rollback chỉ vì một tác vụ hậu commit đã thất bại.

### 15.2. Kế hoạch phục hồi

1. Khôi phục database hoặc cấu hình của `reporting`.
2. Kiểm tra publication còn dang dở tương ứng với `reporting`.
3. Xác minh payload cũ vẫn đọc được và logic projection xử lý lặp an toàn.
4. Thực hiện resubmit theo API/chính sách cấu hình phiên bản đang dùng.
5. Đọc lại dữ liệu projection để xác minh kết quả nghiệp vụ.
6. Kiểm tra publication tương ứng đã được đánh dấu completed.
7. Đảm bảo `notifications` không gửi email lần nữa chỉ vì `reporting` được retry.

### 15.3. Nếu reporting đã commit nhưng chưa được mark?

Khi resubmit, listener đọc dấu xử lý `eventId = E-100` và nhận biết projection đã áp dụng thành công. Nó bỏ qua cập nhật trùng, trả về bình thường, cho phép publication được đóng hoàn tất. Đây là cách **idempotency hỗ trợ completion**.

Nếu reporting không lưu dấu xử lý, một sự cố ở đúng thời điểm giữa việc cập nhật dữ liệu và mark completion có thể làm báo cáo tăng số lần không đúng.

### 15.4. Nếu một lần retry thất bại vĩnh viễn?

Không nên retry vô hạn một event không tương thích schema. Cần:

- Ghi nhận loại lỗi và mức độ ảnh hưởng.
- Chọn quy trình sửa dữ liệu, migration payload hoặc điều tra thủ công.
- Xác định có quyền bỏ qua tác vụ không, ai phê duyệt và bằng chứng nghiệp vụ nào.
- Chỉ đóng publication bằng một cơ chế có thể truy vết, khi tiêu chí chấm dứt trách nhiệm đã được định nghĩa.

Không nên dùng hoàn tất giả để chỉ làm bảng “pending” đẹp hơn.

## 16. Checklist để đánh dấu publication đáng tin cậy

- [ ] Publisher phát một event có ý nghĩa nghiệp vụ rõ ràng sau khi các điều kiện cần thiết đã được thỏa mãn.
- [ ] Transaction nguồn và registry backend được cấu hình để ghi nhận publication phù hợp.
- [ ] Listener đang dùng đúng cơ chế transactional theo thời điểm yêu cầu.
- [ ] Mỗi publication được nhận diện theo listener/target, không gộp các listener của cùng event.
- [ ] Điều kiện “listener thành công” được diễn đạt và kiểm thử cụ thể.
- [ ] Exception do tác vụ cần retry không bị bắt rồi nuốt khiến publication completed sai.
- [ ] Listener hậu commit ghi database với transaction phù hợp và có thể xác minh commit.
- [ ] Nested async không khiến method return trước khi công việc chịu trách nhiệm hoàn thành.
- [ ] Có idempotency cho những side effect có thể bị thực hiện lại.
- [ ] Có chính sách phân loại lỗi, giới hạn retry, resubmit và xử lý trường hợp vĩnh viễn.
- [ ] Có kiểm tra publication tồn đọng khi ứng dụng restart hoặc sau khi nâng cấp schema.
- [ ] Đã phân biệt completion phía producer với việc xử lý hoàn tất ở consumer ngoài hệ thống.
- [ ] Log và metric có đủ event ID, listener, trạng thái và thời điểm, nhưng không lộ dữ liệu nhạy cảm.
- [ ] Có integration test cho commit, rollback, hoàn tất, lỗi, retry, duplicate và crash window.

## 17. Câu hỏi tự kiểm tra

1. Vì sao một event có ba listener có thể tương ứng với ba publication khác nhau?
2. `publishEvent(...)` trả về bình thường có chứng minh listener đã hoàn tất chưa?
3. Khi listener bắt exception rồi chỉ log và return, việc đánh dấu completed có thể sai ở đâu?
4. Sự khác biệt giữa transaction nguồn và transaction xử lý listener là gì?
5. Tại sao việc ghi projection đã commit nhưng dấu completed chưa lưu có thể gây cập nhật trùng?
6. Vai trò của `eventId` và unique constraint trong consumer là gì?
7. Tại sao `CompletableFuture.runAsync(...)` bên trong listener có thể tạo false completion?
8. Nếu `notifications` thành công, `reporting` thất bại, publication nào cần khôi phục?
9. Resubmit một publication khác gì phát một event nghiệp vụ mới?
10. Khi externalizer được đánh dấu completed, tại sao consumer ở Kafka vẫn có thể đang chậm?
11. Vì sao integration test `@Transactional` mặc định rollback có thể không kiểm được `AFTER_COMMIT`?
12. Những thông tin nào cần quan sát để điều tra một publication chưa hoàn tất nhiều giờ?

**Ghi nhớ:** Đánh dấu publication là **ghi nhận trách nhiệm xử lý của một listener đã hoàn tất theo contract**, không phải phép màu biến việc phát event thành xử lý chính xác một lần ở mọi hệ thống. Một luồng đáng tin cậy cần kết hợp transaction nguồn, registry bền vững, listener báo thành công/thất bại đúng sự thật, retry có kiểm soát, idempotency và kiểm thử ở những điểm có thể xảy ra gián đoạn.
