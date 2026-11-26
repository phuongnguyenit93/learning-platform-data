# Phân biệt sự kiện miền, lifecycle event và callback

## 1. Một lần xác nhận đơn hàng có nhiều loại thông báo

Một ứng dụng bán hàng có hành vi `confirm()` để xác nhận đơn hàng. Sau đó ứng dụng lưu đơn hàng vào database. Trong cùng luồng xử lý, bạn có thể gặp ba tên gọi:

- `OrderConfirmed`: đơn hàng đã được xác nhận theo quy tắc nghiệp vụ.
- `AfterSaveEvent<Order>`: hạ tầng lưu trữ vừa đi qua một bước lưu entity.
- `BeforeConvertCallback<Order>`: một điểm framework gọi code để chuẩn bị entity trước khi chuyển đổi sang biểu diễn lưu trữ.

Ba tên gọi này trả lời các câu hỏi khác nhau. Nếu dùng thông báo sau mỗi lần lưu để gửi email xác nhận, một lần cập nhật ghi chú cũng có thể gửi lại email dù người dùng không xác nhận đơn hàng lần nữa.

Bài thuộc chương **Sự kiện aggregate** của module **SPRING_DATA_COMMONS**. Mục tiêu là chọn đúng nơi cho ý nghĩa nghiệp vụ, thông báo về vòng đời persistence và thao tác can thiệp vào entity; đồng thời hiểu giới hạn của từng cơ chế khi có transaction hoặc xử lý bất đồng bộ.

## 2. Phân biệt theo ý nghĩa và theo cơ chế gọi

Sự kiện miền được phân loại theo **ý nghĩa nghiệp vụ**. Lifecycle event được phân loại theo **bước vòng đời lưu trữ**. Callback mô tả **cách framework gọi một điểm mở rộng**. Vì vậy, đây không phải ba khái niệm hoàn toàn loại trừ nhau: một lifecycle callback cũng là callback, và phương thức listener nhận event cũng được framework gọi.

Trong bài, khi nói **EntityCallback**, ta chỉ API điểm mở rộng của Spring Data, không dùng từ callback để gom mọi phương thức framework gọi lại.

| Tiêu chí | Sự kiện miền của aggregate | Lifecycle event của store | Spring Data EntityCallback |
| --- | --- | --- | --- |
| Câu hỏi chính | Điều gì đã xảy ra trong nghiệp vụ? | Hạ tầng đang ở bước persistence nào? | Cần kiểm tra hoặc chuẩn bị entity tại checkpoint nào? |
| Ví dụ | `OrderConfirmed` | MongoDB `AfterSaveEvent<Order>` | MongoDB `BeforeConvertCallback<Order>` |
| Nơi xác định ý nghĩa | Mô hình và quy tắc của ứng dụng | Module lưu trữ | Hợp đồng callback của module |
| Dữ liệu quan tâm trong mẫu | Event ID, order ID, thời điểm xác nhận | Entity và thông tin thao tác lưu | Entity đang được xử lý, collection và dữ liệu liên quan |
| Vai trò của kết quả trả về | Payload thông báo cho người nhận | Listener không trả entity thay thế qua hợp đồng event | Có thể trả entity được dùng ở bước tiếp theo |
| Điều không thể suy ra chỉ từ tên | Transaction đã commit | Một thay đổi nghiệp vụ cụ thể đã xảy ra | Một sự kiện nghiệp vụ cần được công bố |

Các phần sau dùng API thực tế để làm rõ bảng này. Không lựa chọn cơ chế chỉ vì class hoặc annotation có chữ `Event`, `Before` hay `After`.

## 3. Sự kiện miền: mô tả một việc có ý nghĩa với nghiệp vụ

`OrderConfirmed` nên được tạo vì một đơn hàng chuyển sang trạng thái đã xác nhận. Nó không nên được tạo chỉ vì một mapper chuyển object sang document hoặc vì một thao tác save được gọi.

Một payload minh họa:

```java
import java.time.Instant;
import java.util.UUID;

public record OrderConfirmed(
        UUID eventId,
        String orderId,
        Instant occurredAt) {
}
```

Trong thiết kế này:

- `eventId` định danh lần xảy ra sự kiện.
- `orderId` giúp người nhận biết aggregate liên quan.
- `occurredAt` là thời điểm hành vi xác nhận được ứng dụng ghi nhận.

Payload không chứa `MongoTemplate`, tên collection hoặc toàn bộ persistence context. Người nhận có thể hiểu ý nghĩa xác nhận đơn hàng mà không cần biết database được dùng.

Spring Data Commons hỗ trợ lấy sự kiện từ phương thức `@DomainEvents` trên aggregate và dọn sau phát hành bằng `@AfterDomainEventPublication`. Phương thức cung cấp sự kiện không nhận tham số, có thể trả một sự kiện hoặc collection. Cơ chế được kích hoạt qua các lời gọi repository được hỗ trợ như `save` và `saveAll`. [Spring Data Commons: Publishing Events from Aggregate Roots](https://docs.spring.io/spring-data/commons/reference/repositories/core-domain-events.html).

Cần phân biệt **thời điểm ghi nhận** với **thời điểm phát hành**: phương thức domain có thể thêm sự kiện vào danh sách trước khi repository thực hiện lưu. Sự kiện đang nằm trong danh sách chờ chưa tự chứng minh dữ liệu đã được ghi thành công.

## 4. Lifecycle event: thông báo về một bước của persistence

Spring Data MongoDB có các thông báo như trước chuyển đổi, trước lưu, sau lưu và sau chuyển đổi từ document về entity. Chúng được xử lý qua hạ tầng application events, chẳng hạn listener kế thừa `AbstractMongoEventListener`. Đây là thông tin gắn với luồng mapping và lưu trữ. [Spring Data MongoDB: Lifecycle Events](https://docs.spring.io/spring-data/mongodb/reference/mongodb/lifecycle-events.html).

Ví dụ `AfterSaveEvent<Order>` cho biết có một bước lưu trong luồng MongoDB tương ứng. Từ thông báo đó, bạn chưa biết nguyên nhân nghiệp vụ là:

- Tạo đơn hàng nháp.
- Xác nhận đơn hàng.
- Sửa địa chỉ giao hàng.
- Cập nhật một thuộc tính kỹ thuật của document.

Tên event kỹ thuật không cung cấp đủ thông tin để phân biệt bốn việc trên. Nếu một listener nhìn thấy `confirmed=true` trên entity rồi luôn phát `OrderConfirmed`, nó vẫn chưa chứng minh trạng thái vừa chuyển từ chưa xác nhận sang đã xác nhận trong lần lưu này.

Lifecycle event hữu ích khi cần quan sát hoạt động persistence hoặc tích hợp với hạ tầng ở bước cụ thể. Trong ví dụ của bài, listener sau lưu chỉ ghi log kỹ thuật; hành vi xác nhận vẫn thuộc aggregate.

Không giả định mỗi object con đều có cùng thông báo như root. Tài liệu MongoDB mô tả lifecycle events chủ yếu cho root và nêu quy tắc riêng cho document references. Khi cần xử lý cấu trúc nhúng, hãy kiểm tra phạm vi module thực sự hỗ trợ. [Spring Data MongoDB: Lifecycle Events](https://docs.spring.io/spring-data/mongodb/reference/mongodb/lifecycle-events.html).

## 5. EntityCallback: một bước trong chuỗi xử lý entity

Entity callbacks cung cấp checkpoint có thứ tự trong chuỗi xử lý và có thể trả entity đã được điều chỉnh. API đồng bộ và reactive được tách riêng; callback cụ thể thường do từng module định nghĩa. Đây là cơ chế được tài liệu Commons khuyến nghị cho việc sửa entity, đặc biệt khi cần thay instance bất biến. [Spring Data Commons: Entity Callbacks](https://docs.spring.io/spring-data/commons/reference/entity-callbacks.html).

Ví dụ, MongoDB `BeforeConvertCallback<T>` nhận entity cùng tên collection và trả entity để chuyển đổi. [API BeforeConvertCallback](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/mapping/event/BeforeConvertCallback.html).

Một callback như vậy có thể phù hợp để áp dụng giá trị kỹ thuật mặc định mà mapping cần. Nó cần trả đúng object dùng cho bước tiếp theo. Với entity bất biến, việc tạo object mới rồi trả lại object cũ sẽ làm mất thay đổi vừa tính.

Checkpoint cũng quyết định dữ liệu nào còn có thể thay đổi. Trong MongoDB `BeforeSaveCallback`, entity đã được chuyển thành `Document`; thay đổi dữ liệu persistent ở giai đoạn này cần xét document, thay vì mong sửa field entity sẽ được chuyển đổi lại. Muốn sửa persistent properties trước conversion, dùng checkpoint phù hợp như `BeforeConvertCallback`. [API BeforeSaveCallback](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/mapping/event/BeforeSaveCallback.html).

Đây là lý do không coi mọi callback có chữ `Before` là tương đương. Cần đọc chữ ký và vị trí callback trong pipeline của đúng module.

## 6. Ví dụ hoàn chỉnh với ba trách nhiệm riêng

Các ví dụ dùng Java 17 và Spring Data MongoDB đồng bộ có phiên bản tương thích. Đặt mỗi public type trong tệp Java riêng thuộc cùng package `example.events`; các đoạn mã lược dòng package. Ứng dụng cần cấu hình kết nối MongoDB, quét repository và quét các component minh họa.

### 6.1. Aggregate ghi nhận việc xác nhận

Để giảm mã quản lý hàng đợi, mẫu dùng `AbstractAggregateRoot`, lớp tiện ích cung cấp `registerEvent`, phương thức cung cấp sự kiện và cơ chế dọn. [API AbstractAggregateRoot](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/AbstractAggregateRoot.html).

```java
import java.time.Instant;
import java.util.Objects;
import java.util.UUID;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.domain.AbstractAggregateRoot;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("orders")
public class Order extends AbstractAggregateRoot<Order> {

    @Id
    private String id;

    private boolean confirmed;

    private int storageSchemaVersion;

    @Version
    private Long version;

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
        registerEvent(new OrderConfirmed(
                UUID.randomUUID(), id, occurredAt));
    }

    void initializeStorageSchemaVersion() {
        if (storageSchemaVersion == 0) {
            storageSchemaVersion = 1;
        }
    }

    int pendingEventCount() {
        return domainEvents().size();
    }

    public String getId() {
        return id;
    }

    public boolean isConfirmed() {
        return confirmed;
    }

    public int getStorageSchemaVersion() {
        return storageSchemaVersion;
    }
}
```

`confirm()` là nơi mẫu này quyết định phát sinh `OrderConfirmed`. `initializeStorageSchemaVersion()` chỉ chuẩn bị một giá trị kỹ thuật cho document; nó không xác nhận đơn hàng và không thêm domain event.

`pendingEventCount()` là phương thức hỗ trợ quan sát trong bài thực hành. Ứng dụng không cần dùng kích thước hàng đợi như một trạng thái nghiệp vụ hoặc bằng chứng transaction thành công.

### 6.2. Callback chuẩn bị dữ liệu trước conversion

```java
import org.springframework.data.mongodb.core.mapping.event.BeforeConvertCallback;
import org.springframework.stereotype.Component;

@Component
public class OrderStorageDefaults implements BeforeConvertCallback<Order> {

    @Override
    public Order onBeforeConvert(Order entity, String collection) {
        entity.initializeStorageSchemaVersion();
        return entity;
    }
}
```

Đây là callback đồng bộ dành cho API MongoDB đồng bộ. Bean được ứng dụng đăng ký để hạ tầng tìm thấy; chỉ viết một class triển khai interface nhưng không đưa vào cấu hình phù hợp chưa đủ chứng minh callback sẽ chạy.

Nếu đổi sang repository reactive, cần chọn callback reactive tương ứng và để thay đổi nằm trong publisher được thực thi. Không dùng `block()` để cố biến callback đồng bộ thành một mắt xích reactive.

### 6.3. Listener quan sát lifecycle event

```java
import org.springframework.data.mongodb.core.mapping.event.AbstractMongoEventListener;
import org.springframework.data.mongodb.core.mapping.event.AfterSaveEvent;
import org.springframework.stereotype.Component;

@Component
public class OrderPersistenceObserver extends AbstractMongoEventListener<Order> {

    private static final System.Logger LOGGER =
            System.getLogger(OrderPersistenceObserver.class.getName());

    @Override
    public void onAfterSave(AfterSaveEvent<Order> event) {
        LOGGER.log(System.Logger.Level.INFO,
                "Persistence after-save: orderId={0}",
                event.getSource().getId());
    }
}
```

Listener này thông báo về persistence. Nó không gửi email xác nhận và không suy ra hành vi nghiệp vụ chỉ từ việc entity được lưu.

### 6.4. Listener nhận sự kiện miền

```java
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class OrderConfirmationObserver {

    private static final System.Logger LOGGER =
            System.getLogger(OrderConfirmationObserver.class.getName());

    @EventListener
    public void on(OrderConfirmed event) {
        LOGGER.log(System.Logger.Level.INFO,
                "Domain confirmation: eventId={0}, orderId={1}",
                event.eventId(), event.orderId());
    }
}
```

Payload là record thông thường, không cần kế thừa `ApplicationEvent`. Spring hỗ trợ phát object và bọc payload khi cần. Tuy nhiên, hợp đồng publisher chỉ mô tả chuyển giao cho multicaster, không tự cam kết kiểu hoặc thời điểm thực thi mọi listener. [API ApplicationEventPublisher](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/ApplicationEventPublisher.html).

### 6.5. Lưu nhiều lần để thấy sự khác biệt

```java
import org.springframework.data.repository.CrudRepository;

public interface OrderRepository extends CrudRepository<Order, String> {
}
```

Với `repository` là bean đã cấu hình:

```java
Order draft = repository.save(Order.draft("order-42"));

draft.confirm(Instant.parse("2026-02-10T09:30:00Z"));
Order confirmed = repository.save(draft);

Order savedAgain = repository.save(confirmed);
```

Trong cấu hình minh họa có bật lifecycle notifications và lượt xử lý thành công, kỳ vọng:

| Thao tác | Ý nghĩa miền mới | Công việc persistence |
| --- | --- | --- |
| Lưu bản nháp | Chưa có `OrderConfirmed` | Callback chuẩn bị schema version; observer thấy lượt lưu |
| Gọi `confirm()` rồi lưu | Có một `OrderConfirmed` | Hạ tầng vẫn thực hiện các bước lưu tương ứng |
| Lưu lại instance đã được xử lý | Không có xác nhận mới | Một lượt lưu khác không tự trở thành một lần xác nhận |

Hành vi của mẫu không có nghĩa mọi hệ thống phải bỏ qua lần gọi xác nhận thứ hai. Đó là quy tắc do ứng dụng minh họa chọn; mô hình thực tế có thể từ chối hoặc xử lý command lặp theo hợp đồng riêng.

## 7. Nhìn một luồng xử lý mà không trộn các mốc

Với mẫu repository đồng bộ, có thể hình dung đường thành công theo sơ đồ rút gọn:

```text
Hành vi domain
  -> đổi trạng thái và ghi nhận OrderConfirmed

repository.save(...)
  -> các checkpoint trước conversion và trước ghi
     -> lifecycle notifications và entity callbacks tương ứng
  -> ghi dữ liệu
  -> các checkpoint sau ghi
  -> cơ chế repository công bố domain events đang chờ
  -> dọn danh sách sự kiện theo cơ chế aggregate
```

Mã nguồn tham chiếu của cơ chế domain events gọi thao tác repository trước rồi công bố sự kiện từ aggregate trong đối số. Đây là chi tiết cần đối chiếu với phiên bản dự án, nhất là khi custom repository hoặc callback trả một instance khác. [Mã nguồn EventPublishingRepositoryProxyPostProcessor](https://github.com/spring-projects/spring-data-commons/blob/main/src/main/java/org/springframework/data/repository/core/support/EventPublishingRepositoryProxyPostProcessor.java).

Sơ đồ không quy định vị trí commit transaction và không mô tả thứ tự hoàn tất của các listener bất đồng bộ. Với một instance được thay thế giữa các bước, hãy kiểm tra riêng object dùng cho persistence, object trả về và object còn giữ hàng đợi domain events.

Tài liệu EntityCallback cũng phân biệt việc công bố store events với việc thực thi callback trong chuỗi. Nếu event listener được cấu hình chạy ở thread khác, thời điểm công bố event không đồng nghĩa listener đã xử lý xong trước bước tiếp theo. [Spring Data Commons: Entity Callbacks](https://docs.spring.io/spring-data/commons/reference/entity-callbacks.html).

## 8. Chọn vị trí theo trách nhiệm cần thực hiện

Hãy bắt đầu từ câu hỏi nghiệp vụ hoặc kỹ thuật cần giải quyết:

| Nhu cầu | Vị trí phù hợp để bắt đầu thiết kế |
| --- | --- |
| Kiểm tra đơn hàng có được xác nhận hay không | Hành vi domain và quy tắc ứng dụng |
| Ghi nhận đơn hàng vừa được xác nhận | Domain event phát sinh từ thay đổi hợp lệ |
| Chuẩn bị giá trị kỹ thuật trước mapping | Entity callback tại checkpoint phù hợp |
| Quan sát số lượt lưu hoặc nạp dữ liệu | Lifecycle observer hoặc công cụ quan sát persistence phù hợp |
| Dọn hàng đợi domain events sau công bố | Cơ chế `@AfterDomainEventPublication` hoặc lớp tiện ích đang dùng |
| Chỉ phản ứng sau commit thành công | Listener gắn với transaction và cấu hình transaction tương ứng |

Không đặt việc kiểm tra quyền xác nhận đơn hàng vào một observer sau lưu chỉ vì observer đang nhận được entity. Khi đó, domain có thể đã bị đổi trước khi observer nhận thông tin.

Cũng không gọi `confirm()` từ một callback chung trước mỗi lần lưu. Callback có thể được dùng ở những luồng lưu khác, chẳng hạn nhập dữ liệu hoặc sửa metadata; việc chuẩn bị persistence không phải bằng chứng người dùng yêu cầu xác nhận.

Một cách tự kiểm tra hữu ích: nếu thay MongoDB bằng một store khác, quy tắc xác nhận đơn hàng có còn đúng không? Nếu có, quy tắc đó nên được diễn đạt ở mô hình hoặc tầng ứng dụng, thay vì phụ thuộc tên một callback MongoDB.

## 9. Sự kiện sau lưu không tự đồng nghĩa sau commit

MongoDB `AfterSaveCallback` là checkpoint sau khi lưu document; tên gọi ấy mô tả bước persistence, không tuyên bố kết quả của một transaction ngoài đang bao quanh lời gọi. [API AfterSaveCallback](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/mapping/event/AfterSaveCallback.html).

`@TransactionalEventListener` gắn listener với phase transaction, mặc định là `AFTER_COMMIT`. Khi không có transaction phù hợp, mặc định listener không chạy; `fallbackExecution` có thể thay đổi chính sách đó. [Spring Framework: Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html).

Giả sử ứng dụng có transaction ngoài được cấu hình đúng:

```text
Bắt đầu transaction ngoài
  -> confirm()
  -> save và các persistence hooks
  -> công bố OrderConfirmed
  -> service tiếp tục xử lý
Commit hoặc rollback transaction ngoài
```

Ở luồng này, việc đã thấy log sau lưu hoặc listener thường đã nhận `OrderConfirmed` chưa đủ kết luận transaction ngoài đã commit. Nếu tác vụ chỉ được thực hiện sau commit, cần dùng hợp đồng phù hợp và kiểm tra rằng event được phát trong transaction mà listener có thể tham gia.

Các ví dụ MongoDB ở phần 6 không tự tạo một transaction ngoài. Chỉ đổi annotation của listener sang `@TransactionalEventListener` mà không có hạ tầng transaction phù hợp có thể khiến người học không thấy listener chạy.

Với tác vụ gửi sang hệ thống khác, cần xác định thêm yêu cầu lưu bền, retry và xử lý trùng. Một callback hoặc application event trong bộ nhớ không tự cung cấp bằng chứng bên ngoài đã nhận thành công.

## 10. Khả năng của từng module phải được kiểm tra riêng

### 10.1. Commons định nghĩa abstraction, module định nghĩa checkpoint

Không có một chữ ký `BeforeSaveCallback` duy nhất dùng nguyên cho mọi store. Package, tham số và dữ liệu có thể thay đổi ở mỗi module. Khi import một interface, hãy kiểm tra nó thuộc MongoDB, Relational hay API khác.

Với Spring Data JDBC, tài liệu mô tả lifecycle events cho aggregate root và các callback theo trình tự chuyển aggregate thành kế hoạch SQL rồi thực thi. Checkpoint trước conversion và trước save có ý nghĩa khác nhau; không dùng vị trí đặt ID của một store làm quy tắc chung cho store khác. [Spring Data JDBC: Lifecycle Events](https://docs.spring.io/spring-data/relational/reference/jdbc/events.html).

### 10.2. Callback JPA là một hệ hợp đồng khác

Jakarta Persistence có các lifecycle callback như `@PrePersist`, `@PostPersist`, `@PreUpdate` và `@PostLoad`, do persistence provider gọi theo quy tắc JPA. Phương thức có thể nằm trên entity hoặc entity listener với chữ ký tương ứng. [Jakarta Persistence: Lifecycle Callback Methods](https://jakarta.ee/specifications/persistence/3.2/jakarta-persistence-spec-3.2#lifecycle-callback-methods).

Không đồng nhất `@PrePersist` với một bean triển khai MongoDB `BeforeConvertCallback`. Chúng cùng là điểm can thiệp vào vòng đời nhưng thuộc hai hệ mapping và hai hợp đồng gọi khác nhau. Một annotation JPA cũng không tự tạo Spring application event có payload nghiệp vụ.

### 10.3. Repository proxy khác đường ghi trực tiếp

Tài liệu domain events của Commons liệt kê các thao tác repository nhận aggregate; `deleteById` không có cùng cơ chế vì implementation có thể xóa mà không nạp aggregate. [Spring Data Commons: Publishing Events from Aggregate Roots](https://docs.spring.io/spring-data/commons/reference/repositories/core-domain-events.html).

Nếu dùng template, raw driver, query update hoặc bulk operation, hãy kiểm tra từng đường thực thi. Một đường có persistence callbacks không tự chứng minh nó cũng công bố danh sách `@DomainEvents` qua repository proxy. Ngược lại, công bố một domain event thủ công không tự kích hoạt toàn bộ lifecycle lưu entity.

## 11. Kiểm thử để phân biệt ý nghĩa và điểm kích hoạt

### 11.1. Kiểm thử domain không cần database

Test JUnit Jupiter dưới đây đặt cùng package với các class minh họa:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Instant;
import org.junit.jupiter.api.Test;

public class OrderEventMeaningTest {

    @Test
    void confirmationCreatesOneBusinessEvent() {
        Order order = Order.draft("order-42");
        Instant time = Instant.parse("2026-02-10T09:30:00Z");

        order.confirm(time);
        order.confirm(time);

        assertTrue(order.isConfirmed());
        assertEquals(1, order.pendingEventCount());
    }

    @Test
    void storagePreparationDoesNotConfirmTheOrder() {
        Order order = Order.draft("order-42");
        var callback = new OrderStorageDefaults();

        Order result = callback.onBeforeConvert(order, "orders");

        assertFalse(result.isConfirmed());
        assertEquals(1, result.getStorageSchemaVersion());
        assertEquals(0, result.pendingEventCount());
    }
}
```

Test thứ hai gọi callback trực tiếp để kiểm tra trách nhiệm của code. Nó chưa chứng minh callback được Spring đăng ký hoặc repository thực sự gọi callback tại checkpoint mong muốn.

### 11.2. Kiểm thử tích hợp qua đúng API

Trong ứng dụng thử nghiệm có store và component thật, cần kiểm tra thêm:

| Tình huống | Điều cần quan sát |
| --- | --- |
| Lưu đơn hàng nháp | Có bước chuẩn bị persistence, chưa có xác nhận miền |
| Xác nhận rồi save | Listener miền nhận đúng event ID và order ID |
| Save lại sau lượt thành công | Persistence có thể tiếp tục, domain event cũ không được phát lại từ hàng đợi |
| Đọc lại document | Schema version đã được lưu, không chỉ đổi trong bộ nhớ |
| Dùng callback trả instance mới | Instance dùng cho bước tiếp theo chứa thay đổi mong muốn |
| Callback hoặc listener báo lỗi | Kiểm tra lỗi trả về và kết quả transaction thực tế |
| Transaction ngoài rollback | Phân biệt listener thường với listener sau commit |
| Listener xử lý bất đồng bộ | Không suy thứ tự hoàn tất chỉ từ log công bố event |
| Ghi qua template hoặc API trực tiếp | Xác định cơ chế nào thực sự được gọi |

Các ví dụ kiểm thử trong bài là hướng dẫn thực hành, không phải báo cáo đã chạy trên dự án. Khi điều tra sai khác, ghi rõ module, phiên bản, API ghi, loại listener và cấu hình transaction thay vì chỉ ghi tên entity.

## 12. Bài tập phân loại và áp dụng

Với mỗi yêu cầu dưới đây, chọn nơi triển khai và giải thích dữ liệu đầu vào cần có:

1. Từ chối xác nhận đơn hàng chưa đủ điều kiện nghiệp vụ.
2. Ghi nhận một lần xác nhận hợp lệ bằng event có ID riêng.
3. Bổ sung phiên bản cấu trúc document trước conversion.
4. Ghi log sau một lượt lưu để hỗ trợ chẩn đoán persistence.
5. Thực hiện phản ứng chỉ khi transaction chứa thay đổi đã commit.

Sau đó chạy luồng lưu nháp, xác nhận và lưu lại như phần 6. Đối chiếu log nghiệp vụ với log persistence: một hành vi xác nhận có thể đi cùng nhiều checkpoint kỹ thuật, còn một lần save có thể không có sự kiện xác nhận mới.

Một lời giải rõ ràng chỉ ra được ý nghĩa nghiệp vụ, điểm kích hoạt, instance dữ liệu được dùng và ranh giới transaction. Khi bốn điều đó đã rõ, domain events, lifecycle events và callbacks có thể phối hợp mà không bị dùng thay cho nhau một cách tùy tiện.
