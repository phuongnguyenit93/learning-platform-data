# Ngắt kết nối có kiểm soát và giải phóng tài nguyên client STOMP trong Spring

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt hủy một subscription, ngắt một STOMP session và dừng toàn bộ WebSocket client.
- Gửi STOMP `UNSUBSCRIBE` và `DISCONNECT` đúng thời điểm.
- Thiết kế thứ tự shutdown để ngừng phát message, giải phóng subscription, đóng kết nối và dừng các thành phần do client sở hữu.
- Quản lý vòng đời `WebSocketStompClient`, `WebSocketClient`, `TaskScheduler` và HTTP client mà không đóng nhầm tài nguyên dùng chung.
- Xử lý race condition giữa kết nối bất đồng bộ và yêu cầu shutdown.
- Phân biệt đóng kết nối có chủ đích với lỗi transport, timeout và reconnect.
- Làm cho cleanup phía server an toàn khi sự kiện disconnect được phát nhiều lần.

Bài viết tập trung vào Java STOMP over WebSocket với Spring Framework. Các ví dụ dùng API có trong Spring Framework 6.x trở lên; phần khác biệt giữa Spring 6.2 và 7.0 được ghi rõ khi có ảnh hưởng tới mã nguồn.

## 1. Vòng đời client có nhiều lớp

Một client STOMP thường sở hữu nhiều đối tượng với vòng đời khác nhau:

| Thành phần | Trách nhiệm | Cách kết thúc |
|---|---|---|
| `StompSession` | Phiên STOMP đã kết nối, gửi message và quản lý subscription | `disconnect()` |
| `StompSession.Subscription` | Một đăng ký nhận message tại destination | `unsubscribe()` |
| WebSocket connection | Kênh transport hai chiều bên dưới STOMP | Được đóng khi session kết thúc; raw API có `WebSocketSession.close()` |
| `WebSocketStompClient` | Quản lý việc kết nối STOMP qua WebSocketClient | `stop()` theo vòng đời client |
| `WebSocketClient` | Implementation transport như Standard, Jetty hoặc SockJS | Dừng nếu implementation hỗ trợ `Lifecycle` |
| `TaskScheduler` | Chạy tác vụ heartbeat và theo dõi receipt | Dừng theo chủ sở hữu scheduler |
| HTTP client / connection pool | Hỗ trợ XHR transport của SockJS hoặc transport tùy chỉnh | Đóng theo chủ sở hữu HTTP client |

Không phải mọi đối tượng đều có cùng một chủ sở hữu. Một ứng dụng có thể dùng một `WebSocketStompClient` và một `TaskScheduler` chung cho nhiều session. Khi đó, đóng một session không có nghĩa là phải dừng client hoặc scheduler dùng chung.

## 2. Phân biệt UNSUBSCRIBE, DISCONNECT và WebSocket CLOSE

Ba thao tác này có mục đích khác nhau:

- **UNSUBSCRIBE:** bỏ một subscription. Session STOMP vẫn tiếp tục hoạt động và có thể gửi message hoặc đăng ký destination khác.
- **DISCONNECT:** kết thúc toàn bộ STOMP session. Mọi subscription gắn với session đó được giải phóng khi session kết thúc.
- **WebSocket CLOSE:** đóng kết nối transport ở tầng WebSocket. Đây là thao tác tầng thấp, không thay thế ý nghĩa của STOMP DISCONNECT.

Ví dụ một session đang nghe hai destination:

~~~text
STOMP session S1
  +-- subscription sub-1 -> /topic/orders
  +-- subscription sub-2 -> /topic/notifications
~~~

Nếu chỉ bỏ thông báo đơn hàng, gửi UNSUBSCRIBE cho `sub-1`; `sub-2` vẫn hoạt động. Nếu ứng dụng ngừng hoàn toàn, gửi DISCONNECT cho session S1 để kết thúc phiên và giải phóng cả hai subscription.

Không nên đóng raw WebSocket trước rồi mới hy vọng broker nhận được STOMP DISCONNECT. Khi có `StompSession`, hãy dùng API STOMP của session để kết thúc phiên theo đúng giao thức.

## 3. Hủy một subscription khi session vẫn còn hoạt động

Phương thức `StompSession.subscribe` trả về một handle `StompSession.Subscription`. Giữ handle đó nếu sau này cần hủy riêng subscription:

~~~java
StompSession.Subscription updates = session.subscribe(
        "/topic/updates",
        new StompFrameHandler() {

            @Override
            public Type getPayloadType(StompHeaders headers) {
                return String.class;
            }

            @Override
            public void handleFrame(
                    StompHeaders headers,
                    Object payload) {
                System.out.println("Update: " + payload);
            }
        });

// Khi không còn cần nhận /topic/updates:
updates.unsubscribe();
~~~

`unsubscribe()` gửi STOMP frame UNSUBSCRIBE cho subscription tương ứng. Session vẫn kết nối và các subscription khác tiếp tục hoạt động.

Một số lưu ý:

1. Giữ handle của từng subscription mà ứng dụng cần hủy độc lập.
2. Không tạo subscription mới mỗi lần reconnect mà quên dọn session cũ.
3. Khi session đã mất kết nối, không cần gửi UNSUBSCRIBE cho từng handle cũ; broker sẽ dọn subscription gắn với session khi kết nối kết thúc.
4. Hủy subscription không xóa dữ liệu ở broker hoặc database; nó chỉ chấm dứt việc nhận message qua subscription đó.

### Khác biệt API giữa Spring 6.2 và 7.0

Trong Spring 6.2, `Subscription.unsubscribe()` trả về `void`. Từ Spring 7.0, phương thức này trả về `StompSession.Receiptable`, cho phép theo dõi receipt nếu broker hỗ trợ và client đã cấu hình `TaskScheduler`.

Không viết mã dựa vào giá trị trả về của `unsubscribe()` nếu dự án cần tương thích Spring 6.2. Hãy kiểm tra Javadoc đúng phiên bản đang dùng.

## 4. Kết thúc toàn bộ STOMP session

`StompSession.disconnect()` gửi STOMP frame DISCONNECT. Interface cũng cung cấp overload nhận `StompHeaders` để truyền header bổ sung.

~~~java
if (session != null && session.isConnected()) {
    session.disconnect();
}
~~~

Trong implementation mặc định của Spring, quá trình disconnect gửi frame DISCONNECT rồi reset và đóng kết nối transport bên dưới. API công khai cam kết thao tác kết thúc STOMP session bằng cách gửi DISCONNECT.

Sau khi disconnect:

- Session không còn là một phiên hoạt động để gửi message.
- Các subscription gắn với session được kết thúc.
- Client cần tạo một STOMP session mới nếu muốn kết nối lại.
- Các handle subscription cũ không nên được tái sử dụng cho session mới.

`isConnected()` giúp kiểm tra trạng thái hiện tại của session. Tuy nhiên, trạng thái này không phải phép kiểm tra mạng từ xa tức thời. Nếu mạng vừa đứt nhưng heartbeat hoặc callback lỗi chưa được xử lý, trạng thái quan sát được có thể chưa phản ánh ngay tình trạng thực tế.

## 5. Một quy trình shutdown an toàn

Khi ứng dụng chủ động dừng client, hãy thực hiện theo thứ tự:

1. Đánh dấu client đang shutdown để không khởi tạo thêm kết nối hoặc reconnect.
2. Ngừng các tác vụ nghiệp vụ đang phát message qua session.
3. Hủy các subscription riêng lẻ nếu session vẫn cần tiếp tục hoạt động trong một khoảng thời gian. Nếu đóng toàn bộ session ngay, DISCONNECT sẽ kết thúc tất cả subscription.
4. Gửi DISCONNECT cho STOMP session đang hoạt động.
5. Xóa tham chiếu session và subscription để tránh giữ đối tượng không còn sử dụng.
6. Dừng `WebSocketStompClient` nếu component hiện tại sở hữu client đó.
7. Đóng HTTP client, scheduler hoặc executor riêng chỉ sau khi các session và client dùng chúng đã kết thúc.

Ví dụ phương thức kết thúc session:

~~~java
private final AtomicReference<StompSession> sessionRef =
        new AtomicReference<>();

public void disconnectSession() {
    StompSession current = sessionRef.getAndSet(null);

    if (current != null && current.isConnected()) {
        current.disconnect();
    }
}
~~~

Dùng `getAndSet(null)` để chỉ một luồng lấy quyền kết thúc session hiện tại. Nếu nhiều luồng cùng gọi shutdown, các lần gọi sau sẽ không lấy lại cùng một tham chiếu.

Nếu ứng dụng sở hữu riêng cả `WebSocketStompClient`, có thể dừng nó sau khi kết thúc session:

~~~java
public void closeOwnedClient() {
    try {
        disconnectSession();
    }
    finally {
        stompClient.stop();
    }
}
~~~

Nếu `WebSocketStompClient` được chia sẻ giữa nhiều session hoặc nhiều thành phần, không gọi `stop()` khi chỉ một session kết thúc. Chỉ dừng client khi chủ sở hữu cấp ứng dụng quyết định toàn bộ client không còn được sử dụng.

## 6. Dừng WebSocketStompClient và quản lý Lifecycle

`WebSocketStompClient` triển khai `SmartLifecycle`. Nó có các phương thức `start()`, `stop()`, `isRunning()` và cấu hình phase cho thứ tự khởi động, shutdown.

Khi được quản lý như Spring bean:

- `autoStartup` mặc định là `true`.
- Spring Lifecycle processor có thể tự khởi động và dừng client khi ApplicationContext được refresh hoặc đóng.
- `setPhase` điều chỉnh thứ tự khởi động và thứ tự dừng. Thành phần có phase lớn hơn được khởi động muộn hơn và dừng sớm hơn.
- `stop()` dừng WebSocketClient được chứa nếu implementation đó cũng triển khai `Lifecycle`.

Ví dụ cấu hình bean:

~~~java
@Configuration
public class StompClientConfiguration {

    @Bean
    public WebSocketStompClient webSocketStompClient(
            WebSocketClient webSocketClient,
            TaskScheduler taskScheduler) {

        WebSocketStompClient client =
                new WebSocketStompClient(webSocketClient);

        client.setTaskScheduler(taskScheduler);
        client.setInboundMessageSizeLimit(64 * 1024);
        client.setPhase(100);

        return client;
    }
}
~~~

Trong ví dụ, `WebSocketClient` và `TaskScheduler` được inject từ container. Bean client sử dụng scheduler cho heartbeat và receipt tracking. Container quản lý vòng đời của các bean theo cấu hình Lifecycle của chúng.

Nếu ứng dụng cần gửi DISCONNECT trước khi client transport bị dừng, component đang giữ các `StompSession` phải thực hiện cleanup ở phase shutdown phù hợp. Không chỉ dựa vào việc `WebSocketStompClient.stop()` được gọi để thay cho việc kết thúc từng session.

## 7. Phân biệt tài nguyên do client sở hữu và tài nguyên dùng chung

Đây là nguyên tắc quan trọng nhất khi giải phóng tài nguyên.

### Tài nguyên theo session

- `StompSession` hiện tại.
- Các subscription handle của session.
- Các tác vụ heartbeat hoặc receipt gắn với session.
- Callback hoặc listener mà component giữ riêng cho session.

Khi session kết thúc, xóa các tham chiếu này và ngừng tác vụ ứng dụng liên quan.

### Tài nguyên theo client

- `WebSocketStompClient`.
- Implementation `WebSocketClient`.
- HTTP transport client của SockJS nếu có.
- Connection pool hoặc executor riêng mà client tạo ra.

Chỉ đóng chúng khi toàn bộ session dùng client đã kết thúc và chủ sở hữu không còn cần client nữa.

### Tài nguyên dùng chung của ứng dụng

- `TaskScheduler` được nhiều client hoặc service sử dụng.
- Executor dùng chung.
- HTTP connection pool dùng chung.
- Bean do Spring container quản lý.

Không shutdown tài nguyên dùng chung từ phương thức đóng một session. Để container hoặc thành phần sở hữu cấp cao nhất thực hiện shutdown đúng thời điểm.

## 8. Heartbeat và TaskScheduler

`WebSocketStompClient` có thể dùng `TaskScheduler` cho STOMP heartbeat và receipt tracking. Khi cấu hình scheduler, client bật heartbeat mặc định phù hợp nếu heartbeat trước đó đang tắt.

Ví dụ:

~~~java
stompClient.setTaskScheduler(taskScheduler);
~~~

Mỗi session có thể tạo các tác vụ theo dõi hoạt động kết nối. Khi session kết thúc, việc quản lý trạng thái và các tác vụ liên quan của session cần được hoàn tất.

Không nên làm như sau khi một session đóng:

~~~java
// Không làm nếu scheduler còn được các session khác sử dụng:
((ThreadPoolTaskScheduler) taskScheduler).shutdown();
~~~

Việc shutdown scheduler dùng chung sẽ ảnh hưởng heartbeat và receipt tracking của các session khác.

Nếu ứng dụng tự tạo một scheduler riêng chỉ phục vụ một client owner, hãy dừng scheduler sau khi owner đã đóng mọi session và dừng client. Nếu scheduler là Spring bean dùng chung, để Spring quản lý lifecycle của bean đó.

Heartbeat giúp phát hiện kết nối không còn hoạt động. Nó không thay thế thao tác DISCONNECT có chủ đích và cũng không bảo đảm mọi message nghiệp vụ đã được xử lý.

## 9. Đóng transport khi dùng WebSocket thuần hoặc SockJS

Khi sử dụng STOMP, tầng ứng dụng nên kết thúc qua `StompSession.disconnect()`. API `WebSocketSession.close()` thuộc tầng transport và thường xuất hiện trong code làm việc trực tiếp với WebSocket.

`WebSocketSession.close()` đóng kết nối WebSocket với close status bình thường 1000; overload khác cho phép chỉ định close status. Nếu code đang nắm raw `WebSocketSession` mà không dùng STOMP, hãy đóng nó theo lifecycle của raw WebSocket.

Với `SockJsClient`, transport có thể là WebSocket hoặc HTTP fallback. Ứng dụng không nên giả định mọi session đều có một đối tượng raw WebSocket giống nhau. Hãy dùng API `StompSession` để kết thúc STOMP session, rồi để SockJS transport giải phóng các request và session liên quan.

Nếu cung cấp HTTP client hoặc Jetty client được tạo riêng, chủ sở hữu cần dừng hoặc đóng tài nguyên đó theo API của implementation. `WebSocketStompClient.stop()` chỉ truyền lệnh stop tới delegate nếu delegate triển khai `Lifecycle`; nó không thể tự đóng mọi tài nguyên tùy chỉnh mà ứng dụng đã tạo ở bên ngoài.

## 10. Xử lý kết nối bất đồng bộ và race condition

Kết nối STOMP thường bất đồng bộ. Có thể xảy ra tình huống:

1. Ứng dụng bắt đầu connect.
2. Shutdown bắt đầu trước khi STOMP CONNECTED được nhận.
3. Callback `afterConnected` chạy sau khi ứng dụng đã đánh dấu shutdown.
4. Một session mới được tạo trong lúc ứng dụng đang đóng.

Nếu callback không kiểm tra trạng thái shutdown, ứng dụng có thể vô tình tạo subscription mới hoặc giữ session không được đóng.

Mẫu xử lý:

~~~java
private final AtomicBoolean closing = new AtomicBoolean(false);
private final AtomicReference<StompSession> sessionRef =
        new AtomicReference<>();

public void onConnected(StompSession connected) {
    if (closing.get()) {
        connected.disconnect();
        return;
    }

    sessionRef.set(connected);

    // Tạo subscription sau khi session đã sẵn sàng.
}

public void close() {
    closing.set(true);

    StompSession current = sessionRef.getAndSet(null);
    if (current != null && current.isConnected()) {
        current.disconnect();
    }
}
~~~

Đây là khung xử lý vòng đời; nếu callback connect và shutdown có thể chạy đồng thời trong ứng dụng, cần đồng bộ việc đăng ký session để không có khoảng thời gian giữa kiểm tra `closing` và `sessionRef.set` làm session bị bỏ sót.

Với nhiều luồng hoặc nhiều kết nối đồng thời, có thể dùng một lock, một state machine hoặc một connection owner có thao tác chuyển trạng thái nguyên tử. Không chỉ dựa vào biến boolean rời rạc nếu nhiều callback có thể thay đổi session cùng lúc.

## 11. Phân biệt shutdown có chủ đích với transport error

`StompSessionHandler` cung cấp các callback quan trọng:

- `afterConnected`: STOMP session đã nhận CONNECTED và sẵn sàng.
- `handleTransportError`: có lỗi ở tầng transport, ví dụ kết nối bị mất.
- `handleException`: lỗi khi xử lý message hoặc callback.
- `handleFrame`: xử lý STOMP frame, bao gồm ERROR frame theo handler phù hợp.

Khi người dùng hoặc ứng dụng chủ động shutdown, đánh dấu trạng thái đóng trước khi gọi `disconnect()`. Nếu callback lỗi xuất hiện sau đó, không được kích hoạt reconnect.

Khi transport lỗi ngoài ý muốn, xóa tham chiếu session đã hỏng và quyết định reconnect theo chính sách của ứng dụng. Một reconnect thành công tạo session mới; ứng dụng phải đăng ký lại các destination cần thiết.

Không nên coi `handleTransportError` là lệnh đóng ứng dụng. Nó là tín hiệu để cập nhật trạng thái kết nối và áp dụng chính sách khôi phục.

## 12. Reconnect phải tạo session và subscription mới

Sau khi kết nối bị đứt, không tái sử dụng session cũ hoặc subscription handle cũ. Quy trình khôi phục thông thường:

1. Đánh dấu session hiện tại không còn hoạt động.
2. Dọn tham chiếu tới session và subscription cũ.
3. Nếu ứng dụng chưa shutdown, chờ theo exponential backoff có jitter.
4. Tạo STOMP connection mới.
5. Chờ callback `afterConnected`.
6. Đăng ký lại các destination cần thiết.
7. Đồng bộ dữ liệu bị bỏ lỡ qua API hoặc cơ chế lịch sử nếu nghiệp vụ yêu cầu.

Phân biệt hai tình huống:

| Tình huống | Hành động |
|---|---|
| Ứng dụng chủ động đóng | Không reconnect |
| Mạng hoặc server ngắt ngoài ý muốn | Có thể reconnect theo retry policy |
| Authentication hết hạn | Làm mới thông tin xác thực trước khi thử lại |
| Server trả STOMP ERROR | Phân tích lỗi; không retry vô hạn với lỗi cấu hình hoặc quyền |
| Shutdown trong lúc connect | Đóng session ngay khi callback nhận được kết nối và không subscribe |

Retry cần có giới hạn, jitter và khả năng hủy. Nếu hàng nghìn client reconnect cùng lúc sau khi server phục hồi, một khoảng chờ ngẫu nhiên giúp giảm đợt tải dồn.

## 13. Cleanup phía server qua SessionDisconnectEvent

Ở phía Spring server, `SessionDisconnectEvent` được phát khi STOMP session kết thúc. Sự kiện có thể xuất hiện khi client gửi DISCONNECT hoặc khi WebSocket session bị đóng.

Spring lưu ý rằng một session có thể tạo ra nhiều hơn một disconnect event trong một số trường hợp. Vì vậy, cleanup server phải idempotent.

Ví dụ:

~~~java
@Component
public class StompSessionCleanupListener {

    private final ConcurrentMap<String, Boolean> activeSessions =
            new ConcurrentHashMap<>();

    @EventListener
    public void onDisconnect(SessionDisconnectEvent event) {
        String sessionId = event.getSessionId();

        if (activeSessions.remove(sessionId) != null) {
            // Chỉ thực hiện cleanup nghiệp vụ một lần.
            // Ví dụ: đánh dấu user offline hoặc giải phóng presence.
        }
    }
}
~~~

Ví dụ trên giả định map được cập nhật khi session kết nối. Với hệ thống thực tế, thao tác cập nhật presence nên được thiết kế an toàn trước race giữa disconnect, reconnect và nhiều node. Không dùng event disconnect làm nguồn duy nhất cho trạng thái nghiệp vụ quan trọng nếu cần độ bền cao.

Các event liên quan khác:

- `SessionConnectEvent`: nhận STOMP CONNECT.
- `SessionConnectedEvent`: broker đã phản hồi CONNECTED.
- `SessionSubscribeEvent`: client gửi SUBSCRIBE.
- `SessionUnsubscribeEvent`: client gửi UNSUBSCRIBE.
- `SessionDisconnectEvent`: session kết thúc.

Các event này hữu ích cho giám sát và quản lý trạng thái, nhưng không thay thế việc lưu dữ liệu nghiệp vụ bền vững.

## 14. Receipts khi cần biết broker đã xử lý thao tác

STOMP có cơ chế RECEIPT để server/broker xác nhận đã xử lý frame có receipt header. Spring client có thể dùng `setAutoReceipt(true)` để tự thêm receipt header cho các thao tác send và subscribe tiếp theo, hoặc thêm header thủ công.

Để theo dõi receipt, cần cấu hình `TaskScheduler` và thời hạn receipt phù hợp. Broker cũng phải hỗ trợ receipt.

Lưu ý theo phiên bản:

- `send` và `subscribe` trả về `Receiptable` để theo dõi receipt.
- `Subscription` cũng là một `Receiptable`.
- Từ Spring 7.0, `unsubscribe()` trả về `Receiptable`; trong Spring 6.2, phương thức này trả về `void`.
- `StompSession.disconnect()` trả về `void`; không có handle `Receiptable` trực tiếp từ phương thức này.

Với shutdown thông thường, không cần chờ receipt của từng UNSUBSCRIBE nếu ứng dụng sẽ đóng toàn bộ session ngay sau đó. Nếu cần xác nhận một thao tác subscription đã được broker xử lý trong khi session vẫn mở, hãy thiết kế riêng theo khả năng của broker và phiên bản Spring.

Receipt chỉ xác nhận broker đã xử lý frame theo giao thức. Nó không chứng minh client subscriber đã hoàn thành nghiệp vụ.

## 15. Lỗi thường gặp và cách khắc phục

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Chỉ gọi `WebSocketStompClient.stop()` mà không quản lý session | Không có quy trình STOMP DISCONNECT rõ ràng cho từng session | Giữ session handle và gọi `disconnect()` trước khi dừng client |
| Gọi `disconnect()` cho mỗi subscription | Không đúng API; một session có thể có nhiều subscription | Dùng `Subscription.unsubscribe()` để hủy riêng; dùng `StompSession.disconnect()` để đóng toàn phiên |
| Đóng raw WebSocket trước khi gửi DISCONNECT | Broker có thể chỉ thấy kết nối mất đột ngột | Kết thúc qua `StompSession.disconnect()` khi đang dùng STOMP |
| Shutdown scheduler dùng chung khi một session đóng | Heartbeat/receipt của các session khác ngừng hoạt động | Để chủ sở hữu scheduler quản lý shutdown |
| Gọi `stompClient.stop()` khi một trong nhiều session kết thúc | Các thành phần khác mất client transport | Dừng client ở cấp owner khi mọi session đã đóng |
| Reconnect sau shutdown có chủ đích | Kết nối mới xuất hiện trong lúc ứng dụng đang dừng | Dùng cờ shutdown và hủy retry task |
| Tái sử dụng subscription handle cũ sau reconnect | Subscription không thuộc session mới | Tạo subscription mới cho session mới |
| Cleanup server không idempotent | Presence hoặc tài nguyên bị giải phóng nhiều lần | Kiểm tra trạng thái và xử lý disconnect lặp an toàn |
| Không quản lý HTTP client riêng của SockJS | Connection pool hoặc executor còn chạy sau shutdown | Đóng resource theo ownership và lifecycle của implementation |

## 16. Kiểm thử vòng đời và giải phóng tài nguyên

Một bộ kiểm thử nên bao gồm:

| Tình huống | Điều cần xác nhận |
|---|---|
| Hủy một subscription | Client không nhận destination đó nữa; session vẫn gửi/nhận bình thường |
| Disconnect toàn session | STOMP DISCONNECT được gửi và transport kết thúc |
| Đóng session hai lần | Cleanup an toàn, không tạo lỗi do giải phóng lặp |
| Hai session dùng chung client | Đóng một session không làm session còn lại ngừng hoạt động |
| Hai session dùng chung scheduler | Đóng một session không dừng heartbeat của session khác |
| Shutdown trong lúc connect | Session đến muộn được đóng và không tạo subscription |
| Transport lỗi | Session cũ được loại bỏ, reconnect có giới hạn |
| Shutdown khi đang reconnect | Retry task bị hủy, không tạo kết nối mới |
| Server nhận disconnect event lặp | Cleanup nghiệp vụ chỉ hoàn tất một lần |
| ApplicationContext đóng | Các bean Lifecycle dừng theo phase và tài nguyên riêng được giải phóng |

Trong kiểm thử tải, theo dõi số session đang hoạt động, số subscription, số task heartbeat, số thread, số kết nối TCP/HTTP, connection pool, heap và thời gian shutdown. Một client được coi là đóng đúng khi không còn session hoạt động ngoài dự kiến, không còn retry task, và các tài nguyên thuộc quyền sở hữu của client đã được dừng.

## 17. Checklist trước khi đưa vào production

- [ ] Mỗi session đang hoạt động có owner rõ ràng.
- [ ] Handle subscription được lưu nếu cần hủy độc lập.
- [ ] Shutdown ngừng gửi message và reconnect trước khi đóng session.
- [ ] Dùng `StompSession.disconnect()` để kết thúc toàn bộ phiên STOMP.
- [ ] Chỉ gọi `WebSocketStompClient.stop()` ở cấp owner của client.
- [ ] Scheduler dùng chung không bị đóng bởi một session riêng lẻ.
- [ ] HTTP client, connection pool và executor tùy chỉnh được đóng theo ownership.
- [ ] Reconnect tạo session và subscription mới.
- [ ] Cleanup phía server xử lý disconnect event lặp an toàn.
- [ ] Có kiểm thử shutdown trong lúc connect, lúc đang nhận message và lúc transport bị lỗi.
- [ ] Đã kiểm tra API theo đúng phiên bản Spring Framework của dự án.

## Tài liệu tham khảo

- [Spring Framework — STOMP Client](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/client.html)
- [Spring Framework — Application Context Events](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/application-context-events.html)
- [Spring Framework Javadoc — StompSession](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/stomp/StompSession.html)
- [Spring Framework Javadoc — StompSession.Subscription](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/stomp/StompSession.Subscription.html)
- [Spring Framework Javadoc — WebSocketStompClient](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/socket/messaging/WebSocketStompClient.html)
- [Spring Framework Javadoc — WebSocketSession](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/socket/WebSocketSession.html)
