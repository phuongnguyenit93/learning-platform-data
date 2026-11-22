# Correlation giữa message gốc và request enrichment

## 1. Vì sao Content Enricher phải giữ được mối liên hệ với message gốc?

Một hệ thống bán hàng nhận sự kiện `OrderCreated` gồm `eventId`, `orderId` và `customerId`. Trước khi chọn chính sách ưu đãi hay chuyển đơn sang nhánh xử lý phù hợp, hệ thống cần bổ sung **hạng khách hàng** từ một dịch vụ Customer Profile.

~~~text
Order A: eventId=EV-A, orderId=O-101, customerId=C-01
Order B: eventId=EV-B, orderId=O-102, customerId=C-02

Request enrichment A: tra cứu C-01
Request enrichment B: tra cứu C-02

Reply B: CustomerProfile(C-02, STANDARD) đến trước
Reply A: CustomerProfile(C-01, GOLD) đến sau
~~~

Nếu hệ thống chỉ ghép theo **thứ tự response đến**, reply B có thể bị gắn nhầm cho Order A. Nếu ghép theo header `MessageHeaders.ID`, giá trị này có thể thay đổi khi framework tạo message mới hoặc khi qua broker. Nếu copy mọi header một cách mù quáng, reply còn có thể ghi đè `correlationId`, `replyChannel` hoặc metadata tenant của message gốc.

**Correlation giữa message gốc và request enrichment** là khả năng biết **yêu cầu tra cứu nào thuộc về message nào**, bảo đảm dữ liệu trả về được áp dụng đúng đối tượng, đúng tenant và đúng lần xử lý, ngay cả khi có concurrency, timeout, retry, duplicate hoặc reply đến sai thứ tự.

Trong **Spring Integration**, **Content Enricher** gửi một request tới `requestChannel` và chờ reply theo mô hình gateway nội bộ; reply được dùng để bổ sung thông tin vào **payload mục tiêu của message gốc**. Ở đường request–reply nội bộ thông thường, framework hỗ trợ ghép reply với lời gọi đang chờ thông qua cơ chế `replyChannel`. Nhưng khi request đi ra Kafka/AMQP/HTTP bất đồng bộ hoặc cần phục hồi sau restart, hệ thống vẫn phải thiết kế **correlation ID nghiệp vụ và trạng thái chờ bền vững** nếu muốn có bảo đảm end-to-end.

Bài thuộc chương **Content enricher** của module **SPRING_INTEGRATION_PATTERN**. Mục tiêu học tập là triển khai Enterprise Integration Patterns với Spring Integration để xây dựng message flow ít phụ thuộc, dễ mở rộng, kết hợp **Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation**, đồng thời kiểm thử và quan sát từng nhánh xử lý.

**Sau bài này, bạn có thể** vẽ vòng đời message gốc/request/reply, tách các loại ID, cấu hình Enricher request–reply, tránh ghép nhầm dữ liệu giữa các order, xử lý reply trễ/trùng, xác định giới hạn giữa JVM và broker, và kiểm thử correlation trong điều kiện xử lý đồng thời.

## 2. Ba đối tượng trong một lần enrichment

Để không nhầm lẫn, đặt tên cho ba loại thông điệp:

| Đối tượng | Payload minh họa | Vai trò |
|---|---|---|
| **Original message (M0)** | `OrderDraft(O-101, C-01)` | Mang dữ liệu cần bổ sung; chứa context nghiệp vụ |
| **Enrichment request (Q1)** | `customerId=C-01` | Yêu cầu tra cứu dữ liệu bổ sung tại service khác |
| **Enrichment reply (R1)** | `CustomerProfile(C-01, GOLD)` | Kết quả tra cứu; được dùng để enrich đúng M0 |
| **Enriched output (M1)** | `OrderDraft(O-101, C-01, GOLD)` | Message sau khi áp dụng dữ liệu từ R1 vào payload của M0 |

Quan hệ logic là:

\[
M_1 = \operatorname{enrich}(M_0,\ \operatorname{lookup}(Q_1(M_0)))
\]

Ở đây `Q1(M0)` nghĩa là request được tạo từ message gốc, còn `lookup()` trả dữ liệu bổ sung. Quy tắc quan trọng là **R1 phải thuộc Q1 và Q1 phải thuộc M0**, không đơn giản vì R1 tình cờ về trước hoặc có cùng loại payload.

~~~mermaid
sequenceDiagram
    participant P as Publisher
    participant E as Content Enricher
    participant L as Lookup handler
    participant O as Downstream
    P->>E: M0 = OrderDraft(O-101,C-01)
    E->>L: Q1 = lookup(C-01), replyChannel nội bộ
    L-->>E: R1 = CustomerProfile(C-01,GOLD)
    Note over E: Ghép reply vào đúng lời gọi đang chờ
    E->>O: M1 = OrderDraft(..., profile=GOLD)
~~~

Content Enricher là một biến thể của **Transformer**, nhưng khác một Transformer độc lập ở chỗ nó thường cần dữ liệu chưa có trong payload hiện tại. Nó thực hiện một **request–reply subflow** để lấy dữ liệu rồi mới áp dụng các property/header expressions.

## 3. Phân biệt các loại ID và header dùng cho correlation

Không có một ID nào thích hợp cho mọi mục đích:

| Trường | Chủ sở hữu | Dùng để làm gì? | Có nên dùng như request correlation bền vững? |
|---|---|---|---|
| `MessageHeaders.ID` | Spring Messaging | Nhận diện một đối tượng message | **Không**, message có thể được tạo lại |
| `eventId` | Producer/hợp đồng nghiệp vụ | Idempotency và truy vết sự kiện | Có thể làm tham chiếu, nhưng một event có thể có nhiều lookup |
| `orderId` | Domain | Gắn với đơn hàng | Không đủ phân biệt nhiều request/lần thử |
| `customerId` | Domain | Khóa dữ liệu tra cứu | Không đủ phân biệt các order hoặc tenant |
| `correlationId` | Flow tích hợp/aggregator | Ghép các message thuộc cùng nhóm/quy trình | Dùng theo đúng semantics flow; không ghi đè tùy ý |
| `enrichmentRequestId` | Enrichment coordinator | Ghép một request với đúng một reply | **Phù hợp** khi qua broker hoặc lưu pending state |
| `traceId` | Tracing framework | Quan sát chuỗi call qua service | Không thay authorization hoặc request ID |
| `replyChannel` | Gateway/Enricher runtime | Địa chỉ trả lời trong flow | **Không** phải ID lưu/serialize tùy ý |

Trong một message có cả `eventId` và `enrichmentRequestId`, ta có thể diễn đạt: “lần enrichment `ER-5` thuộc sự kiện `EV-A`”. Nếu cùng event cần tra cứu **Customer** và **Fraud**, mỗi operation nên có correlation riêng, ví dụ `ER-5/customer` và `ER-5/fraud` hoặc hai ID khác nhau được gắn chung business event.

Đừng đặt `correlationId` bằng `customerId` chỉ vì tra cứu theo khách hàng. Nhiều order cùng customer có thể đang được xử lý đồng thời; chúng không được phép dùng chung một pending reply chỉ vì key tra cứu giống nhau.

**Nguyên tắc:** tách **business identity**, **processing/request identity**, **trace context** và **routing/reply channel semantics**. Có thể liên kết chúng trong log hoặc một bảng pending request, nhưng không đồng nhất.

## 4. Enricher request–reply trong Spring Integration

Theo tài liệu Spring Integration, khi Content Enricher có `requestChannel`, nó hoạt động tương tự một **gateway**: gửi message đến request channel, chờ reply, rồi áp dụng reply lên payload gốc. Nếu không khai báo `replyChannel` riêng, framework thường dùng **temporary reply channel** tạo cho mỗi request để ghép phản hồi với lời gọi đang chờ.

~~~mermaid
flowchart TB
    ORIG["M0: OrderDraft + headers gốc"] --> EN["ContentEnricher"]
    EN -->|"Q1: request payload + headers"| REQ["customer.lookup.requests"]
    REQ --> LOOK["Customer Lookup"]
    LOOK -->|"R1: lookup reply"| TEMP["Temporary reply channel"]
    TEMP --> EN
    EN -->|"M1: original payload + profile"| NEXT["orders.enriched"]
~~~

Khi khai báo `requestPayloadExpression`, Enricher có thể chỉ gửi **một phần payload** làm request, ví dụ `payload.customerId`. Điều quan trọng: **việc thu nhỏ request payload không mặc nhiên loại các MessageHeaders**. Theo mô tả của Spring Integration, request message vẫn có thể mang đầy đủ headers của original message, bao gồm các metadata không nên lọt ra service ngoài.

Hệ quả:

1. Enricher cần giữ được context của **M0** trong khi chờ **R1**.
2. Lookup reply được đánh giá làm **root của property/header expressions**; expression `payload.tier` tham chiếu dữ liệu reply, không phải tự động tham chiếu M0.
3. Dữ liệu có trong Q1 không nhất thiết là toàn bộ M0.
4. Với in-process synchronous request–reply thông thường, không cần tự phát minh một bảng correlation ngoài chỉ để nối Q1/R1 với lời gọi đang chờ.
5. Khi phát Q1 qua broker hoặc môi trường khác, phải xét cách serialize headers, bảo toàn return address và deadline; không mặc định cơ chế temporary reply channel trong JVM sống qua mọi ranh giới.

**Không đổi header `replyChannel` để lưu business event ID.** Nó phục vụ cơ chế reply của Spring Messaging; nếu bị ghi đè bằng một chuỗi không phải channel hợp lệ, flow có thể mất reply hoặc timeout.

## 5. Mô hình domain rõ ràng cho ví dụ thực hành

Giả sử một OrderDraft đang thiếu CustomerProfile:

~~~java
record CustomerProfile(
    String customerId,
    String tier
) {}

class OrderDraft {
    private final String eventId;
    private final String orderId;
    private final String customerId;

    private CustomerProfile customerProfile;

    public OrderDraft(String eventId, String orderId,
                      String customerId) {
        this.eventId = eventId;
        this.orderId = orderId;
        this.customerId = customerId;
    }

    public String getEventId() {
        return eventId;
    }

    public String getOrderId() {
        return orderId;
    }

    public String getCustomerId() {
        return customerId;
    }

    public CustomerProfile getCustomerProfile() {
        return customerProfile;
    }

    public void setCustomerProfile(CustomerProfile customerProfile) {
        this.customerProfile = customerProfile;
    }
}
~~~

Đây là **các type minh họa**, có thể đặt ở file Java thích hợp khi triển khai, không phải source code được ghi vào module trong STEP 4. `OrderDraft` là JavaBean có setter vì Payload Enricher hỗ trợ gán property trên payload mục tiêu. `CustomerProfile` là record bất biến trả về từ service tra cứu.

Một trường hợp đầu vào:

~~~text
M0.payload = OrderDraft(
  eventId=EV-101,
  orderId=O-101,
  customerId=C-01,
  customerProfile=null
)
M0.headers.businessEventId = EV-101
M0.headers.traceId = TRACE-101
~~~

Mục tiêu không phải thay toàn bộ message bằng một `CustomerProfile`, mà là nhận **M1 có thông tin OrderDraft ban đầu và property customerProfile được điền đúng**. Đây là khác biệt giữa Content Enricher và một Transformer vô điều kiện thay payload bằng dữ liệu tra cứu.

**Chú ý tính mutable:** ví dụ dùng setter để giải thích Content Enricher, nhưng trong production, nếu cùng instance payload được chia sẻ qua PublishSubscribeChannel hoặc nhiều thread, việc sửa object tại chỗ có thể gây race/side effect. Cân nhắc clone/copy payload trước khi enrich hoặc dùng Transformer tạo **immutable result**, theo yêu cầu hệ thống. Cấu hình `shouldClonePayload` chỉ hữu ích khi payload đáp ứng điều kiện clone tương ứng; không mặc định mọi DTO đều được clone sâu.

## 6. Cấu hình Java DSL: lấy profile rồi enrich payload gốc

Spring Integration Java DSL cung cấp `enrich(...)`; `EnricherSpec` có các tùy chọn như `requestChannel`, `requestPayloadExpression`, `propertyExpression`, `requestTimeout` và `replyTimeout`.

~~~java
@Configuration
@EnableIntegration
class OrderEnrichmentFlow {

    @Bean
    IntegrationFlow enrichOrderWithCustomerProfile() {
        return IntegrationFlow.from("orders.in")
            .filter(OrderDraft.class,
                order -> order.getCustomerId() != null
                    && !order.getCustomerId().isBlank(),
                f -> f.throwExceptionOnRejection(true))
            .enrich(e -> e
                .requestChannel("customer.lookup.requests")
                .requestPayloadExpression("payload.customerId")
                .propertyExpression("customerProfile", "payload")
                .requestTimeout(2_000L)
                .replyTimeout(3_000L))
            .channel("orders.enriched")
            .get();
    }
}
~~~

Một lookup handler **đồng bộ** để demo:

~~~java
@MessageEndpoint
class CustomerLookupHandler {

    @ServiceActivator(
        inputChannel = "customer.lookup.requests")
    public CustomerProfile lookup(String customerId) {
        return switch (customerId) {
            case "C-01" -> new CustomerProfile("C-01", "GOLD");
            case "C-02" -> new CustomerProfile("C-02", "STANDARD");
            default -> throw new IllegalArgumentException(
                "UNKNOWN_CUSTOMER");
        };
    }
}
~~~

Đây là **một flow ví dụ**, các import được lược bỏ. Filter từ chối `customerId` null/blank trước khi tạo Q1; ứng dụng thực còn cần kiểm tra quyền và các trường domain bắt buộc khác. Đầu vào `orders.in` cần một `OrderDraft` đúng kiểu; `orders.enriched` cần consumer thật hoặc một `QueueChannel` trong test. Lookup service chỉ mô phỏng bằng `switch`; thực tế có thể gọi repository, HTTP, database hoặc dịch vụ ngoài với timeout và policy riêng.

Diễn giải từng cấu hình:

- `requestChannel("customer.lookup.requests")` chỉ định nơi gửi Q1.
- `requestPayloadExpression("payload.customerId")` tạo payload Q1 là **mã khách hàng**, không phải nguyên OrderDraft.
- `propertyExpression("customerProfile", "payload")` lấy **payload của R1** và gán vào property `customerProfile` của **M0**.
- `requestTimeout` giới hạn thời gian gửi request khi việc gửi có thể block; `replyTimeout` quy định thời gian chờ reply theo API/cấu hình tương ứng. Không coi chúng là timeout toàn bộ nghiệp vụ.
- Không khai báo `replyChannel` cố định, để gateway nội bộ của Enricher quản lý reply channel theo request.

Sau khi nhận được `CustomerProfile("C-01","GOLD")`, M1 vẫn là OrderDraft của `EV-101/O-101` nhưng có profile tương ứng. **Không lấy kết quả lookup làm payload mới của cả flow** trừ khi đó là hợp đồng mà bạn thực sự muốn.

## 7. Ví dụ XML tương đương và ý nghĩa của reply

Đối với dự án dùng XML namespace, Payload Enricher có dạng:

~~~xml
<int:enricher input-channel="orders.in"
              output-channel="orders.enriched"
              request-channel="customer.lookup.requests"
              request-payload-expression="payload.customerId">
    <int:property name="customerProfile" expression="payload"/>
</int:enricher>
~~~

Theo tài liệu Spring Integration, expression của `property` được đánh giá với **reply message từ request flow** làm root khi cấu hình request channel. Do đó `expression="payload"` ở đây trỏ tới `CustomerProfile` trong reply, rồi gán vào property của OrderDraft gốc.

Không bắt buộc phải khai báo `reply-channel` riêng cho use case đồng bộ này; Enricher có thể tự tạo reply channel tạm. Nếu cấu hình reply channel rõ ràng, phải chắc chắn channel đó có semantics đúng cho **nhiều request đồng thời**, không biến một queue chung thành nơi mọi lời gọi tự cạnh tranh nhận reply của người khác.

Ví dụ XML và Java DSL là **hai biến thể thay thế**; không đăng ký đồng thời cả hai trên cùng input trong một ứng dụng mẫu nếu không chủ ý có competing consumers.

## 8. Đường trả lời nội bộ không đồng nghĩa correlation nghiệp vụ

Một request enrichment có hai mối liên hệ:

**Liên hệ điều phối tạm thời** — Enricher gửi Q1, một handler trả R1 tới `replyChannel` được quản lý để Enricher tiếp tục M0. Trong đường in-process request–reply, đây thường là đủ để hai lời gọi đồng thời không vô tình lấy reply của nhau.

**Liên hệ nghiệp vụ và truy vết** — M0 thuộc `eventId=EV-101`, thực hiện operation `CUSTOMER_LOOKUP` theo policy/version đã biết; cần liên kết với log, metric, lỗi hoặc replay sau restart. Những yếu tố này không tự được giải quyết bằng đối tượng temporary reply channel.

~~~mermaid
flowchart LR
    O["M0: eventId=EV-101"] --> E["Enricher invocation"]
    E --> Q["Q1: customerId=C-01"]
    Q --> L["Lookup"]
    L --> R["R1: CustomerProfile"]
    R --> E
    E --> M["M1: original + profile"]
    O -.->|"Business context"| B["eventId / tenant / trace"]
    Q -.->|"Operation context"| B
    R -.->|"Lookup outcome"| B
~~~

Nếu chỉ cần Content Enricher bên trong một JVM và không cần business process dài, **đừng tự viết map concurrent request→reply ngoài framework** chỉ để thay temporary channel; bạn sẽ tạo thêm race, memory leak và timeout handling.

Ngược lại, nếu lookup có thể trả về hàng giờ sau qua broker hoặc một callback HTTP độc lập, cần một **correlation store** hoặc coordinator rõ ràng; temporary reply channel trong bộ nhớ không phải bản ghi bền vững.

## 9. Giữ context gốc khi request payload chỉ còn một trường

Việc chỉ gửi `customerId` làm payload Q1 có lợi vì service lookup không cần biết cả order. Tuy nhiên, **request message vẫn có thể mang headers của original message**.

Giả sử publisher gửi:

~~~java
OrderDraft order =
    new OrderDraft("EV-101", "O-101", "C-01");

Message<OrderDraft> original = MessageBuilder
    .withPayload(order)
    .setHeader("businessEventId", order.getEventId())
    .setHeader("traceId", "trace-101")
    .build();
~~~

Theo hợp đồng Content Enricher, khi `requestPayloadExpression` được dùng, request payload gửi sang lookup có thể chỉ là `"C-01"`, còn header `businessEventId` và `traceId` vẫn có thể đến request flow. Người xử lý có thể quan sát:

~~~java
@ServiceActivator(inputChannel = "customer.lookup.requests")
public CustomerProfile lookup(Message<String> request) {
    String customerId = request.getPayload();
    Object eventId = request.getHeaders().get("businessEventId");
    // Sử dụng eventId cho trace/log theo chính sách, không để quyết định quyền.
    return customerRepository.findProfile(customerId);
}
~~~

Đây là **biến thể thay thế** cho lookup handler ở mục 6; không tạo hai handler competing trên cùng channel chỉ để minh họa. `customerRepository` là dependency ứng dụng phải tự hiện thực và inject.

**Cảnh báo bảo mật:** header được kế thừa không đương nhiên đáng tin. Nếu adapter inbound cho phép client tự gửi `tenantId`, `isAdmin`, `verifiedCustomerId` hoặc metadata liên quan phân quyền, việc copy header sang lookup **không xác thực chúng**. Identity và tenant đáng tin phải được suy ra tại ranh giới đã xác thực hoặc kiểm chứng lại ở service nhận.

**Cảnh báo rò rỉ:** không copy tất cả `MessageHeaders` ra HTTP/Kafka/AMQP. Đặc biệt, `replyChannel` hoặc `errorChannel` có thể là object nội bộ không serialize phù hợp; token, cookie, header bảo mật và PII không được tự động phát ra mọi transport.

## 10. Khi hai request đồng thời trả reply đảo thứ tự

Một test quan trọng là hai request chạy gần như cùng lúc, nhưng kết quả tra cứu trả **ngược thứ tự**:

~~~mermaid
sequenceDiagram
    participant PA as Publisher A
    participant PB as Publisher B
    participant EA as Enricher call A
    participant EB as Enricher call B
    participant L as Lookup service
    PA->>EA: M0-A (C-01)
    PB->>EB: M0-B (C-02)
    EA->>L: Q-A
    EB->>L: Q-B
    L-->>EB: R-B (trả về nhanh)
    EB-->>PB: M1-B (STANDARD)
    Note over L: Q-A vẫn đang chờ
    L-->>EA: R-A (trả về muộn)
    EA-->>PA: M1-A (GOLD)
~~~

Hai reply không được ghép theo “reply nào đến trước”. Trong đường **request–reply của Content Enricher** có reply channel riêng được framework quản lý, mỗi lần thực thi vẫn giữ mối liên hệ tới lời gọi của mình.

Tuy nhiên, hãy kiểm thử điều này với cấu hình thực tế, đặc biệt nếu:

- Người triển khai tự thay temporary reply channel bằng một **shared queue** mà không có cơ chế select/correlation.
- Request đi qua một outbound gateway và broker, nơi reply được biến thành message mới.
- Lookup service trả về qua một consumer khác hoặc sau restart.
- Một handler tự tạo `Message<?>` mới và bỏ các headers dùng để quay về reply channel.

**Nhiều lời gọi đồng thời không cần giữ thứ tự hoàn tất**, nhưng cần giữ **đúng cặp request–reply**. Đó là bất biến chính của correlation.

## 11. Business request ID khi enrichment đi qua broker

Khi tra cứu qua Kafka/AMQP, request có thể được gửi ở process A, xử lý ở process B và reply trở về process A qua một consumer khác. Lúc này cần hợp đồng correlation rõ ràng:

~~~java
record CustomerLookupRequest(
    String enrichmentRequestId,
    String eventId,
    String orderId,
    String tenantId,
    String customerId
) {}

record CustomerLookupReply(
    String enrichmentRequestId,
    String tenantId,
    String customerId,
    String tier,
    String outcome
) {}
~~~

**Đây là contract wire-level ứng dụng**, không phải class framework tự sinh. `enrichmentRequestId` nhận diện một logical lookup. Khi retry, cần công bố chính sách: giữ cùng ID để idempotent retries hay dùng attempt ID riêng gắn tới một logical request ID. Không dùng một `UUID` mới mỗi lần retry rồi bỏ mất liên kết với lần xử lý trước.

Một bản pending state có thể lưu:

~~~text
enrichmentRequestId = ER-001
eventId             = EV-101
orderId             = O-101
tenantId            = tenant-A
customerId          = C-01
status              = WAITING
createdAt           = ...
deadline            = ...
policyVersion       = 3
originalPayloadRef  = location in durable store
~~~

Khi nhận reply, coordinator cần:

1. Tìm bản ghi bằng `enrichmentRequestId`.
2. Xác thực nguồn reply và **kiểm tra tenant/customerId khớp** với request gốc.
3. Kiểm tra deadline, trạng thái và số lần xử lý.
4. Dùng chuyển trạng thái có điều kiện (ví dụ `WAITING → COMPLETED`) để xử lý duplicate.
5. Lấy original payload được lưu bền vững, kết hợp dữ liệu hợp lệ rồi phát enriched event đúng một lần **theo hiệu lực nghiệp vụ**, sử dụng idempotency/outbox khi cần.

Tùy use case, **correlation store** có thể là bảng database, message store, workflow engine hoặc coordinator riêng. Nó không nhất thiết là một Spring Integration Aggregator, vì Aggregator chủ yếu ghép các message thành group theo correlation key/release strategy, còn việc khôi phục **M0 + R1** có thể cần trạng thái riêng cho original và deadline.

## 12. Không serialize `replyChannel` tạm để dùng làm correlation trên wire

Một sai lầm nguy hiểm:

~~~text
Request gửi vào broker:
  payload.customerId=C-01
  headers.replyChannel=<TemporaryReplyChannel Java object>
~~~

Temporary reply channel là một cấu trúc điều phối trong JVM, không phải địa chỉ durable mà process khác có thể tự resolve. Nếu message mapper cố serialize toàn bộ headers, có thể gặp lỗi, làm lộ metadata nội bộ hoặc tạo giả định sai rằng process B có thể gửi trực tiếp vào object ở process A.

Thay vào đó, hãy công bố **return address broker** hoặc reply topic/queue được hỗ trợ bởi adapter và **correlation key kiểu dữ liệu đơn giản**:

~~~text
request.topic = customer.lookup.requests
request.enrichmentRequestId = ER-001
request.replyDestination = customer.lookup.replies

reply.topic = customer.lookup.replies
reply.enrichmentRequestId = ER-001
~~~

Broker adapter/gateway request–reply của Spring Integration có thể cung cấp cơ chế correlation riêng theo công nghệ và phiên bản. Nếu dùng chúng, kiểm chứng chính xác **mapping header trên wire, reply destination, timeout, reply container và behavior sau restart** trước khi tự viết coordinator. Không suy diễn rằng mọi gateway có cùng cách xác định reply hoặc đều durable.

**Phân biệt:** `replyChannel` gốc cho Gateway trong JVM, reply address ở broker và `enrichmentRequestId` trên wire là ba khái niệm khác nhau. Một thiết kế đúng phải ánh xạ được chúng ở **ranh giới transport** mà không để client điều khiển một channel nội bộ tùy ý.

## 13. Multi-tenant: correlation đúng ID nhưng sai tenant vẫn là lỗi

Giả sử tenant A và tenant B đều có `customerId=C-01`. Nếu lookup service tra cứu theo `customerId` mà bỏ tenant, hệ thống có thể đưa profile của tenant B vào order thuộc tenant A, dù `enrichmentRequestId` vẫn ghép đúng lời gọi.

Do đó correlation và authorization là **hai kiểm soát bổ sung**:

| Kiểm tra | Câu hỏi |
|---|---|
| Correlation | Reply này thuộc request nào? |
| Tenant scope | Request và reply có cùng tenant đã được xác thực không? |
| Domain identity | `customerId` trong reply có khớp khóa đã hỏi không? |
| Freshness/version | Profile trả về có đúng phiên bản hoặc thời điểm nghiệp vụ chấp nhận không? |
| Authorization | Người gọi/service có được xem và sử dụng profile này không? |

Nếu profile quyết định giá, hạn mức tín dụng hoặc quyền truy cập, không nên tin mọi giá trị reply chỉ vì “nhận được từ channel”. Cần xác thực service trả lời, schema, giá trị và các bất biến nghiệp vụ liên quan.

Khi lưu pending state, khóa/unique index nên bảo vệ đúng phạm vi; có thể dùng `(tenantId, enrichmentRequestId)` cùng xác minh nguồn. Việc sử dụng một ID global unique vẫn không thay thế kiểm tra tenant.

## 14. Cách xử lý reply không khớp request

Một reply bị sai correlation có thể do bug, producer gửi lỗi, replay cũ, khách hàng đổi tenant hoặc bị giả mạo.

| Trường hợp | Điều không nên làm | Cách xử lý gợi ý |
|---|---|---|
| Không thấy `enrichmentRequestId` trong pending store | Gắn vào request đang chờ đầu tiên | Quarantine/metric unknown correlation |
| Reply có customerId khác request | Bỏ qua customerId và vẫn enrich | Reject mismatch, kiểm tra service/schema |
| Tenant trong reply khác tenant gốc | Enrich chéo tenant | Security error, không phát message |
| Reply trễ sau timeout | Tự động mở lại original đã fail | Áp dụng late-reply policy; không tạo double completion |
| Hai reply cùng request ID | Ghi đè trạng thái và phát hai output | Dedupe/conditional state transition |
| Reply dùng schema không hỗ trợ | Cố cast để lấy tier | Version gate/quarantine |
| Reply hợp lệ nhưng thiếu tier | Tự đặt GOLD | Default/reject theo contract |

**Không sử dụng thứ tự, payload type hoặc key tra cứu làm cách ghép duy nhất.** Những thuộc tính đó có thể trùng lặp giữa nhiều request; cần một correlation identity thật sự phù hợp.

Khi request dùng cùng customerId nhưng thuộc hai order khác nhau, caching có thể tái sử dụng giá trị profile; **cache key** và **enrichment request correlation** vẫn là hai khái niệm khác nhau. Cache có thể trả cùng profile cho hai request, còn hai original message phải nhận kết quả riêng.

## 15. Timeout: chờ reply bao lâu và sau timeout phải làm gì?

Một Content Enricher gọi remote service có thể dừng ở nhiều điểm:

~~~mermaid
flowchart TD
    EN["Enricher gửi Q1"] --> SEND{"Gửi vào requestChannel"}
    SEND -->|"Không gửi được"| SE["Send failure / request timeout"]
    SEND -->|"Đã gửi"| WAIT["Chờ lookup reply"]
    WAIT -->|"Reply hợp lệ"| DONE["Enrich M0 → M1"]
    WAIT -->|"Timeout"| TO["Reply timeout / failure policy"]
    WAIT -->|"Exception"| ER["Error path / fallback policy"]
    TO --> LATE["Nếu reply đến sau: late-reply policy"]
~~~

**`requestTimeout`** giới hạn thời gian ở thao tác gửi có thể block; **`replyTimeout`** giới hạn thời gian chờ reply. Hai giá trị này không tự thay timeout của HTTP client, query database, Kafka producer/consumer hoặc toàn bộ Gateway bên ngoài.

Ngoài ra, mặc định timeout và cách trả lỗi khi timeout **có thể phụ thuộc phiên bản và cấu hình**. Không dựa vào một con số mặc định không kiểm chứng; khai báo timeout theo SLA và test hành vi thật trên stack của dự án.

Sau timeout có ba chiến lược thường gặp:

1. **Fail enrichment:** không phát M1, tạo lỗi có thể truy vết, cho caller hoặc error handler quyết định tiếp.
2. **Fallback có hợp đồng:** chỉ khi nghiệp vụ cho phép, dùng dữ liệu dự phòng như tier `UNKNOWN`, gắn provenance/quality flag và giảm quyền xử lý tương ứng.
3. **Deferred completion:** lưu pending state và hoàn tất bất đồng bộ khi reply đến, với deadline rõ ràng; thường cần process manager/store thay vì giữ request HTTP mở vô hạn.

**Timeout không chứng minh lookup chưa chạy.** Remote service có thể đã xử lý Q1 và gửi R1 ngay sau deadline. Retry phải cân nhắc idempotency, không được tự động biến một kết quả trễ thành lần enrich thứ hai.

## 16. Retry, duplicate và idempotency cho enrichment

Giả sử request Q1 gặp lỗi mạng. Client retry và tạo Q1' giống Q1. Lookup là thao tác đọc thuần thì tác động nghiệp vụ có thể thấp; nhưng nếu service lookup còn ghi audit, trừ quota hoặc cập nhật trạng thái, retry có thể tạo side effect.

**Chiến lược khuyến nghị:**

- Tách **logical enrichment request ID** khỏi attempt ID khi cần thống kê nhiều lần thử.
- Giữ `eventId` của original không đổi khi redelivery.
- Nếu gửi request qua broker, persist state/outbox để không tạo request trùng ngoài ý muốn sau crash giữa database commit và publish.
- Nếu remote lookup là idempotent GET, vẫn cần xử lý **duplicate replies** và deadline ở coordinator.
- Phân loại lỗi: timeout mạng có thể retry giới hạn; `CUSTOMER_NOT_FOUND` hoặc tenant mismatch thường không retry vô hạn.
- Khi đã phát enriched output, đánh dấu completion bằng thao tác có điều kiện để tránh phát lại cùng business outcome, hoặc dựa vào downstream idempotency key.

Một mô hình trạng thái:

~~~mermaid
stateDiagram-v2
    [*] --> WAITING: gửi lookup request
    WAITING --> COMPLETED: reply đúng correlation + hợp lệ
    WAITING --> FAILED: lỗi không thể phục hồi
    WAITING --> TIMED_OUT: quá deadline
    TIMED_OUT --> RETRIED: retry có chủ đích
    RETRIED --> COMPLETED: reply hợp lệ
    RETRIED --> FAILED: hết số lần thử
    COMPLETED --> [*]
    FAILED --> [*]
~~~

Đây là **state machine minh họa của ứng dụng**, không phải behavior tự động của một `ContentEnricher` đơn giản. Khi production sử dụng broker và durable store, định nghĩa rõ cách xử lý `late reply`, trạng thái terminal và idempotency tại mọi transition.

## 17. Header propagation: giữ đủ để ghép, nhưng không quá nhiều

Message gốc có thể mang các header:

~~~text
eventId, tenantId, traceId, correlationId,
replyChannel, errorChannel, sequenceNumber, sequenceSize,
Authorization, Cookie, rawSourceHeader
~~~

Không phải tất cả đều nên đi vào lookup hoặc được đưa trở lại M1.

| Header | Trong M0 | Khi gửi Q1 vào subflow | Khi phát M1/outbound |
|---|---|---|---|
| `eventId`/business ID | Giữ | Có thể truyền để trace/idempotency | Giữ theo hợp đồng |
| `tenantId` tin cậy | Giữ | Gửi nếu lookup cần scope và xác thực | Giữ trong vùng được phép |
| `traceId` | Giữ | Chuyển qua tracer/header mapper phù hợp | Giữ nếu an toàn |
| `correlationId` của Splitter | Giữ | Không ghi đè bằng lookup request ID | Giữ cho Aggregator |
| `replyChannel` nội bộ | Theo gateway flow | Enricher quản lý reply tạm | Không serialize ra broker tùy tiện |
| `errorChannel` | Theo error policy | Không cho external producer ghi đè | Theo ranh giới lỗi |
| `Authorization`/`Cookie` | Có thể có tại ingress | Chỉ chuyển qua cơ chế xác thực được thiết kế | Không copy bừa bãi |
| `enrichmentRequestId` | Không nhất thiết tồn tại | Tạo khi đi external async | Giữ trong audit/log; không để overwrite business correlation |

**Không dùng `MessageBuilder.copyHeaders(...)` mà không suy nghĩ** khi tạo external request. Thay vào đó, tạo một wire contract cụ thể từ các trường được phép. Khi trả về M1, bảo toàn original context mà downstream cần, nhưng không merge reply headers theo kiểu “reply thắng tất cả”.

Nếu reply service gửi một header trùng tên với `tenantId` hoặc `correlationId`, hãy quyết định rõ header nào được phép ghi đè và kiểm tra nguồn. Đặc biệt khi dùng `headerExpression` trong Enricher, semantics `overwrite` và expression root cần kiểm tra đúng API/phiên bản; **không tự đặt các header điều phối quan trọng từ untrusted reply**.

## 18. Phân biệt Content Enricher, Header Enricher, Transformer và Aggregator

| Pattern | Nhiệm vụ | Correlation cần xem xét |
|---|---|---|
| **Header Enricher** | Bổ sung/chuẩn hóa metadata | Không tự gọi lookup; tránh thay headers quan trọng |
| **Content/Payload Enricher** | Lấy dữ liệu bổ sung rồi gán vào payload gốc | M0 ↔ Q1 ↔ R1, đặc biệt khi remote/async |
| **Transformer** | Đổi payload A thành B theo hợp đồng | Giữ event/correlation khi tạo message mới |
| **Request–Reply Gateway** | Cung cấp đường gọi và nhận kết quả | `replyChannel`, timeout, error propagation |
| **Splitter** | Tạo message con từ message gốc | `correlationId`, sequence metadata |
| **Aggregator** | Gom nhiều kết quả theo nhóm | Correlation key, release strategy, timeout |
| **Routing Slip** | Điều phối chuỗi channel | Không tự ghép remote reply với original |

Content Enricher thường chờ **một reply tra cứu** để bổ sung **một original**. Nếu cần gọi **ba dịch vụ độc lập** và chỉ trả kết quả khi đủ ba, đây còn là bài toán **Scatter-Gather/Aggregation**; cấu hình một Enricher rồi kỳ vọng nó tự gom mọi reply là không đủ.

Nếu chỉ cần bổ sung một giá trị cố định hoặc suy ra từ M0, không nhất thiết phải tạo remote request. Có thể dùng một Transformer hoặc header/payload enricher không có `requestChannel` theo mục đích.

## 19. Với Splitter/Aggregator: hai cấp correlation không được nhập nhằng

Một order được tách thành ba line items. Mỗi line lại cần tra cứu thông tin SKU:

~~~mermaid
flowchart LR
    ORD["Order O-101"] --> SPLIT["Splitter"]
    SPLIT --> L1["Line 1"]
    SPLIT --> L2["Line 2"]
    SPLIT --> L3["Line 3"]
    L1 --> E1["Enricher Q-1/R-1"]
    L2 --> E2["Enricher Q-2/R-2"]
    L3 --> E3["Enricher Q-3/R-3"]
    E1 --> AG["Aggregator theo order correlation"]
    E2 --> AG
    E3 --> AG
    AG --> RES["OrderWithSkuDetails"]
~~~

Ở đây tồn tại **hai cấp**:

1. **Order-group correlation:** ghép các line thuộc Order O-101, dùng `correlationId` và `sequenceSize` do Splitter/Aggregator quản lý.
2. **Per-line enrichment correlation:** ghép mỗi lookup reply với đúng line item đang chờ, ví dụ `enrichmentRequestId` cho SKU-1, SKU-2, SKU-3 khi qua broker.

Đừng ghi đè `correlationId` của Splitter bằng `enrichmentRequestId`. Nếu làm vậy, Aggregator có thể xem ba line là ba group khác nhau hoặc chờ mãi.

**Khi một enrichment reply thất bại:**

- Nếu một line không được phát tiếp, Aggregator có thể chờ thiếu message so với sequence size.
- Nếu nghiệp vụ cho phép partial result, chuyển lỗi thành một **failure result có correlation của order và line**.
- Nếu cần fail toàn bộ order, coordinator phải truyền trạng thái thất bại, cancel/timeout những phần còn lại và ngăn side effect không mong muốn.
- Thêm release strategy/group timeout/expired-message policy phù hợp; không đánh dấu hoàn tất vì một nhánh tới sớm.

## 20. Tính nhất quán dữ liệu lookup: profile có thể thay đổi giữa hai lần thử

Ngay cả khi reply được ghép **đúng ID**, kết quả enrichment vẫn có thể không phù hợp thời điểm nghiệp vụ.

Ví dụ, Order EV-101 tạo lúc 09:00, lookup trả profile tier GOLD lúc 09:00:01. Khi replay sau một ngày, customer đã đổi thành STANDARD. Nếu dùng giá trị hiện tại cho cùng order, tổng tiền/ưu đãi có thể thay đổi.

Thiết kế cần quyết định:

- Dùng **current snapshot** tại thời điểm xử lý lại.
- Dùng **version/as-of timestamp** tại thời điểm event xảy ra.
- Lưu **enrichment result snapshot** trong event/process state để replay deterministically.
- Dùng **ETag/version của dữ liệu trả về** và reject nếu phiên bản không phù hợp.

Đối với các nghiệp vụ quan trọng (giá, rủi ro, hạn mức, thuế), nên ghi lại **provenance** của dữ liệu enrichment: nguồn, version, thời điểm, request ID và policy đã áp dụng. Correlation đảm bảo *ghép đúng đối tượng*, còn versioning/freshness đảm bảo *dùng đúng phiên bản dữ liệu*.

## 21. Error channel và recovery: không đánh đồng mọi lỗi với “không tìm thấy”

Một Content Enricher có thể thất bại ở nhiều ranh giới:

| Lỗi | Nguyên nhân | Hướng xử lý |
|---|---|---|
| Request không gửi được | Channel đầy, adapter dừng | Retry có giới hạn / backpressure |
| Reply timeout | Lookup chậm, mất reply | Deadline/late reply policy |
| `CUSTOMER_NOT_FOUND` | Khóa không có dữ liệu | Reject nghiệp vụ hoặc fallback được công bố |
| Reply sai schema | Service trả kiểu không mong đợi | Version gate/quarantine |
| Reply sai correlation/tenant | Ghép sai hoặc giả mạo | Security/reconciliation error, không enrich |
| Property expression lỗi | Reply thiếu field, kiểu không phù hợp | Sửa contract/Transformer |
| Downstream Router/handler lỗi | Enrichment xong nhưng bước sau thất bại | Error/retry policy của downstream |

Spring Integration Content Enricher có cấu hình `errorChannel` trong những trường hợp lỗi xảy ra trong request subflow, có thể giúp tạo đường trả lời thay thế cho enrichment. **Không nên giả định khai báo error channel tự động tạo fallback đúng cho mọi exception**. Nếu muốn fallback, hãy định nghĩa rõ type của reply thay thế, thời hạn và chính sách cho những field thiếu.

Trong luồng đồng bộ, exception có thể truyền ngược caller/Gateway. Với queue, executor, poller hoặc broker, lỗi có thể xảy ra sau khi producer đã gửi và phải được xử lý tại **async error boundary** phù hợp.

**Đừng retry vô hạn** request không hợp lệ, tenant mismatch hoặc lookup key không tồn tại. Lỗi validation vĩnh viễn không biến mất khi đọc lại cùng event. Ngược lại, timeout mạng có thể là tạm thời nhưng vẫn cần giới hạn số lần, jitter/backoff và kiểm soát duplicate.

## 22. Correlation store phải quản lý cả deadline và cleanup

Một `ConcurrentHashMap<requestId, original>` có thể đủ để demo trong một JVM, nhưng production cần đánh giá:

- **Durability:** service restart khi đang chờ reply có làm mất original message?
- **Capacity:** có giới hạn số pending requests theo tenant/worker hay không?
- **Deadline:** request nào quá hạn, ai chuyển sang TIMED_OUT và ai thông báo caller?
- **Late reply:** reply sau timeout bị bỏ, cập nhật trạng thái, hay được phép recovery?
- **Duplicate:** xử lý hai reply giống nhau mà không phát M1 hai lần?
- **Cleanup:** sau success/failure/timeout có xóa pending record và giảm tài nguyên không?
- **Privacy:** original payload/reference có chứa PII không, cần mã hóa/retention ra sao?
- **Consistency:** state update và phát M1 có dùng outbox/idempotency để tránh mất sự kiện giữa chừng?

Nếu request–reply hoàn toàn trong JVM và hoàn tất nhanh, framework đã quản lý correlation lời gọi; không cần mang tất cả phức tạp trên vào một use case đơn giản. **Chỉ mở rộng thành pending store khi yêu cầu recovery/durability/concurrency vượt qua giới hạn local reply**.

## 23. Unit test: validate phép ghép enrichment trước khi sửa original

Với mẫu request qua broker, nên tách một validator thuần Java để kiểm tra R1 thực sự thuộc Q1:

~~~java
record PendingLookup(
    String enrichmentRequestId,
    String tenantId,
    String customerId
) {}

final class LookupReplyValidator {
    void validate(PendingLookup pending, CustomerLookupReply reply) {
        if (pending == null || reply == null) {
            throw new IllegalArgumentException("UNKNOWN_REQUEST");
        }
        if (!Objects.equals(
                pending.enrichmentRequestId(),
                reply.enrichmentRequestId())) {
            throw new IllegalArgumentException("CORRELATION_MISMATCH");
        }
        if (!Objects.equals(
                pending.tenantId(), reply.tenantId())) {
            throw new IllegalArgumentException("TENANT_MISMATCH");
        }
        if (!Objects.equals(
                pending.customerId(), reply.customerId())) {
            throw new IllegalArgumentException("CUSTOMER_MISMATCH");
        }
    }
}
~~~

Ví dụ JUnit 5:

~~~java
@Test
void rejectsCrossTenantReplyEvenWithMatchingRequestId() {
    PendingLookup pending =
        new PendingLookup("ER-1", "tenant-A", "C-01");
    CustomerLookupReply suspicious = new CustomerLookupReply(
        "ER-1", "tenant-B", "C-01", "GOLD", "OK");

    assertThrows(IllegalArgumentException.class,
        () -> new LookupReplyValidator()
            .validate(pending, suspicious));
}

@Test
void rejectsWrongCustomerForSameRequestId() {
    PendingLookup pending =
        new PendingLookup("ER-1", "tenant-A", "C-01");
    CustomerLookupReply suspicious = new CustomerLookupReply(
        "ER-1", "tenant-A", "C-02", "GOLD", "OK");

    assertThrows(IllegalArgumentException.class,
        () -> new LookupReplyValidator()
            .validate(pending, suspicious));
}
~~~

Test ở trên xác minh **bất biến ứng dụng**, không kiểm tra tính đúng của temporary reply channel. Trong production, phải bổ sung authentication của producer reply, kiểm tra outcome/version, deadline và dedupe bằng thao tác có điều kiện trong durable store.

## 24. Integration test: hai order đồng thời không được đổi profile cho nhau

Tạo Spring test context với Content Enricher Java DSL và lookup handler. Đăng ký `orders.enriched` làm `QueueChannel` **trong test-only configuration**; production consumer không đồng thời lấy từ queue test.

Ví dụ phần thân một integration test:

~~~java
@Autowired
ApplicationContext context;

@Test
void enrichesCorrectOriginalOrder() {
    MessageChannel input =
        context.getBean("orders.in", MessageChannel.class);
    PollableChannel output =
        context.getBean("orders.enriched", PollableChannel.class);

    OrderDraft original = new OrderDraft(
        "EV-101", "O-101", "C-01");
    Message<OrderDraft> message = MessageBuilder
        .withPayload(original)
        .setHeader("businessEventId", "EV-101")
        .build();

    assertTrue(input.send(message));
    Message<?> enrichedMessage = output.receive(2_000);
    assertNotNull(enrichedMessage);

    OrderDraft enriched =
        (OrderDraft) enrichedMessage.getPayload();
    assertEquals("O-101", enriched.getOrderId());
    assertEquals("C-01",
        enriched.getCustomerProfile().customerId());
    assertEquals("GOLD",
        enriched.getCustomerProfile().tier());
    assertEquals("EV-101",
        enrichedMessage.getHeaders().get("businessEventId"));
}
~~~

Đây là **integration test minh họa**, cần gắn các flow/handler và queue test vào một Spring context thực. `send()` thành công không đủ chứng minh Enricher đã hoạt động; phải kiểm tra output payload và header.

**Test concurrency** nên:

1. Tạo hai order `O-101/C-01` và `O-102/C-02`.
2. Gửi từ hai publisher threads qua một điểm ingress có thể hỗ trợ xử lý đồng thời.
3. Dùng latch/future để lookup C-01 hoàn tất **sau** lookup C-02; không phụ thuộc vào `Thread.sleep` để ép thứ tự.
4. Nhận hai enriched outputs, ánh xạ theo `eventId`/`orderId` và assert profile chính xác.
5. Gửi thêm duplicate/late reply nếu test một coordinator qua broker; assert chỉ có kết quả cuối được phép.

Không chỉ assert “đã nhận hai message”; hai message có thể đã bị **đảo profile** mà số lượng vẫn bằng hai.

## 25. Ma trận kiểm thử end-to-end

| Test | Thiết lập | Kỳ vọng |
|---|---|---|
| Một request đồng bộ | M0 có C-01; R1 trả GOLD | M1 giữ O-101 và có GOLD |
| Hai request song song | R-B đến trước R-A | M1-A gắn profile A, M1-B gắn profile B |
| Request payload subset | Chỉ `customerId` gửi làm payload Q1 | Header/lookup nhận đúng contract |
| Original header | `businessEventId=EV-A` | M1 giữ ID đã công bố |
| Duplicate reply | Hai R cùng `enrichmentRequestId` | Không phát hai kết quả nghiệp vụ |
| Unknown correlation ID | R không có pending request | Quarantine/ignore có metric, không gắn đại |
| Cross-tenant reply | Request tenant A, reply tenant B | Reject an toàn, không lộ profile |
| Customer mismatch | Q hỏi C-01, R trả C-02 | Reject, không enrich |
| Timeout | Lookup không trả reply trong hạn | Error/fallback theo policy; không chờ vô hạn |
| Late reply | R đến sau deadline | Không tự tạo double completion |
| Lookup error | Remote ném exception | Đúng error boundary/retry classification |
| Unexpected reply type | Reply không có CustomerProfile | Contract/validation error |
| Missing lookup key | `customerId=null` | Reject trước request; không gọi service bằng null |
| Splitter/Aggregator | Ba line có ba lookup khác nhau | Giữ order correlation; không lẫn với request ID |
| Cross-JVM serialization | Q/R qua broker | Không serialize internal reply channel tùy tiện |
| Restart khi pending | Process chết trước khi có R | Recovery theo durability đã công bố |
| Profile version | Replay cùng order vào ngày khác | Snapshot/version policy đúng yêu cầu nghiệp vụ |

Ngoài unit/integration test, nên có **contract test** tại broker hoặc HTTP adapter thực: kiểm tra header mapper, encoding, reply destination, request ID, tenant scope và schema version. Mock service trả trực tiếp Java object không kiểm chứng được mọi lỗi serialize/deserialize trên wire.

## 26. Quan sát correlation trong production

Một trace hữu ích có thể kể lại hành trình:

~~~text
EV-101 / O-101
  → Enricher start, operation=CUSTOMER_LOOKUP, requestId=ER-001
  → Request sent, destination=customer.lookup.requests
  → Reply received, requestId=ER-001, customer=C-01
  → Validation passed, tenant matched
  → Profile applied, tier=GOLD
  → orders.enriched, downstream result
~~~

Các metric đề xuất:

| Tín hiệu | Phát hiện vấn đề |
|---|---|
| `enrichment.request.count` | Lưu lượng lookup |
| `enrichment.reply.duration` | Độ trễ request–reply |
| `enrichment.pending.count` | Số request đang đợi |
| `enrichment.timeout.count` | Mất hoặc reply quá chậm |
| `enrichment.correlation.mismatch.count` | Reply sai khóa hoặc thiếu pending |
| `enrichment.duplicate.reply.count` | Reply bị phát lặp |
| `enrichment.late.reply.count` | Reply đến sau deadline |
| `enrichment.fallback.count` | Số lần phải dùng dữ liệu dự phòng |
| `enrichment.error.count` theo reason | Lỗi kết nối, schema, permission, mapping |
| `enrichment.result.age` | Tuổi dữ liệu lookup khi được áp dụng |

Đây là **tên metric đề xuất**, không khẳng định là meter mặc định của Spring Integration. Không dùng `eventId`/`requestId`/`customerId` làm metric tag vì gây cardinality lớn và rủi ro quyền riêng tư. Để tra một request cụ thể, sử dụng **tracing và structured log có kiểm soát**.

Khi thấy enrichment bị timeout, điều tra theo thứ tự: **M0 được chấp nhận → Q1 đã gửi → request ID → lookup thực thi → R1 được phát → reply destination → correlation mapping → apply property → M1 đến downstream**. Phân biệt “không có reply” với “có reply nhưng bị bỏ vì mismatch/timeout”.

## 27. Các hiểu lầm phổ biến

**“Chỉ cần customerId giống nhau là reply đúng original.”** Sai. Nhiều order hoặc tenant có thể dùng cùng customerId; cần request identity và tenant scope.

**“MessageHeaders.ID là enrichmentRequestId bền vững.”** Sai. Message có thể được tạo lại, retry hoặc qua adapter khiến ID khác.

**“Content Enricher mặc định luôn cần bảng pending request.”** Không. Trong đường request–reply cùng JVM, Enricher dùng cơ chế gateway/reply channel để nối reply với lời gọi.

**“Thu nhỏ request payload sẽ tự loại mọi header nhạy cảm.”** Sai. Request message có thể vẫn mang original headers; outbound mapper phải có policy riêng.

**“replyChannel là correlationId nghiệp vụ.”** Sai. Một bên điều phối return address nội bộ, một bên nhận diện request/group.

**“Có reply thì luôn an toàn để gán vào M0.”** Sai. Cần xác minh tenant, customer identity, schema, outcome, freshness và authorization khi cần.

**“Dùng một queue reply chung là tương đương temporary reply channel.”** Không tự động. Cần resolver/correlation thật để nhiều lời gọi không lấy nhầm reply.

**“Enricher timeout nghĩa là lookup chưa tạo side effect.”** Sai. Service có thể đã xử lý hoặc reply đang trên đường.

**“Đổi correlationId của Splitter thành requestId giúp ghép nhanh hơn.”** Sai. Làm vậy có thể phá Aggregator của order.

**“Reply duplicate nghĩa là phải enrich hai lần.”** Sai. Cần idempotency và state transition có điều kiện.

**“Caching profile và correlating reply là cùng một bài toán.”** Sai. Cache tái sử dụng dữ liệu, correlation ghép đúng kết quả với từng original/request.

**“Có errorChannel sẽ tự chọn fallback hợp lệ cho mọi lỗi.”** Sai. Hợp đồng reply thay thế và chính sách retry/failure vẫn phải thiết kế rõ.

## 28. Bài thực hành: chứng minh correlation đúng khi reply đảo thứ tự

Thực hành xây dựng flow **OrderCustomerEnrichment**:

1. Tạo `OrderDraft` có `eventId, orderId, customerId` và property `customerProfile` cần enrich.
2. Cấu hình Content Enricher gửi `customerId` qua `customer.lookup.requests`, dùng `propertyExpression("customerProfile","payload")`.
3. Viết lookup Service Activator trả `CustomerProfile` và cố tình tạo độ trễ khác nhau bằng latch trong test.
4. Gửi hai order song song, cho C-02 trả trước C-01; xác nhận profile không bị gắn nhầm.
5. Quan sát original headers ở request message và output message; thiết kế whitelist khi chuyển sang broker.
6. Thêm timeout và simulated lookup failure; kiểm tra error path, không hiểu nhầm `send()` thành thành công nghiệp vụ.
7. Mở rộng qua broker: phát `CustomerLookupRequest/Reply` có `enrichmentRequestId` và pending state theo tenant.
8. Thử unknown/duplicate/late/cross-tenant reply; chỉ phát enriched result khi correlation và validation pass.
9. Cho ba line item của một order đi qua enrichment riêng, rồi Aggregator; giữ nguyên order correlation khi tạo per-line request ID.
10. Đo request latency, pending, mismatch, timeout, error và tỷ lệ sử dụng fallback; gắn trace để điều tra từng event.

**Tiêu chí hoàn thành:** M1 giữ đúng original identity và nội dung; reply đến ngược thứ tự không bị ghép nhầm; pending state không rò rỉ sau timeout/restart theo chính sách; không serialize framework reply channel như business ID; retry/duplicate không làm phát output sai hoặc lặp; test phân biệt correlation của enrichment với correlation của Aggregator.

## 29. Ghi nhớ

**Correlation giữa message gốc và request enrichment** có hai lớp: **correlation kỹ thuật** của cơ chế request–reply để đúng R1 quay về đúng lần gọi Enricher đang chờ, và **correlation nghiệp vụ** để liên kết event/order/tenant/operation qua nhiều tiến trình, lần thử và hệ thống quan sát.

Trong một Content Enricher thông thường của Spring Integration, framework có thể dùng **temporary reply channel** để phục vụ việc ghép request–reply. Khi tích hợp với broker, callback hoặc workflow dài, hãy thiết kế **enrichmentRequestId + pending state + deadline + validation + idempotency** theo hợp đồng của ứng dụng. Giữ original business identity, header correlation cho **Splitter/Aggregator**, kiểm soát header propagation, và không coi customerId hay MessageHeaders.ID là khóa ghép duy nhất.

Nhờ đó, các bước **Gateway → Content Enricher → Router/Filter/Transformer → handler hoặc Aggregator** có thể duy trì dữ liệu đúng đối tượng dù xử lý bất đồng bộ, có retry, error channel hoặc thay đổi thứ tự hoàn tất.

### Tài liệu tham khảo

- Spring Integration Reference, **Content Enricher**: https://docs.spring.io/spring-integration/reference/content-enrichment.html
- Spring Integration Java DSL API, **EnricherSpec**: https://docs.spring.io/spring-integration/docs/latest-ga/api/org/springframework/integration/dsl/EnricherSpec.html
- Enterprise Integration Patterns, **Content Enricher**: https://www.enterpriseintegrationpatterns.com/patterns/messaging/DataEnricher.html
