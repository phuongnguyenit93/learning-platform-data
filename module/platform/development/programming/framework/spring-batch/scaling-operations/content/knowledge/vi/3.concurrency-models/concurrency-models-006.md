# Remote chunking qua middleware trong Spring Batch

Một batch job cần đọc 20 triệu hóa đơn từ một nguồn dữ liệu tập trung, làm giàu từng hóa đơn qua dịch vụ tính thuế và ghi kết quả vào database. Reader có thể cung cấp 15.000 item/giây, nhưng processor và writer trên một JVM chỉ xử lý được khoảng 2.000 item/giây. **Remote chunking** là lựa chọn để giữ reader ở một **manager** và đưa các chunk sang nhiều **worker** chạy trên những JVM khác qua middleware như JMS hoặc RabbitMQ.

Điểm quan trọng: remote chunking không đơn thuần là “thêm queue cho nhanh hơn”. Nó thay đổi ranh giới tiến trình, giao dịch, phản hồi và xử lý lỗi. Một worker có thể ghi dữ liệu thành công nhưng phản hồi thất lạc, làm manager tưởng chunk chưa hoàn tất. Nếu thiếu idempotency, retry có thể ghi trùng nghiệp vụ. Vì vậy phải thiết kế **request/reply, durability, redelivery, timeout, checkpoint, backpressure và vận hành** như một hệ thống phân tán.

Bài học thuộc chương **Mô hình đồng thời** trong module **SPRING_BATCH_SCALING_OPERATIONS**. Mục tiêu chung là mở rộng workload dữ liệu lớn bằng multi-threaded step, parallel steps, partitioning và xử lý phân tán phù hợp; đo nút thắt, bảo đảm thread safety, retry/restart, vận hành job và lựa chọn kiến trúc theo năng lực tài nguyên thực tế. Chủ đề ở đây là **Remote chunking qua middleware**.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vai trò của **manager**, **remote workers**, **middleware** và đường đi của `ChunkRequest`/`ChunkResponse`.
2. Phân biệt remote chunking với multi-threaded step và remote partitioning.
3. Thiết kế topology **work queue + reply channel** có competing consumers, correlation và giới hạn in-flight.
4. Cấu hình khung Spring Batch Integration 5.2.x với `RemoteChunkingManagerStepBuilder` và `RemoteChunkingWorkerBuilder`.
5. Phân tích ranh giới transaction/ACK, tình huống mất reply, redelivery, duplicate và dead-letter queue.
6. Thiết kế idempotency cho writer và chính sách retry/restart có kiểm chứng.
7. Tính sơ bộ throughput, chunk size, worker concurrency, payload size và bottleneck của manager/broker/DB.
8. Kiểm thử worker crash, broker outage, duplicate delivery, stale reply và khả năng đáp ứng SLA.

## 2. Remote chunking là gì?

**Remote chunking** chia quá trình xử lý một chunk-oriented step giữa nhiều **process**:

- **Manager:** chạy Spring Batch job/step, dùng `ItemReader` lấy các item từ nguồn; gom item thành chunk, gửi yêu cầu đến middleware; nhận kết quả từ worker và tổng hợp trạng thái step.
- **Workers:** nhận chunk đã chứa item, thực hiện `ItemProcessor` nếu có và `ItemWriter`; trả lời manager về việc xử lý chunk thành công hay thất bại.
- **Middleware:** vận chuyển yêu cầu và phản hồi giữa các process; điều phối competing consumers, buffering và cơ chế giao nhận phù hợp.

Manager giữ trách nhiệm đọc và **không giao cho worker tự truy vấn khoảng dữ liệu**. Khác với remote partitioning, worker thường không được cấp một `StepExecution` độc lập để tự đọc partition của mình.

~~~mermaid
flowchart LR
    SRC[("Nguồn dữ liệu")] --> MR["Manager JVM<br/>Spring Batch Step<br/>ItemReader"]
    MR --> CW["ChunkMessageChannelItemWriter<br/>gửi ChunkRequest"]
    CW --> Q[("Request queue<br/>durable")]
    Q --> W1["Worker JVM A<br/>processor + writer"]
    Q --> W2["Worker JVM B<br/>processor + writer"]
    Q --> W3["Worker JVM C<br/>processor + writer"]
    W1 --> DB[("Output DB / API")]
    W2 --> DB
    W3 --> DB
    W1 --> RQ[("Reply queue<br/>durable")]
    W2 --> RQ
    W3 --> RQ
    RQ --> MA["Manager nhận ChunkResponse<br/>đối chiếu / tổng hợp"]
    MA --> JR[("JobRepository")]
~~~

Một request queue có nhiều worker **competing consumers**: một bản giao message được broker phân phối cho một consumer, chứ không phát cho **mọi worker**. Broker có thể giao lại cùng message sau timeout, connection loss hoặc negative acknowledgement; “một consumer cho mỗi lần giao” **không đồng nghĩa exactly-once về tác dụng nghiệp vụ**.

### 2.1. Một vòng đời chunk

Giả sử manager dùng `chunk size = 200`:

1. Reader đọc tối đa 200 item từ nguồn theo chu kỳ xử lý chunk.
2. Manager tạo một `ChunkRequest` chứa item và metadata cần đối chiếu, rồi gửi qua **request channel** tới broker.
3. Broker phân phối message cho một worker sẵn sàng.
4. Worker giải mã message, chạy processor và writer, commit những thay đổi có transaction phù hợp.
5. Worker tạo `ChunkResponse`, gửi về **reply channel** tới manager.
6. Manager ghép reply vào yêu cầu liên quan, nhận kết quả/đóng góp về step, đánh giá lỗi và tiến độ.
7. Manager chỉ nên kết luận step hoàn tất khi các chunk bắt buộc đã được xử lý và phản hồi theo chính sách được cấu hình.

Remote chunking cho phép manager tiếp tục chuẩn bị/gửi các chunk trong khi worker xử lý các chunk trước. Vì vậy manager cần quản lý **số yêu cầu in-flight** để không đọc trước không giới hạn.

~~~mermaid
sequenceDiagram
    participant M as Manager
    participant B as Request Broker
    participant W as Worker B
    participant D as Output DB
    participant R as Reply Broker
    M->>M: read + group 200 items
    M->>B: ChunkRequest(seq=17, items)
    B->>W: Deliver request
    W->>W: ItemProcessor
    W->>D: ItemWriter / commit
    D-->>W: Commit OK
    W->>R: ChunkResponse(seq=17, success)
    W->>B: ACK theo chính sách adapter
    R->>M: Deliver response
    M->>M: Correlate + aggregate
    Note over M,R: ACK, DB commit, reply publish không tự động nằm trong một transaction phân tán
~~~

Thứ tự ACK ở sơ đồ là **mô hình mong muốn để thảo luận**, không phải mặc định áp dụng cho mọi adapter. Chính xác ACK trước/sau publish reply, auto/manual ACK, local/external transaction và trường hợp lỗi phụ thuộc cấu hình Spring Integration, listener container và broker.

## 3. Phân biệt remote chunking với các mô hình khác

| Mô hình | Ai đọc dữ liệu? | Đơn vị được phân phối | Metadata/Checkpoint | Thường chọn khi |
| --- | --- | --- | --- | --- |
| Chunk step tuần tự | Một step local | Không phân phối | StepExecution/ExecutionContext local | Workload đạt SLA, ưu tiên đơn giản |
| Multi-threaded step | Reader của cùng step | Các chunk qua thread pool cùng JVM | Thường chung StepExecution | Reader/processor/writer thread-safe, có headroom |
| Local partitioning | Reader riêng của từng partition | Worker StepExecution chạy ở nhiều thread | Context riêng theo partition | Chia được file/ID range, muốn restart shard |
| **Remote chunking** | **Manager** | **ChunkRequest chứa item** qua middleware | Manager quản lý chunk/step; worker xử lý request | Reader nhanh, processor/writer tốn tài nguyên |
| Remote partitioning | **Mỗi remote worker** | StepExecution/partition và phạm vi dữ liệu | Context + StepExecution theo partition | Worker có thể tự đọc shard, cần scale reader |

Đặc trưng quyết định: **manager có phải nút thắt hay không**.

Nếu processor mất 100 ms mỗi item còn reader lấy được 20.000 item/giây, phân tán worker có thể có ích. Nhưng nếu reader chỉ đạt 1.000 item/giây mà SLA cần 10.000 item/giây, 50 worker vẫn không sửa được giới hạn này. Khi đó nên đánh giá chia nguồn bằng partitioning hoặc tối ưu reader/index/I/O.

### 3.1. Không nhầm với gửi từng item

Remote chunking gửi **một nhóm item trong một ChunkRequest**, không bắt buộc một message cho mỗi item. Điều này giảm overhead messaging, nhưng tăng kích thước payload và lượng công việc có thể phải xử lý lại sau lỗi. Chunk size, mức in-flight và số worker là **ba tham số khác nhau**.

## 4. Middleware cần bảo đảm những gì?

Spring Batch remote chunking được thiết kế với yêu cầu middleware đủ bền vững để vận chuyển chunk và phản hồi. Một thiết kế thực tế cần:

| Yêu cầu | Lý do |
| --- | --- |
| **Durable request queue** | Broker restart không làm mất toàn bộ yêu cầu chưa xử lý |
| **Persistent messages** | Queue durable một mình chưa đủ nếu message không được ghi bền vững |
| **Competing-consumer semantics** | Mỗi request được phân công cho một worker tại một thời điểm giao |
| **Redelivery khi worker chết** | Message chưa ACK có thể tới worker khác |
| **Durable/recoverable reply path** | Worker thành công nhưng reply mất có thể khiến manager fail hoặc chờ mãi |
| **Correlation** | Manager phải gắn kết response đúng chunk và lần chạy liên quan |
| **Flow control / backpressure** | Không tạo hàng triệu request in-flight khi worker xử lý chậm |
| **DLQ và retry có giới hạn** | Message độc hại không bị lặp vô tận, không chặn vĩnh viễn |
| **Security và compatibility** | Quyền publish/consume tối thiểu, schema version và serialization tương thích |

**At-least-once transport** thường là giả định thiết kế an toàn: cùng một chunk request **có thể xuất hiện nhiều lần**. Chỉ khi toàn bộ giao thức, transaction, idempotency và recovery được xác minh mới có thể phát biểu mức bảo đảm mạnh hơn ở cấp nghiệp vụ.

### 4.1. JMS, RabbitMQ/AMQP và Kafka

- **JMS queue:** thích hợp cho work queue, transaction/acknowledgement và cạnh tranh giữa consumers; cần phân biệt queue và topic. Topic fanout tới mọi subscriber **không** phải request work distribution mong muốn.
- **RabbitMQ (AMQP):** dùng exchange route tới một request queue, nhiều consumer nhận từ queue; reply queue/channel riêng. Bật durable queue, persistent publish, publisher confirm/return và xử lý consumer ACK theo ranh giới business. Việc dùng publisher confirms không tự làm DB + broker atomic.
- **Kafka:** có thể triển khai message-based worker với **consumer group**, nhưng cần quản lý partition count, offset commit, rebalance, request/reply correlation và ordering. Kafka không tự cung cấp RPC/reply pattern của Spring Batch Integration; adapter và recovery phải được thiết kế riêng. Một consumer group chỉ cho tối đa một consumer active cho mỗi Kafka partition trong nhóm ở một thời điểm, nên concurrency bị giới hạn theo partitions.

Không nên thay JMS/AMQP bằng Kafka chỉ vì đang có sẵn một cluster. Cần kiểm tra đặc tính request/reply, retention, payload size, replay và cách manager chờ kết quả.

### 4.2. Topology tối thiểu

~~~text
Manager:
  outboundChunkRequests --> [batch.chunk.requests] --> Worker pool
  inboundChunkReplies  <-- [batch.chunk.replies]  <-- Worker pool

Optional:
  [batch.chunk.requests.dlq]  <-- rejected/poison requests
  [batch.chunk.replies.dlq]   <-- unprocessable/stale replies
~~~

Tên queue ở đây chỉ là ví dụ. Nếu nhiều manager/JobExecution chạy đồng thời, phải bảo đảm reply routing/correlation không làm một manager tiêu thụ và bỏ mất reply của manager khác. Có thể chọn **reply destination riêng theo manager/job execution** hoặc thiết kế reply router có định tuyến và lưu trữ đúng. Không chỉ khai báo “reply queue chung” rồi giả định Spring Batch tự động ngăn các consumer cạnh tranh lấy nhầm response.

## 5. ChunkRequest, ChunkResponse và correlation

Trong Spring Batch Integration, các lớp liên quan gồm:

- `ChunkRequest<T>`: bao gói các item thuộc một chunk cùng thông tin liên quan tới việc xử lý remote; bản 5.2 có thông tin như sequence, định danh execution và `StepContribution`.
- `ChunkResponse`: phản hồi kết quả xử lý chunk và đóng góp thống kê cho step.
- `ChunkMessageChannelItemWriter`: writer phía manager dùng Spring Integration để phát yêu cầu và tiếp nhận/tổng hợp kết quả worker.
- `ChunkProcessorChunkHandler`: worker handler thực thi chuỗi processor/writer theo nội dung request.
- `RemoteChunkingManagerStepBuilder` và `RemoteChunkingWorkerBuilder`: builder hỗ trợ wiring manager/worker.

Không cần tự tạo payload JSON trùng tên `ChunkRequest` nếu đã dùng message contract của Spring Batch Integration. Tuy nhiên, khi **tự chọn serializer/transport**, phải bảo đảm tương thích type/schema, correlation headers và version giữa manager và workers.

### 5.1. Danh tính để đối chiếu

Một request phải được phân biệt theo **lần chạy + sequence chunk** (cùng routing metadata phù hợp), không chỉ theo thứ tự đến queue. Request có thể hoàn tất sai thứ tự:

~~~text
Manager phát:   chunk #17, chunk #18, chunk #19
Workers xong:   chunk #18, chunk #17, chunk #19
Manager nhận:   response #18, #17, #19
~~~

Đây là hành vi bình thường của xử lý song song. Manager cần đối chiếu đúng reply, tránh lấy reply cũ từ JobExecution trước hoặc kết luận một response hợp lệ là lỗi của chunk khác.

**Cảnh báo:** Header correlation của Spring Integration phải được chuyển qua middleware. Khi sử dụng JMS hoặc custom serializer, hãy kiểm tra header mapping của `correlationId` và các header sequence/aggregation mà phiên bản ứng dụng cần. Nếu converter không giữ những header này, replies đến vẫn có thể không ghép được với requests.

### 5.2. Serialization và contract

Payload có thể chứa hàng trăm hoặc hàng nghìn item. Cần định nghĩa:

- Kiểu dữ liệu có thể serialize được và không chứa JDBC connection, file handle hoặc entity lazy-loading phụ thuộc session.
- Message schema version, cách xử lý khi manager và worker chạy hai phiên bản khác nhau.
- Kích thước tối đa một chunk, giới hạn của broker/client, timeout và compression nếu hợp lý.
- PII, encryption in transit/at rest, quyền truy cập broker và chính sách giữ/log dữ liệu.
- Các trường idempotency và trace được tính **từ thông tin bền vững**, không từ random ID thay đổi khi retry.

Tránh sử dụng Java native serialization như một mặc định không đánh giá rủi ro bảo mật/khả năng tương thích. Có thể sử dụng schema có version và message converter an toàn phù hợp hệ sinh thái, nhưng converter phải xử lý đúng contract Spring Batch Integration.

## 6. Ví dụ cấu hình manager với Spring Batch 5.2.x

Ví dụ sau dùng API Spring Batch Integration **5.2.x**, nhằm minh họa **đúng điểm nối** giữa manager và middleware. Các channel được **adapter khác nối với broker thật**; chỉ khai báo channel mà không nối adapter sẽ chưa tạo remote processing.

Giả sử item đầu vào là record `InvoiceRow`. Manager chỉ đọc và gửi các `InvoiceRow`; processor/writer chạy trong worker process.

### 6.1. Message contracts dùng chung

~~~java
// Thư viện hợp đồng dùng chung cho manager và workers.
// File InvoiceRow.java
import java.io.Serializable;
import java.math.BigDecimal;

public record InvoiceRow(long invoiceId,
                         BigDecimal amount,
                         long sourceVersion)
        implements Serializable {}

// File InvoiceResult.java
import java.io.Serializable;
import java.math.BigDecimal;

public record InvoiceResult(long invoiceId,
                            BigDecimal netAmount,
                            long sourceVersion)
        implements Serializable {}
~~~

Đây là ví dụ Java record. Serializer thực tế có thể dùng JSON/Avro/Protobuf theo hợp đồng đã thống nhất; `implements Serializable` **không tự bắt buộc** sử dụng Java native serialization qua broker.

### 6.2. Manager step đọc và gửi chunk

~~~java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.integration.chunk.RemoteChunkingManagerStepBuilder;
import org.springframework.batch.item.ItemReader;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class InvoiceManagerConfiguration {

    @Bean
    public Step invoiceManagerStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            ItemReader<InvoiceRow> invoiceReader,
            @Qualifier("outboundChunkRequests") MessageChannel requests,
            @Qualifier("inboundChunkReplies") PollableChannel replies) {

        return new RemoteChunkingManagerStepBuilder<InvoiceRow, InvoiceRow>(
                "invoiceManagerStep", jobRepository)
                .chunk(200)
                .reader(invoiceReader)
                .transactionManager(transactionManager)
                .outputChannel(requests)   // manager -> broker -> workers
                .inputChannel(replies)     // workers -> broker -> manager
                .maxWaitTimeouts(40)       // số lần chờ reply, không phải 40 giây
                .build();
    }

    @Bean
    public Job invoiceJob(
            JobRepository jobRepository,
            @Qualifier("invoiceManagerStep") Step managerStep) {
        return new JobBuilder("invoiceJob", jobRepository)
                .start(managerStep)
                .build();
    }
}
~~~

`ItemReader<InvoiceRow>` phải là bean đã cấu hình để đọc snapshot đầu vào ổn định và hỗ trợ checkpoint nếu job cần restart. Có thể dùng `JdbcPagingItemReader`, `FlatFileItemReader` hoặc reader phù hợp; không dùng datasource/query không xác định làm ví dụ mặc định.

Điểm cần hiểu:

- `RemoteChunkingManagerStepBuilder` tạo writer phía manager chuyên gửi chunk. **Không gọi `writer(customWriter)`** để thay writer ấy; nghiệp vụ ghi thực tế chạy tại worker.
- `chunk(200)` quyết định số item thuộc request chunk thông thường, không phải số worker hoặc queue prefetch.
- `outboundChunkRequests` và `inboundChunkReplies` là **Spring Messaging channels**; phải nối tới adapter outbound/inbound của broker thực tế.
- `inputChannel` phía manager với API 5.2 nhận `PollableChannel`. Không tùy tiện thay bằng `DirectChannel` khi biên dịch với đúng builder này.
- `maxWaitTimeouts(40)` là **số lần chờ nhận kết quả**; thời lượng thực phụ thuộc receive timeout cấu hình trong messaging gateway/template. Không suy “40 là 40 giây”.
- Manager có `JobRepository` lưu trạng thái JobExecution/StepExecution. Worker kiểu remote chunking **không mặc định là một JobInstance/StepExecution riêng cho mỗi chunk**.

### 6.3. Kết nối tới broker nằm ở đâu?

~~~text
Manager Spring Integration:
  MessageChannel outboundChunkRequests
      -> outbound adapter / gateway
      -> durable request queue

  durable reply queue
      -> inbound adapter / bridge phù hợp
      -> PollableChannel inboundChunkReplies
~~~

Trong code production, định nghĩa `@Bean` channel và các `IntegrationFlow`/adapter nối queue, chọn serializer/header mapper, destination/routing, error channel và chính sách confirmation/ack. Không có cách kết nối nào là mặc định cho mọi JMS/RabbitMQ/Kafka deployment.

**Lưu ý thực thi:** đoạn Java ở mục 6.2 là cấu hình *manager step* có thể ghép vào ứng dụng, **không phải ví dụ chạy end-to-end độc lập**, vì reader, channels và middleware adapter được cung cấp ngoài snippet.

## 7. Ví dụ cấu hình worker bằng Spring Batch Integration

Worker không phải đọc trực tiếp nguồn hóa đơn. Nó nhận `InvoiceRow` trong chunk request, tính phí rồi ghi kết quả. Với Spring Batch Integration 5.2.x, builder tạo một **IntegrationFlow** chứa handler xử lý chunk.

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

import org.springframework.batch.integration.chunk.RemoteChunkingWorkerBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemWriter;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
public class InvoiceWorkerConfiguration {

    @Bean
    public ItemProcessor<InvoiceRow, InvoiceResult> invoiceProcessor() {
        BigDecimal factor = new BigDecimal("0.95");
        return row -> new InvoiceResult(
                row.invoiceId(),
                row.amount().multiply(factor)
                        .setScale(2, RoundingMode.HALF_UP),
                row.sourceVersion());
    }

    @Bean
    public IntegrationFlow remoteInvoiceWorker(
            @Qualifier("inboundChunkRequests") MessageChannel requests,
            @Qualifier("outboundChunkReplies") MessageChannel replies,
            ItemProcessor<InvoiceRow, InvoiceResult> invoiceProcessor,
            @Qualifier("invoiceWriter") ItemWriter<InvoiceResult> invoiceWriter) {

        return new RemoteChunkingWorkerBuilder<InvoiceRow, InvoiceResult>()
                .inputChannel(requests)
                .itemProcessor(invoiceProcessor)
                .itemWriter(invoiceWriter)
                .outputChannel(replies)
                .build();
    }
}
~~~

Worker writer `invoiceWriter` phải được định nghĩa riêng, ví dụ `JdbcBatchItemWriter` ghi qua database transaction, với unique key/idempotency. Worker cũng cần cấu hình adapter:

~~~text
Worker Spring Integration:
  durable request queue
      -> inbound listener adapter
      -> MessageChannel inboundChunkRequests
      -> remoteInvoiceWorker IntegrationFlow
      -> MessageChannel outboundChunkReplies
      -> outbound adapter
      -> durable reply queue
~~~

Các ứng dụng worker có thể chạy nhiều replica dùng **chung request queue** theo competing-consumer pattern. Mỗi replica có thể xử lý một hoặc nhiều request đồng thời tùy số consumer/container concurrency; phải kiểm tra thread safety của processor, writer, client và tài nguyên dùng chung.

### 7.1. Transaction của worker

Điều cần kiểm chứng không chỉ là “writer có dùng JDBC” mà là:

- Listener container có bắt đầu transaction phù hợp không?
- DB write có nằm trong transaction thực và commit trước khi request được ACK không?
- Publish reply có được xác nhận bền vững không?
- Nếu DB commit thành công nhưng reply publish thất bại, message có bị giao lại không?
- Nếu reply publish thành công nhưng ACK request thất bại, worker có thể được gọi lại không?
- Nếu worker call API ngoài transaction, hệ thống đích có idempotency key không?

Builder quản lý flow xử lý remote chunk, nhưng **không tự tạo distributed transaction atomic giữa DB, broker và API**.

### 7.2. Tránh chia sẻ state mutable

`ItemProcessor` dạng stateless thường dễ scale ngang. Singleton writer có thể được gọi từ nhiều request đồng thời, cần kiểm tra implementation cụ thể. Worker không nên giữ biến `currentInvoice` hoặc `currentChunk` mutable ở singleton scope. Với request/reply, state liên quan một chunk nên nằm trong message context, transaction context hoặc storage bền vững có khóa phù hợp.

## 8. Ranh giới ACK, commit và trường hợp ghi trùng

Xét ba sự kiện:

1. **D:** database commit dữ liệu nghiệp vụ.
2. **R:** reply đã được broker nhận và lưu bền vững.
3. **A:** request được broker xác nhận đã xử lý (ACK) để không cần phát lại.

Nếu ba sự kiện này không nằm trong một transaction phân tán có bảo đảm thích hợp, sẽ có những khoảng crash:

| Thời điểm gặp lỗi | Điều có thể xảy ra | Biện pháp |
| --- | --- | --- |
| Trước D | DB transaction rollback, request có thể được giao lại | Retry có giới hạn, worker xử lý lại an toàn |
| Sau D, trước R | Dữ liệu đã ghi, manager chưa nhận kết quả | Idempotent writer; replay request không gây ghi trùng |
| Sau R, trước A | Manager có thể nhận reply nhưng request vẫn bị giao lại | Dedupe request, chống gửi reply gây tổng hợp sai |
| Sau A nhưng reply không tới đúng manager | Request không còn ở queue, manager chờ/timeout | Durable replies, correlation, recovery và đối soát |
| Manager crash khi có chunk in-flight | Broker/worker vẫn có thể xử lý request cũ | Tách job execution identity, quyết định phục hồi có kiểm soát |
| Broker restart khi message chưa bền vững | Request/reply có thể mất | Durable queues, persistent messages, publisher confirm |

**Không thể bảo đảm exactly-once nghiệp vụ bằng cờ `autoAck=false` hoặc `durable=true` riêng lẻ.** Trong thực tế thường phải chấp nhận khả năng **at-least-once delivery** và bảo đảm **effectively-once business effects** qua idempotency + unique constraint + reconciliation.

### 8.1. Ví dụ writer idempotent theo khóa nghiệp vụ

PostgreSQL cho phép upsert kết quả xác định theo hóa đơn và source version:

~~~sql
CREATE TABLE invoice_result (
    invoice_id BIGINT PRIMARY KEY,
    net_amount NUMERIC(18, 2) NOT NULL,
    source_version BIGINT NOT NULL
);

INSERT INTO invoice_result(invoice_id, net_amount, source_version)
VALUES (:invoice_id, :net_amount, :source_version)
ON CONFLICT (invoice_id)
DO UPDATE SET
    net_amount = EXCLUDED.net_amount,
    source_version = EXCLUDED.source_version
WHERE invoice_result.source_version < EXCLUDED.source_version;
~~~

Nếu cùng `invoice_id`/`source_version` được gửi lại, phép ghi không tạo thêm bản ghi hoặc cộng lặp tiền. Nếu cùng phiên bản nhưng payload mâu thuẫn, cần xử lý conflict rõ ràng thay vì âm thầm coi như thành công. Nếu output phụ thuộc trạng thái hiện tại của DB, cần cân nhắc snapshot/locking và quy tắc tính lại.

Một phép ghi **không idempotent** điển hình:

~~~sql
-- Nếu cùng request bị xử lý lại, số dư có thể bị cộng thêm lần nữa.
UPDATE account_balance
SET balance = balance + :amount
WHERE account_id = :account_id;
~~~

Với thu phí, chuyển tiền, email, SMS hoặc HTTP API tạo side effect, cần **khóa idempotency ở hệ thống đích**, transactional outbox/inbox hoặc đối soát giao dịch. Một DB upsert cho bảng trung gian không tự chống gửi email hai lần.

### 8.2. Dedupe theo chunk request

Có thể có một bảng theo dõi request đã ghi nghiệp vụ:

~~~sql
CREATE TABLE processed_chunk (
    execution_key VARCHAR(120) NOT NULL,
    chunk_sequence INTEGER NOT NULL,
    committed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (execution_key, chunk_sequence)
);
~~~

Quy tắc thực hiện **trong cùng DB transaction** khi đầu ra cũng nằm trên database ấy:

~~~text
BEGIN
  INSERT processed_chunk(execution_key, sequence)
     ON CONFLICT DO NOTHING
  IF inserted:
      execute deterministic business write for all items
  ELSE:
      do not repeat business write
COMMIT

Publish success reply (kể cả khi duplicate đã xử lý xong)
ACK request theo policy listener
~~~

Đây là *pseudocode giao dịch*; cần hiện thực bằng API transaction thật và bảo đảm xử lý được two consumers race trên cùng khóa. Nếu worker ghi ở nhiều DB hoặc gọi external API, việc chèn một row vào bảng dedupe **không đủ** để bảo đảm atomic với mọi side effect.

**Execution key phải bền vững và không gây trùng giữa các job run.** Nếu restart tạo chuỗi chunk mới, idempotency ở mức sequence alone có thể không khớp công việc tương đương. Bảo vệ bằng **business key và source version** thường là lớp cần thiết ngay cả khi có dedupe request.

### 8.3. Reply duplicate và stale response

Trong hệ thống phân tán, có thể nhận hai reply cho cùng chunk, hoặc nhận reply của một JobExecution đã bị restart. Hệ thống reply routing/correlation phải:

- Kết hợp đúng run/step/chunk identifiers.
- Không cộng thống kê `StepContribution` hai lần do duplicate.
- Không lấy reply cũ làm bằng chứng thành công cho request mới.
- Ghi log và có kênh xử lý message lạc tuyến/không thể ghép.
- Đối soát thực tế khi trạng thái metadata mâu thuẫn với output.

Không sửa trực tiếp `BATCH_STEP_EXECUTION` để “cho xanh” mà chưa xác minh dữ liệu và worker cũ.

## 9. Timeout, retry và DLQ

### 9.1. Phân loại lỗi

| Loại lỗi | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| Lỗi dữ liệu cố định | JSON/schema invalid, amount sai | Reject/DLQ; skip nếu nghiệp vụ cho phép và có đối soát |
| Lỗi tạm thời worker | DB timeout, HTTP 503 | Retry có backoff, giới hạn số lần |
| Lỗi broker/transport | Network disconnect, broker failover | Kết nối lại, publisher confirm và redelivery |
| Lỗi tài nguyên | DB pool cạn, queue full, memory pressure | Backpressure; điều chỉnh concurrency/transaction |
| Mất reply | Worker đã ghi nhưng manager chưa nhận | Correlation, durable reply, kiểm tra output/idempotency |
| Worker crash | Process chết sau vài chunk | Phát lại request chưa ACK, không ghi trùng |
| Manager crash | JobRepository/queue có request chưa kết thúc | Xác nhận worker cũ, reconcile, restart đúng JobInstance |

Đừng retry mọi exception không giới hạn. Một poison message liên tục requeue có thể ngăn các request tốt phía sau được xử lý. Dùng exponential backoff với jitter, retry limit, DLQ và alert/triage rõ ràng.

### 9.2. Timeout là tín hiệu, không phải bằng chứng worker chưa ghi

Manager không thấy reply trong 30 giây có thể do:

- Worker đang xử lý chunk chậm.
- Worker commit DB xong nhưng broker mất reply.
- Reply bị route sai/thiếu correlation.
- Broker backlog lớn.
- Worker chết trước commit.
- Manager reply consumer bị lỗi hoặc chưa chạy.

**Không tự động gửi lại request và ghi output một lần nữa chỉ dựa trên timeout** nếu chưa có idempotency. Cần hiểu config timeout của manager, receive timeout của Spring Integration, message TTL và chính sách redelivery của broker.

### 9.3. DLQ không phải nơi “cất lỗi là xong”

Khi một chunk đã rơi vào DLQ, manager có thể còn chờ phản hồi và JobExecution có thể fail/timeout. Quy trình xử lý cần:

1. Xác định request gốc, business date, run/chunk identity và nguyên nhân.
2. Kiểm tra DB/output có thể đã commit trước khi message vào DLQ hay không.
3. Sửa lỗi cấu hình hoặc dữ liệu có kiểm soát.
4. Quyết định **replay đúng request** hay restart job/step, tránh tạo hai luồng xử lý cùng lúc.
5. Đối soát kết quả và ghi lại bằng chứng khôi phục.

DLQ nên được giám sát về số message, tuổi message, nguyên nhân lỗi và thời gian triage, tránh tự động xóa khi vẫn còn JobInstance cần phục hồi.

## 10. Checkpoint và restart trong remote chunking

Remote chunking chia **công việc xử lý item**, nhưng **manager vẫn chịu trách nhiệm đọc**. Vì vậy checkpoint của reader và metadata job ở manager rất quan trọng.

Nếu manager phát request #21–#25 rồi bị crash, có thể có nhiều trạng thái:

- Một số worker đã commit và gửi reply.
- Một số worker đã commit nhưng reply chưa tới.
- Một số request còn nằm trong queue.
- Một số request chưa được publish bền vững.
- `JobRepository` chưa phản ánh đầy đủ những hoạt động ngoài transaction manager.

Khi restart cùng JobInstance, phải đối soát message in-flight và dữ liệu đã ghi trước khi cho các worker mới xử lý. Chỉ khởi chạy JobInstance mới với identifying `run.id` khác **không phải restart an toàn**; việc đó có thể phát lại dữ liệu từ đầu.

### 10.1. Điều kiện để resume đáng tin cậy

- `JobRepository` bền vững, giữ `JobExecution`/`StepExecution`/`ExecutionContext` và hỗ trợ restart.
- Reader có checkpoint hợp lệ theo ItemStream và dữ liệu nguồn bất biến.
- Request/reply queues tồn tại và có routing/correlation đúng.
- Worker được kiểm soát concurrency; không có **hai thế hệ execution** cùng thực hiện tác dụng nghiệp vụ gây xung đột.
- Business writes idempotent hoặc có dedupe đúng ranh giới transaction.
- Hệ thống có quy trình phục hồi/đối soát khi manager mất trạng thái trong khi worker vẫn đang xử lý.
- Không đánh đồng reply từ execution trước với success của execution mới.

**Khác remote partitioning:** worker remote chunking thường không có StepExecution riêng cho từng message trong JobRepository. Không thể áp dụng nguyên xi logic “skip partition đã COMPLETED” để suy rằng Spring Batch sẽ tự bỏ qua mọi chunk request bị gửi lại.

### 10.2. Minh họa crash timeline

~~~mermaid
flowchart TD
    A["Manager gửi chunk #27"] --> B["Broker giao cho worker"]
    B --> C["Worker ghi DB / commit thành công"]
    C --> D{"Manager đã nhận reply?"}
    D -->|Có| E["Ghi nhận chunk hoàn tất"]
    D -->|Không| F["Mất reply / manager crash"]
    F --> G["Kiểm tra trạng thái, output và broker"]
    G --> H["Replay/restart có kiểm soát"]
    H --> I["Writer idempotent / request dedupe"]
    I --> E
~~~

Đây là lý do cần tích hợp **failure tests** ngay từ đầu, không chờ tới production mới xử lý duplicate.

## 11. Thiết kế thread safety trong worker pool

Một request chunk có thể được xử lý bởi bất kỳ worker instance nào. Với nhiều message listener threads trong cùng worker JVM, processor, writer và service singleton có thể được gọi đồng thời:

| Component | Vấn đề điển hình | Kiểm soát |
| --- | --- | --- |
| Processor | Biến `currentItem` mutable, cache không an toàn | Stateless/immutable, concurrent data structures khi cần |
| Writer | Buffer instance dùng chung, transaction bị lẫn | Implementation thread-safe, transaction-bound resource |
| HTTP client | Connection pool thiếu hoặc không an toàn | Client đúng hợp đồng, max in-flight và timeout |
| DB pool | Nhiều consumer chờ connection | Hikari pending/acquire latency, connection budget |
| Message converter | Mutable serializer state | Thread-safe converter và schema version |
| Retry listener | Counter mutable trong bộ nhớ | Metrics thread-safe; không dùng count memory thay commit count |
| Log/trace | Thiếu correlation, log PII | MDC theo request, redaction và retention |

Một worker instance có thể nhận cùng loại request từ nhiều JobExecution. Không giữ state “kỳ dữ liệu hiện tại” trong biến static/singleton mà không gắn với request identity.

## 12. Capacity planning: khi nào tăng workers thực sự có ích?

Đặt các thông số minh họa:

- `N` = 10.000.000 item cần xử lý.
- `K` = 200 item/chunk.
- `D` = 1 giờ dành riêng cho xử lý.
- `S` = 0,25 giây latency trung bình để một worker xử lý và ghi **một chunk** khi downstream còn đủ capacity.

Throughput yêu cầu:

\[
R_{\text{items}} = \frac{10{,}000{,}000}{3600}
\approx 2{,}778\text{ item/s}.
\]

Số chunk/giây cần gửi/hoàn tất:

\[
R_{\text{chunks}} = \frac{2{,}778}{200}
\approx13{,}89\text{ chunk/s}.
\]

Theo Little's law với **latency trung bình** 0,25 s cho xử lý worker:

\[
L_{\text{worker}}\approx13{,}89\times0{,}25
\approx3{,}47\text{ chunk in-flight trung bình}.
\]

Tối thiểu về mặt trung bình cần khoảng **4 worker request executions đồng thời** nếu mọi giả định giữ nguyên. Nhưng để xử lý tail latency, retry, message overhead và biến động I/O, phải thử một mức cao hơn và đặt backpressure; không suy ra đây là cấu hình production chính xác.

### 12.1. Đường ống có nhiều trần throughput

Throughput thực không vượt năng lực yếu nhất:

\[
R_{\text{end-to-end}} \le
\min(R_{\text{reader}},
R_{\text{broker}},
R_{\text{workers}},
R_{\text{database}},
R_{\text{reply/aggregation}}).
\]

Ví dụ manager reader chỉ đạt 2.000 item/s trong khi mục tiêu là 2.778 item/s. Dù thêm 20 worker, không thể đạt mục tiêu với cùng reader/nguồn. Cần tối ưu truy vấn, giảm chi phí parse hoặc thay kiến trúc để nhiều worker **tự đọc** (remote partitioning) nếu dữ liệu chia được.

### 12.2. Tính số message và kích thước payload

Với `N=10.000.000`, `K=200`:

\[
M_{\text{request}}\approx
10{,}000{,}000/200=50{,}000\text{ request messages}.
\]

Nếu mỗi item serialize trung bình 2 KiB, payload một request khoảng:

\[
200\times2\text{ KiB}=400\text{ KiB}
\]

chưa kể headers/serialization overhead và framing. 50.000 request messages tạo khoảng **19 GiB payload logic** trước compression/overhead, và còn có reply traffic. Kiểm tra giới hạn max message size, disk, publisher throughput, memory và broker retention. Nếu item rất lớn, có thể nên gửi **tham chiếu đến dữ liệu** hoặc chọn remote partitioning thay vì gửi toàn bộ item qua broker.

### 12.3. Điều chỉnh chunk size và concurrency

| Tham số | Tăng lên có thể giúp | Nhưng có thể gây |
| --- | --- | --- |
| Chunk size | Ít message hơn, ít overhead dispatch | Payload lớn, retry scope lớn, worker transaction dài |
| Worker replicas | Thêm CPU/JVM/HTTP clients | Tổng DB connections/lock/API quota tăng |
| Consumers mỗi worker | Tăng in-flight khi worker thường chờ I/O | Thread safety, memory và pool exhaustion |
| Manager send window | Giúp worker không bị đói việc | Broker backlog/memory, khó recovery nếu in-flight quá lớn |
| Broker prefetch | Giảm round-trip nhận message | Message nằm trong worker chờ lâu, fairness kém |
| Queue retention/TTL | Chặn message quá cũ tồn tại mãi | Hết TTL khi worker vẫn xử lý hợp lệ, mất request/reply |

Không thay cả chunk size, số pods, prefetch và DB pool trong cùng một benchmark; khi throughput tăng/giảm sẽ khó xác định nguyên nhân.

## 13. Nút thắt trong mô hình remote chunking

### 13.1. Manager reader là cổ chai

Nếu reader ở manager parse dữ liệu quá chậm hoặc query khóa DB lâu, worker queue rỗng dù nhiều worker idle. Cần xem read items/s, thời gian đọc/nhóm chunk, source query, CPU/GC của manager và I/O từ nguồn.

### 13.2. Broker có backlog tăng liên tục

Nếu request enqueue nhanh hơn completion rate, queue depth và oldest-message age tăng. Cần so sánh manager enqueue, worker dequeue, worker commit và reply rates. Không mặc định cứ tăng replicas là đủ: có thể DB/API đã bão hòa hoặc messages quá lớn.

### 13.3. Writer database là cổ chai

Nhiều workers cùng upsert bảng có index nóng hoặc khóa chung có thể làm TPS giảm. Kiểm tra row lock, deadlock, WAL/log flush, IOPS, connection pool active/pending, transaction duration và batch SQL. Tăng concurrency thêm khi DB đã bão hòa thường làm SLA xấu hơn.

### 13.4. Reply queue hoặc correlation bị lỗi

Request queue giảm nhưng manager vẫn chờ, reply queue tăng hoặc nhận được nhiều unmatched replies. Phải kiểm tra header mapping, reply destination, consumer lifecycle và lỗi deserialization, không kết luận ngay worker chưa ghi.

### 13.5. Retry storm

Khi DB trả timeout/HTTP API trả 429, nếu mọi worker retry ngay, số request/giây có thể tăng trong khi thành công giảm. Giới hạn retry, backoff với jitter, rate limiter và circuit breaker theo nghiệp vụ; yêu cầu chống lặp vẫn phải áp dụng.

## 14. Quan sát và vận hành remote chunking

Các nhóm metric quan trọng:

| Nhóm | Metric | Câu hỏi |
| --- | --- | --- |
| Manager | item read/s, request sent/s, outstanding requests, reply matched/unmatched, StepExecution status | Manager có tạo đủ việc không? Reply có đối chiếu đúng không? |
| Broker | ready/unacked queue depth, oldest age, redelivery count, DLQ, publish confirm latency | Broker hay worker đang chậm? Có request thất lạc/độc hại? |
| Workers | active consumers, processed chunks/s, p95/p99 processing latency, failures, retries | Worker có tăng throughput khi scale không? |
| Database/API | connection active/pending, lock wait, transaction TPS, API 429/5xx/latency | Downstream còn capacity không? |
| JVM/OS | CPU quota, heap/GC, thread count, network, disk I/O | Quá tải process hay tài nguyên máy? |
| Data quality | unique business keys, expected vs committed count, checksum/reconciliation | Có duplicate/lost effects không? |
| SLA | expected finish, remaining backlog time, recovery cushion | Có nguy cơ trễ deadline khi worker hoặc broker lỗi không? |

Đừng chỉ theo dõi queue depth. Queue depth bằng 0 có thể vì broker đã giao hết nhưng hàng nghìn message đang **unacked** hoặc đang chạy chậm. Ngược lại queue depth lớn có thể là do manager chủ động phát ahead nhưng downstream vẫn đang đáp ứng deadline.

### 14.1. Log theo request identity

Ví dụ bản ghi log **tự thiết kế**, không phải JSON mặc định của Spring Batch:

~~~json
{
  "job": "invoiceJob",
  "jobExecutionId": 204,
  "step": "invoiceManagerStep",
  "chunkSequence": 37,
  "requestId": "run204-chunk37",
  "workerId": "invoice-worker-3",
  "attempt": 2,
  "itemCount": 200,
  "dbCommit": true,
  "replyPublished": true,
  "durationMs": 312
}
~~~

Các ID phải tương ứng với contract/correlation thực; đừng tạo `requestId` ngẫu nhiên mới khi broker redeliver rồi gọi đó là cùng một chunk. Không log payload đầy đủ nếu chứa thông tin nhạy cảm hoặc khối lượng lớn.

### 14.2. Alert gắn với hành động

- **Manager đọc chậm:** reader throughput thấp hơn tốc độ cần thiết trong cửa sổ SLA.
- **Queue lag cao:** oldest request age và ước lượng drain time vượt recovery budget.
- **Reply lag:** requests được consume nhưng replies không tăng tương ứng.
- **DLQ > 0:** có message cần triage; phân biệt lỗi dữ liệu cố định với sự cố hệ thống.
- **Duplicate/replay tăng:** kiểm tra worker crash, broker ACK, serializer và idempotency.
- **SLA at-risk:** ETA dựa trên **thời gian còn lại + backlog + validation/publish** đã vượt deadline nội bộ.

Cần có owner, severity, dashboard liên quan và runbook cụ thể; alert khi JobExecution đã `FAILED` thường là quá muộn để giữ thời gian dự phòng phục hồi.

## 15. Kiểm thử end-to-end qua nhiều tiến trình

Dùng một snapshot bất biến với 100.000 hóa đơn có khóa duy nhất; thiết lập manager, broker và ít nhất hai worker JVM/container. Đối soát output sau mỗi kịch bản.

| Kịch bản | Cách kiểm tra | Kết quả mong đợi |
| --- | --- | --- |
| Baseline | Chạy 1 worker với request/reply thực | Đúng số lượng, giá trị và thời gian đo được |
| Competing consumers | Chạy 3 workers cùng request queue | Mỗi lần delivery được phân công cho một consumer; không fanout sang cả ba |
| Out-of-order replies | Làm worker B chậm hơn worker C | Manager ghép reply đúng chunk, không lệ thuộc thứ tự về |
| Duplicate request | Publish/giao lại cùng ChunkRequest | Không tạo duplicate business effect |
| Worker crash trước DB commit | Kill worker khi đang write | DB rollback; request redelivery xử lý thành công |
| Worker crash sau DB commit | Kill trước khi reply/ACK hoàn tất | Replay an toàn, writer idempotent |
| Manager crash giữa batch | Kill manager khi đang có in-flight | JobRepository còn; có quy trình reconcile/restart an toàn |
| Broker restart | Restart broker với queue đang có messages | Chỉ các message có bảo đảm durability đã cấu hình được khôi phục đúng |
| Reply lost/route sai | Chặn reply consumer hoặc sai correlation | Manager timeout/alert đúng, không tự ghi trùng |
| Poison message | Cho payload schema invalid | Retry hữu hạn, vào DLQ/được phân loại, không requeue vô tận |
| DB saturation | Hạ connection pool / tăng worker pods | Metric pending tăng; backpressure thay vì retry storm |
| API 429/503 | Giả lập rate limit | Backoff/jitter và giới hạn in-flight |
| Mixed-version workers | Deploy hai version contract nếu policy cho phép | Message schema version tương thích hoặc reject có kiểm soát |
| Peak workload | Tăng volume, item size, skew và latency | Throughput, heap, queue, reply và SLA trong budget |

**Đừng dùng mock-only test** để kết luận hệ thống restart được. Cần thử ít nhất một lần worker crash thật sau DB commit, một lần broker restart và một lần manager crash, kiểm tra cả metadata của `JobRepository` lẫn dữ liệu đầu ra.

### 15.1. Bất biến dữ liệu khi nghiệm thu

~~~text
Distinct business IDs in output == Expected IDs for snapshot
No invoice missing and no invalid invoice added
Final amount and source version match independent reference
Replay / redelivery does not increase business side effects
All required chunk replies are matched or failure is made visible
After controlled restart, final output == clean-run output
~~~

Một job có `BatchStatus.COMPLETED` nhưng thiếu hóa đơn vì một worker bị “ACK sớm” vẫn là thất bại nghiệp vụ. Đối soát output là điều kiện quan trọng ngang với metadata.

## 16. Chọn remote chunking hay remote partitioning?

Dùng câu hỏi quyết định:

1. **Có cần scale reader không?** Nếu có, remote partitioning thường phù hợp hơn vì worker tự đọc shard. Remote chunking để reader ở manager.
2. **Có thể chia dữ liệu thành phạm vi độc lập không?** Nếu có file/ID range ổn định, partitioning cho checkpoint riêng từng partition; nếu không, remote chunking có thể đơn giản hóa việc phân phối công việc processor.
3. **Chi phí truyền item qua broker có chấp nhận được không?** Item lớn và nguồn gần worker khiến remote partitioning hoặc gửi reference tiết kiệm hơn.
4. **Có cần cô lập checkpoint theo shard không?** Remote partitioning có StepExecution/ExecutionContext theo partition; remote chunking giữ quản lý reader/chunk ở manager.
5. **Độ khó vận hành middleware có đáng không?** Với workload đạt SLA trên một JVM, remote làm tăng điểm lỗi mà không cần thiết.
6. **Downstream có đủ năng lực không?** Nếu writer DB bão hòa, cả hai mô hình đều không tăng throughput theo số workers.

Ví dụ workload:

- Manager đọc file 400 MB rất nhanh; mỗi item gọi AI/OCR tốn CPU, worker độc lập: **remote chunking** có thể hợp lý.
- Dữ liệu gồm 100 file độc lập, mỗi file vài GB; worker có quyền đọc trực tiếp object storage: **remote partitioning** thường hợp lý.
- Database nguồn chỉ cho một query rất chậm và worker không thể tự đọc: trước tiên **tối ưu nguồn/query**, không kỳ vọng remote chunking sửa nút thắt.
- 300.000 item xử lý xong trong 10 phút trên một JVM, cửa sổ SLA là 3 giờ: giữ **local chunk step** thường đơn giản hơn.

## 17. Checklist trước production

- [ ] SLA, data volume, peak/seasonality và throughput commit mục tiêu đã được định lượng.
- [ ] Đã chứng minh **manager reader không là bottleneck chính**.
- [ ] Request queue dùng competing-consumer semantics, durable queue/persistent publish và ACK phù hợp.
- [ ] Reply path bền vững, routing và correlation đúng từng run/chunk; kiểm tra header mapping.
- [ ] Có giới hạn in-flight, broker backlog, max payload size, worker concurrency và backpressure.
- [ ] Message contract có version, serialization phù hợp và kiểm tra an toàn dữ liệu.
- [ ] Worker processor/writer/service thread-safe khi nhiều consumer trong một JVM.
- [ ] DB write có transaction, unique constraints và idempotency; external side effects có biện pháp riêng.
- [ ] Có retry hữu hạn, backoff/jitter, DLQ, alert và quy trình replay có kiểm soát.
- [ ] JobRepository bền vững, reader checkpoint đúng và input snapshot bất biến.
- [ ] Đã thử worker crash **trước/sau commit**, manager crash, mất reply và broker restart.
- [ ] Monitoring đủ request/reply rates, queue ready/unacked, latency p95/p99, DB/API và SLO.
- [ ] Đã tính tổng DB connection/API quota từ toàn bộ worker pods và online workloads.
- [ ] Có runbook phân biệt retry chunk, restart JobInstance và reprocess nghiệp vụ.
- [ ] Đã đối soát output sau một clean run và sau các lần failure/recovery.

## 18. Câu hỏi tự kiểm tra

1. Trong remote chunking, thành phần nào đọc item và thành phần nào ghi output? Tại sao đây không phải remote partitioning?
2. Vì sao request queue cần competing consumers thay vì publish/subscribe fanout?
3. Manager gửi chunk #10 rồi #11, nhưng reply #11 tới trước #10. Điều gì cần xảy ra?
4. Worker đã commit DB nhưng chết trước khi gửi reply. Vì sao retry cùng request có thể gây ghi trùng? Giải pháp nào có thể kiểm chứng?
5. Có durable queue nhưng publish message ở chế độ non-persistent. Điều đó có bảo đảm message sống qua broker restart không?
6. Vì sao `maxWaitTimeouts(40)` không đồng nghĩa đúng 40 giây?
7. Request queue rỗng nhưng `unacked` rất lớn và worker CPU thấp. Nên điều tra những nguyên nhân nào?
8. Manager đọc 1.000 item/s, SLA cần 4.000 item/s; thêm 20 worker có đạt mục tiêu không?
9. Remote chunking có bảo đảm worker được chạy exactly-once và side effect ngoài DB chỉ xảy ra một lần không?
10. Khi broker giao lại chunk nhưng execution/chunk sequence có thể thay đổi sau restart, vì sao cần idempotency **theo khóa nghiệp vụ**?
11. Chunk 200 item, item serialize trung bình 2 KiB: chỉ riêng payload request khoảng bao nhiêu KiB? Kéo theo cần kiểm tra tài nguyên nào?
12. Khi nào nên ưu tiên remote partitioning hơn remote chunking?

**Gợi ý đáp án:** (1) Manager đọc và chia chunk, worker xử lý/ghi; remote partitioning để worker tự đọc phạm vi. (2) Mỗi delivery cần một consumer xử lý, fanout gây nhân bản công việc. (3) Correlate theo request/run/sequence, không giả định thứ tự về. (4) At-least-once delivery có thể phát lại; DB upsert/unique key và dedupe transaction. (5) Không đủ; durability phụ thuộc queue và message persistence cùng bảo đảm broker. (6) Nó là số lần chờ, thời lượng phụ thuộc receive timeout. (7) Worker giữ message khi chờ DB/API, listener concurrency/prefetch, ACK hoặc transaction đang bị kẹt. (8) Không nếu reader là trần cố định. (9) Không; cần transaction/idempotency/outbox. (10) Sequence không phải khóa business ổn định qua mọi dạng reprocess. (11) Khoảng 400 KiB chưa kể overhead; kiểm tra broker max size, network/memory và retry scope. (12) Khi shard độc lập, reader cần scale hoặc muốn checkpoint theo partition.

## Tài liệu tham khảo

- [Spring Batch 5.2 Reference — Scaling and Parallel Processing / Remote Chunking](https://docs.spring.io/spring-batch/reference/5.2/scalability.html): kiến trúc manager/worker và yêu cầu middleware bảo đảm delivery tới một consumer cho mỗi request.
- [Spring Batch Reference — Spring Batch Integration: Externalizing Execution](https://docs.spring.io/spring-batch/reference/spring-batch-integration/externalizing-execution.html): cách Spring Integration hỗ trợ remote chunking, request/reply channels và worker handler.
- [Spring Batch 5.2 API — RemoteChunkingManagerStepBuilder](https://docs.spring.io/spring-batch/docs/5.2.x/api/org/springframework/batch/integration/chunk/RemoteChunkingManagerStepBuilder.html): `inputChannel`, `outputChannel`, `maxWaitTimeouts` và manager builder.
- [Spring Batch 5.2 API — RemoteChunkingWorkerBuilder](https://docs.spring.io/spring-batch/docs/5.2.x/api/org/springframework/batch/integration/chunk/RemoteChunkingWorkerBuilder.html): cấu hình worker integration flow và processor/writer.
- [Spring Batch 5.2 API — Remote Chunking Package](https://docs.spring.io/spring-batch/docs/5.2.x/api/org/springframework/batch/integration/chunk/package-summary.html): `ChunkRequest`, `ChunkResponse`, `ChunkMessageChannelItemWriter` và handler.
- [Spring Integration Reference](https://docs.spring.io/spring-integration/reference/): message channels, adapters, error handling và kết nối JMS/AMQP.
- [RabbitMQ — Reliability Guide](https://www.rabbitmq.com/docs/reliability): acknowledgements, confirms, durability và giới hạn fault tolerance.

**Điểm cốt lõi:** Remote chunking đưa **xử lý và ghi chunk** ra các worker JVM, nhưng **manager vẫn đọc dữ liệu và quản lý tiến độ step**. Middleware cần work queue có competing consumers, request/reply đáng tin cậy và correlation chính xác. Tăng worker chỉ có lợi khi manager và downstream chưa nghẽn; an toàn dữ liệu vẫn dựa trên checkpoint, transaction, idempotency và các phép kiểm thử crash/replay. Hãy chọn remote chunking khi chi phí xử lý chunk lớn hơn đáng kể chi phí đọc và truyền chunk, đồng thời có đội ngũ và hạ tầng đủ khả năng vận hành một pipeline phân tán.
