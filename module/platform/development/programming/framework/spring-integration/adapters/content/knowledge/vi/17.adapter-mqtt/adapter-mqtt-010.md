# Delivery token và xác nhận publish

## 1. Bài toán: “gửi thành công” thực sự có nghĩa gì?

Một service phát lệnh `TURN_ON` cho thiết bị qua MQTT và thấy `MessageChannel.send(...)` trả về `true`. Có thể cập nhật database thành `COMPLETED` ngay không? **Không.** Hệ thống có ít nhất bốn mức xác nhận khác nhau:

1. Spring đã chấp nhận và chuyển message cho endpoint nội bộ.
2. MQTT client đã nhận yêu cầu PUBLISH, có thể cấp một **delivery token**.
3. MQTT broker đã hoàn tất thủ tục nhận publication theo cấp **QoS** được dùng.
4. Subscriber/thiết bị đã xử lý nội dung, gửi **ACK nghiệp vụ**, backend đã xác minh và lưu kết quả.

Bài **“Delivery token và xác nhận publish”** thuộc chương **Adapter MQTT**, module **SPRING_INTEGRATION_ADAPTERS**. Module tập trung kết nối hệ thống ngoài qua inbound/outbound adapter, gateway, poller và `MessageChannel`, thực hành file, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu, đồng thời xử lý hợp đồng message, lỗi và vòng đời kết nối.

Sau bài học, người đọc có thể:

- Phân biệt `IMqttDeliveryToken`, `waitForCompletion(...)`, callback `deliveryComplete(...)`, MQTT `PUBACK`/`PUBCOMP` và business ACK.
- Hiểu tác động của QoS 0/1/2 đến ý nghĩa token hoàn tất và khả năng message trùng.
- Cấu hình `MqttPahoMessageHandler` publish đồng bộ hoặc bất đồng bộ và giới hạn `completionTimeout`.
- Quan sát Spring Integration MQTT Sent/Delivered events ở phiên bản hỗ trợ; không coi chúng là xác nhận nghiệp vụ.
- Thiết kế message ID/correlation, outbox, retry với kết quả chưa chắc chắn, idempotent subscriber và ACK topic riêng.
- Tạo Java Spring Boot flow gửi MQTT command, nhận ACK, viết test không broker và thử nghiệm lỗi broker có kiểm soát.

**Phạm vi kỹ thuật:** mã minh họa dùng Spring Integration MQTT với Eclipse Paho **MQTT v3 API** và MQTT 3.1.1. Hành vi event/callback phụ thuộc version đã triển khai. MQTT v5 có API, metadata và một số protocol semantics khác; không dùng lẫn ví dụ v3 khi chưa điều chỉnh.

## 2. Bốn cột mốc trong một giao dịch publish

~~~mermaid
sequenceDiagram
    participant APP as Business service
    participant CH as Spring MessageChannel
    participant H as MQTT outbound handler
    participant P as Eclipse Paho client
    participant B as MQTT broker
    participant D as Thiết bị
    APP->>CH: send(commandId=cmd-1001)
    CH->>H: dispatch Spring Message
    H->>P: publish(topic, payload, qos=1)
    Note over APP,P: Bàn giao nội bộ và token của Paho
    P->>B: PUBLISH QoS 1
    B-->>P: PUBACK
    Note over P,B: MQTT publish completion của chặng này
    B->>D: PUBLISH command
    D->>D: Validate, thực hiện tác vụ
    D->>B: PUBLISH ACK(commandId, result)
    B-->>APP: ACK qua MQTT inbound flow riêng
~~~

| Mốc | Tín hiệu | Có thể kết luận | Không thể kết luận |
| --- | --- | --- | --- |
| Spring handoff | `MessageChannel.send()` trả `true` | Channel đã chấp nhận việc gửi theo semantics của channel/consumer. | Broker đã nhận publication. |
| Paho accepted | Có `IMqttDeliveryToken` | Một thao tác MQTT publish đã có handle theo dõi. | Publish đã hoàn tất. |
| MQTT publish complete | Token/callback/event hoàn tất theo QoS | Chặng MQTT publisher→broker đạt điều kiện completion của giao thức/client. | Subscriber đã commit DB, thiết bị đã thi hành. |
| Business acknowledged | ACK có `commandId` hợp lệ, đã cập nhật DB | Xử lý nghiệp vụ đã được xác nhận theo contract. | Các side effect ngoài contract cũng nhất quán nếu chưa đối soát. |

**Đây là lỗi cần tránh:** dùng `token.isComplete()` hoặc `MqttMessageDeliveredEvent` để cập nhật `device_commands.status = APPLIED`. Chúng không hề đọc dữ liệu từ phần cứng hay database của subscriber.

### 2.1. Broker ACK không phải subscriber ACK

MQTT QoS cung cấp handshake trên chặng **publisher ↔ broker** và chặng **broker ↔ subscriber**, theo những subscription/QoS riêng. Publisher không nhận một danh sách các subscriber đã xử lý; nó không tự biết thiết bị nào đang online hay có gửi lại lệnh sau khi offline không.

### 2.2. MQTT topic khác Spring MessageChannel

~~~text
Spring channel: mqtt.commands.out
MQTT broker URI: ssl://broker.example.net:8883
MQTT publish topic: devices/device-17/commands
Business ACK topic: devices/device-17/ack
~~~

`MessageChannel` nối producer và endpoint nội bộ Spring; MQTT topic là đích phân phối qua broker. Không gửi command vào topic có wildcard như `devices/+/commands`: wildcard dành cho **subscription filter**, không phải topic name của PUBLISH.

## 3. IMqttDeliveryToken trong Eclipse Paho là gì?

`IMqttDeliveryToken` theo dõi **một MQTT publish operation** của Paho. Khi gọi API publish bất đồng bộ, client có thể trả về token trước khi broker phát ACK.

~~~java
import org.eclipse.paho.client.mqttv3.IMqttDeliveryToken;

IMqttDeliveryToken token = client.publish(
        "devices/device-17/commands",
        payloadBytes,
        1,
        false);
~~~

Có thể quan sát token:

~~~java
token.waitForCompletion(5000); // mili giây
boolean complete = token.isComplete();
int packetId = token.getMessageId();
~~~

Các thành phần khác nhau:

| Đối tượng | Vai trò | Giới hạn |
| --- | --- | --- |
| `IMqttToken` | Giao diện token chung của một số MQTT async operations. | Không chỉ dành cho PUBLISH. |
| `IMqttDeliveryToken` | Token gắn với delivery/PUBLISH. | Runtime-local; không phải business record bền vững. |
| MQTT packet identifier | ID trong một giao dịch giao thức; ví dụ `57`. | Có thể reuse trong client/session, không unique toàn hệ thống. |
| `commandId`/`eventId` | ID nghiệp vụ do ứng dụng cấp và lưu. | Phải hiện diện trong payload/contract cho consumer bên ngoài. |
| Spring `Message<?>` | Payload + headers trong flow nội bộ. | Không tự truyền mọi Spring header xuyên MQTT v3. |

**Đừng lưu `token.getMessageId()` làm khóa chính của bảng business commands.** Packet ID có thể được dùng lại, và một process restart sẽ không khôi phục được chính object token trước đó. Cần một `commandId` ổn định qua retry/reconnect/restart.

### 3.1. Token trả về chưa đồng nghĩa hoàn tất

Khi một lệnh PUBLISH được chấp nhận cho xử lý bất đồng bộ, token có thể ở trạng thái chưa complete. Tùy API, thao tác `waitForCompletion(...)` sẽ chặn thread trong giới hạn rồi hoàn tất hoặc ném exception.

Không đọc `isComplete()` một lần ngay sau `publish(...)` rồi quyết định dứt khoát là “mất message” nếu nó còn false. Đó có thể chỉ là publication đang chờ broker hoặc client network worker.

### 3.2. Khi waitForCompletion hết thời gian

Nếu completion chưa được ghi nhận trước timeout, kết quả ở publisher có thể **không chắc chắn**:

- PUBLISH chưa ra khỏi client.
- Broker đã nhận nhưng PUBACK/PUBCOMP bị chặn hoặc về muộn.
- Broker đã hoàn tất, còn client/process không kịp ghi nhận.
- Broker đã giao message cho subscriber nhưng application chỉ thấy exception.

**Timeout không phải yêu cầu hủy message đã được broker nhận.** Do đó, retry sau timeout cần giữ cùng `commandId`/`eventId` và consumer phải idempotent.

## 4. Ví dụ độc lập: Paho async client và delivery token

Trước khi tìm hiểu Spring Integration, xem Paho raw API. Đây là một client demo riêng; **không** tự tạo thêm client Paho bên trong handler do Spring đang quản lý.

~~~java
package demo.mqttdelivery;

import java.nio.charset.StandardCharsets;

import org.eclipse.paho.client.mqttv3.IMqttDeliveryToken;
import org.eclipse.paho.client.mqttv3.MqttAsyncClient;
import org.eclipse.paho.client.mqttv3.MqttConnectOptions;

public class RawPahoTokenDemo {

    public static void main(String[] args) throws Exception {
        String broker = "tcp://localhost:1883";
        var client = new MqttAsyncClient(
                broker, "raw-paho-publisher-local-1");

        var options = new MqttConnectOptions();
        options.setConnectionTimeout(10);
        options.setKeepAliveInterval(30);
        options.setCleanSession(true);

        try {
            client.connect(options).waitForCompletion(10000);

            String json = "{\"commandId\":\"cmd-1001\","
                    + "\"action\":\"TURN_ON\"}";

            IMqttDeliveryToken token = client.publish(
                    "devices/device-17/commands",
                    json.getBytes(StandardCharsets.UTF_8),
                    1,
                    false);

            token.waitForCompletion(5000);

            System.out.println(
                    "Publish complete=" + token.isComplete()
                    + ", packetId=" + token.getMessageId());
        } finally {
            if (client.isConnected()) {
                client.disconnect().waitForCompletion(5000);
            }
            client.close();
        }
    }
}
~~~

Các bước:

1. Client mở connection với broker test.
2. `publish(...)` tạo một PUBLISH QoS 1, retained=false và trả token.
3. `waitForCompletion(5000)` chờ tối đa 5 giây cho completion theo Paho.
4. Nếu không xảy ra timeout/lỗi, code đọc `isComplete()`/packetId để log kỹ thuật.
5. `disconnect()`/`close()` giải phóng kết nối khi thoát bình thường.

Broker ở `localhost:1883` phải có sẵn; demo không tạo broker. Với production, dùng TLS/certificate/authentication/ACL, Client ID duy nhất giữa các client active. Không đặt mọi replica cùng một Client ID như ví dụ local.

### 4.1. So sánh token với “future” của business request

Token của Paho là handle cho một operation giao thức, không phải `CompletableFuture<BusinessResult>`. Token complete không chứa trạng thái `APPLIED` của thiết bị, và không có phép chờ Paho nào tự đưa JSON business ACK từ topic khác vào kết quả token.

### 4.2. Timeout và retry

~~~text
PUBLISH commandId=cmd-1001 → broker đã nhận
PUBACK bị mất trên đường về
waitForCompletion(5000) → timeout
Caller phát lại cmd-1001
Device có thể thấy cmd-1001 hai lần
~~~

Nếu caller phát lại bằng `cmd-1002` thì hệ thống **không thể nhận biết dễ dàng** hai attempts là một command nghiệp vụ. Phải giữ `cmd-1001`, có idempotency và ưu tiên đối soát ACK trước khi retry không cần thiết.

## 5. Callback deliveryComplete và bất đồng bộ

Paho MQTT v3 cung cấp `MqttCallback.deliveryComplete(IMqttDeliveryToken)`. Ở client raw Paho, callback có thể thông báo completion mà không cần block caller bằng `waitForCompletion(...)`.

~~~java
import org.eclipse.paho.client.mqttv3.IMqttDeliveryToken;
import org.eclipse.paho.client.mqttv3.MqttCallback;
import org.eclipse.paho.client.mqttv3.MqttMessage;

client.setCallback(new MqttCallback() {

    @Override
    public void connectionLost(Throwable cause) {
        System.err.println("Connection lost: " + cause);
    }

    @Override
    public void messageArrived(String topic, MqttMessage message) {
        // Không dùng trong demo publisher không subscribe.
    }

    @Override
    public void deliveryComplete(IMqttDeliveryToken token) {
        System.out.println("Delivery complete: "
                + token.getMessageId());
    }
});
~~~

Đặt callback trên client Paho **trước khi connect** trong ví dụ raw. Đừng tự thay callback nội bộ của Spring MQTT adapter, vì Spring có logic lifecycle, channel dispatch và error handling phụ thuộc callback đó.

| Cách quan sát | Đặc điểm | Điểm phải lưu ý |
| --- | --- | --- |
| `waitForCompletion(...)` | Thread đợi operation hoàn tất/timeout. | Có thể chặn caller và dẫn tới uncertain outcome. |
| `deliveryComplete(...)` | Notification do client callback phát. | Có thể đến muộn, trên thread khác; không ghi nhận bền vững khi crash. |
| Spring async events | Quan sát từ layer `MqttPahoMessageHandler` nếu hỗ trợ. | Không mặc định mọi cấu hình đều phát event; phải test theo version. |
| Business ACK topic | MQTT publication mới từ subscriber/thiết bị. | Cần schema/identity/correlation và DB commit riêng. |

### 5.1. Callback không phải transactional log

Một callback có thể đến, rồi application crash trước khi persist trạng thái. Khi khởi động lại, Paho token object đã mất nhưng broker có thể đã nhận message. Vì thế callback cần được chuyển thành durable outbox state **khi có thể**, cùng chính sách đối soát khi không chắc chắn; callback bản thân nó không tạo commit atomic với broker.

### 5.2. Không chặn quá lâu trong callback thread

Trong callback nên ghi nhận metadata ngắn gọn hoặc chuyển sang một queue/handler với capacity phù hợp. Nếu gọi HTTP chậm, giữ DB lock hoặc `Thread.sleep(...)` trong callback, có thể gây nghẽn xử lý network và làm khó phục hồi. Luồng nghiệp vụ cần backpressure, retry/error policy ở tầng riêng.

## 6. QoS 0, 1, 2 và ý nghĩa của completion

### 6.1. QoS 0: không có broker PUBACK

~~~mermaid
sequenceDiagram
    participant P as Publisher
    participant B as Broker
    P->>B: PUBLISH QoS 0
    Note over P,B: Không có PUBACK/PUBCOMP cho PUBLISH này
~~~

Token của client có thể complete theo semantics Paho, nhưng **QoS 0 không có ACK của broker tương đương QoS 1**. Không dùng completion QoS 0 để cam kết broker đã nhận hoặc subscriber đã đọc message.

QoS 0 hợp với telemetry tần suất cao khi mất một số mẫu là chấp nhận được.

### 6.2. QoS 1: PUBLISH → PUBACK

~~~mermaid
sequenceDiagram
    participant P as Publisher
    participant B as Broker
    P->>B: PUBLISH QoS 1, packetId=57
    B-->>P: PUBACK packetId=57
    Note over P,B: ACK có thể thất lạc, dẫn đến redelivery
~~~

Ở QoS 1, completion sau PUBACK xác nhận chặng publisher→broker. QoS 1 cho phép message giao lại khi protocol/client retry; cũng có thể có **hai publications độc lập** cùng một `eventId` nếu ứng dụng retry ở tầng cao hơn.

### 6.3. QoS 2: handshake bốn bước

~~~mermaid
sequenceDiagram
    participant P as Publisher
    participant B as Broker
    P->>B: PUBLISH QoS 2, packetId=57
    B-->>P: PUBREC
    P->>B: PUBREL
    B-->>P: PUBCOMP
~~~

QoS 2 cung cấp exactly-once trong phạm vi protocol delivery của một publication, nhưng **không chứng minh side effect exactly-once trong DB hoặc thiết bị**. Một application có thể tạo hai publish operations khác nhau biểu diễn cùng command.

### 6.4. Ma trận

| QoS | Phương thức xác nhận | Completion có thể cho biết | Không chứng minh |
| ---: | --- | --- | --- |
| 0 | Không có PUBACK. | Paho hoàn tất thao tác theo client implementation. | Broker/subscriber đã nhận. |
| 1 | PUBACK. | Chặng MQTT publisher→broker đạt ACK QoS 1. | Subscriber đã xử lý. |
| 2 | PUBREC, PUBREL, PUBCOMP. | Handshake QoS 2 hoàn tất. | Database commit một lần. |

Broker tiếp tục phân phối tới subscriber theo **subscription QoS/session** riêng. Publisher nhận PUBACK không phải một ACK từ mọi subscriber phù hợp với topic filter.

## 7. Spring Integration: MqttPahoMessageHandler đồng bộ

MQTT outbound endpoint trong Spring Integration thường là `MqttPahoMessageHandler`:

~~~java
var handler = new MqttPahoMessageHandler(
        "commands-publisher-1", mqttClientFactory);

handler.setDefaultTopic("diagnostics/unrouted");
handler.setDefaultQos(1);
handler.setDefaultRetained(false);
handler.setConverter(new DefaultPahoMessageConverter());
handler.setAsync(false);
handler.setCompletionTimeout(5000);
~~~

- `setAsync(false)`: publish theo chế độ chờ completion tương ứng, caller có thể bị block.
- `setCompletionTimeout(5000)`: giới hạn thời gian chờ, tính theo **mili giây**.
- `setDefaultQos(1)` và `setDefaultRetained(false)`: giá trị mặc định khi message không override theo contract converter/handler.
- `setDefaultTopic("diagnostics/unrouted")`: chỉ là fallback demo; command production cần fail fast nếu thiếu topic cụ thể.
- `setConverter(...)`: đổi Spring message sang MQTT bytes/metadata, không tự xử lý business ACK.

Nếu handler nằm sau `DirectChannel`, một số lỗi publish đồng bộ có thể lan trở về `MessageChannel.send(...)`. Nhưng `DirectChannel` không tạo transaction giữa MQTT và DB, cũng không bắt thiết bị thực hiện command trước khi trả kết quả.

### 7.1. Header topic/QoS/retained của một command

~~~java
Message<String> command = MessageBuilder
        .withPayload(
                "{\"commandId\":\"cmd-1001\",\"action\":\"TURN_ON\"}")
        .setHeader(MqttHeaders.TOPIC, "devices/device-17/commands")
        .setHeader(MqttHeaders.QOS, 1)
        .setHeader(MqttHeaders.RETAINED, false)
        .build();
~~~

Các hằng `MqttHeaders.TOPIC`, `QOS`, `RETAINED` điều khiển publication. Một Spring header `commandId` tùy biến **không tự trở thành MQTT v3 user property**; nếu device cần đọc ID, đưa nó vào JSON/binary payload.

### 7.2. Sync publish vẫn có uncertain outcome

~~~text
T0: Paho gửi QoS1 PUBLISH
T1: Broker nhận PUBLISH
T2: Network mất PUBACK
T3: Handler chờ quá completionTimeout
T4: Caller thấy exception
~~~

Không được biến T4 thành kết luận “broker chắc chắn chưa nhận command”. Mô hình business state cần `PUBLISH_UNCERTAIN`, outbox/retry với cùng `commandId` và subscriber idempotent.

## 8. Async publish và Spring Integration MQTT events

Handler có thể publish bất đồng bộ:

~~~java
handler.setAsync(true);
handler.setAsyncEvents(true);
~~~

Với `setAsync(true)`, caller có thể nhận return trước khi broker hoàn tất acknowledgement; kết quả muộn cần event/callback/error handling. Ở những Spring Integration versions hỗ trợ, `setAsyncEvents(true)` bật publish notifications như:

- `MqttMessageSentEvent`: cho biết việc publish được gửi theo bước tương ứng của adapter.
- `MqttMessageDeliveredEvent`: phản ánh callback delivery completion khi điều kiện được đáp ứng.

**Cần kiểm tra phiên bản:** cách phát event, tên trường correlation, interaction với QoS 0 và chế độ sync/async là chi tiết API. Không hứa mỗi `send()` sẽ tương ứng đúng một event Delivered, nhất là khi connection mất hoặc application restart. “Sent” **không đồng nghĩa PUBACK**, còn “Delivered” **không đồng nghĩa thiết bị đã thi hành**.

### 8.1. Quan sát event bằng Spring EventListener

~~~java
package demo.mqttdelivery;

import org.springframework.context.event.EventListener;
import org.springframework.integration.mqtt.event.MqttMessageDeliveredEvent;
import org.springframework.integration.mqtt.event.MqttMessageSentEvent;
import org.springframework.stereotype.Component;

@Component
class MqttPublishEventObserver {

    @EventListener
    public void sent(MqttMessageSentEvent event) {
        System.out.println("MQTT SENT: " + event);
    }

    @EventListener
    public void delivered(MqttMessageDeliveredEvent event) {
        System.out.println("MQTT DELIVERED: " + event);
    }
}
~~~

Đây là log demo, không phải implementation production. Muốn correlate events vào outbox, cần dùng các trường được API version bảo đảm; không log full payload/secrets hoặc dùng một MQTT packet ID đơn lẻ làm khóa durable. Nếu version không có event hỗ trợ mong đợi, phải dùng API khác được công bố và kiểm thử trên đúng dependency.

### 8.2. Sync và async so sánh

| Khía cạnh | `setAsync(false)` | `setAsync(true)` |
| --- | --- | --- |
| Caller | Có thể chờ tới completion/timeout. | Thường trả sớm hơn. |
| Error path | Một số lỗi có thể lan trên cùng call stack. | Lỗi có thể đến sau qua event/callback. |
| Completion timeout | Quan trọng với chờ sync publish. | Không coi là hạn chót của mọi kết quả async. |
| Throughput | Có thể bị giới hạn bởi publish latency. | Có thể cao hơn nhưng đòi hỏi quản lý in-flight. |
| Durability | Không tự bền vững. | Không tự bền vững. |
| Business ACK | Không tự có. | Không tự có. |

### 8.3. Không tự thay callback của Spring-managed Paho client

Paho raw API cho phép `setCallback(...)`, nhưng MQTT inbound/outbound adapters của Spring sử dụng callback/lifecycle nội bộ. Không tự chiếm callback trong ứng dụng để “lấy token” nếu cách đó phá endpoint behavior; dùng hooks/events được framework version hỗ trợ hoặc một integration layer riêng có kiểm thử.

## 9. Các thời hạn chờ thuộc các tầng khác nhau

| Tham số | Ví dụ | Đơn vị | Mục đích |
| --- | --- | --- | --- |
| `setConnectionTimeout(10)` | Paho options | Giây | Giới hạn thiết lập MQTT connection. |
| `setKeepAliveInterval(30)` | Paho options | Giây | Duy trì/phát hiện connection theo protocol. |
| `setCompletionTimeout(5000)` | Spring outbound handler | Mili giây | Chờ publish operation theo handler mode. |
| `setRecoveryInterval(10000)` | Spring inbound adapter | Mili giây | Điều tiết recovery của inbound endpoint. |
| `businessAckTimeout=30s` | Application policy | Tùy hợp đồng | Đợi command ACK sau khi subscriber thực thi. |

~~~mermaid
sequenceDiagram
    participant APP as Application
    participant B as Broker
    participant D as Device
    APP->>B: PUBLISH QoS 1 lúc 00.1s
    B--xAPP: PUBACK bị chặn
    Note over APP: Completion timeout tại 05.0s
    B->>D: PUBLISH command
    D->>D: Thực thi trong 7s
    D->>B: ACK business tại 12.0s
    B->>APP: Business ACK tới sau publish timeout
~~~

Trong tình huống này, nếu backend đã gửi lại command mới lúc 5 giây thì device có thể nhận hai lệnh. Vì vậy business state phải cho phép **ACK đến sau publish timeout**, và worker phải dừng retry nếu ACK hợp lệ đã được commit.

## 10. Mô hình trạng thái: không ép kết quả về true/false

~~~mermaid
stateDiagram-v2
    [*] --> CREATED
    CREATED --> READY: Persist outbox
    READY --> PUBLISHING: Worker claim
    PUBLISHING --> MQTT_PUBLISHED: Completion signal observed
    PUBLISHING --> PUBLISH_UNCERTAIN: Timeout / crash / disconnect
    PUBLISH_UNCERTAIN --> PUBLISHING: Retry cùng eventId
    MQTT_PUBLISHED --> BUSINESS_PENDING: Chờ ACK
    BUSINESS_PENDING --> BUSINESS_ACKNOWLEDGED: ACK valid + DB commit
    PUBLISH_UNCERTAIN --> BUSINESS_ACKNOWLEDGED: ACK đến muộn, hợp lệ
    BUSINESS_PENDING --> REVIEW: Quá business timeout
    BUSINESS_ACKNOWLEDGED --> [*]
~~~

Các trạng thái là **mô hình do ứng dụng định nghĩa**, không phải enum Paho/Spring được cung cấp sẵn. Khi có callback trên thread khác, retry worker và ACK consumer, các transition cần kiểm soát concurrency/idempotency.

### 10.1. Outbox record có gì?

~~~json
{
  "commandId": "cmd-1001",
  "tenantId": "tenant-a",
  "deviceId": "device-17",
  "topic": "devices/device-17/commands",
  "payload": {
    "commandId": "cmd-1001",
    "deviceId": "device-17",
    "action": "TURN_ON"
  },
  "qos": 1,
  "retained": false,
  "publishState": "PUBLISH_UNCERTAIN",
  "attemptCount": 2,
  "businessState": "PENDING"
}
~~~

Schema trên **chỉ là ví dụ**; Spring Integration/Paho không tự tạo record này. Production cần persisted event ID, topic quyết định trước, byte payload/schema version, retry budget, error code, claim owner và timestamps.

### 10.2. Các định danh khác nhau

| ID | Phạm vi | Dùng làm idempotency key? |
| --- | --- | --- |
| Spring Message `id` | Instance của một Spring message. | Không tự mặc định. |
| MQTT packet ID | Giao thức, client session và thời điểm. | **Không** là khóa toàn cục. |
| MQTT Client ID | Một client session/connection logic. | Không phải command ID. |
| Business `commandId` | Một lệnh xuyên retry/restart. | **Có**, theo namespace/tenant. |
| Trace ID | Quan sát chuỗi thao tác. | Chỉ khi contract chủ động quy định, không tự thay business ID. |

### 10.3. Idempotency của thiết bị

Một device nhận `commandId=cmd-1001` hai lần cần nhận ra đó là **cùng business command**. Nếu đã xử lý, nó có thể trả ACK tương ứng thay vì lặp side effect.

~~~text
onCommand(command):
    verify identity, authorization, schema, expiry
    if commandId already applied:
        republish recorded ACK
        return
    use idempotent/fenced side-effect policy
    persist result in a recoverable manner
    publish ACK(commandId, status)
~~~

Database unique constraint có ích, nhưng không tự giải quyết mọi side effect vật lý nằm ngoài transaction. Command kiểu “đặt desired state=ON” thường dễ idempotent hơn “tăng công suất thêm 10 đơn vị”; cần thiết kế theo domain.

## 11. Lựa chọn sync, async và outbox theo yêu cầu nghiệp vụ

| Tình huống | Lựa chọn thường phù hợp | Lưu ý |
| --- | --- | --- |
| Telemetry ít quan trọng, tần suất cao | QoS 0/async khi SLA cho phép mất mẫu. | Không dùng token completion làm bảo đảm broker nhận. |
| Event đáng tin cậy, cần retry | QoS 1 + outbox/persistent event store. | At-least-once, dedup ở consumer. |
| Command quan trọng | QoS 1/2 theo SLA + stable command ID + business ACK. | MQTT delivery token không thay thiết bị xác nhận. |
| HTTP request latency thấp | Persist outbox, trả command ID, publish ngoài request. | Hỗ trợ status endpoint/webhook/event. |
| Cần phân tích lỗi đơn giản trong lab | Sync handler + completionTimeout. | Vẫn có uncertain outcome. |
| Cần nhiều publishes đồng thời | Async handler + bounded in-flight/error tracking. | Tránh memory/queue growth, đảm bảo shutdown/recovery. |

**Không để DB transaction mở trong lúc đợi broker token.** Database commit không atomic với một MQTT PUBLISH; dùng transactional outbox để ghi business event và việc cần publish trong cùng DB transaction, sau đó worker gửi MQTT. Kể cả khi worker gửi thành công rồi crash trước khi update outbox, subscriber vẫn cần idempotent.

## 12. Cấu trúc bài thực hành Spring Boot

Ví dụ có hai hướng:

- **Outbound:** Spring channel `mqtt.commands.out` → `MqttPahoMessageHandler` → topic `devices/{deviceId}/commands`.
- **Inbound:** MQTT broker → `MqttPahoMessageDrivenChannelAdapter` subscribe `devices/+/ack` → `mqtt.acks.in` → JSON parser/validator → `AckSink`.

~~~mermaid
flowchart LR
    API["Service nhận Command"]
    OUT["mqtt.commands.out"]
    H["Paho outbound handler<br/>async + events"]
    B[("MQTT broker")]
    D["Device"]
    I["Inbound ACK adapter"]
    ACKCH["mqtt.acks.in"]
    V["Validate ACK JSON / topic"]
    S["ACK sink / DB"]
    API --> OUT --> H --> B --> D
    D -->|"PUBLISH ACK"| B --> I --> ACKCH --> V --> S
~~~

Các tệp minh họa:

~~~text
src/main/java/demo/mqttdelivery/
    MqttDeliveryApplication.java
    MqttDeliveryConfiguration.java
    Command.java
    CommandPublisher.java
    CommandAck.java
    AckSink.java
    AckFlowConfiguration.java
    MqttPublishEventObserver.java

src/main/resources/application.properties

src/test/java/demo/mqttdelivery/
    AckFlowTest.java
~~~

Dùng Java 17+, Spring Boot/Spring Integration MQTT với dependency management tương thích. Chạy demo cần một **MQTT broker thực**; Spring Boot không tự tạo broker.

### 12.1. Maven dependencies

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-integration</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.integration</groupId>
        <artifactId>spring-integration-mqtt</artifactId>
    </dependency>
    <dependency>
        <groupId>com.fasterxml.jackson.core</groupId>
        <artifactId>jackson-databind</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

BOM của Spring Boot nên kiểm soát version tương thích; tránh ghép tùy ý các major versions và trộn API MQTT v3 với v5.

### 12.2. Application và properties

~~~java
package demo.mqttdelivery;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MqttDeliveryApplication {

    public static void main(String[] args) {
        SpringApplication.run(MqttDeliveryApplication.class, args);
    }
}
~~~

`application.properties`:

~~~properties
app.mqtt.broker-url=${MQTT_BROKER_URL:tcp://localhost:1883}
app.mqtt.publisher-id=${MQTT_PUBLISHER_ID:commands-publisher-local-1}
app.mqtt.ack-subscriber-id=${MQTT_ACK_SUBSCRIBER_ID:acks-in-local-1}
~~~

Client IDs riêng cho inbound/outbound, không dùng trùng giữa các active instances. Trong production dùng TLS, credentials từ secrets và broker ACL giới hạn publish commands / subscribe ACK topics.

### 12.3. DTO Command và business ACK

~~~java
package demo.mqttdelivery;

record Command(String commandId, String deviceId, String action) {

    Command {
        if (commandId == null || commandId.isBlank()) {
            throw new IllegalArgumentException("Thiếu commandId");
        }
        if (deviceId == null
                || !deviceId.matches("[A-Za-z0-9_-]{1,40}")) {
            throw new IllegalArgumentException("deviceId không hợp lệ");
        }
        if (!"TURN_ON".equals(action)
                && !"TURN_OFF".equals(action)) {
            throw new IllegalArgumentException(
                    "Không hỗ trợ action: " + action);
        }
    }
}
~~~

~~~java
package demo.mqttdelivery;

record CommandAck(String commandId, String deviceId, String result) {

    CommandAck {
        if (commandId == null || commandId.isBlank()) {
            throw new IllegalArgumentException("Thiếu commandId ACK");
        }
        if (deviceId == null
                || !deviceId.matches("[A-Za-z0-9_-]{1,40}")) {
            throw new IllegalArgumentException("deviceId ACK không hợp lệ");
        }
        if (!"APPLIED".equals(result)
                && !"REJECTED".equals(result)) {
            throw new IllegalArgumentException(
                    "Kết quả ACK không hợp lệ");
        }
    }
}
~~~

Đây là hai record package-private trong cùng package. ACK `APPLIED` khác ACK `REJECTED`: cả hai là **một thông điệp nghiệp vụ đã nhận**, nhưng kết quả của command khác nhau. Khi dùng thêm `ACCEPTED` hay `IN_PROGRESS`, phải mở rộng schema/state machine, không coi mọi ACK là hoàn tất.

### 12.4. Cấu hình Paho client factory và hai MQTT endpoints

~~~java
package demo.mqttdelivery;

import org.eclipse.paho.client.mqttv3.MqttConnectOptions;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.mqtt.core.DefaultMqttPahoClientFactory;
import org.springframework.integration.mqtt.core.MqttPahoClientFactory;
import org.springframework.integration.mqtt.inbound.MqttPahoMessageDrivenChannelAdapter;
import org.springframework.integration.mqtt.outbound.MqttPahoMessageHandler;
import org.springframework.integration.mqtt.support.DefaultPahoMessageConverter;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHandler;

@Configuration
@EnableIntegration
class MqttDeliveryConfiguration {

    @Bean
    MqttPahoClientFactory mqttClientFactory(
            @Value("${app.mqtt.broker-url}") String brokerUrl) {

        var options = new MqttConnectOptions();
        options.setServerURIs(new String[] {brokerUrl});
        options.setConnectionTimeout(10);
        options.setKeepAliveInterval(30);
        options.setCleanSession(true);

        var factory = new DefaultMqttPahoClientFactory();
        factory.setConnectionOptions(options);
        return factory;
    }

    @Bean(name = "mqtt.commands.out")
    MessageChannel commandsOutput() {
        return new DirectChannel();
    }

    @Bean(name = "mqtt.acks.in")
    MessageChannel acksInput() {
        return new DirectChannel();
    }

    @Bean(name = "mqttPublisher")
    MqttPahoMessageHandler mqttPublisher(
            MqttPahoClientFactory factory,
            @Value("${app.mqtt.publisher-id}") String clientId) {

        var publisher = new MqttPahoMessageHandler(
                clientId, factory);
        publisher.setDefaultTopic("diagnostics/unrouted");
        publisher.setDefaultQos(1);
        publisher.setDefaultRetained(false);
        publisher.setConverter(new DefaultPahoMessageConverter());

        // Publish bất đồng bộ, phát events ở version hỗ trợ.
        publisher.setAsync(true);
        publisher.setAsyncEvents(true);
        publisher.setCompletionTimeout(5000);
        return publisher;
    }

    @Bean
    IntegrationFlow commandsOutboundFlow(
            @Qualifier("mqttPublisher") MessageHandler publisher) {
        return IntegrationFlow.from("mqtt.commands.out")
                .handle(publisher)
                .get();
    }

    @Bean
    MqttPahoMessageDrivenChannelAdapter ackInboundAdapter(
            MqttPahoClientFactory factory,
            @Qualifier("mqtt.acks.in") MessageChannel ackInput,
            @Value("${app.mqtt.ack-subscriber-id}") String clientId) {

        var adapter = new MqttPahoMessageDrivenChannelAdapter(
                clientId, factory, "devices/+/ack");
        adapter.setQos(1);
        adapter.setRecoveryInterval(10000);
        adapter.setConverter(new DefaultPahoMessageConverter());
        adapter.setOutputChannel(ackInput);
        return adapter;
    }
}
~~~

Đặc điểm thiết kế:

1. `mqttClientFactory` tạo connection options của Paho MQTT v3. Hai adapters có thể dùng chung factory options nhưng **Client ID phải khác nhau**.
2. `commandsOutboundFlow` dùng `DirectChannel` để giao Spring `Message<?>` tới outbound handler.
3. Publisher được bật `setAsync(true)` và `setAsyncEvents(true)`. Caller có thể về trước publish completion; sự kiện chỉ đáng tin trong phạm vi được phiên bản hỗ trợ.
4. `ackInboundAdapter` subscribe filter `devices/+/ack` ở QoS 1 rồi phát message qua `mqtt.acks.in`. Đây là MQTT **message-driven** adapter, không dùng `@Poller` để đọc broker.
5. `setRecoveryInterval(10000)` là khoảng recovery endpoint bằng mili giây; `setCompletionTimeout(5000)` liên quan publish completion. Cả hai không phải business ACK timeout.
6. Topic `diagnostics/unrouted` chỉ là fallback minh họa. Với command production, nên reject trước handler nếu thiếu topic đúng thay vì để fallback gửi lệnh đến đích không mong muốn.

Với broker production, phải dùng TLS/authentication/ACL. Config bean tồn tại không có nghĩa publisher hoặc inbound subscriber đã kết nối thành công; cần kiểm soát startup, readiness, reconnect và session state.

### 12.5. Service serialize command thành JSON rồi publish

~~~java
package demo.mqttdelivery;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.mqtt.support.MqttHeaders;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
class CommandPublisher {

    private final MessageChannel channel;
    private final ObjectMapper mapper;

    CommandPublisher(
            @Qualifier("mqtt.commands.out") MessageChannel channel,
            ObjectMapper mapper) {
        this.channel = channel;
        this.mapper = mapper;
    }

    boolean requestPublish(Command command)
            throws JsonProcessingException {
        if (command == null) {
            throw new IllegalArgumentException("Thiếu command");
        }

        String json = mapper.writeValueAsString(command);
        String topic = "devices/" + command.deviceId() + "/commands";

        return channel.send(MessageBuilder.withPayload(json)
                .setHeader(MqttHeaders.TOPIC, topic)
                .setHeader(MqttHeaders.QOS, 1)
                .setHeader(MqttHeaders.RETAINED, false)
                .build());
    }
}
~~~

Caller dùng:

~~~java
commandPublisher.requestPublish(
        new Command("cmd-1001", "device-17", "TURN_ON"));
~~~

Tên `requestPublish` cố ý thể hiện **yêu cầu gửi**, không phải `executeDeviceCommandAndConfirm`. Với handler async, boolean trả về chỉ là kết quả bàn giao theo Spring channel, chưa chứng minh broker nhận hoặc device thi hành.

Một command ID phải do tầng nghiệp vụ cấp và lưu bền vững trước khi publish. Nếu client HTTP được phép tự chọn ID, phải chống ghi đè ID thuộc tenant/device khác.

### 12.6. ACK sink minh họa

~~~java
package demo.mqttdelivery;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

class AckSink {

    private final List<CommandAck> accepted =
            new CopyOnWriteArrayList<>();

    void accept(CommandAck ack) {
        accepted.add(ack);
    }

    List<CommandAck> snapshot() {
        return List.copyOf(accepted);
    }

    void clear() {
        accepted.clear();
    }
}
~~~

Sink này chỉ để học/testing, **không lưu qua restart**. Production cần database/inbox, kiểm tra `commandId` đang tồn tại và thuộc đúng device/tenant, idempotent transitions, expiry và audit. ACK message có thể đến trùng hoặc đến muộn.

### 12.7. ACK flow: inbound business confirmation độc lập

~~~java
package demo.mqttdelivery;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.mqtt.support.MqttHeaders;

@Configuration
class AckFlowConfiguration {

    @Bean
    ObjectMapper mqttObjectMapper() {
        return new ObjectMapper();
    }

    @Bean
    AckSink ackSink() {
        return new AckSink();
    }

    @Bean
    IntegrationFlow ackFlow(
            ObjectMapper mqttObjectMapper,
            AckSink sink) {

        return IntegrationFlow.from("mqtt.acks.in")
                .handle(String.class, (json, headers) -> {
                    Object header =
                            headers.get(MqttHeaders.RECEIVED_TOPIC);

                    if (!(header instanceof String topic)
                            || !topic.matches(
                                    "devices/[A-Za-z0-9_-]{1,40}/ack")) {
                        throw new IllegalArgumentException(
                                "ACK topic không hợp lệ");
                    }

                    final CommandAck ack;
                    try {
                        ack = mqttObjectMapper.readValue(
                                json, CommandAck.class);
                    } catch (JsonProcessingException ex) {
                        throw new IllegalArgumentException(
                                "ACK JSON không hợp lệ", ex);
                    }

                    String expected = "devices/"
                            + ack.deviceId() + "/ack";
                    if (!expected.equals(topic)) {
                        throw new IllegalArgumentException(
                                "ACK deviceId khác topic");
                    }

                    sink.accept(ack);
                    return null;
                })
                .get();
    }
}
~~~

**Đây là hai publications độc lập:** command đi từ backend sang device, ACK đi từ device trở lại broker rồi backend. `MqttPahoMessageHandler` outbound không thể tự tạo Java reply DTO chỉ nhờ MQTT broker gửi `PUBACK`.

`MqttHeaders.RECEIVED_TOPIC` mang **topic inbound thực tế**, khác `MqttHeaders.TOPIC` dành cho outbound. Một Spring custom header như `commandId` không tự đi xuyên MQTT v3; device phải đọc ID từ JSON và đưa nó vào JSON ACK.

Trong production, ACK JSON hợp lệ **không tự bảo đảm** nguồn gửi là thiết bị được tin cậy. Broker ACL phải ràng buộc publisher với topic, backend phải xác minh command owner và ghi kết quả vào DB idempotently. ACK giả có thể gây báo thành công sai.

### 12.8. Observability cho publisher async

`MqttPublishEventObserver` ở mục 8 có thể được Spring component scanning nạp để quan sát events. Nó ghi log kỹ thuật, **không** đánh dấu `APPLIED` chỉ khi thấy `MqttMessageDeliveredEvent`.

Khi triển khai production, sử dụng correlation fields mà API version thực sự bảo đảm và chỉ ghi trạng thái MQTT publish kỹ thuật khi có tín hiệu phù hợp. Đối với business state, chỉ dùng ACK đã kiểm tra và DB commit.

### 12.9. Khi API ngoài không thể đợi ACK

Một HTTP API có thể tạo command/outbox và trả:

~~~json
{
  "commandId": "cmd-1001",
  "state": "ACCEPTED",
  "statusUrl": "/commands/cmd-1001"
}
~~~

HTTP `202 Accepted` thể hiện backend nhận công việc, **không** có nghĩa thiết bị đã thực hiện. `statusUrl` chỉ là path minh họa; Spring Integration MQTT không tự tạo REST endpoint đó. Khi HTTP timeout ngắn hơn MQTT/business processing, mô hình trả command ID và truy vấn/truyền status thường rõ hơn việc cố giữ request mở đến khi thiết bị trả ACK.

## 13. Test ACK flow không cần MQTT broker

Test này chứng minh **Spring channel, JSON parser và business topic contract**. Nó không thể chứng minh Paho token, PUBACK hay broker delivery. Không nạp `MqttDeliveryConfiguration` trong test vì sẽ tạo endpoint kết nối mạng; chỉ nạp `AckFlowConfiguration` và test channel.

~~~java
package demo.mqttdelivery;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.mqtt.support.MqttHeaders;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = {
        AckFlowConfiguration.class,
        AckFlowTestChannels.class
})
class AckFlowTest {

    @Autowired
    @Qualifier("mqtt.acks.in")
    MessageChannel input;

    @Autowired
    AckSink sink;

    @BeforeEach
    void reset() {
        sink.clear();
    }

    @Test
    void acceptsValidAck() {
        String json = "{\"commandId\":\"cmd-test-1\","
                + "\"deviceId\":\"device-17\","
                + "\"result\":\"APPLIED\"}";

        boolean sent = input.send(
                MessageBuilder.withPayload(json)
                        .setHeader(MqttHeaders.RECEIVED_TOPIC,
                                "devices/device-17/ack")
                        .build());

        assertTrue(sent);
        assertEquals(
                List.of(new CommandAck(
                        "cmd-test-1", "device-17", "APPLIED")),
                sink.snapshot());
    }

    @Test
    void rejectsDeviceMismatch() {
        String json = "{\"commandId\":\"cmd-test-2\","
                + "\"deviceId\":\"device-21\","
                + "\"result\":\"APPLIED\"}";

        assertThrows(RuntimeException.class, () ->
                input.send(MessageBuilder.withPayload(json)
                        .setHeader(MqttHeaders.RECEIVED_TOPIC,
                                "devices/device-17/ack")
                        .build()));

        assertTrue(sink.snapshot().isEmpty());
    }

    @Test
    void rejectsMalformedJson() {
        assertThrows(RuntimeException.class, () ->
                input.send(MessageBuilder.withPayload(
                        "{\"commandId\":")
                        .setHeader(MqttHeaders.RECEIVED_TOPIC,
                                "devices/device-17/ack")
                        .build()));

        assertTrue(sink.snapshot().isEmpty());
    }
}

@Configuration
@EnableIntegration
class AckFlowTestChannels {

    @Bean(name = "mqtt.acks.in")
    MessageChannel ackInput() {
        return new DirectChannel();
    }
}
~~~

Với `DirectChannel`, test gọi handler đồng bộ nên có thể assert `sink.snapshot()` sau `send(...)`. Test sử dụng `RuntimeException` tổng quát để không phụ thuộc lớp wrapper messaging exception theo framework version; khi triển khai thật cần kiểm tra cause chain/errorChannel.

### 13.1. Test publisher header contract với fake handler

Một fake `MessageHandler` có thể lưu topic, payload, QoS và retained:

~~~java
package demo.mqttdelivery;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.springframework.integration.mqtt.support.MqttHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHandler;

record OutboundObservation(
        String topic, String payload, int qos, boolean retained) {}

class RecordingPublisher implements MessageHandler {

    private final List<OutboundObservation> messages =
            new CopyOnWriteArrayList<>();

    @Override
    public void handleMessage(Message<?> message) {
        messages.add(new OutboundObservation(
                (String) message.getHeaders().get(MqttHeaders.TOPIC),
                (String) message.getPayload(),
                (Integer) message.getHeaders().get(MqttHeaders.QOS),
                (Boolean) message.getHeaders().get(MqttHeaders.RETAINED)));
    }

    List<OutboundObservation> snapshot() {
        return List.copyOf(messages);
    }
}
~~~

Trong test context, tạo bean `mqtt.commands.out`, một `IntegrationFlow.from("mqtt.commands.out").handle(recordingPublisher).get()`, `ObjectMapper` và `CommandPublisher`. Khi gọi `requestPublish(new Command("cmd-test-3","device-17","TURN_ON"))`, kiểm tra recorder nhận:

~~~text
topic:    devices/device-17/commands
payload:  {"commandId":"cmd-test-3","deviceId":"device-17","action":"TURN_ON"}
qos:      1
retained: false
~~~

**Giới hạn:** fake handler không tạo Paho delivery token, không gửi MQTT packet và không chứng minh broker đã nhận message. Cố `Thread.sleep(5001)` trong fake handler chỉ đo độ trễ code test, không phải completion timeout của Paho.

### 13.2. Các test business state cần có

- Reject command thiếu ID, device ID chứa `/`/`+` hoặc action không hợp lệ.
- Reject ACK có device ID khác topic, sai tenant hoặc command chưa từng phát.
- Idempotency: hai ACK giống nhau không sinh hai business side effects.
- ACK `REJECTED` không biến thành `APPLIED`.
- ACK đến muộn khi outbox `PUBLISH_UNCERTAIN` vẫn được đối soát đúng.
- Application restart phải phục hồi outbox pending/uncertain, không chỉ token trong memory.
- Broker ACL không cho thiết bị A publish ACK thay thiết bị B.

## 14. Test delivery token với MQTT broker thật

Phải có broker test do người thử nghiệm kiểm soát. Các lệnh sau giả định Mosquitto CLI và broker test ở `localhost:1883`. Không ngắt production broker hoặc hạ TLS production chỉ để kiểm thử.

### 14.1. Subscriber quan sát command

Terminal A:

~~~bash
mosquitto_sub -h localhost -p 1883 \
  -i demo-command-subscriber-1 \
  -t 'devices/+/commands' -q 1 -v
~~~

Chạy `RawPahoTokenDemo` hoặc gọi `CommandPublisher.requestPublish(...)` trong Spring Boot. Subscriber thấy JSON trên topic phù hợp nếu broker/client hoạt động và có quyền.

**Đây chỉ là kiểm chứng giao nhận ở subscriber thử nghiệm.** Một CLI hiển thị payload không chứng minh actuator đã bật hoặc service downstream đã commit DB.

### 14.2. ACK nghiệp vụ phải tách riêng

Terminal B:

~~~bash
mosquitto_sub -h localhost -p 1883 \
  -i demo-ack-subscriber-1 \
  -t 'devices/+/ack' -q 1 -v
~~~

Giả lập ACK cho lab:

~~~bash
mosquitto_pub -h localhost -p 1883 \
  -t 'devices/device-17/ack' -q 1 \
  -m '{"commandId":"cmd-1001","deviceId":"device-17","result":"APPLIED"}'
~~~

Spring inbound flow có thể nhận và parse ACK. Nhưng đây là **ACK giả do terminal test tạo ra**, không chứng minh thiết bị thật đã thực hiện command. Khi production, chỉ thiết bị được xác thực và cấp quyền phù hợp mới được publish ACK.

### 14.3. So sánh QoS 0, 1, 2

Sửa tham số QoS của `RawPahoTokenDemo` thành 0, 1, 2 ở các lượt thử, quan sát duration và callback:

- QoS 0 không có PUBACK, nên token complete không là broker ACK.
- QoS 1 có PUBACK; ACK lost có thể gây retransmission/uncertain outcome.
- QoS 2 hoàn tất giao thức sau PUBCOMP; không chứng minh DB exactly-once.

Cần kiểm tra hành vi trên đúng Paho/Spring/broker versions của dự án, không chỉ đo một đường localhost lý tưởng.

### 14.4. Tạo publish timeout có ý nghĩa

Dùng network proxy hoặc fault injection để chặn/trễ PUBACK **sau khi broker đã nhận PUBLISH**:

~~~mermaid
sequenceDiagram
    participant P as Paho client
    participant B as Broker
    participant S as Subscriber
    P->>B: PUBLISH QoS1 cmd-1001
    B->>S: PUBLISH cmd-1001
    B--xP: PUBACK bị chặn
    Note over P: waitForCompletion timeout
    Note over S: Có thể đã xử lý cmd-1001
~~~

Nếu chỉ tắt toàn bộ broker, có thể gặp `connection lost` thay vì publish token timeout. Phải tách **initial connect failure**, **reconnect failure**, **completion timeout** và **business ACK timeout** khi ghi kết quả test.

### 14.5. Test matrix

| Kịch bản | Điều cần kiểm chứng |
| --- | --- |
| QoS 0 token | Không diễn giải complete như PUBACK. |
| QoS 1 token | Completion theo PUBACK. |
| QoS 2 token | Completion theo QoS 2 handshake. |
| Sync handler | Caller có thể chờ completion/timeout. |
| Async handler | Result có thể đến sau return, cần events/callback tracking. |
| ACK bị mất | Broker/subscriber đã nhận nhưng publisher timeout. |
| App crash sau PUBACK | Outbox replay có thể duplicate, subscriber cần dedup. |
| Subscriber offline | Publisher vẫn có thể được broker ACK; business ACK chưa có. |
| Client ID trùng | Có thể xảy ra disconnect/reconnect loop. |
| ACK đến muộn | State reconciliation không đánh dấu sai. |
| Retained command | Thấy nguy cơ replay command cũ trong broker lab. |
| Broker offline trước startup | Startup recovery khác mất connection sau startup. |
| Broker ACL từ chối | Phân loại lỗi bảo mật/config, không retry vô hạn. |

## 15. Lỗi publish, timeout và retry nhiều tầng

~~~mermaid
flowchart TD
    OUTBOX["Durable outbox READY"]
    PUBLISH["MQTT publish attempt"]
    DECIDE{"Outcome quan sát?"}
    SENT["MQTT_PUBLISHED"]
    UNKNOWN["PUBLISH_UNCERTAIN"]
    REJECT["FAILED / quarantine"]
    RETRY["Backoff cùng eventId"]
    ACK["ACK từ thiết bị hợp lệ"]
    DONE["BUSINESS_ACKNOWLEDGED"]
    OUTBOX --> PUBLISH --> DECIDE
    DECIDE -->|"Completion observed"| SENT
    DECIDE -->|"Timeout/connection lost"| UNKNOWN
    DECIDE -->|"ACL/schema/topic invalid"| REJECT
    UNKNOWN --> RETRY --> PUBLISH
    SENT --> ACK --> DONE
    UNKNOWN --> ACK
~~~

Có ít nhất hai tầng retry có thể chồng lên nhau:

1. MQTT/Paho có cơ chế retransmission cho packets chưa được xác nhận theo QoS.
2. Ứng dụng thấy timeout rồi tạo một PUBLISH **mới** từ outbox.

Vì thế thiết bị có thể nhận cùng business command nhiều lần. **Dùng `commandId`/`eventId` để dedup**, không dựa riêng vào packet ID hoặc MQTT DUP flag.

| Nhóm lỗi | Policy |
| --- | --- |
| Network/disconnect tạm thời | Retry giới hạn, backoff/jitter, giữ business ID. |
| Publish token timeout | Ghi uncertain, đối soát ACK, retry idempotent nếu cần. |
| Topic không hợp lệ | Reject/quarantine, không gửi vô hạn. |
| Broker ACL/credential lỗi | Alert và sửa config, không retry storm. |
| JSON/schema sai | Non-retryable data error. |
| Thiết bị ACK `REJECTED` | Ghi nhận business failure, không coi là MQTT publish failure. |
| DB cập nhật ACK thất bại | Inbox/idempotent transaction/retry riêng. |

### 15.1. Spring error channel khác callback Paho

Spring Integration hỗ trợ `ErrorMessage`, `errorChannel` và advice ở những endpoint/flow được cấu hình tương ứng. Không giả định **mọi Paho async callback exception** đều được tự động chuyển vào một Spring error channel bất kỳ.

Sync handler trên `DirectChannel` có thể lan một số lỗi về caller; async handler, executor, poller có thể ghi nhận lỗi qua event/callback/error flow khác. Test đúng cách wiring và version thay vì chỉ bắt `Exception` quanh `send()`.

### 15.2. Không retry vô hạn payload hỏng

Nếu command JSON sai schema hoặc topic thuộc tenant khác, broker reconnect không sửa được dữ liệu. Những lỗi này cần reject/audit/quarantine, không đưa ngược source topic theo vòng lặp. Với lỗi network tạm thời, retry phải có ngân sách thời gian/số lần và cơ chế giảm tải.

## 16. Transactional outbox: bền vững hơn delivery token

~~~mermaid
flowchart LR
    API["Business API"]
    DB[("DB + transactional outbox")]
    WORKER["Outbox worker claim/retry"]
    FLOW["Spring MQTT outbound flow"]
    BROKER[("MQTT broker")]
    DEVICE["Device"]
    IN["MQTT ACK inbound"]
    ACKDB[("Business state DB")]
    API -->|"Một transaction"| DB
    DB --> WORKER --> FLOW --> BROKER --> DEVICE
    DEVICE -->|"PUBLISH ACK(commandId)"| BROKER
    BROKER --> IN --> ACKDB
    ACKDB -. "Reconcile retry" .-> WORKER
~~~

Một durable outbox record nên lưu:

| Trường | Chức năng |
| --- | --- |
| `event_id`/`command_id` | Khóa nghiệp vụ bền qua restart/retry. |
| `tenant_id`/`device_id` | Định danh/quyền của command. |
| `mqtt_topic` | Topic đã được validate và chọn. |
| `payload_json`/`payload_bytes` | Dữ liệu cần publish và command ID nằm trong payload. |
| `qos`/`retained` | MQTT delivery policy. |
| `publish_state` | READY/PUBLISHING/PUBLISHED/UNCERTAIN/FAILED. |
| `business_state` | PENDING/APPLIED/REJECTED/UNKNOWN. |
| `attempt_count`/`next_retry_at` | Backoff/budget. |
| `claim_owner`/`claim_until` | Tránh hai workers cùng claim bình thường. |
| `last_error`/`created_at` | Audit/monitoring. |

### 16.1. Luồng outbox

1. Business API xác thực, validate và tạo `commandId`.
2. Ghi business command + outbox record trong **cùng DB transaction**.
3. Worker claim record và publish Spring message với topic/QoS/retained đã xác định.
4. Khi có MQTT completion được quan sát, cập nhật `MQTT_PUBLISHED`; timeout thì `PUBLISH_UNCERTAIN`.
5. Device xử lý idempotent, publish ACK theo `commandId`.
6. ACK consumer validate owner và update DB idempotent.
7. Sau restart worker đọc outbox chưa kết thúc, đối soát rồi retry đúng policy.

Không giữ DB transaction mở trong lúc đợi MQTT token rồi cho rằng DB và broker commit atomic. Dù outbox giải quyết atomic ghi business event + ý định publish trong DB, chặng gửi MQTT vẫn có thể bị lặp do crash sau PUBACK trước khi update outbox.

### 16.2. Correlation khi dùng async events

Nếu handler async phát events, application cần map **event kỹ thuật** với **outbox record**. Packet ID có thể được reuse, event muộn có thể đến sau reconnect, mapping memory biến mất khi crash. Không lưu chỉ `packetId` làm khóa xuyên thời gian.

Nếu API/version không bảo đảm correlation đủ mạnh, một lựa chọn là publish sync từ worker và xử lý uncertain outcome đúng cách, hoặc xây integration layer chuyên biệt với callback/recovery contract được kiểm chứng. Không khẳng định DeliveredEvent luôn chứa `commandId` nếu chưa xác minh.

## 17. ACK security và business state

Một ACK payload có `result=APPLIED` không tự chứng minh nó do thiết bị đúng gửi. Backend cần:

- MQTT authentication, TLS và topic ACL theo device/tenant.
- Kiểm tra `commandId` tồn tại, thuộc đúng device và còn ở trạng thái cho phép.
- Đối chiếu topic thực nhận với `deviceId` trong JSON.
- Chống ACK duplicate/out-of-order bằng unique key, sequence/epoch nếu cần.
- Business transition tách `REJECTED`, `APPLIED` và `PENDING`.
- Validation, audit, hạn chế dữ liệu nhạy cảm trong logs.
- ACK expiry, retry/đối soát và phản hồi rõ khi device không bao giờ xác nhận.

### 17.1. ACK ACCEPTED khác APPLIED

Nếu device chỉ phát `ACCEPTED` sau khi nhận nhưng chưa chạy actuator, backend không được ghi `APPLIED`. Một contract nhiều bước có thể là:

~~~text
CREATED → MQTT_PUBLISHED → DEVICE_ACCEPTED → DEVICE_APPLIED
~~~

Ví dụ `CommandAck` trong bài chỉ chấp nhận `APPLIED/REJECTED` để dễ học. Hệ thống thật có thể mở rộng state/schema và phải xử lý ACK đến sai thứ tự.

### 17.2. LWT và presence ONLINE không thay business ACK

Keep Alive/Last Will chỉ phản ánh trạng thái MQTT connection trong phạm vi giao thức; một thiết bị vẫn online nhưng business worker có thể treo. Khi không có ACK, không tự tạo command mới nguy hiểm mà thiếu đối soát hoặc idempotency.

## 18. Session, retained và reconnect ảnh hưởng thế nào?

| Cơ chế | Làm gì | Không làm |
| --- | --- | --- |
| MQTT QoS | Quy định handshake/delivery ở tầng protocol. | DB exactly-once. |
| `cleanSession=false` | Có thể giữ subscription/offline QoS1/2 messages theo broker policy. | Persist Spring outbox. |
| Retained | Lưu snapshot cuối cùng của một topic. | Lưu toàn bộ command events. |
| Automatic reconnect | Tìm cách khôi phục connection. | Durable business retry. |
| Delivery token | Theo dõi runtime publish operation. | Trở thành durable event record. |
| Last Will | Broker phát khi client connection mất bất thường. | Business ACK cho lệnh. |

Một publisher có thể nhận PUBACK từ broker dù subscriber đang offline. Subscriber có được giao message sau reconnect phụ thuộc QoS/session/subscription/Client ID và broker persistence. Token của publisher **không** cho biết thiết bị đã xử lý khi nào.

Client ID trùng giữa hai clients đang hoạt động có thể gây broker ngắt kết nối luân phiên. Nếu cần persistent session, ID phải ổn định *và* chỉ có một active owner của logical subscriber.

### 18.1. Vì sao command không nên retained?

Retained command một lần có thể được giao lại cho subscriber mới đăng ký và kích hoạt hành động cũ. Demo đặt `MqttHeaders.RETAINED=false`. Nếu hệ thống thực sự dùng desired-state retained, cần schema version/expiry và policy idempotent rõ.

### 18.2. Process restart không phục hồi Java token cũ

Khi app crash, token object và callback state trong RAM không còn. Broker có thể đã nhận PUBLISH. Cần outbox/inbox bền, business ID ổn định và đối soát ACK rồi retry theo policy, không dựa vào token cũ.

## 19. Backpressure, thread và ngân sách timeout

| Kiểu channel/handler | Ưu điểm | Hạn chế |
| --- | --- | --- |
| `DirectChannel` + sync publish | Lỗi đồng bộ dễ theo dõi. | Chặn producer/HTTP/poller khi broker chậm. |
| `DirectChannel` + async publish | Giảm thời gian caller đợi. | Cần theo dõi result muộn/inflight, không dùng return làm ACK. |
| `ExecutorChannel` | Tách thread producer. | Cần giới hạn pool/queue, error handling. |
| `QueueChannel` | Buffer message nội bộ. | Cần poller; RAM queue có thể mất khi restart. |
| Durable outbox | Khôi phục pending event sau crash. | Có thể gửi lặp; cần idempotency. |

`setCompletionTimeout(5000)` **không phải circuit breaker**. Nó không tự áp quota in-flight, retry budget, backoff, DLQ, rate limit hoặc business acknowledgement. Nếu broker mất kết nối kéo dài mà upstream tiếp tục tạo hàng chục nghìn messages, cần bounded resources, durable buffering và admission control.

### 19.1. Khi HTTP timeout sớm hơn MQTT/business processing

HTTP có thể hết 2 giây trong khi publish đợi 5 giây và device trả ACK sau 20 giây. Không nên giữ request vô hạn để gọi đó là đồng bộ. Mẫu phổ biến:

1. Ghi command/outbox, trả `202 Accepted` với `commandId`.
2. Worker publish MQTT và ghi publish outcome.
3. Client tra cứu status hoặc nhận webhook/event.
4. ACK consumer xác minh kết quả và commit DB.

`202 Accepted` không mang nghĩa device đã thực hiện lệnh; nó chỉ thể hiện server chấp nhận công việc theo API contract.

## 20. Observability: phải đo ba tầng

| Metric/field gợi ý | Mục đích |
| --- | --- |
| `mqtt_publish_attempts_total` | Số attempts, gồm retries. |
| `mqtt_publish_completed_total{qos}` | Số publish completions được ghi nhận. |
| `mqtt_publish_timeout_total` | Số operation chờ quá hạn. |
| `mqtt_publish_uncertain_total` | Số event chưa biết broker đã nhận chưa. |
| `mqtt_publish_inflight` | Áp lực publish chưa hoàn tất. |
| `mqtt_client_connected{role}` | Trạng thái các MQTT clients. |
| `outbox_ready_count` | Backlog công việc. |
| `outbox_oldest_age_seconds` | Tuổi event tồn chưa xử lý. |
| `business_ack_received_total{result}` | ACK nghiệp vụ theo kết quả. |
| `business_ack_latency_seconds` | Khoảng thời gian command → ACK. |
| `business_duplicate_ignored_total` | Số duplicate bị dedup. |
| `mqtt_error_total{category}` | Phân loại network/ACL/schema/downstream. |

Tên metric trên chỉ là đề xuất, không phải Spring Integration/Paho mặc định luôn phát đúng tên. Tránh gắn từng `deviceId`/`commandId` vào metric labels vì sẽ tạo cardinality rất cao; dùng logs/traces có kiểm soát để đối chiếu message cụ thể.

Trace bình thường:

~~~text
cmd-1001 CREATED
cmd-1001 OUTBOX_COMMITTED
cmd-1001 PUBLISH_ATTEMPTED
cmd-1001 MQTT_PUBLISHED
cmd-1001 BUSINESS_ACK_RECEIVED
cmd-1001 BUSINESS_ACKNOWLEDGED
~~~

Trace uncertainty:

~~~text
cmd-1002 PUBLISH_ATTEMPTED
cmd-1002 PUBLISH_UNCERTAIN (PUBACK mất)
cmd-1002 BUSINESS_ACK_RECEIVED (đến muộn)
cmd-1002 BUSINESS_ACKNOWLEDGED
~~~

Log phải phân biệt sự kiện **đã quan sát** với kết quả suy đoán. Completion timeout không chứng minh device chưa xử lý, và ACK được nhận chưa đồng nghĩa DB đã commit thành công.

## 21. Các lỗi phổ biến

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| `channel.send()` trả true nhưng không thấy subscriber. | Spring handoff khác MQTT delivery. | Kiểm tra publish result, broker, ACL và subscription. |
| Token complete nhưng thiết bị chưa chạy. | Token chỉ theo dõi MQTT operation. | Cần ACK nghiệp vụ. |
| QoS0 token complete nhưng broker không thấy packet. | QoS0 không có broker PUBACK. | Chọn QoS theo SLA, không hứa delivery. |
| QoS1 timeout nhưng device nhận command. | PUBACK bị mất/chậm. | Unknown outcome, idempotent retry. |
| QoS2 vẫn xử lý side effect trùng. | Hai publications riêng hoặc business retry. | Unique command ID/DB idempotency. |
| Không thấy DeliveredEvent trong async. | Config/version/callback semantics khác. | Kiểm tra asyncEvents/API và test broker. |
| Async send thành công nhưng publish lỗi muộn. | Không có sync exception sau return. | Event/error monitoring + outbox. |
| Packet ID map nhầm command. | ID reuse, thiếu client instance/epoch. | Dùng business ID và correlation có scope. |
| Restart mất tokens. | Token chỉ trong runtime. | Durable outbox, replay/đối soát. |
| HTTP timeout nhưng device đã thực thi. | API deadline ngắn hơn ACK. | Trả command ID/status, không tạo command mới tùy tiện. |
| Retained command thực hiện lại sau subscribe. | Retained=true cho command một lần. | Retained=false, cleanup retained sai. |
| ACK hai lần làm DB cập nhật hai lần. | ACK handler thiếu idempotency. | Unique key/atomic transition. |
| Client reconnect liên tục. | Client ID trùng hoặc ACL/network. | Kiểm tra broker logs và Client ID. |
| Device REJECTED nhưng backend ghi APPLIED. | Nhầm receipt ACK với result. | Validate result/state machine. |
| Error channel không thấy lỗi async. | Error path/callback khác kỳ vọng. | Test đúng framework event/error configuration. |
| Queue đầy khi broker offline. | Không có backpressure. | Rate limit, bounded queue, durable outbox. |

## 22. Bài tập thực hành

**Bối cảnh:** hệ thống điều khiển các thiết bị qua HTTP/MQTT. Lệnh phải được lưu trước khi gửi, broker có thể offline 30 giây hoặc mất PUBACK, và device không được xử lý trùng dù command được replay.

Yêu cầu:

1. Định nghĩa `Command(commandId, deviceId, action)` và outbox record bền vững.
2. HTTP API validate quyền, lưu command/outbox transactionally và trả command ID.
3. Tạo outbound Spring channel `mqtt.commands.out` và `MqttPahoMessageHandler` với QoS1, retained=false.
4. Thử sync `setAsync(false)`, đo caller latency/exception với broker bình thường và broker chậm.
5. Thử async `setAsync(true)` + events ở phiên bản hỗ trợ; giải thích return và completion khác nhau.
6. Viết raw Paho demo lấy `IMqttDeliveryToken`, `waitForCompletion(5000)` và log packet ID cho mục đích kỹ thuật.
7. Dùng broker test subscribe `devices/+/commands` và `devices/+/ack`.
8. Thiết bị giả lập xử lý idempotent theo command ID, trả ACK `APPLIED` hoặc `REJECTED`.
9. Tạo inbound ACK adapter và flow validate JSON, topic, device identity và command ownership.
10. Viết JUnit no-broker cho channel, serialization, topic/QoS/retained và ACK parsing.
11. Test QoS0/1/2, giải thích các handshake/token completion.
12. Tạo fault injection làm PUBACK mất sau khi broker đã nhận PUBLISH.
13. Ghi `PUBLISH_UNCERTAIN` rồi retry cùng `commandId`, chứng minh không có duplicate side effect.
14. Crash worker sau PUBACK nhưng trước DB commit; restart và đối soát outbox.
15. Test business ACK đến sau publish timeout, đến trùng hoặc ACK từ device khác.
16. Kiểm soát Client ID, broker ACL/TLS, queue capacity, retry budget và metrics.
17. Dùng HTTP status lookup để caller theo dõi command thay vì chờ ACK vô hạn.
18. Chứng minh trạng thái `APPLIED` chỉ được commit từ business ACK đã xác minh.

**Tiêu chí đạt:** phân biệt được Spring handoff, Paho publish completion và verified business ACK; xử lý timeout uncertain; giữ message qua restart; không lặp side effect; test broker thật cùng test giả lập có giới hạn trách nhiệm rõ.

## 23. Câu hỏi tự kiểm tra

1. `IMqttDeliveryToken` gắn với thao tác nào?
2. `waitForCompletion(5000)` là giây hay mili giây?
3. `isComplete() == true` ở QoS1 chứng minh điều gì?
4. `deliveryComplete(...)` khác lời gọi đợi token ra sao?
5. MQTT packet ID có thể làm business primary key không?
6. QoS0 có PUBACK không?
7. QoS1 dùng packet ACK nào và vì sao có thể duplicate?
8. QoS2 gồm những bước nào và có bảo đảm DB exactly-once không?
9. Khi broker nhận PUBLISH mà PUBACK mất, caller sẽ thấy tình huống nào?
10. Vì sao completion timeout không chứng minh broker chưa nhận?
11. `MessageChannel.send()` trả true có đồng nghĩa MQTT ACK không?
12. `setAsync(true)` thay đổi error/timing thế nào?
13. `setAsyncEvents(true)` có bảo đảm một DeliveredEvent cho mọi message không?
14. `MqttMessageDeliveredEvent` có xác nhận thiết bị đã thực hiện command không?
15. Connection timeout và completion timeout khác nhau ở đâu?
16. Vì sao business ID cần nằm trong JSON MQTT v3?
17. ACK flow nên đọc topic bằng `MqttHeaders.RECEIVED_TOPIC` hay `MqttHeaders.TOPIC`?
18. Làm sao reject ACK của device khác command owner?
19. Khi business ACK tới sau token timeout, worker nên làm gì?
20. Vì sao outbox vẫn cần khi publish QoS2?
21. Một app crash ngay sau PUBACK có thể phát lại event không?
22. Retained command một lần có rủi ro gì?
23. Fake handler test chứng minh được gì và chưa được gì?
24. Muốn test token timeout phải fault injection ở lớp nào?
25. Vì sao HTTP API nên cân nhắc 202/status lookup?
26. Metrics nào phân biệt MQTT publish completion và business ACK?
27. Client ID trùng giữa hai instances gây vấn đề gì?
28. Hai tầng retry MQTT và outbox có thể tạo duplicate thế nào?
29. Device trả REJECTED có phải lỗi MQTT publish không?
30. Persistent session có làm publisher token biết khi nào device xử lý offline message không?

**Gợi ý:** token theo dõi một MQTT operation; protocol ACK không thay business ACK. Chỉ business ACK hợp lệ và DB commit mới chứng minh kết thúc lệnh theo contract.

## 24. Kết luận

**Delivery token và xác nhận publish** cần được nhìn qua ba ranh giới độc lập:

- **Paho `IMqttDeliveryToken`** theo dõi MQTT PUBLISH; `waitForCompletion(...)` và callback `deliveryComplete(...)` là cách quan sát operation completion.
- **MQTT QoS 0/1/2** quy định các handshake khác nhau: QoS0 không có PUBACK, QoS1 có PUBACK, QoS2 dùng PUBREC/PUBREL/PUBCOMP.
- **`MqttPahoMessageHandler`** có chế độ sync/async, completion timeout và event quan sát tùy configuration/version; chúng không tạo transaction giữa broker và database.
- **Publish completion không phải ACK nghiệp vụ.** Chỉ một ACK riêng có command ID, được authenticate/validate và commit ở backend mới xác nhận thiết bị đã xử lý theo contract.
- **Timeout có thể là unknown outcome.** Broker có thể đã nhận dù caller không thấy ACK; cần durable outbox, stable command ID, retry có giới hạn và idempotent device.
- **Session, retained, reconnect và error channel** bổ trợ delivery nhưng không thay thế business processing state.

Trong module **SPRING_INTEGRATION_ADAPTERS**, tách rõ **Spring handoff → MQTT publish completion → business ACK → database commit** giúp hệ thống truy vết message đúng sự thật, xử lý an toàn khi broker/network không ổn định và tránh báo hoàn tất khi nghiệp vụ chưa được xác minh.



