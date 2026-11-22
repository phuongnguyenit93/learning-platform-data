# Phạm vi callback với Repository, Template và SQL trực tiếp

## 1. Vì sao cần hiểu phạm vi callback?

Spring Data Relational R2DBC cung cấp các callback để can thiệp vào vòng đời của đối tượng được ánh xạ. Chẳng hạn, ứng dụng có thể chuẩn hóa dữ liệu trước khi lưu, bổ sung thông tin audit, hoặc điều chỉnh entity sau khi đọc từ database.

Điểm cần hiểu rõ là callback không phải bộ lọc SQL chạy cho mọi câu lệnh trong ứng dụng. Callback gắn với những điểm cụ thể trong quy trình mapping entity của Spring Data.

Một ứng dụng R2DBC thường có nhiều đường truy cập dữ liệu:

- Repository như ReactiveCrudRepository hoặc R2dbcRepository.
- Template như R2dbcEntityTemplate.
- SQL trực tiếp qua DatabaseClient.
- R2DBC SPI trực tiếp qua Connection, Statement và Result.
- Query tùy chỉnh khai báo bằng @Query hoặc repository fragment.

Các đường này có mức độ tham gia vào vòng đời entity khác nhau. Nếu một quy tắc chỉ được đặt trong callback nhưng một luồng ghi khác dùng SQL trực tiếp, quy tắc đó có thể không được thực thi.

Ví dụ, ứng dụng dùng BeforeConvertCallback để chuẩn hóa mã đơn hàng thành chữ hoa. Repository save có thể đi qua callback này. Nhưng một câu UPDATE được viết trực tiếp bằng DatabaseClient không tự động chạy callback chỉ vì nó cập nhật cùng bảng orders.

Bài học này giải thích callback nào chạy ở từng giai đoạn, những API nào đi qua entity mapping, và cách thiết kế khi ứng dụng kết hợp Repository, Template và SQL trực tiếp.

## 2. Entity callback là gì?

Entity callback là một extension point của Spring Data, cho phép ứng dụng tham gia vào một thời điểm xác định trong vòng đời của entity.

Trong Spring Data R2DBC, các callback store-specific được hỗ trợ gồm:

| Callback | Thời điểm | Mục đích |
|---|---|---|
| BeforeConvertCallback | Trước khi entity được chuyển thành OutboundRow | Chuẩn hóa hoặc bổ sung dữ liệu persistent trước mapping |
| BeforeSaveCallback | Sau khi entity đã được chuyển thành OutboundRow, trước khi ghi | Điều chỉnh hàng dữ liệu sẽ được lưu |
| AfterSaveCallback | Sau khi lưu entity | Điều chỉnh entity được trả về sau thao tác lưu |
| AfterConvertCallback | Sau khi đọc và chuyển Row thành entity | Điều chỉnh entity vừa được materialize |
| AuditingEntityCallback | Trong giai đoạn BeforeConvert | Tự động điền thông tin created/modified theo auditing |

Các callback R2DBC trả về Publisher, thường được triển khai bằng Mono. Vì vậy callback tham gia vào reactive pipeline và không cần tự subscribe.

Các callback được liên kết với kiểu domain thông qua generic type. Ví dụ BeforeConvertCallback<Order> áp dụng cho Order. Spring Data dùng kiểu này để chọn callback phù hợp với entity đang được xử lý.

### 2.1. Callback không phải listener cho mọi câu SQL

Callback được gọi tại điểm Spring Data thực hiện entity mapping. Chúng không phải interceptor toàn cục cho mọi lệnh SQL gửi tới database.

Một callback có thể được gọi khi entity đi qua mapping lifecycle, nhưng không được gọi chỉ vì:

- Một câu SQL chạm vào bảng tương ứng.
- Một câu UPDATE thay đổi cột của entity.
- Một câu SELECT trả về dữ liệu giống entity.
- Một thao tác được chạy trên cùng ConnectionFactory.
- Một method nằm trong repository interface nhưng tự thực thi SQL tùy chỉnh.

Hãy xác định API đang thực hiện thao tác và liệu API đó có đi qua entity lifecycle hay không.

## 3. Vòng đời callback khi ghi entity

Với một thao tác lưu entity thông qua mapping infrastructure, luồng khái niệm thường là:

~~~text
Entity đầu vào
     |
     v
BeforeConvertCallback
     |
     v
Chuyển entity thành OutboundRow
     |
     v
BeforeSaveCallback
     |
     v
Thực thi INSERT hoặc UPDATE
     |
     v
AfterSaveCallback
     |
     v
Entity được trả về
~~~

Mỗi callback có một trách nhiệm khác nhau. Việc chọn đúng điểm rất quan trọng, đặc biệt khi entity bất biến hoặc khi cần thay đổi dữ liệu thực sự được ghi xuống database.

### 3.1. BeforeConvertCallback

BeforeConvertCallback chạy trước khi Spring Data chuyển entity thành OutboundRow. Đây thường là nơi phù hợp để:

- Chuẩn hóa trường persistent.
- Tạo giá trị mặc định trước khi ghi.
- Tính một trường persistent từ dữ liệu của entity.
- Gán mã nghiệp vụ do ứng dụng quản lý.
- Chuẩn bị dữ liệu mà converter sẽ chuyển thành cột.

Ví dụ:

~~~java
import org.reactivestreams.Publisher;
import org.springframework.data.r2dbc.mapping.event.BeforeConvertCallback;
import org.springframework.data.relational.core.sql.SqlIdentifier;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class NormalizeOrderCodeCallback
        implements BeforeConvertCallback<Order> {

    @Override
    public Publisher<Order> onBeforeConvert(
            Order order,
            SqlIdentifier table) {

        if (order.getCode() != null) {
            order.setCode(order.getCode().trim().toUpperCase());
        }

        return Mono.just(order);
    }
}
~~~

Callback nhận entity và tên bảng dưới dạng SqlIdentifier. Nó trả về Publisher phát ra entity sẽ được chuyển đổi và lưu.

Nếu dùng entity bất biến, hãy tạo và trả về một instance mới thay vì thay đổi instance hiện tại:

~~~java
return Mono.just(order.withCode(
    order.code().trim().toUpperCase()
));
~~~

Phương thức withCode trong ví dụ giả định domain type có API tạo bản sao tương ứng. Cách tạo instance mới phụ thuộc thiết kế entity.

### 3.2. BeforeSaveCallback

BeforeSaveCallback chạy sau khi entity đã được chuyển thành OutboundRow và trước khi statement ghi được thực thi.

Callback nhận ba đối số:

- Entity đang được lưu.
- OutboundRow chứa các giá trị đã được mapping.
- SqlIdentifier biểu diễn tên bảng.

Một điểm dễ nhầm: nếu callback thay đổi một trường persistent trên entity, thay đổi đó không tự động được phản ánh vào OutboundRow đã tạo. Theo contract của callback, chính OutboundRow là dữ liệu được dùng để ghi. Vì vậy:

- Muốn thay đổi trường persistent của entity trước khi mapping, dùng BeforeConvertCallback.
- Muốn điều chỉnh trực tiếp giá trị cột sau mapping, thay đổi OutboundRow trong BeforeSaveCallback.
- Chỉ nên thay đổi trường transient trên entity ở BeforeSaveCallback nếu cần thay đổi đối tượng được trả về.

Ví dụ cấu trúc callback:

~~~java
@Component
public class OrderBeforeSaveCallback
        implements BeforeSaveCallback<Order> {

    @Override
    public Publisher<Order> onBeforeSave(
            Order order,
            OutboundRow row,
            SqlIdentifier table) {

        // Có thể điều chỉnh giá trị cột trực tiếp trong row tại đây.
        // Thay đổi persistent field trên order lúc này không cập nhật row.

        return Mono.just(order);
    }
}
~~~

Không đặt logic chuẩn hóa persistent field trong BeforeSaveCallback rồi kỳ vọng entity mutation được lưu. Hãy chọn BeforeConvertCallback hoặc cập nhật OutboundRow có chủ đích.

### 3.3. AfterSaveCallback

AfterSaveCallback chạy sau khi thao tác lưu đã hoàn tất. Callback có thể điều chỉnh entity mà publisher trả về.

Các trường hợp sử dụng phù hợp:

- Bổ sung thông tin chỉ cần có trên đối tượng trả về.
- Tạo giá trị transient phục vụ tầng gọi.
- Chuẩn hóa response representation sau khi lưu.
- Ghi nhận thông tin quan sát không làm thay đổi dữ liệu đã ghi.

AfterSaveCallback không phải cơ hội để sửa persistent field rồi kỳ vọng Spring Data tự phát sinh thêm một UPDATE. SQL đã được thực thi trước khi callback này chạy.

Nếu cần thay đổi dữ liệu persistent trong database, hãy thực hiện thay đổi trước khi mapping/ghi hoặc tạo một thao tác ghi riêng có chủ đích.

## 4. Vòng đời callback khi đọc entity

Khi Spring Data đọc một hàng và chuyển nó thành entity, callback đọc được hỗ trợ là AfterConvertCallback.

Luồng khái niệm:

~~~text
SELECT
  |
  v
Database trả Row
  |
  v
Spring Data converter tạo entity
  |
  v
AfterConvertCallback
  |
  v
Entity được phát ra cho subscriber
~~~

AfterConvertCallback phù hợp khi cần điều chỉnh đối tượng sau mapping, ví dụ:

- Tính một thuộc tính transient.
- Chuẩn hóa cách biểu diễn dữ liệu trong bộ nhớ.
- Bổ sung thông tin cục bộ có thể suy ra từ entity vừa đọc.
- Áp dụng một biến đổi presentation đơn giản.

Ví dụ:

~~~java
@Component
public class OrderAfterConvertCallback
        implements AfterConvertCallback<Order> {

    @Override
    public Publisher<Order> onAfterConvert(
            Order order,
            SqlIdentifier table) {

        order.setDisplayStatus(
            order.getStatus().toDisplayText()
        );

        return Mono.just(order);
    }
}
~~~

Giả sử displayStatus là thuộc tính transient, callback có thể điền giá trị đó để tầng ứng dụng sử dụng.

AfterConvertCallback chỉ thay đổi entity trong bộ nhớ. Nó không ghi lại giá trị mới xuống database. Nếu cần lưu một giá trị, hãy thay đổi nó ở đường ghi hoặc thực hiện một thao tác cập nhật riêng.

Cũng không nên dùng AfterConvertCallback làm nơi duy nhất để áp dụng một quy tắc bảo mật hoặc bất biến nghiệp vụ quan trọng. Một số đường SQL tùy chỉnh có thể không đi qua callback này. Quy tắc bắt buộc phải được bảo vệ ở service/domain layer và, khi phù hợp, bằng constraint của database.

## 5. Đăng ký callback trong Spring ApplicationContext

Spring Data phát hiện callback được đăng ký dưới dạng bean trong ApplicationContext. Có thể dùng @Component hoặc khai báo @Bean.

Ví dụ:

~~~java
@Configuration
public class OrderCallbackConfiguration {

    @Bean
    BeforeConvertCallback<Order> normalizeOrderCode() {
        return (order, table) -> {
            order.setCode(order.getCode().trim().toUpperCase());
            return Mono.just(order);
        };
    }
}
~~~

Một lớp callback chuyên biệt thường dễ đọc và dễ kiểm soát hơn lambda khi dự án có nhiều callback hoặc cần lọc theo generic entity type.

Ví dụ @Component ở các phần trước là một cách đăng ký khác. Không cần tạo một callback manager mới cho mỗi repository.

### 5.1. Callback được lọc theo kiểu entity

Khai báo:

~~~java
BeforeConvertCallback<Order>
~~~

có nghĩa callback này dành cho Order. Nó không tự áp dụng cho Customer hoặc Product.

Nếu một lớp callback triển khai nhiều interface cho cùng một domain type, Spring Data có thể gọi chúng tại các giai đoạn tương ứng:

~~~java
@Component
public class OrderLifecycleCallbacks
        implements BeforeConvertCallback<Order>,
                   AfterConvertCallback<Order> {

    @Override
    public Publisher<Order> onBeforeConvert(
            Order order,
            SqlIdentifier table) {
        return Mono.just(order);
    }

    @Override
    public Publisher<Order> onAfterConvert(
            Order order,
            SqlIdentifier table) {
        return Mono.just(order);
    }
}
~~~

Giữ mỗi callback tập trung vào một trách nhiệm giúp tránh side effect khó theo dõi.

### 5.2. Thứ tự chạy callback

Nếu nhiều callback cùng áp dụng cho một kiểu entity và cùng một giai đoạn, Spring Data gọi chúng tuần tự. Kết quả của callback trước được truyền cho callback tiếp theo.

Có thể quy định thứ tự bằng:

- Annotation @Order.
- Interface Ordered.

Giá trị order nhỏ hơn được chạy trước. Callback không khai báo order mặc định có mức ưu tiên thấp nhất và thường chạy sau các callback có thứ tự tường minh.

Ví dụ:

~~~java
@Component
@Order(50)
public class NormalizeOrderCallback
        implements BeforeConvertCallback<Order> {
    // ...
}
~~~

Spring Data R2DBC có AuditingEntityCallback với order 100. Nếu callback tùy chỉnh phải chuẩn hóa dữ liệu trước auditing, có thể đặt order nhỏ hơn 100. Nếu cần hành vi khác, hãy thiết kế thứ tự dựa trên phụ thuộc thực tế và kiểm thử nó.

### 5.3. Callback reactive phải trả Publisher đúng cách

Callback R2DBC là reactive callback. Không gọi subscribe() bên trong callback và không block để chờ kết quả.

Không phù hợp:

~~~java
@Override
public Publisher<Order> onBeforeConvert(
        Order order,
        SqlIdentifier table) {

    legacyClient.validate(order).block();

    return Mono.just(order);
}
~~~

Cách này chặn thread đang xử lý pipeline. Nếu callback cần một thao tác bất đồng bộ, hãy kết hợp publisher:

~~~java
@Override
public Publisher<Order> onBeforeConvert(
        Order order,
        SqlIdentifier table) {

    return validationClient.validate(order)
        .thenReturn(order);
}
~~~

Nếu validationClient chỉ có API blocking, hãy bọc lời gọi bằng fromCallable và boundedElastic theo đúng nguyên tắc cô lập blocking. Tuy nhiên, nên cân nhắc kỹ việc gọi dịch vụ ngoài trong callback vì nó làm tăng thời gian và side effect của mọi đường mapping entity.

## 6. Phạm vi callback với Repository

Repository của Spring Data R2DBC được xây dựng trên hạ tầng R2dbcEntityOperations và mapping của Spring Data. Vì vậy các thao tác entity thông thường đi qua repository có thể sử dụng lifecycle callback.

Ví dụ:

~~~java
public interface OrderRepository
        extends ReactiveCrudRepository<Order, Long> {
}
~~~

Khi gọi:

~~~java
Mono<Order> saved = orderRepository.save(order);
Mono<Order> loaded = orderRepository.findById(orderId);
~~~

Các thao tác entity CRUD đi qua mapping lifecycle:

- Save entity: các callback trước chuyển đổi, trước lưu và sau lưu được áp dụng theo quy trình tương ứng.
- Đọc entity: AfterConvertCallback có thể được gọi sau khi entity được tạo từ hàng dữ liệu.
- Các thao tác được thực thi khi publisher được subscribe, không phải chỉ vì method được gọi.

### 6.1. save và insert/update

Repository save nhận entity và để Spring Data xác định thao tác insert hoặc update theo cơ chế nhận diện entity mới.

Với đường lưu entity này, callback trước khi convert và trước khi save có thể can thiệp vào dữ liệu được mapping. AfterSaveCallback chạy sau thao tác lưu.

Callback không thay thế quy tắc xác định entity mới, @Id hoặc @Version. Ví dụ, BeforeConvertCallback có thể chuẩn hóa dữ liệu, nhưng không nên tự mô phỏng toàn bộ persistence lifecycle hoặc tự tăng version mà Spring Data đang quản lý.

### 6.2. findById và đọc entity

Khi repository materialize một entity từ database, AfterConvertCallback là điểm có thể điều chỉnh entity sau mapping.

Nếu method trả về DTO projection hoặc một kiểu kết quả khác domain entity, không nên giả định callback của entity gốc sẽ được gọi theo cùng cách. Hãy xác định kiểu kết quả thực tế và đường mapping được sử dụng.

### 6.3. Derived query và @Query cần được phân biệt

Không phải mọi method nằm trong repository interface đều có cùng đường thực thi.

- CRUD method do repository cung cấp thường đi qua entity persistence infrastructure.
- Query method có thể dùng cơ chế query derivation hoặc query khai báo.
- @Query thực thi SQL do ứng dụng cung cấp; kiểu kết quả và cách materialize dữ liệu ảnh hưởng đến mapping.
- DTO projection từ @Query có thể được ánh xạ trực tiếp theo cấu trúc SELECT và kiểu DTO, không nhất thiết qua domain entity.

Đặc biệt, một @Query UPDATE không tạo entity đầu vào để chạy BeforeConvertCallback hoặc BeforeSaveCallback. Việc method nằm trong repository không biến nó thành thao tác save(entity).

Với query SELECT trả về domain entity, hãy xác nhận callback đọc trong đúng phiên bản Spring Data R2DBC và kiểu kết quả của dự án nếu logic phụ thuộc vào AfterConvertCallback. Đừng đặt một quy tắc nghiệp vụ bắt buộc ở callback rồi giả định mọi query method đều thực thi nó.

### 6.4. delete và deleteById

Bộ callback entity store-specific được Spring Data R2DBC tài liệu hóa gồm BeforeConvert, BeforeSave, AfterSave, AfterConvert và auditing. Danh sách này không cung cấp một cặp BeforeDeleteCallback/AfterDeleteCallback tương ứng như một số module Spring Data khác.

Do đó, không nên giả định delete(entity) hoặc deleteById(id) sẽ tự kích hoạt một delete callback chuẩn của R2DBC.

Nếu cần audit việc xóa, hãy thực hiện ở service/use-case trước hoặc sau thao tác delete, dùng outbox/audit table trong cùng transaction khi cần tính nguyên tử, hoặc dùng cơ chế database phù hợp. Hãy kiểm tra chính xác API của phiên bản Spring Data đang sử dụng.

## 7. Phạm vi callback với R2dbcEntityTemplate

R2dbcEntityTemplate là abstraction mapping-aware của Spring Data R2DBC. Nó thực hiện các thao tác entity và sử dụng mapping context/converter để chuyển đổi giữa entity và dữ liệu quan hệ.

Các thao tác template theo entity thường đi qua lifecycle callback tương ứng:

~~~java
Mono<Order> inserted = template.insert(Order.class)
    .using(order);

Mono<Order> selected = template.selectOne(
    Query.query(Criteria.where("id").is(orderId)),
    Order.class
);
~~~

Trong ví dụ, template biết kiểu Order và thực hiện mapping. Vì vậy callback trước khi convert/lưu hoặc sau khi convert khi đọc có thể tham gia theo lifecycle của thao tác.

### 7.1. Entity-oriented insert/update

Khi template nhận một entity để insert hoặc update, Spring Data có entity để chuyển thành OutboundRow. Đây là đường phù hợp với BeforeConvertCallback và BeforeSaveCallback.

Ví dụ khái niệm:

~~~java
return template.insert(Order.class)
    .using(order);
~~~

Callback được kích hoạt trong quá trình thực thi publisher, không phải ngay tại thời điểm xây dựng publisher.

### 7.2. Select và AfterConvertCallback

Khi template select một domain entity, hàng dữ liệu được chuyển thành entity. AfterConvertCallback là điểm hook sau mapping.

~~~java
return template.select(Order.class)
    .matching(Query.query(Criteria.where("status").is("PAID")))
    .all();
~~~

Nếu kết quả là Flux<Order>, callback đọc có thể được áp dụng cho từng entity được materialize theo cơ chế mapping.

Nếu template chỉ trả về giá trị scalar, projection hoặc kiểu đọc khác không phải entity được quản lý theo lifecycle đó, không nên giả định toàn bộ callback entity được gọi.

### 7.3. Update(Query, Update) không giống save(entity)

Template cũng có các API thao tác theo Query và Update. Ví dụ, ứng dụng có thể cập nhật một cột mà không tải entity:

~~~java
return template.update(Order.class)
    .matching(Query.query(Criteria.where("id").is(orderId)))
    .apply(Update.update("status", "PAID"));
~~~

Đường này mô tả trực tiếp điều kiện và dữ liệu cập nhật. Không có entity hoàn chỉnh được truyền vào để chạy BeforeConvertCallback hoặc BeforeSaveCallback theo cách của save(entity).

Nếu cập nhật theo Query/Update là một đường ghi hợp lệ của ứng dụng, hãy đưa các quy tắc cần thiết vào service/domain logic trước khi gọi template hoặc thể hiện chúng trong SQL/constraint. Đừng phụ thuộc callback entity để bảo vệ mọi update dạng này.

### 7.4. Template có thể dùng DatabaseClient bên dưới

R2dbcEntityTemplate sử dụng DatabaseClient và converter để thực hiện mapping-aware operations. Tuy nhiên, việc hai API dùng chung DatabaseClient không có nghĩa mọi lệnh gọi DatabaseClient đều tự động được nâng thành entity lifecycle operation.

Template biết kiểu entity và các metadata cần thiết. DatabaseClient SQL trực tiếp chỉ biết câu SQL, bind parameters và cách ứng dụng map Row. Đây là khác biệt cốt lõi về phạm vi callback.

## 8. Phạm vi callback với DatabaseClient và SQL trực tiếp

DatabaseClient là API SQL mức thấp hơn. Nó quản lý connection, thực thi statement và cho phép ứng dụng ánh xạ kết quả. Nó không tự suy luận rằng một lớp Java bất kỳ là entity cần chạy toàn bộ lifecycle callback của Spring Data Relational.

Ví dụ:

~~~java
return databaseClient.sql("""
        UPDATE orders
        SET status = :status
        WHERE id = :id
        """)
    .bind("status", "PAID")
    .bind("id", orderId)
    .fetch()
    .rowsUpdated();
~~~

Câu SQL trên cập nhật bảng orders. Nhưng DatabaseClient không nhận một Order entity để chuyển đổi thành OutboundRow. Vì vậy:

- Không có entity để chạy BeforeConvertCallback.
- Không có OutboundRow của entity được tạo bởi entity converter để chạy BeforeSaveCallback.
- Không có entity result được đọc để chạy AfterConvertCallback.
- Không có entity lifecycle AfterSaveCallback cho thao tác SQL này.

Ngay cả khi SQL có cùng tên bảng và cột với entity Order, callback vẫn không tự chạy.

### 8.1. DatabaseClient map Row thành entity cũng không tự động tạo lifecycle đầy đủ

Ví dụ:

~~~java
return databaseClient.sql("""
        SELECT id, status
        FROM orders
        WHERE id = :id
        """)
    .bind("id", orderId)
    .map((row, metadata) -> new Order(
        row.get("id", Long.class),
        row.get("status", String.class)
    ))
    .one();
~~~

Đoạn map tự tạo Order từ Row. Đây là mapping do code ứng dụng viết. DatabaseClient không tự gọi AfterConvertCallback chỉ vì kiểu trả về là Order.

Nếu muốn dùng lại logic callback, có thể gọi logic domain/helper dùng chung hoặc chủ động sử dụng ReactiveEntityCallbacks. Không nên nhân bản quy tắc chuẩn hóa ở nhiều mapper.

### 8.2. R2DBC SPI trực tiếp cũng không tự gọi entity callbacks

Nếu code dùng Connection.createStatement(), Statement.execute() và Result.map(), ứng dụng đang làm việc trực tiếp với R2DBC SPI.

Các API này không tự biết callback bean nào cần chạy. Chúng chỉ thực hiện thao tác theo contract của R2DBC driver.

Nếu một đường SQL trực tiếp phải tuân thủ quy tắc như chuẩn hóa mã, ghi audit hoặc tạo giá trị mặc định, hãy gọi một domain service chung trước khi tạo Statement hoặc thiết kế constraint/trigger phù hợp ở database.

### 8.3. SQL script, stored procedure và batch job

Một câu lệnh trong migration, script quản trị, stored procedure hoặc batch job bên ngoài Spring Data cũng không đi qua entity callback của ứng dụng.

Nếu hệ thống có nhiều writer, không nên chỉ dựa vào callback để bảo vệ tính đúng đắn của dữ liệu. Quy tắc cần áp dụng cho mọi writer nên được đặt ở một nơi có phạm vi phù hợp:

- Domain/service layer cho hành vi nghiệp vụ của ứng dụng.
- Constraint database cho bất biến dữ liệu.
- Trigger khi quy tắc thực sự thuộc về database và mọi writer phải tuân thủ.
- Outbox/audit table cho ghi nhận thay đổi cần tính nguyên tử.
- Quy ước chung cho các batch và tích hợp.

## 9. Bảng so sánh phạm vi

| Đường truy cập | Có entity mapping lifecycle? | Điều cần lưu ý |
|---|---|---|
| Repository save(entity) | Có | Đi qua entity conversion và save callbacks |
| Repository findById/findAll | Có khi materialize domain entity | AfterConvert áp dụng cho entity được đọc qua mapping path |
| Repository deleteById | Không có delete callback trong bộ callback R2DBC chuẩn | Dùng service/audit/outbox nếu cần hook xóa |
| Repository @Query SELECT | Phụ thuộc kiểu kết quả và query mapping path | Không suy luận chỉ từ việc method nằm trong repository |
| Repository @Query UPDATE/DELETE | Không có entity save lifecycle chỉ vì method là repository method | SQL tùy chỉnh phải tự thực hiện quy tắc cần thiết |
| R2dbcEntityTemplate insert/update entity | Có | Dùng callback theo lifecycle entity |
| R2dbcEntityTemplate select entity | Có khi materialize entity | AfterConvert có thể điều chỉnh entity sau mapping |
| R2dbcEntityTemplate update(Query, Update) | Không giống save(entity) | Thường không có entity đầu vào để chạy BeforeConvert/BeforeSave |
| DatabaseClient.sql(...) | Không tự động | SQL và Row mapping do ứng dụng điều khiển |
| R2DBC Connection/Statement trực tiếp | Không tự động | Làm việc ở mức SPI, không qua entity callback registry |
| SQL script hoặc stored procedure | Không | Spring Data callback không bao phủ writer bên ngoài |

Bảng trên mô tả nguyên tắc theo loại đường truy cập. Với query method hoặc API đặc thù, hãy kiểm tra call path của đúng phiên bản Spring Data R2DBC và kiểu kết quả thực tế, nhất là khi callback là một phần bắt buộc của nghiệp vụ.

## 10. Dùng callback cho việc gì và không dùng cho việc gì?

Callback phù hợp với các thay đổi nhỏ, đồng nhất và gắn trực tiếp với lifecycle của entity:

- Chuẩn hóa trường trước khi lưu.
- Gán metadata mặc định.
- Tạo thông tin audit.
- Tính giá trị transient sau khi đọc.
- Điều chỉnh OutboundRow ngay trước khi ghi.

Callback không nên trở thành nơi chứa toàn bộ nghiệp vụ:

- Không điều phối nhiều repository phức tạp.
- Không gọi hệ thống thanh toán hoặc gửi email như side effect không thể rollback.
- Không thay thế validation bắt buộc ở mọi đường ghi.
- Không thay thế transaction.
- Không giả định callback bao phủ SQL trực tiếp.
- Không thực hiện truy vấn phụ cho từng entity nếu có thể gây N+1.
- Không dùng AfterSave để kỳ vọng một lần ghi bổ sung tự động.

Nếu logic là quy tắc nghiệp vụ cốt lõi, hãy đặt nó ở domain/service layer và gọi từ mọi use case có liên quan. Callback có thể gọi logic nhỏ dùng chung, nhưng không nên là nơi duy nhất chứa quy tắc mà SQL trực tiếp hoặc batch writer cũng phải tuân thủ.

## 11. Callback không phải transaction boundary

Callback chạy trong quá trình xử lý entity, nhưng bản thân callback không mở transaction độc lập.

Nếu thao tác repository hoặc template đang nằm trong reactive transaction, callback được thực thi như một phần của reactive pipeline đó. Lỗi callback có thể làm pipeline ghi/đọc thất bại và transaction có thể rollback theo transaction manager.

Tuy nhiên, một callback gọi HTTP, gửi email hoặc ghi file không tự động được rollback khi transaction R2DBC rollback.

Ví dụ không nên làm:

~~~java
@Override
public Publisher<Order> onBeforeConvert(
        Order order,
        SqlIdentifier table) {

    return paymentClient.charge(order.getPayment())
        .thenReturn(order);
}
~~~

Nếu thanh toán thành công nhưng câu INSERT/UPDATE sau đó thất bại, database rollback không thể hoàn lại khoản thanh toán. Callback còn khiến mọi đường save entity có thể phát sinh side effect khó dự đoán.

Hãy giữ callback nhẹ và tập trung vào mapping. Với side effect cần phối hợp cùng database, cân nhắc transactional outbox hoặc saga.

## 12. Callback và auditing

Spring Data R2DBC dùng AuditingEntityCallback để điền các trường auditing trước khi entity được chuyển đổi để lưu.

Ví dụ entity:

~~~java
@Table("orders")
public class Order {

    @Id
    private Long id;

    private String status;

    @CreatedDate
    private Instant createdAt;

    @LastModifiedDate
    private Instant updatedAt;

    @CreatedBy
    private String createdBy;

    @LastModifiedBy
    private String modifiedBy;
}
~~~

Bật auditing:

~~~java
@Configuration
@EnableR2dbcAuditing
public class R2dbcAuditingConfiguration {

    @Bean
    ReactiveAuditorAware<String> auditorAware() {
        return () -> ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication().getName());
    }
}
~~~

Ví dụ ReactiveAuditorAware lấy người dùng từ reactive security context. Cách lấy auditor thực tế phụ thuộc vào hệ thống authentication của ứng dụng.

Auditing là một callback tích hợp của Spring Data. Nó vẫn tuân theo phạm vi entity mapping. Một UPDATE SQL trực tiếp qua DatabaseClient không tự chạy AuditingEntityCallback. Nếu một đường SQL trực tiếp cần cập nhật updated_at hoặc modified_by, hãy bind các giá trị đó trong SQL hoặc dùng một cơ chế database phù hợp.

## 13. Callback và domain event là hai cơ chế khác nhau

Spring Data có nhiều cơ chế mở rộng, không nên nhầm EntityCallback với domain event hoặc application event.

| Cơ chế | Mục đích |
|---|---|
| EntityCallback | Can thiệp đồng bộ theo thứ tự vào một giai đoạn mapping/lifecycle cụ thể |
| Application event | Thông báo một sự kiện trong ApplicationContext |
| Domain event | Thể hiện một sự kiện nghiệp vụ do aggregate phát ra |
| Transactional outbox | Ghi sự kiện bền vững cùng transaction để xử lý sau commit |

EntityCallback phù hợp để chuẩn hóa hoặc điều chỉnh entity. Domain event phù hợp để diễn đạt điều gì đã xảy ra trong nghiệp vụ. Outbox phù hợp khi sự kiện cần được chuyển ra hệ thống khác một cách đáng tin cậy.

Không dùng AfterSaveCallback để giả định sự kiện đã được gửi thành công tới broker hoặc email đã được giao. Nếu cần độ tin cậy sau commit, hãy thiết kế outbox hoặc cơ chế phát sự kiện có bảo đảm phù hợp.

## 14. Cách dùng chung logic giữa Repository, Template và SQL trực tiếp

Nếu cùng một quy tắc cần áp dụng ở nhiều đường truy cập, hãy tách quy tắc khỏi callback.

Ví dụ, chuẩn hóa mã đơn hàng:

~~~java
public final class OrderCodePolicy {

    private OrderCodePolicy() {
    }

    public static String normalize(String code) {
        if (code == null || code.isBlank()) {
            throw new IllegalArgumentException("Order code is required");
        }

        return code.trim().toUpperCase();
    }
}
~~~

Callback có thể dùng policy:

~~~java
@Component
public class OrderCodeCallback
        implements BeforeConvertCallback<Order> {

    @Override
    public Publisher<Order> onBeforeConvert(
            Order order,
            SqlIdentifier table) {

        order.setCode(OrderCodePolicy.normalize(order.getCode()));
        return Mono.just(order);
    }
}
~~~

Service dùng cùng policy trước khi thực hiện SQL trực tiếp:

~~~java
public Mono<Integer> updateOrderCode(
        Long orderId,
        String requestedCode) {

    String normalized = OrderCodePolicy.normalize(requestedCode);

    return databaseClient.sql("""
            UPDATE orders
            SET code = :code
            WHERE id = :id
            """)
        .bind("code", normalized)
        .bind("id", orderId)
        .fetch()
        .rowsUpdated();
}
~~~

Như vậy:

- Repository save có thể chạy callback.
- Template entity operation có thể chạy callback.
- SQL trực tiếp gọi policy một cách tường minh.
- Quy tắc chuẩn hóa chỉ được định nghĩa một lần.

Nếu dữ liệu phải luôn được chuẩn hóa kể cả khi có writer ngoài ứng dụng, cân nhắc thêm CHECK constraint hoặc một cơ chế chuẩn hóa ở database phù hợp. Service policy không thể bảo vệ một script hoàn toàn bỏ qua service.

## 15. Kiểm thử phạm vi callback

Không chỉ kiểm tra callback chạy đúng khi gọi một repository method. Cần kiểm tra các đường truy cập mà ứng dụng thực sự sử dụng.

### 15.1. Kiểm tra callback trên repository save

Có thể dùng integration test với database R2DBC:

~~~java
@Test
void shouldNormalizeCodeWhenSavingThroughRepository() {
    Order order = new Order();
    order.setCode("  ab-123  ");

    StepVerifier.create(orderRepository.save(order))
        .assertNext(saved ->
            assertThat(saved.getCode()).isEqualTo("AB-123")
        )
        .verifyComplete();
}
~~~

Test này xác nhận callback trước convert được áp dụng trong đường save của repository và giá trị chuẩn hóa được ghi theo mapping.

### 15.2. Kiểm tra callback trên template

Thực hiện insert/select qua R2dbcEntityTemplate và xác nhận callback tương ứng được gọi. Điều này giúp phát hiện trường hợp template bean được cấu hình khác mapping context hoặc callback registry.

### 15.3. Kiểm tra SQL trực tiếp

Nếu dùng DatabaseClient cho một thao tác, hãy viết test xác nhận quy tắc được gọi tường minh ở service/DAO. Không viết test giả định callback entity tự chạy trên DatabaseClient.

Ví dụ, có thể dùng một policy thuần Java và kiểm tra kết quả được bind vào SQL. Nếu callback là cơ chế duy nhất đang thực hiện chuẩn hóa, test SQL trực tiếp sẽ giúp phát hiện lỗ hổng phạm vi.

### 15.4. Kiểm tra thứ tự callback

Nếu có nhiều callback, test thứ tự bằng một trace đơn giản hoặc kiểm tra kết quả biến đổi. Đặc biệt khi auditing và callback tùy chỉnh cùng thay đổi entity, hãy xác nhận thứ tự @Order đúng với ý định.

### 15.5. Kiểm tra lỗi và reactive behavior

Cần kiểm tra thêm:

- Callback phát Mono.error thì thao tác mapping thất bại.
- Callback không tự subscribe.
- Callback không block event-loop.
- Callback trả entity mới nếu domain object bất biến.
- Callback không tạo side effect lặp khi publisher bị subscribe nhiều lần.
- Callback không gọi truy vấn phụ gây N+1.

## 16. Những lỗi thường gặp

| Nhầm lẫn | Hệ quả | Cách hiểu đúng |
|---|---|---|
| Nghĩ mọi câu SQL đều chạy entity callback | Dữ liệu qua DatabaseClient có thể bỏ qua chuẩn hóa/auditing | Callback gắn với entity mapping lifecycle |
| Nghĩ method nào trong Repository cũng có cùng callback | @Query, projection và modifying query có đường xử lý khác nhau | Xác định loại query và kiểu kết quả |
| Sửa persistent field trong BeforeSaveCallback | OutboundRow đã được tạo từ trước nên giá trị ghi không đổi | Sửa entity trong BeforeConvert hoặc sửa OutboundRow |
| Dùng AfterSave để sửa dữ liệu đã ghi | Thay đổi entity trả về không tự chạy UPDATE | Thay đổi trước khi ghi hoặc gọi thao tác ghi riêng |
| Dùng AfterConvert để bảo vệ bất biến | SQL trực tiếp có thể không chạy callback | Bảo vệ ở domain/service và database |
| Cho rằng R2dbcEntityTemplate và DatabaseClient giống nhau | DatabaseClient không có entity lifecycle context như template | Template biết entity metadata; DatabaseClient xử lý SQL |
| Dùng callback để gửi email hoặc thanh toán | Side effect không rollback cùng database | Dùng outbox/saga hoặc xử lý sau commit |
| Dùng callback đồng bộ trong reactive path | Có thể chặn thread reactive | Dùng callback reactive của R2DBC |
| Tự subscribe trong callback | Tạo luồng xử lý ngoài lifecycle của operation | Trả Publisher cho Spring Data |
| Giả định có BeforeDeleteCallback chuẩn của R2DBC | Có thể dựa vào hook không được hỗ trợ | Dùng service, audit/outbox hoặc database mechanism |
| Cho rằng callback chạy một lần khi gọi method | Publisher có thể được subscribe nhiều lần | Callback chạy theo lần thực thi/subscription của operation |
| Không kiểm tra đường SQL khác | Quy tắc chỉ đúng với một writer | Kiểm tra mọi writer hoặc chuyển bất biến xuống database |

## 17. Quy trình quyết định đặt logic ở đâu

Khi cần thêm logic vào vòng đời entity, hãy tự hỏi:

1. Logic có thực sự là một biến đổi của entity trước hoặc sau mapping không?
2. Nếu thay đổi trường persistent, nó phải xảy ra trước khi tạo OutboundRow hay trực tiếp trên OutboundRow?
3. Có cần logic chạy khi đọc entity không, hay chỉ khi ghi?
4. Tất cả đường ghi có đi qua Repository hoặc entity-oriented Template không?
5. Ứng dụng có dùng @Query, DatabaseClient, R2DBC SPI, script hoặc batch writer không?
6. Quy tắc có phải được áp dụng cho mọi writer không?
7. Nếu callback phát lỗi, thao tác database và transaction phải phản ứng thế nào?
8. Logic có side effect bên ngoài database không?
9. Callback có thể bị gọi lại do retry hoặc subscription mới không?
10. Có thể tách quy tắc thành domain/service policy để dùng chung không?

Có thể chọn như sau:

| Loại logic | Vị trí phù hợp |
|---|---|
| Chuẩn hóa persistent field trước khi lưu qua mapping | BeforeConvertCallback |
| Điều chỉnh giá trị cột sau khi entity đã map | BeforeSaveCallback và OutboundRow |
| Thêm dữ liệu transient vào entity sau khi lưu | AfterSaveCallback |
| Tính trường transient sau khi đọc entity | AfterConvertCallback |
| Kiểm tra quy tắc nghiệp vụ bắt buộc trên mọi use case | Domain/service layer |
| Bảo vệ bất biến dữ liệu trước mọi writer | Database constraint hoặc cơ chế database phù hợp |
| Audit thao tác xóa | Service/outbox/database mechanism |
| Gửi message sau commit | Transactional outbox |
| SQL trực tiếp cần cùng quy tắc chuẩn hóa | Shared policy được gọi tường minh |

## 18. Bài tập tự kiểm tra

### Bài 1: Chọn callback

Bạn muốn trim và uppercase trường code trước khi lưu entity Order. Nên dùng callback nào?

Gợi ý: BeforeConvertCallback vì nó chạy trước khi entity được chuyển thành OutboundRow.

### Bài 2: Thay đổi OutboundRow

Bạn muốn ghi một giá trị cột bổ sung sau khi entity đã được chuyển đổi. Nên dùng callback nào?

Gợi ý: BeforeSaveCallback, vì callback này nhận OutboundRow. Nếu chỉ thay đổi persistent property trên entity ở giai đoạn này, giá trị đã map không tự đổi.

### Bài 3: SQL trực tiếp

Một DAO dùng DatabaseClient để UPDATE bảng orders. BeforeConvertCallback<Order> có tự chạy không?

Gợi ý: Không. DatabaseClient thực thi SQL trực tiếp và không tự chạy entity lifecycle callback. Hãy gọi policy/service logic tường minh hoặc thể hiện quy tắc trong database.

### Bài 4: AfterConvert

Bạn muốn tính displayStatus là trường transient sau khi đọc Order. Nên dùng callback nào?

Gợi ý: AfterConvertCallback. Giá trị chỉ tồn tại trong entity được trả về, không tự ghi xuống database.

### Bài 5: Repository @Query

Một method @Query UPDATE nằm trong OrderRepository. Có thể kết luận BeforeSaveCallback sẽ chạy vì method thuộc repository không?

Gợi ý: Không. @Query UPDATE là câu SQL tùy chỉnh, không phải save(entity). Cần thực hiện các quy tắc cần thiết trong service hoặc SQL.

### Bài 6: Gửi email

Bạn muốn gửi email sau khi đơn hàng được lưu. Có nên gọi email client trực tiếp trong AfterSaveCallback không?

Gợi ý: Không nên dựa vào callback cho side effect cần độ tin cậy. Transaction có thể rollback sau lỗi tiếp theo và email không thể tự rollback. Dùng outbox để gửi sau commit.

### Bài 7: Xóa entity

Bạn cần ghi audit trước khi xóa. Có thể dựa vào BeforeDeleteCallback chuẩn của Spring Data R2DBC không?

Gợi ý: Bộ callback store-specific R2DBC được tài liệu hóa không cung cấp cặp callback xóa tương ứng. Thực hiện audit ở service/use-case hoặc dùng outbox/trigger theo yêu cầu.

### Bài 8: Callback và transaction

BeforeConvertCallback phát lỗi khi lưu Order trong reactive transaction. Điều gì xảy ra?

Gợi ý: Publisher lưu phát lỗi. Transaction manager có thể rollback transaction theo quy tắc rollback đã cấu hình. Callback không tự mở transaction riêng.

## 19. Ghi nhớ

- EntityCallback là hook trong quy trình mapping entity của Spring Data, không phải interceptor cho mọi SQL.
- Spring Data R2DBC hỗ trợ BeforeConvertCallback, BeforeSaveCallback, AfterSaveCallback, AfterConvertCallback và AuditingEntityCallback.
- BeforeConvertCallback phù hợp để thay đổi persistent field trước khi tạo OutboundRow.
- BeforeSaveCallback chạy sau mapping; muốn thay đổi dữ liệu ghi phải chỉnh OutboundRow, không chỉ sửa persistent field trên entity.
- AfterSaveCallback điều chỉnh entity được trả về sau khi lưu, không tự phát sinh một lần ghi nữa.
- AfterConvertCallback điều chỉnh entity trong bộ nhớ sau khi đọc, không cập nhật database.
- Callback được đăng ký như bean trong ApplicationContext, được chọn theo kiểu entity và có thể sắp xếp bằng @Order hoặc Ordered.
- Callback R2DBC là reactive; trả Publisher, không tự subscribe hoặc block.
- Repository CRUD và entity-oriented R2dbcEntityTemplate operations đi qua mapping lifecycle tương ứng.
- @Query, projection, update theo Query/Update và SQL trực tiếp cần được phân biệt theo đường thực thi; không suy luận phạm vi callback chỉ từ tên repository.
- DatabaseClient và R2DBC SPI không tự chạy entity callbacks khi thực thi SQL trực tiếp hoặc map Row thủ công.
- Không giả định bộ callback chuẩn của R2DBC có BeforeDeleteCallback/AfterDeleteCallback.
- Callback không phải transaction boundary và không làm side effect bên ngoài database trở nên rollback được.
- Nếu quy tắc phải áp dụng trên mọi đường ghi, tách nó thành domain/service policy hoặc bảo vệ bằng constraint/database mechanism.
- Kiểm thử riêng repository, template và SQL trực tiếp để xác nhận phạm vi thực tế.

Khi thiết kế callback trong Spring Data Relational R2DBC, hãy đặt logic đúng tại giai đoạn mapping mà nó cần tác động và hiểu rõ đường truy cập nào đi qua giai đoạn đó. Repository và entity-oriented Template cung cấp lifecycle của entity; DatabaseClient và SQL trực tiếp chỉ thực thi câu lệnh do ứng dụng cung cấp. Tách quy tắc nghiệp vụ dùng chung khỏi callback giúp mọi đường ghi giữ được cùng một hành vi.

