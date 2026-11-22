# Phân biệt partitioning với chunk processing

Trong Spring Batch, **chunk processing** và **partitioning** giải quyết hai vấn đề khác nhau. Chunk processing chia dữ liệu trong một Step thành các nhóm item để đọc, xử lý, ghi và commit theo từng transaction. Partitioning chia một công việc Step thành nhiều phần độc lập, mỗi phần được chạy bằng một worker StepExecution và có thể được thực thi song song.

Hai cơ chế không loại trừ nhau. Một Job có thể partition một Step thành nhiều worker, rồi mỗi worker lại xử lý dữ liệu theo chunk. Đây là cách phổ biến để tăng khả năng xử lý song song mà vẫn giữ transaction boundary và checkpoint ở cấp chunk.

## 1. Chunk processing là gì?

Chunk-oriented processing là mô hình xử lý dữ liệu theo nhóm item. Một Step thường có ba thành phần:

1. `ItemReader` đọc item từ nguồn dữ liệu.
2. `ItemProcessor` kiểm tra, lọc hoặc biến đổi từng item.
3. `ItemWriter` ghi nhóm item đã xử lý.

Khi số item đạt commit interval, Spring Batch gọi Writer và commit transaction của chunk. Nếu một chunk thất bại và lỗi cần rollback, các thay đổi trong transaction của chunk hiện tại được hoàn tác; những chunk đã commit trước đó vẫn được giữ.

```text
Một chunk-oriented Step
       |
       v
  ItemReader
       |
       v
 ItemProcessor
       |
       v
 đủ item theo commit interval
       |
       v
   ItemWriter
       |
       v
    COMMIT
       |
       +----> Đọc chunk tiếp theo
```

Ví dụ cấu hình một Step xử lý 500 item mỗi chunk trong Spring Batch 5 trở lên:

```java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;

@Bean
public Step importCustomersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Customer> reader,
        ItemProcessor<Customer, Customer> processor,
        ItemWriter<Customer> writer) {

    return new StepBuilder("importCustomersStep", jobRepository)
            .<Customer, Customer>chunk(500, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}
```

Trong ví dụ, `500` là commit interval. Step có thể đọc và xử lý toàn bộ tập dữ liệu bằng một luồng thực thi, commit sau mỗi chunk. Chunk processing tự nó không có nghĩa là dữ liệu được chia cho nhiều worker hoặc được xử lý song song.

## 2. Partitioning là gì?

Partitioning chia một Step logic thành nhiều phần công việc gọi là partition. Spring Batch tạo một `StepExecution` riêng cho mỗi partition. Một Step đóng vai trò manager điều phối các worker StepExecution; mỗi worker thực hiện cùng cấu hình Step nhưng nhận một `ExecutionContext` riêng để biết phần dữ liệu mình phải xử lý.

Ví dụ, bảng `customer` có ID từ 1 đến 1.000.000. Có thể chia dữ liệu thành bốn khoảng không chồng lấn:

```text
Manager Step: partitionCustomersStep
       |
       +--> Worker StepExecution 0: customer_id 1       - 250000
       |
       +--> Worker StepExecution 1: customer_id 250001  - 500000
       |
       +--> Worker StepExecution 2: customer_id 500001  - 750000
       |
       +--> Worker StepExecution 3: customer_id 750001  - 1000000
```

Mỗi worker chỉ đọc phần dữ liệu được giao. Nếu dùng `TaskExecutor` phù hợp, các worker có thể chạy đồng thời trên nhiều thread. Trong môi trường phân tán, manager có thể gửi các partition tới worker ở process hoặc máy khác thông qua cơ chế remote partitioning.

Partitioning là cơ chế chia và phân phối công việc. Nó không quy định worker phải xử lý item theo cách nào. Worker có thể là chunk-oriented Step, Tasklet Step hoặc một loại Step khác tùy thiết kế.

## 3. Hai cơ chế nằm trên hai trục khác nhau

Điểm cần nhớ là chunk xác định **đơn vị xử lý và commit**, còn partition xác định **đơn vị phân chia và phân phối công việc**.

| Tiêu chí | Chunk processing | Partitioning |
|---|---|---|
| Mục đích chính | Xử lý dữ liệu theo nhóm item và commit theo transaction | Chia một Step thành các phần độc lập để điều phối worker |
| Đơn vị chính | Chunk gồm một nhóm item | Partition có một worker StepExecution |
| Thành phần quan trọng | Reader, Processor, Writer, commit interval | Partitioner, manager Step, worker Step, PartitionHandler |
| Trạng thái | StepExecution và ExecutionContext của Step | Mỗi partition có StepExecution và ExecutionContext riêng |
| Song song | Chunk mặc định có thể chạy tuần tự; cần cơ chế concurrency riêng để song song | Có thể chạy nhiều partition đồng thời qua executor hoặc worker phân tán |
| Transaction | Thường một transaction cho mỗi chunk | Phụ thuộc cách worker Step xử lý; nếu worker là chunk Step thì mỗi chunk có transaction riêng |
| Restart | Dựa vào checkpoint và trạng thái của StepExecution | Có thể restart theo trạng thái và ExecutionContext của từng partition |
| Cách chia dữ liệu | Chia theo số item trong một lần commit | Chia theo phạm vi hoặc khóa dữ liệu, ví dụ ID, ngày, tenant hoặc file |

Vì hai cơ chế bổ sung cho nhau, không nên đặt câu hỏi phải chọn chunk hay partitioning trong mọi trường hợp. Có thể dùng chunk đơn lẻ nếu dữ liệu vừa phải hoặc không cần song song; dùng partitioning với worker chunk-oriented nếu dữ liệu lớn và có thể chia thành các phần độc lập.

## 4. Kết hợp partitioning với chunk processing

Một thiết kế thường gặp là manager Step tạo nhiều partition, sau đó mỗi partition chạy cùng một worker Step có cấu hình chunk. Mỗi worker nhận phạm vi dữ liệu riêng, đọc dữ liệu trong phạm vi đó và commit theo commit interval.

```text
Job: customerImportJob
       |
       v
Manager Step: partitionCustomersStep
       |
       +----------------+----------------+----------------+
       |                |                |                |
       v                v                v                v
   Partition 0      Partition 1      Partition 2      Partition 3
       |                |                |                |
       v                v                v                v
   Worker Step      Worker Step      Worker Step      Worker Step
       |                |                |                |
       v                v                v                v
   Chunk 1           Chunk 1           Chunk 1           Chunk 1
   COMMIT            COMMIT            COMMIT            COMMIT
       |                |                |                |
       v                v                v                v
   Chunk 2           Chunk 2           Chunk 2           Chunk 2
   COMMIT            COMMIT            COMMIT            COMMIT
```

Giả sử có một triệu khách hàng, bốn partition và commit interval 500. Mỗi worker xử lý khoảng 250.000 khách hàng theo các chunk 500 item. Nếu dữ liệu được chia đều, mỗi worker có khoảng 500 chunk. Số partition và số item mỗi chunk là hai cấu hình độc lập:

- `gridSize` hoặc số partition quyết định có bao nhiêu phần công việc.
- `chunk(500, transactionManager)` quyết định mỗi worker commit sau bao nhiêu item.

Tăng `gridSize` không tự động tăng commit interval. Thay đổi chunk size cũng không tự động tạo thêm worker.

## 5. Partitioner chia dữ liệu thành các phạm vi

`Partitioner` là interface tạo ra các `ExecutionContext` cho worker. Mỗi entry trong map đại diện cho một partition; key thường là tên partition và value chứa dữ liệu cần thiết để worker xử lý phần việc được giao.

```java
public interface Partitioner {
    Map<String, ExecutionContext> partition(int gridSize);
}
```

Ví dụ chia một khoảng ID liên tục thành nhiều partition:

```java
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.item.ExecutionContext;

public class CustomerRangePartitioner implements Partitioner {

    private final long minId;
    private final long maxId;

    public CustomerRangePartitioner(long minId, long maxId) {
        if (minId > maxId) {
            throw new IllegalArgumentException("minId must be <= maxId");
        }
        this.minId = minId;
        this.maxId = maxId;
    }

    @Override
    public Map<String, ExecutionContext> partition(int gridSize) {
        if (gridSize < 1) {
            throw new IllegalArgumentException("gridSize must be positive");
        }

        long totalIds = maxId - minId + 1;
        long rangeSize = (totalIds + gridSize - 1) / gridSize;
        Map<String, ExecutionContext> partitions = new LinkedHashMap<>();

        long start = minId;
        int partitionNumber = 0;
        while (start <= maxId) {
            long end = Math.min(start + rangeSize - 1, maxId);

            ExecutionContext context = new ExecutionContext();
            context.putLong("minId", start);
            context.putLong("maxId", end);
            partitions.put("partition" + partitionNumber, context);

            start = end + 1;
            partitionNumber++;
        }

        return partitions;
    }
}
```

Ví dụ này chia một khoảng ID liên tục, không đảm bảo mỗi partition có đúng số bản ghi nếu bảng có nhiều khoảng trống trong ID. Với dữ liệu thực tế, có thể chia theo khoảng ngày, tenant, mã vùng, hash key hoặc danh sách file. Điều quan trọng là các partition phải không chồng lấn và phải bao phủ đúng tập dữ liệu cần xử lý.

Nếu nguồn không có dữ liệu, nên xử lý trường hợp rỗng rõ ràng trước khi tạo partition hoặc trả về một partition rỗng theo chính sách của ứng dụng. Không nên để giá trị `minId` hoặc `maxId` null rồi tiếp tục chia phạm vi.

## 6. Worker Step đọc dữ liệu theo ExecutionContext

Mỗi worker StepExecution có `ExecutionContext` riêng. Có thể dùng `@StepScope` để late-bind giới hạn partition vào reader. Ví dụ, reader dùng JDBC cursor để chỉ đọc các khách hàng trong khoảng ID được giao:

```java
import javax.sql.DataSource;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.database.JdbcCursorItemReader;
import org.springframework.batch.item.database.builder.JdbcCursorItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.BeanPropertyRowMapper;
import org.springframework.jdbc.core.PreparedStatementSetter;

@Bean
@StepScope
public JdbcCursorItemReader<Customer> customerPartitionReader(
        DataSource dataSource,
        @Value("#{stepExecutionContext['minId']}") Long minId,
        @Value("#{stepExecutionContext['maxId']}") Long maxId) {

    PreparedStatementSetter parameters = ps -> {
        ps.setLong(1, minId);
        ps.setLong(2, maxId);
    };

    return new JdbcCursorItemReaderBuilder<Customer>()
            .name("customerPartitionReader")
            .dataSource(dataSource)
            .sql("select id, name from customer "
                    + "where id >= ? and id <= ? order by id")
            .preparedStatementSetter(parameters)
            .rowMapper(new BeanPropertyRowMapper<>(Customer.class))
            .saveState(true)
            .build();
}
```

Mỗi worker nhận `minId` và `maxId` khác nhau, vì vậy reader truy vấn phạm vi riêng. `@StepScope` cho phép các giá trị trong `stepExecutionContext` được cung cấp khi worker StepExecution bắt đầu. Mỗi partition có một StepExecution nên có thể có một target reader riêng với tham số riêng.

Trong ứng dụng thực tế, hãy bảo đảm tên reader ổn định để metadata có thể lưu checkpoint. Reader và nguồn dữ liệu cũng cần được cấu hình phù hợp với restart. Ví dụ dùng `JdbcCursorItemReader` ở trên để minh họa phạm vi truy vấn; với workload cần phân trang hoặc database có giới hạn cursor, có thể chọn `JdbcPagingItemReader`.

## 7. Cấu hình manager Step và worker Step

Worker Step có thể là chunk-oriented Step thông thường. Manager Step dùng partitioner để tạo các worker StepExecution:

```java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemWriter;
import org.springframework.batch.item.database.JdbcCursorItemReader;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.TaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class CustomerPartitionJobConfig {

    @Bean
    public Step customerWorkerStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            JdbcCursorItemReader<Customer> customerPartitionReader,
            ItemProcessor<Customer, Customer> customerProcessor,
            ItemWriter<Customer> customerWriter) {

        return new StepBuilder("customerWorkerStep", jobRepository)
                .<Customer, Customer>chunk(500, transactionManager)
                .reader(customerPartitionReader)
                .processor(customerProcessor)
                .writer(customerWriter)
                .build();
    }

    @Bean
    public TaskExecutor partitionTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(4);
        executor.setThreadNamePrefix("customer-partition-");
        executor.initialize();
        return executor;
    }

    @Bean
    public Step partitionCustomersStep(
            JobRepository jobRepository,
            Step customerWorkerStep,
            Partitioner customerRangePartitioner,
            TaskExecutor partitionTaskExecutor) {

        return new StepBuilder("partitionCustomersStep", jobRepository)
                .partitioner("customerWorkerStep", customerRangePartitioner)
                .step(customerWorkerStep)
                .gridSize(4)
                .taskExecutor(partitionTaskExecutor)
                .build();
    }

    @Bean
    public Job customerImportJob(
            JobRepository jobRepository,
            Step partitionCustomersStep) {
        return new JobBuilder("customerImportJob", jobRepository)
                .start(partitionCustomersStep)
                .build();
    }
}
```

Ví dụ giả định các bean `customerRangePartitioner`, `customerProcessor` và `customerWriter` đã được khai báo. `customerPartitionReader` là bean `@StepScope` ở phần trước. `gridSize(4)` yêu cầu tạo tối đa bốn partition trong thiết kế này; `ThreadPoolTaskExecutor` có bốn thread để có thể thực thi chúng đồng thời.

`gridSize` và kích thước thread pool là hai cấu hình có liên quan nhưng không phải cùng một khái niệm. Nếu tạo 8 partition nhưng executor chỉ có 4 thread, tối đa 4 worker chạy đồng thời; các partition còn lại chờ đến khi có thread rảnh. Nếu executor chỉ có một thread, partitioning vẫn chia dữ liệu thành nhiều worker StepExecution nhưng không đạt song song thực sự.

## 8. Partitioning khác multi-threaded Step như thế nào?

Ngoài partitioning, Spring Batch còn hỗ trợ multi-threaded Step, nơi các chunk có thể được xử lý trên nhiều thread trong cùng một Step. Cả hai đều có thể tăng concurrency nhưng cách cô lập trạng thái khác nhau.

| Tiêu chí | Multi-threaded Step | Partitioned Step |
|---|---|---|
| Cách chia việc | Các chunk của cùng Step được thực thi trên nhiều thread | Một Step được chia thành nhiều worker StepExecution |
| ExecutionContext | Cùng StepExecution quản lý trạng thái của Step | Mỗi partition có StepExecution và ExecutionContext riêng |
| Reader | Có thể được nhiều thread dùng chung tùy cấu hình; cần đánh giá thread safety | Thường tạo reader riêng theo StepScope cho từng partition |
| Phân chia dữ liệu | Cần cơ chế concurrency và reader an toàn để tránh tranh chấp | Partitioner chỉ rõ phạm vi hoặc khóa dữ liệu cho từng worker |
| Phù hợp | Logic item độc lập, component thread-safe và không cần phân vùng phức tạp | Dữ liệu có thể chia thành các phần độc lập hoặc cần chạy worker phân tán |
| Theo dõi và restart | Theo metadata của StepExecution chung và trạng thái reader | Có thể theo dõi và restart từng partition qua StepExecution riêng |

Partitioning thường phù hợp khi có thể phân chia dữ liệu rõ ràng, ví dụ mỗi worker xử lý một vùng ID hoặc một nhóm tenant. Multi-threaded Step có thể đơn giản hơn nếu reader, processor và writer đều hỗ trợ concurrency và không cần các phạm vi dữ liệu riêng.

## 9. Partitioning local và remote partitioning

Partitioning có thể chạy trong cùng một JVM hoặc phân phối worker qua nhiều process/máy:

- **Local partitioning:** manager và worker chạy trong cùng application process. `TaskExecutorPartitionHandler` thường dùng executor để chạy worker trên các thread khác nhau.
- **Remote partitioning:** manager tạo partition và gửi thông điệp mô tả công việc đến worker qua middleware như message broker. Worker ở process khác thực hiện Step và cập nhật metadata theo cấu hình repository chung hoặc cơ chế đồng bộ được thiết kế.

```text
Local partitioning
  Manager Step
      |
      +--> Thread 1 / Worker 1
      +--> Thread 2 / Worker 2
      +--> Thread 3 / Worker 3

Remote partitioning
  Manager Step
      |
      v
  Message Broker
      |
      +--> Worker application A
      +--> Worker application B
      +--> Worker application C
```

Local partitioning phù hợp khi muốn tận dụng nhiều core trong một ứng dụng. Remote partitioning phù hợp khi cần mở rộng worker trên nhiều process hoặc máy. Remote partitioning cần thêm hạ tầng message, xử lý thông điệp, retry, quan sát worker và quản lý lỗi mạng; không nên chọn chỉ vì muốn tăng số thread.

## 10. Restart và checkpoint trong partitioning

Mỗi partition có StepExecution riêng và ExecutionContext riêng. Khi một partition thất bại, metadata của partition đó giúp xác định phần công việc cần tiếp tục. Các partition đã hoàn thành thường được nhận diện qua metadata và không cần chạy lại trong lần restart, theo chính sách restart của Step.

Ví dụ:

```text
Manager StepExecution: partitionCustomersStep
  |
  +--> partition0: COMPLETED
  |       worker StepExecution #1
  |
  +--> partition1: COMPLETED
  |       worker StepExecution #2
  |
  +--> partition2: FAILED
  |       worker StepExecution #3
  |
  +--> partition3: COMPLETED
          worker StepExecution #4

Restart Job
  |
  +--> Các partition hoàn thành được giữ trạng thái
  +--> Partition thất bại được restart theo checkpoint của nó
```

Để restart đáng tin cậy:

1. Tên partition phải ổn định qua các lần chạy lại của cùng đơn vị công việc.
2. Các phạm vi dữ liệu phải được tái tạo nhất quán; tránh thay đổi min/max hoặc điều kiện lọc giữa lần chạy đầu và lần restart.
3. Reader cần lưu state nếu muốn tiếp tục từ checkpoint trong từng partition.
4. Writer cần xử lý an toàn khi item được thử lại sau rollback.
5. Dữ liệu đầu vào cần có snapshot hoặc watermark phù hợp để bản ghi mới không làm thay đổi ranh giới partition giữa hai lần chạy.

Nếu Partitioner tính lại các phạm vi dựa trên dữ liệu nguồn đã thay đổi, có thể phát sinh khoảng trống hoặc chồng lấn khi restart. Với dữ liệu thay đổi liên tục, nên xác định watermark hoặc snapshot ID cho JobInstance và dùng nó để tạo partition ổn định.

## 11. Cách chia dữ liệu để partition hiệu quả

Không phải cách chia nào cũng tạo tải cân bằng. Nếu một partition có 10.000 item nhưng partition khác có 2 triệu item, worker nhanh sẽ kết thúc sớm trong khi worker nặng vẫn chạy, làm giảm hiệu quả song song.

Một số chiến lược chia phổ biến:

| Chiến lược | Ví dụ | Điểm cần chú ý |
|---|---|---|
| Khoảng primary key | ID 1–100.000, 100.001–200.000 | Đơn giản; ID có nhiều khoảng trống có thể làm số item không đều. |
| Khoảng thời gian | Mỗi worker xử lý một ngày hoặc một tháng | Phù hợp dữ liệu theo thời gian; cần xử lý timezone và biên thời gian chính xác. |
| Theo tenant hoặc vùng | Mỗi worker xử lý một nhóm khách hàng | Tránh một tenant lớn làm lệch tải. |
| Theo hash key | `hash(customer_id) mod N` | Có thể cân bằng tốt; query và checkpoint cần dùng cùng quy tắc. |
| Theo danh sách file | Mỗi partition nhận một nhóm file | Dễ cô lập file; cần theo dõi file đã hoàn tất và xử lý file lỗi. |

Khi chọn số partition, cần xem số core CPU, khả năng connection pool, tải database, dung lượng message broker và thời gian xử lý trung bình của mỗi phần. Tăng partition quá nhiều có thể tạo quá nhiều connection, transaction và metadata, làm hiệu năng giảm thay vì tăng.

## 12. Khi nào dùng chunk, khi nào dùng partitioning?

### Chỉ dùng chunk processing

Chọn chunk-oriented Step đơn lẻ khi:

- Dữ liệu có quy mô vừa phải hoặc thời gian chạy đã đáp ứng SLA.
- Xử lý tuần tự là đủ.
- Nguồn dữ liệu khó chia thành các phạm vi độc lập.
- Logic ghi cần thứ tự toàn cục hoặc chia nhỏ sẽ gây tranh chấp.
- Muốn triển khai đơn giản, dễ debug và vận hành.

### Dùng partitioning kết hợp chunk

Chọn partitioned Step với worker chunk-oriented khi:

- Dữ liệu lớn và có thể chia thành các phần không chồng lấn.
- Các phần có thể xử lý độc lập.
- Reader có thể nhận phạm vi riêng qua ExecutionContext.
- Database và writer chịu được concurrency.
- Cần restart và quan sát trạng thái từng phần.

### Cân nhắc multi-threaded Step hoặc remote partitioning

Multi-threaded Step có thể phù hợp nếu các thành phần dùng chung thread-safe và không cần tạo phạm vi dữ liệu riêng. Remote partitioning phù hợp khi cần phân phối worker trên nhiều process hoặc máy và đã có hạ tầng giao tiếp phù hợp.

## 13. Các lưu ý về transaction và hiệu năng

Partitioning không làm mất transaction boundary của worker. Nếu worker là chunk Step với commit interval 500, mỗi worker quản lý transaction cho từng chunk. Nhiều worker có thể mở nhiều transaction đồng thời, vì vậy database phải đủ khả năng chịu tải.

Một số rủi ro cần theo dõi:

- **Lock contention:** các partition có thể cập nhật cùng bảng hoặc cùng khóa; chia dữ liệu không chồng lấn ở Reader chưa chắc tránh được tranh chấp ở Writer.
- **Connection pool:** mỗi worker có thể cần connection riêng; số thread vượt quá pool size có thể khiến worker chờ connection.
- **Uneven partitions:** một partition lớn hơn nhiều partition khác sẽ kéo dài thời gian hoàn thành toàn Step.
- **Retry và idempotency:** một worker thất bại có thể chạy lại item trong chunk chưa commit; writer cần chống ghi trùng.
- **Memory:** mỗi worker giữ reader, processor, buffer và chunk riêng; tăng số worker làm tăng mức sử dụng heap.
- **External side effects:** gọi API hoặc gửi message trong worker không tự rollback cùng transaction database.

Nên benchmark với nhiều giá trị `gridSize` và chunk size. Đo throughput tổng, thời gian partition chậm nhất, connection pool usage, lock wait, rollback, heap và GC. Tăng concurrency chỉ hữu ích khi nguồn dữ liệu và đích ghi có thể phục vụ các worker đồng thời.

## 14. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| Chunk processing đồng nghĩa với xử lý song song | Chunk chỉ xác định nhóm item và transaction; Step có thể chạy tuần tự. |
| Partitioning thay thế chunk processing | Partitioning chia worker; mỗi worker vẫn có thể dùng chunk processing. |
| `gridSize` là commit interval | `gridSize` liên quan số partition; commit interval cấu hình ở worker chunk Step. |
| Có nhiều partition nghĩa là luôn chạy đồng thời | Cần `PartitionHandler`/executor phù hợp và đủ worker capacity. |
| `@StepScope` tự làm reader thread-safe trong multi-threaded Step | StepScope gắn bean với StepExecution; các thread trong cùng StepExecution vẫn có thể chia sẻ target. |
| Chia ID thành các khoảng luôn cân bằng số item | Khoảng ID có thể có nhiều khoảng trống hoặc mật độ dữ liệu khác nhau. |
| Một partition thất bại làm mất dữ liệu các partition đã commit | Transaction và metadata của từng worker được quản lý riêng; kết quả đã commit vẫn tồn tại. |
| Tăng partition luôn làm Job nhanh hơn | Database contention, connection pool, overhead và partition lệch tải có thể làm Job chậm hơn. |

## Kết luận

Chunk processing chia dữ liệu thành các nhóm item để đọc, xử lý, ghi và commit theo transaction. Partitioning chia một Step thành nhiều worker StepExecution, mỗi worker nhận một phạm vi dữ liệu và có ExecutionContext riêng để có thể chạy độc lập hoặc song song. Hai cơ chế bổ sung cho nhau: một Job thường partition dữ liệu thành nhiều phần, rồi mỗi worker xử lý phần được giao bằng chunk. Khi thiết kế, cần chọn phạm vi partition không chồng lấn, giữ chunk size phù hợp, giới hạn concurrency theo năng lực database và bảo đảm reader/writer hỗ trợ restart. Chọn đúng hai lớp này giúp mở rộng throughput mà vẫn duy trì transaction boundary và khả năng phục hồi rõ ràng.
