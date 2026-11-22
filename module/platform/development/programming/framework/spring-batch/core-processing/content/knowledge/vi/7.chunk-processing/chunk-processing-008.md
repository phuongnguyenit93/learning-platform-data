# Lỗi giữa chunk và rollback

Trong Spring Batch, một Step xử lý theo chunk gom nhiều item thành một nhóm, ghi nhóm đó rồi commit transaction. Nếu lỗi xảy ra trước khi transaction của chunk được commit và lỗi đó được cấu hình để rollback, toàn bộ thay đổi thuộc transaction của chunk hiện tại sẽ được hoàn tác. Những chunk đã commit trước đó vẫn được giữ lại.

Ví dụ, Step xử lý 9 đơn hàng với commit interval bằng 3:

```text
Chunk 1: orders 1-3  --> WRITE --> COMMIT
Chunk 2: orders 4-6  --> WRITE --> ERROR --> ROLLBACK
Chunk 3: orders 7-9  --> chưa được thực hiện
```

Khi lỗi xảy ra ở chunk 2, các thay đổi cơ sở dữ liệu thuộc transaction của chunk 2 bị rollback. Kết quả đã commit của chunk 1 vẫn tồn tại. Spring Batch ghi nhận Step thất bại và có thể hỗ trợ restart từ trạng thái đã lưu, tùy khả năng restart của reader, cấu hình Step và cách ứng dụng quản lý dữ liệu.

## 1. Transaction boundary của chunk

Chunk-oriented processing thường gồm ba phần:

1. `ItemReader` đọc item từ nguồn dữ liệu.
2. `ItemProcessor` xử lý hoặc lọc từng item.
3. `ItemWriter` ghi một nhóm item đã xử lý.

Khi cấu hình `chunk(3, transactionManager)`, Spring Batch xử lý tối đa ba item trong một chunk trước khi ghi và commit transaction của chunk đó. Số 3 là commit interval trong ví dụ; ứng dụng có thể chọn giá trị khác theo kích thước dữ liệu, thời gian xử lý và giới hạn tài nguyên.

Luồng tổng quát:

```text
             Bắt đầu transaction
                     |
                     v
              ItemReader.read()
                     |
                     v
           ItemProcessor.process()
                     |
             đủ item / hết dữ liệu
                     |
                     v
              ItemWriter.write()
                     |
               +-----+-----+
               |           |
             thành công    lỗi cần rollback
               |           |
               v           v
             COMMIT     ROLLBACK
               |           |
               v           v
          Chunk kế tiếp  Chunk hiện tại
```

Trong chunk step thông thường, quá trình đọc, xử lý và ghi diễn ra trong transaction được quản lý bởi transaction manager của Step. Việc ghi dữ liệu chỉ được xem là bền vững sau khi transaction commit thành công. Khi exception làm transaction rollback, các thao tác tham gia cùng transaction đó được hoàn tác.

## 2. Điều gì xảy ra khi lỗi xuất hiện giữa một chunk?

Giả sử commit interval là 3 và `ItemWriter` ghi ba đơn hàng vào cùng một cơ sở dữ liệu. Writer ghi đơn hàng đầu tiên, ghi đơn hàng thứ hai rồi gặp lỗi khi ghi đơn hàng thứ ba.

```text
Chunk 2 (orders 4, 5, 6)
       |
       v
Transaction bắt đầu
       |
       +--> INSERT order 4
       |
       +--> INSERT order 5
       |
       +--> INSERT order 6 --> exception
                              |
                              v
                         ROLLBACK
                              |
                              v
             Các INSERT trong transaction bị hoàn tác
```

Nếu cả ba thao tác ghi sử dụng cùng transaction manager và cùng transaction cơ sở dữ liệu, các bản ghi 4 và 5 cũng bị rollback dù chúng đã được thực hiện trước khi lỗi xảy ra. Sau rollback, chúng chưa được commit vào cơ sở dữ liệu.

Rollback áp dụng cho transaction của chunk đang chạy. Nó không tự động xóa các thay đổi thuộc chunk trước đã commit, và cũng không tự động hoàn tác những tác dụng phụ nằm ngoài transaction.

### Ví dụ theo từng chunk

| Chunk | Item | Kết quả ghi | Trạng thái transaction |
|---|---|---|---|
| 1 | 1, 2, 3 | Ghi thành công | `COMMIT` |
| 2 | 4, 5, 6 | Lỗi khi ghi item 6 | `ROLLBACK` |
| 3 | 7, 8, 9 | Chưa chạy | Chưa có transaction |

Sau lỗi, dữ liệu của chunk 1 vẫn được giữ. Các thao tác ghi thuộc chunk 2 bị hoàn tác. Chunk 3 chưa được xử lý vì Step đã dừng tại lỗi.

## 3. Cấu hình commit interval

Với Spring Batch 5 trở lên, có thể cấu hình chunk step bằng `StepBuilder` và truyền `PlatformTransactionManager`:

```java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class OrderImportStepConfig {

    @Bean
    public Step importOrdersStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            ItemReader<Order> orderReader,
            ItemProcessor<Order, Order> orderProcessor,
            ItemWriter<Order> orderWriter) {

        return new StepBuilder("importOrdersStep", jobRepository)
                .<Order, Order>chunk(3, transactionManager)
                .reader(orderReader)
                .processor(orderProcessor)
                .writer(orderWriter)
                .build();
    }
}
```

Trong ví dụ:

- `chunk(3, transactionManager)` đặt commit interval là 3 và chỉ định transaction manager cho Step.
- `orderReader` cung cấp dữ liệu đầu vào.
- `orderProcessor` chuyển đổi hoặc kiểm tra từng đơn hàng.
- `orderWriter` ghi các item đã xử lý trong chunk.

Nếu writer ghi vào cơ sở dữ liệu được quản lý bởi cùng transaction manager, các thao tác ghi của chunk sẽ tham gia cùng transaction. Khi một exception gây rollback, những thay đổi trong transaction đó được hoàn tác.

Commit interval ảnh hưởng đến phạm vi rollback. Interval nhỏ làm transaction ngắn hơn và giới hạn số item trong một lần rollback, nhưng tăng số lần commit và overhead metadata. Interval lớn giảm số lần commit nhưng giữ transaction lâu hơn, dùng nhiều bộ nhớ hơn và có thể phải xử lý lại nhiều item hơn khi chunk thất bại.

## 4. Điều gì được giữ lại sau rollback?

Cần phân biệt dữ liệu nghiệp vụ, metadata thực thi và trạng thái của reader:

| Thành phần | Khi chunk rollback |
|---|---|
| Thay đổi cơ sở dữ liệu trong cùng transaction | Được hoàn tác. |
| Dữ liệu từ chunk trước đã commit | Vẫn được giữ. |
| Chunk tiếp theo chưa bắt đầu | Chưa có thay đổi. |
| Metadata và checkpoint | Được lưu theo cơ chế transaction và repository; trạng thái restart dựa trên checkpoint đã commit gần nhất. |
| Tác dụng phụ ngoài transaction | Không tự động được hoàn tác. |

Ví dụ, nếu chunk 1 đã commit và chunk 2 rollback, checkpoint bền vững thường tương ứng với vị trí cuối cùng đã commit thành công. Khi restart, một reader có hỗ trợ lưu trạng thái có thể tiếp tục từ vị trí phù hợp. Nếu reader không lưu trạng thái hoặc được cấu hình không lưu state, ứng dụng có thể phải đọc lại từ đầu hoặc tự quản lý vị trí tiếp tục.

Trong cùng một lần thực thi có retry hoặc skip, Spring Batch còn có thể buffer item đã đọc và điều phối việc đọc/xử lý lại theo chính sách fault-tolerant. Hành vi cụ thể phụ thuộc reader có transactional hay không, cấu hình retry/skip và loại lỗi. Vì vậy, không nên giả định một item sau rollback luôn được đọc lại từ nguồn theo cùng một cách ở mọi loại reader.

## 5. Lỗi ở Reader, Processor và Writer

Lỗi có thể phát sinh ở bất kỳ giai đoạn nào của chunk. Với transaction và rollback policy mặc định của một chunk step thông thường, exception cần rollback sẽ làm transaction của chunk hiện tại bị hoàn tác.

### Lỗi trong ItemReader

Reader có thể gặp lỗi khi truy vấn cơ sở dữ liệu, đọc file, parse dữ liệu hoặc gọi nguồn đầu vào. Nếu exception làm transaction rollback, chunk hiện tại không được commit. Reader cần có hành vi phù hợp khi được gọi lại hoặc khi Step restart.

### Lỗi trong ItemProcessor

Processor có thể phát hiện dữ liệu sai, không thể chuyển đổi hoặc gặp lỗi nghiệp vụ. Tùy chính sách, lỗi có thể làm rollback chunk, được retry hoặc được skip. Nếu processor gọi dịch vụ ngoài hoặc tạo tác dụng phụ, transaction cơ sở dữ liệu không tự động hoàn tác các tác dụng phụ đó.

### Lỗi trong ItemWriter

Writer thường ghi cả nhóm item của chunk. Nếu writer ném exception trước khi commit, transaction có thể rollback toàn bộ thao tác ghi của chunk nếu các thao tác tham gia cùng transaction. Writer cần tránh để một phần kết quả được commit độc lập trước khi chunk kết thúc.

## 6. Retry và skip ảnh hưởng thế nào đến rollback?

Spring Batch hỗ trợ xử lý lỗi có khả năng phục hồi bằng retry và skip. Hai cơ chế này có mục đích khác nhau:

- **Retry:** thử lại thao tác gặp lỗi, thường phù hợp với lỗi tạm thời như timeout hoặc deadlock.
- **Skip:** bỏ qua item gây lỗi nếu lỗi thuộc nhóm được phép bỏ qua và số lần skip chưa vượt giới hạn.

Trong fault-tolerant chunk step, một lỗi có thể khiến chunk rollback trước khi Spring Batch thử lại hoặc xác định item cần skip. Vì vậy, cùng một item có thể được xử lý nhiều lần. Processor và writer nên được thiết kế để chịu được việc thử lại.

Ví dụ cấu hình retry và skip:

```java
@Bean
public Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> orderReader,
        ItemProcessor<Order, Order> orderProcessor,
        ItemWriter<Order> orderWriter) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, Order>chunk(3, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .faultTolerant()
            .retry(TransientDataAccessException.class)
            .retryLimit(3)
            .skip(InvalidOrderException.class)
            .skipLimit(10)
            .build();
}
```

Trong cấu hình này, lỗi truy cập dữ liệu tạm thời được thử lại tối đa theo giới hạn retry; đơn hàng không hợp lệ có thể được skip trong giới hạn cho phép. Khi hết retry hoặc lỗi không được phép skip, Step có thể kết thúc `FAILED`.

Retry và skip không có nghĩa là mọi lỗi đều không rollback. Với chunk processing, rollback là một phần của cách Spring Batch khôi phục transaction trước khi thực hiện chiến lược xử lý lỗi. Cần đọc log và số liệu retry/skip để biết item nào đã được thử lại hoặc bỏ qua.

## 7. noRollback: ngoại lệ không làm rollback transaction

Trong một số tình huống, ứng dụng muốn một loại exception không làm transaction rollback. Spring Batch hỗ trợ khai báo `noRollback` cho các exception cụ thể trong fault-tolerant step.

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<Order, Order>chunk(3, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .noRollback(NonCriticalValidationException.class)
        .build();
```

`noRollback` thay đổi cách transaction phản ứng với exception được chỉ định. Nó không đồng nghĩa với `skip`: `skip` quyết định item lỗi có được bỏ qua hay không, còn `noRollback` quyết định exception có làm rollback transaction hay không.

Chỉ nên dùng `noRollback` khi ứng dụng bảo đảm trạng thái dữ liệu vẫn nhất quán nếu transaction tiếp tục commit. Nếu exception xảy ra sau khi một phần thao tác ghi đã thực hiện, cho phép commit có thể lưu dữ liệu chưa hoàn chỉnh. Hãy xác định rõ exception phát sinh ở giai đoạn nào và tác động đến các item khác trong chunk.

## 8. Rollback không hoàn tác mọi tác dụng phụ

Transaction chỉ có thể rollback các tài nguyên tham gia vào transaction đó. Nếu writer hoặc processor gọi một dịch vụ bên ngoài, gửi email, ghi file thông thường hoặc cập nhật một hệ thống khác không tham gia cùng transaction, rollback cơ sở dữ liệu không thể tự hoàn tác hành động đó.

Ví dụ:

```text
Chunk transaction
      |
      +--> INSERT order vào Database A
      |
      +--> Gọi HTTP để gửi đơn sang hệ thống B
      |
      +--> Lỗi khi xử lý item tiếp theo
      |
      +--> ROLLBACK Database A

Hệ thống B có thể vẫn đã nhận đơn hàng.
```

Nếu hệ thống B đã nhận yêu cầu, việc rollback Database A không tự gửi lệnh thu hồi cho B. Khi chunk được thử lại, yêu cầu HTTP có thể được gửi lần nữa.

Các cách thiết kế thường dùng để xử lý tình huống này:

1. **Idempotency key:** gửi mã nghiệp vụ duy nhất để hệ thống đích nhận diện và không thực hiện cùng yêu cầu nhiều lần.
2. **Transactional outbox:** ghi sự kiện cần gửi vào bảng outbox trong cùng transaction với dữ liệu nghiệp vụ; một tiến trình riêng gửi sự kiện sau khi commit.
3. **Compensation:** nếu hệ thống ngoài đã thực hiện hành động không thể rollback, tạo thao tác nghiệp vụ bù để sửa trạng thái.
4. **Phân tách Step:** ghi dữ liệu nghiệp vụ trong một Step và gửi thông điệp trong Step khác, với cơ chế retry và chống trùng phù hợp.

Nếu nhiều cơ sở dữ liệu hoặc tài nguyên cần commit nguyên tử cùng nhau, phải cấu hình transaction coordination phù hợp. Không nên giả định chỉ vì các thao tác nằm trong cùng một phương thức `ItemWriter` thì chúng tự động thuộc cùng một transaction.

## 9. Restart sau khi chunk thất bại

Khi một chunk thất bại và Job kết thúc `FAILED`, Spring Batch lưu metadata để có thể khởi động lại JobInstance nếu Job và Step cho phép restart.

Ví dụ:

```text
JobInstance: importOrders / fileId=orders-2026-11-15
  |
  +--> JobExecution #1: FAILED
         |
         +--> Chunk 1: COMMITTED
         +--> Chunk 2: ROLLED BACK
         +--> Chunk 3: chưa chạy

Restart cùng identifying JobParameters
  |
  +--> JobExecution #2
         |
         +--> Khôi phục từ checkpoint đã lưu
         +--> Tiếp tục xử lý phần còn lại
```

Với reader hỗ trợ restart và được cấu hình lưu state, `ExecutionContext` có thể giữ vị trí đọc tại ranh giới commit. Lần restart có thể tiếp tục từ checkpoint gần nhất thay vì xử lý lại toàn bộ dữ liệu. Chunk bị rollback sẽ được xử lý lại theo cách reader và Step hỗ trợ.

Một số điều kiện cần lưu ý:

- Job không được cấu hình `preventRestart` nếu muốn restart.
- Reader cần hỗ trợ lưu và khôi phục state nếu muốn tiếp tục từ vị trí đã commit.
- Các thành phần ghi phải chịu được khả năng item được thử lại.
- Các thao tác ngoài transaction cần có cơ chế chống trùng hoặc bù trừ.
- Phải dùng cùng identifying JobParameters để restart đúng JobInstance.

Nếu reader không lưu state, lần restart có thể bắt đầu đọc lại từ đầu. Khi đó writer phải được thiết kế để không tạo bản ghi trùng hoặc phải có chiến lược xóa/thay thế dữ liệu phù hợp.

## 10. Cách điều tra một lỗi giữa chunk

Khi Step thất bại, có thể dùng metadata và log để xác định phạm vi rollback:

1. **Xác định JobInstance và JobExecution.** Kiểm tra tên Job, identifying parameters và lần thực thi đang thất bại.
2. **Tìm StepExecution bị lỗi.** Xem `BatchStatus`, `ExitStatus` và exception được ghi nhận.
3. **Kiểm tra bộ đếm.** Đối chiếu `readCount`, `writeCount`, `filterCount`, skip counts, `commitCount` và `rollbackCount`.
4. **Xác định chunk cuối đã commit.** Đọc checkpoint trong `ExecutionContext` nếu reader hỗ trợ restart.
5. **Đối chiếu dữ liệu nghiệp vụ.** Kiểm tra những bản ghi đã tồn tại sau các transaction commit trước đó.
6. **Kiểm tra tác dụng phụ bên ngoài.** Xác định email, thông điệp, file hoặc API call nào có thể đã hoàn thành dù transaction cơ sở dữ liệu rollback.
7. **Chọn cách restart hoặc xử lý bù.** Bảo đảm không ghi trùng và không bỏ sót dữ liệu trước khi chạy lại.

Các bộ đếm giúp định hướng điều tra nhưng không thay thế việc kiểm tra dữ liệu thực tế. Ví dụ, `writeCount` trong metadata cần được đọc cùng transaction outcome, exception và trạng thái repository; không nên chỉ dựa vào một con số để kết luận mọi bản ghi đã commit.

## 11. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| Một item lỗi thì chỉ item đó bị rollback | Transaction thường bao phủ cả chunk; các thay đổi trong chunk hiện tại có thể cùng rollback. |
| Chunk rollback làm mất dữ liệu của mọi chunk trước | Các chunk đã commit vẫn được giữ. |
| Writer đã chạy xong một số lệnh SQL thì các lệnh đó chắc chắn được lưu | Nếu chúng tham gia cùng transaction và transaction rollback, các thay đổi bị hoàn tác. |
| Rollback database cũng thu hồi HTTP call hoặc email | Tác dụng phụ ngoài transaction không tự động được rollback. |
| Restart luôn bắt đầu đúng tại item gây lỗi | Restart thường dựa trên checkpoint đã commit; khả năng tiếp tục phụ thuộc reader và ExecutionContext. |
| Retry đồng nghĩa không có rollback | Retry có thể diễn ra sau rollback để thử lại thao tác trong transaction mới. |
| Skip và noRollback là một cơ chế | Skip quyết định bỏ qua item; noRollback quyết định exception có làm rollback hay không. |
| Commit interval càng lớn luôn càng nhanh | Chunk lớn có thể giữ transaction lâu, tăng bộ nhớ và tăng phạm vi xử lý lại khi lỗi. |

## Kết luận

Trong chunk processing, transaction thường bao phủ một chunk. Nếu lỗi xảy ra trước khi commit và thuộc loại cần rollback, Spring Batch hoàn tác các thay đổi trong transaction của chunk hiện tại. Những chunk đã commit trước đó vẫn tồn tại; chunk tiếp theo chưa được thực hiện. Retry, skip và noRollback có thể thay đổi cách xử lý lỗi nhưng cần được cấu hình theo tính nhất quán của dữ liệu. Rollback cũng chỉ tác động đến tài nguyên tham gia transaction, vì vậy các tác dụng phụ bên ngoài cần cơ chế idempotency, outbox hoặc compensation. Khi reader lưu checkpoint và Step hỗ trợ restart, Job có thể tiếp tục từ trạng thái đã commit gần nhất sau khi lỗi được xử lý.
