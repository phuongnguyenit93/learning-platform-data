# Truyền correlation ID qua nhiều endpoint

## 1. Bài toán: một đơn hàng đi qua nhiều endpoint nhưng kết quả phải về đúng nhóm

Một hệ thống nhận `OrderSubmitted` rồi qua nhiều bước:

1. Gateway hoặc HTTP inbound adapter nhận message.
2. Filter kiểm tra dữ liệu đầu vào.
3. Router phân nhánh theo loại đơn hàng.
4. Transformer chuẩn hóa payload thành `OrderWork`.
5. Splitter tạo nhiều `LineWork` để xử lý song song.
6. Các worker gọi Inventory/Pricing và trả `LineResult`.
7. Aggregator gom những kết quả của **đúng một lần xử lý đơn hàng**.
8. Gateway hoặc outbound adapter trả/publish kết quả cuối.

~~~mermaid
flowchart LR
    IN["OrderSubmitted"] --> GW["Gateway / inbound"]
    GW --> V["Filter"]
    V --> R["Router"]
    R --> T["Transformer"]
    T --> S["Splitter"]
    S --> W["Workers"]
    W --> A["Aggregator"]
    A --> OUT["OrderSummary / outbound"]
~~~

Ví dụ hai đơn cùng được gửi:

~~~text
Tenant A / Order O-101 / Revision 3 / Event EV-1
Tenant A / Order O-102 / Revision 1 / Event EV-2

Các message con của hai đơn có thể đến xen kẽ:
  O-101/L2, O-102/L1, O-101/L1, O-102/L2, ...
~~~

Nếu một endpoint làm mất thông tin correlation, hoặc một worker cấp UUID mới cho từng reply, Aggregator không biết kết quả nào thuộc **cùng nhóm**. Nếu key quá thô như `customerId`, nó có thể **gom nhầm hai đơn**. Nếu key là `MessageHeaders.ID` của từng message con, mỗi message có ID khác nhau và nhóm sẽ bị phân mảnh.

**Truyền correlation ID qua nhiều endpoint** nghĩa là duy trì một identity có ngữ nghĩa rõ ràng, cùng định dạng và cùng phạm vi, từ ingress tới các nhánh, các message mới, ranh giới bất đồng bộ, reply và aggregation. Bài không chỉ nói đến việc sao chép một header: **Content-based correlation** còn yêu cầu có thể **suy ra hoặc kiểm tra group key từ chính nội dung nghiệp vụ**, đặc biệt khi header bị đổi/loại bởi transport.

Bài thuộc chương **Content-based correlation** của module **SPRING_INTEGRATION_PATTERN**, phục vụ lộ trình học triển khai Enterprise Integration Patterns bằng Spring Integration để xây dựng message flow ít phụ thuộc và dễ mở rộng. Các ví dụ kết hợp **Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation**, đi kèm kiểm thử và observability.

**Kết quả học tập:** xác định đúng group identity; phân biệt các loại ID; bảo toàn correlation qua endpoint; thiết kế hợp đồng payload/header cho broker; viết custom correlation strategy cho Aggregator; kiểm thử concurrency, retry, duplicate và error path.

## 2. Correlation ID không đồng nghĩa Spring Message ID

Một message có nhiều loại định danh, mỗi loại phục vụ một mục đích:

| Định danh | Ý nghĩa | Có nên làm business group key xuyên endpoint? |
|---|---|---|
| `MessageHeaders.ID` | ID do Spring Messaging cấp cho **message object** | Không: message mới/replay có thể đổi ID |
| `MessageHeaders.TIMESTAMP` | Thời điểm tạo message theo framework | Không: không xác định cùng logical work |
| `correlationId` | Header correlation do flow/endpoint dùng, đặc biệt Splitter/Aggregator | Dùng được khi semantics và propagation đã kiểm soát |
| `sequenceNumber` | Vị trí của message trong một sequence | Không: nhiều group đều có member #1 |
| `sequenceSize` | Số member dự kiến, khi biết được | Không: kích thước không phải identity |
| `eventId` | Sự kiện do producer cấp | Có thể là một phần identity, nhưng một event sinh nhiều operation |
| `orderId` | Đơn hàng nghiệp vụ | Không đủ nếu có nhiều revision/operation |
| `businessCorrelationId` | ID của **logical processing group** do ứng dụng định nghĩa | Phù hợp nếu ổn định và có scope rõ |
| `traceId`/`spanId` | Distributed tracing để quan sát | Không: trace không phải business group |
| `replyChannel`/`errorChannel` | Channel phục vụ trả lời và lỗi trong messaging | Không: đây không phải business ID |

Trong Spring Integration, nhiều component hiểu các header chuẩn như `IntegrationMessageHeaderAccessor.CORRELATION_ID`, `SEQUENCE_NUMBER` và `SEQUENCE_SIZE`. Nhưng ứng dụng cũng có thể cần một header riêng như `businessCorrelationId` để **không đè lên sequence/correlation metadata của Splitter**.

**Quy tắc:** không lấy một ID có vòng đời ngắn hơn logical work làm khóa nhóm dài hạn. Một UUID chỉ ổn định nếu nó được **cấp một lần và bảo toàn**, không phải vì cú pháp UUID tự đảm bảo correlation.

## 3. Content-based correlation là gì?

**Content-based correlation** xác định quan hệ giữa các message dựa trên **các trường nghiệp vụ trong payload**, có thể kết hợp với metadata đáng tin cậy, thay vì tin rằng một header kỹ thuật luôn còn nguyên.

Ví dụ hai message:

~~~json
{
  "tenantId": "tenant-a",
  "orderId": "O-101",
  "revision": 3,
  "eventId": "EV-1",
  "lineId": "L-1"
}
~~~

~~~json
{
  "tenantId": "tenant-a",
  "orderId": "O-101",
  "revision": 3,
  "eventId": "EV-1",
  "lineId": "L-2"
}
~~~

Hai payload khác nhau ở `lineId` nhưng cùng một **logical processing group** nếu quy tắc nghiệp vụ xác định group theo `tenantId + orderId + revision + operation`.

\[
\operatorname{groupKey}(m) =
\operatorname{canonicalize}(
  m.\text{tenantId},\,
  m.\text{orderId},\,
  m.\text{revision},\,
  \text{operation}
)
\]

Không phải nội dung nào cũng thích hợp làm key:

- `customerId` có thể trùng cho nhiều order.
- `status` thay đổi theo từng endpoint.
- `totalAmount` thay đổi khi tính toán.
- `lineId` nhận diện **member**, không phải toàn group.
- Thời gian xử lý hiện tại thay đổi qua retry.

Một key tốt phải dựa vào **các trường ổn định và được định nghĩa trong contract**, không dựa vào những thuộc tính đang bị Transformer hoặc worker thay đổi.

## 4. Hai bất biến cần giữ khi truyền correlation

Một hệ thống đúng phải thỏa cả hai:

**Bất biến A — cùng logical work phải cùng key:**

\[
\operatorname{sameWork}(m_1,m_2)
\Rightarrow
\operatorname{key}(m_1)=\operatorname{key}(m_2)
\]

**Bất biến B — khác logical work không được chung key:**

\[
\neg\operatorname{sameWork}(m_1,m_2)
\Rightarrow
\operatorname{key}(m_1)\ne\operatorname{key}(m_2)
\]

| Lỗi | Biểu hiện | Hậu quả |
|---|---|---|
| Key đổi giữa các endpoint | Input dùng `EV-1`, worker dùng UUID mới | Aggregator tạo nhiều group không đủ member |
| Key quá thô | Chỉ dùng `orderId` | Hai revision/tenant/operation trộn kết quả |
| Mất key qua transport | Header bị mapper loại | Reply không tìm được group cũ |
| Biến đổi kiểu key | String `"00123"` thành integer `123` | Group bị đổi hoặc collision |
| Key lấy từ field mutable | Sử dụng trạng thái `PENDING`/`DONE` | Cùng work bị chia thành nhiều group |
| Key đến từ client không tin cậy | Client tự đặt tenant/group header | Trộn dữ liệu hoặc lộ thông tin |

**Một header tồn tại không đồng nghĩa giá trị của nó đúng.** Cần kiểm tra semantics, nguồn cấp và quan hệ với payload tại mỗi trust boundary.

## 5. Chọn identity theo phạm vi nghiệp vụ

Giả sử cùng `orderId=O-101` có hai lượt xử lý:

~~~text
tenant-a / O-101 / revision=3 / PRICE
tenant-a / O-101 / revision=4 / PRICE
tenant-a / O-101 / revision=3 / INVENTORY
tenant-b / O-101 / revision=3 / PRICE
~~~

Nếu mỗi operation cần một Aggregator riêng, bốn trường hợp trên **không được ghép chung**. Một hợp đồng khóa có thể là:

~~~text
group = tenantId | orderId | revision | operation
~~~

Hoặc coordinator cấp `processingGroupId` duy nhất cho logical operation, rồi lưu mapping tới tenant/order/revision. Khi đó một key:

~~~text
group = tenantId | processingGroupId
~~~

có thể đủ nếu **quy tắc cấp processingGroupId** đã thực sự bảo đảm tính duy nhất trong tenant và xuyên retry.

Không có lựa chọn mặc định cho mọi ngành. Hãy viết rõ “**một group là gì**” trước khi chọn header:

| Use case | Logical group | Member identity |
|---|---|---|
| Tính tổng các dòng order | Một order revision/processing run | `lineId` |
| Ghép ba kết quả của Scatter-Gather | Một quote evaluation | `branchType` |
| Tổng hợp thanh toán | Một payment batch/window | `transactionId` |
| Chờ nhiều file fragments | Một upload/session/version | `partNumber` |
| Reconcile giao dịch | Một reconciliation cycle | `recordId` |

**Group ID** và **member ID** phải tách nhau. Các message của một group có cùng group ID nhưng phải có member ID riêng nếu release strategy cần đếm thành viên phân biệt.

## 6. Mô hình domain minh họa bằng Java 17+

Trong bài này sử dụng các record:

~~~java
enum WorkOperation {
    PRICE, INVENTORY
}

record OrderLine(
    String lineId,
    String sku,
    long unitPriceCents,
    int quantity
) {}

record OrderEvent(
    String tenantId,
    String orderId,
    int revision,
    String eventId,
    WorkOperation operation,
    List<OrderLine> lines
) {}

record LineWork(
    String tenantId,
    String orderId,
    int revision,
    String eventId,
    WorkOperation operation,
    String lineId,
    String sku,
    long unitPriceCents,
    int quantity,
    int expectedLines
) {}

record LineResult(
    String tenantId,
    String orderId,
    int revision,
    String eventId,
    WorkOperation operation,
    String lineId,
    int expectedLines,
    long amountCents,
    boolean success,
    String reasonCode
) {}
~~~

Đây là **mô hình minh họa**, không phải DTO có sẵn trong Spring Integration. Các lớp được đặt theo cùng package hoặc file thích hợp khi triển khai thực tế; import được lược bỏ.

Điểm thiết kế:

- Original event, mỗi child work và mỗi reply result **đều giữ các field cần tính group key**.
- `lineId` khác nhau theo từng child để dedupe.
- `expectedLines` được lấy từ manifest đầu nguồn, không để mỗi worker tự thay đổi.
- `eventId` được giữ để trace và idempotency, nhưng **không bắt buộc** là group key nếu một event có nhiều operation.
- `operation` nằm trong group identity khi PRICE và INVENTORY có thể tạo kết quả đồng thời.

Vì key có thể được tính trực tiếp từ payload, một reply sau khi qua broker vẫn có thể được phân nhóm dù framework header `correlationId` không còn.

## 7. Xây khóa chuẩn hóa, không nối chuỗi mơ hồ

Nối trực tiếp các ID có thể collision:

~~~text
tenant="ab", order="c" → "abc"
tenant="a",  order="bc" → "abc"
~~~

Một cách đơn giản là validate ID theo whitelist ký tự và dùng delimiter không được phép xuất hiện trong ID:

~~~java
final class BusinessGroupKey {

    static String of(
            String tenantId,
            String orderId,
            int revision,
            WorkOperation operation) {
        if (tenantId == null
                || !tenantId.matches("[a-z0-9-]{1,48}")) {
            throw new IllegalArgumentException("INVALID_TENANT");
        }
        if (orderId == null
                || !orderId.matches("[A-Za-z0-9-]{1,80}")) {
            throw new IllegalArgumentException("INVALID_ORDER");
        }
        if (revision < 1 || operation == null) {
            throw new IllegalArgumentException("INVALID_SCOPE");
        }
        return "t:" + tenantId
            + "|o:" + orderId
            + "|v:" + revision
            + "|op:" + operation.name();
    }

    static String from(OrderEvent e) {
        return of(
            e.tenantId(), e.orderId(),
            e.revision(), e.operation());
    }

    static String from(LineResult r) {
        return of(
            r.tenantId(), r.orderId(),
            r.revision(), r.operation());
    }
}
~~~

Ví dụ:

~~~text
t:tenant-a|o:O-101|v:3|op:PRICE
t:tenant-a|o:O-101|v:4|op:PRICE
t:tenant-b|o:O-101|v:3|op:PRICE
~~~

**Lưu ý:** đây là một format minh họa có tính dễ đọc. Nếu business ID cho phép dấu phân cách, Unicode hoặc escape sequences, cần **format có độ dài trường/escaping rõ ràng hoặc canonical serializer**, không chỉ nối chuỗi. Không tùy tiện lower-case mọi field khi contract coi ID có phân biệt hoa/thường.

Trong distributed flow, các instance phải dùng cùng format/version key. Thay đổi thuật toán giữa lúc còn pending groups là một **migration identity**, không chỉ là refactor thông thường.

## 8. Gắn business correlation ngay tại ingress

Ngay ở adapter/gateway, nên tạo hoặc xác minh business key sau khi đã xác thực tenant và validate payload:

~~~java
OrderEvent event = new OrderEvent(
    "tenant-a",
    "O-101",
    3,
    "EV-101",
    WorkOperation.PRICE,
    orderLines);

Message<OrderEvent> original = MessageBuilder
    .withPayload(event)
    .setHeader(
        "businessCorrelationId",
        BusinessGroupKey.from(event))
    .setHeader("businessEventId", event.eventId())
    .build();
~~~

Một message có thể mang đồng thời:

~~~text
payload.orderId                 = O-101
payload.revision                = 3
headers.businessCorrelationId   = t:tenant-a|o:O-101|v:3|op:PRICE
headers.businessEventId         = EV-101
headers.id                      = <Spring-generated message ID>
~~~

**Header riêng** giúp các endpoint quan sát và route nhanh; **payload đủ identity** giúp khôi phục/kiểm tra correlation khi qua transport hoặc khi một Transformer thay đổi message. Nên tránh hai nguồn sự thật mâu thuẫn: trước khi sử dụng header từ bên ngoài, **tính lại group key từ các field đã xác minh**.

Nếu inbound producer được phép chỉ định `tenantId`, adapter phải lấy tenant thực từ credential/principal hoặc kiểm tra quyền truy cập; không lấy một header tự khai để phân quyền hoặc để gom group chéo tenant.

## 9. Spring Integration Java DSL: gắn header bằng Header Enricher

Trong một flow, có thể gắn key từ payload bằng `enrichHeaders`:

~~~java
@Configuration
@EnableIntegration
class CorrelationIngressFlow {

    @Bean
    IntegrationFlow validateAndStampCorrelation() {
        return IntegrationFlow.from("orders.in")
            .filter(OrderEvent.class, event ->
                    event != null
                        && event.lines() != null
                        && !event.lines().isEmpty()
                        && event.operation() != null,
                spec -> spec.throwExceptionOnRejection(true))
            .enrichHeaders(h -> h.headerFunction(
                "businessCorrelationId",
                message -> BusinessGroupKey.from(
                    (OrderEvent) message.getPayload())))
            .channel("orders.correlated")
            .get();
    }
}
~~~

Đoạn code minh họa Java DSL, import được lược bỏ. Cần bổ sung kiểm tra `tenantId`, `orderId`, revision, line IDs và authorization theo domain. Hợp đồng nên phân biệt rõ **input thiếu field** và **input bị làm giả**; Filter chỉ ngăn flow đi tiếp, không tự bảo đảm mọi identity đã đáng tin.

**Quan trọng về overwrite:** nếu `businessCorrelationId` đã tồn tại trên inbound message, chính sách nên là **tính lại và so khớp/reject khi mismatch** hoặc **ghi đè từ nguồn xác thực**, chứ không lặng lẽ giữ giá trị client tự gửi. Semantics mặc định của Header Enricher khi header đã tồn tại có thể phụ thuộc cấu hình overwrite; phải kiểm thử phiên bản Spring Integration đang dùng.

**Không dùng** `headerFunction("correlationId", ...)` một cách máy móc trong flow có Splitter/Aggregator đang dùng header correlation chuẩn. Một endpoint có thể cần `correlationId` riêng cho sequence của nó; hãy giữ business key tách biệt.

## 10. Truyền qua Filter: message bị loại không tự có reply

Filter có thể là điểm đầu tiên khiến chuỗi correlation bị đứt về mặt **nghiệp vụ**, dù header không đổi:

~~~text
OrderEvent O-101
  → Filter.validate
  → ACCEPT: message đi tiếp, businessCorrelationId giữ nguyên
  → REJECT: không có LineResult nếu không thiết kế error outcome
~~~

Nếu Filter loại toàn bộ order trước Splitter, có thể gửi một `OrderRejected` chứa `businessCorrelationId` và lý do. Nếu Filter loại **một message con** sau Splitter, Aggregator có thể chờ thiếu member.

Hai chính sách:

1. **Fail-fast trước split:** reject cả request, không tạo pending group.
2. **Per-member outcome:** chuyển lỗi thành `LineResult(success=false, reasonCode=...)` mang **cùng group key/member ID**, để Aggregator biết member đã có kết luận.

Không tự giảm `sequenceSize` hoặc `expectedLines` chỉ vì một child bị Filter discard. Làm vậy có thể gây release sai: group thiếu một dòng nhưng vẫn được báo hoàn tất.

Khi rejection xảy ra trên đường đồng bộ, exception có thể lan về Gateway. Khi đi qua ExecutorChannel/broker, lỗi phải được xử lý ở đúng **async error boundary** với đủ correlation context.

## 11. Truyền qua Router: phân nhánh nhưng không đổi identity

Content Based Router quyết định channel dựa trên payload hoặc header:

~~~text
operation=PRICE     → price.requests
operation=INVENTORY → inventory.requests
~~~

**Routing key** và **correlation key** có nhiệm vụ khác nhau:

- Router chọn **ai xử lý** một message.
- Correlation xác định **message thuộc lượt xử lý/group nào**.

Nếu một `OrderEvent` được route sang Pricing, nó vẫn thuộc logical group như trước Router. Chỉ vì channel là `price.requests` không có nghĩa phải tạo correlation ID mới.

Một lỗi thường gặp là dùng:

~~~text
correlationId = currentChannelName
~~~

Khi đó mọi đơn qua Pricing có thể vào cùng group `price.requests`. Đó là **route label**, không phải business identity.

Nếu Router fork thành nhiều branch trong một scatter-style flow, từng branch có thể cần `branchId` riêng nhưng vẫn phải liên kết với **parent requestId/businessCorrelationId**. Correlation của **gather group** khác correlation của **line-level Splitter**; cần có manifest về các branch dự kiến.

## 12. Truyền qua Transformer: payload đổi nhưng group identity không được biến mất

Transformer có thể chuyển:

~~~text
OrderEvent → OrderWork → LineWork → LineResult
~~~

Mỗi DTO có kiểu khác nhau. Nếu correlation chỉ có trong payload cũ và Transformer không chuyển các field identity, downstream sẽ mất khả năng content-based correlation.

Ví dụ một Transformer nhận `LineWork` và trả `LineResult`:

~~~java
@MessageEndpoint
class PriceCalculator {

    @Transformer(
        inputChannel = "price.requests",
        outputChannel = "price.results")
    public LineResult price(LineWork work) {
        long amount = Math.multiplyExact(
            work.unitPriceCents(),
            work.quantity());

        return new LineResult(
            work.tenantId(),
            work.orderId(),
            work.revision(),
            work.eventId(),
            work.operation(),
            work.lineId(),
            work.expectedLines(),
            amount,
            true,
            null);
    }
}
~~~

**Key không đổi:** trước và sau Transformer có thể tính cùng một `BusinessGroupKey` từ payload, dù các field tính toán như `amountCents` thay đổi.

Spring Integration thường có cơ chế chuyển/giữ một số request headers khi endpoint tạo reply từ payload, nhưng **không nên suy diễn tất cả headers luôn được bảo toàn** khi có custom MessageBuilder, adapter, reply service hoặc wire mapper. Hãy test end-to-end và giữ identity cần thiết trong **contract payload** nếu nó phải vượt qua ranh giới hệ thống.

## 13. Transformer tự tạo Message mới: copy có chọn lọc

Một custom Transformer có thể tạo hẳn một `Message<?>` mới. Nếu chỉ gọi:

~~~java
MessageBuilder.withPayload(converted).build();
~~~

thì business header cũ **không được ứng dụng copy một cách tường minh**. Một số thành phần framework có thể áp dụng header propagation khi gửi reply, nhưng không nên đặt toàn bộ tính đúng đắn vào giả định đó, đặc biệt khi output rời Spring Integration.

Một ví dụ chủ động gắn header từ payload đích:

~~~java
Message<LineResult> buildResultMessage(LineResult result) {
    String key = BusinessGroupKey.from(result);
    return MessageBuilder.withPayload(result)
        .setHeader("businessCorrelationId", key)
        .setHeader("businessEventId", result.eventId())
        .build();
}
~~~

Ví dụ này **không copy mọi header**, vì các header như `replyChannel`, `errorChannel`, authentication hoặc cookie có semantics/độ tin cậy riêng. Trong JVM, có thể dùng các helper của MessageBuilder để copy headers **được phép**, nhưng phải xác định overwrite policy và trust boundary.

Đặc biệt không tự ghi đè `IntegrationMessageHeaderAccessor.CORRELATION_ID` nếu các endpoints cuối đang sử dụng nó để gom sequence của Splitter. Tách `businessCorrelationId` giúp trách nhiệm rõ ràng.

## 14. Splitter: một original thành nhiều child nhưng vẫn cùng business group

Một Splitter chuyển `OrderEvent` thành các `LineWork`:

~~~java
@MessageEndpoint
class OrderLineSplitter {

    @Splitter(
        inputChannel = "orders.correlated",
        outputChannel = "orders.lines")
    public List<LineWork> split(OrderEvent event) {
        if (event.lines() == null || event.lines().isEmpty()) {
            throw new IllegalArgumentException("EMPTY_LINES");
        }

        int expected = event.lines().size();
        return event.lines().stream()
            .map(line -> new LineWork(
                event.tenantId(),
                event.orderId(),
                event.revision(),
                event.eventId(),
                event.operation(),
                line.lineId(),
                line.sku(),
                line.unitPriceCents(),
                line.quantity(),
                expected))
            .toList();
    }
}
~~~

Hai lớp metadata có thể cùng tồn tại:

~~~text
Message child L1:
  payload.tenantId/orderId/revision/operation → business group identity
  headers.businessCorrelationId              → custom application key
  headers.correlationId                       → framework sequence group
  headers.sequenceNumber                      → 1
  headers.sequenceSize                        → 3

Message child L2:
  cùng business group identity
  sequenceNumber=2, sequenceSize=3
~~~

Spring Integration Splitter có thể cấp correlation/sequence headers (ví dụ theo message gốc) khi cấu hình phù hợp. **Không bảo đảm** mọi loại `Iterator` hay `Stream` có sequenceSize đã biết, và không được giả định các sequence headers là business IDs bền vững xuyên retry/replay.

**Giữ key ở hai cấp:** payload chứa identity nghiệp vụ; header chuẩn phục vụ Splitter/Resequencer/Aggregator ở topology đã được kiểm thử. Nếu nested Splitter, còn cần phân biệt **outer batch group** và **inner line group**.

## 15. Qua Gateway: replyChannel và businessCorrelationId không cùng mục đích

Một Gateway có thể tạo request message và quản lý `replyChannel` để đưa **reply về đúng lời gọi đang chờ**:

~~~java
@MessagingGateway(defaultRequestChannel = "orders.in")
interface OrderGateway {
    OrderSummary submit(OrderEvent event);
}
~~~

**Không trộn lẫn hai cơ chế:**

- `replyChannel` là **return address kỹ thuật** của request–reply đang hoạt động.
- `businessCorrelationId` là **danh tính logical work** để phân nhóm, retry, trace và replay.

Khi Splitter phát nhiều child rồi Aggregator tạo một summary, Gateway thường muốn **một reply tổng hợp**, không phải từng child result. Nếu mất `replyChannel`, timeout/lỗi có thể xuất hiện dù business key vẫn đúng. Nếu mất business key, Aggregator có thể gom sai dù Gateway vẫn có reply channel hợp lệ.

**Không serialize một temporary reply channel object như một business correlation ID** khi phát request qua broker. Nếu cần request–reply xuyên process, dùng adapter/gateway với reply destination/correlation mapping phù hợp, hoặc một coordinator lưu pending state có key bền vững.

## 16. Content Enricher: request tra cứu phụ phải gắn với original

Một OrderEvent cần enrich thông tin khách hàng:

~~~text
Original M0:
  orderId=O-101
  businessCorrelationId=t:tenant-a|o:O-101|v:3|op:PRICE

Lookup request Q1:
  customerId=C-01
  lookupRequestId=ER-501
  parentBusinessCorrelationId=<key M0>

Lookup reply R1:
  lookupRequestId=ER-501
  customerProfile=GOLD
~~~

Content Enricher trong Spring Integration có thể dùng request–reply nội bộ và `replyChannel` tạm để lấy dữ liệu rồi áp vào original message. Tuy nhiên, nếu lookup đi qua broker hoặc callback độc lập, cần một **lookupRequestId riêng** cho mỗi logical enrichment request và mapping tới parent group.

Không dùng `customerId` để ghép toàn bộ replies: nhiều order khác nhau có thể cùng customer. Không đổi `businessCorrelationId` của original thành `lookupRequestId`, vì điều đó phá correlation của flow chính.

**Parent correlation** và **child request correlation** là hai cấp:

~~~mermaid
flowchart TD
    M["Order work group G"] --> Q1["Lookup request ER-501"]
    M --> Q2["Lookup request ER-502"]
    Q1 --> R1["Reply ER-501"]
    Q2 --> R2["Reply ER-502"]
    R1 --> M
    R2 --> M
~~~

Một pending store hoặc broker adapter có thể giữ quan hệ `ER-501 → G` và `ER-502 → G`; không dựa vào thứ tự reply đến.

## 17. Content-based Router, Header Enricher và Aggregator không phải cùng pattern

| Pattern | Câu hỏi | Tác động đến correlation |
|---|---|---|
| Content Based Router | Gửi **đi đâu** theo nội dung? | Phải giữ logical identity qua nhánh |
| Header Enricher | Bổ sung/chuẩn hóa **metadata nào**? | Có thể tạo header business key từ payload |
| Transformer | Đổi **payload sang kiểu gì**? | DTO mới phải có identity hoặc header được giữ |
| Splitter | Tách **bao nhiêu child**? | Thêm sequence metadata, không đánh mất parent identity |
| Aggregator | **Những child nào cùng group** và khi nào đủ? | Dùng correlation strategy và release strategy |
| Content Enricher | Cần tra cứu dữ liệu nào để bổ sung? | Request tra cứu có identity phụ, không ghi đè parent group |
| Gateway | Return address của lời gọi nào? | Reply channel không thay business correlation |
| Resequencer | Phát các message theo thứ tự nào? | Cần group key và sequence number đúng |

**Content-based correlation** là một **chiến lược xác định identity**, không có nghĩa Spring Integration cung cấp một annotation `@ContentBasedCorrelation` độc lập. Nó thường được triển khai bằng **correlation strategy/expression của Aggregator/Resequencer**, cùng việc chuẩn hóa dữ liệu ở ingress.

## 18. Aggregator: ưu tiên correlation strategy dựa trên payload khi cần bền vững

Nếu các worker trả `LineResult` có đủ identity, Aggregator có thể tính key trực tiếp:

~~~java
@Configuration
@EnableIntegration
class GroupedLineResultFlow {

    @Bean
    IntegrationFlow groupLineResults() {
        return IntegrationFlow.from("orders.line.results")
            .aggregate(a -> a
                .correlationStrategy(message ->
                    BusinessGroupKey.from(
                        (LineResult) message.getPayload()))
                .releaseStrategy(new AllExpectedLinesRelease())
                .outputProcessor(new OrderSummaryProcessor()))
            .channel("orders.completed")
            .get();
    }
}
~~~

Đây là Java DSL minh họa. `AllExpectedLinesRelease` và `OrderSummaryProcessor` là các class ứng dụng được giải thích bên dưới; chúng không phải API có sẵn. Cần type validation khi inbound có thể nhận message sai kiểu, và cần MessageGroupStore/locking phù hợp nếu chạy nhiều instance.

**Vì sao đọc payload thay vì header?** Nếu wire adapter bỏ custom header nhưng payload vẫn giữ tenant/order/revision/operation, correlation vẫn có thể được tái tạo. Đây là cốt lõi của **content-based correlation**. Tuy nhiên, payload có thể bị sửa hoặc giả mạo, nên chỉ dùng các field đã validate/được tin cậy.

## 19. Release strategy phải kiểm tra member, không chỉ group size

Một release strategy đơn giản:

~~~java
.releaseStrategy(group -> group.size() == 3)
~~~

**có thể sai** khi:

~~~text
Group G:
  L1 success
  L1 duplicate từ redelivery
  L2 success
  L3 chưa tới

group.size() có thể bằng 3 → release sai.
~~~

Một mô hình minh họa có kiểm tra consistency và số member IDs khác nhau:

~~~java
final class AllExpectedLinesRelease implements ReleaseStrategy {

    @Override
    public boolean canRelease(MessageGroup group) {
        List<LineResult> parts = group.getMessages().stream()
            .map(message -> (LineResult) message.getPayload())
            .toList();

        if (parts.isEmpty()) {
            return false;
        }
        LineResult first = parts.get(0);
        int expected = first.expectedLines();
        if (expected <= 0 || expected > 100_000) {
            throw new IllegalStateException("INVALID_EXPECTED_LINES");
        }
        String key = BusinessGroupKey.from(first);
        boolean consistent = parts.stream().allMatch(part ->
            BusinessGroupKey.from(part).equals(key)
                && part.expectedLines() == expected);
        if (!consistent) {
            throw new IllegalStateException("INCONSISTENT_GROUP");
        }
        long distinctLines = parts.stream()
            .map(LineResult::lineId)
            .distinct()
            .count();
        return distinctLines == expected;
    }
}
~~~

**Giới hạn:** kiểm tra `distinctLines == expected` chưa chứng minh các IDs nằm trong **manifest chính xác**. Member lạ L99 có thể thế chỗ L3. Production nên lưu manifest tập `expectedLineIds` từ đầu và so sánh theo set, đồng thời xử lý duplicate outcomes mâu thuẫn trước khi phát summary.

Không được lấy `expectedLines` từ một worker không tin cậy rồi mặc định đó là tổng hợp lệ; expected count phải được chốt tại coordinator/manifest và cross-check.

## 20. Output processor: summary phải giữ parent correlation

Sau khi group được release, một message mới `OrderSummary` vẫn cần identity nếu còn downstream:

~~~java
record OrderSummary(
    String tenantId,
    String orderId,
    int revision,
    WorkOperation operation,
    String businessCorrelationId,
    int expectedLines,
    long totalAmountCents,
    int failed
) {}

final class OrderSummaryProcessor implements MessageGroupProcessor {

    @Override
    public Object processMessageGroup(MessageGroup group) {
        Map<String, LineResult> byLine = new LinkedHashMap<>();
        for (Message<?> message : group.getMessages()) {
            LineResult part = (LineResult) message.getPayload();
            LineResult previous =
                byLine.putIfAbsent(part.lineId(), part);
            if (previous != null && !previous.equals(part)) {
                throw new IllegalStateException(
                    "CONFLICTING_DUPLICATE_RESULT");
            }
        }
        if (byLine.isEmpty()) {
            throw new IllegalStateException("EMPTY_GROUP");
        }

        LineResult first = byLine.values().iterator().next();
        long total = 0;
        int failed = 0;
        for (LineResult part : byLine.values()) {
            if (part.success()) {
                total = Math.addExact(total, part.amountCents());
            } else {
                failed++;
            }
        }
        return new OrderSummary(
            first.tenantId(),
            first.orderId(),
            first.revision(),
            first.operation(),
            BusinessGroupKey.from(first),
            first.expectedLines(),
            total,
            failed);
    }
}
~~~

`OrderSummary` giữ parent identity và trạng thái fail. Nếu `failed > 0`, downstream phải quyết định summary `PARTIAL`, `FAILED` hay được phép chấp nhận theo domain; **không tự coi các line thành công cộng được tiền là toàn bộ order thành công**.

Output processor cũng không tự tạo transaction exactly-once. Nếu group được release hai lần do redelivery/expiry/restart, cần một idempotent publisher/outbox dựa trên business group key và output version.

## 21. Content key và Spring framework correlation header có thể đồng tồn tại

Trong một message đi qua Splitter, có thể thấy:

~~~text
headers.businessCorrelationId
  = t:tenant-a|o:O-101|v:3|op:PRICE

headers.correlationId
  = <sequence-group identity của framework>

headers.sequenceNumber = 2
headers.sequenceSize   = 3
~~~

**Không cần ép hai header này luôn bằng nhau.** Header `correlationId` của Splitter phục vụ cách framework gom các message con của **lần split cụ thể**. Header `businessCorrelationId` phục vụ logical work xuyên broker, retry, replay và việc kiểm toán.

Nếu Aggregator được cấu hình **custom correlation strategy từ payload**, nó không phải phụ thuộc vào `headers.correlationId`. Tuy nhiên các thành phần khác như Resequencer hoặc nested Aggregator vẫn có thể dựa vào sequence headers; đừng loại chúng trong JVM khi chưa hiểu topology.

Một test nên kiểm tra **cả hai**:

- Business group identity không đổi qua các endpoint.
- Sequence metadata được hiểu đúng tại endpoint tiêu thụ sequence.

## 22. Khi nào nên chỉ giữ key trong header, chỉ giữ trong payload hoặc cả hai?

| Chiến lược | Ưu điểm | Rủi ro/cần bảo vệ |
|---|---|---|
| **Header-only** | Ít thay đổi DTO, framework router dễ đọc | Dễ mất do header mapper/custom message/wire |
| **Payload-only** | Stable contract xuyên broker, dễ replay | Dễ trùng/sai nếu DTO thiếu identity hoặc payload bị giả |
| **Header + payload** | Dễ route/trace và vẫn có khả năng khôi phục | Hai bản key có thể mâu thuẫn; cần cross-check |
| **Lookup từ pending store** | Hữu ích cho callback chỉ có request ID | Phải bảo vệ durability, TTL và authorization |

Với flow **in-process ngắn**, một header correlation chuẩn có thể đủ nếu các endpoints được kiểm soát. Với flow **distributed hoặc replayable**, nên có group identity trong wire schema hoặc một mapping bền vững từ request ID tới group.

Trường hợp giữ cả header và payload, **payload đáng tin sau validation** hoặc pending manifest nên là nguồn chuẩn. Nếu không nhất quán, reject/quarantine thay vì chọn ngẫu nhiên bản nào “đến sau”.

## 23. Qua QueueChannel và ExecutorChannel

Trong cùng JVM, chuyển từ `DirectChannel` sang `ExecutorChannel` hoặc `QueueChannel` không đương nhiên đổi business group key. Tuy vậy, ranh giới asynchronous tạo thêm thách thức:

1. Các message có thể hoàn tất **đảo thứ tự**.
2. Exception xảy ra **sau** khi upstream `send()` thành công.
3. Header `errorChannel` và reply semantics có thể khác khi đi qua async boundary.
4. Pending group chờ đến lúc đủ member hoặc deadline.
5. Thread pool/queue có thể quá tải khi Splitter fan-out nhiều.

**Correlation không phải ordering.** Cùng key không bảo đảm thứ tự arrival. Nếu downstream cần từng event theo sequence thì có thể dùng Resequencer; nếu chỉ cần một summary thì Aggregator có thể nhận kết quả sai thứ tự và gộp theo business member IDs.

**Giới hạn tài nguyên:** dùng bounded executor/queue, max pending groups và timeout. Business correlation đúng nhưng một message mất vĩnh viễn vẫn có thể khiến Aggregator chờ mãi nếu không có expiry policy.

## 24. Qua Kafka/AMQP/HTTP: header không phải hợp đồng wire tự động

Khi message qua broker hoặc HTTP:

- Header mapper chọn header nào được serialize, đổi tên, loại bỏ hoặc đổi kiểu.
- Một Spring Message mới có thể nhận `MessageHeaders.ID` mới ở consumer.
- `replyChannel`/`errorChannel` có thể là object nội bộ không an toàn để truyền như ID.
- CorrelationId ở broker adapter có thể phục vụ **request–reply kỹ thuật**, không phải group key nghiệp vụ.
- Message có thể redeliver, đến trễ hoặc mất thứ tự do nhiều partitions/consumers.

**Hợp đồng wire đề xuất** cho một member:

~~~json
{
  "schemaVersion": 1,
  "tenantId": "tenant-a",
  "orderId": "O-101",
  "revision": 3,
  "operation": "PRICE",
  "eventId": "EV-101",
  "lineId": "L-2",
  "expectedLines": 3,
  "amountCents": 2500,
  "success": true,
  "reasonCode": null
}
~~~

Nếu receiver có đủ fields, nó có thể **tính lại** `BusinessGroupKey`. Một producer cũng có thể gửi thêm `businessCorrelationId`, nhưng receiver phải so với giá trị chuẩn hóa và kiểm tra tenant/source.

Không dùng raw spring `MessageHeaders` làm JSON output mà không có whitelist. Những header có thể chứa credential, routing internals hoặc đối tượng không serialize được. Không suy diễn rằng hai broker adapter khác nhau sẽ giữ cùng header map theo cùng cơ chế.

## 25. Mapping khi reply đi qua transport khác

Ví dụ:

~~~mermaid
sequenceDiagram
    participant P as Order processor
    participant K as Broker
    participant W as Worker
    participant A as Aggregator
    P->>K: LineWork L2 + group fields
    K->>W: Deserialize LineWork
    Note over W: Message ID mới có thể được tạo
    W->>K: LineResult L2 + group fields
    K->>A: Deserialize LineResult
    Note over A: Tính group key từ payload
    A->>A: Group theo tenant/order/revision/operation
~~~

**Không gắn group theo thứ tự đến** hoặc theo một temporary reply channel của JVM. Receiver cần sử dụng identity trong hợp đồng và quy tắc canonicalization ổn định.

Nếu schema tiến hóa từ `revision: number` sang `revision: string`, hoặc đổi cách viết tenant ID, cần versioned validation. Hai giá trị hiển thị gần giống nhau có thể tạo key khác; ngược lại cast sai có thể gây collision.

Với một request–reply adapter chính thức của Spring Integration, hãy kiểm chứng **mapping correlation kỹ thuật và reply destination** theo công nghệ/phiên bản; business correlation không nên bị ghi đè chỉ vì adapter sử dụng cùng tên header trong ngữ cảnh riêng.

## 26. Retry: giữ logical group ID, tách attempt ID

Một line bị timeout:

~~~text
Logical work:
  groupKey = t:tenant-a|o:O-101|v:3|op:PRICE
  lineId   = L-2

Attempt 1:
  attemptId = A-1
  → timeout tại caller

Attempt 2:
  attemptId = A-2
  → LineResult được trả về
~~~

Nếu đây là **retry của cùng logical operation**, group key phải giữ nguyên. Không đưa `attemptId` vào key của Aggregator, nếu không hai attempts thuộc hai group khác nhau. Attempt ID vẫn có ích cho tracing, fencing và lựa chọn result cuối hợp lệ.

**Timeout không chứng minh worker chưa xử lý.** Attempt 1 có thể đã ghi dữ liệu hoặc gửi reply đến muộn. Vì thế cần:

- Idempotency key ở mức `(tenant, group, lineId, operation)` hoặc theo phạm vi side effect.
- Dedupe/conflict detection với duplicate replies.
- Deadline chung của logical work, không reset vô hạn khi retry.
- Conditional completion/publish để không tạo hai summary terminal.

Một UUID mới mỗi attempt là hợp lý cho **attempt tracking**, nhưng không hợp lý để thay **parent business correlation**.

## 27. Duplicate, late reply và completed group

Sau khi Aggregator release group, một reply cũ có thể đến:

~~~text
T0  L1, L2, L3 của group G đã hoàn tất
T1  Aggregator phát OrderSummary(G)
T2  Broker redeliver L2 (duplicate)
T3  Worker attempt cũ trả L1 đến muộn
~~~

Nếu group cũ đã bị xóa và không có dấu hoàn tất bền vững, những late replies **có thể tạo group mới cùng key**, dẫn đến đợi nhóm ma hoặc double publish.

Các cơ chế:

1. **Completion tombstone** theo group key với TTL được chọn theo cửa sổ late arrivals.
2. **Idempotent output** bằng uniqueness key cho `OrderSummary(groupKey, outputVersion)`.
3. **Expiry/late reply policy**: ignore, quarantine hoặc correction event có version.
4. **Reconciliation** khi outcomes conflict hoặc có side effects đã commit.

Spring Integration có các cấu hình liên quan group expiry/completion và MessageGroupStore, nhưng **không tự đảm bảo exactly-once nghiệp vụ**. Đánh giá behavior trên phiên bản và backend đang triển khai.

## 28. Error channel: lỗi cũng cần correlation

Đường thành công có thể giữ business key, nhưng đường lỗi lại bỏ:

~~~text
LineWork L2 → HTTP client exception
  → ErrorMessage(exception only)
  → error handler không biết tenant/order/revision/lineId
~~~

Một error handler hiệu quả cần có **failure context**:

~~~java
record WorkFailure(
    String businessCorrelationId,
    String lineId,
    String reasonCode,
    boolean retryable
) {}
~~~

Khi chuyển lỗi thành một `LineResult(success=false)` hoặc `WorkFailure`, xác định rõ:

- Lỗi thuộc logical group nào?
- Member nào không thành công?
- Có được tính là **đã có outcome** cho member hay phải retry?
- Có phải lỗi vĩnh viễn như invalid SKU, hay tạm thời như timeout?
- Lỗi được trả về Gateway đồng bộ hay phát qua error channel của async transport?

Không mặc định mọi `ErrorMessage` đều có original payload ở cùng vị trí; tùy exception type và endpoint, cần dùng failed message/correlation context mà framework hoặc handler có sẵn. **Không log hoặc phát raw exception chứa dữ liệu nhạy cảm ra broker công khai**.

Nếu error flow trả failure outcome cho Aggregator, outcome phải mang **cùng business key và member ID**, không gộp mọi lỗi dưới key chung như `UNKNOWN`.

## 29. Multi-tenant security: key đúng cú pháp vẫn có thể sai quyền

Một attacker gửi:

~~~json
{
  "tenantId": "tenant-b",
  "orderId": "O-101",
  "revision": 3,
  "operation": "PRICE"
}
~~~

Nếu server chỉ dùng raw payload để xây group key mà không xác minh người gửi có quyền truy cập `tenant-b`, message có thể bị đặt nhầm vào group của tenant khác.

Content-based correlation phải đi cùng:

- **Authenticated tenant scope** tại ingress.
- Kiểm tra `orderId` thuộc tenant đã xác thực.
- Validate reply từ service được phép, schema và member identity.
- Phân quyền với MessageGroupStore, logs và error channels.
- Canonicalization nhất quán giữa mọi instance.
- Chặn group key/ID quá dài hoặc bất thường nhằm hạn chế memory/storage abuse.

**Correlation ID là định danh, không phải bằng chứng authorization.** Việc biết đúng group key không cho phép một bên đọc hoặc sửa nội dung group.

## 30. Nested Splitter và hai cấp correlation

Một batch được chia thành 3 chunks, mỗi chunk có 100 lines:

~~~mermaid
flowchart TD
    B["Batch B-1"] --> S1["Splitter: 3 chunks"]
    S1 --> C1["Chunk 1"]
    S1 --> C2["Chunk 2"]
    S1 --> C3["Chunk 3"]
    C1 --> S2["Splitter: từng line"]
    C2 --> S2
    C3 --> S2
    S2 --> W["Workers"]
    W --> AG1["Line → Chunk Aggregator"]
    AG1 --> AG2["Chunk → Batch Aggregator"]
~~~

Có ít nhất hai identity:

~~~text
parentBatchKey = tenantId + batchId + revision
childChunkKey  = parentBatchKey + chunkIndex
lineMemberId   = lineId
~~~

Nếu nested Splitter đặt lại `correlationId` theo **cấp gần nhất**, chỉ dựa trên header chuẩn có thể làm mất khả năng gom ở tầng outer. Dùng payload IDs/manifest rõ cho từng cấp, hoặc một cơ chế lưu parent correlation được thiết kế trước.

Không lấy `sequenceNumber=2` của chunk làm `sequenceNumber=2` của line: các sequence thuộc các **không gian khác nhau**. Group key phải mã hóa scope/tầng, tránh Aggregator của batch nhận nhầm LineResult thuộc chunk.

## 31. Test đơn vị: key phải ổn định và tách phạm vi

JUnit 5:

~~~java
@Test
void sameLogicalWorkHasSameKey() {
    String keyA = BusinessGroupKey.of(
        "tenant-a", "O-101", 3, WorkOperation.PRICE);
    String keyRetry = BusinessGroupKey.of(
        "tenant-a", "O-101", 3, WorkOperation.PRICE);

    assertEquals(keyA, keyRetry);
}

@Test
void differentRevisionTenantOrOperationHasDifferentKey() {
    String base = BusinessGroupKey.of(
        "tenant-a", "O-101", 3, WorkOperation.PRICE);

    assertNotEquals(base, BusinessGroupKey.of(
        "tenant-a", "O-101", 4, WorkOperation.PRICE));
    assertNotEquals(base, BusinessGroupKey.of(
        "tenant-b", "O-101", 3, WorkOperation.PRICE));
    assertNotEquals(base, BusinessGroupKey.of(
        "tenant-a", "O-101", 3, WorkOperation.INVENTORY));
}

@Test
void rejectsAmbiguousDelimiterInIdentifier() {
    assertThrows(IllegalArgumentException.class,
        () -> BusinessGroupKey.of(
            "tenant|b", "O-101", 3, WorkOperation.PRICE));
}
~~~

Test này chỉ xác minh **khóa**. Chưa kiểm chứng headers trên message, broker serialization hoặc group membership trong Aggregator. Với canonicalization phức tạp, thêm property-based tests cho ký tự Unicode, số 0 đầu, chữ hoa/thường và các trường có delimiter.

## 32. Integration test: cùng key qua Filter và Header Enricher

Test một flow gắn header:

~~~java
@Autowired
ApplicationContext context;

@Test
void stampsBusinessKeyAtIngress() {
    MessageChannel input =
        context.getBean("orders.in", MessageChannel.class);
    PollableChannel output =
        context.getBean("orders.correlated", PollableChannel.class);

    OrderEvent order = new OrderEvent(
        "tenant-a", "O-101", 3, "EV-101",
        WorkOperation.PRICE,
        List.of(new OrderLine("L1", "SKU-1", 500, 2)));

    assertTrue(input.send(new GenericMessage<>(order)));
    Message<?> received = output.receive(1_000);
    assertNotNull(received);

    assertEquals(BusinessGroupKey.from(order),
        received.getHeaders().get("businessCorrelationId"));
}
~~~

Test trên cần cấu hình `orders.correlated` là **QueueChannel test-only** và không có consumer production cạnh tranh. Một test khác nên đưa original có `businessCorrelationId` **sai** để xác minh **reject/overwrite theo chính sách rõ ràng**; đừng chỉ test trường hợp header trống.

## 33. Integration test: Splitter → Workers → Aggregator không trộn hai group

Tạo hai order:

~~~text
O-101/rev3/PRICE → [L1, L2, L3]
O-101/rev4/PRICE → [L1, L2, L4]
~~~

Gửi replies xen kẽ:

~~~text
rev3/L2
rev4/L1
rev3/L1
rev4/L2
rev4/L4
rev3/L3
~~~

Kỳ vọng **hai summary độc lập**. Code định hướng:

~~~java
@Autowired
ApplicationContext context;

@Test
void separatesTwoRevisionsDuringAggregation() {
    MessageChannel input = context.getBean(
        "orders.line.results", MessageChannel.class);
    PollableChannel output = context.getBean(
        "orders.completed", PollableChannel.class);

    send(input, result(3, "L2"));
    send(input, result(4, "L1"));
    send(input, result(3, "L1"));
    send(input, result(4, "L2"));
    send(input, result(4, "L4"));
    send(input, result(3, "L3"));

    OrderSummary first = (OrderSummary)
        Objects.requireNonNull(output.receive(1_000))
            .getPayload();
    OrderSummary second = (OrderSummary)
        Objects.requireNonNull(output.receive(1_000))
            .getPayload();

    assertEquals(Set.of(3, 4),
        Set.of(first.revision(), second.revision()));
    assertNotEquals(first.businessCorrelationId(),
        second.businessCorrelationId());
}
~~~

Hàm `send(...)` và `result(...)` là **test fixture do ứng dụng định nghĩa**. Bổ sung assertion theo **đúng tập member IDs và amounts** chứ không chỉ revision/tổng số output; hai summary có thể đúng revision nhưng sai các member nếu worker hoặc release strategy lỗi.

Không dùng `Thread.sleep` để ép thứ tự; gửi message theo thứ tự định sẵn hoặc dùng `CountDownLatch` khi test concurrency thật. Với broker, chạy thêm test serialization, header mapper và redelivery.

## 34. Ma trận lỗi cần kiểm thử end-to-end

| Tình huống | Đầu vào | Kết quả mong đợi |
|---|---|---|
| Happy path | Một order, đủ line results | Một summary đúng group |
| Hai order cùng tenant | Khác `orderId` | Không trộn group |
| Cùng order khác revision | rev3 và rev4 xen kẽ | Hai summary riêng |
| Hai operation | PRICE và INVENTORY | Không gộp nhầm |
| Cross-tenant | Cùng mã order ở tenant A/B | Group cô lập và kiểm soát quyền |
| Header bị mất qua broker | Payload đủ business fields | Tính lại key đúng |
| Header sai so với payload | Payload/key mâu thuẫn | Reject/quarantine, không chọn bừa |
| Transformer tạo message mới | Message ID khác | Group identity vẫn đúng |
| Retry cùng logical work | Attempt ID đổi | Business key giữ nguyên |
| Duplicate LineResult | Hai bản cùng `lineId` | Không đếm thành hai member |
| Conflicting duplicate | Success và failure cùng member | Phát hiện conflict/reconcile |
| Missing member | Filter drop một line | Timeout/failure result, không complete giả |
| Unknown correlation | Không có group/pending state | Quarantine hoặc reject có metric |
| Late reply | Tới sau completion | Không double publish trái contract |
| Nested Splitter | Batch→chunk→line | Correlation hai tầng chính xác |
| Async error | Worker ném exception | Error path giữ group/member identity |
| Restart | Persistent group store | Recovery theo bảo đảm đã thiết kế |
| Key migration | Old/new canonical format | Cutover có version/drain/migration |

**Đặc biệt:** cần một test tạo **Spring Message mới với cùng payload nhưng `MessageHeaders.ID` khác** để chứng minh group key dựa vào business content chứ không dựa vào object identity.

## 35. Quan sát correlation trong production

Nên có structured trace:

~~~text
ingress:
  eventId=EV-101
  businessCorrelationId=t:tenant-a|o:O-101|v:3|op:PRICE
  endpoint=orders.in

filter/router:
  endpoint=orders.correlated
  route=price.requests

split:
  memberId=L2
  sequenceNumber=2
  sequenceSize=3

worker:
  memberId=L2
  attempt=2
  outcome=SUCCESS

aggregate:
  groupKey=t:tenant-a|o:O-101|v:3|op:PRICE
  distinctMembers=3
  expectedMembers=3
  status=COMPLETED
~~~

Metric gợi ý:

| Metric | Phát hiện |
|---|---|
| `correlation.key.missing.count` | Header/payload bị thiếu key |
| `correlation.key.mismatch.count` | Header khác payload canonical |
| `correlation.group.pending.count` | Nhóm chưa đủ |
| `correlation.group.age` | Nhóm chờ lâu bất thường |
| `correlation.group.duplicate.count` | Redelivery và duplicate |
| `correlation.group.unknown.count` | Reply không có group hợp lệ |
| `correlation.group.expired.count` | Timeout/expiry |
| `correlation.group.late.count` | Late replies |
| `correlation.group.completed.count` | Group release thành công/thất bại |
| `message.store.bytes` | Storage pressure |

Đây là **tên metric đề xuất**, không phải meter mặc định của Spring Integration. Dùng tag có cardinality thấp (flow, endpoint, outcome, reason), **không dùng full businessCorrelationId, orderId hoặc eventId làm metric tag**. Các ID cụ thể dành cho tracing/log có quyền truy cập và retention phù hợp.

Một trace phải giúp trả lời: **ID được cấp ở đâu, có bị đổi tại endpoint nào, message nào bị thiếu, vì sao group chưa release và reply nào đến trễ?**

## 36. Runbook khi mất correlation sau một endpoint

Khi Aggregator giữ hàng nghìn group không hoàn tất hoặc trả nhầm summary:

1. **Xác định logical work scope:** tenant/order/revision/operation; group đúng phải gồm những member nào?
2. **Xem ingress:** identity lấy từ nguồn đã xác thực hay từ header raw của client?
3. **Xem payload:** các field group identity có tồn tại trước và sau Transformer không?
4. **Xem custom headers:** `businessCorrelationId` có bị bỏ/ghi đè không?
5. **Xem Splitter:** `correlationId` chuẩn và sequence metadata có đổi theo đúng tầng group không?
6. **Xem Router/Filter:** một nhánh có bị drop hoặc route sai không?
7. **Xem async boundary:** Queue/Executor/broker có giữ headers/contract như dự định không?
8. **Xem worker reply:** result có chứa event/group/member identity ổn định không?
9. **Xem Aggregator:** correlation strategy tính từ payload/header nào và release có kiểm tra distinct members không?
10. **Xem lỗi/retry:** outcome bị mất, duplicate hay late reply, completion tombstone có tồn tại không?
11. **Xác minh side effect:** có summary sai đã được commit/publish chưa trước khi replay/correction?
12. **Khắc phục:** sửa mapping/validation/key version, bổ sung integration test rồi migrate/drain pending groups có kiểm soát.

**Đừng tạo key `UNKNOWN` cho tất cả message thiếu ID.** Cách này có thể biến mọi input lỗi thành một “super-group”, gây lẫn dữ liệu hoặc rò rỉ cross-tenant. Nếu không khôi phục được identity tin cậy, reject/quarantine và báo lỗi rõ.

## 37. Các hiểu lầm thường gặp

**“Mọi endpoint Spring Integration tự giữ nguyên toàn bộ headers.”** Không thể giả định điều đó, nhất là custom MessageBuilder, adapters và broker mapper. Test theo đúng topology.

**“Correlation ID là MessageHeaders.ID.”** Không. Một cái là group identity, cái kia nhận diện một message object tại một thời điểm.

**“Có traceId là đủ để Aggregator phân nhóm.”** Không. Tracing context có scope và vòng đời khác business group.

**“Chỉ dùng orderId luôn an toàn.”** Không khi có nhiều revision, operation hoặc tenant.

**“UUID mới trong mỗi worker làm correlation mạnh hơn.”** Sai: cùng logical work bị chia thành các group khác nhau.

**“Route sang Pricing thì đổi correlationId thành tên channel.”** Sai: channel name không phải group identity.

**“Splitter correlationId và businessCorrelationId phải luôn giống nhau.”** Không. Hai cấp ID phục vụ semantics khác nhau.

**“Payload có group ID thì không cần kiểm tra header.”** Chưa đủ nếu external caller được phép giả mạo content hoặc hai bản mâu thuẫn.

**“Header tồn tại là đã có authorization.”** Sai. ID chỉ nhận diện, không cấp quyền.

**“MessageGroupStore persistent sẽ tự sửa key collision.”** Sai; nó có thể lưu sai group lâu hơn.

**“Đủ ba message nghĩa là đủ ba line.”** Sai với duplicate. Kiểm tra distinct member IDs và manifest.

**“Retry làm sinh business group mới.”** Không nếu đó là attempt khác của cùng logical operation.

**“Gateway replyChannel có thể dùng làm business correlation trên Kafka.”** Không; return address nội bộ không phải durable group identity.

**“Error channel tự biết cách gửi failure result vào Aggregator.”** Không; phải thiết kế error-to-outcome mapping mang đúng group/member identity.

**“Khi group đã release thì không còn reply muộn.”** Không; phải có idempotency và late-arrival policy.

## 38. Bài thực hành: truyền identity xuyên tám endpoint

Xây flow **OrderCorrelationPipeline**:

1. **Gateway/ingress:** nhận `OrderEvent` đã xác thực, tạo `businessCorrelationId` từ `tenantId/orderId/revision/operation`.
2. **Filter:** reject dữ liệu thiếu/không hợp lệ, giữ group ID trong error outcome.
3. **Header Enricher:** tính hoặc xác minh custom correlation header từ payload.
4. **Router:** phân nhánh PRICE/INVENTORY nhưng không đổi parent group identity.
5. **Transformer:** chuyển payload sang DTO mới có đầy đủ identity.
6. **Splitter:** phát mỗi line, giữ parent key và sequence metadata.
7. **Worker:** trả `LineResult`, dùng member ID bền vững; thử retry tạo Spring Message ID mới.
8. **Aggregator:** tính correlation strategy từ payload, release theo expected manifest/member IDs.
9. **Gateway/outbound:** tạo OrderSummary giữ parent key, có completion status.
10. **Broker:** đưa một nhánh qua Kafka/AMQP rồi kiểm tra payload contract và header mapper.
11. **Lỗi:** thử Filter reject, timeout, duplicate/conflicting reply, late reply và cross-tenant input.
12. **Observability:** truy vết key qua từng endpoint, đo pending/mismatch/expired groups.

**Tiêu chí hoàn thành:** cùng logical work có cùng key qua mọi endpoint; hai revision/tenant/operation không trộn; key từ payload khôi phục được sau broker khi header bị loại; correlation của Splitter không bị ghi đè tùy ý; Aggregator chỉ release đúng member set; error/retry/late replies có quyết định rõ ràng và không tạo output trùng ngoài hợp đồng.

## 39. Ghi nhớ

**Truyền correlation ID qua nhiều endpoint** không chỉ là chuyển một header nguyên vẹn. Đó là việc giữ **ngữ nghĩa của một logical processing group** qua Gateway, Filter, Router, Transformer, Splitter, worker, broker, Aggregator và error channel.

Trong **Content-based correlation**, hãy có **business identity ổn định trong payload hoặc contract bền vững**, tính một canonical group key từ các field đã được xác thực, và có thể giữ thêm `businessCorrelationId` ở header cho nội bộ. Phân biệt key này với `MessageHeaders.ID`, sequence headers của Splitter, trace ID và reply channel của Gateway.

Kết hợp **correlation đúng**, **release strategy kiểm tra member thật**, **idempotency/late reply policy**, **timeout/MessageGroupStore** và **test xuyên transport** để bảo đảm mỗi kết quả được ghép đúng nhóm, ngay cả khi message đổi kiểu, qua nhiều tiến trình, đến sai thứ tự hoặc bị redeliver.

### Tài liệu tham khảo

- Spring Integration Reference, **Aggregator**: https://docs.spring.io/spring-integration/reference/aggregator.html
- Spring Integration Reference, **Splitter**: https://docs.spring.io/spring-integration/reference/splitter.html
- Spring Integration Reference, **Header Enricher**: https://docs.spring.io/spring-integration/reference/content-enrichment.html
- Spring Integration Reference, **Message Channels**: https://docs.spring.io/spring-integration/reference/channel.html
- Enterprise Integration Patterns, **Correlation Identifier**: https://www.enterpriseintegrationpatterns.com/patterns/messaging/CorrelationIdentifier.html
- Enterprise Integration Patterns, **Content-Based Router**: https://www.enterpriseintegrationpatterns.com/patterns/messaging/ContentBasedRouter.html
