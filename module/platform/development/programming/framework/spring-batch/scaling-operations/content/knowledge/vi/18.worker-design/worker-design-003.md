# Worker nhận chunk qua middleware

Trong **remote chunking** của Spring Batch, **manager** giữ vai trò đọc dữ liệu nguồn, chia thành các **chunk** và gửi chúng qua một hệ thống trung gian (middleware/message broker). Các **worker** ở JVM hoặc máy khác nhận thông điệp chunk, thực hiện `ItemProcessor` và `ItemWriter`, sau đó gửi **phản hồi kết quả** cho manager. Mô hình này khác với remote partitioning: một bên chia **chunk đã đọc**, bên kia chia **vùng dữ liệu** để worker tự đọc.

Bài học thuộc chương **Thiết kế worker** của module **SPRING_BATCH_SCALING_OPERATIONS**. Module tập trung mở rộng Spring Batch cho workload dữ liệu lớn bằng multi-threaded step, parallel steps, partitioning và mô hình phân tán; đồng thời đo nút thắt, bảo đảm thread safety, retry/restart, vận hành job và chọn kiến trúc theo tài nguyên thực tế. Chủ đề **“Worker nhận chunk qua middleware”** đi sâu vào hợp đồng thông điệp, cách worker nhận và xử lý chunk, ranh giới transaction, xác nhận thành công, chống xử lý lặp, quản lý lỗi và vận hành nhiều worker.

**Tư tưởng trung tâm:** nhận được thông điệp **không đồng nghĩa** đã ghi thành công; gửi phản hồi **không đồng nghĩa** manager đã nhận; ACK ở broker **không đồng nghĩa** dữ liệu nghiệp vụ đã commit. Muốn chạy đáng tin cậy, phải phân biệt các mốc đó và bảo vệ kết quả khi thông điệp có thể bị giao lại.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vai trò của **manager, middleware, worker, request channel, reply channel** trong remote chunking.
2. Phân biệt remote chunking với **multi-threaded step**, **local partitioning** và **remote partitioning**.
3. Thiết kế nội dung chunk đủ định danh, có phiên bản schema và phù hợp với serializer/transport.
4. Xây worker **stateless hoặc có trạng thái được kiểm soát**, xử lý chunk trong transaction phù hợp, gửi phản hồi sau khi xử lý thành công.
5. Giải thích retry, redelivery, ACK, timeout, correlation và vì sao không thể giả định exactly-once end-to-end.
6. Áp dụng **business key, unique constraint, idempotency** và chiến lược phân loại lỗi transient/permanent.
7. Cấu hình một khung Spring Batch Integration 5.x, gắn request/reply với broker và giới hạn concurrency.
8. Kiểm thử worker bị kill, lỗi DB, trùng thông điệp, mất reply, poison message và restart cùng JobInstance.
9. Đo throughput, độ trễ và backlog để chọn chunk size, số consumer, dung lượng DB pool và kiến trúc phù hợp.

**Tình huống xuyên suốt:** hệ thống đọc khoảng ba triệu giao dịch theo một tập nguồn đã chốt. Manager đọc tuần tự đủ nhanh, nhưng tính toán và ghi kết quả chậm. Nhóm muốn tách phần xử lý/ghi sang bốn worker sử dụng một broker hỗ trợ durable messages. Mỗi giao dịch có `batchKey` và `transactionId` ổn định, kết quả phải không bị nhân đôi kể cả khi worker đã commit nhưng reply bị thất lạc.

## 2. Kiến trúc của một chunk đi qua middleware

~~~mermaid
sequenceDiagram
    participant R as Reader tại Manager
    participant M as Manager Step
    participant Q as Request Queue
    participant W as Worker
    participant D as Business DB
    participant P as Reply Queue
    R->>M: Đọc các item của chunk
    M->>Q: ChunkRequest (items, sequence/correlation)
    Q->>W: Giao thông điệp yêu cầu
    W->>W: ItemProcessor
    W->>D: ItemWriter trong transaction
    D-->>W: Commit hoặc rollback
    W->>P: ChunkResponse (kết quả/thất bại)
    P->>M: Reply tương ứng chunk
    M->>M: Tổng hợp trạng thái StepExecution
~~~

Sơ đồ mô tả **đường dữ liệu logic**. Thứ tự broker ACK, confirm, thời điểm commit, phản hồi lỗi, serialization và redelivery phụ thuộc adapter/broker/transaction configuration được chọn. Không nên suy ra rằng các mũi tên nằm trong một giao dịch ACID duy nhất.

**Các thành phần:**

| Thành phần | Trách nhiệm chính | Ranh giới quan trọng |
| --- | --- | --- |
| Manager step | Đọc từ `ItemReader`, tạo chunk, gửi yêu cầu, thu thập reply, quản lý trạng thái step | Thường là nơi quản lý reader state và JobRepository |
| Request middleware | Chuyển và lưu/buffer thông điệp chunk tới worker | Độ bền, ACK, redelivery, ordering, message TTL |
| Worker | Nhận chunk, `ItemProcessor`, `ItemWriter`, xử lý lỗi, phản hồi | Không tự giả định có reader/StepExecution của riêng mình |
| Business DB/API | Lưu kết quả xử lý | Transaction và idempotency theo nghiệp vụ |
| Reply middleware | Chuyển kết quả tới manager | Reply có thể trễ, lặp hoặc không đến |
| JobRepository | Lưu metadata JobExecution/StepExecution và checkpoint | Không thay thế hệ thống dedup nghiệp vụ |

**Worker remote-chunk không nhất thiết là một partitioned StepExecution riêng.** Trong remote chunking điển hình, manager sở hữu step đọc, còn worker xử lý các `ChunkRequest` qua integration flow. Vì vậy không tự động áp dụng giả định “mỗi worker có một `StepExecution` riêng” của **remote partitioning**.

## 3. So sánh để không chọn sai mô hình

| Mô hình | Ai đọc dữ liệu? | Đơn vị phân phối | Tình huống phù hợp | Nút thắt thường gặp |
| --- | --- | --- | --- | --- |
| Multi-threaded step | Cùng step, qua reader được chia sẻ hoặc điều phối | Chunk trên nhiều thread trong JVM | Chạy trên một máy, reader/writer hỗ trợ concurrent | Reader state, thread safety, DB |
| Local partitioning | Mỗi worker step có reader riêng | Partition theo ID/file/tenant | Có nguồn chia được thành vùng ổn định | Skew vùng, JobRepository, DB |
| Remote partitioning | **Worker** đọc vùng được giao | `ExecutionContext` của partition | Cần phân tán cả chi phí đọc, xử lý và ghi | Phân phối input/metadata, worker failure |
| **Remote chunking** | **Manager** đọc và gửi items | **Chunk chứa các item đã đọc** | Đọc tập trung đủ nhanh, xử lý/ghi cần nhiều máy | Manager reader, network/broker, payload, reply latency |

Nếu reader rất chậm và không tận dụng được một máy, remote chunking **không tự giải quyết** điểm nghẽn vì manager vẫn đọc dữ liệu. Khi reader có thể chia theo khóa chính, file hoặc tenant để nhiều worker đọc độc lập, remote partitioning thường đáng cân nhắc hơn.

Ngược lại, khi nguồn khó chia nhưng reader nhanh, cần tăng CPU cho processor hoặc phân tán writer, remote chunking có thể là lựa chọn hợp lý.

## 4. Hợp đồng chunk: phải rõ định danh và phạm vi công việc

Spring Batch Integration có các kiểu thông điệp/hạ tầng hỗ trợ remote chunking, trong đó **`ChunkRequest`** đại diện yêu cầu xử lý một tập item và **`ChunkResponse`** mang thông tin phản hồi. Khi dùng các builder/flow của framework, **không tự ý thay payload bằng JSON tùy biến** nếu hai đầu chưa triển khai protocol/serializer tương thích.

Ở mức thiết kế, một chunk cần có các thuộc tính:

- **Danh sách item** hoặc tham chiếu tới payload được lưu bền vững, trong giới hạn kích thước thông điệp.
- **Nhận diện công việc**: job/step tương ứng, định danh chunk logic, sequence hoặc correlation mà framework yêu cầu.
- **Phiên bản schema** và phiên bản business rule nếu hai phía có thể deploy độc lập.
- **Định danh dữ liệu bất biến**: `batchKey`, `transactionId`, `sourceSnapshotId` trong item hoặc metadata đã được xác thực.
- **Thông tin reply**: địa chỉ reply channel/queue và correlation để manager nhận đúng kết quả.

Một dạng JSON **minh họa nghiệp vụ**, **không phải định dạng wire chính thức của Spring Batch**:

~~~json
{
  "schemaVersion": 1,
  "batchKey": "settlement-2026-11-26",
  "logicalChunkKey": "step-A/chunk-000042",
  "items": [
    {
      "transactionId": "tx-1001",
      "grossAmount": "100.00"
    },
    {
      "transactionId": "tx-1002",
      "grossAmount": "250.75"
    }
  ],
  "replyCorrelation": "corr-42"
}
~~~

Đây chỉ là hình dung payload để thảo luận hợp đồng dữ liệu. **Builder của Spring Batch Integration tự tạo/cần các thông tin protocol riêng**; code production phải dùng định dạng tương thích giữa manager và worker. Không được chỉ gửi chuỗi `transactionId` nếu worker không thể truy xuất đúng snapshot của item tại thời điểm xử lý.

### Những quy tắc định danh quan trọng

1. **Chunk ID** dùng để theo dõi và đối chiếu một phần việc. Nó có thể khác nhau giữa các lần thử gửi/restart tùy framework và thiết kế.
2. **Message ID** của broker có thể khác nhau khi publish lại cùng công việc; đừng dùng broker message ID làm khóa nghiệp vụ duy nhất.
3. **Business record ID** phải ổn định qua retry/redelivery, chẳng hạn `(batchKey, transactionId)`.
4. Nếu một record sinh ra nhiều output, khóa dedup cần bao gồm **loại output** hoặc **operation ID** phù hợp, không chỉ transactionId.
5. Payload có dữ liệu nhạy cảm: cần authentication/authorization giữa worker và broker, encryption khi truyền/lưu nếu chính sách yêu cầu, và hạn chế PII trong log.

## 5. Vòng đời một chunk và các thời điểm dễ nhầm lẫn

~~~text
1. Manager đọc item từ nguồn
2. Manager gửi ChunkRequest
3. Broker xác nhận nhận publish (nếu có publisher confirm)
4. Worker nhận delivery
5. Worker xử lý và ghi kết quả
6. DB commit thành công
7. Worker gửi ChunkResponse
8. Broker nhận ACK cho delivery yêu cầu
9. Manager nhận và đối chiếu reply
10. Manager cập nhật trạng thái/checkpoint theo cơ chế Spring Batch
~~~

Danh sách này là **các mốc logic cần xét**, không phải thứ tự nguyên tử hoặc cam kết chính xác mọi adapter. Một số bước có thể được hoán đổi bởi cấu hình listener, transaction, acknowledgment hay reply adapter. Điều quan trọng là **không có distributed transaction mặc định bao trùm cả database, request broker, reply broker và JobRepository**.

Ví dụ lỗi:

- Worker **đã commit DB** ở bước 6 nhưng chết trước khi broker xác nhận ACK hoặc trước khi reply được nhận: cùng chunk có thể được giao lại.
- Broker nhận ACK **trước khi** DB commit rồi worker chết: nếu cấu hình như vậy, request có thể bị mất mà chưa có kết quả. Phải kiểm tra listener acknowledgment/transaction thực tế.
- Manager **gửi request** nhưng chết trước khi nhận reply: trạng thái commit ở worker có thể chưa rõ đối với manager; restart có thể cần replay/đối soát.
- Reply tới manager **hai lần**: cần correlation để không cộng gộp đóng góp của một chunk như hai kết quả độc lập.

**Kết luận:** hướng tới *at-least-once processing* cộng với **idempotent business effects**, hoặc một hợp đồng giao dịch rõ hơn nếu hạ tầng hỗ trợ và đã được kiểm chứng. Không tuyên bố exactly-once end-to-end chỉ dựa vào việc bật durable queue.

## 6. Thiết kế worker nhận và xử lý chunk

Trong một worker tốt, pipeline nghiệp vụ nên có các bước:

~~~mermaid
flowchart TD
    Q["Inbound request channel"] --> V["Validate protocol/version"]
    V --> A{"Chunk hợp lệ?"}
    A -- "Không" --> F["Failure reply / DLQ theo policy"]
    A -- "Có" --> P["ItemProcessor từng item"]
    P --> W["ItemWriter ghi một chunk"]
    W --> T{"DB transaction thành công?"}
    T -- "Không" --> R["Rollback / phân loại lỗi"]
    T -- "Có" --> S["Thành công và reply"]
    R --> F
~~~

**Thiết kế đơn giản ưu tiên:**

- Worker **không tự đọc thêm** dữ liệu ngoài chunk được nhận, trừ khi giao thức quy định rõ item chỉ là tham chiếu tới snapshot.
- Processor **stateless và deterministic**: cùng input/snapshot/rules cho cùng output.
- Writer dùng transaction, khóa nghiệp vụ và cơ chế ghi có thể replay an toàn.
- Không giữ `currentChunk`, `currentTenant` hoặc `currentJobExecutionId` trong field singleton mutable; nhiều consumer có thể dùng chung bean.
- Không gửi email, trừ tiền hay publish event không idempotent trực tiếp trong processor.
- Không báo success trước khi biết thao tác nghiệp vụ cần thiết đã thành công theo hợp đồng.
- Không tự ACK/NACK thông điệp tùy tiện khi framework/integration adapter đã quản lý acknowledgment; cấu hình phải nhất quán.

### Ví dụ processor stateless

~~~java
record SaleTask(
        String batchKey,
        String transactionId,
        BigDecimal grossAmount) {}

record SaleResult(
        String batchKey,
        String transactionId,
        BigDecimal netAmount) {}

@Bean
ItemProcessor<SaleTask, SaleResult> saleProcessor() {
    return item -> {
        if (item.batchKey() == null || item.batchKey().isBlank()
                || item.transactionId() == null
                || item.transactionId().isBlank()
                || item.grossAmount() == null
                || item.grossAmount().signum() < 0) {
            throw new IllegalArgumentException("Invalid sale task");
        }

        BigDecimal net = item.grossAmount()
                .setScale(2, RoundingMode.HALF_UP);

        return new SaleResult(
                item.batchKey(),
                item.transactionId(),
                net);
    };
}
~~~

Record và `BigDecimal` trong ví dụ được sử dụng như dữ liệu bất biến. Nhưng nếu processor gọi service có cache mutable không đồng bộ hoặc dùng tỷ giá hiện tại theo thời gian, cùng một item được redeliver vẫn có thể cho output khác. Nên cố định phiên bản rule và dữ liệu tham chiếu theo `batchKey`/snapshot.

## 7. Writer idempotent để chịu được redelivery

Trong PostgreSQL, khóa `(batch_key, transaction_id)` giúp một giao dịch thuộc batch chỉ có một dòng kết quả:

~~~sql
CREATE TABLE normalized_sale (
    batch_key       VARCHAR(100) NOT NULL,
    transaction_id  VARCHAR(100) NOT NULL,
    net_amount      NUMERIC(18, 2) NOT NULL,
    processed_at    TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (batch_key, transaction_id)
);
~~~

Writer mẫu theo item business key:

~~~java
@Bean
JdbcBatchItemWriter<SaleResult> saleWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<SaleResult>()
            .dataSource(dataSource)
            .sql("""
                    INSERT INTO normalized_sale(
                        batch_key, transaction_id, net_amount)
                    VALUES (:batchKey, :transactionId, :netAmount)
                    ON CONFLICT (batch_key, transaction_id)
                    DO UPDATE SET net_amount = EXCLUDED.net_amount
                    """)
            .itemSqlParameterSourceProvider(item ->
                    new MapSqlParameterSource()
                            .addValue("batchKey", item.batchKey())
                            .addValue("transactionId", item.transactionId())
                            .addValue("netAmount", item.netAmount()))
            .build();
}
~~~

Với cùng `batchKey`, `transactionId` và `netAmount`, chạy lại không tạo thêm bản ghi. Nhưng **UPSERT không bảo đảm kết quả giống nhau nếu input thay đổi**: lần phát lại có thể ghi đè số tiền khác. Khi đó có thể giữ `input_hash` hoặc `rule_version` trong bảng và **từ chối conflict có giá trị không khớp** thay vì cập nhật tùy ý.

### Khi writer gọi hệ thống ngoài

Giả sử worker cần gửi lệnh thanh toán:

~~~text
Transaction ID = tx-1001
Operation       = capture-payment
Idempotency key = settlement-2026-11-26/tx-1001/capture-payment
~~~

Hệ thống nhận phải **tự hỗ trợ idempotency key** hoặc có bảng xử lý riêng để bảo đảm cùng operation không được áp dụng hai lần. Nếu cần vừa ghi DB vừa phát event, cân nhắc **transactional outbox**: ghi dữ liệu nghiệp vụ và outbox row trong cùng DB transaction, sau đó publisher độc lập chuyển event với consumer dedup.

**Không lấy độ duy nhất của `ChunkRequest.sequence` thay cho record-level idempotency**: các chunk có thể được tạo lại với ranh giới khác sau restart hoặc deploy; một record nghiệp vụ có thể xuất hiện trong nhiều lần thử.

## 8. Transaction boundary: worker và manager là hai phía độc lập

Ở worker, `ItemWriter` có thể ghi dưới transaction phù hợp với hạ tầng Spring Batch Integration và transaction manager được cấu hình. Ở manager, đọc nguồn, gửi request, nhận reply và cập nhật trạng thái liên quan tới các giao dịch/điểm checkpoint khác.

~~~text
Manager JVM                         Worker JVM
---------------------------------   ---------------------------------
Reader / JobRepository              Receive ChunkRequest
Send request -> broker               Processor / Writer
Wait/correlate reply                  DB transaction COMMIT/ROLLBACK
Update StepExecution                 Reply -> broker

Không mặc định một ACID transaction bao phủ cả hai JVM.
~~~

**Quan trọng về ACK:**

- **Publisher confirm**: broker đã nhận publish theo hợp đồng broker; chưa chứng minh worker xử lý.
- **Consumer ACK**: broker biết delivery đã được xử lý theo chính sách listener; chưa đủ để chứng minh DB và reply đều hoàn tất nếu không có giao thức phối hợp.
- **ChunkResponse success**: worker cho biết phần xử lý tương ứng thành công; vẫn cần manager nhận và cập nhật metadata.
- **DB commit**: kết quả nghiệp vụ được lưu trong phạm vi transaction đó; không bảo đảm reply/ACK đã đến nơi.

Trong cấu hình production, cần mô tả chính xác **ai điều khiển transaction DB, ACK khi nào, publisher confirm/reply có được bảo đảm không và xử lý timeout ra sao**. Thử trực tiếp các điểm lỗi sẽ đáng tin hơn việc suy luận chỉ từ tên thuộc tính của broker.

### Có nên bọc tất cả bằng XA/2PC?

Distributed transaction có thể được cân nhắc trong một số môi trường, nhưng thường tăng độ phức tạp, độ trễ, rủi ro lock và yêu cầu tài nguyên hỗ trợ. Nhiều hệ thống ưu tiên **at-least-once delivery + idempotent writer + outbox/dedup** hơn là cố tạo một giao dịch chung cho broker và DB. Quyết định phải dựa trên yêu cầu đúng đắn, khả năng broker/DB và chi phí vận hành, không phải một mặc định của Spring Batch.

## 9. Khung Spring Batch Integration 5.x cho manager và worker

Spring Batch Integration cung cấp builder để dựng **remote chunking manager step** và **worker integration flow**. Đoạn code sau là **bộ khung cấu hình định hướng** cho Spring Batch 5.x/Spring Integration; cần thêm dependency Spring Batch Integration, broker adapter, bean infrastructure, import và kiểm tra chữ ký API theo version đang dùng trước khi biên dịch.

### 9.1. Manager gửi chunk và nhận reply

~~~java
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
        ItemReader<SaleTask> saleReader,
        @Qualifier("managerRequests") MessageChannel requests,
        @Qualifier("managerReplies") MessageChannel replies) {

    return new RemoteChunkingManagerStepBuilder<SaleTask, SaleResult>(
                    "remoteChunkManagerStep", jobRepository)
            .chunk(200, transactionManager)
            .reader(saleReader)
            .outputChannel(requests)
            .inputChannel(replies)
            .build();
}
~~~

`managerRequests` và `managerReplies` chỉ là **channel nội bộ của ứng dụng manager**. Hai channel này phải được nối bằng Spring Integration flow tới **request queue** và từ **reply queue** của broker. Chúng **không tự tạo mạng lưới remote**.

### 9.2. Worker nhận và xử lý ChunkRequest

~~~java
@Bean
MessageChannel workerRequests() {
    return new DirectChannel();
}

@Bean
MessageChannel workerReplies() {
    return new DirectChannel();
}

@Bean
IntegrationFlow remoteChunkWorkerFlow(
        @Qualifier("workerRequests") MessageChannel requests,
        @Qualifier("workerReplies") MessageChannel replies,
        ItemProcessor<SaleTask, SaleResult> saleProcessor,
        ItemWriter<SaleResult> saleWriter) {

    return new RemoteChunkingWorkerBuilder<SaleTask, SaleResult>()
            .itemProcessor(saleProcessor)
            .itemWriter(saleWriter)
            .inputChannel(requests)
            .outputChannel(replies)
            .build();
}
~~~

Worker ở đây **không có ItemReader**: nhận `ChunkRequest` đã mang những `SaleTask` được manager đọc. Một deployment có thể chạy nhiều consumer tương ứng với khả năng xử lý và tài nguyên. Nếu cấu hình worker integration flow chạy đồng thời, processor/writer và service dùng chung phải được đánh giá thread safety. Đừng tự suy ra `@StepScope` trên worker có đầy đủ StepExecution context như khi chạy một partitioned worker step.

**Lưu ý về builder generics:** chữ ký cụ thể của `RemoteChunkingManagerStepBuilder` và `RemoteChunkingWorkerBuilder` có thể khác giữa các nhánh Spring Batch Integration, đặc biệt các thay đổi Spring Batch 4 → 5. Ví dụ trên trình bày quan hệ manager/worker; khi áp dụng, đối chiếu artifact và API chính xác đã khóa trong dự án. Không triển khai hai phía khác phiên bản serialization mà chưa có bài test tương thích.

### 9.3. Nối request và reply qua middleware

~~~text
MANAGER APP
  managerRequests
      -> Spring Integration outbound adapter
      -> broker exchange/topic/request queue

WORKER APP
  broker request queue
      -> Spring Integration inbound adapter
      -> workerRequests
      -> RemoteChunkingWorkerBuilder flow
      -> workerReplies
      -> Spring Integration outbound adapter
      -> broker reply queue

MANAGER APP
  broker reply queue
      -> Spring Integration inbound adapter
      -> managerReplies
      -> RemoteChunkingManagerStepBuilder
~~~

Với RabbitMQ/AMQP, JMS hoặc middleware khác, adapter và cấu hình xác nhận/transaction khác nhau. Đầu nối phải **bảo toàn payload, headers tương quan và định dạng serialization** theo protocol của Spring Batch Integration. Một message converter ở hai phía không thống nhất có thể khiến request nhận được nhưng worker không deserialize được hoặc reply không correlate.

### 9.4. Các giả định hạ tầng

| Giả định | Điều phải kiểm chứng |
| --- | --- |
| Manager và worker dùng serializer/schema tương thích | Test request và reply end-to-end sau deployment |
| Broker có queue/exchange/routing key đúng | Không gửi nhầm sang worker/job khác |
| Reply đi về manager đang chờ | Correlation và địa chỉ reply chính xác |
| Request/reply cần độ bền | Persistent message + durable topology khi broker hỗ trợ; test crash |
| Worker có quyền DB | Credential tối thiểu, routing theo tenant/snapshot nếu cần |
| Worker có thể scale ngang | Nhiều consumer cùng xử lý queue theo concurrency limit |
| Manager còn sống để tổng hợp | Có timeout/monitoring và restart policy rõ |

**Khi triển khai worker thực tế, nên tách configuration của manager và worker** thành hai ứng dụng/role; không đặt reader nguồn và job manager vào mỗi worker nếu không cần.

## 10. Worker nhận chunk qua adapter: ordering, prefetch và concurrency

Middleware thường cho nhiều consumer cạnh tranh trên cùng request queue. Cùng một queue có thể giao chunk A cho worker 1, chunk B cho worker 2; chunk B xử lý/commit nhanh hơn chunk A.

~~~text
Manager gửi chunk 1, 2, 3
Worker A nhận chunk 1 -> xử lý 9 giây
Worker B nhận chunk 2 -> xử lý 2 giây -> reply trước
Worker C nhận chunk 3 -> xử lý 4 giây -> reply tiếp
Worker A reply cuối
~~~

**Không thiết kế nghiệp vụ dựa trên thứ tự reply hay thứ tự commit trùng thứ tự chunk.** Manager phải đối chiếu bằng thông tin correlation/protocol. Nếu kết quả cần thứ tự tổng thể, phải chọn kiến trúc khác: khóa nghiệp vụ, partition theo key, ordered sink hoặc bước sắp xếp/hợp nhất sau.

Các nút vặn thường có:

- **Consumer concurrency** của inbound adapter/listener: số chunk worker có thể xử lý cùng lúc.
- **Prefetch** của broker: số delivery có thể ở phía consumer nhưng chưa ACK; quá lớn có thể làm một worker giữ nhiều request mà không xử lý kịp.
- **Chunk size** của manager: số item trong một request.
- **Broker message size/TTL**: giới hạn payload và vòng đời; quá lớn có thể gây reject hoặc tăng heap.
- **Outbound publish/reply throughput**: có thể thành bottleneck dù processor nhanh.
- **DB connection pool**: số transaction đồng thời phải phù hợp khả năng DB.

Không lấy `prefetch=50` đồng nghĩa “50 chunk đang ghi DB”. Prefetch thể hiện **delivery outstanding** ở phía consumer, còn số tác vụ thực sự xử lý phụ thuộc listener thread/concurrency và implementation.

## 11. Backpressure: đừng để manager làm ngập broker

Remote chunking có một **nguồn phát chunk tập trung**. Nếu manager đọc và gửi nhanh hơn tổng tốc độ xử lý của worker, request backlog tăng:

~~~text
Manager: 300 chunks/phút
Tổng worker: 180 chunks/phút
Backlog tăng xấp xỉ 120 chunks/phút (nếu không điều tiết).
~~~

Queue lớn có thể hấp thụ đột biến nhưng không giải quyết **quá tải kéo dài**. Hậu quả gồm độ trễ tăng, disk usage broker tăng, message expiry, retry storm và thời gian job khó dự báo.

Giải pháp:

1. **Đo** độ trễ từ publish tới worker start, worker processing duration và reply latency; không chỉ nhìn queue depth.
2. **Giới hạn số chunk đang chờ phản hồi (in-flight)** ở manager theo cơ chế Spring Batch Integration/transport hoặc một điều phối được kiểm chứng; không tự giả định `gridSize` của partitioning là giới hạn remote-chunk backlog.
3. **Tăng số worker khi còn tài nguyên thật**, thay vì chỉ nới queue.
4. **Điều chỉnh chunk size**: chunk quá nhỏ làm nhiều message/ACK/transaction; chunk quá lớn tăng payload, rollback cost và thời gian xử lý từng request.
5. **Giới hạn prefetch/concurrency** để worker không nhận quá nhiều request vượt DB/API capacity.
6. **Đặt alert** cho backlog, message age, redelivery, reply timeout và DLQ.

Lưu ý: một số phiên bản/thiết kế remote chunking manager có **giới hạn số yêu cầu outstanding** hoặc cơ chế chờ reply. Hãy xác minh giới hạn và cấu hình thực tế bằng metrics, không suy ra manager luôn đọc không hạn chế hay luôn được điều tiết tự động.

## 12. Retry, redelivery và poison message

Lỗi trong worker cần được phân loại trước khi quyết định retry:

| Loại lỗi | Ví dụ | Cách ứng xử |
| --- | --- | --- |
| **Transient** | DB connection timeout ngắn, broker tạm gián đoạn | Retry có giới hạn, backoff/jitter, theo dõi số lần thử |
| **Permanent dữ liệu** | Item thiếu khóa, payload sai schema, số tiền âm bị cấm | Phản hồi lỗi hoặc DLQ/quarantine theo hợp đồng job; không retry vô hạn |
| **Permanent cấu hình** | Thiếu quyền DB, worker dùng serializer khác manager | Dừng xử lý, sửa cấu hình/deploy, không nuốt lỗi |
| **Ambiguous outcome** | DB đã commit nhưng reply/ACK mất | Redelivery có thể xảy ra; dùng idempotency và đối soát |
| **Quá tải** | DB pool cạn, API 429 | Backoff, giới hạn consumer; tránh retry storm |

### Một chunk chứa nhiều item, một item bị lỗi thì sao?

Nếu worker đang ghi một chunk trong một transaction và một item ném exception, hệ thống có thể rollback các ghi thuộc transaction đó; chính sách fault tolerance có thể retry/skip tùy cấu hình và cách integration flow vận hành. **Không mặc định một lỗi item sẽ được skip thành công ở remote worker** chỉ vì manager step có cấu hình skip cho local chunk.

Chính sách cần rõ:

- Có được **skip item** hay phải fail cả chunk?
- Retry xảy ra trong worker, broker redelivery, hay ở manager? Các lớp retry có thể **nhân số lần thử** ngoài dự kiến nếu chồng nhau.
- Sau khi hết retry, worker báo lỗi qua reply hay broker đưa message vào **dead-letter queue**?
- Manager có biết job **chưa hoàn tất** nếu message bị đẩy sang DLQ mà không còn reply không?
- Ai sửa poison message, và làm thế nào replay mà không nhân đôi kết quả trước đó?

**Không dùng DLQ như một thùng rác im lặng.** Một chunk bị chuyển vào DLQ mà manager vẫn chờ reply cần cơ chế theo dõi, timeout và báo thất bại rõ. Không tự ACK poison message rồi trả success nếu chưa có chính sách nghiệp vụ cho phép bỏ qua dữ liệu.

### Nguy cơ retry storm

Với 10 worker, mỗi worker retry một lỗi DB tức thì 100 lần có thể tạo thêm tải khiến DB càng không phục hồi. Dùng **bounded retries, exponential backoff với jitter**, giới hạn worker và circuit breaker khi phù hợp. Tính tổng retry của cả Spring Retry, listener container và broker TTL/DLQ, không chỉ một cấu hình đơn lẻ.

## 13. Bốn kịch bản failure injection quan trọng

### Kịch bản A — Worker chết trước khi ghi

~~~text
Manager -> request chunk#42
Broker -> Worker A
Worker A chết trước DB commit
Broker có thể redeliver theo ACK/transaction config
Worker B nhận lại
Worker B ghi và reply
~~~

Nếu broker/adapter có delivery bền vững và ACK đúng thời điểm, chunk có thể được giao lại. Nhưng **phải test cấu hình thực tế**: auto-ACK quá sớm hoặc message không durable có thể khiến thông điệp mất.

### Kịch bản B — Worker commit rồi mất reply

~~~text
Worker A: DB COMMIT thành công
Worker A: crash hoặc reply không tới manager
Manager: timeout/unknown outcome
Chunk được replay hoặc delivery lại
Worker B: gặp cùng (batchKey, transactionId)
Writer idempotent -> không ghi thêm tác động sai
~~~

Đây là lý do **không thể chỉ tin vào trạng thái reply**. Nếu writer là `balance = balance + amount` thì replay có thể cộng tiền hai lần; cần operation key và dedup transaction.

### Kịch bản C — Manager chết khi còn chunk đang bay

Một số worker có thể đã commit; một số message nằm trong broker; một số reply chưa tới hoặc đã tới nhưng manager chưa cập nhật metadata. Sau khi manager khởi động lại, cần **restart cùng JobInstance với dữ liệu nguồn ổn định**, đối soát trạng thái và dựa trên idempotency khi xử lý lại. Không tự xóa request queue để “làm sạch” vì có thể làm mất công việc mà StepExecution chưa ghi nhận.

### Kịch bản D — Reply bị lặp hoặc đến sai job

Nếu hai job cùng dùng reply queue, correlation/headers bị mất ở adapter có thể khiến manager không biết reply thuộc request nào. Phải bảo toàn định danh correlation/sequence mà framework sử dụng, tách routing theo contract và không tạo một reply giả chỉ có `status=SUCCESS` mà thiếu thông tin liên kết.

| Điểm lỗi | Tình trạng DB có thể | Tình trạng broker có thể | Bảo vệ chính |
| --- | --- | --- | --- |
| Trước DB write | Chưa commit | Có thể còn request để redeliver | Durable delivery + retry |
| Giữa transaction | Rollback hoặc chưa rõ khi mất kết nối | Delivery đang chờ ACK | Transaction + idempotency |
| Sau commit, trước ACK | **Đã có kết quả** | Có thể redeliver | Unique business key/dedup |
| Sau ACK, trước reply | Đã có kết quả nhưng manager chưa biết | Request có thể không quay lại | Reply reliability + timeout/đối soát |
| Sau reply publish, trước manager nhận | Đã có kết quả | Reply có thể bị trễ/mất/lặp | Correlation + durable reply khi cần |
| Manager restart | Nhiều trạng thái kết quả khác nhau | In-flight/queued requests | JobRepository + snapshot + replay safety |

## 14. Restart: bảo vệ reader, chunk và business effect

Trong remote chunking, **manager thường sở hữu reader và thông tin StepExecution**. Khi restart một JobInstance thất bại:

1. Giữ **identifying JobParameters** và snapshot dữ liệu đầu vào đã chốt.
2. Đảm bảo reader có checkpoint phù hợp với dữ liệu không thay đổi; không tự sửa vị trí đọc để “nhảy qua” chunk chưa có kết quả rõ ràng.
3. Kiểm tra request/reply queue còn message của lần chạy cũ hay không; xác định chính sách xử lý **stale messages** và correlation theo JobExecution.
4. Xác minh worker cũ đã dừng hoặc có cách chống xử lý đồng thời cùng operation.
5. Bảo vệ kết quả bằng **business-key idempotency** ngay cả khi framework replay một item ở chunk mới.
6. Đối soát tập output với source snapshot trước khi downstream bắt đầu.

**Một StepExecution COMPLETED hoặc một ACK broker riêng lẻ không tự chứng minh mọi tác động ngoài hệ thống đã đúng.** JobRepository phản ánh hợp đồng batch; cơ sở dữ liệu đích và hệ thống gọi ngoài cần kiểm tra bổ sung.

### Một ma trận trạng thái khi vận hành

| Tình trạng | Hành động gợi ý |
| --- | --- |
| Worker báo lỗi dữ liệu vĩnh viễn | Xác định record và chunk, báo job fail/quarantine có kiểm soát; không retry vô hạn |
| Worker mất kết nối tạm thời | Chờ retry/redelivery có giới hạn, quan sát backlog và timeout |
| Manager timeout nhưng có output DB | Kiểm tra business key/idempotency trước replay |
| Có stale message từ JobExecution trước | Dùng correlation/protocol, không áp dụng mù vào job mới |
| Broker nhận nhiều request trùng | Dedup business effect, ghi log attempt và chunk identity |
| Job đã hoàn tất nhưng DLQ còn message thuộc job | Điều tra tương quan và đối soát; không tự động coi đó là dữ liệu được bỏ qua hợp lệ |

## 15. Thread safety khi một worker xử lý nhiều chunk

Một worker process có thể có nhiều consumer thread; cùng một bean `ItemProcessor`, `ItemWriter`, cache hoặc HTTP client được gọi đồng thời. Cần phân biệt:

- **Thread safety trong JVM:** field mutable của processor, `ArrayList`, formatter, map/cache, `ThreadLocal`.
- **Tính đúng đắn liên worker:** hai process khác JVM cùng nhận lại một item; Java `synchronized` trong một JVM **không bảo vệ** dữ liệu ở process kia.
- **Tính đúng đắn DB:** khóa duy nhất, transaction isolation, update có điều kiện, deadlock retry và idempotency.
- **Tenant isolation:** nếu payload chứa `tenantId`, worker phải kiểm tra quyền/route và writer dùng khóa bao gồm tenant. Không lưu `currentTenant` trong singleton field.

Ví dụ sai:

~~~java
@Component
class UnsafeWorkerProcessor implements ItemProcessor<SaleTask, SaleResult> {
    private long processed = 0;  // Shared mutable counter

    @Override
    public SaleResult process(SaleTask item) {
        processed++;
        return new SaleResult(
                item.batchKey(), item.transactionId(),
                item.grossAmount().add(BigDecimal.valueOf(processed)));
    }
}
~~~

`processed++` vừa không thread-safe, vừa làm kết quả **phụ thuộc thứ tự giao chunk**, không deterministic qua restart. Chuyển thành `AtomicLong` chỉ giải quyết race của counter, **không** giải quyết tính đúng nghiệp vụ, retry hoặc nhiều worker JVM.

Ưu tiên processor thuần trên item và immutable configuration. Nếu cần telemetry, dùng metrics thread-safe; **không coi counter số lần process là số record đã commit**, vì rollback và retry có thể gọi lại processor.

## 16. Quản lý payload, serialization và version

Một request chứa 1.000 item với nhiều field/JSON nested có thể vượt giới hạn message broker hoặc tốn thời gian serialize/network hơn xử lý nghiệp vụ.

| Hạng mục | Điều cần quyết định | Rủi ro nếu bỏ qua |
| --- | --- | --- |
| Chunk size | Số item mỗi request | Quá lớn gây payload/rollback lớn; quá nhỏ tốn message overhead |
| Message size | Giới hạn byte của broker và converter | Publish reject, memory spike |
| Serializer | JSON/Java serialization/Avro/Protobuf theo hỗ trợ framework | Không deserialize được, remote code execution risk với deserialization không tin cậy |
| Schema version | Manager/worker deploy độc lập | Worker cũ không hiểu field mới |
| Correlation headers | Giữ nguyên qua outbound/inbound adapters | Reply không khớp yêu cầu, manager timeout |
| Dữ liệu nhạy cảm | Mã hóa/ẩn theo chính sách và hạn chế log | Broker snapshot, DLQ hoặc logs chứa PII |
| Retention / TTL | Bao lâu message tồn tại | Expire trước xử lý hoặc stale request chạy quá muộn |

Nếu dùng **Java native serialization**, phải đặc biệt kiểm soát loại class và ranh giới tin cậy. Không deserialize object từ nguồn không đáng tin vào JVM tùy ý. Dùng serializer rõ schema/allowlist và thử compatibility. **Không thay đổi DTO/serialVersionUID hoặc mapper configuration giữa manager và worker mà không thử round-trip thực sự.**

### Có nên chỉ gửi tham chiếu thay vì full items?

Nếu payload item quá lớn, có thể gửi `snapshotId` cùng danh sách record ID/tham chiếu object bất biến. Tuy nhiên khi worker phải tự truy xuất payload, mô hình đã thêm **I/O đọc dữ liệu tại worker**; cần xét quyền truy cập, snapshot consistency và ranh giới với remote partitioning. Không chỉ chuyển chỗ lưu dữ liệu mà bỏ qua khả năng mất nguồn hoặc phiên bản sai khi replay.

## 17. Quan sát và truy vết end-to-end

Các log và metric của manager/worker/broker phải có khả năng nối một chunk từ lúc gửi đến lúc hoàn thành:

- `jobName`, `jobInstanceId`/`jobExecutionId`, `stepExecutionId` nếu protocol có và được phép log.
- `chunkSequence` hoặc logical correlation key, request ID và số lần delivery.
- `batchKey`, snapshot version và **số item trong chunk**.
- Worker node/instance, start/end time, processing duration, DB commit duration.
- Broker publish time, request queue wait, redelivery count, reply round-trip time.
- Số item đã ghi, retry/skip/error, số record dedup tại sink.

| Metric | Câu hỏi vận hành | Ngưỡng/cảnh báo gợi ý |
| --- | --- | --- |
| Requests published/s | Manager cấp việc nhanh đến đâu? | Sụt đột ngột khi reader đang có dữ liệu |
| Consumer processing chunks/s | Worker xử lý kịp không? | Dưới tốc độ gửi kéo dài |
| Request queue depth và oldest age | Backlog có già đi không? | Age vượt SLA, không chỉ depth |
| In-flight chunks | Có bao nhiêu request chưa có kết quả rõ? | Gần giới hạn admission lâu |
| Reply success/error/timeout | Manager có nhận đủ phản hồi? | Timeout hoặc missing reply tăng |
| Redelivery và retry count | Có lỗi lặp hoặc storm không? | Tăng đột biến |
| DLQ depth và message age | Poison/unrecoverable messages còn chờ xử lý? | Mọi message mới cần điều tra |
| DB active/waiting connections | Worker có làm cạn pool? | Waiting cao và commit latency tăng |
| Item result dedup/conflict | Có nhiều lần ghi cùng business key? | Conflict giá trị khác cần fail |
| CPU/heap/GC/serialization time | Payload hoặc processing có làm JVM nghẽn? | GC pause hoặc memory tăng |

Không gắn `transactionId` của mọi record vào metric tag có cardinality cực lớn. Dùng metric tổng hợp theo job, worker, loại lỗi; chi tiết per-chunk có thể lưu trong log/tracing có retention và quyền truy cập phù hợp.

## 18. Kiểm thử từ worker thuần đến middleware thực

Chạy một bộ test theo các lớp, tăng dần mức realism:

### 18.1. Unit test processor/writer

- Cùng input và cùng rule version phải cho cùng output.
- Dữ liệu bất hợp lệ phát ra lỗi có thể phân loại, không tạo output giả.
- Ghi lại cùng `(batchKey, transactionId)` hai lần vẫn có một result đúng.
- Nếu hai lần ghi cùng khóa mà giá trị khác nhau, hệ thống phải **phát hiện** theo chính sách.
- Hai worker đồng thời ghi cùng khóa không phá unique constraint hoặc tạo side effect trùng.

Ví dụ unit test tính tiền:

~~~java
@Test
void processingIsDeterministicAcrossRetries() throws Exception {
    ItemProcessor<SaleTask, SaleResult> processor = saleProcessor();
    SaleTask task = new SaleTask(
            "batch-1", "tx-1001", new BigDecimal("123.456"));

    SaleResult first = processor.process(task);
    SaleResult replay = processor.process(task);

    assertEquals(new BigDecimal("123.46"), first.netAmount());
    assertEquals(first, replay);
}
~~~

### 18.2. Integration test protocol request/reply

Với manager, worker và middleware chạy trong môi trường test:

1. Chạy một job có ít item, chia thành nhiều chunk.
2. Kiểm tra request được broker nhận, worker xử lý và reply **correlate đúng** từng chunk.
3. Cho nhiều consumer chạy, cố ý làm một chunk chậm hơn chunk sau để xác minh manager không phụ thuộc reply order.
4. Xác minh trạng thái JobExecution/StepExecution cùng tập khóa/giá trị đầu ra.
5. Đổi schema DTO chỉ ở worker trong test riêng; hệ thống phải phát hiện incompatibility rõ ràng, không silently success.

**Test với DirectChannel thuần không chứng minh độ bền/redelivery của broker.** Cần một bài test tích hợp **broker thật hoặc Testcontainers tương ứng** và các adapter publish/consume/reply của sản phẩm.

### 18.3. Dùng CountDownLatch để tạo lỗi đúng điểm

Không dùng `Thread.sleep` để đoán thời gian crash. Trong môi trường test, đặt các barrier có kiểm soát:

~~~java
final class WorkerFailureProbe {
    final CountDownLatch beforeWrite = new CountDownLatch(1);
    final CountDownLatch allowWrite = new CountDownLatch(1);
    final AtomicInteger received = new AtomicInteger();

    void pauseBeforeWrite() throws InterruptedException {
        received.incrementAndGet();
        beforeWrite.countDown();
        if (!allowWrite.await(30, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Test timed out");
        }
    }
}
~~~

Test runner chờ `beforeWrite` rồi đóng consumer/session hoặc gây một lỗi có kiểm soát, sau đó mở `allowWrite` trong `finally` để không treo test. Kiểm tra broker có redeliver theo cấu hình, writer không tạo bản ghi trùng và manager không báo COMPLETED trước khi đủ reply.

Lưu ý: việc **kill process thật** có hành vi khác với ném exception trong một callback. Nên có cả test ngắt JVM/worker container ở môi trường kiểm thử để xác minh ACK, transaction và redelivery tại các ranh giới thực.

### 18.4. Ma trận failure integration test

| Injection | Kết quả mong đợi cần xác minh |
| --- | --- |
| Worker crash trước DB commit | Transaction không tạo kết quả sai; request có thể replay theo hợp đồng durable delivery |
| Worker crash sau DB commit trước ACK/reply | Redelivery/replay không nhân đôi business effect |
| Manager restart khi request còn in-flight | Không mất record và không “đếm đôi” contribution |
| Broker gián đoạn khi publish | Job thất bại/đợi/retry theo policy rõ, không silently bỏ chunk |
| Reply mất hoặc duplicate | Correlation chính xác, manager timeout/đối soát khi cần |
| Poison item trong một chunk | Bounded retry, DLQ/failure policy và job không báo thành công giả |
| Hai consumer nhận cùng operation qua replay | Unique business key/dedup bảo vệ cả hai JVM |
| Queue backlog cao | Backpressure/alert hoạt động; không dẫn đến OOM |
| Manager/worker khác schema version | Serialization lỗi rõ, có cơ chế rolling upgrade |

## 19. Performance: chọn chunk size và worker concurrency

Remote chunking có thêm chi phí **serialize request, truyền broker, deserialize ở worker, trả reply và correlation**. Tăng số worker không làm tốc độ tổng vượt điểm nghẽn của manager reader hoặc broker.

Một cách ước lượng mức trần (mang tính định tính):

~~~text
Throughput hệ thống <= min(
    tốc độ đọc của manager,
    tốc độ publish/consume của broker,
    tổng năng lực xử lý/ghi của workers,
    năng lực business DB/downstream
)
~~~

| Thử nghiệm | Chunk size | Worker concurrency | Điều cần đo |
| --- | ---: | ---: | --- |
| A | 100 | 1 | Baseline đọc, CPU, round-trip, DB |
| B | 100 | 4 | Có tăng throughput hay nghẽn broker? |
| C | 500 | 4 | Ít message hơn, payload/rollback lớn hơn |
| D | 1.000 | 4 | Payload có vượt broker/frame/memory? |
| E | 500 | 8 | DB pool và writer có chịu được thêm worker? |
| F | 500 | 4, prefetch thấp | Phân phối công việc/cân bằng, reply latency |

**Ví dụ:** processor rất tốn CPU nhưng manager đọc nhanh và network ổn định, tăng worker từ 1 lên 4 có thể cải thiện rõ. Nếu manager chỉ đọc được 5.000 item/giây thì tăng workers tới 20 vẫn không làm toàn pipeline vượt 5.000 item/giây khi input chỉ đi qua reader đó.

Đối với **chunk size**, thử nhiều giá trị trên cùng snapshot và theo dõi cả thời gian xử lý trung bình, p95/p99, kích thước payload, số request/reply, GC và rollback latency. Với một item quá lớn, cần giới hạn kích thước theo **byte thực**, không chỉ theo số item.

Nếu số lượng message rất cao và mỗi item xử lý nhẹ, overhead middleware có thể chiếm ưu thế. Khi đó xem lại **local partitioning**, multi-threaded step hoặc chia vùng để worker tự đọc thay vì remote chunking.

## 20. Runbook khi worker không nhận hoặc không trả chunk

Giả sử manager đang RUNNING nhưng không thấy tiến độ:

1. **Xác định JobExecution và step**: thời điểm chunk cuối gửi, số request outstanding, trạng thái JobRepository và timeout.
2. **Kiểm tra broker**: queue tồn tại và routing key đúng không; depth/oldest age, unacked messages, redelivery/DLQ.
3. **Kiểm tra consumer**: worker có kết nối broker không, có deserialize được request không, concurrency/prefetch đang thế nào.
4. **Kiểm tra DB và downstream**: worker có treo ở connection wait, lock, API timeout hay xử lý chunk quá lớn không.
5. **Kiểm tra reply path**: reply đã publish? Reply queue có tồn đọng? Correlation/header có bị converter làm mất?
6. **Phân loại outcome**: chunk chưa được xử lý, đã commit nhưng mất reply, hoặc không thể xác nhận; không xóa queue bừa.
7. **Khôi phục có kiểm soát**: xử lý poison/DLQ theo policy, đảm bảo worker cũ dừng hoặc được chống lặp, restart cùng snapshot/JobInstance khi phù hợp.
8. **Đối soát**: so sánh business keys, giá trị, side effects, skip/retry trước khi báo job hoàn tất và cho downstream tiếp tục.

### Dấu hiệu lỗi và câu hỏi đầu tiên

| Triệu chứng | Kiểm tra đầu tiên | Hướng xử lý điển hình |
| --- | --- | --- |
| Request queue tăng, worker idle | Routing/binding, consumer kết nối, converter | Sửa route/consumer; test end-to-end |
| Worker xử lý nhưng manager không tiến | Reply queue, correlation, reply adapter | Sửa reply path, không tự phát success giả |
| Worker redelivery liên tục | DB/ACK timing, poison message, exception | Backoff, DLQ có kiểm soát, idempotency |
| Job báo thành công nhưng output thiếu | Reply protocol, SQL writer, skip policy | Đối soát, điều tra commit/ack |
| Output trùng sau crash | Dedup key thiếu hoặc writer không idempotent | Ràng buộc business key và transaction |
| Tăng số worker nhưng chậm | Manager reader, broker, DB pool, network | Đo bottleneck và cân nhắc partitioning |
| OOM khi tải cao | Chunk payload lớn, queue/prefetch quá rộng | Giảm chunk/in-flight, đo heap |
| Lộ dữ liệu tenant khác trong worker | Payload/routing thiếu tenant, mutable context | Xác thực tenant và quyền DB, guard writer |
| Chỉ lỗi khi deploy phiên bản mới | Serializer/schema DTO không tương thích | Version contract và kiểm tra rolling upgrade |

## 21. Bài thực hành và checklist trước production

**Bài thực hành:** xây một manager đọc dữ liệu CSV hoặc staging DB đã chốt, tạo chunk 100–500 item; hai worker dùng chung request queue và ghi kết quả vào PostgreSQL bằng khóa `(batch_key, transaction_id)`. Dùng broker phù hợp (ví dụ RabbitMQ) với request/reply flow của Spring Batch Integration.

Yêu cầu:

1. **Luồng cơ bản:** manager gửi nhiều chunk, hai worker xử lý, mọi result đúng, không cần reply theo thứ tự.
2. **Concurrency:** tăng 1 lên 2 và 4 worker; đo throughput, queue wait, DB pool và reply latency.
3. **Crash trước commit:** dừng worker trước khi write; xác minh redelivery hoặc failure rõ theo hợp đồng.
4. **Crash sau commit:** làm mất ACK hoặc reply trong môi trường test; xác minh business key không bị ghi trùng sau replay.
5. **Poison item:** đưa payload vi phạm schema/rule; verify bounded retry, DLQ/quarantine và trạng thái job.
6. **Manager restart:** gián đoạn manager khi còn in-flight chunk; dùng cùng identifying JobParameters/snapshot, đối soát toàn bộ kết quả.
7. **Bảo mật:** kiểm tra worker không thể xử lý tenant/source ngoài quyền, không log nội dung nhạy cảm.
8. **Hiệu năng:** thử chunk size khác nhau và số consumer khác nhau; xác định nút thắt và kiến trúc phù hợp.

Checklist:

- [ ] Đã chọn đúng **remote chunking**: manager có thể đọc nguồn đủ nhanh và worker mới là phần cần mở rộng.
- [ ] Manager và worker dùng protocol/serialization tương thích; request/reply channels đi qua broker thật.
- [ ] Request chứa hoặc tham chiếu tới input snapshot bất biến; mỗi record có business key ổn định.
- [ ] Reply được correlate đúng chunk, có timeout và xử lý reply thiếu/trùng.
- [ ] Đã phân biệt publisher confirm, consumer ACK, DB commit và manager cập nhật StepExecution.
- [ ] Writer idempotent, không có side effect không thể replay an toàn; outbox/dedup khi cần.
- [ ] Có retry hữu hạn, backoff, poison-message/DLQ policy và cảnh báo.
- [ ] Consumer concurrency, prefetch, chunk size và số request in-flight được giới hạn theo tài nguyên.
- [ ] Có kiểm thử crash trước/sau commit, mất reply, manager restart, duplicate message và schema mismatch.
- [ ] Có dashboard queue depth/age, redelivery, reply latency, StepExecution, DB pool và business reconciliation.
- [ ] Có runbook bảo vệ stale messages và đối soát trước khi đánh dấu job thành công về mặt nghiệp vụ.

**Ghi nhớ:** khi worker nhận chunk qua middleware, **thành công của việc truyền thông điệp không tự bảo đảm thành công của giao dịch nghiệp vụ**. Thiết kế vững chắc phải kết hợp **request/reply correlation, transaction đúng phạm vi, input snapshot ổn định, worker stateless, writer idempotent, retry có giới hạn và quan sát xuyên broker–manager–worker**. Remote chunking chỉ tăng hiệu quả nếu manager reader không là nút thắt và số worker được chọn theo năng lực CPU, mạng, middleware, DB thực tế.
