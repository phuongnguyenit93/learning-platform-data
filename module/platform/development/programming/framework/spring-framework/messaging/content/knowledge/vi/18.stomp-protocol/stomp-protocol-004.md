# DISCONNECT, RECEIPT và xác nhận thao tác giao thức STOMP

STOMP là giao thức message dạng frame chạy trên một kết nối hai chiều như TCP hoặc WebSocket. Khi client muốn đóng kết nối, chỉ đóng socket không bảo đảm server đã nhận những frame mà client vừa gửi. STOMP cung cấp **DISCONNECT** và **RECEIPT** để client yêu cầu đóng phiên có xác nhận ở mức giao thức.

Hai frame này có vai trò khác nhau:

- **DISCONNECT** báo cho server biết client muốn kết thúc STOMP session.
- **RECEIPT** là phản hồi của server cho một client frame đã yêu cầu receipt bằng header **receipt**.
- Với DISCONNECT, client gửi receipt token, chờ server trả **receipt-id** tương ứng rồi mới đóng transport.
- RECEIPT xác nhận server đã xử lý frame tương ứng ở mức giao thức. Nó không tự chứng minh consumer đã xử lý xong nghiệp vụ hoặc dữ liệu đã được lưu bền vững theo chính sách của broker.

Bài này tập trung vào STOMP 1.2 và cách Spring Framework hỗ trợ receipt qua WebSocket STOMP client.

## 1. Vị trí của DISCONNECT và RECEIPT trong STOMP

STOMP định nghĩa các frame client gửi lên server và các frame server gửi về client. Frame có command, headers, dòng trống ngăn cách headers với body và ký tự NULL kết thúc frame. DISCONNECT và RECEIPT không có body.

~~~text
Client                                      STOMP Server
  |                                               |
  | CONNECT                                       |
  |---------------------------------------------->|
  |                                               |
  | CONNECTED                                     |
  |<----------------------------------------------|
  |                                               |
  | SEND / SUBSCRIBE / ACK / ...                  |
  |---------------------------------------------->|
  |                                               |
  | RECEIPT (nếu frame yêu cầu receipt)           |
  |<----------------------------------------------|
  |                                               |
  | DISCONNECT                                    |
  |---------------------------------------------->|
  |                                               |
  | RECEIPT                                       |
  |<----------------------------------------------|
  |                                               |
  | Close socket                                  |
~~~

Trong STOMP 1.2:

- Client có thể gửi header **receipt** trên mọi client frame ngoại trừ CONNECT.
- Server gửi frame **RECEIPT** khi đã xử lý thành công một frame yêu cầu receipt.
- Frame RECEIPT phải có header **receipt-id** mang đúng giá trị receipt mà client đã gửi.
- Header receipt của DISCONNECT là tùy chọn.
- Nếu client đã gửi DISCONNECT, client không được gửi thêm STOMP frame nào trên kết nối đó.

Destination và delivery semantics vẫn phụ thuộc server/broker. STOMP không tự định nghĩa rằng một destination có tên /queue hoặc /topic phải có cùng hành vi trên mọi broker.

## 2. DISCONNECT: yêu cầu kết thúc STOMP session

**DISCONNECT** là frame client dùng để thông báo muốn kết thúc STOMP session. Client có thể đóng socket trực tiếp, nhưng cách đó không bảo đảm server đã nhận những frame trước đó.

Frame DISCONNECT không có body và không yêu cầu header bắt buộc:

~~~text
DISCONNECT

^@
~~~

Trong ví dụ, ký hiệu **^@** biểu diễn một byte NULL kết thúc frame. Đây là cách ghi minh họa trong tài liệu giao thức, không phải chuỗi ký tự cần gửi nguyên văn.

### Đóng kết nối trực tiếp

Nếu client đóng TCP/WebSocket ngay sau khi gửi một SEND, có thể xảy ra:

1. Client đã ghi frame SEND vào buffer cục bộ.
2. Socket bị đóng trước khi frame đến server.
3. Client không nhận được phản hồi nào để biết server đã nhận hay chưa.
4. Ứng dụng không biết message đã được server xử lý hay chưa.

Vì vậy, đóng socket trực tiếp phù hợp khi ứng dụng chấp nhận kết quả không chắc chắn hoặc đã có cơ chế phục hồi riêng.

### Đóng kết nối có xác nhận

Để graceful disconnect, STOMP 1.2 khuyến nghị client:

1. Gửi DISCONNECT kèm header receipt.
2. Chờ RECEIPT có receipt-id khớp.
3. Sau khi nhận được RECEIPT, đóng socket.

Ví dụ:

~~~text
DISCONNECT
receipt:disconnect-77

^@
~~~

Server phản hồi:

~~~text
RECEIPT
receipt-id:disconnect-77

^@
~~~

Client chỉ đóng transport sau khi đã nhận frame RECEIPT tương ứng. Giá trị receipt là token tương quan do client chọn; nên dùng giá trị duy nhất trong phạm vi các receipt đang chờ để tránh ghép nhầm phản hồi.

### Không gửi frame sau DISCONNECT

Sau khi gửi DISCONNECT, client MUST NOT gửi thêm frame nào. Vì vậy, hãy hoàn tất các thao tác cần gửi trước khi phát DISCONNECT:

~~~text
SEND
destination:/app/orders
receipt:send-1001

{"orderId":"ORD-1001"}^@

DISCONNECT
receipt:disconnect-1001

^@
~~~

Client chờ receipt cho DISCONNECT rồi mới đóng socket. Không gửi thêm SEND, SUBSCRIBE, ACK hoặc heartbeat STOMP sau DISCONNECT.

## 3. Header receipt và frame RECEIPT

Header **receipt** yêu cầu server xác nhận việc xử lý một client frame. Giá trị của nó là chuỗi tùy ý do client cung cấp.

Ví dụ client gửi SEND:

~~~text
SEND
destination:/queue/orders
content-type:application/json
receipt:send-2026-001

{"orderId":"ORD-1001"}^@
~~~

Server trả:

~~~text
RECEIPT
receipt-id:send-2026-001

^@
~~~

Có thể dùng receipt với nhiều loại frame client, chẳng hạn SEND, SUBSCRIBE, UNSUBSCRIBE, ACK, COMMIT hoặc DISCONNECT, miễn server hỗ trợ semantics tương ứng.

### receipt và receipt-id

| Header | Hướng | Vai trò |
|---|---|---|
| **receipt** | Client → Server | Client yêu cầu server gửi xác nhận cho frame này. |
| **receipt-id** | Server → Client | Server trả lại giá trị receipt để client biết frame nào đã được xác nhận. |

Hai header này không phải message-id hoặc subscription id:

- **message-id** định danh một MESSAGE frame do server giao.
- **subscription** xác định subscription nhận MESSAGE.
- **receipt** là token yêu cầu xác nhận một client frame.
- **receipt-id** là token server dùng để phản hồi yêu cầu đó.

Nên tạo receipt ID có thể truy vết trong log, ví dụ theo loại thao tác và một UUID. Không tái sử dụng cùng token cho nhiều thao tác đang chờ vì client sẽ khó phân biệt các phản hồi.

### Server xử lý frame nào?

Server gửi RECEIPT khi đã xử lý thành công client frame có yêu cầu receipt. Nếu frame có lỗi, server có thể gửi ERROR. Khi ERROR liên quan đến một frame có receipt, server nên đưa receipt-id tương ứng vào ERROR để client xác định thao tác gây lỗi.

Không phải mọi server hoặc broker đều hỗ trợ receipt cho mọi command. Hãy kiểm tra tài liệu broker và phiên bản STOMP được thương lượng trong CONNECTED.

## 4. RECEIPT xác nhận điều gì?

RECEIPT xác nhận server đã xử lý client frame tương ứng. Vì STOMP truyền frame theo một stream có thứ tự, receipt cũng xác nhận rằng server đã nhận tất cả frame trước frame được xác nhận.

Tuy nhiên, có một điểm rất quan trọng: **các frame trước đó có thể vẫn chưa được xử lý hoàn toàn**.

Ví dụ:

~~~text
SEND receipt:send-1
SEND
SEND
DISCONNECT receipt:disconnect-1
~~~

Khi client nhận RECEIPT cho disconnect-1, client có thể kết luận server đã nhận các frame đứng trước trong stream và đã xử lý frame DISCONNECT. Client không được suy luận rằng mọi công việc downstream từ hai frame SEND đã hoàn tất.

Cần phân biệt ba mức:

1. **Frame đã được gửi khỏi client:** transport đã nhận dữ liệu từ ứng dụng hoặc client library.
2. **Server đã nhận/xử lý frame:** được xác nhận ở mức STOMP bằng RECEIPT.
3. **Nghiệp vụ đã hoàn tất:** consumer hoặc service downstream đã xử lý dữ liệu và xác nhận theo hợp đồng nghiệp vụ riêng.

RECEIPT thuộc mức thứ hai. Mức thứ ba cần ACK, reply, event kết quả hoặc một cơ chế xác nhận nghiệp vụ được thiết kế riêng.

### RECEIPT cho SEND không phải xác nhận consumer

Khi client gửi SEND kèm receipt và nhận RECEIPT, điều đó không tự chứng minh:

- Message đã được consumer nhận.
- Consumer đã chạy xong handler.
- Database của consumer đã commit.
- Tất cả subscriber đã nhận broadcast.
- Message đã được lưu bền vững theo chính sách cụ thể của broker.

STOMP để delivery semantics và độ bền của destination phụ thuộc server implementation. Nếu ứng dụng cần xác nhận consumer xử lý xong, hãy thiết kế reply hoặc event kết quả có correlation ID và business event ID.

### RECEIPT cho SUBSCRIBE

Receipt cho SUBSCRIBE có thể dùng để biết server đã xử lý yêu cầu đăng ký. Điều này hữu ích khi client cần đợi subscription được thiết lập trước khi bắt đầu publish hoặc thực hiện thao tác tiếp theo.

Tuy nhiên, receipt cho SUBSCRIBE chỉ có ý nghĩa khi broker hỗ trợ. Built-in simple broker của Spring không hỗ trợ receipt; nếu cần xác nhận subscription ở mức broker, hãy dùng full-featured broker qua STOMP broker relay và xác minh khả năng hỗ trợ của broker.

## 5. RECEIPT khác ACK, NACK và ERROR

Các frame này thường bị nhầm vì đều liên quan đến xác nhận hoặc lỗi, nhưng hướng truyền và ý nghĩa khác nhau.

| Frame | Hướng | Mục đích |
|---|---|---|
| **RECEIPT** | Server → Client | Xác nhận server đã xử lý client frame có header receipt. |
| **ACK** | Client → Server | Xác nhận client đã tiêu thụ một MESSAGE trong subscription dùng explicit acknowledgment. |
| **NACK** | Client → Server | Báo client không tiêu thụ được MESSAGE. |
| **ERROR** | Server → Client | Báo lỗi giao thức hoặc lỗi xử lý frame; server STOMP 1.2 đóng kết nối sau ERROR theo đặc tả. |
| **CONNECTED** | Server → Client | Xác nhận STOMP connection đã được thiết lập và thương lượng phiên bản. |

### ACK/NACK xác nhận message được giao

ACK/NACK liên quan đến message server gửi cho client qua subscription. Client chỉ cần gửi ACK khi SUBSCRIBE dùng:

- **ack:auto:** server xem message đã được nhận ngay khi gửi cho client; client không gửi ACK.
- **ack:client:** client gửi ACK; ACK có tính cumulative đối với các message trước đó của subscription chưa được xác nhận.
- **ack:client-individual:** ACK/NACK chỉ áp dụng cho message tương ứng, không xác nhận các message trước.

Ví dụ SUBSCRIBE:

~~~text
SUBSCRIBE
id:orders-sub
destination:/queue/orders
ack:client-individual

^@
~~~

Server gửi MESSAGE có header ack:

~~~text
MESSAGE
subscription:orders-sub
message-id:msg-901
ack:ack-token-901
destination:/queue/orders

{"orderId":"ORD-1001"}^@
~~~

Client xác nhận message đã xử lý:

~~~text
ACK
id:ack-token-901

^@
~~~

Nếu client không xử lý được, có thể gửi NACK:

~~~text
NACK
id:ack-token-901

^@
~~~

Server quyết định redelivery, discard hoặc chuyển dead-letter theo chính sách của broker.

### Có thể yêu cầu receipt cho ACK không?

Có. ACK là client frame, nên client có thể thêm receipt header nếu broker hỗ trợ. Khi đó:

- ACK thể hiện client xác nhận đã tiêu thụ MESSAGE.
- RECEIPT xác nhận server đã xử lý frame ACK đó.

Hai việc này khác nhau. RECEIPT cho ACK không thay thế ý nghĩa acknowledgment của ACK.

### ERROR và receipt bị thiếu

Nếu server gửi ERROR liên quan đến frame có receipt, ERROR có thể mang receipt-id để chỉ ra token của frame gây lỗi. STOMP 1.2 quy định server gửi ERROR rồi đóng kết nối.

Nếu client không nhận được RECEIPT trước timeout, không thể kết luận chắc chắn thao tác thất bại. Có thể server chưa nhận frame, server đã xử lý nhưng phản hồi bị mất, broker không hỗ trợ receipt hoặc kết nối bị đóng quá sớm. Hãy coi kết quả là chưa xác định và dùng idempotency/correlation để kiểm tra trước khi gửi lại thao tác có side effect.

## 6. Trình tự graceful disconnect đầy đủ

Một client có thể dùng trình tự sau khi kết thúc công việc:

~~~text
1. Dừng nhận thêm công việc mới ở tầng ứng dụng.
2. Hoàn tất hoặc ghi nhận các thao tác đang chạy.
3. Gửi các frame cuối cùng cần thiết.
4. Gửi DISCONNECT với receipt token duy nhất.
5. Chờ RECEIPT có receipt-id trùng token.
6. Đóng WebSocket/TCP socket.
~~~

Ví dụ wire-level:

~~~text
SEND
destination:/app/orders
receipt:send-order-1001
content-type:application/json

{"orderId":"ORD-1001"}^@

DISCONNECT
receipt:close-session-77

^@
~~~

Phản hồi server:

~~~text
RECEIPT
receipt-id:send-order-1001

^@

RECEIPT
receipt-id:close-session-77

^@
~~~

Trong ví dụ, receipt cho SEND xác nhận server đã xử lý SEND. Receipt cho DISCONNECT xác nhận server đã xử lý DISCONNECT và cumulative-ack các frame trước đó đã nhận. Nó vẫn không chứng minh consumer đã hoàn tất xử lý OrderCreated.

Nếu client chỉ cần đóng session và chấp nhận không chờ xác nhận, có thể đóng socket hoặc dùng API disconnect thông thường. Nếu yêu cầu graceful protocol shutdown, phải giữ transport mở đủ lâu để nhận đúng receipt.

### Server có thể đóng socket quá sớm

STOMP 1.2 mô tả connection lingering: server có thể giữ kết nối đã đóng trong thời gian ngắn để hỗ trợ client connect/disconnect nhanh. Nếu server đóng đầu socket quá sớm, client có thể không nhận được RECEIPT cuối cùng cho DISCONNECT.

Vì vậy:

- Đặt timeout chờ receipt hữu hạn.
- Khi hết timeout, ghi nhận trạng thái disconnect chưa được xác nhận.
- Không gửi thêm frame trên connection đã gửi DISCONNECT.
- Nếu cần tiếp tục, tạo connection mới và kiểm tra trạng thái nghiệp vụ bằng event ID hoặc request trạng thái.
- Không gửi lại một lệnh nghiệp vụ chỉ vì không nhận được receipt, trừ khi lệnh có idempotency key.

## 7. Spring WebSocket STOMP client và receipt callback

Spring cung cấp **WebSocketStompClient** và **StompSession** để gửi/nhận STOMP qua WebSocket. Khi cần theo dõi receipt cho thao tác SEND hoặc SUBSCRIBE, Spring cung cấp **StompSession.Receiptable**.

Để receipt tracking hoạt động, cấu hình **TaskScheduler** cho client. Scheduler dùng để theo dõi thời hạn receipt. Thời gian chờ mặc định là 15 giây; có thể thay đổi bằng receipt time limit.

### Cấu hình client và TaskScheduler

~~~java
ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
scheduler.setPoolSize(1);
scheduler.setThreadNamePrefix("stomp-receipt-");
scheduler.initialize();

WebSocketStompClient stompClient =
        new WebSocketStompClient(new StandardWebSocketClient());

stompClient.setTaskScheduler(scheduler);
stompClient.setReceiptTimeLimit(5_000L);
~~~

Đoạn cấu hình này cần dependency Spring WebSocket và một endpoint WebSocket STOMP đang chạy. Trong ứng dụng Spring, nên quản lý scheduler như một bean để Spring quản lý lifecycle và shutdown.

### Theo dõi receipt của SEND

~~~java
public class OrderStompSessionHandler extends StompSessionHandlerAdapter {

    @Override
    public void afterConnected(
            StompSession session,
            StompHeaders connectedHeaders
    ) {
        session.setAutoReceipt(true);

        StompSession.Receiptable receipt = session.send(
                "/app/orders",
                "{\"orderId\":\"ORD-1001\"}"
        );

        receipt.addReceiptTask(headers -> {
            System.out.println(
                    "SEND processed; receipt-id="
                            + headers.getFirst("receipt-id")
            );
        });

        receipt.addReceiptLostTask(() -> {
            System.err.println(
                    "No RECEIPT received before the configured timeout"
            );
        });
    }
}
~~~

Khi bật **setAutoReceipt(true)**, Spring tự thêm receipt header cho các thao tác SEND và SUBSCRIBE tiếp theo. Kết quả của send là Receiptable, cho phép đăng ký:

- **addReceiptTask:** callback chạy khi nhận RECEIPT.
- **addReceiptLostTask:** callback chạy khi hết thời gian chờ mà chưa nhận được receipt.
- **getReceiptId:** lấy token receipt được gắn cho thao tác.

Nếu không bật auto receipt, hãy đặt receipt thủ công trên StompHeaders trước khi gọi overload send/subscribe tương ứng. Nếu không có receipt header, không thể đăng ký callback nhận receipt trên Receiptable.

### Theo dõi receipt của SUBSCRIBE

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
                System.out.println("received=" + payload);
            }
        }
);

subscription.addReceiptTask(headers -> {
    System.out.println(
            "SUBSCRIBE processed; receipt-id="
                    + headers.getFirst("receipt-id")
    );
});

subscription.addReceiptLostTask(() ->
        System.err.println("Subscription receipt timed out")
);
~~~

Subscription handle của Spring cũng hỗ trợ theo dõi receipt. Chỉ dùng callback này khi STOMP server thực sự hỗ trợ receipt cho SUBSCRIBE. Built-in simple broker của Spring không hỗ trợ receipt; hãy kiểm tra broker relay và broker thực tế.

### Lưu ý riêng với DISCONNECT trong StompSession

API **StompSession.disconnect(StompHeaders)** cho phép truyền headers của DISCONNECT, nhưng phương thức trả về **void**, không cung cấp Receiptable để chờ receipt như send/subscribe. Trong implementation client Spring, thao tác disconnect gửi frame rồi reset/đóng transport connection. Vì vậy, không nên xem việc thêm receipt header vào lời gọi này là một quy trình chờ RECEIPT hoàn chỉnh.

Nếu yêu cầu bắt buộc là gửi DISCONNECT, nhận matching RECEIPT rồi mới đóng socket, hãy dùng một STOMP client/transport có hỗ trợ rõ việc giữ kết nối chờ receipt hoặc tự quản lý vòng đời transport. Với StompSession thông thường, dùng disconnect() cho việc đóng session theo API của Spring và hiểu rằng nó không cung cấp callback chờ receipt cho DISCONNECT.

## 8. Spring simple broker và external broker relay

Spring có built-in simple broker để phát triển và thử nghiệm. Nó lưu subscription trong bộ nhớ và broadcast message đến client phù hợp. Simple broker chỉ hỗ trợ một phần STOMP protocol và không hỗ trợ ACK, receipt cùng một số command khác.

Nếu ứng dụng cần:

- Receipt cho SEND/SUBSCRIBE/DISCONNECT.
- Explicit ACK/NACK.
- Broker persistence, redelivery hoặc dead-letter.
- Nhiều node ứng dụng cùng dùng broker.
- Các semantics giao nhận nâng cao.

Hãy dùng broker đầy đủ hỗ trợ STOMP và cấu hình **STOMP broker relay**. Broker cụ thể có thể hỗ trợ thêm header hoặc semantics riêng; luôn đối chiếu tài liệu đúng phiên bản của broker.

Không suy ra rằng receipt hoạt động chỉ vì ứng dụng đã bật STOMP over WebSocket. Receipt là khả năng của STOMP server/broker mà client đang kết nối.

## 9. Sự kiện disconnect phía server trong Spring

Ở phía server Spring WebSocket, **SessionDisconnectEvent** được phát khi STOMP/WebSocket session kết thúc. Sự kiện có thể xảy ra vì client gửi DISCONNECT hoặc vì WebSocket transport đóng.

Một session có thể phát SessionDisconnectEvent nhiều hơn một lần. Listener xử lý sự kiện này phải idempotent, ví dụ chỉ xóa trạng thái session nếu session còn tồn tại và không lặp side effect.

Ví dụ:

~~~java
@Component
public class StompSessionEvents {

    private final SessionRegistry sessionRegistry;

    public StompSessionEvents(SessionRegistry sessionRegistry) {
        this.sessionRegistry = sessionRegistry;
    }

    @EventListener
    public void onDisconnect(SessionDisconnectEvent event) {
        sessionRegistry.removeIfPresent(event.getSessionId());
    }
}
~~~

**SessionDisconnectEvent không phải RECEIPT.** Đây là application event nội bộ phía server báo session đã kết thúc. Nó không chứng minh client đã nhận một frame RECEIPT và cũng không xác nhận message nghiệp vụ đã được consumer xử lý.

Nếu cần audit việc client yêu cầu graceful disconnect, có thể ghi nhận receipt token và kết quả xử lý ở tầng giao thức/broker. Không dùng event disconnect thay thế cho protocol receipt.

## 10. Timeout, retry và idempotency

Receipt timeout là tình huống phổ biến trong hệ thống mạng. Client có thể không nhận receipt vì:

- Broker chưa xử lý frame.
- Broker đã xử lý nhưng phản hồi bị mất.
- Kết nối bị ngắt trước khi frame đến server.
- Server không hỗ trợ receipt cho command đó.
- Server đóng connection quá nhanh sau DISCONNECT.
- Scheduler hoặc receipt time limit phía client cấu hình không phù hợp.

Khi timeout, trạng thái thao tác là **chưa xác định**. Không nên mặc định rằng thao tác thất bại và gửi lại ngay một command có side effect.

### Mẫu xử lý an toàn

1. Mỗi lệnh nghiệp vụ có eventId hoặc idempotency key ổn định.
2. Client gắn receipt token riêng cho frame để tương quan phản hồi giao thức.
3. Nếu nhận RECEIPT, ghi nhận server đã xử lý frame theo semantics STOMP.
4. Nếu timeout hoặc transport error, giữ trạng thái chưa xác định.
5. Reconnect nếu cần và truy vấn trạng thái nghiệp vụ bằng eventId.
6. Chỉ gửi lại khi consumer/server có thể deduplicate hoặc khi xác định chắc lệnh chưa được áp dụng.

Receipt token và eventId có mục đích khác nhau:

| Giá trị | Phạm vi | Mục đích |
|---|---|---|
| receipt | STOMP frame | Tương quan client frame với RECEIPT. |
| receipt-id | STOMP response | Chỉ ra receipt request được server xác nhận. |
| eventId | Hợp đồng nghiệp vụ | Định danh event/lệnh để deduplicate và truy vấn kết quả. |
| correlationId | Luồng request/reply | Liên kết request với response hoặc các thao tác liên quan. |

Không dùng receipt-id làm khóa nghiệp vụ lâu dài. Receipt thuộc một lần giao tiếp STOMP và không thay thế event ID.

## 11. Những lỗi thường gặp

1. **Đóng socket ngay sau SEND rồi giả định server đã nhận message.** TCP/WebSocket close không cung cấp xác nhận xử lý STOMP cho frame trước đó.
2. **Gửi DISCONNECT mà không chờ receipt khi cần graceful shutdown.** Client có thể đóng kết nối trước khi server nhận các frame cuối.
3. **Gửi thêm frame sau DISCONNECT.** STOMP 1.2 cấm client gửi thêm frame trên connection đó.
4. **Nhầm receipt với ACK.** RECEIPT xác nhận server xử lý client frame; ACK xác nhận client tiêu thụ MESSAGE.
5. **Cho rằng RECEIPT đồng nghĩa consumer xử lý xong.** Receipt không xác nhận nghiệp vụ downstream hoặc database commit.
6. **Cho rằng receipt cho frame cuối xác nhận mọi frame trước đã xử lý xong.** Receipt là cumulative acknowledgment rằng các frame trước đã được server nhận; chúng có thể chưa được xử lý hoàn toàn.
7. **Không ghép receipt-id với receipt token.** Có thể nhận nhầm phản hồi khi nhiều thao tác đang chờ.
8. **Dùng cùng receipt token cho nhiều request đang chờ.** Client khó phân biệt các receipt.
9. **Bật setAutoReceipt nhưng không cấu hình TaskScheduler.** Spring cần scheduler để theo dõi timeout receipt.
10. **Không xử lý addReceiptLostTask.** Khi không nhận receipt, ứng dụng không biết thao tác có kết quả hay không.
11. **Giả định simple broker hỗ trợ receipt.** Built-in simple broker của Spring không hỗ trợ receipt và ACK; cần broker đầy đủ khi dùng các tính năng đó.
12. **Dùng StompSession.disconnect(StompHeaders) như API chờ receipt.** Phương thức trả về void và không cung cấp Receiptable; client Spring đóng transport sau khi gửi DISCONNECT.
13. **Coi SessionDisconnectEvent là protocol receipt.** Đây là sự kiện vòng đời phía server, có thể được phát nhiều lần và cần xử lý idempotent.
14. **Retry ngay sau receipt timeout.** Kết quả có thể chưa xác định; cần eventId, idempotency và kiểm tra trạng thái trước khi gửi lại.
15. **Không kiểm tra broker-specific semantics.** STOMP chuẩn hóa frame, nhưng hỗ trợ command và delivery semantics vẫn phụ thuộc server.

## 12. Ghi nhớ

- **DISCONNECT** yêu cầu kết thúc STOMP session.
- **RECEIPT** là phản hồi server cho client frame có header receipt; receipt-id phải khớp giá trị receipt.
- Với graceful disconnect, gửi DISCONNECT kèm receipt, chờ matching RECEIPT rồi đóng socket.
- Sau khi gửi DISCONNECT, client không được gửi thêm frame.
- RECEIPT xác nhận xử lý ở mức giao thức và cumulative acknowledgment việc server đã nhận các frame trước; nó không chứng minh mọi công việc downstream đã hoàn tất.
- **ACK/NACK** xác nhận client đã hoặc chưa tiêu thụ MESSAGE; ý nghĩa khác RECEIPT.
- Spring StompSession hỗ trợ Receiptable cho SEND/SUBSCRIBE; cần TaskScheduler và có timeout tracking.
- Built-in simple broker không hỗ trợ receipt; cần kiểm tra khả năng của external broker.
- StompSession.disconnect(StompHeaders) không cung cấp Receiptable để chờ DISCONNECT receipt.
- SessionDisconnectEvent là event vòng đời server, không phải RECEIPT.
- Khi receipt timeout, coi kết quả là chưa xác định; dùng idempotency key và kiểm tra trạng thái nghiệp vụ trước khi retry.

Khi xây dựng client STOMP, hãy quyết định rõ thao tác nào cần receipt, thao tác nào cần ACK nghiệp vụ và khi nào có thể đóng transport. Dùng receipt để xác nhận giao thức, dùng event/reply để xác nhận nghiệp vụ, và chỉ đóng kết nối sau khi đã hoàn tất trình tự shutdown mà ứng dụng yêu cầu.

## Tài liệu tham khảo

- [STOMP Protocol Specification 1.2 — Header receipt, DISCONNECT and RECEIPT](https://stomp.github.io/stomp-specification-1.2.html)
- [Spring Framework 6.2 — STOMP Client](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/client.html)
- [Spring Framework 6.2 — StompSession API](https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/messaging/simp/stomp/StompSession.html)
- [Spring Framework 6.2 — StompSession.Receiptable API](https://docs.spring.io/spring-framework/docs/6.2.x-SNAPSHOT/javadoc-api/org/springframework/messaging/simp/stomp/StompSession.Receiptable.html)
- [Spring Framework 6.2 — Simple Broker](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/handle-simple-broker.html)
- [Spring Framework 6.2 — Application Context Events](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/application-context-events.html)
