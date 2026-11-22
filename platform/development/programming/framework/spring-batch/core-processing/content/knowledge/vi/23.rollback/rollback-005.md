# NoRollbackExceptionClasses trong Spring Batch

Trong chunk-oriented processing, Spring Batch thường rollback transaction của chunk khi một exception thoát ra khỏi quá trình đọc, xử lý hoặc ghi. Rollback giúp đưa các thay đổi transactional chưa commit về trạng thái trước chunk, nhưng không phải exception nào cũng có nghĩa là transaction đã bị làm hỏng. Một số exception chỉ biểu thị rằng một item không hợp lệ và có thể bị bỏ qua mà không cần hoàn tác các thao tác khác trong chunk.

`NoRollbackExceptionClasses` là cách gọi nhóm các exception class được cấu hình để **không kích hoạt rollback** trong fault-tolerant step. Spring Batch cung cấp phương thức `.noRollback(...)` để khai báo các loại exception đó. Cấu hình này thay đổi cách transaction xử lý exception; nó không tự quyết định item có được skip hay không.

## 1. Rollback mặc định trong chunk step

Một chunk thường được xử lý trong một transaction. Nếu exception xảy ra và được xem là lỗi cần rollback, transaction hiện tại bị hoàn tác:

```text
BEGIN CHUNK TRANSACTION
        |
        v
READ -> PROCESS -> WRITE
        |
        v
Exception thoát ra
        |
        v
ROLLBACK
        |
        v
Chunk có thể được retry/skip hoặc step thất bại
```

Rollback bảo vệ tính nhất quán khi writer đã thay đổi database nhưng một phần khác của chunk thất bại. Các thao tác đã tham gia cùng transaction manager được hoàn tác. Chunk đã commit trước đó vẫn tồn tại.

Tuy nhiên, có exception không làm thay đổi dữ liệu transactional. Ví dụ processor kiểm tra một order và phát hiện trường bắt buộc bị thiếu. Nếu item đó được phép skip, việc rollback toàn bộ chunk có thể không cần thiết vì processor chỉ tính toán và chưa ghi dữ liệu. Trong trường hợp này, ứng dụng có thể cấu hình exception validation không làm rollback.

## 2. NoRollbackExceptionClasses là gì?

Trong Spring Batch, các exception class được liệt kê bằng `.noRollback(...)` tạo thành nhóm exception không cần rollback transaction theo cấu hình step.

API thường dùng trong Spring Batch 5:

```java
.faultTolerant()
.noRollback(InvalidOrderException.class)
```

Có thể khai báo nhiều loại:

```java
.noRollback(
    InvalidOrderException.class,
    OptionalFieldMissingException.class
)
```

Mặc định, exception trong chunk processing được xử lý theo quy tắc rollback của step. `noRollback` bổ sung các loại exception được phân loại là không cần rollback. Cấu hình này thường được dùng cùng skip policy khi ứng dụng muốn loại một item không hợp lệ và tiếp tục chunk mà không rollback transaction chỉ vì exception validation đó.

Tên `NoRollbackExceptionClasses` mô tả danh sách class; trong code ứng dụng, điểm cấu hình là phương thức `.noRollback(...)` trên fault-tolerant step builder.

## 3. noRollback không đồng nghĩa với skip

Đây là khác biệt quan trọng nhất:

| Cấu hình | Trách nhiệm |
| --- | --- |
| `.noRollback(ExceptionType.class)` | Quyết định exception có làm rollback transaction hay không. |
| `.skip(ExceptionType.class)` hoặc `SkipPolicy` | Quyết định exception có được phép bỏ qua để step tiếp tục hay không. |
| `.noSkip(ExceptionType.class)` | Đánh dấu exception không được bỏ qua theo skip classification. |
| `.retry(ExceptionType.class)` | Cho phép thử lại thao tác khi exception phù hợp với retry policy. |

Ví dụ:

```java
.faultTolerant()
.skip(InvalidOrderException.class)
.noRollback(InvalidOrderException.class)
.skipLimit(50)
```

Hai cấu hình đầu giải quyết hai câu hỏi riêng:

- `skip(...)`: item có thể bị loại bỏ vì lỗi validation này không?
- `noRollback(...)`: khi exception này xảy ra, transaction chunk có cần rollback không?

Nếu chỉ khai báo `.noRollback(...)` mà không cho phép skip, exception vẫn có thể làm step thất bại. Việc không rollback không biến exception thành thành công và không yêu cầu framework bỏ qua item.

Ngược lại, chỉ khai báo `.skip(...)` không có nghĩa transaction sẽ không rollback. Theo mặc định, framework vẫn có thể rollback để xử lý exception theo fault-tolerance flow. Chỉ thêm `noRollback` khi đã xác định rollback thực sự không cần thiết và transaction vẫn nhất quán.

## 4. Ví dụ validation exception có thể không cần rollback

Giả sử processor kiểm tra order trước khi tạo output. Nếu order thiếu customer ID, processor ném `InvalidOrderException`. Không có thao tác ghi database nào được thực hiện trong processor:

```java
public class OrderProcessor
        implements ItemProcessor<Order, OrderEntity> {

    @Override
    public OrderEntity process(Order order) {
        if (order.getCustomerId() == null) {
            throw new InvalidOrderException(
                "Missing customer id for order " + order.getId()
            );
        }

        return new OrderEntity(order.getId(), order.getCustomerId());
    }
}
```

Step có thể cho phép skip exception này và không rollback chỉ vì lỗi validation:

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        ItemProcessor<Order, OrderEntity> processor,
        ItemWriter<OrderEntity> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
        .<Order, OrderEntity>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .skip(InvalidOrderException.class)
        .noRollback(InvalidOrderException.class)
        .skipLimit(50)
        .build();
}
```

Với cấu hình này, order không hợp lệ có thể bị skip theo skip policy. Các order hợp lệ còn lại tiếp tục được xử lý. Vì processor không ghi side effect và exception chỉ thể hiện lỗi của item, transaction không cần rollback chỉ để bỏ qua order đó.

Đây là ví dụ phù hợp khi processor là phép biến đổi/validation thuần. Nếu processor đã ghi database, gọi API hoặc thay đổi trạng thái bên ngoài trước khi ném exception, giả định “không cần rollback” có thể không còn đúng.

## 5. Tác động theo từng phase: read, process và write

Tác động của `noRollback` phụ thuộc exception xảy ra ở đâu và những thao tác nào đã thực hiện trước đó.

| Phase | Ví dụ exception | Rủi ro khi không rollback |
| --- | --- | --- |
| Read | Reader phát hiện một dòng có định dạng không hợp lệ. | Thường không có dữ liệu ghi của item đó, nhưng reader phải có khả năng tiếp tục ở bản ghi kế tiếp. |
| Process | Processor ném lỗi validation trước khi tạo output. | Thường an toàn nếu processor không có side effect và chưa thay đổi resource transactional. |
| Write | Writer đã ghi một phần rồi mới ném exception. | Có thể commit một phần dữ liệu nếu các thao tác đó vẫn nằm trong transaction và exception được cấu hình không rollback. |

Vì vậy, `noRollback` thường dễ biện minh hơn cho exception validation ở processor, nơi chưa có thao tác ghi. Với write exception, cần đặc biệt thận trọng. Writer có thể đã ghi một số item trước khi phát hiện lỗi ở item khác. Nếu transaction không rollback, một phần chunk có thể được commit dù step đang xử lý lỗi.

Không nên cấu hình một exception chung là no-rollback cho mọi phase nếu nó có thể được ném từ reader, processor và writer với các trạng thái tài nguyên khác nhau. Tách exception class theo ý nghĩa và phase giúp kiểm soát transaction rõ ràng hơn.

## 6. noRollback và transaction boundary

`noRollback` thay đổi cách transaction phản ứng với exception, nhưng không thay đổi ranh giới chunk. Chunk vẫn có transaction theo commit interval; các chunk trước đó đã commit vẫn độc lập.

Nếu exception thuộc danh sách no-rollback thoát ra khỏi transaction interceptor, transaction có thể được commit thay vì rollback rồi exception vẫn tiếp tục được báo cho flow xử lý. Trong fault-tolerant step, framework còn áp dụng skip/retry classification để quyết định kết quả cuối. Do đó, cần kiểm tra cả trạng thái step lẫn dữ liệu thực tế sau transaction.

Một cách hình dung:

```text
Chunk transaction
    |
    +-- Processor ném InvalidOrderException
    |
    +-- noRollback classifier: không rollback
    |
    +-- SkipPolicy: cho phép skip item
    |
    +-- Các item còn lại được xử lý
    |
    +-- Chunk hoàn tất và commit
```

Nếu exception không được skip và được truyền ra ngoài, step vẫn có thể kết thúc thất bại. Vì transaction được phân loại no-rollback, các thay đổi đã thực hiện trong transaction có nguy cơ được commit. Đây là lý do `noRollback` không nên được xem như một cấu hình “an toàn mặc định” cho exception.

## 7. Exception class và quan hệ kế thừa

`.noRollback(...)` nhận các class exception. Khi thiết kế hierarchy, cần xác định exception cụ thể nào thực sự mang ý nghĩa không cần rollback.

Ví dụ:

```java
public class OrderException extends RuntimeException {
    public OrderException(String message) {
        super(message);
    }
}

public class InvalidOrderException extends OrderException {
    public InvalidOrderException(String message) {
        super(message);
    }
}

public class OrderPersistenceException extends OrderException {
    public OrderPersistenceException(String message) {
        super(message);
    }
}
```

Nếu khai báo:

```java
.noRollback(OrderException.class)
```

thì rule có phạm vi rộng tới nhóm exception con theo cơ chế phân loại class của framework. Điều này có thể khiến cả `OrderPersistenceException` cũng không rollback, dù lỗi ghi database thường cần rollback.

Tốt hơn là khai báo class cụ thể:

```java
.noRollback(InvalidOrderException.class)
```

Không nên dùng superclass chung cho validation, persistence, integration và programming errors nếu chúng có transaction behavior khác nhau. Với exception bị bọc trong exception khác, hãy kiểm tra loại exception thực tế được đưa vào classification trong phiên bản Spring Batch đang dùng và viết test cho wrapper/cause chain.

## 8. Kết hợp noRollback với skipLimit

`noRollback` không đặt giới hạn số item được phép bỏ qua. Skip limit vẫn được quản lý riêng:

```java
.faultTolerant()
.skip(InvalidOrderException.class)
.noRollback(InvalidOrderException.class)
.skipLimit(25)
```

Trong ví dụ, tối đa 25 item có thể bị skip theo skip policy của step. Skip limit là tổng số skip ở read, process và write, không phải 25 cho mỗi phase.

Nếu có item thứ 26 cần skip, step có thể thất bại vì vượt giới hạn. `noRollback` không làm giới hạn biến mất. Nó chỉ ảnh hưởng đến rollback classification của exception.

Khi skip limit bị vượt, cần xem xét trạng thái transaction tại thời điểm exception cuối cùng được ném. Nếu exception thuộc no-rollback, các thay đổi transactional đã thực hiện trong transaction có thể không bị hoàn tác. Vì vậy, không nên cho một exception đại diện cho lỗi writer một phần vừa được skip vừa không rollback nếu chưa có thiết kế đảm bảo dữ liệu nhất quán.

## 9. Kết hợp noRollback với retry

Retry và no-rollback có mục đích khác nhau. Retry thường cần thử lại thao tác lỗi; rollback có thể cần thiết để giải phóng lock, hủy thay đổi dở dang hoặc đưa transaction về trạng thái sạch trước lần thử tiếp theo.

Ví dụ cấu hình retry:

```java
.faultTolerant()
.retry(TransientDataAccessException.class)
.retryLimit(3)
```

Với lỗi truy cập database tạm thời, mặc định rollback thường phù hợp hơn vì transaction có thể đang ở trạng thái không đáng tin cậy. Nếu thêm:

```java
.noRollback(TransientDataAccessException.class)
```

hãy xác định rõ vì sao transaction vẫn an toàn để tiếp tục hoặc commit sau lỗi. Một lỗi timeout hoặc deadlock có thể xảy ra sau khi một phần thao tác đã được thực hiện; không rollback có thể giữ lại thay đổi dở dang hoặc lock/state không như mong muốn.

Không nên kết hợp retry và noRollback cho cùng exception chỉ để giảm overhead. Hãy kiểm tra thứ tự retry, transaction boundary và behavior của resource bằng integration test trước khi dùng trong production.

## 10. noRollback không thay thế noSkip

`noSkip` và `noRollback` có tên gần nhau nhưng điều khiển hai classifier khác nhau:

```java
.faultTolerant()
.noSkip(AccessDeniedException.class)
.noRollback(InvalidOrderException.class)
```

Ý nghĩa:

- `AccessDeniedException` không được bỏ qua; lỗi quyền truy cập phải làm step thất bại theo flow.
- `InvalidOrderException` được phân loại là không cần rollback. Nếu muốn step tiếp tục bằng cách bỏ item, cần cấu hình `.skip(InvalidOrderException.class)` hoặc policy tương ứng.

Có thể cấu hình một exception vừa `noSkip` vừa `noRollback`, nhưng đó là quyết định đặc biệt: exception làm step thất bại mà transaction không rollback. Trường hợp này có thể khiến dữ liệu đã thay đổi được commit dù job thất bại, nên cần có lý do nghiệp vụ rõ ràng và test chứng minh tính nhất quán.

## 11. Exception từ writer: trường hợp cần tránh noRollback

Giả sử writer xử lý chunk `[A, B, C]`. Writer ghi A và B vào database, sau đó gặp lỗi khi ghi C:

```text
BEGIN
  INSERT A
  INSERT B
  INSERT C -> exception
```

Nếu A, B và C cùng tham gia transaction và exception làm rollback, cả A và B được hoàn tác. Spring Batch có thể xử lý exception theo retry/skip policy để cô lập item lỗi.

Nếu exception được cấu hình no-rollback, transaction có thể commit các thay đổi đã thực hiện trước khi exception thoát ra. Khi đó A và B có thể tồn tại trong khi C không được ghi, dù chunk chưa hoàn thành theo dự định. Đây có thể tạo ra kết quả ghi một phần và làm restart khó dự đoán.

Với write exception, chỉ cân nhắc no-rollback nếu writer bảo đảm exception xảy ra trước mọi mutation transactional, hoặc writer có một hợp đồng nguyên tử khác đã được kiểm chứng. Trong đa số trường hợp ghi database, để rollback mặc định là lựa chọn an toàn hơn.

## 12. Processor cần thuần biến đổi khi dùng noRollback

Một processor thuần thường nhận item, kiểm tra/biến đổi và trả về output mà không ghi dữ liệu hay thực hiện side effect:

```java
public class OrderValidationProcessor
        implements ItemProcessor<Order, OrderEntity> {

    @Override
    public OrderEntity process(Order order) {
        if (order.getCustomerId() == null) {
            throw new InvalidOrderException("Customer id is required");
        }

        return new OrderEntity(order.getId(), order.getCustomerId());
    }
}
```

Trong trường hợp này, nếu exception chỉ thể hiện item không hợp lệ và item được skip, không có thay đổi nghiệp vụ nào của processor cần rollback. Đây là use case rõ ràng cho no-rollback classification.

Ngược lại, processor không nên:

- Ghi database qua một transaction khác rồi ném exception.
- Gửi email hoặc message trước khi writer hoàn tất.
- Gọi API tạo giao dịch mà không có idempotency.
- Sửa state mutable dùng chung rồi dựa vào rollback để khôi phục.

Nếu processor có side effect, noRollback có thể khiến thay đổi transactional còn lại được commit trong khi side effect đã xảy ra độc lập. Tốt hơn là chuyển side effect sang writer/outbox hoặc một bước riêng với trạng thái rõ ràng.

## 13. noRollback và listener

`SkipListener` được gọi khi item thực sự bị skip. `noRollback` không tự kích hoạt listener và cũng không thay đổi trách nhiệm của listener.

Ví dụ:

```java
public class InvalidOrderSkipListener
        implements SkipListener<Order, OrderEntity> {

    @Override
    public void onSkipInRead(Throwable t) {
        // Ghi nhận lỗi parse/đọc nếu có định danh nguồn.
    }

    @Override
    public void onSkipInProcess(Order item, Throwable t) {
        // Ghi nhận business key của item bị skip.
    }

    @Override
    public void onSkipInWrite(OrderEntity item, Throwable t) {
        // Ghi nhận output item không ghi được.
    }
}
```

Nếu listener lưu quarantine record vào cùng database transaction, bản ghi đó có thể commit cùng chunk khi transaction thành công. Nếu listener ghi ra hệ thống ngoài transaction, side effect đó không được database rollback bảo vệ. Hãy dùng idempotency hoặc outbox khi cần lưu dấu vết bền vững và tránh ghi trùng.

Không dùng listener để “sửa” transaction sau khi đã cấu hình noRollback. Listener chỉ quan sát sự kiện skip; transaction behavior vẫn do transaction manager và rollback classifier quyết định.

## 14. Kiểm thử noRollback bằng database transaction thật

Unit test chỉ xác nhận builder được gọi với cấu hình mong muốn không chứng minh transaction thực sự commit hay rollback đúng. Nên dùng integration test với database test và transaction manager thật.

Một test cho processor validation có thể:

1. Cung cấp ba item: hai hợp lệ và một không hợp lệ.
2. Processor ném `InvalidOrderException` cho item không hợp lệ.
3. Step cấu hình skip và noRollback cho exception đó.
4. Writer ghi hai output hợp lệ.
5. Xác nhận step hoàn tất, process skip count bằng một và hai bản ghi hợp lệ được commit.

Ví dụ assertion:

```java
JobExecution execution = jobLauncherTestUtils.launchJob(parameters);

assertThat(execution.getStatus()).isEqualTo(BatchStatus.COMPLETED);

StepExecution step = execution.getStepExecutions()
    .stream()
    .filter(s -> s.getStepName().equals("importOrdersStep"))
    .findFirst()
    .orElseThrow();

assertThat(step.getProcessSkipCount()).isEqualTo(1);
assertThat(step.getWriteCount()).isEqualTo(2);
assertThat(orderRepository.count()).isEqualTo(2);
```

Số lượng và tên step trong ví dụ cần khớp fixture thực tế. Kiểm tra cả metadata và dữ liệu database để xác nhận item lỗi đã bị skip còn item hợp lệ được commit.

## 15. Kiểm thử khác biệt giữa rollback và noRollback

Để hiểu tác động transaction, có thể xây dựng hai test riêng với cùng exception:

| Test | Cấu hình | Điều cần quan sát |
| --- | --- | --- |
| Baseline | Cho phép skip nhưng không khai báo noRollback | Xác nhận rollback behavior mặc định và số lần chunk/processor được gọi trong fixture. |
| No rollback | Cho phép skip và khai báo noRollback cho exception | Xác nhận transaction không rollback chỉ vì exception được phân loại này, đồng thời output hợp lệ vẫn được ghi. |

Không nên chỉ so sánh `commitCount` hoặc `rollbackCount` rồi kết luận. Những bộ đếm đó cần được đối chiếu với dữ liệu thực tế, listener invocation và trạng thái execution. Transaction manager, reader buffering và phase phát sinh exception đều ảnh hưởng kết quả.

Để kiểm tra rủi ro writer, tạo writer ghi một item rồi ném exception. Chỉ làm điều này trong database test cô lập và xác nhận rõ dữ liệu nào được commit khi exception thuộc noRollback. Test này giúp chứng minh vì sao không nên áp dụng noRollback rộng cho lỗi ghi.

## 16. Kiểm thử exception hierarchy và wrapper

Nếu policy dùng superclass, hãy kiểm tra cả subclass không mong muốn. Nếu exception có thể bị bọc bởi `ItemStreamException`, `UnexpectedInputException` hoặc một wrapper khác, hãy xác nhận loại exception mà Spring Batch thực sự phân loại.

Một bộ test nên bao gồm:

- Exception validation cụ thể được no-rollback.
- Subclass của exception được cấu hình.
- Exception persistence không vô tình bị no-rollback qua superclass chung.
- Exception wrapper/cause chain được xử lý như dự kiến.
- Exception không nằm trong danh sách vẫn rollback theo mặc định.

Việc kiểm tra hierarchy tránh trường hợp một thay đổi nhỏ trong code tạo exception subclass mới rồi vô tình thay đổi transaction behavior.

## 17. Các lỗi thường gặp khi dùng noRollback

**Cho rằng noRollback đồng nghĩa skip:** noRollback chỉ thay đổi rollback classification. Cần skip policy nếu muốn bỏ item và tiếp tục.

**Chỉ khai báo noRollback mà không khai báo skip:** exception vẫn có thể làm step thất bại; transaction có thể không rollback dù step thất bại.

**Áp dụng cho mọi exception:** lỗi writer, database hoặc hạ tầng có thể để lại thay đổi dở dang nếu transaction commit.

**Dùng superclass quá rộng:** exception persistence có thể kế thừa từ lớp được đánh dấu no-rollback. Chọn class cụ thể và test hierarchy.

**Dùng noRollback cho lỗi transient cần retry:** transaction có thể không trở về trạng thái sạch trước lần thử lại. Giữ rollback mặc định trừ khi có lý do được kiểm chứng.

**Không phân biệt phase:** cùng exception class có thể bị ném ở processor và writer; transaction risk của hai phase khác nhau.

**Tin rằng dữ liệu ngoài database sẽ rollback:** file, API, email và message không tự tham gia transaction. Dùng staging, outbox hoặc compensation.

**Chỉ kiểm tra trạng thái job:** step có thể FAILED nhưng transaction vẫn commit do no-rollback classification. Luôn kiểm tra dữ liệu thực tế.

## 18. Quy trình lựa chọn NoRollbackExceptionClasses trong production

Trước tiên, xác định exception đại diện cho điều gì và nó phát sinh ở phase nào. Chỉ chọn những exception cho biết một item riêng lẻ không hợp lệ, trong khi transaction hiện tại vẫn nhất quán và có thể tiếp tục. Processor validation thuần là trường hợp dễ biện minh; lỗi writer sau khi đã ghi một phần thường không phù hợp.

Tiếp theo, khai báo exception cụ thể bằng `.noRollback(...)`. Nếu muốn bỏ qua item, cấu hình `.skip(...)` hoặc `SkipPolicy` riêng và đặt `skipLimit` phù hợp. Không dùng `noRollback` thay cho retry hoặc noSkip. Kiểm tra exception hierarchy và wrapper để tránh phân loại rộng ngoài ý muốn.

Cuối cùng, chạy integration test với transaction manager và database thật. Xác nhận cả trạng thái `JobExecution`/`StepExecution`, skip count, commit/rollback count và dữ liệu cuối trong database. Kiểm thử riêng lỗi ở processor và writer để hiểu sự khác biệt về partial write. Với side effect ngoài transaction, dùng idempotency, outbox hoặc compensation.

`NoRollbackExceptionClasses` cho phép Spring Batch xử lý một số exception mà không rollback chunk transaction. Cấu hình này hữu ích khi exception chỉ biểu thị item không hợp lệ và không có thay đổi cần hoàn tác, đặc biệt trong processor thuần kết hợp với skip policy. Chọn class hẹp, hiểu phase phát sinh lỗi và xác minh bằng transaction test để tránh commit dữ liệu một phần khi step gặp lỗi.
