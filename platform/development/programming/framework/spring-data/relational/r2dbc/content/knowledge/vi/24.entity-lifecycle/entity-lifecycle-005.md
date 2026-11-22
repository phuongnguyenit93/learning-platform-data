# Xử lý thực thể sau đọc hoặc sau lưu

Trong Spring Data R2DBC, một entity thường cần được xử lý ở những thời điểm khác nhau trong vòng đời persistence. Sau khi đọc một hàng, ứng dụng có thể cần chuẩn hóa dữ liệu hoặc bổ sung một thuộc tính chỉ dùng trong bộ nhớ. Sau khi lưu, ứng dụng có thể cần đánh dấu trạng thái của object trả về hoặc ghi nhận thông tin phục vụ tầng gọi.

Spring Data cung cấp **entity callbacks** để can thiệp vào các mốc này. Hai callback thường gặp là `AfterConvertCallback` và `AfterSaveCallback`. Callback sau khi convert được gọi sau khi dữ liệu hàng đã được ánh xạ thành object Java; callback sau khi save được gọi sau thao tác lưu entity. Chúng cho phép trả về entity đã được xử lý để tiếp tục đi qua reactive pipeline.

Cần phân biệt callback sau lưu với thời điểm transaction commit. Một câu lệnh SQL có thể đã thực thi thành công và `AfterSaveCallback` đã chạy, nhưng transaction bao quanh thao tác vẫn có thể rollback về sau. Vì vậy, callback vòng đời entity phù hợp với xử lý object và mapping; nó không tự biến một side effect bên ngoài thành thao tác nguyên tử sau commit.

## 1. Các mốc vòng đời liên quan đến đọc và lưu

Trong Spring Data Relational/R2DBC, quá trình đọc và lưu có nhiều mốc khác nhau:

| Mốc | Thời điểm | Mục đích thường gặp |
|---|---|---|
| `BeforeConvertCallback` | Trước khi entity được chuyển thành dữ liệu ghi | Chuẩn hóa hoặc bổ sung giá trị trước khi tạo outbound row. |
| `BeforeSaveCallback` | Sau khi tạo dữ liệu ghi, trước khi gửi lệnh SQL | Điều chỉnh entity hoặc `OutboundRow` trước khi insert/update. |
| `AfterSaveCallback` | Sau khi thao tác insert/update thành công | Xử lý entity được trả về sau lưu hoặc bổ sung trạng thái chỉ tồn tại trong bộ nhớ. |
| `AfterConvertCallback` | Sau khi hàng database được chuyển thành entity | Chuẩn hóa object vừa đọc hoặc tính thuộc tính không lưu trong database. |

Tên callback phản ánh mốc xử lý. `AfterConvertCallback` liên quan đến việc chuyển đổi hàng dữ liệu thành entity; `AfterSaveCallback` liên quan đến thao tác lưu. Không nên dùng callback sau đọc để ghi ngược dữ liệu một cách âm thầm, hoặc dùng callback sau lưu để thay thế một quy trình nghiệp vụ cần commit cùng dữ liệu.

## 2. AfterConvertCallback: xử lý entity sau khi đọc

`AfterConvertCallback<T>` được gọi sau khi Spring Data chuyển một hàng dữ liệu thành entity kiểu `T`. Callback nhận entity đã được ánh xạ, hàng nguồn và tên bảng dưới dạng `SqlIdentifier`.

Chữ ký thường dùng:

```java
public interface AfterConvertCallback<T> extends EntityCallback<T> {
    T onAfterConvert(T entity, Row row, SqlIdentifier table);
}
```

Ví dụ, ứng dụng lưu tên hiển thị trong database nhưng muốn chuẩn hóa khoảng trắng trước khi trả object cho tầng nghiệp vụ:

```java
@Component
public class CustomerAfterConvertCallback
        implements AfterConvertCallback<Customer> {

    @Override
    public Customer onAfterConvert(
            Customer customer, Row row, SqlIdentifier table) {

        String normalized = customer.getDisplayName() == null
            ? null
            : customer.getDisplayName().trim();

        return customer.withDisplayName(normalized);
    }
}
```

`withDisplayName` trong ví dụ là phương thức do domain class cung cấp để tạo object mới. Nếu entity mutable, callback có thể cập nhật object rồi trả lại chính instance đó; nếu entity immutable hoặc là record, hãy tạo và trả về instance mới.

Callback phải trả về entity sẽ được chuyển tiếp. Tạo một object mới nhưng vẫn trả về object cũ sẽ khiến thay đổi không có tác dụng đối với caller.

### 2.1 Dùng AfterConvert cho thuộc tính chỉ tồn tại trong bộ nhớ

Một use case phổ biến là tính thuộc tính dẫn xuất sau khi đọc. Ví dụ, `Customer` lưu `firstName` và `lastName`, còn `displayLabel` chỉ phục vụ hiển thị:

```java
@Table("customer")
public class Customer {
    @Id
    private Long id;

    private String firstName;
    private String lastName;

    @Transient
    private String displayLabel;

    public Customer withDisplayLabel(String value) {
        this.displayLabel = value;
        return this;
    }
}
```

Callback có thể tạo label sau khi đọc:

```java
@Component
public class CustomerLabelCallback
        implements AfterConvertCallback<Customer> {

    @Override
    public Customer onAfterConvert(
            Customer customer, Row row, SqlIdentifier table) {

        String label = Stream.of(
                customer.getFirstName(), customer.getLastName())
            .filter(Objects::nonNull)
            .collect(Collectors.joining(" "));

        return customer.withDisplayLabel(label);
    }
}
```

`@Transient` cho biết thuộc tính không được lưu như cột thông thường. Giá trị `displayLabel` được tạo trong bộ nhớ sau khi đọc; nó không phải dữ liệu được ghi vào database.

### 2.2 AfterConvert không phải lazy loading

Callback sau convert không tạo proxy và không tự động biến quan hệ thành lazy relationship. Nếu cần dữ liệu từ bảng khác, callback phải thực hiện một thao tác rõ ràng hoặc, tốt hơn, use case đọc nên thiết kế query/projection phù hợp.

Không nên dùng `AfterConvertCallback` để âm thầm truy vấn một loạt bảng cho từng entity trong `Flux`. Cách đó có thể tạo N+1 queries, làm tăng độ trễ và khiến chi phí đọc khó dự đoán. Nếu màn hình cần dữ liệu tổng hợp, cân nhắc SQL join, projection hoặc một service query chuyên biệt.

## 3. AfterSaveCallback: xử lý entity sau khi lưu

`AfterSaveCallback<T>` được gọi sau khi Spring Data thực hiện thao tác lưu entity. Callback nhận entity, `OutboundRow` được dùng cho thao tác ghi và tên bảng.

Chữ ký thường dùng:

```java
public interface AfterSaveCallback<T> extends EntityCallback<T> {
    T onAfterSave(T entity, OutboundRow row, SqlIdentifier table);
}
```

Ví dụ, entity có thuộc tính transient để tầng gọi biết object vừa đi qua thao tác persistence:

```java
@Table("customer")
public class Customer {
    @Id
    private Long id;

    private String email;

    @Transient
    private boolean persistedInThisOperation;

    public Customer withPersistedInThisOperation(boolean value) {
        this.persistedInThisOperation = value;
        return this;
    }
}
```

Callback:

```java
@Component
public class CustomerAfterSaveCallback
        implements AfterSaveCallback<Customer> {

    @Override
    public Customer onAfterSave(
            Customer customer, OutboundRow row, SqlIdentifier table) {

        return customer.withPersistedInThisOperation(true);
    }
}
```

Giá trị transient được thêm vào object trả về sau thao tác save. Nó không được ghi thành cột database vì `@Transient` loại thuộc tính khỏi mapping persistence.

### 3.1 Thay đổi entity trong AfterSave không tự ghi lại database

Điểm quan trọng nhất của callback sau lưu là SQL đã được thực hiện trước khi callback này chạy. Nếu callback thay đổi một thuộc tính được ánh xạ thành cột, thay đổi đó chỉ nằm trong object được trả về; database không tự phát thêm một câu `UPDATE` để lưu thay đổi mới.

Ví dụ, nếu callback đổi `customer.email` sau save, không nên giả định email trong database cũng được đổi. Muốn lưu thay đổi đó, ứng dụng phải thực hiện một thao tác save/update riêng và thiết kế rõ transaction cùng khả năng phát sinh callback lặp.

Không nên gọi lại cùng repository `save` từ `AfterSaveCallback` cho chính entity đó. Điều này có thể tạo vòng lặp callback, truy vấn lồng nhau hoặc hành vi khó dự đoán. Nếu cần bước persistence thứ hai, hãy đặt nó trong service/use case với luồng xử lý tường minh.

### 3.2 Generated ID và giá trị database sinh ra

ID được database sinh ra là một phần của quy trình insert/mapping mà Spring Data R2DBC quản lý. Khi cần xử lý giá trị ID, hãy sử dụng entity được trả về từ `save` hoặc API insert tương ứng, thay vì tự suy luận thời điểm ID được gán trong callback.

Ví dụ:

```java
return customerRepository.save(customer)
    .flatMap(saved -> auditRepository.recordCreated(saved.getId())
        .thenReturn(saved));
```

Đoạn code dùng entity `saved` do repository trả về. Nếu callback sau save tạo một instance mới, instance đó cũng phải được trả về đúng theo contract callback để tiếp tục chuỗi xử lý.

## 4. Đăng ký entity callback trong Spring

Spring Data phát hiện các implementation `EntityCallback` được đăng ký thành bean trong application context. Có thể dùng `@Component` hoặc khai báo `@Bean` trong configuration.

Ví dụ khai báo bằng `@Bean`:

```java
@Configuration
public class CustomerCallbackConfiguration {

    @Bean
    AfterConvertCallback<Customer> customerAfterConvertCallback() {
        return (customer, row, table) ->
            customer.withDisplayLabel(
                customer.getFirstName() + " " + customer.getLastName());
    }
}
```

Với callback dạng lambda, cần bảo đảm class/kiểu trả về được đăng ký rõ để Spring nhận diện đúng bean callback. Với logic phức tạp hoặc cần dependency, một class `@Component` thường dễ đọc và kiểm thử hơn.

Callback được áp dụng cho entity type tương ứng. Tránh khai báo một callback tổng quát với logic không phân biệt loại entity nếu thao tác thực tế chỉ đúng với một domain type.

## 5. Callback đồng bộ và callback reactive

Spring Data cung cấp callback đồng bộ và biến thể reactive cho các thao tác reactive. Callback đồng bộ trả về entity trực tiếp; callback reactive trả về một `Publisher<T>`.

Ví dụ dạng reactive sau convert:

```java
@Component
public class CustomerReactiveAfterConvertCallback
        implements ReactiveAfterConvertCallback<Customer> {

    @Override
    public Publisher<Customer> onAfterConvert(
            Customer customer, Row row, SqlIdentifier table) {

        return Mono.just(customer.withDisplayLabel(
            customer.getFirstName() + " " + customer.getLastName()));
    }
}
```

Ví dụ minh họa callback trả về `Publisher<Customer>`; import và API cụ thể cần khớp phiên bản Spring Data Relational/R2DBC của dự án.

Với reactive callback:

- Không gọi `block()` để lấy kết quả từ một publisher khác.
- Trả về publisher để Spring Data nối vào pipeline persistence.
- Không gọi `subscribe()` bên trong callback vì sẽ tách công việc khỏi vòng đời thao tác đọc/lưu.
- Nếu callback có I/O bất đồng bộ, hãy cân nhắc chi phí và nguy cơ tạo nhiều truy vấn cho từng entity.
- Nếu chỉ chuẩn hóa chuỗi hoặc tính thuộc tính đơn giản, callback đồng bộ có thể đủ và dễ hiểu hơn.

Không dùng callback đồng bộ để thực hiện I/O blocking trong một luồng reactive. Điều đó có thể chặn thread xử lý và làm giảm khả năng mở rộng của ứng dụng.

## 6. Thứ tự thực thi khi có nhiều callback

Một ứng dụng có thể đăng ký nhiều callback cho cùng entity type hoặc cùng callback phase. Khi cần kiểm soát thứ tự, có thể dùng `Ordered` hoặc annotation `@Order` theo cơ chế ordering của Spring.

Ví dụ:

```java
@Component
@Order(100)
public class NormalizeCustomerAfterConvert
        implements AfterConvertCallback<Customer> {
    // Chuẩn hóa dữ liệu trước.
}

@Component
@Order(200)
public class BuildCustomerLabelAfterConvert
        implements AfterConvertCallback<Customer> {
    // Tạo label sau bước chuẩn hóa.
}
```

Trong ví dụ, callback có order nhỏ hơn được ưu tiên chạy trước trong cùng cơ chế sắp xếp. Hãy dùng thứ tự rõ ràng khi callback sau phụ thuộc kết quả callback trước. Tránh tạo quá nhiều callback có phụ thuộc ngầm; nếu một quy trình cần nhiều bước phối hợp, một callback hoặc service chuyên biệt có thể dễ theo dõi hơn.

Không nên giả định một thứ tự toàn cục giữa mọi loại callback khác nhau chỉ dựa vào `@Order`. Các phase `BeforeConvert`, `BeforeSave`, `AfterSave` và `AfterConvert` có vị trí riêng trong vòng đời persistence.

## 7. Phân biệt EntityCallback với lifecycle event

Spring Data cũng có cơ chế phát lifecycle event thông qua application event publisher. Event phù hợp khi ứng dụng muốn thông báo rằng một mốc vòng đời đã xảy ra để listener quan sát hoặc thực hiện phản ứng phụ.

Điểm khác nhau quan trọng:

| Entity callback | Lifecycle event |
|---|---|
| Được gọi như một phần của quy trình mapping/persistence. | Được publish qua cơ chế application event. |
| Có thể trả về entity đã biến đổi để Spring Data tiếp tục sử dụng. | Listener không trả entity thay thế cho thao tác persistence. |
| Có biến thể reactive cho reactive store. | Cách dispatch phụ thuộc event publisher và cấu hình application context. |
| Phù hợp để điều chỉnh entity hoặc dữ liệu mapping tại một phase cụ thể. | Phù hợp để thông báo/quan sát một sự kiện vòng đời. |

Nếu mục tiêu là thay đổi object trước khi caller nhận kết quả, entity callback thường phù hợp hơn. Nếu mục tiêu là thông báo cho thành phần khác rằng một thao tác đã xảy ra, event có thể phù hợp hơn. Tuy nhiên, lifecycle event sau save cũng không mặc nhiên có nghĩa transaction đã commit.

Với side effect cần chỉ chạy sau commit, phải dùng cơ chế after-commit phù hợp hoặc transactional outbox; không dựa vào tên `AfterSave` hay `AfterSaveEvent` để suy ra thời điểm commit.

## 8. AfterSave không đồng nghĩa after-commit

Đây là điểm dễ gây lỗi nhất khi dùng callback sau lưu. `AfterSaveCallback` chạy sau thao tác lưu entity ở tầng Spring Data. Nếu thao tác đó nằm trong một transaction lớn hơn, transaction có thể vẫn chưa commit.

Ví dụ:

```java
@Transactional
public Mono<Order> createOrder(CreateOrderCommand command) {
    return orderRepository.save(Order.from(command))
        .flatMap(saved -> validateAnotherCondition(saved)
            .thenReturn(saved));
}
```

Giả sử `AfterSaveCallback<Order>` đã chạy khi `orderRepository.save` hoàn tất, nhưng `validateAnotherCondition` sau đó phát lỗi. Transaction có thể rollback. Nếu callback đã gửi email hoặc message ra broker, side effect đó không được rollback cùng database.

Vì vậy, không nên dùng `AfterSaveCallback` để:

- Gửi email hoặc SMS không thể thu hồi.
- Publish message sang broker với giả định message chỉ tồn tại khi database commit.
- Gọi HTTP API để tạo tác động ở service khác.
- Ghi file/object storage mà không có cơ chế bù trừ.

Callback sau lưu thích hợp cho xử lý object cục bộ và metadata phục vụ caller. Với sự kiện cần phát bền vững, hãy ghi outbox row trong cùng transaction với entity, sau đó publisher riêng gửi message sau commit.

## 9. Kết hợp callback với auditing

Auditing của Spring Data có thể tự động quản lý các trường như người tạo, thời điểm tạo, người cập nhật và thời điểm cập nhật. Đây là xử lý trước khi dữ liệu được ghi, không phải trách nhiệm điển hình của `AfterSaveCallback`.

Ví dụ entity:

```java
@Table("customer")
public class Customer {
    @Id
    private Long id;

    private String email;

    @CreatedDate
    private Instant createdAt;

    @LastModifiedDate
    private Instant modifiedAt;

    @CreatedBy
    private String createdBy;

    @LastModifiedBy
    private String modifiedBy;
}
```

Cấu hình auditing cho R2DBC có thể dùng `@EnableR2dbcAuditing`:

```java
@Configuration
@EnableR2dbcAuditing
public class R2dbcAuditingConfiguration {
}
```

Nếu cần xác định người dùng hiện tại trong ứng dụng reactive, cấu hình `ReactiveAuditorAware<T>` theo API của phiên bản Spring Data đang dùng. Auditing callback của Spring Data sẽ điền giá trị trước khi lưu theo vòng đời phù hợp.

Không nên tự cập nhật `createdAt` trong `AfterSaveCallback`, vì câu SQL vừa thực thi có thể đã ghi giá trị cũ hoặc null. Nếu cần thay đổi trường audit trước khi lưu, dùng auditing infrastructure hoặc callback ở phase trước save.

## 10. Callback và entity immutable

Entity immutable thường dùng constructor hoặc record thay vì setter. Trong trường hợp này, callback phải trả một instance mới với giá trị mong muốn.

Ví dụ minh họa:

```java
public record Customer(
    Long id,
    String firstName,
    String lastName,
    String displayLabel
) {
    Customer withDisplayLabel(String value) {
        return new Customer(id, firstName, lastName, value);
    }
}

@Component
class CustomerAfterConvertCallback
        implements AfterConvertCallback<Customer> {

    @Override
    public Customer onAfterConvert(
            Customer customer, Row row, SqlIdentifier table) {

        return customer.withDisplayLabel(
            customer.firstName() + " " + customer.lastName());
    }
}
```

Spring Data tiếp tục sử dụng instance callback trả về. Nếu callback trả `null`, hoặc reactive callback phát `null`, publisher không có giá trị hợp lệ và thao tác có thể thất bại. Hãy luôn trả entity hợp lệ theo contract.

Với entity immutable, callback không được kỳ vọng sửa trực tiếp `Row` để thay đổi object đã được convert; hãy tạo object mới. Với `BeforeSaveCallback`, có thể chỉnh `OutboundRow` nếu mục tiêu là thay đổi dữ liệu ghi, nhưng phải hiểu sự khác nhau giữa giá trị trong entity và giá trị được gửi xuống database.

## 11. Callback không thay thế logic nghiệp vụ trong service

Callback phù hợp với logic kỹ thuật gắn chặt với vòng đời mapping/persistence, ví dụ chuẩn hóa định dạng, tạo thuộc tính transient hoặc thêm metadata trước khi ghi. Logic nghiệp vụ có điều kiện, phụ thuộc nhiều repository hoặc cần gọi hệ thống ngoài thường nên nằm trong service/use case.

Ví dụ không nên đặt toàn bộ quy trình xác nhận đơn hàng vào `AfterSaveCallback<Order>`:

```java
// Không nên để callback tự thực hiện cả workflow.
public Order onAfterSave(Order order, OutboundRow row, SqlIdentifier table) {
    // Gọi inventory, payment, email và broker từ đây.
    return order;
}
```

Cách làm đó ẩn dependency, khó kiểm soát transaction, có thể tạo truy vấn lặp và khiến việc lưu entity bất ngờ kích hoạt cả workflow. Hãy để service thể hiện thứ tự nghiệp vụ:

```java
@Transactional
public Mono<Order> confirmOrder(Long orderId) {
    return orderRepository.findById(orderId)
        .switchIfEmpty(Mono.error(new OrderNotFoundException(orderId)))
        .flatMap(order -> inventoryService.reserve(order)
            .then(order.confirm())
            .flatMap(orderRepository::save));
}
```

Các bước bên ngoài database vẫn cần outbox/saga hoặc cơ chế phối hợp riêng nếu phải bảo đảm nhất quán qua nhiều tài nguyên.

## 12. Hiệu năng và tác động khi callback chạy trên nhiều entity

Callback được gọi theo các thao tác entity mà Spring Data thực hiện. Một truy vấn trả về hàng nghìn entity có thể kích hoạt callback tương ứng cho từng entity được convert. Do đó:

- Tránh xử lý CPU nặng không cần thiết trong callback.
- Không thực hiện blocking I/O.
- Tránh gọi repository cho từng entity để không tạo N+1 queries.
- Tránh tạo object graph lớn hoặc giữ dữ liệu phụ trong cache toàn cục.
- Nếu cần gọi một dịch vụ bất đồng bộ, cân nhắc đưa ra service/use case hoặc một bước xử lý riêng sau khi truy vấn.
- Đo thời gian callback khi truy vấn có khối lượng lớn.

Reactive callback có thể trả publisher và không chặn thread nếu được viết đúng, nhưng nó vẫn có thể làm tăng số thao tác I/O và độ trễ tổng thể. Reactive không làm chi phí truy vấn phụ biến mất.

## 13. Phạm vi callback khi dùng các API truy cập dữ liệu

Callback gắn với quy trình entity mapping của Spring Data. Khi dùng repository hoặc `R2dbcEntityTemplate`, Spring Data quản lý việc convert entity và có thể gọi các callback tương ứng.

Khi dùng `DatabaseClient` để chạy SQL và tự map `Row` thành DTO bằng lambda, ứng dụng đang tự định nghĩa mapping. Không nên giả định mọi entity callback sẽ tự chạy trên object do lambda tạo ra. Nếu cần cùng một logic chuẩn hóa, có thể gọi mapper/helper dùng chung một cách tường minh.

Tương tự, SQL update/delete trực tiếp không nhất thiết đi qua vòng đời đọc/lưu entity như `save` hoặc `select`. Callback `AfterSaveCallback` không phải hook chung cho mọi câu lệnh `UPDATE` viết tay, và callback `AfterConvertCallback` không phải hook cho mọi lần đọc `Row` ở tầng SPI.

Khi sử dụng custom repository, native query hoặc API mức thấp, hãy xác định đường thực thi có đi qua mapping infrastructure hay không. Nếu callback là yêu cầu bắt buộc, nên viết integration test cho đúng API được dùng.

## 14. Kiểm thử AfterConvertCallback và AfterSaveCallback

Có thể kiểm tra callback riêng bằng unit test để xác nhận entity đầu vào được biến đổi đúng. Ví dụ:

```java
@Test
void trimsDisplayNameAfterConvert() {
    Customer customer = customerWithDisplayName("  Nguyen An  ");
    Row row = mock(Row.class);
    SqlIdentifier table = SqlIdentifier.unquoted("customer");

    Customer result = callback.onAfterConvert(customer, row, table);

    assertThat(result.getDisplayName()).isEqualTo("Nguyen An");
}
```

Với callback sau save, kiểm tra object trả về và xác nhận thuộc tính transient được xử lý theo mong đợi. Nếu callback trả instance mới, xác nhận caller nhận đúng instance đã biến đổi.

Integration test cần kiểm tra callback có thực sự được gọi qua đường repository/template của ứng dụng:

1. Lưu entity và xác nhận `AfterSaveCallback` được gọi.
2. Đọc entity bằng repository/template và xác nhận `AfterConvertCallback` được gọi.
3. Kiểm tra entity trả về có các thuộc tính được callback cập nhật.
4. Kiểm tra các thuộc tính `@Transient` không được ghi thành cột.
5. Nếu thao tác nằm trong transaction, cố ý phát lỗi sau save để xác nhận callback không bị hiểu nhầm là commit đã hoàn tất.
6. Kiểm tra callback không che lỗi mapping hoặc lỗi database.

Đối với reactive callback, dùng `StepVerifier` để kiểm tra publisher và bảo đảm callback không tự subscribe hoặc block. Integration test nên chạy trên driver/database tương ứng vì mapping và kiểu cột có thể khác giữa các hệ quản trị.

## 15. Những lỗi thiết kế thường gặp

| Cách làm | Hệ quả |
|---|---|
| Thay đổi entity trong callback nhưng không trả instance mới | Caller vẫn nhận object cũ, thay đổi bị mất. |
| Sửa field mapped trong `AfterSaveCallback` và nghĩ database đã đổi | Object trong bộ nhớ khác với dữ liệu đã ghi. |
| Gửi message trong `AfterSaveCallback` | Message có thể được gửi dù transaction sau đó rollback. |
| Gọi lại `save` từ callback sau save | Có thể tạo vòng lặp callback hoặc thao tác ghi lồng nhau. |
| Thực hiện blocking I/O trong callback reactive | Chặn thread và làm giảm khả năng mở rộng. |
| Truy vấn repository cho từng entity trong `AfterConvertCallback` | Dễ tạo N+1 queries. |
| Dùng callback để điều phối toàn bộ nghiệp vụ | Dependency và transaction boundary bị ẩn, khó kiểm thử. |
| Giả định raw `DatabaseClient` mapping cũng chạy entity callback | Logic callback có thể không được thực thi trên đường mapping tự viết. |

## 16. Chọn đúng cơ chế cho từng nhu cầu

| Nhu cầu | Cơ chế nên cân nhắc |
|---|---|
| Chuẩn hóa object sau khi đọc | `AfterConvertCallback`. |
| Tạo thuộc tính transient sau khi đọc | `AfterConvertCallback` hoặc mapper ở tầng query. |
| Thay đổi dữ liệu trước khi tạo outbound row | `BeforeConvertCallback`. |
| Điều chỉnh outbound row trước SQL | `BeforeSaveCallback`. |
| Xử lý object sau thao tác save | `AfterSaveCallback`. |
| Ghi `createdAt`, `modifiedAt`, `createdBy`, `modifiedBy` | Spring Data auditing. |
| Thông báo cho listener về lifecycle event | Application event nếu phù hợp với semantics và thời điểm. |
| Phát message chỉ sau khi database commit | Transactional outbox hoặc after-commit mechanism phù hợp. |
| Thực hiện quy trình nghiệp vụ nhiều bước | Service/use case, transaction và saga/outbox khi cần. |

## 17. Quy trình áp dụng callback trong dự án

Khi thêm xử lý sau đọc hoặc sau lưu, hãy xác định:

1. Logic thuộc về mapping/entity lifecycle hay là một bước nghiệp vụ độc lập?
2. Logic cần chạy sau convert, trước save hay sau save?
3. Callback có cần tạo entity mới hay chỉ sửa instance mutable?
4. Thay đổi chỉ phục vụ object trả về hay cần được ghi lại xuống database?
5. API truy cập dữ liệu có đi qua Spring Data entity mapping không?
6. Callback là synchronous hay reactive; có nguy cơ blocking hoặc phát sinh N+1 queries không?
7. Callback có side effect bên ngoài không; nếu có, transaction đã commit hay chưa?
8. Có nhiều callback cùng phase cần sắp xếp bằng `Ordered`/`@Order` không?
9. Có integration test xác nhận callback chạy trên đúng repository/template/driver không?

`AfterConvertCallback` phù hợp để xử lý entity sau khi đọc và chuyển đổi từ hàng database. `AfterSaveCallback` phù hợp để xử lý object sau thao tác lưu. Cả hai có thể trả về entity đã biến đổi, nhưng thay đổi sau save không tự ghi lại database và callback sau save không đồng nghĩa transaction đã commit. Giữ callback ngắn, tập trung vào mapping/object lifecycle; đặt workflow và side effect liên quan nhiều tài nguyên ở service, outbox hoặc saga sẽ giúp ranh giới nhất quán rõ ràng hơn.
