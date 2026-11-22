# Dọn sự kiện bằng @AfterDomainEventPublication

Trong Spring Data JPA, một aggregate root có thể ghi nhận các domain event phát sinh trong quá trình thay đổi trạng thái. Spring Data cung cấp `@DomainEvents` để lấy các sự kiện cần phát và `@AfterDomainEventPublication` để gọi một callback sau khi các sự kiện đó đã được publish. Callback thường được dùng để xóa danh sách sự kiện đang chờ, tránh phát lại cùng một sự kiện ở lần gọi repository tiếp theo.

`@AfterDomainEventPublication` thuộc Spring Data Commons (`org.springframework.data.domain`), được Spring Data JPA sử dụng khi làm việc với aggregate root thông qua repository. Annotation này không tự phát sự kiện và cũng không tự quản lý transaction.

> Các đoạn Java trong bài là snippet dành cho dự án Java 17+ với Spring Boot 3+ và `spring-boot-starter-data-jpa`. Chúng minh họa các lớp cần tích hợp vào ứng dụng, không phải chương trình độc lập có thể chạy trực tiếp bằng `javac`/`java`.

## 1. Vai trò của @DomainEvents và @AfterDomainEventPublication

Một aggregate root có thể tạo ra sự kiện khi một hành động nghiệp vụ làm thay đổi trạng thái. Ví dụ, khi đơn hàng chuyển từ `DRAFT` sang `CONFIRMED`, aggregate có thể ghi nhận `OrderConfirmedEvent` để các thành phần khác cập nhật chỉ mục, gửi thông báo hoặc tạo dữ liệu đọc.

Spring Data cung cấp hai annotation phối hợp với nhau:

- `@DomainEvents` đánh dấu phương thức trên aggregate root dùng để trả về một event hoặc một tập hợp event cần publish. Phương thức này không nhận tham số.
- `@AfterDomainEventPublication` đánh dấu callback được gọi sau khi Spring Data đã publish tất cả event lấy được từ aggregate. Callback thường xóa danh sách event đã gửi.

Luồng khái quát:

1. Hành động nghiệp vụ trên aggregate tạo event và thêm vào danh sách chờ.
2. Ứng dụng gọi một phương thức repository được Spring Data hỗ trợ để publish domain event.
3. Spring Data gọi phương thức `@DomainEvents` và publish event dưới dạng Spring application event.
4. Sau khi publish xong tất cả event, Spring Data gọi phương thức `@AfterDomainEventPublication`.
5. Aggregate xóa các event đã publish khỏi danh sách chờ.

Callback cho phép aggregate tự dọn trạng thái event nội bộ. Nếu không xóa danh sách, lần `save()` sau có thể publish lại những event cũ nếu aggregate vẫn còn giữ chúng.

## 2. Cài đặt thủ công trên aggregate root

Ví dụ dưới đây mô tả một đơn hàng có thể chuyển từ trạng thái nháp sang đã xác nhận. Danh sách event là dữ liệu tạm trong bộ nhớ, do đó được đánh dấu `@Transient` để JPA không ánh xạ nó thành cột hoặc quan hệ trong database.

**Event — `OrderConfirmedEvent.java`:**

```java
import java.time.Instant;

public record OrderConfirmedEvent(
        String orderNumber,
        Instant occurredAt) {
}
```

**Aggregate root — `PurchaseOrder.java`:**

```java
import java.time.Instant;
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import java.util.Objects;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Transient;

import org.springframework.data.domain.AfterDomainEventPublication;
import org.springframework.data.domain.DomainEvents;

@Entity
@Table(name = "purchase_order")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String orderNumber;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private OrderStatus status = OrderStatus.DRAFT;

    @Transient
    private final List<Object> pendingEvents = new ArrayList<>();

    protected PurchaseOrder() {
        // JPA cần constructor không tham số.
    }

    public PurchaseOrder(String orderNumber) {
        this.orderNumber = Objects.requireNonNull(orderNumber);
    }

    public void confirm() {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException(
                    "Chỉ đơn hàng ở trạng thái DRAFT mới được xác nhận");
        }

        status = OrderStatus.CONFIRMED;
        pendingEvents.add(
                new OrderConfirmedEvent(orderNumber, Instant.now()));
    }

    @DomainEvents
    public Collection<Object> domainEvents() {
        return List.copyOf(pendingEvents);
    }

    @AfterDomainEventPublication
    public void clearDomainEvents() {
        pendingEvents.clear();
    }

    public Long getId() {
        return id;
    }

    public String getOrderNumber() {
        return orderNumber;
    }

    public OrderStatus getStatus() {
        return status;
    }
}
```

**Enum — `OrderStatus.java`:**

```java
public enum OrderStatus {
    DRAFT,
    CONFIRMED
}
```

Trong ví dụ:

- `confirm()` kiểm tra điều kiện nghiệp vụ, thay đổi trạng thái rồi ghi nhận một event.
- `domainEvents()` trả về bản sao không thể sửa của danh sách event. Spring Data đọc danh sách này để publish.
- `clearDomainEvents()` được đánh dấu `@AfterDomainEventPublication` và xóa danh sách sau khi publication hoàn tất.
- `pendingEvents` được đánh dấu `@Transient` vì danh sách này chỉ là hàng đợi event tạm thời trong aggregate.

Dùng `List.copyOf()` giúp bên đọc không thể thay đổi trực tiếp danh sách nội bộ. Nếu ứng dụng cần hỗ trợ một loại event cụ thể, có thể thay `Object` bằng kiểu interface chung như `DomainEvent`.

## 3. Repository kích hoạt việc publish event

Spring Data publish domain event khi gọi các phương thức repository có aggregate root làm đối số. Tài liệu Spring Data JPA liệt kê các phương thức như `save(…)`, `saveAll(…)`, `delete(…)`, `deleteAll(…)`, `deleteAllInBatch(…)` và `deleteInBatch(…)`.

Ví dụ repository:

```java
import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;

public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    Optional<PurchaseOrder> findByOrderNumber(String orderNumber);
}
```

Service thay đổi aggregate và gọi `save()` để Spring Data xử lý event:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PurchaseOrderService {

    private final PurchaseOrderRepository repository;

    public PurchaseOrderService(PurchaseOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void confirmOrder(String orderNumber) {
        PurchaseOrder order = repository.findByOrderNumber(orderNumber)
                .orElseThrow(() ->
                        new IllegalArgumentException("Không tìm thấy đơn hàng"));

        order.confirm();

        // save() kích hoạt cơ chế publish domain event của Spring Data.
        repository.save(order);
    }
}
```

Khi `repository.save(order)` được gọi, Spring Data tìm phương thức `@DomainEvents`, publish event rồi gọi callback `@AfterDomainEventPublication`. Với entity đang được quản lý, JPA vẫn có thể ghi thay đổi bằng dirty checking khi transaction flush/commit; lời gọi `save()` ở đây còn là điểm kích hoạt cơ chế domain event của Spring Data.

### Vì sao deleteById không nằm trong danh sách?

`deleteById(id)` không nhận aggregate root làm đối số. Spring Data có thể thực hiện xóa bằng truy vấn mà không tải instance aggregate về, nên không có object để đọc danh sách event hoặc gọi callback trên object đó. Nếu cần phát domain event gắn với hành vi xóa, hãy tải aggregate, thực hiện hành vi nghiệp vụ phù hợp và gọi phương thức repository nhận aggregate instance.

Với các phương thức xóa theo lô, hãy đọc kỹ overload đang dùng và cân nhắc ngữ nghĩa của bulk delete. Các thao tác bulk có thể bỏ qua callback vòng đời JPA, cascade ở ORM và đồng bộ persistence context theo cách khác với xóa từng entity. Việc hỗ trợ publish domain event của Spring Data repository không làm thay đổi các giới hạn này của bulk DML.

## 4. Dùng AbstractAggregateRoot để giảm mã lặp

Spring Data cung cấp lớp tiện ích `AbstractAggregateRoot` trong package `org.springframework.data.domain`. Lớp này đã cài đặt cơ chế lưu event, expose chúng qua `@DomainEvents` và xóa danh sách bằng callback `@AfterDomainEventPublication`.

Aggregate có thể kế thừa lớp này và gọi `registerEvent()` khi phát sinh sự kiện:

```java
import java.time.Instant;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;

import org.springframework.data.domain.AbstractAggregateRoot;

@Entity
public class Shipment extends AbstractAggregateRoot<Shipment> {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String trackingCode;

    private boolean dispatched;

    protected Shipment() {
    }

    public Shipment(String trackingCode) {
        this.trackingCode = trackingCode;
    }

    public void dispatch() {
        if (dispatched) {
            throw new IllegalStateException("Shipment đã được gửi");
        }

        dispatched = true;
        registerEvent(
                new ShipmentDispatchedEvent(trackingCode, Instant.now()));
    }
}
```

Event tương ứng:

```java
import java.time.Instant;

public record ShipmentDispatchedEvent(
        String trackingCode,
        Instant occurredAt) {
}
```

`registerEvent(event)` thêm event vào danh sách nội bộ và trả về event vừa đăng ký. `andEvent(event)` cũng đăng ký event nhưng trả về aggregate để có thể nối lời gọi. Khi repository publish event, `AbstractAggregateRoot` tự gọi callback xóa danh sách.

Chọn một cách quản lý event phù hợp với mô hình aggregate:

- Cài đặt `@DomainEvents` và `@AfterDomainEventPublication` trực tiếp khi cần tùy biến danh sách event hoặc logic dọn dẹp.
- Kế thừa `AbstractAggregateRoot` khi muốn dùng cơ chế đăng ký và dọn event có sẵn của Spring Data.

Không cần tự tạo thêm một danh sách event song song nếu đã dùng `AbstractAggregateRoot`.

## 5. Thời điểm callback chạy và thời điểm transaction commit

Đây là điểm dễ nhầm nhất: `@AfterDomainEventPublication` được gọi sau khi Spring Data publish các event, **không có nghĩa là transaction cơ sở dữ liệu đã commit**.

Ví dụ trong service có `@Transactional`:

1. Service tải aggregate trong transaction.
2. Aggregate thay đổi trạng thái và đăng ký event.
3. Service gọi repository `save()`.
4. Spring Data publish event và gọi callback dọn danh sách.
5. Sau đó phương thức service mới kết thúc và transaction được commit.

Vì thế, một listener thông thường dùng `@EventListener` có thể xử lý event trong lúc transaction gốc vẫn chưa commit. Nếu transaction rollback sau đó, listener đã chạy có thể đã thực hiện một tác động bên ngoài dù dữ liệu nghiệp vụ không được commit.

Nếu listener chỉ nên chạy khi transaction thành công, dùng `@TransactionalEventListener`:

```java
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class OrderNotificationListener {

    @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderConfirmed(OrderConfirmedEvent event) {
        // Chỉ xử lý sau khi transaction publish event commit thành công.
        System.out.println("Đơn hàng đã xác nhận: " + event.orderNumber());
    }
}
```

`AFTER_COMMIT` là phase mặc định của `@TransactionalEventListener`. Có thể chọn thêm `BEFORE_COMMIT`, `AFTER_ROLLBACK` hoặc `AFTER_COMPLETION` theo mục đích. Nếu không có transaction đang hoạt động, transactional listener mặc định không được gọi; `fallbackExecution = true` có thể thay đổi hành vi đó khi thật sự phù hợp.

Callback dọn event vẫn chạy sau khi Spring Data publish event vào cơ chế application event. Nó không chờ transaction commit và không chứng minh rằng mọi listener đã hoàn thành xử lý. Nếu listener chạy bất đồng bộ, callback cũng không phải tín hiệu xác nhận công việc bất đồng bộ đã kết thúc.

## 6. Dọn danh sách có bảo đảm event được giao bền vững không?

Không. Danh sách event trong aggregate thường chỉ là trạng thái tạm thời trong bộ nhớ. `@AfterDomainEventPublication` giúp không phát lặp event đã publish từ cùng danh sách ở lần save tiếp theo, nhưng không biến event thành dữ liệu lưu trữ bền vững.

Có một tình huống cần chú ý:

- Service đăng ký event và gọi `repository.save()`.
- Spring Data publish event và callback xóa danh sách event.
- Sau đó transaction cơ sở dữ liệu rollback.

Danh sách event trong object đã được dọn, dù dữ liệu chưa commit. Vì vậy, không nên dựa vào danh sách này như một hàng đợi có thể khôi phục sau rollback. Với listener `@TransactionalEventListener(AFTER_COMMIT)`, listener sẽ không xử lý event khi transaction rollback, nhưng bản thân callback dọn danh sách vẫn không phải cơ chế retry.

Nếu cần bảo đảm thông điệp được gửi tới broker hoặc hệ thống bên ngoài ngay cả khi ứng dụng bị dừng giữa lúc commit và gửi thông điệp, hãy cân nhắc Transactional Outbox. Outbox ghi event vào bảng cùng transaction với dữ liệu nghiệp vụ; một tiến trình riêng đọc các bản ghi chưa gửi và phát lại theo chính sách retry. Đây là cơ chế bền vững khác với danh sách event tạm trong aggregate.

Event nên là đối tượng bất biến, mang dữ liệu cần thiết như mã đơn hàng, loại thay đổi và thời điểm xảy ra. Hạn chế đưa trực tiếp entity JPA hoặc proxy lazy vào payload vì listener có thể chạy sau khi persistence context đã đóng.

## 7. Kiểm thử việc publish và dọn event

Có thể kiểm thử bằng integration test có Spring Data repository và một listener ghi nhận event:

1. Tạo aggregate và gọi hành động nghiệp vụ để đăng ký event.
2. Xác nhận phương thức `domainEvents()` trả về event trước khi gọi repository.
3. Gọi `repository.save(aggregate)` trong transaction.
4. Xác nhận listener nhận đúng loại event và đúng payload.
5. Sau publication, xác nhận danh sách event trong aggregate đã rỗng.
6. Gọi `save()` lần nữa mà không đăng ký event mới; không được publish lại event cũ.
7. Kiểm thử riêng transaction rollback: listener `@TransactionalEventListener(AFTER_COMMIT)` không xử lý event khi transaction rollback.

Khi viết test, cần đảm bảo aggregate được truyền vào phương thức repository có hỗ trợ domain event. Chỉ thay đổi entity đang được quản lý rồi kết thúc transaction mà không gọi phương thức repository kích hoạt publication thì không phải là cách kiểm thử cơ chế này.

## 8. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Event được publish lặp lại sau nhiều lần save | Callback không xóa danh sách event | Cài đặt `@AfterDomainEventPublication` để dọn event |
| Callback không chạy | Aggregate không được truyền qua phương thức repository hỗ trợ hoặc method annotation không được phát hiện | Kiểm tra `@DomainEvents`, repository method và cách gọi |
| Event không được publish khi gọi `deleteById()` | Phương thức chỉ nhận ID, không có aggregate instance để đọc event | Tải aggregate và gọi phương thức repository nhận instance nếu nghiệp vụ cần event |
| Listener chạy dù transaction sau đó rollback | Dùng `@EventListener` thông thường trong luồng transaction | Dùng `@TransactionalEventListener(AFTER_COMMIT)` khi chỉ xử lý sau commit |
| Listener không chạy khi không có transaction | Transactional listener yêu cầu transaction theo phase đã chọn | Gọi trong transaction hoặc cân nhắc `fallbackExecution` |
| Event bị mất sau rollback và retry | Callback đã xóa danh sách sau publication, danh sách không phải outbox bền vững | Đăng ký lại event theo nghiệp vụ hoặc dùng Transactional Outbox |
| Listener nhận entity detached hoặc lỗi lazy loading | Payload chứa entity/proxy thay vì dữ liệu event độc lập | Dùng event bất biến với ID hoặc dữ liệu cần thiết |
| Nghĩ callback chạy sau khi listener bất đồng bộ hoàn tất | Nhầm publication với hoàn tất xử lý | Quản lý xác nhận và retry riêng cho consumer bất đồng bộ |

## 9. Checklist triển khai

- Aggregate đăng ký event đúng lúc trạng thái nghiệp vụ thay đổi.
- Phương thức `@DomainEvents` không nhận tham số và trả về event hoặc collection event.
- Danh sách event tạm không bị JPA ánh xạ thành dữ liệu persistent.
- Callback `@AfterDomainEventPublication` xóa đúng các event đã publish.
- Service gọi repository method hỗ trợ publication như `save()` hoặc `saveAll()`.
- Listener chỉ cần chạy sau commit được đánh dấu `@TransactionalEventListener` với phase phù hợp.
- Không xem callback dọn event là bằng chứng transaction đã commit hoặc event đã được xử lý bền vững.
- Với tích hợp cần giao nhận đáng tin cậy, đánh giá Transactional Outbox và chính sách retry/idempotency.
- Integration test xác nhận publication, cleanup, không phát lặp và hành vi khi rollback.

`@AfterDomainEventPublication` là điểm mở rộng nhỏ nhưng quan trọng trong vòng đời domain event của Spring Data. Dùng callback để dọn danh sách event sau publication, dùng `@TransactionalEventListener` khi cần gắn xử lý với kết quả transaction, và dùng Outbox khi cần độ tin cậy bền vững cho thông điệp tích hợp.

## Tài liệu tham khảo

- [Spring Data JPA — Publishing Events from Aggregate Roots](https://docs.spring.io/spring-data/jpa/reference/4.0/repositories/core-domain-events.html)
- [Spring Data Commons — AfterDomainEventPublication API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/AfterDomainEventPublication.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Data Commons — AbstractAggregateRoot source](https://github.com/spring-projects/spring-data-commons/blob/main/src/main/java/org/springframework/data/domain/AbstractAggregateRoot.java)