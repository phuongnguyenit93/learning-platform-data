# Kết nối lại, đăng ký lại và khôi phục trạng thái ứng dụng

## 1. Vì sao reconnect chưa đủ?

Trong ứng dụng STOMP, kết nối WebSocket và STOMP session có vòng đời riêng. Khi mạng chập chờn, trình duyệt chuyển mạng, máy chủ khởi động lại hoặc broker tạm ngừng, kết nối hiện tại có thể bị đóng. Client cần thiết lập một STOMP session mới để tiếp tục trao đổi message.

Tuy nhiên, **kết nối lại thành công không có nghĩa trạng thái ứng dụng đã được khôi phục**. Một session mới không tự mang theo:

- Các subscription của session cũ.
- Những message đã phát trong khoảng thời gian client offline.
- Trạng thái nghiệp vụ mà client đang hiển thị.
- Các lệnh gửi đi nhưng client chưa biết server đã xử lý hay chưa.
- Vị trí cuối cùng mà client đã xử lý trong một luồng sự kiện.

Vì vậy cần xử lý ba việc riêng:

1. **Reconnect**: tạo lại transport và STOMP session sau khi mất kết nối.
2. **Resubscribe**: đăng ký lại toàn bộ destination cần nghe sau khi broker xác nhận session mới.
3. **State recovery**: đồng bộ lại dữ liệu, phát hiện khoảng trống sự kiện, loại message trùng và xử lý các lệnh đang chờ.

Một client chỉ hiển thị trạng thái “connected” sau khi STOMP CONNECTED là chưa đủ. Với ứng dụng có dữ liệu quan trọng, nên có thêm trạng thái “synchronizing” và chỉ chuyển sang “ready” sau khi hoàn tất đồng bộ.

## 2. Phân biệt các tầng kết nối và sự cố

Một luồng STOMP over WebSocket thường có các tầng:

| Tầng | Thành phần | Sự cố có thể gặp |
|---|---|---|
| Mạng | Wi-Fi, mobile network, proxy, load balancer | Mất mạng, timeout, idle connection bị đóng. |
| WebSocket | Browser WebSocket hoặc SockJS transport | Socket đóng, handshake lỗi, proxy ngắt kết nối. |
| STOMP | CONNECT, CONNECTED, SUBSCRIBE, MESSAGE | Broker gửi ERROR, heartbeat timeout, session bị kết thúc. |
| Ứng dụng | Store, cache, event handler, API đồng bộ | Dữ liệu cũ, mất event, event trùng hoặc sai thứ tự. |

Heartbeat giúp phát hiện kết nối không còn phản hồi; nó không lưu lại message bị bỏ lỡ và không tự phục hồi trạng thái nghiệp vụ.

Cũng cần phân biệt hai loại reconnect:

- **Reconnect của client**: client tạo WebSocket/STOMP session mới và phải subscribe lại.
- **Reconnect của broker relay**: trong cấu hình Spring dùng broker relay, Spring tự khôi phục system connection tới broker khi có thể. Các client connection không tự được khôi phục thay cho trình duyệt; client phải thực hiện reconnect riêng.

Spring có các sự kiện như `SessionConnectEvent`, `SessionConnectedEvent` và `SessionDisconnectEvent` để theo dõi vòng đời session. `SessionConnectedEvent` được phát sau khi broker gửi CONNECTED. `SessionDisconnectEvent` đôi khi được phát nhiều lần cho cùng session, vì vậy thao tác cleanup ở server phải idempotent.

## 3. Tự động reconnect với STOMP.js

Thư viện `@stomp/stompjs` có cơ chế reconnect tích hợp. Thuộc tính `reconnectDelay` là thời gian chờ giữa các lần thử kết nối, tính bằng mili giây; mặc định là 5.000 ms. Đặt bằng 0 để tắt tự động reconnect.

Có thể dùng exponential backoff để tăng dần thời gian chờ khi broker hoặc mạng chưa sẵn sàng:

~~~javascript
import { Client, ReconnectionTimeMode } from "@stomp/stompjs";

const client = new Client({
    brokerURL: "wss://app.example.com/ws",
    reconnectDelay: 1000,
    reconnectTimeMode: ReconnectionTimeMode.EXPONENTIAL,
    maxReconnectDelay: 30000,
    connectionTimeout: 8000,
    heartbeatIncoming: 10000,
    heartbeatOutgoing: 10000
});

client.activate();
~~~

Với cấu hình này, client bắt đầu thử lại sau khoảng 1 giây; exponential backoff tăng thời gian chờ giữa các lần thử và giới hạn ở 30 giây. Điều chỉnh các giá trị theo thời gian phục hồi của hệ thống và giới hạn của broker. Nếu nhiều client cùng mất kết nối, backoff giúp giảm tải do tất cả cùng reconnect liên tục. Nếu cần jitter để tránh các client thử lại đồng thời, có thể bổ sung chính sách phân tán thời điểm thử ở tầng ứng dụng.

Không nên tạo một đối tượng `Client` mới sau mỗi lần socket đóng. Hãy quản lý một client instance cho vòng đời của component hoặc ứng dụng; để thư viện điều khiển vòng reconnect. Tạo nhiều instance có thể sinh nhiều kết nối và subscription trùng.

## 4. Subscribe lại trong onConnect

Đây là quy tắc quan trọng nhất của STOMP.js: callback `onConnect` được gọi sau **mỗi lần kết nối STOMP thành công**, gồm kết nối ban đầu và các lần reconnect. Thư viện không tự đăng ký lại các destination đã subscribe trong session trước. Vì vậy, hãy đặt toàn bộ thao tác `subscribe` cần thiết trong `onConnect`.

~~~javascript
import { Client } from "@stomp/stompjs";

const subscriptions = new Map();

const client = new Client({
    brokerURL: "wss://app.example.com/ws",
    reconnectDelay: 5000,
    heartbeatIncoming: 10000,
    heartbeatOutgoing: 10000,

    onConnect: () => {
        setConnectionStatus("synchronizing");

        // Đây là STOMP session mới. Tạo lại mọi subscription cần dùng.
        subscriptions.clear();

        const ordersSubscription = client.subscribe(
            "/user/queue/orders",
            (message) => {
                handleOrderMessage(JSON.parse(message.body));
            }
        );

        subscriptions.set("orders", ordersSubscription);

        const alertsSubscription = client.subscribe(
            "/user/queue/alerts",
            (message) => {
                handleAlertMessage(JSON.parse(message.body));
            }
        );

        subscriptions.set("alerts", alertsSubscription);

        // Sau khi đã đăng ký nhận event, đồng bộ lại dữ liệu.
        void synchronizeApplicationState();
    },

    onWebSocketClose: () => {
        subscriptions.clear();
        setConnectionStatus("reconnecting");
    },

    onStompError: (frame) => {
        reportBrokerError(frame.headers["message"], frame.body);
    }
});

client.activate();
~~~

Các hàm `setConnectionStatus`, `handleOrderMessage`, `handleAlertMessage`, `synchronizeApplicationState` và `reportBrokerError` là hàm nghiệp vụ của ứng dụng, cần được triển khai theo store và API thực tế.

Trong ví dụ, subscription handle được giữ trong Map để có thể hủy hoặc thay đổi subscription khi cần. Khi WebSocket đóng, các handle thuộc session cũ không còn đại diện cho subscription đang hoạt động. Sau CONNECTED mới, đăng ký lại bằng handle mới.

Không gọi `subscribe` đồng thời ở nhiều nơi như lúc khởi tạo component, callback reconnect và callback khôi phục state. Chọn một nơi sở hữu việc đăng ký, thường là `onConnect`, để tránh duplicate subscription.

## 5. Theo dõi trạng thái kết nối

Nên biểu diễn trạng thái kết nối rõ ràng trong UI và logic ứng dụng:

| Trạng thái | Ý nghĩa | Hành vi phù hợp |
|---|---|---|
| `connecting` | Đang tạo kết nối ban đầu. | Hiển thị đang kết nối; chưa gửi lệnh phụ thuộc STOMP. |
| `connected` | STOMP CONNECTED đã nhận. | Có thể đăng ký subscription; dữ liệu có thể chưa đồng bộ. |
| `synchronizing` | Subscription đã tạo và ứng dụng đang khôi phục dữ liệu. | Buffer event; tránh hiển thị trạng thái đã sẵn sàng quá sớm. |
| `ready` | Dữ liệu nền đã đồng bộ tới cursor/version đã biết. | Cho phép luồng nghiệp vụ realtime hoạt động bình thường. |
| `reconnecting` | Socket/session bị mất và client sẽ thử kết nối lại. | Hiển thị trạng thái tạm thời; giữ dữ liệu đã có nhưng đánh dấu có thể cũ. |
| `sync-error` | Kết nối có thể đã lên nhưng đồng bộ dữ liệu thất bại. | Retry đồng bộ hoặc yêu cầu người dùng thử lại; không giả vờ dữ liệu đã mới. |
| `closed` | Ứng dụng chủ động dừng client. | Không tiếp tục reconnect. |

STOMP.js cung cấp `onConnect`, `onDisconnect`, `onWebSocketClose`, `onWebSocketError`, `onHeartbeatLost` và `onChangeState`. Dùng callback phù hợp với sự kiện cần theo dõi. `onDisconnect` phản ánh DISCONNECT thành công; khi socket bị ngắt đột ngột, không phải lúc nào client cũng nhận được DISCONNECT receipt, do đó cần theo dõi `onWebSocketClose`.

Không đánh đồng WebSocket mở với STOMP session sẵn sàng. Hãy đợi broker gửi CONNECTED và callback `onConnect` chạy trước khi gửi message hoặc đăng ký subscription.

## 6. Heartbeat và phát hiện kết nối chết

STOMP heartbeat giúp hai bên phát hiện connection không còn hoạt động. STOMP.js có hai thuộc tính chính:

- `heartbeatOutgoing`: khoảng gửi heartbeat từ client tới server.
- `heartbeatIncoming`: khoảng client kỳ vọng nhận heartbeat từ server.

Giá trị mặc định của STOMP.js hiện là 10.000 ms cho mỗi hướng; đặt 0 để tắt hướng tương ứng. Heartbeat chỉ được trao đổi khi hai bên thương lượng và hỗ trợ heartbeat theo STOMP version.

~~~javascript
const client = new Client({
    brokerURL: "wss://app.example.com/ws",
    heartbeatOutgoing: 10000,
    heartbeatIncoming: 10000,
    heartbeatToleranceMultiplier: 2,

    onHeartbeatLost: () => {
        setConnectionStatus("reconnecting");
    }
});
~~~

Không đặt heartbeat quá ngắn nếu hệ thống có nhiều client, vì mỗi connection cần xử lý thêm tác vụ định kỳ. Proxy hoặc load balancer cũng có idle timeout riêng; cấu hình heartbeat phải phù hợp với thời gian timeout của các tầng mạng.

Trình duyệt có thể hạn chế timer khi tab ở background. STOMP.js hỗ trợ heartbeat strategy dùng Web Worker trong môi trường trình duyệt để cải thiện độ ổn định của heartbeat khi tab nền. Đây là lựa chọn vận hành, không thay thế reconnect và state recovery.

Heartbeat có thể phát hiện sự cố nhanh hơn việc chỉ chờ TCP timeout, nhưng không đảm bảo rằng mọi event trong khoảng mất kết nối sẽ được phát lại.

## 7. Làm mới token trước mỗi lần kết nối

Một reconnect có thể diễn ra sau khi access token hết hạn. Nếu ứng dụng xác thực STOMP CONNECT bằng token trong header, dùng `beforeConnect` để lấy token mới trước mỗi lần kết nối:

~~~javascript
const client = new Client({
    brokerURL: "wss://app.example.com/ws",
    reconnectDelay: 5000,

    beforeConnect: async () => {
        const token = await refreshAccessToken();

        client.connectHeaders = {
            Authorization: "Bearer " + token
        };
    },

    onConnect: () => {
        registerSubscriptions();
    }
});
~~~

Đoạn này giả định backend có interceptor hoặc cơ chế xác thực STOMP CONNECT để đọc header Authorization. Với ứng dụng Spring xác thực qua HTTP handshake và cookie/session, cần làm mới HTTP session hoặc cookie theo cơ chế đăng nhập của ứng dụng; header STOMP CONNECT không phải HTTP header của WebSocket handshake.

Không đưa token hoặc mật khẩu vào URL vì URL thường xuất hiện trong log, lịch sử trình duyệt và hệ thống giám sát. Không ghi log toàn bộ CONNECT headers hoặc raw STOMP frame trong production nếu có thông tin nhạy cảm.

Nếu làm mới token thất bại vì người dùng đã đăng xuất hoặc refresh token hết hạn, dừng reconnect theo chính sách xác thực và chuyển ứng dụng về trạng thái cần đăng nhập lại. Tránh thử lại vô hạn với credential đã hết hiệu lực.

## 8. Khôi phục trạng thái ứng dụng từ snapshot

Subscription chỉ cung cấp message mới sau khi nó hoạt động. Nó không tự gửi lại toàn bộ lịch sử đã bỏ lỡ. Với dữ liệu hiển thị như danh sách đơn hàng, thông báo, số dư hoặc trạng thái tác vụ, nên có API snapshot để tải trạng thái hiện tại từ server.

Quy trình cơ bản:

1. Sau khi STOMP CONNECTED, đăng ký subscription cần thiết.
2. Nếu broker hỗ trợ STOMP RECEIPT cho SUBSCRIBE, chờ receipt xác nhận subscription đã được broker xử lý.
3. Trong lúc tải snapshot, tạm buffer các event mới nhận được.
4. Gọi API lấy snapshot có kèm version hoặc sequence number.
5. Thay state local bằng snapshot.
6. Áp dụng các event trong buffer có sequence lớn hơn version của snapshot, theo đúng thứ tự.
7. Nếu phát hiện sequence bị thiếu, yêu cầu server replay event từ cursor cuối hoặc tải snapshot mới.
8. Chỉ đánh dấu ứng dụng ready khi state đã đồng bộ.

Ví dụ snapshot API có thể trả:

~~~json
{
  "version": 1842,
  "orders": [
    {
      "id": "ORD-1001",
      "status": "SHIPPED"
    }
  ]
}
~~~

Ví dụ event có thể mang sequence và id riêng:

~~~json
{
  "eventId": "evt-7f3a",
  "sequence": 1843,
  "type": "ORDER_STATUS_CHANGED",
  "orderId": "ORD-1001",
  "status": "DELIVERED"
}
~~~

Version trong snapshot và sequence của event phải thuộc cùng một phạm vi thứ tự mà server định nghĩa, chẳng hạn theo user, tenant hoặc stream. Không dùng timestamp client làm thứ tự tuyệt đối vì đồng hồ giữa các máy có thể lệch.

STOMP RECEIPT có thể xác nhận broker đã xử lý frame SUBSCRIBE nếu broker hỗ trợ. Receipt không chứng minh dữ liệu nghiệp vụ đã được đồng bộ và cũng không thay thế snapshot/replay. Nếu broker không hỗ trợ receipt, cần một giao thức đồng bộ ứng dụng phù hợp và phải hiểu rõ giới hạn nhất quán của nó.

## 9. Chống event trùng và sai thứ tự

Sau reconnect, ứng dụng có thể nhận lại event vì broker redelivery, retry của producer hoặc cơ chế replay phía server. Với event có ý nghĩa nghiệp vụ, nên thiết kế consumer idempotent.

Một event nên có tối thiểu:

- `eventId` duy nhất để nhận diện event.
- `sequence` hoặc `version` để xác định thứ tự trong một stream.
- `aggregateId` hoặc khóa thực thể để biết event tác động tới đối tượng nào.
- `type` và payload có schema rõ ràng.

Nguyên tắc xử lý:

1. Bỏ qua event có sequence nhỏ hơn hoặc bằng sequence cuối đã áp dụng.
2. Nếu sequence kế tiếp đúng bằng sequence hiện tại cộng một, áp dụng event.
3. Nếu sequence nhảy cóc, dừng áp dụng luồng đó và yêu cầu replay hoặc snapshot.
4. Nếu eventId đã được xử lý, không thực hiện side effect lần nữa.
5. Cập nhật cursor/version sau khi thay đổi state thành công.

Nếu nhiều aggregate có sequence riêng, không so sánh sequence của hai aggregate khác nhau. Cursor phải gắn với đúng stream hoặc partition mà server cam kết thứ tự.

## 10. Khôi phục lệnh gửi đi chưa rõ kết quả

Một tình huống khó là client gửi STOMP SEND rồi socket bị đóng trước khi nhận được phản hồi. Client không biết server đã nhận lệnh hay chưa. Gửi lại ngay có thể thực hiện thao tác hai lần.

Với lệnh có tác động nghiệp vụ như tạo đơn, thanh toán, gửi yêu cầu hoặc thay đổi trạng thái:

- Gắn một commandId/idempotency key duy nhất vào mỗi lệnh.
- Lưu lệnh đang chờ ở client nếu cần phục hồi sau reload.
- Server lưu kết quả xử lý theo commandId và từ chối thực hiện side effect lần hai.
- Sau reconnect, client hỏi trạng thái commandId trước khi quyết định gửi lại.
- Chỉ xóa lệnh khỏi outbox khi server xác nhận kết quả nghiệp vụ.

STOMP RECEIPT chỉ xác nhận broker đã xử lý frame tương ứng theo giao thức; nó không tự chứng minh transaction nghiệp vụ trong database đã commit hoặc downstream consumer đã hoàn tất. Nếu cần bảo đảm kết quả nghiệp vụ, server phải trả acknowledgement ở tầng ứng dụng có commandId và trạng thái rõ ràng.

Không thể đạt exactly-once processing chỉ bằng cách reconnect và resubscribe. Thực tế thường cần kết hợp at-least-once delivery, idempotency và lưu cursor bền vững.

## 11. Subscription receipt và thời điểm đánh dấu ready

STOMP hỗ trợ header receipt cho một số frame như SUBSCRIBE và SEND. STOMP.js cho phép đăng ký callback bằng `watchForReceipt` rồi gửi frame với header `receipt`:

~~~javascript
const receiptId = "orders-subscription-" + Date.now();

client.watchForReceipt(receiptId, () => {
    console.log("Broker đã xác nhận SUBSCRIBE");
    // Có thể bắt đầu bước đồng bộ snapshot ở đây.
});

client.subscribe(
    "/topic/orders",
    handleOrderMessage,
    { receipt: receiptId }
);
~~~

Đăng ký watcher trước khi gửi SUBSCRIBE để tránh bỏ lỡ receipt đến sớm. Hỗ trợ receipt và ý nghĩa xử lý chi tiết còn phụ thuộc broker. Nếu dùng broker không hỗ trợ receipt, không giả lập rằng subscription đã được xác nhận chỉ vì hàm subscribe đã trả về.

Ngay cả khi đã nhận receipt, ứng dụng vẫn cần hoàn thành snapshot/replay và xử lý event buffer trước khi chuyển trạng thái sang ready.

## 12. Kết thúc kết nối có chủ đích

Có hai trường hợp cần phân biệt:

- **Mất kết nối ngoài ý muốn**: mạng hoặc server lỗi; client nên tiếp tục reconnect nếu ứng dụng còn hoạt động.
- **Đóng có chủ đích**: người dùng đăng xuất, đóng ứng dụng hoặc component bị hủy; cần dừng reconnect và giải phóng tài nguyên.

Với STOMP.js, gọi `deactivate()` để dừng vòng reconnect và đóng connection đang hoạt động:

~~~javascript
async function logoutMessaging() {
    setConnectionStatus("closed");
    subscriptions.clear();
    await client.deactivate();
}
~~~

Không gọi `deactivate()` chỉ vì nhận được `onWebSocketClose` trong một sự cố mạng tạm thời; điều đó sẽ chấm dứt cơ chế tự reconnect. Khi cần kích hoạt lại sau đó, gọi `activate()` theo vòng đời ứng dụng.

Nếu dùng React hoặc framework component, hãy tạo client trong một owner duy nhất, đăng ký callback một lần và gọi deactivate khi owner bị hủy. Tránh mỗi lần render lại tạo thêm client hoặc subscription.

## 13. Phía Spring: theo dõi session và cleanup idempotent

Server Spring có thể theo dõi các event của STOMP session:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.messaging.SessionConnectedEvent;
import org.springframework.web.socket.messaging.SessionDisconnectEvent;

@Component
public class StompSessionLifecycleListener {

    @EventListener
    public void onConnected(SessionConnectedEvent event) {
        // Broker đã trả CONNECTED; session STOMP sẵn sàng.
        // Có thể cập nhật presence hoặc metric.
    }

    @EventListener
    public void onDisconnected(SessionDisconnectEvent event) {
        // Cleanup phải idempotent vì event có thể xuất hiện nhiều lần.
        // Lấy session id từ message headers nếu cần.
    }
}
~~~

Không xem một event disconnect là bằng chứng người dùng đã đăng xuất hoàn toàn. Một user có thể có nhiều session ở các tab hoặc thiết bị. Quản lý presence nên đếm hoặc theo dõi session theo user và chỉ đánh dấu offline khi không còn session hợp lệ nào. Cleanup cần chịu được event lặp, session timeout và reconnect nhanh.

## 14. Kiểm thử reconnect và state recovery

Không chỉ kiểm tra trường hợp server khởi động bình thường. Hãy mô phỏng các tình huống sau:

| Tình huống | Kết quả cần xác nhận |
|---|---|
| Mạng bị ngắt rồi khôi phục | Client reconnect và callback onConnect chạy lại. |
| Broker restart | Client nhận biết session mất, reconnect sau khi broker sẵn sàng. |
| WebSocket proxy timeout | Heartbeat hoặc close event kích hoạt reconnect. |
| Token hết hạn trong lúc offline | Token được làm mới hoặc client chuyển về trạng thái yêu cầu đăng nhập. |
| Nhiều lần reconnect liên tiếp | Không tạo duplicate subscriptions hoặc nhiều Client instance. |
| Event phát trong lúc client offline | Snapshot/replay đưa state về đúng version mới nhất. |
| Event bị gửi trùng | Idempotency ngăn side effect lặp. |
| Event đến sai thứ tự hoặc sequence bị thiếu | Client phát hiện gap và yêu cầu đồng bộ lại. |
| SEND bị ngắt trước khi có kết quả | CommandId giúp xác định lệnh đã xử lý hay cần gửi lại. |
| Logout khi đang reconnect | deactivate dừng các lần thử tiếp theo. |
| Nhiều tab cùng đăng nhập | Mỗi session subscribe độc lập; presence và broadcast đúng yêu cầu. |

Khi kiểm tra, ghi lại timestamp, trạng thái client, STOMP session id, số lần reconnect, số subscription hiện tại, cursor/version và commandId. Không ghi access token, passcode hoặc payload nhạy cảm vào log.

## 15. Quy trình recovery tham khảo

~~~mermaid
flowchart TD
    A["Mất WebSocket hoặc heartbeat"] --> B["Đánh dấu reconnecting"]
    B --> C["Client thử kết nối lại theo backoff"]
    C --> D{"Nhận STOMP CONNECTED?"}
    D -->|Chưa| C
    D -->|Rồi| E["Đăng ký lại tất cả subscription"]
    E --> F["Chờ SUBSCRIBE receipt nếu broker hỗ trợ"]
    F --> G["Buffer event mới và tải snapshot/cursor"]
    G --> H{"Có sequence gap?"}
    H -->|Có| I["Replay event hoặc tải snapshot mới"]
    I --> H
    H -->|Không| J["Áp dụng event mới, loại event trùng"]
    J --> K["Đối chiếu command đang chờ"]
    K --> L["Đánh dấu ready"]
~~~

Thứ tự này giúp tách rõ transport recovery và business recovery. Nếu broker không hỗ trợ receipt, bước F cần thay bằng cơ chế đồng bộ ứng dụng đã thiết kế; không bỏ qua việc xác định thời điểm subscription thực sự có hiệu lực.

## 16. Những lỗi thường gặp

- **Chỉ reconnect mà không subscribe lại:** STOMP session mới chưa có subscription. Đưa việc đăng ký vào callback chạy sau mỗi CONNECTED.
- **Subscribe ở nhiều callback:** một destination bị đăng ký nhiều lần và event handler chạy trùng. Tập trung quyền sở hữu subscription ở một nơi.
- **Đánh dấu connected ngay khi WebSocket mở:** broker chưa gửi CONNECTED hoặc state chưa đồng bộ. Phân biệt connecting, connected, synchronizing và ready.
- **Giả định message offline sẽ tự phát lại:** subscription STOMP thông thường không phải event log. Dùng snapshot hoặc replay có cursor.
- **Áp dụng event mà không kiểm tra version:** event trùng hoặc đến sai thứ tự có thể làm state lùi hoặc sai. Dùng eventId và sequence.
- **Gửi lại command chưa rõ kết quả:** server có thể đã xử lý trước khi socket đóng. Dùng idempotency key và truy vấn trạng thái command.
- **Không refresh token:** reconnect lặp lại với credential hết hạn. Làm mới credential trước mỗi lần thử nếu kiến trúc xác thực yêu cầu.
- **Dùng deactivate khi mạng tạm thời mất:** client không còn tự reconnect. Chỉ deactivate khi ứng dụng chủ động đóng client.
- **Cleanup không idempotent:** server có thể nhận nhiều disconnect event cho cùng session. Thiết kế cleanup chịu được gọi lặp.

## 17. Ghi nhớ

Reconnect tạo một STOMP session mới; resubscribe khôi phục luồng message; snapshot/replay và cursor khôi phục trạng thái nghiệp vụ. Với STOMP.js, cấu hình reconnectDelay và heartbeat, đặt mọi subscription trong onConnect, theo dõi onWebSocketClose và dùng deactivate cho đóng có chủ đích. Để tránh mất hoặc xử lý trùng event, server cần cung cấp snapshot hoặc replay có version/sequence, còn client cần idempotency và commandId cho các lệnh chưa rõ kết quả. Chỉ đánh dấu ứng dụng ready sau khi subscription và dữ liệu đã được đồng bộ.

## Tài liệu tham khảo

- [STOMP.js — Using StompJs](https://stomp-js.github.io/guide/stompjs/using-stompjs-v5.html)
- [STOMP.js — Client API](https://stomp-js.github.io/api-docs/latest/classes/Client.html)
- [Spring Framework — STOMP Application Context Events](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/application-context-events.html)
- [Spring Framework — STOMP Client](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/client.html)