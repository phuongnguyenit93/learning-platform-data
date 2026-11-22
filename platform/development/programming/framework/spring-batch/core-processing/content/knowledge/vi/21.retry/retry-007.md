# Retry state và item identity trong Spring Batch

Trong chunk-oriented processing, một item có thể được xử lý lại khi thao tác đọc, xử lý hoặc ghi gặp lỗi tạm thời. Để giới hạn số lần thử và tránh nhầm lẫn giữa các lần xử lý, cơ chế retry cần biết item nào đang được thử lại và trạng thái retry hiện tại của item đó. Đây là lý do **retry state** và **item identity** có quan hệ chặt chẽ trong Spring Batch.

Item identity là định danh ổn định của một đơn vị dữ liệu nghiệp vụ trong suốt quá trình xử lý. Nó giúp framework gắn retry context với đúng item ngay cả khi sau rollback reader tạo một object Java mới cho cùng bản ghi. Nếu định danh không ổn định hoặc bị trùng, số lần retry có thể bị tính sai, trạng thái của hai item có thể va chạm hoặc một item có thể bị thử lại như thể nó chưa từng thất bại.

## 1. Retry state là gì?

Retry state là thông tin mà cơ chế retry giữ lại giữa các lần thử một thao tác thất bại. Nó có thể bao gồm số lần đã thử, exception gần nhất, trạng thái của retry policy và các thông tin nội bộ cần để quyết định có tiếp tục retry hay dừng.

Ví dụ, một processor gọi dịch vụ tra cứu bên ngoài. Dịch vụ có thể tạm thời trả về timeout. Job được phép thử lại một số lần trước khi kết luận item không thể xử lý:

```text
Item ORDER-42
    |
    v
Process lần đầu -> timeout
    |
    v
Retry state: đã có một lần thất bại
    |
    v
Process lần tiếp theo -> timeout
    |
    v
Retry state: tiếp tục theo giới hạn
    |
    v
Process lần tiếp theo -> thành công
```

Retry state giúp framework biết những lần gọi đó thuộc cùng một chuỗi retry của item ORDER-42. Nếu không nhận diện được cùng item, mỗi lần object xuất hiện lại có thể bị coi là một item mới và bộ đếm retry không phản ánh đúng tiến trình.

Retry state là trạng thái điều phối kỹ thuật của một lần xử lý. Nó không phải kết quả nghiệp vụ, không thay thế checkpoint của reader và cũng không tự làm cho thao tác bên ngoài trở nên idempotent.

## 2. Item identity là gì?

Item identity là khóa nhận diện một item logic trong nguồn dữ liệu. Khóa này thường đến từ định danh nghiệp vụ như order ID, customer ID, transaction ID hoặc tổ hợp các trường xác định duy nhất bản ghi trong một batch.

Ví dụ, hai object Java khác nhau vẫn có thể đại diện cho cùng một đơn hàng:

```java
Order firstRead = new Order("ORDER-42", new BigDecimal("125.00"));
Order readAgain = new Order("ORDER-42", new BigDecimal("125.00"));

System.out.println(firstRead == readAgain); // false
```

Hai object không cùng identity theo tham chiếu Java (==), nhưng có thể cùng item identity theo nghiệp vụ vì đều đại diện cho ORDER-42.

Trong Spring Batch, item identity cần đủ ổn định để cơ chế retry liên kết các lần thử của cùng một item. Đặc biệt, sau rollback, reader có thể đọc lại bản ghi và tạo object mới. Nếu retry state được khóa theo object identity hoặc theo một giá trị thay đổi giữa các lần đọc, framework có thể không tìm lại được retry context trước đó.

## 3. Vì sao retry cần nhận diện item?

Chunk step xử lý nhiều item trong cùng một transaction. Khi một item gây lỗi, transaction có thể rollback và framework phải thực hiện lại một phần công việc. Với stateful retry, retry state cần được giữ qua ranh giới rollback để lần xuất hiện tiếp theo của cùng item tiếp tục đúng chuỗi retry.

Ví dụ:

```text
Chunk: [A, B, C]
    |
    v
Processor xử lý A -> thành công
Processor xử lý B -> lỗi tạm thời
    |
    v
Chunk rollback
    |
    v
Framework xử lý lại item theo cơ chế retry
    |
    v
Reader có thể cung cấp lại B dưới dạng object mới
    |
    v
Retry state phải được liên kết với cùng item B
```

Nếu không có định danh ổn định, lần đọc lại có thể tạo key khác. Retry policy khi đó không thấy số lần thất bại trước và có thể cho phép nhiều lần thử hơn dự kiến. Ngược lại, nếu hai item khác nhau có cùng key, chúng có thể dùng chung retry state và làm một item bị dừng quá sớm.

Item identity vì vậy phải vừa **ổn định giữa các lần đọc lại** vừa **duy nhất giữa các item logic khác nhau trong phạm vi retry**.

## 4. Retry state khác ExecutionContext như thế nào?

Hai loại trạng thái này phục vụ hai mục đích khác nhau:

| Khía cạnh | Retry state | ExecutionContext |
| --- | --- | --- |
| Mục đích | Theo dõi chuỗi retry của thao tác/item lỗi. | Lưu checkpoint và trạng thái cần khôi phục của job/step. |
| Phạm vi | Gắn với item/operation được retry. | Gắn với StepExecution hoặc JobExecution. |
| Nội dung | Retry count, exception và trạng thái policy. | Reader position, khóa cuối, file name, tham số tiến độ hoặc metadata nhỏ. |
| Vòng đời | Theo vòng đời retry context và cache của cơ chế retry. | Được lưu qua JobRepository theo lifecycle execution. |
| Restart process | Không nên mặc định retry count còn nguyên sau khi JVM khởi động lại. | Được dùng để khôi phục execution khi restart theo quy tắc Spring Batch. |

Ví dụ, reader có thể lưu lastProcessedId=200 trong step ExecutionContext. Đây là checkpoint bền vững để reader tiếp tục sau khi job restart. Trong khi đó, retry state cho ORDER-201 theo dõi số lần thao tác xử lý item đó đã thất bại trong chuỗi retry hiện tại.

Không nên tự lưu retry count vào ExecutionContext chỉ vì muốn theo dõi số lần retry. Nếu nghiệp vụ cần số lần thử bền vững qua nhiều job execution, hãy thiết kế bảng trạng thái nghiệp vụ riêng với transaction, khóa và chính sách cập nhật rõ ràng.

## 5. Stateful retry và stateless retry

Retry có thể được tổ chức theo hai cách khái quát:

- **Stateless retry:** thao tác được thử lại ngay trong cùng phạm vi gọi, không cần gắn trạng thái retry lâu dài với item để khôi phục qua transaction boundary.
- **Stateful retry:** trạng thái của lần thử được giữ lại khi thao tác thoát ra do lỗi và được thử lại trong một transaction/lần xử lý tiếp theo. Framework cần nhận diện lại cùng item để tìm đúng retry context.

Trong batch processing, rollback transaction có thể là một phần của chiến lược phục hồi. Khi một item gây lỗi, transaction chunk được rollback; lần xử lý tiếp theo cần tiếp tục theo retry policy và retry state của chính item đó. Đây là trường hợp item identity đặc biệt quan trọng.

Không phải mọi exception đều cần retry qua rollback. Một lỗi tạm thời có thể được xử lý bằng retry ngay trong thao tác nếu operation an toàn và transaction không cần thoát ra. Ngược lại, nếu cần rollback để giải phóng lock hoặc khôi phục tài nguyên, stateful retry có thể phù hợp hơn.

Hãy chọn cách retry dựa trên loại lỗi, transaction boundary và khả năng thực hiện lại an toàn. Không dùng retry như một vòng lặp vô hạn để che giấu lỗi hạ tầng kéo dài.

## 6. Cấu hình retry cơ bản

Với lỗi tạm thời, có thể cấu hình retry trên fault-tolerant chunk step:

```java
@Bean
Step enrichOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        ItemProcessor<Order, EnrichedOrder> processor,
        ItemWriter<EnrichedOrder> writer) {

    return new StepBuilder("enrichOrdersStep", jobRepository)
        .<Order, EnrichedOrder>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .build();
}
```

Trong ví dụ, TransientDataAccessException được chọn vì nhóm lỗi này có thể phản ánh vấn đề truy cập dữ liệu tạm thời. retryLimit(3) giới hạn retry theo cấu hình của Spring Batch/Spring Retry. Số lần gọi thực tế cần được xác nhận bằng test cho phiên bản đang dùng, vì cần phân biệt lần gọi ban đầu với số lần retry được cho phép.

Chỉ retry những exception có cơ hội thành công khi thử lại. Lỗi dữ liệu không hợp lệ thường nên được validation, skip hoặc fail theo nghiệp vụ. Lỗi xác thực, sai schema hoặc lỗi lập trình hiếm khi được giải quyết bằng cách gọi lại cùng thao tác.

## 7. KeyGenerator dùng để xác định item identity

Khi cơ chế retry cần lưu context theo item, Spring Batch có thể dùng KeyGenerator để tạo khóa cho item. Có thể cấu hình key generator trong FaultTolerantStepBuilder.

Hợp đồng API thường dùng trong Spring Batch 5:

```java
public interface KeyGenerator {
    Object getKey(Object item);
}
```

Nếu item có equals() và hashCode() ổn định theo định danh nghiệp vụ, key mặc định dựa trên item có thể đáp ứng. Tuy nhiên, với DTO không có equality semantics rõ ràng, item mutable hoặc reader tạo object mới mỗi lần đọc, nên cung cấp key generator riêng dựa trên business key.

Ví dụ:

```java
@Bean
KeyGenerator orderRetryKeyGenerator() {
    return item -> {
        Order order = (Order) item;
        return order.getId();
    };
}
```

Đăng ký vào step:

```java
return new StepBuilder("enrichOrdersStep", jobRepository)
    .<Order, EnrichedOrder>chunk(100, transactionManager)
    .reader(reader)
    .processor(processor)
    .writer(writer)
    .faultTolerant()
    .retry(TransientDataAccessException.class)
    .retryLimit(3)
    .keyGenerator(orderRetryKeyGenerator)
    .build();
```

Key generator phải trả về khóa ổn định cho cùng item logic. Nếu item không phải Order, cần dùng đúng kiểu đầu vào của processor/reader; ví dụ cast ở trên chỉ phù hợp khi step thực sự xử lý Order.

## 8. Chọn business key ổn định

Một business key tốt cần đáp ứng các điều kiện:

1. **Ổn định:** cùng item được đọc lại phải tạo ra cùng key.
2. **Duy nhất:** hai item khác nhau trong cùng phạm vi xử lý không dùng chung key.
3. **Bất biến:** các trường tạo key không thay đổi giữa các lần thử.
4. **Nhỏ và dễ so sánh:** tránh đưa toàn bộ payload lớn vào key.
5. **Có phạm vi rõ ràng:** key cần phân biệt các batch/tenant/phiên bản nếu ID đơn lẻ có thể trùng.

Ví dụ, orderId có thể đủ nếu nó duy nhất toàn hệ thống. Nếu order ID chỉ duy nhất trong từng tenant, key nên bao gồm tenant:

```java
@Bean
KeyGenerator orderRetryKeyGenerator() {
    return item -> {
        Order order = (Order) item;
        return order.getTenantId() + ":" + order.getId();
    };
}
```

Nếu cùng một order có thể xuất hiện trong nhiều lần import với payload khác nhau, có thể cần thêm batch ID hoặc version:

```java
@Bean
KeyGenerator importRetryKeyGenerator() {
    return item -> {
        ImportedOrder order = (ImportedOrder) item;
        return order.getImportBatchId()
            + ":" + order.getTenantId()
            + ":" + order.getOrderId()
            + ":" + order.getSourceVersion();
    };
}
```

Đây là khóa nhận diện lần xuất hiện logic của item trong batch. Chọn thành phần nào phụ thuộc vào quy tắc nghiệp vụ; không thêm version nếu nó có thể thay đổi giữa lần đọc lại của cùng một item.

## 9. Vì sao không nên dùng object identity hoặc hash code tùy tiện?

Object identity (==) chỉ cho biết hai biến có trỏ đến cùng instance hay không. Sau rollback, reader có thể dựng một instance mới từ database row hoặc file line, nên tham chiếu khác dù dữ liệu logic giống nhau.

hashCode() cũng không tự động là business key. Một số lớp Java không override equals()/hashCode(), khi đó giá trị dựa trên object identity. Những lớp có override có thể dùng các trường mutable; nếu trường đó thay đổi sau khi key được lưu, việc tra cứu cache có thể không tìm thấy entry cũ.

Ví dụ không ổn định:

```java
public class Order {
    private String id;
    private BigDecimal total;
    private int retryMarker;

    // equals/hashCode được sinh từ toàn bộ field,
    // bao gồm retryMarker thay đổi trong lúc xử lý.
}
```

Nếu retryMarker thay đổi, hash/equality có thể thay đổi trong khi item đang là key của retry context. Hãy tránh dùng các field thay đổi theo xử lý làm thành phần định danh.

Một cách an toàn là dùng key bất biến:

```java
public record OrderRetryKey(String tenantId, String orderId) {}
```

Key generator có thể trả về một OrderRetryKey mới cho mỗi lần đọc; các record có cùng giá trị thành phần sẽ có equality ổn định.

## 10. Key collision và retry state bị dùng nhầm

Nếu hai item khác nhau tạo ra cùng key, retry context của chúng có thể bị chia sẻ hoặc ghi đè. Điều này gây ra lỗi khó phát hiện:

```text
Item A -> key = "ORDER-42" -> retry count = 2
Item B -> key = "ORDER-42" -> tìm thấy retry state của A
```

Item B có thể bị xem như đã retry nhiều lần dù nó chưa gặp lỗi, hoặc item A có thể mất trạng thái riêng. Vì vậy, key phải duy nhất trong phạm vi các item có thể được retry cùng lúc hoặc trong cùng retry context cache.

Các tình huống dễ collision:

- ID chỉ duy nhất trong tenant nhưng key chỉ dùng ID.
- Nhiều file đầu vào dùng lại cùng số thứ tự dòng.
- Một bản ghi được import lại ở các batch khác nhau nhưng key bỏ qua batch ID.
- Key generator chỉ dùng loại item hoặc một trường trạng thái chung.
- Dùng chuỗi rút gọn hoặc hash có khả năng va chạm mà không giữ thành phần định danh gốc.

Khi dùng composite key, chọn các thành phần xác định duy nhất một lần xuất hiện nghiệp vụ. Không đưa timestamp ngẫu nhiên tạo mới trong mỗi lần đọc vào key, vì nó sẽ biến cùng item thành nhiều key khác nhau.

## 11. Reader tạo object mới sau rollback

Một reader database có thể map mỗi row thành DTO mới. Khi chunk rollback và reader đọc lại cùng row, object mới có thể không bằng object trước theo equals(). Key generator dựa trên ID giúp framework nhận diện hai object là cùng item logic.

Ví dụ:

```java
public class OrderRowMapper implements RowMapper<Order> {

    @Override
    public Order mapRow(ResultSet rs, int rowNum) throws SQLException {
        return new Order(
            rs.getString("tenant_id"),
            rs.getString("order_id"),
            rs.getBigDecimal("total")
        );
    }
}
```

Mỗi lần mapper chạy có thể tạo một Order mới. Retry key nên dựa trên tenant_id và order_id, không dựa vào địa chỉ object trong heap.

Với reader file, định danh có thể gồm file identity và số dòng, hoặc business ID đã parse được. Với API phân trang, định danh có thể gồm source ID và record ID. Với queue, dùng message/event ID ổn định do producer tạo.

Nếu không thể lấy business ID vì lỗi xảy ra ngay trong read, callback/read skip chỉ có exception và thông tin nguồn mà reader cung cấp. Khi đó cần định danh nguồn như file path + line number hoặc message ID nếu có, nhưng không nên giả định KeyGenerator cho processor sẽ giải quyết mọi lỗi đọc trước khi item được tạo.

## 12. Item identity và reader buffering

Trong chunk step, Spring Batch có thể buffer item đã đọc để khi transaction rollback, item vẫn có thể được xử lý lại mà không phải đọc lại nguồn. Đây là một phần quan trọng trong việc điều phối retry và rollback.

Với nguồn transactional queue, cơ chế khác có thể được dùng vì broker có thể redeliver message khi transaction rollback. Cấu hình readerIsTransactionalQueue() cho biết reader lấy item từ transactional queue để framework không áp dụng cách buffering thông thường cho nguồn đó.

Dù item được lấy lại từ buffer hay được reader tạo lại, retry state cần được liên kết với đúng item logic. Không nên phụ thuộc vào một instance Java duy nhất nếu reader hoặc nguồn có thể tái tạo object. Dùng key ổn định là cách rõ ràng để thể hiện identity nghiệp vụ.

## 13. Retry state và RetryContextCache

Trong cơ chế retry stateful, thông tin retry cần được giữ giữa các lần thử. Spring Retry cung cấp khái niệm RetryContext và RetryContextCache; Spring Batch sử dụng cơ chế retry tương ứng trong fault-tolerant processing.

Ở mức khái niệm:

```text
Item
  |
  v
KeyGenerator -> item key
  |
  v
RetryContextCache[key]
  |
  +-- retry count
  +-- last exception
  +-- retry policy state
  |
  v
Retry decision
```

Cache cho phép tìm lại retry context bằng key khi cùng item xuất hiện lại. Key generator vì vậy là cầu nối giữa object item và retry state.

Không nên coi retry context cache là kho lưu bền vững cho toàn bộ lịch sử xử lý. Cache thường phục vụ vòng đời retry trong runtime của step. Nếu JVM dừng hoặc ứng dụng restart, không được giả định retry count cũ sẽ còn nguyên. Metadata bền vững của Spring Batch và checkpoint trong ExecutionContext có vai trò riêng.

Nếu hệ thống cần lưu audit số lần thử qua nhiều process restart, hãy ghi nhận vào bảng nghiệp vụ/technical audit riêng bằng một khóa operation ổn định. Không truy cập hoặc chỉnh sửa nội bộ retry cache để thay thế cơ chế lưu trạng thái chính thức.

## 14. Retry state được kết thúc khi nào?

Khi item xử lý thành công hoặc retry sequence kết thúc theo policy, retry context của item không còn cần cho lần thử tiếp theo trong cùng chuỗi. Cơ chế retry quản lý vòng đời context/cache theo implementation.

Ứng dụng không nên tự xóa entry trong retry cache hoặc tự đặt lại retry count bằng một key khác giữa các lần thử. Việc đó có thể làm framework mất khả năng nhận diện chuỗi retry và vượt giới hạn đã cấu hình.

Nếu một item thất bại vượt retry limit và sau đó được skip, listener có thể ghi nhận lỗi cuối cùng. Nếu exception không được skip, step có thể thất bại. Nếu job được restart, reader tiếp tục từ checkpoint đã commit và item chưa commit có thể được xử lý lại trong execution mới; retry state runtime trước đó không phải một bảo đảm lịch sử bền vững.

## 15. Phân biệt retry identity với idempotency key

Hai loại key có thể được tạo từ cùng business ID nhưng có mục đích khác nhau:

| Key | Dùng ở đâu | Mục đích |
| --- | --- | --- |
| Retry identity key | Cơ chế retry của Spring Batch | Nhận diện item để tìm retry state đúng. |
| Idempotency key | Writer, API hoặc consumer bên ngoài | Ngăn một thao tác nghiệp vụ bị áp dụng trùng khi request được gửi lại. |

Retry identity key không tự làm cho side effect idempotent. Ví dụ, key generator giúp Spring Batch nhận ra ORDER-42 đang được retry, nhưng nếu processor gọi API thanh toán hai lần với request ID khác nhau, khách hàng vẫn có thể bị charge hai lần.

Nếu gọi API ngoài, dùng idempotency key ổn định theo operation nghiệp vụ và truyền nó xuyên suốt mọi lần retry. Với database writer, dùng unique constraint, upsert hoặc kiểm tra trạng thái theo khóa nghiệp vụ. Với message, consumer nên lưu event ID đã xử lý để redelivery không tạo tác động lặp.

## 16. ProcessorNonTransactional và retry state

Trong fault-tolerant step, processor có thể được gọi lại khi chunk rollback. Nếu processor thực hiện phép biến đổi thuần nhưng tốn kém, ứng dụng có thể cân nhắc processorNonTransactional() để cache kết quả processor và tránh tính toán lại trong các lần xử lý lại phù hợp với cơ chế của step.

Ví dụ:

```java
return new StepBuilder("enrichOrdersStep", jobRepository)
    .<Order, EnrichedOrder>chunk(100, transactionManager)
    .reader(reader)
    .processor(processor)
    .writer(writer)
    .faultTolerant()
    .retry(TransientDataAccessException.class)
    .retryLimit(3)
    .processorNonTransactional()
    .build();
```

Tùy chọn này liên quan đến việc processor có cần được gọi lại sau rollback hay không; nó không thay thế KeyGenerator và không thay thế retry policy. Processor cần phù hợp với việc cache kết quả: không được phụ thuộc vào dữ liệu thay đổi theo thời gian mà không có snapshot, và không được thực hiện side effect khó lặp an toàn.

Không dùng processorNonTransactional() chỉ để che giấu một processor có side effect. Nếu processor gửi email hoặc gọi API tạo dữ liệu, cache kết quả không giải quyết được mọi tình huống restart, process crash hoặc transaction ngoài hệ thống.

## 17. Retry và Skip phối hợp với item identity

Retry và skip có thể được cấu hình cùng nhau:

```java
return new StepBuilder("importOrdersStep", jobRepository)
    .<Order, OrderEntity>chunk(100, transactionManager)
    .reader(reader)
    .processor(processor)
    .writer(writer)
    .faultTolerant()
    .retry(TransientDataAccessException.class)
    .retryLimit(3)
    .skip(InvalidOrderException.class)
    .skipLimit(20)
    .keyGenerator(orderRetryKeyGenerator)
    .build();
```

Ở đây:

- TransientDataAccessException được thử lại theo retry limit.
- InvalidOrderException có thể được skip trong skip limit.
- KeyGenerator xác định item identity để retry state được gắn với đúng order.
- Exception không thuộc retry hoặc skip policy sẽ làm step thất bại theo cấu hình.

Item identity không thay đổi quyết định exception nào được retry hay skip. Nó chỉ giúp quản lý trạng thái retry cho đúng item. Skip limit cũng khác retry limit: một giới hạn số item bị bỏ qua, giới hạn còn lại kiểm soát số lần thử lại.

## 18. Retry state trong partitioning và multi-threaded step

Khi step chạy đồng thời, nhiều item có thể có retry state cùng lúc. Key generator nên stateless và thread-safe. Không lưu item hiện tại hoặc retry count vào một field mutable dùng chung:

```java
// Không nên: field này có thể bị nhiều worker ghi đè.
private String currentOrderId;
```

Hãy tính key trực tiếp từ item:

```java
@Bean
KeyGenerator orderKeyGenerator() {
    return item -> {
        Order order = (Order) item;
        return new OrderRetryKey(order.getTenantId(), order.getId());
    };
}
```

Trong partitioning, mỗi worker step có StepExecution và retry sequence riêng. Tuy nhiên, cùng một business item không nên được giao đồng thời cho hai partition. Nếu partition range bị chồng lấn, hai worker có thể cùng xử lý một item và tạo side effect trùng dù retry key của mỗi worker ổn định.

Với remote partitioning, retry state thường thuộc runtime của worker xử lý partition. Không giả định retry cache được chia sẻ giữa các máy. Việc redelivery/restart ở worker khác cần dựa vào checkpoint, message identity và idempotency của thao tác ghi.

## 19. Những lỗi thường gặp khi chọn item identity

**Dùng object reference làm identity:** reader có thể tạo object mới sau rollback. Dùng business key ổn định để nhận diện cùng bản ghi.

**Dùng hash code mặc định:** lớp không override equals()/hashCode() có thể dựa trên object identity. Kiểm tra equality semantics hoặc cung cấp KeyGenerator.

**Dùng field mutable trong key:** thay đổi field sau khi retry context được lưu có thể khiến lần tra cứu không tìm thấy key cũ. Chỉ dùng trường bất biến.

**Key không duy nhất:** hai order ở tenant khác nhau có cùng ID có thể va chạm. Dùng composite key gồm tenant và business ID.

**Tạo UUID mới mỗi lần đọc:** cùng item có key khác sau rollback nên retry state bị tách thành nhiều chuỗi. Tạo key từ định danh nghiệp vụ ổn định.

**Dùng retry key làm idempotency key mà không xét operation:** một order có nhiều lần thanh toán hợp lệ có thể bị gộp nhầm. Thêm payment attempt hoặc operation ID khi cần.

**Nhầm retry cache với ExecutionContext:** retry count runtime không phải checkpoint bền vững. Dùng ExecutionContext cho vị trí đọc và dữ liệu restart.

**Cho rằng retry state tồn tại qua JVM restart:** không dựa vào retry cache như lịch sử bền vững. Nếu cần, lưu số lần thử nghiệp vụ trong kho dữ liệu riêng.

**Giữ state trong singleton KeyGenerator:** nhiều worker có thể gọi đồng thời. Tạo key từ input mà không giữ trạng thái chia sẻ.

**Dùng retry cho lỗi không thể phục hồi:** key ổn định không làm lỗi credential, schema hoặc bug tự biến mất. Phân loại exception và giới hạn retry.

## 20. Kiểm thử KeyGenerator

Nên kiểm tra key ổn định cho cùng item logic và khác nhau cho hai item khác nhau:

```java
class OrderRetryKeyGeneratorTest {

    private final KeyGenerator keyGenerator = item -> {
        Order order = (Order) item;
        return new OrderRetryKey(order.getTenantId(), order.getId());
    };

    @Test
    void generatesSameKeyForFreshInstancesOfSameOrder() {
        Order first = new Order("TENANT-A", "ORDER-42");
        Order second = new Order("TENANT-A", "ORDER-42");

        assertThat(keyGenerator.getKey(first))
            .isEqualTo(keyGenerator.getKey(second));
    }

    @Test
    void distinguishesOrdersFromDifferentTenants() {
        Order first = new Order("TENANT-A", "ORDER-42");
        Order second = new Order("TENANT-B", "ORDER-42");

        assertThat(keyGenerator.getKey(first))
            .isNotEqualTo(keyGenerator.getKey(second));
    }
}
```

OrderRetryKey là record bất biến:

```java
public record OrderRetryKey(String tenantId, String orderId) {}
```

Hai test này kiểm tra identity logic độc lập với Spring Batch. Bổ sung test cho batch ID/version nếu chúng là thành phần của key.

## 21. Kiểm thử retry state qua rollback

Một integration test nên mô phỏng reader trả về object mới cho cùng business record sau rollback. Processor hoặc writer có thể ném exception tạm thời một số lần, sau đó thành công.

Các điều cần xác nhận:

1. Các object khác instance nhưng cùng business key tạo ra cùng retry key.
2. Retry policy nhận biết các lần thử thuộc cùng item.
3. Retry count không bị reset chỉ vì reader tạo object mới.
4. Khi vượt giới hạn, step thất bại hoặc xử lý theo skip policy đúng cấu hình.
5. Item khác business key không dùng nhầm retry state của item trước.
6. Sau khi job restart, reader tiếp tục từ checkpoint bền vững; không giả định retry cache cũ vẫn còn.

Có thể dùng một reader test đếm số lần đọc và tạo new Order(...) ở mỗi lần đọc để kiểm tra key generator. Dùng processor test ném lỗi theo business ID và đếm số lần gọi, nhưng phải bảo đảm fixture mô phỏng đúng transaction rollback và reader behavior của step.

Không nên chỉ unit test KeyGenerator rồi kết luận retry trong job đã đúng. Integration test mới xác nhận framework sử dụng key đó trong fault-tolerant step và retry state được liên kết đúng qua lần xử lý lại.

## 22. Chọn item identity trong các nguồn dữ liệu khác nhau

| Nguồn | Identity thường dùng | Lưu ý |
| --- | --- | --- |
| Database table | Primary key hoặc tenant + primary key | Dùng khóa ổn định; tránh field có thể thay đổi trong lúc chạy. |
| CSV/file | File/batch ID + business ID hoặc line number | Line number chỉ duy nhất trong một file; thêm file identity. |
| Message queue | Message ID/event ID | Producer phải tạo ID ổn định để redelivery giữ nguyên identity. |
| API phân trang | Source ID + record ID/version | Token trang không nhất thiết là identity của từng record. |
| Nhiều tenant | Tenant ID + record ID | Tránh collision khi ID chỉ unique trong tenant. |
| Dữ liệu có nhiều phiên bản | Business ID + version hoặc operation ID | Chỉ thêm version nếu nó xác định một lần xuất hiện logic riêng. |

Nếu reader không thể tạo item do lỗi parse, không có object để truyền vào processor retry key. Với read skip, hãy ghi nhận nguồn lỗi qua exception metadata như file name, line number hoặc message identifier nếu reader cung cấp.

## 23. Cách thiết kế retry state và item identity trong production

Trước tiên, phân loại lỗi có thể retry và xác định transaction behavior cần thiết. Chọn retry limit và backoff phù hợp với thời gian phục hồi của hệ thống ngoài; tránh retry lỗi dữ liệu hoặc lỗi cấu hình không thể tự hết.

Tiếp theo, chọn business key ổn định cho item. Nếu item có equality/hash code bất biến và đúng theo nghiệp vụ, có thể dùng identity đó. Nếu reader tạo object mới, DTO mutable hoặc khóa nghiệp vụ là composite, cấu hình KeyGenerator để tạo key bất biến và duy nhất. Kiểm tra collision giữa tenant, batch, file hoặc operation khi các ID có phạm vi khác nhau.

Phân biệt retry state runtime với checkpoint trong ExecutionContext. Reader lưu vị trí đọc và trạng thái restart ở execution context; retry mechanism theo dõi chuỗi thử lại của item trong runtime. Nếu cần lịch sử retry qua process restart, lưu nó trong một kho dữ liệu nghiệp vụ/technical audit riêng.

Cuối cùng, bảo đảm thao tác writer hoặc API ngoài có idempotency độc lập với retry identity. Kiểm thử item được đọc lại dưới dạng object mới, key collision, retry vượt limit, rollback và restart. Khi item identity ổn định và retry state được gắn đúng item, Spring Batch có thể quản lý lần thử lại chính xác hơn mà không làm lẫn trạng thái giữa các bản ghi.
