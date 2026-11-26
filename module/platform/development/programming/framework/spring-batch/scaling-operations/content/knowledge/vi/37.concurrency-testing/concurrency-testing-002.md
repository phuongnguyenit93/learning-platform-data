# Test parallel flow trong Spring Batch

Khi một Spring Batch job chạy hai luồng xử lý độc lập bằng **parallel flow**, việc cả hai step đều trả về trạng thái **COMPLETED** chưa chứng minh chúng đã thực sự chạy song song. Chúng có thể đã chạy lần lượt do cấu hình TaskExecutor, giới hạn thread pool, hoặc lỗi điều phối. Một bài kiểm thử concurrency cần xác minh **hai nhánh có thể hoạt động đồng thời**, **bước sau điểm hợp nhất chỉ chạy khi mọi nhánh cần thiết đã kết thúc**, và **kết quả vẫn nhất quán khi có lỗi hoặc restart**.

Bài học thuộc chương **Testing concurrency** của module **SPRING_BATCH_SCALING_OPERATIONS**. Mục tiêu của module là mở rộng Spring Batch cho workload dữ liệu lớn qua multi-threaded step, parallel steps, partitioning và các mô hình phân tán; đồng thời đo nút thắt, bảo đảm thread safety, retry/restart, vận hành job và chọn kiến trúc theo tài nguyên thực tế. Trong bài này, trọng tâm là **kiểm thử parallel flow trong cùng một JobExecution**; những khác biệt với multi-threaded step và partitioning được chỉ rõ để không áp sai phạm vi test.

## 1. Parallel flow là gì, cần kiểm thử điều gì?

Trong Spring Batch, **flow** mô tả một nhánh điều khiển gồm một hoặc nhiều step. Job có thể dùng **split** với một **TaskExecutor** để chạy nhiều flow ở các thread khác nhau. Khi split hoàn tất, job tiếp tục các bước phía sau dựa trên trạng thái tổng hợp của các flow.

Ví dụ một job chốt số liệu cuối ngày:

- Nhánh A: tính tồn kho, gồm step **inventoryStep**.
- Nhánh B: tổng hợp hóa đơn, gồm step **invoiceStep**.
- Sau khi cả hai nhánh thành công: step **publishStep** tạo bản chốt.

~~~mermaid
flowchart TD
    S["Job bắt đầu"] --> X{"Split: TaskExecutor"}
    X --> A["Flow A: inventoryStep"]
    X --> B["Flow B: invoiceStep"]
    A --> J{"Hợp nhất kết quả các flow"}
    B --> J
    J -->|Cả hai thành công| P["publishStep"]
    J -->|Có nhánh thất bại| F["Job thất bại / xử lý theo transition"]
    P --> E["Job COMPLETED"]
~~~

Sơ đồ mô tả thiết kế mặc định khi chỉ cho phép bước sau chạy nếu split thành công. Nếu người phát triển cấu hình **transition cho trạng thái lỗi** hoặc điều kiện rẽ nhánh đặc biệt, luồng điều khiển có thể khác; test cần bám đúng quy tắc nghiệp vụ.

Một bộ kiểm thử tốt cần trả lời ít nhất sáu câu hỏi:

1. Các nhánh có **khởi động chồng thời gian** khi cả hai còn đang làm việc hay không?
2. Mỗi nhánh có chạy **đúng StepExecution**, dữ liệu và tên step riêng hay không?
3. Bước phụ thuộc sau split có chờ **tất cả nhánh** hoàn tất không?
4. Khi một nhánh lỗi, nhánh còn lại và bước hợp nhất có trạng thái nào?
5. Khi restart, job có bỏ qua step hoàn tất và chạy lại phần chưa hoàn tất **theo quy tắc Spring Batch** hay không?
6. Khi tăng concurrency, dữ liệu đầu ra, connection pool và throughput có còn đáp ứng các bất biến nghiệp vụ?

## 2. Phân biệt parallel flow với các kiểu mở rộng khác

| Mô hình | Đơn vị được chạy đồng thời | Điều nên kiểm thử | Cạm bẫy thường gặp |
| --- | --- | --- | --- |
| **Parallel flows** | Nhiều nhánh flow, mỗi nhánh chứa các step riêng | Hai nhánh cùng hoạt động; join/transition; lỗi một nhánh | Chỉ kiểm tra tổng thời gian hoặc status COMPLETED |
| **Multi-threaded step** | Nhiều thread xử lý công việc trong cùng một step | Reader/writer thread safety, ghi đủ item, thứ tự và commit | Shared state làm mất/trùng item |
| **Local partitioning** | Nhiều worker StepExecution cho các vùng dữ liệu | Không chồng vùng; cân bằng partition; restart từng partition | Kiểm tra mỗi partition xong nhưng không kiểm tra coverage |
| **Remote partitioning/chunking** | Công việc được chuyển qua middleware đến worker khác | Giao việc, ACK/response, redelivery, idempotency | Timeout bị coi là bằng chứng nghiệp vụ chưa commit |

**Parallel flow không tự làm cho ItemReader trong một step trở nên thread-safe.** Mỗi step của các flow có thể chỉ chạy trên một thread nhưng các flow vẫn tranh tài nguyên chung như singleton service, bộ nhớ đệm, bảng DB, pool kết nối và API ngoài.

## 3. Ba mức kiểm thử cần kết hợp

### 3.1. Kiểm thử cấu hình

Kiểm tra job thực sự có split, TaskExecutor có khả năng chạy ít nhất hai tác vụ đồng thời, các flow có tên riêng, và **publishStep** nằm **sau split**. Đừng chỉ nhìn số thread cấu hình: thread pool có thể bị giới hạn bởi task khác hoặc sử dụng executor đồng bộ.

### 3.2. Kiểm thử tích hợp có điều khiển đồng thời

Dùng **CountDownLatch**, **CyclicBarrier** hoặc cơ chế tương đương để tạo điểm đồng bộ tại hai nhánh. Test phải phát hiện được cấu hình vô tình chuyển sang chạy tuần tự, đồng thời tránh phụ thuộc vào thứ tự scheduling.

### 3.3. Kiểm thử kết quả và tải

Kiểm thử với database/transaction thật, sau đó chạy workload ở nhiều mức concurrency để tìm nút thắt CPU, I/O, DB lock, connection pool và memory. Một kiểm thử chức năng chứng minh **khả năng chạy song song**; nó **không tự chứng minh** throughput sản xuất hoặc tính an toàn khi tải cao.

## 4. Vì sao Thread.sleep và kiểm tra thời gian thường không đủ?

Một kiểm thử kiểu “hai step mỗi step sleep 2 giây; tổng thời gian dưới 3 giây thì đạt” dễ bị sai:

- CI chậm, startup Spring context và JobRepository làm tổng thời gian biến động.
- Máy nhanh vẫn có thể chạy các công việc ngắn lần lượt mà tổng thời gian dưới ngưỡng.
- Thread.sleep không chứng minh **cả hai nhánh cùng ở trong vùng xử lý** tại một thời điểm.
- Nếu lỗi được framework retry hoặc DB bị lock, phép đo thời gian phản ánh nhiều yếu tố ngoài parallel flow.

**Cách kiểm tra mạnh hơn:** mỗi nhánh báo “đã vào đoạn xử lý” bằng cách giảm một latch. Cả hai cùng dừng ở một latch thứ hai. Test chờ thấy **cả hai nhánh đều đã vào** trong một thời hạn; nếu executor chỉ chạy một nhánh tại một thời điểm, nhánh đầu sẽ bị giữ lại, nhánh hai không thể báo vào, và test thất bại có chủ đích. Sau đó test mở cổng để hai nhánh kết thúc.

~~~text
Test thread                Flow A worker                Flow B worker
    |                            |                            |
    |---- launchJob async -----> |                            |
    |                            |--- entered.countDown()      |
    |                            |--- await(release)           |
    |                            |                   entered.countDown()
    |--- await(bothEntered) ---- |                   await(release)
    |--- assert join=false ----- |                            |
    |--- release.countDown() --->|                            |
    |                            +---- complete ---------------+
    |------------------------------- join chạy sau cả hai ------|
    |--- get JobExecution, assert status/counters --------------|
~~~

Chỉ dùng timeout để **ngăn test treo vô hạn**, không dùng timeout làm chỉ số tốc độ để khẳng định hiệu năng.

## 5. Ví dụ cấu hình Spring Batch 5.x

Giả định sử dụng **Java 17+, Spring Batch 5.x và Spring Boot 3.x**, đã có JobRepository, DataSource và PlatformTransactionManager hợp lệ. Các đoạn mã sau tập trung vào flow và kiểm thử, có thể đưa vào một project Spring Boot test; phần import được lược bớt.

### 5.1. Probe tạo hai điểm đồng bộ

Probe chỉ dùng cho **kiểm thử**. Hai worker đi qua cùng một latch để xác nhận đã cùng bắt đầu, rồi dừng tại một cổng chung cho tới khi test cho phép. Biến **joinExecuted** ghi nhận việc step phía sau split đã chạy.

~~~java
final class ParallelFlowProbe {
    final CountDownLatch bothEntered = new CountDownLatch(2);
    final CountDownLatch allowFinish = new CountDownLatch(1);
    final AtomicBoolean joinExecuted = new AtomicBoolean(false);
    final Set<String> workerThreads = ConcurrentHashMap.newKeySet();

    void enterBranch() throws InterruptedException {
        workerThreads.add(Thread.currentThread().getName());
        bothEntered.countDown();

        // Fail fast nếu một nhánh không bao giờ được schedule.
        if (!allowFinish.await(20, TimeUnit.SECONDS)) {
            throw new IllegalStateException(
                    "Parallel branch did not receive release signal");
        }
    }
}
~~~

Đây là fixture một lần chạy. Nếu có nhiều phương thức test dùng chung Spring context, hãy cấp **probe mới cho mỗi test** hoặc reset toàn bộ latch một cách an toàn trước khi chạy; tránh dùng lại CountDownLatch đã về 0.

### 5.2. Tạo hai nhánh và bước hợp nhất

~~~java
@Configuration(proxyBeanMethods = false)
class ParallelFlowConfig {

    @Bean
    ParallelFlowProbe parallelFlowProbe() {
        return new ParallelFlowProbe();
    }

    @Bean
    ThreadPoolTaskExecutor parallelFlowExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(2);
        executor.setQueueCapacity(0);
        executor.setThreadNamePrefix("batch-flow-");
        executor.initialize();
        return executor;
    }

    @Bean
    Step inventoryStep(JobRepository jobRepository,
                       PlatformTransactionManager transactionManager,
                       ParallelFlowProbe probe) {
        return new StepBuilder("inventoryStep", jobRepository)
                .tasklet((contribution, context) -> {
                    probe.enterBranch();
                    return RepeatStatus.FINISHED;
                }, transactionManager)
                .build();
    }

    @Bean
    Step invoiceStep(JobRepository jobRepository,
                     PlatformTransactionManager transactionManager,
                     ParallelFlowProbe probe) {
        return new StepBuilder("invoiceStep", jobRepository)
                .tasklet((contribution, context) -> {
                    probe.enterBranch();
                    return RepeatStatus.FINISHED;
                }, transactionManager)
                .build();
    }

    @Bean
    Step publishStep(JobRepository jobRepository,
                     PlatformTransactionManager transactionManager,
                     ParallelFlowProbe probe) {
        return new StepBuilder("publishStep", jobRepository)
                .tasklet((contribution, context) -> {
                    probe.joinExecuted.set(true);
                    return RepeatStatus.FINISHED;
                }, transactionManager)
                .build();
    }

    @Bean
    Flow inventoryFlow(@Qualifier("inventoryStep") Step inventoryStep) {
        return new FlowBuilder<SimpleFlow>("inventoryFlow")
                .start(inventoryStep)
                .build();
    }

    @Bean
    Flow invoiceFlow(@Qualifier("invoiceStep") Step invoiceStep) {
        return new FlowBuilder<SimpleFlow>("invoiceFlow")
                .start(invoiceStep)
                .build();
    }

    @Bean
    Flow parallelFlow(
            @Qualifier("parallelFlowExecutor") TaskExecutor taskExecutor,
            @Qualifier("inventoryFlow") Flow inventoryFlow,
            @Qualifier("invoiceFlow") Flow invoiceFlow) {
        return new FlowBuilder<SimpleFlow>("parallelFlow")
                .split(taskExecutor)
                .add(inventoryFlow, invoiceFlow)
                .build();
    }

    @Bean
    Job parallelJob(JobRepository jobRepository,
                    @Qualifier("parallelFlow") Flow parallelFlow,
                    @Qualifier("publishStep") Step publishStep) {
        return new JobBuilder("parallelJob", jobRepository)
                .start(parallelFlow)
                .next(publishStep)
                .end()
                .build();
    }
}
~~~

**Điểm cần hiểu trong cấu hình:**

- **inventoryFlow** và **invoiceFlow** là hai nhánh của split, có các step độc lập.
- **parallelFlowExecutor** cho phép tối đa hai worker chạy song song trong ví dụ; nếu chỉ có một thread thực sự khả dụng, phép thử latch ở phần sau sẽ phát hiện.
- **publishStep** chỉ được đi tới khi trạng thái tổng hợp của split cho phép transition thành công.
- Tasklet trong ví dụ giữ transaction trong lúc chờ latch. Điều này chỉ phù hợp để kiểm tra điều phối trong môi trường test, **không phải cách thiết kế transaction của job thật**.
- Tên Job, Flow và Step cần ổn định để metadata trong JobRepository có ý nghĩa khi restart.

## 6. Integration test: chứng minh hai flow chạy đồng thời

Sử dụng **JUnit 5**, **@SpringBatchTest** và **@SpringBootTest**. Ví dụ giả định ứng dụng test đã nạp ParallelFlowConfig ở trên thông qua component scan hoặc import configuration, đồng thời cung cấp Spring Batch infrastructure. Tắt tự chạy job lúc khởi động context để không có execution khác tiêu thụ latch.

~~~java
@SpringBatchTest
@SpringBootTest(properties = "spring.batch.job.enabled=false")
class ParallelFlowIT {

    @Autowired
    JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    ParallelFlowProbe probe;

    @Autowired
    @Qualifier("parallelJob")
    Job parallelJob;

    @BeforeEach
    void setTargetJob() {
        jobLauncherTestUtils.setJob(parallelJob);
    }

    @Test
    void bothBranchesOverlapAndJoinRunsAfterBothFinish() throws Exception {
        ExecutorService launcherThread = Executors.newSingleThreadExecutor();

        JobParameters parameters = new JobParametersBuilder()
                .addString("test.run.id", UUID.randomUUID().toString())
                .toJobParameters();

        try {
            Future<JobExecution> pending = launcherThread.submit(
                    () -> jobLauncherTestUtils.launchJob(parameters));

            try {
                // Cả hai nhánh phải đi vào vùng xử lý cùng lúc.
                assertTrue(probe.bothEntered.await(10, TimeUnit.SECONDS),
                        "Both branches must be active before either finishes");

                // Khi cả hai vẫn đang bị chặn, join chưa được phép chạy.
                assertFalse(probe.joinExecuted.get(),
                        "publishStep started before split completed");

                assertEquals(2, probe.workerThreads.size(),
                        "Expected two distinct worker threads");
            } finally {
                // Luôn thả các worker kể cả khi assertion thất bại.
                probe.allowFinish.countDown();
            }

            JobExecution result = pending.get(30, TimeUnit.SECONDS);
            assertEquals(BatchStatus.COMPLETED, result.getStatus());
            assertTrue(probe.joinExecuted.get());

            Map<String, BatchStatus> stepStatuses =
                    result.getStepExecutions().stream()
                            .collect(Collectors.toMap(
                                    StepExecution::getStepName,
                                    StepExecution::getStatus));

            assertEquals(
                    Set.of("inventoryStep", "invoiceStep", "publishStep"),
                    stepStatuses.keySet());
            assertTrue(stepStatuses.values().stream()
                    .allMatch(BatchStatus.COMPLETED::equals));
        } finally {
            probe.allowFinish.countDown();
            launcherThread.shutdownNow();
        }
    }
}
~~~

Tùy project, cần import đầy đủ các lớp từ **org.springframework.batch**, **org.springframework.boot.test.context**, **org.springframework.batch.test**, **org.junit.jupiter.api** và **java.util.concurrent**. Nếu ứng dụng có nhiều cấu hình job hoặc Spring context không tự scan ParallelFlowConfig, hãy khai báo **@Import(ParallelFlowConfig.class)** hoặc chỉ định test configuration. Không đưa fixture này vào job production.

### Test thực sự chứng minh điều gì?

1. **bothEntered.await(...)** trả true trong khi hai nhánh vẫn bị giữ tại cổng **allowFinish**: hai nhánh phải có khả năng thực thi **chồng thời gian**.
2. **workerThreads.size() == 2**: điểm xử lý trong ví dụ diễn ra trên hai thread khác nhau.
3. **joinExecuted == false** trước khi mở cổng: publishStep chưa chạy quá sớm.
4. **JobExecution COMPLETED** và ba StepExecution **COMPLETED** sau khi mở cổng: flow đi hết đường thành công.

Đây là bằng chứng về **thực thi đồng thời và thứ tự phụ thuộc**. Test chưa chứng minh hoạt động đọc/ghi dữ liệu thật, timeout/rollback của DB, hay throughput khi tăng lên hàng triệu item.

### Vì sao launchJob phải chạy ở một thread khác?

Trong nhiều môi trường test, lời gọi **JobLauncherTestUtils.launchJob(...)** sẽ chờ JobExecution kết thúc. Nếu test gọi trực tiếp trên cùng thread rồi mới chờ latch, thread kiểm thử không thể điều khiển điểm mở cổng. Chạy job qua một **ExecutorService riêng** cho phép thread test đồng thời quan sát hai nhánh và thả chúng; executor của **split** vẫn là ThreadPoolTaskExecutor trong cấu hình job.

Nếu test thất bại vì không đủ thread, latch bên trong tasklet sẽ timeout và báo lỗi có ý nghĩa. Hãy bảo đảm timeout đủ rộng cho CI và luôn giải phóng latch trong **finally** để tránh giữ worker khi assertion hỏng.

## 7. Kiểm thử điều kiện join và xử lý lỗi

### 7.1. Nếu một nhánh thất bại

Một kịch bản kiểm thử độc lập nên cấu hình **invoiceStep** chủ động ném ngoại lệ, còn **inventoryStep** hoàn tất bình thường. Với transition mặc định của ví dụ:

- Job cuối cùng ở trạng thái **FAILED**.
- Step của nhánh lỗi có trạng thái **FAILED**.
- Step đã thực thi thành công ở nhánh khác có thể ở **COMPLETED**; rollback của nhánh lỗi **không tự rollback** các transaction đã commit của nhánh kia.
- **publishStep** không được chạy khi split thất bại và không có transition cho phép tiếp tục.
- Không kết luận trạng thái toàn job bằng cách chỉ xem status của một nhánh.

~~~java
// Minh họa nhánh lỗi riêng cho một test case khác:
.tasklet((contribution, context) -> {
    throw new IllegalStateException("Simulated invoice failure");
}, transactionManager)
~~~

Không cấy mã gây lỗi này vào cùng fixture latch đang dùng cho phép thử thành công. Nếu giữ cả hai latch mà một nhánh ném lỗi trước điểm đồng bộ, nhánh còn lại có thể phải đợi timeout, khiến test kiểm tra sai điều cần kiểm chứng.

### 7.2. Nếu một nhánh bị STOPPED

Khi yêu cầu dừng job, hãy kiểm tra khả năng **cooperative stop**: tasklet hoặc reader có trả quyền điều khiển, chunk transaction có đạt tới checkpoint, metadata StepExecution có cập nhật hợp lệ hay không. Việc gửi stop request không phải bằng chứng worker đã dừng ngay; không nên đặt một assert thời gian cực ngắn và coi đó là hợp đồng framework.

### 7.3. Nếu nhánh hoàn tất sớm hơn nhánh còn lại

Dùng hai latch riêng để giữ nhánh B ở một điểm, cho A hoàn tất, rồi kiểm tra **publishStep chưa chạy**. Sau khi giải phóng B, bước join mới có thể thực thi. Biến thể này bổ sung cho test ở phần 6 vì nó kiểm tra rõ điều kiện **đợi nhánh chậm nhất**, vốn là nguyên nhân thường gặp của tổng thời gian job.

## 8. Test tính đúng đắn của dữ liệu khi hai flow dùng tài nguyên chung

Parallel flow cho phép các nhánh chạy cùng lúc nhưng **không tự bảo vệ** dữ liệu nghiệp vụ. Hai nhánh có thể cùng đọc/ghi một bảng, chia sẻ service singleton hoặc tranh connection pool.

Ví dụ: **inventoryStep** cập nhật số lượng tồn, **invoiceStep** ghi hóa đơn. Một invariant hợp lệ có thể là: sau khi job COMPLETED, tổng lượng xuất kho bằng tổng lượng bán trên các hóa đơn được chấp nhận. Test phải kiểm tra invariant này trên **cơ sở dữ liệu thực**, không chỉ kiểm tra hai step có trạng thái COMPLETED.

| Nguy cơ | Cách tạo tình huống test | Bằng chứng cần thu |
| --- | --- | --- |
| Lost update | Hai nhánh cùng sửa một record, có barrier trước thao tác ghi | Số dư cuối đúng; locking/versioning bảo vệ cập nhật |
| Double insert | Hai nhánh cùng chèn một business key | Unique constraint/idempotency hoạt động |
| Dirty/non-repeatable read | Một nhánh đọc dữ liệu khi nhánh khác cập nhật | Kết quả đúng theo isolation level được lựa chọn |
| Shared mutable singleton | Hai nhánh cùng dùng cache/list/counter mutable | Không mất update; dùng state bất biến hoặc đồng bộ đúng |
| ThreadLocal/MDC thiếu | Hai nhánh log cùng correlation ID | Context được truyền rõ ràng hoặc được dựng theo StepExecution |
| DB pool cạn | Pool nhỏ hơn số connection thực cần | Không deadlock/starvation; wait time trong ngưỡng |

Nếu hệ thống sản xuất dùng PostgreSQL, MySQL hoặc Oracle, nên chạy các test đụng tới **transaction, isolation và lock** trên đúng loại database đó (ví dụ Testcontainers). Một database in-memory như H2 có thể dùng để kiểm tra cấu hình flow, nhưng không thay thế bằng chứng về tính chất khóa/giao dịch của DB sản xuất.

### Ví dụ kiểm tra idempotency

~~~sql
CREATE TABLE batch_result (
    job_key       VARCHAR(80) NOT NULL,
    business_key  VARCHAR(80) NOT NULL,
    result_value  NUMERIC(18, 2) NOT NULL,
    PRIMARY KEY (job_key, business_key)
);
~~~

Hai nhánh hoặc một lần restart có thể cùng cố ghi một business key. Unique constraint bảo vệ khỏi **hai dòng trùng khóa**, nhưng chưa chứng minh giá trị đúng; cần thêm assertion về **result_value**, sự kiện ngoài DB và số lần áp dụng nghiệp vụ. Với thao tác cộng dồn, viết lại cùng một record không mặc nhiên là idempotent: cùng một phép cộng chạy lại có thể làm tổng tiền tăng hai lần.

## 9. Test retry, restart và bước đã hoàn tất

Spring Batch dùng **JobRepository** để ghi metadata JobInstance, JobExecution, StepExecution và ExecutionContext. Với một **JobInstance** chưa hoàn tất, lần restart thông thường tạo JobExecution mới và tiếp tục các step phù hợp với trạng thái đã lưu. Mục tiêu kiểm thử là phát hiện bước bị chạy lại ngoài ý muốn, bỏ sót dữ liệu, hoặc trạng thái metadata sai.

Một kịch bản có tính xác định:

1. Chạy job lần đầu. Nhánh A hoàn tất và commit kết quả, nhánh B thất bại có chủ ý sau một checkpoint, bước publish không chạy.
2. Đối chiếu JobExecution đầu **FAILED**, StepExecution của nhánh A **COMPLETED**, B **FAILED** và dữ liệu A đã có.
3. Gỡ lỗi nhánh B, khởi chạy lại **cùng JobInstance** với **cùng identifying JobParameters** bằng cơ chế restart phù hợp.
4. Kiểm tra B hoàn tất; A không chạy lại nếu step mặc định có thể được bỏ qua và không bật **allowStartIfComplete**; publish chỉ chạy sau khi split thành công.
5. Đối soát kết quả, bảo đảm phần dữ liệu đã commit ở lần đầu không bị nhân đôi.

**Phân biệt hai thao tác:**

- **Restart cùng JobInstance:** dùng lại identifying parameters thích hợp, thực thi phần công việc chưa hoàn tất theo trạng thái.
- **Chạy job mới với tham số định danh mới:** tạo JobInstance khác; các step có thể chạy lại từ đầu, nên không được dùng điều này để mô phỏng restart.

Nếu cấu hình bước có **startLimit**, **allowStartIfComplete**, transition tùy chỉnh hoặc trạng thái **STOPPED/UNKNOWN**, kỳ vọng phải điều chỉnh. Cần ghi rõ trạng thái trước và sau trong test.

**Lưu ý:** concurrency test dùng CountDownLatch ở phần 6 chủ yếu kiểm tra điều phối. Test restart nên dùng các step thật có checkpoint, writer idempotent và failure injection **sau commit/chunk boundary**, không giữ transaction mở tại latch rồi suy diễn rằng đó là restart sản xuất.

## 10. Thiết kế failure injection không tạo test giả

Để tái hiện những lỗi concurrency khó gặp, có thể đặt điểm can thiệp rõ ràng ở service/DAO/test hook. Test kiểm soát điểm lỗi và kết quả mong đợi, thay vì chờ race condition tình cờ xảy ra.

| Kịch bản | Điểm chèn lỗi có ích | Kỳ vọng cần test |
| --- | --- | --- |
| Nhánh B exception | Trước khi B kết thúc, sau khi A đã tạo side effect hợp lệ | Job FAILED, publish không chạy, A không bị coi là rollback |
| Nhánh B chậm | Giữ B tại latch, thả A trước | Publish vẫn chờ B |
| Hai nhánh update cùng hàng DB | Barrier trước update hoặc thay đổi isolation | Không mất cập nhật ngoài hợp đồng nghiệp vụ |
| Pool không đủ connection | Hạ giới hạn pool trong môi trường test | Lỗi rõ hoặc chờ trong timeout được định nghĩa, không treo vô hạn |
| Worker bị interrupt | Ngắt tại một operation có hỗ trợ interrupt | Step/Job phản ánh trạng thái và cleanup phù hợp |
| Restart sau commit một phần | Chèn lỗi ở chunk thứ N của nhánh B | Resume đúng checkpoint; không trùng kết quả |

Đừng đặt toàn bộ thao tác chờ dài bên trong transaction thực rồi dùng kết quả đó để mô tả hành vi sản xuất. Việc giữ lock có thể tự tạo deadlock mà hệ thống bình thường không có. Dùng latch ở ranh giới thích hợp, mock một dependency được kiểm soát hoặc tài nguyên test có thời hạn.

## 11. Kiểm tra StepExecution và số liệu quan sát

**JobExecution/StepExecution** là bằng chứng tốt về trạng thái batch, nhưng không đo trực tiếp khả năng chạy đồng thời. Nên kết hợp metadata với ghi nhận thời điểm và thread của từng nhánh.

| Thuộc tính / metric | Dùng để xác minh |
| --- | --- |
| JobExecution status, exitStatus | Trạng thái tổng hợp của job và hướng transition |
| StepExecution status, exitStatus | Nhánh nào hoàn tất, lỗi hoặc bị dừng |
| StepExecution startTime, endTime | Khoảng thực thi từng step (thô; độ chính xác phụ thuộc clock) |
| readCount, writeCount, filterCount, skipCount | Dữ liệu đã đi qua mỗi step |
| commitCount, rollbackCount | Hành vi commit/rollback và chi phí retry |
| Thread name, tracing span, correlation ID | Hai nhánh được schedule ra sao, lỗi liên quan request nào |
| Connection pool active/idle/wait | Tắc nghẽn DB khi tăng concurrency |
| CPU, GC, DB query latency, lock wait | Nút thắt hiệu năng thực sự |

**Điều kiện kiểm tra overlap bằng timestamp** chỉ nên là bổ trợ:

~~~text
overlap nếu:
  max(startA, startB) < min(endA, endB)
~~~

Trong thực tế, timestamp lưu trong metadata có độ phân giải, độ trễ ghi nhận và thời gian khởi tạo khác nhau. Một test dùng latch có thể xác nhận overlap đáng tin hơn. Nếu lấy dữ liệu trên nhiều máy, cần đồng bộ clock hoặc tracing theo khoảng thời gian đơn điệu tại từng node.

## 12. Kiểm thử tải để chọn mức song song phù hợp

Sau khi test cấu hình và tính đúng đắn PASS, đo hiệu năng bằng workload tương đương thực tế. Một bảng thí nghiệm có thể bắt đầu như sau:

| Thử nghiệm | Cấu hình | Quan sát |
| --- | --- | --- |
| Baseline | Hai công việc chạy tuần tự | Tổng thời gian, CPU/DB baseline |
| Split với 2 thread | Flow A/B song song | Thời gian job và nhánh chậm nhất |
| Split với DB pool nhỏ | Hai flow nhưng DB pool bị giới hạn | Connection wait, số lần timeout |
| Split dưới tải hệ thống | Có các tác vụ đồng thời khác | Ảnh hưởng throughput và p95 latency |
| Failure/restart | Một flow lỗi trong lúc flow kia đã commit | Thời gian khôi phục và dữ liệu cuối |

Khi hai flow độc lập chạy song song, thời gian job lý tưởng xấp xỉ **thời gian nhánh chậm nhất + overhead**. Không thể khẳng định tốc độ tăng gấp hai: nếu cùng tranh DB lock, connection pool hoặc băng thông I/O thì parallel flow có thể **chậm hơn** chạy tuần tự.

Ví dụ flow A mất 9 phút, flow B mất 6 phút; tổng tuần tự lý tưởng là 15 phút, trong khi split không tranh tài nguyên có thể tiến gần 9 phút cộng overhead. Đây là **ước lượng minh họa**, không phải một phép đo từ môi trường hiện tại. Cần thử với dữ liệu, DB và hạ tầng thật trước khi quyết định mở rộng.

## 13. Những lỗi kiểm thử thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách sửa |
| --- | --- | --- |
| Test xanh nhưng job thật vẫn tuần tự | Chỉ assert COMPLETED; TaskExecutor chạy đồng bộ hoặc pool một thread | Thêm kiểm tra overlap bằng latch, kiểm tra executor của split |
| Test treo vô hạn | Một nhánh không đến barrier; không có timeout/finally | Dùng await có giới hạn và always-release trong finally |
| Test pass riêng lẻ nhưng fail khi chạy cả suite | Shared probe/latch/JobParameters hoặc DB state còn từ test trước | Fixture mới, dữ liệu cô lập, identifying parameters duy nhất |
| Test flaky theo tốc độ máy CI | Dựa vào Thread.sleep hoặc ngưỡng duration quá chặt | Đồng bộ bằng latch và tách performance test |
| Job COMPLETED nhưng kết quả sai | Shared mutable state, transaction isolation, logic business race | Assert invariant dữ liệu trên DB sản xuất tương đương |
| Join chạy khi một nhánh lỗi | Transition cấu hình cho phép tiếp tục hoặc step nằm ngoài split không đúng | Kiểm tra graph của job và trạng thái/transition thực |
| Restart tạo bản ghi trùng | JobInstance mới hoặc writer không idempotent | Dùng đúng JobParameters, unique constraint, kiểm tra side effect |
| Thêm thread khiến job chậm | DB pool/lock/CPU/GC là bottleneck | Giảm concurrency, tối ưu SQL, đo từng thành phần |

## 14. Bài thực hành tự kiểm chứng

Hãy tạo một job gồm **inventoryFlow** và **invoiceFlow** chạy qua split, sau đó chạy **publishStep**. Trước khi coi cấu hình đạt yêu cầu, thực hiện lần lượt:

1. **Positive test:** dùng probe ở phần 5 và integration test ở phần 6. Cả hai nhánh phải vào đồng thời, join chưa chạy khi chúng đang chờ và cả ba step đều COMPLETED sau khi thả latch.
2. **Negative test cho executor:** đổi executor của split sang chỉ một worker trong môi trường test riêng. Test overlap phải **thất bại có thời hạn**, chứng minh test có khả năng phát hiện chạy tuần tự. Khôi phục cấu hình đúng sau phép thử.
3. **Slow-branch test:** cho A kết thúc trước, giữ B tại latch. Xác minh publishStep vẫn chưa chạy, rồi cho B hoàn tất.
4. **Failing-branch test:** cho B ném ngoại lệ. Xác minh Job FAILED, A có thể đã commit, publish không chạy và metadata ghi đúng lý do thất bại.
5. **Restart test:** sửa nguyên nhân lỗi và restart cùng JobInstance. Xác minh phần đã hoàn tất không bị chạy lại ngoài ý muốn và dữ liệu không bị nhân đôi.
6. **Database test:** cho hai nhánh truy cập cùng một tài nguyên nghiệp vụ có kiểm soát. Kiểm tra invariant dữ liệu, unique constraint và transaction trên database tương đương production.
7. **Performance test:** chạy dữ liệu đủ lớn, so sánh tuần tự và song song với cùng dataset, đo CPU, DB pool, lock, độ trễ và thời gian toàn job.

### Tiêu chí hoàn thành

- **Concurrency:** có bằng chứng hai flow cùng hoạt động, độc lập với thời gian sleep.
- **Ordering:** bước phụ thuộc chạy đúng sau khi mọi nhánh yêu cầu đã hoàn tất.
- **Failure:** trạng thái job/step đúng và không làm sai dữ liệu đã commit ở nhánh khác.
- **Restart:** JobRepository và checkpoint đưa job về kết quả hợp lệ, không bị xử lý trùng ngoài ý muốn.
- **Thread safety:** mọi tài nguyên dùng chung đáp ứng bất biến nghiệp vụ khi thực thi song song.
- **Operations:** có metric chỉ ra mức parallelism phù hợp với CPU, I/O, DB và tài nguyên thực.

**Ghi nhớ:** Kiểm thử parallel flow của Spring Batch cần chứng minh **overlap thực sự, thứ tự hợp nhất, tính đúng đắn và khả năng khôi phục**. CountDownLatch giúp xác nhận khả năng chạy đồng thời một cách ổn định; JobRepository cho biết trạng thái batch; kiểm thử database và load test mới xác định liệu song song có an toàn và hiệu quả đối với workload dữ liệu lớn hay không.
