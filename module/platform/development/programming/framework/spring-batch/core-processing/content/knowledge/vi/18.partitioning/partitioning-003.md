# Partition name và step execution

Trong Spring Batch, partitioning chia dữ liệu của một Step thành nhiều phần độc lập để có thể xử lý riêng, thường là xử lý song song. Mỗi phần được gọi là một **partition**. Khi cấu hình partitioning, `Partitioner` trả về một map gồm tên partition và `ExecutionContext` chứa dữ liệu đầu vào dành cho partition đó.

Spring Batch dùng thông tin này để tạo một `StepExecution` riêng cho mỗi partition. Vì vậy, cần phân biệt hai khái niệm: **partition name** là tên logic của một phần dữ liệu; **StepExecution** là bản ghi runtime đại diện cho một lần thực thi Step trên phần dữ liệu đó. Partition name giúp định danh phần việc trong một lần split, còn StepExecution lưu trạng thái, thời gian, bộ đếm, kết quả và context của lần thực thi.

## 1. Partitioning chia một Step thành những phần nào?

Giả sử một Job cần xử lý 1.000.000 khách hàng. Nếu chạy một worker tuần tự, một Step đọc và ghi toàn bộ dữ liệu. Với partitioning, ứng dụng có thể chia phạm vi dữ liệu thành nhiều partition không chồng lấn:

```text
customerImportJob
        |
        v
  managerStep (partitioned step)
        |
        +---- partition0: customerId 1 - 250000
        |
        +---- partition1: customerId 250001 - 500000
        |
        +---- partition2: customerId 500001 - 750000
        |
        +---- partition3: customerId 750001 - 1000000
                    |
                    v
          workerStep chạy cho từng partition
```

Parent/manager Step điều phối việc chia dữ liệu và khởi chạy các worker execution. Worker Step là định nghĩa xử lý thực tế, chẳng hạn đọc các khách hàng trong một khoảng ID, chuẩn hóa dữ liệu rồi ghi kết quả.

Mỗi partition có đầu vào riêng nên worker có thể xử lý độc lập. Các partition thường được thực thi đồng thời khi cấu hình handler và executor phù hợp, nhưng partitioning cũng có thể chạy tuần tự nếu không bật xử lý song song.

## 2. Partition name là gì?

Partition name là khóa String trong map mà `Partitioner.partition(gridSize)` trả về. Khóa này đặt tên cho một phần công việc trong lần phân chia hiện tại.

Ví dụ:

```java
@Component
public class CustomerPartitioner implements Partitioner {

    @Override
    public Map<String, ExecutionContext> partition(int gridSize) {
        Map<String, ExecutionContext> partitions = new LinkedHashMap<>();

        ExecutionContext first = new ExecutionContext();
        first.putLong("minId", 1L);
        first.putLong("maxId", 250_000L);
        partitions.put("partition0", first);

        ExecutionContext second = new ExecutionContext();
        second.putLong("minId", 250_001L);
        second.putLong("maxId", 500_000L);
        partitions.put("partition1", second);

        return partitions;
    }
}
```

Trong ví dụ, `partition0` và `partition1` là partition name. Chúng mô tả hai phần dữ liệu có phạm vi ID riêng. `ExecutionContext` đi kèm chứa `minId` và `maxId`, để worker biết cần xử lý bản ghi nào.

Partition name:

- Là định danh logic do `Partitioner` cung cấp.
- Là key của một entry trong map kết quả.
- Phải duy nhất trong một lần phân chia để mỗi partition có một tên riêng.
- Nên ổn định và có thể tái tạo khi restart cùng một JobInstance.
- Không phải tên thread, tên máy worker, tên Job hoặc ID database của StepExecution.

Các tên như `partition0`, `partition1`, `northRegion`, `southRegion` hoặc `customerRangeA` đều có thể dùng nếu chúng phản ánh rõ cách chia dữ liệu.

## 3. StepExecution là gì trong partitioning?

`StepExecution` là đối tượng metadata đại diện cho một lần thực thi cụ thể của một Step trong một `JobExecution`. Nó lưu những thông tin như:

- Tên Step được thực thi.
- ID của StepExecution và JobExecution liên quan.
- `BatchStatus` và `ExitStatus`.
- Thời điểm bắt đầu, kết thúc và cập nhật gần nhất.
- Số item đọc, ghi, lọc và bỏ qua.
- Số lần commit và rollback.
- Exception phát sinh trong quá trình chạy.
- `ExecutionContext` dùng để lưu trạng thái và checkpoint.

Trong partitioning, Spring Batch tạo một worker `StepExecution` cho mỗi partition được tách ra. Mỗi bản ghi execution này có trạng thái và bộ đếm riêng. Nhờ vậy, người vận hành có thể biết partition nào đã hoàn tất, partition nào đang chạy và partition nào thất bại.

Ví dụ, với worker Step tên `importCustomersStep`, các execution của partition có thể được đặt tên theo quy ước dạng:

```text
importCustomersStep:partition0
importCustomersStep:partition1
importCustomersStep:partition2
importCustomersStep:partition3
```

Phần sau dấu `:` phản ánh partition name. Đây là quy ước tên StepExecution thường thấy trong splitter mặc định; không nên phụ thuộc vào việc phân tích chuỗi tên này để lấy dữ liệu nghiệp vụ. Nếu worker cần partition name, hãy đưa nó vào `ExecutionContext` một cách tường minh.

## 4. Phân biệt partition name và StepExecution

Hai khái niệm có quan hệ với nhau nhưng không đồng nghĩa:

| Tiêu chí | Partition name | StepExecution |
|---|---|---|
| Bản chất | Tên logic của một phần dữ liệu | Bản ghi/đối tượng của một lần thực thi Step |
| Nguồn tạo | Key trong map do `Partitioner` trả về | Spring Batch tạo khi split JobExecution thành các worker execution |
| Vai trò | Nhận diện partition trong lần split | Theo dõi lifecycle và kết quả thực thi partition |
| Dữ liệu chứa | Chỉ là tên; dữ liệu đầu vào thường nằm trong ExecutionContext đi kèm | Status, thời gian, counters, ExitStatus, exception và ExecutionContext |
| Vòng đời | Được tái tạo khi partitioner chạy cho JobInstance | Được lưu trong JobRepository cho từng execution |
| Phạm vi duy nhất | Cần duy nhất trong map của lần split | Có ID riêng trong JobRepository; tên có thể lặp ở JobExecution khác |

Ví dụ, `partition2` chỉ cho biết đây là partition thứ ba theo quy ước đặt tên. `StepExecution` của nó cho biết partition đó đã `COMPLETED`, đọc được bao nhiêu item, ghi được bao nhiêu item và có lỗi gì hay không.

Cùng một partition name có thể xuất hiện trong những JobExecution khác nhau. Ví dụ, `partition0` của JobInstance ngày 15/11 và `partition0` của JobInstance ngày 16/11 là hai lần thực thi riêng, có StepExecution ID và dữ liệu đầu vào riêng.

## 5. Partitioner trả về tên và ExecutionContext

Interface cơ bản:

```java
public interface Partitioner {
    Map<String, ExecutionContext> partition(int gridSize);
}
```

Mỗi entry trong map đại diện cho một partition:

- Key là partition name.
- Value là `ExecutionContext` chứa tham số hoặc phạm vi dữ liệu của partition đó.

Ví dụ với các khoảng ID liên tiếp:

```java
@Component
public class CustomerRangePartitioner implements Partitioner {

    private final CustomerRangeService rangeService;

    public CustomerRangePartitioner(CustomerRangeService rangeService) {
        this.rangeService = rangeService;
    }

    @Override
    public Map<String, ExecutionContext> partition(int gridSize) {
        long minId = rangeService.findMinimumId();
        long maxId = rangeService.findMaximumId();

        Map<String, ExecutionContext> result = new LinkedHashMap<>();
        if (maxId < minId) {
            return result;
        }

        long total = maxId - minId + 1;
        long targetSize = (total + gridSize - 1) / gridSize;
        long start = minId;
        int index = 0;

        while (start <= maxId) {
            long end = Math.min(start + targetSize - 1, maxId);

            ExecutionContext context = new ExecutionContext();
            context.putLong("minId", start);
            context.putLong("maxId", end);
            context.putString("partitionName", "partition" + index);

            result.put("partition" + index, context);

            start = end + 1;
            index++;
        }

        return result;
    }
}
```

Ví dụ minh họa cách chia một khoảng ID thành tối đa khoảng `gridSize` phạm vi có kích thước gần bằng nhau. Trong ứng dụng thực tế, cần xử lý cẩn thận trường hợp tập dữ liệu rỗng, giá trị biên lớn có nguy cơ tràn số và cách phân chia khi ID bị khuyết nhiều. Với dữ liệu phân bố không đều, chia theo số lượng ID không nhất thiết tạo ra workload cân bằng; có thể cần truy vấn phân bố hoặc chia theo số lượng bản ghi thực tế.

`gridSize` là gợi ý/kích thước lưới được truyền vào partitioner và được dùng trong cấu hình handler. Số partition thực tế được tạo ra là số entry mà map trả về. Executor và partition handler tiếp tục quyết định bao nhiêu partition có thể chạy đồng thời.

## 6. Worker Step nhận dữ liệu partition như thế nào?

Khi Spring Batch tạo worker StepExecution cho mỗi entry, dữ liệu `ExecutionContext` do partitioner trả về được dùng làm context ban đầu của worker execution. Worker Step có thể đọc các key này bằng `@StepScope` và SpEL.

Ví dụ worker reader chỉ đọc các khách hàng nằm trong khoảng ID được giao:

```java
@Bean
@StepScope
JdbcPagingItemReader<Customer> customerReader(
        DataSource dataSource,
        @Value("#{stepExecutionContext['minId']}") Long minId,
        @Value("#{stepExecutionContext['maxId']}") Long maxId) {

    return new JdbcPagingItemReaderBuilder<Customer>()
            .name("customerReader")
            .dataSource(dataSource)
            .queryProvider(customerQueryProvider(dataSource))
            .parameterValues(Map.of(
                    "minId", minId,
                    "maxId", maxId))
            .pageSize(500)
            .rowMapper(customerRowMapper())
            .build();
}
```

Query provider cần lọc dữ liệu theo `minId` và `maxId`, đồng thời có sort key ổn định, thường bao gồm khóa duy nhất. Ví dụ SQL tương ứng:

```sql
SELECT id, full_name, email
FROM customers
WHERE id BETWEEN :minId AND :maxId
ORDER BY id ASC;
```

`@StepScope` quan trọng vì mỗi partition có một StepExecutionContext khác nhau. Nếu reader là singleton được khởi tạo một lần khi ứng dụng khởi động, nó không thể giữ đúng `minId` và `maxId` riêng cho từng partition.

Nếu cần truy cập partition name trong worker, có thể đọc key `partitionName` đã được ghi vào context:

```java
@Bean
@StepScope
Tasklet processPartitionTasklet(
        @Value("#{stepExecutionContext['partitionName']}") String partitionName) {

    return (contribution, chunkContext) -> {
        log.info("Processing {}", partitionName);
        return RepeatStatus.FINISHED;
    };
}
```

## 7. Manager Step và worker Step có StepExecution riêng

Trong cấu hình partitioning, cần phân biệt Step điều phối (manager) và Step thực hiện công việc (worker):

- **Manager Step:** là Step trong Job flow, điều phối việc chia dữ liệu và giao các partition cho handler.
- **Worker Step:** là định nghĩa Step được chạy cho từng partition. Mỗi partition có một worker StepExecution riêng.

Manager Step cũng có StepExecution của chính nó. Bên cạnh đó, JobRepository lưu các StepExecution cho từng partition. Vì vậy, khi theo dõi một partitioned Step, có thể thấy một execution của manager và nhiều execution của worker.

Sơ đồ khái quát:

```text
JobExecution
    |
    +---- managerStep StepExecution
              |
              +---- workerStep:partition0 StepExecution
              |
              +---- workerStep:partition1 StepExecution
              |
              +---- workerStep:partition2 StepExecution
              |
              +---- workerStep:partition3 StepExecution
```

Manager Step phản ánh kết quả điều phối tổng thể. Worker StepExecution phản ánh kết quả riêng của từng partition. Nếu một partition thất bại, thông tin lỗi và bộ đếm của partition đó vẫn có thể được xem riêng trong metadata.

## 8. Cấu hình partitioned Step

Ví dụ với Spring Batch 5, manager Step sử dụng `JobRepository`, `Partitioner`, worker Step và `TaskExecutor`:

```java
@Bean
Step customerManagerStep(
        JobRepository jobRepository,
        Step customerWorkerStep,
        Partitioner customerRangePartitioner,
        TaskExecutor taskExecutor) {

    return new StepBuilder("customerManagerStep", jobRepository)
            .partitioner("customerWorkerStep", customerRangePartitioner)
            .step(customerWorkerStep)
            .gridSize(4)
            .taskExecutor(taskExecutor)
            .build();
}
```

Worker Step là một Step thông thường, ví dụ chunk-oriented:

```java
@Bean
Step customerWorkerStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Customer> customerReader,
        ItemProcessor<Customer, Customer> customerProcessor,
        ItemWriter<Customer> customerWriter) {

    return new StepBuilder("customerWorkerStep", jobRepository)
            .<Customer, Customer>chunk(500, transactionManager)
            .reader(customerReader)
            .processor(customerProcessor)
            .writer(customerWriter)
            .build();
}
```

Trong ví dụ, `partitioner("customerWorkerStep", ...)` chỉ định tên Step nền mà các partition sẽ thực thi. Spring Batch tạo các StepExecution riêng dựa trên tên worker Step và partition name. `gridSize(4)` yêu cầu chia công việc thành lưới khoảng bốn phần; số lượng thực tế còn phụ thuộc map mà partitioner trả về.

`TaskExecutor` cho phép handler thực thi các partition bằng nhiều thread trong cùng JVM. Nếu không cần song song, có thể dùng handler phù hợp để chạy tuần tự. Với remote partitioning, các partition được chuyển tới worker process qua middleware; khái niệm partition name và StepExecution vẫn giữ vai trò tương tự, nhưng cần cấu hình hạ tầng giao tiếp và JobRepository phù hợp.

## 9. Partition name ảnh hưởng restart như thế nào?

Spring Batch lưu StepExecution của các partition trong `JobRepository`. Khi JobInstance bị restart, framework có thể dùng metadata đã lưu để xác định partition nào đã hoàn tất và partition nào cần thực thi lại.

Thông thường:

- Partition đã `COMPLETED` được bỏ qua khi restart, trừ khi Step được cấu hình cho phép chạy lại sau khi hoàn tất.
- Partition `FAILED` hoặc `STOPPED` có thể được thực thi lại nếu Job và Step cho phép restart.
- Partition đang có execution hoạt động cần được xử lý theo trạng thái thực tế; không nên khởi chạy trùng một execution đang chạy.

Để đối chiếu execution cũ với partition được tạo lại, tên partition cần ổn định cho cùng JobInstance. Nếu lần đầu map có `partition0` đại diện ID 1–250.000, nhưng khi restart `partition0` lại đại diện ID 1–300.000, metadata cũ không còn mô tả cùng một phạm vi dữ liệu.

Vì vậy, partitioner nên có tính xác định:

1. Cùng identifying JobParameters phải tạo cùng tập partition name.
2. Mỗi partition name phải đại diện cùng phạm vi hoặc cùng đơn vị dữ liệu qua các lần restart.
3. Các phạm vi cần không chồng lấn và bao phủ đúng tập dữ liệu cần xử lý.
4. Không tạo tên ngẫu nhiên hoặc gắn timestamp mới mỗi lần partitioner được gọi.
5. Nếu dữ liệu nguồn có thể thay đổi, nên cố định snapshot, batch ID, cutoff hoặc ranh giới dữ liệu trong JobParameters/metadata bền vững.

Tên ổn định là điều kiện cần nhưng chưa đủ. `ExecutionContext` và phạm vi dữ liệu đi kèm cũng phải ổn định. Nếu dữ liệu đầu vào bị thay thế hoặc ranh giới partition thay đổi, restart có thể đọc lặp hoặc bỏ sót bản ghi.

## 10. Ví dụ restart với nhiều partition

Giả sử Job tạo bốn partition:

| Partition | Phạm vi ID | Trạng thái lần đầu |
|---|---|---|
| `partition0` | 1–250.000 | `COMPLETED` |
| `partition1` | 250.001–500.000 | `COMPLETED` |
| `partition2` | 500.001–750.000 | `FAILED` |
| `partition3` | 750.001–1.000.000 | `COMPLETED` |

Khi restart cùng JobInstance và partitioner tạo lại đúng tên cùng phạm vi, Spring Batch có thể bỏ qua các partition đã hoàn thành và thực thi lại partition thất bại theo metadata/checkpoint của nó.

```text
Lần chạy đầu:
partition0 -> COMPLETED
partition1 -> COMPLETED
partition2 -> FAILED
partition3 -> COMPLETED

Restart:
partition0 -> bỏ qua
partition1 -> bỏ qua
partition2 -> chạy lại/tiếp tục theo checkpoint
partition3 -> bỏ qua
```

Nếu worker Step của mỗi partition là chunk-oriented và reader hỗ trợ `ItemStream`, checkpoint riêng trong StepExecutionContext có thể giúp partition thất bại tiếp tục từ chunk đã commit gần nhất. Các partition đã hoàn thành không cần xử lý lại trong luồng restart thông thường.

Nếu thay partition name hoặc phạm vi giữa hai lần chạy, framework có thể coi đó là các StepExecution khác và hành vi restart sẽ khác mong muốn. Không nên đổi tên partition để né trạng thái lỗi; hãy sửa nguyên nhân và restart đúng instance.

## 11. Partition name và ExecutionContext có quan hệ gì?

Partition name và ExecutionContext được trả về cùng nhau nhưng có nhiệm vụ khác nhau:

- Partition name định danh phần việc trong map.
- ExecutionContext chứa dữ liệu cần để worker thực hiện phần việc đó.

Ví dụ:

```text
Key: partition-east
Context:
  regionCode = EAST
  minCustomerId = 1
  maxCustomerId = 500000

Key: partition-west
Context:
  regionCode = WEST
  minCustomerId = 500001
  maxCustomerId = 1000000
```

Worker có thể sử dụng cả partition name và các giá trị context. Không nên đưa dữ liệu lớn vào context; chỉ truyền phạm vi, khóa tham chiếu, tên resource hoặc thông tin nhỏ cần thiết để worker truy vấn dữ liệu.

Các key trong context nên có tên rõ ràng và kiểu dữ liệu có thể được serializer của JobRepository lưu. Tránh lưu connection, stream, service bean hoặc object runtime không thể serialize ổn định.

## 12. Đặt tên partition như thế nào?

Một quy ước tên tốt cần dễ hiểu, ổn định và không phụ thuộc vào thời điểm thực thi.

Ví dụ tên có thể dùng:

| Cách chia | Partition name mẫu |
|---|---|
| Theo số thứ tự | `partition0`, `partition1`, `partition2` |
| Theo vùng | `region-north`, `region-south` |
| Theo tenant | `tenant-100`, `tenant-200` |
| Theo dải khóa | `customer-000001-250000` |
| Theo ngày/lô cố định | `batch-20261115-part0` |

Nên tránh:

- UUID ngẫu nhiên được tạo mới mỗi lần partitioner chạy.
- Timestamp hiện tại làm thay đổi tên qua restart.
- Tên quá dài chứa cả payload hoặc danh sách ID.
- Tên không thể ánh xạ ngược về phạm vi dữ liệu cần xử lý.
- Dùng tên thread hoặc hostname vì worker có thể được thực thi trên thread/node khác sau restart.

Tên partition không cần duy nhất toàn cục giữa mọi Job trong hệ thống. Nó cần phân biệt các partition trong lần split của Step và phải ổn định trong phạm vi JobInstance cần restart.

## 13. Partitioning chạy song song và số lượng StepExecution

Nếu partitioner trả về bốn entry, Spring Batch tạo bốn worker StepExecution tương ứng. Tuy nhiên, điều đó không đồng nghĩa bốn partition chắc chắn chạy cùng lúc. Mức song song thực tế phụ thuộc:

- `TaskExecutor` và số thread tối đa.
- `gridSize` và cấu hình `PartitionHandler`.
- Số partition thực tế trong map.
- Connection pool và tài nguyên database.
- Tải CPU, bộ nhớ và hệ thống ngoài.
- Giới hạn concurrency của worker trong remote partitioning.

Ví dụ, partitioner tạo 8 partition nhưng executor chỉ có 4 thread, các partition có thể được xử lý theo nhiều lượt với tối đa 4 worker đồng thời. Nếu chỉ có 2 partition, cấu hình executor 8 thread cũng không tạo ra 8 worker partition.

Mỗi partition có StepExecution riêng, nhưng các worker có thể dùng chung database và service. Hãy đảm bảo phạm vi dữ liệu không chồng lấn nếu các worker ghi dữ liệu độc lập. Nếu nhiều partition cùng cập nhật một bản ghi tổng hợp, có thể phát sinh lock contention hoặc deadlock.

## 14. Manager Step và worker Step có thể có trạng thái khác nhau

Manager Step theo dõi quá trình chia và điều phối partition; worker StepExecution theo dõi kết quả của từng partition. Nếu một worker thất bại, manager thường nhận kết quả tổng thể không thành công và Step/Job có thể chuyển sang `FAILED` theo handler và flow.

Khi điều tra, không nên chỉ xem trạng thái manager. Hãy truy vấn từng worker StepExecution để biết partition nào thất bại, exception nào xảy ra và số item đã đọc/ghi.

Ví dụ bảng theo dõi:

| StepExecution | Partition | BatchStatus | Read count | Write count |
|---|---|---|---:|---:|
| `customerWorkerStep:partition0` | partition0 | `COMPLETED` | 250.000 | 250.000 |
| `customerWorkerStep:partition1` | partition1 | `COMPLETED` | 250.000 | 249.990 |
| `customerWorkerStep:partition2` | partition2 | `FAILED` | 120.000 | 119.800 |
| `customerWorkerStep:partition3` | partition3 | `COMPLETED` | 250.000 | 250.000 |

Các con số chỉ minh họa. Khi processor lọc item hoặc Step skip bản ghi, read count và write count có thể khác nhau. Cần xem thêm filter count, skip count, exception và kết quả nghiệp vụ.

## 15. Các lỗi thường gặp

**Nhầm partition name với StepExecution ID:** partition name là key logic do partitioner tạo; StepExecution có ID và metadata riêng do JobRepository quản lý.

**Tạo tên partition không ổn định:** tên ngẫu nhiên hoặc thay đổi qua restart làm framework khó đối chiếu execution cũ với partition mới.

**Dùng cùng một tên cho nhiều phần dữ liệu trong một lần split:** map không thể biểu diễn hai entry có cùng key; mỗi partition cần tên riêng.

**Không truyền phạm vi dữ liệu trong ExecutionContext:** worker không biết phải đọc phần nào hoặc phải tự tính phạm vi không nhất quán.

**Dùng ExecutionContext như nơi chứa toàn bộ dữ liệu partition:** context nên chứa metadata nhỏ và tham chiếu; dữ liệu lớn nên ở database hoặc file.

**Cho rằng gridSize chính là số thread:** gridSize liên quan số partition mục tiêu; executor/handler quyết định số worker có thể chạy đồng thời.

**Cho rằng một partition luôn chạy trên cùng thread hoặc node:** partition có thể được giao cho worker khác khi dùng executor hoặc remote partitioning.

**Thay đổi ranh giới partition giữa các lần restart:** có thể gây xử lý lặp hoặc bỏ sót vì checkpoint cũ không còn khớp phạm vi mới.

**Chỉ xem manager StepExecution:** cần xem worker StepExecution riêng để xác định partition cụ thể bị lỗi.

**Chia dữ liệu chồng lấn:** hai worker có thể cập nhật cùng bản ghi, gây ghi trùng, lock contention hoặc deadlock.

## 16. Quy trình thiết kế partition name và execution

Khi xây dựng partitioned Step, có thể đi theo các bước sau:

1. Xác định đơn vị dữ liệu có thể xử lý độc lập, ví dụ dải ID, vùng, tenant hoặc file.
2. Chọn quy tắc đặt partition name ổn định, duy nhất trong lần split và dễ truy vết.
3. Tạo `ExecutionContext` cho từng partition với các khóa phạm vi hoặc tham chiếu cần thiết.
4. Bảo đảm các partition không chồng lấn và bao phủ đúng tập dữ liệu yêu cầu.
5. Cấu hình worker Step với `@StepScope` để đọc context riêng của từng StepExecution.
6. Cấu hình handler/executor theo concurrency và giới hạn tài nguyên thực tế.
7. Bảo đảm JobRepository lưu metadata bền vững và reader có checkpoint nếu cần restart.
8. Kiểm thử trường hợp một partition thất bại, restart cùng JobInstance và xác nhận partition đã hoàn thành không bị xử lý lại ngoài ý muốn.
9. Theo dõi từng worker StepExecution thay vì chỉ nhìn trạng thái manager.

## Kết luận

Partition name là tên logic do `Partitioner` trả về để định danh từng phần công việc; `StepExecution` là bản ghi runtime Spring Batch tạo cho worker Step của mỗi partition và lưu trạng thái, bộ đếm, exception cùng ExecutionContext. Manager Step điều phối các worker StepExecution, còn mỗi worker nhận phạm vi dữ liệu qua context riêng. Hãy đặt partition name duy nhất và ổn định cho cùng JobInstance, giữ phạm vi partition nhất quán qua restart, phân chia dữ liệu không chồng lấn và dùng metadata StepExecution để theo dõi từng phần. Cách thiết kế này giúp partitioning dễ quan sát, cân bằng tải và khôi phục an toàn khi một partition thất bại.
