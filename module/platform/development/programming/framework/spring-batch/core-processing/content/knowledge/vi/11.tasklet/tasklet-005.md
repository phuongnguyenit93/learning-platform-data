# Tasklet transaction boundary

Trong Spring Batch, `Tasklet` là cách xây dựng một step thực hiện một đơn vị công việc do ứng dụng định nghĩa, chẳng hạn dọn dữ liệu cũ, gọi một thủ tục lưu trữ, tạo file tổng hợp hoặc thực hiện một thao tác quản trị. Khi chạy trong `TaskletStep`, phương thức `Tasklet.execute(...)` được thực thi bên trong transaction do step quản lý.

Điểm quan trọng là transaction boundary của tasklet gắn với **mỗi lần gọi `execute`**. Nếu tasklet trả về `RepeatStatus.FINISHED`, step kết thúc sau lần gọi đó. Nếu tasklet trả về `RepeatStatus.CONTINUABLE`, Spring Batch gọi lại tasklet để thực hiện vòng tiếp theo; mỗi lần gọi tiếp theo có transaction riêng. Vì vậy, một tasklet có thể chạy trong một transaction duy nhất hoặc chia công việc thành nhiều transaction ngắn tùy cách nó sử dụng `RepeatStatus`.

Transaction boundary quyết định thao tác nào được commit hoặc rollback cùng nhau, metadata nào được lưu cùng checkpoint và khi restart tasklet có thể tiếp tục từ đâu. Hiểu đúng ranh giới này giúp tránh giữ transaction quá lâu, tránh ghi dữ liệu dở dang và thiết kế tasklet có thể phục hồi sau lỗi.

## Tasklet và TaskletStep

`Tasklet` là interface đơn giản với một phương thức:

```java
public interface Tasklet {
    RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) throws Exception;
}
```

Tasklet trả về một trong các trạng thái lặp thường dùng:

| Kết quả | Ý nghĩa |
| --- | --- |
| `RepeatStatus.FINISHED` | Công việc của tasklet đã hoàn tất; step có thể kết thúc thành công |
| `RepeatStatus.CONTINUABLE` | Còn công việc; framework tiếp tục gọi `execute` ở vòng kế tiếp |

`TaskletStep` là loại step thực thi tasklet. Nó điều phối transaction, gọi tasklet, cập nhật `StepExecution` và `ExecutionContext`, rồi lặp lại nếu tasklet trả về `CONTINUABLE`.

Luồng khái quát:

```text
TaskletStep bắt đầu
       |
       v
Mở transaction cho một lần execute
       |
       v
Tasklet.execute(...)
       |
       +----> thay đổi dữ liệu nghiệp vụ
       |
       +----> cập nhật ExecutionContext
       |
       v
Cập nhật StepExecution / metadata
       |
       v
COMMIT hoặc ROLLBACK
       |
       v
RepeatStatus?
   /        \
FINISHED   CONTINUABLE
   |           |
   v           +----> mở transaction mới và gọi execute lần nữa
Kết thúc step
```

Sơ đồ thể hiện ranh giới ở mức khái niệm. Spring Batch quản lý việc gọi tasklet và lưu metadata trong lifecycle của step; ứng dụng không cần tự mở transaction thủ công quanh từng lần `execute` trong trường hợp thông thường.

## Transaction được mở ở đâu?

Khi `TaskletStep` thực thi một lần lặp, nó dùng `PlatformTransactionManager` được cấu hình cho step để bắt đầu transaction. Bên trong transaction đó, framework gọi `Tasklet.execute(...)`. Sau khi tasklet trả về bình thường, Spring Batch áp dụng phần đóng góp của step, cập nhật execution context và lưu các thay đổi metadata của `StepExecution` theo lifecycle của step. Sau đó transaction được commit.

Nếu tasklet ném exception hoặc một thao tác cập nhật metadata thất bại, transaction có thể rollback theo transaction attribute của step. `TaskletStep` mặc định được thiết kế để rollback khi tasklet ném exception; nếu ứng dụng tùy chỉnh transaction attributes, cần hiểu rõ rollback rule mới.

Với JDBC hoặc JPA, các thao tác nghiệp vụ tham gia cùng transaction khi chúng sử dụng đúng resource và transaction manager. Ví dụ, tasklet gọi `JdbcTemplate` dùng cùng `DataSource` với transaction manager của step thì câu SQL thường tham gia transaction đang hoạt động. Nếu tasklet gọi một dịch vụ dùng transaction manager khác hoặc ghi ra hệ thống ngoài database, thao tác đó không tự động nằm trong transaction hiện tại.

## Cấu hình transaction manager cho TaskletStep

Trong Spring Batch 5, transaction manager được truyền trực tiếp khi khai báo tasklet step bằng `StepBuilder`:

```java
@Bean
Step archiveOldOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ArchiveOldOrdersTasklet tasklet) {

    return new StepBuilder("archiveOldOrdersStep", jobRepository)
            .tasklet(tasklet, transactionManager)
            .build();
}
```

`transactionManager` quản lý transaction của từng lần gọi `execute`. Với các phiên bản Spring Batch cũ hơn, cách khai báo builder có thể khác; hãy dùng API tương ứng với phiên bản của dự án. Không nên bỏ qua transaction manager hoặc tự tạo một manager không quản lý datasource mà tasklet đang sử dụng.

Ví dụ tasklet cập nhật dữ liệu database:

```java
public class ArchiveOldOrdersTasklet implements Tasklet {

    private final JdbcTemplate jdbcTemplate;

    public ArchiveOldOrdersTasklet(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {

        jdbcTemplate.update("""
                UPDATE orders
                SET status = 'ARCHIVED'
                WHERE status = 'COMPLETED'
                  AND completed_at < CURRENT_DATE - INTERVAL '90 days'
                """);

        return RepeatStatus.FINISHED;
    }
}
```

Đây là ví dụ SQL theo PostgreSQL. Tasklet thực hiện câu lệnh update rồi trả về `FINISHED`; nếu update và repository metadata cùng tham gia transaction của step, các thay đổi liên quan có thể commit hoặc rollback cùng nhau. Với database khác, cú pháp tính ngày có thể cần điều chỉnh.

## Một lần execute tương ứng một transaction

Với tasklet trả `FINISHED` ngay sau một thao tác, toàn bộ phần việc trong lần gọi `execute` nằm trong một transaction của step. Điều này phù hợp với công việc nhỏ, thời gian ngắn và có thể thực hiện như một đơn vị nguyên tử.

```java
@Override
public RepeatStatus execute(
        StepContribution contribution,
        ChunkContext chunkContext) {

    jdbcTemplate.update("DELETE FROM temporary_records WHERE created_at < ?", cutoff);
    jdbcTemplate.update("INSERT INTO cleanup_audit(job_date, deleted_at) VALUES (?, CURRENT_TIMESTAMP)",
            businessDate);

    return RepeatStatus.FINISHED;
}
```

Nếu cả hai câu lệnh cùng sử dụng datasource và transaction manager của step, chúng thuộc cùng transaction. Nếu câu lệnh thứ hai thất bại và lỗi kích hoạt rollback, câu lệnh delete đầu tiên cũng được rollback. Đây là lợi ích khi nhóm các thao tác database cần nhất quán vào cùng một tasklet invocation.

Tuy nhiên, transaction sẽ tồn tại trong toàn bộ thời gian `execute` đang chạy. Nếu tasklet xử lý hàng triệu bản ghi, gọi API chậm hoặc chờ một hệ thống bên ngoài, transaction có thể giữ connection và lock quá lâu. Trong trường hợp đó, nên chia công việc thành các đơn vị nhỏ và trả về `CONTINUABLE` sau mỗi đơn vị đã hoàn tất.

## RepeatStatus.CONTINUABLE tạo nhiều transaction ngắn

Tasklet có thể xử lý một phần công việc trong mỗi lần gọi `execute` rồi trả `RepeatStatus.CONTINUABLE`. `TaskletStep` kết thúc transaction của lần gọi hiện tại trước khi thực hiện vòng tiếp theo. Như vậy, mỗi page, file segment hoặc nhóm bản ghi có thể được commit riêng.

Ví dụ, một tasklet xử lý dữ liệu theo từng page:

```java
public class ProcessOrdersByPageTasklet implements Tasklet {

    private final OrderPageReader reader;
    private final OrderPageWriter writer;

    public ProcessOrdersByPageTasklet(
            OrderPageReader reader,
            OrderPageWriter writer) {
        this.reader = reader;
        this.writer = writer;
    }

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {

        ExecutionContext context =
                contribution.getStepExecution().getExecutionContext();
        int page = context.getInt("nextPage", 0);

        List<Order> orders = reader.readPage(page);
        if (orders.isEmpty()) {
            return RepeatStatus.FINISHED;
        }

        writer.writePage(orders);
        context.putInt("nextPage", page + 1);

        return RepeatStatus.CONTINUABLE;
    }
}
```

Trong ví dụ, `reader` và `writer` là các thành phần ứng dụng minh họa việc đọc/ghi một page. Khi mỗi lần gọi `execute` hoàn tất:

1. Tasklet đọc page tiếp theo dựa trên `nextPage`.
2. Tasklet ghi page đó.
3. Tasklet cập nhật `nextPage` trong `ExecutionContext`.
4. Tasklet trả về `CONTINUABLE`.
5. Spring Batch cập nhật context và metadata step rồi commit transaction.
6. Vòng tiếp theo bắt đầu với transaction mới.

Nếu `writer.writePage` và `ExecutionContext` được lưu trong cùng transaction resource, dữ liệu của page và checkpoint `nextPage` có thể cùng commit. Nếu lỗi xảy ra trước commit, cả hai thay đổi rollback; lần gọi sau sẽ đọc lại page chưa commit. Khi không còn dữ liệu, tasklet trả `FINISHED` để step kết thúc.

Đây là cách chia công việc thành nhiều transaction ngắn, nhưng tasklet vẫn là một tasklet step. Nếu nghiệp vụ cần xử lý từng item với skip/retry, thống kê read/write và chunk semantics phong phú, chunk-oriented step thường phù hợp hơn.

## So sánh transaction boundary của Tasklet và chunk step

Tasklet step và chunk-oriented step đều sử dụng transaction, nhưng đơn vị công việc nằm trong transaction khác nhau.

| Khía cạnh | TaskletStep | Chunk-oriented step |
| --- | --- | --- |
| Đơn vị thực thi | Một lần gọi `Tasklet.execute` | Một chunk item |
| Ranh giới transaction | Thông thường một transaction cho mỗi lần gọi execute | Một transaction cho mỗi chunk |
| Lặp xử lý | Tasklet trả `CONTINUABLE` để yêu cầu vòng tiếp theo | Framework lặp reader/process/writer theo commit interval |
| Reader/processor/writer | Tasklet tự tổ chức logic nếu cần | Framework điều phối ba thành phần |
| Checkpoint | Tasklet thường tự quản lý state trong `ExecutionContext` | Reader/writer có thể tích hợp `ItemStream` để lưu state |
| Phù hợp | Một thao tác nghiệp vụ hoặc một đơn vị công việc tự định nghĩa | Xử lý tập item với commit, skip, retry và thống kê theo chunk |

Một tasklet thực hiện vòng lặp lớn bên trong một lần `execute` vẫn chỉ có một transaction cho toàn bộ invocation đó. Việc viết `for` hoặc `while` trong tasklet không tự tạo transaction mới cho từng vòng lặp. Muốn có transaction riêng cho từng đơn vị, có thể trả `CONTINUABLE` sau mỗi đơn vị hoặc dùng chunk-oriented step.

## Transaction và ExecutionContext

`ExecutionContext` lưu trạng thái cần thiết để khôi phục job hoặc step. Với tasklet xử lý nhiều lần lặp, đây là nơi phù hợp để lưu checkpoint như page tiếp theo, ID cuối đã xử lý, tên file hoặc trạng thái công việc.

Ví dụ lấy và cập nhật context:

```java
ExecutionContext context =
        contribution.getStepExecution().getExecutionContext();

long lastProcessedId = context.getLong("lastProcessedId", 0L);

// Xử lý một phần dữ liệu bắt đầu sau lastProcessedId.

context.putLong("lastProcessedId", newLastProcessedId);
```

Trong `TaskletStep`, Spring Batch cập nhật execution context và metadata step trong lifecycle của transaction. Nếu context và dữ liệu nghiệp vụ tham gia cùng transaction manager/resource, checkpoint có thể được commit cùng dữ liệu đã xử lý.

Không nên chỉ lưu checkpoint trong field của object tasklet. Bean tasklet có thể được dùng lại giữa các lần chạy hoặc bởi nhiều execution tùy scope và cấu hình ứng dụng. State trong field không được repository lưu bền vững và có thể bị mất khi tiến trình dừng. Dùng `ExecutionContext` cho trạng thái cần restart; giữ tasklet stateless khi có thể.

### Điều gì xảy ra khi restart?

Giả sử tasklet xử lý 10 page, mỗi invocation xử lý một page và commit checkpoint sau từng page. Nếu tiến trình dừng sau page 6 đã commit, lần restart có thể đọc `nextPage=6` và tiếp tục từ page 6 theo quy ước index của ví dụ. Các page đã commit không cần chạy lại.

Nếu tiến trình dừng trước khi transaction page 6 commit, cả dữ liệu page 6 và checkpoint tương ứng sẽ rollback khi chúng cùng resource; lần restart sẽ xử lý lại page 6. Vì vậy, checkpoint phải được cập nhật trong cùng transaction với phần dữ liệu mà nó đại diện.

Nếu writer ghi ra hệ thống ngoài transaction, checkpoint và output có thể không đồng bộ. Ví dụ file hoặc message đã được ghi nhưng database transaction rollback. Khi restart, tasklet có thể lặp lại output. Cần thiết kế file append/restart, message event ID hoặc thao tác idempotent để tránh kết quả trùng.

## Transaction manager và nhiều resource

Một transaction manager thường quản lý một loại transaction resource cụ thể, chẳng hạn JDBC datasource hoặc JPA entity manager factory. Các thao tác trong tasklet chỉ tự động tham gia transaction hiện tại khi chúng dùng đúng resource và transaction manager được cấu hình.

### Cùng database và cùng transaction manager

Nếu tasklet cập nhật bảng nghiệp vụ bằng `JdbcTemplate` dùng cùng `DataSource` với transaction manager của step, câu lệnh SQL tham gia transaction hiện tại. Các cập nhật metadata của step cũng có thể tham gia cùng transaction nếu `JobRepository` được cấu hình trên cùng resource và transaction manager phù hợp.

```text
TaskletStep transaction
          |
          +---- UPDATE business_table
          |
          +---- INSERT audit_table
          |
          +---- Update StepExecution / ExecutionContext
          |
          +---- COMMIT hoặc ROLLBACK
```

Đây là cấu hình dễ hiểu nhất khi yêu cầu dữ liệu nghiệp vụ và checkpoint cần nhất quán. Tuy nhiên, phải xác nhận các thao tác thực sự dùng cùng transaction resource; cùng một database server hoặc cùng URL JDBC nhưng mở các connection độc lập không tự động có nghĩa là cùng một transaction.

### Hai datasource hoặc hai transaction manager

Nếu metadata và dữ liệu nghiệp vụ ở hai database, mỗi transaction manager có thể commit độc lập. Transaction của tasklet không tự động bảo đảm atomic commit qua hai resource.

Ví dụ:

```text
Transaction business DB       Transaction metadata DB
         |                              |
         v                              v
   Ghi dữ liệu nghiệp vụ          Ghi checkpoint
         |                              |
      COMMIT                          ROLLBACK
         |                              |
         +---------- restart -----------+
                    |
                    v
            Dữ liệu có thể bị ghi lại
```

Nếu dữ liệu nghiệp vụ commit nhưng checkpoint rollback, tasklet có thể thực hiện lại phần việc đã ghi. Nếu checkpoint commit trước dữ liệu nghiệp vụ, tasklet có thể bỏ qua phần việc chưa được lưu. Khi tách resource, cần có một chiến lược phục hồi:

- Thiết kế thao tác ghi idempotent theo business key.
- Ghi nhận trạng thái xử lý tại hệ thống nghiệp vụ để đối soát.
- Dùng outbox khi tasklet cần phát message dựa trên thay đổi database.
- Xác định cách khôi phục khi một resource commit còn resource khác thất bại.
- Cân nhắc distributed transaction/XA chỉ khi yêu cầu atomicity qua nhiều resource thực sự cần thiết và hạ tầng hỗ trợ.

## @Transactional bên trong Tasklet

Tasklet thường gọi các service nghiệp vụ có gắn `@Transactional`. Cần hiểu propagation để biết service tham gia transaction của step hay mở transaction độc lập.

Với `Propagation.REQUIRED`, service tham gia transaction đang hoạt động nếu có. Đây thường là lựa chọn phù hợp khi service cập nhật dữ liệu cần commit cùng tasklet invocation.

```java
@Service
public class OrderArchiveService {

    @Transactional
    public int archive(LocalDate cutoffDate) {
        // Các câu lệnh JDBC/JPA tham gia transaction hiện tại
        // nếu cùng transaction manager và resource.
        return 0;
    }
}
```

Với `Propagation.REQUIRES_NEW`, service tạm treo transaction hiện tại và mở transaction độc lập. Nếu service commit thành công rồi tasklet thất bại, thay đổi trong transaction mới vẫn có thể tồn tại. Điều này có thể phá vỡ giả định rằng mọi thay đổi trong một lần tasklet invocation sẽ rollback cùng nhau.

`Propagation.NESTED` dựa trên savepoint và khả năng hỗ trợ của transaction manager/database. Không phải resource nào cũng hỗ trợ giống nhau.

Ngoài ra, `@Transactional` dựa trên cơ chế proxy của Spring. Gọi một method transactional khác trong cùng instance bằng self-invocation có thể không đi qua proxy và annotation có thể không được áp dụng như mong đợi. Hãy đặt transaction boundary ở bean/service được gọi qua proxy và xác nhận đúng transaction manager được chọn khi ứng dụng có nhiều datasource.

Thông thường, không cần bọc thêm `@Transactional` quanh toàn bộ `Tasklet.execute` vì `TaskletStep` đã quản lý transaction. Hãy dùng transaction ở service con khi có lý do rõ ràng về propagation hoặc ranh giới nghiệp vụ.

## Rollback khi tasklet gặp lỗi

Khi một thao tác trong tasklet thất bại, kết quả phụ thuộc loại exception, transaction attribute và resource tham gia transaction.

Trong `TaskletStep`, transaction attribute mặc định được thiết kế để rollback khi tasklet ném exception. Nếu ứng dụng cấu hình transaction attribute tùy chỉnh, cần xác định rõ exception nào kích hoạt rollback. Với database resource tham gia transaction, các thay đổi chưa commit sẽ rollback.

Ví dụ tasklet thực hiện hai thao tác:

```java
@Override
public RepeatStatus execute(
        StepContribution contribution,
        ChunkContext chunkContext) {

    jdbcTemplate.update(
            "UPDATE account SET status = 'CLOSED' WHERE account_id = ?",
            accountId);

    jdbcTemplate.update(
            "INSERT INTO account_audit(account_id, action) VALUES (?, ?)",
            accountId,
            "CLOSED");

    return RepeatStatus.FINISHED;
}
```

Nếu câu insert audit ném exception và cả hai thao tác tham gia cùng transaction, câu update account cũng được rollback. Nếu tasklet đã gửi email hoặc gọi HTTP trước khi lỗi xảy ra, thao tác bên ngoài đó không tự động bị thu hồi.

### Checked exception và rollback rule

Tasklet có thể khai báo `throws Exception`. Khi cần thay đổi rollback rule, cấu hình transaction attribute của step theo API phiên bản Spring Batch đang dùng. Không nên giả định mọi exception trong mọi service đều có cùng rollback behavior: annotation `@Transactional` ở service và transaction attribute của `TaskletStep` là hai lớp cấu hình có thể tương tác.

Nếu một service dùng `@Transactional` với rollback rule riêng, ví dụ `noRollbackFor`, service có thể không đánh dấu transaction rollback-only cho một exception nhất định. Tuy nhiên, `TaskletStep` vẫn có transaction attribute riêng khi quyết định xử lý exception từ `execute`. Hãy kiểm tra cả hai lớp khi có hành vi commit/rollback bất ngờ.

## Transaction timeout và isolation level

Transaction của tasklet có thể được cấu hình với timeout và isolation phù hợp với công việc. Tasklet chạy lâu trong một invocation sẽ giữ transaction lâu tương ứng, vì vậy timeout cần phản ánh thời gian thực tế nhưng không nên đặt quá lớn để che giấu một thao tác bị treo.

Các yếu tố thường cần xem xét:

| Thuộc tính | Ý nghĩa | Khi cần quan tâm |
| --- | --- | --- |
| Propagation | Tham gia transaction hiện tại hay tạo transaction mới | Tasklet gọi service có `@Transactional` |
| Isolation | Mức cô lập đọc/ghi của transaction | Tasklet đọc và cập nhật dữ liệu có cạnh tranh |
| Timeout | Thời gian tối đa cho transaction | Tasklet có thao tác database lâu hoặc chờ lock |
| Read-only | Gợi ý transaction chỉ đọc nếu manager hỗ trợ | Tasklet chỉ truy vấn và không thay đổi dữ liệu |
| Rollback rule | Exception nào làm transaction rollback | Tasklet có checked exception hoặc quy tắc nghiệp vụ riêng |

TaskletStep hỗ trợ cấu hình transaction attribute. Cách gắn `TransactionAttribute` vào step builder có thể khác giữa các phiên bản. Khi thay đổi isolation hoặc timeout, cần xem xét tải database, lock, query plan và thời gian thực thi; không nên nâng isolation lên mức cao nhất nếu không có yêu cầu nhất quán tương ứng.

## Gọi API, ghi file hoặc gửi message trong tasklet

Không phải mọi thao tác bên trong `execute` đều được database transaction bảo vệ.

### Gọi HTTP API

Nếu tasklet gọi một API bên ngoài để tạo tài nguyên hoặc cập nhật trạng thái, database rollback không thể tự hoàn tác request đã được API xử lý. Nếu tasklet thất bại sau khi API thành công, restart có thể gửi lại request. Dùng idempotency key hoặc API hỗ trợ truy vấn trạng thái để tránh tạo tác động lặp.

### Ghi file

Ghi file không mặc nhiên tham gia JDBC transaction. Nếu tasklet ghi một phần file rồi lỗi, database rollback không xóa các byte đã ghi. Hãy ghi file tạm theo định danh execution, lưu checkpoint khi cần tiếp tục, rồi chỉ công bố file sau khi step hoàn tất thành công. Nếu cần append khi restart, phải xác định vị trí và cách khôi phục chính xác.

### Gửi message

Message broker có transaction riêng và không tự động tham gia transaction database của tasklet. Message đã được broker nhận có thể vẫn tồn tại khi transaction database rollback. Có thể dùng transactional outbox để ghi sự kiện cùng transaction nghiệp vụ rồi publisher riêng gửi message; consumer nên xử lý idempotent theo event ID.

## Thiết kế tasklet dài: chia đơn vị commit

Một tasklet thực hiện toàn bộ công việc trong một lần `execute` có thể giữ transaction quá lâu. Nếu có thể chia công việc thành các đơn vị độc lập, hãy xử lý một đơn vị mỗi lần gọi và trả `CONTINUABLE`.

Ví dụ các kiểu chia:

- Một page database mỗi lần gọi.
- Một file hoặc một phần file mỗi lần gọi.
- Một nhóm khách hàng hoặc một khoảng ID mỗi lần gọi.
- Một partition hoặc một batch con theo khóa nghiệp vụ.

Mỗi đơn vị nên có checkpoint tương ứng. Chỉ cập nhật checkpoint sau khi các thay đổi của đơn vị đã được thực hiện thành công trong transaction. Khi tasklet trả `CONTINUABLE`, framework commit transaction hiện tại rồi bắt đầu transaction cho đơn vị tiếp theo.

Không nên tự viết vòng lặp hàng triệu item trong một `execute` nếu yêu cầu là commit định kỳ. Trong trường hợp đó, chunk-oriented step với `ItemReader`, `ItemProcessor` và `ItemWriter` thường cung cấp mô hình tự nhiên hơn, bao gồm commit interval, skip/retry và thống kê theo item.

## Listener và transaction boundary

Tasklet step có thể dùng `StepExecutionListener`, `ChunkListener` hoặc listener phù hợp khác tùy nhu cầu. Cần phân biệt callback của listener với phần công việc nằm trong transaction của tasklet. Không nên giả định mọi callback đều chạy trong cùng transaction với `execute`.

Nếu listener ghi dữ liệu cần commit nguyên tử với tasklet, hãy xác định lifecycle và transaction manager thực tế của callback đó. Với thao tác nghiệp vụ quan trọng, thường dễ kiểm soát hơn nếu thực hiện trong tasklet/service tham gia transaction của step thay vì dựa vào side effect trong listener ở một thời điểm không rõ ràng.

Listener phù hợp để ghi log, đo thời gian, bổ sung metadata hoặc điều phối tác vụ trước/sau step. Nếu listener gửi thông báo ra ngoài, cần lưu ý message hoặc email không rollback cùng transaction database.

## Những lỗi thường gặp

### Nghĩ rằng cả vòng đời step chỉ có một transaction

`TaskletStep` tạo transaction cho từng lần gọi `execute`. Nếu tasklet trả `CONTINUABLE`, vòng tiếp theo có transaction mới. Các thao tác trước đó đã commit không tự rollback khi vòng sau thất bại.

### Dùng vòng lặp lớn trong một lần execute

Một vòng lặp dài bên trong `execute` vẫn giữ một transaction cho toàn bộ invocation. Điều này có thể giữ lock và connection lâu, làm tăng phạm vi rollback. Chia thành nhiều invocation với checkpoint hoặc chuyển sang chunk step.

### Cập nhật checkpoint trước dữ liệu

Nếu checkpoint commit trước khi dữ liệu nghiệp vụ được ghi, restart có thể bỏ qua dữ liệu chưa hoàn tất. Hãy cập nhật context trong cùng transaction với thay đổi mà checkpoint đại diện khi có thể.

### Lưu tiến trình trong field của tasklet

Field trong object không phải metadata bền vững. Khi process dừng hoặc bean được dùng lại, state có thể mất hoặc lẫn giữa execution. Lưu checkpoint vào `ExecutionContext`.

### Gọi service dùng REQUIRES_NEW không chủ ý

Service có thể commit độc lập với transaction tasklet. Khi tasklet rollback, dữ liệu service đã commit vẫn tồn tại. Kiểm tra propagation và transaction manager của service.

### Giả định file hoặc message rollback cùng database

File và message broker thường là resource độc lập. Dùng file tạm, outbox, event ID và idempotency để phục hồi khi các resource không commit cùng nhau.

### Nuốt exception rồi trả FINISHED

Nếu tasklet bắt exception, chỉ ghi log rồi trả `FINISHED`, framework có thể xem invocation hoàn thành bình thường và commit những thay đổi còn lại. Chỉ xử lý exception khi có chính sách phục hồi rõ ràng; nếu tasklet không thể hoàn thành đúng, hãy ném exception để step xử lý lỗi.

## Kiểm thử transaction boundary của Tasklet

Nên kiểm thử cả trường hợp thành công, rollback, nhiều lần lặp và restart.

### Kiểm thử commit thành công

Chạy tasklet với database test và xác nhận thay đổi nghiệp vụ cùng metadata step được ghi sau khi step hoàn tất. Kiểm tra `BatchStatus.COMPLETED` và kết quả dữ liệu.

### Kiểm thử rollback

Cho tasklet thực hiện một cập nhật database rồi ném exception. Xác nhận cập nhật chưa commit được rollback khi dùng cùng transaction resource. Kiểm tra step ở trạng thái thất bại và metadata phản ánh lỗi.

### Kiểm thử CONTINUABLE

Tạo tasklet xử lý một đơn vị mỗi lần gọi, tăng checkpoint trong `ExecutionContext` và trả `CONTINUABLE` cho tới khi hết dữ liệu. Xác nhận mỗi đơn vị được commit riêng và lần gọi sau đọc được checkpoint đã lưu.

### Kiểm thử restart

Mô phỏng lỗi sau một số invocation đã commit. Restart cùng `JobInstance` với identifying parameters cũ và xác nhận tasklet tiếp tục từ checkpoint đã lưu, không xử lý lại các đơn vị đã commit nếu thiết kế yêu cầu điều đó.

### Kiểm thử side effect ngoài transaction

Giả lập API hoặc publisher đã nhận request rồi tasklet ném exception. Xác nhận database rollback không tự thu hồi side effect và kiểm tra idempotency key hoặc outbox xử lý lần chạy lại.

## Nguyên tắc lựa chọn transaction boundary

Khi thiết kế tasklet, hãy trả lời những câu hỏi sau:

1. Một lần `execute` thực hiện bao nhiêu công việc và mất bao lâu?
2. Những thao tác nào cần commit hoặc rollback cùng nhau?
3. Tasklet có trả `CONTINUABLE` để chia thành nhiều transaction không?
4. Checkpoint nào cần lưu trong `ExecutionContext` để restart?
5. Dữ liệu nghiệp vụ và metadata có dùng cùng transaction resource không?
6. Tasklet có gọi API, ghi file hoặc gửi message ngoài transaction không?
7. Service được gọi có propagation `REQUIRED`, `REQUIRES_NEW` hay transaction manager khác?
8. Timeout, isolation và rollback rule có phù hợp với công việc không?
9. Có thể chuyển sang chunk-oriented step nếu cần xử lý nhiều item, skip/retry và commit theo lô không?

Với thao tác ngắn và cần tính nguyên tử, một lần `execute` trả `FINISHED` thường là đủ. Với công việc dài, hãy chia thành các đơn vị nhỏ, lưu checkpoint trong `ExecutionContext` và trả `CONTINUABLE` để mỗi đơn vị có transaction riêng. Khi tasklet làm việc với nhiều resource, phải thiết kế khả năng phục hồi và idempotency vì transaction database không tự bao phủ file, API hoặc message broker.

## Ghi nhớ

`TaskletStep` quản lý transaction cho mỗi lần gọi `Tasklet.execute`. Tasklet trả `FINISHED` để kết thúc step; trả `CONTINUABLE` để yêu cầu lần gọi tiếp theo trong transaction mới. Các thay đổi database và metadata chỉ commit/rollback cùng nhau khi chúng tham gia cùng transaction resource và transaction manager phù hợp. Dùng `ExecutionContext` để lưu checkpoint bền vững, tránh giữ state trong field hoặc giữ transaction quá lâu. Với file, API và message broker, cần cơ chế idempotency, outbox hoặc phục hồi riêng vì side effect ngoài database không tự động rollback cùng tasklet transaction.
