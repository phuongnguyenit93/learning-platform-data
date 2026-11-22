# Gateway trả null khi không có reply

## 1. Tình huống: đã gửi request, nhưng không có phản hồi để trả về Java

Một dịch vụ đặt hàng muốn truy vấn trạng thái xử lý của đơn qua Spring Integration:

~~~java
OrderStatusReply reply = orderStatusGateway.lookup(
        new OrderStatusQuery("REQ-901", "ORD-901"));

// Tại đây reply có thể là null nếu Gateway không nhận được
// một reply phù hợp trong thời gian chờ theo cấu hình.
~~~

Người viết application service có thể mặc định: “Đã gọi phương thức trả `OrderStatusReply` thì chắc chắn nhận `OrderStatusReply`”. Trong kiến trúc messaging, giả định đó không an toàn. Request có thể **được dispatch thành công**, nhưng downstream không gửi reply, gửi quá muộn, bị Filter loại, xử lý vào một nhánh one-way hoặc phát sinh lỗi trên một async boundary.

**Messaging Gateway trả `null` khi không có reply** là một tình huống cần hiểu ở đúng ranh giới: phương thức Java kiểu tham chiếu yêu cầu một giá trị phản hồi, trong khi flow không đưa được một reply message về gateway trước khi điều kiện chờ kết thúc. Tùy configuration và execution path, Gateway có thể trả `null`, ném exception hoặc có cách biểu diễn lỗi khác. Không được xem mọi trường hợp “không thấy reply” đều là `null`.

~~~mermaid
sequenceDiagram
    participant A as Application Service
    participant G as Messaging Gateway
    participant R as Request Channel
    participant H as Service Handler
    A->>G: lookup(query)
    G->>R: Send request + reply address
    R->>H: Deliver request
    H-->>H: Process without sending reply
    Note over G,H: No reply is delivered to Gateway
    G-->>A: null after configured waiting behavior
~~~

Bài nằm trong chương **Messaging gateway**, thuộc module `SPRING_INTEGRATION_PATTERN`. Mục tiêu module là học triển khai Enterprise Integration Patterns bằng Spring Integration để xây dựng luồng message ít phụ thuộc, dễ mở rộng; thực hành Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation, đồng thời kiểm thử và theo dõi các nhánh xử lý.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **request–reply Gateway trả `null`** với **one-way Gateway khai báo `void`**.
2. Giải thích vì sao “request đã được nhận” không đồng nghĩa “reply đã đến”.
3. Hiểu vai trò của `replyChannel`, thời gian chờ reply, `DirectChannel`, `ExecutorChannel`, `QueueChannel` và endpoint trả `null`.
4. Phân loại **không có reply**, **reply đến muộn**, **reply bị mất**, **Filter discard**, **exception** và **business result NOT_FOUND**.
5. Thiết kế Gateway API an toàn: response kiểu tham chiếu, timeout có giới hạn và business status rõ ràng.
6. Viết ví dụ `@MessagingGateway`, Spring Integration Java DSL và JUnit 5 để kiểm tra cả reply và no-reply.
7. Thiết kế correlation, idempotency, retry, error channel và observability mà không làm lặp side effect.

## 2. Phân biệt ba trường hợp dễ bị hiểu nhầm

### 2.1. One-way Gateway có phương thức `void`

~~~java
@MessagingGateway
interface OrderCommandGateway {
    @Gateway(requestChannel = "orders.commands")
    void submit(OrderCommand command);
}
~~~

Gateway này **không có giá trị trả về** trong contract Java. Người gọi không có biến kiểu `OrderStatusReply` để kiểm tra `null`; `void` là lựa chọn chủ đích cho giao tiếp không yêu cầu business reply ngay.

Không suy ra `void` là asynchronous, không bao giờ throw hoặc luôn durable. Nếu `orders.commands` là `DirectChannel` với handler đồng bộ, caller có thể chờ handler chạy xong và vẫn nhận exception nếu dispatch/handler lỗi.

### 2.2. Request–reply Gateway yêu cầu một đối tượng kết quả

~~~java
@MessagingGateway
interface OrderStatusGateway {
    @Gateway(
        requestChannel = "orders.status.request",
        replyTimeout = "500")
    OrderStatusReply lookup(OrderStatusQuery query);
}
~~~

Ở đây method có kiểu trả về `OrderStatusReply`, nên Gateway cần nhận một **reply message có payload phù hợp** để trả đối tượng. Nếu flow không phát reply và timeout/điều kiện chờ theo cấu hình cho phép hoàn tất không có kết quả, một method trả kiểu tham chiếu **có thể nhận `null`**.

Con số `500` trong ví dụ chỉ là **timeout minh họa** theo đơn vị milliseconds của cấu hình Gateway liên quan. Không coi nó là mặc định của mọi phiên bản Spring Integration. Ở production, chọn timeout theo latency budget, deadlines và hành vi adapter thực tế; không mặc định để chờ vô hạn.

### 2.3. Handler trả `null` không phải “reply payload là null”

~~~java
// Terminal handler: không phát reply.
handle(query, headers) {
    audit(query);
    return null;
}
~~~

Spring Messaging yêu cầu một `Message<?>` có **payload khác null**. Trong nhiều endpoint trả reply kiểu Service Activator, giá trị handler `null` với `requiresReply=false` biểu thị **không có message reply được sinh**, không phải gửi một `Message<null>` hợp lệ.

Nếu handler trả `new OrderStatusReply(... )`, framework có thể xây reply message. Nếu handler trả `null` nhưng Gateway đang chờ, có thể dẫn tới timeout và return null ở phía Java, tùy pipeline/configuration.

**Chú ý:** Không phải mọi Transformer/Handler chấp nhận `null` giống nhau. Một Transformer có thể yêu cầu non-null output hoặc được cấu hình `requiresReply=true`; null khi đó có thể gây exception thay vì im lặng kết thúc.

### 2.4. Bảng đối chiếu kết quả

| Trường hợp | API Java | Điều xảy ra | Kết quả phía caller |
|---|---|---|---|
| Gateway một chiều | `void send(Command)` | Không yêu cầu reply. | Không có return value; vẫn có thể throw. |
| Gateway request–reply thành công | `Reply find(Query)` | Reply hợp lệ đến trong deadline. | Trả `Reply`. |
| Gateway request–reply không nhận reply | `Reply find(Query)` | Downstream không phát reply. | Có thể trả `null` sau timeout theo config. |
| Handler được cấu hình bắt buộc reply | `Reply find(Query)` | Handler không sinh reply nhưng requiresReply=true. | Có thể ném reply-required exception. |
| Downstream exception đồng bộ | `Reply find(Query)` | Service Activator throw qua DirectChannel. | Exception có thể propagate hoặc được bọc. |
| Async worker throw sau khi caller chờ | `Reply find(Query)` | Không có reply, error handling chạy riêng. | Null/timeout/exception tùy error flow; không mặc định một kết quả. |
| Reply business NOT_FOUND | `Reply find(Query)` | Handler gửi một reply message chứa status NOT_FOUND. | Nhận đối tượng reply, **không phải null**. |

## 3. Vòng đời request–reply và reply channel

### 3.1. Gateway tạo kênh nhận reply tạm

Khi một gateway có return type cần kết quả, Spring Integration có thể sử dụng **temporary reply channel** để nhận message phản hồi cho invocation hiện tại. Request thường mang metadata reply destination như `replyChannel` để downstream biết trả về đâu.

~~~text
Caller
   |
   v
Gateway proxy
   |
   +-- request payload: OrderStatusQuery
   +-- reply address: temporary reply channel
   |
   v
orders.status.request
   |
   v
Service Activator
   |
   +-- returns reply object
   |
   v
Temporary reply channel
   |
   v
Gateway unwraps payload -> OrderStatusReply to caller
~~~

Điều quan trọng là **reply phải được gửi đúng nơi mà Gateway đang đợi**. Nếu một handler chuyển sang external broker mà bỏ mất reply destination/correlation, hoặc trả output trên một unrelated channel, Gateway có thể không nhận được.

### 3.2. Request accepted khác reply available

Một `MessageChannel.send(...)` thành công theo channel semantics có thể chỉ xác nhận **request được nhận/dispatch**. Nó không bảo đảm downstream tạo reply, reply hợp lệ đến đúng channel, hoặc caller nhận được trong hạn.

Một luồng có thể hoàn toàn đúng ở bước đầu:

~~~text
gateway.lookup -> requestChannel accepted -> Filter discards
                                         -> no reply sent
                                         -> Gateway waits
                                         -> null / timeout handling
~~~

### 3.3. Các mốc cần phân biệt

| Mốc | Ý nghĩa | Chưa chứng minh |
|---|---|---|
| Invocation started | Caller gọi Gateway. | Request đã dispatch. |
| Request sent | Channel nhận/dispatch theo contract. | Handler đã sinh reply. |
| Handler invoked | Có subscriber thực thi. | Reply đã gửi đúng replyChannel. |
| Handler completed | Handler kết thúc. | Có non-null reply payload. |
| Reply sent | Một endpoint gửi reply message. | Gateway đã nhận trước deadline. |
| Reply received | Gateway có reply phù hợp. | Tất cả business side effects chắc chắn bền nếu không có receipt. |
| Gateway returned null | Invocation không có value tại thời điểm kết thúc. | Business chắc chắn NOT_FOUND hoặc không xử lý. |

### 3.4. `replyChannel` không giống business correlation ID

`replyChannel` cho biết **reply phải được gửi tới đâu trong messaging runtime**. `correlationId` giúp liên kết các logical messages hoặc workflow. Hai thứ không tự thay thế nhau:

~~~text
replyChannel = temporary JVM channel for call #71
correlationId = CHECKOUT-88
requestId = REQ-901
businessOperationId = RESERVE-ORD-901
~~~

Nếu Gateway gửi qua Kafka/HTTP/JMS, không nên serialize một `MessageChannel` JVM object rồi cho remote consumer dùng. Khi qua transport boundary, cần reply destination, request ID và correlation mapping **wire-portable**, nếu muốn request–reply xuyên dịch vụ.

### 3.5. Không mặc định có reply chỉ vì một handler trả về object

Nếu một handler đặt trong **nhánh khác**, có output channel sai, hoặc bị một Filter loại sau khi tạo object, reply có thể không trở lại Gateway. Vì vậy kiểm thử cần đi **toàn flow từ Gateway đến return value**, không dừng ở unit test method `handler.handle(...)`.

## 4. Timeout: vì sao Gateway có thể trả null?

### 4.1. Reply timeout giới hạn thời gian chờ

Một cấu hình:

~~~java
@Gateway(
    requestChannel = "orders.status.request",
    replyTimeout = "500")
OrderStatusReply lookup(OrderStatusQuery query);
~~~

thể hiện **hạn chờ reply của Gateway**. Nếu không có reply phù hợp trong khoảng chờ theo semantics của framework/version, một phương thức trả reference type có thể hoàn tất với `null`.

**Không nên đoán giá trị default reply timeout**. Hãy cấu hình rõ theo use case và kiểm thử trên dependency version thật. Một timeout chờ reply không tự hủy downstream work và không chứng minh request chưa được xử lý.

### 4.2. Request timeout khác reply timeout

| Khái niệm | Áp dụng | Rủi ro nếu nhầm |
|---|---|---|
| Request/send timeout | Thời gian chờ send/handoff vào request channel tùy channel. | Hiểu nhầm channel chưa nhận thành không có business reply. |
| Reply timeout | Thời gian Gateway chờ reply về. | Kết luận null là NOT_FOUND dù worker còn chạy. |
| Worker execution timeout | Deadline của downstream computation. | Tưởng Gateway timeout tự cancel worker. |
| Broker reply TTL | Retention/hạn lưu reply ở broker. | Reply đến muộn hoặc mất. |
| API request deadline | Deadline client HTTP/gRPC bên ngoài. | Client đã timeout nhưng internal process vẫn tiếp tục. |
| Business operation SLA | Thời hạn hoàn tất một command. | Báo processing thành công chỉ từ Gateway return. |

### 4.3. Return null không tương đương “đã xử lý và không có dữ liệu”

Giả sử:

~~~text
T0: Gateway lookup(ORD-901).
T1: Worker nhận request, bắt đầu xử lý.
T2: Gateway không có reply trước deadline.
T3: Gateway return null.
T4: Worker trả kết quả OrderStatusReply(FOUND).
~~~

Ở T3, `null` chỉ là **không có reply tại thời điểm Gateway kết thúc chờ**. Nó không cho biết order không tồn tại; T4 cho thấy kết quả nghiệp vụ có thể xuất hiện sau đó.

Nếu caller làm:

~~~java
if (gateway.lookup(query) == null) {
    return OrderStatus.NOT_FOUND;
}
~~~

thì đó là **bug về semantic** trừ khi contract đã chứng minh `null` chỉ có nghĩa NOT_FOUND (điều thường khó chứng minh với messaging timeout).

### 4.4. Reply đến muộn không tự được giao lại cho caller

Temporary reply channel gắn với invocation có thể không còn active sau timeout. Một late reply có thể bị từ chối, bỏ qua, xuất hiện warning hoặc được error-handled theo cấu hình — **không giả định nó sẽ đến được biến return của lời gọi đã kết thúc**.

Nếu kết quả muộn là quan trọng, thiết kế **durable status store, completion event, callback hoặc một reply queue với correlation/deadline**. Không dựa vào temporary reply channel như một nơi lưu kết quả lâu dài.

### 4.5. Null có thể trở nên nguy hiểm khi caller retry

Nếu request là **query thuần**, retry có giới hạn có thể hợp lý. Nếu request là **command có side effect**, một null do timeout có thể đến sau khi worker đã commit. Retry mù quáng có thể xử lý hai lần.

~~~text
SubmitPayment(requestId=PAY-901) 
    -> Gateway times out / returns null
    -> Remote payment already charged
    -> Caller retries with NEW id
    -> Double charge risk
~~~

Với command, dùng **stable operation ID**, idempotency ở consumer/remote system và reconciliation cho outcome `UNKNOWN`. Null không phải bằng chứng an toàn để phát một command mới.

## 5. Business null, missing reply và error cần mô hình riêng

### 5.1. Một reply type tường minh

Thay vì dùng `null` như một business status, thiết kế:

~~~java
enum LookupStatus {
    FOUND, NOT_FOUND, PENDING, REJECTED
}

record OrderStatusReply(
        String requestId,
        LookupStatus status,
        String orderId,
        String detailCode) {}
~~~

Các status là **business/application outcomes có payload thật**. Ví dụ:

~~~java
new OrderStatusReply(
    "REQ-901",
    LookupStatus.NOT_FOUND,
    "ORD-901",
    "ORDER_NOT_FOUND");
~~~

Nó khác `null`, vì Gateway đã nhận được một reply message chứa **bằng chứng cụ thể** về business outcome.

### 5.2. Một operation không hoàn tất trước deadline

Nếu hệ thống không thể trả status trước deadline, caller nên phân biệt:

~~~text
FOUND       = Có reply và order được tìm thấy.
NOT_FOUND   = Có reply và hệ thống có thẩm quyền xác nhận không có order.
PENDING     = Có reply xác nhận chưa hoàn tất, có operation/reference.
REJECTED    = Có reply/contract error xác nhận request không hợp lệ.
NO_REPLY    = Không có reply trong thời gian đợi; outcome chưa biết.
ERROR       = Technical failure / conversion / routing exception.
~~~

Không viết `reply == null ? NOT_FOUND : FOUND`. Nếu API cần luôn trả một value tường minh, bọc null tại **application boundary** thành một kết quả như `NO_REPLY` hoặc exception thích hợp, không gán nhãn nghiệp vụ sai.

### 5.3. Null không phải một payload message hợp lệ

Một Spring `Message<T>` không thể chứa payload `null` theo contract thông thường. Nếu domain muốn diễn đạt “không có order”, gửi **một non-null DTO** như `OrderStatusReply(NOT_FOUND)`.

Một Service Activator trả `null` có thể nghĩa là **không sinh reply message**; một Transformer trả `null` có thể gây lỗi theo contract/`requiresReply`. Những khác biệt này cần kiểm thử theo endpoint implementation.

### 5.4. Primitive return type là anti-pattern với no-reply

~~~java
// Nguy hiểm nếu request có thể không có reply:
@Gateway(requestChannel = "orders.count.request", replyTimeout = "500")
int countOrders(CountQuery query);
~~~

Primitive `int` không thể biểu diễn `null`. Nếu Gateway không có reply, việc chuyển đổi/unboxing về primitive có thể gây lỗi thay vì một value dùng được. Dùng **reference/DTO và contract rõ**, hoặc yêu cầu reply bắt buộc có error handling tường minh.

## 6. Java và Spring Integration: mô phỏng request có reply và không có reply

### 6.1. Payload request độc lập với transport

~~~java
record OrderStatusQuery(String requestId, String orderId) {
    OrderStatusQuery {
        if (requestId == null || requestId.isBlank()
                || orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException(
                    "INVALID_ORDER_STATUS_QUERY");
        }
    }
}
~~~

`OrderStatusQuery` là DTO Java thuần; nó không biết Gateway đang dùng DirectChannel, ExecutorChannel, broker hoặc HTTP. `requestId` dùng nối log/reply theo từng lần truy vấn, không nhất thiết là ID của business operation gây side effect.

### 6.2. Một Gateway có hai method để so sánh

~~~java
import org.springframework.integration.annotation.Gateway;
import org.springframework.integration.annotation.MessagingGateway;

@MessagingGateway
interface OrderStatusLookupGateway {

    @Gateway(
            requestChannel = "orders.lookup.reply",
            replyTimeout = "300")
    OrderStatusReply lookup(OrderStatusQuery query);

    @Gateway(
            requestChannel = "orders.lookup.silent",
            replyTimeout = "300")
    OrderStatusReply lookupWithoutReply(OrderStatusQuery query);
}
~~~

Hai method đều **request–reply theo chữ ký Java** vì trả `OrderStatusReply`, nhưng flow đích khác nhau:

- `orders.lookup.reply`: Service Activator gửi một response object.
- `orders.lookup.silent`: terminal handler chỉ ghi nhận request và **không phát reply**.

Giá trị `replyTimeout="300"` là minh họa để test có giới hạn thời gian chờ; production nên chọn theo SLA. Nếu method có type trả về `void`, đó là một API **one-way khác**, không thể lấy nó để chứng minh Gateway kiểu reference trả `null`.

### 6.3. Probe cho terminal handler không trả reply

~~~java
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

final class LookupProbe {
    private final List<OrderStatusQuery> seen =
            new CopyOnWriteArrayList<>();

    void record(OrderStatusQuery query) {
        seen.add(query);
    }

    List<OrderStatusQuery> snapshot() {
        return List.copyOf(seen);
    }
}
~~~

`LookupProbe` chỉ dùng trong bài học/integration test. Nó không có transaction, idempotency, durability hoặc access control. Một probe nhận request chứng minh **handler đã được gọi**, không chứng minh có reply.

### 6.4. Hai IntegrationFlows: một có reply, một không

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
@IntegrationComponentScan
class GatewayNullReplyConfiguration {

    @Bean(name = "orders.lookup.reply")
    MessageChannel replyInput() {
        return new DirectChannel();
    }

    @Bean(name = "orders.lookup.silent")
    MessageChannel silentInput() {
        return new DirectChannel();
    }

    @Bean
    LookupProbe lookupProbe() {
        return new LookupProbe();
    }

    @Bean
    IntegrationFlow lookupWithReplyFlow() {
        return IntegrationFlow.from("orders.lookup.reply")
                .handle(OrderStatusQuery.class, (query, headers) ->
                        new OrderStatusReply(
                                query.requestId(),
                                LookupStatus.FOUND,
                                query.orderId(),
                                "READ_OK"))
                .get();
    }

    @Bean
    IntegrationFlow lookupWithoutReplyFlow(LookupProbe probe) {
        return IntegrationFlow.from("orders.lookup.silent")
                .handle(OrderStatusQuery.class, (query, headers) -> {
                    probe.record(query);
                    return null; // No reply message emitted.
                })
                .get();
    }
}
~~~

Để chạy ví dụ, đặt `OrderStatusLookupGateway` và configuration trong cùng package được `@IntegrationComponentScan` quét, hoặc đăng ký gateway interface một cách tường minh. Các ví dụ trong bài dùng Spring Integration 6.x ở mức minh họa; phải kiểm tra các overload/semantics với dependency cụ thể ở vòng Content QA riêng, không suy luận mọi version mặc định giống nhau.

### 6.5. Flow có reply

~~~mermaid
sequenceDiagram
    participant A as Caller
    participant G as Gateway
    participant C as DirectChannel
    participant H as Lookup Service Activator
    A->>G: lookup(REQ-901, ORD-901)
    G->>C: Request + temporary replyChannel
    C->>H: Lookup request
    H-->>G: OrderStatusReply(FOUND)
    G-->>A: Non-null OrderStatusReply
~~~

Khi handler trả một `OrderStatusReply` khác null, Spring Integration gửi reply theo reply routing của Gateway nếu flow/headers được giữ đúng. Tại application layer, caller có thể đọc `reply.status()==FOUND`.

### 6.6. Flow không phát reply

~~~mermaid
sequenceDiagram
    participant A as Caller
    participant G as Gateway
    participant C as DirectChannel
    participant H as Terminal Handler
    A->>G: lookupWithoutReply(REQ-902)
    G->>C: Request + replyChannel
    C->>H: Deliver request
    H->>H: record query
    H-->>C: return null / no reply
    Note over G,C: No reply arrives before configured deadline
    G-->>A: null (no reply result)
~~~

Ở đây có thể xảy ra **handler thực sự đã nhận message nhưng Gateway vẫn trả null**. Điều đó rất khác “không có subscriber” hoặc “request chưa dispatch”; hai trường hợp sau có thể ném lỗi tại channel thay vì chờ reply.

### 6.7. Không ghép tất cả logic vào chính Gateway

Gateway nên chịu trách nhiệm API/entrypoint, còn downstream nên có nhiệm vụ rõ:

~~~text
Gateway -> Channel -> Validate -> Service Activator -> Reply
                     |
                     +-> Error / rejection outcome
~~~

Nếu handler chỉ ghi audit mà không sinh reply, nên cân nhắc **đổi Gateway API thành one-way `void`** khi business thật sự không cần kết quả. Không nên để caller tưởng đang thực hiện query trả kết quả nhưng thực chất đang gọi một consumer không có reply.

## 7. JUnit 5: chứng minh Gateway nhận reply và trả null

### 7.1. Test reply bình thường

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringJUnitConfig(GatewayNullReplyConfiguration.class)
@DirtiesContext(classMode =
        DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class GatewayReplyPresentIntegrationTest {

    @Autowired
    OrderStatusLookupGateway gateway;

    @Test
    void lookupReturnsRealReplyPayload() {
        OrderStatusReply reply = gateway.lookup(
                new OrderStatusQuery("REQ-901", "ORD-901"));

        assertNotNull(reply);
        assertEquals("REQ-901", reply.requestId());
        assertEquals(LookupStatus.FOUND, reply.status());
        assertEquals("ORD-901", reply.orderId());
    }
}
~~~

Test này có ý nghĩa vì thực sự đi qua **Gateway proxy → request channel → Service Activator → reply channel → Java return**. Một unit test gọi method handler thuần không đủ chứng minh reply wiring đúng.

### 7.2. Test no-reply: handler chạy nhưng return là null

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

@SpringJUnitConfig(GatewayNullReplyConfiguration.class)
@DirtiesContext(classMode =
        DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class GatewayNoReplyIntegrationTest {

    @Autowired
    OrderStatusLookupGateway gateway;

    @Autowired
    LookupProbe probe;

    @Test
    void returnsNullWhenTerminalHandlerEmitsNoReply() {
        OrderStatusQuery query =
                new OrderStatusQuery("REQ-902", "ORD-902");

        OrderStatusReply reply =
                gateway.lookupWithoutReply(query);

        assertNull(reply);
        assertEquals(1, probe.snapshot().size());
        assertEquals(query, probe.snapshot().get(0));
    }
}
~~~

Đây là **kịch bản chủ đích cho cấu hình no-reply và bounded timeout**. Nếu project bật `requiresReply=true` ở handler hoặc cấu hình error handling khác, kỳ vọng phải đổi sang exception test, không ép mọi đường lỗi trả null.

### 7.3. Không đo timeout bằng `Thread.sleep(...)` thiếu kiểm soát

Một test mong chờ timeout nên chọn timeout nhỏ nhưng có khoảng sai lệch hợp lý cho CI; không assert “đúng 300 ms tuyệt đối”. JVM scheduling, GC, executor và môi trường build có thể ảnh hưởng thời gian.

Nếu muốn đo:

~~~java
import java.time.Duration;
import java.time.Instant;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class BoundedNoReplyPatternTest {
    private final OrderStatusLookupGateway gateway;

    BoundedNoReplyPatternTest(OrderStatusLookupGateway gateway) {
        this.gateway = gateway;
    }

    @Test
    void noReplyFinishesWithinReasonableUpperBound() {
        Instant start = Instant.now();
        OrderStatusReply reply =
                gateway.lookupWithoutReply(
                        new OrderStatusQuery(
                                "REQ-903", "ORD-903"));

        assertNull(reply);
        assertTrue(Duration.between(start, Instant.now())
                .compareTo(Duration.ofSeconds(5)) < 0);
    }
}
~~~

Đoạn đo thời gian chỉ minh họa assertion có **upper bound** và cần được dùng trong test context có inject gateway bean thích hợp; ví dụ không phải standalone test class sẵn chạy nếu chưa cung cấp Spring Test extension/constructor injection. Trong test thật ở mục 7.2 có thể đưa cùng phép đo vào method được `@SpringJUnitConfig` quản lý.

### 7.4. Vì sao test phải kiểm tra cả probe?

Nếu chỉ `assertNull(reply)`, test có thể pass vì:

- Handler đã chạy nhưng không trả.
- Reply bị Filter drop.
- Handler đang chờ trên executor quá lâu.
- Reply gửi sai channel.
- Một error handler bỏ qua exception.

Kiểm tra `probe.snapshot().size()==1` ít nhất chứng minh terminal handler thực sự nhận request trong **flow đồng bộ demo**. Với async flow, phải dùng latch hoặc persisted trace, không assert synchronously.

## 8. Ba đường lỗi khác với no-reply bình thường

### 8.1. Channel không có subscriber

~~~text
Gateway -> DirectChannel (no subscribers)
~~~

Trong tình huống này, request có thể **không được dispatch**, và Spring Messaging thường có thể báo lỗi kiểu dispatch/delivery thay vì im lặng chờ reply. Không được gộp no subscriber với “handler nhận nhưng không reply”.

### 8.2. Handler throw exception

~~~java
// Ví dụ Service Activator đồng bộ:
(query, headers) -> {
    throw new IllegalStateException(
            "BACKEND_LOOKUP_UNAVAILABLE");
}
~~~

Với DirectChannel, exception có thể propagate qua Gateway, có thể được bọc trong `MessagingException`. Khi có `errorChannel` hoặc advice, đường đi có thể khác. Không viết `assertNull` cho mọi lỗi nếu contract quy định throw.

### 8.3. Handler bắt lỗi rồi return null

~~~java
try {
    return repository.findStatus(query);
} catch (Exception ignored) {
    return null;
}
~~~

Đây là anti-pattern rất nguy hiểm: caller không phân biệt **NOT_FOUND**, database timeout, authorization denied hay bug. Thay bằng typed outcome và xử lý technical error rõ; không nuốt exception rồi dùng null như một “giá trị an toàn”.

### 8.4. Bảng chẩn đoán

| Triệu chứng | Đường khả nghi | Cần xem |
|---|---|---|
| Không có handler invocation | Channel routing/subscriber. | Bean registration, channel name, dispatch error. |
| Handler chạy và trả null | Terminal no-reply handler. | Handler contract, `requiresReply`. |
| Handler trả object nhưng caller null | Reply routing/timeout. | `replyChannel`, output channel, Filter phía sau. |
| Caller nhận exception | Synchronous failure hoặc requiresReply. | Cause chain, endpoint/error config. |
| Caller null, sau đó worker hoàn tất | Async reply quá hạn. | Reply deadline, late reply/error path. |
| Caller null với query không tồn tại | Không được suy là NOT_FOUND. | Backend có tạo typed NOT_FOUND reply không? |
| Lỗi parse raw JSON trước handler | Inbound adapter/deserializer. | Adapter error handler, raw DLQ. |

## 9. `requiresReply` và null return: một ranh giới dễ bỏ sót

### 9.1. Null được phép ở một handler không bắt buộc reply

Trong một Service Activator kiểu request–reply nhưng `requiresReply=false`, việc return `null` có thể được hiểu là **không sản sinh reply message**. Gateway chờ reply và có thể return `null` khi hết thời gian chờ.

### 9.2. Reply bắt buộc làm thay đổi failure mode

Khi endpoint yêu cầu reply (ví dụ `requiresReply=true` ở một reply-producing handler), null return có thể dẫn tới **reply-required exception** thay vì chỉ im lặng. Đây thường là lựa chọn hợp lý cho một operation mà hợp đồng không cho phép thiếu reply.

Ví dụ ý tưởng cấu hình:

~~~text
Service Activator endpoint:
  inputChannel = orders.lookup.replyRequired
  requiresReply = true

Handler returns null
  -> reply-required failure
  -> error handling / synchronous exception
~~~

Đó là **semantics endpoint**, khác với phương thức Gateway `void`. Không bật `requiresReply` một cách mù quáng trên những handler được thiết kế one-way, vì sẽ biến một hành vi hợp lệ thành exception.

### 9.3. Transformer trả null có thể là lỗi khác

Một Transformer thường được dùng để chuyển message sang dạng mới. Nếu logic transform không thể tạo payload, có thể cần throw một validation/mapping exception hoặc trả một outcome object, thay vì return `null` rồi để downstream mất message. Các endpoint có thể khác default `requiresReply`; hãy test theo đúng handler implementation và Spring Integration version.

### 9.4. Vì sao default behavior không đủ làm hợp đồng?

Hợp đồng học thuật/production phải nói rõ:

- Reply **bắt buộc hay tùy chọn**?
- `null` nếu thiếu reply là **accepted API behavior** hay failure?
- Có deadline **bao lâu** cho toàn request?
- Nếu thiếu reply, caller **retry, fallback, status query hay alert**?
- Nếu downstream có side effect, **operationId** và idempotency nằm ở đâu?
- Error channel có được phép biến exception thành một typed reply hay không?

Không dựa trên giả định rằng mọi cấu hình Spring Integration và mọi phương thức Gateway đều có cùng default timeout/exception semantics.

## 10. Filter và Router làm Gateway không nhận reply

### 10.1. Filter loại message trên đường request

Một request có thể tới Filter trước Service Activator:

~~~mermaid
flowchart TD
    G["Order Status Gateway"] --> F{"Filter: orderId accepted?"}
    F -->|Yes| H["Status Handler"]
    H --> REP["OrderStatusReply"]
    F -->|No| D["Discard / no reply"]
    D -.-> GW["Gateway waits then no-reply outcome"]
~~~

Nếu Filter chỉ loại request và không tạo reply/exception theo contract, Gateway có thể không nhận phản hồi. Việc **Filter false** là một quyết định routing, **không phải tự động một Java `OrderStatusReply(REJECTED)`**.

Trong một API query đồng bộ, thường nên trả một **typed rejection** thay vì im lặng:

~~~java
new OrderStatusReply(
        query.requestId(),
        LookupStatus.REJECTED,
        query.orderId(),
        "ORDER_ID_NOT_ALLOWED");
~~~

Nếu cần lưu message sai để điều tra, dùng discard flow/quarantine phù hợp, nhưng phải quyết định **reply path** riêng nếu caller vẫn chờ synchronous result.

### 10.2. `discardChannel` không tự trả reply về Gateway

Ví dụ:

~~~text
Gateway -> Filter
             |
             +-- accepted -> Service Activator -> Reply
             |
             +-- rejected -> discardChannel -> Audit Writer
~~~

Trong nhánh rejected, Audit Writer có thể hoàn thành ghi log nhưng **không sinh business reply**. Gateway vẫn có thể timeout/trả null. Nếu API yêu cầu kết quả, hãy tổ chức nhánh rejected gửi một DTO `REJECTED` đến đúng reply destination hoặc chuyển lỗi có kiểm soát. Đừng giả định gửi sang discardChannel là đã đáp ứng request–reply contract.

### 10.3. `throwExceptionOnRejection` làm semantics thay đổi

Một Filter có thể được cấu hình ném exception khi từ chối. Khi đó Gateway có thể nhận exception theo synchronous error path thay vì chờ đến timeout và trả null. Chọn cách nào dựa trên contract:

| Policy | Phía Gateway/caller | Khi phù hợp |
|---|---|---|
| Discard im lặng | Có nguy cơ no-reply/null. | One-way event, caller không cần reply và đã có audit. |
| Discard có reply | Có thể nhận typed `REJECTED` nếu reply flow được thiết kế đúng. | Request–reply API cần lý do từ chối. |
| Throw on rejection | Exception/error handling. | Validation lỗi cần fail fast. |
| Quarantine + async completion | Không trả ngay business outcome; theo dõi operation status. | Request dài, contract asynchronous. |

### 10.4. Router không tìm được đích

Content-Based Router hoặc Header-Based Router có thể không tìm được channel cho input. Tùy `defaultOutputChannel`, `resolutionRequired` và cấu hình, nó có thể ném error hoặc đưa tới default/discard route.

~~~text
orderType = UNKNOWN
    |
    v
Router
    +-- known -> handler -> reply
    +-- unknown -> default/drop/error
~~~

Không nên thiết kế một default route khiến message **được nhận nhưng không có reply** mà không đo lường. Với request–reply, route chưa xác định thường cần một explicit `UNSUPPORTED_REQUEST_TYPE` outcome hoặc exception có quản lý.

### 10.5. Transformer/Enricher làm mất reply metadata

Một `Message<?>` trong Spring có thể mang `replyChannel` header. Nếu một custom Transformer xây message mới và **không giữ selected headers** hoặc thay đổi reply destination, downstream dù trả object đúng vẫn có thể gửi reply sai nơi.

~~~text
Gateway request (replyChannel=temp#1)
  -> Custom Transformer builds fresh message without replyChannel
  -> Service Activator returns Reply
  -> No valid reply destination for temp#1
  -> Gateway receives nothing
~~~

Không nên tin “handler trả object là Gateway chắc chắn nhận”. Test phải đi qua **toàn route**, kiểm tra correlation/reply destination ở endpoint cuối cùng. Nhưng cũng không copy tùy tiện mọi headers từ nguồn ngoài, vì có privileged/internal headers và security concerns.

## 11. DirectChannel, ExecutorChannel và QueueChannel

### 11.1. DirectChannel: xử lý có thể đồng bộ nhưng thiếu reply

~~~text
Gateway -> DirectChannel -> Service Activator (return null)
    |                                |
    +------ no reply observed --------+
~~~

Nếu handler return null bình thường và không phát reply, Gateway vẫn cần xử lý absence. Một handler đồng bộ cũng có thể **block lâu** trước khi return, khiến caller chờ theo thời gian thực thi handler, không chỉ “reply timeout”.

**Bẫy:** cấu hình `replyTimeout=300ms` không có nghĩa mọi synchronous downstream operation bị cắt ở 300 ms. Timeout của receive reply không phải cơ chế kill/hủy handler đang thực thi cùng thread.

### 11.2. ExecutorChannel: worker có thể xong sau deadline

~~~mermaid
sequenceDiagram
    participant A as Caller
    participant G as Gateway
    participant E as ExecutorChannel
    participant W as Worker
    A->>G: lookup(query)
    G->>E: schedule request
    E->>W: handle request later
    Note over G,W: Gateway is waiting for reply
    G-->>A: null after timeout
    W->>W: finishes processing
    W--xG: Late reply cannot satisfy finished invocation
~~~

`ExecutorChannel` tạo ranh giới thread, nhưng không tự lưu reply vào durable store. Nếu worker chậm, bị overload hoặc ném exception, Gateway có thể không nhận reply. Cần bounded executor, monitoring queue depth, error handling và deadline phù hợp.

### 11.3. QueueChannel: có message, không có consumer

`QueueChannel` có thể giữ request để poller lấy sau. Nếu:

- Không cấu hình poller.
- Poller bị stop.
- Consumer quá tải.
- Queue full hoặc có lỗi trong lúc receive.

thì Gateway có thể không nhận reply trong deadline hoặc có thể gặp lỗi send/handoff riêng. Phải phân biệt **request đang pending** với **request mất**.

### 11.4. Bảng so sánh

| Channel/flow | Khi Gateway có thể return null? | Lỗi cần quan sát | Durability |
|---|---|---|---|
| `DirectChannel` + terminal handler null | Không có reply được tạo. | Reply-required, sync exception, misrouting. | Không là storage. |
| `ExecutorChannel` + delayed worker | Reply không đến trước deadline. | Task rejection, async exception, late reply. | Không mặc định. |
| `QueueChannel` + poller | Request tồn tại nhưng chưa có reply trước deadline. | Queue depth, poller state, send timeout. | Memory queue không durable mặc định. |
| Persistent message channel/store | Pending reply quá deadline. | Transaction, retry, correlation, retention. | Theo store/config. |
| External broker request–reply | Reply không đến đúng reply destination trước timeout. | Network, codec, reply topic/queue, consumer group. | Theo broker/adapter. |

Không có channel type nào tự đảm bảo mọi business request có reply đúng hạn chỉ vì Gateway method khai báo return type.

### 11.5. Async tests phải chờ tín hiệu rõ

Một integration test cho ExecutorChannel nên dùng `CountDownLatch`/`BlockingQueue.poll(timeout)` hoặc một test message store; tránh:

~~~java
gateway.lookup(query);
Thread.sleep(100);
assertThat(worker).hasCompleted();
~~~

Mọi test có latch phải giải phóng trong `finally` và shutdown executor để CI không treo. Nếu muốn kiểm tra **late reply**, cần điều khiển thời điểm worker phát response bằng latch, không dựa vào scheduling ngẫu nhiên.

## 12. Reply đến muộn và correlation

### 12.1. Vòng đời reply bị trễ

~~~text
Request:
  requestId = REQ-901
  correlationId = CHECKOUT-88
  sentAt = T0
  replyDeadline = T0 + 300 ms

Worker:
  starts at T0 + 150 ms
  completes at T0 + 700 ms

Gateway:
  no reply by deadline -> null/no-reply result
~~~

Reply sinh ra ở 700 ms không nên bị coi là response của một **lời gọi Java khác** chỉ vì hai request cùng `orderId`. Cần request identity và reply matching/correlation chính xác.

### 12.2. Late reply không có nghĩa message bị mất ở business layer

Một consumer có thể đã hoàn tất một query hoặc command sau deadline. Nếu là **query**, caller có thể query lại trạng thái; nếu là **command**, phải kiểm tra operation ledger trước khi retry. Không dùng outcome `NO_REPLY` như một lệnh rollback tự động.

### 12.3. Bảo vệ khỏi reply của request cũ

Giả sử cùng orderId:

~~~text
Request #1: REQ-901 (times out)
Request #2: REQ-902 (new query)
Late reply: REQ-901
~~~

Nếu hệ thống custom reply routing chỉ match theo `orderId`, late reply #1 có thể bị ghép sai vào #2. Dùng request ID riêng, correlation IDs, deadline và reply selector/consumer theo contract. Với broker reply queue chung, cần tracking in-flight request registry và xử lý late replies có audit.

### 12.4. Spring replyChannel không phải durable reply inbox

Temporary reply channel tiện cho Java call đang chờ. Nhưng khi invocation kết thúc, **nó không phải chỗ lưu reply để caller đọc ngày mai**. Nếu deadline có thể rất dài (phút/giờ), nên chuyển sang **asynchronous operation status + completion event**, hoặc một durable request–reply architecture có correlation/dead letter/expiry rõ.

### 12.5. Timeout chọn theo deadline và SLO

Một timeout hợp lý phải dựa trên:

- Expected latency p50/p95/p99 của downstream.
- Tail latency và ảnh hưởng queue backlog.
- Network/broker delivery, serialization overhead.
- Deadline phía HTTP caller.
- Retry budget và tổng thời gian tối đa.
- Consequences khi reply muộn, đặc biệt payment/inventory.

Chọn timeout quá ngắn → nhiều null giả dù backend sắp trả. Quá dài → giữ threads/resources và giảm throughput. Nếu downstream có thể mất nhiều phút, không nên để hàng nghìn Gateway request threads chờ reply một cách vô hạn.

## 13. Error channel và exception khác no-reply

### 13.1. Synchronous exception có thể propagate

Với DirectChannel, downstream throw trong call stack có thể được bọc thành Spring Messaging exception:

~~~text
Gateway.lookup()
  -> DirectChannel
  -> Service Activator throws DatabaseUnavailableException
  -> MessagingException / cause chain
  -> Caller sees exception
~~~

Không nên bắt mọi exception rồi return null, vì sẽ mất dấu **technical failure**.

### 13.2. Asynchronous exception có thể không quay về caller

Với ExecutorChannel hoặc broker adapter:

~~~text
Gateway waiting...
Async worker throws
  -> configured error handling
  -> ErrorMessage / errorChannel or adapter recovery
Gateway may still have no normal reply
~~~

`ErrorMessage` và `errorChannel` phụ thuộc cấu hình. Không thể mặc định mọi deserialization error, broker consumer failure, JVM exception và security denial đều tự tới global `errorChannel`.

### 13.3. Nếu muốn trả error reply, phải thiết kế nó

Một gateway method muốn luôn nhận kết quả có thể dùng typed envelope:

~~~java
enum LookupOutcomeType {
    FOUND, NOT_FOUND, REJECTED, TECHNICAL_ERROR
}

record LookupOutcome(
        String requestId,
        LookupOutcomeType type,
        OrderStatusReply value,
        String errorCode) {}
~~~

Một error-handling flow **có thể** gửi `LookupOutcome(TECHNICAL_ERROR)` qua reply path thích hợp. Nhưng đó là **logic ứng dụng cần cấu hình**, không tự xuất hiện chỉ vì đã bật error channel.

Nếu lỗi xảy ra trước khi message được dispatch hoặc ở adapter không có reply destination, caller có thể nhận exception trực tiếp hoặc timeout. Một reply contract không thay thế việc quan sát mọi failure modes.

### 13.4. No reply là outcome chưa đủ chứng cứ

Với system status:

~~~text
No reply:
  knows: no usable reply before invocation ended
  does not know: processing never started
  does not know: consumer failed
  does not know: business state not found
  does not know: operation not committed
~~~

Nếu ứng dụng cần bảo đảm “NOT_FOUND”, phải có **authoritative lookup reply**, không suy từ vắng mặt.

## 14. Phân biệt null với empty result và NOT_FOUND

### 14.1. Query không tìm thấy dữ liệu

Không tìm thấy đơn hàng có thể là business outcome hợp lệ:

~~~java
return new OrderStatusReply(
        query.requestId(),
        LookupStatus.NOT_FOUND,
        query.orderId(),
        "ORDER_NOT_FOUND");
~~~

Gửi reply DTO này có ưu điểm là:

- Caller phân biệt NOT_FOUND với timeout.
- Logs/metrics có reason code cụ thể.
- Gateway đã thực sự nhận reply.
- Có thể audit backend nào trả kết luận NOT_FOUND.

### 14.2. Danh sách rỗng là một reply hợp lệ

Với query lấy danh sách:

~~~java
record OrderListReply(
        String requestId,
        java.util.List<String> orderIds) {}

// Không có order:
new OrderListReply("REQ-903", java.util.List.of());
~~~

Đó là **một đối tượng non-null chứa collection rỗng**, khác Gateway trả `null` vì không nhận reply.

### 14.3. Optional không phải phép chữa mặc định

`Optional<OrderStatusReply>` có thể diễn tả không có giá trị trong một Java API, nhưng **không tự phân biệt**:

- Backend xác nhận NOT_FOUND.
- Timeout không nhận reply.
- Filter discard.
- System error đã bị nuốt.

Và cách Gateway map no-reply sang `Optional.empty()` phụ thuộc converter/support của framework; không được giả định chỉ thay return type sẽ giải quyết tất cả. Nếu cần phân biệt, hãy dùng typed status/error domain và cấu hình mapping/test cụ thể.

### 14.4. Primitive, boxing và null dereference

~~~java
int count = gateway.countOrders(query);
// Nếu reply vắng mặt, primitive không biểu diễn null.

OrderStatusReply result = gateway.lookup(query);
result.status(); // NPE nếu result == null.
~~~

Caller phải xử lý `null` rõ hoặc chặn no-reply bằng API contract/requiresReply/error mapping. Không dùng primitive cho operation có thể thiếu reply mà chưa có policy lỗi.

### 14.5. Null trong async callback không tự là completion

Nếu bạn xây adapter custom dùng `CompletableFuture` hoặc callback, `complete(null)` có thể có nghĩa khác nhau tùy library. Đừng áp semantics của `CompletableFuture<Reply>` lên `@MessagingGateway` truyền thống nếu chưa kiểm tra type conversion/async gateway contract. Chọn một typed result và test thực tế.

## 15. Application boundary: chuyển no-reply thành kết quả dễ hiểu

### 15.1. Không để `null` lan khắp domain code

Một application service có thể bọc Gateway:

~~~java
enum StatusQueryState {
    REPLIED, NO_REPLY
}

record StatusQueryResult(
        StatusQueryState state,
        OrderStatusReply reply,
        String diagnosticCode) {

    static StatusQueryResult received(OrderStatusReply reply) {
        if (reply == null) {
            throw new IllegalArgumentException(
                    "REPLY_MUST_NOT_BE_NULL");
        }
        return new StatusQueryResult(
                StatusQueryState.REPLIED, reply, null);
    }

    static StatusQueryResult noReply() {
        return new StatusQueryResult(
                StatusQueryState.NO_REPLY,
                null,
                "GATEWAY_NO_REPLY");
    }
}
~~~

`StatusQueryResult` không cho rằng no-reply là NOT_FOUND. Nó chỉ chuyển **một absence kỹ thuật** thành một trạng thái được đặt tên. Với production, có thể thêm deadline, requestId, elapsed time và error class phù hợp.

### 15.2. Wrapper service sử dụng Gateway an toàn

~~~java
final class OrderStatusLookupService {
    private final OrderStatusLookupGateway gateway;

    OrderStatusLookupService(OrderStatusLookupGateway gateway) {
        this.gateway = gateway;
    }

    StatusQueryResult findStatus(String requestId, String orderId) {
        OrderStatusReply reply = gateway.lookup(
                new OrderStatusQuery(requestId, orderId));

        if (reply == null) {
            return StatusQueryResult.noReply();
        }
        return StatusQueryResult.received(reply);
    }
}
~~~

Ở đây logic chỉ xử lý **return null theo Gateway contract**. Một exception như deserialization, dispatch failure hoặc security denial sẽ **tiếp tục propagate** trừ khi có chính sách catch/map cụ thể. Đừng bắt `RuntimeException` rồi trả `NO_REPLY` cho tất cả, vì sẽ che mất lỗi có thể sửa và rủi ro bảo mật.

### 15.3. Test wrapper mà không chạy Spring

~~~java
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

class OrderStatusLookupServiceTest {

    @Test
    void absenceOfReplyIsNotBusinessNotFound() {
        OrderStatusLookupGateway fake =
                new OrderStatusLookupGateway() {
                    @Override
                    public OrderStatusReply lookup(
                            OrderStatusQuery query) {
                        return null;
                    }

                    @Override
                    public OrderStatusReply lookupWithoutReply(
                            OrderStatusQuery query) {
                        return null;
                    }
                };

        StatusQueryResult result =
                new OrderStatusLookupService(fake)
                        .findStatus("REQ-100", "ORD-100");

        assertEquals(StatusQueryState.NO_REPLY, result.state());
        assertEquals("GATEWAY_NO_REPLY", result.diagnosticCode());
        assertNull(result.reply());
    }
}
~~~

Test Java thuần này chứng minh **cách ứng dụng diễn giải `null`**. Nó không chứng minh Gateway proxy thật return null trong một Spring flow; bằng chứng đó là integration test ở mục 7.

### 15.4. Lựa chọn API khi reply bắt buộc

Với một operation có yêu cầu “mọi request phải trả business response”, có thể:

- Đảm bảo handler luôn trả một non-null reply cho các outcome hợp lệ: `FOUND`, `NOT_FOUND`, `REJECTED`, `PENDING`.
- Cấu hình `requiresReply` cho endpoint phù hợp, để null do bug trở thành exception.
- Dùng bounded timeout; nếu hết hạn, chuyển thành `NO_REPLY`/`OUTCOME_UNKNOWN` tại API boundary.
- Có fallback/status query hoặc explicit error policy.
- Kiểm thử misrouting, Filter discard và late reply.

Không phải mọi trường hợp nên bật requiresReply: một one-way command handler hợp lệ có thể chủ ý không tạo reply. Tránh áp cùng policy cho mọi endpoint trong hệ thống.

## 16. Khi query thật sự không có dữ liệu

### 16.1. NOT_FOUND chỉ được tạo từ nguồn có thẩm quyền

Một query thực hiện ở DB trả danh sách rỗng/cờ not found. Handler phải **xây response**:

~~~java
OrderStatusReply handleLookup(OrderStatusQuery query) {
    return repository.findById(query.orderId())
            .map(order -> new OrderStatusReply(
                    query.requestId(),
                    LookupStatus.FOUND,
                    order.id(),
                    "ORDER_FOUND"))
            .orElseGet(() -> new OrderStatusReply(
                    query.requestId(),
                    LookupStatus.NOT_FOUND,
                    query.orderId(),
                    "ORDER_NOT_FOUND"));
}
~~~

Đây là ví dụ domain logic giản lược; `repository` là dependency giả định được inject trong implementation. Có thể dùng mapping tương đương cho một API thực sự cần thể hiện NOT_FOUND, thay vì trả `null` từ repository rồi để Gateway/Service Activator ngầm không gửi reply.

### 16.2. NO_REPLY nên thường là trạng thái không xác định

~~~text
Reply(FOUND)       -> Business knows order exists
Reply(NOT_FOUND)   -> Business knows authoritative source found no order
Reply(PENDING)     -> Business knows processing is pending
null / no reply    -> Caller cannot know final business outcome
Exception         -> Caller knows a technical/dispatch failure was reported
~~~

Nếu tổ chức muốn ánh xạ no-reply thành HTTP 504 Gateway Timeout hoặc một status `UNKNOWN`, phải phân biệt nó với HTTP 404 Not Found. Một downstream lỗi mạng không biến order đang tồn tại thành “không tìm thấy”.

### 16.3. Status có thể thay đổi sau reply

Ngay cả khi nhận `Reply(NOT_FOUND)`, hệ thống phân tán có thể có eventual consistency: order vừa được tạo ở shard khác nhưng projection chưa bắt kịp. Business contract cần nói **mức độ nhất quán** của kết luận NOT_FOUND, không chỉ giải quyết null.

### 16.4. Không dùng null để diễn đạt permission denied

Một API có thể cố tình “không tiết lộ sự tồn tại” của resource trong một số security policies, nhưng việc đó phải được thiết kế ở API boundary với status và audit phù hợp; không để network timeout và authentication failure vô tình dùng chung `null`.

## 17. Retry khi Gateway trả null

### 17.1. Query idempotent có thể thử lại có giới hạn

Với **lookup chỉ đọc**:

~~~text
Attempt 1: lookup(requestId=REQ-1) -> NO_REPLY
Backoff with jitter
Attempt 2: lookup(requestId=REQ-2) -> Reply(FOUND)
~~~

Hai attempts có thể có request IDs riêng để trace, nhưng chúng nhắm đến **cùng business entity**. Retry cần có tổng deadline, không phải mỗi attempt chờ 30 giây rồi lặp vô hạn. Nếu backend quá tải, retry dồn dập có thể làm incident nặng hơn.

### 17.2. Command không được retry mù chỉ vì null

Với `ReserveInventory` hoặc `ChargePayment`:

~~~text
Attempt 1:
  operationId = RESERVE-ORD-901
  Gateway receives no reply
  Remote consumer may have committed

Attempt 2:
  same operationId + same semantic payload
  consumer/remote service checks authoritative ledger
~~~

Không tạo `operationId` mới ở mỗi attempt nếu cùng logical operation. Cần remote idempotency key, inbox/operation ledger và reconciliation cho trạng thái chưa xác định.

### 17.3. Null không phải chứng cứ để rollback

Nếu caller nhận null sau timeout, nó **không tự chứng minh** transaction ở external service chưa commit. Một local rollback chỉ có thể hoàn tác những resource nằm trong transaction scope. Với remote effects cần saga/compensation hoặc reconciled state; không “undo” bằng cách giả định operation chưa diễn ra.

### 17.4. Backoff và retry budget

Một chính sách ví dụ:

~~~text
Total request deadline = 2 seconds
Attempt #1 reply wait = 400 ms
Backoff = 100 ms + jitter
Attempt #2 reply wait = 400 ms
Backoff = 200 ms + jitter
Remaining time used for status lookup or final UNKNOWN
~~~

Các con số chỉ minh họa; không phải best practice mặc định. Deadline phải bao gồm network/queue/handler latency, serialization và thời gian fallback. Không retry khi đã hết tổng deadline.

### 17.5. Khi null là một lỗi cấu hình, retry vô ích

Nếu handler được viết `return null` trong mọi tình huống, hoặc Router cố định đưa sang discard channel, retry 100 lần vẫn không tạo reply. Cần sửa flow contract, không tăng timeout hoặc số lần retry.

## 18. Kiểm thử late reply có điều khiển

### 18.1. Mục tiêu

Cần chứng minh:

1. Gateway thực sự gửi request.
2. Handler **bắt đầu xử lý**.
3. Gateway kết thúc chờ trước khi handler phát reply.
4. Late reply **không được gán** vào lời gọi Java mới/sai correlation.
5. Hệ thống có tracking completion/error phù hợp.

### 18.2. Dùng latch thay vì `Thread.sleep`

Test fixture nguyên tắc:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

final class DelayedReplyProbe {
    final CountDownLatch started = new CountDownLatch(1);
    final CountDownLatch allowReply = new CountDownLatch(1);

    OrderStatusReply handle(OrderStatusQuery query)
            throws InterruptedException {
        started.countDown();
        if (!allowReply.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException("TEST_REPLY_WAIT_EXPIRED");
        }
        return new OrderStatusReply(
                query.requestId(),
                LookupStatus.FOUND,
                query.orderId(),
                "LATE_REPLY");
    }
}
~~~

Đây là fixture minh họa để dùng trong một **ExecutorChannel integration test**, nơi worker chạy ở thread khác. Không dùng fixture này trực tiếp trên DirectChannel cùng thread rồi kỳ vọng Gateway timeout trong khi handler đang block synchronous, vì caller có thể bị giữ ngay tại handler.

### 18.3. Quy trình test

~~~text
T1  Start gateway.lookup(...) on test caller thread.
T2  Worker enters delayed handler -> started latch.
T3  Assert gateway returned no-reply at configured timeout.
T4  Release allowReply latch.
T5  Worker emits late response.
T6  Assert no reply leaked into another request.
T7  Inspect configured error/late-reply handling.
~~~

Nếu test phải dùng threads/executor, dọn chúng trong `finally` và không để latch kẹt khi assertion thất bại. Việc một temporary reply channel xử lý late send ra sao là **framework/configuration-specific**; test phải phản ánh nó thay vì giả định sẽ luôn có một exception hoặc log cố định.

### 18.4. Late reply sau timeout có thể vẫn là dữ liệu quý

Với một tính toán mất nhiều giây, response có thể chứa business result cần lưu cho hệ thống. Hãy thiết kế một **separate durable completion path**, không chỉ gửi vào replyChannel tạm đã hết hạn. Một delayed result có thể được ghi theo requestId/operationId để query lại, sau khi kiểm tra quyền và retention.

## 19. Correlation và reply matching ở hệ thống phân tán

### 19.1. Gateway nội bộ và remote reply không dùng cùng một cơ chế

Với DirectChannel, reply path có thể được giữ bằng Spring message headers nội bộ. Với broker:

~~~text
Requester:
  request queue = orders.lookup.requests
  reply queue = orders.lookup.replies
  requestId = REQ-901
  correlationId = CHECKOUT-88

Responder:
  consumes request
  replies to approved reply queue
  includes requestId/correlation

Requester reply listener:
  matches in-flight request registry
  ignores/archives replies after deadline by policy
~~~

Đây là **application-level request–reply pattern**; không phải cứ gọi một Java Gateway thì Spring tự provision toàn bộ reply topic, temporary reply queue, correlation registry hoặc DLQ của mọi broker.

### 19.2. Không tin reply destination tự khai từ client

Một untrusted request có thể chứa header `replyTo=malicious-endpoint`. Nếu responder gửi toàn bộ dữ liệu order vào địa chỉ tự khai, có nguy cơ **data exfiltration**. Reply destinations cần allowlist/authentication, tenant scope và authorization; không sử dụng arbitrary URL/topic/channel name từ payload.

### 19.3. Correlation khác business operation identity

~~~text
correlationId = CHECKOUT-88
requestId = REQ-901
businessOperationId = RESERVE-ORD-901
traceId = TRACE-...
~~~

Một workflow có nhiều requests; một request có thể retry; và một business operation có thể được xử lý nhiều deliveries. Không dùng `correlationId` duy nhất làm idempotency key cho tất cả nhánh, cũng không dùng `traceId` như token ủy quyền.

### 19.4. Hai requests cùng orderId phải giữ response riêng

~~~text
REQ-901 asks ORD-901 -> no reply
REQ-902 asks ORD-901 -> successful reply
Late reply for REQ-901 arrives
~~~

Nếu match chỉ theo orderId, late reply có thể chiếm reply slot của REQ-902. Dùng requestId mới cho mỗi attempt và tracking per invocation; với commands có side effect, vẫn giữ **business operationId** ổn định qua retry.

### 19.5. Trace context không thay durable audit

Traces có thể bị sampling, timeout hoặc mất do retention. Để điều tra “Gateway trả null” cần logs có requestId, reply timeout, channel/handler outcome, broker coordinates và business receipt nếu có. Không dựa vào một trace span trống để kết luận backend chưa xử lý.

## 20. Liên hệ với các Enterprise Integration Patterns

### 20.1. Messaging Gateway và Service Activator

Gateway là điểm đưa **Java method invocation → Spring message**, trong khi Service Activator nhận message và gọi service/business logic:

~~~text
Java Caller
   -> Messaging Gateway
   -> MessageChannel
   -> Service Activator
   -> [reply object] or [no reply]
~~~

Nếu caller mong chờ `OrderStatusReply`, Service Activator cần có **reply contract rõ**. Một method side-effect chỉ trả `void` bên dưới một Gateway trả object dễ tạo no-reply mismatch. Không mặc định khớp hai API chỉ vì chúng nhận cùng request DTO.

### 20.2. Transformer

Transformer có thể chuyển:

~~~text
OrderStatusQuery
   -> PartnerLookupRequest
   -> External Service
   -> PartnerLookupResponse
   -> OrderStatusReply
~~~

Nếu một bước Transformer return null cho unsupported source schema hoặc lỗi mapping, tùy endpoint semantics nó có thể throw hoặc không phát reply. Để không biến lỗi dữ liệu thành “Gateway không nhận gì”, hãy trả **MappingResult/RejectedResult** hoặc ném exception có reason phù hợp.

### 20.3. Filter

Filter có thể giữ/loại request hoặc reply. Hai tình huống:

~~~text
A. Gateway -> Filter(request) -> no handler -> no reply.

B. Gateway -> Handler -> Filter(reply) -> discard
   -> no reply reaches Gateway.
~~~

Trong B, handler đã tạo reply nhưng Filter phía sau loại nó. Nếu chỉ debug handler, dễ kết luận sai “đã trả về”. Theo dõi đến **reply channel cuối**, đồng thời giữ validation/rejection outcome nếu Filter được dùng để chặn dữ liệu không hợp lệ.

### 20.4. Content-Based Router và default route

~~~mermaid
flowchart TD
    G["Gateway lookup"] --> R{"Router by query type"}
    R -->|Order status| A["Order handler -> reply"]
    R -->|Shipment status| B["Shipping handler -> reply"]
    R -->|Unknown| U["Default discard?"]
    U --> N["No reply / error path"]
~~~

Với Gateway cần reply, default branch không nên vô thức biến unknown request thành null. Một explicit `UNSUPPORTED_REQUEST_TYPE` reply hoặc exception thường dễ kiểm soát hơn.

### 20.5. Recipient List và Publish–Subscribe

Một request gửi đến nhiều recipients có thể nhận **nhiều responses**. Một Gateway method `OrderStatusReply lookup(...)` mặc định biểu diễn **một kết quả**; không tự thiết kế cách chọn reply nào:

~~~text
Gateway request
  -> Recipient A: reply A
  -> Recipient B: reply B
  -> Recipient C: no reply
~~~

Nếu nghiệp vụ cần tất cả replies, dùng Aggregator/Scatter–Gather với correlation và release strategy. Nếu chỉ cần reply đầu tiên, phải định nghĩa **first valid reply**, cancellation/late replies, fault isolation và không bỏ qua nhánh có side effect một cách mù quáng.

### 20.6. Splitter

Một query danh sách 100 orders được Splitter thành 100 child requests. Nếu một child không reply, Aggregator có thể chờ đủ 100 và khiến Gateway return null khi timeout.

~~~text
BatchStatusQuery(B-1)
  -> Splitter:
       ORD-1 -> FOUND reply
       ORD-2 -> FOUND reply
       ORD-3 -> no reply
  -> Aggregator waiting for 3
  -> Gateway receives nothing before deadline
~~~

Ở đây nguyên nhân no-reply nằm ở **group release condition**, không phải Gateway gửi sai request. Cần per-child status, timeout, partial result policy, stable child ID và duplicate handling.

### 20.7. Aggregator

Aggregator có release strategy và group timeout. Nếu một group **không release**, reply tổng hợp không được tạo. Gateway có thể return null ngay cả khi từng branch đã làm việc.

Các lựa chọn:

- **All required:** trả result khi đủ mọi child; timeout chuyển thành typed failure/partial outcome.
- **Quorum:** chấp nhận tập đủ điều kiện; có chính sách missing branches.
- **Partial result:** trả `BatchStatusReply(PARTIAL)` kèm missing IDs.
- **No partial allowed:** phát explicit error, không biến mất im lặng.

Đừng mặc định Aggregator sẽ tạo reply ở timeout; release/expire/partial semantics phụ thuộc cấu hình và business contract.

### 20.8. Scatter–Gather

~~~mermaid
flowchart LR
    G["Lookup Gateway"] --> S["Scatter: Inventory, Pricing, Fraud"]
    S --> I["Inventory reply"]
    S --> P["Pricing reply"]
    S --> F["Fraud timeout"]
    I --> A["Gatherer"]
    P --> A
    F -.-> A
    A --> R["Release / timeout strategy"]
    R --> G
~~~

Nếu Fraud là bắt buộc, hai replies không đủ để coi giao dịch là APPROVED. Gateway `null` có thể do Gatherer chờ nhánh Fraud. Cần trạng thái **missing/timeout/invalid**, không ép fallback success.

### 20.9. Resequencer

Nếu reply đi qua Resequencer và thiếu message có `sequenceNumber=2`, nó có thể giữ các replies sau để chờ thứ tự:

~~~text
reply seq=1 -> released
reply seq=3 -> buffered
reply seq=2 -> missing
Gateway deadline -> no usable final reply
~~~

Đừng tăng số thứ tự `seq=3` thành 2 để “lấp lỗ”. Xác định gap policy, timeout, correlation và business ordering semantics. `schemaVersion` không phải business sequence number.

### 20.10. Envelope Wrapper

Khi qua transport:

~~~text
Request Envelope:
  messageId, requestId, correlationId, reply destination
  payload = OrderStatusQuery

Reply Envelope:
  replyMessageId, requestId, correlationId
  payload = OrderStatusReply
~~~

Không nhầm `MessageHeaders.ID` với requestId, cũng không cho untrusted header tự chọn privileged reply destination. Một Transformer làm mất envelope metadata có thể khiến reply đi sai đường dù business handler trả đúng DTO.

### 20.11. Claim Check

Một request có thể chỉ chứa claim token tới payload. Nếu token hết hạn hoặc Claim Store không đọc được, handler có thể không thể trả reply:

~~~text
Gateway -> Claim token -> Claim Restore fails
       -> technical error / expired claim outcome
       -> not business NOT_FOUND
~~~

Phải phân loại `CLAIM_EXPIRED`/`CLAIM_NOT_ACCESSIBLE` và đường recovery. Không suy rằng `null` ở Gateway nghĩa business object không tồn tại; đây có thể chỉ là lỗi lấy payload gốc.

### 20.12. Idempotent Receiver

Một request Gateway có side effect mà caller retry sau null có thể tới Idempotent Receiver. Nếu interceptor chỉ đánh dấu message “SEEN” ngay khi bắt đầu rồi handler crash, retry có thể bị chặn dù operation chưa completed.

Với operation quan trọng cần durable state:

~~~text
operationId -> NEW
            -> IN_PROGRESS
            -> COMPLETED(receipt)
            -> FAILED_RETRYABLE / OUTCOME_UNKNOWN
~~~

Khi receive duplicate, kiểm tra **business receipt/state** chứ không chỉ `SEEN`. Một null từ Gateway không thay thế bài toán idempotency này.

### 20.13. Retry và Error Channel

Retry advice có thể giúp khi lỗi tạm thời; error channel lưu/định tuyến technical errors. Nhưng **không có reply** có thể là kết quả **không ném exception**, nên retry/error advice chỉ bắt exception có thể không thấy nó.

Muốn quan sát no-reply phải đo **Gateway return, timeout, late reply và operation status**, không chỉ exception count.

## 21. Vì sao Gateway không nên trả null cho command quan trọng?

### 21.1. Command có side effect không giống query

~~~text
Query:
  "Đơn ORD-901 có trạng thái gì?"
  Retry có thể an toàn hơn nếu là read-only.

Command:
  "Hãy charge 850000 VND cho PAY-901."
  Retry có thể charge lại nếu remote outcome đã commit.
~~~

Một Gateway method `PaymentReceipt charge(...)` return null khiến caller **không biết** thanh toán đã hoàn tất hay chưa. Xử lý đúng thường là trả `OUTCOME_UNKNOWN` và dùng durable operation ID để reconcile.

### 21.2. Một timeline điển hình

~~~mermaid
sequenceDiagram
    participant A as Checkout Caller
    participant G as Gateway
    participant B as Broker
    participant P as Payment Service
    A->>G: charge(PAY-901)
    G->>B: command(PAY-901)
    B->>P: deliver command
    P->>P: commit payment
    Note over G,P: reply lost or delayed
    G-->>A: null at deadline
    Note over A,P: Payment may already be completed
~~~

Nếu caller lập tức phát `PAY-902` vì `PAY-901` “không có reply”, có nguy cơ double charge. Giữ cùng stable `paymentOperationId` khi retry cùng business intent và sử dụng remote idempotency/ledger; nếu cần sửa giá trị, dùng correction operation được phê duyệt thay vì thay payload dưới cùng key.

### 21.3. Durable receipt thay vì chỉ temporary reply

Một thiết kế:

~~~text
POST payment command (operationId=PAY-901)
  -> authenticated validation
  -> durable outbox/broker
  -> payment consumer
  -> durable receipt store (PAY-901, COMPLETED/FAILED/UNKNOWN)
  -> completion event or query API
~~~

Synchronous Gateway vẫn có thể được dùng cho các đoạn nhanh; nhưng nếu kết quả bên ngoài không chắc hoàn tất trong deadline, nên cân nhắc một **asynchronous command contract** với operation status.

### 21.4. Outbox không tự làm reply xuất hiện

Transactional outbox giải quyết **intent publish** cùng DB transaction. Nó có thể giúp không mất command nhưng không bắt buộc downstream trả reply. Nếu mục tiêu là business receipt, phải thêm **inbox/ledger, completion event/status projection hoặc request–reply over broker**.

### 21.5. Trả `PENDING` phải có cơ sở

Một typed `PENDING` reply nên dựa trên **bằng chứng đã nhận command/durable enqueue** theo contract, không phải chỉ “Gateway chưa nhận reply”. Nếu request bị mất trước broker, trả PENDING có thể đánh lừa client.

## 22. Bảo mật, dữ liệu nhạy cảm và reply

### 22.1. Không dùng null như cơ chế che lỗi security

Nếu caller không có quyền tra cứu order, có thể có chủ đích che sự tồn tại của resource, nhưng vẫn cần **API security contract + audit**. Để security exception bị nuốt rồi trả `null` như một timeout bình thường sẽ làm khó phân biệt tấn công với hạ tầng lỗi.

### 22.2. Reply destination phải được bảo vệ

Với external request–reply, nếu reply destination lấy từ request headers tự khai mà không kiểm tra, attacker có thể hướng order details tới một queue/topic/URL họ kiểm soát.

Thiết kế:

- Authenticated caller/producer identity.
- Reply queue/topic allowlist hoặc server-assigned address.
- Tenant isolation và permissions trên cả request/reply transports.
- Correlation ID khó đoán nếu exposure nguy hiểm, nhưng **ID không thay authorization**.
- Data minimization: reply chỉ chứa fields caller được phép đọc.
- TTL/retention phù hợp, tránh để replies nhạy cảm trong DLQ vô hạn.

### 22.3. Không log nguyên request khi debug null

Một log sai:

~~~text
GatewayTimeout request={full order, customerEmail, bearerToken, cardData}
~~~

Đề xuất log:

~~~text
event=GATEWAY_NO_REPLY
  requestRef=REQ-901
  queryType=ORDER_STATUS
  route=orders.status.request
  configuredReplyTimeoutMs=300
  elapsedMs=...
  authenticatedTenantScope=...
~~~

Nếu cần payload gốc cho investigation, dùng protected storage reference với quyền/retention; không nhét raw PII vào errorChannel log hoặc meter labels.

### 22.4. Rate limiting và timeout amplification

Một attacker có thể tạo rất nhiều request chờ đến reply timeout để giữ threads/connection resources. Cần rate limits, bounded queues, per-tenant quotas, bulkheads và proper timeouts. Không để hàng nghìn Gateway requests chờ vô hạn vì default cấu hình không rõ.

### 22.5. Late reply có thể chứa dữ liệu đã hết quyền xem

Nếu user bị revoke trong lúc request đang pending, một reply được phát sau đó phải được kiểm tra đúng security/tenant scope ở delivery boundary. Không tự gửi sensitive result qua callback cũ không còn được phép chỉ vì request ID khớp.

## 23. Observability: đo “không có reply” ở đúng ranh giới

### 23.1. Structured logs nên tách các mốc

~~~text
event=GATEWAY_REQUEST_STARTED
  requestRef=REQ-901
  messageType=ORDER_STATUS_LOOKUP
  route=orders.status.request
  replyDeadlineMs=300

event=REQUEST_CHANNEL_ACCEPTED
  requestRef=REQ-901
  channel=orders.status.request

event=HANDLER_STARTED
  requestRef=REQ-901
  handler=orderStatusLookup

event=HANDLER_COMPLETED_WITHOUT_REPLY
  requestRef=REQ-901
  handler=orderStatusLookup

event=GATEWAY_NO_REPLY
  requestRef=REQ-901
  observedOutcome=NO_REPLY
  elapsedMs=...

event=REPLY_DELIVERED
  requestRef=REQ-902
  responseType=OrderStatusReply

event=LATE_REPLY_OBSERVED
  requestRef=REQ-903
  replyAgeMs=...
~~~

Đây là **schema logs do ứng dụng đề xuất**, không phải một bộ log Spring Integration tự phát trong mọi cấu hình. Chỉ ghi `HANDLER_COMPLETED_WITHOUT_REPLY` nếu đã xác định handler kết thúc bình thường mà không tạo reply, không suy từ việc caller timeout.

### 23.2. Metrics gợi ý

| Metric | Đo gì? |
|---|---|
| `gateway_requests_total{method}` | Số invocations. |
| `gateway_replies_received_total{method}` | Số calls nhận reply hữu dụng. |
| `gateway_no_reply_total{method}` | Số calls hoàn tất mà không có reply. |
| `gateway_request_dispatch_failed_total{reason}` | Lỗi gửi request đến channel. |
| `gateway_reply_latency_seconds{method}` | Thời gian nhận reply (cho successes). |
| `gateway_no_reply_wait_seconds{method}` | Thời gian trước khi kết thúc không reply. |
| `gateway_reply_required_error_total` | Số lần endpoint bắt buộc reply nhưng handler trả null. |
| `gateway_late_reply_total{route}` | Số replies xuất hiện sau deadline/correlation expiry. |
| `gateway_reply_routing_failed_total{reason}` | Reply destination/correlation sai. |
| `gateway_filter_discarded_requests_total` | Requests bị Filter loại. |
| `gateway_async_worker_failed_total{class}` | Lỗi worker sau async boundary. |
| `gateway_outcome_unknown_total` | Commands có outcome chưa xác định. |
| `gateway_inflight_requests` | Số requests đang chờ. |
| `gateway_executor_queue_depth` | Backlog có thể gây reply muộn. |

Các tên chỉ là **gợi ý đo lường**, không khẳng định framework tự cung cấp. Tránh dùng `requestId`, `operationId`, `customerId`, `traceId` hay free-form order IDs làm metric labels vì cardinality cao và có thể lộ dữ liệu.

### 23.3. Vì sao cần riêng metric no-reply?

Nếu dashboard chỉ đếm exceptions:

~~~text
Gateway errors: 0
Gateway calls: 10000
Business replies: 9000
~~~

thì 1.000 calls không có business reply **không xuất hiện trong error count** khi no-reply hợp lệ theo cấu hình và method trả null. Không được kết luận “100% requests thành công” chỉ vì exception count bằng 0.

Lưu ý ví dụ minh họa về số liệu; cần đối chiếu time window, in-flight requests và duplicate attempts để xác định đúng tỷ lệ.

### 23.4. Tỷ lệ no-reply phải tách theo route/policy

Một Gateway một chiều `void` không nên bị thống kê là **no-reply failure** vì đó là hành vi được thiết kế. Chỉ đo no-reply ở **các method có business reply expectation**. Nếu một route trả null theo contract đặc biệt, cần gắn semantics riêng và cảnh báo khi vượt SLO của route đó.

### 23.5. Message History có thể hỗ trợ, nhưng không thay receipt

Spring Integration Message History (khi được bật) có thể giúp xác định một request đã đi qua endpoint nào. Nó không tự xác nhận:

- Temporary reply channel còn hoạt động khi reply đến.
- Một remote consumer đã commit transaction.
- Reply matching/correlation qua broker là đúng.
- Một Filter đã loại reply trước reply channel.
- Client đã nhận reply nếu connection bị đóng.

Cần kết hợp **message history, request/reply audit events, broker transport references, trace context và authoritative business status**.

### 23.6. SLO nên nhắm business result chứ không chỉ Gateway return

Ví dụ:

~~~text
SLO A:
  99.9% validated status queries return a typed Reply
  within 800 ms, excluding explicitly cancelled requests.

SLO B:
  99.99% accepted payment commands reach durable
  operation status COMPLETED or FAILED within 2 minutes.
~~~

Số liệu chỉ là minh họa cách viết SLO. Nếu chỉ đặt mục tiêu “Gateway không throw”, hệ thống có thể trả `null` hàng loạt mà vẫn trông khỏe mạnh.

## 24. Runbook: Gateway trả null thì điều tra từ đâu?

### 24.1. Câu hỏi đầu tiên: loại Gateway nào?

**Có phải method `void` không?** Nếu đúng, không có reply value là bình thường theo contract; vấn đề lúc đó là theo dõi handoff/business completion, không phải “null return”.

**Nếu method trả đối tượng:** hãy kiểm tra timeout, endpoint và reply routing như dưới đây.

### 24.2. Checklist từng bước

1. **Method declaration:** return type là object, primitive, collection, Optional hay `void`? Có `@Gateway(replyTimeout=...)` không?
2. **Gateway bean:** proxy có được đăng ký bằng `@MessagingGateway` và component scan đúng package không?
3. **Request channel:** tên channel có đúng, có subscriber/poller, có gửi được message không?
4. **Send failure:** có `MessageDeliveryException`, channel timeout hoặc task rejection bị caller catch rồi bỏ không?
5. **Handler invocation:** logs/probe chứng minh Service Activator được gọi chưa?
6. **Handler return:** trả object, null, throw hay phát reply sang channel khác?
7. **Reply required:** endpoint có `requiresReply=true` hoặc exception policy nào?
8. **Filter/Router:** request hoặc reply có bị discard/default route không?
9. **Transformer/headers:** có mất `replyChannel`, requestId, correlation hoặc wire reply destination không?
10. **Async boundary:** Executor/Queue/broker có backlog, poller stopped, worker error hoặc conversion lỗi không?
11. **Timeouts:** request send timeout, reply timeout và HTTP deadline có nhất quán không?
12. **Reply produced:** có bằng chứng reply message được tạo và gửi đúng destination không?
13. **Late reply:** reply có được sinh sau khi invocation kết thúc không?
14. **Broker transport:** header mapper, reply queue/topic, ACL, consumer group và DLQ có đúng không?
15. **Side-effect state:** nếu đây là command, durable operation ledger/receipt có COMPLETED hoặc OUTCOME_UNKNOWN không?
16. **Security:** query/callback có bị chặn vì tenant/source không hợp lệ hoặc quyền đã revoke không?
17. **Observability:** có tách `NO_REPLY` khỏi `NOT_FOUND`, `ERROR` và `REJECTED` trong logs/metrics không?
18. **Regression:** viết integration test tái hiện đúng route/timeout/loss trước khi sửa.

### 24.3. Bảng chẩn đoán nhanh

| Dấu hiệu | Nơi kiểm tra trước | Hướng sửa |
|---|---|---|
| Method return null đúng sau deadline | Handler không reply hoặc async quá chậm. | Typed reply hoặc timeout/async status redesign. |
| Method throw ngay lúc send | Channel subscriber/configuration. | Fix wiring/dispatch. |
| Handler trả object nhưng Gateway null | Reply routing, Filter, temporary reply channel. | Trace reply path end-to-end. |
| Null chỉ xảy ra khi tải cao | Executor/queue saturation, broker lag. | Backpressure, capacity, deadline policy. |
| Null chỉ xảy ra với một event type | Router không có route hoặc translator lỗi. | Schema/routing contract. |
| Null sau schema upgrade | Codec/header mapper/version mismatch. | Compatibility tests, typed error. |
| No reply và errorChannel có exception | Async failure không gửi business reply. | Map error to reply/status nếu contract cần. |
| Reply đến sau null | Gateway deadline quá sớm hoặc worker chậm. | Durable late-result handling, deadline tuning. |
| Có reply NOT_FOUND nhưng caller vẫn null | Reply channel/correlation mất. | Transport/header path. |
| Caller coi null là 404 | API boundary semantics sai. | Dùng NO_REPLY/UNKNOWN thay NOT_FOUND. |
| Payment caller null nhưng receipt COMPLETED | Reply mất sau side effect. | Reconcile; không charge lại. |
| No reply khi Filter discard | Rejection branch one-way. | Return rejected DTO hoặc fail-fast exception. |

### 24.4. Một quy trình điều tra ngắn

~~~text
Start with requestRef
  |
  +-> Was request accepted by channel?
  |       No -> dispatch failure
  |       Yes
  |
  +-> Was handler invoked?
  |       No -> routing/queue/broker
  |       Yes
  |
  +-> Was reply generated?
  |       No -> contract/handler/filter
  |       Yes
  |
  +-> Was reply sent to correct destination?
  |       No -> header mapping/routing
  |       Yes
  |
  +-> Did it arrive before Gateway deadline?
          No -> late reply/timeout/correlation
          Yes -> conversion/return handling
~~~

Đi theo **bằng chứng từng mốc**, không sửa bằng cách tăng replyTimeout lên vô hạn hoặc retry 100 lần khi nguyên nhân là handler luôn return null.

## 25. Ma trận kiểm thử Gateway thiếu reply

| ID | Kịch bản | Kết quả cần xác minh | Điều không được xảy ra |
|---|---|---|---|
| NR-01 | Gateway return type `OrderStatusReply`, handler trả object | Caller nhận reply thật. | Return null. |
| NR-02 | Gateway return type reference, handler terminal trả null | Caller có no-reply outcome theo config. | Coi null là FOUND. |
| NR-03 | Handler record request nhưng không reply | Probe nhận request, caller no-reply. | Kết luận không có handler. |
| NR-04 | Gateway method `void` | Caller không có business return value. | Đếm `void` là no-reply failure. |
| NR-05 | `DirectChannel` handler throw | Exception propagate/wrap. | Nuốt exception thành null. |
| NR-06 | `DirectChannel` không subscriber | Dispatch failure hiển thị. | Coi request đã xử lý. |
| NR-07 | Gateway request channel sai tên | Context/config failure rõ. | Silent fallback. |
| NR-08 | Gateway không được component scan | Không có proxy bean, test fail. | Gọi một object không tồn tại. |
| NR-09 | Reply timeout được cấu hình ngắn | Không có reply -> bounded no-reply. | Chờ vô hạn. |
| NR-10 | Reply đến ngay trước deadline | Caller nhận đúng reply. | Return null dù reply có hiệu lực. |
| NR-11 | Reply đến sau deadline | Late reply được phân loại/quan sát. | Ghép vào request mới. |
| NR-12 | Timeout 300ms, synchronous handler block 5s | Test nhận biết thời gian thực thi thực tế. | Giả định timeout kill handler. |
| NR-13 | `requiresReply=true` và handler return null | Reply-required failure theo endpoint. | Bắt mọi trường hợp thành null. |
| NR-14 | `requiresReply=false` và handler return null | No-reply path theo config. | Ném exception không mong đợi ở test. |
| NR-15 | Transformer không tạo output | Lỗi/handling theo Transformer contract. | Đồng nhất với Service Activator null. |
| NR-16 | Filter discard request | Handler business không nhận, no-reply/rejection route rõ. | Caller coi là NOT_FOUND. |
| NR-17 | Filter discard reply đã tạo | Gateway không nhận reply, metrics chỉ đúng điểm drop. | Báo reply đã tới Gateway. |
| NR-18 | Filter throw on rejection | Error path thay vì silent drop. | Giả định discardChannel luôn chạy. |
| NR-19 | Router unknown type | Rejected/exception route rõ. | Mặc định không reply mà không audit. |
| NR-20 | Router default to terminal sink | Gateway no-reply được phát hiện. | Xem là business success. |
| NR-21 | Transformer làm mất `replyChannel` | Regression test bắt wrong reply routing. | Kết luận handler không trả. |
| NR-22 | Handler output sang unrelated channel | Gateway no-reply, trace correct destination. | Nhầm output channel với replyChannel. |
| NR-23 | Spring `MessageHeaders.ID` khác sau rebuild | Request matching bằng stable request ID. | Dedupe theo runtime ID. |
| NR-24 | Handler trả typed `NOT_FOUND` | Caller nhận non-null reply NOT_FOUND. | Return null thay typed status. |
| NR-25 | Handler trả typed `PENDING` | Caller biết đang xử lý. | Coi PENDING là null. |
| NR-26 | Handler trả collection rỗng trong DTO | Có non-null reply. | Coi empty result là no-reply. |
| NR-27 | Gateway return primitive và no reply | Có error/conversion contract. | Unboxing null im lặng. |
| NR-28 | Gateway return Optional theo custom mapping | Test converter/type semantics thật. | Giả định Optional tự giải quyết timeout. |
| NR-29 | Caller gọi `reply.status()` khi reply null | Wrapper chặn NPE. | NPE không được xử lý. |
| NR-30 | Async worker chậm | Gateway hết deadline nhưng worker vẫn chạy. | Coi null là worker chưa bắt đầu. |
| NR-31 | Async worker throw | Error handling/alert rõ, no-reply không che failure. | Caller bắt exception đã qua thread boundary. |
| NR-32 | Executor saturated | Queue depth/rejection tăng. | Tăng timeout mãi mà không backpressure. |
| NR-33 | QueueChannel không poller | Pending queue được quan sát. | Coi request đã lost chắc chắn. |
| NR-34 | QueueChannel full | Send failure/timeout phân biệt reply timeout. | Đếm send failure là no reply thông thường. |
| NR-35 | Broker request–reply missing reply topic | Correct configuration error. | Coi là NOT_FOUND. |
| NR-36 | Reply consumer group không lắng nghe | Reply backlog/TTL/correlation có audit. | Silent loss không cảnh báo. |
| NR-37 | Reply header mapper drop requestId | No reply/mis-correlation được phát hiện. | Ghép replies theo orderId ngẫu nhiên. |
| NR-38 | Late reply #1 đến lúc request #2 đang chờ | Không match sai vào #2. | Reply leak. |
| NR-39 | Duplicate reply cùng requestId | First valid/multiple reply policy. | Hai side effects do duplicate response. |
| NR-40 | Splitter child #2 không reply | Aggregator partial/timeout policy. | Chờ vô hạn không trạng thái. |
| NR-41 | Aggregator group chưa release | Gateway no-reply đúng timeout; nhóm còn pending. | Coi toàn batch NOT_FOUND. |
| NR-42 | Scatter–Gather Fraud timeout | Không APPROVED chỉ nhờ Pricing/Inventory. | Trả success giả. |
| NR-43 | Resequencer thiếu sequence #2 | Gap/recovery/timeout. | Đảo thứ tự hoặc fake reply. |
| NR-44 | Claim Check token expired | Technical expired-claim outcome. | Coi là order not found. |
| NR-45 | JSON decode failure trước typed handler | Adapter-specific error route. | Bắt Filter như thể đã xử lý. |
| NR-46 | Authorization denied | Security error/rejection. | Che hết thành null giống network timeout. |
| NR-47 | Client khai reply destination nguy hiểm | Destination allowlist/auth. | Gửi data sang attacker. |
| NR-48 | Query no-reply và retry bounded | Tổng deadline, backoff có giới hạn. | Retry storm. |
| NR-49 | Command no-reply nhưng đã commit side effect | Reconciliation + stable operationId. | Double charge. |
| NR-50 | Same operationId, payload khác | Fingerprint conflict. | Dedupe success sai payload. |
| NR-51 | Broker redelivery tạo new Spring message ID | Business operation dedupe ổn định. | Double processing. |
| NR-52 | Outbox publish duplicate | Consumer idempotency + receipt. | Tuyên bố exactly-once mặc định. |
| NR-53 | Caller timeout nhưng status store COMPLETED | Return authoritative result trên query status. | Tự rollback remote effect. |
| NR-54 | Debug logs chứa PII | Redaction/protected reference. | Log toàn raw request. |
| NR-55 | Client gửi 10.000 queries không reply | Rate limit/bulkhead/timeout. | Thread exhaustion. |
| NR-56 | Gateway no-reply metric tăng | Alert đúng route, không đếm void methods. | Báo 100% success vì exceptions=0. |
| NR-57 | Message History bật nhưng chưa có receipt | Distinguish trace vs business completion. | Dựa vào history để khẳng định commit. |
| NR-58 | Backend trả NOT_FOUND từ stale projection | Document consistency contract. | Coi NOT_FOUND luôn tức thời tuyệt đối. |
| NR-59 | Method return `LookupOutcome` có ERROR | Caller xử lý typed error đúng. | Ép thành FOUND/NOT_FOUND. |
| NR-60 | Status query và command dùng cùng timeout policy | Config phân biệt latency/risk. | Copy timeout vô điều kiện. |

### 25.1. Nên kiểm thử ở những lớp nào?

| Cấp độ | Chứng minh được | Không chứng minh |
|---|---|---|
| **Java unit test** | Wrapper `null → NO_REPLY`, typed result handling. | Gateway proxy và message routing. |
| **Spring Integration sync test** | Gateway/DirectChannel/handler/return/requiresReply. | Async race hoặc broker mapping. |
| **Spring Integration async test** | ExecutorChannel, bounded wait, late reply/error flow. | Broker persistence nếu không dùng broker. |
| **Adapter/contract test** | Reply topic/queue, headers, serializer, correlation. | Business commit ngoài adapter. |
| **Database/ledger test** | Idempotency, operation status, transaction/fingerprint. | External side effect nếu mock. |
| **System/chaos test** | Crash, ack lost, duplicate, overload, late replies. | Mọi tình huống production chưa mô phỏng. |
| **Security test** | Tenant, reply destination ACL, PII, replay authorization. | Security boundaries không nằm trong test. |

### 25.2. Ba golden fixtures cốt lõi

~~~text
Fixture A — normal reply:
  requestId=REQ-1
  handlerResponse=OrderStatusReply(FOUND)
  expected=non-null Reply(FOUND)

Fixture B — no reply:
  requestId=REQ-2
  handlerEmitsReply=false
  gatewayReplyTimeout=bounded
  expected=null or explicit no-reply mapping by tested configuration
  expectedHandlerInvoked=true

Fixture C — business not found:
  requestId=REQ-3
  handlerResponse=OrderStatusReply(NOT_FOUND)
  expected=non-null Reply(NOT_FOUND)
~~~

Kiểm thử riêng ba fixtures giúp phát hiện lỗi phổ biến nhất: **đánh đồng Gateway không nhận reply với kết quả nghiệp vụ NOT_FOUND**. Nếu hệ thống yêu cầu một kiểu `LookupOutcome` duy nhất, các fixtures vẫn nên phân biệt trạng thái từ Gateway boundary.

## 26. Những sai lầm phổ biến

| Anti-pattern | Hậu quả | Giải pháp |
|---|---|---|
| “Gateway trả null nghĩa là NOT_FOUND.” | Kết luận sai khi backend timeout. | Reply `NOT_FOUND` tường minh; null → `NO_REPLY`. |
| “Gateway có return type nên handler chắc chắn reply.” | Không thấy Filter/Router/terminal endpoint. | Integration test full request–reply flow. |
| “Method `void` và method trả null giống nhau.” | Sai business contract. | Phân biệt one-way và request–reply. |
| “Service Activator return null là gửi `Message<null>`.” | Hiểu sai Spring Message payload contract. | Null thường là no-reply hoặc error theo endpoint. |
| “Mọi handler trả null đều không lỗi.” | Bỏ qua requiresReply/Transformer behavior. | Test endpoint-specific semantics. |
| “Reply timeout luôn cancel downstream handler.” | Side effect vẫn có thể commit sau timeout. | Operation status/reconciliation. |
| “Tăng replyTimeout lên vô hạn để hết null.” | Thread starvation và latency cao. | Bounded deadlines và async redesign. |
| “Bắt exception và return null cho đơn giản.” | Che lỗi DB, mapping, auth, bug. | Typed error và classified handling. |
| “Nếu handler đã trả object thì Gateway chắc nhận.” | Reply bị Filter drop/header missing. | Trace replyChannel tới Gateway. |
| “Filter discard là đã trả REJECTED.” | Caller no-reply/timeout. | Reply DTO hoặc fail-fast error contract. |
| “Không có subscriber thì chỉ đợi rồi null.” | Bỏ sót dispatch failure. | Kiểm tra channel error và subscriptions. |
| “Router default output gửi vào nullChannel là bình thường.” | Request–reply bị silent loss. | Explicit default rejection. |
| “`MessageHeaders.ID` chính là requestId.” | Mismatch khi message được rebuild. | Stable application request ID. |
| “Spring replyChannel object gửi được qua Kafka.” | Reply routing không wire-portable. | Protocol reply queue/topic + correlation. |
| “Nếu reply muộn thì Java caller sẽ nhận sau.” | Lời gọi đã kết thúc không thể nhận value muộn. | Completion event/status store. |
| “Ghép reply chỉ theo orderId là đủ.” | Late response ghép sai request. | Request ID + in-flight registry. |
| “No reply có nghĩa command chưa chạy.” | Retry gây double side effect. | Durable operation ledger/idempotency. |
| “Retry mỗi lần tạo new payment ID.” | Remote charge lặp. | Giữ stable operationId và fingerprint. |
| “Có errorChannel thì Gateway chắc trả typed error.” | Async error không được map thành reply. | Error-to-reply/status flow rõ. |
| “No reply đếm vào exception metric.” | Bỏ sót failures không throw. | Measure `gateway_no_reply_total` riêng. |
| “Trả Optional.empty là đủ semantics.” | Không phân biệt timeout và NOT_FOUND. | Typed result statuses. |
| “Primitive return type có thể đại diện no reply.” | Unboxing/conversion error. | Reference DTO hoặc explicit failure. |
| “QueueChannel luôn durable.” | Process crash làm mất pending request. | Persistent queue/broker khi cần. |
| “Aggregated result chưa đủ child thì Gateway lỗi.” | Có thể chỉ chờ release đến timeout. | Partial/timeout release policy. |
| “Reply destination do caller tự khai là đáng tin.” | Data exfiltration. | Destination allowlist/authorization. |
| “Một trace span trống chứng minh request chưa chạy.” | Missing sampling/data không có nghĩa no work. | Dùng business/transport evidence. |
| “Chỉ test handler method, không test Gateway.” | Không biết reply routing đúng không. | Spring Integration integration tests. |
| “Không cần status store vì Gateway return object.” | Timeout/late reply không có cách truy nguyên. | Durable receipt nếu operation quan trọng. |

## 27. Bài tập thực hành

1. **Tạo Gateway request–reply:** khai báo `OrderStatusLookupGateway.lookup(...)` trả `OrderStatusReply` với `replyTimeout` rõ.
2. **Tạo Gateway one-way:** khai báo `void submit(...)` khác interface/method; giải thích khác nhau về Java contract.
3. **Flow trả reply:** xây Service Activator trả `OrderStatusReply(FOUND)`, assert caller nhận non-null.
4. **Flow trả null:** xây terminal Service Activator trả `null`, assert Gateway trả no-reply theo config; kiểm tra probe handler đã chạy.
5. **Null vs NOT_FOUND:** tạo typed `OrderStatusReply(NOT_FOUND)` và chứng minh không phải `null`.
6. **Null vs empty list:** trả `OrderListReply(List.of())` và kiểm tra non-null payload.
7. **Application wrapper:** viết `OrderStatusLookupService` chuyển `null` thành `StatusQueryResult(NO_REPLY)`.
8. **Unit fake Gateway:** fake trả null và fake trả FOUND; test wrapper không nhầm với NOT_FOUND.
9. **Reply timeout:** đổi thời hạn chờ, đo upper bound hợp lý, không dùng `Thread.sleep` cố định để assert đúng 1 ms.
10. **Sync handler chậm:** dùng DirectChannel với handler block, giải thích reply timeout không tự hủy synchronous work.
11. **No subscriber:** bỏ Service Activator trong test context và phân biệt dispatch failure với no-reply.
12. **RequiresReply:** bật cấu hình reply-required ở endpoint có return type; xác minh null tạo failure thay vì silent absence.
13. **Filter discard request:** thiết kế đường rejected rõ; không để Gateway trả null như kết quả business.
14. **Filter discard reply:** tạo reply rồi cố ý loại ở nhánh sau; quan sát Gateway không nhận và debug đúng điểm.
15. **Router unknown:** định nghĩa default rejection hoặc error route; không trỏ unknown vào nullChannel vô audit.
16. **Transformer header loss:** xây transformer tạo new message thiếu `replyChannel` trong test, phát hiện regression; sửa bằng propagation có chọn lọc.
17. **ExecutorChannel:** chạy handler ở worker thread, dùng latch để kiểm tra Gateway có thể hết deadline trước completion.
18. **Late reply:** giữ worker bằng latch, đợi Gateway no-reply, thả latch, xác minh reply muộn không lẫn sang request khác.
19. **QueueChannel:** dùng poller stop/start, đo pending queue và timeout; không gọi queue memory là durable.
20. **Reply over broker:** thiết kế request/reply topics hoặc queues với requestId, correlation, reply destination có quyền.
21. **Wrong correlation:** gửi reply cho `REQ-901` khi caller đang đợi `REQ-902`; test không match sai.
22. **Multiple replies:** gửi hai replies cùng requestId, thiết kế first-valid/duplicate policy.
23. **Gateway primitive return:** thử một method trả `int` với no-reply theo test, tài liệu hóa error behavior và chọn DTO thay thế.
24. **Technical error:** Service Activator throw; caller thấy error class/cause chain, không ép thành NOT_FOUND.
25. **Async errorChannel:** worker throw sau Gateway return; kiểm tra error handler và NO_REPLY/correlation metrics.
26. **Business command:** giả lập `ReserveInventory` commit xong nhưng reply mất; retry cùng operationId và đảm bảo effect chỉ một lần.
27. **Payload conflict:** cùng operationId nhưng amount khác, phát hiện conflict thay vì trả receipt cũ vô điều kiện.
28. **Splitter/Aggregator:** một child không reply, kiểm tra timeout/partial result và không báo success giả.
29. **Scatter–Gather:** Fraud timeout trong khi Inventory/Pricing thành công; thiết kế final outcome an toàn.
30. **Resequencer:** một reply sequence bị thiếu, thêm gap policy; không đổi sequence numbers tùy tiện.
31. **Claim Check:** claim token hết hạn trước khi reply, trả technical error/reconciliation thay vì NOT_FOUND.
32. **Security:** thử reply destination do user tự khai trỏ đến queue trái quyền, kiểm tra allowlist.
33. **Metrics:** ghi `gateway_no_reply_total` theo route; không đếm Gateway `void` như failure.
34. **Runbook:** từ một `REQ-901` trả null, truy theo request sent, handler invoked, reply generated, reply delivered, deadline.
35. **Production decision:** chọn giữa synchronous Gateway, bounded request–reply, async command + durable status, trình bày lý do theo SLA.

### 27.1. Tiêu chí nghiệm thu

Một implementation đáp ứng bài học khi:

- Phương thức Gateway **trả reference type** và method `void` được phân biệt về contract.
- Một reply hợp lệ có non-null payload và business status rõ.
- No-reply không bị đánh đồng với NOT_FOUND/REJECTED/ERROR.
- Reply timeout được cấu hình có chủ đích, có giới hạn và đo lường.
- Handler trả null được quan sát riêng với dispatch failure hoặc exception.
- Reply routing qua Transformer/Filter/Router/adapter không làm mất correlation.
- Late replies không bị ghép sai vào request mới.
- Commands có side effect dùng stable operation identity, durable receipt và retry/reconciliation an toàn.
- Error channels, SLO, logging và metrics phân biệt các mốc thật.
- JUnit unit/integration/system tests kiểm tra đúng ranh giới cần tin cậy.

## 28. Câu hỏi tự kiểm tra

**Câu 1: Gateway trả `null` khi không có reply có giống Gateway phương thức `void` không?**

Không. `void` là chữ ký không yêu cầu business value. Một method trả `OrderStatusReply` mà nhận `null` là tình huống request–reply không có giá trị phản hồi trong invocation theo config.

**Câu 2: Service Activator return `null` có nghĩa đã gửi một Spring `Message<null>` không?**

Không. Payload của Spring Message không được null theo contract; null ở reply-producing handler thường nghĩa là không tạo reply hoặc gây lỗi khi reply bắt buộc.

**Câu 3: Gateway không nhận reply có chứng minh handler chưa chạy không?**

Không. Handler có thể đã chạy, trả null, tạo reply sai channel, hoặc hoàn tất sau deadline. Cần logs/probe/trace theo từng mốc.

**Câu 4: `replyTimeout` có tự kill handler đang chạy DirectChannel không?**

Không. Timeout chờ reply không phải interruption/cancellation của mọi downstream operation, nhất là handler đồng bộ trong caller thread.

**Câu 5: Gateway nhận `null` có được trả HTTP 404 Not Found không?**

Không mặc định. Null có thể biểu thị timeout/misrouting/no response. Chỉ typed authoritative NOT_FOUND mới chứng minh kết quả nghiệp vụ tương ứng.

**Câu 6: Làm sao biểu diễn đơn hàng thực sự không tồn tại?**

Trả một DTO khác null như `OrderStatusReply(status=NOT_FOUND)` với requestId và reason code, theo consistency contract.

**Câu 7: Reply đến sau Gateway timeout có tự vào return value của Java method không?**

Không. Invocation đã kết thúc; cần một late-reply/durable completion path nếu kết quả còn giá trị.

**Câu 8: Nếu Router không có route, Gateway luôn trả null phải không?**

Không. Tùy default route/resolutionRequired/error handling, có thể throw hoặc discard/no-reply. Cần kiểm thử cấu hình thật.

**Câu 9: Filter discard có tự trả một reply REJECTED không?**

Không. Phải thiết kế rejection response/error path riêng nếu caller đang chờ.

**Câu 10: `requiresReply=true` thay đổi điều gì?**

Nó có thể biến handler không tạo reply thành reply-required exception thay vì một no-reply im lặng, theo endpoint implementation.

**Câu 11: Primitive `int` có phù hợp khi Gateway có thể không reply không?**

Không an toàn vì primitive không biểu diễn null; cần typed DTO/error contract và test conversion/unboxing.

**Câu 12: Optional có tự phân biệt no-reply và NOT_FOUND không?**

Không. `Optional.empty()` thiếu thông tin vì sao không có giá trị, và framework mapping semantics phải được kiểm thử.

**Câu 13: Khi async worker throw, caller có luôn nhận được exception trực tiếp không?**

Không. Async boundary làm lỗi thường cần errorChannel/adapter handler/audit/status route riêng.

**Câu 14: Tại sao một Gateway có replyTimeout ngắn dễ trả null dưới tải cao?**

Vì queue backlog, thread scheduling, broker lag hoặc handler latency có thể làm reply đến sau deadline. Cần đo p99, queue depth và backpressure.

**Câu 15: Nếu payment Gateway trả null, có được retry bằng một paymentOperationId mới không?**

Không nếu cùng logical payment. Remote side effect có thể đã commit; phải dùng stable idempotency key, receipt/status reconciliation và policy hợp lệ.

**Câu 16: `MessageHeaders.ID` có phải requestId ổn định qua broker không?**

Không. Message runtime có thể được xây lại và mang ID khác; giữ requestId/correlation/application identity ở wire contract.

**Câu 17: Correlation ID và replyChannel có cùng nhiệm vụ không?**

Không. Correlation liên kết logical messages; replyChannel/reply destination chỉ nơi gửi response.

**Câu 18: Một Aggregator chưa release group có khiến Gateway không nhận reply không?**

Có. Nếu flow yêu cầu aggregate result và group chưa đủ để release, reply tổng hợp chưa được gửi. Cần timeout/partial/failure policy.

**Câu 19: Trong Scatter–Gather, chỉ hai trong ba branches success thì nên trả success chung chưa?**

Tùy business contract. Nếu nhánh Fraud bắt buộc, không được APPROVED khi Fraud chưa có outcome hợp lệ.

**Câu 20: Một reply được tạo nhưng Gateway vẫn null, kiểm tra gì?**

Reply output channel, Filter/Transformer phía sau, `replyChannel` propagation, broker reply destination, correlation và deadline.

**Câu 21: Có thể dùng errorChannel như một business reply tự động không?**

Không mặc định. ErrorMessage/errorChannel cần cấu hình; nếu muốn typed error reply phải map và gửi qua reply path chính xác.

**Câu 22: Gateway `void` có nên tính vào `gateway_no_reply_total` không?**

Không, vì nó không hứa business reply. Metric no-reply phục vụ những methods có kỳ vọng nhận reply.

**Câu 23: Vì sao không log toàn request để debug null?**

Vì dữ liệu có thể chứa PII/credentials. Dùng stable opaque requestId, reason/status code, route, elapsed time và protected payload reference nếu cần.

**Câu 24: Khi một Gateway no-reply, bước điều tra đầu tiên là gì?**

Xác định method có return type gì, timeout config, request đã dispatch chưa, handler có chạy và sinh reply hay không, rồi lần theo reply channel/correlation/deadline.

**Câu 25: Nếu không có bảo đảm reply trong vài giây, kiến trúc nào hợp lý hơn?**

Cân nhắc asynchronous command + durable acceptance/status store + completion event, thay vì để synchronous Gateway thread chờ vô hạn.

## 29. Checklist trước khi đưa Gateway request–reply vào production

| Câu hỏi | Trạng thái cần xác nhận |
|---|---|
| Method có thật sự cần business reply ngay không? | Nếu không, chọn one-way `void` API rõ ràng. |
| Có xác định type reply và các business outcomes? | `FOUND/NOT_FOUND/REJECTED/PENDING` hoặc status tương đương. |
| `null` biểu thị gì? | `NO_REPLY/UNKNOWN`, không tự là NOT_FOUND. |
| Reply deadline được đặt có chủ đích? | Bounded, dựa trên latency budget và SLO. |
| Request send timeout được kiểm tra riêng? | Không nhầm với reply timeout. |
| Handler có luôn tạo reply khi contract bắt buộc? | Typed reply hoặc reply-required/error semantics. |
| Filter/Router có default rejection rõ? | Không silent discard trong request–reply. |
| Transformer có giữ selected reply metadata? | Reply reaches Gateway qua mọi hop. |
| Async handler có error path và backpressure? | Không chỉ mong caller catch được exception. |
| Late reply có nơi xử lý? | Không ghép nhầm vào request khác. |
| Broker reply destination có auth và correlation? | Không arbitrary client-supplied destination. |
| Command retry có idempotency key và receipt? | Không nhân đôi side effect khi timeout. |
| Observability đo no-reply riêng? | Không chỉ exception counter. |
| Security/PII được kiểm soát? | Redacted logs, tenant permission, TTL và rate limit. |
| Có integration/system tests theo transport thật? | Proxy/channel/adapter/recovery được xác minh. |

## 30. Kết luận

**Gateway trả `null` khi không có reply** cần được hiểu là một tình huống **vắng mặt phản hồi ở request–reply boundary**, chứ không phải một kết luận nghiệp vụ. Khi một `@MessagingGateway` method khai báo trả `OrderStatusReply`, request có thể được gửi thành công nhưng Service Activator không tạo reply, Filter discard, Router đi nhánh im lặng, Transformer làm mất `replyChannel`, Aggregator chưa release hoặc reply đến quá hạn. Trong các điều kiện/cấu hình cho phép hoàn tất không có value, caller có thể nhận `null`; trong những đường lỗi khác, Gateway/endpoint có thể **ném exception** thay vì trả null.

**Ba phân biệt không được bỏ qua:**

1. **`void` one-way khác reference-type Gateway trả null.** `void` không yêu cầu business reply; null ở Gateway có return type là thiếu một giá trị được kỳ vọng.
2. **`null` khác `Reply(NOT_FOUND)`.** Không có reply trước deadline không chứng minh order không tồn tại hay command chưa được xử lý; nên dùng typed status, `NO_REPLY/UNKNOWN` và authoritative receipt.
3. **Reply timeout khác hủy downstream processing.** DirectChannel có thể block đồng bộ; ExecutorChannel/QueueChannel/broker có thể xử lý sau deadline; late reply và retry phải có correlation, error handling và idempotency.

Trong `SPRING_INTEGRATION_PATTERN`, hãy kiểm thử từ Java Gateway proxy qua Router, Filter, Transformer, Splitter, Aggregator, Scatter–Gather, Resequencer, Claim Check, Service Activator, retry/error channel đến reply destination thực tế. Một thiết kế đáng tin trả lời được ba câu: **“Request có thật đã được xử lý ở đâu?”, “Reply có được tạo và tới đúng Gateway trước deadline không?”, và “Nếu không có reply, caller sẽ nhận trạng thái gì và có thể phục hồi an toàn như thế nào?”**. Khi các ranh giới đó rõ ràng, `null` không còn là một giá trị bí ẩn khiến hệ thống trả sai NOT_FOUND, mất correlation hoặc lặp tác động nghiệp vụ.
