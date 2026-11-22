# Flow split và join

Trong Spring Batch, một Job không nhất thiết phải chạy tất cả Step theo một chuỗi tuần tự. Khi các nhóm công việc độc lập, Job có thể chia luồng thành nhiều nhánh để thực thi đồng thời, sau đó chờ các nhánh hoàn tất rồi tiếp tục phần công việc chung. Cơ chế này được gọi là **split và join**.

`split` chia một flow thành nhiều flow con có thể chạy song song thông qua `TaskExecutor`. Điểm **join** là ranh giới nơi flow điều phối chờ các nhánh kết thúc trước khi chuyển sang Step tiếp theo. Cách tổ chức này giúp giảm thời gian tổng thể khi các nhánh có thể chạy độc lập, nhưng cần kiểm soát tài nguyên, dữ liệu dùng chung, transaction và cách xử lý khi một nhánh thất bại.

## 1. Split và join là gì?

Giả sử một Job tạo báo cáo cuối ngày. Sau khi xác thực ngày nghiệp vụ, Job cần thực hiện hai nhóm việc độc lập:

- Cập nhật số dư và tổng hợp giao dịch.
- Làm mới dữ liệu khách hàng và tính các chỉ số phân khúc.

Hai nhóm này có thể chạy đồng thời. Khi cả hai hoàn tất, Job mới tổng hợp kết quả và xuất báo cáo.

```text
                    prepareStep
                         |
                         v
                       SPLIT
                      /     \
                     /       \
                    v         v
              accountFlow  customerFlow
                    |         |
                    v         v
              calculate   refreshCustomer
                    |         |
                    v         v
              aggregate   calculateSegment
                    |         |
                    +----+----+
                         |
                         v
                        JOIN
                         |
                         v
                  generateReportStep
                         |
                         v
                        END
```

Ở đây:

- **Split:** bắt đầu thực thi các flow con theo cơ chế song song.
- **Flow branch:** một nhánh gồm một hoặc nhiều Step nối tiếp nhau.
- **Join:** đợi các flow branch kết thúc để xác định kết quả của phần split.
- **Step sau join:** chỉ bắt đầu sau khi phần split đã hoàn tất và flow điều khiển cho phép tiếp tục.

Join là một điểm đồng bộ trong luồng điều khiển. Nó không tự gộp dữ liệu, không hợp nhất transaction của các nhánh và cũng không tự giải quyết xung đột khi nhiều nhánh cùng ghi một bảng.

## 2. Khi nào nên dùng split và join?

Split phù hợp khi một Job có những nhóm công việc độc lập và có thể chạy đồng thời mà không phụ thuộc kết quả tức thời của nhau.

Ví dụ:

- Tạo nhiều báo cáo riêng cho các miền dữ liệu độc lập.
- Làm mới cache khách hàng trong khi một nhánh khác tổng hợp giao dịch.
- Đọc và xử lý dữ liệu từ các nguồn độc lập.
- Chuẩn bị dữ liệu cho nhiều hệ thống đích, sau đó chạy một Step tổng hợp kết quả.
- Chạy các kiểm tra độc lập trước khi đưa ra quyết định cuối cùng.

Không nên dùng split nếu nhánh B cần dữ liệu do nhánh A tạo ra trong cùng lần chạy. Khi có dependency dữ liệu, cần đặt nhánh phụ thuộc sau join hoặc tổ chức các Step theo thứ tự tuần tự.

Một Job có thể kết hợp cả ba kiểu: Step tuần tự trước split, nhiều flow chạy song song, rồi một Step tuần tự sau join.

## 3. Khai báo split flow trong Spring Batch 5

Spring Batch cung cấp API `split(TaskExecutor)` trên Job/Flow builder. Các flow được thêm vào bằng `add(...)` sẽ được thực thi qua executor.

Ví dụ, Job có một Step chuẩn bị, hai flow độc lập và một Step tổng hợp sau join:

```java
@Bean
Job endOfDayJob(
        JobRepository jobRepository,
        Step prepareStep,
        Flow accountFlow,
        Flow customerFlow,
        Step generateReportStep,
        TaskExecutor batchFlowExecutor) {

    return new JobBuilder("endOfDayJob", jobRepository)
            .start(prepareStep)
            .split(batchFlowExecutor)
            .add(accountFlow, customerFlow)
            .next(generateReportStep)
            .end()
            .build();
}
```

Trong flow này, `prepareStep` chạy trước. Sau đó, `accountFlow` và `customerFlow` được khởi chạy qua `batchFlowExecutor`. Khi phần split kết thúc, Job chuyển tới `generateReportStep` theo flow đã khai báo.

Mỗi nhánh có thể chứa một Step hoặc một chuỗi Step:

```java
@Bean
Flow accountFlow(
        Step calculateAccountBalanceStep,
        Step summarizeAccountStep) {

    return new FlowBuilder<SimpleFlow>("accountFlow")
            .start(calculateAccountBalanceStep)
            .next(summarizeAccountStep)
            .build();
}

@Bean
Flow customerFlow(
        Step refreshCustomerStep,
        Step calculateSegmentStep) {

    return new FlowBuilder<SimpleFlow>("customerFlow")
            .start(refreshCustomerStep)
            .next(calculateSegmentStep)
            .build();
}
```

Trong mỗi nhánh, các Step vẫn chạy tuần tự theo `.start()` và `.next()`. Hai nhánh độc lập mới được chạy song song với nhau.

## 4. TaskExecutor quyết định cách chạy song song

`split()` cần một `TaskExecutor` để thực thi các flow branch. Executor quyết định cách các tác vụ được đưa vào thread và giới hạn số lượng công việc đồng thời.

Trong ví dụ đơn giản, có thể dùng `SimpleAsyncTaskExecutor`. Tuy nhiên, trong ứng dụng production, nên cân nhắc một thread pool có giới hạn để kiểm soát tài nguyên.

```java
@Bean
ThreadPoolTaskExecutor batchFlowExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(8);
    executor.setThreadNamePrefix("batch-flow-");
    return executor;
}
```

Với cấu hình trên, executor có tối đa bốn thread hoạt động đồng thời và hàng đợi có sức chứa tám tác vụ. Nếu Job chỉ có hai nhánh, tối đa hai nhánh được chạy trong lần split đó. Nếu có nhiều flow hơn số thread, các flow còn lại phải chờ theo chính sách của executor.

Số thread không nên được chọn chỉ dựa trên số CPU. Nếu các nhánh chủ yếu chờ database hoặc HTTP, có thể cần cấu hình khác với công việc tính toán CPU-bound. Cần tính đến connection pool, quota service ngoài, giới hạn database và tải của các Job khác cùng chạy.

## 5. Join xảy ra khi nào?

Join là điểm đồng bộ sau khi tất cả flow branch trong split đã kết thúc. Step sau join chỉ được thực thi khi phần split trả kết quả về cho flow cha.

Ví dụ:

```text
Branch A: A1 -> A2 ----------- done
                  \          /
                   \        /
                    JOIN
                   /        \
                  /          \
Branch B: B1 -> B2 ----------- done
                    |
                    v
              aggregateStep
```

Nếu Branch A hoàn tất nhanh hơn Branch B, Job vẫn chờ Branch B. `aggregateStep` không chạy ngay khi A xong; nó chỉ chạy sau khi mọi nhánh của split đã kết thúc và kết quả flow cho phép tiếp tục.

Do đó, thời gian của phần split thường bị chi phối bởi nhánh chậm nhất, cộng thêm chi phí điều phối. Nếu thời lượng các nhánh chênh lệch lớn, một nhánh rất chậm có thể làm giảm lợi ích của việc chạy song song.

## 6. Split/join không phải partitioning

Hai cơ chế đều có thể chạy song song nhưng giải quyết những vấn đề khác nhau.

| Tiêu chí | Split và join | Partitioning |
|---|---|---|
| Đơn vị chia | Các flow branch, mỗi nhánh có thể gồm nhiều Step khác nhau | Một Step được chia thành nhiều partition |
| Mục tiêu | Chạy các nhóm công việc độc lập đồng thời | Chia dữ liệu của cùng một kiểu xử lý thành các phần |
| Thành phần chính | `Flow`, `split(TaskExecutor)`, `add(...)` | `Partitioner`, manager Step, worker Step, `PartitionHandler` |
| Dữ liệu đầu vào | Mỗi nhánh có thể dùng nguồn và JobParameters/context phù hợp | Mỗi partition thường nhận phạm vi dữ liệu qua StepExecutionContext |
| Execution | Các Step trong các flow branch có StepExecution riêng | Mỗi partition tạo worker StepExecution riêng |
| Ví dụ | Tính số dư song song với làm mới hồ sơ khách hàng | Chia bảng khách hàng thành các dải ID để nhiều worker cùng import |

Nếu cần chạy ba quy trình khác nhau đồng thời, split flow thường dễ diễn đạt hơn. Nếu cần chạy cùng một worker Step trên nhiều dải dữ liệu, partitioning thường phù hợp hơn.

## 7. Mỗi nhánh có StepExecution và transaction riêng

Các flow branch dùng chung JobExecution của Job cha, nhưng mỗi lần thực thi Step có `StepExecution` riêng. Các transaction được quản lý theo từng Step và từng chunk, tùy cấu hình của Step.

Ví dụ:

```text
JobExecution
    |
    +---- prepareStep StepExecution
    |
    +---- accountFlow
    |        +---- calculateBalanceStep StepExecution
    |        +---- summarizeAccountStep StepExecution
    |
    +---- customerFlow
    |        +---- refreshCustomerStep StepExecution
    |        +---- calculateSegmentStep StepExecution
    |
    +---- generateReportStep StepExecution
```

Các Step trong hai nhánh có thể commit độc lập. Nếu `calculateBalanceStep` đã commit nhưng `calculateSegmentStep` thất bại, dữ liệu đã commit của nhánh tài khoản không tự động rollback. Join không tạo một transaction bao trùm mọi branch.

Nếu nghiệp vụ yêu cầu hoàn tác dữ liệu của nhánh đã thành công khi nhánh khác thất bại, cần thiết kế thao tác bù trừ, trạng thái trung gian hoặc saga. Không nên dựa vào split/join để cung cấp atomicity giữa nhiều transaction.

## 8. Truyền dữ liệu vào và ra khỏi các nhánh

Các nhánh song song thường cần dùng chung một mã lô, ngày nghiệp vụ hoặc snapshot ID. Những giá trị do caller cung cấp khi launch Job có thể được truyền qua `JobParameters` và được đọc ở mỗi Step bằng `@StepScope`.

Ví dụ đọc JobParameter:

```java
@Bean
@StepScope
Tasklet accountTasklet(
        @Value("#{jobParameters['businessDate']}") LocalDate businessDate,
        AccountService accountService) {

    return (contribution, chunkContext) -> {
        accountService.calculateFor(businessDate);
        return RepeatStatus.FINISHED;
    };
}
```

Nếu các nhánh tạo ra dữ liệu mà Step sau join cần tổng hợp, nên ghi kết quả vào một kho dữ liệu bền vững theo khóa chung, chẳng hạn `batchId`. Sau join, Step tổng hợp đọc kết quả của tất cả nhánh bằng khóa đó.

```text
                 JobParameters: batchId
                         |
                +--------+--------+
                |                 |
                v                 v
          accountFlow        customerFlow
                |                 |
                v                 v
         account_summary   customer_summary
                |                 |
                +--------+--------+
                         |
                         v
                    JOIN POINT
                         |
                         v
                 generateReportStep
                  đọc theo batchId
```

Không nên để nhiều nhánh ghi cùng một key trong `JobExecutionContext` mà không có cơ chế phối hợp. JobExecutionContext thuộc JobExecution chung, nên việc nhiều thread đồng thời cập nhật có thể gây ghi đè hoặc trạng thái khó dự đoán. Nếu cần chia sẻ kết quả, ưu tiên bảng kết quả riêng theo branch hoặc key riêng và đọc sau join.

## 9. Điều gì xảy ra khi một nhánh thất bại?

Nếu một Step trong một flow branch thất bại và flow không có transition xử lý lỗi, nhánh đó thường kết thúc với trạng thái lỗi. Split flow tổng hợp kết quả của các nhánh; Job thường thất bại và Step sau join không chạy.

Ví dụ:

```text
accountFlow:   A1 -> A2 -> COMPLETED
                              \
                               JOIN -> FAILED
                              /
customerFlow:  C1 -> C2 -> FAILED

generateReportStep: không chạy trong luồng thành công thông thường
```

Các nhánh khác có thể đã hoàn tất và commit dữ liệu trước khi lỗi được ghi nhận. Không nên giả định Spring Batch tự hủy mọi nhánh đang chạy và rollback mọi thay đổi đã commit khi một nhánh thất bại. Cách các nhánh đang hoạt động được kết thúc còn phụ thuộc executor, thời điểm lỗi và cơ chế điều phối; cần thiết kế để mỗi branch có thể kết thúc an toàn.

Nếu muốn xử lý lỗi trong một nhánh, có thể khai báo transition trong flow đó, ví dụ chuyển từ Step thất bại sang Step ghi nhận lỗi hoặc thực hiện bù trừ. Kết quả cuối cùng của flow branch sẽ ảnh hưởng tới trạng thái mà split trả về.

### Dùng ExitStatus để định tuyến trong từng nhánh

```java
@Bean
Flow accountFlow(
        Step calculateBalanceStep,
        Step recordAccountFailureStep,
        Step summarizeAccountStep) {

    return new FlowBuilder<SimpleFlow>("accountFlow")
            .start(calculateBalanceStep)
                .on("FAILED").to(recordAccountFailureStep)
            .from(calculateBalanceStep)
                .on("COMPLETED").to(summarizeAccountStep)
            .end();
}
```

Đây là ví dụ minh họa flow transition theo ExitStatus. Cần khai báo các transition cần thiết và quyết định flow cuối cùng nên được xem là thành công hay thất bại theo quy tắc nghiệp vụ. Không nên chuyển một lỗi quan trọng thành `COMPLETED` chỉ để Job tiếp tục mà không có trạng thái hoặc báo cáo phản ánh chính xác kết quả.

## 10. Restart Job có split flow

Spring Batch lưu JobExecution và StepExecution của từng nhánh trong `JobRepository`. Khi Job thất bại và được restart với cùng identifying JobParameters, framework sử dụng metadata đã lưu để xác định các Step cần thực thi lại.

Thông thường:

- Step đã `COMPLETED` được bỏ qua khi restart, trừ khi được cấu hình `allowStartIfComplete(true)`.
- Step thất bại có thể được chạy lại nếu Job và Step cho phép restart.
- Chunk-oriented Step có reader hỗ trợ `ItemStream` có thể khôi phục checkpoint trong StepExecutionContext.
- Các Step thuộc nhánh khác đã hoàn tất có thể không cần chạy lại.

Ví dụ:

```text
Lần chạy đầu:
  accountFlow:   A1 COMPLETED, A2 COMPLETED
  customerFlow: C1 COMPLETED, C2 FAILED
  Job: FAILED

Restart cùng JobInstance:
  accountFlow:   các Step đã COMPLETED thường được bỏ qua
  customerFlow: C1 được bỏ qua, C2 được chạy lại
  Sau khi các nhánh hoàn tất: join -> generateReportStep
```

Hành vi cụ thể còn phụ thuộc flow transition, trạng thái StepExecution và cách split được cấu hình. Hãy kiểm thử restart trong trường hợp một nhánh thất bại sau khi nhánh khác đã commit, thay vì chỉ kiểm thử trường hợp mọi nhánh thành công.

Nếu một Step đã hoàn thành cần chạy lại sau restart, `allowStartIfComplete(true)` có thể được dùng, nhưng chỉ khi tác vụ idempotent hoặc có cơ chế chống tác dụng phụ trùng. Ví dụ gửi email, thanh toán hoặc tạo file cần có business key ổn định để nhận diện cùng hành động.

## 11. Tính độc lập và idempotency của các nhánh

Để split có lợi và an toàn, mỗi nhánh nên có đầu vào, đầu ra và quyền sở hữu dữ liệu rõ ràng.

Các nguyên tắc thiết kế:

1. Mỗi nhánh chỉ phụ thuộc vào dữ liệu đã sẵn sàng trước split hoặc dữ liệu riêng của nhánh.
2. Các nhánh không ghi đè cùng một bản ghi hoặc cùng một key context nếu không có đồng bộ rõ ràng.
3. Tác dụng phụ bên ngoài transaction cần idempotency key ổn định.
4. Kết quả nhánh cần lưu bền vững để Step sau join có thể đọc và đối soát.
5. Nếu một nhánh thất bại, các nhánh đã hoàn tất không nên cần chạy lại chỉ để tái tạo kết quả giống hệt.

Ví dụ, `accountFlow` ghi `account_summary` theo `batchId`, còn `customerFlow` ghi `customer_summary` theo cùng `batchId`. Sau join, `generateReportStep` đọc cả hai bảng. Cách chia này giúp mỗi nhánh sở hữu bảng đầu ra riêng và giảm tranh chấp ghi.

Nếu cả hai nhánh cập nhật cùng một bảng tổng hợp, cần khóa hoặc phân chia phạm vi ghi hợp lý. Nếu không, chạy song song có thể tạo lock contention, deadlock hoặc ghi đè kết quả.

## 12. Giới hạn tài nguyên và hiệu năng

Split giúp giảm thời gian bằng cách chạy nhánh đồng thời, nhưng không làm tổng công việc biến mất. Tải database, CPU, bộ nhớ, connection pool và service ngoài có thể tăng lên.

Khi chọn số thread, cần xem:

- Số flow branch có thể chạy đồng thời.
- Thời gian và mức sử dụng CPU của mỗi branch.
- Số connection database mà mỗi Step có thể giữ.
- Quota và giới hạn concurrency của API bên ngoài.
- Tải của các Job khác chạy cùng ứng dụng.
- Dung lượng heap và số lượng object được tạo khi nhiều Step chạy cùng lúc.

Ví dụ, nếu mỗi branch có chunk writer giữ một database connection và có bốn branch đồng thời, connection pool phải có đủ khả năng phục vụ chúng cùng các request khác. Tăng thread khi pool chỉ có hai connection có thể làm các branch chờ nhau và không tăng throughput.

Không nên dùng executor không giới hạn cho Job có nhiều flow hoặc có thể được khởi chạy đồng thời nhiều lần. Thread pool có giới hạn và queue phù hợp giúp kiểm soát tải, nhưng cần chọn rejection policy và shutdown behavior phù hợp với cách Job được điều phối.

## 13. Thread safety của bean trong các flow song song

Các Step trong những branch có thể chạy trên thread khác nhau. Spring singleton bean được chia sẻ giữa các thread, vì vậy processor, listener, service hoặc helper không nên giữ trạng thái mutable theo từng execution trong field dùng chung.

Ví dụ không an toàn:

```java
@Component
public class UnsafeAccountProcessor
        implements ItemProcessor<AccountInput, AccountResult> {

    private AccountInput currentItem;

    @Override
    public AccountResult process(AccountInput item) {
        currentItem = item;
        return calculate(currentItem);
    }
}
```

Nếu nhiều Step hoặc nhiều thread dùng chung processor, `currentItem` có thể bị ghi đè. Nên dùng biến cục bộ và chỉ giữ dependency bất biến trong field:

```java
@Component
public class AccountProcessor
        implements ItemProcessor<AccountInput, AccountResult> {

    private final AccountCalculationService calculationService;

    public AccountProcessor(AccountCalculationService calculationService) {
        this.calculationService = calculationService;
    }

    @Override
    public AccountResult process(AccountInput item) {
        return calculationService.calculate(item);
    }
}
```

Reader hoặc writer có trạng thái riêng theo Step nên được khai báo với scope phù hợp, thường là `@StepScope`, để mỗi StepExecution có instance hoặc trạng thái riêng theo thiết kế. Cũng cần xác nhận các service, cache và HTTP client được gọi đồng thời là thread-safe.

## 14. Theo dõi split và join

Khi Job có nhiều nhánh, chỉ xem trạng thái tổng thể của Job thường không đủ để tìm bottleneck. Nên theo dõi từng StepExecution trong từng flow branch.

Các thông tin hữu ích:

- JobExecution ID và identifying JobParameters.
- Tên flow branch và tên Step.
- StepExecution ID, BatchStatus và ExitStatus.
- Thời điểm bắt đầu, kết thúc và thời gian chạy.
- Read/write/filter/skip count của chunk Step.
- Exception và số lần retry.
- Số thread đang hoạt động và thời gian chờ executor.
- Thời gian từ lúc split bắt đầu đến khi branch cuối cùng hoàn tất.

Gắn correlation ID hoặc `batchId` vào log của tất cả nhánh để liên kết dữ liệu. Khi điều tra Job chậm, so sánh thời lượng từng branch; nhánh có thời gian dài nhất thường quyết định thời điểm join hoàn tất.

## 15. Kiểm thử split và join

Một Job dùng split cần kiểm thử cả kết quả nghiệp vụ lẫn hành vi điều phối:

- Các nhánh độc lập được thực thi và Step sau join chỉ bắt đầu sau khi tất cả nhánh kết thúc.
- Dữ liệu đầu vào của từng branch được đọc đúng.
- Một nhánh thất bại làm Job có trạng thái phù hợp và Step sau join không chạy nếu flow không xử lý lỗi.
- Transition xử lý lỗi trong branch hoạt động theo ExitStatus đã khai báo.
- Restart sau khi một branch thất bại không thực hiện lại các Step đã hoàn thành ngoài ý muốn.
- Các bean dùng chung không bị race condition khi chạy đồng thời.
- Connection pool và executor đáp ứng mức concurrency cấu hình.

Trong test, có thể dùng executor nhỏ và service giả lập có latch/barrier để xác minh điểm join thực sự đợi các nhánh. Không nên kiểm thử tính song song chỉ bằng cách đo thời gian vì kết quả phụ thuộc máy chạy test và scheduler.

## 16. Các lỗi thường gặp

**Nhầm split/join với partitioning:** split chạy nhiều flow khác nhau; partitioning chia một Step thành nhiều phần dữ liệu cho worker Step.

**Cho rằng join gộp transaction:** mỗi Step/chunk có transaction riêng. Join chỉ đồng bộ flow và không rollback dữ liệu đã commit ở nhánh khác.

**Cho rằng Step sau join chạy ngay khi một nhánh hoàn tất:** join đợi tất cả branch trong split kết thúc.

**Chia nhánh khi có dependency dữ liệu:** nếu một nhánh cần đầu ra của nhánh khác, chạy song song có thể khiến dữ liệu chưa sẵn sàng. Đưa dependency sau join hoặc sắp xếp tuần tự.

**Dùng executor không giới hạn:** có thể tạo quá nhiều thread và làm cạn connection pool hoặc quá tải service phụ thuộc.

**Nhiều nhánh ghi cùng dữ liệu:** dễ tạo race condition, lock contention hoặc deadlock. Xác định quyền sở hữu dữ liệu cho từng branch.

**Cập nhật chung JobExecutionContext từ nhiều thread:** có nguy cơ ghi đè hoặc trạng thái khó dự đoán. Dùng key riêng hoặc kho dữ liệu bền vững theo branch.

**Cho rằng một branch lỗi sẽ rollback branch khác:** transaction độc lập; dữ liệu đã commit của branch thành công vẫn tồn tại.

**Không kiểm thử restart:** trạng thái các Step đã hoàn thành và tác dụng phụ bên ngoài có thể làm kết quả khác dự kiến khi Job chạy lại.

## 17. Quy trình thiết kế split và join

Khi xây dựng Job có flow song song, hãy đi theo các bước:

1. Xác định công việc nào thực sự độc lập và có thể chạy đồng thời.
2. Đặt các bước chuẩn bị chung trước split.
3. Gom các Step phụ thuộc nhau thành từng flow branch riêng.
4. Xác định dữ liệu đầu vào và đầu ra bền vững cho từng branch.
5. Cấu hình `TaskExecutor` có giới hạn phù hợp với tài nguyên hệ thống.
6. Đặt Step tổng hợp hoặc bước tiếp theo sau điểm join.
7. Xác định trạng thái cần xử lý khi một branch thất bại và khai báo transition phù hợp.
8. Thiết kế transaction, idempotency và cơ chế bù trừ cho dữ liệu đã commit.
9. Kiểm thử concurrency, failure và restart trong môi trường đại diện.
10. Theo dõi thời lượng từng branch để tìm nhánh chậm và điều chỉnh tài nguyên.

## Kết luận

`split` cho phép một Job thực thi nhiều flow branch đồng thời thông qua `TaskExecutor`; `join` là điểm chờ các nhánh kết thúc trước khi Job chuyển sang Step tiếp theo. Mỗi branch có các StepExecution và transaction riêng, nên join không tạo transaction chung và không tự hợp nhất dữ liệu. Hãy chỉ chạy song song những công việc độc lập, dùng executor có giới hạn, truyền dữ liệu qua JobParameters hoặc kho dữ liệu bền vững, tránh cập nhật context dùng chung đồng thời và thiết kế idempotency cho các tác dụng phụ. Khi một nhánh thất bại, cần hiểu trạng thái của từng Step và kiểm thử restart để bảo đảm các nhánh đã hoàn tất không bị thực hiện lại ngoài ý muốn.
