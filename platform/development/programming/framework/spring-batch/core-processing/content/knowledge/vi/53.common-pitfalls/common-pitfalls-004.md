# Reader không restartable nhưng job cần restart trong Spring Batch

Một Spring Batch job đọc hàng triệu bản ghi, ghi được vài chunk rồi thất bại vì database hoặc dịch vụ đích không sẵn sàng. Người vận hành khởi chạy lại **cùng công việc**, nhưng reader quay về bản ghi đầu tiên, đọc lặp dữ liệu đã ghi hoặc không tìm được vị trí đã dừng. Đôi khi job không báo lỗi rõ ràng về reader; nó chỉ gặp duplicate key, tạo kết quả trùng, hoặc xử lý lại rất lâu. Nguyên nhân có thể là **`ItemReader` không lưu trạng thái để restart**, dù chính job được thiết kế cho phép restart.

Đây là một lỗi phổ biến trong **Spring Batch Core Processing → Lỗi thường gặp**. Muốn xử lý đúng, cần hiểu sự khác nhau giữa *khả năng restart của job* và *khả năng khôi phục điểm đọc của reader*. Tài liệu này giải thích cơ chế `ItemStream`/`ExecutionContext`, nhận diện cấu hình sai, cách viết reader có checkpoint, cách phục hồi nguồn không hỗ trợ replay và chiến lược kiểm thử để ngăn đọc lặp hoặc bỏ sót item.

Ví dụ Java tập trung vào **Spring Batch 5.2.x và Java 17**. Một số package/API được tổ chức lại ở Spring Batch 6.x; nguyên lý checkpoint và consistency vẫn áp dụng.

## 1. Job restartable không đồng nghĩa reader restartable

Spring Batch phân biệt các khái niệm sau:

| Thành phần | Trách nhiệm | Câu hỏi khi restart |
| --- | --- | --- |
| `JobInstance` | Công việc logic xác định bởi tên job và các identifying `JobParameters` | Đây có phải cùng công việc cần hoàn tất không? |
| `JobExecution` | Một lần thử thực thi `JobInstance` | Lần trước đã `FAILED`, `STOPPED` hay `COMPLETED`? |
| `StepExecution` | Trạng thái và kết quả thực thi một step | Step nào cần chạy lại, step nào đã hoàn tất? |
| `JobRepository` | Lưu metadata, status, counter và execution context | Điểm khôi phục nào thực sự đã commit? |
| `ItemReader` | Cung cấp item tiếp theo qua `read()` | Sau khi tạo lại, reader bắt đầu ở đâu? |
| `ItemStream` | Mở, cập nhật và đóng tài nguyên, lưu/trả trạng thái | Reader có thể phục hồi vị trí sau commit gần nhất không? |
| `ItemWriter` | Ghi kết quả | Nếu một item được giao lại, có ghi trùng tác động nghiệp vụ không? |

Một job có thể cho phép restart theo cấu hình và metadata, nhưng Spring Batch **không thể tự đoán offset** của reader chỉ triển khai `ItemReader<T>`. Giao diện này chỉ có thao tác `read()`; nó không định nghĩa cách lưu vị trí sang lần thực thi khác.

Ví dụ:
 
```text
Job: importOrders
  |
  +-- JobInstance A (businessDate=2026-11-15)
        |
        +-- JobExecution 101: FAILED
        |     +-- StepExecution 201: FAILED
        |           +-- checkpoint reader: đã commit tới item 200
        |
        +-- JobExecution 102: restart
              +-- StepExecution 202: phải tiếp tục từ item 201
```

Nếu reader ở lần chạy thứ hai khởi tạo lại một `Iterator` mới và đọc từ đầu, nó sẽ gặp item 1 thay vì item 201. Lúc đó có thể có hai dạng lỗi: **duplicate** vì các item 1–200 đã ghi, hoặc **ghi đè sai** nếu writer không có khóa/idempotency thích hợp.

Ngoài ra, khi một step đã `COMPLETED` ở lần trước, Spring Batch thường **không chạy lại step ấy** khi restart cùng `JobInstance`, trừ khi được cấu hình cho phép chạy lại. Lỗi reader không restartable chủ yếu lộ ra ở step chưa hoàn tất và phải tiếp tục.

## 2. Checkpoint của reader được lưu như thế nào?

Giao diện `ItemStream` định nghĩa ba phương thức lifecycle:

```java
public interface ItemStream {
    void open(ExecutionContext executionContext);
    void update(ExecutionContext executionContext);
    void close();
}
```

Trong Spring Batch 5.2, giao diện kết hợp là `org.springframework.batch.item.ItemStreamReader<T>`, tức một reader vừa có `read()` vừa hỗ trợ `open`, `update` và `close`.

| Phương thức | Vai trò | Thời điểm |
| --- | --- | --- |
| `open(context)` | Mở tài nguyên và phục hồi từ checkpoint được truyền vào | Trước khi đọc item |
| `read()` | Trả item tiếp theo hoặc `null` khi hết nguồn | Mỗi lần framework yêu cầu item |
| `update(context)` | Đưa vị trí/trạng thái cần checkpoint vào `ExecutionContext` | Trước khi context được lưu ở ranh giới commit |
| `close()` | Giải phóng file handle, cursor, connection hoặc tài nguyên khác | Khi step kết thúc/đóng stream |

`ExecutionContext` là một cấu trúc key-value mà Spring Batch có thể lưu trong `JobRepository`. Thông thường state phục hồi **vị trí reader** thuộc `StepExecutionContext`, không phải `JobExecutionContext`; các reader cùng step cần dùng **key riêng** để tránh ghi đè lẫn nhau.

Chu trình đơn giản:

```text
        Step bắt đầu / restart
                |
                v
      ItemStream.open(stepContext)
                |
         đọc và xử lý chunk
                |
                v
      ItemStream.update(stepContext)
                |
                v
     JobRepository lưu checkpoint
                |
          COMMIT transaction
                |
        +-------+---------+
        |                 |
     Tiếp tục          Sau này FAILED
        |                 |
        v                 v
      chunk mới      Tạo JobExecution mới
                              |
                              v
                    open(context đã commit)
                              |
                              v
                    Đọc từ điểm khôi phục
```

**Không phải cứ `read()` một item là checkpoint đã được ghi vào database.** Với chunk size 100, reader có thể đi qua 85 item trong chunk mới nhưng process chết trước commit; lần restart thường quay về checkpoint của chunk đã commit trước đó và xử lý lại 85 item này. Đó là hành vi mong đợi khi dữ liệu nghiệp vụ cũng rollback theo transaction, hoặc khi writer xử lý replay một cách an toàn.

Việc gọi `update(context)` ở một test thuần Java chỉ thay đổi object trong bộ nhớ. Trong job thật, **framework và `JobRepository`** chịu trách nhiệm lưu context bền vững theo ranh giới transaction. Không nên tự gọi repository update trên mỗi `read()` để “chắc ăn”; làm như vậy có thể tạo checkpoint tiến trước dữ liệu đã commit.

## 3. Nhận diện reader không có khả năng restart

Những nguyên nhân thường gặp:

1. Reader chỉ triển khai `ItemReader<T>`, giữ `Iterator`, page number hoặc index trong field nhưng không có `ItemStream` để lưu trạng thái.
2. Reader hỗ trợ `ItemStream` nhưng được cấu hình `saveState(false)`, tức cố ý không lưu vị trí.
3. Reader có `ItemStream` ở bên trong một wrapper/composite, nhưng **step không đăng ký delegate stream** nên không gọi lifecycle của delegate.
4. Reader có `@StepScope` và nhận được `JobParameters` nhưng không giữ checkpoint; tạo bean mới khi restart rồi đọc lại từ đầu.
5. Reader có lưu offset nhưng nguồn dữ liệu **không ổn định**: file bị thay thế, SQL thiếu thứ tự ổn định, dữ liệu bị chèn/xóa, API stream không cho phát lại.
6. Reader dùng chung giữa nhiều execution hoặc nhiều thread, khiến index và checkpoint bị ghi đè/race condition.
7. Context có key xung đột, reader bị đổi `name` sau deploy, hoặc serializer/context không còn tương thích.
8. Metadata của `JobRepository` không được commit hoặc đã mất do database lỗi, cleanup hoặc restore từ bản backup cũ.

Một số dấu hiệu chỉ xuất hiện gián tiếp:

| Triệu chứng | Khả năng cần điều tra |
| --- | --- |
| Restart đọc lại từ record đầu | Không có checkpoint, `saveState(false)`, hoặc context không được restore |
| Restart báo duplicate key | Reader replay dữ liệu đã ghi hoặc writer không idempotent |
| Restart bỏ qua nhiều record | Checkpoint lệch với file/query mới; checkpoint tiến quá dữ liệu đã commit |
| Có `@StepScope` nhưng vẫn đọc lại | Scope tạo bean mới, **không tự lưu vị trí đọc** |
| Có `ItemStreamReader` nhưng `update` không chạy | Delegate bị wrapper che; step không đăng ký stream |
| Đã lưu context nhưng reader mở ở index 0 | Key/name khác lần trước; logic `open` bỏ qua context |
| Cùng input có kết quả khác khi restart | Nguồn hoặc thứ tự truy vấn đã thay đổi |
| Multi-thread step bị lặp/thiếu | Reader state không thread-safe hoặc checkpoint không thể biểu diễn tiến độ song song |

Đừng sửa lỗi bằng cách đặt `allowStartIfComplete(true)` hoặc thêm `run.id=timestamp` mà chưa hiểu hậu quả. Hai lựa chọn này **không khiến reader tự phục hồi checkpoint**.

## 4. Ví dụ lỗi: reader giữ `Iterator` trong RAM

Đây là một reader tối giản có vẻ hoạt động tốt khi job chạy một lần:

```java
import java.util.Iterator;
import java.util.List;
import org.springframework.batch.item.ItemReader;

public class NonRestartableOrdersReader implements ItemReader<String> {

    private final Iterator<String> iterator;

    public NonRestartableOrdersReader(List<String> orders) {
        this.iterator = orders.iterator();
    }

    @Override
    public String read() {
        return iterator.hasNext() ? iterator.next() : null;
    }
}
```

Nếu tạo reader với danh sách `["A", "B", "C", "D"]`, gọi `read()` hai lần sẽ trả `A` rồi `B`. Nhưng nếu process chết và Spring tạo object reader mới, iterator cũng mới và vị trí lại là 0.

```text
JobExecution lần 1:
  read A -> write A -> commit
  read B -> write B -> commit
  read C -> writer lỗi, step FAILED

JobExecution lần 2:
  new NonRestartableOrdersReader(...)
  read A  <-- đã xử lý trước đó
  read B  <-- đã xử lý trước đó
```

Vấn đề không phải `Iterator` sai; vấn đề là **vị trí chỉ tồn tại trong bộ nhớ của một reader instance**. Không có cơ chế nào để `JobRepository` lấy được vị trí ấy trong lần chạy mới.

Một số reader kiểu danh sách/cursor chỉ dùng để kiểm thử hoặc tác vụ rerun toàn bộ có thể phù hợp với thiết kế này. Nhưng nếu yêu cầu là **restart chính xác từ chunk commit trước đó**, cần dùng reader có `ItemStream` hoặc chuyển sang chiến lược input replay/idempotency.

## 5. Sửa bằng custom `ItemStreamReader` có checkpoint

Để thấy chính xác cơ chế, ta viết một reader dùng danh sách **bất biến** và lưu `nextIndex` vào `ExecutionContext`. Đây là ví dụ giáo dục cho nguồn dữ liệu một luồng, có thứ tự cố định; trong production thường nên ưu tiên reader có sẵn của Spring Batch.

```java
import java.util.List;
import java.util.Objects;

import org.springframework.batch.item.ExecutionContext;
import org.springframework.batch.item.ItemStreamException;
import org.springframework.batch.item.ItemStreamReader;

public final class CheckpointingListReader
        implements ItemStreamReader<String> {

    private final List<String> items;
    private final String name;
    private int nextIndex;

    public CheckpointingListReader(String name, List<String> items) {
        this.name = Objects.requireNonNull(name);
        this.items = List.copyOf(items);
    }

    private String checkpointKey() {
        return name + ".nextIndex";
    }

    @Override
    public void open(ExecutionContext context) {
        nextIndex = context.getInt(checkpointKey(), 0);

        if (nextIndex < 0 || nextIndex > items.size()) {
            throw new ItemStreamException(
                    "Invalid reader checkpoint for " + name);
        }
    }

    @Override
    public String read() {
        if (nextIndex >= items.size()) {
            return null;
        }
        return items.get(nextIndex++);
    }

    @Override
    public void update(ExecutionContext context) {
        context.putInt(checkpointKey(), nextIndex);
    }

    @Override
    public void close() {
        // Không có tài nguyên bên ngoài cần đóng.
    }
}
```

Giải thích:

- `nextIndex` luôn chỉ vào **item tiếp theo** chưa trả ra, tránh nhầm với index cuối đã đọc.
- `open` đọc state đã lưu; không có state thì bắt đầu từ 0.
- `update` đặt checkpoint vào context mà framework sẽ lưu khi chunk commit.
- `checkpointKey()` có tên riêng, tránh đụng những stream khác trong cùng step.
- `List.copyOf(items)` giữ cấu trúc danh sách không đổi **trong lần thực thi hiện tại**; để restart chính xác, lần chạy sau phải nhận **cùng dữ liệu và cùng thứ tự**.
- Ví dụ chỉ an toàn cho **đọc tuần tự**. Nếu step có retry/rollback trong chính một execution, phải xét khả năng reader tua lại hoặc framework buffer item; reader này chưa phải một bộ đọc production cho mọi kịch bản transaction/concurrency.

### Kiểm tra checkpoint bằng JUnit

```java
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.batch.item.ExecutionContext;

import static org.junit.jupiter.api.Assertions.assertEquals;

class CheckpointingListReaderTest {

    @Test
    void resumesFromTheLastSavedCheckpoint() throws Exception {
        List<String> source = List.of("A", "B", "C", "D");
        ExecutionContext savedContext = new ExecutionContext();

        CheckpointingListReader first =
                new CheckpointingListReader("orders", source);
        first.open(savedContext);

        assertEquals("A", first.read());
        assertEquals("B", first.read());

        // Mô phỏng ranh giới chunk đã thành công:
        first.update(savedContext);

        // Item C được đọc nhưng chunk tiếp theo chưa commit:
        assertEquals("C", first.read());
        first.close();

        // Tạo reader mới như sau crash/restart:
        CheckpointingListReader restarted =
                new CheckpointingListReader("orders", source);
        restarted.open(savedContext);

        assertEquals("C", restarted.read());
        assertEquals("D", restarted.read());
        restarted.close();
    }
}
```

Test minh họa **logic lưu và phục hồi index trong `ExecutionContext`**, chưa phải test restart đầy đủ. Nó không chạy `JobRepository`, không mô phỏng transaction/database thật và không xác nhận writer idempotent. Một integration test cần chạy job/step, tạo failure thật sau chunk đã commit, rồi khởi chạy lại cùng `JobInstance` và đối chiếu output.

### Những trường hợp custom checkpoint phức tạp hơn index

| Nguồn dữ liệu | State có thể cần lưu | Điều kiện để replay đúng |
| --- | --- | --- |
| File từng record | Vị trí item/byte offset, resource ID, encoding | File không đổi; reader hiểu record separator và BOM |
| JDBC cursor | Vị trí được framework quản lý hoặc mốc truy vấn | Dữ liệu/thứ tự truy vấn đủ ổn định |
| JDBC paging | Sort keys, paging state, snapshot logic | Khóa sắp xếp xác định và ổn định |
| API phân trang | Page token/cursor, resource version, vị trí trong page | Token còn hiệu lực; endpoint trả cùng tập dữ liệu |
| Kafka/queue | Offset/acknowledgment hoặc mã message bền vững | Chính sách commit/ack phù hợp với writer và transaction |
| Nhiều file | File hiện tại, vị trí trong file, danh sách/version file | Danh sách và thứ tự file có thể tái tạo |

Không nên cố lưu cả nội dung file, object có connection đang mở hoặc iterator vào `ExecutionContext`. Context là nơi lưu **checkpoint nhỏ, bền vững và serializable**, không phải cache toàn bộ input.

## 6. Ưu tiên reader có sẵn với `saveState(true)`

Với các nguồn phổ biến, hãy kiểm tra liệu reader Spring Batch đã có hỗ trợ `ItemStream` và checkpoint hay chưa. Ví dụ `FlatFileItemReader`, `JdbcCursorItemReader` và `JdbcPagingItemReader` có cơ chế lưu state phù hợp với đặc điểm của chúng.

### Ví dụ `FlatFileItemReader` để restart

```java
import java.math.BigDecimal;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.FileSystemResource;

@Configuration
public class RestartableFileReaderConfig {

    public record OrderRow(String orderId, BigDecimal amount) {}

    @Bean
    @StepScope
    public FlatFileItemReader<OrderRow> ordersReader(
            @Value("#{jobParameters['inputFile']}") String inputFile) {

        return new FlatFileItemReaderBuilder<OrderRow>()
                .name("ordersReader")
                .resource(new FileSystemResource(inputFile))
                .encoding("UTF-8")
                .strict(true)
                .linesToSkip(1) // Bỏ header của CSV.
                .saveState(true)
                .delimited()
                .names("orderId", "amount")
                .fieldSetMapper(fields -> new OrderRow(
                        fields.readString("orderId"),
                        fields.readBigDecimal("amount")))
                .build();
    }
}
```

`saveState(true)` là mặc định của builder này ở Spring Batch 5.2, nhưng viết rõ có thể giúp người bảo trì nhận biết rằng **restart từ checkpoint là yêu cầu**. Khi lưu state, `name("ordersReader")` cung cấp một phần định danh để reader tạo key trong `ExecutionContext`.

`@StepScope` cho phép reader lấy `inputFile` theo `JobParameters` và được tạo theo phạm vi step; **`@StepScope` không thay thế `saveState` hoặc `ItemStream`**. Trong một context Spring Batch đã đăng ký StepScope, Spring tạo scoped proxy phù hợp.

Các điều kiện để ví dụ restart đúng:

1. File `inputFile` phải là **cùng nội dung/cùng thứ tự record** trong các lần chạy lại của cùng công việc.
2. Tên reader và các key checkpoint phải tương thích qua các lần deployment; đổi `name` có thể làm key cũ không còn được đọc.
3. Bảng metadata và `StepExecutionContext` của `JobInstance` phải còn.
4. Step phải được framework đăng ký reader stream và đóng/mở đúng lifecycle.
5. Writer/transaction phải xử lý an toàn các item của chunk chưa commit.
6. File phải có thể mở lại; đường dẫn tạm bị xóa giữa các lần chạy sẽ không hỗ trợ restart dù reader có state.

Đặc biệt, không tự đặt `currentItemCount` cố định mỗi lần chạy để “tiếp tục ở dòng đã biết”, bởi cách đó dễ ghi đè hoặc bỏ qua checkpoint thật. Chỉ dùng các tùy chọn khởi tạo vị trí khi chúng phản ánh hợp đồng xử lý có chủ đích.

### Những lưu ý riêng với reader JDBC

| Reader | Vấn đề khi restart | Khuyến nghị |
| --- | --- | --- |
| `JdbcCursorItemReader` | Tập kết quả hoặc thứ tự dòng có thể thay đổi giữa hai lần đọc | SQL có thứ tự ổn định, nguồn dữ liệu phù hợp với điểm resume; kiểm tra `saveState` |
| `JdbcPagingItemReader` | Phân trang cần xác định đúng điểm tiếp tục | Dùng sort key ổn định và **duy nhất**; cẩn trọng với hàng được chèn/xóa/cập nhật |
| Reader đọc bảng đang thay đổi liên tục | Offset vật lý không còn tương ứng cùng business row | Snapshot/đánh dấu dữ liệu theo batch ID hoặc process indicator |
| Reader API cursor theo session | Cursor/token hết hạn sau crash | Dùng durable token có thể replay hoặc staging dữ liệu trước khi xử lý |

Một câu `SELECT * FROM orders` không có `ORDER BY` là nguồn rủi ro nếu reader/checkpoint dựa trên vị trí dòng. Ngay cả khi có `ORDER BY created_at`, nếu nhiều dòng có cùng `created_at` thì thứ tự giữa các dòng có thể không ổn định. Với paging reader, hãy chọn khóa sắp xếp duy nhất như `(created_at, order_id)` khi phù hợp và đảm bảo nguồn không đổi theo cách khiến dữ liệu bị bỏ qua.

## 7. Khi reader có `ItemStream` nhưng wrapper che mất lifecycle

Một lỗi khó nhận ra: developer đã chọn `FlatFileItemReader` hoặc `JdbcCursorItemReader` có checkpoint, nhưng đặt bên ngoài nó một `ItemReader` khác và chỉ truyền wrapper vào step. Spring Batch tự đăng ký `ItemStream` khi đó là reader/writer/processor **trực tiếp** của step. Delegate bị ẩn bên trong có thể không được framework tự gọi `open`, `update`, `close`.

Ví dụ có wrapper chuyển tiếp đơn giản:

```java
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemStreamReader;

// delegate là reader có hỗ trợ checkpoint.
ItemStreamReader<String> delegate = /* reader thật */;

ItemReader<String> wrapper = () -> delegate.read();
```

Nếu chỉ gắn `wrapper` vào `StepBuilder.reader(...)`, lifecycle của `delegate` không được bảo đảm. Cần **đăng ký delegate với step**:

```java
@Bean
Step stepWithWrappedReader(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemStreamReader<String> delegate,
        ItemWriter<String> writer) {

    ItemReader<String> wrapper = delegate::read;

    return new StepBuilder("stepWithWrappedReader", jobRepository)
            .<String, String>chunk(100, transactionManager)
            .reader(wrapper)
            .writer(writer)
            .stream(delegate) // Gọi open/update/close cho stream bị ẩn.
            .build();
}
```

Đoạn code được đặt trong class `@Configuration` của ứng dụng, giả định các bean và import tương ứng đã có. Các import chính: `org.springframework.batch.core.Step`, `org.springframework.batch.core.repository.JobRepository`, `org.springframework.batch.core.step.builder.StepBuilder`, `org.springframework.transaction.PlatformTransactionManager`, `org.springframework.batch.item.ItemReader`, `ItemWriter` và `ItemStreamReader`.

Có thể chọn cách khác: viết wrapper **cũng triển khai `ItemStreamReader`** và chuyển tiếp cả `open`/`update`/`close` cho delegate, bảo đảm không đăng ký lặp cùng stream. Nếu có nhiều reader/writer con, mỗi stream có key checkpoint riêng trong `ExecutionContext`.

Cũng cần lưu ý: một wrapper che cả `StepListener` của delegate có thể làm mất listener callback, nhưng đó là vấn đề khác với `ItemStream` và phải được cấu hình phù hợp.

## 8. Restart cùng `JobInstance` và `JobParameters`

Một job restart không phải là “chạy lại một job bất kỳ với input giống gần giống”. Nó là **thực thi lại cùng `JobInstance`** khi metadata cho phép.

```text
JobInstance = jobName + identifying JobParameters

Job name: importOrders
Identifying parameters:
  businessDate = 2026-11-15
  inputVersion = orders-v3-sha256-...
```

Hai `JobExecution` liên tiếp muốn thuộc cùng instance cần cùng tên job và cùng tập identifying parameters. Ví dụ chuẩn bị ổn định:

```java
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;

JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("inputVersion", "orders-v3", true)
        .toJobParameters();

// Sau FAILED, dùng lại đúng bộ identifying parameters
// để khởi chạy lại cùng JobInstance:
JobParameters restartParameters =
        new JobParametersBuilder(parameters).toJobParameters();
```

Ví dụ chỉ chuẩn bị tham số, chưa thực thi job. Khi gọi `JobLauncher.run(job, restartParameters)` với job/repository phù hợp, Spring Batch sẽ áp dụng quy tắc restart. `JobInstanceAlreadyCompleteException` xảy ra khi instance đã hoàn tất; `JobExecutionAlreadyRunningException` xảy ra khi framework còn ghi nhận một execution đang chạy; lỗi loại này **không được giải quyết bằng cách thêm timestamp** nếu mục tiêu là restart.

Phân biệt các cấu hình thường bị nhầm:

| Cấu hình hoặc thao tác | Tác dụng thật | Có sửa reader không restartable? |
| --- | --- | --- |
| `JobBuilder.preventRestart()` | Cấm restart job | **Không**; chỉ chấp nhận mất khả năng restart |
| `saveState(false)` trên reader | Không lưu checkpoint của reader | **Không**; thường tạo ra chính vấn đề |
| `@StepScope` | Tạo bean theo phạm vi step và giải tham số runtime | **Không** nếu reader không lưu state |
| `allowStartIfComplete(true)` trên step | Cho phép chạy lại step đã hoàn tất trong lần thực thi sau | **Không**; có thể tạo replay ngoài ý muốn |
| Đổi `run.id`/UUID | Tạo job instance mới nếu param identifying | **Không**; có thể xử lý lại từ đầu |
| `saveState(true)` + `name` đúng | Cho reader có hỗ trợ state lưu checkpoint | **Có ích**, nếu nguồn ổn định và lifecycle hoạt động |
| Tạo reader kiểu `ItemStreamReader` | Tự định nghĩa state/cách khôi phục | **Có ích**, nếu `open/update` đúng và được đăng ký |
| Process indicator + writer idempotent | Tránh đọc lại record đã xử lý, không dựa offset | **Giải pháp thay thế**, cần thiết kế transaction đúng |

Nếu step đã `COMPLETED` trước khi job thất bại ở step sau, Spring Batch có thể bỏ qua step ấy khi restart; không cần cưỡng ép đọc lại chỉ để “chạy cho đủ”. Nếu step `FAILED`, chỉ riêng việc có checkpoint không bảo đảm restart an toàn nếu nguồn hoặc writer đã thay đổi.

## 9. Khi nguồn không hỗ trợ replay: dùng process indicator

Không phải nguồn nào cũng khôi phục được bằng offset. Ví dụ một endpoint HTTP chỉ trả stream một lần hoặc database luôn thay đổi thứ tự dữ liệu. Khi đó không nên cố biến con số `nextIndex` trong RAM thành checkpoint đáng tin cậy.

Một chiến lược thường dùng là **process indicator**: nguồn có trạng thái bền vững cho biết record nào đã xử lý thành công. Reader mỗi lần chạy chọn những record còn `processed=false`. Lúc này trạng thái hoàn tất **nằm trong dữ liệu nghiệp vụ**, không phụ thuộc offset vật lý của reader.

Ví dụ SQL khái niệm:

```sql
SELECT id, payload
FROM import_inbox
WHERE processed = FALSE
ORDER BY id;
```

Khi item được ghi thành công, ứng dụng đánh dấu processed trong một transaction thích hợp:

```sql
UPDATE import_inbox
SET processed = TRUE
WHERE id = :id
  AND processed = FALSE;
```

Nếu dữ liệu đích và bảng `import_inbox` nằm **cùng một database transaction**, writer có thể ghi kết quả và cập nhật indicator cùng nhau, hạn chế trường hợp “đã xử lý nhưng vẫn còn được chọn”. Khi dùng database/tài nguyên khác nhau, phải thiết kế idempotency key, outbox/inbox hoặc quy tắc xác nhận độc lập.

Với chiến lược này, một số reader được cấu hình `saveState(false)` **có chủ đích**, vì checkpoint theo vị trí sẽ không còn đúng khi tập dữ liệu chưa xử lý co lại sau mỗi commit. Đây là một ngoại lệ quan trọng: **reader không lưu offset vẫn có thể hỗ trợ restart nghiệp vụ** nếu toàn bộ hệ thống bảo đảm chỉ chọn item chưa xử lý và side effect có thể replay an toàn.

Cần cân nhắc:

- Hệ thống phải có khóa nghiệp vụ duy nhất và đánh dấu hoàn tất **sau khi** kết quả được ghi theo transaction/consistency đã chọn.
- Nếu nhiều worker đọc cùng nguồn, cần cơ chế **claim/locking** để tránh xử lý cùng row song song.
- Các status như `NEW`, `PROCESSING`, `DONE`, `FAILED` và lease timeout có thể cần thiết cho nguồn phân tán.
- Với dữ liệu input thay đổi khi job đang chạy, phải xác định “tập record của kỳ này” bằng batch ID, timestamp/snapshot hoặc danh sách staging.
- `processed=false` không tự giải quyết external API đã nhận request nhưng DB chưa đánh dấu xong; cần idempotency ở hệ thống đích.

## 10. Multi-threaded step và giới hạn của checkpoint theo vị trí

Reader có thể hoạt động restart trong step tuần tự nhưng không phù hợp khi nhiều thread gọi `read()`. Trong multi-threaded step, chunk có thể được xử lý và commit **không theo đúng thứ tự đọc**.

```text
Reader phát item: A, B, C, D, E, F

Thread 1 lấy A,B,C -> writer chậm
Thread 2 lấy D,E,F -> commit trước

Một checkpoint index=6 không chứng minh A,B,C đã commit.
```

Chỉ khóa `read()` bằng `synchronized` giúp tránh hai thread lấy cùng vị trí cùng lúc, nhưng **không bảo đảm checkpoint phản ánh mọi chunk đã commit**. Spring Batch có `SynchronizedItemStreamReader` để bọc một reader chưa thread-safe; tài liệu API cảnh báo rằng nếu việc xử lý lại item là vấn đề thì cách này có thể khiến job không restartable.

Các phương án cân nhắc:

1. **Giữ một step đọc tuần tự** nếu tính đúng đắn và restart quan trọng hơn throughput.
2. **Partitioning**: chia nguồn thành các khoảng độc lập, mỗi partition có reader, `StepExecution` và checkpoint riêng; key/ranh giới phân vùng phải ổn định.
3. **Process indicator/claim queue**: mỗi item có trạng thái xử lý bền vững, không dựa một con trỏ tuần tự chung.
4. **Idempotent writer** để xử lý item bị replay nếu failure xảy ra giữa các tác động ngoài transaction.

Không tùy tiện bật `saveState(true)` cho reader dùng nhiều thread và mong nó trở nên an toàn. Một số implementation khuyến nghị **tắt lưu state khi hoạt động đồng thời**, sau đó dựa vào một chiến lược dữ liệu riêng để bảo đảm restart.

## 11. Ranh giới transaction, skip và rollback

Khả năng restart chính xác không chỉ nằm ở reader. Sau khi xử lý một chunk, Spring Batch phải đưa state của reader và kết quả nghiệp vụ về một điểm nhất quán.

Giả sử chunk size là 3:

```text
Checkpoint đã commit: nextIndex = 6

Reader đọc index 6, 7, 8
Processor xử lý 6, 7, 8
Writer gọi external API cho 6, 7, 8
   |
   +-- API đã nhận item 6, 7
   +-- item 8 gây timeout
   +-- chunk rollback / checkpoint 6 vẫn còn

Restart từ index 6:
  gửi lại item 6, 7, 8
```

Nếu writer có giao dịch chung với metadata, rollback trước commit sẽ thường hủy cả data và checkpoint. Với **HTTP API, email, file, queue ngoài transaction**, rollback của `JobRepository` không hủy được side effect đã xảy ra. Vì vậy ngay cả reader restartable cũng chưa đủ để bảo đảm **exactly-once business effect**.

Một vài nguyên tắc:

- `readCount` là số item đọc thành công được framework ghi nhận, không phải lúc nào cũng là offset vật lý của file; không dùng `readCount` để suy ra mọi checkpoint.
- Lỗi được `skipPolicy` cho phép có thể làm tăng `readSkipCount`, `processSkipCount` hoặc `writeSkipCount`; với reader tùy chỉnh, cần xác định item lỗi có được tiêu thụ/di chuyển vị trí đúng không.
- Khi retry, một item có thể được đọc/xử lý/ghi nhiều lần trong một execution; số lần gọi `read()` không bằng số item đã commit.
- `ExecutionContext` được lưu theo ranh giới transaction; đừng gọi `update` hoặc tự persist state ngay sau mỗi item mà không có cơ chế commit tương thích.
- Với dữ liệu ngoài transaction, có thể dùng idempotency key gắn với **business identity**, không gắn với `jobExecutionId` vì ID này đổi khi restart.

Một hệ thống cần kết quả không trùng phải kiểm soát đồng thời **replay của reader**, **điểm commit** và **tác động writer**.

## 12. Cách điều tra một job restart nhưng đọc lại từ đầu

Nên làm việc theo đúng thứ tự thay vì thử sửa nhiều cấu hình cùng lúc.

### Bước 1 — Xác định lần chạy và instance

Ghi lại `jobName`, `jobInstanceId`, `jobExecutionId`, `stepName`, `stepExecutionId` và các identifying `JobParameters`. Xác nhận lần chạy sau thật sự là **restart cùng `JobInstance`**, không phải instance mới có `run.id`, timestamp hay resource path thay đổi.

### Bước 2 — Kiểm tra step nào được chạy lại

Với `JobExplorer`, đọc lần `FAILED` và lần khởi chạy sau. Xem step trước đó có `FAILED`/`STOPPED` hay đã `COMPLETED`; đừng giả định mọi step đều được chạy lại.

```java
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.explore.JobExplorer;

public void showExecutions(JobExplorer explorer, long jobExecutionId) {
    JobExecution job = explorer.getJobExecution(jobExecutionId);

    if (job == null) {
        throw new IllegalArgumentException("Unknown execution");
    }

    System.out.printf("job=%s instance=%s execution=%s status=%s%n",
            job.getJobInstance().getJobName(),
            job.getJobInstance().getId(),
            job.getId(),
            job.getStatus());

    for (StepExecution step : job.getStepExecutions()) {
        System.out.printf(
                "step=%s stepExecution=%s status=%s " +
                "read=%d write=%d commit=%d rollback=%d contextKeys=%s%n",
                step.getStepName(), step.getId(), step.getStatus(),
                step.getReadCount(), step.getWriteCount(),
                step.getCommitCount(), step.getRollbackCount(),
                step.getExecutionContext().keySet());
    }
}
```

Đây là đoạn code minh họa dùng **Spring Batch 5.2.x**. Context keys hữu ích để tìm checkpoint của reader nhưng có thể chứa tên/path hoặc dữ liệu nhạy cảm; chỉ xuất ở môi trường điều tra được phân quyền. `JobExplorer` phản ánh metadata đã được lưu, không chứng minh mọi side effect ngoài transaction đã commit.

### Bước 3 — Kiểm tra `ItemStream` và `saveState`

Xem class reader thực tế triển khai `ItemStream` hoặc `ItemStreamReader` không. Với built-in reader, xác nhận `saveState(true)` và tên reader ổn định. Với custom reader, kiểm tra logic:

- `open` có đọc lại đúng key checkpoint?
- `update` có lưu trạng thái “item tiếp theo” ở mốc commit?
- `close` có giữ nguyên dữ liệu cần lưu, không xóa checkpoint?
- `read` có vô tình reset index khi tạo resource mới?
- Context có bị đổi tên key sau nâng cấp/đổi cấu hình không?

### Bước 4 — Kiểm tra wrapper/delegate

Nếu reader thật nằm trong `CompositeItemReader` hoặc wrapper khác, kiểm tra step có gọi callback `ItemStream` cho **tất cả delegate cần lưu state** không. Với delegate không được phát hiện tự động, đăng ký bằng `.stream(delegate)` hoặc thiết kế wrapper chuyển tiếp lifecycle.

### Bước 5 — Kiểm tra input có bất biến không

Đối chiếu checksum/file version, số record, thứ tự sort key, timestamp của dữ liệu nguồn và chính sách paging. Cùng index=200 không có giá trị nếu vị trí 200 đã trở thành một bản ghi khác.

### Bước 6 — Kiểm tra writer và transaction

Đối chiếu item đã được ghi/được hệ thống ngoài xác nhận với checkpoint cuối. Nếu có tác động đã xảy ra sau checkpoint, **không restart tự động** trước khi xác định deduplication/idempotency.

### Bước 7 — Chọn một hướng phục hồi

Có thể sửa reader, khôi phục đầu vào bất biến rồi restart, chuyển sang process indicator, staging/replay hoặc tạo một **job instance mới có kiểm soát** sau đối soát. Phương án cuối không phải restart từ checkpoint; phải ghi rõ đây là rerun/replay.

## 13. Đọc metadata bằng SQL khi cần

Nếu dùng `JobRepository` JDBC và table prefix mặc định `BATCH_`, câu truy vấn sau giúp biết lịch sử execution/step. Chỉ đọc, không sửa metadata:

```sql
SELECT
    ji.JOB_NAME,
    ji.JOB_INSTANCE_ID,
    je.JOB_EXECUTION_ID,
    je.STATUS AS JOB_STATUS,
    je.START_TIME AS JOB_START_TIME,
    je.END_TIME AS JOB_END_TIME,
    se.STEP_EXECUTION_ID,
    se.STEP_NAME,
    se.STATUS AS STEP_STATUS,
    se.READ_COUNT,
    se.WRITE_COUNT,
    se.COMMIT_COUNT,
    se.ROLLBACK_COUNT,
    se.LAST_UPDATED
FROM BATCH_JOB_INSTANCE ji
JOIN BATCH_JOB_EXECUTION je
  ON je.JOB_INSTANCE_ID = ji.JOB_INSTANCE_ID
LEFT JOIN BATCH_STEP_EXECUTION se
  ON se.JOB_EXECUTION_ID = je.JOB_EXECUTION_ID
WHERE ji.JOB_NAME = :jobName
ORDER BY je.JOB_EXECUTION_ID, se.STEP_EXECUTION_ID;
```

`:jobName` là named parameter minh họa; khi chạy trong công cụ SQL thuần, dùng cú pháp bind phù hợp. Checkpoint của step thường nằm trong `BATCH_STEP_EXECUTION_CONTEXT`, nhưng **không tự parse, sửa hoặc xóa** row context bằng SQL để “dời con trỏ”. Serializer, khóa nội bộ và tính tương thích phiên bản có thể thay đổi. Ưu tiên đọc qua `JobExplorer`/API của Spring Batch và chỉ phục hồi metadata bằng quy trình vận hành chính thức.

Một số thông tin cần đối chiếu:

| Metadata | Ý nghĩa điều tra |
| --- | --- |
| `JOB_INSTANCE_ID` | Các execution có thực sự cùng một instance không |
| `JOB_EXECUTION_ID` | Có restart thật hay mỗi lần tạo instance mới |
| `STEP_EXECUTION_ID` | Step nào thực thi lần đầu và lần sau |
| `STATUS` | `FAILED`, `STARTED`, `COMPLETED`, `STOPPED` |
| `READ_COUNT`/`WRITE_COUNT` | Khối lượng framework ghi nhận, không phải checkpoint duy nhất |
| `COMMIT_COUNT`/`ROLLBACK_COUNT` | Chunk có commit/rollback không |
| `ExecutionContext` | Reader đã lưu key và vị trí gì ở mốc commit |
| `LAST_UPDATED` | Metadata được ghi lần cuối; không đồng nghĩa heartbeat liên tục |

Nếu trạng thái vẫn `STARTED` sau khi process đã chết, cần xử lý **execution mồ côi** theo quy trình xác minh riêng; đừng tự thay bằng `FAILED` qua SQL khi chưa đối soát dữ liệu.

## 14. Kiểm thử restart ở cấp tích hợp

Một reader có unit test `open/update` đúng vẫn có thể thất bại trong job thật: stream không được đăng ký, file thay đổi, transaction không đồng bộ hoặc writer thiếu idempotency.

Kịch bản integration test cơ bản:

1. Tạo repository/database **riêng cho test**, nguồn input cố định gồm 6 record và writer có khóa nghiệp vụ duy nhất.
2. Đặt chunk size 2; lần chạy đầu commit record 1–2 và cố tình gây lỗi không skip ở record 3.
3. Xác nhận `JobExecution` đầu `FAILED`, output có đúng record 1–2; metadata có checkpoint của chunk đã commit.
4. Bỏ điều kiện gây lỗi nhưng **không thay identifying `JobParameters`**, không xóa context/repository.
5. Chạy lại cùng job/instance; reader phải tiếp tục từ record 3 (hoặc replay an toàn theo chiến lược đã chọn).
6. Xác nhận execution mới `COMPLETED` và đích chứa chính xác 6 business IDs duy nhất.
7. Xem cả `readCount`/`writeCount` và dữ liệu thật; không chỉ kiểm tra status.

Ví dụ assertion khái niệm:

```java
// Trong integration test đã cấu hình Spring Batch và test DB:
JobExecution first = jobLauncher.run(importOrdersJob, fixedParameters);
assertEquals(BatchStatus.FAILED, first.getStatus());

disableInjectedFailure();

JobExecution restarted = jobLauncher.run(importOrdersJob, fixedParameters);
assertEquals(BatchStatus.COMPLETED, restarted.getStatus());

// Đếm business records duy nhất, không cộng mù các writeCount:
assertEquals(6, orderRepository.count());
assertEquals(6, orderRepository.countDistinctOrderIds());
```

Đây là **pseudocode có chủ đích**: `disableInjectedFailure()`, `orderRepository` và cấu hình job/test DB là thành phần của dự án; không phải API Spring Batch. `BatchStatus` được import từ `org.springframework.batch.core.BatchStatus` ở Spring Batch 5.x.

Để mô phỏng lỗi thật, nên inject failure tại một điểm xác định **sau khi một chunk đã commit**. Nếu ném lỗi trong chunk đầu trước commit, output đúng có thể vẫn trống, khiến test không kiểm chứng khả năng resume. Test còn nên xác nhận reader mới được tạo, `ExecutionContext` còn bền vững sau khi context Spring khởi tạo lại, và nguồn không thay đổi.

### Những trường hợp biên nên thử

| Kịch bản | Kỳ vọng |
| --- | --- |
| Crash trước commit chunk đầu | Restart từ đầu, không có side effect đã commit bị nhân đôi |
| Crash sau commit chunk thứ hai | Resume từ checkpoint đã lưu |
| Đổi `saveState(false)` | Test phát hiện replay ngoài thiết kế |
| Wrapper không đăng ký delegate | Test phát hiện thiếu callback `open/update` |
| Đổi tên reader giữa hai deployment | Test/điều tra phát hiện key context không tương thích |
| Input file bị thay đổi sau failure | Restart bị từ chối hoặc chuyển sang quy trình replay riêng |
| Writer gọi API ngoài và bị timeout | Idempotency key không tạo side effect trùng |
| Multi-thread reader | Không có item bị skip/trùng do checkpoint không xác định |
| Process chết lúc cập nhật metadata | Kiểm tra trạng thái và checkpoint đã commit trước khi phục hồi |

## 15. Quy trình khắc phục trên hệ thống đang chạy

Khi sự cố đã xảy ra ở production, thứ tự ưu tiên là **bảo toàn dữ liệu trước khi chạy lại**:

```text
Phát hiện FAILED / duplicate / reader reset
                 |
                 v
   Xác nhận process cũ đã dừng hẳn?
                 |
          +------+-------+
          |              |
         Chưa           Rồi
          |              |
  Không restart         v
                  Kiểm tra metadata
                  và source version
                         |
                  +------+-------+
                  |              |
          Checkpoint tin cậy?   Không
                  |              |
                 Có              v
                  |      Đối soát input/output,
                  v      thiết kế replay an toàn
           Writer có idempotency
           hoặc cùng transaction?
                  |
           +------+------+
           |             |
          Có            Chưa
           |             |
     Restart đúng       v
     JobInstance    Dừng để đối soát
                    và giảm trùng lặp
```

Runbook nên ghi lại: ID execution, input checksum/version, checkpoint cuối được xác nhận, số bản ghi đầu ra theo khóa nghiệp vụ, loại reader, trạng thái `saveState`, người phê duyệt replay và kết quả đối soát sau khôi phục.

Tuyệt đối tránh các “chữa cháy” không kiểm soát như:

- Thêm `run.id`/UUID mỗi lần thử lại để né `JobExecutionAlreadyRunningException` hay `JobInstanceAlreadyCompleteException`.
- Xóa `BATCH_STEP_EXECUTION_CONTEXT` hoặc thay các cột `STATUS`/`VERSION` thủ công.
- Đổi `saveState(true)` nhưng không kiểm tra source đã thay đổi và writer có thể ghi trùng.
- Coi `@StepScope` là đủ để xác nhận reader có checkpoint.
- Retry không giới hạn với API ngoài không hỗ trợ idempotency.
- Đánh dấu processed trước khi kết quả ghi bền vững, dẫn đến bỏ sót item sau crash.

## 16. Phân biệt các phương án thiết kế

| Cách xử lý | Phù hợp khi | Đánh đổi / nguy cơ |
| --- | --- | --- |
| Built-in `ItemStreamReader` + `saveState(true)` | File/cursor/paging có input ổn định | Phải giữ source/schema/sort order và metadata nhất quán |
| Custom `ItemStreamReader` | Nguồn riêng có cursor/offset replay được | Tự chịu trách nhiệm `open/update/close`, key, transaction và test |
| Process indicator | Dữ liệu có status bền vững; muốn không phụ thuộc offset | Cần claim/idempotency/transaction và đối soát record |
| Snapshot hoặc staging input | Nguồn API/DB thay đổi trong khi chạy | Tốn storage/ETL nhưng tạo nguồn có thể tái lập |
| Partitioning với checkpoint riêng | Nguồn lớn, cần scale song song | Thiết kế phân vùng ổn định và tránh overlap |
| Restart từ đầu nhưng writer idempotent | Công việc cho phép replay toàn bộ | Tốn thời gian; phải có bằng chứng không tạo side effect trùng |
| Không cho restart (`preventRestart`) | Công việc chủ động chỉ chạy một lần, có quy trình xử lý ngoài | Không thỏa nhu cầu restart nếu nghiệp vụ bắt buộc tiếp tục |

Mỗi lựa chọn cần được đánh giá bằng **mục tiêu nghiệp vụ**: phải xử lý đúng một lần hay có thể phát lại? Có thể dựng lại tập input ban đầu không? Đích có unique business key hoặc idempotency không? Metadata và dữ liệu đích có cùng transaction không?

## 17. Tóm tắt sự cố và cách giải quyết nhanh

| Hiện tượng | Nguyên nhân khả dĩ | Cách tiếp cận |
| --- | --- | --- |
| Reader tự viết luôn đọc lại từ đầu | Chỉ triển khai `ItemReader`; index trong RAM | Dùng `ItemStreamReader` và checkpoint trong `ExecutionContext` |
| `FlatFileItemReader` không tiếp tục từ mốc cũ | `saveState(false)` hoặc reader name/context khác | Kiểm tra `saveState(true)`, `name`, state đã commit |
| Có `@StepScope` vẫn replay | Scope không phải state persistence | Kết hợp scope với reader có `ItemStream` |
| Stream delegate không được `open/update` | Wrapper không đăng ký delegate | `.stream(delegate)` hoặc wrapper chuyển tiếp lifecycle |
| `JdbcPagingItemReader` trùng/bỏ record | Sort key không duy nhất hoặc dữ liệu nguồn đổi | Sort key ổn định duy nhất, snapshot/process indicator |
| Job restart nhưng toàn bộ step không chạy | Step đã `COMPLETED`, được skip theo quy tắc restart | Xác nhận status và ý đồ thiết kế, đừng ép chạy lại |
| Job không cho restart | `preventRestart` hoặc trạng thái repository ngăn restart | Phân biệt chính sách job với khả năng reader |
| Checkpoint có nhưng duplicate vẫn xuất hiện | Chunk trước chưa commit hoặc writer ngoài transaction | Idempotent writer, đối soát side effect |
| Reader hỏng khi chạy song song | State shared giữa threads, checkpoint không biểu diễn tiến độ | Partition, process indicator hoặc đọc tuần tự |
| API input chỉ stream một lần | Token/offset không bền vững | Staging, durable cursor, event replay hoặc inbox |
| Restart đọc khác dữ liệu trước | File bị thay, SQL không ổn định | Source version/checksum, snapshot |
| `STARTED` nhưng process đã chết | Metadata chưa ghi status cuối | Xác minh liveness, dùng runbook recovery, không sửa SQL tùy tiện |

## 18. Tài liệu tham khảo

Những ví dụ Java trên dùng package của **Spring Batch 5.2.x**, ví dụ `org.springframework.batch.item.ItemStreamReader`, `ExecutionContext` và `org.springframework.batch.item.file.FlatFileItemReader`. Với Spring Batch 6.x, nhiều API của hạ tầng item nằm trong package `org.springframework.batch.infrastructure.item`; cần chỉnh theo dependency thực tế khi triển khai. Các liên kết chính thức:

- [Spring Batch 5.2 — ItemStream, ExecutionContext và restart](https://docs.spring.io/spring-batch/reference/5.2/readers-and-writers/item-stream.html)
- [Spring Batch 5.2 — Creating custom ItemReaders](https://docs.spring.io/spring-batch/reference/5.2/readers-and-writers/custom.html)
- [Spring Batch 5.2 — Registering ItemStream with a Step](https://docs.spring.io/spring-batch/reference/5.2/step/chunk-oriented-processing/registering-item-streams.html)
- [Spring Batch 5.2 — Preventing State Persistence (process indicator)](https://docs.spring.io/spring-batch/reference/5.2/readers-and-writers/process-indicator.html)
- [Spring Batch 5.2 — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/5.2/scalability.html)
- [Spring Batch 5.2 — ItemReader/Writer Implementations và SynchronizedItemStreamReader](https://docs.spring.io/spring-batch/reference/5.2/readers-and-writers/item-reader-writer-implementations.html)
- [Spring Batch 5.2 API — FlatFileItemReaderBuilder](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/item/file/builder/FlatFileItemReaderBuilder.html)
- [Spring Batch 5.2 API — ItemStream](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/item/ItemStream.html)
- [Spring Batch 5.2 API — SynchronizedItemStreamReader](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/item/support/SynchronizedItemStreamReader.html)

Điểm mấu chốt: **restartable job chỉ có giá trị khi từng thành phần stateful có chiến lược phục hồi đúng**. Với reader tuần tự và nguồn bất biến, dùng `ItemStream` để lưu checkpoint ở `ExecutionContext` và để framework quản lý cập nhật cùng commit. Với nguồn không replay được hoặc xử lý song song, dùng process indicator, staging, partitioning và idempotency có chủ đích. Trước khi restart production, luôn đối chiếu **checkpoint đã lưu**, **dữ liệu nguồn** và **side effect đã commit**, bởi lỗi đọc lặp sau restart không chỉ làm chậm job mà còn có thể tạo sai lệch dữ liệu nghiệp vụ.
