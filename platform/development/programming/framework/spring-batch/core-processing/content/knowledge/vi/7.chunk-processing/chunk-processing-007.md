# Chunk có ít item hơn commit interval

Trong Spring Batch, `commit-interval` xác định số item mà một chunk hướng tới xử lý trước khi transaction được commit. Tuy nhiên, **không phải chunk nào cũng phải có đủ số item bằng commit interval**. Trường hợp phổ biến nhất là chunk cuối cùng: khi `ItemReader` báo hết dữ liệu trước khi đạt đến ngưỡng, Spring Batch vẫn xử lý và commit phần item còn lại như một chunk nhỏ hơn.

Ví dụ, Step có `commit-interval = 100` nhưng nguồn chỉ có 237 bản ghi. Spring Batch xử lý hai chunk đủ 100 item và một chunk cuối có 37 item. Chunk cuối vẫn được xử lý trong transaction của nó và được commit khi quá trình xử lý thành công.

Hiểu đúng hành vi này giúp thiết kế reader, writer, transaction, checkpoint và số liệu giám sát chính xác hơn. Nó cũng giúp tránh nhầm lẫn giữa số item đã đọc, số item được processor giữ lại và số item thực sự được writer ghi.

## 1. Commit interval là ngưỡng kích thước chunk

Trong chunk-oriented processing, Spring Batch thực hiện một chu trình gồm đọc item, xử lý item, ghi kết quả rồi commit transaction. `commit-interval` là số item mà framework gom vào một chunk trước khi kết thúc chu trình commit thông thường.

Ví dụ cấu hình Step với chunk size là 100:

```java
@Bean
public Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        ItemProcessor<Order, Order> processor,
        ItemWriter<Order> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}
```

Với cấu hình này, Spring Batch cố gắng đọc đủ 100 item cho một chunk. Sau đó framework xử lý các item, gọi writer với kết quả còn lại và hoàn tất transaction của chunk. Khi đạt EOF sớm hơn, framework xử lý phần dữ liệu đã đọc được như chunk cuối.

Do đó, `100` là kích thước mục tiêu của chunk, không phải yêu cầu rằng mọi chunk phải có chính xác 100 item. Kích thước thực tế có thể nhỏ hơn, đặc biệt ở cuối nguồn dữ liệu hoặc khi một số item bị filter.

## 2. Chunk cuối cùng có ít item hơn commit interval

Giả sử nguồn dữ liệu có 237 đơn hàng và Step dùng commit interval 100. Reader trả lần lượt từng đơn hàng; khi không còn item, `read()` trả về `null` để báo kết thúc dữ liệu.

```text
Tổng số item đầu vào: 237
Commit interval:       100

Chunk 1: 100 item  -> process -> write -> commit
Chunk 2: 100 item  -> process -> write -> commit
Chunk 3:  37 item  -> process -> write -> commit
                                  |
                                  +--> Reader báo EOF
```

| Chunk | Số item đọc được | Kết quả |
|---|---:|---|
| Chunk 1 | 100 | Xử lý và commit |
| Chunk 2 | 100 | Xử lý và commit |
| Chunk 3 | 37 | Xử lý và commit như chunk cuối |
| Tổng | 237 | 3 chunk |

Khi reader trả về `null` sau item thứ 237, Spring Batch biết nguồn đã kết thúc. Phần 37 item đang có trong chunk không bị bỏ đi chỉ vì chưa đạt 100. Framework tiếp tục xử lý và ghi phần dữ liệu này, sau đó commit transaction nếu không có lỗi làm thất bại chunk.

Nếu tổng số item đúng bằng bội số của commit interval, ví dụ 200 item với interval 100, sẽ có hai chunk đủ 100. Khi framework bắt đầu đọc chunk kế tiếp và reader trả `null` ngay, Step kết thúc mà không có chunk dữ liệu cuối cần ghi.

## 3. Vì sao reader có thể kết thúc trước khi đủ chunk?

Trong contract của `ItemReader`, trả về `null` có nghĩa là không còn item để đọc. Spring Batch sử dụng tín hiệu này để kết thúc việc tạo chunk. Nếu số item đã đọc trong chunk hiện tại nhỏ hơn commit interval, phần còn lại chính là chunk cuối.

Ví dụ reader đơn giản:

```java
public class ListOrderReader implements ItemReader<Order> {

    private final Iterator<Order> iterator;

    public ListOrderReader(List<Order> orders) {
        this.iterator = orders.iterator();
    }

    @Override
    public Order read() {
        return iterator.hasNext() ? iterator.next() : null;
    }
}
```

Nếu danh sách có 237 phần tử, `read()` trả 237 item rồi trả `null`. Với chunk size 100, Spring Batch tạo hai chunk đầy đủ và một chunk cuối gồm 37 item.

Điểm quan trọng là `null` mang ý nghĩa EOF. Với nguồn dữ liệu tạm thời chưa có item nhưng có thể có thêm dữ liệu sau đó, không nên trả `null` để biểu thị “hiện chưa có dữ liệu”; làm như vậy sẽ báo cho Spring Batch rằng Step đã hết đầu vào. Reader cho nguồn streaming hoặc nguồn đến theo thời gian cần có cơ chế chờ, retry hoặc giao thức đọc riêng phù hợp với nguồn dữ liệu.

## 4. Chunk đầu vào và số item được ghi có thể khác nhau

Một nguyên nhân khác khiến writer nhận ít item hơn commit interval là `ItemProcessor` có thể filter item. Khi processor trả về `null`, Spring Batch hiểu rằng item đó bị loại khỏi kết quả đầu ra và không chuyển item đó cho writer.

Ví dụ:

```java
@Component
public class EligibleOrderProcessor implements ItemProcessor<Order, Order> {

    @Override
    public Order process(Order order) {
        if (!isEligible(order)) {
            return null; // Filter item, không phải skip do exception.
        }

        return normalize(order);
    }

    private boolean isEligible(Order order) {
        return order.getTotalAmount().signum() > 0;
    }

    private Order normalize(Order order) {
        // Chuẩn hóa dữ liệu trước khi ghi.
        return order;
    }
}
```

Giả sử một chunk đọc đủ 100 item, nhưng processor loại 10 item. Writer chỉ nhận 90 item. Kích thước chunk đầu vào vẫn là 100; số item đầu ra nhỏ hơn do filter.

| Chỉ số của chunk | Số lượng minh họa | Ý nghĩa |
|---|---:|---|
| Item được đọc | 100 | Reader cung cấp đủ một chunk |
| Item bị filter | 10 | Processor trả `null` cho 10 item |
| Item chuyển đến writer | 90 | Kết quả còn lại sau processing |

Nếu tất cả item trong chunk đều bị filter, writer không có item để ghi và Spring Batch không cần gọi writer với một chunk đầu ra rỗng. Việc filter vẫn khác với skip: filter là quyết định nghiệp vụ bình thường của processor; skip liên quan đến exception được cấu hình để bỏ qua trong quá trình đọc, xử lý hoặc ghi.

Vì vậy, khi thấy writer nhận ít item hơn commit interval, cần xác định đó là chunk cuối do EOF hay là kết quả sau khi processor filter, hoặc do các item bị skip theo cấu hình.

## 5. Transaction của chunk nhỏ vẫn được commit theo chunk

Một chunk cuối có 37 item không đồng nghĩa Spring Batch phải mở 37 transaction hoặc commit từng item riêng lẻ. Nó vẫn là một chunk và được xử lý trong transaction của chunk đó.

```text
Transaction của chunk cuối
       |
       +--> Đọc 37 item còn lại
       |
       +--> Process 37 item
       |
       +--> Writer ghi kết quả còn lại
       |
       +--> Commit transaction
```

Nếu quá trình xử lý và ghi thành công, transaction được commit. Nếu writer hoặc một thành phần khác ném exception làm transaction thất bại, transaction của chunk hiện tại có thể rollback theo cấu hình transaction và fault-tolerance của Step.

Các chunk đã commit trước đó vẫn giữ kết quả của chúng. Ví dụ, nếu chunk 1 và chunk 2 đã commit nhưng chunk cuối thất bại, rollback của chunk cuối không tự động hoàn tác hai chunk trước. Khi restart, Spring Batch dựa trên metadata và checkpoint đã lưu để tiếp tục theo thiết kế của reader/Step.

Đây là một đặc điểm quan trọng của chunk processing: commit interval xác định ranh giới transaction theo nhóm item, còn chunk cuối có thể nhỏ hơn nhóm mục tiêu mà vẫn có ranh giới commit riêng.

## 6. Ảnh hưởng đến checkpoint và restart

Với reader có trạng thái, Spring Batch có thể lưu tiến độ trong Step `ExecutionContext` tại các ranh giới commit. Khi Step được restart, reader khôi phục checkpoint đã lưu và tiếp tục đọc từ vị trí phù hợp.

Giả sử có 237 item, commit interval 100:

1. Chunk 1 xử lý 100 item và commit; checkpoint được cập nhật.
2. Chunk 2 xử lý 100 item và commit; checkpoint được cập nhật tiếp.
3. Chunk cuối xử lý 37 item nhưng writer gặp lỗi trước commit.
4. Transaction chunk cuối rollback; checkpoint của chunk chưa commit không được xem là tiến độ đã hoàn tất.
5. Khi restart, reader tiếp tục từ checkpoint của chunk cuối cùng đã commit và xử lý lại phần chưa hoàn tất.

Reader cần triển khai cơ chế lưu/khôi phục trạng thái phù hợp, thường thông qua `ItemStream` hoặc các reader tích hợp sẵn có hỗ trợ restart. Không nên chỉ giữ vị trí đọc trong một field của singleton bean, vì trạng thái trong bộ nhớ có thể mất khi ứng dụng restart và có thể bị dùng chung giữa các execution.

Với nguồn đầu vào có thể thay đổi, checkpoint nên dựa trên định danh ổn định như ID hoặc offset, không chỉ dựa trên vị trí nếu vị trí có thể dịch chuyển. Thiết kế checkpoint phải bảo đảm rằng dữ liệu được đọc lại sau restart khớp với dữ liệu nghiệp vụ đã commit.

## 7. Phân biệt filter, skip và chunk cuối

Ba tình huống có thể làm số item writer ghi nhỏ hơn commit interval nhưng có nguyên nhân khác nhau:

| Tình huống | Nguyên nhân | Cách hiểu |
|---|---|---|
| Chunk cuối | Reader trả `null` trước khi đủ commit interval | Không còn dữ liệu; phần item còn lại vẫn được xử lý và commit |
| Filter | Processor trả `null` cho item | Item được đọc nhưng không chuyển đến writer |
| Skip | Exception được cấu hình để bỏ qua | Item lỗi được xử lý theo skip policy; số item ghi có thể giảm |

Ví dụ, một chunk có 100 item đầu vào, 5 item bị filter và 2 item bị skip theo cấu hình. Số item chuyển tới writer có thể là 93. Con số này không có nghĩa commit interval đã thay đổi thành 93; nó phản ánh kết quả xử lý của chunk đó.

Skip và retry có thể làm framework đọc, xử lý hoặc ghi lại một số item tùy loại lỗi và cấu hình fault-tolerant. Vì vậy, không nên suy luận chính xác số lần gọi reader/processor/writer chỉ từ kích thước chunk cuối cùng.

## 8. Đọc số liệu StepExecution

`StepExecution` cung cấp các bộ đếm hữu ích để quan sát số lượng item và transaction. Một số chỉ số thường dùng:

| Chỉ số | Ý nghĩa tổng quát |
|---|---|
| `readCount` | Số item đọc thành công |
| `writeCount` | Số item được ghi thành công |
| `filterCount` | Số item bị processor filter |
| `readSkipCount` | Số item bị skip do lỗi ở bước đọc |
| `processSkipCount` | Số item bị skip do lỗi ở bước xử lý |
| `writeSkipCount` | Số item bị skip do lỗi ở bước ghi |
| `commitCount` | Số lần transaction commit được ghi nhận cho Step |
| `rollbackCount` | Số lần rollback được ghi nhận cho Step |

Có thể đọc các chỉ số này sau khi Step thực thi:

```java
public class ImportStepListener implements StepExecutionListener {

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        log.info(
                "step={}, read={}, written={}, filtered={}, commits={}, rollbacks={}",
                stepExecution.getStepName(),
                stepExecution.getReadCount(),
                stepExecution.getWriteCount(),
                stepExecution.getFilterCount(),
                stepExecution.getCommitCount(),
                stepExecution.getRollbackCount()
        );

        return stepExecution.getExitStatus();
    }
}
```

Không nên giả định `readCount` luôn bằng `writeCount`, hoặc `writeCount` luôn bằng `commitInterval × commitCount`. Filter, skip, chunk cuối nhỏ hơn ngưỡng, rollback và các lần thử lại đều có thể làm các chỉ số khác nhau. Hãy đọc các counter theo đúng ý nghĩa thay vì dùng một counter để suy ra tất cả.

## 9. Chọn commit interval phù hợp

Chunk cuối nhỏ hơn commit interval là hành vi bình thường, không phải dấu hiệu cấu hình sai. Khi chọn commit interval, hãy cân nhắc các yếu tố khác:

- **Chi phí transaction:** chunk lớn giảm số lần commit nhưng giữ transaction và tài nguyên lâu hơn.
- **Bộ nhớ:** chunk lớn cần giữ nhiều item trong bộ nhớ trước khi ghi.
- **Khả năng rollback:** lỗi trong chunk có thể khiến nhiều item của chunk đó phải xử lý lại.
- **Tải lên writer và database:** kích thước chunk ảnh hưởng số lượng item gửi trong mỗi lần ghi.
- **Độ trễ checkpoint:** commit interval lớn có thể làm checkpoint thưa hơn, khiến restart phải xử lý lại nhiều hơn sau sự cố.
- **Tính chất nguồn dữ liệu:** file, database cursor, API và message stream có đặc điểm đọc/ghi khác nhau.

Ví dụ, interval 100 có thể phù hợp với writer hỗ trợ batch insert. Nhưng nếu mỗi item tạo ra một thao tác I/O chậm hoặc transaction giữ lock lâu, cần đo và thử kích thước nhỏ hơn. Không cần cố làm cho số item cuối cùng chia hết cho interval; Spring Batch đã xử lý chunk cuối không đầy đủ.

## 10. Những nhầm lẫn thường gặp

**Cho rằng chunk nào cũng phải đủ commit interval.** Chunk cuối được phép có ít item hơn khi reader báo EOF. Phần dữ liệu còn lại vẫn được xử lý như một chunk.

**Cho rằng chunk nhỏ hơn sẽ bị bỏ qua.** Spring Batch xử lý và commit phần item cuối nếu quá trình hoàn tất thành công.

**Cho rằng writer luôn nhận đúng số item reader đọc.** Processor có thể filter item bằng cách trả `null`; skip cũng có thể làm số item được ghi giảm.

**Dùng `null` để báo nguồn tạm thời chưa có dữ liệu.** Với ItemReader, `null` biểu thị không còn item và kết thúc đầu vào của Step. Nguồn dữ liệu có thể tiếp tục phát sinh cần cơ chế đọc khác phù hợp.

**Cho rằng chunk cuối nhỏ thì commit từng item.** Chunk cuối vẫn là một đơn vị xử lý và transaction theo chunk; số item ít hơn không làm thay đổi mô hình commit.

**So sánh readCount và writeCount như hai số phải bằng nhau.** Filter, skip và lỗi xử lý làm hai bộ đếm khác nhau. Cần xem thêm filter/skip count và trạng thái Step.

## 11. Cách hiểu đúng khi vận hành

Khi quan sát một Step có commit interval 100 nhưng writer nhận 37 item ở lần cuối, hãy kiểm tra nguồn đầu vào có tổng cộng 237 item hay không. Nếu đúng, đây có thể chỉ là chunk cuối sau EOF. Nếu reader đã đọc đủ 100 nhưng writer chỉ nhận 90, hãy kiểm tra processor có filter 10 item hay không. Nếu có exception, xem skip/retry policy, rollback count và checkpoint để hiểu kết quả thực tế.

`commit-interval` quy định kích thước mục tiêu của chunk và ranh giới commit theo nhóm. Spring Batch vẫn xử lý phần dữ liệu còn lại khi nguồn kết thúc trước ngưỡng. Phân biệt kích thước chunk đầu vào với số item đầu ra, đồng thời hiểu transaction và checkpoint, sẽ giúp thiết kế Step và đọc số liệu vận hành chính xác.
