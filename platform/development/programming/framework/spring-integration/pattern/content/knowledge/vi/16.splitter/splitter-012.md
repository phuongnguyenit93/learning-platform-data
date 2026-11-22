# Phân biệt splitter với chunking

## 1. Bài toán: một lô 1.250 dòng hàng nên được chia như thế nào?

Một hệ thống nhận một message chứa **1.250 dòng hàng** cần kiểm tra tồn kho, tính phí vận chuyển và lưu kết quả. Nhóm phát triển đề xuất hai phương án:

- **Phương án A:** tách message thành 1.250 message, mỗi message chứa **một dòng hàng** để xử lý độc lập.
- **Phương án B:** chia danh sách thành các **chunk tối đa 100 dòng**, gửi lần lượt 13 message, mỗi message chứa một nhóm dòng hàng.

Cả hai đều được mô tả bằng từ “chia nhỏ”, nhưng **đơn vị xử lý**, **số lượng message**, **ranh giới retry/transaction**, **cách gom kết quả** và **mức độ song song** khác nhau.

Trong Enterprise Integration Patterns (EIP), **Splitter** là pattern chuyển **một message tổng hợp** thành **nhiều message con**. **Chunking** là một chiến lược **phân dữ liệu thành các khối có giới hạn kích thước, số lượng hoặc thời gian** nhằm kiểm soát bộ nhớ, tải, I/O hoặc transaction. Một hệ thống có thể dùng **Splitter để phát ra các chunk**, cũng có thể **Splitter từng phần tử mà không dùng chunking**. Vì vậy, chúng **không phải hai pattern loại trừ nhau**.

Bài học thuộc chương **Splitter** của module **SPRING_INTEGRATION_PATTERN**. Module hướng tới triển khai Enterprise Integration Patterns bằng Spring Integration để dựng message flow ít phụ thuộc và dễ mở rộng, thực hành **Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation**, đồng thời kiểm thử và theo dõi các nhánh xử lý.

**Sau bài này, bạn sẽ:** phân biệt Splitter với chunking và Spring Batch chunk-oriented processing; viết flow tách từng item hoặc từng chunk; tính ranh giới message, correlation và kích thước nhóm; quyết định khi nào nên dùng Aggregator, queue hay broker; xử lý batch rỗng, partial failure, duplicate và kiểm thử tải.

## 2. Hai khái niệm nhìn từ hai câu hỏi khác nhau

**Splitter hỏi:** “Một message đại diện cho nhiều thực thể có thể được phân rã thành những message con nào?”

**Chunking hỏi:** “Mỗi lần đọc, xử lý, truyền hoặc commit bao nhiêu dữ liệu là hợp lý?”

| Khía cạnh | Splitter (EIP) | Chunking |
|---|---|---|
| Mục tiêu | Biến một message tổng hợp thành một luồng message con | Giới hạn lượng dữ liệu trong một đơn vị công việc |
| Đơn vị đầu ra | **Message** (có payload + headers) | **Chunk** (nhóm phần tử; có thể thành message hoặc không) |
| Số phần tử mỗi đầu ra | Có thể là một item hoặc một nhóm | Thường nhiều item, tối đa theo limit |
| Vị trí trong kiến trúc | Messaging endpoint/pattern | Thuật toán phân đoạn, chiến lược I/O/batching/transaction |
| Metadata thường dùng | `correlationId`, `sequenceNumber`, `sequenceSize` | `batchId`, `chunkIndex`, `startOffset`, `itemCount` |
| Bảo đảm transaction | Không tự tạo transaction cho mọi item | Tùy hệ thống; **Spring Batch chunk step** có ranh giới commit rõ |
| Công cụ có thể dùng | Spring Integration `@Splitter`, Java DSL `split()` | Java loop, stream partition, Spring Batch, custom Transformer + Splitter |
| Ghép kết quả | Thường kết hợp Aggregator | Tùy việc phải gộp chunk/item hay không |
| Tình huống điển hình | Xử lý từng OrderLine độc lập | Ghi database 100 dòng/lượt hoặc gửi API 100 item/request |

**Điểm cốt lõi:** Splitter định nghĩa **cách phát message**, còn chunking định nghĩa **kích thước công việc**. Một Splitter có thể phát message chứa danh sách 100 phần tử; khi ấy nó đang phân phối **các chunk**, nhưng một message chunk vẫn mang **100 phần tử** chứ không phải 100 message con.

## 3. Hai sơ đồ cho cùng một lô hàng

### Splitter phát mỗi dòng thành một message

~~~mermaid
flowchart LR
    IN["OrderBatch (1.250 lines)"] --> SPLIT{"Splitter"}
    SPLIT --> A["Message: line 1"]
    SPLIT --> B["Message: line 2"]
    SPLIT --> C["..."]
    SPLIT --> D["Message: line 1.250"]
    A --> W["Line processors"]
    B --> W
    C --> W
    D --> W
~~~

Một message gốc được phân thành **1.250 message con**. Downstream có thể xử lý, retry hoặc route từng item dựa trên `sku` hay `warehouse`. Nếu muốn gom lại một kết quả đơn hàng, cần thiết kế **correlation và release strategy**.

### Chia thành chunk rồi phát mỗi chunk thành một message

~~~mermaid
flowchart LR
    IN["OrderBatch (1.250 lines)"] --> PART["Chunker: mỗi chunk tối đa 100 lines"]
    PART --> SPLIT{"Splitter"}
    SPLIT --> A["Chunk 0: lines 1–100"]
    SPLIT --> B["Chunk 1: lines 101–200"]
    SPLIT --> C["..."]
    SPLIT --> D["Chunk 12: lines 1.201–1.250"]
    A --> W["Batch processors"]
    B --> W
    C --> W
    D --> W
~~~

Sau chunking có **13 nhóm dữ liệu**; sau Splitter có **13 message**, không phải 1.250. Một worker có thể gửi mỗi chunk thành **một bulk API call**, một lần ghi DB, hoặc tự lặp qua từng phần tử trong nội bộ chunk.

**Không suy ra “ít message hơn” tức “nhanh hơn” trong mọi trường hợp.** Bulk API có thể hiệu quả hơn, nhưng một chunk lớn thất bại thường buộc retry lại nhiều phần tử nếu không có cơ chế báo lỗi từng item. Quyết định phụ thuộc năng lực consumer, tính độc lập của item và yêu cầu atomicity.

## 4. Tính kích thước và số lượng chunk

Với `N` item, chia theo kích thước tối đa `K > 0`:

\[
\text{chunkCount} =
\left\lceil \frac{N}{K} \right\rceil
\]

Ví dụ `N = 1.250` và `K = 100`:

- 12 chunk đầu có 100 item.
- Chunk cuối có 50 item.
- Tổng cộng **13 chunk**.

Không dùng phép chia nguyên `N / K` rồi bỏ phần dư; như vậy chunk cuối có thể bị bỏ sót.

| N item | K max/chunk | Số chunk | Kích thước chunk cuối |
|---:|---:|---:|---:|
| 0 | 100 | 0 | Không có |
| 1 | 100 | 1 | 1 |
| 100 | 100 | 1 | 100 |
| 101 | 100 | 2 | 1 |
| 1.250 | 100 | 13 | 50 |
| 1.250 | 500 | 3 | 250 |

**Chunk size** không phải **số lượng thread**, **số lượng partition**, hay **sequenceSize** của một Splitter ở mọi topology. Nếu danh sách của bạn được chia thành 13 chunk rồi mới split mỗi chunk thành 100 item, sẽ xuất hiện **hai cấp phân chia** có ý nghĩa correlation khác nhau.

## 5. Mô hình dữ liệu cho các ví dụ Java

Ta dùng Java 17+ để mô tả một lô và các dòng hàng:

~~~java
record OrderLine(
    String lineId,
    String sku,
    int quantity
) {}

record OrderBatch(
    String batchId,
    List<OrderLine> lines
) {}

record LineChunk(
    String batchId,
    int chunkIndex,          // 0-based
    int expectedChunks,
    List<OrderLine> lines
) {}
~~~

Các bất biến cần kiểm tra **trước khi Splitter**:

- `batchId` phải hiện diện và ổn định qua retry/replay.
- `lines` không được `null`; nếu rỗng phải có chính sách kết thúc rõ.
- Mỗi `lineId` phải ổn định và không trùng trong phạm vi batch khi nghiệp vụ yêu cầu.
- `quantity`, `sku` và các field liên quan phải đạt contract; có thể validate một lần trước khi split hoặc validate từng item tùy yêu cầu.
- `chunkIndex` là định danh vị trí của nhóm dữ liệu, **không** phải chứng nhận chunk đã được xử lý thành công.

Trong production, nếu danh sách quá lớn thì việc chứa sẵn `List<OrderLine>` của toàn bộ batch có thể là vấn đề bộ nhớ. Ở các mục sau, ta phân biệt rõ **chia danh sách đã có trong RAM** và **đọc dữ liệu thành từng trang/chunk từ nguồn ngoài**.

## 6. Splitter chuẩn: mỗi item thành một message

Spring Integration cung cấp `@Splitter` cho một method trả về collection/iterable các phần tử. Ví dụ:

~~~java
@MessageEndpoint
class OrderLineSplitter {

    @Splitter(
        inputChannel = "orders.batches",
        outputChannel = "orders.lines")
    public List<OrderLine> split(OrderBatch batch) {
        if (batch == null || batch.lines() == null) {
            throw new IllegalArgumentException("MISSING_LINES");
        }
        return batch.lines();
    }
}
~~~

Message gốc có payload `OrderBatch`; output là các message có payload `OrderLine`. Spring Integration có thể gắn sequence/correlation headers cho các message con; hiệu lực và cách tạo headers phụ thuộc loại Splitter, cấu hình `applySequence` và việc xác định được tổng số phần tử.

**Điều Splitter không tự làm:**

1. Không tự gửi mỗi item sang một tiến trình riêng hoặc chạy song song.
2. Không tự commit transaction riêng cho từng message con.
3. Không tự gom các kết quả về một `OrderResult`.
4. Không tự bảo đảm exactly-once khi broker redelivery.
5. Không tự làm cho collection cực lớn trở thành streaming bền vững nếu dữ liệu đã được materialize vào RAM.

Nếu output channel là `DirectChannel`, downstream có thể được gọi đồng bộ trong thread upstream; 1.250 lần dispatch có thể giữ thread gửi bận lâu. Nếu có `ExecutorChannel`, queue hoặc broker, concurrency và backpressure do thành phần tương ứng quyết định.

## 7. Java DSL: tách từng OrderLine

Có thể viết flow tương tự với Java DSL, thay vì dùng `@Splitter`:

~~~java
@Configuration
@EnableIntegration
class PerLineFlow {

    @Bean
    IntegrationFlow splitIntoLines() {
        return IntegrationFlow.from("orders.batches")
            .split(OrderBatch.class, OrderBatch::lines)
            .channel("orders.lines")
            .get();
    }
}
~~~

Đây là **phương án thay thế** cho annotation ở mục 6; không khai báo cả hai để cùng tiêu thụ `orders.batches` trừ khi chủ ý xây topology nhiều subscriber. Trong bài thực hành, cần consumer thực cho `orders.lines`, ví dụ một handler áp dụng business rule theo `lineId`.

Kết quả mà handler `orders.lines` nhận được:

~~~text
Message 1: payload = OrderLine(L-1, SKU-A, 2)
Message 2: payload = OrderLine(L-2, SKU-B, 1)
Message 3: payload = OrderLine(L-3, SKU-C, 5)
...
~~~

Nếu muốn giữ `batchId` trong mọi item sau khi tách, **đừng dựa duy nhất vào khả năng suy ngược từ một `OrderLine`**. Có thể dùng header do application quản lý, hoặc định nghĩa `OrderLineWork(batchId,lineId,...)` làm payload con. Metadata business ổn định có lợi cho replay, error handling và idempotency.

## 8. Chunker thuần Java: chia danh sách trước khi phát message

Chunking không nhất thiết là một component EIP riêng. Ta có thể viết một hàm partition **không làm I/O**:

~~~java
final class OrderChunker {

    List<LineChunk> partition(OrderBatch batch, int chunkSize) {
        if (batch == null || batch.batchId() == null
                || batch.batchId().isBlank()
                || batch.lines() == null) {
            throw new IllegalArgumentException("INVALID_BATCH");
        }
        if (chunkSize <= 0 || chunkSize > 1_000) {
            throw new IllegalArgumentException("INVALID_CHUNK_SIZE");
        }
        List<OrderLine> lines = batch.lines();
        if (lines.isEmpty()) {
            return List.of();
        }

        int expectedChunks =
            1 + (lines.size() - 1) / chunkSize;
        List<LineChunk> chunks = new ArrayList<>(expectedChunks);

        for (int start = 0, chunkIndex = 0;
             start < lines.size();
             chunkIndex++) {
            int end = start + Math.min(
                chunkSize, lines.size() - start);
            chunks.add(new LineChunk(
                batch.batchId(),
                chunkIndex,
                expectedChunks,
                List.copyOf(lines.subList(start, end))));
            start = end;
        }
        return List.copyOf(chunks);
    }
}
~~~

Chú ý trong code:

- `chunkSize <= 0` phải bị từ chối; không để bước lặp có thể treo hoặc chia cho 0.
- Dùng `1 + (size - 1)/chunkSize` cho danh sách không rỗng để tính số chunk mà không cần floating point.
- `end` không vượt quá `lines.size()`; chunk cuối có thể nhỏ hơn `chunkSize`.
- `List.copyOf` tạo danh sách snapshot ở mức **các tham chiếu phần tử**; nếu object item có thể sửa, nó không tự clone sâu.
- `chunkIndex` và `expectedChunks` được đặt trong **payload** để có thể giữ qua transport khi các Spring headers bị chuyển đổi/loại.

Đây là chunker cho **danh sách đã nằm trong RAM**. Hàm trả cả danh sách chunk, vì thế có thêm overhead theo số item/chunk. Nó **không** làm tăng khả năng xử lý input vô hạn. Với dữ liệu hàng triệu dòng, hãy cân nhắc paging, cursor/iterator được quản lý và bounded pipeline.

## 9. Java DSL: Transformer tạo chunks, Splitter phát từng chunk

Để gửi **13 chunk message** thay vì 1.250 line message, có thể phối hợp **Transformer + Splitter**:

~~~java
@Configuration
@EnableIntegration
class ChunkedOrderFlow {

    @Bean
    OrderChunker orderChunker() {
        return new OrderChunker();
    }

    @Bean
    IntegrationFlow splitIntoChunks(OrderChunker chunker) {
        return IntegrationFlow.from("orders.batches")
            .transform(OrderBatch.class,
                batch -> chunker.partition(batch, 100))
            .split()
            .channel("orders.chunks")
            .get();
    }
}
~~~

Đây là một topology **khác** với flow tách từng item ở mục 7. Transformer đổi payload `OrderBatch` thành `List<LineChunk>`. Splitter sau đó phát **một message cho mỗi `LineChunk`**.

Ở consumer của `orders.chunks`, mỗi message chứa một **nhóm**:

~~~java
@MessageEndpoint
class ChunkConsumer {

    private final BulkLineService bulkLineService;

    ChunkConsumer(BulkLineService bulkLineService) {
        this.bulkLineService = bulkLineService;
    }

    @ServiceActivator(inputChannel = "orders.chunks")
    public void handle(LineChunk chunk) {
        bulkLineService.process(
            chunk.batchId(),
            chunk.chunkIndex(),
            chunk.lines());
    }
}
~~~

`BulkLineService` là abstraction của ứng dụng, không phải class có sẵn của Spring Integration; cần cài đặt bean phù hợp. Nếu nó gọi bulk API hoặc ghi database theo chunk, **transaction/ack/retry** phải được cấu hình ở ranh giới đó.

**Cẩn thận:** handler `void` trên đây là **terminal consumer**, không phát một `ChunkResult`. Nếu Gateway cần chờ tổng kết của toàn bộ batch, phải tạo **result message** từ mỗi chunk và Aggregator phù hợp; không thể chỉ gắn Aggregator sau handler `void` rồi kỳ vọng có dữ liệu để gom.

## 10. Chunking không chỉ là “tách đều một List”

Ngoài chunk theo số lượng item cố định, có nhiều chiến lược:

| Loại chunk | Điều kiện phát chunk | Use case |
|---|---|---|
| **Count-based** | Đủ 100 item | Bulk insert 100 bản ghi |
| **Byte-size-based** | Tổng kích thước khoảng 1 MiB, không vượt limit | API/broker có giới hạn kích thước request |
| **Time-window** | Tích lũy trong 2 giây hoặc khi đủ số lượng | Telemetry và micro-batch |
| **Key-based** | Nhóm theo `tenantId`/`warehouseId` trước khi cắt | Không trộn các miền dữ liệu/quyền |
| **Offset/page-based** | Mỗi trang 500 record từ DB | Export/import lượng dữ liệu lớn |
| **Transactional** | Số item mỗi commit theo step | Spring Batch chunk-oriented processing |

Một chunk theo **bytes** không thể tính chỉ từ `List.size()`: payload mỗi item có kích thước khác nhau, cần đo kích thước sau serialize và tính overhead của headers/protocol. Một chunk theo **thời gian** có thể rỗng hoặc nhỏ hơn limit khi đến hạn.

**Không nhầm “chunk” với “partition” trong broker.** Partition thường là đơn vị phân phối/ordering của log/broker, còn chunk là đơn vị gom item cho một lần xử lý. Một partition có thể chứa vô số chunk qua thời gian; một chunk cũng có thể được gửi tới một partition theo key.

## 11. Splitter khác batching và Aggregator như thế nào?

Một nhầm lẫn phổ biến: **splitter** và **batching** đều nhắc tới nhiều item nên dễ bị coi là cùng một thao tác. Thực ra chúng có thể là hai hướng dữ liệu trái nhau:

~~~mermaid
flowchart LR
    B["Một message batch"] --> S["Splitter"]
    S --> M1["Message item 1"]
    S --> M2["Message item 2"]
    S --> MN["Message item N"]
    M1 --> A["Aggregator / batching"]
    M2 --> A
    MN --> A
    A --> R["Một message kết quả/nhóm"]
~~~

- **Splitter**: một message tổng hợp thành nhiều message.
- **Aggregator**: nhiều message thành một group/reply theo correlation + release strategy.
- **Batcher/chunker**: tạo nhóm dữ liệu có giới hạn để xử lý/ghi/gửi hiệu quả; có thể dùng Aggregator khi **gom message đang đến từ nhiều thời điểm**, hoặc dùng hàm partition khi **đã có List**.
- **Resequencer**: sắp xếp message theo sequence khi cần thứ tự; không đồng nghĩa với chunker.

Nếu nguồn đầu vào là **một message chứa 1.250 item**, chunker + Splitter hợp lý. Nếu nguồn đầu vào là **1.250 message độc lập đến qua broker**, cần cân nhắc **Aggregator với release theo count/time** để tạo các chunk; không cần dựng một message batch lớn rồi lại split chỉ để mô phỏng chunking.

Điểm phân biệt là **biên dữ liệu ban đầu**: dữ liệu đã ở trong một message tổng hợp hay đang đến thành dòng message rời.

## 12. Spring Batch chunk-oriented processing là một khái niệm khác

**Spring Batch** có mô hình **chunk-oriented processing**: đọc item qua `ItemReader`, biến đổi qua `ItemProcessor`, gom một số item rồi ghi qua `ItemWriter`, sau đó commit transaction theo cấu hình step.

~~~mermaid
flowchart LR
    R["ItemReader"] --> P["ItemProcessor"]
    P --> C["Chunk: tối đa 100 items"]
    C --> W["ItemWriter"]
    W --> COMMIT["Commit transaction"]
    COMMIT -.->|"Tiếp tục"| R
~~~

Ví dụ ý tưởng với Spring Batch phiên bản hỗ trợ `StepBuilder` và chunk transaction manager:

~~~java
@Bean
Step importLines(JobRepository jobRepository,
                 PlatformTransactionManager tx,
                 ItemReader<OrderLine> reader,
                 ItemProcessor<OrderLine, OrderLine> processor,
                 ItemWriter<OrderLine> writer) {
    return new StepBuilder("importLines", jobRepository)
        .<OrderLine, OrderLine>chunk(100, tx)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .build();
}
~~~

Đây là ví dụ **Spring Batch**, không phải cú pháp của `IntegrationFlow.split()`. JobRepository, transaction manager, reader, processor và writer cần được cấu hình đúng để chạy. Trong mô hình này, **chunk size thường gắn với commit interval của step**; retry, skip, restart/checkpoint của Spring Batch có chính sách riêng.

So sánh ngắn:

| Nhu cầu | Spring Integration Splitter | Spring Batch chunk step |
|---|---|---|
| Nhận message rồi phân phối nhiều handler/channel | Thích hợp | Không phải mục tiêu chính |
| Tách một payload List thành từng message | Thích hợp | Không mặc định |
| Bulk read-process-write theo transaction và restart | Phải tự thiết kế những phần này | Là use case trọng tâm |
| Workflow sự kiện bất đồng bộ, router và broker | Tự nhiên với Spring Integration | Có thể tích hợp, nhưng khác abstraction |
| Mỗi 100 item commit DB theo step | Không tự có | Cấu hình chunk-oriented step |

**Một Splitter phát 100 message không có nghĩa Spring Batch sẽ commit theo 100 message**. Ngược lại, Spring Batch xử lý một chunk 100 item không có nghĩa 100 message EIP đã được phát.

## 13. Correlation và sequence headers của Splitter

Trong Spring Integration, Splitter thường tạo metadata giúp các message con có thể được **ghép lại**. Những header quan trọng:

| Header | Ý nghĩa | Lưu ý |
|---|---|---|
| `correlationId` | Nhận diện nhóm các message có cùng nguồn/scope | Không dùng tùy tiện như business batch ID |
| `sequenceNumber` | Vị trí của message con trong sequence | Không khẳng định thời gian hoàn tất |
| `sequenceSize` | Tổng số phần tử dự kiến, **nếu biết được** | Iterator/stream có thể chưa biết số lượng |
| `MessageHeaders.ID` | ID của message cụ thể | Có thể khác khi reply/redelivery |
| `batchId` (custom) | Khóa nghiệp vụ ổn định cho lô | Dùng cho idempotency/trace |
| `chunkIndex` (custom) | Vị trí chunk trong batch | Dùng cho replay/checkpoint theo chunk |

`applySequence` là một tùy chọn liên quan việc gắn metadata sequence. Với collection có kích thước xác định, Splitter thường có đủ thông tin để xác định sequence size; với iterator/stream không biết trước độ dài, **không được giả định Aggregator sẽ nhận một sequence size dương và chính xác** trong mọi cấu hình/phiên bản.

**Đừng dùng sequenceNumber làm lineId nghiệp vụ.** Nếu producer thêm/xóa một item hoặc sắp xếp lại List khi retry, thứ tự có thể khác. Một `lineId` riêng giữ tính nhận diện ổn định qua các lần phát lại.

Ví dụ conceptual:

~~~text
Original: OrderBatch(batchId=B-101, lines=[L1,L2,L3])

Child 1: payload=L1, sequenceNumber=1, sequenceSize=3
Child 2: payload=L2, sequenceNumber=2, sequenceSize=3
Child 3: payload=L3, sequenceNumber=3, sequenceSize=3

Nhóm được liên kết bằng correlationId của cùng lượt split.
~~~

Ví dụ chỉ để hình dung metadata khi sequence đã được bật và số phần tử biết trước; **không hard-code** cách tạo correlation ID cụ thể cho mọi loại splitter.

## 14. Hai cấp split: chunk trước, item sau

Một pipeline có thể cần **chunk để phân phối**, rồi **split từng item để xử lý song song trong worker**:

~~~mermaid
flowchart TD
    O["Batch B-101: 1.250 lines"] --> C["Chunker: 13 chunks"]
    C --> S1{"Splitter cấp chunk"}
    S1 --> C0["Chunk 0: 100 lines"]
    S1 --> C1["Chunk 1: 100 lines"]
    S1 --> C12["Chunk 12: 50 lines"]
    C0 --> S2["Splitter cấp item"]
    C1 --> S2
    C12 --> S2
    S2 --> ITEM["Line work + handler"]
    ITEM --> G["Chunk-level result / batch-level result"]
~~~

Ở đây có **ít nhất hai quan hệ**:

1. `batchId` liên kết các chunk của một batch.
2. `chunkIndex` + `lineId` liên kết item với chunk để retry và gộp kết quả.

Nếu nested Splitter tiếp tục sinh `correlationId/sequenceNumber/sequenceSize`, các giá trị tiêu chuẩn có thể phản ánh **cấp split gần nhất** hoặc bị thay đổi theo cơ chế header handling. **Không dựa vào một bộ sequence headers duy nhất để biểu diễn cả hai cấp** nếu chưa kiểm thử topology cụ thể.

Khi cần hai tầng Aggregator, nên thiết kế contract:

~~~text
LineResult(batchId, chunkIndex, lineId, outcome)
      ↓
ChunkResult(batchId, chunkIndex, itemsProcessed, outcome)
      ↓
BatchResult(batchId, chunksProcessed, overallOutcome)
~~~

Các field này là **business correlation**; còn headers Spring Integration vẫn hữu ích cho các endpoint trong JVM. Đặc biệt khi message qua broker, payload IDs giúp khôi phục ý nghĩa nhóm nếu header mapper không bảo toàn toàn bộ sequence metadata.

## 15. Streaming, iterator và giới hạn bộ nhớ

Khi số item rất lớn, phương án `List<OrderLine> lines` ở trên có thể tiêu tốn nhiều bộ nhớ **trước cả khi Splitter bắt đầu**.

So sánh:

| Phương án | Bộ nhớ ở bên tạo message | Rủi ro |
|---|---|---|
| Materialize 1 triệu item thành List rồi split | Có thể rất lớn | OOM, GC pause |
| Đọc DB theo page 500 item và phát chunk | Giới hạn theo page/queue | Cần quản lý cursor, snapshot, retry |
| Iterator/stream được Splitter hỗ trợ | Có thể lazy trong điều kiện phù hợp | Nguồn bị đóng, không biết size, backpressure |
| Queue/broker bounded giữa producer và worker | Giới hạn in-flight | Rejection, timeout, redelivery |

**Iterable/Iterator/Stream không đồng nghĩa với streaming bền vững**. Một Iterator có thể giữ database cursor, file handle hoặc transaction đang mở; nếu consumer chậm, tài nguyên đó có thể sống lâu. Cần xác định ai đóng tài nguyên, lifetime của connection và cách resume sau lỗi.

Một mẫu an toàn hơn cho export lớn:

~~~text
DB page 1 (500 records)
    → validate → chunk/split → bounded channel → workers
DB page 2 (500 records)
    → chỉ đọc tiếp khi capacity cho phép
...
checkpoint = last committed page/key
~~~

Việc giới hạn page size không tự đảm bảo memory bound nếu producer liên tục tạo page mới mà queue bên trong không giới hạn. Cần giới hạn **cả nguồn đọc lẫn số message đang đợi**.

## 16. Throughput và backpressure: vì sao chunk size cần đo?

Đặt:

- `L`: số item cần xử lý.
- `K`: item tối đa/chunk.
- `H`: overhead cố định cho mỗi message/API call.
- `C`: chi phí xử lý trên mỗi item.

Một mô hình đơn giản, bỏ qua concurrency và các overhead khác:

\[
T(K) \approx
\left\lceil \frac{L}{K} \right\rceil H + L C
\]

Khi `K` lớn hơn, số lần trả overhead `H` giảm. Nhưng lợi ích này có thể bị triệt tiêu bởi **payload lớn, serialization, timeout, contention, một lỗi làm retry toàn chunk**, hoặc giới hạn API/broker.

**Ví dụ định tính:**

- Gửi 1.250 request đơn lẻ tới một bulk-friendly API có thể tốn nhiều round-trip.
- Gửi 13 request 100 item giảm số lần gọi, nhưng mỗi request lỗi có thể ảnh hưởng 100 item.
- Gửi một request 1.250 item có thể vượt giới hạn kích thước hoặc timeout, dù overhead nhỏ nhất.

**Backpressure** phải được thể hiện bằng bounded queue, rejection, tốc độ poll/receive hoặc cơ chế điều khiển đầu vào. Splitter có thể tạo message con nhanh hơn downstream xử lý, dù số lượng input message mỗi giây rất thấp.

Khi quyết định chunk size, đo latency p95/p99, payload bytes, queue depth, error rate, retry amplification, memory/GC và throughput **theo item**, không chỉ theo message.

## 17. Thứ tự xử lý: thứ tự split khác thứ tự hoàn tất

Với `List` có thứ tự, Splitter có thể phát message theo thứ tự phần tử. Nhưng sau khi qua executor/broker/consumer song song, **thứ tự hoàn tất không được bảo đảm**:

~~~text
Phát:        line-1 → line-2 → line-3
Hoàn tất:    line-2 → line-3 → line-1
~~~

Điều này cũng đúng với chunk:

~~~text
Phát:        chunk-0 → chunk-1 → chunk-2
Hoàn tất:    chunk-1 → chunk-0 → chunk-2
~~~

Nếu business yêu cầu cập nhật tuần tự một SKU hoặc account:

- Partition theo key thích hợp để cùng entity được xử lý trên một lane tuần tự.
- Gắn version/sequence nghiệp vụ để từ chối cập nhật cũ.
- Dùng Resequencer hoặc coordinator phù hợp nếu thật sự cần khôi phục thứ tự kết quả.
- Không dựa vào `sequenceNumber` của Splitter để bảo đảm transaction commit order.

**Chunk index không phải thứ tự commit.** Nếu chunk 4 đã thành công nhưng chunk 3 còn retry, checkpoint phải biết cách ghi nhận hole/partial completion thay vì chỉ lấy index lớn nhất rồi kết luận các chunk trước đã xong.

## 18. Lỗi một item và lỗi một chunk khác nhau ra sao?

Giả sử một chunk chứa 100 dòng, chỉ dòng thứ 37 có `sku` không tồn tại:

| Thiết kế | Phạm vi thất bại mặc định có thể gặp | Điều cần quyết định |
|---|---|---|
| Split mỗi item thành message | Một line bị lỗi; các line khác vẫn có thể chạy | Retry item, reject line, group completion |
| Chunk thành message chứa 100 item | Consumer bulk call có thể báo lỗi cả chunk | Retry toàn chunk hay tách lỗi từng item |
| Spring Batch chunk step với transaction | Rollback chunk theo transaction/policy của step | Retry/skip/rollback và commit interval |
| Split rồi Aggregator | Một message con không sinh result | Group timeout, partial release hoặc failure result |

**Không được coi việc “đã gửi chunk” là “100 item đều thành công”.** Một bulk service có thể trả kết quả hỗn hợp:

~~~json
{
  "batchId": "B-101",
  "chunkIndex": 2,
  "processed": 100,
  "succeeded": 98,
  "failed": [
    {"lineId": "L-237", "reasonCode": "UNKNOWN_SKU"},
    {"lineId": "L-286", "reasonCode": "OUT_OF_STOCK"}
  ]
}
~~~

Thiết kế cần chọn một trong các semantics:

1. **All-or-nothing chunk:** lỗi một item làm cả chunk thất bại và rollback nếu các side effect cùng transaction.
2. **Partial success:** worker trả result cho từng item; chỉ retry những item thất bại đủ điều kiện.
3. **Dead-letter/quarantine:** chuyển item hoặc chunk không thể xử lý tới luồng điều tra, có reason code.
4. **Compensation:** nếu đã có side effect không rollback được, phải có xử lý bù trừ thích hợp.

Không dùng retry vô hạn cho lỗi validation vĩnh viễn; cùng SKU sai sẽ tiếp tục thất bại, dù được chia thành chunk kích thước nào.

## 19. Retry, idempotency và rủi ro nhân đôi

Message broker thường hỗ trợ cơ chế **at-least-once** theo cấu hình; một message có thể được phát lại khi ack chưa hoàn tất. Splitter bản thân **không biến toàn bộ quá trình thành exactly-once**.

Một chunk đã ghi thành công 70/100 dòng rồi lỗi có thể được phát lại. Nếu worker xử lý lại cả chunk:

~~~text
Attempt 1: chunk-02 → 70 dòng đã có side effect, 30 chưa xong
Attempt 2: chunk-02 → đọc lại từ đầu
Nguy cơ: 70 dòng đầu bị ghi hoặc tính phí lần nữa
~~~

Khi thiết kế idempotency:

- Key theo batch/chunk giúp **nhận diện đơn vị công việc**, nhưng có thể không đủ khi bulk API hỗ trợ partial success.
- Key theo `(batchId, lineId, operation)` thường phù hợp hơn để bảo vệ side effect từng dòng.
- Nếu retry cả chunk, mỗi line handler phải biết đã xử lý thành công hay chưa.
- `MessageHeaders.ID` không nên là idempotency key duy nhất: message có thể được tạo lại khi redelivery.
- Khi dùng database + broker, cân nhắc transaction/outbox/inbox và trạng thái xử lý bền vững.

Đối với retry cùng batch sau khi **sửa nội dung**, cần phân biệt **batch revision/version**. Nếu cùng `batchId` nhưng danh sách item thay đổi, `chunkIndex=2` có thể chứa các item khác lần trước. Hãy xác định rõ semantics: batch bất biến, hoặc thêm `batchVersion`/manifest hash khi muốn replay được.

## 20. Aggregator ghép kết quả theo điều kiện nào?

Sau Splitter, Aggregator không chỉ cần một correlation key, mà còn cần biết **khi nào đủ kết quả để release**.

~~~mermaid
flowchart LR
    S["Splitter → N children"] --> W["Workers"]
    W --> RES["N results"]
    RES --> AG{"Aggregator"}
    AG --> OUT["BatchResult"]
~~~

Một phương án là dùng sequence metadata của splitter khi số phần tử được biết và **mỗi child tạo chính xác một result**. Nhưng thực tế có thêm tình huống:

- Một child bị Filter discard nên không sinh result.
- Một handler `void` chỉ làm side effect và không trả reply.
- Iterator/stream làm `sequenceSize` không biết trước.
- Một child retry sinh duplicate result.
- Một child trả failure result cần tính là **đã có kết luận**, nhưng batch outcome là FAILED/PARTIAL.
- Một child đến sau deadline hoặc sau khi group đã release.

Nếu cần hoàn thành chắc chắn, có thể lưu manifest từ đầu:

~~~text
BatchManifest(
    batchId=B-101,
    expectedChunkIds=[0,1,2,...,12],
    deadline=...,
    version=1
)
~~~

Aggregator/coordinator dùng manifest để đối chiếu **những chunk đã có kết quả**, không chỉ dựa vào message đến lần đầu. Với data volume cao, không nhất thiết giữ danh sách IDs đầy đủ trong RAM; có thể dùng persisted count/bitset/trạng thái theo khóa.

**Không tự gán `sequenceSize=13` vào mọi item ở cấp dưới** nếu item đã được tách từ từng chunk và cần một release strategy khác. Cần xác định **hai cấp group** và metadata riêng khi split lồng nhau.

## 21. Empty batch và `null`: không tự coi là hoàn thành

Nếu một `OrderBatch` có `lines=[]`:

- Chunker ở mục 8 trả một danh sách rỗng, nên không tạo chunk nào.
- Splitter trên collection rỗng có thể **không phát message con**, tùy endpoint và cấu hình.
- Gateway đang chờ một kết quả từ downstream có thể **không nhận reply**.
- Aggregator không nhận message nên không tự biết “batch có 0 item và đã hoàn tất”.

Nếu nghiệp vụ cho phép batch rỗng, hãy phát một kết quả terminal **riêng**, ví dụ `BatchResult(batchId, processed=0, status=EMPTY)` trước khi gọi Splitter. Nếu batch rỗng là vi phạm contract, từ chối ngay với reason code `EMPTY_BATCH`.

**`null` không phải collection rỗng**. `lines=null` có thể nghĩa là payload không hợp lệ hoặc deserializer chưa có dữ liệu. Đừng đổi null thành list rỗng rồi đánh dấu thành công nếu không có quy tắc được phê duyệt.

Với chunking theo thời gian, window không chứa event có thể bị bỏ qua hoặc phát tick/empty-window message tùy yêu cầu monitoring. Không mặc định hai semantics này tương đương.

## 22. Correlation và header propagation qua broker

Khi output của Splitter qua Kafka/AMQP/HTTP:

1. **Header mapper** quyết định những metadata Spring được chuyển thành native headers.
2. `correlationId`/sequence header có thể bị chuyển kiểu, đổi tên hoặc không được phát.
3. `replyChannel`/`errorChannel` có thể là object trong JVM; không tự serialize để dùng như remote address.
4. Consumer khác tiến trình không tự biết GroupStore/sequence status của tiến trình gốc.
5. Broker có ack, redelivery, partition/order và giới hạn payload riêng.

Một wire contract cho chunk nên có thông tin ứng dụng tường minh:

~~~json
{
  "batchId": "B-101",
  "batchVersion": 1,
  "chunkIndex": 2,
  "expectedChunks": 13,
  "lines": [
    {"lineId": "L-201", "sku": "SKU-01", "quantity": 1},
    {"lineId": "L-202", "sku": "SKU-02", "quantity": 2}
  ]
}
~~~

Đây là ví dụ rút gọn của một chunk; thông tin `expectedChunks` thuộc manifest batch đã được chốt, không lấy từ số message vừa nhận trong consumer. Nếu producer đổi chunk size trong lúc batch đang chạy mà không có version, các giá trị index/expected có thể mâu thuẫn. Thiết kế phải định nghĩa **batch bất biến hoặc revision**.

Đừng coi `message sent to broker` đồng nghĩa `business item committed`; cần metrics/status/ack tương ứng.

## 23. Unit test: chứng minh chunker không thiếu, không lặp item

Một unit test Java thuần cho `OrderChunker`:

~~~java
@Test
void partitions1250ItemsInto13ChunksWithoutLoss() {
    List<OrderLine> lines = IntStream.rangeClosed(1, 1_250)
        .mapToObj(i -> new OrderLine(
            "L-" + i, "SKU-" + i, 1))
        .toList();

    List<LineChunk> chunks = new OrderChunker()
        .partition(new OrderBatch("B-101", lines), 100);

    assertEquals(13, chunks.size());
    assertEquals(100, chunks.get(0).lines().size());
    assertEquals(50, chunks.get(12).lines().size());
    assertEquals(13, chunks.get(12).expectedChunks());
    assertEquals(12, chunks.get(12).chunkIndex());

    List<String> allIds = chunks.stream()
        .flatMap(chunk -> chunk.lines().stream())
        .map(OrderLine::lineId)
        .toList();

    assertEquals(1_250, allIds.size());
    assertEquals(1_250, new HashSet<>(allIds).size());
    assertEquals(lines.stream().map(OrderLine::lineId).toList(), allIds);
}

@Test
void rejectsZeroChunkSize() {
    OrderBatch batch = new OrderBatch(
        "B-102", List.of(new OrderLine("L-1", "SKU-A", 1)));

    assertThrows(IllegalArgumentException.class,
        () -> new OrderChunker().partition(batch, 0));
}

@Test
void treatsEmptyBatchExplicitly() {
    List<LineChunk> chunks = new OrderChunker()
        .partition(new OrderBatch("B-EMPTY", List.of()), 100);
    assertTrue(chunks.isEmpty());
}
~~~

Các test dùng JUnit 5 và Java Stream, lược bỏ import. Unit test xác nhận partition đúng kích thước, giữ thứ tự, không thiếu/trùng `lineId` trong input đã có ID duy nhất. Nó **chưa** chứng minh Spring Integration tạo đúng số message hoặc broker không phát lại.

Nên bổ sung property-based test với nhiều `N` và `K`: tổng số phần tử trong mọi chunk phải bằng `N`, mỗi chunk không rỗng khi `N > 0` và có kích thước **không vượt K**, index tăng liên tục từ 0.

## 24. Integration test: số message thực sự được Splitter phát

Trong Spring test context, thay `orders.chunks` bằng một `QueueChannel` test-only và gửi `OrderBatch` đến input của **ChunkedOrderFlow**; đừng chạy song song consumer production của cùng channel.

~~~java
@Autowired
ApplicationContext context;

@Test
void sendsOneMessagePerChunk() {
    MessageChannel input = context.getBean(
        "orders.batches", MessageChannel.class);
    PollableChannel output = context.getBean(
        "orders.chunks", PollableChannel.class);

    List<OrderLine> lines = IntStream.rangeClosed(1, 205)
        .mapToObj(i -> new OrderLine(
            "L-" + i, "SKU-" + i, 1))
        .toList();

    assertTrue(input.send(new GenericMessage<>(
        new OrderBatch("B-205", lines))));

    List<LineChunk> received = new ArrayList<>();
    for (int i = 0; i < 3; i++) {
        Message<?> message = output.receive(1_000);
        assertNotNull(message);
        received.add((LineChunk) message.getPayload());
    }

    assertNull(output.receive(0));
    assertEquals(List.of(100, 100, 5),
        received.stream().map(c -> c.lines().size()).toList());
    assertTrue(received.stream()
        .allMatch(c -> c.batchId().equals("B-205")));
}
~~~

Nếu luồng dùng dispatch bất đồng bộ, **thứ tự receive có thể khác thứ tự chunkIndex**; khi đó sort theo `chunkIndex` trước khi so kích thước, hoặc assert tập kết quả không phụ thuộc thứ tự. Ví dụ này giả định flow test chưa gắn executor/broker và request được gửi trực tiếp.

### Ma trận integration test tối thiểu

| Test | Đầu vào/cấu hình | Điều cần chứng minh |
|---|---|---|
| Split từng item | Batch 205 item | **205** message con kiểu `OrderLine` |
| Split theo chunk | Batch 205, K=100 | **3** message con kiểu `LineChunk` |
| Chunk cuối nhỏ | 205, K=100 | Chunk cuối có 5 item |
| Đúng biên | 200, K=100 | Đúng 2 chunk, không có chunk thứ ba rỗng |
| Empty batch | 0 item | Có terminal outcome hoặc rejection theo hợp đồng |
| K không hợp lệ | K=0 hoặc âm | Lỗi validation, không treo |
| Một item sai | One bad `sku` | Error/partial success theo policy |
| Một chunk lỗi | Bulk service timeout | Retry scope được xác minh, không double side effect |
| Parallel workers | Chunk 2 xong trước chunk 1 | Group vẫn kết luận đúng |
| Correlation | Split → process → Aggregator | Không ghép lẫn batch khác |
| Duplicate delivery | Phát lại chunk 2 | Idempotency theo batch/chunk/line |
| Restart khi còn pending | Broker + durable store | Recovery theo bảo đảm được thiết kế |
| Backpressure | Queue bounded và worker chậm | Reject/block có chủ đích, không OOM |
| Header mapping | Chunk qua transport ngoài JVM | Business ID/version còn nguyên |

## 25. Quan sát hiệu suất và tiến độ xử lý

Chỉ đếm message không đủ: **13 chunk message** và **1.250 item message** có thể đại diện cùng lượng công việc.

| Metric đề xuất | Phát hiện |
|---|---|
| `batch.received.count` | Số batch đầu vào |
| `batch.item.count` | Tổng item được yêu cầu xử lý |
| `split.child.message.count` | Số message con phát ra |
| `chunk.size.items` | Phân bố số item mỗi chunk |
| `chunk.size.bytes` | Kích thước sau serialize |
| `chunk.process.duration` | P50/P95/P99 theo chunk |
| `item.process.duration` | Độ trễ theo item |
| `chunk.retry.count` | Tải tăng do retry chunk |
| `item.failure.count` theo reason | Chất lượng dữ liệu nghiệp vụ |
| `queue.depth` và `queue.oldest.age` | Backlog và backpressure |
| `batch.pending.chunks` | Chunks còn thiếu kết quả |
| `batch.completed.count` theo outcome | Kết quả cuối: success/partial/failed |

Đây là **metric gợi ý**, không khẳng định có sẵn trong Spring Integration. Với Micrometer/observation, dùng tag có cardinality hữu hạn như `flow`, `operation`, `outcome`, `sizeBand`; không gắn `batchId` hoặc `lineId` làm metric tag.

Muốn truy vết một batch cụ thể, dùng structured logs/tracing với `batchId`, `batchVersion`, `chunkIndex`, `lineId` và correlation context phù hợp, đồng thời tránh ghi payload nhạy cảm. So sánh **item processed per second**, không chỉ `message sent per second` khi đo trước/sau chunking.

## 26. Bài thực hành: chọn đúng mức chia cho 1.250 dòng

Xây ứng dụng **OrderLineImport** với ba biến thể:

1. **Per-item Splitter:** nhận `OrderBatch` chứa 1.250 dòng, phát 1.250 `OrderLine` message tới `orders.lines`.
2. **Chunked Splitter:** dùng `OrderChunker.partition(batch,100)`, phát 13 `LineChunk` message tới `orders.chunks`.
3. **Chunk-oriented Spring Batch:** dùng một Job/Step đọc item và commit mỗi 100 item với transaction manager, không giả định các bước này tạo message con.
4. **So sánh tải:** đo elapsed time, queue depth, memory, p95 latency, số lần gọi bulk API và số lần retry.
5. **Lỗi có chủ đích:** cho dòng thứ 237 sai SKU; kiểm tra per-item reject, bulk partial success và chunk rollback.
6. **Retry:** phát lại chunk chứa dòng 237 và chứng minh không tạo side effect trùng ở 99 dòng còn lại.
7. **Correlation:** tạo `ChunkResult` và `BatchResult`, giữ `batchId` ổn định và xử lý khi một chunk không trả result.
8. **Empty batch:** quyết định fail hay phát `BatchResult(status=EMPTY)` trước bước split.
9. **Broker boundary:** thử gửi LineChunk qua Kafka/AMQP với header mapper chọn lọc, kiểm tra `batchVersion` và giới hạn payload.
10. **Điều chỉnh K:** thử 10, 100, 500 và so sánh lợi ích overhead với retry amplification, payload size, throughput.

**Tiêu chí hoàn thành:** giải thích được vì sao 1.250 message item khác 13 message chunk; chunk cuối không mất 50 item; dữ liệu không trùng khi retry; có lộ trình Aggregator/completion; đo được backpressure; biết khi nào chọn Spring Batch chunk step thay vì chỉ thêm Splitter.

## 27. Sai lầm thường gặp

**“Splitter và chunking là hai tên gọi cho cùng một pattern.”** Sai. Splitter là **message fan-out**; chunking là **giới hạn nhóm dữ liệu**, có thể dùng chung với Splitter.

**“Đặt K=100 thì Splitter sẽ tự commit mỗi 100 message.”** Sai. Transaction/commit interval thuộc hệ thống thực thi/transaction manager, không do số lượng message của Splitter tự quyết định.

**“13 chunk message có nghĩa chỉ xử lý 13 item.”** Sai. Mỗi chunk chứa nhiều item; phải đo cả message và item counts.

**“Chunk size càng lớn càng nhanh.”** Không luôn đúng. Lớn hơn có thể vượt payload limit, gây timeout, tăng memory và làm retry khuếch đại.

**“Một chunk thất bại thì mọi item trong chunk chưa có side effect.”** Sai khi các thao tác không nằm trong cùng transaction hoặc bulk API hỗ trợ partial success.

**“sequenceNumber là lineId bền vững.”** Sai. Sequence có thể thay đổi khi sort, retry hoặc split lồng nhau; cần business ID.

**“Một Splitter hỗ trợ Iterable nghĩa là tự có backpressure và recovery.”** Sai. Cần bounded pipeline, quản lý tài nguyên, checkpoint/durability.

**“Aggregator luôn biết bao giờ đủ message.”** Sai nếu unknown sequence size, mất child, Filter drop hoặc duplicate; cần release/timeout/failure policy.

**“Gửi batch rỗng qua Splitter rồi Gateway tự nhận result.”** Không mặc định. Cần một terminal outcome rõ ràng.

**“Dùng chung correlationId cho mọi cấp split.”** Có thể làm nhầm nhóm. Hãy thể hiện batch/chunk/line identity và kiểm thử headers từng cấp.

## 28. Ghi nhớ

**Splitter** trong Spring Integration biến **một message tổng hợp thành nhiều message con** và có thể cung cấp **sequence/correlation metadata** để phối hợp downstream. **Chunking** là việc **chia dữ liệu thành các nhóm có giới hạn** nhằm tối ưu I/O, bộ nhớ, throughput hoặc transaction. Bạn có thể **split mỗi item**, **chia chunk rồi split mỗi chunk**, hoặc **gom các message rời thành chunk bằng Aggregator/batcher**.

Chọn đơn vị xử lý dựa trên **yêu cầu độc lập của item, bulk capability, retry scope, idempotency, memory bound, transaction, ordering và completion semantics**. Nếu cần **chunk-oriented read-process-write với commit/restart**, cân nhắc Spring Batch; nếu cần **fan-out theo message, routing và phối hợp với Gateway/Filter/Transformer/Aggregator**, dùng Spring Integration và thiết kế correlation/error handling rõ ràng.

Khi phân biệt chính xác các lớp này, message flow sẽ dễ mở rộng hơn mà không nhầm **“chia nhỏ công việc”** với **“được xử lý thành công”**.

### Tài liệu tham khảo

- Spring Integration Reference, **Splitter**: https://docs.spring.io/spring-integration/reference/splitter.html
- Spring Integration Reference, **Aggregator**: https://docs.spring.io/spring-integration/reference/aggregator.html
- Spring Batch Reference, **Chunk-oriented Processing**: https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html
- Enterprise Integration Patterns, **Splitter**: https://www.enterpriseintegrationpatterns.com/patterns/messaging/Sequencer.html
