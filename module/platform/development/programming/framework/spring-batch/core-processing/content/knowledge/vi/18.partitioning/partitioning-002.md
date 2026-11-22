# Partitioner tạo ExecutionContext cho từng partition trong Spring Batch

Trong Spring Batch, partitioning cho phép chia một Step lớn thành nhiều phần dữ liệu độc lập để xử lý bằng nhiều worker Step. Mỗi phần được gọi là một **partition**. Để worker biết mình phải xử lý phần dữ liệu nào, Spring Batch cần một mô tả đầu vào riêng cho từng partition.

Thành phần chịu trách nhiệm tạo các mô tả đó là **Partitioner**. Mỗi lần gọi, Partitioner trả về một map gồm tên partition và một **ExecutionContext** tương ứng. ExecutionContext chứa các giá trị như khoảng ID, ngày nghiệp vụ, mã tenant, tên file hoặc khóa phân vùng. Spring Batch dùng từng context để tạo StepExecution riêng cho worker.

Bài học này giải thích hợp đồng của Partitioner, cách tạo map partition ổn định, cách đưa dữ liệu vào ExecutionContext, cách worker đọc context bằng StepScope, cũng như cách thiết kế ranh giới dữ liệu, restart và kiểm thử để không bỏ sót hoặc xử lý trùng item.

## 1. Partitioner làm nhiệm vụ gì?

Một partitioned Step có hai vai trò:

- **Manager Step:** điều phối, chia công việc thành partition và khởi chạy các worker Step.
- **Worker Step:** thực hiện xử lý dữ liệu trong phạm vi của một partition.

Partitioner chỉ mô tả cách chia công việc. Nó không trực tiếp đọc và xử lý toàn bộ item, cũng không tự tạo thread. Spring Batch dùng kết quả của Partitioner để tạo StepExecution riêng cho từng partition và giao chúng cho cơ chế thực thi partition.

Ví dụ, một bảng có 1.000.000 khách hàng. Thay vì một worker đọc toàn bộ bảng, ứng dụng có thể chia ID thành bốn khoảng:

| Partition | Khoảng ID | Dữ liệu worker xử lý |
|---|---:|---|
| partition0 | 1–250000 | Khách hàng có ID từ 1 đến 250000 |
| partition1 | 250001–500000 | Khách hàng có ID từ 250001 đến 500000 |
| partition2 | 500001–750000 | Khách hàng có ID từ 500001 đến 750000 |
| partition3 | 750001–1000000 | Khách hàng có ID từ 750001 đến 1000000 |

Mỗi worker nhận một ExecutionContext chứa khoảng ID tương ứng. Worker dùng các giá trị này để truy vấn đúng phần dữ liệu của mình.

~~~mermaid
flowchart TD
    A["Manager Step"] --> B["Partitioner.partition(gridSize)"]
    B --> C["Map: partition0 -> ExecutionContext"]
    B --> D["Map: partition1 -> ExecutionContext"]
    B --> E["Map: partition2 -> ExecutionContext"]
    B --> F["Map: partition3 -> ExecutionContext"]
    C --> G["Worker StepExecution 0"]
    D --> H["Worker StepExecution 1"]
    E --> I["Worker StepExecution 2"]
    F --> J["Worker StepExecution 3"]
~~~

Mỗi partition có context và StepExecution riêng. Vì vậy, worker có thể chạy độc lập, có trạng thái riêng và được restart theo metadata của Spring Batch.

## 2. Hợp đồng của Partitioner

Spring Batch định nghĩa interface Partitioner:

~~~java
public interface Partitioner {
    Map<String, ExecutionContext> partition(int gridSize);
}
~~~

Phương thức nhận gridSize và trả về một map:

- Key là tên partition.
- Value là ExecutionContext chứa dữ liệu đầu vào của partition đó.

Ví dụ kết quả:

~~~java
Map<String, ExecutionContext> partitions = new LinkedHashMap<>();

ExecutionContext first = new ExecutionContext();
first.putLong("minId", 1L);
first.putLong("maxId", 250L);

partitions.put("partition0", first);
~~~

Khi Spring Batch tạo worker StepExecution, nó dùng tên partition để định danh execution và đưa ExecutionContext tương ứng vào phạm vi của worker.

### Tên partition có vai trò gì?

Tên partition cần duy nhất trong một lần chia và nên ổn định giữa các lần chạy lại cùng JobInstance. Tên thường là các giá trị dễ đọc như:

- partition0
- partition1
- region_APAC
- tenant_001
- file_20261115_01

Tên partition giúp nhận diện StepExecution, xem trạng thái trong JobRepository, đọc log và theo dõi worker nào thất bại.

Không nên tạo tên ngẫu nhiên bằng UUID mỗi lần gọi Partitioner nếu muốn restart nhận diện lại các partition cũ. Một tên mới có thể khiến Spring Batch xem đó là một partition khác.

### Map phải mô tả đầy đủ công việc

Mỗi ExecutionContext nên chứa đủ thông tin để worker xác định chính xác phần dữ liệu của mình. Ví dụ, nếu worker cần đọc theo khoảng ID, context phải chứa cả cận dưới và cận trên.

Không nên chỉ đưa một giá trị chung rồi để các worker tự suy đoán phạm vi. Logic chia dữ liệu cần được tập trung ở Partitioner để có thể kiểm tra tính đầy đủ, không chồng lấn và có thể tái tạo khi restart.

## 3. ExecutionContext của partition

ExecutionContext là một vùng lưu trữ key-value mà Spring Batch gắn với execution. Trong partitioning, mỗi partition có một ExecutionContext riêng.

Ví dụ:

~~~java
ExecutionContext context = new ExecutionContext();
context.putLong("minId", 1L);
context.putLong("maxId", 250L);
context.putString("region", "APAC");
context.putString("sourceBatchId", "BATCH-20261115");
~~~

Worker có thể đọc các key:

- minId: ID nhỏ nhất thuộc partition.
- maxId: ID lớn nhất thuộc partition.
- region: khu vực cần xử lý.
- sourceBatchId: mã lô dữ liệu nguồn.

### ExecutionContext không phải JobParameters

Hai loại dữ liệu có phạm vi khác nhau:

| Nơi lưu | Phạm vi | Ví dụ |
|---|---|---|
| JobParameters | Đầu vào nhận diện hoặc cấu hình một JobInstance | businessDate, sourceBatchId |
| JobExecutionContext | Dữ liệu được chia sẻ giữa các Step trong một JobExecution | đường dẫn work directory, thông tin tổng hợp |
| StepExecutionContext | Trạng thái riêng của một StepExecution, bao gồm worker partition | minId, maxId, partition-specific file |

Trong partitioning, dữ liệu Partitioner tạo ra được đặt vào StepExecutionContext của từng worker. Đây là lý do worker có thể đọc stepExecutionContext để lấy khoảng dữ liệu riêng.

Không nên đặt minId và maxId của mọi partition vào một JobExecutionContext chung rồi cho các worker cùng đọc. Các worker cần giá trị riêng, không ghi đè lẫn nhau.

### Giá trị trong context cần có thể lưu trữ

ExecutionContext được lưu trong JobRepository để hỗ trợ trạng thái và restart. Vì vậy, chỉ nên lưu các giá trị nhỏ, ổn định và có thể serialize, ví dụ:

- String.
- Long, Integer, Double hoặc Boolean.
- Ngày giờ hoặc kiểu dữ liệu được serializer cấu hình hỗ trợ.
- Các cấu trúc dữ liệu nhỏ có thể serialize an toàn.

Không đưa các đối tượng như JDBC Connection, ResultSet, InputStream, file handle, thread, Spring bean hoặc object không serialize được vào ExecutionContext. Hãy lưu thông tin nhận diện tài nguyên, chẳng hạn đường dẫn hoặc ID, rồi để worker mở tài nguyên khi chạy.

## 4. Viết RangePartitioner chia dữ liệu theo ID

Một chiến lược phổ biến là chia bảng theo khoảng ID. Ví dụ, dữ liệu có ID từ 1 đến 1.000 và muốn tạo bốn partition.

Mỗi partition nhận hai cận:

- minId: cận dưới, bao gồm.
- maxId: cận trên, bao gồm.

Worker truy vấn bằng điều kiện:

~~~sql
WHERE id >= :minId
  AND id <= :maxId
~~~

Các khoảng phải liền nhau và không chồng lấn. Ví dụ:

~~~text
partition0: [1, 250]
partition1: [251, 500]
partition2: [501, 750]
partition3: [751, 1000]
~~~

Một triển khai thực tế có thể dùng BigInteger để tính kích thước khoảng mà không bị tràn số khi miền ID rộng:

~~~java
public class RangePartitioner implements Partitioner {

    private final long minId;
    private final long maxId;

    public RangePartitioner(long minId, long maxId) {
        this.minId = minId;
        this.maxId = maxId;
    }

    @Override
    public Map<String, ExecutionContext> partition(int gridSize) {
        if (gridSize < 1) {
            throw new IllegalArgumentException(
                "gridSize phải lớn hơn 0"
            );
        }

        if (minId > maxId) {
            return Map.of();
        }

        BigInteger min = BigInteger.valueOf(minId);
        BigInteger max = BigInteger.valueOf(maxId);
        BigInteger total = max.subtract(min).add(BigInteger.ONE);
        BigInteger divisor = BigInteger.valueOf(gridSize);

        BigInteger targetSize = total
            .add(divisor)
            .subtract(BigInteger.ONE)
            .divide(divisor);

        Map<String, ExecutionContext> result =
            new LinkedHashMap<>();

        for (int i = 0; i < gridSize; i++) {
            BigInteger start = min.add(
                targetSize.multiply(BigInteger.valueOf(i))
            );

            if (start.compareTo(max) > 0) {
                break;
            }

            BigInteger end = start
                .add(targetSize)
                .subtract(BigInteger.ONE)
                .min(max);

            ExecutionContext context = new ExecutionContext();
            context.putLong("minId", start.longValueExact());
            context.putLong("maxId", end.longValueExact());

            result.put("partition" + i, context);
        }

        return result;
    }
}
~~~

Trong ví dụ:

- Nếu gridSize bằng 4, Partitioner tạo tối đa bốn partition.
- Nếu số bản ghi ít hơn gridSize, chỉ tạo số partition cần thiết.
- Các khoảng được chia liên tiếp.
- Cận trên của partition trước nhỏ hơn cận dưới của partition sau một đơn vị.
- Mỗi context chứa đúng hai giá trị biên cho worker.

Ví dụ dùng BigInteger giúp tránh tràn số trong phép tính tổng số ID và kích thước khoảng. longValueExact() bảo đảm giá trị đưa vào ExecutionContext vẫn nằm trong miền long.

### Vì sao dùng LinkedHashMap?

LinkedHashMap giữ thứ tự chèn của các partition. Thứ tự không phải điều kiện để dữ liệu được chia đúng, nhưng giúp log, debug và kiểm thử dễ đọc hơn.

Tên partition vẫn phải ổn định. Không dựa vào thứ tự map để tạo logic nghiệp vụ khác nhau.

## 5. Lấy minId và maxId từ database

Trong ứng dụng thực tế, khoảng dữ liệu có thể được xác định từ bảng nguồn:

~~~sql
SELECT MIN(customer_id), MAX(customer_id)
FROM customer_source
WHERE batch_id = :batchId
~~~

Có thể dùng JdbcTemplate để lấy giá trị:

~~~java
public RangePartitioner createPartitioner(
        JdbcTemplate jdbcTemplate,
        String batchId) {

    Long minId = jdbcTemplate.queryForObject(
        """
        SELECT MIN(customer_id)
        FROM customer_source
        WHERE batch_id = ?
        """,
        Long.class,
        batchId
    );

    Long maxId = jdbcTemplate.queryForObject(
        """
        SELECT MAX(customer_id)
        FROM customer_source
        WHERE batch_id = ?
        """,
        Long.class,
        batchId
    );

    if (minId == null || maxId == null) {
        return new RangePartitioner(1L, 0L);
    }

    return new RangePartitioner(minId, maxId);
}
~~~

Đây là ví dụ minh họa việc xác định biên. Trong cấu hình Spring Batch, Partitioner thường được đăng ký thành bean và nhận các dependency cần thiết qua constructor hoặc factory method.

### Phạm vi truy vấn phải thống nhất

Điều kiện lọc dùng để tìm min/max phải giống điều kiện nguồn mà worker dùng. Nếu Partitioner tính min/max trên toàn bảng nhưng worker chỉ đọc một batch, các khoảng có thể lớn hơn cần thiết. Nếu Partitioner lọc theo batch nhưng worker không lọc theo cùng batch ID, worker có thể đọc nhầm dữ liệu.

Hãy thống nhất các điều kiện:

- batch ID hoặc ngày nghiệp vụ.
- trạng thái bản ghi được phép xử lý.
- tenant hoặc region.
- điều kiện xóa mềm hoặc active flag.
- snapshot hoặc phiên bản dữ liệu.

Thông tin điều kiện chung có thể nằm trong JobParameters hoặc ExecutionContext, sau đó được worker sử dụng cùng với khoảng ID.

## 6. Xử lý nguồn rỗng

Khi bảng không có bản ghi phù hợp, MIN và MAX thường trả về null. Không nên chuyển null thành 0 rồi tạo một khoảng giả nếu ID 0 có thể là giá trị hợp lệ.

Có hai cách thiết kế phổ biến:

**Cách 1: xử lý NO_DATA trước partition Step.**

Một Step validation kiểm tra số lượng hoặc min/max. Nếu không có dữ liệu, flow đi sang nhánh NO_DATA hoặc kết thúc theo quy tắc nghiệp vụ. Partition Step chỉ chạy khi có dữ liệu.

**Cách 2: tạo một partition rỗng có chủ đích.**

Nếu muốn worker vẫn chạy để ghi nhận kết quả 0 item, có thể tạo một context có cờ empty=true. Worker đọc cờ đó và kết thúc mà không truy vấn nguồn.

Ví dụ context:

~~~java
ExecutionContext context = new ExecutionContext();
context.putBoolean("empty", true);

Map<String, ExecutionContext> partitions = new LinkedHashMap<>();
partitions.put("partition0", context);
~~~

Worker kiểm tra cờ này trước khi tạo hoặc sử dụng reader. Cách này giúp có StepExecution và metrics cho trường hợp nguồn rỗng.

Không nên trả về một range tùy tiện như 0 đến 0 nếu điều đó có thể đọc nhầm một bản ghi thực tế.

## 7. Đưa dữ liệu partition vào worker bằng StepScope

ExecutionContext của partition được gắn vào StepExecution của worker. Một bean có @StepScope có thể lấy giá trị bằng SpEL.

Ví dụ reader đọc theo khoảng ID:

~~~java
@Bean
@StepScope
JdbcCursorItemReader<Customer> customerReader(
        DataSource dataSource,
        @Value("#{stepExecutionContext['minId']}") Long minId,
        @Value("#{stepExecutionContext['maxId']}") Long maxId,
        @Value("#{jobParameters['batchId']}") String batchId) {

    return new JdbcCursorItemReaderBuilder<Customer>()
        .name("customerReader")
        .dataSource(dataSource)
        .sql("""
            SELECT customer_id, full_name, email
            FROM customer_source
            WHERE batch_id = ?
              AND customer_id >= ?
              AND customer_id <= ?
            ORDER BY customer_id
            """)
        .preparedStatementSetter(ps -> {
            ps.setString(1, batchId);
            ps.setLong(2, minId);
            ps.setLong(3, maxId);
        })
        .rowMapper((rs, rowNum) -> new Customer(
            rs.getLong("customer_id"),
            rs.getString("full_name"),
            rs.getString("email")
        ))
        .saveState(true)
        .build();
}
~~~

Trong ví dụ:

- minId và maxId đến từ StepExecutionContext của partition.
- batchId đến từ JobParameters chung của Job.
- @StepScope trì hoãn việc tạo reader đến khi worker StepExecution đã tồn tại.
- Reader chỉ truy vấn các bản ghi thuộc batch và khoảng ID của partition.

Nếu không dùng StepScope, Spring có thể tạo reader quá sớm, khi chưa có StepExecutionContext để inject giá trị. Khi đó late binding không hoạt động như mong muốn.

### Dùng context trong processor hoặc writer

Các bean khác của worker cũng có thể nhận giá trị partition qua StepScope. Ví dụ, writer có thể ghi tên partition vào cột audit:

~~~java
@Bean
@StepScope
ItemWriter<Customer> customerWriter(
        CustomerRepository repository,
        @Value("#{stepExecutionContext['partitionName']}")
        String partitionName) {

    return chunk -> {
        for (Customer customer : chunk.getItems()) {
            repository.saveProcessed(
                customer,
                partitionName
            );
        }
    };
}
~~~

Nếu muốn sử dụng partitionName, hãy đưa key đó vào ExecutionContext khi tạo partition:

~~~java
context.putString("partitionName", "partition" + i);
~~~

Tên partition cũng có thể được xác định từ StepExecution name. Lưu key riêng giúp worker truy cập trực tiếp, nhưng cần bảo đảm nó luôn đồng nhất với key map.

## 8. Cấu hình manager Step và worker Step

Worker Step là Step thực hiện xử lý chunk. Manager Step là partitioned Step điều phối các worker.

Ví dụ worker:

~~~java
@Bean
Step customerWorkerStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Customer> customerReader,
        ItemProcessor<Customer, ProcessedCustomer> customerProcessor,
        ItemWriter<ProcessedCustomer> customerWriter) {

    return new StepBuilder("customerWorkerStep", jobRepository)
        .<Customer, ProcessedCustomer>chunk(200, transactionManager)
        .reader(customerReader)
        .processor(customerProcessor)
        .writer(customerWriter)
        .build();
}
~~~

Cấu hình manager:

~~~java
@Bean
Step customerManagerStep(
        JobRepository jobRepository,
        Step customerWorkerStep,
        Partitioner customerPartitioner,
        TaskExecutor partitionTaskExecutor) {

    return new StepBuilder("customerManagerStep", jobRepository)
        .partitioner("customerWorkerStep", customerPartitioner)
        .step(customerWorkerStep)
        .gridSize(4)
        .taskExecutor(partitionTaskExecutor)
        .build();
}
~~~

gridSize(4) yêu cầu Partitioner tạo số partition mục tiêu là bốn. Nếu Partitioner trả về ít hơn bốn partition do nguồn nhỏ, số worker được tạo tương ứng với map trả về.

taskExecutor(...) cho phép manager điều phối worker bằng TaskExecutor. Số worker chạy đồng thời còn phụ thuộc giới hạn của executor, tài nguyên database và cấu hình hệ thống.

### Cấu hình TaskExecutor

Ví dụ dùng thread pool:

~~~java
@Bean
ThreadPoolTaskExecutor partitionTaskExecutor() {
    ThreadPoolTaskExecutor executor =
        new ThreadPoolTaskExecutor();

    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(20);
    executor.setThreadNamePrefix("batch-partition-");

    return executor;
}
~~~

Spring quản lý vòng đời bean TaskExecutor. Cần chọn pool size phù hợp với số partition, connection pool, CPU và khả năng chịu tải của database.

Grid size không đồng nghĩa với số thread. Ví dụ có 12 partition và pool size 4, tối đa bốn worker có thể chạy đồng thời; các partition còn lại được thực thi khi thread sẵn sàng.

## 9. Tạo Partitioner thành Spring bean

Có thể đăng ký Partitioner trực tiếp:

~~~java
@Bean
@StepScope
Partitioner customerPartitioner(
        JdbcTemplate jdbcTemplate,
        @Value("#{jobParameters['batchId']}") String batchId) {

    return new CustomerRangePartitioner(
        jdbcTemplate,
        batchId
    );
}
~~~

Nếu Partitioner cần đọc JobParameters, có thể dùng @StepScope hoặc một cách late binding phù hợp với thời điểm manager Step chạy. Tuy nhiên, Partitioner được gọi trong quá trình chuẩn bị partition của manager; hãy bảo đảm các giá trị runtime đã có ở đúng scope.

Một cách tổ chức rõ ràng là tạo bean Partitioner có dependency vào một service lấy range, sau đó service nhận batch ID từ JobParameters trong manager Step scope.

Ví dụ dùng một Partitioner đã biết biên:

~~~java
@Bean
@StepScope
Partitioner customerPartitioner(
        @Value("#{jobParameters['minId']}") Long minId,
        @Value("#{jobParameters['maxId']}") Long maxId) {

    return new RangePartitioner(minId, maxId);
}
~~~

Trong trường hợp cần late binding, bean có thể được khai báo với @StepScope để giá trị JobParameters được inject khi manager StepExecution đã tồn tại. Tránh tạo bean singleton có constructor nhận JobParameters runtime.

## 10. Đặt tên partition và lưu context ổn định

Tên partition và nội dung ExecutionContext ảnh hưởng đến restart. Spring Batch lưu StepExecution của từng partition trong JobRepository. Ví dụ tên worker execution có thể được tạo từ tên worker Step cộng với tên partition, như customerWorkerStep:partition0.

Để restart ổn định:

- Tạo tên partition có tính xác định.
- Dùng cùng quy tắc chia cho cùng JobInstance.
- Giữ nguyên các identifying JobParameters.
- Giữ nguyên ý nghĩa của các key trong ExecutionContext.
- Không thay đổi grid size hoặc chiến lược partition giữa một lần chạy và lần restart nếu điều đó làm thay đổi danh sách partition.
- Giữ tập dữ liệu nguồn ổn định hoặc xác định snapshot rõ ràng.

Nếu lần đầu tạo partition0 đến partition3, nhưng khi restart lại tạo partition0 đến partition7 với ranh giới khác, metadata cũ không còn ánh xạ đúng với kế hoạch dữ liệu mới. Điều này có thể gây thiếu hoặc xử lý lặp dữ liệu.

### Phiên bản hóa partition plan

Với hệ thống quan trọng, có thể lưu một mã phiên bản hoặc mã kế hoạch trong ExecutionContext:

~~~java
context.putString("partitionPlanVersion", "v1");
context.putString("batchId", batchId);
context.putLong("minId", start);
context.putLong("maxId", end);
~~~

Worker có thể kiểm tra version và batch ID để bảo đảm context phù hợp với dữ liệu đang xử lý.

Nếu chiến lược partition thay đổi, hãy tạo JobInstance mới bằng identifying JobParameters phù hợp hoặc thiết kế migration metadata rõ ràng. Không thay đổi ý nghĩa của các key context trong khi một JobInstance cũ vẫn có thể được restart.

## 11. ExecutionContext và restart của worker

Mỗi worker StepExecution có ExecutionContext riêng. Reader, writer hoặc thành phần khác có thể lưu checkpoint của chính partition đó trong cùng context.

Ví dụ:

~~~text
customerWorkerStep:partition0
  minId = 1
  maxId = 250
  reader.current.count = 120

customerWorkerStep:partition1
  minId = 251
  maxId = 500
  reader.current.count = 250
~~~

Đây là mô tả khái niệm. Tên key checkpoint cụ thể phụ thuộc reader và cấu hình.

Khi partition0 hoàn tất nhưng partition1 thất bại:

- Partition0 đã COMPLETED thường không cần chạy lại khi restart cùng JobInstance.
- Partition1 có thể được restart theo trạng thái và chính sách của Step.
- Partition2 và partition3 được xử lý theo trạng thái thực tế của chúng.
- Worker khôi phục phạm vi partition từ ExecutionContext và vị trí đọc từ checkpoint của reader.

### Không tự ghi đè context khi restart

Không nên tạo một ExecutionContext khác với phạm vi mới cho cùng partition đã có metadata. Nếu Partitioner tạo range không nhất quán, reader có thể khôi phục vị trí cũ nhưng truy vấn trên phạm vi mới, dẫn đến dữ liệu bị bỏ sót hoặc lặp.

Hãy coi partition plan là một phần của hợp đồng JobInstance. Cùng identifying parameters cần tạo ra cùng partition names và cùng ranh giới dữ liệu.

## 12. Phân chia dữ liệu không chồng lấn và không có khoảng trống

Một Partitioner đúng cần bảo đảm toàn bộ tập dữ liệu mục tiêu được phân chia đầy đủ.

Với range inclusive, mỗi partition có điều kiện:

~~~sql
customer_id >= :minId
AND customer_id <= :maxId
~~~

Nếu partition trước có maxId là 250, partition sau phải bắt đầu từ 251. Không được để hai partition cùng chứa ID 250 hoặc bỏ qua ID 251.

Ví dụ phân chia sai:

~~~text
partition0: [1, 250]
partition1: [250, 500]   -- ID 250 bị xử lý hai lần
~~~

Ví dụ có khoảng trống:

~~~text
partition0: [1, 250]
partition1: [252, 500]   -- ID 251 bị bỏ sót
~~~

Ví dụ đúng:

~~~text
partition0: [1, 250]
partition1: [251, 500]
~~~

### ID không liên tục

Range partitioning không yêu cầu ID phải liên tục. Nếu bảng có ID 1, 3, 100 và 900, các range vẫn có thể bao phủ đúng toàn bộ bản ghi nếu query dùng điều kiện biên. Một số partition có thể có ít item hơn hoặc rỗng.

Nếu dữ liệu phân bố lệch, chia theo range số học có thể tạo partition mất cân bằng. Ví dụ, phần lớn ID tập trung ở khoảng 1–1000, còn ID lớn hơn rất thưa. Khi đó cần xem xét chia theo số lượng bản ghi, histogram hoặc key phân vùng phù hợp hơn.

### Các chiến lược partition khác

| Chiến lược | Giá trị trong ExecutionContext | Phù hợp khi |
|---|---|---|
| Range ID | minId, maxId | Khóa có thứ tự |
| Ngày nghiệp vụ | fromDate, toDate | Dữ liệu phân theo thời gian |
| Tenant | tenantId | Mỗi tenant là đơn vị xử lý độc lập |
| Region | regionCode | Dữ liệu chia theo khu vực |
| File | resourcePath, fileName | Mỗi file là một partition |
| Hash bucket | bucketNumber, bucketCount | Phân phối theo hash ổn định |

Bất kể chiến lược nào, mỗi partition cần mô tả rõ phạm vi dữ liệu và không được chồng lấn ngoài chủ đích.

## 13. Chia partition theo ngày hoặc tenant

Không phải lúc nào cũng chia theo ID. Ví dụ partition theo ngày:

~~~java
ExecutionContext context = new ExecutionContext();
context.putString("fromDate", "2026-11-01");
context.putString("toDate", "2026-11-07");
context.putString("batchId", batchId);

partitions.put("week_2026_11_01", context);
~~~

Worker đọc các key bằng StepScope:

~~~java
@Bean
@StepScope
ItemReader<TransactionRecord> transactionReader(
        @Value("#{stepExecutionContext['fromDate']}") String fromDate,
        @Value("#{stepExecutionContext['toDate']}") String toDate,
        @Value("#{jobParameters['batchId']}") String batchId) {
    // Tạo reader chỉ đọc khoảng ngày của partition.
}
~~~

Với tenant partitioning:

~~~java
ExecutionContext context = new ExecutionContext();
context.putString("tenantId", tenantId);
context.putString("batchId", batchId);

partitions.put("tenant_" + tenantId, context);
~~~

Worker chỉ đọc dữ liệu của tenant được giao. Cần xác định rõ việc một tenant có thể được chia thành nhiều partition hay luôn là một partition riêng.

Không đưa danh sách tenant rất lớn vào một key duy nhất nếu có thể tạo mỗi tenant thành một partition riêng. Ngược lại, nếu có hàng chục nghìn tenant nhỏ, một partition cho mỗi tenant có thể tạo quá nhiều StepExecution. Có thể gom tenant thành nhóm và lưu danh sách nhỏ, có thể serialize, trong context.

## 14. Dữ liệu nguồn thay đổi trong khi partition chạy

Nếu Partitioner lấy MIN/MAX ở thời điểm bắt đầu nhưng dữ liệu tiếp tục thay đổi, worker có thể đọc các bản ghi mới được thêm vào hoặc bỏ lỡ bản ghi tùy điều kiện truy vấn.

Ví dụ:

1. Partitioner xác định maxId là 1000.
2. Một tiến trình khác thêm bản ghi ID 1001.
3. Worker chỉ đọc đến 1000.
4. Bản ghi 1001 không thuộc partition plan hiện tại.

Điều này có thể đúng nếu Job chỉ xử lý snapshot tại thời điểm tạo plan. Nếu cần xử lý mọi bản ghi mới, cần có cơ chế xác định phạm vi rõ hơn.

Một số cách kiểm soát:

- Dùng batch ID cố định để đóng tập đầu vào.
- Lưu upper bound hoặc watermark khi bắt đầu Job.
- Dùng snapshot isolation hoặc cơ chế snapshot phù hợp với database.
- Không cho phép thay đổi khóa phân vùng trong thời gian xử lý.
- Ghi nhận timestamp hoặc version của partition plan.
- Đưa dữ liệu đến sau vào batch tiếp theo.

Không nên để mỗi worker tự truy vấn MIN/MAX riêng tại thời điểm chạy. Nếu nguồn thay đổi giữa các worker, các phạm vi có thể không còn cùng một kế hoạch.

## 15. Xử lý partition mất cân bằng

Range partitioning theo min/max có thể tạo các khoảng cùng kích thước số học, nhưng số lượng bản ghi trong mỗi khoảng có thể rất khác nhau.

Ví dụ:

| Partition | Khoảng ID | Số bản ghi thực tế |
|---|---:|---:|
| partition0 | 1–250000 | 200000 |
| partition1 | 250001–500000 | 180000 |
| partition2 | 500001–750000 | 15000 |
| partition3 | 750001–1000000 | 5000 |

Hai partition đầu chạy lâu hơn nhiều. Khi đó, tổng thời gian Job bị chi phối bởi worker chậm nhất.

Một số lựa chọn:

- Chia theo phân vị hoặc histogram của khóa.
- Dùng nhiều partition nhỏ hơn số thread để scheduler phân phối dần.
- Chia theo batch ID hoặc tenant có khối lượng tương đương.
- Dùng hash bucket để phân phối đều nếu truy vấn hỗ trợ.
- Theo dõi thời gian và số lượng item theo từng partition.

Không tăng gridSize vô hạn. Quá nhiều partition tạo thêm metadata, StepExecution, query và overhead điều phối. Hãy đo throughput thực tế và giới hạn tải database.

## 16. Partitioning và concurrency

Partitioning cho phép worker chạy độc lập, có thể đồng thời nếu manager Step dùng TaskExecutor hoặc handler phù hợp.

Cần bảo đảm:

- Mỗi partition xử lý phạm vi dữ liệu riêng.
- Writer có thể xử lý ghi đồng thời.
- Database có đủ connection và tài nguyên.
- Các bảng đích có index và constraint phù hợp.
- Không dùng chung mutable state không thread-safe giữa các worker.
- Các file output của partition có tên riêng, tránh ghi đè lẫn nhau.

Nếu nhiều worker ghi vào cùng một bảng, database vẫn cần xử lý contention, unique constraint và deadlock. Partitioning tăng khả năng song song nhưng không tự loại bỏ xung đột ghi.

### Tên file riêng cho từng partition

Nếu worker ghi file, đưa partition name vào context và tạo file riêng:

~~~java
Path output = outputDirectory.resolve(
    "customers-" + partitionName + ".csv"
);
~~~

Sau khi tất cả worker hoàn tất, một Step khác có thể ghép file hoặc publish manifest. Không để nhiều worker cùng ghi vào một file thông thường nếu writer không hỗ trợ ghi đồng thời và đồng bộ.

## 17. JobRepository lưu metadata của từng partition

Khi manager Step tạo worker execution, Spring Batch lưu trạng thái partition trong JobRepository. Mỗi worker có StepExecution riêng, bao gồm:

- Step name và execution ID.
- BatchStatus và ExitStatus.
- Start time, end time.
- Read, write, filter và skip counts.
- ExecutionContext của partition và checkpoint.
- Thông tin lỗi nếu worker thất bại.

Điều này giúp vận hành xem được worker nào hoàn tất, worker nào thất bại và phạm vi dữ liệu mà worker đó được giao.

Tên StepExecution thường được tạo từ tên worker Step cộng tên partition. Ví dụ:

~~~text
customerWorkerStep:partition0
customerWorkerStep:partition1
customerWorkerStep:partition2
customerWorkerStep:partition3
~~~

Tên chính xác phụ thuộc cấu hình và cơ chế splitter, nhưng việc đặt tên partition rõ ràng giúp tra cứu dễ hơn.

Không xóa hoặc ghi đè metadata partition khi Job còn cần restart. ExecutionContext là một phần quan trọng của trạng thái xử lý.

## 18. Kiểm thử Partitioner độc lập

Partitioner là một lớp Java có thể kiểm thử trực tiếp mà không cần khởi chạy Job. Nên kiểm tra số lượng partition, tên, giá trị context, phạm vi và tính đầy đủ.

Ví dụ:

~~~java
@Test
void createsNonOverlappingRanges() {
    RangePartitioner partitioner =
        new RangePartitioner(1L, 10L);

    Map<String, ExecutionContext> partitions =
        partitioner.partition(3);

    assertEquals(3, partitions.size());

    assertEquals(
        1L,
        partitions.get("partition0").getLong("minId")
    );
    assertEquals(
        4L,
        partitions.get("partition0").getLong("maxId")
    );

    assertEquals(
        5L,
        partitions.get("partition1").getLong("minId")
    );
    assertEquals(
        8L,
        partitions.get("partition1").getLong("maxId")
    );

    assertEquals(
        9L,
        partitions.get("partition2").getLong("minId")
    );
    assertEquals(
        10L,
        partitions.get("partition2").getLong("maxId")
    );
}
~~~

Với ví dụ minId 1, maxId 10 và gridSize 3, kích thước mục tiêu là 4, nên các range là [1,4], [5,8] và [9,10].

### Các trường hợp cần kiểm thử

| Đầu vào | Điều cần xác nhận |
|---|---|
| gridSize bằng 0 hoặc âm | Bị từ chối |
| minId bằng maxId | Tạo một partition có một ID |
| minId lớn hơn maxId | Hành vi nguồn rỗng theo thiết kế |
| Tổng số ID chia hết gridSize | Các range cân bằng |
| Tổng số ID không chia hết | Partition cuối nhỏ hơn |
| Tổng số ID nhỏ hơn gridSize | Không tạo range rỗng ngoài chủ đích |
| Biên gần Long.MIN_VALUE hoặc Long.MAX_VALUE | Không tràn số |
| Gọi lại cùng input | Tạo cùng tên và cùng context |
| Hai partition liền kề | Không chồng lấn, không có khoảng trống |

Nên kiểm tra bằng cách hợp nhất các khoảng và xác nhận:

- Cận dưới đầu tiên bằng minId.
- Cận trên cuối cùng bằng maxId.
- Với hai partition liên tiếp, maxId của partition trước cộng một bằng minId của partition sau.
- Không có partition nào có minId lớn hơn maxId.
- Tên partition là duy nhất.

## 19. Kiểm thử worker nhận đúng ExecutionContext

Ngoài kiểm thử Partitioner, cần kiểm thử tích hợp để bảo đảm Spring Batch truyền context đến worker.

Một test có thể:

1. Tạo Partitioner trả về hai context khác nhau.
2. Cấu hình worker Step có reader @StepScope.
3. Reader nhận minId và maxId qua stepExecutionContext.
4. Chạy manager Step.
5. Xác nhận mỗi worker truy vấn đúng khoảng dữ liệu.
6. Kiểm tra StepExecution của từng partition trong JobRepository.
7. Xác nhận tổng output bằng dữ liệu nguồn và không có bản ghi trùng.

Có thể dùng một reader test ghi lại các range được inject. Không chỉ kiểm tra Partitioner trả map đúng; phải xác nhận wiring StepScope và worker thực sự đọc đúng context.

### Kiểm thử restart partition

Tạo tình huống một partition hoàn tất và một partition thất bại. Sau đó restart cùng JobInstance:

- Partition đã COMPLETED không bị chạy lại ngoài chính sách.
- Partition thất bại được chạy lại.
- Context của partition được khôi phục đúng.
- Reader tiếp tục từ checkpoint của partition đó.
- Kết quả cuối không thiếu hoặc trùng dữ liệu.

## 20. Những lỗi triển khai thường gặp

### Dùng chung một ExecutionContext cho mọi partition

Nếu cùng một object context được đưa vào nhiều key, các giá trị có thể bị thay đổi và gây nhiễm trạng thái giữa các worker. Tạo một ExecutionContext mới cho mỗi partition.

### Tên partition ngẫu nhiên

Tên không ổn định làm restart khó nhận diện StepExecution cũ. Dùng tên xác định từ chỉ số, tenant, region hoặc file key.

### Không lưu đủ dữ liệu trong context

Nếu worker cần batch ID, range hoặc phiên bản dữ liệu nhưng context không có, worker phải tự suy đoán hoặc truy vấn lại theo cách có thể không nhất quán. Đưa đủ thông tin cần thiết vào context hoặc dùng JobParameters chung một cách rõ ràng.

### Đưa object không serialize được vào ExecutionContext

Connection, stream hoặc bean không nên được lưu trong context. Chỉ lưu dữ liệu nhỏ và có thể serialize.

### Không dùng StepScope cho late binding

Bean singleton được tạo trước khi partition StepExecution tồn tại có thể không nhận được giá trị từ stepExecutionContext. Dùng @StepScope cho reader, writer hoặc bean cần dữ liệu partition lúc runtime.

### Range bị chồng lấn hoặc bỏ trống

Cận inclusive/exclusive không nhất quán có thể khiến một bản ghi được xử lý hai lần hoặc không bao giờ được xử lý. Định nghĩa rõ quy tắc biên và kiểm thử mọi khoảng.

### Tính range riêng ở từng worker

Mỗi worker tự lấy min/max tại thời điểm khác nhau có thể tạo kế hoạch không đồng nhất nếu nguồn thay đổi. Tính partition plan một lần tại manager và truyền context cho worker.

### Thay đổi gridSize khi restart

Số partition và ranh giới có thể thay đổi, không còn khớp metadata cũ. Giữ partition plan ổn định cho cùng JobInstance hoặc tạo JobInstance mới khi thay đổi chiến lược.

### Cho rằng gridSize bằng số thread

gridSize là mục tiêu số partition; concurrency thực tế phụ thuộc TaskExecutor hoặc PartitionHandler. Cần cấu hình cả hai dựa trên tài nguyên hệ thống.

### Chia dữ liệu không cân bằng

Range có cùng độ rộng không đảm bảo số bản ghi bằng nhau. Theo dõi khối lượng thực tế và chọn chiến lược phù hợp.

## 21. Quy trình xây dựng Partitioner

Khi triển khai partitioning, có thể làm theo trình tự:

1. **Xác định tập dữ liệu:** xác định batch ID, ngày, tenant hoặc điều kiện nguồn.
2. **Chọn chiến lược chia:** range, tenant, region, file hoặc hash bucket.
3. **Tạo partition plan:** tính tên và phạm vi của từng partition tại manager.
4. **Tạo ExecutionContext riêng:** lưu các key worker cần dùng cho mỗi partition.
5. **Giữ tính xác định:** cùng JobInstance phải tái tạo cùng tên và ranh giới partition.
6. **Cấu hình worker Step:** dùng @StepScope để nhận context bằng late binding.
7. **Cấu hình manager Step:** gắn Partitioner, worker Step, gridSize và executor.
8. **Bảo vệ dữ liệu:** bảo đảm phạm vi không chồng lấn, không bỏ trống và nguồn ổn định.
9. **Thiết kế restart:** giữ checkpoint và context của từng worker.
10. **Kiểm thử:** kiểm tra partition map, wiring context, concurrency và restart.

## 22. Những điểm cần nhớ

- Partitioner triển khai partition(int gridSize) và trả về Map<String, ExecutionContext>.
- Mỗi key là tên partition duy nhất; mỗi value là ExecutionContext riêng của partition.
- Spring Batch dùng context để tạo StepExecution cho từng worker.
- ExecutionContext của partition thuộc phạm vi StepExecution, khác JobParameters và JobExecutionContext.
- Lưu các giá trị nhỏ, ổn định và serialize được như range, batch ID, tenant hoặc file path.
- Worker dùng @StepScope và stepExecutionContext để nhận dữ liệu runtime.
- Manager Step cấu hình bằng partitioner(...).step(...).gridSize(...).taskExecutor(...).
- gridSize là số partition mục tiêu, không nhất thiết là số worker chạy đồng thời.
- Partition plan cần xác định, không chồng lấn và bao phủ đúng tập dữ liệu.
- Cùng JobInstance cần giữ tên partition và ranh giới ổn định để restart chính xác.
- Kiểm soát dữ liệu nguồn thay đổi, phân bố lệch và concurrency.
- Kiểm thử cả Partitioner độc lập lẫn worker nhận context, xử lý dữ liệu và restart.

Một Partitioner được thiết kế tốt biến một công việc lớn thành các phạm vi nhỏ, có tên và trạng thái riêng. Khi mỗi ExecutionContext mô tả chính xác phần dữ liệu của worker, Spring Batch có thể phân phối xử lý song song, theo dõi tiến độ và khôi phục từng partition một cách nhất quán.

