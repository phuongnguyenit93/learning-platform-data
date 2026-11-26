# @AfterDomainEventPublication và dọn danh sách sau phát hành

## 1. Vì sao aggregate cần dọn danh sách sự kiện?

Một đơn hàng chuyển từ trạng thái nháp sang đã xác nhận và ghi nhận sự kiện `OrderConfirmed`. Khi ứng dụng lưu đơn hàng qua repository, hạ tầng phát sự kiện ấy cho các listener. Nếu instance đơn hàng vẫn giữ sự kiện trong danh sách chờ, lần lưu sau có thể công bố lại cùng một sự kiện dù không có lần xác nhận mới.

`@AfterDomainEventPublication` đánh dấu phương thức trên aggregate để được gọi sau khi các sự kiện của aggregate được phát hành. Một mục đích trực tiếp là dọn danh sách sự kiện đã công bố. [API AfterDomainEventPublication](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/AfterDomainEventPublication.html).

Bài thuộc chương **Sự kiện aggregate** của module **SPRING_DATA_COMMONS**. Trọng tâm là vòng đời danh sách chờ trong một instance aggregate: ghi nhận, cung cấp cho hạ tầng, phát hành và dọn. Sau bài học, bạn cần phân biệt được việc dọn danh sách với transaction commit, xử lý listener và lưu lịch sử sự kiện.

Tình huống mong muốn:

```text
Xác nhận đơn hàng
  -> pendingEvents = [OrderConfirmed]
Lưu lần thứ nhất
  -> phát OrderConfirmed
  -> dọn pendingEvents
Lưu lần thứ hai, không có thay đổi nghiệp vụ mới
  -> không phát lại OrderConfirmed từ danh sách cũ
```

## 2. Hai annotation phối hợp như thế nào?

`@DomainEvents` đặt trên phương thức không nhận tham số, trả một sự kiện hoặc collection sự kiện. `@AfterDomainEventPublication` đặt trên phương thức được gọi sau lượt phát hành để thực hiện công việc như dọn danh sách. Đây là hai điểm mở rộng trên aggregate root. [Spring Data Commons: Publishing Events from Aggregate Roots](https://docs.spring.io/spring-data/commons/reference/repositories/core-domain-events.html).

Một thiết kế dễ hiểu dùng hai phương thức riêng:

```java
@DomainEvents
Collection<Object> domainEvents() {
    return List.copyOf(pendingEvents);
}

@AfterDomainEventPublication
void clearPendingEvents() {
    pendingEvents.clear();
}
```

Trong thiết kế này:

- `domainEvents()` chỉ cung cấp ảnh chụp các sự kiện đang chờ.
- `clearPendingEvents()` thay đổi hàng đợi sau lượt phát hành.
- Callback không nhận event hay transaction làm tham số.
- Callback không cần trả về một aggregate mới; việc dọn tác động lên danh sách mà instance đang giữ.

Đặt callback trong aggregate quản lý danh sách. Không chuyển annotation sang một Spring listener rồi kỳ vọng hạ tầng tìm và dọn danh sách của aggregate từ listener ấy.

Nên giữ một phương thức cung cấp sự kiện và một phương thức dọn rõ ràng cho mỗi thiết kế aggregate, tránh nhiều callback có cùng nhiệm vụ hoặc dựa vào thứ tự quét phương thức.

## 3. Ví dụ đầy đủ: đơn hàng có hàng đợi trong bộ nhớ

Ví dụ dùng Java 17 và Spring Data MongoDB đồng bộ có phiên bản tương thích. Mỗi public type đặt trong tệp Java riêng, cùng package `example.orders`; các đoạn mã lược dòng khai báo package. Ứng dụng cần cấu hình kết nối MongoDB, quét repository và đăng ký listener khi thực hành.

### 3.1. Sự kiện chứa dữ liệu độc lập với danh sách

```java
import java.time.Instant;
import java.util.UUID;

public record OrderConfirmed(
        UUID eventId,
        String orderId,
        Instant occurredAt) {
}
```

Sự kiện chứa ID của chính nó, ID đơn hàng và thời điểm nghiệp vụ. Nó không giữ tham chiếu tới cả aggregate hoặc tới `pendingEvents`. Khi hàng đợi bị dọn, các giá trị trong sự kiện vẫn có ý nghĩa đối với người nhận.

ID sự kiện trong ví dụ được tạo khi thay đổi nghiệp vụ xảy ra. Không tạo một ID mới mỗi lần `domainEvents()` được gọi, vì một lần đọc hàng đợi không phải một sự kiện nghiệp vụ mới.

### 3.2. Aggregate tự quản lý danh sách chờ

```java
import java.time.Instant;
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import java.util.Objects;
import java.util.UUID;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Transient;
import org.springframework.data.annotation.Version;
import org.springframework.data.domain.AfterDomainEventPublication;
import org.springframework.data.domain.DomainEvents;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("orders")
public class Order {

    @Id
    private String id;

    private boolean confirmed;

    @Version
    private Long version;

    @Transient
    private final List<Object> pendingEvents = new ArrayList<>();

    protected Order() {
    }

    public static Order draft(String orderId) {
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("orderId bắt buộc");
        }

        Order order = new Order();
        order.id = orderId;
        return order;
    }

    public void confirm(Instant occurredAt) {
        Objects.requireNonNull(occurredAt, "occurredAt bắt buộc");

        if (confirmed) {
            return;
        }

        confirmed = true;
        pendingEvents.add(new OrderConfirmed(
                UUID.randomUUID(), id, occurredAt));
    }

    @DomainEvents
    Collection<Object> domainEvents() {
        return List.copyOf(pendingEvents);
    }

    @AfterDomainEventPublication
    void clearPendingEvents() {
        pendingEvents.clear();
    }

    public String getId() {
        return id;
    }

    public boolean isConfirmed() {
        return confirmed;
    }
}
```

Một số quyết định thuộc về ứng dụng minh họa:

| Quyết định | Mục đích |
| --- | --- |
| `confirm()` chỉ ghi sự kiện ở lần chuyển trạng thái đầu | Gọi lại cùng hành vi không tự tạo thêm xác nhận |
| ID đơn hàng có sẵn trước `confirm()` | Payload chứa định danh ổn định ngay khi tạo sự kiện |
| `pendingEvents` là danh sách riêng của từng instance | Tránh trộn sự kiện giữa các đơn hàng |
| `List.copyOf(...)` khi cung cấp sự kiện | Bên nhận không sửa trực tiếp danh sách nội bộ |
| `@Transient` của Spring Data trên hàng đợi | Hàng đợi tạm không phải dữ liệu document của mẫu MongoDB này |
| Callback chỉ gọi `clear()` | Giữ trách nhiệm dọn đơn giản, ít khả năng phát sinh lỗi |

Annotation mapping trong ví dụ thuộc MongoDB và Spring Data. Nếu chuyển sang JPA, cần thiết kế mapping và thuộc tính không lưu theo quy tắc của JPA; không mặc định mọi annotation `Transient` có thể thay thế cho nhau.

### 3.3. Repository và luồng sử dụng

```java
import org.springframework.data.repository.CrudRepository;

public interface OrderRepository extends CrudRepository<Order, String> {
}
```

Với `repository` là bean đã được ứng dụng cung cấp:

```java
Order order = Order.draft("order-42");
order.confirm(Instant.parse("2026-01-15T08:00:00Z"));

Order saved = repository.save(order);
Order savedAgain = repository.save(saved);
```

Lần lưu đầu có một `OrderConfirmed` đang chờ. Khi lượt phát hành và callback hoàn tất bình thường, hàng đợi của aggregate được xử lý đã rỗng. Lần lưu tiếp không có lý do nghiệp vụ để phát lại xác nhận cũ.

Hãy dùng instance được repository trả về cho thao tác lưu tiếp theo, đồng thời kiểm tra đúng instance sở hữu hàng đợi khi quan sát callback. Hai câu hỏi này cần được xét riêng khi custom repository hoặc mapping tạo bản sao entity.

## 4. Thời điểm dọn và ý nghĩa của việc phát hành

Trong mã nguồn tham chiếu, interceptor gọi thao tác repository trước, sau đó phát các sự kiện lấy từ aggregate trong đối số và mới gọi callback dọn. Callback không được đặt trong `finally`; luồng này cũng có thể gọi callback khi collection rỗng. Đây là chi tiết implementation cần đối chiếu với phiên bản đang sử dụng. [Mã nguồn EventPublishingRepositoryProxyPostProcessor](https://github.com/spring-projects/spring-data-commons/blob/main/src/main/java/org/springframework/data/repository/core/support/EventPublishingRepositoryProxyPostProcessor.java).

Với luồng thành công, có thể dùng mô hình sau để điều tra:

```text
Thao tác repository trả về
  -> đọc danh sách từ aggregate đầu vào
  -> chuyển từng sự kiện cho publisher
  -> callback dọn danh sách
  -> trả kết quả cho bên gọi
```

Không dùng sơ đồ này để kết luận rằng database đã commit tại một mốc cố định. Thời điểm commit còn phụ thuộc ranh giới transaction bao quanh lời gọi.

Hợp đồng `ApplicationEventPublisher` mô tả phát hành là chuyển giao cho multicaster; lời gọi đó tự nó không cam kết listener chạy đồng bộ, bất đồng bộ hay ngay lập tức. [API ApplicationEventPublisher](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/ApplicationEventPublisher.html).

Do đó, trong ví dụ đơn hàng, callback hoàn tất chỉ cho biết hàng đợi của lượt phát hành đã được dọn. Nó không phải biên nhận rằng email đã gửi, broker đã xác nhận hoặc mọi listener đã hoàn thành tác vụ.

Nếu đang dùng thiết kế bất biến hoặc repository trả một instance khác, cần kiểm tra đường đi của hàng đợi giữa object đầu vào và object trả về. Không chỉ nhìn trạng thái một bản sao rồi suy ra callback đã dọn mọi object có liên quan.

## 5. Giữ phương thức @DomainEvents không có tác dụng phụ

Một lỗi dễ gặp là lấy và xóa sự kiện ngay trong phương thức cung cấp chúng:

```java
@DomainEvents
Collection<Object> domainEvents() {
    List<Object> result = List.copyOf(pendingEvents);
    pendingEvents.clear();
    return result;
}
```

Thiết kế này làm việc đọc hàng đợi thay đổi trạng thái của aggregate. Một công cụ chẩn đoán, một test hoặc hạ tầng đọc lại phương thức có thể thấy kết quả khác dù không có thay đổi nghiệp vụ.

Trong implementation tham chiếu, danh sách còn được đọc lại để kiểm tra sự thay đổi trong lúc phát hành. Vì vậy, không thiết kế phương thức này như thao tác lấy một lần rồi tiêu thụ mất dữ liệu. [Mã nguồn EventPublishingRepositoryProxyPostProcessor](https://github.com/spring-projects/spring-data-commons/blob/main/src/main/java/org/springframework/data/repository/core/support/EventPublishingRepositoryProxyPostProcessor.java).

Với mẫu của bài, hai lần gọi `domainEvents()` trước callback cần biểu diễn cùng các sự kiện đang chờ. Callback mới là nơi chuyển hàng đợi sang trạng thái rỗng.

`List.copyOf` chỉ bảo vệ cấu trúc collection được trả ra. Nếu phần tử là một object mutable chứa tham chiếu tới dữ liệu thay đổi liên tục, payload vẫn có thể thay đổi sau lúc lấy danh sách. Dùng record chứa các giá trị phù hợp giúp diễn đạt rõ sự kiện đã xảy ra.

## 6. Callback nên dọn gì và giữ lại gì?

Hãy giới hạn callback vào dữ liệu tạm phục vụ lần công bố vừa rồi. Với `Order`, đó là `pendingEvents`; trạng thái `confirmed` vẫn phải giữ nguyên.

| Dữ liệu hoặc công việc | Cách xử lý trong mẫu này |
| --- | --- |
| Danh sách sự kiện chờ trong bộ nhớ | Dọn sau lượt phát hành |
| ID, version và trạng thái nghiệp vụ | Giữ lại |
| Lịch sử nghiệp vụ được lưu riêng | Quản lý theo vòng đời lưu trữ riêng |
| Gửi email hoặc gọi broker | Đặt trong luồng xử lý sự kiện có hợp đồng rõ |
| Tạo thêm thay đổi nghiệp vụ | Thực hiện bằng command hoặc hành vi domain riêng |

Một callback dễ vận hành có tính chất gọi lại vẫn an toàn: dọn danh sách đã rỗng không làm sai aggregate. Không đòi hỏi danh sách phải có đúng một phần tử và không coi callback là nơi tăng số lần xác nhận đơn hàng.

Tránh gọi `repository.save(this)` trong callback. Với một phương thức vốn được kích hoạt từ luồng repository, thao tác lưu lồng nhau làm khó xác định lượt nào đang phát và lượt nào đang dọn.

Cũng tránh sửa hàng đợi đang được công bố từ listener bằng cách giữ tham chiếu tới cùng aggregate. Nếu nghiệp vụ tiếp theo phát sinh một hành vi mới, hãy thiết kế nó như một bước xử lý riêng với ranh giới và instance được kiểm soát.

## 7. Dùng AbstractAggregateRoot để giảm mã quản lý hàng đợi

`AbstractAggregateRoot` cung cấp các phương thức ghi nhận, cung cấp và dọn domain events. Đây là lớp tiện ích dùng cơ chế `@DomainEvents` và `@AfterDomainEventPublication`, không phải một hệ thống phát sự kiện khác. [API AbstractAggregateRoot](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/AbstractAggregateRoot.html).

Một biến thể domain tối giản, thay cho phần tự quản lý danh sách:

```java
import java.time.Instant;
import java.util.Objects;
import java.util.UUID;
import org.springframework.data.domain.AbstractAggregateRoot;

public class OrderRoot extends AbstractAggregateRoot<OrderRoot> {

    private final String id;
    private boolean confirmed;

    public OrderRoot(String id) {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("id bắt buộc");
        }
        this.id = id;
    }

    public void confirm(Instant occurredAt) {
        Objects.requireNonNull(occurredAt, "occurredAt bắt buộc");
        if (confirmed) {
            return;
        }

        confirmed = true;
        registerEvent(new OrderConfirmed(
                UUID.randomUUID(), id, occurredAt));
    }
}
```

Đoạn này chỉ minh họa biến thể domain; muốn lưu `OrderRoot` cần bổ sung mapping và cấu hình repository thích hợp. Không đăng ký đồng thời nó và mẫu `Order` rồi coi chúng là cùng một aggregate persistent.

Lớp cơ sở đã có phương thức dọn được đánh dấu annotation và lưu hàng đợi tạm trong instance. [Mã nguồn AbstractAggregateRoot](https://github.com/spring-projects/spring-data-commons/blob/main/src/main/java/org/springframework/data/domain/AbstractAggregateRoot.java).

Nếu cần tùy biến sâu, hãy chọn một cách quản lý hàng đợi nhất quán. Tránh kế thừa lớp cơ sở nhưng lại ghi sự kiện vào một danh sách khác mà phương thức dọn kế thừa không biết tới.

## 8. Listener lỗi, callback lỗi và phát hành một phần

`SimpleApplicationEventMulticaster` mặc định gọi listener trên thread phát hành. Khi không có error handler tùy biến, lỗi listener có thể dừng lượt multicast và truyền về publisher; executor hoặc error handler có thể làm hành vi khác đi. [API SimpleApplicationEventMulticaster](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html).

Kết hợp đặc điểm đó với luồng callback ở phần 4, cần phân tích ít nhất các trường hợp sau:

| Điểm phát sinh lỗi | Điều cần kiểm tra trước khi retry |
| --- | --- |
| Thao tác repository chưa trả về bình thường | Dữ liệu đã được ghi hay rollback, sự kiện đã vào bước phát chưa |
| Publisher báo lỗi ở sự kiện đầu | Listener nào đã nhận sự kiện trước lỗi |
| Đã phát một số sự kiện rồi lỗi | Tập sự kiện đã được xử lý có thể chỉ là một phần |
| Callback dọn ném lỗi | Các sự kiện có thể đã được phát trước lỗi callback |
| Listener bất đồng bộ lỗi sau đó | Hàng đợi có thể đã được dọn trước khi tác vụ lỗi |

Ví dụ aggregate có `[e1, e2]`: một listener của `e1` đã gửi thông báo, rồi quá trình xử lý `e2` báo lỗi trước callback. Nếu ứng dụng phát lại cả danh sách, `e1` có thể tạo thông báo lần nữa. Dọn hàng đợi thành công ở luồng bình thường không giải quyết được tình huống phát hành một phần này.

Giữ ID sự kiện khi retry cùng sự kiện và thiết kế người nhận xử lý lặp một cách an toàn nếu yêu cầu nghiệp vụ cần điều đó. Đồng thời phân biệt retry phát hành một sự kiện đã có với chạy lại command để tạo một sự kiện mới.

Không thêm một khối `finally` trong service để luôn xóa hàng đợi sau mọi lỗi chỉ nhằm làm test hết sự kiện tồn đọng. Quyết định bỏ hay giữ dữ liệu chờ phải phù hợp chính sách retry và trạng thái transaction thực tế.

## 9. Dọn danh sách khác với transaction commit

`@TransactionalEventListener` gắn xử lý listener với một phase transaction, mặc định là `AFTER_COMMIT`. Khi không có transaction phù hợp, mặc định listener không chạy; có thể đổi hành vi bằng `fallbackExecution`. [Spring Framework: Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html).

Giả sử lời gọi repository nằm bên trong một service có transaction ngoài, và event được phát trong transaction đó. Một dòng thời gian có thể là:

```text
Bắt đầu transaction ngoài
  -> thay đổi aggregate
  -> repository.save(...)
  -> phát sự kiện; listener theo transaction đăng ký xử lý
  -> callback dọn pendingEvents
  -> service tiếp tục công việc
Commit transaction ngoài
  -> listener AFTER_COMMIT chạy
```

Nếu service thất bại và transaction rollback trước commit, listener `AFTER_COMMIT` không chạy theo luồng commit thành công, trong khi danh sách trong object Java có thể đã được dọn. Đây là lý do không dùng kích thước hàng đợi làm bằng chứng transaction đã thành công.

Một rollback dữ liệu cũng không tự chạy ngược các phép `clear()` trên mọi collection Java. Sau lỗi, cần kiểm soát việc tái sử dụng aggregate và chọn cách retry phù hợp; không tự suy rằng object đang giữ đã trở lại trạng thái trước command.

Nếu cần chuyển sự kiện ra hệ thống khác với khả năng khôi phục sau khi tiến trình dừng, hãy thiết kế nơi lưu bền và quá trình chuyển giao có thể theo dõi. Hàng đợi tạm cùng callback dọn không cung cấp bản ghi bền để khôi phục lượt gửi còn dang dở.

## 10. Phạm vi kích hoạt phải được kiểm tra qua repository

Tài liệu Commons liệt kê `save`, `saveAll` và các biến thể delete nhận aggregate trong số các điểm kích hoạt. `deleteById` không thuộc cơ chế này vì implementation có thể xóa trực tiếp mà không có instance aggregate. [Spring Data Commons: Publishing Events from Aggregate Roots](https://docs.spring.io/spring-data/commons/reference/repositories/core-domain-events.html).

Với ứng dụng đơn hàng, hãy kiểm tra rõ lời gọi nào đi qua repository proxy được cấu hình. Một số tình huống cần phân biệt:

- Gọi `order.confirm(...)` mới ghi sự kiện vào hàng đợi của mẫu này.
- Gọi phương thức domain rồi không lưu chưa chứng minh có lượt phát hành.
- Gọi template, raw driver hoặc query cập nhật trực tiếp cần được đánh giá theo đường thực thi riêng.
- Chỉ gọi `ApplicationEventPublisher.publishEvent(...)` thủ công không tự chứng minh callback trên aggregate đã được gọi.
- Với JPA, không suy rằng chỉ dựa vào dirty checking rồi commit sẽ có cùng bước công bố domain events như một lời gọi repository được hỗ trợ.

Khi dùng `saveAll`, quan sát hàng đợi của từng aggregate. Không thiết kế một danh sách static dùng chung rồi dọn sau một aggregate, vì như vậy sự kiện của aggregate khác có thể bị mất.

## 11. Kiểm thử việc dọn và kiểm thử hạ tầng là hai bước

### 11.1. Kiểm thử quy tắc hàng đợi trong domain

Test dưới đây dùng JUnit Jupiter, đặt cùng package với `Order` để gọi các phương thức package-private của mẫu:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Instant;
import org.junit.jupiter.api.Test;

public class OrderEventQueueTest {

    @Test
    void readingEventsDoesNotConsumeThem() {
        Order order = Order.draft("order-42");
        order.confirm(Instant.parse("2026-01-15T08:00:00Z"));

        var firstRead = order.domainEvents();
        var secondRead = order.domainEvents();

        assertEquals(1, firstRead.size());
        assertEquals(firstRead, secondRead);
    }

    @Test
    void cleanupIsRepeatableAndKeepsBusinessState() {
        Order order = Order.draft("order-42");
        order.confirm(Instant.parse("2026-01-15T08:00:00Z"));
        var exposedEvents = order.domainEvents();

        order.clearPendingEvents();
        order.clearPendingEvents();

        assertTrue(order.domainEvents().isEmpty());
        assertTrue(order.isConfirmed());
        assertEquals(1, exposedEvents.size());
    }
}
```

Những test này kiểm tra quy tắc do domain triển khai. Vì callback được gọi trực tiếp, chúng chưa chứng minh Spring Data phát hiện annotation hoặc gọi callback qua repository.

### 11.2. Kiểm thử tích hợp qua đúng module

Trong ứng dụng thử nghiệm có repository và listener thật, cần quan sát:

| Tình huống | Kết quả cần kiểm tra |
| --- | --- |
| Xác nhận rồi save | Listener nhận đúng event ID và order ID |
| Save lại sau lượt thành công | Số sự kiện nhận không tăng do hàng đợi cũ |
| Đọc `domainEvents()` trước save | Việc đọc không làm mất sự kiện |
| Aggregate không có sự kiện chờ | Callback vẫn an toàn với danh sách rỗng |
| Listener đồng bộ ném lỗi | Quan sát hàng đợi, lỗi trả về và kết quả transaction |
| Callback dọn ném lỗi trong biến thể thử nghiệm | Phát hiện trường hợp event đã được gửi trước lỗi |
| Transaction ngoài rollback | Phân biệt listener thường với listener sau commit |
| Listener chạy bất đồng bộ | Không suy luận hoàn tất xử lý từ lúc callback đã chạy |
| Save nhiều aggregate | Danh sách của mỗi instance được xử lý độc lập |

Các đoạn kiểm thử trong bài là ví dụ thực hành, không phải báo cáo đã chạy trên dự án. Khi tái hiện lỗi, ghi lại cấu hình multicaster, loại listener, ranh giới transaction, API repository và phiên bản Spring Data.

## 12. Bài tập áp dụng

Tạo một ứng dụng thử nghiệm có `OrderRepository` và listener thu các `OrderConfirmed` nhận được. Xác nhận một đơn hàng rồi lưu hai lần, ghi lại event ID và số phần tử trong hàng đợi sau mỗi lần lưu.

Sau đó giải thích các câu hỏi:

1. Vì sao lần lưu thứ hai không nên công bố lại xác nhận cũ?
2. Vì sao không dọn danh sách ngay trong `domainEvents()`?
3. Callback dọn có chứng minh email hoặc tác vụ bất đồng bộ đã hoàn tất không?
4. Nếu phát sự kiện thứ hai bị lỗi, điều gì có thể xảy ra khi retry cả danh sách?
5. Nếu transaction ngoài rollback sau khi danh sách đã dọn, ứng dụng nên kiểm tra gì trước khi dùng lại aggregate?

Khi đọc một thiết kế sử dụng `@AfterDomainEventPublication`, hãy chỉ ra được instance giữ hàng đợi, nơi ghi nhận sự kiện, đường repository kích hoạt và chính sách xử lý lỗi. Bốn điểm đó giúp việc dọn danh sách có ý nghĩa rõ ràng trong vòng đời aggregate.
