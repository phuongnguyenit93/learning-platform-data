# Master step điều phối partition

Trong Spring Batch, partitioning chia một Step lớn thành nhiều phần công việc độc lập để có thể xử lý đồng thời hoặc phân phối đến nhiều worker. **Master Step** (còn gọi là manager Step) chịu trách nhiệm điều phối các phần việc đó. Mỗi phần được thực thi bởi một **worker Step** với StepExecution và ExecutionContext riêng.

Master Step không trực tiếp đọc và ghi toàn bộ dữ liệu nghiệp vụ. Nó tạo hoặc nhận danh sách partition, yêu cầu PartitionHandler khởi chạy worker cho từng partition, thu kết quả và tổng hợp trạng thái. Worker Step mới thực hiện công việc thực tế như đọc, xử lý và ghi dữ liệu của partition được giao.

Hiểu rõ vai trò của master giúp thiết kế Job có thể mở rộng, theo dõi tiến độ từng partition, xử lý lỗi và restart một cách có kiểm soát.

## 1. Partitioning và vai trò của Master Step

Giả sử Job cần nhập 1.000.000 đơn hàng. Nếu một worker xử lý toàn bộ dữ liệu, thời gian chạy có thể dài. Có thể chia phạm vi dữ liệu thành nhiều partition:

~~~text
Job: importOrdersJob
        |
        v
Master Step: managerStep
        |
        +-- Partition 0: orderId 1 - 250000
        |
        +-- Partition 1: orderId 250001 - 500000
        |
        +-- Partition 2: orderId 500001 - 750000
        |
        +-- Partition 3: orderId 750001 - 1000000
                 |
                 v
          Worker Step instances
~~~

Mỗi partition là một phạm vi công việc riêng. Worker nhận metadata của partition, đọc dữ liệu thuộc phạm vi đó, xử lý và ghi kết quả. Các worker có thể chạy tuần tự, song song trong cùng JVM hoặc trên các process/máy khác nhau tùy PartitionHandler.

Master Step có các trách nhiệm chính:

- Yêu cầu Partitioner xác định các partition cần thực hiện.
- Tạo hoặc phối hợp tạo StepExecution tương ứng với từng partition.
- Chuyển ExecutionContext của mỗi partition đến worker.
- Dùng PartitionHandler để phân phối và khởi chạy worker.
- Thu thập kết quả StepExecution của các worker.
- Tổng hợp trạng thái và kết thúc master Step phù hợp với kết quả các partition.

Worker Step có các trách nhiệm khác:

- Nhận phạm vi dữ liệu từ StepExecutionContext.
- Mở reader và resource theo phạm vi được giao.
- Xử lý dữ liệu bằng reader, processor và writer.
- Lưu checkpoint riêng nếu thành phần hỗ trợ restart.
- Trả trạng thái hoàn tất hoặc thất bại cho master.

Master Step là bộ điều phối. Worker Step là đơn vị xử lý dữ liệu. Hai vai trò có thể dùng chung một định nghĩa Step nhưng mỗi partition có StepExecution riêng.

## 2. Các thành phần chính trong partitioning

Một cấu hình partitioning thường có bốn thành phần:

| Thành phần | Trách nhiệm |
| --- | --- |
| **Master Step** | Điều phối việc tạo và thực thi các partition |
| **Partitioner** | Tạo tên partition và ExecutionContext chứa dữ liệu cần thiết cho worker |
| **Worker Step** | Thực hiện xử lý nghiệp vụ cho một partition |
| **PartitionHandler** | Khởi chạy worker, phân phối công việc và thu kết quả thực thi |

Luồng phối hợp:

~~~text
Master Step
    |
    v
Partitioner.partition(gridSize)
    |
    +--> partition0 + ExecutionContext
    +--> partition1 + ExecutionContext
    +--> partition2 + ExecutionContext
    |
    v
StepExecutionSplitter
    |
    v
PartitionHandler
    |
    +--> Worker Step / partition0
    +--> Worker Step / partition1
    +--> Worker Step / partition2
    |
    v
Thu kết quả StepExecution
    |
    v
Master Step tổng hợp trạng thái
~~~

Spring Batch dùng các abstraction như Partitioner, StepExecutionSplitter và PartitionHandler để thực hiện quy trình này. Ứng dụng thường cấu hình Partitioner và worker Step; cơ sở hạ tầng StepBuilder tạo master Step cùng handler thích hợp.

## 3. Partitioner tạo phạm vi công việc

Partitioner nhận grid size và trả về Map có tên partition cùng ExecutionContext tương ứng:

~~~java
public interface Partitioner {
    Map<String, ExecutionContext> partition(int gridSize);
}
~~~

Mỗi entry trong Map đại diện cho một partition. Key là tên partition, còn ExecutionContext chứa dữ liệu worker cần biết, ví dụ:

- Khóa bắt đầu và kết thúc của phạm vi dữ liệu.
- Ngày nghiệp vụ hoặc tenant ID.
- Tên file đầu vào hoặc vị trí file.
- Partition number hoặc sort key.
- Một số tham số nhỏ cần thiết để mở resource.

Ví dụ Partitioner chia đơn hàng theo khoảng ID:

~~~java
public class OrderRangePartitioner implements Partitioner {

    private final OrderRepository orderRepository;

    public OrderRangePartitioner(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Override
    public Map<String, ExecutionContext> partition(int gridSize) {
        long minId = orderRepository.findMinId();
        long maxId = orderRepository.findMaxId();

        Map<String, ExecutionContext> partitions = new LinkedHashMap<>();

        if (maxId < minId) {
            return partitions;
        }

        long total = maxId - minId + 1;
        long targetSize = (total + gridSize - 1) / gridSize;
        long start = minId;
        int partitionNumber = 0;

        while (start <= maxId) {
            long end = Math.min(start + targetSize - 1, maxId);

            ExecutionContext context = new ExecutionContext();
            context.putLong("minOrderId", start);
            context.putLong("maxOrderId", end);

            partitions.put("partition" + partitionNumber, context);

            start = end + 1;
            partitionNumber++;
        }

        return partitions;
    }
}
~~~

Ví dụ này minh họa cách chia một khoảng ID liên tục thành các đoạn gần bằng nhau. Trong hệ thống thật, cần xử lý cẩn thận khi bảng rỗng, ID có khoảng trống lớn hoặc phép tính có nguy cơ tràn số. Nếu ID không liên tục hoặc phân bố dữ liệu lệch, chia đều theo khoảng số học có thể tạo partition có số item rất khác nhau.

Một chiến lược khác là chia theo ngày, tenant, hash bucket hoặc các nhóm khóa có kích thước gần nhau. Điều quan trọng là mỗi partition phải có phạm vi rõ ràng và không vô tình đọc trùng dữ liệu của partition khác.

## 4. ExecutionContext truyền dữ liệu từ master đến worker

Partitioner không truyền toàn bộ danh sách item cho worker. Nó truyền thông tin mô tả phạm vi xử lý thông qua ExecutionContext.

Ví dụ partitioner tạo context:

~~~java
ExecutionContext context = new ExecutionContext();
context.putLong("minOrderId", 1L);
context.putLong("maxOrderId", 250000L);
~~~

Worker Step có thể đọc các giá trị này bằng Step scope:

~~~java
@Bean
@StepScope
public ItemReader<Order> orderReader(
        OrderRepository orderRepository,
        @Value("#{stepExecutionContext['minOrderId']}") Long minOrderId,
        @Value("#{stepExecutionContext['maxOrderId']}") Long maxOrderId) {

    return new OrderRangeReader(
            orderRepository,
            minOrderId,
            maxOrderId);
}
~~~

StepExecutionContext chứa giá trị riêng của partition hiện tại. Khi worker cho partition 0 chạy, reader nhận min/max của partition 0; worker cho partition 1 nhận phạm vi khác.

### Vì sao cần @StepScope?

Worker Step có thể được thực thi nhiều lần cho nhiều partition. Nếu reader được tạo một lần và giữ min/max trong field, các worker có thể dùng chung một instance và ghi đè dữ liệu phạm vi của nhau.

@StepScope trì hoãn việc tạo bean đến khi có StepExecution cụ thể. Nhờ vậy, mỗi partition nhận một instance reader được khởi tạo với ExecutionContext của chính nó.

Các thành phần phụ thuộc vào partition context như reader, processor hoặc writer cũng có thể cần Step scope. Không cần đặt scope cho mọi bean; chỉ dùng khi bean cần truy cập dữ liệu gắn với StepExecution hoặc cần instance riêng cho mỗi StepExecution.

ExecutionContext nên chứa dữ liệu nhỏ, có thể lưu trong JobRepository và có thể serialize theo cơ chế đang dùng. Không nên đưa cả danh sách hàng triệu ID, connection, stream, service object hoặc payload lớn vào context.

## 5. Cấu hình Worker Step

Worker Step thường là một chunk-oriented Step giống Step thông thường. Điểm khác biệt là reader hoặc các thành phần khác nhận phạm vi từ StepExecutionContext.

Ví dụ:

~~~java
@Bean
public Step orderWorkerStep(
        JobRepository jobRepository,
        @Qualifier("businessTransactionManager")
        PlatformTransactionManager transactionManager,
        ItemReader<Order> orderReader,
        ItemProcessor<Order, Order> orderProcessor,
        ItemWriter<Order> orderWriter) {

    return new StepBuilder("orderWorkerStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .build();
}
~~~

Worker xử lý 100 item mỗi chunk trong phạm vi ID mà reader nhận từ partition context. Mỗi partition có StepExecution riêng, nên read count, write count, status và ExecutionContext của worker được theo dõi độc lập.

Nếu worker sử dụng reader có trạng thái, hãy bảo đảm reader triển khai ItemStream hoặc dùng implementation hỗ trợ restart. Mỗi partition phải có checkpoint riêng để restart một partition không làm thay đổi tiến độ của partition khác.

## 6. Cấu hình Master Step bằng StepBuilder

Với Spring Batch 5 trở lên, có thể cấu hình master Step chạy partition bằng TaskExecutorPartitionHandler thông qua StepBuilder:

~~~java
@Bean
public Step orderManagerStep(
        JobRepository jobRepository,
        Step orderWorkerStep,
        Partitioner orderPartitioner,
        TaskExecutor partitionTaskExecutor) {

    return new StepBuilder("orderManagerStep", jobRepository)
            .partitioner(orderWorkerStep.getName(), orderPartitioner)
            .step(orderWorkerStep)
            .gridSize(4)
            .taskExecutor(partitionTaskExecutor)
            .build();
}
~~~

Ý nghĩa các phần:

- orderManagerStep là tên master Step được lưu trong JobRepository.
- partitioner(...) cung cấp Partitioner để tạo các ExecutionContext.
- step(orderWorkerStep) chỉ định worker Step sẽ được chạy cho từng partition.
- gridSize(4) đưa ra quy mô partition mong muốn cho quá trình chia việc.
- taskExecutor(...) cấu hình việc thực thi worker bằng executor.

Grid size là đầu vào cho quá trình tạo partition và cấu hình handler. Số partition thực tế được quyết định bởi Map mà Partitioner trả về. Một Partitioner tùy chỉnh có thể trả về ít hơn hoặc nhiều hơn grid size nếu logic chia việc yêu cầu; vì vậy không nên xem grid size là cam kết cứng về số partition.

### Cấu hình TaskExecutor

Ví dụ dùng ThreadPoolTaskExecutor:

~~~java
@Bean
public TaskExecutor partitionTaskExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(0);
    executor.setThreadNamePrefix("order-partition-");
    return executor;
}
~~~

Executor trên cho phép tối đa bốn worker chạy đồng thời. Khi Spring quản lý bean, lifecycle của ThreadPoolTaskExecutor được khởi tạo và đóng theo container. Nếu tự tạo executor ngoài Spring, ứng dụng phải quản lý vòng đời thread pool.

Không nên đặt số thread chỉ theo số CPU. Worker có thể bị giới hạn bởi database connection, I/O, API ngoài hoặc lock. Số worker đồng thời phải nằm trong khả năng chịu tải của các hệ thống phụ thuộc.

## 7. Đưa Master Step vào Job flow

Master Step được khai báo như một Step trong Job. Sau khi tất cả partition được xử lý và kết quả được tổng hợp, Job có thể chuyển sang Step tiếp theo:

~~~java
@Bean
public Job orderImportJob(
        JobRepository jobRepository,
        Step orderManagerStep,
        Step publishImportSummaryStep) {

    return new JobBuilder("orderImportJob", jobRepository)
            .start(orderManagerStep)
            .next(publishImportSummaryStep)
            .build();
}
~~~

Job flow chỉ chuyển đến publishImportSummaryStep sau khi orderManagerStep kết thúc theo trạng thái tương ứng. Nếu một worker partition thất bại và master Step kết thúc FAILED, flow mặc định sẽ không tiếp tục như một lần hoàn tất bình thường, trừ khi có transition xử lý nhánh lỗi.

Master Step có StepExecution riêng. Các worker StepExecution là các execution con được liên kết với cùng JobExecution và được lưu trong JobRepository.

## 8. PartitionHandler điều phối worker

PartitionHandler là abstraction chịu trách nhiệm thực thi các partition. Nó nhận StepExecutionSplitter và StepExecution của master, sau đó khởi chạy các worker và trả về tập StepExecution tương ứng.

Có hai hướng triển khai thường gặp:

**Local partitioning:** worker chạy trong cùng JVM, thường thông qua TaskExecutorPartitionHandler. Cách này đơn giản để mở rộng xử lý trên nhiều thread trong một ứng dụng.

**Remote partitioning:** master gửi yêu cầu thực thi partition qua middleware hoặc message channel đến worker process khác. Worker thực thi Step và gửi kết quả trở lại master. Cách này phù hợp khi muốn phân phối tải trên nhiều process hoặc máy.

~~~text
Local partitioning

Master Step
    |
    v
TaskExecutorPartitionHandler
    |
    +--> Worker thread 1
    +--> Worker thread 2
    +--> Worker thread 3
    +--> Worker thread 4


Remote partitioning

Master Step
    |
    v
Messaging / middleware
    |
    +--> Worker process A
    +--> Worker process B
    +--> Worker process C
    |
    v
Kết quả gửi về master
~~~

Với local partitioning, dữ liệu partition và bean được truyền trong cùng ứng dụng. Với remote partitioning, cần thêm cơ chế serialize message, định tuyến, retry message, xử lý worker mất kết nối và bảo đảm metadata repository được chia sẻ hoặc cấu hình đúng giữa master và worker.

Remote partitioning khác với remote chunking. Trong remote partitioning, mỗi worker chạy một Step độc lập trên một partition dữ liệu. Trong remote chunking, manager đọc và gửi chunk cho worker xử lý/ghi theo mô hình khác. Chọn đúng mô hình theo nơi cần thực hiện reader và cách phân phối công việc.

## 9. Master tổng hợp trạng thái partition

Mỗi partition có StepExecution riêng. Khi worker kết thúc, kết quả được trả về handler và master Step tổng hợp trạng thái.

Ví dụ:

~~~text
Master: orderManagerStep
    |
    +-- partition0: COMPLETED
    +-- partition1: COMPLETED
    +-- partition2: FAILED
    +-- partition3: COMPLETED
             |
             v
      Master Step: FAILED
~~~

Nếu một partition thất bại, master thường không thể xem toàn bộ công việc là hoàn tất. Master Step có thể kết thúc FAILED sau khi handler thu kết quả. Flow Job sẽ xử lý theo trạng thái của master Step.

Không nên chỉ kiểm tra trạng thái master mà bỏ qua trạng thái từng worker. Khi điều tra, cần biết partition nào thất bại, partition nào đã commit dữ liệu và partition nào chưa bắt đầu.

Có thể tra cứu StepExecution của JobExecution qua JobExplorer để xem trạng thái từng worker. Tên StepExecution của partition thường bao gồm tên worker Step và tên partition, nhưng nên dùng metadata thực tế thay vì tự ghép chuỗi để xác định ID.

## 10. Cách chia partition cân bằng

Chất lượng partition ảnh hưởng trực tiếp đến thời gian hoàn tất toàn Job. Nếu các partition có khối lượng khác nhau nhiều, các worker nhanh sẽ kết thúc sớm và chờ partition chậm nhất.

Ví dụ chia theo khoảng ID:

| Partition | Phạm vi ID | Số item thực tế |
| --- | --- | ---: |
| 0 | 1-250000 | 240000 |
| 1 | 250001-500000 | 18000 |
| 2 | 500001-750000 | 220000 |
| 3 | 750001-1000000 | 6000 |

Khoảng ID bằng nhau không đảm bảo số item bằng nhau nếu dữ liệu có khoảng trống hoặc phân bố lệch.

Một số chiến lược chia:

- **Range partitioning:** chia theo khoảng khóa hoặc thời gian. Đơn giản, dễ quan sát, nhưng cần kiểm tra phân bố.
- **Hash partitioning:** dùng hash của khóa để phân tán dữ liệu. Có thể cân bằng tốt nếu khóa phân bố phù hợp, nhưng cần điều kiện truy vấn tương ứng.
- **Tenant partitioning:** mỗi tenant hoặc nhóm tenant là một partition. Phù hợp khi ranh giới dữ liệu theo khách hàng.
- **Date partitioning:** chia theo ngày, tháng hoặc kỳ nghiệp vụ. Dễ đối soát nhưng cần cân nhắc các kỳ có tải khác nhau.
- **File partitioning:** mỗi file hoặc nhóm file là một partition. Phù hợp với pipeline xử lý file độc lập.

Nên đo số item và chi phí xử lý thực tế của từng partition. Nếu một số bản ghi nặng hơn nhiều, cân bằng theo số item chưa chắc cân bằng theo thời gian xử lý.

## 11. Restart khi một partition thất bại

Partitioning hỗ trợ restart nhờ metadata của từng worker StepExecution và ExecutionContext. Nếu một partition thất bại, JobExecution của master có thể kết thúc FAILED. Khi restart cùng JobInstance, Spring Batch sử dụng metadata để xác định partition nào đã hoàn tất và partition nào cần chạy lại, tùy cấu hình và khả năng restart của worker.

~~~text
Lần chạy đầu:

partition0 -> COMPLETED
partition1 -> COMPLETED
partition2 -> FAILED
partition3 -> COMPLETED

Restart:

partition0 -> đã hoàn tất, thường được bỏ qua
partition1 -> đã hoàn tất, thường được bỏ qua
partition2 -> chạy lại từ checkpoint của worker nếu có
partition3 -> đã hoàn tất, thường được bỏ qua
~~~

Để restart đúng:

- Giữ nguyên Job name và identifying JobParameters.
- Giữ ổn định tên partition hoặc quy tắc ánh xạ partition.
- Bảo đảm Partitioner tạo lại phạm vi nhất quán với lần chạy trước.
- Worker reader/writer phải lưu checkpoint nếu cần tiếp tục giữa partition.
- Side effect phải idempotent vì partition thất bại có thể được thực hiện lại.

Nếu Partitioner dựa trên dữ liệu nguồn đang thay đổi, lần restart có thể tạo phạm vi khác với lần chạy đầu. Nên dùng input snapshot, watermark hoặc tham số xác định phạm vi dữ liệu để việc phân chia ổn định.

### Partitioner và tên partition ổn định

Tên partition là một phần quan trọng để Spring Batch liên kết execution và trạng thái. Không tạo tên ngẫu nhiên cho mỗi lần gọi partitioner nếu mục tiêu là restart cùng partition.

Ví dụ tên ổn định:

~~~text
partition0
partition1
partition2
partition3
~~~

ExecutionContext của partition cũng cần giữ ý nghĩa ổn định. Nếu partition0 trước đây đại diện cho order ID 1-250000 nhưng sau triển khai mới lại đại diện cho 500001-750000, checkpoint cũ có thể được áp dụng sai phạm vi.

Khi thay đổi thuật toán partitioning hoặc số partition giữa các phiên bản, cần có chiến lược tương thích và xử lý metadata cũ. Không nên thay đổi cách chia dữ liệu khi còn JobExecution đang cần restart mà chưa đánh giá ảnh hưởng.

## 12. Lưu ý về dữ liệu dùng chung và transaction

Partitioning giúp worker xử lý độc lập nhưng không tự tạo transaction phân tán hoặc bảo đảm dữ liệu không tranh chấp.

Khi thiết kế worker:

- Mỗi partition nên có phạm vi dữ liệu không chồng lấn nếu cùng ghi vào một bảng.
- Các unique key và constraint của database vẫn cần bảo vệ dữ liệu.
- Reader và writer nên được cấu hình với transaction manager phù hợp.
- Connection pool phải đủ cho số worker đồng thời nhưng không vượt giới hạn database.
- Tránh để nhiều partition cập nhật cùng một bản ghi hoặc cùng một tài nguyên tuần tự.
- Nếu metadata và dữ liệu nghiệp vụ dùng các database khác nhau, cần hiểu rõ khả năng commit lệch nhau.

Mỗi worker có transaction của riêng StepExecution/chunk. Transaction của partition này không tự động rollback transaction đã commit ở partition khác. Nếu partition 2 thất bại sau khi các partition khác hoàn tất, dữ liệu đã commit của các partition thành công vẫn còn.

Do đó, worker cần idempotent hoặc có khóa nghiệp vụ để khi restart không ghi trùng. Nếu nghiệp vụ yêu cầu tất cả partition thành công hoặc không partition nào được giữ kết quả, cần thiết kế staging và bước publish/commit ở cấp nghiệp vụ; không thể dựa vào transaction chunk riêng lẻ để tạo atomicity toàn Job.

## 13. Thread safety và tài nguyên dùng chung

Với local partitioning, nhiều worker có thể chạy trong cùng JVM. Các bean singleton được chia sẻ nếu không dùng scope phù hợp. Vì vậy:

- Reader giữ cursor hoặc vị trí đọc thường cần instance riêng cho từng StepExecution.
- Writer có state nội bộ cần được kiểm tra thread safety.
- Processor không nên giữ mutable state dùng chung nếu không đồng bộ.
- Repository/service dùng chung phải an toàn khi được gọi đồng thời.
- Các buffer, file handle và client connection phải có vòng đời rõ ràng.

@StepScope là lựa chọn thường dùng cho reader/processor/writer phụ thuộc vào StepExecutionContext. Tuy nhiên, scope không tự làm mọi collaborator thread-safe; service singleton được inject vào bean step-scoped vẫn có thể được nhiều worker gọi đồng thời.

Nếu các partition ghi file, nên ghi file riêng theo partition rồi hợp nhất sau khi hoàn tất. Tránh nhiều worker cùng ghi một file tuần tự nếu writer không hỗ trợ concurrency.

## 14. Điều chỉnh grid size và concurrency

Grid size, số partition thực tế và số worker chạy đồng thời là các khái niệm có liên quan nhưng không giống nhau:

- **Grid size:** quy mô được đưa vào cấu hình partitioning và handler.
- **Partition count:** số entry Partitioner thực sự trả về.
- **Concurrency:** số worker có thể chạy cùng lúc theo TaskExecutor hoặc hạ tầng remote.

Ví dụ Partitioner có thể tạo 12 partition nhưng TaskExecutor chỉ cho phép 4 worker chạy đồng thời. Khi đó các partition còn lại chờ lượt.

~~~text
12 partitions
    |
    v
TaskExecutor: max 4 workers
    |
    +-- Batch 1: partition 0-3
    +-- Batch 2: partition 4-7
    +-- Batch 3: partition 8-11
~~~

Tăng số partition không nhất thiết tăng throughput nếu số worker đồng thời không đổi. Nó có thể giúp cân bằng tải tốt hơn hoặc tạo đơn vị restart nhỏ hơn, nhưng cũng làm tăng metadata và overhead điều phối.

Tăng số worker có thể tăng throughput cho đến khi database, network, CPU hoặc hệ thống đích đạt giới hạn. Theo dõi connection pool, lock wait, CPU, I/O và thời gian hoàn tất từng partition để điều chỉnh.

## 15. Quan sát và chẩn đoán Master Step

Master Step và worker StepExecution đều được lưu trong JobRepository. Có thể dùng JobExplorer để lấy lịch sử thực thi và kiểm tra trạng thái từng partition.

Ví dụ:

~~~java
JobExecution execution =
        jobExplorer.getJobExecution(jobExecutionId);

if (execution != null) {
    for (StepExecution stepExecution : execution.getStepExecutions()) {
        log.info(
                "step={}, status={}, read={}, write={}, commits={}, rollbacks={}",
                stepExecution.getStepName(),
                stepExecution.getStatus(),
                stepExecution.getReadCount(),
                stepExecution.getWriteCount(),
                stepExecution.getCommitCount(),
                stepExecution.getRollbackCount());
    }
}
~~~

Khi điều tra, hãy xem:

- Master Step có bắt đầu và hoàn tất hay không.
- Partitioner trả về bao nhiêu partition.
- Tên và ExecutionContext của từng partition.
- Worker nào đã bắt đầu, hoàn tất hoặc thất bại.
- Read/write/skip count của từng worker.
- Thời gian chạy và thời gian chờ của mỗi partition.
- Exception gốc của worker thất bại.
- Checkpoint và side effect đã commit.

Nếu một partition chạy lâu bất thường, kiểm tra phân bố dữ liệu và truy vấn reader. Nếu tất cả worker chậm, có thể bottleneck nằm ở database, connection pool hoặc hệ thống dùng chung thay vì cách chia partition.

## 16. Những lỗi thường gặp

### Master Step bị dùng như worker Step

Master điều phối partition; worker mới đọc và ghi dữ liệu. Không đặt logic xử lý toàn bộ dữ liệu vào master rồi mong PartitionHandler tự chia công việc.

### Partitioner tạo phạm vi bị chồng lấn

Hai worker cùng đọc một bản ghi có thể gây ghi trùng hoặc tranh chấp. Xác định ranh giới inclusive/exclusive rõ ràng và kiểm tra các khoảng không giao nhau.

### Dùng singleton reader cho nhiều partition

Reader có state có thể bị các worker ghi đè vị trí đọc. Dùng Step scope hoặc cơ chế tạo instance riêng phù hợp.

### Đưa dữ liệu lớn vào ExecutionContext

ExecutionContext là metadata, không phải nơi truyền hàng triệu item. Chỉ lưu khóa, phạm vi và tham số nhỏ để worker tự truy cập nguồn.

### Nhầm grid size với số worker đồng thời

Partitioner có thể tạo nhiều partition hơn số thread. Kiểm tra cả Map trả về và giới hạn TaskExecutor.

### Thay đổi partition mapping khi restart

Checkpoint cũ có thể được áp dụng cho phạm vi mới. Giữ partition name và mapping ổn định trong suốt vòng đời JobInstance cần restart.

### Cho rằng mọi partition cùng rollback khi một partition lỗi

Transaction của các worker độc lập. Partition đã commit vẫn giữ dữ liệu khi partition khác thất bại. Thiết kế idempotency hoặc staging nếu cần phục hồi ở cấp toàn Job.

### Chia đều theo ID nhưng tải không đều

ID có thể có khoảng trống hoặc dữ liệu phân bố lệch. Đo số item và thời gian xử lý thực tế để chọn chiến lược partition.

### Tăng concurrency vượt khả năng database

Nhiều worker có thể làm cạn connection pool, tăng lock contention hoặc làm database quá tải. Điều chỉnh thread pool và pool connection cùng nhau.

### Không xử lý lỗi worker

Master cần quan sát kết quả của từng partition và Job flow cần có nhánh lỗi phù hợp. Đừng bỏ qua worker FAILED chỉ vì các partition khác đã hoàn tất.

## 17. Quy trình thiết kế Master/Worker partitioning

Khi xây dựng partitioned Step, hãy lần lượt xác định:

1. Dữ liệu được chia theo khóa, ngày, tenant, file hay một quy tắc nghiệp vụ nào?
2. Partitioner có tạo phạm vi không chồng lấn và có thể tái tạo ổn định không?
3. ExecutionContext cần truyền những giá trị nào cho worker?
4. Reader, processor và writer nào cần @StepScope?
5. Worker Step dùng transaction manager và chunk size nào?
6. Local hay remote PartitionHandler phù hợp với yêu cầu triển khai?
7. Grid size, số partition và concurrency nên được đặt ở mức nào?
8. Các worker có tranh chấp tài nguyên hoặc ghi cùng dữ liệu không?
9. Khi một partition thất bại, các partition đã commit được xử lý thế nào?
10. Restart có giữ nguyên JobParameters, partition names, mapping và checkpoint không?
11. JobExplorer và log có đủ thông tin xác định worker lỗi không?
12. Có cần Step tổng hợp hoặc publish kết quả sau khi tất cả partition hoàn tất không?

Nên thử nghiệm với dữ liệu có phân bố thực tế, tạo lỗi có kiểm soát ở một worker và restart Job để xác nhận các partition đã hoàn tất được xử lý đúng, partition thất bại được khôi phục và không phát sinh dữ liệu trùng.

## Kết luận

Master Step là bộ điều phối trong Spring Batch partitioning. Nó dùng Partitioner để tạo các partition cùng ExecutionContext, dùng StepExecutionSplitter và PartitionHandler để phân phối worker Step, sau đó thu và tổng hợp trạng thái của các worker. Worker Step thực hiện xử lý dữ liệu trong phạm vi riêng và lưu checkpoint theo StepExecution. Để partitioning mở rộng và restart an toàn, cần phân vùng không chồng lấn, mapping và tên partition ổn định, Step-scoped components phù hợp, concurrency nằm trong khả năng hệ thống và side effect có tính idempotent.
