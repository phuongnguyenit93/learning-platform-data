# Executor cho parallel flow

Trong Spring Batch, một job có thể chứa nhiều flow độc lập và thực thi chúng đồng thời bằng cơ chế **split flow**. Executor quyết định các flow đó được chạy trên thread nào và có bao nhiêu flow có thể tiến hành cùng lúc. Khi các nhánh hoàn tất, Spring Batch hợp nhất kết quả của chúng để tiếp tục flow chung, chẳng hạn một step tổng hợp ở cuối job.

Executor thường được truyền vào `FlowBuilder.split(TaskExecutor)`. Với `ThreadPoolTaskExecutor`, ứng dụng có thể giới hạn số worker, quản lý queue, đặt tên thread và cấu hình shutdown. Nếu dùng `SyncTaskExecutor`, các nhánh được thực thi trên thread gọi theo cách đồng bộ, nên không có concurrency thực sự.

Executor cho parallel flow điều khiển việc chạy đồng thời **giữa các flow branch**. Nó không tự làm các step bên trong một flow chạy song song, cũng không phải executor dùng để khởi chạy job từ `JobLauncher`. Hiểu rõ phạm vi này giúp cấu hình đúng nơi cần concurrency và tránh tạo quá nhiều thread hoặc quá tải database.

## Parallel flow và vai trò của executor

Một flow có thể gồm nhiều step chạy tuần tự. Khi job cần thực hiện một số nhánh độc lập, có thể dùng `split` để chạy các flow đó đồng thời.

Ví dụ job nhập dữ liệu khách hàng có ba nhánh:

- `customerFlow`: chuẩn hóa và ghi khách hàng.
- `accountFlow`: đồng bộ tài khoản.
- `referenceFlow`: tải dữ liệu tham chiếu.

Sau khi cả ba nhánh hoàn tất, `summaryStep` tổng hợp kết quả.

```text
                         parentJob
                             |
                             v
                        split(executor)
                       /      |       \
                      /       |        \
                     v        v         v
              customerFlow accountFlow referenceFlow
                     |        |         |
               customerStep accountStep referenceStep
                     |        |         |
                     +--------+---------+
                             |
                        join / wait
                             |
                             v
                        summaryStep
                             |
                             v
                        job complete
```

Executor nhận các tác vụ đại diện cho từng flow branch. Các branch có thể bắt đầu trên những worker thread khác nhau. `split` chờ các flow trong nhóm hoàn tất trước khi chuyển sang bước tiếp theo trong flow cha.

Một branch vẫn có thể chứa nhiều step tuần tự:

```text
customerFlow:  extractCustomer -> normalizeCustomer -> writeCustomer
accountFlow:   extractAccount  -> reconcileAccount
referenceFlow: loadCurrency    -> loadCountry
```

Executor của split điều khiển concurrency giữa ba flow trên. Các step trong `customerFlow` vẫn chạy theo thứ tự đã khai báo, trừ khi chính flow đó được thiết kế thêm một cấu trúc song song khác.

## Cấu hình TaskExecutor cho split flow

Trong ứng dụng production, `ThreadPoolTaskExecutor` thường là lựa chọn phù hợp vì tái sử dụng thread và cho phép kiểm soát concurrency.

Ví dụ tạo pool cố định cho tối đa ba flow chạy đồng thời:

```java
@Bean(name = "parallelFlowExecutor")
ThreadPoolTaskExecutor parallelFlowExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(3);
    executor.setMaxPoolSize(3);
    executor.setQueueCapacity(6);
    executor.setThreadNamePrefix("batch-flow-");
    executor.setWaitForTasksToCompleteOnShutdown(true);
    executor.setAwaitTerminationSeconds(60);
    return executor;
}
```

Ý nghĩa các thuộc tính:

| Thuộc tính | Ý nghĩa | Cân nhắc |
| --- | --- | --- |
| `corePoolSize` | Số worker cơ bản của pool | Chọn theo số flow cần chạy thường xuyên |
| `maxPoolSize` | Số worker tối đa | Giới hạn concurrency khi tải tăng |
| `queueCapacity` | Số tác vụ có thể chờ trong queue | Dùng queue hữu hạn để tránh tích lũy quá nhiều công việc chờ |
| `threadNamePrefix` | Prefix tên thread | Giúp nhận diện flow worker trong log và thread dump |
| `waitForTasksToCompleteOnShutdown` | Cho executor chờ task đã nhận khi shutdown | Hữu ích khi flow đang xử lý dữ liệu cần hoàn tất có kiểm soát |
| `awaitTerminationSeconds` | Thời gian chờ tối đa khi shutdown | Chọn theo thời gian dừng hợp lý của ứng dụng |

Với `corePoolSize` và `maxPoolSize` cùng bằng 3, pool có tối đa ba worker thực thi song song. Queue chứa các tác vụ chưa có worker ngay tại thời điểm submit. `queueCapacity` không làm tăng số flow chạy đồng thời; nó chỉ quyết định có bao nhiêu tác vụ có thể chờ.

`ThreadPoolTaskExecutor` được Spring quản lý như một bean nên lifecycle khởi tạo và shutdown do container điều phối. Nếu tự tạo executor bên ngoài Spring, ứng dụng phải tự quản lý khởi tạo và giải phóng resource.

## Khai báo các flow branch

Mỗi branch nên được mô tả thành một `Flow` có tên rõ ràng. Ví dụ:

```java
@Bean
Flow customerFlow(Step extractCustomerStep, Step writeCustomerStep) {
    return new FlowBuilder<SimpleFlow>("customerFlow")
            .start(extractCustomerStep)
            .next(writeCustomerStep)
            .build();
}

@Bean
Flow accountFlow(Step extractAccountStep, Step reconcileAccountStep) {
    return new FlowBuilder<SimpleFlow>("accountFlow")
            .start(extractAccountStep)
            .next(reconcileAccountStep)
            .build();
}

@Bean
Flow referenceFlow(Step loadCurrencyStep, Step loadCountryStep) {
    return new FlowBuilder<SimpleFlow>("referenceFlow")
            .start(loadCurrencyStep)
            .next(loadCountryStep)
            .build();
}
```

Mỗi flow có chuỗi step riêng. Các step có thể dùng chung `JobRepository` và transaction manager của ứng dụng, nhưng cần có tên step duy nhất trong phạm vi job và cấu hình resource phù hợp với việc chạy đồng thời.

## Ghép các flow bằng split(executor)

Sau khi khai báo branch, dùng `FlowBuilder.split(...)` để chỉ định executor thực thi chúng:

```java
@Bean
Flow parallelImportFlow(
        @Qualifier("customerFlow") Flow customerFlow,
        @Qualifier("accountFlow") Flow accountFlow,
        @Qualifier("referenceFlow") Flow referenceFlow,
        @Qualifier("parallelFlowExecutor") TaskExecutor executor) {

    return new FlowBuilder<SimpleFlow>("parallelImportFlow")
            .start(customerFlow)
            .split(executor)
            .add(accountFlow, referenceFlow)
            .build();
}
```

Trong cấu trúc này, flow đầu tiên được đặt bằng `start(customerFlow)`, còn các flow bổ sung được truyền qua `add(...)`. `split(executor)` điều phối nhóm branch bằng executor đã cấu hình.

Sau đó, đưa parallel flow vào job và khai báo step chạy sau khi các nhánh kết thúc:

```java
@Bean
Job parallelImportJob(
        JobRepository jobRepository,
        Flow parallelImportFlow,
        Step summaryStep) {

    return new JobBuilder("parallelImportJob", jobRepository)
            .start(parallelImportFlow)
            .next(summaryStep)
            .end()
            .build();
}
```

`summaryStep` chỉ bắt đầu sau khi parallel flow hoàn tất theo trạng thái flow đã được tổng hợp. Nó có thể đọc các kết quả được lưu ở nơi chia sẻ phù hợp, tổng hợp số liệu hoặc phát báo cáo cuối.

Với ứng dụng có nhiều bean `Flow` hoặc `TaskExecutor`, hãy dùng `@Qualifier` để inject đúng branch và đúng executor. Tránh để Spring chọn nhầm executor mặc định của một tác vụ khác.

## Executor đồng bộ và bất đồng bộ

`TaskExecutor` là abstraction; không phải implementation nào cũng tạo concurrency.

| Implementation | Hành vi | Khi phù hợp |
| --- | --- | --- |
| `SyncTaskExecutor` | Chạy task trên thread gọi | Test flow tuần tự hoặc môi trường không cần concurrency |
| `SimpleAsyncTaskExecutor` | Tạo thread mới cho task; có thể đặt giới hạn concurrency | Tác vụ ít, tải nhỏ hoặc ví dụ đơn giản |
| `ThreadPoolTaskExecutor` | Tái sử dụng worker thread và quản lý queue | Production cần giới hạn tài nguyên và theo dõi tải |
| `ConcurrentTaskExecutor` | Adapter cho executor Java có sẵn | Tích hợp `Executor` đã được quản lý ở nơi khác |

### SyncTaskExecutor

Nếu truyền `SyncTaskExecutor` vào split, các flow được thực thi đồng bộ trên thread gọi. Điều này hữu ích trong test hoặc khi muốn giữ cùng cấu trúc flow nhưng chưa muốn chạy song song.

```java
@Bean
TaskExecutor parallelFlowExecutor() {
    return new SyncTaskExecutor();
}
```

Tên phương thức vẫn là `parallelFlowExecutor` trong ví dụ để phù hợp với cấu hình split, nhưng executor thực tế không tạo thread song song. Có thể đặt tên khác trong dự án để tránh gây hiểu nhầm.

### SimpleAsyncTaskExecutor

`SimpleAsyncTaskExecutor` tạo thread mới cho mỗi task thay vì tái sử dụng pool. Có thể đặt `concurrencyLimit` để giới hạn số task đồng thời. Nó dễ cấu hình nhưng không cung cấp cơ chế tái sử dụng worker giống thread pool; với nhiều job hoặc nhiều flow chạy liên tục, cần cân nhắc chi phí tạo thread và giới hạn tài nguyên.

### ThreadPoolTaskExecutor

`ThreadPoolTaskExecutor` thường phù hợp với ứng dụng server vì pool và queue có giới hạn. Nó cho phép ứng dụng kiểm soát số flow chạy cùng lúc, quan sát thread và cấu hình chính sách từ chối khi quá tải.

## Hiểu đúng core size, max size và queue

Một điểm dễ nhầm của `ThreadPoolTaskExecutor` là pool không nhất thiết tăng thread từ core lên max ngay khi có task mới. Theo hành vi của `ThreadPoolExecutor`, task mới thường được đưa vào queue sau khi số worker đạt core size. Khi queue đầy, pool mới mở rộng worker tới max size; nếu cả pool và queue đều đầy, task có thể bị từ chối.

Ví dụ:

```text
corePoolSize = 2
maxPoolSize  = 4
queueCapacity = 5

Task 1, 2  -> chạy trên 2 worker core
Task 3..7  -> được xếp vào queue
Task tiếp  -> khi queue đầy, pool có thể mở rộng worker lên 3 rồi 4
Task vượt khả năng tiếp nhận -> áp dụng rejection policy
```

Nếu muốn giới hạn concurrency chính xác ở ba flow, cấu hình `corePoolSize=3` và `maxPoolSize=3` là cách dễ hiểu. Queue hữu hạn quyết định số tác vụ có thể đợi nếu có nhiều hơn ba branch được submit.

Không nên dùng queue không giới hạn một cách tùy tiện. Khi có nhiều job cùng chạy, queue lớn có thể tích lũy nhiều flow chờ, làm tăng thời gian hoàn thành và tiêu thụ bộ nhớ. Nếu queue đầy, hãy có chính sách từ chối hoặc back-pressure rõ ràng thay vì để ứng dụng nhận số lượng công việc vượt năng lực.

## Số worker nên chọn như thế nào?

Số worker không nên được chọn chỉ dựa vào số CPU hoặc số branch trong một job. Một flow có thể sử dụng database connection, bộ nhớ, CPU và dịch vụ ngoài trong suốt thời gian chạy.

Các giới hạn cần xem xét:

- **Số branch thực sự độc lập:** không cần tạo pool quá lớn nếu job chỉ có hai branch.
- **Database connection pool:** mỗi branch có thể cần connection trong transaction; pool quá nhỏ khiến các branch chờ nhau.
- **Năng lực database:** nhiều transaction đồng thời có thể tăng lock contention, deadlock và I/O.
- **CPU và memory:** processor nặng CPU hoặc giữ nhiều item có thể làm máy chủ quá tải.
- **Giới hạn hệ thống ngoài:** API, broker hoặc dịch vụ tham chiếu có thể có quota concurrency.
- **Các job khác trên cùng ứng dụng:** executor có thể được dùng chung bởi nhiều job, nên concurrency tổng cao hơn số branch của một job.

Ví dụ, nếu ba branch đều ghi database và connection pool chỉ có hai connection khả dụng cho batch, branch thứ ba có thể phải chờ. Nếu tăng executor lên mười worker, tải cạnh tranh trên database có thể còn lớn hơn mà không tăng throughput.

Một cách chọn ban đầu là đặt worker tối đa theo số branch độc lập dự kiến, sau đó đo thời gian chờ connection, lock, CPU, memory và latency hệ thống ngoài. Điều chỉnh theo số liệu thực tế thay vì tăng thread theo cảm tính.

## Parallel flow khác executor của JobLauncher

Spring Batch có nhiều nơi sử dụng `TaskExecutor`, nhưng mỗi nơi điều khiển một loại concurrency khác nhau.

| Vị trí cấu hình | Điều khiển |
| --- | --- |
| `FlowBuilder.split(taskExecutor)` | Chạy đồng thời các flow branch bên trong một job |
| `TaskExecutorJobLauncher` | Chạy một job execution trên worker thread thay vì thread gọi |
| Executor của multi-threaded step hoặc partition handler | Điều khiển concurrency trong một step theo cơ chế tương ứng |

Ví dụ, một ứng dụng có thể khởi chạy hai `JobInstance` khác nhau bằng `TaskExecutorJobLauncher`, đồng thời mỗi job lại có một parallel flow sử dụng executor riêng. Khi đó, concurrency tổng có thể là số job đang chạy nhân với số branch chạy đồng thời trong mỗi job, nếu tài nguyên cho phép.

Không nên dùng executor của `JobLauncher` với kỳ vọng nó tự chia các branch của flow. Muốn chạy parallel flow, cần truyền executor trực tiếp vào `split(...)`.

## Join: flow tiếp theo chờ các branch

Split flow có một điểm hợp nhất logic sau các branch. Spring Batch cần đợi các flow trong nhóm hoàn tất trước khi tiếp tục phần flow sau split.

Điều này có một số hệ quả:

- `summaryStep` không nên giả định branch nhanh nhất đã đại diện cho toàn bộ kết quả.
- Tổng thời gian split thường bị chi phối bởi branch chậm nhất, cộng thêm chi phí điều phối.
- Một branch có thể hoàn thành sớm và worker được giải phóng trong khi branch khác vẫn chạy.
- Nếu một branch thất bại, trạng thái của split/flow cha phản ánh kết quả tổng hợp theo quy tắc của Spring Batch và flow transition đã cấu hình.

Ví dụ:

```text
customerFlow   [ 10s ] -------- COMPLETED --+
accountFlow    [       35s       ] COMPLETED +--> join --> summaryStep
referenceFlow  [  15s ] ------- COMPLETED --+
```

Trong ví dụ, summary chỉ bắt đầu sau khi `accountFlow` hoàn tất ở giây thứ 35. Tăng số worker không giúp ích nếu branch chậm do query, lock hoặc API latency; cần đo và tối ưu chính branch đó.

## Điều kiện để các branch chạy song song an toàn

Parallel flow chỉ có lợi khi các branch có thể thực hiện độc lập hoặc đã có cơ chế đồng bộ rõ ràng.

Trước khi đưa hai step vào các branch khác nhau, hãy xác định:

1. Hai branch có đọc/ghi cùng bản ghi hoặc cùng file không?
2. Có phụ thuộc dữ liệu đầu ra của branch kia không?
3. Có cần thứ tự thực hiện không?
4. Có thể dùng transaction riêng cho từng step mà vẫn đáp ứng nghiệp vụ không?
5. Khi một branch thất bại, branch khác đã commit dữ liệu gì?
6. Có thể chạy lại branch thất bại mà không tạo duplicate không?

Nếu `accountFlow` cần dữ liệu do `customerFlow` tạo ra, hai flow không độc lập và không nên chạy song song theo cách đó. Hãy đặt `customerFlow` trước, sau đó mới split các nhánh phụ thuộc vào dữ liệu đã sẵn sàng.

## Thread safety của step và các component

Các flow branch chạy trên nhiều thread. Vì vậy, những object được chia sẻ giữa các branch phải an toàn khi truy cập đồng thời.

### Singleton service

Spring service thường là singleton. Nếu service giữ mutable state trong field, nhiều branch có thể cùng sửa state đó và tạo race condition. Service dùng chung nên stateless hoặc dùng cấu trúc đồng bộ/thread-safe phù hợp.

### Reader và writer

Reader hoặc writer có state như cursor, file position, buffer hay counter không nên được chia sẻ đồng thời giữa các branch nếu implementation không hỗ trợ thread-safe. Mỗi branch nên có reader/writer riêng, với resource và tên stream phù hợp.

Ví dụ, hai branch ghi file nên dùng hai đường dẫn output riêng. Nếu cùng ghi vào một file, cần cơ chế đồng bộ và định dạng record rõ ràng; thường dễ kiểm soát hơn nếu mỗi branch ghi file riêng rồi có step hợp nhất sau join.

### StepScope

`@StepScope` tạo bean theo phạm vi `StepExecution`, hữu ích cho reader/writer có state hoặc cần late binding từ job/step parameters. Khi các branch tạo các `StepExecution` riêng, step-scoped component có thể giữ state riêng cho từng execution.

```java
@Bean
@StepScope
FlatFileItemReader<OrderInput> customerReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {
    // Tạo reader riêng cho StepExecution hiện tại.
    return buildReader(inputFile);
}
```

Đảm bảo scope được cấu hình đúng và không lưu state execution-specific trong singleton field bên ngoài step-scoped component.

## Transaction và dữ liệu khi chạy song song

Mỗi step branch có execution và transaction boundary riêng. Split flow không tạo một transaction duy nhất bao trùm tất cả branch.

Ví dụ `customerFlow` commit thành công nhưng `accountFlow` thất bại. Dữ liệu đã commit của customer vẫn tồn tại; Spring Batch không tự rollback các transaction đã hoàn tất ở branch khác chỉ vì một branch thất bại.

```text
customerFlow:  transaction -> COMMIT ------------------+
                                                     |
accountFlow:   transaction -> ROLLBACK                +--> split failure
                                                     |
referenceFlow: transaction -> COMMIT ----------------+
```

Nếu job cần hoàn tác toàn bộ thay đổi của mọi branch khi một branch thất bại, cần thiết kế cơ chế bù trừ hoặc một quy trình staging/publish riêng. Không thể dựa vào split flow để có distributed atomic transaction giữa các step.

Với các branch ghi cùng database, database vẫn quản lý transaction và lock riêng của từng branch. Hãy tránh cập nhật cùng một hàng theo thứ tự không nhất quán, dùng khóa nghiệp vụ rõ ràng và kiểm thử deadlock. Nếu branch chia phạm vi dữ liệu không chồng lấn, khả năng chạy song song an toàn thường cao hơn.

## Trạng thái lỗi và flow transition

Mỗi branch có thể hoàn tất, dừng hoặc thất bại theo logic riêng. Split flow tổng hợp kết quả các branch để flow cha quyết định bước tiếp theo. Cần thiết kế rõ hành vi khi một nhánh thất bại.

Các lựa chọn thường gặp:

- Để lỗi branch làm job thất bại và yêu cầu restart sau khi xử lý nguyên nhân.
- Dùng transition hoặc flow riêng để chạy recovery step khi trạng thái split phù hợp.
- Cho phép một nhánh kết thúc với custom exit code nếu nghiệp vụ định nghĩa rõ trạng thái đó là chấp nhận được.
- Ghi nhận kết quả từng branch để step tổng hợp có thể báo cáo nhánh nào thành công hoặc thất bại.

Không nên catch exception trong tasklet rồi trả `FINISHED` chỉ để split tiếp tục. Làm như vậy có thể biến một nhánh thất bại thành thành công giả. Nếu lỗi có thể retry hoặc skip, cấu hình fault tolerance ở step branch tương ứng.

Với flow có custom exit code, cần kiểm tra cả `BatchStatus` và `ExitStatus`. Flow transition thường dựa trên exit code; test phải xác nhận pattern thực tế khớp như mong đợi.

## Restart của parallel flow

Mỗi branch chứa các `StepExecution` riêng và metadata được lưu trong `JobRepository`. Khi job thất bại, restart dựa trên trạng thái của từng step và quy tắc restart của job.

Một số tình huống:

- Branch A hoàn tất, branch B thất bại: khi restart, Spring Batch có thể bỏ qua step đã hoàn thành và tiếp tục step cần restart theo metadata.
- Branch có nhiều step, một step giữa branch thất bại: các step đã hoàn thành trước đó có thể không chạy lại nếu restart semantics cho phép.
- Một branch ghi dữ liệu ra hệ thống ngoài rồi thất bại trước khi checkpoint được lưu: output có thể được gửi lại; writer cần idempotent.
- Một branch phụ thuộc file do branch khác tạo: file phải tồn tại và có version ổn định khi restart.

Giữ identifying parameters của job ổn định khi restart cùng `JobInstance`. Không thêm timestamp identifying mới chỉ để tránh lỗi chạy trùng, vì điều đó tạo logical instance mới và có thể khiến mọi branch chạy lại từ đầu.

Nếu các branch chia sẻ tài nguyên ngoài database, hãy lưu checkpoint/reference phù hợp và thiết kế cleanup chỉ sau khi mọi nhánh cần resource đó đã hoàn tất.

## Rejection, queue và back-pressure

Executor có giới hạn worker và queue. Khi ứng dụng chạy nhiều job song song, nhiều split flow có thể cùng submit branch vào một pool. Nếu pool và queue đều đầy, executor có thể từ chối task theo rejection policy.

Hãy cân nhắc:

- Dùng queue hữu hạn để giới hạn số flow chờ.
- Chọn rejection policy có hành vi rõ ràng; không âm thầm bỏ tác vụ.
- Bắt và ghi nhận lỗi submit/rejection ở cấp điều phối phù hợp.
- Giới hạn số job đồng thời để tránh nhiều split cùng chiếm hết worker.
- Theo dõi active count, pool size, queue size và số task bị từ chối.

Không nên chọn `CallerRunsPolicy` một cách máy móc. Chính sách này có thể làm thread submit phải chạy task trực tiếp, thay đổi latency và luồng điều phối; trong một số tình huống nó giúp back-pressure, nhưng cần hiểu tác động tới thread gọi `JobStep` hoặc flow engine.

## Nested parallel flow và nguy cơ thread starvation

Một flow branch có thể chứa cấu trúc split khác, nhưng dùng cùng một pool nhỏ cho nhiều tầng song song có thể gây thread starvation.

Ví dụ, các worker của split bên ngoài đều đang chạy branch cha và chờ các tác vụ con được submit vào chính pool đó. Nếu không còn worker rảnh và các task cha chưa kết thúc để giải phóng worker, task con có thể phải chờ vô hạn hoặc tới timeout.

Để giảm rủi ro:

- Tránh lồng nhiều cấp split nếu không cần thiết.
- Dùng executor riêng cho từng tầng khi cần concurrency độc lập.
- Bảo đảm pool có đủ worker cho cấu trúc lồng nhau đã thiết kế.
- Tránh chờ đồng bộ một future được submit vào cùng pool khi toàn bộ worker đang bị chiếm.
- Kiểm thử tải với số branch và job đồng thời gần production.

Không nên tăng pool vô hạn để né starvation; điều đó có thể chuyển vấn đề thành quá tải CPU, database hoặc memory. Thiết kế flow và executor cần xét toàn bộ mô hình concurrency.

## Thread context: logging, security và tracing

Khi flow chuyển sang worker thread, các dữ liệu gắn với thread gọi như `ThreadLocal`, MDC logging context hoặc security context không tự động được sao chép trong mọi cấu hình.

Nếu cần giữ correlation ID hoặc thông tin tracing, có thể cấu hình `TaskDecorator` cho `ThreadPoolTaskExecutor` để sao chép context cần thiết khi submit và khôi phục/xóa context sau khi task kết thúc.

Không nên dựa vào HTTP request context hoặc security context của thread gọi nếu job có thể chạy lâu hơn request. Truyền định danh người yêu cầu hoặc business context cần thiết qua `JobParameters` hay một store được bảo vệ. Không đưa credential hoặc token trực tiếp vào parameter.

## Shutdown khi các branch đang chạy

Khi ứng dụng nhận tín hiệu shutdown, executor cần có chính sách cho các branch đang chạy hoặc đang chờ.

`setWaitForTasksToCompleteOnShutdown(true)` yêu cầu executor chờ các task đã nhận hoàn tất trong quá trình shutdown. `setAwaitTerminationSeconds(...)` giới hạn thời gian chờ. Đây không phải bảo đảm mọi branch luôn hoàn thành: tiến trình có thể bị kill, timeout có thể hết hoặc hệ thống ngoài có thể không phản hồi.

Các job dài cần restart được. Khi shutdown đột ngột, transaction chưa commit sẽ được rollback khi resource được giải phóng; các branch đã commit vẫn giữ dữ liệu. Reader/writer cần lưu checkpoint và side effect ngoài transaction cần idempotency.

Không nên đóng database connection pool hoặc client hệ thống ngoài trước khi các flow worker đã hoàn tất phần việc cần thiết. Thứ tự shutdown của executor, datasource và các client nên được cấu hình theo lifecycle của ứng dụng.

## Kiểm thử parallel flow

Kiểm thử parallel flow cần xác nhận cả kết quả nghiệp vụ lẫn việc các branch thực sự có thể chạy đồng thời. Chỉ assert job `COMPLETED` không chứng minh executor được cấu hình đúng; một `SyncTaskExecutor` vẫn có thể làm job hoàn tất tuần tự.

### Kiểm thử kết quả của từng branch

Dùng integration test chạy job với dữ liệu nhỏ. Sau khi job kết thúc, kiểm tra:

- Mỗi branch có `StepExecution` tương ứng.
- Trạng thái và `ExitStatus` của từng step đúng.
- Dữ liệu nghiệp vụ của từng branch được ghi đúng.
- `summaryStep` chỉ chạy sau khi các branch cần thiết đã hoàn tất.
- Không có duplicate hoặc lost update do chạy đồng thời.

Có thể dùng `JobLauncherTestUtils` để chạy job và `JobExplorer` để đọc metadata. Nếu application context có nhiều job, chỉ định job test bằng `setJob(...)` hoặc inject `@Qualifier` phù hợp.

### Kiểm thử concurrency có kiểm soát

Để xác nhận hai branch chạy đồng thời, có thể dùng một `CountDownLatch` dùng chung trong test. Mỗi branch giảm latch khi bắt đầu rồi chờ branch còn lại tới cùng điểm. Nếu executor thực sự cho phép ít nhất hai worker, cả hai có thể vượt qua barrier; nếu chạy tuần tự, branch đầu sẽ hết timeout.

Ví dụ helper dùng trong test:

```java
public class ParallelStartBarrier {

    private final CountDownLatch ready = new CountDownLatch(2);

    public void awaitBothBranches() throws InterruptedException {
        ready.countDown();
        if (!ready.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException(
                    "Both branches did not reach the barrier in time");
        }
    }
}
```

Hai test tasklet gọi `awaitBothBranches()` ngay khi bắt đầu. Dùng timeout hữu hạn để test không treo nếu executor bị cấu hình tuần tự hoặc chỉ có một worker. Barrier chỉ dùng để kiểm tra đồng thời trong test; không đưa cơ chế chờ này vào tasklet production.

Không nên dựa vào `Thread.sleep` và so sánh tổng thời gian chạy để kết luận concurrency. Thời gian máy test biến động theo tải, nên barrier hoặc đồng bộ hóa tường minh cho kết quả đáng tin cậy hơn.

### Kiểm thử lỗi một branch

Tạo một branch ném exception có kiểm soát, branch còn lại hoàn tất. Xác nhận trạng thái split/parent theo flow đã cấu hình, các transaction đã commit của branch thành công vẫn còn và restart không tạo dữ liệu trùng.

### Kiểm thử executor quá tải

Với pool và queue nhỏ, submit nhiều branch hoặc chạy nhiều parent job đồng thời để xác nhận rejection/back-pressure được xử lý rõ ràng. Không để test phụ thuộc vào timing không xác định; dùng executor test có giới hạn và barrier/latch để kiểm soát thứ tự.

## Quan sát và vận hành executor

Trong production, nên theo dõi:

- Pool size, active worker count và số thread đang chờ.
- Queue size và số task bị từ chối.
- Thời gian từng branch và thời gian chờ tại join.
- Số job/flow đồng thời.
- Database connection pool usage, lock wait và deadlock.
- CPU, memory và latency của API/broker mà branch sử dụng.
- Trạng thái từng `StepExecution` và `JobExecution`.

Tên thread có prefix như `batch-flow-` giúp nhận diện worker trong log và thread dump. Nên gắn job execution ID, step execution ID và branch name vào structured logging để truy vết các nhánh chạy song song.

Nếu một branch thường xuyên chậm hơn, hãy đo thời gian reader, processor và writer của branch đó. Tăng số worker không nhất thiết giải quyết được một query chậm hoặc một API bị giới hạn quota.

## Các lỗi thường gặp

### Dùng SyncTaskExecutor nhưng mong branch chạy song song

`SyncTaskExecutor` chạy trên thread gọi. Dùng `ThreadPoolTaskExecutor` hoặc executor bất đồng bộ phù hợp nếu cần concurrency.

### Truyền executor vào sai vị trí

Executor của `JobLauncher` điều khiển job execution; executor trong `split(...)` điều khiển flow branch. Hãy cấu hình đúng nơi cần chạy song song.

### Nghĩ queueCapacity là số worker

Queue chỉ giữ task chờ. Số worker thực thi đồng thời bị giới hạn bởi pool size.

### Tăng thread làm database quá tải

Nhiều branch cùng mở transaction hoặc connection có thể tăng lock contention và deadlock. Giới hạn pool theo năng lực database và connection pool.

### Dùng chung reader/writer không thread-safe

Các branch có thể cùng truy cập mutable state hoặc cùng ghi một file. Dùng component riêng, `@StepScope`, resource riêng hoặc cơ chế đồng bộ phù hợp.

### Cho các branch phụ thuộc dữ liệu chạy song song

Nếu branch B cần kết quả branch A, split có thể khiến B chạy trước khi A hoàn tất. Tách phần phụ thuộc thành flow tuần tự hoặc đặt step sau join.

### Giả định một branch lỗi sẽ rollback tất cả branch

Các step có transaction riêng; branch đã commit không tự rollback khi branch khác thất bại. Dùng staging, idempotency hoặc compensation nếu cần phục hồi tổng thể.

### Pool nhỏ gây starvation ở nested split

Các task cha chiếm hết worker trong khi chờ task con trên cùng pool. Tránh lồng split hoặc thiết kế executor riêng và đủ worker.

### Không xử lý shutdown và rejection

Task có thể bị từ chối hoặc bị dừng khi ứng dụng shutdown. Cấu hình queue, rejection policy, graceful shutdown và restart phù hợp.

## Nguyên tắc thiết kế executor cho parallel flow

Khi đưa split flow vào production, hãy xác định:

1. Những branch nào thực sự độc lập và có thể chạy đồng thời?
2. Mỗi branch cần bao nhiêu database connection, CPU, memory và quota hệ thống ngoài?
3. `corePoolSize`, `maxPoolSize` và `queueCapacity` giới hạn concurrency/queue như thế nào?
4. Có nhiều job cùng dùng executor hay không?
5. Reader, writer và service dùng chung có thread-safe không?
6. Các branch có ghi đè dữ liệu hoặc tài nguyên của nhau không?
7. Khi một branch thất bại, dữ liệu branch khác đã commit được xử lý ra sao?
8. Restart có thể tiếp tục từng branch mà không tạo duplicate không?
9. Rejection, thread context và shutdown được xử lý thế nào?
10. Test đã xác nhận branch chạy đồng thời, join, failure và restart chưa?

Với đa số ứng dụng, một `ThreadPoolTaskExecutor` có kích thước hữu hạn, queue hữu hạn và thread name rõ ràng là điểm bắt đầu tốt. Đo tải thực tế để điều chỉnh số worker. Giữ các branch độc lập, dùng component an toàn với thread và thiết kế transaction/restart theo từng step thay vì giả định toàn bộ split là một đơn vị commit.

## Ghi nhớ

Executor cho parallel flow được truyền vào `FlowBuilder.split(TaskExecutor)` để điều phối nhiều flow branch đồng thời. `ThreadPoolTaskExecutor` thường phù hợp production vì giới hạn worker và queue; `SyncTaskExecutor` chỉ chạy tuần tự. Số worker quyết định concurrency, còn queue chỉ chứa task chờ. Split đợi các branch hoàn tất trước khi tiếp tục flow chung, và mỗi step branch có transaction riêng. Một branch thất bại không tự rollback các branch đã commit. Hãy chọn pool theo năng lực database/CPU/dịch vụ ngoài, bảo đảm reader/writer/service thread-safe, xử lý rejection và shutdown, giữ identifying parameters ổn định cho restart, đồng thời kiểm thử concurrency bằng barrier/latch thay vì dựa vào thời gian chạy.
