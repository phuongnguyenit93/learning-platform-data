# Sử dụng AbstractAggregateRoot khi phù hợp với mô hình nghiệp vụ

Trong Spring Data, AbstractAggregateRoot là lớp tiện ích giúp một aggregate root ghi nhận các **domain event** phát sinh từ hành vi nghiệp vụ. Khi aggregate được lưu thông qua Spring Data repository, các event đã đăng ký có thể được Spring Data phát hành thành application event trong Spring ApplicationContext.

Ví dụ: khi khách hàng đặt hàng, aggregate PurchaseOrder chuyển sang trạng thái đã đặt và ghi nhận sự kiện OrderPlaced. Một thành phần khác có thể lắng nghe sự kiện đó để gửi thông báo, cập nhật một read model hoặc khởi động một quy trình tiếp theo.

Không phải entity nào cũng cần kế thừa AbstractAggregateRoot. Chỉ nên dùng khi mô hình có ranh giới aggregate rõ ràng và các thay đổi của aggregate tạo ra sự kiện có ý nghĩa nghiệp vụ. Lớp này hỗ trợ đăng ký và phát hành event trong ứng dụng; nó không tự định nghĩa nghiệp vụ, không thay thế transaction và không cung cấp hàng đợi bền vững như message broker.

## 1. Aggregate root và domain event

### 1.1. Aggregate root là gì?

Trong Domain-Driven Design (DDD), aggregate là một nhóm đối tượng domain được xem như một đơn vị nhất quán. Aggregate root là đối tượng bên ngoài dùng để truy cập và thay đổi trạng thái của nhóm đó. Các invariant của aggregate được bảo vệ thông qua hành vi của root.

Ví dụ, một PurchaseOrder có thể chứa các OrderLine. Mã nghiệp vụ nên yêu cầu PurchaseOrder thêm sản phẩm, xác nhận đơn hoặc hủy đơn; không nên để nhiều thành phần tùy ý sửa từng OrderLine khiến tổng tiền, số lượng và trạng thái đơn hàng mất nhất quán.

### 1.2. Domain event là gì?

Domain event mô tả một sự việc đã xảy ra trong miền nghiệp vụ và có ý nghĩa đối với các thành phần khác. Tên event thường diễn đạt ở thì quá khứ, chẳng hạn OrderPlaced, OrderConfirmed, PaymentReceived hoặc OrderCancelled.

Một domain event hữu ích khi nó ghi lại một sự kiện nghiệp vụ mà thành phần khác cần phản ứng. Nó không nên chỉ là bản sao của một thao tác kỹ thuật như RepositorySaved hay EntityUpdated.

Event nên chứa dữ liệu tối thiểu để người nhận hiểu điều gì đã xảy ra, thường là ID aggregate, thời điểm xảy ra và các giá trị nghiệp vụ cần thiết. Ưu tiên event bất biến để người nhận không vô tình sửa dữ liệu mà thành phần phát hành đang sử dụng.

Ví dụ event dưới đây dùng Java record:

~~~java
import java.time.Instant;
import java.util.UUID;

public record OrderPlaced(UUID orderId, Instant occurredAt) {}
~~~

Record phù hợp với event vì các thành phần của record là final và giá trị được truyền qua constructor. Trong dự án, có thể đặt mỗi public record trong một file riêng theo quy tắc Java.

## 2. AbstractAggregateRoot hỗ trợ điều gì?

Lớp org.springframework.data.domain.AbstractAggregateRoot thuộc Spring Data Commons, được Spring Data JPA sử dụng như một tiện ích chung của hệ sinh thái Spring Data. Lớp này giúp aggregate root quản lý danh sách domain event mà nó đã đăng ký.

Các hành vi chính:

- **registerEvent(event):** đăng ký một event khi hành vi nghiệp vụ tương ứng xảy ra. Phương thức trả lại chính event đã truyền vào để có thể kết hợp trong biểu thức nếu cần.
- **domainEvents():** cung cấp các event đã đăng ký cho cơ chế phát hành của Spring Data. Phương thức này được đánh dấu bằng @DomainEvents trong lớp cơ sở.
- **clearDomainEvents():** xóa các event sau khi phát hành. Phương thức này được đánh dấu bằng @AfterDomainEventPublication.
- **andEvent(...)** và **andEventsFrom(...)**: các phương thức tiện ích hỗ trợ đăng ký một event hoặc nhận event từ aggregate khác trong những trường hợp phù hợp với API của phiên bản đang dùng.

Khi kế thừa lớp này, entity không phải tự cài đặt danh sách event và hai annotation publication/cleanup. Aggregate chỉ cần gọi registerEvent(...) tại thời điểm một hành vi nghiệp vụ hợp lệ hoàn tất.

Spring Data kiểm tra các aggregate root được truyền vào một số repository operation như save(...), saveAll(...) và các thao tác delete được hỗ trợ để tìm và phát hành domain event. Danh sách method cụ thể có thể phụ thuộc phiên bản Spring Data; hãy kiểm tra tài liệu của phiên bản dự án nếu dựa vào một biến thể delete đặc biệt. Các thao tác cập nhật bulk bằng JPQL hoặc SQL trực tiếp không tự động đi qua quy trình lưu aggregate root như vậy.

## 3. Ví dụ: aggregate tự đăng ký domain event

Giả sử ứng dụng quản lý đơn hàng. Khi tạo đơn, aggregate chuyển sang trạng thái PLACED và đăng ký OrderPlaced. ID được tạo bằng UUID trong ứng dụng để event có thể chứa ID ngay cả trước khi entity được lưu.

~~~java
import java.time.Instant;
import java.util.UUID;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import org.springframework.data.domain.AbstractAggregateRoot;

@Entity
public class PurchaseOrder extends AbstractAggregateRoot<PurchaseOrder> {
    @Id
    private UUID id;

    private String status;

    protected PurchaseOrder() {
    }

    private PurchaseOrder(UUID id) {
        this.id = id;
        this.status = "PLACED";
    }

    public static PurchaseOrder place() {
        PurchaseOrder order = new PurchaseOrder(UUID.randomUUID());
        order.registerEvent(new OrderPlaced(order.id, Instant.now()));
        return order;
    }

    public void confirm() {
        if (!"PLACED".equals(status)) {
            throw new IllegalStateException("Only a placed order can be confirmed");
        }

        status = "CONFIRMED";
        registerEvent(new OrderConfirmed(id, Instant.now()));
    }

    public UUID getId() {
        return id;
    }
}
~~~

Event xác nhận đơn hàng có thể được định nghĩa như sau:

~~~java
import java.time.Instant;
import java.util.UUID;

public record OrderConfirmed(UUID orderId, Instant occurredAt) {}
~~~

Trong ví dụ, registerEvent(...) chỉ được gọi sau khi trạng thái đã chuyển hợp lệ. Nếu điều kiện xác nhận không thỏa mãn, phương thức ném exception và không đăng ký OrderConfirmed. Cách tổ chức này giữ cho event phản ánh một thay đổi nghiệp vụ đã được aggregate chấp nhận.

ID UUID được tạo trước khi lưu để event có thể tham chiếu aggregate ngay. Nếu dùng ID database sinh sau insert, không nên tạo event với ID đang null. Có thể chọn ID do ứng dụng cấp, hoặc thiết kế thời điểm tạo event và dữ liệu event phù hợp với chiến lược ID của dự án.

## 4. Phát hành event qua Spring Data repository

Khai báo repository thông thường:

~~~java
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, UUID> {
}
~~~

Service tạo đơn và lưu aggregate:

~~~java
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PurchaseOrderService {
    private final PurchaseOrderRepository orders;

    public PurchaseOrderService(PurchaseOrderRepository orders) {
        this.orders = orders;
    }

    @Transactional
    public UUID placeOrder() {
        PurchaseOrder order = PurchaseOrder.place();
        orders.save(order);
        return order.getId();
    }

    @Transactional
    public void confirmOrder(UUID id) {
        PurchaseOrder order = orders.findById(id).orElseThrow();
        order.confirm();
        orders.save(order);
    }
}
~~~

Khi gọi orders.save(order), Spring Data có thể lấy các event từ aggregate root và phát hành chúng qua cơ chế application event. Sau khi phát hành, callback clearDomainEvents() xóa danh sách event đã đăng ký để chúng không bị phát lại ở lần repository operation tiếp theo.

Trong confirmOrder, entity được tải trong transaction và đang được persistence context quản lý. Dirty checking có thể ghi thay đổi trạng thái khi transaction flush hoặc commit. Gọi save(order) ở đây giúp minh họa thời điểm Spring Data kiểm tra domain events; với entity đã managed, JPA không bắt buộc phải gọi save() lần nữa chỉ để dirty checking hoạt động. Nếu muốn dựa vào repository event publication, cần bảo đảm aggregate root được truyền vào operation có hỗ trợ publication.

## 5. Lắng nghe domain event

Vì domain event được phát hành thành Spring application event, một bean có thể lắng nghe bằng @EventListener hoặc @TransactionalEventListener.

Ví dụ lắng nghe sau khi transaction commit:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class OrderEventHandler {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void on(OrderPlaced event) {
        System.out.println("Order placed: " + event.orderId());
    }
}
~~~

@TransactionalEventListener cho phép gắn thời điểm xử lý event với vòng đời transaction. Các phase thường dùng gồm:

- **BEFORE_COMMIT:** xử lý trước khi transaction commit.
- **AFTER_COMMIT:** xử lý sau khi transaction commit thành công.
- **AFTER_ROLLBACK:** xử lý sau khi transaction rollback.
- **AFTER_COMPLETION:** xử lý sau khi transaction hoàn tất, bất kể commit hay rollback.

Với AFTER_COMMIT, nếu transaction rollback thì listener không chạy theo phase này. Đây thường là lựa chọn phù hợp cho tác vụ chỉ nên bắt đầu khi dữ liệu nghiệp vụ đã commit, chẳng hạn gửi thông báo hoặc kích hoạt xử lý tiếp theo.

Khác với @TransactionalEventListener, @EventListener thông thường xử lý event ngay khi event được phát hành. Trong luồng save() nằm bên trong service transaction, thời điểm phát hành thường xảy ra trước khi transaction bên ngoài commit. Nếu listener gửi thông báo ra hệ thống khác ngay lúc đó, hệ thống nhận có thể thấy thông báo dù transaction sau đó rollback. Hãy chọn phase theo yêu cầu nhất quán.

Nếu listener sau commit cần ghi dữ liệu vào database, hãy tạo transaction mới một cách có chủ đích, thường qua một service bean khác với propagation REQUIRES_NEW. Tại thời điểm AFTER_COMMIT, transaction gốc đã hoàn tất; không nên giả định thao tác ghi trong listener sẽ được commit như một phần của transaction cũ.

## 6. Thời điểm phát hành và giới hạn đảm bảo

Có ba thời điểm cần phân biệt:

1. **Đăng ký event:** hành vi nghiệp vụ gọi registerEvent(...) và aggregate giữ event trong bộ nhớ.
2. **Phát hành application event:** Spring Data repository operation phát hành event khi xử lý aggregate root.
3. **Commit transaction:** transaction manager xác nhận các thay đổi dữ liệu trong database.

Phát hành application event không đồng nghĩa với database đã commit. Khi service có @Transactional, repository save() thường được gọi bên trong transaction đó. Spring Data phát hành event trong quá trình thực thi repository method, trước khi transaction của service hoàn tất. Listener thông thường có thể chạy ở thời điểm này; listener AFTER_COMMIT được trì hoãn đến khi transaction commit.

AbstractAggregateRoot giữ event trong bộ nhớ và xóa danh sách sau callback publication. Nó không ghi event vào một bảng bền vững. Nếu tiến trình dừng đột ngột sau khi dữ liệu commit nhưng trước khi một tác vụ bên ngoài được thực hiện, chỉ dựa vào application event không bảo đảm tác vụ đó sẽ được gửi lại.

Khi cần bảo đảm phát sự kiện ra message broker đáng tin cậy, cân nhắc **Transactional Outbox**: ghi thay đổi aggregate và bản ghi outbox trong cùng transaction database, sau đó một publisher đọc outbox và gửi message, có cơ chế retry cùng idempotency. AbstractAggregateRoot có thể giúp phát hiện sự kiện nghiệp vụ ở trong ứng dụng, nhưng bản thân nó không phải outbox.

## 7. Khi nào nên dùng AbstractAggregateRoot?

Nên cân nhắc dùng khi:

- Entity thực sự là aggregate root và kiểm soát các thay đổi nghiệp vụ của một aggregate.
- Một hành vi nghiệp vụ tạo ra event có ý nghĩa đối với các thành phần khác.
- Ứng dụng lưu aggregate thông qua Spring Data repository và muốn gắn event publication với thao tác repository.
- Event có thể được mô tả độc lập, bất biến và chứa dữ liệu đủ để người nhận xử lý.

Không cần dùng chỉ vì một entity được lưu bằng JPA. Nếu chỉ muốn ghi log, cập nhật một trường kỹ thuật hoặc gọi một hàm nội bộ ngay trong service, một event domain có thể làm mô hình phức tạp không cần thiết.

Có thể không dùng lớp cơ sở này khi:

- Mô hình không có aggregate root rõ ràng hoặc entity không sở hữu hành vi nghiệp vụ.
- Event cần được ghi bền vững, retry, phân phối giữa nhiều service hoặc bảo đảm không mất sau sự cố; khi đó cần outbox hoặc cơ chế message bền vững.
- Thay đổi dữ liệu được thực hiện bằng bulk JPQL/native SQL mà không tải và lưu aggregate root qua repository.
- Dự án cần cơ chế đăng ký event tùy biến hơn; khi đó có thể tự triển khai @DomainEvents và @AfterDomainEventPublication hoặc dùng một domain event dispatcher phù hợp.

## 8. Các lỗi thường gặp

- **Đăng ký event trước khi kiểm tra invariant.** Event có thể mô tả một hành động chưa thực sự được chấp nhận. Hãy kiểm tra điều kiện và cập nhật trạng thái trước khi đăng ký event.
- **Đưa toàn bộ entity vào event.** Điều này tạo phụ thuộc vào cấu trúc persistence, lazy association và trạng thái mutable. Ưu tiên ID cùng dữ liệu nghiệp vụ cần thiết.
- **Cho rằng event chỉ được phát hành sau commit.** Repository publication và commit là hai thời điểm khác nhau. Dùng @TransactionalEventListener(AFTER_COMMIT) nếu listener chỉ nên chạy sau commit.
- **Cho rằng event đã được lưu bền vững.** AbstractAggregateRoot giữ event trong bộ nhớ. Muốn đảm bảo gửi message sau sự cố, cần outbox hoặc giải pháp bền vững khác.
- **Kỳ vọng bulk update tự phát hành domain event.** JPQL bulk update/delete và SQL trực tiếp không đi qua lifecycle của từng aggregate root như save().
- **Đăng ký event trong setter hoặc callback persistence tùy tiện.** Event nên gắn với hành vi domain có tên và có ý nghĩa, chẳng hạn confirm(), cancel() hoặc place().
- **Dùng một event để thay thế kiểm soát transaction.** Event không tự làm cho nhiều thao tác database nguyên tử. Hãy đặt transaction ở service theo ranh giới nghiệp vụ.
- **Quên rằng danh sách event được xóa sau publication.** Nếu cần thử lại publication hoặc khôi phục event sau rollback, không thể coi danh sách nội bộ của aggregate là kho lưu trữ event.

## 9. Quy trình áp dụng trong dự án

1. Xác định aggregate root và invariant mà root phải bảo vệ.
2. Xác định hành vi nghiệp vụ nào tạo ra sự kiện đáng để thành phần khác phản ứng.
3. Định nghĩa event bất biến, đặt tên ở thì quá khứ và chỉ chứa dữ liệu cần thiết.
4. Cho aggregate root kế thừa AbstractAggregateRoot<AggregateType> và gọi registerEvent(...) sau khi hành vi hợp lệ hoàn tất.
5. Lưu aggregate qua Spring Data repository trong transaction phù hợp.
6. Dùng @TransactionalEventListener với phase thích hợp nếu listener phụ thuộc vào kết quả commit hoặc rollback.
7. Nếu cần gửi sự kiện tin cậy sang hệ thống khác, thiết kế outbox, retry và idempotency thay vì chỉ dựa vào event trong bộ nhớ.
8. Viết integration test để kiểm tra trạng thái aggregate, event publication, callback xóa event và hành vi listener khi commit/rollback.

## 10. Kiểm thử domain event

Có thể kiểm thử event được phát hành bằng ApplicationEvents trong Spring Test hoặc đăng ký một listener test để thu thập event. Ví dụ minh họa dưới đây dùng @RecordApplicationEvents và ApplicationEvents của Spring Test; cần chạy trong Spring test context có repository và transaction manager thật của ứng dụng:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationEvents;
import org.springframework.test.context.event.RecordApplicationEvents;

@SpringBootTest
@RecordApplicationEvents
class PurchaseOrderEventTest {

    @Autowired
    PurchaseOrderService service;

    @Autowired
    ApplicationEvents events;

    @Test
    void publishesOrderPlacedWhenOrderIsSaved() {
        service.placeOrder();

        assertThat(events.stream(OrderPlaced.class)).hasSize(1);
    }
}
~~~

Đây là mẫu kiểm thử tích hợp, không phải chương trình độc lập. Cần dùng phiên bản Spring Test hỗ trợ ApplicationEvents và bảo đảm event được phát hành trong test context. Nếu test chạy trong transaction do framework kiểm thử quản lý và transaction đó chưa commit, listener AFTER_COMMIT có thể chưa được gọi; cần thiết kế test phase commit phù hợp để kiểm chứng listener sau commit.

Ngoài trường hợp thành công, nên kiểm tra các tình huống:

- Hành vi domain thất bại do invariant không hợp lệ thì không đăng ký event.
- Aggregate được lưu và event được phát hành đúng số lần mong đợi.
- Event được xóa khỏi aggregate sau publication, không bị phát lại ngoài ý muốn ở lần save sau.
- Listener AFTER_COMMIT chạy khi commit thành công và không chạy khi transaction rollback.
- Bulk update không phát hành event tự động; nếu nghiệp vụ cần event, phải thiết kế đường phát hành riêng.

AbstractAggregateRoot hữu ích khi domain model có aggregate root thực sự và event phản ánh hành vi nghiệp vụ của root. Hãy dùng nó để kết nối hành vi domain với cơ chế application event của Spring Data, đồng thời chọn rõ thời điểm xử lý và mức độ bảo đảm cần có cho từng event.