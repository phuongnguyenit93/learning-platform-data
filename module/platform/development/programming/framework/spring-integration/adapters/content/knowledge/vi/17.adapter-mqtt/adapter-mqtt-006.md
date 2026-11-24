# Automatic reconnect và completion timeout

## 1. Bối cảnh: kết nối MQTT không phải lúc nào cũng ổn định

Ứng dụng Spring Integration có thể gửi lệnh điều khiển thiết bị qua MQTT, nhận telemetry từ broker và đẩy dữ liệu sang database, HTTP, JMS, Kafka hoặc hệ thống khác. Khi một broker restart, đường mạng gián đoạn, certificate hết hạn hay downstream quá tải, hai câu hỏi xuất hiện ngay:

1. **Làm thế nào MQTT client khôi phục kết nối mà không cần khởi động lại toàn bộ ứng dụng?**
2. **Một thao tác kết nối, subscribe hoặc publish được phép chờ bao lâu trước khi trả về lỗi/timeout?**

Đó là phạm vi của **automatic reconnect** và **completion timeout**. Chúng liên quan nhưng không phải hai tên của cùng một cơ chế:

- **Automatic reconnect** cho phép client tìm cách thiết lập lại kết nối khi một kết nối MQTT bị mất.
- **Completion timeout** giới hạn thời gian chờ hoàn tất một thao tác do endpoint/client thực hiện; thao tác publish bị timeout không có nghĩa broker chắc chắn chưa nhận message.

Bài này nằm trong chương **Adapter MQTT** của module **SPRING_INTEGRATION_ADAPTERS**. Module hướng tới tích hợp hệ thống bên ngoài bằng inbound/outbound adapter, gateway, poller và `MessageChannel`, với các ví dụ file, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu; đồng thời yêu cầu kiểm soát hợp đồng message, lỗi và vòng đời kết nối. Với MQTT, Spring Integration sử dụng MQTT client để kết nối broker, sau đó chuyển payload/headers vào hoặc ra `IntegrationFlow`.

Sau bài, người học có thể:

- Phân biệt `MqttConnectOptions.setAutomaticReconnect(true)` của Eclipse Paho với cơ chế `setRecoveryInterval(...)` của inbound adapter.
- Phân biệt **connection timeout**, **keepalive interval**, **completion timeout**, **recovery interval**, **business ACK timeout**.
- Cấu hình inbound/outbound MQTT adapters bằng factory và Client ID phù hợp.
- Giải thích lỗi **mất kết nối ban đầu**, **đang publish thì mất mạng**, **client reconnect nhưng session không còn**, **publish completion timeout**.
- Thiết kế replay, idempotency, backpressure và trạng thái publish không chắc chắn.
- Kiểm thử cấu hình và flow không có broker; kiểm tra thực với broker bị ngắt, chậm, từ chối authentication và restart.
- Theo dõi kết nối, publish latency, lỗi reconnect, queue backlog và trạng thái ứng dụng.

**Giới hạn:** ví dụ sử dụng Spring Integration MQTT với Eclipse Paho **MQTT v3 API**, `MqttConnectOptions` và MQTT 3.1.1. Hành vi callback, event và recovery khi bật nhiều cơ chế cùng lúc có thể thay đổi theo phiên bản Spring Integration/Paho; cần kiểm thử trên các phiên bản của dự án, không suy từ một ví dụ thành cam kết cho mọi hệ thống.

## 2. Vị trí của reconnect và timeout trong kiến trúc

~~~mermaid
flowchart LR
    SRC["Business service / inbound adapters"]
    OUT["mqtt.commands.out<br/>MessageChannel"]
    HANDLER["MqttPahoMessageHandler<br/>outbound"]
    CLIENT["Paho MQTT client<br/>connect / publish / reconnect"]
    BROKER[("MQTT broker")]
    SUB["Subscriber / thiết bị"]
    IN["MqttPahoMessageDrivenChannelAdapter<br/>inbound"]
    CH["mqtt.telemetry.in<br/>MessageChannel"]
    FLOW["Validation / database flow"]
    SRC --> OUT --> HANDLER --> CLIENT
    CLIENT -->|"PUBLISH QoS + topic"| BROKER --> SUB
    BROKER -->|"DELIVER"| IN --> CH --> FLOW
    CLIENT -. "connection lost" .-> CLIENT
    IN -. "endpoint recovery" .-> IN
~~~

Một message từ hệ thống nghiệp vụ đi qua nhiều ranh giới, và timeout ở từng ranh giới mang ý nghĩa khác nhau:

| Ranh giới | Thành phần kiểm soát | Câu hỏi cần trả lời |
| --- | --- | --- |
| Mở kết nối TCP/TLS/MQTT | Paho `MqttConnectOptions` | Client có thiết lập được connection trong thời gian cho phép không? |
| Duy trì kết nối | MQTT keepalive, client network và broker | Khi không có lưu lượng ứng dụng, hai phía còn phát hiện mất kết nối được không? |
| Mất kết nối rồi khôi phục | Paho automatic reconnect và/hoặc adapter recovery | Ai chủ động reconnect? Lần thử tiếp theo khi nào? |
| Đăng ký subscribe hoặc publish | Paho token, adapter completion timeout | Thao tác đã hoàn tất trong giới hạn thời gian chờ chưa? |
| Bàn giao vào Spring channel | `DirectChannel`/`QueueChannel`/`ExecutorChannel` | Message đã được consumer nhận, đang chờ hay bị từ chối? |
| Side effect ở đích | Database transaction, HTTP/JMS/Kafka handler | Nghiệp vụ đã hoàn tất hay chỉ mới bắt đầu? |
| Phản hồi từ thiết bị | ACK topic và business correlation | Thiết bị đã thực hiện lệnh nào, kết quả gì và khi nào? |

**Không gọi `completionTimeout=5000` là “thời gian broker được offline tối đa 5 giây”.** Nó giới hạn một thao tác chờ cụ thể, không bắt broker khôi phục trong thời gian đó.

## 3. Bảng phân biệt năm loại thời gian thường gặp

| Tham số | Ví dụ API/cấu hình | Đơn vị | Ý nghĩa chính |
| --- | --- | --- | --- |
| **Connection timeout** | `MqttConnectOptions.setConnectionTimeout(10)` | Giây | Thời gian tối đa dành cho việc thiết lập một kết nối theo Paho. |
| **Keepalive interval** | `MqttConnectOptions.setKeepAliveInterval(30)` | Giây | Khoảng hoạt động MQTT dùng để phát hiện kết nối không phản hồi theo giao thức. |
| **Recovery interval** | `MqttPahoMessageDrivenChannelAdapter.setRecoveryInterval(10000)` | Mili giây | Khoảng recovery/retry của inbound endpoint theo API Spring Integration. |
| **Completion timeout** | `MqttPahoMessageHandler.setCompletionTimeout(5000)` | Mili giây | Giới hạn chờ hoàn tất thao tác publish đồng bộ ở outbound handler. |
| **Business ACK timeout** | Ứng dụng tự đặt, ví dụ 30 giây | Theo hợp đồng | Thời gian chờ subscriber xác nhận thực hiện command nghiệp vụ. |

Hai dòng hay bị nhầm nhất:

~~~java
options.setConnectionTimeout(10);   // 10 GIÂY
handler.setCompletionTimeout(5000);  // 5000 MILI GIÂY = 5 giây
~~~

Khi cấu hình cũng cần hiểu:

- `connectionTimeout` không phải timeout cho một HTTP request hoặc cho Spring `MessageChannel.send(...)`.
- `keepAliveInterval` là tín hiệu về **connection**, không phải heartbeat nghiệp vụ của cảm biến.
- `recoveryInterval` điều khiển cách endpoint tổ chức việc thử khôi phục; nó không nói message đang nằm ở đâu.
- `completionTimeout` không tạo exactly-once và không bảo đảm bên nhận xử lý.
- Business ACK timeout có thể dài hơn và độc lập với thời hạn publish MQTT.

## 4. Automatic reconnect của Eclipse Paho

Eclipse Paho MQTT v3 cung cấp tùy chọn:

~~~java
MqttConnectOptions options = new MqttConnectOptions();
options.setServerURIs(new String[] {
        "tcp://localhost:1883"
});
options.setConnectionTimeout(10);
options.setKeepAliveInterval(30);
options.setAutomaticReconnect(true);
~~~

Khi một client **đã có kết nối rồi bị mất kết nối ngoài ý muốn**, Paho có thể tự thử kết nối lại theo cơ chế backoff/giám sát nội bộ của thư viện. Application không cần tự chạy vòng lặp gọi `connect()` trên một client đang được Paho quản lý automatic reconnect.

### 4.1. Automatic reconnect giúp những gì?

- Phục hồi sau mạng gián đoạn tạm thời hoặc broker restart trong các điều kiện thư viện hỗ trợ.
- Giảm nhu cầu viết vòng lặp reconnect thủ công ở lớp nghiệp vụ.
- Có thể kết hợp nhiều broker URI để thử endpoint phù hợp theo khả năng client và topology broker.
- Cho phép adapter tiếp tục làm việc khi client được khôi phục và các subscription/session cần thiết vẫn hợp lệ.

### 4.2. Automatic reconnect không bảo đảm những gì?

1. **Không mặc nhiên xử lý mọi lỗi kết nối ban đầu.** Nếu chưa từng kết nối thành công, ứng dụng vẫn phải xem xét chính sách khởi động/retry của endpoint. Tính năng automatic reconnect chủ yếu nhắm đến *connection lost* sau khi kết nối.
2. **Không sửa được credential sai hoặc ACL bị từ chối.** Lặp lại CONNECT với mật khẩu không hợp lệ không phải chiến lược tự chữa lỗi.
3. **Không tự giữ mọi message outbound khi broker offline.** Muốn buffering/offline queue phải có cấu hình và giới hạn riêng, đồng thời phải xác định độ bền khi restart.
4. **Không bảo đảm subscriber vẫn còn subscription như cũ** khi session đã bị xóa, Client ID thay đổi hoặc broker không chia sẻ session khi failover.
5. **Không rollback side effect downstream** nếu DB đã ghi, HTTP đã xử lý hoặc thiết bị đã thực hiện command.
6. **Không biến MQTT QoS 1 thành exactly-once nghiệp vụ.** Message có thể được giao lại hoặc publisher có thể phát sự kiện mới trùng ý nghĩa.

### 4.3. Reconnect là một state machine, không phải lời gọi một lần

~~~mermaid
stateDiagram-v2
    [*] --> Configured
    Configured --> Connecting: Khởi tạo client
    Connecting --> Connected: MQTT CONNECT thành công
    Connecting --> ConnectFailed: Timeout / ACL / DNS / TLS
    Connected --> ConnectionLost: Network hoặc broker ngắt
    ConnectionLost --> Reconnecting: Chính sách recovery bật
    Reconnecting --> Connected: Kết nối lại thành công
    Reconnecting --> Reconnecting: Chưa thành công / retry backoff
    Reconnecting --> Stopped: Endpoint bị stop
    Connected --> Stopped: Shutdown chủ động
    ConnectFailed --> Stopped: Policy dừng khởi tạo
~~~

Sơ đồ chỉ mô tả **trạng thái logic**. Spring Integration và Paho không bắt buộc phát mọi event với đúng các tên trên. Khi triển khai, log và metrics phải cho biết: đang kết nối, đã ngắt, đang retry, vừa phục hồi hay đã dừng theo chủ đích.

### 4.4. Mất kết nối có thể làm gián đoạn cả inbound lẫn outbound

Trong ứng dụng dùng hai MQTT clients, publisher và subscriber thường có **Client ID khác nhau**. Chúng có thể reconnect không đồng thời dù dùng chung broker. Một PUBLISH outbound thành công ở client A không chứng minh inbound client B đã subscribe xong hoặc đang online.

Nếu ứng dụng chuyển broker URI sau failover, cần kiểm tra cluster có đồng bộ subscription, session, retained state và inflight messages không. **`setServerURIs(...)` không phải replication hoặc publish tới tất cả broker.**

## 5. Recovery interval của inbound adapter Spring Integration

Spring Integration cung cấp `MqttPahoMessageDrivenChannelAdapter` để subscribe topic và đưa MQTT message vào channel. Các phiên bản hỗ trợ API recovery interval:

~~~java
var adapter = new MqttPahoMessageDrivenChannelAdapter(
        "telemetry-subscriber-1",
        mqttClientFactory,
        "sensors/+/temperature");

adapter.setQos(1);
adapter.setRecoveryInterval(10000);
adapter.setOutputChannel(mqttTelemetryInput);
~~~

`setRecoveryInterval(10000)` biểu thị một khoảng phục hồi ở tầng endpoint, tính bằng **mili giây**. Nó không phải poller đọc broker theo chu kỳ. MQTT inbound adapter vẫn là **message-driven**: khi client nhận PUBLISH qua callback, adapter phát Spring message.

### 5.1. Recovery của adapter và automatic reconnect của Paho khác nhau

| Cơ chế | Đặt ở đâu? | Mục tiêu | Cần kiểm chứng |
| --- | --- | --- | --- |
| Paho `setAutomaticReconnect(true)` | `MqttConnectOptions`. | Client MQTT tự thử kết nối lại khi connection bị mất. | Hành vi callbacks, subscription/session sau reconnect, giai đoạn khởi tạo. |
| Spring `setRecoveryInterval(...)` | `MqttPahoMessageDrivenChannelAdapter`. | Điều tiết thời điểm endpoint xử lý/khôi phục lỗi kết nối theo cơ chế version. | Có được áp dụng trong tình huống cụ thể khi client bật Paho auto reconnect không? |
| Retry business handler | Advice/error flow/outbox. | Thử lại xử lý nghiệp vụ hoặc publish thất bại. | Idempotency, trạng thái nguồn, lỗi dữ liệu không retry. |

Đây là **những lớp khác nhau**, nhưng có thể cùng chạm tới vòng đời kết nối nếu bật đồng thời. Vì vậy không nên mặc định “bật cả hai là sẽ reconnect hai lần nhanh hơn”. Khi dùng Spring Integration/Paho thật, chọn một chính sách và kiểm tra tương tác với phiên bản framework được triển khai.

### 5.2. Ví dụ tách hai chính sách để học rõ

Một cấu hình dễ quan sát trong môi trường demo:

- **Subscriber:** tạo Paho options `automaticReconnect=false` và cho inbound adapter quản lý recovery theo `recoveryInterval`.
- **Publisher:** dùng factory khác với `automaticReconnect=true` để Paho thử phục hồi một connection đã hoạt động và bị ngắt.
- **Mỗi client** có Client ID riêng, cấu hình session riêng.

Đây là **cách minh họa ranh giới trách nhiệm**, không phải hướng dẫn rằng mọi phiên bản Spring Integration phải cấu hình đúng mô hình này. Với một số phiên bản, framework có thể quản lý reconnect/subscription khác nhau; cần thử disconnect và đọc behavior API đang dùng trước khi quyết định production policy.

## 6. Completion timeout của MQTT outbound handler

Trong Spring Integration, outbound MQTT adapter thường được triển khai bằng `MqttPahoMessageHandler`:

~~~java
MqttPahoMessageHandler handler =
        new MqttPahoMessageHandler(
                "commands-publisher-1", clientFactory);

handler.setDefaultTopic("devices/default/commands");
handler.setDefaultQos(1);
handler.setDefaultRetained(false);
handler.setAsync(false);
handler.setCompletionTimeout(5000);
~~~

Đối với **publish đồng bộ** (`setAsync(false)`), handler có thể chờ Paho publish token hoàn tất đến một giới hạn. `setCompletionTimeout(5000)` giới hạn khoảng chờ đó theo mili giây.

### 6.1. Completion timeout thực sự phát biểu điều gì?

Khi một publish vượt quá khoảng đợi:

- Caller/endpoint có thể nhận exception/timeout tùy API và tầng bao bọc.
- Trạng thái publication có thể **không chắc chắn**: broker có thể chưa nhận, đang xử lý, hoặc **đã nhận nhưng ACK về muộn/thất lạc**.
- Nếu ngay lập tức phát lại với một message/command mới, subscriber có nguy cơ xử lý hai lần.
- Một timeout **không tự động hủy publication đã được broker nhận**.

Ví dụ:

~~~mermaid
sequenceDiagram
    participant APP as Spring handler
    participant CLIENT as Paho client
    participant BROKER as MQTT broker
    APP->>CLIENT: publish(cmd-1001, QoS=1)
    CLIENT->>BROKER: PUBLISH(cmd-1001)
    BROKER--xCLIENT: PUBACK bị mất hoặc rất chậm
    CLIENT-->>APP: Completion timeout
    Note over APP,BROKER: Broker có thể đã nhận cmd-1001
    APP->>APP: Đánh dấu kết quả chưa chắc chắn
~~~

Trong tình huống này, lỗi timeout không phải bằng chứng an toàn để tạo một command khác có ID mới. Cần giữ `commandId`/`eventId` ổn định và có cơ chế idempotency, outbox, đối soát hoặc ACK nghiệp vụ riêng.

### 6.2. Completion timeout khác connection timeout

~~~java
MqttConnectOptions options = new MqttConnectOptions();
options.setConnectionTimeout(10); // Giây: mở kết nối

MqttPahoMessageHandler handler =
        new MqttPahoMessageHandler("publisher-1", clientFactory);
handler.setCompletionTimeout(5000); // Mili giây: chờ publish
~~~

Nếu DNS hoặc TLS handshake không hoàn tất, ta đang điều tra **kết nối**. Nếu connection đã tồn tại và PUBLISH QoS 1 đợi PUBACK quá lâu, ta đang điều tra **publish completion**. Cùng một lỗi network có thể gây cả hai loại triệu chứng, nhưng metric và recovery khác nhau.

### 6.3. QoS 0/1/2 làm completion có ý nghĩa khác nhau

| QoS | Handshake chính | Kỳ vọng khi chờ publish token | Điều vẫn không thể suy ra |
| --- | --- | --- | --- |
| 0 | Không có PUBACK QoS 1/2. | Hoàn tất ở mức thao tác client/protocol hỗ trợ, không có broker ACK riêng như QoS 1. | Subscriber đã nhận payload. |
| 1 | `PUBLISH → PUBACK`. | Thao tác có thể đợi xác nhận QoS 1. | Subscriber đã xử lý/commit DB. |
| 2 | `PUBLISH → PUBREC → PUBREL → PUBCOMP`. | Thao tác theo dõi handshake QoS 2. | Application side effect exactly once. |

**Lưu ý:** cách Paho token báo complete với mỗi QoS và cơ chế handler chờ phụ thuộc API/version; khi thiết kế SLA phải kiểm tra bằng test có broker, không dựa trên mô tả tổng quát để suy ra thời điểm ACK của subscriber.

## 7. Async publish: completion timeout không có cùng ý nghĩa với sync

Outbound handler có thể được đặt ở chế độ bất đồng bộ:

~~~java
handler.setAsync(true);
handler.setAsyncEvents(true);
~~~

Trong mô hình async, handler có thể trả về **trước khi broker hoàn thành acknowledgement**, và các lỗi muộn cần được theo dõi qua callback/application events hoặc API hỗ trợ ở phiên bản đang dùng. `setCompletionTimeout(...)` không nên được xem là “timeout của một lời gọi đồng bộ chờ broker” trong mọi thao tác khi async đã bật.

| Tiêu chí | `setAsync(false)` | `setAsync(true)` |
| --- | --- | --- |
| Caller sau `DirectChannel.send(...)` | Có thể phải chờ publish token hoàn tất. | Thường có thể trả về sớm hơn. |
| Lỗi xuất hiện muộn | Có thể thấy nhiều lỗi trên cùng call stack. | Có thể nằm ở callback/event/error handling khác. |
| Completion timeout | Quan trọng cho thời gian chờ synchronous publish. | Cần hiểu hành vi cụ thể của async handler và completion events. |
| Đảm bảo lưu bền vững | Không tự có. | Không tự có. |
| MQTT publish đã được thiết bị xử lý | Không suy ra được. | Không suy ra được. |

**Ví dụ sai:** gọi `channel.send(message)`, nhận `true`, lập tức đánh dấu database `DEVICE_COMPLETED`. Với async publish, kết quả chỉ có thể là đã bàn giao việc gửi; ngay cả khi MQTT publish thành công, thiết bị có thể chưa thực hiện command.

Nếu cần biết **khi nào publication hoàn thành**, hãy theo dõi kết quả publish theo `eventId` và API/application events phù hợp phiên bản. Cần thử lỗi network sau khi `send()` trả về và kiểm tra trạng thái outbox có được cập nhật chính xác không.

## 8. Vì sao không nên retry mù khi timeout hoặc reconnect?

Giả sử ứng dụng xử lý lệnh `cmd-1001` như sau:

~~~text
T0: Spring tạo event cmd-1001
T1: MQTT publisher gửi PUBLISH QoS 1
T2: Broker nhận cmd-1001
T3: Đường mạng mất trước PUBACK
T4: Handler báo completion timeout
T5: Application retry bằng PUBLISH mới
T6: Thiết bị nhận lại cmd-1001
~~~

Trong một số tình huống, client/protocol đã có cơ chế gửi lại publication chưa được xác nhận; đồng thời **ứng dụng** cũng có thể retry. Nếu thiếu kiểm soát, hai tầng retry tạo duplicate.

### 8.1. Ba kiểu kết quả cần phân biệt

| Trạng thái | Ý nghĩa | Việc nên làm |
| --- | --- | --- |
| `PUBLISH_NOT_ATTEMPTED` | Chưa bắt đầu publish theo bằng chứng application. | Có thể thử theo outbox policy. |
| `PUBLISH_CONFIRMED` | Hoàn tất theo tín hiệu publish MQTT được theo dõi. | Đánh dấu gửi thành công ở tầng MQTT, chờ ACK nghiệp vụ nếu cần. |
| `PUBLISH_UNCERTAIN` | Timeout, disconnect, callback không rõ hoặc crash trước cập nhật trạng thái. | Không giả định broker chưa nhận; retry dùng **cùng event ID**, kiểm tra dedup/đối soát. |

Các tên trên là **trạng thái nghiệp vụ minh họa**, không phải enum có sẵn của Spring Integration. Dùng chúng để tách record bền vững khỏi các callback kỹ thuật.

### 8.2. Tách retry ở đúng tầng

1. **Reconnect MQTT client:** giải quyết đường kết nối giữa client và broker.
2. **MQTT QoS retransmission:** phục hồi giao nhận packet chưa xác nhận trong phạm vi protocol.
3. **Outbox publish retry:** xử lý event ứng dụng chưa được ghi nhận publish thành công/không chắc chắn.
4. **Subscriber processing retry:** xử lý database/HTTP downstream bị lỗi sau khi nhận MQTT.
5. **Business command retry:** gửi lại yêu cầu nghiệp vụ khi ACK thiết bị không tới.

Không trộn các tầng này trong một vòng lặp `while(true)` không giới hạn. Mỗi tầng có điều kiện dừng, backoff, idempotency, metric và nhóm lỗi riêng.

## 9. Connection/session sau reconnect

Reconnect thành công không tự chứng minh luồng message đã phục hồi hoàn toàn. Cần xét **Client ID**, **clean session**, **subscription QoS** và trạng thái của broker.

### 9.1. MQTT 3.1.1 clean session

- `cleanSession=true`: khi client reconnect, session cũ không được giữ như persistent session; subscriber thường phải subscribe lại.
- `cleanSession=false`: broker có thể khôi phục session/subscription và message QoS 1/2 lưu khi client offline nếu Client ID ổn định và broker hỗ trợ.
- Retained snapshot là dữ liệu theo topic tại broker, **không** phải lịch sử đầy đủ của persistent session.
- Client ID thay đổi sau restart làm subscription/session cũ không tự được nối lại bằng ID mới.

### 9.2. Đừng dùng Client ID chung để scale ngang

Nếu hai instance của ứng dụng cùng dùng `telemetry-subscriber-1`, broker có thể ngắt client cũ khi client mới CONNECT. Hai client sẽ liên tục đẩy nhau khỏi kết nối. Điều này trông giống “reconnect loop” nhưng gốc là **cấu hình Client ID trùng**, không phải một lỗi timeout cần tăng giá trị.

Các mô hình đúng cần cân nhắc:

| Mục tiêu | Cách tiếp cận | Lưu ý |
| --- | --- | --- |
| Một consumer logic, có persistent session | Client ID ổn định; chỉ một active client cùng ID. | Failover phải quản lý active ownership. |
| Nhiều subscriber độc lập nhận cùng event | Client ID riêng trên mỗi instance. | Mỗi instance có subscription/session độc lập. |
| Chia tải subscriber | Shared subscriptions nếu broker/protocol hỗ trợ, hoặc broker queue phù hợp. | Không mô phỏng competing consumers bằng Client ID trùng. |
| Publish từ nhiều instance | Publisher Client ID riêng, outbox claim/partition. | Tránh nhiều instance publish trùng business event. |

### 9.3. Topic subscription có thể mất sau failover

Hai broker URI không đồng nghĩa hai broker chia sẻ session/retained. Client kết nối lại tới broker độc lập khác có thể cần subscribe lại và có thể thiếu message được broker cũ lưu khi offline. Với HA, phải kiểm thử broker cluster thật: session replication, subscription state, inflight message, retained và quota.

## 10. Ví dụ chạy được: inbound recovery và outbound completion timeout

Ví dụ Spring Boot sau minh họa **hai factory** để tách chính sách subscriber/publisher:

- Inbound subscriber dùng options `automaticReconnect=false` và adapter `recoveryInterval=10000 ms` để quan sát cơ chế recovery của endpoint.
- Outbound publisher dùng `automaticReconnect=true` và handler `completionTimeout=5000 ms`, `async=false`.
- Hai MQTT clients có **Client ID riêng**.
- Hai integration flows tách inbound telemetry và outbound command.

Đây là cấu hình **học tập có chủ đích**, không phải quy tắc cố định cho mọi phiên bản. Trước production, thử cả lỗi kết nối ban đầu và reconnect sau khi đã kết nối, và kiểm tra tương tác adapter/Paho.

### 10.1. Dependencies

Sử dụng Java 17+, Spring Boot/Spring Integration với phiên bản tương thích:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-mqtt</artifactId>
</dependency>
~~~

Spring Boot BOM nên quản lý phiên bản Spring Integration/Paho. Ví dụ dùng API Eclipse Paho MQTT v3 (`org.eclipse.paho.client.mqttv3.MqttConnectOptions`); MQTT v5 client/options khác và cần chỉnh lại ví dụ.

### 10.2. Cấu trúc ví dụ

~~~text
src/main/java/demo/mqttrecovery/
    MqttRecoveryApplication.java
    MqttClientConfiguration.java
    MqttEndpointConfiguration.java
    CommandPublisher.java

src/main/resources/
    application.properties

src/test/java/demo/mqttrecovery/
    MqttClientConfigurationTest.java
    CommandFlowTest.java
~~~

Đặt mỗi class Java có modifier `public` vào file trùng tên. Ví dụ code dưới đây chủ yếu dùng package-private class để tập trung vào cấu hình.

### 10.3. application.properties

~~~properties
app.mqtt.broker-url=${MQTT_BROKER_URL:tcp://localhost:1883}
app.mqtt.subscriber-id=${MQTT_SUBSCRIBER_ID:telemetry-in-local-1}
app.mqtt.publisher-id=${MQTT_PUBLISHER_ID:commands-out-local-1}
~~~

Các giá trị chỉ dành cho local test. Application **không tự chạy broker**. Trong production, URL nên là TLS URI phù hợp; username/password, truststore/certificate, ACL và Client ID được quản lý qua deployment/secrets. Hai client IDs phải **khác nhau và không trùng giữa các instance active**.

### 10.4. Spring Boot application

~~~java
package demo.mqttrecovery;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MqttRecoveryApplication {
    public static void main(String[] args) {
        SpringApplication.run(MqttRecoveryApplication.class, args);
    }
}
~~~

### 10.5. Hai bộ connection options tách biệt

~~~java
package demo.mqttrecovery;

import org.eclipse.paho.client.mqttv3.MqttConnectOptions;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.mqtt.core.DefaultMqttPahoClientFactory;
import org.springframework.integration.mqtt.core.MqttPahoClientFactory;

@Configuration
class MqttClientConfiguration {

    @Bean(name = "subscriberOptions")
    MqttConnectOptions subscriberOptions(
            @Value("${app.mqtt.broker-url}") String brokerUrl) {

        var options = connectionOptions(brokerUrl);
        options.setAutomaticReconnect(false);
        options.setCleanSession(false); // giữ session theo broker policy
        return options;
    }

    @Bean(name = "publisherOptions")
    MqttConnectOptions publisherOptions(
            @Value("${app.mqtt.broker-url}") String brokerUrl) {

        var options = connectionOptions(brokerUrl);
        options.setAutomaticReconnect(true);
        options.setCleanSession(true);
        return options;
    }

    private static MqttConnectOptions connectionOptions(String brokerUrl) {
        var options = new MqttConnectOptions();
        options.setServerURIs(new String[] {brokerUrl});
        options.setConnectionTimeout(10); // giây
        options.setKeepAliveInterval(30); // giây
        return options;
    }

    @Bean(name = "subscriberFactory")
    MqttPahoClientFactory subscriberFactory(
            @Qualifier("subscriberOptions") MqttConnectOptions options) {
        return newFactory(options);
    }

    @Bean(name = "publisherFactory")
    MqttPahoClientFactory publisherFactory(
            @Qualifier("publisherOptions") MqttConnectOptions options) {
        return newFactory(options);
    }

    private static MqttPahoClientFactory newFactory(
            MqttConnectOptions options) {

        var factory = new DefaultMqttPahoClientFactory();
        factory.setConnectionOptions(options);
        return factory;
    }
}
~~~

**Ý nghĩa thiết kế:** `subscriberOptions` và `publisherOptions` là hai bean `MqttConnectOptions` với chính sách khác nhau. Factory được tạo từ đúng options bằng `@Qualifier`; không nên để injection tự chọn ngẫu nhiên một bean khi context có hai bean cùng kiểu.

Lưu ý `options.setAutomaticReconnect(true)` không tự định nghĩa chính xác bao lâu ứng dụng được chờ khi broker offline. Paho có policy retry riêng; Spring endpoint startup, thread và lỗi initial connect vẫn phải được kiểm thử.

### 10.6. Inbound adapter và outbound handler

~~~java
package demo.mqttrecovery;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.mqtt.core.MqttPahoClientFactory;
import org.springframework.integration.mqtt.inbound.MqttPahoMessageDrivenChannelAdapter;
import org.springframework.integration.mqtt.outbound.MqttPahoMessageHandler;
import org.springframework.integration.mqtt.support.DefaultPahoMessageConverter;
import org.springframework.integration.mqtt.support.MqttHeaders;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHandler;

@Configuration
@EnableIntegration
class MqttEndpointConfiguration {

    @Bean(name = "mqtt.telemetry.in")
    MessageChannel telemetryInput() {
        return new DirectChannel();
    }

    @Bean(name = "mqtt.commands.out")
    MessageChannel commandOutput() {
        return new DirectChannel();
    }

    @Bean
    MqttPahoMessageDrivenChannelAdapter telemetryAdapter(
            @Qualifier("subscriberFactory") MqttPahoClientFactory factory,
            @Qualifier("mqtt.telemetry.in") MessageChannel output,
            @Value("${app.mqtt.subscriber-id}") String clientId) {

        var adapter = new MqttPahoMessageDrivenChannelAdapter(
                clientId, factory, "sensors/+/temperature");

        adapter.setQos(1);
        adapter.setRecoveryInterval(10000); // mili giây
        adapter.setConverter(new DefaultPahoMessageConverter());
        adapter.setOutputChannel(output);
        return adapter;
    }

    @Bean(name = "mqttPublisher")
    MqttPahoMessageHandler mqttPublisher(
            @Qualifier("publisherFactory") MqttPahoClientFactory factory,
            @Value("${app.mqtt.publisher-id}") String clientId) {

        var handler = new MqttPahoMessageHandler(clientId, factory);
        handler.setDefaultTopic("demo/unrouted");
        handler.setDefaultQos(1);
        handler.setDefaultRetained(false);
        handler.setAsync(false);
        handler.setCompletionTimeout(5000); // mili giây
        handler.setConverter(new DefaultPahoMessageConverter());
        return handler;
    }

    @Bean
    IntegrationFlow telemetryFlow() {
        return IntegrationFlow.from("mqtt.telemetry.in")
                .handle(String.class, (payload, headers) -> {
                    System.out.println(
                            "Telemetry from "
                            + headers.get(MqttHeaders.RECEIVED_TOPIC)
                            + ", size=" + payload.length());
                    return null;
                })
                .get();
    }

    @Bean
    IntegrationFlow commandFlow(
            @Qualifier("mqttPublisher") MessageHandler publisher) {

        return IntegrationFlow.from("mqtt.commands.out")
                .handle(publisher)
                .get();
    }
}
~~~

Hành vi:

- Inbound adapter subscribe topic filter `sensors/+/temperature` ở QoS 1, nhận message do broker giao rồi phát tới `mqtt.telemetry.in`. Nó không cần `@Poller`.
- Outbound handler publish `Message<String>` từ `mqtt.commands.out` lên broker; `setAsync(false)` và completion timeout giới hạn thời gian đợi publish.
- Channel `DirectChannel` làm flow dễ quan sát nhưng có thể khiến thread gửi bị chặn nếu publish đợi network/broker. Khi dùng `QueueChannel`/`ExecutorChannel` phải thiết kế thêm poller/capacity/error flow.
- `defaultTopic("demo/unrouted")` chỉ để minh họa fallback; **không nên để lệnh production thiếu topic** bị gửi tới topic mặc định mà không validate.

### 10.7. Service tạo message có ID ổn định

~~~java
package demo.mqttrecovery;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.mqtt.support.MqttHeaders;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
class CommandPublisher {

    private final MessageChannel output;

    CommandPublisher(
            @Qualifier("mqtt.commands.out") MessageChannel output) {
        this.output = output;
    }

    boolean publish(
            String commandId, String deviceId, String jsonPayload) {

        if (commandId == null || commandId.isBlank()) {
            throw new IllegalArgumentException("Thiếu commandId");
        }
        if (deviceId == null
                || !deviceId.matches("[A-Za-z0-9_-]{1,40}")) {
            throw new IllegalArgumentException("deviceId không hợp lệ");
        }
        if (jsonPayload == null || jsonPayload.isBlank()) {
            throw new IllegalArgumentException("Thiếu payload");
        }

        String topic = "devices/" + deviceId + "/commands";

        return output.send(MessageBuilder.withPayload(jsonPayload)
                .setHeader(MqttHeaders.TOPIC, topic)
                .setHeader(MqttHeaders.QOS, 1)
                .setHeader(MqttHeaders.RETAINED, false)
                .setHeader("commandId", commandId)
                .build());
    }
}
~~~

Caller đã được authorize có thể gọi:

~~~java
publisher.publish(
        "cmd-1001",
        "device-17",
        "{\"commandId\":\"cmd-1001\",\"action\":\"TURN_ON\"}");
~~~

**Contract:** `commandId` phải xuất hiện trong **payload MQTT** nếu subscriber cần đọc. Header Spring `commandId` không tự truyền thành MQTT v3 user property. Trong ứng dụng thật, nên serialize DTO thành JSON đã validate thay vì cho caller cung cấp một chuỗi JSON có thể không khớp `commandId` được kiểm tra.

`MqttHeaders.QOS=1` có thể mang lại redelivery; `MqttHeaders.RETAINED=false` giúp tránh broker lưu command một lần cho subscriber mới. Cả hai thuộc tính không thay thế ACK nghiệp vụ.

## 11. Thử nghiệm cấu hình Paho mà không cần broker

Có thể kiểm thử `MqttConnectOptions` và factory bean riêng mà **không nạp MQTT adapters**. Điều này cho phép phát hiện sai đơn vị timeout, clean session, bật/tắt automatic reconnect và mơ hồ injection ngay trong CI.

Thêm dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Tạo `MqttClientConfigurationTest.java`:

~~~java
package demo.mqttrecovery;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.eclipse.paho.client.mqttv3.MqttConnectOptions;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.mqtt.core.MqttPahoClientFactory;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = MqttClientConfiguration.class)
@TestPropertySource(properties = {
        "app.mqtt.broker-url=tcp://localhost:1883"
})
class MqttClientConfigurationTest {

    @Autowired
    @Qualifier("subscriberOptions")
    MqttConnectOptions subscriberOptions;

    @Autowired
    @Qualifier("publisherOptions")
    MqttConnectOptions publisherOptions;

    @Autowired
    @Qualifier("subscriberFactory")
    MqttPahoClientFactory subscriberFactory;

    @Autowired
    @Qualifier("publisherFactory")
    MqttPahoClientFactory publisherFactory;

    @Test
    void connectionPoliciesRemainDistinct() {
        assertNotNull(subscriberFactory);
        assertNotNull(publisherFactory);
        assertFalse(subscriberOptions.isAutomaticReconnect());
        assertTrue(publisherOptions.isAutomaticReconnect());
        assertFalse(subscriberOptions.isCleanSession());
        assertTrue(publisherOptions.isCleanSession());
        assertEquals(10, publisherOptions.getConnectionTimeout());
        assertEquals(30, publisherOptions.getKeepAliveInterval());
    }
}
~~~

Test chỉ kiểm tra **bean/options**; nó không chứng minh Paho reconnect sẽ chạy đúng khi broker mất mạng, adapter re-subscribe thành công hoặc outbound publish có ACK.

### 11.1. Đo thời gian với các giá trị có ý nghĩa

Nếu cần test completion timeout, phải có môi trường có thể điều khiển broker/network để tạo **publish token chờ quá thời gian**. Không dùng `Thread.sleep(5001)` trong handler giả rồi tuyên bố đã kiểm tra Paho completion timeout: đó chỉ kiểm tra code ứng dụng đang chờ, không phải đường publish MQTT.

Cũng không nên dựa vào một test localhost broker rất nhanh để kết luận completion timeout 5 giây sẽ đủ cho production WAN/TLS. Cần test kết hợp latency, loss, broker overload và retry.

## 12. Kiểm thử Spring outbound flow bằng fake handler

Để xác minh đường **channel → endpoint** mà không cần broker, cung cấp một `MessageHandler` giả có thể nhận message hoặc mô phỏng lỗi. Không cần nạp `MqttEndpointConfiguration` chứa adapter inbound đang tự kết nối mạng.

~~~java
package demo.mqttrecovery;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.mqtt.support.MqttHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageDeliveryException;
import org.springframework.messaging.MessageHandler;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = {
        CommandFlowTestConfiguration.class,
        RecordingPublisherConfiguration.class
})
class CommandFlowTest {

    @Autowired
    @Qualifier("mqtt.commands.out")
    MessageChannel output;

    @Autowired
    RecordingPublisher recorder;

    @BeforeEach
    void reset() {
        recorder.clear();
        recorder.setFail(false);
    }

    @Test
    void deliversTopicAndPayloadToOutboundEndpoint() {
        String json = "{\"commandId\":\"cmd-test-1\"}";

        boolean sent = output.send(
                MessageBuilder.withPayload(json)
                        .setHeader(MqttHeaders.TOPIC,
                                "devices/device-17/commands")
                        .setHeader(MqttHeaders.QOS, 1)
                        .setHeader(MqttHeaders.RETAINED, false)
                        .build());

        assertTrue(sent);
        assertEquals(
                List.of(new SentMessage(
                        json, "devices/device-17/commands")),
                recorder.snapshot());
    }

    @Test
    void directChannelReportsSynchronousFailure() {
        recorder.setFail(true);

        assertThrows(MessageDeliveryException.class,
                () -> output.send(
                        MessageBuilder.withPayload(
                                "{\"commandId\":\"cmd-test-2\"}")
                                .setHeader(MqttHeaders.TOPIC,
                                        "devices/device-17/commands")
                                .build()));
    }
}

record SentMessage(String payload, String topic) {}

class RecordingPublisher implements MessageHandler {

    private final List<SentMessage> records =
            new CopyOnWriteArrayList<>();
    private boolean fail;

    @Override
    public void handleMessage(Message<?> message) {
        if (fail) {
            throw new MessageDeliveryException(
                    message, "Mô phỏng outbound failure");
        }
        records.add(new SentMessage(
                (String) message.getPayload(),
                (String) message.getHeaders().get(MqttHeaders.TOPIC)));
    }

    void setFail(boolean value) {
        fail = value;
    }

    List<SentMessage> snapshot() {
        return List.copyOf(records);
    }

    void clear() {
        records.clear();
    }
}

@Configuration
@EnableIntegration
class CommandFlowTestConfiguration {

    @Bean(name = "mqtt.commands.out")
    MessageChannel commandChannel() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow outboundFlow(
            @Qualifier("mqttPublisher") MessageHandler publisher) {
        return IntegrationFlow.from("mqtt.commands.out")
                .handle(publisher)
                .get();
    }
}

@Configuration
class RecordingPublisherConfiguration {

    @Bean(name = "mqttPublisher")
    RecordingPublisher mqttPublisher() {
        return new RecordingPublisher();
    }
}
~~~

Test này chứng minh:

1. Channel tồn tại, flow và handler đã được đăng ký.
2. Payload và topic header được chuyển đến handler.
3. Với `DirectChannel` và handler ném `MessageDeliveryException` đồng bộ, caller nhìn thấy lỗi tương ứng.

Nó **không chứng minh** Paho có automatic reconnect, completion timeout hoạt động, message đã đến broker hoặc subscriber đã xử lý. Để thử các điều kiện đó cần broker/network test thật.

## 13. Thực nghiệm broker disconnect, reconnect và completion timeout

Bài thử end-to-end cần broker MQTT riêng do người học kiểm soát. Không nên cố ngắt mạng hoặc restart broker production để thử resilience.

Có thể sử dụng Mosquitto hoặc broker test/container tương đương, cùng CLI `mosquitto_pub`/`mosquitto_sub`.

### 13.1. Xác minh hệ thống hoạt động trước khi gây lỗi

Mở terminal A để nhận command:

~~~bash
mosquitto_sub -h localhost -p 1883 \
  -i test-command-subscriber-1 \
  -q 1 -t 'devices/+/commands' -v
~~~

Mở terminal B để gửi telemetry đến Spring inbound adapter:

~~~bash
mosquitto_pub -h localhost -p 1883 \
  -i test-telemetry-publisher-1 \
  -q 1 -t 'sensors/device-17/temperature' \
  -m '{"eventId":"evt-1001","celsius":26.5}'
~~~

Nếu broker sẵn sàng, inbound flow có thể ghi log topic và kích thước payload. Gọi `CommandPublisher.publish(...)` trong ứng dụng để kiểm tra outbound flow; nếu thành công, subscriber test có thể nhận message.

### 13.2. Thử mất kết nối sau khi đã connect thành công

1. Đảm bảo inbound adapter và outbound handler đã từng kết nối thành công.
2. Ngắt broker test, hoặc dùng công cụ network fault injection trong môi trường thử nghiệm.
3. Quan sát trạng thái connected/disconnected, exception publish, thời gian caller chờ và số lần recovery.
4. Khôi phục broker test.
5. Kiểm tra inbound adapter **subscribe đúng topic trở lại**, không có Client ID trùng, và xử lý một telemetry mới.
6. Kiểm tra publisher có thể gửi publication mới, phân biệt message **được gửi sau reconnect** với message **có thể đã mất khi offline**.
7. Đối chiếu số message trong outbox/quarantine với publication thực tế, bao gồm duplicate.

Không chỉ đọc log “reconnected” rồi kết luận backlog được giao đủ. Với clean session/persistent session/QoS, điều kiện phục hồi session và lưu offline messages còn phụ thuộc broker.

### 13.3. Thử broker không sẵn sàng ngay từ startup

Đây là **bài thử khác** với mất kết nối sau startup. Khi broker chưa bao giờ chấp nhận CONNECT, Paho automatic reconnect có thể không thay thế được startup retry của adapter. Kiểm tra ứng dụng:

- Khởi động thành công nhưng endpoint ở trạng thái retry?
- Fail-fast rồi application context dừng?
- Ghi nhận trạng thái **not ready** cho dịch vụ phụ thuộc broker?
- Có giữ command pending trong outbox thay vì làm mất command?
- Có tiếp tục kết nối lại khi broker xuất hiện mà không cần redeploy không?

Kết quả cụ thể phải được quan sát với Spring Integration/Paho version của dự án. Không hứa mọi ứng dụng Spring Boot với `setAutomaticReconnect(true)` sẽ khởi động và gửi message bình thường khi broker offline.

### 13.4. Mô phỏng publish timeout đúng cách

Muốn khiến Paho publish token chưa hoàn tất trong 5 giây, có thể dùng broker test hoặc network proxy có khả năng **chặn/trễ packet/ACK** sau khi client đã connect. Thử:

~~~text
Paho connectionTimeout = 10 seconds
Spring completionTimeout = 5000 milliseconds
MQTT publish QoS        = 1
Network fault            = chặn/trễ PUBACK sau PUBLISH
Expected                 = application thấy timeout hoặc publish error
                          và đánh dấu PUBLISH_UNCERTAIN
~~~

Tuy nhiên, kết quả phụ thuộc client/broker, cách fault injection và phiên bản. Chặn toàn bộ network có thể được phát hiện là **connection lost** trước khi completion timeout; khi đó phải phân biệt đúng nguyên nhân. Không nên “tạo timeout giả” bằng cách sleep trong business handler.

### 13.5. Ma trận thử nghiệm

| Trường hợp | Phát sinh lỗi | Cần xác minh |
| --- | --- | --- |
| Broker ngắt sau kết nối | Restart broker thử nghiệm. | Auto reconnect/endpoint recovery và subscription phục hồi đúng. |
| Broker chưa chạy ở startup | Khởi động app trước broker. | Startup policy, error/log và cơ chế phục hồi khi broker xuất hiện. |
| Client ID bị trùng | Hai client active dùng cùng ID. | Reconnect loop/đá kết nối và cách cấp ID đúng. |
| Credential hoặc ACL sai | Broker từ chối CONNECT/SUBSCRIBE/PUBLISH. | Không retry vô hạn một lỗi cấu hình mà thiếu alert. |
| TLS lỗi | Certificate/hostname không hợp lệ. | Fail đúng, không bỏ qua kiểm tra TLS. |
| Completion timeout | Trễ/chặn publish ACK. | Timeout, trạng thái uncertain, retry idempotent. |
| Publisher QoS 1 gửi lặp | Mô phỏng ACK lost hoặc app retry. | Subscriber dedup theo commandId/eventId. |
| Subscriber cleanSession=false offline | Publish QoS 1 trong lúc offline. | Session/subscription/backlog theo broker policy. |
| Broker failover URI khác | Chuyển client sang endpoint dự phòng. | Session/retained/inflight state và dữ liệu thiếu/trùng. |
| App shutdown khi publish in-flight | Dừng có chủ đích. | Outbox recovery, pending trạng thái và không mất dữ liệu im lặng. |

## 14. Thread, queue và backpressure khi broker chậm

Một outbound handler đồng bộ trên `DirectChannel` có thể làm caller chờ trong lúc broker chậm. Nếu một hệ thống HTTP inbound gọi `DirectChannel.send(...)` rồi MQTT publish đợi 5 giây, HTTP request latency có thể tăng theo.

| Channel trước MQTT handler | Ưu điểm | Hệ quả khi reconnect/timeout |
| --- | --- | --- |
| `DirectChannel` | Đường lỗi đồng bộ và đơn giản. | Caller/poller bị chặn khi handler chờ publish. |
| `ExecutorChannel` | Tách thread xử lý khỏi producer. | Phải giới hạn thread pool/queue, theo dõi lỗi async và shutdown. |
| `QueueChannel` | Có thể buffer message nội bộ. | Cần poller, capacity và độ bền; queue RAM có thể mất sau restart. |
| Broker bền vững/outbox | Có thể lưu công việc chưa publish. | Tăng độ phức tạp; vẫn cần idempotency và checkpoint. |

Một sơ đồ có outbox:

~~~mermaid
flowchart LR
    API["Business service"]
    DB[("Business DB + transactional outbox")]
    WORKER["Outbox worker<br/>backoff / claim / retry"]
    FLOW["Spring MQTT outbound flow"]
    BROKER[("MQTT broker")]
    DEVICE["Subscriber/thiết bị"]
    ACK["ACK flow"]
    API -->|"Một DB transaction"| DB
    DB --> WORKER --> FLOW --> BROKER --> DEVICE
    DEVICE -. "Business ACK" .-> ACK
~~~

Nếu broker offline vài phút mà upstream vẫn tạo 10.000 message/giây, RAM queue 100 phần tử không thể tự giải quyết. Cần giới hạn tốc độ, lưu bền vững, chỉ chấp nhận công việc trong năng lực hệ thống và cung cấp phản hồi retry/throttling thích hợp cho upstream.

### 14.1. Không gọi completion timeout là circuit breaker

Completion timeout chỉ giới hạn thời gian chờ một thao tác, không tự:

- Dừng gửi mới trong một khoảng cooldown.
- Chặn số lượng request đồng thời.
- Kiểm soát retry storm.
- Định tuyến sang broker/đích khác.
- Đưa message vào DLQ hoặc outbox bền vững.

Nếu cần các hành vi đó, áp dụng circuit breaker/rate limit/retry advice/outbox ở tầng thích hợp và kiểm thử tương tác với client auto reconnect.

## 15. Error handling và trạng thái endpoint

### 15.1. Error channel trong Spring Integration

Trong flow đồng bộ, exception từ handler có thể truyền theo call stack trở lại producer hoặc gateway. Trong flow asynchronous hoặc polling, lỗi có thể được đưa vào `ErrorMessage`, `errorChannel` hoặc error flow tùy endpoint/advice cấu hình. MQTT connection error cũng có thể được ghi nhận qua event, logging hoặc client callback.

**Không giả định** mọi lỗi Paho được tự động publish thành message vào một Spring error channel tùy ý. Thiết kế một error policy cho:

- Lỗi connect/auth/TLS.
- Lỗi subscribe/topic ACL.
- Lỗi converter/schema.
- Lỗi dispatch vào channel.
- Lỗi MQTT publish completion/timeout.
- Lỗi xử lý DB/HTTP sau inbound.
- Lỗi ACK nghiệp vụ không tới.

Mỗi nhóm có một chiến lược khác nhau: sửa config, retry có backoff, quarantine, lưu outbox, DLQ hoặc đối soát.

### 15.2. Retry giới hạn và lỗi không thể phục hồi

Không retry vô hạn một payload JSON sai schema hoặc topic vượt ACL. Những lỗi này sẽ không tự hết chỉ vì broker reconnect. Ngược lại, một network timeout ngắn có thể đáng thử lại, nhưng phải giới hạn số lần/thời gian và giữ `eventId` ổn định.

Một mô hình policy:

~~~text
network disconnected:
    mark PUBLISH_UNCERTAIN
    retry with backoff and same eventId
    stop after retry budget / escalate

invalid topic or forbidden publish:
    reject/quarantine
    alert on configuration/security issue
    no blind retry loop

downstream business validation failed:
    do not treat as MQTT reconnect issue
    create data-quality error with correlationId
~~~

Policy trên là mô tả nghiệp vụ, không phải cấu hình Spring Integration sẵn có. Nó phải được hiện thực bằng handler/advice/outbox/monitoring phù hợp.

## 16. Vòng đời và observability

### 16.1. Các trạng thái cần đo

| Metric/log có ích | Tại sao |
| --- | --- |
| `mqtt_connected{clientId,role}` | Phát hiện publisher/subscriber offline; tránh gắn nhãn có secrets. |
| `mqtt_disconnect_total` | Phân biệt disconnect đơn lẻ với reconnect loop. |
| `mqtt_reconnect_attempt_total` | Phát hiện broker outage và thundering herd. |
| `mqtt_connection_duration_ms` | Đo thời gian kết nối và TLS handshake. |
| `mqtt_publish_completion_ms` | Chọn completion timeout dựa trên dữ liệu đo, không phỏng đoán. |
| `mqtt_publish_timeout_total` | Phát hiện broker/network chậm hoặc QoS ACK lỗi. |
| `mqtt_pending_outbox` | Số command/event đang chờ xuất bản an toàn. |
| `mqtt_subscription_recovered_total` | Chứng minh inbound subscriber hoạt động sau reconnect. |
| `business_ack_lag_ms` | Đo khoảng cách giữa MQTT publish và xác nhận nghiệp vụ. |
| `message_duplicate_total` | Kiểm tra hiệu quả dedup ở downstream. |

Tên trên là **gợi ý thiết kế**, không phải metric mặc định được Spring Integration/Paho phát ra với chính xác tên đó.

### 16.2. Quan sát một sự kiện qua toàn pipeline

Với payload:

~~~json
{
  "commandId": "cmd-1001",
  "deviceId": "device-17",
  "action": "TURN_ON"
}
~~~

Có thể lưu log/trace theo các bước:

~~~text
cmd-1001 CREATED
cmd-1001 PUBLISH_ATTEMPTED
cmd-1001 PUBLISH_UNCERTAIN (completion timeout)
cmd-1001 PUBLISH_CONFIRMED (theo kết quả được quan sát sau retry)
cmd-1001 BUSINESS_ACKNOWLEDGED (thiết bị xác nhận)
~~~

Các trạng thái phải có timestamp và correlation, nhưng **không lưu secret/credential/full payload nhạy cảm** trong log. Trạng thái không được phép nhảy thẳng từ `CREATED` sang `BUSINESS_ACKNOWLEDGED` chỉ vì `MessageChannel.send()` thành công.

### 16.3. Startup readiness và graceful shutdown

Khi broker bắt buộc cho chức năng chính, readiness check có thể cần báo degraded/not ready đến khi publisher và subscriber hoạt động theo SLA. Nhưng không nhất thiết phải fail toàn bộ ứng dụng nếu broker là dependency cho một chức năng không thiết yếu và outbox vẫn nhận công việc.

Khi shutdown:

1. Ngừng nhận command mới hoặc đưa chúng vào outbox.
2. Chờ publish in-flight trong một khoảng giới hạn.
3. Giữ các record `PUBLISH_UNCERTAIN` chưa đối soát.
4. Dừng adapter/client để giải phóng kết nối và thread.
5. Đảm bảo restart không tạo Client ID trùng với replica cũ còn active.

Automatic reconnect không phải cơ chế để “cứ giữ app chạy là không mất dữ liệu”; shutdown/crash recovery cần kế hoạch lưu bền vững riêng.

## 17. Bảo mật và cấu hình môi trường

Automatic reconnect có thể thử lại liên tục trong bối cảnh credential hết hạn, TLS certificate sai hoặc ACL đã thay đổi. Đây là **lỗi cấu hình/bảo mật**, không nên chỉ tăng timeout để che khuất.

| Rủi ro | Biện pháp |
| --- | --- |
| TCP plaintext trên mạng không tin cậy | Dùng TLS, xác minh certificate chain/hostname. |
| Reconnect với credential đã bị thu hồi | Alert sớm, xoay vòng secret theo quy trình an toàn. |
| Client ID trùng | Gắn định danh ổn định/hợp lệ theo instance hoặc consumer ownership. |
| Publish sai topic | Validate device/tenant, broker topic ACL và default topic policy. |
| Retry storm sau broker phục hồi | Backoff/jitter, giới hạn concurrency và outbox workers. |
| Payload nhạy cảm được replay không kiểm soát | Encryption/retention/ACL, audit replay và hạn chế số bản sao. |
| Lệnh nguy hiểm bị xử lý trùng | Stable commandId, idempotency, expiration và xác nhận trạng thái. |
| MQTT retained command cũ | `retained=false` cho command một lần, cleanup retained sai theo quyền quản trị. |

Với Paho v3, URI TLS thường có dạng `ssl://broker-host:8883`. Chỉ thay chuỗi URL không đủ: phải có trust configuration/certificate phù hợp và xác minh kết nối thực tế. Không vô hiệu hóa hostname verification trong production.

## 18. Những lỗi cấu hình thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| `automaticReconnect=true` nhưng app fail ngay khi startup. | Chưa từng CONNECT thành công; endpoint startup policy khác recovery sau mất kết nối. | Thử initial connection failure riêng; thiết kế readiness/retry thích hợp. |
| App liên tục reconnect dù broker tốt. | Client ID trùng, ACL, network proxy hoặc broker kick connection. | Kiểm tra broker logs, Client ID và policy, không chỉ tăng timeout. |
| Inbound adapter không nhận message sau reconnect. | Session/subscription chưa được phục hồi hoặc topic filter/ACL sai. | Kiểm tra clean session, subscribe lại, client ID và version behavior. |
| Completion timeout rất ngắn gây lỗi trên WAN. | Không đủ latency cho QoS/SSL hoặc broker có tải. | Đo publish latency, chọn timeout và backpressure phù hợp. |
| Timeout xong retry tạo command trùng. | Broker có thể đã nhận trước khi ACK mất. | Cùng commandId, idempotency và đối soát. |
| `MessageChannel.send()` trả true nhưng publish thất bại sau đó. | Async handler hoặc chuyển thread. | Theo dõi publish callback/events/outbox; không coi send là MQTT ACK. |
| Sửa `connectionTimeout` nhưng publish vẫn chậm. | Đây là timeout mở kết nối, không phải completion publish. | Kiểm tra `setCompletionTimeout(...)` và broker QoS/latency. |
| Thay keepalive làm thiết bị không còn offline. | Keepalive chỉ theo dõi MQTT connection, không phải heartbeat thiết bị. | Xây device heartbeat/Last Will theo nghiệp vụ. |
| Queue đầy trong lúc broker offline. | Message đến nhanh hơn publish; không có backpressure. | Rate limit, persistent outbox, capacity và cảnh báo. |
| QoS 2 vẫn có sự kiện nghiệp vụ trùng. | Hai lần publish độc lập hoặc retry business side effect. | Event ID/unique constraint, không dựa vào QoS 2. |
| Broker failover rồi mất subscription cũ. | Hai broker độc lập không chia sẻ persistent session. | Kiểm tra cluster/session replication và re-subscribe. |
| Auto reconnect gây CPU/log spam. | Retry cấu hình sai, không backoff/jitter/alert đúng. | Sửa nguyên nhân, giới hạn logging và đo retry thực tế. |
| Listener có kết nối nhưng DB không ghi. | Converter/handler/channel/downstream lỗi. | Kiểm tra toàn pipeline và error channel, không chỉ MQTT client. |

## 19. Bài tập thực hành có kiểm chứng

**Bối cảnh:** một hệ thống nhà thông minh dùng MQTT để nhận nhiệt độ từ cảm biến và publish lệnh điều hòa. Broker có thể mất kết nối 30–60 giây trong giờ cao điểm; lệnh bật/tắt không được xử lý lặp và trạng thái phải có thể đối soát.

Thực hiện:

1. Cấu hình Spring Integration MQTT inbound adapter subscribe `sensors/+/temperature`, outbound handler publish `devices/{id}/commands`.
2. Đặt hai Client IDs riêng; giải thích vì sao publisher/subscriber không nên chia sẻ cùng ID.
3. Tạo hai `MqttPahoClientFactory` với options tách biệt: một thử adapter recovery, một thử Paho automatic reconnect.
4. Cấu hình `connectionTimeout=10s`, `keepalive=30s`, `recoveryInterval=10000ms` và `completionTimeout=5000ms`. Ghi rõ đơn vị.
5. Viết integration test không broker để xác nhận policy connection options, channel, message headers và xử lý exception đồng bộ.
6. Với broker thử nghiệm, gửi telemetry và command thành công trước khi gây lỗi.
7. Dừng broker sau một kết nối đã thành công, quan sát reconnect attempts, reconnect duration và việc subscription được khôi phục.
8. Khởi động ứng dụng khi broker offline; so sánh với tình huống mất kết nối sau startup.
9. Dùng fault injection tạo publish QoS 1 với ACK chậm hơn completion timeout; đánh dấu trạng thái `PUBLISH_UNCERTAIN`.
10. Retry cùng `commandId` qua outbox; thiết bị/subscriber dùng idempotency để tránh side effect lặp.
11. Thử cleanSession=true/false và Client ID ổn định khi offline; quan sát message backlog và thiếu/trùng.
12. Đưa handler sau `QueueChannel` với capacity có giới hạn; đo backlog trong lúc broker offline và hành vi khi queue đầy.
13. Tạo readiness/alert và thống kê số publish thất bại, message uncertain, duplicate và business ACK timeout.
14. Giải thích lỗi authentication/TLS khác temporary network outage và vì sao không retry vô hạn lỗi cấu hình.

**Tiêu chí đạt:** có sơ đồ trạng thái rõ, tách biệt các timeout, test phân biệt initial connect/reconnect, log/trạng thái không nhầm MQTT publish với ACK nghiệp vụ, có chiến lược không mất command và không lặp side effect khi broker/ứng dụng restart.

## 20. Câu hỏi tự kiểm tra

1. `MqttConnectOptions.setAutomaticReconnect(true)` giải quyết vấn đề gì?
2. Nó có mặc nhiên retry vô hạn khi kết nối lần đầu chưa từng thành công không?
3. `MqttPahoMessageDrivenChannelAdapter.setRecoveryInterval(10000)` là mili giây hay giây?
4. Vì sao không nên bật hai cơ chế reconnect mà chưa kiểm tra tương tác theo phiên bản?
5. `setConnectionTimeout(10)` khác `setCompletionTimeout(5000)` ở đâu?
6. Keepalive có phải timeout ACK của một command không?
7. Khi publish QoS 1 bị timeout, có chắc broker chưa nhận message không?
8. Vì sao retry một PUBLISH mới có thể tạo duplicate dù có QoS?
9. QoS 2 có bảo đảm database transaction chỉ commit một lần không?
10. Vì sao `setAsync(true)` có thể khiến `MessageChannel.send()` về trước broker ACK?
11. Khi publisher auto reconnect xong, tại sao subscriber vẫn có thể thiếu message?
12. Clean session và Client ID ảnh hưởng offline delivery thế nào?
13. Hai replica cùng Client ID có phải cơ chế chia tải subscriber hợp lệ không?
14. Nhiều broker URI có bảo đảm session/state đồng bộ khi failover không?
15. Completion timeout có phải circuit breaker không?
16. Tại sao test với fake `MessageHandler` không chứng minh được Paho recovery?
17. Làm sao xác minh một timeout là lỗi publish token chứ không phải lỗi mở TCP/TLS?
18. Trong hệ thống có outbox, làm sao xử lý message chưa rõ broker đã nhận hay chưa?
19. Những metric nào giúp phát hiện reconnect loop và publish latency tăng?
20. Vì sao thiết bị phải phát business ACK riêng nếu nghiệp vụ cần xác nhận thực thi lệnh?

**Gợi ý:** Automatic reconnect là chiến lược khôi phục connection; completion timeout là giới hạn đợi một thao tác; thành công MQTT không đồng nghĩa hoàn tất nghiệp vụ. Cần xác định message state, Client ID, QoS, replay và idempotency.

## 21. Kết luận

**Automatic reconnect và completion timeout** là hai công cụ nền tảng khi vận hành MQTT adapters trong Spring Integration:

- `MqttConnectOptions.setAutomaticReconnect(true)` giúp Paho thử khôi phục một kết nối đã hoạt động và bị mất, nhưng không thay thế startup policy, xử lý authentication hoặc lưu bền vững.
- `MqttPahoMessageDrivenChannelAdapter.setRecoveryInterval(...)` liên quan việc endpoint khôi phục kết nối; phải kiểm tra tương tác với Paho reconnect theo phiên bản cụ thể.
- `MqttPahoMessageHandler.setCompletionTimeout(...)` giới hạn thời gian chờ publish theo chế độ xử lý thích hợp; **timeout có thể tạo kết quả chưa chắc chắn**, không phải xác nhận broker chưa nhận.
- `connectionTimeout`, `keepAliveInterval`, `recoveryInterval`, `completionTimeout` và business ACK timeout là các đại lượng khác nhau, với đơn vị và mục tiêu riêng.

Trong module **SPRING_INTEGRATION_ADAPTERS**, một kiến trúc đáng tin cậy không chỉ là “client tự kết nối lại”. Cần bảo đảm **Client ID/session, subscription, QoS/retained, MessageChannel và thread**, cùng error handling, backpressure, transactional outbox, idempotency, monitoring và kiểm thử broker bị lỗi. Khi biết message đang ở giai đoạn nào và ai chịu trách nhiệm phục hồi, hệ thống có thể tiếp tục vận hành an toàn ngay cả khi network hoặc broker không ổn định.

