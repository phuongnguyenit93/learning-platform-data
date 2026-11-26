# Vì sao deleteById không có cùng điều kiện phát sự kiện?

## Mục tiêu và phạm vi

Trong Spring Data Commons, sự kiện aggregate được lấy từ chính aggregate root thông qua phương thức đánh dấu `@DomainEvents`. Hạ tầng repository có hỗ trợ cơ chế này cần một aggregate instance để gọi phương thức đó.

`deleteById(id)` chỉ nhận một định danh. Hợp đồng của phương thức không yêu cầu implementation phải tải aggregate và không cung cấp aggregate đang giữ các sự kiện chờ phát cho bên gọi. Vì thế, không thể xem `deleteById(id)` là điểm phát aggregate events tương đương với `delete(aggregate)`.

Sự khác biệt nằm ở điều kiện đầu vào và đường tích hợp, không nằm ở việc ID có hợp lệ hay câu lệnh xóa có thực thi thành công.

Bài học giúp bạn:

- Giải thích mối liên hệ giữa aggregate instance, bộ đệm sự kiện và repository.
- Phân biệt hợp đồng của `deleteById` với chi tiết implementation của từng store.
- Thiết kế một luồng xóa có kiểm tra nghiệp vụ và cung cấp domain event.
- Nhận biết giới hạn liên quan đến transaction, bulk delete, callback JPA và độ tin cậy khi gửi sự kiện ra ngoài.

Các ví dụ cụ thể sử dụng Spring Data JPA đồng bộ. Annotation sự kiện thuộc Commons, còn mapping, khóa và transaction trong ví dụ thuộc JPA. Khi áp dụng cho store khác, phải xác minh khả năng tích hợp của module đó.

## 1. Điều kiện để aggregate events được công bố

Một aggregate có thể tự ghi nhận sự kiện trong bộ nhớ sau khi thực hiện hành vi nghiệp vụ:

```text
aggregate kiểm tra điều kiện
    -> chấp nhận thay đổi nghiệp vụ
    -> thêm event object vào bộ đệm
    -> ứng dụng gọi repository qua đường được hỗ trợ
    -> hạ tầng đọc @DomainEvents trên aggregate
    -> Spring công bố các application event
    -> hạ tầng gọi cleanup
```

Một cấu trúc thường gặp:

```java
@DomainEvents
public Collection<Object> domainEvents() {
    return List.copyOf(pendingEvents);
}

@AfterDomainEventPublication
public void clearDomainEvents() {
    pendingEvents.clear();
}
```

Hai annotation này thuộc package `org.springframework.data.domain`.

Có ba điều kiện khác nhau:

| Điều kiện | Ý nghĩa |
|---|---|
| Có aggregate instance | Có đối tượng để gọi phương thức cung cấp sự kiện |
| Aggregate có sự kiện đang chờ | Provider trả về event object thay vì collection rỗng |
| Đi qua điểm repository được hỗ trợ | Hạ tầng có cơ hội đọc và công bố các sự kiện |

Chỉ có aggregate instance là chưa đủ. Gọi `delete(entity)` trên một entity không có sự kiện đang chờ không tự sinh ra một event nghiệp vụ như `OrderDeleted`.

Ngược lại, aggregate đã giữ sự kiện nhưng ứng dụng ghi dữ liệu bằng một API không tham gia cơ chế repository này thì sự kiện cũng không tự được công bố.

## 2. deleteById chỉ cung cấp định danh

Xét hai lời gọi:

```java
repository.deleteById(orderId);
repository.delete(order);
```

Ở lời gọi thứ nhất, đối số là một ID, ví dụ `UUID`. Ở lời gọi thứ hai, đối số là aggregate có thể đang chứa metadata, trạng thái nghiệp vụ và bộ đệm sự kiện.

| Khía cạnh | `deleteById(id)` | `delete(aggregate)` |
|---|---|---|
| Dữ liệu bên gọi cung cấp | Định danh | Aggregate instance |
| Bộ đệm sự kiện trên đối số | Không có bộ đệm của aggregate | Có thể có |
| Bắt buộc tải aggregate theo hợp đồng API | Không | Bên gọi đã cung cấp một instance |
| Có thể đọc provider trên aggregate đầu vào | Không dựa vào ID để làm việc này | Có điều kiện đầu vào phù hợp |
| Tự tạo event nghiệp vụ | Không | Không |
| Bảo đảm transaction đã commit khi công bố event | Không | Không |

Một store có thể triển khai xóa theo ID bằng câu lệnh tương đương:

```sql
DELETE FROM purchase_order WHERE id = ?;
```

Lệnh này không cần tạo object `PurchaseOrder` trong bộ nhớ. Không có object thì cũng không có phương thức `@DomainEvents` của object đó để đọc.

Ngay cả khi ID xác định duy nhất một hàng, nó vẫn chỉ cho biết danh tính, không chứa:

- Các sự kiện mà aggregate đã ghi nhận trong phiên xử lý hiện tại.
- Các dữ kiện trước khi xóa, trừ khi được đọc thêm.
- Kết quả kiểm tra quy tắc nghiệp vụ trên aggregate.
- Lý do xóa và tác nhân thực hiện nếu ứng dụng chưa cung cấp.

Commons không tự dựng một aggregate từ ID rồi đoán những sự kiện cần phát.

## 3. Tải entity bên trong implementation không thay đổi hợp đồng

Một implementation có thể tải entity trước khi xóa vì nhu cầu của store hoặc ORM. Ví dụ khái niệm:

```text
deleteById(id)
    -> tìm entity theo id
    -> thực hiện xóa bằng cơ chế của store
```

Điều này vẫn không làm `deleteById` có cùng điều kiện phát aggregate events với lời gọi `delete(aggregate)` từ ứng dụng.

### 3.1. Object được tải không phải bộ đệm sự kiện của bên gọi

Giả sử một aggregate đã được tải ở nơi khác và đã ghi nhận event trong một danh sách transient. Việc đọc một entity từ database không khôi phục danh sách event đó, vì danh sách không được lưu như trạng thái persistent thông thường.

Một object vừa được materialize có thể có bộ đệm rỗng. Có dữ liệu nghiệp vụ trong entity không đồng nghĩa có event đang chờ.

### 3.2. Đường gọi công khai vẫn là deleteById

Cơ chế phát aggregate events được nối vào những điểm repository được hỗ trợ. Không được suy ra rằng mọi lời gọi nội bộ của implementation sẽ đi lại qua đúng lớp proxy/interceptor như lời gọi từ ứng dụng.

Nếu một implementation gọi một hàm `delete` nội bộ, đó có thể là self-invocation trên target. Không thể dùng tên hàm nội bộ làm bằng chứng rằng interceptor phát aggregate events đã chạy.

### 3.3. Chi tiết implementation có thể khác giữa các store

Một store có thể đọc entity để xóa; một store khác có thể xóa trực tiếp bằng ID. Một phiên bản implementation cũng có thể thay đổi chiến lược thực hiện.

Đó là lý do thiết kế ở mức Commons phải dựa trên hợp đồng API và khả năng tích hợp được hỗ trợ, thay vì dựa vào giả định rằng “tôi thấy một lần SELECT trước DELETE nên event chắc chắn được phát”.

Nếu ứng dụng tự tùy biến một API xóa theo ID để tải aggregate, thực hiện hành vi và công bố sự kiện, đó là hợp đồng do ứng dụng xây dựng. Nó không phải bảo đảm mặc định của `deleteById`.

## 4. Mẫu dễ sai: chuẩn bị event rồi vẫn gọi deleteById

Xét luồng sau:

```java
PurchaseOrder order = repository.findById(orderId).orElseThrow();

order.approveDeletion(actorId, clock.instant());

repository.deleteById(orderId);
```

Vấn đề không phải aggregate chưa được tải. Aggregate đã được tải và có thể đang giữ event, nhưng lời gọi xóa chỉ truyền ID.

Hạ tầng không có trách nhiệm tìm khắp persistence context, cache hay các biến local để phát hiện object nào đang giữ sự kiện tương ứng với ID đó.

Luồng phù hợp hơn với cơ chế aggregate events:

```java
PurchaseOrder order = repository.findById(orderId).orElseThrow();

order.approveDeletion(actorId, clock.instant());

repository.delete(order);
```

Sự thay đổi quan trọng là truyền chính aggregate đã thực hiện hành vi vào đường repository được hỗ trợ.

Cũng không nên tạo một object chỉ có ID rồi coi đó là bản thay thế tương đương cho việc tải aggregate. Một object như vậy không có đủ trạng thái để kiểm tra quy tắc nghiệp vụ hoặc chụp các dữ kiện cần thiết trước khi xóa.

## 5. Ví dụ: chỉ đơn hàng nháp mới được phép xóa

Giả sử hệ thống cho phép xóa vật lý đơn hàng ở trạng thái `DRAFT`. Đơn hàng đã `CONFIRMED` phải đi qua một quy trình nghiệp vụ khác.

Sự kiện `OrderDeletionApproved` mô tả việc aggregate chấp nhận xóa theo quy tắc. Tên này không khẳng định rằng transaction database đã commit ngay tại lúc event được tạo.

### 5.1. Payload sự kiện

```java
import java.time.Instant;
import java.util.UUID;

public record OrderDeletionApproved(
        UUID eventId,
        UUID orderId,
        String customerId,
        String actorId,
        Instant occurredAt
) {
}
```

Payload mang những giá trị cần dùng sau khi xóa. Listener không phải tải lại một đơn hàng đã không còn trong database để biết `customerId`.

Không đưa cả entity vào payload để bên nhận tùy ý truy cập về sau. Một entity đã bị xóa hoặc tách khỏi persistence context không phải nguồn dữ liệu ổn định cho listener.

### 5.2. Aggregate kiểm tra quy tắc và ghi nhận event

Mỗi kiểu public trong các ví dụ được hiểu là một đơn vị mã nguồn riêng trong ứng dụng.

```java
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
        DRAFT, CONFIRMED
    }

    @Id
    private UUID id;

    @Version
    private Long version;

    private String customerId;

    @Enumerated(EnumType.STRING)
    private Status status;

    @Transient
    private boolean deletionApproved;

    @Transient
    private final List<Object> pendingEvents = new ArrayList<>();

    protected PurchaseOrder() {
    }

    public PurchaseOrder(String customerId) {
        if (customerId == null || customerId.isBlank()) {
            throw new IllegalArgumentException("Customer is required");
        }

        this.id = UUID.randomUUID();
        this.customerId = customerId;
        this.status = Status.DRAFT;
    }

    public void approveDeletion(String actorId, Instant occurredAt) {
        if (actorId == null || actorId.isBlank()) {
            throw new IllegalArgumentException("Actor is required");
        }

        Objects.requireNonNull(occurredAt, "occurredAt");

        if (status != Status.DRAFT) {
            throw new IllegalStateException(
                    "Only a draft order can be deleted"
            );
        }

        if (deletionApproved) {
            throw new IllegalStateException(
                    "Deletion has already been approved on this instance"
            );
        }

        deletionApproved = true;

        pendingEvents.add(new OrderDeletionApproved(
                UUID.randomUUID(),
                id,
                customerId,
                actorId,
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

Các lựa chọn trong ví dụ có ý nghĩa cụ thể:

- Kiểm tra nghiệp vụ diễn ra trước khi thêm sự kiện.
- `pendingEvents` không được JPA persist vì có `jakarta.persistence.Transient`.
- `deletionApproved` chỉ ngăn việc phê duyệt lặp trên cùng instance; nó không phải cơ chế chống xử lý trùng được lưu bền.
- Provider trả snapshot và không tự tạo event mới trong mỗi lần đọc.
- Cleanup dọn bộ đệm sau bước công bố của hạ tầng.
- UUID được cấp trước, nên payload có ID ổn định.
- `@Version Long` thuộc lựa chọn mapping và quản lý phiên bản của JPA, không phải điều kiện của annotation sự kiện.

Khi chuyển sang MongoDB, JDBC hoặc store khác, dùng mapping và cơ chế loại trừ thuộc tính phù hợp. Không mặc định annotation JPA có cùng hiệu lực với mọi store.

## 6. Service tải aggregate rồi gọi delete(aggregate)

Ví dụ JPA sau chọn khóa ghi khi tải để làm rõ chính sách xử lý cạnh tranh trong luồng kiểm tra rồi xóa.

```java
import java.util.Optional;
import java.util.UUID;

import jakarta.persistence.LockModeType;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface OrderRepository
        extends JpaRepository<PurchaseOrder, UUID> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select o from PurchaseOrder o where o.id = :id")
    Optional<PurchaseOrder> findForDeletion(@Param("id") UUID id);
}
```

Khóa JPA trong ví dụ là một lựa chọn về tính nhất quán khi truy cập dữ liệu, không phải yêu cầu để `@DomainEvents` hoạt động. Khả năng và hành vi khóa cần phù hợp với database đang dùng.

Application service:

```java
import java.time.Clock;
import java.util.Optional;
import java.util.UUID;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderDeletionService {

    private final OrderRepository repository;
    private final Clock clock;

    public OrderDeletionService(
            OrderRepository repository,
            Clock clock
    ) {
        this.repository = repository;
        this.clock = clock;
    }

    @Transactional
    public boolean deleteDraftOrder(UUID orderId, String actorId) {
        Optional<PurchaseOrder> candidate =
                repository.findForDeletion(orderId);

        if (candidate.isEmpty()) {
            return false;
        }

        PurchaseOrder order = candidate.get();

        order.approveDeletion(actorId, clock.instant());

        repository.delete(order);

        return true;
    }
}
```

Ứng dụng cần cung cấp bean `Clock`, chẳng hạn `Clock.systemUTC()`, cùng cấu hình JPA và schema tương ứng. `actorId` phải lấy từ nguồn danh tính có thẩm quyền của ứng dụng; không dùng tùy ý giá trị do client khai báo.

Luồng thực thi có các bước rõ ràng:

1. Tìm đơn hàng trong transaction.
2. Nếu không có, trả `false` và không tạo event phê duyệt xóa.
3. Aggregate kiểm tra trạng thái và ghi nhận event.
4. Truyền chính aggregate đó vào `repository.delete(order)`.
5. Hạ tầng repository được hỗ trợ đọc các sự kiện đang chờ.
6. Transaction hoàn tất theo kết quả xử lý.

Không cần `save(order)` chỉ để “mồi” việc phát event trước khi gọi xóa. Nếu làm vậy, event có thể được công bố ở điểm save trước khi lệnh delete được thực hiện, gây nhầm ý nghĩa thời điểm.

Khi JPA đánh dấu entity là removed, object Java vẫn có thể tồn tại trong bộ nhớ để provider trả payload đã chuẩn bị. Điều này không đòi hỏi đọc lại entity từ database sau khi xóa.

## 7. delete(aggregate) vẫn không phải bảo đảm đã xóa một hàng

Điểm nối phát aggregate events không phải một cơ chế theo dõi số hàng bị xóa ở database.

Có aggregate instance và lời gọi repository hoàn tất bình thường chưa đủ để kết luận rằng:

- Một hàng có tồn tại ngay trước thao tác.
- Chính xác một hàng vừa bị xóa.
- Mọi ràng buộc database đã được kiểm tra xong tại thời điểm phát event.
- Transaction bao ngoài chắc chắn sẽ commit.

Một implementation có thể trì hoãn SQL đến khi flush. Một thao tác cũng có thể không tạo thay đổi dữ liệu theo semantics của store.

Vì vậy, không làm theo cách sau:

```text
Tạo object chỉ có ID
    -> thêm một event khẳng định đã xóa
    -> gọi delete(object)
    -> coi event là bằng chứng hàng đã bị xóa và commit
```

Thiết kế mẫu trong bài tải aggregate thật để kiểm tra quy tắc trước khi xóa. Tuy vậy, event vẫn cần được diễn giải cùng transaction; nó không thay thế việc xử lý lỗi khi flush hoặc commit.

Nếu nghiệp vụ yêu cầu số hàng ảnh hưởng làm một phần kết quả, cần chọn một API phù hợp với store hoặc xây dựng thao tác có hợp đồng kết quả rõ ràng. Đừng suy số hàng ảnh hưởng từ việc listener được gọi.

## 8. Phân biệt aggregate events với callback JPA và trigger database

Các cơ chế dưới đây có thể cùng xuất hiện trong một ứng dụng nhưng có điểm kích hoạt khác nhau:

| Cơ chế | Điểm tích hợp | Nội dung chính |
|---|---|---|
| `@DomainEvents` | Hạ tầng repository có hỗ trợ | Event do aggregate đã ghi nhận |
| `@PreRemove`, `@PostRemove` | Vòng đời entity của JPA provider | Callback liên quan thao tác remove entity |
| Trigger database | Thực thi thay đổi tại database theo cấu hình | Logic gắn với thao tác dữ liệu |
| Listener ứng dụng tự viết | Điểm gọi do ứng dụng thiết kế | Hợp đồng do ứng dụng quy định |

Một implementation `deleteById` có thể tải entity và đi qua callback JPA. Điều đó không tự nối callback JPA với provider `@DomainEvents`.

Tương tự:

- `@PostRemove` không phải cam kết rằng transaction đã commit.
- Xóa bằng bulk JPQL có thể bỏ qua lifecycle callback của từng entity.
- Cascade remove không tự biến mọi object con thành aggregate root được repository đọc domain events.
- Trigger database không tự tạo application event trong Spring nếu không có một cầu nối được triển khai.

Khi điều tra hiện tượng “callback chạy nhưng listener event không chạy”, trước hết phải xác định đang nói đến cơ chế nào.

## 9. Xóa hàng loạt và truy vấn xóa chuyên biệt

Tên phương thức bắt đầu bằng “delete” không tạo ra một hợp đồng aggregate events chung cho mọi API.

| Đường xóa | Đầu vào | Điều cần hiểu |
|---|---|---|
| `delete(aggregate)` | Một aggregate | Có instance để đọc event khi tích hợp được hỗ trợ |
| `deleteAll(aggregates)` | Các aggregate | Có các instance; cần hiểu hỗ trợ và semantics của module |
| `deleteById(id)` | Một ID | Không dựa vào nó để lấy event của aggregate |
| `deleteAllById(ids)` | Các ID | Danh sách ID không phải danh sách aggregate có bộ đệm |
| `deleteAll()` không đối số | Không cung cấp instance | Không mặc định hạ tầng sẽ tải mọi aggregate để phát event |
| Bulk query hoặc SQL trực tiếp | Điều kiện truy vấn | Không tự đọc provider của từng aggregate |

Ở Spring Data JPA còn có các API batch riêng. Phải phân biệt overload nhận entity với API chỉ nhận ID, và kiểm tra method nào có tích hợp aggregate events trong bộ phiên bản dùng thực tế.

Một thao tác batch nhận các aggregate có thể cho hạ tầng repository những object để đọc event, trong khi câu SQL bulk bên dưới vẫn không chạy callback JPA cho từng entity. Đây là hai lớp xử lý độc lập.

Nếu cần kiểm tra quy tắc nghiệp vụ và event riêng cho từng đối tượng, hãy cân nhắc:

- Tải các aggregate cần xử lý theo lô có kích thước kiểm soát.
- Thực hiện hành vi hợp lệ trên từng aggregate.
- Dùng đường repository hỗ trợ và transaction phù hợp.
- Thiết kế bộ nhớ, khóa và cách xử lý khi một đối tượng trong lô thất bại.

Nếu mục tiêu là dọn dữ liệu kỹ thuật theo một điều kiện lớn và không cần domain event cho từng hàng, một bulk delete có hợp đồng riêng có thể phù hợp hơn. Đừng gắn một event tổng hợp với ý nghĩa “mọi aggregate đã chấp nhận xóa” khi chưa thực sự kiểm tra từng aggregate.

## 10. Thời điểm phát event và thời điểm commit

Với transaction bao quanh service, event có thể được công bố trong khi transaction vẫn còn mở:

```text
Bắt đầu transaction
    -> tải aggregate
    -> chấp nhận xóa và ghi nhận event
    -> repository.delete(aggregate)
    -> công bố application event
    -> tiếp tục xử lý
    -> flush/commit hoặc rollback
```

Sơ đồ thể hiện quan hệ khái quát. Thứ tự flush chi tiết phụ thuộc store và implementation.

Một listener thông thường có thể đã quan sát event trước commit. Nếu sau đó transaction rollback vì ràng buộc dữ liệu, listener đã gọi HTTP hoặc gửi email thì tác dụng phụ đó không tự biến mất.

Nếu chỉ muốn xử lý sau khi transaction commit, dùng listener theo transaction:

```java
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class OrderDeletionObserver {

    private static final System.Logger LOG =
            System.getLogger(OrderDeletionObserver.class.getName());

    @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT
    )
    public void on(OrderDeletionApproved event) {
        LOG.log(
                System.Logger.Level.INFO,
                "Deletion transaction committed for order "
                        + event.orderId()
        );
    }
}
```

Điều kiện cần nhớ:

- Event phải được phát trong ngữ cảnh transaction thích hợp để đăng ký listener theo phase.
- Mặc định, listener theo transaction không xử lý event khi không có transaction.
- `AFTER_COMMIT` không làm việc gửi message bên ngoài trở thành nguyên tử với thao tác delete.
- Lỗi xảy ra sau commit không thể hoàn tác transaction đã hoàn tất.

`@AfterDomainEventPublication` chỉ dọn bộ đệm sau bước công bố của hạ tầng repository. Nó không phải callback after-commit và không phải xác nhận từ broker.

Nếu cleanup đã chạy rồi transaction rollback, bộ đệm trong object có thể đã rỗng. Không nên giả định có thể giữ nguyên instance đó và retry như chưa từng có gì xảy ra.

## 11. Không tìm thấy dữ liệu và yêu cầu xóa lặp

Cần xác định ý nghĩa nghiệp vụ khi không có aggregate tương ứng với ID.

Ví dụ service trong bài chọn:

```text
Không tìm thấy đơn hàng
    -> trả false
    -> không có aggregate để kiểm tra quy tắc
    -> không phát OrderDeletionApproved
```

Đây là chính sách của application service, không phải một quy tắc rằng mọi hệ thống phải báo lỗi khi xóa lại một tài nguyên đã vắng mặt.

Nếu API chọn hành vi idempotent, lần xóa tiếp theo có thể vẫn được xem là hoàn tất theo hợp đồng API. Tuy nhiên, “yêu cầu xóa đã được tiếp nhận” khác với “một aggregate hiện hữu vừa được xóa”.

Phân biệt các loại thông tin:

| Thông tin cần ghi nhận | Nguồn thích hợp |
|---|---|
| Người dùng gửi yêu cầu xóa một ID | Application service hoặc cơ chế ghi nhận request |
| Aggregate hiện hữu chấp nhận xóa | Hành vi trên aggregate đã được tải |
| Transaction chứa thao tác xóa đã commit | Xử lý gắn với transaction hoặc cơ chế lưu bền phù hợp |
| Consumer bên ngoài xử lý xong message | Giao thức và trạng thái của luồng tích hợp |

Không phát thêm sự kiện “aggregate vừa bị xóa” chỉ để mỗi request xóa lặp đều có một event cùng tên.

Nếu cần chống xử lý trùng, `eventId` có thể là một phần dữ liệu hỗ trợ, nhưng cần thêm chính sách lưu trạng thái và nhận diện lần xử lý. Tạo UUID mới cho mỗi lần retry không tự nhận diện được rằng hai lần đó thuộc cùng một yêu cầu nghiệp vụ.

## 12. Khi cần chuyển sự kiện ra ngoài tiến trình

Một rủi ro của luồng xóa là dữ liệu gốc đã biến mất, trong khi thông báo ra bên ngoài vẫn cần được gửi hoặc gửi lại.

Nếu chỉ giữ payload trong bộ nhớ rồi gửi sau commit, tiến trình có thể dừng giữa commit và lần gửi. Application event không tự khôi phục phần việc còn thiếu.

Một thiết kế có thể dùng transactional outbox:

```text
Cùng một transaction database
    -> kiểm tra aggregate
    -> xóa aggregate
    -> lưu payload outbox
    -> commit

Bộ phát riêng
    -> đọc outbox
    -> gửi message
    -> quản lý retry và trạng thái xử lý
```

Điểm quan trọng là bản ghi outbox được lưu trong cùng transaction với việc xóa. Nếu chờ đến `AFTER_COMMIT` mới bắt đầu lưu outbox, hai việc đó không còn nguyên tử trong transaction đã kết thúc.

Payload outbox cần chứa đủ dữ kiện để xử lý khi aggregate không còn tồn tại. Cũng cần thiết kế vòng đời và quan hệ dữ liệu để outbox không bị xóa cascade cùng aggregate.

Đây là một cơ chế bổ sung phải triển khai rõ ràng. `@DomainEvents` không tự tạo outbox, không tự lưu event và không tự bảo đảm giao nhận đúng một lần.

Với soft delete, aggregate vẫn tồn tại nhưng chuyển sang trạng thái bị đánh dấu xóa. Khi đó có thể thiết kế một hành vi và sự kiện khác rồi lưu bằng đường repository phù hợp. Việc thay đổi mô hình xóa không làm `deleteById` mặc nhiên có thêm khả năng phát aggregate events.

## 13. Kiểm tra hành vi đúng trong ứng dụng

### 13.1. Kiểm tra ở mức aggregate

Kiểm tra logic object thuần có thể bao gồm:

1. Đơn hàng nháp chấp nhận xóa và cung cấp đúng một event.
2. Payload chứa đúng mã đơn hàng, khách hàng, tác nhân và thời gian.
3. Đơn hàng ở trạng thái không được phép xóa ném lỗi trước khi ghi nhận event.
4. Provider không sinh thêm event khi được đọc nhiều lần.
5. Cleanup làm collection sự kiện trở về rỗng.

Những kiểm tra này chưa chứng minh rằng Spring repository tự phát event.

### 13.2. Kiểm tra tích hợp repository

Dùng repository thật được Spring tạo với store phù hợp. Một mock repository không tự có interceptor công bố aggregate events.

Các kịch bản có ích:

| Kịch bản | Điều cần quan sát |
|---|---|
| Tải aggregate, ghi nhận event, gọi `delete(aggregate)` | Event được công bố qua tích hợp hỗ trợ |
| Chỉ gọi `deleteById(id)` | Không dựa vào đó để lấy event đang chờ của aggregate |
| Chuẩn bị event trên object rồi vẫn gọi `deleteById(id)` | Việc object tồn tại trong bộ nhớ không thay thế đường tích hợp |
| Không tìm thấy aggregate trong service mẫu | Không có event phê duyệt xóa |
| Xóa bằng bulk query | Không tự đọc provider cho từng aggregate |
| Transaction rollback | Listener after-commit không chạy như một commit thành công |
| Commit thật | Dữ liệu và listener theo phase phản ánh kết quả đã commit |

Với JPA, cần hoàn tất flush hoặc commit khi kịch bản yêu cầu để không nhầm việc đánh dấu removed trong bộ nhớ với việc database đã chấp nhận thao tác.

Một integration test tự rollback ở cuối không đủ để xác minh listener `AFTER_COMMIT`. Muốn kiểm tra phase đó, phải có kịch bản commit thực sự.

### 13.3. Kiểm tra cạnh tranh và lỗi

Transaction không tự giải quyết mọi vấn đề cạnh tranh. Cần chọn và kiểm tra cơ chế nhất quán phù hợp, chẳng hạn khóa như ví dụ JPA hoặc kiểm tra phiên bản theo store.

Cũng cần biết ứng dụng làm gì khi:

- Đơn hàng đổi trạng thái trong lúc một yêu cầu khác muốn xóa.
- Database từ chối xóa do ràng buộc tham chiếu.
- Listener đồng bộ ném exception.
- Transaction thất bại sau khi bộ đệm event đã được dọn.
- Tiến trình dừng sau commit nhưng trước khi gửi thông báo.

Những kịch bản đó xác minh chính sách nghiệp vụ và độ tin cậy của luồng xử lý, không thay đổi lý do gốc khiến `deleteById` thiếu aggregate instance.

## 14. Chẩn đoán nhanh

| Hiện tượng | Điều cần kiểm tra |
|---|---|
| Xóa thành công nhưng không nhận event | Đã gọi `deleteById`, bulk query hay đường repository nhận aggregate? |
| Có SELECT trước DELETE mà vẫn không có event | Có đang nhầm chi tiết implementation với hợp đồng aggregate events không? |
| `@PreRemove` chạy nhưng listener không chạy | Callback JPA và provider Commons có bị coi là cùng một cơ chế không? |
| Gọi `delete(aggregate)` mà không có event | Aggregate có thực sự ghi nhận sự kiện và provider trả đúng collection không? |
| Chuẩn bị event rồi gọi xóa bằng ID | Có truyền chính aggregate đang giữ event vào đường hỗ trợ không? |
| Event được nhận nhưng transaction rollback | Listener có chạy trước commit không? |
| Listener sau commit thiếu dữ kiện | Payload có phụ thuộc vào việc tải lại aggregate đã bị xóa không? |
| Đổi store hoặc sang reactive thì hành vi khác | Module đích có tích hợp cùng điểm repository và mô hình thực thi không? |

Không áp dụng nguyên ví dụ repository JPA đồng bộ cho mọi store hoặc publisher reactive. Phải xác minh module, method và thời điểm thực thi thực tế; một abstraction chung của Commons không bảo đảm mọi implementation có cùng lifecycle.

## 15. Bài thực hành

Xây dựng luồng xóa một aggregate với quy tắc nghiệp vụ cụ thể:

1. Chọn store và ghi rõ điều kiện được phép xóa.
2. Thiết kế event mang đủ dữ kiện trước khi dữ liệu bị xóa.
3. Cho aggregate kiểm tra quy tắc và ghi nhận event.
4. Tải aggregate trong service và gọi `delete(aggregate)` qua repository hỗ trợ.
5. Chọn rõ chính sách khi không tìm thấy dữ liệu.
6. So sánh với lời gọi `deleteById(id)` và giải thích khác biệt về đầu vào.
7. Quan sát thời điểm listener thông thường và listener sau commit.
8. Nếu cần gửi ra ngoài tiến trình, mô tả cách lưu bền thông tin cần gửi và xử lý retry.

Điểm cần nắm là: **ID xác định đối tượng cần xóa, còn aggregate instance cung cấp trạng thái và sự kiện nghiệp vụ đang chờ**. `deleteById` không có cùng điều kiện phát aggregate events vì hợp đồng của nó không mang aggregate đó qua điểm tích hợp; việc implementation có tải entity nội bộ cũng không tạo ra bảo đảm tương đương.