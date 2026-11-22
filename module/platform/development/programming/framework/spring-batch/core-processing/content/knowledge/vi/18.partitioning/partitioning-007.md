# Range partitioning

**Range partitioning** chia dữ liệu thành nhiều khoảng giá trị không chồng lấn dựa trên một khóa có thứ tự, sau đó giao mỗi khoảng cho một worker Step xử lý độc lập. Trong Spring Batch, cách này thường được dùng khi cần xử lý tập dữ liệu lớn từ database theo nhiều partition song song.

Ví dụ bảng orders có ID từ 1 đến 1.000.000. Có thể chia thành bốn khoảng:

| Partition | Khoảng ID |
|---|---:|
| partition0 | 1–250.000 |
| partition1 | 250.001–500.000 |
| partition2 | 500.001–750.000 |
| partition3 | 750.001–1.000.000 |

Mỗi worker chỉ đọc dữ liệu thuộc khoảng được giao. Nếu các khoảng được thiết kế đúng, mỗi bản ghi thuộc tối đa một partition và toàn bộ tập dữ liệu mục tiêu được bao phủ.

Range partitioning giúp chia tải xử lý, tận dụng nhiều luồng hoặc nhiều máy và theo dõi tiến độ riêng của từng partition. Hiệu quả phụ thuộc vào khóa phân vùng, cách chia khoảng, phân bố dữ liệu và tài nguyên database.

## 1. Range partitioning trong Spring Batch

Spring Batch hỗ trợ partitioning thông qua ba thành phần:

- **Partitioner** tạo các partition và cung cấp ExecutionContext riêng cho từng partition.
- **Partition manager Step** điều phối việc tạo và chạy các worker Step.
- **Worker Step** thực hiện công việc trên phạm vi dữ liệu được giao.

~~~text
                  Manager Step
                       |
                       v
              Partitioner.partition()
                       |
          +------------+------------+
          |            |            |
          v            v            v
      Context 0    Context 1    Context 2
          |            |            |
          v            v            v
      Worker 0     Worker 1     Worker 2
      ID 1-100     ID 101-200   ID 201-300
          |            |            |
          v            v            v
       Kết quả      Kết quả      Kết quả
          +------------+------------+
                       |
                       v
              Manager Step hoàn tất
~~~

Trong range partitioning, Partitioner thường truy vấn giá trị khóa nhỏ nhất và lớn nhất, chia miền khóa thành các khoảng rồi đặt cận dưới và cận trên vào ExecutionContext.

Worker Step đọc các giá trị này để giới hạn truy vấn. Vì mỗi partition có StepExecution và Step ExecutionContext riêng, các worker có thể lưu checkpoint và restart độc lập.

## 2. Khi nào nên dùng range partitioning?

Range partitioning phù hợp khi:

- Dữ liệu có một khóa có thứ tự rõ ràng, thường là ID tăng dần hoặc ngày nghiệp vụ.
- Có thể biểu diễn mỗi partition bằng cận dưới và cận trên.
- Worker có thể xử lý từng khoảng mà không cần phụ thuộc vào kết quả của worker khác.
- Nguồn dữ liệu đủ lớn để chia thành nhiều phần.
- Database có thể phục vụ các truy vấn theo khoảng khóa hiệu quả.

Ví dụ:

- Xử lý đơn hàng theo ID.
- Tính lại trạng thái giao dịch theo ngày.
- Xuất dữ liệu khách hàng theo khoảng khóa.
- Đối soát bản ghi theo số tài khoản hoặc mã giao dịch có thứ tự.
- Chuyển dữ liệu lịch sử theo khoảng ngày.

Range partitioning không phải lúc nào cũng là lựa chọn tốt. Nếu dữ liệu không có khóa thứ tự phù hợp, phân bố khóa quá lệch hoặc mỗi bản ghi cần kết quả từ partition khác, cách chia này có thể không cân bằng hoặc làm phức tạp xử lý.

## 3. Chọn khóa phân vùng

Khóa phân vùng quyết định dữ liệu được chia và worker truy vấn như thế nào.

Một khóa tốt thường có các đặc điểm:

- Có thể so sánh và sắp xếp ổn định.
- Có index phù hợp để truy vấn theo khoảng.
- Có giá trị cho phần lớn bản ghi cần xử lý.
- Có độ phân bố đủ tốt để tạo các partition có khối lượng tương đối cân bằng.
- Không thay đổi tùy tiện trong khi Job đang chạy hoặc restart.

Khóa thường dùng là ID số, timestamp hoặc ngày nghiệp vụ. Với dữ liệu có khóa trùng, hãy bổ sung một khóa duy nhất làm tie-breaker nếu thuật toán phân vùng dựa trên thứ tự bản ghi.

Nếu khóa có thể null, hãy quyết định rõ các bản ghi đó thuộc partition riêng hay được xử lý ở một Step khác. Đừng để điều kiện WHERE vô tình bỏ sót chúng.

### Chia theo khoảng khóa khác với chia đều số bản ghi

Giả sử ID có các giá trị:

~~~text
1, 2, 3, 4, 5, 900000, 900001, 900002, 900003
~~~

Nếu chia miền số từ 1 đến 900003 thành hai nửa, partition đầu có thể chứa 5 bản ghi còn partition thứ hai chứa 4 bản ghi. Trong ví dụ này kết quả vẫn khá cân bằng, nhưng với dữ liệu tập trung ở một vùng, hai khoảng có thể có số bản ghi rất khác nhau.

Chia đều miền giá trị không đồng nghĩa chia đều khối lượng công việc. Nếu cần cân bằng theo số dòng, hãy dùng thống kê dữ liệu, percentile, các mốc khóa lấy từ truy vấn hoặc một bảng điều phối partition được tạo trước.

## 4. Xác định ranh giới không chồng lấn và không bỏ sót

Điều kiện quan trọng nhất là các partition phải bao phủ đúng tập dữ liệu mục tiêu.

Có hai cách biểu diễn khoảng thường gặp:

- **Khoảng đóng**: từ và đến đều được tính, ví dụ [1, 100].
- **Khoảng nửa mở**: lấy cận dưới, không lấy cận trên, ví dụ [1, 101).

Khoảng nửa mở thuận tiện khi nối các khoảng vì cận trên của khoảng trước là cận dưới của khoảng sau. Khoảng đóng cũng dễ dùng với truy vấn SQL có điều kiện BETWEEN.

Ví dụ dùng khoảng đóng:

~~~sql
SELECT id, status
FROM orders
WHERE id >= :fromId
  AND id <= :toId
ORDER BY id
~~~

Các khoảng:

~~~text
[1, 100]
[101, 200]
[201, 300]
~~~

Không có ID nào nằm trong hai khoảng cùng lúc, và mọi ID trong miền 1–300 đều được bao phủ.

Nếu dùng BETWEEN, nhớ rằng cả hai đầu đều inclusive. Viết hai partition là BETWEEN 1 AND 100 và BETWEEN 100 AND 200 sẽ khiến ID 100 bị xử lý hai lần.

Với kiểu số có giới hạn như long, tránh tính cận tiếp theo bằng phép cộng có thể overflow. Có thể dùng BigInteger khi tính ranh giới hoặc thiết kế khoảng nửa mở với kiểm soát cận trên. Ví dụ code bên dưới dùng BigInteger để chia miền ID an toàn rồi lưu cận inclusive dạng long.

## 5. Partitioner tạo ExecutionContext cho từng khoảng

Hợp đồng Partitioner:

~~~java
public interface Partitioner {
    Map<String, ExecutionContext> partition(int gridSize);
}
~~~

Mỗi entry trong map đại diện một partition:

- Key là tên partition, ví dụ partition0.
- Value là ExecutionContext chứa dữ liệu worker cần, ví dụ fromId và toId.

Ví dụ Partitioner dùng ID nhỏ nhất và lớn nhất từ repository:

~~~java
public class OrderRangePartitioner implements Partitioner {

    private static final BigInteger ONE = BigInteger.ONE;

    private final OrderRepository repository;

    public OrderRangePartitioner(OrderRepository repository) {
        this.repository = repository;
    }

    @Override
    public Map<String, ExecutionContext> partition(int gridSize) {
        if (gridSize < 1) {
            throw new IllegalArgumentException(
                    "gridSize must be positive");
        }

        Long minId = repository.findMinId();
        Long maxId = repository.findMaxId();

        if (minId == null || maxId == null) {
            return Collections.emptyMap();
        }

        if (minId > maxId) {
            throw new IllegalStateException("Invalid ID range");
        }

        BigInteger min = BigInteger.valueOf(minId);
        BigInteger max = BigInteger.valueOf(maxId);
        BigInteger total = max.subtract(min).add(ONE);

        int partitionCount = total.min(
                BigInteger.valueOf(gridSize)).intValueExact();

        Map<String, ExecutionContext> result =
                new LinkedHashMap<>();

        BigInteger count = BigInteger.valueOf(partitionCount);

        for (int i = 0; i < partitionCount; i++) {
            BigInteger from = min.add(
                    total.multiply(BigInteger.valueOf(i))
                            .divide(count));

            BigInteger toExclusive = min.add(
                    total.multiply(BigInteger.valueOf(i + 1))
                            .divide(count));

            BigInteger toInclusive = toExclusive.subtract(ONE);

            ExecutionContext context = new ExecutionContext();
            context.putLong("fromId", from.longValueExact());
            context.putLong("toId", toInclusive.longValueExact());

            result.put("partition" + i, context);
        }

        return result;
    }
}
~~~

Đoạn code chia miền ID nguyên inclusive từ minId tới maxId thành tối đa gridSize khoảng. BigInteger tránh overflow trong phép tính tổng độ dài miền và các ranh giới trung gian. Vì mỗi ranh giới cuối cùng vẫn nằm trong miền long đầu vào, longValueExact() có thể chuyển đổi an toàn.

Nếu nguồn rỗng, ví dụ trả về map rỗng để không tạo worker. Ứng dụng cần xác định rõ hành vi nghiệp vụ khi không có bản ghi: manager Step hoàn tất không có partition, hay một partition rỗng được tạo để ghi nhận kết quả. Hãy chọn một chính sách nhất quán và kiểm thử nó.

### Vì sao cần tên partition ổn định?

Tên partition được dùng để nhận diện các worker execution trong metadata. Dùng tên ổn định như partition0, partition1 giúp Spring Batch liên kết các lần thực thi và restart.

Không nên đặt tên dựa trên UUID ngẫu nhiên mỗi lần gọi partitioner nếu muốn restart các partition đã thất bại. Tên thay đổi có thể làm việc đối chiếu execution cũ trở nên khó khăn.

## 6. Dùng ExecutionContext truyền cận cho worker

Sau khi Partitioner tạo context, Spring Batch tạo StepExecution cho từng partition và gắn context tương ứng.

Ví dụ một partition có:

~~~text
partition1
  fromId = 250001
  toId   = 500000
~~~

Worker Step có thể lấy các giá trị này bằng StepScope và late binding:

~~~java
@Bean
@StepScope
public JdbcCursorItemReader<OrderInput> orderReader(
        DataSource dataSource,
        @Value("#{stepExecutionContext['fromId']}") Long fromId,
        @Value("#{stepExecutionContext['toId']}") Long toId) {

    return new JdbcCursorItemReaderBuilder<OrderInput>()
            .name("orderReader")
            .dataSource(dataSource)
            .sql("""
                SELECT id, status
                FROM orders
                WHERE id >= ?
                  AND id <= ?
                ORDER BY id
                """)
            .preparedStatementSetter(statement -> {
                statement.setLong(1, fromId);
                statement.setLong(2, toId);
            })
            .rowMapper((rs, rowNum) ->
                    new OrderInput(
                            rs.getLong("id"),
                            rs.getString("status")))
            .saveState(true)
            .build();
}
~~~

**@StepScope** là cần thiết để reader được tạo trong phạm vi StepExecution của từng worker. Khi mỗi partition chạy, các giá trị fromId và toId được resolve từ Step ExecutionContext tương ứng.

Nếu reader là singleton được tạo trước khi partition bắt đầu, nó không thể nhận đúng cận riêng cho từng worker và có thể khiến các partition dùng chung phạm vi dữ liệu.

Reader cần có tên ổn định và saveState(true) nếu muốn lưu checkpoint riêng để restart. Mỗi worker có StepExecution/ExecutionContext riêng nên cùng một tên reader trong bean StepScope vẫn có thể lưu trạng thái theo từng partition.

## 7. Cấu hình worker Step và manager Step

Worker Step chứa logic xử lý dữ liệu của một partition. Nó không cần biết toàn bộ cách manager tạo các partition; nó chỉ cần đọc phạm vi được giao.

~~~java
@Bean
public Step orderWorkerStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> orderReader,
        ItemProcessor<OrderInput, ProcessedOrder> orderProcessor,
        ItemWriter<ProcessedOrder> orderWriter) {

    return new StepBuilder("orderWorkerStep", jobRepository)
            .<OrderInput, ProcessedOrder>chunk(200, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .build();
}
~~~

Manager Step dùng Partitioner và worker Step:

~~~java
@Bean
public Step orderManagerStep(
        JobRepository jobRepository,
        Step orderWorkerStep,
        Partitioner orderRangePartitioner,
        TaskExecutor partitionTaskExecutor) {

    return new StepBuilder("orderManagerStep", jobRepository)
            .partitioner("orderWorkerStep", orderRangePartitioner)
            .step(orderWorkerStep)
            .gridSize(4)
            .taskExecutor(partitionTaskExecutor)
            .build();
}
~~~

Trong ví dụ:

- orderWorkerStep là logic xử lý của từng partition.
- orderRangePartitioner tạo các khoảng ID.
- gridSize(4) yêu cầu tạo tối đa bốn partition theo thiết kế này.
- taskExecutor cho phép manager chạy worker bằng nhiều thread trong cùng tiến trình.

Manager Step điều phối các worker và tổng hợp trạng thái hoàn tất của chúng. Một worker thất bại có thể khiến manager Step thất bại; các worker khác có thể đã hoàn thành và được lưu trạng thái riêng.

## 8. Cấu hình TaskExecutor cho partition song song

Có thể dùng ThreadPoolTaskExecutor để chạy các worker trong cùng JVM:

~~~java
@Bean
public TaskExecutor partitionTaskExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(0);
    executor.setThreadNamePrefix("orders-partition-");
    return executor;
}
~~~

Trong Spring, ThreadPoolTaskExecutor được quản lý như bean và lifecycle của nó do container quản lý.

Cần phân biệt:

- **gridSize** điều khiển số partition mà Partitioner/manager yêu cầu.
- **Pool size** giới hạn số worker có thể chạy đồng thời.
- **Chunk size** của worker điều khiển số item trong mỗi transaction chunk bên trong partition.

Ba giá trị này có tác động khác nhau. Ví dụ gridSize bằng 8 nhưng thread pool chỉ có 4 thread thì thường chỉ có tối đa 4 worker thực thi đồng thời; các partition còn lại chờ đến lượt.

Tăng số worker không phải lúc nào cũng tăng throughput. Database có thể bị quá tải bởi nhiều truy vấn đồng thời, connection pool có thể cạn, hoặc writer có thể tranh chấp lock. Hãy đo số worker phù hợp với năng lực nguồn và đích.

## 9. Range partitioning khác gì chunk processing?

Chunk và partition giải quyết hai cấp độ chia việc khác nhau:

| Khái niệm | Chia theo | Mục tiêu |
|---|---|---|
| Chunk processing | Nhóm item bên trong một StepExecution | Commit/rollback theo lô |
| Range partitioning | Phạm vi dữ liệu giao cho các StepExecution độc lập | Chạy nhiều phần dữ liệu song song |
| Grid size | Số partition được tạo/yêu cầu | Chia công việc cho worker |
| Chunk size | Số item trong một chunk của worker | Điều khiển transaction và working set |

Một partition worker vẫn có thể dùng chunk processing. Ví dụ có bốn partition, mỗi partition xử lý 250.000 ID và worker chunk size 500. Mỗi worker sẽ đọc phạm vi của nó theo các chunk 500 item và commit riêng từng chunk.

~~~text
Manager
  |
  +--> Partition 0: ID 1-250000
  |       +--> Chunk 1
  |       +--> Chunk 2
  |       +--> ...
  |
  +--> Partition 1: ID 250001-500000
  |       +--> Chunk 1
  |       +--> Chunk 2
  |       +--> ...
  |
  +--> Partition 2: ID 500001-750000
  |       +--> Chunk 1
  |       +--> Chunk 2
  |       +--> ...
  |
  +--> Partition 3: ID 750001-1000000
          +--> Chunk 1
          +--> Chunk 2
          +--> ...
~~~

Partitioning tăng khả năng xử lý song song. Chunk size vẫn quyết định tần suất commit trong từng worker.

## 10. Range partitioning cần truy vấn có index

Nếu worker chạy truy vấn:

~~~sql
SELECT id, status
FROM orders
WHERE id >= ?
  AND id <= ?
ORDER BY id
~~~

cột id nên có index phù hợp, thường là primary key hoặc index được database tối ưu cho điều kiện range và sort.

Nếu không có index, mỗi worker có thể quét toàn bộ bảng để tìm khoảng của mình. Khi nhiều partition cùng quét, tổng tải database có thể tăng mạnh thay vì giảm thời gian.

Hãy kiểm tra execution plan với số lượng dữ liệu thực tế. Nếu query có thêm điều kiện như status hoặc business_date, có thể cần composite index theo thứ tự cột phù hợp với điều kiện lọc và sắp xếp.

Cũng cần tránh dùng hàm trên cột khóa trong điều kiện WHERE nếu nó làm database không sử dụng được index range scan, trừ khi có functional index phù hợp.

## 11. Phân bố dữ liệu và partition không cân bằng

Range partitioning chia theo miền khóa. Nếu dữ liệu phân bố không đều, worker có thể nhận lượng dữ liệu rất khác nhau.

Ví dụ:

~~~text
ID 1 - 100000       : 800.000 bản ghi
ID 100001 - 200000 : 100.000 bản ghi
ID 200001 - 300000 :  50.000 bản ghi
ID 300001 - 400000 :  50.000 bản ghi
~~~

Nếu chia mỗi partition 100.000 đơn vị ID, worker đầu tiên sẽ chạy lâu hơn nhiều. Các worker khác có thể kết thúc sớm và tài nguyên không được sử dụng cân bằng.

Một số cách cải thiện:

- Dùng thống kê hoặc histogram để xác định điểm chia.
- Chọn ranh giới theo percentile số bản ghi.
- Tạo bảng điều phối chứa start_key/end_key cho từng partition.
- Chia theo ngày hoặc nhóm nghiệp vụ nếu phân bố phù hợp hơn.
- Đo thời gian và số dòng từng partition để điều chỉnh lần chạy sau.

Nếu cần cân bằng theo số dòng, có thể lấy các mốc khóa bằng truy vấn ranking hoặc window function, sau đó tạo khoảng dựa trên các mốc đó. Cần bảo đảm các mốc là duy nhất hoặc có tie-breaker để không chia cắt sai nhóm khóa trùng.

## 12. Xử lý ID bị khuyết và khoảng rỗng

ID không cần liên tục để range partitioning hoạt động.

Ví dụ dữ liệu có ID:

~~~text
10, 11, 19, 100, 105, 900
~~~

Các khoảng [10, 100] và [101, 900] vẫn bao phủ toàn bộ dữ liệu. Khoảng số có thể chứa nhiều giá trị không có bản ghi; điều đó không gây lỗi nếu query trả về đúng những bản ghi hiện hữu.

Tuy nhiên, nếu ID rất thưa hoặc phân bố tập trung, một số partition có thể không có bản ghi. Worker rỗng thường kết thúc nhanh nhưng vẫn tiêu thụ một phần chi phí khởi tạo, metadata và thread scheduling.

Nếu số lượng dữ liệu nhỏ hơn gridSize, có thể giới hạn partitionCount theo độ dài miền khóa hoặc theo số lượng bản ghi. Việc giới hạn theo độ dài miền khóa không loại bỏ được mọi partition rỗng khi khóa có khoảng trống; muốn tránh điều đó cần dựa trên thống kê thực tế hoặc các mốc khóa có dữ liệu.

## 13. Dữ liệu thay đổi trong lúc partition đang chạy

Giả sử Partitioner truy vấn minId=1 và maxId=1.000.000 rồi tạo bốn khoảng. Trong lúc worker đang xử lý, hệ thống khác thêm bản ghi ID=1.000.001.

Bản ghi mới nằm ngoài phạm vi đã tạo và có thể không được xử lý trong Job hiện tại. Nếu dữ liệu bị xóa hoặc thay đổi trạng thái, một số worker có thể đọc ít hơn dự kiến.

Để kết quả nhất quán, cần xác định tập dữ liệu của Job:

- Chụp watermark hoặc upper bound tại thời điểm bắt đầu.
- Dùng điều kiện lọc theo ngày/kỳ nghiệp vụ.
- Dùng snapshot hoặc isolation phù hợp nếu cần đọc nhất quán.
- Đưa mã snapshot, ngày xử lý hoặc watermark vào JobParameters nếu nó xác định đơn vị công việc.
- Tránh thay đổi dữ liệu nguồn theo cách làm thay đổi phạm vi trong khi Job đang chạy.

Một chiến lược phổ biến là lấy minId và maxId tại thời điểm bắt đầu, lưu chúng vào metadata hoặc Job ExecutionContext, rồi tạo partition dựa trên các giá trị đã chốt. Khi restart, phải dùng lại phạm vi của lần chạy đó, không tự động tính lại theo dữ liệu mới nếu điều đó làm thay đổi tập dữ liệu.

## 14. Restart của partition

Mỗi partition có StepExecution và ExecutionContext riêng. Vì vậy, Spring Batch có thể theo dõi partition nào đã hoàn thành, partition nào thất bại và checkpoint reader của từng worker.

~~~text
orderManagerStep
   |
   +--> partition0: COMPLETED
   |       checkpoint riêng
   |
   +--> partition1: FAILED
   |       checkpoint sau chunk 12
   |
   +--> partition2: COMPLETED
   |       checkpoint riêng
   |
   +--> partition3: COMPLETED
           checkpoint riêng
~~~

Khi restart JobInstance:

- Partition đã hoàn thành thường được bỏ qua.
- Partition thất bại có thể được restart từ checkpoint của worker.
- Reader cần hỗ trợ ItemStream và lưu state.
- JobRepository phải giữ metadata bền vững.
- Tên partition và phạm vi dữ liệu cần ổn định giữa các lần chạy.

Nếu đổi gridSize, thuật toán chia khoảng hoặc dữ liệu đầu vào giữa lần chạy đầu và restart, các partition mới có thể không còn tương ứng với StepExecution cũ. Hãy giữ cấu hình phân vùng nhất quán cho cùng JobInstance hoặc thiết kế rõ chiến lược migration/restart.

Nếu nguồn thay đổi, việc restart từ checkpoint cũ có thể không còn phản ánh cùng một tập dữ liệu. Dùng snapshot hoặc watermark để xác định phạm vi xử lý ổn định.

## 15. Partition context và StepScope

ExecutionContext do Partitioner tạo được gắn với worker StepExecution. Để dùng các giá trị đó, reader, processor hoặc writer thường cần StepScope.

Ví dụ processor đọc chế độ xử lý riêng của partition:

~~~java
@Bean
@StepScope
public ItemProcessor<OrderInput, ProcessedOrder> orderProcessor(
        @Value("#{stepExecutionContext['region']}") String region) {

    return order -> processForRegion(order, region);
}
~~~

Các giá trị partition có thể bao gồm:

- fromId và toId.
- fromDate và toDate.
- region hoặc tenant.
- tên file đầu vào của partition.
- mã batch hoặc snapshot ID.

Không lưu cả danh sách item của partition vào ExecutionContext. Context nên chứa thông tin cấu hình và checkpoint nhỏ, không phải payload dữ liệu lớn.

Nếu nhiều partition dùng cùng một bean mutable singleton, chúng có thể ghi đè trạng thái của nhau. Dùng StepScope cho component có state riêng theo partition và tránh chia sẻ mutable object không thread-safe.

## 16. Range partitioning và partitioning từ xa

Range partitioning mô tả **cách chia dữ liệu**, còn local hay remote partitioning mô tả **nơi worker chạy**.

- **Local partitioning**: manager chạy các worker Step trong cùng JVM, thường qua TaskExecutor.
- **Remote partitioning**: manager gửi yêu cầu worker qua messaging middleware hoặc cơ chế phân phối; worker chạy ở tiến trình/máy khác.

Cả hai cách đều có thể dùng ExecutionContext chứa cận ID hoặc ngày. Worker nhận context và xử lý phạm vi được giao.

Với remote partitioning, cần chú ý thêm:

- Serialization của ExecutionContext và message.
- Khả năng retry khi worker mất kết nối.
- Định danh partition và chống xử lý trùng.
- Khả năng quan sát trạng thái worker ở nhiều tiến trình.
- JobRepository và metadata dùng chung hoặc được cấu hình phù hợp.

Không nên coi việc dùng nhiều thread trong TaskExecutor là remote partitioning. TaskExecutor chạy worker trong cùng tiến trình; remote partitioning cần cơ chế truyền công việc giữa manager và worker ở các tiến trình khác nhau.

## 17. Giám sát từng partition

Khi Job có nhiều partition, chỉ xem trạng thái manager Step là chưa đủ. Cần theo dõi từng worker StepExecution.

Các thông tin hữu ích:

| Thông tin | Mục đích |
|---|---|
| Partition name | Xác định worker nào |
| StepExecution ID | Truy vấn lần chạy cụ thể |
| fromId / toId | Biết phạm vi dữ liệu được giao |
| BatchStatus | Biết worker đang chạy, hoàn tất hay thất bại |
| readCount / writeCount | Đo lượng dữ liệu đã đọc và ghi |
| commitCount / rollbackCount | Quan sát transaction của worker |
| startTime / endTime | So sánh thời gian chạy |
| failureExceptions | Điều tra lỗi worker |

Nếu một partition chạy lâu hơn nhiều partition khác, hãy kiểm tra phân bố dữ liệu, execution plan, lock contention, tốc độ writer và các truy vấn phụ trong processor.

Ghi partition name cùng JobExecution ID vào log giúp liên kết lỗi với đúng phạm vi dữ liệu. Không nên chỉ log thông báo chung như "partition failed" mà thiếu tên partition và execution ID.

## 18. Lỗi thường gặp khi triển khai range partitioning

### Các khoảng bị chồng lấn

Dùng BETWEEN với cận cuối của partition trước trùng cận đầu của partition sau khiến một số bản ghi bị xử lý hai lần. Hãy dùng khoảng đóng có cận kế tiếp chính xác hoặc khoảng nửa mở.

### Có khoảng bị bỏ sót

Tính ranh giới sai, làm tròn không nhất quán hoặc bỏ quên bản ghi ở cận max có thể khiến dữ liệu không được xử lý. Hãy kiểm thử toàn bộ miền với các giá trị ở hai phía ranh giới.

### Chia đều số ID nhưng không đều số bản ghi

Dữ liệu phân bố lệch làm một worker xử lý lâu hơn. Hãy dùng thống kê hoặc mốc khóa theo percentile khi cần cân bằng.

### Reader không dùng partition context

Nếu worker query toàn bảng thay vì lọc theo fromId/toId, tất cả partition có thể đọc cùng dữ liệu và tạo kết quả trùng.

### Reader không có StepScope

Reader singleton có thể nhận một bộ cận chung hoặc giữ state dùng chung. Hãy tạo reader theo từng StepExecution bằng StepScope khi cần giá trị partition.

### gridSize bị nhầm với chunk size

gridSize là số partition; chunk size là số item mỗi transaction của worker. Điều chỉnh một giá trị không thay thế giá trị kia.

### Tăng số worker làm database quá tải

Nhiều truy vấn đồng thời có thể làm cạn connection pool, tăng lock hoặc làm database chậm. Tăng concurrency theo năng lực nguồn và đích.

### Restart với ranh giới khác lần đầu

Nếu partition layout thay đổi, checkpoint cũ có thể không còn khớp phạm vi dữ liệu. Giữ cấu hình và source snapshot ổn định cho cùng JobInstance.

### Dữ liệu mới nằm ngoài watermark

Bản ghi được thêm sau khi Partitioner xác định maxId có thể không thuộc bất kỳ partition nào. Hãy định nghĩa rõ snapshot hoặc watermark của Job.

## 19. Kiểm thử Partitioner

Nên kiểm thử Partitioner độc lập trước khi chạy toàn bộ Job.

Các trường hợp quan trọng:

- gridSize bằng 1.
- gridSize lớn hơn số giá trị trong miền.
- Dữ liệu rỗng.
- Chỉ có một ID.
- minId bằng maxId.
- ID âm hoặc miền có cả số âm và dương.
- Miền ID rất lớn, gần giới hạn long.
- Dữ liệu thưa có nhiều khoảng trống.
- Mọi cận partition liền kề, không chồng lấn.
- Tên partition ổn định.

Ví dụ kiểm tra các khoảng được tạo:

~~~java
@Test
void createsAdjacentNonOverlappingRanges() {
    OrderRepository repository = mock(OrderRepository.class);
    when(repository.findMinId()).thenReturn(1L);
    when(repository.findMaxId()).thenReturn(100L);

    OrderRangePartitioner partitioner =
            new OrderRangePartitioner(repository);

    Map<String, ExecutionContext> partitions =
            partitioner.partition(4);

    assertEquals(4, partitions.size());

    long expectedFrom = 1L;

    for (ExecutionContext context : partitions.values()) {
        long from = context.getLong("fromId");
        long to = context.getLong("toId");

        assertEquals(expectedFrom, from);
        assertTrue(to >= from);

        expectedFrom = to + 1;
    }

    assertEquals(101L, expectedFrom);
}
~~~

Test này giả định miền 1–100 và 4 partition. Nó xác nhận các khoảng liên tiếp, không chồng lấn và bao phủ tới maxId. Với trường hợp maxId là Long.MAX_VALUE, không dùng phép cộng to + 1 trong assertion; hãy dùng BigInteger hoặc kiểm tra cận cuối riêng.

Ngoài unit test Partitioner, cần chạy Step integration test với dữ liệu ở đúng các cận: minId, maxId, giá trị ngay trước và sau mỗi ranh giới. Tổng hợp ID được đọc từ mọi partition rồi xác nhận không thiếu và không trùng.

## 20. Quy trình thiết kế range partitioning

Khi xây dựng Job dùng range partitioning, hãy thực hiện theo trình tự:

1. Chọn khóa phân vùng có thứ tự ổn định và index phù hợp.
2. Xác định tập dữ liệu của Job bằng ngày nghiệp vụ, snapshot hoặc watermark.
3. Truy vấn min/max hoặc thống kê để xác định ranh giới.
4. Viết Partitioner tạo các ExecutionContext có cận rõ ràng.
5. Chọn quy ước inclusive hoặc half-open và dùng nhất quán trong SQL.
6. Tạo worker Step đọc cận từ Step ExecutionContext qua StepScope.
7. Dùng query có điều kiện range và ORDER BY ổn định.
8. Cấu hình manager Step, gridSize và TaskExecutor theo năng lực hệ thống.
9. Lưu checkpoint riêng của mỗi worker để hỗ trợ restart.
10. Kiểm thử ranh giới, dữ liệu rỗng, dữ liệu thưa và trường hợp restart.
11. Theo dõi trạng thái, số dòng và thời gian của từng partition.
12. Giữ partition names, source snapshot và thuật toán chia ổn định cho cùng JobInstance.

Range partitioning hiệu quả khi các worker nhận được những phạm vi rõ ràng, độc lập và có khối lượng hợp lý. Partitioner quyết định ranh giới, ExecutionContext truyền phạm vi, worker Step thực hiện truy vấn và chunk processing quản lý transaction bên trong mỗi worker. Khi các ranh giới không chồng lấn, nguồn dữ liệu ổn định và mức concurrency phù hợp, Spring Batch có thể xử lý tập dữ liệu lớn song song mà vẫn theo dõi và restart từng partition một cách có kiểm soát.
