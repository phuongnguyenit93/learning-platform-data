# Phân biệt EntityCallback với ApplicationEvent và thứ tự thực thi

Spring Data JDBC cung cấp hai cơ chế để can thiệp vào vòng đời của aggregate: **EntityCallback** và **lifecycle ApplicationEvent**. Cả hai đều có thể được gọi ở những mốc như trước khi lưu hoặc sau khi đọc dữ liệu, nhưng mục đích và cách hoạt động khác nhau.

- **EntityCallback** là hook nằm trực tiếp trong pipeline xử lý aggregate. Callback có thể trả về cùng entity hoặc một instance đã được thay đổi. Spring Data gọi callback tuần tự tại những checkpoint xác định.
- **ApplicationEvent** là thông báo được phát trong Spring ApplicationContext. Listener nhận thông tin về một sự kiện vòng đời; cơ chế event phù hợp cho logging, audit, metrics hoặc thông báo tới thành phần khác.

Trong Spring Data JDBC, lifecycle event là một loại `ApplicationEvent` do Spring Data phát ra. EntityCallback và event tương ứng thường xuất hiện tại cùng một checkpoint, với event được publish trước callback. Khi cần thay đổi entity một cách có kiểm soát, Spring khuyến nghị dùng callback. Khi cần thông báo cho listener, dùng event.

Bài học giải thích sự khác nhau, các callback và event có sẵn, pipeline save/load/delete, thứ tự giữa event và callback, cách đăng ký bean, transaction boundary và những trường hợp không kích hoạt lifecycle hook.

## 1. Hai cơ chế phục vụ hai mục đích

### EntityCallback

`EntityCallback<T>` là abstraction của Spring Data cho một điểm mở rộng trong quy trình xử lý entity. Mỗi callback interface gắn với kiểu domain thông qua generic type `T`.

Ví dụ, `BeforeConvertCallback<Order>` chỉ xử lý aggregate kiểu `Order`. Phương thức callback nhận entity và trả về entity có thể đã được thay đổi:

~~~java
public interface BeforeConvertCallback<T> extends EntityCallback<T> {
    T onBeforeConvert(T aggregate);
}
~~~

Giá trị trả về được Spring Data sử dụng ở bước tiếp theo. Vì vậy callback có thể hoạt động với cả entity mutable lẫn immutable.

### ApplicationEvent

Spring Data JDBC publish các lifecycle event, ví dụ `BeforeSaveEvent<Order>`. Listener đăng ký nhận event trong ApplicationContext:

~~~java
@EventListener
public void onBeforeSave(BeforeSaveEvent<Order> event) {
    log.info("Saving order {}", event.getEntity().getId());
}
~~~

Event là thông báo về một mốc trong vòng đời. Listener có thể đọc entity và thông tin aggregate change đi kèm, nhưng event không có hợp đồng trả về instance thay thế cho pipeline persist.

### So sánh nhanh

| Tiêu chí | EntityCallback | ApplicationEvent |
| --- | --- | --- |
| Mục đích chính | Can thiệp pipeline xử lý entity | Thông báo một sự kiện đã/đang xảy ra |
| Kết quả xử lý | Trả về entity có thể đã thay đổi | Không trả về entity cho pipeline |
| Thứ tự | Tuần tự tại checkpoint; có thể sắp xếp bằng `@Order`/`Ordered` | Phụ thuộc ApplicationEventMulticaster và cấu hình listener |
| Entity immutable | Hỗ trợ tốt vì có thể trả instance mới | Không có cơ chế trả instance mới cho Spring Data |
| Phạm vi | Callback được lọc theo generic domain type | Listener được chọn theo event type |
| Đăng ký | Bean `EntityCallback` trong ApplicationContext | `ApplicationListener` hoặc `@EventListener` |
| Trường hợp dùng | Chuẩn hóa, gán dữ liệu, kiểm tra trước khi persist | Logging, audit, metrics, thông báo thành phần khác |

Không nên coi hai cơ chế là hai tên gọi cho cùng một API. Callback tham gia vào luồng xử lý entity; event phục vụ giao tiếp và quan sát trong ứng dụng.

## 2. Các lifecycle callback của Spring Data JDBC

Các callback imperative trong Spring Data JDBC thuộc package:

~~~java
import org.springframework.data.relational.core.mapping.event.*;
~~~

Những interface thường gặp:

| Callback | Thời điểm | Mục đích |
| --- | --- | --- |
| `BeforeConvertCallback<T>` | Trước khi aggregate được chuyển thành kế hoạch thay đổi database | Thay đổi dữ liệu domain trước khi tạo các thao tác SQL; phù hợp để gán ID theo chương trình |
| `BeforeSaveCallback<T>` | Sau khi `AggregateChange` đã được tạo, trước khi chạy SQL | Can thiệp ở giai đoạn chuẩn bị ghi |
| `AfterSaveCallback<T>` | Sau khi các câu SQL lưu aggregate đã chạy | Xử lý instance sau khi persist |
| `AfterConvertCallback<T>` | Sau khi aggregate được dựng từ dữ liệu database | Bổ sung hoặc điều chỉnh instance sau khi đọc |
| `BeforeDeleteCallback<T>` | Trước khi xóa aggregate | Can thiệp vào thao tác xóa |
| `AfterDeleteCallback<T>` | Sau khi xóa aggregate | Xử lý sau khi xóa |

Ví dụ các chữ ký chính:

~~~java
public interface BeforeConvertCallback<T> extends EntityCallback<T> {
    T onBeforeConvert(T aggregate);
}

public interface BeforeSaveCallback<T> extends EntityCallback<T> {
    T onBeforeSave(
        T aggregate,
        MutableAggregateChange<T> aggregateChange
    );
}

public interface AfterSaveCallback<T> extends EntityCallback<T> {
    T onAfterSave(T aggregate);
}

public interface AfterConvertCallback<T> extends EntityCallback<T> {
    T onAfterConvert(T aggregate);
}

public interface BeforeDeleteCallback<T> extends EntityCallback<T> {
    T onBeforeDelete(
        T aggregate,
        MutableAggregateChange<T> aggregateChange
    );
}

public interface AfterDeleteCallback<T> extends EntityCallback<T> {
    T onAfterDelete(T aggregate);
}
~~~

Các callback này áp dụng cho **aggregate root**. Nếu cần xử lý một entity con thuộc aggregate, hãy truy cập nó thông qua aggregate root trong callback tương ứng. Spring Data JDBC không tự gọi một callback riêng cho từng object con trong collection.

## 3. Các lifecycle ApplicationEvent tương ứng

Spring Data JDBC publish các event sau:

| Event | Thời điểm publish |
| --- | --- |
| `BeforeConvertEvent<T>` | Trước khi aggregate được chuyển thành kế hoạch SQL, sau khi Spring Data đã xác định insert hay update |
| `BeforeSaveEvent<T>` | Trước khi áp dụng các thay đổi xuống database, sau khi `AggregateChange` được tạo |
| `AfterSaveEvent<T>` | Sau khi aggregate đã được lưu bằng các câu SQL |
| `AfterConvertEvent<T>` | Sau khi aggregate được tạo từ `ResultSet` và các property đã được gán |
| `BeforeDeleteEvent<T>` | Trước khi xóa aggregate root |
| `AfterDeleteEvent<T>` | Sau khi xóa aggregate root |

Các event này nằm trong package:

~~~java
import org.springframework.data.relational.core.mapping.event.*;
~~~

Chúng là các lớp event của Spring, có thể được nhận bằng `ApplicationListener` hoặc `@EventListener`.

Ví dụ đăng ký listener theo kiểu event:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.data.relational.core.mapping.event.AfterSaveEvent;

@Component
public class OrderLifecycleListener {

    @EventListener
    public void onAfterSave(AfterSaveEvent<Order> event) {
        Order savedOrder = event.getEntity();

        log.info(
            "Order {} was persisted",
            savedOrder.getId()
        );
    }
}
~~~

Nếu muốn dùng listener tổng quát hơn, có thể triển khai `ApplicationListener<BeforeSaveEvent<Order>>`. Dùng generic type cụ thể giúp Spring lọc đúng event domain cần xử lý.

## 4. Thứ tự thực thi khi lưu aggregate

Đây là phần quan trọng nhất của bài học. Khi repository hoặc template lưu aggregate, Spring Data JDBC thực hiện nhiều giai đoạn. Ở mỗi checkpoint có lifecycle event và callback tương ứng.

~~~mermaid
flowchart TD
    A["Bắt đầu save aggregate"] --> B["Xác định entity mới hay đã tồn tại"]
    B --> C["BeforeConvertEvent"]
    C --> D["BeforeConvertCallback"]
    D --> E["Tạo AggregateChange / DbAction"]
    E --> F["BeforeSaveEvent"]
    F --> G["BeforeSaveCallback"]
    G --> H["Thực thi SQL"]
    H --> I["AfterSaveEvent"]
    I --> J["AfterSaveCallback"]
    J --> K["Trả kết quả từ thao tác save"]
~~~

Theo cơ chế Spring Data Commons, store-specific ApplicationEvent được publish trước khi các EntityCallback tương ứng được gọi. Vì vậy trong cấu hình event đồng bộ mặc định, thứ tự tại từng checkpoint là:

1. Publish event.
2. Gọi callback tương ứng.
3. Tiếp tục sang bước xử lý kế tiếp.

### 4.1. Xác định insert hay update

Spring Data JDBC quyết định aggregate là mới hay đã tồn tại trước khi gọi `BeforeConvertCallback`. Quyết định này ảnh hưởng đến kế hoạch persist tiếp theo.

Điều đó có nghĩa callback `BeforeConvertCallback` có thể gán ID cho aggregate mới, nhưng không phải nơi để thay đổi tùy ý trạng thái newness đã được xác định.

### 4.2. BeforeConvertEvent và BeforeConvertCallback

Sau khi xác định insert/update, Spring Data publish `BeforeConvertEvent` rồi gọi `BeforeConvertCallback`.

Đây là checkpoint phù hợp để:

- Chuẩn hóa dữ liệu domain trước khi mapping.
- Gán ID theo chương trình cho aggregate mới.
- Tạo giá trị slug hoặc mã nghiệp vụ cần được ghi vào database.
- Bổ sung timestamp hoặc metadata cần nằm trong dữ liệu persist.

Ví dụ, dùng callback để chuẩn hóa mã đơn hàng:

~~~java
import org.springframework.data.relational.core.mapping.event.BeforeConvertCallback;
import org.springframework.stereotype.Component;

@Component
public class NormalizeOrderCodeCallback
        implements BeforeConvertCallback<Order> {

    @Override
    public Order onBeforeConvert(Order order) {
        String normalized = order.getCode().trim().toUpperCase();

        order.setCode(normalized);

        return order;
    }
}
~~~

Ví dụ trên dùng entity mutable để minh họa. Nếu entity immutable, hãy tạo và trả về instance mới thay vì sửa object hiện tại.

### 4.3. Tạo AggregateChange

Sau `BeforeConvertCallback`, Spring Data JDBC chuyển aggregate thành `AggregateChange`. Cấu trúc này chứa các `DbAction` cần thực hiện, chẳng hạn insert, update và delete cho root cùng các entity con.

Tại giai đoạn này, Spring Data đã xác định cách thực hiện các thao tác và liệu ID được cung cấp từ aggregate hay database cần sinh ID.

### 4.4. BeforeSaveEvent và BeforeSaveCallback

Sau khi tạo `AggregateChange`, Spring Data publish `BeforeSaveEvent` rồi gọi `BeforeSaveCallback`. SQL chưa được chạy ở thời điểm này.

Callback này nhận cả aggregate và `MutableAggregateChange`. Nó có thể trả về entity và can thiệp vào kế hoạch thay đổi.

Không dùng `BeforeSaveCallback` để tạo ID cho aggregate mới. Quyết định chiến lược ID đã được đưa ra khi tạo aggregate change. Nếu cần gán ID trước khi persist, dùng `BeforeConvertCallback`.

### 4.5. SQL và AfterSaveEvent/AfterSaveCallback

Sau callback trước khi lưu, Spring Data thực thi các câu SQL trong `AggregateChange`. Khi thao tác lưu hoàn thành, Spring Data publish `AfterSaveEvent` rồi gọi `AfterSaveCallback`.

Đây là checkpoint phù hợp để quan sát kết quả persist hoặc điều chỉnh instance được trả về từ pipeline. Tuy nhiên, “SQL đã chạy” không đồng nghĩa “transaction đã commit”. Nếu service đang có transaction bao quanh, commit có thể xảy ra sau khi repository method trả về.

## 5. Thứ tự khi đọc và xóa aggregate

### 5.1. Khi đọc

Khi Spring Data JDBC đọc dữ liệu và dựng aggregate:

~~~text
Chạy SELECT
    ↓
Đọc ResultSet
    ↓
Dựng aggregate root và các property
    ↓
AfterConvertEvent
    ↓
AfterConvertCallback
    ↓
Trả aggregate cho caller
~~~

`AfterConvertCallback` phù hợp nếu cần bổ sung một giá trị tính toán hoặc điều chỉnh instance sau khi mapping. Hãy cân nhắc kỹ việc thay đổi dữ liệu trong callback đọc: cùng một hàng database có thể được đọc ở nhiều use case khác nhau, vì vậy callback nên có hành vi ổn định và không tạo side effect.

### 5.2. Khi xóa

Quy trình xóa aggregate về mặt khái niệm:

~~~text
Bắt đầu delete aggregate
    ↓
BeforeDeleteEvent
    ↓
BeforeDeleteCallback
    ↓
Thực thi các câu SQL xóa root và entity con
    ↓
AfterDeleteEvent
    ↓
AfterDeleteCallback
~~~

Một giới hạn đáng chú ý: `BeforeDeleteCallback` và `AfterDeleteCallback` chỉ được gọi khi phương thức xóa nhận **instance aggregate** làm đối số. Các thao tác xóa theo ID hoặc xóa không truyền instance không kích hoạt hai callback này.

Ví dụ:

~~~java
repository.delete(order);       // Có thể kích hoạt delete callbacks
repository.deleteById(orderId);  // Không kích hoạt delete callbacks
~~~

Nếu logic bắt buộc phải chạy trong callback xóa, hãy dùng thao tác xóa truyền aggregate instance. Với delete theo ID, có thể dùng application service để load aggregate trước rồi xóa object đó, nếu chi phí và yêu cầu nghiệp vụ cho phép.

## 6. Đăng ký EntityCallback

Spring Data nhận các callback bean được đăng ký trong `ApplicationContext`. Có thể dùng `@Component` hoặc khai báo bằng `@Bean`.

Ví dụ component:

~~~java
import org.springframework.core.annotation.Order;
import org.springframework.data.relational.core.mapping.event.BeforeConvertCallback;
import org.springframework.stereotype.Component;

@Component
@Order(100)
public class OrderTimestampCallback
        implements BeforeConvertCallback<Order> {

    @Override
    public Order onBeforeConvert(Order order) {
        if (order.getCreatedAt() == null) {
            order.setCreatedAt(Instant.now());
        }

        return order;
    }
}
~~~

Ví dụ đăng ký bằng bean:

~~~java
@Configuration
public class OrderCallbackConfiguration {

    @Bean
    BeforeConvertCallback<Order> orderCodeCallback() {
        return order -> {
            order.setCode(order.getCode().trim());
            return order;
        };
    }
}
~~~

Trong hệ thống thực tế, nếu callback cần thời gian có thể kiểm thử, nên inject `Clock` thay vì gọi trực tiếp `Instant.now()`. Điều đó giúp test kiểm soát được giá trị thời gian.

### 6.1. Callback theo domain type

Generic type `Order` cho Spring Data biết callback áp dụng cho kiểu nào. Callback có thể xử lý kiểu được khai báo và các kiểu con tương thích.

Nếu một class triển khai nhiều callback interface, nó có thể xử lý nhiều checkpoint trong cùng một bean:

~~~java
@Component
public class OrderCallbacks
        implements BeforeConvertCallback<Order>,
                   AfterConvertCallback<Order> {

    @Override
    public Order onBeforeConvert(Order order) {
        // Chuẩn bị dữ liệu trước khi persist.
        return order;
    }

    @Override
    public Order onAfterConvert(Order order) {
        // Bổ sung dữ liệu sau khi đọc.
        return order;
    }
}
~~~

### 6.2. Sắp xếp nhiều callback

Khi có nhiều callback cùng loại cho một domain type, có thể xác định thứ tự bằng `@Order` hoặc implement `Ordered`.

~~~java
@Component
@Order(10)
class FirstOrderCallback implements BeforeConvertCallback<Order> {
    @Override
    public Order onBeforeConvert(Order order) {
        order.setCode(order.getCode().trim());
        return order;
    }
}

@Component
@Order(20)
class SecondOrderCallback implements BeforeConvertCallback<Order> {
    @Override
    public Order onBeforeConvert(Order order) {
        order.setCode(order.getCode().toUpperCase());
        return order;
    }
}
~~~

Giá trị order nhỏ hơn được gọi trước. Callback tiếp theo nhận kết quả mà callback trước trả về. Trong ví dụ, callback thứ hai nhận order đã được trim.

Callback không có order tường minh có thể được gọi sau callback đã được sắp xếp. Lambda callback không bộc lộ generic type metadata theo cách class callback làm, nên dùng class/enum callback khi cần lọc type hiệu quả và rõ ràng.

## 7. Đăng ký ApplicationEvent listener

Có hai cách phổ biến để nhận lifecycle event.

### 7.1. Dùng @EventListener

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.data.relational.core.mapping.event.BeforeSaveEvent;
import org.springframework.data.relational.core.mapping.event.AfterSaveEvent;

@Component
public class OrderEventListener {

    @EventListener
    public void onBeforeSave(BeforeSaveEvent<Order> event) {
        log.info("About to save order {}", event.getEntity().getId());
    }

    @EventListener
    public void onAfterSave(AfterSaveEvent<Order> event) {
        log.info("Saved order {}", event.getEntity().getId());
    }
}
~~~

### 7.2. Dùng ApplicationListener

~~~java
import org.springframework.context.ApplicationListener;
import org.springframework.stereotype.Component;
import org.springframework.data.relational.core.mapping.event.AfterSaveEvent;

@Component
public class OrderSavedListener
        implements ApplicationListener<AfterSaveEvent<Order>> {

    @Override
    public void onApplicationEvent(AfterSaveEvent<Order> event) {
        Order order = event.getEntity();

        log.info("Order {} was persisted", order.getId());
    }
}
~~~

Dùng `@EventListener` phù hợp khi một class nhận nhiều event type. Dùng `ApplicationListener<E>` phù hợp khi muốn một bean có hợp đồng listener rõ ràng cho một loại event.

### 7.3. Event chỉ được publish cho aggregate root

Spring Data JDBC chỉ phát lifecycle event cho aggregate root. Một `OrderLine` nằm trong `Order` không tự phát `BeforeSaveEvent<OrderLine>` hoặc callback riêng. Nếu cần log hoặc kiểm tra dòng hàng, hãy đọc collection từ `event.getEntity()` của root.

## 8. ApplicationEvent tùy chỉnh và @TransactionalEventListener

Không phải mọi event trong ứng dụng đều là lifecycle event của Spring Data. Ứng dụng có thể tự publish một event nghiệp vụ qua `ApplicationEventPublisher`.

Ví dụ, sau khi tạo đơn hàng, service publish `OrderPlacedEvent`:

~~~java
public record OrderPlacedEvent(Long orderId) {
}
~~~

~~~java
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    private final OrderRepository orders;
    private final ApplicationEventPublisher events;

    public OrderService(
            OrderRepository orders,
            ApplicationEventPublisher events) {
        this.orders = orders;
        this.events = events;
    }

    @Transactional
    public Long placeOrder(Order order) {
        Order saved = orders.save(order);

        events.publishEvent(
            new OrderPlacedEvent(saved.getId())
        );

        return saved.getId();
    }
}
~~~

Nếu listener gửi thông báo ra hệ thống bên ngoài, chỉ publish event đồng bộ chưa đủ để bảo đảm transaction đã commit. Dùng `@TransactionalEventListener` để gắn listener với một phase của transaction:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class OrderNotificationListener {

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT
    )
    public void onOrderPlaced(OrderPlacedEvent event) {
        notificationService.notifyOrderPlaced(event.orderId());
    }
}
~~~

Mặc định, `@TransactionalEventListener` dùng phase `AFTER_COMMIT`. Listener chỉ chạy sau khi transaction commit thành công. Các phase khác gồm `BEFORE_COMMIT`, `AFTER_ROLLBACK` và `AFTER_COMPLETION`.

Có thể dùng `@TransactionalEventListener` với lifecycle event của Spring Data JDBC vì chúng cũng là ApplicationEvent. Tuy nhiên, với event nghiệp vụ riêng như `OrderPlacedEvent`, code ứng dụng ít phụ thuộc vào chi tiết persistence hơn.

Nếu không có transaction đang hoạt động, transactional listener mặc định không được gọi. Có thể bật `fallbackExecution = true` nếu nghiệp vụ muốn listener vẫn chạy khi không có transaction, nhưng cần cân nhắc rõ semantics.

`AFTER_COMMIT` giúp tránh gửi thông báo khi transaction rollback. Nó không phải hàng đợi bền vững: nếu tiến trình dừng sau commit nhưng trước khi listener hoàn tất, thông báo vẫn có thể bị mất. Với yêu cầu giao nhận sự kiện đáng tin cậy, hãy cân nhắc Transactional Outbox hoặc cơ chế message delivery bền vững.

## 9. Thứ tự callback và event không giống nhau

Có hai loại thứ tự cần phân biệt:

### Thứ tự giữa event và callback cùng checkpoint

Spring Data Commons quy định store-specific ApplicationEvent được publish trước khi gọi EntityCallback tương ứng.

Trong cấu hình event đồng bộ mặc định, ví dụ tại checkpoint trước khi lưu:

~~~text
BeforeSaveEvent được publish
        ↓
ApplicationEvent listener được gọi
        ↓
BeforeSaveCallback được gọi
        ↓
SQL được thực thi
~~~

Đây là thứ tự của pipeline khi event listener xử lý đồng bộ. Nếu cấu hình ApplicationEventMulticaster với TaskExecutor hoặc listener chạy bằng `@Async`, việc xử lý event có thể diễn ra trên thread khác và không còn bảo đảm hoàn tất trước callback.

Vì vậy, không đặt logic sửa entity bắt buộc phải hoàn thành trong asynchronous event listener.

### Thứ tự giữa nhiều EntityCallback

Dùng `@Order` hoặc `Ordered` để xác định callback nào chạy trước. Callback được thực hiện tuần tự; instance trả về từ callback trước là input cho callback kế tiếp.

### Thứ tự giữa nhiều ApplicationEvent listener

Spring event infrastructure có thể sắp xếp listener bằng `@Order`. Tuy nhiên, thứ tự listener không thay đổi vị trí của event trong pipeline persist. Nếu listener bất đồng bộ, không dựa vào thứ tự hoàn tất để bảo đảm tính đúng đắn.

Không nên dùng `@Order` để cố điều phối một event listener và một EntityCallback như thể chúng cùng nằm trong một danh sách callback. Hai cơ chế có quy tắc điều phối riêng.

## 10. Đồng bộ và bất đồng bộ

### EntityCallback

EntityCallback của Spring Data JDBC là callback imperative, được gọi tuần tự trong pipeline xử lý aggregate. Nó không dùng `ApplicationEventMulticaster` để phân phối callback.

Điều này giúp Spring Data kiểm soát checkpoint và dùng giá trị callback trả về cho bước tiếp theo.

### ApplicationEvent

Spring ApplicationEvent được phân phối qua `ApplicationEventMulticaster`. Cấu hình mặc định thường gọi listener đồng bộ trên thread publish event. Nếu cấu hình TaskExecutor hoặc dùng `@Async`, listener có thể chạy ở thread khác.

| Đặc điểm | Callback | Event listener đồng bộ | Event listener bất đồng bộ |
| --- | --- | --- | --- |
| Cùng thread với pipeline | Có | Mặc định có | Không nhất thiết |
| Hoàn tất trước bước tiếp theo | Có | Có trong cấu hình đồng bộ | Không bảo đảm |
| Trả entity đã sửa cho pipeline | Có | Không | Không |
| Exception truyền trực tiếp qua pipeline | Có | Có thể truyền qua publisher | Không truyền trực tiếp về caller theo cách async thông thường |
| Phù hợp để sửa entity | Có | Không nên dùng | Không |
| Phù hợp cho công việc nền | Không | Có thể làm chậm caller | Có, nếu chấp nhận tính bất đồng bộ |

Không nên cấu hình event lifecycle bất đồng bộ nếu listener cần hoàn tất trước khi aggregate được persist. Dùng callback cho các thay đổi cần nằm trong pipeline.

## 11. Phạm vi kích hoạt và những trường hợp bị bỏ qua

Lifecycle callbacks và events không được gọi trong mọi câu SQL mà ứng dụng thực hiện.

### 11.1. Chỉ aggregate root

Event và callback của Spring Data JDBC chỉ kích hoạt cho aggregate root. Entity con được xử lý trong ngữ cảnh root chứa chúng.

### 11.2. Derived query và annotated query

Các callback liên quan đến save/delete không được gọi cho những thao tác derived query hoặc annotated query thực thi trực tiếp. Spring Data JDBC không có cách hiệu quả để xác định toàn bộ aggregate bị ảnh hưởng bởi câu query đó.

Ví dụ, một câu lệnh cập nhật hàng loạt bằng `@Modifying` không đi qua cùng pipeline `save(aggregate)`:

~~~java
@Modifying
@Query("UPDATE purchase_orders SET status = :status WHERE id = :id")
int updateStatus(Long id, String status);
~~~

Không giả định `BeforeSaveCallback` hoặc `AfterSaveCallback` sẽ chạy cho từng aggregate bị câu SQL trên cập nhật. Nếu nghiệp vụ cần auditing hoặc notification, hãy thực hiện rõ ràng ở service/query workflow.

### 11.3. Xóa bằng ID

Như đã nêu, `BeforeDeleteCallback` và `AfterDeleteCallback` chỉ được gọi khi phương thức delete nhận aggregate instance. `deleteById` và delete không có instance không kích hoạt các callback đó.

### 11.4. Custom RowMapper

Nếu query dùng custom `RowMapper`, `ResultSetExtractor` hoặc mapping riêng, Spring Data JDBC không thể tự áp dụng đầy đủ callback/event như khi dùng mapping mặc định. Query mapping tùy chỉnh cần tự xử lý hook nếu use case yêu cầu.

## 12. Chọn cơ chế theo nhu cầu

| Nhu cầu | Nên dùng |
| --- | --- |
| Chuẩn hóa dữ liệu trước khi lưu | `BeforeConvertCallback` |
| Gán ID theo chương trình cho aggregate mới | `BeforeConvertCallback` |
| Can thiệp vào `AggregateChange` trước khi SQL chạy | `BeforeSaveCallback` |
| Bổ sung dữ liệu sau khi aggregate được đọc | `AfterConvertCallback` |
| Ghi log khi aggregate sắp được lưu | `BeforeSaveEvent` listener |
| Ghi log sau khi SQL lưu aggregate đã chạy | `AfterSaveEvent` listener |
| Ghi log khi aggregate được xóa | `BeforeDeleteEvent` / `AfterDeleteEvent` |
| Gửi notification chỉ sau khi transaction commit | Application event + `@TransactionalEventListener(AFTER_COMMIT)` |
| Xử lý một nghiệp vụ cần trả instance immutable mới | EntityCallback |
| Phát sự kiện nghiệp vụ giữa các module | Custom ApplicationEvent |

Một quy tắc thực tế:

- Nếu kết quả của xử lý phải tác động tới object được persist hoặc trả về, dùng EntityCallback.
- Nếu chỉ cần thông báo cho thành phần khác biết một mốc đã xảy ra, dùng ApplicationEvent.
- Nếu side effect phụ thuộc transaction commit, dùng transactional event listener.
- Nếu cần giao nhận sự kiện bền vững, dùng outbox hoặc messaging infrastructure phù hợp.

## 13. Kiểm thử thứ tự thực thi

Có thể viết test ghi nhận thứ tự callback và event bằng một danh sách dùng chung. Ví dụ minh họa:

~~~java
@Component
public class OrderBeforeConvertCallback
        implements BeforeConvertCallback<Order> {

    private final List<String> trace;

    public OrderBeforeConvertCallback(List<String> trace) {
        this.trace = trace;
    }

    @Override
    public Order onBeforeConvert(Order order) {
        trace.add("before-convert-callback");
        return order;
    }
}
~~~

Event listener:

~~~java
@Component
public class OrderBeforeConvertListener {

    private final List<String> trace;

    public OrderBeforeConvertListener(List<String> trace) {
        this.trace = trace;
    }

    @EventListener
    public void onBeforeConvert(BeforeConvertEvent<Order> event) {
        trace.add("before-convert-event");
    }
}
~~~

Trong test configuration, cung cấp một collection dùng chung và gọi repository trong transaction test phù hợp. Với event listener đồng bộ mặc định, thứ tự mong đợi tại checkpoint này là:

~~~text
before-convert-event
before-convert-callback
~~~

Đây là test minh họa nguyên tắc. Khi dùng Spring context thật, cần bảo đảm hai bean cùng nhận đúng instance trace và event multicaster không bị cấu hình bất đồng bộ.

Để kiểm tra toàn pipeline save, đăng ký thêm listener/callback cho `BeforeSave` và `AfterSave`, rồi xác nhận thứ tự các checkpoint tương ứng. Không nên kiểm thử thứ tự hoàn tất event listener bất đồng bộ bằng một assertion tuần tự đơn giản; cần dùng latch hoặc cơ chế đồng bộ test riêng.

### Các tình huống nên có integration test

1. Callback BeforeConvert thay đổi entity và giá trị đó được lưu vào database.
2. Entity immutable được thay thế bằng instance callback trả về.
3. BeforeSaveCallback được gọi sau khi AggregateChange đã tạo.
4. AfterConvertCallback được gọi khi repository đọc aggregate.
5. Event listener nhận đúng aggregate root type.
6. Event và callback chạy theo thứ tự khi event multicaster đồng bộ.
7. Transaction rollback không kích hoạt listener `AFTER_COMMIT`.
8. `deleteById` không gọi delete callbacks.
9. Câu query modifying không kích hoạt save/delete callbacks.

## 14. Những lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Sửa entity trong event listener nhưng dữ liệu không đổi như mong muốn | Event là notification, không có hợp đồng trả entity mới | Dùng EntityCallback |
| Callback không chạy | Bean chưa được đăng ký trong ApplicationContext hoặc generic type không phù hợp | Đăng ký `@Component`/`@Bean` và kiểm tra domain type |
| Gán ID trong BeforeSaveCallback nhưng insert không dùng ID | AggregateChange và chiến lược ID đã được xác định trước đó | Gán ID trong `BeforeConvertCallback` |
| Callback sau không thấy thay đổi callback trước | Callback trước không trả về instance đã thay đổi | Trả đúng instance hoặc instance mới |
| Event listener chạy sau callback dù event publish trước | Event multicaster hoặc listener đang bất đồng bộ | Dùng callback cho logic cần thứ tự xác định |
| Gửi email dù transaction rollback | Listener thường chạy trước commit | Dùng `@TransactionalEventListener(AFTER_COMMIT)` |
| Callback không chạy khi dùng `@Modifying` | Query chạy trực tiếp, không qua aggregate lifecycle | Gọi nghiệp vụ ở service hoặc xử lý audit/event tường minh |
| Delete callback không chạy khi gọi deleteById | Callback yêu cầu aggregate instance làm đối số | Load aggregate và gọi `delete(entity)` nếu cần callback |
| Callback chạy với root nhưng không chạy cho child | Lifecycle hook chỉ áp dụng aggregate root | Xử lý child thông qua root |
| Thứ tự callback không ổn định | Không khai báo order khi có nhiều callback | Dùng `@Order` hoặc `Ordered` |
| Event listener bất đồng bộ mất transaction context | Listener chạy ở thread khác | Dùng transactional listener hoặc truyền dữ liệu sự kiện tường minh |

## 15. Bài tập tự thực hành

### Bài 1 — So sánh hai cơ chế

Tạo một `BeforeConvertCallback<Order>` và một `BeforeConvertEvent<Order>` listener. Ghi lại thứ tự thực thi khi lưu aggregate. Giải thích vì sao callback phù hợp hơn nếu cần thay đổi object trước khi persist.

### Bài 2 — Entity immutable

Chuyển `Order` thành record. Viết callback tạo record mới với trường `updatedAt` được cập nhật. Xác nhận giá trị callback trả về được dùng trong pipeline.

### Bài 3 — Callback ordering

Tạo hai `BeforeConvertCallback` với `@Order(10)` và `@Order(20)`. Callback thứ hai dựa vào kết quả callback thứ nhất. Quan sát thứ tự và giá trị cuối cùng.

### Bài 4 — Save lifecycle

Đăng ký listener cho `BeforeConvertEvent`, `BeforeSaveEvent` và `AfterSaveEvent`. Ghi log thời điểm nhận event và so sánh với callback tương ứng.

### Bài 5 — Transaction commit

Publish một custom `OrderPlacedEvent` trong method `@Transactional`. Viết listener thường và listener `@TransactionalEventListener(AFTER_COMMIT)`. Tạo tình huống rollback để so sánh.

### Bài 6 — Delete callbacks

Thử `repository.delete(order)` và `repository.deleteById(id)`. Quan sát callback nào được gọi. Giải thích khác biệt dựa trên việc callback cần aggregate instance.

### Bài 7 — Modifying query

Viết một phương thức `@Modifying @Query` để cập nhật trạng thái đơn hàng. Xác nhận callback save không tự chạy và quyết định nơi đặt auditing/notification.

### Bài 8 — Async event

Cấu hình event listener bất đồng bộ. Quan sát event có thể hoàn tất sau callback hoặc sau khi method save trả về. Giải thích vì sao logic thay đổi entity cần nằm trong EntityCallback.

## 16. Tài liệu tham khảo chính thức

- [Spring Data Relational — Lifecycle Events](https://docs.spring.io/spring-data/relational/reference/jdbc/events.html): các lifecycle event, callback được hỗ trợ và thứ tự các giai đoạn persist/load/delete.
- [Spring Data Commons — Entity Callbacks](https://docs.spring.io/spring-data/commons/reference/entity-callbacks.html): cách triển khai, đăng ký và sắp xếp EntityCallback; quan hệ thứ tự giữa event và callback.
- [Spring Data Relational — BeforeConvertCallback API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/relational/core/mapping/event/BeforeConvertCallback.html): thời điểm callback chạy và lý do dùng nó để gán ID.
- [Spring Data Relational — BeforeSaveCallback API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/relational/core/mapping/event/BeforeSaveCallback.html): callback sau khi AggregateChange được tạo.
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): dùng `@TransactionalEventListener` để xử lý event theo phase của transaction.
- [Spring Framework — Application Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html): cơ chế publish/subscribe event trong ApplicationContext và thực thi đồng bộ/bất đồng bộ.

EntityCallback và ApplicationEvent cùng tham gia vào lifecycle của Spring Data JDBC nhưng có trách nhiệm riêng. Callback là điểm mở rộng có thứ tự, trả về entity để pipeline tiếp tục xử lý; event là thông báo cho listener. Nắm được thứ tự event trước callback ở từng checkpoint, vị trí tạo AggregateChange, thời điểm chạy SQL và ranh giới transaction sẽ giúp đặt đúng logic vào đúng nơi và tránh phụ thuộc vào side effect chưa commit.
