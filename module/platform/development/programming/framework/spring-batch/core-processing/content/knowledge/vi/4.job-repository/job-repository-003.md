# ExecutionContext của job và step

Trong Spring Batch, `ExecutionContext` là vùng lưu trữ các cặp key/value gắn với quá trình thực thi. Framework dùng nó để giữ trạng thái cần thiết giữa các bước xử lý, lưu checkpoint và hỗ trợ restart khi Job bị gián đoạn. Có hai phạm vi chính: `ExecutionContext` của `JobExecution` và `ExecutionContext` của `StepExecution`.

Hai context đều có kiểu `ExecutionContext`, nhưng chúng đại diện cho hai phạm vi khác nhau. Job context phục vụ dữ liệu cần tồn tại ở phạm vi toàn Job và có thể được các Step sử dụng. Step context lưu trạng thái riêng của một lần thực thi Step, đặc biệt hữu ích cho checkpoint của reader hoặc writer.

## 1. ExecutionContext là gì?

`ExecutionContext` là một cấu trúc dữ liệu dạng key/value do Spring Batch quản lý. Mỗi entry có một tên key và một giá trị. Ví dụ, một Step có thể lưu số thứ tự bản ghi đã đọc, mã bản ghi cuối cùng đã xử lý hoặc tên file đầu vào đang được sử dụng.

```java
ExecutionContext context = new ExecutionContext();

context.putString("inputFile", "orders.csv");
context.putLong("lastProcessedId", 4200L);

String inputFile = context.getString("inputFile");
long lastProcessedId = context.getLong("lastProcessedId");
```

Trong ứng dụng Spring Batch, thông thường không tự tạo context mới như ví dụ trên để quản lý trạng thái thực thi. Hãy lấy context gắn với `JobExecution` hoặc `StepExecution` hiện tại. Spring Batch và `JobRepository` chịu trách nhiệm lưu metadata context theo vòng đời thực thi.

ExecutionContext có các đặc điểm quan trọng:

- Dữ liệu được tổ chức theo key để có thể đọc lại ở một thời điểm thực thi sau đó.
- Context thuộc về một execution cụ thể, không phải cấu hình tĩnh của Job.
- Framework lưu context vào metadata repository để hỗ trợ theo dõi và restart.
- Giá trị cần có khả năng được serializer mà ứng dụng cấu hình xử lý. Các kiểu đơn giản như String, số và các object Serializable phù hợp hơn các object lớn hoặc phụ thuộc tài nguyên runtime.
- Key cần ổn định và có ý nghĩa rõ ràng vì code ở lần chạy tiếp theo có thể phụ thuộc vào chính key đó.

ExecutionContext là nơi lưu trạng thái thực thi, không phải nơi lưu toàn bộ dữ liệu nghiệp vụ. Ví dụ, lưu ID của bản ghi cuối cùng đã commit thường hợp lý hơn lưu cả danh sách hàng triệu bản ghi vào context.

## 2. Job ExecutionContext và Step ExecutionContext

Mỗi `JobExecution` có một Job-level `ExecutionContext`. Mỗi `StepExecution` có một Step-level `ExecutionContext`. Một JobExecution có thể chứa nhiều StepExecution, do đó trong một lần chạy Job có thể tồn tại một Job context và nhiều Step context.

```text
JobExecution
  |
  +-- Job ExecutionContext
  |     +-- inputFile
  |     +-- businessDate
  |     +-- validatedRecordCount
  |
  +-- StepExecution: validateStep
  |     +-- Step ExecutionContext
  |           +-- currentLine
  |           +-- validationCheckpoint
  |
  +-- StepExecution: importStep
  |     +-- Step ExecutionContext
  |           +-- lastCommittedOrderId
  |           +-- readPosition
  |
  +-- StepExecution: reportStep
        +-- Step ExecutionContext
              +-- reportPage
```

| Tiêu chí | Job ExecutionContext | Step ExecutionContext |
|---|---|---|
| Thuộc về | Một `JobExecution` | Một `StepExecution` |
| Phạm vi | Toàn bộ lần chạy Job | Một lần chạy Step cụ thể |
| Mục đích | Giữ trạng thái dùng chung giữa các Step hoặc cần thiết ở phạm vi Job | Giữ checkpoint và trạng thái riêng của Step |
| Thời điểm lưu thông thường | Được cập nhật vào repository ở ranh giới hoàn tất Step | Được lưu tại các điểm commit của Step và khi Step kết thúc |
| Ví dụ | Ngày nghiệp vụ, đường dẫn đầu vào, số bản ghi đã kiểm tra để Step sau sử dụng | Vị trí reader, ID cuối cùng đã commit, số trang đang xử lý |

Một Step có thể truy cập cả hai context thông qua StepExecution:

```java
StepExecution stepExecution = contribution.getStepExecution();

ExecutionContext stepContext = stepExecution.getExecutionContext();
ExecutionContext jobContext = stepExecution.getJobExecution().getExecutionContext();
```

Hai biến trên cùng có kiểu `ExecutionContext`, nhưng ghi vào biến nào sẽ quyết định phạm vi và thời điểm dữ liệu được duy trì.

## 3. Lưu dữ liệu vào Job ExecutionContext

Job context phù hợp với dữ liệu mà nhiều Step cần sử dụng hoặc trạng thái có ý nghĩa ở phạm vi toàn bộ lần chạy Job. Ví dụ, Step đầu tiên xác định file đầu vào và Step tiếp theo cần đọc lại đường dẫn file đó.

Có thể ghi vào Job context từ code đang chạy trong một Step:

```java
public class PrepareInputTasklet implements Tasklet {

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {

        JobExecution jobExecution = contribution.getStepExecution().getJobExecution();
        ExecutionContext jobContext = jobExecution.getExecutionContext();

        jobContext.putString("inputFile", "data/orders-2026-11-15.csv");
        jobContext.putString("businessDate", "2026-11-15");

        return RepeatStatus.FINISHED;
    }
}
```

Ở Step tiếp theo, có thể đọc lại các giá trị từ JobExecution hiện tại:

```java
public class ImportOrdersTasklet implements Tasklet {

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {

        ExecutionContext jobContext = contribution.getStepExecution()
                .getJobExecution()
                .getExecutionContext();

        String inputFile = jobContext.getString("inputFile");
        String businessDate = jobContext.getString("businessDate");

        // Dùng inputFile và businessDate để thực hiện công việc nhập dữ liệu.
        return RepeatStatus.FINISHED;
    }
}
```

Job context được lưu theo ranh giới Step. Vì vậy, khi Step tiếp theo bắt đầu, nó có thể đọc những thay đổi Job context đã được lưu sau khi Step trước hoàn tất. Nếu Job bị lỗi giữa lúc một Step đang chạy, không nên giả định mọi thay đổi Job context mới thực hiện trong Step đó đã được lưu ngay lập tức.

Hãy dùng Job context cho dữ liệu cần được chia sẻ ở phạm vi Job. Nếu cần checkpoint chi tiết trong một Step đang chạy, Step context thường phù hợp hơn vì nó được lưu tại các điểm commit của Step.

## 4. Lưu checkpoint trong Step ExecutionContext

Step context thường được dùng để lưu tiến độ xử lý của một Step. Trong chunk-oriented processing, một Step đọc, xử lý và ghi dữ liệu theo từng chunk. Khi một chunk commit thành công, Spring Batch có thể lưu trạng thái của Step để lần restart biết tiến độ đã được xác nhận đến đâu.

Một reader có trạng thái thường triển khai `ItemStream` (hoặc interface mở rộng như `ItemStreamReader`) để nhận và cập nhật ExecutionContext:

```java
public class CheckpointingReader implements ItemStreamReader<Order> {

    private int currentIndex;
    private List<Order> orders;

    @Override
    public void open(ExecutionContext executionContext) {
        currentIndex = executionContext.getInt("currentIndex", 0);
        orders = loadOrders();
    }

    @Override
    public Order read() {
        if (currentIndex >= orders.size()) {
            return null;
        }

        return orders.get(currentIndex++);
    }

    @Override
    public void update(ExecutionContext executionContext) {
        executionContext.putInt("currentIndex", currentIndex);
    }

    @Override
    public void close() {
        // Giải phóng tài nguyên nếu reader có mở tài nguyên.
    }

    private List<Order> loadOrders() {
        // Ví dụ minh họa: tải dữ liệu từ nguồn đầu vào.
        return List.of();
    }
}
```

Spring Batch gọi `open` khi bắt đầu stream, truyền vào Step ExecutionContext đã được khôi phục. Reader đọc vị trí đã lưu để tiếp tục. Trong quá trình xử lý, framework gọi `update` tại các điểm lưu trạng thái để reader ghi checkpoint hiện tại vào context. Khi Step được restart, `open` nhận lại checkpoint đã được lưu.

Đoạn code trên minh họa cơ chế; reader thực tế cần bảo đảm vị trí checkpoint tương ứng với dữ liệu đã commit. Với nguồn dữ liệu có thể thay đổi, chỉ lưu chỉ số dòng có thể chưa đủ. Có thể cần lưu khóa ổn định, offset hoặc token do nguồn dữ liệu cung cấp.

Các reader và writer tích hợp sẵn như `FlatFileItemReader` đã hỗ trợ cơ chế stream và lưu trạng thái khi được cấu hình phù hợp. Khi dùng component có sẵn, cần giữ trạng thái lưu trữ của nó được bật nếu muốn hỗ trợ restart; không nên tự triển khai checkpoint nếu component đã quản lý tiến độ an toàn.

## 5. Chia sẻ dữ liệu từ Step context sang Job context

Một trường hợp phổ biến là Step đầu tiên tính toán một giá trị và Step tiếp theo cần sử dụng giá trị đó. Có thể ghi kết quả vào Step context rồi dùng `ExecutionContextPromotionListener` để đưa một số key lên Job context sau khi Step hoàn tất thành công.

Trong Step tạo dữ liệu, lưu giá trị vào Step ExecutionContext:

```java
public class ValidateOrdersTasklet implements Tasklet {

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {

        ExecutionContext stepContext = contribution.getStepExecution()
                .getExecutionContext();

        long validatedCount = validateInput();
        stepContext.putLong("validatedCount", validatedCount);

        return RepeatStatus.FINISHED;
    }

    private long validateInput() {
        // Thực hiện kiểm tra và trả về số bản ghi hợp lệ.
        return 250L;
    }
}
```

Khai báo promotion listener cho Step:

```java
@Bean
public ExecutionContextPromotionListener validationPromotionListener() {
    ExecutionContextPromotionListener listener =
            new ExecutionContextPromotionListener();

    listener.setKeys(new String[] {"validatedCount"});
    listener.setStatuses(new String[] {"COMPLETED"});
    return listener;
}
```

Đăng ký listener trong cấu hình Step:

```java
@Bean
public Step validateOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ValidateOrdersTasklet tasklet,
        ExecutionContextPromotionListener validationPromotionListener) {

    return new StepBuilder("validateOrdersStep", jobRepository)
            .tasklet(tasklet, transactionManager)
            .listener(validationPromotionListener)
            .build();
}
```

Sau khi Step hoàn tất với exit code phù hợp, listener sao chép key được chỉ định từ Step ExecutionContext sang Job ExecutionContext. Step sau có thể đọc giá trị từ Job context:

```java
long validatedCount = contribution.getStepExecution()
        .getJobExecution()
        .getExecutionContext()
        .getLong("validatedCount");
```

Promotion hữu ích khi muốn Step giữ dữ liệu nội bộ trong lúc chạy, sau đó chỉ công bố một số kết quả cần thiết cho phần còn lại của Job. Hãy cấu hình danh sách key rõ ràng và chỉ promotion những dữ liệu Step sau thực sự cần.

## 6. Thời điểm lưu và khôi phục context

Thời điểm lưu là điểm quan trọng khi thiết kế restart:

| Context | Thời điểm lưu thông thường | Ý nghĩa khi restart |
|---|---|---|
| Step ExecutionContext | Tại các điểm commit của Step; được cập nhật khi Step kết thúc | Có thể khôi phục checkpoint gần nhất đã được lưu của Step |
| Job ExecutionContext | Ở ranh giới hoàn tất mỗi Step | Step tiếp theo hoặc lần restart có thể dùng trạng thái Job đã được lưu sau Step trước |

Với chunk-oriented Step, các thay đổi Step context gắn với ranh giới commit. Nếu một chunk thất bại và transaction rollback, checkpoint của chunk đó không nên được xem là đã commit. Khi restart, reader cần tiếp tục từ checkpoint nhất quán với dữ liệu đã commit.

Job context không được thiết kế để thay thế checkpoint từng chunk. Nếu một Step xử lý hàng triệu bản ghi và chỉ ghi số lượng đã xử lý vào Job context, giá trị đó có thể không phản ánh tiến độ mới nhất khi Step bị lỗi giữa chừng. Hãy lưu tiến độ chi tiết trong Step context hoặc cơ chế checkpoint phù hợp của reader/writer.

Việc lưu metadata và transaction dữ liệu nghiệp vụ cần được thiết kế nhất quán. Với cấu hình repository và transaction thông thường, Spring Batch phối hợp cập nhật trạng thái tại ranh giới xử lý. Tuy nhiên, nếu dữ liệu nghiệp vụ nằm ở hệ thống hoặc transaction manager khác, cần cân nhắc lỗi giữa hai lần commit và thiết kế xử lý lặp an toàn (idempotent) hoặc cơ chế đối soát.

## 7. Phân biệt ExecutionContext với JobParameters

`JobParameters` và `ExecutionContext` đều có thể chứa dữ liệu liên quan đến một lần chạy, nhưng mục đích của chúng khác nhau:

| Tiêu chí | JobParameters | ExecutionContext |
|---|---|---|
| Vai trò | Đầu vào khi khởi chạy Job | Trạng thái phát sinh trong quá trình thực thi |
| Nơi cung cấp | Ứng dụng hoặc scheduler gọi JobLauncher | Job/Step và các component trong quá trình chạy |
| Nội dung ví dụ | Ngày nghiệp vụ, đường dẫn file, chế độ xử lý | Vị trí reader, số bản ghi đã kiểm tra, ID cuối cùng đã commit |
| Identifying | Có thể đánh dấu identifying để xác định JobInstance | Không dùng để xác định JobInstance |
| Thay đổi trong lúc chạy | Được xem là tham số đầu vào của lần chạy | Được cập nhật để lưu tiến độ và trạng thái |

Ví dụ, `businessDate=2026-11-15` có thể là JobParameter identifying để xác định công việc nhập dữ liệu cho ngày đó. Trong khi đó, `lastProcessedOrderId=4200` là checkpoint phát sinh trong lúc chạy và phù hợp với Step ExecutionContext.

Không nên dùng ExecutionContext để thay thế dữ liệu đầu vào mà scheduler cần cung cấp rõ ràng. Cũng không nên cố thay đổi JobParameters để lưu tiến độ; hãy dùng context đúng phạm vi.

## 8. Quy tắc thiết kế key và giá trị

ExecutionContext được lưu lâu hơn vòng đời một method hoặc một object Java. Vì vậy, cần thiết kế key và giá trị có tính ổn định:

- Dùng key mô tả ý nghĩa, chẳng hạn `lastCommittedOrderId` thay vì `x1`.
- Tránh trùng key giữa các component trong cùng một context. Có thể thêm tiền tố tên Step hoặc component, ví dụ `importOrders.lastCommittedId`.
- Chỉ lưu giá trị nhỏ cần thiết cho điều phối hoặc restart; dữ liệu nghiệp vụ lớn nên nằm trong database hoặc object storage.
- Chọn kiểu dữ liệu có thể được serializer cấu hình hỗ trợ và duy trì tương thích khi triển khai phiên bản ứng dụng mới.
- Tránh lưu connection, stream, thread, file handle hoặc object phụ thuộc trạng thái runtime; các tài nguyên này cần được mở lại trong lần thực thi mới.
- Không lưu mật khẩu, token truy cập hoặc bí mật vào context nếu không có cơ chế bảo vệ phù hợp, vì metadata có thể được lưu trong cơ sở dữ liệu và được người vận hành tra cứu.
- Khi thay đổi một object mutable đã đặt trong context, hãy cẩn thận: framework theo dõi trạng thái thay đổi của context qua các thao tác put/remove, không nhất thiết nhận biết mọi thay đổi bên trong object. Ưu tiên giá trị bất biến hoặc đặt lại giá trị bằng `put` sau khi cập nhật.

Nếu cấu trúc dữ liệu lưu trong context thay đổi giữa các phiên bản ứng dụng, cần cân nhắc khả năng đọc lại context cũ khi restart. Ví dụ, đổi kiểu dữ liệu của một key hoặc đổi tên key có thể khiến code mới không đọc được metadata được tạo bởi phiên bản trước. Có thể duy trì tương thích bằng cách hỗ trợ key cũ trong giai đoạn chuyển đổi hoặc chủ động kết thúc các execution cũ trước khi triển khai thay đổi.

## 9. Những nhầm lẫn thường gặp

**Dùng Job context để lưu checkpoint cho từng chunk.** Job context thường được lưu ở ranh giới Step. Hãy dùng Step context cho tiến độ chi tiết trong Step đang chạy.

**Cho rằng hai context là một vùng dữ liệu duy nhất.** Job context và Step context có phạm vi và vòng đời lưu khác nhau. Ghi key vào Step context không tự động làm key xuất hiện trong Job context; dùng promotion listener khi cần chuyển dữ liệu.

**Cho rằng mọi thay đổi context được ghi xuống database ngay lập tức.** Thời điểm lưu phụ thuộc phạm vi context và ranh giới commit/Step. Thiết kế restart phải dựa trên checkpoint đã được lưu.

**Lưu toàn bộ object nghiệp vụ vào context.** Context phục vụ metadata và checkpoint. Lưu dữ liệu lớn làm metadata nặng, tăng chi phí serialize và gây khó khăn khi thay đổi cấu trúc object.

**Dùng JobParameters để ghi tiến độ.** JobParameters là đầu vào xác định lần chạy; ExecutionContext là nơi lưu trạng thái phát sinh khi chạy.

**Giả định Step context tự động chia sẻ cho Step tiếp theo.** Step context thuộc về một StepExecution. Muốn Step sau đọc một giá trị, hãy lưu nó trong Job context hoặc promotion từ Step context.

## 10. Chọn đúng context cho từng nhu cầu

Khi cần một reader tiếp tục từ vị trí đã đọc sau khi restart, lưu checkpoint trong Step ExecutionContext. Khi Step đầu tiên xác định một giá trị mà nhiều Step sau cần dùng, lưu trong Job ExecutionContext hoặc promotion key từ Step context. Khi scheduler truyền ngày nghiệp vụ hay đường dẫn file đầu vào, dùng JobParameters. Khi dữ liệu lớn cần được xử lý, lưu dữ liệu trong kho lưu trữ nghiệp vụ và chỉ giữ khóa hoặc checkpoint nhỏ trong context.

Phân biệt đúng phạm vi Job và Step giúp Spring Batch khôi phục tiến độ nhất quán, chia sẻ dữ liệu giữa các Step có chủ đích và tránh phụ thuộc vào trạng thái chỉ tồn tại trong bộ nhớ của một lần chạy.
