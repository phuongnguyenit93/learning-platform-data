# Phạm vi callback trên aggregate root và xử lý thành phần con

Trong **Spring Data Relational JDBC (Spring Data JDBC)**, entity callback và lifecycle event được phát ra theo **aggregate root**. Khi Spring Data JDBC lưu, tải hoặc xóa một aggregate, callback nhận object root đại diện cho toàn aggregate. Các object con như OrderLine hoặc Address được lưu ở bảng riêng vẫn thuộc cùng aggregate, nhưng không nhận một lượt callback độc lập cho từng object.

Điều này có ý nghĩa trực tiếp khi ứng dụng muốn chuẩn hóa dữ liệu, gán audit timestamp, kiểm tra trạng thái hoặc ghi nhận thao tác trên các thành phần con. Muốn xử lý child entity, callback cần đi qua aggregate root chứa nó, sau đó gọi hành vi trên root hoặc duyệt collection con. Không thể đăng ký một callback cho kiểu child rồi kỳ vọng Spring Data JDBC tự gọi callback đó mỗi khi child được insert/update/delete trong quá trình lưu aggregate.

## 1. Aggregate root và thành phần con

Giả sử một đơn hàng gồm root Order và danh sách OrderLine:

~~~text
Order (aggregate root)
├── id
├── status
├── createdAt
└── lines
    ├── OrderLine
    │   ├── sku
    │   └── quantity
    └── OrderLine
        ├── sku
        └── quantity
~~~

Order là điểm truy cập aggregate. OrderLine có thể được lưu trong bảng riêng, nhưng vòng đời của các line được quản lý thông qua Order. Khi gọi repository để lưu Order, Spring Data JDBC tạo các thao tác SQL cần thiết cho root và các thành phần con.

~~~mermaid
flowchart TB
    Repo["OrderRepository.save(order)"]
    Callback["BeforeConvertCallback<Order>"]
    Root["Aggregate root: Order"]
    Child["Order.lines<br/>OrderLine objects"]
    Mapping["Spring Data JDBC<br/>aggregate mapping"]
    SQL["SQL actions for root<br/>and owned children"]
    DB[("Database")]
    After["AfterSaveCallback<Order>"]
    Repo --> Callback --> Root
    Root --> Child
    Root --> Mapping
    Child --> Mapping
    Mapping --> SQL --> DB --> After
~~~

Callback có generic type là `BeforeConvertCallback<Order>`. Khi callback nhận Order, nó có thể đọc và thay đổi dữ liệu trong danh sách lines thông qua API của aggregate. Spring Data JDBC không tự gọi thêm `BeforeConvertCallback<OrderLine>` cho từng phần tử.

## 2. Những callback và event nào được hỗ trợ?

Spring Data JDBC có các callback theo những mốc chính của vòng đời aggregate:

| Thao tác | Callback | Thời điểm |
|---|---|---|
| Lưu | `BeforeConvertCallback<T>` | Sau khi xác định insert/update, trước khi tạo kế hoạch SQL |
| Lưu | `BeforeSaveCallback<T>` | Sau khi aggregate đã được chuyển thành AggregateChange, trước khi chạy SQL |
| Lưu | `AfterSaveCallback<T>` | Sau khi các thao tác SQL lưu aggregate đã chạy |
| Đọc | `AfterConvertCallback<T>` | Sau khi aggregate được dựng từ ResultSet và các property đã được ánh xạ |
| Xóa | `BeforeDeleteCallback<T>` | Trước khi xóa aggregate |
| Xóa | `AfterDeleteCallback<T>` | Sau khi xóa aggregate |

Các callback trên nhận aggregate root. Lifecycle event tương ứng cũng được phát ra cho root, gồm `BeforeConvertEvent`, `BeforeSaveEvent`, `AfterSaveEvent`, `AfterConvertEvent`, `BeforeDeleteEvent` và `AfterDeleteEvent`.

Trong các phiên bản hiện đại, callback đọc sau khi mapping là `AfterConvertCallback`. Một số phiên bản cũ có `AfterLoadCallback` hoặc `AfterLoadEvent` đã được thay thế/deprecated; hãy dùng API phù hợp với phiên bản Spring Data Relational trong dự án.

## 3. Phạm vi callback: root được gọi, child không được gọi riêng

Giả sử aggregate có một Order và ba OrderLine:

~~~text
Order #501
  lines:
    OrderLine #1
    OrderLine #2
    OrderLine #3
~~~

Khi lưu aggregate, callback nhận một object Order:

~~~java
public class OrderBeforeConvertCallback
        implements BeforeConvertCallback<Order> {

    @Override
    public Order onBeforeConvert(Order order) {
        // Được gọi một lần cho aggregate root Order.
        // Có thể truy cập order.getLines() tại đây.
        return order;
    }
}
~~~

Callback không được gọi thêm ba lần cho các OrderLine. Điều này đúng dù mỗi OrderLine được ghi thành một hàng ở bảng order_lines.

| Thành phần | Có callback riêng trong lần lưu Order? | Có thể được xử lý qua callback root? |
|---|---:|---:|
| Order root | Có | Có |
| OrderLine thuộc Order | Không | Có |
| Address embedded trong Order | Không | Có |
| Customer là aggregate khác, chỉ được tham chiếu bằng ID | Không trong callback Order | Không thuộc object graph của Order; cần xử lý riêng |

Điểm phân biệt quan trọng: callback root có thể duyệt những object con thực sự nằm trong aggregate object graph. Nó không tự tải aggregate khác được tham chiếu bằng một ID scalar.

## 4. Cấu trúc aggregate có collection con

Ví dụ entity Order:

~~~java
package com.example.sales.order;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.MappedCollection;
import org.springframework.data.relational.core.mapping.Table;

@Table("sales_orders")
public class Order {

    @Id
    private Long id;

    private String status;
    private Instant updatedAt;

    @MappedCollection(idColumn = "order_id")
    private List<OrderLine> lines = new ArrayList<>();

    protected Order() {
    }

    public Order(List<OrderLine> lines) {
        this.status = "DRAFT";
        this.lines.addAll(lines);
    }

    public Long getId() {
        return id;
    }

    public String getStatus() {
        return status;
    }

    public Instant getUpdatedAt() {
        return updatedAt;
    }

    public List<OrderLine> getLines() {
        return List.copyOf(lines);
    }

    public void prepareForPersistence(Instant now) {
        this.updatedAt = now;
        lines.forEach(line -> line.prepareForPersistence(now));
    }
}
~~~

Child entity:

~~~java
package com.example.sales.order;

import java.time.Instant;

public class OrderLine {

    private String sku;
    private int quantity;
    private Instant updatedAt;

    protected OrderLine() {
    }

    public OrderLine(String sku, int quantity) {
        this.sku = sku;
        this.quantity = quantity;
    }

    public String getSku() {
        return sku;
    }

    public int getQuantity() {
        return quantity;
    }

    public Instant getUpdatedAt() {
        return updatedAt;
    }

    public void prepareForPersistence(Instant now) {
        this.updatedAt = now;
    }
}
~~~

Phương thức `Order.prepareForPersistence` là hành vi của aggregate root. Nó cập nhật metadata trên root và gọi hành vi tương ứng của từng line. Callback chỉ cần gọi một phương thức trên Order; root tự điều phối các thành phần con.

## 5. Xử lý root và child trong BeforeConvertCallback

`BeforeConvertCallback` là hook phù hợp khi muốn thay đổi aggregate trước khi Spring Data JDBC chuyển nó thành kế hoạch các thao tác database. Vì vậy, nếu cần chuẩn hóa hoặc cập nhật dữ liệu trên child trước khi lưu, hãy xử lý ở giai đoạn này.

~~~java
package com.example.sales.order;

import java.time.Clock;

import org.springframework.data.relational.core.mapping.event.BeforeConvertCallback;
import org.springframework.stereotype.Component;

@Component
public class OrderBeforeConvertCallback
        implements BeforeConvertCallback<Order> {

    private final Clock clock;

    public OrderBeforeConvertCallback(Clock clock) {
        this.clock = clock;
    }

    @Override
    public Order onBeforeConvert(Order aggregate) {
        aggregate.prepareForPersistence(clock.instant());
        return aggregate;
    }
}
~~~

Khi repository lưu Order:

1. Spring Data JDBC xác định aggregate là mới hay đã tồn tại.
2. Callback nhận Order root.
3. Callback gọi `prepareForPersistence`, cập nhật `updatedAt` của root và tất cả OrderLine hiện có trong aggregate.
4. Spring Data JDBC chuyển aggregate đã được chuẩn bị thành các thao tác ghi.
5. SQL cho root và child được thực thi.

Không tạo một `BeforeConvertCallback<OrderLine>` để xử lý từng dòng. Hãy giữ logic liên quan đến vòng đời của line trong OrderLine và để Order gọi logic đó.

### Vì sao dùng Clock thay vì gọi Instant.now() trực tiếp?

Inject `Clock` giúp kiểm soát thời gian trong test:

~~~java
@Bean
Clock applicationClock() {
    return Clock.systemUTC();
}
~~~

Test có thể cung cấp một Clock cố định để xác minh timestamp của root và child mà không phụ thuộc thời điểm thực thi.

## 6. BeforeSaveCallback xảy ra sau khi aggregate đã được chuyển đổi

Quy trình save có hai hook trước SQL nhưng chúng có thời điểm khác nhau:

~~~mermaid
flowchart TD
    A["Xác định aggregate mới hay cũ"]
    B["BeforeConvertCallback"]
    C["Tạo AggregateChange / DbAction"]
    D["BeforeSaveCallback"]
    E["Thực thi SQL"]
    F["AfterSaveCallback"]
    A --> B --> C --> D --> E --> F
~~~

`BeforeConvertCallback` chạy trước khi tạo AggregateChange. Đây là nơi phù hợp để thay đổi entity và các child trước khi framework xác định các thao tác ghi.

`BeforeSaveCallback` chạy sau khi aggregate đã được chuyển thành `MutableAggregateChange`. Callback này nhận cả aggregate root và change plan:

~~~java
import org.springframework.data.relational.core.mapping.event.BeforeSaveCallback;
import org.springframework.data.relational.core.conversion.MutableAggregateChange;
import org.springframework.stereotype.Component;

@Component
public class OrderBeforeSaveCallback
        implements BeforeSaveCallback<Order> {

    @Override
    public Order onBeforeSave(
            Order aggregate,
            MutableAggregateChange<Order> aggregateChange) {

        // Có thể kiểm tra aggregate hoặc điều chỉnh AggregateChange
        // cho các trường hợp persistence nâng cao.
        return aggregate;
    }
}
~~~

Ở giai đoạn này, quyết định insert/update và các DbAction đã được tạo. Thay đổi property trên object root/child ở đây không phải cách đáng tin cậy để sửa dữ liệu đã được chuyển vào change plan. Nếu mục tiêu là chuẩn hóa entity hoặc cập nhật field của child, hãy làm trong `BeforeConvertCallback`. Chỉ dùng `MutableAggregateChange` khi thực sự cần can thiệp vào kế hoạch persistence và đã hiểu API của phiên bản đang dùng.

Một trường hợp quan trọng: nếu muốn cấp ID thủ công cho aggregate mới, hãy làm trong `BeforeConvertCallback`. Khi `BeforeSaveCallback` chạy, quyết định ID sẽ được gửi xuống database hay do database tạo đã được xác định.

## 7. AfterSaveCallback cũng chỉ nhận aggregate root

Sau khi các câu SQL lưu aggregate được thực thi, Spring Data JDBC gọi `AfterSaveCallback` với root:

~~~java
import org.springframework.data.relational.core.mapping.event.AfterSaveCallback;
import org.springframework.stereotype.Component;

@Component
public class OrderAfterSaveCallback
        implements AfterSaveCallback<Order> {

    @Override
    public Order onAfterSave(Order aggregate) {
        // Có thể quan sát root sau thao tác lưu.
        // aggregate.getLines() vẫn cho phép truy cập child graph.
        return aggregate;
    }
}
~~~

Nếu cần ghi log tổng số dòng hàng, callback có thể dùng `aggregate.getLines().size()`. Không có một callback AfterSave riêng cho mỗi OrderLine.

Không xem `AfterSaveCallback` là hook sau khi transaction đã commit. Callback chạy sau các thao tác SQL của aggregate, nhưng transaction bao ngoài có thể vẫn chưa commit. Nếu sau đó transaction rollback, một side effect đã gửi ra hệ thống ngoài từ callback không tự được hoàn tác.

Vì vậy, tránh gửi email, gọi HTTP, publish message trực tiếp hoặc thực hiện side effect không thể rollback trong callback. Với yêu cầu phát thông báo sau commit, cân nhắc transactional event listener hoặc transactional outbox.

## 8. AfterConvertCallback khi aggregate được tải

Khi Spring Data JDBC đọc aggregate, framework thực hiện các truy vấn cần thiết, ánh xạ root và các thành phần con, sau đó gọi `AfterConvertCallback`:

~~~java
import org.springframework.data.relational.core.mapping.event.AfterConvertCallback;
import org.springframework.stereotype.Component;

@Component
public class OrderAfterConvertCallback
        implements AfterConvertCallback<Order> {

    @Override
    public Order onAfterConvert(Order aggregate) {
        // Aggregate và các property đã được mapping.
        // Có thể truy cập aggregate.getLines().
        return aggregate;
    }
}
~~~

Callback này có thể dùng để:

- Tính một giá trị transient từ các property đã tải.
- Chuẩn hóa biểu diễn trong bộ nhớ nếu đó là quy tắc phù hợp.
- Kiểm tra invariant cần phát hiện ngay sau khi đọc.

Không dùng callback này để tự tải Customer aggregate hoặc gọi dịch vụ ngoài cho từng Order. Làm vậy dễ tạo N+1 query, phụ thuộc mạng và khiến thao tác đọc một aggregate trở nên khó dự đoán.

Nếu dữ liệu cần hiển thị đến từ aggregate khác, hãy để application service/query layer phối hợp rõ ràng. Nếu giá trị có thể tính bằng SQL hoặc là read model, cân nhắc projection/query chuyên biệt.

## 9. Xử lý child trong callback sau khi đọc

Vì `AfterConvertCallback<Order>` nhận root đã được dựng, có thể gọi phương thức root để xử lý các line:

~~~java
@Override
public Order onAfterConvert(Order aggregate) {
    aggregate.recalculateTransientSummary();
    return aggregate;
}
~~~

Ví dụ root:

~~~java
public void recalculateTransientSummary() {
    // Tính dữ liệu chỉ tồn tại trong bộ nhớ từ lines đã tải.
    this.lineCount = lines.size();
}
~~~

Nếu summary là dữ liệu persistent cần lưu, đừng chỉ tính trong AfterConvert rồi kỳ vọng giá trị đó tự được ghi xuống database. AfterConvert xảy ra trong luồng đọc; muốn cập nhật dữ liệu persistent phải thực hiện một use case ghi riêng hoặc tính bằng database khi truy vấn.

## 10. Callback khi xóa aggregate

Spring Data JDBC có `BeforeDeleteCallback` và `AfterDeleteCallback`. Chúng cũng làm việc với aggregate root:

~~~java
import org.springframework.data.relational.core.mapping.event.BeforeDeleteCallback;
import org.springframework.data.relational.core.mapping.event.AfterDeleteCallback;
import org.springframework.data.relational.core.conversion.MutableAggregateChange;
import org.springframework.stereotype.Component;

@Component
public class OrderDeleteCallback
        implements BeforeDeleteCallback<Order>, AfterDeleteCallback<Order> {

    @Override
    public Order onBeforeDelete(
            Order aggregate,
            MutableAggregateChange<Order> aggregateChange) {

        // Có thể kiểm tra root và duyệt child graph nếu cần.
        // Không dùng thay đổi persistent trên aggregate để thay đổi
        // quyết định xóa đã được tạo.
        return aggregate;
    }

    @Override
    public Order onAfterDelete(Order aggregate) {
        // Aggregate root đã được xóa.
        return aggregate;
    }
}
~~~

Có một giới hạn quan trọng: callback delete chỉ được gọi khi phương thức xóa nhận **instance aggregate** làm tham số, ví dụ `repository.delete(order)`. Các thao tác xóa theo ID hoặc xóa không có tham số như `deleteById(id)`/`deleteAll()` không gọi các callback delete này vì framework không có instance aggregate để chuyển cho callback.

Điều này cũng có nghĩa callback không phải nơi bảo đảm mọi đường xóa trong ứng dụng đều chạy cùng logic. Nếu nghiệp vụ yêu cầu kiểm tra trước khi xóa hoặc ghi audit cho mọi cách xóa, hãy đặt quy tắc trong application service và kiểm soát các đường ghi/xóa được phép.

## 11. Child có cần callback riêng không?

Không. Nếu một child cần xử lý trước khi lưu, hãy đặt hành vi trong child và để root điều phối:

~~~java
public class OrderLine {

    private String sku;
    private int quantity;
    private String normalizedSku;

    public void normalize() {
        this.normalizedSku = sku == null
            ? null
            : sku.trim().toUpperCase(Locale.ROOT);
    }
}
~~~

Root:

~~~java
public void prepareForPersistence(Instant now) {
    this.updatedAt = now;
    lines.forEach(line -> {
        line.normalize();
        line.markUpdated(now);
    });
}
~~~

Callback:

~~~java
@Override
public Order onBeforeConvert(Order aggregate) {
    aggregate.prepareForPersistence(clock.instant());
    return aggregate;
}
~~~

Thiết kế này giữ trách nhiệm rõ ràng:

- Order quyết định khi nào các line được chuẩn bị cùng aggregate.
- OrderLine biết cách chuẩn hóa dữ liệu của chính nó.
- Callback kết nối lifecycle persistence với hành vi aggregate.

Không đặt logic nghiệp vụ quan trọng chỉ trong callback nếu nó phải chạy cả khi domain được thay đổi ngoài Spring Data JDBC. Quy tắc phải luôn đúng nên nằm trong domain method/factory; callback chỉ phù hợp với công việc gắn với persistence lifecycle như audit metadata hoặc chuẩn bị dữ liệu lưu.

## 12. EntityCallback và ApplicationEvent khác nhau thế nào?

Spring Data JDBC có cả entity callback và lifecycle event. Chúng có mục tiêu khác nhau:

| Tiêu chí | EntityCallback | Lifecycle event |
|---|---|---|
| Mục đích | Can thiệp hoặc biến đổi entity trong lifecycle | Thông báo rằng một lifecycle phase đã xảy ra |
| Có thể trả entity đã chỉnh sửa | Có | Event không có cơ chế trả entity thay thế |
| Thứ tự xử lý | Theo pipeline callback; có thể điều khiển bằng order | Phụ thuộc ApplicationEventMulticaster |
| Xử lý bất đồng bộ | Callback synchronous của Spring Data JDBC chạy theo luồng persistence | Event listener có thể được cấu hình chạy async |
| Phù hợp | Chuẩn hóa entity, audit field, kiểm tra trước persistence | Logging, metrics, thông báo và tích hợp event |
| Phạm vi | Aggregate root | Aggregate root |

Entity callback là lựa chọn phù hợp khi cần sửa object, đặc biệt với immutable entity vì callback có thể trả về instance mới. Lifecycle event phù hợp cho notification. Nếu ApplicationEventMulticaster chạy async, không được giả định listener hoàn tất trước khi thao tác persistence tiếp tục.

Ví dụ listener nhận sự kiện trước khi save:

~~~java
import org.springframework.context.ApplicationListener;
import org.springframework.data.relational.core.mapping.event.BeforeSaveEvent;
import org.springframework.stereotype.Component;

@Component
public class OrderSaveListener
        implements ApplicationListener<BeforeSaveEvent<Order>> {

    @Override
    public void onApplicationEvent(BeforeSaveEvent<Order> event) {
        Order order = event.getEntity();
        // Chỉ quan sát/thông báo; event chỉ chứa aggregate root.
    }
}
~~~

Nếu listener cần chạy sau commit, có thể dùng `@TransactionalEventListener(phase = AFTER_COMMIT)` cho event nghiệp vụ do ứng dụng phát ra. Không nhầm lifecycle callback AfterSave với thời điểm transaction commit.

## 13. Callback có được gọi cho derived query và @Query không?

Không phải mọi thao tác SQL trong repository đều đi qua aggregate lifecycle. Spring Data JDBC không thể luôn xác định chính xác aggregate nào bị ảnh hưởng bởi một câu query tùy chỉnh hoặc derived modifying query. Vì vậy, **save/delete related callbacks và events không được gọi cho derived query methods hoặc methods khai báo bằng @Query** theo cơ chế được tài liệu Spring Data JDBC mô tả.

Ví dụ:

~~~java
@Modifying
@Query("UPDATE sales_orders SET status = :status WHERE customer_id = :customerId")
int updateStatusForCustomer(String status, Long customerId);
~~~

Đây là bulk update trực tiếp. Không giả định Spring Data JDBC sẽ tải từng Order, gọi BeforeConvert/BeforeSave cho từng root rồi mới chạy câu SQL. Child rows cũng không tự được chuyển qua callback.

Nếu một bulk update cần audit/version/side effect:

- Đưa logic cần thiết vào SQL hoặc một quy trình application service rõ ràng.
- Cập nhật audit columns/version trong câu lệnh nếu yêu cầu.
- Ghi outbox/audit record trong cùng transaction khi cần bảo đảm.
- Hoặc tải từng aggregate và lưu qua repository nếu bắt buộc phải áp dụng đầy đủ domain lifecycle, chấp nhận chi phí lớn hơn.

Không dựa vào callback như một trigger database toàn cục. Các đường ghi bằng JdbcTemplate, SQL script, stored procedure hoặc ứng dụng khác cũng không tự chạy callback của Spring Data JDBC.

## 14. Thứ tự callback và nhiều callback cùng loại

Entity callback được Spring Data thực thi theo pipeline đồng bộ. Nếu có nhiều bean cùng triển khai một callback cho cùng domain type, có thể dùng `@Order` hoặc `Ordered` để xác định thứ tự:

~~~java
import org.springframework.core.annotation.Order;
import org.springframework.data.relational.core.mapping.event.BeforeConvertCallback;
import org.springframework.stereotype.Component;

@Component
@Order(10)
public class OrderNormalizeCallback
        implements BeforeConvertCallback<Order> {

    @Override
    public Order onBeforeConvert(Order aggregate) {
        aggregate.normalize();
        return aggregate;
    }
}
~~~

~~~java
@Component
@Order(20)
public class OrderAuditCallback
        implements BeforeConvertCallback<Order> {

    @Override
    public Order onBeforeConvert(Order aggregate) {
        aggregate.updateAuditMetadata();
        return aggregate;
    }
}
~~~

Ví dụ đặt normalization trước audit. Nếu callback sau phụ thuộc kết quả callback trước, hãy khai báo order tường minh thay vì dựa vào thứ tự phát hiện bean.

Lambda callback không biểu lộ type generic rõ như class implementation trong một số trường hợp lọc callback. Với callback cần dùng ổn định cho domain type cụ thể, class bean giúp code dễ đọc và xác định type rõ hơn.

## 15. Hiệu năng và giới hạn trách nhiệm

Callback chạy trên đường persistence của aggregate. Khi một truy vấn tải hàng nghìn aggregate, callback đọc có thể được gọi nhiều lần. Một callback nặng có thể làm thay đổi đáng kể thời gian đọc.

Tránh các việc sau trong callback:

- Gọi HTTP hoặc truy cập dịch vụ bên ngoài.
- Truy vấn repository khác cho từng child.
- Chạy truy vấn phụ lặp lại để tính dữ liệu có thể lấy bằng một query.
- Duyệt cấu trúc lớn nhiều lần nếu không cần thiết.
- Gửi message/email trước khi transaction commit.
- Thực hiện logic nghiệp vụ mà các đường ghi khác không đi qua.

Callback nên ngắn, xác định, dễ kiểm thử và gắn với một mốc lifecycle cụ thể. Logic domain nên nằm trong aggregate; orchestration giữa nhiều aggregate thuộc application service.

## 16. Kiểm thử phạm vi callback trên root và child

Một bài test hữu ích là xác minh callback chỉ được gọi cho root dù aggregate có nhiều child:

~~~java
@Test
void beforeConvertCallbackReceivesAggregateRoot() {
    Order order = new Order(List.of(
        new OrderLine("SKU-1", 2),
        new OrderLine("SKU-2", 3),
        new OrderLine("SKU-3", 1)
    ));

    Order result = callback.onBeforeConvert(order);

    assertThat(result).isSameAs(order);
    assertThat(result.getUpdatedAt()).isNotNull();
    assertThat(result.getLines())
        .allSatisfy(line ->
            assertThat(line.getUpdatedAt()).isNotNull()
        );
}
~~~

Ngoài unit test cho callback, integration test nên kiểm tra:

1. Save một Order có nhiều OrderLine: callback root chạy theo aggregate, không chạy riêng từng line.
2. Load Order: AfterConvertCallback nhận root đã có collection con.
3. Delete bằng instance: BeforeDelete/AfterDelete callback được gọi.
4. Delete bằng ID: không kỳ vọng callback delete instance được gọi.
5. Derived delete hoặc @Query bulk update: không kỳ vọng save/delete lifecycle callback chạy cho từng root bị ảnh hưởng.
6. Transaction rollback sau save: không xem AfterSaveCallback là bằng chứng dữ liệu đã commit.
7. Nhiều callback cùng loại: xác minh thứ tự bằng @Order.

Test nên kiểm tra cả dữ liệu trong database và số lần callback được gọi. Chỉ kiểm tra một callback đã chạy không chứng minh child data được chuẩn bị hoặc lưu đúng.

## 17. Các lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Đăng ký callback cho kiểu child và chờ Spring gọi từng child | Callback child không được gọi theo lifecycle aggregate | Đăng ký callback cho root và duyệt child graph |
| Nghĩ mỗi hàng bảng con là một aggregate root | Thiết kế sai phạm vi persistence | Phân biệt child thuộc aggregate với aggregate độc lập |
| Sửa child trong BeforeSave sau khi change plan đã tạo | Giá trị thay đổi có thể không được phản ánh vào DbAction | Sửa root/child trong BeforeConvert |
| Tạo ID mới trong BeforeSave | Quyết định insert và ID strategy đã được xác định | Tạo ID trong BeforeConvert |
| Dùng AfterSave như after-commit hook | Side effect có thể xảy ra dù transaction sau đó rollback | Dùng transactional event/outbox |
| Dùng callback để tải aggregate khác | N+1 query và coupling giữa aggregate | Dùng application service/query layer |
| Nghĩ deleteById gọi BeforeDeleteCallback | Callback delete không có instance aggregate để nhận | Dùng delete(instance) nếu cần callback hoặc xử lý ở service |
| Dựa vào callback cho bulk @Query/derived delete | Các aggregate bị ảnh hưởng không đi qua callback từng root | Đặt logic trong query/service/outbox phù hợp |
| Dùng event listener async để sửa entity | Thay đổi có thể xảy ra quá muộn hoặc không được persistence dùng | Dùng EntityCallback để biến đổi entity |
| Gửi email/message trong callback | Side effect không rollback cùng database | Phát event sau commit hoặc dùng outbox |
| Đặt quá nhiều logic vào callback | Domain khó chạy ngoài Spring Data JDBC | Đưa invariant vào aggregate/domain method |
| Callback làm truy vấn phụ cho mỗi root | Thời gian tải tăng theo số aggregate | Tính dữ liệu trong query hoặc batch |

## 18. Bài thực hành

1. Tạo Order aggregate root có collection OrderLine bằng @MappedCollection.
2. Viết BeforeConvertCallback<Order> và xác minh nó nhận Order root.
3. Trong root, viết prepareForPersistence(Instant now) để cập nhật audit timestamp của root và từng line.
4. Lưu Order có ba line; kiểm tra timestamp của cả root và child trong database.
5. Viết AfterConvertCallback<Order> và xác minh collection line đã được ánh xạ khi callback chạy.
6. Viết BeforeSaveCallback<Order>; quan sát callback nhận MutableAggregateChange sau khi change plan được tạo.
7. Thử đặt việc cấp ID ở BeforeConvert và so sánh với việc gán ID ở BeforeSave.
8. Viết BeforeDeleteCallback<Order> và AfterDeleteCallback<Order>; gọi delete(instance) để kiểm tra.
9. Gọi deleteById và xác minh không kỳ vọng callback delete instance chạy.
10. Viết một bulk @Query update và kiểm tra save/delete callbacks không được gọi cho từng Order bị ảnh hưởng.
11. Đăng ký hai BeforeConvertCallback có @Order khác nhau và ghi nhận thứ tự thực thi.
12. Viết event listener chỉ để log root; không sửa entity trong listener.
13. Tạo transaction rollback sau thao tác save và chứng minh AfterSaveCallback không có nghĩa transaction đã commit.
14. Thiết kế outbox event được ghi trong cùng transaction và phát đi sau commit.

## 19. Ghi nhớ

Spring Data JDBC gọi lifecycle callback và event trên **aggregate root**. Child entity vẫn được lưu/tải/xóa cùng aggregate theo mapping, nhưng không có callback độc lập cho từng child. Khi cần xử lý child, callback root phải duyệt object graph hoặc gọi hành vi domain do root điều phối.

Với thao tác save, dùng BeforeConvert để chuẩn bị root và child trước khi tạo kế hoạch SQL; BeforeSave chạy sau khi AggregateChange đã được tạo; AfterSave chạy sau khi SQL của aggregate đã thực thi. Với thao tác đọc, AfterConvert chạy sau khi aggregate được dựng. Với delete, callback delete chỉ chạy khi xóa bằng aggregate instance; delete theo ID hoặc bulk query không cung cấp callback cho từng root.

Dùng EntityCallback khi cần biến đổi entity theo pipeline có thứ tự. Dùng lifecycle event để thông báo/quan sát. Giữ callback ngắn và tránh side effect ngoài transaction; nếu cần phát thông báo sau commit, dùng transactional event hoặc outbox.

## Tài liệu tham khảo

- [Spring Data Relational — Lifecycle Events](https://docs.spring.io/spring-data/relational/reference/jdbc/events.html)
- [Spring Data Relational — Entity Callbacks](https://docs.spring.io/spring-data/relational/reference/commons/entity-callbacks.html)
- [BeforeConvertCallback API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/relational/core/mapping/event/BeforeConvertCallback.html)
- [BeforeSaveCallback API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/relational/core/mapping/event/BeforeSaveCallback.html)
- [BeforeDeleteCallback API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/relational/core/mapping/event/BeforeDeleteCallback.html)
