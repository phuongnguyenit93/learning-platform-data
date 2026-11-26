# Phương thức repository có truyền aggregate để phát sự kiện

## 1. Aggregate tạo sự kiện, repository là một điểm kích hoạt publication

Trong chương **Sự kiện aggregate** của module **SPRING_DATA_COMMONS**, cần phân biệt ba hành động:

1. Aggregate ghi nhận một sự kiện khi thực hiện hành vi nghiệp vụ.
2. Một lời gọi repository phù hợp đưa aggregate đó qua cơ chế phát sự kiện.
3. Listener tiếp nhận sự kiện theo cấu hình của ứng dụng.

Ba hành động này không tự xảy ra đồng thời chỉ vì một field của entity đã đổi.

Ví dụ:

~~~java
order.approve(clock.instant());
orderRepository.save(order);
~~~

`approve(...)` có thể đăng ký một `OrderApproved` trong danh sách sự kiện đang chờ của `order`. Lời gọi `save(order)` qua Spring Data repository proxy là điểm để hạ tầng nhận aggregate, lấy các sự kiện và chuyển chúng cho cơ chế application event của Spring.

Nếu chỉ sửa entity trong bộ nhớ, hoặc ghi dữ liệu bằng một đường không đi qua cơ chế này, không nên mặc định sự kiện đã được phát.

Điểm quan trọng của bài là **aggregate được truyền vào lời gọi repository**, không chỉ một ID, một điều kiện truy vấn hay một giá trị trả về từ database.

## 2. Vì sao cần chính aggregate làm đối số?

Aggregate có thể giữ các sự kiện được tạo trong quá trình thực hiện nghiệp vụ:

~~~text
PurchaseOrder
├── id
├── status
└── pending events
    ├── OrderApproved(...)
    └── ...
~~~

Hạ tầng không thể suy ra toàn bộ danh sách này chỉ từ `orderId`.

ID giúp tìm dữ liệu trong store, nhưng không tự chứa:

- Những sự kiện vừa được aggregate đăng ký trong bộ nhớ.
- Giá trị nghiệp vụ đã được chụp lại trong từng sự kiện.
- Số sự kiện đang chờ publication.
- Thông tin nào cần được dọn sau publication.

Đó là lý do `save(order)` và `delete(order)` có ý nghĩa khác với các API chỉ nhận ID, dù kết quả dữ liệu cuối cùng có thể liên quan cùng một bản ghi.

### 2.1. Dữ liệu giống nhau chưa chắc mang cùng danh sách sự kiện

Giả sử `orderA` đã thực hiện `approve(...)` và đang giữ một sự kiện. Nếu code tự tạo một `orderB` có cùng ID và trạng thái, `orderB` không tự có sự kiện đang chờ của `orderA`.

~~~text
orderA: id = 501, status = APPROVED, events = [OrderApproved]
orderB: id = 501, status = APPROVED, events = []
~~~

Truyền `orderB` vào repository không có nghĩa hạ tầng sẽ tìm danh sách sự kiện nằm trên `orderA`.

Trong thiết kế thông thường, danh sách sự kiện chờ phát là trạng thái tạm thời của aggregate trong lần xử lý đó. Nó không phải một kho event được tự động khôi phục mỗi lần tải entity từ database.

## 3. Hợp đồng lấy và dọn sự kiện

Spring Data Commons cung cấp hai annotation liên quan:

| Thành phần | Vai trò |
| --- | --- |
| `@DomainEvents` | Đánh dấu phương thức không có đối số cung cấp sự kiện của aggregate |
| `@AfterDomainEventPublication` | Đánh dấu phương thức không có đối số được gọi để xử lý sau publication, thường để dọn danh sách sự kiện |
| `AbstractAggregateRoot<A>` | Lớp hỗ trợ đăng ký, cung cấp và dọn sự kiện theo hợp đồng này |

Aggregate có thể tự triển khai các phương thức annotation, hoặc dùng `AbstractAggregateRoot`. Không cần tự viết thêm một publisher trong mỗi phương thức nghiệp vụ chỉ để làm lại cùng luồng tự động.

Một đoạn minh họa cho cách tự triển khai, đặt bên trong aggregate:

~~~java
private final transient List<Object> pendingEvents =
        new ArrayList<>();

@DomainEvents
public Collection<Object> domainEvents() {
    return List.copyOf(pendingEvents);
}

@AfterDomainEventPublication
public void clearDomainEvents() {
    pendingEvents.clear();
}
~~~

Đoạn này sử dụng `List`, `ArrayList`, `Collection` từ `java.util` và hai annotation từ `org.springframework.data.domain`. Logic nghiệp vụ phải thêm sự kiện vào `pendingEvents`; annotation không tự phát hiện mọi thay đổi field để tạo event.

Đây là một lựa chọn thay thế cho việc kế thừa `AbstractAggregateRoot`, không phải yêu cầu khai báo thêm một bộ phương thức trùng chức năng khi đã sử dụng lớp hỗ trợ.

### 3.1. Không có sự kiện chờ thì không có sự kiện nghiệp vụ để phát

Gọi `save(order)` không tự tạo ra `OrderApproved`, `OrderChanged` hay một event chung cho mọi thay đổi.

Nếu aggregate không cung cấp sự kiện nào, repository vẫn có thể lưu dữ liệu bình thường. Publication dựa vào những sự kiện aggregate cung cấp, không phải một phép so sánh tự động giữa các cột trước và sau.

### 3.2. “Sau publication” khác “sau commit”

`@AfterDomainEventPublication` nói về vòng đời cung cấp và phát application event. Nó không có nghĩa:

- Transaction chắc chắn đã commit.
- Mọi listener bất đồng bộ đã hoàn tất.
- Một message broker đã lưu bền vững thông điệp.
- Mọi hệ thống bên ngoài đã xác nhận xử lý.

Không dùng callback này như một xác nhận giao thông điệp bền vững từ đầu đến cuối.

## 4. Phân biệt các lời gọi repository

Các API phổ biến cần nhận diện:

| Lời gọi | Đối số có chứa aggregate đang giữ event? | Cách hiểu về publication |
| --- | --- | --- |
| `save(order)` | Có, một aggregate | Là điểm phát sự kiện tiêu biểu của cơ chế aggregate events |
| `saveAll(orders)` | Có, tập aggregate | Hạ tầng có thể lấy sự kiện từ các aggregate được truyền vào |
| `delete(order)` | Có, một aggregate | Có aggregate để lấy sự kiện đã đăng ký trước lời gọi xóa |
| `deleteAll(orders)` | Có, tập aggregate | Có các aggregate để xử lý sự kiện tương ứng |
| `deleteById(id)` | Không, chỉ có ID | Không phải điểm phát sự kiện aggregate theo cùng hợp đồng |
| `deleteAllById(ids)` | Không, chỉ có các ID | Không thể thay cho việc truyền các aggregate đang giữ sự kiện |
| `deleteAll()` | Không có đối số aggregate | Không cung cấp các aggregate qua đối số để lấy sự kiện |
| `findById(id)` | Đối số là ID | Việc trả về entity không tự kích hoạt publication của các event đang chờ |
| Derived query theo trạng thái, tên hoặc điều kiện khác | Thường là điều kiện truy vấn | Không phải lời gọi phát sự kiện chỉ vì method thuộc repository |

Các method phải được gọi qua repository có tích hợp cơ chế aggregate events. Chỉ có một class Java mang tên `Repository` hoặc tự gọi implementation không đủ tạo ra tích hợp đó.

### 4.1. Chọn đúng overload

Hai lời gọi sau khác nhau về đầu vào:

~~~java
orderRepository.deleteAll(orders);
orderRepository.deleteAll();
~~~

Lời gọi thứ nhất nhận tập aggregate cụ thể. Lời gọi thứ hai không nhận tập aggregate từ caller.

Không suy từ tên method giống nhau rằng mọi overload đều cung cấp cùng dữ liệu cho cơ chế publication.

Với các API mở rộng của từng module, như `saveAndFlush(...)`, `deleteAllInBatch(...)` hoặc `deleteInBatch(...)` trong những phiên bản JPA có API tương ứng, cần kiểm tra đúng method, overload và khả năng tích hợp của phiên bản đang dùng.

Đặc biệt, overload batch nhận entity và overload không nhận entity không có cùng tiền đề. Việc một API batch có tích hợp aggregate events cũng không biến nó thành thao tác gọi đầy đủ mọi JPA entity lifecycle callback.

### 4.2. Có đối số aggregate chưa phải điều kiện đủ cho mọi method tùy biến

Một method tùy biến như:

~~~java
void approveAndStore(PurchaseOrder order);
~~~

không tự có hợp đồng publication chỉ vì nhận một aggregate.

Cần biết lời gọi đó có đi qua điểm tích hợp mà Spring Data nhận diện hay không, hoặc implementation có chủ động gọi repository/publisher phù hợp hay không.

Nguyên tắc thực hành là dùng một điểm lưu/phát rõ ràng, thay vì đặt tên tùy ý rồi suy rằng annotation trên aggregate sẽ khiến mọi method repository phát event.

## 5. Luồng xử lý khái quát

~~~mermaid
sequenceDiagram
    participant S as Application service
    participant A as Aggregate
    participant R as Repository proxy
    participant D as Store implementation
    participant P as Application event publisher
    S->>A: Thực hiện hành vi nghiệp vụ
    A->>A: Đăng ký event
    S->>R: save(aggregate)
    R->>D: Gọi phương thức lưu
    D-->>R: Trả về bình thường
    R->>A: Lấy domain events
    R->>P: Publish từng event
    R->>A: Xử lý sau publication
    R-->>S: Trả kết quả
~~~

Sơ đồ mô tả đường đi bình thường của publication, không mô tả vị trí commit cho mọi tổ hợp transaction và advisor.

Nếu phương thức lưu phát sinh lỗi trước khi hoàn tất lời gọi, không nên kỳ vọng luồng publication thành công như sơ đồ. Ngược lại, repository trả về bình thường tại một thời điểm cũng chưa tự chứng minh outer transaction về sau sẽ commit.

Để kiểm soát rõ phạm vi nghiệp vụ, ví dụ chính trong bài dùng một application service có `@Transactional` bao quanh lời gọi repository.

## 6. Ví dụ aggregate với AbstractAggregateRoot

Ví dụ sau dùng **Spring Data JPA**, Jakarta Persistence và Java hỗ trợ `record`. Mỗi public type được đặt trong một file riêng. Datasource, quét entity/repository, bean `Clock` và các cấu hình ứng dụng được cung cấp bởi dự án sử dụng ví dụ.

### 6.1. Payload sự kiện là dữ liệu của lần thay đổi

~~~java
import java.time.Instant;
import java.util.UUID;

public record OrderApproved(
        UUID eventId,
        UUID orderId,
        Instant occurredAt) {
}
~~~

~~~java
import java.time.Instant;
import java.util.UUID;

public record OrderDeletionRequested(
        UUID eventId,
        UUID orderId,
        Instant occurredAt) {
}
~~~

Payload giữ các giá trị ổn định tại lúc aggregate đăng ký sự kiện. Nó không giữ một tham chiếu entity mutable để listener tùy thời điểm đọc thấy một trạng thái khác.

`eventId` hỗ trợ nhận diện một event; bản thân field này chưa triển khai cơ chế chống xử lý trùng. `occurredAt` là thời điểm hành vi được ghi nhận trong ứng dụng, không phải timestamp commit do database xác nhận.

### 6.2. Aggregate đăng ký event sau khi kiểm tra quy tắc

~~~java
public enum OrderStatus {
    DRAFT,
    APPROVED
}
~~~

~~~java
import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

import org.springframework.data.domain.AbstractAggregateRoot;

@Entity
@Table(name = "purchase_order")
public class PurchaseOrder
        extends AbstractAggregateRoot<PurchaseOrder> {

    @Id
    private UUID id;

    @Version
    private Long version;

    @Enumerated(EnumType.STRING)
    private OrderStatus status;

    protected PurchaseOrder() {
    }

    private PurchaseOrder(UUID id) {
        this.id = Objects.requireNonNull(id, "id");
        this.status = OrderStatus.DRAFT;
    }

    public static PurchaseOrder draft(UUID id) {
        return new PurchaseOrder(id);
    }

    public UUID getId() {
        return id;
    }

    public void approve(Instant occurredAt) {
        Objects.requireNonNull(occurredAt, "occurredAt");

        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException(
                    "Only a draft order can be approved");
        }

        status = OrderStatus.APPROVED;

        registerEvent(new OrderApproved(
                UUID.randomUUID(),
                id,
                occurredAt));
    }

    public void requestDeletion(Instant occurredAt) {
        Objects.requireNonNull(occurredAt, "occurredAt");

        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException(
                    "Only a draft order can be deleted");
        }

        registerEvent(new OrderDeletionRequested(
                UUID.randomUUID(),
                id,
                occurredAt));
    }
}
~~~

`registerEvent(...)` đưa event vào danh sách của aggregate. Nó không tự gọi broker hay listener ngay tại dòng đó.

Trong ví dụ, ID được ứng dụng cung cấp trước khi ghi dữ liệu, nên event có thể chứa ID ngay khi được đăng ký. Nếu store sinh ID về sau, cần thiết kế thời điểm tạo payload để không vô tình giữ một ID chưa có giá trị.

`@Version` phục vụ kiểm soát cập nhật đồng thời. Nó không phải công tắc publication và cũng không thay danh sách event.

`requestDeletion(...)` ghi nhận một yêu cầu xóa hợp lệ theo quy tắc mẫu. Tên sự kiện không tuyên bố database chắc chắn đã xóa và commit thành công tại thời điểm phương thức đó chạy.

## 7. Application service truyền đúng aggregate vào save

Repository JPA minh họa:

~~~java
import java.util.UUID;

import org.springframework.data.jpa.repository.JpaRepository;

public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, UUID> {
}
~~~

Service bao quanh thao tác bằng transaction:

~~~java
import java.time.Clock;
import java.util.UUID;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PurchaseOrderService {

    private final PurchaseOrderRepository orders;
    private final Clock clock;

    public PurchaseOrderService(
            PurchaseOrderRepository orders,
            Clock clock) {

        this.orders = orders;
        this.clock = clock;
    }

    @Transactional
    public void approve(UUID orderId) {
        PurchaseOrder order = orders.findById(orderId)
                .orElseThrow(() -> new IllegalArgumentException(
                        "Order not found"));

        order.approve(clock.instant());
        orders.save(order);
    }

    @Transactional
    public void deleteDraft(UUID orderId) {
        PurchaseOrder order = orders.findById(orderId)
                .orElseThrow(() -> new IllegalArgumentException(
                        "Order not found"));

        order.requestDeletion(clock.instant());
        orders.delete(order);
    }
}
~~~

Ở cả hai method, object đã đăng ký event cũng là object được truyền cho repository.

Application service còn phải được tích hợp với kiểm tra quyền và các quy tắc nghiệp vụ đầy đủ của ứng dụng. Ví dụ tập trung vào ranh giới aggregate/repository; nó không phải một API đặt hàng hoàn chỉnh.

### 7.1. Tại sao vẫn gọi save khi entity đang managed?

Trong JPA, entity được tải trong transaction có thể được lưu thay đổi nhờ dirty checking mà không cần một lần gọi `save` bổ sung.

Nhưng hai yêu cầu sau khác nhau:

- Làm thay đổi của entity được persistence context ghi xuống database.
- Đi qua lời gọi repository có tích hợp publication của aggregate events.

Đoạn sau có thể làm trạng thái được ghi khi flush, nhưng thiếu điểm gọi repository để phát event đang chờ theo cơ chế đang xét:

~~~java
@Transactional
public void approveWithoutRepositoryPublication(UUID orderId) {
    PurchaseOrder order = orders.findById(orderId)
            .orElseThrow();

    order.approve(clock.instant());
    // Không có lời gọi repository save/delete tương ứng.
}
~~~

Không nên dùng kết quả “database đã có trạng thái APPROVED” làm bằng chứng rằng `OrderApproved` cũng đã được publish.

### 7.2. Không cần save lần nữa chỉ để nhận cùng event

Sau một vòng publication thành công và dọn event, gọi lại `save(order)` không nên được hiểu là tự phát lại sự kiện cũ.

Nếu nghiệp vụ có một thay đổi mới, aggregate đăng ký event mới. Nếu cần phát lại dữ liệu lịch sử để phục hồi hệ thống khác, phải có nguồn event bền vững và quy trình replay riêng.

## 8. deleteById không thay thế delete với aggregate

Đoạn sau không truyền aggregate đang giữ event:

~~~java
orders.deleteById(orderId);
~~~

Ngay cả khi một implementation cụ thể có thể tải entity trong quá trình xóa, caller không nên dựa vào chi tiết đó để suy ra cơ chế aggregate event sẽ nhận và phát các event mong muốn.

Một implementation khác có thể xóa bằng truy vấn trực tiếp mà không tạo aggregate instance tương ứng cho caller. Hợp đồng dùng ID không hứa cung cấp danh sách event của một aggregate đã thực hiện hành vi nghiệp vụ trước đó.

Nếu nghiệp vụ cần kiểm tra quy tắc xóa và phát event từ aggregate, luồng tường minh là:

~~~text
Tải aggregate
    → thực hiện hành vi yêu cầu xóa trên aggregate
    → aggregate đăng ký event
    → delete(aggregate) qua repository
~~~

Việc tải entity chỉ có ích nếu nó đi kèm hành vi và lời gọi phù hợp. Tải xong rồi tiếp tục gọi `deleteById(id)` vẫn không phải cách truyền object vừa giữ event vào điểm publication này.

### 8.1. Xóa không tự sinh một event nghiệp vụ

Nếu gọi `delete(order)` trên một aggregate có danh sách event rỗng, Spring Data không tự biết ứng dụng muốn một `OrderDeleted` với nội dung nào.

Aggregate hoặc một thành phần được thiết kế rõ phải tạo event phù hợp. Không nhầm cơ chế aggregate events với một hệ thống tự động ghi nhận mọi thay đổi dữ liệu hoặc mọi callback persistence.

## 9. saveAll và deleteAll với tập aggregate

Với thao tác nhiều aggregate, mỗi object cần tự giữ các event thuộc về nó:

~~~java
Instant occurredAt = clock.instant();

for (PurchaseOrder order : ordersToApprove) {
    order.approve(occurredAt);
}

orderRepository.saveAll(ordersToApprove);
~~~

`ordersToApprove` ở đây là một collection ổn định chứa các aggregate đã được tải và chọn cho thao tác. Khai báo `Instant` thuộc `java.time`.

Điểm cần kiểm soát:

- Truyền các aggregate đã đăng ký event, không truyền một tập object thay thế chỉ có cùng ID.
- Dùng collection có thể duyệt ổn định; tránh thiết kế phụ thuộc một iterable chỉ dùng được một lần.
- Không vô tình thêm cùng một aggregate instance nhiều lần rồi kỳ vọng framework tự suy ra số event nghiệp vụ mong muốn.
- Không suy thứ tự business toàn cục chỉ từ thứ tự collection và timestamp.
- Không mặc định `saveAll` đồng nghĩa một câu SQL duy nhất hoặc mọi callback được gom thành một lần.

Với xóa nhiều aggregate có sự kiện, nguyên tắc tương tự áp dụng cho `deleteAll(entities)` trong phạm vi hỗ trợ của repository.

### 9.1. Nhiều aggregate không tự trở thành một aggregate lớn hơn

Mỗi aggregate vẫn là một ranh giới nghiệp vụ. Việc truyền cả danh sách cho repository không tự thiết lập tính nhất quán nghiệp vụ giữa mọi object trong danh sách.

Tính nguyên tử của ghi dữ liệu phụ thuộc transaction, store và cấu hình. Publication cũng không tự tạo ra một giao dịch bền vững bao trùm database và mọi listener bên ngoài.

## 10. Đối số truyền vào khác kết quả trả về

Xét:

~~~java
PurchaseOrder saved = orders.save(order);
~~~

`order` là aggregate được truyền vào và đang giữ các event đã đăng ký. `saved` là kết quả của hợp đồng lưu, có thể cần dùng cho trạng thái persistence hoặc dữ liệu được store bổ sung.

Không nên thiết kế dựa trên giả định mọi store hoặc mọi đường lưu đều trả lại chính cùng một object reference. Chẳng hạn, một đường JPA liên quan merge có thể trả về instance managed khác instance đầu vào.

Điểm cần giữ là event được đăng ký trên aggregate đi vào điểm publication. Không chờ đến sau khi `save` trả về mới thêm event rồi cho rằng lời gọi đã kết thúc sẽ tự quay lại phát event mới đó.

Ví dụ sai về thời điểm:

~~~java
PurchaseOrder saved = orders.save(order);
saved.approve(clock.instant());
// Lời gọi save trước đó không tự phát event vừa đăng ký sau này.
~~~

Ngoài việc thiếu publication cho event mới, trạng thái persistence của `saved` còn phải được hiểu theo transaction và store cụ thể. Không dùng một lời gọi đã qua làm cơ chế lên lịch cho thay đổi tương lai.

## 11. Listener thường và listener gắn với transaction

### 11.1. EventListener

Một listener đơn giản có thể nhận event theo kiểu dữ liệu:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ApprovalTraceListener {

    @EventListener
    public void on(OrderApproved event) {
        System.out.println(
                "Approval observed for order " + event.orderId());
    }
}
~~~

Trong cấu hình event multicaster đồng bộ thông thường, listener được xử lý trên luồng publication. Tuy nhiên, cấu hình executor, listener bất đồng bộ và xử lý lỗi có thể thay đổi cách thực thi.

Với outer transaction của service trong ví dụ, một listener đồng bộ có thể quan sát event trước khi transaction đó commit. Nếu về sau transaction rollback, tác dụng phụ đã thực hiện bên ngoài database không tự được thu hồi.

### 11.2. TransactionalEventListener với AFTER_COMMIT

Khi cần chỉ xử lý sau khi transaction hiện hành commit thành công, có thể dùng listener theo phase:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class CommittedApprovalTraceListener {

    @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT)
    public void on(OrderApproved event) {
        System.out.println(
                "Committed approval for order " + event.orderId());
    }
}
~~~

Hai class listener trên minh họa hai thời điểm xử lý. Nếu cùng đăng ký cả hai, chúng là hai listener độc lập cùng nhận event theo điều kiện của từng listener.

`@TransactionalEventListener` mặc định không xử lý một event được publish khi không có transaction phù hợp, trừ khi cấu hình cho phép fallback. Vì vậy, vị trí mở transaction là một phần của thiết kế, không phải chi tiết có thể bỏ qua.

Listener sau commit không thể làm transaction đã commit quay lại rollback chỉ vì xử lý của nó thất bại. Nếu listener cần ghi thêm dữ liệu, phải thiết kế transaction phù hợp cho lần ghi đó; không coi transaction cũ là một lần commit mới sẵn có.

### 11.3. Bất đồng bộ không tự kế thừa transaction của publisher

Đưa listener sang xử lý bất đồng bộ không tự chuyển transaction hiện tại sang luồng khác. Cũng không nên mặc định thứ tự hoàn tất của các listener bằng thứ tự phát event.

Payload cần chứa đủ dữ liệu ổn định cho cách xử lý đã chọn. Tránh phụ thuộc một entity còn managed hoặc một ngữ cảnh request sẽ không còn tồn tại khi listener chạy.

## 12. Dọn event và xử lý lỗi

Việc dọn event giúp một aggregate instance không phát lại cùng danh sách ở mọi lần lưu kế tiếp.

Tuy nhiên, không nên suy từ đó một bảo đảm “chỉ xử lý đúng một lần”:

- Một listener có thể đã tạo tác dụng phụ trước khi listener khác lỗi.
- Một outer transaction có thể rollback sau khi event đã được publish trong process.
- Một listener bất đồng bộ có thể thất bại sau khi danh sách event trên aggregate đã được dọn.
- Một lần retry có thể tạo lại event cho cùng yêu cầu nghiệp vụ.

Khi publication gặp lỗi giữa chừng, không giả định mọi listener đều chưa chạy, mọi event đều đã được dọn hoặc có thể retry bằng cách dùng lại chính object cũ mà không xem xét trạng thái.

### 12.1. Không tạo vòng lưu lại chính aggregate trong listener

Nếu listener đồng bộ lại gọi `save` cho chính aggregate đang còn các event chờ được dọn, có thể xuất hiện publication lặp hoặc vòng xử lý đệ quy.

Nên thiết kế trách nhiệm của listener rõ ràng, giới hạn sự phụ thuộc quay lại publisher và dùng định danh/tính idempotent khi có chuỗi xử lý nhiều bước.

Không sửa tùy ý danh sách event đang được publication rồi dựa vào thứ tự nội bộ để điều phối nghiệp vụ.

### 12.2. Retry cần một hợp đồng riêng

Nếu một request được thực hiện lại, cần quyết định:

- Đó là một hành vi mới hay cùng một yêu cầu đã được tiếp nhận trước đó.
- Event ID có được giữ ổn định qua retry hay một event mới được tạo.
- Consumer nhận diện và xử lý trùng như thế nào.
- Trạng thái nào được tải lại sau lỗi transaction.

Danh sách event tạm thời trong aggregate không thay thế một cơ chế idempotency hoặc hàng đợi retry bền vững.

## 13. Những đường ghi không tự đi qua điểm publication này

| Đường thao tác | Vì sao cần kiểm tra riêng? |
| --- | --- |
| JPA dirty checking không có lời gọi repository phù hợp | Persistence có thể ghi field nhưng thiếu điểm interception để lấy event |
| `EntityManager.persist`, `merge` hoặc `remove` trực tiếp | Không phải lời gọi qua Spring Data repository proxy đang xét |
| JPQL bulk update hoặc native SQL | Thường không có aggregate đang giữ event đi qua lời gọi |
| Derived delete query theo điều kiện | Không nên suy rằng nó có cùng hợp đồng với `delete(aggregate)` |
| Custom repository fragment | Việc tích hợp phụ thuộc đường gọi và implementation thực tế |
| Gọi method nội bộ trong implementation | Không tự đồng nghĩa đi qua lại proxy và các interceptor cần thiết |
| Thay đổi một entity con riêng lẻ | Cần kiểm tra aggregate root nào cung cấp event và root nào được truyền vào repository |
| Script database hoặc ứng dụng khác | Không chạy logic đăng ký event trong aggregate của ứng dụng này |

Nếu một phương thức implementation tự gọi một method nội bộ khác, không dùng sự giống nhau về tên với `save` làm bằng chứng rằng proxy đã chạy lại cơ chế publication.

Với repository tùy biến, cần kiểm chứng luồng thực tế thay vì chỉ đọc chữ ký method.

## 14. Aggregate con, dữ liệu truy vấn và projection

Một object con có field thay đổi không tự làm event xuất hiện trên aggregate root. Domain model phải xác định hành vi nào đăng ký event và danh sách sự kiện nằm ở đâu.

Nếu thiết kế aggregate yêu cầu mọi thay đổi dòng hàng đi qua đơn hàng, có thể để root thực hiện hành vi và đăng ký event. Sau đó truyền root vào repository tương ứng.

Ngược lại, trả về một projection hoặc DTO từ một query không tạo ra một aggregate có khả năng publication:

~~~text
findById(...) → aggregate để thực hiện hành vi
query projection → dữ liệu phục vụ đọc
~~~

Derived query, phân trang, sắp xếp hoặc Query by Example giúp lấy dữ liệu theo nhu cầu. Chúng không tự đăng ký sự kiện nghiệp vụ, và kết quả đọc không thay thế một lời gọi lưu/xóa phù hợp cho aggregate đang giữ event.

## 15. Giới hạn theo module và kiểu thực thi

Spring Data Commons cung cấp abstraction, nhưng khả năng tích hợp phụ thuộc repository và module cụ thể.

Ví dụ JPA trong bài không cho phép suy ra mọi repository reactive, mọi custom repository hoặc mọi store đều có cùng thời điểm publication.

Đặc biệt, không lấy kết luận từ một method đồng bộ rồi áp nguyên sang method trả `Mono`, `Flux` hoặc một kiểu trì hoãn thực thi. “Method đã trả về publisher” và “pipeline đã lưu dữ liệu thành công” là hai mốc khác nhau.

Khi dùng một module khác, cần xác nhận:

1. Repository có tích hợp aggregate events theo cơ chế đang xét không.
2. Những method và overload nào được hỗ trợ.
3. Điểm publication nằm ở đâu so với thực thi lưu dữ liệu.
4. Transaction và listener theo phase có tương thích với mô hình thực thi không.
5. Có đường ghi nào bỏ qua điểm tích hợp đó không.

Không cần đưa thêm một annotation bất kỳ lên aggregate rồi coi các khác biệt này đã được giải quyết.

## 16. Aggregate events không tự là thông điệp bền vững

`AbstractAggregateRoot` và các annotation publication hỗ trợ phát application event trong ứng dụng. Chúng không tự lưu event vào một event store hay một message broker.

Nếu ứng dụng cần bảo đảm một thay đổi đã commit cuối cùng sẽ được hệ thống khác nhận, cần thiết kế thêm cơ chế bền vững.

Một hướng thường dùng là transactional outbox:

~~~text
Local transaction:
    cập nhật aggregate + ghi outbox

Worker phát thông điệp:
    đọc outbox → gửi → ghi nhận tiến độ / retry
~~~

Bản ghi outbox phải được tạo trong cùng transaction phù hợp với cập nhật chính nếu muốn giữ tính nguyên tử tại database đó.

Chỉ dùng một listener `AFTER_COMMIT` để gửi mạng không tự loại bỏ khoảng trống khi tiến trình dừng sau commit nhưng trước khi gửi thành công.

Outbox cũng cần xử lý trùng, retry và thứ tự theo hợp đồng. Nó là phần bổ sung về độ bền và giao nhận, khác với câu hỏi repository có nhận aggregate để lấy event hay không.

## 17. Kiểm chứng hành vi bằng các tình huống cụ thể

Các tình huống dưới đây là định hướng kiểm thử, không phải báo cáo đã chạy kiểm thử cho một phiên bản Spring Data cụ thể:

| Tình huống | Điều cần quan sát |
| --- | --- |
| Aggregate đăng ký một event rồi gọi `save(aggregate)` | Listener tương ứng nhận event theo cấu hình |
| `save` một aggregate không có event | Không tự phát sinh một event nghiệp vụ giả định |
| Gọi `save` lại sau publication và cleanup thành công | Event cũ không xuất hiện lại chỉ vì cùng object được lưu |
| Nhiều aggregate có event rồi gọi `saveAll` | Nhận đủ event theo hợp đồng, payload gắn đúng aggregate |
| Đăng ký event rồi gọi `delete(aggregate)` | Xác nhận publication và kết quả dữ liệu theo transaction |
| Gọi `deleteById` | Không dựa vào lời gọi này để nhận event từ aggregate |
| Chỉ đổi managed entity và để dirty checking ghi | Phân biệt dữ liệu được ghi với event được publication |
| Repository hoặc flush phát sinh lỗi | Quan sát transaction và tránh khẳng định tác dụng phụ chưa từng xảy ra |
| Outer transaction rollback | Listener sau commit không xử lý như một commit thành công |
| Event được phát ngoài transaction | Kiểm tra điều kiện chạy của transactional listener và fallback |
| API mở rộng hoặc custom method | Kiểm chứng đúng method, overload và phiên bản |

Một unit test chỉ gọi `order.approve(...)` có thể chứng minh aggregate đăng ký đúng payload. Nó chưa chứng minh repository proxy thực sự lấy event, listener được đăng ký hoặc transaction chạy đúng phase.

Đối với tích hợp publication, cần gọi bean repository thực tế trong môi trường kiểm thử phù hợp. Đối với `AFTER_COMMIT`, kiểm thử phải thực sự đi đến một lần commit; transaction test luôn rollback không tự chứng minh đường xử lý sau commit.

## 18. Tự kiểm tra kiến thức

**Tại sao `deleteById` không tương đương `delete(aggregate)` đối với aggregate events?**

Vì lời gọi bằng ID không cung cấp aggregate đang giữ danh sách sự kiện. Không nên phụ thuộc implementation có tải entity nội bộ hay không.

**Chỉ có `@DomainEvents` là đủ để mọi thay đổi field phát event không?**

Không. Aggregate phải cung cấp event đã đăng ký và cần đi qua điểm publication phù hợp.

**Vì sao một managed entity có thể được lưu mà listener không nhận event?**

Dirty checking có thể ghi trạng thái mà không có lời gọi repository dùng để lấy danh sách event đang chờ.

**Một custom method nhận aggregate có tự được hỗ trợ không?**

Không tự động suy ra như vậy. Cần xác định điểm tích hợp và đường gọi thực tế của method đó.

**Dọn event sau publication có nghĩa transaction đã commit không?**

Không. Cleanup, publication và commit là các mốc khác nhau.

**`AFTER_COMMIT` có tự bảo đảm event được giao bền vững tới hệ thống ngoài không?**

Không. Cần cơ chế lưu và giao nhận bền vững nếu đó là yêu cầu của ứng dụng.

**Điều gì cần giữ khi mở rộng repository hoặc đổi store?**

Xác định aggregate nào giữ event, method nào thực sự nhận aggregate đó và điểm tích hợp nào thực hiện publication; sau đó kiểm chứng transaction, listener và khả năng hỗ trợ của module đang dùng.
