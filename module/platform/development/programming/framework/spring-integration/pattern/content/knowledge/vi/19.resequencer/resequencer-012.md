# So sánh resequencer với aggregator

## 1. Một bài toán, hai nhu cầu hoàn toàn khác nhau

Hệ thống nhận một đơn hàng có ba dòng sản phẩm. **Splitter** phát ba message con để các worker kiểm tra tồn kho và tính giá. Do một worker truy vấn dữ liệu chậm, kết quả về theo thứ tự **3 → 1 → 2** thay vì **1 → 2 → 3**.

Có hai yêu cầu nghiệp vụ:

- **Yêu cầu A:** chuyển **từng kết quả** cho consumer theo thứ tự dòng 1, 2, 3, để consumer xử lý tuần tự.
- **Yêu cầu B:** đợi đủ các kết quả, sau đó tạo **một OrderSummary** chứa tổng tiền và trạng thái đơn hàng.

**Resequencer** giải quyết yêu cầu A; **Aggregator** giải quyết yêu cầu B. Cả hai đều giữ trạng thái message group theo correlation và có cơ chế release, nhưng **hợp đồng đầu ra khác nhau**: Resequencer phát lại **nhiều message riêng rẽ theo thứ tự**, còn Aggregator tạo **một kết quả tổng hợp** từ những thành viên được gom.

~~~mermaid
flowchart TD
    IN["Nhận kết quả #3, #1, #2"] --> C{"Downstream cần gì?"}
    C -->|"Ba message theo thứ tự"| R["Resequencer"]
    C -->|"Một kết quả tổng"| A["Aggregator"]
    R --> M1["Message #1"]
    R --> M2["Message #2"]
    R --> M3["Message #3"]
    A --> S["OrderSummary"]
~~~

**Điểm cần ghi nhớ ngay:** một Resequencer có thể **đợi cho đủ toàn bộ sequence**, nhưng nó **không biến các message thành một List hoặc tính tổng**. Một Aggregator có thể chứa cả một group trong bộ nhớ, nhưng điều đó **không bảo đảm consumer nhận từng message theo thứ tự** vì Aggregator không có nhiệm vụ phát từng member ra ngoài.

Bài thuộc chương **Resequencer** của module **SPRING_INTEGRATION_PATTERN**. Đây là một phần của hành trình học triển khai **Enterprise Integration Patterns** với Spring Integration để tạo message flow ít phụ thuộc, dễ mở rộng, phối hợp **Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation**, đồng thời kiểm thử và quan sát nhánh xử lý.

Sau bài học, bạn có thể chọn đúng pattern, hiểu các header `CORRELATION_ID`/`SEQUENCE_NUMBER`/`SEQUENCE_SIZE`, cấu hình Java DSL `resequence()` và `aggregate()`, phân tích partial release, timeout, MessageGroupStore, duplicate, retry và kiểm thử cả thứ tự lẫn số lượng output.

## 2. Bảng so sánh Resequencer và Aggregator

| Tiêu chí | Resequencer | Aggregator |
|---|---|---|
| Mục đích | Khôi phục **thứ tự** các message cùng sequence | **Kết hợp** nội dung/kết quả của các message cùng group |
| Đầu vào | Nhiều message có correlation và sequence | Nhiều message có correlation và điều kiện hoàn tất |
| Đầu ra điển hình | **N message** theo thứ tự hợp lệ | **Một message** tổng hợp cho một lần release |
| Payload | Giữ nội dung message thành viên, không tự cộng/gộp | Mặc định thường là collection payloads; tùy biến bằng output processor |
| Hợp đồng ordering | Theo giá trị sequence number trong group | Nếu cần ordering trong summary thì phải tự quy định |
| Cơ chế nhóm | Correlation strategy và MessageGroupStore | Correlation strategy và MessageGroupStore |
| Cơ chế release | Đợi đủ hoặc phát prefix liên tục nếu cho phép partial | Release khi đủ điều kiện nghiệp vụ/sequence/group |
| Lỗi phổ biến | Gap #2 làm #3 chờ, sequence bị sai | Nhầm group, duplicate làm đủ count giả |
| Dùng với Gateway trả một reply | Thường chưa đủ | Phù hợp nếu tạo đúng một reply |
| Có phải deduplicator? | Không | Không |
| Có phải transaction manager? | Không | Không |

Spring Integration documentation mô tả trực tiếp: hai endpoint đều sử dụng group theo correlation, nhưng **Resequencer truyền messages đi theo `SEQUENCE_NUMBER` mà không biến đổi chúng**, còn Aggregator kết hợp messages.

Không nên diễn giải “Resequencer chỉ là Aggregator cộng thêm sort”: việc **đưa ra N message riêng** và **đưa ra một summary** có tác động hoàn toàn khác đến Gateway, backpressure, lỗi và side effects downstream.

## 3. Cùng ba input, output có cardinality khác nhau

Giả sử có:

~~~text
Group G-501, sequenceSize=3:

Arrival #1: M3, sequenceNumber=3, payload=LineResult(L3, 30)
Arrival #2: M1, sequenceNumber=1, payload=LineResult(L1, 10)
Arrival #3: M2, sequenceNumber=2, payload=LineResult(L2, 20)
~~~

**Resequencer** phát:

~~~text
Output 1: M1 = LineResult(L1, 10)
Output 2: M2 = LineResult(L2, 20)
Output 3: M3 = LineResult(L3, 30)

Tổng: 3 messages
~~~

**Aggregator** có thể phát:

~~~text
Output: OrderSummary(
    groupId=G-501,
    itemCount=3,
    totalAmount=60
)

Tổng: 1 message
~~~

Tổng tiền **60** là ví dụ về logic **do ứng dụng viết**, không phải giá trị Spring Integration tự tạo khi gọi `aggregate()`. Với Aggregator mặc định, output thường là một collection payloads; muốn `OrderSummary` với `totalAmount` và business status, cần một output processor hoặc Transformer thích hợp.

## 4. Correlation xác định nhóm; sequence xác định vị trí

Các header hay xuất hiện trong hai pattern:

| Header/field | Ý nghĩa | Có thay cho nhau được không? |
|---|---|---|
| `correlationId` | Những message nào thuộc **cùng group** | Có thể dùng correlation strategy riêng |
| `sequenceNumber` | **Vị trí** trong sequence, thường bắt đầu từ 1 | Không phải khóa nhóm |
| `sequenceSize` | Tổng phần tử dự kiến **nếu biết trước** | Không phải member identity |
| `MessageHeaders.ID` | ID của message Java/Spring cụ thể | Không nên làm logical batch ID xuyên retry |
| `batchId`/`processingId` | Một lần xử lý nghiệp vụ ổn định | Hữu ích cho broker/replay |
| `lineId` | Danh tính một thành viên | Hữu ích cho idempotency |

Ví dụ hai group chạy xen kẽ:

~~~text
Batch A: A1, A2, A3
Batch B: B1, B2, B3

Đến:   B2, A3, A1, B1, A2, B3

Đúng theo group:
  Batch A: A1, A2, A3
  Batch B: B1, B2, B3
~~~

Không có nghĩa mọi kết quả A **phải được phát trước** mọi kết quả B. Resequencer bảo đảm thứ tự theo **mỗi correlation group được cấu hình đúng**, không tự cấp **total ordering toàn hệ thống**.

Nếu chỉ dùng `sequenceNumber=1` làm correlation key, message A1 và B1 có thể bị gom chung. Nếu chỉ dùng `customerId` hoặc `tenantId` làm key, nhiều đơn hàng cùng customer/tenant có thể bị trộn. Cần group identity có phạm vi và bất biến qua các bước xử lý.

## 5. Resequencer khác một phép sort trong Java

`List.sort()` yêu cầu collection hiện hữu trong lời gọi hiện tại. Một Resequencer phải xử lý những tình huống khó hơn:

1. Các message đến **khác thời điểm** từ nhiều worker.
2. Nhiều group tồn tại đồng thời và cần được cô lập.
3. Một số sequence numbers có thể **chưa đến** hoặc đã mất.
4. Retry/broker redelivery có thể tạo **duplicate**.
5. MessageGroupStore cần timeout, expiry, cleanup và quan sát.
6. Correlation headers có thể bị thay đổi khi qua Transformer/transport.

Nó là một **correlating endpoint có state và output ordering policy**, không phải hàm sort thuần. Ngược lại, nếu dữ liệu đã là một `List` đầy đủ trong cùng method và chỉ cần sắp thứ tự để tính tổng, sử dụng Java Stream/sort có thể đơn giản hơn một endpoint Resequencer.

## 6. Luồng Resequencer: đợi rồi phát từng message

~~~mermaid
sequenceDiagram
    participant W as Workers
    participant R as Resequencer
    participant S as MessageGroupStore
    participant D as Downstream
    W->>R: M3, correlation=G, seq=3
    R->>S: Lưu #3, chờ
    W->>R: M1, correlation=G, seq=1
    R->>S: Lưu #1, chờ
    W->>R: M2, correlation=G, seq=2
    R->>S: Lưu #2, sequence đầy đủ
    R->>D: M1
    R->>D: M2
    R->>D: M3
~~~

Ở chế độ đợi đủ (thường mặc định `releasePartialSequences=false`), Resequencer giữ nhóm tới khi release strategy thỏa mãn rồi phát các message trong thứ tự sequence. Khi cho phép phát partial, có thể phát **prefix liên tục** sớm hơn, xem mục 13.

Reference Spring Integration nhấn mạnh Resequencer phù hợp **sequence tương đối ngắn, có ít gaps**. Một hệ thống với hàng chục nghìn group mà mỗi group thiếu nhiều vị trí có thể tốn đáng kể bộ nhớ/store và phải duy trì trạng thái chờ rất lâu.

## 7. Luồng Aggregator: đợi rồi tạo một kết quả

~~~mermaid
sequenceDiagram
    participant W as Workers
    participant A as Aggregator
    participant S as MessageGroupStore
    participant D as Downstream
    W->>A: M3, correlation=G, seq=3
    A->>S: Thêm L3
    W->>A: M1, correlation=G, seq=1
    A->>S: Thêm L1
    W->>A: M2, correlation=G, seq=2
    A->>S: Thêm L2
    Note over A: Group đủ theo release strategy
    A->>A: Output processor gộp dữ liệu
    A->>D: Một OrderSummary
~~~

Aggregator phải định nghĩa:

- **Correlation strategy:** message thuộc group nào?
- **Release strategy:** khi nào đủ thông tin để tạo kết quả?
- **Output processor:** kết quả được tính hoặc xây từ các message như thế nào?

Một Aggregator có thể có partial aggregation/release và expiry theo cấu hình; vì thế “mỗi group chỉ có đúng một output mãi mãi” là một giả định cần thiết kế và kiểm thử, **không phải bảo đảm exactly-once nghiệp vụ mặc nhiên**.

## 8. Java model: cùng dữ liệu nhưng hai output contract

Ví dụ dùng Java 17+:

~~~java
record LineResult(
    String batchId,
    String lineId,
    int position,
    long amountCents,
    boolean success
) {}

record BatchSummary(
    String batchId,
    int totalLines,
    long amountCents,
    int succeeded,
    int failed
) {}
~~~

- `batchId`: logical work identity; không tự đổi khi redelivery.
- `lineId`: identity của member, phục vụ deduplication.
- `position`: business sequence number, bắt đầu từ 1 trong ví dụ.
- `amountCents`: minh họa tiền theo đơn vị nhỏ; production cần currency/scale/overflow policy.
- `success`: outcome thất bại có cấu trúc vẫn có thể được tính là member **đã kết luận**, không phải message bị mất.

Nếu cần replay deterministic, phân biệt `batchId` với `revision`, `operation`, `tenantId` và `attemptId`. Không dùng một ID mới sinh tại mỗi worker làm group key nếu muốn nhiều worker vào cùng nhóm.

## 9. Java DSL: Splitter → Executor → Resequencer

Spring Integration Java DSL hỗ trợ `.resequence()`:

~~~java
@Configuration
@EnableIntegration
class ResequencerFlow {

    @Bean
    IntegrationFlow orderedLines(TaskExecutor lineExecutor) {
        return IntegrationFlow.from("lines.input")
            .split()
            .channel(MessageChannels.executor(lineExecutor))
            .resequence()
            .channel("lines.ordered")
            .get();
    }
}
~~~

Đây là một mẫu theo tài liệu chính thức **Aggregators and Resequencers**. Đầu vào `lines.input` là message mang collection/List; `split()` phát message con. Executor có thể làm các message đến Resequencer đảo thứ tự. Resequencer dùng sequence headers để phát lại từng message vào `lines.ordered` theo thứ tự phù hợp.

Để chạy trong ứng dụng:

1. Có bean `TaskExecutor` phù hợp, ưu tiên bounded executor.
2. Có consumer thật cho `lines.ordered` hoặc test `QueueChannel`.
3. Splitter phải cung cấp correlation/sequence metadata hợp lệ.
4. Có chính sách timeout/store nếu một child thất lạc.

**Đừng hiểu Resequencer biến output thành List.** Consumer `lines.ordered` sẽ nhận **nhiều message**, dù Resequencer đã tạm giữ cả group trước khi phát.

## 10. Java DSL: Splitter → Executor → Aggregator

Nếu downstream chỉ cần một collection kết quả, thay Resequencer bằng Aggregator:

~~~java
@Configuration
@EnableIntegration
class AggregationFlow {

    @Bean
    IntegrationFlow collectedLines(TaskExecutor lineExecutor) {
        return IntegrationFlow.from("lines.input")
            .split()
            .channel(MessageChannels.executor(lineExecutor))
            .aggregate()
            .channel("lines.collected")
            .get();
    }
}
~~~

Đây là **phương án thay thế** cho flow mục 9, không đăng ký cả hai cùng tiêu thụ `lines.input` nếu không có chủ đích về competing consumers. Aggregator mặc định thường tạo một message chứa **collection payloads**, không tự tạo `BatchSummary(amountCents=...)`.

Khi cần tính tổng, một bước tiếp theo có thể chuyển collection thành domain result, hoặc cấu hình output processor của Aggregator. Nếu thứ tự bên trong collection là quan trọng, cần dùng sort theo `position` hoặc quy tắc release/processor phù hợp; **đừng xem arrival order trên executor là business order**.

## 11. Nếu cần cả thứ tự và tổng hợp thì sao?

Có thể đặt Resequencer trước Aggregator:

~~~java
@Bean
IntegrationFlow orderedThenAggregated(TaskExecutor lineExecutor) {
    return IntegrationFlow.from("lines.input")
        .split()
        .channel(MessageChannels.executor(lineExecutor))
        .resequence()
        .aggregate()
        .channel("lines.summary.input")
        .get();
}
~~~

~~~mermaid
flowchart LR
    IN["List line items"] --> SPLIT["Splitter"]
    SPLIT --> WORK["Concurrent workers"]
    WORK --> RS["Resequencer: N ordered messages"]
    RS --> AG["Aggregator: one grouped output"]
    AG --> OUT["Batch summary"]
~~~

Đây là topology hợp lệ khi **một bước sau Resequencer cần xử lý từng message đúng thứ tự** và cuối cùng vẫn cần kết quả tổng hợp. Nhưng nếu chỉ cần **một summary đã sắp theo position**, Aggregator + sort trong output processor có thể đơn giản, ít state và ít latency hơn.

**Rất quan trọng:** đặt Resequencer **sau** các worker không thể đảo lại thứ tự các side effect đã commit **trước** nó. Nếu worker #3 đã ghi DB trước worker #1, output 1→2→3 không xóa được lịch sử commit 3→1→2.

## 12. Bảng quyết định: pattern nào phù hợp?

| Nhu cầu | Nên dùng | Vì sao |
|---|---|---|
| Gửi từng event đến writer theo đúng thứ tự | Resequencer trước writer | Giữ message riêng, sắp thứ tự phát |
| Tính tổng tiền của N dòng | Aggregator | Cần một payload kết quả |
| Trả JSON gồm các dòng đã sort | Aggregator + sort ở processor | Không cần phát lại N messages |
| Phát các audit events tuần tự | Resequencer | Downstream đọc từng event |
| Gateway cần một phản hồi | Aggregator/Gather | Hợp đồng một reply |
| Một List đã đầy đủ trong một Java method | Java sort/collect | Không cần message group store |
| Kafka có ordering per-key phù hợp, xử lý tuần tự | Partition/consumer policy | Không nhất thiết cần Resequencer |
| Xử lý song song rồi in báo cáo theo order | Resequencer → print hoặc Aggregator + sort | Tùy output là dòng hay cả báo cáo |

**Quy tắc:** chọn theo **hợp đồng của downstream**, không chỉ vì message đến sai thứ tự. Nếu consumer cần một object tổng, sorting là chi tiết của aggregation; nếu consumer thực sự phải thấy từng event theo sequence, đó là chức năng của Resequencer.

## 13. Release partial sequences: đợi đủ hay phát prefix sớm?

Resequencer có tùy chọn `releasePartialSequences`, mặc định là `false` theo reference Spring Integration.

Giả sử sequence có 4 message, đến theo thứ tự 3,1,4,2:

| Thời điểm | Message tới | `false`: đợi đủ | `true`: cho phát prefix liên tục |
|---|---|---|---|
| T1 | #3 | Chờ | Chờ vì chưa có #1 |
| T2 | #1 | Chờ | Có thể phát **#1** |
| T3 | #4 | Chờ | Chờ vì còn thiếu #2 |
| T4 | #2 | Phát **#1,#2,#3,#4** | Phát tiếp **#2,#3,#4** |

Java DSL:

~~~java
@Bean
IntegrationFlow partialSequenceFlow() {
    return IntegrationFlow.from("parts.in")
        .resequence(r -> r.releasePartialSequences(true))
        .channel("parts.ordered")
        .get();
}
~~~

Ví dụ minh họa tính chất **prefix liên tục**, không phải cam kết Resequencer được phép bỏ qua gap rồi phát #3 khi #1/#2 chưa có. Hành vi cụ thể có thể thay đổi theo release strategy tùy biến, expiry và phiên bản; nên integration test theo topology thật.

**Partial release không đồng nghĩa kết quả nghiệp vụ đã đầy đủ**. Consumer phải biết những message đã phát chỉ là một prefix của sequence, nếu cần kết luận cuối phải có completion signal hoặc sequence size/manifest phù hợp.

## 14. Aggregator cũng có release strategy nhưng ý nghĩa khác

Ví dụ một release strategy đơn giản:

~~~java
.aggregate(a -> a
    .releaseStrategy(group -> group.size() == 3))
~~~

Với group có #3,#1,#2, nó có thể release khi đủ ba message và tạo **một aggregate output**, chứ không phát từng message 1,2,3.

Hơn nữa, `group.size()==3` có thể sai trong thực tế khi broker redelivery tạo:

~~~text
Group G:
  L1: attempt 1
  L1: duplicate
  L2: attempt 1

group.size()==3 nhưng còn thiếu L3!
~~~

Vì vậy production cần kiểm tra **member IDs duy nhất và membership manifest**, không chỉ đếm message. Resequencer cũng phải có duplicate/gap policy, nhưng nhiệm vụ release của nó tập trung vào **ordering**, còn Aggregator tập trung vào **business completion và cách gộp**.

## 15. Vai trò của Splitter đối với sequence metadata

Splitter thường cấp sequence headers cho các child khi nguồn có kích thước xác định:

~~~text
Original: OrderBatch(batchId=B-501, lines=[L1,L2,L3])

After Splitter (minh họa khi applySequence):
  L1: correlationId=G, sequenceNumber=1, sequenceSize=3
  L2: correlationId=G, sequenceNumber=2, sequenceSize=3
  L3: correlationId=G, sequenceNumber=3, sequenceSize=3
~~~

Điều này giúp Resequencer và Aggregator nhận ra cùng group. Tuy nhiên không nên giả định một Iterator/Stream không biết trước kích thước luôn có `sequenceSize=3`, hoặc Transformer tự dựng `Message<?>` mới sẽ giữ toàn bộ metadata.

Nếu có nested split, ví dụ Batch → Chunk → Item, sẽ có **hai cấp sequence logic**. Đừng dùng duy nhất một cặp header `correlationId/sequenceNumber` để biểu diễn cả chunk sequence và item sequence nếu endpoint cấp sau đã thay metadata. Dùng business IDs/manifest rõ ràng ở từng cấp.

## 16. Correlation key sai phá cả hai pattern

Giả sử:

~~~text
Batch A: seq1, seq2, seq3
Batch B: seq1, seq2, seq3

Sai: correlationKey = tenantId
Kết quả có thể bị xếp chung:
  A1, B1, A2, B2, B3, A3
~~~

Resequencer không thể tạo một sequence chuẩn 1→3 nếu mỗi vị trí có hai message thuộc hai batch khác nhau. Aggregator có thể trộn sáu kết quả hoặc release sai tại ba message đầu tiên.

Một key có phạm vi phù hợp:

~~~text
groupKey = tenantId + processingGroupId + revision
~~~

Quy tắc:

- Cấp `processingGroupId` một lần trước Splitter.
- Giữ nguyên cho mọi child và result của cùng logical work.
- Không sinh `UUID.randomUUID()` trong từng worker hoặc correlation strategy.
- Phân biệt tenant/revision/operation khi những phạm vi đó có thể trùng business ID.
- Xác thực tenant tại trust boundary, không tin raw header do client tự cấp.
- Với MessageGroupStore bền vững, giữ thuật toán key ổn định qua retry và deploy, hoặc có migration rõ.

Resequencer **không phải công cụ sửa correlation**. Một nhóm đã trộn dữ liệu không trở nên đúng chỉ vì được sắp theo sequence number.

## 17. Java: tạo message test có correlation và sequence

Một test fixture Java dùng trực tiếp headers Spring Integration:

~~~java
Message<LineResult> resultMessage(
        String groupId, int position, int size) {
    LineResult result = new LineResult(
        "B-501",
        "L-" + position,
        position,
        position * 10L,
        true);

    return MessageBuilder.withPayload(result)
        .setHeader(
            IntegrationMessageHeaderAccessor.CORRELATION_ID,
            groupId)
        .setHeader(
            IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER,
            position)
        .setHeader(
            IntegrationMessageHeaderAccessor.SEQUENCE_SIZE,
            size)
        .build();
}
~~~

Đây là một **test fixture**, lược bỏ imports. Cùng logical batch phải có **cùng correlation ID**, sequence numbers hợp lệ và sequenceSize thống nhất nếu biết trước. Khi broker redeliver, Spring message ID có thể khác nhưng logical group key **không tự đổi**.

**Không dùng `MessageHeaders.ID` thay group key** nếu mục tiêu là gom lại các kết quả của cùng logical work xuyên retry/rebuild.

## 18. Filter drop một child: Resequencer và Aggregator phản ứng khác

Giả sử Splitter phát #1,#2,#3 nhưng Filter loại #2:

~~~mermaid
flowchart LR
    S["Splitter #1,#2,#3"] --> F{"Filter"}
    F -->|"#1"| R["Resequencer / Aggregator"]
    F -->|"#2 rejected"| E["Error / reject flow"]
    F -->|"#3"| R
~~~

Với **Resequencer**, nếu cần giữ ordering đầy đủ, #3 không thể được phát sau #1 khi #2 chưa tới theo policy bình thường; partial release có thể phát #1 nhưng #3 vẫn bị chặn bởi gap.

Với **Aggregator**, group có hai kết quả trên ba member dự kiến. Nếu release đòi đủ ba outcomes, group chờ cho đến deadline hoặc một recovery event.

Giải pháp:

1. Fail toàn batch trước Splitter nếu một item sai là điều kiện hủy tất cả.
2. Đưa **failure outcome** cho #2 vào cùng sequence để group có một kết quả rõ.
3. Thiết kế group timeout/partial-result policy có trạng thái `FAILED/PARTIAL`.
4. Nếu business cho skip, định nghĩa cách xử lý missing position/manifest; không âm thầm giảm sequenceSize ở message còn lại.

**Không dùng `return null` của Transformer như placeholder**: output null không phải một result message hợp lệ cho Resequencer/Aggregator và có thể tạo transformation exception.

## 19. Failure result khác với exception không sinh reply

Định nghĩa outcome có cấu trúc:

~~~java
record LineOutcome(
    String batchId,
    String lineId,
    int position,
    boolean success,
    String reasonCode
) {}
~~~

Một sequence:

~~~text
LineOutcome(L1, seq=1, success=true)
LineOutcome(L2, seq=2, success=false, INVALID_SKU)
LineOutcome(L3, seq=3, success=true)
~~~

Resequencer phát **ba outcomes theo thứ tự**, để consumer chọn tiếp tục hay dừng tại #2. Aggregator có thể tạo **BatchSummary(status=PARTIAL, failed=1)** khi cả ba đã có kết luận.

Ngược lại, nếu worker ném exception mà không phát `LineOutcome`, group có thể **thiếu member mãi**. Error channel/caller sẽ thấy lỗi theo cấu hình, nhưng Aggregator không tự nhận một reply từ error channel trừ khi đã nối một error-to-outcome flow mang đúng correlation.

## 20. Timeout và expiry: mất sequence vs thiếu group member

| Tình huống | Resequencer | Aggregator |
|---|---|---|
| Thiếu #2, có #1 và #3 | #3 bị chặn bởi gap nếu phải giữ thứ tự | Group thiếu thành viên |
| Hết deadline | Có thể expire, discard hoặc phát partial theo policy | Có thể fail, expire hoặc tạo partial summary |
| Reply sau expiry | Có thể bị loại hoặc tạo group mới tùy lifecycle | Có thể tạo group mới/duplicate output tùy lifecycle |
| Group quá lớn | Nhiều buffered messages | Nhiều payloads/chưa tính tổng |
| Cần audit | Missing sequence positions | Missing business member IDs |

Spring Integration có các cấu hình như `groupTimeout`, `sendPartialResultOnExpiry`, `expireGroupsUponCompletion`, `discardChannel` và `MessageGroupStore`. Phải kiểm tra chính xác semantics theo phiên bản/endpoint thực tế. **Timeout không tự tạo một message bị mất** và không bắt buộc mọi remote worker dừng ngay.

Với Resequencer, **phát partial khi expiry** có thể khác với hành vi phát một prefix liên tục bình thường; một sequence không hoàn chỉnh cần status/diagnostics để downstream không coi đó là “đã đủ N”.

## 21. MessageGroupStore: cả hai đều stateful

Không phải Resequencer là stateless chỉ vì nó không đổi payload:

| Vấn đề | In-memory store | Persistent/shared store |
|---|---|---|
| Restart | Pending groups có thể mất | Có thể phục hồi nếu cấu hình đúng |
| Nhóm thiếu member | Giữ trong RAM, có thể phình | Giữ trong backend, cần cleanup |
| Multi-node | Không chia sẻ tự nhiên | Cần locking/transaction đúng |
| Late reply | Cần expiry/completion policy | Vẫn cần expiry/completion policy |
| Duplicate/dedupe | Không tự giải quyết | Không tự giải quyết |
| Group ID collision | Gom sai ngay trong RAM | Có thể gom sai dai dẳng qua restart |

Resequencer giữ các message chờ phát theo sequence; Aggregator giữ các message hoặc group state để tạo kết quả. Cả hai cần giới hạn pending groups, timeout, retention và theo dõi memory/store.

**Persistent storage không sửa được correlation strategy sai, sequence gaps hay business idempotency.** Trong distributed deployment, dùng shared store nhưng không có khóa/trạng thái atomic phù hợp vẫn có rủi ro double release.

## 22. Duplicate và sequence conflict

Một group nhận:

~~~text
G-501:
  seq1 → L1, attempt 1
  seq1 → L1, duplicate attempt 1
  seq2 → L2
  seq3 → L3
~~~

Resequencer **không phải endpoint deduplication**; Aggregator cũng **không tự áp business-level dedupe** chỉ vì có group. Cần có idempotency ở nơi thích hợp.

Ví dụ khóa:

~~~text
memberKey = (tenantId, batchId, revision, lineId, operation)

Nếu đã có result cuối cùng giống hệt → duplicate: ignore/ack
Nếu đã có result mâu thuẫn        → conflict: quarantine/reconcile
Nếu chưa có                      → validate rồi accept
~~~

Kiểm tra phải xét atomic persistence ở nơi tạo side effect; chỉ so Spring message ID không đủ khi broker tạo lại message. Cần quyết định chuyện gì xảy ra khi hai result có **cùng sequenceNumber nhưng khác lineId**, hoặc một lineId được gán hai positions.

Nếu output của Aggregator cần **đúng member set**, release strategy phải so với manifest, không chỉ `group.size()==expected`.

## 23. Sắp thứ tự message không sắp lại được side effects đã commit

Giả sử worker #3 ghi DB trước #1 và #2:

~~~text
Worker #3 → DB COMMIT
Worker #1 → DB COMMIT
Worker #2 → DB COMMIT
           ↓
      Resequencer
Output:    #1, #2, #3
~~~

Output được sắp đúng, nhưng **DB đã commit theo 3,1,2**. Muốn bảo đảm business transaction theo thứ tự thì:

- Đặt Resequencer **trước** handler/side effect nhạy thứ tự.
- Đảm bảo channel và consumer **sau Resequencer** không tự làm mất thứ tự.
- Hoặc partition/order theo business key, xử lý trên một lane tuần tự.
- Dùng version/fencing/idempotency để không cho cập nhật cũ ghi đè cập nhật mới.

Nếu đặt `ExecutorChannel` multi-thread **sau** Resequencer, các task vẫn có thể hoàn tất sai thứ tự. Phải nêu rõ **ranh giới mà ordering contract có hiệu lực**, không coi ordering như thuộc tính bất biến của mọi downstream handler.

## 24. Broker partition ordering và Resequencer

Kafka thường bảo toàn ordering **trong một partition** theo log, nhưng không cung cấp total order xuyên mọi partition. Khi producer chọn partition key theo entity và consumer xử lý tuần tự, bạn có thể **không cần Resequencer**.

Resequencer có ích khi:

- Branch results bị đảo thứ tự sau xử lý song song.
- Message từ nhiều đường vận chuyển cùng một logical sequence đến lệch nhau.
- Consumer tiếp theo cần đúng thứ tự theo business sequence đã được công bố.

Nhưng nếu luồng là một stream vô hạn và thiếu sequence liên tục kéo dài, không nên dùng một MessageGroupStore vô hạn để cố “lấp” mọi gap. Reference Spring Integration khuyến nghị **short sequences with small gaps**. Xem partitioning, offset/checkpoint, window/epoch hoặc stream processing có chính sách state rõ ràng.

## 25. Gateway muốn một reply: Aggregator phù hợp hơn

Một Gateway điển hình:

~~~java
@MessagingGateway(defaultRequestChannel = "order.request")
interface OrderGateway {
    BatchSummary submit(List<LineResult> lines);
}
~~~

Nếu flow chỉ là **Splitter → Resequencer**, nó phát **nhiều message**, chưa tạo một `BatchSummary`. Gateway thông thường mong một reply, nên việc thiếu một bước gộp có thể gây timeout hoặc trả một payload không đúng contract, tùy topology.

Muốn trả một summary:

~~~text
Gateway request
   → Splitter
   → Branch handlers
   → Aggregator
   → (Transformer thành BatchSummary nếu cần)
   → một Gateway reply
~~~

Nếu consumer thực sự muốn từng event theo thứ tự, dùng channel hoặc streaming API phù hợp, không giả định một phương thức synchronous request–reply sẽ biến N outputs của Resequencer thành collection.

Khi dùng `Gateway → Resequencer → Aggregator`, phải đảm bảo reply/error headers và correlation đi đủ qua các endpoint; nếu một child bị Filter drop, Gateway có thể chờ tới timeout.

## 26. Java DSL hoặc XML, không có `@Resequencer` annotation

Spring Integration hỗ trợ Resequencer qua Java DSL `resequence()` hoặc XML:

~~~xml
<int:channel id="parts.in"/>
<int:channel id="parts.ordered"/>

<int:resequencer
    input-channel="parts.in"
    output-channel="parts.ordered"
    release-partial-sequences="false"/>
~~~

Ví dụ XML cần Spring integration namespace/context và consumer thật cho output channel. Tài liệu chính thức nêu **không có annotation support chuyên biệt cho Resequencer**: endpoint không cần custom POJO method để xử lý/gộp payload.

Không tự viết `@Resequencer` rồi giả định đó là annotation có sẵn tương tự `@Aggregator`. Muốn nghiệp vụ xử lý từng message, đặt một Service Activator hoặc Transformer **sau** Resequencer.

## 27. Capacity và backpressure của hai endpoint

Một group có 1.000 message; #1 tới rất muộn còn #2–#1000 đã nhận. Resequencer có thể giữ nhiều message trước khi đủ prefix để phát. Nếu có hàng nghìn group như vậy, buffer/store tăng mạnh.

| Giới hạn nên thiết kế | Resequencer | Aggregator |
|---|---|---|
| Max group/sequence size | Bảo vệ buffer trước các gaps dài | Bảo vệ memory của aggregate |
| Max pending groups | Tránh nhiều sequence chờ | Tránh nhiều batch chờ |
| Deadline/group timeout | Không chờ thiếu số mãi | Không chờ member bị mất mãi |
| Bounded ingress queue | Hạn chế tốc độ nhận | Hạn chế tốc độ nhận |
| Per-tenant quota | Tránh một tenant chiếm store | Tránh một tenant chiếm store |
| Retry budget | Tránh retry storm khi thiếu sequence | Tránh duplicate/failure amplification |
| Cleanup/tombstone | Xử lý late messages | Tránh double aggregation |

`releasePartialSequences(true)` có thể giảm buffer khi prefix đã liên tục, nhưng **không giúp** nếu thiếu #1 lâu dài. Tăng heap không thay giải pháp timeout/expiry/ownership cho các group không bao giờ hoàn tất.

Aggregator có thể dùng output processor tích lũy dữ liệu thay vì giữ toàn bộ payloads tùy bài toán, nhưng phải kiểm tra transaction/restart và tính đúng của kết quả. Không nên dùng một Aggregator với group vô hạn nếu nghiệp vụ không có điều kiện release hoặc window rõ ràng.

## 28. Integration test: Resequencer nhận 3,1,2 và phát 1,2,3

Một Spring test context riêng:

~~~java
@Configuration
@EnableIntegration
class ResequencerTestConfig {
    @Bean
    IntegrationFlow resequenceOnly() {
        return IntegrationFlow.from("test.resequence.in")
            .resequence()
            .channel("test.resequence.out")
            .get();
    }

    @Bean("test.resequence.out")
    PollableChannel resequencedOutput() {
        return new QueueChannel();
    }
}
~~~

Test dùng fixture `resultMessage()`:

~~~java
@Autowired
ApplicationContext context;

@Test
void emitsThreeMessagesInSequenceOrder() {
    MessageChannel input = context.getBean(
        "test.resequence.in", MessageChannel.class);
    PollableChannel output = context.getBean(
        "test.resequence.out", PollableChannel.class);

    assertTrue(input.send(resultMessage("G-501", 3, 3)));
    assertTrue(input.send(resultMessage("G-501", 1, 3)));
    assertNull(output.receive(0));  // Chưa đủ sequence

    assertTrue(input.send(resultMessage("G-501", 2, 3)));
    for (int expected = 1; expected <= 3; expected++) {
        Message<?> actual = output.receive(1_000);
        assertNotNull(actual);
        LineResult part = (LineResult) actual.getPayload();
        assertEquals(expected, part.position());
        assertEquals("G-501",
            actual.getHeaders().get(
                IntegrationMessageHeaderAccessor.CORRELATION_ID));
    }
    assertNull(output.receive(0));
}
~~~

Đây là các đoạn test minh họa, lược bỏ import và phần test runner. Khi dùng DirectChannel trước Resequencer và QueueChannel ở output, có thể kiểm chứng thứ tự bằng receive. Nếu app thật có executor sau Resequencer, phải kiểm tra **consumer thực** thay vì chỉ queue trong test.

## 29. Integration test: Aggregator tạo một collection

Một test context **khác**:

~~~java
@Configuration
@EnableIntegration
class AggregatorTestConfig {
    @Bean
    IntegrationFlow aggregateOnly() {
        return IntegrationFlow.from("test.aggregate.in")
            .aggregate()
            .channel("test.aggregate.out")
            .get();
    }

    @Bean("test.aggregate.out")
    PollableChannel aggregatedOutput() {
        return new QueueChannel();
    }
}
~~~

Test:

~~~java
@Autowired
ApplicationContext context;

@Test
void emitsOneCollectionWhenGroupComplete() {
    MessageChannel input = context.getBean(
        "test.aggregate.in", MessageChannel.class);
    PollableChannel output = context.getBean(
        "test.aggregate.out", PollableChannel.class);

    input.send(resultMessage("G-502", 3, 3));
    input.send(resultMessage("G-502", 1, 3));
    assertNull(output.receive(0));

    input.send(resultMessage("G-502", 2, 3));
    Message<?> result = output.receive(1_000);
    assertNotNull(result);
    assertInstanceOf(Collection.class, result.getPayload());
    assertEquals(3, ((Collection<?>) result.getPayload()).size());
    assertNull(output.receive(0));
}
~~~

Test chứng minh **cardinality và payload shape**, không chứng minh tổng tiền hoặc nội dung đúng member. Bổ sung test custom aggregation processor với `batchId, member IDs, amounts, failures`, đặc biệt khi có duplicate.

## 30. Test partial release, missing message và concurrency

Với Resequencer bật partial:

~~~text
Input: #3, #1, #4, #2 (sequenceSize=4)

Đường mong đợi của prefix:
  sau #3 → chưa có output
  sau #1 → output #1
  sau #4 → chưa phát #4
  sau #2 → output #2, #3, #4
~~~

Một ma trận test đầy đủ:

| Case | Resequencer cần chứng minh | Aggregator cần chứng minh |
|---|---|---|
| Out of order | Phát theo sequence | Gộp đúng member |
| Missing #2 | #3 không vượt gap nếu không có skip policy | Không báo thành công đủ |
| Duplicate #1 | Không tạo side effect trùng theo business policy | Không đếm duplicate là member mới |
| Two groups interleaved | Không trộn nhóm | Không tạo summary chéo |
| SequenceSize không nhất quán | Error/expiry policy rõ | Không release sai |
| Timeout | Partial/discard/expiry có contract | Partial/fail result có contract |
| Late reply | Không tự tạo sequence hoàn tất lần hai | Không tự publish summary thứ hai |
| Retry new MessageHeaders.ID | Business group key vẫn giữ | Idempotency vẫn đúng |
| Parallel workers | Output boundary có ordering | Summary không phụ thuộc arrival order |

Dùng `CountDownLatch`/barrier và timeout hữu hạn để điều khiển thứ tự, không dựa vào `Thread.sleep` ngẫu nhiên. Với broker, phải test header mapper, ack/redelivery, durable store và thứ tự ở từng consumer lane.

## 31. Khi cần một summary đã sort: không phải lúc nào cũng cần Resequencer

Nếu mục tiêu chỉ là một output chứa các dòng đúng thứ tự, có thể sort trong processor sau Aggregator:

~~~java
record OrderedBatch(
    String batchId,
    List<LineResult> orderedLines,
    long totalAmountCents
) {}

OrderedBatch summarize(Collection<LineResult> results) {
    if (results.isEmpty()) {
        throw new IllegalArgumentException("EMPTY_GROUP");
    }
    List<LineResult> ordered = results.stream()
        .sorted(Comparator.comparingInt(LineResult::position))
        .toList();

    long total = ordered.stream()
        .mapToLong(LineResult::amountCents)
        .reduce(0L, Math::addExact);

    return new OrderedBatch(
        ordered.get(0).batchId(), ordered, total);
}
~~~

Đây là hàm Java thuần minh họa; trước khi production phải validate **cùng tenant/batch/revision, positions hợp lệ, member set đầy đủ, duplicate conflicts**, currency và overflow. Nếu business không có yêu cầu từng message phải được phát theo thứ tự, **Aggregator + sort** thường ít state và đơn giản hơn **Resequencer → Aggregator**.

## 32. Observability: đo ordering khác với đo aggregation completion

| Metric gợi ý | Resequencer | Aggregator |
|---|---|---|
| `group.pending.count` | Nhóm chờ gap | Nhóm chờ member |
| `sequence.out.of.order.count` | Số input đảo thứ tự | Có thể không quan trọng |
| `sequence.gap.count` | Vị trí chưa nhận | Kiểm tra member manifest |
| `sequence.buffered.count` | Messages đang chờ phát | Messages đang chờ kết luận |
| `group.release.latency` | Thời gian chờ được phát | Thời gian chờ kết quả tổng |
| `aggregation.completed.count` | Không phải output chính | Số summary đã release |
| `group.timeout.count` | Gap không được lấp | Member chưa có outcome |
| `group.duplicate.count` | Duplicate sequence/member | Duplicate business result |
| `group.late.count` | Message tới sau expiry | Reply tới sau complete |
| `message.store.bytes` | Buffer/resource pressure | Aggregate state pressure |

Đây là **tên metric đề xuất**, không phải lời khẳng định về meter mặc định của Spring Integration. Dùng tag có cardinality thấp (`flow, status, reasonCode`), không đưa `batchId/correlationId` vào metric tags không giới hạn. ID cụ thể thuộc structured logs/tracing có retention và quyền truy cập phù hợp.

Khi consumer báo “message #3 mãi không xử lý”, cần xác định #3 đang chờ #1/#2 ở Resequencer, bị queue sau đó chặn, hay đã tới Aggregator nhưng group còn thiếu member.

## 33. Runbook khi thứ tự sai hoặc group không hoàn tất

1. **Xác định output contract:** cần N message theo thứ tự hay một summary?
2. **Đối chiếu group key:** các result có cùng logical batch/tenant/revision không?
3. **Kiểm tra sequence:** số bắt đầu, sequence size, gap, duplicate, type/format header.
4. **Xem Splitter/Transformer:** có mất hoặc ghi đè correlation headers?
5. **Xem Filter/error channel:** một child đã bị drop hoặc lỗi không phát failure result?
6. **Xem GroupStore:** nhóm tồn tại bao lâu, deadline và expiry như thế nào?
7. **Xem broker/executor:** reorder xảy ra trước hay sau Resequencer?
8. **Xem Aggregator:** release bằng count có bị duplicate đánh lừa không?
9. **Kiểm tra side effects:** đã commit trước ordering boundary hay chưa?
10. **Recovery:** replay đúng member thiếu hoặc phát correction theo policy, không xóa hết group rồi phát lại khi chưa xác minh idempotency.

Một bộ đệm Resequencer tăng liên tục vì nhiều gap không phải tín hiệu chỉ cần thêm RAM. Cần xem lại nguồn sequence, cách phát/ack message, và có nên xử lý theo ordered partition hoặc window thay vì lưu group lâu.

## 34. Các hiểu lầm phổ biến

**“Resequencer là Aggregator có sort.”** Sai. Nó phát **từng message**; Aggregator tạo **kết quả gộp**.

**“Đợi đủ sequence nghĩa là output thành một List.”** Sai với Resequencer. Release và aggregation là hai quyết định khác nhau.

**“Aggregator mặc định trả collection theo đúng thứ tự business.”** Không nên giả định nếu worker song song; cần sort/processor theo contract.

**“sequenceNumber là group ID.”** Sai. Sequence number có nghĩa trong một correlation group.

**“MessageHeaders.ID đủ bền vững cho retry.”** Sai. Message có thể bị dựng lại.

**“Partial release được phép bỏ qua mọi gap.”** Sai. Nó chủ yếu cho phép phát prefix liên tục; bỏ gap cần expiry/skip policy rõ.

**“Resequencer sửa thứ tự commit ở database trước nó.”** Sai. Nó chỉ sắp message đi ra **sau vị trí được đặt**.

**“Một Gateway sẽ tự gom N outputs của Resequencer thành một reply.”** Không tự động; cần Aggregator hoặc streaming contract khác.

**“Persistent MessageGroupStore bảo đảm exactly-once.”** Sai. Còn idempotency, locking, transactions và late replies.

**“Filter drop message #2, Resequencer sẽ tự lấp #2.”** Sai. Cần failure outcome hoặc recovery/timeout.

**“Resequencer phù hợp mọi luồng vô hạn có gaps lớn.”** Không phải use case khuyến nghị; reference cảnh báo về hiệu năng với nhiều sequences có gaps.

## 35. Bài thực hành: so sánh ba kiến trúc trên cùng dữ liệu

Xây ứng dụng **OrderLineOutcomeFlow**:

1. **Resequencer:** gửi 3,1,2 và assert **3 outputs** theo 1,2,3.
2. **Aggregator:** gửi cùng ba message và assert **1 output** là collection/summary.
3. **Combined:** dùng Resequencer → Aggregator và so sánh với Aggregator + sort trong processor.
4. **Partial sequence:** bật `releasePartialSequences(true)`, gửi 3,1,4,2; kiểm tra prefix.
5. **Missing member:** không gửi #2; kiểm tra group timeout và policy.
6. **Filter rejection:** tạo failure result #2 có sequence/correlation đúng.
7. **Correlation:** gửi hai batch A/B xen kẽ, không gom lẫn.
8. **Retry:** dựng lại Spring Message với ID mới nhưng logical group ID cũ, kiểm tra dedupe.
9. **Broker/Executor:** đo ordering trước và sau mỗi async boundary.
10. **Gateway:** kiểm tra phương thức trả BatchSummary chỉ hoàn thành khi Aggregator có kết quả.
11. **Storage:** so memory với pending groups, gaps và group expiry.
12. **Incident drill:** chẩn đoán missing sequence, duplicate, sai key, sai release strategy.

**Tiêu chí hoàn thành:** phân biệt bằng assertion **N messages so với một message**, không dùng sequenceNumber làm correlation key, giữ group độc lập, partial release không tự phát vượt gap, retry không tạo side effect trùng và error/expiry có chính sách minh bạch.

## 36. Ghi nhớ

**Resequencer và Aggregator đều sử dụng message groups nhưng có mục tiêu khác nhau.** Resequencer phát lại từng message theo `SEQUENCE_NUMBER` trong phạm vi `CORRELATION_ID`; Aggregator thu thập các message để tạo kết quả tổng hợp theo release strategy và output processor.

Chọn **Resequencer** khi downstream phải **nhận từng event đúng thứ tự**. Chọn **Aggregator** khi cần **một response, một batch result, tổng tiền hoặc kết luận Scatter-Gather**. Chỉ kết hợp hai endpoint khi cả ordering lẫn aggregation đều là yêu cầu thực sự.

Một flow Spring Integration đáng tin cậy cần giữ đúng **correlation/sequence metadata**, có chính sách **missing gaps, duplicate, retry, timeout, MessageGroupStore, idempotency và ordering boundary**. Sắp đúng thứ tự không tự sửa side effect đã xảy ra trước đó; nhóm đủ số lượng cũng chưa chắc đủ **đúng thành viên**. Hãy kiểm thử riêng **ordering, output cardinality và business completion**.

### Tài liệu tham khảo

- Spring Integration Reference, **Resequencer**: https://docs.spring.io/spring-integration/reference/resequencer.html
- Spring Integration Reference, **Aggregator**: https://docs.spring.io/spring-integration/reference/aggregator.html
- Spring Integration Reference, **Aggregators and Resequencers (Java DSL)**: https://docs.spring.io/spring-integration/reference/dsl/java-aggregators.html
- Spring Integration Reference, **Splitter**: https://docs.spring.io/spring-integration/reference/splitter.html
- Enterprise Integration Patterns, **Resequencer**: https://www.enterpriseintegrationpatterns.com/patterns/messaging/Resequencer.html
- Enterprise Integration Patterns, **Aggregator**: https://www.enterpriseintegrationpatterns.com/patterns/messaging/Aggregator.html
