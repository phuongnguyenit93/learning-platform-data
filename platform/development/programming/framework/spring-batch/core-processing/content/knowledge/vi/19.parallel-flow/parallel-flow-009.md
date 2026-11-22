# Deadlock khi flow chia sẻ resource

Trong Spring Batch, một Job có thể chạy nhiều flow hoặc Step song song để rút ngắn thời gian xử lý. Khi các nhánh song song cùng truy cập một tài nguyên như bảng database, hàng dữ liệu, file, connection pool hoặc dịch vụ bên ngoài, chúng có thể tranh chấp tài nguyên. Một trường hợp nghiêm trọng là **deadlock**: mỗi transaction đang giữ một lock mà transaction còn lại cần, khiến cả hai không thể tiếp tục.

Deadlock thường xuất hiện khi các Step cập nhật cùng nhóm dữ liệu theo thứ tự khác nhau. Ví dụ, flow A khóa bản ghi khách hàng trước rồi khóa tài khoản; flow B khóa tài khoản trước rồi khóa khách hàng. Nếu hai transaction chạy đồng thời, mỗi bên có thể giữ một lock và chờ lock của bên kia. Database thường phát hiện vòng chờ, chọn một transaction làm deadlock victim và rollback transaction đó.

Để giảm deadlock, cần thiết kế ranh giới dữ liệu của từng flow, thứ tự truy cập tài nguyên, thời gian transaction và mức concurrency. Retry có thể giúp phục hồi deadlock tạm thời, nhưng không thay thế việc sửa nguyên nhân tranh chấp.

## 1. Deadlock là gì?

Deadlock xảy ra khi hai hoặc nhiều transaction giữ tài nguyên mà transaction khác đang chờ, tạo thành một vòng chờ không thể tự giải quyết.

Ví dụ hai transaction cập nhật hai dòng trong cùng bảng:

```text
Transaction A                    Transaction B
--------------                    --------------
BEGIN                             BEGIN
Lock row 1                        Lock row 2
                                  Request lock row 1
Request lock row 2                (đang chờ A)
(đang chờ B)                      |
       |                          |
       +-------- wait cycle ------+
```

Transaction A đang giữ lock trên row 1 và chờ row 2. Transaction B đang giữ lock trên row 2 và chờ row 1. Không bên nào có thể tiếp tục. Database phát hiện chu trình trong wait-for graph và thường rollback một transaction để giải phóng lock.

Deadlock khác với một transaction chờ lock thông thường. Chờ lock có thể kết thúc khi transaction đang giữ lock commit hoặc rollback. Deadlock có vòng chờ; database cần phá vòng đó bằng cách hủy một transaction hoặc áp dụng cơ chế xử lý riêng.

## 2. Vì sao parallel flow có thể gây deadlock?

Khi Job có nhiều flow chạy đồng thời, các Step trong những flow đó có thể dùng cùng database hoặc tài nguyên bên ngoài. Mỗi Step thường có transaction riêng theo chunk hoặc theo lần gọi Tasklet. Transaction của các Step chạy trên thread khác nhau có thể cùng giữ lock trên các tài nguyên chung.

Ví dụ Job chia thành hai flow:

```text
                    Job
                     |
                  split()
                 /       \
                v         v
            Flow A      Flow B
                |         |
                v         v
          updateOrder  updateAccount
                |         |
                +----+----+
                     |
             Shared database tables
```

Các tình huống thường tạo tranh chấp:

- Hai Step cập nhật cùng một bản ghi hoặc cùng một nhóm bản ghi.
- Hai Step cập nhật nhiều bảng theo thứ tự khác nhau.
- Một Step giữ lock trong lúc gọi HTTP hoặc chờ file/network.
- Writer cập nhật bảng nghiệp vụ trong khi một flow khác đọc hoặc ghi bảng liên quan có khóa ngoại/index.
- Các partition có phạm vi dữ liệu chồng lấn.
- Một flow cập nhật bảng nghiệp vụ trong khi flow khác cập nhật metadata hoặc bảng trạng thái dùng chung.
- Nhiều Job chạy đồng thời trên cùng database và cùng khóa nghiệp vụ.

Không phải mọi shared resource đều gây deadlock. Nếu các transaction chỉ chờ cùng một lock theo một chiều, hệ thống có thể bị chậm mà không có vòng chờ. Deadlock xuất hiện khi thứ tự giữ và yêu cầu lock tạo thành chu trình.

## 3. Ví dụ deadlock do thứ tự cập nhật khác nhau

Giả sử hai flow cập nhật hai bảng `customer` và `account`.

Flow A thực hiện:

```sql
BEGIN;
UPDATE customer SET status = 'ACTIVE' WHERE id = 10;
UPDATE account SET balance = balance + 100 WHERE customer_id = 10;
COMMIT;
```

Flow B thực hiện theo thứ tự ngược lại:

```sql
BEGIN;
UPDATE account SET balance = balance + 100 WHERE customer_id = 10;
UPDATE customer SET status = 'ACTIVE' WHERE id = 10;
COMMIT;
```

Nếu hai transaction chạy đồng thời, Flow A có thể khóa dòng `customer` trước, còn Flow B khóa dòng `account` trước. Sau đó A chờ account trong khi B chờ customer. Đây là vòng chờ gây deadlock.

Một cách giảm nguy cơ là thống nhất thứ tự truy cập tài nguyên trong mọi flow, ví dụ luôn khóa/cập nhật `customer` trước rồi mới đến `account`. Quy tắc này cần được áp dụng nhất quán ở mọi đường code có thể chạy đồng thời, không chỉ trong hai Step đang quan sát.

Thứ tự bảng không phải yếu tố duy nhất. Database có thể lấy lock trên index, row liên quan, khóa ngoại hoặc tài nguyên nội bộ khác. Khi điều tra deadlock, cần xem execution plan và deadlock report của database, không chỉ so sánh thứ tự câu lệnh ở tầng Java.

## 4. Parallel flow trong Spring Batch

Với Spring Batch 5 trở lên, có thể chạy các flow độc lập song song bằng `split()` và `TaskExecutor`:

```java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.job.flow.Flow;
import org.springframework.batch.core.job.flow.support.SimpleFlow;
import org.springframework.batch.core.job.flow.builder.FlowBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.TaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class ParallelJobConfig {

    @Bean
    public TaskExecutor flowTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(2);
        executor.setThreadNamePrefix("batch-flow-");
        executor.initialize();
        return executor;
    }

    @Bean
    public Flow customerFlow(Step updateCustomerStep) {
        return new FlowBuilder<SimpleFlow>("customerFlow")
                .start(updateCustomerStep)
                .build();
    }

    @Bean
    public Flow accountFlow(Step updateAccountStep) {
        return new FlowBuilder<SimpleFlow>("accountFlow")
                .start(updateAccountStep)
                .build();
    }

    @Bean
    public Job parallelUpdateJob(
            JobRepository jobRepository,
            Flow customerFlow,
            Flow accountFlow,
            TaskExecutor flowTaskExecutor) {

        Flow splitFlow = new FlowBuilder<SimpleFlow>("splitUpdateFlow")
                .start(customerFlow)
                .split(flowTaskExecutor)
                .add(accountFlow)
                .build();

        return new JobBuilder("parallelUpdateJob", jobRepository)
                .start(splitFlow)
                .end()
                .build();
    }
}
```

Ví dụ giả định `updateCustomerStep` và `updateAccountStep` đã được khai báo. Hai flow có thể thực thi đồng thời nhờ executor. Mỗi Step quản lý transaction theo cấu hình của Step; các transaction trên thread khác nhau không tự động trở thành một transaction chung.

`TaskExecutor` quyết định khả năng chạy đồng thời, nhưng không tự giải quyết xung đột dữ liệu. Nếu hai Step cập nhật cùng bản ghi theo thứ tự không nhất quán, tăng số thread có thể làm deadlock xảy ra thường xuyên hơn.

## 5. Phân biệt deadlock với connection pool starvation

Một Job có thể bị chậm hoặc đứng lại vì nhiều loại tranh chấp khác nhau. Cần phân biệt đúng để chọn biện pháp khắc phục.

| Hiện tượng | Dấu hiệu | Nguyên nhân thường gặp |
|---|---|---|
| Database deadlock | Database log báo deadlock hoặc transaction victim; có vòng chờ lock | Các transaction giữ và chờ lock theo chu trình. |
| Lock wait/lock timeout | Transaction chờ một lock quá lâu rồi timeout | Một transaction khác giữ lock lâu, nhưng không nhất thiết có vòng chờ. |
| Connection pool starvation | Thread chờ lấy connection; pool active đạt giới hạn, pending tăng | Số worker/transaction vượt khả năng cấp connection hoặc connection bị giữ quá lâu. |
| Thread starvation | Task đã sẵn sàng nhưng không có thread thực thi | Executor quá nhỏ hoặc thread bị block. |
| Slow query | SQL chạy lâu nhưng không có deadlock | Query thiếu index, execution plan kém hoặc đọc quá nhiều dữ liệu. |

Tăng connection pool không sửa được deadlock do thứ tự lock sai. Ngược lại, giảm concurrency có thể giảm cả lock contention và nhu cầu connection, nhưng cần xác định đúng nguyên nhân trước khi thay đổi cấu hình.

## 6. Giải pháp 1: chia dữ liệu để các flow không cập nhật cùng bản ghi

Biện pháp hiệu quả nhất thường là giảm vùng dữ liệu giao nhau. Nếu có thể, mỗi flow hoặc partition nên sở hữu một tập khóa nghiệp vụ riêng.

Ví dụ chia theo vùng:

```text
Flow A: region = NORTH
  customer_id thuộc nhóm NORTH

Flow B: region = SOUTH
  customer_id thuộc nhóm SOUTH
```

Hoặc chia theo khoảng ID không chồng lấn:

```text
Worker 1: id 1       - 100000
Worker 2: id 100001  - 200000
Worker 3: id 200001  - 300000
```

Khi chia dữ liệu, cần bảo đảm Writer cũng chỉ cập nhật đúng phạm vi được giao. Một Reader lọc theo ID range nhưng Writer cập nhật bảng tổng hợp dùng chung vẫn có thể tạo lock contention.

Nếu nhiều flow bắt buộc cập nhật cùng một thực thể, hãy xác định một Step chịu trách nhiệm cập nhật thực thể đó, hoặc gom thay đổi vào một luồng tuần tự. Có thể chạy song song phần tính toán độc lập rồi hợp nhất kết quả ở một Step cuối.

## 7. Giải pháp 2: thống nhất thứ tự truy cập resource

Nếu nhiều transaction cần khóa nhiều bảng hoặc nhiều dòng, hãy thống nhất thứ tự truy cập. Ví dụ tất cả các đường xử lý đều:

1. Khóa hoặc cập nhật bản ghi `customer`.
2. Khóa hoặc cập nhật bản ghi `account`.
3. Cập nhật bản ghi `order`.

Nếu cần xử lý nhiều ID, nên sắp xếp ID theo cùng một thứ tự trước khi khóa/cập nhật. Điều này giảm khả năng transaction A giữ khóa trên tài nguyên X rồi chờ Y trong khi transaction B giữ Y rồi chờ X.

Ví dụ SQL minh họa:

```sql
BEGIN;
SELECT id FROM customer WHERE id = ? FOR UPDATE;
SELECT id FROM account WHERE customer_id = ? ORDER BY id FOR UPDATE;
-- Cập nhật dữ liệu theo thứ tự đã thống nhất
COMMIT;
```

Cú pháp lock và semantics phụ thuộc database. Hãy xác minh câu lệnh `FOR UPDATE`, mức isolation và thứ tự lock trên hệ quản trị thực tế. Không phải mọi câu `SELECT` đều khóa dòng; cũng không nên thêm pessimistic lock nếu không có nhu cầu nghiệp vụ rõ ràng.

## 8. Giải pháp 3: rút ngắn transaction

Transaction càng dài thì lock càng có thể được giữ lâu, làm tăng cơ hội giao nhau với transaction khác. Trong Spring Batch, chunk processing cho phép commit theo từng nhóm item thay vì giữ một transaction cho toàn bộ Job.

Một số cách giảm thời gian transaction:

- Chọn commit interval vừa phải để transaction không bao trùm quá nhiều công việc.
- Không gọi HTTP, gửi email hoặc chờ message broker trong khi đang giữ lock database.
- Tính toán dữ liệu không cần database trước khi mở transaction ghi nếu kiến trúc cho phép.
- Tạo index phù hợp để câu lệnh cập nhật tìm đúng hàng nhanh hơn.
- Tránh query hoặc update quét quá nhiều dòng trong cùng transaction.
- Không mở transaction bên ngoài bao trùm toàn bộ Job hoặc một flow dài.
- Dùng Tasklet cho thao tác ngắn; chuyển vòng lặp xử lý lượng lớn item sang chunk Step.

Ví dụ, thay vì gọi API cho từng item trong transaction Writer, có thể ghi một sự kiện vào transactional outbox cùng transaction nghiệp vụ rồi gửi ra ngoài sau commit. Cách này tránh giữ lock trong thời gian chờ mạng và vẫn lưu được yêu cầu gửi một cách bền vững.

## 9. Giải pháp 4: giới hạn concurrency phù hợp

Không phải lúc nào nhiều thread hơn cũng làm Job nhanh hơn. Nếu database chỉ xử lý hiệu quả một số transaction đồng thời nhất định, tăng số worker có thể làm lock wait, deadlock, context switching và connection usage tăng.

Có thể điều chỉnh:

- `corePoolSize` và `maxPoolSize` của `TaskExecutor`.
- `gridSize` khi dùng partitioning.
- Số partition được gửi đồng thời.
- Số Job được scheduler cho phép chạy cùng lúc.
- Connection pool size và timeout, trong giới hạn tài nguyên database.

Ví dụ executor có giới hạn rõ ràng:

```java
@Bean
public TaskExecutor batchTaskExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(8);
    executor.setThreadNamePrefix("batch-worker-");
    executor.initialize();
    return executor;
}
```

Giá trị 4 thread chỉ là ví dụ. Cần benchmark dựa trên database, số connection, thời gian transaction và tải ứng dụng online. Không nên đặt pool size bằng một con số lớn tùy ý.

Connection pool cần đủ cho các transaction thực sự chạy đồng thời và các nhu cầu khác của ứng dụng. Tuy nhiên, tăng pool quá lớn có thể làm database chịu nhiều transaction đồng thời hơn mức tối ưu. Hãy quan sát số connection active, pending, acquisition time và transaction duration trước khi điều chỉnh.

## 10. Giải pháp 5: chọn isolation và lock strategy phù hợp

Isolation level ảnh hưởng đến cách transaction nhìn thấy dữ liệu và loại lock hoặc cơ chế kiểm soát đồng thời mà database sử dụng. Isolation cao hơn không tự động loại bỏ deadlock; trong một số database, nó có thể làm tăng lock hoặc tạo thêm tranh chấp.

Các lựa chọn thường gặp:

- `READ_COMMITTED`: thường là mức mặc định ở nhiều database; giảm một số kiểu đọc dữ liệu chưa commit nhưng vẫn có thể gặp deadlock khi cập nhật.
- `REPEATABLE_READ`: giữ tính nhất quán đọc mạnh hơn tùy database; có thể tăng thời gian hoặc phạm vi lock.
- `SERIALIZABLE`: cô lập cao nhất trong các mức chuẩn phổ biến; có thể giảm anomaly nhưng giảm concurrency và có thể phát sinh serialization failure.
- Optimistic locking: dùng cột version để phát hiện cập nhật đồng thời; phù hợp khi xung đột ít và có thể retry nghiệp vụ.
- Pessimistic locking: khóa trước khi cập nhật; phù hợp khi cần ngăn thay đổi đồng thời nhưng có thể tăng lock wait.

Ví dụ optimistic locking với JPA:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Version;

@Entity
public class Account {

    @Id
    private Long id;

    private String status;

    @Version
    private long version;
}
```

Khi hai transaction cùng cập nhật một entity, version giúp phát hiện một transaction đã ghi dựa trên trạng thái cũ. Optimistic locking thường báo lỗi optimistic lock thay vì chờ khóa lâu, nhưng ứng dụng vẫn cần xử lý conflict, reload và retry theo quy tắc nghiệp vụ.

Không thay đổi isolation level chỉ dựa trên suy đoán. Hãy xem deadlock report và tài liệu database để xác định lock nào được tạo ra bởi query, index và isolation hiện tại.

## 11. Giải pháp 6: retry deadlock có kiểm soát

Deadlock đôi khi là lỗi tạm thời do hai transaction tình cờ giao nhau. Database thường rollback một transaction victim; ứng dụng có thể retry transaction đó sau một khoảng chờ ngắn.

Trong Spring Batch, có thể cấu hình retry cho nhóm exception locking phù hợp:

```java
import org.springframework.dao.PessimisticLockingFailureException;

return new StepBuilder("updateStep", jobRepository)
        .<InputRecord, OutputRecord>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .retry(PessimisticLockingFailureException.class)
        .retryLimit(3)
        .build();
```

Ví dụ này cần điều chỉnh theo exception mà database driver và Spring exception translator thực tế phát ra. Một số lỗi có thể được biểu diễn bằng subclass khác của `TransientDataAccessException` hoặc `PessimisticLockingFailureException`. Hãy kiểm tra exception chain trong log trước khi cấu hình.

Retry nên có giới hạn và backoff để các transaction không lập tức va chạm lại cùng lúc. Nếu deadlock xảy ra liên tục vì hai flow luôn khóa tài nguyên theo thứ tự ngược nhau, retry chỉ làm tăng số lần thử; cần sửa thứ tự truy cập hoặc chia dữ liệu.

Writer và các thao tác bên ngoài phải idempotent trước khi bật retry. Nếu transaction bị rollback nhưng một API call đã thành công, retry có thể gửi yêu cầu lần nữa. Dùng idempotency key hoặc outbox cho các side effect đó.

## 12. Chú ý khi các flow dùng chung JobRepository

Các Step và flow trong một Job cùng cập nhật metadata thực thi qua `JobRepository`. Khi chạy song song, nhiều StepExecution có thể ghi metadata gần như đồng thời. Đây là tình huống Spring Batch hỗ trợ, nhưng repository và schema cần được cấu hình đúng, transaction manager phù hợp và database đủ khả năng xử lý.

Một số điểm cần lưu ý:

- Không tự cập nhật trực tiếp các bảng `BATCH_*` để né lock hoặc sửa trạng thái khi Job đang chạy.
- Dùng schema metadata tương ứng với phiên bản Spring Batch.
- Không dùng chung một `ExecutionContext` mutable tự tạo giữa các thread.
- Mỗi Step/partition cần có phạm vi metadata riêng do framework quản lý.
- Nếu JobRepository và bảng nghiệp vụ dùng chung DataSource, tính cả tải metadata khi chọn connection pool và concurrency.
- Không mở transaction ngoài bao trùm toàn bộ Job; transaction metadata và transaction nghiệp vụ cần có boundary rõ ràng.

Nếu deadlock xảy ra trên bảng `BATCH_*`, cần xem deadlock report để xác định câu SQL và transaction nào giữ lock. Không mặc định mọi deadlock trong batch đều do bảng nghiệp vụ.

## 13. Shared file, cache và dịch vụ ngoài

Deadlock thường được nhắc đến trong database, nhưng các flow song song còn có thể tranh chấp tài nguyên khác:

### File dùng chung

Hai flow cùng ghi một file có thể làm dữ liệu xen kẽ, ghi đè hoặc lỗi file lock. Cách xử lý là dùng tên file riêng theo partition/StepExecution, ghi file tạm riêng rồi hợp nhất ở Step cuối, hoặc dùng cơ chế file lock có timeout và giải phóng đúng cách.

### Cache hoặc mutable singleton

Một singleton bean chứa `HashMap`, `ArrayList` hoặc biến trạng thái dùng chung có thể bị race condition khi nhiều flow cập nhật. Đây không nhất thiết là database deadlock nhưng có thể khiến Job treo, dữ liệu sai hoặc phát sinh exception đồng thời. Dùng cấu trúc thread-safe, immutable data hoặc trạng thái bền vững phù hợp.

### Dịch vụ ngoài

Hai flow có thể gọi cùng API và bị giới hạn concurrency hoặc khóa nghiệp vụ ở hệ thống đích. Cần áp dụng rate limit, idempotency key, timeout và retry có backoff. Không giữ transaction database trong lúc chờ một dịch vụ ngoài nếu không cần thiết.

`synchronized` trong Java chỉ điều phối thread trong cùng một JVM. Nếu Job chạy trên nhiều process hoặc nhiều máy, khóa trong bộ nhớ không bảo vệ được resource dùng chung giữa các process. Khi cần distributed coordination, hãy dùng database constraint/lock, distributed lock service hoặc thiết kế phân vùng dữ liệu; đồng thời xác định lease, timeout và hành vi khi worker chết.

## 14. Cách chẩn đoán deadlock

Khi Job bị deadlock, cần tìm transaction, SQL và resource cụ thể thay vì chỉ tăng timeout.

Quy trình điều tra:

1. **Xác định thời điểm:** ghi nhận JobExecution, StepExecution, flow, thread name và thời điểm deadlock.
2. **Lấy deadlock report của database:** xem transaction victim, lock đang giữ, lock đang chờ, bảng/index và câu SQL liên quan.
3. **Đối chiếu Step song song:** xác định Step nào đang chạy cùng thời điểm và chúng có cập nhật cùng khóa hay không.
4. **So sánh thứ tự truy cập:** kiểm tra các transaction có khóa bảng/dòng theo thứ tự khác nhau không.
5. **Kiểm tra thời gian transaction:** tìm query chậm, network call hoặc vòng lặp dài nằm trong transaction.
6. **Kiểm tra pool và executor:** xem connection active/pending, thread đang chạy/chờ và giới hạn concurrency.
7. **Tái hiện có kiểm soát:** chạy cùng dữ liệu với concurrency thấp rồi tăng dần để xác định ngưỡng và pattern.
8. **Áp dụng sửa đổi:** giảm vùng dữ liệu giao nhau, thống nhất lock order, rút ngắn transaction hoặc giới hạn worker; sau đó kiểm tra lại.

Các chỉ số nên quan sát:

| Chỉ số | Điều cần tìm |
|---|---|
| Deadlock count và deadlock victim | Tần suất, câu SQL và transaction bị chọn rollback. |
| Lock wait duration | Step nào giữ lock lâu hoặc phải chờ nhiều. |
| Transaction duration | Transaction có dài hơn dự kiến không. |
| Query duration/plan | Có query quét bảng hoặc thiếu index không. |
| Connection pool active/pending | Worker có chờ connection không. |
| Executor active/queue | Có thread starvation hoặc queue quá lớn không. |
| StepExecution start/end/status | Flow nào chậm, thất bại hoặc được retry. |
| Rollback/retry count | Deadlock có được phục hồi hay lặp liên tục. |

Thread dump giúp xác định thread Java đang chờ connection, lock trong JVM hoặc response từ service ngoài. Tuy nhiên, deadlock database phải được xác nhận bằng thông tin từ database vì thread dump không hiển thị đầy đủ wait-for graph của database.

## 15. Ví dụ thiết kế lại hai flow có xung đột

Giả sử hai flow trước đây cùng cập nhật `customer` và `account` theo thứ tự khác nhau. Có thể sửa theo một trong các hướng:

**Hướng A: gom cập nhật vào một Step tuần tự.** Nếu hai thao tác phải thay đổi cùng một aggregate nghiệp vụ, xử lý chúng trong một Writer/Step có thứ tự nhất quán để tránh hai transaction cạnh tranh cùng lúc.

**Hướng B: chia dữ liệu không giao nhau.** Flow A xử lý nhóm customer ID chẵn, Flow B xử lý nhóm ID lẻ, nếu nghiệp vụ cho phép và các cập nhật liên quan không vượt qua ranh giới nhóm.

**Hướng C: song song phần tính toán, tuần tự hóa phần ghi.** Hai flow tạo kết quả độc lập vào staging table; một Step cuối merge vào bảng chính theo business key và thứ tự khóa thống nhất.

**Hướng D: giới hạn số flow đồng thời.** Nếu database có giới hạn về transaction concurrency, giảm thread pool và chạy thêm Job theo lịch hoặc theo batch nhỏ hơn.

Chọn hướng dựa trên tính độc lập nghiệp vụ. Không nên chia dữ liệu chỉ để tránh deadlock nếu việc đó làm một aggregate bị cập nhật dở dang hoặc phá vỡ quy tắc nhất quán.

## 16. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Tăng số thread để chữa Job chậm | Nhiều transaction cùng tranh chấp, deadlock có thể tăng. | Benchmark concurrency và kiểm tra lock wait. |
| Hai flow cập nhật bảng theo thứ tự khác nhau | Tạo vòng chờ giữa transaction. | Thống nhất thứ tự truy cập resource. |
| Giữ transaction khi gọi HTTP hoặc chờ file | Lock và connection bị giữ lâu. | Tách side effect ra sau commit bằng outbox hoặc Step riêng. |
| Chỉ tăng transaction timeout | Deadlock không biến mất; thời gian chờ có thể dài hơn. | Đọc deadlock report và sửa lock contention. |
| Retry vô hạn | Tạo vòng lặp lỗi và làm database quá tải. | Retry có giới hạn, backoff và idempotency. |
| Dùng `synchronized` để khóa database giữa nhiều máy | Monitor chỉ có hiệu lực trong một JVM. | Dùng database/distributed coordination hoặc phân vùng dữ liệu. |
| Chỉ kiểm tra Reader không chồng lấn | Writer vẫn có thể cập nhật bảng/khóa chung. | Phân tích toàn bộ đường ghi và resource liên quan. |
| Nhầm pool starvation với deadlock | Điều chỉnh sai thành phần. | Kết hợp DB deadlock report, pool metrics và thread dump. |
| Chia partition không cân bằng | Một worker kéo dài, các worker khác chờ kết thúc flow. | Chọn partition key và phạm vi cân bằng hơn. |

## Kết luận

Deadlock trong parallel flow thường xuất hiện khi các Step chạy đồng thời giữ và chờ những lock trên resource dùng chung theo thứ tự không nhất quán. Hãy giảm vùng dữ liệu giao nhau, thống nhất thứ tự truy cập, rút ngắn transaction và giới hạn concurrency theo khả năng database. Retry có giới hạn có thể phục hồi deadlock tạm thời, nhưng Writer và side effect phải idempotent để tránh dữ liệu trùng. Khi điều tra, cần đối chiếu deadlock report của database với JobExecution, StepExecution, thread, connection pool và thời gian transaction để tìm đúng nguyên nhân trước khi thay đổi cấu hình.
