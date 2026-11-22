# Các thành phần sẽ gặp trong một ứng dụng Spring Batch

Spring Batch là framework của Spring dành cho các tác vụ xử lý dữ liệu theo lô (batch processing). Một ứng dụng batch thường phải đọc một lượng dữ liệu lớn, kiểm tra hoặc chuyển đổi dữ liệu, ghi kết quả sang hệ thống khác và có khả năng tiếp tục chạy sau khi gặp lỗi. Spring Batch cung cấp các thành phần để tổ chức công việc, điều phối từng bước xử lý, quản lý giao dịch và lưu trạng thái thực thi.

Khi đọc một ứng dụng Spring Batch, bạn sẽ thường gặp các nhóm thành phần sau:

- **Job và Step** mô tả công việc cần thực hiện và các bước cấu thành công việc đó.
- **JobLauncher và JobRepository** khởi chạy công việc và lưu thông tin thực thi.
- **ItemReader, ItemProcessor và ItemWriter** đảm nhiệm việc đọc, xử lý và ghi từng nhóm dữ liệu.
- **PlatformTransactionManager và ExecutionContext** hỗ trợ giao dịch và lưu trạng thái để có thể khởi động lại.
- **Listener, scope và các công cụ quản lý** cho phép bổ sung hành vi ở những thời điểm phù hợp và vận hành job thuận tiện hơn.

## 1. Bức tranh tổng thể

Một luồng xử lý cơ bản có thể hình dung như sau:

```text
Người dùng / Scheduler / API
             |
             v
        JobLauncher
             |
             v
            Job
             |
       +-----+------+
       |            |
       v            v
     Step 1       Step 2       ...
       |
       v
  ItemReader
       |
       v
 ItemProcessor (có thể bỏ qua)
       |
       v
  ItemWriter

JobLauncher, Job và Step làm việc với JobRepository
để lưu metadata và trạng thái thực thi.
Step sử dụng TransactionManager để quản lý giao dịch.
```

Ví dụ, một job nhập dữ liệu đơn hàng có thể gồm ba step: đọc và kiểm tra file đầu vào, ghi đơn hàng vào cơ sở dữ liệu, sau đó tạo báo cáo kết quả. Mỗi step có thể dùng cách xử lý khác nhau. Step nhập dữ liệu thường dùng mô hình chunk với reader, processor và writer; step tạo báo cáo có thể dùng một tasklet đơn giản.

## 2. Job: công việc batch hoàn chỉnh

`Job` là đơn vị công việc cấp cao nhất trong Spring Batch. Job mô tả một quy trình batch có tên, gồm một hoặc nhiều step và có thể có các nhánh điều khiển tùy theo kết quả thực thi.

Ví dụ về các job:

- `importCustomerJob`: nhập dữ liệu khách hàng từ file.
- `dailySettlementJob`: đối soát giao dịch cuối ngày.
- `archiveOrderJob`: chuyển các đơn hàng cũ sang vùng lưu trữ.

Job thường được khai báo thành một Spring bean. Job không trực tiếp đọc từng dòng dữ liệu; nó điều phối các step thực hiện phần việc cụ thể.

### JobInstance và JobExecution

Hai khái niệm này rất dễ nhầm lẫn:

| Thành phần | Ý nghĩa |
|---|---|
| `Job` | Bản định nghĩa công việc, chẳng hạn `dailySettlementJob`. |
| `JobInstance` | Một lần chạy logic của job, được xác định bởi tên job và các identifying job parameter. |
| `JobExecution` | Một lần thực thi cụ thể của một JobInstance. Một JobInstance có thể có nhiều JobExecution nếu lần chạy trước thất bại và được khởi động lại. |

Giả sử `dailySettlementJob` chạy với tham số ngày nghiệp vụ `2026-11-15`. Tổ hợp tên job và tham số định danh ngày đó xác định một JobInstance. Nếu lần chạy đầu thất bại, lần chạy lại với cùng tham số định danh sẽ tạo một JobExecution mới thuộc cùng JobInstance. Nếu chạy với ngày nghiệp vụ khác, Spring Batch xác định một JobInstance khác.

Vì vậy, `JobInstance` trả lời câu hỏi “đây là công việc cho bộ dữ liệu hoặc kỳ nghiệp vụ nào?”, còn `JobExecution` trả lời câu hỏi “lần thực thi cụ thể này đã diễn ra thế nào?”.

## 3. JobParameters: dữ liệu đầu vào khi khởi chạy

`JobParameters` là tập tham số được truyền vào khi khởi chạy job. Chúng thường dùng để chỉ định file đầu vào, ngày xử lý, mã khách hàng hoặc một phạm vi dữ liệu.

Ví dụ:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("inputFile", "data/orders.csv", true)
        .addString("businessDate", "2026-11-15", true)
        .addString("requestedBy", "scheduler", false)
        .toJobParameters();
```

Tham số có cờ `identifying` bằng `true` tham gia xác định JobInstance. Tham số `requestedBy` ở ví dụ trên có giá trị `false`, nên không làm thay đổi danh tính của JobInstance. Việc chọn tham số định danh cần dựa trên ý nghĩa nghiệp vụ: hai lần chạy có cùng tham số định danh được xem là cùng một lần xử lý logic và có thể liên quan đến cơ chế restart.

Không nên thêm một tham số định danh thay đổi ngẫu nhiên vào mọi lần chạy nếu mục tiêu là khởi động lại đúng JobInstance đã thất bại. Ngược lại, nếu muốn tạo một JobInstance mới có chủ đích, cần truyền bộ tham số định danh mới phù hợp.

## 4. Step và StepExecution

`Step` là một giai đoạn độc lập trong Job. Một job có thể gồm một step hoặc nhiều step nối tiếp, rẽ nhánh hay chạy theo flow được cấu hình.

Ví dụ quy trình nhập đơn hàng:

1. `readOrdersStep`: đọc và kiểm tra dữ liệu đầu vào.
2. `writeOrdersStep`: ghi dữ liệu hợp lệ vào cơ sở dữ liệu.
3. `createSummaryStep`: tạo thống kê sau khi nhập dữ liệu.

`StepExecution` lưu thông tin về một lần thực thi của một step, chẳng hạn trạng thái, thời điểm bắt đầu và kết thúc, số item đã đọc, ghi, bỏ qua hoặc commit. Khi một JobExecution chạy qua nhiều step, mỗi step được thực thi có thông tin StepExecution tương ứng.

Step thường được xây dựng theo một trong hai kiểu chính:

- **Chunk-oriented step**: đọc và xử lý dữ liệu theo từng nhóm item.
- **Tasklet step**: thực hiện một tác vụ trong một hoặc nhiều lần gọi tasklet.

## 5. Chunk processing: đọc, xử lý và ghi theo nhóm

Chunk processing là mô hình thường gặp nhất khi xử lý dữ liệu hàng loạt. Trong mô hình này, Spring Batch đọc từng item, tùy chọn chuyển đổi item, gom các item thành một chunk rồi ghi chunk đó.

Ba thành phần chính là:

### ItemReader

`ItemReader<T>` đọc dữ liệu và trả về từng item kiểu `T`. Mỗi lần Spring Batch gọi `read()`, reader trả về một item. Khi hết dữ liệu, reader trả về `null` để báo kết thúc.

Một số reader thường gặp:

- `FlatFileItemReader`: đọc dữ liệu từ file văn bản như CSV hoặc file phân cách bằng ký tự.
- `JdbcCursorItemReader`: đọc kết quả truy vấn JDBC theo kiểu cursor.
- `JdbcPagingItemReader`: đọc dữ liệu theo từng trang, phù hợp với một số truy vấn dữ liệu lớn.
- `RepositoryItemReader`: đọc dữ liệu thông qua Spring Data repository.

Reader chịu trách nhiệm lấy dữ liệu và chuyển dữ liệu nguồn thành item mà các bước tiếp theo có thể sử dụng. Việc kiểm tra quy tắc nghiệp vụ thường được đặt trong processor để phân chia trách nhiệm rõ ràng.

### ItemProcessor

`ItemProcessor<I, O>` nhận một item kiểu `I`, xử lý và trả về item kiểu `O`. Kiểu đầu vào và đầu ra có thể giống hoặc khác nhau.

Processor thường được dùng để:

- Chuẩn hóa dữ liệu, ví dụ loại bỏ khoảng trắng hoặc chuẩn hóa mã.
- Kiểm tra điều kiện nghiệp vụ và bổ sung thông tin cần thiết.
- Chuyển đổi một bản ghi đầu vào thành đối tượng phù hợp với hệ thống đích.

Processor có thể trả về `null` để lọc bỏ item khỏi chunk được ghi. Đây là hành vi filter; nó khác với việc ném exception để báo lỗi xử lý. Nếu không cần biến đổi hoặc lọc dữ liệu, processor có thể được bỏ qua.

### ItemWriter

`ItemWriter<T>` nhận một nhóm item đã được xử lý và ghi chúng đến đích, chẳng hạn cơ sở dữ liệu, file hoặc dịch vụ khác.

Một số writer thường gặp:

- `JdbcBatchItemWriter`: ghi dữ liệu bằng JDBC batch.
- `FlatFileItemWriter`: ghi dữ liệu ra file.
- `RepositoryItemWriter`: ghi thông qua Spring Data repository.

Trong Spring Batch 5, phương thức `write` nhận một `Chunk` các item. Khi đọc code từ phiên bản cũ hơn, bạn có thể gặp chữ ký phương thức khác, vì API writer đã thay đổi qua các phiên bản.

### Chunk size và ranh giới giao dịch

Giả sử cấu hình chunk size là `100`. Spring Batch đọc tối đa 100 item, chạy processor cho các item đó nếu có, gọi writer để ghi nhóm dữ liệu rồi commit giao dịch. Sau đó framework tiếp tục chunk kế tiếp.

```text
Đọc item 1 ... 100
        |
        v
Xử lý các item (nếu có processor)
        |
        v
Ghi một chunk gồm tối đa 100 item
        |
        v
Commit giao dịch
        |
        v
Đọc chunk tiếp theo
```

Chunk cuối cùng có thể có ít item hơn kích thước đã cấu hình. Khi reader trả về `null`, step kết thúc sau khi hoàn tất việc ghi và commit chunk còn lại.

Chunk size ảnh hưởng đến số lần commit, lượng dữ liệu nằm trong một giao dịch và mức sử dụng bộ nhớ. Chunk quá nhỏ có thể làm tăng chi phí commit; chunk quá lớn có thể khiến giao dịch kéo dài và cần nhiều tài nguyên hơn. Giá trị phù hợp phụ thuộc vào tốc độ reader/writer, kích thước item, cơ sở dữ liệu và yêu cầu khôi phục.

## 6. Tasklet: thực hiện một tác vụ

`Tasklet` phù hợp với công việc không cần đọc và ghi từng item theo chunk, ví dụ:

- Xóa file tạm.
- Tạo thư mục hoặc chuẩn bị dữ liệu đầu vào.
- Chạy một câu lệnh cập nhật hoặc stored procedure.
- Thực hiện một thao tác tổng hợp đơn giản.

Một tasklet triển khai phương thức `execute`. Phương thức trả về `RepeatStatus.FINISHED` khi hoàn tất hoặc `RepeatStatus.CONTINUABLE` khi cần được gọi tiếp. Trong một `TaskletStep`, Spring Batch quản lý giao dịch cho từng lần gọi tasklet theo cấu hình của step.

Ví dụ khai báo một step dùng tasklet:

```java
@Bean
Step cleanupStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager) {

    return new StepBuilder("cleanupStep", jobRepository)
            .tasklet((contribution, chunkContext) -> {
                // Thực hiện công việc dọn dẹp tại đây.
                return RepeatStatus.FINISHED;
            }, transactionManager)
            .build();
}
```

Hãy chọn chunk khi công việc xử lý một tập item theo chu trình read-process-write. Chọn tasklet khi công việc là một thao tác hoặc một đoạn xử lý do ứng dụng tự điều khiển.

## 7. JobRepository: nơi lưu metadata của Spring Batch

`JobRepository` là thành phần hạ tầng rất quan trọng. Nó lưu metadata về JobInstance, JobExecution, StepExecution, JobParameters và ExecutionContext. Nhờ metadata này, Spring Batch có thể theo dõi trạng thái, thống kê kết quả và hỗ trợ restart.

Trong một ứng dụng thực tế, JobRepository thường được cấu hình để lưu dữ liệu vào cơ sở dữ liệu thông qua các bảng metadata của Spring Batch. Các bảng này khác với bảng nghiệp vụ mà ứng dụng dùng để lưu đơn hàng, khách hàng hoặc giao dịch.

Ví dụ, ứng dụng có thể có:

- Cơ sở dữ liệu nghiệp vụ chứa bảng `orders`.
- Các bảng metadata của Spring Batch chứa thông tin job, step, execution và trạng thái checkpoint.

Hai nhóm dữ liệu có thể nằm cùng một database hoặc ở các database khác nhau, tùy cấu hình. Cần bảo đảm schema metadata đã được khởi tạo đúng với phiên bản Spring Batch đang sử dụng và datasource/transaction manager được cấu hình nhất quán.

`JobRepository` không phải nơi lưu toàn bộ dữ liệu đầu vào hoặc dữ liệu nghiệp vụ đã xử lý. Nó lưu thông tin quản lý thực thi và trạng thái cần thiết cho framework.

## 8. JobLauncher: khởi chạy Job

`JobLauncher` nhận một Job cùng `JobParameters` và yêu cầu Spring Batch thực thi job đó. Thành phần gọi có thể là ứng dụng, REST endpoint, scheduler hoặc một thành phần điều phối khác.

Ví dụ:

```java
JobExecution execution = jobLauncher.run(importJob, parameters);
```

JobLauncher phối hợp với JobRepository để tạo hoặc tìm JobInstance, ghi nhận JobExecution và bắt đầu quá trình thực thi. Cách thực thi đồng bộ hay bất đồng bộ phụ thuộc cấu hình launcher và executor được sử dụng.

Khi khởi chạy, ứng dụng có thể gặp các trường hợp như job cùng JobInstance đang chạy, JobInstance đã hoàn tất hoặc tham số không hợp lệ. Vì thế, nơi gọi JobLauncher cần xử lý các ngoại lệ phù hợp và ghi nhận kết quả khởi chạy.

## 9. JobExplorer, JobOperator và JobRegistry

Đây là các thành phần hỗ trợ tra cứu và quản lý job khi ứng dụng có nhu cầu vận hành phong phú hơn.

| Thành phần | Vai trò |
|---|---|
| `JobExplorer` | Tra cứu metadata đã lưu, ví dụ tìm JobInstance, JobExecution hoặc StepExecution và xem trạng thái thực thi. |
| `JobOperator` | Cung cấp các thao tác vận hành job ở mức cao hơn, chẳng hạn khởi chạy, khởi động lại hoặc yêu cầu dừng một execution theo API được phiên bản hỗ trợ. |
| `JobRegistry` | Đăng ký và tra cứu các Job theo tên; hữu ích khi job được đăng ký hoặc lựa chọn động. |

Không phải ứng dụng nào cũng cần gọi trực tiếp cả ba thành phần này. Với ứng dụng nhỏ, JobLauncher và JobRepository có thể đã đủ cho luồng chạy cơ bản. Khi cần màn hình theo dõi, endpoint quản trị hoặc cơ chế điều phối động, JobExplorer, JobOperator và JobRegistry trở nên hữu ích hơn.

## 10. PlatformTransactionManager: quản lý giao dịch

Trong chunk processing, Spring Batch cần xác định khi nào bắt đầu, commit hoặc rollback giao dịch. `PlatformTransactionManager` là abstraction của Spring dùng để quản lý các giao dịch đó.

Một step thường nhận transaction manager phù hợp với tài nguyên mà step sử dụng. Ví dụ, nếu writer ghi vào cơ sở dữ liệu quan hệ qua JDBC, transaction manager phải quản lý đúng datasource đó.

Khi một chunk thất bại trước khi commit, giao dịch của chunk có thể được rollback. Điều này giúp tránh trạng thái ghi dở dang trong tài nguyên được quản lý bởi giao dịch. Tuy nhiên, nếu processor hoặc writer gọi một hệ thống bên ngoài không tham gia cùng giao dịch, thao tác bên ngoài có thể không tự động được hoàn tác. Khi tích hợp nhiều hệ thống, cần thiết kế xử lý lỗi, retry và tính idempotent phù hợp.

## 11. ExecutionContext: lưu trạng thái để tiếp tục xử lý

`ExecutionContext` là vùng lưu trữ key-value gắn với một JobExecution hoặc StepExecution. Spring Batch dùng nó để lưu trạng thái cần thiết giữa các lần thực thi, đặc biệt là thông tin checkpoint của reader có hỗ trợ restart.

Ví dụ, một reader có thể lưu vị trí đã đọc trong file. Nếu step thất bại sau một số chunk đã commit, lần restart có thể dùng trạng thái đã lưu để tiếp tục từ vị trí phù hợp thay vì đọc lại từ đầu.

Có hai phạm vi thường gặp:

- **Job ExecutionContext**: trạng thái ở phạm vi toàn job, có thể được các step sau sử dụng.
- **Step ExecutionContext**: trạng thái riêng của một step, thường dùng cho checkpoint của reader hoặc writer trong step đó.

ExecutionContext được lưu cùng metadata thực thi trong JobRepository. Chỉ nên lưu những giá trị nhỏ, cần thiết để tiếp tục công việc; không nên đưa toàn bộ tập dữ liệu lớn vào đây. Các giá trị cần được serializer của Spring Batch hỗ trợ.

## 12. Listener: móc xử lý ở các thời điểm trong vòng đời

Listener cho phép ứng dụng chạy logic bổ sung khi một sự kiện trong job hoặc step xảy ra. Chúng hữu ích cho logging, đo thời gian, ghi audit hoặc gửi thông tin trạng thái.

Một số listener thường gặp:

| Listener | Thời điểm sử dụng |
|---|---|
| `JobExecutionListener` | Trước và sau khi một JobExecution chạy. |
| `StepExecutionListener` | Trước và sau khi một StepExecution chạy. |
| `ChunkListener` | Trước và sau một chunk, hoặc khi chunk gặp lỗi theo các callback tương ứng. |
| `ItemReadListener` | Trước/sau khi đọc item hoặc khi đọc gặp lỗi. |
| `ItemProcessListener` | Trước/sau khi xử lý item hoặc khi xử lý gặp lỗi. |
| `ItemWriteListener` | Trước/sau khi ghi chunk hoặc khi ghi gặp lỗi. |

Ví dụ, `JobExecutionListener` có thể ghi thời điểm bắt đầu trong `beforeJob` và ghi kết quả trong `afterJob`. Listener nên tập trung vào hành vi bổ trợ. Quy tắc nghiệp vụ chính và luồng điều khiển nên được đặt ở job, step, tasklet hoặc processor phù hợp.

## 13. @StepScope và @JobScope

Một số bean cần được tạo với dữ liệu chỉ có khi job bắt đầu, chẳng hạn đường dẫn file nằm trong JobParameters hoặc một giá trị được lưu trong ExecutionContext. `@StepScope` và `@JobScope` giúp trì hoãn việc khởi tạo bean để có thể truy cập các giá trị theo phạm vi thực thi.

- `@StepScope` tạo bean theo phạm vi một step execution. Đây là lựa chọn thường gặp cho reader, processor hoặc writer cần tham số của step.
- `@JobScope` tạo bean theo phạm vi một job execution. Nó phù hợp với đối tượng cần dùng chung trong phạm vi job và cần truy cập job parameter hoặc job execution context.

Ví dụ, một reader có thể nhận tên file từ job parameter bằng biểu thức late binding:

```java
@Bean
@StepScope
FlatFileItemReader<String> inputReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {
    // Cấu hình reader sử dụng inputFile tại đây.
    return new FlatFileItemReaderBuilder<String>()
            .name("inputReader")
            .resource(new FileSystemResource(inputFile))
            .lineMapper((line, lineNumber) -> line)
            .build();
}
```

Do bean scope gắn với vòng đời thực thi, cần khai báo các bean này theo cách Spring Batch có thể quản lý scope. Không nên đọc JobParameters trong lúc tạo một singleton bean thông thường nếu giá trị đó chỉ tồn tại khi job được khởi chạy.

## 14. Ví dụ ghép Job, Step và các thành phần chunk

Ví dụ dưới đây minh họa cấu hình theo API Spring Batch 5 trở lên. `reader` và `writer` được giả định là các bean đã khai báo ở nơi khác; ví dụ tập trung vào cách ghép các thành phần thành một job.

```java
@Configuration
public class ImportJobConfiguration {

    @Bean
    Job importJob(JobRepository jobRepository, Step importStep) {
        return new JobBuilder("importJob", jobRepository)
                .start(importStep)
                .build();
    }

    @Bean
    Step importStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            ItemReader<String> reader,
            ItemProcessor<String, String> processor,
            ItemWriter<String> writer) {

        return new StepBuilder("importStep", jobRepository)
                .<String, String>chunk(100, transactionManager)
                .reader(reader)
                .processor(processor)
                .writer(writer)
                .build();
    }

    @Bean
    ItemProcessor<String, String> normalizeProcessor() {
        return String::trim;
    }
}
```

Trong ví dụ:

1. `importJob` định nghĩa job có tên `importJob` và bắt đầu bằng `importStep`.
2. `importStep` là chunk-oriented step với chunk size bằng 100.
3. `reader` cung cấp từng chuỗi đầu vào.
4. `normalizeProcessor` loại bỏ khoảng trắng ở đầu và cuối chuỗi.
5. `writer` nhận các chuỗi đã xử lý trong từng chunk và ghi chúng đến đích.
6. `JobRepository` lưu metadata; `PlatformTransactionManager` quản lý giao dịch cho chunk.

Khi khởi chạy, thành phần gọi tạo JobParameters rồi truyền job và parameters cho JobLauncher:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("inputFile", "data/input.txt", true)
        .addString("businessDate", "2026-11-15", true)
        .toJobParameters();

JobExecution execution = jobLauncher.run(importJob, parameters);
```

Đoạn cấu hình này giả định `JobRepository`, `PlatformTransactionManager`, `JobLauncher` và các bean reader/writer đã được cấu hình trong application context. Cách cấu hình hạ tầng cụ thể phụ thuộc việc ứng dụng dùng Spring Boot hay cấu hình Spring Batch trực tiếp, cũng như phiên bản framework.

## 15. Điều gì xảy ra khi job thất bại và được restart?

Khả năng restart là một lý do quan trọng để sử dụng Spring Batch. Khi một job thất bại, metadata trong JobRepository cho biết JobInstance, JobExecution và step nào đã chạy, trạng thái hiện tại ra sao. ExecutionContext có thể chứa checkpoint đã lưu tại những ranh giới commit.

Khi khởi động lại với cùng các identifying JobParameters, Spring Batch có thể tạo JobExecution mới cho JobInstance hiện có và tiếp tục theo quy tắc restart của job/step. Step đã hoàn tất có thể được bỏ qua trong lần restart nếu cấu hình và trạng thái cho phép; step thất bại có thể được chạy lại. Khả năng tiếp tục chính xác còn phụ thuộc reader/writer, checkpoint, transaction và thiết kế của ứng dụng.

Một số nguyên tắc cần nhớ:

- Chọn identifying JobParameters phản ánh đúng một đơn vị công việc nghiệp vụ.
- Dùng reader/writer có khả năng lưu và khôi phục trạng thái khi cần restart.
- Thiết kế thao tác ghi có tính idempotent khi có khả năng một phần công việc phải được thực hiện lại.
- Không giả định mọi thao tác gọi API hoặc hệ thống bên ngoài đều được rollback cùng giao dịch cơ sở dữ liệu.
- Phân biệt restart một JobInstance đã thất bại với việc tạo JobInstance mới bằng tham số định danh khác.

## 16. Phân biệt các thành phần dễ nhầm

| Cặp khái niệm | Cách phân biệt |
|---|---|
| `Job` và `JobInstance` | Job là định nghĩa; JobInstance là một lần xử lý logic được xác định bởi identifying parameters. |
| `JobInstance` và `JobExecution` | Một JobInstance có thể có nhiều JobExecution qua các lần chạy hoặc restart. |
| `Step` và `StepExecution` | Step là định nghĩa một giai đoạn; StepExecution là một lần thực thi giai đoạn đó. |
| `ItemProcessor` và `ItemWriter` | Processor biến đổi hoặc lọc từng item; writer ghi các item đã xử lý theo chunk. |
| Chunk và Tasklet | Chunk tổ chức read-process-write theo nhóm; tasklet thực hiện một tác vụ do ứng dụng định nghĩa. |
| `JobRepository` và `ExecutionContext` | JobRepository lưu metadata thực thi; ExecutionContext là vùng trạng thái key-value thuộc execution và được lưu thông qua repository. |
| `JobLauncher` và `JobOperator` | JobLauncher khởi chạy job; JobOperator cung cấp thêm các thao tác quản lý job ở mức vận hành. |

Khi đọc một ứng dụng Spring Batch, hãy bắt đầu từ bean `Job` để biết quy trình gồm những step nào. Sau đó mở từng `Step` để xác định step dùng chunk hay tasklet, reader lấy dữ liệu từ đâu, processor áp dụng quy tắc gì và writer ghi đến đâu. Cuối cùng, xem JobParameters, JobRepository, transaction manager và listener để hiểu cách job được khởi chạy, theo dõi và khôi phục khi có lỗi.
