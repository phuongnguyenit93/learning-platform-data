# Phân biệt filter với skip

Trong Spring Batch, **filter** và **skip** đều có thể khiến một item không được ghi bởi `ItemWriter`, nhưng chúng biểu thị hai tình huống khác nhau. Filter là quyết định có chủ đích của `ItemProcessor`: item hợp lệ về mặt xử lý nhưng không thuộc kết quả cần tạo, vì vậy processor trả về `null`. Skip là cơ chế fault tolerance: một exception xảy ra khi đọc, xử lý hoặc ghi item được cấu hình là có thể bỏ qua, cho phép Step tiếp tục với các item khác trong giới hạn đã đặt.

Phân biệt đúng hai cơ chế giúp báo cáo dữ liệu chính xác. Ví dụ, đơn hàng đã hủy có thể được filter khỏi báo cáo; đơn hàng thiếu mã bắt buộc là dữ liệu lỗi và có thể được skip nếu nghiệp vụ cho phép. Nếu dùng filter để che lỗi dữ liệu, hệ thống sẽ mất thông tin về bản ghi không hợp lệ. Nếu dùng skip cho mọi item không cần xử lý, skip count sẽ phản ánh sai tình hình chất lượng dữ liệu.

## 1. Filter và skip trong chunk processing

Trong chunk-oriented Step, luồng xử lý cơ bản là:

```text
ItemReader
    |
    v
ItemProcessor
    |
    +-- Trả về object ------> ItemWriter
    |
    +-- Trả về null --------> Filter (không gửi đến writer)
    |
    +-- Ném exception -----> Skip policy / Retry / Step failure
```

`ItemProcessor` có thể trả về một object đầu ra hoặc `null`. Khi trả về `null`, Spring Batch xem item đã được filter và không chuyển nó đến writer. Không có exception nào được ném ra chỉ vì filter.

Ngược lại, skip bắt đầu từ một exception. Nếu exception thuộc loại được cấu hình skip và chưa vượt quá skip limit, Spring Batch bỏ qua item bị lỗi theo chính sách fault tolerance và tiếp tục xử lý. Nếu exception không được phép skip hoặc vượt giới hạn, Step có thể thất bại.

| Tiêu chí | Filter | Skip |
|---|---|---|
| Ý nghĩa | Loại item theo quy tắc nghiệp vụ có chủ đích. | Bỏ qua item do một lỗi được cho phép. |
| Cách kích hoạt phổ biến | Processor trả về `null`. | Reader, processor hoặc writer ném exception được cấu hình skip. |
| Có exception không? | Không cần exception. | Có exception làm căn cứ skip. |
| Bộ đếm | `filterCount`. | `readSkipCount`, `processSkipCount`, `writeSkipCount` và `skipCount`. |
| Có tính vào `skipLimit` không? | Không. | Có. |
| Có thể dùng `SkipListener` không? | Không, vì filter không phải skip event. | Có, để ghi nhận item bị skip. |
| Ví dụ | Bỏ đơn hàng đã hủy khỏi báo cáo. | Bỏ dòng CSV lỗi định dạng theo chính sách đã duyệt. |

## 2. Filter: processor trả về null

Filter phù hợp khi item không cần xuất hiện trong kết quả nhưng việc loại bỏ item là một quyết định bình thường của nghiệp vụ.

Ví dụ, một Job chỉ xuất các đơn hàng đã xác nhận. Đơn hàng chưa xác nhận không phải dữ liệu hỏng; chúng chỉ nằm ngoài phạm vi của báo cáo:

```java
public class ConfirmedOrderProcessor
        implements ItemProcessor<OrderInput, Order> {

    @Override
    public Order process(OrderInput item) {
        if (!item.confirmed()) {
            return null;
        }

        return new Order(
                item.orderId(),
                item.customerId(),
                item.amount());
    }
}
```

Khi processor trả về `null`:

- Item đã được reader đọc.
- Processor đã quyết định không tạo output cho item đó.
- Writer không nhận item đó.
- `filterCount` của `StepExecution` được tăng.
- Không có skip event và không tiêu thụ skip limit.

Một processor có thể vừa filter vừa chuyển đổi các item còn lại. Ví dụ, lọc đơn hàng đã hủy và chuyển đơn hàng còn hiệu lực sang model đầu ra:

```java
@Override
public Order process(OrderInput item) {
    if (item.cancelled()) {
        return null;
    }

    return toOrder(item);
}
```

Nên dùng filter khi điều kiện loại bỏ là quy tắc rõ ràng, ổn định và được chấp nhận trong nghiệp vụ. Có thể ghi nhận lý do filter bằng metric hoặc cơ chế audit riêng nếu báo cáo cần giải thích vì sao số item đầu vào lớn hơn số item được ghi.

## 3. Skip: bỏ qua item do exception

Skip dùng cho những lỗi đã được xác định là có thể bỏ qua mà không cần dừng toàn bộ Step. Trong chunk step, exception có thể phát sinh ở ba giai đoạn:

- **Read:** reader không thể đọc một bản ghi, ví dụ dòng CSV sai định dạng.
- **Process:** processor không thể xử lý một item, ví dụ mã nghiệp vụ không hợp lệ.
- **Write:** writer không thể ghi một item, ví dụ vi phạm ràng buộc dữ liệu mà chính sách cho phép bỏ qua.

Ví dụ, một đơn hàng thiếu mã đơn hàng là dữ liệu không hợp lệ. Processor ném exception thay vì trả `null`:

```java
public class OrderProcessor implements ItemProcessor<OrderInput, Order> {

    @Override
    public Order process(OrderInput item) {
        if (item.orderId() == null || item.orderId().isBlank()) {
            throw new InvalidOrderException("Order ID is required");
        }

        return toOrder(item);
    }
}
```

Nếu `InvalidOrderException` được cấu hình là skip exception và giới hạn chưa bị vượt, Spring Batch có thể bỏ qua item lỗi và tiếp tục xử lý các item còn lại.

Skip không có nghĩa là exception bị xem như chưa từng xảy ra. Đây là một quyết định xử lý lỗi có kiểm soát. Ứng dụng nên ghi nhận nguyên nhân, loại item và thông tin cần thiết để sửa dữ liệu hoặc đối soát sau này.

## 4. Cấu hình skip và skip limit

Trong Spring Batch 5, có thể bật fault tolerance và khai báo exception được phép skip trên chunk step:

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> orderReader,
        ItemProcessor<OrderInput, Order> orderProcessor,
        ItemWriter<Order> orderWriter) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, Order>chunk(500, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .faultTolerant()
            .skip(InvalidOrderException.class)
            .skipLimit(100)
            .build();
}
```

Trong ví dụ, tối đa 100 lỗi thuộc nhóm được cấu hình skip được chấp nhận theo giới hạn của Step. Khi số lần skip vượt giới hạn, Step thất bại. Các exception không thuộc chính sách skip cũng có thể làm Step thất bại.

`skipLimit` là giới hạn tổng hợp cho các skip ở giai đoạn đọc, xử lý và ghi, không phải một giới hạn độc lập cho từng giai đoạn. `filterCount` không được tính vào skip limit.

Ví dụ, nếu skip limit là 10 và Step đã skip 10 item, một lỗi tiếp theo thuộc loại được skip sẽ làm giới hạn bị vượt và Step không thể tiếp tục theo chính sách đó.

### Chỉ định exception không được skip

Có thể cấu hình một exception cụ thể không được skip bằng `noSkip`, kể cả khi một lớp cha của nó đã được khai báo skip:

```java
.faultTolerant()
.skip(Exception.class)
.noSkip(FatalImportException.class)
.skipLimit(50)
```

Đây chỉ là ví dụ minh họa quy tắc phân loại. Trong ứng dụng thật, không nên khai báo `skip(Exception.class)` một cách quá rộng vì có thể che giấu lỗi hệ thống, lỗi lập trình hoặc lỗi hạ tầng nghiêm trọng. Nên chỉ định các exception nghiệp vụ có thể bỏ qua.

### Dùng SkipPolicy tùy chỉnh

Nếu quyết định skip phụ thuộc vào loại lỗi, số lần lỗi hoặc ngữ cảnh, có thể dùng `SkipPolicy` tùy chỉnh thay vì liệt kê nhiều loại exception đơn giản. Policy phải đưa ra quyết định rõ ràng cho từng exception và số lần đã skip; nếu không cho phép skip, nó ném exception theo hợp đồng của `SkipPolicy`.

Policy tùy chỉnh hữu ích khi quy tắc nghiệp vụ phức tạp, nhưng cần giữ logic dễ hiểu và kiểm thử. Không nên dùng policy để biến mọi lỗi không rõ nguyên nhân thành skip.

## 5. Skip ở giai đoạn đọc (read skip)

Read skip xảy ra khi `ItemReader` ném exception trong lúc đọc item và exception đó được cho phép skip.

Ví dụ, reader đọc CSV gặp một dòng có cấu trúc sai. Nếu `FlatFileParseException` được cấu hình skip, Step có thể bỏ qua dòng lỗi và tiếp tục với dòng kế tiếp, tùy hành vi của reader và nguồn dữ liệu.

```java
.faultTolerant()
.skip(FlatFileParseException.class)
.skipLimit(25)
```

Read skip phù hợp với lỗi có thể xác định vị trí và tiếp tục đọc an toàn, chẳng hạn một dòng đầu vào không parse được. Nếu reader mất kết nối database hoặc gặp lỗi hệ thống không thể phục hồi, skip exception chung có thể khiến Job tiếp tục trong trạng thái dữ liệu không đáng tin cậy. Cần phân biệt lỗi của một bản ghi với lỗi của nguồn dữ liệu.

Với read skip, reader có thể không tạo được item hoàn chỉnh. Vì vậy, callback `SkipListener.onSkipInRead` chỉ nhận exception, không có item đầu vào để ghi nhận. Nếu cần biết dòng lỗi hoặc nội dung thô, exception của reader có thể cung cấp thông tin vị trí hoặc dữ liệu; hãy xử lý an toàn và tránh ghi toàn bộ dữ liệu nhạy cảm vào log.

## 6. Skip ở giai đoạn xử lý (process skip)

Process skip xảy ra khi `ItemProcessor.process` ném exception được cấu hình skip.

Ví dụ, item được đọc thành công nhưng không thỏa quy tắc dữ liệu:

```java
@Override
public Invoice process(InvoiceInput item) {
    if (item.amount() == null || item.amount().signum() <= 0) {
        throw new InvalidInvoiceException("Invoice amount must be positive");
    }

    return toInvoice(item);
}
```

Nếu `InvalidInvoiceException` được phép skip, item đó không được chuyển đến writer, còn Step có thể tiếp tục với item khác.

Process skip phù hợp khi:

- Lỗi gắn với một item cụ thể.
- Item lỗi không thể được sửa bằng retry tự động.
- Nghiệp vụ cho phép tiếp tục xử lý các item còn lại.
- Ứng dụng có thể lưu lại lý do để sửa hoặc đối soát.

Nếu lỗi chỉ là tạm thời, ví dụ một dịch vụ tham chiếu đang timeout, retry có thể phù hợp hơn skip. Nếu bỏ qua lỗi tạm thời, kết quả nghiệp vụ có thể thiếu dữ liệu đáng lẽ phải xử lý được.

## 7. Skip ở giai đoạn ghi (write skip)

Write skip xảy ra khi `ItemWriter` ném exception và exception đó được cấu hình skip. Ví dụ, database từ chối ghi một bản ghi do vi phạm unique constraint, trong khi chính sách nghiệp vụ cho phép loại bản ghi trùng.

```java
.faultTolerant()
.skip(DuplicateOrderException.class)
.skipLimit(100)
```

Writer thường nhận một nhóm item, vì vậy lỗi ghi có thể liên quan đến một item hoặc toàn bộ batch. Spring Batch có thể phải rollback chunk và phân tích lại item để xác định phần tử gây lỗi theo cơ chế fault tolerance. Điều này có thể làm reader/processor/writer được gọi lại trong quá trình xử lý lỗi.

Vì vậy, writer cần được thiết kế phù hợp với transaction và khả năng gọi lại. Không nên thực hiện tác dụng phụ ngoài transaction trong writer nếu không có cơ chế idempotency. Nếu database trả lỗi cho cả batch và không thể xác định bản ghi lỗi theo cách an toàn, Step có thể thất bại thay vì skip tùy tiện.

## 8. Ghi nhận skip bằng SkipListener

SkipListener cho phép ứng dụng ghi nhận item bị skip để tạo báo cáo lỗi, lưu thông tin vào bảng reject hoặc gửi đến một luồng xử lý dữ liệu lỗi riêng.

Interface có các callback chính:

```java
public interface SkipListener<I, O> {
    void onSkipInRead(Throwable t);
    void onSkipInProcess(I item, Throwable t);
    void onSkipInWrite(O item, Throwable t);
}
```

Ví dụ listener ghi log theo từng giai đoạn:

```java
public class OrderSkipListener implements SkipListener<OrderInput, Order> {

    @Override
    public void onSkipInRead(Throwable exception) {
        log.warn("Could not read an input record: {}", exception.getMessage());
    }

    @Override
    public void onSkipInProcess(OrderInput item, Throwable exception) {
        log.warn("Skipping order input {}: {}",
                item.orderId(), exception.getMessage());
    }

    @Override
    public void onSkipInWrite(Order item, Throwable exception) {
        log.warn("Skipping order {} during write: {}",
                item.orderId(), exception.getMessage());
    }
}
```

Đăng ký listener vào Step:

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(500, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .skip(InvalidOrderException.class)
        .skipLimit(100)
        .listener(orderSkipListener)
        .build();
```

Ví dụ trên tập trung vào cách đăng ký và các callback; ứng dụng cần khai báo logger, kiểu dữ liệu và chính sách lưu lỗi phù hợp. `onSkipInRead` không có item vì reader có thể không tạo được item. `onSkipInProcess` nhận item đầu vào, còn `onSkipInWrite` nhận item đầu ra đã được processor tạo.

SkipListener dành cho skip do exception. Khi processor trả về `null`, listener này không được gọi. Nếu muốn audit cả filter, hãy tạo metric hoặc listener/cơ chế ghi nhận riêng cho quyết định filter.

## 9. Filter và skip ảnh hưởng đến bộ đếm như thế nào?

`StepExecution` lưu các bộ đếm giúp phân biệt item được đọc, item bị filter và item bị skip:

| Bộ đếm | Ý nghĩa |
|---|---|
| `readCount` | Số item reader đọc thành công. |
| `filterCount` | Số item processor loại bỏ bằng cách trả về `null`. |
| `writeCount` | Số item writer ghi. |
| `readSkipCount` | Số item bị skip do exception khi đọc. |
| `processSkipCount` | Số item bị skip do exception khi xử lý. |
| `writeSkipCount` | Số item bị skip do exception khi ghi. |
| `skipCount` | Tổng số skip qua các giai đoạn. |

Ví dụ một Step có số liệu:

| Chỉ số | Giá trị |
|---|---:|
| `readCount` | 1.000 |
| `filterCount` | 100 |
| `processSkipCount` | 15 |
| `writeSkipCount` | 5 |
| `readSkipCount` | 0 |
| `writeCount` | 880 |

Ví dụ này cho thấy 100 item bị filter theo quy tắc, 20 item bị skip do lỗi và 880 item được writer ghi. Đây là bộ số minh họa; trong ứng dụng thực tế, các bộ đếm có thể chịu ảnh hưởng của retry, rollback, writer ghi nhiều đầu ra cho một item hoặc cách reader/writer triển khai.

Không nên áp dụng một công thức đơn giản cho mọi Step như `readCount = writeCount + filterCount + skipCount`. Các bộ đếm phản ánh hoạt động của từng giai đoạn, nhưng writer có thể ghi nhiều output cho một input hoặc các lần rollback/retry làm quy trình phức tạp hơn. Hãy đọc các chỉ số cùng log và kết quả dữ liệu.

## 10. Kết hợp filter, skip và retry

Một Step có thể dùng đồng thời filter, skip và retry vì chúng giải quyết các trường hợp khác nhau:

- Filter item hợp lệ nhưng không thuộc phạm vi cần ghi.
- Retry lỗi tạm thời có khả năng phục hồi.
- Skip lỗi item đã được xác định là có thể bỏ qua.
- Làm Step thất bại khi lỗi nghiêm trọng hoặc vượt giới hạn skip/retry.

Ví dụ:

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(500, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .skip(InvalidOrderException.class)
        .skip(FlatFileParseException.class)
        .skipLimit(100)
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .noSkip(FatalImportException.class)
        .build();
```

Processor có thể trả về `null` cho đơn hàng bị hủy. Nếu một item có dữ liệu không hợp lệ, processor ném `InvalidOrderException`; nếu reader không parse được một dòng, nó có thể ném `FlatFileParseException`; nếu writer gặp lỗi truy cập database tạm thời, exception có thể được retry. `FatalImportException` được loại khỏi chính sách skip.

Thứ tự và cách phân loại exception cần phản ánh ý nghĩa lỗi. Không nên cấu hình retry và skip cho cùng một exception một cách tùy tiện; hãy xác định hành vi mong muốn khi retry hết số lần cho phép và kiểm tra chính sách xử lý cuối cùng.

## 11. Chọn filter hay skip theo tình huống

### Đơn hàng đã hủy

Nếu Job chỉ tạo báo cáo đơn hàng đang hoạt động, đơn hàng đã hủy là item hợp lệ nhưng nằm ngoài phạm vi báo cáo. Processor trả về `null` là phù hợp. Đây là filter.

### Đơn hàng thiếu mã định danh

Nếu mã đơn hàng là bắt buộc, item thiếu mã là dữ liệu lỗi. Processor có thể ném `InvalidOrderException`. Nếu nghiệp vụ cho phép tiếp tục và lưu lại bản ghi lỗi, cấu hình skip là phù hợp.

### Dòng CSV sai định dạng

Nếu reader không thể parse một dòng nhưng có thể tiếp tục đọc các dòng sau, có thể cấu hình skip cho exception parse cụ thể. Đây là read skip. Nếu file hỏng cấu trúc nghiêm trọng hoặc reader không thể tiếp tục an toàn, nên để Step thất bại.

### Giao dịch gặp database timeout

Timeout có thể là lỗi tạm thời. Retry với giới hạn và backoff phù hợp thường đáng cân nhắc. Skip ngay có thể làm thiếu giao dịch. Nếu lỗi kéo dài, Step nên thất bại để hệ thống có thể restart hoặc điều tra.

### Bản ghi trùng khóa duy nhất

Đây có thể là dữ liệu trùng cần skip, hoặc là lỗi nghiêm trọng nếu nghiệp vụ yêu cầu mọi bản ghi phải duy nhất. Quyết định phụ thuộc quy tắc nghiệp vụ. Nếu skip, hãy lưu lại khóa và lý do để đối soát.

| Tình huống | Cách xử lý thường phù hợp | Lý do |
|---|---|---|
| Item hợp lệ nhưng không cần trong kết quả | Filter (`return null`) | Quyết định nghiệp vụ có chủ đích. |
| Item sai định dạng nhưng có thể bỏ qua | Skip | Exception đã biết và được cho phép. |
| Lỗi tạm thời có thể phục hồi | Retry | Có khả năng thành công ở lần thử sau. |
| Lỗi hệ thống hoặc dữ liệu không thể tiếp tục an toàn | Fail Step | Không nên che giấu lỗi nghiêm trọng. |
| Item bị loại cần audit như một quyết định nghiệp vụ | Filter + metric/audit riêng | Không phải skip event. |
| Item bị bỏ do exception và cần ghi báo cáo lỗi | Skip + SkipListener | Có exception và callback tương ứng. |

## 12. Tác động của transaction và rollback

Chunk processing thường xử lý mỗi chunk trong một transaction. Khi exception xảy ra, transaction có thể rollback trước khi framework xác định có thể retry hoặc skip item hay không. Vì vậy, một phần logic trong chunk có thể được gọi lại trong quá trình fault tolerance.

Điều này ảnh hưởng đến filter và skip:

- Filter không ném exception, nhưng processor vẫn có thể được gọi lại nếu chunk rollback do lỗi ở item khác.
- Skip bắt đầu từ exception và có thể cần rollback/replay chunk để xác định item lỗi hoặc tiếp tục an toàn.
- Writer có thể được gọi lại khi framework xử lý retry hoặc scan item lỗi.
- Các tác dụng phụ ngoài transaction không tự rollback cùng database.

Do đó, processor nên tập trung vào tính toán và tạo kết quả. Tránh gửi email, ghi file hoặc gọi API không idempotent trong processor. Nếu cần lưu dữ liệu lỗi, thiết kế cơ chế lưu phù hợp với transaction và vòng đời listener để không tạo bản ghi reject trùng khi retry.

## 13. Thiết kế báo cáo dữ liệu filter và skip

Một Job production thường cần giải thích số item đầu vào đã trở thành kết quả như thế nào. Có thể báo cáo riêng:

- Tổng số item đọc.
- Số item filter theo từng lý do nghiệp vụ.
- Số item skip theo giai đoạn đọc, xử lý hoặc ghi.
- Loại exception và thông tin định danh bản ghi lỗi.
- Số item writer ghi thành công.
- Số lần retry, rollback và trạng thái cuối cùng của Step.

`StepExecution` cung cấp các bộ đếm tổng hợp, nhưng không lưu đầy đủ lý do nghiệp vụ cho mọi item bị filter. Nếu cần thống kê theo lý do như `CANCELLED`, `OUT_OF_SCOPE` hoặc `DUPLICATE`, processor có thể gửi metric có nhãn hoặc cập nhật một báo cáo audit phù hợp.

Với skip, `SkipListener` có thể ghi lại exception và thông tin item. Cần cân nhắc transaction: bản ghi reject nên được lưu theo cách nhất quán với việc chunk commit, tránh trường hợp bản ghi lỗi đã được ghi vào bảng reject nhưng transaction chunk sau đó rollback và listener được gọi lại.

Không nên ghi toàn bộ payload nhạy cảm của item vào log. Chỉ lưu business key, loại lỗi, vị trí nguồn và thông tin cần thiết để sửa dữ liệu.

## 14. Những lỗi thường gặp

### Dùng return null cho mọi loại dữ liệu lỗi

Điều này biến lỗi dữ liệu thành filter, làm `filterCount` tăng và không kích hoạt `SkipListener`. Khi cần điều tra hoặc báo cáo bản ghi lỗi, hãy ném exception cụ thể và cấu hình skip nếu được phép.

### Dùng skip cho item chỉ đơn giản nằm ngoài phạm vi

Điều này làm tăng skip count và tạo cảm giác chất lượng dữ liệu kém dù item hoàn toàn hợp lệ. Hãy dùng filter cho quyết định loại bỏ nghiệp vụ.

### Cấu hình skip quá rộng

Skip `Exception.class` hoặc một lớp exception quá tổng quát có thể che giấu lỗi lập trình, mất kết nối, lỗi cấu hình hoặc lỗi transaction. Chỉ skip loại exception đã hiểu và có thể bỏ qua an toàn.

### Đặt skip limit quá cao hoặc vô hạn

Một Job có thể hoàn tất dù đã bỏ qua số lượng lớn bản ghi quan trọng. Chọn giới hạn theo yêu cầu nghiệp vụ và giám sát tỷ lệ lỗi, không chỉ tổng số.

### Cho rằng skip không cần ghi nhận

Skip có nghĩa bản ghi không được xử lý thành công theo pipeline chính. Cần cân nhắc `SkipListener`, bảng reject hoặc báo cáo lỗi để có thể sửa và đối soát.

### Cho rằng filter không ảnh hưởng kết quả báo cáo

Filter làm giảm số item writer nhận. Nếu không ghi nhận lý do filter, người dùng có thể không hiểu vì sao số item đầu vào khác số item đầu ra.

### Retry một lỗi dữ liệu cố định

Retry không sửa được một item thiếu trường bắt buộc hoặc sai định dạng. Hãy phân loại lỗi dữ liệu và lỗi tạm thời để chọn skip hoặc retry phù hợp.

## 15. Quy trình quyết định filter, skip hay fail

Khi xử lý một item không được ghi, hãy xác định nguyên nhân theo trình tự:

1. Item có hợp lệ và chỉ nằm ngoài phạm vi kết quả cần tạo không? Nếu có, filter bằng cách trả về `null`.
2. Có exception xảy ra trong reader, processor hoặc writer không? Nếu không, không gọi đó là skip.
3. Exception có phải lỗi của riêng item và nghiệp vụ cho phép bỏ qua không? Nếu có, cấu hình skip cho exception cụ thể.
4. Lỗi có khả năng tạm thời và thao tác có thể lặp an toàn không? Nếu có, cân nhắc retry với giới hạn.
5. Lỗi có làm dữ liệu hoặc trạng thái hệ thống không đáng tin cậy không? Nếu có, để Step thất bại và xử lý theo quy trình phục hồi.
6. Item bị filter hoặc skip có cần được audit, báo cáo hoặc sửa lại không? Nếu có, ghi nhận lý do và business key bằng cơ chế phù hợp.

| Kết quả mong muốn | Cơ chế |
|---|---|
| Loại item hợp lệ khỏi output | Processor trả về `null` (filter). |
| Bỏ qua lỗi item đã được cho phép | Cấu hình `.skip(...)` và `.skipLimit(...)`. |
| Ghi nhận item bị skip | Đăng ký `SkipListener`. |
| Thử lại lỗi tạm thời | Cấu hình `.retry(...)` và `.retryLimit(...)`. |
| Dừng khi lỗi không được phép bỏ qua | Không cấu hình skip cho exception đó hoặc dùng `.noSkip(...)`. |

## Kết luận

Filter là quyết định nghiệp vụ của `ItemProcessor`: trả về `null` để loại một item khỏi writer và tăng `filterCount`. Skip là cơ chế fault tolerance được kích hoạt bởi exception ở reader, processor hoặc writer; nó được kiểm soát bằng skip policy/skip limit, tăng các skip count và có thể được ghi nhận qua `SkipListener`. Hãy dùng filter cho item hợp lệ nhưng không cần trong kết quả, dùng skip cho lỗi item đã được cho phép bỏ qua, dùng retry cho lỗi tạm thời và để Step thất bại khi không thể tiếp tục an toàn.
