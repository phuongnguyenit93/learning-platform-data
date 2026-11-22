# RepeatStatus.FINISHED và CONTINUABLE

Trong Spring Batch, `Tasklet` thực hiện một đơn vị công việc bên trong một step và trả về `RepeatStatus` để cho biết tasklet đã hoàn tất hay cần được gọi lại. Hai giá trị thường dùng là `RepeatStatus.FINISHED` và `RepeatStatus.CONTINUABLE`.

`FINISHED` yêu cầu kết thúc vòng lặp thực thi tasklet của step hiện tại. `CONTINUABLE` yêu cầu Spring Batch gọi lại `Tasklet.execute()` trong cùng `StepExecution`. Vì vậy, `RepeatStatus` điều khiển việc lặp bên trong một tasklet step; nó không trực tiếp chọn step tiếp theo trong job flow.

## 1. RepeatStatus là gì?

`RepeatStatus` là kết quả của một lần gọi `Tasklet.execute`. Tasklet có thể thực hiện một phần công việc rồi trả về trạng thái để Spring Batch quyết định có tiếp tục gọi tasklet hay dừng vòng lặp.

| Giá trị | Ý nghĩa | Hành vi tiếp theo |
|---|---|---|
| `RepeatStatus.FINISHED` | Lần thực thi tasklet đã hoàn tất | Spring Batch dừng vòng lặp của tasklet step |
| `RepeatStatus.CONTINUABLE` | Còn công việc cần thực hiện | Spring Batch gọi lại `Tasklet.execute()` trong cùng step |

Ví dụ đơn giản:

```java
public class CleanupTasklet implements Tasklet {

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {

        cleanupService.removeExpiredRecords();
        return RepeatStatus.FINISHED;
    }
}
```

Tasklet trên chỉ cần thực hiện thao tác dọn dẹp một lần, vì vậy trả về `FINISHED`. Khi phương thức trả về, tasklet step kết thúc bình thường nếu không có lỗi nào khác.

## 2. FINISHED dừng vòng lặp tasklet

Khi tasklet trả về `RepeatStatus.FINISHED`, Spring Batch hiểu rằng tasklet không cần được gọi lại trong step execution hiện tại.

```text
TaskletStep bắt đầu
       |
       v
Tasklet.execute()
       |
       v
Trả về FINISHED
       |
       v
Không gọi execute() lần nữa
       |
       v
Step tiếp tục hoàn tất
```

`FINISHED` không có nghĩa toàn bộ JobExecution đã hoàn tất ngay tại thời điểm trả về. Nó chỉ kết thúc vòng lặp của tasklet step. Sau đó Spring Batch vẫn thực hiện các bước hoàn tất step, cập nhật trạng thái và tiếp tục job flow nếu job còn step khác.

Ví dụ job có ba step:

```text
validateInput -> processFile (Tasklet trả FINISHED) -> archiveFile
```

Sau khi `processFile` trả về `FINISHED`, Spring Batch có thể chuyển sang `archiveFile` theo flow đã khai báo. Nếu `processFile` là step cuối cùng và hoàn tất thành công, job có thể kết thúc với trạng thái `COMPLETED`.

## 3. CONTINUABLE yêu cầu gọi lại Tasklet.execute

Khi tasklet trả về `RepeatStatus.CONTINUABLE`, Spring Batch tiếp tục vòng lặp và gọi lại chính tasklet đó. Các lần gọi này thuộc cùng một `StepExecution`; framework không tạo step mới cho mỗi lần lặp.

```text
TaskletStep bắt đầu
       |
       v
Tasklet.execute() lần 1
       |
       +-- CONTINUABLE
       |
       v
Tasklet.execute() lần 2
       |
       +-- CONTINUABLE
       |
       v
Tasklet.execute() lần 3
       |
       +-- FINISHED
       |
       v
TaskletStep kết thúc vòng lặp
```

`CONTINUABLE` phù hợp khi mỗi lần gọi tasklet xử lý một phần hữu hạn của công việc, chẳng hạn một trang dữ liệu, một nhóm tệp hoặc một lô bản ghi. Tasklet cần có cách xác định phần tiếp theo và điều kiện dừng rõ ràng.

## 4. Ví dụ xử lý dữ liệu theo từng trang

Giả sử một tasklet cần xử lý một bảng dữ liệu lớn. Thay vì tải toàn bộ dữ liệu vào bộ nhớ, mỗi lần `execute()` xử lý một trang. Vị trí trang tiếp theo được lưu trong `ExecutionContext` để có thể tiếp tục sau restart.

```java
public class ProcessPagesTasklet implements Tasklet {

    private static final int PAGE_SIZE = 500;

    private final PageService pageService;

    public ProcessPagesTasklet(PageService pageService) {
        this.pageService = pageService;
    }

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {

        ExecutionContext context =
            contribution.getStepExecution().getExecutionContext();

        int page = context.getInt("nextPage", 0);
        List<Record> records = pageService.loadPage(page, PAGE_SIZE);

        if (records.isEmpty()) {
            return RepeatStatus.FINISHED;
        }

        pageService.process(records);
        context.putInt("nextPage", page + 1);

        return RepeatStatus.CONTINUABLE;
    }
}
```

Mỗi lần gọi, tasklet đọc số trang từ `ExecutionContext`, tải trang đó và xử lý. Nếu không còn dữ liệu, tasklet trả về `FINISHED`. Nếu đã xử lý một trang, nó lưu số trang tiếp theo rồi trả về `CONTINUABLE` để được gọi lại.

Trong ví dụ này, khi trang cuối cùng có dữ liệu, tasklet vẫn trả về `CONTINUABLE`; lần gọi tiếp theo đọc trang rỗng và trả về `FINISHED`. Có thể tối ưu để trả về `FINISHED` ngay sau khi xử lý một trang ngắn hơn `PAGE_SIZE`, nếu hợp đồng của `loadPage` bảo đảm trang ngắn là trang cuối.

### Khai báo TaskletStep

```java
@Bean
Step processPagesStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ProcessPagesTasklet processPagesTasklet) {

    return new StepBuilder("processPages", jobRepository)
        .tasklet(processPagesTasklet, transactionManager)
        .build();
}
```

`RepeatStatus` được trả về từ `execute()`, còn `StepBuilder.tasklet(...)` khai báo tasklet và transaction manager cho step. Mỗi lần gọi tasklet không tạo một `StepExecution` mới.

## 5. Transaction boundary giữa các lần lặp

Trong `TaskletStep`, mỗi lần gọi `Tasklet.execute()` được thực hiện trong transaction của step. Khi tasklet trả về `CONTINUABLE`, lần gọi hiện tại kết thúc và Spring Batch tiếp tục lần lặp kế tiếp theo cơ chế repeat của step.

Điều này có nghĩa tasklet có thể xử lý một đơn vị công việc trong mỗi transaction thay vì giữ một transaction lớn cho toàn bộ vòng lặp.

```text
Tasklet.execute() lần 1
    xử lý phần A
    cập nhật ExecutionContext
    commit transaction 1
             |
             v
Tasklet.execute() lần 2
    xử lý phần B
    cập nhật ExecutionContext
    commit transaction 2
             |
             v
Tasklet.execute() lần 3
    trả về FINISHED
    commit transaction 3
```

Việc lưu dữ liệu nghiệp vụ và checkpoint có thể cùng được commit nếu chúng dùng chung transaction resource và transaction manager phù hợp. Nếu tasklet ghi dữ liệu sang một database khác hoặc gọi API bên ngoài, transaction của step không tự động rollback side effect đó. Hãy dùng idempotency key, outbox hoặc cơ chế đối soát để xử lý retry/restart an toàn.

Không nên thực hiện một thao tác kéo dài hoặc chờ vô hạn bên trong `execute()`, vì transaction của lần gọi đó có thể bị giữ mở trong suốt thời gian chờ. Nếu cần chờ dịch vụ ngoài, hãy dùng timeout hữu hạn, giới hạn số lần polling và backoff phù hợp.

## 6. Lưu trạng thái giữa các lần gọi

Khi trả về `CONTINUABLE`, tasklet thường cần biết lần sau phải tiếp tục từ đâu. `ExecutionContext` của `StepExecution` là nơi phù hợp để lưu checkpoint hoặc trạng thái nhỏ cần thiết cho việc tiếp tục.

Ví dụ các giá trị có thể lưu:

- Số trang hoặc offset tiếp theo.
- Khóa bản ghi cuối cùng đã xử lý.
- Tên tệp tiếp theo trong danh sách công việc.
- Mã lô hiện tại hoặc giai đoạn xử lý.

`TaskletStep` phối hợp cập nhật metadata và `ExecutionContext` trong vòng đời thực thi. Tuy nhiên, chỉ lưu checkpoint sau khi phần công việc tương ứng được xử lý thành công. Nếu lưu vị trí tiếp theo trước khi dữ liệu nghiệp vụ commit, job có thể bỏ sót dữ liệu khi có lỗi.

Với dữ liệu lớn hoặc nguồn thay đổi liên tục, nên dùng keyset pagination hoặc một cursor ổn định thay vì offset nếu việc thêm/xóa bản ghi có thể làm thay đổi vị trí trang. Hãy xác định thứ tự đọc ổn định và khóa duy nhất để tránh bỏ sót hoặc xử lý trùng.

### Ví dụ lưu khóa cuối cùng đã xử lý

```java
String lastId = context.getString("lastProcessedId", "");
List<Record> records = pageService.loadAfter(lastId, PAGE_SIZE);

if (records.isEmpty()) {
    return RepeatStatus.FINISHED;
}

pageService.process(records);
context.putString("lastProcessedId", records.get(records.size() - 1).id());
return RepeatStatus.CONTINUABLE;
```

Ví dụ này giả định `id` có thứ tự ổn định và `loadAfter` trả về các bản ghi có ID lớn hơn khóa cuối cùng. Với dữ liệu thực tế, cần bảo đảm khóa sắp xếp không đổi và không có hai bản ghi dùng cùng khóa định vị.

## 7. CONTINUABLE không phải chuyển sang step khác

`RepeatStatus` thường bị nhầm với `ExitStatus` hoặc `BatchStatus`, nhưng chúng phục vụ các mục đích khác nhau.

| Trạng thái | Phạm vi | Câu hỏi được trả lời |
|---|---|---|
| `RepeatStatus` | Một lần gọi tasklet và vòng lặp tasklet step | Có gọi lại `Tasklet.execute()` không? |
| `ExitStatus` | Kết quả của step, dùng trong job flow | Step kết thúc với mã kết quả nào? |
| `BatchStatus` | Trạng thái vòng đời execution | Execution đang chạy, hoàn thành, thất bại hay dừng? |

Ví dụ:

- `RepeatStatus.CONTINUABLE`: gọi lại cùng tasklet trong cùng step.
- `RepeatStatus.FINISHED`: dừng lặp tasklet; step tiếp tục hoàn tất.
- `ExitStatus` như `COMPLETED`, `FAILED` hoặc mã tùy chỉnh: được dùng để quyết định transition sang step khác hoặc kết thúc job.
- `BatchStatus` như `COMPLETED`, `FAILED`, `STOPPED`: phản ánh trạng thái thực thi của step/job.

Nếu cần chuyển sang step khác dựa trên kết quả nghiệp vụ, hãy dùng job flow và transition theo `ExitStatus`, hoặc `JobExecutionDecider`. Trả về `CONTINUABLE` không làm Spring Batch nhảy sang step tiếp theo.

## 8. RepeatStatus trong Tasklet và chunk-oriented step

`RepeatStatus` thuộc hợp đồng trả về của `Tasklet.execute()`. Chunk-oriented step dùng `ItemReader`, `ItemProcessor` và `ItemWriter` với vòng lặp chunk do Spring Batch quản lý.

| Đặc điểm | TaskletStep | Chunk-oriented step |
|---|---|---|
| Đơn vị xử lý | Một lần gọi `Tasklet.execute()` | Một chunk item |
| Cách kết thúc | Tasklet trả `FINISHED` | Reader báo hết dữ liệu bằng `null` và chunk cuối hoàn tất |
| Cách lặp | Tasklet trả `CONTINUABLE` | Framework đọc và ghi các chunk tiếp theo |
| API chính | `Tasklet` và `RepeatStatus` | `ItemReader`, `ItemProcessor`, `ItemWriter` |

Không trả về `RepeatStatus` từ `ItemReader.read()`. Reader trả `null` khi hết dữ liệu. Cũng không cần tự viết vòng lặp `CONTINUABLE` bên trong processor hoặc writer; Spring Batch điều khiển vòng lặp chunk.

Chọn Tasklet khi công việc là một thao tác tùy chỉnh hoặc có thể chia thành các lượt thực thi rõ ràng. Chọn chunk-oriented processing khi dữ liệu cần được đọc, xử lý và ghi theo nhóm với checkpoint và fault tolerance theo item/chunk.

## 9. Tránh vòng lặp vô hạn

Nếu tasklet luôn trả về `CONTINUABLE`, Spring Batch sẽ tiếp tục gọi nó. Một lỗi phổ biến là điều kiện dừng không bao giờ đạt được, hoặc trạng thái tiến độ không được cập nhật đúng.

Ví dụ lỗi:

```java
@Override
public RepeatStatus execute(
        StepContribution contribution,
        ChunkContext chunkContext) {

    processCurrentBatch();
    return RepeatStatus.CONTINUABLE; // Không có điều kiện dừng
}
```

Tasklet này có thể chạy mãi cho đến khi bị dừng, lỗi hoặc hết tài nguyên. Trước khi trả về `CONTINUABLE`, cần bảo đảm lần lặp tiếp theo có công việc hữu hạn và có thể tiến gần tới điều kiện kết thúc.

Các biện pháp kiểm soát:

1. Xác định điều kiện dừng rõ ràng, ví dụ không còn trang dữ liệu hoặc không còn tệp.
2. Cập nhật checkpoint sau mỗi phần việc hoàn tất.
3. Đặt giới hạn số lượt lặp hoặc deadline tổng thể khi nghiệp vụ yêu cầu.
4. Ghi log/metric về số lượt, số item và tiến độ để phát hiện tasklet không tiến triển.
5. Dùng timeout và backoff khi gọi hệ thống bên ngoài.
6. Nếu không có công việc mới, trả `FINISHED` thay vì tiếp tục polling không giới hạn.

Không nên dùng `Thread.sleep()` dài trong tasklet để chờ sự kiện nếu việc đó giữ transaction mở. Với tác vụ chờ lâu, cân nhắc tách thành bước điều phối, scheduler, message queue hoặc cơ chế chờ bên ngoài rồi khởi chạy job khi có điều kiện.

## 10. CONTINUABLE và lỗi/restart

Nếu một lần gọi tasklet ném exception, lần lặp hiện tại thất bại và step có thể kết thúc với trạng thái `FAILED` tùy xử lý lỗi. Khi restart JobInstance hợp lệ, Spring Batch tạo JobExecution mới và có thể tiếp tục step dựa trên metadata cùng `ExecutionContext` đã lưu.

Để restart an toàn, tasklet cần:

- Lưu checkpoint đủ để xác định phần việc tiếp theo.
- Chỉ cập nhật checkpoint sau khi phần dữ liệu tương ứng được xử lý thành công.
- Có khả năng xử lý lại phần việc nếu lỗi xảy ra trước commit.
- Dùng thao tác idempotent hoặc khóa nghiệp vụ cho side effect không thể rollback.
- Giữ cấu trúc key và ý nghĩa dữ liệu trong `ExecutionContext` tương thích giữa các lần triển khai.

Ví dụ nếu tasklet xử lý trang 5, ghi dữ liệu nghiệp vụ rồi cập nhật `nextPage=6` trong cùng transaction, restart có thể bắt đầu từ trang 6 sau khi transaction commit. Nếu transaction rollback, checkpoint cũ vẫn được dùng và trang 5 có thể được xử lý lại. Nếu hai thao tác ở hai hệ thống không cùng transaction, cần thiết kế đối soát và idempotency.

`CONTINUABLE` tự nó không lưu tiến độ. Nó chỉ yêu cầu lặp lại. Việc lưu trạng thái phải do tasklet và các thành phần `ItemStream`/`ExecutionContext` liên quan thực hiện.

## 11. Các lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Luôn trả `CONTINUABLE` | Tasklet lặp vô hạn | Xây dựng điều kiện dừng rõ ràng |
| Trả `FINISHED` khi còn dữ liệu | Công việc bị kết thúc sớm | Kiểm tra kết quả xử lý và trạng thái nguồn trước khi kết thúc |
| Dùng `CONTINUABLE` để chuyển sang step khác | Flow không chuyển như mong đợi | Dùng transition theo `ExitStatus` hoặc decider |
| Không lưu checkpoint | Restart có thể bắt đầu lại từ đầu hoặc không biết phần tiếp theo | Lưu tiến độ vào `ExecutionContext` |
| Cập nhật checkpoint trước khi xử lý thành công | Có thể bỏ sót dữ liệu khi lỗi | Cập nhật trạng thái sau xử lý và trong transaction phù hợp |
| Chờ vô hạn bên trong `execute()` | Giữ transaction và tài nguyên quá lâu | Dùng timeout, backoff hoặc cơ chế điều phối bên ngoài |
| Side effect không idempotent | Lặp thao tác khi retry/restart | Dùng idempotency key, outbox hoặc đối soát |
| Dùng Tasklet cho pipeline item phức tạp không có checkpoint riêng | Khó quản lý retry/skip theo item | Cân nhắc chunk-oriented processing |

## 12. Quy trình chọn RepeatStatus

Khi triển khai tasklet, hãy xác định:

1. Công việc có thể hoàn tất trong một lần gọi hay cần nhiều lượt?
2. Nếu cần nhiều lượt, mỗi lượt xử lý đơn vị hữu hạn nào?
3. Điều kiện chính xác để biết không còn việc cần làm là gì?
4. Tiến độ cần lưu trong `ExecutionContext` gồm những gì?
5. Dữ liệu nghiệp vụ và checkpoint có thể commit trong cùng transaction không?
6. Nếu một lượt được gọi lại sau lỗi, thao tác có an toàn và idempotent không?
7. Có giới hạn số lần lặp, timeout hoặc cơ chế dừng khi không có tiến triển không?

Nếu tasklet hoàn tất công việc trong một lần gọi, trả `FINISHED`. Nếu vừa xử lý xong một phần và còn phần tiếp theo, cập nhật checkpoint rồi trả `CONTINUABLE`. Nếu cần chuyển sang một step khác, để tasklet step kết thúc và định nghĩa transition trong job flow.

## Kết luận

`RepeatStatus.FINISHED` dừng vòng lặp thực thi tasklet, còn `RepeatStatus.CONTINUABLE` yêu cầu Spring Batch gọi lại `Tasklet.execute()` trong cùng `StepExecution`. Mỗi lần gọi tasklet trong `TaskletStep` được quản lý bằng transaction của step, vì vậy có thể chia công việc thành nhiều lượt và lưu checkpoint giữa các lượt.

`RepeatStatus` không phải trạng thái job flow và không thay thế `ExitStatus` hoặc `BatchStatus`. Hãy dùng `CONTINUABLE` khi có điều kiện lặp hữu hạn, lưu tiến độ đúng thời điểm, tránh chờ lâu trong transaction và bảo đảm side effect an toàn khi retry hoặc restart.
