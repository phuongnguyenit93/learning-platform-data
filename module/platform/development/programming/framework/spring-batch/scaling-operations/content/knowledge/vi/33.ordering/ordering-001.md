# Ordering trong một partition của Spring Batch

## 1. Đặt vấn đề: một partition có thật sự xử lý đúng thứ tự?

Trong Spring Batch, **partitioning** chia một tập dữ liệu lớn thành các phần việc độc lập để nhiều worker Step thực thi đồng thời. Đây là một cách mở rộng phù hợp với workload dữ liệu lớn, nhưng **chạy đúng tập bản ghi** và **xử lý đúng thứ tự** là hai yêu cầu khác nhau.

Ví dụ, mỗi tài khoản ngân hàng có chuỗi sự kiện:

~~~text
Tài khoản A: A#101 (+100) -> A#102 (-30) -> A#103 (+10)
Tài khoản B: B#201 (+50)  -> B#202 (-20)

Partition A: đọc và xử lý A#101 -> A#102 -> A#103
Partition B: đọc và xử lý B#201 -> B#202

Khi chạy song song, lịch thực thi có thể là:
A#101, B#201, B#202, A#102, A#103
~~~

Trình tự xen kẽ giữa A và B có thể chấp nhận được nếu nghiệp vụ chỉ yêu cầu **mỗi tài khoản xử lý theo thứ tự riêng**. Tuy nhiên, nếu A#103 được áp dụng trước A#102, kết quả trạng thái tài khoản có thể sai dù cuối cùng mọi sự kiện đều được ghi.

Trong module **SPRING_BATCH_SCALING_OPERATIONS**, nhu cầu giữ ordering phải được làm rõ trước khi chọn multi-threaded step, parallel steps, partitioning hoặc xử lý phân tán. Bài này tập trung vào câu hỏi:

> **Làm thế nào để bảo toàn một thứ tự nghiệp vụ được định nghĩa rõ ràng bên trong một partition, kể cả khi các partition khác chạy song song và Job phải retry/restart?**

Sau bài học, bạn sẽ biết cách:

- Phân biệt **thứ tự đọc**, **thứ tự gọi xử lý**, **thứ tự hoàn tất**, **thứ tự commit** và **thứ tự người tiêu thụ quan sát được**.
- Xác định phạm vi ordering cần bảo vệ: toàn Job, theo partition hay theo khóa nghiệp vụ.
- Thiết kế partition key, truy vấn có thứ tự xác định, worker Step và writer phù hợp.
- Nhận diện cấu hình khiến ordering bị mất, nhất là concurrency **bên trong** worker, xử lý bất đồng bộ, remote I/O và retry.
- Kiểm chứng ordering qua crash/restart, dữ liệu đến muộn, các partition chạy lệch tốc độ và việc tăng concurrency.

## 2. Định nghĩa chính xác điều được gọi là ordering

### 2.1. Năm loại thứ tự khác nhau

| Loại thứ tự | Ý nghĩa | Điều cần làm rõ |
|---|---|---|
| **Input order** | Bản ghi được reader trả về theo thứ tự nào | SQL có ORDER BY ổn định không; file có quy tắc đọc xác định không? |
| **Processing order** | Processor bắt đầu xử lý bản ghi theo thứ tự nào | Step có một luồng không; có async processor/executor không? |
| **Completion order** | Thao tác của mỗi item/chunk kết thúc theo thứ tự nào | Các tác vụ có độ trễ khác nhau có thể vượt nhau không? |
| **Commit order** | Transaction hoặc side effect được xác nhận bền vững theo thứ tự nào | Có nhiều transaction hoặc writer chạy đồng thời không? |
| **Observation order** | Downstream nhận/thấy kết quả theo thứ tự nào | DB query, message broker, API, file export có hợp đồng ordering riêng không? |

Năm khái niệm này không tương đương.

Giả sử một reader trả về các item **1, 2, 3** theo thứ tự. Nếu Step sử dụng TaskExecutor, việc xử lý 1 mất 300 ms, 2 mất 40 ms, 3 mất 10 ms, các item hoặc chunk có thể hoàn thành/commit không theo 1 → 2 → 3. Nếu writer dùng queue bất đồng bộ, ngay cả một Step gọi writer tuần tự cũng chưa chứng minh downstream nhận đúng thứ tự.

Mặt khác, **database quan hệ không có thứ tự hàng mặc định**. Việc INSERT theo 1 → 2 → 3 không khiến câu lệnh SELECT không có ORDER BY trả dữ liệu theo trình tự đó.

### 2.2. Chọn phạm vi ordering trước khi chọn kỹ thuật

| Phạm vi | Ví dụ | Giải pháp khởi điểm |
|---|---|---|
| Toàn Job | Mọi giao dịch phải phát ra theo một sequence toàn cục | Một luồng xuất tuần tự hoặc giai đoạn gom/sắp xếp/publish tuần tự |
| Theo partition | Trong một partition, bản ghi n phải được xử lý trước n+1 | Reader có thứ tự ổn định, worker tuần tự, writer đồng bộ |
| Theo khóa nghiệp vụ | Mọi sự kiện cùng accountId phải đúng sequence | Đưa toàn bộ một khóa vào cùng partition và xử lý tuần tự theo khóa |
| Theo cửa sổ thời gian | Bản ghi ngày trước phải hoàn tất trước ngày sau | Barrier/checkpoint giữa các window hoặc stage xử lý |
| Không bắt buộc | Biến đổi ảnh/file độc lập, kết quả không phụ thuộc lịch chạy | Có thể dùng concurrency mạnh hơn nếu tính đúng đắn cho phép |

**Ordering trong partition** không hàm ý ordering **giữa các partition**. Nếu cùng một khóa nghiệp vụ được chia ra hai partition chạy đồng thời, mỗi partition có thể giữ thứ tự nội bộ hoàn hảo nhưng chuỗi sự kiện chung của khóa đó vẫn sai.

### 2.3. Hai tính chất cần tách biệt

- **Deterministic input:** Với cùng snapshot dữ liệu và cùng điều kiện lọc, reader luôn tạo cùng một thứ tự item.
- **Ordered side effects:** Các thay đổi nghiệp vụ mà downstream ghi nhận phải tuân theo quan hệ trước–sau đã định nghĩa.

Deterministic input là **điều kiện quan trọng nhưng chưa đủ** cho ordered side effects. Với nghiệp vụ yêu cầu “sự kiện k+1 chỉ áp dụng sau k”, phải thiết kế cả ranh giới ghi, commit, retry và quan sát kết quả.

## 3. Ordering ở các cấp thực thi Spring Batch

~~~mermaid
flowchart TB
    M[Manager Step] --> P[Partitioner]
    P --> A[Partition A - worker Step]
    P --> B[Partition B - worker Step]
    A --> A1[A#101]
    A1 --> A2[A#102]
    A2 --> A3[A#103]
    B --> B1[B#201]
    B1 --> B2[B#202]
    A3 --> F[Đối soát kết quả]
    B2 --> F
~~~

Sơ đồ thể hiện **thứ tự cần duy trì trong A và B**; hai nhánh không có ràng buộc trước–sau với nhau.

### 3.1. Partitioning khác multi-threaded step

Một manager Step có thể phân phát partition cho nhiều worker Step trong cùng JVM hoặc ở các tiến trình khác nhau. Theo cấu hình thông thường, mỗi worker Step chạy chuỗi read–process–write theo mô hình chunk trong một luồng của chính nó. Vì thế, **các worker khác nhau chạy song song không tự làm mất ordering trong từng worker tuần tự**.

Tuy nhiên, nếu lại gắn TaskExecutor vào worker Step, thêm async processor/writer, hoặc đưa lời gọi xử lý sang executor bên trong processor, **một partition cũng có thể bị xử lý đồng thời**. Không được dựa vào tên gọi “partition” để suy ra trình tự thực thi.

| Cách thực thi | Ordering trong một partition | Ordering giữa các partition |
|---|---|---|
| Worker Step tuần tự, reader có thứ tự xác định, writer đồng bộ | Có thể giữ được trong phạm vi transaction/side effect được kiểm soát | Không bảo đảm |
| Local partitioning, mỗi worker Step tuần tự | Có thể giữ được trên từng partition | Không bảo đảm |
| Remote partitioning, mỗi worker Step tuần tự | Có thể giữ được nếu worker/broker/side effect có hợp đồng phù hợp | Không bảo đảm |
| Worker Step có TaskExecutor xử lý nhiều chunk | Không được mặc định bảo đảm | Không bảo đảm |
| Async processor/remote I/O không giữ thứ tự hoàn tất | Có thể đảo thứ tự hoàn tất hoặc side effect | Không bảo đảm |
| Remote chunking | Phụ thuộc cách gửi, worker, tổng hợp kết quả và ghi | Không tự động bảo đảm |

**Lưu ý:** Spring Batch quản lý JobExecution/StepExecution và checkpoint; điều đó không tương đương với một cam kết ordering của tất cả ItemReader/ItemWriter, queue hoặc hệ thống downstream.

### 3.2. Thứ tự item và ranh giới chunk

Trong một **chunk-oriented Step tuần tự**, reader lấy item và processor được gọi trong vòng xử lý theo thứ tự đọc. Writer nhận một **Chunk** các item chưa bị filter. Nếu writer lặp tuần tự trên chunk và hoàn thành đồng bộ, các thao tác do writer gọi có thứ tự trong phạm vi đó.

Tuy vậy:

1. Processor có thể lọc item bằng cách trả về null; chuỗi item ghi ra sẽ **không còn đủ phần tử**, dù thứ tự tương đối của các item còn lại vẫn có thể giữ.
2. Retry hoặc rollback có thể khiến một item/chunk được **gọi lại**. Chuỗi *lần thử* không còn đơn giản là 1, 2, 3; dữ liệu **commit cuối cùng** mới là điều nghiệp vụ cần đối soát.
3. Writer có thể phát các request song song hoặc return trước khi side effect hoàn tất; khi đó trình tự gọi writer không chứng minh trình tự ghi nhận của hệ thống ngoài.
4. Nếu reader đọc dữ liệu có thể thay đổi khi restart, việc lưu checkpoint đơn thuần không chứng minh thứ tự không bị thay đổi.

Ví dụ minh họa (các transaction được commit tuần tự; không có retry):

~~~text
Chunk 1: đọc [1,2,3] -> xử lý [1,2,3] -> writer [1,2,3] -> COMMIT
Chunk 2: đọc [4,5,6] -> xử lý [4,5,6] -> writer [4,5,6] -> COMMIT
~~~

Nếu một async writer gửi 1, 2, 3 tới ba API request đồng thời, response có thể về theo **3, 1, 2**. Bản thân giao diện ItemWriter không bảo đảm API ngoài áp dụng tác dụng phụ theo thứ tự.

## 4. Thiết kế partition key phù hợp với thứ tự nghiệp vụ

### 4.1. Gắn tất cả sự kiện của một khóa vào cùng partition

Giả sử nghiệp vụ yêu cầu mỗi **accountId** được cập nhật theo **sequenceNo** tăng dần. Cách đơn giản và dễ kiểm chứng là phân vùng theo accountId (hoặc hash của accountId):

~~~text
Partition 0: accountId {A, D, G, ...}
Partition 1: accountId {B, E, H, ...}
Partition 2: accountId {C, F, I, ...}
~~~

Với mỗi tài khoản, chỉ **một partition** xử lý mọi sự kiện của nó trong một Job. Nếu một worker đồng thời xử lý nhiều account, reader cần một quy tắc ổn định để nhóm và sắp xếp theo account, ví dụ:

~~~sql
SELECT account_id, sequence_no, event_id, amount_delta
FROM account_events
WHERE partition_bucket = :bucket
  AND sequence_no <= :snapshot_sequence_limit
ORDER BY account_id ASC, sequence_no ASC, event_id ASC;
~~~

Câu SQL chỉ minh họa cách sắp xếp. Điều kiện **snapshot_sequence_limit** phải tương thích với quy tắc đánh số của dữ liệu (giới hạn toàn cục hay theo tài khoản); không sử dụng một số giới hạn toàn cục nếu sequence chỉ có ý nghĩa riêng trong từng account mà không định nghĩa cách chốt watermark. Nếu thiết kế dữ liệu không có partition_bucket, có thể dùng một biểu thức hash phù hợp và bảo đảm query/index đủ hiệu quả.

**Phân vùng theo accountId giữ cùng khóa trong một partition**, nhưng nếu chỉ một partition có hàng triệu sự kiện của account A, A có thể thành straggler. Khi đó có hai lựa chọn kiến trúc:

- Giữ thứ tự chặt của account A và chấp nhận A là một nhánh tuần tự có giới hạn throughput.
- Phân tách A thành nhiều giai đoạn có barrier hoặc dùng cách xử lý không phụ thuộc thứ tự được nghiệp vụ chứng minh; đổi cách chia một cách có kiểm soát.

Không thể đồng thời yêu cầu mọi sự kiện của một account phải áp dụng tuần tự tuyệt đối và mong các sự kiện phụ thuộc nhau được xử lý hoàn toàn độc lập trên nhiều worker mà không có cơ chế phối hợp.

### 4.2. Chia theo dải sequence: phải nhìn cả ranh giới partition

Giả sử một account bị chia như sau:

~~~text
Partition P0: A#1 ... A#100
Partition P1: A#101 ... A#200
~~~

Dù P0 xử lý 1 → 100 và P1 xử lý 101 → 200, P1 có thể commit A#101 trước khi P0 hoàn tất A#100. Đó là **vi phạm ordering theo account trên toàn bộ Job**, nhưng **không vi phạm ordering nội bộ P0 hay P1**.

Nếu nghiệp vụ cần A#100 hoàn tất trước A#101, phải thêm **barrier** giữa các dải, phối hợp consumer theo sequence hoặc thay đổi cách chia. Nếu chỉ cần tổng hợp giao hoán (ví dụ SUM các delta và có thể chứng minh không phát sinh side effect phụ thuộc thứ tự), có thể nới hợp đồng ordering để lấy hiệu quả parallelism.

### 4.3. Kích thước partition không đồng nghĩa mức concurrency

Số partition là số phần việc logic; concurrency là số phần được xử lý đồng thời. Có thể tạo 64 partition nhưng chỉ 8 worker chạy cùng lúc. Tăng số worker có thể đổi thời gian hoàn tất **giữa** các partition; điều đó không nên làm đổi thứ tự **trong** từng partition nếu thiết kế tuần tự và checkpoint ổn định.

Tại bước phân tích tài nguyên, nên đo throughput/partition, thời gian của partition chậm nhất, CPU, connection pool, database lock wait và retry. Tăng worker không giải quyết được ordering sai do partition key hoặc reader không có ORDER BY.

## 5. Reader: tạo ra thứ tự đầu vào xác định

### 5.1. Không có ORDER BY, không có thứ tự SQL được bảo đảm

Sai lầm phổ biến:

~~~sql
-- Không có bảo đảm rằng dữ liệu trả về theo khóa chính.
SELECT account_id, sequence_no, amount_delta
FROM account_events
WHERE account_id = :accountId;
~~~

Một index, execution plan hay lần chạy thử có thể vô tình trả đúng thứ tự. Điều đó không cấu thành hợp đồng SQL.

Nếu sequence_no **duy nhất trong từng account và không bị sửa**, có thể dùng:

~~~sql
SELECT account_id, sequence_no, event_id, amount_delta
FROM account_events
WHERE account_id = :accountId
  AND sequence_no <= :cutoffSequence
ORDER BY sequence_no ASC;
~~~

Tại tầng dữ liệu, nên có ràng buộc và index phù hợp, ví dụ PostgreSQL:

~~~sql
ALTER TABLE account_events
ADD CONSTRAINT uq_account_sequence
UNIQUE (account_id, sequence_no);

CREATE INDEX idx_account_events_order
ON account_events (account_id, sequence_no);
~~~

Trong thực tế, PostgreSQL có thể đã sử dụng index tạo bởi ràng buộc UNIQUE cho truy vấn này; **không tự tạo index trùng lặp** nếu query plan xác nhận không cần. Hai câu SQL minh họa các ý tưởng độc lập; việc thêm index riêng cần đánh giá trên schema thật.

Nếu sort theo timestamp **không duy nhất**, cần tie-breaker ổn định:

~~~sql
ORDER BY event_time ASC, event_id ASC;
~~~

Timestamp không tự nói lên quan hệ nhân quả của nghiệp vụ. Nếu hai sự kiện cùng thời gian nhưng cần thứ tự nhân quả xác định, dùng sequence/counter do nguồn phát hành theo hợp đồng phù hợp, không tùy tiện suy ra thứ tự từ event_id.

### 5.2. Paging, cursor và restart

| Reader/nguồn | Điều cần kiểm tra khi muốn giữ ordering |
|---|---|
| JdbcCursorItemReader | SQL có ORDER BY, dữ liệu nguồn ổn định, cursor/connection phù hợp, ItemStream checkpoint đúng |
| JdbcPagingItemReader | Sort key ổn định và duy nhất, query không đổi tập dữ liệu trong lúc paging/restart |
| Repository/API pagination | Contract của API về sort/page/cursor; chống trùng hoặc thiếu khi dữ liệu chèn mới |
| FlatFileItemReader | Thứ tự dòng cố định của phiên bản file; file không bị sửa/ghi thay giữa các lần chạy |
| Kafka/JMS/queue | Contract ordering theo partition/session và xử lý theo consumer; retry/redelivery có thể ảnh hưởng |
| Reader tự viết | Kết quả deterministic, khả năng đọc tiếp, checkpoint và ranh giới partition được kiểm thử |

Với **offset pagination** trên bảng đang thêm/xóa bản ghi, các trang có thể lặp hoặc bỏ sót phần tử dù có ORDER BY. Với **keyset pagination** theo khóa ổn định, truy vấn thường có dạng:

~~~sql
SELECT account_id, sequence_no, event_id, amount_delta
FROM account_events
WHERE account_id = :accountId
  AND sequence_no > :lastSequenceNo
  AND sequence_no <= :cutoffSequence
ORDER BY sequence_no ASC
LIMIT :pageSize;
~~~

Biến **lastSequenceNo** ở đây là mốc đã hoàn thành theo chính sách checkpoint, không phải một con số chỉ nằm trong RAM worker. Khi đọc lại sau crash, chỉ cập nhật checkpoint cho phần công việc đã commit an toàn. Nếu JobRepository và database nghiệp vụ khác transaction resource, phải kết hợp idempotent write và đối soát để xử lý cửa sổ **đã ghi nhưng chưa lưu checkpoint**.

Tham số **cutoffSequence** phải được chốt và duy trì qua restart. Nếu dữ liệu có thể bị sửa hoặc xóa ở phần đã đọc, một cutoff đơn lẻ chưa tạo ra snapshot bất biến; cần database snapshot, materialized workset, immutable event log hoặc cơ chế nhất quán tương đương.

### 5.3. Ví dụ reader StepScope theo partition account

Ví dụ minh họa theo API Spring Batch 5, giả định bản ghi sự kiện bất biến, sequence tăng và duy nhất cho account, partition context đã có **accountId** và **cutoffSequence**:

~~~java
import javax.sql.DataSource;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.database.JdbcCursorItemReader;
import org.springframework.batch.item.database.builder.JdbcCursorItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;

public record AccountEvent(
        String accountId,
        long sequenceNo,
        long eventId,
        long amountDelta) {}

@Bean
@StepScope
public JdbcCursorItemReader<AccountEvent> accountEventReader(
        DataSource sourceDataSource,
        @Value("#{stepExecutionContext['accountId']}") String accountId,
        @Value("#{stepExecutionContext['cutoffSequence']}") Long cutoffSequence) {

    return new JdbcCursorItemReaderBuilder<AccountEvent>()
        .name("accountEventReader")
        .dataSource(sourceDataSource)
        .sql("""
            SELECT account_id, sequence_no, event_id, amount_delta
            FROM account_events
            WHERE account_id = ?
              AND sequence_no <= ?
            ORDER BY sequence_no ASC
            """)
        .preparedStatementSetter(ps -> {
            ps.setString(1, accountId);
            ps.setLong(2, cutoffSequence);
        })
        .rowMapper((rs, rowNum) -> new AccountEvent(
            rs.getString("account_id"),
            rs.getLong("sequence_no"),
            rs.getLong("event_id"),
            rs.getLong("amount_delta")))
        .fetchSize(500)
        .saveState(true)
        .build();
}
~~~

**Điều kiện của ví dụ:**

1. Mỗi StepExecution có reader StepScope riêng. Không dùng chung một cursor stateful giữa các partition.
2. Cấu hình worker Step đọc/xử lý/ghi **tuần tự**, không thêm TaskExecutor vào worker.
3. Dải sự kiện của account và cutoff phải ổn định; nếu account có cùng lúc nhiều partition thì ordering theo toàn account cần phối hợp bổ sung.
4. saveState(true) hỗ trợ reader lưu trạng thái qua ItemStream, **không** tự bảo đảm checkpoint cùng transaction với mọi side effect ở hệ thống khác.
5. Mã là phần cấu hình mẫu; cần khai báo package/class, datasource, Step/Job và writer phù hợp phiên bản thực tế.

## 6. Processor và writer: chỗ thường làm mất ordering

### 6.1. Processor thuần, xử lý đồng bộ

Đối với item độc lập, processor thuần chỉ biến đổi dữ liệu đầu vào, không giữ state mutable dùng chung:

~~~java
public record PreparedEvent(
        String accountId,
        long sequenceNo,
        long eventId,
        long deltaCents) {}

public class EventProcessor
        implements org.springframework.batch.item.ItemProcessor<AccountEvent, PreparedEvent> {

    @Override
    public PreparedEvent process(AccountEvent event) {
        return new PreparedEvent(
            event.accountId(),
            event.sequenceNo(),
            event.eventId(),
            event.amountDelta());
    }
}
~~~

Processor thuần giúp giảm khó khăn về thread safety và restart, nhưng **không đủ** để bảo đảm side effect đúng thứ tự nếu writer hoặc downstream làm việc bất đồng bộ.

Nếu processor phải gọi API ở mỗi item, cần hỏi: API chỉ tra cứu dữ liệu (read-only), hay thực hiện hành động nghiệp vụ? Nếu API có side effect, xảy ra timeout sau khi phía server đã áp dụng hành động thì retry có thể làm lặp. Đánh giá idempotency key, sequence guard hoặc outbox, tùy hợp đồng API.

### 6.2. Writer đồng bộ theo thứ tự chunk

Một writer đồng bộ có thể duyệt phần tử theo thứ tự nhận được:

~~~java
import org.springframework.batch.item.Chunk;
import org.springframework.batch.item.ItemWriter;

public final class OrderedWriter implements ItemWriter<PreparedEvent> {

    private final EventRepository repository;

    public OrderedWriter(EventRepository repository) {
        this.repository = repository;
    }

    @Override
    public void write(Chunk<? extends PreparedEvent> chunk) {
        for (PreparedEvent event : chunk) {
            repository.applyInOrder(event);
        }
    }
}
~~~

**EventRepository** ở trên là hợp đồng nghiệp vụ minh họa, chưa phải một class sẵn có của Spring Batch. Để duy trì ordering thật sự, phương thức **applyInOrder** cần hoàn tất đồng bộ và ràng buộc thứ tự/transaction đúng cách; chỉ lặp một danh sách chưa đủ nếu repository tự tạo request bất đồng bộ.

Ngoài ra, writer được gọi sau khi processor đã loại các item null. Kiểm tra kỳ vọng nghiệp vụ với filtered item: nếu mỗi sequence bắt buộc được áp dụng, không thể bỏ qua một sự kiện rồi tiếp tục mà không có quy tắc rõ ràng.

### 6.3. Guard sequence ở đích: bảo vệ khỏi retry và vượt thứ tự

Khi thứ tự sự kiện ảnh hưởng kết quả nghiệp vụ, nên có **bất biến ở database đích**. Ví dụ bảng trạng thái tài khoản gồm account_id, balance_cents, last_sequence. Nếu sequence phải liền kề bắt đầu từ 1:

~~~sql
UPDATE account_state
SET balance_cents = balance_cents + :deltaCents,
    last_sequence = :sequenceNo
WHERE account_id = :accountId
  AND last_sequence = :sequenceNo - 1;
~~~

- **1 hàng được cập nhật:** sự kiện tiếp theo hợp lệ đã được áp dụng ở transaction hiện tại.
- **0 hàng được cập nhật:** có thể do duplicate, khoảng trống sequence, account chưa tồn tại hoặc tranh chấp. Không tự hiểu mọi trường hợp là thành công; phải truy vấn kiểm tra trạng thái và bảng idempotency để phân loại.
- Nếu sự kiện đã được commit ở một lần chạy trước, retry phải nhận ra **cùng event_id, cùng payload/version** đã được áp dụng, rồi xác nhận an toàn; không cộng delta thêm lần nữa.
- Nếu sự kiện có gap thực sự, cần dừng/chờ/đưa vào xử lý lỗi theo nghiệp vụ; không âm thầm bỏ qua rồi cập nhật last_sequence lên số lớn hơn.

Có thể thêm bảng **processed_events(account_id, event_id, payload_hash, sequence_no)** với unique constraint và ghi nhận trong **cùng transaction** với thay đổi state. Nếu dùng hai database hoặc gọi API ngoài thì cần cơ chế idempotency/đối soát riêng; không suy ra tính nguyên tử xuyên hệ thống.

Guard ở đích rất hữu ích vì ngay cả khi cấu hình application bị thay đổi (thêm worker không đúng, message bị redeliver), database sẽ từ chối việc áp dụng sai chuỗi thay vì tạo kết quả sai im lặng.

### 6.4. Thứ tự ghi và thứ tự đọc lại

Dù writer commit sự kiện 1 trước 2, bên tiêu thụ phải query với ORDER BY khi cần hiển thị đúng thứ tự:

~~~sql
SELECT account_id, sequence_no, amount_delta
FROM account_event_projection
WHERE account_id = :accountId
ORDER BY sequence_no ASC;
~~~

Không dùng thứ tự vật lý của table, thứ tự auto-increment của transaction khác, thời điểm log xuất hiện hoặc thời điểm nhận response mạng làm chuẩn ordering nghiệp vụ khi chúng không được thiết kế để phản ánh quan hệ nhân quả.

## 7. Một worker Step tuần tự có đủ không?

Câu trả lời phụ thuộc **hợp đồng cần bảo vệ**. Để bảo toàn input order và xử lý đồng bộ trong một partition, những điều kiện sau thường cần đồng thời đúng:

1. Reader có thứ tự **xác định và ổn định**.
2. Partition key phù hợp: các item có quan hệ phụ thuộc ordering nằm trong cùng partition hoặc có barrier đã định nghĩa.
3. Worker Step không xử lý nhiều item/chunk cạnh tranh nhau khi nghiệp vụ yêu cầu thứ tự nghiêm ngặt.
4. Processor không tạo side effect bất đồng bộ gây vượt thứ tự.
5. Writer và hệ thống đích xác nhận thao tác đồng bộ theo thứ tự cần thiết; transaction và checkpoint được hiểu đúng.
6. Retry/restart có thể gặp xử lý lại nhưng không gây duplicate hoặc vượt sequence.
7. Consumer có quy tắc đọc/publish theo sequence nếu thứ tự quan sát cũng thuộc SLA.

Một Step tuần tự làm điều kiện 3 dễ đạt, nhưng không tự chứng minh 1, 2, 4, 5, 6 hoặc 7.

### 7.1. Cấu hình worker Step khởi điểm

Dùng worker Step theo kiểu chunk đơn luồng để giảm số yếu tố không xác định:

~~~java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemWriter;
import org.springframework.transaction.PlatformTransactionManager;

@Bean
public Step orderedWorkerStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<AccountEvent> reader,
        ItemProcessor<AccountEvent, PreparedEvent> processor,
        ItemWriter<PreparedEvent> writer) {

    return new StepBuilder("orderedWorkerStep", jobRepository)
        .<AccountEvent, PreparedEvent>chunk(200, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .build();
}
~~~

Không có cấu hình TaskExecutor **bên trong** Step này. Manager vẫn có thể phân phát nhiều partition để các worker Step khác nhau chạy đồng thời.

Số **200 item/chunk** chỉ là ví dụ. Chunk quá nhỏ tăng commit overhead; chunk quá lớn giữ transaction lâu, tăng thời gian rollback và trì hoãn checkpoint. Nếu cần người tiêu thụ thấy **từng sự kiện** ngay sau khi áp dụng, commit theo chunk sẽ khiến họ thấy cả một nhóm cùng lúc; cần đánh giá lại hợp đồng visibility, không tự cho rằng mỗi item được công bố ngay khi processor xử lý xong.

### 7.2. Khi phải dùng concurrency bên trong một partition

Nếu nhu cầu throughput buộc xử lý nhiều item trong cùng partition đồng thời, cần xác định bước nào có thể song song:

- **Xử lý thuần, độc lập:** có thể tính toán trước song song, sau đó gom kết quả về một điểm xuất **theo sequence**.
- **Ghi phụ thuộc thứ tự:** vẫn phải đi qua bộ phận áp dụng tuần tự hoặc sequence guard/ordered commit được kiểm chứng.
- **Nhiều khóa độc lập trong một partition:** có thể tách tuyến theo key, mỗi key một hàng xử lý tuần tự; tuy vậy phải giới hạn số queue và xác định restart/checkpoint từng key.
- **Phần công việc giao hoán:** nếu nghiệp vụ chứng minh phép toán không phụ thuộc thứ tự, có thể bỏ yêu cầu ordering ở phần đó và tổng hợp sau.

Ví dụ, ba item cần tính toán CPU mất [300, 40, 10] ms. Các phép biến đổi có thể hoàn tất theo [3, 2, 1], nhưng bộ gom **reorder buffer** phải chờ 1 để xuất [1, 2, 3]. Điều này tạo **head-of-line blocking**, tốn RAM và cần cơ chế phục hồi kết quả sau crash. Không sử dụng bộ nhớ reorder buffer làm kho checkpoint duy nhất.

## 8. Retry và restart: giữ thứ tự thực thi có ý nghĩa nghiệp vụ

### 8.1. Chỉ xét thứ tự gọi là không đủ

Xem chuỗi chunk sau:

~~~text
Chunk [10,11,12]
  attempt 1:
    apply 10 -> apply 11 -> apply 12 -> lỗi tại commit/ack
  rollback, hoặc trạng thái commit không rõ vì có nhiều hệ thống
  attempt 2:
    apply 10 -> apply 11 -> apply 12
~~~

Ở tầng application, item có thể được gọi hai lần. Nếu transaction hoàn toàn rollback ở hệ thống đích, có thể thực thi lại an toàn. Nhưng nếu các side effect đã được một API/DB khác commit, lần thử thứ hai có thể trùng dữ liệu hoặc ghi sai trật tự.

Phân biệt:

- **At-most-once attempt:** không lặp lời gọi; có thể mất sự kiện khi crash.
- **At-least-once execution:** có thể lặp, cần idempotency.
- **Exactly-once business effect:** mỗi sự kiện được áp dụng nghiệp vụ một lần về mặt kết quả cuối; cần chứng minh bằng transaction/dedupe/guard, không suy ra từ số lần reader phát item.

Đây là các khái niệm về hành vi hệ thống, **không phải chế độ tự động** chỉ cần bật một cờ trong Spring Batch.

### 8.2. Cửa sổ lỗi và hướng xử lý

| Lỗi | Rủi ro về ordering | Kiểm soát cần có |
|---|---|---|
| Worker chết trước commit chunk | Chunk được xử lý lại; khả năng lặp lần gọi | Transaction rollback và checkpoint đúng |
| Đích đã commit nhưng checkpoint JobRepository chưa cập nhật | Replay cùng item; trùng side effect | Idempotency key/sequence guard, đối soát |
| Async API nhận item k+1 trước k | Thứ tự hiệu ứng bị đảo | Gửi tuần tự/ordered consumer hoặc sequence guard ở đích |
| Retry k trong khi k+1 vẫn chạy | Ghi k+1 quá sớm | Không cho vượt k trong đường ghi bắt buộc tuần tự |
| Đọc lại với dữ liệu đã bị chèn/sửa | Sequence item khác trước crash | Snapshot cố định hoặc workset bất biến |
| Partition được gán lại khi worker cũ chưa dừng hẳn | Hai worker cùng ghi một key | Ownership/lease/fencing phù hợp; kiểm tra guard transaction |
| Manager chết nhưng worker vẫn còn chạy | Trạng thái COMPLETED/FAILED khó đồng bộ | JobRepository, reconciliation, quy trình restart có điều kiện |

**Restartability** không tự bảo đảm ordering ở đích. Tính đúng đắn sau restart cần dựa vào điều kiện đầu vào không đổi và side effect có thể nhận diện/khử trùng lặp.

### 8.3. Checkpoint phải gắn với tiến độ commit

Trong Spring Batch, StepExecution và ExecutionContext lưu thông tin tiến độ; các ItemStream hỗ trợ cơ chế checkpoint. Nhưng một **counter “đã đọc đến item 100”** chỉ có ý nghĩa nếu hệ thống có thể xác nhận những item đến 100 đã hoàn tất theo hợp đồng cần thiết.

Với database đích riêng JobRepository, kiểm tra cửa sổ:

~~~text
1. Writer commit A#100 ở database nghiệp vụ.
2. Tiến trình chết trước khi checkpoint tương ứng được lưu.
3. Worker mới đọc lại A#100.
4. Writer nhận diện A#100 đã áp dụng và không cộng delta lần thứ hai.
5. Sau đó mới tiếp tục A#101.
~~~

Nếu bước 4 chỉ kiểm tra **sequenceNo <= last_sequence** rồi bỏ qua vô điều kiện, một sự kiện lỗi có cùng sequence nhưng payload khác cũng có thể bị bỏ qua. Cần đối chiếu khóa/id và nội dung đã được áp dụng để tránh che giấu xung đột dữ liệu.

### 8.4. Chính sách skip/filter phải hợp lệ với thứ tự

Nếu dữ liệu nghiệp vụ bắt buộc đủ sequence 1, 2, 3, việc skip 2 rồi áp dụng 3 có thể vi phạm invariant. Cần phân loại:

- Item không ảnh hưởng trạng thái và được phép filter: có thể giữ thứ tự tương đối của các item còn lại.
- Item có sequence bắt buộc dù nghiệp vụ là no-op: vẫn cần đánh dấu sequence đã xử lý theo hợp đồng.
- Item lỗi vĩnh viễn: fail partition, đưa vào hàng chờ sửa/đối soát, hoặc có quy tắc nghiệp vụ rõ ràng về việc bỏ qua và nối tiếp.

Không nên bật skip không giới hạn chỉ để Job hoàn thành; trạng thái COMPLETED khi bỏ một sự kiện bắt buộc vẫn có thể là dữ liệu sai.

## 9. Quan sát ordering trong production

### 9.1. Chỉ số kỹ thuật và bất biến nghiệp vụ

Đo cả hiệu năng và độ đúng:

| Nhóm | Metric/kiểm tra | Ý nghĩa |
|---|---|---|
| Execution | Job/Step duration, read/write/filter/skip/rollback count | Xác định điều kiện tải, retry và lỗi |
| Partition | partitionName, workerId, start/end, records/sec | Tìm straggler và concurrency ngoài ý muốn |
| Sequence | lastAppliedSequence theo key, số gap/duplicate/out-of-order | Phát hiện vi phạm thứ tự nghiệp vụ |
| Writer | transaction duration, commit p95/p99, lock waits, retry | Xác định nghẽn của đường ghi tuần tự |
| Downstream | publish lag, receive sequence, consumer offset/ack | Phân biệt thứ tự commit và thứ tự quan sát |
| Resource | CPU, GC, DB connection pending, queue depth | Đánh giá giới hạn khi tăng worker |

Các metric chứa accountId, eventId, partitionName động có thể tạo **cardinality rất cao**. Dùng log/trace cho ID cụ thể, metric tổng hợp theo loại lỗi/Step hoặc nhóm hữu hạn, và dashboard truy vấn dữ liệu nghiệp vụ khi cần điều tra sâu.

### 9.2. Log có cấu trúc

Ví dụ mỗi lần commit chunk có thể phát một bản ghi:

~~~text
jobExecutionId=317
stepExecutionId=992
partitionName=account-A
workerInstance=worker-03
firstSequence=101
lastSequence=200
writtenCount=100
commitStatus=success
durationMs=475
~~~

Nếu có lỗi, log thêm **expectedSequence**, **actualSequence**, **eventId**, loại exception và tính chất retryable. Không ghi dữ liệu nhạy cảm, payload hoặc secret không cần thiết. Log là bằng chứng điều tra, **không thay thế** kho bền vững lưu tiến độ.

### 9.3. Dấu hiệu cần xử lý ngay

- **lastAppliedSequence** của một account nhảy từ 100 lên 102 khi hợp đồng yêu cầu không có gap.
- Số sự kiện “out of order” tăng ngay sau khi thêm TaskExecutor/async API.
- Retry tăng ở những sequence đã commit, kèm duplicate hoặc deadlock.
- Một partition hoàn thành rất muộn do đầu chuỗi bị lỗi, dù nhiều worker khác đang rảnh.
- Data checksum cuối Job đúng nhưng hệ thống phát notification sai thứ tự; đây là dấu hiệu cần kiểm tra **side effect order**, không chỉ dữ liệu bảng đích.

## 10. Đánh đổi giữa ordering, throughput và kiến trúc scaling

~~~mermaid
flowchart TD
    R[Item trong partition có phụ thuộc thứ tự?] -->|Không| P[Có thể song song nếu idempotent và thread-safe]
    R -->|Có| S[Phạm vi bắt buộc theo key hay toàn Job?]
    S -->|Theo key| K[Giữ cùng key trong một partition]
    S -->|Toàn Job| G[Stage + sort + publish tuần tự / barrier]
    K --> T[Worker Step tuần tự hoặc ordered sink]
    G --> T
    T --> V[Đo throughput, DB/API bottleneck, retry/restart]
    V --> E[Kiểm chứng các invariant ordering]
~~~

| Cách xử lý | Lợi thế | Chi phí/rủi ro |
|---|---|---|
| Worker đơn luồng mỗi partition | Dễ hiểu, ít nguy cơ đảo thứ tự nội bộ | Một key nóng bị giới hạn throughput tuần tự |
| Nhiều partition, mỗi partition tuần tự | Scale theo số khóa độc lập, mỗi key giữ thứ tự | Data skew, thiếu ordering toàn Job |
| Async compute rồi reorder trước write | Tận dụng CPU cho phần tính độc lập | Buffer, head-of-line blocking, restart phức tạp |
| Sequence guard ở database | Chặn cập nhật sai khi retry/concurrency | Tranh chấp khóa theo key, thêm truy vấn/transaction |
| Staging tất cả kết quả rồi sort/publish | Tách tính toán song song và phát hành theo thứ tự | Tăng I/O, latency và chi phí staging |
| Một luồng toàn Job | Hợp đồng trình tự đơn giản nhất | Thường không tận dụng được tài nguyên phân tán |

Nếu phần lớn thời gian CPU nằm ở phép biến đổi item độc lập, có thể song song hóa **pha tính toán** và giữ **pha publish theo thứ tự**. Nếu bottleneck chính là ghi tuần tự của một tài khoản, số partition/pod cao hơn không thể loại bỏ phụ thuộc dữ liệu của tài khoản đó; cần xem lại yêu cầu nghiệp vụ hoặc mô hình lưu trữ.

**Ordering không đồng nghĩa thread safety.** Một reader/writer được đồng bộ để tránh data race vẫn có thể bị các chunk đến theo thứ tự khác. Tương tự, xử lý có ordering nhưng không idempotent vẫn có thể ghi hai lần khi retry.

## 11. Tình huống thực tế: sao chép event stream theo tài khoản

### 11.1. Yêu cầu

Hệ thống nhận 6 triệu event mỗi đêm, thuộc 100.000 tài khoản. Mỗi account có **sequenceNo tăng đơn điệu và không trùng**, số hiệu liên tiếp theo quy tắc nguồn; một số account có nhiều event hơn hẳn. Đích cần cập nhật account_state và phát một sự kiện xác nhận sau khi commit. SLA: Job hoàn tất trong 40 phút.

Thiết kế ban đầu:

~~~text
Nguồn account_events
      |
      v
Partitioner theo bucket hash ổn định của accountId
      |
      +---- Worker 1: account A, D, ...
      +---- Worker 2: account B, E, ...
      +---- Worker 3: account C, F, ...
      |
      v
Đích account_state + processed_events
      |
      v
Outbox -> publisher -> downstream consumer
~~~

Định nghĩa ordering:

- Trong **một account**, account_state phải được áp dụng theo sequenceNo tăng dần và không bỏ gap bắt buộc.
- Các account khác nhau **không** có ràng buộc thứ tự với nhau.
- Thay vì tạo 100.000 StepExecution cho 100.000 account, nên thử một số lượng bucket hợp lý theo tải và chi phí metadata; mọi event của một account phải vào cùng bucket, reader trong bucket sắp xếp theo accountId rồi sequenceNo. Giữ quy tắc bucket ổn định qua restart.
- Outbox ghi cùng transaction với state và idempotency record; publisher/consumer phải bảo vệ thứ tự theo account, ví dụ một tuyến queue/partition theo accountId với cơ chế tuần tự và handling retry phù hợp.
- Báo cáo cuối Job chỉ công bố khi mọi partition được kiểm tra và hoàn thành.

**Lưu ý:** Outbox tự nó giải quyết cửa sổ mất thông điệp giữa commit và gửi, nhưng **không tự bảo đảm ordering** nếu nhiều publisher cùng đọc các outbox row của một account rồi gửi song song. Cần thêm chính sách chọn/publish theo sequence và bảo vệ việc ack/retry.

### 11.2. Thí nghiệm xác minh

Chạy cùng snapshot dữ liệu, so sánh các cấu hình:

| Cấu hình | Giả thuyết | Điều cần kiểm tra |
|---|---|---|
| 1 partition active, worker tuần tự | Baseline dễ quan sát ordering | Sequence, throughput và p95 commit |
| 4 partition active, worker tuần tự | Scale khi các key độc lập | Không vi phạm per-key ordering |
| 16 partition active, worker tuần tự | Có thể nhanh hơn nếu DB còn dư năng lực | Lock wait, pool, GC, straggler |
| Thêm TaskExecutor vào mỗi worker | Throughput có thể tăng nhưng làm đảo commit | Test phải phát hiện hoặc DB guard từ chối out-of-order |
| Kill worker giữa chunk | Restart không làm sai thứ tự | Không mất, không trùng tác dụng phụ nghiệp vụ |
| Kill worker sau commit đích | Replay có thể xảy ra | Sequence guard/idempotency khử tác dụng phụ trùng |
| Dữ liệu nguồn bị sửa sau khi chốt cutoff | Thứ tự/tập dữ liệu có thể khác | Phải dùng snapshot/workset ổn định hoặc fail có kiểm soát |

Không lấy tổng row count trùng khớp làm điều kiện duy nhất để pass; tổng tiền, sequence cuối, processed_events, outbound event order và trạng thái cuối đều cần đối soát.

### 11.3. Bộ kiểm thử ordering tối thiểu

Với mỗi account trong tập kiểm thử, tạo chuỗi chuẩn:

~~~text
A: (seq=1, +100), (seq=2, -30), (seq=3, +20)
B: (seq=1, +50),  (seq=2, -10)
C: (seq=1, +5)
~~~

Kết quả mong đợi:

~~~text
A: lastSequence=3, balance=90
B: lastSequence=2, balance=40
C: lastSequence=1, balance=5
~~~

Ngoài kết quả cuối, phải kiểm tra log/audit hoặc bảng applied_events để xác minh A: **1 → 2 → 3** và B: **1 → 2** theo từng account.

Các ca lỗi bắt buộc:

1. **Tăng tốc không đều:** trì hoãn A#2 nhưng tăng tốc A#3; A#3 không được áp dụng trước khi A#2 hoàn tất.
2. **Retry cùng sự kiện:** gửi lại A#2 sau khi đã commit; số dư không được giảm thêm 30.
3. **Thiếu sequence:** loại A#2 khỏi snapshot; worker phải báo gap theo chính sách thay vì tự áp dụng A#3.
4. **Phát lại sau crash:** worker chết sau commit A#2 nhưng trước checkpoint; restart vẫn có A#1..3 đúng một hiệu ứng mỗi sự kiện.
5. **Nhiều worker cùng key:** cố tình tạo phân vùng chồng lấn A để bảo đảm cơ chế guard phát hiện và từ chối.
6. **Outbox publisher concurrency:** hai publisher cố lấy A#2 và A#3; consumer không được thấy trạng thái A#3 trước A#2 nếu hợp đồng yêu cầu.
7. **Dữ liệu đến muộn:** thêm một event có thời gian cũ nhưng sequence mới; xử lý theo định nghĩa canonical sequence, không tự chèn event vào giữa lịch sử đã commit.
8. **Thay đổi số worker:** so sánh 2 và 8 worker trên snapshot giống nhau; kết quả per-key sequence và bất biến nghiệp vụ không được thay đổi.

Mỗi bài kiểm thử cần kiểm tra hai loại kết quả: **state cuối** và **chuỗi hiệu ứng đã được ghi nhận**. Hai hệ thống có số dư cuối bằng nhau vẫn có thể khác về event order, thông báo đã gửi hoặc trạng thái trung gian mà nghiệp vụ quan tâm.

## 12. Checklist thiết kế trước khi triển khai

- [ ] Đã viết thành lời hợp đồng ordering: theo key, theo partition hay toàn Job.
- [ ] Partition key không cắt ngang chuỗi sự kiện có quan hệ trước–sau bắt buộc; nếu có thì đã bổ sung barrier/coordination.
- [ ] Reader dùng ORDER BY có khóa sort ổn định, duy nhất hoặc tie-breaker xác định.
- [ ] Đầu vào có snapshot/watermark/workset rõ ràng và không thay đổi ý nghĩa khi restart.
- [ ] Worker Step không thêm TaskExecutor/async side effect ngoài ý muốn.
- [ ] Reader/Writer stateful được khởi tạo theo StepExecution, không dùng chung mutable cursor/buffer.
- [ ] Writer có giao dịch và sequence/idempotency guard đúng nghiệp vụ.
- [ ] Retry, rollback, skip và restart đã được định nghĩa cho cả sự kiện bị lặp và bị thiếu.
- [ ] Hệ thống downstream được kiểm thử thứ tự quan sát, không chỉ thứ tự gọi writer.
- [ ] Có metric out-of-order, duplicate, gap, lag, rollback và p95 commit.
- [ ] Có kiểm thử tải với nhiều partition, key nóng và thay đổi số worker.
- [ ] Có kiểm thử crash trước/sau commit và chạy lại trên worker khác.

## 13. Tổng kết

**Ordering trong một partition** là một thuộc tính phải thiết kế ở **toàn bộ đường xử lý dữ liệu**, bắt đầu từ cách chia partition, truy vấn của reader, cấu hình concurrency của worker, processor/writer, commit, rồi đến checkpoint và downstream. Một worker Step tuần tự với reader có ORDER BY ổn định là điểm khởi đầu phù hợp, nhưng chưa đủ nếu side effect bất đồng bộ, retry không idempotent hoặc dữ liệu nguồn thay đổi khi restart.

Điểm quyết định là **ordering có phạm vi**: các partition khác nhau có thể xen kẽ bình thường, còn những bản ghi có phụ thuộc thứ tự phải được đưa vào cùng phạm vi được bảo vệ, hoặc có cơ chế phối hợp. Khi đã xác định rõ phạm vi này, ta mới chọn được mức song song thực tế, đo bottleneck và mở rộng Spring Batch mà vẫn giữ tính đúng đắn của Job.

**Tài liệu nên đối chiếu theo phiên bản sử dụng:** Spring Batch Reference Documentation về Scaling and Parallel Processing, Partitioning, Chunk-Oriented Processing, JobRepository/ExecutionContext, ItemStream, StepScope và Retry/Restart; tài liệu của ItemReader/ItemWriter đang dùng; tài liệu database về ORDER BY, isolation/transaction và tài liệu broker về ordering/redelivery. Cần kiểm tra API và guarantee cụ thể của phiên bản Spring Batch, Spring Boot và middleware trong dự án.
