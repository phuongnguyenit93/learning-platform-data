# BeforeSaveCallback, AfterSaveCallback và AggregateChange

Trong Spring Data JDBC, thao tác lưu một aggregate không chỉ là gửi một câu INSERT hoặc UPDATE. Spring Data trước tiên xác định aggregate mới hay đã tồn tại, chuyển aggregate thành một kế hoạch gồm các thao tác cơ sở dữ liệu, thực thi kế hoạch đó rồi trả kết quả cho caller. **BeforeSaveCallback**, **AfterSaveCallback** và **AggregateChange** cung cấp các điểm mở rộng để quan sát hoặc điều chỉnh quá trình này.

Ba khái niệm có quan hệ trực tiếp nhưng vai trò khác nhau:

- **BeforeSaveCallback** chạy sau khi Spring Data đã tạo kế hoạch thay đổi, nhưng trước khi SQL được thực thi.
- **AggregateChange** mô tả các thao tác cần thực hiện để lưu hoặc xóa toàn bộ aggregate.
- **AfterSaveCallback** chạy sau khi các thao tác SQL của aggregate đã được thực thi và có thể trả lại một instance đã chỉnh sửa cho caller.

Các callback này được gọi cho aggregate root trong đường persistence do Spring Data JDBC quản lý. Chúng không tự chạy cho mọi câu SQL trong ứng dụng; đặc biệt, derived query và method dùng @Query không kích hoạt save callbacks.

## 1. Vị trí của callback trong vòng đời lưu aggregate

Khi ứng dụng gọi repository.save(aggregate) hoặc lưu aggregate qua JdbcAggregateTemplate, Spring Data JDBC thực hiện quy trình khái quát sau:

1. Xác định aggregate mới hay đã tồn tại để quyết định INSERT hay UPDATE.
2. Gọi BeforeConvertCallback và phát hành BeforeConvertEvent.
3. Chuyển aggregate thành AggregateChange chứa các DbAction cần thực hiện.
4. Gọi BeforeSaveCallback và phát hành BeforeSaveEvent.
5. Thực thi các câu SQL tương ứng với kế hoạch thay đổi.
6. Gọi AfterSaveCallback và phát hành AfterSaveEvent.

~~~mermaid
flowchart TD
    A[repository.save aggregate] --> B[Quyết định INSERT hay UPDATE]
    B --> C[BeforeConvertCallback]
    C --> D[Tạo AggregateChange và DbAction]
    D --> E[BeforeSaveCallback]
    E --> F[Thực thi SQL]
    F --> G[AfterSaveCallback]
    G --> H[Trả aggregate đã lưu]
~~~

Thứ tự này quan trọng vì mỗi callback nhìn thấy một trạng thái khác nhau:

- BeforeConvertCallback nhận aggregate trước khi chuyển thành kế hoạch SQL.
- BeforeSaveCallback nhận aggregate và kế hoạch thay đổi đã được tạo.
- AfterSaveCallback nhận aggregate sau khi các câu SQL đã chạy.

Nếu cần gán một ID do ứng dụng tự tạo trước khi Spring Data quyết định giá trị ID có được gửi xuống database hay không, hãy dùng BeforeConvertCallback. BeforeSaveCallback chạy sau bước quyết định insert/update và sau khi kế hoạch đã được tạo, vì vậy không phải nơi phù hợp để tạo ID mới.

## 2. AggregateChange là gì?

AggregateChange nằm trong package org.springframework.data.relational.core.conversion. Nó biểu diễn thay đổi cần thực hiện trên một aggregate theo ranh giới aggregate root.

Một aggregate có thể bao gồm root và các entity con được ánh xạ qua @MappedCollection. Khi lưu root, Spring Data JDBC tạo các DbAction để biểu diễn các thao tác cần thiết, ví dụ:

- Insert aggregate root mới.
- Update aggregate root đã tồn tại.
- Insert entity con mới.
- Update hoặc delete entity con theo trạng thái collection.
- Xóa các hàng thuộc aggregate theo thứ tự phù hợp với quan hệ phụ thuộc.

AggregateChange là mô hình kế hoạch persistence, không phải một câu SQL duy nhất. Một lần save root có thể tạo nhiều DbAction và nhiều câu SQL.

API AggregateChange cung cấp một số thông tin để quan sát kế hoạch:

| API | Ý nghĩa |
|---|---|
| getKind() | Loại thay đổi aggregate, ví dụ save hoặc delete |
| getEntityType() | Kiểu của aggregate root |
| forEachAction(consumer) | Duyệt các DbAction trong kế hoạch |

Trong callback BeforeSave, tham số cụ thể là MutableAggregateChange<T>. MutableAggregateChange mở rộng AggregateChange và cho phép thay đổi kế hoạch, ví dụ thêm DbAction qua addAction(...). Vì vậy, khi nói về hợp đồng callback, cần phân biệt interface đọc chung AggregateChange với kiểu mutable mà BeforeSaveCallback nhận.

## 3. Ví dụ aggregate root

Giả sử ứng dụng quản lý đơn hàng:

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_orders")
public record PurchaseOrder(
        @Id Long id,
        @Version Long version,
        String orderNumber,
        String status,
        BigDecimal total,
        Instant createdAt
) {}
~~~

Repository:

~~~java
import org.springframework.data.repository.CrudRepository;

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {
}
~~~

Một lần lưu:

~~~java
PurchaseOrder order = new PurchaseOrder(
        null,
        null,
        "PO-2026-001",
        "NEW",
        new BigDecimal("250.00"),
        Instant.now()
);

PurchaseOrder saved = repository.save(order);
~~~

Spring Data JDBC xác định entity mới theo quy tắc nhận diện của repository, tạo kế hoạch insert root và thực thi SQL. Sau khi database sinh ID, aggregate được trả về với thông tin ID/version tương ứng theo mapping.

Callbacks cho PurchaseOrder có thể quan sát các giai đoạn của lần lưu này mà không phải tự viết lại toàn bộ repository.

## 4. BeforeSaveCallback: chạy sau khi kế hoạch thay đổi được tạo

BeforeSaveCallback thuộc package:

~~~java
org.springframework.data.relational.core.mapping.event
~~~

Chữ ký trong Spring Data Relational hiện hành:

~~~java
public interface BeforeSaveCallback<T> {
    T onBeforeSave(T aggregate, MutableAggregateChange<T> aggregateChange);
}
~~~

Callback nhận hai đối số:

- Aggregate root đang được lưu.
- MutableAggregateChange chứa các DbAction đã được tạo cho lần lưu đó.

Callback có thể trả về cùng aggregate hoặc một instance khác; đồng thời có thể quan sát hoặc điều chỉnh MutableAggregateChange trước khi các thao tác SQL được thực thi.

Ví dụ callback ghi log kế hoạch:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.relational.core.conversion.MutableAggregateChange;
import org.springframework.data.relational.core.mapping.event.BeforeSaveCallback;
import org.springframework.stereotype.Component;

@Component
public class PurchaseOrderBeforeSaveCallback
        implements BeforeSaveCallback<PurchaseOrder> {

    private static final Logger log =
            LoggerFactory.getLogger(PurchaseOrderBeforeSaveCallback.class);

    @Override
    public PurchaseOrder onBeforeSave(
            PurchaseOrder aggregate,
            MutableAggregateChange<PurchaseOrder> aggregateChange
    ) {
        log.debug(
                "Saving aggregate type={}, kind={}",
                aggregateChange.getEntityType().getSimpleName(),
                aggregateChange.getKind()
        );

        aggregateChange.forEachAction(action ->
                log.debug(
                        "Planned database action: {}",
                        action.getClass().getSimpleName()
                )
        );

        return aggregate;
    }
}
~~~

Đây là vị trí hữu ích để ghi nhận kế hoạch persistence, kiểm tra loại thay đổi hoặc bổ sung một DbAction chuyên biệt khi ứng dụng thực sự cần kiểm soát sâu quá trình lưu.

### Vì sao tham số là MutableAggregateChange?

AggregateChange mô tả kế hoạch và cung cấp khả năng duyệt các thao tác. MutableAggregateChange mở rộng interface đó với khả năng thêm action. BeforeSaveCallback cần kiểu mutable vì callback có thể điều chỉnh kế hoạch trước khi SQL chạy.

Không nên thay đổi DbAction tùy tiện. Các action có thể phụ thuộc vào ID do action trước sinh ra, đường dẫn property trong aggregate, thứ tự insert/delete và optimistic locking. Thêm một action không hợp lệ có thể làm sai thứ tự persistence hoặc phá vỡ tính nhất quán của aggregate.

Nếu chỉ cần quan sát kế hoạch, dùng forEachAction và không sửa nó.

## 5. BeforeSaveCallback khác BeforeConvertCallback

Hai callback này có tên gần nhau nhưng chạy ở hai thời điểm khác nhau:

| Callback | Thời điểm | Dùng phù hợp cho |
|---|---|---|
| BeforeConvertCallback | Trước khi aggregate được chuyển thành kế hoạch DbAction | Chuẩn hóa hoặc thay đổi dữ liệu aggregate trước khi tạo SQL actions; gán ID do ứng dụng quản lý |
| BeforeSaveCallback | Sau khi AggregateChange/DbAction đã được tạo, trước khi SQL chạy | Quan sát hoặc điều chỉnh kế hoạch persistence đã tạo |
| AfterSaveCallback | Sau khi SQL actions được thực thi | Quan sát kết quả lưu, dùng thông tin ID/version đã có, tạo instance trả về |

Ví dụ, nếu muốn gán mã đơn hàng khi chưa có:

~~~java
import java.util.UUID;
import org.springframework.data.relational.core.mapping.event.BeforeConvertCallback;
import org.springframework.stereotype.Component;

@Component
public class PurchaseOrderBeforeConvertCallback
        implements BeforeConvertCallback<PurchaseOrder> {

    @Override
    public PurchaseOrder onBeforeConvert(PurchaseOrder aggregate) {
        if (aggregate.orderNumber() != null
                && !aggregate.orderNumber().isBlank()) {
            return aggregate;
        }

        return new PurchaseOrder(
                aggregate.id(),
                aggregate.version(),
                "PO-" + UUID.randomUUID(),
                aggregate.status(),
                aggregate.total(),
                aggregate.createdAt()
        );
    }
}
~~~

Ví dụ minh họa việc thay đổi aggregate trước khi tạo kế hoạch lưu. Với ID được database sinh, không tự gán ID ở callback này nếu ứng dụng muốn Spring Data JDBC để database cấp ID. Nếu ứng dụng dùng ID do client/ứng dụng tạo, hãy tuân theo chiến lược ID và quy tắc isNew của entity.

BeforeSaveCallback chạy muộn hơn. Việc thay đổi aggregate được trả về từ callback không phải cách đáng tin cậy để sửa các DbAction đã được tạo từ dữ liệu trước đó. Nếu mục tiêu là thay đổi property persistent trước khi SQL plan được xây dựng, dùng BeforeConvertCallback.

## 6. Điều chỉnh MutableAggregateChange

MutableAggregateChange có các API như addAction(DbAction<?>). Với các kiểu RootAggregateChange cụ thể, API còn có thể cung cấp thao tác đặt root hoặc root action. Đây là các API mức thấp dành cho trường hợp cần tích hợp thao tác persistence tùy chỉnh.

AggregateChange cho phép duyệt action:

~~~java
aggregateChange.forEachAction(action -> {
    // Quan sát một DbAction trong kế hoạch.
});
~~~

MutableAggregateChange cho phép thêm action:

~~~java
mutableAggregateChange.addAction(customDbAction);
~~~

Đoạn thứ hai chỉ là hình dạng API, không phải ví dụ hoàn chỉnh để tạo DbAction. Việc tạo DbAction đúng cần biết kiểu action, root, property path, ID phụ thuộc, metadata và thứ tự thực thi. Không nên tự thêm action chỉ để ghi audit đơn giản nếu một application service hoặc transactional outbox có thể diễn đạt use case rõ hơn.

### AggregateChange không phải change log nghiệp vụ

Kế hoạch DbAction mô tả thao tác persistence mà Spring Data JDBC cần thực hiện. Nó không nhất thiết mô tả đầy đủ ý nghĩa nghiệp vụ như “đơn hàng được thanh toán”, “khách hàng đổi địa chỉ” hay “tồn kho được đặt chỗ”.

Không nên dùng danh sách DbAction như một event domain ổn định để phát ra bên ngoài. Cấu trúc action có thể thay đổi khi mapping aggregate, framework hoặc cách lưu collection thay đổi. Nếu cần domain event, hãy mô hình hóa event theo ngôn ngữ nghiệp vụ và phát hành theo cơ chế phù hợp.

## 7. AfterSaveCallback: chạy sau khi SQL được thực thi

AfterSaveCallback thuộc package org.springframework.data.relational.core.mapping.event.

Chữ ký:

~~~java
public interface AfterSaveCallback<T> {
    T onAfterSave(T aggregate);
}
~~~

Callback nhận aggregate đã được lưu. Với insert dùng generated ID, instance được chuyển tới giai đoạn after-save có thể mang ID đã được nhận từ database. Nếu aggregate có @Version, version cũng được Spring Data JDBC quản lý trong đường save chuẩn.

Ví dụ:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.relational.core.mapping.event.AfterSaveCallback;
import org.springframework.stereotype.Component;

@Component
public class PurchaseOrderAfterSaveCallback
        implements AfterSaveCallback<PurchaseOrder> {

    private static final Logger log =
            LoggerFactory.getLogger(PurchaseOrderAfterSaveCallback.class);

    @Override
    public PurchaseOrder onAfterSave(PurchaseOrder aggregate) {
        log.info(
                "Saved purchase order id={}, version={}, number={}",
                aggregate.id(),
                aggregate.version(),
                aggregate.orderNumber()
        );

        return aggregate;
    }
}
~~~

AfterSaveCallback có thể trả về cùng instance hoặc một instance đã chỉnh sửa. Với aggregate bất biến như record, callback có thể tạo một record mới để trả về cho caller. Tuy nhiên, SQL của lần save đã chạy trước callback; thay đổi trong instance được trả về không tự động tạo thêm UPDATE xuống database.

Nếu callback chỉ thêm thông tin tính toán vào instance trả về, caller có thể nhận thông tin đó nhưng database vẫn giữ dữ liệu đã được lưu ở bước trước. Nếu cần lưu một giá trị persistent, hãy thay đổi aggregate trước khi lưu hoặc thực hiện một thao tác persistence riêng trong transaction phù hợp.

## 8. AfterSave không có nghĩa transaction đã commit

Đây là khác biệt quan trọng:

- **AfterSaveCallback** chạy sau khi Spring Data JDBC đã thực thi các DbAction của lần lưu.
- **Transaction commit** xảy ra khi ranh giới transaction kết thúc thành công.

Nếu save chạy bên trong một service method có @Transactional, AfterSaveCallback thường được gọi khi transaction vẫn còn mở. Các câu SQL có thể đã chạy nhưng chưa commit.

~~~mermaid
sequenceDiagram
    participant S as Service
    participant R as Repository
    participant C as AfterSaveCallback
    participant DB as Database
    S->>R: save(aggregate)
    R->>DB: INSERT / UPDATE / child actions
    DB-->>R: SQL completed
    R->>C: onAfterSave(aggregate)
    C-->>R: aggregate
    R-->>S: saved aggregate
    S->>S: Các bước nghiệp vụ tiếp theo
    S->>DB: Transaction commit khi method kết thúc
~~~

Nếu AfterSaveCallback ném RuntimeException trong cùng transaction và exception làm transaction rollback, các thay đổi SQL trước đó có thể bị rollback. Nhưng nếu callback đã gửi email, gọi HTTP hoặc phát message ra broker bên ngoài, các tác động ngoài database đó không tự rollback.

Vì vậy, không nên hiểu AfterSaveCallback là điểm an toàn để phát hành side effect không thể đảo ngược. Nếu cần chạy việc chỉ sau khi commit, hãy dùng cơ chế after-commit như TransactionalEventListener với phase AFTER_COMMIT, hoặc transactional outbox nếu cần độ tin cậy cao giữa database và message broker.

## 9. Callback chỉ áp dụng cho aggregate root

Spring Data JDBC tổ chức persistence theo aggregate. Các entity con trong @MappedCollection được lưu như một phần của aggregate root.

Callbacks và lifecycle events của Spring Data JDBC được gọi cho **aggregate root**. Một callback khai báo cho kiểu child không tự được gọi riêng mỗi khi child được insert/update/delete trong quá trình lưu root.

Ví dụ:

~~~java
@Table("purchase_orders")
public record PurchaseOrder(
        @Id Long id,
        String orderNumber,
        @MappedCollection(idColumn = "order_id")
        List<OrderLine> lines
) {}

public record OrderLine(
        String sku,
        int quantity
) {}
~~~

Khi lưu PurchaseOrder, callback nhận PurchaseOrder và AggregateChange mô tả kế hoạch lưu toàn bộ aggregate. Không nên kỳ vọng một BeforeSaveCallback<OrderLine> được gọi riêng cho từng OrderLine.

Nếu cần xử lý child, có thể duyệt dữ liệu child qua aggregate root hoặc quan sát DbAction trong AggregateChange. Nếu một child thực sự cần lifecycle và transaction độc lập, hãy xem lại ranh giới aggregate thay vì dựa vào callback riêng cho child.

## 10. Callback không được gọi cho derived query và @Query

Save/delete callbacks được tích hợp với quy trình persistence aggregate. Chúng không được gọi cho derived query methods hoặc annotated query methods.

Ví dụ:

~~~java
@Modifying
@Query("UPDATE purchase_orders SET status = :status WHERE id = :id")
int updateStatusDirectly(Long id, String status);
~~~

Câu UPDATE trên được thực thi theo query method tùy chỉnh. Spring Data JDBC không xây kế hoạch save aggregate thông thường cho từng root bị tác động, nên không thể xác định và gọi BeforeSaveCallback/AfterSaveCallback cho từng aggregate bị cập nhật.

Tương tự, một derived delete query không đồng nghĩa với việc gọi callback delete cho từng aggregate bị ảnh hưởng.

Nếu use case dùng @Query hoặc SQL trực tiếp nhưng vẫn cần audit, domain event hoặc cập nhật read model, hãy điều phối phần đó ở application service/custom repository theo cách rõ ràng. Không phụ thuộc vào callback vốn không được kích hoạt trong đường query đó.

## 11. Đăng ký callback trong Spring ApplicationContext

Spring Data tìm các EntityCallback bean trong ApplicationContext. Có thể đăng ký bằng @Component:

~~~java
@Component
public class PurchaseOrderAfterSaveCallback
        implements AfterSaveCallback<PurchaseOrder> {

    @Override
    public PurchaseOrder onAfterSave(PurchaseOrder aggregate) {
        return aggregate;
    }
}
~~~

Hoặc khai báo bean bằng @Bean:

~~~java
@Configuration
public class PersistenceCallbackConfiguration {

    @Bean
    AfterSaveCallback<PurchaseOrder> purchaseOrderAfterSaveCallback() {
        return aggregate -> {
            // Xử lý đồng bộ, ngắn gọn.
            return aggregate;
        };
    }
}
~~~

Generic type giúp callback được liên kết với domain type tương ứng. Nên dùng implementation class có generic rõ ràng nếu cần type filtering và hành vi dễ kiểm thử. Callback dạng lambda không thể hiện thông tin generic ở runtime theo cách giống một class cụ thể, nên khi có nhiều domain type hoặc nhiều callback, implementation class thường rõ ràng hơn.

Không cần tự gọi callback trong service. Hãy để Spring Data JDBC gọi callback tại lifecycle checkpoint tương ứng.

## 12. Thứ tự khi có nhiều callback

Một aggregate có thể có nhiều callback cùng loại. Spring Data EntityCallback API hỗ trợ sắp xếp callback thông qua Ordered hoặc @Order.

Ví dụ:

~~~java
@Component
@Order(100)
public class FirstPurchaseOrderCallback
        implements BeforeSaveCallback<PurchaseOrder> {

    @Override
    public PurchaseOrder onBeforeSave(
            PurchaseOrder aggregate,
            MutableAggregateChange<PurchaseOrder> change
    ) {
        return aggregate;
    }
}

@Component
@Order(200)
public class SecondPurchaseOrderCallback
        implements BeforeSaveCallback<PurchaseOrder> {

    @Override
    public PurchaseOrder onBeforeSave(
            PurchaseOrder aggregate,
            MutableAggregateChange<PurchaseOrder> change
    ) {
        return aggregate;
    }
}
~~~

Thứ tự thấp hơn được xử lý trước theo quy tắc ordering của Spring. Khi nhiều callback cùng thay đổi aggregate hoặc MutableAggregateChange, thứ tự trở thành một phần của hành vi ứng dụng. Hãy khai báo order rõ ràng nếu callback phụ thuộc kết quả của callback khác.

Không nên dựa vào thứ tự đăng ký bean hoặc thứ tự quét component nếu logic yêu cầu một thứ tự xác định.

## 13. Callback và ApplicationEvent khác nhau thế nào?

Spring Data JDBC cung cấp cả EntityCallback và lifecycle event như BeforeSaveEvent/AfterSaveEvent.

| Tiêu chí | EntityCallback | Lifecycle event |
|---|---|---|
| Mục đích | Hook đồng bộ để kiểm tra/chỉnh sửa entity hoặc kế hoạch persistence | Thông báo một mốc lifecycle đã xảy ra |
| Kiểu trả về | Có thể trả instance đã chỉnh sửa | Listener không thay thế entity bằng giá trị trả về |
| Thứ tự | EntityCallback API hỗ trợ ordering và đảm bảo gọi theo thứ tự | Phụ thuộc ApplicationEventMulticaster; có thể cấu hình async |
| Immutable aggregate | Phù hợp vì callback trả instance mới | Event listener không phải cơ chế thay thế entity |
| Sử dụng | Chuẩn hóa dữ liệu, kiểm tra hoặc điều chỉnh change plan | Logging, metrics, notification và quan sát lifecycle |

Callbacks được khuyến nghị khi cần thay đổi entity, đặc biệt với kiểu immutable. Events phù hợp khi chỉ cần thông báo cho listener.

Nếu ApplicationEventMulticaster được cấu hình dùng TaskExecutor, event có thể được xử lý bất đồng bộ và không còn bảo đảm thứ tự thực thi giống callback đồng bộ. Không dùng event async để thay đổi entity đang được lưu.

## 14. Callback và transaction

Callback được gọi bên trong quy trình persistence của Spring Data JDBC. Khi thao tác save nằm trong transaction Spring, callback chạy trong cùng luồng xử lý và trước khi ranh giới transaction kết thúc.

Một số nguyên tắc:

- Giữ callback ngắn và có thể dự đoán.
- Tránh gọi dịch vụ ngoài có độ trễ cao trong callback.
- Không tự mở connection hoặc tự commit transaction.
- Nếu callback ném exception, để exception được xử lý theo chính sách transaction của use case.
- Không xem AfterSaveCallback là after-commit hook.
- Nếu cần audit cùng transaction, ghi audit bằng repository/JDBC trong transaction hoặc dùng outbox.
- Nếu cần thông báo sau commit, dùng TransactionalEventListener(AFTER_COMMIT) hoặc cơ chế tương đương.

Callback không tự tạo một transaction mới chỉ vì nó được gọi. Nó tham gia context persistence hiện tại. Transaction boundary vẫn do repository/template và application service cùng transaction manager quyết định.

## 15. Các giới hạn khi dùng AggregateChange

AggregateChange là abstraction ở mức nội bộ persistence. Dù API cho phép duyệt action và MutableAggregateChange cho phép thêm action, không nên coi đây là một extension point thay thế toàn bộ repository.

Các giới hạn cần nhớ:

- Kế hoạch được tạo từ mapping metadata và trạng thái aggregate tại thời điểm save.
- DbAction có thể phụ thuộc ID của action trước đó.
- Thứ tự action phản ánh dependency giữa root và child.
- Thay đổi kế hoạch sai có thể phá vỡ optimistic locking hoặc referential integrity.
- Cấu trúc DbAction là chi tiết persistence, không phải domain event public.
- Custom action phải được transaction và data access strategy hỗ trợ.
- Derived query và @Query không tạo kế hoạch aggregate để callbacks save/delete quan sát.

Nếu chỉ cần thêm một audit record, thường application service/outbox rõ ràng hơn việc thêm DbAction tùy chỉnh vào AggregateChange. Chỉ chỉnh MutableAggregateChange khi hiểu rõ API, dependency và thứ tự thực thi của các action.

## 16. Ví dụ đầy đủ: callback trước và sau khi lưu

Ví dụ này kết hợp callback trước để quan sát kế hoạch và callback sau để ghi nhận ID/version đã lưu.

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.relational.core.conversion.MutableAggregateChange;
import org.springframework.data.relational.core.mapping.event.BeforeSaveCallback;
import org.springframework.data.relational.core.mapping.event.AfterSaveCallback;
import org.springframework.stereotype.Component;

@Component
public class PurchaseOrderLifecycleCallback
        implements BeforeSaveCallback<PurchaseOrder>,
                   AfterSaveCallback<PurchaseOrder> {

    private static final Logger log =
            LoggerFactory.getLogger(PurchaseOrderLifecycleCallback.class);

    @Override
    public PurchaseOrder onBeforeSave(
            PurchaseOrder aggregate,
            MutableAggregateChange<PurchaseOrder> change
    ) {
        log.debug(
                "Before save: type={}, kind={}",
                change.getEntityType().getSimpleName(),
                change.getKind()
        );

        change.forEachAction(action ->
                log.debug("Action: {}", action.getClass().getSimpleName())
        );

        return aggregate;
    }

    @Override
    public PurchaseOrder onAfterSave(PurchaseOrder aggregate) {
        log.info(
                "After save: id={}, version={}, orderNumber={}",
                aggregate.id(),
                aggregate.version(),
                aggregate.orderNumber()
        );

        return aggregate;
    }
}
~~~

Cùng một bean có thể triển khai nhiều callback interface. Spring gọi mỗi method ở checkpoint tương ứng. Nếu logic lớn hơn, có thể tách thành các bean riêng để trách nhiệm dễ kiểm thử và ordering dễ quản lý.

## 17. Kiểm thử callback

Có thể kiểm thử callback ở hai mức.

### Unit test cho logic callback

Nếu callback chỉ kiểm tra thuộc tính hoặc xử lý một AggregateChange, có thể gọi trực tiếp method với object mẫu và một MutableAggregateChange được tạo cho test. Kiểm tra kết quả trả về hoặc các action đã được thêm/sửa.

Unit test phù hợp để xác nhận logic nhỏ, nhưng không chứng minh Spring Data JDBC thực sự đăng ký và gọi callback trong đúng lifecycle.

### Integration test qua repository

Để xác nhận callback được đăng ký và chạy đúng thời điểm, dùng Spring context và database test:

~~~java
@SpringBootTest
class PurchaseOrderCallbackIntegrationTest {

    @Autowired
    PurchaseOrderRepository repository;

    @Autowired
    PurchaseOrderCallbackProbe probe;

    @Test
    void invokesCallbacksWhenSavingAggregate() {
        PurchaseOrder saved = repository.save(
                new PurchaseOrder(
                        null,
                        null,
                        "PO-TEST-1",
                        "NEW",
                        new BigDecimal("10.00"),
                        Instant.now()
                )
        );

        assertNotNull(saved.id());
        assertTrue(probe.beforeSaveCalled());
        assertTrue(probe.afterSaveCalled());
    }
}
~~~

PurchaseOrderCallbackProbe là bean test ghi nhận callback đã chạy. Test thực tế cần reset probe giữa các test để tránh trạng thái dùng chung làm sai kết quả.

Nên có thêm test cho các trường hợp:

- Insert root mới và kiểm tra ID có mặt ở AfterSaveCallback.
- Update root hiện có và kiểm tra version theo cấu hình.
- Save root có child và xác nhận callback được gọi cho root, không phải mỗi child.
- Thực thi derived query hoặc @Query DML và xác nhận save callbacks không được gọi.
- Callback ném exception trong transaction và kiểm tra rollback theo cấu hình.
- Nhiều callback có @Order và xác nhận thứ tự gọi.

## 18. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| BeforeSaveCallback không thấy giá trị vừa đổi | AggregateChange đã được tạo trước callback | Dùng BeforeConvertCallback để thay đổi entity trước khi chuyển đổi |
| ID không được tạo như mong muốn | Cố gán ID ở BeforeSaveCallback sau quyết định insert/update | Gán ID ở BeforeConvertCallback hoặc dùng chiến lược ID phù hợp |
| AfterSaveCallback không chạy khi dùng @Query update | Query method không đi qua aggregate save lifecycle | Điều phối side effect ở service/custom fragment |
| Callback của child không chạy | Callback chỉ được gọi cho aggregate root | Xử lý child qua root hoặc AggregateChange |
| Thay đổi trong AfterSaveCallback không có trong DB | SQL đã chạy trước callback | Sửa dữ liệu trước save hoặc thực hiện persistence riêng |
| Email được gửi dù transaction rollback | AfterSave không đồng nghĩa commit; email là side effect ngoài DB | Dùng after-commit listener hoặc transactional outbox |
| Callback chạy sai thứ tự | Nhiều callback không khai báo order | Dùng @Order hoặc Ordered |
| Thêm DbAction làm lỗi FK/ID | Action không tôn trọng dependency và thứ tự aggregate | Kiểm tra DbAction, root, property path và ID dependency |
| Event listener xử lý không đúng thứ tự | ApplicationEventMulticaster có thể chạy bất đồng bộ | Dùng EntityCallback cho logic cần đồng bộ |
| Callback không được phát hiện | Bean chưa được đăng ký trong ApplicationContext hoặc generic type không phù hợp | Đăng ký @Component/@Bean và kiểm tra domain type |
| Callback không chạy trong batch DML | Derived/annotated query không tạo aggregate lifecycle cho từng hàng | Xử lý batch side effect riêng và có chủ đích |

## 19. Quy trình chọn đúng callback

Khi muốn can thiệp vào quá trình lưu, hãy xác định mục tiêu trước:

1. **Muốn thay đổi aggregate trước khi tạo SQL plan?** Dùng BeforeConvertCallback.
2. **Muốn xem hoặc điều chỉnh kế hoạch DbAction?** Dùng BeforeSaveCallback với MutableAggregateChange.
3. **Muốn quan sát aggregate sau khi SQL đã chạy hoặc thay đổi instance trả về?** Dùng AfterSaveCallback.
4. **Muốn thông báo một thành phần khác về lifecycle?** Cân nhắc event listener.
5. **Muốn chạy side effect chỉ sau commit?** Dùng after-commit event hoặc outbox, không dùng AfterSaveCallback như after-commit hook.
6. **Đang dùng derived query hoặc @Query DML?** Tự điều phối logic liên quan vì save callbacks không được kích hoạt cho các method đó.
7. **Muốn xử lý child?** Thực hiện qua aggregate root và kế hoạch aggregate, không giả định callback riêng cho child.

~~~mermaid
flowchart TD
    A[Cần can thiệp vào lúc save] --> B{Thay đổi entity trước khi tạo SQL plan?}
    B -->|Có| C[BeforeConvertCallback]
    B -->|Không| D{Cần xem hoặc sửa DbAction plan?}
    D -->|Có| E[BeforeSaveCallback + MutableAggregateChange]
    D -->|Không| F{Cần xử lý sau khi SQL chạy?}
    F -->|Có| G[AfterSaveCallback]
    F -->|Không| H{Chỉ cần thông báo?}
    H -->|Có| I[Lifecycle Event]
    H -->|Cần sau commit| J[AFTER_COMMIT hoặc Outbox]
~~~

## 20. Nguyên tắc ghi nhớ

- Spring Data JDBC xác định insert/update, gọi BeforeConvert, tạo AggregateChange, gọi BeforeSave, thực thi SQL rồi gọi AfterSave.
- BeforeSaveCallback nhận aggregate root và MutableAggregateChange<T>; MutableAggregateChange mở rộng AggregateChange.
- AggregateChange mô tả kế hoạch persistence qua các DbAction, có thể duyệt bằng forEachAction.
- MutableAggregateChange cho phép thay đổi kế hoạch, nhưng thêm/sửa DbAction cần hiểu dependency và thứ tự thực thi.
- Dùng BeforeConvertCallback để thay đổi dữ liệu aggregate trước khi kế hoạch SQL được tạo hoặc gán ID theo chiến lược ứng dụng.
- BeforeSaveCallback chạy sau khi kế hoạch đã tạo; không dùng nó như cách đơn giản để thay đổi property trước khi chuyển đổi.
- AfterSaveCallback chạy sau khi SQL đã thực thi và có thể trả một instance aggregate đã chỉnh sửa.
- Thay đổi instance trong AfterSaveCallback không tự động được ghi lại bằng một câu UPDATE mới.
- Callback save/delete chỉ được gọi cho aggregate root và không được kích hoạt bởi derived query hoặc annotated query methods.
- EntityCallback phù hợp với xử lý đồng bộ; lifecycle event phù hợp với thông báo và có thể được xử lý bất đồng bộ tùy multicaster.
- AfterSave không phải after-commit; side effect ngoài database nên dùng after-commit hoặc transactional outbox.
- Đăng ký callback trong ApplicationContext bằng @Component hoặc @Bean; dùng @Order/Ordered khi cần thứ tự rõ ràng.

BeforeSaveCallback, AfterSaveCallback và AggregateChange giúp mở rộng quy trình persistence của Spring Data JDBC tại các mốc có ý nghĩa. Hãy dùng BeforeConvert để chuẩn bị aggregate, BeforeSave để làm việc với kế hoạch DbAction và AfterSave để quan sát kết quả sau SQL. Khi giữ rõ ranh giới aggregate root, callback lifecycle và transaction commit, các phần mở rộng sẽ phối hợp với repository một cách dễ dự đoán mà không biến callback thành nơi chứa toàn bộ nghiệp vụ hoặc side effect ngoài database.

## Tài liệu tham khảo

- [Spring Data Relational — Lifecycle Events](https://docs.spring.io/spring-data/relational/reference/jdbc/events.html)
- [Spring Data Relational — Entity Callbacks](https://docs.spring.io/spring-data/relational/reference/commons/entity-callbacks.html)
- [BeforeSaveCallback API](https://docs.spring.io/spring-data/relational/docs/current/api/org/springframework/data/relational/core/mapping/event/BeforeSaveCallback.html)
- [AfterSaveCallback API](https://docs.spring.io/spring-data/relational/docs/current/api/org/springframework/data/relational/core/mapping/event/AfterSaveCallback.html)
- [AggregateChange API](https://docs.spring.io/spring-data/relational/docs/current/api/org/springframework/data/relational/core/conversion/AggregateChange.html)
- [MutableAggregateChange API](https://docs.spring.io/spring-data/relational/docs/current/api/org/springframework/data/relational/core/conversion/MutableAggregateChange.html)

