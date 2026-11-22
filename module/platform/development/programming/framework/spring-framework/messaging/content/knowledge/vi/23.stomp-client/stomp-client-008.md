# Receipt callback, thời gian chờ và giới hạn của simple broker

Khi dùng STOMP, client có thể yêu cầu server xác nhận rằng một frame đã được xử lý bằng header **receipt**. Server trả về frame **RECEIPT** với header **receipt-id** tương ứng. Spring cung cấp callback để ứng dụng biết receipt đã về hay đã hết thời gian chờ.

Receipt hữu ích khi cần biết một lệnh **SUBSCRIBE** đã được broker xử lý trước khi client tiếp tục gửi message, hoặc khi cần xác nhận broker đã tiếp nhận frame **SEND**. Tuy nhiên, receipt không chứng minh consumer đã nhận message hay hoàn tất nghiệp vụ. Spring simple broker không hỗ trợ receipt, vì vậy các callback này chỉ hoạt động khi server/broker thực sự hỗ trợ tính năng đó, thường là external broker qua STOMP broker relay.

## 1. Receipt trong giao thức STOMP

Một STOMP client có thể thêm header **receipt** vào frame client gửi, ngoại trừ **CONNECT**. Giá trị header là một mã do client chọn. Khi server xử lý thành công frame yêu cầu receipt, server gửi **RECEIPT** và đặt giá trị đó vào header **receipt-id**.

Ví dụ client yêu cầu receipt cho SUBSCRIBE:

~~~text
SUBSCRIBE
id:orders-subscription
destination:/topic/orders
receipt:orders-subscription-ready

^@
~~~

Nếu server hỗ trợ receipt và xử lý SUBSCRIBE thành công, response có dạng:

~~~text
RECEIPT
receipt-id:orders-subscription-ready

^@
~~~

Client so sánh **receipt-id** với mã đã gửi để xác định operation nào được xác nhận. Khi có nhiều SEND hoặc SUBSCRIBE đang chờ cùng lúc, mỗi operation nên dùng một receipt ID duy nhất trong phạm vi kết nối.

Receipt cũng có thể được yêu cầu cho SEND:

~~~text
SEND
destination:/queue/orders
receipt:order-send-42
content-type:text/plain

create-order-42
^@
~~~

Server trả về **RECEIPT** khi frame SEND đã được xử lý theo semantics của server/broker. Điều đó không có nghĩa là một consumer đã nhận message, đã chạy code xử lý hoặc đã commit transaction nghiệp vụ.

## 2. Receipt xác nhận điều gì?

Theo STOMP 1.2, RECEIPT xác nhận server đã xử lý frame client tương ứng. Vì STOMP truyền frame theo một luồng có thứ tự, receipt còn là xác nhận cộng dồn rằng các frame đứng trước đã được server nhận. Tuy nhiên, những frame trước đó có thể chưa được xử lý hoàn tất.

Cần phân biệt ba tín hiệu:

| Tín hiệu | Ý nghĩa | Không chứng minh |
| --- | --- | --- |
| **RECEIPT** | Server đã xử lý frame yêu cầu receipt, ví dụ SEND hoặc SUBSCRIBE | Consumer đã nhận message hoặc hoàn thành nghiệp vụ |
| **ACK** | Consumer xác nhận đã tiêu thụ một MESSAGE trong subscription dùng chế độ ACK tường minh | Một operation SEND bất kỳ đã được broker xử lý |
| **ERROR** | Server báo lỗi khi xử lý frame hoặc giao thức | Operation đã thành công |

Nếu yêu cầu là biết subscription đã được broker đăng ký trước khi publish, receipt cho SUBSCRIBE là tín hiệu phù hợp khi broker hỗ trợ. Nếu yêu cầu là biết người nhận đã xử lý đơn hàng, hãy thiết kế response nghiệp vụ riêng, ví dụ event có **correlationId** hoặc một message phản hồi sau khi service hoàn thành. Không dùng RECEIPT thay cho xác nhận nghiệp vụ.

## 3. Vì sao receipt quan trọng với SUBSCRIBE?

Một tình huống phổ biến là client kết nối, subscribe vào **/topic/orders**, rồi ngay lập tức gửi một request khiến server phát message tới topic đó. Nếu subscription chưa được broker xử lý xong trước khi message được phát, client có thể bỏ lỡ message đầu tiên.

Với broker hỗ trợ receipt, client có thể:

1. Gửi SUBSCRIBE kèm receipt ID.
2. Chờ RECEIPT có receipt-id khớp.
3. Chỉ sau callback thành công mới gửi request cần nhận broadcast.

Đây là cách đồng bộ theo xác nhận của broker thay vì chờ một khoảng thời gian đoán trước. **setTimeout(..., 500)** hoặc **Thread.sleep(500)** không chứng minh subscription đã sẵn sàng; thời gian xử lý có thể thay đổi theo tải và network.

Receipt của SUBSCRIBE xác nhận server đã xử lý frame đăng ký subscription. Nó không thay thế việc kiểm tra quyền subscribe, cũng không bảo đảm message nghiệp vụ tương lai sẽ luôn được giao nếu kết nối bị ngắt hoặc destination có semantics không lưu trữ.

## 4. Spring simple broker không hỗ trợ receipt

Spring có thể chạy simple broker trong bộ nhớ bằng **enableSimpleBroker("/topic", "/queue")**. Đây là lựa chọn tiện để bắt đầu, nhưng nó chỉ hỗ trợ một tập con các STOMP command. Simple broker không hỗ trợ **ACK**, **RECEIPT** và một số tính năng khác; nó cũng không phù hợp cho clustering.

Ví dụ cấu hình:

~~~java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");
    registry.enableSimpleBroker("/topic", "/queue");
}
~~~

Với cấu hình này, client có thể subscribe và nhận broadcast thông thường. Nhưng nếu client gửi SUBSCRIBE kèm receipt, simple broker không trả frame RECEIPT. Trong Spring Java STOMP client, operation sẽ hết thời gian chờ và callback **addReceiptLostTask** được gọi nếu TaskScheduler đã được cấu hình.

Điều đó không nhất thiết có nghĩa subscription bị từ chối. Có thể server đã xử lý subscription nhưng simple broker không hỗ trợ gửi receipt. Vì vậy, đừng dùng receipt timeout để kết luận rằng simple broker không tạo subscription.

Khi ứng dụng cần receipt, ACK/NACK hoặc khả năng broker độc lập, hãy cấu hình external STOMP broker như RabbitMQ hoặc ActiveMQ và bật **enableStompBrokerRelay(...)** cho các destination tương ứng. Cần kiểm tra tài liệu broker vì hỗ trợ và semantics cụ thể vẫn phụ thuộc sản phẩm.

## 5. Cấu hình Spring WebSocketStompClient

Spring cung cấp **WebSocketStompClient** để kết nối tới STOMP server qua WebSocket. Receipt tracking cần một **TaskScheduler** để đặt lịch hết hạn. Mặc định, receipt được xem là hết hạn sau **15.000 milliseconds (15 giây)** nếu chưa nhận được phản hồi.

Có thể khai báo scheduler và client thành Spring bean:

~~~java
package com.example.messaging;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.TaskScheduler;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;
import org.springframework.web.socket.client.standard.StandardWebSocketClient;
import org.springframework.web.socket.messaging.WebSocketStompClient;

@Configuration
public class StompClientConfiguration {

    @Bean
    public ThreadPoolTaskScheduler stompClientTaskScheduler() {
        ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(1);
        scheduler.setThreadNamePrefix("stomp-client-");
        return scheduler;
    }

    @Bean
    public WebSocketStompClient webSocketStompClient(
            TaskScheduler stompClientTaskScheduler) {

        WebSocketStompClient client =
                new WebSocketStompClient(new StandardWebSocketClient());

        client.setTaskScheduler(stompClientTaskScheduler);
        client.setReceiptTimeLimit(10_000);
        return client;
    }
}
~~~

Trong ví dụ, thời gian chờ được đặt thành 10 giây bằng **setReceiptTimeLimit(10_000)**. Nếu không gọi phương thức này, giá trị mặc định là 15 giây. Scheduler được Spring quản lý vòng đời; không cần tự gọi **initialize()** khi bean được tạo bởi container.

**setTaskScheduler(...)** cũng được dùng cho heartbeat của STOMP client. Riêng receipt tracking cần scheduler để chạy tác vụ timeout. Nếu không cấu hình scheduler, client không có cơ chế theo dõi thời gian receipt và có thể ném lỗi khi cố đăng ký receipt callback.

## 6. Dùng callback trong Spring Java STOMP client

Mỗi lần gọi **StompSession.send(...)** hoặc **StompSession.subscribe(...)** trả về một handle kiểu **StompSession.Receiptable** hoặc **StompSession.Subscription**. Handle cho phép đăng ký hai callback:

- **addReceiptTask(...)**: chạy khi server trả RECEIPT tương ứng.
- **addReceiptLostTask(...)**: chạy khi không nhận được RECEIPT trong thời gian đã cấu hình.

Có thể bật receipt tự động cho các thao tác send và subscribe tiếp theo:

~~~java
session.setAutoReceipt(true);
~~~

Sau đó đăng ký callback trên handle trả về:

~~~java
StompSession.Subscription subscription = session.subscribe(
        "/topic/orders",
        new StompFrameHandler() {
            @Override
            public Type getPayloadType(StompHeaders headers) {
                return String.class;
            }

            @Override
            public void handleFrame(StompHeaders headers, Object payload) {
                System.out.println("Order event: " + payload);
            }
        });

subscription.addReceiptTask(() ->
        System.out.println("Broker processed the SUBSCRIBE frame"));

subscription.addReceiptLostTask(() ->
        System.err.println("No SUBSCRIBE receipt before timeout"));
~~~

Tương tự, khi gửi message:

~~~java
StompSession.Receiptable send = session.send(
        "/topic/order-events",
        "order-created");

send.addReceiptTask(() ->
        System.out.println("Broker processed the SEND frame"));

send.addReceiptLostTask(() ->
        System.err.println("No SEND receipt before timeout"));
~~~

Hai ví dụ trên giả định STOMP server/broker có hỗ trợ receipt. Nếu dùng Spring simple broker, callback thành công sẽ không được gọi vì broker không gửi RECEIPT; sau thời gian cấu hình, callback hết hạn sẽ được gọi.

### 6.1. Chỉ yêu cầu receipt cho operation cần thiết

**setAutoReceipt(true)** tự thêm receipt header vào mọi thao tác **send** và **subscribe** tiếp theo của session. Cách này tiện khi hầu hết thao tác đều cần theo dõi, nhưng có thể tạo thêm nhiều receipt và timer không cần thiết.

Nếu chỉ cần receipt cho một SUBSCRIBE hoặc SEND cụ thể, hãy thêm header thủ công. Ví dụ:

~~~java
StompHeaders headers = new StompHeaders();
headers.setDestination("/topic/orders");
headers.setId("orders-subscription");
headers.setReceipt("orders-subscription-ready");

StompSession.Subscription subscription = session.subscribe(
        headers,
        new StompFrameHandler() {
            @Override
            public Type getPayloadType(StompHeaders headers) {
                return String.class;
            }

            @Override
            public void handleFrame(StompHeaders headers, Object payload) {
                System.out.println(payload);
            }
        });

subscription.addReceiptTask(() ->
        System.out.println("Orders subscription is registered"));

subscription.addReceiptLostTask(() ->
        System.err.println("Orders subscription receipt timed out"));
~~~

Với SEND, dùng overload **send(StompHeaders, Object)**:

~~~java
StompHeaders sendHeaders = new StompHeaders();
sendHeaders.setDestination("/topic/order-events");
sendHeaders.setReceipt("order-event-42");

StompSession.Receiptable receipt = session.send(
        sendHeaders,
        "order-created");

receipt.addReceiptTask(() ->
        System.out.println("Order event accepted by broker"));

receipt.addReceiptLostTask(() ->
        System.err.println("No broker receipt for order event"));
~~~

Chỉ gọi **addReceiptTask** hoặc **addReceiptLostTask** khi operation thực sự có receipt header. Nếu không bật auto receipt và cũng không đặt header thủ công, handle không có receipt ID và Spring có thể ném **IllegalArgumentException** khi đăng ký callback.

## 7. Callback và lỗi trong StompSessionHandler

Receipt timeout là một sự kiện riêng. Khi broker gửi **ERROR**, client cần xử lý ERROR frame. Khi WebSocket/TCP bị ngắt hoặc xảy ra lỗi transport, cần xử lý callback transport.

**StompSessionHandlerAdapter** là adapter phù hợp để nhận các sự kiện này. Ví dụ:

~~~java
StompSessionHandlerAdapter handler = new StompSessionHandlerAdapter() {

    @Override
    public void afterConnected(
            StompSession session,
            StompHeaders connectedHeaders) {

        session.setAutoReceipt(true);

        StompSession.Subscription subscription = session.subscribe(
                "/topic/orders",
                new StompFrameHandler() {
                    @Override
                    public Type getPayloadType(StompHeaders headers) {
                        return String.class;
                    }

                    @Override
                    public void handleFrame(
                            StompHeaders headers,
                            Object payload) {
                        System.out.println("Received: " + payload);
                    }
                });

        subscription.addReceiptTask(() ->
                System.out.println("SUBSCRIBE confirmed"));

        subscription.addReceiptLostTask(() ->
                System.err.println("SUBSCRIBE receipt expired"));
    }

    @Override
    public void handleFrame(StompHeaders headers, Object payload) {
        System.err.println(
                "Broker ERROR: " + headers.getFirst("message")
                        + " - " + payload);
    }

    @Override
    public void handleTransportError(
            StompSession session,
            Throwable exception) {
        System.err.println("STOMP transport error: " + exception.getMessage());
    }
};
~~~

**afterConnected** chỉ chạy sau khi STOMP session đã nhận CONNECTED. **handleFrame** của adapter nhận ERROR frame; adapter mặc định dùng String làm kiểu payload cho ERROR. **handleTransportError** xử lý lỗi transport như mất kết nối hoặc lỗi đọc/ghi frame.

Không nên coi ba callback này là một trạng thái duy nhất:

- Receipt callback thành công: server đã xác nhận frame.
- Receipt lost callback: không nhận được receipt trước hạn.
- ERROR frame: server đã báo lỗi giao thức hoặc xử lý.
- Transport error: kết nối hoặc quá trình truyền frame gặp lỗi.

Nếu server gửi ERROR cho một frame có receipt header, STOMP cho phép ERROR mang **receipt-id** tương ứng để client liên hệ lỗi với operation gốc. Broker có thể đóng kết nối sau ERROR; hãy xử lý lỗi và reconnect theo vòng đời client.

## 8. Dùng receipt với @stomp/stompjs trong trình duyệt

Với JavaScript client **@stomp/stompjs**, API **watchForReceipt(receiptId, callback)** theo dõi RECEIPT có receipt-id tương ứng. Đăng ký callback trước khi gửi operation và truyền cùng receipt ID trong header.

Ví dụ chờ xác nhận subscription:

~~~javascript
const receiptId = "orders-sub-" + crypto.randomUUID();

const timeoutId = window.setTimeout(() => {
    console.warn("No SUBSCRIBE receipt within 15 seconds");
}, 15000);

client.watchForReceipt(receiptId, (frame) => {
    window.clearTimeout(timeoutId);
    console.log(
        "Subscription processed:",
        frame.headers["receipt-id"]
    );
});

client.subscribe(
    "/topic/orders",
    (message) => {
        console.log("Order event:", message.body);
    },
    {
        id: "orders-subscription",
        receipt: receiptId
    }
);
~~~

Ví dụ gửi message có receipt:

~~~javascript
const receiptId = "order-send-" + crypto.randomUUID();

const timeoutId = window.setTimeout(() => {
    console.warn("No SEND receipt within 15 seconds");
}, 15000);

client.watchForReceipt(receiptId, (frame) => {
    window.clearTimeout(timeoutId);
    console.log("Broker receipt:", frame.headers["receipt-id"]);
});

client.publish({
    destination: "/topic/order-events",
    headers: {
        receipt: receiptId,
        "content-type": "text/plain"
    },
    body: "order-created"
});
~~~

**watchForReceipt** cần được gọi khi client đã kết nối STOMP. Dùng receipt ID duy nhất cho từng operation đang chờ. Ví dụ dùng **crypto.randomUUID()** trong secure context của trình duyệt.

Timeout trong hai ví dụ JavaScript là timer do ứng dụng tự tạo; StompJS không tự biến timeout đó thành xác nhận thất bại từ broker. Khi timer chạy, operation vẫn có thể đã được broker xử lý hoặc receipt có thể đến muộn. Callback theo dõi receipt vẫn có thể nhận frame nếu frame về sau đó; ứng dụng nên quản lý trạng thái operation và dọn dẹp timer phù hợp.

Nếu server là Spring simple broker, StompJS cũng không nhận RECEIPT. Timer sẽ báo hết hạn sau 15 giây, nhưng điều đó không cho biết subscription đã được tạo hay chưa.

## 9. Thời gian chờ và cách chọn timeout

Với Spring Java client, **setReceiptTimeLimit(long)** nhận số milliseconds trước khi receipt được xem là hết hạn. Mặc định là 15.000 ms. Timeout nên đủ dài để chịu được độ trễ mạng, tải broker và thời gian xử lý thông thường, nhưng không quá dài khiến UI hoặc workflow chờ vô hạn.

Ví dụ:

~~~java
stompClient.setReceiptTimeLimit(8_000);
~~~

Giá trị 8 giây chỉ là ví dụ; hãy đo latency trong môi trường thực tế trước khi chọn timeout production. Một số yếu tố cần tính đến:

- Độ trễ từ trình duyệt tới Spring server.
- Độ trễ từ Spring relay tới broker.
- Tải của broker và số lượng subscription.
- Proxy, load balancer hoặc network có thể trì hoãn frame.
- Heartbeat và trạng thái reconnect của client.
- Broker có thực sự hỗ trợ receipt cho loại frame đó hay không.

Timeout không hủy frame đã gửi. Khi timeout xảy ra, client chỉ biết chưa nhận được xác nhận trong giới hạn thời gian. Broker có thể đã xử lý frame nhưng phản hồi bị mất hoặc bị trễ. Vì vậy, retry SEND có thể tạo message trùng.

Với thao tác không idempotent, hãy gắn **idempotency key** hoặc business request ID vào payload/header để server có thể phát hiện request lặp. Không tự động retry lệnh tạo thanh toán, tạo đơn hoặc thực hiện hành động không thể lặp an toàn chỉ vì receipt timeout.

## 10. Graceful disconnect bằng receipt

STOMP cho phép yêu cầu receipt trên frame **DISCONNECT**. Client có thể đợi xác nhận trước khi đóng socket để giảm nguy cơ đóng kết nối quá sớm khi các frame trước vẫn đang trên đường tới server.

Ví dụ theo STOMP 1.2:

~~~text
DISCONNECT
receipt:disconnect-77

^@
~~~

Server có thể trả:

~~~text
RECEIPT
receipt-id:disconnect-77

^@
~~~

Sau khi nhận receipt, client mới đóng socket. Tuy vậy, STOMP specification cũng lưu ý server có thể đóng socket nhanh tới mức client không nhận kịp RECEIPT của DISCONNECT. Nếu cần đảm bảo quy trình shutdown ở cấp ứng dụng, hãy thiết kế timeout và fallback rõ ràng.

API **StompSession.disconnect()** của Spring là thao tác disconnect tiện lợi và không trả về **Receiptable**. Nếu cần theo dõi receipt của DISCONNECT, cần dùng API/protocol path có thể gửi frame DISCONNECT kèm receipt và quan sát frame RECEIPT trước khi đóng transport; không giả định gọi disconnect() tự động tạo receipt callback.

## 11. Receipt và ACK/NACK khác nhau

Receipt và ACK/NACK thường bị nhầm vì đều là frame xác nhận, nhưng chúng áp dụng cho hai bước khác nhau.

**RECEIPT** xác nhận server đã xử lý một frame client yêu cầu xác nhận. Ví dụ, SUBSCRIBE được chấp nhận hoặc SEND được broker xử lý.

**ACK/NACK** liên quan đến một message đã được gửi tới consumer. Khi SUBSCRIBE dùng **ack:client** hoặc **ack:client-individual**, consumer gửi ACK sau khi xử lý message; nếu không xử lý được, có thể gửi NACK. Chế độ **ack:auto** không yêu cầu client gửi ACK tường minh.

~~~text
SUBSCRIBE
id:orders-consumer
destination:/queue/orders
ack:client-individual

^@

MESSAGE
subscription:orders-consumer
message-id:msg-42
destination:/queue/orders

order-42
^@

ACK
id:ack-42

^@
~~~

Trong STOMP 1.2, ACK dùng header **id** lấy từ header **ack** của MESSAGE frame. Thư viện client có thể cung cấp API riêng để ACK/NACK thay cho việc tự tạo frame.

Simple broker của Spring không hỗ trợ ACK, RECEIPT và một số command khác. Nếu cần delivery semantics dựa trên ACK/NACK, phải dùng broker hỗ trợ các tính năng đó và cấu hình subscription tương ứng. Receipt không làm message trở nên durable và không thay thế ACK.

## 12. Xử lý timeout an toàn

Khi receipt không về, nên ghi lại thông tin đủ để chẩn đoán:

- Receipt ID và STOMP command (SEND, SUBSCRIBE hoặc DISCONNECT).
- Destination và session ID nếu có.
- Thời điểm gửi, timeout đã cấu hình và thời điểm timeout.
- Trạng thái WebSocket/STOMP connection và heartbeat gần nhất.
- Broker loại nào, có bật STOMP receipt support không.
- Có ERROR frame hoặc transport error xảy ra trước timeout không.

Không ghi credentials hoặc nội dung payload nhạy cảm vào log. Receipt ID nên được đưa vào log cùng correlation ID để đối chiếu với broker log nếu cần.

Trước khi retry, phân loại tình huống:

1. Simple broker không hỗ trợ receipt: callback timeout là hành vi dự kiến. Dùng cơ chế xác nhận cấp ứng dụng hoặc external broker.
2. Broker hỗ trợ receipt nhưng connection đã đóng: xử lý transport error và reconnect; operation cũ có thể ở trạng thái chưa xác định.
3. Broker hỗ trợ receipt, connection còn sống nhưng response chậm: kiểm tra tải và điều chỉnh timeout dựa trên số liệu.
4. Broker gửi ERROR: xử lý lỗi theo frame và destination; không coi đó là timeout bình thường.
5. SEND có thể đã được broker xử lý nhưng receipt mất: dùng idempotency key trước khi retry để tránh message trùng.

## 13. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| **addReceiptTask** không được gọi | Server không gửi RECEIPT hoặc receipt ID không khớp | Kiểm tra receipt header, broker support và frame nhận được |
| **addReceiptLostTask** chạy sau 15 giây | Mặc định receipt timeout là 15 giây; có thể server không hỗ trợ receipt | Kiểm tra simple broker hay external broker relay |
| Spring ném lỗi khi đăng ký callback | Operation không có receipt header hoặc TaskScheduler chưa được cấu hình | Bật auto receipt hoặc đặt header thủ công; cấu hình scheduler trước khi connect |
| Subscription vẫn nhận message nhưng receipt timeout | Simple broker có thể đã xử lý subscription nhưng không hỗ trợ receipt | Không dùng timeout làm kết luận subscription thất bại |
| Client gửi request ngay sau SUBSCRIBE và bỏ lỡ event đầu | Broker chưa xử lý subscription trước khi publish | Với broker hỗ trợ receipt, đợi receipt SUBSCRIBE rồi mới gửi request |
| SEND receipt thành công nhưng người dùng không thấy kết quả | Receipt chỉ xác nhận server xử lý frame SEND | Kiểm tra routing, subscription, consumer và response nghiệp vụ |
| Retry sau timeout tạo message trùng | Frame đầu có thể đã được broker xử lý | Dùng idempotency key và deduplication ở server/consumer |
| ERROR frame đến thay cho RECEIPT | Broker từ chối frame hoặc phát hiện lỗi giao thức | Xử lý ERROR riêng, kiểm tra destination, quyền và header |

## 14. Kiểm thử receipt

Một integration test có giá trị nên chạy với broker STOMP thật nếu tính năng cần kiểm tra là receipt. Simple broker không thể chứng minh receipt hoạt động vì nó không hỗ trợ command này.

Các tình huống nên kiểm thử:

1. Kết nối thành công và đăng ký SUBSCRIBE có receipt; xác nhận callback thành công chạy đúng một lần.
2. Gửi SEND có receipt; xác nhận callback nhận receipt tương ứng.
3. Có hai operation đang chờ cùng lúc; xác nhận receipt ID không bị nhầm giữa hai callback.
4. Đặt timeout ngắn trong test; xác nhận callback lost chạy khi broker không trả receipt.
5. Dùng simple broker; xác nhận không có callback thành công và timeout được ghi nhận đúng.
6. Broker trả ERROR; xác nhận handler xử lý ERROR riêng.
7. Ngắt WebSocket khi đang chờ receipt; xác nhận transport error được xử lý và trạng thái operation trở thành chưa xác định.
8. Retry một SEND sau timeout; xác nhận idempotency key ngăn xử lý trùng.
9. Với SUBSCRIBE, đợi receipt trước khi kích hoạt bước publish tiếp theo và xác nhận client nhận event đầu tiên.

Trong test, dùng timeout ngắn để giảm thời gian chạy nhưng không đặt quá thấp tới mức test thất bại do scheduling hoặc CI chậm. Không dùng Thread.sleep làm bằng chứng receipt đã về; hãy chờ callback bằng latch, future hoặc cơ chế đồng bộ của test framework.

## 15. Tài liệu tham khảo

- [STOMP 1.2 Specification — Header receipt and RECEIPT frame](https://stomp.github.io/stomp-specification-1.2.html): quy tắc receipt, receipt-id, ý nghĩa xác nhận cộng dồn, ACK/NACK và DISCONNECT.
- [Spring Framework — STOMP Client](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/client.html): WebSocketStompClient, setAutoReceipt, Receiptable callback, TaskScheduler và thời gian chờ mặc định.
- [Spring Framework — External Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay.html): giới hạn của simple broker và cách chuyển sang broker relay.
- [StompSession Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/stomp/StompSession.html): API send, subscribe và setAutoReceipt.
- [StompSession.Receiptable Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/stomp/StompSession.Receiptable.html): receipt success và lost callbacks.
- [StompClientSupport Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/stomp/StompClientSupport.html): TaskScheduler và receiptTimeLimit.
- [@stomp/stompjs Client API](https://stomp-js.github.io/api-docs/latest/classes/Client.html): watchForReceipt và các callback phía trình duyệt.
