# Reply channel của worker

Trong Spring Batch **remote chunking**, manager đọc các item, tạo `ChunkRequest` và gửi chúng qua middleware. Worker nhận chunk, thực hiện xử lý/ghi dữ liệu rồi phát một **phản hồi** qua **reply channel** để manager biết kết quả tương ứng với yêu cầu đã gửi. Nếu worker ghi thành công nhưng không phát được reply, hoặc phát reply nhưng manager không nhận được, công việc có thể đã tạo tác động nghiệp vụ trong khi trạng thái của manager vẫn chưa rõ. Vì vậy, reply channel là một phần của **giao thức hoàn thành công việc**, không chỉ là một đường truyền thông điệp.

Bài học thuộc chương **Thông điệp phân tán** của module **SPRING_BATCH_SCALING_OPERATIONS**. Module tập trung mở rộng Spring Batch cho workload dữ liệu lớn bằng multi-threaded step, parallel steps, partitioning và các mô hình phân tán, đồng thời đo nút thắt, giữ thread safety, retry/restart, vận hành job và chọn kiến trúc theo tài nguyên thực tế. Chủ đề này đi sâu vào **vai trò, cấu hình, định tuyến, độ bền, correlation, xử lý lỗi và quan sát reply channel của worker**.

> **Ghi nhớ trước tiên:** `workerReplies` là nơi worker **đưa kết quả ra khỏi integration flow trong ứng dụng worker**; nó không tự trở thành một hàng đợi ở broker. Muốn manager ở JVM khác nhận được reply, phải có **outbound adapter từ worker đến middleware** và **inbound adapter từ middleware đến input channel của manager**, với payload và metadata tương thích.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích đường đi **manager request → broker → worker → reply channel → broker → manager reply input** trong Spring Batch Integration.
2. Phân biệt `outputChannel` của worker, **broker reply destination**, và `inputChannel` ở manager.
3. Dựng bộ khung remote chunking trên Java 17+/Spring Batch 5.x với `RemoteChunkingWorkerBuilder` và `RemoteChunkingManagerStepBuilder`.
4. Hiểu lý do reply phải giữ đúng **protocol metadata/correlation**, không chỉ chứa một cờ `SUCCESS`.
5. Phân biệt **DB commit, request ACK, publish reply, publisher confirm và manager nhận reply**.
6. Đánh giá reply channel trực tiếp/bất đồng bộ, broker queue bền vững, consumer routing, timeout, retry và duplicate.
7. Ngăn worker bị treo hoặc job báo thành công giả khi reply mất, đến muộn, sai destination hay sai execution.
8. Kiểm thử end-to-end với broker thực, worker failure sau commit, reply duplicate/out-of-order, manager restart và đối soát business output.
9. Thiết lập metric, cảnh báo và runbook cho các sự cố trên reply path.

**Tình huống xuyên suốt:** job chốt sổ một triệu giao dịch. Manager đọc nguồn, phát các chunk 200 item tới RabbitMQ/JMS hoặc middleware được hỗ trợ; bốn worker xử lý/ghi vào PostgreSQL. Có lúc một worker đã commit 200 item nhưng kết nối tới reply broker ngắt ngay sau đó. Manager không được tự coi 200 item ấy là “chưa từng xử lý”; khi replay, writer phải chống ghi trùng và reply phải ghép đúng request.

## 2. Ba khái niệm thường bị gọi chung là “reply channel”

| Thành phần | Nằm ở đâu? | Ai ghi/đọc? | Bản chất |
| --- | --- | --- | --- |
| **Worker output channel** (ví dụ `workerReplies`) | Spring Integration trong ứng dụng worker | Remote chunk worker flow **gửi** response vào channel; outbound adapter **tiêu thụ** | `MessageChannel`, thường là đường nối **nội bộ JVM** |
| **Reply queue/topic/destination** (ví dụ `batch.chunk.replies`) | Middleware/message broker | Worker outbound adapter **publish**; manager inbound adapter **consume** | Hạ tầng vận chuyển; có thể bền vững hoặc không tùy cấu hình |
| **Manager input channel** (ví dụ `managerReplies`) | Spring Integration trong ứng dụng manager | Manager inbound adapter **đưa** reply vào; manager step/gateway **nhận** | `MessageChannel` nối reply về logic tổng hợp của Spring Batch |

Ba thành phần này phải được nối theo đúng chiều. Chỉ khai báo:

~~~java
@Bean
MessageChannel workerReplies() {
    return new DirectChannel();
}
~~~

**chưa có nghĩa** worker đã gửi một byte dữ liệu nào qua mạng. `DirectChannel` mặc định chuyển message cho subscriber nội bộ trên thread gọi (nếu có subscriber), không tự tạo broker queue, không có bền vững xuyên JVM và có thể báo lỗi nếu không có subscriber phù hợp.

### Đường đi của một phản hồi

~~~mermaid
flowchart LR
    subgraph Manager["Manager JVM"]
        MS["Remote chunk manager step"]
        MQ["managerRequests"]
        MR["managerReplies"]
    end
    subgraph Broker["Middleware"]
        RQ[("Request queue")]
        PQ[("Reply queue")]
    end
    subgraph Worker["Worker JVM"]
        WR["workerRequests"]
        WF["Remote chunk worker flow"]
        WP["workerReplies"]
    end
    MS --> MQ
    MQ -->|"request outbound adapter"| RQ
    RQ -->|"worker inbound adapter"| WR
    WR --> WF
    WF --> WP
    WP -->|"reply outbound adapter"| PQ
    PQ -->|"manager inbound adapter"| MR
    MR --> MS
~~~

Nếu bỏ mất cạnh **`workerReplies → reply outbound adapter → reply queue`**, worker có thể đã tạo response nhưng không gửi được đến manager. Nếu thiếu cạnh **`reply queue → manager inbound adapter → managerReplies`**, broker có thể vẫn giữ response nhưng manager chờ mãi.

## 3. Reply channel làm gì trong remote chunking?

Trong remote chunking, manager thường chịu trách nhiệm:

- Dùng `ItemReader` để đọc nguồn.
- Nhóm item thành chunk và gửi yêu cầu xử lý.
- Theo dõi những yêu cầu đang đợi kết quả theo giao thức của Spring Batch Integration.
- Nhận `ChunkResponse`, tổng hợp đóng góp/trạng thái hoặc lỗi và điều phối tiến trình job.
- Quản lý metadata/checkpoint đọc và trạng thái StepExecution phù hợp.

Worker thường chịu trách nhiệm:

- Nhận `ChunkRequest` đã chứa item do manager đọc.
- Gọi `ItemProcessor` và `ItemWriter` theo flow/transaction được cấu hình.
- Trả `ChunkResponse` hoặc báo lỗi theo protocol thay vì gửi một message tùy ý.
- Không tự đọc toàn bộ nguồn từ đầu trừ khi kiến trúc định nghĩa rõ một tham chiếu snapshot.

Trong **remote partitioning**, worker lại có một **worker StepExecution** đọc chính vùng dữ liệu của nó và trả kết quả partition/StepExecution cho manager. Hai mô hình đều có thể có reply channel, nhưng **kiểu payload, granularity và điều kiện hoàn tất khác nhau**.

| Tiêu chí | Remote chunking | Remote partitioning |
| --- | --- | --- |
| Manager giao công việc | Chunk gồm item đã đọc | Partition/StepExecution với ExecutionContext |
| Worker đọc dữ liệu nguồn? | Thông thường không | Có, đọc vùng được giao |
| Reply gắn với | `ChunkRequest`/chunk sequence hoặc metadata protocol | Partition execution/StepExecution |
| Vấn đề khi reply mất | Manager chưa thể biết outcome của chunk | Manager chưa biết kết quả worker step |
| Khả năng replay | Có thể xử lý lại item đã ghi | Có thể restart worker step/partition |

**Không được** dùng reply channel của một flow remote chunking để gửi `StepExecution` tùy biến rồi giả định manager vẫn correlate đúng. Phải giữ nguyên contract mà Spring Batch Integration ở phiên bản ứng dụng yêu cầu.

## 4. Chu trình request/reply nhìn từ worker

~~~mermaid
sequenceDiagram
    participant M as Manager
    participant B as Broker request
    participant W as Worker
    participant DB as Business DB
    participant R as Broker reply
    M->>B: ChunkRequest / protocol identity
    B->>W: Deliver chunk
    W->>W: Processor + Writer
    W->>DB: Commit hoặc rollback
    DB-->>W: DB outcome
    W->>R: Publish ChunkResponse
    R-->>W: Publisher confirmation, nếu cấu hình
    R->>M: Deliver response
    M->>M: Match reply và cập nhật step
~~~

**Sơ đồ chỉ minh họa các mốc logic.** Broker request ACK, reply publish, publisher confirm, DB commit có thể xảy ra theo thứ tự khác tùy adapter, transaction và acknowledgment policy. **Không có một ACID transaction mặc định bao trùm cả DB, hai message destination và JobRepository.**

Một chuỗi thành công nên chứng minh được:

1. Worker nhận yêu cầu **hợp lệ** và hiểu đúng schema/protocol.
2. Processor/writer hoàn thành theo transaction policy, không để kết quả sai bị coi là success.
3. Worker tạo **response phù hợp với request**, có correlation/sequence mà manager cần.
4. Reply được publish tới **đúng destination**, với độ bền phù hợp.
5. Manager nhận và match đúng response, không nhầm với request khác.
6. Metadata batch và business output được đối soát trước khi coi toàn pipeline hoàn tất.

## 5. Hợp đồng phản hồi: không chỉ gửi “SUCCESS”

Spring Batch Integration sử dụng các kiểu như `ChunkRequest` và `ChunkResponse` cho remote chunking. Nội dung protocol có thông tin cần thiết để ghép kết quả, đóng góp vào step và xử lý lỗi. **Định dạng wire chính xác phụ thuộc phiên bản và serializer**, vì vậy không nên thay response của framework bằng một string hoặc JSON tự nghĩ nếu không viết lại cả giao thức.

Để hình dung những thông tin **có vai trò** trong một reply, xét một envelope nghiệp vụ **chỉ mang tính minh họa**, **không phải `ChunkResponse` chính thức**:

~~~json
{
  "protocolVersion": 1,
  "correlationId": "c0b2b8e2-9a85-46a7-a21e-a9c7b8309ae7",
  "jobExecutionId": 845,
  "stepExecutionId": 1092,
  "logicalChunkId": "batch-20261126/chunk-42",
  "attempt": 1,
  "status": "SUCCEEDED",
  "processedItems": 200
}
~~~

**Ý nghĩa các trường minh họa:**

- `correlationId`: giúp nhận diện request/reply exchange.
- `jobExecutionId`/`stepExecutionId`: hỗ trợ chặn nhầm phản hồi của lần chạy khác.
- `logicalChunkId`: nhận diện phần việc logic, hữu ích khi replay.
- `attempt`: phân biệt các lần gửi thử nếu giao thức chọn per-attempt identity.
- `status`: phản ánh outcome theo hợp đồng xử lý.
- `processedItems`: số item theo quy tắc đếm nhất quán; không thay thế việc đối soát DB.

Trong Spring Batch remote chunking, một phần thông tin tương ứng có thể nằm **trong payload** thay vì header `correlationId`, hoặc theo `sequence`/execution metadata của framework. Cần **giữ nguyên payload/header cần thiết** qua outbound và inbound adapter. Không tự suy ra tên header phổ quát cho mọi transport.

### Những định danh dễ nhầm

| Định danh | Mục đích | Có thay được correlation không? | Có chống ghi trùng được không? |
| --- | --- | --- | --- |
| Broker message ID | Nhận diện một message theo broker/producer | Không mặc định | Không |
| Request/reply correlation | Ghép response với request | Đúng vai trò của nó | **Không** |
| Chunk sequence | Thứ tự/chunk identity trong protocol | Chỉ khi framework quy định đủ namespace | Không ổn định cho mọi record khi restart |
| StepExecution ID | Lần thực thi step | Không đủ để phân biệt các chunk cùng step | Không |
| Trace ID | Nối log/span của một luồng phân tán | Không: có thể gồm nhiều request | Không |
| Business/idempotency key | Nhận diện một tác động nghiệp vụ | Không thay protocol request/reply | **Có**, nếu sink thi hành dedup đúng |

**Ví dụ:** request có correlation A đã ghi `tx-1001`; vì reply A thất lạc, manager phát request B chứa lại `tx-1001` với correlation B. Hai correlation khác nhau nhưng **cùng một business operation**. Writer phải chống trùng dựa trên `(batchKey, transactionId)`, không dựa trên A/B.

## 6. Dựng khung worker với outputChannel

Ví dụ **Spring Batch Integration 5.x + Java 17+**, minh họa các bean Spring Integration trong ứng dụng worker. Đoạn cấu hình cố ý tách **channel nội bộ** khỏi **adapter của broker** để làm rõ trách nhiệm:

~~~java
@Configuration
class WorkerChunkingConfiguration {
    @Bean
    MessageChannel workerRequests() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel workerReplies() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow workerChunkFlow(
            @Qualifier("workerRequests") MessageChannel requests,
            @Qualifier("workerReplies") MessageChannel replies,
            ItemProcessor<SaleInput, SaleOutput> processor,
            ItemWriter<SaleOutput> writer) {

        return new RemoteChunkingWorkerBuilder<SaleInput, SaleOutput>()
                .itemProcessor(processor)
                .itemWriter(writer)
                .inputChannel(requests)
                .outputChannel(replies)
                .build();
    }
}
~~~

`SaleInput`, `SaleOutput`, `processor` và `writer` là các thành phần nghiệp vụ được triển khai riêng. Cần dependency **Spring Batch Integration**, Spring Integration cùng adapter middleware tương thích với phiên bản dự án.

Trong ví dụ, `.outputChannel(replies)` **chỉ cấu hình đích phát phản hồi bên trong worker JVM**. Cần một **integration flow gửi những message từ `workerReplies` sang broker**. Worker không được tạo một `Message<SomeCustomResponse>` tùy tiện để thay payload mà `RemoteChunkingWorkerBuilder` sinh ra.

### Minh họa mô hình lắp ghép

~~~text
workerRequests: MessageChannel
  <- broker inbound adapter (request queue)
  <- serialized ChunkRequest

RemoteChunkingWorkerBuilder
  inputChannel(workerRequests)
  itemProcessor(...)
  itemWriter(...)
  outputChannel(workerReplies)

workerReplies: MessageChannel
  -> broker outbound adapter (reply destination)
  -> serialized ChunkResponse + required headers
~~~

**Điểm dễ nhầm:** nếu cấu hình `workerReplies` là `QueueChannel` nhưng không có subscriber/poller chuyển message ra broker, response sẽ **chỉ nằm trong queue nội bộ JVM** (cho đến khi hết capacity hoặc JVM chết). Tương tự, `ExecutorChannel` không biến response thành message bền vững; nó chỉ đổi cách dispatch trong JVM.

## 7. Khung manager nhận reply tương ứng

Ở manager, `inputChannel` đóng vai trò **đầu vào của các phản hồi đến từ broker**:

~~~java
@Configuration
class ManagerChunkingConfiguration {
    @Bean
    MessageChannel managerRequests() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel managerReplies() {
        return new DirectChannel();
    }

    @Bean
    Step remoteChunkManagerStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            ItemReader<SaleInput> reader,
            @Qualifier("managerRequests") MessageChannel requests,
            @Qualifier("managerReplies") MessageChannel replies) {

        return new RemoteChunkingManagerStepBuilder<SaleInput, SaleOutput>(
                "remoteChunkManagerStep", jobRepository)
                .chunk(200, transactionManager)
                .reader(reader)
                .outputChannel(requests)
                .inputChannel(replies)
                .build();
    }
}
~~~

`managerRequests` phải được nối tới **request outbound adapter**. `managerReplies` phải được nối từ **reply inbound adapter**. Nếu hai channel chỉ được khai báo mà không có bridge thực tế, manager và worker ở hai máy sẽ không giao tiếp.

**Lưu ý phiên bản:** Spring Batch Integration 4.x, 5.x và các nhánh sau có thể khác chữ ký builder, thành phần transaction hoặc kiểu container. Mã ở đây là **bộ khung mang tính giáo dục**, cần đối chiếu API artifact đã khóa và chạy integration test trước khi áp dụng sản xuất. Không giả định việc đặt các bean trong **cùng** một application context là mô hình triển khai remote đầy đủ.

## 8. Nối workerReplies với broker: những quyết định bắt buộc

Ví dụ với một hệ thống message broker có request destination `batch.chunk.requests` và reply destination `batch.chunk.replies`:

~~~text
MANAGER
  outputChannel(managerRequests)
    -> outbound adapter -> batch.chunk.requests

WORKER
  inbound adapter(batch.chunk.requests) -> inputChannel(workerRequests)
  outputChannel(workerReplies) -> outbound adapter(batch.chunk.replies)

MANAGER
  inbound adapter(batch.chunk.replies) -> inputChannel(managerReplies)
~~~

Để cấu hình adapter đúng, phải trả lời:

1. **Destination:** worker publish reply tới queue/topic nào? Có dùng `replyTo` từ request hay destination cố định không?
2. **Routing key/binding:** broker định tuyến reply đến đúng manager đang chờ bằng cách nào?
3. **Serialization:** converter giữ đúng `ChunkResponse`, payload type, version và headers nào?
4. **Durability:** reply message và queue/topic có bền vững qua broker restart không? TTL/retention có đủ lâu?
5. **Publish acknowledgment:** worker có biết broker đã nhận reply không? Khi publisher confirm không về, outcome được coi là gì?
6. **Consumer ACK:** manager inbound adapter xác nhận reply ở thời điểm nào, đặc biệt khi handler ném lỗi?
7. **Concurrency:** có nhiều manager consumer dùng chung reply queue không? Liệu reply có đến sai consumer?
8. **Failure path:** khi reply không publish được, worker/broker retry, DLQ hay báo lỗi theo chính sách nào?

### Đừng nhầm replyTo với correlationId

`replyTo` là **địa chỉ gửi phản hồi**; `correlationId` giúp **ghép phản hồi với yêu cầu**. Nhiều request có thể dùng chung reply destination nhưng cần correlation khác nhau. Một request cũng có thể được retry với địa chỉ reply khác sau restart. **Cả routing và correlation đều phải đúng.**

## 9. Cách chọn loại channel trong Spring Integration

| Channel | Hành vi điển hình | Có phù hợp ở reply path? | Điều cần chú ý |
| --- | --- | --- | --- |
| `DirectChannel` | Dispatch đồng bộ tới subscriber nội bộ | Phổ biến khi nối worker flow và outbound adapter | Publisher có thể chịu lỗi/độ trễ downstream ngay trên call stack |
| `ExecutorChannel` | Chuyển dispatch sang executor, bất đồng bộ | Có thể hữu ích khi muốn tách thread | Ngữ cảnh transaction/exception không tự xuyên thread; executor cần bounded queue |
| `QueueChannel` | Giữ message trong queue để poller lấy | Có thể dùng với poller rõ ràng | Queue nội bộ không tự bền vững; giới hạn dung lượng và polling |
| `PublishSubscribeChannel` | Gửi tới nhiều subscriber | Thường **không** phù hợp để fan-out response chính | Có thể vô tình xuất nhiều reply cho cùng chunk |

**Khuyến nghị khởi đầu:** dùng `DirectChannel` làm channel nội bộ của flow khi phù hợp semantics, để adapter broker là nơi cung cấp cơ chế transport và persistence. Chỉ thêm asynchronous boundary khi đo đạc cho thấy lợi ích và đã kiểm soát được **thứ tự, transaction, shutdown, retry**.

### Rủi ro khi chuyển sang ExecutorChannel

Giả sử worker commit DB, sau đó đưa response vào một `ExecutorChannel` có queue nội bộ. Lời gọi gửi response có thể được chấp nhận vào queue JVM trước khi task outbound publish thực sự chạy. Nếu JVM chết trong khoảng đó, **reply bị mất dù DB đã commit**. Cần độ bền/recovery ở đúng nơi hoặc dựa vào replay-safe business effect và cơ chế timeout/đối soát ở manager.

Đừng dùng một `QueueChannel` trong RAM rồi gọi đó là “durable reply queue”; nếu yêu cầu durable messaging, phải thiết kế dựa trên storage/broker đáng tin cậy và kiểm thử crash thật.

## 10. Broker reply destination: queue dùng chung hay riêng?

Trong hệ thống có một manager đang xử lý một job, dùng một reply queue cố định có thể đơn giản. Khi có **nhiều manager hoặc nhiều JobExecution** đồng thời, việc thiết kế routing phức tạp hơn.

| Kiểu destination | Ưu điểm | Rủi ro |
| --- | --- | --- |
| Reply queue dùng chung | Ít queue, cấu hình đơn giản | Competing consumers có thể lấy reply của manager khác; correlation không tự sửa routing |
| Queue riêng theo manager instance | Routing rõ, mỗi manager tự nhận reply | Cần lifecycle, cleanup, xử lý manager mất/chuyển node |
| Destination theo job/execution | Thuận lợi cho phân tách và truy vết | Số destination lớn, cần dọn và tránh stale reply |
| Topic + selector/routing key | Có thể phân phối theo nhãn manager/execution | Phụ thuộc broker/adapter, phải tránh broadcast hoặc miss |

**Một lỗi thiết kế quan trọng:** hai manager A và B cùng consume từ một queue theo cơ chế competing consumer. Reply của request A có thể được broker giao cho B. Nếu B không tìm thấy correlation rồi **ACK và bỏ**, A sẽ timeout dù worker đã hoàn tất. **Chỉ thêm correlation ID không đảm bảo reply đến đúng manager**; phải dùng queue/destination, selector hoặc routing contract đúng theo broker.

Nếu dùng reply queue tạm thời cho mỗi process, cần quyết định điều gì xảy ra khi manager JVM chết. Reply queue tạm bị xóa có thể làm mất phản hồi của các chunk đã commit. Chọn durability/lifecycle theo hợp đồng restart, không chỉ theo tiện lợi cấu hình ban đầu.

## 11. Header và payload phải sống sót qua hai chiều adapter

Spring Integration message có **payload** và **headers**. Khi worker nhận một request từ broker và trả response, các adapter có thể:

- Mapping `correlationId`, `replyTo`, message properties hoặc headers ứng dụng.
- Serialize payload bằng converter (JSON, Java serialization, Avro/Protobuf nếu được hỗ trợ theo contract).
- Biến đổi kiểu hoặc bỏ những header không nằm trong allowlist.
- Thay đổi message ID của broker khi gửi một reply **mới**.

| Transport | Metadata thường cần kiểm tra | Điều không được giả định |
| --- | --- | --- |
| RabbitMQ/AMQP | Reply routing, `correlationId`, `replyTo`, header mapping, content type | Broker tự biết `ChunkResponse` thuộc job nào |
| JMS | `JMSReplyTo`, `JMSCorrelationID`, selector và `JMSMessageID` | `JMSMessageID` của reply tự bằng ID request |
| Kafka | Reply topic, record headers/key và consumer routing | Record key tự đóng vai correlation ID |
| Spring Integration | `MessageHeaders` và framework payload contract | Một `MessageChannel` object có thể serialize rồi dùng ở JVM khác |

**Điều quan trọng đối với Spring Batch Integration:** không phát minh một header tùy ý để thay thế metadata mà framework dùng cho `ChunkRequest`/`ChunkResponse`. Có thể có correlation ở payload, header hoặc cả hai tùy phiên bản. Kiểm tra end-to-end sau khi qua **đúng adapter thực tế** và giữ các trường tương thích.

### Lưu ý về MessageHeaders.REPLY_CHANNEL

Trong flow nội bộ, reply channel header có thể chứa tham chiếu tới một `MessageChannel`. Đó là **đối tượng trong JVM**, không phải địa chỉ network. Không serialise nguyên đối tượng Java rồi gửi cho worker khác. Dùng tên destination/queue/topic hoặc cơ chế reply-to của broker mà adapter và framework hỗ trợ.

### Quy tắc bảo mật

- Broker authentication/authorization chỉ cho worker publish tới reply destinations hợp lệ.
- Không tin mù một `replyTo` do nguồn không được ủy quyền gửi vào; có thể dẫn tới gửi dữ liệu sang queue ngoài phạm vi.
- Không đưa password, token, PII, dữ liệu nhạy cảm vào correlation ID/headers hoặc log.
- Message converter/deserializer cần giới hạn class/schema hợp lệ; **không deserialize object từ broker không tin cậy một cách tùy ý**.
- Đặt encryption, network ACL và quyền tenant phù hợp với nội dung response và metadata.

## 12. Trạng thái worker khi trả reply thành công

Một worker trả reply **sau khi** xử lý logic chunk, nhưng điều đó không có nghĩa mọi hệ thống xung quanh đều nhận cùng một outcome tại cùng thời điểm.

~~~text
T1 Worker nhận request chunk-42
T2 Worker chạy processor
T3 Worker ghi DB
T4 DB commit thành công
T5 Worker phát response vào workerReplies
T6 Outbound adapter publish reply
T7 Broker xác nhận publish, nếu có publisher confirm
T8 Manager inbound adapter nhận response
T9 Manager match response và cập nhật tiến độ
~~~

**Các mốc là mô hình phân tích, không phải thứ tự ACK và transaction mặc định được bảo đảm.** Điều đáng lo là hệ thống có thể dừng ở **bất kỳ khoảng giữa hai mốc**.

| Trạng thái | Kết quả nghiệp vụ có thể | Việc cần làm |
| --- | --- | --- |
| Dừng trước DB commit | Transaction chưa commit hoặc bị rollback | Redelivery/retry theo request delivery policy |
| DB commit rồi dừng trước T5/T6 | Đã ghi data, chưa có reply | Writer idempotent, replay/đối soát |
| Publish reply nhưng không nhận confirm | Broker có thể đã hoặc chưa nhận | Coi outcome là **không chắc chắn**, tránh đánh dấu success giả |
| Broker giữ reply, manager offline | DB đã commit, manager chưa biết | Reply durability/recovery hoặc replay-safe restart |
| Manager nhận reply hai lần | DB có thể chỉ commit một lần | Dedupe/ghép đúng protocol, không cộng state hai lần |

**ACK của request và publish reply là hai luồng riêng.** Worker ACK sớm quá có thể làm mất request khi chưa xử lý xong; ACK muộn có thể gây redelivery khi DB đã commit. Không có cấu hình duy nhất tốt cho mọi broker/transaction; cần chứng minh bằng failure injection.

## 13. Lỗi xử lý chunk: worker trả gì về reply channel?

Một remote chunk worker không nên tạo `ChunkResponse(SUCCESS)` giả khi gặp lỗi. Tùy builder, fault-tolerance policy và integration adapter, exception có thể dẫn tới **response lỗi phù hợp protocol** hoặc làm message processing thất bại để middleware retry/redeliver. **Phải xác minh chính xác hành vi của phiên bản đang dùng**.

Các nhóm lỗi:

| Lỗi | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| Transient DB/broker | Timeout tạm thời, mất kết nối | Retry có giới hạn và backoff; không làm mất request |
| Permanent data | Payload sai schema, amount không hợp lệ | Trả failure theo protocol/quarantine có giám sát; không retry vô hạn |
| Lỗi serializer | Worker không deserialize được request hoặc reply | Dừng/alert, đưa vào DLQ theo policy, sửa version/converter |
| Không publish được reply | Broker reply down, wrong routing key | Không tự coi chunk là completed; retry publish theo hợp đồng |
| Outcome mơ hồ | DB commit đã xong nhưng reply mất | Business idempotency và đối soát |
| Lỗi authentication/authorization | Worker không có quyền publish reply | Sửa config/ACL, không silently drop |

### Reply thất bại cũng là một kết quả cần theo dõi

Nếu worker báo failure hợp lệ tới manager, manager có thể quyết định step/job FAILED theo giao thức. Nếu worker **không trả được bất kỳ response nào**, manager có thể tiếp tục đợi cho tới timeout hoặc cơ chế phát hiện lỗi khác. **Không đồng nhất “không có reply” với “có reply báo lỗi”.**

**Không sử dụng `catch (Exception e) { return SUCCESS; }`**, không sửa trực tiếp metadata batch để che lỗi và không dùng một dead-letter queue không được giám sát như thùng rác. Mỗi thông điệp DLQ cần được truy vết tới request/job và outcome nghiệp vụ.

## 14. Tình huống khó nhất: đã commit nhưng reply bị mất

Giả sử một request chứa 200 transaction:

~~~text
Manager gửi chunk C42
Worker 1 nhận C42
Worker 1 ghi và COMMIT 200 kết quả vào DB
Worker 1 crash trước khi reply tới manager
Broker có thể redeliver C42, hoặc manager replay sau timeout/restart
Worker 2 nhận lại cùng business operations
~~~

Nếu writer làm `balance = balance + amount`, lặp request có thể cộng số dư **hai lần**. Nếu writer có unique key theo `(batch_key, transaction_id)` và ghi giá trị **deterministic**, replay không nhân đôi dòng kết quả.

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE normalized_transaction (
    batch_key      VARCHAR(100) NOT NULL,
    transaction_id VARCHAR(100) NOT NULL,
    net_amount     NUMERIC(18, 2) NOT NULL,
    PRIMARY KEY (batch_key, transaction_id)
);

INSERT INTO normalized_transaction(
    batch_key, transaction_id, net_amount)
VALUES (:batchKey, :transactionId, :netAmount)
ON CONFLICT (batch_key, transaction_id)
DO UPDATE SET net_amount = EXCLUDED.net_amount;
~~~

UPSERT ngăn **hai dòng cùng khóa**, nhưng nếu retry tính lại `netAmount` khác vì tỷ giá hoặc rule thay đổi, câu `DO UPDATE` có thể che lỗi. Với yêu cầu nghiêm ngặt, chốt snapshot/rule version, lưu checksum và **fail khi giá trị conflict không khớp**. Nếu operation là trừ tiền, gửi email hay xuất event, cần **idempotency key ở hệ thống đích** hoặc transactional outbox/dedup; chỉ unique key cho bảng normalized không bảo vệ mọi side effect.

### Reply path không thay thế cơ chế exactly-once

- Correlation ID: xác định reply của request nào.
- Durable reply queue: giảm rủi ro mất reply khi broker/consumer ngừng hoạt động.
- Publisher confirms: biết broker đã nhận publish ở mức broker contract.
- Database unique key/idempotency: ngăn tác động nghiệp vụ trùng khi xử lý lại.

**Không thành phần nào một mình bảo đảm exactly-once end-to-end** giữa manager, broker, worker và business DB.

## 15. Duplicate, late và out-of-order reply

Ba tình huống phải xử lý riêng:

1. **Out-of-order:** worker B hoàn tất request B trước request A, dù manager gửi A trước.
2. **Duplicate:** cùng reply hoặc kết quả có thể được gửi/giao lại do publish retry, broker redelivery hoặc logic ứng dụng.
3. **Late/stale:** reply đến sau timeout hoặc từ JobExecution trước, khi manager đã restart.

~~~mermaid
sequenceDiagram
    participant M as Manager
    participant W1 as Worker 1
    participant W2 as Worker 2
    M->>W1: C1 / request-A
    M->>W2: C2 / request-B
    W2-->>M: reply-B SUCCESS
    W1-->>M: reply-A SUCCESS
    W1-->>M: reply-A SUCCESS (duplicate)
    Note over M: Match B trước A, không đếm A hai lần
~~~

**Không** ghép reply theo thứ tự nhận, `threadName` hay `workerId`. Manager/adapter cần bảo toàn correlation/protocol metadata, và completion cho một request logic phải được xử lý theo quy tắc **không đếm hai lần**.

### Khi một reply của execution cũ đến execution mới

Ví dụ một request thuộc `jobExecutionId=845`, manager restart tạo `jobExecutionId=846` nhưng vẫn cùng JobInstance. Reply của lần 845 đến muộn không được tự động hiểu là response hợp lệ cho request đang đợi của 846 chỉ vì cùng `chunkSequence`. Cần dùng protocol Spring Batch theo version hoặc identity/namespace đầy đủ của giao thức tùy biến.

Nếu message không còn đối tượng đợi tương ứng, cần chính sách **orphan/stale reply**: log với correlation, kiểm tra outcome nghiệp vụ, ACK/route/DLQ theo hợp đồng. Không gửi reply đó vào một request khác cho “đỡ timeout”.

## 16. Timeout và quản lý reply đang chờ

Một manager có thể có nhiều request đang đợi phản hồi. Nếu một worker bị treo hoặc reply đi sai route, danh sách chờ sẽ tăng. Timeout là **tín hiệu kết quả chưa được xác nhận**, không chứng minh worker chưa commit.

~~~text
T0: manager publish chunk-42
T1: worker commit DB
T2: worker publish reply nhưng broker tạm chậm
T3: manager timeout, đánh dấu outcome chưa rõ
T4: reply của chunk-42 mới tới
T5: ứng dụng phân loại late reply và đối soát, không gán bừa
~~~

### Một state machine minh họa

~~~mermaid
stateDiagram-v2
    [*] --> CREATED
    CREATED --> SENT: publish request
    SENT --> SUCCEEDED: valid success reply
    SENT --> FAILED: valid failure reply
    SENT --> TIMED_OUT: reply timeout
    TIMED_OUT --> RECONCILING: unknown outcome
    RECONCILING --> RETRYING: replay safe
    RECONCILING --> SUCCEEDED: business outcome verified
    RETRYING --> SENT: retry request
~~~

Đây là **mô hình khái niệm**, không phải trạng thái enum mặc định của Spring Batch. Framework có cơ chế quản lý trạng thái riêng; nếu thêm một registry request tùy biến, phải có TTL, cleanup và persistence khi cần khôi phục qua JVM crash. `ConcurrentHashMap` trong RAM không giải quyết được durability.

**Giới hạn in-flight** cũng quan trọng: nếu manager gửi nhanh hơn worker xử lý, cả request backlog và số reply đang chờ có thể tăng. Hãy đo số outstanding, thời gian chờ p95/p99, queue age và tốc độ worker; không tăng timeout vô hạn chỉ để che bottleneck.

## 17. Tách sự cố reply path khỏi sự cố worker

Khi manager không tiến độ, hãy đi từng điểm:

~~~text
1. Manager đã publish request chưa?
2. Broker request queue có delivery/unacked không?
3. Worker có nhận và deserialize được chunk không?
4. Processor/writer có hoàn tất và COMMIT không?
5. Remote chunk worker flow có phát ChunkResponse không?
6. workerReplies có subscriber/outbound adapter không?
7. Outbound adapter có publish tới đúng reply destination không?
8. Broker nhận reply và có routing đến manager không?
9. Manager inbound adapter có deserialize và đưa vào managerReplies không?
10. Manager có correlate đúng reply với request đang chờ không?
~~~

**Ví dụ chẩn đoán:**

| Triệu chứng | Điểm cần kiểm tra đầu tiên | Rủi ro ẩn |
| --- | --- | --- |
| Worker log “write successful”, manager đứng | workerReplies, outbound adapter, reply broker | DB đã commit; retry có thể ghi lặp |
| Reply queue tăng, manager không nhận | manager inbound adapter, consumer ACL, converter | Reply đang có nhưng chưa correlate |
| Reply queue bằng 0 nhưng manager timeout | Routing sai hoặc consumer khác đã ACK | Queue depth thấp không chứng minh thành công |
| Worker nhận nhiều request giống nhau | Request ACK/redelivery và lỗi reply | Có thể là replay hợp lệ, writer phải idempotent |
| Đã có reply nhưng manager báo unknown | Correlation/sequence/execution mismatch | Payload hoặc header bị biến đổi |
| Chỉ lỗi sau rolling deploy | Schema/serializer không tương thích | Message của phiên bản trước vẫn trong queue |
| Chỉ lỗi khi hai manager chạy | Shared reply queue với competing consumers | Reply bị manager khác ăn mất |
| Worker bận, broker reply nhàn | DB pool/processor bottleneck | Tăng reply consumer không cải thiện processing |

**Không kiểm tra queue depth đơn lẻ để kết luận dữ liệu đã xử lý hay chưa.** Cần log correlation, JobRepository và kết quả business DB.

## 18. Độ bền và transaction của reply queue

Khi yêu cầu tính chịu lỗi cao, cần làm rõ các yếu tố dưới đây theo **broker cụ thể**:

| Thuộc tính | Câu hỏi vận hành |
| --- | --- |
| Durable destination | Reply queue/topic còn tồn tại sau broker restart không? |
| Persistent delivery | Reply message có được lưu bền vững theo hợp đồng broker không? |
| Publisher confirm/transaction | Worker biết publish thành công ở mức broker như thế nào? |
| Consumer ACK | Manager xác nhận đã xử lý reply lúc nào? |
| Redelivery | Reply chưa ACK có được giao lại khi consumer chết không? |
| TTL/retention | Reply có hết hạn trước khi manager khôi phục không? |
| DLQ | Reply poison hoặc không deserialize được được lưu ở đâu và ai theo dõi? |
| Quota/max length | Khi reply backlog đầy, broker làm gì: block, reject, drop hay overflow policy? |

**Durable queue nhưng non-persistent message** có thể không đáp ứng độ bền mong muốn. Ngược lại, persistent messages và confirm vẫn **không** tạo distributed transaction tự động với business DB.

### Cẩn trọng khi ACK reply

Nếu manager inbound listener ACK trước khi handler nhận/correlate được reply, rồi JVM chết, reply có thể mất dù chưa được Spring Batch ghi nhận. Nếu ACK sau xử lý nhưng handler đã ghi metadata rồi ACK mất, broker có thể **giao lại reply**. Cả hai chiều đều cần được test với adapter và JobRepository thực tế. Cơ chế dedup/khả năng phản hồi lặp là một phần của thiết kế đúng.

## 19. Quản lý nhiều worker, tenant và rolling deployment

Một reply destination có thể nhận phản hồi từ nhiều worker version, nhiều region hoặc tenant. Cần:

- Version hóa **message schema/serialization** giữa manager và worker; tránh deploy không tương thích khiến reply không deserialize được.
- Giữ nguyên correlation/sequence metadata qua converter; không sinh ID mới cho cùng response do protocol yêu cầu.
- Giới hạn quyền broker để worker chỉ publish các reply hợp lệ; không để worker tùy ý chuyển reply chứa dữ liệu tenant A sang destination của tenant B.
- Dùng message idempotency ở business sink khi hai worker nhận request trùng do redelivery.
- Không đặt tenant secret hoặc PII vào reply queue name, message header, trace ID.
- Cân nhắc **drain/rollover** request/reply queue trước nâng cấp incompatible protocol; kiểm tra những message còn tồn tại từ deployment cũ.

### Khi có nhiều worker thì có cần nhiều reply queue?

**Không nhất thiết.** Nhiều worker có thể publish vào một reply destination mà đúng manager đang consume. Vấn đề là **ai cần nhận reply**, không phải worker nào gửi reply. Số reply destination thường nên phản ánh routing/ownership của manager hoặc protocol, không mặc định bằng số worker.

### Điều gì xảy ra nếu worker gửi hai reply?

Nếu worker retry publish sau khi không nhận publisher confirm, broker có thể đã nhận message lần đầu; lần publish thứ hai tạo **duplicate reply**. Manager phải chịu được trường hợp này. Không nên viết code “nếu nhận hai SUCCESS thì tăng writeCount hai lần”.

## 20. Observability: đo cả reply lẫn kết quả nghiệp vụ

Ở production, theo dõi ít nhất:

| Metric/tín hiệu | Ý nghĩa | Khi cần điều tra |
| --- | --- | --- |
| `chunk_requests_sent_total` | Số request manager đã gửi | Tốc độ gửi và đọc nguồn |
| `worker_chunks_completed_total` | Worker báo đã xử lý xong chunk | Có tăng nhưng manager đứng? |
| `worker_reply_publish_total` | Worker thử publish reply | Tỉ lệ lỗi publish/confirm |
| `reply_queue_depth` | Reply đang nằm ở broker | Manager inbound chậm hoặc offline |
| `reply_queue_oldest_age` | Tuổi reply chưa được tiêu thụ | Reply không tới manager đúng hạn |
| `reply_latency_seconds` | Request đến khi manager nhận/match reply | p95/p99 tăng |
| `reply_correlation_miss_total` | Reply không khớp pending/protocol | Header mất, stale reply, sai route |
| `reply_duplicate_total` | Reply lặp đã được phát hiện | Publish retry/redelivery |
| `reply_timeout_total` | Request hết hạn đợi | Worker lỗi, broker reply lỗi, backlog |
| `worker_redelivery_total` | Chunk request bị giao lại | ACK/commit/reply lỗi hoặc worker crash |
| `step_status/read/write/rollback` | Trạng thái Spring Batch thực tế | Sai metadata hoặc không hoàn tất |
| `business_dedup_conflict_total` | Sink gặp operation trùng/giá trị khác | Rủi ro exactly-once business effect |

**Correlation ID nên nằm trong log/tracing, không là tag riêng cho mỗi time series metric** nếu có hàng triệu request, vì sẽ tạo cardinality cực lớn. Hãy dùng metric theo job, step, worker, loại lỗi; log theo ID với retention và kiểm soát truy cập phù hợp.

### Bản ghi log gợi ý

~~~text
manager SEND          step=settlement corr=req-42 items=200
worker-2 RECEIVE      corr=req-42 attempt=1
worker-2 DB_COMMIT    corr=req-42 count=200
worker-2 REPLY_SEND   corr=req-42 destination=batch.chunk.replies
broker   REPLY_ACCEPT corr=req-42
manager  REPLY_MATCH  corr=req-42 result=SUCCEEDED
~~~

Tên event chỉ minh họa; nên log **theo những mốc thực sự quan sát được**. Không log `DB_COMMIT` trước khi transaction kết thúc, và không ghi `REPLY_ACCEPT` chỉ dựa vào việc `MessageChannel.send()` trả về nếu broker chưa confirm.

## 21. Unit test: kiểm tra output channel có nhận reply

**Đừng coi unit test channel là kiểm thử middleware.** Unit test chỉ kiểm tra integration flow phát response đúng kiểu vào output channel khi worker xử lý request thành công; nó không chứng minh broker có thể định tuyến và lưu reply.

Một kịch bản kiểm thử hợp lý:

1. Cấu hình worker flow bằng builder Spring Batch Integration tương ứng.
2. Dùng input message theo đúng `ChunkRequest` protocol của framework.
3. Gắn một **test subscriber/channel** lên output để thu `ChunkResponse`.
4. Xác minh item đã qua processor/writer và response có metadata ghép được với request.
5. Tiêm lỗi processor/writer để xác minh failure behavior hoặc exception routing đúng hợp đồng.
6. Đảm bảo test thu được **một logical outcome**, không giả định số message tuyệt đối khi framework/adapter cho phép retry.

Ví dụ một **collector** JUnit 5 + Spring Integration cho output `DirectChannel`:

~~~java
final class ReplyCollector implements MessageHandler {
    private final BlockingQueue<Message<?>> replies =
            new LinkedBlockingQueue<>();

    @Override
    public void handleMessage(Message<?> message) {
        replies.add(message);
    }

    Message<?> next(long timeout, TimeUnit unit)
            throws InterruptedException {
        return replies.poll(timeout, unit);
    }
}

@Test
void directChannelDeliversReplyToSubscriber() throws Exception {
    DirectChannel replies = new DirectChannel();
    ReplyCollector collector = new ReplyCollector();
    replies.subscribe(collector);

    Message<String> sample = MessageBuilder
            .withPayload("illustrative-response")
            .setHeader("correlationId", "req-42")
            .build();
    assertTrue(replies.send(sample));

    Message<?> received = collector.next(1, TimeUnit.SECONDS);
    assertNotNull(received);
    assertEquals("req-42",
            received.getHeaders().get("correlationId"));
}
~~~

Test này chứng minh `DirectChannel` phân phối message nội bộ tới subscriber, **không chứng minh `RemoteChunkingWorkerBuilder` tự sinh đúng `ChunkResponse`**. Để kiểm tra framework thực, cần phát `ChunkRequest` hợp lệ qua worker input channel và thu output có payload/hợp đồng được framework hỗ trợ.

## 22. Integration test với broker: các trường hợp phải có

Dùng broker thật trong môi trường test (hoặc Testcontainers thích hợp), manager/worker Spring Batch Integration và DB test. Nên có các test sau:

| Test | Cách tạo | Assertion |
| --- | --- | --- |
| Happy path | Manager gửi nhiều chunk, worker ghi và reply | Mỗi chunk kết thúc đúng protocol; output đúng |
| Reply out-of-order | Giữ worker A bằng latch, B xong trước | Manager vẫn match đúng, không dựa thứ tự |
| Worker crash trước commit | Kill worker container ở điểm có kiểm soát | Rollback/recovery đúng theo ACK policy |
| Worker crash sau commit trước reply | Ngắt reply adapter hoặc kill tại thời điểm phù hợp | Replay không nhân đôi business effects |
| Publish reply fail | Broker reply destination không thể publish | Failure/timeout rõ; không báo COMPLETED giả |
| Reply bị mất header | Converter/mapper bỏ metadata yêu cầu | Manager không ghép bừa, có alert/mismatch |
| Duplicate reply | Broker redeliver hoặc publish lại response | Không đếm hoàn tất hai lần |
| Stale reply sau restart | Đưa reply của execution cũ tới manager mới | Không gán nhầm; xử lý orphan theo policy |
| Nhiều manager | Hai JobExecution đồng thời, shared broker | Reply chỉ đến đúng manager hoặc selector |
| Reply queue backlog | Tạm dừng manager inbound adapter | Durable reply/age/alert/khôi phục |
| Poison reply | Payload schema sai, deserialize failure | DLQ/error policy và monitoring hoạt động |
| Broker restart | Restart broker trong lúc in-flight | Không mất hoặc xử lý sai so với durability contract |

### Vì sao dùng latch thay vì sleep?

`Thread.sleep(500)` không bảo đảm worker A chậm hơn B trong CI nhiều máy. Dùng `CountDownLatch` hoặc test barrier để giữ worker A ở ranh giới **trước write**, **sau commit**, hoặc **trước publish reply**. Sau khi quan sát đúng mốc, test mới chủ động mở latch/ngắt consumer. Mọi latch cần timeout và `finally` để không làm test treo.

### Hai phép đối soát bổ sung

1. **Business reconciliation:** so sánh tập `(batchKey, transactionId)` đầu vào với bảng output và giá trị đã tính; chỉ so `COUNT(*)` chưa đủ.
2. **Protocol reconciliation:** so sánh request được manager phát với reply hợp lệ đã match, duplicate/timeout/orphan và StepExecution status. Có thể thấy business output đủ nhưng manager chưa nhận reply, hoặc manager báo success do protocol lỗi dù output thiếu.

## 23. Capacity planning: reply path cũng có thể nghẽn

Đôi khi processor/writer nhanh nhưng manager inbound reply adapter xử lý chậm, hoặc broker reply partition bị giới hạn tốc độ. Khi đó:

~~~text
Manager gửi:      100 chunk/s
Workers hoàn tất: 100 chunk/s
Manager nhận được: 60 reply/s
Reply backlog:    tăng khoảng 40 reply/s
~~~

Ngay cả khi business DB đã lưu đầy đủ, manager có thể còn rất nhiều chunk “đang chờ reply”. Tăng số worker trong tình huống đó sẽ **làm backlog reply tệ hơn**.

| Nút thắt | Triệu chứng | Hướng xử lý |
| --- | --- | --- |
| Worker processor/DB | Request queue tăng, reply queue thấp | Tối ưu worker, DB, chunk size |
| Reply outbound adapter | Worker xong nhưng không publish kịp | Kiểm tra network, thread, publisher confirms và retry |
| Reply broker | Reply queue age/latency tăng, broker I/O cao | Scale/tune broker theo kiến trúc, giới hạn in-flight |
| Manager inbound adapter | Reply queue tăng dù worker xong | Xem consumer concurrency, deserialize, xử lý correlation |
| Manager correlation/state | Reply đã nhận nhưng chưa match | Sửa protocol, header mapping, tránh contention |
| JobRepository | Manager chậm cập nhật metadata | Kiểm tra DB pool/lock/commit và số lượng chunk |

**Cẩn trọng khi tăng consumer concurrency trên reply queue:** nếu manager/framework xử lý metadata response theo một cơ chế yêu cầu thread safety hoặc ordering, phải kiểm thử trước. Nhiều consumer hơn không sửa được routing sai hay reply đã bị mất header.

## 24. Runbook: worker trả reply nhưng manager không tiến

Khi gặp một job RUNNING lâu bất thường:

1. **Khoanh vùng:** xác định JobInstance/JobExecution, manager node, step, broker request/reply destination và thời gian chunk cuối được gửi.
2. **Kiểm tra worker:** worker có nhận chunk không, `ItemWriter` có commit chưa, có exception hay restart consumer không.
3. **Kiểm tra `workerReplies`:** output channel có subscriber/outbound flow không; message đã thoát JVM chưa.
4. **Kiểm tra broker reply:** routing/binding, publisher confirm, độ bền, reply depth, oldest age, DLQ, TTL và quyền.
5. **Kiểm tra manager inbound:** consumer còn kết nối không, converter có đọc được payload không, đã gửi vào `managerReplies` chưa.
6. **Kiểm tra correlation:** sequence, execution identity, request/reply metadata có nguyên vẹn, có stale hoặc duplicate không.
7. **Đánh giá outcome:** với chunk chưa có reply, tra business DB theo business key để biết có thể đã commit hay chưa.
8. **Ổn định hệ thống:** sửa routing/adapter, giới hạn concurrency hoặc retry có backoff; không xóa queue bừa.
9. **Khôi phục:** restart cùng JobInstance và snapshot nếu phù hợp, bảo đảm writer idempotent và worker cũ không tạo side effect cạnh tranh.
10. **Đối soát cuối:** dữ liệu đích, trạng thái StepExecution, DLQ và orphan replies trước khi công bố job thành công về mặt nghiệp vụ.

**Không sửa trực tiếp JobRepository thành `COMPLETED` chỉ vì thấy worker đã ghi DB**, và cũng không coi việc drain reply queue là bằng chứng tất cả chunk được manager ghép đúng.

## 25. Bài thực hành và checklist cuối bài

**Bài thực hành:** xây một manager remote chunking đọc dữ liệu đã chốt thành chunk 100 item; hai worker dùng cùng request queue, ghi vào PostgreSQL theo business key `(batchKey, transactionId)`, rồi trả reply qua một broker destination cho manager.

Yêu cầu thực hiện:

1. **Lắp đúng luồng:** manager output → broker request → worker input → worker output → broker reply → manager input.
2. **Hợp đồng reply:** sử dụng `ChunkRequest`/`ChunkResponse` theo đúng Spring Batch Integration version, bảo toàn metadata qua adapter.
3. **Normal path:** nhiều chunk được xử lý và reply có thể đến trái thứ tự; StepExecution hoàn tất với output đúng.
4. **Broken reply route:** cố tình cấu hình sai destination trong môi trường test; worker ghi xong nhưng manager không nhận được. Điều tra theo runbook.
5. **Commit trước reply:** kill worker sau commit nhưng trước publish, xác minh retry/replay không nhân đôi output.
6. **Duplicate/stale reply:** gửi lại một response hoặc reply của execution trước; manager không tăng kết quả sai.
7. **Multi-manager:** thử hai manager trên broker; xác minh reply routing không rơi vào competing consumer sai.
8. **Load test:** tăng số worker và chunk size, đo throughput, reply queue age/latency, memory, DB connection pool.
9. **Failure recovery:** restart JobInstance thất bại với snapshot bất biến và đối soát business output.

Checklist trước production:

- [ ] Đã xác định rõ worker output channel, broker reply destination và manager input channel.
- [ ] Cả hai chiều request/reply được nối bằng adapter đúng; không nhầm `DirectChannel` với broker queue.
- [ ] `ChunkResponse` và metadata/correlation của Spring Batch Integration được giữ đúng, không tự thay bằng cờ `SUCCESS`.
- [ ] Routing reply đến đúng manager, kể cả khi nhiều manager/job chạy đồng thời.
- [ ] Serializer/schema tương thích, headers được bảo toàn, broker auth/ACL phù hợp.
- [ ] Có policy publish confirm, ACK, redelivery, timeout, TTL, DLQ và restart.
- [ ] Writer idempotent theo business key; các side effect ngoài DB có outbox/dedup/idempotency.
- [ ] Chấp nhận reply có thể trễ/trùng/trái thứ tự; completion không bị đếm hai lần.
- [ ] Có giới hạn chunk size, prefetch/in-flight/concurrency và capacity của reply path.
- [ ] Có metric request/reply, queue age, correlation miss, timeout, duplicate và DB commit.
- [ ] Có test broker thật cho các mốc crash trước/sau commit, mất reply, multi-manager, rolling upgrade và khôi phục.
- [ ] Có runbook kiểm tra từng hop và đối soát trước khi xác nhận hoàn tất nghiệp vụ.

**Ghi nhớ:** **reply channel của worker là cửa ra của kết quả xử lý trong JVM worker**, còn **middleware reply destination** mới vận chuyển nó sang manager. Thiết kế đúng phải nối đủ hai đầu adapter, giữ nguyên `ChunkResponse`/correlation metadata, phân biệt DB commit–broker ACK–reply publish–manager match và chấp nhận retry/restart có thể phát sinh xử lý lặp. Độ tin cậy đến từ **routing đúng, reply durability phù hợp, writer idempotent, quan sát và kiểm thử sự cố**, không phải chỉ từ việc khai báo một bean `MessageChannel`.
