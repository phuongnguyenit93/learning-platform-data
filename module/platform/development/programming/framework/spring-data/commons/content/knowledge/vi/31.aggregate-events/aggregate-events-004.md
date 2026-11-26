# AbstractAggregateRoot và đăng ký sự kiện

## 1. Mục tiêu và phạm vi

Trong chương **Sự kiện aggregate** của module **Spring Data Commons**, bài này giới thiệu cách dùng `AbstractAggregateRoot` để ghi nhận các sự kiện được tạo ra khi aggregate thực hiện hành vi nghiệp vụ.

Sau bài học, bạn cần làm được các việc sau:

- Khai báo đúng kiểu kế thừa và dùng `registerEvent`, `andEvent`.
- Phân biệt đăng ký sự kiện trong bộ nhớ với phát sự kiện qua repository.
- Thiết kế payload phản ánh điều đã xảy ra.
- Hiểu vai trò của việc dọn danh sách sự kiện và `andEventsFrom`.
- Kiểm tra riêng hành vi domain, repository và thời điểm xử lý theo transaction.

Ví dụ xuyên suốt là xác nhận đơn hàng. Một đơn ở trạng thái nháp có thể được xác nhận; một lần chuyển trạng thái hợp lệ tạo ra sự kiện `PurchaseOrderConfirmed`.

Phần tích hợp dùng Spring Data JPA đồng bộ để có một store cụ thể. Các API đăng ký sự kiện thuộc Commons; mapping entity, repository và transaction vẫn cần cấu hình theo store.

## 2. AbstractAggregateRoot cung cấp những gì?

`AbstractAggregateRoot<A>` là lớp tiện ích giữ các sự kiện chờ phát và cung cấp các hook cho hạ tầng repository.

~~~java
public class PurchaseOrder
        extends AbstractAggregateRoot<PurchaseOrder> {
    // Trạng thái và hành vi nghiệp vụ.
}
~~~

Tham số kiểu là **kiểu aggregate**, không phải kiểu id. Trong ví dụ, id là `UUID` nhưng tham số generic vẫn là `PurchaseOrder`.

| Method | Kết quả |
| --- | --- |
| `registerEvent(T event)` | Thêm sự kiện, trả lại chính sự kiện |
| `andEvent(Object event)` | Thêm sự kiện, trả lại aggregate |
| `domainEvents()` | Cung cấp các sự kiện đang chờ |
| `clearDomainEvents()` | Xóa danh sách đang chờ |
| `andEventsFrom(A aggregate)` | Thêm các sự kiện của aggregate được truyền vào |

Các method này có phạm vi `protected`; chúng phục vụ triển khai aggregate. Không cần mở một API công khai cho controller tự thêm sự kiện tùy ý.

Xem [AbstractAggregateRoot API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/AbstractAggregateRoot.html).

## 3. Thiết kế một sự kiện thể hiện việc đã xảy ra

Một sự kiện xác nhận đơn hàng nên mang những dữ liệu cần thiết để bên nhận hiểu được sự việc:

~~~java
package com.example.orders;

import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

public record PurchaseOrderConfirmed(
        UUID eventId,
        UUID orderId,
        Instant occurredAt) {

    public PurchaseOrderConfirmed {
        Objects.requireNonNull(eventId, "eventId");
        Objects.requireNonNull(orderId, "orderId");
        Objects.requireNonNull(occurredAt, "occurredAt");
    }
}
~~~

Các field có mục đích khác nhau:

| Field | Ý nghĩa |
| --- | --- |
| `eventId` | Nhận diện một sự kiện cụ thể |
| `orderId` | Nhận diện aggregate đã tạo sự kiện |
| `occurredAt` | Thời điểm hành vi nghiệp vụ được ghi nhận |

Tên `PurchaseOrderConfirmed` diễn đạt một kết quả đã xảy ra. Một command như `ConfirmPurchaseOrder` lại yêu cầu hệ thống thực hiện hành vi; hai loại thông điệp có vai trò khác nhau.

Ví dụ chọn `UUID` và `Instant`, đều là các giá trị bất biến. Nếu bổ sung collection vào record, cần kiểm soát tính bất biến của collection đó; record không tự sao chép sâu mọi object bên trong.

Tránh để payload giữ trực tiếp một entity mutable. Nếu entity tiếp tục thay đổi, bên nhận có thể quan sát trạng thái khác với thời điểm đăng ký sự kiện. Các quan hệ lazy cũng có thể phụ thuộc persistence context đã đóng.

`occurredAt` được cung cấp cho hành vi domain, giúp kiểm tra dễ hơn. Nó không được gọi là thời điểm database commit.

## 4. Đăng ký sau khi hành vi nghiệp vụ hợp lệ

Các public type trong ví dụ được đặt trong file Java riêng khi đưa vào một project. Enum trạng thái:

~~~java
package com.example.orders;

public enum PurchaseOrderStatus {
    DRAFT,
    CONFIRMED
}
~~~

Aggregate minh họa dùng mapping JPA:

~~~java
package com.example.orders;

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
    private PurchaseOrderStatus status;

    protected PurchaseOrder() {
    }

    protected PurchaseOrder(UUID id) {
        this.id = Objects.requireNonNull(id, "id");
        this.status = PurchaseOrderStatus.DRAFT;
    }

    public static PurchaseOrder draft(UUID id) {
        return new PurchaseOrder(id);
    }

    public void confirm(Instant occurredAt) {
        Objects.requireNonNull(occurredAt, "occurredAt");

        if (status != PurchaseOrderStatus.DRAFT) {
            throw new IllegalStateException(
                    "Only draft orders can be confirmed");
        }

        status = PurchaseOrderStatus.CONFIRMED;

        registerEvent(new PurchaseOrderConfirmed(
                UUID.randomUUID(),
                id,
                occurredAt));
    }

    public UUID getId() {
        return id;
    }

    public PurchaseOrderStatus getStatus() {
        return status;
    }
}
~~~

Một lần `confirm` hợp lệ thực hiện ba việc: kiểm tra điều kiện, chuyển trạng thái và ghi nhận sự kiện. Không đăng ký sự kiện trước khi biết hành vi có được chấp nhận hay không.

Gọi `confirm` lần hai trong ví dụ sẽ báo lỗi và không thêm sự kiện thứ hai. Đây là quy tắc của domain trong ví dụ. `AbstractAggregateRoot` không tự ngăn hai lần đăng ký cùng một loại sự kiện.

Mã đơn được cấp trước khi xác nhận, nên payload đã có `orderId`. Nếu dùng id do database sinh, cần thiết kế thời điểm tạo sự kiện cho phù hợp. Không mặc định id sẽ tự được bổ sung vào một record đã tạo trước đó.

`@Version` phục vụ kiểm soát cạnh tranh của JPA, độc lập với việc giữ sự kiện trong bộ nhớ.

### 4.1. registerEvent trả về sự kiện

Có thể dùng giá trị trả về nếu phương thức nghiệp vụ thực sự cần trả sự kiện:

~~~java
PurchaseOrderConfirmed event = registerEvent(
        new PurchaseOrderConfirmed(
                UUID.randomUUID(),
                id,
                occurredAt));
~~~

Đây là minh họa thay cho lời gọi đăng ký tương ứng, không phải một lời gọi bổ sung sau `confirm`. Gọi cả hai sẽ tạo thêm sự kiện.

Không viết `return registerEvent(event)` trong một method khai báo trả về `PurchaseOrder`: giá trị trả về ở đây là sự kiện, không phải aggregate.

### 4.2. andEvent phục vụ cách viết trả về aggregate

Nếu muốn `confirm` trả về aggregate, có thể thay method ở trên bằng phương án sau:

~~~java
public PurchaseOrder confirm(Instant occurredAt) {
    Objects.requireNonNull(occurredAt, "occurredAt");

    if (status != PurchaseOrderStatus.DRAFT) {
        throw new IllegalStateException(
                "Only draft orders can be confirmed");
    }

    status = PurchaseOrderStatus.CONFIRMED;

    return andEvent(new PurchaseOrderConfirmed(
            UUID.randomUUID(),
            id,
            occurredAt));
}
~~~

Chỉ chọn một phiên bản `confirm`. Khác biệt là kiểu trả về phục vụ cách sử dụng API; cả hai đều mới đăng ký sự kiện để phát sau.

## 5. Đăng ký chưa phải phát sự kiện

Đoạn mã thuần Java sau chưa đi qua repository:

~~~java
PurchaseOrder order =
        PurchaseOrder.draft(UUID.randomUUID());

order.confirm(Instant.parse("2026-01-15T09:00:00Z"));
~~~

Aggregate lúc này có trạng thái `CONFIRMED` và một sự kiện đang chờ. Lời gọi `registerEvent` không tự gửi email, không gọi broker và không trực tiếp gọi listener trong Spring context.

Đường tích hợp repository dùng hai annotation mà lớp cơ sở đã cung cấp:

- `@DomainEvents` cho hạ tầng lấy sự kiện.
- `@AfterDomainEventPublication` cho bước xử lý sau publication, thường là dọn danh sách.

Tài liệu Commons mô tả cơ chế này cho các method như `save`, `saveAll` và một số method xóa nhận aggregate. `deleteById` không nằm trong cùng bảo đảm vì đường thực thi có thể không có instance aggregate. Xem [Publishing Events from Aggregate Roots](https://docs.spring.io/spring-data/commons/reference/repositories/core-domain-events.html).

Khi kế thừa `AbstractAggregateRoot`, không cần tự khai báo lại hai hook chỉ để có hành vi mặc định.

## 6. Lưu qua repository trong một service

Repository cụ thể cho ví dụ JPA:

~~~java
package com.example.orders;

import java.util.UUID;

import org.springframework.data.jpa.repository.JpaRepository;

public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, UUID> {
}
~~~

Service điều phối một đơn nháp đã được lưu trước đó:

~~~java
package com.example.orders;

import java.time.Clock;
import java.util.UUID;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PurchaseOrderService {

    private final PurchaseOrderRepository repository;
    private final Clock clock;

    public PurchaseOrderService(
            PurchaseOrderRepository repository,
            Clock clock) {
        this.repository = repository;
        this.clock = clock;
    }

    @Transactional
    public UUID confirm(UUID id) {
        PurchaseOrder order = repository.findById(id)
                .orElseThrow(() ->
                        new IllegalArgumentException(
                                "Order not found"));

        order.confirm(clock.instant());

        PurchaseOrder saved = repository.save(order);

        return saved.getId();
    }
}
~~~

Ứng dụng cần cung cấp bean `Clock`, chẳng hạn `Clock.systemUTC()`, đồng thời cấu hình JPA và transaction. `Clock` không tự xuất hiện chỉ vì constructor yêu cầu nó.

Service phải được gọi qua cơ chế proxy transaction của Spring để có ranh giới transaction như mong muốn.

Điểm đáng chú ý là lời gọi `repository.save(order)`. Trong JPA, dirty checking có thể ghi trạng thái entity managed mà không cần gọi lại `save`. Tuy nhiên, việc ghi trạng thái đó không tự thay thế điểm tích hợp phát domain event của repository.

Service sử dụng instance trả về từ `save`, phù hợp với việc một đường lưu có thể trả instance khác. Không coi mọi reference của cùng một id là cùng một object có chung danh sách sự kiện.

Ví dụ này cũng không chứng minh cùng vòng đời cho repository reactive. Với API reactive, cần kiểm tra khả năng hỗ trợ của store và thời điểm thực thi theo subscription.

## 7. Vòng đời publication và việc dọn danh sách

Với service có transaction bên ngoài và đường repository đồng bộ ở trên, có thể đọc luồng theo thứ tự:

~~~text
Service bắt đầu transaction
    -> tải đơn nháp
    -> confirm: đổi trạng thái, đăng ký sự kiện
    -> gọi repository.save
        -> thực hiện phần lưu
        -> chuyển sự kiện cho ApplicationEventPublisher
        -> dọn các sự kiện đã publication theo hook
    -> service hoàn tất
Transaction commit hoặc rollback
~~~

Ở triển khai interceptor được tham chiếu, repository thực hiện lời gọi lưu trước rồi mới lấy sự kiện từ các aggregate truyền vào để publication. Đây chưa phải xác nhận transaction đã commit. Xem [EventPublishingRepositoryProxyPostProcessor](https://github.com/spring-projects/spring-data-commons/blob/main/src/main/java/org/springframework/data/repository/core/support/EventPublishingRepositoryProxyPostProcessor.java).

Danh sách chờ của lớp cơ sở nằm trong bộ nhớ. `domainEvents()` cung cấp một view không cho sửa trực tiếp; `clearDomainEvents()` làm rỗng danh sách. Hook dọn chạy sau bước publication, không mang ý nghĩa “đã lưu bền vững vào một kho sự kiện”. Xem [AbstractAggregateRoot implementation](https://github.com/spring-projects/spring-data-commons/blob/main/src/main/java/org/springframework/data/domain/AbstractAggregateRoot.java).

Các hệ quả khi thiết kế ứng dụng:

- Sau publication bình thường, lưu lại cùng object mà không có hành vi mới không nên phát lại danh sách cũ.
- Không gọi `clearDomainEvents()` từ service trước khi repository lấy sự kiện.
- Việc danh sách đã rỗng không chứng minh một consumer bên ngoài đã xử lý thành công.

Nếu tùy biến việc đọc hoặc dọn sự kiện, cần giữ đúng hợp đồng của cả hai hook. Một getter có tác dụng phụ, chẳng hạn xóa danh sách ngay khi đọc, khiến vòng đời khó kiểm soát.

## 8. andEventsFrom: giữ sự kiện khi thay thế instance

`andEventsFrom` hữu ích khi một cách thiết kế trả về instance aggregate mới thay cho instance cũ. Một bước chuyển tiếp có thể cần giữ cả các sự kiện đang chờ trên instance cũ:

~~~java
// Bên trong aggregate có thiết kế tạo instance thay thế:
return replacement.andEventsFrom(this);
~~~

Đoạn này chỉ minh họa việc chuyển tiếp danh sách sự kiện; nó không phải phần cần thêm vào entity JPA mutable ở ví dụ trước.

Những điều cần giữ rõ:

1. Tham số có cùng kiểu aggregate theo generic; method không nhận tùy ý mọi loại aggregate.
2. Nó thêm sự kiện vào bên nhận, không sao chép trạng thái nghiệp vụ hay kiểm tra hai id có tương ứng không.
3. Nó không xóa danh sách bên nguồn và không tự loại sự kiện trùng.
4. Việc thêm là theo các object sự kiện hiện có, không phải tạo bản sao sâu của payload.

Chẳng hạn, nếu `replacement` đại diện cùng đơn hàng theo mô hình bất biến, việc mang theo sự kiện chờ có thể cần thiết. Nhưng truyền một đơn khác chỉ vì cùng class sẽ trộn hai luồng nghiệp vụ nếu không có quy tắc kiểm soát.

Nếu cả instance nguồn và instance thay thế cùng được lưu và đều còn sự kiện, cần xét nguy cơ publication lặp. Lớp cơ sở không cung cấp cơ chế khử trùng theo `eventId`.

## 9. Listener thường và listener theo transaction

### 9.1. Quan sát publication bằng EventListener

Một listener đơn giản trong Spring context:

~~~java
package com.example.orders;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class PurchaseOrderObserver {

    private static final Logger log =
            LoggerFactory.getLogger(
                    PurchaseOrderObserver.class);

    @EventListener
    public void on(PurchaseOrderConfirmed event) {
        log.info(
                "Observed order confirmation: orderId={}, eventId={}",
                event.orderId(),
                event.eventId());
    }
}
~~~

Với multicaster mặc định và listener đồng bộ, listener được gọi trên thread publication. Exception có thể truyền ngược ra publisher; cấu hình executor hoặc error handler có thể thay đổi hành vi đó. Xem [SimpleApplicationEventMulticaster](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html).

Một dòng log tại đây thể hiện đã quan sát sự kiện. Nó không đủ để khẳng định transaction lưu đơn đã commit.

Đừng để listener đồng bộ thực hiện công việc chậm mà chưa xem tác động đến thời gian phản hồi. Nếu chuyển sang bất đồng bộ, cần thiết kế riêng việc xử lý lỗi và ngữ cảnh thực thi.

### 9.2. Xử lý khi transaction đã commit

Nếu tác vụ chỉ có ý nghĩa sau commit, có thể chọn listener gắn với transaction:

~~~java
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT)
public void onCommitted(
        PurchaseOrderConfirmed event) {
    log.info(
            "Committed order confirmation: orderId={}",
            event.orderId());
}
~~~

Snippet này dùng các import:

~~~java
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
~~~

Method được đặt trong một Spring bean có logger tương ứng. `AFTER_COMMIT` cũng là phase mặc định. Nếu không có transaction tại thời điểm publication, listener không chạy theo cấu hình mặc định; `fallbackExecution` là một lựa chọn làm thay đổi quy tắc đó. Xem [Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html).

Trong ví dụ, transaction được bao quanh ở service để làm rõ thời điểm publication. Không suy từ việc có một method tên `save` rằng mọi listener theo transaction đều chắc chắn chạy.

Listener sau commit bị lỗi không thể làm transaction đã commit quay lại trạng thái chưa commit. Nếu cần giao tiếp tin cậy với hệ thống khác, phải thiết kế thêm cơ chế lưu và gửi lại thông điệp.

## 10. Các ranh giới dễ bị bỏ sót

### 10.1. Sự kiện gắn với instance đã thực hiện hành vi

Danh sách chờ thuộc object aggregate. Nếu gọi `confirm` trên object A rồi chỉ lưu một object B có cùng id, không được mặc định B có các sự kiện của A.

Một DTO được map thành entity mới cũng không tự mang theo các sự kiện đã đăng ký trên entity khác.

Không sửa vấn đề bằng cách công khai danh sách cho controller sao chép tùy ý. Hãy làm rõ đối tượng nào thực hiện hành vi và đối tượng nào được chuyển cho đường lưu.

### 10.2. Đọc dữ liệu không phải tái thực hiện hành vi

Không đăng ký `PurchaseOrderConfirmed` trong getter hoặc trong quá trình khôi phục entity chỉ vì thấy trạng thái là `CONFIRMED`. Tải lại một đơn đã xác nhận không có nghĩa vừa phát sinh một lần xác nhận mới.

Tương tự, không tạo sự kiện nghiệp vụ trong setter được mapper gọi cho mọi lần bind dữ liệu mà chưa phân biệt mục đích thao tác.

### 10.3. Cập nhật trực tiếp không gọi phương thức domain

Một câu SQL hoặc JPQL update trạng thái không thực hiện `order.confirm(...)`. Nó không tạo sự kiện chỉ vì class kế thừa `AbstractAggregateRoot`.

Một đường custom repository cũng cần được đánh giá theo cách thực thi thực tế. Không dựa vào tên folder hoặc interface để kết luận mọi update đều phát cùng sự kiện.

### 10.4. Sự kiện ở entity con cần được điều phối qua root

Nếu dòng hàng tạo một thông tin nghiệp vụ cần công bố, aggregate root phải chủ động ghi nhận hoặc điều phối nó theo thiết kế. Không giả định repository tự duyệt toàn bộ object graph để lấy mọi danh sách sự kiện của các entity con.

### 10.5. Xóa theo id và xóa có aggregate là hai tình huống khác nhau

Nếu nghiệp vụ cần sự kiện hủy đơn, hãy thực hiện hành vi hủy theo hợp đồng domain rồi dùng đường lưu phù hợp. Một method xóa chỉ nhận id không tự thể hiện các điều kiện hủy và dữ liệu payload cần thiết.

Không đồng nhất mọi thao tác xóa dữ liệu với một sự kiện nghiệp vụ có cùng ý nghĩa.

## 11. Lỗi, retry và độ bền của sự kiện

Một publication thất bại giữa chừng có thể để lại kết quả không đồng đều: listener trước đã chạy, listener sau chưa chạy. Không coi danh sách chờ là một hàng đợi có cơ chế retry và xác nhận từng consumer.

Nếu transaction rollback sau khi publication bình thường đã dọn danh sách, Java object cũng không tự phục hồi danh sách sự kiện theo rollback. Khi thiết kế retry, nên khôi phục lại trạng thái nghiệp vụ và thực hiện command theo một chính sách rõ ràng, thay vì mặc định object cũ vẫn giữ mọi thứ cần phát lại.

`eventId` là dữ liệu hỗ trợ nhận diện, chưa phải cơ chế chống trùng. Đặc biệt, một lần thực hiện lại command có thể tạo `eventId` khác; nếu cần idempotency ở cấp yêu cầu nghiệp vụ, phải xác định khóa và nơi lưu kết quả cho cấp đó.

Với yêu cầu giao tiếp bền vững ra ngoài tiến trình, một thiết kế outbox thường tách thành:

~~~text
Transaction nghiệp vụ
    -> lưu thay đổi aggregate
    -> lưu ý định gửi sự kiện vào outbox

Bộ gửi riêng
    -> đọc outbox
    -> gửi thông điệp
    -> cập nhật trạng thái, retry theo chính sách
~~~

Tính nguyên tử giữa thay đổi nghiệp vụ và outbox phải được triển khai bằng transaction phù hợp. `AbstractAggregateRoot` không tự tạo bảng outbox, lưu log sự kiện hay cấu hình broker.

Listener `AFTER_COMMIT` cũng không tự bảo đảm có thể gửi lại sau khi tiến trình dừng. Hãy chọn mức bảo đảm theo yêu cầu, thay vì suy từ từ “event” rằng đã có hạ tầng truyền thông tin cậy.

## 12. Kiểm tra hành vi domain bằng một phép kiểm tra có ý nghĩa

Có thể kiểm tra chuyển trạng thái và payload mà không khởi động Spring hoặc database. Test dùng subclass chỉ trong kiểm tra để đọc các sự kiện chờ:

~~~java
package com.example.orders;

import static org.junit.jupiter.api.Assertions.*;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

import org.junit.jupiter.api.Test;

class PurchaseOrderTest {

    static class InspectableOrder extends PurchaseOrder {

        InspectableOrder(UUID id) {
            super(id);
        }

        List<Object> pendingEvents() {
            return List.copyOf(domainEvents());
        }
    }

    @Test
    void confirmationRegistersSnapshotAndRejectsSecondConfirmation() {
        UUID orderId = UUID.randomUUID();
        Instant at = Instant.parse("2026-01-15T09:00:00Z");
        InspectableOrder order =
                new InspectableOrder(orderId);

        order.confirm(at);

        assertEquals(
                PurchaseOrderStatus.CONFIRMED,
                order.getStatus());
        assertEquals(1, order.pendingEvents().size());

        PurchaseOrderConfirmed event = assertInstanceOf(
                PurchaseOrderConfirmed.class,
                order.pendingEvents().get(0));

        assertNotNull(event.eventId());
        assertEquals(orderId, event.orderId());
        assertEquals(at, event.occurredAt());

        assertThrows(
                IllegalStateException.class,
                () -> order.confirm(at.plusSeconds(1)));

        assertEquals(1, order.pendingEvents().size());
    }
}
~~~

Phép kiểm tra này xác minh một điều kiện nghiệp vụ, dữ liệu snapshot và việc không thêm sự kiện khi lệnh thứ hai bị từ chối. Nó chưa chứng minh repository phát sự kiện, listener được đăng ký hay transaction commit thành công.

Subclass quan sát chỉ dành cho kiểm tra thuần Java; không cần biến nó thành entity JPA của ứng dụng.

## 13. Kiểm tra tích hợp repository riêng

Dùng repository thật được Spring tạo proxy, cùng listener ghi nhận sự kiện trong môi trường kiểm tra.

| Tình huống | Điều cần xác minh |
| --- | --- |
| Chỉ gọi `confirm` trên object thuần Java | Có sự kiện chờ; chưa có publication qua repository |
| Lưu aggregate có sự kiện | Listener phù hợp nhận đúng payload |
| Lưu lại cùng object sau publication bình thường, không có hành vi mới | Không phát lại danh sách cũ |
| Hành vi bị từ chối | Không phát sinh sự kiện xác nhận mới |
| Commit transaction bao quanh service | Listener `AFTER_COMMIT` chạy theo phase |
| Rollback transaction bao quanh service | Listener `AFTER_COMMIT` không chạy |
| Cập nhật trạng thái bằng query trực tiếp | Không mặc định phát sự kiện từ phương thức `confirm` |
| Lưu các aggregate khác nhau | Payload giữ đúng id của từng aggregate |

Mock repository chỉ xác nhận rằng service có gọi `save`; nó không thay thế hạ tầng publication thực tế.

Trong Spring TestContext, test có transaction thường rollback mặc định. Để kiểm tra `AFTER_COMMIT`, cần chủ động cho transaction hoàn tất bằng commit, chẳng hạn qua `TestTransaction`, rồi mới kiểm tra kết quả sau commit. Xem [Spring Framework: Testing Transactions](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html).

Khi listener kiểm tra giữ danh sách các sự kiện, làm sạch dữ liệu ghi nhận giữa các test. Nếu có xử lý bất đồng bộ, cần cơ chế chờ có điều kiện và thời hạn phù hợp; việc gọi `save` xong chưa đồng nghĩa công việc bất đồng bộ đã hoàn tất.

## 14. Bài thực hành

Hoàn thiện luồng xác nhận đơn hàng:

1. Tạo payload bất biến với id sự kiện, id đơn và thời điểm nghiệp vụ.
2. Cho root kế thừa `AbstractAggregateRoot` với đúng tham số kiểu.
3. Đặt validation, chuyển trạng thái và đăng ký sự kiện trong cùng phương thức nghiệp vụ.
4. Điều phối tải, thực hiện hành vi và lưu qua repository trong service.
5. Quan sát riêng listener thường và listener sau commit.
6. Kiểm tra một lần chuyển trạng thái hợp lệ và một lần bị từ chối.
7. Kiểm tra lưu lần hai không có hành vi mới để hiểu việc dọn danh sách.
8. Giải thích cách xử lý nếu cần giao sự kiện sang hệ thống khác một cách bền vững.

Bài thực hành đạt yêu cầu khi bạn phân biệt được **sự kiện đang chờ trên object**, **publication qua repository**, **kết quả transaction** và **mức bảo đảm của bên nhận**, đồng thời chỉ ra được thành phần chịu trách nhiệm cho từng bước.
