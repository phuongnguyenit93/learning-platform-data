# Ghi nhận sự kiện từ aggregate mà không phụ thuộc vào cơ chế vận chuyển

Trong Domain-Driven Design (DDD), **Domain Event** mô tả một sự việc nghiệp vụ đã xảy ra và có ý nghĩa đối với mô hình miền, chẳng hạn `OrderConfirmed`, `PaymentReceived` hoặc `InventoryReserved`. Aggregate là nơi hiểu rõ một hành động có hợp lệ hay không, vì vậy nó thường là nơi ghi nhận sự kiện sau khi hành vi nghiệp vụ thành công.

Tuy nhiên, Aggregate không nên biết sự kiện sẽ được gửi qua Kafka, RabbitMQ, HTTP hay một cơ chế nào khác. Nó chỉ cần ghi nhận sự thật nghiệp vụ bằng một đối tượng sự kiện bất biến. Application và Infrastructure chịu trách nhiệm thu thập, lưu trữ và vận chuyển sự kiện theo chiến lược của hệ thống.

Tách biệt này giúp mô hình miền giữ được tính độc lập, dễ kiểm thử và không bị ràng buộc bởi nhà cung cấp message broker. Đồng thời, nhóm có thể chọn cách phát sự kiện phù hợp với yêu cầu nhất quán: xử lý trong tiến trình, phát sau khi transaction commit hoặc dùng Transactional Outbox để tránh mất sự kiện khi ứng dụng gặp sự cố.

## 1. Domain Event là gì?

Domain Event là bản ghi về một điều có ý nghĩa trong nghiệp vụ đã xảy ra. Tên sự kiện thường dùng thì quá khứ vì nó mô tả một sự thật, không phải yêu cầu thực hiện hành động.

Ví dụ:

| Command hoặc hành động được yêu cầu | Domain Event sau khi thành công |
| --- | --- |
| `PlaceOrder` | `OrderPlaced` |
| `ConfirmOrder` | `OrderConfirmed` |
| `CancelOrder` | `OrderCancelled` |
| `ReceivePayment` | `PaymentReceived` |
| `ReserveInventory` | `InventoryReserved` |
| `DispatchShipment` | `ShipmentDispatched` |

Command thể hiện ý định: ai đó muốn hệ thống làm điều gì. Domain Event thể hiện kết quả: một sự việc đã được xác nhận là xảy ra. Một command có thể bị từ chối và khi đó sự kiện thành công tương ứng không được ghi nhận.

### 1.1. Sự kiện phải có ý nghĩa nghiệp vụ

Không phải mọi thay đổi kỹ thuật đều là Domain Event. Ví dụ `DatabaseRowUpdated`, `HttpRequestReceived` hoặc `JpaEntityFlushed` thường là chi tiết triển khai. Những sự kiện như `OrderConfirmed` hoặc `CreditApplicationRejected` diễn đạt kết quả mà chuyên gia nghiệp vụ có thể quan tâm.

Một sự kiện có thể được dùng để:

- Thông báo cho phần khác của cùng Bounded Context rằng một sự việc đã xảy ra.
- Kích hoạt một quy trình nghiệp vụ tiếp theo.
- Cập nhật read model hoặc báo cáo.
- Ghi nhận lịch sử nghiệp vụ.
- Tạo dữ liệu tích hợp để thông báo cho Bounded Context hoặc hệ thống khác.

### 1.2. Domain Event khác Message và Integration Event

Các khái niệm này liên quan nhưng không đồng nghĩa:

| Khái niệm | Ý nghĩa | Phạm vi |
| --- | --- | --- |
| Domain Event | Sự thật nghiệp vụ đã xảy ra trong mô hình miền. | Bên trong một Bounded Context. |
| Integration Event | Hợp đồng sự kiện được công bố để hệ thống hoặc Bounded Context khác tiêu thụ. | Qua ranh giới tích hợp. |
| Message | Đơn vị dữ liệu được gửi qua một cơ chế truyền tin. | Phụ thuộc giao thức hoặc nền tảng. |
| Command | Yêu cầu một bên thực hiện hành động. | Gửi đến nơi có trách nhiệm xử lý. |

Một Domain Event có thể được chuyển thành Integration Event, nhưng không nhất thiết phải công bố mọi sự kiện nội bộ ra ngoài. Khi tích hợp, nên ánh xạ sang hợp đồng công khai có ngữ nghĩa và phiên bản được quản lý, thay vì để cấu trúc nội bộ của Domain chi phối giao thức bên ngoài.

## 2. Vì sao Aggregate nên ghi nhận sự kiện?

Aggregate Root chịu trách nhiệm bảo vệ các bất biến trong ranh giới Aggregate. Nó biết trạng thái hiện tại, điều kiện chuyển trạng thái và thời điểm hành động thực sự thành công. Vì vậy, đây là nơi phù hợp để ghi nhận sự kiện mô tả kết quả của hành động.

Ví dụ, khi `order.confirm()` được gọi:

1. Order kiểm tra đơn có đang ở trạng thái cho phép xác nhận không.
2. Order kiểm tra các điều kiện nghiệp vụ như có dòng hàng hợp lệ.
3. Nếu hợp lệ, Order chuyển sang trạng thái đã xác nhận.
4. Order ghi nhận `OrderConfirmed`.

Nếu điều kiện không thỏa mãn, hành động bị từ chối và `OrderConfirmed` không được ghi nhận.

Đặt việc ghi nhận tại Aggregate giúp sự kiện phản ánh đúng trạng thái đã được mô hình xác nhận. Nếu Application Service tự tạo sự kiện trước hoặc sau khi gọi các setter, nhiều luồng có thể quên phát sự kiện hoặc phát sự kiện dù thay đổi chưa hợp lệ.

### 2.1. Aggregate ghi nhận sự thật, không gửi sự kiện

Aggregate có thể tạo một đối tượng `OrderConfirmed` và lưu nó trong danh sách sự kiện nội bộ. Aggregate không cần biết:

- Broker nào được dùng.
- Topic, queue hoặc routing key là gì.
- Sự kiện được mã hóa JSON, Avro hay định dạng khác.
- Địa chỉ máy chủ hoặc thông tin xác thực.
- Cách retry hoặc xử lý dead-letter.
- Sự kiện được gửi đồng bộ hay bất đồng bộ.

Những chi tiết này thuộc Application, Infrastructure hoặc cơ chế tích hợp. Aggregate chỉ thể hiện rằng một sự việc nghiệp vụ đã xảy ra.

### 2.2. Chỉ ghi nhận sau khi hành vi hợp lệ

Không ghi nhận sự kiện trước khi các điều kiện nghiệp vụ được kiểm tra và trạng thái được thay đổi thành công. Ví dụ:

~~~java
public void confirm() {
    requireDraft();
    if (lines.isEmpty()) {
        throw new IllegalStateException("An empty order cannot be confirmed");
    }

    status = OrderStatus.CONFIRMED;
    raise(new OrderConfirmed(id, clock.instant()));
}
~~~

Trong ví dụ, `raise(...)` chỉ thêm sự kiện vào danh sách nội bộ. Nó không gửi message ra bên ngoài. Nếu hành động bị từ chối trước khi thay đổi trạng thái, không có sự kiện thành công nào được ghi nhận.

## 3. Mô hình sự kiện độc lập với vận chuyển

Một Domain Event thường là một đối tượng bất biến, chứa dữ liệu đủ để diễn đạt sự việc đã xảy ra. Nó không cần kế thừa từ lớp của message broker hoặc mang annotation của framework.

### 3.1. Định nghĩa hợp đồng sự kiện miền

Có thể bắt đầu bằng một interface đánh dấu:

~~~java
public interface DomainEvent {
}
~~~

Sau đó định nghĩa sự kiện cụ thể:

~~~java
import java.time.Instant;
import java.util.Objects;

public record OrderConfirmed(
        OrderId orderId,
        Instant occurredAt
) implements DomainEvent {
    public OrderConfirmed {
        Objects.requireNonNull(orderId);
        Objects.requireNonNull(occurredAt);
    }
}
~~~

`OrderConfirmed` không chứa Kafka key, exchange, queue, JSON envelope hay URL. Các thông tin đó không thuộc sự thật nghiệp vụ mà sự kiện muốn diễn đạt.

### 3.2. Chọn dữ liệu sự kiện

Payload nên đủ để bên tiêu thụ hiểu sự việc mà không phải truy cập tùy tiện vào trạng thái nội bộ của Aggregate. Một số dữ liệu thường cần:

- Định danh Aggregate liên quan.
- Các giá trị nghiệp vụ đã được xác nhận tại thời điểm sự kiện xảy ra.
- Thời điểm nghiệp vụ nếu nó có ý nghĩa.
- Định danh các đối tượng liên quan khi cần.

Ví dụ, `OrderConfirmed` có thể chỉ cần OrderId và thời điểm xác nhận nếu consumer có thể truy vấn thêm dữ liệu theo một hợp đồng phù hợp. Nếu consumer cần biết giá hoặc số lượng tại thời điểm xác nhận, sự kiện có thể chứa snapshot của những giá trị đó.

Không nên đưa toàn bộ Aggregate vào payload. Làm vậy tạo phụ thuộc mạnh vào cấu trúc nội bộ, tăng kích thước message và khiến thay đổi mô hình khó tương thích.

### 3.3. Sự kiện nên bất biến

Sự kiện mô tả một sự thật đã xảy ra nên dữ liệu của nó không nên bị sửa sau khi tạo. Java record là một lựa chọn phù hợp cho nhiều payload đơn giản. Nếu sự kiện chứa collection, cần tạo bản sao không thể sửa:

~~~java
public record OrderPlaced(
        OrderId orderId,
        List<OrderLineSnapshot> lines,
        Instant occurredAt
) implements DomainEvent {
    public OrderPlaced {
        lines = List.copyOf(lines);
    }
}
~~~

Các phần tử bên trong collection cũng nên là Value Object bất biến. Một danh sách không thể sửa nhưng chứa đối tượng mutable vẫn có thể làm nội dung sự kiện thay đổi ngoài ý muốn.

### 3.4. Phân biệt thời điểm nghiệp vụ và thời điểm vận chuyển

Một sự kiện có thể có thời điểm nghiệp vụ `occurredAt`; message envelope khi gửi có thể có thời điểm `publishedAt` hoặc `receivedAt`. Hai thời điểm này khác nhau:

- `occurredAt`: khi sự việc nghiệp vụ xảy ra.
- `publishedAt`: khi hệ thống phát message ra kênh truyền.
- `receivedAt`: khi consumer nhận được message.

Không nên dùng thời điểm gửi message thay cho thời điểm nghiệp vụ nếu cần phân tích thời gian hoặc xử lý thứ tự sự kiện.

## 4. Aggregate ghi nhận sự kiện trong bộ nhớ

Một cách phổ biến là Aggregate Root giữ danh sách các Domain Event vừa phát sinh trong quá trình xử lý command. Danh sách này là trạng thái tạm thời phục vụ Unit of Work hoặc Application thu thập sự kiện; nó không phải dữ liệu nghiệp vụ lâu dài của Aggregate.

### 4.1. Lớp Aggregate Root cơ sở

~~~java
import java.util.ArrayList;
import java.util.List;

public abstract class AggregateRoot {
    private final List<DomainEvent> domainEvents = new ArrayList<>();

    protected final void raise(DomainEvent event) {
        domainEvents.add(event);
    }

    public final List<DomainEvent> domainEvents() {
        return List.copyOf(domainEvents);
    }

    public final void clearDomainEvents() {
        domainEvents.clear();
    }
}
~~~

Phương thức `raise` được bảo vệ để chỉ hành vi của Aggregate hoặc lớp con có thể ghi nhận sự kiện. `domainEvents()` trả về snapshot chỉ đọc, tránh để caller thêm hoặc xóa sự kiện tùy ý.

`clearDomainEvents()` là thao tác kỹ thuật để Unit of Work hoặc Application dọn danh sách sau khi đã xử lý thành công. Không gọi nó quá sớm trước khi sự kiện được lưu hoặc bàn giao an toàn; nếu transaction thất bại, cần bảo đảm sự kiện không bị mất khỏi quy trình xử lý.

Trong một codebase, có thể thay phương thức clear bằng một API lấy và xóa sự kiện có kiểm soát. Dù chọn cách nào, vòng đời của danh sách sự kiện cần được xác định rõ.

### 4.2. Aggregate phát sinh sự kiện

~~~java
import java.time.Clock;
import java.util.Objects;

public final class Order extends AggregateRoot {
    private final OrderId id;
    private final Clock clock;
    private OrderStatus status = OrderStatus.DRAFT;

    public Order(OrderId id, Clock clock) {
        this.id = Objects.requireNonNull(id);
        this.clock = Objects.requireNonNull(clock);
    }

    public void confirm() {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException("Only draft orders can be confirmed");
        }

        status = OrderStatus.CONFIRMED;
        raise(new OrderConfirmed(id, clock.instant()));
    }

    public OrderId id() {
        return id;
    }
}
~~~

Clock được truyền vào để hành vi có thể kiểm thử với thời gian cố định. Trong một mô hình cụ thể, việc lấy thời gian có thể được thực hiện ở Application và truyền Instant vào hành vi; cách đó cũng giữ cho Domain không cần tự tạo phụ thuộc toàn cục.

Điểm quan trọng là Order chỉ gọi `raise`. Nó không biết ai sẽ nhận `OrderConfirmed` hoặc sự kiện sẽ được lưu ở đâu.

### 4.3. Khi tải lại Aggregate

Khi Repository khôi phục Aggregate từ cơ sở dữ liệu hiện tại, danh sách Domain Event đang chờ thường phải bắt đầu rỗng. Việc dựng lại trạng thái từ dữ liệu đã lưu không có nghĩa là nghiệp vụ vừa xảy ra lần nữa.

Ví dụ, tải một đơn đang ở trạng thái CONFIRMED không được tự động phát lại `OrderConfirmed`. Sự kiện chỉ được ghi nhận khi hành vi xác nhận thực sự được thực hiện. Điều này cần được chú ý trong constructor, mapper và ORM lifecycle callback.

## 5. Luồng từ hành vi Aggregate đến nơi tiêu thụ sự kiện

Một luồng xử lý điển hình:

1. Presentation nhận command và gọi Application Service.
2. Application tải Aggregate qua Repository.
3. Application gọi hành vi trên Aggregate.
4. Aggregate kiểm tra quy tắc, thay đổi trạng thái và ghi nhận Domain Event.
5. Application hoặc Unit of Work thu thập các sự kiện đang chờ.
6. Aggregate và bản ghi sự kiện được lưu theo chiến lược nhất quán đã chọn.
7. Sau khi dữ liệu được commit, dispatcher hoặc publisher chuyển sự kiện đến handler hoặc kênh tích hợp.

~~~mermaid
sequenceDiagram
    actor User as Người dùng
    participant App as Application Service
    participant Repo as Repository
    participant Agg as Aggregate Root
    participant UoW as Unit of Work
    participant Bus as Event Dispatcher
    participant Handler as Event Handler
    User->>App: Command
    App->>Repo: load Aggregate
    Repo-->>App: Aggregate
    App->>Agg: gọi hành vi nghiệp vụ
    Agg->>Agg: kiểm tra bất biến và đổi trạng thái
    Agg->>Agg: ghi nhận Domain Event
    App->>UoW: lưu Aggregate và sự kiện
    UoW->>Repo: persist Aggregate
    UoW->>UoW: commit transaction
    UoW-->>Bus: bàn giao sự kiện sau commit
    Bus->>Handler: dispatch event
~~~

Sơ đồ cho thấy ranh giới trách nhiệm. Aggregate quyết định sự kiện nào đã xảy ra; Application/Unit of Work quản lý thời điểm thu thập và lưu; Dispatcher hoặc Infrastructure quyết định cách vận chuyển.

## 6. Phát sự kiện sau khi transaction commit

Một cách triển khai đơn giản là lưu Aggregate trong transaction, sau đó phát sự kiện khi transaction commit thành công. Điều này tránh trường hợp consumer nhận `OrderConfirmed` trong khi transaction lưu Order sau đó rollback.

Ví dụ khái niệm:

~~~java
public void confirm(OrderId orderId) {
    transaction.execute(() -> {
        Order order = orders.findById(orderId)
                .orElseThrow(() -> new OrderNotFound(orderId));

        order.confirm();
        List<DomainEvent> events = order.domainEvents();
        orders.save(order);

        transaction.afterCommit(() -> {
            eventDispatcher.dispatch(events);
            order.clearDomainEvents();
        });
    });
}
~~~

Đây là pseudocode vì API transaction và callback phụ thuộc framework. Nó minh họa thứ tự mong muốn: chỉ dispatch sau commit và dọn danh sách sau khi callback xử lý. Nếu transaction rollback, Unit of Work nên loại bỏ instance Aggregate đã thay đổi thay vì tái sử dụng nó như trạng thái đã lưu; sự kiện không được xem là đã commit.

### 6.1. Vì sao không phát trước commit?

Nếu gửi message trước khi database commit:

- Consumer có thể xử lý sự kiện trong khi dữ liệu Aggregate chưa tồn tại.
- Transaction có thể rollback nhưng message đã được gửi.
- Các hệ thống khác có thể thực hiện hành động dựa trên một sự việc chưa được lưu thành công.

Vì vậy, phát trước commit có thể tạo ra trạng thái không nhất quán giữa dữ liệu và message.

### 6.2. Phát sau commit vẫn có một khoảng rủi ro

Phát sau commit giải quyết vấn đề gửi trước khi dữ liệu được lưu, nhưng vẫn có khoảng thời gian giữa commit và publish:

1. Database commit thành công.
2. Process bị dừng trước khi publisher gửi message.
3. Aggregate đã được lưu nhưng sự kiện không được phát.

Nếu sự kiện có vai trò quan trọng trong quy trình nghiệp vụ hoặc tích hợp, callback sau commit đơn thuần chưa đủ bảo đảm không mất sự kiện.

## 7. Transactional Outbox: lưu sự kiện cùng transaction

**Transactional Outbox** là một mẫu triển khai giúp đồng bộ việc lưu thay đổi Aggregate với việc ghi nhận thông điệp cần phát. Trong cùng một transaction cơ sở dữ liệu:

- Repository lưu Aggregate.
- Outbox Repository lưu bản ghi sự kiện cần phát.
- Transaction commit cả hai hoặc rollback cả hai.

Một tiến trình riêng đọc Outbox, gửi message đến broker hoặc hệ thống đích, rồi đánh dấu bản ghi đã xử lý. Nhờ đó, nếu ứng dụng dừng sau commit, bản ghi Outbox vẫn còn để dispatcher gửi lại khi hoạt động trở lại.

~~~mermaid
flowchart TD
    A[Application gọi hành vi Aggregate] --> B[Aggregate ghi nhận Domain Event]
    B --> C[Bắt đầu database transaction]
    C --> D[Lưu Aggregate]
    D --> E[Ánh xạ Domain Event thành Outbox Message]
    E --> F[Lưu Outbox Message]
    F --> G{Commit thành công?}
    G -->|Không| H[Rollback cả Aggregate và Outbox]
    G -->|Có| I[Outbox Dispatcher đọc bản ghi chưa gửi]
    I --> J[Publish đến broker hoặc endpoint]
    J --> K[Đánh dấu đã gửi]
~~~

### 7.1. Outbox không thuộc Aggregate

Outbox là cơ chế lưu trữ và vận chuyển của Infrastructure. Aggregate không nên có thuộc tính `outboxMessages` hoặc gọi `outboxRepository.save(...)`. Nó chỉ ghi nhận Domain Event. Application/Unit of Work thu thập sự kiện, ánh xạ sang bản ghi Outbox và lưu trong cùng transaction với Aggregate.

### 7.2. Ví dụ bảng Outbox

Một bản ghi Outbox có thể chứa:

| Trường | Ý nghĩa |
| --- | --- |
| message_id | Định danh duy nhất của message. |
| event_type | Loại sự kiện hoặc Integration Event. |
| aggregate_id | Aggregate phát sinh sự kiện. |
| occurred_at | Thời điểm nghiệp vụ xảy ra. |
| payload | Dữ liệu đã được ánh xạ để gửi. |
| created_at | Thời điểm ghi Outbox. |
| published_at | Thời điểm gửi thành công, nếu có. |
| status | Trạng thái chờ gửi, đang xử lý hoặc đã gửi. |

Định dạng cụ thể tùy hạ tầng. Không nên đưa các trường vận chuyển này vào Domain Event nếu chúng không thuộc ý nghĩa nghiệp vụ.

### 7.3. Dispatcher và xử lý gửi lại

Dispatcher có thể:

- Đọc các bản ghi chưa gửi theo lô.
- Khóa hoặc nhận quyền xử lý để tránh nhiều worker gửi cùng lúc ngoài ý muốn.
- Gửi message đến broker hoặc endpoint.
- Đánh dấu đã gửi sau khi nhận xác nhận.
- Retry khi gặp lỗi tạm thời.
- Đưa lỗi kéo dài vào quy trình xử lý riêng để vận hành điều tra.

Outbox thường cung cấp khả năng giao ít nhất một lần (at-least-once), không tự bảo đảm đúng một lần ở mọi hệ thống. Nếu dispatcher gửi thành công nhưng chết trước khi đánh dấu bản ghi, nó có thể gửi lại. Vì vậy consumer cần xử lý idempotent bằng message ID hoặc business key phù hợp.

### 7.4. Thứ tự sự kiện

Nếu thứ tự sự kiện có ý nghĩa, cần xác định phạm vi thứ tự, ví dụ theo Aggregate ID. Có thể dùng Aggregate version hoặc sequence để nhận diện thứ tự, kết hợp partition key và cách đọc Outbox phù hợp. Không nên giả định một broker hoặc nhiều worker sẽ giữ thứ tự toàn cục nếu hệ thống không cấu hình và thiết kế cho điều đó.

## 8. Ánh xạ Domain Event thành Integration Event

Domain Event phản ánh mô hình nội bộ. Integration Event là hợp đồng được công bố cho bên khác. Hai loại có thể mang dữ liệu giống nhau nhưng không bắt buộc giống cấu trúc.

Ví dụ nội bộ:

~~~java
public record OrderConfirmed(
        OrderId orderId,
        Instant occurredAt,
        Money total
) implements DomainEvent {}
~~~

Hợp đồng tích hợp có thể là:

~~~json
{
  "eventId": "evt-01JABC",
  "eventType": "sales.order-confirmed.v1",
  "aggregateId": "ord-1042",
  "occurredAt": "2026-11-18T03:00:00Z",
  "data": {
    "orderId": "ord-1042",
    "totalAmount": "1250000",
    "currency": "VND"
  }
}
~~~

Ví dụ JSON trên là envelope tích hợp, không phải kiểu mà Aggregate cần biết. Adapter ánh xạ Domain Event sang Integration Event, quản lý tên hợp đồng, version và cách serialize.

Việc tách này cho phép:

- Đổi cấu trúc nội bộ mà không buộc consumer thay đổi.
- Chỉ công bố những sự kiện được phép chia sẻ.
- Bổ sung hoặc loại bỏ trường theo chính sách tương thích.
- Che giấu dữ liệu nhạy cảm hoặc chi tiết nội bộ.
- Quản lý version hợp đồng độc lập với code Domain.

Không nên công bố mọi Domain Event một cách tự động. Hãy xác định sự kiện nào có ý nghĩa với bên ngoài và ai sở hữu hợp đồng tích hợp.

## 9. Domain Event và Event Sourcing không phải một khái niệm

Domain Event có thể được dùng trong một ứng dụng lưu trạng thái hiện tại bằng ORM hoặc cơ sở dữ liệu quan hệ. Aggregate ghi nhận sự kiện để các phần khác phản ứng; Repository vẫn lưu trạng thái Aggregate hiện tại.

**Event Sourcing** là một chiến lược lưu trữ trong đó chuỗi sự kiện là nguồn dữ liệu chính để tái dựng trạng thái Aggregate. Mỗi thay đổi được lưu như một sự kiện trong Event Store và trạng thái được tính bằng cách replay các sự kiện.

| Tiêu chí | Domain Event trong mô hình thông thường | Event Sourcing |
| --- | --- | --- |
| Nguồn dữ liệu chính | Trạng thái hiện tại của Aggregate trong database. | Chuỗi sự kiện đã lưu. |
| Mục đích sự kiện | Thông báo sự việc và hỗ trợ phối hợp. | Là dữ liệu gốc để tái dựng trạng thái. |
| Repository | Tải và lưu trạng thái Aggregate. | Tải lịch sử sự kiện và lưu sự kiện mới. |
| Replay | Không nhất thiết cần replay để tải Aggregate. | Thường replay để tái dựng trạng thái. |

Không cần áp dụng Event Sourcing chỉ vì hệ thống có Domain Event. Có thể ghi nhận và phát sự kiện từ Aggregate trong một kiến trúc lưu trạng thái hiện tại.

## 10. Xử lý nhiều sự kiện và nhiều Aggregate

Một hành vi nghiệp vụ có thể ghi nhận nhiều Domain Event nếu nhiều sự việc thực sự xảy ra. Tuy nhiên, không nên phát sự kiện chỉ để phản ánh từng phép gán thuộc tính.

Ví dụ, một hành động hoàn tất giao hàng có thể tạo `ShipmentDelivered`; nếu chính sách nghiệp vụ đồng thời làm đơn hàng hoàn tất, Order có thể ghi nhận `OrderCompleted`. Hai sự kiện thuộc hai Aggregate khác nhau và có thể được tạo trong một quy trình phối hợp.

Application cần xác định:

- Aggregate nào là chủ sở hữu của từng sự kiện.
- Thay đổi nào nằm trong cùng transaction.
- Sự kiện nào được ghi vào Outbox cùng transaction.
- Consumer nào xử lý và cần idempotency ra sao.
- Nếu một bước thất bại, có hành động bù trừ hoặc trạng thái chờ nào không.

Không nên để một Aggregate tự sửa trạng thái nội bộ của Aggregate khác. Mỗi Root bảo vệ bất biến của mình; Application hoặc Process Manager điều phối các bước giữa chúng.

## 11. Kiểm thử việc ghi nhận sự kiện

Kiểm thử Domain Event ở mức Aggregate nên xác nhận rằng sự kiện phản ánh đúng hành vi nghiệp vụ.

Các tình huống cần kiểm tra:

- Hành vi hợp lệ làm thay đổi trạng thái và ghi nhận đúng sự kiện.
- Hành vi bị từ chối không ghi nhận sự kiện thành công.
- Payload có đúng định danh và dữ liệu nghiệp vụ tại thời điểm xảy ra.
- Sự kiện là bất biến và collection trả về không thể bị caller sửa.
- Tải lại Aggregate từ trạng thái đã lưu không tự phát lại sự kiện cũ.
- Một lần xử lý command không vô tình thu thập hoặc gửi cùng sự kiện hai lần.

Ví dụ JUnit rút gọn:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;

class OrderTest {
    @Test
    void confirmRecordsOrderConfirmed() {
        Clock clock = Clock.fixed(
                Instant.parse("2026-11-18T03:00:00Z"),
                ZoneOffset.UTC
        );
        Order order = Order.draft(new OrderId("ORD-1"), clock);

        order.addLine(new OrderLine(new ProductId("SKU-1"), 1));
        order.confirm();

        assertEquals(OrderStatus.CONFIRMED, order.status());
        assertEquals(1, order.domainEvents().size());
        assertInstanceOf(OrderConfirmed.class, order.domainEvents().getFirst());
    }

    @Test
    void invalidConfirmationDoesNotRecordEvent() {
        Clock clock = Clock.systemUTC();
        Order order = Order.draft(new OrderId("ORD-2"), clock);

        assertThrows(IllegalStateException.class, order::confirm);
        assertTrue(order.domainEvents().isEmpty());
    }
}
~~~

Đây là ví dụ minh họa; các kiểu Order, OrderId, OrderLine, ProductId, OrderStatus và OrderConfirmed được giả định đã được định nghĩa. `List.getFirst()` yêu cầu Java 21 trở lên; với phiên bản thấp hơn có thể dùng `get(0)`.

Kiểm thử dispatcher và Outbox là kiểm thử hạ tầng riêng. Chúng cần xác nhận message được gửi sau commit, retry khi lỗi, không đánh dấu thành công trước khi gửi và consumer có thể xử lý message lặp.

## 12. Những sai lầm thường gặp

### 12.1. Aggregate gọi thẳng Event Bus

Nếu Entity gọi `eventBus.publish(...)`, mô hình miền phụ thuộc cơ chế vận chuyển. Khi đổi broker hoặc muốn kiểm thử độc lập, nhóm phải sửa hoặc mock hạ tầng bên trong Entity. Hãy để Aggregate chỉ ghi nhận Domain Event.

### 12.2. Application tự tạo sự kiện dù hành vi chưa thành công

Nếu Application phát `OrderConfirmed` trước khi gọi `order.confirm()`, sự kiện có thể được phát dù Aggregate từ chối hành động. Hãy để Root ghi nhận sự kiện sau khi xác nhận thay đổi hợp lệ.

### 12.3. Phát message trước khi transaction commit

Consumer có thể nhìn thấy một sự kiện mà thay đổi dữ liệu sau đó rollback. Dùng callback sau commit hoặc Outbox tùy mức bảo đảm cần thiết.

### 12.4. Chỉ dùng callback sau commit cho sự kiện quan trọng

Process có thể dừng sau commit nhưng trước publish. Nếu không được phép mất sự kiện, hãy ghi Outbox trong cùng transaction và dùng dispatcher gửi lại.

### 12.5. Cho rằng Outbox bảo đảm exactly-once

Dispatcher có thể gửi thành công rồi gặp sự cố trước khi đánh dấu bản ghi. Consumer cần idempotency và cơ chế nhận diện message lặp.

### 12.6. Đưa toàn bộ Aggregate vào payload

Payload lớn và gắn chặt vào cấu trúc nội bộ khiến hợp đồng khó thay đổi. Chỉ đưa dữ liệu cần để hiểu sự kiện hoặc thực hiện hành động tiếp theo.

### 12.7. Dùng tên kỹ thuật thay cho tên nghiệp vụ

`OrderTableUpdated` không cho biết sự việc nghiệp vụ nào xảy ra. Hãy dùng tên như `OrderConfirmed` hoặc `OrderCancelled` khi đó là điều đã được xác nhận.

### 12.8. Phát lại sự kiện khi khôi phục Aggregate

Mapper hoặc constructor có thể vô tình gọi hành vi nghiệp vụ trong lúc tải dữ liệu, làm sự kiện cũ được ghi nhận lại. Quá trình rehydration phải khôi phục trạng thái mà không giả lập một command mới.

### 12.9. Nhầm Domain Event với Event Sourcing

Có Domain Event không có nghĩa phải lưu toàn bộ lịch sử sự kiện làm nguồn dữ liệu chính. Hãy chọn Event Sourcing khi yêu cầu về lịch sử, truy vết, tái dựng trạng thái và độ phức tạp vận hành thực sự phù hợp.

## 13. Quy trình thiết kế và phát sự kiện

Có thể áp dụng quy trình sau:

1. **Xác định sự việc nghiệp vụ:** mô tả điều gì đã xảy ra bằng ngôn ngữ quá khứ.
2. **Xác định Aggregate sở hữu hành vi:** tìm Root có trách nhiệm kiểm tra điều kiện và thay đổi trạng thái.
3. **Thiết kế payload:** chọn định danh, dữ liệu nghiệp vụ và thời điểm cần thiết.
4. **Ghi nhận sau khi hành vi thành công:** Aggregate tạo đối tượng sự kiện bất biến và lưu trong danh sách tạm.
5. **Thu thập tại Application/Unit of Work:** lấy snapshot các sự kiện được ghi nhận trong use case.
6. **Lưu thay đổi theo chiến lược nhất quán:** dùng after-commit cho trường hợp chấp nhận khoảng rủi ro; dùng Outbox khi cần bảo đảm bền vững.
7. **Ánh xạ hợp đồng tích hợp:** chỉ công bố các sự kiện cần chia sẻ, không để lộ cấu trúc nội bộ.
8. **Vận chuyển và xử lý:** dispatcher gửi message; consumer xử lý idempotent và có retry phù hợp.
9. **Kiểm thử và quan sát:** kiểm tra hành vi miền, transaction, Outbox, thứ tự và lỗi gửi.

~~~mermaid
flowchart TD
    A[Command đến Application] --> B[Application tải Aggregate]
    B --> C[Aggregate thực hiện hành vi]
    C --> D{Hành vi hợp lệ?}
    D -->|Không| E[Từ chối, không ghi sự kiện thành công]
    D -->|Có| F[Aggregate ghi nhận Domain Event]
    F --> G[Application/Unit of Work thu thập]
    G --> H[Lưu Aggregate và Outbox trong cùng transaction]
    H --> I{Commit thành công?}
    I -->|Không| J[Rollback]
    I -->|Có| K[Dispatcher gửi message]
    K --> L[Consumer xử lý idempotent]
~~~

## 14. Checklist ghi nhận sự kiện độc lập vận chuyển

- [ ] Sự kiện mô tả một sự thật nghiệp vụ đã xảy ra.
- [ ] Tên sự kiện dùng thì quá khứ và thuật ngữ của Bounded Context.
- [ ] Aggregate sở hữu hành vi ghi nhận sự kiện sau khi hành động hợp lệ.
- [ ] Aggregate không phụ thuộc Event Bus, broker, HTTP hoặc serializer.
- [ ] Payload bất biến và chỉ chứa dữ liệu nghiệp vụ cần thiết.
- [ ] Thời điểm nghiệp vụ được phân biệt với thời điểm publish/receive.
- [ ] Danh sách sự kiện tạm thời có vòng đời rõ ràng.
- [ ] Tải lại Aggregate không tự ghi nhận lại sự kiện cũ.
- [ ] Application/Unit of Work thu thập sự kiện sau hành vi.
- [ ] Đã xác định phát sau commit hay cần Transactional Outbox.
- [ ] Consumer có xử lý message lặp và retry.
- [ ] Domain Event được ánh xạ thành Integration Event khi cần chia sẻ ra ngoài.
- [ ] Hợp đồng tích hợp có version và không làm lộ mô hình nội bộ.
- [ ] Kiểm thử bao gồm thành công, thất bại, transaction và vận chuyển.

## 15. Kết luận

Ghi nhận sự kiện từ Aggregate mà không phụ thuộc cơ chế vận chuyển là cách giữ cho mô hình miền tập trung vào sự thật nghiệp vụ. Aggregate kiểm tra quy tắc, thay đổi trạng thái và ghi nhận Domain Event bất biến sau khi hành vi thành công. Nó không biết sự kiện được gửi qua broker nào hoặc được serialize ra sao.

Application và Unit of Work thu thập sự kiện; Infrastructure quyết định cách lưu và vận chuyển. Callback sau commit có thể đủ cho các tình huống chấp nhận rủi ro mất message nhỏ, còn Transactional Outbox phù hợp khi cần lưu thay đổi Aggregate và ý định phát sự kiện một cách nguyên tử. Consumer vẫn cần idempotency vì việc gửi có thể lặp. Khi phân biệt rõ Domain Event, Integration Event và Message, hệ thống giữ được mô hình miền độc lập mà vẫn hỗ trợ phối hợp tin cậy giữa các thành phần.
