# Rollback và skip

Trong Spring Batch, rollback và skip là hai cơ chế khác nhau nhưng thường phối hợp khi một item gây lỗi trong chunk-oriented step. Rollback hoàn tác các thay đổi chưa commit của transaction hiện tại. Skip cho phép step loại một item lỗi khỏi quá trình xử lý và tiếp tục với các item còn lại, nếu exception thuộc loại được phép skip và giới hạn skip chưa bị vượt.

Điểm quan trọng là skip không có nghĩa transaction hiện tại chắc chắn được giữ nguyên. Khi một exception xảy ra, Spring Batch có thể rollback chunk để khôi phục trạng thái nhất quán, sau đó thực hiện recovery để xác định item lỗi và tiếp tục với phần dữ liệu hợp lệ. Vì vậy, một item cuối cùng bị skip vẫn có thể khiến chunk ban đầu rollback.

## 1. Rollback và skip giải quyết hai vấn đề khác nhau

Rollback là hành vi của transaction manager. Khi transaction chưa commit gặp lỗi cần rollback, các thay đổi thuộc transaction đó được hoàn tác. Skip là chính sách xử lý dữ liệu lỗi của Spring Batch: framework chấp nhận loại bỏ một item và tiếp tục step thay vì làm cả step thất bại.

| Cơ chế | Mục đích | Kết quả |
|---|---|---|
| Rollback | Bảo đảm các thay đổi chưa commit không được giữ lại khi transaction thất bại | Hoàn tác transaction hiện tại trên các tài nguyên được quản lý |
| Skip | Cho phép bỏ qua item có lỗi đã được cho phép | Item không được ghi thành công; step có thể tiếp tục |

Ví dụ, một chunk có 10 đơn hàng. Processor phát hiện đơn hàng thứ 4 có dữ liệu không hợp lệ. Nếu exception được cấu hình là skippable, Spring Batch có thể rollback lần xử lý chunk đang diễn ra, phục hồi trạng thái reader và chạy lại phần cần thiết mà không đưa item lỗi tới writer. Các item hợp lệ còn lại vẫn có thể được ghi và commit trong chunk recovery.

Rollback bảo vệ tính nhất quán của transaction; skip quyết định item lỗi có được phép loại bỏ hay không. Hai cơ chế bổ sung cho nhau.

## 2. Transaction boundary của chunk

Trong chunk-oriented processing, Spring Batch xử lý một nhóm item trong transaction của step. Reader lấy item, processor biến đổi từng item và writer ghi nhóm item đầu ra. Nếu chunk hoàn tất, transaction commit; nếu lỗi cần rollback xảy ra trước commit, transaction được rollback.

```text
Chunk transaction bắt đầu
        |
        v
     Reader
        |
        v
    Processor
        |
        v
     Writer
        |
        +-- tất cả thành công --> COMMIT
        |
        +-- lỗi cần rollback --> ROLLBACK
                                  |
                                  v
                              recovery
                                  |
                         skip / retry / fail
```

Các chunk đã commit trước đó là những transaction riêng và không bị rollback chỉ vì chunk sau thất bại. Rollback thông thường chỉ tác động đến transaction đang mở, trên những tài nguyên thực sự tham gia transaction đó.

Ví dụ step có `chunk(10, transactionManager)`: mỗi nhóm tối đa 10 item được xử lý trong một transaction. Nếu chunk thứ 5 lỗi và rollback, dữ liệu của chunk 1 đến 4 đã commit vẫn tồn tại. Spring Batch có thể tiếp tục hoặc kết thúc thất bại tùy skip/retry policy.

## 3. Cấu hình skip cho exception cụ thể

Trong Spring Batch 5, bật fault tolerance và khai báo exception có thể skip bằng `.skip(...)`. `skipLimit(...)` giới hạn tổng số item được phép skip trong step execution.

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderRow> reader,
        ItemProcessor<OrderRow, Order> processor,
        ItemWriter<Order> writer) {

    return new StepBuilder("importOrders", jobRepository)
        .<OrderRow, Order>chunk(10, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .skip(InvalidOrderException.class)
        .skipLimit(20)
        .build();
}
```

Trong ví dụ này, `InvalidOrderException` đại diện cho lỗi dữ liệu có thể loại bỏ. Step được phép skip tối đa 20 item theo chính sách. Các exception khác không tự động được skip; nếu không có retry hoặc policy xử lý khác, chúng có thể làm step thất bại.

Chỉ nên skip exception có ý nghĩa nghiệp vụ rõ ràng. Tránh `.skip(Exception.class)` vì cấu hình quá rộng có thể che giấu lỗi lập trình, lỗi kết nối, sai schema hoặc lỗi cấu hình hệ thống.

## 4. Skip limit được tính như thế nào?

`skipLimit(n)` đặt giới hạn tổng số skip của step execution. Giới hạn này được tính chung cho lỗi xảy ra ở các giai đoạn read, process và write, chứ không phải một giới hạn riêng cho từng giai đoạn.

Ví dụ với `.skipLimit(5)`: step có thể chấp nhận tối đa năm item bị skip. Khi phát sinh lần skip thứ sáu, step vượt giới hạn và thất bại.

| Số item đã skip | Hành vi với `skipLimit(5)` |
|---:|---|
| 0–4 | Vẫn còn trong giới hạn |
| 5 | Đã dùng hết hạn mức nhưng chưa vượt |
| 6 | Vượt giới hạn; step thất bại |

Skip limit là giới hạn cho một step execution, không phải ngân sách retry. Một item được retry nhiều lần rồi cuối cùng thành công không được tính là skip chỉ vì đã có các lần thử lỗi.

Đặt skip limit cần dựa trên chất lượng dữ liệu và yêu cầu nghiệp vụ. Nếu số item lỗi vượt ngưỡng, job nên dừng để tránh công bố kết quả thiếu dữ liệu.

## 5. Skip ở read, process và write

Spring Batch có thể skip lỗi phát sinh ở cả ba giai đoạn. Cách xác định item lỗi và dữ liệu listener nhận được khác nhau.

| Giai đoạn | Ví dụ lỗi | Item có sẵn để ghi nhận? |
|---|---|---|
| Read | Dòng CSV không parse được thành object | Thường không có item đã đọc thành công; chỉ có exception |
| Process | Thiếu mã đơn hàng hoặc dữ liệu không hợp lệ | Có item đầu vào của processor |
| Write | Vi phạm unique constraint khi ghi | Có item đầu ra hoặc chunk writer nhận; recovery có thể cần xác định item gây lỗi |

Ví dụ cấu hình skip cho hai loại lỗi:

```java
.faultTolerant()
.skip(MalformedInputException.class)
.skip(InvalidOrderException.class)
.skipLimit(50)
```

Không nên dùng cùng một exception chung cho mọi giai đoạn nếu cách phục hồi khác nhau. Việc phân loại rõ giúp xác định lỗi nào có thể bỏ qua và listener nào cần ghi nhận.

## 6. Khi skip vẫn làm rollback chunk

Một lỗi trong chunk có thể làm transaction rollback trước khi Spring Batch hoàn tất recovery. Sau rollback, framework có thể đọc/xử lý lại dữ liệu liên quan để cô lập item lỗi và loại item đó theo skip policy.

Ví dụ processor ném `InvalidOrderException` cho một item:

```text
Chunk ban đầu: A, B, C, D, E

Attempt ban đầu:
  process A -> OK
  process B -> OK
  process C -> InvalidOrderException
  transaction -> ROLLBACK

Recovery:
  xác định C là item lỗi
  bỏ C theo skip policy
  xử lý lại/tiếp tục với A, B, D, E theo cơ chế framework
  writer ghi các item hợp lệ
  transaction recovery commit
```

Đây là mô tả khái niệm; số lần callback reader/processor/writer được gọi lại phụ thuộc giai đoạn lỗi và cấu hình fault tolerance. Không nên giả định mọi item trong chunk chỉ được đọc hoặc xử lý đúng một lần.

Rollback trong recovery giúp các thao tác database chưa commit không để lại trạng thái một phần. Skip sau đó cho phép phần dữ liệu hợp lệ tiếp tục được ghi.

## 7. Phân biệt skip với filter bằng null

Processor có thể trả về `null` để filter một item có chủ đích. Filter không phải exception và không được tính là skip.

```java
@Bean
ItemProcessor<OrderRow, Order> orderProcessor() {
    return row -> {
        if (row.cancelled()) {
            return null; // Filter: item hợp lệ nhưng không thuộc đầu ra cần ghi
        }

        if (row.orderId() == null || row.orderId().isBlank()) {
            throw new InvalidOrderException("Order ID is required");
        }

        return toOrder(row);
    };
}
```

Trong ví dụ này, đơn đã hủy được filter theo quy tắc nghiệp vụ. Đơn thiếu mã bị ném exception và chỉ được skip nếu step cấu hình `InvalidOrderException` là skippable.

| Cách xử lý | Ý nghĩa | Tăng skip count? |
|---|---|---|
| Processor trả `null` | Filter item có chủ đích | Không |
| Processor ném exception được skip policy chấp nhận | Loại item lỗi theo fault tolerance | Có |
| Processor ném exception không được skip | Step có thể thất bại | Không được tính là skip thành công |

Không dùng `null` để che giấu dữ liệu lỗi vì như vậy số liệu skip và audit không phản ánh đúng chất lượng nguồn.

## 8. noRollback: exception không yêu cầu rollback

Spring Batch cho phép khai báo exception không làm rollback transaction bằng `.noRollback(...)` trong cấu hình fault-tolerant step. Cơ chế này hữu ích khi exception biểu diễn một tình huống mà các thao tác trước đó trong transaction vẫn có thể được giữ lại một cách an toàn.

```java
return new StepBuilder("processOrders", jobRepository)
    .<OrderRow, Order>chunk(10, transactionManager)
    .reader(reader)
    .processor(processor)
    .writer(writer)
    .faultTolerant()
    .skip(InvalidOrderException.class)
    .noRollback(InvalidOrderException.class)
    .skipLimit(20)
    .build();
```

`noRollback` điều chỉnh rollback classification; nó không tự biến exception thành skippable. Nếu muốn bỏ qua item, vẫn cần khai báo skip policy phù hợp. Hai cấu hình trả lời hai câu hỏi khác nhau: exception có được phép loại bỏ không, và khi exception xảy ra có cần rollback transaction không.

Chỉ dùng `noRollback` sau khi hiểu chính xác thao tác nào đã diễn ra trước exception. Nếu transaction đã ghi một phần dữ liệu nghiệp vụ mà không rollback, có thể để lại trạng thái không nhất quán. Với lỗi phát sinh trong processor trước khi writer ghi dữ liệu, trường hợp này có thể khác với lỗi xảy ra giữa một loạt thao tác ghi.

Không áp dụng `noRollback` rộng cho mọi exception. Hãy dùng loại exception cụ thể và kiểm thử bằng transaction thực tế.

## 9. Skip và retry phối hợp như thế nào?

Retry thử lại một thao tác có khả năng thành công nếu lỗi tạm thời biến mất. Skip chấp nhận loại bỏ item sau khi policy xác định không tiếp tục thử hoặc lỗi thuộc loại được phép skip.

Ví dụ một dịch vụ đối tác thỉnh thoảng timeout:

```java
return new StepBuilder("enrichOrders", jobRepository)
    .<OrderRow, EnrichedOrder>chunk(20, transactionManager)
    .reader(reader)
    .processor(processor)
    .writer(writer)
    .faultTolerant()
    .retry(TransientPartnerException.class)
    .retryLimit(3)
    .skip(InvalidOrderException.class)
    .skipLimit(25)
    .build();
```

Trong cấu hình này, timeout tạm thời được retry tối đa theo giới hạn đã đặt. Lỗi dữ liệu `InvalidOrderException` được skip. Nếu muốn lỗi đối tác sau khi hết retry cũng được skip, cần chủ động thêm exception đó vào skip policy và xác nhận nghiệp vụ cho phép loại bỏ item.

Không nên mặc định rằng hết retry thì mọi exception tự động được skip. Nếu exception không skippable, step sẽ thất bại khi recovery không thể tiếp tục.

## 10. Writer lỗi và rollback toàn chunk

Writer thường nhận một `Chunk` gồm nhiều item. Nếu writer ném exception khi ghi, transaction chunk có thể rollback. Khi fault tolerance được cấu hình, Spring Batch có thể thực hiện recovery để xác định item gây lỗi, retry hoặc skip theo policy.

Ví dụ writer ghi nhiều đơn hàng và một đơn vi phạm unique constraint:

```text
Writer nhận: [A, B, C, D]
  ghi A
  ghi B
  ghi C -> duplicate key exception

Transaction rollback:
  thay đổi A và B trong transaction bị hoàn tác

Recovery:
  xác định item gây lỗi theo cơ chế fault tolerance
  skip C nếu exception và skip limit cho phép
  ghi lại các item hợp lệ
```

Đừng giả định writer chỉ được gọi một lần. Khi recovery, writer có thể được gọi lại với chunk hoặc tập item khác. Writer phải an toàn khi được gọi lặp, đặc biệt nếu nó gọi API ngoài hoặc tạo side effect không nằm trong transaction database.

## 11. SkipListener ghi nhận item bị loại

`SkipListener` cung cấp callback theo giai đoạn để ghi nhận item bị skip. Đây là nơi phù hợp để lưu reject record, ghi lý do lỗi hoặc cập nhật metric cho từng item bị loại.

```java
public class OrderSkipListener implements SkipListener<OrderRow, Order> {

    private static final Logger log =
        LoggerFactory.getLogger(OrderSkipListener.class);

    @Override
    public void onSkipInRead(Throwable error) {
        log.warn("Input could not be read: {}", error.getMessage());
    }

    @Override
    public void onSkipInProcess(OrderRow item, Throwable error) {
        log.warn("Skipping order {}: {}", item.orderId(), error.getMessage());
    }

    @Override
    public void onSkipInWrite(Order item, Throwable error) {
        log.warn("Skipping order {} during write: {}", item.orderId(), error.getMessage());
    }
}
```

Đăng ký listener:

```java
.faultTolerant()
.skip(InvalidOrderException.class)
.skipLimit(20)
.listener(orderSkipListener)
```

`onSkipInRead` không nhận item vì reader không tạo được item hợp lệ. `onSkipInProcess` nhận item đầu vào của processor. `onSkipInWrite` nhận item đầu ra bị skip trong giai đoạn ghi.

Spring Batch thiết kế callback skip để được thông báo khi item thực sự bị skip trong quá trình recovery, thay vì coi mỗi lần exception xuất hiện là một skip cuối cùng. Listener nên ghi nhận có kiểm soát và tránh side effect không idempotent.

## 12. Ghi reject record và transaction

Nhiều hệ thống cần lưu bản ghi lỗi vào bảng reject để người vận hành có thể điều tra và xử lý lại. Có thể thực hiện việc này trong `SkipListener`, nhưng cần xem xét transaction boundary.

Nếu reject record được ghi vào cùng datasource và transaction phù hợp, thay đổi có thể tham gia transaction của step theo cách listener được gọi. Nếu ghi sang database khác hoặc hệ thống ngoài, thao tác có thể không rollback cùng chunk.

Các nguyên tắc nên áp dụng:

- Ghi khóa nghiệp vụ, nguồn dữ liệu, giai đoạn lỗi, loại exception và lý do đủ để điều tra.
- Dùng unique key hoặc idempotency key để tránh tạo reject record trùng khi recovery/restart.
- Không lưu toàn bộ payload nhạy cảm nếu không cần thiết.
- Nếu cần bảo đảm reject record và trạng thái skip được commit nhất quán, kiểm tra transaction manager và datasource thực tế.
- Không để lỗi ghi reject bị nuốt âm thầm; xác định rõ nếu reject store không khả dụng thì job phải dừng hay có cơ chế dự phòng.

Với dữ liệu cần audit chặt chẽ, có thể dùng outbox hoặc bảng staging trong cùng transaction database rồi xử lý thông báo riêng sau commit.

## 13. Rollback không hoàn tác side effect ngoài transaction

Rollback chỉ tác động đến tài nguyên tham gia transaction. Nếu processor hoặc writer gọi HTTP API, gửi email, publish message hoặc ghi file trực tiếp, transaction database không thể tự hoàn tác các hành động đó.

Ví dụ writer gửi lệnh thanh toán cho ba đơn hàng. Hai lệnh đầu đã được hệ thống bên ngoài chấp nhận, lệnh thứ ba timeout. Database transaction của chunk rollback không có nghĩa hai lệnh thanh toán đầu bị hủy.

Để tránh xử lý trùng hoặc trạng thái lệch:

1. Dùng idempotency key ổn định theo nghiệp vụ cho mỗi request bên ngoài.
2. Ghi yêu cầu vào outbox trong transaction database, rồi phát sau commit.
3. Với file, ghi file tạm và chỉ công bố sau khi transaction/step hoàn tất theo thiết kế.
4. Có cơ chế đối soát trạng thái sau timeout vì không biết request đã được hệ thống ngoài chấp nhận hay chưa.
5. Nếu cần đảo ngược hành động đã xảy ra, thiết kế compensation riêng; rollback database không thay thế compensation.

## 14. Ảnh hưởng của rollback đến reader state và checkpoint

Reader có thể lưu vị trí đọc trong `ExecutionContext`. Khi chunk rollback, Spring Batch cần khôi phục trạng thái phù hợp để item chưa commit không bị bỏ qua. Các reader có hỗ trợ `ItemStream` và lưu state thường phối hợp với cơ chế checkpoint của framework.

Không nên tự cập nhật checkpoint lên vị trí mới trước khi dữ liệu tương ứng được commit. Nếu checkpoint đi trước dữ liệu nghiệp vụ, restart có thể bỏ sót item. Nếu dữ liệu đã commit nhưng checkpoint không đồng bộ, item có thể được đọc lại; writer nên idempotent hoặc có khóa nghiệp vụ để xử lý an toàn.

Với reader không lưu state hoặc nguồn ngoài không hỗ trợ rollback, cần thiết kế cách đọc lại bằng khóa ổn định, offset hoặc cursor. Skip/retry không tự làm cho mọi reader tùy chỉnh trở nên restartable.

## 15. Exception nào rollback và exception nào được skip?

Skip policy và rollback classification là hai cấu hình độc lập. Một exception có thể được phép skip nhưng vẫn làm rollback transaction trước khi framework recovery. Ngược lại, cấu hình `noRollback` không tự động cho phép skip exception.

| Skip policy | Rollback policy | Ý nghĩa tổng quát |
|---|---|---|
| Không skippable | Rollback | Exception làm chunk rollback và step thường thất bại |
| Skippable | Rollback | Rollback/recovery có thể diễn ra, sau đó item được bỏ qua và chunk tiếp tục nếu hợp lệ |
| Skippable | No rollback | Item có thể được bỏ qua mà không rollback transaction theo classification; chỉ an toàn nếu các thay đổi trước đó vẫn hợp lệ |
| Không skippable | No rollback | Không tự skip; step vẫn có thể thất bại dù transaction không rollback theo classification |

Bảng này mô tả nguyên tắc; hành vi cụ thể còn phụ thuộc giai đoạn phát sinh exception, reader/writer, transaction manager và fault-tolerance implementation. Đặc biệt, lỗi trong writer có thể cần recovery khác với lỗi trong processor.

## 16. Khi nào nên dùng noRollback?

`noRollback` không phải lựa chọn mặc định để tăng tốc. Chỉ cân nhắc khi exception biểu thị một tình huống mà việc giữ các thay đổi transaction hiện tại là đúng về nghiệp vụ và không tạo dữ liệu một phần.

Ví dụ một processor phát hiện một item thuộc nhóm không cần ghi và ném exception đã được phân loại skip. Nếu processor chưa thực hiện thay đổi database nào, việc không rollback có thể tránh rollback không cần thiết trong một số thiết kế. Tuy nhiên, nếu trước đó trong cùng transaction đã có thao tác ghi, phải xác minh việc giữ các thay đổi đó không làm sai dữ liệu.

Trước khi dùng, hãy kiểm tra:

- Exception có thể phát sinh ở giai đoạn nào?
- Trước exception, transaction đã thay đổi dữ liệu gì?
- Các thay đổi đó có hợp lệ nếu item bị skip không?
- Reader/processor/writer có state cần rollback hoặc khôi phục không?
- Listener ghi reject có tham gia transaction nào?
- Integration test có chứng minh trạng thái database sau exception đúng không?

## 17. Những lỗi thường gặp khi kết hợp rollback và skip

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Cho rằng skip đồng nghĩa không rollback | Hiểu sai recovery; thay đổi trong chunk có thể đã bị hoàn tác | Phân biệt skip policy với transaction rollback |
| Skip mọi `Exception` | Che giấu lỗi hệ thống và lỗi lập trình | Chỉ skip exception dữ liệu cụ thể |
| Cho rằng hết retry tự động skip | Step vẫn thất bại nếu exception không skippable | Khai báo skip riêng khi nghiệp vụ cho phép |
| Dùng `noRollback` cho lỗi ghi không phân loại | Có thể giữ lại dữ liệu một phần | Chỉ cấu hình exception cụ thể và kiểm thử transaction |
| Ghi reject record không idempotent | Recovery/restart có thể tạo reject trùng | Dùng khóa duy nhất hoặc outbox |
| Gửi email/API trong listener rồi chunk rollback | Side effect ngoài transaction vẫn tồn tại | Phát sau commit hoặc dùng idempotency |
| Nuốt exception trong writer | Framework không biết chunk thất bại để rollback/recovery | Truyền exception ra ngoài |
| Không theo dõi skip count | Job hoàn thành nhưng chất lượng dữ liệu giảm | Theo dõi read/write/skip count và tỷ lệ lỗi |

## 18. Kiểm thử rollback và skip

Kiểm thử cần xác nhận cả trạng thái batch lẫn dữ liệu đã commit. Chỉ assert JobExecution là `COMPLETED` chưa đủ để chứng minh rollback và skip đúng.

Các trường hợp nên có:

1. Item hợp lệ: writer ghi dữ liệu và chunk commit.
2. Processor ném exception skippable: item bị bỏ qua, các item hợp lệ được ghi.
3. Exception không skippable: chunk rollback và step thất bại.
4. Skip limit vừa đủ: step tiếp tục khi số skip chưa vượt giới hạn.
5. Skip limit bị vượt: step thất bại và dữ liệu chưa commit của chunk được rollback.
6. Writer lỗi giữa chunk: kiểm tra các thay đổi database của transaction được rollback.
7. Kết hợp retry và skip: lỗi tạm thời thành công sau retry, lỗi dữ liệu bị skip.
8. `noRollback`: xác nhận chính xác thay đổi nào được giữ lại và vì sao điều đó an toàn.
9. SkipListener: reject record được ghi đúng số lần và không bị trùng khi recovery.
10. Side effect ngoài transaction: xác nhận idempotency hoặc compensation hoạt động khi chunk rollback.

Integration test nên dùng JobRepository, transaction manager và database tương thích với môi trường chạy. Dùng writer/processor giả lập lỗi ở các thời điểm xác định để quan sát commit/rollback và callback.

## 19. Quy trình lựa chọn rollback và skip trong production

Khi một item gây lỗi, hãy quyết định theo thứ tự:

1. Xác định lỗi là dữ liệu của riêng item hay lỗi hệ thống ảnh hưởng nhiều item.
2. Nếu lỗi tạm thời, cân nhắc retry có giới hạn trước khi skip.
3. Nếu item có thể loại bỏ theo nghiệp vụ, khai báo exception cụ thể là skippable và đặt `skipLimit` phù hợp.
4. Nếu item không được phép bỏ qua, để step thất bại khi retry không giải quyết được lỗi.
5. Xác định transaction có cần rollback khi exception xuất hiện; chỉ dùng `noRollback` khi giữ các thay đổi hiện tại là an toàn.
6. Ghi nhận item bị skip bằng `SkipListener` hoặc reject store có tính idempotent.
7. Kiểm tra side effect ngoài transaction và thiết kế outbox/compensation khi cần.
8. Theo dõi skip count, rollback, retry và trạng thái từng step để phát hiện dữ liệu nguồn hoặc hệ thống phụ thuộc suy giảm.

## Kết luận

Rollback hoàn tác các thay đổi chưa commit trong transaction hiện tại; skip cho phép Spring Batch loại một item lỗi và tiếp tục step nếu exception được cho phép và `skipLimit` chưa bị vượt. Khi recovery, chunk ban đầu có thể đã rollback trước khi item lỗi được xác định và bỏ qua. Vì vậy, skip không đồng nghĩa với việc transaction không rollback.

Hãy phân loại exception rõ ràng, cấu hình skip có giới hạn, dùng `SkipListener` để ghi nhận item bị loại và chỉ dùng `noRollback` khi các thay đổi trước exception vẫn hợp lệ. Rollback không hoàn tác side effect ngoài transaction, nên writer và tích hợp bên ngoài vẫn cần idempotency, outbox hoặc compensation để retry/restart an toàn.
