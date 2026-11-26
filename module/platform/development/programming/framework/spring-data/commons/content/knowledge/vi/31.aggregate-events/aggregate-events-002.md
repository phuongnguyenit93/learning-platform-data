# @DomainEvents và phương thức cung cấp sự kiện

## Mục tiêu và phạm vi

Trong Spring Data Commons, `@DomainEvents` đánh dấu một phương thức của aggregate root để cung cấp các sự kiện nghiệp vụ đang chờ phát. Hạ tầng repository có hỗ trợ aggregate events sẽ gọi phương thức này tại những điểm tích hợp thích hợp, rồi chuyển các sự kiện cho cơ chế application event của Spring.

Annotation này giúp nối hành vi của aggregate với hạ tầng repository. Nó không tự theo dõi mọi thay đổi thuộc tính, không tự lưu lịch sử sự kiện xuống database và không tự gửi message đến Kafka, RabbitMQ hay một hệ thống bên ngoài.

Sau bài học, bạn cần có khả năng:

- Viết phương thức `@DomainEvents` không có tham số, trả về một sự kiện hoặc một tập sự kiện.
- Phân biệt việc ghi nhận sự kiện trong aggregate với việc phát sự kiện qua repository.
- Dọn các sự kiện đã được cung cấp bằng `@AfterDomainEventPublication`.
- Xác định giới hạn của cơ chế này với transaction, listener, thao tác ghi trực tiếp và từng loại store.

Các ví dụ chính sử dụng repository đồng bộ của Spring Data JPA để có một đường thực thi cụ thể. Hợp đồng annotation thuộc Commons; mapping entity, transaction và khả năng tích hợp repository vẫn phụ thuộc module store. Ví dụ dùng Java có hỗ trợ record và namespace `jakarta.persistence`.

## 1. Sự kiện thuộc về hành vi của aggregate

Aggregate root là điểm kiểm soát các thay đổi nghiệp vụ trong một aggregate. Một domain event biểu diễn điều có ý nghĩa nghiệp vụ đã xảy ra trong phạm vi hành vi đó.

Ví dụ:

- `OrderSubmitted`: đơn hàng đã được gửi để xử lý.
- `OrderCancelled`: đơn hàng đã được hủy theo quy tắc nghiệp vụ.
- `ShippingAddressChanged`: địa chỉ giao hàng đã thay đổi.

Tên sự kiện nên thể hiện một sự việc, không phải một yêu cầu thực thi. `SubmitOrder` là tên phù hợp hơn cho command; `OrderSubmitted` là tên phù hợp hơn cho event.

Sự kiện cũng không đồng nhất với một lần gọi `save()`. Một lần lưu có thể không phát sinh sự kiện nghiệp vụ nào, hoặc có thể đưa ra nhiều sự kiện đã được aggregate ghi nhận trước đó.

```text
Ứng dụng gọi hành vi nghiệp vụ
    -> aggregate kiểm tra điều kiện hợp lệ
    -> aggregate thay đổi trạng thái
    -> aggregate ghi nhận sự kiện vào bộ nhớ
    -> ứng dụng gọi repository được hỗ trợ
    -> repository lấy sự kiện qua @DomainEvents
    -> Spring phát application event
```

Việc “đã xảy ra” trong tên domain event phản ánh quyết định nghiệp vụ của aggregate. Nó chưa tự chứng minh rằng transaction đã commit hay hệ thống bên ngoài đã nhận sự kiện.

## 2. Hợp đồng của phương thức @DomainEvents

Annotation cần dùng là:

```java
import org.springframework.data.domain.DomainEvents;
```

Đặt annotation trên một phương thức của aggregate root. Phương thức đó:

1. Không nhận tham số.
2. Trả về một đối tượng sự kiện hoặc một collection các đối tượng sự kiện.
3. Cung cấp các sự kiện đã được ghi nhận, thay vì tạo lại một sự kiện mới mỗi lần framework đọc.
4. Không nên thực hiện I/O, gọi repository khác hoặc thay đổi trạng thái nghiệp vụ.

Dạng thường dùng:

```java
@DomainEvents
public Collection<Object> domainEvents() {
    return List.copyOf(pendingEvents);
}
```

`pendingEvents` là bộ đệm của aggregate trong bộ nhớ, không phải thành phần do annotation tự tạo. `List.copyOf(...)` trả về một snapshot không cho sửa qua collection được trả về.

Các đối tượng sự kiện có thể là POJO hoặc record; chúng không bắt buộc kế thừa `ApplicationEvent`.

| Cách thiết kế | Ý nghĩa |
|---|---|
| Trả về một event object | Phù hợp khi có đúng một sự kiện cần cung cấp |
| Trả về `Collection<EventType>` hoặc `Collection<Object>` | Phù hợp với không, một hoặc nhiều sự kiện đang chờ |
| Trả collection rỗng | Không có sự kiện để phát |
| Tạo event mới ngay trong provider | Dễ phát ra sự kiện không tương ứng với hành vi mới |
| Trả `Stream`, `Mono` hoặc `Flux` | Không phải hợp đồng để Commons tự mở rộng thành tập domain events |

Nên có một phương thức đầu mối `@DomainEvents` cho mỗi aggregate root. Không khai báo nhiều phương thức rồi kỳ vọng framework tự hợp nhất các kết quả theo một thứ tự nghiệp vụ.

Chọn collection rỗng cho trạng thái không có sự kiện giúp hợp đồng rõ ràng hơn việc trả `null`. Không đưa phần tử `null` vào collection.

## 3. Thiết kế payload sự kiện

Ví dụ một sự kiện đơn hàng:

```java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

public record OrderSubmitted(
        UUID eventId,
        UUID orderId,
        String customerId,
        BigDecimal total,
        Instant occurredAt
) {
}
```

Các trường có nhiệm vụ khác nhau:

| Trường | Mục đích |
|---|---|
| `eventId` | Nhận diện một sự kiện cụ thể; hữu ích khi thiết kế chống xử lý trùng |
| `orderId` | Liên hệ sự kiện với aggregate phát sinh |
| `customerId` | Dữ kiện nghiệp vụ cần cho bên xử lý |
| `total` | Snapshot giá trị tại lúc hành vi diễn ra |
| `occurredAt` | Thời điểm nghiệp vụ ghi nhận sự kiện |

Không truyền toàn bộ JPA entity vào event chỉ để listener tự đọc mọi thứ về sau. Listener có thể chạy sau commit, khi trạng thái đã đổi hoặc khi không còn điều kiện truy cập thuộc tính lazy.

Các thành phần payload trong ví dụ đều là kiểu giá trị bất biến. Nếu payload chứa `List`, `Map` hoặc một object có thể thay đổi, cần tạo bản sao hoặc biểu diễn bất biến phù hợp. Record không tự biến mọi object lồng bên trong thành bất biến.

`eventId` không tự tạo ra bảo đảm xử lý một lần. Consumer hoặc cơ chế lưu bền vẫn phải thực hiện chính sách idempotency nếu nghiệp vụ cần.

## 4. Ví dụ aggregate tự quản lý sự kiện

Ví dụ dưới đây dùng một JPA entity để minh họa đồng thời trạng thái nghiệp vụ và bộ đệm sự kiện. Mỗi code block khai báo kiểu public riêng được hiểu là một đơn vị mã nguồn riêng trong ứng dụng.

```java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import java.util.Objects;
import java.util.UUID;

import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Transient;
import jakarta.persistence.Version;

import org.springframework.data.domain.AfterDomainEventPublication;
import org.springframework.data.domain.DomainEvents;

@Entity
@Table(name = "purchase_order")
public class PurchaseOrder {

    public enum Status {
        DRAFT, SUBMITTED
    }

    @Id
    private UUID id;

    @Version
    private Long version;

    private String customerId;

    private BigDecimal total;

    @Enumerated(EnumType.STRING)
    private Status status;

    @Transient
    private final List<Object> pendingEvents = new ArrayList<>();

    protected PurchaseOrder() {
    }

    public PurchaseOrder(String customerId, BigDecimal total) {
        if (customerId == null || customerId.isBlank()) {
            throw new IllegalArgumentException("Customer is required");
        }
        if (total == null || total.signum() <= 0) {
            throw new IllegalArgumentException("Total must be positive");
        }

        this.id = UUID.randomUUID();
        this.customerId = customerId;
        this.total = total;
        this.status = Status.DRAFT;
    }

    public void submit(Instant occurredAt) {
        Objects.requireNonNull(occurredAt, "occurredAt");

        if (status != Status.DRAFT) {
            throw new IllegalStateException("Only a draft can be submitted");
        }

        status = Status.SUBMITTED;

        pendingEvents.add(new OrderSubmitted(
                UUID.randomUUID(),
                id,
                customerId,
                total,
                occurredAt
        ));
    }

    @DomainEvents
    public Collection<Object> domainEvents() {
        return List.copyOf(pendingEvents);
    }

    @AfterDomainEventPublication
    public void clearDomainEvents() {
        pendingEvents.clear();
    }

    public UUID getId() {
        return id;
    }
}
```

### 4.1. Tại sao event được tạo trong submit()?

`submit()` biết điều kiện nghiệp vụ đã được kiểm tra và trạng thái đã chuyển từ `DRAFT` sang `SUBMITTED`. Đây là nơi có đủ ngữ cảnh để ghi nhận `OrderSubmitted`.

Provider `domainEvents()` chỉ đọc kết quả đã được ghi nhận. Nếu framework hoặc một phép kiểm tra gọi provider hai lần trước khi dọn, cả hai lần phải phản ánh cùng những sự kiện đang chờ, thay vì sinh thêm `eventId` hoặc đổi `occurredAt`.

Nếu điều kiện nghiệp vụ không hợp lệ, phương thức ném exception trước khi thêm sự kiện. Không ghi nhận sự kiện thành công rồi mới kiểm tra điều kiện thất bại.

### 4.2. Tại sao pendingEvents là transient?

Bộ đệm này phục vụ việc công bố sự kiện trong tiến trình hiện tại. Trong ví dụ JPA, `jakarta.persistence.Transient` loại nó khỏi mapping persistent của entity.

Với MongoDB, JDBC hoặc store khác, sử dụng cơ chế loại trừ mapping tương ứng của module đó. Không mang annotation JPA sang document rồi mặc định rằng nó được xử lý giống nhau.

Loại khỏi mapping cũng có nghĩa: tải lại entity từ database không khôi phục các sự kiện từng nằm trong bộ đệm. Đây không phải event store.

### 4.3. Vì sao ID được cấp trước?

Event cần chứa một `orderId` ổn định ngay tại lúc `submit()` tạo payload. Ví dụ cấp UUID trong constructor, do đó không phải chờ database sinh ID.

`@Version Long version` còn giúp Spring Data JPA nhận diện trạng thái mới theo metadata version khi phiên bản chưa được gán. Đây là một phần của lựa chọn mapping trong ví dụ, không phải yêu cầu của `@DomainEvents`.

Nếu dự án dùng ID do database sinh, cần thiết kế rõ thời điểm event được tạo. Một event bất biến đã chụp `orderId = null` không tự đổi sang ID vừa được cấp sau khi lưu.

## 5. @AfterDomainEventPublication dọn bộ đệm, không xác nhận commit

Annotation cleanup thuộc cùng package với `@DomainEvents`:

```java
import org.springframework.data.domain.AfterDomainEventPublication;
```

Phương thức cleanup thường không có tham số, trả `void` và chỉ xóa những sự kiện đã được cung cấp:

```java
@AfterDomainEventPublication
public void clearDomainEvents() {
    pendingEvents.clear();
}
```

Vai trò của hai annotation cần tách rõ:

| Annotation | Công việc |
|---|---|
| `@DomainEvents` | Cung cấp những event object đang chờ |
| `@AfterDomainEventPublication` | Dọn bộ đệm sau bước công bố sự kiện của hạ tầng repository |

Không xóa bộ đệm ngay trong provider:

```java
// Cách thiết kế nên tránh.
@DomainEvents
public Collection<Object> domainEvents() {
    var snapshot = List.copyOf(pendingEvents);
    pendingEvents.clear();
    return snapshot;
}
```

Thiết kế trên trộn việc đọc với việc tiêu thụ. Một lần gọi để xem nội dung đã làm mất các sự kiện khỏi aggregate trước bước cleanup được chỉ định.

Ngược lại, nếu không có cleanup tương ứng, những event còn nằm trong bộ đệm có thể được cung cấp lại ở lần gọi repository tiếp theo trên cùng object.

Tên `AfterDomainEventPublication` không có nghĩa là:

- Transaction chắc chắn đã commit.
- Mọi listener bất đồng bộ đã xử lý xong.
- Broker bên ngoài đã xác nhận message.
- Mọi tác dụng phụ đã được thực hiện thành công và đúng một lần.

Với cấu hình phát application event đồng bộ, lời gọi publisher có thể kích hoạt listener ngay trên luồng hiện tại. Với listener theo transaction hoặc bất đồng bộ, việc xử lý thực tế có thể diễn ra ở thời điểm khác. Cleanup không phải một giao thức xác nhận giao nhận bền vững.

## 6. Repository tạo điểm nối với application event của Spring

Repository cho ví dụ:

```java
import java.util.UUID;

import org.springframework.data.jpa.repository.JpaRepository;

public interface OrderRepository
        extends JpaRepository<PurchaseOrder, UUID> {
}
```

Ví dụ application service:

```java
import java.time.Clock;
import java.util.UUID;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderApplicationService {

    private final OrderRepository orders;
    private final Clock clock;

    public OrderApplicationService(
            OrderRepository orders,
            Clock clock
    ) {
        this.orders = orders;
        this.clock = clock;
    }

    @Transactional
    public UUID submit(UUID orderId) {
        PurchaseOrder order = orders.findById(orderId)
                .orElseThrow(() ->
                        new IllegalArgumentException("Order not found"));

        order.submit(clock.instant());

        PurchaseOrder saved = orders.save(order);
        return saved.getId();
    }
}
```

Ứng dụng cần cung cấp bean `Clock`, ví dụ `Clock.systemUTC()`, cùng cấu hình JPA và schema phù hợp. Đưa đồng hồ vào service giúp thời gian của hành vi dễ kiểm soát hơn trong kiểm thử.

Trong ví dụ này, thứ tự có ý nghĩa:

1. Tải aggregate.
2. Thực hiện hành vi và ghi nhận event.
3. Gọi repository qua Spring proxy.
4. Hạ tầng repository lấy và phát event.
5. Transaction bao ngoài hoàn tất theo kết quả thực thi.

Không cần đăng ký aggregate làm Spring bean. Annotation trên aggregate là metadata mà hạ tầng repository kiểm tra; bản thân aggregate không phải một application service.

Nếu `save()` trả về một object khác, ứng dụng nên dùng kết quả trả về cho các thao tác tiếp theo phù hợp với store. Đồng thời, đừng giả định hạ tầng sẽ tìm sự kiện trong mọi bản sao của entity: sự kiện cần nằm trên aggregate được truyền qua đường repository mà cơ chế tích hợp hỗ trợ.

## 7. Những thao tác nào làm provider được gọi?

Với tích hợp repository hỗ trợ aggregate events, `save(...)` và `saveAll(...)` là các điểm nối điển hình. Những thao tác xóa nhận chính aggregate instance cũng có thể tham gia theo API được module và phiên bản hỗ trợ.

Điểm quan trọng là hạ tầng phải có aggregate instance để gọi phương thức cung cấp sự kiện.

| Thao tác | Cách đánh giá |
|---|---|
| Gọi `order.submit(...)` | Ghi nhận event trong bộ nhớ; chưa tự phát qua repository |
| Gọi `save(order)` qua repository được hỗ trợ | Là điểm tích hợp để lấy sự kiện từ aggregate |
| Gọi `saveAll(orders)` | Sự kiện thuộc từng aggregate, không tự biến thành một event chung cho cả batch |
| Xóa bằng API nhận aggregate | Kiểm tra hỗ trợ cụ thể của API và store; không mặc định mọi overload như nhau |
| Gọi `deleteById(id)` | Không dựa vào nó để lấy event từ một aggregate đã được tải |
| Thực thi SQL hoặc bulk query | Không tự gọi provider của từng aggregate |
| Ghi bằng API trực tiếp của driver | Không đi qua interceptor repository này |

`deleteById(...)` không phải điểm nối có thể trông cậy cho cơ chế này vì một implementation có thể xóa theo ID mà không cần có aggregate instance trong bộ nhớ.

Ngay cả với thao tác xóa nhận aggregate, event nghiệp vụ vẫn phải được aggregate ghi nhận. Repository không tự chế tạo `OrderCancelled` chỉ vì thấy một lệnh delete.

### Trường hợp dễ nhầm với JPA dirty checking

Trong JPA, một entity managed có thể được cập nhật khi transaction flush dù ứng dụng không gọi lại `save()`. Điều đó không đồng nghĩa interceptor phát aggregate events của repository đã chạy.

Nếu service chỉ làm:

```java
PurchaseOrder order = orders.findById(orderId).orElseThrow();
order.submit(clock.instant());
// Transaction có thể flush trạng thái của entity.
// Chưa có lời gọi save(order) để đi qua điểm nối phát event này.
```

database có thể được cập nhật trong khi event vẫn chỉ nằm trong bộ đệm của object.

Vì vậy, nếu thiết kế dựa trên aggregate events qua repository, cần thống nhất đường thực hiện command và điểm gọi repository. Không suy ra “database đã đổi” là “`@DomainEvents` chắc chắn đã chạy”.

## 8. Phát event và xử lý sau commit là hai lựa chọn khác nhau

Listener thông thường có thể đăng ký bằng `@EventListener`:

```java
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class OrderEventObserver {

    private static final System.Logger LOG =
            System.getLogger(OrderEventObserver.class.getName());

    @EventListener
    public void on(OrderSubmitted event) {
        LOG.log(
                System.Logger.Level.INFO,
                "Observed OrderSubmitted: " + event.eventId()
        );
    }
}
```

Với cấu hình multicaster thông thường và không có xử lý bất đồng bộ, listener này chạy trong tiến trình và thường trên luồng phát event. Việc listener được gọi chưa xác nhận transaction bao ngoài đã commit.

Nếu chỉ muốn phản ứng sau commit thành công, dùng listener theo transaction:

```java
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class CommittedOrderObserver {

    private static final System.Logger LOG =
            System.getLogger(CommittedOrderObserver.class.getName());

    @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT
    )
    public void on(OrderSubmitted event) {
        LOG.log(
                System.Logger.Level.INFO,
                "Order committed: " + event.orderId()
        );
    }
}
```

Hai listener trên là hai minh họa về thời điểm quan sát. Nếu cùng đăng ký cả hai trong ứng dụng, cả hai có thể nhận sự kiện theo điều kiện của chúng; chúng không thay thế nhau tự động.

Một số điều kiện quan trọng:

- Listener theo transaction cần sự kiện được phát trong ngữ cảnh transaction thích hợp để đăng ký xử lý theo phase.
- Nếu không có transaction, mặc định `@TransactionalEventListener` không xử lý event; `fallbackExecution` là một lựa chọn có chủ đích, không phải cách bật ngữ nghĩa after-commit khi không có commit.
- Transaction bao quanh application service giúp biên giao dịch của ví dụ rõ ràng.
- Listener `AFTER_COMMIT` không thể đảo ngược transaction đã commit chỉ vì việc gửi email hoặc gọi HTTP sau đó thất bại.
- Nếu listener sau commit cần ghi thêm dữ liệu, phải thiết kế transaction cho thao tác đó rõ ràng; không mặc định nó còn thuộc transaction vừa hoàn tất.

Thêm `@Async` cũng không biến application event thành hàng đợi bền vững. Nó còn thay đổi luồng thực thi, cách truyền ngữ cảnh và cách quan sát lỗi.

## 9. Hiểu các tình huống lỗi và phát lại

Bộ đệm sự kiện là trạng thái của object trong bộ nhớ. Nó không có đầy đủ ngữ nghĩa giao dịch của database.

| Tình huống | Hệ quả cần hiểu |
|---|---|
| Repository thất bại trước bước phát event | Không coi event đã được công bố thành công |
| Listener đồng bộ ném exception | Lời gọi repository có thể thất bại; cleanup có thể chưa được thực hiện |
| Một số listener chạy xong rồi listener khác lỗi | Tác dụng phụ đã xảy ra không tự được hoàn tác đồng loạt |
| Cleanup đã chạy nhưng transaction bao ngoài rollback | Object có thể đã mất bộ đệm event dù dữ liệu chưa commit |
| Transaction commit, sau đó tiến trình dừng trước khi xử lý ngoài hệ thống | Application event trong bộ nhớ không tự phục hồi phần việc còn thiếu |
| Thực hiện lại command hoặc phát lại event | Có thể có xử lý trùng; cần chính sách idempotency nếu nghiệp vụ yêu cầu |

Với transaction bao ngoài và exception được truyền ra theo rollback rules, lỗi listener đồng bộ có thể dẫn tới rollback. Không dựa vào nhận định rằng mọi listener lỗi ở mọi phase đều làm rollback được dữ liệu đã ghi.

Cũng không nên giữ một aggregate instance đã trải qua transaction thất bại để thử lại tùy tiện. Trạng thái entity, bộ đệm event và dữ liệu đã commit có thể không còn đồng nhất. Một chiến lược retry cần xác định rõ việc tải lại dữ liệu và tái thực hiện command.

Nếu listener sửa chính bộ đệm event của aggregate đang được công bố, việc diễn giải tập sự kiện sẽ trở nên khó kiểm soát. Đừng dùng callback listener để thêm sự kiện vào cùng danh sách đang được hạ tầng đọc. Một hành vi nghiệp vụ tiếp theo nên có ranh giới command và transaction rõ ràng.

## 10. Khi cần chuyển sự kiện ra ngoài tiến trình

`@DomainEvents` phù hợp để đưa sự kiện của aggregate vào hạ tầng application event trong ứng dụng có hỗ trợ.

Nếu yêu cầu là “đơn hàng và thông tin cần gửi phải cùng được lưu thành công, sau đó có thể retry gửi ra broker”, chỉ dùng bộ đệm trong aggregate và listener gửi message trực tiếp là chưa đủ.

Một hướng thiết kế là transactional outbox:

```text
Transaction xử lý command
    -> lưu trạng thái aggregate
    -> lưu bản ghi outbox trong cùng transaction
    -> commit

Bộ phát riêng
    -> đọc bản ghi outbox chưa xử lý
    -> gửi message
    -> quản lý trạng thái, retry và chống xử lý trùng
```

Cần triển khai việc lưu outbox và transaction chung một cách tường minh. `@DomainEvents` không tự tạo bảng outbox, không tự lưu payload và không tự phối hợp transaction của database với broker.

Tương tự, event sourcing yêu cầu lưu chuỗi sự kiện làm nguồn sự thật và tái dựng trạng thái theo một mô hình riêng. Việc đánh dấu một method `@DomainEvents` không biến entity thông thường thành aggregate event-sourced.

## 11. Các thiết kế provider cần tránh

### 11.1. Sinh lại event trong mỗi lần đọc

```java
// Không gắn sự kiện với một chuyển trạng thái mới.
@DomainEvents
public Object domainEvents() {
    return new OrderSubmitted(
            UUID.randomUUID(),
            id,
            customerId,
            total,
            Instant.now()
    );
}
```

Mỗi lần provider được gọi sẽ tạo một sự kiện mới dù không có hành vi submit mới. Cách sửa là ghi nhận event ở nơi hành vi xảy ra và để provider chỉ trả về bộ đệm.

### 11.2. Cho client sửa collection nội bộ

```java
// Bên gọi có thể thêm, xóa hoặc sửa tập sự kiện đang chờ.
@DomainEvents
public Collection<Object> domainEvents() {
    return pendingEvents;
}
```

Một snapshot bất biến giúp bảo vệ bộ đệm khỏi thay đổi qua giá trị trả về. Tuy nhiên, snapshot không biến aggregate thành object an toàn cho nhiều thread. Aggregate và transaction vẫn phải được quản lý theo mô hình thực thi của ứng dụng.

### 11.3. Chạy tác dụng phụ trong provider

Provider không nên gửi email, gọi API thanh toán hoặc chạy query chỉ để “chuẩn bị event”. Những việc đó làm việc đọc sự kiện có thể chậm, lỗi hoặc gây tác dụng phụ lặp lại.

Payload nên được chuẩn bị từ dữ kiện nghiệp vụ đã có. Công việc phản ứng với event thuộc listener hoặc cơ chế xử lý tiếp theo có trách nhiệm rõ ràng.

### 11.4. Xem save() là bảo đảm commit

Provider có thể được gọi khi transaction bao ngoài chưa hoàn tất. Nếu listener thông thường gửi thông báo ngay, hệ thống bên ngoài có thể đã nhận thông báo trong khi transaction sau đó rollback.

Chọn listener theo transaction hoặc một thiết kế lưu bền phù hợp với yêu cầu. Không đổi ý nghĩa của `@DomainEvents` thành một callback sau commit chỉ bằng cách đặt tên method khác.

### 11.5. Phụ thuộc thứ tự xử lý ngầm định

Một `List` thể hiện thứ tự ghi nhận trong bộ đệm của một aggregate, nhưng không thiết lập một thứ tự nghiệp vụ toàn cục giữa các aggregate, listener hay tiến trình.

Nếu thứ tự là một phần của hợp đồng tích hợp, cần mô hình hóa nó rõ ràng, chẳng hạn bằng sequence/version thích hợp và một cơ chế vận chuyển có đặc tính phù hợp.

## 12. Tự quản lý bộ đệm hay dùng AbstractAggregateRoot?

Commons cung cấp `AbstractAggregateRoot<A>` như một lớp tiện ích để ghi nhận, cung cấp và dọn các sự kiện.

Nếu kế thừa lớp này, hành vi nghiệp vụ có thể dùng `registerEvent(event)` thay cho việc tự quản lý danh sách. Cơ chế provider và cleanup đã được tổ chức trong lớp cơ sở.

Lựa chọn phụ thuộc thiết kế:

| Tự khai báo provider và cleanup | Dùng `AbstractAggregateRoot` |
|---|---|
| Kiểm soát rõ cấu trúc bộ đệm và phương thức | Giảm mã quản lý sự kiện lặp lại |
| Không chiếm vị trí lớp cha | Cần chấp nhận quan hệ kế thừa |
| Dễ học trực tiếp hợp đồng của hai annotation | Dùng các phương thức hỗ trợ của lớp cơ sở |
| Phải tự bảo đảm bộ đệm được dọn đúng | Vẫn cần hiểu giới hạn repository và transaction |

Không kết hợp hai bộ đệm độc lập rồi đăng ký cùng event vào cả hai. Không thêm một provider thứ hai chỉ để lặp lại các event lớp cơ sở đã cung cấp.

Dù lựa chọn nào, sự kiện vẫn cần được ghi nhận từ hành vi nghiệp vụ, và vẫn không tự trở thành dữ liệu được lưu bền.

## 13. Xác minh đúng điều cần kiểm tra

### 13.1. Kiểm tra hành vi của aggregate

Ở mức kiểm tra object thuần:

1. Tạo đơn hàng hợp lệ.
2. Gọi `submit(T1)`.
3. Đọc provider và kiểm tra có đúng một `OrderSubmitted`.
4. Kiểm tra payload chứa ID, tổng tiền và thời gian đúng.
5. Đọc provider lần nữa trước cleanup; không có event mới hoặc timestamp mới.
6. Gọi cleanup; provider trở về collection rỗng.
7. Gọi hành vi không hợp lệ; không ghi nhận thêm event thành công.

Những kiểm tra này xác minh logic bộ đệm và nghiệp vụ, không chứng minh Spring đã tự phát event.

### 13.2. Kiểm tra tích hợp repository

Để xác minh annotation và proxy hoạt động, dùng repository thật được Spring tạo trong application context có store phù hợp.

Một kịch bản có ích:

- Tạo hoặc tải aggregate.
- Gọi hành vi để ghi nhận event.
- Lưu qua repository.
- Quan sát event bằng listener kiểm tra.
- Xác minh cleanup trên aggregate đã đi qua đường công bố.
- Lưu lại khi không có hành vi mới và xác minh không có event nghiệp vụ mới tương ứng.

Mock repository chỉ trả lại đối tượng không tự tái hiện interceptor phát aggregate events. Một bài kiểm tra chỉ xác minh `save()` được gọi là chưa đủ cho tính năng này.

### 13.3. Kiểm tra transaction riêng

Với listener `AFTER_COMMIT`, cần tạo tình huống commit thực sự. Một integration test có transaction tự rollback ở cuối không chứng minh listener sau commit hoạt động.

Nên phân biệt hai kịch bản:

| Kịch bản | Kỳ vọng |
|---|---|
| Event được phát trong transaction và transaction commit | Listener after-commit xử lý theo đăng ký |
| Event được phát trong transaction rồi transaction rollback | Không xử lý như một commit thành công |

Nếu hệ thống có thao tác ngoài tiến trình, kiểm tra cả tình huống retry và xử lý trùng theo cơ chế đã thiết kế. Đây là yêu cầu của luồng tích hợp, không phải bảo đảm sẵn có của annotation.

## 14. Chẩn đoán khi không thấy event

| Hiện tượng | Nguyên nhân cần xem xét | Hướng kiểm tra |
|---|---|---|
| Hành vi chạy nhưng listener không được gọi | Chưa qua điểm repository hỗ trợ phát event | Kiểm tra đường command và lời gọi `save` |
| Có `@DomainEvents` nhưng provider không chạy | Sai đối tượng, sai chữ ký hoặc đường ghi không có tích hợp | Kiểm tra annotation import, method không tham số và module store |
| Entity được cập nhật nhưng event không phát | Chỉ dựa vào dirty checking, SQL trực tiếp hoặc bulk query | Xác định API ghi thực tế |
| Provider trả event nhưng không có người nhận | Listener không được đăng ký hoặc không khớp kiểu payload | Kiểm tra bean listener và kiểu tham số |
| Listener after-commit không chạy | Không có transaction thích hợp hoặc transaction rollback | Kiểm tra ngữ cảnh và phase |
| Lưu lần hai lại thấy cùng event | Bộ đệm chưa được cleanup hoặc luồng trước gặp lỗi | Kiểm tra `@AfterDomainEventPublication` và trạng thái object |
| Event chứa ID rỗng | Payload tạo trước khi ID được cấp | Thiết kế ID và thời điểm chụp payload |
| Chỉ sai khi đổi store hoặc sang reactive | Đã suy rộng khả năng tích hợp của một module | Kiểm tra hỗ trợ và mô hình thực thi của store đích |
| Listener đọc sai trạng thái hoặc lỗi lazy loading | Event mang entity sống thay vì dữ kiện cần thiết | Dùng payload giá trị và snapshot phù hợp |

Đối với reactive repository, không suy rằng annotation sẽ tự mở rộng publisher hoặc giữ nguyên mọi đặc tính của ví dụ JPA đồng bộ. Cần kiểm tra tích hợp cụ thể của module và phiên bản đang dùng, cũng như thời điểm subscription và ngữ cảnh transaction. Commons cung cấp abstraction chung; mỗi store chỉ có những khả năng mà implementation của nó thực sự tích hợp.

## 15. Bài thực hành

Xây dựng command gửi đơn hàng với một store được lựa chọn rõ ràng:

1. Khai báo event bất biến chứa mã sự kiện, mã đơn hàng và thời điểm nghiệp vụ.
2. Để aggregate chỉ ghi nhận event sau khi kiểm tra hợp lệ.
3. Viết một provider `@DomainEvents` không tham số, trả collection snapshot.
4. Viết cleanup bằng `@AfterDomainEventPublication`.
5. Gọi repository theo đường command có transaction rõ ràng.
6. Quan sát khác biệt giữa listener thông thường và listener sau commit.
7. Thử rollback sau khi lưu và giải thích vì sao bộ đệm trong bộ nhớ không phải hàng đợi giao dịch bền vững.
8. Thử cập nhật bằng một đường ghi trực tiếp rồi giải thích vì sao không thể mặc định provider được gọi.

Điểm cần giải thích được là: **aggregate ghi nhận sự kiện → phương thức cung cấp trả các sự kiện đang chờ → repository được hỗ trợ công bố chúng → cleanup dọn bộ đệm**. Khả năng lưu dữ liệu, thời điểm commit và độ tin cậy khi chuyển sự kiện ra ngoài phải được thiết kế cùng với cơ chế đó.