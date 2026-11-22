# Chunk rỗng và kết thúc input trong Spring Batch

Trong chunk-oriented processing, Spring Batch đọc dữ liệu theo từng nhóm item, xử lý nhóm đó rồi ghi kết quả trong ranh giới transaction. Một job không phải lúc nào cũng nhận đủ số item như cấu hình. Nguồn có thể không có dữ liệu ngay từ đầu, chỉ còn một phần nhỏ ở chunk cuối, hoặc processor có thể loại bỏ toàn bộ item trong một chunk.

Những trường hợp này cần được phân biệt rõ. **Kết thúc input** là tín hiệu từ `ItemReader` cho biết không còn item nào để đọc. **Chunk cuối nhỏ hơn commit interval** là chunk hợp lệ. **Chunk đầu vào không có item** có thể xảy ra khi nguồn rỗng. Còn **chunk đầu ra rỗng** có thể xuất hiện khi processor lọc bỏ tất cả item đã đọc. Các trường hợp này có ảnh hưởng khác nhau đến bộ đếm, writer, trạng thái step và khả năng restart.

## 1. Chunk và commit interval

Một chunk là nhóm item được đọc, xử lý và ghi trong một transaction. Khi cấu hình:

```java
new StepBuilder("importOrdersStep", jobRepository)
    .<Order, Order>chunk(100, transactionManager)
    .reader(orderReader)
    .processor(orderProcessor)
    .writer(orderWriter)
    .build();
```

`100` là commit interval: step cố gắng gom tối đa 100 item đầu vào cho một lần xử lý chunk trước khi commit. Đây không phải cam kết rằng nguồn phải có đúng 100 item, cũng không phải kích thước tối thiểu của chunk.

Nếu nguồn còn 37 item rồi kết thúc, Spring Batch vẫn xử lý 37 item đó trong chunk cuối và commit theo transaction boundary của chunk. Nếu nguồn không có item nào, step không cần chờ đủ 100 item; reader báo hết dữ liệu và step có thể hoàn tất bình thường.

Một chu kỳ xử lý điển hình có thể hình dung như sau:

```text
ItemReader
    |
    v
Đọc tối đa commit interval item
    |
    v
ItemProcessor cho từng item
    |
    v
ItemWriter ghi các output còn lại
    |
    v
Commit transaction
    |
    v
Đọc chunk tiếp theo
```

Ở chunk cuối, reader có thể phát hiện EOF trước khi gom đủ số lượng cấu hình. Những item đã đọc trước tín hiệu EOF vẫn được xử lý. Tín hiệu kết thúc không làm mất phần chunk hợp lệ đã được đọc.

## 2. ItemReader báo kết thúc input bằng null

Hợp đồng của `ItemReader<T>.read()` là trả về một item tiếp theo hoặc trả về `null` khi không còn item nào. Spring Batch dùng `null` như tín hiệu kết thúc nguồn dữ liệu (end of input/end of file, thường viết tắt là EOF).

Ví dụ một reader đơn giản đọc từ iterator:

```java
public class OrderReader implements ItemReader<Order> {

    private final Iterator<Order> iterator;

    public OrderReader(List<Order> orders) {
        this.iterator = orders.iterator();
    }

    @Override
    public Order read() {
        if (!iterator.hasNext()) {
            return null;
        }
        return iterator.next();
    }
}
```

Khi `read()` trả về `null`, Spring Batch hiểu rằng reader đã hết dữ liệu. Step sẽ kết thúc phần đọc và chuyển sang hoàn tất những công việc còn lại của chunk cuối, nếu có. `null` không phải một item để chuyển cho processor hoặc writer.

Trong một job thực tế, các reader như `FlatFileItemReader`, `JdbcCursorItemReader` hoặc reader tùy chỉnh đều tuân theo ý nghĩa này: trả về item khi còn dữ liệu và trả về `null` khi nguồn đã kết thúc. Chi tiết phát hiện EOF phụ thuộc loại reader và nguồn dữ liệu.

Không dùng `null` để biểu diễn một bản ghi nghiệp vụ hợp lệ. Nếu dữ liệu nguồn có khái niệm giá trị rỗng, hãy biểu diễn nó bằng một object không null, ví dụ một DTO có trường rỗng, chuỗi rỗng hoặc một kiểu wrapper phù hợp. Trong hợp đồng `ItemReader`, `null` dành cho tín hiệu hết dữ liệu.

## 3. Phân biệt EOF với item có giá trị rỗng

Một item rỗng về mặt nghiệp vụ không nhất thiết là EOF. Ví dụ, nếu reader trả về chuỗi rỗng `""`, một object có các trường trống hoặc một collection rỗng, Spring Batch vẫn xem đó là một item vì giá trị trả về khác `null`.

| Giá trị từ `ItemReader.read()` | Cách Spring Batch hiểu |
| --- | --- |
| Một object hợp lệ | Có item mới; chuyển item sang processor nếu được cấu hình. |
| Chuỗi rỗng `""` | Một item kiểu `String` có giá trị rỗng. |
| Collection rỗng | Một item là collection rỗng, nếu kiểu item của reader là collection. |
| `null` | Không còn item; reader đã kết thúc input. |
| Ném exception | Có lỗi khi đọc; xử lý theo cấu hình retry/skip hoặc làm step thất bại. |

Sự khác biệt này rất quan trọng với file CSV. Một dòng trống trong file có thể được reader ánh xạ thành chuỗi rỗng hoặc được xử lý theo cấu hình tokenizer/line mapper. Dòng trống không tự động có nghĩa toàn bộ file đã kết thúc. Chỉ khi reader không còn dòng nào để đọc và trả về `null`, Spring Batch mới nhận tín hiệu EOF.

Nếu reader tùy chỉnh trả về `null` do lỗi phân tích một dòng, step có thể kết thúc sớm mà không báo lỗi. Vì vậy, hãy phân biệt rõ dữ liệu kết thúc bình thường với dữ liệu hỏng. Lỗi parse nên được thể hiện bằng exception phù hợp để chính sách skip, retry hoặc fail có thể xử lý.

## 4. Chunk cuối nhỏ hơn commit interval

Giả sử commit interval là 100 nhưng nguồn có 237 item. Quá trình đọc và commit sẽ có dạng:

```text
Chunk 1: item 1..100       -> 100 item -> commit
Chunk 2: item 101..200     -> 100 item -> commit
Chunk 3: item 201..237     ->  37 item -> commit
Reader đọc tiếp            -> null (EOF)
Step hoàn tất
```

Chunk cuối có 37 item vẫn là một chunk bình thường. Spring Batch không yêu cầu số lượng item của chunk cuối phải bằng commit interval. Reader phát hiện EOF, nhưng các item đã đọc trong chunk cuối vẫn được đưa qua processor và writer theo cấu hình của step.

Nếu tổng số item chia hết cho commit interval, ví dụ 200 item với interval 100, hai chunk đầy đủ được xử lý. Ở lần đọc tiếp theo, reader trả về `null`; không có thêm item để tạo một chunk nghiệp vụ mới. Step kết thúc sau khi hoàn tất các transaction cần thiết.

Không nên tự thêm một item giả để làm đầy chunk cuối. Việc đó có thể khiến writer ghi dữ liệu không có thật hoặc làm sai các bộ đếm. Kích thước chunk là giới hạn nhóm xử lý, không phải số lượng bản ghi mà nguồn phải cung cấp.

## 5. Input rỗng ngay từ đầu

Nếu nguồn không có item nào, lời gọi `read()` đầu tiên trả về `null`. Step vẫn có thể chạy và hoàn tất bình thường:

```text
Start step
    |
    v
ItemReader.read()
    |
    +---- trả về null
              |
              v
          Không có item
              |
              v
         Step COMPLETED
```

Với một chunk step tiêu chuẩn, trường hợp này thường có các đặc điểm:

- `BatchStatus` của step là `COMPLETED` nếu không có lỗi khác.
- `readCount` bằng 0 vì không có item nào được đọc.
- `writeCount` bằng 0 vì không có item nào được ghi.
- Processor không được gọi vì không có input item.
- Writer không có output để ghi và không được gọi cho một chunk dữ liệu rỗng theo xử lý chunk mặc định.

Job tiếp tục theo flow đã cấu hình. Nếu step này là step cuối cùng, job có thể kết thúc với `BatchStatus.COMPLETED`. Vì vậy, **không có dữ liệu không mặc nhiên là lỗi kỹ thuật**. Việc input rỗng có phải kết quả nghiệp vụ hợp lệ hay không phụ thuộc yêu cầu của ứng dụng.

Ví dụ, job tổng hợp doanh thu theo ngày có thể chấp nhận ngày không có giao dịch. Nhưng job đối soát bắt buộc phải có file đầu vào có thể cần coi file rỗng là lỗi nghiệp vụ. Hãy thể hiện quy tắc đó một cách rõ ràng thay vì dựa vào giả định rằng Spring Batch sẽ tự xem input rỗng là thất bại.

## 6. Phân biệt chunk đầu vào rỗng và chunk đầu ra rỗng

Một chunk có thể có item đầu vào nhưng không còn item đầu ra sau khi xử lý. Trường hợp phổ biến là `ItemProcessor` trả về `null` để loại bỏ một item.

Hợp đồng của processor cho phép trả về `null` khi item không cần được ghi. Điều này được gọi là filtering. Nó khác với `ItemReader` trả về `null` để báo EOF.

```java
public class ActiveOrderProcessor implements ItemProcessor<Order, Order> {

    @Override
    public Order process(Order order) {
        if (!order.isActive()) {
            return null; // lọc item này khỏi output
        }
        return order;
    }
}
```

Giả sử reader đọc 10 đơn hàng nhưng processor lọc cả 10. Input chunk có 10 item, output chunk không có item nào. Đây không phải kết thúc input: reader vẫn có thể tiếp tục đọc các chunk tiếp theo.

Với chunk processing mặc định, khi output chunk rỗng, writer không được gọi vì không có item để ghi. Transaction và quá trình hoàn tất chunk vẫn được framework quản lý. Step tiếp tục đọc cho đến khi reader trả về `null` hoặc xảy ra lỗi.

Sự khác biệt thể hiện rõ qua bộ đếm:

| Tình huống | `readCount` | `filterCount` | `writeCount` |
| --- | ---: | ---: | ---: |
| Input rỗng ngay từ đầu | 0 | 0 | 0 |
| Đọc 10 item, lọc cả 10 | 10 | 10 | 0 |
| Đọc 10 item, lọc 3 và ghi 7 | 10 | 3 | 7 |

Do đó, nếu chỉ nhìn `writeCount = 0`, chưa thể kết luận nguồn rỗng. Cần xem cả `readCount` và `filterCount` để biết step không có input hay đã đọc nhưng lọc hết dữ liệu.

## 7. Phân biệt filtering với skip

Filtering và skip đều có thể khiến một item không xuất hiện trong output, nhưng nguyên nhân và bộ đếm khác nhau.

- **Filtering:** processor chủ động trả về `null` vì item không cần ghi. Đây thường là quyết định nghiệp vụ bình thường và được tính vào `filterCount`.
- **Skip:** một exception xảy ra trong quá trình đọc, xử lý hoặc ghi, và chính sách skip cho phép bỏ qua item lỗi. Các bộ đếm tương ứng có thể là `readSkipCount`, `processSkipCount` hoặc `writeSkipCount`.
- **EOF:** reader trả về `null` vì không còn item. Đây là tín hiệu kết thúc nguồn, không phải filter hay skip.

Ví dụ, một đơn hàng không hoạt động có thể được filter; một dòng CSV sai định dạng có thể phát sinh parse exception và được skip nếu cấu hình cho phép; sau dòng cuối cùng, reader trả về `null` để kết thúc.

Không nên dùng filtering để che giấu dữ liệu không hợp lệ. Nếu một item bị loại do lỗi dữ liệu và cần được thống kê hoặc điều tra, hãy dùng exception cùng skip policy hoặc một cơ chế ghi nhận lỗi nghiệp vụ riêng.

## 8. Điều gì xảy ra khi nguồn kết thúc giữa lúc đọc chunk?

Trong một chunk, reader được gọi nhiều lần cho đến khi đạt commit interval hoặc phát hiện EOF. Nếu EOF xuất hiện sau khi đã đọc một số item, chunk hiện tại vẫn chứa các item đã đọc được. Spring Batch chuyển những item đó qua processor và writer rồi commit theo transaction của chunk.

Ví dụ với interval 5 và nguồn có 7 item:

```text
Lượt đọc 1..5  -> chunk đủ 5 item -> process -> write -> commit
Lượt đọc 6..7  -> reader tiếp tục đọc
Lượt đọc tiếp  -> null (EOF)
                  |
                  v
              chunk cuối có 2 item
                  |
                  v
              process -> write -> commit
                  |
                  v
              step hoàn tất
```

EOF không hủy chunk đang có item. Điều này giúp xử lý đúng các nguồn có số lượng item không chia hết cho commit interval.

Nếu processor filter một số item trong chunk cuối, writer chỉ nhận các output còn lại. Nếu tất cả item bị filter, writer không có dữ liệu để ghi, nhưng step vẫn cần hoàn tất việc xử lý chunk và lưu trạng thái cần thiết.

## 9. Kết thúc input trong reader dạng file, database và stream

### File reader

Với file reader, EOF thường xảy ra khi reader đã đọc hết các dòng hoặc bản ghi. File rỗng sẽ khiến lần đọc đầu tiên trả về `null`. File có 237 dòng dữ liệu với commit interval 100 tạo hai chunk đủ và một chunk cuối nhỏ hơn.

Cần phân biệt file rỗng với file chỉ có header. Tùy reader và cấu hình mapping, header có thể được bỏ qua và kết quả vẫn là không có item nghiệp vụ. Nếu nghiệp vụ cần phân biệt hai trường hợp này, hãy kiểm tra metadata file hoặc thêm bước validation riêng.

### Database reader

Với cursor reader, khi result set không còn hàng tiếp theo, reader trả về `null`. Với paging reader, khi không còn trang hoặc hàng tiếp theo, reader cũng báo kết thúc theo hợp đồng của nó. Một truy vấn trả về 0 hàng vì điều kiện lọc không khớp thường là input rỗng hợp lệ ở cấp framework.

Nếu dữ liệu có thể thay đổi trong lúc job chạy, hãy xác định snapshot hoặc isolation semantics mà reader sử dụng. Một nguồn dữ liệu thay đổi liên tục có thể khiến tập item được đọc khác với dự kiến; đó là vấn đề về tính nhất quán của nguồn và truy vấn, không phải ý nghĩa của chunk rỗng.

### Message queue hoặc nguồn streaming

Với nguồn dữ liệu có thể tạm thời chưa có message mới, không được trả về `null` chỉ vì queue đang rỗng tại thời điểm kiểm tra nếu job vẫn phải tiếp tục chờ message. Theo hợp đồng `ItemReader`, `null` có nghĩa không còn item và step có thể kết thúc.

Nếu cần chờ dữ liệu mới, reader phải có chính sách chờ/polling phù hợp, timeout, hoặc một mô hình điều phối khác. Chỉ trả về `null` khi thực sự muốn báo kết thúc input của lần chạy hiện tại. Với queue có thể nhận message liên tục, cần xác định rõ điều kiện kết thúc, chẳng hạn giới hạn số message, marker kết thúc hoặc cửa sổ thời gian.

## 10. Kết thúc input và restart

Với reader có hỗ trợ restart, Spring Batch có thể lưu trạng thái đọc trong `ExecutionContext` tại ranh giới commit. Khi job thất bại giữa chừng, lần restart có thể khôi phục reader từ checkpoint cuối cùng đã lưu.

`ItemStream` định nghĩa các callback vòng đời quan trọng:

- `open(ExecutionContext)` khôi phục hoặc khởi tạo trạng thái reader.
- `update(ExecutionContext)` ghi trạng thái hiện tại vào execution context để checkpoint.
- `close()` giải phóng tài nguyên sau khi step kết thúc.

Nhiều reader có sẵn triển khai `ItemStream`. Reader tùy chỉnh cần triển khai và lưu trạng thái phù hợp nếu muốn hỗ trợ restart. Ví dụ, reader file có thể lưu vị trí dòng hoặc vị trí byte; reader phân trang có thể lưu khóa cuối cùng đã đọc.

Nếu job kết thúc bình thường do EOF, step có trạng thái hoàn tất. Một `JobInstance` đã `COMPLETED` thường không thể được khởi chạy lại như một lần restart. Nếu cần nhập lại cùng file hoặc chạy lại cùng đơn vị nghiệp vụ, hãy xác định rõ cơ chế tạo instance mới bằng identifying parameters phù hợp hoặc dùng quy trình reprocess riêng.

Không nên lưu một cờ EOF tự chế trong bộ nhớ rồi kỳ vọng nó được khôi phục sau restart. Trạng thái cần thiết phải được ghi trong `ExecutionContext` hoặc được suy ra ổn định từ nguồn dữ liệu. Cũng cần lưu ý rằng checkpoint chỉ bảo vệ tiến độ đọc; nó không tự bảo đảm side effect bên ngoài không bị lặp khi transaction nghiệp vụ và metadata không cùng một ranh giới commit.

## 11. Biểu diễn nghiệp vụ khi không có dữ liệu

Theo mặc định, step không có input vẫn có thể hoàn tất với `BatchStatus.COMPLETED`. Nếu nghiệp vụ cần phân biệt `NO_DATA` với `COMPLETED` thông thường, có thể gán một `ExitStatus` tùy chỉnh dựa trên `readCount`.

Ví dụ listener:

```java
public class NoDataExitStatusListener implements StepExecutionListener {

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        if (stepExecution.getReadCount() == 0) {
            return new ExitStatus("NO_DATA");
        }
        return null;
    }
}
```

Listener này đặt exit code `NO_DATA` khi step không đọc được item nào. Trả về `null` trong trường hợp còn dữ liệu để giữ `ExitStatus` đã có. Có thể dùng mã đó trong flow của job:

```java
@Bean
Job importJob(JobRepository jobRepository,
              Step importStep,
              Step noDataStep,
              Step reportStep) {
    return new JobBuilder("importJob", jobRepository)
        .start(importStep)
            .on("NO_DATA").to(noDataStep)
        .from(importStep)
            .on("COMPLETED").to(reportStep)
        .from(noDataStep)
            .on("*").end()
        .from(reportStep)
            .on("*").end()
        .end()
        .build();
}
```

Trong ví dụ này, `BatchStatus` của step có thể vẫn là `COMPLETED`, còn `ExitStatus` là `NO_DATA`. Flow đối chiếu exit code để chọn nhánh. Nếu không cần một nhánh riêng, có thể chỉ ghi log hoặc metric khi `readCount` bằng 0.

Nếu processor lọc hết item, `readCount` lớn hơn 0 và `filterCount` phản ánh số item bị loại. Listener trên không coi trường hợp đó là input rỗng. Nếu nghiệp vụ muốn coi “không có output” là `NO_DATA`, hãy dùng điều kiện khác, ví dụ kết hợp `writeCount == 0` và các bộ đếm liên quan, đồng thời xác định rõ ý nghĩa của filtering.

## 12. Theo dõi bộ đếm để nhận biết input rỗng

`StepExecution` cung cấp các bộ đếm hữu ích khi điều tra chunk:

| Bộ đếm | Ý nghĩa |
| --- | --- |
| `readCount` | Số item đọc thành công từ reader. |
| `writeCount` | Số item được ghi thành công. |
| `filterCount` | Số item được processor lọc bằng cách trả về `null`. |
| `readSkipCount` | Số item bị bỏ qua do lỗi trong quá trình đọc theo skip policy. |
| `processSkipCount` | Số item bị bỏ qua do lỗi trong quá trình xử lý. |
| `writeSkipCount` | Số item bị bỏ qua do lỗi trong quá trình ghi. |
| `commitCount` | Số lần transaction chunk được commit. |
| `rollbackCount` | Số lần rollback được ghi nhận cho step. |

Một số cách đọc nhanh:

- `readCount = 0`, `writeCount = 0`: có thể nguồn rỗng hoặc reader không cung cấp item; kiểm tra log và metadata nguồn.
- `readCount > 0`, `filterCount = readCount`, `writeCount = 0`: tất cả item đã được processor lọc.
- `readCount > 0`, `writeCount = 0`, có skip count: item có thể đã bị bỏ qua do lỗi theo skip policy.
- `readCount > writeCount`: có thể do filter, skip hoặc các quy tắc xử lý khác; không tự kết luận dữ liệu bị mất.

Các bộ đếm phản ánh hoạt động của step theo quy tắc framework. Khi cần xác minh dữ liệu nghiệp vụ thực sự được lưu, hãy đối chiếu với hệ thống đích, đặc biệt khi writer gọi API hoặc database khác transaction manager.

## 13. Kiểm thử các trường hợp chunk rỗng và EOF

Nên có test riêng cho nguồn rỗng, nguồn có ít item hơn commit interval, số item chia hết cho commit interval và trường hợp processor lọc toàn bộ item. Những test này giúp xác nhận reader trả về `null` đúng lúc, chunk cuối không bị mất và bộ đếm phản ánh đúng hoạt động.

Ví dụ với một job test dùng `ListItemReader`:

```java
ItemReader<Order> emptyReader = new ListItemReader<>(List.of());
ItemReader<Order> shortReader = new ListItemReader<>(List.of(
    new Order("A-1"),
    new Order("A-2")
));
```

Với commit interval 10, `emptyReader` không cung cấp item nào; `shortReader` cung cấp một chunk cuối gồm 2 item. Có thể khởi chạy step/job và kiểm tra `StepExecution`:

```java
assertThat(stepExecution.getReadCount()).isEqualTo(0);
assertThat(stepExecution.getWriteCount()).isEqualTo(0);
assertThat(stepExecution.getStatus()).isEqualTo(BatchStatus.COMPLETED);
```

Đoạn assertion trên dành cho trường hợp input rỗng. Với reader có 2 item và writer ghi cả hai, kỳ vọng `readCount` và `writeCount` là 2. Nếu processor lọc cả hai, kỳ vọng `readCount` là 2, `filterCount` là 2 và `writeCount` là 0.

Ngoài bộ đếm, có thể dùng một writer test đếm số lần được gọi để xác nhận writer không được gọi khi output chunk rỗng theo xử lý mặc định. Không nên chỉ kiểm tra trạng thái `COMPLETED`, vì cả input rỗng và input có dữ liệu đều có thể hoàn tất thành công.

Khi kiểm thử EOF và restart, cần dùng reader có trạng thái restartable nếu mục tiêu là xác nhận checkpoint. Một reader chỉ giữ iterator trong bộ nhớ phù hợp cho test đơn giản nhưng không chứng minh được trạng thái đọc có thể phục hồi sau khi application context hoặc process bị tạo lại.

## 14. Lỗi thường gặp khi xử lý chunk rỗng và EOF

**Trả về null cho dữ liệu tạm thời chưa có:** framework hiểu `null` là kết thúc input và hoàn tất step. Với nguồn có thể phát sinh thêm dữ liệu, hãy dùng cơ chế chờ hoặc polling thay vì báo EOF quá sớm.

**Nhầm chuỗi rỗng với EOF:** `""` là một item khác null. Nếu chuỗi rỗng biểu thị dòng không hợp lệ, hãy validate hoặc filter theo nghiệp vụ.

**Coi chunk cuối nhỏ là lỗi:** chunk cuối có ít item hơn commit interval là hành vi bình thường. Không cần bổ sung item giả hoặc thay đổi commit interval chỉ để làm đầy chunk.

**Nhầm processor trả null với reader hết dữ liệu:** processor trả null chỉ loại item hiện tại khỏi output. Reader vẫn tiếp tục đọc những item sau.

**Cho rằng writer luôn được gọi:** nếu output chunk rỗng, writer mặc định không có item để ghi và thường không được gọi. Đừng đặt logic bắt buộc như cập nhật trạng thái “đã xử lý” chỉ trong writer nếu logic đó phải chạy cả khi không có output.

**Cho rằng input rỗng là job thất bại:** framework có thể đánh dấu step và job `COMPLETED` khi không có dữ liệu. Nếu nghiệp vụ yêu cầu trạng thái riêng, hãy dùng exit code tùy chỉnh hoặc bước validation.

**Bỏ qua khác biệt giữa filter và skip:** hai trường hợp có bộ đếm và ý nghĩa khác nhau. Dùng đúng cơ chế để giám sát chất lượng dữ liệu.

**Reader báo EOF sớm do lỗi:** một lỗi parse hoặc lỗi kết nối bị chuyển nhầm thành `null` có thể khiến step hoàn tất với dữ liệu thiếu. Hãy ném exception phù hợp khi không thể xác định rằng nguồn thực sự đã kết thúc.

## 15. Cách thiết kế xử lý input kết thúc

Khi thiết kế chunk step, hãy xác định rõ hợp đồng của nguồn dữ liệu: giá trị nào là item, khi nào nguồn thực sự kết thúc và có thể tạm thời không có dữ liệu hay không. Reader phải trả về `null` đúng lúc EOF và không dùng nó cho trạng thái lỗi hoặc chờ dữ liệu.

Tiếp theo, quyết định nghiệp vụ cho input rỗng. Nếu không có dữ liệu là bình thường, để step hoàn tất và ghi nhận metric phù hợp. Nếu cần nhánh xử lý riêng, dùng `ExitStatus` tùy chỉnh như `NO_DATA`. Nếu dữ liệu không được phép rỗng, hãy validate và làm step thất bại theo cách có thể quan sát được.

Cuối cùng, theo dõi `readCount`, `writeCount`, `filterCount` và skip count để phân biệt nguồn rỗng với dữ liệu đã bị lọc hoặc bỏ qua. Với reader có restart, lưu checkpoint qua `ExecutionContext` và xác nhận writer có thể xử lý an toàn khi chunk được thực hiện lại.

Khi hiểu đúng ý nghĩa của `null`, chunk cuối và output rỗng, ứng dụng Spring Batch có thể kết thúc input một cách tự nhiên, xử lý chính xác nguồn có kích thước bất kỳ và biểu diễn rõ ràng sự khác biệt giữa không có dữ liệu, lọc dữ liệu và lỗi khi đọc.
