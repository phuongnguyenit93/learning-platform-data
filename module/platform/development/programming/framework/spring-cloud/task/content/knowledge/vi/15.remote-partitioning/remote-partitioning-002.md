# Phân biệt remote partitioning và remote chunking

**Remote partitioning** và **remote chunking** là hai cách phân tán công việc của **Spring Batch** ra nhiều tiến trình (manager và worker), thường giao tiếp qua middleware như JMS hoặc AMQP. Cả hai giúp xử lý dữ liệu lớn, nhưng **đơn vị gửi đi, vị trí đọc dữ liệu và cách quản lý trạng thái hoàn toàn khác nhau**. Chọn nhầm kiến trúc có thể khiến manager quá tải, hàng đợi chứa payload khổng lồ hoặc quy trình khởi động lại sau lỗi trở nên khó kiểm soát.

Bài học thuộc chương **Phân vùng từ xa** của module **SPRING_CLOUD_TASK**. Spring Cloud Task phù hợp để chạy một ứng dụng hữu hạn, ghi `TaskExecution` vào `TaskRepository` và báo trạng thái/mã thoát cho bộ điều phối. Spring Batch thực hiện phần **chia công việc, đọc/ghi theo chunk và lưu `JobExecution`, `StepExecution` trong `JobRepository`**. Bài tập trung phân biệt remote partitioning và remote chunking, sau đó nối kiến trúc Batch với cách khởi chạy, theo dõi lỗi và vận hành an toàn của một Spring Cloud Task.

Sau khi học, bạn có thể giải thích vì sao một luồng nhập dữ liệu nên chia theo phạm vi ID hoặc theo các chunk item, xác định manager/worker cần những thành phần nào, lựa chọn thiết kế phù hợp với nút thắt hiệu năng và dự kiến hậu quả khi worker bị lỗi hoặc một message được gửi lại.

## 1. Bối cảnh: từ một Batch Step đến nhiều worker

Một Step xử lý theo chunk thường có luồng:

~~~text
ItemReader → ItemProcessor → ItemWriter
       (lặp theo các chunk, có transaction/checkpoint)
~~~

Ví dụ nhập 10 triệu đơn hàng: đọc bản ghi từ CSDL nguồn, kiểm tra, chuẩn hóa rồi ghi vào CSDL đích. Nếu một tiến trình xử lý không kịp cửa sổ vận hành, ta có thể tăng song song bằng cách mở nhiều worker. Spring Batch hỗ trợ nhiều mô hình: multi-threaded Step, parallel Step, local partitioning, remote partitioning và remote chunking.

**Remote** nghĩa là các phần xử lý được đặt ở **các tiến trình riêng**, thường trên nhiều Pod/VM; không phải chỉ tăng thread trong một JVM. Middleware chuyển yêu cầu và kết quả qua ranh giới mạng. Chi phí mới xuất hiện gồm truyền message, serialization, timeout, phối hợp trạng thái và quản lý lỗi.

| Tiêu chí ban đầu | Remote partitioning | Remote chunking |
| --- | --- | --- |
| Đơn vị phân công | **Partition**: một phạm vi dữ liệu, kèm `ExecutionContext` và `StepExecution` | **Chunk**: một nhóm item do manager đã đọc |
| Ai đọc dữ liệu nguồn? | **Worker**: mỗi worker có `ItemReader` của Step mình chạy | **Manager**: một `ItemReader` tạo các chunk |
| Ai process và write? | **Worker** chạy Step đầy đủ: reader, processor, writer | **Worker** xử lý và ghi các item đã nhận |
| Mục tiêu mở rộng nổi bật | Phân tán cả I/O đọc lẫn xử lý/ghi | Phân tán phần xử lý/ghi nặng trong khi đọc nhanh |
| Metadata điều phối | `JobRepository` có các `StepExecution` phân vùng | Manager quản lý Step/Job; worker nhận yêu cầu chunk |
| Payload gửi qua broker | Thường là **mô tả partition / ID StepExecution**, ít dữ liệu | **Dữ liệu các item trong chunk**, có thể lớn |
| Rủi ro cổ chai | Phân vùng lệch, CSDL chung quá tải, phân vùng quá lớn | Reader ở manager, throughput broker, serialization |
| Worker cần đọc chung dữ liệu nguồn? | **Có** quyền đọc được vùng được giao (trực tiếp hoặc object storage) | **Không nhất thiết**: item đã tới trong message |

Đừng kết luận “remote partitioning luôn nhanh hơn” hoặc “remote chunking luôn dễ hơn”. Hiệu quả phụ thuộc tỷ lệ thời gian **đọc — xử lý — ghi**, kích thước dữ liệu, độ lệch giữa các phân vùng và khả năng chịu tải của broker/CSDL.

## 2. Remote partitioning: giao một vùng dữ liệu cho một Step ở xa

Manager dùng **`Partitioner`** tách không gian đầu vào thành các partition, ví dụ theo dải ID đơn hàng, ngày nghiệp vụ, tenant hoặc danh sách file. Mỗi partition có tên ổn định như `partition0`, `partition1` và một `ExecutionContext` chứa tham số cần thiết.

Sau đó `PartitionStep` trên manager tạo các `StepExecution` tương ứng. Một `PartitionHandler` gửi yêu cầu đến worker. Worker nhận định danh StepExecution, lấy thông tin liên quan từ repository, tìm Step được cấu hình và **thực thi cả Step đó**.

~~~mermaid
flowchart LR
  subgraph Manager["Manager / Batch Job"]
    P["Partitioner<br/>chia ID hoặc file"] --> PS["PartitionStep<br/>tạo StepExecution"]
    PS --> PH["PartitionHandler"]
  end
  PH --> MQ[("Broker / middleware<br/>partition requests")]
  MQ --> W1["Worker A<br/>Reader → Processor → Writer"]
  MQ --> W2["Worker B<br/>Reader → Processor → Writer"]
  MQ --> W3["Worker C<br/>Reader → Processor → Writer"]
  W1 <--> JR[("JobRepository<br/>StepExecution + Context")]
  W2 <--> JR
  W3 <--> JR
  PS <--> JR
~~~

Ví dụ input có các ID trong đoạn `[1, 1_000_000]`:

| Partition | ExecutionContext | Worker đọc | Phạm vi xử lý |
| --- | --- | --- | --- |
| `partition0` | `minId=1, maxId=250000` | Worker A | `1 ≤ id ≤ 250000` |
| `partition1` | `minId=250001, maxId=500000` | Worker B | `250001 ≤ id ≤ 500000` |
| `partition2` | `minId=500001, maxId=750000` | Worker C | `500001 ≤ id ≤ 750000` |
| `partition3` | `minId=750001, maxId=1000000` | Worker có tài nguyên trống | `750001 ≤ id ≤ 1000000` |

**Không có hàng dữ liệu nào phải nằm trong message điều phối**. Worker tự dùng `minId`, `maxId` để đọc cơ sở dữ liệu. Điều này giảm payload mạng khi nguồn đã có thể được truy cập trực tiếp bởi worker.

### 2.1. Thành phần then chốt

| Thành phần | Trách nhiệm |
| --- | --- |
| `Partitioner` | Tạo map `partitionName → ExecutionContext` từ tập dữ liệu logic |
| `PartitionStep` / `StepExecutionSplitter` | Phân tách công việc thành các StepExecution có trạng thái độc lập |
| `PartitionHandler` | Phân phối yêu cầu thực thi các Step ở worker và tổng hợp trạng thái |
| `MessageChannelPartitionHandler` | Một triển khai dùng Spring Integration MessageChannel để giao tiếp từ xa |
| `StepExecutionRequestHandler` | Ở worker, xử lý yêu cầu và thực thi Step tương ứng |
| `JobRepository` / `JobExplorer` | Lưu và tra StepExecution, JobExecution, ExecutionContext, checkpoint |

**`TaskExecutorPartitionHandler`** chỉ chạy partition ở các thread cục bộ, rất hữu ích để thử cách chia dữ liệu. Để phân tán sang JVM/Pod khác, cần handler có khả năng **gửi yêu cầu qua middleware**, chẳng hạn `MessageChannelPartitionHandler`.

### 2.2. Ví dụ Partitioner theo dải ID

Đây là phần Java tự chứa minh họa **cách chia dữ liệu**, dùng API `Partitioner` của Spring Batch:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.item.ExecutionContext;

public class OrderIdRangePartitioner implements Partitioner {

    private final long firstId;
    private final long lastId;

    public OrderIdRangePartitioner(long firstId, long lastId) {
        if (firstId < 1 || lastId < firstId) {
            throw new IllegalArgumentException("Invalid ID range");
        }
        this.firstId = firstId;
        this.lastId = lastId;
    }

    @Override
    public Map<String, ExecutionContext> partition(int gridSize) {
        if (gridSize <= 0) {
            throw new IllegalArgumentException("gridSize must be positive");
        }

        long total = lastId - firstId + 1;
        long partitionSize = total / gridSize
                + (total % gridSize == 0 ? 0 : 1);

        Map<String, ExecutionContext> result = new LinkedHashMap<>();
        long start = firstId;
        int index = 0;

        while (start <= lastId) {
            long end = Math.min(lastId, start + partitionSize - 1);
            ExecutionContext context = new ExecutionContext();
            context.putLong("minId", start);
            context.putLong("maxId", end);
            result.put("partition" + index, context);
            start = end + 1;
            index++;
        }
        return result;
    }
}
~~~

**Đặc tính cần giữ:** các khoảng không chồng lấn, không bỏ sót vùng ID, tên partition ổn định giữa các lần restart. Ví dụ giả định miền ID hữu hạn và không tràn phép cộng kiểu `long`. Với dữ liệu phân bố lệch, phân chia đều theo **số ID** chưa chắc cho số bản ghi đồng đều; cần cân nhắc lượng dữ liệu thực tế.

Một worker có thể dùng **Step-scoped Reader** lấy hai đầu mút từ context:

~~~java
@Bean
@StepScope
public JdbcCursorItemReader<OrderRow> orderReader(
        DataSource sourceDataSource,
        @Value("#{stepExecutionContext['minId']}") Long minId,
        @Value("#{stepExecutionContext['maxId']}") Long maxId) {

    JdbcCursorItemReader<OrderRow> reader = new JdbcCursorItemReader<>();
    reader.setName("orderRangeReader");
    reader.setDataSource(sourceDataSource);
    reader.setSql("""
        SELECT id, amount
        FROM orders
        WHERE id >= ? AND id <= ?
        ORDER BY id
        """);
    reader.setPreparedStatementSetter(ps -> {
        ps.setLong(1, minId);
        ps.setLong(2, maxId);
    });
    reader.setRowMapper((rs, rowNum) ->
            new OrderRow(rs.getLong("id"), rs.getBigDecimal("amount")));
    return reader;
}

record OrderRow(long id, BigDecimal amount) {}
~~~

Ví dụ này dùng cú pháp **Spring Batch 5.x / Spring Boot 3.x**. Các import chính: `@Bean`, `@StepScope`, `@Value`, `DataSource`, `JdbcCursorItemReader`, `BigDecimal`. Cần thêm processor, writer, Step, transaction manager, cấu hình repository, broker và worker handler để có hệ thống chạy được. `JdbcCursorItemReader` ở đây đọc khoảng ID theo thứ tự tăng; ở môi trường thật, cần kiểm tra tính ổn định của dữ liệu nguồn và chính sách snapshot khi nguồn thay đổi trong lúc xử lý.

### 2.3. Cấu hình manager/worker ở mức cấu trúc

Ví dụ `PartitionStep` từ API Java Spring Batch 5.x:

~~~java
@Bean
Step managerStep(
        JobRepository repository,
        Partitioner partitioner,
        PartitionHandler remotePartitionHandler) {

    return new StepBuilder("orderManagerStep", repository)
            .partitioner("orderWorkerStep", partitioner)
            .partitionHandler(remotePartitionHandler)
            .build();
}
~~~

`remotePartitionHandler` phải được cấu hình để gửi yêu cầu thực thi **`orderWorkerStep`** qua broker. Với Spring Batch Integration, có thể dùng `@EnableBatchIntegration` và các factory/builder remote partitioning tương ứng với **phiên bản** đang dùng, hoặc cấu hình `MessageChannelPartitionHandler` trực tiếp.

Worker triển khai `orderWorkerStep` với `ItemReader`, `ItemProcessor` và `ItemWriter` của chính mình, đồng thời nhận request qua `StepExecutionRequestHandler`. Manager không cần chuyển toàn bộ hàng dữ liệu trong message, nhưng worker phải có **quyền truy cập nguồn dữ liệu** và **metadata repository phù hợp**.

## 3. Remote chunking: manager đọc, worker nhận các chunk

Với **remote chunking**, manager giữ **`ItemReader`**; mỗi lần đọc đủ `chunkSize` item, manager gửi **cả chunk đã đọc** qua middleware. Worker là consumer nhận message, dùng **`ItemProcessor` và `ItemWriter`** để xử lý/ghi rồi gửi phản hồi để manager tổng hợp kết quả.

~~~mermaid
flowchart LR
  subgraph Manager["Manager / Batch Step"]
    R["ItemReader"] --> CP["ChunkProvider"]
    CP --> CW["ChunkMessageChannelItemWriter"]
  end
  CW --> MQ[("Broker<br/>chunk payloads")]
  MQ --> W1["Worker A<br/>Processor → Writer"]
  MQ --> W2["Worker B<br/>Processor → Writer"]
  MQ --> W3["Worker C<br/>Processor → Writer"]
  W1 --> Dest[("CSDL / dịch vụ đích")]
  W2 --> Dest
  W3 --> Dest
  W1 -. "reply" .-> CW
  W2 -. "reply" .-> CW
  W3 -. "reply" .-> CW
~~~

Ví dụ manager đọc 1.000.000 đơn hàng với `chunkSize=200`. Nó tạo tối đa 5.000 yêu cầu chunk, mỗi yêu cầu mang tối đa 200 item (tùy số bản ghi cuối). Broker phân phối các yêu cầu tới những worker sẵn sàng; mỗi worker không phải truy vấn bảng nguồn để biết “mình được giao khoảng ID nào”.

### 3.1. Thành phần then chốt

| Thành phần | Trách nhiệm |
| --- | --- |
| `ItemReader` của manager | Đọc nguồn theo thứ tự ổn định, tạo item |
| `ChunkProvider` | Gom item thành chunk |
| `ChunkMessageChannelItemWriter` | Chuyển chunk thành request tới worker và nhận/tổng hợp reply |
| `ChunkProcessor` trên worker | Thực thi ItemProcessor/ItemWriter cho chunk nhận được |
| `ChunkProcessorChunkRequestHandler` | Chuyển message request thành thao tác xử lý chunk |
| `MessageChannel` / JMS / AMQP | Vận chuyển request/reply giữa tiến trình |

Trong mô hình chuẩn, worker remote chunking là **message consumer**, không nhất thiết là một Spring Batch Job/Step hoàn chỉnh. Theo hướng dẫn Spring Batch Integration, worker trong kiến trúc này **không bắt buộc truy cập `JobRepository` của manager** hoặc có nguyên cấu hình Job; nó cần xử lý payload, transaction nghiệp vụ và gửi reply phù hợp.

### 3.2. Khung Step tại manager

Ví dụ minh họa API Step Spring Batch 5.x. Phần `outboundChunkWriter` là bean `ChunkMessageChannelItemWriter` đã cấu hình channel và cơ chế nhận reply:

~~~java
@Bean
Step chunkManagerStep(
        JobRepository repository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderRow> orderReader,
        ItemWriter<OrderRow> outboundChunkWriter) {

    return new StepBuilder("chunkManagerStep", repository)
            .<OrderRow, OrderRow>chunk(200, transactionManager)
            .reader(orderReader)
            .writer(outboundChunkWriter)
            .build();
}
~~~

Khác với Step xử lý cục bộ, **writer này không trực tiếp INSERT vào bảng đích**; nó gửi dữ liệu đến worker và phối hợp kết quả. Các `ItemProcessor` nặng và writer nghiệp vụ đặt ở worker. Với phiên bản hỗ trợ builder của Spring Batch Integration, có thể dùng `RemoteChunkingManagerStepBuilderFactory` / builder tương ứng để framework lắp `ChunkMessageChannelItemWriter`, channel và reply handling.

Manager cần quản lý kích thước chunk, số lượng message đang chờ phản hồi và timeout. **Một `ItemReader` trên manager vẫn có thể là nút thắt cổ chai**, nhất là khi truy vấn nguồn chậm hoặc một item cần tiền xử lý nặng ngay lúc đọc.

### 3.3. Chú ý về message chứa dữ liệu

Remote chunking gửi **payload item**, nên serialization rất quan trọng:

- Các kiểu dữ liệu gửi qua broker phải có định dạng và phiên bản schema phù hợp.
- Payload cần giới hạn kích thước; chunk lớn không phải lúc nào cũng nhanh hơn.
- Tránh đưa mật khẩu, token hoặc dữ liệu cá nhân không cần thiết vào message.
- Worker cần xác thực nguồn message, phân quyền consume/publish và bảo vệ đường truyền.
- Khi worker/broker xử lý message lặp, writer phải hỗ trợ **idempotency**.

Đối với dữ liệu chứa tệp nhị phân lớn, thường tốt hơn khi gửi **tham chiếu đối tượng bất biến** hoặc dùng partitioning để worker tự truy xuất nguồn thay vì đóng gói toàn bộ nội dung vào một message.

## 4. So sánh trực quan: dữ liệu nào thực sự đi qua broker?

Giả sử cùng xử lý 1.000.000 giao dịch:

~~~text
REMOTE PARTITIONING
Manager:
  partition0: minId=1,      maxId=250000
  partition1: minId=250001, maxId=500000
  partition2: minId=500001, maxId=750000
  partition3: minId=750001, maxId=1000000
  → gửi 4 yêu cầu StepExecution (mô tả phạm vi + ID)

Worker:
  → tự SELECT khoảng ID
  → process + write theo chunk nội bộ
  → cập nhật StepExecution/ExecutionContext


REMOTE CHUNKING
Manager:
  → SELECT và đọc item
  → chia thành chunk 200 item
  → gửi khoảng 5.000 message chứa item

Worker:
  → nhận một chunk 200 item
  → process + write
  → trả reply cho manager
~~~

**Số 4 partition và 5.000 chunk chỉ là ví dụ**. Trong partitioning, `gridSize` là gợi ý số lượng phân vùng/độ rộng chia việc, không phải lời hứa rằng có đúng bấy nhiêu worker vật lý. Trong chunking, số message phụ thuộc tổng số item thực tế và chunk size, cộng các retry/redelivery nếu có lỗi.

| Câu hỏi lựa chọn | Remote partitioning | Remote chunking |
| --- | --- | --- |
| “Reader ở đâu?” | Trên worker | Trên manager |
| “Broker chở gì?” | Tham chiếu StepExecution/phạm vi | Các item của chunk |
| “Ai sở hữu điểm bắt đầu/kết thúc của vùng dữ liệu?” | Partitioner, StepExecution và ExecutionContext | Reader/checkpoint của manager |
| “Làm sao worker biết đọc đoạn nào?” | `stepExecutionContext` chứa tham số vùng dữ liệu | Không cần tự chia nguồn; item đã ở message |
| “Tình trạng mất cân bằng?” | Partition quá lớn có thể khiến một worker chạy rất lâu | Phân phối từng chunk cho worker thường cân bằng tải động tốt hơn |
| “Áp lực lên mạng?” | Ít payload điều phối, nhưng mỗi worker tự đọc nguồn | Payload item qua broker tăng theo số lượng/chunk size |
| “Mở rộng đọc nguồn?” | Có thể phân tán reader | Reader của manager vẫn tập trung |

## 5. JobRepository, StepExecution và TaskRepository khác vai trò

Khi tích hợp Spring Cloud Task với Spring Batch có **hai lớp metadata**:

~~~mermaid
flowchart TD
    L["Launcher: Cron / API / workflow"] --> T["Spring Cloud Task process"]
    T --> TR[("TaskRepository<br/>TaskExecution")]
    T --> BJ["Spring Batch JobLauncher"]
    BJ --> JR[("JobRepository<br/>JobExecution + StepExecution")]
    BJ --> M["Manager Step"]
    M --> B[("Broker")]
    B --> W["Workers"]
    W -. "cập nhật step / trả reply" .-> JR
~~~

Sơ đồ thể hiện lớp remote partitioning; ở **remote chunking**, worker thường trả reply qua broker tới manager và **không cần** ghi StepExecution vào cùng JobRepository như worker partitioning.

### 5.1. Metadata khi remote partitioning

Manager tạo **StepExecution** cho từng phân vùng, với các tên dạng `workerStep:partition0`, `workerStep:partition1` trong cùng JobExecution. `ExecutionContext` của từng partition ghi phạm vi đọc và checkpoint của Step. Worker xử lý một StepExecution được giao và cập nhật kết quả qua repository.

Manager có thể tổng hợp các StepExecution thành trạng thái của manager step, bao gồm số item đã đọc/ghi và partition lỗi. Khi restart **cùng JobInstance** với cùng identifying JobParameters, các partition đã hoàn tất thông thường không cần xử lý lại; partition lỗi có thể được chạy lại theo cơ chế restart của Batch, miễn tên partition, vùng dữ liệu và repository được giữ nhất quán.

**Không đồng nhất metadata Step với exactly-once bên ngoài DB.** Nếu worker gửi email hoặc gọi API, lỗi giữa thao tác ngoài và commit checkpoint có thể khiến tác dụng phụ được thực hiện lại.

### 5.2. Metadata khi remote chunking

Manager chạy một Step chunk-oriented, giữ reader/checkpoint và tổng hợp reply. Worker nhận/chạy một **ChunkProcessor**, nên không nhất thiết có một StepExecution Batch riêng cho từng chunk. Trạng thái Job/Step chính nằm ở manager và `JobRepository` của nó.

Khi mất reply, manager có thể không biết worker đã ghi dữ liệu đích hay chưa. Vì vậy, khôi phục đúng đòi hỏi queue/broker và cơ chế đối soát, retry, idempotent writes phù hợp. **Một message được nhận lại không chứng minh chunk trước chưa được ghi.**

### 5.3. Vòng đời Spring Cloud Task

Spring Cloud Task theo dõi **tiến trình có thời gian chạy hữu hạn**. Khi manager được đóng gói thành Task, nó phải chờ kết quả Job/Step ở xa trước khi đánh dấu kết thúc. Nếu runner khởi chạy công việc bất đồng bộ rồi trả về ngay, `TaskExecution` có thể thành công hoặc kết thúc sớm trong khi worker còn chạy.

Nếu worker chạy như **message consumer dài hạn**, worker đó thường là một dịch vụ lắng nghe broker, không tự nhiên trở thành một Spring Cloud Task hữu hạn. Một số hệ thống dùng launcher/deployer để **khởi chạy worker dạng tiến trình hữu hạn**, nhưng cần thiết kế riêng điều kiện dừng, timeout và cách thông báo kết quả. **Không có thuộc tính `spring.cloud.task.remote-chunking=true` hay `spring.cloud.task.remote-partitioning=true` có thể tự biến một Task thường thành hai mô hình này.**

## 6. Luồng lỗi và restart: khác nhau ở đâu?

### 6.1. Remote partitioning

~~~mermaid
flowchart TD
  P["Manager chia partition0..3"] --> R["Gửi yêu cầu đến worker"]
  R --> C{"Kết quả StepExecution?"}
  C -->|COMPLETED| S["Ghi metadata phân vùng hoàn tất"]
  C -->|FAILED| F["Job thất bại hoặc áp dụng flow đã định"]
  F --> J["Restart cùng JobInstance"]
  J --> K["Nhận diện partition đã hoàn tất và partition cần chạy lại"]
  K --> R
~~~

Ví dụ 4 partition: `partition0`, `partition1`, `partition3` hoàn tất; `partition2` thất bại. Trong hệ thống có repository bền vững, cách tạo partition ổn định và Step hỗ trợ restart, Spring Batch có thể **chỉ chạy lại phần chưa hoàn thành**. Mỗi worker vẫn phải hỗ trợ transaction/chunk checkpoint và idempotency nếu có tác dụng phụ.

Nếu mã Partitioner thay đổi giữa lần 1 và lần restart khiến tên partition hoặc phạm vi không khớp, hệ thống có thể xử lý lại hoặc bỏ sót dữ liệu. Hãy gắn nguồn đầu vào với phiên bản/checksum hoặc snapshot đủ ổn định; không chia lại ngẫu nhiên khi restart cùng JobInstance.

### 6.2. Remote chunking

~~~mermaid
flowchart TD
  M["Manager đọc và gửi chunk #42"] --> Q[("Broker")]
  Q --> W["Worker ghi 200 item"]
  W --> X{"Reply về manager?"}
  X -->|Có| A["Manager cập nhật tiến độ / tiếp tục"]
  X -->|Mất reply| U["Không chắc worker đã ghi xong"]
  U --> V["Khôi phục / redelivery / đối soát"]
  V --> I["Idempotent writer và khóa nghiệp vụ"]
~~~

Nếu worker đã commit 200 item nhưng reply bị mất, một cơ chế retry có thể gửi lại chunk. Không được dùng giả định “message chỉ xử lý một lần” để đảm bảo tính đúng đắn. Cần chọn broker phù hợp, transaction boundary, deduplication key hoặc `UPSERT`/ràng buộc duy nhất ở nơi ghi.

Tài liệu Spring Batch yêu cầu middleware remote chunking có khả năng **lưu bền và phân phối tin cậy cho một consumer**. Hàng đợi công việc theo kiểu competing consumers phù hợp hơn kênh broadcast phát cùng chunk tới tất cả worker.

### 6.3. Đối chiếu về phục hồi

| Câu hỏi | Remote partitioning | Remote chunking |
| --- | --- | --- |
| Có thể biết partition nào FAILED? | **Có**, theo StepExecution của từng partition | **Không có partition**; theo Step/chunk và request/reply |
| Dữ liệu cần phát lại là gì? | Lệnh thực thi một partition, với StepExecution và context | Chunk item đã gửi hoặc dữ liệu được reader đọc lại |
| Worker có checkpoint của chính Step? | Có, nếu Step được cấu hình restartable | Worker chỉ xử lý chunk; checkpoint chính ở manager |
| Tránh xử lý lặp bằng gì? | Metadata Batch + transaction/idempotency nghiệp vụ | Broker/reply correlation + idempotent writer |
| Nếu một worker mất kết nối? | Xác định trạng thái StepExecution, phục hồi/restart partition | Chú ý chunk đang xử lý và reply có thể thất lạc |
| Yêu cầu về JobRepository? | Worker thường cần truy cập cùng metadata repository | Worker không nhất thiết phải có JobRepository |

**Chốt phạm vi bảo đảm:** metadata Batch giúp kiểm soát restart và tránh chạy lại Step đã `COMPLETED` trong JobInstance, nhưng cả hai kiến trúc đều phải tự giải quyết dữ liệu ngoài giao dịch, network retry và các tác dụng phụ không thể rollback.

## 7. Khi nào chọn mô hình nào?

### 7.1. Chọn remote partitioning khi...

- Đầu vào **tách tự nhiên thành vùng độc lập**: mỗi file, mỗi tenant, mỗi ngày, khoảng khóa chính hoặc shard.
- Đọc dữ liệu nguồn là điểm nghẽn và worker có thể đọc song song với index/snapshot hợp lý.
- Muốn theo dõi tiến độ/lỗi ở cấp **StepExecution từng vùng**.
- Muốn tận dụng chunk checkpoint nội bộ trong từng Step worker.
- Payload đầu vào lớn; truyền bản ghi qua broker tốn băng thông và serialization.

Ví dụ: 200 tệp lớn nằm trên object storage, mỗi file có cấu trúc độc lập và có thể được worker tải trực tiếp. `Partitioner` tạo mỗi partition với `objectKey`/version, rồi worker tự tải, parse, validate, ghi kết quả. Khi một file lỗi, chỉ partition tương ứng cần xử lý lại theo quy tắc restart.

### 7.2. Chọn remote chunking khi...

- Một reader có thể đọc dữ liệu **nhanh và ổn định**, còn process/write tốn CPU hoặc I/O.
- Input khó chia thành các vùng đọc độc lập đáng tin cậy.
- Cần phân phối **động**: worker rảnh nhận chunk tiếp theo từ broker.
- Kích thước item và chunk đủ nhỏ, phù hợp giới hạn message và băng thông.
- Đã có hạ tầng broker bền vững, request/reply correlation, giám sát độ trễ và idempotent writer.

Ví dụ: đọc nhanh bảng các mã sản phẩm, sau đó mỗi sản phẩm cần gọi dịch vụ phân tích tốn CPU. Manager chỉ đọc và phân phối chunk; các worker xử lý và lưu kết quả.

### 7.3. Đánh giá cổ chai bằng phép đo

Trước khi chọn, đo thử dữ liệu đại diện:

| Chỉ số | Ý nghĩa |
| --- | --- |
| `read items/sec` tại manager/worker | Reader có phải giới hạn? |
| `process ms/item` | Xử lý có nặng hơn đọc không? |
| `write ms/item` và số kết nối DB | Worker có thể làm quá tải DB đích không? |
| Kích thước payload/chunk và serialization time | Remote chunking có phù hợp mạng/broker? |
| Độ lệch số item/partition | Remote partitioning có worker chạy quá lâu? |
| Queue depth, consumer lag, reply timeout | Broker/worker có đủ năng lực? |
| Thời gian restart và số dòng xử lý lại | Chi phí phục hồi khi lỗi? |

Nếu không có số liệu, bắt đầu bằng **Step cục bộ chạy đúng**, thử tăng worker trong một môi trường kiểm soát, rồi quyết định có cần remote hay không. Phân tán sớm có thể tăng chi phí vận hành mà không tăng throughput.

## 8. Thiết kế dữ liệu và phân vùng an toàn

### 8.1. Tên partition và phạm vi phải ổn định

Các key `partition0`, `partition1`, ... có vai trò đối chiếu StepExecution qua restart. Nếu dùng phân vùng theo file, nên dùng danh sách file với định danh/version cố định. Nếu dùng dải ID, nên xác định **high-water mark** tại thời điểm chốt dữ liệu; tránh việc input thay đổi bất ngờ trong khi các worker đang xử lý.

Ví dụ một phân vùng dùng context:

~~~text
partitionName=partition2
inputSnapshot=orders-2026-11-23-v1
minId=500001
maxId=750000
~~~

Nếu nguồn thay đổi trong quá trình chạy, cần chính sách snapshot, đóng băng nguồn hoặc chấp nhận dữ liệu mới sẽ xử lý ở lần sau. Các dải không chồng lấn giúp tránh phân vùng xử lý cùng hàng, nhưng cần kiểm tra filter SQL thực tế, nhất là khi dùng nhiều điều kiện ngoài ID.

### 8.2. Chunk size không phải partition count

`gridSize`/số partition quyết định **số vùng công việc logic** để đưa tới worker. Trong từng worker partition, một Step vẫn có thể xử lý theo **chunk size = 100 hoặc 500**. Remote chunking lại có **chunk size** để quyết định lượng item gửi trong **mỗi message**.

~~~text
Remote partitioning:
  4 partition × nhiều chunk nội bộ cho mỗi Step

Remote chunking:
  1 reader/Step manager → nhiều request, mỗi request là một chunk
~~~

Tăng grid size quá lớn gây nhiều StepExecution, chi phí quản trị và quá tải metadata repository. Tăng chunk size quá lớn gây transaction dài, payload message lớn, khó retry và tăng độ trễ trước khi nhận kết quả. Hai nút điều khiển này tác động lên **hai tầng khác nhau**.

## 9. Hạ tầng, triển khai và bảo mật

### 9.1. Các thành phần tối thiểu

| Thành phần | Remote partitioning | Remote chunking |
| --- | --- | --- |
| Manager chứa `JobLauncher` / `JobRepository` | Cần | Cần |
| Broker/message transport | Cần cho remote nhiều JVM | Cần cho remote nhiều JVM |
| Worker có reader | Cần | Thông thường không |
| Worker có processor/writer | Cần | Cần |
| Worker có JobRepository/JobExplorer phù hợp | Thông thường cần để xử lý StepExecution | Không bắt buộc theo mô hình chuẩn |
| Schema metadata Batch | Manager và worker partitioning phải phối hợp nhất quán | Manager sử dụng; worker chunking có thể không cần |
| Retry, timeout, idempotency nghiệp vụ | Cần thiết | Cần thiết |
| Job/Task launcher và giám sát | Cần thiết | Cần thiết |

Trong Spring Boot, dùng BOM tương thích giữa Spring Batch, Spring Integration và Spring Cloud Task. Các module liên quan có thể gồm `spring-batch-integration`, adapter `spring-integration-jms` hoặc `spring-integration-amqp`, cùng driver JDBC và starter cần thiết. Chỉ thêm dependency mà không có **queue, channel, reply mapping và cấu hình worker** sẽ chưa tạo ra remote processing.

### 9.2. Vì sao cần bảo vệ message?

- Mã hóa transport và xác thực worker/manager với broker.
- Chỉ cấp quyền publish/consume đúng queue; tách queue request/reply giữa môi trường.
- Giới hạn payload, TTL message và chính sách dead-letter queue theo quy trình phục hồi.
- Không đưa token, mật khẩu hay dữ liệu cá nhân không cần thiết vào payload hoặc log.
- Version hóa serializer/schema khi manager và worker được rolling update ở các thời điểm khác nhau.
- Đảm bảo correlation ID và header cần thiết không bị mất khi qua adapter, nhất là luồng reply.

**Lưu ý phiên bản mới:** trong hướng dẫn Spring Batch 6.1, khi sử dụng **JMS**, phải cấu hình `DefaultJmsHeaderMapper` để giữ các header Spring Integration phục vụ correlation/aggregation như `correlationId`, `sequenceNumber`, `sequenceSize`; nếu header bị loại bỏ, manager có thể không ghép được reply. Ví dụ whitelist chỉ dùng khi transport/phiên bản tương ứng hỗ trợ:

~~~java
new DefaultJmsHeaderMapper(
        "correlationId", "sequenceNumber", "sequenceSize");
~~~

Không mở toàn bộ header qua `"*"` nếu không cần thiết về mặt bảo mật. Với AMQP hoặc adapter khác, kiểm tra header mapping theo cơ chế tương ứng.

### 9.3. Ai là tiến trình hữu hạn?

Nếu dùng **Spring Cloud Task** làm manager, TaskExecution là vòng đời **một lần chạy Batch Job**, chỉ hoàn tất khi Job và các worker đã hoàn tất/được xác định thất bại. Worker listener nhận message liên tục thường được triển khai như một service chạy dài hạn, hoặc được quản lý theo chính sách khởi chạy và dừng riêng.

Không giả định `@EnableTask` trên worker là đủ để tự dừng khi hết message. Nếu muốn worker cũng là Task hữu hạn, phải có chính sách **số request được xử lý, deadline, drain queue, graceful shutdown** và trạng thái kết quả trước khi tiến trình thoát.

### 9.4. Đảm bảo mã thoát cho scheduler

Một `JobExecution` có thể mang `BatchStatus.FAILED` mà tiến trình Java vẫn kết thúc mã `0` nếu ứng dụng không truyền thất bại cho bộ điều phối. Với tích hợp Spring Cloud Task–Batch phù hợp, cân nhắc `spring.cloud.task.batch.fail-on-job-failure=true`. Nếu tự gọi `JobLauncher`, luôn kiểm tra trạng thái Job và ném lỗi/chuyển exit code khi thất bại.

Timeout của manager cần bao gồm thời gian chờ worker, retry và phản hồi; không đánh dấu `TaskExecution` thành công chỉ vì đã **gửi xong message**.

## 10. Quan sát và xử lý sự cố

### 10.1. Metadata cần theo dõi

| Tầng | Dữ liệu quan sát |
| --- | --- |
| Spring Cloud Task | `TaskExecution ID`, tên Task, thời gian chạy, `EXIT_CODE`, `EXIT_MESSAGE` |
| Spring Batch manager | `JobExecution ID`, JobInstance, StepExecution manager, trạng thái cuối |
| Remote partitioning | Tên partition, StepExecution ID, context/phạm vi, số đọc/ghi, lỗi từng Step |
| Remote chunking | Chunk request ID/correlation ID, số message đã gửi/ack, queue lag, reply timeout |
| Worker | Worker ID/Pod, thời gian xử lý, lỗi đọc/ghi, retry/deduplication |
| Nghiệp vụ | Business key, tổng số bản ghi, checksum, đối soát nguồn và đích |

`TASK_EXECUTION` thuộc TaskRepository, còn `BATCH_JOB_EXECUTION` và `BATCH_STEP_EXECUTION` thuộc JobRepository. Không cố suy ra trực tiếp `TaskExecution ID = JobExecution ID`. Với tích hợp Task–Batch có liên kết tương ứng, có thể truy vết qua `TASK_TASK_BATCH` hoặc API `TaskExplorer`; nếu thiếu liên kết, ghi correlation ID để đối chiếu.

### 10.2. Triệu chứng thường gặp

| Triệu chứng | Chỗ cần kiểm tra đầu tiên |
| --- | --- |
| Remote partitioning chỉ một worker chạy | Số partition thực tế, gridSize, queue consumer, worker kết nối nguồn |
| Một partition chạy quá lâu | Phạm vi dữ liệu lệch, index truy vấn, dữ liệu nóng, transaction/chunk |
| Remote partitioning worker không tìm được StepExecution | Cấu hình JobExplorer/JobRepository, DB/schema, Step name, request ID |
| Remote chunking manager đọc nhanh nhưng Job đứng | Queue backlog, worker chết, reply correlation, timeout |
| Worker ghi xong nhưng manager báo retry | Mất reply/ack; kiểm tra idempotency và trạng thái broker |
| Có dữ liệu trùng sau restart | Thiếu unique constraint/idempotent write hoặc partition phạm vi chồng lấn |
| Có JobExecution FAILED nhưng Task exit code 0 | Thiếu cơ chế phản ánh Batch failure tới Task/launcher |
| Kết thúc Task khi worker còn chạy | Runner/JobLauncher bất đồng bộ và không chờ kết quả |
| Queue chứa message quá lớn | Chunk size quá lớn, serializer chứa object graph không cần thiết |

Đừng coi một StepExecution chưa có `END_TIME` là worker vẫn sống; nó có thể đã bị kill trước khi kịp cập nhật repository. Phải đối chiếu Pod/Job/consumer, broker và log để biết chính xác.

## 11. Ma trận quyết định bằng tình huống thực tế

| Bài toán | Mô hình đề xuất | Lý do |
| --- | --- | --- |
| 100 file CSV độc lập trên object storage | **Remote partitioning** | Phân công từng file; worker tự đọc và quản lý StepExecution |
| Đọc một query nhẹ, mỗi item phải chạy phân tích ảnh nặng | **Remote chunking** | Manager đọc nhanh; worker phân tán phần CPU nặng |
| Mỗi tenant có một bảng hoặc shard riêng | **Remote partitioning** | Mỗi partition gắn tenant/shard, giảm reader tập trung |
| Một nguồn dữ liệu duy nhất rất chậm, không thể chia miền | Chưa vội chọn remote chunking | Manager reader vẫn là nút thắt; tối ưu nguồn trước |
| Ghi đích chậm nhưng item nhỏ, đọc nhanh | **Remote chunking** có thể phù hợp | Worker chia tải xử lý/ghi, với giới hạn DB đích |
| Data lake có vùng dữ liệu rất lệch | **Remote partitioning có thiết kế cân bằng tải** | Cần partition theo kích thước thực tế, có thể tạo nhiều vùng nhỏ |
| Broker giới hạn payload thấp, nguồn worker truy cập được | **Remote partitioning** | Chỉ chuyển thông tin vùng dữ liệu qua message |
| Không cần nhiều tiến trình, một máy đã đủ tải | **Step cục bộ** | Tránh chi phí broker, remote debugging và vận hành |

Không có kết quả nào mặc định **exactly-once** trên tác dụng phụ bên ngoài giao dịch. Với cả hai mô hình, thiết kế bản ghi đầu ra với khóa duy nhất phù hợp, xử lý replay và có phương án đối soát sau khi lỗi.

## 12. Bài tập thực hành

Một hệ thống thương mại điện tử có 4 triệu đơn hàng, mỗi đơn gồm `orderId`, `tenantId`, `amount`. Mục tiêu là tổng hợp và chuẩn hóa dữ liệu trong đêm. Có 4 worker Pod, PostgreSQL, RabbitMQ và Spring Cloud Task điều phối tiến trình manager.

### Phần A — triển khai remote partitioning

1. Thiết kế `Partitioner` chia ID thành 8 vùng độc lập, tên partition ổn định.
2. Gắn `minId` và `maxId` vào `ExecutionContext`; dùng `@StepScope` để Reader của worker nhận đúng vùng.
3. Dùng Step chunk-oriented tại worker; ghi trạng thái vào `JobRepository` được manager và worker phối hợp truy cập.
4. Giả lập `partition3` thất bại sau khi đã ghi một vài chunk; restart **cùng JobInstance** và quan sát các StepExecution cần chạy lại.
5. Chứng minh không bỏ sót/trùng bằng số lượng ID, checksum hoặc khóa duy nhất.

### Phần B — triển khai remote chunking

1. Đặt Reader ở manager, dùng `chunkSize=200`, gửi item qua queue.
2. Worker nhận chunk, xử lý và ghi đích; reply trở về manager với correlation ID đúng.
3. Giả lập worker đã commit rồi mất reply; phân tích nguy cơ gửi lại chunk và thiết kế idempotent writer.
4. Tăng từ 2 lên 4 worker; đo throughput, queue depth, kích thước message và mức tải CSDL.
5. So sánh chi phí mạng/broker với mô hình phân vùng.

### Phần C — nối với Spring Cloud Task

1. Khởi chạy manager như một Task hữu hạn và ghi `TaskExecution ID`.
2. Liên kết `TaskExecution` với `JobExecution` hoặc giữ correlation ID có thể tra cứu.
3. Cố ý làm một Step/worker lỗi; kiểm tra Batch Job FAILED có dẫn tới **mã thoát Task khác 0**.
4. Kiểm chứng manager **đợi đến khi kết quả worker hoàn tất**, không kết thúc sau khi chỉ gửi message.
5. Lập bảng so sánh **đơn vị gửi đi, reader location, worker role, metadata, retry và idempotency**.

**Tiêu chí đạt:** giải thích được vì sao remote partitioning worker thường cần JobRepository và quyền đọc dữ liệu nguồn, còn remote chunking worker nhận trực tiếp item từ broker và có thể không cần JobRepository của manager. Nêu được một tình huống mà mỗi mô hình là lựa chọn hợp lý và một lỗi khi retry cần khắc phục bằng cơ chế nghiệp vụ.

## 13. Các điểm cần ghi nhớ

1. **Remote partitioning** phân phối **StepExecution/ExecutionContext đại diện vùng dữ liệu**; worker chạy Step hoàn chỉnh, tự đọc, xử lý và ghi.
2. **Remote chunking** phân phối **item theo chunk đã đọc tại manager**; worker xử lý/ghi rồi trả kết quả để manager tổng hợp.
3. Partitioning phù hợp dữ liệu **chia độc lập và cần mở rộng I/O đọc**; chunking phù hợp khi **manager đọc nhanh, xử lý/ghi mới nặng**.
4. Remote partitioning theo dõi **StepExecution từng partition** trong JobRepository; remote chunking tập trung Step/Job metadata ở manager và phụ thuộc request/reply đúng.
5. Cả hai đều cần **transaction boundary, timeout, retry, quan sát và idempotency**. Metadata Batch và broker không tự bảo đảm exactly-once cho API hay dữ liệu ngoài giao dịch.
6. Spring Cloud Task quản lý **lần chạy hữu hạn và kết quả tiến trình**; Spring Batch quản lý **Job/Step/partition/chunk**. Khi dùng cả hai, phải đảm bảo Task không kết thúc trước Job/worker.
7. Trước khi chọn remote, đo **reader throughput, process/write time, kích thước payload, mức độ lệch partition và khả năng của CSDL/broker**.

### Tài liệu tham khảo chính thức

- [Spring Batch Reference — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html)
- [Spring Batch Reference — Spring Batch Integration: Remote Chunking và Remote Partitioning](https://docs.spring.io/spring-batch/reference/spring-batch-integration/externalizing-execution.html)
- [Spring Cloud Task Reference — Tích hợp Spring Batch](https://docs.spring.io/spring-cloud-task/reference/batch.html)
- [Spring Batch Reference 5.2 — Externalizing Batch Process Execution](https://docs.spring.io/spring-batch/reference/5.2/spring-batch-integration/externalizing-execution.html)
