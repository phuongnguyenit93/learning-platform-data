# Partition context và metadata

Trong Spring Batch, partitioning chia một Step lớn thành nhiều worker StepExecution độc lập. Mỗi worker xử lý một phần dữ liệu, chẳng hạn một khoảng ID, một nhóm file hoặc một tập tenant. Để worker biết phần việc của mình và có thể tiếp tục sau lỗi, Spring Batch gắn một ExecutionContext riêng với từng partition rồi lưu context đó cùng metadata của StepExecution trong JobRepository.

Cần phân biệt ba loại thông tin: dữ liệu đầu vào của Job nằm trong JobParameters; tham số phân vùng và checkpoint riêng của worker nằm trong Step ExecutionContext; metadata về trạng thái, thời gian và kết quả thực thi nằm trong JobRepository. Hiểu đúng mối quan hệ này giúp chia việc không chồng lấn, quan sát được từng worker và restart đúng partition còn dang dở.

## 1. Partitioning tạo nhiều worker StepExecution

Một partitioned Step thường có một manager Step điều phối và một worker Step thực hiện xử lý. Manager xác định các partition, tạo StepExecution tương ứng và giao chúng cho handler. Mỗi partition có một tên ổn định và một ExecutionContext riêng.

Ví dụ Job xử lý đơn hàng theo khoảng ID:

~~~text
importOrdersJob
      |
      v
managerStep
      |
      | tạo các partition
      |
      +------------------------------+
      |              |               |
      v              v               v
worker:partition0 worker:partition1 worker:partition2
  ID 1..1000        ID 1001..2000     ID 2001..3000
      |              |               |
      v              v               v
  StepExecution   StepExecution   StepExecution
  + context       + context       + context
~~~

Mỗi worker là một StepExecution riêng. Nó có status, counters, thời gian bắt đầu/kết thúc và ExecutionContext riêng. Vì vậy, partitioning không chỉ chia dữ liệu; nó còn tạo các đơn vị thực thi có metadata riêng để theo dõi và restart.

gridSize là số partition mục tiêu mà manager yêu cầu tạo. Số worker thực sự chạy đồng thời còn phụ thuộc handler và executor. Ví dụ có thể tạo 8 partition nhưng chỉ cho phép 4 thread chạy cùng lúc.

## 2. Partitioner tạo partition context

Interface Partitioner nhận grid size và trả về map từ tên partition sang ExecutionContext:

~~~java
public interface Partitioner {
    Map<String, ExecutionContext> partition(int gridSize);
}
~~~

Mỗi entry trong map đại diện cho một phần việc. Key là tên partition; value là context chứa tham số cần thiết để worker xử lý đúng phạm vi.

Ví dụ context cho ba partition:

~~~java
Map<String, ExecutionContext> partitions = new HashMap<>();

ExecutionContext first = new ExecutionContext();
first.putLong("minId", 1L);
first.putLong("maxIdExclusive", 1001L);
partitions.put("partition0", first);

ExecutionContext second = new ExecutionContext();
second.putLong("minId", 1001L);
second.putLong("maxIdExclusive", 2001L);
partitions.put("partition1", second);

ExecutionContext third = new ExecutionContext();
third.putLong("minId", 2001L);
third.putLong("maxIdExclusive", 3001L);
partitions.put("partition2", third);
~~~

Các context này là dữ liệu đầu vào cho worker StepExecution. Worker có thể dùng minId và maxIdExclusive để tạo truy vấn riêng.

Nên dùng khoảng nửa mở [minId, maxIdExclusive): giá trị bắt đầu được bao gồm, giá trị kết thúc không được bao gồm. Quy ước này giúp ghép các khoảng liên tiếp mà không bị trùng biên:

- Partition 0: id >= 1 AND id < 1001.
- Partition 1: id >= 1001 AND id < 2001.
- Partition 2: id >= 2001 AND id < 3001.

Nếu dùng khoảng inclusive ở cả hai đầu, phải đặc biệt cẩn thận khi tính biên để không xử lý trùng hoặc bỏ sót bản ghi.

## 3. Xây dựng Partitioner theo khoảng ID

Ví dụ sau minh họa cách chia một miền ID liên tục thành các khoảng có kích thước gần bằng nhau. Trong ứng dụng thật, min/max nên được lấy từ nguồn dữ liệu hoặc từ một snapshot đã xác định.

~~~java
public class CustomerRangePartitioner implements Partitioner {

    private final long minId;
    private final long maxIdExclusive;

    public CustomerRangePartitioner(
            long minId,
            long maxIdExclusive) {
        if (minId > maxIdExclusive) {
            throw new IllegalArgumentException("Invalid ID range");
        }
        this.minId = minId;
        this.maxIdExclusive = maxIdExclusive;
    }

    @Override
    public Map<String, ExecutionContext> partition(int gridSize) {
        if (gridSize <= 0) {
            throw new IllegalArgumentException(
                    "gridSize must be positive");
        }

        Map<String, ExecutionContext> result = new LinkedHashMap<>();

        long total = maxIdExclusive - minId;
        if (total == 0) {
            return result;
        }

        long targetSize = (total + gridSize - 1) / gridSize;
        long start = minId;
        int index = 0;

        while (start < maxIdExclusive) {
            long end = Math.min(start + targetSize, maxIdExclusive);

            ExecutionContext context = new ExecutionContext();
            context.putLong("minId", start);
            context.putLong("maxIdExclusive", end);

            result.put("partition" + index, context);
            start = end;
            index++;
        }

        return result;
    }
}
~~~

Đây là ví dụ minh họa cho miền ID đã biết và các phép tính nằm trong giới hạn long. Với dữ liệu production, cần xử lý overflow khi tính tổng, target size hoặc biên; đồng thời xác định rõ hành vi khi nguồn rỗng, ID thưa hoặc có khoảng trống lớn.

Chia theo min/max không đảm bảo mỗi partition có cùng số bản ghi nếu ID không liên tục. Nếu dữ liệu phân bố lệch, một partition có thể nặng hơn các partition khác. Có thể chia theo số thứ tự, hash, tenant, ngày hoặc truy vấn phân phối dữ liệu để cân bằng workload tốt hơn.

## 4. Đưa partition context vào worker Step

Worker Step có thể dùng @StepScope và expression stepExecutionContext để nhận tham số của partition.

~~~java
@Bean
@StepScope
JdbcCursorItemReader<Customer> customerReader(
        DataSource dataSource,
        @Value("#{stepExecutionContext['minId']}") Long minId,
        @Value("#{stepExecutionContext['maxIdExclusive']}")
        Long maxIdExclusive) {

    return new JdbcCursorItemReaderBuilder<Customer>()
            .name("customerReader")
            .dataSource(dataSource)
            .sql("""
                select id, name, email
                from customer
                where id >= ? and id < ?
                order by id
                """)
            .preparedStatementSetter(statement -> {
                statement.setLong(1, minId);
                statement.setLong(2, maxIdExclusive);
            })
            .rowMapper((rs, rowNum) -> new Customer(
                    rs.getLong("id"),
                    rs.getString("name"),
                    rs.getString("email")))
            .saveState(true)
            .build();
}
~~~

@StepScope trì hoãn việc tạo reader đến khi worker StepExecution đã tồn tại. Khi đó Spring có thể phân giải giá trị trong Step ExecutionContext của đúng partition.

Không tạo reader singleton chứa min/max mutable rồi thay giá trị trước mỗi partition. Nhiều worker có thể chạy đồng thời và ghi đè phạm vi của nhau. Dùng scope theo StepExecution để mỗi worker có reader và tham số riêng.

## 5. Cấu hình manager Step và worker Step

Một cấu hình partitioned Step gồm worker Step, Partitioner và manager Step. Với Spring Batch 5, cấu hình Java có thể theo dạng:

~~~java
@Bean
Step customerWorkerStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Customer> customerReader,
        ItemWriter<Customer> customerWriter) {

    return new StepBuilder("customerWorkerStep", jobRepository)
            .<Customer, Customer>chunk(100, transactionManager)
            .reader(customerReader)
            .writer(customerWriter)
            .build();
}

@Bean
Step customerManagerStep(
        JobRepository jobRepository,
        Step customerWorkerStep,
        Partitioner customerPartitioner,
        TaskExecutor taskExecutor) {

    return new StepBuilder("customerManagerStep", jobRepository)
            .partitioner(
                    "customerWorkerStep",
                    customerPartitioner)
            .step(customerWorkerStep)
            .gridSize(4)
            .taskExecutor(taskExecutor)
            .build();
}
~~~

Manager Step dùng partitioner để tạo các worker execution. TaskExecutor điều khiển concurrency trong local partitioning. Trong ví dụ, grid size là 4; executor cần được cấu hình với pool phù hợp với số worker được phép chạy cùng lúc và tài nguyên database.

Tên worker Step và tên partition nên ổn định. Spring Batch dùng định danh execution và partition để liên kết metadata qua các lần chạy. Đổi tên Step hoặc partition tùy tiện có thể làm restart khó khôi phục đúng execution cũ.

## 6. Partition context và Step ExecutionContext

Context do Partitioner trả về được dùng để khởi tạo context cho StepExecution của partition. Trong lúc worker chạy, các thành phần như reader và writer có thể bổ sung checkpoint vào chính Step context đó qua ItemStream lifecycle.

Ví dụ context của một worker có thể chứa:

~~~text
partition0 Step ExecutionContext
  minId = 1
  maxIdExclusive = 1001
  customerReader.currentPage = 3
  customerReader.lastId = 742
  orderWriter.lastCommittedId = 742
~~~

Các key minId và maxIdExclusive xác định phần việc của partition. Các key currentPage, lastId và lastCommittedId có thể là state runtime do reader/writer cập nhật để phục hồi sau lỗi.

Nên đặt namespace cho key để tránh trùng giữa partition parameters và state của component. Ví dụ có thể dùng partition.minId, customerReader.lastId và customerWriter.lastId.

Không nhầm context do Partitioner tạo với Job ExecutionContext. Partition context thuộc worker StepExecution. Mỗi partition có bản riêng; việc một worker cập nhật context không tự động làm thay đổi context của worker khác.

## 7. Job context không phải vùng chia sẻ mutable cho các partition

Job ExecutionContext thuộc JobExecution và có phạm vi chung cho các Step trong Job. Trong khi đó, các partition có thể chạy đồng thời.

Nếu nhiều worker cùng ghi một key vào Job context, các cập nhật có thể ghi đè hoặc tạo ra kết quả không xác định theo thứ tự hoàn thành. Job context không phải một concurrent map để các worker dùng làm kênh trao đổi dữ liệu.

Nên tuân theo nguyên tắc:

- Dữ liệu đầu vào chung của Job được đặt trong JobParameters hoặc Job context nếu nó là metadata runtime cần chia sẻ.
- Tham số riêng của partition được đặt trong Step ExecutionContext của partition đó.
- Checkpoint reader/writer được đặt trong Step context của worker.
- Kết quả tổng hợp giữa các partition được tính bằng cơ chế aggregation hoặc lưu vào kho dữ liệu có đồng bộ.

Ví dụ, nếu mỗi partition đếm số bản ghi đã xử lý, không để tất cả worker cùng cập nhật jobExecutionContext['processedCount']. Hãy dùng StepExecution counters, aggregator hoặc bảng kết quả có khóa theo partition rồi tổng hợp sau.

## 8. Metadata của partition được lưu trong JobRepository

JobRepository lưu metadata của JobInstance, JobExecution, StepExecution và ExecutionContext. Trong JDBC repository, các bảng thường gặp gồm:

| Metadata | Bảng JDBC thường gặp |
|---|---|
| JobInstance | BATCH_JOB_INSTANCE |
| JobExecution | BATCH_JOB_EXECUTION |
| Job ExecutionContext | BATCH_JOB_EXECUTION_CONTEXT |
| StepExecution | BATCH_STEP_EXECUTION |
| Step ExecutionContext | BATCH_STEP_EXECUTION_CONTEXT |

Tên bảng có thể thay đổi theo table prefix và schema của phiên bản Spring Batch. Các hàng StepExecution của worker được liên kết với JobExecution và có ExecutionContext riêng.

Metadata thường cho phép truy vấn:

- JobExecution nào đã khởi chạy manager Step.
- Partition nào đã được tạo.
- Worker StepExecution nào đang chạy, hoàn thành, thất bại hoặc dừng.
- Mỗi worker có read/write/skip/commit/rollback counters ra sao.
- Checkpoint nào được lưu trong context của từng worker.

Không cần tự tạo bảng metadata riêng chỉ để lưu trạng thái partition nếu JobRepository đã quản lý được thông tin đó. Nếu cần lưu kết quả nghiệp vụ chi tiết, hãy dùng bảng nghiệp vụ hoặc bảng audit riêng, không sửa cấu trúc BATCH_* để nhét dữ liệu tùy ý.

## 9. Serialization của partition context

ExecutionContext được JobRepository serialize trước khi persist. Vì vậy, giá trị mà Partitioner đặt vào context phải được serializer hiện tại hỗ trợ.

Các giá trị thường phù hợp:

- Long hoặc Integer cho ID và giới hạn.
- String cho mã tenant, tên file hoặc version.
- Boolean cho cờ xử lý.
- Các giá trị nhỏ, có cấu trúc ổn định và dễ khôi phục.

Ví dụ:

~~~java
ExecutionContext context = new ExecutionContext();
context.putLong("partition.minId", 1L);
context.putLong("partition.maxIdExclusive", 1001L);
context.putString("partition.sourceVersion", "snapshot-42");
~~~

Tránh đặt vào context:

- Danh sách hàng nghìn entity.
- Nội dung file hoặc payload lớn.
- JDBC Connection, stream, thread hay executor.
- JPA entity graph hoặc object phụ thuộc class không ổn định.
- Password, token, private key hoặc credential.

Với dữ liệu lớn, hãy lưu vào database, file hoặc object storage rồi đưa ID hay reference vào context. Serialization không phải mã hóa; ai có quyền đọc metadata có thể đọc các giá trị đã persist tùy format và quyền truy cập.

## 10. Checkpoint riêng và restart từng partition

Một ưu điểm quan trọng của partitioning là mỗi worker có state riêng. Nếu một partition thất bại, các partition khác đã hoàn thành có thể được giữ trạng thái completed. Khi restart cùng JobInstance, Spring Batch sử dụng metadata cũ để xác định worker nào cần tiếp tục.

Ví dụ:

~~~text
JobExecution lần đầu
  partition0 -> COMPLETED
  partition1 -> FAILED
  partition2 -> COMPLETED
  partition3 -> COMPLETED

Restart cùng JobInstance
  partition0 -> giữ kết quả completed
  partition1 -> restart từ checkpoint đã lưu
  partition2 -> giữ kết quả completed
  partition3 -> giữ kết quả completed
~~~

Để cơ chế này hoạt động đúng:

- Giữ nguyên identifying JobParameters của JobInstance.
- Duy trì tên manager Step, worker Step và partition ổn định.
- Duy trì ý nghĩa của các key trong partition context.
- Reader/writer cần hỗ trợ ItemStream nếu cần khôi phục checkpoint.
- Dữ liệu nguồn phải có thứ tự hoặc snapshot ổn định.
- Writer cần idempotent hoặc tham gia transaction để tránh ghi trùng khi retry/restart.

Nếu thay đổi grid size hoặc thuật toán phân vùng giữa lần chạy đầu và restart, cần kiểm tra cách các partition cũ được nhận diện và xử lý. Không tự tạo tên partition mới cho cùng phạm vi dữ liệu khi mục tiêu là restart execution cũ.

## 11. PartitionNameProvider và tên partition ổn định

Trong một số trường hợp, việc tính lại các partition rất tốn kém, ví dụ phải truy vấn hệ thống ngoài để tìm danh sách file hoặc tenant. PartitionNameProvider là extension point cho phép cung cấp danh sách tên partition khi framework cần biết tên, đặc biệt hữu ích trong luồng restart khi tên đã được tạo trước đó.

Điều kiện quan trọng là danh sách tên phải ổn định và tương ứng với các partition đã tạo. Nếu tên thay đổi, Spring Batch có thể không ghép được partition hiện tại với StepExecution metadata cũ.

Chỉ dùng PartitionNameProvider khi có thể xác định tên partition mà không cần tái tính toàn bộ context. Nếu phạm vi dữ liệu hoặc nguồn thay đổi, hãy lưu version hoặc snapshot identifier để bảo đảm context cũ vẫn có ý nghĩa.

## 12. Aggregation kết quả từ worker

Sau khi worker hoàn tất, manager cần tổng hợp trạng thái và counters của các StepExecution con. Spring Batch sử dụng cơ chế StepExecutionAggregator cho mục đích này.

Các thông tin thường cần tổng hợp:

- Trạng thái tổng thể của manager Step.
- Read, write, filter và skip counts.
- Commit và rollback counts.
- ExitStatus và lỗi của các worker.
- Thời gian hoặc thông tin vận hành cần hiển thị.

Aggregation trạng thái/counters không đồng nghĩa với việc hợp nhất mọi key trong ExecutionContext của worker vào Job context. Nếu mỗi partition có lastId hoặc outputFile riêng, không có một giá trị duy nhất để tự động gộp.

Nếu cần kết quả tổng hợp nghiệp vụ, hãy định nghĩa quy tắc rõ ràng. Ví dụ, tổng số đơn hàng là tổng counters; danh sách file đầu ra là collection các reference theo partition; trạng thái lỗi có thể lấy mức nghiêm trọng nhất theo quy tắc của Job.

Không để nhiều worker ghi đè cùng một key Job context để thay cho aggregator.

## 13. Remote partitioning và metadata dùng chung

Trong local partitioning, manager và worker thường chạy trong cùng ứng dụng nhưng trên các thread khác nhau. Trong remote partitioning, manager gửi công việc tới worker chạy ở process hoặc node khác thông qua middleware như message broker.

Mô hình khái quát:

~~~text
Manager application
  Partitioner
      |
      v
  JobRepository <-------------------------+
      |                                   |
      v                                   |
  StepExecution requests                  |
      |                                   |
      v                                   |
  Message broker                          |
      |                                   |
      +--------------+--------------------+
                     |
              Worker application
                     |
                     v
              JobRepository
                     |
                     v
           Worker StepExecution
                     |
                     v
             Step ExecutionContext
~~~

Trong remote partitioning, metadata repository cần được chia sẻ hoặc được cấu hình theo kiến trúc hỗ trợ để manager và worker cùng nhìn thấy các execution. Thông điệp điều phối xác định execution cần chạy; worker dùng metadata tương ứng để nạp StepExecution và partition context.

Cần bảo đảm:

- Manager và worker dùng chung JobRepository phù hợp.
- Cả hai bên có cùng định nghĩa Job/Step và phiên bản tương thích.
- Worker có quyền truy cập dữ liệu của partition được giao.
- Partition name và StepExecution ID được giữ ổn định.
- Transaction manager của worker quản lý đúng business resource.
- Lỗi gửi message, worker chết hoặc message được giao lại có thể được phục hồi.

Remote partitioning khác remote chunking. Partitioning gửi các đơn vị StepExecution độc lập cho worker; remote chunking thường có một manager đọc dữ liệu rồi gửi chunk tới worker để xử lý/ghi. Hai mô hình có vị trí reader, metadata và ranh giới công việc khác nhau.

## 14. Partition context với JobParameters

JobParameters mô tả yêu cầu chạy Job và tham gia xác định JobInstance nếu được đánh dấu identifying. Partition context mô tả phạm vi cụ thể mà một worker phải xử lý.

Ví dụ:

~~~text
JobParameters
  businessDate = 2026-11-15
  tenantGroup = enterprise

partition0 Step ExecutionContext
  minId = 1
  maxIdExclusive = 1001

partition1 Step ExecutionContext
  minId = 1001
  maxIdExclusive = 2001
~~~

Hai worker dùng chung businessDate và tenantGroup của Job, nhưng mỗi worker có khoảng ID riêng. Không cần tạo JobInstance mới cho từng partition; partition là các StepExecution thuộc cùng JobExecution.

Nếu một tham số làm thay đổi phạm vi dữ liệu của toàn Job, nó thường nên là JobParameter identifying. Nếu nó chỉ mô tả phần việc của một worker do Partitioner tạo ra, đặt nó trong partition Step context.

## 15. Theo dõi partition qua JobExplorer

JobExplorer cung cấp API đọc metadata đã lưu trong JobRepository. Có thể dùng nó để xem các JobExecution, StepExecution và trạng thái của từng worker.

Các thông tin vận hành hữu ích:

- JobExecution ID và JobInstance ID.
- Tên manager Step.
- Tên worker Step và partition.
- BatchStatus và ExitStatus của từng worker.
- Read/write/skip counts.
- Thời gian bắt đầu, kết thúc và thời gian chạy.
- ExecutionContext đã lưu, nếu quyền và API truy vấn cho phép.

Dashboard có thể hiển thị từng partition như một hàng:

| Partition | Phạm vi | Status | Read | Write |
|---|---|---|---:|---:|
| partition0 | ID 1–1000 | COMPLETED | 1000 | 998 |
| partition1 | ID 1001–2000 | FAILED | 430 | 420 |
| partition2 | ID 2001–3000 | COMPLETED | 1000 | 1000 |
| partition3 | ID 3001–4000 | COMPLETED | 1000 | 997 |

Phạm vi và số liệu trong bảng chỉ là ví dụ. Trong thực tế, lấy dữ liệu từ metadata và context đã lưu; không suy đoán status từ log hoặc từ số message đã gửi.

Không truy vấn trực tiếp hoặc sửa bảng BATCH_* để điều khiển worker. Dùng JobExplorer để đọc và JobRepository/framework API để quản lý execution.

## 16. Các lỗi thường gặp khi thiết kế partition context

**Dùng chung một Job context cho mọi worker.** Các worker chạy đồng thời có thể ghi đè nhau. Đặt phạm vi riêng trong Step context của từng partition.

**Tên partition không ổn định.** Restart không ghép được worker mới với metadata cũ. Dùng tên deterministic và giữ quy ước qua các lần triển khai.

**Khoảng dữ liệu chồng lấn hoặc bị hở.** Bản ghi bị xử lý hai lần hoặc bị bỏ sót. Dùng quy ước biên rõ ràng và kiểm tra coverage.

**Thay đổi dữ liệu nguồn giữa các lần restart.** Checkpoint cũ có thể không còn tương ứng với cùng tập bản ghi. Dùng snapshot, watermark hoặc source version.

**Lưu object lớn vào context.** Metadata phình to và khó serialize. Chỉ lưu scalar hoặc reference.

**Không dùng Step scope.** Worker có thể nhận nhầm tham số hoặc chia sẻ reader state. Tạo component stateful theo StepExecution.

**Nhầm aggregation với context promotion.** Aggregator tổng hợp execution status/counters; promotion chuyển key được chọn từ Step context lên Job context. Hai cơ chế có mục đích khác nhau.

**Không chia sẻ repository trong remote partitioning.** Manager và worker không nhìn thấy cùng metadata, dẫn đến execution không được cập nhật đúng.

**Giả định gridSize là concurrency.** Grid size xác định số partition mục tiêu; executor/handler quyết định mức chạy đồng thời thực tế.

## 17. Bảo mật và vòng đời metadata

Partition context thường chứa business key, ID, tenant, đường dẫn file hoặc version nguồn. Chỉ lưu dữ liệu cần thiết để worker thực hiện và restart.

Không đưa secret vào context. Nếu worker cần credential, dùng secret manager và lưu reference không nhạy cảm. Hạn chế quyền đọc JobRepository vì người có thể đọc metadata có thể xem partition parameters và checkpoint.

Metadata partition có thể tồn tại lâu sau khi Job kết thúc để phục vụ audit và restart policy. Cần có retention/cleanup phù hợp, nhưng không xóa context của execution đang chạy hoặc còn cần restart. Dùng quy trình cleanup chính thức của Spring Batch và chính sách lưu trữ của tổ chức.

## 18. Kiểm thử partition context và metadata

Nên kiểm thử partitioner, worker Step và restart ở cả cấp thành phần và integration.

### Unit test cho Partitioner

Xác nhận:

- Grid size hợp lệ được xử lý đúng.
- Tên partition ổn định và duy nhất.
- Các phạm vi không chồng lấn.
- Tổng hợp các phạm vi bao phủ toàn bộ miền dữ liệu.
- Nguồn rỗng tạo kết quả rỗng theo chính sách.
- Biên đầu/cuối không gây mất hoặc lặp bản ghi.

Ví dụ với miền ID 1 đến 3000, ba partition nên bao phủ đúng các miền [1,1001), [1001,2001) và [2001,3001).

### Integration test với JobRepository

Chạy một Job partitioned và xác nhận:

1. Manager tạo đúng số worker StepExecution.
2. Mỗi worker nhận đúng partition context.
3. Step context của các worker được lưu riêng.
4. Counters và status của từng worker được cập nhật.
5. Manager nhận kết quả aggregation phù hợp.
6. Một worker thất bại có thể restart từ checkpoint.
7. Các partition đã hoàn thành không bị chạy lại ngoài chủ đích.
8. Job context không bị ghi đè bởi các worker đồng thời.

Với remote partitioning, kiểm thử thêm trường hợp message được giao lại, worker dừng giữa chừng, metadata repository tạm thời không sẵn sàng và worker chạy lại cùng StepExecution.

## 19. Quy trình thiết kế partition context

Khi xây dựng partitioned Step, hãy thực hiện theo thứ tự:

1. Xác định đơn vị phân vùng: khoảng ID, tenant, file, ngày hoặc nhóm dữ liệu.
2. Chọn tên partition deterministic và duy nhất trong Step.
3. Tạo ExecutionContext chỉ chứa tham số cần thiết cho worker.
4. Dùng Step scope để worker đọc đúng context của StepExecution.
5. Để reader/writer lưu checkpoint riêng trong Step context.
6. Dùng JobRepository để persist metadata và theo dõi từng worker.
7. Dùng aggregator cho status/counters; dùng cơ chế riêng cho kết quả nghiệp vụ cần hợp nhất.
8. Bảo đảm nguồn dữ liệu và thuật toán phân vùng ổn định qua restart.
9. Với remote partitioning, cấu hình manager và worker cùng nhìn thấy metadata repository phù hợp.
10. Kiểm thử phạm vi, concurrency, rollback, restart và message redelivery.

Partition context là hợp đồng dữ liệu giữa manager và worker. JobRepository biến hợp đồng đó thành metadata bền vững gắn với từng StepExecution. Khi mỗi partition có context riêng, tên ổn định, checkpoint phù hợp và dữ liệu nguồn có version rõ ràng, Spring Batch có thể điều phối nhiều worker, theo dõi tiến độ từng phần và restart đúng partition còn dang dở.

