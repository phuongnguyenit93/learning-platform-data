# Giới hạn partitioning trong module core

Trong Spring Batch, **partitioning** chia một step lớn thành nhiều phần dữ liệu độc lập. Mỗi phần được xử lý bởi một worker step với `StepExecution` và `ExecutionContext` riêng. Cách tổ chức này cho phép nhiều worker xử lý song song, tăng thông lượng cho những batch job có thể chia dữ liệu an toàn.

Partitioning trong Spring Batch Core cung cấp các abstraction để chia phạm vi công việc, tạo execution cho từng partition và điều phối worker. Tuy nhiên, core không tự giải quyết mọi vấn đề của xử lý phân tán. Ứng dụng vẫn phải xác định cách chia dữ liệu, bảo đảm các partition không xử lý chồng lấn, quản lý tài nguyên dùng chung, thiết kế restart và kiểm soát các giới hạn của database hoặc hệ thống đích.

Hiểu rõ những giới hạn này giúp chọn đúng mô hình song song và tránh kỳ vọng rằng chỉ cần tăng `gridSize` là batch sẽ nhanh hơn hoặc tự động chạy trên nhiều máy.

## 1. Partitioning trong Spring Batch Core làm gì?

Partitioning chia công việc của một step thành nhiều đơn vị nhỏ hơn. Một step đóng vai trò manager tạo các partition; mỗi partition được thực hiện bởi một worker step. Worker step có thể là cùng một định nghĩa step nhưng nhận `ExecutionContext` khác nhau để xử lý phạm vi dữ liệu riêng.

Ví dụ, job cần xử lý một triệu khách hàng. Thay vì một worker đọc và cập nhật toàn bộ dữ liệu, manager có thể chia ID thành nhiều khoảng:

```text
managerStep
    |
    +-- partition0: customer_id 1      - 100000
    +-- partition1: customer_id 100001 - 200000
    +-- partition2: customer_id 200001 - 300000
    +-- partition3: customer_id 300001 - 400000
    +-- ...
             |
             v
       workerStep chạy trên từng partition
```

Mỗi partition nhận dữ liệu mô tả phạm vi xử lý, thường được lưu trong một `ExecutionContext`. Worker step đọc phạm vi đó và thực hiện công việc bằng reader, processor, writer hoặc tasklet.

Các abstraction chính gồm:

| Thành phần | Vai trò |
|---|---|
| `Partitioner` | Tạo tên partition và `ExecutionContext` mô tả dữ liệu/phạm vi của từng partition. |
| Manager step | Điều phối việc chia step thành nhiều partition. |
| Worker step | Thực hiện công việc cho một partition. |
| `StepExecutionSplitter` | Tạo các `StepExecution` cho những partition theo trạng thái và metadata. |
| `PartitionHandler` | Điều phối cách thực thi các worker step, chẳng hạn trong cùng process hoặc qua cơ chế phân phối tùy chỉnh. |
| `JobRepository` | Lưu metadata của manager step và các worker `StepExecution`. |
| `ExecutionContext` | Chứa tham số riêng của từng partition và trạng thái cần cho restart. |

Partitioning tập trung vào việc chia và điều phối các đơn vị step. Nó không tự quyết định quy tắc nghiệp vụ để phân chia dữ liệu; phần đó thuộc về `Partitioner` và thiết kế của ứng dụng.

## 2. Giới hạn quan trọng: Core không tự chia dữ liệu nghiệp vụ

Spring Batch Core cung cấp interface `Partitioner`, nhưng ứng dụng phải triển khai cách chia dữ liệu. Ví dụ, với bảng khách hàng, ứng dụng có thể chia theo khoảng ID, vùng địa lý, mã khách hàng hoặc hash bucket.

Interface có dạng:

```java
public interface Partitioner {
    Map<String, ExecutionContext> partition(int gridSize);
}
```

`gridSize` là gợi ý số partition mong muốn truyền cho partitioner. Implementation có thể dùng giá trị này để tính phạm vi, nhưng số partition thực tế phụ thuộc logic do ứng dụng viết. Core không tự kiểm tra rằng các phạm vi đã bao phủ toàn bộ dữ liệu hoặc không chồng lấn.

Ví dụ partitioner chia một khoảng ID:

```java
@Component
public class CustomerRangePartitioner implements Partitioner {

    private final CustomerRepository repository;

    public CustomerRangePartitioner(CustomerRepository repository) {
        this.repository = repository;
    }

    @Override
    public Map<String, ExecutionContext> partition(int gridSize) {
        long minId = repository.findMinId();
        long maxId = repository.findMaxId();

        Map<String, ExecutionContext> partitions = new LinkedHashMap<>();
        long total = maxId - minId + 1;
        long targetSize = (long) Math.ceil((double) total / gridSize);

        for (int i = 0; i < gridSize; i++) {
            long start = minId + i * targetSize;
            long end = Math.min(maxId, start + targetSize - 1);
            if (start > maxId) {
                break;
            }

            ExecutionContext context = new ExecutionContext();
            context.putLong("minCustomerId", start);
            context.putLong("maxCustomerId", end);
            partitions.put("customerPartition" + i, context);
        }

        return partitions;
    }
}
```

Đây là ví dụ minh họa cách tạo các context. Trong ứng dụng thật, cần xử lý bảng rỗng, ID thưa, dữ liệu thay đổi trong lúc lấy min/max và cách phân chia để cân bằng khối lượng. Chia khoảng số học không bảo đảm mỗi partition có cùng số bản ghi nếu ID bị thưa hoặc phân bố không đều.

### Các yêu cầu mà partitioner phải bảo đảm

- Mỗi bản ghi cần xử lý thuộc đúng một partition nếu nghiệp vụ yêu cầu xử lý đúng một lần.
- Không bỏ sót bản ghi nằm trong phạm vi cần xử lý.
- Các tên partition ổn định giữa lần chạy và restart của cùng đơn vị công việc.
- `ExecutionContext` chứa đủ thông tin để worker xác định đúng phạm vi dữ liệu.
- Dữ liệu dùng để tạo partition phải nhất quán với tập dữ liệu worker thực sự đọc.

Nếu partitioner chia phạm vi bị trùng, nhiều worker có thể cập nhật cùng bản ghi. Nếu có khoảng trống, một phần dữ liệu sẽ không được xử lý. Spring Batch lưu và điều phối những partition mà ứng dụng tạo ra, nhưng không thể tự biết quy tắc nghiệp vụ nào là đúng.

## 3. Giới hạn của gridSize

`gridSize` thường được hiểu là số partition mong muốn hoặc mức độ chia nhỏ mà manager yêu cầu. Nó không đồng nghĩa với số thread chắc chắn chạy đồng thời, cũng không phải cấu hình tự động tăng số máy xử lý.

Ví dụ, manager step có `gridSize(8)` nhưng executor chỉ có 4 worker thread. Khi đó các partition có thể được xử lý theo nhiều đợt, tối đa 4 tác vụ chạy đồng thời theo năng lực executor. Ngược lại, nếu partitioner chỉ tạo 5 partition dù grid size là 8, chỉ có 5 worker execution được tạo.

```text
gridSize = 8
partitioner tạo 8 partition
executor pool size = 4

Đợt 1: partition 0, 1, 2, 3 chạy
Đợt 2: partition 4, 5, 6, 7 chạy
```

Số worker chạy đồng thời còn bị giới hạn bởi:

- Kích thước thread pool hoặc năng lực `PartitionHandler`.
- Số connection có thể cấp từ connection pool.
- Khả năng xử lý đồng thời của database và hệ thống đích.
- CPU, bộ nhớ, I/O và tài nguyên của máy chạy batch.
- Số partition thực tế do `Partitioner` trả về.
- Giới hạn concurrency do ứng dụng hoặc nền tảng triển khai áp đặt.

Tăng `gridSize` có thể làm tăng số `StepExecution`, metadata, truy vấn và chi phí điều phối. Nếu tài nguyên downstream đã bão hòa, tăng partition chỉ làm nhiều worker tranh chấp cùng tài nguyên và có thể khiến tổng thời gian chạy dài hơn.

## 4. Local partitioning không tự động là remote partitioning

Một giới hạn dễ hiểu nhầm là partitioning trong core không tự động phân phối worker lên nhiều máy. Khi cấu hình manager với `TaskExecutor` thông thường, các partition thường được chạy trên các thread trong cùng JVM/process.

Ví dụ cấu hình local partitioning theo Spring Batch 5:

```java
@Bean
Step customerWorkerStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<CustomerInput> reader,
        ItemProcessor<CustomerInput, Customer> processor,
        ItemWriter<Customer> writer) {

    return new StepBuilder("customerWorkerStep", jobRepository)
            .<CustomerInput, Customer>chunk(500, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}

@Bean
Step customerManagerStep(
        JobRepository jobRepository,
        Step customerWorkerStep,
        Partitioner customerPartitioner,
        TaskExecutor partitionTaskExecutor) {

    return new StepBuilder("customerManagerStep", jobRepository)
            .partitioner("customerWorkerStep", customerPartitioner)
            .step(customerWorkerStep)
            .gridSize(8)
            .taskExecutor(partitionTaskExecutor)
            .build();
}
```

`partitionTaskExecutor` cần được cấu hình riêng, thường là thread pool có giới hạn. Các worker vẫn chạy trong cùng ứng dụng và dùng chung các tài nguyên mà application context cung cấp.

Nếu cần chạy worker trên nhiều process hoặc nhiều máy, phải có cơ chế vận chuyển và điều phối phù hợp. Có thể dùng remote partitioning với Spring Integration/messaging hoặc một `PartitionHandler` tùy chỉnh. Việc gửi message, nhận kết quả, xử lý worker mất kết nối, bảo đảm delivery và giám sát node là phần hạ tầng bổ sung; chỉ cấu hình `gridSize` hoặc `TaskExecutor` không tạo ra khả năng phân tán qua mạng.

## 5. Core không tự cân bằng tải giữa các partition

Partitioner thường tạo danh sách partition trước khi worker thực thi. Nếu dữ liệu được chia không đều, một số worker có thể hoàn tất nhanh trong khi một partition lớn vẫn chạy lâu.

Ví dụ:

```text
Partition 0: 10.000 bản ghi  -> hoàn tất sau 10 giây
Partition 1: 10.000 bản ghi  -> hoàn tất sau 11 giây
Partition 2: 10.000 bản ghi  -> hoàn tất sau 12 giây
Partition 3: 90.000 bản ghi  -> hoàn tất sau 95 giây
```

Thời gian tổng thể bị chi phối bởi partition chậm nhất cộng với chi phí điều phối. Trong mô hình partitioning cơ bản, core không tự chia lại một partition đang chạy thành các phần nhỏ hơn hoặc tự di chuyển item từ worker chậm sang worker nhanh.

Các cách cải thiện cân bằng:

- Chia theo số lượng bản ghi ước tính thay vì chỉ chia đều khoảng ID.
- Dùng histogram hoặc thống kê phân bố dữ liệu để xác định ranh giới.
- Chọn khóa phân vùng có phân bố tương đối đều.
- Tạo nhiều partition nhỏ hơn số worker để giảm ảnh hưởng của chênh lệch thời gian, trong giới hạn chi phí metadata và scheduling.
- Tách riêng các nhóm dữ liệu đặc biệt nặng thành partition riêng.
- Đo thời gian thực tế của từng partition rồi điều chỉnh chiến lược chia ở lần chạy sau.

Tạo quá nhiều partition cũng có chi phí. Mỗi partition tạo execution metadata, cần khởi tạo worker và có thể tạo thêm truy vấn. Cần tìm mức chia cân bằng dựa trên kích thước dữ liệu và thời gian xử lý thực tế.

## 6. Partitioning cần dữ liệu đầu vào có thể chia độc lập

Partitioning phát huy hiệu quả khi các phạm vi có thể được xử lý độc lập. Nếu kết quả của partition A phụ thuộc vào kết quả partition B hoặc cần một thứ tự xử lý toàn cục, việc chạy song song có thể làm thay đổi ý nghĩa nghiệp vụ.

Ví dụ, tính tổng doanh thu theo từng khách hàng có thể chia theo customer ID nếu mỗi khách hàng chỉ thuộc một partition. Nhưng nếu cần tính số dư tài khoản dựa trên chuỗi giao dịch có thứ tự thời gian, chia giao dịch ngẫu nhiên theo ID có thể làm mất thứ tự cần thiết.

Trước khi partition, cần xác định:

- Một item có thể được xử lý độc lập hay không?
- Có yêu cầu thứ tự giữa các item không?
- Hai partition có thể cập nhật cùng một aggregate hoặc cùng một bản ghi không?
- Có dữ liệu dùng chung cần khóa hoặc đồng bộ không?
- Nếu partition thất bại, các partition khác đã commit có thể giữ nguyên hay phải bù trừ?

Nếu công việc có phụ thuộc thứ tự, có thể cần chia theo nhóm nghiệp vụ độc lập (ví dụ theo tài khoản) rồi giữ thứ tự bên trong từng nhóm. Nếu không thể tạo các phạm vi độc lập, partitioning có thể không phải lựa chọn phù hợp.

## 7. Tài nguyên dùng chung có thể trở thành nút thắt

Trong local partitioning, các worker chạy đồng thời trong cùng JVM. Nhiều worker có thể dùng chung bean singleton, datasource, connection pool, file system, cache hoặc API client. Không phải tài nguyên nào cũng an toàn khi truy cập đồng thời.

Các rủi ro thường gặp:

- Reader hoặc writer giữ trạng thái nội bộ như cursor, vị trí file hoặc buffer và không thread-safe.
- Nhiều worker cùng ghi vào một file mà không có cơ chế phân vùng output.
- Nhiều worker cùng cập nhật một hàng hoặc một tập bảng, gây lock contention/deadlock.
- Connection pool không đủ connection cho số worker đang chạy.
- API bên ngoài giới hạn request rate, khiến worker phải chờ hoặc bị throttling.
- Cache mutable hoặc bộ đếm dùng chung bị race condition.

Nên tạo tài nguyên theo scope phù hợp với từng `StepExecution` hoặc partition. Với reader/writer có state, thường cần `@StepScope` để mỗi worker nhận instance và tham số riêng. Tuy nhiên, `@StepScope` không tự biến mọi dependency bên trong thành thread-safe; các singleton service hoặc client được inject vẫn có thể được dùng chung.

Ví dụ reader nhận phạm vi partition qua Step ExecutionContext:

```java
@Bean
@StepScope
JdbcPagingItemReader<CustomerInput> customerReader(
        DataSource dataSource,
        @Value("#{stepExecutionContext['minCustomerId']}") Long minId,
        @Value("#{stepExecutionContext['maxCustomerId']}") Long maxId) {

    return new JdbcPagingItemReaderBuilder<CustomerInput>()
            .name("customerReader")
            .dataSource(dataSource)
            .selectClause("select id, name")
            .fromClause("from customer")
            .whereClause("where id between :minId and :maxId")
            .parameterValues(Map.of("minId", minId, "maxId", maxId))
            .sortKeys(Map.of("id", Order.ASCENDING))
            .rowMapper((rs, rowNum) -> new CustomerInput(
                    rs.getLong("id"), rs.getString("name")))
            .pageSize(500)
            .saveState(true)
            .build();
}
```

Trong ví dụ, mỗi worker đọc một khoảng ID riêng. Cần bảo đảm `minId` và `maxId` được tạo chính xác, và reader thực sự được khởi tạo trong scope của worker step.

## 8. Database có thể giới hạn khả năng mở rộng

Partitioning tăng số worker nhưng không làm database tự tăng năng lực xử lý. Nếu tất cả worker cùng đọc và ghi vào một database, database có thể trở thành nút thắt trước CPU của ứng dụng.

Một số giới hạn phổ biến:

- Connection pool không đủ connection cho worker.
- Truy vấn mỗi partition quét cùng một bảng lớn do thiếu index hoặc điều kiện lọc không tối ưu.
- Các worker cập nhật những hàng liên quan, gây lock contention hoặc deadlock.
- Nhiều partition cùng insert vào một index nóng hoặc sequence/bảng tổng hợp.
- Database I/O, CPU hoặc log writer đã bão hòa.
- Transaction kéo dài làm giữ lock và tăng thời gian chờ của hệ thống online.

Không nên đặt thread pool lớn hơn khả năng database chỉ vì máy ứng dụng còn CPU. Cần đo connection wait, query latency, lock wait, deadlock, I/O và commit time khi tăng concurrency.

Nếu mỗi partition cần một connection đồng thời, connection pool phải có đủ năng lực cho worker cùng các hoạt động khác của ứng dụng. Nhưng tăng pool size quá lớn cũng có thể làm database chịu quá nhiều session. Số worker và connection pool phải được điều chỉnh cùng nhau theo giới hạn database.

## 9. ExecutionContext chỉ nên chứa metadata nhỏ

Partitioner trả về một `ExecutionContext` cho mỗi partition. Context thường chứa giới hạn dữ liệu, tên file, mã phân vùng hoặc tham số cần thiết để worker xác định việc phải làm.

Ví dụ:

```java
ExecutionContext context = new ExecutionContext();
context.putLong("minCustomerId", 100001L);
context.putLong("maxCustomerId", 200000L);
context.putString("regionCode", "NORTH");
```

Không nên đặt toàn bộ danh sách hàng nghìn hoặc hàng triệu ID vào ExecutionContext. Các giá trị context phải được lưu trong JobRepository và có thể cần serialize/deserialize. Payload lớn làm tăng kích thước metadata, thời gian lưu/đọc và áp lực lên repository.

Với tập dữ liệu lớn, nên lưu dữ liệu phân vùng hoặc danh sách ID trong database/file/object storage rồi đưa khóa tham chiếu vào context. Không lưu các object không thể serialize an toàn như `Connection`, `ResultSet`, `InputStream`, service bean hoặc entity manager.

## 10. Restart cần partition identity ổn định

Spring Batch lưu `StepExecution` riêng cho từng partition. Khi job thất bại và được restart, framework dùng metadata để xác định partition đã hoàn tất, partition thất bại và partition cần thực hiện lại.

Điều này phụ thuộc vào tên partition và dữ liệu mà partition đại diện phải ổn định. Nếu lần restart tạo partition name khác hoặc ranh giới dữ liệu thay đổi, framework có thể không còn ánh xạ đúng metadata cũ với công việc ban đầu.

Ví dụ lần chạy đầu:

```text
customerPartition0: ID 1      - 100000  COMPLETED
customerPartition1: ID 100001 - 200000  FAILED
customerPartition2: ID 200001 - 300000  COMPLETED
```

Khi restart cùng JobInstance, các partition đã hoàn tất có thể được bỏ qua; partition thất bại được thực hiện lại theo trạng thái và cấu hình. Nếu partitioner thay đổi cách chia giữa hai lần chạy, chẳng hạn partition1 giờ xử lý ID 150001-250000, trạng thái cũ không còn mô tả đúng phạm vi mới.

Để restart đáng tin cậy:

- Dùng tên partition có quy tắc ổn định.
- Giữ nguyên cách ánh xạ tên partition sang phạm vi dữ liệu trong cùng JobInstance.
- Dùng identifying JobParameters để cố định batch, ngày nghiệp vụ hoặc snapshot đầu vào.
- Không thay đổi file hoặc tập dữ liệu nguồn giữa lần chạy và restart.
- Lưu checkpoint riêng của worker qua reader/writer hỗ trợ `ItemStream`.
- Bảo đảm writer an toàn khi item chưa commit được xử lý lại.

`PartitionNameProvider` có thể được dùng trong một số trường hợp để cung cấp tên partition đã tạo mà không cần tính lại toàn bộ context khi restart. Tuy nhiên, nó không thay thế yêu cầu giữ ổn định ý nghĩa dữ liệu của từng partition; ứng dụng vẫn phải bảo đảm worker khôi phục đúng phạm vi.

## 11. Partitioning không tạo một transaction toàn cục

Mỗi worker step quản lý transaction riêng cho chunk hoặc tasklet của nó. Các partition không mặc định nằm trong một transaction phân tán duy nhất.

Ví dụ, bốn partition cùng chạy:

```text
partition0: chunk 1 COMMIT, chunk 2 COMMIT, COMPLETED
partition1: chunk 1 COMMIT, chunk 2 FAILED
partition2: chunk 1 COMMIT, chunk 2 COMMIT, COMPLETED
partition3: chunk 1 COMMIT, chunk 2 COMMIT, COMPLETED
```

Khi partition1 thất bại, các chunk đã commit của partition1 và dữ liệu đã commit của những partition khác không tự động rollback. JobRepository ghi nhận trạng thái từng worker để có thể restart phần chưa hoàn tất.

Nếu nghiệp vụ yêu cầu tất cả partition thành công hoặc không có thay đổi nào được áp dụng, cần một chiến lược bù trừ hoặc thiết kế staging/publish riêng. Có thể ghi kết quả vào vùng staging theo batch ID rồi chỉ chuyển trạng thái/publish khi mọi partition hoàn tất. Không nên giả định partitioning cung cấp atomicity toàn job.

## 12. Lỗi và retry ở cấp partition

Một partition có thể thất bại do lỗi dữ liệu, database, timeout hoặc lỗi trong processor/writer. Manager step tổng thể sẽ phản ánh kết quả của các worker theo cơ chế điều phối. Cần phân biệt:

- Retry một item trong chunk.
- Retry thao tác đọc/ghi theo fault-tolerant step.
- Restart một worker `StepExecution` đã thất bại.
- Restart toàn bộ manager step/job.

Đây là những cấp phục hồi khác nhau. Tăng retry limit ở worker không giải quyết lỗi partitioner chia sai dữ liệu. Restart manager không bảo đảm mọi tác dụng phụ ngoài transaction được hoàn tác.

Các worker cần ghi log có partition name hoặc batch reference để có thể tìm ra partition gây lỗi. Khi xử lý sự cố, cần kiểm tra `StepExecution` của partition đó, counter, exception và checkpoint thay vì chỉ nhìn trạng thái tổng thể của manager step.

## 13. Giới hạn metadata và JobRepository

Mỗi partition tạo ra metadata thực thi trong JobRepository. Khi số partition lớn, số `StepExecution`, lần cập nhật trạng thái và checkpoint cũng tăng. Repository có thể trở thành nút thắt nếu nhiều worker cùng ghi metadata với tần suất cao.

Các yếu tố cần cân nhắc:

- Số partition trên mỗi JobExecution.
- Tần suất cập nhật ExecutionContext/checkpoint.
- Kích thước context được serialize.
- Số worker đồng thời cập nhật metadata.
- Index và hiệu năng của các bảng Spring Batch metadata.
- Chính sách lưu giữ và dọn dẹp lịch sử execution.

Không nên tạo một partition cho mỗi bản ghi nếu dữ liệu có thể được gom thành các phạm vi lớn hơn. Số partition quá cao làm tăng chi phí scheduling và metadata mà không nhất thiết tăng throughput.

JobRepository cần được cấu hình bền vững và dùng nhất quán giữa manager và worker. Trong remote partitioning, các worker cần nhìn thấy metadata/repository phù hợp để trạng thái execution được quản lý đúng. Nếu mỗi node ghi vào repository độc lập mà không có cơ chế đồng bộ, khả năng theo dõi và restart sẽ không đáng tin cậy.

## 14. Remote partitioning cần hạ tầng bổ sung

Trong remote partitioning, manager gửi yêu cầu thực thi partition đến các worker process khác thông qua middleware hoặc cơ chế truyền tin. Worker nhận yêu cầu, thực hiện step và trả kết quả. Đây là mô hình phân tán, nhưng không phải tính năng tự động có được chỉ bằng API partitioning cơ bản.

Ứng dụng cần giải quyết thêm:

- Message transport và định tuyến đến worker.
- Serialization của yêu cầu và context.
- Worker registration, availability và health check.
- Retry khi message gửi/nhận thất bại.
- Xử lý message trùng hoặc worker chết giữa chừng.
- Bảo đảm manager nhận được kết quả cuối cùng.
- Chia sẻ JobRepository hoặc cơ chế metadata tương thích.
- Quản lý version của code/config giữa manager và worker.
- Bảo mật kênh truyền và quyền truy cập dữ liệu.

Nếu worker nhận message hai lần, cần bảo đảm cùng partition không tạo tác dụng phụ nghiệp vụ lặp. Cần có định danh partition/execution ổn định và cơ chế idempotency phù hợp.

Remote partitioning phù hợp khi mỗi worker cần đọc một phần dữ liệu từ nguồn và xử lý độc lập. Nếu manager đọc dữ liệu rồi gửi từng chunk cho worker xử lý, mô hình remote chunking có thể phù hợp hơn. Hai mô hình có điểm khác nhau về nơi đọc dữ liệu và nơi điều phối chunk.

## 15. Partitioning khác multi-threaded step và remote chunking

Spring Batch có nhiều cách tăng concurrency. Chọn sai mô hình có thể tạo thêm phức tạp mà không giải quyết đúng nút thắt.

| Mô hình | Cách chia công việc | Phù hợp khi |
|---|---|---|
| Multi-threaded step | Nhiều thread cùng tham gia xử lý một step; item/chunk được điều phối theo cấu hình. | Logic xử lý có thể chạy đồng thời và reader/writer cùng tài nguyên hỗ trợ concurrency. |
| Local partitioning | Chia thành nhiều `StepExecution`, mỗi worker nhận một phạm vi dữ liệu riêng trong cùng process. | Dữ liệu có thể phân vùng độc lập và cần trạng thái/restart riêng theo partition. |
| Remote partitioning | Manager phân phối worker step/partition đến process hoặc node khác. | Cần scale worker qua nhiều process/máy và có hạ tầng truyền tin phù hợp. |
| Remote chunking | Manager đọc item, gửi chunk đến worker để xử lý/ghi. | Muốn tập trung việc đọc ở manager và phân phối chunk sang worker. |

Partitioning thường có lợi khi mỗi worker có thể tự đọc phạm vi dữ liệu của mình. Nếu một reader duy nhất phải đọc tuần tự rồi mới gửi item đến worker, remote chunking có thể phù hợp hơn.

## 16. Khi nào partitioning không đem lại lợi ích?

Partitioning có thể không phù hợp hoặc không cải thiện hiệu năng trong các trường hợp:

- Tổng lượng dữ liệu nhỏ, thời gian khởi tạo worker và metadata lớn hơn thời gian xử lý.
- Công việc bị giới hạn bởi một tài nguyên tuần tự không thể chia nhỏ.
- Các item phụ thuộc thứ tự toàn cục hoặc cùng cập nhật một aggregate.
- Database đã bão hòa và nhiều worker chỉ làm tăng lock contention.
- Một partition chứa phần lớn dữ liệu, khiến các worker khác nhàn rỗi.
- Reader/writer không thread-safe và việc tạo instance riêng quá tốn kém.
- Phạm vi dữ liệu không thể xác định ổn định qua restart.
- Công việc cần một transaction atomic xuyên suốt toàn bộ tập dữ liệu.

Trong những trường hợp này, tối ưu SQL, index, chunk size, writer batch hoặc xử lý tuần tự có thể đem lại kết quả tốt hơn. Cần đo trước và sau khi thay đổi thay vì giả định concurrency luôn cải thiện throughput.

## 17. Quy trình thiết kế partitioning có kiểm soát

Khi triển khai partitioning trong module core, có thể đi theo các bước:

1. **Xác định đơn vị dữ liệu độc lập:** chọn khóa hoặc nhóm nghiệp vụ để chia.
2. **Chốt tập dữ liệu:** dùng batch ID, watermark hoặc snapshot để worker cùng xử lý một phạm vi ổn định.
3. **Thiết kế partitioner:** tạo tên và context có ranh giới rõ, không chồng lấn và không bỏ sót.
4. **Thiết kế worker step:** dùng reader/writer theo scope của từng partition và lấy tham số từ Step ExecutionContext.
5. **Chọn local hay remote:** local khi cùng JVM đủ năng lực; remote khi thực sự cần process/node khác và đã có hạ tầng phân phối.
6. **Chọn grid size và executor:** bắt đầu với concurrency vừa phải, đo database và downstream rồi điều chỉnh.
7. **Kiểm soát tài nguyên:** connection pool, thread pool, file, API rate limit và state dùng chung.
8. **Thiết kế restart:** giữ partition name/range ổn định, bật checkpoint và dùng writer idempotent.
9. **Thiết kế quan sát:** log partition name, batch reference, thời gian, counter và exception.
10. **Đo hiệu năng:** so sánh throughput, thời gian partition chậm nhất, lock wait, connection wait và metadata overhead.

Không nên bắt đầu bằng số partition thật lớn. Hãy chạy thử với một số mức concurrency nhỏ, quan sát tài nguyên và tăng dần khi hệ thống còn khả năng đáp ứng.

## 18. Các lỗi thường gặp khi dùng partitioning

| Vấn đề | Nguyên nhân có thể gặp | Hướng xử lý |
|---|---|---|
| Tăng grid size nhưng job không nhanh hơn | Executor, database hoặc hệ thống đích đã là nút thắt. | Đo concurrency thực tế và bottleneck trước khi tăng. |
| Bản ghi bị xử lý hai lần | Các partition có phạm vi chồng lấn hoặc worker retry tác dụng phụ. | Kiểm tra partitioner và dùng khóa/idempotency cho ghi dữ liệu. |
| Bản ghi bị bỏ sót | Ranh giới partition có khoảng trống hoặc tập dữ liệu thay đổi khi chia. | Kiểm tra toàn bộ khoảng, snapshot và watermark. |
| Một worker chạy lâu hơn hẳn | Dữ liệu phân bố lệch hoặc partition có độ phức tạp khác nhau. | Chia theo số lượng/khối lượng ước tính và điều chỉnh dựa trên metric. |
| Restart tạo partition khác lần đầu | Tên/range partition không ổn định hoặc nguồn đã thay đổi. | Giữ partition identity và tập dữ liệu cố định trong cùng JobInstance. |
| Lỗi race condition | Worker dùng chung reader/writer/cache mutable không thread-safe. | Tạo instance theo partition, đồng bộ hóa hoặc phân vùng tài nguyên. |
| Database quá tải | Quá nhiều worker cùng truy vấn/cập nhật. | Giảm concurrency, tối ưu query/index và kiểm soát connection pool. |
| JobRepository tăng tải | Quá nhiều partition hoặc context/checkpoint lớn. | Giảm số partition, lưu context nhỏ và tối ưu metadata retention. |
| Remote worker không cập nhật trạng thái | Message/response hoặc repository không được cấu hình nhất quán. | Kiểm tra transport, retry, worker health và metadata repository. |
| Một partition thất bại nhưng dữ liệu khác đã commit | Mỗi worker có transaction riêng, không có transaction toàn cục. | Thiết kế restart, staging hoặc bù trừ theo nghiệp vụ. |

## 19. Những điểm cần ghi nhớ

- Partitioning chia một step thành nhiều worker execution, mỗi partition có `StepExecution` và `ExecutionContext` riêng.
- Spring Batch Core cung cấp cơ chế điều phối; ứng dụng phải tự thiết kế cách chia dữ liệu đúng nghiệp vụ.
- `gridSize` là gợi ý số partition, không phải số thread hoặc số máy chắc chắn chạy đồng thời.
- `TaskExecutor` thường tạo local partitioning trong cùng process; remote partitioning cần transport và hạ tầng bổ sung.
- Core không tự cân bằng lại partition đang chạy; dữ liệu lệch làm partition chậm nhất quyết định thời gian tổng thể.
- Worker cần phạm vi dữ liệu độc lập, partition name ổn định và resource phù hợp với concurrency.
- Database, connection pool, API rate limit, CPU, I/O và JobRepository đều có thể giới hạn khả năng mở rộng.
- ExecutionContext nên chứa metadata nhỏ, có thể serialize và đủ để worker xác định phạm vi.
- Các partition có transaction riêng; một partition thất bại không tự rollback dữ liệu đã commit của partition khác.
- Restart phụ thuộc partition identity, checkpoint, dữ liệu nguồn ổn định và writer có khả năng xử lý lặp an toàn.
- Partitioning khác multi-threaded step và remote chunking; hãy chọn theo nơi đọc dữ liệu và cách phân chia công việc.
- Đo throughput và bottleneck thực tế trước khi tăng số partition hoặc worker.

Partitioning trong Spring Batch Core là cơ chế chia và điều phối công việc, không phải giải pháp tự động cho mọi vấn đề scale. Muốn đạt hiệu quả, ứng dụng cần chia dữ liệu chính xác, giữ mỗi worker độc lập, quản lý tài nguyên dùng chung, bảo đảm metadata/restart ổn định và đo giới hạn của hệ thống đích. Khi các điều kiện đó được đáp ứng, partitioning mới giúp tăng concurrency mà vẫn giữ kết quả batch có thể theo dõi và phục hồi.
