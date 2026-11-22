# Correlation không ổn định gây gom nhầm group

## 1. Một đơn hàng, hai lần xử lý và một kết quả sai

Một hệ thống nhận đơn hàng có ba dòng sản phẩm. **Splitter** tách đơn thành ba message, các worker xử lý tồn kho rồi gửi kết quả về **Aggregator**. Về nguyên tắc, Aggregator chỉ được gom những kết quả thuộc **cùng một lần xử lý logic của cùng một đơn**.

Giả sử khách hàng cập nhật đơn `O-101` trước khi lượt xử lý đầu tiên hoàn tất:

~~~text
Lượt A: orderId=O-101, revision=1, lines=[L1, L2, L3]
Lượt B: orderId=O-101, revision=2, lines=[L1, L2, L4]

Kết quả về theo thứ tự:
  A/L1 thành công
  B/L1 thành công
  B/L2 thành công
  A/L3 thành công
  A/L2 thành công
  B/L4 thành công
~~~

Nếu Aggregator chỉ dùng `orderId=O-101` để correlation, **hai lượt A và B có thể bị gom chung một message group**. Nếu release strategy chỉ kiểm tra số lượng 3, nhóm có thể được giải phóng ngay sau ba kết quả đầu tiên dù chúng thuộc **hai revision khác nhau**. Output trông như đủ ba dòng nhưng có nội dung sai.

Đây là lỗi nguy hiểm vì nó có thể **không ném exception**: một `OrderSummary` được tạo, Gateway trả reply, downstream ghi dữ liệu, nhưng kết quả tổng hợp không thuộc một tập nghiệp vụ nhất quán.

**Chủ đề của bài:** thiết kế **correlation key ổn định và có phạm vi**, bảo đảm mỗi message thuộc đúng một group, tránh ghép nhầm giữa các tenant, lượt xử lý, revision, retry hoặc broker redelivery; kết hợp release strategy và idempotency để không kết luận hoàn tất quá sớm.

Bài nằm trong chương **Aggregator** của module **SPRING_INTEGRATION_PATTERN**. Module hướng tới học triển khai **Enterprise Integration Patterns** với Spring Integration để xây dựng message flow ít phụ thuộc, dễ mở rộng; thực hành **Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation**, đồng thời kiểm thử và quan sát các nhánh xử lý.

Sau bài học, bạn có thể phân tích nguyên nhân gom sai group, định nghĩa identity của một đơn vị công việc, tạo correlation strategy rõ ràng, phối hợp với Splitter, xử lý nhóm trùng/thiếu/trễ, dùng MessageGroupStore phù hợp và kiểm thử concurrency, retry, restart.

## 2. Aggregator không tự biết thế nào là “cùng nghiệp vụ”

**Aggregator** trong Enterprise Integration Patterns tiếp nhận nhiều message liên quan, đưa chúng vào **message group**, đánh giá **release strategy**, sau đó tạo một output tổng hợp. Để làm vậy, ít nhất phải trả lời:

1. **Correlation:** message này phải được đặt vào **group nào**?
2. **Release:** khi nào group ấy đã có **đủ thông tin để kết luận**?
3. **Aggregation:** gộp những message trong group thành payload kết quả **như thế nào**?
4. **Expiry:** group chưa đủ hoặc đã hoàn tất được giữ/xóa/xử lý khi nào?

~~~mermaid
flowchart LR
    A["LineResult A/L1"] --> COR{"Correlation strategy"}
    B["LineResult B/L1"] --> COR
    C["LineResult A/L2"] --> COR
    COR --> GA["Group: O-101/rev1"]
    COR --> GB["Group: O-101/rev2"]
    GA --> RA{"Release strategy A"}
    GB --> RB{"Release strategy B"}
    RA --> OA["Summary revision 1"]
    RB --> OB["Summary revision 2"]
~~~

Một correlation key bị tính sai làm message **vào nhầm group từ đầu**. Khi ấy release strategy có thể hoạt động đúng theo quy tắc đếm nhưng vẫn cho ra **kết quả sai nghiệp vụ**. Ngược lại, một key quá cụ thể hoặc thay đổi liên tục khiến các message thuộc cùng lượt xử lý bị **chia thành nhiều group**, không group nào có đủ kết quả.

**Một Aggregator không tự sửa được correlation sai** chỉ bằng cách đợi lâu hơn. Cần sửa định nghĩa identity, bảo vệ đầu vào, kiểm tra thành viên group và thiết kế retry/expiry.

## 3. Correlation không ổn định là gì?

Khóa correlation “ổn định” nghĩa là **mọi kết quả của cùng một đơn vị công việc logic tạo ra chính xác cùng khóa**, còn hai đơn vị công việc **không được phép gom chung** phải có khóa khác nhau.

Hai dạng lỗi đối nghịch:

| Dạng lỗi | Ví dụ | Hệ quả |
|---|---|---|
| **Key thay đổi trong cùng group** | Mỗi lần retry tạo UUID mới rồi dùng làm correlation | Cùng batch bị chia thành nhiều group thiếu kết quả |
| **Key trùng giữa những group khác nhau** | Chỉ dùng `orderId`, không gồm revision | Hai lần xử lý bị trộn |
| **Key mất khi đổi message** | Transformer tạo message mới và bỏ header correlation | Aggregator tạo group sai hoặc không phân nhóm được |
| **Key biến đổi kiểu/format** | `"00123"` thành số `123` khi qua broker | Kết quả về group khác hoặc collision |
| **Key chứa nguồn không tin cậy** | Dùng raw `tenantId`/`correlationId` do client tự đặt | Có thể trộn dữ liệu chéo tenant |
| **Key phụ thuộc thời điểm** | Tính key từ `Instant.now()` ở mỗi handler | Mỗi nhánh có thể vào group riêng |
| **Key quá thô** | Dùng `customerId` làm correlation | Nhiều order cùng customer vào chung group |
| **Key quá chi tiết** | Dùng `lineId` để gom kết quả toàn order | Mỗi line thành group riêng |

**Bất biến quan trọng:**

\[
\text{sameLogicalWork}(m_1,m_2)
\Longrightarrow
\operatorname{key}(m_1)=\operatorname{key}(m_2)
\]

\[
\neg\text{sameLogicalWork}(m_1,m_2)
\Longrightarrow
\operatorname{key}(m_1)\ne\operatorname{key}(m_2)
\]

Hai điều kiện cần được xác định theo **ngữ nghĩa nghiệp vụ**, không chỉ theo kiểu Java hoặc giá trị header. Thực tế một hash có thể collision, một string có thể bị chuẩn hóa sai, và một business ID có thể được tái sử dụng có chủ đích cho nhiều revision.

## 4. “Cùng đơn” không nhất thiết là “cùng group”

Một mã `orderId` có thể sống lâu hơn một lần tính toán:

~~~text
tenant-A / O-101 / pricing-revision-1
tenant-A / O-101 / pricing-revision-2
tenant-A / O-101 / refund-operation-1
tenant-B / O-101 / pricing-revision-1
~~~

Cả bốn bản ghi có thể chia sẻ một phần ID, nhưng không được đặt chung message group.

Một **aggregation scope** tốt thường cần một tổ hợp:

| Thuộc tính | Vì sao cần |
|---|---|
| `tenantId` hoặc phạm vi chủ sở hữu | Tránh dữ liệu tenant A lẫn vào B |
| `operationType` | Phân biệt pricing, inventory, shipping, refund |
| `workId`/`batchId`/`processId` | Nhận diện một lần xử lý logic |
| `revision`/`generation` | Phân biệt nhiều phiên bản của cùng dữ liệu |
| `expectedMemberSet` hoặc manifest | Biết các kết quả nào thực sự thuộc group |

**Không phải lúc nào cũng cần nối tất cả thuộc tính**. Nếu một `processingGroupId` được cấp duy nhất cho mỗi lượt xử lý và có tenant scope rõ ràng, nó có thể đã đại diện cho cả operation/revision. Tuy nhiên, phải công bố và kiểm thử hợp đồng cấp ID đó.

Trong các ví dụ bên dưới, dùng khóa gồm `tenantId + processingGroupId + revision`. Đây là **khóa tổng hợp đã chuẩn hóa**, không phải chuỗi người dùng tự nhập vào một header không được kiểm soát.

## 5. Phân biệt Message ID, correlationId và business group ID

| Định danh | Ai thường tạo | Mục đích | Rủi ro khi dùng làm group key bền vững |
|---|---|---|---|
| `MessageHeaders.ID` | Spring Messaging | Định danh một đối tượng message | Message tái tạo có thể nhận ID mới |
| `IntegrationMessageHeaderAccessor.CORRELATION_ID` | Flow/endpoint hoặc ứng dụng | Liên hệ các message cùng nhóm | Có thể được gán lại hoặc không qua transport |
| `sequenceNumber` | Splitter/sequence producer | Vị trí phần tử trong sequence | Không duy nhất cho group; mọi nhóm đều có phần tử 1 |
| `sequenceSize` | Splitter/sequence producer | Số phần tử dự kiến, khi biết được | Không nhận diện group; có thể thiếu/sai |
| `eventId` | Producer nghiệp vụ | Truy vết/idempotency của event | Một event có thể sinh nhiều operation |
| `orderId` | Domain | Nhận diện order | Nhiều revision/lượt xử lý trên cùng order |
| `processingGroupId` | Coordinator/Splitter đầu nguồn | Nhận diện một lượt xử lý logic | Phù hợp nếu ổn định, duy nhất, được xác thực |
| `traceId` | Tracing | Quan sát chuỗi call | Không nhất thiết trùng phạm vi group |

**Spring Integration có correlation strategy mặc định** thường sử dụng header `correlationId` và release strategy dựa trên sequence headers. Chúng hữu ích với Splitter/Aggregator trong một topology được kiểm soát, nhưng **không phải hợp đồng correlation nghiệp vụ bền vững cho mọi broker/retry/restart**.

Đặc biệt, một Splitter có thể tạo correlation theo ID của **message gốc tại thời điểm split**. Khi replay cùng batch dưới một **message mới**, ID của message gốc có thể khác: các child lần 2 không được gom cùng lần 1 dù nghiệp vụ muốn tiếp tục cùng logical work.

Khi cần semantics xuyên process hoặc retry, chủ động định nghĩa một **stable business group key**, thay vì dựa vào cách framework cấp ID message trong từng lần dispatch.

## 6. Khóa nhóm phải được cấp trước khi tách message

Một coordinator nhận lô đầu vào, xác định **logical work**, rồi cấp một key dùng chung:

~~~mermaid
flowchart TD
    IN["OrderBatch O-101 revision 7"] --> CO["Coordinator: cấp processingGroupId=PG-901"]
    CO --> S["Splitter"]
    S --> L1["LineWork L1 + PG-901"]
    S --> L2["LineWork L2 + PG-901"]
    S --> L3["LineWork L3 + PG-901"]
    L1 --> W1["Worker 1"]
    L2 --> W2["Worker 2"]
    L3 --> W3["Worker 3"]
    W1 --> A["Aggregator by stable group key"]
    W2 --> A
    W3 --> A
~~~

Tại bước cấp ID:

1. Xác định tenant theo nguồn đã xác thực.
2. Chọn operation và revision theo manifest hoặc trạng thái đã lưu.
3. Cấp `processingGroupId` **một lần cho logical work**, không cấp lại ở mỗi line handler.
4. Ghi manifest các member dự kiến và deadline nếu cần bền vững.
5. Gửi group ID xuống từng child và yêu cầu mọi result bảo toàn nó.

Đừng gọi `UUID.randomUUID()` **bên trong correlation strategy**. Một method được gọi cho từng message sẽ tạo khóa mới cho từng result, khiến mỗi message thành một group riêng.

Nếu muốn retry **chính logical work cũ**, tái sử dụng group ID đã được lưu. Nếu nghiệp vụ quyết định retry là **một lần xử lý mới độc lập**, dùng group ID khác, nhưng phải nêu rõ điều này trong state machine; không đổi ngẫu nhiên vì worker restart.

## 7. Mô hình message con cho aggregation ổn định

Sử dụng Java 17+ với record bất biến:

~~~java
record OrderLine(
    String lineId,
    String sku,
    int quantity
) {}

record OrderWork(
    String tenantId,
    String orderId,
    String processingGroupId,
    int revision,
    List<OrderLine> lines
) {}

record LineWork(
    String tenantId,
    String orderId,
    String processingGroupId,
    int revision,
    String lineId,
    String sku,
    int quantity,
    int expectedLines
) {}

record LineOutcome(
    String tenantId,
    String orderId,
    String processingGroupId,
    int revision,
    String lineId,
    int expectedLines,
    boolean success,
    String reasonCode
) {
    String stableGroupKey() {
        return StableGroupKey.of(
            tenantId, processingGroupId, revision);
    }
}

record OrderSummary(
    String tenantId,
    String orderId,
    String processingGroupId,
    int revision,
    int expectedLines,
    int succeeded,
    int failed
) {}
~~~

Điểm quan trọng:

- `LineWork` và `LineOutcome` **đều mang lại identity**, không chỉ trông chờ original Spring headers.
- `lineId` là identity của **một member** trong group; `processingGroupId` là identity của **group**.
- `expectedLines` cần được chốt từ manifest và phải nhất quán giữa các member; không để mỗi worker tự tính.
- `revision` giúp phân biệt thay đổi của đơn khi cùng một order đang được xử lý nhiều lần.

Đây là các type mô tả contract. Thực tế cần validate các field không null/blank tại ingress và có giới hạn kích thước, phạm vi tenant, quyền thao tác trước khi dùng chúng làm khóa.

## 8. Tạo khóa ổn định, tránh collision khi nối chuỗi

Nối thô như `tenant + orderId` có thể tạo collision:

~~~text
tenant="AB", orderId="C" → "ABC"
tenant="A",  orderId="BC" → "ABC"
~~~

Nếu dùng key string để lưu trong MessageGroupStore/broker, cần một format **có quy tắc và không nhập nhằng**:

~~~java
final class StableGroupKey {

    static String of(String tenantId,
                     String processingGroupId,
                     int revision) {
        if (tenantId == null
                || !tenantId.matches("[a-z0-9-]{1,48}")) {
            throw new IllegalArgumentException("INVALID_TENANT");
        }
        if (processingGroupId == null
                || !processingGroupId.matches("[A-Z0-9-]{1,80}")) {
            throw new IllegalArgumentException("INVALID_GROUP_ID");
        }
        if (revision < 1) {
            throw new IllegalArgumentException("INVALID_REVISION");
        }
        // Dấu | không nằm trong bộ ký tự được phép của các trường.
        return "t:" + tenantId
            + "|g:" + processingGroupId
            + "|v:" + revision;
    }
}
~~~

Ví dụ:

~~~text
t:tenant-a|g:PG-901|v:7
t:tenant-a|g:PG-901|v:8
t:tenant-b|g:PG-901|v:7
~~~

Ba khóa khác nhau tương ứng ba group khác nhau. Nếu ID cho phép Unicode, dấu phân cách hoặc case-insensitive semantics, cần xác định encoding/canonicalization và versioning cho format. Một **record làm group key** cũng có thể phù hợp trong JVM, nhưng cần cân nhắc tính serialize/deserialize ổn định khi dùng persistent/distributed MessageGroupStore.

**Cẩn thận với chuẩn hóa:** không tự đổi chữ hoa/thường của business identifier nếu contract coi `AB` và `ab` là hai ID khác nhau. Chuẩn hóa ở đầu nguồn và dùng **cùng thuật toán trên mọi instance**, không tự biến đổi mỗi nhánh một kiểu.

## 9. Splitter phải bảo toàn group ID khi phát từng item

Một Splitter đơn giản có thể tạo các `LineWork`:

~~~java
@MessageEndpoint
class OrderWorkSplitter {

    @Splitter(
        inputChannel = "orders.work",
        outputChannel = "orders.lines")
    public List<LineWork> split(OrderWork work) {
        if (work.lines() == null || work.lines().isEmpty()) {
            throw new IllegalArgumentException("EMPTY_LINES");
        }
        int expected = work.lines().size();
        return work.lines().stream()
            .map(line -> new LineWork(
                work.tenantId(),
                work.orderId(),
                work.processingGroupId(),
                work.revision(),
                line.lineId(),
                line.sku(),
                line.quantity(),
                expected))
            .toList();
    }
}
~~~

Các child có thể mang sequence headers do Splitter quản lý. Nhưng **stable group identity nằm trong payload contract** và có thể được giữ khi worker chuyển thành `LineOutcome`.

Nếu các bước Transformer, Header Enricher hoặc broker adapter nằm giữa Splitter và Aggregator, kiểm thử rằng chúng không làm mất `tenantId`, `processingGroupId`, `revision` hoặc ánh xạ sang ID khác. Một worker chỉ trả `lineId` và `status` mà bỏ group identity sẽ khiến Aggregator không đủ dữ liệu để ghép chắc chắn.

## 10. Java DSL: cấu hình Aggregator với correlation strategy riêng

Spring Integration cho phép cấu hình **correlation strategy**, **release strategy** và **output processor** tách biệt. Ta không phụ thuộc vào `MessageHeaders.ID` hay nhận thức ngầm về source của `correlationId`.

~~~java
@Configuration
@EnableIntegration
class OrderAggregationFlow {

    @Bean
    IntegrationFlow aggregateLineOutcomes() {
        return IntegrationFlow.from("orders.line.results")
            .aggregate(a -> a
                .correlationStrategy(message ->
                    ((LineOutcome) message.getPayload())
                        .stableGroupKey())
                .releaseStrategy(new StableOrderReleaseStrategy())
                .outputProcessor(new OrderSummaryProcessor()))
            .channel("orders.completed")
            .get();
    }
}
~~~

Khi một `LineOutcome` đến, correlation strategy trả một **string ổn định**, giúp Aggregator xác định đúng message group. Hai strategy tiếp theo sẽ được mô tả chi tiết ở mục sau.

**Điều kiện để ví dụ hoạt động:**

- `orders.line.results` nhận đúng kiểu `LineOutcome` hoặc có type gate phù hợp.
- Các consumer/producer đã xác minh nguồn và scope, không tin tùy ý vào `tenantId`/`processingGroupId` tự gửi từ client.
- `orders.completed` có consumer hoặc test channel thực.
- Đây là một minh họa Java DSL, lược bỏ import; phiên bản Spring Integration thực tế có thể cần tinh chỉnh một số method/options.
- Không đăng ký đồng thời một Aggregator khác tiêu thụ cùng point-to-point input nếu không có chủ ý.

## 11. Release strategy không được chỉ đếm message

Một sai lầm hay gặp:

~~~java
.releaseStrategy(group -> group.size() == 3)
~~~

Điều đó nói “nhóm hiện có ba message”, **không nói ba message đại diện cho ba member khác nhau**. Nếu L1 bị redeliver hai lần còn L3 chưa đến:

~~~text
Group PG-901:
  L1: result lần đầu
  L1: duplicate từ retry
  L2: result hợp lệ

group.size() có thể bằng 3 → release sai, thiếu L3
~~~

Một release strategy chặt hơn cần biết **manifest các member mong đợi** hoặc tối thiểu kiểm tra **số ID member duy nhất** và metadata nhất quán. Ví dụ sau dùng `expectedLines` đã được upstream chốt:

~~~java
final class StableOrderReleaseStrategy implements ReleaseStrategy {

    @Override
    public boolean canRelease(MessageGroup group) {
        List<LineOutcome> parts = group.getMessages().stream()
            .map(message -> (LineOutcome) message.getPayload())
            .toList();
        if (parts.isEmpty()) {
            return false;
        }

        LineOutcome first = parts.get(0);
        int expected = first.expectedLines();
        if (expected <= 0 || expected > 100_000) {
            throw new IllegalStateException("INVALID_EXPECTED_COUNT");
        }

        boolean consistent = parts.stream().allMatch(part ->
            part.stableGroupKey().equals(first.stableGroupKey())
                && part.orderId().equals(first.orderId())
                && part.expectedLines() == expected);
        if (!consistent) {
            throw new IllegalStateException("GROUP_METADATA_MISMATCH");
        }

        long uniqueMembers = parts.stream()
            .map(LineOutcome::lineId)
            .distinct()
            .count();

        return uniqueMembers == expected;
    }
}
~~~

**Giới hạn của ví dụ:** so `uniqueMembers == expected` mới chứng minh có **đủ số lượng ID khác nhau**, chưa chứng minh các ID đó nằm trong **tập ID được manifest chấp nhận**. Một message từ line lạ có thể thế chỗ line bị thiếu. Trong production, nên kiểm tra `Set<lineId> == manifest.expectedLineIds` tại coordinator, hoặc dùng một store/validator có thể xác minh membership.

Ngoài ra, duplicate cùng `lineId` có thể mang **hai outcome mâu thuẫn**; cần policy để phân loại trước khi output (ví dụ chỉ chấp nhận result của attempt/version hợp lệ). Không nên im lặng lấy kết quả cuối đến trước hoặc cuối đến sau theo thứ tự ngẫu nhiên.

## 12. Output processor: mỗi member chỉ đóng góp một kết quả

Khi release, Aggregator cần tạo một kết quả có thể kiểm toán. Ví dụ:

~~~java
final class OrderSummaryProcessor implements MessageGroupProcessor {

    @Override
    public Object processMessageGroup(MessageGroup group) {
        Map<String, LineOutcome> byLine = new LinkedHashMap<>();
        for (Message<?> message : group.getMessages()) {
            LineOutcome part = (LineOutcome) message.getPayload();
            LineOutcome previous =
                byLine.putIfAbsent(part.lineId(), part);
            if (previous != null && !previous.equals(part)) {
                throw new IllegalStateException(
                    "CONFLICTING_DUPLICATE_RESULT");
            }
        }

        if (byLine.isEmpty()) {
            throw new IllegalStateException("EMPTY_GROUP");
        }
        LineOutcome first = byLine.values().iterator().next();

        long successes = byLine.values().stream()
            .filter(LineOutcome::success)
            .count();

        return new OrderSummary(
            first.tenantId(),
            first.orderId(),
            first.processingGroupId(),
            first.revision(),
            first.expectedLines(),
            Math.toIntExact(successes),
            byLine.size() - Math.toIntExact(successes));
    }
}
~~~

Processor ở đây **không tính duplicate thành một member mới**. Tuy vậy nó không thay thế một inbox/dedupe store có transaction và không tự đảm bảo **chỉ phát một output** nếu group được tạo lại sau expiry hoặc broker redelivery.

Nếu `LineOutcome.success=false`, outcome đó vẫn là **một kết quả đã có** của member; nó có thể đóng góp vào điều kiện “đã có kết luận cho mọi line”, còn tổng kết là `PARTIAL/FAILED`. Không phải mọi failure đều nên làm Aggregator đợi mãi; cần phân biệt **failure result có cấu trúc** với exception làm mất reply.

## 13. Sai khóa vs sai release: hai nhóm lỗi khác nhau

| Triệu chứng | Nguyên nhân chính | Điều cần sửa |
|---|---|---|
| A/rev1 và B/rev2 bị lẫn | Correlation key quá thô | Bổ sung processing group/revision/tenant |
| Mỗi line thành một group | Key được sinh mới ở từng handler | Cấp group ID từ coordinator trước Splitter |
| Group có 3 message nhưng thiếu L3 | Release chỉ đếm message | Unique members + manifest |
| Group vẫn chờ dù đã đủ line | Kết quả dùng hai key format khác nhau | Canonicalization/hợp đồng correlation |
| Group release rồi lại có summary khác | Group bị xóa/tạo lại, late/duplicate đến | Completion tombstone và idempotency |
| Summary trộn tenant | Dùng ID trùng không có tenant scope | Identity đã xác minh + key đa tenant |
| Chỉ thấy timeout ở Gateway | Một member không bao giờ đến | Error/timeout/result contract |

**Chẩn đoán theo thứ tự:** trước hết xem **message thuộc group nào**; sau đó xem **group đủ member chưa**; cuối cùng mới đánh giá output processor. Nếu group đã chứa dữ liệu của hai lượt logic khác nhau, tăng timeout hoặc đổi cách cộng kết quả chỉ che giấu vấn đề.

## 14. Retry và redelivery không được tự đổi group identity

Giả sử worker xử lý L2 của group `PG-901` nhưng bị timeout khi gửi reply. Broker phát lại L2.

~~~text
Attempt 1: LineWork(PG-901, L2) → LineOutcome(PG-901, L2)
Attempt 2: LineWork(PG-901, L2) → LineOutcome(PG-901, L2)
~~~

Để retry là **một lần thử của cùng logical work**, phải giữ ổn định:

- `tenantId`;
- `processingGroupId`;
- `revision`;
- `lineId`;
- request/event ID nếu dùng làm idempotency;
- manifest/expected members.

Có thể thêm `attemptNumber` hoặc `attemptId` để quan sát retry, nhưng **không đưa attemptId vào group key** nếu muốn hai attempt cạnh tranh cho cùng một member của group cũ.

Nếu attempt 2 khác outcome của attempt 1, không được tùy ý coi hai kết quả tương đương. Cần xác định:

1. Outcome nào được phép là **quyết định cuối** của line?
2. Có version/fencing token để bỏ kết quả từ attempt cũ không?
3. Khi một side effect đã commit, hệ thống có idempotency theo line/operation không?
4. Có thể sửa một summary đã phát hay phải phát một bản correction mới?

**Spring Integration Aggregator không tự cung cấp exactly-once business semantics.** Correlation ổn định chỉ giúp nhận diện đúng group; transaction, deduplication và downstream idempotency vẫn phải thiết kế riêng.

## 15. Vì sao MessageHeaders.ID có thể làm retry thành group mới?

Ở một Splitter trong JVM, sequence/correlation headers có thể dựa trên message gốc. Nhưng khi redelivery:

~~~text
Message gốc lần 1:
  Spring Message ID = m-111
  Splitter → children correlationId = m-111 (minh họa)

Message gốc lần 2 (rebuild):
  Spring Message ID = m-222
  Splitter → children correlationId = m-222
~~~

Đây là **mô hình minh họa** phụ thuộc cách tạo headers của splitter và cấu hình cụ thể. Nó cho thấy rủi ro: cùng `batchId=PG-901` nhưng hai lần tách tạo **hai group khác nhau** nếu dùng framework message ID làm correlation xuyên retry.

Khi dùng transport bên ngoài, header mapper còn có thể chuyển `UUID` thành `String`, thay tên hoặc bỏ đi. Hai giá trị nhìn giống nhau trong log chưa chắc cùng kiểu/canonical format tại `MessageGroupStore`.

**Khuyến nghị:** giữ các framework headers cho mục tiêu điều phối **trong topology đã kiểm thử**, đồng thời dùng một business group key kiểu dữ liệu ổn định khi cần đi qua broker, restart hoặc thay đổi triển khai.

## 16. Multi-tenant: ghép đúng ID nhưng sai tenant vẫn là sai

Hai tenant có thể dùng cùng mã đơn:

~~~text
tenant-A / order=O-101 / group=PG-01
tenant-B / order=O-101 / group=PG-01
~~~

Nếu correlation strategy chỉ trả `PG-01`, dữ liệu có thể **trộn qua ranh giới tenant**.

~~~mermaid
flowchart LR
    A["Tenant A / PG-01 / L1"] --> BAD{"Key = PG-01"}
    B["Tenant B / PG-01 / L2"] --> BAD
    BAD --> MIX["Mixed group: sai"]
~~~

Để ngăn:

- Xác thực tenant tại adapter hoặc trust boundary; không dựa hoàn toàn vào header `tenantId` do client có thể gửi.
- Dùng correlation key có **tenant scope**.
- Kiểm tra message member có đúng tenant/order/operation/revision so với manifest không.
- Phân quyền đối với MessageGroupStore, logs và error channel; không trả payload nhóm A cho caller thuộc B.
- Tránh log thô thông tin cá nhân; chỉ giữ ID cần thiết cho truy vết có kiểm soát.

**Đưa tenant vào key là cần nhưng chưa đủ.** Nếu producer có thể giả mạo tenant ID rồi gửi vào group của người khác, identity vẫn có thể sai. Cần kiểm soát nguồn gán giá trị và quyền thao tác.

## 17. Một revision mới không được lén nhập vào group cũ

Khi đơn đã được sửa, có hai mô hình hợp lệ:

**Mô hình A — mỗi revision là logical work mới:**

~~~text
PG-901/v1 → kết quả riêng
PG-901/v2 → kết quả riêng
~~~

Nhóm v1 có thể hoàn tất muộn, nhưng hệ thống phải quyết định có còn được **publish/commit** kết quả cũ khi v2 đã là phiên bản hiện hành hay không. Có thể dùng version check/fencing tại downstream.

**Mô hình B — cùng logical work được điều chỉnh trước khi chốt:** coordinator cập nhật manifest theo một state machine; lúc đó expected members, version và chính sách release cần thay đổi **có kiểm soát**, không tự sửa group key trên các message đang bay mà không có bước migrate.

**Không trộn hai mô hình.** Nếu xử lý revision mới nhưng vẫn dùng key cũ và expectedCount cũ, một nhóm có thể release khi chưa có kết quả của revision mới hoặc dùng kết quả lỗi thời.

Một cách kiểm toán tốt: mỗi `OrderSummary` mang `processingGroupId` và `revision`; consumer chỉ chấp nhận kết quả theo phiên bản hợp lệ của nghiệp vụ.

## 18. Late arrivals và completed group

Một tình huống thường bị bỏ qua: Aggregator đã release group, nhưng sau đó một reply cũ hoặc duplicate đến.

~~~text
09:00:00  L1, L2, L3 của PG-901 tới → release Summary #1
09:00:01  duplicate L2 tới
09:00:02  reply L1 của attempt cũ tới muộn
~~~

Hành vi của Aggregator với các message đến sau completion phụ thuộc **lifecycle group**, cấu hình expiry và MessageGroupStore. Nếu group cũ đã bị xóa và không có bản ghi completion, các late arrivals **có thể hình thành một group mới với cùng correlation key**, cuối cùng tạo thêm output sai.

Các giải pháp tùy yêu cầu:

1. **Completion tombstone:** lưu một dấu “group PG-901/v7 đã hoàn tất” trong thời hạn được xác định; late arrivals bị bỏ hoặc quarantine.
2. **Durable dedupe:** dùng business key và uniqueness constraint/conditional transition cho output `SummaryPublished`.
3. **Reconciliation:** nếu late result được phép sửa kết quả, phát **correction event** có version thay vì âm thầm tạo summary trùng.
4. **Expiry policy:** định nghĩa xử lý group hết hạn và các message đến sau expiry.

Cấu hình Spring Integration như `expireGroupsUponCompletion`, group timeout và các cơ chế xử lý message group sau release cần được lựa chọn, kiểm thử theo phiên bản đang dùng; **không giả định trạng thái group được giữ vĩnh viễn hoặc late arrivals mặc nhiên bị từ chối**.

## 19. Group thiếu thành viên: Filter, handler void và lỗi không có result

Một group có thể **không bao giờ đủ**, dù correlation key đúng.

~~~mermaid
flowchart TD
    SPLIT["Splitter: L1, L2, L3"] --> F{"Filter / worker"}
    F -->|"L1: OK"| A["Aggregator"]
    F -->|"L2: bị drop"| LOST["Không có result"]
    F -->|"L3: OK"| A
    A --> WAIT["Chỉ có 2/3 outcomes: chờ"]
~~~

Các tình huống:

- Filter loại một child mà không tạo result thay thế.
- Service Activator `void` thực hiện side effect nhưng không reply.
- Exception xảy ra trước khi worker trả `LineOutcome`.
- Kafka/AMQP message bị giữ trong retry/DLQ nhưng Aggregator chưa biết kết quả.
- Reply đi tới sai channel hoặc mất correlation header.

Nếu yêu cầu Aggregator kết luận **mọi member đã có outcome**, có thể biến rejection thành **failure result** có group key và member ID, hoặc có coordinator đánh dấu lỗi toàn group. Không được tự cho `sequenceSize` giảm xuống vì thiếu message: việc đó có thể khiến một batch hỏng bị báo thành công.

**Đường lỗi không nên được xem như “một message khác không liên quan”.** Nếu cần group-level status, error handler phải có đủ identity để liên hệ lỗi với group gốc.

## 20. Group timeout và partial release phải có ngữ nghĩa rõ

Không phải group nào cũng có thể chờ vô hạn. Cần chính sách deadline:

| Chính sách | Khi phù hợp | Rủi ro |
|---|---|---|
| **Fail on timeout** | Mọi member đều bắt buộc | Caller cần error/status thay vì chờ mãi |
| **Partial release** | Kết quả một phần được nghiệp vụ chấp nhận | Dễ bị coi nhầm là thành công đầy đủ |
| **Quarantine group** | Cần điều tra thủ công và replay | Tốn storage, phải có ownership |
| **Late-result correction** | Kết quả có thể cập nhật về sau | Cần versioned output/idempotency |
| **Cancel remaining work** | Khi một lỗi làm toàn group vô nghĩa | Cancel không bảo đảm tác vụ đã phát chưa tạo side effect |

Spring Integration có các khả năng liên quan **group timeout, expiry và partial result**, nhưng cấu hình cụ thể phụ thuộc AggregatorSpec/MessageGroupStore/version. Khi bật release một phần, output phải có trạng thái như `PARTIAL`, số member nhận được và danh sách còn thiếu, không được trả `COMPLETED` chỉ vì đã hết thời gian.

Một bảng status của group có thể chứa:

~~~text
groupKey        = t:tenant-a|g:PG-901|v:7
expectedLineIds = [L1, L2, L3]
receivedLineIds = [L1, L3]
missingLineIds  = [L2]
deadline        = 2026-11-21T12:00:00Z
state           = WAITING
~~~

**Deadline phải được chốt cho logical work**, tránh tính lại mỗi lần retry làm kéo dài vô hạn thời gian nhóm được phép chờ.

## 21. MessageGroupStore: dữ liệu nhóm phải sống được bao lâu?

Aggregator có thể dùng `MessageGroupStore` để lưu messages trong từng group và metadata của group. Cần phân biệt **in-memory** và **persistent**:

| Thuộc tính | In-memory store | Persistent/shared store |
|---|---|---|
| Đơn giản, độ trễ thấp | Thường tốt | Phụ thuộc backend |
| Survive process restart | Không tự bảo đảm | Có thể, nếu cấu hình đúng |
| Nhiều instance cùng thao tác group | Không chia sẻ tự nhiên | Cần coordination/locking |
| Memory pressure | Có thể tăng theo incomplete groups | Dùng storage khác nhưng vẫn có chi phí |
| Dedupe/business completion | Không tự có | Vẫn cần business-level idempotency |
| Xóa group sau expiry | Cần cấu hình | Cần cấu hình và kiểm thử cleanup |

**Persistent store không sửa được correlation key sai.** Nó có thể khiến lỗi tồn tại **lâu hơn** và ảnh hưởng cả những message sau restart. Nếu tên group bị collision qua tenant/revision, dữ liệu không đáng lẽ gặp nhau vẫn có thể được lưu chung.

Trong multi-node, phải xem cách framework thực hiện **group locking, atomic update, transaction và release**; không giả định việc dùng chung một database tự động khiến hai Aggregator instance an toàn khi cùng cập nhật một group. Có thể cần cấu hình lock registry hoặc phân vùng quyền xử lý theo group key.

Ngoài ra, kiểm soát retention: group chờ mãi vì thiếu member có thể chiếm storage vô thời hạn nếu không có timeout, expired-group handling và cleanup.

## 22. Thay đổi correlation strategy khi đã có group tồn tại

Đây là một thay đổi schema/state, không chỉ là refactor code.

Giả sử phiên bản cũ dùng:

~~~text
key = orderId
      → O-101
~~~

Phiên bản mới dùng:

~~~text
key = tenantId + processingGroupId + revision
      → t:tenant-a|g:PG-901|v:7
~~~

Nếu MessageGroupStore vẫn có group cũ `O-101`, các message sau deploy có thể rơi vào group mới, còn group cũ chờ vĩnh viễn. Tệ hơn, một số node chạy code cũ và node khác chạy code mới có thể gom dữ liệu vào **hai nhóm khác nhau** trong cùng thời điểm.

Quy trình migrate hợp lý:

1. Kiểm kê phiên bản correlation strategy đang chạy.
2. Xác định group cũ còn pending và quy tắc hoàn tất/thất bại của chúng.
3. Drain hoặc migrate state theo manifest có kiểm tra tenant/revision; không đổi khóa hàng loạt dựa trên phỏng đoán.
4. Tạo cơ chế versioned key và giới hạn rollout/cutover.
5. Theo dõi hai phiên bản và mọi mismatch qua canary.
6. Chỉ xóa dữ liệu cũ khi đã có điều kiện an toàn và audit.

Không thay đổi thuật toán key giữa chừng rồi kỳ vọng Aggregator tự nhận ra hai string khác nhau là một group. Với workflow dài, có thể cần **version pinning** cho những message phát trước thời điểm cutover.

## 23. Header mapping qua broker và nhiều JVM

Khi message đi qua Kafka, AMQP, HTTP hoặc file:

- Một số header Spring là object nội bộ và **không nên serialize tùy ý** như `replyChannel`.
- `correlationId` có thể là UUID/String tùy tầng mapping; khi đổi type, cần chuẩn hóa cùng một format.
- `sequenceNumber` hoặc `sequenceSize` có thể bị thiếu hoặc không có semantics chính xác sau restart.
- Message có thể được **redeliver**, đảo thứ tự hoặc nhận từ nhiều partition.
- Tracing header không thay thế một business group key.

Một contract trên wire:

~~~json
{
  "tenantId": "tenant-a",
  "orderId": "O-101",
  "processingGroupId": "PG-901",
  "revision": 7,
  "lineId": "L2",
  "expectedLines": 3,
  "success": true,
  "reasonCode": null
}
~~~

Đây là dữ liệu ứng dụng rõ ràng, có thể version/schema validate ở consumer. Không vì có `processingGroupId` trong payload mà bỏ qua kiểm tra **nguồn đã xác thực, tenant scope, manifest membership** và idempotency.

**Không ghép message theo partition offset hoặc thứ tự đến.** Offset xác định vị trí trong log của một partition, không nói hai result thuộc cùng logical batch. Khi dữ liệu được xử lý song song, những item cùng group có thể hoàn tất sai thứ tự.

## 24. Lỗi của correlation strategy phải đi vào error path

Một strategy có thể gặp:

- `processingGroupId=null`;
- `tenantId` sai format;
- `revision=0`;
- payload sai kiểu (String thay vì LineOutcome);
- manifest không tìm thấy;
- message thuộc phiên bản schema chưa hỗ trợ.

**Không trả một key chung như `"UNKNOWN"` cho tất cả message lỗi.** Làm vậy biến những message không cùng nghiệp vụ thành **một super-group**, có thể gây rò dữ liệu hoặc release sai khi số lượng đủ.

~~~mermaid
flowchart TD
    IN["LineOutcome incoming"] --> V{"Validate identity + manifest"}
    V -->|"Sai"| ERR["Error channel / quarantine"]
    V -->|"Đúng"| KEY["Compute stable group key"]
    KEY --> AG["Aggregator"]
    AG --> REL{"Release strategy"}
    REL -->|"Đủ"| OUT["OrderSummary"]
    REL -->|"Chưa"| WAIT["Persist and wait"]
~~~

Phân biệt:

| Lỗi | Có nên retry tự động? | Gợi ý xử lý |
|---|---|---|
| ID thiếu hoặc sai schema | Thường **không** | Reject, DLQ/quarantine có reason |
| Không tìm thấy manifest do eventual consistency | Có thể retry ngắn nếu contract cho phép | Bounded backoff, deadline |
| Group key sai tenant | Không nên retry như lỗi mạng | Security incident/quarantine |
| Message store tạm mất kết nối | Có thể | Retry có giới hạn, bảo toàn ack |
| Group chứa metadata mâu thuẫn | Không tự đếm tiếp | Error/corruption alert, reconcile |
| Duplicate đã được xác nhận | Không cần xử lý lại | Dedupe/ack theo policy |

Error channel được chọn theo **adapter/channel/poller và error handler** cụ thể. Một exception trong synchronous DirectChannel có thể truyền về caller; ở executor/broker có thể xảy ra sau lúc publisher gửi và phải xử lý ở ranh giới async. Đừng coi `send() == true` là chứng minh group đã đúng.

## 25. Kiểm thử unit: các khóa phải ổn định và cách ly

Test `StableGroupKey` trước khi khởi động Spring context:

~~~java
@Test
void sameLogicalWorkUsesSameKeyAcrossRetries() {
    String first = StableGroupKey.of(
        "tenant-a", "PG-901", 7);
    String retry = StableGroupKey.of(
        "tenant-a", "PG-901", 7);

    assertEquals(first, retry);
}

@Test
void revisionAndTenantNeverShareTheSameGroup() {
    String base = StableGroupKey.of(
        "tenant-a", "PG-901", 7);
    String newRevision = StableGroupKey.of(
        "tenant-a", "PG-901", 8);
    String otherTenant = StableGroupKey.of(
        "tenant-b", "PG-901", 7);

    assertNotEquals(base, newRevision);
    assertNotEquals(base, otherTenant);
    assertNotEquals(newRevision, otherTenant);
}

@Test
void rejectsMalformedCorrelationScope() {
    assertThrows(IllegalArgumentException.class,
        () -> StableGroupKey.of("tenant|other", "PG-901", 7));
    assertThrows(IllegalArgumentException.class,
        () -> StableGroupKey.of("tenant-a", null, 7));
}
~~~

Tiếp theo, kiểm thử release strategy bằng một `SimpleMessageGroup` hoặc test fixture do framework version hỗ trợ. Test quan trọng:

| Input group | Kỳ vọng |
|---|---|
| L1, L2 | Chưa release, expected=3 |
| L1, L2, L3 | Release khi identity/manifest đều đúng |
| L1, duplicate L1, L2 | Chưa release dù có 3 message |
| L1, L2, line lạ L99 | Không release nếu manifest yêu cầu L3 |
| L1 rev7, L2 rev8 | Không thuộc cùng key; không được ghép |
| L1 tenant A, L2 tenant B | Không cùng key |
| Hai result L1 mâu thuẫn | Conflict, không âm thầm chọn một |
| `expectedLines=2` và `3` trong cùng group | Lỗi metadata, không release |

Nếu chỉ dùng release strategy minh họa ở mục 11, test `L99` có thể phơi bày hạn chế: **đủ ba distinct IDs nhưng sai manifest**. Hãy bổ sung membership validation trước khi dùng trong production.

## 26. Integration test: interleave hai revision, không được trộn

Trong Spring test context, gắn Aggregator ở mục 10 vào `orders.line.results`, dùng `QueueChannel` cho `orders.completed` (test-only) và có thể dùng MessageGroupStore in-memory riêng để không giữ trạng thái giữa các test.

Kịch bản:

~~~text
Gửi message theo thứ tự:
  rev7/L1
  rev8/L1
  rev7/L2
  rev8/L2
  rev8/L4
  rev7/L3

Kỳ vọng:
  Summary rev8 chứa đúng [L1,L2,L4]
  Summary rev7 chứa đúng [L1,L2,L3]
  Không có summary chứa members của cả hai revision
~~~

Một ví dụ phần thân test:

~~~java
@Autowired
ApplicationContext context;

@Test
void separatesTwoRevisionsOfSameOrder() {
    MessageChannel input = context.getBean(
        "orders.line.results", MessageChannel.class);
    PollableChannel output = context.getBean(
        "orders.completed", PollableChannel.class);

    send(input, outcome("PG-901", 7, "L1", 3));
    send(input, outcome("PG-901", 8, "L1", 3));
    send(input, outcome("PG-901", 7, "L2", 3));
    send(input, outcome("PG-901", 8, "L2", 3));
    send(input, outcome("PG-901", 8, "L4", 3));
    send(input, outcome("PG-901", 7, "L3", 3));

    OrderSummary first =
        (OrderSummary) Objects.requireNonNull(
            output.receive(1_000)).getPayload();
    OrderSummary second =
        (OrderSummary) Objects.requireNonNull(
            output.receive(1_000)).getPayload();

    assertEquals(Set.of(7, 8),
        Set.of(first.revision(), second.revision()));
    assertEquals("PG-901", first.processingGroupId());
    assertEquals("PG-901", second.processingGroupId());
    assertEquals(3, first.expectedLines());
    assertEquals(3, second.expectedLines());
}

private void send(MessageChannel input, LineOutcome result) {
    assertTrue(input.send(new GenericMessage<>(result)));
}

private LineOutcome outcome(
        String groupId, int revision,
        String lineId, int expected) {
    return new LineOutcome(
        "tenant-a", "O-101", groupId,
        revision, lineId, expected, true, null);
}
~~~

**Đây là code kiểm thử định hướng**, cần đặt các method trong test class và thêm import/config test. Test chỉ chứng minh hai summary có revision khác nhau và expectedCount đúng; để kiểm chứng sâu nội dung group, hãy cho `OrderSummary` mang set line IDs hoặc kiểm tra audit/spy của `OrderSummaryProcessor`. Không dùng số lượng output làm bằng chứng duy nhất rằng group không bị trộn.

Đối với flow bất đồng bộ, thứ tự hai summary có thể đảo: assert tập các revision và **đúng member set**, không giả định rev7 luôn hoàn tất trước rev8.

## 27. Ma trận kiểm thử end-to-end: lỗi khó phát hiện

| Case | Cách mô phỏng | Điều phải chứng minh |
|---|---|---|
| Happy path | Ba line cùng group | Một summary đúng member set |
| Interleaved revisions | Hai revision cùng order xen kẽ | Hai summary tách biệt |
| Cross-tenant collision | Cùng group ID ở hai tenant | Không gom chung |
| Retry same logical work | Redeliver L2 với cùng group key | Không tạo summary sai do duplicate |
| Retry with new Spring Message ID | Tái tạo GenericMessage chứa cùng payload identity | Vẫn cùng business group |
| Fresh UUID per child (phản ví dụ) | Cố tạo group ID trong worker | Test phát hiện group phân mảnh |
| Missing correlation | Xóa processingGroupId | Rejection, không key `UNKNOWN` |
| Case/type normalization | Uppercase/lowercase, UUID vs String | Hợp đồng canonical được áp dụng nhất quán |
| Manifest mismatch | Có L99 thay cho L3 | Không release |
| Conflicting duplicate | L1 success và L1 failure | Báo conflict/reconciliation |
| One child dropped | Filter loại L2 | Timeout/failure result, không complete sai |
| Late reply after completion | Gửi duplicate sau release | Không phát summary mới ngoài policy |
| Restart with pending | Persistent store + restart | Khôi phục group đúng theo guarantee |
| Two nodes race to aggregate | Cùng group đến hai instance | Không double-release do lock/transaction |
| Router/Transformer đổi payload | Một nhánh sửa header | Business group identity vẫn giữ |
| Gateway timeout | Một member rất chậm | Caller timeout không đồng nghĩa group chưa commit |
| Correlation strategy upgrade | Mixed old/new key format | Migration/cutover có kiểm soát |

**Đặc biệt:** test redelivery nên tạo **một Spring Message mới với cùng business group identity** để lộ sai lầm khi dùng framework-generated message ID. Test concurrency cần dùng latch/barrier và timeout hữu hạn, không dựa vào `Thread.sleep` để suy thứ tự.

## 28. Observability: nhìn thấy dấu hiệu gom nhầm group

Nên theo dõi ba tầng: **input identity → group state → released output**.

| Tín hiệu | Dấu hiệu cần chú ý |
|---|---|
| `aggregator.group.created.count` | Số group đột tăng do key thay đổi theo message |
| `aggregator.group.pending.count` | Nhiều group không đủ member |
| `aggregator.group.age` | Group chờ quá lâu dù worker đã xử lý |
| `aggregator.group.member.count` | Số message trong group khác số member distinct |
| `aggregator.group.duplicate.count` | Retry và duplicate đang tăng |
| `aggregator.group.identity.mismatch.count` | Cùng group nhưng metadata không nhất quán |
| `aggregator.group.expired.count` | Nhiều group timeout hoặc cleanup |
| `aggregator.group.late.count` | Reply tới sau completion |
| `aggregator.release.count` theo outcome | Summary thành công/partial/failed |
| `aggregator.output.duplicate.count` | Group bị release lặp hoặc downstream redelivery |
| `message.store.size` | Storage growth do pending groups |

Các tên này là **metric đề xuất**, không phải lời khẳng định về meter mặc định của Spring Integration. Khi dùng Micrometer/observation, chỉ dùng nhãn có cardinality thấp như `flowName`, `outcome`, `reasonCode`; **không đưa group key, orderId hay tenantId động vào metric tags không giới hạn**.

Để điều tra một group cụ thể, structured logs/tracing có thể lưu:

~~~text
eventId=EV-201
groupKey=t:tenant-a|g:PG-901|v:7
memberId=L2
originalMessageId=<local messaging id>
attempt=2
expected=3
distinctReceived=2
groupState=WAITING
~~~

Những giá trị trên thuộc **log/tracing với quyền truy cập kiểm soát**, không phải nhãn metric phổ thông. Nếu ID có PII hoặc thông tin nhạy cảm, dùng hashing/alias và retention phù hợp.

## 29. Runbook khi phát hiện summary sai

Nếu khách hàng báo kết quả tổng hợp chứa dữ liệu của hai revision khác nhau:

1. **Khoanh vùng:** xác định `tenantId/orderId/operation/processingGroupId/revision` của summary sai.
2. **Dừng phát kết quả không đáng tin:** cân nhắc chặn output/canary theo phạm vi, tránh rollback bừa bãi mọi flow.
3. **Truy vết group key:** tìm các member message đã đi vào group và thuật toán key dùng tại thời điểm đó.
4. **So với manifest:** kiểm tra member IDs, expectedCount, tenant, revision, duplicate và missing outcomes.
5. **Xác minh store/expiry:** group đã được tạo khi nào, còn tồn tại không, late arrivals có tạo lại group không?
6. **Xem deployment/version:** các instance có đang chạy các phiên bản correlation strategy khác nhau không?
7. **Xác định side effect:** summary sai đã khiến Gateway, DB, broker hoặc downstream thực hiện hành động nào?
8. **Khắc phục:** cập nhật correlation strategy, test migration, xử lý bù trừ/rebuild summary theo manifest được xác minh.
9. **Chặn tái diễn:** thêm test interleaved revisions, cross-tenant, retries, late arrivals và duplicate results.

Không đơn giản “xóa hết groups rồi restart” nếu chưa biết trạng thái business đã commit; cách đó có thể làm message bị xử lý lại và khiến dữ liệu sai nghiêm trọng hơn.

## 30. Bài thực hành: chứng minh không thể gom nhầm hai group

Xây ứng dụng **OrderOutcomeAggregator**:

1. **Input:** tạo hai `OrderWork` cùng `orderId=O-101` nhưng khác `revision`, và một đơn khác tenant có cùng mã order.
2. **Coordinator:** cấp `processingGroupId` một lần cho mỗi logical work, lưu expected line IDs.
3. **Splitter:** phát `LineWork` chứa `tenantId/processingGroupId/revision/lineId/expectedLines`.
4. **Workers:** chuyển thành `LineOutcome` với success hoặc failure reason, giữ nguyên identity.
5. **Aggregator:** correlation strategy dùng `StableGroupKey`, release khi đủ **tập member IDs** theo manifest, output processor tạo summary.
6. **Interleave:** gửi kết quả của hai revision và hai tenant xen kẽ; xác minh không có group bị trộn.
7. **Retry:** phát lại một LineOutcome dưới Spring message ID khác; không làm đủ giả số lượng member.
8. **Error:** cho một worker fail trước reply; tạo failure result hoặc group timeout có chính sách.
9. **Late arrival:** gửi duplicate sau completion, kiểm tra tombstone/idempotency/output không bị nhân đôi.
10. **Persistence:** nếu sử dụng store bền vững, thử restart khi group đang pending và thử hai node cập nhật cùng group.
11. **Telemetry:** đo pending groups, group age, duplicate, identity mismatch, expiry và release outcome.
12. **Migration:** mô phỏng thay từ correlation theo orderId sang composite key; xác minh không có group cũ bị bỏ mặc.

**Tiêu chí hoàn thành:** mỗi summary chỉ chứa member thuộc đúng tenant, operation, processingGroupId và revision; retry cùng logical work dùng chung group identity; count-based release không bị duplicate đánh lừa; group thiếu/trễ có trạng thái rõ; không tạo output trùng do expiry/restart; error channel và correlation có thể được truy vết từ đầu đến cuối.

## 31. Những sai lầm thường gặp

**“Dùng orderId là đủ vì orderId duy nhất.”** Chưa chắc. Cùng order có thể có nhiều revision/operation và nhiều tenant có thể tái sử dụng mã.

**“correlationId là MessageHeaders.ID nên luôn ổn định.”** Không. Đây là hai khái niệm khác nhau; framework message ID có thể được tạo lại.

**“Mỗi worker tự sinh UUID làm group ID càng an toàn.”** Sai. Cùng logical batch sẽ bị phân thành nhiều group nếu mỗi worker sinh key khác.

**“sequenceSize=3 và group.size()=3 nghĩa là đủ ba line.”** Sai khi có duplicate hoặc member lạ. Cần unique member IDs và manifest.

**“Một key chung UNKNOWN cho mọi message thiếu ID giúp đỡ mất dữ liệu.”** Sai, nó có thể trộn các message không liên quan thành super-group.

**“Persistent MessageGroupStore sẽ tự khắc phục collision.”** Sai. Nó chỉ lưu/điều phối trạng thái, không tự hiểu nghiệp vụ hay sửa key sai.

**“Đổi correlation strategy khi deploy không ảnh hưởng group cũ.”** Sai. Đây là thay đổi identity có thể cần migration/draining.

**“Group release xong thì không thể có reply trễ.”** Sai. Broker redelivery và worker chạy chậm có thể gửi tiếp; cần late-arrival policy.

**“Nếu group đúng key, không cần kiểm tra tenant.”** Sai. Key có thể bị giả mạo hoặc được tính từ metadata không đáng tin.

**“Một summary được publish nghĩa là toàn bộ side effect đã exactly-once.”** Sai. Business idempotency, transaction, outbox và downstream recovery là việc riêng.

**“Bật group timeout thì mọi case thiếu member trở thành thành công.”** Sai. Timeout phải có outcome `FAILED/PARTIAL/EXPIRED` được nghiệp vụ chấp nhận.

## 32. Ghi nhớ

**Correlation không ổn định gây gom nhầm group** theo hai hướng: **khóa thay đổi** làm cùng logical work bị chia thành nhiều group không hoàn tất; **khóa quá thô hoặc collision** làm message của các work khác nhau bị ghép chung và release sai. Lỗi thứ hai đặc biệt khó phát hiện vì Aggregator vẫn có thể tạo output đúng kiểu nhưng sai dữ liệu.

Trong Spring Integration, hãy cấp **group identity ổn định tại nguồn**, giữ nó qua **Splitter → Transformer/Filter/Router → worker → Aggregator**, dùng **correlation strategy có phạm vi tenant/revision/operation**, và kết hợp **release strategy kiểm tra distinct member IDs so với manifest**. Bổ sung timeout, completion tombstone, deduplication, MessageGroupStore, transaction và observability phù hợp với ranh giới broker/restart.

**Một khóa đúng giúp tìm đúng group; một release strategy đúng giúp kết luận đúng thời điểm; một output processor và idempotency đúng giúp tạo đúng kết quả.** Cần cả ba để xử lý message flow có retry, error channel, concurrency và correlation thực tế.

### Tài liệu tham khảo

- Spring Integration Reference, **Aggregator**: https://docs.spring.io/spring-integration/reference/aggregator.html
- Spring Integration Reference, **Splitter**: https://docs.spring.io/spring-integration/reference/splitter.html
- Spring Integration Reference, **Message Store**: https://docs.spring.io/spring-integration/reference/message-store.html
- Enterprise Integration Patterns, **Correlation Identifier**: https://www.enterpriseintegrationpatterns.com/patterns/messaging/CorrelationIdentifier.html
- Enterprise Integration Patterns, **Aggregator**: https://www.enterpriseintegrationpatterns.com/patterns/messaging/Aggregator.html
