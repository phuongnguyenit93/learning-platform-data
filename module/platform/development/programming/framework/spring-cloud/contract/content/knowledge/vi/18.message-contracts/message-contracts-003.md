# Input, outputMessage và địa chỉ gửi hoặc nhận

## Mục tiêu bài học

Trong **Spring Cloud Contract**, hợp đồng không chỉ dành cho HTTP request/response. Nhiều hệ thống tích hợp bằng **thông điệp bất đồng bộ**: một service nhận lệnh từ queue/topic, thực hiện nghiệp vụ rồi phát event cho service khác. Với **Groovy DSL** hoặc **YAML DSL**, ta có thể mô tả điều kiện kích hoạt và **thông điệp mà producer cam kết phát ra**, từ đó sinh kiểm thử phía producer, tạo stub và cho consumer dùng **Stub Runner** trong CI.

Điểm quan trọng nhất của bài: hãy luôn đọc message contract **từ góc nhìn producer đang được kiểm chứng**. Trong một hợp đồng:

- `input` mô tả **điều làm producer bắt đầu hành vi**: gọi một phương thức kiểm thử hoặc đưa thông điệp vào một nguồn mà producer lắng nghe.
- `outputMessage` mô tả **thông điệp producer phải phát ra** sau điều kiện kích hoạt: đích gửi, body và headers.
- `messageFrom(...)` trong `input` và `sentTo(...)` trong `outputMessage` biểu diễn hai **hướng khác nhau**; ý nghĩa vật lý phụ thuộc vào adapter và cấu hình hệ thống messaging.

Sau bài học, bạn có thể:

1. Phân biệt `triggeredBy(...)` với `messageFrom(...)` trong `input`.
2. Mô tả `messageBody`, `messageHeaders`, `body` và `headers` đúng vị trí trong hợp đồng.
3. Chỉ ra nguồn nhận và đích gửi thông điệp khi dùng queue, topic hoặc binding.
4. Viết message contract bằng Groovy DSL và YAML DSL cho hai tình huống: **producer tự phát event** và **producer nhận command rồi phát event**.
5. Thiết lập hướng kiểm chứng producer test, label/stub trigger và consumer tests qua Stub Runner.
6. Nhận diện giới hạn của một contract đối với retry, ordering, idempotency, broker configuration và CI.

## 1. Góc nhìn producer: thông điệp vào và thông điệp ra

Giả sử hệ thống có hai hoạt động:

1. **Order Service** nhận yêu cầu thanh toán một đơn hàng.
2. Khi thanh toán thành công, Order Service phát event `ORDER_PAID` để **Shipping Service** nhận và bắt đầu xử lý vận chuyển.

Có hai cách kích hoạt để kiểm thử hành vi phát event:

- Gọi một phương thức **test-side** nhằm kích hoạt xử lý đơn hàng trực tiếp.
- Gửi một **command message** vào nơi Order Service đang nhận thông điệp.

Hai cách đều có thể dẫn đến cùng output event, nhưng không phải cùng một loại `input`.

~~~mermaid
flowchart LR
    T["Hành động kích hoạt"] --> P["Order Service<br/>producer đang kiểm thử"]
    Q["Command trên nguồn nhận<br/>orders.commands"] --> P
    P --> E["Event ORDER_PAID"]
    E --> D["Đích gửi<br/>orders.events"]
    D --> C["Shipping Service<br/>consumer"]
~~~

Trong sơ đồ:

- `orders.commands` là **nguồn producer nhận thông điệp** nếu kịch bản kích hoạt bằng command.
- `orders.events` là **đích producer phát event**.
- Shipping Service là **consumer của event**, không phải đối tượng bắt buộc tham gia test producer.
- Nếu dùng `triggeredBy`, nhánh command message có thể không cần thiết trong test.

**Không đánh đồng `outputMessage` với HTTP response.** Một HTTP response có thể trả về ngay, trong khi event được phát qua broker; đôi khi producer còn phát nhiều event hoặc xử lý bất đồng bộ. Hợp đồng mô tả một cam kết quan sát được mà công cụ và môi trường test có thể xác minh.

## 2. Những thành phần chính của message contract

| Thành phần DSL | Nằm ở đâu? | Ý nghĩa |
| --- | --- | --- |
| `label` | Cấp contract | Tên gợi nhớ kịch bản; thường hữu ích để kích hoạt message stub theo nhãn |
| `input` | Cấp contract | Điều kiện hoặc nguồn kích hoạt producer |
| `triggeredBy(...)` | Bên trong `input` | Tham chiếu phương thức được generated producer test gọi để tạo sự kiện |
| `messageFrom(...)` | Bên trong `input` | Nguồn/binding/kênh chứa message **được đưa vào producer** |
| `messageBody(...)` | Bên trong `input` | Nội dung command/message đầu vào khi dùng kịch bản nhận message |
| `messageHeaders` | Bên trong `input` | Headers của message đầu vào |
| `outputMessage` | Cấp contract | Thông điệp producer phải phát |
| `sentTo(...)` | Bên trong `outputMessage` | Đích/binding/kênh gửi message đầu ra |
| `body(...)` | Bên trong `outputMessage` | Payload được kỳ vọng ở message phát ra |
| `headers` | Bên trong `outputMessage` | Headers producer phải đặt trên message đầu ra |

Các tên trên là cách diễn đạt thường gặp của **Groovy DSL**. Trong YAML DSL, chúng xuất hiện dưới dạng thuộc tính có cấu trúc tương ứng. Khả năng hỗ trợ chi tiết và cách giải quyết destination phụ thuộc phiên bản Spring Cloud Contract cùng tích hợp messaging đang dùng.

### Quy tắc nhớ

~~~text
input:
  triggeredBy  = generated test gọi phương thức kích hoạt
  messageFrom  = generated test đưa command vào phía producer
  messageBody  = dữ liệu của command đầu vào
  messageHeaders = metadata của command đầu vào

outputMessage:
  sentTo       = nơi producer phải phát event
  body         = payload event kỳ vọng
  headers      = metadata event kỳ vọng
~~~

Với một kịch bản đơn lẻ, thường chọn **một cách kích hoạt phù hợp**: `triggeredBy` hoặc `messageFrom`. Không đặt cả hai chỉ vì muốn “bao phủ đầy đủ”; điều đó dễ khiến test gọi producer hai lần hoặc làm mất rõ ràng về điểm bắt đầu luồng xử lý.

## 3. Ví dụ 1: producer chủ động phát event qua triggeredBy

Giả sử Order Service đã có nghiệp vụ xác nhận thanh toán. Ta muốn xác minh rằng gọi nghiệp vụ đó sẽ phát một event đúng cấu trúc.

### Groovy DSL

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description "Khi đơn được thanh toán, phát ORDER_PAID"
    label "order_paid"

    input {
        triggeredBy("markTestOrderAsPaid()")
    }

    outputMessage {
        sentTo("orders.events")
        body(
            eventId: "EVT-TEST-0001",
            eventType: "ORDER_PAID",
            orderId: "ORD-TEST-1001",
            paidAmount: 150000
        )
        headers {
            header("eventType", "ORDER_PAID")
            header("correlationId", "CORR-TEST-0001")
        }
    }
}
~~~

Giải thích từng phần:

1. `label "order_paid"` đặt **nhãn kịch bản**. Nhãn này không phải tên broker topic.
2. `input.triggeredBy("markTestOrderAsPaid()")` tham chiếu phương thức mà generated producer test cần gọi để kích hoạt hành vi.
3. `outputMessage.sentTo("orders.events")` mô tả đích được kỳ vọng cho event phát ra.
4. `body(...)` là payload event được consumer quan sát.
5. `headers` kiểm tra các thuộc tính metadata mà consumer có thể cần, ví dụ loại event và correlation ID.

Các mã `EVT-TEST-0001`, `ORD-TEST-1001` và `CORR-TEST-0001` là dữ liệu **tổng hợp**, không lấy từ production. Kịch bản phải có fixture phù hợp để producer phát đúng nội dung. Nếu ID hoặc timestamp thực tế mang tính động, nên dùng giá trị kiểm soát được trong base test hoặc matcher phù hợp, thay vì chép một giá trị production vào hợp đồng.

**Chú ý:** `markTestOrderAsPaid()` là phương thức phía kiểm thử; nó **không** được chạy trong Stub Runner khi consumer nhận event. Phương thức phải tồn tại trong ngữ cảnh test producer và thực sự kích hoạt logic phát message cần xác minh.

### YAML DSL tương ứng

~~~yaml
description: "Khi đơn được thanh toán, phát ORDER_PAID"
label: order_paid
input:
  triggeredBy: markTestOrderAsPaid()
outputMessage:
  sentTo: orders.events
  body:
    eventId: EVT-TEST-0001
    eventType: ORDER_PAID
    orderId: ORD-TEST-1001
    paidAmount: 150000
  headers:
    eventType: ORDER_PAID
    correlationId: CORR-TEST-0001
~~~

YAML thể hiện cùng ý tưởng bằng mapping. Cú pháp cụ thể của message contract, ví dụ tên field và matcher ở từng vị trí, cần được kiểm chứng với phiên bản Spring Cloud Contract mà dự án sử dụng. **Không đặt cùng hai bản Groovy và YAML mô tả y hệt một kịch bản trong nguồn build nếu không có chủ đích**, vì có thể tạo kiểm thử/stub trùng lặp.

## 4. Ví dụ 2: producer nhận command bằng messageFrom rồi phát event

Đây là tình huống rõ ràng nhất để phân biệt **địa chỉ nhận** với **địa chỉ gửi**.

Order Service nhận command `PAY_ORDER` tại nguồn `orders.commands`, sau đó phát `ORDER_PAID` tới đích `orders.events`.

### Groovy DSL cho message đầu vào

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description "Nhận PAY_ORDER rồi phát ORDER_PAID"
    label "pay_order_command"

    input {
        messageFrom("orders.commands")
        messageBody(
            commandId: "CMD-TEST-0001",
            commandType: "PAY_ORDER",
            orderId: "ORD-TEST-1001"
        )
        messageHeaders {
            header("correlationId", "CORR-TEST-0001")
        }
    }

    outputMessage {
        sentTo("orders.events")
        body(
            eventId: "EVT-TEST-0001",
            eventType: "ORDER_PAID",
            orderId: "ORD-TEST-1001"
        )
        headers {
            header("correlationId", "CORR-TEST-0001")
        }
    }
}
~~~

**Diễn giải luồng:**

1. Generated producer test cần đưa thông điệp có `messageBody` và `messageHeaders` vào **nguồn vào** mà producer đang lắng nghe.
2. Producer xử lý command thông qua listener/handler thực tế trong phạm vi cấu hình test.
3. Producer phát thông điệp đến **đích ra** được khai báo trong `sentTo`.
4. Test sử dụng tích hợp message verifier để thu được output, rồi so sánh body và headers với contract.

Trong kịch bản này, `input` là một **message đi vào producer**, không phải HTTP request và không phải dữ liệu consumer đang nhận từ producer. `outputMessage` là message phát ra từ producer.

### YAML DSL tương ứng

~~~yaml
description: "Nhận PAY_ORDER rồi phát ORDER_PAID"
label: pay_order_command
input:
  messageFrom: orders.commands
  messageBody:
    commandId: CMD-TEST-0001
    commandType: PAY_ORDER
    orderId: ORD-TEST-1001
  messageHeaders:
    correlationId: CORR-TEST-0001
outputMessage:
  sentTo: orders.events
  body:
    eventId: EVT-TEST-0001
    eventType: ORDER_PAID
    orderId: ORD-TEST-1001
  headers:
    correlationId: CORR-TEST-0001
~~~

Chính xác cách adapter sử dụng `messageFrom` và `sentTo` cần được cấu hình. Không có bảo đảm rằng chỉ cần viết tên địa chỉ vào YAML là Spring Cloud Contract sẽ tự tạo Kafka topic, JMS queue, Spring Integration channel hoặc Spring Cloud Stream binding tương ứng.

## 5. Sơ đồ thời gian: test phát lệnh và bắt sự kiện

~~~mermaid
sequenceDiagram
    participant T as Generated producer test
    participant M as Message verifier/adapter
    participant P as Order Service
    participant B as Messaging infrastructure
    T->>M: Gửi PAY_ORDER đến orders.commands
    M->>B: Đưa message vào kênh nguồn được cấu hình
    B->>P: Giao command cho listener/handler
    P->>P: Xử lý đơn ORD-TEST-1001
    P->>B: Phát ORDER_PAID đến orders.events
    B->>M: Cung cấp output message cho verifier
    M-->>T: Body + headers + destination
    T->>T: Kiểm chứng các cam kết của contract
~~~

Sơ đồ thể hiện **luồng cần được cấu hình**, không có nghĩa mọi plugin đều dùng một broker thật. Có dự án dùng binder/test channel hoặc message verifier riêng; có dự án chạy broker test container. Cơ chế nào được chọn sẽ quyết định producer test bao phủ đến đâu.

**Không cần cố dựng một broker production để làm contract test** nếu mục tiêu là kiểm tra nội dung event và logic phát event. Nhưng nếu tên topic, routing, serializer, partition key hoặc broker configuration là một phần tương thích quan trọng, phải có những test tích hợp thích hợp xác minh các yếu tố đó.

## 6. Địa chỉ gửi/nhận là logic hay vật lý?

`messageFrom("orders.commands")` và `sentTo("orders.events")` chứa chuỗi định danh địa chỉ. Tuy nhiên, **ý nghĩa của chuỗi phụ thuộc hệ thống messaging và tích hợp Spring Cloud Contract**.

| Bối cảnh | Địa chỉ có thể đại diện cho | Điều phải xác minh |
| --- | --- | --- |
| Spring Integration | Tên channel | Channel bean có tồn tại; test adapter gửi/nhận đúng channel |
| Spring Cloud Stream | Binding hoặc destination theo cấu hình ứng dụng | Binding được map tới destination thực tế; binder test phù hợp |
| Kafka | Topic hoặc logical destination do adapter quy định | Producer gửi tới topic đúng, serializer/headers/key được giữ |
| RabbitMQ/AMQP | Queue/exchange/routing key theo cấu hình cụ thể | Đường route exchange–queue và routing metadata |
| JMS | Queue/topic hoặc tên destination được adapter hỗ trợ | Loại destination và cách chuyển message |
| Test double | Kênh/bộ đệm trong bộ giả lập | Kết quả test chỉ có giá trị trong phạm vi fake đang dùng |

Ví dụ, một ứng dụng có thể dùng **binding name** `orderPaid-out-0` trong cấu hình nhưng broker thực nhận tại topic `orders.events.v2`. Nếu contract viết `sentTo("orderPaid-out-0")`, cần biết adapter đang đối chiếu **binding name** hay **physical destination**.

**Tránh giả định:** “đổi tên trong `sentTo` tức là đổi tên topic ở broker”. Một thay đổi text trong contract chỉ đổi điều kiện kiểm chứng theo cách công cụ hiểu; hạ tầng triển khai vẫn cần cấu hình tương ứng.

### Tên đích thay đổi có thể là breaking change

Nếu consumer đang subscribe `orders.events` mà producer bắt đầu publish sang `orders.events.v2`, consumer cũ có thể **không nhận được event nào**, dù JSON payload giữ nguyên.

Để phát hành an toàn, nhóm có thể:

1. Hỗ trợ song song destination cũ và mới trong giai đoạn chuyển tiếp.
2. Cập nhật và kiểm thử consumer đang sử dụng destination cũ.
3. Công bố phiên bản, cơ chế subscribe và lịch ngừng hỗ trợ.
4. Chạy kiểm thử routing thực tế ở môi trường phù hợp nếu đường route thuộc phạm vi cam kết.

Không đánh giá khả năng tương thích chỉ bằng nội dung `body`; **địa chỉ gửi, headers và phương thức phát** có thể quan trọng không kém.

## 7. Payload đầu vào khác payload đầu ra

Hai payload trong ví dụ `PAY_ORDER` → `ORDER_PAID` có ý nghĩa khác nhau:

~~~json
{
  "commandId": "CMD-TEST-0001",
  "commandType": "PAY_ORDER",
  "orderId": "ORD-TEST-1001"
}
~~~

Là **command input**: một bên yêu cầu Order Service làm việc gì đó.

~~~json
{
  "eventId": "EVT-TEST-0001",
  "eventType": "ORDER_PAID",
  "orderId": "ORD-TEST-1001"
}
~~~

Là **event output**: Order Service thông báo sự kiện đã xảy ra.

| Thuộc tính | Command input | Event output |
| --- | --- | --- |
| Vai trò | Kích hoạt xử lý | Công bố kết quả/hành vi đã xảy ra |
| Tên loại | `commandType` | `eventType` |
| Mã định danh | `commandId` | `eventId` |
| Dữ liệu liên kết | `orderId` | `orderId` |
| Địa chỉ | `messageFrom` | `sentTo` |
| Headers | `messageHeaders` | `headers` |

Một contract tốt chỉ khai báo những trường consumer/producer thực sự thỏa thuận. Không bắt consumer nhận toàn bộ entity nội bộ của producer, đồng thời không loại bỏ các trường mà consumer phụ thuộc như `eventType`, `orderId` hoặc correlation ID nếu chúng là cam kết.

## 8. Headers và thông tin định tuyến

Trong hệ thống messaging, headers có thể chứa:

- `contentType` hoặc metadata về serialization.
- `eventType`, `schemaVersion` giúp consumer chọn cách đọc payload.
- `correlationId` giúp liên kết command và event.
- `tenantId` khi xử lý theo tenant (cần dữ liệu test an toàn).
- Metadata kỹ thuật như partition key, trace ID hoặc routing information.

Không phải mọi metadata broker đều là **header ứng dụng**. Chẳng hạn Kafka record key, routing key trong RabbitMQ hoặc một số thuộc tính native của JMS có cách biểu diễn và đường truyền riêng. **Viết một trường `headers` trong contract không tự chứng minh mọi metadata vật lý đó được mapping đúng**; nếu consumer phụ thuộc, cần kiểm tra qua adapter hoặc integration test phù hợp.

### Ví dụ correlation ID xuyên hai chiều

~~~text
PAY_ORDER gửi vào orders.commands
  header correlationId = CORR-TEST-0001
  body orderId = ORD-TEST-1001
                  |
                  v
ORDER_PAID gửi ra orders.events
  header correlationId = CORR-TEST-0001
  body orderId = ORD-TEST-1001
~~~

Việc dùng cùng correlation ID là một **yêu cầu nghiệp vụ/giao thức** nếu các bên đã thống nhất; không phải điều Spring Cloud Contract tự động tạo. Trong test, fixture cần chuẩn bị dữ liệu để producer thực sự bảo toàn hoặc ánh xạ correlation ID đúng.

Một matcher chỉ kiểm tra correlation ID có kiểu string chưa chứng minh **bằng nhau giữa input và output**. Nếu tính nhất quán giữa hai message là cam kết, cần assertion/fixture hoặc cơ chế DSL phù hợp để xác minh quan hệ đó.

## 9. Message verifier và base test class

Đối với HTTP, generated test gửi một request rồi assert response. Với thông điệp, generated test phải có cơ chế **đưa message vào hoặc kích hoạt producer**, đồng thời **thu nhận message được phát**. Công việc này phụ thuộc vào tích hợp messaging và cấu hình **MessageVerifier** hoặc adapter tương đương.

Ví dụ lớp nền có phương thức kích hoạt ở producer:

~~~java
// Phác thảo: phụ thuộc ứng dụng và cấu hình test,
// không phải một base class chạy độc lập.
public abstract class OrderMessagingContractBase {

    @Autowired
    private OrderApplicationService orderService;

    public void markTestOrderAsPaid() {
        orderService.confirmPayment("ORD-TEST-1001");
    }
}
~~~

Lớp thực tế còn cần Spring test context, fixture, message verifier/binder, phương thức chờ output và dọn state sau test. Phương thức `markTestOrderAsPaid()` cần kích hoạt **logic phát event của producer**, không chỉ gửi trực tiếp một message đã được chép từ contract để tự làm test PASS.

### Hai chiến lược kiểm chứng khác nhau

| Chiến lược | Cách hoạt động | Phạm vi bằng chứng |
| --- | --- | --- |
| **Test messaging trong tiến trình** | Dùng channel/test binder/message verifier; gọi handler/service thực | Kiểm tra payload, headers và logic publish trong phạm vi binder giả lập |
| **Integration test với broker thật trong môi trường test** | Producer phát/nhận qua Kafka/JMS/AMQP test container hoặc broker được quản lý | Có thể bao phủ serializer, routing và một phần cấu hình hạ tầng |

Không cần lúc nào cũng dùng broker thật, nhưng **phải biết mình đang kiểm tra loại địa chỉ nào**. Một test qua in-memory channel PASS chưa chứng minh production đã cấu hình đúng Kafka topic hoặc RabbitMQ routing key.

Với message bất đồng bộ, test phải **đợi theo điều kiện có timeout hữu hạn** và dọn message/queue giữa các kịch bản. Dùng `Thread.sleep(1000)` cứng thường tạo flaky tests: máy nhanh thì thừa, CI tải cao thì vẫn không đủ.

## 10. label không đồng nghĩa với sentTo

Hãy đặt cạnh nhau:

~~~groovy
label "order_paid"

outputMessage {
    sentTo("orders.events")
    body(eventType: "ORDER_PAID", orderId: "ORD-TEST-1001")
}
~~~

- `order_paid` là **nhãn hợp đồng**, giúp con người nhận biết kịch bản và hỗ trợ kích hoạt stub theo nhãn trong những chế độ Stub Runner messaging.
- `orders.events` là **destination** để phát thông điệp.
- `ORDER_PAID` là **loại event trong payload**.

Đây là **ba khái niệm riêng biệt**. Việc đổi label không nhất thiết đổi nơi publish hoặc loại event. Ngược lại, đổi `sentTo` có thể phá vỡ subscriber dù label vẫn giữ nguyên.

### Consumer dùng Stub Runner để thử nhận event

Một consumer đang xử lý `ORDER_PAID` có thể dùng stub được producer phát hành để tạo message mẫu. Trong các cấu hình hỗ trợ trigger theo nhãn, consumer test có thể gọi cơ chế **StubTrigger** của Stub Runner:

~~~java
// Phác thảo consumer test trong môi trường đã cấu hình
// Stub Runner và messaging integration phù hợp.
@Autowired
StubTrigger stubTrigger;

@Test
void shouldHandleOrderPaidEvent() {
    stubTrigger.trigger("order_paid");

    // Chờ handler của consumer xử lý event.
    // Assert đơn hàng được đưa vào bước giao vận,
    // hoặc trạng thái consumer thay đổi như mong đợi.
}
~~~

Việc khởi tạo Stub Runner, các broker/binder, version artifact và cách test chờ consumer xử lý không được thể hiện trong khung trên; chúng phải được cấu hình theo công cụ và phiên bản thực tế. **Không phải mọi message contract tự động cho phép trigger theo label trong mọi adapter**.

Stub trigger **không gọi `markTestOrderAsPaid()` của producer**. Consumer nhận một event mô phỏng phù hợp với stub artifact. Producer test riêng mới xác minh logic producer thật phát event theo contract.

## 11. Các hướng tương tác consumer–producer cần kiểm tra riêng

Với event-driven architecture, có ít nhất hai góc nhìn kiểm thử:

### Producer là bên phát event

~~~text
Order Service (producer) --ORDER_PAID--> Shipping Service (consumer)
~~~

Một hợp đồng có `input.triggeredBy` và `outputMessage.sentTo` giúp xác minh producer phát event. Stub của event giúp Shipping Service test phần xử lý message mà không cần Order Service chạy thật.

### Producer là bên nhận command rồi phát event

~~~text
Checkout --PAY_ORDER--> Order Service --ORDER_PAID--> Shipping Service
~~~

Hợp đồng có `input.messageFrom` và `outputMessage.sentTo` mô tả luồng từ command đến event. Nó có thể giúp producer test gửi command thử nghiệm và quan sát event được phát. Tuy nhiên:

- Checkout còn cần biết command nó tạo có đúng schema hay không.
- Shipping Service cần biết event nó nhận có đúng schema hay không.
- Một test message-flow của Order Service **không tự xác minh tất cả consumer**.
- Nếu nhiều producer hoặc nhiều subscriber chia sẻ destination, cần xác định rõ ai sở hữu hợp đồng nào.

Tùy kiến trúc, có thể cần **hợp đồng riêng cho command và event** hoặc nhiều kịch bản để kiểm chứng đầy đủ các hướng tích hợp. Đừng giả định một file contract duy nhất thay thế toàn bộ contract testing trong hệ thống.

## 12. Định dạng payload, schema và giá trị động

Trong ví dụ `ORDER_PAID`, payload dạng JSON map:

~~~json
{
  "eventId": "EVT-TEST-0001",
  "eventType": "ORDER_PAID",
  "orderId": "ORD-TEST-1001",
  "paidAmount": 150000
}
~~~

Đặc tả có thể cần cam kết:

1. **Kiểu JSON:** `paidAmount` là number, `orderId` là string.
2. **Trường bắt buộc:** `eventType` và `orderId` có luôn tồn tại hay không?
3. **Enum:** `ORDER_PAID` có phải tên chính thức của loại event?
4. **ID động:** `eventId` được tạo mới theo định dạng nào?
5. **Version:** payload có `schemaVersion` hoặc header version không?
6. **Địa chỉ:** event phát đến đúng destination subscriber đang dùng không?

Nếu event ID do producer sinh động, có thể dùng matcher hoặc fixture test kiểm soát ID. Không dùng `UUID.randomUUID()` trong script Groovy để tự tạo expected body ở mỗi lần build; cùng commit hợp đồng có thể sinh output khác nhau.

### Thông điệp không nhất thiết luôn là JSON

Kafka/JMS/AMQP có thể truyền chuỗi, byte array, JSON, Avro, Protobuf hoặc format riêng. Nếu message thực được serialize thành byte, test cần hiểu **schema/serializer/content type**. Một contract diễn đạt body dưới dạng map không tự chứng minh format trên wire là JSON đúng như consumer đang giải mã.

Khi consumer phụ thuộc schema registry, schema ID hoặc compatibility mode, cần thêm kiểm tra schema và test tích hợp serializer/deserializer tương ứng. Contract testing ở cấp payload vẫn có ích nhưng **không thay thế** bảo đảm của tầng serialization.

## 13. Không suy diễn các bảo đảm từ một event mẫu

Một hợp đồng `PAY_ORDER` → `ORDER_PAID` PASS thường chứng minh **một kịch bản đầu vào đã kích hoạt output theo cấu trúc mong đợi**. Nó **không tự chứng minh**:

| Thuộc tính | Vì sao không được chứng minh chỉ bằng một contract? |
| --- | --- |
| **At-least-once/exactly-once** | Cần kiểm tra cách broker, producer và consumer xử lý retry/ack/transaction |
| **Idempotency** | Cần thử command trùng lặp hoặc event bị phát lại |
| **Ordering** | Một event đơn lẻ không kiểm tra thứ tự nhiều event/partition |
| **No duplicate** | Cần tạo điều kiện phát lặp, crash/retry và so sánh |
| **Delivery guarantee** | Stub có thể bỏ qua broker/network thực |
| **Retention/DLQ** | Phụ thuộc cấu hình broker và chính sách xử lý lỗi |
| **Performance** | Không có bằng chứng về throughput/latency hoặc backpressure |
| **Authorization** | Phân quyền publish/subscribe thuộc lớp bảo mật và broker setup |

Do đó, khi một consumer cần xử lý event lặp hoặc mất thứ tự, hãy bổ sung **integration tests hoặc behavioral tests** phù hợp. Đừng mở rộng ý nghĩa kết quả Contract Verifier PASS quá phạm vi được thiết kế.

## 14. Message contract khi producer xử lý lỗi

Giả sử `PAY_ORDER` tham chiếu đơn không tồn tại. Producer có thể:

- Không phát `ORDER_PAID`, ghi log và từ chối command.
- Phát một event `ORDER_PAYMENT_REJECTED` có schema riêng.
- Đưa message vào error channel hoặc dead-letter queue sau khi retry.

**Không thể lấy contract thành công và suy ra hành vi lỗi.** Nếu consumer phụ thuộc event từ chối, cần khai báo kịch bản riêng với input và output kỳ vọng tương ứng.

Ví dụ **YAML DSL minh họa** cho trường hợp producer phát event từ chối:

~~~yaml
description: "Từ chối thanh toán đơn không tồn tại"
label: payment_rejected
input:
  messageFrom: orders.commands
  messageBody:
    commandType: PAY_ORDER
    orderId: ORD-TEST-NOT-FOUND
outputMessage:
  sentTo: orders.events
  body:
    eventType: ORDER_PAYMENT_REJECTED
    orderId: ORD-TEST-NOT-FOUND
    reason: ORDER_NOT_FOUND
~~~

Đây là **quy ước nghiệp vụ giả định** để học cách thiết kế hợp đồng. Tên event và mã `ORDER_NOT_FOUND` chỉ hợp lệ nếu producer/consumer thực tế đã đồng ý. Nếu hệ thống có quy tắc **không được phát message**, cần chọn chiến lược test assertion phù hợp; không mặc định một `outputMessage` trống là cách chứng minh absence.

Với retry hoặc DLQ, thường cần kiểm thử tích hợp riêng để xác minh các trạng thái broker và timer. Test message contract chủ yếu mô tả thông điệp quan sát được, không tự mô phỏng mọi biến cố của hạ tầng.

## 15. Các lỗi thường gặp khi viết input và outputMessage

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Generated test không tìm thấy phương thức kích hoạt | `triggeredBy` gọi method không tồn tại ở base test | Khai báo method, cấu hình đúng base class, kiểm tra generated test |
| Test không nhận message output | Producer chưa phát, verifier lắng nghe sai đích, hoặc async timeout | Xác minh routing, binder, fixture và cơ chế chờ |
| Dùng `sentTo` như nguồn đầu vào | Nhầm producer nhận và producer phát | Dùng `messageFrom` cho input, `sentTo` cho output |
| Dùng `label` làm topic broker | Nhầm nhãn kịch bản với destination | Phân biệt label, eventType và sentTo |
| Broker thật không có destination mong đợi | Tên logical binding khác physical destination | Kiểm tra mapping adapter/binder và config triển khai |
| Contract test PASS nhưng event không tới subscriber | Test dùng in-memory channel và không kiểm tra broker routing | Thêm integration test với messaging stack phù hợp |
| Header correlation ID bị mất | Publisher hoặc adapter không forward header | Kiểm tra contract và serialization/header mapping thực tế |
| JSON body đúng nhưng consumer không giải mã được | Sai content type, serializer, schema hoặc encoding | Kiểm tra wire format và consumer deserializer |
| Stub trigger không phát event | Chưa cấu hình messaging integration hoặc label không đúng | Kiểm tra version stub, label, Stub Runner setup |
| Test chập chờn vì timeout | Bất đồng bộ, dữ liệu chung hoặc dùng sleep cố định | Cách ly state, chờ theo điều kiện và timeout hữu hạn |
| Consumer CI PASS với stub cũ | Không khóa version/revision | Phát hành stub mới và chạy consumer với artifact đúng |

Với các lỗi message-based, nên kiểm tra theo thứ tự: **hợp đồng được phát hiện** → **generated test chạy** → **input kích hoạt đúng handler** → **output thật xuất hiện đúng destination** → **matcher kiểm tra body/headers** → **stub artifact và consumer tests dùng đúng version**.

## 16. Kiểm thử và phát hành message stub trong CI

~~~mermaid
flowchart TD
    A["Hợp đồng Groovy/YAML được review"] --> B["Verifier nạp và sinh producer tests"]
    B --> C["Base test cấu hình messaging verifier/adapter"]
    C --> D["Kích hoạt input hoặc gửi command"]
    D --> E{"Thu được output đúng destination?"}
    E -->|Không| X["BLOCK"]
    E -->|Có| F["Kiểm tra body/headers/event type"]
    F --> G{"Generated tests PASS và không skip?"}
    G -->|Không| X
    G -->|Có| H["Đóng gói stub có version cố định"]
    H --> I["Consumer tải qua Stub Runner"]
    I --> J["Kích hoạt stub message và assert consumer"]
    J --> K{"Consumer tests PASS?"}
    K -->|Không| X
    K -->|Có| L["Lưu bằng chứng và xem phạm vi tương thích"]
~~~

Những điểm CI cần bảo đảm:

1. **Nguồn đúng:** tệp Groovy/YAML được phát hiện, không bị bộ lọc hoặc đổi thư mục làm bỏ qua.
2. **Producer test thật sự chạy:** không chỉ sinh mã rồi đánh dấu build xanh.
3. **Messaging infrastructure đúng:** producer test có adapter và fixture để gửi input/thu output.
4. **Không rò rỉ dữ liệu production:** payload, headers, log và stub dùng dữ liệu tổng hợp; không đặt token thật trong message mẫu.
5. **Stub có provenance:** artifact được tạo từ đúng revision hợp đồng và producer build đã test.
6. **Consumer kiểm thử đúng stub:** không dùng một bản phát hành cũ hoặc label/event chưa được đóng gói.
7. **Đủ phạm vi:** các producer/consumer/địa chỉ và nhánh lỗi quan trọng được kiểm tra trước rollout.

Một biên bản kết quả **do dự án tự thiết kế**:

~~~yaml
# Minh họa evidence record, không phải cấu hình mặc định SCC.
producer_revision: "order-service@abc123"
contract_revision: "message-contracts@def456"
message_contracts:
  - order_paid
  - pay_order_command
input_destinations:
  - orders.commands
output_destinations:
  - orders.events
producer_message_tests: PASS
stub_artifact: "com.example:order-service:2.4.0:stubs"
consumer_version: "shipping-service:1.9.0"
consumer_stub_tests: PASS
coverage_note: "Không bao phủ retry, ordering hay broker failover"
~~~

Các giá trị ở đây chỉ minh họa cách truy vết. Không phải bằng chứng một pipeline thực đã chạy. Khi kiểm thử nhiều message adapters, nên ghi rõ dùng in-memory binder hay broker test container để tránh hiểu quá phạm vi của báo cáo.

## 17. Thực hành có hướng dẫn

### Bài tập A — Xác định hướng vào/ra

Order Service nhận `RESERVE_STOCK` tại `inventory.commands` và phát `STOCK_RESERVED` tại `inventory.events`.

**Yêu cầu:** chọn `messageFrom` và `sentTo` đúng chỗ, nêu thông điệp nào thuộc `messageBody` và thông điệp nào thuộc `outputMessage.body`.

**Gợi ý:** `input.messageFrom("inventory.commands")` chỉ nguồn nhận command; `outputMessage.sentTo("inventory.events")` chỉ đích phát event. Payload tương ứng nằm ở input và output khác nhau.

### Bài tập B — triggeredBy hay messageFrom?

Producer có phương thức `completePayment("ORD-TEST-1001")`. Hãy thiết kế một hợp đồng kiểm tra event `ORDER_PAID` mà **không cần gửi command qua broker**.

**Yêu cầu:** dùng `input.triggeredBy(...)`, `outputMessage.sentTo(...)`, body và label. Giải thích phương thức sẽ chạy ở đâu.

**Gợi ý:** base test định nghĩa phương thức không đối số do `triggeredBy` tham chiếu, trong đó gọi service cần kiểm tra. Stub của consumer dùng nhãn để kích hoạt output mô phỏng chứ không gọi method ở producer.

### Bài tập C — Phân biệt ba tên

Một contract có `label "order_paid"`, `sentTo("orders.events")`, body chứa `eventType: "ORDER_PAID"`. Một thành viên đề xuất đổi label thành `orders.events` vì “label là topic”.

**Yêu cầu:** giải thích sai lầm và xác định phần nào thay đổi khi rename từng giá trị.

**Gợi ý:** label là nhãn kịch bản/stub trigger; sentTo là destination; eventType là trường payload. Ba giá trị có vai trò độc lập.

### Bài tập D — Correlation ID

Command có header `correlationId = CORR-TEST-0001`. Event ra có body đúng nhưng thiếu header correlationId, trong khi Shipping Service cần nó để liên kết giao dịch.

**Yêu cầu:** bổ sung contract và thiết kế fixture/producer assertion để kiểm tra header được chuyển đúng. Nêu vì sao matcher theo kiểu string chưa chứng minh hai giá trị input/output bằng nhau.

**Gợi ý:** khai báo messageHeaders ở input và headers ở output, dùng dữ liệu mẫu nhất quán; nếu consumer yêu cầu quan hệ động, cần assertion/logic kiểm thử phù hợp.

### Bài tập E — Broker config bị sai

Producer test sử dụng in-memory channel PASS với `sentTo("orders.events")`; production lại publish sang một Kafka topic khác. Shipping Service không nhận event.

**Yêu cầu:** xác định khoảng trống bằng chứng và đề xuất bổ sung một integration test.

**Gợi ý:** kiểm tra cấu hình binding → Kafka topic, serializer và headers qua môi trường broker test; đừng kết luận broker routing được xác minh chỉ bằng hợp đồng payload.

### Bài tập F — CI PASS nhưng chưa tương thích

Producer test PASS, consumer Stub Runner PASS; tuy nhiên Shipping Service dùng stub version cũ, trong khi bản producer mới đổi destination và thêm trường bắt buộc.

**Yêu cầu:** nêu các bước cần thực hiện trước khi phát hành và cách liên kết bằng chứng hai phía.

**Gợi ý:** khóa contract revision, producer build, stub artifact; chạy lại consumer tests với stub mới; đánh giá thay đổi destination/schema với những subscriber đang hoạt động và lên kế hoạch rollout tương thích.

## 18. Checklist khi hoàn thiện hợp đồng thông điệp

- [ ] Đã xác định rõ **producer đang được kiểm chứng** và hướng input/output theo góc nhìn producer.
- [ ] Mỗi kịch bản chọn cách kích hoạt phù hợp: `triggeredBy` hoặc `messageFrom`.
- [ ] Nếu dùng `messageFrom`, `messageBody` và `messageHeaders` mô tả đúng thông điệp đầu vào.
- [ ] Nếu dùng `triggeredBy`, base test có method được tham chiếu và nó kích hoạt hành vi producer thật.
- [ ] `outputMessage.sentTo` là đúng địa chỉ theo quy ước của adapter/binder đang dùng.
- [ ] `outputMessage.body` và `headers` thể hiện dữ liệu consumer thực sự cần.
- [ ] Không nhầm `label`, destination và `eventType`.
- [ ] Đã xác minh binding/logical destination với broker/physical destination khi điều đó thuộc phạm vi cam kết.
- [ ] Serialization, schema, content type và metadata cần thiết đã được kiểm tra.
- [ ] Dữ liệu hợp đồng, fixture và stub không chứa thông tin production nhạy cảm.
- [ ] Producer tests thực sự gửi/kích hoạt input và quan sát output, không chỉ mock kết quả cuối.
- [ ] Cơ chế đợi bất đồng bộ có timeout hữu hạn; dữ liệu, topic/queue được cách ly giữa test.
- [ ] Đã xem xét các kịch bản lỗi, và có test bổ sung cho retry/idempotency/ordering khi cần.
- [ ] Stub artifact được tạo từ đúng contract revision và producer build đã PASS.
- [ ] Consumer tests sử dụng Stub Runner đúng version và kiểm chứng logic xử lý message.
- [ ] CI ghi rõ phạm vi bằng chứng, không coi một message contract PASS là bảo đảm delivery/ordering toàn hệ thống.

**Ghi nhớ:** `input` là **điểm kích hoạt producer**, có thể đến từ phương thức test qua `triggeredBy` hoặc thông điệp nhận qua `messageFrom`; `outputMessage` là **điều producer phải phát**, gồm `sentTo`, body và headers. Hiểu chính xác **hướng dữ liệu và ý nghĩa của destination** là điều kiện để Spring Cloud Contract sinh producer tests, stub và CI có ích trong phát hiện thay đổi tương thích của hệ thống message-driven.
