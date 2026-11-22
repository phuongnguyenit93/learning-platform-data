# TaskletStep và chunk-oriented step

Trong Spring Batch, Step là một giai đoạn độc lập của Job. Một Step có thể thực hiện một thao tác nghiệp vụ gọn, chẳng hạn gọi stored procedure hoặc di chuyển file, hoặc xử lý một lượng lớn bản ghi theo từng nhóm. Hai cách tổ chức thường gặp là **TaskletStep** và **chunk-oriented processing**.

Điểm quan trọng khi học hai khái niệm này là phân biệt API dùng để khai báo Step với cơ chế thực thi bên dưới. TaskletStep là một kiểu Step triển khai việc gọi Tasklet trong một vòng lặp có quản lý giao dịch. Chunk-oriented processing là mô hình xử lý dữ liệu theo từng chunk; trong Spring Batch, mô hình này cũng được triển khai bên trong TaskletStep bằng một Tasklet chuyên biệt.

## 1. Step nằm ở đâu trong Job?

Job mô tả quy trình batch ở mức tổng thể. Job thường được ghép từ nhiều Step, mỗi Step đảm nhiệm một phần công việc:

~~~text
Job: importOrders
    |
    +-- Step 1: validateInput
    |
    +-- Step 2: importOrders
    |
    +-- Step 3: generateReport
    |
    +-- Step 4: archiveInput
~~~

Step có vòng đời, trạng thái thực thi và metadata riêng. Spring Batch ghi nhận các lần thực thi Step thông qua StepExecution, bao gồm số lần đọc, xử lý, ghi, số bản ghi bị bỏ qua, trạng thái và ExecutionContext.

Khi thiết kế Step, câu hỏi đầu tiên nên là bản chất công việc:

- Công việc là một thao tác hoặc một đoạn logic có thể thực hiện trong một lần gọi? Tasklet thường phù hợp.
- Công việc cần đọc nhiều item, xử lý từng item và ghi kết quả theo nhóm? Chunk-oriented processing thường phù hợp.

Hai lựa chọn cùng sử dụng cơ chế quản lý Step của Spring Batch, nhưng cách tổ chức logic, ranh giới giao dịch và khả năng xử lý lỗi ở cấp item khác nhau.

## 2. Tasklet và TaskletStep là gì?

**Tasklet** là một hợp đồng xử lý nhỏ trong Spring Batch. Một Tasklet thực hiện công việc trong phương thức:

~~~java
RepeatStatus execute(
        StepContribution contribution,
        ChunkContext chunkContext) throws Exception;
~~~

Tasklet nhận StepContribution để cập nhật thông tin đóng góp cho StepExecution và ChunkContext để truy cập ngữ cảnh của lần gọi. Phương thức trả về RepeatStatus để cho biết vòng lặp Tasklet cần tiếp tục hay đã kết thúc:

- **RepeatStatus.FINISHED**: Tasklet đã hoàn tất công việc; Step có thể kết thúc nếu không có lỗi khác.
- **RepeatStatus.CONTINUABLE**: Spring Batch gọi Tasklet tiếp tục ở lượt kế tiếp.

**TaskletStep** là implementation của Step thực thi một Tasklet. Nó quản lý vòng lặp gọi Tasklet, transaction, cập nhật StepExecution và lưu trạng thái thực thi. Mỗi lần gọi Tasklet.execute được thực hiện trong một transaction do Step quản lý.

Với một Tasklet chỉ thực hiện một thao tác, luồng thường có dạng:

~~~text
TaskletStep bắt đầu
       |
       v
Mở transaction
       |
       v
Gọi Tasklet.execute(...)
       |
       v
Tasklet trả FINISHED?
   | Có             | Không
   v                v
Commit transaction  Commit transaction
   |                |
   v                v
Kết thúc Step       Lặp lại và gọi Tasklet lần nữa
~~~

Nếu Tasklet trả về CONTINUABLE, Step tiếp tục vòng lặp. Mỗi lần gọi tiếp theo lại được thực hiện trong transaction của lượt đó. Nếu Tasklet ném exception, transaction hiện tại được rollback theo cấu hình transaction manager và Step có thể kết thúc ở trạng thái thất bại.

### Ví dụ Tasklet thực hiện một thao tác

Giả sử hệ thống cần đánh dấu một lô dữ liệu đã được đối soát. Công việc là một thao tác nghiệp vụ đơn lẻ nên có thể triển khai bằng Tasklet:

~~~java
@Bean
public Step markReconciliationStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ReconciliationService reconciliationService) {

    Tasklet tasklet = (contribution, chunkContext) -> {
        reconciliationService.markCurrentBatchAsReconciled();
        return RepeatStatus.FINISHED;
    };

    return new StepBuilder("markReconciliationStep", jobRepository)
            .tasklet(tasklet, transactionManager)
            .build();
}
~~~

Trong ví dụ, Tasklet gọi service và trả về FINISHED sau khi thao tác hoàn tất. StepBuilder tạo Step với tên ổn định, JobRepository quản lý metadata và transaction manager điều khiển transaction cho lần thực thi Tasklet.

Đoạn code sử dụng API của Spring Batch 5 trở lên, trong đó JobRepository và PlatformTransactionManager được truyền trực tiếp khi tạo StepBuilder và khai báo Tasklet.

### Khi Tasklet cần nhiều lượt thực thi

Tasklet không bắt buộc chỉ được gọi đúng một lần. Nếu công việc cần lặp, Tasklet có thể trả về CONTINUABLE khi vẫn còn việc và FINISHED khi đã xử lý xong:

~~~java
@Bean
public Step processPendingPagesStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        PendingPageService pageService) {

    Tasklet tasklet = (contribution, chunkContext) -> {
        boolean processed = pageService.processNextPage();

        return processed
                ? RepeatStatus.CONTINUABLE
                : RepeatStatus.FINISHED;
    };

    return new StepBuilder("processPendingPagesStep", jobRepository)
            .tasklet(tasklet, transactionManager)
            .build();
}
~~~

Mỗi lượt gọi xử lý một trang và kết thúc transaction của lượt đó. Khi còn trang, vòng lặp tiếp tục. Khi không còn dữ liệu, Tasklet trả FINISHED.

Với công việc lặp qua nhiều lượt, cần xác định rõ cách lưu vị trí xử lý. Nếu tiến độ phải được khôi phục sau restart, Tasklet cần lưu checkpoint vào ExecutionContext hoặc một kho trạng thái bền vững phù hợp. Không nên chỉ dựa vào biến instance trong bộ nhớ vì bean có thể được tạo lại hoặc tiến trình có thể dừng bất kỳ lúc nào.

## 3. Chunk-oriented processing là gì?

Chunk-oriented processing tổ chức việc xử lý dữ liệu theo từng nhóm item. Mỗi chunk được đọc, xử lý và ghi trong một đơn vị giao dịch. Mô hình tiêu chuẩn gồm ba thành phần:

- **ItemReader** đọc từng item từ nguồn dữ liệu.
- **ItemProcessor** biến đổi, kiểm tra hoặc loại bỏ item; thành phần này có thể không được cấu hình nếu không cần xử lý trung gian.
- **ItemWriter** ghi một nhóm item đã xử lý ra đích.

Ví dụ Job nhập đơn hàng từ file CSV vào cơ sở dữ liệu. Thay vì nạp toàn bộ file vào bộ nhớ rồi ghi một lần, Spring Batch đọc và ghi theo các nhóm có kích thước giới hạn.

~~~text
Nguồn dữ liệu
     |
     v
 ItemReader
     |
     v
 ItemProcessor (tùy chọn)
     |
     v
 Tập item của chunk
     |
     v
 ItemWriter
     |
     v
 Đích dữ liệu

Mỗi chunk hoàn tất trong một transaction
     |
     v
 Commit và chuyển sang chunk tiếp theo
~~~

**Commit interval** là số lượng item dùng để xác định kích thước chunk thông thường. Ví dụ cấu hình chunk size là 100 thì Step đọc và xử lý một nhóm tối đa khoảng 100 item trước khi gọi writer và commit nhóm đó. Chunk cuối có thể ít hơn 100 item khi nguồn dữ liệu đã hết.

Chunk-oriented processing phù hợp khi cần xử lý tập dữ liệu lớn, giới hạn bộ nhớ, kiểm soát transaction theo nhóm và tận dụng các cơ chế reader, processor, writer của Spring Batch.

### Ví dụ khai báo chunk-oriented Step

Ví dụ sau xử lý các Order theo từng chunk 100 item:

~~~java
@Bean
public Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> orderReader,
        ItemProcessor<Order, Order> orderProcessor,
        ItemWriter<Order> orderWriter) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .build();
}
~~~

Hai kiểu generic trong khai báo chunk thể hiện kiểu item đầu vào và kiểu item sau xử lý:

- Kiểu thứ nhất là kiểu được ItemReader đọc ra, ở đây là Order.
- Kiểu thứ hai là kiểu ItemProcessor trả về và ItemWriter nhận vào, ở đây cũng là Order.

Nếu processor chuyển đổi OrderInput thành OrderEntity, có thể khai báo hai kiểu khác nhau:

~~~java
return new StepBuilder("convertOrdersStep", jobRepository)
        .<OrderInput, OrderEntity>chunk(100, transactionManager)
        .reader(orderInputReader)
        .processor(orderConverter)
        .writer(orderEntityWriter)
        .build();
~~~

Trong cấu hình này, reader đọc OrderInput, processor chuyển thành OrderEntity và writer ghi các OrderEntity.

## 4. Chunk size quyết định ranh giới transaction

Với chunk-oriented Step, Spring Batch gom các item thành một chunk. Khi chunk đạt kích thước cấu hình hoặc nguồn dữ liệu kết thúc, framework gọi ItemWriter để ghi nhóm item và hoàn tất transaction của chunk.

Ví dụ với chunk size bằng 3:

~~~text
Đọc item 1 -> xử lý item 1
Đọc item 2 -> xử lý item 2
Đọc item 3 -> xử lý item 3
Gọi writer với [1, 2, 3]
Commit transaction của chunk 1

Đọc item 4 -> xử lý item 4
Đọc item 5 -> xử lý item 5
Đọc item 6 -> xử lý item 6
Gọi writer với [4, 5, 6]
Commit transaction của chunk 2
~~~

Nếu writer hoặc một thao tác tham gia transaction thất bại trước khi commit, transaction của chunk hiện tại có thể rollback. Những chunk đã commit trước đó vẫn được ghi nhận. Khi restart, Spring Batch dựa vào metadata và trạng thái của các thành phần có hỗ trợ lưu trạng thái để tiếp tục theo khả năng của reader và cấu hình Step.

Chunk size tạo ra sự cân bằng:

| Chunk size | Tác động thường gặp |
| --- | --- |
| Nhỏ | Transaction ngắn, lượng dữ liệu phải làm lại khi rollback thường nhỏ; đổi lại có nhiều lần commit và overhead lớn hơn |
| Lớn | Ít lần commit hơn và có thể tăng thông lượng; đổi lại transaction kéo dài, dùng nhiều bộ nhớ hơn và phạm vi rollback lớn hơn |

Không có một kích thước chunk tối ưu cho mọi hệ thống. Cần cân nhắc thời gian xử lý item, giới hạn transaction của cơ sở dữ liệu, dung lượng bộ nhớ, khả năng chịu tải và yêu cầu phục hồi.

## 5. Vì sao chunk-oriented vẫn được thực thi bằng TaskletStep?

Đây là mối quan hệ dễ gây nhầm lẫn khi đọc API Spring Batch.

TaskletStep là một bộ điều khiển thực thi Step. Nó nhận một Tasklet và gọi Tasklet trong transaction. Khi khai báo Step bằng API chunk, Spring Batch xây dựng một Tasklet chuyên biệt là ChunkOrientedTasklet để thực hiện vòng đọc, xử lý và ghi từng chunk. ChunkOrientedTasklet được chạy bên trong TaskletStep.

Có thể biểu diễn mối quan hệ như sau:

~~~text
Khai báo Step bằng tasklet(...)
          |
          v
      TaskletStep
          |
          v
      Tasklet tùy chỉnh

Khai báo Step bằng chunk(...)
          |
          v
      TaskletStep
          |
          v
  ChunkOrientedTasklet
          |
          +--> ItemReader
          +--> ItemProcessor
          +--> ItemWriter
          |
          v
     Các chunk và transaction
~~~

Vì vậy, trong cách sử dụng thông thường, TaskletStep và chunk-oriented Step không phải hai loại Step độc lập ở tầng implementation. Khác biệt nằm ở mô hình xử lý được khai báo và Tasklet cụ thể được Step thực thi:

- Với API tasklet, ứng dụng cung cấp Tasklet của riêng mình.
- Với API chunk, ứng dụng cấu hình reader, processor, writer và commit interval; Spring Batch tạo logic chunk tương ứng.

Hiểu mối quan hệ này giúp đọc stack trace, metadata và cấu hình Step chính xác hơn. Một chunk-oriented Step vẫn có StepExecution, transaction và vòng đời của TaskletStep.

## 6. So sánh Tasklet và chunk-oriented processing

| Tiêu chí | Tasklet tùy chỉnh | Chunk-oriented |
| --- | --- | --- |
| Mục tiêu | Thực hiện một thao tác hoặc vòng lặp nghiệp vụ do ứng dụng điều khiển | Xử lý tập item qua reader, processor và writer |
| Đơn vị xử lý | Mỗi lần gọi Tasklet.execute | Một chunk gồm nhiều item |
| Ranh giới transaction | Mỗi lần gọi Tasklet.execute | Mỗi chunk |
| Điều khiển tiếp tục | Tasklet trả FINISHED hoặc CONTINUABLE | Framework quản lý vòng đọc và kết thúc khi reader hết dữ liệu |
| Xử lý item | Ứng dụng tự tổ chức logic | Có cấu trúc reader/processor/writer |
| Commit interval | Không có cấu hình chunk size ở API tasklet | Có cấu hình chunk size |
| Skip/retry theo item | Thường phải tự thiết kế hoặc xử lý ở mức phù hợp | Có cơ chế fault-tolerant ở cấp chunk/item |
| Theo dõi tiến độ | Ứng dụng cần chủ động lưu checkpoint nếu cần | Nhiều reader/writer hỗ trợ ItemStream và ExecutionContext |
| Ví dụ | Gọi stored procedure, dọn dữ liệu, gửi một lệnh điều phối | Import file, đồng bộ bản ghi, chuyển đổi dữ liệu hàng loạt |

Điểm khác biệt về transaction cần được hiểu đúng. Tasklet có thể được gọi nhiều lần và mỗi lần gọi nằm trong transaction riêng. Chunk-oriented Step cũng dùng transaction, nhưng một transaction bao trùm quá trình xử lý một chunk, bao gồm đọc, xử lý và ghi theo cấu hình của Step.

## 7. Xử lý lỗi, retry và skip

### Với Tasklet

Tasklet phù hợp với thao tác có logic nghiệp vụ rõ ràng và phạm vi lỗi tương đối gọn. Khi exception thoát khỏi Tasklet, transaction hiện tại thường bị rollback và Step thất bại, trừ khi ứng dụng hoặc cấu hình xử lý lỗi theo cách khác.

Nếu Tasklet thực hiện nhiều thao tác trong một lần gọi, cần lưu ý transaction chỉ tự động rollback các tài nguyên tham gia cùng transaction manager. Gọi HTTP API, ghi file hoặc gửi thông điệp đến hệ thống bên ngoài không tự động được hoàn tác khi transaction cơ sở dữ liệu rollback.

Vì vậy, Tasklet thực hiện side effect bên ngoài cần được thiết kế có tính idempotent hoặc có cơ chế đối soát, retry và bù trừ. Nếu Tasklet được gọi lại sau restart, cùng một thao tác không nên tạo ra kết quả trùng ngoài ý muốn.

### Với chunk-oriented Step

Chunk-oriented processing cung cấp các cơ chế fault-tolerant để cấu hình retry và skip cho những lỗi phù hợp. Ví dụ:

~~~java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .skip(InvalidOrderException.class)
        .skipLimit(20)
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .build();
~~~

Trong ví dụ, tối đa 20 lỗi InvalidOrderException được phép skip theo cấu hình; lỗi TransientDataAccessException được retry tối đa 3 lần theo chính sách retry. Nếu vượt giới hạn hoặc lỗi không được phép skip/retry, Step có thể thất bại.

Skip và retry có ý nghĩa khác nhau:

- **Skip** cho phép bỏ qua item hoặc lỗi thuộc nhóm được cấu hình để tiếp tục xử lý các item còn lại. Tùy thời điểm phát sinh lỗi, Spring Batch áp dụng skip policy ở giai đoạn đọc, xử lý hoặc ghi.
- **Retry** thử lại thao tác bị lỗi, thường hữu ích với lỗi tạm thời như kết nối cơ sở dữ liệu gián đoạn.

Không nên cấu hình skip cho mọi exception. Bỏ qua lỗi dữ liệu không hợp lệ có thể là yêu cầu nghiệp vụ, nhưng bỏ qua lỗi hạ tầng hoặc lỗi lập trình có thể che giấu sự cố và làm sai kết quả.

## 8. Restart và lưu trạng thái xử lý

Spring Batch lưu metadata của JobExecution và StepExecution trong JobRepository. ExecutionContext gắn với StepExecution có thể lưu thông tin cần thiết để tiếp tục công việc sau khi tiến trình bị dừng.

### Restart trong chunk-oriented Step

Nhiều thành phần reader và writer của Spring Batch triển khai ItemStream. Vòng đời ItemStream cho phép thành phần mở tài nguyên, cập nhật trạng thái và lưu trạng thái vào ExecutionContext. Ví dụ, một file reader có thể lưu vị trí đọc để khi restart biết cần tiếp tục từ đâu.

Việc restart phụ thuộc vào reader/writer cụ thể và cấu hình của chúng. Không phải mọi custom reader đều tự động lưu tiến độ. Nếu tự triển khai reader, cần xem xét triển khai ItemStream, lưu trạng thái trong open/update và khôi phục trong lần mở tiếp theo.

Một số thành phần có tùy chọn saveState. Nếu tắt lưu trạng thái, thành phần đó có thể không khôi phục vị trí đọc như mong đợi. Cần kiểm tra cấu hình trước khi dựa vào restart.

### Restart trong Tasklet

Tasklet tùy chỉnh không tự động có checkpoint chi tiết như một reader hỗ trợ ItemStream. Nếu Tasklet chia công việc thành nhiều lượt hoặc xử lý nhiều nhóm dữ liệu, ứng dụng cần chủ động ghi lại vị trí đã hoàn thành vào ExecutionContext hoặc một kho trạng thái bền vững.

Ví dụ về ý tưởng lưu checkpoint:

~~~java
Tasklet tasklet = (contribution, chunkContext) -> {
    ExecutionContext executionContext =
            contribution.getStepExecution().getExecutionContext();

    int nextPage = executionContext.getInt("nextPage", 0);

    boolean hasMore = pageService.processPage(nextPage);

    if (hasMore) {
        executionContext.putInt("nextPage", nextPage + 1);
        return RepeatStatus.CONTINUABLE;
    }

    return RepeatStatus.FINISHED;
};
~~~

Đây là minh họa cách đọc và cập nhật vị trí xử lý. Trong ứng dụng thực tế, cần xác định rõ ý nghĩa giá trị trả về của service, thời điểm checkpoint được lưu, tính nguyên tử giữa cập nhật dữ liệu nghiệp vụ và checkpoint, cũng như cách xử lý khi một trang bị thực hiện lại.

Checkpoint chỉ đáng tin cậy khi nó nhất quán với dữ liệu đã commit. Nếu cập nhật dữ liệu thành công nhưng checkpoint chưa được lưu, lần restart có thể xử lý lại cùng dữ liệu. Nếu checkpoint được lưu trước khi dữ liệu nghiệp vụ được commit, restart có thể bỏ sót dữ liệu. Thiết kế transaction và tính idempotent phải tính đến hai tình huống này.

## 9. Chọn mô hình nào cho từng loại công việc?

### Dùng Tasklet cho thao tác nghiệp vụ gọn

Tasklet thường là lựa chọn phù hợp khi công việc có thể diễn đạt rõ trong một thao tác hoặc một vòng lặp do ứng dụng kiểm soát, ví dụ:

- Gọi stored procedure để tạo dữ liệu tổng hợp.
- Xóa dữ liệu tạm theo một điều kiện.
- Di chuyển hoặc đổi tên file đầu vào.
- Ghi một bản ghi kiểm soát hoặc cập nhật trạng thái lô.
- Gọi một service điều phối quy trình khác.

Với các thao tác này, mô hình reader/processor/writer có thể không đem lại lợi ích đáng kể. Một Tasklet ngắn, có transaction và xử lý lỗi rõ ràng thường dễ hiểu hơn.

### Dùng chunk-oriented cho xử lý nhiều item

Chunk-oriented phù hợp khi:

- Nguồn dữ liệu có nhiều bản ghi và cần đọc tuần tự.
- Mỗi bản ghi cần được validate hoặc chuyển đổi.
- Kết quả được ghi theo nhóm để tối ưu truy cập cơ sở dữ liệu.
- Cần theo dõi số lượng item đọc, ghi, filter, skip.
- Cần retry hoặc skip ở cấp item theo chính sách cụ thể.
- Muốn tận dụng ItemStream và ExecutionContext để hỗ trợ restart.

Ví dụ điển hình là nhập hàng triệu dòng từ file, đồng bộ dữ liệu giữa hai hệ thống hoặc chuyển đổi bản ghi theo lô.

### Có thể kết hợp cả hai trong một Job

Một Job có thể sử dụng nhiều Step với mô hình khác nhau. Chẳng hạn:

~~~text
Job: dailyImport
    |
    +-- TaskletStep: prepareInput
    |       Kiểm tra file, tạo thư mục làm việc
    |
    +-- Chunk-oriented Step: importRecords
    |       Đọc, chuyển đổi và ghi từng nhóm bản ghi
    |
    +-- TaskletStep: publishResult
    |       Ghi trạng thái hoàn tất, phát tín hiệu
    |
    +-- TaskletStep: archiveInput
            Lưu trữ file đã xử lý
~~~

Việc chia Step theo trách nhiệm giúp theo dõi trạng thái từng giai đoạn và thiết kế restart dễ hơn. Cần đảm bảo các Step có thể được chạy lại an toàn theo chính sách restart của Job.

## 10. Khai báo Step trong Spring Batch 5 trở lên

Spring Batch 5 khuyến khích khai báo Step bằng StepBuilder và truyền JobRepository trực tiếp. Transaction manager cũng được chỉ rõ khi cấu hình Tasklet hoặc chunk:

~~~java
@Configuration
public class OrderJobConfiguration {

    @Bean
    public Step prepareStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            PreparationService preparationService) {

        Tasklet tasklet = (contribution, chunkContext) -> {
            preparationService.prepare();
            return RepeatStatus.FINISHED;
        };

        return new StepBuilder("prepareStep", jobRepository)
                .tasklet(tasklet, transactionManager)
                .build();
    }

    @Bean
    public Step importStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            ItemReader<OrderInput> reader,
            ItemProcessor<OrderInput, Order> processor,
            ItemWriter<Order> writer) {

        return new StepBuilder("importStep", jobRepository)
                .<OrderInput, Order>chunk(100, transactionManager)
                .reader(reader)
                .processor(processor)
                .writer(writer)
                .build();
    }
}
~~~

Hai Step trên minh họa hai cách khai báo:

- prepareStep sử dụng Tasklet tùy chỉnh và hoàn tất sau một lần gọi.
- importStep sử dụng chunk-oriented processing với commit interval 100.

Ở các phiên bản Spring Batch cũ hơn, ứng dụng có thể gặp StepBuilderFactory hoặc JobBuilderFactory. Cách cấu hình phụ thuộc phiên bản framework; khi nâng cấp cần chuyển theo API của phiên bản đang dùng và khai báo transaction manager phù hợp.

## 11. Những lỗi thiết kế thường gặp

### Dùng Tasklet để tự xử lý toàn bộ file lớn trong bộ nhớ

Nếu Tasklet đọc toàn bộ file vào một danh sách rồi mới ghi, bộ nhớ có thể tăng theo kích thước file và toàn bộ thao tác có thể nằm trong một transaction dài. Với dữ liệu lớn, chunk-oriented thường kiểm soát bộ nhớ và transaction tốt hơn.

### Chọn chunk size quá lớn

Chunk lớn có thể làm transaction kéo dài, giữ tài nguyên lâu và khiến một lần rollback phải xử lý lại nhiều item. Hãy đo thời gian và tài nguyên thực tế để chọn kích thước phù hợp.

### Cho rằng một Tasklet luôn chỉ chạy một lần

TaskletStep có thể gọi Tasklet nhiều lần nếu Tasklet trả CONTINUABLE. Logic Tasklet phải xác định điều kiện dừng rõ ràng để tránh vòng lặp vô hạn.

### Dùng RepeatStatus như trạng thái của Job

RepeatStatus chỉ điều khiển vòng lặp gọi Tasklet. Nó không thay thế BatchStatus hoặc ExitStatus. Tasklet trả FINISHED nghĩa là vòng lặp Tasklet kết thúc bình thường; trạng thái cuối của Step còn phụ thuộc kết quả thực thi và các listener hoặc cấu hình khác.

### Nghĩ rằng rollback cơ sở dữ liệu sẽ hoàn tác mọi side effect

Transaction manager chỉ quản lý các tài nguyên tham gia transaction tương ứng. Một request HTTP hoặc thao tác ghi file có thể đã hoàn tất dù transaction cơ sở dữ liệu bị rollback. Hãy dùng idempotency key, outbox, retry có kiểm soát hoặc quy trình bù trừ khi cần phối hợp nhiều hệ thống.

### Không lưu checkpoint cho Tasklet có nhiều lượt

Nếu Tasklet xử lý nhiều trang hoặc nhiều nhóm, việc không lưu tiến độ khiến restart có thể bắt đầu lại từ đầu. Hãy xác định checkpoint bền vững và đảm bảo checkpoint nhất quán với dữ liệu đã commit.

### Bỏ qua khả năng restart của reader và writer

Chunk-oriented không có nghĩa mọi reader/writer đều tự động restart được. Cần dùng thành phần hỗ trợ ItemStream hoặc tự triển khai cơ chế lưu và khôi phục trạng thái.

## 12. Cách ra quyết định khi thiết kế Step

Trước khi viết code, hãy mô tả đầu vào, đầu ra và cách phục hồi của công việc:

1. Công việc có phải xử lý một tập item lớn hay chỉ thực hiện một thao tác nghiệp vụ?
2. Có cần đọc, chuyển đổi và ghi từng item không?
3. Muốn commit sau mỗi thao tác hay sau một nhóm item?
4. Khi một item lỗi, có thể skip hoặc retry riêng item đó không?
5. Khi tiến trình dừng giữa chừng, cần khôi phục từ checkpoint nào?
6. Có side effect bên ngoài transaction cơ sở dữ liệu không, và làm sao tránh thực hiện trùng?

Nếu công việc là một thao tác rõ ràng, Tasklet thường phù hợp. Nếu công việc là luồng xử lý nhiều item, chunk-oriented thường phù hợp. Khi Job có nhiều giai đoạn khác nhau, có thể ghép nhiều Step và chọn mô hình phù hợp cho từng giai đoạn.

## Kết luận

TaskletStep cung cấp cơ chế thực thi Tasklet với vòng lặp, transaction và metadata của Step. Tasklet tùy chỉnh phù hợp với thao tác nghiệp vụ gọn hoặc vòng lặp do ứng dụng điều khiển. Chunk-oriented processing xử lý dữ liệu theo từng nhóm thông qua ItemReader, ItemProcessor và ItemWriter, với mỗi chunk là một đơn vị transaction. Trong Spring Batch, chunk-oriented Step cũng được thực thi bên trong TaskletStep thông qua ChunkOrientedTasklet. Nắm rõ mối quan hệ này giúp chọn đúng mô hình, thiết kế commit interval và xây dựng khả năng restart phù hợp.
