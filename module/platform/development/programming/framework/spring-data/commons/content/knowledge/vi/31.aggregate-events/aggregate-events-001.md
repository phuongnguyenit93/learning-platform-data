# Vai trò của sự kiện miền trong mô hình aggregate

Một aggregate không chỉ lưu giữ trạng thái. Nó còn thực hiện các chuyển đổi có ý nghĩa nghiệp vụ: đơn hàng được xác nhận, hợp đồng được gia hạn, hạn mức được điều chỉnh. **Sự kiện miền** mô tả những điều đã xảy ra sau khi mô hình chấp nhận một chuyển đổi như vậy.

Trong Spring Data Commons, aggregate root có thể ghi nhận các sự kiện chờ công bố. Khi một lời gọi repository được hỗ trợ đi qua cơ chế tích hợp của Spring Data, các sự kiện này có thể được công bố qua hạ tầng sự kiện ứng dụng của Spring.

Cơ chế đó giúp mô hình miền diễn đạt sự thật nghiệp vụ và cho các thành phần khác phản ứng với chúng. Tuy nhiên, **công bố sự kiện không đồng nghĩa giao dịch đã commit, thông điệp đã được lưu bền vững hoặc hệ thống bên ngoài đã xử lý thành công**.

Bài học thuộc chương **Sự kiện aggregate** của module **SPRING_DATA_COMMONS**. Nội dung liên hệ sự kiện miền với abstraction Repository và CRUD, cách mở rộng repository, metadata sự kiện và giới hạn tích hợp của từng loại kho dữ liệu.

## 1. Bắt đầu từ ranh giới aggregate

### 1.1. Aggregate là ranh giới bảo vệ quy tắc

Một aggregate gồm các đối tượng liên quan được thao tác thông qua một aggregate root. Root chịu trách nhiệm giữ các quy tắc nhất quán bên trong ranh giới đó.

Ví dụ, aggregate `PurchaseOrder` có thể chịu trách nhiệm cho các quy tắc:

- Đơn hàng chỉ được xác nhận khi đang ở trạng thái nháp.
- Đơn hàng phải có ít nhất một mặt hàng.
- Tổng tiền phải đáp ứng điều kiện nghiệp vụ để được xác nhận.
- Khi xác nhận thành công, trạng thái chuyển sang `CONFIRMED`.

Một lời gọi nghiệp vụ nên đi qua root:

```java
order.confirm(now);
```

thay vì để mã bên ngoài tự gán trạng thái:

```java
order.setStatus(CONFIRMED);
```

Ở cách đầu tiên, mô hình có một điểm rõ ràng để kiểm tra quy tắc, thay đổi trạng thái và ghi nhận sự kiện. Ở cách thứ hai, việc cập nhật dữ liệu có thể bỏ qua ý nghĩa nghiệp vụ.

Aggregate là ranh giới thiết kế miền. Việc lưu toàn bộ trạng thái của nó có thực sự nguyên tử hay không còn phụ thuộc mapping, transaction manager và khả năng của kho dữ liệu. Một class được gọi là aggregate không tự tạo ra bảo đảm giao dịch.

### 1.2. Sự kiện xuất hiện sau khi mô hình chấp nhận hành động

Với lệnh xác nhận đơn hàng, trình tự trong miền là:

```text
Nhận yêu cầu xác nhận
        |
        v
Kiểm tra trạng thái và điều kiện nghiệp vụ
        |
        +-- Không hợp lệ --> Từ chối, không ghi nhận OrderConfirmed
        |
        v
Đổi trạng thái thành CONFIRMED
        |
        v
Ghi nhận sự kiện OrderConfirmed đang chờ công bố
```

Sự kiện `OrderConfirmed` nói rằng aggregate đã chấp nhận chuyển đổi xác nhận trong bộ nhớ. Khi chuyển đổi này nằm trong một giao dịch chưa commit, khả năng nó trở thành trạng thái bền vững vẫn còn phụ thuộc kết quả giao dịch.

Vì vậy, nơi tiêu thụ sự kiện phải hiểu nó được gọi ở giai đoạn nào. Không dùng một sự kiện được phát trước commit để khẳng định rằng đơn hàng đã tồn tại bền vững trong cơ sở dữ liệu.

## 2. Phân biệt command, domain event và persistence event

| Khái niệm | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Command | `ConfirmOrder` | Yêu cầu hệ thống thử thực hiện một hành động |
| Domain event | `OrderConfirmed` | Ghi nhận một chuyển đổi nghiệp vụ đã được mô hình chấp nhận |
| Persistence event/callback | Callback trước hoặc sau khi lưu | Phản ánh một giai đoạn của cơ chế lưu trữ |
| Integration event | `OrderConfirmedV1` gửi sang hệ thống khác | Hợp đồng thông điệp dành cho ranh giới tích hợp |

### 2.1. Một lệnh có thể thất bại

`ConfirmOrder` không bảo đảm rằng đơn hàng sẽ được xác nhận. Nó có thể bị từ chối vì đơn hàng đã hủy hoặc không có mặt hàng.

Tên sự kiện nên dùng dạng diễn tả việc đã xảy ra:

```text
OrderConfirmed
OrderCancelled
CreditLimitChanged
```

Tránh đặt tên sự kiện như một yêu cầu chưa được thực hiện:

```text
PleaseConfirmOrder
SendConfirmationEmail
```

`SendConfirmationEmail` phù hợp hơn với một command gửi cho thành phần gửi thư. `OrderConfirmed` cho phép nhiều thành phần tự quyết định phản ứng tương ứng với sự thật nghiệp vụ đó.

### 2.2. Lưu thành công không mô tả đầy đủ nghiệp vụ

Một entity được lưu có thể là kết quả của nhiều tình huống:

- Tạo đơn nháp.
- Sửa địa chỉ giao hàng.
- Xác nhận đơn.
- Sửa dữ liệu trong quá trình vận hành.

Nếu mọi lần `save` đều bị diễn giải là `OrderConfirmed`, mô hình sự kiện sẽ sai. **Phương thức nghiệp vụ quyết định sự kiện nào đã xảy ra; repository cung cấp một điểm tích hợp để công bố các sự kiện đã được ghi nhận.**

### 2.3. Domain event không mặc nhiên là integration event

Sự kiện nội bộ có thể dùng tên kiểu và dữ liệu phù hợp với mô hình hiện tại. Thông điệp gửi ra ngoài thường cần thêm hợp đồng ổn định: phiên bản schema, định danh message, thời điểm, quy tắc tương thích và chính sách loại bỏ dữ liệu nhạy cảm.

Có thể chuyển đổi từ domain event sang integration event. Không cần buộc mọi sự kiện nội bộ trở thành API công khai cho các hệ thống khác.

## 3. Sự kiện giúp aggregate phối hợp với phần còn lại như thế nào?

### 3.1. Giữ aggregate tập trung vào quy tắc của nó

Sau khi xác nhận đơn hàng, ứng dụng có thể cần:

- Ghi nhận thay đổi vào một mô hình đọc phục vụ báo cáo.
- Lên lịch gửi thông báo.
- Khởi động một bước tiếp theo trong quy trình xử lý.
- Tạo thông điệp tích hợp cho hệ thống khác.

Aggregate không cần giữ dependency tới email client, message broker hoặc hệ thống báo cáo chỉ để thực hiện các phản ứng này. Nó có thể ghi nhận một sự kiện, còn các thành phần ngoài aggregate xử lý phần việc tương ứng.

Điều này làm rõ sự phân công:

```text
Aggregate: kiểm tra quy tắc, thay đổi trạng thái, ghi nhận sự thật
Application service: điều phối use case và ranh giới giao dịch
Repository: lưu aggregate và tham gia cơ chế công bố được hỗ trợ
Listener/handler: phản ứng với sự kiện theo hợp đồng của ứng dụng
```

### 3.2. Không đưa invariant quan trọng ra khỏi root

Giả sử quy tắc là đơn hàng không được xác nhận nếu tổng tiền không hợp lệ. Kiểm tra đó phải nằm trong đường thực hiện xác nhận, trước khi ghi nhận `OrderConfirmed`.

Không nên đổi trạng thái trước rồi hy vọng một listener sẽ phát hiện tổng tiền sai và sửa lại. Listener có thể được cấu hình chạy sau commit, chạy bất đồng bộ hoặc thất bại độc lập.

Đối với quy tắc liên quan nhiều aggregate, cần quyết định rõ:

- Có yêu cầu nhất quán tức thời không?
- Có thể biểu diễn trạng thái chờ xử lý không?
- Có cần một quy trình nhiều bước và hành động bù không?

Ví dụ, nếu cần xác nhận tồn kho trước khi chấp nhận đơn hàng, một trạng thái như `PENDING_STOCK` có thể phù hợp hơn việc công bố `OrderConfirmed` rồi mới phát hiện không còn hàng. Tên sự kiện phải phản ánh đúng cam kết nghiệp vụ tại thời điểm phát sinh.

### 3.3. Không phải thao tác nào cũng cần sự kiện

Sự kiện hữu ích khi một thay đổi có ý nghĩa mà thành phần khác cần biết. Không cần phát một domain event cho mọi setter, mọi lần đọc repository hay mọi thao tác sửa định dạng hiển thị.

Nếu một cộng tác viên bắt buộc phải trả kết quả ngay để use case tiếp tục, một lời gọi Java tường minh có thể dễ hiểu hơn. Dùng sự kiện nên làm rõ quan hệ nghiệp vụ, không tạo ra chuỗi điều khiển khó quan sát.

## 4. Ghi nhận sự kiện bằng Spring Data Commons

### 4.1. Hai annotation cốt lõi

Spring Data Commons cung cấp:

| API | Vai trò |
| --- | --- |
| `@DomainEvents` | Đánh dấu phương thức trên aggregate root cung cấp sự kiện cần công bố |
| `@AfterDomainEventPublication` | Đánh dấu phương thức dọn dẹp sau khi cơ chế công bố đã thực hiện |
| `AbstractAggregateRoot` | Lớp hỗ trợ lưu danh sách sự kiện chờ công bố và triển khai các điểm móc tương ứng |

Một triển khai thủ công có thể chứa các phương thức như sau:

```java
private final List<Object> pendingEvents = new ArrayList<>();

@DomainEvents
Collection<Object> domainEvents() {
    return List.copyOf(pendingEvents);
}

@AfterDomainEventPublication
void clearDomainEvents() {
    pendingEvents.clear();
}
```

Các annotation thuộc package `org.springframework.data.domain`. Ví dụ này chỉ thể hiện phần thu thập và dọn sự kiện; khi đưa vào entity thực tế, phải loại danh sách sự kiện tạm khỏi mapping theo cơ chế của store.

Phương thức `@DomainEvents` là phương thức không nhận đối số, trả một sự kiện hoặc tập hợp sự kiện. Annotation được đặt trên phương thức cung cấp sự kiện của aggregate, không phải trên class sự kiện.

Phương thức `@AfterDomainEventPublication` cũng không nhận đối số. Nó thường xóa các sự kiện đã công bố để tránh phát lại trong một lần lưu kế tiếp của cùng đối tượng.

### 4.2. Dọn sự kiện không phải xác nhận commit

Tên `@AfterDomainEventPublication` nói về **publication**, không nói về transaction commit.

Sau khi callback dọn danh sách đã chạy, giao dịch vẫn có thể thất bại ở giai đoạn sau. Việc danh sách sự kiện trong bộ nhớ đã rỗng không chứng minh rằng:

- Dữ liệu đã commit.
- Listener sau commit đã chạy xong.
- Thông điệp đã tới message broker.
- Tất cả consumer đã xử lý thành công.

Không dùng danh sách này như một hàng đợi giao nhận bền vững.

### 4.3. `AbstractAggregateRoot` giảm mã lặp

Thay vì tự quản lý danh sách và annotation, aggregate có thể kế thừa:

```java
AbstractAggregateRoot<PurchaseOrder>
```

Trong phương thức nghiệp vụ, gọi:

```java
registerEvent(event);
```

để ghi nhận một sự kiện đang chờ công bố. `registerEvent` không tự gọi repository và cũng không tự gửi thông điệp ra bên ngoài.

Đây là một lớp hỗ trợ, không phải yêu cầu bắt buộc của thiết kế aggregate. Nếu cần kế thừa một lớp khác hoặc muốn tự kiểm soát cơ chế thu thập sự kiện, có thể sử dụng hai annotation trực tiếp.

## 5. Ví dụ: xác nhận đơn hàng

Các đoạn mã dưới đây dùng cú pháp `record` của Java hiện đại và tập trung vào mô hình miền cùng điểm tích hợp repository. Khi thực hành, cần bổ sung mapping entity theo store, cấu hình repository và transaction manager tương ứng.

### 5.1. Thiết kế một sự kiện bất biến

```java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

public record OrderConfirmed(
        UUID eventId,
        UUID orderId,
        UUID customerId,
        BigDecimal total,
        String currency,
        Instant occurredAt
) {
}
```

Ý nghĩa các trường:

| Trường | Mục đích |
| --- | --- |
| `eventId` | Phân biệt lần phát sinh sự kiện, hỗ trợ nhận diện bản trùng |
| `orderId` | Xác định aggregate đã thay đổi |
| `customerId` | Cung cấp định danh liên quan mà handler cần |
| `total`, `currency` | Snapshot dữ liệu nghiệp vụ tại lúc xác nhận |
| `occurredAt` | Thời điểm hành động nghiệp vụ được ghi nhận |

`occurredAt` không phải thời điểm commit. UUID ngẫu nhiên cũng không cung cấp thứ tự nghiệp vụ giữa nhiều sự kiện.

Ví dụ dùng các kiểu giá trị bất biến như `UUID`, `BigDecimal`, `String` và `Instant`. Nếu sự kiện chứa danh sách hoặc object mutable, cần tạo snapshot phù hợp; một `record` có field kiểu `List` chưa tự bảo đảm bất biến sâu.

### 5.2. Root thay đổi trạng thái và ghi nhận sự kiện

```java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

import org.springframework.data.domain.AbstractAggregateRoot;

public class PurchaseOrder extends AbstractAggregateRoot<PurchaseOrder> {

    public enum Status {
        DRAFT,
        CONFIRMED
    }

    private final UUID id;
    private final UUID customerId;
    private final BigDecimal total;
    private final String currency;
    private final int itemCount;
    private Status status;

    public PurchaseOrder(
            UUID id,
            UUID customerId,
            BigDecimal total,
            String currency,
            int itemCount
    ) {
        this.id = Objects.requireNonNull(id);
        this.customerId = Objects.requireNonNull(customerId);
        this.total = Objects.requireNonNull(total);
        this.currency = Objects.requireNonNull(currency);
        this.itemCount = itemCount;
        this.status = Status.DRAFT;
    }

    public void confirm(Instant now) {
        Objects.requireNonNull(now);

        if (status != Status.DRAFT) {
            throw new IllegalStateException("Order is not a draft");
        }
        if (itemCount <= 0) {
            throw new IllegalStateException("Order has no items");
        }
        if (total.signum() <= 0) {
            throw new IllegalStateException("Order total must be positive");
        }
        if (currency.isBlank()) {
            throw new IllegalStateException("Currency is required");
        }

        status = Status.CONFIRMED;

        registerEvent(new OrderConfirmed(
                UUID.randomUUID(),
                id,
                customerId,
                total,
                currency,
                now
        ));
    }

    public UUID getId() {
        return id;
    }

    public Status getStatus() {
        return status;
    }
}
```

Quy tắc tổng tiền dương là giả định của ví dụ; hệ thống cho phép đơn miễn phí có thể cần một quy tắc khác.

Các điểm cần quan sát:

1. `confirm` giữ invariant và thực hiện chuyển trạng thái.
2. Sự kiện chỉ được đăng ký sau khi các điều kiện trong ví dụ đã được chấp nhận.
3. Aggregate không gọi email service, broker hoặc repository.
4. Thời gian được truyền vào, giúp mã miền dễ kiểm tra với một thời điểm cố định.
5. Định danh đơn hàng đã có trước khi sự kiện được tạo.

Nếu store cấp ID khi lưu, không mặc định ID đã tồn tại lúc gọi `registerEvent`. Phải thiết kế thời điểm tạo sự kiện hoặc chiến lược cấp định danh cho phù hợp. Tương tự, version do persistence cập nhật có thể chưa sẵn có khi mô hình tạo sự kiện.

Mô hình trên lưu `itemCount` và `total` để giữ ví dụ gọn. Trong một aggregate thực tế có các dòng hàng, root cần quản lý chúng và duy trì các giá trị tổng hợp theo quy tắc của miền.

### 5.3. Application service điều phối use case

Repository minh họa:

```java
import java.util.UUID;

import org.springframework.data.repository.CrudRepository;

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, UUID> {
}
```

Application service:

```java
import java.time.Clock;
import java.util.UUID;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ConfirmOrderService {

    private final PurchaseOrderRepository orders;
    private final Clock clock;

    public ConfirmOrderService(PurchaseOrderRepository orders, Clock clock) {
        this.orders = orders;
        this.clock = clock;
    }

    @Transactional
    public void confirm(UUID orderId) {
        PurchaseOrder order = orders.findById(orderId)
                .orElseThrow(() -> new IllegalArgumentException(
                        "Order not found: " + orderId
                ));

        order.confirm(clock.instant());
        orders.save(order);
    }
}
```

Ví dụ giả định `Clock` được khai báo thành bean, domain object được ánh xạ đúng cho store, và phương thức service được gọi qua proxy giao dịch của Spring. `@Transactional` chỉ có tác dụng theo cấu hình hạ tầng thực tế; annotation này không tự cung cấp transaction cho mọi loại kho dữ liệu.

Với repository proxy và cơ chế domain events được module hỗ trợ, `save(order)` là điểm để Spring Data thu thập các sự kiện từ aggregate được truyền vào và công bố chúng.

Đối với JPA, thay đổi entity đang managed có thể được lưu nhờ dirty checking. Tuy nhiên, **dirty checking và việc kích hoạt cơ chế domain events của repository là hai chuyện khác nhau**. Không suy ra rằng mọi lần flush hoặc mọi thay đổi được JPA phát hiện đều làm Spring Data gọi phương thức `@DomainEvents`.

## 6. Vòng đời: ghi nhận, lưu, công bố, commit

Một luồng thường gặp với service giao dịch có thể được đọc như sau:

```text
Bắt đầu transaction
        |
        v
Load aggregate
        |
        v
order.confirm(...) -> đổi trạng thái + lưu sự kiện tạm
        |
        v
repository.save(order)
        |
        v
Cơ chế repository công bố sự kiện qua Spring
        |
        +--> Listener thông thường có thể chạy ngay
        |
        +--> Listener giao dịch đăng ký xử lý ở phase đã chọn
        |
        v
Dọn danh sách sự kiện sau publication
        |
        v
Transaction tiếp tục và thử commit
        |
        +-- Rollback --> không có xử lý AFTER_COMMIT
        |
        +-- Commit thành công --> xử lý AFTER_COMMIT
```

Sơ đồ mô tả trường hợp đồng bộ thông dụng để phân biệt các mốc. Không dùng nó để suy ra rằng mọi store đã gửi lệnh ghi xuống cơ sở dữ liệu hoặc flush xong trước khi listener thông thường chạy.

### 6.1. Không có transaction thì không có bảo đảm commit theo sơ đồ

Một lời gọi repository có thể có transaction riêng, tham gia transaction ngoài hoặc chạy theo khả năng khác của store. Thời điểm và phạm vi transaction phải được xác định trong ứng dụng cụ thể.

Nếu use case cần nhiều thao tác thuộc cùng một transaction, đặt ranh giới điều phối ở service và cấu hình transaction manager phù hợp. Không suy ra một transaction chung chỉ vì mọi thao tác đều dùng interface Repository.

### 6.2. Rollback không phục hồi object trong bộ nhớ

Khi transaction rollback, trạng thái cơ sở dữ liệu có thể được hoàn tác theo khả năng transaction. Tuy nhiên, đối tượng `PurchaseOrder` đang giữ trong bộ nhớ vẫn có thể mang trạng thái `CONFIRMED` và danh sách sự kiện đã được dọn.

Không coi rollback là cơ chế tự động khôi phục mọi field Java. Khi retry một giao dịch, nên tải lại trạng thái bền vững và thực hiện lại use case theo chính sách retry, concurrency và idempotency đã thiết kế.

## 7. Listener chạy khi nào?

### 7.1. `@EventListener`: phản ứng với publication

Listener thông thường có thể nhận sự kiện bằng:

```java
@EventListener
public void on(OrderConfirmed event) {
    // Xử lý nội bộ theo hợp đồng của ứng dụng.
}
```

Trong cấu hình Spring application events mặc định, listener thông thường được gọi đồng bộ trên luồng công bố. Nếu ứng dụng cấu hình executor hoặc cơ chế bất đồng bộ, đặc tính thực thi có thể thay đổi.

Với luồng đồng bộ, listener có thể chạy trước khi transaction của service commit. Một lỗi không được xử lý từ listener có thể truyền ngược ra lời gọi repository và ảnh hưởng kết quả transaction, tùy loại exception và quy tắc rollback.

Không dùng vị trí này để gửi một email không thể thu hồi rồi mặc định rằng transaction sau đó chắc chắn thành công.

### 7.2. `@TransactionalEventListener`: gắn với phase giao dịch

Khi có transaction phù hợp, listener có thể đăng ký xử lý sau commit:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class OrderConfirmationObserver {

    private static final Logger log =
            LoggerFactory.getLogger(OrderConfirmationObserver.class);

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void afterCommit(OrderConfirmed event) {
        log.info("Order committed: orderId={}, eventId={}",
                event.orderId(), event.eventId());
    }
}
```

Ví dụ chỉ minh họa thời điểm quan sát; log không phải một cơ chế giao nhận sự kiện bền vững.

Các phase thường gặp:

| Phase | Mục đích |
| --- | --- |
| `BEFORE_COMMIT` | Xử lý trước khi giao dịch commit |
| `AFTER_COMMIT` | Xử lý sau khi commit thành công |
| `AFTER_ROLLBACK` | Phản ứng khi rollback |
| `AFTER_COMPLETION` | Phản ứng khi giao dịch kết thúc, gồm cả commit và rollback |

Với cấu hình mặc định của `@TransactionalEventListener`, nếu không có transaction phù hợp thì listener không được gọi như một listener thông thường. Việc bật `fallbackExecution` thay đổi hành vi này và cần có chủ đích.

### 7.3. Sau commit vẫn có thể thất bại

`AFTER_COMMIT` giải quyết câu hỏi về **thời điểm**, không giải quyết toàn bộ câu hỏi về **độ tin cậy**.

Nếu tiến trình dừng sau commit nhưng trước khi gửi thông báo, thông báo có thể bị mất. Nếu gửi thành công rồi tiến trình dừng trước khi ghi nhận kết quả, thao tác retry có thể gửi trùng.

Nếu listener sau commit cần ghi thêm dữ liệu, không mặc định nó vẫn có một transaction ghi có thể commit cùng transaction vừa kết thúc. Cần thiết kế một transaction mới hoặc một cơ chế xử lý riêng phù hợp. Khi dùng `REQUIRES_NEW`, cũng phải bảo đảm lời gọi đi qua proxy giao dịch đúng cách.

`@Async` có thể giúp tách thời gian chạy khỏi luồng gọi, nhưng không tự thêm lưu trữ bền vững, retry hoặc transaction chung.

## 8. Khi cần giao nhận bền vững: outbox

Nếu thông báo là bắt buộc phải được chuyển đến một hệ thống khác, chỉ dựa vào danh sách sự kiện trong aggregate và một listener trong bộ nhớ thường chưa đủ.

Một hướng thiết kế là transactional outbox:

```text
Trong cùng một transaction có hiệu lực:
    Lưu trạng thái aggregate
    Lưu bản ghi outbox cho thông điệp cần chuyển
                  |
                  v
                Commit
                  |
                  v
Relay đọc outbox và gửi tới broker
                  |
                  v
Consumer xử lý có khả năng nhận lại cùng thông điệp
```

Ý nghĩa của thiết kế này là trạng thái nghiệp vụ và ý định gửi thông điệp được lưu bền vững cùng nhau. Bảo đảm đó chỉ tồn tại nếu hai thao tác ghi thực sự tham gia cùng một transaction được kho dữ liệu hỗ trợ.

Một triển khai có thể dùng listener đồng bộ trong transaction để chuyển domain event thành bản ghi outbox. Khi làm vậy, phải kiểm tra rằng listener và repository outbox tham gia transaction hiện tại; tên annotation không đủ để chứng minh tính nguyên tử.

Không ghi outbox ở `AFTER_COMMIT` rồi tuyên bố nó nguyên tử với cập nhật aggregate: transaction của aggregate đã kết thúc trước bước đó.

Outbox còn cần:

- Chính sách lấy và xử lý các bản ghi chưa gửi.
- Retry khi broker hoặc mạng lỗi.
- Nhận diện thông điệp bằng một ID ổn định khi gửi lại.
- Theo dõi lỗi và tồn đọng.
- Consumer idempotent theo hợp đồng xử lý.

Outbox không tự biến toàn bộ hệ thống thành cơ chế xử lý đúng một lần. Trong nhiều thiết kế, consumer vẫn phải chấp nhận khả năng nhận lặp.

Đây là phần mở rộng kiến trúc khi yêu cầu cần đến; không phải khả năng được tự động cung cấp chỉ bằng `AbstractAggregateRoot`.

## 9. Thiết kế payload và metadata sự kiện

### 9.1. Dùng snapshot có chủ đích

Tránh tạo sự kiện chỉ giữ tham chiếu tới entity đang thay đổi:

```java
record OrderConfirmed(PurchaseOrder order) {
}
```

Những vấn đề có thể xuất hiện:

- Listener đọc trạng thái mới hơn thời điểm sự kiện phát sinh.
- Lazy association không còn truy cập được ngoài persistence context.
- Serialization kéo theo một object graph lớn.
- Payload vô tình lộ dữ liệu không cần thiết.
- Consumer bị phụ thuộc vào cấu trúc entity nội bộ.

Thay vào đó, chọn các định danh và giá trị bất biến mà handler thực sự cần.

Không phải mọi event đều phải chứa toàn bộ snapshot. Có thể chỉ chứa ID rồi đọc lại trạng thái nếu consumer chấp nhận nhìn thấy trạng thái hiện tại. Điều quan trọng là biết mình cần **trạng thái tại thời điểm sự kiện** hay **trạng thái mới nhất**.

### 9.2. Chọn metadata theo nhu cầu thực tế

| Metadata | Khi hữu ích |
| --- | --- |
| `eventId` | Nhận diện bản trùng, theo dõi một lần phát sinh |
| `aggregateId` | Liên hệ với aggregate nguồn |
| `occurredAt` | Diễn đạt thời điểm nghiệp vụ |
| `aggregateVersion` hoặc sequence | Kiểm tra thứ tự khi đã có một chiến lược cấp version rõ ràng |
| `correlationId` | Theo dõi các bước trong cùng một luồng xử lý |
| `causationId` | Liên hệ sự kiện với command hoặc sự kiện gây ra nó |
| `tenantId` | Cách ly và định tuyến trong hệ thống nhiều tenant |
| `schemaVersion` | Quản lý hợp đồng thông điệp tích hợp |

Không thêm metadata chỉ để đủ danh sách. Mỗi trường cần có nguồn cấp, ý nghĩa và nơi sử dụng rõ ràng.

Đặc biệt, không lấy timestamp làm bằng chứng thứ tự tuyệt đối giữa các máy. Nếu consumer cần thứ tự theo aggregate, phải thiết kế sequence, optimistic locking và cách vận chuyển tương ứng; `occurredAt` chưa đủ.

### 9.3. Tránh giả định dữ liệu thread luôn có sẵn

Metadata như người thao tác hoặc tenant thường đến từ application context đã được xác thực. Aggregate không nhất thiết phải tự truy cập security context hay `ThreadLocal` để lấy chúng.

Nếu cần đưa metadata vào sự kiện, truyền giá trị hoặc context miền có chủ đích từ lớp điều phối. Khi xử lý bất đồng bộ hoặc reactive, không mặc định mọi dữ liệu gắn với luồng đồng bộ vẫn tồn tại.

## 10. Repository, CRUD và giới hạn của từng store

### 10.1. Phải đi qua cơ chế được hỗ trợ

Các lời gọi như `save` và `saveAll` là những điểm tích hợp điển hình của cơ chế aggregate domain events trên repository Spring Data được hỗ trợ.

Không suy ra cơ chế này sẽ chạy với:

- Một đối tượng repository được tự `new`, không đi qua hạ tầng proxy tương ứng.
- Câu lệnh SQL chạy trực tiếp.
- Một bulk update không nạp aggregate.
- Một thao tác dùng template/client riêng để ghi dữ liệu.
- Một repository fragment mà đường thực thi không đi qua điểm móc cần thiết.

Nếu mở rộng repository hoặc dùng phương thức ghi tùy biến, cần xác định rõ nó có tiếp tục thu thập và công bố sự kiện từ aggregate hay không.

### 10.2. `deleteById` không cung cấp aggregate cho cơ chế này

Cơ chế sự kiện gắn với aggregate cần có đối tượng để đọc các sự kiện đã ghi nhận. Một lời gọi chỉ truyền ID như `deleteById` không nên được xem là điểm tự động công bố các sự kiện của aggregate.

Nếu nghiệp vụ là hủy đơn, mô hình thường cần một phương thức như:

```java
order.cancel(reason, now);
```

để kiểm tra quy tắc, đổi trạng thái và ghi nhận `OrderCancelled`. Sau đó lưu thay đổi theo use case.

Việc hủy nghiệp vụ không mặc nhiên tương đương xóa vật lý một bản ghi. Nếu thực sự cần xóa vật lý và phát sự kiện, phải xem phương thức delete nào được module hỗ trợ, đối tượng nào được truyền vào và transaction bao quanh nó.

### 10.3. Cùng abstraction không có nghĩa cùng khả năng lưu trữ

| Khía cạnh | Câu hỏi cần xác định |
| --- | --- |
| Mapping aggregate | Root và các thành phần được ghi vào bao nhiêu bản ghi/tài liệu? |
| Transaction | Phạm vi nguyên tử nào được store và cấu hình hiện tại hỗ trợ? |
| Repository method | Phương thức nào thực sự kích hoạt cơ chế domain events? |
| Optimistic locking | Hai command đồng thời được phát hiện xung đột như thế nào? |
| Reactive | Context giao dịch và sự kiện được truyền theo mô hình nào? |
| Bulk operation | Có nạp aggregate và chạy hành vi miền không? |

Spring Data Commons cung cấp abstraction dùng chung, còn store module quyết định cách tích hợp với cơ chế lưu trữ cụ thể. Không suy ra hành vi giống nhau giữa JPA, JDBC, MongoDB và các module khác chỉ vì cùng có tên `save`.

## 11. Idempotency, concurrency và khả năng phát lại

### 11.1. Không lặp sự kiện do lặp `save`

Nếu aggregate vẫn giữ một sự kiện sau khi đã công bố, lần `save` kế tiếp của cùng đối tượng có thể phát lại nó. Đây là lý do cần dọn sự kiện qua callback hoặc lớp hỗ trợ.

Tuy nhiên, dọn danh sách chỉ xử lý một nguồn gây lặp trong bộ nhớ. Nó không xử lý bản trùng do mạng, retry gửi broker hoặc consumer nhận lại message.

### 11.2. Lặp command khác với lặp delivery

Hai tình huống cần xử lý riêng:

| Tình huống | Chính sách cần có |
| --- | --- |
| Client gửi lại `ConfirmOrder` | Quyết định trả kết quả cũ, từ chối hay dùng command id để chống lặp |
| Consumer nhận lại cùng `OrderConfirmed` | Nhận diện event/message ID và tránh lặp hiệu ứng nghiệp vụ |

Trong ví dụ, gọi `confirm` lần thứ hai bị từ chối vì trạng thái không còn là `DRAFT`. Đây là một chính sách từ chối thao tác lặp; nó chưa phải giao thức idempotency hoàn chỉnh để client nhận lại cùng một kết quả thành công.

Nếu consumer cần chống trùng, có thể lưu khóa đã xử lý gồm định danh consumer và event ID. Việc ghi khóa và thay đổi trạng thái của consumer phải có ranh giới nguyên tử phù hợp, nếu không vẫn có cửa sổ lỗi.

### 11.3. Hai command đồng thời cần kiểm soát xung đột

Hai transaction có thể cùng đọc một đơn nháp rồi cùng thử xác nhận. Kiểm tra `status == DRAFT` trong bộ nhớ của mỗi transaction chưa đủ để ngăn cả hai cùng tiến hành.

Có thể cần optimistic locking hoặc cơ chế concurrency khác của store. Nếu một transaction thua vì version conflict, những side effect không thể thu hồi đã thực hiện trước đó vẫn là vấn đề. Đây là thêm một lý do để phân biệt publication trước commit với thông điệp được gửi sau khi trạng thái đã được lưu bền vững.

Không dùng sự tồn tại của domain event như một thay thế cho khóa, version hoặc ràng buộc nhất quán trong kho dữ liệu.

## 12. Những điều sự kiện aggregate không tự cung cấp

- Không tự biến mô hình CRUD thành event sourcing. Event sourcing yêu cầu lưu chuỗi sự kiện làm nguồn sự thật và tái dựng trạng thái theo thiết kế riêng.
- Không bắt buộc sử dụng CQRS. Một ứng dụng vẫn có thể dùng chung mô hình đọc và ghi.
- Không tự gửi sự kiện tới Kafka, RabbitMQ hoặc một broker khác.
- Không tự cung cấp retry, dead-letter queue hoặc lưu trữ sự kiện.
- Không tự tạo transaction phân tán giữa nhiều kho dữ liệu.
- Không thay thế auditing. Các trường `createdBy`, `lastModifiedDate` và một sự kiện như `OrderConfirmed` phục vụ những câu hỏi khác nhau.
- Không bảo đảm projection hoặc mô hình đọc được cập nhật tức thời nếu handler chạy sau commit hoặc bất đồng bộ.

Các khả năng này có thể được bổ sung, nhưng cần những thành phần và hợp đồng cụ thể ngoài cơ chế aggregate events cơ bản.

## 13. Tình huống thực hành và tiêu chí kiểm chứng

### 13.1. Bài thực hành

Xây dựng use case xác nhận đơn theo ví dụ và thực hiện theo thứ tự:

1. Hoàn thiện mapping `PurchaseOrder` cho một store cụ thể.
2. Cấu hình repository và transaction manager thích hợp.
3. Ghi nhận `OrderConfirmed` từ phương thức `confirm`.
4. Thêm một observer thông thường để quan sát publication.
5. Thêm một observer `AFTER_COMMIT` để quan sát giao dịch thành công.
6. Tạo một tình huống khiến transaction rollback sau khi repository đã công bố sự kiện.
7. So sánh trạng thái bền vững, trạng thái object trong bộ nhớ và các observer đã chạy.

Mục tiêu là nhìn thấy các mốc khác nhau, không chỉ đếm số lần gọi listener.

### 13.2. Ma trận cần kiểm chứng trong dự án thực hành

| Tình huống | Điều cần kiểm chứng |
| --- | --- |
| Đơn nháp hợp lệ được xác nhận | Trạng thái đổi và một sự kiện được ghi nhận |
| Đơn không có mặt hàng | Không chuyển sang xác nhận và không ghi nhận sự kiện thành công |
| Lưu một đơn không có thay đổi nghiệp vụ mới | Không tự tạo thêm `OrderConfirmed` |
| Lưu lại cùng object sau publication | Danh sách đã công bố được dọn theo cơ chế đang dùng |
| Transaction rollback | Không có cập nhật đã commit và observer `AFTER_COMMIT` không xử lý thành công đó |
| Listener đồng bộ ném lỗi | Quan sát exception và quy tắc rollback thực tế |
| Hai transaction xác nhận đồng thời | Xung đột được xử lý theo cơ chế concurrency đã chọn |
| Consumer nhận lại một event | Không lặp hiệu ứng ngoài chính sách cho phép |
| Ghi bằng bulk update hoặc client trực tiếp | Không giả định cơ chế aggregate events đã chạy |

Trong bài kiểm tra có transaction tự rollback ở cuối, listener `AFTER_COMMIT` thường không chạy như một luồng commit thành công. Cần điều khiển ranh giới transaction của bài kiểm tra phù hợp với hành vi muốn quan sát.

### 13.3. Câu hỏi tự đánh giá

1. Vì sao `OrderConfirmed` nên được tạo trong hành vi miền thay vì tạo cho mọi lần repository `save`?
2. Vì sao callback dọn sự kiện không chứng minh dữ liệu đã commit?
3. Khi nào một listener phải chạy trong transaction hiện tại, khi nào cần sau commit?
4. Vì sao `AFTER_COMMIT` vẫn chưa đủ để bảo đảm email hoặc message luôn được gửi?
5. Vì sao giữ nguyên entity trong payload có thể làm ý nghĩa sự kiện thay đổi theo thời gian?
6. Nếu use case ghi trực tiếp bằng SQL, ai chịu trách nhiệm giữ hợp đồng sự kiện?
7. Khi consumer nhận lại thông điệp, event ID giúp gì và chưa giải quyết được điều gì?

## 14. Điểm cần ghi nhớ

- Aggregate bảo vệ invariant; domain event mô tả một chuyển đổi có ý nghĩa mà mô hình đã chấp nhận.
- Root ghi nhận sự kiện, application service điều phối và repository tham gia công bố theo khả năng tích hợp.
- `@DomainEvents`, `@AfterDomainEventPublication` và `AbstractAggregateRoot` hỗ trợ thu thập, công bố và dọn sự kiện tạm.
- Publication, transaction commit và giao nhận bền vững là các mốc riêng biệt.
- Listener phải được chọn theo thời điểm, yêu cầu transaction và chính sách thất bại của use case.
- Payload nên biểu đạt đúng sự thật nghiệp vụ bằng dữ liệu ổn định; metadata cần có ý nghĩa rõ ràng.
- Khi cần tích hợp tin cậy, bổ sung lưu trữ bền vững, retry và idempotency theo thiết kế phù hợp, chẳng hạn outbox.
- Luôn xét khả năng của store, repository method và ranh giới giao dịch thực tế trước khi dựa vào hành vi sự kiện.